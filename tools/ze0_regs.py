#!/usr/bin/env python3
"""Register census for the QEMU ``ze0`` machine (TODO M8.A8).

Sub-commands:

  census LOG [--top N]
        Stream a QEMU ``-d unimp,guest_errors`` log of a ``-M ze0`` boot and
        list every register the machine does **not** model: the catch-all
        lines ``ze0-p4/ze0-area4/ze0-area6: unimplemented device read|write
        (size S, offset O[, value V])`` and the memory-core lines
        ``Invalid read|write at addr A, size S`` (an address with no region
        at all, typically an area-7 alias ``0x1fxxxxxx`` of a P4 register).
        Each address is shown in its P4 form (``0xffxxxxxx``) when it is an
        area-7 alias.  Per address: sizes, reads, writes, first written
        value, source.  Also counts ``Unauthorized access`` lines (user-mode
        P4 access, a guest exception, not a register).

  who IMG ADDR [ADDR ...] [--image-start S ...]
        Which ROM modules hold an address of the register's 4 KiB page in a
        literal pool of an executable section: the P4 page (``0xffe4c000``),
        its area-7 form (``0x1fe4c000``), the ``PAGE_PHYSICAL`` form that
        ``VirtualCopy`` takes (``0x001fe4c0``), or the exact register in
        either form.  Default images: B (``0x3e00200``) and A (``0x200200``).
        A hit is a pool word, not a proven load: ``sh4xref.py --to`` confirms.

Usage:
  ze0_regs.py census qemu.log [--top 80]
  ze0_regs.py who archive/head256.img 0xffe4c01c 0xffc08814
  ze0_regs.py --selftest

Method and results: docs/experiments/EXP-2026-11-20-M8.A8-f0-registers.md
"""

import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CATCH_BASE = {
    "ze0-p4": 0xFF800000,
    "ze0-area4": 0x10000000,
    "ze0-area6": 0x18000000,
}
UNIMP_RE = re.compile(r"(ze0-[a-z0-9]+): unimplemented device (read|write)\s*"
                      r"\(size (\d+), offset 0x([0-9a-fA-F]+)(?:, value 0x([0-9a-fA-F]+))?\)")
INVALID_RE = re.compile(r"Invalid (read|write) at addr 0x([0-9a-fA-F]+), size (\d+)")
UNAUTH = "Unauthorized access"


def p4_form(addr):
    """Area-7 alias 0x1c000000..0x1fffffff -> P4 0xfc000000..0xffffffff."""
    if 0x1C000000 <= addr < 0x20000000:
        return addr | 0xE0000000
    return addr


class Census:
    def __init__(self):
        self.regs = {}
        self.unauth = 0
        self.lines = 0

    def add(self, addr, kind, size, value, source):
        r = self.regs.setdefault(addr, {"sizes": set(), "reads": 0, "writes": 0,
                                         "first_write": None, "sources": set(), "order": len(self.regs)})
        r["sizes"].add(size)
        r["sources"].add(source)
        if kind == "read":
            r["reads"] += 1
        else:
            r["writes"] += 1
            if r["first_write"] is None and value is not None:
                r["first_write"] = value

    def feed(self, line):
        self.lines += 1
        if UNAUTH in line:
            self.unauth += 1
            return
        m = UNIMP_RE.search(line)
        if m:
            base = CATCH_BASE.get(m.group(1))
            if base is None:
                return
            addr = base + int(m.group(4), 16)
            val = int(m.group(5), 16) if m.group(5) else None
            self.add(addr, m.group(2), int(m.group(3)), val, m.group(1))
            return
        m = INVALID_RE.search(line)
        if m:
            raw = int(m.group(2), 16)
            self.add(p4_form(raw), m.group(1), int(m.group(3)), None,
                     "a7-alias" if raw != p4_form(raw) else "unmapped")


def page_forms(addr):
    page = p4_form(addr) & ~0xFFF
    a7 = page & 0x1FFFFFFF
    forms = {page: "page", a7: "a7-page", a7 >> 8: "phys>>8"}
    forms[p4_form(addr)] = "reg"
    forms[p4_form(addr) & 0x1FFFFFFF] = "a7-reg"
    return forms


def scan_words(blob, base, wanted):
    out = []
    start = (-base) % 4
    for off in range(start, len(blob) - 3, 4):
        v = struct.unpack_from("<I", blob, off)[0]
        if v in wanted:
            out.append((base + off, v))
    return out


