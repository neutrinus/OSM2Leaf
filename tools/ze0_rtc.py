#!/usr/bin/env python3
"""Drive the EU2011 OAL real-time-clock functions under QEMU ``-M ze0`` (TODO M8.B3).

EU2011 ``nk.exe`` keeps the date in software: ``OEMGetRealTime``
(fn ``0x880400a8``) builds a SYSTEMTIME from six RAM words (year
``0x89e43098``, month ``0x89e43094``, day ``0x89e43090``, hour ``0x89e4308c``,
minute ``0x89e43088``, second ``0x89e61394``) plus ``CurMSec`` (``0x89e41888``)
minus the base tick ``0x89e61390``; ``OEMSetRealTime`` (call target ``0x880401e0``, in a pdata gap)
range-checks a SYSTEMTIME (year 1601..9999, month 1..12, day 1..31,
hour <= 23, minute/second <= 59) and stores it with the base tick.  No
hardware register is read.

Sub-commands:

  shim -o OUT [--set Y-M-D-h-m-s]
        Write a small SH-4 program (our bytes, no vendor data) that sets
        SR (BL=1, IMASK=15) and a stack, optionally calls OEMSetRealTime on a
        SYSTEMTIME at ``base+0x100`` (result word at ``base+0x300``), then
        calls OEMGetRealTime with ``r4 = base+0x200`` and spins.  The kernel
        image must be loaded (``-device loader``) so the OAL code is there.

  decode LOG
        Find the HMP ``xp /8hx <base+0x200>`` line (and ``xp /2wx
        <base+0x300>`` = set result, done marker) in a captured ``-monitor stdio`` transcript and print
        the SYSTEMTIME fields and the set result.

  initdate IMAGE [--image-start 0x3e00200]
        Static: walk the ROMHDR copy entries of the kernel image and print
        the initial value of the five date words (they live in nk.exe's
        initialised data, copied to RAM at boot; the second word is in the
        zero-filled tail).

  ramdate LOG
        Dynamic: decode ``xp /5wx 0x09e43088`` (and ``xp /1wx 0x09e61394``)
        from an HMP transcript of a running boot.

Usage:
  ze0_rtc.py initdate IMAGE [--image-start 0x3e00200]
  ze0_rtc.py ramdate HMP_LOG
  ze0_rtc.py shim -o FILE [--base 0x8f000000] [--set 2011-3-15-10-20-30]
  ze0_rtc.py decode HMP_LOG [--base 0x8f000000]
  ze0_rtc.py --selftest

Method and results: docs/experiments/EXP-2026-11-20-M8.B3-rtc-time.md
"""

import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sh4dis import Mem, decode as sh4decode, fmt  # noqa: E402
from ze0_intc import Asm  # noqa: E402

GET_RT_EU2011 = 0x880400A8
SET_RT_EU2011 = 0x880401E0
SR_QUIET = 0x500000F0          # MD=1, RB=0, BL=1, IMASK=15
SET_OFF, GET_OFF, RES_OFF, DONE_OFF, STACK_OFF = 0x100, 0x200, 0x300, 0x304, 0x800
DONE_MAGIC = 0x600DF00D
# RAM words OEMGetRealTime reads (EU2011), in order minute, hour, day, month, year
DATE_WORDS_EU2011 = 0x89E43088
SECOND_EU2011 = 0x89E61394
NK_IMAGE_START_EU2011 = 0x3E00200   # SD offset of the EU2011 nk image (build B)
FIELDS = ("wYear", "wMonth", "wDayOfWeek", "wDay", "wHour", "wMinute",
          "wSecond", "wMilliseconds")


def systemtime(y, mo, d, h, mi, s, dow=0, ms=0):
    return struct.pack("<8H", y, mo, dow, d, h, mi, s, ms)


def build_shim(base=0x8F000000, set_time=None):
    if base % 0x1000:
        raise ValueError("base must be 4 KiB aligned")
    a = Asm(base)
    a.movl(SR_QUIET, 0)
    a.w(0x400E)                      # ldc r0,sr  (bank 0 from here on)
    a.movl(base + STACK_OFF, 15)     # mov.l @(..),r15
    if set_time is not None:
        a.movl(base + SET_OFF, 4)
        a.movl(SET_RT_EU2011, 1)
        a.w(0x410B)                  # jsr @r1
        a.w(0x0009)
        a.movl(base + RES_OFF, 2)
        a.w(0x2202)                  # mov.l r0,@r2   result of OEMSetRealTime
    a.movl(base + GET_OFF, 4)
    a.movl(GET_RT_EU2011, 1)
    a.w(0x410B)                      # jsr @r1
    a.w(0x0009)
    a.movl(base + DONE_OFF, 2)
    a.movl(DONE_MAGIC, 0)
    a.w(0x2202)                      # mov.l r0,@r2   "OEMGetRealTime returned"
    a.label("spin")
    a.bra("spin")
    a.w(0x0009)
    code = a.assemble()
    if len(code) > SET_OFF:
        raise ValueError("shim code too long")
    blob = bytearray(STACK_OFF + 4)
    blob[:len(code)] = code
    if set_time is not None:
        blob[SET_OFF:SET_OFF + 16] = systemtime(*set_time)
    struct.pack_into("<I", blob, RES_OFF, 0xDEADBEEF)
    return bytes(blob)


