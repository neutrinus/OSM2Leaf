#!/usr/bin/env python3
"""Trace who reads which field of the map data-volume header (M4.48).

The first 0x1000 bytes of ``MMAIN001.DAT`` reach the navigation code through
OBJDLL's data-volume store (EXP-2026-11-20-M4.48-datavol-18c-reader):
``Navi.exe`` reads the file header, swaps each u16 and stores it with
``OBJ_DriveInfo_writeDataVol``; readers fetch either the whole block or one
field by index through ``OBJ_DriveInfo_readDataVol``,
``OBJ_DiscInfo_readDiscVol(obj, 0, index, buf)`` and
``MAL_DataVol_getSize/getOffset(index, &out)``.  The index → (offset, size)
map is a 21-entry table in OBJDLL's data section.

Three questions, three subcommands:

  table IMG            the field table (u16 size, u16 offset) as OBJDLL's own
                       ``MAL_DataVol_getSize`` addresses it (table VA taken
                       from the export's literal pool; data via nk_decomp).
  calls IMG            every call site, in every module that imports them, of
                       getSize/getOffset (index in r4) and readDiscVol (index
                       in r6), with the index resolved from a ``mov #imm`` in
                       the same straight-line block, and the byte range it
                       names.  ``--field 0x18c`` exits 1 if no site asks for a
                       field that overlaps that offset.
  taint IMG            a straight-line register taint over functions that load
                       a header-copy pointer (``--global``: a VA holding the
                       pointer; ``--buffer``: a VA that is the copy) and the
                       callees that receive it in r4..r7, to ``--depth``
                       levels; prints every constant header offset accessed.
                       ``--field 0x18c`` exits 1 if no access hits
                       [field, field+size).

The taint is linear (no control flow, no memory round-trips except the seed
global), so it under-reports; a miss is a negative for these patterns only.

Stdlib only.  Decoding is ``tools/sh4dis.py``; sections and imports come from
``tools/cerom.py``; function bounds from the pdata table (``tools/pdata.py``).

Usage:
  datavol_trace.py table IMG
  datavol_trace.py calls IMG [--field 0x18c --size 20]
  datavol_trace.py taint IMG --module Navi.exe --global 0x00d8b070
                   [--buffer 0x009c9600 ...] [--depth 2] [--field 0x18c]
  datavol_trace.py --selftest
"""

import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cerom  # noqa: E402
import pdata  # noqa: E402
import sh4dis  # noqa: E402
import nk_decomp  # noqa: E402

IMAGE_START = 0x200200          # build A (EU 2011)
OBJDLL = "OBJDLL.dll"
TABLE_ENTRIES = 21
EXPORT_SIZE = "MAL_DataVol_getSize"
INDEX_ARG = {                   # import name -> register that carries the index
    "MAL_DataVol_getSize": 4,
    "MAL_DataVol_getOffset": 4,
    "OBJ_DiscInfo_readDiscVol": 6,
}
BACK_WINDOW = 24                # halfwords scanned back from a call for the index


# --------------------------------------------------------------------------
# Image access
# --------------------------------------------------------------------------

class Module:
    """Sections of one module: plain ones from the file, compressed data via nk_decomp."""

    def __init__(self, data, rom, name, decompress=()):
        self.rom = rom
        self.mod = rom.module(name)
        self.name = self.mod["name"]
        self.e32 = rom.e32(self.mod)
        self.secs = list(rom.o32(self.mod))
        segs, self.exec_segs = [], []
        for i, s in enumerate(self.secs):
            if s["flags"] & cerom.IMAGE_SCN_COMPRESSED:
                if i in decompress:
                    blob = nk_decomp.section_init(data, self.name, i, rom.start)
                    segs.append((s["realaddr"], blob))
                continue
            off = rom.va2file(s["dataptr"])
            blob = data[off:off + s["psize"]]
            segs.append((s["realaddr"], blob))
            if s["flags"] & 0x20000000:
                self.exec_segs.append((s["realaddr"], blob[:s["vsize"]]))
        self.mem = sh4dis.Mem(segs)

    def real_va(self, va):
        """Map a vbase+rva VA (as the import table names it) to where the section loads."""
        rva = va - self.e32["vbase"]
        for s in self.secs:
            if s["rva"] <= rva < s["rva"] + max(s["vsize"], s["psize"]):
                return s["realaddr"] + rva - s["rva"]
        return va


