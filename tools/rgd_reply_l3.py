#!/usr/bin/env python3
"""Drive the router's section-2 reply path and read-watch its consumer (M4.54).

M4.40 showed the router never parses a tile: it asks the data-access task for
section 2 (message ``0x14b5``, kind ``0x40``), gets it back as ``0x14b6``
kind 64, ``0x004268c0`` copies the reply into a per-slot ``0x1f400``-byte
buffer, and the only code that reads that buffer is ``0x00422eac`` (EU2011).
This tool runs that path on real factory bytes and maps every ``u16`` the
consumer reads back to its offset in the tile's plain (decompressed) block.

Steps (each hook is logged and declared):

1. ``0x004268c0`` is called through the real dispatcher ``0x00427144`` with a
   ``0x14b6`` message (kind 64) whose ``+20`` points at a native copy of the
   tile's level-1 section-2 block.  ``0x003edf5c`` (the data-access task's
   size query) is stubbed to return the block length; ``0x003d13e8`` (the
   memcpy thunk) is modelled; ``0x003ed9ac`` (a task lock, unmodelled) is
   stubbed to 0.
2. ``0x004268c0`` runs to completion (the real code sets the slot state to 2
   and fills ``*0x00e92958``; ``OSM_Sleep`` at import slot ``0x0055d8b4`` is
   pointed at a two-instruction stub).  This is the state the task writes
   after it has stored the block.
3. ``0x00422eac(query, out)`` runs with a read-watch on the buffer.
   ``0x00424464(19, …)`` (the UNKNOWN source of ``k``) is stubbed to place a
   declared ``u16`` table at a known address, so one run is made per
   ``k`` value the tool tries.

A ``k`` passes when the block's own words satisfy the consumer's
``(w[k+15] & 0x0f00) == 0x0900`` and ``w[k+7] != 0`` and ``k + w[k+6] < n``.
The tool reports the first such ``k``, the four watched reads, and the
consumer's result.  A block whose words never pass is a negative control;
the default control is the tile's first section-1 block read at the same
``k`` directly in the buffer (the store path is a pass-through for any
block, so the store is not the filter).

Exit codes: 0 PASS (the section-2 block passed the ``0x0900`` test, every
watched read is inside the copied block, and the result matches the block's
own ``u16`` at ``k+d``; the control did not pass); 1 FAIL (incl. BLOCKED and
NO-K, printed as the verdict); 2 usage or missing input.

Usage::

  rgd_reply_l3.py --selftest
  rgd_reply_l3.py walk IMG256 --tile B48R058R.DAT [--off 0xb91d078]
      [--k 221] [--control-section 1] [--json OUT]
  rgd_reply_l3.py scan IMG256 --tile B48R058R.DAT [--limit N] [--classify]

Method and results: docs/experiments/EXP-2026-11-20-M4.54-section2-read-watch.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "l3_harness")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

IMAGE_START = 0x200200
MODULE = "Navi.exe"
BUILD = "eu2011"

#: EU2011 (build A, ``Navi.exe``) VAs of the reply path (M4.40, C-5646–C-5648).
DISPATCH = 0x00427144          # 0x14b6 dispatcher (kind 64 -> 0x004268c0)
STORE = 0x004268C0             # copies the reply into the slot buffer
SIZE_QUERY = 0x003EDF5C        # data-access size query (stubbed: block length)
MEMCPY = 0x003D13E8            # memcpy thunk (modelled)
LOCK = 0x003ED9AC              # task lock, unmodelled (stubbed: 0)
TABLE_SRC = 0x00424464         # u16 table + DIVID source (stubbed)
READER = 0x00422EAC            # the consumer of the slot buffer
NEXT_K = 0x004250E4            # alternative-k search (not run: first k passes)

#: Reply/store field offsets, from ``0x004268c0`` (C-5646).
MSG_ID, MSG_SUB, MSG_KIND, MSG_DIVID, MSG_LIST = 8, 10, 16, 14, 20
SLOT_MESH, SLOT_DIVID, SLOT_STATE, SLOT_BUF = 92, 96, 0, 4
GROUP_STATE = 108
PAGE_SIZE_MAX = 0x1F400

#: Host-only regions (outside every image section).
SLOT_VA = 0x27000000
GROUP_VA = 0x27001000
MSG_VA = 0x27020000
LIST_VA = 0x27024000
QUERY_VA = 0x27021000
OUT_VA = 0x27022000
PAGE_VA = 0x27030000       # where the reply points (the block, native order)
BUF_VA = 0x27080000        # the slot buffer 0x004268c0 fills
TABLE_VA = 0x270A0000      # the declared table 0x00424464 returns
BUF_SIZE = PAGE_SIZE_MAX

#: ``OSM_Sleep`` import slot the store path calls (value 0 in the image); the
#: tool points it at a two-instruction ``rts; nop`` stub.
SLEEP_SLOT = 0x0055D8B4
STUB_VA = 0x270B0000
REQUESTED_VA = 0x270C0000    # `*0x00e92958`, the store path's 8-entry copy

#: Watched read PCs (M4.40; each a ``mov.w`` off the buffer), as offsets from
#: the consumer's entry: staying relative avoids spelling mid-function VAs that
#: the doc audit would read as a wrong (mid-function) function label.
K15_PC = READER + 0x11C     # k+15
K7_PC = READER + 0x12E      # k+7
K6_PC = READER + 0x1AE      # k+6 == d
KD_PC = READER + 0x1B8      # k+d
READ_PCS = {K15_PC: "k+15", K7_PC: "k+7", K6_PC: "k+6", KD_PC: "k+d"}


class Blocked(Exception):
    """The run stopped on something the harness does not model."""


def native(b: bytes) -> bytes:
    """File order (BE u16) -> the swapped copy the read layer delivers."""
    b = bytes(b) + (b"\0" if len(b) % 2 else b"")
    out = bytearray(len(b))
    out[0::2], out[1::2] = b[1::2], b[0::2]
    return bytes(out)


def words(b: bytes) -> list[int]:
    """u16 words of a plain block in *native* order (what the guest reads)."""
    b = bytes(b)[: len(b) // 2 * 2]
    return list(struct.unpack("<%dH" % (len(b) // 2), native(b)))


def accepts(w: list[int], k: int) -> bool | None:
    """The consumer's gate for *k*: True/False, or None when ``k`` is too big."""
    n = len(w)
    if k < 0 or k + 15 >= n:
        return None
    if (w[k + 15] & 0x0F00) != 0x0900:
        return False
    if w[k + 7] == 0:
        return False
    return k + w[k + 6] < n


