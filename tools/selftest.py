#!/usr/bin/env python3
"""Registry runner for the repository self-tests.

The runner has two kinds of suites:

* **builtin** — synthetic tests for the primitive parsers (``cmpind``,
  ``drstr``, ``mesh_grid``, ``cardcheck`` L1 helpers).  They need no vendor
  data and never touch the network.
* **tool** — every ``tools/*.py`` that advertises ``--selftest`` is executed
  as a subprocess with a timeout.  A tool without the flag is reported as
  ``SKIP (no --selftest)``; a tool that disappears between discovery and the
  run is a skip, not a failure.  Discovery is re-run on every invocation, so
  tools added by other work are picked up automatically.

Usage::

    python3 tools/selftest.py                 # everything
    python3 tools/selftest.py --list          # names only, run nothing
    python3 tools/selftest.py --only cmpind   # one suite (repeatable)
    python3 tools/selftest.py --json          # machine-readable report
    python3 tools/selftest.py --verbose       # show captured output
    python3 tools/selftest.py --include-dir /tmp/mytools

Exit codes: ``0`` all selected suites passed (skips are not failures),
``1`` at least one suite failed, ``2`` usage error.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import struct
import subprocess
import sys
import tempfile
import time
import traceback
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
SELF_PATH = Path(__file__).resolve()

SELFTEST_FLAG = "--selftest"
TOOL_TIMEOUT = 60.0
PROBE_TIMEOUT = 10.0
OUTPUT_LIMIT = 8000

SKIP_NO_FLAG = "no --selftest"
SKIP_MISSING = "missing tool"

# ``sys.path`` is needed by the builtin suites, which import sibling modules.
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import cardcheck  # noqa: E402
import cmpind  # noqa: E402
import drstr  # noqa: E402
import mesh_grid  # noqa: E402


# --------------------------------------------------------------------------
# Builtin synthetic suites (synthetic data only, no vendor files)
# --------------------------------------------------------------------------


def test_cmpind() -> None:
    chunk0 = b"A" * 0x10000
    chunk1 = b"B" * 1000
    stream0 = zlib.compress(chunk0)
    stream1 = zlib.compress(chunk1)
    payload = stream0 + stream1

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cmp_path = tmp_path / "TEST.DAT.cmp"
        ind_path = tmp_path / "TEST.DAT.ind"
        cmp_path.write_bytes(payload)
        ind_path.write_bytes(
            struct.pack("<IIII", len(chunk0) + len(chunk1), len(payload), 2, 0x10000)
            + struct.pack("<II", 0, len(stream0))
        )

        blob, info = cmpind.decode(cmp_path, ind_path)
        assert blob == chunk0 + chunk1, "cmpind round-trip mismatch"
        assert info["chunk_count"] == 2
        assert len(info["offsets"]) == 2

        usize, csize, count, chunk_size, offsets = cmpind.read_index(ind_path)
        assert (usize, csize, count, chunk_size) == (
            len(chunk0) + len(chunk1),
            len(payload),
            2,
            0x10000,
        )
        assert offsets == (0, len(stream0))

        out = tmp_path / "TEST.DAT"
        cmpind.main(["extract", str(cmp_path), "-o", str(out)])
        assert out.read_bytes() == chunk0 + chunk1

        cmpind.main(["verify", str(tmp_path)])


def test_drstr() -> None:
    # Node 0 is the root "/". The table starts at 0x00; there is no header.
    listing_offset = 40
    node = (
        b"/\0\0\0\0\0\0\0"
        + b"\0" * 12
        + struct.pack("<HH", 1, 1)  # next=1, parent_plus_one=1 (root)
        + struct.pack("<I", 1)      # entry_count
        + struct.pack("<II", 0, 0)  # reserved
        + struct.pack("<I", listing_offset)
    )
    assert len(node) == 40

    entry = (
        b"FILE.TXT\0\0\0\0\0"       # 13-byte name field
        + b"\0" * 9
        + struct.pack("<H", 0)      # type 0 = file
        + struct.pack("<I", 0)      # reserved
        + struct.pack("<I", 123)    # logical size
    )
    assert len(entry) == 32

    tree = drstr.parse(node + entry)
    assert tree["node_count"] == 1
    assert tree["table_end"] == 40
    assert tree["nodes"][0]["name"] == "/"
    assert tree["nodes"][0]["parent"] == 0
    assert tree["nodes"][0]["entry_count"] == 1
    assert tree["nodes"][0]["entries"][0]["name"] == "FILE.TXT"
    assert tree["nodes"][0]["entries"][0]["value"] == 123


def test_mesh_grid() -> None:
    lat_min, lat_max, lon_min, lon_max = mesh_grid.tile_box("B48R058R.DAT")
    assert abs(lat_min - 48.0) < 1e-9
    assert abs(lat_max - 53.3333333333) < 1e-6
    assert abs(lon_min - 12.0) < 1e-9
    assert abs(lon_max - 20.0) < 1e-9


def _lfn_entry(seq: int, text: str) -> bytes:
    entry = bytearray(32)
    entry[0] = seq
    entry[11] = 0x0F
    raw = text.encode("utf-16le")
    if len(raw) < 26:
        raw += b"\x00\x00"
    raw = raw[:26].ljust(26, b"\xff")
    entry[1:11] = raw[:10]
    entry[14:26] = raw[10:22]
    entry[28:32] = raw[22:26]
    return bytes(entry)


def _short_entry(name: str, attr: int = 0x20, cluster: int = 0, size: int = 0) -> bytes:
    entry = bytearray(32)
    encoded = name.encode("ascii")
    entry[0:11] = encoded.ljust(11, b" ")[:11]
    entry[11] = attr
    struct.pack_into("<H", entry, 20, cluster >> 16)
    struct.pack_into("<H", entry, 26, cluster & 0xFFFF)
    struct.pack_into("<I", entry, 28, size)
    return bytes(entry)


def test_cardcheck_helpers() -> None:
    # Level table: one section, one row.
    table = struct.pack(">HBBBBH", 1, 1, 1, 2, 0x91, 123)
    groups = cardcheck.parse_level_table(table, 0)
    assert groups == [
        {"section": 1, "rows": [{"level": 2, "type": 0x91, "count": 123}]}
    ]

    # Common header fields.
    header = bytearray(0x180)
    for off, text in (
        (0x00, "CLARION"),
        (0x40, "HITACHI"),
        (0x80, "CLA-NAVI05-01"),
        (0xA0, "FORMAT VERSION X08-02-00"),
        (0xE0, "DATA VERSION 11/06/27/01"),
    ):
        raw = text.encode("utf-16-be")
        header[off : off + len(raw)] = raw
    fields = cardcheck.header_fields(bytes(header))
    assert fields["clarion"] == "CLARION"
    assert fields["model"] == "CLA-NAVI05-01"
    assert fields["format"] == "FORMAT VERSION X08-02-00"

    # LFN + short entry.  The card's WinCE FAT checksums do not match the
    # standard algorithm, so the parser deliberately trusts a contiguous
    # sequence instead.
    directory = _lfn_entry(0x41, "TESTFILE.TXT") + _short_entry(
        "TESTFI~1TXT", size=42
    )
    entries = cardcheck.parse_dir_entries(directory)
    assert len(entries) == 1
    assert entries[0]["name"] == "TESTFILE.TXT"
    assert entries[0]["size"] == 42

    # .cmp/.ind decode helper.
    chunk0 = b"A" * 0x10000
    chunk1 = b"B" * 100
    stream0 = zlib.compress(chunk0)
    stream1 = zlib.compress(chunk1)
    packed = stream0 + stream1
    ind = (
        struct.pack("<IIII", len(chunk0) + len(chunk1), len(packed), 2, 0x10000)
        + struct.pack("<II", 0, len(stream0))
    )
    blob, info = cardcheck.decode_cmp(packed, ind)
    assert blob == chunk0 + chunk1
    assert info["chunks"] == 2

    # Logical listing: .cmp/.ind maps to the .ind uncompressed size; DRSTR
    # itself and .ind files are not logical entries.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "A.DAT.cmp").write_bytes(b"x")
        (root / "A.DAT.ind").write_bytes(struct.pack("<I", 100))
        (root / "B.DAT").write_bytes(b"12345")
        (root / "DRSTR001.DAT").write_bytes(b"x")
        source = cardcheck.RootSource(root)
        listing = cardcheck.logical_listing(source, "")
        assert set(listing) == {"A.DAT", "B.DAT"}
        assert listing["A.DAT"].size == 100
        assert listing["B.DAT"].size == 5
        assert cardcheck.tree_size(source, "") == 105


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------


@dataclass
class Suite:
    id: str
    kind: str  # "builtin" | "tool"
    description: str
    func: Callable[[], None] | None = None
    path: Path | None = None
    has_selftest: bool = False


def builtin_suites() -> list[Suite]:
    """The synthetic suites, in their historical execution order."""
    return [
        Suite(
            "cmpind",
            "builtin",
            "cmpind decode, .ind index, extract and verify",
            func=test_cmpind,
        ),
        Suite(
            "drstr",
            "builtin",
            "drstr node/entry parse",
            func=test_drstr,
        ),
        Suite(
            "mesh_grid",
            "builtin",
            "mesh_grid tile bbox mapping",
            func=test_mesh_grid,
        ),
        Suite(
            "cardcheck",
            "builtin",
            "cardcheck L1 helpers: level table, header, LFN, .cmp, listing",
            func=test_cardcheck_helpers,
        ),
    ]


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _source_mentions_flag(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return SELFTEST_FLAG in text


def exposes_selftest(path: Path) -> bool:
    """Whether *path* really accepts ``--selftest``.

    A source scan avoids spawning a process for every tool.  When the flag is
    mentioned, ``--help`` confirms it is declared in the argument parser, so a
    documentation mention cannot produce a spurious failure.  If the probe
    cannot run at all, the source scan decides.  Discovery is read-only either
    way.
    """
    if not _source_mentions_flag(path):
        return False
    try:
        proc = subprocess.run(
            [sys.executable, str(path), "--help"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    help_text = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 or not help_text.strip():
        # The probe could not produce usable help; trust the source scan.
        return True
    return SELFTEST_FLAG in help_text


def discover_tools(directories: list[Path]) -> list[Suite]:
    """Map ``*.py`` files to tool suites, sorted by stem for stable output.

    Later directories override earlier ones with the same stem, so an
    explicit ``--include-dir`` can shadow a repository tool.  Private modules
    and this runner are never discovered.
    """
    found: dict[str, Path] = {}
    for directory in directories:
        for path in sorted(directory.glob("*.py")):
            if not path.is_file() or path.name.startswith("_"):
                continue
            try:
                if path.resolve() == SELF_PATH:
                    continue
            except OSError:
                continue
            found[path.stem] = path

    suites: list[Suite] = []
    for stem in sorted(found):
        path = found[stem]
        has = exposes_selftest(path)
        rel = _display_path(path)
        description = f"{rel} {SELFTEST_FLAG}" if has else f"{rel} (no selftest)"
        suites.append(
            Suite(f"tool:{stem}", "tool", description, path=path, has_selftest=has)
        )
    return suites


def build_registry(include_dirs: list[Path]) -> list[Suite]:
    """Builtin suites first (fixed order), then discovered tools by name."""
    directories = [TOOLS_DIR]
    seen = {TOOLS_DIR}
    for directory in include_dirs:
        resolved = directory.expanduser().resolve()
        if resolved not in seen:
            directories.append(resolved)
            seen.add(resolved)
    return builtin_suites() + discover_tools(directories)


# --------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------


@dataclass
class Result:
    id: str
    kind: str
    description: str
    status: str  # PASS | FAIL | SKIP
    seconds: float = 0.0
    detail: str = ""
    output: str = ""
    path: str = ""


def _clip(text: str) -> str:
    if len(text) <= OUTPUT_LIMIT:
        return text
    return "...(truncated)...\n" + text[-OUTPUT_LIMIT:]


def run_builtin(suite: Suite) -> Result:
    """Run a synthetic suite in-process, capturing its chatter."""
    assert suite.func is not None
    stdout, stderr = io.StringIO(), io.StringIO()
    result = Result(suite.id, suite.kind, suite.description, "PASS")
    started = time.perf_counter()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            suite.func()
    except Exception as exc:  # AssertionError included
        result.status = "FAIL"
        result.detail = f"{type(exc).__name__}: {exc}"
        result.output = traceback.format_exc()
    finally:
        result.seconds = time.perf_counter() - started
    if result.status == "PASS":
        result.output = stdout.getvalue() + stderr.getvalue()
    else:
        result.output = result.output + stdout.getvalue() + stderr.getvalue()
    result.output = _clip(result.output)
    return result


def run_tool(suite: Suite, timeout: float = TOOL_TIMEOUT) -> Result:
    """Run ``<tool> --selftest`` as a subprocess."""
    assert suite.path is not None
    result = Result(
        suite.id, suite.kind, suite.description, "SKIP", path=str(suite.path)
    )
    if not suite.has_selftest:
        result.detail = SKIP_NO_FLAG
        return result
    if not suite.path.exists():
        result.detail = SKIP_MISSING
        return result

    started = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, str(suite.path), SELFTEST_FLAG],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        result.status = "FAIL"
        result.detail = f"timeout after {timeout:g}s"
        result.output = _clip(_decode_timeout(exc.stdout) + _decode_timeout(exc.stderr))
        result.seconds = time.perf_counter() - started
        return result
    except FileNotFoundError as exc:
        # The tool vanished mid-run; that is not a test failure.
        result.detail = f"{SKIP_MISSING} ({exc})"
        result.seconds = time.perf_counter() - started
        return result
    except OSError as exc:
        result.status = "FAIL"
        result.detail = f"cannot run: {exc}"
        result.seconds = time.perf_counter() - started
        return result

    result.seconds = time.perf_counter() - started
    result.output = _clip((proc.stdout or "") + (proc.stderr or ""))
    if proc.returncode == 0:
        result.status = "PASS"
    else:
        result.status = "FAIL"
        result.detail = f"exit {proc.returncode}"
    return result


def _decode_timeout(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def run_suite(suite: Suite, timeout: float = TOOL_TIMEOUT) -> Result:
    if suite.kind == "builtin":
        return run_builtin(suite)
    return run_tool(suite, timeout=timeout)


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def _status_detail(result: Result) -> str:
    if result.status == "PASS":
        return f"{result.seconds:.2f}s"
    if result.status == "FAIL":
        return f"{result.detail} ({result.seconds:.2f}s)"
    return result.detail


def print_results(results: list[Result], verbose: bool) -> None:
    width = max((len(r.id) for r in results), default=0)
    for result in results:
        print(f"{result.id:<{width}}  {result.status:<4}  {_status_detail(result)}")
        if verbose or result.status == "FAIL":
            if verbose and result.path:
                print(f"  path: {result.path}")
            for out_line in (result.output or "").rstrip().splitlines():
                print(f"  | {out_line}")


def print_summary(results: list[Result], elapsed: float) -> None:
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    skipped = sum(1 for r in results if r.status == "SKIP")
    print()
    print(
        f"passed={passed} failed={failed} skipped={skipped} "
        f"total={len(results)} time={elapsed:.2f}s"
    )


def json_report(results: list[Result], elapsed: float) -> dict:
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    skipped = sum(1 for r in results if r.status == "SKIP")
    return {
        "ok": failed == 0,
        "elapsed_seconds": round(elapsed, 3),
        "counts": {
            "pass": passed,
            "fail": failed,
            "skip": skipped,
            "total": len(results),
        },
        "suites": [
            {
                "id": r.id,
                "kind": r.kind,
                "status": r.status,
                "seconds": round(r.seconds, 4),
                "detail": r.detail,
                "path": r.path or None,
                "description": r.description,
                "output": r.output or None,
            }
            for r in results
        ],
    }


def print_list(suites: list[Suite], as_json: bool) -> None:
    if as_json:
        print(
            json.dumps(
                [
                    {
                        "id": s.id,
                        "kind": s.kind,
                        "path": str(s.path) if s.path else None,
                        "selftest": s.has_selftest if s.kind == "tool" else True,
                        "description": s.description,
                    }
                    for s in suites
                ],
                indent=2,
            )
        )
        return
    width = max((len(s.id) for s in suites), default=0)
    for suite in suites:
        if suite.kind == "builtin":
            note = "builtin"
        else:
            note = SELFTEST_FLAG if suite.has_selftest else SKIP_NO_FLAG
        print(f"{suite.id:<{width}}  {note:<14}  {suite.description}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Exit codes: 0 pass, 1 failure, 2 usage error.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list suite names and exit without running anything",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="NAME",
        help="run only the named suite(s); repeatable, accepts comma lists",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="show captured output of every suite",
    )
    parser.add_argument(
        "--include-dir",
        action="append",
        default=[],
        metavar="DIR",
        help="also discover tools/*.py in DIR (repeatable)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=TOOL_TIMEOUT,
        metavar="SECONDS",
        help=f"per-tool subprocess timeout (default {TOOL_TIMEOUT:g})",
    )
    return parser


def _select(suites: list[Suite], only: list[str], parser: argparse.ArgumentParser):
    tokens = []
    for value in only:
        tokens.extend(part.strip() for part in value.split(",") if part.strip())
    if not tokens:
        return suites

    by_id = {suite.id: suite for suite in suites}
    selected: set[str] = set()
    for token in tokens:
        match = by_id.get(token)
        if match is None:
            # A bare tool name may omit the "tool:" namespace.
            match = by_id.get(f"tool:{token}")
        if match is None:
            candidates = [s for s in suites if s.id.split(":", 1)[-1] == token]
            if len(candidates) == 1:
                match = candidates[0]
        if match is None:
            parser.error(
                f"unknown suite {token!r}; use --list to see available names"
            )
        selected.add(match.id)
    return [suite for suite in suites if suite.id in selected]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    include_dirs = [Path(value) for value in args.include_dir]
    missing = [
        d for d in include_dirs if not d.expanduser().is_dir()
    ]
    if missing:
        parser.error(f"not a directory: {missing[0]}")

    suites = build_registry(include_dirs)

    if args.list:
        print_list(suites, args.json)
        return 0

    selected = _select(suites, args.only, parser)

    started = time.perf_counter()
    results = [run_suite(suite, timeout=args.timeout) for suite in selected]
    elapsed = time.perf_counter() - started

    failed = sum(1 for r in results if r.status == "FAIL")
    if args.json:
        print(json.dumps(json_report(results, elapsed), indent=2))
    else:
        print_results(results, args.verbose)
        print_summary(results, elapsed)
        print("selftest: FAILED" if failed else "selftest: OK")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
