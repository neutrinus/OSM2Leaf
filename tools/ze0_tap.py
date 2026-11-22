#!/usr/bin/env python3
"""Inject one CE mouse message into a running ``-M ze0`` guest via GDB RSP.

The system gdb on this host has no SH-4 target, so this tool speaks the GDB
Remote Serial Protocol directly to QEMU's gdbstub (TCP 127.0.0.1:1234 by
default).  It interrupts the CPU, calls ``COREDLL!PostMessageW`` at a known P1
VA (build B EU2011: ``0x88098d2c`` = coredll load ``0x8808f000`` + export RVA
``0x9d2c``), and restores the registers afterwards.  A breakpoint at the call
VA counts the hit; a second breakpoint at an ``rts`` trampoline catches the
return, after which the saved PC on the stack resumes the interrupted thread.

Touch coordinates are the message-level contract of ``docs/firmware/touch.md``:
``lParam = (y << 16) | x`` for ``WM_MOUSEMOVE`` / ``WM_LBUTTONDOWN`` /
``WM_LBUTTONUP`` (``0x0200`` / ``0x0201`` / ``0x0202``).

Usage:
  ze0_tap.py --selftest
  ze0_tap.py --status
  ze0_tap.py tap 400 240            # down, hold, up (HWND_BROADCAST)
  ze0_tap.py key 0x17               # not used by M8.H39, kept for parity
  ze0_tap.py --hwnd 0xffff --msg 0x201 --x 400 --y 240

Stdlib only.  Claims C-7360–C-7369; method and results in
``docs/experiments/EXP-2026-11-22-M8.H39-tap-l4.md``.
"""

import argparse
import socket
import struct
import sys
import time

POSTMESSAGE_P1 = 0x88098D2C    # COREDLL!PostMessageW, EU2011 build B
RTS_P1 = 0x880911FC           # coredll sec0 rva 0x21fc, a plain `rts`
DOC_CALL_VA = 0x03A1B154      # kepdrv thunk named in docs/firmware/touch.md
HWND_BROADCAST = 0xFFFF
REG_COUNT = 59                # QEMU SH-4 g packet: r0..r15, pc, pr, sr, ...
REG_SP = 15
REG_PC = 16
REG_PR = 17


class RspError(RuntimeError):
    """A malformed RSP reply or an unexpected stop."""


def packet(data):
    """RSP framing: $data#checksum, checksum = sum of bytes mod 256."""
    payload = data.encode("ascii") if isinstance(data, str) else data
    return b"$" + payload + b"#" + ("%02x" % (sum(payload) & 0xFF)).encode()


def decode_regs(hex_string):
    """One register per 8 hex chars, target (little) byte order."""
    if len(hex_string) % 8 or not all(c in "0123456789abcdefABCDEF"
                                      for c in hex_string):
        raise RspError("bad g packet")
    return [int.from_bytes(bytes.fromhex(hex_string[i:i + 8]), "little")
            for i in range(0, len(hex_string), 8)]


def encode_regs(regs):
    return "".join(struct.pack("<I", r & 0xFFFFFFFF).hex() for r in regs)


class Rsp:
    def __init__(self, host="127.0.0.1", port=1234, timeout=10.0):
        self.sock = socket.create_connection((host, port), timeout)
        self.sock.settimeout(timeout)
        self.buffer = bytearray()

    def close(self):
        self.sock.close()

    def _read_byte(self):
        if self.buffer:
            return self.buffer.pop(0)
        chunk = self.sock.recv(4096)
        if not chunk:
            raise RspError("gdbstub closed the connection")
        self.buffer.extend(chunk)
        return self.buffer.pop(0)

    def _discard_async(self, first):
        """Consume an unsolicited stop reply, leaving the next byte buffered."""
        if first != ord("$") and first != ord("%"):
            return first
        while self._read_byte() != ord("#"):
            pass
        self._read_byte()
        self._read_byte()
        return self._read_byte()

    def command(self, cmd, ack=True):
        self.sock.sendall(packet(cmd))
        if ack:
            got = self._read_byte()
            for _ in range(8):
                if got == ord("+"):
                    break
                got = self._discard_async(got)
            else:
                raise RspError("no ACK for %r: %r" % (cmd, got))
        while self._read_byte() != ord("$"):
            pass
        out = bytearray()
        while True:
            c = self._read_byte()
            if c == ord("#"):
                break
            out.append(c)
        hi = chr(self._read_byte())
        lo = chr(self._read_byte())
        want = sum(out) & 0xFF
        if int(hi + lo, 16) != want:
            raise RspError("bad checksum for %r" % cmd)
        return out.decode("utf-8", "replace")

    def interrupt(self):
        self.sock.sendall(b"\x03")
        return self._read_stop()

    def _read_stop(self):
        while True:
            data = self.command("?", ack=False)
            if data.startswith("T"):
                return data
            time.sleep(0.02)

    def regs(self):
        return decode_regs(self.command("g"))

    def set_regs(self, regs):
        if len(regs) != REG_COUNT:
            raise RspError("expected %d registers, got %d" % (REG_COUNT, len(regs)))
        if self.command("G" + encode_regs(regs)) != "OK":
            raise RspError("G failed")

    def write_mem(self, addr, data):
        if self.command("M%x,%d:%s" % (addr, len(data), data.hex())) != "OK":
            raise RspError("M failed at 0x%x" % addr)

    def set_bp(self, addr):
        return self.command("Z0,%x,0" % addr)

    def del_bp(self, addr):
        return self.command("z0,%x,0" % addr)

    def cont(self):
        return self.command("c", ack=False)

    def pc(self, regs=None):
        return (regs or self.regs())[REG_PC]

    def call(self, va, args, doc_va=None):
        """Call ``va(args)``; return (hit_at_va, hit_at_doc, reply)."""
        self.command("Hg0")
        self.interrupt()
        saved = self.regs()
        sp = saved[REG_SP]
        self.write_mem(sp, struct.pack("<I", saved[REG_PC]))
        self.set_bp(va)
        if doc_va:
            self.set_bp(doc_va)
        self.set_bp(RTS_P1)
        new = list(saved)
        for idx, value in enumerate(args):
            new[idx] = value & 0xFFFFFFFF
        new[REG_PC] = va
        new[REG_PR] = RTS_P1
        self.set_regs(new)
        hits = {va: 0, doc_va or 0: 0, RTS_P1: 0}
        replied = None
        for _ in range(64):
            stop = self.cont()
            replied = stop
            self.interrupt() if False else None
            pc = self.pc()
            if pc in hits:
                hits[pc] += 1
            if pc == va:
                # Step over the breakpoint at the entry point.
                self.del_bp(va)
                if doc_va:
                    self.del_bp(doc_va)
                continue
            if pc == RTS_P1:
                break
        self.del_bp(va)
        if doc_va:
            self.del_bp(doc_va)
        self.del_bp(RTS_P1)
        self.set_regs(saved)
        self.cont()
        return hits[va], hits.get(doc_va or 0, 0), replied


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------

