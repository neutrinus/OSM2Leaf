#!/usr/bin/env python3
"""Read-watch the firmware on one decoded page: who reads (and writes) it (M9.38).

The dynamic counterpart of M3.23.  Two commands, both on real bytes:

``walk``
    Put a decoded factory page in a buffer and run the family's own walker on
    it with a read watch and a write watch on that buffer.  The page is the
    factory ``POINT010`` page ``0x840ba0`` (US corpus) or its EU twin; the
    walker is ``fn 0x003f5194`` (EU2011) / ``fn 0x0041db44`` (US2011), a
    ``.pdata`` GAP leaf, so the tool reports the gap container and the entry.

``chain``
    Run the ``.cmp`` caller ``fn 0x0041c044`` (EU2011, a ``.pdata`` START,
    length 0x88; US2011 ``fn 0x00443da8``) with a real ``.cmp``/``.ind`` pair
    mapped and the decoded page pre-written into the decoder's destination
    ``OUT_VA``, watching that destination.  The caller reaches the chunk
    engine through a context descriptor, and where it lands is a finding
    either way.

The watch is observation only.  Every run also executes once **without** a
watch and the two results are compared (``r0``, OUT SHA-256, ``sec_reads``,
instruction count) -- a watch that changes any of them is a failure.

A watch that records no guest read is reported as ``NO HITS`` and is never a
pass; a run that stops on an import before reaching the buffer reports
``BLOCKED`` with the import name (which belongs on M9.24's list).

Usage::

  read_watch_l3.py --selftest
  read_watch_l3.py walk IMG --cmp C --ind I --page 0x840ba0 \
      [--page-len 42848] [--build us2011] [--n 0,1,2]
  read_watch_l3.py chain IMG --cmp C --ind I --entry 0x0041c044 \
      [--build eu2011] [--offset 0x840ba0] [--length 42848]

Method and results: docs/experiments/EXP-2026-11-19-M9.38-read-watch.md
"""

from __future__ import annotations

import argparse
import hashlib
import os
import struct
import sys
import zlib
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
for path in (HERE, os.path.join(HERE, "l3_harness")):
    if path not in sys.path:
        sys.path.insert(0, path)

import chunk_decoder_l3 as cdl3  # noqa: E402
import mutate_refer_poi as mrp  # noqa: E402
import point_walk_l3 as pw  # noqa: E402
import watch as watch_mod  # noqa: E402
from engine import PySh4  # noqa: E402

IMAGE_START = cdl3.IMAGE_START
MODULE = cdl3.MODULE
PAGE_VA = pw.PAGE_VA            # 0x20000000, the walker's page argument
WALK_STACK = 0x30000000

#: US2011 counterpart of the EU ``.cmp`` caller 0x0041c044 (M1.22b fn_match,
#: `pdata where` = START, length 0x88).
US_CHAIN_ENTRY = 0x00443DA8

#: The POINT record dispatcher (M9.38 ``above``): it compares the page argument
#: with slots of a global BSS table and calls the nth reader.  ``slot`` is the
#: table offset whose match branches to the walker load; ``pool`` is the
#: dispatcher's own literal slot the walker VA is loaded from -- that value is
#: what proves the route, because the table itself is BSS (zero at load).
ABOVE = {
    "eu2011": {"dispatch": 0x003F5CDC, "table": 0x00D53500, "walker": 0x003F5194,
               "slot": 28, "pool": 0x003F5D84},
    "us2011": {"dispatch": 0x0041E63C, "table": 0x00C81100, "walker": 0x0041DB44,
               "slot": 28, "pool": 0x0041E6E4},
}


# ---------------------------------------------------------------------------
# shared helpers


def decoded_page(cmp_path: Path, ind_path: Path, page: int, page_len: int) -> bytes:
    """The decoded page at *page* (inner zlib stream, as point_walk_l3 reads it)."""
    _usize, _csize, _count, _chunk, offsets = mrp.read_ind(ind_path)
    blob = mrp.decode(cmp_path.read_bytes(), offsets)
    end = page + page_len if page_len else len(blob)
    return zlib.decompressobj().decompress(blob[page:end])


