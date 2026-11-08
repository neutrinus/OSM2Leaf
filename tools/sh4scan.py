#!/usr/bin/env python3
"""Committed SH-4 halfword scans: the searches behind the M3.11, M3.13 and M3.2b negatives.

Each scan reads the stored bytes of the o32 sections of one CE build (chosen
by ``--image-start``, for example 0x200200 = build A) and matches 16-bit
instruction encodings at even virtual addresses only. Halfwords are
little-endian: SH-4 code in this image is little-endian (AGENTS.md), so a
big-endian search finds nothing. A pattern scan is halfword arithmetic, not
disassembly, so ``capstone`` is not needed.

Encodings (SH-4 manual, 16-bit words, shown as the halfword value):

  cmp/eq #imm,R0      0x88ii          tag tests (POINT 0x60/0x68, ADDRE 0xc0/0xc8)
  and    #imm,R0      0xC9ii          mask tests (M3.11: and #0x70, and #0xf7)
  mov.b @(1,Rm),R0    0x84m1 (mask 0xFF0F == 0x8401)   length byte at +1
  shll   R0           0x4000          doubling of the length (2*L)
  add    R0,R0        0x300C          doubling by add
  add    R0,Rn        0x300C | n<<8   cursor advance by the doubled length

Subcommands (all print the corpus they covered):

  corpus                    list every o32 section of the selected modules
  tags    [--module M]      exact cmp/eq #tag hits and tag pairs within a window
  pattern HEX [--module M]  exact aligned halfword HEX (the TODO's ``--pattern``)
  mask-pair [--module M]    and #imm,R0 then cmp/eq #tag,R0; --via-reg: mov #imm,Rn; and Rn,R0; cmp/eq
  stride  [--module M]      mov.b @(1,Rm),R0 -> doubling -> add to Rm, funnel counts
  anchors [--module M]      zlib error/banner strings (M3.2b anchor list)

Compressed sections (IMAGE_SCN_COMPRESSED) are not decoded (AGENTS.md: the
decompressor is M1.2f / M8.E1). They are listed by ``corpus`` and counted as
skipped by every scan; a scan never reads them as code.

Exit codes: 0 ok, 1 self-test failed or a corpus read error, 2 usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import struct
import sys
from array import array
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cerom  # noqa: E402
import sh4dis  # noqa: E402

# SH-4 16-bit encodings (halfword values, read as little-endian from memory).
CMP_EQ_IMM_R0 = 0x8800      # 0x88ii: cmp/eq #ii,R0
AND_IMM_R0 = 0xC900         # 0xC9ii: and #ii,R0
MOV_B_DISP1_R0 = 0x8401     # 0x84m1: mov.b @(1,Rm),R0 (test with mask 0xFF0F)
SHLL_R0 = 0x4000            # shll R0
ADD_R0_R0 = 0x300C          # add R0,R0 (n=0, m=0)

DEFAULT_READ_MIB = 256      # the firmware is in the first ~100 MB (AGENTS.md)
DEFAULT_TAGS = (0x60, 0x68)
DEFAULT_PAIR_BYTES = 24     # M3.11 / M3.13 "pairs within 24 B"
DEFAULT_MASK_BYTES = 14     # M3.11 "and #0xf7 then cmp/eq within 14 B"
DEFAULT_STRIDE_HW = 8       # halfwords per stride stage (16 bytes)
# The three families of the M3.2b table (14 hits in build A). "invalid block
# type" is named in M3.2b's Inputs list but has no row in its table; it is
# counted and printed separately (ZLIB_EXTRA), never folded into the 14.
ZLIB_MARKERS = (
    b"incorrect header check",
    b"invalid stored block lengths",
    b"inflate 1.1.",
)
ZLIB_EXTRA = (b"invalid block type",)


@dataclass
class Sec:
    module: str
    index: int
    va: int
    file_off: int
    psize: int
    vsize: int
    flags: int
    compressed: bool
    blob: bytes = b""
    vals: array = field(default_factory=lambda: array("H"))

    @property
    def name(self):
        return "sec%d" % self.index


def halfword_array(blob):
    """Little-endian halfwords of ``blob`` (an odd trailing byte is dropped).

    The LE convention is pinned in ``tools/sh4dis.py`` (M1.14: no duplicate
    reader); this keeps the array representation for scan speed.
    """
    return sh4dis.halfwords_le(blob)


def load_sections(r, data, module=None):
    """Every o32 section of the selected modules, as ``Sec`` records."""
    secs = []
    for mod in r.modules():
        name = mod["name"] or "?"
        if module and name.lower() != module.lower():
            continue
        try:
            raw = list(r.o32(mod))
        except (struct.error, ValueError, KeyError, TypeError):
            continue
        for i, s in enumerate(raw):
            comp = bool(s["flags"] & cerom.IMAGE_SCN_COMPRESSED)
            off = r.va2file(s["dataptr"])
            sec = Sec(module=name, index=i, va=s["realaddr"], file_off=off,
                      psize=s["psize"], vsize=s["vsize"], flags=s["flags"], compressed=comp)
            if not comp:
                sec.blob = data[off:off + s["psize"]]
                if len(sec.blob) != s["psize"]:
                    raise ValueError("%s sec%d: stored bytes run past the read window "
                                     "(file 0x%x, psize %d); raise --read-mib"
                                     % (name, i, off, s["psize"]))
                sec.vals = halfword_array(sec.blob)
            secs.append(sec)
    return secs


def corpus_summary(secs):
    unc = [s for s in secs if not s.compressed]
    comp = [s for s in secs if s.compressed]
    p_unc = sum(s.psize for s in unc)
    p_comp = sum(s.psize for s in comp)
    v_unc = sum(s.vsize for s in unc)
    v_comp = sum(s.vsize for s in comp)
    return dict(
        sections=len(secs), uncompressed=len(unc), compressed=len(comp),
        uncompressed_psize=p_unc, compressed_psize=p_comp,
        uncompressed_vsize=v_unc, compressed_vsize=v_comp,
        compressed_share_vsize=(100.0 * v_comp / (v_unc + v_comp)) if (v_unc + v_comp) else 0.0,
        compressed_share_psize=(100.0 * p_comp / (p_unc + p_comp)) if (p_unc + p_comp) else 0.0,
    )


def corpus_line(secs):
    c = corpus_summary(secs)
    return ("corpus: %d sections (%d uncompressed, %d compressed); uncompressed %d B psize "
            "(%d B vsize); compressed %d B psize / %d B vsize; compressed share %.2f%% of "
            "vsize, %.2f%% of psize"
            % (c["sections"], c["uncompressed"], c["compressed"], c["uncompressed_psize"],
               c["uncompressed_vsize"], c["compressed_psize"], c["compressed_vsize"],
               c["compressed_share_vsize"], c["compressed_share_psize"]))


# ---------------------------------------------------------------------------
# Pattern semantics (pure functions on halfword arrays; pinned by --selftest)
# ---------------------------------------------------------------------------


def find_exact(vals, value):
    """Halfword indices where ``vals[i] == value`` (aligned by construction)."""
    return [i for i, v in enumerate(vals) if v == value]


def tag_hits(vals, tags):
    """(index, tag) for each cmp/eq #tag,R0 halfword with a tag in ``tags``."""
    wanted = set(tags)
    out = []
    for i, v in enumerate(vals):
        if v & 0xFF00 == CMP_EQ_IMM_R0 and (v & 0xFF) in wanted:
            out.append((i, v & 0xFF))
    return out


