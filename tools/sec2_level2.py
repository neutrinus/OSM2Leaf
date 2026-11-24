#!/usr/bin/env python3
"""sec2_level2.py — the upper section-2 route levels 2, 4 and 5 of a generated map (M5.103).

The route search runs long routes top-down (``LEV4Top``/``LEV5Top``, then
``LEV2DSIDE``, ``LEV1DSIDE``; C-10057, C-10075).  Each upper level is the
graph of the main roads of the level below, on meshes that group S x S meshes
of the level below.  Level 2 sits in the grid tile; levels 4 and 5 sit in
``MAPAL001/LEV3456R.DAT``.  Rules measured on the factory London tile
(``B48R068R``) and ``LEV3456R`` (M4.98 C-9938, EXP-2026-11-23-M5.103):

* level 2 groups 4 x 4 level-1 meshes, level 4 groups 16 x 16 level-2
  meshes, level 5 groups 4 x 4 level-4 meshes; mesh keys:
  level 2 ``(w0 & 0xfff0 | 0xf, w1 & 0xfff0 | 0x2)`` of a level-1 code,
  level 4 ``(w0 & 0xff00 | 0x0f, w1 & 0xff00 | 0x04)``,
  level 5 ``(w0 & 0xfc00 | 0x0f, w1 & 0xfc00 | 0x05)``;
* coordinates: ``(col * 2048 + x) // S`` over the grouped meshes (level 4:
  8,837 / 8,841 factory entries within +-1, level 5: 14,198 / 14,225);
* unit 1 selector ``row << (16 - b) | col << (8 - b)`` with ``b`` = bits per
  row/col (2 for S = 4, 4 for S = 16);
* level classes: level 2 = 1-7, 10, 11 (C-10074); level 4 and 5 hold classes
  1-6 and 10 in the factory, with only part of classes 4-6 (largest factory
  level-4 mesh: 3,442 nodes), so the class alone does not choose them; here a
  link's rank comes from its OSM highway (``rank``: motorway and trunk reach
  level 5, their slip roads level 4, other level-2 classes level 2;
  provisional), from the class when there is no highway;
* a node of level k is an upper node exactly when its node word 2 has
  ``0x2000``; a link of level k carries ``w1`` bit ``0x2`` when its class is
  on the level above; boundary entries never;
* an upper node is set at junctions of upper-class roads, dead ends, the
  outer edge of the upper mesh and where class, type or one-way sense change;
  an upper link is the chain of lower links between two upper nodes, with the
  summed cost ``w5`` and length ``w6`` (87,774 / 87,774 within 2 % at level 2);
* records come in pairs with the mesh key: unit 0 (the graph, level-1
  format) and unit 1 (``[node count, 0x2100, entries, key]``; entry =
  ``links << 12``, a self triple ``(node, selector, lower node)`` and one
  triple per link ``(target, selector, first lower step)``; a boundary link's
  triple names the neighbour mesh's selector and lower node);
* only boundary nodes may lie on a mesh edge (x or y 0 or 0x7ff, C-10064).

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
L4_CLASSES = frozenset({1, 2, 3, 4, 6, 10, 11})
L5_CLASSES = frozenset({1, 2, 3, 4, 6, 10})


class Spec:
    """Geometry of one upper level over the level below."""

    def __init__(self, level, size, key):
        self.level, self.size, self._key = level, size, key
        self.bits = size.bit_length() - 1

    def key(self, code):
        """Upper mesh key of a lower mesh code and the lower mesh's (row, col) in it."""
        return self._key(code)

    def xy(self, sub, xy):
        row, col = sub
        return (col * 2048 + xy[0]) // self.size, (row * 2048 + xy[1]) // self.size

    def selector(self, sub):
        return sub[0] << (16 - self.bits) | sub[1] << (8 - self.bits)


SPEC2 = Spec(2, 4, lambda c: (((c[0] & 0xFFF0) | 0xF, (c[1] & 0xFFF0) | 0x2),
                                          (c[0] & 3, c[1] & 3)))
