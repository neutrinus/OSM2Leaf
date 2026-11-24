#!/usr/bin/env python3
"""M5.83 evidence helper: crop a PNG and count changed pixels between crops.

Standard-library only; no PIL.  Reads/writes 8-bit RGB PNG (the format
``tools/ze0_screenshot.py`` emits).  Used to make a deterministic crop of the
L4 screenshot and to show that the crop comparison can detect a planted
substitution (negative control).

Commands
    m583_evidence.py crop SRC DST --box x0,y0,x1,y1
    m583_evidence.py diff A B          # prints changed_pixels=N
    m583_evidence.py --selftest        # synthetic PNG round-trip + diff control
"""
from __future__ import annotations

import argparse
import os
import struct
import tempfile
import zlib


def read_png(path):
    data = open(path, "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    idat = b""
    w = h = 0
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h = struct.unpack(">II", body[:8])
        elif typ == b"IDAT":
            idat += body
        pos += 12 + ln
    raw = zlib.decompress(idat)
    stride = w * 3
    rows = []
    prev = bytearray(stride)
    i = 0
    for _ in range(h):
        ft = raw[i]
        i += 1
        cur = bytearray(raw[i:i + stride])
        i += stride
        for x in range(stride):
            a = cur[x - 3] if x >= 3 else 0
            b = prev[x]
            c = prev[x - 3] if x >= 3 else 0
            if ft == 1:
                cur[x] = (cur[x] + a) & 0xff
            elif ft == 2:
                cur[x] = (cur[x] + b) & 0xff
            elif ft == 3:
                cur[x] = (cur[x] + ((a + b) // 2)) & 0xff
            elif ft == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                cur[x] = (cur[x] + pr) & 0xff
        rows.append(bytes(cur))
        prev = cur
    return w, h, rows


def write_png(path, w, h, rows):
    out = bytearray(b"\x89PNG\r\n\x1a\n")

    def chunk(typ, body):
        return struct.pack(">I", len(body)) + typ + body + struct.pack(">I", zlib.crc32(typ + body) & 0xffffffff)

    out += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    raw = b"".join(b"\x00" + row for row in rows)
    out += chunk(b"IDAT", zlib.compress(raw, 6))
    out += chunk(b"IEND", b"")
    open(path, "wb").write(out)


def crop(rows, x0, y0, x1, y1):
    return [row[x0 * 3:x1 * 3] for row in rows[y0:y1]]


def diff(a, b):
    if len(a) != len(b):
        return None
    return sum(1 for ra, rb in zip(a, b) for x, y in zip(ra, rb) if x != y)


def selftest():
    w = h = 8
    rows = [bytes((x * 3 + y) % 256 for x in range(w * 3)) for y in range(h)]
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "a.png")
        write_png(p, w, h, rows)
        assert read_png(p) == (w, h, rows)
        c = crop(rows, 2, 2, 6, 6)
        assert len(c) == 4 and len(c[0]) == 12
        assert diff(c, c) == 0
        planted = [bytearray(r) for r in c]
        planted[0][0] = (planted[0][0] + 1) & 0xff
        assert diff(c, [bytes(r) for r in planted]) == 1
    print("selftest: OK (PNG round-trip, crop, diff control: 0 vs 1)")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    c = sub.add_parser("crop")
    c.add_argument("src")
    c.add_argument("dst")
    c.add_argument("--box", required=True, help="x0,y0,x1,y1")
    d = sub.add_parser("diff")
    d.add_argument("a")
    d.add_argument("b")
    a = p.parse_args()
    if a.selftest:
        return selftest()
    if a.cmd == "crop":
        x0, y0, x1, y1 = map(int, a.box.split(","))
        w, h, rows = read_png(a.src)
        sub_rows = crop(rows, x0, y0, x1, y1)
        write_png(a.dst, x1 - x0, y1 - y0, sub_rows)
        print("crop %s box=(%d,%d,%d,%d) size=%dx%d" % (a.dst, x0, y0, x1, y1, x1 - x0, y1 - y0))
        return 0
    if a.cmd == "diff":
        _, _, ra = read_png(a.a)
        _, _, rb = read_png(a.b)
        print("changed_pixels=%s" % diff(ra, rb))
        return 0
    p.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