def tag_pairs(hits, window_bytes):
    """Pairs of distinct tags whose halfwords lie within ``window_bytes`` (both directions)."""
    max_hw = window_bytes // 2
    pairs = 0
    for a in range(len(hits)):
        for b in range(a + 1, len(hits)):
            ia, ta = hits[a]
            ib, tb = hits[b]
            if ib - ia > max_hw:
                break
            if ta != tb:
                pairs += 1
    return pairs


def mask_pairs(vals, and_imm, cmp_tag, window_bytes):
    """Sites where ``and #and_imm,R0`` is followed by ``cmp/eq #cmp_tag,R0`` within the window."""
    and_word = AND_IMM_R0 | (and_imm & 0xFF)
    cmp_word = CMP_EQ_IMM_R0 | (cmp_tag & 0xFF)
    max_hw = window_bytes // 2
    sites = []
    for i, v in enumerate(vals):
        if v != and_word:
            continue
        for j in range(i + 1, min(len(vals), i + 1 + max_hw)):
            if vals[j] == cmp_word:
                sites.append((i, j))
                break
    return sites


def mask_pairs_via_reg(vals, and_imm, cmp_tag, window_bytes):
    """Register-AND variant: ``mov #and_imm,Rn``; ``and Rn,R0``; ``cmp/eq #cmp_tag,R0``.

    The mask immediate is loaded into Rn and ANDed into R0 via a register
    (M3.20 / EXP-2026-11-08-M3.19-sh4scan §5: the site M3.11 reported as
    ``and #0x70,r0`` is ``mov #0x70,R3; and R3,R0; cmp/eq #0x60,R0``).
    Returns (i_mov, i_and, i_cmp, reg) tuples, matched within ``window_bytes``
    from the ``mov`` to the ``cmp/eq``.
    """
    cmp_word = CMP_EQ_IMM_R0 | (cmp_tag & 0xFF)
    max_hw = window_bytes // 2
    sites = []
    for i, v in enumerate(vals):
        if (v & 0xF0FF) != (0xE000 | (and_imm & 0xFF)):
            continue
        reg = (v >> 8) & 0xF
        and_reg_word = 0x2009 | (reg << 4)  # and Rn,R0
        i_and = None
        for j in range(i + 1, min(len(vals), i + 1 + max_hw)):
            if vals[j] == and_reg_word:
                i_and = j
                break
        if i_and is None:
            continue
        for k in range(i_and + 1, min(len(vals), i + 1 + max_hw)):
            if vals[k] == cmp_word:
                sites.append((i, i_and, k, reg))
                break
    return sites


