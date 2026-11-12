#!/usr/bin/env python3
"""Match functions between two builds of the same module by content.

The EU and US 2011 cards carry different ``Navi.exe`` builds (H51): the US
build is larger code, smaller BSS, and no function sits at the same address.
``fn_match.py`` matches functions without any fitted delta.

Method
-------

1. Function boundaries come from the CE ``.pdata`` section (8-byte records:
   begin VA, packed word = prologue length in bits 0-7 and function length in
   bits 8-29, both in 2-byte instructions). A VA that has no record is a leaf
   function (the POINT walker ``0x003f5194`` is the known case) or data; the
   tool names those instead of guessing.
2. Each function is hashed over its instruction halfwords with every
   position-dependent field erased:

   * PC-relative displacements (``bra``/``bsr``/``bt``/``bf``) become a fixed
     marker; the target's position relative to the function is kept only as a
     same-function/other-function bit.
   * Literal-pool words (the data a ``mov.l @(disp,PC)`` / ``mov.w`` loads)
     are hashed as *content* when they are not pointers into the module's own
     load range, and masked to a marker when they are (a relocated pointer is
     not a constant). The pool's address is never hashed.
   * Everything else (opcodes, register fields, immediates that are not
     addresses) is hashed verbatim.

   Two functions with the same hash are the same code reached from a
   different address.
3. Hashes are grouped; a digest with exactly one A function and one B
   function is a UNIQUE match. A digest with several on either side is
   AMBIGUOUS and never guessed. No shared digest is NOMATCH.
4. Unmatched functions are propagated through **call order**: if an unmatched
   A function ``f`` is only ever called (direct ``bsr``) from A functions
   that have UNIQUE B matches, and exactly one B callee of those B matches
   shares no digest with any other candidate, that B callee is the match.
   This is a one-hop propagation, reported separately from the hash matches.

``--selftest`` builds two synthetic "builds" in memory and checks: a
position-shifted body matches; a pool *pointer* is masked; a pool *constant*
is kept; a duplicated body is AMBIGUOUS and refused; the ``.pdata`` parser
decodes the packed word.

Usage:
  fn_match.py --selftest
  fn_match.py match IMG_A IMG_B [--module Navi.exe] [--image-start 0x200200]
      [--va 0x003f5194 ...] [--index-a 2 --index-b 2]
      [--pdata-a FILE] [--pdata-b FILE] [--json OUT] [--all]

``--pdata-*`` takes a JSON list of ``[begin, prologue, length]`` triples as
produced by ``nk_decomp.py pdata`` (the tool dumps it with ``--cache FILE``);
without them the tool runs the kernel decompressor itself.

Stdlib only. No vendor bytes are written to the repo.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import cerom  # noqa: E402

MEM_EXECUTE = 0x20000000

# ---------------------------------------------------------------- pdata


def parse_pdata(blob: bytes):
    """SH-4 CE ``.pdata``: 8-byte records (begin VA, packed word).

    Packed word: bits 0-7 prologue length, bits 8-29 function length, both in
    2-byte instructions; bit 30 32-bit flag, bit 31 exception flag.
    """
    out = []
    for off in range(0, len(blob) - 7, 8):
        begin, word = struct.unpack_from("<II", blob, off)
        if begin:
            out.append([begin, (word & 0xFF) * 2, ((word >> 8) & 0x3FFFFF) * 2])
    return out


def locate(pdata, va: int):
    starts = [p[0] for p in pdata]
    i = bisect.bisect_right(starts, va) - 1
    if i < 0:
        return "BEFORE", None
    begin, prolog, length = pdata[i]
    if va == begin:
        return "START", pdata[i]
    if va < begin + length:
        return "INSIDE", pdata[i]
    return "GAP", pdata[i]


def load_pdata(image, image_start, module, index, cache):
    if cache and Path(cache).is_file():
        return json.loads(Path(cache).read_text())
    import nk_decomp  # heavy: runs the kernel decompressor in PySh4
    data = Path(image).read_bytes()
    rom = cerom.CERom(data, image_start)
    s = list(rom.o32(rom.module(module)))[index]
    r0, out = nk_decomp.decompress(data, rom.va2file(s["dataptr"]),
                                   s["psize"], s["vsize"])
    pdata = parse_pdata(out[:r0])
    if cache:
        Path(cache).write_text(json.dumps(pdata))
    return pdata


# ---------------------------------------------------------------- opcodes

def is_branch(w: int) -> bool:
    hi = w >> 12
    if hi in (0xA, 0xB):                    # bra / bsr
        return True
    return hi == 0x8 and ((w >> 8) & 0xF) in (0x9, 0xB, 0xD, 0xF)  # bt/bf


def is_mov_pc(w: int) -> bool:
    return (w >> 12) in (0x9, 0xD)          # mov.w / mov.l @(disp,PC)


def pool_addr(va: int, w: int) -> int:
    if (w >> 12) == 0xD:
        return ((va + 4) & ~3) + (w & 0xFF) * 4
    return va + 4 + (w & 0xFF) * 2


def branch_target(va: int, w: int) -> int:
    if (w >> 12) in (0xA, 0xB):
        disp = w & 0xFFF
        if disp & 0x800:
            disp -= 0x1000
        return va + 4 + disp * 2
    disp = w & 0xFF
    if disp & 0x80:
        disp -= 0x100
    return va + 4 + disp * 2


def is_bsr(w: int) -> bool:
    return (w >> 12) == 0xB


# ------------------------------------------------------------ fingerprint

def fingerprint(words, base_va: int, load_range, image_bytes: bytes,
                code_base: int, iat_slots: frozenset | None = None):
    """Position-independent digest of one function.

    ``words`` are the function's halfwords; ``image_bytes`` is the whole
    (uncompressed) code section, so pool words that sit in the trailing pool
    area of the function can be read as content. A pool value that is a
    relocated pointer (inside the module's own VA range) **or** one of the
    module's import-table slots is masked: both move when the build moves.
    Everything else (immediates, small constants) is kept.
    """
    lo, hi = load_range
    iat_slots = iat_slots or frozenset()
    fp = hashlib.sha256()
    n = len(words)
    span = 2 * n
    span = 2 * n

    def pool_value(va, size):
        off = va - code_base
        if 0 <= off and off + size <= len(image_bytes):
            if size == 4:
                return struct.unpack_from("<I", image_bytes, off)[0]
            return struct.unpack_from("<H", image_bytes, off)[0]
        return None

    # Pass 1: find every literal-pool slot referenced by this function.
    # Offsets are relative to code_base (image), matching pass 2.
    pool_bytes: set[int] = set()
    pool_meta: dict[int, tuple] = {}
    for i, w in enumerate(words):
        if not is_mov_pc(w):
            continue
        va = base_va + 2 * i
        lit = pool_addr(va, w)
        off2 = lit - code_base
        size = 4 if (w >> 12) == 0xD else 2
        for k in range(size):
            pool_bytes.add(off2 + k)
        pool_meta[off2] = (lit, size, (w >> 8) & 0xF)

    # Pass 2: hash instructions; pool halfwords hash as 0x0000 (their value
    # travels through the referencing mov.* in pass 3 below).
    bsr_targets: list[int] = []
    pool_sites: list[int] = []
    for i, w in enumerate(words):
        va = base_va + 2 * i
        off = va - code_base
        if off in pool_bytes:
            fp.update(b"\x00\x00")
            continue
        if is_branch(w):
            tgt = branch_target(va, w)
            same = base_va <= tgt < base_va + span
            if is_bsr(w) and not same:
                bsr_targets.append(tgt)
            cls = (w >> 12) if (w >> 12) in (0xA, 0xB) else 0x80 | ((w >> 8) & 0xF)
            fp.update(struct.pack("<BB", cls, 1 if same else 0))
            continue
        if is_mov_pc(w):
            lit = pool_addr(va, w)
            pool_sites.append(lit)
            dest = (w >> 8) & 0xF
            fp.update(struct.pack("<BH", (w >> 12), dest))
            continue
        fp.update(struct.pack("<H", w))

    # Pass 3: hash pool contents in a canonical order (by pool offset), so a
    # relocated pointer is masked and a constant is kept.
    for off in sorted(pool_meta):
        lit, size, dest = pool_meta[off]
        val = pool_value(lit, size)
        if val is None:
            fp.update(b"\x00" * size)
        elif lo <= val < hi or val in iat_slots:
            fp.update(b"\xff" * size)
        else:
            fp.update(struct.pack("<I" if size == 4 else "<H", val))
    return fp.hexdigest(), bsr_targets, pool_sites


def shape(words):
    """Coarse structural digest: opcode nibble per instruction + branch/call
    structure only. Ignores register fields and immediates entirely. Used as a
    candidate prefilter for functions whose register allocation changed."""
    fp = hashlib.sha256()
    for w in words:
        if is_branch(w):
            cls = (w >> 12) if (w >> 12) in (0xA, 0xB) else 0x80 | ((w >> 8) & 0xF)
            fp.update(struct.pack("<B", cls))
            continue
        if is_mov_pc(w):
            fp.update(struct.pack("<B", (w >> 12)))
            continue
        fp.update(struct.pack("<B", w >> 12))
    return fp.hexdigest()


# ---------------------------------------------------------------- synthetic

def selftest() -> int:
    fails: list[str] = []

    def check(name, cond):
        print("%s %s" % ("ok  " if cond else "FAIL", name))
        if not cond:
            fails.append(name)

    # Build two synthetic "images": A with the function at 0x1000, B with the
    # same function at 0x3000. Each buffer holds the code section image; the
    # pool word sits at offset 0x14 within the function.
    body = [0xD704, 0x000B, 0x0009, 0x0000, 0x0009, 0x0000]  # mov.l @(lit,pc),r7 ; rts

    def make_code(pool_value):
        buf = bytearray(0x400)
        for k, w in enumerate(body):
            struct.pack_into("<H", buf, 2 * k, w)
        struct.pack_into("<I", buf, 0x14, pool_value)
        return bytes(buf)

    code_a = make_code(0x00001200)   # pointer into A's load range
    code_b = make_code(0x00003200)   # relocated pointer into B's load range

    f_a, _, _ = fingerprint(body, 0x1000, (0x1000, 0x1400), code_a, 0x1000)
    f_b, _, _ = fingerprint(body, 0x3000, (0x3000, 0x3400), code_b, 0x3000)
    check("relocated pool pointer is masked (position-independent)", f_a == f_b)

    code_c = make_code(0x0000BEEF)   # constant, not an address
    f_c, _, _ = fingerprint(body, 0x1000, (0x1000, 0x1400), code_c, 0x1000)
    check("pool constant that is not an address changes the hash", f_c != f_a)

    # duplicated body -> ambiguity, never a guess
    def make_dup_code(pool_value, second_off):
        buf = bytearray(0x400)
        for off in (0x000, second_off):
            for k, w in enumerate(body):
                struct.pack_into("<H", buf, off + 2 * k, w)
            struct.pack_into("<I", buf, off + 0x14, pool_value)
        return bytes(buf)

    code_a2 = make_dup_code(0x00001200, 0x030)   # A has two copies (0x1000, 0x1030)
    code_b2 = make_dup_code(0x00003200, 0x030)   # B has two copies
    matches = match_builds(
        [(0x1000, body, (0x1000, 0x1400), code_a2, 0x1000),
         (0x1030, body, (0x1000, 0x1400), code_a2, 0x1000)],
        [(0x3000, body, (0x3000, 0x3400), code_b2, 0x3000)],
    )
    check("two A candidates for one B function are AMBIGUOUS",
          all(m[2] == "AMBIGUOUS" for m in matches))
    matches = match_builds(
        [(0x1000, body, (0x1000, 0x1400), code_a, 0x1000)],
        [(0x3000, body, (0x3000, 0x3400), code_b2, 0x3000),
         (0x3030, body, (0x3000, 0x3400), code_b2, 0x3000)],
    )
    check("one A function matching two B candidates is AMBIGUOUS",
          all(m[2] == "AMBIGUOUS" for m in matches))
    # pdata packed word
    pd = parse_pdata(struct.pack("<II", 0x1000, (0x10 << 8) | 3) + b"\0" * 8)
    check("pdata packed word decodes prologue/length", pd == [[0x1000, 6, 0x20]])
    check("pdata locate START/INSIDE/GAP",
          locate(pd, 0x1000)[0] == "START" and
          locate(pd, 0x1002)[0] == "INSIDE" and
          locate(pd, 0x1030)[0] == "GAP")

    print("fn_match selftest: %s (%d failed)" % ("OK" if not fails else "FAIL", len(fails)))
    return 1 if fails else 0


def match_builds(a_funcs, b_funcs):
    """[(va, words, lr, bytes, code_base)] x2 -> [(a_va, b_va|None, verdict)]."""
    b_hash: dict[str, list[int]] = {}
    for va, words, lr, cb, cbase in b_funcs:
        d, _, _ = fingerprint(words, va, lr, cb, cbase)
        b_hash.setdefault(d, []).append(va)
    a_hash: dict[str, list[int]] = {}
    for va, words, lr, cb, cbase in a_funcs:
        d, _, _ = fingerprint(words, va, lr, cb, cbase)
        a_hash.setdefault(d, []).append(va)
    out = []
    for va, words, lr, cb, cbase in a_funcs:
        d, _, _ = fingerprint(words, va, lr, cb, cbase)
        cand = b_hash.get(d, [])
        mine = a_hash.get(d, [])
        if len(cand) == 1 and len(mine) == 1:
            out.append((va, cand[0], "UNIQUE"))
        elif cand:
            out.append((va, None, "AMBIGUOUS"))
        else:
            out.append((va, None, "NOMATCH"))
    return out


# ---------------------------------------------------------------- command

def module_range(rom, module):
    """VA span of the whole module (all sections), for pointer masking."""
    secs = list(rom.o32(rom.module(module)))
    lo = min(x["realaddr"] for x in secs)
    hi = max(x["realaddr"] + x["vsize"] for x in secs)
    return (lo, hi)


def import_index(rom, module):
    """IAT slot VA -> stable across-build token, e.g. IMPORT:COREDLL.dll:ord1047."""
    m = rom.module(module)
    out = {}
    for dll, slot, name, ordinal in rom.imports(m):
        tag = name if name else "ord%d" % (ordinal or 0)
        out[slot] = "IMPORT:%s:%s" % (dll, tag)
    return out


def code_section(image, image_start, module):
    with open(image, "rb") as fh:
        data = fh.read()
    rom = cerom.CERom(data, image_start)
    m = rom.module(module)
    secs = list(rom.o32(m))
    code = next((x for x in secs if x["flags"] & MEM_EXECUTE), secs[0])
    off = rom.va2file(code["dataptr"])
    return data, code, off, module_range(rom, module), rom



def collect_functions(data, code, off, pdata, load_range):
    base = code["realaddr"]
    size = code["vsize"]
    code_bytes = data[off:off + size]
    out = []
    for begin, prolog, length in pdata:
        if length <= 0:
            continue
        if not (base <= begin < base + size):
            continue
        words = []
        for va in range(begin, begin + length, 2):
            o = va - base
            if o + 2 > len(code_bytes):
                break
            words.append(code_bytes[o] | (code_bytes[o + 1] << 8))
        if words:
            out.append((begin, words, load_range, code_bytes, base))
    return out


def leaf_words(data, code, off, va, limit=0x400):
    base = code["realaddr"]
    size = code["vsize"]
    code_bytes = data[off:off + size]
    words = []
    for k in range(0, limit, 2):
        o = va - base + k
        if o + 2 > len(code_bytes):
            break
        w = code_bytes[o] | (code_bytes[o + 1] << 8)
        words.append(w)
        if w == 0x000B:  # rts: include its delay slot, then stop
            k += 2
            o = va - base + k
            if o + 2 <= len(code_bytes):
                words.append(code_bytes[o] | (code_bytes[o + 1] << 8))
            break
    return words


def pdata_starts(pdata):
    return [p[0] for p in pdata]


def halfword_diff(a_words, b_words):
    """Count of halfword positions that differ; also the length difference."""
    n = min(len(a_words), len(b_words))
    d = sum(1 for i in range(n) if a_words[i] != b_words[i])
    return d + abs(len(a_words) - len(b_words)), max(len(a_words), len(b_words))


def normalized_diff(a_words, b_words, base_va, load_range, image_bytes, code_base):
    """Differing instruction halfwords after erasing the position-dependent
    fields the same way ``fingerprint`` does; used to eyeball a near match."""
    def norm(words, va):
        out = []
        span = 2 * len(words)
        for i, w in enumerate(words):
            v = va + 2 * i
            if is_branch(w):
                tgt = branch_target(v, w)
                same = va <= tgt < va + span
                cls = (w >> 12) if (w >> 12) in (0xA, 0xB) else 0x80 | ((w >> 8) & 0xF)
                out.append(struct.pack("<BB", cls, 1 if same else 0))
                continue
            if is_mov_pc(w):
                out.append(struct.pack("<BH", (w >> 12), (w >> 8) & 0xF))
                continue
            out.append(struct.pack("<H", w))
        return out

    na = norm(a_words, base_va)
    nb = norm(b_words, base_va + 0)  # addresses already irrelevant after masking
    return na, nb


def record_digest_map(funcs):
    """va -> digest for every collected function."""
    out = {}
    for va, words, lr, cb, cbase in funcs:
        d, _, _ = fingerprint(words, va, lr, cb, cbase)
        out[va] = d
    return out


def _callee_digest(target, starts, digests, pdata):
    i = bisect.bisect_right(starts, target) - 1
    if i < 0:
        return None
    begin, prolog, length = pdata[i]
    if begin <= target < begin + length:
        return digests.get(begin)
    return None


def call_sequence(words, base_va, code_bytes, lr, pdata_a, digests_a,
                  imports=None, code_bytes_va=None, image_full=None):
    """Ordered digests of resolvable callees of one function.

    Direct ``bsr`` edges use the displacement target. Indirect ``jsr @Rn``
    edges resolve ``Rn`` from the last ``mov.l @(disp,PC),Rn`` before the
    call site (the SH-4 idiom for a far call). A resolved VA inside a pdata
    record yields that record's digest. A resolved VA that is a 3-instruction
    import stub yields ``IMPORT:<dll>:<name|ord>`` from the module's import
    table, so stubs that load different IAT addresses in the two builds still
    compare equal. Edges that resolve to neither are kept as ``"?"``.
    """
    starts = pdata_starts(pdata_a)
    seq = []
    code_base = code_bytes_va if code_bytes_va is not None else base_va
    for i, w in enumerate(words):
        va = base_va + 2 * i
        tgt = None
        if is_bsr(w):
            tgt = branch_target(va, w)
        elif (w & 0xF0FF) == 0x400B:  # jsr @Rn
            rn = (w >> 8) & 0xF
            for j in range(i - 1, -1, -1):
                u = words[j]
                if (u >> 12) == 0xD and ((u >> 8) & 0xF) == rn:
                    lit = pool_addr(base_va + 2 * j, u)
                    off = lit - code_base
                    if 0 <= off + 4 <= len(code_bytes):
                        tgt = struct.unpack_from("<I", code_bytes, off)[0]
                    break
                if is_branch(u) or (u >> 12) in (0xA, 0xB):
                    break  # control-flow boundary: be conservative
        if tgt is None:
            continue
        d = _callee_digest(tgt, starts, digests_a, pdata_a)
        if d is None and imports:
            # maybe an import stub: mov.l @(disp,PC),r0 ; mov.l @r0,r0 ; jmp @r0
            soff = tgt - code_base
            if 0 <= soff + 6 <= len(code_bytes):
                w0, w1, w2 = struct.unpack_from("<HHH", code_bytes, soff)
                if ((w0 >> 12) == 0xD and ((w0 >> 8) & 0xF) == 0
                        and w1 == 0x6002 and w2 == 0x402B):
                    lit = pool_addr(tgt, w0)
                    loff = lit - code_base
                    if 0 <= loff + 4 <= len(code_bytes):
                        slot = struct.unpack_from("<I", code_bytes, loff)[0]
                        d = imports.get(slot, "IMPORT:?%#x" % slot)
        seq.append(d if d else "?")
    return tuple(seq)


def cmd_match(args) -> int:
    pdata_a = load_pdata(args.image_a, args.image_start, args.module,
                         args.index_a, args.pdata_a)
    pdata_b = load_pdata(args.image_b, args.image_start, args.module,
                         args.index_b, args.pdata_b)
    print("# pdata A: %d records  B: %d records" % (len(pdata_a), len(pdata_b)))

    data_a, code_a, off_a, lr_a, rom_a = code_section(args.image_a, args.image_start, args.module)
    data_b, code_b, off_b, lr_b, rom_b = code_section(args.image_b, args.image_start, args.module)
    imports_a = import_index(rom_a, args.module)
    imports_b = import_index(rom_b, args.module)
    print("# imports A: %d  B: %d" % (len(imports_a), len(imports_b)))
    fa = collect_functions(data_a, code_a, off_a, pdata_a, lr_a)
    fb = collect_functions(data_b, code_b, off_b, pdata_b, lr_b)
    print("# A functions: %d  B functions: %d" % (len(fa), len(fb)))

    b_hash: dict[str, list[int]] = {}
    b_words: dict[int, tuple] = {}
    for va, words, lr, cb, cbase in fb:
        d, _, _ = fingerprint(words, va, lr, cb, cbase)
        b_hash.setdefault(d, []).append(va)
        b_words[va] = (words, lr, cb, cbase)
    a_hash: dict[str, list[int]] = {}
    for va, words, lr, cb, cbase in fa:
        d, _, _ = fingerprint(words, va, lr, cb, cbase)
        a_hash.setdefault(d, []).append(va)

    # call-sequence map for propagation: digest per pdata record in each build
    dig_a = record_digest_map(fa)
    dig_b = record_digest_map(fb)
    code_bytes_a = data_a[off_a:off_a + code_a["vsize"]]
    code_bytes_b = data_b[off_b:off_b + code_b["vsize"]]
    word_cache: dict[int, list] = {va: w for va, w, _, _, _ in fa}
    word_cache_b: dict[int, list] = {va: w for va, w, _, _, _ in fb}
    seq_a = {va: call_sequence(w, va, code_bytes_a, lr_a, pdata_a, dig_a,
                               imports_a, code_a["realaddr"])
             for va, w in word_cache.items()}
    seq_b = {va: call_sequence(w, va, code_bytes_b, lr_b, pdata_b, dig_b,
                               imports_b, code_b["realaddr"])
             for va, w in word_cache_b.items()}
    # leaf candidates in B: scan the whole B code section for a window whose
    # masked hash equals the A leaf's hash (leaves have no pdata record in B).
    # Prefiltered by first halfword; identical bytes hash identically, so a
    # match here is exact.
    leaf_cache: dict[str, list] = {}

    def find_leaf_in_b(a_digest, words):
        if a_digest in leaf_cache:
            return leaf_cache[a_digest]
        n = len(words)
        first = words[0]
        base = code_b["realaddr"]
        hits = []
        for off in range(0, code_b["vsize"] - 2 * n, 2):
            if code_bytes_b[off] | (code_bytes_b[off + 1] << 8) != first:
                continue
            w = [code_bytes_b[off + 2 * k] | (code_bytes_b[off + 2 * k + 1] << 8)
                 for k in range(n)]
            d, _, _ = fingerprint(w, base + off, lr_b, code_bytes_b, base)
            if d == a_digest:
                hits.append(base + off)
                if len(hits) > 1:
                    break
        leaf_cache[a_digest] = hits
        return hits

    want = [int(v, 0) for v in args.va]
    results = []
    for va in want:
        kind, rec = locate(pdata_a, va)
        entry = rec[0] if rec else va
        if kind == "GAP":
            words = leaf_words(data_a, code_a, off_a, va)
            if not words:
                print("%#010x  NOMATCH  leaf outside code section" % va)
                results.append((va, None, "NOMATCH", kind))
                continue
            d, bsr, _ = fingerprint(words, va, lr_a, code_bytes_a,
                                    code_a["realaddr"])
            # a leaf may coincide with a B pdata record; hash-match those first
            cand = b_hash.get(d, [])
            if len(cand) == 1:
                verdict, bva = "UNIQUE", cand[0]
            else:
                hits = find_leaf_in_b(d, words)
                if len(hits) == 1:
                    verdict, bva = "UNIQUE", hits[0]
                elif hits:
                    verdict, bva = "AMBIGUOUS", None
                else:
                    verdict, bva = "NOMATCH", None
            print("%#010x  %-9s pdata=%-6s A-leaf %#010x (%d B, %d bsr) -> %s" % (
                va, verdict, kind, va, len(words) * 2, len(bsr),
                "%#010x" % bva if bva is not None else "-"))
            results.append((va, bva, verdict, kind))
            continue
        match = next((f for f in fa if f[0] == entry), None)
        if match is None:
            print("%#010x  NOMATCH  no A pdata record" % va)
            results.append((va, None, "NOMATCH", kind))
            continue
        _, words, lr, cb, cbase = match
        d, bsr, _ = fingerprint(words, entry, lr, cb, cbase)
        cand = b_hash.get(d, [])
        mine = a_hash.get(d, [])
        if len(cand) == 1 and len(mine) == 1:
            verdict, bva = "UNIQUE", cand[0]
        elif cand:
            verdict, bva = "AMBIGUOUS", None
        else:
            # one-hop call-order propagation: find B functions whose callee
            # digest sequence equals the A function's, with every callee known
            a_seq = seq_a.get(entry, ())
            if a_seq and "?" not in a_seq:
                hits = [bv for bv, sb in seq_b.items() if sb == a_seq]
                if len(hits) == 1:
                    verdict, bva = "CALLORDER", hits[0]
                elif hits:
                    verdict, bva = "AMBIGUOUS", None
                else:
                    verdict, bva = "NOMATCH", None
            else:
                verdict, bva = "NOMATCH", None
        print("%#010x  %-9s pdata=%-6s A-fn %#010x (%d B, %d calls) -> %s" % (
            va, verdict, kind, entry, len(words) * 2, len(seq_a.get(entry, ())),
            "%#010x" % bva if bva is not None else "-"))
        results.append((va, bva, verdict, kind))

    if args.json:
        Path(args.json).write_text(json.dumps(
            [{"a": v, "b": b, "verdict": s, "pdata": k} for v, b, s, k in results],
            indent=1))
    uniq = sum(1 for r in results if r[2] == "UNIQUE")
    amb = sum(1 for r in results if r[2] == "AMBIGUOUS")
    nom = sum(1 for r in results if r[2] == "NOMATCH")
    print("# unique: %d  ambiguous: %d  nomatch: %d  of %d" % (uniq, amb, nom, len(results)))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    m = sub.add_parser("match")
    m.add_argument("image_a")
    m.add_argument("image_b")
    m.add_argument("--module", default="Navi.exe")
    m.add_argument("--image-start", type=lambda x: int(x, 0), default=0x200200)
    m.add_argument("--index-a", type=int, default=2,
                   help="pdata section index of the A image (Navi.exe: 2)")
    m.add_argument("--index-b", type=int, default=2)
    m.add_argument("--va", nargs="*", default=[])
    m.add_argument("--pdata-a", default=None, help="JSON cache of A pdata")
    m.add_argument("--pdata-b", default=None, help="JSON cache of B pdata")
    m.add_argument("--json", default=None)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "match":
        return cmd_match(args)
    ap.error("--selftest or a subcommand is required")
    return 2


if __name__ == "__main__":
    sys.exit(main())
