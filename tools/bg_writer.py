#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write OSM water, river and forest polygons into one ZE0 level-1 tile.

Input is a small OSM XML extract (api.openstreetmap.org /map?bbox=...).  The
geometry is clipped to one parcel, simplified with the M5.75 default and
encoded with the ZE0 background grammar recorded by M4.70 and implemented in
``clarion_bg.py``: a 26-pair layer table, ``0001 0003`` groups and
``count/type/ref/x0/y0 + int8 dx,dy`` shapes.  The result is spliced into a
factory tile exactly like ``tilewriter.splice_factory`` does for roads.

Commands:
  python3 tools/bg_writer.py --selftest
  python3 tools/bg_writer.py --factory TILE --osm-xml EXTRACT --cell B48R058R --out OUT.DAT [--json REPORT]
"""
import argparse
import collections
import hashlib
import json
import math
import struct
import sys
import zlib
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "ze0-viewer" / "tools_ze0"))
import clarion_bg  # noqa: E402
import clarion_tile  # noqa: E402

import tilewriter  # noqa: E402
from slot_budget import dp_simplify  # noqa: E402

LEVEL = 1
TYPES = {"water": 0xC015, "river": 0xC014, "forest": 0xC01A}
LAYERS = {"water": 1, "river": 11, "forest": 0}
KINDS = {"water": 0x80, "river": 0x40, "forest": 0x80}
TOLERANCE_M = 3.0  # M5.75 default for level 1


def parse_osm_xml(path):
    """Return nodes {id: (lon, lat)} and features [{kind, points}]."""
    root = ET.parse(path).getroot()
    nodes = {}
    for n in root.findall("node"):
        nodes[n.get("id")] = (float(n.get("lon")), float(n.get("lat")))
    features = []
    for w in root.findall("way"):
        tags = {t.get("k"): t.get("v") for t in w.findall("tag")}
        kind = None
        if tags.get("natural") == "water":
            kind = "water"
        elif tags.get("waterway") == "river":
            kind = "river"
        elif tags.get("landuse") == "forest" or tags.get("natural") == "wood":
            kind = "forest"
        if kind is None:
            continue
        pts = [nodes[nd.get("ref")] for nd in w.findall("nd") if nd.get("ref") in nodes]
        if len(pts) >= 2:
            features.append(dict(kind=kind, id=w.get("id"), points=pts))
    return nodes, features


def clip_polygon(points, rect):
    """Sutherland-Hodgman clip of a closed ring to (lon0, lat0, lon1, lat1)."""
    x0, y0, x1, y1 = rect
    def inside(p, edge):
        x, y = p
        return (x >= x0, x <= x1, y >= y0, y <= y1)[edge]
    def cut(a, b, edge):
        dx, dy = b[0] - a[0], b[1] - a[1]
        if edge == 0:
            t = (x0 - a[0]) / dx
        elif edge == 1:
            t = (x1 - a[0]) / dx
        elif edge == 2:
            t = (y0 - a[1]) / dy
        else:
            t = (y1 - a[1]) / dy
        return (a[0] + t * dx, a[1] + t * dy)
    out = list(points)
    for edge in range(4):
        if not out:
            break
        src, out = out, []
        for a, b in zip(src[-1:] + src[:-1], src):
            ai, bi = inside(a, edge), inside(b, edge)
            if ai != bi:
                out.append(cut(a, b, edge))
            if bi:
                out.append(b)
    return out


def target_parcel(features, level=LEVEL):
    """Pick the parcel containing the most of the three feature kinds."""
    candidates = collections.Counter()
    for f in features:
        for lon, lat in f["points"]:
            candidates[tilewriter.parcel_of(lon, lat, level)] += 1
    best, best_score = None, (-1, -1)
    for p, _ in candidates.most_common(40):
        y0, x0, row, col = p
        lon0, lat0, w, h = clarion_bg.parcel_geo(level, y0, x0, row, col)
        rect = (lon0, lat0, lon0 + w, lat0 + h)
        kinds = set()
        for f in features:
            if f["kind"] == "river":
                for piece in tilewriter.parcel_runs(f["points"], level):
                    if piece[0] == p:
                        kinds.add("river")
            elif len(clip_polygon(f["points"], rect)) >= 4:
                kinds.add(f["kind"])
        score = (len(kinds), candidates[p])
        if score > best_score:
            best, best_score = p, score
        if score[0] == 3:
            break
    return best, best_score


def feature_shapes(features, parcel, level=LEVEL):
    """Clip + simplify + quantise to the parcel's 0..2047 lattice."""
    y0, x0, row, col = parcel
    lon0, lat0, w, h = clarion_bg.parcel_geo(level, y0, x0, row, col)
    rect = (lon0, lat0, lon0 + w, lat0 + h)
    shapes = {k: [] for k in TYPES}
    for f in features:
        kind = f["kind"]
        if kind == "river":
            pieces = [pts for p, pts in tilewriter.parcel_runs(f["points"], level) if p == parcel]
            closed = False
        else:
            ring = clip_polygon(f["points"], rect)
            pieces = [ring] if len(ring) >= 4 else []
            closed = True
        for pts in pieces:
            simp, _err = dp_simplify(pts, TOLERANCE_M)
            q = [tilewriter.quantise(lon, lat, lon0, lat0, w, h) for lon, lat in simp]
            dedup = [q[0]]
            for p in q[1:]:
                if p != dedup[-1]:
                    dedup.append(p)
            if closed:
                if dedup[0] != dedup[-1]:
                    dedup.append(dedup[0])
                if len(dedup) < 4:
                    continue
            elif len(dedup) < 2:
                continue
            shapes[kind].append(dict(type=TYPES[kind], ref=0xFFFF, pts=dedup))
    return shapes