SPEC4 = Spec(4, 16, lambda c: (((c[0] & 0xFF00) | 0x0F, (c[1] & 0xFF00) | 0x04),
                                           ((c[0] >> 4) & 0xF, (c[1] >> 4) & 0xF)))
SPEC5 = Spec(5, 4, lambda c: (((c[0] & 0xFC00) | 0x0F, (c[1] & 0xFC00) | 0x05),
                                          ((c[0] >> 8) & 3, (c[1] >> 8) & 3)))
SPECS = (SPEC2, SPEC4, SPEC5)
# LEV3456R slot directories: slot row = (key w0 >> shift) - row0, column = (key w1 >> shift) - col0
# (factory records of LEV3456R, C-10066)
LEV_PLACE = {4: (8, 0x90, 0xC4), 5: (10, 0x24, 0x31)}


def l2_key(code):
    return SPEC2.key(code)


def selector(sub):
    return SPEC2.selector(sub)


class Net:
    """A route graph of one level: nodes ``(mesh code, xy, index in mesh, parcel)``,
    entries ``(far node, link dict, at last point, direction)`` and boundary hops."""

    def __init__(self):
        self.node, self.ent, self.hop = [], [], {}

    @classmethod
    def from_prepared(cls, prepared, bounds):
        net = cls()
        ids = {}
        for parcel, (code, order, _ent) in prepared.items():
            for i, xy in enumerate(order):
                ids[(tuple(code), xy)] = len(net.node)
                net.node.append((tuple(code), xy, i, parcel))
        net.ent = [None] * len(net.node)
        for parcel, (code, order, ent) in prepared.items():
            c = tuple(code)
            for xy in order:
                v = ids[(c, xy)]
                for _far, L, _last, _d in ent[xy]:
                    L.setdefault("uid", (c, L["cls"], L["lid"]))
                net.ent[v] = [(ids[(c, far)], L, last, d) for far, L, last, d in ent[xy]]
                b = bounds[parcel].get(xy)
                if b is not None:
                    side, _j, nb = b
                    w = ids.get((nb, W.mirror(side, *xy)))
                    if w is not None:
                        net.hop[v] = (w, side)
        net.ids = ids
        return net

    def entries(self, v, level):
        """Entries of ``v`` whose link reaches ``level``."""
        return [e for e in self.ent[v] if rank(e[1]) >= level]


# primary on level 4 would give 7,168 nodes in one London level-4 mesh (factory maximum
# 3,442) and a record above the 0x10000-word limit
HIGHWAY_RANK = {"motorway": 5, "trunk": 5, "motorway_link": 4, "trunk_link": 4}
# Tertiary roads are class 8 in our table, but the factory level 2 carries the
# minor through roads (class 7): without them the destination-side level-1
# search (200 settled nodes) can end before it meets a level-2 node and the
# route fails with "MST CAND SELECT ERROR" (M5.103).
MINOR_L2 = {"tertiary", "tertiary_link"}


def rank(L) -> int:
    """Highest route level a link reaches (1, 2, 4 or 5)."""
    r = L.get("rank")
    if r is not None:
        return r
    cls = L["cls"]
    hw = L.get("highway")
    if cls == 8 and hw in MINOR_L2:
        return 2
    if cls not in L2_CLASSES:
        return 1
    if hw is not None:
        return HIGHWAY_RANK.get(hw, 2)
    return 5 if cls in L5_CLASSES else 4 if cls in L4_CLASSES else 2


def on_level2(L) -> bool:
    """Link word 1 bit 0x2 rule for level 1 (``sec2_writer.link_w1``)."""
    return rank(L) >= 2


def link_cost(L):
    return L["cost"] if "cost" in L else L["length"] * W.COST_PER_M.get(L["cls"], 0.72)


