#!/usr/bin/env python3
"""Print the EU2011 kernel's debug messages from a QEMU ``-M ze0`` boot (TODO M8.B5).

EU2011 ``nk.exe`` never writes its debug text to a UART (M8.A6, C-1281): every
``NKDbgPrintfW`` ends in ``fn 0x880404f4`` with the formatted wide string in
``r4``, which only goes to an AstLog buffer.  This tool is a small GDB
remote-protocol client (stdlib only, no SH-capable gdb needed): it starts
QEMU with ``-gdb``/``-S``, puts breakpoints on hook addresses, and at each hit
reads a register and, for a string hook, the string it points to, then
continues.  The guest sees the breakpoints only as lost host time (with
``-icount`` its virtual time does not move while stopped).

Hook syntax ``VA:REG:KIND``: KIND ``w`` = NUL-terminated UTF-16 string at
REG, ``a`` = ASCII string at REG, ``x`` = the register value only.  The
default hook is ``0x880404f4:r4:w`` (EU2011 debug-string sink).  ``--count``
hooks are only counted, never printed.

``modules DUMP --dump-va VA IMAGE`` lists the ROM modules (TOC entries of
the CE image at ``--image-start``) whose TOC-entry address appears as a
word in a RAM dump (HMP ``pmemsave``): the CE 5 kernel keeps that pointer
in each loaded process's and module's loader record, so a ``.exe`` listed
here has been started.

Usage:
  ze0_dbgmsg.py modules DUMP --dump-va 0x89e40000 IMAGE [--image-start 0x3e00200]
  ze0_dbgmsg.py run --duration 60 [--hook VA:REG:KIND ...] [--count VA ...] [--word VA ...]
                    [--dump VA:LEN:FILE ...] [-o LOG] -- QEMU-ARGV...
  ze0_dbgmsg.py --selftest

Method and results: docs/experiments/EXP-2026-11-20-M8.B5-ze0-f1-filesys.md
"""

import argparse
import os
import socket
import struct
import subprocess
import sys
import time

DEFAULT_HOOK = "0x880404f4:r4:w"
REGNAMES = ["r%d" % i for i in range(16)] + ["pc", "pr", "gbr", "vbr", "mach", "macl", "sr"]


def checksum(payload):
    return "%02x" % (sum(payload.encode("latin1")) & 0xFF)


def frame(payload):
    return "$%s#%s" % (payload, checksum(payload))


def parse_frames(buf):
    """Split a byte buffer into (list of payload strings, rest)."""
    out = []
    while True:
        i = buf.find(b"$")
        if i < 0:
            return out, b""
        j = buf.find(b"#", i)
        if j < 0 or j + 3 > len(buf):
            return out, buf[i:]
        out.append(buf[i + 1:j].decode("latin1"))
        buf = buf[j + 3:]


def parse_hook(text):
    va, reg, kind = text.split(":")
    if reg not in REGNAMES:
        raise argparse.ArgumentTypeError("unknown register %r" % reg)
    if kind not in ("w", "a", "x"):
        raise argparse.ArgumentTypeError("KIND must be w, a or x")
    return int(va, 0), reg, kind


def parse_dump(text):
    va, length, path = text.split(":", 2)
    return int(va, 0), int(length, 0), path


def regs_from_g(payload):
    vals = {}
    for i, name in enumerate(REGNAMES):
        h = payload[8 * i:8 * i + 8]
        if len(h) < 8:
            break
        vals[name] = struct.unpack("<I", bytes.fromhex(h))[0]
    return vals


def decode_str(raw, kind):
    if kind == "w":
        n = len(raw) - len(raw) % 2
        for k in range(0, n, 2):
            if raw[k:k + 2] == b"\0\0":
                n = k
                break
        return raw[:n].decode("utf-16-le", "replace")
    return raw.split(b"\0")[0].decode("latin1")


class Rsp:
    def __init__(self, port, timeout=10.0):
        deadline = time.monotonic() + timeout
        while True:
            try:
                self.s = socket.create_connection(("127.0.0.1", port), timeout=2.0)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.1)
        self.buf = b""

    def _recv_packet(self, timeout):
        self.s.settimeout(timeout)
        while True:
            frames, rest = parse_frames(self.buf)
            if frames:
                first = frames[0]
                i = self.buf.find(b"#", self.buf.find(b"$"))
                self.buf = self.buf[i + 3:]
                self.s.sendall(b"+")
                return first
            self.buf = rest if rest else self.buf.lstrip(b"+-")
            chunk = self.s.recv(65536)
            if not chunk:
                raise EOFError("gdbstub closed")
            self.buf += chunk

    def cmd(self, payload, timeout=10.0):
        self.s.sendall(frame(payload).encode("latin1"))
        return self._recv_packet(timeout)

    def cont(self, timeout):
        self.s.sendall(frame("c").encode("latin1"))
        try:
            return self._recv_packet(timeout)
        except socket.timeout:
            return None

    def interrupt(self):
        self.s.sendall(b"\x03")
        try:
            return self._recv_packet(5.0)
        except (socket.timeout, EOFError):
            return None

    def mem(self, addr, n):
        r = self.cmd("m%x,%x" % (addr, n))
        if r.startswith("E") or not r:
            return b""
        return bytes.fromhex(r)


