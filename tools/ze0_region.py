#!/usr/bin/env python3
"""Named-region SHA-256 of a ``ze0_screenshot.py plane -n 1`` PNG (M8.H39).

The ZOOM widget of the NK1 AUI blinks, so a whole-frame PNG hash is not
stable across two boots.  This tool hashes a named region of the plane-1
page.  Default region is the scale label (screen x 700..799, y 240..299),
where ZOOM IN changes ``1/16mi`` to ``1/8mi``.  ``--mask-from`` builds a mask
of pixels that differ between an idle and a tap PNG but not between an
empty-area pair (the falsifier control), so the same mask is used for all
comparisons.  ``--selftest`` exercises the PNG reader and hash on a tiny
synthetic image.

Usage:
  ze0_region.py --mask-from IDLE.png TAP.png EMPTY_BEFORE.png EMPTY_AFTER.png \\
      --hash IDLE.png TAP.png EMPTY_BEFORE.png EMPTY_AFTER.png
  ze0_region.py --selftest

Stdlib only.  Claims C-10092-C-10095;
method and results in EXP-2026-11-24-M8.H39-tap-l4.
"""

import argparse
import hashlib
import struct
import sys
import zlib

REGION = (700, 800, 240, 300)


def png_rgb(path):
    """Return (width, height, rows) of an 8-bit RGB PNG (no interlace)."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("%s: not a PNG" % path)
    i, idat, w, h, depth, colour = 8, b"", 0, 0, 0, 0
    while i + 12 <= len(data):
        n = struct.unpack(">I", data[i:i + 4])[0]
        kind = data[i + 4:i + 8]
        payload = data[i + 8:i + 8 + n]
        i += 12 + n
        if kind == b"IHDR":
            w, h, depth, colour = struct.unpack(">IIBB", payload[:10])
            if depth != 8 or colour != 2:
                raise ValueError("%s: expected 8-bit RGB" % path)
        elif kind == b"IDAT":
            idat += payload
        elif kind == b"IEND":
            break
    raw = zlib.decompress(idat)
    stride = w * 3
    rows = []
    for y in range(h):
        base = y * (stride + 1)
        if raw[base] != 0:
            raise ValueError("%s: unsupported PNG filter" % path)
        rows.append(raw[base + 1:base + 1 + stride])
    return w, h, rows


def pixel(rows, x, y):
    return rows[y][3 * x:3 * x + 3]


def build_mask(idle, tap, empty_before, empty_after, region=REGION):
    """Pixels changing idle->tap but stable under the empty-area tap."""
    x0, x1, y0, y1 = region
    return [(x, y) for y in range(y0, y1) for x in range(x0, x1)
            if pixel(idle[2], x, y) != pixel(tap[2], x, y)
            and pixel(empty_before[2], x, y) == pixel(empty_after[2], x, y)]


def region_hash(rows, mask):
    return hashlib.sha256(b"".join(pixel(rows, x, y) for x, y in mask)).hexdigest()


def _synthetic_png():
    """8x8 RGB PNG with one red pixel at (3,3)."""
    width = height = 8
    rows = [b"\x00\x00\x00" * width for _ in range(height)]
    rows[3] = b"\x00\x00\x00" * 3 + b"\xff\x00\x00" + b"\x00\x00\x00" * 4
    raw = b"".join(b"\x00" + r for r in rows)
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data +
                struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def selftest():
    import io
    import os
    import tempfile

    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))

    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "s.png")
        with open(p, "wb") as f:
            f.write(_synthetic_png())
        w, h, rows = png_rgb(p)
        check("size", (w, h), (8, 8))
        check("red pixel", pixel(rows, 3, 3), b"\xff\x00\x00")
        check("black pixel", pixel(rows, 0, 0), b"\x00\x00\x00")
        check("region hash", region_hash(rows, [(3, 3)]),
              hashlib.sha256(b"\xff\x00\x00").hexdigest())
        check("mask count",
              len(build_mask((0, 0, rows), (0, 0, rows),
                             (0, 0, rows), (0, 0, rows), (0, 8, 0, 8))), 0)
    print("ze0_region selftest: %s (%d failure(s))" %
          ("OK" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mask-from", nargs=4, metavar=("IDLE", "TAP", "EMPTY0", "EMPTY1"))
    ap.add_argument("--x0", type=int, default=REGION[0])
    ap.add_argument("--x1", type=int, default=REGION[1])
    ap.add_argument("--y0", type=int, default=REGION[2])
    ap.add_argument("--y1", type=int, default=REGION[3])
    ap.add_argument("--hash", nargs="+", metavar="PNG")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.hash:
        ap.error("give --hash PNG [PNG ...]")
    region = (a.x0, a.x1, a.y0, a.y1)
    if a.mask_from:
        imgs = [png_rgb(p) for p in a.mask_from]
        mask = build_mask(*imgs, region=region)
        print("mask pixels: %d" % len(mask))
    else:
        mask = [(x, y) for y in range(region[2], region[3])
                for x in range(region[0], region[1])]
    for p in a.hash:
        print("%s  %s" % (region_hash(png_rgb(p)[2], mask), p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
