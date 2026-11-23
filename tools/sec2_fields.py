#!/usr/bin/env python3
"""Check the section-2 field meanings read off Navi.exe (M4.98) on a factory tile.

Each check states a rule taken from decompiled firmware (EU2011 build A, see
EXP-2026-11-23-M4.98-sec2-fields-ghidra) and counts how many links or records
of a tile obey it.  Reads only the tile; prints counts, never vendor bytes.

    python3 tools/sec2_fields.py TILE.DAT [--sample N]
    python3 tools/sec2_fields.py TILE.DAT --level2
    python3 tools/sec2_fields.py TILE.DAT --s1-direction [--limit N]
    python3 tools/sec2_fields.py TILE.DAT --census
    python3 tools/sec2_fields.py FACTORY.DAT --sense OTHER.DAT [--limit N]
    python3 tools/sec2_fields.py --selftest

``--level2`` checks the level-2 unit-1 layout (the level-2 to level-1 node map
read by ``0x0036d530``) against the level-2 graph and the level-1 records.
``--s1-direction`` pairs each section-2 entry with its drawn section-1 link
(key ``(parcel, class, id)``, C-5150) and counts (section-1 point y bits
15-14, section-2 ``w2 >> 14``, entry at the drawn last point): the factory
has 1 = one-way along the drawn points, 2 = against, 3 = closed (M5.57).
"""
from __future__ import annotations

import argparse
import collections
import os
import random
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def link_words(w1: int, w2: int, w3: int) -> int:
    """Extra halfwords after the 7 fixed link words (firmware size rule)."""
    return ((w2 & 0x3FC0) >> 6) + (w1 & 1) + (w2 & 0x3F) + (w3 >> 14)


def walk(u: list[int]):
    """Yield (node_index, node_words, link_words, extra_words) for unit 0."""
    nn = (u[0] << 16) | u[1]
    p = 26
    for k in range(nn):
        node = u[p:p + 3]
        p += 3
        for _ in range(node[0] >> 12):
            lw = u[p:p + 7]
            n = link_words(lw[1], lw[2], lw[3])
            yield k, node, lw, u[p + 7:p + 7 + n]
            p += 7 + n


def check_record(w: list[int], st: collections.Counter) -> None:
    o, n = (w[6] << 16) | w[7], (w[8] << 16) | w[9]
    if o == 0xFFFFFFFF:
        return
    u = w[o:o + n]
    nn, nl = (u[0] << 16) | u[1], (u[2] << 16) | u[3]
    pairs = [(u[4 + 2 * i], u[5 + 2 * i]) for i in range(11)]
    st["records"] += 1
    st["header: sum of 11 pair firsts == node count"] += sum(a for a, _ in pairs) == nn
    st["header: sum of 11 pair seconds == link count"] += sum(b for _, b in pairs) == nl
    ends = collections.defaultdict(list)
    for k, node, lw, extra in walk(u):
        st["links"] += 1
        edge = (node[0] & 0x7FF) in (0, 0x7FF) or (node[1] & 0x7FF) in (0, 0x7FF)
        if lw[4] & 0x8000:
            st["boundary link (w4 & 0x8000)"] += 1
            st["boundary link at a mesh-edge node"] += edge
        else:
            ends[(lw[4] & 0xF, lw[3] & 0x1FFF)].append(lw)
        for x in extra[:(lw[2] & 0x3FC0) >> 6]:
            st["turn word"] += 1
            st["turn word, target nibble 0xf (condition record)"] += (x >> 12) == 0xF
            st["turn word, low byte 0xff (always banned)"] += (x & 0xFF) == 0xFF
            st["turn word, low byte 0 (allowed)"] += (x & 0xFF) == 0
    for lst in ends.values():
        if len(lst) != 2:
            continue
        a, b = (x[2] >> 14 for x in lst)
        st["inner link seen from both ends"] += 1
        key = {(0, 0): "two-way (0/0)", (3, 3): "closed (3/3)"}.get((a, b))
        if key is None and {a, b} == {1, 2}:
            key = "one-way (1/2)"
        st["direction " + (key or "other %d/%d" % (a, b))] += 1


def graph(u: list[int]):
    """Return ([(x, y)], [[link words]]) per node of a unit 0 (all nodes, linkless too)."""
    nn = (u[0] << 16) | u[1]
    p, xy, links = 26, [], []
    for _ in range(nn):
        node = u[p:p + 3]
        p += 3
        xy.append((node[0] & 0x7FF, node[1] & 0x7FF))
        t = []
        for _ in range(node[0] >> 12):
            lw = u[p:p + 7]
            p += 7 + link_words(lw[1], lw[2], lw[3])
            t.append(lw)
        links.append(t)
    return xy, links


