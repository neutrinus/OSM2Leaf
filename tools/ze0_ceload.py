#!/usr/bin/env python3
"""Plan the ``-M ze0 -kernel`` CE image load the way the machine does (TODO M8.A3).

The ZE0 SD card has no boot loader, so ``ze0-0004`` teaches the QEMU machine
to load the CE images itself: ``-kernel SD-IMAGE`` with the machine options
``kernel-off=`` (default ``0x3e00200``, EU2011 image B) and ``app-off=``
(default ``0x200200``, image A; 0 = none).  This tool is a second,
independent implementation of the same rule, so its plan can be compared
line by line with the ``info:`` lines QEMU prints:

  * ``ECEC`` at image + 0x40, pTOC (ROMHDR VA) at + 0x44, the ROMHDR's
    offset from the image start at + 0x48; physfirst = pTOC - that offset
    and must equal ROMHDR physfirst (+0x08);
  * the image is physfirst .. physlast (ROMHDR +0x0c) and lands at
    ``physfirst & 0x1fffffff``;
  * the entry is ``e32_vbase + e32_entryrva`` of the ``nk.exe`` TOC entry
    (32-byte entries after the 0x54-byte ROMHDR; name VA at +0x10,
    ulE32Offset at +0x14; e32_rom entryrva at +4, vbase at +8).

The old ``run.sh`` cut length (the u32 at the image start, C-1283) is
printed beside it for comparison.

``trace LOG...`` compares boots: for each ``-d unimp,guest_errors,int``
log it prints the exception counts and a SHA-256 over the ordered
``(code, pc)`` list without the timer interrupts (INTEVT ``0x400`` arrives
on host time, so its count and position differ run to run), plus the
unmodelled-access list (``ce_qemu_probe.summarize_log``).

Usage:
  ze0_ceload.py plan IMAGE [--kernel-off 0x3e00200] [--app-off 0x200200]
  ze0_ceload.py trace LOG [LOG...]
  ze0_ceload.py --selftest

Method and results: docs/experiments/EXP-2026-11-20-M8.A3-builtin-loader.md
"""

import argparse
import hashlib
import os
import struct
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ce_qemu_probe import summarize_log  # noqa: E402

ROMHDR_LEN = 0x54
TOCENTRY_LEN = 32
CE_MAX_LEN = 256 << 20
RAM_BASE, RAM_SIZE = 0x08000000, 128 << 20


class LoadError(Exception):
    pass


def _read(fh, off, n):
    fh.seek(off)
    data = fh.read(n)
    if len(data) != n:
        raise LoadError("cannot read %d bytes at file offset 0x%x" % (n, off))
    return data


def plan_image(fh, off, want_entry):
    """dict(physfirst, physlast, len, phys, entry, oldlen) for one CE image."""
    hdr = _read(fh, off, 0x4C)
    if hdr[0x40:0x44] != b"ECEC":
        raise LoadError("no ECEC at file offset 0x%x (+0x40)" % (off + 0x40))
    ptoc, roff = struct.unpack_from("<II", hdr, 0x44)
    rh = _read(fh, off + roff, ROMHDR_LEN)
    physfirst, physlast, nummods = struct.unpack_from("<III", rh, 0x08)
    if physfirst != (ptoc - roff) & 0xFFFFFFFF or physlast <= physfirst \
            or physlast - physfirst > CE_MAX_LEN:
        raise LoadError("inconsistent ROMHDR (pTOC 0x%08x, offset 0x%x, physfirst 0x%08x, "
                        "physlast 0x%08x)" % (ptoc, roff, physfirst, physlast))
    length = physlast - physfirst
    phys = physfirst & 0x1FFFFFFF
    if phys < RAM_BASE or phys + length > RAM_BASE + RAM_SIZE:
        raise LoadError("image 0x%08x..0x%08x is outside DRAM" % (phys, phys + length))
    out = {"physfirst": physfirst, "physlast": physlast, "len": length, "phys": phys,
           "entry": None, "nummods": nummods,
           "oldlen": struct.unpack_from("<I", hdr, 0)[0]}
    if want_entry:
        body = _read(fh, off, length)
        for i in range(nummods):
            te = roff + ROMHDR_LEN + i * TOCENTRY_LEN
            if te + TOCENTRY_LEN > length:
                break
            nva, e32va = struct.unpack_from("<II", body, te + 0x10)
            n, e = nva - physfirst, e32va - physfirst
            if not (0 <= n and n + 7 <= length and 0 <= e and e + 12 <= length):
                continue
            if body[n:n + 7].lower() == b"nk.exe\0":
                erva, vbase = struct.unpack_from("<II", body, e + 4)
                out["entry"] = (vbase + erva) & 0xFFFFFFFF
                break
        if out["entry"] is None:
            raise LoadError("no nk.exe in its %d TOC entries" % nummods)
    return out


def plan(path, kernel_off, app_off):
    with open(path, "rb") as fh:
        rows = [("kernel", kernel_off, plan_image(fh, kernel_off, True))]
        if app_off:
            rows.append(("app", app_off, plan_image(fh, app_off, False)))
    return rows


def format_rows(rows):
    lines = []
    for what, off, p in rows:
        lines.append("%s image at file 0x%x: VA 0x%08x..0x%08x (%d bytes) -> phys 0x%08x"
                     % (what, off, p["physfirst"], p["physlast"], p["len"], p["phys"]))
        if p["entry"] is not None:
            lines.append("entry 0x%08x (nk.exe e32_vbase + e32_entryrva)" % p["entry"])
        lines.append("  (old run.sh cut length, u32 at the image start: %d bytes)" % p["oldlen"])
    return lines