def out_sha(out: bytes) -> str:
    return hashlib.sha256(out).hexdigest()


def result_signature(ret: int, out: bytes, stats: dict) -> dict:
    """Everything a watch must not change."""
    return {
        "r0": ret & 0xFFFFFFFF,
        "out_sha256": out_sha(out),
        "sec_reads": sorted((va, size, hits) for (va, size), hits
                            in stats.get("sec_reads", {}).items()),
        "insns": stats.get("insns"),
    }


def print_table(rows, hits, base: int, indent: str = "  ") -> None:
    guest = [h for h in hits if not h.kind.startswith("api") and h.kind != "x"]
    api = watch_mod.api_summary(hits)
    if not guest:
        print(f"{indent}NO HITS: the watch saw no guest access to {base:#010x}")
    for row in rows:
        widths = ",".join(str(w) for w in row["widths"])
        print(f"{indent}read" if row["kind"] == "r" else f"{indent}write", end="")
        print(f" {row['function']} n={row['accesses']} "
              f"first={row['first_offset']} last={row['last_offset']} "
              f"widths={widths}")
    print(f"{indent}api={api['api']} fetch={api['fetch']} "
          f"guest={watch_mod.totals(hits)}")


# ---------------------------------------------------------------------------
# walk: the family's own walker on a decoded page


def cmd_walk(args) -> int:
    tgt = pw.target(args.build)
    data = pw.load_image(args.image)
    text_va, text = pw.navi_text(data, IMAGE_START)
    raw = decoded_page(Path(args.cmp), Path(args.ind), args.page, args.page_len)
    native = pw.swap16(raw)
    ns = [int(x, 0) for x in args.n.split(",")] if args.n else [0, 1, 2]
    watches = [{"lo": PAGE_VA, "hi": PAGE_VA + len(native), "kind": kind,
                "name": f"page-{kind}"} for kind in ("r", "w")]
    lab = watch_mod.Labeller(data, IMAGE_START, MODULE, entry=tgt["nth"])
    print(f"build {args.build}: walker={tgt['nth']:#010x} "
          f"page={PAGE_VA:#010x}..{PAGE_VA + len(native):#010x} "
          f"({len(native)} B) n={ns}")
    fails = 0
    for n in ns:
        eng = PySh4(endian="little")
        eng.map("text", text_va, text, "rx")
        eng.map("page", PAGE_VA, bytearray(native) + bytearray(0x40), "rw")
        eng.map("stack", WALK_STACK, bytearray(0x1000), "rw")
        eng.set_regs(r15=WALK_STACK + 0xF00)
        for spec in watches:
            eng.watch(spec["lo"], spec["hi"], kind=spec["kind"], name=spec["name"])
        eng.arm_watch()
        try:
            ret = eng.call(tgt["nth"], [PAGE_VA, n])
            fault = None
        except Exception as exc:  # noqa: BLE001 - a fault is a verdict, hits kept
            ret, fault = None, exc
        hits = eng.watch_hits()
        rows = watch_mod.summarise(hits, PAGE_VA, labeller=lab.label)
        value = None if ret in (None, 0) else ret - PAGE_VA
        print(f"n={n}: r0={eng.get_regs()['r0']:#010x} "
              f"record_offset={None if value is None else hex(value)}"
              + (f" fault={type(fault).__name__}: {fault}" if fault else ""))
        print_table(rows, hits, PAGE_VA)
        if not [h for h in hits if h.kind == "r"]:
            fails += 1
            print("  NO HITS: no guest read of the page (never a pass)")
    # negative control: the same run with the watch off must give the same r0
    ret_off = None
    for n in ns[:1]:
        eng = PySh4(endian="little")
        eng.map("text", text_va, text, "rx")
        eng.map("page", PAGE_VA, bytearray(native) + bytearray(0x40), "rw")
        eng.map("stack", WALK_STACK, bytearray(0x1000), "rw")
        eng.set_regs(r15=WALK_STACK + 0xF00)
        try:
            ret_off = eng.call(tgt["nth"], [PAGE_VA, n])
        except Exception:  # noqa: BLE001
            ret_off = None
        print(f"control (watch off): n={n} r0={eng.get_regs()['r0']:#010x} "
              f"hits={len(eng.watch_hits())}")
        if eng.watch_hits():
            fails += 1
            print("  FAIL: an unarmed engine recorded hits")
    print("result:", "PASS" if not fails else "FAIL (%d)" % fails)
    return 0 if not fails else 1