def mark(net: Net, spec: Spec = SPEC2) -> set:
    """Lower node ids that become upper nodes."""
    out = set()
    for v in range(len(net.node)):
        es = net.entries(v, spec.level)
        if not es:
            continue
        code = net.node[v][0]
        if v in net.hop:
            w = net.hop[v][0]
            if spec.key(net.node[w][0])[0] != spec.key(code)[0]:
                out.add(v)          # outer edge of the upper mesh
            continue                 # inner lower edge: the chain goes on
        if len(es) != 2:
            out.add(v)
            continue
        (_, a, _, da), (_, b, _, db) = es
        if (a["cls"], a.get("typ", a["cls"]), rank(a)) != (b["cls"], b.get("typ", b["cls"]), rank(b)):
            out.add(v)
        elif (da, db) not in ((0, 0), (1, 2), (2, 1)):
            out.add(v)
    return out


def link_uid(L):
    """Identity of a link shared by its two end entries."""
    return L.get("uid", id(L))


def walk(net: Net, flagged: set, v: int, e, level=2):
    """Follow entry ``e`` from upper node ``v`` to the next upper node, link by
    link (parallel links between the same two nodes are separate chains, as in
    the firmware's partner-link walk).

    Returns ``(end node, uid of the link into it, length m, cost, direction at v,
    first step)`` or ``None`` when the chain loops back without an upper node or
    forks."""
    far, L, _last, d0 = e
    first = far
    length = L["length"]
    cost = link_cost(L)
    oneway = d0 != 0
    via, cur = link_uid(L), far
    seen = {v}
    while cur not in flagged:
        if cur in seen:
            return None
        seen.add(cur)
        es = net.entries(cur, level)
        if cur in net.hop and len(es) == 1 and link_uid(es[0][1]) == via:
            cur, via = net.hop[cur][0], None
            if cur in flagged:
                return None          # a chain must not end across a mesh edge
            continue
        nxt = [x for x in es if link_uid(x[1]) != via]
        if len(nxt) != 1:
            return None
        x = nxt[0]
        length += x[1]["length"]
        cost += link_cost(x[1])
        oneway = oneway and x[3] != 0
        via, cur = link_uid(x[1]), x[0]
    return cur, via, length, cost, (d0 if oneway else 0), first


class Upper:
    """One built upper level: its graph (a ``Net`` over the upper nodes) plus what
    the records need about the level below."""

    def __init__(self, spec, lower, flagged, net, meshes, lower_node):
        self.spec, self.lower, self.flagged = spec, lower, flagged
        self.net, self.meshes, self.lower_node = net, meshes, lower_node


PREV_LEVEL = {2: 1, 4: 2, 5: 4}


def prune_dead_ends(net: Net, level: int, st: collections.Counter) -> None:
    """Drop the dead-end spurs from ``level``: the factory upper levels have no
    node of degree 1 (London level 2: 0 of 34,037) while trimmed OSM main roads
    end anywhere.  A spur link keeps its level-below rank on both ends, so the
    link word 1 bit 0x2 of the level below follows (``on_level2`` / ``records``)."""
    def deg(v):
        n = len(net.entries(v, level))
        if v in net.hop and net.entries(net.hop[v][0], level):
            n += 1
        return n
    todo = [v for v in range(len(net.node)) if deg(v) == 1]
    while todo:
        v = todo.pop()
        es = net.entries(v, level)
        if deg(v) != 1 or len(es) != 1:
            continue
        far, L, _last, _d = es[0]
        # level 1: both ends hold the same dict; upper levels: one dict per end,
        # same uid (level-1 uids repeat over the links of one OSM way)
        uid = L.get("uid")
        if not (isinstance(uid, tuple) and uid and isinstance(uid[0], int)):
            uid = None
        for x in (v, far):
            for e in net.ent[x]:
                if e[1] is L or (uid is not None and e[1].get("uid") == uid):
                    e[1]["rank"] = PREV_LEVEL[level]
        st["level-%d dead-end links dropped" % level] += 1
        todo.append(far)


