#!/usr/bin/env python3
"""Classify ``fn_match`` NOMATCH functions: rewrite or second matcher class (H89).

After M1.22b the EU→US ``Navi.exe`` census is ``NOMATCH 1259`` of 7596 (C-3626):
no hash hit, no unique masked-form twin, no call-order match.  This tool takes
a seeded random sample of those NOMATCH functions, pairs each with a US
counterpart **without using any matcher hash**, and classifies the pair by
its instruction stream.

Pairing (independent of the matcher's own verdict):

1. **Address-order anchor.**  ``.pdata`` records are sorted in both builds and
   the linker keeps object order, so the nearest matched EU neighbours
   (``UNIQUE``/``DIFFERENT``/``CALLORDER``) on each side bracket a US index
   range.  When the EU gap and the US gap hold the same number of records the
   counterpart is the record at the same offset (``anchor``); otherwise every
   US record in the gap is a candidate (``gap``, at most ``GAP_CAP`` nearest
   the expected index) and the most similar one is kept.
2. A candidate whose similarity is below ``MIN_RATIO`` is not a counterpart.
   Such a row (or one with no US gap at all) falls back to the most similar
   **unclaimed** US record of comparable length (``+global``; similarity
   only, weaker evidence); with none above ``MIN_RATIO`` it is ``UNPAIRED``.

Classes (first that applies, on the *body*: the function's halfwords with its
own literal-pool slots removed and trailing alignment padding dropped; branch
displacements and ``mov.x @(disp,PC)`` displacements are already masked by
``fn_match._instruction_tokens``):

* ``TWIN``       the masked form stream (``fn_match.code_digest``) is equal and
                 the US build has two or more such functions, so
                 ``_pool_only_twin`` refused it; identical code.
* ``PHANTOM-SLOT`` body equal; ``code_digest`` differs only because a pool
                 *data* halfword that decodes as ``mov.x @(disp,PC)`` made
                 ``fn_match`` blank a real instruction as a "pool slot" in one
                 build (``naive_slots`` vs the forward-pass ``pool_slots``).
* ``POOL-LAYOUT`` body equal, no phantom slot; the pool slot layout differs
                 (another pool size / order / padding).
* ``REGALLOC``   same length and per-position form; only register fields differ.
* ``IMMEDIATE``  same length and form; only immediate/displacement fields differ.
* ``OPERANDS``   same length and form; both register and immediate fields differ.
* ``REORDER``    same multiset of instructions in another order.
* ``EDIT``       insertions/deletions/replacements, similarity >= ``EDIT_RATIO``.
* ``REWRITE``    similarity in ``[MIN_RATIO, EDIT_RATIO)``.
* ``UNPAIRED``   no candidate reaches ``MIN_RATIO`` (or no US gap at all).

Every row prints the first differing body instruction in both builds.

Usage:
  nomatch_census.py EU_IMG US_IMG [--seed 89] [--size 40] [--all]
      [--no-global | --global-all] [--verbose]
      [--anchor-shift K | --anchor-shuffle SEED] [--module Navi.exe] [--image-start 0x200200]
      [--json OUT]
  nomatch_census.py EU_IMG US_IMG --pair EU_VA:US_VA
  nomatch_census.py --selftest

Stdlib only; reads the images, writes nothing to the repo.
"""
from __future__ import annotations

import argparse
import contextlib
import difflib
import hashlib
import io
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fn_match as fm  # noqa: E402
import sh4dis  # noqa: E402

MIN_RATIO = 0.5
EDIT_RATIO = 0.9
GAP_CAP = 64
MATCHED = ("UNIQUE", "DIFFERENT", "CALLORDER")
CLASSES = ("TWIN", "PHANTOM-SLOT", "POOL-LAYOUT", "REGALLOC", "IMMEDIATE", "OPERANDS",
           "REORDER", "EDIT", "REWRITE", "UNPAIRED")
# the classes in which no instruction differs (matcher weakness, not code)
SAME_CODE = ("TWIN", "PHANTOM-SLOT", "POOL-LAYOUT")


# ------------------------------------------------------------------ body