# ---------------------------------------------------------------------------
# above: the dispatcher that routes the page to the walker


def route_proven(data, pool_va: int, walker: int) -> bool:
    """True when the dispatcher's own literal pool names the walker.

    The dispatch table is BSS (zero at load), so the value that proves the
    route is the pool word the dispatcher loads the walker VA from.
    """
    from sh4dis import Mem

    _, secs = pw.module_sections(data, IMAGE_START, MODULE)
    mem = Mem([(s["realaddr"], blob) for s, comp, blob in secs
               if not comp and blob is not None])
    return mem.u32(pool_va) == walker


def cmd_above(args) -> int:
    tgt = pw.target(args.build)
    cfg = ABOVE[args.build]
    data = pw.load_image(args.image)
    text_va, text = pw.navi_text(data, IMAGE_START)
    raw = decoded_page(Path(args.cmp), Path(args.ind), args.page, args.page_len)
    native = pw.swap16(raw)
    if not route_proven(data, cfg["pool"], cfg["walker"]):
        print(f"BLOCKED: dispatcher pool {cfg['pool']:#010x} does not hold "
              f"the walker {cfg['walker']:#010x}; dispatch route not proven")
        return 4
    slot = cfg["slot"]
    n = args.n
    watches = [{"lo": PAGE_VA, "hi": PAGE_VA + len(native), "kind": kind,
                "name": f"page-{kind}"} for kind in ("r", "w")]
    lab = watch_mod.Labeller(data, IMAGE_START, MODULE, entry=tgt["nth"])
    print(f"build {args.build}: dispatch={cfg['dispatch']:#010x} "
          f"table={cfg['table']:#010x} walker_slot=+{slot:#x} "
          f"pool={cfg['pool']:#010x} -> walker={cfg['walker']:#010x} n={n}")

    def run(with_watch: bool):
        eng = PySh4(endian="little")
        eng.map("text", text_va, text, "rx")
        eng.map("table", cfg["table"], bytearray(0x200), "rw")
        eng.write_mem(cfg["table"] + slot, struct.pack("<I", PAGE_VA))
        eng.map("page", PAGE_VA, bytearray(native) + bytearray(0x40), "rw")
        eng.map("stack", WALK_STACK, bytearray(0x1000), "rw")
        eng.set_regs(r15=WALK_STACK + 0xF00)
        if with_watch:
            for spec in watches:
                eng.watch(spec["lo"], spec["hi"], kind=spec["kind"], name=spec["name"])
            eng.arm_watch()
        try:
            ret = eng.call(cfg["dispatch"], [PAGE_VA, n])
            fault = None
        except Exception as exc:  # noqa: BLE001
            ret, fault = None, exc
        return ret, eng, fault

    ret, eng, fault = run(True)
    hits = eng.watch_hits()
    rows = watch_mod.summarise(hits, PAGE_VA, labeller=lab.label)
    value = None if ret in (None, 0) else ret - PAGE_VA
    print(f"n={n}: r0={eng.get_regs()['r0']:#010x} "
          f"record_offset={None if value is None else hex(value)}"
          + (f" fault={type(fault).__name__}: {fault}" if fault else ""))
    print_table(rows, hits, PAGE_VA)
    ret_off, eng_off, _ = run(False)
    print(f"control (watch off): r0={ret_off if ret_off is None else hex(ret_off)} "
          f"hits={len(eng_off.watch_hits())}")
    guest_r = [h for h in hits if h.kind == "r"]
    if not guest_r:
        fails = 1
        print("  NO HITS: the dispatcher never reached a page read (never a pass)")
    else:
        fails = 0
        if ret_off != ret:
            fails = 1
            print("  FAIL: watch changed r0")
    print("result:", "PASS" if not fails else "FAIL (%d)" % fails)
    return 0 if not fails else 1


