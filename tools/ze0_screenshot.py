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

    ze0_screenshot.py screen --monitor SOCK -o shot.png    # what the panel shows
    ze0_screenshot.py grab --monitor SOCK -o shot          # shot_0000000.png ...
    ze0_screenshot.py render vram.bin -o shot              # from a saved dump
    ze0_screenshot.py --selftest

``screen`` (M8.C1f) composes the display unit's planes the way the DU
registers describe them (phys 0x1ff80000, plane n at +0x100 * n):
+0x00 mode (0x1000 = colour key on, 0x4000 = opaque; the pixels of both
modes are (A)RGB1555 although the registry names "565": the map land
colour 0x6f7a is light grey only as 1555), +0x04
stride (pixels), +0x10/+0x14 width/height (0 = off), +0x20 address,
+0x30/+0x34 x/y of the window in the plane, +0x48 colour key (15-bit RGB).
Higher plane numbers are drawn first, plane 1 last (on top).  The layout
is read from the firmware's register writes (EXP-2026-11-22-M8.C1f), not
from a data sheet.

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


DU_PHYS = 0x1ff80000


def hmp_words(sock_path, phys, count):
    """Read COUNT 32-bit words of guest physical memory with HMP xp."""
    out = hmp(sock_path, "xp /%dwx 0x%x" % (count, phys), settle=0.2)
    words = []
    for line in out.decode(errors="replace").splitlines():
        if ":" in line:
            head, _, rest = line.partition(":")
            try:
                int(head.strip().split()[-1], 16)
            except (ValueError, IndexError):
                continue
            words += [int(x, 16) for x in rest.split() if x.startswith("0x")]
    return words[:count]