def naive_slots(words, va):
    """Pool slot indexes as ``fn_match`` derives them: every halfword that
    decodes as ``mov.x @(disp,PC)`` names a slot, **including halfwords that
    are themselves pool data** (a literal whose low half is ``0x9nnn`` or
    ``0xDnnn``)."""
    out = set()
    for i, w in enumerate(words):
        if fm.is_mov_pc(w):
            j = (fm.pool_addr(va + 2 * i, w) - va) // 2
            out.update((j, j + 1) if (w >> 12) == 0xD else (j,))
    return out


def pool_slots(words, va):
    """Pool slot indexes from a forward pass that skips pool data.

    A PC-relative load only reaches forward (``disp`` is unsigned), so a slot
    is always marked before the scan reaches it; a halfword already marked as
    a slot is data and never names another slot.
    """
    out = set()
    for i, w in enumerate(words):
        if i in out or not fm.is_mov_pc(w):
            continue
        j = (fm.pool_addr(va + 2 * i, w) - va) // 2
        out.update((j, j + 1) if (w >> 12) == 0xD else (j,))
    return out


def phantom(words, va):
    """True when ``fn_match``'s slot set differs from the forward-pass one."""
    n = len(words)
    return {k for k in naive_slots(words, va) if k < n} != \
        {k for k in pool_slots(words, va) if k < n}


def token(w, va, base_va, span):
    """``fn_match._instruction_tokens``' per-instruction form, without the
    pool zeroing (slots are removed from the body instead)."""
    if fm.is_branch(w):
        tgt = fm.branch_target(va, w)
        same = base_va <= tgt < base_va + span
        cls = (w >> 12) if (w >> 12) in (0xA, 0xB) else 0x80 | ((w >> 8) & 0xF)
        return ("b", cls, 1 if same else 0)
    if fm.is_mov_pc(w):
        return ("p", w >> 12, (w >> 8) & 0xF)
    return ("i", w)


def fixed_digest(words, va):
    """``code_digest`` with the forward-pass slots: slots blank, the rest is
    the per-instruction form.  Equal for two functions that differ only in
    pool values *and* phantom slots."""
    slots = pool_slots(words, va)
    span = 2 * len(words)
    h = hashlib.sha256()
    for i, w in enumerate(words):
        h.update(b"\x00\x00" if i in slots else
                 repr(token(w, va + 2 * i, va, span)).encode())
    return h.hexdigest()


def body(words, va, code_bytes=None, code_base=None):
    """[(index, token, word)] without pool slots and trailing padding."""
    slots = pool_slots(words, va)
    span = 2 * len(words)
    out = [(i, token(words[i], va + 2 * i, va, span), words[i])
           for i in range(len(words)) if i not in slots]
    # drop alignment padding after the last delay slot
    while len(out) > 2 and out[-1][2] in (0x0009, 0x0000) and \
            out[-2][2] != 0x000B:
        out.pop()
    return out


def reg_mask(w):
    """Bits of ``w`` that name registers (by the manual's operand table)."""
    form, rn, rm = sh4dis.operands(w)
    if form in ("fpu", "unknown"):
        return 0x0FF0
    return (0x0F00 if rn is not None else 0) | (0x00F0 if rm is not None else 0)


def form_of(tok, w):
    """Per-position form: the token for branches / PC loads, else the form."""
    if fm.is_branch(w) or fm.is_mov_pc(w):
        return tok
    return sh4dis.operands(w)[0]


def classify_bodies(ba, bb):
    """(class, first_index_a, first_index_b, ratio) for two bodies.

    ``first_index_*`` index the body lists (None when the bodies are equal).
    The TWIN class needs the matcher's twin count and is decided by the caller.
    """
    ta = [t for _, t, _ in ba]
    tb = [t for _, t, _ in bb]
    if ta == tb:
        return "POOL-LAYOUT", None, None, 1.0
    n = min(len(ta), len(tb))
    first = next((k for k in range(n) if ta[k] != tb[k]), n)
    ratio = difflib.SequenceMatcher(None, ta, tb, autojunk=False).ratio()
    if len(ta) == len(tb):
        same_form = all(form_of(ta[k], ba[k][2]) == form_of(tb[k], bb[k][2])
                        for k in range(n))
        if same_form:
            reg = imm = False
            for k in range(n):
                if ta[k] == tb[k]:
                    continue
                diff = ba[k][2] ^ bb[k][2]
                mask = reg_mask(ba[k][2])
                reg |= bool(diff & mask)
                imm |= bool(diff & ~mask & 0xFFFF)
            cls = "OPERANDS" if reg and imm else ("REGALLOC" if reg else "IMMEDIATE")
            return cls, first, first, ratio
    if sorted(ta) == sorted(tb):
        return "REORDER", first, first, ratio
    if ratio >= EDIT_RATIO:
        return "EDIT", first, first, ratio
    if ratio >= MIN_RATIO:
        return "REWRITE", first, first, ratio
    return "UNPAIRED", first, first, ratio