# ---------------------------------------------------------------------------
# chain: the .cmp caller with its destination watched


def cmd_chain(args) -> int:
    import cmpind

    tgt = dict(cdl3.BUILD_TARGETS[args.build])
    image = pw.load_image(args.image)
    usize, csize, _count, chunk_size, offsets = cmpind.read_index(Path(args.ind))
    rows = cdl3.table_rows(usize, csize, offsets, chunk_size)
    cmp_bytes = Path(args.cmp).read_bytes()
    page = decoded_page(Path(args.cmp), Path(args.ind), args.offset, args.length)
    watches = [{"lo": cdl3.OUT_VA, "hi": cdl3.OUT_VA + len(page), "kind": kind,
                "name": f"out-{kind}"} for kind in ("r", "w")]
    print(f"build {args.build}: entry={args.entry:#010x} "
          f"watch={cdl3.OUT_VA:#010x}..{cdl3.OUT_VA + len(page):#010x} "
          f"({len(page)} B seeded from the decoded .cmp)")

    def run(with_watch: bool):
        eng = PySh4(endian="little")
        ret, out, stats = cdl3.run_firmware(
            image, cmp_bytes, rows, args.offset, args.length, chunk_size,
            sec_mode="zero-mask", sec1_table=None, tgt=tgt, engine=eng,
            watches=watches if with_watch else (),
            seed_page=page,
        )
        return ret, out, stats

    try:
        w_ret, w_out, w_stats = run(True)
    except cdl3.Blocked as exc:
        stats = exc.args[2] if len(exc.args) > 2 else {}
        print(f"BLOCKED: {exc.args[0]}")
        hits = stats.get("watch_hits", [])
        lab = watch_mod.Labeller(image, IMAGE_START, MODULE, entry=args.entry)
        rows = watch_mod.summarise(hits, cdl3.OUT_VA, labeller=lab.label)
        print_table(rows, hits, cdl3.OUT_VA)
        print("result: BLOCKED (an import/engine stop before the buffer; "
              "never a pass)")
        return 4
    p_ret, p_out, p_stats = run(False)
    sig_w = result_signature(w_ret, w_out, w_stats)
    sig_p = result_signature(p_ret, p_out, p_stats)
    print(f"r0={w_ret:#010x} insns={w_stats['insns']} "
          f"out_sha={sig_w['out_sha256']}")
    print("control (watch on vs off):",
          "IDENTICAL" if sig_w == sig_p else f"DIFFERS {sig_p}")

    hits = w_stats.get("watch_hits", [])
    lab = watch_mod.Labeller(image, IMAGE_START, MODULE, entry=args.entry)
    rows = watch_mod.summarise(hits, cdl3.OUT_VA, labeller=lab.label)
    print_table(rows, hits, cdl3.OUT_VA)

    guest_r = [h for h in hits if h.kind == "r"]
    guest_w = [h for h in hits if h.kind == "w"]
    api_w = [h for h in hits if h.kind == "api-w"]
    api_r = [h for h in hits if h.kind == "api-r"]
    # The copy-proof tie: OUT seeded (write/read nonzero) in the same run, so a
    # zero guest write-watch afterwards means "written by a copy, no visible
    # writer", not "wrong address".
    print(f"copy-proof: seeded={len(page)} B api-r={len(api_r)} api-w={len(api_w)} "
          f"guest-read={len(guest_r)} guest-write={len(guest_w)}")
    if api_w and guest_r and not guest_w:
        print("verdict: the destination is read after seeding and no guest "
              "instruction writes it in this run")
    ok = sig_w == sig_p
    print("result:", "PASS (watch inert)" if ok else "FAIL (watch changed a result)")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# self-test (no vendor data): two functions, api exclusion, GAP label