def parse_set(s):
    parts = [int(x) for x in s.split("-")]
    if len(parts) != 6:
        raise argparse.ArgumentTypeError("--set wants Y-M-D-h-m-s")
    return tuple(parts)


def parse_hmp(text, base):
    """(fields dict or None, set result or None) from an HMP transcript."""
    phys_get = (base + GET_OFF) & 0x1FFFFFFF
    phys_res = (base + RES_OFF) & 0x1FFFFFFF
    st = res = done = None
    m = re.search(r"%016x:((?: 0x[0-9a-f]{4}){8})" % phys_get, text)
    if m:
        vals = [int(v, 16) for v in m.group(1).split()]
        st = dict(zip(FIELDS, vals))
    m = re.search(r"%016x: (0x[0-9a-f]{8}) (0x[0-9a-f]{8})" % phys_res, text)
    if m:
        res = int(m.group(1), 16)
        done = int(m.group(2), 16) == DONE_MAGIC
    if st is not None and not done:
        st = None            # read before OEMGetRealTime returned: not a sample
    return st, res


def copy_entries(read, image_va0):
    """ROMHDR copy entries via ``read(va, n)``; image starts at VA image_va0."""
    if read(image_va0 + 0x40, 4) != b"ECEC":
        raise ValueError("no ECEC signature at image+0x40")
    ptoc = struct.unpack("<I", read(image_va0 + 0x44, 4))[0]
    hdr = struct.unpack("<10I", read(ptoc, 40))
    count, off = hdr[8], hdr[9]
    return [struct.unpack("<4I", read(off + 16 * i, 16)) for i in range(count)]


def initial_ram_word(read, image_va0, va):
    """Value of RAM word ``va`` right after the boot-time copy, or None."""
    for src, dst, clen, dlen in copy_entries(read, image_va0):
        if dst <= va < dst + dlen:
            if va + 4 <= dst + clen:
                return struct.unpack("<I", read(src + va - dst, 4))[0]
            return 0
    return None


def date_from_words(minute, hour, day, month, year, second):
    return "%04d-%02d-%02d %02d:%02d:%02d" % (year, month, day, hour, minute, second)


def cmd_initdate(args):
    with open(args.image, "rb") as fh:
        def read(va, n):
            fh.seek(args.image_start + va - 0x88000000)
            data = fh.read(n)
            if len(data) != n:
                raise ValueError("short read at VA 0x%08x" % va)
            return data
        ents = copy_entries(read, 0x88000000)
        for src, dst, clen, dlen in ents:
            print("copy entry: src 0x%08x -> dest 0x%08x copylen 0x%x destlen 0x%x"
                  % (src, dst, clen, dlen))
        words = [initial_ram_word(read, 0x88000000, DATE_WORDS_EU2011 + 4 * i) for i in range(5)]
        sec = initial_ram_word(read, 0x88000000, SECOND_EU2011)
    if None in words or sec is None:
        print("initdate: a date word is outside every copy entry")
        return 1
    print("initial date words (EU2011 0x%08x..0x%08x, second 0x%08x): %s"
          % (DATE_WORDS_EU2011, DATE_WORDS_EU2011 + 16, SECOND_EU2011, date_from_words(*words, sec)))
    return 0


def parse_ramdate(text):
    m = re.search(r"%016x:((?: 0x[0-9a-f]{8}){4})\s+%016x: (0x[0-9a-f]{8})"
                  % (DATE_WORDS_EU2011 & 0x1FFFFFFF, (DATE_WORDS_EU2011 + 16) & 0x1FFFFFFF), text)
    if not m:
        return None
    words = [int(v, 16) for v in m.group(1).split()] + [int(m.group(2), 16)]
    m2 = re.search(r"%016x: (0x[0-9a-f]{8})" % (SECOND_EU2011 & 0x1FFFFFFF), text)
    return words + [int(m2.group(1), 16) if m2 else 0]


def cmd_ramdate(args):
    with open(args.log, "r", errors="replace") as fh:
        w = parse_ramdate(fh.read())
    if w is None:
        print("ramdate: no xp /5wx 0x%08x line" % (DATE_WORDS_EU2011 & 0x1FFFFFFF))
        return 1
    print("RAM date words: %s" % date_from_words(*w))
    return 0


def cmd_shim(args):
    blob = build_shim(args.base, args.set)
    with open(args.out, "wb") as fh:
        fh.write(blob)
    print("shim %s: %d bytes at VA 0x%08x (phys 0x%08x); set=%s; "
          "SYSTEMTIME out at phys 0x%08x, set result at phys 0x%08x"
          % (args.out, len(blob), args.base, args.base & 0x1FFFFFFF, args.set,
             (args.base + GET_OFF) & 0x1FFFFFFF, (args.base + RES_OFF) & 0x1FFFFFFF))
    return 0


