#!/usr/bin/env python3
"""Census of object-store event subscriptions in a CE ROM image (M9.57).

An object-store event reaches a task as message ``0x07d0`` with a sub word.
The subscriber fills an event parameter block with

    OBJ_Event_setPrm(prm, task, sub, kind)           (OBJDLL #262)
    OBJ_Event_setPrmForMP(prm, ...)                  (OBJDLL #263, other processes)

and hands the block to an object call (``OBJ_DiscInfo_setEventPublicDisc``,
``OBJ_CarPos_setEventMesh``, ...).  This tool lists every call site of the two
functions in every module of a segment and resolves, for each site, where the
argument registers ``r5``/``r6``/``r7`` come from:

    imm 0x64          a literal (``mov #imm``, a pool word, with ``extu``/``shll``)
    *0x011fff58       a word loaded from that global (a task id)
    arg r6            the caller's own argument register.  Such a site is a
                      helper: it is printed once per caller of the helper,
                      with the argument read at that call ("helper called at")
    call              the result of a call (``taskIdSelf()``)
    ?                 not resolved by the backward walk

and names the object call that follows the site (the next import call that is
not ``OBJ_Event_*``).

The walk is linear and local: it reads back at most BACK instructions from the
``jsr`` and stops at the function start.  It does not follow branches, so a
value set on another path prints ``?`` -- a ``?`` row must be read by hand and
is counted in the summary.  A site is found through the literal pool that
holds the import stub's VA or the import slot (inlined call), as
``tools/sh4xref.py`` does, and every ``jsr`` through a callee-saved register
that still holds the loaded address is a site (one load, several calls).  An
address that reaches the ``jsr`` through memory or another register copy
would be missed (the positive control below guards the common form).

Usage:
  event_subs.py IMG [--image-start 0x200200] [--resolve-with 0x3e00200]
                    [--module Navi.exe] [--task 0x011fff58] [--sub 11]
                    [--expect-site 0x003eb99c] [--json OUT]
                    [--handler-table Navi.exe:0x001796f4:6]
  event_subs.py --selftest

``--task``/``--sub`` filter the rows; with a filter the exit status is 1 when
no row matches (a negative that can fail needs ``--expect-site``: the named
``jsr`` VA must be in the unfiltered census, else exit 2).

Stdlib only; uses ``tools/cerom.py`` (import stubs), ``tools/sh4dis.py``
(decoder, little-endian) and ``tools/sh4xref.py`` (module loader, pool search).
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import cerom      # noqa: E402
import sh4dis     # noqa: E402
import sh4xref    # noqa: E402

APIS = ("OBJ_Event_setPrm", "OBJ_Event_setPrmForMP")
BACK = 96          # instructions read back from the jsr
HELD = 600        # instructions followed after a load into a callee-saved register
FWD = 40           # instructions read forward for the object call


def _sx8(v):
    return v - 256 if v & 0x80 else v


def _reg_source(mem, jsr_va, reg, floor, start=None):
    """Where does ``reg`` come from at ``jsr_va``?  Returns (kind, value).

    The delay slot (jsr_va + 2) is the last instruction before the call takes
    effect, so the walk starts there.  ``floor`` is the function start.
    ``start`` (with ``jsr_va`` None) begins a plain backward walk at that VA.
    """
    ops = []                  # unary ops applied after the load, newest first
    va = jsr_va + 2 if start is None else start
    want = reg
    steps = 0
    while va >= floor and steps < BACK + 1:
        w = mem.u16(va)
        if w is None:
            break
        if va != jsr_va:
            hi, n, m, lo = w >> 12, (w >> 8) & 15, (w >> 4) & 15, w & 15
            if hi == 0xE and n == want:                       # mov #imm,Rn
                return _apply(("imm", _sx8(w & 0xFF) & 0xFFFFFFFF), ops)
            if hi == 0x9 and n == want:                       # mov.w @(d,PC),Rn
                t = va + 4 + (w & 0xFF) * 2
                v = mem.u16(t)
                if v is None:
                    return ("?", None)
                if v & 0x8000:
                    v |= 0xFFFF0000
                return _apply(("imm", v), ops)
            if hi == 0xD and n == want:                       # mov.l @(d,PC),Rn
                t = ((va + 4) & ~3) + (w & 0xFF) * 4
                v = mem.u32(t)
                return _apply(("imm", v), ops) if v is not None else ("?", None)
            if hi == 0x6 and n == want:
                if lo == 3:                                   # mov Rm,Rn
                    want = m
                    if va == floor or _is_arg_copy(mem, va, floor, m):
                        pass
                elif lo == 2:                                 # mov.l @Rm,Rn
                    src = (_reg_source(mem, None, m, floor, start=va - 2)
                           if va - 2 >= floor else ("?", None))
                    if src[0] == "imm":
                        return ("deref", src[1])
                    return ("deref?", None)
                elif lo == 0xC:                               # extu.b Rm,Rn
                    ops.append("extu.b")
                    want = m
                elif lo == 0xD:                               # extu.w
                    ops.append("extu.w")
                    want = m
                elif lo in (0xE, 0xF):                        # exts.b / exts.w
                    want = m
                else:
                    return ("?", None)
            elif hi == 0x4 and n == want and (w & 0xFF) in (0x08, 0x18, 0x28, 0x00):
                ops.append({0x08: "shll2", 0x18: "shll8", 0x28: "shll16", 0x00: "shll"}[w & 0xFF])
            elif hi == 0x7 and n == want:                     # add #imm,Rn
                ops.append(("add", _sx8(w & 0xFF)))
            elif hi == 0x5 and n == want:                     # mov.l @(d,Rm),Rn
                return ("mem", None)
            elif hi == 0x8 and (w >> 8) == 0x85 and want == 0:  # mov.w @(d,Rm),R0
                return ("mem", None)
            elif (w & 0xF0FF) == 0x400B or hi == 0xB:          # jsr @Rm / bsr
                if want == 0:
                    return ("call", None)
                if want in (4, 5, 6, 7):
                    return ("?", None)                         # clobbered by a call
        va -= 2
        steps += 1
    if want in (4, 5, 6, 7) and va < floor:
        return ("arg", want)
    if want in (8, 9, 10, 11, 12, 13, 14):
        # a callee-saved register that the prologue filled from an argument
        src = _saved_from_arg(mem, floor, want)
        if src is not None:
            return ("arg", src)
    return ("?", None)


def _is_arg_copy(mem, va, floor, m):
    return False


def _saved_from_arg(mem, floor, reg):
    """``mov Rarg,Rreg`` in the first 16 instructions of the function."""
    for k in range(16):
        w = mem.u16(floor + 2 * k)
        if w is None:
            break
        if (w & 0xF00F) == 0x6003 and ((w >> 8) & 15) == reg and ((w >> 4) & 15) in (4, 5, 6, 7):
            return (w >> 4) & 15
    return None


def _apply(src, ops):
    kind, v = src
    if kind != "imm":
        return src
    for op in reversed(ops):
        if op == "extu.b":
            v &= 0xFF
        elif op == "extu.w":
            v &= 0xFFFF
        elif op == "shll":
            v = (v << 1) & 0xFFFFFFFF
        elif op == "shll2":
            v = (v << 2) & 0xFFFFFFFF
        elif op == "shll8":
            v = (v << 8) & 0xFFFFFFFF
        elif op == "shll16":
            v = (v << 16) & 0xFFFFFFFF
        elif isinstance(op, tuple):
            v = (v + op[1]) & 0xFFFFFFFF
    return ("imm", v)


def _fmt_src(src):
    kind, v = src
    if kind == "imm":
        return "imm 0x%x" % v
    if kind == "deref":
        return "*0x%08x" % v
    if kind == "arg":
        return "arg r%d" % v
    return kind


def _call_sites(mem, exec_segs, target):
    """jsr VAs that call ``target`` (a stub VA or an import slot), with the
    load VA.  Covers ``mov.l @(pc),Rn; [mov.l @Rn,Rn;] ... jsr @Rn``."""
    out = []
    for pool in sh4xref.pool_entries(mem, exec_segs, target):
        for load, reg in sh4xref.loads_of(mem, pool):
            call = sh4xref.call_after(mem, load, reg)
            if call:
                out.append((call[0], load))
            if reg >= 8:
                out += [(va, load) for va in _held_calls(mem, load, reg)]
    return sorted(set(out))


def _held_calls(mem, load, reg):
    """Every ``jsr @Rn`` after ``load`` while the callee-saved ``Rn`` (r8-r14)
    still holds the loaded value: a function that calls the same import
    several times keeps its address in one register.  Stops at the first
    instruction that writes ``Rn`` (the epilogue's pop at the latest)."""
    out = []
    for k in range(1, HELD):
        va = load + 2 * k
        w = mem.u16(va)
        if w is None:
            break
        hi, n = w >> 12, (w >> 8) & 15
        if w == (0x400B | (reg << 8)):
            out.append(va)
        elif n == reg and hi in (0x5, 0x6, 0x7, 0x9, 0xD, 0xE):
            break
        elif n == reg and hi == 0x3 and (w & 15) in (0x8, 0xA, 0xB, 0xC, 0xE, 0xF):
            break                                             # sub/add/... Rm,Rn
    return out


def _next_object_call(mem, jsr_va, labels):
    """Name of the first labelled call after the site that is not OBJ_Event_*
    and not an ``_getObjID``; ``labels`` maps stub VA / slot VA -> name."""
    regs = {}
    for k in range(2, FWD):
        va = jsr_va + 2 * k
        w = mem.u16(va)
        if w is None:
            break
        if (w >> 12) == 0xD:
            t = ((va + 4) & ~3) + (w & 0xFF) * 4
            regs[(w >> 8) & 15] = mem.u32(t)
        elif (w & 0xF0FF) == 0x400B:
            v = regs.get((w >> 8) & 15)
            name = labels.get(v)
            if name and not name.startswith("OBJ_Event_") and not name.endswith("_getObjID"):
                return name
        elif w == 0x000B:                                      # rts
            break
    return None


def census_module(mem, exec_segs, stubs, labels, fn_of=None):
    """Rows for one module.  ``stubs``: {api_name: [stub or slot VA, ...]}."""
    rows = []
    for api, targets in stubs.items():
        for target in targets:
            sites = _call_sites(mem, exec_segs, target)
            sites += [(a, a) for a in bsr_sites(exec_segs, target)]
            for jsr, load in sorted(set(sites)):
                if any(t <= jsr < t + 8 for t in targets):
                    continue                  # the import stub's own jmp
                fn = None
                if fn_of is not None:
                    fn = fn_of(jsr)
                if fn is None:
                    fn = sh4xref.fn_start(mem, jsr)
                floor = fn if fn is not None else jsr - 2 * BACK
                row = {"api": api, "jsr": jsr, "fn": fn}
                for reg in (5, 6, 7):
                    row["r%d" % reg] = _fmt_src(_reg_source(mem, jsr, reg, floor))
                row["object_call"] = _next_object_call(mem, jsr, labels)
                rows.extend(_through_callers(mem, exec_segs, row, fn_of))
    return sorted(rows, key=lambda r: (r["jsr"], r.get("caller") or 0))


def _through_callers(mem, exec_segs, row, fn_of=None):
    """A helper takes the task or the sub from its own argument (``arg rN``).
    One row per caller of the helper, with the argument read at that call
    (key ``caller`` = the caller's jsr VA); the row itself when the helper has
    no caller the pool search finds, or when nothing is an argument."""
    args = {k: int(row[k][5:]) for k in ("r5", "r6", "r7") if row[k].startswith("arg r")}
    if not args or row["fn"] is None:
        return [row]
    sites = [a for a, _l in _call_sites(mem, exec_segs, row["fn"])]
    sites += bsr_sites(exec_segs, row["fn"])
    out = []
    for site in sorted(set(sites)):
        fn = fn_of(site) if fn_of is not None else None
        if fn is None:
            fn = sh4xref.fn_start(mem, site)
        floor = fn if fn is not None else site - 2 * BACK
        sub = dict(row, caller=site)
        for k, reg in args.items():
            src = _fmt_src(_reg_source(mem, site, reg, floor))
            sub[k] = src if not src.startswith("arg r") else "arg2 r" + src[5:]
        out.append(sub)
    return out or [row]


def real_slot(r, m, slot_va):
    """The address code uses for an import slot.  A DLL's writable section is
    loaded away from ``vbase + rva`` (``realaddr`` in the o32 record), so the
    slot ``cerom.imports`` prints is not the word the code loads."""
    rva = slot_va - r.e32(m)["vbase"]
    for s in r.o32(m):
        if s["rva"] <= rva < s["rva"] + max(s["vsize"], s["psize"]):
            return s["realaddr"] + (rva - s["rva"])
    return slot_va


def import_labels(mem, exec_segs, slots):
    """{VA: name} for the import slots and for every stub that jumps through
    one (``mov.l @(pc),Rn ; mov.l @Rn,Rn ; jmp @Rn``)."""
    labels = dict(slots)
    for slot, name in slots.items():
        for pool in sh4xref.pool_entries(mem, exec_segs, slot):
            for load, reg in sh4xref.loads_of(mem, pool):
                w1, w2 = mem.u16(load + 2), mem.u16(load + 4)
                if w1 is None or w2 is None:
                    continue
                if (w1 & 0xF00F) == 0x6002 and (w2 & 0xF0FF) == 0x402B:
                    labels[load] = name            # a stub; callers load its VA
    return labels


def bsr_sites(exec_segs, target):
    out = []
    for base, b in exec_segs:
        for off in range(0, len(b) - 1, 2):
            w = b[off] | (b[off + 1] << 8)
            if (w >> 12) == 0xB:
                d = w & 0xFFF
                if d & 0x800:
                    d -= 0x1000
                if base + off + 4 + 2 * d == target:
                    out.append(base + off)
    return out


def census_image(img, image_start, resolve_with, only_module=None):
    """Rows per module, from each module's own import table (names come from
    the OriginalFirstThunk; no cross-image resolution is needed for OBJDLL
    because every importer names these two functions)."""
    with open(img, "rb") as fh:
        data = fh.read(128 << 20)
    r = cerom.CERom(data, image_start)
    out, scanned, importers = {}, 0, []
    for m in r.modules():
        name = m["name"]
        if only_module and name.lower() != only_module.lower():
            continue
        scanned += 1
        slots = {}
        for dll, slot, nm, _ordn in r.imports(m):
            if nm and dll.lower().startswith("objdll"):
                slots[real_slot(r, m, slot)] = nm
        if not any(v in APIS for v in slots.values()):
            continue
        importers.append(name)
        mem, exec_segs, _imports, _exports = sh4xref.load_module(
            img, image_start, name, resolve_with=resolve_with)
        labels = import_labels(mem, exec_segs, slots)
        stubs = {}
        for va, nm in labels.items():
            if nm in APIS:
                stubs.setdefault(nm, []).append(va)
        rows = census_module(mem, exec_segs, {k: sorted(v) for k, v in stubs.items()},
                             labels, getattr(mem, "fn_of", None))
        out[name] = rows
    return out, scanned, importers


def _cols(row):
    """(task column, sub column): setPrm(prm, task, sub, kind);
    setPrmForMP(prm, class, task, sub, kind-on-stack) (OBJDLL rva 0x13cc4)."""
    return ("r5", "r6") if row["api"] == "OBJ_Event_setPrm" else ("r6", "r7")


def _match(row, task, sub):
    tcol, scol = _cols(row)
    if task is not None and row[tcol] != "*0x%08x" % task:
        return False
    if sub is not None and row[scol] != "imm 0x%x" % sub:
        return False
    return True


def read_table(img, image_start, module, va, n):
    """N rows {u32 sub, u32 handler} at data VA `va` of `module`."""
    mem, _exec, _i, _e = sh4xref.load_module(img, image_start, module)
    return [(mem.u32(va + 8 * i), mem.u32(va + 8 * i + 4)) for i in range(n)]


def table_rows(table, every, task):
    """Per table row, the (module, row) subscriptions of `task` that name its sub."""
    return [(sub, handler, [(m, r) for m, r in every if _match(r, task, sub)])
            for sub, handler in table]


# --------------------------------------------------------------------------
# Self-test (synthetic code, no vendor bytes)
# --------------------------------------------------------------------------

def _synthetic():
    """Two subscriptions and a helper at 0x10000.

      F1 0x10004: r5 = *0x00020000, r6 = #100, r7 = #2, jsr stub(0x10100)
                  then jsr objcall(0x10110)
      F2 0x10040: r6 = #-57 extu.b (199), r5 = *0x00020004, jsr stub
      F3 0x10080: helper: mov r6,r5 ; mov r7,r6 ; jsr stub   (task/sub = args)
      F4 0x100C0: calls F3 with r6 = *0x00020008, r7 = #6
    """
    base = 0x10000
    b = bytearray(0x140)

    def put(va, w):
        struct.pack_into("<H", b, va - base, w)

    def lit(va, v):
        struct.pack_into("<I", b, va - base, v)

    def movl_pc(va, reg, pool):
        put(va, 0xD000 | (reg << 8) | ((pool - ((va + 4) & ~3)) // 4))

    put(0x10000, 0x000B); put(0x10002, 0x0009)
    # F1
    put(0x10004, 0x4F22)                      # sts.l pr,@-r15
    movl_pc(0x10006, 2, 0x10030)              # r2 = 0x00020000
    movl_pc(0x10008, 3, 0x10034)              # r3 = stub
    put(0x1000A, 0x6522)                      # mov.l @r2,r5
    put(0x1000C, 0xE702)                      # mov #2,r7
    put(0x1000E, 0xE664)                      # mov #100,r6
    put(0x10010, 0x430B)                      # jsr @r3
    put(0x10012, 0x6483)                      # mov r8,r4 (delay slot)
    movl_pc(0x10014, 3, 0x10038)              # r3 = object call
    put(0x10016, 0x430B); put(0x10018, 0x0009)
    put(0x1001A, 0x4F26); put(0x1001C, 0x000B); put(0x1001E, 0x0009)
    lit(0x10030, 0x00020000); lit(0x10034, 0x10100); lit(0x10038, 0x10110)
    # F2
    put(0x10040, 0x4F22)
    put(0x10042, 0xE6C7)                      # mov #-57,r6
    movl_pc(0x10044, 9, 0x10060)              # r9 = 0x00020004
    movl_pc(0x10046, 3, 0x10064)              # r3 = stub
    put(0x10048, 0x6592)                      # mov.l @r9,r5
    put(0x1004A, 0xE702)
    put(0x1004C, 0x666C)                      # extu.b r6,r6
    put(0x1004E, 0x430B); put(0x10050, 0x6483)
    put(0x10052, 0x4F26); put(0x10054, 0x000B); put(0x10056, 0x0009)
    lit(0x10060, 0x00020004); lit(0x10064, 0x10100)
    # F3 (helper)
    put(0x10080, 0x4F22)
    put(0x10082, 0x6563)                      # mov r6,r5
    movl_pc(0x10084, 3, 0x100A0)
    put(0x10086, 0x6673)                      # mov r7,r6
    put(0x10088, 0xE702)
    put(0x1008A, 0x430B); put(0x1008C, 0x0009)
    put(0x1008E, 0x4F26); put(0x10090, 0x000B); put(0x10092, 0x0009)
    lit(0x100A0, 0x10100)
    # F4: calls the helper F3 with task = *0x00020008, sub = 6
    put(0x100C0, 0x4F22)
    movl_pc(0x100C2, 2, 0x100E0)              # r2 = 0x00020008
    movl_pc(0x100C4, 3, 0x100E4)              # r3 = F3
    put(0x100C6, 0x6622)                      # mov.l @r2,r6
    put(0x100C8, 0x430B)                      # jsr @r3
    put(0x100CA, 0xE706)                      # mov #6,r7 (delay slot)
    put(0x100CC, 0x4F26); put(0x100CE, 0x000B); put(0x100D0, 0x0009)
    lit(0x100E0, 0x00020008); lit(0x100E4, 0x10080)
    # F5: one load into r13, two calls through it (subs 7 and 8, task = #1)
    put(0x100F0, 0x4F22)
    movl_pc(0x100F2, 13, 0x10114)             # r13 = stub
    put(0x100F4, 0xE501)                      # mov #1,r5
    put(0x100F6, 0x4D0B); put(0x100F8, 0xE607)   # jsr @r13 ; mov #7,r6
    put(0x100FA, 0x4D0B); put(0x100FC, 0xE608)   # jsr @r13 ; mov #8,r6
    put(0x100FE, 0x6DF6)                      # mov.l @r15+,r13
    lit(0x10114, 0x10100)
    seg = (base, bytes(b))
    return sh4dis.Mem([seg]), [seg]


def _stub_mem():
    """0x10000: mov.l @(pc),r0 ; mov.l @r0,r0 ; jmp @r0 ; nop ; slot literal
    0x30000 at 0x10008; 0x10010: bsr 0x10000."""
    base = 0x10000
    b = bytearray(0x20)
    struct.pack_into("<4H", b, 0, 0xD001, 0x6002, 0x402B, 0x0009)
    struct.pack_into("<I", b, 8, 0x30000)
    struct.pack_into("<H", b, 0x10, 0xB000 | (((0x10000 - 0x10014) // 2) & 0xFFF))
    seg = (base, bytes(b))
    return sh4dis.Mem([seg]), [seg]


def selftest() -> int:
    mem, exec_segs = _synthetic()
    labels = {0x10100: "OBJ_Event_setPrm", 0x10110: "OBJ_DiscInfo_setEventPublicDisc"}
    rows = census_module(mem, exec_segs, {"OBJ_Event_setPrm": [0x10100]}, labels)
    by = {r["jsr"]: r for r in rows}
    checks = [
        ("five call sites found", len({r["jsr"] for r in rows}) == 5),
        ("F5: both calls through the held register are sites",
         by[0x100F6]["r6"] == "imm 0x7" and by[0x100FA]["r6"] == "imm 0x8"),
        ("F1 task is a global", by[0x10010]["r5"] == "*0x00020000"),
        ("F1 sub is 100", by[0x10010]["r6"] == "imm 0x64"),
        ("F1 kind is 2", by[0x10010]["r7"] == "imm 0x2"),
        ("F1 object call named", by[0x10010]["object_call"] == "OBJ_DiscInfo_setEventPublicDisc"),
        ("F2 sub is 199 (mov #-57 + extu.b)", by[0x1004E]["r6"] == "imm 0xc7"),
        ("F2 task is the second global", by[0x1004E]["r5"] == "*0x00020004"),
        ("F3 (helper) task read at its caller F4", by[0x1008A]["r5"] == "*0x00020008"),
        ("F3 (helper) sub read at its caller F4", by[0x1008A]["r6"] == "imm 0x6"),
        ("F3 row names the caller's jsr", by[0x1008A].get("caller") == 0x100C8),
        ("filter task+sub finds F1", [r["jsr"] for r in rows if _match(r, 0x20000, 100)] == [0x10010]),
        ("import stub recognised from its slot",
         import_labels(*_stub_mem(), {0x30000: "OBJ_Event_setPrm"}).get(0x10000) == "OBJ_Event_setPrm"),
        ("bsr call to the stub found", bsr_sites(_stub_mem()[1], 0x10000) == [0x10010]),
        ("filter sub 11 finds nothing", not [r for r in rows if _match(r, 0x20000, 11)]),
        ("table row with a subscription names it; one without is empty",
         [len(x[2]) for x in table_rows([(100, 0x1), (11, 0x2)],
                                        [("m", r) for r in rows], 0x20000)] == [1, 0]),
        ("a stub nobody calls gives no row",
         census_module(mem, exec_segs, {"OBJ_Event_setPrm": [0x10120]}, labels) == []),
    ]
    failed = 0
    for name, ok in checks:
        print("  %-44s %s" % (name, "ok" if ok else "FAIL"))
        failed += 0 if ok else 1
    print("event_subs selftest: %d failed" % failed)
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("image", nargs="?")
    ap.add_argument("--image-start", type=lambda s: int(s, 0), default=0x200200)
    ap.add_argument("--resolve-with", type=lambda s: int(s, 0), action="append",
                    help="image start of another segment whose exports name ordinal imports")
    ap.add_argument("--module", help="one module instead of every module")
    ap.add_argument("--task", type=lambda s: int(s, 0), help="only rows whose task is *VA")
    ap.add_argument("--sub", type=lambda s: int(s, 0), help="only rows whose sub is this literal")
    ap.add_argument("--expect-site", type=lambda s: int(s, 0), action="append", default=[],
                    help="positive control: this jsr VA must be in the census")
    ap.add_argument("--handler-table", metavar="MODULE:VA:N",
                    help="with --task: read N rows {u32 sub, u32 handler} of the task's "
                         "event table and print, per row, the subscription that names it")
    ap.add_argument("--json")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.image:
        ap.error("IMG is required")
    rows_by_mod, scanned, importers = census_image(
        args.image, args.image_start, args.resolve_with, args.module)
    total = len({(m, r["jsr"]) for m, v in rows_by_mod.items() for r in v})
    all_jsr = {r["jsr"] for v in rows_by_mod.values() for r in v}
    missing = [s for s in args.expect_site if s not in all_jsr]
    shown = 0
    unresolved = 0
    for mod, rows in rows_by_mod.items():
        for r in rows:
            tcol, scol = _cols(r)
            if (r[tcol] in ("?", "deref?", "mem") or r[scol] in ("?", "deref?", "mem")
                    or r[tcol].startswith("arg") or r[scol].startswith("arg")):
                unresolved += 1
            if not _match(r, args.task, args.sub):
                continue
            shown += 1
            print("%-14s fn %s jsr 0x%08x %-22s r5=%-12s r6=%-10s r7=%-10s %s%s" % (
                mod, "0x%08x" % r["fn"] if r["fn"] is not None else "?",
                r["jsr"], r["api"], r["r5"], r["r6"], r["r7"], r["object_call"] or "-",
                "  (helper called at 0x%08x)" % r["caller"] if r.get("caller") else ""))
    print("modules read: %d; modules importing %s: %d (%s)" % (
        scanned, "/".join(APIS), len(importers),
        ", ".join("%s %d" % (m, len({r["jsr"] for r in v})) for m, v in rows_by_mod.items())))
    print("call sites: %d; rows with an unresolved task or sub: %d; shown: %d" % (
        total, unresolved, shown))
    for s in args.expect_site:
        print("positive control 0x%08x: %s" % (s, "MISSING" if s in missing else "found"))
    if args.handler_table:
        if args.task is None:
            ap.error("--handler-table needs --task")
        mod, va, n = args.handler_table.split(":")
        table = read_table(args.image, args.image_start, mod, int(va, 0), int(n, 0))
        every = [(m, r) for m, v in rows_by_mod.items() for r in v]
        for sub, handler, sites in table_rows(table, every, args.task):
            print("table sub %-4d handler 0x%08x  %s" % (
                sub, handler,
                ", ".join("%s 0x%08x %s" % (m, r["jsr"], r["object_call"] or "-")
                          for m, r in sites) or "NO SUBSCRIPTION"))
    if args.json:
        doc = {"schema": "osm2leaf.event_subs/v1", "image": Path(args.image).name,
               "image_start": "0x%x" % args.image_start,
               "modules_read": scanned, "importers": importers, "call_sites": total,
               "unresolved": unresolved,
               "rows": [dict(r, module=m, jsr="0x%08x" % r["jsr"],
                             fn="0x%08x" % r["fn"] if r["fn"] is not None else None)
                        for m, v in rows_by_mod.items() for r in v]}
        for r in doc["rows"]:
            if r.get("caller"):
                r["caller"] = "0x%08x" % r["caller"]
        Path(args.json).write_text(json.dumps(doc, indent=1) + "\n")
    if missing:
        return 2
    if (args.task is not None or args.sub is not None) and not shown:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
