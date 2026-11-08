#!/usr/bin/env python3
"""SH-4 decoder for the reader work (M1.11), with the endianness pinned.

Decodes the subset the Navi / nk.exe reader analysis needs (mov.b/w/l with
all addressing modes that occur in the prologues and flag tests, add/sub,
cmp, shifts, and/or/tst/xor, bra/bsr/bt/bf (+/s), jsr/jmp/rts, nop, sts/lds
of PR and the push/pop pairs). Anything else prints ``.word 0x....`` and never
raises.

ENDIANNESS: SH-4 code in these images is stored as **little-endian 16-bit
halfwords**. Every halfword and literal-pool word in this module is read
through ``read_u16`` / ``read_u32``, which pin little-endian in one place. A
big-endian reading of the same bytes decodes to nonsense (``e62f`` becomes
``mov #47,r6``), which is the M8.E1 mistake (EXP-2026-11-06-M8.E1b). The
``--selftest`` carries that trap as an explicit case.

Addresses come from the image through ``tools/cerom.py`` (never fitted
deltas). Stdlib only. No external disassembler is needed or used.

Method and the pinned real-image checks: docs/experiments/EXP-2026-11-08-M1.11-sh4dis.md

Usage:
  sh4dis.py IMG MODULE [--image-start X] --va VA [--count N]
  sh4dis.py IMG MODULE [--image-start X] --sweep
  sh4dis.py IMG MODULE [--image-start X] --check-real   (exit 1 mismatch, 2 no image)
  sh4dis.py --hex BYTES [--va VA]                        (LE halfwords, raw bytes)
  sh4dis.py --selftest
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cerom  # noqa: E402

ENDIAN = "little"          # pinned: SH-4 code and pools in these images
ENDIAN_STRUCT = "<"        # struct prefix matching ENDIAN
IMAGE_READ_BYTES = 128 << 20


# --------------------------------------------------------------------------
# The single place where bytes become values
# --------------------------------------------------------------------------

def read_u16(buf, off=0):
    """SH-4 halfword at ``buf[off:off+2]``, little-endian (pinned)."""
    return struct.unpack_from(ENDIAN_STRUCT + "H", buf, off)[0]


def read_u32(buf, off=0):
    """Literal-pool word at ``buf[off:off+4]``, little-endian (pinned)."""
    return struct.unpack_from(ENDIAN_STRUCT + "I", buf, off)[0]


def halfwords_le(blob):
    """Array of little-endian halfwords of ``blob`` (odd trailing byte dropped).

    Shared by scanners that walk many halfwords; the LE convention comes from
    this module's pinned ``ENDIAN_STRUCT``.
    """
    from array import array
    arr = array("H")
    arr.frombytes(blob[: len(blob) // 2 * 2])
    if ENDIAN_STRUCT == "<" and sys.byteorder != "little":
        arr.byteswap()
    elif ENDIAN_STRUCT == ">" and sys.byteorder != "big":
        arr.byteswap()
    return arr


class Mem:
    """Read-only view of VA ranges: list of (base_va, bytes)."""

    def __init__(self, segments):
        self.segs = sorted(segments, key=lambda s: s[0])

    def read(self, va, n):
        for base, b in self.segs:
            if base <= va and va + n <= base + len(b):
                return b[va - base:va - base + n]
        return None

    def u16(self, va):
        b = self.read(va, 2)
        return read_u16(b) if b is not None else None

    def u32(self, va):
        b = self.read(va, 4)
        return read_u32(b) if b is not None else None

    def contains(self, va):
        return self.read(va, 1) is not None


# --------------------------------------------------------------------------
# Decoder
# --------------------------------------------------------------------------

class Insn:
    """One decoded halfword.

    kind: 'call' (bsr/jsr), 'jump' (bra/jmp), 'branch' (bt/bf),
          'ret' (rts/rte), 'load' (PC-relative literal load), 'other', 'word'.
    target: branch target VA, or None.
    lit: literal-pool VA for PC-relative loads, or None.
    delayed: the next halfword is a delay slot.
    """

    __slots__ = ("va", "word", "text", "kind", "target", "lit", "delayed")

    def __init__(self, va, word, text, kind="other", target=None, lit=None, delayed=False):
        self.va = va
        self.word = word
        self.text = text
        self.kind = kind
        self.target = target
        self.lit = lit
        self.delayed = delayed

    def __repr__(self):
        return "Insn(0x%08x %04x %s)" % (self.va, self.word, self.text)


def R(k):
    return "r%d" % k


def s8(x):
    return x - 0x100 if x & 0x80 else x


def s12(x):
    return x - 0x1000 if x & 0x800 else x


def movl_pc_target(addr, w):
    """(reg, literal_va) for ``mov.l @(disp,PC),Rn`` (0xDnnn), else None.

    Literal address is ``((addr + 4) & ~3) + disp * 4``.
    """
    if w is None or w & 0xF000 != 0xD000:
        return None
    reg = (w >> 8) & 15
    lit = ((addr + 4) & ~3) + (w & 0xFF) * 4
    return reg, lit


def jsr_reg(w):
    """Register of ``jsr @Rn`` (0x400B) or ``jmp @Rn`` (0x402B), else None."""
    if w is None:
        return None
    if w & 0xF0FF == 0x400B:
        return ("jsr", (w >> 8) & 15)
    if w & 0xF0FF == 0x402B:
        return ("jmp", (w >> 8) & 15)
    return None


def bsr_target(addr, w):
    """Target of ``bsr disp12`` (0xBnnn), else None."""
    if w is None or w & 0xF000 != 0xB000:
        return None
    return addr + 4 + s12(w & 0xFFF) * 2


def is_rts(w):
    return w == 0x000B


def _alu_text(mn, w):
    return "%s %s,%s" % (mn, R((w >> 4) & 15), R((w >> 8) & 15))


def decode(w, va=0, mem=None):
    """Decode one halfword ``w`` at ``va``. Never raises.

    ``mem`` (optional) is used only to print the value of a literal pool
    slot next to a PC-relative load.
    """
    w &= 0xFFFF
    hi = w >> 12
    n = (w >> 8) & 15
    m = (w >> 4) & 15
    d = w & 15
    i = w & 0xFF

    def ins(text, kind="other", target=None, lit=None, delayed=False):
        return Insn(va, w, text, kind, target, lit, delayed)

    def lit_note(lit, size):
        if mem is None:
            return ""
        v = mem.u32(lit) if size == 4 else mem.u16(lit)
        if v is None:
            return "  ; [0x%08x] unmapped" % lit
        return "  ; [0x%08x]=0x%0*x" % (lit, size * 2, v)

    if hi == 0x0:
        if w == 0x0009:
            return ins("nop")
        if w == 0x000B:
            return ins("rts", "ret", delayed=True)
        if w == 0x002B:
            return ins("rte", "ret", delayed=True)
        if w == 0x0008:
            return ins("clrt")
        if w == 0x0018:
            return ins("sett")
        if w & 0xF0FF == 0x002A:
            return ins("sts pr,%s" % R(n))
        if d == 0x4:
            return ins("mov.b %s,@(r0,%s)" % (R(m), R(n)))
        if d == 0x5:
            return ins("mov.w %s,@(r0,%s)" % (R(m), R(n)))
        if d == 0x6:
            return ins("mov.l %s,@(r0,%s)" % (R(m), R(n)))
        if d == 0x7:
            return ins("mul.l %s,%s" % (R(m), R(n)))
        if d == 0xC:
            return ins("mov.b @(r0,%s),%s" % (R(m), R(n)))
        if d == 0xD:
            return ins("mov.w @(r0,%s),%s" % (R(m), R(n)))
        if d == 0xE:
            return ins("mov.l @(r0,%s),%s" % (R(m), R(n)))
        return ins(".word 0x%04x" % w)

    if hi == 0x1:
        return ins("mov.l %s,@(%d,%s)" % (R(m), d * 4, R(n)))

    if hi == 0x2:
        if d == 0x0:
            return ins("mov.b %s,@%s" % (R(m), R(n)))
        if d == 0x1:
            return ins("mov.w %s,@%s" % (R(m), R(n)))
        if d == 0x2:
            return ins("mov.l %s,@%s" % (R(m), R(n)))
        if d == 0x6:
            return ins("mov.l %s,@-%s" % (R(m), R(n)))
        if d == 0x7:
            return ins(_alu_text("div0s", w))
        if d == 0x8:
            return ins(_alu_text("tst", w))
        if d == 0x9:
            return ins(_alu_text("and", w))
        if d == 0xA:
            return ins(_alu_text("xor", w))
        if d == 0xB:
            return ins(_alu_text("or", w))
        return ins(".word 0x%04x" % w)

    if hi == 0x3:
        mn = {0x0: "cmp/eq", 0x2: "cmp/hs", 0x3: "cmp/ge", 0x6: "cmp/hi",
              0x7: "cmp/gt", 0x8: "sub", 0xA: "subc", 0xB: "subv",
              0xC: "add", 0xE: "addc", 0xF: "addv"}.get(d)
        if mn is None:
            return ins(".word 0x%04x" % w)
        return ins(_alu_text(mn, w))

    if hi == 0x4:
        if i == 0x0B:
            return ins("jsr @%s" % R(n), "call", delayed=True)
        if i == 0x2B:
            return ins("jmp @%s" % R(n), "jump", delayed=True)
        if i == 0x22:
            return ins("sts.l pr,@-%s" % R(n))
        if i == 0x26:
            return ins("lds.l @%s+,pr" % R(n))
        if i == 0x2A:
            return ins("lds %s,pr" % R(n))
        simple = {0x00: "shll", 0x01: "shlr", 0x08: "shll2", 0x09: "shlr2",
                  0x18: "shll8", 0x19: "shlr8", 0x28: "shll16", 0x29: "shlr16",
                  0x10: "dt", 0x11: "cmp/pz", 0x15: "cmp/pl"}
        if i in simple:
            return ins("%s %s" % (simple[i], R(n)))
        return ins(".word 0x%04x" % w)

    if hi == 0x5:
        return ins("mov.l @(%d,%s),%s" % (d * 4, R(m), R(n)))

    if hi == 0x6:
        if d == 0x0:
            return ins("mov.b @%s,%s" % (R(m), R(n)))
        if d == 0x1:
            return ins("mov.w @%s,%s" % (R(m), R(n)))
        if d == 0x2:
            return ins("mov.l @%s,%s" % (R(m), R(n)))
        if d == 0x3:
            return ins("mov %s,%s" % (R(m), R(n)))
        if d == 0x4:
            return ins("mov.b @%s+,%s" % (R(m), R(n)))
        if d == 0x5:
            return ins("mov.w @%s+,%s" % (R(m), R(n)))
        if d == 0x6:
            return ins("mov.l @%s+,%s" % (R(m), R(n)))
        un = {0x7: "not", 0x8: "swap.b", 0x9: "swap.w", 0xB: "neg",
              0xC: "extu.b", 0xD: "extu.w", 0xE: "exts.b", 0xF: "exts.w"}.get(d)
        if un is None:
            return ins(".word 0x%04x" % w)
        return ins("%s %s,%s" % (un, R(m), R(n)))

    if hi == 0x7:
        return ins("add #%d,%s" % (s8(i), R(n)))

    if hi == 0x8:
        if n == 0x0:
            return ins("mov.b r0,@(%d,%s)" % (d, R(m)))
        if n == 0x1:
            return ins("mov.w r0,@(%d,%s)" % (d * 2, R(m)))
        if n == 0x4:
            return ins("mov.b @(%d,%s),r0" % (d, R(m)))
        if n == 0x5:
            return ins("mov.w @(%d,%s),r0" % (d * 2, R(m)))
        if n == 0x8:
            return ins("cmp/eq #%d,r0" % s8(i))
        if n in (0x9, 0xB, 0xD, 0xF):
            tgt = va + 4 + s8(i) * 2
            mn = {0x9: "bt", 0xB: "bf", 0xD: "bt/s", 0xF: "bf/s"}[n]
            return ins("%s 0x%08x" % (mn, tgt), "branch", target=tgt,
                       delayed=n in (0xD, 0xF))
        return ins(".word 0x%04x" % w)

    if hi == 0x9:
        lit = va + 4 + i * 2
        return ins("mov.w @(0x%08x,pc),%s%s" % (lit, R(n), lit_note(lit, 2)),
                   "load", lit=lit)

    if hi == 0xA:
        tgt = va + 4 + s12(w & 0xFFF) * 2
        return ins("bra 0x%08x" % tgt, "jump", target=tgt, delayed=True)

    if hi == 0xB:
        tgt = va + 4 + s12(w & 0xFFF) * 2
        return ins("bsr 0x%08x" % tgt, "call", target=tgt, delayed=True)

    if hi == 0xC:
        imm = {0x8: "tst", 0x9: "and", 0xA: "xor", 0xB: "or"}.get(n)
        if imm is None:
            return ins(".word 0x%04x" % w)
        return ins("%s #0x%02x,r0" % (imm, i))

    if hi == 0xD:
        _r, lit = movl_pc_target(va, w)
        return ins("mov.l @(0x%08x,pc),%s%s" % (lit, R(n), lit_note(lit, 4)),
                   "load", lit=lit)

    if hi == 0xE:
        return ins("mov #%d,%s" % (s8(i), R(n)))

    return ins(".word 0x%04x" % w)


def disasm(mem, start, count):
    """Decode ``count`` halfwords from ``start``; stops at unmapped memory."""
    out = []
    for k in range(count):
        va = start + 2 * k
        w = mem.u16(va)
        if w is None:
            break
        out.append(decode(w, va, mem))
    return out


def fmt(insn):
    return "0x%08x  %04x  %s" % (insn.va, insn.word, insn.text)


# --------------------------------------------------------------------------
# Image binding (cerom only; no dependency on sh4xref)
# --------------------------------------------------------------------------

def load_segments(img_path, image_start, module):
    """(Mem, exec_segs, sections) for the uncompressed sections of MODULE.

    ``exec_segs`` is a list of (base, blob) where blob is the executable
    section's file bytes cut to its virtual size (the loaded code; bytes past
    vsize are file padding). ``sections`` lists dicts for every section,
    compressed ones included, so callers can state coverage.
    """
    with open(img_path, "rb") as fh:
        data = fh.read(IMAGE_READ_BYTES)
    r = cerom.CERom(data, image_start)
    m = r.module(module)
    segs, exec_segs, sections = [], [], []
    for s in r.o32(m):
        executable = bool(s["flags"] & 0x20000000)      # MEM_EXECUTE
        compressed = bool(s["flags"] & cerom.IMAGE_SCN_COMPRESSED)
        sections.append({"va": s["realaddr"], "vsize": s["vsize"],
                         "psize": s["psize"], "exec": executable,
                         "compressed": compressed})
        if compressed:
            continue
        off = r.va2file(s["dataptr"])
        blob = data[off:off + s["psize"]]
        segs.append((s["realaddr"], blob))
        if executable:
            exec_segs.append((s["realaddr"], blob[:s["vsize"]]))
    return Mem(segs), exec_segs, sections


# --------------------------------------------------------------------------
# Pinned real-image checks (EXP-2026-11-08-M1.11, bytes from EXP-2026-11-06-M8.E1b)
# --------------------------------------------------------------------------

NK_MODULE = "nk.exe"
NK_IMAGE_START = 0x3E00200
PROLOGUE_VA = 0x880385E4
FLAG_TEST_VA = 0x88038666

PROLOGUE_TEXT = [
    "mov.l r14,@-r15", "mov.l r8,@-r15", "mov.l r9,@-r15", "mov.l r10,@-r15",
    "mov.l r11,@-r15", "mov.l r12,@-r15", "mov.l r13,@-r15", "sts.l pr,@-r15",
]
FLAG_TEST_TEXT = [
    "mov #32,r2", "mov.l @(20,r8),r3", "shll8 r2", "and r2,r3", "tst r3,r3",
    "bf 0x8803867a",
]
FLAG_TEST_HEX = "20e28553184229233823038b"      # LE bytes at 0x88038666
PROLOGUE_HEX = "e62f862f962fa62fb62fc62fd62f224f"  # LE bytes at 0x880385e4

# (pool VA, expected LE u32 value) from EXP-2026-11-06-M8.E1b
POOLS = [
    (0x88038848, 0x88034D94),   # DECOMP_ALLOC
    (0x8803884C, 0x88037590),   # DECOMP_WRAP
    (0x88037620, 0x88037464),   # DECOMP_SECT (pool in DECOMP_WRAP)
    (0x8803758C, 0x8803A384),   # DECOMP_BLK (pool in DECOMP_SECT)
]

# M1.14: mov.w @(disp,PC),Rn (0x9nnn) pinned on Navi.exe build A. These are
# the C-2129/C-2540 POINT walker (fn 0x003f5194) constant loads; confirming the
# range uses mov.w @(disp,PC) answers C-2489 with a real-image positive control.
NAVI_MODULE = "Navi.exe"
NAVI_IMAGE_START = 0x200200
MOVW_POINT_WALKER = [
    # (va, hex16, mnemonic, lit_va, lit_u16)
    (0x003F51A8, "1494", "mov.w @(0x003f51d4,pc),r4  ; [0x003f51d4]=0x04e8",
     0x003F51D4, 0x04E8),
    (0x003F51AE, "1291", "mov.w @(0x003f51d6,pc),r1  ; [0x003f51d6]=0x03ff",
     0x003F51D6, 0x03FF),
    (0x003F51C2, "0991", "mov.w @(0x003f51d8,pc),r1  ; [0x003f51d8]=0x4e20",
     0x003F51D8, 0x4E20),
]

# M1.8 four call sites (C-710) - oracle agreement targets.
M18_CALL_SITES = [
    # (va, word, text)
    (0x003778B2, 0x430B, "jsr @r3"),
    (0x00377B46, 0x430B, "jsr @r3"),
    (0x003778BC, 0x430B, "jsr @r3"),
    (0x00377B52, 0x430B, "jsr @r3"),
]


def _listing_texts(mem, va, count):
    return [i.text for i in disasm(mem, va, count)]


def _hex_of(mem, va, n):
    b = mem.read(va, n)
    return b.hex() if b is not None else None


def check_real(mem, exec_segs, module=NK_MODULE):
    """Pinned assertions on real bytes. Returns list of failure strings.

    Dispatches by module: nk.exe pins the M1.11 decompressor path (0x88038666
    stays pinned); Navi.exe pins mov.w @(disp,PC) on the C-2129/C-2540 POINT
    walker (M1.14, C-2489). An unmapped address is a failure, never an
    exception.
    """
    fails = []

    def expect(label, got, want):
        ok = got == want
        print("%-52s %s" % (label, "ok" if ok else "FAIL got=%r want=%r" % (got, want)))
        if not ok:
            fails.append(label)

    if module.lower() == NK_MODULE.lower():
        expect("prologue 0x880385e4 bytes (LE)",
               _hex_of(mem, PROLOGUE_VA, 16), PROLOGUE_HEX)
        expect("prologue 0x880385e4 mnemonics (8 halfwords)",
               _listing_texts(mem, PROLOGUE_VA, 8), PROLOGUE_TEXT)
        expect("flag test 0x88038666 bytes (LE)",
               _hex_of(mem, FLAG_TEST_VA, 12), FLAG_TEST_HEX)
        expect("flag test 0x88038666 mnemonics (6 halfwords)",
               _listing_texts(mem, FLAG_TEST_VA, 6), FLAG_TEST_TEXT)
        w = mem.u16(0x88038670)
        bf_target = decode(w, 0x88038670, mem).target if w is not None else None
        expect("bf at 0x88038670 target", bf_target, 0x8803867A)
        for pool, want in POOLS:
            expect("pool 0x%08x holds" % pool, mem.u32(pool), want)
    elif module.lower() == NAVI_MODULE.lower():
        for va, hx, text, lit_va, lit_u16 in MOVW_POINT_WALKER:
            expect("mov.w @(disp,PC) 0x%08x bytes" % va, _hex_of(mem, va, 2), hx)
            w = mem.u16(va)
            ins = decode(w, va, mem) if w is not None else None
            expect("mov.w @(disp,PC) 0x%08x text" % va,
                   ins.text if ins else None, text)
            expect("mov.w @(disp,PC) 0x%08x lit va" % va,
                   ins.lit if ins else None, lit_va)
            v = mem.u16(lit_va)
            expect("mov.w @(disp,PC) 0x%08x lit u16" % va, v, lit_u16)
        # C-2129 range uses mov.w @(disp,PC): all three sites in fn 0x003f5194.
        movw = [i for i in disasm(mem, 0x003F5194, 40)
                if i.kind == "load" and i.text.startswith("mov.w")]
        expect("C-2129 fn 0x003f5194 mov.w @(disp,PC) count", len(movw), 3)
        for va, word, text in M18_CALL_SITES:
            w = mem.u16(va)
            ins = decode(w, va, mem) if w is not None else None
            expect("M1.8 call site 0x%08x" % va,
                   (ins.word, ins.text) if ins else None, (word, text))
    else:
        expect("check-real module has pins", module, "(nk.exe or Navi.exe)")
    return fails


# --------------------------------------------------------------------------
# Independent oracle (M1.14): Capstone or objdump when available, else a
# pinned skip. Disagreement is recorded per instruction and the caller must stop.
# --------------------------------------------------------------------------

ORACLE_SKIP = "SKIP: no independent SH-4 oracle (no capstone, no sh*-objdump)"


def _oracle_capstone():
    try:
        import capstone  # type: ignore
    except Exception:
        return None
    try:
        md = capstone.Cs(capstone.CS_ARCH_SH, capstone.CS_MODE_SH4 | capstone.CS_MODE_LITTLE_ENDIAN)
        md.detail = False
        return ("capstone", md)
    except Exception:
        return None


def _oracle_objdump():
    import shutil
    for name in ("sh4-linux-gnu-objdump", "sh4le-linux-gnu-objdump",
                 "sh4-elf-objdump", "sh-elf-objdump"):
        if shutil.which(name):
            return ("objdump", name)
    return None


def oracle_available():
    return _oracle_capstone() or _oracle_objdump()


def _norm(text):
    """Normalize mnemonics for oracle comparison (spacing/case/hex forms)."""
    t = " ".join(text.lower().replace("\t", " ").split())
    t = t.replace("pc),", "pc), ")
    t = t.replace(",r", ", r").replace("r0,", "r0,").replace("r1,", "r1,")
    t = t.replace("r2,", "r2,").replace("r3,", "r3,").replace("r4,", "r4,")
    t = t.replace("r5,", "r5,").replace("r6,", "r6,").replace("r7,", "r7,")
    t = t.replace("r8,", "r8,").replace("r9,", "r9,")
    return " ".join(t.split())


def oracle_decode_one(oracle, code, va):
    """(ok, text_or_reason) for one halfword using the independent oracle."""
    kind, obj = oracle
    if kind == "capstone":
        try:
            insns = list(obj.disasm(code[:2], va, count=1))
        except Exception as exc:
            return False, "capstone error: %s" % exc
        if not insns:
            return False, "capstone: no decode"
        i = insns[0]
        return True, ("%s %s" % (i.mnemonic, i.op_str)).strip()
    if kind == "objdump":
        import subprocess
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
            tf.write(code[:2] + b"\x00\x00")
            name = tf.name
        try:
            p = subprocess.run(
                [obj, "-D", "-b", "binary", "-m", "sh4", "--adjust-vma=%d" % va, name],
                capture_output=True, text=True, timeout=10)
            for line in p.stdout.splitlines():
                if line.strip().startswith("%x:" % va):
                    # "   3778b2:\t0b 43       \tjsr\t@r3"
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        return True, " ".join(parts[-1].split())
            return False, "objdump: no line for 0x%x: %s" % (va, p.stdout.strip()[-120:])
        except Exception as exc:
            return False, "objdump error: %s" % exc
        finally:
            try:
                os.unlink(name)
            except OSError:
                pass
    return False, "unknown oracle"


def oracle_agrees(oracle, va, word, our_text):
    """Check one instruction. Returns (status, detail). status in ok/skip/fail."""
    code = struct.pack(ENDIAN_STRUCT + "H", word)
    ok, their = oracle_decode_one(oracle, code, va)
    if not ok:
        return "fail", "oracle could not decode 0x%08x %04x: %s" % (va, word, their)
    ours = _norm(our_text.split(";")[0])
    theirs = _norm(their)
    # Accept jsr @rN / jsr @rn forms and minor formatting differences.
    if ours == theirs:
        return "ok", "0x%08x %04x  agree: %s" % (va, word, our_text.split(";")[0].strip())
    # Looser match for register/call forms.
    import re
    o2 = re.sub(r"\s+", " ", ours)
    t2 = re.sub(r"\s+", " ", theirs)
    if o2 == t2:
        return "ok", "0x%08x %04x  agree(normalized): %s | %s" % (va, word, ours, theirs)
    return "fail", ("DISAGREE 0x%08x %04x\n  sh4dis : %s\n  oracle : %s (%s)"
                    % (va, word, our_text, their, oracle[0]))


def run_oracle(mem):
    """Run oracle on the four M1.8 call sites. Returns (status, lines).

    status: 'ok', 'skip', 'fail'. On 'fail' lines record every disagreement.
    """
    oracle = oracle_available()
    lines = []
    if oracle is None:
        lines.append("oracle: %s" % ORACLE_SKIP)
        return "skip", lines
    lines.append("oracle: %s" % oracle[0])
    status = "ok"
    for va, word, text in M18_CALL_SITES:
        w = mem.u16(va)
        ins = decode(w, va, mem) if w is not None else None
        our = ins.text if ins else None
        if w is None or ins is None:
            lines.append("FAIL 0x%08x unmapped in provided image" % va)
            status = "fail"
            continue
        if w != word or our != text:
            lines.append("FAIL 0x%08x sh4dis gave %04x %r, expected pin %04x %r"
                         % (va, w, our, word, text))
            status = "fail"
            continue
        st, detail = oracle_agrees(oracle, va, w, our)
        lines.append(detail)
        if st == "fail":
            status = "fail"
    return status, lines


def sweep(mem, exec_segs, sections):
    """Counts over uncompressed executable sections. Returns invariant failures."""
    words = decoded = unknown = pc_loads = pc_ok = 0
    word_loads = word_loads_ok = 0
    bad = []
    for base, blob in exec_segs:
        for k in range(0, len(blob) - 1, 2):
            va = base + k
            w = read_u16(blob, k)
            ins = decode(w, va, mem)
            words += 1
            if ins.text.startswith(".word"):
                unknown += 1
            else:
                decoded += 1
            if ins.kind == "load":
                if ins.text.startswith("mov.l"):
                    pc_loads += 1
                    inside = mem.contains(ins.lit) and mem.contains(ins.lit + 3)
                    aligned = ins.lit % 4 == 0
                    if inside and aligned:
                        pc_ok += 1
                    else:
                        bad.append("mov.l literal 0x%08x at 0x%08x" % (ins.lit, va))
                else:
                    word_loads += 1
                    if mem.contains(ins.lit) and mem.contains(ins.lit + 1):
                        word_loads_ok += 1
    print("sweep: exec sections %d (%d bytes), halfwords %d"
          % (len(exec_segs), sum(len(b) for _, b in exec_segs), words))
    print("  decoded %d, .word %d (%.1f %%)" % (decoded, unknown,
                                                100.0 * unknown / max(words, 1)))
    print("  mov.l PC loads %d, literal inside section and 4-aligned %d"
          % (pc_loads, pc_ok))
    print("  mov.w PC loads %d, target inside section %d"
          % (word_loads, word_loads_ok))
    print("  uncompressed/compressed sections: %d / %d"
          % (sum(1 for s in sections if not s["compressed"]),
             sum(1 for s in sections if s["compressed"])))
    return bad


# --------------------------------------------------------------------------
# Self-test on synthetic bytes plus the real pinned byte strings
# --------------------------------------------------------------------------

def _hex_mem(base, hexstr):
    return Mem([(base, bytes.fromhex(hexstr))])


def _swap_pairs(b):
    """The BE reading of LE bytes: swap each byte pair (the trap input)."""
    out = bytearray(b)
    out[0::2], out[1::2] = b[1::2], b[0::2]
    return bytes(out)


def selftest():
    fails = []

    def check(label, got, want):
        ok = got == want
        print("%-60s %s" % (label, "ok" if ok else "FAIL got=%r want=%r" % (got, want)))
        if not ok:
            fails.append(label)

    # 1. Real pinned bytes, LE (the EXP-2026-11-06-M8.E1b strings)
    pm = _hex_mem(PROLOGUE_VA, PROLOGUE_HEX)
    check("LE prologue mnemonics", _listing_texts(pm, PROLOGUE_VA, 8), PROLOGUE_TEXT)
    fm = _hex_mem(FLAG_TEST_VA, FLAG_TEST_HEX)
    check("LE flag test mnemonics", _listing_texts(fm, FLAG_TEST_VA, 6), FLAG_TEST_TEXT)
    check("LE bf target 0x8803867a", decode(0x8B03, 0x88038670).target, 0x8803867A)

    # 2. BE trap: the same bytes read big-endian must NOT give the prologue.
    be_mem = Mem([(PROLOGUE_VA, _swap_pairs(bytes.fromhex(PROLOGUE_HEX)))])
    be_first = disasm(be_mem, PROLOGUE_VA, 1)[0].text
    check("BE trap: first halfword reads mov #47,r6", be_first, "mov #47,r6")
    check("BE trap: BE listing differs from prologue",
          _listing_texts(be_mem, PROLOGUE_VA, 8) == PROLOGUE_TEXT, False)
    check("BE trap: pinned check fails loudly on BE bytes",
          len(check_real_quiet(be_mem)) > 0, True)
    check("LE read of the same halfword is 0x2fe6", read_u16(bytes.fromhex("e62f")), 0x2FE6)

    # 3. PC-relative arithmetic (synthetic, positions chosen so each rule matters)
    check("mov.l PC: va 0x1002 disp 2 -> 0x100c (align addr+4)",
          movl_pc_target(0x1002, 0xD002), (0, 0x100C))
    check("mov.l PC: va 0x1000 disp 1 -> 0x1008",
          movl_pc_target(0x1000, 0xD001), (0, 0x1008))
    check("mov.w PC: va 0x1000 disp 1 -> 0x1006 (no alignment)",
          decode(0x9101, 0x1000).lit, 0x1006)
    check("mov.w PC: va 0x1002 disp 0 -> 0x1006 (no alignment)",
          decode(0x9100, 0x1002).lit, 0x1006)
    check("bf negative disp: va 0x10 disp -1 -> 0x12",
          decode(0x8BFF, 0x10).target, 0x12)
    check("bt/s delay flag", decode(0x8DFF, 0x10).delayed, True)
    check("bsr negative: va 0x10044 0xBFFE -> 0x10044",
          bsr_target(0x10044, 0xBFFE), 0x10044)
    check("bra forward: va 0x100 0xA002 -> 0x108", decode(0xA002, 0x100).target, 0x108)
    check("jsr @r3 kind", decode(0x430B, 0).kind, "call")
    check("jsr_reg", jsr_reg(0x430B), ("jsr", 3))
    check("jmp_reg", jsr_reg(0x432B), ("jmp", 3))
    check("rts kind", decode(0x000B, 0).kind, "ret")

    # 4. Literal value printing from a synthetic pool
    # 0xD001 at 0x1000 -> literal ((0x1004)&~3)+4 = 0x1008; LE bytes 78 56 34 12
    syn = Mem([(0x1000, bytes.fromhex("01d0" "0900" "00000000" "78563412"))])
    check("literal load prints pool value",
          decode(0xD001, 0x1000, syn).text,
          "mov.l @(0x00001008,pc),r0  ; [0x00001008]=0x12345678")
    # mov.w @(disp,PC),Rn (0x9nnn): M1.14 pin, real encoding 0x9414 at 0x003f51a8
    # lit = (0x003f51ac & ~3) + 0x14*2 = 0x003f51d4, pool u16 LE e8 04 = 0x04e8
    mw = Mem([(0x003F51A8, bytes.fromhex("1494")),
              (0x003F51D4, bytes.fromhex("e804"))])
    check("mov.w @(disp,PC) 0x9414 pinned mnemonic+lit",
          decode(0x9414, 0x003F51A8, mw).text,
          "mov.w @(0x003f51d4,pc),r4  ; [0x003f51d4]=0x04e8")
    check("mov.w @(disp,PC) kind/lit",
          (decode(0x9414, 0x003F51A8, mw).kind, decode(0x9414, 0x003F51A8, mw).lit),
          ("load", 0x003F51D4))
    check("halfwords_le shared (LE pinned)",
          list(halfwords_le(bytes.fromhex("1494e804"))), [0x9414, 0x04E8])

    # 5. Mnemonic table spot checks, each from a published encoding
    check("mov.l r8,@-r15 (0x2F86)", decode(0x2F86).text, "mov.l r8,@-r15")
    check("sts.l pr,@-r15 (0x4F22)", decode(0x4F22).text, "sts.l pr,@-r15")
    check("mov.l @(20,r8),r3 (0x5385)", decode(0x5385).text, "mov.l @(20,r8),r3")
    check("shll8 r2 (0x4218)", decode(0x4218).text, "shll8 r2")
    check("and r2,r3 (0x2329)", decode(0x2329).text, "and r2,r3")
    check("tst r3,r3 (0x2338)", decode(0x2338).text, "tst r3,r3")
    check("mov #-1,r2 (0xE2FF)", decode(0xE2FF).text, "mov #-1,r2")
    check("add #-2,r15 (0x7FFE)", decode(0x7FFE).text, "add #-2,r15")
    check("cmp/eq r2,r3 (0x3320)", decode(0x3320).text, "cmp/eq r2,r3")
    check("lds.l @r15+,pr (0x4F26)", decode(0x4F26).text, "lds.l @r15+,pr")
    check("mov.b r0,@(3,r1) (0x8013)", decode(0x8013, 0).text,
          "mov.b r0,@(3,r1)")
    # Done-when families not yet covered above (encodings from the SH-4 table)
    check("mov.b r1,@r0 (0x2010)", decode(0x2010).text, "mov.b r1,@r0")
    check("mov.w r1,@r0 (0x2011)", decode(0x2011).text, "mov.w r1,@r0")
    check("mov.b @r1,r0 (0x6010)", decode(0x6010).text, "mov.b @r1,r0")
    check("mov.w @r1,r0 (0x6011)", decode(0x6011).text, "mov.w @r1,r0")
    check("sub r2,r3 (0x3328)", decode(0x3328).text, "sub r2,r3")
    check("add r2,r3 (0x332C)", decode(0x332C).text, "add r2,r3")
    check("or r2,r3 (0x232B)", decode(0x232B).text, "or r2,r3")
    check("jmp @r3 (0x432B)", decode(0x432B).text, "jmp @r3")
    check("bt 0x10 disp 0 (0x8900) target", decode(0x8900, 0x10).target, 0x14)
    check("bsr 0x10 disp 0 (0xB000) target", decode(0xB000, 0x10).target, 0x14)
    check("shll r2 (0x4200)", decode(0x4200).text, "shll r2")
    check("unknown word is .word, no raise", decode(0xF000).text, ".word 0xf000")

    # 6. Oracle (M1.14): pinned skip mode when absent; if present, must agree
    # on the four M1.8 call sites. Disagreement records per instruction.
    m18mem = Mem([])
    # build a mem containing the four sites
    segs = []
    for va, word, _text in M18_CALL_SITES:
        segs.append((va, struct.pack(ENDIAN_STRUCT + "H", word)))
    m18mem = Mem(segs)
    st, lines = run_oracle(m18mem)
    avail = oracle_available()
    if avail is None:
        check("oracle absent -> pinned skip", st, "skip")
        check("oracle skip message", any(ORACLE_SKIP in l for l in lines), True)
    else:
        check("oracle present (%s) agrees on M1.8 sites" % avail[0], st, "ok")
        for l in lines:
            if "DISAGREE" in l or l.startswith("FAIL"):
                check("oracle disagreement detail", l, "(no disagreement)")
    # M1.8 pin constants decode as expected by our own decoder (sanity)
    for va, word, text in M18_CALL_SITES:
        check("M1.8 pin decode 0x%08x" % va, decode(word, va).text, text)

    # 7. Totality: every halfword decodes without an exception
    raised = 0
    for w in range(0x10000):
        try:
            decode(w, 0x8000)
        except Exception:
            raised += 1
    check("all 65536 halfwords decode without raising", raised, 0)

    print("sh4dis selftest: %s" % ("OK" if not fails else "FAILED %d" % len(fails)))
    return 0 if not fails else 1


def check_real_quiet(mem):
    """check_real without printing, for the BE trap."""
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return check_real(mem, [])


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?")
    ap.add_argument("module", nargs="?")
    ap.add_argument("--image-start", type=lambda s: int(s, 0), default=None)
    ap.add_argument("--va", type=lambda s: int(s, 0), default=None)
    ap.add_argument("--count", type=int, default=16)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--check-real", action="store_true",
                    help="pinned real-image checks (nk.exe@0x3e00200 or Navi.exe@0x200200)")
    ap.add_argument("--oracle", action="store_true",
                    help="independent decoder vs four M1.8 call sites; SKIP if absent")
    ap.add_argument("--hex", help="raw bytes as hex, decoded as LE halfwords")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    print("# endian: %s (pinned; SH-4 halfwords and pools in these images)" % ENDIAN)
    if a.hex is not None:
        buf = bytes.fromhex(a.hex)
        mem = Mem([(a.va or 0, buf)])
        for ins in disasm(mem, a.va or 0, len(buf) // 2):
            print(fmt(ins))
        return 0
    if not a.image or not a.module:
        ap.error("IMG MODULE is required (or --hex / --selftest / --oracle with IMG)")
    if not os.path.exists(a.image):
        print("no image at %s" % a.image)
        return 2
    start = a.image_start
    mem, exec_segs, sections = load_segments(a.image, start, a.module)
    if a.oracle:
        st, lines = run_oracle(mem)
        for line in lines:
            print(line)
        if st == "fail":
            print("oracle: FAIL (disagreement recorded; stopped)")
            return 1
        print("oracle: %s" % st.upper())
        return 0
    if a.check_real:
        mod = a.module
        if mod.lower() == NK_MODULE.lower():
            pass
        elif mod.lower() == NAVI_MODULE.lower():
            pass
        else:
            ap.error("--check-real pins nk.exe (0x3e00200) or Navi.exe (0x200200)")
        fails = check_real(mem, exec_segs, module=mod)
        print("check-real(%s): %s" % (mod, "OK" if not fails else "FAILED %d" % len(fails)))
        return 0 if not fails else 1
    if a.sweep:
        bad = sweep(mem, exec_segs, sections)
        print("  invariant violations: %d" % len(bad))
        for line in bad[:20]:
            print("    " + line)
        return 0 if not bad else 1
    if a.va is None:
        ap.error("--va is required for a listing")
    for ins in disasm(mem, a.va, a.count):
        print(fmt(ins))
    return 0


if __name__ == "__main__":
    sys.exit(main())