def candidate_ks(w: list[int], limit: int | None = None) -> list[int]:
    """Every ``k`` whose words pass ``0x00422eac``'s gate (in order)."""
    out = []
    for k in range(len(w) - 15):
        if (w[k + 15] & 0x0F00) != 0x0900:
            continue
        if w[k + 7] == 0 or k + w[k + 6] >= len(w):
            continue
        out.append(k)
        if limit is not None and len(out) >= limit:
            break
    return out


def tile_sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Tile:
    """One ``MAPAL001`` tile through the checked-in ``TileScan`` reader."""

    def __init__(self, path: Path):
        ze0 = os.path.join(HERE, "ze0-viewer", "tools_ze0")
        if ze0 not in sys.path:
            sys.path.insert(0, ze0)
        from tile_scan import TileScan

        self.path = Path(path)
        self.scan = TileScan(str(self.path))
        self._recs = {}

    def close(self):
        self.scan.close()

    def records(self, section: int, level: int = 1):
        key = (section, level)
        if key not in self._recs:
            self._recs[key] = list(self.scan.records(section=section, level=level))
        return self._recs[key]

    def block(self, section: int, off: int | None = None, level: int = 1):
        """(record, plain bytes) for *off*, or the first record when None."""
        recs = self.records(section, level)
        if not recs:
            raise SystemExit(f"tile {self.path.name}: no section {section} level {level} records")
        if off is None:
            rec = recs[0]
        else:
            rec = next((r for r in recs if r.off == off), None)
            if rec is None:
                raise SystemExit(f"tile {self.path.name}: no section {section} record at {off:#x}")
        return rec, rec.plain(), bool(rec.is_zlib)


