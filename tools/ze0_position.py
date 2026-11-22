#!/usr/bin/env python3
"""Read the navigation's current position from a QEMU ``ze0`` guest (M8.H29).

The live car-position word is a little-endian u32 at guest VA ``0x00d940e4``
(EU2011) or ``0x00cc1ce4`` (US2011), written after start by object-store event
handlers ``0x003f6b1c`` (sub 11) and ``0x00403564`` (sub 6) in ``Navi.exe``.
The same word is used by ``tools/datask_l3.py`` and ``tools/position_store_l3.py``.

    word = (lat_code << 16) | lon_code
    lat  = (lat_code - 32768) / 192.0      # 1/192 degree, ~600 m
    lon  = (lon_code - 52742) / 128.0      # 1/128 degree

Usage:
  ze0_position.py read --monitor SOCK [--va VA] [--build EU2011|US2011] [--json]
  ze0_position.py read --file IMAGE --offset OFFSET [--build ...]
  ze0_position.py decode WORD [--build ...]
  ze0_position.py encode LAT LON [--build ...]
  ze0_position.py --selftest

``--monitor SOCK`` is the HMP unix socket created by ``tools/qemu-ze0/run.sh``.
The selftest uses a synthetic 256 KiB memory image, not vendor bytes.

Method and results: docs/experiments/EXP-2026-11-22-M8.H29-fix-to-map.md
"""

import argparse
import json
import os
import re
import socket
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from coord import decode_position_word, position_word  # noqa: E402

EU_VA = 0x00D940E4
US_VA = 0x00CC1CE4
ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")


def va_for(build):
    return US_VA if build.upper() == "US2011" else EU_VA


def decode(word, build="EU2011"):
    """Return (lat, lon, raw word); raises for an out-of-range grid code."""
    lat, lon = decode_position_word(word)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("position word 0x%08x is outside the grid" % word)
    return lat, lon, word


