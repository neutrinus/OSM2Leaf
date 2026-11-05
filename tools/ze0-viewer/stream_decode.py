#!/usr/bin/env python3
"""Streaming ZE0 tile decoder: no whole-tile object graph.

    python3 stream_decode.py TILE.DAT --stats
    python3 stream_decode.py TILE.DAT --out crop.geojson --bbox 4,33,12,38
    python3 stream_decode.py TILE.DAT --out river.geojson --levels 1,2

`clarion_tile.read_tile` builds a Python object per record and peaks near 20 GB
on the 73 MB B40R050R, so it cannot open the 436 MB B48R060R.  This walks the
container through mmap (`tile_scan`), decodes section-1 background and
road-shape records one at a time, and writes GeoJSON incrementally.  `--stats`
counts features and reports a bbox without keeping features.

Names for road shapes are not attached in this path yet; the object decoder
(`ze0_decode.py`) does that because it can see the odd partner record.
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
import tile_scan
import ze0_decode
import ze0_roads


def dir_map(t):
    """{dir offset: (mesh_y, mesh_x)} for section 1."""
    out = {}
    for sid, lev, doff, nslots in t._dirs(section=1):
        h = struct.unpack_from('>6H', t.m, doff)
        x = h[4] - 65536 if h[4] > 32767 else h[4]
        out[doff] = (h[3], x)          # stored as mesh_x - 1024
    return out


def features(path, bbox=None, levels=None):
    with tile_scan.TileScan(path) as t:
        dirs = dir_map(t)
        for rec in t.records(section=1):
            if levels and rec.level not in levels:
                continue
            info = dirs.get(rec.dir_off)
            if info is None:
                continue
            y, x = info
            try:
                plain = rec.plain()
                w2 = struct.unpack_from('>H', plain, 4)[0]
            except Exception:
                continue
            if rec.k % 2 == 1:                     # background
                if w2 not in (0xfa, 0x19):
                    continue
                try:
                    parsed = clarion_bg.parse_record(plain)
                except Exception:
                    continue
                lon0, lat0, w, h = ze0_decode.parcel_origin(
                    rec.level, y, x, rec.slot, rec.k // 2)
                for layer, group in parsed['layers'].items():
                    if 'raw' in group:
                        continue
                    for sh in group['shapes']:
                        coords = [(lon0 + px / clarion_bg.UNITS * w,
                                   lat0 + py / clarion_bg.UNITS * h)
                                  for px, py in sh['pts']]
                        if not coords or len(coords) > 8192 or not ze0_decode.valid_coords(coords):
                            continue
                        if bbox and not any(bbox[0] <= q[0] <= bbox[2]
                                            and bbox[1] <= q[1] <= bbox[3] for q in coords):
                            continue
                        yield dict(level=rec.level, layer=layer, kind=group.get('kind', 0),
                                   type=sh['type'], coords=coords, road=False)
            else:                                   # road shapes
                if w2 != 0xfa:
                    continue
                try:
                    for f in ze0_decode._road_features(plain, rec.level, y, x,
                                                       rec.slot, rec.k // 2, {}):
                        if not ze0_decode.valid_coords(f['coords']):
                            continue
                        if bbox and not any(bbox[0] <= q[0] <= bbox[2]
                                            and bbox[1] <= q[1] <= bbox[3]
                                            for q in f['coords']):
                            continue
                        yield f
                except Exception:
                    continue


def write_geojson(path, feats):
    with open(path, 'w') as out:
        out.write('{"type":"FeatureCollection","features":[')
        first = True
        for f in feats:
            if not first:
                out.write(',')
            first = False
            g = dict(type='Point' if f['kind'] == 0 else
                     ('Polygon' if f['kind'] & 0x80 else 'LineString'),
                     coordinates=(list(f['coords'][0]) if f['kind'] == 0 else
                                  ([[list(c) for c in f['coords']]]
                                   if f['kind'] & 0x80 else [list(c) for c in f['coords']])))
            props = {k: v for k, v in f.items() if k != 'coords'}
            props['type'] = '0x%04x' % props['type']
            out.write(json.dumps(dict(type='Feature', geometry=g, properties=props),
                                 separators=(',', ':')))
        out.write(']}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('tile')
    ap.add_argument('--out', default='')
    ap.add_argument('--stats', action='store_true')
    ap.add_argument('--bbox', default='')
    ap.add_argument('--levels', default='')
    args = ap.parse_args()
    bbox = tuple(float(x) for x in args.bbox.split(',')) if args.bbox else None
    levels = {int(x) for x in args.levels.split(',') if x.strip()} or None
    if args.out:
        write_geojson(args.out, features(args.tile, bbox, levels))
        print('wrote', args.out)
    if args.stats or not args.out:
        import collections
        counts = collections.Counter()
        lo = [1e9, 1e9]; hi = [-1e9, -1e9]
        n = 0
        for f in features(args.tile, bbox, levels):
            n += 1
            counts[(f['level'], f['layer'], '0x%04x' % f['type'])] += 1
            for x, y in f['coords']:
                lo[0] = min(lo[0], x); hi[0] = max(hi[0], x)
                lo[1] = min(lo[1], y); hi[1] = max(hi[1], y)
        print('%s: %d features' % (args.tile, n))
        for k, v in sorted(counts.items()):
            print('  level %d layer %-3d type %s: %d' % (k[0], k[1], k[2], v))
        if n:
            print('  bbox lon %.4f..%.4f lat %.4f..%.4f' % (lo[0], hi[0], lo[1], hi[1]))


if __name__ == '__main__':
    main()