def stride_funnel(vals, window_hw):
    """Three nested stages of the M3.11 length-stride heuristic.

    stage1: ``mov.b @(1,Rm),R0`` (length byte loaded into R0).
    stage2: stage1 and a doubling of R0 (``shll R0`` or ``add R0,R0``) within the window.
    stage3: stage2 and ``add R0,Rm`` (the cursor Rm advances by 2*L) within the window.
    Returns (stage1, stage2, stage3) site lists of (mov_index, base_reg).
    """
    s1, s2, s3 = [], [], []
    n = len(vals)
    for i, v in enumerate(vals):
        if v & 0xFF0F != MOV_B_DISP1_R0:
            continue
        base = (v >> 4) & 0xF
        s1.append((i, base))
        dbl = None
        for j in range(i + 1, min(n, i + 1 + window_hw)):
            if vals[j] in (SHLL_R0, ADD_R0_R0):
                dbl = j
                break
        if dbl is None:
            continue
        s2.append((i, base))
        for k in range(dbl + 1, min(n, dbl + 1 + window_hw)):
            w = vals[k]
            # add Rm,Rn with Rn = base and Rm = R0 (the doubled length)
            if w & 0xF00F == 0x300C and (w >> 8) & 0xF == base and (w >> 4) & 0xF == 0:
                s3.append((i, base))
                break
    return s1, s2, s3


def anchor_hits(blob, markers=ZLIB_MARKERS):
    """(offset, marker) for each zlib anchor string in ``blob``."""
    out = []
    for marker in markers:
        start = 0
        while True:
            k = blob.find(marker, start)
            if k < 0:
                break
            out.append((k, marker))
            start = k + 1
    return sorted(out)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def scanned(secs):
    return [s for s in secs if not s.compressed]


