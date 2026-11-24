#!/usr/bin/env python3
"""kiwi_index_check.py — consistency check of the M4.74 KIWIndex family table.

The EXP's family table maps a ZE0 index family (POINT, ADDRE, ZCODE, ICODE,
COORD, INDEX) to a KIWI chapter-11 index structure, a byte test and a verdict.
This tool re-derives every verdict from the quoted informative counts and the
evidence note, so a verdict cannot be promoted by editing a single word.

Decision rule (same contract as tools/kiwi_verdict_check.py):

    adopt     <=> EU informative > 0 AND US informative > 0
    partial   <=> EU = US = 0 AND evidence note starts with "concept-only"
    unrelated <=> EU = US = 0 AND note does not start with "concept-only"

"No byte test" is recorded as 0.  A concept-only row is a structure-name
mapping only (KIWI chapter 11 was not obtained as a byte layout in M4.65),
never a byte-level adoption and never rule-13 confirmation of a reader VA.

Two modes:

    python3 tools/kiwi_index_check.py docs/experiments/EXP-2026-11-24-M4.74-kiwi-index.md
    python3 tools/kiwi_index_check.py --selftest

The selftest is the mandatory negative-mutation control: the canonical table
must pass, then three single-cell mutations must each fail loudly.  Synthetic
and standard-library only: no GPL code and no vendor bytes are read or written.

Exit status: 0 on pass, 1 on a verdict/note mismatch or a failed mutation
control, 2 on usage / unreadable input.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

HEADER_CELLS = (
    "Family", "KIWI structure (ch.1/ch.11)", "Our family / node format",
    "Record id width", "Record -> parcel", "Byte test (EU/US)",
    "Evidence note", "Verdict", "Evidence",
)
VERDICTS = {"adopt", "partial", "unrelated"}

CANONICAL_ROWS = (
    "| POINT POI index | 11.1 Index Data Frame; 11.7 Category Codes; "
    "11.8 Jump Table | name-trie + 12-u16 index records + spatial leaves | "
    "24-byte index key (12 BE u16) | spatial leaf by low 11 bits of name ptr | "
    "0/0 | concept-only: tries, index and category words present; KIWI node "
    "format not on disk; 2,814,259/2,814,259 key joins | partial | "
    "EXP-M4.74; C-7730, C-7731 |",
    "| ADDRE address index | 11.1 Index Data Frame; 7.4 Name Data Frame | "
    "12-B initial directory + 6-B cells + 22-B index records | "
    "11 BE u16 per index record | packed coord id (cx,cy) + point tokens | "
    "0/0 | concept-only: initial-directory trie and word records match the "
    "index-frame concept; KIWI node format differs; 2621/2621 count | partial | "
    "EXP-M4.74; C-7732, C-7733 |",
    "| ZCODE postal trie | 11.1 Index Data Frame; 11.7 Category Codes | "
    "12-B dir entries (size, tag, count, offset), child = 0x1204 + offset*2 | "
    "1-B digit tag '0'..'9' | 16-B area ladder of u16 coords, not a parcel id | "
    "0/0 | concept-only: digit-keyed trie with a jump-like offset; sector "
    "encoding rec_addr_enc 0xbaf00 -> 0x5d7800 | partial | "
    "EXP-M4.74; C-7734 |",
    "| ICODE place-name index | 11.8 Jump Table; 7.4 Name Data Frame | "
    "12-B name rows (rlen, nlen, roff, cnt, idx) in per-language chains | "
    "u16 roff relative to language chain | chain link, chain terminator "
    "0xffffffff | 0/0 | concept-only: ch.11 jump table predicts a root-pointer "
    "table; our root-pointer table still UNKNOWN, so no field is resolved | "
    "partial | EXP-M4.74; C-7735 |",
    "| COORD region boxes | 10.12 Node Coordinate Data; 1.2.13 Parcel ID | "
    "14-B bbox records (x0,y0,x1,y1,level48) at 0x1010 | "
    "u16 grid (lat/192, lon/128) | one-hot 48-bit level mask, no parcel pointer | "
    "0/0 | 15.625 arcsec KIWI unit not our fine step; M4.68 already unrelated | "
    "unrelated | EXP-M4.74; C-7736 |",
    "| INDEX search index | 11.1 Index Data Frame; 11.8 Jump Table | "
    "INDEX003 absent EU+US; US INDEX001 binary, layout UNKNOWN | "
    "UNKNOWN | UNKNOWN | 0/0 | concept-only: ch.11 is the name of this family "
    "but no file on these cards carries a testable frame; layout stays UNKNOWN | "
    "partial | EXP-M4.74; C-7737 |",
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
        raise ValueError(f"found {len(starts)} family-table headers, need 1")
    rows: list[list[str]] = []
    for line in lines[starts[0] + 2:]:
        if not line.strip().startswith("|"):
            break
        rows.append(_cells(line))
    if not rows:
        raise ValueError("family table has no data rows")
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


def check(rows: list[list[str]]) -> tuple[bool, list[str], dict[str, int]]:
    problems: list[str] = []
    counts = {"adopt": 0, "partial": 0, "unrelated": 0}
    for cells in rows:
        family, _structure, _ours, _idwidth, _parcel, bytetest, note, verdict, _ev = cells
        if verdict not in VERDICTS:
            problems.append(f"{family}: unknown verdict {verdict!r}")
            continue
        counts[verdict] += 1
        eu, _, us = bytetest.partition("/")
        e, u = informative(eu), informative(us)
        expected = ("adopt" if e > 0 and u > 0 else
                    "partial" if note.startswith("concept-only") else
                    "unrelated")
        if verdict != expected:
            problems.append(
                f"{family}: verdict {verdict!r} but EU={e} US={u}, "
                f"note={note[:40]!r} implies {expected!r}")
    return not problems, problems, counts


def selftest() -> int:
    header = "| " + " | ".join(HEADER_CELLS) + " |"
    sep = "| " + " | ".join("---" for _ in HEADER_CELLS) + " |"
    table = "\n".join([header, sep, *CANONICAL_ROWS])
    ok, problems, counts = check(read_rows(table))
    if not ok:
        print("kiwi_index_check selftest: canonical table FAILED")
        for p in problems:
            print("  " + p)
        return 1
    print("kiwi_index_check selftest: canonical table OK "
          f"({counts['adopt']} adopt, {counts['partial']} partial, "
          f"{counts['unrelated']} unrelated)")

    mutations = (
        ("flip POINT partial->adopt with 0/0 counts",
         CANONICAL_ROWS[0].replace("| partial |", "| adopt |")),
        ("relabel COORD unrelated->concept-only partial",
         CANONICAL_ROWS[4].replace("| unrelated |", "| partial |")),
        ("invent an informative ZCODE byte test 1/1",
         CANONICAL_ROWS[2].replace("| 0/0 |", "| 1/1 |")),
    )
    for index, (label, mutated) in enumerate(mutations):
        rows = list(CANONICAL_ROWS)
        rows[index] = mutated
        bad_table = "\n".join([header, sep, *rows])
        bad_ok, bad_problems, _ = check(read_rows(bad_table))
        if bad_ok:
            print(f"  FAIL {label}: mutation was accepted")
            return 1
        print(f"  REJECT {label}: {bad_problems[0][:78]}")
    print("kiwi_index_check selftest: 3/3 mutations rejected, OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("exp", nargs="?", help="EXP page with the family table")
    ap.add_argument("--selftest", action="store_true",
                    help="synthetic positive + 3 mutation controls")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.exp:
        ap.error("give an EXP path or --selftest")
    path = Path(args.exp)
    try:
        rows = read_rows(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"kiwi_index_check: {exc}")
        return 2
    ok, problems, counts = check(rows)
    if not ok:
        print(f"kiwi_index_check: {path} FAIL")
        for p in problems:
            print("  " + p)
        return 1
    print(f"kiwi_index_check: {path} OK "
          f"({len(rows)} rows: {counts['adopt']} adopt, {counts['partial']} partial, "
          f"{counts['unrelated']} unrelated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
