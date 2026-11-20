#!/usr/bin/env python3
"""Rank the functions of a CE module by the RDSTM link-group reader signature (M4.49).

The signature is derived from the data-side decode of ``RDSTM001.DAT``
(EXP-2026-11-20-M4.16e, C-5137–C-5139) -- the weakest kind of signature
(rule 14), stated so a miss can be judged:

* ``mask1fff``  -- ``and Rm,Rn`` with a register loaded from a pool literal
  ``0x1fff`` (node index / link id of a 4-byte entry), or ``mov #-1``-free
  equivalents are NOT covered;
* ``addr_build`` -- the container address ``(v >> 8) * 0x800 + (v & 0xff) *
  0x100``: one function holds ``shlr8`` (or ``shlr16``) **and** ``shll8``
  **and** ``extu.b``, and a ``shll2``/``shll`` or a literal ``0x800``;
* ``stride6``  -- ``add #6,Rn`` (6-byte ``(u32 parcel, u16 count)`` rows)
  together with a backward branch (a loop);
* ``head18``   -- ``add #18,Rn`` (18-byte group head before the rows);
* ``swap``     -- ``swap.b`` (big-endian halfwords read on a little-endian
  CPU); a byte-wise reader (``mov.b`` + ``shll8`` + ``or``) counts as
  ``bytebuild``.

Each function of the module's ``.pdata`` gets the set of features it shows;
the output lists the functions with the most features (and every function with
``mask1fff`` and ``addr_build`` together).  Nothing here proves a reader; a
candidate must be confirmed by disassembly and an L3 run.

Usage:
  rdstm_reader_scan.py IMG [--module Navi.exe] [--image-start 0x200200] [--top 40]
  rdstm_reader_scan.py IMG --const 0x14f4      # functions loading a constant
  rdstm_reader_scan.py IMG --graph G.json --roots 0x004003f4,0x00412ac0 [--depth 8]
  rdstm_reader_scan.py IMG --graph G.json --callers-of 0x003c0e68 [--literals 0x1400:0x15ff]
  rdstm_reader_scan.py --selftest

Stdlib only; uses ``tools/cerom.py`` and ``tools/nk_decomp.py`` for the
section table and function table (as ``tools/callgraph.py``).
"""
from __future__ import annotations

import argparse
import collections
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE / "l3_harness"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

FEATURES = ("mask1fff", "addr_build", "stride6", "head18", "swap", "bytebuild", "loop")