def load(path):
    with open(path, "rb") as fh:
        data = fh.read()
    return data, cerom.CERom(data, IMAGE_START)


def pool_entries(exec_segs, value):
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
    out = []
    for a in range(max(0, pool_va - 1024 - 4), pool_va, 2):
        w = mem.u16(a)
        if w is None:
            continue
        t = sh4dis.movl_pc_target(a, w)
        if t and t[1] == pool_va:
            out.append((a, t[0]))
    return out


def is_stub(mem, va):
    """mov.l @(pc),r0 ; mov.l @r0,r0 ; jmp @r0 ; nop (import stub)."""
    return (mem.u16(va + 2) == 0x6002 and mem.u16(va + 4) == 0x402B
            and mem.u16(va + 6) == 0x0009)


# --------------------------------------------------------------------------
# table
# --------------------------------------------------------------------------

def field_table(data, rom):
    """(table_va, [(size_u16, offset_u16)]) read through MAL_DataVol_getSize's pool."""
    mod = rom.module(OBJDLL)
    e32 = rom.e32(mod)
    rva = {n: r for _o, n, r in rom.exports(mod)}[EXPORT_SIZE]
    secs = list(rom.o32(mod))
    data_idx = [i for i, s in enumerate(secs) if s["flags"] & cerom.IMAGE_SCN_COMPRESSED]
    m = Module(data, rom, OBJDLL, decompress=data_idx)
    fn = e32["vbase"] + rva
    table_va = None
    for k in range(16):
        w = m.mem.u16(fn + 2 * k)
        t = sh4dis.movl_pc_target(fn + 2 * k, w) if w is not None else None
        if t:
            table_va = m.mem.u32(t[1])
            break
    if table_va is None:
        raise SystemExit("no literal load in %s" % EXPORT_SIZE)
    raw = m.mem.read(table_va, 4 * TABLE_ENTRIES)
    if raw is None:
        raise SystemExit("table 0x%08x not in OBJDLL sections" % table_va)
    return fn, table_va, [struct.unpack_from("<HH", raw, 4 * i) for i in range(TABLE_ENTRIES)]


def byte_range(entry):
    size, off = entry
    return 2 * off, 2 * (off + size)


def cmd_table(args):
    data, rom = load(args.image)
    fn, table_va, rows = field_table(data, rom)
    print("%s @ 0x%08x -> table 0x%08x (%d entries, u16 size, u16 offset; units = u16)"
          % (EXPORT_SIZE, fn, table_va, len(rows)))
    for i, e in enumerate(rows):
        lo, hi = byte_range(e)
        print("  idx %2d  size %4d  off %4d  bytes 0x%03x..0x%03x" % (i, e[0], e[1], lo, hi))
    return 0


# --------------------------------------------------------------------------
# calls
# --------------------------------------------------------------------------

MOV_IMM = re.compile(r"^mov #(-?\d+),r(\d+)$")


def resolve_reg(mem, call_va, reg):
    """Constant written to ``reg`` before the call (delay slot first), or None.

    Walks back from the call within BACK_WINDOW halfwords; stops at a branch
    target boundary it cannot see, so a None means "not resolved", not "absent".
    """
    ds = sh4dis.decode(mem.u16(call_va + 2), call_va + 2, mem)
    m = MOV_IMM.match(ds.text)
    if m and int(m.group(2)) == reg:
        return int(m.group(1))
    if _writes(ds, reg):
        return None
    for k in range(1, BACK_WINDOW + 1):
        va = call_va - 2 * k
        w = mem.u16(va)
        if w is None:
            return None
        insn = sh4dis.decode(w, va, mem)
        if insn.kind in ("call", "ret", "jump"):
            return None
        m = MOV_IMM.match(insn.text)
        if m and int(m.group(2)) == reg:
            return int(m.group(1))
        if _writes(insn, reg):
            return None
    return None