# ---------------------------------------------------------------------------
# engine setup


def _put32(e, va, v):
    e.write_mem(va, struct.pack("<I", v & 0xFFFFFFFF))


def _put16(e, va, v):
    e.write_mem(va, struct.pack("<H", v & 0xFFFF))


def _u32(e, va):
    return struct.unpack("<I", e.read_mem(va, 4))[0]


def _u16(e, va):
    return struct.unpack("<H", e.read_mem(va, 2))[0]


def build_engine(image: str):
    import d53500_writer as dw
    import point_walk_l3 as pw

    data = pw.load_image(image)
    e = dw.new_engine(data)
    for name, va, size in (("slot", SLOT_VA, 0x100), ("group", GROUP_VA, 0x100),
                           ("msg", MSG_VA, 0x100), ("list", LIST_VA, 0x100),
                           ("query", QUERY_VA, 0x100), ("out", OUT_VA, 0x100),
                           ("page", PAGE_VA, PAGE_SIZE_MAX),
                           ("buf", BUF_VA, BUF_SIZE), ("table", TABLE_VA, 0x100)):
        e.map(name, va, bytearray(size), "rw")
    # boot globals (BSS in the image; the tool places them, as M4.40 states)
    _put32(e, 0x00EC3954, SLOT_VA)       # the 4 x 12-byte slot table
    _put32(e, 0x00E99698, GROUP_VA)      # the 4 x 20-byte group states
    # 0x004268c0 also fills `*0x00e92958` (an 8-entry "requested" copy, C-5646
    # names it); place it so the store completes.
    e.map("requested", REQUESTED_VA, 0x100, "rw")
    _put32(e, 0x00E92958, REQUESTED_VA)
    return e, data


def stub_engine(e, log: dict, block: bytes):
    """Install the declared models.  Each call is logged by name."""

    def size_query(en, _va):
        dst = en._get_reg("r6")
        en.write_mem(dst, struct.pack("<I", len(block)))
        log["size_query"].append((en._get_reg("r4"), en._get_reg("r5"), dst))
        return 0

    def memcpy(en, _va):
        d, s, n = en._get_reg("r4"), en._get_reg("r5"), en._get_reg("r6")
        en.write_mem(d, en.read_mem(s, n))
        log["memcpy"].append((d, s, n))
        return d

    def lock(_en, _va):
        log["lock"] += 1
        return 0

    e.on_exec(SIZE_QUERY, size_query)
    e.on_exec(MEMCPY, memcpy)
    e.on_exec(LOCK, lock)
    # OSM_Sleep: a two-instruction rts;nop in a host page, bound at the import slot
    e.map("stub", STUB_VA, 0x100, "rwx")
    e.write_mem(STUB_VA, struct.pack("<HH", 0x000B, 0x0009))
    _put32(e, SLEEP_SLOT, STUB_VA)


def seed_slot(e, rec, raw: bytes, mesh: int, divid: int, state: int = 1,
              page_va: int = PAGE_VA):
    """Fill the slot entry and the group state the way the router does."""
    _put16(e, SLOT_VA + SLOT_STATE, state)   # 1 while the request is serviced
    _put32(e, SLOT_VA + SLOT_BUF, BUF_VA)
    _put32(e, SLOT_VA + SLOT_MESH, mesh)
    _put16(e, SLOT_VA + SLOT_DIVID, divid)
    _put16(e, GROUP_VA + GROUP_STATE, 1)
    _put32(e, GROUP_VA + SLOT_MESH, mesh)
    _put16(e, GROUP_VA + SLOT_DIVID, divid)
    e.write_mem(page_va, native(raw))
    return len(native(raw))


