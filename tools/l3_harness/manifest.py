#!/usr/bin/env python3
"""Build and validate the L3 corpus manifest.

The manifest is the contract between the Python readers and the future Ghidra
L3 harness: for every corpus file it records the size, SHA-256, the reader
under test, the case family and the verdict that reader must produce.  It is
plain JSON, so it can be reviewed in a diff and rebuilt from a staging tree.

The manifest never contains vendor data itself; it only names files relative
to a corpus root.  Building needs files, validating the *shape* does not, and
the package self-test uses synthetic files in a temporary directory.

Case families (``case``) fix the expected verdict, so a typo such as
``"MAYBE"`` or ``"accept"`` is a validation error, not a silent pass.

Usage::

    python3 tools/l3_harness/manifest.py schema
    python3 tools/l3_harness/manifest.py build --root /tmp/l3/corpus \\
        --out /tmp/l3/manifest.json \\
        --case factory:cmp_ind:REFER001/ADDRE001.DAT.cmp \\
        --case corrupt_ind:cmp_ind:REFER001/ADDRE001.DAT.cmp.bad-ind
    python3 tools/l3_harness/manifest.py validate /tmp/l3/manifest.json \\
        --root /tmp/l3/corpus
    python3 tools/l3_harness/manifest.py selftest

Exit codes: ``0`` ok, ``1`` validation problems, ``2`` usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath

SCHEMA = "osm2leaf.l3.manifest/v1"
GENERATOR = "tools/l3_harness/manifest.py"

VERDICTS = ("ACCEPT", "REJECT")

READERS = {
    "cmp_lst": "CMP.LST and map-path opener",
    "cmp_ind": "REFER/ADDRE/POINT .cmp + .ind container reader",
    "drstr": "DRSTR001.DAT directory tree parser",
    "tile": "MAPAL001 BxxRyyR.DAT tile reader",
    "hdd_info": "VER_INFO/HDD_INFO.TXT map-code parser",
}

#: ``case`` -> allowed readers, mandatory verdict and purpose.
CASES = {
    "factory": {
        "readers": ("cmp_lst", "cmp_ind", "drstr", "tile", "hdd_info"),
        "verdict": "ACCEPT",
        "purpose": "factory file is accepted unchanged",
    },
    "noop_rebuild": {
        "readers": ("cmp_ind",),
        "verdict": "ACCEPT",
        "purpose": "container identity after a no-op rebuild",
    },
    "recompressed": {
        "readers": ("cmp_ind",),
        "verdict": "ACCEPT",
        "purpose": "recompressed zlib chunks are accepted",
    },
    "poi_rename": {
        "readers": ("cmp_ind",),
        "verdict": "ACCEPT",
        "purpose": "same-length POI rename is accepted",
    },
    "corrupt_ind": {
        "readers": ("cmp_ind",),
        "verdict": "REJECT",
        "purpose": "corrupted .ind offset or size is rejected",
    },
    "truncated_cmp": {
        "readers": ("cmp_ind",),
        "verdict": "REJECT",
        "purpose": "truncated .cmp is rejected",
    },
    "tile_factory": {
        "readers": ("tile",),
        "verdict": "ACCEPT",
        "purpose": "factory tile decodes",
    },
    "tile_edited": {
        "readers": ("tile",),
        "verdict": "ACCEPT",
        "purpose": "writer-produced tile is accepted",
    },
    "drstr_factory": {
        "readers": ("drstr",),
        "verdict": "ACCEPT",
        "purpose": "factory DRSTR001.DAT tree parses",
    },
    "drstr_size_mismatch": {
        "readers": ("drstr",),
        "verdict": "REJECT",
        "purpose": "DRSTR entry size disagrees with the file",
    },
    "hdd_info_factory": {
        "readers": ("hdd_info",),
        "verdict": "ACCEPT",
        "purpose": "factory HDD_INFO.TXT map code matches",
    },
    "hdd_info_mismatch": {
        "readers": ("hdd_info",),
        "verdict": "REJECT",
        "purpose": "HDD_INFO.TXT map code does not match",
    },
}

ENTRY_KEYS = {
    "id",
    "case",
    "reader",
    "path",
    "sha256",
    "size",
    "expected",
    "notes",
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ManifestError(ValueError):
    """Raised when a manifest cannot be built from the given inputs."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_path(value: str) -> str | None:
    if not value:
        return "path is empty"
    if value.startswith("/") or value.startswith("~"):
        return "path must be relative to the corpus root"
    if "\\" in value:
        return "path must use forward slashes"
    parts = PurePosixPath(value).parts
    if ".." in parts:
        return "path must not escape the corpus root"
    if value.endswith("/"):
        return "path must name a file, not a directory"
    return None