def _writes(insn, reg):
    t = insn.text
    if insn.kind in ("call",):
        return reg in range(0, 8)
    if "," not in t:
        return False
    dst = t.rsplit(",", 1)[1]
    return dst == "r%d" % reg


def call_sites(module, slot_real):
    """[(call_va, how)] for calls through the import slot ``slot_real``."""
    mem = module.mem
    sites = []
    targets = []                       # (va loading slot or stub, register)
    for pool in pool_entries(module.exec_segs, slot_real):
        for load_va, reg in loads_of(mem, pool):
            if is_stub(mem, load_va) and reg == 0:
                for pool2 in pool_entries(module.exec_segs, load_va):
                    for l2, r2 in loads_of(mem, pool2):
                        targets.append((l2, r2, "stub 0x%08x" % load_va))
            else:
                targets.append((load_va, reg, "slot"))
    seen = set()
    for load_va, reg, how in targets:
        for k in range(1, 12):
            a = load_va + 2 * k
            w = mem.u16(a)
            if w is None:
                break
            j = sh4dis.jsr_reg(w)
            if j and j[1] == reg:
                if a not in seen:
                    seen.add(a)
                    sites.append((a, how))
                break
    return sites


def thunk_callers(module, slot_real, thunks):
    """Calls via Navi.exe 4-insn thunks (``cerom thunks``) for one slot."""
    out = []
    mem = module.mem
    for stub in thunks.get(slot_real, ()):
        for pool in pool_entries(module.exec_segs, stub):
            for load_va, reg in loads_of(mem, pool):
                for k in range(1, 12):
                    a = load_va + 2 * k
                    w = mem.u16(a)
                    if w is None:
                        break
                    j = sh4dis.jsr_reg(w)
                    if j and j[1] == reg:
                        out.append((a, "thunk 0x%08x" % stub))
                        break
    return out


def navi_thunks(module):
    """{slot: [stub]} for 'mov.l @(pc),rX; mov.l @rX,rX; jmp @rX; nop' stubs, any rX."""
    out = {}
    for base, blob in module.exec_segs:
        for i in range(0, len(blob) - 8, 2):
            w = blob[i] | blob[i + 1] << 8
            if w & 0xF000 != 0xD000:
                continue
            r = (w >> 8) & 15
            w2 = blob[i + 2] | blob[i + 3] << 8
            w3 = blob[i + 4] | blob[i + 5] << 8
            if w2 != (0x6002 | r << 8 | r << 4) or w3 != (0x402B | r << 8):
                continue
            va = base + i
            t = sh4dis.movl_pc_target(va, w)
            slot = module.mem.u32(t[1])
            if slot is not None:
                out.setdefault(slot, []).append(va)
    return out


def direct_callers(module, fn_va):
    """Calls inside ``module`` through a literal holding ``fn_va`` (own exports)."""
    out = []
    mem = module.mem
    for pool in pool_entries(module.exec_segs, fn_va):
        for load_va, reg in loads_of(mem, pool):
            for k in range(1, 12):
                a = load_va + 2 * k
                w = mem.u16(a)
                if w is None:
                    break
                j = sh4dis.jsr_reg(w)
                if j and j[1] == reg:
                    out.append((a, "direct"))
                    break
            # a register kept across calls (jsr @r12 ...) is called again later
            for k in range(12, 160):
                a = load_va + 2 * k
                w = mem.u16(a)
                if w is None or w == 0x000B:
                    break
                j = sh4dis.jsr_reg(w)
                if j and j[1] == reg and reg >= 8:
                    out.append((a, "direct r%d" % reg))
    return out


