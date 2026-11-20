#!/usr/bin/env python3
"""Function-pointer tables in a CE module's data, and the code that loads them (M3.24).

A "table" is a run of at least ``--min-run`` consecutive aligned 32-bit words
(stride 4) that all point at code: a ``.pdata`` function start (``START``) or
a pdata gap (``GAP``, leaf code with no record).  A word that lands
``INSIDE`` a function ends the run (an entry point is never mid-function, H51).

Two data areas are scanned:

  * sec0 below the first pdata record (rodata; always readable), and
  * the *stored* bytes of the compressed writable section (sec1 ``INIT``),
    decoded with the kernel routine (``nk_decomp.py``), minus the import
    address table at its start (``--skip-iat``, 0xd38 B in ``Navi.exe``).

For every table the tool lists its *users*: functions whose literal pool holds
a word in ``[base - 8, end)`` (the base, or base-1/2 entries for 1-based
indices, or an entry address) and that load it with ``mov.l @(disp,PC),Rn``.
Literal pools are skipped while scanning, the same rule ``callgraph.py`` uses
(H112).  A data word elsewhere that holds the base is reported as a ``data``
reference (a table of tables / an object that holds the vtable pointer).

Nothing is executed and no vendor byte is stored: the tool reads the image the
caller names.

Usage:
  fptables.py --selftest
  fptables.py scan IMG [--module Navi.exe] [--graph g.json] [--min-run 3]
                   [--sec1 SEC1.bin] [--json OUT] [--edges OUT]
  fptables.py refs IMG VA [VA ...]   # code literals and data words that equal VA
  fptables.py via graph.json tables.json VA [VA ...] [--depth 4]
                                     # table entries that statically reach VA
"""
from __future__ import annotations

import argparse
import bisect
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE / "l3_harness"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

IMAGE_A = 0x200200
IAT_BYTES = 0xD38            # Navi.exe sec1: 846 import slots (C-3440)


# --------------------------------------------------------------------------
# pure functions (selftested)

def classify(starts, pdata, va: int) -> str:
    """START / INSIDE / GAP / OUT for one word (``starts`` = sorted begins)."""
    if va & 1 or not starts or va < starts[0] or va >= pdata[-1][0] + pdata[-1][2]:
        return "OUT"
    i = bisect.bisect_right(starts, va) - 1
    begin, _p, length = pdata[i]
    if va == begin:
        return "START"
    if va < begin + length:
        return "INSIDE"
    return "GAP"


def find_tables(blob: bytes, base: int, starts, pdata, min_run: int = 3, skip: int = 0,
                max_stride: int = 64, max_hole: int = 16, shift: int = 0):
    """Runs of >= ``min_run`` code pointers (START or GAP) at a fixed stride.

    Stride 4 is a plain pointer array; it may hold NULL slots (at most
    ``max_hole`` in a row), as a sparse state x event matrix does: ``count``
    is then the number of slots and ``nulls`` how many are empty.  A larger
    stride is an array of rows
    (``{id, fn}``, ``{name, fn, arg}`` ...) with the pointer in one column.
    Each word joins at most one table; the smallest stride that gives a run
    wins.  An ``INSIDE`` word never counts (an entry is never mid-function).
    Returns [{"base", "count", "stride", "entries": [(va, kind)], "nulls", "starts"}].
    """
    a0 = (skip + 3) & ~3
    kinds = {}
    for off in range(a0, len(blob) - 3, 4):
        w = struct.unpack_from("<I", blob, off)[0]
        if not w:
            continue
        k = classify(starts, pdata, (w + shift) & 0xFFFFFFFF)
        if k in ("START", "GAP"):
            kinds[off] = (w, k)
    used, out = set(), []
    zero = struct.pack("<I", 0)
    for off in sorted(kinds):
        if off in used:
            continue
        # stride 4, NULL slots allowed (a sparse handler matrix: state x event)
        run, slot, holes = [off], off + 4, 0
        while slot + 4 <= len(blob) and holes <= max_hole:
            if slot in kinds and slot not in used:
                run.append(slot)
                holes = 0
            elif blob[slot:slot + 4] == zero:
                holes += 1
            else:
                break
            slot += 4
        if len(run) >= min_run:
            ents = [kinds[o] for o in run]
            used.update(run)
            out.append({"base": base + off, "count": (run[-1] - off) // 4 + 1, "stride": 4,
                        "entries": ents, "nulls": (run[-1] - off) // 4 + 1 - len(run),
                        "starts": sum(1 for _w, k in ents if k == "START")})
            continue
        for stride in range(8, max_stride + 1, 4):
            if off - stride in kinds and off - stride not in used and stride > 4:
                continue                   # not the first row at this stride
            run = [off]
            while run[-1] + stride in kinds and run[-1] + stride not in used:
                run.append(run[-1] + stride)
            if len(run) >= min_run:
                ents = [kinds[o] for o in run]
                used.update(run)
                out.append({"base": base + off, "count": len(run), "stride": stride,
                            "entries": ents, "nulls": 0,
                            "starts": sum(1 for _w, k in ents if k == "START")})
                break
    return out


