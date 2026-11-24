#!/usr/bin/env python3
"""sec2_level2.py — the section-2 level-2 route graph of a generated tile (M5.103).

The route search runs long routes top-down (``LEV4Top``/``LEV5Top``, then
``LEV2DSIDE``, ``LEV1DSIDE``; C-10057, C-10075).  Level 2 is the level-1
graph of the main roads, drawn on meshes of 4 x 4 level-1 meshes.  The rules
here are measured on the factory London tile (``B48R068R``, M4.98 C-9938 and
EXP-2026-11-23-M5.103):

* level-2 classes: 1-7 plus the ferry classes 10 and 11 (C-10074);
* a level-1 node is a level-2 node exactly when its node word 2 has
  ``0x2000`` (430,438 / 430,438 both ways); the factory sets it at junctions
  of level-2 roads (level-2 degree other than 2), at dead ends, on the outer
  edge of the level-2 mesh, where the class, ``w1`` or the one-way sense
  changes, and at further points; extra level-2 nodes are harmless;
* a level-2 link is the chain of level-1 links between two level-2 nodes:
  its cost ``w5`` and length ``w6`` are the sums over the chain (87,774 /
  87,774 within 2 %), its class the chain's class;
* level-2 coordinates are level-1 coordinates / 4 across the 16 level-1
  meshes (``x2 = (col * 2048 + x) // 4``);
* records come in pairs with the level-2 key (``w0 & 0xfff0 | 0xf``,
  ``w1 & 0xfff0 | 0x2``): unit 0 (the graph, level-1 format) and unit 1
  (``[node count, 0x2100, entries, key]``; entry = ``links << 12``, a self
  triple ``(level-2 node, row << 14 | col << 6, level-1 node)`` and one
  triple per link ``(target, selector, first level-1 step)``; a boundary
  link's triple names the neighbour mesh's selector and level-1 node);
* a slot directory row holds the pair at ``k = 2 col`` (unit 0) and
  ``k = 2 col + 1`` (unit 1).

Unit 1 word 1 is ``0x?100`` in the factory with the top nibble 2...c; its
meaning is unknown and ``0x2100`` is written.

    sec2_level2.py --selftest
"""
from __future__ import annotations

import collections
import struct
import sys
import zlib

import sec2_writer as W

L2_CLASSES = frozenset(range(1, 8)) | {10, 11}


def l2_key(code):
    """Level-2 mesh key of a level-1 mesh code, and the level-1 mesh's (row, col) in it."""
    return ((code[0] & 0xFFF0) | 0xF, (code[1] & 0xFFF0) | 0x2), (code[0] & 3, code[1] & 3)


def l2_xy(sub, xy):
    row, col = sub
    return (col * 2048 + xy[0]) // 4, (row * 2048 + xy[1]) // 4


def selector(sub):
    return sub[0] << 14 | sub[1] << 6


class Net:
    """The level-1 graph of a tile: node ids, entries and boundary hops."""

    def __init__(self, prepared, bounds):
        self.ids, self.node = {}, []
        for parcel, (code, order, _ent) in prepared.items():
            for i, xy in enumerate(order):
                self.ids[(tuple(code), xy)] = len(self.node)
                self.node.append((tuple(code), xy, i, parcel))
        self.ent = [None] * len(self.node)
        self.hop = {}
        for parcel, (code, order, ent) in prepared.items():
            c = tuple(code)
            for xy in order:
                v = self.ids[(c, xy)]
                self.ent[v] = [(self.ids[(c, far)], L, last, d) for far, L, last, d in ent[xy]]
                b = bounds[parcel].get(xy)
                if b is not None:
                    side, _j, nb = b
                    w = self.ids.get((nb, W.mirror(side, *xy)))
                    if w is not None:
                        self.hop[v] = (w, side)

    def l2_entries(self, v):
        return [e for e in self.ent[v] if e[1]["cls"] in L2_CLASSES]


def mark(net: Net) -> set:
    """Level-1 node ids that become level-2 nodes."""
    out = set()
    for v, ents in enumerate(net.ent):
        es = net.l2_entries(v)
        if not es:
            continue
        code, xy, _i, _p = net.node[v]
        if v in net.hop:
            w = net.hop[v][0]
            if l2_key(net.node[w][0])[0] != l2_key(code)[0]:
                out.add(v)          # outer edge of the level-2 mesh
            continue                 # inner level-1 edge: the chain goes on
        if len(es) != 2:
            out.add(v)
            continue
        (_, a, _, da), (_, b, _, db) = es
        if (a["cls"], a.get("typ", a["cls"])) != (b["cls"], b.get("typ", b["cls"])):
            out.add(v)
        elif (da, db) not in ((0, 0), (1, 2), (2, 1)):
            out.add(v)
    return out