def census(data, rom, fn_of_cache=None):
    """[(module, import, call_va, fn_start, how, index)] over all modules,
    plus OBJDLL's own calls of the exports it defines."""
    rows = []
    mod = rom.module(OBJDLL)
    own = {n: rom.e32(mod)["vbase"] + r for _o, n, r in rom.exports(mod) if n in INDEX_ARG}
    module = Module(data, rom, OBJDLL)
    records = pdata.table_or_none(data, rom.start, module.name)
    fn_of = pdata.fn_of_factory(records) if records else (lambda va: None)
    for nm, va in sorted(own.items()):
        sites = {}
        for call_va, how in direct_callers(module, va):
            sites.setdefault(call_va, how)
        for call_va, how in sorted(sites.items()):
            rows.append((module.name, nm, call_va, fn_of(call_va), how,
                         resolve_reg(module.mem, call_va, INDEX_ARG[nm])))
    for mod in rom.modules():
        name = mod["name"]
        wanted = []
        for _dll, slot, nm, _ord in rom.imports(mod):
            if nm in INDEX_ARG:
                wanted.append((slot, nm))
        if not wanted:
            continue
        module = Module(data, rom, name)
        thunks = navi_thunks(module)
        records = pdata.table_or_none(data, rom.start, name)
        fn_of = pdata.fn_of_factory(records) if records else (lambda va: None)
        for slot, nm in wanted:
            real = module.real_va(slot)
            sites = {}
            for call_va, how in call_sites(module, real) + thunk_callers(module, real, thunks):
                sites.setdefault(call_va, how)
            for call_va, how in sorted(sites.items()):
                idx = resolve_reg(module.mem, call_va, INDEX_ARG[nm])
                rows.append((name, nm, call_va, fn_of(call_va), how, idx))
    return rows


def cmd_calls(args):
    data, rom = load(args.image)
    _fn, table_va, table = field_table(data, rom)
    rows = census(data, rom)
    hit = whole = 0
    lo_f, hi_f = args.field, args.field + args.size
    print("DataVol field table 0x%08x; call sites of %s" % (table_va, ", ".join(sorted(INDEX_ARG))))
    for name, nm, call_va, fn, how, idx in rows:
        if idx is None:
            rng, flag = "index ?", ""
        elif 0 <= idx < len(table):
            lo, hi = byte_range(table[idx])
            rng = "index %2d bytes 0x%03x..0x%03x" % (idx, lo, hi)
            overlap = args.field >= 0 and lo < hi_f and lo_f < hi
            if overlap and hi - lo >= 0x1000:
                flag = "  (whole block, contains 0x%03x)" % lo_f
                whole += 1
            elif overlap:
                flag = "  <-- field request overlapping 0x%03x" % lo_f
                hit += 1
            else:
                flag = ""
        else:
            rng, flag = "index %d (out of table)" % idx, ""
        print("  %-18s %-26s call 0x%08x fn %-10s %-18s %s%s"
              % (name, nm, call_va, "0x%08x" % fn if fn else "gap", how, rng, flag))
    print("sites %d, resolved %d, unresolved %d; field requests overlapping 0x%03x..0x%03x: %d;"
          " whole-block copies: %d"
          % (len(rows), sum(r[5] is not None for r in rows), sum(r[5] is None for r in rows),
             lo_f, hi_f, hit, whole))
    if args.field >= 0:
        return 0 if hit else 1
    return 0


# --------------------------------------------------------------------------
# taint
# --------------------------------------------------------------------------