def header(args, secs, digest, size):
    print("image: %s  size %d  sha256(read) %s  image_start 0x%x  module %s"
          % (os.path.basename(args.image), size, digest, args.image_start,
             args.module or "(all)"))
    print(corpus_line(secs))


def cmd_corpus(args, r, secs):
    for s in secs:
        state = "compressed" if s.compressed else "uncompressed"
        print("%-16s %-5s va 0x%08x file 0x%08x psize %9d vsize %9d flags 0x%08x %s"
              % (s.module, s.name, s.va, s.file_off, s.psize, s.vsize, s.flags, state))
    return 0


def va_of(sec, hw_index):
    return sec.va + 2 * hw_index


def cmd_tags(args, r, secs):
    tags = [int(t, 16) for t in args.tags.split(",")]
    per_tag = {t: 0 for t in tags}
    pairs = 0
    rows = []
    for sec in scanned(secs):
        hits = tag_hits(sec.vals, tags)
        for i, t in hits:
            per_tag[t] += 1
            rows.append((sec, i, t))
        pairs += tag_pairs([(i, t) for i, t in hits], args.pair_bytes)
    for t in tags:
        print("cmp/eq #0x%02x,R0 (0x%04x), aligned: %d" % (t, CMP_EQ_IMM_R0 | t, per_tag[t]))
    print("tag pairs (distinct tags within %d B): %d" % (args.pair_bytes, pairs))
    if args.list:
        for sec, i, t in rows:
            print("  %s %s va 0x%08x tag 0x%02x" % (sec.module, sec.name, va_of(sec, i), t))
    return 0


def cmd_pattern(args, r, secs):
    value = int(args.hex, 16)
    if not 0 <= value <= 0xFFFF:
        print("error: pattern must be one halfword (0000..ffff)", file=sys.stderr)
        return 2
    total = 0
    for sec in scanned(secs):
        for i in find_exact(sec.vals, value):
            total += 1
            print("  %s %s va 0x%08x" % (sec.module, sec.name, va_of(sec, i)))
    print("pattern 0x%04x (LE bytes %02x %02x), aligned hits: %d"
          % (value, value & 0xFF, value >> 8, total))
    return 0


def cmd_mask_pair(args, r, secs):
    and_imm = int(args.and_imm, 16)
    cmp_tag = int(args.cmp, 16)
    total = 0
    if getattr(args, "via_reg", False):
        for sec in scanned(secs):
            for i, j, k, reg in mask_pairs_via_reg(sec.vals, and_imm, cmp_tag, args.window_bytes):
                total += 1
                print("  %s %s mov @0x%08x and @0x%08x cmp @0x%08x R%d (+%d B)"
                      % (sec.module, sec.name, va_of(sec, i), va_of(sec, j),
                         va_of(sec, k), reg, 2 * (k - i)))
        print("mov #0x%02x,Rn; and Rn,R0; cmp/eq #0x%02x,R0 within %d B: %d"
              % (and_imm, cmp_tag, args.window_bytes, total))
        return 0
    for sec in scanned(secs):
        for i, j in mask_pairs(sec.vals, and_imm, cmp_tag, args.window_bytes):
            total += 1
            print("  %s %s and @0x%08x cmp @0x%08x (+%d B)"
                  % (sec.module, sec.name, va_of(sec, i), va_of(sec, j), 2 * (j - i)))
    print("and #0x%02x,R0 then cmp/eq #0x%02x,R0 within %d B: %d"
          % (and_imm, cmp_tag, args.window_bytes, total))
    return 0


def cmd_stride(args, r, secs):
    window = args.window_hw
    t1 = t2 = t3 = 0
    for sec in scanned(secs):
        s1, s2, s3 = stride_funnel(sec.vals, window)
        t1 += len(s1)
        t2 += len(s2)
        t3 += len(s3)
        for i, base in s3:
            print("  %s %s mov.b @(1,R%d),R0 @0x%08x -> doubling -> add R0,R%d"
                  % (sec.module, sec.name, base, va_of(sec, i), base))
    print("mov.b @(1,Rm),R0 sites: %d" % t1)
    print("  + doubling of R0 within %d hw: %d" % (window, t2))
    print("  + add R0,Rm cursor advance within %d hw: %d" % (window, t3))
    return 0