def build_upper(lower: Net, spec: Spec, st: collections.Counter, prune: bool = True) -> Upper:
    if prune:
        prune_dead_ends(lower, spec.level, st)
    flagged = mark(lower, spec)
    links = {}
    # chains that loop without an upper node, or back to their start: give each one a node
    for _round in range(10):
        todo = []
        for v in sorted(flagged):
            for j, e in enumerate(lower.entries(v, spec.level)):
                r = walk(lower, flagged, v, e, spec.level)
                if r is None:
                    if e[0] not in lower.hop:
                        todo.append(e[0])
                elif r[0] == v and e[0] not in flagged and e[0] not in lower.hop:
                    todo.append(e[0])   # a loop back to v: the factory has no upper self-loops
                else:
                    links[(v, j)] = r
        # parallel upper links between the same two nodes (the factory has none):
        # an upper node on every chain but the first
        par = collections.defaultdict(list)
        for (v, j), r in sorted(links.items()):
            if r[0] != v:
                par[(v, r[0])].append(r[5])
        for (v, end), firsts in par.items():
            firsts.sort(key=lambda f: f != end)     # keep a direct link, split the others
            for f in firsts[1:]:
                if f not in flagged and f not in lower.hop and f != end:
                    todo.append(f)
        if not todo or _round == 9:
            st["level-%d unsplit chains" % spec.level] += len(todo)
            break
        flagged.update(todo)
        links.clear()

    def outer_hop(v):
        if v not in lower.hop or lower.hop[v][0] not in flagged:
            return False        # no partner on this level (e.g. its side was a pruned spur)
        return spec.key(lower.node[lower.hop[v][0]][0])[0] != spec.key(lower.node[v][0])[0]

    mesh_nodes = collections.defaultdict(list)
    for v in flagged:
        mesh_nodes[spec.key(lower.node[v][0])[0]].append(v)
    up_id, lower_node, net = {}, {}, Net()
    for key in sorted(mesh_nodes):
        vs = mesh_nodes[key]

        def sortkey(v):
            code, xy, _i, _p = lower.node[v]
            cmin = min(e[1]["cls"] for e in lower.entries(v, spec.level))
            p = spec.xy(spec.key(code)[1], xy)
            return (W.group(cmin), p[1], p[0], v)
        vs.sort(key=sortkey)
        for i, v in enumerate(vs):
            code, xy, _i, _p = lower.node[v]
            x2, y2 = spec.xy(spec.key(code)[1], xy)
            if not outer_hop(v):
                x2, y2 = min(max(x2, 1), 0x7FE), min(max(y2, 1), 0x7FE)
            up_id[v] = len(net.node)
            lower_node[len(net.node)] = v
            net.node.append((key, (x2, y2), i, key))
    net.ent = [[] for _ in net.node]
    # link ids: one per chain, shared by its two ends; an end is (node, uid of its first link)
    canon, next_id = {}, collections.Counter()
    for (v, j), (end, via, ln, cost, d, first) in sorted(links.items()):
        e = lower.entries(v, spec.level)[j]
        a, b = (v, link_uid(e[1])), (end, via)
        k = min(a, b)
        cls, typ, rk = e[1]["cls"], e[1].get("typ", e[1]["cls"]), rank(e[1])
        if k not in canon:
            key = spec.key(lower.node[v][0])[0]
            next_id[(key, cls)] += 1
            canon[k] = next_id[(key, cls)]
        L = dict(cls=cls, typ=typ, rank=rk, length=ln, cost=cost, lid=canon[k], first=first,
                 uid=(spec.level,) + k)
        net.ent[up_id[v]].append((up_id[end], L, a != k, d))
    for v, u in up_id.items():
        if outer_hop(v):
            w, side = lower.hop[v]
            net.hop[u] = (up_id[w], side)
            st["level-%d boundary" % spec.level] += 1
    st["level-%d nodes" % spec.level] += len(net.node)
    st["level-%d links" % spec.level] += sum(len(e) for e in net.ent) + len(net.hop)
    return Upper(spec, lower, flagged, net, {k: [up_id[v] for v in vs] for k, vs in mesh_nodes.items()},
                 lower_node)