# ---------------------------------------------------------------- pairing

def anchor_candidates(i, amap, keys, n_b):
    """('anchor'|'gap'|'edge', [US indexes]) for EU index ``i``.

    ``amap`` maps matched EU pdata indexes to US pdata indexes, ``keys`` is
    ``sorted(amap)``.  Gap candidates are ordered by distance from the
    proportional expected index and capped at ``GAP_CAP``.
    """
    import bisect
    k = bisect.bisect_left(keys, i)
    p = keys[k - 1] if k > 0 else None
    q = keys[k] if k < len(keys) and keys[k] != i else (
        keys[k + 1] if k + 1 < len(keys) else None)
    if p is None or q is None:
        return "edge", []
    jp, jq = amap[p], amap[q]
    if jq - jp == q - p:
        return "anchor", [jp + (i - p)]
    lo, hi = jp + 1, jq
    if hi <= lo:
        return "gap", []
    exp = jp + (i - p) * (jq - jp) / float(q - p)
    cands = sorted(range(lo, hi), key=lambda j: abs(j - exp))[:GAP_CAP]
    _ = n_b
    return "gap", cands


# ------------------------------------------------------------------ run

def insn_text(word, va):
    return sh4dis.fmt(sh4dis.decode(word, va)).split("  ", 2)[-1].strip()


def census(m):
    """EU va -> (US va|None, verdict) through ``Matcher.verdict``."""
    out = {}
    with contextlib.redirect_stdout(io.StringIO()):
        for va, _w, _lr, _cb, _cc in m.fa:
            r = m.verdict(va)
            out[va] = (r[1], r[2])
    return out


def global_best(ba, free_bodies):
    """Most similar unclaimed US body (length within 0.7x..1.43x), or None.

    The fallback for a row the address-order anchor could not pair: it says
    whether the EU code moved elsewhere in the US link order or has no
    counterpart at all.  Similarity only, so weaker than an anchor pair.
    """
    ta = [t for _, t, _ in ba]
    best = None
    for j, bb in free_bodies:
        if not (0.7 * len(ta) <= len(bb) <= 1.43 * len(ta)):
            continue
        tb = [t for _, t, _ in bb]
        sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
        floor = best[0] if best else MIN_RATIO
        if sm.real_quick_ratio() < floor or sm.quick_ratio() < floor:
            continue
        r = sm.ratio()
        if r >= floor and (best is None or r > best[0]):
            best = (r, j, bb)
    return best


