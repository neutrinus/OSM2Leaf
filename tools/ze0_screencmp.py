#!/usr/bin/env python3
"""Compare a QEMU screendump (PPM P6) with a ze0_screenshot.py PNG, pixel by pixel.

M8.H4 exposes the DU planes as a QEMU graphic console, so HMP
``screendump FILE ze0-gfx`` and ``ze0_screenshot.py screen`` should show the
same frame at the same instant.  This tool is that comparison: it reads an
8-bit RGB P6 PPM (what ``screendump`` writes without libpng) and an 8-bit
RGB PNG (what ``ze0_screenshot.py png_bytes()`` writes, filter type 0) and
prints the count of differing pixels and the first one.

    python3 tools/ze0_screencmp.py shot.ppm host.png   # 0 equal, 1 differ
    python3 tools/ze0_screencmp.py --selftest

Exit codes: 0 pixel-identical, 1 differ, 2 unsupported/invalid input.
"""
import argparse
import struct
import sys
import zlib


def read_ppm(data):
    if not data.startswith(b"P6"):
        raise ValueError("not a P6 PPM")
    fields, i = [], 2
    while len(fields) < 3:
        while i < len(data) and data[i:i + 1].isspace():
            i += 1
        if data[i:i + 1] == b"#":
            while i < len(data) and data[i:i + 1] != b"\n":
                i += 1
            continue
        start = i
        while i < len(data) and not data[i:i + 1].isspace():
            i += 1
        fields.append(int(data[start:i]))
    i += 1
    w, h, maxval = fields
    if maxval != 255:
        raise ValueError("maxval %d != 255" % maxval)
    px = data[i:i + w * h * 3]
    if len(px) != w * h * 3:
        raise ValueError("short PPM payload")
    return w, h, px


def read_png(data):
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG")
    i, idat, w, h, bpp, ctype = 8, b"", 0, 0, 0, 0
    while i + 8 <= len(data):
        n = struct.unpack(">I", data[i:i + 4])[0]
        kind = data[i + 4:i + 8]
        body = data[i + 8:i + 8 + n]
        i += 12 + n
        if kind == b"IHDR":
            w, h, bpp, ctype = struct.unpack(">IIBB", body[:10])
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
    if bpp != 8 or ctype != 2:
        raise ValueError("PNG is not 8-bit RGB")
    raw = zlib.decompress(idat)
    stride = w * 3
    out = bytearray()
    prev = bytearray(stride)
    for y in range(h):
        base = y * (stride + 1)
        f = raw[base]
        line = bytearray(raw[base + 1:base + 1 + stride])
        if f == 0:
            pass
        elif f == 1:
            for x in range(3, stride):
                line[x] = (line[x] + line[x - 3]) & 0xff
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 0xff
        else:
            raise ValueError("PNG filter %d unsupported" % f)
        out += line
        prev = line
    return w, h, bytes(out)


def compare(ppm, png):
    pw, ph, ppx = read_ppm(ppm)
    nw, nh, npx = read_png(png)
    if (pw, ph) != (nw, nh):
        raise ValueError("size %dx%d != %dx%d" % (pw, ph, nw, nh))
    diff = n = 0
    first = None
    for k in range(0, len(ppx), 3):
        if ppx[k:k + 3] != npx[k:k + 3]:
            diff += 1
            if first is None:
                p = k // 3
                first = (p % pw, p // pw, ppx[k:k + 3].hex(), npx[k:k + 3].hex())
        if ppx[k:k + 3] != b"\0\0\0":
            n += 1
    return pw, ph, diff, n, first


def selftest():
    w, h = 4, 3
    a = bytes([0, 0, 0, 1, 2, 3, 255, 255, 255] * (w * h // 3))
    ppm = b"P6\n%d %d\n255\n" % (w, h) + a

    def png(rgb):
        raw = b"".join(b"\0" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))
        def chunk(kind, body):
            return (struct.pack(">I", len(body)) + kind + body +
                    struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff))
        return (b"\x89PNG\r\n\x1a\n" +
                chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
                chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))

    _, _, diff, n, _ = compare(ppm, png(a))
    assert diff == 0 and n == 8, (diff, n)
    bad = bytearray(a)
    bad[4] ^= 0xff
    _, _, diff, _, first = compare(ppm, png(bytes(bad)))
    assert diff == 1 and first[:2] == (1, 0), (diff, first)
    for blob in (b"P5\n1 1\n255\n\0", b"nope"):
        try:
            read_ppm(blob)
            raise AssertionError("read_ppm accepted %r" % blob)
        except (ValueError, IndexError):
            pass
    print("ze0_screencmp selftest: ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("ppm", nargs="?")
    ap.add_argument("png", nargs="?")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return 0
    if not (a.ppm and a.png):
        ap.error("need a PPM and a PNG (or --selftest)")
    try:
        w, h, diff, n, first = compare(open(a.ppm, "rb").read(),
                                       open(a.png, "rb").read())
    except (ValueError, OSError) as exc:
        print("ze0_screencmp: %s" % exc)
        return 2
    print("%dx%d: %d differing pixels, %d non-black; first %s" %
          (w, h, diff, n, "-" if first is None else
           "(%d,%d) ppm=%s png=%s" % first))
    return 0 if diff == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