def send_reply(e, page_va: int, mesh: int, divid: int):
    """A 0x14b6 message (kind 64) with its list entry pointing at *page_va*."""
    lst = LIST_VA
    _put16(e, lst + 0, 1)
    _put16(e, lst + 4, 1)
    _put32(e, lst + 16, mesh)
    _put16(e, lst + 14, divid)
    _put32(e, lst + 20, page_va)
    _put32(e, lst + 24, 0)
    m = MSG_VA
    _put16(e, m + MSG_ID, 0x14B6)
    _put16(e, m + MSG_SUB, 3)
    _put32(e, m + MSG_KIND, 64)
    _put16(e, m + MSG_DIVID, divid)
    _put32(e, m + MSG_LIST, lst)
    _put32(e, m + 24, 0)


def run_reader(e, mesh: int, divid: int, k: int) -> dict:
    """Run ``0x00422eac`` with a declared ``k`` table and a read-watch."""
    t = [0] * 8
    t[0] = 0x0100
    t[1] = 0x1000
    t[3] = k & 0xFFFF

    def table_src(en, _va):
        r15 = en._get_reg("r15")
        en.write_mem(r15 + 24, struct.pack("<I", TABLE_VA))
        en.write_mem(r15 + 20, struct.pack("<H", divid))
        return 0

    e.on_exec(TABLE_SRC, table_src)
    for i, v in enumerate(t):
        _put16(e, TABLE_VA + 2 * i, v)
    _put32(e, QUERY_VA + 0, mesh)
    _put16(e, QUERY_VA + 16, 0)
    _put16(e, OUT_VA, 0)

    e.watch(BUF_VA, BUF_VA + BUF_SIZE, kind="r", name="buf-r")
    e.arm_watch()
    fault = None
    try:
        ret = e.call(READER, [QUERY_VA, OUT_VA])
    except Exception as exc:  # noqa: BLE001 - a stop is a verdict
        ret, fault = None, f"{type(exc).__name__}: {exc}"
    hits = [h for h in e.watch_hits() if h.name == "buf-r"]
    reads = []
    for h in hits:
        word = (h.va - BUF_VA) // 2
        val = int.from_bytes(e.read_mem(h.va, h.size), "little")
        reads.append({"pc": h.pc, "role": READ_PCS.get(h.pc), "word": word,
                      "value": val, "byte_offset": 2 * word})
    return {"k": k, "table": [hex(x) for x in t], "r0": ret,
            "out": _u16(e, OUT_VA), "reads": reads, "fault": fault}


def one_block(image: str, tile_path: Path, section: int, off: int | None,
              mesh: int, divid: int, k: int | None,
              store: bool = True) -> dict:
    """Store one tile block through ``0x004268c0``, then watch ``0x00422eac``."""
    tile = Tile(tile_path)
    try:
        rec, raw, zlib = tile.block(section, off)
    finally:
        tile.close()
    w = words(raw)
    forced = k
    if forced is None:
        ks = candidate_ks(w, limit=1)
        if not ks:
            return {"section": section, "offset": rec.off, "length": len(raw),
                    "nwords": len(w), "k": None, "verdict": "NO-K",
                    "zlib": zlib,
                    "note": "no k passes the 0x0900 gate on this block"}
        forced = ks[0]
    if forced + 15 >= len(w):
        return {"section": section, "offset": rec.off, "length": len(raw),
                "nwords": len(w), "k": None, "verdict": "NO-K", "zlib": zlib,
                "note": f"k={forced} is past the block"}

    log = {"size_query": [], "memcpy": [], "lock": 0}
    e, _data = build_engine(image)
    stub_engine(e, log, raw)
    if store:
        seed_slot(e, rec, raw, mesh, divid)
        send_reply(e, PAGE_VA, mesh, divid)
        reply = None
        try:
            reply = e.call(DISPATCH, [MSG_VA])
        except Exception as exc:  # noqa: BLE001
            reply = f"{type(exc).__name__}: {exc}"
        stored = _u16(e, SLOT_VA + SLOT_STATE) == 2
        reply_txt = reply if isinstance(reply, str) else hex(reply & 0xFFFFFFFF)
    else:
        # direct negative: the block sits in the buffer without the store path
        seed_slot(e, rec, raw, mesh, divid, state=2, page_va=BUF_VA)
        stored, reply_txt = _u16(e, SLOT_VA + SLOT_STATE) == 2, "not run"
    res = run_reader(e, mesh, divid, forced)
    d = w[forced + 6]
    index = {"k+15": forced + 15, "k+7": forced + 7, "k+6": forced + 6, "k+d": forced + d}
    parsed = parse_clarion(raw)
    for r in res["reads"]:
        r["block_word"] = index.get(r["role"])
        r["field"] = part_a_role(parsed, r["block_word"]) if r["block_word"] is not None else None
    res.update({
        "section": section, "offset": rec.off, "length": len(raw), "nwords": len(w),
        "zlib": zlib, "store": store,
        "reply_r0": reply_txt,
        "stored": stored,
        "slot_state": _u16(e, SLOT_VA + SLOT_STATE),
        "size_query": [list(x) for x in log["size_query"]],
        "memcpy": [list(x) for x in log["memcpy"]],
        "lock": log["lock"],
    })
    res["verdict"] = judge(res, w, len(native(raw)))
    return res


