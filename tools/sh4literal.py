#!/usr/bin/env python3
"""SH-4 literal-pool scan: referenced vs unreferenced 32-bit words (M1.24).

"Literal X appears in no pool" was an ad-hoc survey pasted into EXPs (M3.13
pass 3, M3.11c, M3.15). This tool makes it one command.

Model.  Every even halfword of every executable section is decoded as a
possible PC-relative load:

  mov.l @(disp,PC),Rn  0xDndd  pool word  ((pc+4) & ~3) + disp*4   (32-bit)
  mov.w @(disp,PC),Rn  0x9ndd  pool half  pc + 4 + disp*2           (16-bit)
  mova  @(disp,PC),R0  0xC7dd  address    ((pc+4) & ~3) + disp*4   (no read)

A linear sweep also decodes pool data as instructions, so references are
filtered in two steps: (1) a target is *structural* when the words before it
(other pool words, a 0x0009/0x0000 pad) end in the delay slot of an
unconditional transfer (rts, rte, bra, braf, jmp) — compiled code puts pools
only there; (2) a reference whose source halfword lies inside a structural
pool word is data, not code, and is dropped (iterated to a fixed point).

Queries (all print the corpus they covered):

  find WORD [WORD ...]   per word: aligned occurrences in executable sections,
                         each referenced (mov.l sources) or unreferenced; mova
                         targets equal to WORD; 16-bit mov.w pool halves equal
                         to WORD when WORD < 0x10000; occurrences in data and
                         decoded INIT sections, with pool words pointing at them
  bytes HEX              byte pattern (a string such as ``3a3b3a``): every
                         occurrence, and pool words / mova targets equal to the
                         occurrence or to its NUL-delimited string start
  --range LO HI          referenced pool words whose value is in [LO, HI]
  --unreferenced         words inside pool blocks that no instruction reads
  --parent-of VA         enclosing function start from the pool walker's own
                         operand data (pool blocks and rts boundaries), with
                         the ``.pdata`` start beside it (AGREE / DIFFER)
  --parent-audit         run --parent-of on one mid-point per .pdata function

Compressed sections are decoded with ``tools/nk_decomp.py`` (the kernel's own
routine, cached). One that does not decode prints ``NOT SEARCHED (section N)``
and is never folded into "absent". Not a disassembler: decoding is
``tools/sh4dis.py``.

Usage:
  sh4literal.py IMG MODULE [--image-start X] find WORD [WORD ...] [--window LO HI] [--json]
  sh4literal.py IMG MODULE [--image-start X] bytes HEX [--json]
  sh4literal.py IMG MODULE [--image-start X] --range LO HI [--json]
  sh4literal.py IMG MODULE [--image-start X] --unreferenced [--json]
  sh4literal.py IMG MODULE [--image-start X] --parent-of VA [VA ...]
  sh4literal.py IMG MODULE [--image-start X] --parent-audit
  sh4literal.py --selftest

Exit codes: 0 ok, 1 self-test failure, 2 usage error or no image.
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import struct
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sh4dis  # noqa: E402
from sh4dis import halfwords_le  # noqa: E402
from sh4xref import is_prologue_word  # noqa: E402

PAD_HALVES = (0x0009, 0x0000)   # nop / zero pad before a pool
TAIL_WORDS = 16                 # unread words counted after a block's last read word
DEFAULT_IMAGE_START = 0x200200


def is_transfer(w):
    """Unconditional transfer that may be followed by a delay slot and a pool."""
    if w is None:
        return False
    return (w in (0x000B, 0x002B)            # rts, rte
            or w & 0xF000 == 0xA000          # bra
            or w & 0xF0FF == 0x0023          # braf
            or w & 0xF0FF == 0x402B)         # jmp @Rn


def is_push(w):
    """``mov.l Rm,@-r15`` or ``sts.l pr,@-r15``: the opening of a prologue."""
    return w is not None and (w & 0xFF0F == 0x2F06 or w == 0x4F22)


def is_return(w):
    return w in (0x000B, 0x002B)


# --------------------------------------------------------------------------
# Segments
# --------------------------------------------------------------------------

class Seg:
    """One section: base VA, bytes, executable flag, origin label."""

    def __init__(self, base, blob, exe, label):
        self.base, self.blob, self.exe, self.label = base, bytes(blob), exe, label
        self.end = base + len(self.blob)
        self.halves = halfwords_le(self.blob) if exe else None

    def u16(self, va):
        o = va - self.base
        if 0 <= o and o + 2 <= len(self.blob):
            return self.halves[o >> 1] if self.halves is not None and not o & 1 \
                else sh4dis.read_u16(self.blob, o)
        return None

    def u32(self, va):
        o = va - self.base
        if 0 <= o and o + 4 <= len(self.blob):
            return sh4dis.read_u32(self.blob, o)
        return None


class Pools:
    """Reference map over the executable segments."""

    def __init__(self, segs):
        self.segs = sorted(segs, key=lambda s: s.base)
        self.exe = [s for s in self.segs if s.exe]
        self.ref32 = defaultdict(list)   # pool VA -> [source VA]
        self.ref16 = defaultdict(list)
        self.mova = defaultdict(list)
        self._raw()
        self.structural = set()
        self._filter()

    # -- lookup
    def seg_of(self, va):
        for s in self.segs:
            if s.base <= va < s.end:
                return s
        return None

    def u16(self, va):
        s = self.seg_of(va)
        return s.u16(va) if s else None

    def u32(self, va):
        s = self.seg_of(va)
        return s.u32(va) if s else None

    # -- build
    def _raw(self):
        for s in self.exe:
            h, base, end = s.halves, s.base, s.end
            for i in range(len(h)):
                w = h[i]
                top = w & 0xF000
                if top == 0xD000:
                    a = base + 2 * i
                    t = ((a + 4) & ~3) + (w & 0xFF) * 4
                    if t + 4 <= end:
                        self.ref32[t].append(a)
                elif top == 0x9000:
                    a = base + 2 * i
                    t = a + 4 + (w & 0xFF) * 2
                    if t + 2 <= end:
                        self.ref16[t].append(a)
                elif w & 0xFF00 == 0xC700:
                    a = base + 2 * i
                    t = ((a + 4) & ~3) + (w & 0xFF) * 4
                    self.mova[t].append(a)

    def _pool_bytes(self, targets32, targets16):
        b = set()
        for t in targets32:
            b.update((t, t + 2))
        for t in targets16:
            b.add(t)
        return b                              # halfword addresses

    def block_start(self, t, halves_in_pool):
        """Walk back from pool VA ``t`` over pool halves and pads."""
        a = t
        while True:
            p = a - 2
            if p in halves_in_pool:
                a = p
                continue
            w = self.u16(p)
            if w in PAD_HALVES and ((p - 2) in halves_in_pool or
                                    not is_transfer(self.u16(p - 2))):
                a = p
                continue
            return a

    def _is_structural(self, t, halves):
        a = self.block_start(t, halves)
        return is_transfer(self.u16(a - 4))

    def _filter(self):
        for _ in range(6):
            halves = self._pool_bytes(self.ref32, self.ref16)
            st32 = {t for t in self.ref32 if self._is_structural(t, halves)}
            st16 = {t for t in self.ref16 if self._is_structural(t, halves)}
            pool = self._pool_bytes(st32, st16)
            changed = False
            for table in (self.ref32, self.ref16, self.mova):
                for t in list(table):
                    keep = [a for a in table[t] if a not in pool]
                    if len(keep) != len(table[t]):
                        changed = True
                        if keep:
                            table[t] = keep
                        else:
                            del table[t]
            self.structural = st32 | {("w", t) for t in st16}
            if not changed:
                break
        self.pool_halves = self._pool_bytes(
            [t for t in self.ref32 if t in self.structural],
            [t for t in self.ref16 if ("w", t) in self.structural])

    def entries(self):
        """Entries from the walker's operand data: bsr targets, the values of
        referenced pool words that point into executable bytes (a ``jsr``
        target or a function pointer passed on), and aligned words of the
        data sections that point into executable bytes (init/vtables)."""
        if getattr(self, "_entries", None) is None:
            e = set()
            for s in self.exe:
                h, base = s.halves, s.base
                for i in range(len(h)):
                    w = h[i]
                    if w & 0xF000 == 0xB000:
                        d = w & 0xFFF
                        e.add(base + 2 * i + 4 + (d - 0x1000 if d & 0x800 else d) * 2)
            def code(v):
                return v is not None and not v & 1 and \
                    any(x.base <= v < x.end for x in self.exe)
            for t in self.ref32:
                v = self.u32(t)
                if code(v):
                    e.add(v)
            for s in self.segs:
                if s.exe:
                    continue
                for o in range(0, len(s.blob) - 3, 4):
                    v = sh4dis.read_u32(s.blob, o)
                    if code(v):
                        e.add(v)
            self._entries = e
        return self._entries

    # -- queries
    def refs_of(self, t):
        return self.ref32.get(t, [])

    def is_pool(self, t):
        return t in self.structural

    def aligned_hits(self, value, exe_only=True):
        needle = struct.pack("<I", value & 0xFFFFFFFF)
        out = []
        for s in self.segs:
            if exe_only and not s.exe:
                continue
            i = s.blob.find(needle)
            while i >= 0:
                if (s.base + i) % 4 == 0:
                    out.append((s, s.base + i))
                i = s.blob.find(needle, i + 1)
        return out

    def byte_hits(self, pat, segs):
        out = []
        for s in segs:
            i = s.blob.find(pat)
            while i >= 0:
                out.append((s, s.base + i))
                i = s.blob.find(pat, i + 1)
        return out

    def pool_words_equal(self, value):
        """Referenced pool words (anywhere) whose value equals ``value``."""
        return [t for t in self.ref32 if self.u32(t) == value]


# --------------------------------------------------------------------------
# Query implementations
# --------------------------------------------------------------------------

def _hx(v):
    return "0x%08x" % v


def query_word(pools, value, extra, fn_of=None, window=None):
    """Result dict for one 32-bit value."""
    rows = []
    for s, va in pools.aligned_hits(value):
        refs = pools.refs_of(va)
        if window and not any(window[0] <= a < window[1] for a in refs) and \
                not window[0] <= va < window[1]:
            continue
        rows.append({
            "va": _hx(va), "section": s.label,
            "status": "referenced" if refs else "unreferenced",
            "pool": pools.is_pool(va),
            "refs": [{"va": _hx(a), "fn": _hx(fn_of(a)) if fn_of and fn_of(a) else None}
                     for a in refs],
        })
    mova = [_hx(a) for a in pools.mova.get(value, [])]
    w16 = []
    if value < 0x10000:
        for t, srcs in pools.ref16.items():
            if pools.u16(t) == value:
                if window and not window[0] <= t < window[1] and \
                        not any(window[0] <= a < window[1] for a in srcs):
                    continue
                w16.append({"va": _hx(t), "refs": [_hx(a) for a in srcs]})
    data = []
    for s, va in pools.aligned_hits(value, exe_only=False):
        if s.exe:
            continue
        data.append({"va": _hx(va), "section": s.label,
                     "pointed_by": [_hx(t) for t in pools.pool_words_equal(va)]})
    ref_rows = [r for r in rows if r["status"] == "referenced"]
    return {
        "word": _hx(value),
        "exec_aligned": len(rows),
        "referenced_pool_words": len(ref_rows),
        "references": sum(len(r["refs"]) for r in ref_rows),
        "unreferenced": len(rows) - len(ref_rows),
        "mova_targets": mova,
        "movw16": w16,
        "data_aligned": data,
        "not_searched": extra["not_searched"],
        "rows": sorted(rows, key=lambda r: r["va"]),
        "movw16_rows": sorted(w16, key=lambda r: r["va"]),
    }


def string_start(seg, va, limit=256):
    o = va - seg.base
    lo = max(0, o - limit)
    k = seg.blob.rfind(b"\0", lo, o)
    return seg.base + (k + 1 if k >= 0 else lo)


def query_bytes(pools, pat, extra):
    hits = []
    for s, va in pools.byte_hits(pat, pools.segs):
        start = string_start(s, va)
        targets = sorted({va, start})
        ptr = []
        for t in targets:
            ptr += [{"pool": _hx(p), "value": _hx(t), "refs": [_hx(a) for a in pools.refs_of(p)]}
                    for p in pools.pool_words_equal(t)]
        mova = [{"src": _hx(a), "value": _hx(t)} for t in targets for a in pools.mova.get(t, [])]
        dptr = [{"at": _hx(d), "section": ds.label, "value": _hx(t)}
                for t in targets for ds, d in pools.aligned_hits(t, exe_only=False)
                if not ds.exe]
        hits.append({"va": _hx(va), "section": s.label, "string_start": _hx(start),
                     "pool_pointers": ptr, "mova": mova, "data_pointers": dptr})
    return {"bytes": pat.hex(), "occurrences": len(hits),
            "referenced": sum(1 for h in hits if h["pool_pointers"] or h["mova"]),
            "data_pointed": sum(1 for h in hits if h["data_pointers"]),
            "hits": hits, "not_searched": extra["not_searched"]}


def query_range(pools, lo, hi):
    rows = []
    for t in sorted(pools.ref32):
        v = pools.u32(t)
        if v is not None and lo <= v <= hi:
            rows.append({"pool": _hx(t), "value": _hx(v), "struct": pools.is_pool(t),
                         "refs": [_hx(a) for a in pools.ref32[t]]})
    return rows


def pool_blocks(pools):
    """Blocks of structural pool words: (start, end, referenced words)."""
    st = sorted(t for t in pools.ref32 if t in pools.structural)
    blocks = []
    for t in st:
        if blocks and t - blocks[-1][1] <= 64 and not _code_between(pools, blocks[-1][1], t):
            blocks[-1][1] = t + 4
            blocks[-1][2].append(t)
        else:
            blocks.append([t, t + 4, [t]])
    srcs = _sources(pools)
    for b in blocks:
        b[0] = pools.block_start(b[0], pools.pool_halves)
        # tail: unread words after the last read one, up to the next code
        end = b[1]
        for _ in range(TAIL_WORDS):
            h0, h1 = pools.u16(end), pools.u16(end + 2)
            if h0 is None or h1 is None or end in pools.structural:
                break
            if any(is_prologue_word(x) or is_transfer(x) for x in (h0, h1)) or \
                    end in srcs or (end + 2) in srcs:
                break
            end += 4
        b[1] = end
    return blocks


def _code_between(pools, a, b):
    """True when a reference source or a transfer lies in [a, b)."""
    for x in range(a, b, 2):
        w = pools.u16(x)
        if w is None or is_transfer(w) or is_prologue_word(w):
            return True
        if w & 0xF000 in (0xD000, 0x9000) and x not in pools.pool_halves and \
                (((x + 4) & ~3) + (w & 0xFF) * 4) in pools.ref32 and \
                x in _sources(pools):
            return True
    return False


_SRC_CACHE = {}


def _sources(pools):
    key = id(pools)
    if key not in _SRC_CACHE:
        s = set()
        for table in (pools.ref32, pools.ref16, pools.mova):
            for v in table.values():
                s.update(v)
        _SRC_CACHE[key] = s
    return _SRC_CACHE[key]


def unreferenced(pools):
    """Aligned words inside pool blocks that no instruction reads."""
    out = []
    srcs = _sources(pools)
    for start, end, refd in pool_blocks(pools):
        a = (start + 3) & ~3
        refset = set(refd)
        for w in range(a, end, 4):
            if w in refset or w in pools.ref32 or w in pools.mova:
                continue
            if w in pools.pool_halves or (w + 2) in pools.pool_halves:
                continue   # holds a mov.w half
            if w in srcs or (w + 2) in srcs:
                continue
            out.append(w)
    return out


# --------------------------------------------------------------------------
# --parent-of: function start from the pool walker
# --------------------------------------------------------------------------

def parent_of(pools, va, max_back=0x8000):
    """(start, how) from pool blocks and return boundaries; None if not found."""
    seg = pools.seg_of(va)
    if seg is None or not seg.exe:
        return None, "not in an executable section"
    ph = pools.pool_halves
    a = va & ~1
    lo = max(seg.base, va - max_back)
    while a > lo:
        p = a - 2
        boundary = None
        if p in ph:
            b = pools.block_start(p, ph)
            t = pools.u16(b - 4)
            boundary = ("pool %s-%s after %s@%s" % (_hx(b), _hx(a - 1),
                        "rts" if is_return(t) else "branch", _hx(b - 4)), b, is_return(t))
        elif is_return(pools.u16(p - 2)) and (p - 2) not in ph:
            boundary = ("rts@%s" % _hx(p - 2), p - 2, True)
        elif pools.u16(p) in PAD_HALVES and is_push(pools.u16(a)):
            return a, "push run after pad@%s" % _hx(p)
        if boundary:
            how, back, ret = boundary
            cand = a
            while cand < va and (pools.u16(cand) in PAD_HALVES or cand in ph):
                cand += 2
            if cand in ph or (cand == va and pools.u16(cand) in PAD_HALVES):
                a = back            # VA is pad/pool after the boundary: tail
                continue
            if is_prologue_word(pools.u16(cand)):
                return cand, how
            if cand in pools.entries():
                return cand, how + " (leaf: called entry)"
            if ret:
                # unread pool words / tables may follow the read ones: the
                # function opens at the first push run before VA, if any
                x = cand
                while x <= va:
                    if x not in ph and is_prologue_word(pools.u16(x)) and \
                            not is_prologue_word(pools.u16(x - 2)):
                        return x, how + " (+ unread words to the first push)"
                    x += 2
            a = back
            continue
        a -= 2
    if a <= seg.base:
        return seg.base, "section start"
    return None, "no boundary within %#x bytes" % max_back


# --------------------------------------------------------------------------
# Image binding
# --------------------------------------------------------------------------

def load_image_segs(img_path, image_start, module, decode=True):
    """(segs, extra) for MODULE. Compressed sections go through nk_decomp."""
    import cerom
    with open(img_path, "rb") as fh:
        data = fh.read(sh4dis.IMAGE_READ_BYTES)
    rom = cerom.CERom(data, image_start)
    m = rom.module(module)
    segs, cover, not_searched = [], [], []
    for i, s in enumerate(rom.o32(m)):
        exe = bool(s["flags"] & 0x20000000)
        comp = bool(s["flags"] & cerom.IMAGE_SCN_COMPRESSED)
        label = "sec%d" % i
        if comp:
            if not decode:
                not_searched.append(i)
                cover.append("%s %s compressed NOT SEARCHED (--no-decode)" % (label, _hx(s["realaddr"])))
                continue
            try:
                import nk_decomp
                blob = nk_decomp.section_init(data, m["name"], i, image_start)
            except Exception as exc:  # noqa: BLE001 - reported, never folded into absent
                not_searched.append(i)
                cover.append("%s %s NOT SEARCHED (section %d): %s" % (label, _hx(s["realaddr"]), i, exc))
                continue
            label += "(decoded)"
        else:
            off = rom.va2file(s["dataptr"])
            blob = data[off:off + min(s["psize"], s["vsize"])]
        segs.append(Seg(s["realaddr"], blob, exe, label))
        cover.append("%s %s %s %d B%s" % (label, _hx(s["realaddr"]),
                                          "exec" if exe else "data", len(blob),
                                          " (INIT bytes; BSS not stored)" if comp else ""))
    fn_of = None
    records = None
    try:
        import pdata
        records = pdata.load_table(data, rom.start, m["name"])[0]
        fn_of = pdata.fn_of_factory(records)
    except Exception:  # noqa: BLE001
        pass
    return segs, {"cover": cover, "not_searched": not_searched,
                  "fn_of": fn_of, "records": records}


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------

def _synthetic():
    """Code section at 0x10000 + data section at 0x20000.

    0x10000 fn A: mov.l @(pc) r1 -> 0x1000c (0xCAFE0001, referenced, direct)
    0x10002       mova  @(pc) r0 -> 0x10010 (PC-relative address)
    0x10004       mov.w @(pc) r2 -> 0x10014 (16-bit 0x4e20)
    0x10006       rts ; 0x10008 nop (delay) ; 0x1000a pad 0x0009
    0x1000c pool  0xCAFE0001 (referenced)
    0x10010       0x00020000 (mova target; data pointer)
    0x10014       0x00004e20 (mov.w half 0x4e20 + zero half)
    0x10018       0xBEEF0002 (false pool word: inside the block, nobody reads it)
    0x1001c fn B: sts.l pr,@-r15 (prologue) ... 0x10028 rts; nop
    0x1002c       0xBEEF0002 again, after rts with no reader (unreferenced)
    0x20000 data  0xCAFE0001 (pool-in-data: same value in a data section)
    0x20004       0x00020008 (data pointer to the string)
    0x20008       "x:;:y\\0"
    """
    code = bytearray(0x30)
    h = lambda off, w: struct.pack_into("<H", code, off, w)  # noqa: E731
    h(0x00, 0xD100 | 2)          # mov.l @(2*4 + ((0x10000+4)&~3)) = 0x1000c
    h(0x02, 0xC700 | 3)          # mova ((0x10002+4)&~3)+12 = 0x10010
    h(0x04, 0x9200 | 7)          # mov.w 0x10004+4+14 = 0x10016? -> adjust below
    h(0x06, 0x000B)
    h(0x08, 0x0009)
    h(0x0A, 0x0009)
    struct.pack_into("<I", code, 0x0C, 0xCAFE0001)
    struct.pack_into("<I", code, 0x10, 0x00020004)
    struct.pack_into("<I", code, 0x14, 0x00004E20)
    struct.pack_into("<I", code, 0x18, 0xBEEF0002)
    h(0x1C, 0x4F22)
    h(0x1E, 0xD200 | 2)          # mov.l ((0x1001e+4)&~3)+8 = 0x1002c? keep pointing in-pool below
    h(0x20, 0x0009)
    h(0x22, 0x0009)
    h(0x24, 0x4F26)
    h(0x26, 0x0009)
    h(0x28, 0x000B)
    h(0x2A, 0x0009)
    struct.pack_into("<I", code, 0x2C, 0xBEEF0002)
    # fix mov.w to the 0x4e20 half at 0x10014: disp = (0x10014 - 0x10004 - 4)/2 = 6
    h(0x04, 0x9200 | 6)
    # fn B's load: drop it (a nop) so 0x1002c stays unreferenced
    h(0x1E, 0x0009)
    data = bytearray(0x14)
    struct.pack_into("<I", data, 0, 0xCAFE0001)
    struct.pack_into("<I", data, 4, 0x00020008)   # pointer to the string
    data[8:14] = b"x:;:y\0"
    return [Seg(0x10000, code, True, "sec0"), Seg(0x20000, data, False, "sec1")]


def selftest():
    fails = []

    def check(name, got, want):
        ok = got == want
        print("%s %s%s" % ("ok  " if ok else "FAIL", name, "" if ok else ": got %r want %r" % (got, want)))
        if not ok:
            fails.append(name)

    p = Pools(_synthetic())
    extra = {"not_searched": []}
    r = query_word(p, 0xCAFE0001, extra)
    check("direct mov.l: 1 referenced pool word", r["referenced_pool_words"], 1)
    check("direct mov.l: source 0x00010000", r["rows"][0]["refs"][0]["va"], "0x00010000")
    check("direct mov.l: structural pool", r["rows"][0]["pool"], True)
    check("pool-in-data: data hit reported, not a pool", [d["va"] for d in r["data_aligned"]], ["0x00020000"])
    r = query_word(p, 0x00010010, extra)
    check("PC-relative mova target", r["mova_targets"], ["0x00010002"])
    r = query_word(p, 0x4E20, extra)
    check("mov.w 16-bit half 0x4e20", [w["va"] for w in r["movw16"]], ["0x00010014"])
    r = query_word(p, 0xBEEF0002, extra)
    check("false pool word: 2 aligned hits", r["exec_aligned"], 2)
    check("false pool word: 0 referenced", r["referenced_pool_words"], 0)
    check("false pool word: both unreferenced", r["unreferenced"], 2)
    u = unreferenced(p)
    check("--unreferenced finds the in-block false word", 0x10018 in u, True)
    rb = query_bytes(p, bytes.fromhex("3a3b3a"), extra)
    check("bytes: one occurrence", rb["occurrences"], 1)
    check("bytes: string start", rb["hits"][0]["string_start"], "0x00020008")
    check("bytes: data pointer to the string start",
          [d["at"] for d in rb["hits"][0]["data_pointers"]], ["0x00020004"])
    check("bytes: referenced through the mova pointer word? (pool word value)",
          rb["referenced"], 0)
    check("parent-of inside fn B (prologue after pool)", parent_of(p, 0x10024)[0], 0x1001C)
    check("parent-of fn A from section start", parent_of(p, 0x10004)[0], 0x10000)
    # a data halfword that decodes as mov.l must be dropped when it sits in a pool
    code = bytearray(0x20)
    struct.pack_into("<HHHH", code, 0, 0xD101, 0x000B, 0x0009, 0x0009)  # mov.l ->0x10008
    struct.pack_into("<I", code, 8, 0x0000D201)    # pool word whose low half is 0xD201
    struct.pack_into("<I", code, 0x0C, 0x12345678)
    p2 = Pools([Seg(0x10000, code, True, "sec0")])
    check("pool data decoding as mov.l is not a reference",
          [t for t in p2.ref32], [0x10008])
    check("range query", [r["value"] for r in query_range(p, 0xCAFE0000, 0xCAFEFFFF)], ["0xcafe0001"])
    # 0x0041c7e8 regression shape: previous fn ends rts, pool, then prologue
    code = bytearray(0x20)
    struct.pack_into("<HHHHHH", code, 0, 0xD101, 0x000B, 0x0009, 0x0009, 0x0000, 0x0000)
    struct.pack_into("<I", code, 0x08, 0x0041C404)
    struct.pack_into("<HHHHHH", code, 0x0C, 0x2F86, 0x2F96, 0x2FA6, 0x0009, 0x000B, 0x0009)
    p3 = Pools([Seg(0x10000, code, True, "sec0")])
    check("parent-of after a pool block (0x0041c7e8 shape)", parent_of(p3, 0x10014)[0], 0x1000C)
    # early return inside fn C (no entry after rts) vs a bsr-called leaf D
    code = bytearray(0x20)
    struct.pack_into("<16H", code, 0,
                     0x2F86,   # 0x10000 fn C: mov.l r8,@-r15
                     0x8901,   # 0x10002 bt 0x10008
                     0x000B,   # 0x10004 rts (early return)
                     0x68F6,   # 0x10006 delay
                     0xE001,   # 0x10008 mov #1,r0   (still fn C)
                     0xB002,   # 0x1000a bsr 0x10012 -> leaf D
                     0x0009,   # 0x1000c
                     0x000B,   # 0x1000e rts
                     0x68F6,   # 0x10010 delay
                     0xE002,   # 0x10012 leaf D: mov #2,r0
                     0x000B,   # 0x10014 rts
                     0x0009, 0, 0, 0, 0)
    p4 = Pools([Seg(0x10000, code, True, "sec0")])
    check("parent-of past an early rts (not an entry)", parent_of(p4, 0x1000a)[0], 0x10000)
    check("parent-of a bsr-called leaf after rts", parent_of(p4, 0x10014)[0], 0x10012)
    print("sh4literal selftest: %s" % ("FAIL %s" % fails if fails else "PASS"))
    return 1 if fails else 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _int(s):
    return int(s, 0)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?")
    ap.add_argument("module", nargs="?")
    ap.add_argument("query", nargs="*", help="find WORD... | bytes HEX")
    ap.add_argument("--image-start", type=_int, default=DEFAULT_IMAGE_START)
    ap.add_argument("--range", nargs=2, type=_int, metavar=("LO", "HI"))
    ap.add_argument("--window", nargs=2, type=_int, metavar=("LO", "HI"),
                    help="find: keep only hits whose pool or a reference lies in [LO, HI)")
    ap.add_argument("--unreferenced", action="store_true")
    ap.add_argument("--parent-of", nargs="+", type=_int, metavar="VA")
    ap.add_argument("--parent-audit", action="store_true")
    ap.add_argument("--no-decode", action="store_true",
                    help="do not decode compressed sections (they print NOT SEARCHED)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.image or not a.module:
        ap.error("IMG and MODULE are required (or --selftest)")
    if not os.path.isfile(a.image):
        print("no image at %s" % a.image)
        return 2
    segs, extra = load_image_segs(a.image, a.image_start, a.module, decode=not a.no_decode)
    pools = Pools(segs)
    fn_of = extra["fn_of"]
    out = {"module": a.module, "image_start": _hx(a.image_start), "corpus": extra["cover"],
           "pool_words_referenced": len(pools.ref32),
           "pool_words_structural": sum(1 for t in pools.ref32 if t in pools.structural),
           "movw_halves_referenced": len(pools.ref16), "mova_targets": len(pools.mova)}
    if not a.json:
        print("# %s @ %s" % (a.module, _hx(a.image_start)))
        for c in extra["cover"]:
            print("# corpus %s" % c)
        print("# pool words referenced %d (structural %d), mov.w halves %d, mova targets %d"
              % (out["pool_words_referenced"], out["pool_words_structural"],
                 out["movw_halves_referenced"], out["mova_targets"]))
    window = tuple(a.window) if a.window else None
    if a.query:
        kind, rest = a.query[0], a.query[1:]
        if kind == "find" and rest:
            res = [query_word(pools, _int(w), extra, fn_of, window) for w in rest]
            out["find"] = res
            if not a.json:
                for r in res:
                    ns = " NOT SEARCHED (section %s)" % ",".join(map(str, r["not_searched"])) \
                        if r["not_searched"] else ""
                    print("find %s: exec aligned %d, referenced pool words %d (%d refs), "
                          "unreferenced %d, mova %d, mov.w16 %d, data/decoded aligned %d%s"
                          % (r["word"], r["exec_aligned"], r["referenced_pool_words"],
                             r["references"], r["unreferenced"], len(r["mova_targets"]),
                             len(r["movw16"]), len(r["data_aligned"]), ns))
                    for row in r["rows"]:
                        refs = ", ".join("%s%s" % (x["va"], " fn " + x["fn"] if x["fn"] else "")
                                         for x in row["refs"])
                        print("  %s %s %s%s%s" % (row["va"], row["section"], row["status"],
                                                 "" if row["pool"] or not row["refs"] else " (non-structural)",
                                                 " <- " + refs if refs else ""))
                    for w in r["movw16_rows"]:
                        print("  mov.w half %s <- %s" % (w["va"], ", ".join(w["refs"])))
                    for d in r["data_aligned"]:
                        print("  data %s %s pointed_by %s" % (d["va"], d["section"], d["pointed_by"] or "-"))
        elif kind == "bytes" and len(rest) == 1:
            r = query_bytes(pools, bytes.fromhex(rest[0]), extra)
            out["bytes"] = r
            if not a.json:
                print("bytes %s: occurrences %d, referenced by code %d, pointed to by data %d%s"
                      % (r["bytes"], r["occurrences"], r["referenced"], r["data_pointed"],
                         " NOT SEARCHED (section %s)" % ",".join(map(str, r["not_searched"]))
                         if r["not_searched"] else ""))
                for hh in r["hits"]:
                    print("  %s %s string_start %s pool_pointers %d mova %d data_pointers %d"
                          % (hh["va"], hh["section"], hh["string_start"],
                             len(hh["pool_pointers"]), len(hh["mova"]), len(hh["data_pointers"])))
        else:
            ap.error("query must be 'find WORD [WORD...]' or 'bytes HEX'")
    if a.range:
        rows = query_range(pools, *a.range)
        out["range"] = rows
        if not a.json:
            print("range %s..%s: %d referenced pool words" % (_hx(a.range[0]), _hx(a.range[1]), len(rows)))
            for r in rows:
                print("  %s = %s <- %s" % (r["pool"], r["value"], ", ".join(r["refs"])))
    if a.unreferenced:
        u = unreferenced(pools)
        blocks = pool_blocks(pools)
        out["unreferenced"] = {"pool_blocks": len(blocks), "count": len(u),
                               "first": [_hx(x) for x in u[:20]]}
        if not a.json:
            print("unreferenced: %d words inside %d pool blocks (first: %s)"
                  % (len(u), len(blocks), " ".join(_hx(x) for x in u[:10])))
    if a.parent_of:
        res = []
        for va in a.parent_of:
            st, how = parent_of(pools, va)
            pd = fn_of(va) if fn_of else None
            verdict = "AGREE" if pd is not None and pd == st else \
                ("NO PDATA" if pd is None else "DIFFER")
            res.append({"va": _hx(va), "parent": _hx(st) if st is not None else None,
                        "how": how, "pdata": _hx(pd) if pd is not None else None,
                        "verdict": verdict})
            if not a.json:
                print("parent-of %s: fn %s (%s); pdata fn %s %s"
                      % (_hx(va), _hx(st) if st is not None else "?", how,
                         _hx(pd) if pd is not None else "-", verdict))
        out["parent_of"] = res
    if a.parent_audit:
        recs = extra["records"] or []
        agree = differ = 0
        examples = []
        for begin, _pro, length in recs:
            va = (begin + length // 2) & ~1
            st, _how = parent_of(pools, va)
            if st == begin:
                agree += 1
            else:
                differ += 1
                if len(examples) < 10:
                    examples.append("%s:%s" % (_hx(va), _hx(st) if st is not None else "?"))
        out["parent_audit"] = {"functions": len(recs), "agree": agree, "differ": differ,
                               "examples": examples}
        if not a.json:
            print("parent-audit: %d pdata functions (mid-point VA), agree %d, differ %d (%.2f%%)"
                  % (len(recs), agree, differ, 100.0 * differ / max(1, len(recs))))
            print("  first differ: %s" % " ".join(examples))
    if a.json:
        print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
