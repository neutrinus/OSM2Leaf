#!/usr/bin/env python3
"""Small gdb-remote client and HMP helper for debugging `-M ze0` (M8.C1q).

The sandbox has no `gdb-multiarch`, so the firmware was debugged with this
stdlib-only client of QEMU's gdbstub (`-gdb tcp::PORT -S`) plus the HMP
monitor socket (`-monitor unix:SOCK,server,nowait`). With a real
`gdb-multiarch` the same steps are ordinary gdb commands; see
docs/emulator/debugging.md.

Commands::

    ze0_gdb.py regs   [--port 1240]                 # stop, print r0-r15, pc, pr, sr
    ze0_gdb.py break  ADDR[,ADDR...] [--seconds 60] [--max 20] [--name-reg 4]
                                                    # count/print breakpoint hits
    ze0_gdb.py watch  ADDR [--seconds 60] [--min-delta 0]
                                                    # write watchpoint, print value changes
    ze0_gdb.py xp     --monitor SOCK ADDR [WORDS]   # read physical memory via HMP
    ze0_gdb.py --selftest

`break` steps over each hit (remove, single-step, reinsert) because QEMU's
sh4 gdbstub stops again on the same breakpoint after a plain `c`. With
`--name-reg N` it reads a UTF-16 string at rN (e.g. the image name passed to
CreateProcessW). Addresses are guest VAs; QEMU's TCG breakpoints match the
PC, so a kernel P1 address (0x8xxxxxxx) works while the guest is in user
mode, but memory reads of P1 through the gdbstub fail in user mode; use `xp`
with the physical address (P1 & 0x1fffffff) instead.
"""
from __future__ import annotations

import argparse
import collections
import re
import socket
import struct
import sys
import time


def checksum(data: bytes) -> int:
    return sum(data) & 0xFF


def frame(payload: str) -> bytes:
    d = payload.encode()
    return b"$" + d + b"#%02x" % checksum(d)


def parse_frames(buf: bytes):
    """Split a byte buffer into (payloads, rest); acks '+'/'-' are dropped."""
    out = []
    while True:
        i = buf.find(b"$")
        if i < 0:
            return out, b""
        j = buf.find(b"#", i)
        if j < 0 or len(buf) < j + 3:
            return out, buf[i:]
        payload = buf[i + 1:j]
        if int(buf[j + 1:j + 3], 16) != checksum(payload):
            raise ValueError("bad checksum")
        out.append(payload.decode())
        buf = buf[j + 3:]


