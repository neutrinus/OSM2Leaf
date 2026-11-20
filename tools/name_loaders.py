#!/usr/bin/env python3
"""Which firmware function names which map file (M3.28).

The firmware addresses a card file by an id, and gets the id from a name:
``resolve(directory, file name)`` walks the volume table built from
``DRSTR001.DAT`` and returns ``(directory id << 16) | file id``.  So the
functions that *name* a file are the functions that open it.  This tool reads
that off the image:

  census   every map-file name string in the module's first section, every
           aligned word that points at one, and for each word either the
           function whose literal pool holds it (a *loader*) or the rodata
           table it sits in; then the functions that load a table.
  openers  the callers of the name resolver, each with the names it can pass
           (direct literals and tables), i.e. one row per file family.

Static only: the image and a call graph from ``callgraph.py build``.  The
dynamic half (run the resolver and the name builders on a card) is
``vcard_l3.py lookup``.

Usage:
  name_loaders.py --selftest
  name_loaders.py census  IMG256 --graph g.json [--json OUT]
  name_loaders.py openers IMG256 --graph g.json [--resolver VA] [--json OUT]

Exit codes: 0 ok, 2 usage or missing input.
"""
from __future__ import annotations

import argparse
import bisect
import json
import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

IMAGE_A = 0x200200
NAME_RE = re.compile(rb"[A-Z][A-Z0-9_]{2,10}\.(?:DAT|TXT|LST|ATT)")
PART_RE = re.compile(rb"[A-Z]{3,6}0{1,5}|\.DAT")          # POINT0, CRO00000, .DAT
DIR_RE = re.compile(rb"(?:MAPAL|REFER|RDSTM|BICON|HOUSE)00[0-9]")
# EU2011 build A: resolve(directory path, file name) -> file id or -1
RESOLVER_EU2011 = (0x40B << 12) + 0x358
# EU2011: the synchronous read request and the three wrappers that fill it
# from a file control block (firmware.md, "Who names which file")
READERS_EU2011 = [(0x3F6 << 12) + 0xC88, (0x3F7 << 12) + 0x384, (0x3F7 << 12) + 0x3DC, (0x3F7 << 12) + 0x480]
TABLE_GAP = 32            # two name pointers this close are one table


def strings_in(blob: bytes, base: int, limit: int) -> dict[int, tuple[str, str]]:
    """{va: (text, kind)} for NUL-terminated name strings below ``limit``."""
    out = {}
    pos = 0
    end = min(len(blob), limit - base)
    while pos < end:
        nul = blob.find(b"\0", pos, end)
        if nul < 0:
            break
        s = blob[pos:nul]
        if 3 <= len(s) <= 16 and (pos == 0 or blob[pos - 1] == 0):
            kind = None
            if NAME_RE.fullmatch(s):
                kind = "file"
            elif DIR_RE.fullmatch(s):
                kind = "dir"
            elif PART_RE.fullmatch(s):
                kind = "part"
            if kind:
                out[base + pos] = (s.decode("ascii"), kind)
        pos = nul + 1
    return out


class Graph:
    def __init__(self, functions: dict):
        self.fn = {int(k, 0): v for k, v in functions.items()}
        self.starts = sorted(self.fn)
        self.callers: dict[int, list[int]] = {}
        for k, v in self.fn.items():
            for c in v.get("calls", []):
                self.callers.setdefault(int(c, 0), []).append(k)

    def owner(self, va: int) -> int | None:
        i = bisect.bisect_right(self.starts, va) - 1
        if i < 0:
            return None
        k = self.starts[i]
        return k if va < k + max(self.fn[k]["len"], 2) else None


def pointer_words(blob: bytes, base: int, targets) -> dict[int, list[int]]:
    """{target va: [va of each aligned word equal to it]}."""
    want = set(targets)
    out: dict[int, list[int]] = {t: [] for t in want}
    for off in range(0, len(blob) - 3, 4):
        (w,) = struct.unpack_from("<I", blob, off)
        if w in want:
            out[w].append(base + off)
    return out


