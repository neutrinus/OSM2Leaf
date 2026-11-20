#!/usr/bin/env python3
"""Decode the INTER/FRWAY 12-byte record table at 0x1108 (M3.16).

The factory files are **big-endian**: the record is ``u16 key`` (``0xffff`` =
terminator at record +0), ``u16 0`` (+2), ``u8 id`` (+4), ``u8 0`` (+5),
``u16 length`` (+6), ``u16 0`` (+8), ``u16 offset`` (+10).  The little-endian
reading in ``refer.md`` (``u8 id`` at +0, ``u16 length`` at +8) puts the
``0xffff`` terminator at +8, which no factory shard has; it is an endianness
and field-offset error (C-2215/C-2216).

Usage::

  inter_table.py --selftest
  inter_table.py dump FILE [--max N] [--json]
  inter_table.py check FILE...        # exit 1 on a record violating the layout
  inter_table.py refute FILE...       # old LE (11-byte) layout vs the real one
"""

from __future__ import annotations

import argparse
import json
import struct
import sys

TABLE_BLOCK = 0x1108          # 8-byte block header; records start at +8
RECORD_SIZE = 12
TERMINATOR = 0xFFFF


def records(blob: bytes):
    """Yield ``(offset, key, id, length, index)`` for each record before the
    terminator; stop at the first non-conforming record.

    A record conforms when ``u16@+2 == 0``, ``u8@+5 == 0`` and (except in the
    large shards where a third field is populated) ``u16@+8`` holds no more
    than the "zero" invariant the doc claims.  We report the ``u16@+8`` value
    instead of rejecting on it, because INTER002–005 set it (C-2216).
    """
    base = TABLE_BLOCK + 8
    pos = base
    while pos + RECORD_SIZE <= len(blob):
        rec = blob[pos:pos + RECORD_SIZE]
        key, zero2, idb, zero5, length, zero8, index = struct.unpack(">HHBBHHH", rec)
        if key == TERMINATOR:
            return
        if zero2 != 0 or zero5 != 0:
            return
        yield pos, key, idb, length, index, zero8
        pos += RECORD_SIZE


def decode(blob: bytes):
    rows = []
    for pos, key, idb, length, index, zero8 in records(blob):
        rows.append({"offset": pos, "key": key, "id": idb,
                     "length": length, "index": index, "zero8": zero8})
    return rows


def check(blob: bytes, name: str) -> list[str]:
    """Layout violations on the whole record run; empty list means clean.

    Only ``u16@+2 == 0`` is a hard invariant (all factory shards).  ``u8@+5``
    and ``u16@+8`` are per-record variant fields (``u16@+8`` nonzero in 25/35
    INTER002, 8/29 INTER003, 23/31 INTER004, 25/36 INTER005 records;
    ``u8@+5`` nonzero in 4 INTER005 records), so they are reported as notes,
    not failures.
    """
    problems = []
    base = TABLE_BLOCK + 8
    pos = base
    n = 0
    v5 = v8 = 0
    while pos + RECORD_SIZE <= len(blob):
        rec = blob[pos:pos + RECORD_SIZE]
        key, zero2, idb, zero5, length, zero8, index = struct.unpack(">HHBBHHH", rec)
        if key == TERMINATOR:
            if v5 or v8:
                print(f"{name}: {v5} record(s) u8@+5 != 0, {v8} record(s) "
                      f"u16@+8 != 0 (variant fields)")
            return problems
        if zero2 != 0:
            problems.append(f"{name}+{pos:#06x}: u16@+2 = {zero2:#06x} (want 0)")
        v5 += zero5 != 0
        v8 += zero8 != 0
        n += 1
        pos += RECORD_SIZE
    problems.append(f"{name}: no 0xffff terminator after {n} records")
    return problems


def refute(blob: bytes):
    """Count the old little-endian layout's invariants against the real run.

    The pre-M3.16 doc wrote the record as ``u8 id, u16 n, u16 0, u16 offset,
    u16 length, u16 0`` **little-endian** (11 bytes), so ``u16 0`` sits at +3,
    ``length`` at +7 and — reading r2's +8 family — the ``0xffff`` terminator
    at +8.  We walk the records using the real (big-endian, 12-byte, 0xffff at
    +0) terminator and test each old assertion.  Returns a dict of counts.
    """
    base = TABLE_BLOCK + 8
    pos = base
    n = z3 = t7 = t8 = be2 = 0
    while pos + RECORD_SIZE <= len(blob):
        key = struct.unpack_from(">H", blob, pos)[0]
        if key == TERMINATOR:
            break
        z3 += struct.unpack_from("<H", blob, pos + 3)[0] == 0
        t7 += struct.unpack_from("<H", blob, pos + 7)[0] == TERMINATOR
        t8 += struct.unpack_from("<H", blob, pos + 8)[0] == TERMINATOR
        be2 += struct.unpack_from(">H", blob, pos + 2)[0] == 0
        n += 1
        pos += RECORD_SIZE
    return {"records": n, "u16_le_+3_zero": z3, "u16_le_+7_ffff": t7,
            "u16_le_+8_ffff": t8, "u16_be_+2_zero": be2}