def cmd_plan(args):
    try:
        rows = plan(args.image, args.kernel_off, args.app_off)
    except LoadError as exc:
        print("ze0_ceload: %s" % exc)
        return 1
    print("\n".join(format_rows(rows)))
    return 0


def trace_digest(text):
    """(Counter of exception codes, sha256 of non-0x400 (code, pc), access list)."""
    accesses, exceptions = summarize_log(text)
    counts = Counter(code for code, _name, _pc in exceptions)
    seq = ["0x%03x@%s" % (code, "0x%08x" % pc if pc is not None else "?")
           for code, _name, pc in exceptions if code != 0x400]
    digest = hashlib.sha256("\n".join(seq).encode()).hexdigest()[:16]
    return counts, digest, len(seq), accesses


def cmd_trace(args):
    for path in args.logs:
        with open(path, "r", errors="replace") as fh:
            counts, digest, n, accesses = trace_digest(fh.read())
        print("%s: %s | non-0x400 sequence %d events sha256:%s | unmodelled accesses %d"
              % (path, " ".join("0x%03x x%d" % (c, counts[c]) for c in sorted(counts)),
                 n, digest, len(accesses)))
    return 0


def synth_image(entry_name=b"nk.exe"):
    """A tiny SD image: one CE image at 0x400, VA 0x88000000, 2 TOC entries."""
    base, off, length = 0x88000000, 0x400, 0x800
    img = bytearray(off + length + 0x200)
    struct.pack_into("<I", img, off, 0x24)             # the misleading old length word
    img[off + 0x40:off + 0x44] = b"ECEC"
    struct.pack_into("<II", img, off + 0x44, base + 0x100, 0x100)
    struct.pack_into("<III", img, off + 0x100 + 0x08, base, base + length, 2)
    for i, (name_off, e32_off) in enumerate(((0x400, 0x420), (0x440, 0x460))):
        te = off + 0x100 + ROMHDR_LEN + i * TOCENTRY_LEN
        struct.pack_into("<II", img, te + 0x10, base + name_off, base + e32_off)
    img[off + 0x400:off + 0x408] = b"gwes.exe"
    img[off + 0x440:off + 0x447] = entry_name + b"\0"
    struct.pack_into("<HHII", img, off + 0x420, 1, 0, 0x99, 0x88100000)
    struct.pack_into("<HHII", img, off + 0x460, 1, 0, 0xEBD0, base)
    return bytes(img), off


def selftest():
    import io

    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))

    img, off = synth_image()
    p = plan_image(io.BytesIO(img), off, True)
    check("physfirst", p["physfirst"], 0x88000000)
    check("len from ROMHDR, not the u32 at the start", (p["len"], p["oldlen"]), (0x800, 0x24))
    check("phys", p["phys"], 0x08000000)
    check("entry = vbase + entryrva of nk.exe (second TOC entry)", p["entry"], 0x8800EBD0)
    for label, image, o in (
            ("wrong offset refused", img, off - 0x200),
            ("no nk.exe refused", synth_image(b"nk.dll")[0], off),
            ("short file refused", img[:off + 0x20], off)):
        try:
            plan_image(io.BytesIO(image), o, True)
            check(label, "loaded", "LoadError")
        except LoadError:
            check(label, "LoadError", "LoadError")
    bad = bytearray(img)
    struct.pack_into("<I", bad, off + 0x48, 0xF0)     # ROMHDR offset disagrees with pTOC
    try:
        plan_image(io.BytesIO(bytes(bad)), off, True)
        check("pTOC/offset mismatch refused", "loaded", "LoadError")
    except LoadError:
        check("pTOC/offset mismatch refused", "LoadError", "LoadError")
    log = ("exception 0x040 [tlb_miss] raised\npc=0x88000010 sr=0\n"
           "exception 0x400 [interrupt] raised\npc=0x88000020 sr=0\n"
           "exception 0x180 [illegal_instruction] raised\npc=0x88000030 sr=0\n")
    c1, d1, n1, _a = trace_digest(log)
    c2, d2, _n, _a = trace_digest(log.replace("0x400 [interrupt] raised\npc=0x88000020",
                                              "0x400 [interrupt] raised\npc=0x88000024"))
    c3, d3, _n, _a = trace_digest(log.replace("pc=0x88000030", "pc=0x88000032"))
    check("trace counts", (c1[0x40], c1[0x400], c1[0x180], n1), (1, 1, 1, 2))
    check("trace ignores 0x400 placement", d1 == d2, True)
    check("trace sees a moved fault", d1 == d3, False)
    rows = [("kernel", off, p)]
    check("format", format_rows(rows)[1], "entry 0x8800ebd0 (nk.exe e32_vbase + e32_entryrva)")
    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("plan")
    p.add_argument("image")
    p.add_argument("--kernel-off", type=lambda s: int(s, 0), default=0x3E00200)
    p.add_argument("--app-off", type=lambda s: int(s, 0), default=0x200200)
    t = sub.add_parser("trace")
    t.add_argument("logs", nargs="+")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "plan":
        return cmd_plan(args)
    if args.cmd == "trace":
        return cmd_trace(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