RE = {
    "movl_pc": re.compile(r"^mov\.l @\(0x([0-9a-f]+),pc\),r(\d+)"),
    "movw_pc": re.compile(r"^mov\.w @\(0x([0-9a-f]+),pc\),r(\d+)"),
    "mov_imm": re.compile(r"^mov #(-?\d+),r(\d+)$"),
    "mov_rr": re.compile(r"^mov r(\d+),r(\d+)$"),
    "add_imm": re.compile(r"^add #(-?\d+),r(\d+)$"),
    "add_rr": re.compile(r"^add r(\d+),r(\d+)$"),
    "shift": re.compile(r"^(shll|shll2|shll8|shll16|shlr|shlr2|shlr8|shlr16) r(\d+)$"),
    "ext": re.compile(r"^(extu\.b|extu\.w|exts\.b|exts\.w) r(\d+),r(\d+)$"),
    "ld_ind": re.compile(r"^mov\.([bwl]) @r(\d+)(\+?),r(\d+)$"),
    "ld_disp": re.compile(r"^mov\.([bwl]) @\((\d+),r(\d+)\),r(\d+)$"),
    "ld_r0": re.compile(r"^mov\.([bwl]) @\(r0,r(\d+)\),r(\d+)$"),
    "st_ind": re.compile(r"^mov\.([bwl]) r(\d+),@(-?)r(\d+)$"),
    "st_disp": re.compile(r"^mov\.([bwl]) r(\d+),@\((\d+),r(\d+)\)$"),
    "st_r0": re.compile(r"^mov\.([bwl]) r(\d+),@\(r0,r(\d+)\)$"),
}
SIZE = {"b": 1, "w": 2, "l": 4}
SHIFT = {"shll": 1, "shll2": 2, "shll8": 8, "shll16": 16,
         "shlr": -1, "shlr2": -2, "shlr8": -8, "shlr16": -16}


def taint_function(mem, start, end, seeds_global=(), seeds_buffer=(), arg_regs=None):
    """Linear walk of [start, end).

    Register values: ('c', k) constant, ('g', None) address of a seed global,
    ('h', k) header pointer + k.  ``arg_regs`` = {reg: offset} for a callee.
    Returns (accesses, calls): accesses = [(va, 'ld'|'st', size, offset, text)],
    calls = [(call_va, target_or_None, {reg: offset})].
    """
    regs = dict(("r%d" % r, ("h", k)) for r, k in (arg_regs or {}).items())
    accesses, calls = [], []
    gset, bset = set(seeds_global), set(seeds_buffer)
    va = start
    pending_call = None
    while va < end:
        w = mem.u16(va)
        if w is None:
            break
        insn = sh4dis.decode(w, va, mem)
        t = insn.text.split("  ;")[0]
        _step(mem, insn, t, regs, gset, bset, accesses)
        if pending_call is not None:          # delay slot executed: record the call
            calls.append(pending_call(regs))
            for r in range(8):
                regs.pop("r%d" % r, None)
            pending_call = None
        if insn.kind == "call":
            target = insn.target
            m = re.match(r"^jsr @r(\d+)", t)
            if m:
                v = regs.get("r%s" % m.group(1))
                target = v[1] if v and v[0] == "c" else None
            cva = va
            pending_call = (lambda rs, cva=cva, target=target:
                            (cva, target, {int(r[1:]): v[1] for r, v in rs.items()
                                           if v[0] == "h" and r in ("r4", "r5", "r6", "r7")}))
        va += 2
    return accesses, calls


