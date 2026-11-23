#!/usr/bin/env python3
"""osm_areas.py — background features (water, parks, forest, urban area, rivers) from an OSM PBF (M5.89, Z4).

The road IMF (``osm_ingest.py``) keeps only ``highway=*``. The background
needs areas: closed ways and ``type=multipolygon`` relations with a land-use
tag, and river/canal centre lines. This tool reads the PBF three times with
``osm_ingest.iter_pbf`` (relations, then ways, then the nodes those need), so
memory holds only the features kept, assembles multipolygon outer rings from
their member ways, and writes one JSON line per feature:

    {"id": "w123", "kind": "park", "rings": [[[lon, lat], ...]], "holes": [[...]]}
    {"id": "w456", "kind": "river", "line": [[lon, lat], ...]}

    osm_areas.py IN.osm.pbf --bbox=W,S,E,N -o OUT.jsonl [--json]
    osm_areas.py --selftest

Kinds and the tags they come from are in ``classify``; anything else is
dropped and counted. Inner rings are kept as ``holes``; the writer decides what
to do with them. Exit codes: 0 ok, 1 check failed, 2 usage.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import osm_ingest  # noqa: E402

WATER_NATURAL = {"water", "bay"}
WATER_LANDUSE = {"reservoir", "basin"}
PARK_LEISURE = {"park", "garden", "common", "recreation_ground", "nature_reserve", "golf_course"}
PARK_LANDUSE = {"grass", "recreation_ground", "village_green", "cemetery", "meadow", "allotments"}
FOREST_LANDUSE = {"forest"}
FOREST_NATURAL = {"wood"}
HEATH_NATURAL = {"heath", "scrub", "grassland"}
URBAN_LANDUSE = {"residential", "commercial", "industrial", "retail", "railway", "construction",
                 "brownfield", "garages", "education", "institutional"}
LINE_WATERWAY = {"river", "canal"}
PLACES = {"city", "town", "suburb", "quarter", "neighbourhood", "village", "hamlet", "locality"}
KINDS = ("water", "riverarea", "river", "park", "forest", "heath", "urban")
RIVER_WATER = {"river", "canal", "stream"}


def classify(tags: dict, closed: bool) -> str | None:
    """OSM tags -> background kind, or None. Lines only for rivers/canals."""
    ww = tags.get("waterway")
    if not closed:
        return "river" if ww in LINE_WATERWAY else None
    if ww == "riverbank" or tags.get("natural") == "water" and tags.get("water") in RIVER_WATER:
        return "riverarea"
    if tags.get("natural") in WATER_NATURAL or "water" in tags and tags.get("natural") != "wetland" \
            or tags.get("landuse") in WATER_LANDUSE or ww == "riverbank":
        return "water"
    if tags.get("landuse") in FOREST_LANDUSE or tags.get("natural") in FOREST_NATURAL:
        return "forest"
    if tags.get("leisure") in PARK_LEISURE or tags.get("landuse") in PARK_LANDUSE:
        return "park"
    if tags.get("natural") in HEATH_NATURAL:
        return "heath"
    if tags.get("landuse") in URBAN_LANDUSE:
        return "urban"
    if ww in LINE_WATERWAY:
        return "river"  # a closed river centre line (rare) stays a line
    return None


def join_rings(segments: list[list[int]]) -> tuple[list[list[int]], int]:
    """Join way node lists into closed rings by shared end nodes.

    Returns ``(rings, unclosed)``; segments that never close are dropped and
    counted.
    """
    rings, open_ = [], []
    for s in segments:
        if len(s) >= 4 and s[0] == s[-1]:
            rings.append(list(s))
        elif len(s) >= 2:
            open_.append(list(s))
    unclosed = 0
    while open_:
        cur = open_.pop()
        changed = True
        while cur[0] != cur[-1] and changed:
            changed = False
            for i, s in enumerate(open_):
                if s[0] == cur[-1]:
                    cur += s[1:]
                elif s[-1] == cur[-1]:
                    cur += s[::-1][1:]
                elif s[-1] == cur[0]:
                    cur = s[:-1] + cur
                elif s[0] == cur[0]:
                    cur = s[::-1][:-1] + cur
                else:
                    continue
                open_.pop(i)
                changed = True
                break
        if cur[0] == cur[-1] and len(cur) >= 4:
            rings.append(cur)
        else:
            unclosed += 1
    return rings, unclosed


def in_bbox(pts, bbox) -> bool:
    w, s, e, n = bbox
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return not (max(xs) < w or min(xs) > e or max(ys) < s or min(ys) > n)


def extract(path: str, bbox, elements=None) -> tuple[list[dict], dict]:
    """Three passes over ``path`` (or over the list ``elements`` in the selftest)."""
    def it():
        return iter(elements) if elements is not None else osm_ingest.iter_pbf(path)

    stats = collections.Counter()
    # pass 1: relations
    rels = {}
    member_ways = set()
    for el in it():
        if el[0] != "relation":
            continue
        r = el[1]
        if r.tags.get("type") != "multipolygon":
            continue
        kind = classify(r.tags, True)
        if kind is None or kind == "river":
            stats["relations_other"] += 1
            continue
        outer = [ref for typ, ref, role in r.members if typ == "way" and role in ("outer", "")]
        inner = [ref for typ, ref, role in r.members if typ == "way" and role == "inner"]
        rels[r.id] = (kind, outer, inner)
        member_ways.update(outer)
        member_ways.update(inner)
    stats["relations"] = len(rels)
    # pass 2: ways
    ways = {}
    feats_w = []
    need = set()
    for el in it():
        if el[0] != "way":
            continue
        w = el[1]
        if w.id in member_ways:
            ways[w.id] = w.refs
            need.update(w.refs)
        if len(w.refs) < 2:
            continue
        closed = w.refs[0] == w.refs[-1] and len(w.refs) >= 4
        kind = classify(w.tags, closed)
        if kind is None:
            continue
        feats_w.append((w.id, kind, w.refs))
        need.update(w.refs)
    # pass 3: nodes (and place labels, M5.90)
    coords = {}
    feats = []
    for el in it():
        if el[0] != "node":
            continue
        if el[1] in need:
            coords[el[1]] = (el[3], el[2])  # (lon, lat)
        tags = el[4] if len(el) > 4 else {}
        if tags.get("place") in PLACES and tags.get("name") and in_bbox([(el[3], el[2])], bbox):
            feats.append(dict(id="n%d" % el[1], kind="place", place=tags["place"], name=tags["name"],
                              point=[el[3], el[2]]))
            stats["place"] += 1

    def pts(refs):
        out = [coords[r] for r in refs if r in coords]
        if len(out) != len(refs):
            stats["missing_nodes"] += len(refs) - len(out)
        return out

    for wid, kind, refs in feats_w:
        p = pts(refs)
        if len(p) < 2 or not in_bbox(p, bbox):
            stats["outside"] += 1
            continue
        if kind == "river":
            feats.append(dict(id="w%d" % wid, kind=kind, line=p))
        elif len(p) >= 4 and p[0] == p[-1]:
            feats.append(dict(id="w%d" % wid, kind=kind, rings=[p], holes=[]))
        stats[kind] += 1
    for rid, (kind, outer, inner) in rels.items():
        orings, un1 = join_rings([ways[w] for w in outer if w in ways])
        irings, un2 = join_rings([ways[w] for w in inner if w in ways])
        stats["unclosed_rings"] += un1 + un2
        rings = [p for p in (pts(r) for r in orings) if len(p) >= 4 and p[0] == p[-1]]
        if not rings or not any(in_bbox(r, bbox) for r in rings):
            stats["outside"] += 1
            continue
        holes = [p for p in (pts(r) for r in irings) if len(p) >= 4 and p[0] == p[-1]]
        feats.append(dict(id="r%d" % rid, kind=kind, rings=rings, holes=holes))
        stats[kind] += 1
    return feats, dict(stats)


def selftest() -> int:
    fails = 0

    def ok(cond, msg):
        nonlocal fails
        print(("ok   " if cond else "FAIL ") + msg)
        fails += 0 if cond else 1

    W, R = osm_ingest.OsmWay, osm_ingest.OsmRelation
    nodes = [("node", i, 51.5 + 0.001 * (i // 10), -0.1 + 0.001 * (i % 10), {}) for i in range(100)]
    nodes[55] = ("node", 55, 51.505, -0.095, {"place": "suburb", "name": "Soho"})
    els = nodes + [
        ("way", W(1, [0, 1, 11, 10, 0], {"leisure": "park"})),
        ("way", W(2, [20, 21, 22], {"waterway": "river"})),
        ("way", W(3, [30, 31, 41], {})),           # outer half 1
        ("way", W(4, [41, 40, 30], {})),           # outer half 2 (reversed join)
        ("way", W(5, [50, 51, 61, 50], {"landuse": "farmland"})),
        ("way", W(6, [70, 71, 81, 70], {"natural": "water"})),
        ("relation", R(9, [("way", 3, "outer"), ("way", 4, "outer")], {"type": "multipolygon", "landuse": "forest"})),
    ]
    feats, st = extract("", (-0.2, 51.4, 0.0, 51.6), elements=els)
    kinds = collections.Counter(f["kind"] for f in feats)
    ok(kinds == {"park": 1, "river": 1, "forest": 1, "water": 1, "place": 1},
       "park, river, forest (relation), water, place kept; farmland dropped: %s" % dict(kinds))
    rel = [f for f in feats if f["id"] == "r9"][0]
    ok(len(rel["rings"]) == 1 and rel["rings"][0][0] == rel["rings"][0][-1] and len(rel["rings"][0]) == 5,
       "two half-ways join into one closed ring")
    feats2, _ = extract("", (10.0, 10.0, 11.0, 11.0), elements=els)
    ok(not feats2, "a bbox elsewhere keeps nothing (negative control)")
    rings, un = join_rings([[1, 2, 3], [3, 4], [7, 8]])
    ok(not rings and un == 2, "unclosed chains are counted, not invented")
    ok(classify({"natural": "water", "water": "river"}, True) == "riverarea"
       and classify({"natural": "water", "water": "pond"}, True) == "water"
       and classify({"waterway": "river"}, False) == "river"
       and classify({"highway": "residential"}, False) is None, "classify")
    print("osm_areas selftest: %s (%d failure(s))" % ("OK" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pbf", nargs="?")
    ap.add_argument("--bbox")
    ap.add_argument("-o", "--out")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not (args.pbf and args.bbox and args.out):
        ap.print_usage(sys.stderr)
        return 2
    feats, st = extract(args.pbf, _wsen(args.bbox))
    with open(args.out, "w", encoding="utf-8") as fh:
        for f in feats:
            fh.write(json.dumps(f, separators=(",", ":")) + "\n")
    print(json.dumps(st, indent=1) if args.json else "osm_areas: %d feature(s) %s" % (len(feats), st))
    return 0


def _wsen(text):
    w, s, e, n = (float(v) for v in text.split(","))
    return (w, s, e, n)


if __name__ == "__main__":
    sys.exit(main())
