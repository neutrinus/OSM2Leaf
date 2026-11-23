#!/usr/bin/env python3
"""sec2_writer.py — write the level-1 route graph (section 2) of a generated tile (M5.57).

``tilewriter.build_road_record(..., graph=True)`` splits drawn links at
junctions, numbers them per class and lists them in ``last_graph``.  This
module turns those lists into section-2 level-1 records with the field rules
read off the firmware and the factory London tile (M4.98, M9.75, M4.39):

* record header: parcel code (words 0, 1), five unit pairs (only unit 0 used),
  word 26 = ISO 3166 country;
* unit 0: node count, link count, 11 (nodes, links) pairs by node group, then
  per node 3 words (``x | links << 12``, ``y | min class << 12``, 0) and its
  links;
* link (7 words, no extras): ``w0`` far node, ``w1`` class attribute word
  (the factory's commonest per class), ``w2 = direction << 14`` (0 free,
  1 may leave here, 2 may not leave here), ``w3`` link id ``| 0x2000`` at the
  drawn last point, ``w4 = class | class << 8`` ``| 0x10`` on two-way links
  only (factory: 99.5 % of two-way, 18.5 % of one-way entries), ``w5`` cost, ``w6``
  length in metres (12-bit mantissa, 2-bit scale);
* boundary link where a node sits on the parcel edge and the neighbour parcel
  has a node at the same edge point: ``w0`` node index in the neighbour,
  ``w4 = 0x8000 | side << 13 | (inner w4 & 0x1fff)`` (side N 0, E 1, S 2, W 3),
  ``w1`` = the inner link's ``w1`` (as in the factory), other words 0.

Not written (left 0 / absent): turn restrictions and conditions, unit 2,
node word 2, ``w4 & 0x4000``, level 2 and unit 1.

    sec2_writer.py --selftest
"""
from __future__ import annotations

import collections
import math
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE / "ze0-viewer" / "tools_ze0", HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

EDGE = 0x7FF
# node group (unit-0 pair index) by the lowest class at the node (factory census, M5.57)
GROUP = {0: 0, 1: 1, 2: 2, 3: 2, 4: 2, 5: 2, 6: 2, 7: 2, 8: 3, 9: 4}
# commonest w1 per class in B48R068R (meaning: cost-function attributes, C-9936)
W1 = {1: 0x1002, 4: 0x0002, 5: 0x0002, 6: 0x7002, 7: 0x0002}
# median cost/length per class in B48R068R (w5 / w6)
COST_PER_M = {1: 0.28, 2: 1.58, 3: 0.24, 4: 0.67, 5: 0.70, 6: 0.67, 7: 0.72, 8: 0.72,
              9: 0.73, 10: 0.24, 11: 2.4, 12: 3.6}
SCALE_W5 = (1, 2, 4, 40)
SCALE_W6 = (1, 2, 4, 20)


class GraphError(ValueError):
    pass


def group(cls: int) -> int:
    return GROUP.get(cls, 10)


def encode(value: float, scales) -> int:
    """Smallest scale whose 12-bit mantissa holds ``value`` (rounded)."""
    v = max(1, int(round(value)))
    for i, s in enumerate(scales):
        m = int(round(v / s))
        if m <= 0xFFF:
            return (i << 12) | max(1, m)
    return (3 << 12) | 0xFFF


def decode(word: int, scales) -> int:
    return (word & 0xFFF) * scales[(word >> 12) & 3]


def step(v: int, d: int) -> int:
    """Neighbour parcel code word (level 1): low 2 bits then the nibble above."""
    lo, hi = v & 3, v >> 4
    lo += d
    if lo > 3:
        lo, hi = 0, hi + 1
    elif lo < 0:
        lo, hi = 3, hi - 1
    return (hi << 4) | 0xC | lo


SIDES = {"N": (0, (1, 0)), "E": (1, (0, 1)), "S": (2, (-1, 0)), "W": (3, (0, -1))}


def edge_side(x: int, y: int):
    on = [s for s, c in (("W", x == 0), ("E", x == EDGE), ("S", y == 0), ("N", y == EDGE)) if c]
    return on[0] if len(on) == 1 else None


def mirror(side: str, x: int, y: int):
    return {"E": (0, y), "W": (EDGE, y), "N": (x, 0), "S": (x, EDGE)}[side]