def cmd_anchors(args, r, secs):
    markers = ZLIB_MARKERS + ZLIB_EXTRA
    per_marker = {m: 0 for m in markers}
    total = 0
    for sec in scanned(secs):
        for off, marker in anchor_hits(sec.blob, markers):
            per_marker[marker] += 1
            if marker in ZLIB_MARKERS:
                total += 1
            print("  %s %s va 0x%08x  %r" % (sec.module, sec.name, sec.va + off, marker))
    for m in ZLIB_MARKERS:
        print("marker %r (M3.2b table): %d" % (m.decode(), per_marker[m]))
    for m in ZLIB_EXTRA:
        print("marker %r (named in M3.2b Inputs, no table row): %d" % (m.decode(), per_marker[m]))
    print("zlib anchor hits in uncompressed sections (M3.2b table families): %d" % total)
    return 0


def decode_halfword(w):
    """Short mnemonic for the encodings this tool matches; '' when unknown."""
    if w & 0xFF00 == CMP_EQ_IMM_R0:
        return "cmp/eq #0x%02x,R0" % (w & 0xFF)
    if w & 0xFF00 == AND_IMM_R0:
        return "and #0x%02x,R0" % (w & 0xFF)
    if w & 0xFF0F == MOV_B_DISP1_R0:
        return "mov.b @(1,R%d),R0" % ((w >> 4) & 0xF)
    if w & 0xF000 == 0xE000:
        imm = w & 0xFF
        value = imm - 256 if imm & 0x80 else imm
        return "mov #%s,R%d" % (hex(value), (w >> 8) & 0xF)
    if w & 0xF00F == 0x2009:
        return "and R%d,R%d" % ((w >> 4) & 0xF, (w >> 8) & 0xF)
    if w & 0xF00F == 0x300C:
        return "add R%d,R%d" % ((w >> 4) & 0xF, (w >> 8) & 0xF)
    if w == SHLL_R0:
        return "shll R0"
    if w == 0x0009:
        return "nop"
    return ""


def cmd_dump(args, r, secs):
    va = int(args.va, 0)
    for sec in scanned(secs):
        if sec.va <= va < sec.va + sec.psize:
            start = (va - sec.va) // 2
            for i in range(start, min(len(sec.vals), start + args.count)):
                w = sec.vals[i]
                print("  %s %s va 0x%08x  %04x  %s" % (sec.module, sec.name, va_of(sec, i), w,
                                                    decode_halfword(w)))
            return 0
    print("error: va 0x%08x is not in an uncompressed section of the selected modules" % va,
          file=sys.stderr)
    return 1


COMMANDS = {
    "dump": cmd_dump,
    "corpus": cmd_corpus,
    "tags": cmd_tags,
    "pattern": cmd_pattern,
    "mask-pair": cmd_mask_pair,
    "stride": cmd_stride,
    "anchors": cmd_anchors,
}


# ---------------------------------------------------------------------------
# Self-test: pins the pattern semantics on synthetic halfwords (no image)
# ---------------------------------------------------------------------------


def hw(*words):
    """Little-endian bytes of the given halfword values."""
    return b"".join(struct.pack("<H", w) for w in words)


NOP = 0x0009