def cmd_decode(args):
    with open(args.log, "r", errors="replace") as fh:
        text = fh.read()
    st, res = parse_hmp(text, args.base)
    if st is None:
        print("decode: no xp line for the SYSTEMTIME buffer, or OEMGetRealTime had not returned")
        return 1
    print("SYSTEMTIME " + " ".join("%s=%d" % (k, v) for k, v in st.items()))
    if res is not None:
        print("OEMSetRealTime result word: 0x%08x" % res)
    return 0


def selftest():
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))

    base = 0x8F000000
    blob = build_shim(base, (2011, 3, 15, 10, 20, 30))
    mem = Mem([(base, blob)])
    text = [fmt(sh4decode(mem.u16(base + 2 * i), base + 2 * i, mem)) for i in range(20)]
    joined = "\n".join(text)
    check("ldc sr first", " 400e " in text[1], True)
    check("stack literal", "0x8f000800" in text[2] and "r15" in text[2], True)
    check("calls OEMSetRealTime", "0x880401e0" in joined, True)
    check("calls OEMGetRealTime", "0x880400a8" in joined, True)
    check("SYSTEMTIME in", struct.unpack_from("<8H", blob, SET_OFF), (2011, 3, 0, 15, 10, 20, 30, 0))
    check("result sentinel", struct.unpack_from("<I", blob, RES_OFF)[0], 0xDEADBEEF)
    nos = build_shim(base)
    nmem = Mem([(base, nos)])
    ntext = "\n".join(fmt(sh4decode(nmem.u16(base + 2 * i), base + 2 * i, nmem)) for i in range(16))
    check("no --set: no OEMSetRealTime", "0x880401e0" in ntext, False)
    hmp = ("(qemu) xp /8hx 0x0f000200\n000000000f000200: 0x07db 0x0003 0x0002 0x000f"
           " 0x000a 0x0014 0x001e 0x0000\n(qemu) xp /2wx 0x0f000300\n"
           "000000000f000300: 0x00000001 0x600df00d\n")
    st, res = parse_hmp(hmp, base)
    check("decode year", st["wYear"], 2011)
    check("decode second", st["wSecond"], 30)
    check("decode result", res, 1)
    check("decode missing", parse_hmp("nothing", base), (None, None))
    early = hmp.replace("0x600df00d", "0x00000000")
    check("read before return is rejected", parse_hmp(early, base)[0], None)
    # initdate on a synthetic image: ECEC, pTOC, ROMHDR with one copy entry
    img = bytearray(0x3000)
    img[0x40:0x44] = b"ECEC"
    struct.pack_into("<I", img, 0x44, 0x88001000)
    struct.pack_into("<10I", img, 0x1000, 0, 0, 0x88000000, 0x88003000, 0, 0, 0, 0, 1, 0x88001100)
    src = 0x88002000
    struct.pack_into("<4I", img, 0x1100, src, DATE_WORDS_EU2011 - 0x88, 0xA0, SECOND_EU2011 + 8 - (DATE_WORDS_EU2011 - 0x88))
    struct.pack_into("<5I", img, 0x2088, 10, 7, 10, 7, 2009)

    def rd(va, n):
        return bytes(img[va - 0x88000000:va - 0x88000000 + n])
    words = [initial_ram_word(rd, 0x88000000, DATE_WORDS_EU2011 + 4 * i) for i in range(5)]
    check("initdate copied words", words, [10, 7, 10, 7, 2009])
    check("initdate zero-filled second", initial_ram_word(rd, 0x88000000, SECOND_EU2011), 0)
    check("initdate outside copy", initial_ram_word(rd, 0x88000000, 0x80000000), None)
    check("date format", date_from_words(10, 7, 10, 7, 2009, 0), "2009-07-10 07:10:00")
    bad = bytearray(img)
    bad[0x40:0x44] = b"XXXX"
    try:
        copy_entries(lambda va, n: bytes(bad[va - 0x88000000:va - 0x88000000 + n]), 0x88000000)
        check("no ECEC refused", False, True)
    except ValueError:
        check("no ECEC refused", True, True)
    ram = ("0000000009e43088: 0x0000000a 0x00000007 0x0000000a 0x00000007\n"
           "0000000009e43098: 0x000007d9\n0000000009e61394: 0x00000003\n")
    check("ramdate", parse_ramdate(ram), [10, 7, 10, 7, 2009, 3])
    check("ramdate missing", parse_ramdate("x"), None)
    try:
        parse_set("2011-3-15")
        check("short --set refused", False, True)
    except argparse.ArgumentTypeError:
        check("short --set refused", True, True)
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
    s.add_argument("--set", type=parse_set)
    d = sub.add_parser("decode")
    d.add_argument("log")
    d.add_argument("--base", type=_int, default=0x8F000000)
    i = sub.add_parser("initdate")
    i.add_argument("image")
    i.add_argument("--image-start", type=_int, default=NK_IMAGE_START_EU2011)
    r = sub.add_parser("ramdate")
    r.add_argument("log")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "shim":
        return cmd_shim(args)
    if args.cmd == "decode":
        return cmd_decode(args)
    if args.cmd == "initdate":
        return cmd_initdate(args)
    if args.cmd == "ramdate":
        return cmd_ramdate(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
