#!/usr/bin/env python3
"""Save the head unit's screen memory from a running ``-M ze0`` guest as PNG.

The display driver (``gdisubdrv.dll``) reports ``VRAM Base >> AE700000`` and
``VRAM Size >> 01860000`` on the serial log, and the registry asks for an
800 x 480 panel with 16-bit RGB565 layers (``System\\Automotive\\Graphic``,
``DDDDIFull\\FourCC = "565"``).  This tool asks QEMU's HMP monitor for the
VRAM (``pmemsave``), then writes one PNG per 800 x 480 frame-sized block
that holds non-zero pixels, so the first layer that something draws into
shows up without knowing its offset in advance.

Start QEMU with ``-monitor unix:SOCK,server,nowait``, then::

    ze0_screenshot.py grab --monitor SOCK -o shot          # shot_0000000.png ...
    ze0_screenshot.py render vram.bin -o shot              # from a saved dump
    ze0_screenshot.py --selftest

Exit status 0 and "no non-zero pixel" when nothing has been drawn yet.
"""
import argparse
import os
import socket
import struct
import sys
import tempfile
import time
import zlib

VRAM_PHYS = 0x0e700000
VRAM_SIZE = 0x01860000
WIDTH, HEIGHT = 800, 480
FRAME = WIDTH * HEIGHT * 2


def hmp(sock_path, command, settle=1.0, timeout=60.0):
    """Send one HMP command and wait until the monitor prompt returns."""
    s = socket.socket(socket.AF_UNIX)
    s.settimeout(timeout)
    s.connect(sock_path)
    buf = b""
    deadline = time.time() + timeout
    while b"(qemu)" not in buf and time.time() < deadline:
        buf += s.recv(65536)
    s.sendall(command.encode() + b"\n")
    buf = b""
    while buf.count(b"(qemu)") < 1 and time.time() < deadline:
        chunk = s.recv(65536)
        if not chunk:
            break
        buf += chunk
    time.sleep(settle)
    s.close()
    return buf


def png_bytes(rgb, width, height):
    """Minimal PNG writer (8-bit RGB, no external modules)."""
    raw = b"".join(b"\0" + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))

    def chunk(kind, data):
        c = struct.pack(">I", len(data)) + kind + data
        return c + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def rgb565_to_rgb(frame):
    out = bytearray(len(frame) // 2 * 3)
    for i, (px,) in enumerate(struct.iter_unpack("<H", frame)):
        out[3 * i] = (px >> 11 & 0x1f) << 3
        out[3 * i + 1] = (px >> 5 & 0x3f) << 2
        out[3 * i + 2] = (px & 0x1f) << 3
    return bytes(out)


def render(data, prefix, limit=8):
    """Write a PNG for each frame-sized block with a non-zero byte."""
    written = []
    for off in range(0, len(data) - FRAME + 1, FRAME):
        block = data[off:off + FRAME]
        if not any(block):
            continue
        name = "%s_%07x.png" % (prefix, off)
        with open(name, "wb") as f:
            f.write(png_bytes(rgb565_to_rgb(block), WIDTH, HEIGHT))
        written.append((off, name, len(block) - block.count(0)))
        if len(written) >= limit:
            break
    return written


def grab(sock_path, out_bin, phys=VRAM_PHYS, size=VRAM_SIZE):
    out_bin = os.path.abspath(out_bin)
    if os.path.exists(out_bin):
        os.unlink(out_bin)
    hmp(sock_path, 'pmemsave 0x%x 0x%x "%s"' % (phys, size, out_bin))
    for _ in range(100):
        if os.path.exists(out_bin) and os.path.getsize(out_bin) == size:
            break
        time.sleep(0.2)
    with open(out_bin, "rb") as f:
        return f.read()


def report(written, total):
    if not written:
        print("no non-zero pixel in %d bytes of VRAM" % total)
    for off, name, nz in written:
        print("VRAM +0x%07x: %s (%d non-zero bytes)" % (off, name, nz))


def selftest():
    frame = bytearray(FRAME)
    frame[0:2] = struct.pack("<H", 0xf800)          # red pixel
    data = bytes(FRAME) + bytes(frame)
    with tempfile.TemporaryDirectory() as d:
        w = render(data, os.path.join(d, "t"))
        assert len(w) == 1 and w[0][0] == FRAME, w
        png = open(w[0][1], "rb").read()
        assert png.startswith(b"\x89PNG") and b"IEND" in png
        assert rgb565_to_rgb(struct.pack("<H", 0xf800)) == b"\xf8\x00\x00"
        assert render(bytes(FRAME), os.path.join(d, "z")) == []
    print("ze0_screenshot selftest: ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    g = sub.add_parser("grab", help="pmemsave the VRAM of a running guest and render it")
    g.add_argument("--monitor", required=True, help="HMP unix socket path")
    g.add_argument("-o", "--out", required=True, help="PNG name prefix")
    g.add_argument("--phys", type=lambda s: int(s, 0), default=VRAM_PHYS)
    g.add_argument("--size", type=lambda s: int(s, 0), default=VRAM_SIZE)
    g.add_argument("--keep-bin", action="store_true", help="keep PREFIX.vram.bin")
    r = sub.add_parser("render", help="render a saved VRAM dump")
    r.add_argument("dump")
    r.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return 0
    if a.cmd == "grab":
        binpath = a.out + ".vram.bin"
        data = grab(a.monitor, binpath, a.phys, a.size)
        if not a.keep_bin:
            os.unlink(binpath)
    elif a.cmd == "render":
        data = open(a.dump, "rb").read()
    else:
        ap.error("command required")
    report(render(data, a.out), len(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
