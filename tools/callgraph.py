#!/usr/bin/env python3
"""Static call graph of a CE module from its function table (M3.23 core, H101).

Nodes are the ``.pdata`` function records (decoded with ``nk_decomp``) plus
the leaf targets of direct calls.  Edges come from three instruction shapes:

  * ``bsr``                                   -> direct call
  * ``mov.l @(disp,PC),Rn`` ... ``jsr/jmp @Rn``  -> call through a pool literal
  * ``mov.l @(disp,PC),Rm; mov.l @Rm,Rn; jsr @Rn`` where the literal is an
    import slot                              -> import call (named)

A ``jsr @Rn`` whose register was not loaded from a literal in the same
function is counted as *unresolved* (an indirect call: a table, a vtable or an
argument).  Nothing is guessed for those.

Usage:
  callgraph.py --selftest
  callgraph.py build   IMG [--module Navi.exe] -o graph.json
  callgraph.py callers graph.json VA [--depth N]
  callgraph.py callees graph.json VA [--depth N]
  callgraph.py reach   graph.json VA            # imports reachable below VA
  callgraph.py users   graph.json IMPORT[,IMPORT...]  # functions that call them
  callgraph.py path    graph.json FROM TO
  callgraph.py stats   graph.json
"""
from __future__ import annotations

import argparse
import bisect
import json
import struct
import subprocess
import sys
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE / "l3_harness"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

IMAGE_A = 0x200200
IMAGE_B = 0x3E00200


def sx(v: int, bits: int) -> int:
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def scan_function(code: bytes, base: int, start: int, length: int, iat: dict,
                  leaf: bool = False):
    """Edges of one function.  ``code`` is the section, ``base`` its VA.

    Returns (direct targets, import names, unresolved indirect call count).
    """
    lit: dict[int, int] = {}          # register -> literal value
    imp: dict[int, str] = {}          # register -> import name (after @Rm load)
    calls, imports, unresolved, prev_end = [], [], 0, False
    end = min(start + length, base + len(code))
    pc = start
    pool: set[int] = set()            # literal-pool words: data, never decoded
    while pc + 1 < end:
        if pc in pool:                                   # H112: a pool word is not a bsr
            pc += 2
            continue
        insn = struct.unpack_from("<H", code, pc - base)[0]
        top, n, m, low = insn >> 12, (insn >> 8) & 15, (insn >> 4) & 15, insn & 15
        if top == 0x9:                                   # mov.w @(disp,PC),Rn
            pool.add(pc + 4 + (insn & 0xFF) * 2)
        if top == 0xD:                                   # mov.l @(disp,PC),Rn
            addr = (pc & ~3) + 4 + (insn & 0xFF) * 4
            pool.update((addr, addr + 2))
            if base <= addr and addr + 4 <= base + len(code):
                lit[n] = struct.unpack_from("<I", code, addr - base)[0]
                imp.pop(n, None)
        elif top == 0xB:                                 # bsr
            calls.append((pc + 4 + sx(insn & 0xFFF, 12) * 2) & 0xFFFFFFFF)
        elif top == 0x6 and low == 0x2:                  # mov.l @Rm,Rn
            if m in lit and lit[m] in iat:
                imp[n] = iat[lit[m]]
            else:
                imp.pop(n, None)
            lit.pop(n, None)
        elif top == 0x6 and low == 0x3:                  # mov Rm,Rn
            for table in (lit, imp):
                if m in table:
                    table[n] = table[m]
                else:
                    table.pop(n, None)
        elif top == 0x4 and (insn & 0xFF) in (0x0B, 0x2B):   # jsr/jmp @Rn
            if n in imp:
                imports.append(imp[n])
            elif n in lit:
                if lit[n] in iat:
                    imports.append(iat[lit[n]])
                else:
                    calls.append(lit[n])
            elif (insn & 0xFF) == 0x0B:
                unresolved += 1
            if (insn & 0xFF) == 0x0B:                    # r0-r7 do not survive a call
                for reg in range(8):
                    lit.pop(reg, None)
                    imp.pop(reg, None)
        elif top in (0xE, 0x7, 0x3, 0x2) or (top == 0x6 and low not in (2, 3)) \
                or top == 0x5 or (top == 0x9):
            # Rn is overwritten/modified by something we do not track
            if top != 0x2:                               # 0x2: stores, Rn is a pointer
                lit.pop(n, None)
                imp.pop(n, None)
        if leaf and prev_end:                            # delay slot of rts/jmp done
            break
        prev_end = leaf and (insn == 0x000B or (top == 0x4 and (insn & 0xFF) == 0x2B))
        pc += 2
    return calls, imports, unresolved