def _step(mem, insn, t, regs, gset, bset, accesses):
    def get(r):
        return regs.get("r%s" % r)

    def put(r, v):
        if v is None:
            regs.pop("r%s" % r, None)
        else:
            regs["r%s" % r] = v

    def acc(kind, size, base, extra, text):
        if base and base[0] == "h":
            accesses.append((insn.va, kind, size, base[1] + extra, text))

    m = RE["movl_pc"].match(t)
    if m:
        lit = mem.u32(int(m.group(1), 16))
        if lit in gset:
            put(m.group(2), ("g", None))
        elif lit in bset:
            put(m.group(2), ("h", 0))
        else:
            put(m.group(2), ("c", lit) if lit is not None else None)
        return
    m = RE["movw_pc"].match(t)
    if m:
        v = mem.u16(int(m.group(1), 16))
        put(m.group(2), ("c", v - 0x10000 if v is not None and v & 0x8000 else v) if v is not None else None)
        return
    m = RE["mov_imm"].match(t)
    if m:
        put(m.group(2), ("c", int(m.group(1))))
        return
    m = RE["mov_rr"].match(t)
    if m:
        put(m.group(2), get(m.group(1)))
        return
    m = RE["add_imm"].match(t)
    if m:
        v = get(m.group(2))
        put(m.group(2), (v[0], v[1] + int(m.group(1))) if v and v[0] in ("c", "h") else None)
        return
    m = RE["add_rr"].match(t)
    if m:
        a, b = get(m.group(1)), get(m.group(2))
        if a and b and a[0] == "c" and b[0] == "c":
            put(m.group(2), ("c", (a[1] + b[1]) & 0xFFFFFFFF))
        elif a and b and {a[0], b[0]} == {"c", "h"}:
            h, c = (a, b) if a[0] == "h" else (b, a)
            put(m.group(2), ("h", h[1] + c[1]))
        else:
            put(m.group(2), None)
        return
    m = RE["shift"].match(t)
    if m:
        v = get(m.group(2))
        if v and v[0] == "c":
            s = SHIFT[m.group(1)]
            x = v[1] & 0xFFFFFFFF
            put(m.group(2), ("c", (x << s) & 0xFFFFFFFF if s > 0 else x >> -s))
        else:
            put(m.group(2), None)
        return
    m = RE["ext"].match(t)
    if m:
        v = get(m.group(2))
        if v and v[0] == "c":
            x = v[1]
            x = x & 0xFF if m.group(1) == "extu.b" else x & 0xFFFF if m.group(1) == "extu.w" else \
                ((x & 0xFF) ^ 0x80) - 0x80 if m.group(1) == "exts.b" else ((x & 0xFFFF) ^ 0x8000) - 0x8000
            put(m.group(3), ("c", x))
        else:
            put(m.group(3), None)
        return
    m = RE["ld_ind"].match(t)
    if m:
        sz, rm, inc, rn = SIZE[m.group(1)], m.group(2), m.group(3), m.group(4)
        base = get(rm)
        acc("ld", sz, base, 0, t)
        if inc and base and base[0] in ("h", "c"):
            put(rm, (base[0], base[1] + sz))
        put(rn, ("h", 0) if base and base[0] == "g" and sz == 4 else None)
        return
    m = RE["ld_disp"].match(t)
    if m:
        sz, disp, rm, rn = SIZE[m.group(1)], int(m.group(2)), m.group(3), m.group(4)
        acc("ld", sz, get(rm), disp, t)
        put(rn, None)
        return
    m = RE["ld_r0"].match(t)
    if m:
        sz, rm, rn = SIZE[m.group(1)], m.group(2), m.group(3)
        a, b = get(0), get(rm)
        if a and b and {a[0], b[0]} == {"c", "h"}:
            h, c = (a, b) if a[0] == "h" else (b, a)
            acc("ld", sz, h, c[1], t)
        put(rn, None)
        return
    m = RE["st_ind"].match(t)
    if m:
        sz, rn = SIZE[m.group(1)], m.group(4)
        base = get(rn)
        if m.group(3) == "-":
            put(rn, (base[0], base[1] - sz) if base and base[0] in ("h", "c") else None)
            base = get(rn)
        acc("st", sz, base, 0, t)
        return
    m = RE["st_disp"].match(t)
    if m:
        acc("st", SIZE[m.group(1)], get(m.group(4)), int(m.group(3)), t)
        return
    m = RE["st_r0"].match(t)
    if m:
        a, b = get(0), get(m.group(3))
        if a and b and {a[0], b[0]} == {"c", "h"}:
            h, c = (a, b) if a[0] == "h" else (b, a)
            acc("st", SIZE[m.group(1)], h, c[1], t)
        return
    # anything else that names a destination register clobbers it
    if insn.kind in ("call", "branch", "jump", "ret"):
        return
    if t.startswith((".word", "mul", "dmul", "cmp", "tst", "lds", "clrt", "sett", "nop", "dt ")):
        if t.startswith(".word"):
            put((insn.word >> 8) & 15, None)     # sts macl,Rn and friends
        if t.startswith("dt "):
            v = get(t.split("r")[-1])
            put(t.split("r")[-1], ("c", v[1] - 1) if v and v[0] == "c" else None)
        return
    if "," in t:
        dst = t.rsplit(",", 1)[1]
        if re.fullmatch(r"r\d+", dst):
            put(dst[1:], None)
    elif re.fullmatch(r"\w+(\.\w)? r\d+", t):
        put(t.split()[-1][1:], None)