def validate(doc, root=None, check_files: bool = True) -> list[str]:
    """Return a list of problems; an empty list means the manifest is valid.

    ``root`` enables file-existence/size/SHA-256 checks.  With ``root=None``
    only the document shape and internal consistency are checked.
    """

    problems: list[str] = []

    if not isinstance(doc, dict):
        return ["manifest must be a JSON object"]
    if doc.get("schema") != SCHEMA:
        problems.append(
            f"schema: expected {SCHEMA!r}, got {doc.get('schema')!r}"
        )
    for key in ("generator", "notes"):
        value = doc.get(key)
        if value is not None and not isinstance(value, str):
            problems.append(f"{key}: must be a string")

    entries = doc.get("corpus")
    if not isinstance(entries, list):
        problems.append("corpus: missing or not a list")
        return problems
    if not entries:
        problems.append("corpus: no entries")
        return problems

    ids: dict[str, int] = {}
    pairs: dict[tuple[str, str], int] = {}
    file_cache: dict[str, tuple[int, str] | None] = {}

    for index, entry in enumerate(entries):
        where = f"corpus[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{where}: entry is not an object")
            continue

        unknown_keys = sorted(set(entry) - ENTRY_KEYS)
        if unknown_keys:
            problems.append(f"{where}: unknown key(s) {unknown_keys}")

        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not entry_id.strip():
            problems.append(f"{where}: missing id")
        else:
            where = f"corpus[{index}] ({entry_id})"
            if entry_id in ids:
                problems.append(
                    f"{where}: duplicate id, first used at corpus[{ids[entry_id]}]"
                )
            else:
                ids[entry_id] = index

        case = entry.get("case")
        case_spec = CASES.get(case) if isinstance(case, str) else None
        if case_spec is None:
            problems.append(
                f"{where}: unknown case {case!r}; known: {sorted(CASES)}"
            )

        reader = entry.get("reader")
        if reader not in READERS:
            problems.append(
                f"{where}: unknown reader {reader!r}; known: {sorted(READERS)}"
            )
        elif case_spec is not None and reader not in case_spec["readers"]:
            problems.append(
                f"{where}: case {case!r} does not apply to reader {reader!r}; "
                f"allowed: {list(case_spec['readers'])}"
            )

        expected = entry.get("expected")
        if expected not in VERDICTS:
            problems.append(
                f"{where}: unknown verdict {expected!r}; "
                f"expected one of {list(VERDICTS)}"
            )
        elif case_spec is not None and expected != case_spec["verdict"]:
            problems.append(
                f"{where}: case {case!r} requires verdict "
                f"{case_spec['verdict']!r}, got {expected!r}"
            )

        path = entry.get("path")
        if not isinstance(path, str):
            problems.append(f"{where}: missing path")
            path = None
        else:
            path_problem = _check_path(path)
            if path_problem:
                problems.append(f"{where}: {path_problem}: {path!r}")
            if isinstance(reader, str):
                key = (path, reader)
                if key in pairs:
                    problems.append(
                        f"{where}: duplicate (path, reader) pair, first used at "
                        f"corpus[{pairs[key]}]"
                    )
                else:
                    pairs[key] = index

        size = entry.get("size")
        if not _is_int(size) or size < 0:
            problems.append(f"{where}: size must be a non-negative integer")

        digest = entry.get("sha256")
        if not isinstance(digest, str) or not _SHA256_RE.match(digest):
            problems.append(
                f"{where}: sha256 must be 64 lowercase hex characters"
            )

        notes = entry.get("notes")
        if notes is not None and not isinstance(notes, str):
            problems.append(f"{where}: notes must be a string")

        if root is None or not check_files or path is None:
            continue
        if path in file_cache:
            actual = file_cache[path]
        else:
            target = Path(root) / path
            if not target.is_file():
                problems.append(f"{where}: file not found under root: {target}")
                file_cache[path] = None
                continue
            actual = (target.stat().st_size, sha256_file(target))
            file_cache[path] = actual
        if actual is None:
            continue
        actual_size, actual_sha = actual
        if _is_int(size) and actual_size != size:
            problems.append(
                f"{where}: size mismatch (manifest {size}, file {actual_size})"
            )
        if isinstance(digest, str) and actual_sha != digest:
            problems.append(
                f"{where}: sha256 mismatch (manifest {digest}, file {actual_sha})"
            )

    return problems


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "entry"


