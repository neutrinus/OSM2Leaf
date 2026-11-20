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
     not a constant). The pool's address is never hashed. Slots are found in a
     forward pass: a halfword **already named** as a slot is pool data and never
     names another slot, so a pool word that was loaded (already marked) and
     decodes as a load cannot blank a real instruction (H113, H89
     PHANTOM-SLOT). Pool data that no load names is caught by static control
     flow (H118): a slot never lies on a halfword the entry reaches, and in a
     function without a reached ``braf``/``jmp`` an unreached halfword names
     no slot.
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
  fn_match.py --fixture FILE --us IMG_B [--eu IMG_A] [--module Navi.exe]
      [--json OUT]
  fn_match.py bodies IMG_A IMG_B [--fixture-rows FILE] [--pair EU:US ...]
      [--negative EU:US ...] [--window 0x800]

``bodies`` prints the M1.22 relocated-body table (M1.33): for each EU/US pair
the body length (first ``rts`` plus its delay slot, in halfwords) and the first
difference of the two windows after zeroing every pool value a body load
points at.  A pair is "identical masked form stream" when the bodies have the
same length and the first masked difference is past the body.  ``--negative``
pairs must differ inside the body.  Exit 1 when a pair or a negative disagrees.

``--fixture`` replays a committed, vendor-free table of EU VAs and their
expected EU→US verdicts (``tools/fixtures/fn_match_eu_us_2011.json``) against a
supplied US head. It aborts with exit 2 and the actual hash when the US (or EU)
head does not match the fixture's SHA-256, and exits 1 when a row's verdict or
US address differs from the pinned expectation — never a silent ``NOMATCH``.

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
LEAF_CAP = 0x400       # byte cap on a pdata GAP leaf window (M1.27)

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


def is_computed_jump(w: int) -> bool:
    """``braf Rn`` or ``jmp @Rn``: a jump whose target the walk cannot see."""
    return ((w >> 12) == 0x0 and (w & 0xFF) == 0x23) or \
        ((w >> 12) == 0x4 and (w & 0xFF) == 0x2B)