def metres(pts, unit_m):
    ux, uy = unit_m
    return sum(math.hypot((b[0] - a[0]) * ux, (b[1] - a[1]) * uy) for a, b in zip(pts, pts[1:]))


def parcel_graph(links):
    """Nodes and per-node link entries of one parcel.

    ``links``: ``[dict(cls, lid, pts, oneway, length)]``.  Returns
    ``(order, entries)``: node (x, y) in record order and ``{xy: [entry]}``
    with entry = (far xy, link, at_last_point, direction)."""
    ent = collections.defaultdict(list)
    for L in links:
        a, b = L["pts"][0], L["pts"][-1]
        if a == b:
            continue
        ow = L["oneway"]
        da, db = (1, 2) if ow > 0 else (2, 1) if ow < 0 else (0, 0)
        ent[a].append((b, L, False, da))
        ent[b].append((a, L, True, db))
    order = sorted(ent, key=lambda xy: (group(min(e[1]["cls"] for e in ent[xy])), xy[1], xy[0]))
    return order, ent


def record_words(code, order, ent, country, boundary=None):
    """Section-2 level-1 record words (big-endian halfwords).

    ``boundary``: ``{xy: (side, neighbour node index)}``."""
    boundary = boundary or {}
    index = {xy: i for i, xy in enumerate(order)}
    pairs = [[0, 0] for _ in range(11)]
    body = []
    nlinks = 0
    for xy in order:
        es = ent[xy]
        cmin = min(e[1]["cls"] for e in es)
        n = len(es) + (1 if xy in boundary else 0)
        if n > 15:
            raise GraphError("node %r has %d links (max 15)" % (xy, n))
        body += [xy[0] | n << 12, xy[1] | cmin << 12, 0]
        inner_w4 = None
        for far, L, last, d in es:
            cls = L["cls"]
            if L["lid"] > 0x1FFF:
                raise GraphError("link id %d of class %d above 0x1fff" % (L["lid"], cls))
            # 0x10: set on 99.5 % of two-way and 18.5 % of one-way factory links, never on closed ones
            w4 = cls | L.get("typ", cls) << 8 | (0x10 if d == 0 else 0)
            if inner_w4 is None:
                inner_w4, inner_w1 = w4, W1.get(cls, 0)
            ln = L["length"]
            body += [index[far], W1.get(cls, 0), d << 14, L["lid"] | (0x2000 if last else 0), w4,
                     encode(ln * COST_PER_M.get(cls, 0.72), SCALE_W5), encode(ln, SCALE_W6)]
        if xy in boundary:
            side, far = boundary[xy]
            body += [far, inner_w1, 0, 0, 0x8000 | SIDES[side][0] << 13 | (inner_w4 & 0x1FFF), 0, 0]
        g = group(cmin)
        pairs[g][0] += 1
        pairs[g][1] += n
        nlinks += n
    unit = [len(order) >> 16, len(order) & 0xFFFF, nlinks >> 16, nlinks & 0xFFFF]
    unit += [v for p in pairs for v in p] + body
    head = [code[0], code[1], 0, 0, 0, 0, 0, 27, len(unit) >> 16, len(unit) & 0xFFFF]
    head += [0xFFFF, 0xFFFF, 0, 0] * 4 + [country]
    return head + unit


def scc(n: int, succ) -> list[int]:
    """Strongly connected component id per node (iterative Tarjan); ``succ[v]`` lists successors."""
    index = [-1] * n
    low = [0] * n
    on = [False] * n
    comp = [-1] * n
    stack, counter, ncomp = [], 0, 0
    for root in range(n):
        if index[root] != -1:
            continue
        work = [(root, 0)]
        while work:
            v, i = work.pop()
            if i == 0:
                index[v] = low[v] = counter
                counter += 1
                stack.append(v)
                on[v] = True
            recurse = False
            nxt = succ[v]
            while i < len(nxt):
                w = nxt[i]
                i += 1
                if index[w] == -1:
                    work.append((v, i))
                    work.append((w, 0))
                    recurse = True
                    break
                if on[w]:
                    low[v] = min(low[v], index[w])
            if recurse:
                continue
            if low[v] == index[v]:
                while True:
                    w = stack.pop()
                    on[w] = False
                    comp[w] = ncomp
                    if w == v:
                        break
                ncomp += 1
            if work:
                u = work[-1][0]
                low[u] = min(low[u], low[v])
    return comp


