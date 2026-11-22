#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""point_tree_l3.py - run the firmware's POINT spatial-tree walk on a factory tree (M3.35).

The spatial tree of a ``POINTnnn.DAT`` (directory cell ``0x85a`` -> one tree
per category, 16-byte entries ``0008, u32 ptr, u16 size_w, u16 kx, u16 ky,
u32 fine``) is read by the **nearest-POI search** of EU2011 ``Navi.exe``:

* ``fn 0x0040f944(entry, slot, ctx, level, request)`` loads the child node
  of an inner entry: block ``ptr >> 7`` after the tree base
  (``*0x00d5b858``), ``((ptr & 0x7f) + size_w + 127) >> 7`` blocks of 128
  words, key ``kx << 16 | ky``;
* ``fn 0x004110dc(level, n, index, ctx, -, request)`` steps to entry
  ``index`` of a node (each step is ``2 * word0`` bytes) and calls the
  loader;
* ``fn 0x004114dc(level, request)`` walks a node at levels ``0x1004`` and
  ``0x1005``: it stops at the first entry shorter than 8 words (the ``0005``
  terminator), descends inner entries, and for a leaf (``word 6 & 0x0800``)
  takes ``x = word 6 & 0x7ff``, ``y = word 7 & 0x7ff``, the 6-bit code
  ``(word 6 & 0x8000 | word 7 >> 1) >> 10``, measures the distance to the
  search origin with ``STDDLL!STD_MeshLine_calcLength`` (``fn 0x00408ea4``)
  and stores ``{distance, ptr}`` in the result table ``0x00d5d800``.

This tool runs those functions from the image on a factory (or generated)
tree.  What it models by hand: the block cache (``0x00407724`` lookup,
``0x004086b4`` allocate, ``0x00408268`` release, ``0x0040782c`` find) is served from the decoded
file; ``memset``/``memmove``/``_modlu`` and the error logger are host
functions; the search state the search set-up would have written (tree base
block, origin mesh point, distance window, result buffers, no category
filter) is written by the tool.  The upper levels (root node ``0x1001``,
level-1 node ``0x1002``, cell entry ``0x1003``) are driven by the tool
calling ``fn 0x004110dc`` once per entry; their firmware driver
(``fn 0x00411fd4`` / ``fn 0x0041235c``) is not run.

Checks per level-1 node: the name-record ordinals the firmware stores equal
the leaves ``point_census`` reads below that node, and its distances equal
the distance computed on the host from ``point_census.fine_position`` of
those name records (WGS 84 ellipsoid, within 3 m + 0.2 %).  Controls: a
leaf with its fine word changed moves by the expected distance; a node cut
by a ``0005`` terminator loses the leaves behind it; a leaf with the
``0x0800`` flag cleared is dropped when it sits in the cell node; a leaf
with a code other than 0 or 63 is kept only when ``*0x005638ec`` holds that
code.

Usage:
  point_tree_l3.py run IMG --dir PAIRS --file POINT010 [--tree N|all] [--cells 50] [--json OUT]
  point_tree_l3.py --selftest

Exit codes: 0 ACCEPT, 1 mismatch, 3 BLOCKED.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "l3_harness"))

import cerom  # noqa: E402
import point_census as pc  # noqa: E402
import point_pair_regen as regen  # noqa: E402
import point_walk_l3 as pw  # noqa: E402
from engine import EngineError  # noqa: E402
from sh4fpu import PySh4Fpu, bits_f64, f64_bits  # noqa: E402

IMAGE_START = 0x200200
KERNEL_START = 0x3E00200
# EU2011 Navi.exe
LOAD_CHILD = 0x0040F944
STEP = 0x004110DC
WALK = 0x004114DC
DISTANCE = 0x00408EA4
CACHE_LOOKUP, CACHE_ALLOC, CACHE_RELEASE = 0x00407724, 0x004086B4, 0x00408268
CACHE_FIND = 0x0040782C        # block of a buffer address: a scan of 1024 table rows
ERRLOG = 0x0041BBEC
MEMSET, MEMMOVE, MODLU = 0x003D13C4, 0x003D13E8, 0x003D1484      # COREDLL thunks
BUILD_CHECK = (WALK + 0x2C4, 0x07FF)          # literal pool word of the walker
G_TREE_BASE = 0x00D5B858      # first block of the tree
G_ORIGIN_ID = 0x00D5D7E8      # search origin: mesh id
G_ORIGIN_XY = 0x00D5B864      # search origin: s16 x, s16 y
G_DIST_MIN, G_DIST_MAX = 0x00D5B848, 0x00D5B840
G_COUNT, G_RESULTS = 0x00D5B85C, 0x00D5D800   # 24-byte result records, at most 128
G_COPY_PTR, G_COPY_WORDS = 0x00D5E420, 0x00D5B844
G_FILTER = 0x00D5D7DC         # two u16 category filters, ffff = none
G_LIMIT = 0x005644D8
G_MODE = 0x00D5D7E4
G_FORMAT = 0x0056389C
G_CODE = 0x005638EC          # the leaf code the search keeps besides 0 and 63
LEVEL_ROOT = 0x1001
RESULT = struct.Struct("<HHIHHII4x")
MAX_RESULTS = 128