def classify_one(m, i, amap, keys, b_forms, b_fixed, free_bodies=None):
    va, words, _lr, cb, cbase = m.fa[i]
    fixed = b_fixed.get(fixed_digest(words, va), [])
    cdig = fm.code_digest(words, va, cb, cbase)
    twins = b_forms.get(cdig, [])
    how, cands = anchor_candidates(i, amap, keys, len(m.fb))
    ba = body(words, va, cb, cbase)
    best = None
    for j in cands:
        bva, bwords, _blr, bcb, bcbase = m.fb[j]
        bb = body(bwords, bva, bcb, bcbase)
        if fm.code_digest(bwords, bva, bcb, bcbase) == cdig:
            res = ("TWIN", None, None, 1.0)
        else:
            res = classify_bodies(ba, bb)
        if best is None or res[3] > best[2][3]:
            best = (j, bb, res)
        if res[3] == 1.0:
            break
    if free_bodies is not None and (best is None or best[2][0] == "UNPAIRED"):
        g = global_best(ba, free_bodies)
        if g is not None:
            how = how + "+global"
            gva, gw, _glr, gcb, gcbase = m.fb[g[1]]
            if fm.code_digest(gw, gva, gcb, gcbase) == cdig:
                gres = ("TWIN", None, None, 1.0)
            else:
                gres = classify_bodies(ba, g[2])
            best = (g[1], g[2], gres)
    row = {"eu": va, "eu_bytes": 2 * len(words), "pairing": how,
           "eu_phantom": phantom(words, va), "us_phantom": None,
           "candidates": len(cands), "us_twins": len(twins),
           "us_fixed_twins": len(fixed),
           "us_fixed": fixed[0] if len(fixed) == 1 else None, "us": None,
           "us_bytes": None, "class": "UNPAIRED", "ratio": None,
           "first_diff": None}
    if best is None:
        return row
    j, bb, (cls, fa_i, fb_i, ratio) = best
    bva, bwords = m.fb[j][0], m.fb[j][1]
    row.update(us=bva, us_bytes=2 * len(bwords), ratio=round(ratio, 3),
               us_phantom=phantom(bwords, bva))
    if cls == "POOL-LAYOUT" and (row["eu_phantom"] or row["us_phantom"]):
        cls = "PHANTOM-SLOT"
    if cls == "UNPAIRED":
        row["us"] = None
    row["class"] = cls
    if fa_i is not None:
        ea = ba[fa_i] if fa_i < len(ba) else None
        eb = bb[fb_i] if fb_i < len(bb) else None
        row["first_diff"] = {
            "offset_eu": 2 * ea[0] if ea else None,
            "offset_us": 2 * eb[0] if eb else None,
            "eu": "%04x %s" % (ea[2], insn_text(ea[2], va + 2 * ea[0])) if ea else "-",
            "us": "%04x %s" % (eb[2], insn_text(eb[2], bva + 2 * eb[0])) if eb else "-",
        }
    return row


def controls(m, verdicts, amap, keys, seed, size):
    """Anchor control: a UNIQUE function, its own anchor removed, must be
    paired with the matcher's US function.  Classifier control: the same EU
    body against the next US record must not be classed as same code.  (The
    whole-pipeline negative control is ``--anchor-shift``/``--anchor-shuffle``.)"""
    uniq = [i for i in keys if verdicts[m.fa[i][0]][1] == "UNIQUE"]
    pick = sorted(random.Random(seed).sample(uniq, min(size, len(uniq))))
    pos_pair = 0
    neg = Counter()
    for i in pick:
        k2 = [k for k in keys if k != i]
        how, cands = anchor_candidates(i, amap, k2, len(m.fb))
        va, words = m.fa[i][0], m.fa[i][1]
        ba = body(words, va)
        j = amap[i]
        if how == "anchor" and cands == [j]:
            pos_pair += 1
        if j + 1 < len(m.fb):
            nva, nw = m.fb[j + 1][0], m.fb[j + 1][1]
            neg[classify_bodies(ba, body(nw, nva))[0]] += 1
    print("# anchor control: %d UNIQUE (seed %d), own anchor removed: the "
          "anchor names the matcher's US function in %d" % (len(pick), seed, pos_pair))
    print("# classifier control: same EU body vs the next US record: " +
          "  ".join("%s %d" % (c, neg[c]) for c in CLASSES if neg[c]))


def fmt_row(r):
    fd = r["first_diff"]
    tail = ""
    if fd:
        tail = " @+%s EU[%s] US[%s]" % (
            "%#x" % fd["offset_eu"] if fd["offset_eu"] is not None else "-",
            fd["eu"], fd["us"])
    return "%#010x %5dB %-13s cand=%-3d twins=%d/%d%s -> %s %-11s r=%s%s" % (
        r["eu"], r["eu_bytes"], r["pairing"], r["candidates"], r["us_twins"],
        r["us_fixed_twins"], " ph" if r["eu_phantom"] or r["us_phantom"] else "   ",
        ("%#010x %5dB" % (r["us"], r["us_bytes"])) if r["us"] else "-" + " " * 17,
        r["class"], "%.3f" % r["ratio"] if r["ratio"] is not None else "-", tail)


def phantom_sources(words, va):
    """[(data_index, word, blanked_index)]: pool data that names a phantom slot."""
    fwd = pool_slots(words, va)
    out = []
    for i, w in enumerate(words):
        if i in fwd and fm.is_mov_pc(w):
            j = (fm.pool_addr(va + 2 * i, w) - va) // 2
            if j < len(words) and j not in fwd:
                out.append((i, w, j))
    return out