def census(blob: bytes, base: int, graph: Graph, limit: int) -> dict:
    names = strings_in(blob, base, limit)
    words = pointer_words(blob, base, names)
    loaders: dict[int, list[int]] = {}
    rodata: list[tuple[int, int]] = []           # (word va, string va)
    for sva, where in words.items():
        for wva in where:
            fn = graph.owner(wva)
            if fn is None:
                rodata.append((wva, sva))
            else:
                loaders.setdefault(sva, [])
                if fn not in loaders[sva]:
                    loaders[sva].append(fn)
    rodata.sort()
    tables: list[dict] = []
    for wva, sva in rodata:
        if tables and wva - tables[-1]["end"] <= TABLE_GAP:
            tables[-1]["end"] = wva + 4
            tables[-1]["names"].append(sva)
        else:
            tables.append({"start": wva, "end": wva + 4, "names": [sva]})
    # a function "loads a table" when one of its pool words points into it
    for t in tables:
        t["loaders"] = []
    if tables:
        starts = [t["start"] for t in tables]
        for off in range(0, len(blob) - 3, 4):
            (w,) = struct.unpack_from("<I", blob, off)
            i = bisect.bisect_right(starts, w) - 1
            if i >= 0 and tables[i]["start"] <= w < tables[i]["end"]:
                fn = graph.owner(base + off)
                if fn is not None and fn not in tables[i]["loaders"]:
                    tables[i]["loaders"].append(fn)
    return {"names": names, "loaders": loaders, "tables": tables}


def names_of(fn: int, cen: dict) -> dict:
    """Names function ``fn`` can pass: direct literals and tables it loads."""
    direct = sorted(cen["names"][s][0] for s, fns in cen["loaders"].items() if fn in fns)
    via = []
    for t in cen["tables"]:
        if fn in t["loaders"]:
            seen = []
            for s in t["names"]:
                text = cen["names"][s][0]
                if text not in seen:
                    seen.append(text)
            via.append({"table": t["start"], "names": seen})
    return {"direct": direct, "tables": via}


def near_reads(fn: int, graph: Graph, readers) -> list[int]:
    """Functions one call away from the opener that issue a read request:
    the opener, its callees, its callers and the callers' other callees."""
    def callees(f):
        return {int(c, 0) for c in graph.fn.get(f, {}).get("calls", [])}
    callers = set(graph.callers.get(fn, []))
    near = {fn} | callees(fn) | callers
    for c in callers:
        near |= callees(c)
    want = set(readers)
    return sorted(f for f in near if f not in want and callees(f) & want)


def openers(cen: dict, graph: Graph, resolver: int, readers=()) -> list[dict]:
    rows = []
    for fn in sorted(set(graph.callers.get(resolver, []))):
        row = {"fn": fn, "len": graph.fn[fn]["len"], "callers": sorted(set(graph.callers.get(fn, []))),
               "reads": near_reads(fn, graph, readers)}
        row.update(names_of(fn, cen))
        rows.append(row)
    return rows


# --------------------------------------------------------------------------
def load_text(image_path: str, image_start: int, module: str):
    import cerom
    data = Path(image_path).read_bytes()
    rom = cerom.CERom(data, image_start)
    secs = list(rom.o32(rom.module(module)))
    text = next(s for s in secs if s["flags"] & 0x20000000)
    off = rom.va2file(text["dataptr"])
    return data[off:off + text["psize"]], text["realaddr"]


def _load(args):
    blob, base = load_text(args.image, args.image_start, args.module)
    graph = Graph(json.loads(Path(args.graph).read_text())["functions"])
    limit = graph.starts[0]                      # rodata lies below the first function
    return blob, base, graph, census(blob, base, graph, limit)