def build_graph(code: bytes, base: int, pdata, iat: dict) -> dict:
    starts = [p[0] for p in pdata]
    lo, hi = starts[0], pdata[-1][0] + pdata[-1][2]
    fns = {}
    for begin, _prolog, length in pdata:
        calls, imports, unresolved = scan_function(code, base, begin, length, iat)
        fns[begin] = {"len": length, "calls": sorted({c for c in calls if lo <= c < hi}),
                      "imports": sorted(set(imports)), "unresolved": unresolved}
    # a call target that is not a START: map INSIDE to its function, keep a GAP as a leaf
    leaves = {}
    for begin, info in fns.items():
        fixed = []
        for c in info["calls"]:
            i = bisect.bisect_right(starts, c) - 1
            if starts[i] == c:
                fixed.append(c)
            elif c < starts[i] + pdata[i][2]:
                fixed.append(starts[i])                  # tail entry inside a function
            else:
                nxt = starts[i + 1] if i + 1 < len(starts) else hi
                leaves.setdefault(c, nxt - c)
                fixed.append(c)
        info["calls"] = sorted(set(fixed))
    for va, room in leaves.items():
        calls, imports, unresolved = scan_function(code, base, va, min(room, 0x400), iat, leaf=True)
        fns[va] = {"len": 0, "leaf": True, "calls": sorted({c for c in calls if c in fns}),
                   "imports": sorted(set(imports)), "unresolved": unresolved}
    # an import thunk (literal slot, load, jmp) is not a function: fold it into its callers
    thunks = {va: v["imports"][0] for va, v in fns.items()
              if v.get("leaf") and len(v["imports"]) == 1 and not v["calls"] and not v["unresolved"]}
    for va, info in fns.items():
        if va in thunks:
            continue
        info["imports"] = sorted(set(info["imports"]) | {thunks[c] for c in info["calls"] if c in thunks})
        info["calls"] = [c for c in info["calls"] if c not in thunks]
    for va in thunks:
        del fns[va]
    return {"schema": "osm2leaf.callgraph/v1",
            "functions": {"%#010x" % k: v | {"calls": ["%#010x" % c for c in v["calls"]]}
                          for k, v in sorted(fns.items())}}


def load(path):
    g = json.loads(Path(path).read_text())["functions"]
    fwd = {int(k, 0): [int(c, 0) for c in v["calls"]] for k, v in g.items()}
    rev: dict[int, list] = {k: [] for k in fwd}
    for k, cs in fwd.items():
        for c in cs:
            rev.setdefault(c, []).append(k)
    return g, fwd, rev


def owner(g, va):
    keys = sorted(int(k, 0) for k in g)
    i = bisect.bisect_right(keys, va) - 1
    k = keys[i]
    return k if va < k + max(g["%#010x" % k]["len"], 2) else va


def walk(edges, root, depth):
    seen, out, q = {root}, [], deque([(root, 0)])
    while q:
        node, d = q.popleft()
        if d:
            out.append((d, node))
        if d < depth:
            for nxt in sorted(edges.get(node, [])):
                if nxt not in seen:
                    seen.add(nxt)
                    q.append((nxt, d + 1))
    return out


def parse_exports(text: str) -> dict[str, str]:
    """``cerom.py exports`` lines (``  55 OSM_SramSet  rva=...``) -> {"#55": name}."""
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0].isdigit() and parts[-1].startswith("rva="):
            out["#" + parts[0]] = parts[1]
    return out