def pool_loads(code: bytes, base: int, lo: int, hi: int):
    """Yield (insn_va, literal_va, value) for every ``mov.l @(disp,PC),Rn`` in
    ``[lo, hi)``, skipping words already known to be pool literals (H112)."""
    pool: set[int] = set()
    pc = lo
    end = min(hi, base + len(code))
    while pc + 1 < end:
        if pc in pool:
            pc += 2
            continue
        insn = struct.unpack_from("<H", code, pc - base)[0]
        top = insn >> 12
        if top == 0x9:
            pool.add(pc + 4 + (insn & 0xFF) * 2)
        elif top == 0xD:
            addr = (pc & ~3) + 4 + (insn & 0xFF) * 4
            pool.update((addr, addr + 2))
            if base <= addr and addr + 4 <= base + len(code):
                yield pc, addr, struct.unpack_from("<I", code, addr - base)[0]
        pc += 2


def owner_fn(starts, pdata, va: int):
    """pdata function that contains ``va``, else the preceding start (GAP code)."""
    i = bisect.bisect_right(starts, va) - 1
    if i < 0:
        return None
    return starts[i]


def is_text(word: bytes) -> bool:
    """Four bytes that read as a short string (>= 2 printable, rest NUL)."""
    pr = sum(1 for c in word if 0x20 <= c < 0x7F)
    return pr >= 2 and pr + word.count(0) == 4 and word[0] != 0


def attach_users(tables, loads, data_words, starts, pdata, slack: int = 8, word_at=None):
    """Fill ``users`` (code) and ``data_refs`` for each table.

    A reference is a value in the first row before the pointer column
    (printed as ``prefix=``: it may also be a shared constant there, such as
    an empty string, so a table whose only users are prefix users is weak)
    (``[base - stride + 4, base]``; ``[base - 8, base]`` for stride 4, which
    covers 1- and 2-based indices) or the address of one entry.  A value in
    that prefix whose word reads as text (``word_at(value)``, ``is_text``) is
    a string of the preceding data, not a row start, and does not count.
    """
    bases = sorted((t["base"], t) for t in tables)
    keys = [b for b, _ in bases]

    def hit(value):
        i = bisect.bisect_right(keys, value + 64) - 1
        for j in range(i, max(i - 8, -1), -1):       # tables are short; a few back suffice
            b, t = bases[j]
            lo_row = b - (slack if t["stride"] == 4 else t["stride"] - 4)
            if lo_row <= value < b and word_at is not None and is_text(word_at(value)):
                continue
            if lo_row <= value <= b or (b <= value < b + t["stride"] * t["count"]
                                        and (value - b) % t["stride"] == 0):
                return t
        return None

    for t in tables:
        t["users"], t["data_refs"] = {}, []
    for insn, _lit, value in loads:
        t = hit(value)
        if t is not None:
            fn = owner_fn(starts, pdata, insn)
            t["users"].setdefault(fn, []).append((insn, value))
    for addr, value in data_words:
        t = hit(value)
        if t is not None and not (t["base"] - t["stride"] <= addr < t["base"] + t["stride"] * t["count"]):
            t["data_refs"].append((addr, value))
    return tables


# --------------------------------------------------------------------------
# image access