def walk(net: Net, flagged: set, v: int, e):
    """Follow level-2 entry ``e`` from level-2 node ``v`` to the next level-2 node.

    Returns ``(end node, the node before it, length m, cost, direction at v, first
    step)`` or ``None`` when the chain loops back without a level-2 node."""
    far, L, _last, d0 = e
    first = far
    length = L["length"]
    cost = L["length"] * W.COST_PER_M.get(L["cls"], 0.72)
    oneway = d0 != 0
    prev, cur = v, far
    seen = {v}
    while cur not in flagged:
        if cur in seen:
            return None
        seen.add(cur)
        if cur in net.hop and len(net.l2_entries(cur)) == 1 and net.l2_entries(cur)[0][0] == prev:
            prev, cur = cur, net.hop[cur][0]
            continue
        nxt = [x for x in net.l2_entries(cur) if x[0] != prev]
        if prev in net.hop and net.hop[prev][0] == cur:
            nxt = net.l2_entries(cur)
        if len(nxt) != 1:
            return None
        x = nxt[0]
        length += x[1]["length"]
        cost += x[1]["length"] * W.COST_PER_M.get(x[1]["cls"], 0.72)
        oneway = oneway and x[3] != 0
        prev, cur = cur, x[0]
    return cur, prev, length, cost, (d0 if oneway else 0), first


