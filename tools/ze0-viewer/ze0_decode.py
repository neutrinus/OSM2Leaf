#!/usr/bin/env python3
"""Decode ZE0 (X08-02-00) section-1 background geometry to a neutral GeoJSON.

Usage:
    python3 ze0_decode.py TILE.DAT OUT.geojson [--levels 1,2,3] [--min-level N]

The ZE0 format differs from the X08-03-00 files osm2clarion documents in four
places this decoder handles (see notes.md):

  * zlib streams are 78 9c, not 58 85 (detected by a valid zlib header);
  * background records carry kind 0x00fa in word 2, not 0x0019;
  * the even pair of a section-1 row is the road-shape record, the odd pair
    is the background record;
  * directory slot-body sizes are per kind, not per section.

Levels 1 and 2 live in a MAPAL001 tile, levels 3-6 in LEV3456R.DAT.

Output is deliberately neutral: every feature carries level, layer, type,
parcel and the directory mesh.  No projection other than WGS84 lon/lat.
"""
import argparse
import json
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools_ze0'))

import clarion_bg
import clarion_tile
import ze0_roads

# Mesh coordinates: y = lat * 1.5, x = lon + 924.  A directory header stores
# x as (mesh_x - 1024), i.e. a signed value around -120..-20.
MESH_LON0 = 924

# level -> (parcel columns, parcel rows, meshes per directory, pairs per column)
# levels 1-4 carry two records per column (even = road shapes, odd = background),
# levels 5-6 carry one.
LEVEL_LAYOUT = {
    1: (32, 32, 1, 2),
    2: (32, 32, 4, 2),
    3: (16, 16, 8, 2),
    4: (44, 44, 88, 2),
    5: (11, 11, 88, 1),
    6: (1, 1, 88, 1),
}


def _signed16(v):
    return v - 65536 if v > 32767 else v


def parcel_origin(level, dir_y, dir_x, row, col):
    """(lon0, lat0, width_deg, height_deg) of a parcel, WGS84."""
    _cols, _rows, meshes, _ppc = LEVEL_LAYOUT[level]
    width = 1.0 * meshes / _cols          # 1 degree of longitude per mesh
    height = (2.0 / 3.0) * meshes / _rows  # 40 arc-minutes per mesh
    # The directory header stores mesh_x - 1024.
    mesh_x = _signed16(dir_x) + 1024
    lon0 = (mesh_x - MESH_LON0) + col * width
    lat0 = dir_y / 1.5 + row * height
    return lon0, lat0, width, height


def _is_background(level, k):
    ppc = LEVEL_LAYOUT[level][3]
    return (k % 2 == 1) if ppc == 2 else True


def _road_features(plain, level, dir_y, dir_x, row, col):
    """Road-shape record (even pair) to line features.

    Layer 5 is the main road layer; 6 is the second road layer, 4 other
    network, 0 ferries.  Style/value/id are parsed but not yet used for
    colour or direction.
    """
    rec = ze0_roads.parse_record(plain)
    lon0, lat0, w, h = parcel_origin(level, dir_y, dir_x, row, col)
    for layer, shapes in rec['layers'].items():
        if layer not in (0, 5):      # 5 = drawn roads, 0 = ferries; 4/6 unknown
            continue
        for sh in shapes:
            for line in sh.get('lines') or [sh.get('points', [])]:
                if len(line) < 2:
                    continue
                coords = [(lon0 + x / clarion_bg.UNITS * w,
                           lat0 + y / clarion_bg.UNITS * h)
                          for x, y, *_ in line]
                yield {
                    'level': level,
                    'dir_y': dir_y,
                    'dir_x': _signed16(dir_x) + 1024,
                    'row': row,
                    'col': col,
                    'layer': 200 + layer,
                    'kind': 0x40,
                    'type': 0x1000 | layer,
                    'road': True,
                    'coords': coords,
                }


