#!/usr/bin/env python3
"""Search Navi.exe's executable sections for a 16-bit byte-order swap (M3.11b).

The POINT walker ``fn 0x003f5194`` reads native u16 words, but the file stores
each record header big-endian (C-2542). Some firmware code must turn the
inflated page into native order. This scan looks for the three shapes that
such code can take on SH-4, as halfword patterns (little-endian, even VAs
only, the same reading as ``sh4scan.py``):

  loop     a backward branch, at most ``--span`` halfwords after its target,
           whose body holds a swap op (``swap.b``, ``swap.w``, ``xtrct``,
           ``shll8``), a load and a store: the "swap loop" the task names
  pair     ``shll8`` within 6 halfwords of an ``or Rm,Rn``: the byte-pair
           assembly ``mov.b`` + ``shll8`` + ``or``
  swap32   ``swap.b`` and ``swap.w`` within 3 halfwords of each other: the
           32-bit ``swap.b; swap.w; swap.b`` form

A zero count is only a result when the same scan finds the planted loop in a
copy of the real bytes (``control``). ``--selftest`` pins the encodings.

Usage::

  point_swap_scan.py --selftest
  point_swap_scan.py scan IMG --image-start 0x200200 [--module Navi.exe]
                      [--range LO:HI] [--list]
  point_swap_scan.py control IMG --image-start 0x200200 [--module Navi.exe]
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from array import array

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cerom  # noqa: E402
import sh4scan  # noqa: E402

MEM_EXECUTE = 0x20000000
CNT_CODE = 0x00000020
SPAN = 24            # halfwords between a backward branch and its target
PAIR_SPAN = 6        # halfwords between shll8 and or (byte-pair assembly)
SWAP32_SPAN = 3      # halfwords between swap.b and swap.w (32-bit swap)


def _enc(word, mask, value):
    return (word & mask) == value


def is_swap_b(w):
    return _enc(w, 0xF00F, 0x6008)


def is_swap_w(w):
    return _enc(w, 0xF00F, 0x6009)


def is_xtrct(w):
    return _enc(w, 0xF00F, 0x200D)


def is_shll8(w):
    return _enc(w, 0xF0FF, 0x4018)


def is_or(w):
    return _enc(w, 0xF00F, 0x200B)


def is_load(w):
    return (w & 0xF000) == 0x6000 and (w & 0xF) in (0, 1, 2, 4, 5, 6)


def is_store(w):
    return (w & 0xF000) == 0x2000 and (w & 0xF) in (0, 1, 2, 4, 5, 6)


def is_w_load(w):
    return (w & 0xF00F) in (0x6001, 0x6005)


def is_w_store(w):
    return (w & 0xF00F) in (0x2001, 0x2005)


def is_b_load(w):
    return (w & 0xF00F) in (0x6000, 0x6004)


def is_b_store(w):
    return (w & 0xF00F) in (0x2000, 0x2004)


def is_swap_op(w):
    return is_swap_b(w) or is_swap_w(w) or is_xtrct(w) or is_shll8(w)


def branch_target(vals_index, w, va_of_index):
    """Target VA of a PC-relative branch at halfword index, or None."""
    pc = va_of_index(vals_index)
    if (w & 0xFF00) in (0x8900, 0x8B00, 0x8D00, 0x8F00):      # bt, bf, bt/s, bf/s
        disp = w & 0xFF
        disp = disp - 256 if disp & 0x80 else disp
        return pc + 4 + 2 * disp
    if (w & 0xF000) == 0xA000:                                 # bra
        disp = w & 0xFFF
        disp = disp - 0x1000 if disp & 0x800 else disp
        return pc + 4 + 2 * disp
    return None


def swap_dataflow(body):
    """mov.w load into Rd, swap.b Rm,Rn with Rm == Rd, then a mov.w store."""
    for j, x in enumerate(body):
        if not is_w_load(x):
            continue
        d = (x >> 8) & 0xF
        for k in range(j + 1, len(body)):
            v = body[k]
            if is_swap_b(v) and ((v >> 4) & 0xF) == d:
                if any(is_w_store(y) for y in body[k + 1:]):
                    return True
    return False


def pair_dataflow(vals, i):
    """shll8 Rd, with a mov.b load into Rd in the 3 halfwords before and an
    ``or`` that reads or writes Rd in the 3 halfwords after."""
    d = (vals[i] >> 8) & 0xF
    loaded = any(is_b_load(vals[j]) and ((vals[j] >> 8) & 0xF) == d
                 for j in range(max(0, i - 3), i))
    if not loaded:
        return False
    for j in range(i + 1, min(len(vals), i + 4)):
        v = vals[j]
        if is_or(v) and d in (((v >> 8) & 0xF), ((v >> 4) & 0xF)):
            return True
    return False


def scan_vals(vals, va, lo=None, hi=None, span=SPAN):
    """Return the swap-shape hits for one halfword array starting at VA ``va``.

    ``lo``/``hi`` (VA, half-open) restrict the reported sites, not the search.
    """
    def va_of(i):
        return va + 2 * i

    def inside(a):
        return (lo is None or a >= lo) and (hi is None or a < hi)

    n = len(vals)
    out = {"loop": [], "loop16": [], "loop16_exact": [], "loopb": [], "pair": [],
           "pair_strict": [], "swap32": [],
           "swap_b": [], "swap_w": [], "xtrct": [], "shll8": []}
    for i in range(n):
        w = vals[i]
        a = va_of(i)
        if inside(a):
            if is_swap_b(w):
                out["swap_b"].append(a)
            elif is_swap_w(w):
                out["swap_w"].append(a)
            elif is_xtrct(w):
                out["xtrct"].append(a)
            elif is_shll8(w):
                out["shll8"].append(a)
        if is_shll8(w) and inside(a) and pair_dataflow(vals, i):
            out["pair_strict"].append(a)
        if is_shll8(w):
            for j in range(i + 1, min(n, i + 1 + PAIR_SPAN)):
                if is_or(vals[j]):
                    if inside(a):
                        out["pair"].append(a)
                    break
        if is_swap_b(w):
            for j in range(i + 1, min(n, i + 1 + SWAP32_SPAN + 1)):
                if is_swap_w(vals[j]):
                    if inside(a):
                        out["swap32"].append(a)
                    break
        t = branch_target(i, w, va_of)
        if t is None or t >= a:
            continue
        s = (t - va) // 2
        if (t - va) % 2 or s < 0 or i - s > span:
            continue
        body = vals[s:i + 1]
        if any(is_swap_op(x) for x in body) and any(is_load(x) for x in body) \
                and any(is_store(x) for x in body) and inside(a):
            out["loop"].append((t, a))
            if any(is_w_load(x) for x in body) and any(is_w_store(x) for x in body) \
                    and any(is_swap_op(x) for x in body):
                out["loop16"].append((t, a))
            if swap_dataflow(body):
                out["loop16_exact"].append((t, a))
            if any(is_b_load(x) for x in body) and any(is_b_store(x) for x in body) \
                    and any(is_shll8(x) for x in body) and any(is_or(x) for x in body):
                out["loopb"].append((t, a))
    return out


def count_summary(res):
    return {k: len(v) for k, v in res.items()}


def code_sections(secs):
    return [s for s in secs if not s.compressed and (s.flags & (CNT_CODE | MEM_EXECUTE))]


def scan_secs(secs, lo=None, hi=None):
    total = {"loop": [], "loop16": [], "loop16_exact": [], "loopb": [], "pair": [],
             "pair_strict": [], "swap32": [],
             "swap_b": [], "swap_w": [], "xtrct": [], "shll8": []}
    for sec in code_sections(secs):
        res = scan_vals(sec.vals, sec.va, lo, hi)
        for k in total:
            total[k].extend(res[k])
    return total


def _parse_range(text):
    if not text:
        return None, None
    lo, hi = text.split(":")
    return int(lo, 0), int(hi, 0)


def _load(args):
    size = os.path.getsize(args.image)
    with open(args.image, "rb") as fh:
        data = fh.read(args.read_mib << 20)
    digest = hashlib.sha256(data).hexdigest()
    r = cerom.CERom(data, args.image_start)
    secs = sh4scan.load_sections(r, data, args.module)
    return size, digest, secs


def cmd_scan(args, secs):
    lo, hi = _parse_range(args.range)
    code = code_sections(secs)
    print("code corpus: %d uncompressed executable sections, %d B vsize; compressed "
          "executable sections skipped: %d"
          % (len(code), sum(s.vsize for s in code),
             sum(1 for s in secs if s.compressed and (s.flags & (CNT_CODE | MEM_EXECUTE)))))
    total = scan_secs(secs, lo, hi)
    for k in ("swap_b", "swap_w", "xtrct", "shll8", "pair", "pair_strict", "swap32", "loop",
              "loop16", "loop16_exact", "loopb"):
        print("%-8s %6d" % (k, len(total[k])))
    if args.list:
        for k in ("loop", "loop16", "loop16_exact", "loopb"):
            for t, a in total[k]:
                print("%-6s branch 0x%08x -> target 0x%08x" % (k, a, t))
        for k in ("pair", "pair_strict", "swap32"):
            for a in total[k]:
                print("%-6s 0x%08x" % (k, a))
    return 0


def cmd_control(args, secs):
    """Plant one swap loop in a copy of the real Navi.exe code; expect +1 loop."""
    code = code_sections(secs)
    if not code:
        print("error: no executable section", file=sys.stderr)
        return 1
    sec = code[0]
    base = scan_secs(secs)
    planted = array("H", sec.vals)
    # loop: mov.w @r5+,r0; swap.b r0,r0; mov.w r0,@-r6; dt r7; bf back (-12 B)
    loop = [0x6055, 0x6008, 0x2605, 0x4710, 0x8BFA]
    # place it at the first halfword that is not already a swap or branch
    at = 64
    for k, v in enumerate(loop):
        planted[at + k] = v
    planted_secs = []
    for s in secs:
        if s is sec:
            c = sh4scan.Sec(module=s.module, index=s.index, va=s.va, file_off=s.file_off,
                            psize=s.psize, vsize=s.vsize, flags=s.flags, compressed=False,
                            blob=s.blob, vals=planted)
            planted_secs.append(c)
        else:
            planted_secs.append(s)
    res = scan_secs(planted_secs)
    target = sec.va + 2 * at
    got = [(t, a) for t, a in res["loop"] if t == target]
    print("control: planted loop at 0x%08x (branch 0x%08x)" % (target, sec.va + 2 * (at + 4)))
    print("baseline loops %d, with planted loop %d; exact mov.w/swap.b/mov.w loops %d -> %d; "
          "planted loop found: %s" % (len(base["loop"]), len(res["loop"]),
                                      len(base["loop16_exact"]), len(res["loop16_exact"]),
                                      "yes" if got else "NO"))
    ok = (len(res["loop"]) == len(base["loop"]) + 1 and bool(got)
          and len(res["loop16_exact"]) == len(base["loop16_exact"]) + 1)
    print("control:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def _hw(*words):
    return array("H", words)


def selftest():
    fails = 0

    def check(name, cond):
        nonlocal fails
        print("%-60s %s" % (name, "ok" if cond else "FAIL"))
        fails += not cond

    # encodings
    check("swap.b r0,r0 = 0x6008", is_swap_b(0x6008))
    check("swap.w r0,r0 = 0x6009", is_swap_w(0x6009))
    check("shll8 r0 = 0x4018", is_shll8(0x4018))
    check("or r1,r6 is not a swap op", not is_swap_op(0x261B))
    check("mov.w @r5+,r0 is a load", is_load(0x6055))
    check("mov.w r0,@-r6 is a store", is_store(0x2605))
    # positive: halfword swap loop
    loop = _hw(0x6055, 0x6008, 0x2605, 0x4710, 0x8BFA)
    res = scan_vals(loop, 0x1000)
    check("loop found (synthetic)", res["loop"] == [(0x1000, 0x1008)])
    check("exact mov.w/swap.b/mov.w loop found", res["loop16_exact"] == [(0x1000, 0x1008)])
    wrong = _hw(0x6055, 0x6138, 0x2605, 0x4710, 0x8BFA)  # swap.b r3,r1: not the loaded value
    check("swap of another register is not a data swap",
          scan_vals(wrong, 0x1000)["loop16_exact"] == [])
    # positive: byte-pair assembly
    pair = _hw(0x6000, 0x4018, 0x200B, 0x0009)
    check("shll8 + or pair found", scan_vals(pair, 0x2000)["pair"] == [0x2002])
    check("strict pair (mov.b load into shll8 reg, or) found",
          scan_vals(_hw(0x6000, 0x4018, 0x200B, 0x0009), 0x2000)["pair_strict"] == [0x2002])
    check("strict pair rejects shll8 of an unloaded reg",
          scan_vals(_hw(0x6000, 0x4118, 0x200B, 0x0009), 0x2000)["pair_strict"] == [])
    # positive: 32-bit swap
    s32 = _hw(0x6008, 0x6009, 0x6008)
    check("swap.b + swap.w swap32 found", scan_vals(s32, 0x3000)["swap32"] == [0x3000])
    # negative: a plain copy loop (no swap op) is not a loop hit
    copy = _hw(0x6055, 0x2605, 0x4710, 0x8BFB)
    check("plain copy loop is not a swap loop", scan_vals(copy, 0x4000)["loop"] == [])
    # negative: a forward branch is not a loop
    fwd = _hw(0x6008, 0x6055, 0x2605, 0x8B01, 0x6008)
    check("forward branch is not a loop", scan_vals(fwd, 0x5000)["loop"] == [])
    # negative: a loop whose body is longer than the span is not counted
    far = array("H", [0x6008] + [0x0009] * (SPAN + 4) + [0x6055, 0x2605, 0x8B00 | ((-(SPAN + 9)) & 0xFF)])
    check("loop longer than SPAN is not counted", scan_vals(far, 0x6000)["loop"] == [])
    # range restriction keeps only the sites inside it
    check("range restricts reported sites",
          scan_vals(loop, 0x1000, lo=0x1010)["loop"] == [])
    print("selftest:", "PASS" if not fails else "FAIL (%d)" % fails)
    return 0 if not fails else 1


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("scan", "control"):
        p = sub.add_parser(name)
        p.add_argument("image", help="IMG256 (first 256 MiB of the EU card)")
        p.add_argument("--image-start", type=lambda s: int(s, 0), required=True)
        p.add_argument("--module", default="Navi.exe")
        p.add_argument("--read-mib", type=int, default=sh4scan.DEFAULT_READ_MIB)
        if name == "scan":
            p.add_argument("--range", help="report sites in LO:HI (VA, hex ok)")
            p.add_argument("--list", action="store_true", help="print each loop/pair site")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd not in ("scan", "control"):
        build_parser().print_help()
        return 2
    try:
        size, digest, secs = _load(args)
    except (ValueError, KeyError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    print("image: %s  size %d  sha256(read) %s  image_start 0x%x  module %s"
          % (os.path.basename(args.image), size, digest, args.image_start, args.module))
    if args.cmd == "scan":
        return cmd_scan(args, secs)
    return cmd_control(args, secs)


if __name__ == "__main__":
    sys.exit(main())