def build(root, specs) -> dict:
    """Build a manifest from ``(case, reader, path, expected)`` tuples.

    ``root`` is the corpus staging tree; every ``path`` is resolved under it.
    ``expected`` may be ``None`` to use the case's mandatory verdict.
    """

    root = Path(root)
    problems: list[str] = []
    used_ids: set[str] = set()
    entries: list[dict] = []

    for spec in specs:
        if len(spec) != 4:
            raise ManifestError([f"bad spec {spec!r}: want (case, reader, path, expected)"])
        case, reader, path, expected = spec

        case_spec = CASES.get(case)
        if case_spec is None:
            problems.append(f"unknown case {case!r}")
            continue
        if reader not in READERS:
            problems.append(f"unknown reader {reader!r}")
            continue
        if reader not in case_spec["readers"]:
            problems.append(
                f"case {case!r} does not apply to reader {reader!r}"
            )
            continue
        if expected is None:
            expected = case_spec["verdict"]
        if expected != case_spec["verdict"]:
            problems.append(
                f"case {case!r} requires verdict {case_spec['verdict']!r}, "
                f"got {expected!r}"
            )
            continue
        path_problem = _check_path(path)
        if path_problem:
            problems.append(f"{path_problem}: {path!r}")
            continue

        target = root / path
        if not target.is_file():
            problems.append(f"file not found: {target}")
            continue

        entry_id = _slug(f"{case}-{path}")
        candidate = entry_id
        suffix = 2
        while candidate in used_ids:
            candidate = f"{entry_id}-{suffix}"
            suffix += 1
        used_ids.add(candidate)

        entries.append(
            {
                "id": candidate,
                "case": case,
                "reader": reader,
                "path": path,
                "sha256": sha256_file(target),
                "size": target.stat().st_size,
                "expected": expected,
            }
        )

    if problems:
        raise ManifestError(problems)
    if not entries:
        raise ManifestError(["no entries were built"])

    doc = {
        "schema": SCHEMA,
        "generator": GENERATOR,
        "corpus": entries,
    }
    problems = validate(doc, root=root)
    if problems:
        raise ManifestError(problems)
    return doc


def refresh(doc, root) -> dict:
    """Recompute ``size``/``sha256`` for every existing entry."""

    root = Path(root)
    problems: list[str] = []
    for entry in doc.get("corpus", []):
        path = entry.get("path")
        if not isinstance(path, str):
            continue
        target = root / path
        if not target.is_file():
            problems.append(f"{entry.get('id', path)}: file not found: {target}")
            continue
        entry["size"] = target.stat().st_size
        entry["sha256"] = sha256_file(target)
    if problems:
        raise ManifestError(problems)
    return doc


def json_schema() -> dict:
    """Return the JSON Schema for a manifest document."""

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA,
        "title": "OSM2Leaf L3 corpus manifest",
        "description": (
            "Corpus contract for the Ghidra L3 reader harness. Paths are "
            "relative to a corpus root; no vendor data is stored here."
        ),
        "type": "object",
        "required": ["schema", "corpus"],
        "additionalProperties": False,
        "properties": {
            "schema": {"const": SCHEMA},
            "generator": {"type": "string"},
            "notes": {"type": "string"},
            "corpus": {
                "type": "array",
                "minItems": 1,
                "items": {"$ref": "#/$defs/entry"},
            },
        },
        "$defs": {
            "entry": {
                "type": "object",
                "required": [
                    "id",
                    "case",
                    "reader",
                    "path",
                    "sha256",
                    "size",
                    "expected",
                ],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "case": {"enum": sorted(CASES)},
                    "reader": {"enum": sorted(READERS)},
                    "path": {
                        "type": "string",
                        "minLength": 1,
                        "pattern": "^(?!/)(?!.*\\\\)(?!.*(^|/)\\.\\.(/|$)).+$",
                    },
                    "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "size": {"type": "integer", "minimum": 0},
                    "expected": {"enum": list(VERDICTS)},
                    "notes": {"type": "string"},
                },
            }
        },
    }


