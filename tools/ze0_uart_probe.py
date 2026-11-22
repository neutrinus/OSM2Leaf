#!/usr/bin/env python3
"""Register-patching probe for the ``ze0`` UAT3 receive path (TODO M8.H3).

``serial_uat.dll`` calls ``InterruptInitialize(SYSINTR=0x1b, event)``
(measured with ``ze0_dbgmsg.py``), but no OAL ISR in the EU2011 image returns
0x1b, so an interrupt asserted for that SYSINTR cannot wake the driver's IST.
This probe stops at the call, rewrites one guest register with a GDB RSP ``P``
packet, and continues.  With ``--patch 0x39a4cd8:4:12`` the driver registers
the event on SYSINTR 0x12, whose OAL ISR at INTEVT 0x8c0 returns 0x12; the
QEMU UART can then deliver a byte through the real driver read path.

This is a **diagnostic workaround**, not a claim about the firmware: it shows
that the model's RX FIFO, IRQ line and the driver's receive code work together
once a routable SYSINTR is used.  See the M8.H3 EXP.

Usage:
  ze0_uart_probe.py --selftest
  ze0_uart_probe.py --duration 20 --patch 0x39a4cd8:4:12 \\
      --hook 0x39a3e14:4:x -o hits.log -- QEMU_ARGS...

Stdlib only.
"""

from __future__ import annotations

import argparse
import re
import sys
import time

from ze0_dbgmsg import Rsp, frame, regs_from_g

PATCH_RE = re.compile(r"^(0x[0-9a-fA-F]+):([0-9]+):(0x[0-9a-fA-F]+|[0-9a-fA-F]+)$")
HOOK_RE = re.compile(r"^(0x[0-9a-fA-F]+):([0-9]+):([xw])$")


def parse_patch(text: str) -> tuple[int, int, int]:
    m = PATCH_RE.match(text)
    if not m:
        raise ValueError("patch must be VA:REG:VALUE")
    return int(m.group(1), 16), int(m.group(2)), int(m.group(3), 16)


def parse_hook(text: str) -> tuple[int, int, str]:
    m = HOOK_RE.match(text)
    if not m:
        raise ValueError("hook must be VA:REG:x|w")
    return int(m.group(1), 16), int(m.group(2)), m.group(3)


def reg_name(n: int) -> str:
    """SH-4 GDB register numbers: r0..r15 are 0..15 (QEMU gdbstub)."""
    if not 0 <= n <= 15:
        raise ValueError("SH-4 GPR number out of range: %d" % n)
    return "r%d" % n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--duration", type=float, default=20.0)
    ap.add_argument("--port", type=int, default=1234)
    ap.add_argument("--attach", action="store_true",
                    help="attach to an already-running -S QEMU gdbstub")
    ap.add_argument("--patch", action="append", default=[])
    ap.add_argument("--hook", action="append", default=[])
    ap.add_argument("-o", "--out")
    ap.add_argument("qemu_argv", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    a.qemu_argv = [x for x in a.qemu_argv if x != "--"]
    if not a.attach and not a.qemu_argv:
        print("probe: give the QEMU argv after --", file=sys.stderr)
        return 2
    import subprocess

    patches = [parse_patch(x) for x in a.patch]
    hooks = [parse_hook(x) for x in a.hook]
    out = open(a.out, "w", encoding="utf-8") if a.out else sys.stdout
    proc = None
    if not a.attach:
        argv = [x for x in a.qemu_argv if x != "--"]
        argv += ["-gdb", "tcp:127.0.0.1:%d" % a.port, "-S"]
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL)
    patched = {va: 0 for va, _, _ in patches}
    try:
        rsp = Rsp(a.port)
        rsp.cmd("?")
        for va in {va for va, _, _ in patches} | {va for va, _, _ in hooks}:
            if rsp.cmd("Z0,%x,2" % va) != "OK":
                print("probe: breakpoint at 0x%08x refused" % va,
                      file=sys.stderr)
        t0 = time.monotonic()
        last_pc = None
        while True:
            left = a.duration - (time.monotonic() - t0)
            if left <= 0 or (proc is not None and proc.poll() is not None):
                break
            if last_pc is not None:
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
            if pc in patched:
                for pva, rnum, value in patches:
                    if pva == pc:
                        ans = rsp.cmd("P%x=%x" % (rnum, value))
                        if ans != "OK":
                            print("probe: P packet refused: %s" % ans,
                                  file=sys.stderr)
                patched[pc] += 1
                out.write("%8.3f patched pc=0x%08x\n" %
                          (time.monotonic() - t0, pc))
                out.flush()
            for hva, rnum, mode in hooks:
                if pc == hva:
                    out.write("%8.3f hit 0x%08x %s=0x%x\n" %
                              (time.monotonic() - t0, pc,
                               reg_name(rnum), regs.get(reg_name(rnum), 0)))
                    out.flush()
            last_pc = pc if pc in patched or any(pc == h for h, _, _ in hooks) else None
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
    for va, n in patched.items():
        out.write("patched 0x%08x: %d\n" % (va, n))
    if out is not sys.stdout:
        out.close()
    return 0


def selftest() -> int:
    checks = []
    va, reg, value = parse_patch("0x39a4cd8:4:12")
    checks.append(("parse patch", (va, reg, value) == (0x39a4cd8, 4, 0x12)))
    p = frame("P4=12")
    checks.append(("P packet", p == "$P4=12#24"))
    checks.append(("register name", reg_name(4) == "r4"))
    try:
        parse_patch("bad")
    except ValueError:
        checks.append(("negative: bad patch refused", True))
    else:
        checks.append(("negative: bad patch refused", False))
    try:
        reg_name(99)
    except ValueError:
        checks.append(("negative: bad register refused", True))
    else:
        checks.append(("negative: bad register refused", False))
    for name, ok in checks:
        print("%-38s %s" % (name, "PASS" if ok else "FAIL"))
    print("selftest: %d/%d" % (sum(x for _, x in checks), len(checks)))
    return 0 if all(x for _, x in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
