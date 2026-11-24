#!/usr/bin/env python3
"""kiwi_verdict_check.py — check the M4.78 decision table against its own rule (clean room).

The glossary's family table is the authoritative verdict for the question
"is KIWI a shortcut?".  This tool is a *consistency check* of that table, not a
new byte probe: it re-derives every verdict from the quoted informative-fit
counts and the evidence note, so an unbacked verdict cannot be promoted by
editing a word.

Decision rule (fixed contract with docs/format/kiwi-glossary.md):

    adopt     <=> EU informative > 0 AND US informative > 0
    partial   <=> EU = US = 0 AND evidence note starts with "concept-only"
    unrelated <=> EU = US = 0 AND note does not start with "concept-only"

"Informative" excludes stored 0 / 0xffff / sentinel values: a raw fit such as
41/341 or 194/36581 whose informative column is 0 is not an adopt on either
card.  Only the numerator of the `N/M` counts is compared; `—` means 0.

Two modes:

    python3 tools/kiwi_verdict_check.py docs/format/kiwi-glossary.md
    python3 tools/kiwi_verdict_check.py --selftest

The selftest is the mandatory negative-mutation control (navigator M4.78):
the canonical table must pass, then three single-cell mutations must each fail
loudly.  It is synthetic and standard-library only: no GPL code and no vendor
bytes are read or written.

Exit status: 0 on pass (including a clean selftest), 1 on a verdict/note
mismatch or a failed mutation control, 2 on usage / unreadable input.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

HEADER_CELLS = (
    "Family", "Our name", "File / offset", "EU informative",
    "US informative", "Evidence note", "Verdict", "EXP / claims",
)
VERDICTS = {"adopt", "partial", "unrelated"}

CANONICAL_ROWS = (
    "| Basic types — SWS size word | Directory header word 0 / slot (ln, X) | "
    "docs/format/map-tiles.md:255,266,388; tile 0x000 / slot pairs | 4854/4854 | "
    "4292/4292 | informative SWS fits; also dir 24/24 EU, 16/16 US | adopt | "
    "C-7651, C-7652; EXP-M4.66 |",
    "| Basic types — D / sector address | .ind chunk_offset[], DRSTR listing_offset | "
    "docs/format/cmp-ind.md, docs/format/drstr.md | 0/300 | 0/269 | "
    "zero/sentinel-only raw fits 41/341 EU, 35/304 US; ZE0 sector+page | unrelated | "
    "C-7653, C-7654, C-7658; EXP-M4.66 |",
    "| Volume / management headers (5.x, 6.1) | common header, MMAIN/tile 0x184, 0x1ac | "
    "docs/format/file-header.md, docs/format/map-tiles.md | 0/4 | 0/4 | "
    "0/4 KIWI grammar checks on 3 files; geonum 143.922 outside frame | unrelated | "
    "EXP-M4.63, EXP-M4.67 |",
    "| Level / block management (6.1.1, 6.1.2, 6.2.1) | MMAIN level totals, tile dirs | "
    "MMAIN001.DAT 0x1ac, tile 0x1ac | 0/4 | 0/4 | "
    "nlmr=nbsmr=16191 constant, not KIWI record counts; lvl=0 | unrelated | "
    "EXP-M4.67 |",
    "| Parcel ID arithmetic (1.2.13) | tile grid, POI fine word | "
    "docs/format/coord-zcode-icode.md | 0 | 0 | "
    "grid-level arithmetic compatible; 15.625 arcsec unit not our fine step | unrelated | "
    "EXP-M4.68 |",
    "| Road frame (7.2) | 22-word road record header | "
    "docs/format/map-tiles.md:548-568 | 0/3000 | 0/3000 | "
    "distribution header size word fails on 6,000 records on two cards | unrelated | "
    "EXP-M4.69 |",
    "| Background frame (7.3) | odd background records, ZE0 shapes | "
    "docs/format/map-tiles.md:570-587 | 0/1416 | 0/12220 | "
    "concept-only: shared 11-bit count and i8 deltas; ZE0 shape one word shorter | partial | "
    "EXP-M4.70 |",
    "| Route planning (ch.10) | section 2 node / link records | "
    "docs/format/map-tiles.md (section 2) | 0 | 0 | "
    "no field named; r=0.1035/0.0363 under 0.8; ch.10 names reference only | unrelated | "
    "EXP-M4.72 |",
    "| Route guidance (8.4) | section 4 signpost, INTER/FRWAY shards | "
    "docs/format/refer.md, tile section 4 | 0 | 0 | "
    "concept-only: field kinds predicted, ZE0 stores verbatim text keyed by mesh | partial | "
    "EXP-M4.73 |",
    "| Firmware vocabulary | Navi.exe string table, XGLDLL.dll symbol | "
    "docs/format/kiwi-glossary.md (firmware table) | 0 | 0 | "
    "concept-only: MDP_*/XANAVI/RcvParcel in ROM A; KIWI chapter terms absent | partial | "
    "EXP-M4.64 |",
)


def _cells(row: str) -> list[str]:
    parts = re.split(r"(?<!\\)\|", row.strip())
    if len(parts) != len(HEADER_CELLS) + 2:
        raise ValueError(f"row has {len(parts) - 2} cells, need {len(HEADER_CELLS)}: {row[:60]!r}")
    return [p.strip() for p in parts[1:-1]]


def read_rows(text: str) -> list[list[str]]:
    lines = text.splitlines()
    starts = [i for i, l in enumerate(lines)
              if l.strip().startswith("|") and _header_matches(l)]
    if len(starts) != 1:
        raise ValueError(f"found {len(starts)} decision-table headers, need 1")
    rows: list[list[str]] = []
    for line in lines[starts[0] + 2:]:
        if not line.strip().startswith("|"):
            break
        rows.append(_cells(line))
    if not rows:
        raise ValueError("decision table has no data rows")
    return rows


def _header_matches(line: str) -> bool:
    try:
        return tuple(_cells(line)) == HEADER_CELLS
    except ValueError:
        return False


def informative(cell: str) -> int:
    head = cell.split("/", 1)[0].strip().replace(",", "")
    if head in ("", "—", "-", "0"):
        return 0
    if not head.isdigit():
        raise ValueError(f"not an informative count: {cell!r}")
    return int(head)


def check(rows: list[list[str]]) -> tuple[bool, list[str]]:
    problems: list[str] = []
    counts = {"adopt": 0, "partial": 0, "unrelated": 0}
    for cells in rows:
        family, _name, _where, eu, us, note, verdict, _evidence = cells
        if verdict not in VERDICTS:
            problems.append(f"{family}: unknown verdict {verdict!r}")
            continue
        counts[verdict] += 1
        e, u = informative(eu), informative(us)
        expected = ("adopt" if e > 0 and u > 0 else
                    "partial" if note.startswith("concept-only") else
                    "unrelated")
        if verdict != expected:
            problems.append(
                f"{family}: verdict {verdict!r} but EU={e} US={u}, "
                f"note={note[:40]!r} implies {expected!r}")
    if counts["adopt"] != 1 or counts["partial"] != 3 or counts["unrelated"] != 6:
        problems.append(
            f"family counts {counts}, expected 1 adopt / 3 partial / 6 unrelated")
    return not problems, problems


def selftest() -> int:
    header = "| " + " | ".join(HEADER_CELLS) + " |"
    sep = "| " + " | ".join("---" for _ in HEADER_CELLS) + " |"
    table = "\n".join([header, sep, *CANONICAL_ROWS])
    ok, problems = check(read_rows(table))
    if not ok:
        print("kiwi_verdict_check selftest: canonical table FAILED")
        for p in problems:
            print("  " + p)
        return 1
    print("kiwi_verdict_check selftest: canonical table OK (1 adopt, 3 partial, 6 unrelated)")

    mutations = (
        ("flip SWS adopt->unrelated",
         CANONICAL_ROWS[0].replace("| adopt |", "| unrelated |")),
        ("corrupt SWS EU informative 4854->0",
         CANONICAL_ROWS[0].replace("| 4854/4854 |", "| 0/4854 |")),
        ("relabel zero-informative D/SA unrelated->adopt",
         CANONICAL_ROWS[1].replace("| unrelated |", "| adopt |")),
    )
    for index, (label, mutated) in enumerate(mutations):
        rows = list(CANONICAL_ROWS)
        rows[index] = mutated
        bad_table = "\n".join([header, sep, *rows])
        bad_ok, bad_problems = check(read_rows(bad_table))
        if bad_ok:
            print(f"  FAIL {label}: mutation was accepted")
            return 1
        print(f"  REJECT {label}: {bad_problems[0][:78]}")
    print("kiwi_verdict_check selftest: 3/3 mutations rejected, OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("glossary", nargs="?", help="glossary page with the family table")
    ap.add_argument("--selftest", action="store_true", help="synthetic positive + 3 mutation controls")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.glossary:
        ap.error("give a glossary path or --selftest")
    path = Path(args.glossary)
    try:
        rows = read_rows(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"kiwi_verdict_check: {exc}")
        return 2
    ok, problems = check(rows)
    if not ok:
        print(f"kiwi_verdict_check: {path} FAIL")
        for p in problems:
            print("  " + p)
        return 1
    print(f"kiwi_verdict_check: {path} OK ({len(rows)} rows: "
          "1 adopt, 3 partial, 6 unrelated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