def cmd_census(args) -> int:
    blob, base, graph, cen = _load(args)
    names, loaders = cen["names"], cen["loaders"]
    files = {s: n for s, n in names.items() if n[1] != "part"}
    with_loader = [s for s in files if loaders.get(s)]
    in_table = {s for t in cen["tables"] for s in t["names"]}
    print("name strings: %d (%d file, %d directory), %d with a loading function, %d only in tables, "
          "%d never referenced; %d name parts"
          % (len(files), sum(1 for n in files.values() if n[1] == "file"),
             sum(1 for n in files.values() if n[1] == "dir"), len(with_loader),
             sum(1 for s in files if not loaders.get(s) and s in in_table),
             sum(1 for s in files if not loaders.get(s) and s not in in_table),
             len(names) - len(files)))
    for s in sorted(names):
        text, kind = names[s]
        fns = ", ".join("%#010x" % f for f in sorted(loaders.get(s, [])))
        note = fns or ("table only" if s in in_table else "no reference")
        print("  %#010x  %-4s %-14s %s" % (s, kind, text, note))
    print("tables: %d" % len(cen["tables"]))
    for t in cen["tables"]:
        seen = []
        for s in t["names"]:
            if names[s][0] not in seen:
                seen.append(names[s][0])
        print("  %#010x..%#010x  %2d pointers  loaded by %s" % (
            t["start"], t["end"], len(t["names"]),
            ", ".join("%#010x" % f for f in sorted(t["loaders"])) or "no function"))
        print("      " + " ".join(seen))
    if args.json:
        Path(args.json).write_text(json.dumps({
            "schema": "osm2leaf.name_loaders/v1",
            "names": {"%#010x" % s: {"text": n[0], "kind": n[1],
                                     "loaders": ["%#010x" % f for f in sorted(loaders.get(s, []))]}
                      for s, n in names.items()},
            "tables": [{"start": "%#010x" % t["start"], "end": "%#010x" % t["end"],
                        "names": [names[s][0] for s in t["names"]],
                        "loaders": ["%#010x" % f for f in sorted(t["loaders"])]} for t in cen["tables"]],
        }, indent=1))
    return 0


def cmd_openers(args) -> int:
    blob, base, graph, cen = _load(args)
    resolver = int(args.resolver, 0) if args.resolver else RESOLVER_EU2011
    if resolver not in graph.fn:
        print("error: %#010x is not a function start in the graph" % resolver, file=sys.stderr)
        return 2
    readers = [int(x, 0) for x in args.readers.split(",")] if args.readers else READERS_EU2011
    rows = openers(cen, graph, resolver, readers)
    print("resolver %#010x: %d calling functions" % (resolver, len(rows)))
    for r in rows:
        print("  %#010x  len %#06x  direct: %s" % (r["fn"], r["len"], " ".join(r["direct"]) or "-"))
        for t in r["tables"]:
            print("      table %#010x: %s" % (t["table"], " ".join(t["names"])))
        print("      called by: %s" % (", ".join("%#010x" % c for c in r["callers"]) or "-"))
        print("      read requests one call away: %s" % (", ".join("%#010x" % c for c in r["reads"]) or "none"))
    if args.json:
        Path(args.json).write_text(json.dumps({"schema": "osm2leaf.name_openers/v1", "resolver": "%#010x" % resolver,
                                               "rows": [dict(r, fn="%#010x" % r["fn"],
                                                             callers=["%#010x" % c for c in r["callers"]],
                                                             reads=["%#010x" % c for c in r["reads"]])
                                                        for r in rows]}, indent=1))
    return 0


