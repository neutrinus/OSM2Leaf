#!/usr/bin/env python3
"""L3 rung of the verification ladder: run every declared L3 target.

``l3check.py`` is the L3 counterpart of ``cardcheck.py`` (L1) and
``l2check.py`` (L2).  It takes a corpus built by
``tools/l3_harness/corpus.py`` (or one supplied with ``--corpus``), asks
``tools/l3_harness/runner.py`` to run every target declared in
``tools/l3_harness/targets.json``, and reports one status per target:

============  ==============================================================
``PASS``      the engine's verdict matched the target's expectation
``FAIL``      a mismatch, an invalid input, or a target that could not run
``SKIP``      the requested back end is absent; nothing is claimed
``BLOCKED``   the reader has no located entry point; nothing is claimed
============  ==============================================================

Exit codes: ``0`` every runnable target passed (blocked/skipped targets are
counted, not failed), ``1`` a target failed or the corpus/inputs were invalid,
``2`` usage error, ``3`` nothing was runnable (every target blocked or
skipped; no verdict is claimed).

The tool never fakes a pass.  A reader that is not located is ``BLOCKED`` no
matter how good the corpus is, an absent back end is ``SKIP``, a missing
corpus file is a ``FAIL``, and a synthetic PASS proves only that the
runner/dispatcher path works -- not that the firmware accepts a card.  Every
row carries its reader ID and the claim IDs its evidence rests on.

Card gate (M9.12): ``--card OUT.img --factory IMG`` finds files that differ
from the factory image and reports every relevant L3 target as ``pass`` /
``fail`` / ``not-yet-available``.  It exits non-zero on any fail.  Targets
whose reader is not runnable are reported honestly as ``not-yet-available``
(e.g. the POI reader / M9.10); the gate never synthesizes a pass.

Usage::

    python3 tools/l3check.py --build-corpus
    python3 tools/l3check.py --corpus /tmp/opencode/l3-corpus
    python3 tools/l3check.py --corpus /tmp/opencode/l3-corpus --target probe-zlib-cmf
    python3 tools/l3check.py --card us_S2.img --factory LEAF_US.img
    python3 tools/l3check.py --corpus /tmp/opencode/l3-corpus --json
    python3 tools/l3check.py --selftest
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from l3_harness import corpus as corpus_mod  # noqa: E402
from l3_harness import engine as engine_mod  # noqa: E402
from l3_harness import manifest as manifest_mod  # noqa: E402
from l3_harness import runner as runner_mod  # noqa: E402

SCHEMA = "osm2leaf.l3check/v1"

#: Reservation from TODO M9.8 (C-1700-C-1709); this tool uses C-1700.
TOOL_CLAIM = "C-1700"
EXP_RECORD = "EXP-2026-11-06-M9.8-l3check"
#: Reservation from TODO M9.12 (C-2160-C-2169); card gate uses C-2160.
CARD_CLAIM = "C-2160"
CARD_EXP = "EXP-2026-11-08-M9.12-l3check-card"

#: One row per target in ``targets.json``: the reader under test and the claim
#: IDs its evidence rests on.  C-1670 is the runner, C-1690 the corpus (both
#: pipeline evidence); a blocked row names the claims that describe its
#: blocker, and C-520/C-528 mark the retired map-code comparator.  The table is
#: validated against ``targets.json`` on every run: a target added or renamed
#: there makes this tool FAIL instead of silently dropping it.
TARGET_EVIDENCE = {
    "probe-zlib-cmf": {
        "reader": "synthetic",
        "claims": ("C-1670", "C-1690"),
        "note": "runner and corpus claim; the probe is a pipeline fixture",
    },
    "hddinfo_compare": {
        "reader": "hdd_info",
        "claims": ("C-521",),
        "note": "HDD_INFO literals are located; the parser is behind a COM object",
    },
    "cmp_ind_reader": {
        "reader": "cmp_ind",
        "claims": (),
        "note": "no .cmp/.ind reader entry point yet",
    },
    "tile_reader": {
        "reader": "tile",
        "claims": (),
        "note": "no tile reader entry point yet",
    },
    "drstr_parser": {
        "reader": "drstr",
        "claims": (),
        "note": "no DRSTR parser entry point yet",
    },
    "mapcode_comparator": {
        "reader": "hdd_info",
        "claims": ("C-520", "C-528"),
        "note": "retired BT_MGR.dll chain; kept blocked on purpose",
    },
}

STATUSES = ("PASS", "FAIL", "SKIP", "BLOCKED")

#: ``runner.py`` status -> ladder status.  A missing entry means the runner
#: returned something this tool does not understand, which is a FAIL.
_RUNNER_STATUS = {
    "PASS": "PASS",
    "SKIP": "SKIP",
    "BLOCKED": "BLOCKED",
    "MISMATCH": "FAIL",
    "INVALID": "FAIL",
}

_CLAIM_RE = re.compile(r"^C-\d+$")


class UsageError(ValueError):
    """The command line cannot be turned into a run."""


# --------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------


def _temp_corpus_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="l3check-corpus-"))


def _resolve_corpus(args) -> tuple[dict, dict | None]:
    """Build or validate the corpus; never invent one that was not asked for."""

    if getattr(args, "corpus", None) and getattr(args, "build_corpus", False):
        raise UsageError("pass either --corpus DIR or --build-corpus, not both")

    built = None
    if getattr(args, "corpus", None):
        root = Path(args.corpus).expanduser()
        source = "supplied"
    else:
        root = _temp_corpus_root()
        source = "built"
        try:
            built = corpus_mod.build_corpus(root)
        except (corpus_mod.CorpusError, manifest_mod.ManifestError, OSError) as exc:
            return (
                {
                    "root": str(root),
                    "manifest": str(root / "manifest.json"),
                    "source": source,
                    "entries": 0,
                    "problems": [f"corpus build failed: {exc}"],
                    "kept": True,
                },
                None,
            )

    manifest_path = root / "manifest.json"
    info = {
        "root": str(root),
        "manifest": str(manifest_path),
        "source": source,
        "entries": 0,
        "problems": [],
        "kept": source == "built",
    }
    if built is not None:
        info["build"] = {
            "entries": built["entries"],
            "skipped": list(built["skipped"]),
        }

    try:
        doc = manifest_mod.load(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        info["problems"].append(f"cannot read {manifest_path}: {exc}")
        return info, None

    info["entries"] = len(doc.get("corpus", []))
    info["problems"] = manifest_mod.validate(doc, root=root)
    return info, doc


def _card_info(args) -> dict | None:
    """Legacy --root/--image (recorded only). M9.12 uses --card/--factory."""
    if getattr(args, "card", None) or getattr(args, "factory", None):
        return None
    if not (getattr(args, "root", None) or getattr(args, "image", None)):
        return None
    return {
        "status": "NOT_IMPLEMENTED",
        "checked": False,
        "task": "M9.12",
        "root": getattr(args, "root", None),
        "image": getattr(args, "image", None),
        "note": (
            "card-level L3 uses --card/--factory (M9.12); these paths are "
            "recorded, not checked, and are not evidence"
        ),
    }


# --------------------------------------------------------------------------
# Card gate (M9.12): diff card vs factory, run available targets per diff
# --------------------------------------------------------------------------


def _sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _7z_listing(image: Path) -> dict[str, int]:
    """Return {path: size} for regular files in a FAT image via 7z l -slt."""
    proc = subprocess.run(
        ["7z", "l", "-slt", str(image)],
        capture_output=True,
        text=True,
        errors="replace",
    )
    if proc.returncode not in (0, 1):  # 1 = warnings
        raise UsageError(f"7z l failed for {image}: {proc.stderr.strip()[:200]}")
    files: dict[str, int] = {}
    current: str | None = None
    is_folder = False
    size: int | None = None
    for line in proc.stdout.splitlines():
        if line.startswith("Path = "):
            if current and not is_folder and size is not None and "/" in current:
                # skip archive/partition pseudo-paths (no slash or special)
                files[current] = size
            current = line[7:]
            is_folder = False
            size = None
        elif line.startswith("Folder = "):
            is_folder = line[9:].strip() == "+"
        elif line.startswith("Size = "):
            try:
                size = int(line[7:].strip())
            except ValueError:
                size = None
    if current and not is_folder and size is not None and "/" in current:
        files[current] = size
    return files


def _7z_extract(image: Path, paths: list[str], dest: Path) -> None:
    if not paths:
        return
    dest.mkdir(parents=True, exist_ok=True)
    cmd = ["7z", "e", "-y", f"-o{dest}", str(image), *paths]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if proc.returncode not in (0, 1):
        raise UsageError(f"7z e failed for {image}: {proc.stderr.strip()[:300]}")


def _files_content_differ(card: Path, factory: Path, paths: list[str],
                          tmp: Path) -> list[str]:
    """Extract *paths* from both images and return those with different bytes."""
    if not paths:
        return []
    card_dir = tmp / "card"
    fact_dir = tmp / "factory"
    _7z_extract(card, paths, card_dir)
    _7z_extract(factory, paths, fact_dir)
    differ: list[str] = []
    for rel in paths:
        name = Path(rel).name
        a = card_dir / name
        b = fact_dir / name
        if not a.exists() or not b.exists():
            differ.append(rel)
            continue
        if a.read_bytes() != b.read_bytes():
            differ.append(rel)
    return differ


#: Card-relevant patterns: files that may have an L3 target mapping.
_CARD_RELEVANT_PREFIXES = (
    "VER_INFO/HDD_INFO.TXT",
    "DRSTR001.DAT",
    "REFER001/",
    "MAPAL001/",
)


def _is_card_relevant(path: str) -> bool:
    p = path.replace("\\", "/")
    return any(p == pre or p.startswith(pre) for pre in _CARD_RELEVANT_PREFIXES)


def diff_card_files(card: Path, factory: Path) -> dict:
    """Find card-relevant files that differ between two images.

    Returns a report dict with ``differing`` (sorted paths), ``method``,
    ``identical_images`` and any ``problems``.  Uses 7z listings (size) plus
    content comparison for REFER001/*.ind and size-matched relevant files, so
    same-size content changes are caught for the small/critical set.
    """
    result = {
        "card": str(card),
        "factory": str(factory),
        "method": "7z listing size+content compare (REFER001/ind and size-matched relevant files)",
        "identical_images": False,
        "differing": [],
        "problems": [],
        "card_files": 0,
        "factory_files": 0,
    }
    if not card.exists():
        result["problems"].append(f"card image not found: {card}")
        return result
    if not factory.exists():
        result["problems"].append(f"factory image not found: {factory}")
        return result

    # Fast path: identical files.
    if card.resolve() == factory.resolve() or (
            card.stat().st_size == factory.stat().st_size
            and card.stat().st_size < 512 * 1024 * 1024
            and card.read_bytes() == factory.read_bytes()):
        result["identical_images"] = True
        return result
    # For large identical images, SHA-256 comparison is expensive but correct;
    # S1==factory is a real case. We compare by streaming hash only when sizes
    # match and the caller didn't short-circuit above.
    if card.stat().st_size == factory.stat().st_size:
        try:
            if _sha256_file(card) == _sha256_file(factory):
                result["identical_images"] = True
                result["method"] = "streaming SHA-256 (identical)"
                return result
        except OSError as exc:
            result["problems"].append(f"hash compare failed: {exc}")
            return result

    try:
        card_list = _7z_listing(card)
        fact_list = _7z_listing(factory)
    except (UsageError, FileNotFoundError) as exc:
        result["problems"].append(str(exc))
        return result
    result["card_files"] = len(card_list)
    result["factory_files"] = len(fact_list)

    differing: set[str] = set()
    to_check: list[str] = []
    all_paths = set(card_list) | set(fact_list)
    for rel in sorted(all_paths):
        p = rel.replace("\\", "/")
        if not _is_card_relevant(p):
            continue
        cs, fs = card_list.get(rel), fact_list.get(rel)
        if cs is None or fs is None:
            differing.add(p)
        elif cs != fs:
            differing.add(p)
        elif p.upper().endswith(".IND") or p in (
                "VER_INFO/HDD_INFO.TXT", "DRSTR001.DAT"):
            # Same size but content may differ (.ind is 612 B, critical files).
            to_check.append(rel)

    if to_check:
        with tempfile.TemporaryDirectory(prefix="l3check-diff-") as tmp:
            try:
                differing.update(p.replace("\\", "/") for p in
                                 _files_content_differ(card, factory, to_check,
                                                       Path(tmp)))
            except (UsageError, OSError) as exc:
                result["problems"].append(f"content compare: {exc}")

    result["differing"] = sorted(differing)
    return result


# Card target mapping: (path predicate) -> (target name, adapter, note).
# ``adapter``: "targets.json" = run via runner; "chunk_decoder" = M9.11
# firmware path via chunk_decoder_l3.py (cmp_ind_reader not registered, M9.11b);
# "not-yet-available" = report honestly (M9.10 POI reader).
_CARD_TARGETS = [
    {
        "name": "hddinfo_compare",
        "label": "map-code/HDD_INFO compare (M9.6)",
        "applies": lambda p: p.upper() == "VER_INFO/HDD_INFO.TXT",
        "adapter": "targets.json",
        "unavailable_note": "hddinfo_compare target blocked in targets.json; M9.6 runnable target not registered",
    },
    {
        "name": "cmp_ind_reader",
        "label": ".cmp/.ind chunk decoder (M9.11)",
        "applies": lambda p: p.upper().startswith("REFER001/") and p.upper().endswith((".CMP", ".IND")),
        "adapter": "chunk_decoder",
        "unavailable_note": "cmp_ind_reader blocked in targets.json (M9.11b); chunk_decoder_l3.py adapter used when .cmp/.ind pair available",
    },
    {
        "name": "poi_record_decode",
        "label": "POI record reader (M9.10)",
        "applies": lambda p: p.upper().startswith("REFER001/POINT") and p.upper().endswith(".DAT.CMP"),
        "adapter": "not-yet-available",
        "unavailable_note": "POI reader not yet available (M9.10; no poi_record_decode target in targets.json, name accessor waits M3.11c)",
    },
    {
        "name": "drstr_parser",
        "label": "DRSTR001 parser (M9.14)",
        "applies": lambda p: p.upper() == "DRSTR001.DAT",
        "adapter": "targets.json",
        "unavailable_note": "drstr_parser blocked (compressed sec1/import stubs; M1.2f/M9.24)",
    },
    {
        "name": "tile_reader",
        "label": "tile reader (M9.13)",
        "applies": lambda p: p.upper().startswith("MAPAL001/") and p.upper().endswith(".DAT"),
        "adapter": "targets.json",
        "unavailable_note": "tile_reader blocked (M9.13; runner/module entry constraints)",
    },
]


def _norm_cmp_pair(path: str) -> tuple[str, str] | None:
    """For a .cmp or .ind path return (cmp, ind) base names in REFER001, else None."""
    p = path.replace("\\", "/")
    up = p.upper()
    if not up.startswith("REFER001/"):
        return None
    if up.endswith(".DAT.CMP"):
        return p, p[:-4] + ".ind"
    if up.endswith(".DAT.IND"):
        return p[:-4] + ".cmp", p
    return None


def _chunk_decoder_cmd() -> list[str]:
    return [sys.executable, str(TOOLS_DIR / "chunk_decoder_l3.py")]


def _run_chunk_decoder(card: Path, factory: Path, cmp_rel: str, ind_rel: str,
                       tmp: Path) -> dict:
    """Run M9.11 firmware path on the card's differing .cmp pair vs reference."""
    work = tmp / "chunk"
    _7z_extract(card, [cmp_rel, ind_rel], work / "card")
    _7z_extract(factory, [cmp_rel, ind_rel], work / "factory")
    # chunk_decoder_l3.py needs Navi.exe from IMG256 head (archive) by default
    # or via --image; find it.
    img256 = _find_img256()
    if img256 is None:
        return {"status": "not-yet-available", "verdict": None,
                "detail": "IMG256 (Navi.exe head) not found for chunk decoder; rule 11",
                "l3_claim": False}
    # Run against the card's pair as --cmp/--ind, reference is cmpind.decode of
    # the same pair (chunk_decoder compares to reference). For a correct S2 edit,
    # the firmware should decode the card pair byte-identically to cmpind.decode
    # of that pair.
    cmp_path = work / "card" / Path(cmp_rel).name
    ind_path = work / "card" / Path(ind_rel).name
    cmd = _chunk_decoder_cmd() + [
        "run", str(img256),
        "--cmp", str(cmp_path), "--ind", str(ind_path),
        "--sec1", "zero-mask",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                          timeout=600)
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0 and "verdict: PASS" in out:
        return {"status": "pass", "verdict": "PASS", "detail": out.strip()[-400:],
                "l3_claim": False,
                "note": "M9.11 firmware path via chunk_decoder_l3.py (not targets.json; M9.11b registers cmp_ind_reader)"}
    if proc.returncode == 1 or "FAIL" in out:
        return {"status": "fail", "verdict": "FAIL", "detail": out.strip()[-400:],
                "l3_claim": False}
    if proc.returncode == 4 or "BLOCKED" in out:
        return {"status": "not-yet-available", "verdict": None,
                "detail": "BLOCKED: " + out.strip()[-300:], "l3_claim": False}
    if proc.returncode == 3:
        return {"status": "not-yet-available", "verdict": None,
                "detail": "missing input: " + out.strip()[:200], "l3_claim": False}
    return {"status": "not-yet-available", "verdict": None,
            "detail": f"exit {proc.returncode}: " + out.strip()[:300],
            "l3_claim": False}


def _find_img256() -> Path | None:
    candidates = [
        TOOLS_DIR.parent / "archive" / "head256.img",
        Path(os.environ.get("IMG256", "")),
        Path("/home/marek/projekty/OSM2Leaf/archive/head256.img"),
        Path("/home/marek/projekty/leafre-work/leaf2011.img"),
    ]
    for p in candidates:
        if p and str(p) and p.is_file():
            return p
    return None


def _card_status_norm(status: str) -> str:
    """M9.12 terminology: pass / fail / not-yet-available."""
    if status in ("pass", "PASS"):
        return "pass"
    if status in ("fail", "FAIL", "MISMATCH", "INVALID"):
        return "fail"
    return "not-yet-available"


def build_card_report(card: Path, factory: Path, *, by_name: dict,
                      engine: str = "pysh4") -> dict:
    """M9.12 card gate: diff, then per-target pass/fail/not-yet-available."""
    diff = diff_card_files(card, factory)
    rows: list[dict] = []
    problems = list(diff.get("problems") or [])

    differing = diff.get("differing") or []
    if diff.get("identical_images"):
        differing = []
    seen_targets: set[tuple[str, str]] = set()

    # Always report POI reader availability when POINT files differ, and also
    # include it once as not-yet-available if no POINT diffs but M9.12 requires
    # the POI reader to be reported as "not yet available" where applicable.
    # We report per applicable target for differing files.
    with tempfile.TemporaryDirectory(prefix="l3check-card-") as tmp:
        tmpdir = Path(tmp)
        for ct in _CARD_TARGETS:
            applicable = [p for p in differing if ct["applies"](p)]
            if not applicable and ct["name"] != "poi_record_decode":
                continue
            # Report POI reader once, as not-yet-available, when applicable by
            # spec (M9.12 done-when requires reporting it). Also report when
            # POINT files differ.
            if ct["name"] == "poi_record_decode" and not applicable:
                # "where applicable" - report its availability status once.
                rows.append({
                    "name": ct["name"],
                    "label": ct["label"],
                    "status": "not-yet-available",
                    "files": [],
                    "detail": ct["unavailable_note"],
                    "l3_claim": False,
                })
                continue

            if ct["adapter"] == "not-yet-available":
                rows.append({
                    "name": ct["name"],
                    "label": ct["label"],
                    "status": "not-yet-available",
                    "files": applicable,
                    "detail": ct["unavailable_note"],
                    "l3_claim": False,
                })
                continue

            if ct["adapter"] == "chunk_decoder" and ct["name"] == "cmp_ind_reader":
                # Run on each differing .cmp pair (dedup).
                pairs = []
                for p in applicable:
                    pair = _norm_cmp_pair(p)
                    if pair and pair not in pairs:
                        pairs.append(pair)
                for cmp_rel, ind_rel in pairs:
                    res = _run_chunk_decoder(card, factory, cmp_rel, ind_rel,
                                             tmpdir)
                    rows.append({
                        "name": ct["name"],
                        "label": ct["label"],
                        "status": _card_status_norm(res["status"]),
                        "files": [cmp_rel, ind_rel],
                        "detail": res.get("detail", ""),
                        "l3_claim": res.get("l3_claim", False),
                        "note": res.get("note"),
                    })
                if not pairs:
                    rows.append({
                        "name": ct["name"], "label": ct["label"],
                        "status": "not-yet-available", "files": applicable,
                        "detail": "no .cmp/.ind pair resolved from diff",
                        "l3_claim": False,
                    })
                continue

            # targets.json adapter
            target = by_name.get(ct["name"])
            if target is None:
                rows.append({
                    "name": ct["name"], "label": ct["label"],
                    "status": "not-yet-available", "files": applicable,
                    "detail": f"target {ct['name']} not in targets.json",
                    "l3_claim": False,
                })
                continue
            entry_kind = (target.get("entry") or {}).get("kind")
            if entry_kind == "blocked":
                rows.append({
                    "name": ct["name"], "label": ct["label"],
                    "status": "not-yet-available", "files": applicable,
                    "detail": (target.get("entry") or {}).get("reason")
                              or ct["unavailable_note"],
                    "l3_claim": False,
                })
                continue
            # Runnable target - but we need to supply the right input for the
            # differing file. The generic runner uses corpus; card mode would
            # need per-file input wiring. Report honestly if not wired.
            rows.append({
                "name": ct["name"], "label": ct["label"],
                "status": "not-yet-available", "files": applicable,
                "detail": f"target {ct['name']} is runnable but card-mode per-file input wiring not implemented for this target kind",
                "l3_claim": False,
            })

    counts = {"pass": 0, "fail": 0, "not-yet-available": 0, "total": len(rows)}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    has_fail = counts["fail"] > 0
    runnable = counts["pass"] + counts["fail"]
    if has_fail:
        result_status, exit_code = "FAIL", 1
    elif runnable == 0 and not diff.get("identical_images") and differing:
        # Diffs exist but nothing runnable -> report clearly; not a fake pass.
        result_status, exit_code = "NOT_YET_AVAILABLE", 3
    elif diff.get("identical_images") and runnable == 0:
        # No diffs, nothing to fail on; but also nothing verified.
        result_status, exit_code = "NO_DIFFS", 3
    elif runnable > 0 and counts["fail"] == 0:
        result_status, exit_code = "PASS", 0
    else:
        result_status, exit_code = "NO_DIFFS" if not differing else "NOT_YET_AVAILABLE", 3

    return {
        "schema": SCHEMA,
        "command": "l3check --card",
        "claim": CARD_CLAIM,
        "exp": CARD_EXP,
        "card": str(card),
        "factory": str(factory),
        "diff": diff,
        "targets": rows,
        "counts": counts,
        "result": result_status,
        "exit": exit_code,
        "problems": problems,
        "note": (
            "M9.12 card gate: per-target pass/fail/not-yet-available on files "
            "that differ from factory. POI reader reported as not yet available "
            "where applicable (M9.10). A not-yet-available target is not a pass."
        ),
    }


def _print_card_report(report: dict) -> None:
    print(f"l3check --card: software gate before car test (claim {CARD_CLAIM})")
    print(f"exp      {report['exp']}")
    print(f"card     {report['card']}")
    print(f"factory  {report['factory']}")
    diff = report.get("diff") or {}
    if diff.get("identical_images"):
        print("diff     identical images (no differing files)")
    else:
        differing = diff.get("differing") or []
        print(f"diff     {len(differing)} differing card-relevant file(s) [{diff.get('method','')}]")
        for p in differing[:30]:
            print(f"         {p}")
        if len(differing) > 30:
            print(f"         ... ({len(differing)-30} more)")
    for problem in report.get("problems", []):
        print(f"PROBLEM  {problem}")
    print()
    if not report["targets"]:
        print("targets  (none applicable)")
    else:
        for row in report["targets"]:
            files = ", ".join(row.get("files") or []) or "-"
            print(f"  [{row['status']}] {row['name']}: {row['label']}")
            print(f"           files: {files}")
            print(f"           {row.get('detail','')}")
            if row.get("note"):
                print(f"           note: {row['note']}")
    counts = report["counts"]
    print()
    print(f"counts   pass={counts.get('pass',0)} fail={counts.get('fail',0)} "
          f"not-yet-available={counts.get('not-yet-available',0)} total={counts['total']}")
    if report["result"] == "PASS":
        print("RESULT: PASS (every runnable target passed)")
    elif report["result"] == "FAIL":
        print(f"RESULT: FAIL ({counts.get('fail',0)} target(s) failed; exit 1)")
    elif report["result"] == "NO_DIFFS":
        print("RESULT: NO_DIFFS (no differing files or nothing runnable; exit 3, not a pass)")
    else:
        print(f"RESULT: {report['result']} (exit {report['exit']}; not-yet-available is not a pass)")


# --------------------------------------------------------------------------
# Targets
# --------------------------------------------------------------------------


def _evidence_problems(by_name: dict[str, dict]) -> list[str]:
    """Return every drift between ``TARGET_EVIDENCE`` and ``targets.json``."""

    problems: list[str] = []
    declared = set(by_name)
    known = set(TARGET_EVIDENCE)
    for name in sorted(declared - known):
        problems.append(
            f"target {name!r} has no reader/claim row in TARGET_EVIDENCE"
        )
    for name in sorted(known - declared):
        problems.append(
            f"TARGET_EVIDENCE lists {name!r}, which targets.json does not declare"
        )
    for name in sorted(declared & known):
        row = TARGET_EVIDENCE[name]
        target = by_name[name]
        if row["reader"] != target["reader"]:
            problems.append(
                f"{name}: evidence reader {row['reader']!r} != target reader "
                f"{target['reader']!r}"
            )
        for claim in row["claims"]:
            if not _CLAIM_RE.match(claim):
                problems.append(f"{name}: {claim!r} is not a claim ID")
    return problems


def _select_targets(by_name: dict[str, dict], requested) -> list[dict]:
    if not requested:
        return list(by_name.values())
    unknown = [name for name in requested if name not in by_name]
    if unknown:
        raise UsageError(
            f"unknown target(s) {', '.join(repr(n) for n in unknown)}; known: "
            f"{', '.join(sorted(by_name))}"
        )
    selected: list[str] = []
    for name in requested:
        if name not in selected:
            selected.append(name)
    return [by_name[name] for name in selected]


def _run_one(target: dict, corpus_root: Path, engine: str) -> dict:
    """Run one target through ``runner.run_target``; never raise at the caller."""

    evidence = TARGET_EVIDENCE[target["name"]]
    namespace = argparse.Namespace(
        engine=engine,
        input=None,
        corpus=str(corpus_root),
        max_insns=engine_mod.DEFAULT_MAX_INSNS,
        dry_run=False,
    )
    try:
        payload = runner_mod.run_target(target, namespace)
    except Exception as exc:  # noqa: BLE001 - one target must not abort the run
        payload = {
            "status": "INVALID",
            "exit": runner_mod.EXIT_INVALID,
            "problems": [f"runner error: {type(exc).__name__}: {exc}"],
            "reason": None,
            "l3_claim": False,
        }

    status = _RUNNER_STATUS.get(payload.get("status"), "FAIL")
    problems = list(payload.get("problems") or [])
    if payload.get("status") not in _RUNNER_STATUS:
        problems.append(f"runner returned unknown status {payload.get('status')!r}")
    expect = (target.get("expect") or {}).get("verdict")
    input_info = payload.get("input") or None

    return {
        "name": target["name"],
        "reader": target["reader"],
        "entry": (target.get("entry") or {}).get("kind"),
        "claims": list(evidence["claims"]),
        "claim_note": evidence["note"],
        "expected": expect,
        "status": status,
        "verdict": payload.get("verdict"),
        "accepted": payload.get("accepted"),
        "reason": payload.get("reason"),
        "problems": problems,
        "engine": payload.get("engine") or engine,
        "backend": payload.get("backend"),
        "synthetic": payload.get("synthetic"),
        "l3_claim": payload.get("l3_claim", False),
        "steps": payload.get("cycles"),
        "stub_calls": len(payload.get("stub_calls") or []),
        "input": input_info,
        "runner_exit": payload.get("exit"),
    }


def _counts(rows: list[dict]) -> dict:
    counts = {"pass": 0, "fail": 0, "skip": 0, "blocked": 0}
    for row in rows:
        counts[row["status"].lower()] += 1
    counts["runnable"] = counts["pass"] + counts["fail"]
    counts["total"] = len(rows)
    return counts


def _result(counts: dict) -> tuple[str, int]:
    if counts["fail"]:
        return "FAIL", 1
    if counts["runnable"] == 0:
        return "NO_RUNNABLE", 3
    return "PASS", 0


def build_report(args) -> dict:
    """Build the whole report; the CLI and the self-test share this path."""

    try:
        by_name, targets_doc = runner_mod.load_targets(
            getattr(args, "targets", None)
        )
    except runner_mod.TargetError as exc:
        return {
            "schema": SCHEMA,
            "command": "l3check",
            "claim": TOOL_CLAIM,
            "exp": EXP_RECORD,
            "engine": getattr(args, "engine", "pysh4"),
            "corpus": None,
            "card": _card_info(args),
            "targets": [],
            "counts": {"pass": 0, "fail": 0, "skip": 0, "blocked": 0,
                       "runnable": 0, "total": 0},
            "result": "FAIL",
            "exit": 1,
            "problems": [f"targets.json: {problem}" for problem in exc.problems],
            "note": "no target ran; a broken target table is not a pass",
        }

    problems = _evidence_problems(by_name)
    if problems:
        return {
            "schema": SCHEMA,
            "command": "l3check",
            "claim": TOOL_CLAIM,
            "exp": EXP_RECORD,
            "engine": getattr(args, "engine", "pysh4"),
            "corpus": None,
            "card": _card_info(args),
            "targets": [],
            "counts": {"pass": 0, "fail": 0, "skip": 0, "blocked": 0,
                       "runnable": 0, "total": 0},
            "result": "FAIL",
            "exit": 1,
            "problems": problems,
            "note": "the reader/claim table is out of step with targets.json",
        }

    # M9.12 card gate mode
    if getattr(args, "card", None) or getattr(args, "factory", None):
        if not (getattr(args, "card", None) and getattr(args, "factory", None)):
            raise UsageError("--card and --factory must be passed together")
        return build_card_report(Path(args.card), Path(args.factory),
                                 by_name=by_name,
                                 engine=getattr(args, "engine", "pysh4"))

    corpus_info, corpus_doc = _resolve_corpus(args)
    if corpus_info["problems"]:
        return {
            "schema": SCHEMA,
            "command": "l3check",
            "claim": TOOL_CLAIM,
            "exp": EXP_RECORD,
            "engine": getattr(args, "engine", "pysh4"),
            "corpus": corpus_info,
            "card": _card_info(args),
            "targets": [],
            "counts": {"pass": 0, "fail": 0, "skip": 0, "blocked": 0,
                       "runnable": 0, "total": 0},
            "result": "FAIL",
            "exit": 1,
            "problems": list(corpus_info["problems"]),
            "note": "the corpus is invalid, so no target was run",
        }

    selected = _select_targets(by_name, getattr(args, "target", None) or [])
    engine = getattr(args, "engine", "pysh4")
    root = Path(corpus_info["root"])
    rows = [_run_one(target, root, engine) for target in selected]
    counts = _counts(rows)
    result, exit_code = _result(counts)

    return {
        "schema": SCHEMA,
        "command": "l3check",
        "claim": TOOL_CLAIM,
        "exp": EXP_RECORD,
        "engine": engine,
        "corpus": corpus_info,
        "card": _card_info(args),
        "targets": rows,
        "counts": counts,
        "result": result,
        "exit": exit_code,
        "problems": [],
        "target_count": len(targets_doc.get("targets", [])),
        "note": (
            "a PASS on a synthetic target proves the runner/dispatcher path, "
            "not that the firmware accepts a card; BLOCKED and SKIP claim "
            "nothing and are counted, not failed"
        ),
    }


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def _detail(row: dict) -> str:
    if row["status"] == "PASS":
        text = f"{row['verdict']} (expected {row['expected']})"
        extra = []
        if row["steps"] is not None:
            extra.append(f"{row['steps']} steps")
        if row["engine"]:
            extra.append(row["engine"])
        if row["input"] and row["input"].get("path"):
            extra.append(row["input"]["path"])
        return text + (", " + ", ".join(extra) if extra else "")
    if row["status"] in ("SKIP", "BLOCKED"):
        return row["reason"] or "-"
    return "; ".join(row["problems"]) or row["reason"] or "no detail"


def _print_report(report: dict) -> None:
    print(f"l3check: L3 rung of the verification ladder (claim {TOOL_CLAIM})")
    print(f"exp      {EXP_RECORD}")
    if report["corpus"] is None:
        print("corpus   -")
    else:
        corpus = report["corpus"]
        print(
            f"corpus   {corpus['root']} ({corpus['source']}"
            f"; {corpus['entries']} entries"
            + (", kept" if corpus.get("kept") else "")
            + ")"
        )
    if report["card"]:
        print("card     not checked (--root/--image recorded; card mode is M9.12)")
    print(f"engine   {report['engine']}")

    for problem in report.get("problems", []):
        print(f"FAIL {problem}")
    if not report["targets"]:
        print(f"RESULT: {report['result']} (no target ran; exit {report['exit']})")
        return

    header = ("target", "reader", "entry", "claims", "RESULT")
    rows = [
        (
            row["name"],
            row["reader"],
            row["entry"] or "-",
            ",".join(row["claims"]) or "-",
            row["status"],
        )
        for row in report["targets"]
    ]
    widths = [len(item) for item in header]
    for row in rows:
        widths = [max(width, len(cell)) for width, cell in zip(widths, row)]
    print()
    print("  ".join(cell.ljust(width) for cell, width in zip(header, widths)))
    for row in rows:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)))

    details = [
        (row["name"], row["status"], _detail(row))
        for row in report["targets"]
        if row["status"] != "PASS"
    ]
    if details:
        print()
        for name, status, detail in details:
            print(f"  {status} {name}: {detail}")

    counts = report["counts"]
    print()
    print(
        f"counts   pass={counts['pass']} fail={counts['fail']} "
        f"skip={counts['skip']} blocked={counts['blocked']} "
        f"runnable={counts['runnable']}/{counts['total']}"
    )
    if report["result"] == "PASS":
        print(
            "RESULT: PASS (every runnable target passed; "
            f"{counts['blocked']} blocked, {counts['skip']} skipped)"
        )
    elif report["result"] == "NO_RUNNABLE":
        print(
            "RESULT: NO_RUNNABLE (exit 3; every target is blocked or skipped, "
            "nothing was claimed)"
        )
    else:
        print(f"RESULT: FAIL ({counts['fail']} target(s) failed; exit 1)")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="L3 rung of the verification ladder (M9.8) and card gate (M9.12)",
        epilog=(
            "Exit codes: 0 every runnable target passed, 1 a target failed or "
            "an input was invalid, 2 usage error, 3 nothing was runnable "
            "(or card mode found no runnable verdict)."
        ),
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--root", help="card tree (recorded only; use --card/--factory for M9.12)")
    source.add_argument("--image", help="card image (recorded only; use --card/--factory for M9.12)")
    source.add_argument("--card", help="M9.12: card image to check against --factory")
    parser.add_argument(
        "--factory",
        help="M9.12: factory/baseline card image (required with --card)",
    )
    parser.add_argument(
        "--corpus",
        help="corpus root built by tools/l3_harness/corpus.py (needs manifest.json)",
    )
    parser.add_argument(
        "--build-corpus",
        action="store_true",
        help="build a fresh corpus in a new temporary directory",
    )
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        metavar="NAME",
        help="run only this target (repeatable; default: every declared target)",
    )
    parser.add_argument(
        "--engine",
        default="pysh4",
        help="back end for every target: %s (default: pysh4)"
        % ", ".join(sorted(engine_mod.BACKENDS)),
    )
    parser.add_argument(
        "--targets",
        help="path to targets.json (default: tools/l3_harness/targets.json)",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="synthetic self-test: probe target, blocked target, FAIL/SKIP/card paths",
    )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()

    if args.engine not in engine_mod.BACKENDS:
        print(
            f"error: unknown engine {args.engine!r} "
            f"(known: {', '.join(sorted(engine_mod.BACKENDS))})",
            file=sys.stderr,
        )
        return 2

    try:
        report = build_report(args)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        if report.get("command") == "l3check --card":
            _print_card_report(report)
        else:
            _print_report(report)
    return report["exit"]


# --------------------------------------------------------------------------
# Self-test: synthetic target + blocked target + honest FAIL/SKIP paths
# --------------------------------------------------------------------------

CHECKS: list[tuple[str, callable]] = []
SKIPS: list[str] = []
_SELFTEST_CORPUS: Path | None = None
_SELFTEST_TMP: Path | None = None


def check(name):
    def register(func):
        CHECKS.append((name, func))
        return func

    return register


def _cli(argv) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        code = main(argv)
    return code, buffer.getvalue()


def _json_cli(argv) -> tuple[int, dict]:
    code, output = _cli([*argv, "--json"])
    try:
        return code, json.loads(output)
    except json.JSONDecodeError:
        raise AssertionError(f"not JSON (exit {code}): {output}") from None


def _corpus() -> Path:
    assert _SELFTEST_CORPUS is not None
    return _SELFTEST_CORPUS


@check("targets: targets.json and the reader/claim table agree")
def test_evidence_table():
    by_name, _doc = runner_mod.load_targets()
    problems = _evidence_problems(by_name)
    assert not problems, problems
    assert TOOL_CLAIM == "C-1700"
    assert TARGET_EVIDENCE["probe-zlib-cmf"]["reader"] == "synthetic"
    assert TARGET_EVIDENCE["mapcode_comparator"]["claims"] == ("C-520", "C-528")
    for row in TARGET_EVIDENCE.values():
        for claim in row["claims"]:
            assert _CLAIM_RE.match(claim), claim


@check("run: the synthetic target PASSes and the five unlocated readers are BLOCKED")
def test_full_run():
    code, report = _json_cli(["--corpus", str(_corpus())])
    assert code == 0, report
    assert report["result"] == "PASS", report
    assert report["claim"] == "C-1700"
    assert report["engine"] == "pysh4"
    assert report["corpus"]["source"] == "supplied", report["corpus"]
    assert report["corpus"]["entries"] == 108, report["corpus"]
    rows = {row["name"]: row for row in report["targets"]}
    probe = rows["probe-zlib-cmf"]
    assert probe["status"] == "PASS", probe
    assert probe["verdict"] == "ACCEPT" and probe["expected"] == "ACCEPT", probe
    assert probe["claims"] == ["C-1670", "C-1690"], probe
    assert probe["synthetic"] is True and probe["l3_claim"] is False, probe
    assert probe["input"]["manifest_sha256_match"] is True, probe["input"]
    assert probe["steps"] and probe["steps"] > 0, probe
    blocked = sorted(name for name, row in rows.items() if row["status"] == "BLOCKED")
    assert blocked == [
        "cmp_ind_reader",
        "drstr_parser",
        "hddinfo_compare",
        "mapcode_comparator",
        "tile_reader",
    ], blocked
    for name in blocked:
        row = rows[name]
        assert row["verdict"] is None and row["accepted"] is None, row
        assert row["l3_claim"] is False and row["reason"], row
        assert row["claims"] == list(TARGET_EVIDENCE[name]["claims"]), row
    assert report["counts"] == {
        "pass": 1, "fail": 0, "skip": 0, "blocked": 5,
        "runnable": 1, "total": 6,
    }, report["counts"]


@check("run: --target selects exactly one target (PASS)")
def test_single_target():
    code, report = _json_cli(
        ["--corpus", str(_corpus()), "--target", "probe-zlib-cmf"]
    )
    assert code == 0, report
    assert [row["name"] for row in report["targets"]] == ["probe-zlib-cmf"], report
    assert report["counts"]["total"] == 1, report["counts"]
    assert report["targets"][0]["status"] == "PASS", report["targets"]


@check("run: a blocked target is exit 3 and claims no verdict")
def test_blocked_target():
    code, report = _json_cli(
        ["--corpus", str(_corpus()), "--target", "hddinfo_compare"]
    )
    assert code == 3, report
    assert report["result"] == "NO_RUNNABLE", report
    row = report["targets"][0]
    assert row["status"] == "BLOCKED" and row["verdict"] is None, row
    assert row["l3_claim"] is False and row["reason"], row
    assert report["counts"]["runnable"] == 0, report["counts"]
    assert report["counts"]["blocked"] == 1, report["counts"]


@check("run: a blocked target needs no corpus input (nothing is invented)")
def test_blocked_needs_no_input():
    missing = Path(_SELFTEST_TMP) / "no-such-corpus"
    by_name, _doc = runner_mod.load_targets()
    row = _run_one(by_name["cmp_ind_reader"], missing, "pysh4")
    assert row["status"] == "BLOCKED", row
    assert row["verdict"] is None and row["input"] is None, row
    assert row["l3_claim"] is False, row


@check("run: a tampered corpus makes the probe FAIL (never a pass)")
def test_tampered_corpus():
    target = Path(_SELFTEST_TMP) / "tampered"
    shutil.copytree(_corpus(), target)
    relative = "cmp/factory/ADDRE001.DAT.cmp"
    victim = target / relative
    data = bytearray(victim.read_bytes())
    data[0] = 0x00                      # no longer the zlib CMF 0x78
    victim.write_bytes(bytes(data))

    manifest_path = target / "manifest.json"
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    import hashlib

    digest = hashlib.sha256(bytes(data)).hexdigest()
    for entry in doc["corpus"]:
        if entry["path"] == relative:
            entry["sha256"] = digest
            entry["size"] = len(data)
    manifest_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    code, report = _json_cli(
        ["--corpus", str(target), "--target", "probe-zlib-cmf"]
    )
    assert code == 1, report
    assert report["result"] == "FAIL", report
    row = report["targets"][0]
    assert row["status"] == "FAIL", row
    assert row["verdict"] == "REJECT", row
    assert any("expects ACCEPT" in problem for problem in row["problems"]), row
    assert row["input"]["manifest_sha256_match"] is True, row["input"]


@check("run: a corpus without manifest.json is invalid and runs nothing")
def test_missing_manifest():
    empty = Path(_SELFTEST_TMP) / "empty-corpus"
    empty.mkdir()
    code, report = _json_cli(["--corpus", str(empty)])
    assert code == 1, report
    assert report["result"] == "FAIL" and report["targets"] == [], report
    assert any("manifest.json" in problem for problem in report["problems"]), report


@check("run: an absent back end is SKIP, never PASS")
def test_backend_skip():
    available = next(
        item for item in engine_mod.probe_all(["ghidra"])
    )
    code, report = _json_cli(
        ["--corpus", str(_corpus()), "--target", "probe-zlib-cmf",
         "--engine", "ghidra"]
    )
    row = report["targets"][0]
    if not available.available:
        assert available.code == "MISSING_GHIDRA", available.as_dict()
        assert code == 3, report
        assert row["status"] == "SKIP" and row["verdict"] is None, row
        assert row["l3_claim"] is False, row
        assert "MISSING_GHIDRA" in row["reason"], row
        SKIPS.append(f"ghidra: {available.code} - {available.detail}")
        return
    assert row["status"] != "SKIP", row


@check("run: --build-corpus builds into a temporary directory")
def test_build_corpus():
    code, report = _json_cli(
        ["--build-corpus", "--target", "probe-zlib-cmf"]
    )
    try:
        assert code == 0, report
        corpus = report["corpus"]
        assert corpus["source"] == "built" and corpus["kept"] is True, corpus
        assert corpus["entries"] == 108, corpus
        assert Path(corpus["root"]).is_dir(), corpus
        assert (Path(corpus["root"]) / "manifest.json").is_file(), corpus
        assert report["targets"][0]["status"] == "PASS", report["targets"]
    finally:
        root = (report.get("corpus") or {}).get("root")
        if root:
            shutil.rmtree(root, ignore_errors=True)


@check("cli: an unknown --target is a usage error (exit 2)")
def test_unknown_target():
    code, output = _cli(
        ["--corpus", str(_corpus()), "--target", "no-such-target"]
    )
    assert code == 2, output
    assert "unknown target" in output, output


@check("cli: --corpus together with --build-corpus is a usage error")
def test_conflicting_corpus_flags():
    code, output = _cli(["--corpus", str(_corpus()), "--build-corpus"])
    assert code == 2, output
    assert "not both" in output, output


@check("run: two runs give the same verdicts")
def test_determinism():
    first = _json_cli(["--corpus", str(_corpus())])[1]
    second = _json_cli(["--corpus", str(_corpus())])[1]
    assert first == second, "two runs differ"


@check("card: --card without --factory is a usage error")
def test_card_requires_factory():
    code, output = _cli(["--card", "/no/such.img"])
    assert code == 2, output
    assert "--card and --factory" in output or "factory" in output.lower(), output


@check("card: missing images produce honest problems (no fake pass)")
def test_card_missing_images():
    code, report = _json_cli(["--card", "/no/such-card.img",
                              "--factory", "/no/such-factory.img"])
    assert code in (1, 3), report
    assert report["command"] == "l3check --card", report
    assert report["claim"] == CARD_CLAIM, report
    probs = report.get("problems") or []
    assert any("not found" in p for p in probs), report
    assert report["result"] != "PASS", report


@check("card: identical small files short-circuit to no diffs (no 7z)")
def test_card_identical_shortcircuit():
    p = Path(_SELFTEST_TMP) / "tiny.img"
    p.write_bytes(b"\x00" * 1024)
    code, report = _json_cli(["--card", str(p), "--factory", str(p)])
    assert code == 3, report  # no diffs / nothing runnable = not a pass
    assert report["diff"]["identical_images"] is True, report["diff"]
    assert report["diff"]["differing"] == [], report["diff"]
    assert report["result"] in ("NO_DIFFS", "NOT_YET_AVAILABLE"), report
    assert report["counts"]["fail"] == 0, report["counts"]


@check("card: target mapping reports POI reader as not-yet-available (M9.10)")
def test_card_poi_not_yet_available():
    by_name, _ = runner_mod.load_targets()
    # Simulate report structure for a POINT diff by calling the label logic.
    ct = next(c for c in _CARD_TARGETS if c["name"] == "poi_record_decode")
    assert ct["applies"]("REFER001/POINT010.DAT.cmp"), ct
    assert not ct["applies"]("REFER001/ADDRE001.DAT.cmp"), ct
    assert "not yet available" in ct["unavailable_note"].lower(), ct["unavailable_note"]
    assert "M9.10" in ct["unavailable_note"], ct["unavailable_note"]


@check("card: cmp pair normalization")
def test_card_cmp_pair():
    assert _norm_cmp_pair("REFER001/POINT010.DAT.cmp") == (
        "REFER001/POINT010.DAT.cmp", "REFER001/POINT010.DAT.ind")
    assert _norm_cmp_pair("REFER001/POINT010.DAT.ind") == (
        "REFER001/POINT010.DAT.cmp", "REFER001/POINT010.DAT.ind")
    assert _norm_cmp_pair("DRSTR001.DAT") is None


def run_selftest() -> int:
    global _SELFTEST_CORPUS, _SELFTEST_TMP

    failures = 0
    with tempfile.TemporaryDirectory(prefix="l3check-selftest-") as tmp:
        _SELFTEST_TMP = Path(tmp)
        _SELFTEST_CORPUS = Path(tmp) / "corpus"
        try:
            corpus_mod.build_corpus(_SELFTEST_CORPUS)
        except (corpus_mod.CorpusError, manifest_mod.ManifestError, OSError) as exc:
            print(f"FAIL corpus fixture: {exc}")
            print("\nl3check selftest: FAILED (0/1 checks)")
            return 1

        for name, func in CHECKS:
            try:
                func()
            except Exception as exc:  # noqa: BLE001 - report, do not abort
                failures += 1
                print(f"FAIL {name}: {exc}")
                if "--verbose" in sys.argv[1:]:
                    import traceback

                    traceback.print_exc()
            else:
                print(f"ok   {name}")
        for skip in SKIPS:
            print(f"skip {skip}")

    total = len(CHECKS)
    print()
    if failures:
        print(f"l3check selftest: FAILED ({failures}/{total} checks)")
        return 1
    print(
        f"l3check selftest: OK ({total} checks"
        + (f", {len(SKIPS)} skipped" if SKIPS else "")
        + ")"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