def cmd_pair(m, eu_va, us_va) -> int:
    """Raw halfword compare of one EU/US pair, with slot and phantom notes."""
    fa = m._fa_by_va.get(eu_va)
    fb = m._fb_by_va.get(us_va)
    if fa is None or fb is None:
        print("# pair: %#x or %#x is not a pdata start" % (eu_va, us_va))
        return 2
    a, b = fa[0], fb[0]
    ba, bb = body(a, eu_va), body(b, us_va)
    cls = classify_bodies(ba, bb)
    sa, sb = pool_slots(a, eu_va), pool_slots(b, us_va)
    diffs = [k for k in range(min(len(a), len(b))) if a[k] != b[k]]
    in_slots = sum(1 for k in diffs if k in sa and k in sb)
    print("# pair EU %#010x (%d B) / US %#010x (%d B): body class %s ratio %.3f"
          % (eu_va, 2 * len(a), us_va, 2 * len(b), cls[0], cls[3]))
    print("# raw halfword diffs over the common length: %d, in a pool slot of "
          "both builds: %d, length difference %d B" % (
              len(diffs), in_slots, 2 * (len(b) - len(a))))
    for k in diffs:
        if not (k in sa and k in sb):
            print("  +%#06x EU %04x %-28s US %04x %s" % (
                2 * k, a[k], insn_text(a[k], eu_va + 2 * k),
                b[k], insn_text(b[k], us_va + 2 * k)))
    for name, w, va in (("EU", a, eu_va), ("US", b, us_va)):
        for i, x, j in phantom_sources(w, va):
            print("# %s phantom: pool data +%#x = %04x decodes as %s and "
                  "blanks +%#x (%04x %s)" % (
                      name, 2 * i, x, insn_text(x, va + 2 * i), 2 * j, w[j],
                      insn_text(w[j], va + 2 * j)))
    return 0