def unit1_entries(u1: list[int]):
    """Split a level-2 unit 1 into entries: [count, word, entries..., mesh w0, mesh w1].

    Entry = header (neighbour count << 12), then a self triple and one triple per
    level-2 link of that node.  Triple = (level-2 node, level-1 record selector
    (row << 14 | col << 6), level-1 node index).  Width 3 = 2*K+1 with K = 1 in
    the factory data (0x0036d530 reads K from a descriptor).
    """
    p, out = 2, []
    while p < len(u1) - 2:
        n = u1[p] >> 12
        out.append((u1[p], [tuple(u1[p + 1 + 3 * t:p + 4 + 3 * t]) for t in range(n + 1)]))
        p += 1 + 3 * (n + 1)
    return out, p == len(u1) - 2


def l1_key(l2key: tuple[int, int], sel: int) -> tuple[int, int]:
    """Level-1 record key (header halfwords 0, 1) for a selector inside a level-2 mesh."""
    return (l2key[0] & 0xFFF0) + 12 + (sel >> 14), (l2key[1] & 0xFFF0) + 12 + ((sel >> 6) & 3)


def check_level2(key, u0, u1, l1, st: collections.Counter) -> None:
    xy, links = graph(u0)
    nn = len(xy)
    ents, exact = unit1_entries(u1)
    st["L2 unit-1 records"] += 1
    st["L2 unit 1: word 0 == unit-0 node count"] += u1[0] == nn
    st["L2 unit 1: parses exactly, 2-word trailer"] += exact
    st["L2 unit 1: trailer == record mesh key"] += tuple(u1[-2:]) == key
    st["L2 unit 1: one entry per level-2 node"] += sorted(e[1][0][0] for e in ents) == list(range(nn))
    for h, tr in ents:
        a, sel, b = tr[0]
        st["L2 entries"] += 1
        st["L2 entry: neighbour count == node link count"] += (h >> 12) == len(links[a])
        nodes = l1.get(l1_key(key, sel))
        if nodes and b < len(nodes[0]) and a < nn:
            x1, y1 = nodes[0][b]
            gx, gy = (((sel >> 6) & 3) * 2048 + x1) / 4, ((sel >> 14) * 2048 + y1) / 4
            st["L2 entry: level-1 node on the level-2 node (1/4 scale, +-1)"] += (
                abs(gx - xy[a][0]) <= 1 and abs(gy - xy[a][1]) <= 1)
        for j, (a2, s2, b2) in enumerate(tr[1:]):
            st["L2 link triples"] += 1
            st["L2 link triple: node == link target (w0 & 0x3fff)"] += (links[a][j][0] & 0x3FFF) == a2
            if s2 == sel and nodes and b < len(nodes[1]):
                st["L2 link triple in same level-1 record"] += 1
                st["L2 link triple: level-1 node is a level-1 neighbour of the entry's"] += b2 in nodes[1][b]


