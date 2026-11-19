#!/usr/bin/env python3
"""Run the writer of the BSS slot table ``0x00d53500`` in PySh4 (M3.22).

``0x00d53500`` (EU2011; ``0x00c81100`` US2011) is BSS in ``Navi.exe`` sec1:
zero at load, filled at run time.  The POINT dispatcher ``fn 0x003f5cdc``
(EU2011) compares its page argument with the table's slots and calls the
reader that belongs to the slot that matched (M9.38: slot ``+0x1c`` ->
walker ``0x003f5194``).  M9.38's ``above`` run wrote that slot **by hand**.
This tool lets the firmware write it instead, then hands the table the
writer produced to the real dispatcher on a decoded factory page.

Commands (all on real bytes except ``--selftest``):

``cases IMG --build B``
    Decode the message switch that calls the populate writers
    (``fn 0x003ff6a0`` EU2011 / ``0x0042780c`` US2011): message type
    ``@(ctx+104)`` minus ``0x14cc`` indexes a byte table, ``braf`` jumps, and
    each case loads its callee from the literal pool.  Prints type -> callee.

``writer IMG --cmp C --ind I --build B``
    Call the populate writer (``fn 0x003faf04`` EU2011 / ``0x00423ba8``
    US2011) with a context of message type ``0x14ef``.  All compressed
    sections are mapped zero-filled (BSS = zero at load).  Declared inputs:
    the page-object global the type leaf (``0x0040e858`` / ``0x004368b0``)
    returns -- found by **running** that leaf, not typed in -- gets
    ``+0 = OBJ`` and ``+16 = 1``; ``OBJ+20 = PAGE`` (the decoded, swapped
    factory POINT page).  A write watch on the table records every slot the
    writer stores.  Then the dispatcher runs on ``PAGE`` with the table the
    writer left (no hand write) and the walker returns record ``n``'s offset.
    Controls: the same run with type ``0x14f0`` (the writer's other branch)
    must leave ``+0x1c`` zero, and the dispatcher must then not reach the
    walker's page read through ``+0x1c``.

``slots IMG --build B [--sites]``
    Static census of the table's slots: from every ``sh4xref --to TABLE``
    load site, follow the code (both branch arms, delay slots, ``jsr`` kills
    r0-r7) with a register tracker for "table + k" and small constants, and
    record every load/store through ``@(disp,Rn)``, ``@Rn``, ``@(r0,Rn)``.
    Prints, per slot offset, width, reads, writes and the writing functions.
    A tracker, not an emulator: it can miss an access whose base passes
    through memory, and it never invents one (selftest).

Usage::

  d53500_writer.py --selftest
  d53500_writer.py cases archive/head256.img --build eu2011
  d53500_writer.py writer archive/head256.img --cmp C --ind I --build eu2011
  d53500_writer.py slots archive/head256.img --build eu2011

Method and results: docs/experiments/EXP-2026-11-19-M3.22-d53500-writer-l3.md
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "l3_harness")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import point_walk_l3 as pw  # noqa: E402
from engine import PySh4  # noqa: E402

IMAGE_START = 0x200200
MODULE = "Navi.exe"

PAGE_VA = 0x20000000
OBJ_VA = 0x21000000
CTX_VA = 0x22000000
STACK_VA = 0x30000000
STACK_SIZE = 0x4000
TABLE_SPAN = 0x100          # bytes of the table watched / dumped
CTX_TYPE = 104              # @(ctx+104): message type the writers switch on
TYPE_POINT = 0x14EF          # the writer branch that stores slot +0x1c
TYPE_OTHER = 0x14F0          # the other branch (negative control)
POINT_SLOT = 0x1C

#: Per-build addresses (EU2011 = head256 ``92aa525d…``, US2011 = us256
#: ``70d945d8…``).  ``check`` entries are verified against the image before
#: any run: a wrong build is a loud error, never a silent result.
BUILDS = {
    "eu2011": {
        "table": 0x00D53500,
        "writer": 0x003FAF04,           # pdata START, len 0x19e
        "store_pc": 0x003FB034,         # mov.l r2,@(28,r9)
        "type_leaf": 0x0040E858,        # ctx type -> page-object global
        "dispatch": 0x003F5CDC,
        "walker": 0x003F5194,
        "switch": {"fn": 0x003FF6A0, "braf": 0x003FF6E0, "jt": 0x001793F8,
                   "jt_pool": 0x003FF774, "base": 0x14CC, "cases": 37,
                   "default": 0x003FF734},
        "page": 0x6E06D0, "page_len": 97158,
    },
    "us2011": {
        "table": 0x00C81100,
        "writer": 0x00423BA8,           # pdata START, len 0x19e
        "store_pc": 0x00423CD8,
        "type_leaf": 0x004368B0,
        "dispatch": 0x0041E63C,
        "walker": 0x0041DB44,
        "switch": {"fn": 0x0042780C, "braf": 0x0042784C, "jt": 0x0015FDD0,
                   "jt_pool": 0x004278E0, "base": 0x14CC, "cases": 37,
                   "default": 0x004278A0},
        "page": 0x840BA0, "page_len": 42848,
    },
}


class Mismatch(SystemExit):
    pass


# ---------------------------------------------------------------------------
# image helpers


def sec0_mem(data: bytes):
    from sh4dis import Mem
    _, secs = pw.module_sections(data, IMAGE_START, MODULE)
    return Mem([(s["realaddr"], blob) for s, comp, blob in secs
                if not comp and blob is not None])


def switch_cases(mem_u8, mem_u16, mem_u32, sw: dict) -> list[tuple[int, int | None]]:
    """(message type, callee VA or None) for every case of the switch.

    ``braf r0`` at ``sw['braf']`` jumps to ``braf + 4 + sext8(jt[type-base])``;
    a case that calls a writer starts with ``mov.l @(disp,pc),r3`` (``d3dd``)
    whose pool word is the callee.  The switch's own out-of-range target
    (``sw['default']``, the common tail) and any other first instruction
    -> None.
    """
    if mem_u16(sw["braf"]) != 0x0023:
        raise Mismatch(f"no braf r0 at {sw['braf']:#010x}: wrong build?")
    if mem_u32(sw["jt_pool"]) != sw["jt"]:
        raise Mismatch(f"pool {sw['jt_pool']:#010x} does not hold the jump "
                       f"table {sw['jt']:#010x}: wrong build?")
    out = []
    for idx in range(sw["cases"]):
        b = mem_u8(sw["jt"] + idx)
        b = b - 0x100 if b & 0x80 else b
        tgt = sw["braf"] + 4 + b
        op = mem_u16(tgt)
        callee = None
        if tgt == sw.get("default"):
            out.append((sw["base"] + idx, None))
            continue
        if op & 0xFF00 == 0xD300:
            pool = ((tgt + 4) & ~3) + (op & 0xFF) * 4
            callee = mem_u32(pool)
        out.append((sw["base"] + idx, callee))
    return out


def map_module(eng: PySh4, data: bytes) -> list[tuple[int, int]]:
    """Map sec0 (code + rodata) and every compressed section zero-filled."""
    _, secs = pw.module_sections(data, IMAGE_START, MODULE)
    zero = []
    for s, comp, blob in secs:
        if comp:
            eng.map("sec@%08x" % s["realaddr"], s["realaddr"],
                    bytearray(s["vsize"]), "rw")
            zero.append((s["realaddr"], s["realaddr"] + s["vsize"]))
        elif blob is not None:
            eng.map("sec@%08x" % s["realaddr"], s["realaddr"],
                    bytearray(blob) + bytearray(max(0, s["vsize"] - len(blob))),
                    "rx" if s["flags"] & pw.EXEC else "rw")
    return zero


def u32(eng: PySh4, va: int) -> int:
    return struct.unpack("<I", eng.read_mem(va, 4))[0]


def put32(eng: PySh4, va: int, value: int) -> None:
    eng.write_mem(va, struct.pack("<I", value & 0xFFFFFFFF))


def slot_writes(eng: PySh4, table: int, span: int = TABLE_SPAN):
    """[(pc, offset, size, value now)] for every guest store into the table."""
    rows = []
    for h in eng.watch_hits():
        if h.kind != "w" or not table <= h.va < table + span:
            continue
        off = h.va - table
        raw = eng.read_mem(h.va, h.size)
        val = int.from_bytes(raw, "little")
        rows.append((h.pc, off, h.size, val))
    return rows


# ---------------------------------------------------------------------------
# the writer run


def new_engine(data: bytes) -> PySh4:
    eng = PySh4(endian="little")
    map_module(eng, data)
    eng.map("stack", STACK_VA, bytearray(STACK_SIZE), "rw")
    eng.set_regs(r15=STACK_VA + STACK_SIZE - 0x100)
    return eng


def type_global(data: bytes, cfg: dict, msg_type: int) -> int:
    """Run the type leaf on a context of *msg_type*; it returns the global."""
    eng = new_engine(data)
    eng.map("ctx", CTX_VA, bytearray(0x200), "rw")
    put32(eng, CTX_VA + CTX_TYPE, msg_type)
    return eng.call(cfg["type_leaf"], [CTX_VA])


def run_writer(data: bytes, cfg: dict, native_page: bytes, msg_type: int,
               n: int = 1) -> dict:
    """Writer then dispatcher, in one engine; returns the observations."""
    glob = type_global(data, cfg, msg_type)
    eng = new_engine(data)
    eng.map("ctx", CTX_VA, bytearray(0x200), "rw")
    eng.map("obj", OBJ_VA, bytearray(0x100), "rw")
    eng.map("page", PAGE_VA, bytearray(native_page) + bytearray(0x40), "rw")
    put32(eng, CTX_VA + CTX_TYPE, msg_type)
    # declared inputs: the page object the type leaf names, and its buffer
    put32(eng, glob + 0, OBJ_VA)
    put32(eng, glob + 16, 1)
    put32(eng, OBJ_VA + 20, PAGE_VA)
    msg = STACK_VA + 0x100
    table = cfg["table"]
    eng.watch(table, table + TABLE_SPAN, kind="w", name="table-w")
    eng.watch(msg, msg + 0x20, kind="w", name="msg-w")
    eng.arm_watch()
    fault = None
    try:
        eng.call(cfg["writer"], [0, CTX_VA, 0, msg])
    except Exception as exc:  # noqa: BLE001
        fault = exc
    writes = slot_writes(eng, table)
    msg_words = [u32(eng, msg + 4 * i) for i in range(8)]
    slot = u32(eng, table + POINT_SLOT)
    eng.disarm_watch()
    page_reads = []
    eng.watch(PAGE_VA, PAGE_VA + len(native_page), kind="r", name="page-r")
    eng.arm_watch()
    dfault = None
    ret = None
    try:
        ret = eng.call(cfg["dispatch"], [PAGE_VA, n])
    except Exception as exc:  # noqa: BLE001
        dfault = exc
    page_reads = [h for h in eng.watch_hits() if h.kind == "r" and h.name == "page-r"]
    return {"global": glob, "writes": writes, "fault": fault, "slot": slot,
            "msg": msg_words, "ret": ret, "dfault": dfault,
            "page_reads": page_reads}


def walker_reference(data: bytes, cfg: dict, native_page: bytes, n: int) -> int | None:
    """The walker alone on the same page (M9.38 positive control)."""
    eng = new_engine(data)
    eng.map("page", PAGE_VA, bytearray(native_page) + bytearray(0x40), "rw")
    return eng.call(cfg["walker"], [PAGE_VA, n])


def report_writer(build: str, res: dict, label: str) -> None:
    print(f"[{label}] build {build}: page-object global = {res['global']:#010x}"
          + (f" fault={type(res['fault']).__name__}: {res['fault']}" if res["fault"] else ""))
    for pc, off, size, val in res["writes"]:
        print(f"  write pc={pc:#010x} table+{off:#04x} size={size} value={val:#010x}")
    if not res["writes"]:
        print("  no guest write into the table")
    print(f"  slot +0x1c = {res['slot']:#010x}")
    print("  msg words: " + " ".join(f"{w:#x}" for w in res["msg"]))
    pcs = sorted({h.pc for h in res["page_reads"]})
    ret = res["ret"]
    print(f"  dispatch r0={'None' if ret is None else hex(ret)}"
          f" page_reads={len(res['page_reads'])} at "
          + (",".join(f"{p:#010x}" for p in pcs) or "-")
          + (f" fault={type(res['dfault']).__name__}: {res['dfault']}" if res["dfault"] else ""))


def cmd_writer(args) -> int:
    cfg = BUILDS[args.build]
    data = pw.load_image(args.image)
    mem = sec0_mem(data)
    from read_watch_l3 import decoded_page
    page = args.page if args.page is not None else cfg["page"]
    plen = args.page_len if args.page_len is not None else cfg["page_len"]
    raw = decoded_page(Path(args.cmp), Path(args.ind), page, plen)
    native = pw.swap16(raw)
    if mem.u16(cfg["store_pc"]) != 0x1927:
        raise Mismatch(f"{cfg['store_pc']:#010x} is not mov.l r2,@(28,r9): wrong build?")
    print(f"build {args.build}: writer={cfg['writer']:#010x} table={cfg['table']:#010x} "
          f"dispatch={cfg['dispatch']:#010x} walker={cfg['walker']:#010x} "
          f"page={page:#x} ({len(native)} B decoded) n={args.n}")
    pos = run_writer(data, cfg, native, TYPE_POINT, args.n)
    report_writer(args.build, pos, f"type {TYPE_POINT:#x}")
    neg = run_writer(data, cfg, native, TYPE_OTHER, args.n)
    report_writer(args.build, neg, f"type {TYPE_OTHER:#x} (negative)")
    ref = walker_reference(data, cfg, native, args.n)
    print(f"walker alone: r0={ref:#010x}")
    fails = 0
    store_hit = [w for w in pos["writes"] if w[0] == cfg["store_pc"] and w[1] == POINT_SLOT]
    walker_read = any(cfg["walker"] <= h.pc < cfg["walker"] + 0x100 for h in pos["page_reads"])
    checks = [
        ("writer ran without fault", pos["fault"] is None),
        ("slot +0x1c written at the store pc", bool(store_hit)),
        ("slot +0x1c == page buffer (OBJ+20)", pos["slot"] == PAGE_VA),
        ("dispatcher reached the walker's page read", walker_read),
        ("dispatcher r0 == walker alone r0", pos["ret"] == ref and ref not in (0, None)),
        ("negative: type 0x14f0 leaves +0x1c zero", neg["slot"] == 0),
        ("negative: no walker page read via +0x1c",
         not any(cfg["walker"] <= h.pc < cfg["walker"] + 0x100 for h in neg["page_reads"])),
    ]
    for name, ok in checks:
        print(f"  check {name}: {'ok' if ok else 'FAIL'}")
        fails += not ok
    if pos["ret"] not in (None, 0):
        print(f"record {args.n} offset via writer-filled table: {pos['ret'] - PAGE_VA:#x}")
    print("result:", "PASS" if not fails else f"FAIL ({fails})")
    return 0 if not fails else 1


# ---------------------------------------------------------------------------
# slots: static census from every load site of the table base

MAX_STATES = 6000
PRE_INSNS = 8


def _sx(v: int, bits: int) -> int:
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def step(u16, u32, pc: int, st: dict, table: int, out: set):
    """Apply the instruction at *pc* to the tracker state *st* (in place).

    State values: ``("b", k)`` = table + k, ``("c", v)`` = a constant.
    Accesses through a tracked base go to *out* as (pc, kind, size, offset).
    Returns the control kind: ``("next",)``, ``("cond", tgt, delayed)``,
    ``("jump", tgt)`` (bra), ``("call",)`` (jsr/bsr/bsrf, delayed),
    ``("end",)`` (rts/braf/jmp, delayed).
    """
    op = u16(pc)
    n, m, d4 = (op >> 8) & 15, (op >> 4) & 15, op & 15
    rn, rm = "r%d" % n, "r%d" % m
    top = op >> 12

    def base(r):
        v = st.get(r)
        return v[1] if v and v[0] == "b" else None

    def const(r):
        v = st.get(r)
        return v[1] if v and v[0] == "c" else None

    def acc(kind, size, off):
        if off is not None:
            out.add((pc, kind, size, off))

    def r0_index(r):
        if base(r) is not None and const("r0") is not None:
            return base(r) + const("r0")
        if base("r0") is not None and const(r) is not None:
            return base("r0") + const(r)
        return None

    def kill(r):
        st.pop(r, None)

    if top == 0x1:                                   # mov.l Rm,@(d,Rn)
        acc("w", 4, None if base(rn) is None else base(rn) + d4 * 4)
    elif top == 0x5:                                 # mov.l @(d,Rm),Rn
        acc("r", 4, None if base(rm) is None else base(rm) + d4 * 4)
        kill(rn)
    elif top == 0x8 and n in (0, 1, 4, 5):           # mov.b/w r0 <-> @(d,Rm)
        size = 1 if n in (0, 4) else 2
        b = base(rm)
        acc("w" if n < 4 else "r", size, None if b is None else b + d4 * size)
        if n >= 4:
            kill("r0")
    elif top == 0x8 and n in (9, 0xB, 0xD, 0xF):     # bt/bf(/s)
        return ("cond", pc + 4 + _sx(op & 0xFF, 8) * 2, n in (0xD, 0xF))
    elif top == 0x2 and d4 in (0, 1, 2):             # mov.x Rm,@Rn
        acc("w", 1 << d4, base(rn))
    elif top == 0x6 and d4 in (0, 1, 2, 4, 5, 6):    # mov.x @Rm,Rn / @Rm+,Rn
        b = base(rm)
        acc("r", 1 << (d4 & 3), b)
        kill(rn)
        if d4 >= 4 and b is not None and m != n:
            st[rm] = ("b", b + (1 << (d4 & 3)))
    elif top == 0x0 and d4 in (4, 5, 6):             # mov.x Rm,@(r0,Rn)
        acc("w", 1 << (d4 - 4), r0_index(rn))
    elif top == 0x0 and d4 in (0xC, 0xD, 0xE):       # mov.x @(r0,Rm),Rn
        acc("r", 1 << (d4 - 0xC), r0_index(rm))
        kill(rn)
    elif top == 0x6 and d4 == 3:                     # mov Rm,Rn
        if rm in st:
            st[rn] = st[rm]
        else:
            kill(rn)
    elif top == 0x6 and d4 in (0xC, 0xD):            # extu.b/w Rm,Rn
        c = const(rm)
        if c is not None:
            st[rn] = ("c", c & (0xFF if d4 == 0xC else 0xFFFF))
        else:
            kill(rn)
    elif top == 0x7:                                 # add #imm,Rn
        v = st.get(rn)
        if v:
            st[rn] = (v[0], v[1] + _sx(op & 0xFF, 8))
    elif top == 0x3 and d4 == 0xC:                   # add Rm,Rn
        if base(rn) is not None and const(rm) is not None:
            st[rn] = ("b", base(rn) + const(rm))
        elif const(rn) is not None and base(rm) is not None:
            st[rn] = ("b", const(rn) + base(rm))
        elif const(rn) is not None and const(rm) is not None:
            st[rn] = ("c", const(rn) + const(rm))
        else:
            kill(rn)
    elif top == 0x3 and d4 in (0, 2, 3, 6, 7):       # cmp/xx: no register write
        pass
    elif top == 0xE:                                 # mov #imm,Rn
        st[rn] = ("c", _sx(op & 0xFF, 8))
    elif top == 0x9:                                 # mov.w @(d,pc),Rn
        st[rn] = ("c", _sx(u16(pc + 4 + (op & 0xFF) * 2), 16))
    elif top == 0xD:                                 # mov.l @(d,pc),Rn
        val = u32(((pc + 4) & ~3) + (op & 0xFF) * 4)
        st[rn] = ("b", 0) if val == table else ("c", val)
    elif top == 0xA:                                 # bra
        return ("jump", pc + 4 + _sx(op & 0xFFF, 12) * 2)
    elif top == 0xB:                                 # bsr
        return ("call",)
    elif top == 0x4 and op & 0xFF == 0x0B:           # jsr @Rn
        return ("call",)
    elif top == 0x0 and op & 0xFF == 0x03:           # bsrf
        return ("call",)
    elif op == 0x000B or (top == 0x0 and op & 0xFF == 0x23) \
            or (top == 0x4 and op & 0xFF == 0x2B):  # rts / braf / jmp
        return ("end",)
    elif top == 0x2 and d4 in (8, 0xC):              # tst / cmp/str
        pass
    elif top == 0x8 or op in (0x0009, 0x0008, 0x0018, 0x0028, 0x0019):
        pass                                          # cmp/eq #imm, nop, clrt, sett...
    elif top == 0xC:
        if n not in (0, 1, 2, 3, 8):                 # writes r0 (and/or/xor #, mova, gbr loads)
            kill("r0")
    elif top == 0x0 and d4 == 7:                     # mul.l
        pass
    elif top == 0x4 and op & 0xFF in (0x11, 0x15):   # cmp/pz, cmp/pl
        pass
    else:                                            # anything else: Rn is unknown
        kill(rn)
    return ("next",)


def trace_site(u16, u32, start: int, reg: int, table: int, lo: int, hi: int):
    """Follow the code after the load at *start* of *table* into *reg*.

    Both arms of every conditional branch, delay slots executed once,
    ``jsr``/``bsr`` kill r0-r7 (caller-saved), ``rts``/``braf``/``jmp`` end
    the path.  Paths stay inside ``[lo, hi)``.  Returns the access set.
    """
    out = set()
    seen = set()
    # constants set just before the load (``mov #-100,r0`` then the load):
    # replay up to PRE_INSNS straight-line instructions, accesses discarded
    pre: dict = {}
    for pc in range(max(lo, start - 2 * PRE_INSNS), start, 2):
        if step(u16, u32, pc, pre, table, set())[0] != "next":
            pre = {}
    pre = {r: v for r, v in pre.items() if v[0] == "c"}
    pre["r%d" % reg] = ("b", 0)
    work = [(start + 2, tuple(sorted(pre.items())))]
    while work and len(seen) < MAX_STATES:
        pc, frozen = work.pop()
        if (pc, frozen) in seen or not lo <= pc < hi:
            continue
        seen.add((pc, frozen))
        st = dict(frozen)
        ctl = step(u16, u32, pc, st, table, out)
        kind = ctl[0]
        if kind == "next":
            work.append((pc + 2, tuple(sorted(st.items()))))
            continue
        if kind == "cond" and not ctl[2]:
            fz = tuple(sorted(st.items()))
            work += [(pc + 2, fz), (ctl[1], fz)]
            continue
        # delayed: execute the slot once, then branch
        slot_ctl = step(u16, u32, pc + 2, st, table, out)
        if slot_ctl[0] != "next":            # illegal slot: stop this path
            continue
        if kind == "call":
            for r in range(8):
                st.pop("r%d" % r, None)
        fz = tuple(sorted(st.items()))
        if kind == "cond":
            work += [(pc + 4, fz), (ctl[1], fz)]
        elif kind == "jump":
            work.append((ctl[1], fz))
        elif kind == "call":
            work.append((pc + 4, fz))
    return out


def bounds_of(records, va: int) -> tuple[int, int, bool]:
    """(lo, hi, in_pdata): the pdata function holding *va*, else its gap."""
    import bisect
    starts = [r[0] for r in records]
    i = bisect.bisect_right(starts, va) - 1
    if i >= 0:
        begin, _p, length = records[i]
        if begin <= va < begin + length:
            return begin, begin + length, True
    lo = records[i][0] + records[i][2] if i >= 0 else va & ~0xFFF
    hi = records[i + 1][0] if i + 1 < len(records) else va + 0x1000
    return lo, hi, False


def cmd_slots(args) -> int:
    import pdata
    import sh4xref
    cfg = BUILDS[args.build]
    table = cfg["table"]
    mem, exec_segs, _imp, _exp = sh4xref.load_module(args.image, IMAGE_START, MODULE)
    data = pw.load_image(args.image)
    records, _meta = pdata.load_table(data, IMAGE_START, MODULE)
    sites = []
    for pool in sh4xref.pool_entries(mem, exec_segs, table):
        sites += sh4xref.loads_of(mem, pool)
    print(f"build {args.build}: table={table:#010x} load sites={len(sites)}")
    per_off: dict[int, dict] = {}
    fns = set()
    for load, reg in sorted(sites):
        lo, hi, inp = bounds_of(records, load)
        fns.add(lo)
        acc = trace_site(mem.u16, mem.u32, load, reg, table, lo, hi)
        r = sum(1 for a in acc if a[1] == "r")
        w = sum(1 for a in acc if a[1] == "w")
        tag = "fn" if inp else "gap@"
        print(f"  site {load:#010x} r{reg} {tag} {lo:#010x}: reads={r} writes={w}")
        for pc, kind, size, off in sorted(acc):
            row = per_off.setdefault(off, {"r": set(), "w": set(), "sizes": set(),
                                           "wfn": set(), "rfn": set()})
            row[kind].add(pc)
            row["sizes"].add(size)
            row[kind + "fn"].add(lo)
            if args.sites:
                print(f"    {pc:#010x} {kind} {size} +{off:#x}")
    print(f"functions={len(fns)} distinct offsets={len(per_off)}")
    for off in sorted(per_off):
        row = per_off[off]
        print(f"  +{off:#05x} size={','.join(map(str, sorted(row['sizes'])))} "
              f"reads={len(row['r'])} writes={len(row['w'])} "
              f"writers={','.join(f'{f:#010x}' for f in sorted(row['wfn'])) or '-'}")
    if per_off:
        print(f"span: +{min(per_off):#x}..+{max(o + 4 for o in per_off):#x}")
    return 0


def cmd_cases(args) -> int:
    cfg = BUILDS[args.build]
    data = pw.load_image(args.image)
    mem = sec0_mem(data)
    sw = cfg["switch"]
    cases = switch_cases(lambda va: mem.u16(va & ~1) >> (8 * (va & 1)) & 0xFF,
                         mem.u16, mem.u32, sw)
    print(f"build {args.build}: switch {sw['fn']:#010x} braf {sw['braf']:#010x} "
          f"jump table {sw['jt']:#010x} types {sw['base']:#x}..{sw['base'] + sw['cases'] - 1:#x}")
    by = {}
    for t, callee in cases:
        by.setdefault(callee, []).append(t)
    for callee, types in sorted(by.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)):
        name = "default (common tail, no writer)" if callee is None else f"{callee:#010x}"
        print(f"  {name}: {len(types)} type(s) " + ",".join(f"{t:#x}" for t in types))
    return 0


# ---------------------------------------------------------------------------
# self-test (synthetic; no vendor bytes)


def selftest() -> int:
    fails = 0

    def check(name, cond):
        nonlocal fails
        print("%-60s %s" % (name, "ok" if cond else "FAIL"))
        fails += not cond

    # 1. a synthetic writer: table[+0x1c] = (*glob)->+20, like the real store
    code = 0x10000000
    prog = struct.pack("<4H", 0x6242, 0x5225, 0x000B, 0x1527)
    table, glob = 0x11000000, 0x11001000
    eng = PySh4(endian="little")
    eng.map("code", code, prog, "rx")
    eng.map("bss", table, bytearray(0x2000), "rw")
    eng.map("obj", OBJ_VA, bytearray(0x40), "rw")
    eng.map("stack", STACK_VA, bytearray(0x1000), "rw")
    eng.set_regs(r15=STACK_VA + 0xF00)
    put32(eng, glob, OBJ_VA)
    put32(eng, OBJ_VA + 20, PAGE_VA)
    eng.watch(table, table + TABLE_SPAN, kind="w", name="table-w")
    eng.arm_watch()
    eng.call(code, [glob, table])
    rows = slot_writes(eng, table)
    check("synthetic writer: one store recorded", len(rows) == 1)
    check("synthetic writer: store at pc+6 into +0x1c",
          rows and rows[0][0] == code + 6 and rows[0][1] == 0x1C)
    check("synthetic writer: value is the buffer", rows and rows[0][3] == PAGE_VA)
    # negative: a set-up write is not a guest store
    eng2 = PySh4(endian="little")
    eng2.map("bss", table, bytearray(0x200), "rw")
    eng2.watch(table, table + TABLE_SPAN, kind="w", name="table-w")
    eng2.arm_watch()
    put32(eng2, table + 0x1C, 1)
    check("negative: a host write is not a slot write", slot_writes(eng2, table) == [])

    # 2. switch decode on a synthetic byte table
    braf, jt, pool = 0x1000, 0x2000, 0x1100
    mem = {}

    def w16(va, v):
        mem[va] = v & 0xFF
        mem[va + 1] = v >> 8

    def w32(va, v):
        w16(va, v & 0xFFFF)
        w16(va + 2, v >> 16)
    w16(braf, 0x0023)
    w32(pool, jt)
    for i, b in enumerate([0x00, 0x10, 0x20]):
        mem[jt + i] = b
    w16(braf + 4, 0xD301)          # mov.l @(1*4+pc),r3 -> pool at 0x100c
    w32(((braf + 8) & ~3) + 4, 0xAAAA0000)
    w16(braf + 4 + 0x10, 0xD301)
    w32(((braf + 4 + 0x10 + 4) & ~3) + 4, 0xBBBB0000)
    w16(braf + 4 + 0x20, 0x0009)   # nop: default
    u8 = lambda va: mem.get(va, 0)  # noqa: E731
    u16 = lambda va: u8(va) | u8(va + 1) << 8  # noqa: E731
    u32_ = lambda va: u16(va) | u16(va + 2) << 16  # noqa: E731
    sw = {"fn": 0, "braf": braf, "jt": jt, "jt_pool": pool, "base": 0x14CC, "cases": 3}
    got = switch_cases(u8, u16, u32_, sw)
    check("switch: three cases decoded",
          got == [(0x14CC, 0xAAAA0000), (0x14CD, 0xBBBB0000), (0x14CE, None)])
    bad = dict(sw, jt_pool=pool + 4)
    try:
        switch_cases(u8, u16, u32_, bad)
        check("switch: wrong pool is a loud mismatch", False)
    except Mismatch:
        check("switch: wrong pool is a loud mismatch", True)
    # 3. the static slot tracker on a synthetic site
    C, T = 0x00400000, 0x00D53500
    words = [0xE09C, 0xD206, 0x600C, 0x022E, 0xD904, 0x430B, 0x1927, 0x1931,
             0x6593, 0x430B, 0x0009, 0x1551, 0x000B, 0x0009]
    blob = bytearray(struct.pack("<%dH" % len(words), *words))
    blob += struct.pack("<I", T)
    m16 = lambda va: struct.unpack_from("<H", blob, va - C)[0]  # noqa: E731
    m32 = lambda va: struct.unpack_from("<I", blob, va - C)[0]  # noqa: E731
    got = trace_site(m16, m32, C + 2, 2, T, C, C + 28)
    want = {(C + 6, "r", 4, 0x9C), (C + 12, "w", 4, 0x1C), (C + 14, "w", 4, 0x4)}
    check("tracker: pre-load constant, delay slot, callee-saved base", got == want)
    check("tracker: no access through a reg a jsr clobbered",
          all(a[0] != C + 22 for a in got))
    got2 = trace_site(m16, m32, C + 2, 2, T + 4, C, C + 28)
    check("tracker negative: other table -> only the seeded load's read",
          got2 == {(C + 6, "r", 4, 0x9C)})
    print("selftest:", "PASS" if not fails else f"FAIL ({fails})")
    return 0 if not fails else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    c = sub.add_parser("cases")
    c.add_argument("image")
    c.add_argument("--build", choices=tuple(BUILDS), default="eu2011")
    w = sub.add_parser("writer")
    w.add_argument("image")
    w.add_argument("--cmp", required=True)
    w.add_argument("--ind", required=True)
    w.add_argument("--page", type=lambda s: int(s, 0), default=None)
    w.add_argument("--page-len", type=lambda s: int(s, 0), default=None)
    w.add_argument("--n", type=int, default=1)
    w.add_argument("--build", choices=tuple(BUILDS), default="eu2011")
    k = sub.add_parser("slots")
    k.add_argument("image")
    k.add_argument("--build", choices=tuple(BUILDS), default="eu2011")
    k.add_argument("--sites", action="store_true", help="print every access")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "cases":
        return cmd_cases(args)
    if args.cmd == "writer":
        return cmd_writer(args)
    if args.cmd == "slots":
        return cmd_slots(args)
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