def cmd_run(args):
    if not args.qemu_argv:
        print("run: give the QEMU argv after --")
        return 2
    hooks = args.hook or [parse_hook(DEFAULT_HOOK)]
    argv = list(args.qemu_argv) + ["-gdb", "tcp:127.0.0.1:%d" % args.port, "-S"]
    out = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL)
    counts = {va: 0 for va in args.count}
    hits = 0
    try:
        rsp = Rsp(args.port)
        rsp.cmd("?")
        for va in [h[0] for h in hooks] + list(args.count):
            if rsp.cmd("Z0,%x,2" % va) != "OK":
                print("run: breakpoint at 0x%08x refused" % va, file=sys.stderr)
        by_va = {h[0]: h for h in hooks}
        t0 = time.monotonic()
        last_pc = None
        while True:
            left = args.duration - (time.monotonic() - t0)
            if left <= 0 or proc.poll() is not None:
                break
            if last_pc is not None:
                # step over the breakpoint we stopped on, then re-arm it
                rsp.cmd("z0,%x,2" % last_pc)
                rsp.cmd("s")
                rsp.cmd("Z0,%x,2" % last_pc)
                last_pc = None
            stop = rsp.cont(left)
            if stop is None:
                rsp.interrupt()
                break
            if not stop.startswith(("T", "S")):
                break
            regs = regs_from_g(rsp.cmd("g"))
            pc = regs.get("pc")
            last_pc = pc if (pc in counts or pc in by_va) else None
            if pc in counts:
                counts[pc] += 1
                continue
            hook = by_va.get(pc)
            if hook is None:
                continue
            hits += 1
            val = regs.get(hook[1], 0)
            text = ""
            if hook[2] in ("w", "a"):
                text = decode_str(rsp.mem(val, args.max_len), hook[2])
            out.write("%8.3f 0x%08x pr=0x%08x %s=0x%08x %s\n"
                      % (time.monotonic() - t0, pc, regs.get("pr", 0), hook[1], val,
                         text.rstrip("\r\n").replace("\r\n", " | ")))
            out.flush()
            if args.max_hits and hits >= args.max_hits:
                break
        # the CPU is stopped here: at a breakpoint, or by the interrupt above
        if proc.poll() is None and (args.dump or args.word):
            for va in args.word:
                raw = rsp.mem(va, 4)
                out.write("word 0x%08x: %s\n" % (va, "0x%08x" % struct.unpack("<I", raw)[0]
                                                    if len(raw) == 4 else "unreadable"))
            for va, length, path in args.dump:
                data = bytearray()
                while len(data) < length:
                    chunk = rsp.mem(va + len(data), min(0x800, length - len(data)))
                    if not chunk:
                        break
                    data += chunk
                with open(path, "wb") as fh:
                    fh.write(data)
                out.write("dump 0x%08x+0x%x -> %s (%d bytes)\n" % (va, length, path, len(data)))
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
    for va, n in counts.items():
        out.write("count 0x%08x: %d\n" % (va, n))
    out.write("hook hits: %d\n" % hits)
    if out is not sys.stdout:
        out.close()
    return 0


def toc_entries(read, image_va0):
    """[(name, TOC entry VA)] of a CE image; ``read(va, n)``."""
    hdr = read(image_va0 + 0x40, 12)
    if hdr[:4] != b"ECEC":
        raise ValueError("no ECEC at image + 0x40")
    ptoc = struct.unpack_from("<I", hdr, 4)[0]
    nummods = struct.unpack("<I", read(ptoc + 0x10, 4))[0]
    out = []
    for i in range(nummods):
        te = ptoc + 0x54 + 32 * i
        nva = struct.unpack("<I", read(te + 0x10, 4))[0]
        raw = read(nva, 64)
        out.append((raw.split(b"\0")[0].decode("latin1"), te))
    return out