def du_planes(regs):
    """Decode plane n from the DU register words (index = offset / 4)."""
    planes = []
    for n in (1, 2, 3, 4):
        r = lambda off: regs[(0x100 * n + off) // 4]
        mode, stride, w, h, addr = r(0x00), r(0x04), r(0x10), r(0x14), r(0x20)
        if not (w and h and addr and stride):
            continue
        planes.append({"n": n, "mode": mode, "stride": stride, "w": w, "h": h,
                       "addr": addr & 0x1fffffff, "sx": r(0x30), "sy": r(0x34),
                       "key": r(0x48) & 0x7fff})
    return planes


def compose(planes, fetch, notes=None):
    """Return 800 x 480 RGB bytes; fetch(addr, size) gives plane memory.

    A keyed plane is fetched where its window (+0x30/+0x34) points.  When that
    band holds no visible (un-keyed) pixel but another page of the plane
    (``+0x34`` points one 480-row page on) does, that page is used instead and
    a note is appended: the NK1 AUI draws into one page while the window
    register stays on the other (M8.C1t), and a strict window composition
    would show an empty plane.  A plane whose pages are both keyed is left as
    its window says.
    """
    out = bytearray(WIDTH * HEIGHT * 3)
    for p in sorted(planes, key=lambda p: -p["n"]):
        w, h = min(p["w"], WIDTH), min(p["h"], HEIGHT)
        keyed = (p["mode"] & 0xf000) == 0x1000
        base = p["addr"] + (p["sy"] * p["stride"] + p["sx"]) * 2
        data = fetch(base, ((h - 1) * p["stride"] + w) * 2)
        if keyed and not _visible(data, p, w, h):
            for page_row in (0, 2 * h):
                if page_row == p["sy"]:
                    continue
                page = p["addr"] + page_row * p["stride"] * 2
                alt = fetch(page, ((h - 1) * p["stride"] + w) * 2)
                if _visible(alt, p, w, h):
                    data = alt
                    if notes is not None:
                        notes.append("plane %d: window row %d is empty; "
                                     "showing page rows %d-%d (M8.C1t)" %
                                     (p["n"], p["sy"], page_row,
                                      page_row + h - 1))
                    break
        for y in range(h):
            row = data[y * p["stride"] * 2:(y * p["stride"] + w) * 2]
            for x, (px,) in enumerate(struct.iter_unpack("<H", row)):
                o = 3 * (y * WIDTH + x)
                if keyed and (not px & 0x8000 or (px & 0x7fff) == p["key"]):
                    continue
                out[o] = (px >> 10 & 0x1f) << 3
                out[o + 1] = (px >> 5 & 0x1f) << 3
                out[o + 2] = (px & 0x1f) << 3
    return bytes(out)


def _visible(data, p, w, h):
    """True when at least one pixel of the band survives the plane's key."""
    for y in range(h):
        row = data[y * p["stride"] * 2:(y * p["stride"] + w) * 2]
        for (px,) in struct.iter_unpack("<H", row):
            if not (not px & 0x8000 or (px & 0x7fff) == p["key"]):
                return True
    return False


def screen(sock_path, out_png):
    planes = du_planes(hmp_words(sock_path, DU_PHYS, 0x500 // 4))

    def fetch(addr, size):
        return grab(sock_path, out_png + ".bin", addr, size)

    notes = []
    rgb = compose(planes, fetch, notes)
    if os.path.exists(out_png + ".bin"):
        os.unlink(out_png + ".bin")
    with open(out_png, "wb") as f:
        f.write(png_bytes(rgb, WIDTH, HEIGHT))
    for p in planes:
        print("plane %d: mode 0x%04x %dx%d at 0x%08x stride %d window (%d,%d)"
              % (p["n"], p["mode"], p["w"], p["h"], p["addr"], p["stride"],
                 p["sx"], p["sy"]))
    for note in notes:
        print(note)
    print("%s: %d non-black pixels" % (out_png, sum(
        1 for i in range(0, len(rgb), 3) if rgb[i:i + 3] != b"\0\0\0")))


def plane_png(sock_path, n, out_png, pages=2):
    """Write plane n's buffer as it is in memory (no colour key, ``pages`` x height rows).

    M8.C1n: the AUI layer draws into plane 1, whose window register (+0x34)
    is 480 on NK1 + A, so ``screen`` shows rows 480-959 of the buffer (black)
    and drops pixels without the 1555 alpha bit.  This view shows every row.
    """
    p = {q["n"]: q for q in du_planes(hmp_words(sock_path, DU_PHYS, 0x500 // 4))}.get(n)
    if p is None:
        raise SystemExit("plane %d is off" % n)
    rows = p["h"] * pages
    data = grab(sock_path, out_png + ".bin", p["addr"], rows * p["stride"] * 2)
    os.unlink(out_png + ".bin")
    w = min(p["w"], WIDTH)
    rgb = bytearray()
    for y in range(rows):
        for (px,) in struct.iter_unpack("<H", data[y * p["stride"] * 2:(y * p["stride"] + w) * 2]):
            rgb += bytes(((px >> 10 & 0x1f) << 3, (px >> 5 & 0x1f) << 3, (px & 0x1f) << 3))
    with open(out_png, "wb") as f:
        f.write(png_bytes(bytes(rgb), w, rows))
    print("plane %d: %dx%d at 0x%08x, window (%d,%d) -> %s" % (
        n, w, rows, p["addr"], p["sx"], p["sy"], out_png))


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
        # compose: opaque plane 4 under a keyed plane 2 (key 0x03ff), 1555
        regs = [0] * (0x500 // 4)
        for n, mode, addr in ((2, 0x1002, 0x1000), (4, 0x4002, 0x2000)):
            regs[(0x100 * n) // 4] = mode
            regs[(0x100 * n + 4) // 4] = WIDTH
            regs[(0x100 * n + 0x10) // 4] = WIDTH
            regs[(0x100 * n + 0x14) // 4] = HEIGHT
            regs[(0x100 * n + 0x20) // 4] = addr
        regs[(0x248) // 4] = 0x03ff
        mem = {0x2000: struct.pack("<H", 0x7c00) * (WIDTH * HEIGHT),
               0x1000: struct.pack("<H", 0x83ff) + struct.pack("<H", 0x801f) + struct.pack("<H", 0x001f) * (WIDTH * HEIGHT - 2)}
        rgb = compose(du_planes(regs), lambda a, n: mem[a][:n])
        assert rgb[0:3] == b"\xf8\x00\x00", rgb[0:3]       # key: plane 4 shows
        assert rgb[3:6] == b"\x00\x00\xf8", rgb[3:6]       # plane 2 blue on top
        assert rgb[6:9] == b"\x7c\x00\x00" or rgb[6:9] == b"\xf8\x00\x00", rgb[6:9]  # alpha bit clear: plane 4
        # M8.C1t: a keyed plane whose window row is empty falls back to its page
        regs = [0] * (0x500 // 4)
        regs[(0x100 * 1) // 4] = 0x1002
        regs[(0x100 * 1 + 4) // 4] = WIDTH
        regs[(0x100 * 1 + 0x10) // 4] = WIDTH
        regs[(0x100 * 1 + 0x14) // 4] = HEIGHT
        regs[(0x100 * 1 + 0x20) // 4] = 0x1000
        regs[(0x100 * 1 + 0x34) // 4] = HEIGHT
        regs[(0x100 * 1 + 0x48) // 4] = 0x03ff
        page = struct.pack("<H", 0x801f) * (WIDTH * HEIGHT)
        mem = {0x1000: page, 0x1000 + HEIGHT * WIDTH * 2: struct.pack("<H", 0x83ff) * (WIDTH * HEIGHT)}
        notes = []
        rgb = compose(du_planes(regs), lambda a, n: mem[a][:n], notes)
        assert rgb[0:3] == b"\x00\x00\xf8", rgb[0:3]    # page 0 blue, not the empty window
        assert len(notes) == 1 and "window row 480" in notes[0], notes
        notes = []
        rgb = compose(du_planes(regs), lambda a, n: struct.pack("<H", 0x801f) * (WIDTH * HEIGHT), notes)
        assert notes == [] and rgb[0:3] == b"\x00\x00\xf8", (notes, rgb[0:3])
        # the drawn page may be the second one: window on page 0, content on page 1
        regs[(0x100 * 1 + 0x34) // 4] = 0
        mem2 = {0x1000: struct.pack("<H", 0x83ff) * (WIDTH * HEIGHT),
                0x1000 + HEIGHT * WIDTH * 2: struct.pack("<H", 0x83ff) * (WIDTH * HEIGHT),
                0x1000 + HEIGHT * WIDTH * 4: page}
        notes = []
        rgb = compose(du_planes(regs), lambda a, n: mem2[a][:n], notes)
        assert rgb[0:3] == b"\x00\x00\xf8", rgb[0:3]
        assert len(notes) == 1 and "showing page rows 960-1439" in notes[0], notes
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
    c = sub.add_parser("screen", help="compose the DU planes into one 800x480 PNG")
    c.add_argument("--monitor", required=True, help="HMP unix socket path")
    c.add_argument("-o", "--out", required=True, help="PNG file")
    pl = sub.add_parser("plane", help="one plane's buffer as stored, all pages (M8.C1n)")
    pl.add_argument("--monitor", required=True, help="HMP unix socket path")
    pl.add_argument("-n", type=int, default=1, help="plane number (default 1, the AUI layer)")
    pl.add_argument("--pages", type=int, default=2)
    pl.add_argument("-o", "--out", required=True, help="PNG file")
    r = sub.add_parser("render", help="render a saved VRAM dump")
    r.add_argument("dump")
    r.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return 0
    if a.cmd == "screen":
        screen(a.monitor, a.out)
        return 0
    if a.cmd == "plane":
        plane_png(a.monitor, a.n, a.out, a.pages)
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