def scan(code: bytes, base: int, start: int, length: int) -> dict:
    """Feature counts of one function (``code`` = section bytes at VA ``base``)."""
    lit: dict[int, int] = {}
    pool: set[int] = set()
    f = collections.Counter()
    ops = collections.Counter()
    end = min(start + length, base + len(code))
    pc = start
    while pc + 1 < end:
        if pc in pool:
            pc += 2
            continue
        w = struct.unpack_from("<H", code, pc - base)[0]
        top, n, m, low = w >> 12, (w >> 8) & 15, (w >> 4) & 15, w & 15
        if top == 0x9:                                    # mov.w @(disp,PC),Rn (sign-extended)
            a = pc + 4 + (w & 0xFF) * 2
            pool.add(a)
            if base <= a < base + len(code) - 1:
                v = struct.unpack_from("<H", code, a - base)[0]
                lit[n] = v - 0x10000 if v & 0x8000 else v
        elif top == 0xD:                                  # mov.l @(disp,PC),Rn
            a = (pc & ~3) + 4 + (w & 0xFF) * 4
            pool.update((a, a + 2))
            if base <= a < base + len(code) - 3:
                lit[n] = struct.unpack_from("<I", code, a - base)[0]
        elif top == 0x2 and low == 0x9:                   # and Rm,Rn
            if lit.get(m) == 0x1FFF or lit.get(n) == 0x1FFF:
                f["mask1fff"] += 1
        elif top == 0x4 and (w & 0xFF) in (0x18, 0x19, 0x29, 0x08, 0x00):
            ops[{0x18: "shll8", 0x19: "shlr8", 0x29: "shlr16", 0x08: "shll2", 0x00: "shll"}[w & 0xFF]] += 1
        elif top == 0x6 and low == 0xC:
            ops["extu.b"] += 1
        elif top == 0x6 and low == 0x8:
            f["swap"] += 1
        elif top == 0x6 and low == 0x0:                   # mov.b @Rm,Rn
            ops["movb"] += 1
        elif top == 0x6 and low == 0x4:                   # mov.b @Rm+,Rn
            ops["movb"] += 1
        elif top == 0x2 and low == 0xB:                   # or Rm,Rn
            ops["or"] += 1
        elif top == 0x7:
            imm = w & 0xFF
            if imm == 6:
                ops["add6"] += 1
            elif imm == 18:
                f["head18"] += 1
        elif top == 0x8 and n in (0x9, 0xB, 0xD, 0xF):    # bt/bf/bt.s/bf.s
            d = w & 0xFF
            if d & 0x80:
                f["loop"] += 1
        elif top == 0xA:                                  # bra
            if w & 0x800:
                f["loop"] += 1
        if top not in (0x9, 0xD) and top in (0xE, 0x7, 0x3, 0x6, 0x5):
            lit.pop(n, None)
        if top == 0xE:
            lit[n] = (w & 0xFF) - 0x100 if w & 0x80 else w & 0xFF
        pc += 2
    if (ops["shlr8"] or ops["shlr16"]) and ops["shll8"] and ops["extu.b"] and (ops["shll2"] or ops["shll"]):
        f["addr_build"] += 1
    if ops["add6"] and f["loop"]:
        f["stride6"] += ops["add6"]
    if ops["movb"] and ops["shll8"] and ops["or"]:
        f["bytebuild"] += 1
    return dict(f)


def const_users(code: bytes, base: int, pdata, value: int) -> list[tuple[int, int]]:
    """[(function start, pc)] of every ``mov.w``/``mov.l @(disp,PC)`` that loads ``value``."""
    out = []
    for begin, _p, length in pdata:
        pool: set[int] = set()
        pc, end = begin, min(begin + length, base + len(code))
        while pc + 1 < end:
            if pc in pool:
                pc += 2
                continue
            w = struct.unpack_from("<H", code, pc - base)[0]
            if w >> 12 == 0x9:
                a = pc + 4 + (w & 0xFF) * 2
                pool.add(a)
                if base <= a < base + len(code) - 1 and struct.unpack_from("<H", code, a - base)[0] == value & 0xFFFF \
                        and value < 0x8000:
                    out.append((begin, pc))
            elif w >> 12 == 0xD:
                a = (pc & ~3) + 4 + (w & 0xFF) * 4
                pool.update((a, a + 2))
                if base <= a < base + len(code) - 3 and struct.unpack_from("<I", code, a - base)[0] == value:
                    out.append((begin, pc))
            pc += 2
    return out


def literals_in(code: bytes, base: int, start: int, length: int, lo: int, hi: int) -> list[tuple[int, int]]:
    """[(pc, value)] of ``mov.w``/``mov.l @(disp,PC)`` literals with ``lo <= value <= hi`` in one function."""
    out = []
    pool: set[int] = set()
    pc, end = start, min(start + length, base + len(code))
    while pc + 1 < end:
        if pc in pool:
            pc += 2
            continue
        w = struct.unpack_from("<H", code, pc - base)[0]
        if w >> 12 == 0x9:
            a = pc + 4 + (w & 0xFF) * 2
            pool.add(a)
            if base <= a < base + len(code) - 1:
                v = struct.unpack_from("<H", code, a - base)[0]
                if lo <= v <= hi:
                    out.append((pc, v))
        elif w >> 12 == 0xD:
            a = (pc & ~3) + 4 + (w & 0xFF) * 4
            pool.update((a, a + 2))
            if base <= a < base + len(code) - 3:
                v = struct.unpack_from("<I", code, a - base)[0]
                if lo <= v <= hi:
                    out.append((pc, v))
        pc += 2
    return out