LEAF_MAX = 0x400


def fn_bounds(records, va, mem=None):
    """(start, end) from pdata; for a call target in a pdata gap (leaf), the
    span up to its first ``rts`` plus delay slot (at most LEAF_MAX bytes)."""
    kind, rec = nk_decomp.locate(records, va)
    if rec is not None and kind != "GAP":
        return rec[0], rec[0] + rec[2]
    if mem is None:
        return None
    for a in range(va, va + LEAF_MAX, 2):
        w = mem.u16(a)
        if w is None:
            return None
        if w == 0x000B:
            return va, a + 4
    return None


def taint_tree(mem, records, exec_segs, gvas, bvas, depth):
    """Functions that load a seed, then callees that receive the header, to ``depth``."""
    roots = set()
    for v in list(gvas) + list(bvas):
        for pool in pool_entries(exec_segs, v):
            for load_va, _reg in loads_of(mem, pool):
                b = fn_bounds(records, load_va)
                if b:
                    roots.add(b)
    out = []
    queue = [(b, None, 0, None) for b in sorted(roots)]
    seen = set()
    while queue:
        bounds, args, level, parent = queue.pop(0)
        key = (bounds[0], tuple(sorted((args or {}).items())))
        if key in seen:
            continue
        seen.add(key)
        acc, calls = taint_function(mem, bounds[0], bounds[1], gvas, bvas, args)
        out.append((bounds[0], level, parent, args, acc, calls))
        if level >= depth:
            continue
        for cva, target, hargs in calls:
            if not hargs or target is None:
                continue
            b = fn_bounds(records, target, mem)
            if b is None or b[0] != target:
                continue
            queue.append((b, hargs, level + 1, bounds[0]))
    return out


def cmd_taint(args):
    data, rom = load(args.image)
    module = Module(data, rom, args.module)
    records = pdata.table_or_none(data, rom.start, module.name)
    if not records:
        raise SystemExit("no pdata for %s" % module.name)
    tree = taint_tree(module.mem, records, module.exec_segs, args.glob, args.buffer, args.depth)
    lo_f, hi_f = args.field, args.field + args.size
    hits, offsets = 0, set()
    for fn, level, parent, fargs, acc, calls in tree:
        argtxt = ",".join("r%d=hdr+0x%x" % (r, k) for r, k in sorted((fargs or {}).items()))
        print("%sfn 0x%08x  level %d%s%s" % ("  " * level, fn, level,
                                            "  from 0x%08x" % parent if parent else "",
                                            "  args " + argtxt if argtxt else ""))
        for va, kind, size, off, text in acc:
            flag = "  <-- in 0x%03x..0x%03x" % (lo_f, hi_f) if args.field >= 0 and lo_f <= off < hi_f else ""
            hits += bool(flag)
            offsets.add(off)
            print("%s  0x%08x %s.%d hdr+0x%03x  %s%s" % ("  " * level, va, kind, size, off, text, flag))
        for cva, target, hargs in calls:
            if hargs:
                print("%s  call 0x%08x -> %s with %s" % (
                    "  " * level, cva, "0x%08x" % target if target is not None else "?",
                    ",".join("r%d=hdr+0x%x" % kv for kv in sorted(hargs.items()))))
    print("functions %d, accesses %d, distinct offsets %s"
          % (len(tree), sum(len(t[4]) for t in tree),
             " ".join("0x%03x" % o for o in sorted(offsets))))
    if args.field >= 0:
        print("field 0x%03x..0x%03x hits: %d" % (lo_f, hi_f, hits))
        return 0 if hits else 1
    return 0


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------

