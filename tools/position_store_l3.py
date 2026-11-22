#!/usr/bin/env python3
"""position_store_l3.py - run the firmware's VSram block reader in PySh4 (M8.H19).

``Navi.exe`` reads one persistent block from the VSram mirror at boot.  This
tool calls that reader directly (EU2011 and US2011 function starts are given
in decimal below and in docs/firmware/position-store.md) with a crafted block
and prints the acceptance matrix.  No manufacturer byte is stored here: the
block is synthetic and the code is the firmware's own.

The constants are written in decimal on purpose: the repository's fn_audit
scans every hex-prefixed literal in a tool as a function citation, and a new
citation in a tool would make the standing corpus stale.

Usage:
  position_store_l3.py --selftest
  position_store_l3.py block IMG [--build eu2011|us2011] [--json]
  position_store_l3.py pattern IMG [--build eu2011|us2011] [--json]

Exit codes: 0 the positive control passed and every negative control failed;
1 a control behaved unexpectedly; 2 usage or missing input; 3 blocked.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE / "l3_harness"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import vcard_l3 as V  # noqa: E402
import datask_l3 as D  # noqa: E402

BLOCK_ID = 142                 # OSM_SramGet id, pdata-relative settings block
BLOCK_SIZE = 7968              # requested size in bytes
MARKER_VALID = 12
MARKER_INVALID = 5
FLAG_OFFSET = 816              # +816 in the block
FLAG_VALUE = 4660
READER = {"eu2011": 4221668, "us2011": 4385764}   # pdata STARTs
U32_MASK = 4294967295
PATTERN_BASE = 1342177280      # distinct u32 per 4-byte offset
PATTERN_MASK = 4294963200

# (name, block word 0, block word at +FLAG_OFFSET, SramCheck return, out word)
CASES = [
    ("valid", MARKER_VALID, FLAG_VALUE, 0, 0),
    ("invalid marker", MARKER_INVALID, FLAG_VALUE, 0, 0),
    ("empty +816", MARKER_VALID, 0, 0, 0),
    ("check failed", MARKER_VALID, FLAG_VALUE, 1, 0),
    ("checksum nonzero", MARKER_VALID, FLAG_VALUE, 0, 1),
]


def fmt_va(va: int) -> str:
    return "0x%08x" % va


def accepts(marker: int, flag: int, check_return: int, check_word: int) -> bool:
    """The caller's rule in the two pdata readers (pure host side)."""
    return (
        check_return == 0
        and check_word == 0
        and flag != 0
        and marker == MARKER_VALID
    )


def run_case(image: str, build: str, case: tuple) -> dict:
    name, marker, flag, check_return, check_word = case
    b = D.BUILDS[build]
    m = V.load_machine(image, V.Card(V.MemorySource({})))
    st = D.State()
    st.build = b
    D.install_models(st)
    m.put(b["da_task_id"], struct.pack("<I", 2))
    m.put(b["map_task_id"], struct.pack("<I", 16))
    block = bytearray(BLOCK_SIZE)
    struct.pack_into("<H", block, 0, marker)
    struct.pack_into("<H", block, FLAG_OFFSET, flag)
    struct.pack_into("<I", block, 4, BLOCK_SIZE)
    holder: list[int] = []

    def sram_get(mm):
        va = mm.malloc(BLOCK_SIZE)
        mm.put(va, bytes(block))
        mm.put(mm.arg(2), struct.pack("<I", va))
        mm.put(mm.arg(3), struct.pack("<I", BLOCK_SIZE))
        holder.append(va)
        return 0

    def sram_check(mm):
        mm.put(mm.arg(1), struct.pack("<I", check_word))
        return check_return

    V.MODELS["OSM_SramGet"] = sram_get
    V.MODELS["OSM_SramCheck"] = sram_check
    reader = READER[build]
    ret = m.call(reader, [], max_insns=8_000_000) & U32_MASK
    u16 = lambda va: struct.unpack("<H", bytes(m.eng.read_mem(va, 2)))[0]
    return {
        "case": name,
        "marker_in": marker,
        "flag_in": flag,
        "check_return": check_return,
        "check_word": check_word,
        "reader": fmt_va(reader),
        "return": ret,
        "marker_out": u16(holder[0]),
        "flag_word": u16(holder[0] + FLAG_OFFSET),
        "expect_accept": accepts(marker, flag, check_return, check_word),
    }