def load_module(image: str, module: str, image_start: int, sec1_cache: str | None):
    import cerom
    import nk_decomp
    data = Path(image).read_bytes()
    rom = cerom.CERom(data, image_start)
    secs = list(rom.o32(rom.module(module)))
    text = next(s for s in secs if s["flags"] & 0x20000000)
    off = rom.va2file(text["dataptr"])
    code = data[off:off + min(text["psize"], text["vsize"])]
    comp = [s for s in secs if s["flags"] & cerom.IMAGE_SCN_COMPRESSED]
    ro = [s for s in comp if not s["flags"] & 0x80000000]
    rw = [s for s in comp if s["flags"] & 0x80000000]
    r0, blob = nk_decomp.decompress(data, rom.va2file(ro[0]["dataptr"]), ro[0]["psize"], ro[0]["vsize"])
    pdata = nk_decomp.parse_pdata(blob[:r0])
    sec1, sec1_va = b"", None
    if rw:
        s = rw[0]
        sec1_va = s["realaddr"]
        if sec1_cache and Path(sec1_cache).exists():
            full = Path(sec1_cache).read_bytes()
            r1 = s["vsize"]
        else:
            r1, full = nk_decomp.decompress(data, rom.va2file(s["dataptr"]), s["psize"], s["vsize"])
        # stored bytes only: everything after the last non-zero byte is BSS
        stored = full[:r1].rstrip(b"\0")
        sec1 = stored + b"\0" * ((-len(stored)) % 4)
    return code, text["realaddr"], sec1, sec1_va, pdata


def scan(args):
    code, base0, sec1, sec1_va, pdata = load_module(args.image, args.module, args.image_start, args.sec1)
    starts = [p[0] for p in pdata]
    lo, hi = starts[0], pdata[-1][0] + pdata[-1][2]
    rodata = code[:lo - base0]
    tables = []
    for t in find_tables(rodata, base0, starts, pdata, args.min_run, shift=args.shift):
        t["area"] = "sec0"
        tables.append(t)
    if sec1:
        for t in find_tables(sec1, sec1_va, starts, pdata, args.min_run, skip=args.skip_iat,
                             shift=args.shift):
            t["area"] = "sec1"
            tables.append(t)
    loads = list(pool_loads(code, base0, lo, hi))
    data_words = [(base0 + o, struct.unpack_from("<I", rodata, o)[0]) for o in range(0, len(rodata) - 3, 4)]
    data_words += [(sec1_va + o, struct.unpack_from("<I", sec1, o)[0])
                   for o in range(args.skip_iat, len(sec1) - 3, 4)]
    def word_at(va):
        if base0 <= va < base0 + len(rodata) - 3:
            return rodata[va - base0:va - base0 + 4]
        if sec1_va is not None and sec1_va <= va < sec1_va + len(sec1) - 3:
            return sec1[va - sec1_va:va - sec1_va + 4]
        return None
    attach_users(tables, loads, data_words, starts, pdata, word_at=word_at)
    return tables, starts, pdata, (lo, hi), len(rodata), len(sec1), sec1_va, loads