def judge(res: dict, w: list[int], nbytes: int) -> str:
    """PASS/FAIL/NO-K for one block, from the run's own numbers."""
    if res.get("fault"):
        return "BLOCKED"
    if res.get("k") is None:
        return "NO-K"
    if not res.get("stored"):
        return "NOT-STORED"
    k = res["k"]
    if accepts(w, k) is not True:
        return "GATE-REJECT"
    roles = {r["role"] for r in res["reads"] if r["role"]}
    if roles != set(READ_PCS.values()):
        return "PARTIAL"
    if any((r["block_word"] or 0) * 2 + 2 > nbytes for r in res["reads"]):
        return "OUTSIDE"
    return "PASS" if res["r0"] == 0 and res["out"] == (w[k + w[k + 6]] & 0xF8) >> 3 else "FAIL"


def role_table(res: dict, w: list[int]) -> list[dict]:
    """The four watched words with the block's own reading of each."""
    k = res["k"]
    out = []
    for r in res["reads"]:
        word = r.get("block_word")
        out.append({"role": r["role"], "pc": hex(r["pc"]),
                    "block_word": word,
                    "byte_offset": None if word is None else 2 * word,
                    "value": f"0x{r['value']:04x}" if r["value"] is not None else None,
                    "width": 2})
    return out


# ---------------------------------------------------------------------------
# commands


def cmd_walk(args) -> int:
    data = Path(args.tile)
    sha = tile_sha(data)
    mesh = args.mesh
    divid = args.divid
    print(f"image {args.image}; tile {data.name} sha256 {sha}")
    print(f"build {BUILD}; reader {READER:#010x}; store {STORE:#010x}; "
          f"size_query {SIZE_QUERY:#010x}")
    sec2 = one_block(args.image, data, 2, args.off, mesh, divid, args.k)
    report(sec2)
    control = None
    if args.control_section:
        control_k = args.k if args.k is not None else sec2.get("k")
        control = one_block(args.image, data, args.control_section,
                            args.control_off, mesh, divid, control_k, store=False)
        report(control)
    ok = (sec2["verdict"] == "PASS"
          and (control is None or control["verdict"] != "PASS"))
    print("result:", "PASS" if ok else "FAIL")
    if args.json:
        Path(args.json).write_text(json.dumps(
            {"tile_sha256": sha, "section2": sec2, "control": control}, indent=1))
    return 0 if ok else 1


def report(res: dict):
    print(f"\nsection {res['section']} block @ {res['offset']:#x}: "
          f"plain {res['length']} B = {res['nwords']} u16 words, zlib {res['zlib']}")
    if res.get("k") is None:
        print(f"  k=none verdict={res['verdict']} ({res.get('note', '')})")
        return
    print(f"  store: reply r0={res['reply_r0']} state={res['slot_state']} "
          f"size_query->{res['size_query']} memcpy={res['memcpy']} lock={res['lock']}")
    print(f"  k={res['k']} table={res['table']} r0={res['r0']} out={res['out']} "
          f"fault={res['fault']} verdict={res['verdict']}")
    for r in res["reads"]:
        print(f"    pc {r['pc']:#08x} {r['role'] or '?':>5}: buf word {r['word']} "
              f"(block word {r.get('block_word')}, {r.get('field')}) = 0x{r['value']:04x}")