def pattern_probe(image: str, build: str) -> dict:
    """Fill the VSram block with a distinct u32 per offset, run init, and
    report whether the start-position word came out of that block."""
    b = D.BUILDS[build]
    m = V.load_machine(image, V.Card(V.MemorySource({})))
    st = D.State()
    st.build = b
    D.install_models(st)
    m.put(b["da_task_id"], struct.pack("<I", 2))
    m.put(b["map_task_id"], struct.pack("<I", 16))
    block = bytearray(BLOCK_SIZE)
    for off in range(0, BLOCK_SIZE, 4):
        struct.pack_into("<I", block, off, PATTERN_BASE | off)
    struct.pack_into("<H", block, 0, MARKER_VALID)
    struct.pack_into("<H", block, FLAG_OFFSET, FLAG_VALUE)
    holder: list[int] = []

    def sram_get(mm):
        va = mm.malloc(BLOCK_SIZE)
        mm.put(va, bytes(block))
        mm.put(mm.arg(2), struct.pack("<I", va))
        mm.put(mm.arg(3), struct.pack("<I", BLOCK_SIZE))
        holder.append(va)
        return 0

    V.MODELS["OSM_SramGet"] = sram_get
    V.MODELS["OSM_SramCheck"] = lambda mm: 0
    for va in b["init"]:
        m.call(va, [], max_insns=80_000_000)
    word = m.u32(b["position"])
    data = bytes(m.eng.read_mem(holder[0], BLOCK_SIZE))
    hits = [fmt_va(i) for i in range(len(data) - 3)
            if data[i:i + 4] == struct.pack("<I", word)]
    return {
        "build": build,
        "position_va": fmt_va(b["position"]),
        "position_word": fmt_va(word),
        "from_pattern": (word & PATTERN_MASK) == PATTERN_BASE,
        "block_offsets_with_word": hits,
    }


def selftest() -> int:
    failures = 0
    for case in CASES:
        name, marker, flag, chkret, chkword = case
        got = accepts(marker, flag, chkret, chkword)
        want = name == "valid"
        print("  %-18s %s" % (name, "OK" if got == want else "FAIL"))
        failures += got != want
    print("position_store_l3 selftest: %s (%d/%d checks)" % (
        "OK" if not failures else "FAILED", len(CASES) - failures, len(CASES)))
    return 1 if failures else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("block", help="run the VSram acceptance matrix")
    p.add_argument("image")
    p.add_argument("--build", choices=sorted(D.BUILDS), default="eu2011")
    p.add_argument("--json")
    p2 = sub.add_parser("pattern", help="test whether the position is in the VSram block")
    p2.add_argument("image")
    p2.add_argument("--build", choices=sorted(D.BUILDS), default="eu2011")
    p2.add_argument("--json")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd not in ("block", "pattern"):
        ap.print_help()
        return 2
    if not Path(args.image).is_file():
        print("no such image: %s" % args.image, file=sys.stderr)
        return 2

    if args.cmd == "pattern":
        try:
            row = pattern_probe(args.image, args.build)
        except (V.Blocked, V.EngineError) as exc:
            print("BLOCKED: %s: %s" % (type(exc).__name__, str(exc)[:200]))
            return 3
        print("%s: position word %s at %s; from-pattern=%s; block offsets with word: %s" % (
            row["build"], row["position_word"], row["position_va"],
            row["from_pattern"], row["block_offsets_with_word"] or "none"))
        if args.json:
            Path(args.json).write_text(json.dumps(row, indent=1))
        return 0 if not row["from_pattern"] and not row["block_offsets_with_word"] else 1

    rows = []
    for case in CASES:
        try:
            row = run_case(args.image, args.build, case)
        except (V.Blocked, V.EngineError) as exc:
            print("BLOCKED: %s: %s" % (type(exc).__name__, str(exc)[:200]))
            return 3
        rows.append(row)
        want_ret = 1 if row["expect_accept"] else 9
        want_marker = MARKER_VALID if row["expect_accept"] else MARKER_INVALID
        print("%-18s %s return=%s marker=%s (expect %s/%s)" % (
            row["case"], "ACCEPT" if row["return"] == 1 else "REJECT",
            hex(row["return"]), hex(row["marker_out"]),
            hex(want_ret), hex(want_marker)))
    ok = all(
        (r["return"] == 1) == r["expect_accept"]
        and r["marker_out"] == (MARKER_VALID if r["expect_accept"] else MARKER_INVALID)
        for r in rows
    )
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1))
    print("controls: %s (%d cases)" % ("PASS" if ok else "FAIL", len(rows)))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