def records(up: Upper, upper_flags=frozenset(), up_level=None, country=826):
    """``{mesh key: (u0 plain, u0 comp, u1 plain, u1 comp)}`` of a built level.
    ``upper_flags``: node ids of ``up.net`` that are nodes of the level above
    (node word 2 = 0x2000); ``up_level``: the level above (link w1 bit 0x2 on links
    that reach it)."""
    spec, net, lower = up.spec, up.net, up.lower
    out = {}
    for key in sorted(up.meshes):
        us = up.meshes[key]
        body, pairs, nlinks, u1 = [], [[0, 0] for _ in range(11)], 0, []
        for u in us:
            v = up.lower_node[u]
            code, xy, i1, _p = lower.node[v]
            sub = spec.key(code)[1]
            es = net.ent[u]
            hop = net.hop.get(u)
            n = len(es) + (1 if hop else 0)
            if n > 15:
                raise W.GraphError("level-%d node with %d links" % (spec.level, n))
            cmin = min(e[1]["cls"] for e in lower.entries(v, spec.level))
            x2, y2 = net.node[u][1]
            body += [x2 | n << 12, y2 | cmin << 12, 0x2000 if u in upper_flags else 0]
            triples = [net.node[u][2], spec.selector(sub), i1]
            inner_w4 = None
            for end, L, last, d in es:
                w4 = L["cls"] | L["typ"] << 8 | (0x10 if d == 0 else 0)
                if inner_w4 is None:
                    inner_w4 = w4
                body += [net.node[end][2], (W.W1.get(L["cls"], 0) & ~0xE) | (0x2 if up_level and rank(L) >= up_level else 0),
                         d << 14,
                         L["lid"] | (0x2000 if last else 0), w4,
                         W.encode(L["cost"], W.SCALE_W5), W.encode(L["length"], W.SCALE_W6)]
                first = L["first"]
                triples += [net.node[end][2], spec.selector(spec.key(lower.node[first][0])[1]),
                            lower.node[first][2]]
            if hop:
                w, side = hop
                body += [net.node[w][2], 0, 0, 0, 0x8000 | W.SIDES[side][0] << 13 | ((inner_w4 or 0) & 0x1FFF),
                         0, 0]
                wl = up.lower_node[w]
                triples += [net.node[w][2], spec.selector(spec.key(lower.node[wl][0])[1]), lower.node[wl][2]]
            g = W.group(cmin)
            pairs[g][0] += 1
            pairs[g][1] += n
            nlinks += n
            u1.append((spec.selector(sub), i1, [n << 12] + triples))
        unit0 = [len(us) >> 16, len(us) & 0xFFFF, nlinks >> 16, nlinks & 0xFFFF]
        unit0 += [x for p in pairs for x in p] + body
        head0 = [key[0], key[1], 0, 0, 0, 0, 0, 27, len(unit0) >> 16, len(unit0) & 0xFFFF]
        head0 += [0xFFFF, 0xFFFF, 0, 0] * 4 + [country]
        unit1 = [len(us), 0x2100] + [x for _s, _i, e in sorted(u1, key=lambda t: (t[0], t[1])) for x in e]
        unit1 += [key[0], key[1]]
        head1 = [key[0], key[1], 0, 0, 0, 0, 0xFFFF, 0xFFFF, 0, 0, 0, 27, len(unit1) >> 16, len(unit1) & 0xFFFF]
        head1 += [0xFFFF, 0xFFFF, 0, 0] * 3 + [country]
        recs = []
        for words in (head0 + unit0, head1 + unit1):
            if len(words) > 0x10000:
                raise W.GraphError("level-%d record of %d words" % (spec.level, len(words)))
            plain = struct.pack(">%dH" % len(words), *words)
            comp = zlib.compress(plain, 6)
            if len(comp) % 2:
                comp += b"\0"
            recs += [plain, comp]
        out[key] = tuple(recs)
    return out