def rank(rows: dict, top: int):
    """rows: {va: features} -> sorted [(score, va, features)] for printing."""
    def score(fe):
        return sum(1 for k in ("mask1fff", "addr_build", "stride6", "head18") if fe.get(k)) * 10 + \
            sum(1 for k in ("swap", "bytebuild") if fe.get(k))
    out = sorted(((score(fe), va, fe) for va, fe in rows.items() if score(fe)), key=lambda x: (-x[0], x[1]))
    return out[:top]


def load_module(image: str, image_start: int, module: str):
    import cerom
    import nk_decomp
    data = Path(image).read_bytes()
    rom = cerom.CERom(data, image_start)
    secs = list(rom.o32(rom.module(module)))
    text = next(s for s in secs if s["flags"] & 0x20000000)
    off = rom.va2file(text["dataptr"])
    code = data[off:off + text["psize"]]
    ro = [s for s in secs if s["flags"] & cerom.IMAGE_SCN_COMPRESSED and not s["flags"] & 0x80000000]
    if len(ro) != 1:
        raise SystemExit("cannot pick the pdata section of %s" % module)
    r0, blob = nk_decomp.decompress(data, rom.va2file(ro[0]["dataptr"]), ro[0]["psize"], ro[0]["vsize"])
    return code, text["realaddr"], nk_decomp.parse_pdata(blob[:r0])


def subtree(graph_path: str, roots: list[int], depth: int) -> tuple[set[int], int]:
    """Functions reachable from ``roots`` (inclusive) in a ``callgraph.py`` graph, and their unresolved calls."""
    import callgraph
    g, fwd, _rev = callgraph.load(graph_path)
    seen = set(roots)
    for r in roots:
        seen.update(v for _d, v in callgraph.walk(fwd, r, depth))
    unresolved = sum(g[k].get("unresolved", 0) for k in g if int(k, 0) in seen)
    return seen, unresolved


def cmd_scan(a) -> int:
    code, base, pdata = load_module(a.image, a.image_start, a.module)
    if a.graph and a.roots:
        roots = [int(x, 0) for x in a.roots.split(",")]
        keep, unres = subtree(a.graph, roots, a.depth)
        pdata = [p for p in pdata if p[0] in keep]
        print(f"restricted to {len(pdata)} functions reachable from {len(roots)} roots "
              f"(depth {a.depth}; {unres} unresolved indirect calls inside)")
    if a.callers_of:
        import callgraph
        _g, _fwd, rev = callgraph.load(a.graph)
        lo, hi = (int(x, 0) for x in a.literals.split(":"))
        target = int(a.callers_of, 0)
        callers = sorted(set(rev.get(target, [])))
        size = {b: n for b, _p, n in pdata}
        census: dict = collections.Counter()
        print(f"callers of 0x{target:08x}: {len(callers)}; literals in [0x{lo:x}, 0x{hi:x}]")
        for fn in callers:
            lits = literals_in(code, base, fn, size.get(fn, 0), lo, hi)
            for _pc, v in lits:
                census[v] += 1
            print(f"  fn 0x{fn:08x}: " + (" ".join(f"0x{v:x}@0x{pc:08x}" for pc, v in lits) or "-"))
        print("ids: " + ", ".join(f"0x{v:x} x{n}" for v, n in sorted(census.items())))
        return 0
    if a.const is not None:
        hits = const_users(code, base, pdata, a.const)
        print(f"module {a.module}: loads of 0x{a.const:x}: {len(hits)}")
        for fn, pc in hits:
            print(f"  fn 0x{fn:08x}  at 0x{pc:08x}")
        return 0
    rows = {begin: scan(code, base, begin, length) for begin, _p, length in pdata}
    tot = collections.Counter()
    for fe in rows.values():
        for k in fe:
            tot[k] += 1
    print(f"module {a.module} image_start 0x{a.image_start:x}: functions {len(rows)}, code {len(code)} B")
    print("functions with feature: " + ", ".join(f"{k} {tot[k]}" for k in FEATURES))
    both = [va for va, fe in rows.items() if fe.get("mask1fff") and fe.get("addr_build")]
    print(f"mask1fff and addr_build together: {len(both)} " + " ".join(f"0x{v:08x}" for v in sorted(both)))
    print("score  va          features")
    for s, va, fe in rank(rows, a.top):
        print(f"{s:5d}  0x{va:08x}  " + " ".join(f"{k}={fe[k]}" for k in FEATURES if fe.get(k)))
    return 0


