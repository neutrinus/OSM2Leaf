#!/usr/bin/env python3
"""SH-4 xref helper for Windows CE modules (M1.8).

Answers two questions the M2/M3 tasks ask over and over:

  --to VA        which code loads VA? A VA used as a code literal (for example a
                 string pointer such as 0x004e7d28, or a thunk address such as
                 0x003d1bb0) is found in the literal pools of the executable
                 sections, then every ``mov.l @(disp,PC),Rn`` that loads it is
                 listed with the ``jsr/jmp @Rn`` that follows and the enclosing
                 function start (prologue heuristic).

  --calls FUNC   what does FUNC call? Lists ``bsr`` targets and register calls
                 (``mov.l`` literal then ``jsr @Rn``), each labelled through the
                 module's import thunks (``IMPORT dll!name``), its exports
                 (``EXPORT name``) or ``sub_<va>``.

Stdlib only. Uses ``tools/cerom.py`` for the section table, the OFT import
names and the export names, so every address is derived from the image headers.
Only uncompressed sections are read (code is never compressed, C-530).

Method and the EXP-50 reproduction: docs/experiments/EXP-2026-11-05-M1.8-sh4xref.md

Usage:
  sh4xref.py IMG MODULE [--image-start X] --to VA
  sh4xref.py IMG MODULE [--image-start X] --calls FUNC_VA
  sh4xref.py --selftest
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cerom  # noqa: E402

MAX_BACK = 0x2000        # prologue search window
CALL_WINDOW = 12         # instructions after a literal load searched for jsr/jmp
FUNC_LIMIT = 0x4000      # bytes scanned by --calls when no rts is seen


# --------------------------------------------------------------------------
# Memory and decoding helpers
# --------------------------------------------------------------------------

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
        return struct.unpack("<H", b)[0] if b is not None else None

    def u32(self, va):
        b = self.read(va, 4)
        return struct.unpack("<I", b)[0] if b is not None else None

    def contains(self, va):
        return self.read(va, 1) is not None


def movl_pc_target(addr, w):
    """(reg, literal_va) for ``mov.l @(disp,PC),Rn`` (0xDnnn), else None."""
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
    disp = w & 0xFFF
    if disp & 0x800:
        disp -= 0x1000
    return addr + 4 + disp * 2


def is_rts(w):
    return w == 0x000B


def is_prologue_word(w):
    """``sts.l PR,@-R15`` (0x4F22), ``mov.l Rm,@-R15`` (0x2F?6) or
    ``add #imm,R15`` (0x7F??, frame setup)."""
    if w is None:
        return False
    return w == 0x4F22 or w & 0xFF0F == 0x2F06 or w & 0xFF00 == 0x7F00


def function_start(mem, addr):
    """Start of the function containing ``addr`` (prologue heuristic).

    The nearest ``rts`` before ``addr`` ends the previous function; the next
    function begins after its delay slot. Literal pools may sit in that gap,
    so the start is the first prologue word (``sts.l PR,@-R15``,
    ``mov.l Rm,@-R15`` or ``add #imm,R15``) within 64 bytes of the gap, else
    the first word after the delay slot. Returns None if no ``rts`` is found
    within MAX_BACK bytes.
    """
    a = addr & ~1
    limit = a - MAX_BACK
    r = a - 2
    while r >= limit and mem.u16(r) != 0x000B:
        r -= 2
    if r < limit:
        return None
    s = r + 4                              # after rts and its delay slot
    for k in range(0, 64, 2):
        if s + k > a:
            break
        if is_prologue_word(mem.u16(s + k)):
            return s + k
    return s if s <= a else None


def thunk_slot(mem, va):
    """If ``va`` is an import stub (mov.l @(pc),R0; mov.l @R0,R0; jmp @R0; nop),
    return the IAT slot VA it jumps through, else None."""
    w = mem.u16(va)
    if w is None or w & 0xFF00 != 0xD000 or (w >> 8) & 15 != 0:
        return None
    if mem.u16(va + 2) != 0x6002 or mem.u16(va + 4) != 0x402B or mem.u16(va + 6) != 0x0009:
        return None
    _, lit = movl_pc_target(va, w)
    return mem.u32(lit)


class Labeller:
    def __init__(self, mem, imports, exports):
        self.mem = mem
        self.imports = imports      # slot VA -> "dll!name"
        self.exports = exports      # VA -> name

    def __call__(self, va):
        slot = thunk_slot(self.mem, va)
        if slot is not None:
            return "IMPORT %s" % self.imports.get(slot, "slot_%08x" % slot)
        if va in self.exports:
            return "EXPORT %s" % self.exports[va]
        return "sub_%08x" % va


# --------------------------------------------------------------------------
# Queries
# --------------------------------------------------------------------------

def pool_entries(mem, exec_segs, value):
    """Addresses of 4-byte literal words equal to ``value`` in the given segments."""
    needle = struct.pack("<I", value)
    out = []
    for base, b in exec_segs:
        i = b.find(needle)
        while i >= 0:
            if (base + i) % 4 == 0:
                out.append(base + i)
            i = b.find(needle, i + 1)
    return out