def find_refs(dump, dump_va, entries):
    """[(name, TOC VA, [dump VAs holding it])] for entries referenced in dump."""
    res = []
    for name, te in entries:
        pat = struct.pack("<I", te)
        hits, j = [], dump.find(pat)
        while j >= 0:
            if j % 4 == 0:
                hits.append(dump_va + j)
            j = dump.find(pat, j + 1)
        if hits:
            res.append((name, te, hits))
    return res


def cmd_modules(args):
    with open(args.image, "rb") as fh:
        def read(va, n):
            fh.seek(args.image_start + va - 0x88000000)
            return fh.read(n)
        entries = toc_entries(read, 0x88000000)
    with open(args.dump, "rb") as fh:
        dump = fh.read()
    refs = find_refs(dump, args.dump_va, entries)
    for name, te, hits in refs:
        print("%-24s TOC 0x%08x  referenced at %s" % (name, te, " ".join("0x%08x" % h for h in hits[:4])))
    exes = sorted(n for n, _t, _h in refs if n.lower().endswith(".exe"))
    print("modules: %d of %d TOC entries referenced; .exe: %s" % (len(refs), len(entries), " ".join(exes) or "none"))
    return 0


def selftest():
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))

    img = bytearray(0x400)
    img[0x40:0x44] = b"ECEC"
    struct.pack_into("<I", img, 0x44, 0x88000100)
    struct.pack_into("<I", img, 0x110, 2)
    for i, (nm, off) in enumerate(((b"nk.exe", 0x300), (b"filesys.exe", 0x320))):
        struct.pack_into("<I", img, 0x100 + 0x54 + 32 * i + 0x10, 0x88000000 + off)
        img[off:off + len(nm) + 1] = nm + b"\0"
    ents = toc_entries(lambda va, n: bytes(img[va - 0x88000000:va - 0x88000000 + n]), 0x88000000)
    check("toc names", [e[0] for e in ents], ["nk.exe", "filesys.exe"])
    dump = b"\0" * 8 + struct.pack("<I", ents[1][1]) + b"\0" * 4
    check("refs", [(r[0], r[2]) for r in find_refs(dump, 0x89e40000, ents)], [("filesys.exe", [0x89e40008])])
    check("frame", frame("g"), "$g#67")
    check("frame Z0", frame("Z0,880404f4,2"), "$Z0,880404f4,2#" + checksum("Z0,880404f4,2"))
    frames, rest = parse_frames(b"+$OK#9a$T05#b9$pa")
    check("parse two frames", frames, ["OK", "T05"])
    check("partial kept", rest, b"$pa")
    g = "".join(struct.pack("<I", v).hex() for v in range(23))
    regs = regs_from_g(g)
    check("r4", regs["r4"], 4)
    check("pc", regs["pc"], 16)
    check("sr", regs["sr"], 22)
    check("utf16", decode_str("SH-4 Kernel\r\n".encode("utf-16-le") + b"\0\0junk", "w"), "SH-4 Kernel\r\n")
    check("ascii", decode_str(b"abc\0def", "a"), "abc")
    check("dump parse", parse_dump("0x89e40000:0x40000:k.bin"), (0x89E40000, 0x40000, "k.bin"))
    check("hook parse", parse_hook("0x880404f4:r4:w"), (0x880404F4, "r4", "w"))
    for bad in ("0x1:r99:w", "0x1:r4:q"):
        try:
            parse_hook(bad)
            check("bad hook %s refused" % bad, False, True)
        except argparse.ArgumentTypeError:
            check("bad hook %s refused" % bad, True, True)
    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    qemu_argv = []
    if "--" in argv:
        i = argv.index("--")
        argv, qemu_argv = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("--duration", type=float, required=True)
    r.add_argument("--hook", type=parse_hook, action="append")
    r.add_argument("--count", type=lambda s: int(s, 0), action="append", default=[])
    r.add_argument("--port", type=int, default=1234 + os.getpid() % 1000)
    r.add_argument("--max-len", type=int, default=512)
    r.add_argument("--max-hits", type=int, default=0)
    r.add_argument("-o", "--out")
    r.add_argument("--word", type=lambda v: int(v, 0), action="append", default=[],
                   help="print this guest word at the end (e.g. CurMSec 0x89e41888)")
    r.add_argument("--dump", type=parse_dump, action="append", default=[],
                   help="VA:LEN:FILE, read through the gdbstub at the end")
    m = sub.add_parser("modules")
    m.add_argument("dump")
    m.add_argument("image")
    m.add_argument("--dump-va", type=lambda v: int(v, 0), required=True)
    m.add_argument("--image-start", type=lambda v: int(v, 0), default=0x3E00200)
    args = ap.parse_args(argv)
    args.qemu_argv = qemu_argv
    if args.selftest:
        return selftest()
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "modules":
        return cmd_modules(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