def cmd_scan(args) -> int:
    tables, starts, pdata, (lo, hi), n0, n1, sec1_va, loads = scan(args)
    g = None
    if args.graph:
        g = json.loads(Path(args.graph).read_text())["functions"]
        called = set()
        for v in g.values():
            called.update(int(c, 0) for c in v["calls"])
        roots = {int(k, 0) for k in g if int(k, 0) not in called and not g[k].get("leaf")}
    entries = sum(t["count"] for t in tables)
    targets = {w for t in tables for w, _k in t["entries"]}
    print("%s: code %#010x..%#010x; scanned sec0 rodata %#x B, sec1 stored %#x B (from %#x)"
          % (args.module, lo, hi, n0, max(n1 - args.skip_iat, 0), args.skip_iat))
    print("tables %d (sec0 %d, sec1 %d), entries %d, distinct targets %d, tables with a code user %d, "
          "with only data refs %d, unreferenced %d"
          % (len(tables), sum(t["area"] == "sec0" for t in tables), sum(t["area"] == "sec1" for t in tables),
             entries, len(targets), sum(1 for t in tables if t["users"]),
             sum(1 for t in tables if not t["users"] and t["data_refs"]),
             sum(1 for t in tables if not t["users"] and not t["data_refs"])))
    if g is not None:
        expl = targets & roots
        print("no-static-caller functions %d; in a table %d" % (len(roots), len(expl)))
        unres_users = {u for t in tables for u in t["users"] if u is not None
                       and g.get("%#010x" % u, {}).get("unresolved", 0)}
        print("table users with unresolved jsr @Rn %d (of %d distinct users), holding %d of %d unresolved sites"
              % (len(unres_users), len({u for t in tables for u in t["users"]}),
                 sum(g["%#010x" % u]["unresolved"] for u in unres_users),
                 sum(v["unresolved"] for v in g.values())))
        lits = {v for _i, _l, v in loads}
        cb = (roots - expl) & lits
        print("no-static-caller functions outside tables loaded as a code literal (callback) %d, "
              "neither %d" % (len(cb), len(roots - expl - lits)))
    for t in sorted(tables, key=lambda t: t["base"]):
        def fmt(us):
            return ",".join("%#010x%s" % (u or 0, ("(u%d)" % g["%#010x" % u]["unresolved"])
                                          if g is not None and u is not None and "%#010x" % u in g
                                          and g["%#010x" % u]["unresolved"] else "")
                            for u in sorted(us, key=lambda x: x or 0))
        exact = [u for u, v in t["users"].items() if any(val >= t["base"] for _i, val in v)]
        prefix = [u for u in t["users"] if u not in exact]
        drefs = ",".join("%#010x" % a for a, _v in t["data_refs"][:4])
        print("%s %#010x s=%-2d n=%-3d null=%-3d START=%-3d first=%#010x users=[%s] prefix=[%s] data=[%s]"
              % (t["area"], t["base"], t["stride"], t["count"], t["nulls"], t["starts"], t["entries"][0][0],
                 fmt(exact), fmt(prefix) if len(prefix) <= 6 else "%d functions" % len(prefix), drefs))
        if args.verbose:
            print("    " + " ".join("%#x%s" % (w, "" if k == "START" else "g") for w, k in t["entries"]))
    if args.json:
        Path(args.json).write_text(json.dumps({
            "schema": "osm2leaf.fptables/v1", "module": args.module,
            "tables": [{"area": t["area"], "base": "%#010x" % t["base"], "stride": t["stride"], "count": t["count"], "nulls": t["nulls"],
                        "entries": [["%#010x" % w, k] for w, k in t["entries"]],
                        "users": {"%#010x" % (u or 0): [["%#010x" % i, "%#010x" % val] for i, val in v]
                                  for u, v in t["users"].items()},
                        "data_refs": ["%#010x" % a for a, _v in t["data_refs"]]}
                       for t in sorted(tables, key=lambda t: t["base"])]}, indent=1))
    if args.edges:
        edges = sorted({("%#010x" % u, "%#010x" % w) for t in tables for u in t["users"] if u
                        for w, _k in t["entries"]})
        Path(args.edges).write_text(json.dumps({"schema": "osm2leaf.table_edges/v1",
                                                "edges": edges}, indent=0))
    return 0


def cmd_refs(args) -> int:
    code, base0, sec1, sec1_va, pdata = load_module(args.image, args.module, args.image_start, args.sec1)
    starts = [p[0] for p in pdata]
    lo, hi = starts[0], pdata[-1][0] + pdata[-1][2]
    want = {int(v, 0) for v in args.va}
    for insn, lit, value in pool_loads(code, base0, lo, hi):
        if value in want:
            print("%#010x code  mov.l at %#010x (pool %#010x) in fn %#010x"
                  % (value, insn, lit, owner_fn(starts, pdata, insn)))
    for area, blob, b, sk in (("sec0", code, base0, 0), ("sec1", sec1, sec1_va, args.skip_iat)):
        for o in range(sk, len(blob) - 3, 4):
            if b + o >= lo and area == "sec0":
                break
            v = struct.unpack_from("<I", blob, o)[0]
            if v in want:
                print("%#010x data  word at %#010x (%s)" % (v, b + o, area))
    for v in sorted(want):
        print("%#010x is %s" % (v, classify(starts, pdata, v)))
    return 0