def cmd_build(args) -> int:
    import cerom
    import nk_decomp
    data = Path(args.image).read_bytes()
    rom = cerom.CERom(data, args.image_start)
    secs = list(rom.o32(rom.module(args.module)))
    text = next(s for s in secs if s["flags"] & 0x20000000)
    off = rom.va2file(text["dataptr"])
    code = data[off:off + text["psize"]]
    ro = [s for s in secs if s["flags"] & cerom.IMAGE_SCN_COMPRESSED and not s["flags"] & 0x80000000]
    if len(ro) != 1:
        raise SystemExit("cannot pick the pdata section of %s (use pdata.py)" % args.module)
    r0, blob = nk_decomp.decompress(data, rom.va2file(ro[0]["dataptr"]), ro[0]["psize"], ro[0]["vsize"])
    pdata = nk_decomp.parse_pdata(blob[:r0])
    iat = {}
    text_out = subprocess.run([sys.executable, str(HERE / "cerom.py"), "--image-start",
                               hex(args.image_start), args.image, "imports", args.module,
                               "--resolve-with", hex(IMAGE_B)], capture_output=True, text=True).stdout
    ordinals: dict[str, dict[str, str]] = {}         # dll -> {"#55": "OSM_SramSet"} (H112)

    def by_ordinal(dll: str) -> dict[str, str]:
        if dll not in ordinals:
            out = subprocess.run([sys.executable, str(HERE / "cerom.py"), "--image-start",
                                  hex(args.image_start), args.image, "exports", dll],
                                 capture_output=True, text=True).stdout
            ordinals[dll] = parse_exports(out)
        return ordinals[dll]

    for line in text_out.splitlines():
        if "slot=" in line:
            parts = line.split()
            name = parts[2] if len(parts) > 2 else "?"
            if "!" not in name:                      # by ordinal: OSMDLL.dll ... #55
                name = by_ordinal(parts[0]).get(name, name)
                name = parts[0].rsplit(".", 1)[0] + "!" + name
            iat[int(parts[1].split("=")[1], 16)] = name
    graph = build_graph(code, text["realaddr"], pdata, iat)
    graph["module"], graph["image_start"] = args.module, args.image_start
    Path(args.output).write_text(json.dumps(graph))
    return cmd_stats(argparse.Namespace(graph=args.output))


def cmd_stats(args) -> int:
    g, fwd, rev = load(args.graph)
    edges = sum(len(v) for v in fwd.values())
    unresolved = sum(v["unresolved"] for v in g.values())
    imports = sum(len(v["imports"]) for v in g.values())
    roots = sum(1 for k in fwd if not rev.get(k))
    print("functions %d (leaf targets %d), direct edges %d, import edges %d, "
          "unresolved indirect calls %d, functions with no static caller %d"
          % (len(g), sum(1 for v in g.values() if v.get("leaf")), edges, imports, unresolved, roots))
    return 0


def cmd_walk(args) -> int:
    g, fwd, rev = load(args.graph)
    root = owner(g, int(args.va, 0))
    for d, node in walk(rev if args.cmd == "callers" else fwd, root, args.depth):
        info = g["%#010x" % node]
        print("%s%#010x  len=%#x unresolved=%d imports=%s"
              % ("  " * d, node, info["len"], info["unresolved"], ",".join(info["imports"][:6])))
    return 0


def cmd_reach(args) -> int:
    g, fwd, _ = load(args.graph)
    root = owner(g, int(args.va, 0))
    nodes = [root] + [n for _, n in walk(fwd, root, 10 ** 6)]
    names: dict[str, int] = {}
    for n in nodes:
        for name in g["%#010x" % n]["imports"]:
            names[name] = names.get(name, 0) + 1
    print("%#010x reaches %d functions, %d unresolved indirect calls, %d distinct imports"
          % (root, len(nodes), sum(g["%#010x" % n]["unresolved"] for n in nodes), len(names)))
    for name, count in sorted(names.items(), key=lambda kv: (-kv[1], kv[0])):
        print("  %-40s %d" % (name, count))
    return 0


def cmd_users(args) -> int:
    g, _, rev = load(args.graph)
    want = set(args.imports.split(","))
    for k, v in g.items():
        hit = [i for i in v["imports"] if i.split("!")[-1] in want or i in want]
        if hit:
            print("%s len=%#x callers=%d  %s" % (k, v["len"], len(rev.get(int(k, 0), [])), ",".join(hit)))
    return 0


def cmd_path(args) -> int:
    g, fwd, _ = load(args.graph)
    src, dst = owner(g, int(args.src, 0)), owner(g, int(args.dst, 0))
    prev, q = {src: None}, deque([src])
    while q:
        node = q.popleft()
        if node == dst:
            break
        for nxt in fwd.get(node, []):
            if nxt not in prev:
                prev[nxt] = node
                q.append(nxt)
    if dst not in prev:
        print("no static path")
        return 1
    chain = []
    while dst is not None:
        chain.append("%#010x" % dst)
        dst = prev[dst]
    print(" -> ".join(reversed(chain)))
    return 0


