#!/usr/bin/env python3
"""TMU0 interrupt delivery test for the QEMU ``ze0`` INTC model (TODO M8.B1).

Two sub-commands:

  shim -o OUT   Write a small SH-4 program (our bytes, no vendor data) that
                programs TMU0 at ``0xffd80000`` the way EU2011 nk.exe does
                (TSTR=0, TCOR0/TCNT0, TCR0 with UNIE, TSTR=1), sets INT2PRI0
                to the firmware's value ``0x08020202`` and unmasks INT2 bit 1
                through INT2MSKCR ``0xff804044`` (fn 0x8803d168, EU2011),
                points VBR at its own vector page and clears SR.BL/IMASK.
                Its handler at VBR+0x600 reads INTEVT (``0xff000028``),
                **acknowledges** the interrupt by clearing TCR0.UNF (bit 8, as
                the firmware's timer ISR fn 0x8803cb34 does), writes one
                character per interrupt to the debug SCIF ``0xffe4600c``
                (M8.A6) and returns with ``rte``.  The character is
                ``'0' + ((INTEVT >> 8) & 0xf)`` -- ``'4'`` for INTEVT 0x400.

                ``--no-ack`` drops the TCR0 write (the level stays asserted:
                the CPU must re-enter at once), ``--no-unmask`` drops the
                INT2MSKCR write (the source stays masked: nothing may be
                delivered).  These are the negative controls.

  count LOG     Count the handler's characters in a serial capture and the
                ``interrupt`` entries in a QEMU ``-d int`` log (optional
                ``--int-log``).  Prints counts per character.

Usage:
  ze0_intc.py shim -o FILE [--base 0x8f000000] [--tcor 0x00100000]
              [--no-ack] [--no-unmask]
  ze0_intc.py count SERIAL_LOG [--int-log QEMU_LOG]
  ze0_intc.py --selftest

Method and results: docs/experiments/EXP-2026-11-19-M8.B1-intc-model.md
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sh4dis import Mem, decode, fmt  # noqa: E402

TMU_BASE = 0xFFD80000      # TOCR +0, TSTR +4, TCOR0 +8, TCNT0 +0xc, TCR0 +0x10
INT2_BASE = 0xFF804000     # INT2PRI0 +0, INT2MSKR +0x40, INT2MSKCR +0x44
INT2PRI0_EU2011 = 0x08020202   # written by fn 0x8803d168 (EU2011)
TMU_INT2_BIT = 1               # INT2MSKCR = 2 right after the TMU0 hook
CCN_BASE = 0xFF000000      # INTEVT at +0x28
SCIF_TDR = 0xFFE4600C      # debug SCIF data register (M8.A6)
VBR_OFFSET = 0x1000        # vector page = base + 0x1000; handler at +0x600
SR_RUN = 0x40000000        # MD=1, RB=0, BL=0, IMASK=0


class Asm:
    """Tiny two-pass assembler for the shim: halfwords + a literal pool."""

    def __init__(self, base):
        self.base = base
        self.words = []          # (kind, value): ('w', hw) | ('lit', label) | ('bra', label)
        self.labels = {}
        self.lits = []

    def label(self, name):
        self.labels[name] = len(self.words) * 2

    def w(self, hw):
        self.words.append(("w", hw & 0xFFFF))

    def movl(self, value, rn):
        """mov.l @(disp,PC),Rn with a pooled literal."""
        if value not in self.lits:
            self.lits.append(value)
        self.words.append(("lit", (value, rn)))

    def bra(self, name):
        self.words.append(("bra", name))

    def assemble(self):
        code_len = len(self.words) * 2
        pool = (code_len + 3) & ~3
        lit_off = {v: pool + 4 * i for i, v in enumerate(self.lits)}
        out = bytearray(pool + 4 * len(self.lits))
        for i, (kind, val) in enumerate(self.words):
            a = 2 * i
            if kind == "w":
                hw = val
            elif kind == "lit":
                value, rn = val
                disp = (lit_off[value] - ((a + 4) & ~3)) // 4
                if not 0 <= disp <= 0xFF:
                    raise ValueError("literal out of range")
                hw = 0xD000 | (rn << 8) | disp
            else:
                disp = (self.labels[val] - (a + 4)) // 2
                hw = 0xA000 | (disp & 0xFFF)
            struct.pack_into("<H", out, a, hw)
        for v, off in lit_off.items():
            struct.pack_into("<I", out, off, v)
        return bytes(out)


def main_program(base, tcor, unmask=True):
    a = Asm(base)
    # VBR and SR first: the CPU resets with SR.RB=1, and ldc sr switches to
    # bank 0, so any r0-r7 loaded before it would be lost.
    a.movl(base + VBR_OFFSET, 0)
    a.w(0x402E)                      # ldc r0,vbr
    a.movl(SR_RUN, 0)
    a.w(0x400E)                      # ldc r0,sr   (bank 0, BL=0, IMASK=0)
    a.movl(TMU_BASE, 1)
    a.w(0xE000)                      # mov #0,r0
    a.w(0x8014)                      # mov.b r0,@(4,r1)    TSTR = 0
    a.movl(tcor, 2)
    a.w(0x1122)                      # mov.l r2,@(8,r1)    TCOR0
    a.w(0x1123)                      # mov.l r2,@(12,r1)   TCNT0
    a.w(0xE020)                      # mov #0x20,r0        TCR0 = UNIE, Pphi/4
    a.w(0x8118)                      # mov.w r0,@(16,r1)
    a.movl(INT2_BASE, 3)
    a.movl(INT2PRI0_EU2011, 0)
    a.w(0x2302)                      # mov.l r0,@r3        INT2PRI0
    if unmask:
        a.movl(INT2_BASE + 0x44, 3)
        a.w(0xE000 | (1 << TMU_INT2_BIT))  # mov #2,r0
        a.w(0x2302)                  # mov.l r0,@r3        INT2MSKCR
    a.w(0xE001)                      # mov #1,r0
    a.w(0x8014)                      # mov.b r0,@(4,r1)    TSTR = 1
    a.label("spin")
    a.bra("spin")
    a.w(0x0009)                      # nop
    return a.assemble()


def handler(base, ack=True):
    a = Asm(base)
    a.movl(CCN_BASE, 1)
    a.movl(SCIF_TDR, 2)
    if ack:
        a.movl(TMU_BASE, 3)
        a.movl(0xFFFFFEFF, 4)
        a.w(0x8538)                  # mov.w @(16,r3),r0   TCR0
        a.w(0x2049)                  # and r4,r0           clear UNF (bit 8)
        a.w(0x8138)                  # mov.w r0,@(16,r3)
    a.w(0x501A)                      # mov.l @(40,r1),r0   INTEVT
    a.w(0x4019)                      # shlr8 r0
    a.w(0xC90F)                      # and #15,r0
    a.w(0x7030)                      # add #48,r0
    a.w(0x2200)                      # mov.b r0,@r2        one char to the SCIF
    a.w(0x002B)                      # rte
    a.w(0x0009)                      # nop
    return a.assemble()


def build_shim(base=0x8F000000, tcor=0x00100000, ack=True, unmask=True):
    """One blob: main program at +0, handler at +VBR_OFFSET+0x600."""
    if base % 0x1000:
        raise ValueError("base must be 4 KiB aligned")
    blob = bytearray(VBR_OFFSET + 0x600)
    mp = main_program(base, tcor, unmask)
    if len(mp) > VBR_OFFSET:
        raise ValueError("main program too long")
    blob[:len(mp)] = mp
    blob += handler(base + VBR_OFFSET + 0x600, ack)
    return bytes(blob)


def disasm(blob, base, start, count):
    mem = Mem([(base, blob)])
    return [fmt(decode(mem.u16(base + start + 2 * i), base + start + 2 * i, mem))
            for i in range(count)]


def cmd_shim(args):
    blob = build_shim(args.base, args.tcor, not args.no_ack, not args.no_unmask)
    with open(args.out, "wb") as fh:
        fh.write(blob)
    print("shim %s: %d bytes at VA 0x%08x (phys 0x%08x); entry 0x%08x; "
          "handler 0x%08x; ack=%s unmask=%s tcor=0x%x"
          % (args.out, len(blob), args.base, args.base & 0x1FFFFFFF, args.base,
             args.base + VBR_OFFSET + 0x600, not args.no_ack, not args.no_unmask, args.tcor))
    return 0


def count_serial(data):
    out = {}
    for b in data:
        out[chr(b)] = out.get(chr(b), 0) + 1
    return out


def count_int_log(text):
    """{vector: n} for QEMU ``-d int`` lines ``exception 0xNNN [interrupt] raised``."""
    out = {}
    for line in text.splitlines():
        if line.startswith("exception ") and "[interrupt]" in line:
            v = line.split()[1]
            out[v] = out.get(v, 0) + 1
    return out


def cmd_count(args):
    with open(args.log, "rb") as fh:
        data = fh.read()
    c = count_serial(data)
    print("serial %s: %d bytes" % (args.log, len(data)))
    for k in sorted(c):
        print("  %r %d" % (k, c[k]))
    if args.int_log:
        with open(args.int_log, "r", errors="replace") as fh:
            text = fh.read()
        ints = count_int_log(text)
        print("int log %s: %d taken interrupt(s)" % (args.int_log, sum(ints.values())))
        for k in sorted(ints):
            print("  %s %d" % (k, ints[k]))
    return 0


def selftest():
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))

    base = 0x8F000000
    blob = build_shim(base)
    check("handler at VBR+0x600", len(blob) > VBR_OFFSET + 0x600, True)
    main = disasm(blob, base, 0, 24)
    text = "\n".join(main)
    check("SR loaded before any bank-0 register", " 400e " in main[3], True)
    check("main loads TMU base", "0xffd80000" in main[4], True)
    check("TSTR=0 then 1", text.count("mov.b r0,@(4,r1)"), 2)
    check("TCOR0 and TCNT0", ("mov.l r2,@(8,r1)" in text, "mov.l r2,@(12,r1)" in text), (True, True))
    # sh4dis prints ldc as .word; check the encodings (ldc Rm,VBR 0x4m2E,
    # ldc Rm,SR 0x4m0E) directly
    check("ldc r0,vbr present", any(" 402e " in l for l in main), True)
    check("ldc r0,sr present", any(" 400e " in l for l in main), True)
    check("INT2MSKCR literal", "0xff804044" in text, True)
    check("spin is bra to itself",
          any(len(l.split()) > 3 and l.split()[2] == "bra" and l.split()[0] == l.split()[3]
              for l in main), True)
    h = disasm(blob, base, VBR_OFFSET + 0x600, 16)
    htext = "\n".join(h)
    check("handler reads INTEVT", "mov.l @(40,r1),r0" in htext, True)
    check("handler acks TCR0", ("mov.w @(16,r3),r0" in htext, "mov.w r0,@(16,r3)" in htext), (True, True))
    check("handler ends with rte", any(l.split()[2] == "rte" for l in h if len(l.split()) > 2), True)
    noack = disasm(build_shim(base, ack=False), base, VBR_OFFSET + 0x600, 12)
    check("--no-ack has no TCR0 write", "mov.w r0,@(16,r3)" in "\n".join(noack), False)
    nounmask = "\n".join(disasm(build_shim(base, unmask=False), base, 0, 24))
    check("--no-unmask has no INT2MSKCR", "0xff804044" in nounmask, False)
    # the handler's character for INTEVT 0x400
    check("char for 0x400", chr(((0x400 >> 8) & 15) + 48), "4")
    check("serial count", count_serial(b"4444"), {"4": 4})
    log = ("exception 0x400 [interrupt] raised\npc=0x0\n"
           "exception 0x040 [tlb_miss] raised\nexception 0x400 [interrupt] raised\n")
    check("int log counts interrupts only", count_int_log(log), {"0x400": 2})
    try:
        build_shim(0x8F000004)
        check("misaligned base refused", False, True)
    except ValueError:
        check("misaligned base refused", True, True)
    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def _int(s):
    return int(s, 0)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("shim")
    s.add_argument("-o", "--out", required=True)
    s.add_argument("--base", type=_int, default=0x8F000000)
    s.add_argument("--tcor", type=_int, default=0x00100000)
    s.add_argument("--no-ack", action="store_true")
    s.add_argument("--no-unmask", action="store_true")
    c = sub.add_parser("count")
    c.add_argument("log")
    c.add_argument("--int-log")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "shim":
        return cmd_shim(args)
    if args.cmd == "count":
        return cmd_count(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