def free_oneway_traps(prepared: dict, bounds: dict) -> int:
    """Make two-way every one-way link that joins two strongly connected parts.

    A dropped way (``--max-plain`` trimming) or an OSM one-way stub leaves
    places that can be entered but not left, or the reverse; the factory has
    almost none (13 one-way dead ends in B48R068R against 1,165 in the London
    OSM build) and the route search fails when the destination sits in one
    (M5.57, L4 ``NET SRCH --> SRCH NORT``).  After this every weakly connected
    part of the tile graph is strongly connected.  Returns links freed."""
    ids = {}
    for parcel, (code, order, _ent) in prepared.items():
        for xy in order:
            ids[(tuple(code), xy)] = len(ids)
    succ = [[] for _ in ids]
    for parcel, (code, order, ent) in prepared.items():
        c = tuple(code)
        for xy in order:
            v = ids[(c, xy)]
            for far, _L, _last, d in ent[xy]:
                if d in (0, 1):
                    succ[v].append(ids[(c, far)])
            if xy in bounds[parcel]:
                side, _j, nb = bounds[parcel][xy]
                w = ids.get((nb, mirror(side, *xy)))
                if w is not None:
                    succ[v].append(w)
                    succ[w].append(v)
    comp = scc(len(ids), succ)
    freed = 0
    for parcel, (code, order, ent) in prepared.items():
        c = tuple(code)
        for xy in order:
            for far, L, last, d in ent[xy]:
                if d == 1 and L["oneway"] and comp[ids[(c, xy)]] != comp[ids[(c, far)]]:
                    L["oneway"] = 0
                    freed += 1
    return freed


def build(graphs: dict, country: int, free_traps: bool = True):
    """``{parcel: (code, links, unit_m)}`` -> ``{parcel: (plain, comp)}`` and stats."""
    by_code = {}
    prepared = {}
    st = collections.Counter()
    for parcel, (code, links, unit_m) in graphs.items():
        for L in links:
            L["length"] = metres(L["pts"], unit_m)
        order, ent = parcel_graph(links)
        if not order:
            continue
        if len(order) > 0x3FFF:
            raise GraphError("parcel %r has %d nodes (max 0x3fff)" % (parcel, len(order)))
        prepared[parcel] = (code, order, ent)
        by_code[tuple(code)] = (order, {xy: i for i, xy in enumerate(order)}, ent)
    bounds = {}
    for parcel, (code, order, ent) in prepared.items():
        boundary = {}
        for xy in order:
            side = edge_side(*xy)
            if side is None or len(ent[xy]) != 1:
                continue
            dy, dx = SIDES[side][1]
            nb = (step(code[0], dy) if dy else code[0], step(code[1], dx) if dx else code[1])
            other = by_code.get(nb)
            if other is None:
                continue
            j = other[1].get(mirror(side, *xy))
            if j is None or len(other[2][mirror(side, *xy)]) != 1:
                continue
            boundary[xy] = (side, j, nb)
        bounds[parcel] = boundary
    if free_traps:
        st["oneway links freed (SCC)"] = free_oneway_traps(prepared, bounds)
        for parcel, (code, order, ent) in list(prepared.items()):
            _order, ent = parcel_graph(graphs[parcel][1])
            prepared[parcel] = (code, order, ent)
    out = {}
    for parcel, (code, order, ent) in prepared.items():
        boundary = {xy: v[:2] for xy, v in bounds[parcel].items()}
        w = record_words(code, order, ent, country, boundary)
        if len(w) > 0x10000:
            raise GraphError("parcel %r route record is %d words; the directory pair table "
                             "addresses at most 0x10000 (lower --max-plain)" % (parcel, len(w)))
        plain = struct.pack(">%dH" % len(w), *w)
        comp = zlib.compress(plain, 6)
        if len(comp) % 2:
            comp += b"\0"
        out[parcel] = (plain, comp)
        st["records"] += 1
        st["nodes"] += len(order)
        st["links"] += sum(len(v) for v in ent.values())
        st["boundary"] += len(boundary)
        st["oneway link ends"] += sum(1 for v in ent.values() for e in v if e[3])
    return out, dict(st)