def selftest():
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" %
              ("ok  " if ok else "FAIL", label, got, want))

    check("packet framing", packet("qSupported"), b"$qSupported#37")
    check("packet checksum", b"#%02x" % (sum(b"abc") & 0xFF), b"#26")
    regs = [0x11223344] * REG_COUNT
    dec = decode_regs(encode_regs(regs))
    check("register round-trip", (dec[0], dec[-1]), (0x11223344, 0x11223344))
    check("register byte order",
          decode_regs("78563412" + "00" * 4 * (REG_COUNT - 1))[0], 0x12345678)
    check("lparam packing", ((240 << 16) | 400), 0x00F00190)
    check("postmessage P1 from module headers", 0x8808F000 + 0x9D2C, POSTMESSAGE_P1)
    check("rts trampoline P1", 0x8808F000 + 0x21FC, RTS_P1)
    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1234)
    ap.add_argument("--hwnd", type=lambda x: int(x, 0), default=HWND_BROADCAST)
    ap.add_argument("--msg", type=lambda x: int(x, 0), default=0x0201)
    ap.add_argument("--x", type=int, default=0)
    ap.add_argument("--y", type=int, default=0)
    ap.add_argument("--doc-va", type=lambda x: int(x, 0), default=DOC_CALL_VA)
    ap.add_argument("--status", action="store_true",
                    help="print the stop reply and registers, inject nothing")
    ap.add_argument("--resume", action="store_true",
                    help="continue a target stopped by an earlier probe")
    ap.add_argument("--probe", action="store_true",
                    help="single-step the first instructions of the injected call")
    ap.add_argument("command", nargs="?", choices=("tap", "key"))
    ap.add_argument("coords", nargs="*")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    rsp = Rsp(args.host, args.port)
    try:
        if args.resume:
            rsp.sock.sendall(packet("c"))
            print("continued")
            return 0
        if args.probe:
            rsp.command("Hg0")
            rsp.interrupt()
            saved = rsp.regs()
            new = list(saved)
            new[REG_PC] = POSTMESSAGE_P1
            new[REG_PR] = RTS_P1
            for idx, value in enumerate([args.hwnd, args.msg, 0,
                                          (args.y << 16) | args.x]):
                new[idx] = value & 0xFFFFFFFF
            rsp.set_regs(new)
            pcs = []
            try:
                for _ in range(14):
                    rsp.command("s", ack=False)
                    pcs.append(rsp.pc())
            finally:
                rsp.set_regs(saved)
                rsp.sock.sendall(packet("c"))
                time.sleep(0.2)
            print("probe PCs: " + " ".join("0x%08x" % pc for pc in pcs))
            return 0
        if args.status:
            rsp.command("Hg0")
            print("stop:", rsp._read_stop())
            print("regs:", " ".join("%s=0x%08x" % (name, reg)
                                    for name, reg in zip(
                                        ["r%d" % i for i in range(16)] + ["pc", "pr"],
                                        rsp.regs())))
            return 0
        if args.command == "tap" and len(args.coords) == 2:
            x, y = int(args.coords[0]), int(args.coords[1])
            hit, doc, stop = rsp.call(
                POSTMESSAGE_P1,
                [args.hwnd, 0x0201, 0, (y << 16) | x],
                doc_va=args.doc_va)
            print("injected down x=%d y=%d lParam=0x%08x hits=%d doc_hits=%d stop=%s" %
                  (x, y, (y << 16) | x, hit, doc, stop))
            hit, doc, stop = rsp.call(
                POSTMESSAGE_P1,
                [args.hwnd, 0x0202, 0, (y << 16) | x],
                doc_va=args.doc_va)
            print("injected up   x=%d y=%d lParam=0x%08x hits=%d doc_hits=%d stop=%s" %
                  (x, y, (y << 16) | x, hit, doc, stop))
            return 0
        hit, doc, stop = rsp.call(
            POSTMESSAGE_P1,
            [args.hwnd, args.msg, 0, (args.y << 16) | args.x],
            doc_va=args.doc_va)
        print("injected msg=0x%04x x=%d y=%d hits=%d doc_hits=%d stop=%s" %
              (args.msg, args.x, args.y, hit, doc, stop))
        return 0
    finally:
        rsp.close()


if __name__ == "__main__":
    sys.exit(main())