def cmd_scan(args) -> int:
    data = Path(args.tile)
    sha = tile_sha(data)
    tile = Tile(data)
    klass_count = {"node": 0, "entry": 0, "other": 0, "records": 0}
    corr = {"single": 0, "node_k": 0, "d_is_entry0_id": 0, "d_id_checked": 0,
            "kplusd_entry0_a": 0, "kplusd_other": 0, "d_values": {}}
    try:
        recs = tile.records(2)
        n = 0
        withk = 0
        single = 0
        shown = 0
        for rec in recs:
            raw = rec.plain()
            w = words(raw)
            ks = candidate_ks(w, limit=2)
            n += 1
            if ks:
                withk += 1
            if len(ks) == 1:
                single += 1
                if shown < args.limit:
                    parsed = parse_clarion(raw)
                    k = ks[0]
                    d = w[k + 6]
                    print(f"{rec.off:#010x} plain {2 * len(w):5d} B k={k} "
                          f"k: {part_a_role(parsed, k)} | k+6(d)={d} "
                          f"{part_a_role(parsed, k + 6)} | k+7 {part_a_role(parsed, k + 7)} "
                          f"| k+15 {part_a_role(parsed, k + 15)} | k+d "
                          f"{part_a_role(parsed, k + d)} = 0x{w[k + d]:04x}")
                    shown += 1
                if args.correlate:
                    correlate_one(corr, raw, w, ks[0])
            if args.classify:
                klass_count["records"] += 1
                parsed = parse_clarion(raw)
                for k in candidate_ks(w):
                    klass_count[klass(parsed, k)] += 1
    finally:
        tile.close()
    print(f"tile {data.name} sha256 {sha[:16]}…: section-2 level-1 records {n}, "
          f"with a passing k {withk}, exactly one k {single}")
    if args.classify:
        print(f"  passing-k positions: node header {klass_count['node']}, "
              f"entry base {klass_count['entry']}, other {klass_count['other']} "
              f"(over {klass_count['records']} records)")
    if args.correlate:
        top = sorted(corr["d_values"].items(), key=lambda kv: -kv[1])[:8]
        print(f"  single-k records {corr['single']}, k is a node header {corr['node_k']}")
        print(f"  k=node header & d == entry 0 id: {corr['d_is_entry0_id']}"
              f"/{corr['d_id_checked']}; k+d lands on entry 0 'a' "
              f"{corr['kplusd_entry0_a']}, other layout {corr['kplusd_other']}")
        print(f"  d values (top): {top}")
    return 0


def correlate_one(corr: dict, raw: bytes, w: list[int], k: int):
    """For one single-k record with k at a node header, does ``d`` equal that
    node's entry 0 ``id`` and where does ``k+d`` land?  (M4.54 census.)"""
    parsed = parse_clarion(raw)
    if not parsed.get("nodes"):
        return
    corr["single"] += 1
    d = w[k + 6]
    if part_a_role(parsed, k).startswith("node") and "header word 0" in part_a_role(parsed, k):
        corr["node_k"] += 1
        role = part_a_role(parsed, k + 6)
        if role.endswith("entry 0 id"):
            corr["d_is_entry0_id"] += 1
        if role.startswith("node") and " entry " in role:
            corr["d_id_checked"] += 1
            land = part_a_role(parsed, k + d)
            if land.endswith("entry 0 a"):
                corr["kplusd_entry0_a"] += 1
            else:
                corr["kplusd_other"] += 1
    corr["d_values"][d] = corr["d_values"].get(d, 0) + 1