def _parse_spec(text: str):
    parts = text.split(":", 3)
    if len(parts) < 3:
        raise argparse.ArgumentTypeError(
            "want CASE:READER:PATH[:EXPECTED]"
        )
    case, reader, path = parts[0], parts[1], parts[2]
    expected = parts[3] if len(parts) == 4 else None
    return case, reader, path, expected


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build or validate an L3 corpus manifest"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build_cmd = sub.add_parser("build", help="build a manifest from a staging root")
    build_cmd.add_argument("--root", required=True, help="corpus staging root")
    build_cmd.add_argument("--out", help="write JSON here (default: stdout)")
    build_cmd.add_argument(
        "--case",
        action="append",
        default=[],
        type=_parse_spec,
        metavar="CASE:READER:PATH[:EXPECTED]",
        help="corpus entry (repeatable)",
    )

    refresh_cmd = sub.add_parser("refresh", help="recompute hashes for a manifest")
    refresh_cmd.add_argument("manifest")
    refresh_cmd.add_argument("--root", required=True, help="corpus staging root")
    refresh_cmd.add_argument("--out", help="write JSON here (default: in place)")

    validate_cmd = sub.add_parser("validate", help="validate a manifest")
    validate_cmd.add_argument("manifest")
    validate_cmd.add_argument("--root", help="also verify size and SHA-256")
    validate_cmd.add_argument(
        "--no-files", action="store_true", help="skip file checks even with --root"
    )
    validate_cmd.add_argument("--json", action="store_true")

    sub.add_parser("schema", help="print the JSON Schema")
    sub.add_parser("selftest", help="run the package self-test")
    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--selftest"]:
        argv = ["selftest"]

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "schema":
        print(json.dumps(json_schema(), indent=2))
        return 0

    if args.command == "selftest":
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from l3_harness import selftest

        return selftest.main([])

    if args.command == "build":
        try:
            doc = build(args.root, args.case)
        except ManifestError as exc:
            for problem in exc.problems:
                print(f"error: {problem}", file=sys.stderr)
            return 1
        text = json.dumps(doc, indent=2) + "\n"
        if args.out:
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            print(f"wrote {out} ({len(doc['corpus'])} entries)")
        else:
            sys.stdout.write(text)
        return 0

    if args.command == "refresh":
        try:
            doc = refresh(load(args.manifest), args.root)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        problems = validate(doc, root=args.root)
        if problems:
            for problem in problems:
                print(f"error: {problem}", file=sys.stderr)
            return 1
        text = json.dumps(doc, indent=2) + "\n"
        out = Path(args.out) if args.out else Path(args.manifest)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out} ({len(doc['corpus'])} entries)")
        return 0

    if args.command == "validate":
        try:
            doc = load(args.manifest)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: cannot read {args.manifest}: {exc}", file=sys.stderr)
            return 1
        problems = validate(
            doc,
            root=args.root,
            check_files=not args.no_files,
        )
        if args.json:
            print(
                json.dumps(
                    {
                        "manifest": args.manifest,
                        "entries": len(doc.get("corpus", []) or []),
                        "root": args.root,
                        "problems": problems,
                        "result": "PASS" if not problems else "FAIL",
                    },
                    indent=2,
                )
            )
        else:
            for problem in problems:
                print(f"FAIL {problem}")
            if problems:
                print(f"RESULT: FAIL ({len(problems)} problem(s))")
            else:
                print(
                    f"RESULT: PASS ({len(doc.get('corpus', []))} entries"
                    + (f", files verified under {args.root}" if args.root and not args.no_files else "")
                    + ")"
                )
        return 0 if not problems else 1

    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