def _level6_features(plain, dir_y, dir_x):
    """Level-6 record: 26 (offset, point-count) pairs from word 11.

    The second number is a total point count, not a shape count; the group
    header carries the shape count.  Parse each subgroup's shapes and map the
    2048-unit sheet to the whole database box.
    """
    hdr = struct.unpack_from('>22H', plain, 0)
    base = 4 * hdr[9]
    pairs = [struct.unpack_from('>HH', plain, base + 4 * k) for k in range(26)]
    lon0, lat0, w, h = parcel_origin(6, dir_y, dir_x, 0, 0)
    for layer, (off, _points) in enumerate(pairs):
        if off == 0xffff:
            continue
        q = base + 4 * off
        nsub, hw = struct.unpack_from('>HH', plain, q)
        if not (1 <= nsub <= 8):
            continue
        q += 4
        for _ in range(nsub):
            if q + 2 > len(plain):
                break
            kind, count = plain[q], plain[q + 1]
            q += 2
            if _ < nsub - 1:
                q += 2                 # word offset where this subgroup ends
            try:
                q, shapes = clarion_bg.parse_shapes(plain, q, kind, count)
            except Exception:
                break
            for sh in shapes:
                coords = [(lon0 + x / clarion_bg.UNITS * w,
                           lat0 + y / clarion_bg.UNITS * h) for x, y in sh['pts']]
                if not coords:
                    continue
                yield {
                    'level': 6, 'dir_y': dir_y,
                    'dir_x': _signed16(dir_x) + 1024,
                    'row': 0, 'col': 0,
                    'layer': layer, 'kind': kind, 'type': sh['type'],
                    'coords': coords,
                }


def _record_col(level, k):
    ppc = LEVEL_LAYOUT[level][3]
    return k // 2 if ppc == 2 else k


def cell_bbox(name):
    """WGS84 bbox of a MAPAL001 cell name B{hex}R{hex}R."""
    b = int(name[1:3], 16); r = int(name[4:7], 16)
    lat0 = b * 2 / 3
    lon1 = 108 - r
    return lon1 - 8, lat0, lon1, lat0 + 16 / 3


def decode_records(path, levels=None, bbox=None):
    """Return (features, coverage_rects) from a ZE0 tile or LEV3456R.DAT.

    coverage_rects are the extents of every parcel that has a background
    record.  A parcel inside coverage is land unless a sea polygon says
    otherwise; a parcel with no record is simply not on the card.
    """
    features, coverage = [], []
    data = open(path, 'rb').read()
    tile = clarion_tile.read_tile(data)
    section = tile['sections'][0]  # section 1 is the drawn surface

    for lvl in section['levels']:
        level = lvl['level']
        if level not in LEVEL_LAYOUT:
            continue
        if levels and level not in levels:
            continue
        for d in lvl['dirs']:
            for row, slot in d['slots'].items():
                for rec in slot['recs']:
                    try:
                        plain = (zlib.decompress(rec['raw'])
                                 if clarion_tile.is_zlib(rec['raw']) else rec['raw'])
                        word2 = struct.unpack_from('>H', plain, 4)[0]
                    except Exception:
                        continue
                    if not _is_background(level, rec['k']):
                        if word2 != 0xfa:          # even pair: road shapes
                            continue
                        try:
                            for f in _road_features(plain, level, d['y'], d['x'],
                                                    row, _record_col(level, rec['k'])):
                                if bbox and not any(bbox[0] <= q[0] <= bbox[2]
                                                    and bbox[1] <= q[1] <= bbox[3]
                                                    for q in f['coords']):
                                    continue
                                features.append(f)
                        except Exception:
                            pass
                        continue
                    if level == 6 and word2 == 0xfa:
                        for f in _level6_features(plain, d['y'], d['x']):
                            if bbox and not any(bbox[0] <= q[0] <= bbox[2]
                                                and bbox[1] <= q[1] <= bbox[3]
                                                for q in f['coords']):
                                continue
                            features.append(f)
                        continue
                    if word2 not in (0xfa, 0x19):
                        continue
                    try:
                        parsed = clarion_bg.parse_record(plain)
                    except Exception:
                        continue
                    lon0, lat0, w, h = parcel_origin(
                        level, d['y'], d['x'], row, _record_col(level, rec['k']))
                    if bbox is None or (lon0 < bbox[2] and lon0 + w > bbox[0]
                                        and lat0 < bbox[3] and lat0 + h > bbox[1]):
                        coverage.append((lon0, lat0, lon0 + w, lat0 + h, level))
                    for layer, group in parsed['layers'].items():
                        if 'raw' in group:
                            continue
                        for shape in group['shapes']:
                            coords = [
                                (lon0 + x / clarion_bg.UNITS * w,
                                 lat0 + y / clarion_bg.UNITS * h)
                                for x, y in shape['pts']]
                            if not coords or len(coords) > 8192:
                                continue
                            if bbox and not any(bbox[0] <= q[0] <= bbox[2]
                                                and bbox[1] <= q[1] <= bbox[3]
                                                for q in coords):
                                continue
                            features.append({
                                'level': level,
                                'dir_y': d['y'],
                                'dir_x': _signed16(d['x']) + 1024,
                                'row': row,
                                'col': _record_col(level, rec['k']),
                                'layer': layer,
                                'kind': group.get('kind', 0),
                                'type': shape['type'],
                                'coords': coords,
                            })
    return features, coverage


