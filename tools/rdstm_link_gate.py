#!/usr/bin/env python3
"""Gate for M4.2: can any RDSTM001 row field be tied to a road identity?

M4.2 needs a row -> road link before OSM tags can be correlated with row
fields. This gate runs first and needs no OSM. For each candidate u16 field of
the 16-byte row (offsets 0..14, plus the high byte of the code at +12, which
the sample shows as the only non-zero byte of the code word) it measures the
LCTBL001 join hit rate (catalog code or 2-byte name prefix; see
``rdstm_schema.join_probe``) and compares it with a control: the same number
of uniform random u16 values, drawn with a fixed seed.

A field passes the gate only if all of these hold:

* its unique-value hit rate is at least ``--min-hit`` (default 0.50), so most
  distinct values resolve to the index,
* that rate exceeds the random control by ``--margin`` (default 0.10),
* it has at least ``--min-distinct`` distinct values (a road identity needs
  more than a handful of classes), and
* the hit rate is measured on at least ``--min-rows`` rows.

Passing the gate would still not prove a join: ``join_probe`` is a necessary
condition (C-105). A pass means "the next step, OSM correlation, is worth
running"; a fail means no field can be tied to a road from this file alone.

Usage::

    python3 tools/rdstm_link_gate.py RDSTM001.DAT LCTBL001.DAT
    python3 tools/rdstm_link_gate.py RDSTM001.DAT LCTBL001.DAT --start 0x1000 --rows 4096 --json
    python3 tools/rdstm_link_gate.py --selftest

Exit codes: ``0`` ran (gate result printed), ``1`` gate selftest or input
failure, ``2`` usage or I/O error.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rdstm_schema  # noqa: E402  (same directory, read-only use)

ROW = 0x10
SEED = 42


def candidate_fields() -> list[tuple[str, int, int, int]]:
    """(label, byte offset, width, shift) for every u16 field plus code high byte."""
    fields = [(f"u16@{off:#x}", off, 2, 0) for off in range(0, ROW, 2)]
    fields.append(("byte@0xd(code hi)", 0xD, 1, 0))
    return fields


def extract(blob: bytes, start: int, rows: int, offset: int, width: int) -> list[int]:
    values: list[int] = []
    for index in range(rows):
        position = start + index * ROW + offset
        raw = blob[position : position + width]
        if len(raw) < width:
            break
        values.append(int.from_bytes(raw, "little"))
    return values


def random_control(count: int, seed: int = SEED) -> list[int]:
    rng = random.Random(seed)
    return [rng.randrange(0, 0x10000) for _ in range(count)]


def evaluate(
    blob: bytes,
    start: int,
    rows: int,
    index: dict,
    margin: float,
    min_hit: float,
    min_distinct: int,
    min_rows: int,
) -> list[dict]:
    results: list[dict] = []
    for label, offset, width, _shift in candidate_fields():
        values = extract(blob, start, rows, offset, width)
        if not values:
            results.append({"field": label, "rows": 0, "pass": False, "reason": "no rows"})
            continue
        observed = rdstm_schema.join_probe(values, index)
        control = rdstm_schema.join_probe(random_control(len(values)), index)
        distinct = len(set(values))
        # Unique-value basis: a key must resolve distinct values, and repeated
        # values must not inflate the rate (the occurrence rate does).
        hit = observed["index_hit_unique"]
        base = control["index_hit_unique"]
        reasons = []
        if len(values) < min_rows:
            reasons.append(f"rows {len(values)} < {min_rows}")
        if hit < min_hit:
            reasons.append(f"unique hit {hit:.3f} < {min_hit:.2f}")
        if hit - base < margin:
            reasons.append(f"unique hit {hit:.3f} - control {base:.3f} < {margin:.2f}")
        if distinct < min_distinct:
            reasons.append(f"distinct {distinct} < {min_distinct}")
        results.append(
            {
                "field": label,
                "rows": len(values),
                "distinct": distinct,
                "hit": round(hit, 4),
                "control_hit": round(base, 4),
                "pass": not reasons,
                "reason": "; ".join(reasons) or "pass",
            }
        )
    return results


def print_table(results: list[dict]) -> None:
    print(f"{'field':<20} {'rows':>6} {'distinct':>8} {'uniq-hit':>9} {'control':>8}  gate")
    for row in results:
        print(
            f"{row['field']:<20} {row.get('rows', 0):>6} {row.get('distinct', 0):>8} "
            f"{row.get('hit', 0.0):>7.3f} {row.get('control_hit', 0.0):>8.3f}  "
            f"{'PASS' if row['pass'] else 'fail'} ({row['reason']})"
        )
    passed = [row["field"] for row in results if row["pass"]]
    print(f"gate: {len(passed)} of {len(results)} fields pass" + (f" ({', '.join(passed)})" if passed else ""))


def cmd_run(args: argparse.Namespace) -> int:
    try:
        blob = Path(args.rdstm).read_bytes()
        lctbl = Path(args.lctbl).read_bytes()
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    index = rdstm_schema.lctbl_index(lctbl, None)
    rows = args.rows or (len(blob) - args.start) // ROW
    results = evaluate(blob, args.start, rows, index, args.margin, args.min_hit, args.min_distinct, args.min_rows)
    if args.json:
        print(json.dumps({"file": str(args.rdstm), "start": args.start, "rows": rows, "fields": results}, indent=2))
    else:
        print_table(results)
    return 0


def cmd_selftest(_args: argparse.Namespace) -> int:
    """Positive control: a field of known catalog codes must pass. Negative: random fields must fail."""
    lctbl = rdstm_schema.build_synthetic_lctbl()
    index = rdstm_schema.lctbl_index(lctbl, None)
    known = sorted(index["catalog_set"] | index["prefixes"])
    if len(known) < 8:
        print("selftest: synthetic index too small", file=sys.stderr)
        return 1
    rng = random.Random(7)
    rows = 512
    blob = bytearray()
    for index_row in range(rows):
        row = bytearray(ROW)
        # field at +12 carries a known code (positive control)
        code = known[rng.randrange(len(known))]
        row[12:14] = code.to_bytes(2, "little")
        # field at +4 carries uniform noise (negative control)
        row[4:8] = rng.randrange(0, 1 << 32).to_bytes(4, "little")
        row[0:2] = index_row.to_bytes(2, "little")
        blob += row
    results = evaluate(bytes(blob), 0, rows, index, margin=0.10, min_hit=0.50, min_distinct=8, min_rows=64)
    by_field = {row["field"]: row for row in results}
    failures = []
    positive = by_field["u16@0xc"]
    if not positive["pass"]:
        failures.append(f"positive control did not pass: {positive['reason']}")
    noise = by_field["u16@0x4"]
    if noise["pass"]:
        failures.append("negative control (random u32 at +4) passed the gate")
    if failures:
        for line in failures:
            print(f"selftest FAIL: {line}", file=sys.stderr)
        return 1
    print(f"selftest: OK (positive u16@0xc hit {positive['hit']:.3f}, noise u16@0x4 hit {noise['hit']:.3f})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rdstm", nargs="?", help="RDSTM001.DAT")
    ap.add_argument("lctbl", nargs="?", help="LCTBL001.DAT")
    ap.add_argument("--start", type=lambda s: int(s, 0), default=0x1000)
    ap.add_argument("--rows", type=int, default=0, help="rows to test (0 = to end of file)")
    ap.add_argument("--margin", type=float, default=0.10)
    ap.add_argument("--min-hit", type=float, default=0.50)
    ap.add_argument("--min-distinct", type=int, default=64)
    ap.add_argument("--min-rows", type=int, default=1024)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return cmd_selftest(args)
    if not args.rdstm or not args.lctbl:
        print("error: RDSTM001.DAT and LCTBL001.DAT are required", file=sys.stderr)
        return 2
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