def via(calls: dict, entries: dict, target: int, depth: int):
    """Table entries from which ``target`` is statically reachable.

    ``calls``: {fn: [callee, ...]} (callgraph.py edges); ``entries``:
    {entry_va: [table_base, ...]}.  Returns [(dist, entry, table_bases, chain)]
    by breadth-first search backwards from ``target`` (dist 0 = itself).
    """
    rev: dict[int, list] = {}
    for f, cs in calls.items():
        for c in cs:
            rev.setdefault(c, []).append(f)
    prev, frontier, out = {target: None}, [target], []
    for d in range(depth + 1):
        nxt = []
        for node in frontier:
            if node in entries:
                chain, n = [], node
                while n is not None:
                    chain.append(n)
                    n = prev[n]
                out.append((d, node, entries[node], chain))
            for p in sorted(rev.get(node, [])):
                if p not in prev:
                    prev[p] = node
                    nxt.append(p)
        frontier = nxt
    return out


def cmd_via(args) -> int:
    g = json.loads(Path(args.graph).read_text())["functions"]
    calls = {int(k, 0): [int(c, 0) for c in v["calls"]] for k, v in g.items()}
    tabs = json.loads(Path(args.tables).read_text())["tables"]
    entries: dict[int, list] = {}
    for t in tabs:
        for w, _k in t["entries"]:
            entries.setdefault(int(w, 0), [])
            if t["base"] not in entries[int(w, 0)]:
                entries[int(w, 0)].append(t["base"])
    for text in args.va:
        va = int(text, 0)
        hits = via(calls, entries, va, args.depth)
        print("%#010x: %d table entr%s within %d static calls"
              % (va, len(hits), "y" if len(hits) == 1 else "ies", args.depth))
        for d, e, bases, chain in hits:
            print("  d=%d entry %#010x in %s  chain %s"
                  % (d, e, ",".join(bases), " -> ".join("%#010x" % c for c in chain)))
    return 0