class Gdb:
    """Minimal RSP client: one request, one reply."""

    def __init__(self, port: int = 1240, host: str = "127.0.0.1", sock=None):
        if sock is None:
            for _ in range(50):
                try:
                    sock = socket.create_connection((host, port))
                    break
                except OSError:
                    time.sleep(0.2)
            else:
                raise SystemExit(f"cannot connect to gdbstub {host}:{port}")
        self.s = sock
        self.buf = b""

    def recv(self, timeout=None) -> str:
        self.s.settimeout(timeout)
        while True:
            frames, rest = parse_frames(self.buf)
            if frames:
                self.buf = self.buf[len(self.buf) - len(rest):] if rest else b""
                # keep anything after the first frame
                first = frames[0]
                tail = b"".join(frame(f) for f in frames[1:]) + rest
                self.buf = tail
                self.s.sendall(b"+")
                return first
            chunk = self.s.recv(65536)
            if not chunk:
                raise EOFError("gdbstub closed")
            self.buf += chunk

    def pkt(self, payload: str) -> str:
        self.s.sendall(frame(payload))
        return self.recv()

    def regs(self) -> list[int]:
        g = self.pkt("g")
        return [struct.unpack("<I", bytes.fromhex(g[k * 8:k * 8 + 8]))[0]
                for k in range(len(g) // 8)]

    def mem(self, addr: int, n: int) -> bytes:
        r = self.pkt("m%x,%x" % (addr, n))
        if r.startswith("E"):
            raise OSError(f"read {addr:#x}: {r}")
        return bytes.fromhex(r)

    def cont(self, timeout=None) -> str | None:
        self.s.sendall(frame("c"))
        try:
            return self.recv(timeout)
        except socket.timeout:
            self.s.settimeout(None)
            self.s.sendall(b"\x03")
            self.recv()
            return None

    def step_over(self, kind: str, addr: int, size: int = 2) -> None:
        self.pkt("z%s,%x,%d" % (kind, addr, size))
        self.pkt("s")
        self.pkt("Z%s,%x,%d" % (kind, addr, size))


# sh4 register order in QEMU's 'g' packet: r0-r15, pc, pr, gbr, vbr, mach, macl, sr
PC, PR, SR = 16, 17, 22


def fmt_regs(g: list[int]) -> str:
    rs = " ".join("r%d=%x" % (i, g[i]) for i in range(16))
    return "pc=%x pr=%x sr=%x %s" % (g[PC], g[PR], g[SR] if len(g) > SR else 0, rs)


def hmp_xp(sock_path: str, addr: int, words: int) -> list[int]:
    m = socket.socket(socket.AF_UNIX)
    m.connect(sock_path)
    m.settimeout(1.0)
    try:
        m.recv(65536)
    except socket.timeout:
        pass
    m.sendall(b"xp /%dwx 0x%x\n" % (words, addr & 0x1FFFFFFF))
    buf = b""
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            c = m.recv(65536)
        except socket.timeout:
            break
        if not c:
            break
        buf += c
        if buf.rstrip().endswith(b"(qemu)") and b":" in buf:
            break
    return parse_xp(buf.decode(errors="replace"))


def parse_xp(text: str) -> list[int]:
    vals = []
    for line in text.splitlines():
        m = re.match(r"^\s*[0-9a-f]{8,16}:((?:\s+0x[0-9a-f]{8})+)", line.strip())
        if m:
            vals += [int(x, 16) for x in m.group(1).split()]
    return vals


def cmd_break(a) -> int:
    g = Gdb(a.port)
    print("state", g.pkt("?"), flush=True)
    bps = [int(x, 16) for x in a.addrs.split(",")]
    for b in bps:
        g.pkt("Z0,%x,2" % b)
    hits = collections.Counter()
    t0 = time.time()
    while time.time() - t0 < a.seconds:
        if g.cont(max(1, a.seconds - (time.time() - t0))) is None:
            break
        r = g.regs()
        pc = r[PC]
        hits[pc] += 1
        if hits[pc] <= a.max:
            extra = ""
            if a.name_reg is not None:
                try:
                    extra = " name=" + g.mem(r[a.name_reg], 80).decode(
                        "utf-16-le", "replace").split("\0")[0]
                except OSError as e:
                    extra = f" name=? ({e})"
            print("%7.1f %s%s" % (time.time() - t0, fmt_regs(r), extra), flush=True)
        if pc in bps:
            g.step_over("0", pc)
    for b in bps:
        g.pkt("z0,%x,2" % b)
    print("hits", {hex(k): v for k, v in hits.items()}, flush=True)
    g.s.sendall(frame("c"))
    return 0


def cmd_watch(a) -> int:
    g = Gdb(a.port)
    g.pkt("?")
    addr = int(a.addr, 16)
    print("Z2", g.pkt("Z2,%x,4" % addr), flush=True)
    prev = None
    t0 = time.time()
    while time.time() - t0 < a.seconds:
        if g.cont(max(1, a.seconds - (time.time() - t0))) is None:
            break
        r = g.regs()
        try:
            v = struct.unpack("<I", g.mem(addr, 4))[0]
        except OSError:
            v = None
        if prev is None or v is None or abs(v - prev) >= a.min_delta:
            print("%7.1f %s -> %s pc=%x pr=%x" % (time.time() - t0, prev, v, r[PC], r[PR]),
                  flush=True)
        prev = v
        g.step_over("2", addr, 4)
    g.pkt("z2,%x,4" % addr)
    g.s.sendall(frame("c"))
    return 0


def selftest() -> int:
    assert frame("g") == b"$g#67"
    assert frame("m5894,4") == b"$m5894,4#" + b"%02x" % checksum(b"m5894,4")
    frames, rest = parse_frames(b"+$OK#9a$T05#b9$par")
    assert frames == ["OK", "T05"] and rest == b"$par", (frames, rest)
    try:
        parse_frames(b"$OK#00")
    except ValueError:
        pass
    else:
        raise AssertionError("bad checksum accepted")
    xp = "xp /4wx 0x9e41b10\n0000000009e41b10: 0x0000031b 0x000000c4 0x89e42bf8 0x89e418a0\n(qemu) "
    assert parse_xp(xp) == [0x31B, 0xC4, 0x89E42BF8, 0x89E418A0]
    # client against a socketpair: reply to 'g' with 23 registers
    a, b = socket.socketpair()
    g = Gdb(sock=a)
    regs = list(range(23))
    b.sendall(frame("".join(struct.pack("<I", x).hex() for x in regs)))
    got = g.regs()
    assert b.recv(100).startswith(b"$g#67")
    assert got == regs, got
    assert "pc=10 pr=11" in fmt_regs(got)
    a.close()
    b.close()
    print("ze0_gdb selftest: OK")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("regs")
    p.add_argument("--port", type=int, default=1240)
    p = sub.add_parser("break")
    p.add_argument("addrs")
    p.add_argument("--port", type=int, default=1240)
    p.add_argument("--seconds", type=float, default=60)
    p.add_argument("--max", type=int, default=20)
    p.add_argument("--name-reg", type=int)
    p = sub.add_parser("watch")
    p.add_argument("addr")
    p.add_argument("--port", type=int, default=1240)
    p.add_argument("--seconds", type=float, default=60)
    p.add_argument("--min-delta", type=int, default=0)
    p = sub.add_parser("xp")
    p.add_argument("--monitor", required=True)
    p.add_argument("addr")
    p.add_argument("words", nargs="?", type=int, default=8)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "regs":
        g = Gdb(a.port)
        g.s.sendall(b"\x03")
        print("state", g.recv())
        print(fmt_regs(g.regs()))
        g.s.sendall(frame("c"))
        return 0
    if a.cmd == "break":
        return cmd_break(a)
    if a.cmd == "watch":
        return cmd_watch(a)
    if a.cmd == "xp":
        base = int(a.addr, 16)
        for i, v in enumerate(hmp_xp(a.monitor, base, a.words)):
            print("%08x %08x" % (base + 4 * i, v))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