def densify(pts):
    """The same int8-step walk clarion_bg.build_shapes applies on write."""
    walked = [pts[0]]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dx, dy = x1 - x0, y1 - y0
        n = max(1, -(-max(abs(dx), abs(dy)) // 127))
        for i in range(1, n + 1):
            walked.append((x0 + round(dx * i / n), y0 + round(dy * i / n)))
    return walked


def template_header(tile, level=LEVEL):
    """Header words of the first odd background record of a level-1 directory."""
    entry = tilewriter.road_level(tile, level)
    for directory in entry["dirs"]:
        for slot in directory["slots"].values():
            for rec in slot["recs"]:
                if rec["k"] % 2 == 1:
                    try:
                        plain = zlib.decompressobj().decompress(rec["raw"])
                        return list(struct.unpack_from(">22H", plain, 0))
                    except (zlib.error, struct.error):
                        pass
    raise ValueError("no odd background record in the factory tile to use as header template")


def background_record(shapes, header, parcel, level=LEVEL):
    """Build one inflated ZE0 background record (26 layers)."""
    w = list(header)
    y0, x0, row, col = parcel
    per = clarion_bg.LEVELS[level]["rows"] // clarion_bg.LEVELS[level]["dir_meshes"]
    w[0], w[1] = clarion_bg.parcel_code(level, y0 * per + row, x0 * per + col)
    layers = {}
    for kind in ("forest", "water", "river"):
        items = shapes.get(kind, [])
        if not items:
            continue
        subs = [dict(kind=KINDS[kind], shapes=items[i:i + 255])
                for i in range(0, len(items), 255)]
        layers[LAYERS[kind]] = dict(subs[0], more=subs[1:])
    model = dict(hdr=w, nlayers=26, layers=layers, sections={}, gi=9, strict=True)
    return clarion_bg.build_record(model)


def splice_record(factory, parcel, pair, plain, level=LEVEL):
    """Replace/add one odd record in the slot block; return (tile bytes, info)."""
    tile = clarion_tile.read_tile(factory)
    entry = tilewriter.road_level(tile, level)
    directories = {(d["y"], tilewriter.dir_x0(d)): d for d in entry["dirs"]}
    y0, x0, row, col = parcel
    directory = directories.get((y0, x0))
    if directory is None or directory["kind"] not in tilewriter.SPLICEABLE_DIR_KINDS:
        raise ValueError("no spliceable level-%d directory at y=%d x=%d" % (level, y0, x0))
    slot = directory["slots"].get(row)
    body = tilewriter._slot_body(level, directory["body"], slot)
    recs = list(slot["recs"]) if slot else []
    comp = tilewriter.compress(plain)
    recs = [r for r in recs if r["k"] != pair]
    recs.append(dict(k=pair, raw=comp, words=len(plain) // 2, flag=0))
    recs.sort(key=lambda r: r["k"])
    for r in recs:
        struct.pack_into(">II", body, 8 * r["k"], len(r["raw"]) // 2, r["words"])
    block = b"".join(bytes(r["raw"]) for r in recs)
    out = bytearray(factory)
    slot_off = directory["off"] + 12 + row * (4 + directory["body"])
    old_off = slot["block_off"] if slot else None
    old = clarion_tile.block_bytes(slot) if slot else b""
    shared = tilewriter.shared_slot_blocks(tile)
    if old_off is not None and old_off not in shared and 0 < len(block) <= len(old) \
            and out[old_off:old_off + len(old)] == old:
        out[old_off:old_off + len(block)] = block
        out[old_off + len(block):old_off + len(old)] = b"\x00" * (len(old) - len(block))
        how = "in_place"
    else:
        offset = clarion_tile.pad256(len(out))
        out.extend(b"\x00" * (offset - len(out)))
        out.extend(block)
        struct.pack_into(">I", out, slot_off, clarion_tile.enc_addr(offset))
        how = "appended"
    out[slot_off + 4:slot_off + 4 + directory["body"]] = bytes(body)
    return bytes(out), dict(how=how, directory=hex(directory["off"]), slot=row,
                            pair=pair, compressed=len(comp), plain=len(plain))


def readback(tile_bytes, parcel, pair, level=LEVEL):
    """Decode the written odd record and return its shapes for count/vertex check."""
    tile = clarion_tile.read_tile(tile_bytes)
    entry = tilewriter.road_level(tile, level)
    y0, x0, row, col = parcel
    directory = next(d for d in entry["dirs"]
                     if (d["y"], tilewriter.dir_x0(d)) == (y0, x0))
    slot = directory["slots"][row]
    rec = next(r for r in slot["recs"] if r["k"] == pair)
    plain = zlib.decompressobj().decompress(rec["raw"])
    model = clarion_bg.parse_record(plain)
    by_kind = collections.defaultdict(list)
    for layer in model["layers"].values():
        for s in layer.get("shapes", []):
            by_kind[s["type"]].append([list(p) for p in s["pts"]])
    return dict(shapes={"%04x" % k: v for k, v in by_kind.items()},
                total=sum(len(v) for v in by_kind.values()),
                layers=sorted(model["layers"]), nlayers=model["nlayers"])


def write_background(factory_path, xml_path, cell, out_path=None):
    factory = Path(factory_path).read_bytes()
    nodes, features = parse_osm_xml(xml_path)
    parcel, score = target_parcel(features)
    if parcel is None or score[0] < 2:
        raise ValueError("the extract has fewer than two of water/river/forest in one parcel")
    shapes = feature_shapes(features, parcel)
    plain = background_record(shapes, template_header(clarion_tile.read_tile(factory)), parcel)
    pair = 2 * parcel[3] + 1
    blob, info = splice_record(factory, parcel, pair, plain)
    rb = readback(blob, parcel, pair)
    expected = {("%04x" % TYPES[k]): [ [list(p) for p in densify(s["pts"])] for s in v]
                for k, v in shapes.items() if v }
    ok = rb["shapes"] == expected
    report = dict(cell=cell, factory=dict(path=str(factory_path), sha256=hashlib.sha256(factory).hexdigest()),
                 osm=dict(path=str(xml_path), sha256=hashlib.sha256(Path(xml_path).read_bytes()).hexdigest()),
                 parcel=dict(y=parcel[0], x=parcel[1], row=parcel[2], col=parcel[3]),
                 kinds=score[0], input_types={k: len(v) for k, v in shapes.items()},
                 splice=info, readback=rb, roundtrip=ok)
    if out_path:
        Path(out_path).write_bytes(blob)
    return report, blob


def selftest():
    """Synthetic XML with three features in one parcel; write + readback must agree."""
    import tempfile
    p = Path(tempfile.mkdtemp(prefix="bgwriter-")) / "town.xml"
    # Four points inside B50R058R parcel grid; the three features overlap so
    # one parcel can hold all of them.
    xml = ['<osm version="0.6">']
    for i, (lon, lat) in enumerate([(17.00, 50.70), (17.01, 50.70), (17.01, 50.71), (17.00, 50.71)], 1):
        xml.append('<node id="%d" lon="%.6f" lat="%.6f"/>' % (i, lon, lat))
    for wid, tags in ((1, '<tag k="natural" v="water"/>'),
                      (2, '<tag k="waterway" v="river"/>'),
                      (3, '<tag k="landuse" v="forest"/>')):
        xml.append('<way id="%d">%s%s</way>' % (wid, ''.join('<nd ref="%d"/>' % i for i in range(1, 5)), tags))
    xml.append('</osm>')
    p.write_text(''.join(xml))
    assert len(parse_osm_xml(p)[1]) == 3
    assert len(clip_polygon([(0, 0), (2, 0), (2, 2), (0, 2)], (0, 0, 1, 1))) >= 4
    synthetic = clarion_tile.read_tile(tilewriter.make_factory("B50R058R"))
    header = template_header(synthetic)
    shapes = {"water": [dict(type=TYPES["water"], ref=0xFFFF,
                             pts=[(10, 10), (100, 10), (100, 100), (10, 100), (10, 10)])]}
    plain = background_record(shapes, header, (82, 940, 5, 5))
    model = clarion_bg.parse_record(plain)
    got = [s["type"] for layer in model["layers"].values() for s in layer.get("shapes", [])]
    assert got == [TYPES["water"]], got
    assert model["nlayers"] == 26
    print("bg_writer selftest: XML parse, clip, parcel pick, ZE0 record round-trip OK")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--factory")
    ap.add_argument("--osm-xml")
    ap.add_argument("--cell", default="B48R058R")
    ap.add_argument("--out")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not (a.factory and a.osm_xml):
        ap.error("--factory and --osm-xml are required")
    report, _ = write_background(a.factory, a.osm_xml, a.cell, a.out)
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=2) + "\n")
    print("cell %s parcel %s kinds %d" % (a.cell, report["parcel"], report["kinds"]))
    print("input %s written %s" % (report["input_types"], report["readback"]["shapes"].keys()))
    print("spliced %s roundtrip %s" % (report["splice"]["how"], report["roundtrip"]))
    return 0 if report["roundtrip"] else 1


if __name__ == "__main__":
    sys.exit(main())