def selftest():
    fails = []

    def check(name, got, want):
        if got != want:
            fails.append("%s: got %r want %r" % (name, got, want))

    # 1. Little-endian decoding.
    blob = hw(CMP_EQ_IMM_R0 | 0x60)           # bytes 60 88
    check("le-bytes", bytes(blob), b"\x60\x88")
    check("le-hit", find_exact(halfword_array(blob), 0x8860), [0])
    check("be-reading-not-hit", find_exact(halfword_array(b"\x88\x60"), 0x8860), [])

    # 2. Alignment: the odd-address false positive M3.11 rejected.
    odd = b"\x00\x60\x88\x00"                 # 0x8860 starts at byte 1 (odd)
    arr = halfword_array(odd)
    check("odd-address-not-matched", find_exact(arr, 0x8860), [])
    check("even-address-matched", find_exact(halfword_array(b"\x60\x88\x00\x00"), 0x8860), [0])

    # 3. Tag tests and pairs (within 24 B = 12 halfwords).
    near = halfword_array(hw(CMP_EQ_IMM_R0 | 0x60, NOP, NOP, NOP, NOP, NOP, NOP, NOP,
                             NOP, NOP, NOP, CMP_EQ_IMM_R0 | 0x68))   # 0x60 @0, 0x68 @22 B
    h = tag_hits(near, (0x60, 0x68))
    check("tag-hits", h, [(0, 0x60), (11, 0x68)])
    check("pair-at-22B", tag_pairs(h, 24), 1)
    far = halfword_array(hw(CMP_EQ_IMM_R0 | 0x60) + hw(NOP) * 13 + hw(CMP_EQ_IMM_R0 | 0x68))
    check("pair-at-28B-rejected", tag_pairs(tag_hits(far, (0x60, 0x68)), 24), 0)
    check("same-tag-not-a-pair",
          tag_pairs(tag_hits(halfword_array(hw(CMP_EQ_IMM_R0 | 0x60, NOP, CMP_EQ_IMM_R0 | 0x60)),
                             (0x60,)), 24), 0)

    # 4. and #imm,R0 then cmp/eq #tag,R0 within 14 B (7 halfwords).
    m = halfword_array(hw(AND_IMM_R0 | 0x70, NOP, NOP, CMP_EQ_IMM_R0 | 0x60))   # +6 B
    check("mask-hit-6B", mask_pairs(m, 0x70, 0x60, 14), [(0, 3)])
    m14 = halfword_array(hw(AND_IMM_R0 | 0x70) + hw(NOP) * 6 + hw(CMP_EQ_IMM_R0 | 0x60))  # +14 B
    check("mask-hit-edge-14B", len(mask_pairs(m14, 0x70, 0x60, 14)), 1)
    m16 = halfword_array(hw(AND_IMM_R0 | 0x70) + hw(NOP) * 7 + hw(CMP_EQ_IMM_R0 | 0x60))  # +16 B
    check("mask-miss-16B", mask_pairs(m16, 0x70, 0x60, 14), [])
    check("and-f7-is-not-and-70",
          mask_pairs(halfword_array(hw(AND_IMM_R0 | 0xF7, NOP, CMP_EQ_IMM_R0 | 0x60)), 0x70, 0x60, 14), [])

    # 4b. Register-AND variant (M3.20): mov #imm,Rn; and Rn,R0; cmp/eq #tag,R0.
    # The M3.19/M3.11 site: mov #0x70,R3 (E370); and R3,R0 (2039); cmp/eq #0x60,R0 (8860).
    via = halfword_array(hw(0xE370, 0x2039, 0x8860))
    check("via-reg-site", mask_pairs_via_reg(via, 0x70, 0x60, 14), [(0, 1, 2, 3)])
    check("via-reg-not-immediate", mask_pairs(via, 0x70, 0x60, 14), [])
    check("via-reg-wrong-imm", mask_pairs_via_reg(via, 0x71, 0x60, 14), [])
    check("via-reg-wrong-cmp", mask_pairs_via_reg(via, 0x70, 0x68, 14), [])
    # Register pairing: mov loads R3 but and uses R4 — must not match.
    mis = halfword_array(hw(0xE370, 0x2049, 0x8860))
    check("via-reg-wrong-reg-pair", mask_pairs_via_reg(mis, 0x70, 0x60, 14), [])
    # Window edge: mov@0, and@+6B, cmp@+14B from mov (7 halfwords gap total) fits in 14 B.
    edge = halfword_array(hw(0xE370, NOP, NOP, 0x2039) + hw(NOP) * 3 + hw(0x8860))
    check("via-reg-edge-14B", len(mask_pairs_via_reg(edge, 0x70, 0x60, 14)), 1)
    farv = halfword_array(hw(0xE370, NOP, NOP, 0x2039) + hw(NOP) * 4 + hw(0x8860))
    check("via-reg-miss-16B", mask_pairs_via_reg(farv, 0x70, 0x60, 14), [])
    # Other register (R0 is unusual but encodable): mov #0x70,R0; and R0,R0; cmp/eq #0x60,R0.
    r0 = halfword_array(hw(0xE070, 0x2009, 0x8860))
    check("via-reg-r0", mask_pairs_via_reg(r0, 0x70, 0x60, 14), [(0, 1, 2, 0)])

    # 5. Stride funnel: mov.b @(1,R3),R0 = 0x8431; shll R0; add R0,R3 = 0x330C.
    full = halfword_array(hw(0x8431, SHLL_R0, 0x330C))
    s1, s2, s3 = stride_funnel(full, 8)
    check("stride-full-stage1", s1, [(0, 3)])
    check("stride-full-stage2", s2, [(0, 3)])
    check("stride-full-stage3", s3, [(0, 3)])
    other = halfword_array(hw(0x8431, SHLL_R0, 0x350C))      # advances R5, not R3
    s1, s2, s3 = stride_funnel(other, 8)
    check("stride-other-reg-stage2", len(s2), 1)
    check("stride-other-reg-stage3", s3, [])
    nodbl = halfword_array(hw(0x8431, NOP, 0x330C))           # no doubling
    s1, s2, s3 = stride_funnel(nodbl, 8)
    check("stride-no-doubling-stage1", len(s1), 1)
    check("stride-no-doubling-stage2", s2, [])
    check("mov-b-disp2-not-counted", stride_funnel(halfword_array(hw(0x8432)), 8)[0], [])

    # 6. Anchors: zlib strings, offsets in a blob.
    blob6 = b"\x00inflate 1.1.3 Copyright\x00invalid stored block lengths\x00"
    got = anchor_hits(blob6)
    check("anchor-count", len(got), 2)
    check("anchor-offsets", [o for o, _ in got], [1, 25])
    check("anchor-extra-not-in-table", len(anchor_hits(b"invalid block type", ZLIB_MARKERS)), 0)

    # 7. Corpus accounting: compressed sections are listed and never scanned.
    sec_u = Sec("M", 0, 0x11000, 0, 4, 4, 0x68000020, False, b"\x60\x88\x00\x00",
                halfword_array(b"\x60\x88\x00\x00"))
    sec_c = Sec("M", 1, 0x55d000, 0, 6, 100, 0xc8002040, True)
    secs = [sec_u, sec_c]
    check("scanned-only-uncompressed", [s.name for s in scanned(secs)], ["sec0"])
    summ = corpus_summary(secs)
    check("corpus-sections", (summ["uncompressed"], summ["compressed"]), (1, 1))
    check("corpus-bytes", (summ["uncompressed_psize"], summ["compressed_psize"]), (4, 6))
    check("corpus-share-vsize", round(summ["compressed_share_vsize"], 2), 96.15)

    # 8. Decoder labels used by dump (observation only, not a match rule).
    check("decode-cmp", decode_halfword(0x8860), "cmp/eq #0x60,R0")
    check("decode-and-reg", decode_halfword(0x2039), "and R3,R0")
    check("decode-mov-imm", decode_halfword(0xE370), "mov #0x70,R3")
    check("decode-mov-imm-neg", decode_halfword(0xE3F0), "mov #-0x10,R3")
    check("decode-stride", decode_halfword(0x8431), "mov.b @(1,R3),R0")

    print("sh4scan selftest: %s" % ("OK" if not fails else "FAILED %d" % len(fails)))
    for f in fails:
        print("  FAIL", f)
    return 0 if not fails else 1