# --------------------------------------------------------------------------
def selftest() -> int:
    fails = []

    def check(name, cond):
        print("%s %s" % ("ok  " if cond else "FAIL", name))
        if not cond:
            fails.append(name)

    pdata = [(0x1000, 4, 0x20), (0x1040, 4, 0x20), (0x1080, 4, 0x20)]
    starts = [p[0] for p in pdata]
    check("classify START/INSIDE/GAP/OUT",
          [classify(starts, pdata, v) for v in (0x1040, 0x1044, 0x1060, 0x2000, 0x1041)]
          == ["START", "INSIDE", "GAP", "OUT", "OUT"])
    # data: [string ptr][f0][f1][gap][f2][INSIDE][f0][f1][0]
    words = [0x500, 0x1000, 0x1040, 0x1060, 0x1080, 0x1044, 0x1000, 0x1040, 0]
    blob = struct.pack("<%dI" % len(words), *words)
    tabs = find_tables(blob, 0x800, starts, pdata, 3)
    check("one run of four (START,START,GAP,START); INSIDE breaks it; a pair is no table",
          len(tabs) == 1 and tabs[0]["base"] == 0x804 and tabs[0]["count"] == 4 and tabs[0]["starts"] == 3)
    rows = struct.pack("<8I", 1, 0x1000, 2, 0x1040, 3, 0x1080, 4, 0x1044)
    st = find_tables(rows, 0x600, starts, pdata, 3)
    check("rows {id, fn}: one stride-8 table of three; the INSIDE row ends it",
          [(t["base"], t["stride"], t["count"]) for t in st] == [(0x604, 8, 3)])
    sparse = struct.pack("<9I", 0x1000, 0, 0, 0x1040, 0, 0x1080, 0, 0, 7)
    sp = find_tables(sparse, 0x700, starts, pdata, 3)
    check("sparse matrix: NULL slots inside a stride-4 run, trailing NULLs trimmed",
          [(t["base"], t["count"], t["nulls"]) for t in sp] == [(0x700, 6, 3)])
    check("a hole longer than max_hole splits the run",
          find_tables(sparse, 0x700, starts, pdata, 3, max_hole=1) == [])
    check("shift control: +2 turns every START into INSIDE, no table",
          find_tables(blob, 0x800, starts, pdata, 3, shift=2) == [])
    check("skip excludes leading bytes (the IAT)", find_tables(blob, 0x800, starts, pdata, 3, skip=12) == [])
    # code: mov.l @(1,PC),r1 at 0x1000 -> pool 0x1008 = 0x804 (table base);
    # the pool word's low half 0xB0xx would decode as bsr / a mov.l if not skipped
    code = bytearray(0x40)
    struct.pack_into("<HHHH", code, 0, 0xD101, 0x000B, 0x0009, 0x0009)
    struct.pack_into("<I", code, 8, 0x0000D1FF)        # pool: low half looks like mov.l
    struct.pack_into("<HH", code, 0x0C, 0xD201, 0x0009)  # mov.l @(1,PC),r2 at 0x100c -> 0x1014
    struct.pack_into("<I", code, 0x14, 0x00000808)       # table entry address (base+4)
    loads = list(pool_loads(bytes(code), 0x1000, 0x1000, 0x1040))
    check("pool words are not decoded as instructions (H112)",
          [(i, v) for i, _l, v in loads] == [(0x1000, 0xD1FF), (0x100C, 0x808)])
    attach_users(tabs, loads + [(0x1044, 0, 0x7FC)], [(0x900, 0x804), (0x808, 0x804)], starts, pdata)
    t = tabs[0]
    check("base-8..end literal ties the table to its user; unrelated literal does not",
          sorted(t["users"]) == [0x1000, 0x1040] and [i for i, _v in t["users"][0x1000]] == [0x100C])
    rt = find_tables(rows, 0x600, starts, pdata, 3)
    attach_users(rt, [(0x1004, 0, 0x600), (0x1008, 0, 0x5FC)], [], starts, pdata,
                 word_at=lambda va: b"RT0\0" if va == 0x5FC else b"\1\0\0\0")
    check("stride-8 row start (base-4) is a use; a string word before it is not",
          list(rt[0]["users"]) == [0x1000] and is_text(b"GS \0") and not is_text(b"\0\0\0\0"))
    check("data word outside the table that holds its base is a data ref; inside is not",
          t["data_refs"] == [(0x900, 0x804)])
    hits = via({1: [2], 2: [3], 4: [3], 5: [4]}, {1: ["T"], 5: ["U"]}, 3, 2)
    check("via: entries reach the target backwards, depth-limited, with the chain",
          [(d, e, c) for d, e, _b, c in hits] == [(2, 1, [1, 2, 3]), (2, 5, [5, 4, 3])]
          and via({1: [2]}, {1: ["T"]}, 2, 0) == [])
    print("selftest: %s (%d failed)" % ("OK" if not fails else "FAIL", len(fails)))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("via")
    p.add_argument("graph")
    p.add_argument("tables", help="scan --json output")
    p.add_argument("va", nargs="+")
    p.add_argument("--depth", type=int, default=4)
    for name in ("scan", "refs"):
        p = sub.add_parser(name)
        p.add_argument("image")
        p.add_argument("--module", default="Navi.exe")
        p.add_argument("--image-start", type=lambda x: int(x, 0), default=IMAGE_A)
        p.add_argument("--sec1", help="cached nk_decomp.py section output (full vsize file)")
        p.add_argument("--skip-iat", type=lambda x: int(x, 0), default=IAT_BYTES)
        if name == "scan":
            p.add_argument("--graph", help="callgraph.py build output, for root/unresolved counts")
            p.add_argument("--min-run", type=int, default=3)
            p.add_argument("--shift", type=lambda x: int(x, 0), default=0,
                           help="negative control: add N to every word before classifying")
            p.add_argument("--json")
            p.add_argument("--edges", help="write user->target table edges (for callgraph M3.23)")
            p.add_argument("-v", "--verbose", action="store_true")
        else:
            p.add_argument("va", nargs="+")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmd:
        ap.print_help()
        return 2
    return {"scan": cmd_scan, "refs": cmd_refs, "via": cmd_via}[args.cmd](args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
