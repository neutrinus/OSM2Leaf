#!/usr/bin/env python3
"""Find who signals and who waits for an ACM module id (M1.35).

``AppLaunch.dll`` (build B) orders the boot with numbered ids on the
``ACM9:`` driver: a record waits with IOCTL_ACM_WAIT_ID ``0x80002004`` and the
module that is up signals with IOCTL_ACM_SET_ID ``0x80002000`` (M1.34).  Other
modules do the same through two ``commondll.dll`` exports:

* ``CApi_ModuleInitializeComplete(id, ...)`` -> ``fn 0x03c08c40``, which loads
  ``0x80002000`` (SET_ID, EU2011 build B);
* ``CApi_WaitModuleInitialize(id, timeout)`` -> ``0x80002004`` (WAIT_ID).

The scan walks every module of one or more CE images and lists each call that
passes an id in ``r4``:

1. **import calls** - a call through an import thunk or IAT slot named
   ``CApi_ModuleInitializeComplete`` (``set``) or ``CApi_WaitModuleInitialize``
   (``wait``): ``bsr THUNK``, ``mov.l @(pc),Rn = THUNK; jsr @Rn``, or
   ``mov.l @(pc),Rn = SLOT; mov.l @Rn,Rm; jsr @Rm``;
2. **local wrappers** - a function of the module that itself loads the literal
   ``0x80002000`` (``set``) or ``0x80002004`` (``wait``) is a wrapper; each
   ``bsr`` / literal ``jsr`` to it is a call.

For every call the id is the value of ``r4`` at the call, found by walking
back (the delay slot first) to the last write of ``r4``: ``mov #imm,r4``,
``mov.w @(pc),r4``, ``mov.l @(pc),r4``, ``add #imm,r4`` (accumulated) or
``mov Rm,r4`` (followed once to ``Rm``).  Anything else, a branch target or a
call in between ends the walk with ``?``: the id is then not static.

Usage:
  acm_id_scan.py --selftest
  acm_id_scan.py IMG [--image-start 0x3e00200 ...] [--id 94] [--all]
                 [--resolve-with 0x3e00200]

Default image starts: A ``0x200200``, B ``0x3e00200``, C ``0x5200200``.
Without ``--all`` only calls whose id is ``--id`` (or not static) are printed;
the summary line counts every call.  Stdlib only; sections, imports and
exports come from ``tools/cerom.py``.
Method and the EU2011/US2011 runs:
docs/experiments/EXP-2026-11-20-M1.35-sdc1-ioctl-wait94.md
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cerom  # noqa: E402
import pdata  # noqa: E402
from sh4dis import Mem, bsr_target, jsr_reg, movl_pc_target  # noqa: E402

SET_ID = 0x80002000
WAIT_ID = 0x80002004
IMPORT_KIND = {"CApi_ModuleInitializeComplete": "set",
               "CApi_WaitModuleInitialize": "wait"}
THUNK_SHAPE = (0xd001, 0x6002, 0x402b, 0x0009)
CALL_WINDOW = 12
BACK_WINDOW = 24
DEFAULT_STARTS = (0x200200, 0x3e00200, 0x5200200)


# ------------------------------------------------------------ r4 back-walk

def _s8(x):
    return x - 0x100 if x & 0x80 else x


def _writes(w, reg):
    """Classify instruction ``w`` as a write of ``reg``: returns
    (kind, operand) or None when it does not write ``reg``."""
    n = (w >> 8) & 15
    m = (w >> 4) & 15
    hi = w & 0xf000
    if hi == 0xe000 and n == reg:
        return "imm", _s8(w & 0xff)
    if hi == 0x9000 and n == reg:
        return "movw", w & 0xff
    if hi == 0xd000 and n == reg:
        return "movl", w & 0xff
    if hi == 0x7000 and n == reg:
        return "add", _s8(w & 0xff)
    if hi == 0x6000 and n == reg:
        if w & 0xf == 3:
            return "mov", m
        if w & 0xf in (0xc, 0xd):
            return ("extu.b" if w & 0xf == 0xc else "extu.w"), m
        return "other", None
    # generic writes of Rn we do not model: arithmetic/logic 3nmX, 2nmX ops
    # that write Rn, shifts 4nXX, loads 5nmd, 8xxx with r0, cXXX with r0.
    if n == reg and hi in (0x3000, 0x5000):
        return "other", None
    if n == reg and hi == 0x2000 and (w & 0xf) in (0x9, 0xa, 0xb, 0xd, 0xe, 0xf):
        return "other", None
    if n == reg and hi == 0x4000 and (w & 0xff) in (0x00, 0x01, 0x04, 0x05, 0x08, 0x09,
                                                     0x10, 0x18, 0x19, 0x20, 0x21,
                                                     0x24, 0x25, 0x28, 0x29):
        return "other", None
    if n == reg and hi == 0x0000 and (w & 0xf) in (0x2, 0x9, 0xa, 0xc, 0xd, 0xe):
        return "other", None
    if reg == 0 and hi in (0x8000, 0xc000) and (w >> 8) in (0x84, 0x85, 0xc4, 0xc5,
                                                            0xc6, 0xc7, 0xc9, 0xcb, 0xcd, 0xcf, 0x88):
        return ("other", None) if (w >> 8) != 0x88 else None
    return None


def _ends_block(w):
    """A call, return or branch before the call site ends the back-walk."""
    if w is None:
        return True
    if jsr_reg(w) or w == 0x000b or w & 0xf000 in (0xa000, 0xb000):
        return True
    if w & 0xff00 in (0x8900, 0x8b00, 0x8d00, 0x8f00):   # bt/bf(/s)
        return True
    if w & 0xf0ff in (0x0023, 0x0003):                    # braf/bsrf
        return True
    return False


def value_of(mem, call_va, reg=4, depth=0, start=None):
    """Static value of ``reg`` at ``call_va`` (the ``jsr``/``bsr``), or None.

    The delay slot (``call_va + 2``) executes before the callee and is checked
    first; then the walk goes back from the instruction before the call.
    ``add #imm`` and ``extu.b``/``extu.w`` met on the way are applied, in
    program order, to the value found at the end of the walk."""
    ops = []            # collected backwards
    order = []
    if start is None:
        order.append(call_va + 2)
        a = call_va - 2
    else:
        a = start
    for _ in range(BACK_WINDOW):
        order.append(a)
        a -= 2

    def finish(v):
        if v is None:
            return None
        for op, k in reversed(ops):
            if op == "add":
                v = v + k
            elif op == "extu.b":
                v &= 0xff
            elif op == "extu.w":
                v &= 0xffff
        return v & 0xffffffff

    for k, a in enumerate(order):
        w = mem.u16(a)
        if w is None:
            return None
        if k > 0 and _ends_block(w):
            return None
        hit = _writes(w, reg)
        if hit is None:
            continue
        kind, op = hit
        if kind == "imm":
            return finish(op)
        if kind == "movw":
            v = mem.u16(a + 4 + op * 2)
            if v is None:
                return None
            return finish(v - 0x10000 if v & 0x8000 else v)
        if kind == "movl":
            return finish(mem.u32(((a + 4) & ~3) + op * 4))
        if kind == "add":
            ops.append(("add", op))
            continue
        if kind in ("extu.b", "extu.w"):
            ops.append((kind, 0))
            if op == reg:
                continue
            kind = "mov"
        if kind == "mov" and depth == 0:
            return finish(value_of(mem, call_va, reg=op, depth=1, start=a - 2))
        return None
    return None


def has_imm(mem, lo, hi, value):
    """True if a ``mov #value,Rn`` (or ``mov #value-256,Rn`` + extu.b) word
    lies in [lo, hi): a weak hint that a dynamic id may be ``value``."""
    for a in range(lo, hi, 2):
        w = mem.u16(a)
        if w is None or w & 0xf000 != 0xe000:
            continue
        if value <= 0xff and w & 0xff == value:
            return True
    return False


# ------------------------------------------------------------ module model

class Module:
    def __init__(self, name, segs, exec_segs, thunks, slots, fn_ranges=None):
        self.name = name
        self.mem = Mem(segs)
        self.exec_segs = exec_segs
        self.thunks = thunks        # thunk VA -> "dll!name"
        self.slots = slots          # IAT slot VA -> "dll!name"
        self.fn_ranges = fn_ranges or []


def load_modules(data, image_start, resolve_with=()):
    rom = cerom.CERom(data, image_start)
    ex_tables, mod_names = cerom.load_resolver_tables(data, list(resolve_with))
    for m in rom.modules():
        try:
            secs = list(rom.o32(m))
            vbase = rom.e32(m)["vbase"]
            imports = list(rom.imports(m))
        except Exception:
            continue
        segs, exec_segs = [], []
        for s in secs:
            if s["flags"] & cerom.IMAGE_SCN_COMPRESSED:
                continue
            try:
                off = rom.va2file(s["dataptr"])
            except Exception:
                continue
            blob = data[off:off + s["psize"]]
            segs.append((s["realaddr"], blob))
            if s["flags"] & cerom.MEM_EXECUTE:
                exec_segs.append((s["realaddr"], blob))
        if not exec_segs:
            continue
        # import slot VA (process VA, vbase + rva) -> realaddr of the IAT slot
        slots = {}
        for dll, oft, nm, ordn in imports:
            sym, _ok, _n = cerom.resolve_import_entry(dll, nm, ordn, ex_tables, mod_names)
            for d in secs:
                lo = vbase + d["rva"]
                if lo <= oft < lo + max(d["vsize"], 1):
                    slots[d["realaddr"] + oft - lo] = sym
        mem = Mem(segs)
        thunks = {}
        for base, blob in exec_segs:
            for off in range(0, len(blob) - 12, 2):
                if struct.unpack_from("<4H", blob, off) != THUNK_SHAPE:
                    continue
                pc = base + off
                slot = mem.u32(((pc + 4) & ~3) + 4)
                if slot in slots:
                    thunks[pc] = slots[slot]
        yield Module(m["name"], segs, exec_segs, thunks, slots)


def _kind_of_symbol(sym):
    for k, v in IMPORT_KIND.items():
        if sym and sym.endswith("!" + k):
            return v
    return None


def _fn_start(mem, va):
    """Nearest preceding ``sts.l pr,@-r15`` block start (prologue heuristic,
    used only to label wrappers; pdata is checked separately in the EXP)."""
    a = va
    for _ in range(2048):
        a -= 2
        w = mem.u16(a)
        if w is None:
            return None
        if w in (0x000b,) and mem.u16(a + 2) is not None:
            # rts + delay slot ends the previous function
            b = a + 4
            while mem.u16(b) == 0x0009:
                b += 2
            if b <= va:
                return b
    return None


def wrappers(mod):
    """{fn VA: kind} for local functions that load the SET/WAIT literal into
    ``r5``, the ``dwIoControlCode`` argument of ``DeviceIoControl``.  A load
    into another register is a compare (the ``ACM9:`` driver's own
    ``ACM_IOControl``) or an address constant (``nk.exe`` uses ``0x80002000``
    as a P1 address), not a request."""
    out = {}
    for base, blob in mod.exec_segs:
        for val, kind in ((SET_ID, "set"), (WAIT_ID, "wait")):
            needle = struct.pack("<I", val)
            i = blob.find(needle)
            while i >= 0:
                if (base + i) % 4 == 0:
                    lit = base + i
                    for a in range(max(base, lit - 1024), lit, 2):
                        t = movl_pc_target(a, mod.mem.u16(a))
                        if t and t[1] == lit and t[0] == 5:
                            fn_of = getattr(mod.mem, "fn_of", None)
                            fn = fn_of(a) if fn_of else None
                            if fn is None:
                                fn = _fn_start(mod.mem, a)
                            if fn is not None:
                                out[fn] = kind
                i = blob.find(needle, i + 1)
    return out


def call_sites(mod, targets, slot_targets):
    """Yield (call VA, kind, how) for calls to ``targets`` {VA: kind} (bsr or a
    literal ``jsr``) and through ``slot_targets`` {slot VA: kind}."""
    for base, blob in mod.exec_segs:
        for off in range(0, len(blob) - 1, 2):
            a = base + off
            w = struct.unpack_from("<H", blob, off)[0]
            t = bsr_target(a, w)
            if t is not None and t in targets:
                yield a, targets[t], "bsr 0x%08x" % t
                continue
            ml = movl_pc_target(a, w)
            if not ml:
                continue
            reg, lit = ml
            v = mod.mem.u32(lit)
            if v is None:
                continue
            if v in targets:
                for k in range(1, CALL_WINDOW + 1):
                    w2 = mod.mem.u16(a + 2 * k)
                    j = jsr_reg(w2)
                    if j and j[0] == "jsr" and j[1] == reg:
                        yield a + 2 * k, targets[v], "jsr 0x%08x" % v
                        break
                    if w2 is None or _ends_block(w2) or _writes(w2, reg):
                        break
            elif v in slot_targets:
                for k in range(1, CALL_WINDOW + 1):
                    w2 = mod.mem.u16(a + 2 * k)
                    if w2 is not None and w2 & 0xf00f == 0x6002 and (w2 >> 4) & 15 == reg:
                        r2 = (w2 >> 8) & 15
                        for k2 in range(k + 1, k + CALL_WINDOW):
                            j = jsr_reg(mod.mem.u16(a + 2 * k2))
                            if j and j[0] == "jsr" and j[1] == r2:
                                yield a + 2 * k2, slot_targets[v], "jsr @slot 0x%08x" % v
                                break
                        break


def scan_module(mod, want=None):
    """List of dicts {module, call, kind, id, via}."""
    targets = {}
    for va, sym in mod.thunks.items():
        k = _kind_of_symbol(sym)
        if k:
            targets[va] = k
    slot_targets = {}
    for va, sym in mod.slots.items():
        k = _kind_of_symbol(sym)
        if k:
            slot_targets[va] = k
    local = wrappers(mod)
    targets.update(local)
    out = []
    if not targets and not slot_targets:
        return out, local
    for call, kind, how in call_sites(mod, targets, slot_targets):
        v = value_of(mod.mem, call)
        hint = False
        if v is None and want is not None:
            fn_of = getattr(mod.mem, "fn_of", None)
            lo = (fn_of(call) if fn_of else None) or _fn_start(mod.mem, call) or call - 0x200
            hint = has_imm(mod.mem, lo, call + 4, want)
        out.append(dict(module=mod.name, call=call, kind=kind, id=v, via=how,
                        hint=hint))
    return out, local


def run_scan(data, starts, resolve_with, want=None, corpus=None):
    rows, wraps = [], []
    for st in starts:
        for mod in load_modules(data, st, resolve_with):
            if corpus is not None:
                corpus[0] += 1
                corpus[1] += sum(len(b) for _a, b in mod.exec_segs)
            if mod.slots and any(_kind_of_symbol(x) for x in mod.slots.values()) or any(
                    struct.pack("<I", v) in blob for _b, blob in mod.exec_segs
                    for v in (SET_ID, WAIT_ID)):
                try:
                    pdata.attach_fn_of_from_image(mod.mem, data, st, mod.name)
                except Exception:
                    pass
            r, local = scan_module(mod, want)
            for row in r:
                row["image_start"] = st
            rows.extend(r)
            for fn, kind in sorted(local.items()):
                wraps.append((st, mod.name, fn, kind))
    return rows, wraps


def fmt_row(r):
    idv = "?" if r["id"] is None else "%d" % r["id"] if r["id"] < 0x10000 else "0x%08x" % r["id"]
    return "0x%07x %-24s 0x%08x %-4s id=%-5s %s%s" % (
        r["image_start"], r["module"], r["call"], r["kind"], idv, r["via"],
        "  [fn has mov #id]" if r.get("hint") else "")


# ------------------------------------------------------------ selftest

def _synthetic_module():
    """A fake module: thunk to CApi_ModuleInitializeComplete at 0x1000, a
    local SET_ID wrapper at 0x1100, and callers with static and dynamic ids."""
    base = 0x1000
    blob = bytearray(0x400)

    def put(va, *words):
        for i, w in enumerate(words):
            struct.pack_into("<H", blob, va - base + 2 * i, w)

    def lit(va, v):
        struct.pack_into("<I", blob, va - base, v)

    # thunk at 0x1000: mov.l @(4,pc),r0; mov.l @r0,r0; jmp @r0; nop; .long slot
    put(0x1000, *THUNK_SHAPE)
    lit(0x1008, 0x2000)
    # wrapper at 0x1100 (after an rts at 0x10fc): mov.l @(lit),r5 = SET_ID; rts
    # and a compare at 0x1140 (mov.l @(lit),r3 = SET_ID): not a wrapper
    put(0x113c, 0x000b, 0x0009)
    put(0x1140, 0xd300, 0x0009)                    # lit at 0x1144
    lit(0x1144, SET_ID)
    put(0x10fc, 0x000b, 0x0009)
    put(0x1100, 0xd501, 0x000b, 0x0009, 0x0009)   # lit at ((0x1100+4)&~3)+4 = 0x1108
    lit(0x1108, SET_ID)
    # caller 1 at 0x1200: mov #94,r4 ; bsr 0x1000 ; nop        -> set id 94
    put(0x1200, 0xe45e, 0xb000 | ((0x1000 - 0x1206) // 2 & 0xfff), 0x0009)
    # caller 2 at 0x1210: mov r9,r4 ; mov.l @(lit),r3 ; jsr @r3 ; add #82,r4 -> ? (dynamic)
    put(0x1210, 0x6493, 0xd303, 0x430b, 0x7452)   # lit at ((0x1212+4)&~3)+12 = 0x1220
    lit(0x1220, 0x1100)
    # caller 3 at 0x1230: mov #40,r8 ; mov r8,r4 ; bsr 0x1100 ; add #2,r4 -> set id 42
    put(0x1230, 0xe828, 0x6483, 0xb000 | ((0x1100 - 0x1238) // 2 & 0xfff), 0x7402)
    # caller 4 at 0x1240: mov #94,r4 ; bt 0x1250 ; bsr 0x1000 ; nop -> ? (branch between)
    put(0x1240, 0xe45e, 0x8906, 0xb000 | ((0x1000 - 0x1248) // 2 & 0xfff), 0x0009)
    # caller 5 at 0x1260: mov.w @(lit),r4 = 300 ; bsr 0x1000 ; nop -> set id 300
    put(0x1260, 0x9402, 0xb000 | ((0x1000 - 0x1266) // 2 & 0xfff), 0x0009)
    put(0x1268, 300)                               # mov.w lit at 0x1260+4+2*2
    # caller 6 at 0x1270: mov #-122,r4 ; mov.l @(lit),r3 = slot ; mov.l @r3,r3 ;
    #                     extu.b r4,r4 ; jsr @r3 ; mov #1,r5      -> set id 134
    put(0x1270, 0xe486, 0xd303, 0x6332, 0x644c, 0x430b, 0xe501)  # lit 0x1280
    lit(0x1280, 0x2000)
    # caller 7 at 0x1290: mov.l @(lit),r3 = wrapper ; bra +2 ; mov.l @(lit),r3 = other ;
    #                     jsr @r3 -> the wrapper literal is overwritten: no call
    put(0x1290, 0xd303, 0xa000, 0xd303, 0x430b, 0x0009)          # lits 0x129c/0x12a0
    lit(0x129c, 0x1100)
    lit(0x12a0, 0x1300)
    put(0x120a, 0x000b, 0x0009)                    # function ends before caller 2
    put(0x12a8, 0x000b, 0x0009)                    # function ends before caller 8
    # caller 8 at 0x12b0: mov #94,r3 ; mov.l r3,@(16,r15) ; ... ; mov.l @r10+,r4 ;
    #                     bsr wrapper (id from a stack array: dynamic, hinted)
    put(0x12b0, 0xe35e, 0x1f34, 0xb000 | ((0x1100 - 0x12b8) // 2 & 0xfff), 0x64a6)
    segs = [(base, bytes(blob))]
    return Module("SYNTH.dll", segs, segs, {0x1000: "commondll.dll!CApi_ModuleInitializeComplete"},
                  {0x2000: "commondll.dll!CApi_ModuleInitializeComplete"})


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + name)
        ok = ok and cond

    mod = _synthetic_module()
    rows, local = scan_module(mod)
    got = {r["call"]: (r["kind"], r["id"]) for r in rows}
    check("local SET_ID wrapper found at 0x1100; the r3 compare at 0x1140 is not one",
          local == {0x1100: "set"})
    check("bsr to the import thunk with mov #94,r4 -> set id 94",
          got.get(0x1202) == ("set", 94))
    check("literal jsr to the wrapper, r4 = r9 + 82 -> id not static",
          got.get(0x1214) == ("set", None))
    check("mov r8,r4 followed to mov #40,r8 plus add #2 in the delay slot -> 42",
          got.get(0x1234) == ("set", 42))
    check("negative: a branch between the id load and the call -> not static",
          got.get(0x1244) == ("set", None))
    check("mov.w literal id 300", got.get(0x1262) == ("set", 300))
    check("mov #-122,r4 + extu.b r4,r4 through the IAT slot -> 134",
          got.get(0x1278) == ("set", 134))
    check("negative: a literal overwritten before the jsr is no call",
          0x1296 not in got)
    check("exactly seven call sites", len(rows) == 7)
    rows_h, _ = scan_module(_synthetic_module(), want=94)
    hint = {r["call"]: r["hint"] for r in rows_h}
    check("dynamic id from a stack array is hinted when the fn holds mov #94",
          hint.get(0x12b4) is True and hint.get(0x1214) is False)
    # negative control: rename the import -> the thunk is no longer a target
    mod2 = _synthetic_module()
    mod2.thunks = {0x1000: "commondll.dll!CApi_GetBootMode"}
    mod2.slots = {}
    rows2, _ = scan_module(mod2)
    check("negative: an unrelated import gives no thunk calls",
          all(r["call"] in (0x1214, 0x1234, 0x12b4) for r in rows2) and len(rows2) == 3)
    print("selftest: %s" % ("OK" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if "--selftest" in argv:
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("image")
    ap.add_argument("--image-start", type=lambda s: int(s, 0), action="append")
    ap.add_argument("--resolve-with", type=lambda s: int(s, 0), action="append",
                    default=None, help="extra CE images whose exports name ordinals "
                    "(default: 0x3e00200, which holds commondll.dll)")
    ap.add_argument("--id", type=int, default=94)
    ap.add_argument("--all", action="store_true", help="print every call, not only --id")
    a = ap.parse_args(argv)
    starts = a.image_start or list(DEFAULT_STARTS)
    resolve = a.resolve_with if a.resolve_with is not None else [0x3e00200]
    with open(a.image, "rb") as fh:
        data = fh.read(128 << 20)
    corpus = [0, 0]
    rows, wraps = run_scan(data, starts, resolve, a.id, corpus)
    print("corpus: %d modules with executable sections, %d bytes, image starts %s"
          % (corpus[0], corpus[1], " ".join("0x%x" % x for x in starts)))
    for st, name, fn, kind in wraps:
        print("wrapper 0x%07x %-24s fn 0x%08x %s" % (st, name, fn, kind))
    shown = 0
    for r in sorted(rows, key=lambda r: (r["image_start"], r["module"], r["call"])):
        if a.all or r["id"] is None or r["id"] == a.id:
            print(fmt_row(r))
            shown += 1
    n_set = sum(1 for r in rows if r["kind"] == "set")
    n_wait = sum(1 for r in rows if r["kind"] == "wait")
    n_static = sum(1 for r in rows if r["id"] is not None)
    hit_set = sum(1 for r in rows if r["kind"] == "set" and r["id"] == a.id)
    hit_wait = sum(1 for r in rows if r["kind"] == "wait" and r["id"] == a.id)
    mods = sorted({r["module"] for r in rows})
    n_hint = sum(1 for r in rows if r.get("hint"))
    print("summary: %d calls (%d set, %d wait) in %d modules, %d static ids; "
          "id %d: %d set, %d wait static, %d dynamic calls with mov #%d in the "
          "function" % (len(rows), n_set, n_wait, len(mods), n_static,
                        a.id, hit_set, hit_wait, n_hint, a.id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