def selftest() -> int:
    fails = []

    def check(name, cond):
        print("%s %s" % ("ok  " if cond else "FAIL", name))
        if not cond:
            fails.append(name)

    base = 0x1000
    code = bytearray(0x100)

    def put(va, *words):
        for i, w in enumerate(words):
            struct.pack_into("<H", code, va - base + 2 * i, w)

    # f0 @0x1000: bsr f1; literal call f2; import call; indirect call via r5
    put(0x1000, 0xB01E,          # bsr 0x1040
        0x0009,
        0xD304,                  # mov.l @(0x1018),r3   -> 0x1060
        0x430B,                  # jsr @r3
        0xD204,                  # mov.l @(0x101c),r2   -> IAT slot
        0x6322,                  # mov.l @r2,r3
        0x430B,                  # jsr @r3
        0x450B,                  # jsr @r5  (unresolved)
        0x000B, 0x0009)
    struct.pack_into("<I", code, 0x18, 0x1060)
    struct.pack_into("<I", code, 0x1C, 0x9000)
    put(0x1040, 0x000B, 0x0009)
    put(0x1060, 0xB00E, 0x0009, 0x000B, 0x0009)          # f2: bsr 0x1080 (a leaf, no pdata)
    put(0x1080, 0x000B, 0x0009)
    # thunk @0x10a0: mov.l @(pool),r1; mov.l @r1,r0; jmp @r0; nop; pool -> slot 0x9004
    put(0x10A0, 0xD101, 0x6012, 0x402B, 0x0009)
    struct.pack_into("<I", code, 0xA8, 0x9004)
    put(0x1064, 0xB01C)                                  # f2 also: bsr 0x10a0
    # f3 @0x10c0: loads a pool word whose low half decodes as "bsr 0x1040" -- not a call
    put(0x10C0, 0xD101, 0x000B, 0x0009, 0x0009)          # mov.l @(0x10c8),r1; rts; nop; pad
    struct.pack_into("<I", code, 0xC8, 0x0000BFBA)       # 0xBFBA at 0x10c8 = bsr 0x1040
    pdata = [(0x1000, 4, 0x14), (0x1040, 0, 4), (0x1060, 0, 8), (0x10C0, 0, 0xC)]
    graph = build_graph(bytes(code), base, pdata + [(0x10F0, 0, 4)], {0x9000: "COREDLL!fread", 0x9004: "COREDLL!ReadFile"})
    f = graph["functions"]
    check("bsr and literal jsr are edges", f["0x00001000"]["calls"] == ["0x00001040", "0x00001060"])
    check("import call is named", f["0x00001000"]["imports"] == ["COREDLL!fread"])
    check("register call with no literal is unresolved, not guessed", f["0x00001000"]["unresolved"] == 1)
    check("call into a pdata gap becomes a leaf node", f.get("0x00001080", {}).get("leaf") is True)
    check("leaf is an edge of its caller", f["0x00001060"]["calls"] == ["0x00001080"])
    check("a call to an import thunk is an import of the caller, and the thunk is no node",
          f["0x00001060"]["imports"] == ["COREDLL!ReadFile"] and "0x000010a0" not in f)
    check("export lines give ordinal names; other lines are ignored (H112)",
          parse_exports("   55 OSM_SramSet      rva=00003930\nexports of X\n 7 A rva=1\n")
          == {"#55": "OSM_SramSet", "#7": "A"})
    check("a literal-pool word that looks like bsr is not an edge (H112)",
          f["0x000010c0"]["calls"] == [])
    print("selftest: %s (%d failed)" % ("OK" if not fails else "FAIL", len(fails)))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("build")
    p.add_argument("image")
    p.add_argument("--module", default="Navi.exe")
    p.add_argument("--image-start", type=lambda x: int(x, 0), default=IMAGE_A)
    p.add_argument("-o", "--output", required=True)
    for name in ("callers", "callees"):
        p = sub.add_parser(name)
        p.add_argument("graph")
        p.add_argument("va")
        p.add_argument("--depth", type=int, default=3)
    p = sub.add_parser("reach")
    p.add_argument("graph")
    p.add_argument("va")
    p = sub.add_parser("users")
    p.add_argument("graph")
    p.add_argument("imports")
    p = sub.add_parser("path")
    p.add_argument("graph")
    p.add_argument("src")
    p.add_argument("dst")
    p = sub.add_parser("stats")
    p.add_argument("graph")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmd:
        ap.print_help()
        return 2
    return {"build": cmd_build, "stats": cmd_stats, "callers": cmd_walk, "callees": cmd_walk,
            "reach": cmd_reach, "users": cmd_users, "path": cmd_path}[args.cmd](args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