def cmd_census(args):
    c = Census()
    with open(args.log, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            c.feed(line)
    rows = sorted(c.regs.items())
    print("log lines %d, unmodelled registers %d, Unauthorized access %d"
          % (c.lines, len(rows), c.unauth))
    print("%-10s %-6s %8s %8s %-11s %s" % ("address", "size", "reads", "writes", "first-wr", "source"))
    shown = rows if not args.top else sorted(
        rows, key=lambda kv: -(kv[1]["reads"] + kv[1]["writes"]))[:args.top]
    for addr, r in sorted(shown):
        fw = "0x%08x" % r["first_write"] if r["first_write"] is not None else "-"
        print("0x%08x %-6s %8d %8d %-11s %s" % (addr, "/".join(str(s) for s in sorted(r["sizes"])),
                                               r["reads"], r["writes"], fw, ",".join(sorted(r["sources"]))))
    pages = sorted({a & ~0xFFF for a in c.regs})
    print("pages %d: %s" % (len(pages), " ".join("0x%08x" % p for p in pages)))
    return 0


def cmd_who(args):
    import cerom
    with open(args.image, "rb") as fh:
        data = fh.read(128 << 20)
    starts = args.image_start or [0x3E00200, 0x200200]
    for addr in args.addr:
        forms = page_forms(addr)
        hits = []
        for start in starts:
            rom = cerom.CERom(data, start)
            for mod in rom.modules():
                try:
                    secs = list(rom.o32(mod))
                except (struct.error, ValueError):
                    continue
                for s in secs:
                    if s["flags"] & cerom.IMAGE_SCN_COMPRESSED or not s["flags"] & 0x20000000:
                        continue
                    off = rom.va2file(s["dataptr"])
                    if off is None:
                        continue
                    blob = data[off:off + s["psize"]]
                    for va, v in scan_words(blob, s["realaddr"], forms):
                        hits.append((start, mod["name"], va, v, forms[v]))
        print("0x%08x (page 0x%08x): %d pool word(s)" % (addr, p4_form(addr) & ~0xFFF, len(hits)))
        for start, name, va, v, kind in hits:
            print("  image 0x%x %-24s pool 0x%08x = 0x%08x (%s)" % (start, name, va, v, kind))
    return 0


def selftest():
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))

    c = Census()
    for line in [
        "ze0-p4: unimplemented device write (size 4, offset 0x408814, value 0x00000100)",
        "ze0-p4: unimplemented device read  (size 4, offset 0x408814)",
        "ze0-area6: unimplemented device read  (size 2, offset 0x1400004)",
        "Invalid read at addr 0x1FC08234, size 4, region '(null)', reason: rejected",
        "Invalid write at addr 0xAAAA, size 2, region '(null)', reason: rejected",
        "Unauthorized access",
        "ze0-sdhi0: wr16 +0x00 = 0x0000",
    ]:
        c.feed(line)
    check("p4 register", c.regs[0xFFC08814]["reads"], 1)
    check("first write", c.regs[0xFFC08814]["first_write"], 0x100)
    check("area6 base", 0x19400004 in c.regs, True)
    check("a7 alias shown as P4", 0xFFC08234 in c.regs, True)
    check("low unmapped kept", c.regs[0xAAAA]["sources"], {"unmapped"})
    check("unauthorized counted, not a register", (c.unauth, len(c.regs)), (1, 4))
    check("modelled-device trace line ignored (negative)", c.lines, 7)
    f = page_forms(0xFFE4C01C)
    check("page forms", sorted(f.items()), sorted({0xFFE4C000: "page", 0x1FE4C000: "a7-page",
                                                   0x001FE4C0: "phys>>8", 0xFFE4C01C: "reg",
                                                   0x1FE4C01C: "a7-reg"}.items()))
    blob = struct.pack("<4I", 0x12345678, 0x1FE4C000, 0, 0x001FE4C0)
    check("scan words", scan_words(blob, 0x1000, f), [(0x1004, 0x1FE4C000), (0x100C, 0x001FE4C0)])
    check("scan misaligned base", scan_words(b"\0\0" + blob, 0x0FFE, f),
          [(0x1004, 0x1FE4C000), (0x100C, 0x001FE4C0)])
    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def _int(s):
    return int(s, 0)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("census")
    c.add_argument("log")
    c.add_argument("--top", type=int, default=0)
    w = sub.add_parser("who")
    w.add_argument("image")
    w.add_argument("addr", type=_int, nargs="+")
    w.add_argument("--image-start", type=_int, action="append")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "census":
        return cmd_census(args)
    if args.cmd == "who":
        return cmd_who(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