def run_level2(tile: str) -> collections.Counter:
    import tile_relayout
    m = tile_relayout.read_model(open(tile, "rb").read())
    st = collections.Counter()
    for sec in m["sections"]:
        if sec["id"] != 2:
            continue
        lv = {L["level"]: L for L in sec["levels"]}

        def records(L):
            for dm in L["dirs"]:
                for un in dm["units"]:
                    for raw in un["recs"]:
                        if raw:
                            pl = zlib.decompress(raw)
                            yield list(struct.unpack(">%dH" % (len(pl) // 2), pl[:len(pl) // 2 * 2]))

        def unit(w, i):
            o, n = (w[6 + 4 * i] << 16) | w[7 + 4 * i], (w[8 + 4 * i] << 16) | w[9 + 4 * i]
            return None if o == 0xFFFFFFFF else w[o:o + n]

        l1 = {}
        for w in records(lv[1]):
            u = unit(w, 0)
            if u:
                xy, links = graph(u)
                l1[(w[0], w[1])] = (xy, [[None if lw[4] & 0x8000 else lw[0] & 0x3FFF for lw in t] for t in links])
        u0s, u1s = {}, {}
        for w in records(lv[2]):
            st["L2 record kinds (unit 0, unit 1) %s" % ([unit(w, i) is not None for i in range(5)],)] += 1
            if unit(w, 0):
                u0s[(w[0], w[1])] = unit(w, 0)
            if unit(w, 1):
                u1s[(w[0], w[1])] = unit(w, 1)
        st["L2 unit-0 records with a unit-1 record of the same key"] += len(set(u0s) & set(u1s))
        for key, u1 in u1s.items():
            check_level2(key, u0s[key], u1, l1, st)
    return st


def run_s1_direction(tile: str, limit: int = 0) -> collections.Counter:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ze0-viewer", "tools_ze0"))
    import route_link_join as R
    T = R.Tile(tile)
    st = collections.Counter()
    codes = [c for c in T.sec2 if c in T.shape_rec]
    for code in codes[:limit or None]:
        try:
            sh, g = T.shapes(code), T.graph(code)
        except Exception:
            st["parcels unreadable"] += 1
            continue
        if not sh or not g:
            continue
        w, _unit, shapes = sh
        bits = {}
        for s in shapes:
            for off, (role, lid) in s["points"].items():
                if lid is not None and role in ("end", "vertex") and off + 1 < len(w):
                    bits.setdefault((s["cls"], lid & 0x1FFF), set()).add(w[off + 1] >> 14)
        for nd in g["nodes"]:
            for e in nd["entries"]:
                k = (e["cls"] & 0xF, e["id"] & 0x1FFF)
                if e["cls"] & 0x8000 or k not in bits:
                    continue
                st["s1 bits %s, s2 dir %d, at last point %s"
                   % ("/".join(map(str, sorted(bits[k]))), e["w5"] >> 14, bool(e["id"] & 0x2000))] += 1
    return st


def level1_records(tile: str):
    """Yield the plain halfwords of every section-2 level-1 record of a tile."""
    import tile_relayout
    m = tile_relayout.read_model(open(tile, "rb").read())
    for sec in m["sections"]:
        if sec["id"] != 2:
            continue
        for L in sec["levels"]:
            if L["level"] != 1:
                continue
            for dm in L["dirs"]:
                for un in dm["units"]:
                    for raw in un["recs"]:
                        if raw:
                            pl = zlib.decompress(raw)
                            yield list(struct.unpack(">%dH" % (len(pl) // 2), pl[:len(pl) // 2 * 2]))


def census_record(w: list[int], st: collections.Counter) -> None:
    """Count (direction, class, w4 type nibble) per inner link entry and one-way traps per node."""
    o, n = (w[6] << 16) | w[7], (w[8] << 16) | w[9]
    if o == 0xFFFFFFFF:
        return
    _xy, links = graph(w[o:o + n])
    for ls in links:
        inner = [lw for lw in ls if not lw[4] & 0x8000]
        dirs = [lw[2] >> 14 for lw in inner]
        if len(ls) == 1 and inner:
            st["node: dead end, direction %d" % dirs[0]] += 1
        if inner and len(inner) == len(ls):
            st["node: no way out (all 2/3)"] += all(d in (2, 3) for d in dirs)
            st["node: no way in (all 1/3)"] += all(d in (1, 3) for d in dirs)
        for lw in inner:
            st["dir %d class %2d type %2d" % (lw[2] >> 14, lw[4] & 0xF, (lw[4] >> 8) & 0xF)] += 1
            st["dir %d w4 & 0x10 %s" % (lw[2] >> 14, bool(lw[4] & 0x10))] += 1


def run_census(tile: str) -> collections.Counter:
    st = collections.Counter()
    for w in level1_records(tile):
        census_record(w, st)
    return st


def drawn_links(T, code):
    """[(first point, last point, one-way bits)] of the drawn links of one parcel (section 1)."""
    sh = T.shapes(code)
    if not sh:
        return []
    w, _unit, shapes = sh
    out = []
    for s in shapes:
        bits = collections.defaultdict(set)
        for off, (_role, lid) in s["points"].items():
            if lid is not None and off + 1 < len(w):
                bits[lid & 0x1FFF].add(w[off + 1] >> 14)
        for lid, (a, b) in zip(s["links"], s["ends"]):
            bb = bits.get(lid & 0x1FFF, set()) - {0}
            out.append((a, b, max(bb) if bb else 0))
    return out


def sense_pairs(fac, oth, tol=3):
    """Pair one-way drawn links of ``fac`` with ``oth`` links whose ends lie within ``tol``;
    yield (factory sense, other sense), +1 = along the factory link's first->last points."""
    near = lambda p, q: abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol  # noqa: E731
    idx = collections.defaultdict(list)
    for a, b, d in oth:
        idx[(a[0] // 4, a[1] // 4)].append((a, b, d))
    for a, b, d in fac:
        if d not in (1, 2):
            continue
        for oa, ob, od in idx.get((a[0] // 4, a[1] // 4), []) + idx.get((b[0] // 4, b[1] // 4), []):
            if near(a, oa) and near(b, ob):
                flip = 1
            elif near(a, ob) and near(b, oa):
                flip = -1
            else:
                continue
            yield (1 if d == 1 else -1), (0 if od == 0 else (1 if od == 1 else -1) * flip)
            break


def run_sense(tile: str, other: str, limit: int = 0) -> collections.Counter:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ze0-viewer", "tools_ze0"))
    import route_link_join as R
    F, O = R.Tile(tile), R.Tile(other)
    st = collections.Counter()
    codes = [c for c in F.shape_rec if c in O.shape_rec]
    for code in codes[:limit or None]:
        for fs, os_ in sense_pairs(drawn_links(F, code), drawn_links(O, code)):
            st["factory one-way %+d, other %+d" % (fs, os_)] += 1
    return st


def run(tile: str, sample: int | None) -> collections.Counter:
    import tile_relayout
    m = tile_relayout.read_model(open(tile, "rb").read())
    st = collections.Counter()
    for sec in m["sections"]:
        if sec["id"] != 2:
            continue
        for L in sec["levels"]:
            if L["level"] != 1:
                continue
            recs = [r for dm in L["dirs"] for un in dm["units"] for r in un["recs"] if r]
            if sample:
                random.seed(1)
                recs = random.sample(recs, min(sample, len(recs)))
            for raw in recs:
                pl = zlib.decompress(raw)
                w = list(struct.unpack(">%dH" % (len(pl) // 2), pl[:len(pl) // 2 * 2]))
                st["country (header halfword 26) %d" % w[26]] += 1
                check_record(w, st)
    return st


def selftest() -> int:
    # one record: node 0 (edge) with a one-way link to node 1 and a boundary link,
    # node 1 with the other end of the one-way link
    u = [0, 2, 0, 2] + [0, 0] * 11
    u[4:6] = [2, 2]
    u += [0x2000, 0x0100, 0, 1, 0, 0x4000, 0x0003, 5, 0, 0,
          0, 0, 0, 0x0003, 0x8004, 0, 0]
    u += [0x1100, 0x0100, 0, 0, 0, 0x8000, 0x2003, 5, 0, 0]
    w = [0] * 27
    w[6:10] = [0, 27, 0, len(u)]
    st = collections.Counter()
    check_record(w + u, st)
    assert st["direction one-way (1/2)"] == 1, st
    assert st["boundary link at a mesh-edge node"] == 1, st
    assert st["header: sum of 11 pair firsts == node count"] == 1, st
    assert link_words(1, 0x0041, 0x4000) == 4
    fac = [((0, 0), (100, 0), 1), ((0, 50), (0, 90), 2)]
    oth = [((101, 1), (1, 0), 2), ((0, 50), (0, 91), 0)]
    assert list(sense_pairs(fac, oth)) == [(1, 1), (-1, 0)]
    st = collections.Counter()
    census_record(w + u, st)
    assert st["node: dead end, direction 2"] == 1 and st["node: no way out (all 2/3)"] == 1, st
    assert st["dir 1 class  5 type  0"] == 1 and st["node: no way in (all 1/3)"] == 0, st
    # level 2: two nodes joined by one link, mapped to level-1 nodes 0 and 1 of record (0, 0)
    u0 = [0, 2, 0, 2] + [0, 0] * 11 + [0x1004, 0x0004, 0, 1, 0, 0, 0, 0, 0, 0,
                                         0x1008, 0x0004, 0, 0, 0, 0, 1, 0, 0, 0]
    u1 = [2, 0x2100, 0x1000, 0, 0, 0, 1, 0, 1, 0x1000, 1, 0, 1, 0, 0, 0, 0xA40F, 0xCC02]
    l1 = {(0xA40C, 0xCC0C): ([(16, 16), (32, 16)], [[1], [0]])}
    st = collections.Counter()
    check_level2((0xA40F, 0xCC02), u0, u1, l1, st)
    assert st["L2 unit 1: parses exactly, 2-word trailer"] == 1, st
    assert st["L2 link triple: node == link target (w0 & 0x3fff)"] == 2, st
    assert st["L2 entry: level-1 node on the level-2 node (1/4 scale, +-1)"] == 2, st
    assert st["L2 link triple: level-1 node is a level-1 neighbour of the entry's"] == 2, st
    print("selftest OK: link size, one-way pairing, boundary links, header pairs, census, level-2 unit 1")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tile", nargs="?")
    ap.add_argument("--sample", type=int)
    ap.add_argument("--level2", action="store_true", help="check level-2 unit 1 instead")
    ap.add_argument("--s1-direction", action="store_true",
                    help="pair section-2 directions with the section-1 one-way bits")
    ap.add_argument("--limit", type=int, default=0, help="--s1-direction: first N parcels only")
    ap.add_argument("--census", action="store_true",
                    help="count (direction, class, type) per link end and one-way traps per node")
    ap.add_argument("--sense", metavar="OTHER",
                    help="compare section-1 one-way sense of TILE (factory) with OTHER on links with matching ends")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.tile:
        ap.error("TILE required")
    if a.s1_direction:
        st = run_s1_direction(a.tile, a.limit)
    elif a.sense:
        st = run_sense(a.tile, a.sense, a.limit)
    elif a.census:
        st = run_census(a.tile)
    else:
        st = run_level2(a.tile) if a.level2 else run(a.tile, a.sample)
    for k, v in sorted(st.items()):
        print("%-55s %d" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