def hmp_command(sock_path, command, timeout=5.0):
    """Send one HMP command and return the text reply without ANSI echoes."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(sock_path)
        sock.sendall((command + "\n").encode())
        data = bytearray()
        while True:
            try:
                part = sock.recv(4096)
            except socket.timeout:
                break
            if not part:
                break
            data.extend(part)
    return ANSI.sub("", data.decode("utf-8", "replace"))


def parse_x_reply(text):
    """Parse the first ``ADDR: 0xWORD`` line of an HMP ``x /1wx`` reply.

    Deliberately refuses a reply with no word, so a monitor that did not
    answer cannot be mistaken for a valid position.
    """
    for line in text.replace("\r", "").split("\n"):
        m = re.search(r":\s+0x([0-9a-fA-F]{1,8})\b", line)
        if m:
            return int(m.group(1), 16)
    raise ValueError("no word in HMP reply: %r" % text[:200])


def gdb_word(port, va):
    """Read 4 bytes of guest *virtual* memory through the QEMU gdbstub.

    HMP ``x`` can answer ``Cannot access memory`` for a user-mode VA when the
    CPU is in another context; the RSP ``m`` packet uses the current guest MMU
    and is the reliable route for Navi.exe's 0x00d940e4.
    """
    import ze0_dbgmsg
    rsp = ze0_dbgmsg.Rsp(port)
    payload = rsp.cmd("m%x,%x" % (va, 4))
    if payload.startswith("E") or len(payload) < 8:
        raise ValueError("gdbstub could not read 0x%08x: %r" % (va, payload[:40]))
    return struct.unpack("<I", bytes.fromhex(payload[:8]))[0]


def read_word(args):
    if args.file:
        with open(args.file, "rb") as fh:
            fh.seek(args.offset)
            data = fh.read(4)
        if len(data) != 4:
            raise ValueError("short read at 0x%x of %s" % (args.offset, args.file))
        word = struct.unpack("<I", data)[0]
    elif args.gdb:
        word = gdb_word(args.gdb, args.va)
    else:
        if not args.monitor:
            raise ValueError("need --monitor SOCK, --gdb PORT or --file IMAGE")
        text = hmp_command(args.monitor, "x /1wx 0x%08x" % args.va)
        word = parse_x_reply(text)
    return word


def cmd_read(args):
    word = read_word(args)
    lat, lon, word = decode(word, args.build)
    result = {"va": "0x%08x" % args.va, "word": "0x%08x" % word,
              "lat": round(lat, 6), "lon": round(lon, 6),
              "resolution_deg": 1.0 / 192.0}
    if args.json:
        print(json.dumps(result))
    else:
        print("position 0x%08x: lat %.6f  lon %.6f  (word 0x%08x)" %
              (args.va, lat, lon, word))
    return 0


def selftest():
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" %
              ("ok  " if ok else "FAIL", label, got, want))

    # Synthetic memory: a 256 KiB image with the exact grid point at the EU VA.
    word = position_word(51.0, 17.0)
    check("encoded word", "0x%08x" % word, "0xa640d686")
    with tempfile.TemporaryDirectory(prefix="ze0-position-") as td:
        path = os.path.join(td, "mem.bin")
        with open(path, "wb") as fh:
            fh.write(b"\x00" * EU_VA + struct.pack("<I", word))
        args = argparse.Namespace(file=path, offset=EU_VA, monitor=None,
                                  gdb=None, build="EU2011", va=EU_VA, json=False)
        read_back = read_word(args)
        check("synthetic memory read", "0x%08x" % read_back, "0xa640d686")
        lat, lon, _ = decode(read_back)
        check("synthetic decode", (lat, lon), (51.0, 17.0))
        # Negative controls: byte-swapped and truncated images must not pass.
        with open(path, "wb") as fh:
            fh.write(b"\x00" * EU_VA + struct.pack(">I", word))
        swapped = read_word(args)
        # A byte swap must not still decode to the injected point.
        try:
            back = decode(swapped)[:2] != (51.0, 17.0)
        except ValueError:
            back = True
        check("byte swap changes position", back, True)
        with open(path, "wb") as fh:
            fh.write(b"\x00" * EU_VA + b"\x86\xd6\x40")
        try:
            read_word(args)
            check("short memory rejected", False, True)
        except ValueError:
            check("short memory rejected", True, True)

    # HMP reply parsing, including the terminal echo QEMU sends on a fresh
    # socket and the prompt; a reply without a word is an error.
    reply = ("QEMU 11.1.3 monitor\r\n(qemu) x/refx/1wx 0x00d940e4\r\n"
             "0000000000d940e4: 0xa640d686\r\n(qemu) ")
    check("parse HMP word", "0x%08x" % parse_x_reply(reply), "0xa640d686")
    try:
        parse_x_reply("(qemu) ")
        check("empty HMP reply refused", False, True)
    except ValueError:
        check("empty HMP reply refused", True, True)

    # One-degree grid points round-trip exactly; arbitrary points are within
    # half a cell. US VA is a different address but the same encoding.
    check("US VA", "0x%08x" % va_for("US2011"), "0x00cc1ce4")
    for lat, lon in ((0, 0), (51, 17), (-5, 60), (60, -5)):
        got = decode(position_word(lat, lon))
        check("grid round-trip %d,%d" % (lat, lon),
              (round(got[0], 4), round(got[1], 4)), (float(lat), float(lon)))
    w = position_word(51.7, 17.45)
    got = decode(w)
    check("arbitrary point within a cell",
          abs(got[0] - 51.7) <= 1 / 192.0 and
          abs(got[1] - 17.45) <= 1 / 128.0, True)
    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("read", help="read the live position word")
    src = r.add_mutually_exclusive_group(required=False)
    src.add_argument("--monitor", help="HMP unix socket of run.sh")
    src.add_argument("--gdb", type=int, metavar="PORT",
                     help="gdbstub TCP port (virtual read; use when HMP x fails)")
    src.add_argument("--file", help="synthetic/frozen memory image")
    r.add_argument("--offset", type=lambda s: int(s, 0), default=EU_VA)
    r.add_argument("--va", type=lambda s: int(s, 0), default=None)
    r.add_argument("--build", choices=["EU2011", "US2011"], default="EU2011")
    r.add_argument("--json", action="store_true")
    d = sub.add_parser("decode")
    d.add_argument("word", type=lambda s: int(s, 0))
    d.add_argument("--build", choices=["EU2011", "US2011"], default="EU2011")
    e = sub.add_parser("encode")
    e.add_argument("lat", type=float)
    e.add_argument("lon", type=float)
    e.add_argument("--build", choices=["EU2011", "US2011"], default="EU2011")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "read":
        if args.va is None:
            args.va = va_for(args.build)
        return cmd_read(args)
    if args.cmd == "decode":
        try:
            lat, lon, word = decode(args.word, args.build)
        except ValueError as exc:
            print("decode: %s" % exc, file=sys.stderr)
            return 1
        print("0x%08x: lat %.6f lon %.6f" % (word, lat, lon))
        return 0
    if args.cmd == "encode":
        print("0x%08x" % position_word(args.lat, args.lon))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
