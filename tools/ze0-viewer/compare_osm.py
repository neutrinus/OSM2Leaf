#!/usr/bin/env python3
"""Compare decoded ZE0 coastline/water edges with an OSM coastline extract.

    python3 compare_osm.py TILE.geojson OSM.osm [--bbox lon0,lat0,lon1,lat1]
                                                   [--level 1] [--layer 1]

The OSM input is any OSM XML file, e.g. a small area from the OSM API:

    curl -A 'OSM2Leaf-research/0.1' \\
      'https://api.openstreetmap.org/api/0.6/map?bbox=10.80,35.74,10.86,35.80' \\
      -o monastir.osm

Only ways tagged natural=coastline are used.  Distances are point-to-segment
in metres in a local equirectangular projection.  Two directions are reported:

  decoded -> OSM   how far the card's water edge is from OSM
  OSM -> decoded   how much of the OSM coast the card actually represents

Axis-aligned edges that sit on the level-1 parcel grid are dropped: they are
parcel clips, not coast.  This is a sanity metric, not a survey.  The factory
data is NAVTEQ 2011 and OSM is current, and ZE0 stores land implicitly, so a
median of a few hundred metres on a developed coast means "same coast,
different vintage/generalisation", not "wrong by that much".
"""
import argparse
import json
import math
import xml.etree.ElementTree as ET

M_PER_DEG = 111320.0
LON_STEP = 1.0 / 32.0      # level-1 parcel width in degrees
LAT_STEP = 1.0 / 48.0      # level-1 parcel height in degrees


def _on_grid(v):
    return (abs(v[0] / LON_STEP - round(v[0] / LON_STEP)) < 1e-4 or
            abs(v[1] / LAT_STEP - round(v[1] / LAT_STEP)) < 1e-4)


def osm_coast(path, bbox=None):
    """(segments, vertices) of natural=coastline ways."""
    tree = ET.parse(path)
    nodes = {}
    for n in tree.getroot().iter('node'):
        try:
            nodes[n.get('id')] = (float(n.get('lon')), float(n.get('lat')))
        except (TypeError, ValueError):
            continue
    segs, verts = [], []
    for w in tree.getroot().iter('way'):
        tags = {t.get('k'): t.get('v') for t in w.findall('tag')}
        if tags.get('natural') != 'coastline':
            continue
        pts = [nodes[nd.get('ref')] for nd in w.findall('nd') if nd.get('ref') in nodes]
        for a, b in zip(pts, pts[1:]):
            if bbox and not (_near(a, bbox) or _near(b, bbox)):
                continue
            segs.append((a, b))
        for p in pts:
            if not bbox or _near(p, bbox, 0):
                verts.append(p)
    return segs, verts


def _near(p, bbox, pad=0.01):
    return bbox[0] - pad <= p[0] <= bbox[2] + pad and bbox[1] - pad <= p[1] <= bbox[3] + pad


def decoded_edges(path, level, layer, bbox):
    """(segments, vertices) of decoded features of one level/layer."""
    gj = json.load(open(path))
    segs, verts = [], []
    for f in gj['features']:
        p = f['properties']
        if p.get('level') != level or p.get('layer') != layer:
            continue
        g = f['geometry']
        if g['type'] == 'Point':
            pts = [g['coordinates']]
        elif g['type'] == 'LineString':
            pts = g['coordinates']
        elif g['type'] == 'Polygon':
            pts = [q for ring in g['coordinates'] for q in ring]
        else:
            continue
        if bbox and not any(_near(q, bbox, 0) for q in pts):
            continue
        for q in pts:
            if not bbox or _near(q, bbox, 0):
                verts.append(q)
        for a, b in zip(pts, pts[1:]):
            if _on_grid(a) and _on_grid(b):
                continue
            if bbox and not (_near(a, bbox, 0.02) or _near(b, bbox, 0.02)):
                continue
            segs.append((a, b))
    return segs, verts


def _dist(p, a, b, lat0):
    kx = M_PER_DEG * math.cos(math.radians(lat0))
    px, py = p[0] * kx, p[1] * M_PER_DEG
    ax, ay = a[0] * kx, a[1] * M_PER_DEG
    bx, by = b[0] * kx, b[1] * M_PER_DEG
    dx, dy = bx - ax, by - ay
    den = dx * dx + dy * dy
    t = 0.0 if den == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / den))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def nearest(p, segs, lat0):
    best = 1e30
    for a, b in segs:
        d = _dist(p, a, b, lat0)
        if d < best:
            best = d
    return best


def _stats(vals):
    vals = sorted(vals)
    n = len(vals)
    if not n:
        return None
    q = lambda f: vals[min(n - 1, int(f * (n - 1)))]
    return n, q(0.5), q(0.9), vals[-1], sum(vals) / n


def _print(label, st):
    if st:
        n, med, p90, mx, mean = st
        print('%s: n %d, median %.1f m, p90 %.1f m, max %.1f m, mean %.1f m'
              % (label, n, med, p90, mx, mean))
    else:
        print('%s: no points' % label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('geojson'); ap.add_argument('osm')
    ap.add_argument('--bbox', default='')
    ap.add_argument('--level', type=int, default=1)
    ap.add_argument('--layer', type=int, default=1,
                    help='1 = sea/water polygon (ZE0 has no layer-11 coastline)')
    args = ap.parse_args()
    bbox = tuple(float(x) for x in args.bbox.split(',')) if args.bbox else None

    osm_segs, osm_verts = osm_coast(args.osm, bbox)
    dec_segs, dec_verts = decoded_edges(args.geojson, args.level, args.layer, bbox)
    print('OSM: %d segments, %d vertices' % (len(osm_segs), len(osm_verts)))
    print('decoded level %d layer %d: %d segments, %d vertices'
          % (args.level, args.layer, len(dec_segs), len(dec_verts)))
    if not osm_segs or not dec_segs:
        print('nothing to compare')
        return
    lat0 = sum(p[1] for p in dec_verts) / len(dec_verts)
    _print('decoded -> OSM', _stats([nearest(p, osm_segs, lat0) for p in dec_verts]))
    _print('OSM -> decoded', _stats([nearest(p, dec_segs, lat0) for p in osm_verts]))


if __name__ == '__main__':
    main()