def decode_tile(path, levels=None, bbox=None):
    """Yield feature dicts only (kept for one-liners and tests)."""
    return decode_records(path, levels, bbox)[0]


def to_geojson(features, coverage=None):
    out = []
    for f in features:
        kind = f['kind']
        if kind == 0 or len(f['coords']) == 1:
            geom = {'type': 'Point', 'coordinates': list(f['coords'][0])}
        elif kind & 0x80:
            ring = [list(c) for c in f['coords']]
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            geom = {'type': 'Polygon', 'coordinates': [ring]}
        else:
            geom = {'type': 'LineString', 'coordinates': [list(c) for c in f['coords']]}
        props = {k: v for k, v in f.items() if k != 'coords'}
        props['type'] = '0x%04x' % props['type']
        out.append({'type': 'Feature', 'geometry': geom, 'properties': props})
    gj = {'type': 'FeatureCollection', 'features': out}
    if coverage:
        gj['ze0_coverage'] = [list(r) for r in coverage]
    return gj


def feature_bbox(features):
    xs, ys = [], []
    for f in features:
        xs.extend(c[0] for c in f['coords'])
        ys.extend(c[1] for c in f['coords'])
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('tile')
    ap.add_argument('out')
    ap.add_argument('--levels', default='',
                    help='comma-separated levels, e.g. 1,2 (default: all present)')
    ap.add_argument('--stats', action='store_true')
    ap.add_argument('--bbox', default='', help='lonmin,latmin,lonmax,latmax')
    ap.add_argument('--cell', default='', help='B28R070R, uses that cell bbox')
    args = ap.parse_args()
    levels = {int(x) for x in args.levels.split(',') if x.strip()} or None
    bbox = tuple(float(x) for x in args.bbox.split(',')) if args.bbox else None
    if args.cell:
        bbox = cell_bbox(args.cell)
    feats, coverage = decode_records(args.tile, levels, bbox)
    gj = to_geojson(feats, coverage)
    with open(args.out, 'w') as fh:
        json.dump(gj, fh, separators=(',', ':'))
    print('%s: %d features' % (args.out, len(feats)))
    if args.stats:
        from collections import Counter
        c = Counter((f['level'], f['layer'], '0x%04x' % f['type']) for f in feats)
        for k, v in sorted(c.items()):
            print('  level %d layer %-2d type %s: %d' % (k[0], k[1], k[2], v))
        print('  bbox lon/lat:', feature_bbox(feats))


if __name__ == '__main__':
    main()
