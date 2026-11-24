#!/usr/bin/env python3
"""The four rule-17 map numbers as one command (H109).

Rule 17 (TODO.md) asks every PO pass to report four numbers before anything
else: reader-coverage rows with a located reader, rows with a running (non-
BLOCKED) L3 target, bytes of a factory tile explained by the format docs, and
the highest card-ladder step that passes its own gate.

Before H109 those were three ``python3 -c`` one-liners, a 10-line shell loop
and a hard-coded host path.  This tool prints the same four numbers from one
command, with a stable key each, and says ``NOT RUN`` when an input is absent
instead of crashing.

It redefines **no** metric.  Each signal delegates to the code that already
owns the definition:

* ``readers``    -> ``progress_report.parse_reader_coverage`` (the matrix
                    parser in ``tools/progress_report.py``).
* ``l3_rows``    -> the exact ``grep | awk`` row filter from the TODO
                    Priorities block (column 9 of a numbered matrix row bearing
                    ``PASS``/``REJECT``), run as a subprocess.
* ``tile_bytes`` -> ``clarion_tile.read_tile`` (``tools/ze0-viewer/tools_ze0``)
                    plus the union-of-container-spans arithmetic from the
                    Priorities snippet.
* ``card_step``  -> a fresh report's validated ``step`` (P0..P4), read only
                    when ``cardcheck_ok``/``l2check_ok`` and both gate rc values
                    agree, checked against ``card_ladder.py steps --check``.
                    A report without a valid step is ``NOT RUN`` / ``none``,
                    never a promoted number (M9.76).

Usage::

    python3 tools/map_signals.py                      # all four signals
    python3 tools/map_signals.py readers l3_rows      # selected signals
    python3 tools/map_signals.py --json               # JSON for the logs
    python3 tools/map_signals.py --factory-root DIR --report PATH --matrix PATH
    python3 tools/map_signals.py --selftest           # synthetic, no vendor data

Defaults for the host paths (overridable by flag, then by environment):

    --factory-root  $OSM2LEAF_FACTORY_ROOT  ~/projekty/leafre-work/m5.4/card-factory
    --report        $OSM2LEAF_M5_34_REPORT  ~/projekty/leafre-work/m5.34/report.json
    --matrix                                docs/research/reader-coverage.md

Exit status is 0 whenever the tool could evaluate the signals it was asked
for; a missing input is reported as ``NOT RUN`` (a named, quotable state), not
an error.  A broken input (a matrix that parses to zero readers, a report that
is not JSON) also prints ``NOT RUN`` with the reason rather than a guessed
number.

JSON keys (the portable contract the Priorities block cites):

    readers   -> {"located", "partial", "unlocated"}
    l3_rows   -> {"l3-running"}
    tile_bytes-> {"tiles": {name: percent}, "status"}
    card_step -> {"cardcheck_ok", "l2check_ok", "cardcheck_rc", "l2check_rc",
                  "card_sha256", "step", "status", "disagree", "reason"}
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
ZE0 = TOOLS / "ze0-viewer" / "tools_ze0"

DEFAULT_MATRIX = ROOT / "docs" / "research" / "reader-coverage.md"
DEFAULT_FACTORY_ROOT = Path.home() / "projekty" / "leafre-work" / "m5.4" / "card-factory"
DEFAULT_REPORT = Path.home() / "projekty" / "leafre-work" / "m5.34" / "report.json"

TILE_NAMES = ("B28R070R", "B30R048R", "B48R058R")
SIGNALS = ("readers", "l3_rows", "tile_bytes", "card_step")
CARD_STEPS = ("P0", "P1", "P2", "P3", "P4")
SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")


def _not_run(reason: str) -> dict:
    return {"status": "NOT RUN", "reason": reason}


# --------------------------------------------------------------------------
# readers: progress_report.parse_reader_coverage owns the row semantics
# --------------------------------------------------------------------------


def signal_readers(matrix: Path) -> dict:
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    try:
        from progress_report import parse_reader_coverage
    except Exception as exc:  # pragma: no cover - import guard
        return _not_run(f"cannot import progress_report: {exc}")
    if not matrix.is_file():
        return _not_run(f"matrix not found: {matrix}")
    doc, problems = parse_reader_coverage(matrix)
    summary = (doc.get("summary") or {}).get("firmware_reader")
    if not summary or not doc.get("row_count"):
        detail = problems[0].detail if problems else "no data rows"
        return _not_run(f"matrix parsed no readers: {detail}")
    return {
        "status": "LOCAL",
        "located": summary["located"],
        "partial": summary["partial"],
        "unlocated": summary["unlocated"],
        # The Priorities reader out is "located N / partial N / unlocated N";
        # keep the remaining buckets for completeness, not as the headline.
        "not_needed": summary.get("not_needed"),
        "other": summary.get("other"),
        "rows": doc.get("row_count"),
        "problems": [p.detail for p in problems],
    }


# --------------------------------------------------------------------------
# l3_rows: the verbatim Priorities awk over a numbered matrix row
# --------------------------------------------------------------------------

L3_AWK = ('{gsub(/ /,"",$9); if ($9 ~ /PASS|REJECT/) c++} END{print "l3-running", c+0}')


def signal_l3_rows(matrix: Path) -> dict:
    if not matrix.is_file():
        return _not_run(f"matrix not found: {matrix}")
    # Same two-stage pipeline as the Priorities block: numbered rows from grep,
    # field 9 tested for PASS/REJECT by awk.  Run as a shell pipeline so the
    # definition is byte-for-byte the TODO command, not a reimplementation.
    cmd = (
        "grep -E '^\\| [0-9]+ \\|' \"$1\" | awk -F'|' '" + L3_AWK + "'"
    )
    proc = subprocess.run(["bash", "-c", cmd, "bash", str(matrix)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        return _not_run(f"row filter failed rc={proc.returncode}: {proc.stderr.strip()}")
    line = proc.stdout.strip()
    if not line.startswith("l3-running"):
        return _not_run(f"row filter printed no count: {line!r}")
    try:
        count = int(line.split()[-1])
    except ValueError:
        return _not_run(f"row filter count unparsable: {line!r}")
    return {"status": "LOCAL", "l3-running": count, "raw": line}


# --------------------------------------------------------------------------
# tile_bytes: clarion_tile.read_tile + the union-of-spans arithmetic
# --------------------------------------------------------------------------


def _import_clarion_tile():
    if str(ZE0) not in sys.path:
        sys.path.insert(0, str(ZE0))
    import clarion_tile as ct  # noqa: E402
    return ct


def count_table_spans(data: bytes, tile) -> list[tuple[int, int]]:
    """Section header-table spans ``[taddr, taddr + 2*u16@taddr)`` (M4.99).

    ``clarion_tile.read_tile`` reads ``u16@taddr`` as the table's word count
    (``clarion_tile.py:39-41``); the span it describes is a real, count-word
    bounded block, not padding.  ``tile_explained_percent`` previously counted
    only directory+slot spans, so these bytes were the whole M4.96 class-d
    residual.  The count word is load-bearing: overwriting it makes
    ``read_tile`` raise, which is the falsifier for this classification.
    """
    import struct
    spans: list[tuple[int, int]] = []
    for section in tile["sections"]:
        taddr = section["taddr"]
        count = struct.unpack_from(">H", data, taddr)[0]
        spans.append((taddr, taddr + 2 * count))
    return spans


def tile_explained_percent(data: bytes, ct, detail: bool = False):
    """Percent of nonzero bytes past 0x1000 that fall inside explained spans.

    The span union has two kinds (M4.99):

    * directory ``(off, end)`` and slot ``(block_off, block_end)`` spans — the
      original Priorities-snippet arithmetic from M4.86;
    * section header-table spans ``[taddr, taddr + 2*u16@taddr)`` (M4.99) — a
      count-word bounded block read by ``clarion_tile.read_tile``.  These were
      the whole M4.96 class-d residual; M4.96's follow-up nominated counting
      them so the headline stops excluding a parsed block.

    Intervals are merged, then nonzero bytes inside them are counted over the
    total nonzero bytes in ``d[0x1000:]``.  With ``detail=True`` also return
    the pre-table percent and the last delta, so the number's move is quotable.
    """
    tile = ct.read_tile(data)
    intervals = []
    for section in tile["sections"]:
        for level in section["levels"]:
            for directory in level["dirs"]:
                intervals.append((directory["off"], directory["end"]))
                intervals += [(slot["block_off"], slot["block_end"])
                              for slot in directory["slots"].values()]
    intervals = sorted(intervals)

    def _merged_pct(spans):
        merged = []
        for start, end in sorted(intervals + spans):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        tail = data[0x1000:]
        nonzero_all = sum(1 for byte in tail if byte)
        nonzero_in = sum(sum(1 for byte in data[start:end] if byte)
                         for start, end in merged)
        if not nonzero_all:
            return 0.0, 0, nonzero_all
        return 100.0 * nonzero_in / nonzero_all, nonzero_in, nonzero_all

    old_pct, old_in, total = _merged_pct([])
    tabs = count_table_spans(data, tile)
    new_pct, new_in, total = _merged_pct(tabs)
    if detail:
        return {
            "percent": new_pct,
            "baseline_percent": old_pct,
            "delta_bytes": new_in - old_in,
            "nonzero_tail": total,
            "table_spans": tabs,
        }
    return new_pct


def signal_tile_bytes(factory_root: Path, names: tuple[str, ...] = TILE_NAMES) -> dict:
    mapal = factory_root / "MAPAL001"
    present = [n for n in names if (mapal / f"{n}.DAT").is_file()]
    if not present:
        return _not_run("no factory tiles")
    try:
        ct = _import_clarion_tile()
    except Exception as exc:  # pragma: no cover - import guard
        return _not_run(f"cannot import clarion_tile: {exc}")
    tiles: dict[str, float] = {}
    for name in present:
        data = (mapal / f"{name}.DAT").read_bytes()
        try:
            tiles[name] = round(tile_explained_percent(data, ct), 2)
        except Exception as exc:
            return _not_run(f"{name}: read_tile failed: {exc}")
    return {"status": "LOCAL", "tiles": tiles, "factory_root": str(factory_root)}


# --------------------------------------------------------------------------
# card_step: a validated ladder step from a fresh gate report (M9.76)
# --------------------------------------------------------------------------


def ladder_steps() -> dict:
    """Return the step groups from ``card_ladder.py steps --check``.

    The summary rc is *not* the oracle: today the board has unrelated missing
    and bad Step tags, so ``--check`` exits 1 while the step grouping is still
    valid.  We parse the ``P0 (N): ...`` lines and fail only when those are
    absent or unusable.  ``None`` means the ladder could not be read.
    """
    try:
        proc = subprocess.run(
            [sys.executable, str(TOOLS / "card_ladder.py"), "steps", "--check"],
            capture_output=True, text=True, cwd=str(ROOT))
    except Exception:
        return None
    if proc.returncode not in (0, 1):
        return None
    groups: dict[str, list[str]] = {}
    for line in proc.stdout.splitlines():
        match = re.match(r"^(P[0-4]) \(\d+\): (.*)$", line)
        if match:
            groups[match.group(1)] = match.group(2).split()
    return groups or None


def card_step_from_report(report: dict, ladder: dict | None = None) -> dict:
    """Return the report's validated ladder step, never a guessed promotion.

    A step is printed only when all of the following hold: the report has a
    ``step`` in P0..P4; ``cardcheck_ok``/``l2check_ok`` are both True; the
    printed ``cardcheck_rc`` and ``l2check_rc`` both agree with those booleans
    (0 for True); the card has a full SHA-256; and the step appears in the
    ``card_ladder.py steps --check`` grouping.  Otherwise ``status`` is
    ``NOT RUN`` and ``step`` is ``none``.  An rc/ok disagreement sets
    ``disagree`` so it is visible beside the number, never resolved silently.
    """
    cardcheck_ok = report.get("cardcheck_ok")
    l2check_ok = report.get("l2check_ok")
    counts = report.get("counts") or {}
    cardcheck_rc = counts.get("cardcheck_rc", report.get("cardcheck_rc"))
    l2check_rc = counts.get("l2check_rc", report.get("l2check_rc"))
    card_sha256 = report.get("card_sha256")
    if not isinstance(card_sha256, str):
        card = report.get("card")
        card_sha256 = card.get("sha256") if isinstance(card, dict) else None
    if not isinstance(card_sha256, str) or not SHA256_RE.fullmatch(card_sha256):
        card_sha256 = None
    step = report.get("step")
    result = {
        "cardcheck_ok": cardcheck_ok,
        "l2check_ok": l2check_ok,
        "cardcheck_rc": cardcheck_rc,
        "l2check_rc": l2check_rc,
        "card_sha256": card_sha256,
        "step": step if step in CARD_STEPS else "none",
        "status": "LOCAL",
        "disagree": False,
        "reported_step": step,
        "ladder_available": ladder is not None,
    }
    reasons = []
    if step not in CARD_STEPS:
        reasons.append(f"no valid step (P0..P4) in report: {step!r}")
    if cardcheck_ok is not True or l2check_ok is not True:
        reasons.append("cardcheck_ok/l2check_ok not both true")
    if card_sha256 is None:
        reasons.append("report has no full card_sha256")
    ok_rcs = isinstance(cardcheck_rc, int) and isinstance(l2check_rc, int) \
        and cardcheck_rc == 0 and l2check_rc == 0
    result["disagree"] = (
        isinstance(cardcheck_ok, bool) and isinstance(cardcheck_rc, int)
        and cardcheck_ok != (cardcheck_rc == 0)
    ) or (
        isinstance(l2check_ok, bool) and isinstance(l2check_rc, int)
        and l2check_ok != (l2check_rc == 0)
    )
    if not ok_rcs:
        reasons.append(f"gate rc values not both 0: cardcheck_rc={cardcheck_rc!r} l2check_rc={l2check_rc!r}")
    if ladder is not None and step not in ladder:
        reasons.append(f"step {step!r} not in card_ladder.py steps --check groups")
    if reasons:
        result["status"] = "NOT RUN"
        result["reason"] = "; ".join(reasons)
        result["step"] = "none"
    return result


def signal_card_step(report_path: Path) -> dict:
    if not report_path.is_file():
        return _not_run(f"report not found: {report_path}")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _not_run(f"report is not JSON: {exc}")
    if not isinstance(report, dict):
        return _not_run("report JSON is not an object")
    result = card_step_from_report(report, ladder_steps())
    result["report"] = str(report_path)
    return result


# --------------------------------------------------------------------------
# formatting
# --------------------------------------------------------------------------


def _fmt_readers(sig: dict) -> str:
    if sig.get("status") != "LOCAL":
        return f"readers: NOT RUN ({sig.get('reason', 'unavailable')})"
    return (f"readers: located {sig['located']} partial {sig['partial']} "
            f"unlocated {sig['unlocated']}")


def _fmt_l3(sig: dict) -> str:
    if sig.get("status") != "LOCAL":
        return f"l3_rows: NOT RUN ({sig.get('reason', 'unavailable')})"
    return f"l3_rows: l3-running {sig['l3-running']}"


def _fmt_tiles(sig: dict) -> str:
    if sig.get("status") != "LOCAL":
        return f"tile_bytes: NOT RUN ({sig.get('reason', 'unavailable')})"
    body = ", ".join(f"{name} {pct:.2f}%" for name, pct in sig["tiles"].items())
    return f"tile_bytes: {body}"


def _fmt_card(sig: dict) -> str:
    if sig.get("status") != "LOCAL":
        return f"card_step: NOT RUN ({sig.get('reason', 'unavailable')})"
    return (f"card_step: {sig['step']} "
            f"(cardcheck_ok={sig['cardcheck_ok']} l2check_ok={sig['l2check_ok']} "
            f"cardcheck_rc={sig['cardcheck_rc']} l2check_rc={sig['l2check_rc']} "
            f"card_sha256={sig['card_sha256']}"
            f"{' DISAGREE' if sig.get('disagree') else ''})")


FORMATTERS = {
    "readers": _fmt_readers,
    "l3_rows": _fmt_l3,
    "tile_bytes": _fmt_tiles,
    "card_step": _fmt_card,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="The four rule-17 map numbers as one command (H109).")
    parser.add_argument("signals", nargs="*", metavar="SIGNAL",
                        help=f"subset of {', '.join(SIGNALS)} (default: all four)")
    parser.add_argument("--matrix", type=Path, default=None,
                        help="reader-coverage matrix (default: docs/research/reader-coverage.md)")
    parser.add_argument("--factory-root", type=Path, default=None,
                        help="factory card root holding MAPAL001/*.DAT "
                             "(default: $OSM2LEAF_FACTORY_ROOT or the host path)")
    parser.add_argument("--report", type=Path, default=None,
                        help="validated ladder report JSON "
                             "(default: $OSM2LEAF_M5_34_REPORT or the host path)")
    parser.add_argument("--json", nargs="?", const="-", default=None, metavar="PATH",
                        help="write JSON to PATH (or stdout with no PATH)")
    parser.add_argument("--selftest", action="store_true",
                        help="run the synthetic self-test and exit")
    return parser


def _resolve(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    matrix = args.matrix or DEFAULT_MATRIX
    factory_root = args.factory_root or Path(
        os.environ.get("OSM2LEAF_FACTORY_ROOT", DEFAULT_FACTORY_ROOT))
    report = args.report or Path(
        os.environ.get("OSM2LEAF_M5_34_REPORT", DEFAULT_REPORT))
    return matrix, factory_root, report


def run(args: argparse.Namespace) -> dict:
    matrix, factory_root, report = _resolve(args)
    wanted = args.signals or list(SIGNALS)
    out: dict[str, dict] = {}
    if "readers" in wanted:
        out["readers"] = signal_readers(matrix)
    if "l3_rows" in wanted:
        out["l3_rows"] = signal_l3_rows(matrix)
    if "tile_bytes" in wanted:
        out["tile_bytes"] = signal_tile_bytes(factory_root)
    if "card_step" in wanted:
        out["card_step"] = signal_card_step(report)
    return out


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv == ["--selftest"]:
        return selftest()
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    invalid = [name for name in args.signals if name not in SIGNALS]
    if invalid:
        build_parser().error(
            f"argument SIGNAL: invalid choice: {invalid[0]!r} "
            f"(choose from {', '.join(repr(s) for s in SIGNALS)})")
    result = run(args)
    if args.json is not None:
        text = json.dumps(result, indent=2)
        if args.json == "-":
            print(text)
        else:
            Path(args.json).write_text(text + "\n", encoding="utf-8")
            print(f"report: {args.json}")
    else:
        for key in SIGNALS:
            if key in result:
                print(FORMATTERS[key](result[key]))
    return 0


# --------------------------------------------------------------------------
# self-test: synthetic tile + stub report, no vendor bytes
# --------------------------------------------------------------------------


def _stub_matrix(tmp: Path) -> Path:
    """A two-row reader matrix in progress_report's owned header contract."""
    header = ("| # | File type / path | Gen | Format doc | Offline proof | "
              "Firmware reader (M3) | L3 target (M9) | L3 result | F4 (M8.E4) | "
              "Cross-year / market | Evidence (claims, EXPs) | Next action |")
    sep = "| --: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    # Row 1: located reader + REJECT L3 result (must count in both signals).
    # Row 2: partial reader + BLOCKED L3 result (must count in neither L3).
    row1 = ("| 1 | `A.DAT` | generate · exists | doc | L1 | located `0x1` (M3) | "
            "`tgt` | REJECT | — | EU 2011 | C-1; EXP-1 | M9.1 |")
    row2 = ("| 2 | `B.DAT` | generate · exists | doc | L1 | partial `0x2` (M3) | "
            "`tgt2` | BLOCKED (4) | — | EU 2011 | C-1; EXP-1 | M9.2 |")
    path = tmp / "reader-coverage.md"
    path.write_text("\n".join([header, sep, row1, row2, ""]), encoding="utf-8")
    return path