def selftest() -> int:
    fails = []

    def check(name, cond):
        print("  %-60s %s" % (name, "ok" if cond else "FAIL"))
        if not cond:
            fails.append(name)

    base = 0x10000
    blob = bytearray(0x400)

    def put(off, data):
        blob[off:off + len(data)] = data

    # rodata: strings at 0x000.., a pointer table at 0x100, code from 0x200
    put(0x000, b"POINT0\0\0")              # part
    put(0x008, b"MMAIN001.DAT\0")          # file, loaded directly by f1
    put(0x018, b"REFER001\0")              # dir, in the table
    put(0x024, b"ADDRE001.DAT\0")          # file, in the table only
    put(0x034, b"ORPHAN01.DAT\0")          # file, never referenced
    put(0x044, b"lower001.dat\0")          # not a name (lower case)
    put(0x054, b"xMMAIN002.DAT\0")         # not at a string start
    put(0x100, struct.pack("<III", base + 0x018, base + 0x024, 0))
    put(0x10C, struct.pack("<I", base + 0x000))
    # f1 at 0x200 (len 0x20): pool word -> MMAIN001.DAT; f2 at 0x240: pool -> table
    put(0x218, struct.pack("<I", base + 0x008))
    put(0x258, struct.pack("<I", base + 0x104))        # points into the table
    # a word equal to a string VA outside any function and far from the table
    put(0x3F0, struct.pack("<I", base + 0x008))
    functions = {
        "%#010x" % (base + 0x200): {"len": 0x20, "calls": ["%#010x" % (base + 0x300)]},
        "%#010x" % (base + 0x240): {"len": 0x20, "calls": ["%#010x" % (base + 0x300)]},
        "%#010x" % (base + 0x280): {"len": 0x20, "calls": []},
        "%#010x" % (base + 0x300): {"len": 0x20, "calls": []},
    }
    g = Graph(functions)
    cen = census(bytes(blob), base, g, base + 0x200)
    texts = sorted(n[0] for n in cen["names"].values())
    check("name strings found, case and string start respected",
          texts == ["ADDRE001.DAT", "MMAIN001.DAT", "ORPHAN01.DAT", "POINT0", "REFER001"])
    check("kinds: file / dir / part", cen["names"][base + 0x018][1] == "dir"
          and cen["names"][base][1] == "part" and cen["names"][base + 0x008][1] == "file")
    check("a pool word inside a function is a loader", cen["loaders"].get(base + 0x008) == [base + 0x200])
    check("a table-only name has no loader", base + 0x024 not in cen["loaders"])
    check("an unreferenced name has no loader and no table",
          base + 0x034 not in cen["loaders"] and all(base + 0x034 not in t["names"] for t in cen["tables"]))
    check("adjacent rodata pointers form one table; the far word is another",
          [(t["start"] - base, len(t["names"])) for t in cen["tables"]] == [(0x100, 3), (0x3F0, 1)])
    check("a pool word into the table names its loader", cen["tables"][0]["loaders"] == [base + 0x240])
    rows = openers(cen, g, base + 0x300)
    check("openers = callers of the resolver", [r["fn"] - base for r in rows] == [0x200, 0x240])
    check("direct names of an opener", rows[0]["direct"] == ["MMAIN001.DAT"] and rows[0]["tables"] == [])
    functions["%#010x" % (base + 0x280)]["calls"] = ["%#010x" % (base + 0x200), "%#010x" % (base + 0x2C0)]
    functions["%#010x" % (base + 0x2C0)] = {"len": 0x20, "calls": ["%#010x" % (base + 0x2E0)]}
    functions["%#010x" % (base + 0x2E0)] = {"len": 0x20, "calls": []}
    g2 = Graph(functions)
    rows2 = openers(cen, g2, base + 0x300, [base + 0x2E0])
    check("a read issued by the caller's other callee is one call away",
          rows2[0]["reads"] == [base + 0x2C0] and rows2[1]["reads"] == [])
    check("table names of an opener",
          rows[1]["tables"] == [{"table": base + 0x100, "names": ["REFER001", "ADDRE001.DAT", "POINT0"]}])
    # negative control: shift the table pointer out of the table -> no loader
    put(0x258, struct.pack("<I", base + 0x1F0))
    cen2 = census(bytes(blob), base, g, base + 0x200)
    check("negative: a pointer outside the table is not a table load", cen2["tables"][0]["loaders"] == [])
    check("owner() rejects an address between functions", g.owner(base + 0x230) is None
          and g.owner(base + 0x21F) == base + 0x200)
    print("name_loaders selftest: %s" % ("FAIL (%d)" % len(fails) if fails else "ok"))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("census", "openers"):
        p = sub.add_parser(name)
        p.add_argument("image")
        p.add_argument("--graph", required=True, help="call graph from callgraph.py build")
        p.add_argument("--module", default="Navi.exe")
        p.add_argument("--image-start", type=lambda x: int(x, 0), default=IMAGE_A)
        p.add_argument("--json")
        if name == "openers":
            p.add_argument("--resolver", help="VA of resolve(directory, name); default EU2011")
            p.add_argument("--readers", help="comma-separated VAs of the read-request functions; default EU2011")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmd:
        ap.print_help()
        return 2
    for path in (args.image, args.graph):
        if not Path(path).exists():
            print("error: missing input %s" % path, file=sys.stderr)
            return 2
    return {"census": cmd_census, "openers": cmd_openers}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