def build_level2(prepared: dict, bounds: dict, country: int):
    """Return ``(flagged level-1 (code, xy) set, {(y0, x0, row, col): (u0 plain, u0 comp,
    u1 plain, u1 comp)}, stats)`` for the level-2 directories (row/col in 32 x 32 level-2
    meshes of a directory that spans 4 x 4 level-1 directories)."""
    net = Net(prepared, bounds)
    flagged = mark(net)
    st = collections.Counter()
    # chains that loop without a level-2 node: give each one a node
    links = {}
    for _round in range(3):
        todo = []
        for v in sorted(flagged):
            for e in net.l2_entries(v):
                r = walk(net, flagged, v, e)
                if r is None:
                    todo.append(e[0])
                else:
                    links[(v, e[0])] = r
        if not todo:
            break
        flagged.update(todo)
        links.clear()
    def outer_hop(v):
        return v in net.hop and l2_key(net.node[net.hop[v][0]][0])[0] != l2_key(net.node[v][0])[0]

    # level-2 nodes per mesh
    mesh_nodes = collections.defaultdict(list)
    for v in flagged:
        code, xy, _i, _p = net.node[v]
        key, sub = l2_key(code)
        mesh_nodes[key].append(v)
    index, xy2 = {}, {}
    for key, vs in mesh_nodes.items():
        def sortkey(v):
            code, xy, _i, _p = net.node[v]
            sub = l2_key(code)[1]
            cmin = min(e[1]["cls"] for e in net.l2_entries(v))
            p = l2_xy(sub, xy)
            return (W.group(cmin), p[1], p[0], v)
        vs.sort(key=sortkey)
        for i, v in enumerate(vs):
            index[v] = i
            code, xy, _i, _p = net.node[v]
            x2, y2 = l2_xy(l2_key(code)[1], xy)
            if not outer_hop(v):
                # only boundary nodes may sit on a mesh edge (C-10064, level 2 too)
                x2, y2 = min(max(x2, 1), 0x7FE), min(max(y2, 1), 0x7FE)
            xy2[v] = (x2, y2)
    # link ids: one per chain, shared by its two ends
    lid, next_id, canon = {}, collections.Counter(), {}
    for (v, f), (end, prev, ln, cost, d, first) in sorted(links.items()):
        a, b = (v, f), (end, prev)
        k = min(a, b)
        if k not in canon:
            cls = None
            for e in net.l2_entries(v):
                if e[0] == f:
                    cls = e[1]["cls"]
            key = l2_key(net.node[v][0])[0]
            next_id[(key, cls)] += 1
            canon[k] = next_id[(key, cls)]
        lid[a] = (canon[k], a != k)
    out = {}
    for key, vs in mesh_nodes.items():
        body, pairs, nlinks, u1 = [], [[0, 0] for _ in range(11)], 0, []
        for v in vs:
            code, xy, i1, _p = net.node[v]
            sub = l2_key(code)[1]
            es = [e for e in net.l2_entries(v) if (v, e[0]) in links]
            hop = net.hop.get(v) if v in net.hop and l2_key(net.node[net.hop[v][0]][0])[0] != key else None
            n = len(es) + (1 if hop else 0)
            if n > 15:
                raise W.GraphError("level-2 node with %d links" % n)
            cmin = min(e[1]["cls"] for e in net.l2_entries(v))
            x2, y2 = xy2[v]
            body += [x2 | n << 12, y2 | cmin << 12, 0]
            triples = [index[v], selector(sub), i1]
            inner_w4 = inner_w1 = None
            for e in es:
                end, prev, ln, cost, d, first = links[(v, e[0])]
                cls, typ = e[1]["cls"], e[1].get("typ", e[1]["cls"])
                ident, last = lid[(v, e[0])]
                if ident > 0x1FFF:
                    raise W.GraphError("level-2 link id above 0x1fff")
                w4 = cls | typ << 8 | (0x10 if d == 0 else 0)
                if inner_w4 is None:
                    inner_w4, inner_w1 = w4, W.link_w1(cls, ())
                body += [index[end], W.link_w1(cls, ()), d << 14, ident | (0x2000 if last else 0), w4,
                         W.encode(cost, W.SCALE_W5), W.encode(ln, W.SCALE_W6)]
                fsub = l2_key(net.node[first][0])[1]
                triples += [index[end], selector(fsub), net.node[first][2]]
            if hop:
                w, side = hop
                body += [index[w], 0, 0, 0, 0x8000 | W.SIDES[side][0] << 13 | ((inner_w4 or 0) & 0x1FFF), 0, 0]
                triples += [index[w], selector(l2_key(net.node[w][0])[1]), net.node[w][2]]
                st["boundary"] += 1
            g = W.group(cmin)
            pairs[g][0] += 1
            pairs[g][1] += n
            nlinks += n
            u1.append((selector(sub), i1, [n << 12] + triples))
        unit0 = [len(vs) >> 16, len(vs) & 0xFFFF, nlinks >> 16, nlinks & 0xFFFF]
        unit0 += [x for p in pairs for x in p] + body
        head0 = [key[0], key[1], 0, 0, 0, 0, 0, 27, len(unit0) >> 16, len(unit0) & 0xFFFF]
        head0 += [0xFFFF, 0xFFFF, 0, 0] * 4 + [country]
        unit1 = [len(vs), 0x2100] + [x for _s, _i, e in sorted(u1, key=lambda t: (t[0], t[1])) for x in e]
        unit1 += [key[0], key[1]]
        head1 = [key[0], key[1], 0, 0, 0, 0, 0xFFFF, 0xFFFF, 0, 0, 0, 27, len(unit1) >> 16, len(unit1) & 0xFFFF]
        head1 += [0xFFFF, 0xFFFF, 0, 0] * 3 + [country]
        recs = []
        for words in (head0 + unit0, head1 + unit1):
            if len(words) > 0x10000:
                raise W.GraphError("level-2 record of %d words" % len(words))
            plain = struct.pack(">%dH" % len(words), *words)
            comp = zlib.compress(plain, 6)
            if len(comp) % 2:
                comp += b"\0"
            recs += [plain, comp]
        out[key] = tuple(recs)
        st["records"] += 2
        st["nodes"] += len(vs)
        st["links"] += nlinks
    flagged_xy = {(net.node[v][0], net.node[v][1]) for v in flagged}
    return flagged_xy, out, dict(st)


