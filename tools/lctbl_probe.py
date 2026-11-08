#!/usr/bin/env python3
"""LCTBL001 reader precheck and probe (M3.15).

Answers three questions for the M3.15 record-walk / string-decode search, using
only VAs produced by tools/cerom.py (no fitted deltas):

  --va VA [VA ...]   which section holds each VA, and is that section
                     COMPRESSED in the image? Plain VAs also print 16 bytes.
  --expect-ascii VA TEXT
                     positive control: TEXT must be stored as bytes at VA in
                     decodable (plain) bytes. Proves the VA-to-bytes mapping.
  --scan-inflate     zlib's inflate length-base table (lbase, little-endian
                     u16, 29 entries from 3 to 258 as in zlib inftrees.c) is
                     searched in the plain sections of every module. A
                     table-driven zlib decoder carries it; a hit is a candidate
                     decoder, no hit means none in the decodable bytes.

Stdlib only. Method and results: docs/experiments/EXP-2026-11-08-M3.15-lctbl-reader.md

Usage:
  lctbl_probe.py IMG --image-start 0x200200 --module Navi.exe \
      --va 0x0055d924 0x004125a8 --expect-ascii 0x0017a1f8 LCTBL001.DAT
  lctbl_probe.py IMG --image-start 0x200200 --scan-inflate
  lctbl_probe.py --selftest
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cerom  # noqa: E402

# zlib inftrees.c lbase[] (length codes 257..285), as the decoder stores it.
ZLIB_LBASE = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31,
              35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258]
LBASE_LE = struct.pack("<%dH" % len(ZLIB_LBASE), *ZLIB_LBASE)


def scan_inflate_table(blob):
    """Offsets of the little-endian lbase table inside blob."""
    hits, i = [], blob.find(LBASE_LE)
    while i != -1:
        hits.append(i)
        i = blob.find(LBASE_LE, i + 1)
    return hits


def classify_va(sections, va):
    """Return the section dict that holds va, or None. sections: dicts with
    realaddr, vsize, flags (as cerom.o32 yields them)."""
    for s in sections:
        if s["realaddr"] <= va < s["realaddr"] + s["vsize"]:
            return s
    return None


def is_compressed(section):
    return bool(section["flags"] & cerom.IMAGE_SCN_COMPRESSED)


def load_sections(data, rom, module_name):
    m = rom.module(module_name)
    return [dict(s, file_off=rom.va2file(s["dataptr"])) for s in rom.o32(m)]


def plain_blob(data, s):
    return data[s["file_off"]:s["file_off"] + s["psize"]]


def run(img, image_start, module, vas, expect, scan):
    with open(img, "rb") as fh:
        data = fh.read(128 << 20)
    rom = cerom.CERom(data, image_start)
    secs = load_sections(data, rom, module)
    print("module %s: %d sections" % (module, len(secs)))
    for s in secs:
        print("  realaddr=%08x vsize=%08x flags=%08x %s" % (
            s["realaddr"], s["vsize"], s["flags"],
            "COMPRESSED" if is_compressed(s) else "plain"))
    rc = 0
    for va in vas:
        s = classify_va(secs, va)
        if s is None:
            print("VA %08x: no section" % va)
            rc = 1
            continue
        tag = "COMPRESSED" if is_compressed(s) else "plain"
        line = "VA %08x: section %08x (%s)" % (va, s["realaddr"], tag)
        if not is_compressed(s):
            off = s["file_off"] + (va - s["realaddr"])
            line += " bytes=%s" % data[off:off + 16].hex()
        print(line)
    if expect:
        va, text = expect
        s = classify_va(secs, va)
        if s is None or is_compressed(s):
            print("positive control: VA %08x not in plain bytes" % va)
            rc = 1
        else:
            off = s["file_off"] + (va - s["realaddr"])
            got = data[off:off + len(text)]
            ok = got == text.encode("ascii")
            print("positive control: VA %08x holds %r -> %s" % (
                va, got.decode("latin-1"), "OK" if ok else "MISMATCH"))
            rc = rc if ok else 1
    if scan:
        total_secs = total_plain = total_bytes = 0
        hits = []
        for m in rom.modules():
            name = m["name"]
            if not name:
                continue
            for s in rom.o32(m):
                total_secs += 1
                if is_compressed(s):
                    continue
                total_plain += 1
                off = rom.va2file(s["dataptr"])
                blob = data[off:off + s["psize"]]
                total_bytes += len(blob)
                for h in scan_inflate_table(blob):
                    hits.append((name, s["realaddr"], h))
        print("inflate scan: modules=%d sections=%d plain_sections=%d plain_bytes=%d"
              % (len(list(rom.modules())), total_secs, total_plain, total_bytes))
        print("inflate scan hits: %d" % len(hits))
        for name, real, h in hits:
            print("  %s section %08x offset %x" % (name, real, h))
    return rc


def _synthetic():
    table = LBASE_LE
    with_table = b"\x00" * 37 + table + b"\xff" * 11
    without = b"\x00" * 37 + b"\x01\x02" * 40
    secs = [dict(realaddr=0x11000, vsize=0x1000, flags=0x68000020),
            dict(realaddr=0x55d000, vsize=0x2000, flags=0xc8002040)]
    return with_table, without, secs


def selftest():
    with_table, without, secs = _synthetic()
    # positive control: the table is found at its planted offset
    assert scan_inflate_table(with_table) == [37], scan_inflate_table(with_table)
    # negative control: no table in unrelated bytes
    assert scan_inflate_table(without) == []
    # big-endian layout must not match: the probe reads LE only
    assert scan_inflate_table(struct.pack(">29H", *ZLIB_LBASE)) == []
    # VA classification: plain section, compressed section, and a gap
    assert classify_va(secs, 0x0011000 + 5)["realaddr"] == 0x11000
    assert is_compressed(classify_va(secs, 0x0055d924))
    assert classify_va(secs, 0x0040000) is None
    print("lctbl_probe selftest: OK (5 synthetic asserts: 2 scan controls, BE negative, 3 VA classes)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?")
    ap.add_argument("--image-start", type=lambda s: int(s, 0), default=None)
    ap.add_argument("--module", default="Navi.exe")
    ap.add_argument("--va", nargs="*", default=[], type=lambda s: int(s, 0))
    ap.add_argument("--expect-ascii", nargs=2, metavar=("VA", "TEXT"), default=None)
    ap.add_argument("--scan-inflate", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.image:
        ap.error("IMG is required (or --selftest)")
    expect = None
    if a.expect_ascii:
        expect = (int(a.expect_ascii[0], 0), a.expect_ascii[1])
    return run(a.image, a.image_start, a.module, a.va, expect, a.scan_inflate)


if __name__ == "__main__":
    sys.exit(main())