def synthetic() -> bytes:
    """One conforming shard: header, three records, terminator, tail."""
    out = bytearray(0x1110)
    out[0x1108:0x1110] = b"\x00\x00\x00\x10\x00\x08\x00\x00"   # 8-byte block header
    recs = [(0x24, 0x42, 0x10, 0x0100), (0x30, 0x43, 0x12, 0x0200),
            (0x18, 0x44, 0x1b, 0x0300)]
    for key, idb, length, index in recs:
        out += struct.pack(">HHBBHHH", key, 0, idb, 0, length, 0, index)
    out += struct.pack(">HHBBHHH", TERMINATOR, TERMINATOR, 0xFF, 0, 0, 0, 0)
    out += b"\x00" * 0x40
    return bytes(out)


def selftest() -> int:
    fails = 0

    def check_(name, cond):
        nonlocal fails
        print("%-56s %s" % (name, "ok" if cond else "FAIL"))
        fails += not cond

    blob = synthetic()
    rows = decode(blob)
    check_("three records decoded before the terminator", len(rows) == 3)
    check_("ids are 0x42/0x43/0x44", [r["id"] for r in rows] == [0x42, 0x43, 0x44])
    check_("key read big-endian (0x24, not 0x2400)", rows[0]["key"] == 0x24)
    check_("length at +6", [r["length"] for r in rows] == [0x10, 0x12, 0x1b])
    check_("index at +10", [r["index"] for r in rows] == [0x100, 0x200, 0x300])
    check_("clean shard has no layout problems", check(blob, "syn") == [])
    # negative: a 0xffff key at +0 ends the run at that record
    bad = bytearray(blob)
    bad[0x1110:0x1112] = b"\xff\xff"
    check_("0xffff key ends the run at that record", len(decode(bytes(bad))) == 0)
    # negative: nonzero +2 is rejected
    bad2 = bytearray(blob)
    bad2[0x1110 + 2] = 0x01
    check_("nonzero u16@+2 stops the run", len(decode(bytes(bad2))) == 0)
    check_("check() flags the nonzero u16@+2", check(bytes(bad2), "bad") != [])
    print("selftest:", "PASS" if not fails else "FAIL (%d)" % fails)
    return 0 if not fails else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    d = sub.add_parser("dump", help="print the record table")
    d.add_argument("file")
    d.add_argument("--max", type=int, default=40)
    d.add_argument("--json", action="store_true")
    c = sub.add_parser("check", help="validate the record layout")
    c.add_argument("files", nargs="+")
    rf = sub.add_parser("refute", help="old LE layout vs the real one")
    rf.add_argument("files", nargs="+")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "dump":
        rows = decode(open(args.file, "rb").read())
        if args.json:
            print(json.dumps(rows[:args.max], indent=1))
        else:
            print(f"{args.file}: {len(rows)} records")
            for r in rows[:args.max]:
                print("  +%#06x key=%#06x id=%#04x len=%#06x index=%#06x u16@8=%#06x"
                      % (r["offset"], r["key"], r["id"], r["length"],
                         r["index"], r["zero8"]))
        return 0
    if args.cmd == "refute":
        tot = {"records": 0, "u16_le_+3_zero": 0, "u16_le_+7_ffff": 0,
               "u16_le_+8_ffff": 0, "u16_be_+2_zero": 0}
        for f in args.files:
            r = refute(open(f, "rb").read())
            print(f"{f}: {r['records']} records  old LE@+3==0 {r['u16_le_+3_zero']}"
                  f"/{r['records']}  LE@+7==ffff {r['u16_le_+7_ffff']}"
                  f"  LE@+8==ffff {r['u16_le_+8_ffff']}"
                  f"  real BE@+2==0 {r['u16_be_+2_zero']}/{r['records']}")
            for k in tot:
                tot[k] += r[k]
        print("TOTAL %d records  old LE@+3==0 %d  LE@+7==ffff %d  LE@+8==ffff %d  "
              "real BE@+2==0 %d"
              % (tot["records"], tot["u16_le_+3_zero"], tot["u16_le_+7_ffff"],
                 tot["u16_le_+8_ffff"], tot["u16_be_+2_zero"]))
        return 0
    if args.cmd == "check":
        bad = 0
        for f in args.files:
            problems = check(open(f, "rb").read(), f)
            print(f"{f}: {'OK' if not problems else '%d problems' % len(problems)}")
            for p in problems[:10]:
                print("  " + p)
            bad += bool(problems)
        return 1 if bad else 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