def reachable(words) -> set[int]:
    """Halfword indexes the entry (index 0) reaches by static control flow.

    Fall-through, ``bt``/``bf``(``/s``) both ways, ``bra`` to its target,
    delay slots of every delayed branch; ``rts``/``rte``/``jmp``/``braf`` end
    a path after their delay slot, ``bsr``/``jsr``/``bsrf`` return to the
    next instruction.  Code reached only through a computed jump (a switch
    table) is **not** in the set, so the set under-approximates code; the
    slot pass trusts an unreached halfword to be data only when the function
    has no reached computed jump (H118).  Known blind spots: code reached only
    by an in-function ``bsr`` or by an SEH ``__except`` handler is treated as
    unreached, so in a "closed" function its loads are dropped (no effect on
    the EU2011/US2011 ``Navi.exe`` census, H118 navigator review).
    """
    n = len(words)
    seen: set[int] = set()
    todo = [0] if n else []
    while todo:
        i = todo.pop()
        while 0 <= i < n and i not in seen:
            seen.add(i)
            w = words[i]
            hi = w >> 12
            if w in (0x000B, 0x002B) or is_computed_jump(w):
                if i + 1 < n:                  # rts/rte/braf/jmp: delay slot
                    seen.add(i + 1)
                break
            if hi == 0xA:                      # bra: delay slot, then target
                if i + 1 < n:
                    seen.add(i + 1)
                i = branch_target(2 * i, w) // 2
                continue
            if hi == 0x8 and ((w >> 8) & 0xF) in (0x9, 0xB, 0xD, 0xF):
                todo.append(branch_target(2 * i, w) // 2)
                if ((w >> 8) & 0xF) in (0xD, 0xF) and i + 1 < n:
                    seen.add(i + 1)            # bt/s, bf/s delay slot
                    i += 2
                    continue
            i += 1
    return seen


def _pool_loads(words, base_va: int):
    """``(index, slot_va, size, dest)`` for each real PC-relative load.

    A forward pass: a PC-relative load only reaches forward (its displacement
    is unsigned), so every slot is named before the scan reaches it, and a
    halfword already marked as a slot is pool data and never names another
    slot.  Without the second rule a pool word whose low half decodes as
    ``mov.x @(disp,PC)`` (e.g. ``0xda3c``) names a real instruction, which is
    then blanked and hashed as ``0x0000`` (H89 PHANTOM-SLOT, H113).  Loads
    whose slot sits past ``len(words)`` are real (the trailing pool area).

    Pool data that **no** load names is caught by control flow (H118): a
    slot that lands on a halfword the entry reaches (``reachable``) is not a
    slot, and in a function without a reached ``braf``/``jmp`` (no switch
    table can hide code from the walk) an unreached halfword names nothing.
    A function with a computed jump keeps its unreached loads (case bodies).
    """
    slots: set[int] = set()
    live = reachable(words)
    closed = not any(is_computed_jump(words[k]) for k in live)
    for i, w in enumerate(words):
        if i in slots or not is_mov_pc(w):
            continue
        size = 4 if (w >> 12) == 0xD else 2
        lit = pool_addr(base_va + 2 * i, w)
        j = (lit - base_va) // 2
        # A slot never lies on an instruction the entry reaches: such a
        # "load" is pool data no load names (H118), so it names nothing.
        if any(k in live for k in ((j, j + 1) if size == 4 else (j,))):
            continue
        # In a function with no computed jump every instruction is reached,
        # so an unreached "load" is pool data (e.g. the double 0x9999999a)
        # and must not pull bytes past the function into the hash (H118).
        if closed and i not in live:
            continue
        slots.update((j, j + 1) if size == 4 else (j,))
        yield i, lit, size, (w >> 8) & 0xF


def pool_slots(words, base_va: int) -> set[int]:
    """Halfword indexes (relative to ``base_va``) of literal-pool data.

    Indexes may fall past ``len(words)`` (a slot in the trailing pool area).
    """
    out: set[int] = set()
    for i, lit, size, _dest in _pool_loads(words, base_va):
        j = (lit - base_va) // 2
        out.update((j, j + 1) if size == 4 else (j,))
    return out


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

    # Pass 1: find every literal-pool slot referenced by this function, in a
    # forward pass that never lets pool data name a slot (H113).  Offsets are
    # relative to code_base (image), matching pass 2.
    pool_bytes: set[int] = set()
    pool_meta: dict[int, tuple] = {}
    for _i, lit, size, dest in _pool_loads(words, base_va):
        off2 = lit - code_base
        for k in range(size):
            pool_bytes.add(off2 + k)
        pool_meta[off2] = (lit, size, dest)

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


def leaf_window_limit(va, starts, called, code_end, limit=0x400):
    """Byte bound for a leaf window starting at ``va``.

    A pdata ``GAP`` has no length, so the window must stop at the first of:
    the next pdata ``START`` (``starts`` sorted), the next called leaf entry
    (``called`` sorted; a GAP that is itself a ``bsr``/``jsr`` target), the end
    of the code section (``code_end``), or the hard cap ``limit``.  Without this
    the window of a gap that has no ``rts`` (a thunk stub) runs across the next
    function and pairs unrelated code.
    """
    i = bisect.bisect_right(starts, va)
    nxt = starts[i] if i < len(starts) else code_end
    j = bisect.bisect_right(called, va)
    if j < len(called):
        nxt = min(nxt, called[j])
    nxt = min(nxt, code_end)
    return max(0, min(limit, nxt - va))


def trim_words(words):
    """Cut a leaf window at its ``rts`` (keeping the delay slot).

    A pdata ``GAP`` has no length, so the window is first bounded by
    ``leaf_window_limit`` (next START / next called GAP / code end / cap) and
    then cut at its own ``rts``.  A gap with no ``rts`` (a thunk stub) stays at
    the bound instead of running into the next function.
    """
    for i, w in enumerate(words):
        if w == 0x000B:
            return words[:i + 2] if i + 1 < len(words) else words[:i + 1]
    return words


def _instruction_tokens(words, base_va, image_bytes, code_base):
    """One normalised token per halfword, pool *locations* zeroed.

    This is the instruction half of ``fingerprint`` without pass 3 (pool
    contents).  Two functions with equal tokens have the same code and differ
    at most in the values their literal pools hold; it lets a caller match a
    callee even when a relocated constant inside the callee moved.
    """
    # A forward pass marks pool data only; a pool word that decodes as a
    # PC load does not name another slot (H113).
    pool_offs = set()
    for _i, lit, size, _dest in _pool_loads(words, base_va):
        for k in range(size):
            pool_offs.add(lit - code_base + k)
    pool_bytes = pool_offs

    tokens: list[bytes] = []
    n = len(words)
    span = 2 * n
    for i, w in enumerate(words):
        va = base_va + 2 * i
        off = va - code_base
        if off in pool_bytes:
            tokens.append(b"\x00\x00")
            continue
        if is_branch(w):
            tgt = branch_target(va, w)
            same = base_va <= tgt < base_va + span
            cls = (w >> 12) if (w >> 12) in (0xA, 0xB) else 0x80 | ((w >> 8) & 0xF)
            tokens.append(struct.pack("<BB", cls, 1 if same else 0))
            continue
        if is_mov_pc(w):
            tokens.append(struct.pack("<BH", (w >> 12), (w >> 8) & 0xF))
            continue
        tokens.append(struct.pack("<H", w))
    return tokens


def code_digest(words, base_va, image_bytes, code_base):
    """Digest of the instruction stream only (pool values excluded)."""
    fp = hashlib.sha256()
    for t in _instruction_tokens(words, base_va, image_bytes, code_base):
        fp.update(t)
    return fp.hexdigest()


def _pool_value(words, i, base_va, image_bytes, code_base):
    """Value of the pool word loaded by ``words[i]`` (4 or 2 bytes), or None."""
    w = words[i]
    lit = pool_addr(base_va + 2 * i, w)
    off = lit - code_base
    size = 4 if (w >> 12) == 0xD else 2
    if 0 <= off and off + size <= len(image_bytes):
        if size == 4:
            return struct.unpack_from("<I", image_bytes, off)[0]
        return struct.unpack_from("<H", image_bytes, off)[0]
    return None


def leaf_complete(words):
    """True when the window ends in its own ``rts`` (a whole leaf).

    A gap with no ``rts`` is bounded by ``leaf_window_limit``; the truncated
    window is not a function, so it may only match by exact masked hash and is
    never paired through the caller context (that would pair a thunk stub with
    an unrelated stub-table entry).
    """
    return bool(words) and 0x000B in words


def leaf_truncated(words, natural_bound, cap=LEAF_CAP):
    """True when a cap-limited GAP window is shorter than the gap's natural
    bound and holds no ``rts``.  The window is then a slice of a function (or
    of a data run), so a hash miss is "the cap cannot see it", not "the code
    differs" -- the caller must report ``TRUNCATED``, not ``NOMATCH``."""
    return natural_bound > cap and not leaf_complete(words)


def leaf_call_sites(words, base_va, image_bytes, code_base):
    """[(call_insn_index, callee_va)] for direct and pool-loaded calls.

    A direct ``bsr`` names its callee in the displacement.  A far call loads the
    callee address from the literal pool and executes ``jsr @Rn`` (the SH-4
    idiom); the callee is the pool *value*, which relocates with the build, so
    it is deliberately not masked by the load range.  Sites are deduplicated by
    (index, callee) because one ``jsr`` may be fed by more than one pool load.
    """
    sites = set()
    n = len(words)
    for i, w in enumerate(words):
        if is_bsr(w):
            sites.add((i, branch_target(base_va + 2 * i, w)))
            continue
        if (w >> 12) != 0xD:
            continue
        reg = (w >> 8) & 0xF
        val = _pool_value(words, i, base_va, image_bytes, code_base)
        if val is None:
            continue
        for k in range(1, 13):
            j = i + k
            if j >= n:
                break
            u = words[j]
            if (u & 0xF0FF) == 0x400B and ((u >> 8) & 0xF) == reg:
                sites.add((j, val))
                break
    return sorted(sites)


def leaf_tokens(words, base_va, image_bytes, code_base, load_range,
                iat_slots=frozenset()):
    """Per-instruction tokens with referenced pool *values* merged in.

    Extends ``_instruction_tokens`` so a changed non-address pool constant
    surfaces on the instruction that loads it (the first differing pair).
    A relocated pointer or IAT slot is masked, as in ``fingerprint``.
    """
    lo, hi = load_range
    toks = _instruction_tokens(words, base_va, image_bytes, code_base)
    out = list(toks)
    for i, w in enumerate(words):
        if not is_mov_pc(w):
            continue
        val = _pool_value(words, i, base_va, image_bytes, code_base)
        if val is None or lo <= val < hi or val in iat_slots:
            continue
        if w >> 12 == 0xD:
            out[i] = out[i] + struct.pack("<I", val)
        else:
            out[i] = out[i] + struct.pack("<H", val)
    return out


def leaf_compare(a, va_a, cb_a, base_a, lr_a, b, va_b, cb_b, base_b, lr_b,
                 iat_a=frozenset(), iat_b=frozenset()):
    """First differing ``(index, a_word, a_pool, b_word, b_pool)`` or None.

    ``a``/``b`` are the trimmed instruction words; pool values are reported
    separately so a DIFFERENT verdict names the instruction and the literal.
    """
    def pv(words, i, va, cb, base):
        w = words[i]
        return _pool_value(words, i, va, cb, base) if is_mov_pc(w) else None

    ta = leaf_tokens(a, va_a, cb_a, base_a, lr_a, iat_a)
    tb = leaf_tokens(b, va_b, cb_b, base_b, lr_b, iat_b)
    n = min(len(ta), len(tb))
    for i in range(n):
        if ta[i] != tb[i]:
            return (i, a[i], pv(a, i, va_a, cb_a, base_a),
                    b[i], pv(b, i, va_b, cb_b, base_b))
    if len(ta) != len(tb):
        i = n
        wa = a[i] if i < len(a) else None
        wb = b[i] if i < len(b) else None
        return (i, wa, pv(a, i, va_a, cb_a, base_a) if wa is not None else None,
                wb, pv(b, i, va_b, cb_b, base_b) if wb is not None else None)
    return None


def _pair_text(word, pool):
    if word is None:
        return "-"
    return "%#06x%s" % (word, "" if pool is None else " (pool %#x)" % pool)


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
    ran: list[str] = []

    def check(name, cond):
        ran.append(name)
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

    # ---- leaf path: a synthetic pdata GAP (no record) with its own pool.
    # leaf = mov.w @(pool,pc),r4 ; rts ; mov r6,r0  (pool word at +0x24)
    leaf = [0x9410, 0x000B, 0x6063]
    check("trim_words cuts a leaf at rts and keeps its delay slot",
          trim_words(leaf + [0x1234, 0x5678]) == leaf)

    def make_leaf(pool16):
        buf = bytearray(0x400)
        for k, w in enumerate(leaf):
            struct.pack_into("<H", buf, 2 * k, w)
        struct.pack_into("<H", buf, 0x24, pool16)
        return bytes(buf)

    la = make_leaf(0x04E8)                       # non-address constant
    lb = make_leaf(0x04E8)
    check("leaf: identical bytes compare equal",
          leaf_compare(leaf, 0x1000, la, 0x1000, (0x1000, 0x1400),
                       leaf, 0x3000, lb, 0x3000, (0x3000, 0x3400)) is None)
    lb2 = make_leaf(0x04D8)                      # one constant moved
    pair = leaf_compare(leaf, 0x1000, la, 0x1000, (0x1000, 0x1400),
                        leaf, 0x3000, lb2, 0x3000, (0x3000, 0x3400))
    check("leaf: a moved non-address pool constant is DIFFERENT at its mov",
          pair is not None and pair[0] == 0 and pair[2] == 0x04E8
          and pair[4] == 0x04D8)

    # a no-rts gap must not cross the next pdata START: the clamp bounds the
    # window at min(next START, next called GAP, code end, cap) before trim.
    starts = [0x1000, 0x2000]
    check("leaf_window_limit: next START bounds a no-rts gap",
          leaf_window_limit(0x1400, starts, [], 0x4000, limit=0x4000)
          == 0x2000 - 0x1400)
    check("leaf_window_limit: a called gap entry bounds it first",
          leaf_window_limit(0x1400, starts, [0x1800], 0x4000, limit=0x4000)
          == 0x1800 - 0x1400)
    check("leaf_window_limit: the hard cap wins over a far START",
          leaf_window_limit(0x1000, [0x4000], [], 0x8000) == 0x400)

    no_rts = [0x0009, 0x0009, 0x0009]   # a thunk stub, no rts
    buf = bytearray(0x800)
    for k, w in enumerate(no_rts):
        struct.pack_into("<H", buf, 2 * k, w)
    struct.pack_into("<H", buf, 0x400, 0x000B)   # next START's body
    code = {"realaddr": 0, "vsize": len(buf)}
    bound = leaf_window_limit(0x0000, [0x400], [], len(buf))
    window = trim_words(leaf_words(buf, code, 0, 0x0000, limit=bound))
    check("no-rts gap: window ends at the next START, not the 0x400 cap",
          bound == 0x400 and len(window) * 2 == 0x400)

    # M1.31 cap-truncated leaf: a 0x420-B complete function (rts at +0x41e) is
    # longer than the 0x400 cap, so the capped window cannot reach its rts.  It
    # must be TRUNCATED, never a silent NOMATCH.
    big = bytearray(0x440)
    for k in range(0, 0x41E, 2):
        struct.pack_into("<H", big, k, 0x0009)     # nop body
    struct.pack_into("<H", big, 0x41E, 0x000B)      # rts at +0x41e
    struct.pack_into("<H", big, 0x420, 0x0009)      # its delay slot
    big = bytes(big)
    code_big = {"realaddr": 0, "vsize": len(big)}
    nat = 0x420
    cap_bound = leaf_window_limit(0x0000, [0x2000], [], len(big))
    cap_window = leaf_words(big, code_big, 0, 0x0000, limit=cap_bound)
    check("cap-truncated leaf: the 0x400 cap cannot see the rts at +0x41e",
          cap_bound == 0x400 and not leaf_complete(cap_window)
          and leaf_truncated(cap_window, nat))
    full = leaf_words(big, code_big, 0, 0x0000, limit=nat)
    check("cap-truncated leaf: scanning the natural bound reaches its rts",
          leaf_complete(full) and len(full) * 2 == 0x422)
    check("cap-truncated leaf: a no-rts stub inside the bound is not truncated",
          leaf_truncated([0x0009, 0x0009, 0x0009], 0x400) is False
          and leaf_truncated([0x0009, 0x0009], 0x40) is False)

    # relocated pointer leaf: same code, pool value points into each build's
    # own range; it must compare equal (masked), which the record hash cannot.
    lp_a = make_leaf(0x1200)
    lp_b = make_leaf(0x3200)
    dpa, _, _ = fingerprint(leaf, 0x1000, (0x1000, 0x1400), lp_a, 0x1000)
    dpb, _, _ = fingerprint(leaf, 0x3000, (0x3000, 0x3400), lp_b, 0x3000)
    check("leaf: relocated pool pointer hash-matches (record path would not)",
          dpa == dpb and
          leaf_compare(leaf, 0x1000, lp_a, 0x1000, (0x1000, 0x1400),
                       leaf, 0x3000, lp_b, 0x3000, (0x3000, 0x3400)) is None)

    # call-site context: a caller that differs only in the callee's relocated
    # pool literal still has the same instruction digest and the same site.
    caller = [0xD300, 0x430B, 0x0009]            # mov.l @(0,pc),r3 ; jsr @r3
    def make_caller(lit):
        buf = bytearray(0x400)
        for k, w in enumerate(caller):
            struct.pack_into("<H", buf, 2 * k, w)
        struct.pack_into("<I", buf, 0x04, lit)
        return bytes(buf)
    ca = make_caller(0x2000)
    cb = make_caller(0x3000)
    check("caller: code_digest ignores the relocated callee literal",
          code_digest(caller, 0x1000, ca, 0x1000) ==
          code_digest(caller, 0x3000, cb, 0x3000))
    check("caller: pool literal + jsr yields the call site (index, callee)",
          leaf_call_sites(caller, 0x1000, ca, 0x1000) == [(1, 0x2000)])

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

    # fixture replay: the table comparison is pure, so a synthetic fixture can
    # prove that a pinned row mismatch fails and a clean replay passes.
    fixture = {
        "schema": FIXTURE_SCHEMA,
        "module": "Navi.exe",
        "rows": [
            {"eu_va": "0x1000", "expect": "UNIQUE", "us_va": "0x3000"},
            {"eu_va": "0x2000", "expect": "NOMATCH",
             "reason": "synthetic difference"},
        ],
    }
    good = [(0x1000, 0x3000, "UNIQUE", "START"),
            (0x2000, None, "NOMATCH", "START")]
    bad_kind = [(0x1000, None, "NOMATCH", "START"),
                (0x2000, None, "NOMATCH", "START")]
    bad_addr = [(0x1000, 0x4000, "UNIQUE", "START"),
                (0x2000, None, "NOMATCH", "START")]
    check("fixture: agreeing replay has no problems",
          compare_rows(fixture, good)[0] == [])
    p1, _ = compare_rows(fixture, bad_kind)
    check("fixture: UNIQUE->NOMATCH is a mismatch",
          bool(p1) and "verdict" in p1[0][1])
    p2, _ = compare_rows(fixture, bad_addr)
    check("fixture: a moved US VA is a mismatch",
          bool(p2) and "US VA" in p2[0][1])
    check("fixture: NOMATCH->UNIQUE is a mismatch",
          bool(compare_rows(fixture,
                            [(0x1000, 0x3000, "UNIQUE", "START"),
                             (0x2000, 0x3000, "UNIQUE", "START")])[0]))
    check("fixture: matching module/image_start has no header problem",
          fixture_header_problem(fixture, "Navi.exe", 0x200200) is None)
    check("fixture: a wrong module is a header problem",
          "module" in (fixture_header_problem(fixture, "OSMNav.exe",
                                              0x200200) or ""))
    fx_start = dict(fixture, image_start="0x200200")
    check("fixture: a wrong image_start is a header problem",
          "image_start" in (fixture_header_problem(fx_start, "Navi.exe",
                                                   0x300000) or ""))

    # a wrong head must fail loudly with its hash, not become a NOMATCH
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False) as fh:
        fh.write(b"not an image")
        tmp = fh.name
    try:
        digest = sha256_file(tmp)
        try:
            check_head(tmp, {"sha256": digest}, "US")
            check("check_head: matching hash passes", True)
        except SystemExit:
            check("check_head: matching hash passes", False)
        try:
            check_head(tmp, {"sha256": "0" * 64}, "US")
            check("check_head: wrong hash exits 2", False)
        except SystemExit as exc:
            check("check_head: wrong hash exits 2", exc.code == 2)
        try:
            check_head(tmp, None, "US")
            check("check_head: no pinned hash is a no-op", True)
        except SystemExit:
            check("check_head: no pinned hash is a no-op", False)
    finally:
        Path(tmp).unlink()

    # ---- M1.22b: a NOMATCH whose masked form stream is unique in B is a
    # literal-pool difference, not a rewrite. Build the same function twice
    # with different *non-address* pool constants and prove the verdict.
    # mov.l @(0x14,pc),r7 ; mov.l @(0x10,pc),r8 ; rts ; pad -> pool at +0x14
    # mov.l @(0x14,pc),r7 ; mov.l @(0x10,pc),r8 ; rts ; nop ; then the pool
    body2 = [0xD704, 0xD806, 0x000B, 0x0009, 0x0009, 0x0000,
             0x0000, 0x0000, 0x0000, 0x0000]
    def make_two(pool_a, pool_b):
        buf = bytearray(0x800)
        for i, w in enumerate(body2):
            struct.pack_into("<H", buf, 2 * i, w)
        struct.pack_into("<I", buf, 0x14, pool_a)
        struct.pack_into("<I", buf, 0x18, pool_b)
        return buf
    ca = make_two(0x1111, 0x2222)
    cb = make_two(0x3333, 0x4444)
    words2 = body2 + [0x0000, 0x0000, 0x0000, 0x0000]
    fa = [(0x1000, words2, (0x1000, 0x1800), bytes(ca), 0x1000)]
    fb = [(0x5000, words2, (0x5000, 0x5800), bytes(cb), 0x5000)]
    mM = Matcher.__new__(Matcher)
    mM.fa, mM.fb = fa, fb
    mM.code_bytes_a, mM.code_bytes_b = bytes(ca), bytes(cb)
    mM.code_a = {"realaddr": 0x1000}
    mM.code_b = {"realaddr": 0x5000}
    mM.lr_a, mM.lr_b = (0x1000, 0x1800), (0x5000, 0x5800)
    mM.imports_a, mM.imports_b = {}, {}
    mM.seq_a, mM.seq_b = {}, {}
    mM._fb_by_va = {0x5000: (words2, mM.lr_b, mM.code_b, 0x5000)}
    mM._a_forms = mM._b_forms = None
    got = mM._pool_only_twin(0x1000, words2, bytes(ca), 0x1000)
    check("pool-only twin: equal masked forms + different constants -> explained",
          got is not None and got[0] == 0x5000 and got[1] is not None)
    # a real instruction change must NOT be explained away
    body3 = list(body2)
    body3[0] = 0x0008            # mov #0,r0 instead of nop
    fb_changed = [(0x5000, body3 + words2[len(body2):], mM.lr_b, bytes(cb), 0x5000)]
    mM.fb = fb_changed
    mM._fb_by_va = {0x5000: (fb_changed[0][1], mM.lr_b, mM.code_b, 0x5000)}
    mM._a_forms = mM._b_forms = None
    check("pool-only twin: a changed opcode stays unexplained (NOMATCH)",
          mM._pool_only_twin(0x1000, words2, bytes(ca), 0x1000) is None)

    # (b) two B functions with the same masked form stream are ambiguous: the
    # A function must stay NOMATCH, never be paired with a coin flip.
    mM.fb = [(0x5000, words2, mM.lr_b, bytes(cb), 0x5000),
             (0x6000, words2, (0x6000, 0x6800), bytes(cb), 0x6000)]
    mM._fb_by_va = {va: (w, lr, mM.code_b, cc)
                    for va, w, lr, cc in [(0x5000, words2, mM.lr_b, 0x5000),
                                          (0x6000, words2, (0x6000, 0x6800), 0x6000)]}
    mM._a_forms = mM._b_forms = None
    check("pool-only twin: two identical twins stay NOMATCH (ambiguous)",
          mM._pool_only_twin(0x1000, words2, bytes(ca), 0x1000) is None)

    # (c) a pool-masking cascade: B's first halfword is a load whose slot lands
    # on a different file offset, so the *masked* streams differ. That is not a
    # pool-value difference and must not be explained away.
    body4 = [0x0009] + body2[1:]     # A loads a literal where B has a nop
    cb4 = bytearray(0x800)
    for i, w in enumerate(body4):
        struct.pack_into("<H", cb4, 2 * i, w)
    struct.pack_into("<I", cb4, 0x14, 0x3333)
    struct.pack_into("<I", cb4, 0x18, 0x4444)
    mM.fb = [(0x5000, body4 + words2[len(body4):], mM.lr_b, bytes(cb4), 0x5000)]
    mM._fb_by_va = {0x5000: (mM.fb[0][1], mM.lr_b, mM.code_b, 0x5000)}
    mM._a_forms = mM._b_forms = None
    check("pool-only twin: a shifted masked stream stays unexplained (NOMATCH)",
          mM._pool_only_twin(0x1000, words2, bytes(ca), 0x1000) is None)

    # M1.33: relocated-body table (pool-masked masked-form compare).
    va_x, va_y = 0x2000, 0x7000           # same alignment mod 4
    # body: mov.l @(2,PC),r1 (slot hw 6..7) ; mov.w @(2,PC),r2 (hw 5) ;
    # add r2,r1 ; rts ; nop  | pool: hw 5 = word, hw 6..7 = long
    bodyx = [0xD102, 0x9202, 0x312C, 0x000B, 0x0009, 0x1111, 0x2222, 0x3333]
    bodyy = list(bodyx)
    mx = pool_masked(bodyx, va_x, body_length(bodyx))
    lx = (pool_addr(va_x, 0xD102) - va_x) // 2
    lw = (pool_addr(va_x + 2, 0x9202) - va_x) // 2
    check("bodies: body length = first rts + delay slot", body_length(bodyx) == 5)
    check("bodies: mov.l zeroes two halfwords, mov.w one",
          mx[lx] == 0 and mx[lx + 1] == 0 and mx[lw] == 0 and mx[0] == 0xD102
          and (lx, lw) == (6, 5))
    bodyy[lx] ^= 0x5A5A
    bodyy[lw] ^= 0x00FF
    r1 = body_compare(bodyx, va_x, bodyy, va_y)
    check("bodies: a pool-value move is not an in-body difference",
          not r1["inside"] and r1["first_diff"] is None
          and r1["raw_first_diff"] is not None)
    bodyz = list(bodyx)
    bodyz[2] = 0x313C                     # add -> different opcode in body
    r2 = body_compare(bodyx, va_x, bodyz, va_y)
    check("bodies: an in-body opcode change is inside at halfword 2",
          r2["inside"] and r2["first_diff"] == 2)
    bodyw = [0xD103] + bodyx[1:]          # displacement moved: not masked away
    r3 = body_compare(bodyx, va_x, bodyw, va_y)
    check("bodies: a moved displacement is an in-body difference",
          r3["inside"] and r3["first_diff"] == 0)
    bodyv = [0x0009] + bodyx              # one more insn: body length differs
    r4 = body_compare(bodyx, va_x, bodyv, va_y)
    check("bodies: a body-length change is inside", r4["inside"]
          and (r4["body_a"], r4["body_b"]) == (5, 6))
    check("bodies: no rts in window is never identical",
          body_compare([0x0009] * 4, 0, [0x0009] * 4, 0)["inside"])
    check("bodies: EU:US pair parser", parse_pair("0x10:0x20") == (0x10, 0x20))

    # H113: a pool word that decodes as mov.l @(disp,PC) must not name a slot.
    # hw0 = mov.l @(2,pc),r7 -> slot {6,7}; hw6 = 0xda39 is pool data whose low
    # half decodes as a load that would otherwise blank hw122, a real insn.
    # hw10 = mov.l @(5,pc),r1 -> a real load with slot {22,23}, reached by
    # hw1 = bt -> hw10 (H118: an unreached halfword of a function without a
    # computed jump is data, so the real load must be on a path).  hw11 ends
    # that path: braf r0 (default, keeps the H113 rule isolated) or rts.
    def make_phantom(real_word, end=0x0023, extra=()):
        ws = [0x0009] * 130
        ws[0] = 0xD702
        ws[1] = 0x8907
        ws[2] = 0x000B
        ws[6] = 0xDA39
        ws[10] = 0xD105
        ws[11] = end
        ws[122] = real_word
        for k, w in extra:
            ws[k] = w
        buf = bytearray(2 * len(ws))
        for k, w in enumerate(ws):
            struct.pack_into("<H", buf, 2 * k, w)
        return ws, bytes(buf)

    ws, buf = make_phantom(0xC11E)
    slots = pool_slots(ws, 0x1000)
    check("H113: forward pass marks the real slots and not the phantom one",
          {6, 7, 22, 23} <= slots and 122 not in slots)
    check("H113: the pool word decodes as a load that would name hw122",
          (pool_addr(0x1000 + 2 * 6, ws[6]) - 0x1000) // 2 == 122)
    ws_b, buf_b = make_phantom(0xC11F)
    fp_a, _, _ = fingerprint(ws, 0x1000, (0x1000, 0x1400), buf, 0x1000)
    fp_b, _, _ = fingerprint(ws_b, 0x1000, (0x1000, 0x1400), buf_b, 0x1000)
    check("H113: a real instruction the old pass blanked still changes the hash",
          fp_a != fp_b)
    toks = _instruction_tokens(ws, 0x1000, buf, 0x1000)
    check("H113: the real instruction hashes as itself, not as 0x0000",
          toks[122] == struct.pack("<H", 0xC11E)
          and toks[6] == b"\x00\x00" and toks[22] == b"\x00\x00")
    masked = pool_masked(ws, 0x1000, 20)
    check("H113: pool_masked still zeroes a real load's slot",
          masked[22] == 0 and masked[6] == 0 and masked[122] == 0xC11E
          and masked[0] == 0xD702 and masked[10] == 0xD105)

    # H118: pool data that NO load names.  hw50 = 0xd023 (mov.l @(0x23,pc),r0)
    # is named by no load and would name hw122.  The fixture function has no
    # computed jump (hw11 = rts), so hw50 is unreached data and names nothing.
    check("H118: the walk reaches the bt target and stops at rts",
          reachable(make_phantom(0xC11E, 0x000B)[0]) == {0, 1, 2, 3, 10, 11, 12})
    hw50 = ((50, 0xD023),)
    ws, buf = make_phantom(0xC11E, 0x000B, hw50)
    check("H118: hw50 decodes as a load that would name hw122",
          (pool_addr(0x1000 + 2 * 50, 0xD023) - 0x1000) // 2 == 122)
    slots = pool_slots(ws, 0x1000)
    toks = _instruction_tokens(ws, 0x1000, buf, 0x1000)
    masked = pool_masked(ws, 0x1000, len(ws))
    check("H118: unloaded hw50 does not blank hw122 (slots/tokens/masked)",
          122 not in slots and toks[122] == struct.pack("<H", 0xC11E)
          and masked[122] == 0xC11E)
    check("H118: the loaded pool word and the real load still blank their slots",
          {6, 7, 22, 23} <= slots and toks[6] == b"\x00\x00"
          and masked[6] == 0 and masked[22] == 0)
    ws_o, _ = make_phantom(0xC11E, 0x0023, hw50)
    check("H118 negative: with a reached braf an unreached load is kept "
          "(switch case bodies), so hw50 still names hw122",
          122 in pool_slots(ws_o, 0x1000))
    # Rule A: the slot lands on a reached instruction.  bra at hw1 jumps over a
    # mid-function pool (hw3..59) to hw60; the path runs over hw122 to a braf
    # at hw124, so the function is open and only the reached-target rule works.
    ws = [0x0009] * 130
    for k, w in ((0, 0xD702), (1, 0xA039), (6, 0xDA39), (50, 0xD023),
                 (64, 0xD11E), (122, 0xC11E), (124, 0x0023)):
        ws[k] = w
    live = reachable(ws)
    slots = pool_slots(ws, 0x1000)
    check("H118: a slot on a reached instruction is not a slot (open function)",
          50 not in live and 122 in live and 122 not in slots
          and {6, 7, 126, 127} <= slots)
    # Out-of-function read: the double 0x9999999a after rts decodes as two
    # mov.w loads whose slots lie past the function.  Their "pool value" is
    # another function's bytes and must not enter the hash.
    ws = [0x000B, 0x0009, 0x999A, 0x9999]
    big = bytearray(0x400)
    for k, w in enumerate(ws):
        struct.pack_into("<H", big, 2 * k, w)
    fp1, _, _ = fingerprint(ws, 0x1000, (0x1000, 0x1400), bytes(big), 0x1000)
    big[2 * 158] ^= 0xFF
    fp2, _, _ = fingerprint(ws, 0x1000, (0x1000, 0x1400), bytes(big), 0x1000)
    check("H118: trailing data never pulls bytes past the function into the hash",
          pool_slots(ws, 0x1000) == set() and fp1 == fp2)

    print("fn_match selftest: %s (%d checks, %d failed)"
          % ("OK" if not fails else "FAIL", len(ran), len(fails)))
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


class Matcher:
    """EU build A → US build B function matcher (hash + call order)."""

    def __init__(self, image_a, image_b, module, image_start, index_a, index_b,
                 pdata_a, pdata_b):
        self.pdata_a = load_pdata(image_a, image_start, module, index_a, pdata_a)
        self.pdata_b = load_pdata(image_b, image_start, module, index_b, pdata_b)
        print("# pdata A: %d records  B: %d records" % (
            len(self.pdata_a), len(self.pdata_b)))
        self.data_a, self.code_a, self.off_a, self.lr_a, self.rom_a = \
            code_section(image_a, image_start, module)
        self.data_b, self.code_b, self.off_b, self.lr_b, self.rom_b = \
            code_section(image_b, image_start, module)
        self.imports_a = import_index(self.rom_a, module)
        self.imports_b = import_index(self.rom_b, module)
        print("# imports A: %d  B: %d" % (len(self.imports_a), len(self.imports_b)))
        self.fa = collect_functions(self.data_a, self.code_a, self.off_a,
                                    self.pdata_a, self.lr_a)
        self.fb = collect_functions(self.data_b, self.code_b, self.off_b,
                                    self.pdata_b, self.lr_b)
        print("# A functions: %d  B functions: %d" % (len(self.fa), len(self.fb)))

        self.b_hash: dict[str, list[int]] = {}
        for va, words, lr, cb, cbase in self.fb:
            d, _, _ = fingerprint(words, va, lr, cb, cbase)
            self.b_hash.setdefault(d, []).append(va)
        self.a_hash: dict[str, list[int]] = {}
        for va, words, lr, cb, cbase in self.fa:
            d, _, _ = fingerprint(words, va, lr, cb, cbase)
            self.a_hash.setdefault(d, []).append(va)

        # instruction-stream index (pool values excluded): a NOMATCH whose
        # opcode/register stream equals exactly one B function is a pool-data
        # difference, not a rewrite (M1.22b).
        self.b_cdig: dict[str, list[int]] = {}
        for va, words, lr, cb, cbase in self.fb:
            d = code_digest(words, va, cb, cbase)
            self.b_cdig.setdefault(d, []).append(va)

        # call-sequence map for propagation: digest per pdata record in each build
        dig_a = record_digest_map(self.fa)
        dig_b = record_digest_map(self.fb)
        self.code_bytes_a = self.data_a[self.off_a:self.off_a + self.code_a["vsize"]]
        self.code_bytes_b = self.data_b[self.off_b:self.off_b + self.code_b["vsize"]]
        word_cache = {va: w for va, w, _, _, _ in self.fa}
        word_cache_b = {va: w for va, w, _, _, _ in self.fb}
        self.seq_a = {va: call_sequence(w, va, self.code_bytes_a, self.lr_a,
                                        self.pdata_a, dig_a, self.imports_a,
                                        self.code_a["realaddr"])
                      for va, w in word_cache.items()}
        self.seq_b = {va: call_sequence(w, va, self.code_bytes_b, self.lr_b,
                                        self.pdata_b, dig_b, self.imports_b,
                                        self.code_b["realaddr"])
                      for va, w in word_cache_b.items()}
        # leaf candidates in B: scan the whole B code section for a window whose
        # masked hash equals the A leaf's hash (leaves have no pdata record in
        # B). Prefiltered by first halfword; identical bytes hash identically,
        # so a match here is exact.
        self._leaf_cache: dict[str, list] = {}
        self._fa_by_va = {va: (words, lr, cb, cbase)
                          for va, words, lr, cb, cbase in self.fa}
        self._fb_by_va = {va: (words, lr, cb, cbase)
                          for va, words, lr, cb, cbase in self.fb}
        self._sites_a: dict[int, list[tuple[int, int]]] | None = None
        self._sites_b: dict[int, list[tuple[int, int]]] | None = None
        self._cdig_b: dict[str, list[int]] | None = None
        self._called_a: list[int] | None = None
        self._called_b: list[int] | None = None
        self.force_leaf = False
        self._a_forms: set[str] | None = None
        self._b_forms: dict[str, list[int]] | None = None
        self._starts_a = pdata_starts(self.pdata_a)
        self._starts_b = pdata_starts(self.pdata_b)

    def _find_leaf_in_b(self, a_digest, words):
        if a_digest in self._leaf_cache:
            return self._leaf_cache[a_digest]
        n = len(words)
        first = words[0]
        base = self.code_b["realaddr"]
        cb = self.code_bytes_b
        hits = []
        for off in range(0, self.code_b["vsize"] - 2 * n, 2):
            if cb[off] | (cb[off + 1] << 8) != first:
                continue
            w = [cb[off + 2 * k] | (cb[off + 2 * k + 1] << 8)
                 for k in range(n)]
            d, _, _ = fingerprint(w, base + off, self.lr_b, cb, base)
            if d == a_digest:
                hits.append(base + off)
                if len(hits) > 1:
                    break
        self._leaf_cache[a_digest] = hits
        return hits

    def _caller_sites(self):
        """caller function start -> [(call-insn index, callee VA)], both builds."""
        if self._sites_a is not None and self._sites_b is not None:
            return
        self._sites_a = {}
        for va, words, lr, cb, cbase in self.fa:
            self._sites_a[va] = leaf_call_sites(words, va, cb, cbase)
        self._sites_b = {}
        self._cdig_b = {}
        for va, words, lr, cb, cbase in self.fb:
            self._sites_b[va] = leaf_call_sites(words, va, cb, cbase)
            d = code_digest(words, va, cb, cbase)
            self._cdig_b.setdefault(d, []).append(va)

    def _context_candidates(self, va):
        """US leaf addresses reached at the same call site as EU ``va``.

        Locate every EU caller that calls ``va`` (``bsr`` or pool + ``jsr``),
        match that caller by its instruction stream alone (so the callee's
        relocated pool constant does not block the match), then read the callee
        literal at the same instruction index in the US caller.  Returns a
        sorted list of candidate US leaf VAs.
        """
        self._caller_sites()
        base_b = self.code_b["realaddr"]
        b_lo, b_hi = base_b, base_b + self.code_b["vsize"]
        cands = set()
        for caller_va, sites in self._sites_a.items():
            idxs = {idx for idx, callee in sites if callee == va}
            if not idxs:
                continue
            words, lr, cb, cbase = self._fa_by_va[caller_va]
            d = code_digest(words, caller_va, cb, cbase)
            for b_caller in self._cdig_b.get(d, []):
                b_sites = dict(self._sites_b.get(b_caller, []))
                for idx in idxs:
                    callee = b_sites.get(idx)
                    if callee is not None and b_lo <= callee < b_hi:
                        cands.add(callee)
        return sorted(cands)

    def _called_starts(self, build):
        """Sorted VAs that are direct ``bsr`` targets: leaf entries in a gap."""
        self._caller_sites()
        seen = set()
        sites = self._sites_a if build == "a" else self._sites_b
        for _caller, lst in sites.items():
            for _idx, callee in lst:
                seen.add(callee)
        return sorted(seen)

    def _leaf_natural(self, va, build):
        """Byte bound of the GAP without the ``0x400`` cap (next pdata START /
        called entry / code end).  Used only to tell a cap-truncated leaf from
        a real no-``rts`` stub; the matching window still uses the cap."""
        if build == "a":
            if self._called_a is None:
                self._called_a = self._called_starts("a")
            return leaf_window_limit(
                va, self._starts_a, self._called_a,
                self.code_a["realaddr"] + self.code_a["vsize"], limit=1 << 24)
        if self._called_b is None:
            self._called_b = self._called_starts("b")
        return leaf_window_limit(
            va, self._starts_b, self._called_b,
            self.code_b["realaddr"] + self.code_b["vsize"], limit=1 << 24)

    def _leaf_bound(self, va, build):
        if build == "a":
            if self._called_a is None:
                self._called_a = self._called_starts("a")
            return leaf_window_limit(
                va, self._starts_a, self._called_a,
                self.code_a["realaddr"] + self.code_a["vsize"], limit=LEAF_CAP)
        if self._called_b is None:
            self._called_b = self._called_starts("b")
        return leaf_window_limit(
            va, self._starts_b, self._called_b,
            self.code_b["realaddr"] + self.code_b["vsize"], limit=LEAF_CAP)

    def _leaf_verdict(self, va):
        kind, rec = locate(self.pdata_a, va)
        words = trim_words(leaf_words(
            self.data_a, self.code_a, self.off_a, va,
            limit=self._leaf_bound(va, "a")))
        if not words:
            print("%#010x  LEAF      pdata=GAP    outside the code section" % va)
            return (va, None, "LEAF", "GAP", None)
        natural = self._leaf_natural(va, "a")
        if leaf_truncated(words, natural):
            # no rts inside the cap but the gap runs further: the window is a
            # slice, so a hash miss says nothing about the code.  Never report
            # a false NOMATCH for it (M1.31).
            print("%#010x  TRUNCATED pdata=GAP    leaf %d B (cap %#x, natural "
                  "bound %#x, no rts in cap)" % (va, len(words) * 2, LEAF_CAP,
                                                 natural))
            return (va, None, "TRUNCATED", kind, None)
        d, bsr, _ = fingerprint(words, va, self.lr_a, self.code_bytes_a,
                                self.code_a["realaddr"])
        cand = self.b_hash.get(d, [])
        hits = []
        if len(cand) == 1:
            hits = [cand[0]]
        else:
            hits = self._find_leaf_in_b(d, words)
        verdict = bva = diff = None
        if len(hits) == 1:
            bva, verdict = hits[0], "UNIQUE"
        elif hits:
            verdict = "AMBIGUOUS"
        if verdict is None and not leaf_complete(words):
            # a gap with no rts is bounded, not a whole function: exact hash
            # only, never paired through the caller (no thunk-table pairing).
            verdict = "NOMATCH"
        if verdict is None:
            context = self._context_candidates(va)
            if len(context) == 1:
                bva = context[0]
                b_words = trim_words(leaf_words(
                    self.data_b, self.code_b, self.off_b, bva,
                    limit=self._leaf_bound(bva, "b")))
                pair = leaf_compare(
                    words, va, self.code_bytes_a, self.code_a["realaddr"],
                    self.lr_a, b_words, bva, self.code_bytes_b,
                    self.code_b["realaddr"], self.lr_b,
                    frozenset(self.imports_a), frozenset(self.imports_b))
                if pair is None:
                    verdict = "UNIQUE"
                else:
                    verdict = "DIFFERENT"
                    diff = pair
            elif context:
                verdict, bva = "AMBIGUOUS", None
            else:
                verdict = "NOMATCH"
        if diff is not None:
            i, aw, ap, bw, bp = diff
            print("%#010x  %-9s pdata=GAP    leaf %d B -> %#010x  first diff "
                  "@+%#x: EU %s / US %s" % (
                      va, verdict, len(words) * 2, bva, 2 * i,
                      _pair_text(aw, ap), _pair_text(bw, bp)))
        else:
            print("%#010x  %-9s pdata=GAP    leaf %d B -> %s" % (
                va, verdict, len(words) * 2,
                "%#010x" % bva if bva is not None else "-"))
        return (va, bva, verdict, kind, diff)

    def _propagate(self, entry, words, cb, cbase):
        """One-hop call-order propagation, then the pool-only explanation.

        The call-order step finds a B function whose callee digest sequence
        equals the A function's, with every callee known. It returns
        ``(verdict, bva)``.
        """
        a_seq = self.seq_a.get(entry, ())
        if a_seq and "?" not in a_seq:
            hits = [bv for bv, sb in self.seq_b.items() if sb == a_seq]
            if len(hits) == 1:
                return "CALLORDER", hits[0]
            if hits:
                return "AMBIGUOUS", None
        return "NOMATCH", None

    def _pool_only_twin(self, entry, words, cb, cbase):
        """Explain a NOMATCH as a literal-pool/literal-immediate change.

        The test is on the **masked form stream**: per instruction, the form
        (branch class and in-span bit, load form and destination, otherwise
        the halfword itself) with this build's own literal-pool slots
        blanked. Two functions with equal masked form streams have the same
        opcodes, the same register allocation and the same branch structure;
        only literal-pool values (and the immediate fields of the load forms)
        differ -- a data pointer into a section whose base shifted, a table
        entry, a small constant -- and the build-relative jump targets differ
        in their displacement words, which the form blanking already covers.

        Returns ``(b_va, first_diff, note)`` when exactly one B function has
        that stream; ``None`` for zero or several (the caller keeps NOMATCH).
        ``first_diff`` is the ``leaf_compare`` tuple or None when every pool
        value is equal too.
        """
        if self._a_forms is None:
            self._a_forms = {code_digest(w, va, cb, cc)
                             for va, w, _lr, cb, cc in self.fa}
            self._b_forms = {}
            for va, w, _lr, cb, cc in self.fb:
                self._b_forms.setdefault(code_digest(w, va, cb, cc), []).append(va)
        cdig = code_digest(words, entry, cb, cbase)
        twins = self._b_forms.get(cdig, [])
        if len(twins) != 1:
            return None
        bva = twins[0]
        b_words, _b_lr, _b_cb, _b_cbase = self._fb_by_va[bva]
        diff = leaf_compare(
            words, entry, self.code_bytes_a, self.code_a["realaddr"],
            self.lr_a, b_words, bva, self.code_bytes_b,
            self.code_b["realaddr"], self.lr_b,
            frozenset(self.imports_a), frozenset(self.imports_b))
        if diff is None:
            note = "identical masked form stream and pool values"
        else:
            note = "identical masked form stream; literal/pool values differ"
        return bva, diff, note

    def verdict(self, va):
        """(EU va, US va|None, verdict, pdata class[, diff]) for one EU address."""
        kind, rec = locate(self.pdata_a, va)
        entry = rec[0] if rec else va
        if kind == "GAP" or self.force_leaf:
            return self._leaf_verdict(va)
        match = next((f for f in self.fa if f[0] == entry), None)
        if match is None:
            print("%#010x  NOMATCH  no A pdata record" % va)
            return (va, None, "NOMATCH", kind)
        _, words, lr, cb, cbase = match
        d, bsr, _ = fingerprint(words, entry, lr, cb, cbase)
        cand = self.b_hash.get(d, [])
        mine = self.a_hash.get(d, [])
        if len(cand) == 1 and len(mine) == 1:
            verdict, bva = "UNIQUE", cand[0]
        elif cand:
            verdict, bva = "AMBIGUOUS", None
        else:
            verdict, bva = self._propagate(entry, words, cb, cbase)
        diff = None
        if verdict == "NOMATCH":
            explained = self._pool_only_twin(entry, words, cb, cbase)
            if explained is not None:
                bva, diff, kind_txt = explained
                verdict = "DIFFERENT"
                if diff is not None:
                    i, aw2, ap, bw2, bp = diff
                    print("%#010x  %-9s pdata=%-6s A-fn %#010x (%d B, %d calls)"
                          " -> %#010x  %s; first diff @+%#x: EU %s / US %s"
                          % (va, verdict, kind, entry, len(words) * 2,
                             len(self.seq_a.get(entry, ())), bva, kind_txt,
                             2 * i, _pair_text(aw2, ap),
                             _pair_text(bw2, bp)))
                    return (va, bva, verdict, kind, diff)
        print("%#010x  %-9s pdata=%-6s A-fn %#010x (%d B, %d calls) -> %s" % (
            va, verdict, kind, entry, len(words) * 2,
            len(self.seq_a.get(entry, ())),
            "%#010x" % bva if bva is not None else "-"))
        return (va, bva, verdict, kind)


def cmd_match(args) -> int:
    m = Matcher(args.image_a, args.image_b, args.module, args.image_start,
                args.index_a, args.index_b, args.pdata_a, args.pdata_b)
    if getattr(args, "leaf", False):
        m.force_leaf = True
    results = [m.verdict(int(v, 0)) for v in args.va]
    if args.json:
        Path(args.json).write_text(json.dumps(
            [{"a": v, "b": b, "verdict": s, "pdata": k,
              "diff": None if len(r) < 5 or r[4] is None else {
                  "offset": 2 * r[4][0],
                  "a_word": r[4][1], "a_pool": r[4][2],
                  "b_word": r[4][3], "b_pool": r[4][4]}}
             for r in results for v, b, s, k in [r[:4]]],
            indent=1))
    uniq = sum(1 for r in results if r[2] == "UNIQUE")
    amb = sum(1 for r in results if r[2] == "AMBIGUOUS")
    dif = sum(1 for r in results if r[2] == "DIFFERENT")
    leaf = sum(1 for r in results if r[2] == "LEAF")
    nom = sum(1 for r in results if r[2] == "NOMATCH")
    trunc = sum(1 for r in results if r[2] == "TRUNCATED")
    print("# unique: %d  ambiguous: %d  different: %d  leaf: %d  nomatch: %d  "
          "truncated: %d  of %d" % (uniq, amb, dif, leaf, nom, trunc, len(results)))
    return 0


# ---------------------------------------------------------------- bodies

BODY_WINDOW = 0x800    # bytes read past a body start for the masked compare


def window_words(code_bytes, code_base, va, size=BODY_WINDOW):
    """Little-endian halfwords of ``size`` bytes at ``va`` (clipped)."""
    out = []
    o = va - code_base
    for k in range(0, size, 2):
        if o + k < 0 or o + k + 2 > len(code_bytes):
            break
        out.append(code_bytes[o + k] | (code_bytes[o + k + 1] << 8))
    return out


def body_length(words):
    """Halfwords up to and including the delay slot of the first ``rts``."""
    for i, w in enumerate(words):
        if w == 0x000B:
            return min(i + 2, len(words))
    return None


def pool_masked(words, va, body):
    """Copy of ``words`` with every pool value a body load points at zeroed.

    Only loads inside the first ``body`` halfwords count: ``mov.l
    @(disp,PC)`` zeroes the two halfwords of its 32-bit slot, ``mov.w``
    the one halfword.  The displacement field itself is kept, so a moved
    pool slot is still a difference.
    """
    out = list(words)
    # Forward pass: pool data never names a slot, so a body load whose slot
    # lands on a real instruction cannot blank it (H113).  A load whose slot
    # falls past the body (trailing pool) still counts.
    for i, lit, size, _dest in _pool_loads(words[:body], va):
        j = (lit - va) // 2
        for k in ((j, j + 1) if size == 4 else (j,)):
            if 0 <= k < len(out):
                out[k] = 0
    return out


def body_compare(words_a, va_a, words_b, va_b):
    """Masked-form comparison of two bodies (M1.22 relocated-body table).

    Returns ``dict(body_a, body_b, first_diff, inside, raw_first_diff,
    raw_pair)``: body lengths in halfwords (first ``rts`` + delay slot),
    the first differing halfword index of the pool-masked windows (``None``
    when the windows agree), ``inside`` = True when the bodies differ in
    length or the first masked difference falls inside the body, and the
    first raw (unmasked) difference with its two halfwords.
    """
    ba, bb = body_length(words_a), body_length(words_b)
    if ba is None or bb is None:
        return dict(body_a=ba, body_b=bb, first_diff=None, inside=True,
                    raw_first_diff=None, raw_pair=None)
    ma, mb = pool_masked(words_a, va_a, ba), pool_masked(words_b, va_b, bb)
    n = min(len(ma), len(mb))
    first = next((i for i in range(n) if ma[i] != mb[i]), None)
    raw = next((i for i in range(n) if words_a[i] != words_b[i]), None)
    inside = ba != bb or (first is not None and first < ba)
    return dict(body_a=ba, body_b=bb, first_diff=first, inside=inside,
                raw_first_diff=raw,
                raw_pair=None if raw is None else (words_a[raw], words_b[raw]))


def parse_pair(text):
    a, sep, b = text.partition(":")
    if not sep:
        raise argparse.ArgumentTypeError("expected EU_VA:US_VA, got %r" % text)
    return int(a, 0), int(b, 0)


def body_rows_from_fixture(path):
    """(label, eu_va, us_va) for every fixture row that names a US address."""
    doc = load_fixture(path)
    rows = []
    for r in doc["rows"]:
        us = r.get("us_va") or r.get("us_candidate")
        if us:
            rows.append((r.get("role", "").split(" (")[0],
                         int(str(r["eu_va"]), 0), int(str(us), 0)))
    return rows


def format_body_row(label, va_a, va_b, res):
    if res["body_a"] is None or res["body_b"] is None:
        return "%-22s %#010x -> %#010x  no rts in window" % (label, va_a, va_b)
    if res["inside"]:
        where = "halfword %d @+%#x" % (res["first_diff"], 2 * res["first_diff"]) \
            if res["first_diff"] is not None else "body length"
        txt = "first masked diff: %s" % where
        if res["raw_pair"]:
            txt += " (raw first diff halfword %d @+%#x: %#06x vs %#06x)" % (
                res["raw_first_diff"], 2 * res["raw_first_diff"],
                res["raw_pair"][0], res["raw_pair"][1])
    else:
        txt = "first masked diff: NONE (next diff %s)" % (
            "halfword %d, past the body" % res["first_diff"]
            if res["first_diff"] is not None else "none in window")
    return "%-22s %#010x -> %#010x  body EU=%-3d US=%-3d %s" % (
        label, va_a, va_b, res["body_a"], res["body_b"], txt)


def cmd_bodies(args) -> int:
    rows = []
    if args.fixture_rows:
        rows.extend(body_rows_from_fixture(args.fixture_rows))
    rows.extend(("pair", a, b) for a, b in args.pair or [])
    negs = [("NEGATIVE", a, b) for a, b in args.negative or []]
    if not rows and not negs:
        raise SystemExit("bodies: give --fixture-rows FILE, --pair or --negative")
    data_a, code_a, off_a, _lr, _rom = code_section(args.image_a, args.image_start, args.module)
    data_b, code_b, off_b, _lr, _rom = code_section(args.image_b, args.image_start, args.module)
    cb_a = data_a[off_a:off_a + code_a["vsize"]]
    cb_b = data_b[off_b:off_b + code_b["vsize"]]
    bad = 0
    same = 0
    print("# %s A=%s B=%s window=%#x B; pool values a body load points at are "
          "zeroed; body = first rts + delay slot" % (
              args.module, Path(args.image_a).name, Path(args.image_b).name,
              args.window))
    for label, va_a, va_b in rows + negs:
        wa = window_words(cb_a, code_a["realaddr"], va_a, args.window)
        wb = window_words(cb_b, code_b["realaddr"], va_b, args.window)
        res = body_compare(wa, va_a, wb, va_b)
        print(format_body_row(label, va_a, va_b, res))
        if label == "NEGATIVE":
            if not res["inside"]:
                print("  FAIL negative control has an identical masked body")
                bad += 1
        elif res["inside"]:
            bad += 1
        else:
            same += 1
    print("summary: %d/%d identical masked form stream; negatives %d; problems %d"
          % (same, len(rows), len(negs), bad))
    return 1 if bad else 0


# ---------------------------------------------------------------- fixture

FIXTURE_SCHEMA = "osm2leaf.fn_match.fixture/v1"


def sha256_file(path, limit=None):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        remaining = limit
        while True:
            n = 1 << 20 if remaining is None else min(1 << 20, remaining)
            if n <= 0:
                break
            chunk = fh.read(n)
            if not chunk:
                break
            h.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
    return h.hexdigest()


def load_fixture(path):
    doc = json.loads(Path(path).read_text())
    if doc.get("schema") != FIXTURE_SCHEMA:
        raise SystemExit("%s: schema is %r, expected %r" % (
            path, doc.get("schema"), FIXTURE_SCHEMA))
    rows = doc.get("rows") or []
    if not rows:
        raise SystemExit("%s: fixture has no rows" % path)
    seen = set()
    for r in rows:
        va = int(str(r["eu_va"]), 0)
        if va in seen:
            raise SystemExit("%s: duplicate EU VA %#010x" % (path, va))
        seen.add(va)
        if r["expect"] not in ("UNIQUE", "NOMATCH", "AMBIGUOUS", "CALLORDER",
                               "DIFFERENT", "LEAF"):
            raise SystemExit("%s: bad expect %r at %#010x" % (
                path, r["expect"], va))
        if r["expect"] == "UNIQUE" and not r.get("us_va"):
            raise SystemExit("%s: UNIQUE row %#010x has no us_va" % (path, va))
        if r["expect"] == "DIFFERENT" and not r.get("us_candidate"):
            raise SystemExit("%s: DIFFERENT row %#010x has no us_candidate"
                             % (path, va))
    return doc


def check_head(path, want, label):
    """Fail loudly (exit 2) on a wrong head; never a NOMATCH.

    When the fixture pins ``bytes``, only that prefix is hashed, so a full card
    image works as well as a truncated head; a shorter file fails with its size.
    """
    if not want:
        return
    want_bytes = want.get("bytes")
    size = Path(path).stat().st_size
    if want_bytes is not None:
        if size < want_bytes:
            print("FAIL %s is %d bytes, fixture needs at least %d"
                  % (label, size, want_bytes))
            raise SystemExit(2)
        got = sha256_file(path, want_bytes)
    else:
        got = sha256_file(path)
    if got != want["sha256"]:
        print("FAIL %s SHA-256 %s, fixture expects %s" % (
            label, got, want["sha256"]))
        raise SystemExit(2)


def compare_rows(fixture, results):
    """Return a list of (level, message); empty means the replay agrees."""
    want = {int(str(r["eu_va"]), 0): r for r in fixture["rows"]}
    got = {r[0]: r[:4] for r in results}
    diffs = {r[0]: (r[4] if len(r) > 4 else None) for r in results}
    problems = []
    for va, row in want.items():
        if va not in got:
            problems.append((va, "missing from replay"))
            continue
        bva, verdict, _kind = got[va][1:]
        exp, exp_b = row["expect"], row.get("us_va")
        if verdict != exp:
            problems.append((va, "verdict %s, fixture expects %s%s" % (
                verdict, exp,
                " (%s)" % row["reason"] if row.get("reason") else "")))
        elif exp == "UNIQUE" and bva != int(str(exp_b), 0):
            problems.append((va, "US VA %s, fixture expects %s" % (
                "%#010x" % bva if bva is not None else "-", exp_b)))
        elif exp == "DIFFERENT" and row.get("us_candidate"):
            want_b = int(str(row["us_candidate"]), 0)
            if bva != want_b:
                problems.append((va, "US candidate %s, fixture expects %s" % (
                    "%#010x" % bva if bva is not None else "-",
                    row["us_candidate"])))
            elif row.get("diff_offset") is not None:
                pair = diffs.get(va)
                if pair is None or 2 * pair[0] != int(str(row["diff_offset"]), 0):
                    problems.append((va, "first diff offset %s, fixture expects %s"
                                     % ("-" if pair is None else "%#x" % (2 * pair[0]),
                                        row["diff_offset"])))
    for va in got:
        if va not in want:
            problems.append((va, "replayed but not in fixture"))
    return problems, want


def fixture_header_problem(fixture, module, image_start):
    """Message for a module/image-start disagreement, or None."""
    want_module = fixture.get("module")
    if want_module and want_module != module:
        return ("fixture module %r, CLI --module %r; the table's VAs are for "
                "%s only" % (want_module, module, want_module))
    if fixture.get("image_start"):
        want_start = int(str(fixture["image_start"]), 0)
        if want_start != image_start:
            return "fixture image_start %#x, CLI --image-start %#x" % (
                want_start, image_start)
    return None


def cmd_fixture(args) -> int:
    fixture = load_fixture(args.fixture)
    problem = fixture_header_problem(fixture, args.module, args.image_start)
    if problem:
        print("FAIL %s" % problem)
        raise SystemExit(2)
    us = args.us or getattr(args, "image_b", None)
    eu = args.eu or getattr(args, "image_a", None)
    if not us:
        raise SystemExit("--us IMG is required with --fixture")
    if not eu:
        eu = "archive/head256.img"
        if not Path(eu).is_file():
            raise SystemExit("--eu IMG is required: archive/head256.img absent")
    check_head(us, fixture.get("us_head"), "US")
    check_head(eu, fixture.get("eu_head"), "EU")
    print("# fixture %s: %d rows (EU %s, US %s)" % (
        args.fixture, len(fixture["rows"]), Path(eu).name, Path(us).name))
    m = Matcher(eu, us, args.module, args.image_start, args.index_a,
                args.index_b, args.pdata_a, args.pdata_b)
    if getattr(args, "leaf", False):
        m.force_leaf = True
    results = [m.verdict(int(str(r["eu_va"]), 0)) for r in fixture["rows"]]
    problems, want = compare_rows(fixture, results)
    if args.json:
        Path(args.json).write_text(json.dumps({
            "fixture": str(args.fixture),
            "results": [{"a": r[0], "b": r[1], "verdict": r[2], "pdata": r[3],
                         "expect": want[r[0]]["expect"]}
                        for r in results],
            "ok": not problems,
        }, indent=1))
    for va, msg in sorted(problems):
        print("%#010x  MISMATCH  %s" % (va, msg))
    print("# fixture replay: %d rows, %d mismatch" % (len(results), len(problems)))
    return 0 if not problems else 1



def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--fixture", default=None,
                    help="replay a committed EU->US fixture table (see below)")
    ap.add_argument("--us", default=None, help="US head for --fixture")
    ap.add_argument("--eu", default=None,
                    help="EU head for --fixture (default archive/head256.img)")
    ap.add_argument("--module", default="Navi.exe")
    ap.add_argument("--image-start", type=lambda x: int(x, 0), default=0x200200)
    ap.add_argument("--index-a", type=int, default=2,
                    help="pdata section index of the A image (Navi.exe: 2)")
    ap.add_argument("--index-b", type=int, default=2)
    ap.add_argument("--pdata-a", default=None, help="JSON cache of A pdata")
    ap.add_argument("--pdata-b", default=None, help="JSON cache of B pdata")
    ap.add_argument("--json", default=None)
    ap.add_argument("--leaf", action="store_true",
                    help="force the leaf path (every VA is hashed as a leaf)")
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
    m.add_argument("--leaf", action="store_true",
                   help="force the leaf path for every --va (GAP targets use "
                        "it by default)")
    bo = sub.add_parser("bodies",
                        help="pool-masked relocated-body table (M1.22/M1.33)")
    bo.add_argument("image_a")
    bo.add_argument("image_b")
    bo.add_argument("--module", default="Navi.exe")
    bo.add_argument("--image-start", type=lambda x: int(x, 0), default=0x200200)
    bo.add_argument("--fixture-rows", metavar="FILE",
                    help="take every fixture row with a us_va/us_candidate")
    bo.add_argument("--pair", type=parse_pair, action="append",
                    metavar="EU:US", help="an extra pair expected identical")
    bo.add_argument("--negative", type=parse_pair, action="append",
                    metavar="EU:US", help="a pair expected to differ in-body")
    bo.add_argument("--window", type=lambda x: int(x, 0), default=BODY_WINDOW)
    args = ap.parse_args(argv)
    if args.cmd == "bodies":
        return cmd_bodies(args)
    if args.selftest:
        return selftest()
    if args.fixture:
        # fixture mode ignores the subcommand's positional images; --fixture
        # is a top-level replay so the task's done-when command is short.
        if args.cmd == "match" and getattr(args, "image_a", None):
            if not args.us:
                args.us = args.image_b
            if not args.eu:
                args.eu = args.image_a
        return cmd_fixture(args)
    if args.cmd == "match":
        return cmd_match(args)
    ap.error("--selftest, --fixture or a subcommand is required")
    return 2


if __name__ == "__main__":
    sys.exit(main())