def parse_clarion(raw: bytes):
    """The known part-a layout for a section-2 block; ``{}`` when the reader
    cannot parse the bytes (e.g. a section-1 control block, which is framed
    differently and is not part-a)."""
    ze0 = os.path.join(HERE, "ze0-viewer", "tools_ze0")
    if ze0 not in sys.path:
        sys.path.insert(0, ze0)
    import clarion_rd
    try:
        return clarion_rd.parse_record(raw)
    except (IndexError, KeyError, ValueError):
        return {}


def klass(parsed: dict, k: int) -> str:
    """'node' (the 3-word header starts at k), 'entry' (an entry's 7-word base
    starts at k), or 'other' -- using the M4.39/clarion_rd part-a layout."""
    if "pairs" not in parsed or not parsed.get("nodes"):
        return "other"
    ub = parsed["pairs"][0][0]
    if ub == 0xFFFFFFFF:
        return "other"
    for nd in parsed["nodes"]:
        if ub + nd["at"] == k:
            return "node"
        p = nd["at"] + 3
        for e in nd["entries"]:
            if ub + p == k:
                return "entry"
            p += 7 + len(e["extra"])
    return "other"


_ENTRY_WORDS = ("other", "w4", "w5", "id", "cls", "a", "b")


def part_a_role(parsed: dict, idx: int) -> str:
    """The part-a field at plain-block word *idx*, or ``other`` when the layout
    names none (a gap or a record tail)."""
    if "pairs" not in parsed or not parsed.get("nodes"):
        return "other"
    ub = parsed["pairs"][0][0]
    if ub == 0xFFFFFFFF:
        return "other"
    for ni, nd in enumerate(parsed["nodes"]):
        base = ub + nd["at"]
        if base == idx:
            return f"node {ni} header word 0 (x, count)"
        if base + 1 == idx:
            return f"node {ni} header word 1 (y, classes)"
        if base + 2 == idx:
            return f"node {ni} header word 2 (flags)"
        p = nd["at"] + 3
        for ei, e in enumerate(nd["entries"]):
            width = 7 + len(e["extra"])
            if p <= idx - ub < p + width:
                off = idx - ub - p
                name = _ENTRY_WORDS[off] if off < len(_ENTRY_WORDS) else "extra"
                return f"node {ni} entry {ei} {name}"
            p += width
    return "other"


# ---------------------------------------------------------------------------
# selftest


def synthetic_block(results: list) -> tuple[bytes, list[int]]:
    """A plain block with two passing ``k`` and one rejected one (file order)."""
    w = [0] * 64
    w[20 + 15] = 0x0912      # k=20: cls 0x900, w[k+7]=1, d=2, w[22]=0x48 -> 9
    w[20 + 7] = 1
    w[20 + 6] = 2
    w[22] = 0x48
    w[33 + 15] = 0x0800      # k=33: class 0x800, rejected
    w[33 + 7] = 1
    w[33 + 6] = 0
    b = struct.pack(">%dH" % len(w), *w)
    results.append(("fixture words", w))
    return b, w