def place_level2(m: dict, built: dict, l1_dirs: dict) -> dict:
    """Put ``{level-2 key: (u0 plain, u0 comp, u1 plain, u1 comp)}`` into the section-2
    level-2 directories.  ``l1_dirs`` maps a level-2 key to its level-1 parcel
    ``(y0, x0, row, col)`` (any of the 16)."""
    import tilewriter
    dirs = {}
    for sec in m["sections"]:
        if sec["id"] != 2:
            continue
        for L in sec["levels"]:
            if L["level"] != 2:
                continue
            for dm in L["dirs"]:
                D = dm["D"]
                dirs[(D["y"], tilewriter.dir_x0(D))] = dm
    rows = collections.defaultdict(dict)
    for key, rec in built.items():
        y0, x0, row, col = l1_dirs[key]
        Y, X = y0 * 32 + row, x0 * 32 + col
        y2, x2 = (y0 // 4) * 4, (x0 // 4) * 4
        r2, c2 = Y // 4 - y2 * 8, X // 4 - x2 * 8
        if (y2, x2) not in dirs:
            raise W.GraphError("no section-2 level-2 directory for %r" % ((y2, x2),))
        rows[(y2, x2, r2)][c2] = rec
    st = collections.Counter()
    for (y2, x2, r2), cols in rows.items():
        dm = dirs[(y2, x2)]
        D = dm["D"]
        words = [0xFFFFFFFF] * (D["body"] // 4)
        recs = []
        for c2 in sorted(cols):
            p0, c0, p1, c1 = cols[c2]
            for k, plain, comp in ((2 * c2, p0, c0), (2 * c2 + 1, p1, c1)):
                words[2 * k] = len(comp) // 2
                words[2 * k + 1] = len(plain) // 2
                recs.append(dict(k=k, raw=comp, words=len(plain) // 2, flag=0))
                st["level-2 records"] += 1
        body = struct.pack(">%dI" % len(words), *words)
        D["slots"][r2] = dict(tag=0, body=body, recs=recs, block_off=-1)
        D.get("empty_tags", {}).pop(r2, None)
        D.get("empty_bodies", {}).pop(r2, None)
        dm["units"][r2].update(live=True, old=("sec2-l2", y2, x2, r2), tag=0,
                               block=b"".join(r["raw"] for r in recs), recs=[r["raw"] for r in recs])
        st["level-2 rows"] += 1
    return dict(st)


def selftest() -> int:
    import copy
    from sec2_fields import check_level2, graph as unit_graph
    # one level-1 mesh: a primary road A-B-C (B a plain bend), a side road at C to D
    code = (0xA40C, 0xCC0C)
    links = [dict(cls=5, lid=1, pts=[(100, 100), (500, 100)], oneway=0),
             dict(cls=5, lid=2, pts=[(500, 100), (900, 100)], oneway=0),
             dict(cls=5, lid=3, pts=[(900, 100), (900, 700)], oneway=0),
             dict(cls=5, lid=4, pts=[(900, 100), (1300, 100)], oneway=0),
             dict(cls=8, lid=1, pts=[(500, 100), (500, 400)], oneway=0)]
    for L in links:
        L["length"] = W.metres(L["pts"], (1.0, 1.0))
    order, ent = W.parcel_graph(links)
    prepared = {"P": (code, order, ent)}
    flagged, out, st = build_level2(prepared, {"P": {}}, 826)
    # B is not a level-2 node (one class-8 side link only); A, C, the two ends are
    assert {xy for _c, xy in flagged} == {(100, 100), (900, 100), (900, 700), (1300, 100)}, flagged
    key = (0xA40F, 0xCC02)
    p0, _c0, p1, _c1 = out[key]
    w0 = list(struct.unpack(">%dH" % (len(p0) // 2), p0))
    w1 = list(struct.unpack(">%dH" % (len(p1) // 2), p1))
    u0, u1 = w0[27:], w1[27:]
    xy, lk = unit_graph(u0)
    assert len(xy) == 4 and (25, 25) in xy, xy
    ab = [l for l in lk[xy.index((25, 25))]][0]
    assert W.decode(ab[6], W.SCALE_W6) == 800, ab
    l1 = {code: ([p for p in order],
                 [[order.index(e[0]) for e in ent[p]] for p in order])}
    c = collections.Counter()
    check_level2(key, u0, u1, l1, c)
    assert c["L2 unit 1: parses exactly, 2-word trailer"] == 1, c
    assert c["L2 unit 1: one entry per level-2 node"] == 1, c
    assert c["L2 entry: level-1 node on the level-2 node (1/4 scale, +-1)"] == 4, c
    assert c["L2 link triple: node == link target (w0 & 0x3fff)"] == 6, c
    assert c["L2 link triple: level-1 node is a level-1 neighbour of the entry's"] == 6, c
    print("sec2_level2 selftest OK: level-2 nodes, chain sums, unit 1 triples")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    print(__doc__)
    sys.exit(2)