def place(m: dict, built: dict) -> dict:
    """Put ``{(y0, x0, row, col): (plain, comp)}`` into the section-2 level-1
    slot directories of an (empty) ``tile_relayout`` model."""
    import tilewriter
    dirs = {}
    for sec in m["sections"]:
        if sec["id"] != 2:
            continue
        for L in sec["levels"]:
            if L["level"] != 1:
                continue
            for dm in L["dirs"]:
                D = dm["D"]
                dirs[(D["y"], tilewriter.dir_x0(D))] = dm
    rows = collections.defaultdict(dict)
    for (y0, x0, row, col), rec in built.items():
        if (y0, x0) not in dirs:
            raise GraphError("no section-2 directory for parcel %r" % ((y0, x0, row, col),))
        rows[(y0, x0, row)][col] = rec
    st = collections.Counter()
    for (y0, x0, row), cols in rows.items():
        dm = dirs[(y0, x0)]
        D = dm["D"]
        words = [0xFFFFFFFF] * (D["body"] // 4)
        recs = []
        for col in sorted(cols):
            plain, comp = cols[col]
            words[2 * col] = len(comp) // 2
            words[2 * col + 1] = len(plain) // 2
            recs.append(dict(k=col, raw=comp, words=len(plain) // 2, flag=0))
            st["records"] += 1
        body = struct.pack(">%dI" % len(words), *words)
        D["slots"][row] = dict(tag=0, body=body, recs=recs, block_off=-1)
        D.get("empty_tags", {}).pop(row, None)
        D.get("empty_bodies", {}).pop(row, None)
        dm["units"][row].update(live=True, old=("sec2", y0, x0, row), tag=0,
                                block=b"".join(r["raw"] for r in recs), recs=[r["raw"] for r in recs])
        st["rows"] += 1
    return dict(st)


def selftest() -> int:
    from sec2_fields import check_record, graph as unit_graph
    # two parcels side by side; a one-way street crosses the shared edge
    A, B = (0xA40C, 0xCC0F), (0xA40C, 0xCC1C)
    gA = [dict(cls=8, lid=1, pts=[(100, 100), (EDGE, 100)], oneway=1),
          dict(cls=5, lid=1, pts=[(100, 100), (100, 900)], oneway=0)]
    gB = [dict(cls=8, lid=1, pts=[(0, 100), (500, 100)], oneway=1)]
    import copy
    graphs = {"A": (A, gA, (1.1, 1.1)), "B": (B, gB, (1.1, 1.1))}
    _b, st2 = build(copy.deepcopy(graphs), 826)
    assert st2["oneway links freed (SCC)"] == 2 and st2["oneway link ends"] == 0, st2
    ring = [dict(cls=8, lid=i + 1, pts=[p, q], oneway=1) for i, (p, q) in
            enumerate([((10, 10), (90, 10)), ((90, 10), (50, 90)), ((50, 90), (10, 10))])]
    ring.append(dict(cls=8, lid=9, pts=[(50, 90), (50, 300)], oneway=0))
    _b, st3 = build({"R": (A, ring, (1.1, 1.1))}, 826)
    assert st3["oneway links freed (SCC)"] == 0 and st3["oneway link ends"] == 6, st3
    built, st = build(graphs, 826, free_traps=False)
    assert st["boundary"] == 2, st
    for k, (plain, comp) in built.items():
        w = list(struct.unpack(">%dH" % (len(plain) // 2), plain))
        c = collections.Counter()
        check_record(w, c)
        assert c["header: sum of 11 pair firsts == node count"] == 1, c
        assert c["boundary link at a mesh-edge node"] == c["boundary link (w4 & 0x8000)"] == 1, (k, c)
        assert zlib.decompress(comp)[:len(plain)] == plain
    w = list(struct.unpack(">%dH" % (len(built["A"][0]) // 2), built["A"][0]))
    c = collections.Counter()
    check_record(w, c)
    assert c["direction one-way (1/2)"] == 1 and c["direction two-way (0/0)"] == 1, c
    xy, links = unit_graph(w[27:])
    assert [decode(lw[6], SCALE_W6) for lw in links[xy.index((100, 100))]] == [2142, 880], links
    assert encode(5000, SCALE_W6) == (1 << 12) | 2500 and decode(encode(80000, SCALE_W6), SCALE_W6) == 80000
    print("sec2_writer selftest OK: framing, one-way pairing, boundary links, length encoding, one-way traps")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    print(__doc__)
    sys.exit(2)