def loads_of(mem, pool_va):
    """(load_va, reg) for each ``mov.l @(disp,PC),Rn`` that reads ``pool_va``."""
    out = []
    for a in range(max(0, pool_va - 1024 - 4), pool_va, 2):
        t = movl_pc_target(a, mem.u16(a))
        if t and t[1] == pool_va:
            out.append((a, t[0]))
    return out


def call_after(mem, load_va, reg):
    """First ``jsr/jmp @reg`` within CALL_WINDOW instructions after a load."""
    for k in range(1, CALL_WINDOW + 1):
        a = load_va + 2 * k
        j = jsr_reg(mem.u16(a))
        if j and j[1] == reg:
            return a, j[0]
    return None


def _load_line(mem, load, reg):
    fn = function_start(mem, load)
    call = call_after(mem, load, reg)
    s = "  load 0x%08x (r%d)" % (load, reg)
    s += "  fn 0x%08x" % fn if fn is not None else "  fn ?"
    if call:
        s += "  %s 0x%08x" % (call[1], call[0])
    return s


def query_to(mem, exec_segs, value, label):
    """Two readings of ``value``:
      * the code reads the pool slot AT ``value`` (mov.l @(disp,PC) with
        literal address == value), e.g. the HDD_INFO slot 0x004e7d28;
      * ``value`` is the word held in a pool slot (e.g. a thunk VA).
    """
    lines = []
    slot_loads = loads_of(mem, value)
    if slot_loads:
        lines.append("slot 0x%08x is read by:" % value)
        lines += [_load_line(mem, a, r) for a, r in slot_loads]
    for pool in pool_entries(mem, exec_segs, value):
        lines.append("pool 0x%08x holds 0x%08x" % (pool, value))
        lines += [_load_line(mem, a, r) for a, r in loads_of(mem, pool)]
    if not lines:
        lines.append("no literal pool holds 0x%08x in executable sections" % value)
    return lines


def query_calls(mem, func, label):
    lines = []
    reg_val = {}
    for k in range(0, FUNC_LIMIT, 2):
        a = func + k
        w = mem.u16(a)
        if w is None:
            break
        if k and is_rts(w):
            lines.append("  0x%08x rts" % a)
            break
        t = bsr_target(a, w)
        if t is not None:
            lines.append("  0x%08x bsr 0x%08x  %s" % (a, t, label(t)))
            continue
        ld = movl_pc_target(a, w)
        if ld:
            v = mem.u32(ld[1])
            reg_val[ld[0]] = v
            continue
        j = jsr_reg(w)
        if j and j[0] == "jsr" and j[1] in reg_val and reg_val[j[1]] is not None:
            tgt = reg_val[j[1]]
            lines.append("  0x%08x jsr @r%d -> 0x%08x  %s" % (a, j[1], tgt, label(tgt)))
    return lines


# --------------------------------------------------------------------------
# Image binding
# --------------------------------------------------------------------------

def load_module(img_path, image_start, module):
    with open(img_path, "rb") as fh:
        data = fh.read(128 << 20)
    r = cerom.CERom(data, image_start)
    m = r.module(module)
    segs, exec_segs = [], []
    for s in r.o32(m):
        if s["flags"] & cerom.IMAGE_SCN_COMPRESSED:
            continue
        off = r.va2file(s["dataptr"])
        blob = data[off:off + s["psize"]]
        segs.append((s["realaddr"], blob))
        if s["flags"] & 0x20000000:  # MEM_EXECUTE
            exec_segs.append((s["realaddr"], blob))
    mem = Mem(segs)
    imports = {}
    for dll, slot, nm, ordn in r.imports(m):
        imports[slot] = "%s!%s" % (dll, nm if nm is not None else "#%d" % ordn)
    exports = {}
    try:
        for ordinal, name, rva in r.exports(m):
            exports[e32_vbase(r, m) + rva] = name
    except Exception:
        pass
    return mem, exec_segs, imports, exports


def e32_vbase(r, m):
    return r.e32(m)["vbase"]


# --------------------------------------------------------------------------
# Self-test on synthetic SH-4 bytes (no vendor data)
# --------------------------------------------------------------------------