def run(args) -> int:
    with contextlib.redirect_stdout(io.StringIO()):
        m = fm.Matcher(args.eu, args.us, args.module, args.image_start,
                       2, 2, None, None)
    if args.pair:
        eu_va, _, us_va = args.pair.partition(":")
        return cmd_pair(m, int(eu_va, 0), int(us_va, 0))
    verdicts = census(m)
    counts = Counter(v for _b, v in verdicts.values())
    print("# census: " + "  ".join("%s %d" % (k, counts[k]) for k in
          ("UNIQUE", "DIFFERENT", "CALLORDER", "AMBIGUOUS", "NOMATCH")) +
          "  total %d" % sum(counts.values()))
    b_index = {f[0]: j for j, f in enumerate(m.fb)}
    amap = {}
    for i, f in enumerate(m.fa):
        bva, v = verdicts[f[0]]
        if v in MATCHED and bva in b_index:
            amap[i] = b_index[bva]
    keys = sorted(amap)
    inv = sum(1 for a, b in zip(keys, keys[1:]) if amap[b] < amap[a])
    if args.anchor_shift:
        # pipeline negative control: every anchor points k US records off
        amap = {i: min(max(j + args.anchor_shift, 0), len(m.fb) - 1)
                for i, j in amap.items()}
        print("# CONTROL: anchors shifted by %+d US records" % args.anchor_shift)
    if args.anchor_shuffle is not None:
        vals = [amap[i] for i in keys]
        random.Random(args.anchor_shuffle).shuffle(vals)
        amap = dict(zip(keys, vals))
        print("# CONTROL: anchors shuffled (seed %d)" % args.anchor_shuffle)
    print("# anchors: %d matched EU records, %d order inversions" % (len(keys), inv))
    nomatch = [i for i, f in enumerate(m.fa) if verdicts[f[0]][1] == "NOMATCH"]
    b_forms = {}
    for va, w, _lr, cb, cc in m.fb:
        b_forms.setdefault(fm.code_digest(w, va, cb, cc), []).append(va)
    b_fixed = {}
    for va, w, _lr, _cb, _cc in m.fb:
        b_fixed.setdefault(fixed_digest(w, va), []).append(va)
    if args.all:
        sample = nomatch
        print("# population: all %d NOMATCH" % len(nomatch))
    else:
        sample = sorted(random.Random(args.seed).sample(nomatch, args.size))
        print("# sample: seed %d size %d of %d NOMATCH" % (
            args.seed, args.size, len(nomatch)))
    claimed = set() if args.global_all else set(amap.values())
    free_bodies = None
    if not args.no_global:
        free_bodies = [(j, body(f[1], f[0])) for j, f in enumerate(m.fb)
                       if j not in claimed]
        print("# global fallback over %d %sUS records" % (
            len(free_bodies), "" if args.global_all else "unclaimed "))
    rows = [classify_one(m, i, amap, keys, b_forms, b_fixed, free_bodies)
            for i in sample]
    if not args.all or args.verbose:
        for r in rows:
            print(fmt_row(r))
    dist = Counter(r["class"] for r in rows)
    print("# classes: " + "  ".join("%s %d" % (c, dist[c]) for c in CLASSES))
    for how in sorted({r["pairing"] for r in rows}):
        sub = Counter(r["class"] for r in rows if r["pairing"] == how)
        print("#   %-13s %4d: " % (how, sum(sub.values())) +
              "  ".join("%s %d" % (c, sub[c]) for c in CLASSES if sub[c]))
    named = Counter(r["us"] for r in rows if r["us"] is not None)
    multi = sorted(v for v, n in named.items() if n > 1)
    print("# US records named by more than one row: %d (rows %d)" % (
        len(multi), sum(named[v] for v in multi)))
    same = sum(dist[c] for c in SAME_CODE)
    print("# same code (TWIN+PHANTOM-SLOT+POOL-LAYOUT): %d  operand-only (REGALLOC+IMMEDIATE+"
          "OPERANDS): %d  instruction changes (REORDER+EDIT+REWRITE): %d  "
          "unpaired: %d  of %d" % (
              same, dist["REGALLOC"] + dist["IMMEDIATE"] + dist["OPERANDS"],
              dist["REORDER"] + dist["EDIT"] + dist["REWRITE"],
              dist["UNPAIRED"], len(rows)))
    if not args.all and not args.anchor_shift and args.anchor_shuffle is None:
        controls(m, verdicts, amap, keys, args.seed, args.size)
    fix1 = [r for r in rows if r["us_fixed_twins"] == 1]
    agree = sum(1 for r in fix1 if r["us"] == r["us_fixed"])
    print("# forward-pass digest unique in US: %d of %d (the anchor pairs the "
          "same US function in %d)" % (len(fix1), len(rows), agree))
    if args.json:
        Path(args.json).write_text(json.dumps(
            {"seed": None if args.all else args.seed, "size": len(rows),
             "census": dict(counts), "rows": rows}, indent=1))
    return 0


# --------------------------------------------------------------- selftest

