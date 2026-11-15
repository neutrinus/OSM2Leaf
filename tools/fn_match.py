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
  fn_match.py --fixture FILE --us IMG_B [--eu IMG_A] [--module Navi.exe]
      [--json OUT]

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

    def verdict(self, va):
        """(EU va, US va|None, verdict, pdata class) for one EU address."""
        kind, rec = locate(self.pdata_a, va)
        entry = rec[0] if rec else va
        if kind == "GAP":
            words = leaf_words(self.data_a, self.code_a, self.off_a, va)
            if not words:
                print("%#010x  NOMATCH  leaf outside code section" % va)
                return (va, None, "NOMATCH", kind)
            d, bsr, _ = fingerprint(words, va, self.lr_a, self.code_bytes_a,
                                    self.code_a["realaddr"])
            # a leaf may coincide with a B pdata record; hash-match those first
            cand = self.b_hash.get(d, [])
            if len(cand) == 1:
                verdict, bva = "UNIQUE", cand[0]
            else:
                hits = self._find_leaf_in_b(d, words)
                if len(hits) == 1:
                    verdict, bva = "UNIQUE", hits[0]
                elif hits:
                    verdict, bva = "AMBIGUOUS", None
                else:
                    verdict, bva = "NOMATCH", None
            print("%#010x  %-9s pdata=%-6s A-leaf %#010x (%d B, %d bsr) -> %s" % (
                va, verdict, kind, va, len(words) * 2, len(bsr),
                "%#010x" % bva if bva is not None else "-"))
            return (va, bva, verdict, kind)
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
            # one-hop call-order propagation: find B functions whose callee
            # digest sequence equals the A function's, with every callee known
            a_seq = self.seq_a.get(entry, ())
            if a_seq and "?" not in a_seq:
                hits = [bv for bv, sb in self.seq_b.items() if sb == a_seq]
                if len(hits) == 1:
                    verdict, bva = "CALLORDER", hits[0]
                elif hits:
                    verdict, bva = "AMBIGUOUS", None
                else:
                    verdict, bva = "NOMATCH", None
            else:
                verdict, bva = "NOMATCH", None
        print("%#010x  %-9s pdata=%-6s A-fn %#010x (%d B, %d calls) -> %s" % (
            va, verdict, kind, entry, len(words) * 2,
            len(self.seq_a.get(entry, ())),
            "%#010x" % bva if bva is not None else "-"))
        return (va, bva, verdict, kind)


def cmd_match(args) -> int:
    m = Matcher(args.image_a, args.image_b, args.module, args.image_start,
                args.index_a, args.index_b, args.pdata_a, args.pdata_b)
    results = [m.verdict(int(v, 0)) for v in args.va]
    if args.json:
        Path(args.json).write_text(json.dumps(
            [{"a": v, "b": b, "verdict": s, "pdata": k} for v, b, s, k in results],
            indent=1))
    uniq = sum(1 for r in results if r[2] == "UNIQUE")
    amb = sum(1 for r in results if r[2] == "AMBIGUOUS")
    nom = sum(1 for r in results if r[2] == "NOMATCH")
    print("# unique: %d  ambiguous: %d  nomatch: %d  of %d" % (
        uniq, amb, nom, len(results)))
    return 0


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
        if r["expect"] not in ("UNIQUE", "NOMATCH", "AMBIGUOUS", "CALLORDER"):
            raise SystemExit("%s: bad expect %r at %#010x" % (
                path, r["expect"], va))
        if r["expect"] == "UNIQUE" and not r.get("us_va"):
            raise SystemExit("%s: UNIQUE row %#010x has no us_va" % (path, va))
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
    got = {v: (b, s, k) for v, b, s, k in results}
    problems = []
    for va, row in want.items():
        if va not in got:
            problems.append((va, "missing from replay"))
            continue
        bva, verdict, _kind = got[va]
        exp, exp_b = row["expect"], row.get("us_va")
        if verdict != exp:
            problems.append((va, "verdict %s, fixture expects %s%s" % (
                verdict, exp,
                " (%s)" % row["reason"] if row.get("reason") else "")))
        elif exp == "UNIQUE" and bva != int(str(exp_b), 0):
            problems.append((va, "US VA %s, fixture expects %s" % (
                "%#010x" % bva if bva is not None else "-", exp_b)))
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
    results = [m.verdict(int(str(r["eu_va"]), 0)) for r in fixture["rows"]]
    problems, want = compare_rows(fixture, results)
    if args.json:
        Path(args.json).write_text(json.dumps({
            "fixture": str(args.fixture),
            "results": [{"a": v, "b": b, "verdict": s, "pdata": k,
                         "expect": want[v]["expect"]}
                        for v, b, s, k in results],
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