def _synthetic():
    """Build a tiny text block at 0x10000 with known answers.

    Layout (addresses):
      0x10000  rts ; nop                       end of the previous function
      0x10004  sts.l pr,@-r15                  function F starts here
      0x10006  mov.l @(pc),r3  -> pool 0x1001c (holds 0x10040, the thunk VA)
      0x10008  jsr @r3 ; nop                   call F -> thunk
      0x1000c  bsr 0x10040 ; nop               direct call to the thunk
      0x10010  rts ; nop
      0x10014  (pad)
      0x10040  thunk: mov.l @(pc),r0 -> pool 0x10048 (holds slot 0x20000)
               mov.l @r0,r0 ; jmp @r0 ; nop
      0x10048  slot literal 0x20000
      0x1001c  pool: 0x10040 (thunk VA) at 0x1001c
    """
    base = 0x10000
    b = bytearray(0x80)

    def put(va, w):
        struct.pack_into("<H", b, va - base, w)

    put(0x10000, 0x000B); put(0x10002, 0x0009)
    put(0x10004, 0x4F22)
    # mov.l @(pc),r3 at 0x10006: lit = ((0x10006+4)&~3) + disp*4 = 0x1000c? use 0x1001c
    # (0x10008 & ~3)=0x10008 -> disp = (0x1001c-0x10008)/4 = 5
    put(0x10006, 0xD300 | 5)
    put(0x10008, 0x430B); put(0x1000A, 0x0009)
    put(0x1000C, 0xB000 | (((0x10040 - (0x1000C + 4)) // 2) & 0xFFF)); put(0x1000E, 0x0009)
    put(0x10010, 0x000B); put(0x10012, 0x0009)
    # thunk at 0x10040: mov.l @(pc),r0 -> lit (0x10040+4)&~3 = 0x10044, + disp*4 = 0x10048 -> disp=1
    put(0x10040, 0xD001); put(0x10042, 0x6002); put(0x10044, 0x402B); put(0x10046, 0x0009)
    # pool bytes
    struct.pack_into("<I", b, 0x10048 - base, 0x20000)
    struct.pack_into("<I", b, 0x1001C - base, 0x10040)
    return Mem([(base, bytes(b))]), [(base, bytes(b))]


def _gap_mem():
    """rts; nop; literal pool word; function with a prologue at 0x1000e."""
    base = 0x10000
    b = bytearray(0x40)
    struct.pack_into("<H", b, 0x00, 0x000B)   # rts
    struct.pack_into("<H", b, 0x02, 0x0009)   # delay slot nop
    struct.pack_into("<I", b, 0x04, 0x00ABCDEF)  # pool data
    struct.pack_into("<H", b, 0x0E, 0x2F86)   # mov.l r8,@-r15 (prologue)
    return Mem([(base, bytes(b))])


def selftest():
    fails = []

    def check(label, got, want):
        ok = got == want
        print("%-44s %s" % (label, "ok" if ok else "FAIL got=%r want=%r" % (got, want)))
        if not ok:
            fails.append(label)

    mem, exec_segs = _synthetic()
    check("movl_pc_target", movl_pc_target(0x10006, mem.u16(0x10006)), (3, 0x1001C))
    check("bsr_target", bsr_target(0x1000C, mem.u16(0x1000C)), 0x10040)
    check("bsr negative disp (0xBFFE: PC+4-4)", bsr_target(0x10044, 0xBFFE), 0x10044)
    check("jsr_reg", jsr_reg(0x430B), ("jsr", 3))
    check("function_start from 0x10008", function_start(mem, 0x10008), 0x10004)
    check("function_start skips pool gap", function_start(_gap_mem(), 0x10016), 0x1000E)
    check("thunk_slot", thunk_slot(mem, 0x10040), 0x20000)
    check("pool_entries(0x10040)", pool_entries(mem, exec_segs, 0x10040), [0x1001C])
    check("loads_of(0x1001C)", loads_of(mem, 0x1001C), [(0x10006, 3)])
    check("call_after load 0x10006", call_after(mem, 0x10006, 3), (0x10008, "jsr"))

    lab = Labeller(mem, {0x20000: "OBJDLL.dll!MAL_test"}, {0x10004: "F_export"})
    check("label thunk", lab(0x10040), "IMPORT OBJDLL.dll!MAL_test")
    check("label export", lab(0x10004), "EXPORT F_export")

    to_lines = query_to(mem, exec_segs, 0x10040, lab)
    check("--to 0x10040 reports one pool and one load",
          [l.split()[0] for l in to_lines], ["pool", "load"])
    check("--to call site is the jsr", "jsr 0x00010008" in to_lines[1], True)

    calls = query_calls(mem, 0x10004, lab)
    check("--calls finds bsr to thunk",
          any("bsr 0x00010040" in l and "IMPORT" in l for l in calls), True)
    check("--calls finds jsr @r3 to thunk",
          any("jsr @r3 -> 0x00010040" in l for l in calls), True)
    check("--calls stops at rts", any("rts" in l for l in calls), True)

    print("sh4xref selftest: %s" % ("OK" if not fails else "FAILED %d" % len(fails)))
    return 0 if not fails else 1


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?")
    ap.add_argument("module", nargs="?")
    ap.add_argument("--image-start", type=lambda s: int(s, 0), default=None)
    ap.add_argument("--to", type=lambda s: int(s, 0))
    ap.add_argument("--calls", type=lambda s: int(s, 0))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.image or not a.module or (a.to is None and a.calls is None):
        ap.error("IMG MODULE and one of --to / --calls are required (or --selftest)")
    mem, exec_segs, imports, exports = load_module(a.image, a.image_start, a.module)
    lab = Labeller(mem, imports, exports)
    if a.to is not None:
        for line in query_to(mem, exec_segs, a.to, lab):
            print(line)
    if a.calls is not None:
        for line in query_calls(mem, a.calls, lab):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
