#!/usr/bin/env python3
"""One 16-byte RDSTM001.DAT table row: decode, encode, round-trip (M4.1).

Scope: a field split of one row into the candidate link tuple from
docs/format/rdstm.md (`--layout link=...`, record size 0x10). Every byte of
the row belongs to a field, so decode followed by encode returns the same 16
bytes. That is what the round-trip check proves. It proves nothing about the
meaning of a field: the field names are HYPOTHESIS (rdstm.md, "Ranked
unknowns" 3), not decodes.

Layout (little-endian, offsets within the row):
  0  u16  id        HYPOTHESIS: row / node index
  2  u16  pad2      no role found (kept so the row is covered)
  4  u32  ref       HYPOTHESIS: reference or offset
  8  u16  src       HYPOTHESIS: graph node (src of the tuple)
  10 u16  dst       HYPOTHESIS: graph node (dst of the tuple)
  12 u16  code      HYPOTHESIS: 2-byte code (LCTBL-linked, rdstm.md)
  14 u16  tail      no role found

Usage:
  rdstm_record.py FILE OFFSET [--count N]   decode and round-trip N rows
  rdstm_record.py --selftest                synthetic checks, no vendor data
"""
from __future__ import annotations

import argparse
import random
import struct
import sys
from pathlib import Path

ROW = 0x10
FIELDS = (
    ("id", 0, "<H"),
    ("pad2", 2, "<H"),
    ("ref", 4, "<I"),
    ("src", 8, "<H"),
    ("dst", 10, "<H"),
    ("code", 12, "<H"),
    ("tail", 14, "<H"),
)


def decode(row: bytes) -> dict:
    if len(row) != ROW:
        raise ValueError(f"row must be {ROW} bytes, got {len(row)}")
    return {name: struct.unpack_from(fmt, row, off)[0] for name, off, fmt in FIELDS}


def encode(rec: dict) -> bytes:
    out = bytearray(ROW)
    for name, off, fmt in FIELDS:
        struct.pack_into(fmt, out, off, rec[name])
    return bytes(out)


def roundtrip(row: bytes) -> bool:
    return encode(decode(row)) == row


def _selftest() -> int:
    fails = []

    def check(name, cond):
        if not cond:
            fails.append(name)

    # known values, little-endian
    row = bytes(range(16))
    rec = decode(row)
    check("known id", rec["id"] == 0x0100)
    check("known ref", rec["ref"] == 0x07060504)
    check("known src", rec["src"] == 0x0908)
    check("known code", rec["code"] == 0x0D0C)
    check("known roundtrip", encode(rec) == row)
    # random rows round-trip (coverage of all 16 bytes)
    rng = random.Random(1)
    check("random roundtrip", all(
        roundtrip(bytes(rng.randrange(256) for _ in range(ROW))) for _ in range(500)))
    # wrong length is refused
    try:
        decode(b"\x00" * 15)
        check("short row refused", False)
    except ValueError:
        pass
    print(f"selftest: {'OK' if not fails else 'FAIL ' + ', '.join(fails)}")
    return 0 if not fails else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("offset", nargs="?")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if not a.file or a.offset is None:
        ap.error("FILE and OFFSET are required")
    off = int(a.offset, 0)
    with Path(a.file).open("rb") as fh:
        fh.seek(off)
        blob = fh.read(ROW * a.count)
    ok = 0
    for i in range(len(blob) // ROW):
        row = blob[i * ROW:(i + 1) * ROW]
        rec = decode(row)
        good = roundtrip(row)
        ok += good
        print(f"{off + i * ROW:#010x} " + " ".join(f"{k}={v:#x}" for k, v in rec.items())
              + f" roundtrip={'ok' if good else 'FAIL'}")
    print(f"rows={len(blob) // ROW} roundtrip_ok={ok}")
    return 0 if ok == len(blob) // ROW else 1


if __name__ == "__main__":
    sys.exit(main())