# ---------------------------------------------------------------------------


def build_parsers():
    """Top-level options, plus one parser for the subcommand and its options.

    The subcommand is split off argv before parsing: argparse binds an optional
    IMAGE positional to the subcommand slot when IMAGE precedes --image-start,
    so ``sh4scan.py IMG --image-start 0x200200 tags`` needs the split.
    """
    top = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    top.add_argument("image", nargs="?", help="raw image (the first --read-mib of it is read)")
    top.add_argument("--image-start", type=lambda s: int(s, 0), default=None,
                     help="CE image start, e.g. 0x200200 (build A), 0x3e00200 (B), 0x5200200 (C)")
    top.add_argument("--read-mib", type=int, default=DEFAULT_READ_MIB,
                     help="bytes of the image to read, in MiB (default %(default)s)")
    top.add_argument("--selftest", action="store_true", help="run the synthetic self-test and exit")
    sub = argparse.ArgumentParser(prog="sh4scan.py <command>", description="subcommand options")
    sub.add_argument("cmd", choices=sorted(COMMANDS), help="subcommand")
    sub.add_argument("arg", nargs="?", help="pattern: one halfword in hex")
    sub.add_argument("--va", help="dump: start VA (hex, e.g. 0x3715a0)")
    sub.add_argument("--count", type=int, default=32, help="dump: halfwords to print (default 32)")
    sub.add_argument("--module", help="module name, e.g. Navi.exe (default: all modules)")
    sub.add_argument("--tags", default="60,68", help="tag command: comma-separated hex tags (default 60,68)")
    sub.add_argument("--pair-bytes", type=int, default=DEFAULT_PAIR_BYTES, help="tag pair window in bytes")
    sub.add_argument("--list", action="store_true", help="tags: print each hit")
    sub.add_argument("--and", dest="and_imm", default="70", help="mask-pair: hex mask immediate (default 70)")
    sub.add_argument("--cmp", default="60", help="mask-pair: hex cmp/eq tag (default 60)")
    sub.add_argument("--via-reg", action="store_true",
                     help="mask-pair: register-AND variant mov #imm,Rn; and Rn,R0; cmp/eq")
    sub.add_argument("--window-bytes", type=int, default=DEFAULT_MASK_BYTES, help="mask-pair window in bytes")
    sub.add_argument("--window-hw", type=int, default=DEFAULT_STRIDE_HW,
                     help="stride: halfwords allowed between stages (default %(default)s)")
    return top, sub


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    k = next((i for i, a in enumerate(argv) if a in COMMANDS), None)
    head, tail = (argv, []) if k is None else (argv[:k], argv[k:])
    top, sub = build_parsers()
    args = top.parse_args(head)
    if args.selftest:
        return selftest()
    if not tail or not args.image or args.image_start is None:
        top.error("IMAGE, --image-start and a subcommand are required (or --selftest)")
    sargs = sub.parse_args(tail)
    if sargs.cmd == "dump" and sargs.va is None:
        sub.error("dump needs --va")
    if sargs.cmd == "pattern":
        if sargs.arg is None:
            sub.error("pattern needs one halfword in hex")
        try:
            value = int(sargs.arg, 16)
        except ValueError:
            value = -1
        if not 0 <= value <= 0xFFFF:
            print("error: pattern must be one halfword (0000..ffff)", file=sys.stderr)
            return 2
        sargs.hex = sargs.arg
    for name, value in vars(sargs).items():
        setattr(args, name, value)
    args.cmd = sargs.cmd

    size = os.path.getsize(args.image)
    with open(args.image, "rb") as fh:
        data = fh.read(args.read_mib << 20)
    digest = hashlib.sha256(data).hexdigest()
    try:
        r = cerom.CERom(data, args.image_start)
        secs = load_sections(r, data, args.module)
    except (ValueError, KeyError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    if not secs:
        print("error: no sections for module %r at image start 0x%x"
              % (args.module, args.image_start), file=sys.stderr)
        return 1
    header(args, secs, digest, size)
    return COMMANDS[args.cmd](args, r, secs)


if __name__ == "__main__":
    sys.exit(main())