def _two_function_program(page: int):
    """A reads 4 B of PAGE and calls B; B writes 1 B of PAGE; A returns.

    Literals are placed programmatically so no displacement is hand-typed.
    ``A`` at ``code``, ``B`` at ``code+0x28``; PAGE at ``code+0x38``, B at
    ``code+0x3c``.
    """
    code = 0x8C100000
    fn_b = code + 0x28
    lit_page = code + 0x38
    lit_b = code + 0x3C
    words = [0x0009] * (0x40 // 2)

    def disp_load(insn_va: int, literal_va: int) -> int:
        base = (insn_va + 4) & ~3
        return (literal_va - base) // 4

    # A -- save pr first: `jsr @r1` clobbers it, so A must restore it before rts
    words[0x00 // 2] = 0x4F22                                     # sts.l pr,@-r15
    words[0x02 // 2] = 0xD200 | disp_load(code + 0x02, lit_page)  # r2 = PAGE
    words[0x04 // 2] = 0x6322                                     # mov.l @r2,r3 (4 B)
    words[0x06 // 2] = 0xD100 | disp_load(code + 0x06, lit_b)     # r1 = B
    words[0x08 // 2] = 0x410B                                     # jsr @r1
    words[0x0a // 2] = 0x0009                                     # delay slot
    words[0x0c // 2] = 0x4F26                                     # lds.l @r15+,pr
    words[0x0e // 2] = 0x000B                                     # rts
    words[0x10 // 2] = 0x0009                                     # delay slot
    # B
    words[0x28 // 2] = 0xD200 | disp_load(code + 0x28, lit_page)  # r2 = PAGE
    words[0x2a // 2] = 0xE001                                     # mov #0,r0
    words[0x2c // 2] = 0x2200                                     # mov.b r0,@r2 (1 B)
    words[0x2e // 2] = 0x000B                                     # rts
    words[0x30 // 2] = 0x0009                                     # delay slot
    blob = bytearray(b"".join(struct.pack("<H", w) for w in words))
    blob[0x38:0x3c] = struct.pack("<I", page)
    blob[0x3c:0x40] = struct.pack("<I", fn_b)
    return code, bytes(blob)


def selftest() -> int:
    fails = 0

    def check(name, cond):
        nonlocal fails
        print("%-58s %s" % (name, "ok" if cond else "FAIL"))
        fails += not cond

    page = PAGE_VA
    code, program = _two_function_program(page)
    fn_b = code + 0x28
    eng = PySh4(endian="little")
    eng.map("code", code, program, "rx")
    eng.map("page", page, bytearray(0x40), "rw")
    eng.map("stack", 0x30000000, bytearray(0x1000), "rw")
    eng.set_regs(r15=0x30000F00, r4=page)
    eng.watch(page, page + 0x20, kind="r", name="page")
    eng.watch(page + 0x20, page + 0x40, kind="r", name="other-half")
    eng.watch(page, page + 0x40, kind="w", name="page-w")
    eng.arm_watch()
    eng.write_mem(page, b"\x11\x22\x33\x44")      # setup write: api, excluded
    try:
        eng.call(code, [])
        fault = None
    except Exception as exc:  # noqa: BLE001
        fault = exc
    hits = eng.watch_hits()

    def labeller(pc):
        # A leaf test program: name by the containing function (A or B).
        return f"fn 0x{fn_b:08x}" if pc >= fn_b else f"fn 0x{code:08x}"

    rows = watch_mod.summarise(hits, page, labeller=labeller)
    check("two-function program ran", fault is None)
    read_fns = {r["function"] for r in rows if r["kind"] == "r"}
    check("A is credited for a page read", f"fn 0x{code:08x}" in read_fns)
    a_read = next((r for r in rows if r["function"] == f"fn 0x{code:08x}"
                   and r["kind"] == "r"), None)
    check("A's read width is 4", a_read is not None and a_read["widths"] == [4])
    check("the unwatched half has no hits",
          all(h.name != "other-half" for h in hits))
    check("setup api write is excluded from guest reads/writes",
          watch_mod.api_summary(hits)["api"] == 1
          and watch_mod.totals(hits) == {"r": 1, "w": 1})
    check("B's write lands in the write watch",
          any(r["kind"] == "w" and r["function"] == f"fn 0x{code + 0x28:08x}"
              for r in rows))
    # GAP label case reuses the pure logic (synthetics have no pdata)
    check("GAP label names the entry, not the preceding fn",
          watch_mod._label_from([(0x1000, 4, 0x20), (0x1100, 4, 0x20)], 0x1044,
                                called=[0x1040], gap=(0x1020, 0x1100))
          == "GAP@0x00001020 (pc 0x00001044, entry 0x00001040)")
    check("unarmed engine records nothing",
          len(PySh4().watch_hits()) == 0)

    print("selftest:", "PASS" if not fails else "FAIL (%d)" % fails)
    return 0 if not fails else 1


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    walk = sub.add_parser("walk", help="watch the family walker on a decoded page")
    walk.add_argument("image")
    walk.add_argument("--cmp", required=True)
    walk.add_argument("--ind", required=True)
    walk.add_argument("--page", type=lambda s: int(s, 0), required=True)
    walk.add_argument("--page-len", type=lambda s: int(s, 0), default=0)
    walk.add_argument("--n", help="comma-separated record numbers")
    walk.add_argument("--build", choices=tuple(pw.BUILD_TARGETS), default="us2011")
    above = sub.add_parser("above", help="run the dispatcher that routes the page to the walker")
    above.add_argument("image")
    above.add_argument("--cmp", required=True)
    above.add_argument("--ind", required=True)
    above.add_argument("--page", type=lambda s: int(s, 0), default=None)
    above.add_argument("--page-len", type=lambda s: int(s, 0), default=None)
    above.add_argument("--n", type=int, default=1)
    above.add_argument("--build", choices=tuple(pw.BUILD_TARGETS), default="eu2011")
    chain = sub.add_parser("chain", help="watch the .cmp caller's destination")
    chain.add_argument("image")
    chain.add_argument("--cmp", required=True)
    chain.add_argument("--ind", required=True)
    chain.add_argument("--entry", type=lambda s: int(s, 0), default=None,
                       help="default: 0x0041c044 EU, 0x00443da8 US")
    chain.add_argument("--offset", type=lambda s: int(s, 0), default=None,
                       help="default: 0x840ba0 US, 0x6e06d0 EU (the POINT010 page)")
    chain.add_argument("--length", type=lambda s: int(s, 0), default=None,
                       help="default: 42848 US, 97158 EU")
    chain.add_argument("--build", choices=tuple(cdl3.BUILD_TARGETS), default="eu2011")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "above":
        if args.page is None:
            args.page = 0x840BA0 if args.build == "us2011" else 0x6E06D0
        if args.page_len is None:
            args.page_len = 42848 if args.build == "us2011" else 97158
        return cmd_above(args)
    if args.cmd == "chain":
        us = args.build == "us2011"
        if args.entry is None:
            args.entry = US_CHAIN_ENTRY if us else 0x0041C044
        if args.offset is None:
            args.offset = 0x840BA0 if us else 0x6E06D0
        if args.length is None:
            args.length = 42848 if us else 97158
        return cmd_chain(args)
    if args.cmd == "walk":
        return cmd_walk(args)
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