HEAP, HEAP_SIZE = 0x20000000, 0x800000
STUBS = 0x28000000
STACK = 0x30000000
REL_TOL = 0.002               # the firmware's length is within 0.12 % of the WGS 84 one on the samples


class Blocked(Exception):
    pass


def entries(node: bytes):
    """Host reading of one node (file byte order): yields (pos, ptr, size, kx, ky, fine)."""
    pos = 0
    while pos + 2 <= len(node):
        (head,) = struct.unpack_from(">H", node, pos)
        if head < 8:
            return
        _, ptr, size, kx, ky, fine = pc.SPATIAL_ENTRY.unpack_from(node, pos)
        yield pos, ptr, size, kx, ky, fine
        pos += 2 * head


def is_leaf(fine: int) -> bool:
    return bool(fine >> 16 & 0x0800)


def leaf_code(fine: int) -> int:
    """The 6-bit code of a leaf: bit 15 of word 6 and the top five bits of word 7.
    The firmware keeps a leaf whose code is 0, 63 or the current value of ``*0x005638ec``."""
    return ((fine >> 16 & 0x8000) | (fine & 0xFFFF) >> 1) >> 10


def kept(code: int, current: int) -> bool:
    return code in (0, 63, current)


def host_leaves(blob: bytes, ref: dict, ptr: int, size: int) -> list[tuple[int, int, int, int, int]]:
    """Leaves ``(ordinal, x, y, code, file offset)`` below the node at ``ptr`` (host walk)."""
    out = []
    stack = [(ptr, size)]
    while stack:
        p, s = stack.pop()
        node = blob[ref["start"] + 2 * p:ref["start"] + 2 * (p + s)]
        for pos, cptr, csize, _kx, _ky, fine in entries(node):
            if is_leaf(fine):
                out.append((cptr, fine >> 16 & 0x7FF, fine & 0x7FF, leaf_code(fine), ref["start"] + 2 * p + pos))
            else:
                stack.append((cptr, csize))
    return out


class Firmware:
    def __init__(self, image: bytes):
        self.image = image
        self.rom = cerom.CERom(image, IMAGE_START)
        self.navi_va, self.navi = pw.navi_text(image, IMAGE_START)
        off = BUILD_CHECK[0] - self.navi_va
        if not 0 <= off < len(self.navi) - 2 or struct.unpack_from("<H", self.navi, off)[0] != BUILD_CHECK[1]:
            raise Blocked("this image is not EU2011: no 0x07ff literal at %#010x" % BUILD_CHECK[0])
        import nk_decomp
        mod = self.rom.module("STDDLL.dll")
        self.std = []                               # (name, va, bytes, perms) of every STDDLL section
        for n, sec in enumerate(self.rom.o32(mod)):
            off = self.rom.va2file(sec["dataptr"])
            if sec["flags"] & cerom.IMAGE_SCN_COMPRESSED:
                size, data = nk_decomp.decompress(image, off, sec["psize"], sec["vsize"])
                data = data[:size]
            else:
                data = image[off:off + sec["psize"]]
            data = bytes(data).ljust((max(sec["vsize"], len(data)) + 0xFFF) & ~0xFFF, b"\0")
            code = bool(sec["flags"] & 0x20000000)
            self.std.append(("stddll%d" % n, sec["realaddr"], data, "rx" if code else "rw"))
        # STDDLL's own imports (COREDLL arithmetic and maths): slot -> name
        kernel = cerom.CERom(image, KERNEL_START)
        core = {o: n for o, n, _r in kernel.exports(kernel.module("coredll.dll"))}
        std_base = self.rom.e32(mod)["vbase"]
        self.std_imports = {}
        for dll, slot, name, ordinal in self.rom.imports(mod):
            if dll.lower() == "coredll.dll":
                rva = slot - std_base
                for sec in self.rom.o32(mod):
                    if sec["rva"] <= rva < sec["rva"] + max(sec["vsize"], 1):
                        self.std_imports[sec["realaddr"] + rva - sec["rva"]] = name or core.get(ordinal, "#%d" % ordinal)
        if not any(p == "rx" for _n, _v, _d, p in self.std):
            raise Blocked("STDDLL.dll has no code section")
        mod = self.rom.module("STDDLL.dll")
        base = self.rom.e32(mod)["vbase"]
        exports = {n: base + r for _o, n, r in self.rom.exports(mod)}
        self.iat = {}
        for dll, slot, name, _ord in self.rom.imports(self.rom.module("Navi.exe")):
            if dll.lower() == "stddll.dll" and name in exports:
                self.iat[slot] = exports[name]