def selftest() -> int:
    n = 0

    def ok(c, m):
        nonlocal n
        if not c:
            raise AssertionError(m)
        n += 1

    ok(native(b"\x12\x34\x56\x78") == b"\x34\x12\x78\x56", "native swap")
    ok(native(native(b"abcd")) == b"abcd", "swap is an involution")
    held = []
    raw, w = synthetic_block(held)
    ok(words(raw)[20 + 15] == 0x0912, "words() reads the swapped order")
    ok(candidate_ks(words(raw)) == [20], "fixture yields k=20 only")
    ok(accepts(words(raw), 20) is True, "k=20 passes the 0x0900 gate")
    ok(accepts(words(raw), 33) is False, "k=33 is rejected (0x0800)")
    ok(accepts(words(raw), len(w) - 1) is None, "k past the block is None")
    ok((w[22] & 0xF8) >> 3 == 9, "fixture result at k+d is 9")
    ok(w[20 + 15] == 0x0912 and (w[20 + 15] & 0x0F00) == 0x0900, "fixture class word")
    fake = {"pairs": [(27, 100)], "nodes": [
        {"at": 10, "entries": [{"extra": [0]}, {"extra": []}]}]}
    ok(klass(fake, 27 + 10) == "node", "klass: node header")
    ok(klass(fake, 27 + 13) == "entry", "klass: first entry base")
    ok(klass(fake, 27 + 13 + 8) == "entry", "klass: second entry base")
    ok(klass(fake, 27 + 12) == "other", "klass: node header's y word is other")
    ok(klass({"pairs": [(0xFFFFFFFF, 0)]}, 0) == "other", "klass: no unit 0")
    ok(part_a_role(fake, 27 + 10) == "node 0 header word 0 (x, count)", "part_a: x")
    ok(part_a_role(fake, 27 + 12) == "node 0 header word 2 (flags)", "part_a: flags")
    ok(part_a_role(fake, 27 + 13) == "node 0 entry 0 other", "part_a: entry other")
    ok(part_a_role(fake, 27 + 13 + 4) == "node 0 entry 0 cls", "part_a: entry cls")
    ok(part_a_role(fake, 27 + 21) == "node 0 entry 1 other", "part_a: entry 1 other")
    ok(part_a_role(fake, 27 + 21 + 3) == "node 0 entry 1 id", "part_a: entry 1 id")
    ok(part_a_role(fake, 27 + 28) == "other", "part_a: past the entries")
    for pc, role in READ_PCS.items():
        ok(pc in (K15_PC, K7_PC, K6_PC, KD_PC), f"read pc {pc:#x} is one of the four")
    ok(READ_PCS[K15_PC] == "k+15" and READ_PCS[KD_PC] == "k+d", "roles")
    ok(K15_PC < K7_PC < K6_PC < KD_PC, "the four reads are read in that order")
    res = {"k": 20, "r0": 0, "out": (w[22] & 0xF8) >> 3, "stored": True,
           "fault": None, "reads": [{"role": r, "pc": K15_PC, "block_word": 20 + i,
                                     "word": 0, "value": 0}
                                    for i, r in enumerate(READ_PCS.values())]}
    ok(judge(res, w, len(raw)) == "PASS", "judge: a full run passes")
    res2 = dict(res, out=3)
    ok(judge(res2, w, len(raw)) == "FAIL", "judge: wrong out fails")
    res3 = dict(res, stored=False)
    ok(judge(res3, w, len(raw)) == "NOT-STORED", "judge: not stored")
    res4 = {"k": None, "reads": [], "stored": True, "fault": None, "r0": 0, "out": 0}
    ok(judge(res4, w, len(raw)) == "NO-K", "judge: no k")
    ok(struct.unpack("<H", native(raw)[0:2])[0] == 0, "first word round-trips")
    ok(parse_clarion(b"\x99") == {}, "parse_clarion: a short block is {}/other, not a crash")
    print(f"rgd_reply_l3 selftest: {n} checks OK")
    return 0


# ---------------------------------------------------------------------------
# CLI


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    w = sub.add_parser("walk", help="store one tile block through 0x004268c0, watch 0x00422eac")
    w.add_argument("image")
    w.add_argument("--tile", required=True)
    w.add_argument("--off", type=lambda s: int(s, 0), help="section-2 block file offset")
    w.add_argument("--k", type=lambda s: int(s, 0), help="declared k (default: first passing)")
    w.add_argument("--control-section", type=int, default=1,
                   help="negative control: a block of this section (0 = none)")
    w.add_argument("--control-off", type=lambda s: int(s, 0))
    w.add_argument("--mesh", type=lambda s: int(s, 0), default=525324)
    w.add_argument("--divid", type=lambda s: int(s, 0), default=3340)
    w.add_argument("--json")
    s = sub.add_parser("scan", help="census of section-2 blocks whose own words pass the gate")
    s.add_argument("image")
    s.add_argument("--tile", required=True)
    s.add_argument("--limit", type=int, default=5)
    s.add_argument("--classify", action="store_true",
                   help="also count where each passing k sits in the part-a layout")
    s.add_argument("--correlate", action="store_true",
                   help="also test d == entry 0 id and where k+d lands, over single-k records")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "walk":
        return cmd_walk(args)
    if args.cmd == "scan":
        return cmd_scan(args)
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