def _asm(words) -> bytes:
    return b"".join(struct.pack("<H", w) for w in words)


def selftest() -> int:
    fails = []

    def check(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    base = 0x10000
    # fn A at base: mov.w @(disp,PC),r1 -> 0x1fff ; and r1,r2 ; shlr8 r3 ; shll8 r4 ; extu.b r5,r6 ;
    # shll2 r4 ; add #6,r7 ; bf back ; rts ; nop ; pool 0x1fff
    a = [0x9108,            # mov.w @(PC+4+8*2),r1 -> the pool word 0x1fff
         0x2219,            # and r1,r2
         0x4319,            # shlr8 r3
         0x4418,            # shll8 r4
         0x665C,            # extu.b r5,r6
         0x4408,            # shll2 r4
         0x7706,            # add #6,r7
         0x8BF8,            # bf back
         0x000B, 0x0009,
         0x1FFF, 0x0000]
    # fn B: nothing of interest; a lone and with a non-0x1fff literal
    b = [0xE10F, 0x2219, 0x000B, 0x0009]
    code = _asm(a + b)
    fa = scan(code, base, base, 2 * len(a))
    check("mask1fff found", fa.get("mask1fff") == 1)
    check("addr_build found", fa.get("addr_build") == 1)
    check("stride6 in a loop", fa.get("stride6") == 1 and fa.get("loop") == 1)
    fb = scan(code, base, base + 2 * len(a), 2 * len(b))
    check("plain function empty", not fb.get("mask1fff") and not fb.get("addr_build"))
    hits = const_users(code, base, [(base, 0, 2 * len(a)), (base + 2 * len(a), 0, 2 * len(b))], 0x1FFF)
    check("const users", hits == [(base, base)])
    check("literals in range", literals_in(code, base, base, 2 * len(a), 0x1000, 0x2000) == [(base, 0x1FFF)])
    r = rank({base: fa, base + 24: fb}, 5)
    check("rank puts A first", r and r[0][1] == base and r[0][0] == 30 and len(r) == 1)
    print("selftest:", "FAIL" if fails else "PASS")
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("image", nargs="?")
    ap.add_argument("--module", default="Navi.exe")
    ap.add_argument("--image-start", type=lambda s: int(s, 0), default=0x200200)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--graph", help="callgraph.py graph JSON; with --roots, scan only the reachable subtree")
    ap.add_argument("--roots", default="", help="comma-separated root VAs for --graph")
    ap.add_argument("--depth", type=int, default=8)
    ap.add_argument("--callers-of", help="with --graph: list the pool literals in --literals LO:HI of each caller of this VA")
    ap.add_argument("--literals", default="0x1400:0x15ff")
    ap.add_argument("--const", type=lambda s: int(s, 0), default=None,
                    help="list the functions that load this constant from a literal pool instead")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.image:
        ap.print_help()
        return 2
    return cmd_scan(a)


if __name__ == "__main__":
    sys.exit(main())
