#!/usr/bin/env python3
"""tile_graph_roundtrip.py - L2 golden for the section-2 route graph (M5.37).

A ``MAPAL001/BxxRyyR.DAT`` tile's section 2 is the router graph. This tool
checks that the graph a writer *emitted* is the graph the reader *decodes*
back from the tile bytes, at the level the writer round-trips today:

* compared (the "framing"): the record's absolute parcel ``(row, col)``
  from its parcel code (``rd_check.rowcol``); the node multiset
  ``(x, y)`` (11-bit parcel units); every link as ``(id, start (x, y),
  end (x, y))`` where the end is the entry whose id word carries ``0x2000``
  and both entries must name each other's node; every parcel-edge entry as
  ``(node (x, y), side bits, twin word)``; node and link counts;
* ``UNKNOWN`` (decoded, never compared, never asserted): ``w4``, ``w5``
  (one-way bits and regulation words), the class word, the time/length cost
  words, the country list, and the whole level-2/4/5 part b (odd records,
  M4.23/M4.24 open).

Writer = ``tools/ze0-viewer/tools_ze0/rd_encode.build_record_edges``; reader =
``clarion_rd.parse_record`` on ``rd_check.part_a``. A graph is a JSON file
``{"format": "ze0-sec2-graph/1", "records": [{"level", "row", "col",
"nodes": [[x, y]...], "links": [[i, j, id]...], "edges": [[i, side, twin]...]}]}``
with ``row``/``col`` the absolute parcel (``rd_check.rowcol``); a record is
found in a tile by ``(level, row, col)``, not by slot.

Commands::

    tile_graph_roundtrip.py check TILE [--emitted GRAPH.json] [--factory TILE]
        per section-2 record: emitted -> decoded graph compare (PASS/FAIL);
        records not in GRAPH must be byte-identical (inflated) to --factory
        ("preserved"). Verdict PASS | preserved | FAIL. A tile with no
        emitted record is never a graph match: it is "preserved" at best.
    tile_graph_roundtrip.py reemit TILE [--levels 1,2] [--limit N]
        decode every unit-0 record, emit the decoded graph with the writer,
        decode again and compare; counts PASS/FAIL and skips by named reason
    tile_graph_roundtrip.py inject TILE --out OUT --graph-out GRAPH.json
            [--level 1] [--dir Y,X] [--count N]
        fixture builder: re-emit N decoded records of one directory with the
        writer and patch them in place (zlib stream padded to the old span,
        the slot's plain-word count updated); writes the emitted graph
    tile_graph_roundtrip.py mutate TILE --graph GRAPH.json --out OUT
        negative control: move one link endpoint (node x +/-1) in the first
        emitted record of TILE
    tile_graph_roundtrip.py drop-link GRAPH.json --out GRAPH2.json
        negative control: the emitted graph minus one link
    tile_graph_roundtrip.py --selftest

Exit codes: 0 PASS / preserved, 1 FAIL, 2 usage. Read-only on its inputs.
Vendor bytes never leave the tile paths given; outputs go where pointed.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import shutil
import struct
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "ze0-viewer", "tools_ze0"))
import clarion_bg  # noqa: E402
import clarion_rd  # noqa: E402
import clarion_tile  # noqa: E402
import rd_check  # noqa: E402
import rd_encode  # noqa: E402
from tile_scan import TileScan  # noqa: E402

FORMAT = "ze0-sec2-graph/1"
PAIRED = (2, 4, 5)          # odd k on these levels is part b (UNKNOWN grammar)
END_FLAG = 0x2000
ID_MASK = 0x1fff
FOREIGN = 0x4000            # entry's far node lives in another record (factory)
COMPARED = ("code", "nodes", "links", "edges", "counts")
UNKNOWN = ("parcel-code bits outside rowcol (w0 bit 15 is set on every factory record)", "w4", "w5 (one-way, regulation words)", "class word", "cost words a/b",
           "countries", "part b (odd records, levels 2/4/5)")
DEFAULT_COUNTRY = 276


# ---------------------------------------------------------------------------
# decode


def _parse(plain: bytes, level: int):
    return clarion_rd.parse_record(rd_check.part_a(plain, level))


def indexed_graph(plain: bytes, level: int):
    """(graph, reasons) with node indices: nodes [(x, y)], links [(i, j, id)],
    edges [(i, side, twin)], code (w0, w1). reasons names what does not fit
    the framing model (unpaired ids, foreign ends, flag problems)."""
    rec = _parse(plain, level)
    reasons = []
    if "nnodes" not in rec:
        return None, ["no unit 0"]
    if rec.get("error") or rec["consumed"] != rec["unit_len"]:
        return None, ["body does not parse"]
    nodes = [(nd["x"], nd["y"]) for nd in rec["nodes"]]
    ends = collections.defaultdict(list)
    edges = []
    for i, nd in enumerate(rec["nodes"]):
        for e in nd["entries"]:
            if e["cls"] & 0x8000:
                edges.append((i, e["cls"] & 0xe000, e["other"]))
                continue
            if e["other"] & FOREIGN:
                reasons.append("foreign far node")
                continue
            if e["id"] & ~(ID_MASK | END_FLAG) & 0xffff:
                reasons.append("id word high bits")
            ends[(e["id"] & ID_MASK, e["cls"] & 0xff)].append((i, e))
    links = []
    for (lid, _c), lst in ends.items():
        if len(lst) != 2:
            reasons.append("id seen %d times" % len(lst))
            continue
        (ia, ea), (ib, eb) = lst
        fa, fb = bool(ea["id"] & END_FLAG), bool(eb["id"] & END_FLAG)
        if fa == fb:
            reasons.append("end flag on %s ends" % ("both" if fa else "neither"))
            continue
        if fa:
            (ia, ea), (ib, eb) = (ib, eb), (ia, ea)
        if ea["other"] != ib or eb["other"] != ia:
            reasons.append("ends do not name each other")
            continue
        links.append((ia, ib, lid))
    return dict(code=tuple(rd_check.rowcol(level, *rec["code"])), nodes=nodes, links=links, edges=edges,
                countries=list(rec.get("countries", []))), reasons


def framing(g) -> dict:
    """Index-free form of an indexed graph: what the check compares."""
    n = g["nodes"]
    return dict(
        code=tuple(g["code"]),
        nodes=sorted(map(tuple, n)),
        links=sorted((lid, tuple(n[i]), tuple(n[j])) for i, j, lid in g["links"]),
        edges=sorted((tuple(n[i]), side, twin) for i, side, twin in g["edges"]),
        counts=(len(n), len(g["links"]), len(g["edges"])),
    )


def compare(expected: dict, decoded: dict) -> list[str]:
    """Differences between two framings, one line per compared attribute."""
    out = []
    for key in COMPARED:
        a, b = expected[key], decoded[key]
        if a == b:
            continue
        if isinstance(a, list):
            ca, cb = collections.Counter(a), collections.Counter(b)
            miss, extra = list((ca - cb).elements()), list((cb - ca).elements())
            out.append("%s: %d emitted not decoded %s; %d decoded not emitted %s"
                       % (key, len(miss), miss[:3], len(extra), extra[:3]))
        else:
            out.append("%s: emitted %s, decoded %s" % (key, a, b))
    return out


# ---------------------------------------------------------------------------
# emit (the writer)


def emit(level: int, row: int, col: int, nodes, links, edges, country=DEFAULT_COUNTRY):
    """(plain, stored) for one record from an indexed graph, via rd_encode.

    Nodes without an entry are dropped by the writer (and so not part of the
    expected framing either)."""
    live = {i for i, j, _ in links} | {j for i, j, _ in links} | {i for i, _, _ in edges}
    keep = [i for i in range(len(nodes)) if i in live]
    pos = {old: new for new, old in enumerate(keep)}
    nn = [tuple(nodes[i]) for i in keep]
    ll = [(pos[i], pos[j], 1.0) for i, j, _ in links]
    ids = [lid for _, _, lid in links]
    ee = {pos[i]: (side, twin) for i, side, twin in edges}
    plain, stored = rd_encode.build_record_edges(level, 0, 0, row, col, nn, ll, ee,
                                                 ids=ids, country=country)
    return plain, stored


def expected_framing(level: int, row: int, col: int, nodes, links, edges) -> dict:
    live = {i for i, j, _ in links} | {j for i, j, _ in links} | {i for i, _, _ in edges}
    g = dict(code=(row, col), nodes=list(nodes), links=list(links), edges=list(edges))
    f = framing(g)
    f["nodes"] = sorted(tuple(nodes[i]) for i in range(len(nodes)) if i in live)
    f["counts"] = (len(f["nodes"]), len(links), len(edges))
    return f


def ids_repeat(g) -> bool:
    return len({lid for _, _, lid in g["links"]}) != len(g["links"])


def renumber(g):
    """The graph with link ids 1..n in link order, for factory records whose ids
    repeat across link classes (the reader pairs ends by (id, class low byte);
    the writer gives every link one class word, so repeated ids would merge)."""
    return dict(g, links=[(i, j, k + 1) for k, (i, j, _) in enumerate(g["links"])])


def writer_limits(g) -> list[str]:
    """Why the writer cannot express an indexed graph (empty when it can)."""
    out = []
    per = collections.Counter(i for i, _, _ in g["edges"])
    if any(c > 1 for c in per.values()):
        out.append("node with more than one parcel-edge entry")
    if len({lid for _, _, lid in g["links"]}) != len(g["links"]):
        out.append("link id repeated across classes")
    if any(lid > ID_MASK or lid == 0 for _, _, lid in g["links"]):
        out.append("link id out of range")
    deg = collections.Counter()
    for i, j, _ in g["links"]:
        deg[i] += 1
        deg[j] += 1
    for i, _, _ in g["edges"]:
        deg[i] += 1
    if any(d > 15 for d in deg.values()):
        out.append("node degree above 15")
    return out


# ---------------------------------------------------------------------------
# tile access


def dir_head(t: TileScan, off: int):
    return struct.unpack_from(">HHHHHH", t.m, off)


def section2_records(t: TileScan, levels=None):
    """Yield (level, rec) for every section-2 unit-0 record (odd part b skipped)."""
    for r in t.records(section=2):
        if levels and r.level not in levels:
            continue
        if r.level in PAIRED and r.k % 2:
            continue
        yield r.level, r


def record_key(level: int, plain: bytes):
    w0, w1 = struct.unpack_from(">HH", plain, 0)
    return (level,) + tuple(rd_check.rowcol(level, w0, w1))


def load_graph(path):
    with open(path) as f:
        d = json.load(f)
    if d.get("format") != FORMAT:
        raise ValueError("%s: format %r, want %r" % (path, d.get("format"), FORMAT))
    out = {}
    for r in d["records"]:
        key = (r["level"], r["row"], r["col"])
        out[key] = dict(nodes=[tuple(p) for p in r["nodes"]],
                        links=[tuple(x) for x in r["links"]],
                        edges=[tuple(x) for x in r["edges"]])
    return out


def dump_graph(path, records: dict):
    recs = [dict(level=k[0], row=k[1], col=k[2], nodes=[list(p) for p in g["nodes"]],
                 links=[list(x) for x in g["links"]], edges=[list(x) for x in g["edges"]])
            for k, g in sorted(records.items())]
    with open(path, "w") as f:
        json.dump(dict(format=FORMAT, records=recs), f, indent=0)
        f.write("\n")


def digest_map(path, levels=None):
    """{(level, row, col, ordinal): sha256 of the inflated record} for section 2,
    part-b records included (keyed by their unit-0 partner order)."""
    out = {}
    seen = collections.Counter()
    with TileScan(path) as t:
        for r in t.records(section=2):
            if levels and r.level not in levels:
                continue
            p = r.plain()
            key = record_key(r.level, p) + (r.k % 2 if r.level in PAIRED else 0,)
            n = seen[key]
            seen[key] += 1
            out[key + (n,)] = hashlib.sha256(p).hexdigest()
    return out


# ---------------------------------------------------------------------------
# commands


def check_tile(tile, emitted=None, factory=None, levels=None) -> dict:
    """The tile_graph_roundtrip verdict for one tile (see module doc)."""
    res = dict(tile=os.path.basename(str(tile)), emitted=0, match=0, fail=0,
               preserved=0, changed=0, missing=0, errors=[])
    em = emitted or {}
    found = set()
    with TileScan(tile) as t:
        for level, r in section2_records(t, levels):
            p = r.plain()
            key = record_key(level, p)
            if key not in em:
                continue
            found.add(key)
            res["emitted"] += 1
            g, reasons = indexed_graph(p, level)
            want = expected_framing(level, key[1], key[2], **em[key])
            diffs = (["decode: " + "; ".join(sorted(set(reasons)))] if g is None or reasons else []) \
                + (compare(want, framing(g)) if g is not None else [])
            if diffs:
                res["fail"] += 1
                res["errors"].append("%s: %s" % (key, " | ".join(diffs)))
            else:
                res["match"] += 1
    for key in sorted(set(em) - found):
        res["missing"] += 1
        res["errors"].append("%s: emitted record not in tile section 2" % (key,))
    if factory is not None:
        a, b = digest_map(tile, levels), digest_map(factory, levels)
        for k in sorted(set(a) | set(b)):
            if k[:3] in em:
                continue
            if a.get(k) == b.get(k):
                res["preserved"] += 1
            else:
                res["changed"] += 1
                if len(res["errors"]) < 20:
                    res["errors"].append("%s: not emitted and differs from factory" % (k,))
    if res["fail"] or res["missing"] or res["changed"]:
        res["verdict"] = "FAIL"
    elif res["match"]:
        res["verdict"] = "PASS"
    elif factory is not None and res["preserved"]:
        res["verdict"] = "preserved"
    else:
        res["verdict"] = "FAIL"
        res["errors"].append("nothing checked: no emitted record and no --factory")
    return res


def reemit_tile(tile, levels=None, limit=0) -> dict:
    res = dict(tile=os.path.basename(str(tile)), records=0, passed=0, failed=0, renumbered=0, skipped_records=0,
               skipped=collections.Counter(), by_level=collections.Counter(), errors=[])
    with TileScan(tile) as t:
        for level, r in section2_records(t, levels):
            if limit and res["records"] >= limit:
                break
            res["records"] += 1
            p = r.plain()
            g, reasons = indexed_graph(p, level)
            if g is None or reasons:
                res["skipped_records"] += 1
                for why in sorted(set(reasons)) or ["undecodable"]:
                    res["skipped"][why] += 1
                continue
            if ids_repeat(g):
                g = renumber(g)
                res["renumbered"] += 1
            lim = writer_limits(g)
            if lim:
                res["skipped_records"] += 1
                for why in lim:
                    res["skipped"]["writer: " + why] += 1
                continue
            _, row, col = record_key(level, p)
            plain, _ = emit(level, row, col, g["nodes"], g["links"], g["edges"],
                            (g["countries"] or [DEFAULT_COUNTRY])[0])
            g2, reasons2 = indexed_graph(plain, level)
            want = expected_framing(level, row, col, g["nodes"], g["links"], g["edges"])
            if framing(g) != want:
                res["skipped_records"] += 1
                res["skipped"]["code or node set not reproducible"] += 1
                continue
            diffs = (["decode: " + "; ".join(sorted(set(reasons2)))] if g2 is None or reasons2 else []) \
                + (compare(want, framing(g2)) if g2 is not None else [])
            if diffs:
                res["failed"] += 1
                if len(res["errors"]) < 20:
                    res["errors"].append("%s: %s" % ((level, row, col), " | ".join(diffs)))
            else:
                res["passed"] += 1
                res["by_level"][level] += 1
    res["verdict"] = "PASS" if res["passed"] and not res["failed"] else "FAIL"
    return res


def _slot_pair_off(t: TileScan, r):
    """Byte offset of the (ln, X) pair of record r in its directory slot body."""
    kind = struct.unpack_from(">H", t.m, r.dir_off)[0]
    body = {0x1046: 256, 0x2046: 512, 0x2146: 512, 0x2346: 512}.get(kind, 256)
    return r.dir_off + 12 + r.slot * (4 + body) + 4 + 8 * r.k


def inject(tile, out, graph_out, level=1, dirxy=None, count=8) -> dict:
    """Copy TILE to OUT and replace up to COUNT level-1 records (in directory
    DIRXY if given) by the writer's emission of their decoded graph."""
    if level != 1:
        raise ValueError("inject writes zlib level-1 records only")
    shutil.copyfile(tile, out)
    plan, emitted, skipped = [], {}, collections.Counter()
    with TileScan(tile) as t:
        for lv, r in section2_records(t, {level}):
            if len(plan) >= count:
                break
            _k, _a, _b, y, x, _typ = dir_head(t, r.dir_off)
            if dirxy and (y, (x + 1024) & 0xffff) != dirxy and (y, x) != dirxy:
                continue
            if not r.is_zlib:
                skipped["not zlib"] += 1
                continue
            p = r.plain()
            g, reasons = indexed_graph(p, lv)
            if g is not None and not reasons and ids_repeat(g):
                g = renumber(g)
            if g is None or reasons or writer_limits(g):
                skipped["not expressible"] += 1
                continue
            _, row, col = record_key(lv, p)
            plain, stored = emit(lv, row, col, g["nodes"], g["links"], g["edges"],
                                 (g["countries"] or [DEFAULT_COUNTRY])[0])
            if len(stored) > r.n:
                skipped["emission longer than factory span"] += 1
                continue
            plan.append((r.off, r.n, stored, _slot_pair_off(t, r), len(plain) // 2))
            emitted[(lv, row, col)] = dict(nodes=g["nodes"], links=g["links"], edges=g["edges"])
    with open(out, "r+b") as f:
        for off, n, stored, pair_off, words in plan:
            f.seek(off)
            f.write(stored + b"\0" * (n - len(stored)))
            f.seek(pair_off + 4)
            f.write(struct.pack(">I", words))
    dump_graph(graph_out, emitted)
    return dict(injected=len(plan), skipped=dict(skipped))


def mutate(tile, graph, out) -> dict:
    """Move one emitted link endpoint (x +/- 1) in the first emitted record found."""
    em = load_graph(graph)
    shutil.copyfile(tile, out)
    with TileScan(tile) as t:
        for level, r in section2_records(t, {1}):
            p = r.plain()
            key = record_key(level, p)
            if key not in em or not r.is_zlib:
                continue
            rec = _parse(p, level)
            for nd in rec["nodes"]:
                if any(not e["cls"] & 0x8000 for e in nd["entries"]):
                    break
            else:
                continue
            word = rec["pairs"][0][0] + nd["at"]
            w = struct.unpack_from(">H", p, 2 * word)[0]
            x = w & 0x7ff
            nx = x + 1 if x < 2047 else x - 1
            q = bytearray(p)
            struct.pack_into(">H", q, 2 * word, (w & ~0x7ff) | nx)
            c = zlib.compressobj(6, zlib.DEFLATED, 13, 8)
            comp = c.compress(bytes(q)) + c.flush()
            if len(comp) > r.n:
                continue
            with open(out, "r+b") as f:
                f.seek(r.off)
                f.write(comp + b"\0" * (r.n - len(comp)))
            return dict(record=key, node=(x, nd["y"]), moved_to=(nx, nd["y"]))
    raise SystemExit("mutate: no emitted level-1 record with a link found")


def drop_link(graph, out) -> dict:
    """Negative control for the falsifier: the emitted graph with one link fewer
    (the last link of the first record) written to OUT."""
    em = load_graph(graph)
    key = sorted(em)[0]
    em[key] = dict(em[key], links=em[key]["links"][:-1])
    dump_graph(out, em)
    return dict(record=key, links=len(em[key]["links"]))


# ---------------------------------------------------------------------------
# selftest: synthetic factory-shaped section 2, no vendor bytes


def _synthetic_tile(records: dict, level=1) -> bytes:
    """A minimal tile with one section (2) and one level-1 directory holding
    the emitted records, laid out by clarion_tile.write_tile."""
    rows = collections.defaultdict(dict)
    y0, x0 = 76, 940
    for (lv, row, col), g in records.items():
        plain, stored = emit(lv, row, col, g["nodes"], g["links"], g["edges"])
        rows[row % 32][col % 32] = (plain, stored)
    D = rd_encode.make_dir(level, y0, x0, rows)
    for s in D["slots"].values():
        s["block_off"], s["tag"] = -1, None
    hdr = bytearray(b"\0" * clarion_tile.TABLE1_OFF)
    struct.pack_into(">HBBBBH", hdr, clarion_tile.LEVEL_OFF, 1, 2, 1, level, D["typ"], 1)
    struct.pack_into(">IHI", hdr, clarion_tile.SECT_OFF, 0, 1, 0xffffffff)
    sec = dict(id=2, count=1, levels=[dict(level=level, typ=D["typ"], dirs=[D])])
    t = dict(header=bytes(hdr), sections=[sec])
    return clarion_tile.write_tile(t, clarion_tile.default_order(t), preserve_gaps=False)


def _fixture():
    # absolute parcel as rd_check.rowcol returns it (column modulo 16384 at level 1)
    base_r, base_c = 76 * 32, (940 * 32) % 16384
    # parcel A: a triangle plus a spur and one parcel-edge exit
    a = dict(nodes=[(100, 200), (900, 210), (500, 1500), (1800, 1700), (2047, 1000)],
             links=[(0, 1, 1), (1, 2, 2), (2, 0, 3), (2, 3, 4), (3, 4, 5)],
             edges=[(4, 0xa000, 0)])
    # parcel B: a two-link chain entering from the left edge
    b = dict(nodes=[(0, 1000), (700, 1100), (1400, 400)],
             links=[(0, 1, 1), (1, 2, 2)],
             edges=[(0, 0xe000, 4)])
    return {(1, base_r + 3, base_c + 7): a, (1, base_r + 3, base_c + 8): b}


def selftest() -> int:
    fails = 0

    def ok(cond, what):
        nonlocal fails
        print(("  ok   " if cond else "  FAIL ") + what)
        if not cond:
            fails += 1

    fx = _fixture()
    # 1. record level: emit -> decode equals the emitted framing
    for key, g in fx.items():
        plain, _ = emit(key[0], key[1], key[2], **g)
        dg, reasons = indexed_graph(plain, key[0])
        ok(not reasons and framing(dg) == expected_framing(key[0], key[1], key[2], **g),
           "record %s round-trips (nodes %d, links %d, edges %d)"
           % (key, len(g["nodes"]), len(g["links"]), len(g["edges"])))
    key = next(iter(fx))
    g = fx[key]
    plain, _ = emit(*key, **g)
    dec = framing(indexed_graph(plain, 1)[0])
    # 2. falsifier: one fewer emitted link must not match
    fewer = dict(g, links=g["links"][:-1])
    ok(compare(expected_framing(*key, **fewer), dec) != [], "one fewer link -> FAIL")
    # 3. falsifier: moved endpoint
    moved = dict(g, nodes=[(101, 200)] + g["nodes"][1:])
    ok(compare(expected_framing(*key, **moved), dec) != [], "moved endpoint -> FAIL")
    # 4. reversed link direction (end flag) must not match
    rev = dict(g, links=[(1, 0, 1)] + g["links"][1:])
    ok(compare(expected_framing(*key, **rev), dec) != [], "reversed link -> FAIL")
    # 5. edge side change must not match
    side = dict(g, edges=[(4, 0x8000, 0)])
    ok(compare(expected_framing(*key, **side), dec) != [], "edge side changed -> FAIL")
    # 6. tile level
    with tempfile.TemporaryDirectory() as d:
        tile, gpath = os.path.join(d, "T.DAT"), os.path.join(d, "g.json")
        with open(tile, "wb") as f:
            f.write(_synthetic_tile(fx))
        dump_graph(gpath, fx)
        em = load_graph(gpath)
        r = check_tile(tile, em, factory=tile)
        ok(r["verdict"] == "PASS" and r["match"] == 2, "tile: emitted graph decodes back (PASS, %d/2)" % r["match"])
        r = check_tile(tile, None, factory=tile)
        ok(r["verdict"] == "preserved" and r["match"] == 0 and r["preserved"] == 2,
           "tile vs itself without emitted graph -> preserved (never a graph match)")
        r = check_tile(tile, None, factory=None)
        ok(r["verdict"] == "FAIL", "tile with nothing to compare -> FAIL")
        em2 = dict(em)
        em2[key] = dict(em[key], links=em[key]["links"][:-1])
        r = check_tile(tile, em2, factory=tile)
        ok(r["verdict"] == "FAIL", "tile: emitted graph with one fewer link -> FAIL")
        g3 = os.path.join(d, "g3.json")
        drop_link(gpath, g3)
        r = check_tile(tile, load_graph(g3), factory=tile)
        ok(r["verdict"] == "FAIL", "tile: drop-link graph -> FAIL")
        neg = os.path.join(d, "N.DAT")
        m = mutate(tile, gpath, neg)
        r = check_tile(neg, em, factory=tile)
        ok(r["verdict"] == "FAIL" and r["fail"] == 1, "tile: endpoint moved %s -> FAIL" % (m["node"],))
        r = reemit_tile(tile)
        ok(r["verdict"] == "PASS" and r["passed"] == 2, "reemit: 2/2 records")
        inj, g2 = os.path.join(d, "I.DAT"), os.path.join(d, "g2.json")
        info = inject(tile, inj, g2, count=8)
        r = check_tile(inj, load_graph(g2), factory=tile)
        ok(info["injected"] == 2 and r["verdict"] == "PASS", "inject: 2 records re-emitted in place, PASS")
    print("selftest:", "OK" if not fails else "FAIL", "(%d failure(s))" % fails)
    return 1 if fails else 0


# ---------------------------------------------------------------------------


def _levels(s):
    return {int(x) for x in s.split(",")} if s else None


def _dirxy(s):
    if not s:
        return None
    y, x = s.split(",")
    return int(y), int(x)


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if "--selftest" in argv:
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="run the synthetic self-test")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("tile")
    c.add_argument("--emitted")
    c.add_argument("--factory")
    c.add_argument("--levels")
    c.add_argument("--json")
    r = sub.add_parser("reemit")
    r.add_argument("tile")
    r.add_argument("--levels")
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--json")
    i = sub.add_parser("inject")
    i.add_argument("tile")
    i.add_argument("--out", required=True)
    i.add_argument("--graph-out", required=True)
    i.add_argument("--dir")
    i.add_argument("--count", type=int, default=8)
    m = sub.add_parser("mutate")
    m.add_argument("tile")
    m.add_argument("--graph", required=True)
    m.add_argument("--out", required=True)
    dl = sub.add_parser("drop-link")
    dl.add_argument("graph")
    dl.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "check":
        res = check_tile(a.tile, load_graph(a.emitted) if a.emitted else None,
                         a.factory, _levels(a.levels))
    elif a.cmd == "reemit":
        res = reemit_tile(a.tile, _levels(a.levels), a.limit)
        res["skipped"] = dict(res["skipped"].most_common())
        res["by_level"] = dict(res["by_level"])
    elif a.cmd == "inject":
        res = inject(a.tile, a.out, a.graph_out, 1, _dirxy(a.dir), a.count)
        res["verdict"] = "PASS" if res["injected"] else "FAIL"
    elif a.cmd == "drop-link":
        res = drop_link(a.graph, a.out)
        res["verdict"] = "PASS"
    else:
        res = mutate(a.tile, a.graph, a.out)
        res["verdict"] = "PASS"
    res["compared"] = list(COMPARED)
    res["unknown"] = list(UNKNOWN)
    text = json.dumps(res, indent=1, default=list)
    if getattr(a, "json", None):
        with open(a.json, "w") as f:
            f.write(text + "\n")
    print(text)
    print("tile_graph_roundtrip:", res["verdict"])
    return 0 if res["verdict"] in ("PASS", "preserved") else 1


if __name__ == "__main__":
    raise SystemExit(main())