def _synthetic_tile_bytes(tmp: Path) -> Path:
    """A minimal synthetic tile via tile_diff.make_synthetic_tiles."""
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    import tile_diff  # noqa: E402
    path_a, _path_b, _facts = tile_diff.make_synthetic_tiles(str(tmp / "tiles"))
    return Path(path_a)


def selftest() -> int:
    import tempfile

    fails = 0

    def chk(cond: bool, msg: str) -> None:
        nonlocal fails
        if cond:
            print(f"  ok   {msg}")
        else:
            print(f"  FAIL {msg}")
            fails += 1

    print("map_signals selftest (synthetic, no vendor data)")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # readers + l3_rows on a fixture matrix.
        matrix = _stub_matrix(tmp)
        readers = signal_readers(matrix)
        chk(readers.get("status") == "LOCAL", "fixture matrix parses (readers LOCAL)")
        chk((readers.get("located"), readers.get("partial")) == (1, 1),
            "fixture matrix: located=1 partial=1")
        l3 = signal_l3_rows(matrix)
        chk(l3.get("status") == "LOCAL", "fixture matrix l3_rows LOCAL")
        chk(l3.get("l3-running") == 1, "fixture matrix: only the REJECT row counts (1)")

        # Absent matrix -> NOT RUN, no crash, not a guess.
        missing = signal_readers(tmp / "nope.md")
        chk(missing.get("status") == "NOT RUN", "absent matrix is readers NOT RUN")
        chk(signal_l3_rows(tmp / "nope.md").get("status") == "NOT RUN",
            "absent matrix is l3_rows NOT RUN")

        # tile_bytes on a synthetic tile: parseable, percent in [0, 100].
        tile_path = _synthetic_tile_bytes(tmp)
        try:
            ct = _import_clarion_tile()
            pct = tile_explained_percent(tile_path.read_bytes(), ct)
            chk(0.0 <= pct <= 100.0, f"synthetic tile explained percent in [0,100] ({pct:.2f}%)")

            # M4.99: section-table spans are count-word bounded (u16@taddr)
            # and read by clarion_tile.read_tile.  The positive case: the span
            # covers the still-unexplained class-d bytes and moves the number.
            det = tile_explained_percent(tile_path.read_bytes(), ct, detail=True)
            chk(det["percent"] >= det["baseline_percent"],
                "positive control: table span never lowers tile_bytes percent")
            chk(bool(det["table_spans"]), "positive control: section-table spans enumerated")
            import struct
            raw = bytearray(tile_path.read_bytes())
            for ta, tb in det["table_spans"]:
                chk(struct.unpack_from(">H", raw, ta)[0] == (tb - ta) // 2,
                    "positive control: u16@taddr == table_words (count word bounds span)")

            # Mandatory negative mutation: overwrite the count word with 1 so
            # the span no longer bounds the real table words.  The verdict
            # must change — either read_tile raises (count word is load-bearing
            # to the parser) or the span stops covering the table's nonzero
            # bytes so delta_bytes drops.
            mut = bytearray(raw)
            ta0, tb0 = det["table_spans"][0]
            struct.pack_into(">H", mut, ta0, 1)
            flipped = False
            try:
                mut_det = tile_explained_percent(bytes(mut), ct, detail=True)
                flipped = mut_det["delta_bytes"] < det["delta_bytes"]
            except (IndexError, struct.error, ValueError):
                flipped = True
            chk(flipped,
                "negative control: corrupting the count word changes the span verdict")
        except Exception as exc:  # pragma: no cover - fixture guard
            chk(False, f"synthetic tile read failed: {exc}")
        absent_tiles = signal_tile_bytes(tmp / "no-factory")
        chk(absent_tiles.get("status") == "NOT RUN"
            and absent_tiles.get("reason") == "no factory tiles",
            "absent factory root is tile_bytes NOT RUN (no factory tiles)")

        # card_step: validated reports. A synthetic ladder keeps this test
        # independent of the board's unrelated missing/bad Step tags.
        ladder = {s: [f"M9.{i}"] for i, s in enumerate(CARD_STEPS)}

        def report(step="P0", cc_ok=True, l2_ok=True, cc_rc=0, l2_rc=0,
                   sha="a" * 64, with_step=True):
            r = {"cardcheck_ok": cc_ok, "l2check_ok": l2_ok,
                 "counts": {"cardcheck_rc": cc_rc, "l2check_rc": l2_rc},
                 "card_sha256": sha}
            if with_step:
                r["step"] = step
            return r

        agree = card_step_from_report(report(), ladder)
        chk(agree["status"] == "LOCAL" and agree["step"] == "P0" and not agree["disagree"],
            "report P0, true/true, rc 0/0, full sha -> P0 LOCAL, no disagreement")
        p1 = card_step_from_report(report(step="P1"), ladder)
        chk(p1["status"] == "LOCAL" and p1["step"] == "P1",
            "report P1 with true/true rc 0/0 -> P1 (positive control: the number moves)")
        no_step = card_step_from_report(report(with_step=False), ladder)
        chk(no_step["status"] == "NOT RUN" and no_step["step"] == "none",
            "missing step key -> NOT RUN/none, never P0 (stale-report shape)")
        false_ok = card_step_from_report(report(cc_ok=False), ladder)
        chk(false_ok["status"] == "NOT RUN" and false_ok["step"] == "none",
            "false cardcheck_ok -> NOT RUN/none, no promotion")
        false_l2 = card_step_from_report(report(l2_ok=False), ladder)
        chk(false_l2["status"] == "NOT RUN" and false_l2["step"] == "none",
            "false l2check_ok -> NOT RUN/none, no promotion")
        cc_disagree = card_step_from_report(report(cc_ok=True, cc_rc=1), ladder)
        chk(cc_disagree["disagree"] is True and cc_disagree["status"] == "NOT RUN",
            "booleans true but cardcheck_rc=1 -> DISAGREE flag, NOT RUN")
        chk(cc_disagree["cardcheck_rc"] == 1, "cardcheck_rc is printed beside the booleans")
        l2_disagree = card_step_from_report(report(l2_ok=True, l2_rc=1), ladder)
        chk(l2_disagree["disagree"] is True and l2_disagree["status"] == "NOT RUN",
            "booleans true but l2check_rc=1 -> DISAGREE flag, NOT RUN")
        bad_step = card_step_from_report(report(step="P7"), ladder)
        chk(bad_step["status"] == "NOT RUN" and bad_step["step"] == "none",
            "step outside P0..P4 -> NOT RUN/none")
        ladder_disagree = card_step_from_report(report(step="P2"),
                                                {s: [] for s in ("P0", "P1", "P3", "P4")})
        chk(ladder_disagree["status"] == "NOT RUN" and ladder_disagree["step"] == "none",
            "step absent from ladder groups -> NOT RUN/none")
        no_sha = card_step_from_report(report(sha=None), ladder)
        chk(no_sha["status"] == "NOT RUN" and no_sha["step"] == "none",
            "report without full card_sha256 -> NOT RUN/none")
        nested = report(sha="b" * 64)
        nested.pop("card_sha256")
        nested["card"] = {"sha256": "b" * 64}
        chk(card_step_from_report(nested, ladder)["status"] == "LOCAL",
            "card.sha256 nested shape is accepted as the full hash")
        missing_report = signal_card_step(tmp / "nope.json")
        chk(missing_report.get("status") == "NOT RUN", "absent report is card_step NOT RUN")

        # main() exits 0 with all NOT RUN, and the text keys are stable.
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--matrix", str(tmp / "nope.md"),
                       "--factory-root", str(tmp / "no-factory"),
                       "--report", str(tmp / "nope.json")])
        text = buf.getvalue()
        chk(rc == 0, "main() with every input absent exits 0")
        chk("tile_bytes: NOT RUN (no factory tiles)" in text,
            "text line 'tile_bytes: NOT RUN (no factory tiles)' is verbatim")
        chk(text.count("NOT RUN") == 4, "all four signals report NOT RUN with no inputs")

        # Bare invocation must run all four on every Python: 3.11 rejects an
        # empty list against a positional `choices=` (the regression the first
        # push shipped), so assert the bare call prints one line per signal.
        old_env = dict(os.environ)
        os.environ["OSM2LEAF_FACTORY_ROOT"] = str(tmp / "no-factory")
        os.environ["OSM2LEAF_M5_34_REPORT"] = str(tmp / "nope.json")
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc_bare = main([])
        finally:
            os.environ.clear()
            os.environ.update(old_env)
        bare = buf.getvalue()
        chk(rc_bare == 0, "bare main([]) exits 0 (no subcommand)")
        chk(all(f"{key}:" in bare for key in ("readers", "l3_rows", "tile_bytes", "card_step")),
            "bare main([]) prints all four signal keys")

    print(f"selftest: {'OK' if not fails else 'FAIL'} ({fails} failure(s))")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
