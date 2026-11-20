#!/usr/bin/env python3
"""Four halfword signature families for an INTER/FRWAY record walker (M3.16).

The 12-byte record table at ``0x1108`` is big-endian (C-2215): ``u16 key``
(``0xffff`` terminator at +0), ``u16 0`` (+2), ``u8 id`` (+4), ``u8 flag``
(+5), ``u16 length`` (+6), ``u16 b8`` (+8), ``u16 offset`` (+10).  A walker
loads a ``u16`` (the key), compares it to ``0xffff``, then advances the
cursor by 12 bytes.  This tool scans one CE build's uncompressed executable
halfwords for that shape and its neighbours.

Halfwords are little-endian (AGENTS.md: SH-4 code here is little-endian); a
big-endian search finds nothing.  A pattern scan is halfword arithmetic, not
disassembly.  Families (each stated before the search):

  f1  ``mov.w @(8,Rm),R0`` + ``cmp/eq #-1,R0`` + ``add #12,Rn``
      (r2's writer-inverse: terminator assumed at record +8 -- refuted, C-2216)
  f2  ``mov #0x11,Rn`` + ``shll8 Rn`` + ``add #8,Rn`` in one register
      (r2's ``0x1108`` table-offset construction)
  f3  ``mov.w @Rm,R0`` + ``add #12,Rn`` + ``cmp/eq #-1,R0``
      (the corrected shape: key loaded from a register pointer)
  f4  ``mov.w @(10,Rm),R0`` + ``mov.w @(6,Rm),R0`` + ``add #12,Rn``
      (reads the real +10 offset / +6 length, no explicit key compare)

Every f1/f3 hit reports the ``cmp/eq #imm,R0`` immediates within the window,
so a reader sees whether the candidate really tests ``0xffff``.

Usage::

  inter_reader_scan.py --selftest
  inter_reader_scan.py scan IMG [--image-start 0x200200] [--module Navi.exe]
  inter_reader_scan.py scan IMG --family 3

Exit codes: 0 ok, 1 selftest failed / corpus read error, 2 usage error.
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cerom  # noqa: E402
import sh4dis  # noqa: E402

IMG_START = 0x200200
MODULE = "Navi.exe"
WINDOW = 16                 # halfwords on each side of the comparator

CMP_EQ_IMM_R0 = 0x8800      # 0x88ii
ADD_IMM_RN = 0x7000         # 0x7nii
MOV_IMM_RN = 0xE000         # 0xEnii
SHLL8_RN = 0x4018           # 0x4n18
MOVW_AT_RM_R0 = 0x6000      # 0x6n m 0, mask 0xF00F
MOVW_DISP_R0 = 0x8500       # 0x85md: match (h & 0xFF00), disp = h & 0xF


def _add12(h):
    return (h & 0xF0FF) == (ADD_IMM_RN | 0x0C)


def _colour(vals, i, lo=-WINDOW, hi=WINDOW):
    lo_i = max(0, i + lo)
    hi_i = min(len(vals), i + hi + 1)
    return vals[lo_i:hi_i]


def family(vals, base_va: int, fam: int):
    """Return [(va, [cmp/eq imm near hit])] for one family over ``vals``."""
    hits = []
    n = len(vals)
    for i in range(n):
        v = vals[i]
        ok = False
        if fam in (1, 3):
            if v != (CMP_EQ_IMM_R0 | 0xFF):
                continue
            ctx = _colour(vals, i)
            if fam == 1:
                movw8 = any((h & 0xFF00) == MOVW_DISP_R0 and (h & 0xF) == 4
                            for h in ctx)
                ok = movw8 and any(_add12(h) for h in ctx)
            else:
                movw = any((h & 0xF00F) == MOVW_AT_RM_R0 for h in ctx)
                ok = movw and any(_add12(h) for h in ctx)
        elif fam == 2:
            if (v & 0xF0FF) != (MOV_IMM_RN | 0x11):
                continue
            reg = (v >> 8) & 0xF
            shll8 = SHLL8_RN | (reg << 8)
            w = list(vals[i + 1:i + 7])
            if shll8 in w:
                k = w.index(shll8)
                ok = any(h == (ADD_IMM_RN | (reg << 8) | 0x08) for h in w[k + 1:])
        elif fam == 4:
            if (v & 0xFF00) != MOVW_DISP_R0 or (v & 0xF) != 5:
                continue
            w = list(vals[i + 1:i + 7])
            ok = (any((h & 0xFF00) == MOVW_DISP_R0 and (h & 0xF) == 3 for h in w)
                  and any(_add12(h) for h in w))
        if ok:
            near = sorted({h & 0xFF for h in _colour(vals, i)
                           if (h & 0xFF00) == CMP_EQ_IMM_R0})
            hits.append((base_va + i * 2, near))
    return hits


def load_module(data: bytes, image_start: int, module: str):
    """Return (halfwords, va, psize, vsize) of sec0 of ``module``."""
    rom = cerom.CERom(data, image_start)
    for mod in rom.modules():
        if (mod["name"] or "").lower() != module.lower():
            continue
        sec = list(rom.o32(mod))[0]
        if sec["flags"] & cerom.IMAGE_SCN_COMPRESSED:
            raise ValueError("%s sec0 is compressed; this scan needs code" % module)
        off = rom.va2file(sec["dataptr"])
        blob = data[off:off + sec["psize"]]
        if len(blob) != sec["psize"]:
            raise ValueError("%s sec0 runs past the read window" % module)
        return sh4dis.halfwords_le(blob), sec["realaddr"], sec["psize"], sec["vsize"]
    raise ValueError("module %r not found" % module)


def synthetic():
    """Halfword corpus with one hit per family at known indices."""
    words = [0x0009] * 64          # nop filler
    words[4] = MOVW_DISP_R0 | (2 << 4) | 0x04  # f1: mov.w @(8,R2),R0
    words[8] = CMP_EQ_IMM_R0 | 0xFF
    words[10] = ADD_IMM_RN | 0x0C
    words[20] = MOV_IMM_RN | (3 << 8) | 0x11  # f2
    words[21] = SHLL8_RN | (3 << 8)
    words[22] = ADD_IMM_RN | (3 << 8) | 0x08
    words[30] = MOVW_AT_RM_R0 | (2 << 8)      # f3
    words[32] = CMP_EQ_IMM_R0 | 0xFF
    words[33] = ADD_IMM_RN | 0x0C
    words[44] = MOVW_DISP_R0 | (2 << 4) | 0x05  # f4
    words[45] = MOVW_DISP_R0 | (2 << 4) | 0x03
    words[46] = ADD_IMM_RN | 0x0C
    return words


def selftest() -> int:
    fails = 0

    def check_(name, cond):
        nonlocal fails
        print("%-54s %s" % (name, "ok" if cond else "FAIL"))
        fails += not cond

    vals = synthetic()
    got = {f: [va for va, _ in family(vals, 0x1000, f)] for f in (1, 2, 3, 4)}
    check_("f1 finds index 8", got[1] == [0x1000 + 8 * 2])
    check_("f2 finds index 20", got[2] == [0x1000 + 20 * 2])
    check_("f3 finds index 32", got[3] == [0x1000 + 32 * 2])
    check_("f4 finds index 44", got[4] == [0x1000 + 44 * 2])
    check_("f3 reports the 0xff comparator", family(vals, 0x1000, 3)[0][1] == [0xFF])
    bad = [0x7010 if h == (ADD_IMM_RN | 0x0C) else h for h in vals]
    check_("f3 misses without add #12", family(bad, 0x1000, 3) == [])
    print("selftest:", "PASS" if not fails else "FAIL (%d)" % fails)
    return 0 if not fails else 1


def cmd_scan(args) -> int:
    with open(args.image, "rb") as f:
        data = f.read(256 << 20)
    vals, va0, psize, vsize = load_module(data, args.image_start, args.module)
    print(f"corpus {args.module} sec0 {psize} B stored / {vsize} B vsize at VA "
          f"{va0:#x} (uncompressed executable, C-2128)")
    fams = [args.family] if args.family else [1, 2, 3, 4]
    for f in fams:
        hits = family(vals, va0, f)
        shown = ", ".join(f"{va:#010x}(cmp/eq {','.join('%#04x' % i for i in n)})"
                          for va, n in hits[:20])
        print(f"f{f}: {len(hits)} candidate(s)  {shown}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("scan")
    s.add_argument("image")
    s.add_argument("--image-start", type=lambda x: int(x, 0), default=IMG_START)
    s.add_argument("--module", default=MODULE)
    s.add_argument("--family", type=int, choices=(1, 2, 3, 4))
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "scan":
        try:
            return cmd_scan(args)
        except ValueError as e:
            print("error:", e, file=sys.stderr)
            return 1
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