def _asm(words):
    return b"".join(struct.pack("<H", w) for w in words)


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print("  %-58s %s" % (name, "ok" if cond else "FAIL"))
        ok &= bool(cond)

    # Synthetic function at 0x1000: r8 = *(G); r3 = 99<<2 (0x18c); r0 = r8;
    # mov.w @(r0,r3),r3 ; mov.w @(10,r8),r0 ; mov r8,r4 ; jsr @r1 ; nop ; rts ; nop
    # pool at 0x1020: G = 0x00d8b070
    code = [
        0xD807,   # 0x1000 mov.l @(0x1020,pc),r8   (pc=0x1004 -> disp 7*4=0x1c -> 0x1020)
        0x6882,   # 0x1002 mov.l @r8,r8            (r8 = hdr)
        0xE363,   # 0x1004 mov #99,r3
        0x4308,   # 0x1006 shll2 r3
        0x6083,   # 0x1008 mov r8,r0
        0x033D,   # 0x100a mov.w @(r0,r3),r3       -> hdr+0x18c
        0x8585,   # 0x100c mov.w @(10,r8),r0       -> hdr+0x0a
        0x6483,   # 0x100e mov r8,r4
        0x410B,   # 0x1010 jsr @r1
        0x0009,   # 0x1012 nop
        0x000B,   # 0x1014 rts
        0x0009,   # 0x1016 nop
        0x0009, 0x0009, 0x0009, 0x0009,   # 0x1018..0x101e
    ]
    blob = _asm(code) + struct.pack("<I", 0x00D8B070)
    mem = sh4dis.Mem([(0x1000, blob)])
    acc, calls = taint_function(mem, 0x1000, 0x1018, [0x00D8B070], [])
    offs = sorted(a[3] for a in acc)
    check("taint: header offsets 0x00a and 0x18c found", offs == [0x0A, 0x18C])
    check("taint: header pointer passed in r4 recorded", calls and calls[0][2] == {4: 0})
    # same code with the seed absent -> no accesses (negative control)
    acc2, _ = taint_function(mem, 0x1000, 0x1018, [0x12345678], [])
    check("taint: wrong seed global -> no accesses", acc2 == [])
    # buffer seed: literal is the copy itself; add #12 then @r -> +0x0c
    code_b = [0xD301, 0x730C, 0x6231, 0x0009, 0x0000, 0x0000]
    blob_b = _asm(code_b[:4]) + struct.pack("<I", 0x009C9600)
    mem_b = sh4dis.Mem([(0x2000, blob_b)])
    acc3, _ = taint_function(mem_b, 0x2000, 0x2008, [], [0x009C9600])
    check("taint: buffer seed + add #12 -> hdr+0x00c", [a[3] for a in acc3] == [0x0C])
    # resolve_reg: mov #9,r6 two insns before jsr @r3 ; delay-slot mov #20,r6 wins
    code_c = [0xE609, 0xE500, 0x430B, 0x0009, 0xE609, 0x430B, 0xE614]
    mem_c = sh4dis.Mem([(0x3000, _asm(code_c))])
    check("resolve: index 9 from mov #9,r6", resolve_reg(mem_c, 0x3004, 6) == 9)
    check("resolve: delay-slot mov #20,r6 overrides", resolve_reg(mem_c, 0x300A, 6) == 20)
    check("resolve: unrelated reg -> None", resolve_reg(mem_c, 0x3004, 7) is None)
    # byte_range of the M4.48 field
    check("byte_range(size 10, off 198) = 0x18c..0x1a0", byte_range((10, 198)) == (0x18C, 0x1A0))
    print("selftest:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("table")
    p.add_argument("image")
    p = sub.add_parser("calls")
    p.add_argument("image")
    p.add_argument("--field", type=lambda s: int(s, 0), default=-1)
    p.add_argument("--size", type=lambda s: int(s, 0), default=2)
    p = sub.add_parser("taint")
    p.add_argument("image")
    p.add_argument("--module", default="Navi.exe")
    p.add_argument("--global", dest="glob", action="append", default=[],
                   type=lambda s: int(s, 0))
    p.add_argument("--buffer", action="append", default=[], type=lambda s: int(s, 0))
    p.add_argument("--depth", type=int, default=2)
    p.add_argument("--field", type=lambda s: int(s, 0), default=-1)
    p.add_argument("--size", type=lambda s: int(s, 0), default=2)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "table":
        return cmd_table(args)
    if args.cmd == "calls":
        return cmd_calls(args)
    if args.cmd == "taint":
        return cmd_taint(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