def selftest() -> int:
    failed = 0
    checks = 0

    def check(name, cond):
        nonlocal failed, checks
        checks += 1
        if not cond:
            failed += 1
            print("FAIL", name)

    base = 0x1000
    blob = bytearray(0x400)

    def mk(words, va=base):
        return body(words, va, bytes(blob), base)

    # prologue / body / rts / pool
    f = [0x2F86, 0x4F22, 0xD303, 0x6493, 0x430B, 0x0009, 0x4F26, 0x000B,
         0x68F6, 0x0009, 0x1234, 0x5678]
    bf = mk(f)
    check("pool slots removed", all(w not in (0x1234, 0x5678) for _, _, w in bf))
    # same code, pool values differ -> POOL-LAYOUT when bodies equal
    g = list(f)
    g[10], g[11] = 0xAAAA, 0xBBBB
    check("pool value only is POOL-LAYOUT", classify_bodies(bf, mk(g))[0] == "POOL-LAYOUT")
    # trailing padding dropped
    check("padding dropped", classify_bodies(bf, mk(f[:10] + [0x1234, 0x5678, 0x0009]))[0]
          in ("POOL-LAYOUT",))
    # register allocation: mov r9,r4 -> mov r10,r4
    h = list(f)
    h[3] = 0x64A3
    check("regalloc", classify_bodies(bf, mk(h))[0] == "REGALLOC")
    # immediate: add #-16,r15 vs add #-8,r15 (same form)
    i1 = [0x7FF0] + f
    i2 = [0x7FF8] + f
    check("immediate", classify_bodies(mk(i1), mk(i2))[0] == "IMMEDIATE")
    # operands: both reg and imm differ
    o2 = [0x7EF8] + f
    check("operands", classify_bodies(mk(i1), mk(o2))[0] == "OPERANDS")
    # reorder: swap two independent instructions
    r1 = [0xE101, 0x7202] + f
    r2 = [0x7202, 0xE101] + f
    c = classify_bodies(mk(r1), mk(r2))
    check("reorder", c[0] == "REORDER" and c[1] == 0)
    # edit: one inserted instruction in a long body
    long = [0x6013 + (k % 7) * 0x100 for k in range(40)] + [0x000B, 0x0009]
    ins = long[:20] + [0x7001] + long[20:]
    c = classify_bodies(mk(long), mk(ins))
    check("edit", c[0] == "EDIT" and c[1] == 20)
    # rewrite: half the body differs
    half = long[:20] + [0x3C0C] * 20 + [0x000B, 0x0009]
    check("rewrite", classify_bodies(mk(long), mk(half))[0] == "REWRITE")
    # unrelated
    other = [0x2008 + k * 0x10 for k in range(40)] + [0x000B, 0x0009]
    check("unpaired", classify_bodies(mk(long), mk(other))[0] == "UNPAIRED")
    # reg mask of a two-register form and of mov #imm
    check("reg_mask mov r,r", reg_mask(0x6493) == 0x0FF0)
    check("reg_mask mov #imm", reg_mask(0xE401) == 0x0F00)
    # phantom slot: a pool literal whose low half is 0xD3xx names a slot
    # in fn_match's naive pass; the forward pass treats it as data
    ph = [0xD301, 0x000B, 0x0009, 0x0009, 0xD300, 0x0000, 0x6013, 0x6013]
    check("naive pass marks a phantom slot", 6 in naive_slots(ph, base))
    check("forward pass skips pool data", 6 not in pool_slots(ph, base)
          and 4 in pool_slots(ph, base) and phantom(ph, base))
    check("no phantom in plain code", not phantom(f, base))
    check("phantom source named", phantom_sources(ph, base) == [(4, 0xD300, 6)])
    # anchors
    amap = {0: 0, 4: 4, 6: 9}
    keys = sorted(amap)
    check("anchor exact", anchor_candidates(2, amap, keys, 10) == ("anchor", [2]))
    how, c = anchor_candidates(5, amap, keys, 10)
    check("gap range", how == "gap" and sorted(c) == [5, 6, 7, 8] and c[0] in (6, 7))
    check("edge", anchor_candidates(7, amap, keys, 10) == ("edge", []))
    check("empty gap", anchor_candidates(1, {0: 0, 2: 1}, [0, 2], 3) == ("gap", []))
    print("nomatch_census selftest: %s (%d checks, %d failed)" % (
        "OK" if not failed else "FAIL", checks, failed))
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("eu", nargs="?")
    ap.add_argument("us", nargs="?")
    ap.add_argument("--module", default="Navi.exe")
    ap.add_argument("--image-start", type=lambda s: int(s, 0), default=0x200200)
    ap.add_argument("--seed", type=int, default=89)
    ap.add_argument("--size", type=int, default=40)
    ap.add_argument("--all", action="store_true",
                    help="classify every NOMATCH (prints the distribution only)")
    ap.add_argument("--verbose", action="store_true",
                    help="with --all, print every row too")
    ap.add_argument("--no-global", action="store_true",
                    help="skip the similarity search over unclaimed US records")
    ap.add_argument("--global-all", action="store_true",
                    help="fallback searches every US record, claimed ones too")
    ap.add_argument("--pair", metavar="EU:US",
                    help="raw compare of one EU/US pdata pair and exit")
    ap.add_argument("--anchor-shift", type=int, default=0, metavar="K",
                    help="negative control: move every anchor K US records")
    ap.add_argument("--anchor-shuffle", type=int, default=None, metavar="SEED",
                    help="negative control: shuffle the anchors' US indexes")
    ap.add_argument("--json")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.eu or not args.us:
        ap.error("EU_IMG and US_IMG are required")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