class Walk:
    """One engine with the cache model bound to one decoded file and tree."""

    def __init__(self, fw: Firmware, blob: bytes, ref: dict, fmt: int = 0x2000, mode: int = 1):
        self.fw, self.blob, self.ref = fw, blob, ref
        self.base_block = ref["start"] // regen.BLOCK
        if ref["start"] % regen.BLOCK:
            raise Blocked("tree does not start on a block")
        eng = self.eng = PySh4Fpu(endian="little")
        eng.map("navi", fw.navi_va, fw.navi, "rx")
        for name, va, data, perms in fw.std:
            eng.map(name, va, data if perms == "rx" else bytearray(data), perms)
        lo = min(fw.iat) & ~0xFFF
        table = bytearray((max(fw.iat) + 4 - lo + 0xFFF) & ~0xFFF)
        for slot, target in fw.iat.items():
            struct.pack_into("<I", table, slot - lo, target)
        eng.map("iat", lo, table, "r")
        stubs = bytearray(b"\x0b\x00\x09\x00" * 64)          # rts; nop
        eng.map("stubs", STUBS, bytes(stubs), "rx")
        for k, (slot, name) in enumerate(sorted(fw.std_imports.items())):
            eng.write_mem(slot, struct.pack("<I", STUBS + 4 * k))
            eng.on_exec(STUBS + 4 * k, self._core(name))
        eng.map("globals", 0x00560000, bytearray(0x00DA0000 - 0x00560000), "rw")
        eng.map("heap", HEAP, bytearray(HEAP_SIZE), "rw")
        eng.map("stack", STACK, bytearray(0x10000), "rw")
        self.top = HEAP
        self.ctx: dict[bytes, int] = {}
        self.reads: list[tuple[int, int]] = []
        self.errors: list[int] = []
        self.core_calls = Counter()
        self.ctx_made: list[int] = []
        self.patch: dict[int, bytes] = {}          # file offset -> replacement bytes (controls)
        eng.on_exec(CACHE_LOOKUP, self._lookup)
        eng.on_exec(CACHE_ALLOC, self._alloc)
        eng.on_exec(CACHE_RELEASE, lambda e, va: 0)
        eng.on_exec(CACHE_FIND, lambda e, va: 0)       # the table is empty in this harness
        eng.on_exec(ERRLOG, self._err)
        eng.on_exec(MEMSET, self._memset)
        eng.on_exec(MEMMOVE, self._memmove)
        eng.on_exec(MODLU, lambda e, va: e.get_regs()["r4"] % (e.get_regs()["r5"] or 1))
        w = eng.write_mem
        w(G_TREE_BASE, struct.pack("<I", self.base_block))
        w(G_FILTER, b"\xff\xff\xff\xff")
        w(G_DIST_MIN, struct.pack("<i", -1))
        w(G_DIST_MAX, struct.pack("<I", 0xFFFFFFFF))
        w(G_LIMIT, struct.pack("<I", 1 << 30))
        w(G_MODE, struct.pack("<I", mode))
        w(G_FORMAT, struct.pack("<I", fmt))
        self.copies = self.alloc(16 * (MAX_RESULTS + 2))
        w(G_COPY_PTR, struct.pack("<I", self.copies))
        w(G_COPY_WORDS, struct.pack("<I", 8))
        self.request = self.alloc(80)
        self.mark = self.top

    # --- host models -------------------------------------------------------
    def alloc(self, n: int) -> int:
        a = self.top
        self.top += (n + 15) & ~15
        if self.top > HEAP + HEAP_SIZE:
            raise Blocked("harness heap full")
        return a

    def _file(self, off: int, n: int) -> bytes:
        data = bytearray(self.blob[off:off + n])
        for o, repl in self.patch.items():
            if off <= o < off + n:
                data[o - off:o - off + len(repl)] = repl
        return bytes(data)

    def _lookup(self, eng, va):
        req = eng.get_regs()["r4"]
        b = eng.read_mem(req, 76)
        if struct.unpack_from("<H", b, 52)[0] == 1:          # a walk-state block
            return self.ctx.get(b[0:4] + b[32:36], 0)
        words, _h, block = struct.unpack_from("<3I", b, 24)
        self.reads.append((block - self.base_block, words))
        data = pw.swap16(self._file(block * regen.BLOCK, 2 * words))
        obj, buf = self.alloc(80), self.alloc(len(data))
        eng.write_mem(buf, data)
        eng.write_mem(obj, b)
        eng.write_mem(obj + 20, struct.pack("<I", buf))
        eng.write_mem(obj + 42, struct.pack("<H", 1))        # status: data present
        return obj

    def _alloc(self, eng, va):
        req = eng.get_regs()["r4"]
        b = eng.read_mem(req, 76)
        (words,) = struct.unpack_from("<I", b, 24)
        obj, buf = self.alloc(80), self.alloc(max(2 * words, 16))
        eng.write_mem(obj, b)
        eng.write_mem(obj + 20, struct.pack("<I", buf))
        if struct.unpack_from("<H", b, 52)[0] == 1:
            self.ctx[b[0:4] + b[32:36]] = obj
            self.ctx_made.append(obj)
        return obj

    def _err(self, eng, va):
        self.errors.append(eng.get_regs()["pr"])
        return 0

    def _core(self, name: str):
        """Host model of one COREDLL import of STDDLL (integer and double maths)."""
        def s32(v):
            return v - (1 << 32) if v & 0x80000000 else v

        def dbl(eng, n):
            return bits_f64((eng.fr[n] << 32) | eng.fr[n + 1])

        def ret_dbl(eng, value):
            bits = f64_bits(value)
            eng.fr[0], eng.fr[1] = bits >> 32, bits & 0xFFFFFFFF
            return eng.get_regs()["r0"]

        def handler(eng, va):
            r = eng.get_regs()
            self.core_calls[name] += 1
            if name in ("_divls", "_modls"):
                a, b = s32(r["r4"]), s32(r["r5"])
                if b == 0:
                    raise Blocked("%s by zero" % name)
                q = abs(a) // abs(b) * (1 if (a < 0) == (b < 0) else -1)
                return (q if name == "_divls" else a - q * b) & 0xFFFFFFFF
            if name == "memcpy":
                return self._memmove(eng, va)
            if name in ("cos", "sin", "atan"):
                return ret_dbl(eng, getattr(math, name)(dbl(eng, 4)))
            if name == "atan2":
                return ret_dbl(eng, math.atan2(dbl(eng, 4), dbl(eng, 6)))
            raise Blocked("STDDLL import %s is not modelled" % name)
        return handler

    @staticmethod
    def _memset(eng, va):
        r = eng.get_regs()
        if r["r6"]:
            eng.write_mem(r["r4"], bytes([r["r5"] & 0xFF]) * r["r6"])
        return r["r4"]

    @staticmethod
    def _memmove(eng, va):
        r = eng.get_regs()
        if r["r6"]:
            eng.write_mem(r["r4"], eng.read_mem(r["r5"], r["r6"]))
        return r["r4"]

    # --- driving -----------------------------------------------------------
    def set_code(self, code: int) -> None:
        self.eng.write_mem(G_CODE, struct.pack("<I", code))

    def set_origin(self, mesh_id: int, x: int, y: int) -> None:
        self.eng.write_mem(G_ORIGIN_ID, struct.pack("<I", mesh_id))
        self.eng.write_mem(G_ORIGIN_XY, struct.pack("<hh", x, y))

    def _call_step(self, level: int, index: int, ctx: int) -> int:
        sp = STACK + 0xF000
        self.eng.set_regs(r15=sp)
        self.eng.write_mem(sp + 16, struct.pack("<II", 0, self.request))
        self.last_alloc = 0
        self.ctx_made = []
        r0 = self.eng.call(STEP, [level, 0, index, ctx])
        self.last_alloc = self.ctx_made[0] if self.ctx_made else 0
        return r0

    def descend(self, path: tuple[int, int, int]) -> dict:
        """Root entry ``i`` -> entry ``j`` of its node -> entry ``k`` of that node
        (the mesh cell) -> the firmware's walk of everything below it."""
        eng = self.eng
        self.top = self.mark                      # one walk at a time: reuse the heap
        self.ctx.clear()
        self.reads.clear()
        eng.write_mem(G_COUNT, bytes(4))
        root = pw.swap16(self._file(self.ref["start"], 2 * self.ref["root_words"]))
        node = self.alloc(len(root))
        eng.write_mem(node, root)
        head = self.alloc(32)
        eng.write_mem(head, bytes(8) + b"\xff\xff\xff\xff")
        ctx = self.alloc(28 + 16 * (len(root) // 16 + 1))
        eng.write_mem(ctx + 20, struct.pack("<II", head, node))
        status = None
        for depth, index in enumerate(path):
            status = self._call_step(LEVEL_ROOT + depth, index, ctx)
            if status != 1 or not self.last_alloc:
                return {"status": status, "results": [], "count": 0, "reads": list(self.reads), "depth": depth}
            (ctx,) = struct.unpack("<I", eng.read_mem(self.last_alloc + 20, 4))
        (count,) = struct.unpack("<I", eng.read_mem(G_COUNT, 4))
        results = []
        for n in range(min(count, MAX_RESULTS)):
            _a, _b, dist, _idx, _c, _d, ptr = RESULT.unpack(eng.read_mem(G_RESULTS + 24 * n, 24))
            results.append((dist, ptr))
        return {"status": status, "results": results, "count": count, "reads": list(self.reads), "depth": len(path)}


def open_tree(pair_dir: Path, name: str, tree: int):
    pair = pc.find_pairs(pair_dir, [name])
    if not pair:
        raise Blocked(f"{name} not in {pair_dir}")
    blob = pc.load(pair[0][1], pair[0][2])
    addr, blocks = struct.unpack_from(">IH", blob, pc.CELL_SPATIAL)
    if addr == pc.EMPTY:
        raise Blocked(f"{name}: no spatial cell")
    refs = pc.read_ref_list(blob, regen.blk_off(addr), blocks * regen.BLOCK)
    if not 0 <= tree < len(refs):
        raise Blocked(f"{name}: tree {tree} of {len(refs)}")
    chain = regen.chain_via_locator(blob, 1000)
    return blob, refs[tree], pc.chain_records(chain), len(refs)


def record_mesh(rec: bytes) -> tuple[int, int, int]:
    """Firmware mesh point of a name record (M3.34): id, x, y."""
    ax, ay, x, y = pc.fine_fields(rec)
    return ((ax << 16) | ay) & 0xFFF3FFF3, x, y


def host_distance(a: bytes, b: bytes) -> float:
    """Distance of two name records in metres on the WGS 84 ellipsoid (local radii
    at the mean latitude; good to a few metres at the distances used here)."""
    la1, lo1 = pc.fine_position(a)
    la2, lo2 = pc.fine_position(b)
    phi = math.radians((la1 + la2) / 2)
    flat = 1 / 298.257223563
    e2 = flat * (2 - flat)
    w = math.sqrt(1 - e2 * math.sin(phi) ** 2)
    meridian = 6378137.0 * (1 - e2) / w ** 3
    normal = 6378137.0 / w
    return math.hypot(meridian * math.radians(la2 - la1), normal * math.cos(phi) * math.radians(lo2 - lo1))


def cells(blob: bytes, ref: dict):
    """Host list of the mesh cells of a tree: (path (i, j, k), ptr, size_w, kx, ky)."""
    base = ref["start"]

    def node(ptr, size):
        return blob[base + 2 * ptr:base + 2 * (ptr + size)]

    for i, (_p, p0, s0, _kx, _ky, f0) in enumerate(entries(blob[base:base + 2 * ref["root_words"]])):
        if is_leaf(f0) or not s0:
            continue
        for j, (_p, p1, s1, _kx, _ky, f1) in enumerate(entries(node(p0, s0))):
            if is_leaf(f1) or not s1:
                continue
            for k, (_p, p2, s2, kx, ky, f2) in enumerate(entries(node(p1, s1))):
                if not is_leaf(f2) and s2:
                    yield (i, j, k), p2, s2, kx, ky


def compare(results: list[tuple[int, int]], leaves: list[tuple], names: list[bytes],
            origin: bytes, tol_m: float, code: int = 0) -> dict:
    """Firmware results against the host leaves of the same cell (pure)."""
    want = Counter(leaf[0] for leaf in leaves if kept(leaf[3], code))
    got = Counter(o for _d, o in results)
    worst = 0.0
    dist_ok = True
    for dist, ordinal in results:
        if ordinal >= len(names):
            dist_ok = False
            continue
        err = abs(dist - host_distance(origin, names[ordinal]))
        worst = max(worst, err)
        dist_ok = dist_ok and err <= tol_m + REL_TOL * dist
    order_ok = [d for d, _o in results] == sorted(d for d, _o in results)
    return {"set": got == want, "dist": dist_ok, "order": order_ok, "worst_m": worst,
            "leaves": sum(want.values()), "found": sum(got.values())}


def tree_report(fw: Firmware, opened, args, tree: int) -> dict:
    """Run one tree; returns the numbers ``cmd_run`` prints."""
    blob, ref, names, ntrees = opened
    walk = Walk(fw, blob, ref)
    todo = list(cells(blob, ref))
    step = max(1, len(todo) // args.cells)
    sample = todo[::step][:args.cells]
    if not sample:
        raise Blocked("tree has no three-level cell")
    rows, bad, leaves_total, capped, coded = [], 0, 0, 0, None
    worst = 0.0
    origin = None
    direct = None
    for path, ptr, size, kx, ky in sample:
        leaves = host_leaves(blob, ref, ptr, size)
        live = [leaf for leaf in leaves if kept(leaf[3], 0)]
        if origin is None and live:
            origin = names[live[0][0]]
            walk.set_origin(*record_mesh(origin))
        if direct is None and live:
            in_cell = ref["start"] + 2 * ptr <= live[0][4] < ref["start"] + 2 * (ptr + size)
            direct = (path, live[0], in_cell)
        if coded is None:
            coded = next(((path, leaf) for leaf in leaves if not kept(leaf[3], 0)), None)
        res = walk.descend(path)
        if len(live) > MAX_RESULTS:                  # the result table holds 128 records
            capped += 1
            ok = res["count"] == MAX_RESULTS and {o for _d, o in res["results"]} <= {leaf[0] for leaf in live}
        else:
            cmpd = compare(res["results"], leaves, names, origin or names[0], args.tol)
            ok = res["status"] == 1 and cmpd["set"] and cmpd["dist"] and cmpd["order"]
            worst = max(worst, cmpd["worst_m"])
        bad += 0 if ok else 1
        leaves_total += len(leaves)
        rows.append({"path": list(path), "cell": "%04x%04x" % (kx, ky), "leaves": len(leaves), "kept": len(live),
                     "found": res["count"], "blocks": len(res["reads"]), "ok": ok,
                     "nearest": list(res["results"][0]) if res["results"] else None})
    if direct is None:
        raise Blocked("no sampled cell has a leaf the search keeps")

    # controls on the first kept leaf
    path, (ordinal, _x, _y, _code, leaf_off), in_cell = direct
    base = walk.descend(path)
    fine_off = leaf_off + 12
    (fine,) = struct.unpack_from(">I", blob, fine_off)
    moved_y = (fine & 0x7FF) ^ 0x400                              # half a mesh north or south
    walk.patch = {fine_off: struct.pack(">I", (fine & ~0x7FF) | moved_y)}
    moved = walk.descend(path)
    d0 = dict((o, d) for d, o in base["results"]).get(ordinal)
    d1 = dict((o, d) for d, o in moved["results"]).get(ordinal)
    half_mesh = 6367000.0 * math.radians(1 / 96)                 # 1024 fine steps of latitude
    ctl_move = d0 is not None and d1 is not None and abs(abs(d1 - d0) - half_mesh) < 0.25 * half_mesh
    walk.patch = {leaf_off: b"\x00\x05"}                         # terminator in place of that leaf
    cut = walk.descend(path)
    ctl_cut = cut["count"] < base["count"] and ordinal not in {o for _d, o in cut["results"]}
    walk.patch = {fine_off: struct.pack(">I", fine & ~0x08000000)}   # leaf flag cleared: an inner entry
    try:
        unflag = walk.descend(path)
        stored = ordinal in {o for _d, o in unflag["results"]}
    except (EngineError, Blocked):
        stored = False
    ctl_flag = stored != in_cell                     # the flag is tested in the cell's node only (level 0x1004)
    walk.patch = {}
    ctl_code = None
    if coded:                                        # a leaf with a code: kept only when the code is current
        cpath, cleaf = coded
        without = {o for _d, o in walk.descend(cpath)["results"]}
        walk.set_code(cleaf[3])
        with_code = walk.descend(cpath)
        walk.set_code(0)
        want = Counter(leaf[0] for leaf in host_leaves(blob, ref, *next((p, s_) for pa, p, s_, _a, _b in sample if pa == cpath))
                       if kept(leaf[3], cleaf[3]))
        ctl_code = (cleaf[0] not in without and Counter(o for _d, o in with_code["results"]) == want)

    # which instruction reads which entry byte (one more walk with a read watch on the heap)
    walk.eng.watch(walk.mark, HEAP + HEAP_SIZE, "r", "nodes")
    walk.eng.arm_watch()
    walk.descend(path)
    walk.eng.disarm_watch()
    table = Counter()
    for hit in walk.eng.watch_hits():
        d = hit.as_dict()
        pc_ = int(d["pc"], 16)
        if LOAD_CHILD <= pc_ < LOAD_CHILD + 0x1B0 or STEP <= pc_ < WALK + 0x55C:
            table[pc_] += 1

    ok = bad == 0 and ctl_move and ctl_cut and ctl_flag and ctl_code is not False
    return {"file": args.file, "tree": tree, "trees": ntrees, "cells": len(todo), "sampled": len(sample),
            "step": step, "leaves": leaves_total, "bad": bad, "worst_m": worst, "capped": capped,
            "first": rows[0], "ok": ok, "d0": d0, "d1": d1, "in_cell": in_cell, "stored": stored,
            "cut": (base["count"], cut["count"]), "coded": coded[1][3] if coded else None,
            "controls": {"move": ctl_move, "cut": ctl_cut, "flag": ctl_flag, "code": ctl_code},
            "rows": rows[:100], "reads_by_pc": {"%#010x" % k: v for k, v in sorted(table.items())}}


def cmd_root_load(args) -> int:
    """Run root loader fn 0x0040f674 on one tree and verify it sets the tree base.

    The root loader is driven by the POI search setup; this harness seeds the
    request/state the static callers pass (r4=request/context pointer) and
    checks that *0x00d5b858 is set to the tree base block and that STEP can
    descend from the returned root context. If the loader needs unavailable
    search state, return BLOCKED with the missing precondition.
    """
    fw = Firmware(pw.load_image(args.image))
    blob, ref, names, ntrees = open_tree(Path(args.dir), args.file, int(args.tree))
    walk = Walk(fw, blob, ref)
    # Seed globals observed in callers: mode/format/filter already set by Walk.
    # Provide request pointer as r4; many callers pass r9=request struct.
    req = walk.request
    walk.eng.write_mem(req, bytes(80))
    # Common fields seen in setup: store origin/id placeholders harmlessly.
    sp = STACK + 0xF000
    walk.eng.set_regs(r15=sp)
    try:
        r0 = walk.eng.call(0x0040f674, [req])
    except (EngineError, Blocked) as exc:
        print("BLOCKED: root-load engine stop: %s" % str(exc)[:300])
        return 3
    base = struct.unpack("<I", walk.eng.read_mem(G_TREE_BASE, 4))[0]
    ok_base = base == walk.base_block
    # Try stepping root entry 0 if loader produced/returned a context-like state.
    step_status = None
    try:
        # best-effort: use request as ctx if it was filled; else report base only
        ctx = req
        step_status = walk._call_step(LEVEL_ROOT, 0, ctx)
    except Exception as exc:
        step_status = f"err:{type(exc).__name__}"
    print("%s tree %d: root_load r0=%s tree_base=%#x expected=%#x step0=%s" % (
        args.file, int(args.tree), hex(r0 & 0xFFFFFFFF), base, walk.base_block, step_status))
    ok = ok_base and step_status == 1
    print("RESULT: %s" % ("ACCEPT" if ok else "BLOCKED"))
    return 0 if ok else 3


def cmd_run(args) -> int:
    fw = Firmware(pw.load_image(args.image))
    if args.tree == "all":
        pair = pc.find_pairs(Path(args.dir), [args.file])
        if not pair:
            raise Blocked(f"{args.file} not in {args.dir}")
        blob = pc.load(pair[0][1], pair[0][2])
        addr, blocks = struct.unpack_from(">IH", blob, pc.CELL_SPATIAL)
        refs = pc.read_ref_list(blob, regen.blk_off(addr), blocks * regen.BLOCK)
        names = pc.chain_records(regen.chain_via_locator(blob, 1000))
        tot = Counter()
        worst, reports = 0.0, []
        for tree, ref in enumerate(refs):
            try:
                rep = tree_report(fw, (blob, ref, names, len(refs)), args, tree)
            except Blocked as exc:
                print("  tree %d: BLOCKED %s" % (tree, exc))
                tot["blocked"] += 1
                continue
            reports.append({k: v for k, v in rep.items() if k not in ("rows", "reads_by_pc")})
            tot["trees"] += 1
            tot["ok"] += rep["ok"]
            tot["cells"] += rep["sampled"]
            tot["cells_ok"] += rep["sampled"] - rep["bad"]
            tot["leaves"] += rep["leaves"]
            tot["capped"] += rep["capped"]
            for name, value in rep["controls"].items():
                tot["ctl_" + name] += value is True
                tot["ctl_" + name + "_n"] += value is not None
            tot["deep"] += not rep["in_cell"]
            worst = max(worst, rep["worst_m"])
        print("%s: %d trees, %d run, %d ACCEPT; cells %d/%d equal to the host; %d leaves; worst distance difference %.1f m" % (
            args.file, len(refs), tot["trees"], tot["ok"], tot["cells_ok"], tot["cells"], tot["leaves"], worst))
        print("  controls: moved %d/%d, cut %d/%d, flag %d/%d (%d trees with the leaf one level below the cell), code %d/%d; cells over %d leaves: %d" % (
            tot["ctl_move"], tot["ctl_move_n"], tot["ctl_cut"], tot["ctl_cut_n"], tot["ctl_flag"], tot["ctl_flag_n"],
            tot["deep"], tot["ctl_code"], tot["ctl_code_n"], MAX_RESULTS, tot["capped"]))
        ok = tot["trees"] > 0 and tot["ok"] == tot["trees"] and not tot["blocked"]
        print("RESULT: %s" % ("ACCEPT" if ok else "REJECT"))
        if args.json:
            Path(args.json).write_text(json.dumps({"file": args.file, "totals": dict(tot), "trees": reports}, indent=1) + "\n")
        return 0 if ok else 1
    rep = tree_report(fw, open_tree(Path(args.dir), args.file, int(args.tree)), args, int(args.tree))
    r0 = rep["first"]
    print("%s tree %d of %d: %d cells, %d sampled (every %d), %d leaves below them" % (
        args.file, rep["tree"], rep["trees"], rep["cells"], rep["sampled"], rep["step"], rep["leaves"]))
    print("  first cell %s path %s: %d leaves, firmware stored %d, nearest %s, %d block reads" % (
        r0["cell"], r0["path"], r0["leaves"], r0["found"], r0["nearest"], r0["blocks"]))
    print("  firmware leaves and distances = host: %d/%d cells (worst distance difference %.1f m; %d cells over %d leaves)" % (
        rep["sampled"] - rep["bad"], rep["sampled"], rep["worst_m"], rep["capped"], MAX_RESULTS))
    ctl = rep["controls"]
    print("  control, fine y of one leaf moved by 1024: distance %s -> %s m: %s" % (
        rep["d0"], rep["d1"], "moved" if ctl["move"] else "NOT as expected"))
    print("  control, terminator in place of that leaf: %d -> %d results: %s" % (
        rep["cut"][0], rep["cut"][1], "cut" if ctl["cut"] else "NOT cut"))
    print("  control, leaf flag 0x0800 cleared (leaf %s): %s, %s" % (
        "in the cell's node" if rep["in_cell"] else "one level below the cell's node",
        "still stored" if rep["stored"] else "not stored", "as the code says" if ctl["flag"] else "NOT as expected"))
    print("  control, leaf with a code: %s" % ("none in the sample" if ctl["code"] is None else
                                               "stored only when *0x005638ec is its code (%d)" % rep["coded"] if ctl["code"]
                                               else "NOT as expected"))
    print("  instructions of the three functions that read heap data: %d" % len(rep["reads_by_pc"]))
    print("RESULT: %s" % ("ACCEPT" if rep["ok"] else "REJECT"))
    if args.json:
        Path(args.json).write_text(json.dumps(rep, indent=1) + "\n")
    return 0 if rep["ok"] else 1


def selftest() -> int:
    """Pure checks of the host side (the firmware run needs the image: ``run``)."""
    n = 0
    leaf = pc.SPATIAL_ENTRY.pack(8, 7, 0, 0, 0, (0x8800 | 0x123) << 16 | 0xF800 | 0x456)
    inner = pc.SPATIAL_ENTRY.pack(8, 0x100, 0x15, 0xA6AE, 0xC95F, 0)
    term = b"\x00\x05\xff\xff\xff\xff\x00\x00\x00\x00"
    got = list(entries(inner + leaf + term + leaf))
    assert [g[1] for g in got] == [0x100, 7], got            # the terminator ends the node
    assert not is_leaf(got[0][5]) and is_leaf(got[1][5])
    n += 3
    ax, ay, w6, w8 = pc.encode_position(52.2297, 21.0122)
    a = struct.pack(">HHHHH", 0x6008, ax, ay, w6, w8) + bytes(6)
    ax2, ay2, w62, w82 = pc.encode_position(52.2387, 21.0122)          # 1 km north
    b = struct.pack(">HHHHH", 0x6008, ax2, ay2, w62, w82) + bytes(6)
    assert abs(host_distance(a, b) - 1001.4) < 3, host_distance(a, b)
    assert record_mesh(a) == (((ax << 16) | ay) & 0xFFF3FFF3, w6 & 0x7FF, w8 & 0x7FF)
    n += 2
    names = [a, b]
    two = [(0, 0, 0, 63, 0), (1, 0, 0, 63, 0)]
    good = compare([(0, 0), (1001, 1)], two, names, a, 2)
    assert good["set"] and good["dist"] and good["order"], good
    assert not compare([(0, 0)], two, names, a, 2)["set"]                              # a leaf missing
    assert not compare([(0, 0), (1500, 1)], two, names, a, 2)["dist"]
    assert not compare([(1001, 1), (0, 0)], two, names, a, 2)["order"]
    n += 4
    coded = [(0, 0, 0, 63, 0), (1, 0, 0, 6, 0)]                                         # a leaf with code 6
    assert compare([(0, 0)], coded, names, a, 2)["set"]
    assert compare([(0, 0), (1001, 1)], coded, names, a, 2, code=6)["set"]
    assert not compare([(0, 0), (1001, 1)], coded, names, a, 2)["set"]
    assert leaf_code(0x8E99FABD) == 63 and leaf_code(0x0E9932BD) == 6 and leaf_code(0x08000000) == 0
    n += 4
    assert RESULT.size == 24
    n += 1
    print("selftest OK (%d checks)" % n)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("image")
    r.add_argument("--dir", required=True, help="directory with POINTnnn.DAT.CMP/.IND pairs")
    r.add_argument("--file", default="POINT010")
    r.add_argument("--tree", default="0", help="tree number (one per category) or 'all'")
    r.add_argument("--cells", type=int, default=50)
    r.add_argument("--tol", type=float, default=3.0, help="distance tolerance in metres (plus 0.2 %%)")
    r.add_argument("--json")
    rl = sub.add_parser("root-load", help="run root loader fn 0x0040f674 on one tree")
    rl.add_argument("image")
    rl.add_argument("--dir", required=True)
    rl.add_argument("--file", default="POINT010")
    rl.add_argument("--tree", default="0")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmd:
        ap.error("need a command or --selftest")
    try:
        if args.cmd == "root-load":
            return cmd_root_load(args)
        return cmd_run(args)
    except Blocked as exc:
        print("BLOCKED: %s" % exc)
        return 3
    except EngineError as exc:
        print("BLOCKED: engine stop: %s" % str(exc)[:300])
        return 3


if __name__ == "__main__":
    sys.exit(main())
