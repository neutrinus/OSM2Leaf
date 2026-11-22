#!/usr/bin/env python3
"""Decode the hard-key translation tables embedded in build-B kepdrv.dll (M8.H37).

kepdrv.dll is the Windows CE key-event processor of the ZE0 head unit.  Its
compressed section 1 (o32_realaddr 0x01f42000) holds a block of ``{u8 code,
u8 vk}`` pairs.  ``KEPV:FindTable (0x03a161dc)`` selects a {pointer,count} pair
from the object installed by fn 0x03a15d58, and ``KEPV:GetVkey (0x03a16e60)``
(or ``KEPV:GetMatrixKey (0x03a15f40)``) linearly scans that pair list.  The
counts below are the immediates written by fn 0x03a15d58, quoted from
``python3 tools/sh4dis.py ... --va 0x03a15d58``; they are part of this tool so
the decode is reproducible without re-reading the disassembly.

No vendor bytes are stored here: the image is read from the sample path, the
compressed section is decoded with tools/nk_decomp.py (kernel routine), and
only offsets, counts, hashes and byte pairs are printed.

Usage:
  python3 tools/kep_tables.py IMG [--image-start 0x3e00200] [--json]
  python3 tools/kep_tables.py --selftest
"""

import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cerom
import nk_decomp

MODULE = "kepdrv.dll"
SEC_INDEX = 1                 # rva 0xc000, o32_realaddr 0x01f42000
SEC_REALADDR = 0x01f42000
DEFAULT_IMAGE_START = 0x3e00200

# (offset in sec1, count, use, selector) -- counts from fn 0x03a15d58 writes.
# Selector is the panel/maker word compared at 0x03a15d84..0x03a15d96, or
# MATRIX when r2+12 == 2 (0x03a15d60).
TABLES = (
    (0x0100, 2,  "matrix", "panel word == 2 (fn 0x03a15d60)"),
    (0x0104, 9,  "KeyType 1", "default panel"),
    (0x0118, 9,  "KeyType 1", "panel 0x10100600"),
    (0x012c, 9,  "KeyType 1", "panel 0x01101100"),
    (0x0140, 13, "KeyType 1", "panel 0x10101100"),
    (0x0158, 1,  "KeyType 1", "panel word == 2 (fn 0x03a15d78)"),
    (0x015c, 10, "KeyType 2", "default panel"),
    (0x0170, 10, "KeyType 2", "panel 0x10100600"),
    (0x0184, 10, "KeyType 2", "panel 0x01101100"),
    (0x0198, 10, "KeyType 2", "panel 0x10101100"),
    (0x01b4, 17, "KeyType 3", "always (fn 0x03a15e1e)"),
    (0x01d8, 18, "KeyType 4", "always (fn 0x03a15e34)"),
    (0x01fc, 7,  "KeyType 3", "alternate (fn 0x03a15e3a)"),
    (0x0210, 36, "KeyType 5", "always (fn 0x03a15e4c)"),
    (0x0258, 13, "KeyType 6", "always (fn 0x03a15e54)"),
)


def decode(blob, base, tables=TABLES):
    """Return one dict per table: VA, count, pairs and in-table duplicates."""
    rows = []
    for off, count, use, selector in tables:
        if off + 2 * count > len(blob):
            raise ValueError("table 0x%x+%d overruns %d bytes" % (off, 2 * count, len(blob)))
        pairs = [(blob[off + 2 * i], blob[off + 2 * i + 1]) for i in range(count)]
        codes = [a for a, _ in pairs]
        dups = sorted({c for c in codes if codes.count(c) > 1})
        rows.append({
            "va": base + off,
            "offset": off,
            "count": count,
            "use": use,
            "selector": selector,
            "pairs": ["%02x:%02x" % (a, b) for a, b in pairs],
            "duplicate_codes": ["%02x" % c for c in dups],
            "shadowed": len(dups) > 0,
        })
    return rows


def selftest():
    blob = bytearray(64)
    # two clean tables and one with a repeated raw code at a later index
    blob[0x00:0x06] = bytes([1, 2, 3, 4, 5, 6])
    blob[0x10:0x16] = bytes([7, 8, 9, 10, 11, 12])
    blob[0x20:0x28] = bytes([1, 2, 2, 3, 1, 4, 5, 6])
    tt = ((0x00, 3, "A", "t"), (0x10, 3, "B", "t"), (0x20, 4, "C", "t"))
    rows = decode(blob, 0x1000, tt)
    assert rows[0]["pairs"] == ["01:02", "03:04", "05:06"], rows[0]
    assert rows[1]["duplicate_codes"] == [], rows[1]
    assert rows[2]["duplicate_codes"] == ["01"], rows[2]
    assert rows[2]["pairs"][:4] == ["01:02", "02:03", "01:04", "05:06"], rows[2]
    # truncated input must fail loudly, not silently shorten a table
    try:
        decode(blob[:0x27], 0x1000, tt)
    except ValueError:
        pass
    else:
        raise AssertionError("truncated table did not fail")
    print("kep_tables selftest: 3 tables, 1 duplicate case, 1 truncation case OK")
    return 0


def run(args):
    with open(args.image, "rb") as fh:
        data = fh.read(args.read_limit)
    rom = cerom.CERom(data, args.image_start)
    mod = rom.module(MODULE)
    sections = list(rom.o32(mod))
    if len(sections) <= SEC_INDEX:
        raise SystemExit("%s has no section %d" % (MODULE, SEC_INDEX))
    s = sections[SEC_INDEX]
    init = nk_decomp.section_init(data, MODULE, SEC_INDEX, args.image_start, cache=False)
    blob = init + bytes(s["vsize"] - len(init))
    rows = decode(blob, SEC_REALADDR)
    report = {
        "schema": "osm2leaf.kep-tables/v1",
        "image": os.path.basename(args.image),
        "image_sha256": hashlib.sha256(data).hexdigest(),
        "image_start": args.image_start,
        "module": MODULE,
        "section_index": SEC_INDEX,
        "section_rva": s["rva"],
        "section_realaddr": s["realaddr"],
        "vsize": s["vsize"],
        "init_len": len(init),
        "init_sha256": hashlib.sha256(init).hexdigest(),
        "tables": rows,
    }
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        print("image %s sha256=%s" % (report["image"], report["image_sha256"][:16]))
        print("module %s sec%d rva=0x%04x realaddr=0x%08x vsize=0x%x init=%d sha256=%s"
              % (MODULE, SEC_INDEX, s["rva"], s["realaddr"], s["vsize"],
                 len(init), report["init_sha256"][:16]))
        for r in rows:
            print("VA=0x%08x n=%2d %-10s %-38s dup=%s"
                  % (r["va"], r["count"], r["use"], r["selector"],
                     ",".join(r["duplicate_codes"]) or "-"))
            print("    " + " ".join(r["pairs"]))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("image", nargs="?")
    p.add_argument("--image-start", type=lambda x: int(x, 0), default=DEFAULT_IMAGE_START)
    p.add_argument("--read-limit", type=lambda x: int(x, 0), default=128 * 1024 * 1024)
    p.add_argument("--json", action="store_true")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.image:
        p.error("image is required (or use --selftest)")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