def build_levels(prepared: dict, bounds: dict, country: int, top: int = 5, prune: bool = True):
    """Levels 2 (and 4, 5 up to ``top``) of a level-1 graph.

    Returns ``(level-1 (code, xy) nodes that are level-2 nodes, {level: {key: records}},
    stats)``."""
    st = collections.Counter()
    l1 = Net.from_prepared(prepared, bounds)
    ups, lower = [], l1
    for spec in SPECS:
        if spec.level > top:
            break
        up = build_upper(lower, spec, st, prune)
        ups.append(up)
        lower = up.net
    out = {}
    for i, up in enumerate(ups):
        nxt = ups[i + 1] if i + 1 < len(ups) else None
        flags = nxt.flagged if nxt else frozenset()   # ids of up.net
        out[up.spec.level] = records(up, flags, nxt.spec.level if nxt else None, country)
        st["level-%d records" % up.spec.level] += 2 * len(out[up.spec.level])
    flagged_xy = {(l1.node[v][0], l1.node[v][1]) for v in ups[0].flagged} if ups else set()
    return flagged_xy, out, dict(st)


def place_lev(m: dict, built: dict) -> dict:
    """Replace every section-2 level-4 and level-5 record of a ``LEV3456R``
    ``tile_relayout`` model with ``{level: {key: (u0 plain, u0 comp, u1 plain,
    u1 comp)}}`` (factory upper records name factory level-2 node indices, so
    none may stay, C-10065)."""
    import clarion_tile
    st = collections.Counter()
    for sec in m["sections"]:
        if sec["id"] != 2:
            continue
        for L in sec["levels"]:
            lv = L["level"]
            if lv not in LEV_PLACE:
                continue
            for dm in L["dirs"]:
                D = dm["D"]
                n = D.get("nslots", clarion_tile.SLOTS)
                D["slots"] = {}
                D["empty_tags"] = {i: 0xFFFFFFFF for i in range(n)}
                D["empty_bodies"] = {i: b"\xff" * D["body"] for i in range(n)}
                D.pop("tail", None)
                for u in dm["units"]:
                    u.update(tag=0xFFFFFFFF, live=False, old=None, block=b"", recs=[])
            if not built.get(lv):
                continue
            if len(L["dirs"]) != 1:
                raise W.GraphError("LEV3456R level %d has %d directories" % (lv, len(L["dirs"])))
            dm = L["dirs"][0]
            D = dm["D"]
            shift, row0, col0 = LEV_PLACE[lv]
            rows = collections.defaultdict(dict)
            for key, rec in built[lv].items():
                r, c = (key[0] >> shift) - row0, (key[1] >> shift) - col0
                if not (0 <= r < D["nslots"] and 0 <= 2 * c + 1 < D["body"] // 8):
                    raise W.GraphError("level-%d mesh %04x %04x outside LEV3456R" % (lv, key[0], key[1]))
                rows[r][c] = rec
            for r, cols in rows.items():
                words = [0xFFFFFFFF] * (D["body"] // 4)
                recs = []
                for c in sorted(cols):
                    p0, c0, p1, c1 = cols[c]
                    for k, plain, comp in ((2 * c, p0, c0), (2 * c + 1, p1, c1)):
                        words[2 * k] = len(comp) // 2
                        words[2 * k + 1] = len(plain) // 2
                        recs.append(dict(k=k, raw=comp, words=len(plain) // 2, flag=0))
                        st["level-%d records" % lv] += 1
                D["slots"][r] = dict(tag=0, body=struct.pack(">%dI" % len(words), *words), recs=recs,
                                     block_off=-1)
                D["empty_tags"].pop(r, None)
                D["empty_bodies"].pop(r, None)
                dm["units"][r].update(live=True, old=("sec2-l%d" % lv, r), tag=0,
                                      block=b"".join(x["raw"] for x in recs), recs=[x["raw"] for x in recs])
    return dict(st)


def build_level2(prepared: dict, bounds: dict, country: int, prune: bool = True):
    """Level 2 only: ``(flagged level-1 (code, xy), {key: records}, stats)``."""
    flagged, out, st = build_levels(prepared, bounds, country, top=2, prune=prune)
    return flagged, out.get(2, {}), st


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
    flagged, out, st = build_level2(prepared, {"P": {}}, 826, prune=False)
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
    # levels 4 and 5: a motorway A-B-C with a primary spur at B
    mw = [dict(cls=1, lid=1, pts=[(100, 100), (900, 100)], oneway=0),
          dict(cls=1, lid=2, pts=[(900, 100), (1700, 100)], oneway=0),
          dict(cls=5, lid=1, pts=[(900, 100), (900, 900)], oneway=0)]
    for L in mw:
        L["length"] = W.metres(L["pts"], (1.0, 1.0))
    order, ent = W.parcel_graph(mw)
    fl, lv, st = build_levels({"P": (code, order, ent)}, {"P": {}}, 826, prune=False)
    assert sorted(lv) == [2, 4, 5], sorted(lv)
    k4 = SPEC4.key(key)[0]
    assert k4 == (0xA40F, 0xCC04) and k4 in lv[4], lv[4].keys()
    w2 = list(struct.unpack(">%dH" % (len(lv[2][key][0]) // 2), lv[2][key][0]))
    xy2, lk2 = unit_graph(w2[27:])
    nodew = []
    p = 27 + 26
    for links in lk2:
        nodew.append(w2[p + 2])
        p += 3 + 7 * len(links)
    # level-2 nodes A, B, C, D: only the motorway ends A and C are level-4 nodes
    # (class 5 is not on level 4, so the motorway runs through B)
    assert sum(1 for x in nodew if x == 0x2000) == 2, (xy2, nodew)
    w4 = list(struct.unpack(">%dH" % (len(lv[4][k4][0]) // 2), lv[4][k4][0]))
    xy4, lk4 = unit_graph(w4[27:])
    assert len(xy4) == 2 and len(lk4[0]) == 1, (xy4, lk4)
    assert W.decode(lk4[0][0][6], W.SCALE_W6) == 1600, lk4
    # a square of primary roads with a spur (dropped) and a double link (split)
    sq = [dict(cls=5, lid=1, pts=[(100, 100), (900, 100)], oneway=0),
          dict(cls=5, lid=2, pts=[(900, 100), (900, 900)], oneway=0),
          dict(cls=5, lid=3, pts=[(900, 900), (100, 900)], oneway=0),
          dict(cls=5, lid=4, pts=[(100, 900), (100, 100)], oneway=0),
          dict(cls=5, lid=5, pts=[(100, 100), (500, 500), (900, 900)], oneway=0),
          dict(cls=5, lid=6, pts=[(900, 900), (1500, 1500)], oneway=0)]
    for L in sq:
        L["length"] = W.metres(L["pts"], (1.0, 1.0))
    order, ent = W.parcel_graph(sq)
    fl, out, st = build_level2({"P": (code, order, ent)}, {"P": {}}, 826)
    assert st.get("level-2 dead-end links dropped") == 1, st
    assert all(rank(L) == (1 if L["lid"] == 6 else 2) for L in sq), [rank(L) for L in sq]
    assert (1500, 1500) not in {xy for _c, xy in fl}, fl
    w2 = list(struct.unpack(">%dH" % (len(out[key][0]) // 2), out[key][0]))
    xy2, lk2 = unit_graph(w2[27:])
    pairs = collections.Counter((i, l[0] & 0x3FFF) for i, ls in enumerate(lk2) for l in ls)
    assert pairs and max(pairs.values()) == 1, pairs
    print("sec2_level2 selftest OK: level-2 nodes, chain sums, unit 1 triples, levels 4 and 5, "
          "dead ends, parallel links")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    print(__doc__)
    sys.exit(2)
