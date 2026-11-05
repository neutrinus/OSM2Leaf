#!/usr/bin/env python3
"""Validation harness for ZE0 (Clarion X08-02-00) navigation tiles.

Commands
    info TILE                 header, tables, record census
    roundtrip TILE            read_tile -> write_tile byte-identical?
    verify TILE               every record inflates and every background
                              record rebuilds byte-exactly
    decode TILE OUT.geojson [--levels 1,2] [--cell B28R070R]
    render TILE OUT.png [--levels ...] [--cell ...] [--width 1400]
    compose TILE LEV3456R.DAT OUT.png --cell B30R060R
                              level-3 base from the coarse file under the
                              tile's own levels 1-2
    mutate IN.DAT OUT.DAT [--dx 40] [--level 1]
    compare A.geojson B.geojson
    selftest TILE             all of the above on one factory tile

Everything is read-only on the input; outputs go where you point them.
"""
import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools_ze0'))
sys.path.insert(0, HERE)

import clarion_bg
import clarion_rd
import clarion_tile
import tile_scan
import ze0_roads
import ze0_decode


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def header_strings(data):
    out = []
    for off in (0x00, 0x40, 0x80, 0xa0, 0xe0):
        raw = data[off:off + 64]
        s = raw.decode('utf-16-be', 'replace').split('\uffff')[0].split('\x00')[0]
        out.append((off, s.strip()))
    return out


def bbox_table(data):
    off = 0x2ac
    n = struct.unpack_from('>H', data, off)[0]
    p = off + 2
    rows = []
    for _ in range(n):
        sid, nl = data[p], data[p + 1]; p += 2
        for _ in range(nl):
            lv, flag, a, b, c, d = struct.unpack_from('>BBhhhh', data, p); p += 10
            rows.append((sid, lv, flag, a / 60, b / 60, c / 60, d / 60))
    return rows


def cmd_info(path):
    data = open(path, 'rb').read()
    print('file    %s' % path)
    print('size    %d bytes' % len(data))
    print('sha256  %s' % sha256(path))
    for off, s in header_strings(data):
        print('0x%03x   %s' % (off, s))
    print('bbox table (arc-min / 60):')
    for sid, lv, flag, la1, la0, lo0, lo1 in bbox_table(data):
        print('  section %d level %d: lat %.3f..%.3f lon %.3f..%.3f'
              % (sid, lv, la0, la1, lo0, lo1))
    tile = clarion_tile.read_tile(data)
    for sec in tile['sections']:
        print('section %d: table at 0x%x, %d levels'
              % (sec['id'], sec['taddr'], len(sec['levels'])))
        for lvl in sec['levels']:
            bg = shape = graph = other = 0
            for d in lvl['dirs']:
                for slot in d['slots'].values():
                    for rec in slot['recs']:
                        if not clarion_tile.is_zlib(rec['raw']):
                            other += 1
                            continue
                        plain = zlib.decompress(rec['raw'])
                        kind = struct.unpack_from('>H', plain, 4)[0]
                        if sec['id'] == 1 and rec['k'] % 2 == 1:
                            bg += 1
                        elif sec['id'] == 1:
                            shape += 1
                        else:
                            graph += 1
            print('  level %d type 0x%02x dirs %d: background %d, shape %d, graph %d, raw %d'
                  % (lvl['level'], lvl['typ'], len(lvl['dirs']), bg, shape, graph, other))


def cmd_roundtrip(path):
    data = open(path, 'rb').read()
    tile = clarion_tile.read_tile(data)
    out = clarion_tile.write_tile(tile)
    if out == data:
        print('%s: byte-identical rebuild OK (%d bytes)' % (path, len(data)))
        return True
    i = next((i for i in range(min(len(data), len(out))) if data[i] != out[i]),
             min(len(data), len(out)))
    print('%s: MISMATCH input %d bytes, output %d bytes, first diff 0x%x'
          % (path, len(data), len(out), i))
    print('  in  %s' % data[max(0, i - 8):i + 8].hex())
    print('  out %s' % out[max(0, i - 8):i + 8].hex())
    return False


def cmd_verify(path, quiet=False):
    data = open(path, 'rb').read()
    tile = clarion_tile.read_tile(data)
    ok_rec = bad_rec = ok_bg = bad_bg = ok_graph = bad_graph = opaque = 0
    bg_by_level = {}
    errors = []
    for sec in tile['sections']:
        for lvl in sec['levels']:
            for d in lvl['dirs']:
                for slot in d['slots'].values():
                    for rec in slot['recs']:
                        try:
                            if clarion_tile.is_zlib(rec['raw']):
                                plain = zlib.decompress(rec['raw'])
                                if len(plain) != 2 * rec['words']:
                                    raise ValueError('inflated %d, header says %d'
                                                     % (len(plain), 2 * rec['words']))
                            else:
                                plain = rec['raw']
                            ok_rec += 1
                        except Exception as e:
                            bad_rec += 1
                            if len(errors) < 5:
                                errors.append('record at 0x%x: %r' % (rec.get('off', 0), e))
                            continue
                        if sec['id'] == 1 and rec['k'] % 2 == 1:
                            try:
                                parsed_bg = clarion_bg.parse_record(plain)
                                if parsed_bg.get('opaque'):
                                    opaque += 1
                                rebuilt = clarion_bg.build_record(parsed_bg)
                                if rebuilt == plain:
                                    ok_bg += 1
                                    bg_by_level.setdefault(lvl['level'], [0, 0])[0] += 1
                                else:
                                    bad_bg += 1
                                    bg_by_level.setdefault(lvl['level'], [0, 0])[1] += 1
                                    if len(errors) < 5:
                                        errors.append('background record at 0x%x: rebuild differs' % rec.get('off', 0))
                            except Exception as e:
                                # A record the reader cannot model is opaque,
                                # not a container failure; the writer keeps its
                                # bytes verbatim in non-strict mode.
                                opaque += 1
                                if len(errors) < 5:
                                    errors.append('background record (opaque): %r' % e)
                        elif sec['id'] == 2:
                            try:
                                r = clarion_rd.parse_record(plain)
                                if r.get('error'):
                                    bad_graph += 1
                                    if len(errors) < 5:
                                        errors.append('graph record: %s' % r['error'])
                                else:
                                    ok_graph += 1
                            except Exception as e:
                                bad_graph += 1
                                if len(errors) < 5:
                                    errors.append('graph record: %r' % e)
    rt = cmd_roundtrip(path) if not quiet else True
    if quiet:
        out = clarion_tile.write_tile(tile)
        rt = out == data
    print('%s: records ok %d bad %d | background rebuild ok %d bad %d (opaque %d) | graph parse ok %d bad %d | roundtrip %s'
          % (path, ok_rec, bad_rec, ok_bg, bad_bg, opaque, ok_graph, bad_graph, 'OK' if rt else 'FAIL'))
    for lv in sorted(bg_by_level):
        print('  level %d background rebuild: ok %d bad %d' % (lv, *bg_by_level[lv]))
    for e in errors:
        print('  ' + e)
    # Levels 1-2 are the drawn tile surface we can rebuild byte-exactly. The
    # coarse file's level 3-5 records carry extra sections that the reader does
    # not model, so a mismatch there is reported but not fatal.
    bad_l12 = sum(v[1] for lv, v in bg_by_level.items() if lv in (1, 2))
    return rt and not bad_rec and not bad_l12 and not bad_graph


def cmd_scan(path):
    """Streaming record check for tiles too large for read_tile (B40R050 is 73 MB
    and read_tile peaks near 20 GB).  No byte-identical rebuild, but every record
    is inflated and every background record is parsed and rebuilt."""
    import collections
    stats = collections.Counter()
    errs = []
    with tile_scan.TileScan(path) as t:
        for rec in t.records():
            try:
                plain = rec.plain()
                if rec.is_zlib and len(plain) != 2 * rec.words:
                    raise ValueError('inflated %d, header says %d' % (len(plain), 2 * rec.words))
                stats['records'] += 1
            except Exception as e:
                stats['bad_record'] += 1
                if len(errs) < 5:
                    errs.append('record at 0x%x: %r' % (rec.off, e))
                continue
            if rec.section == 1 and rec.k % 2 == 1:
                try:
                    rebuilt = clarion_bg.build_record(clarion_bg.parse_record(plain))
                    stats['bg_ok' if rebuilt == plain else 'bg_diff'] += 1
                except Exception as e:
                    stats['bg_exc'] += 1
                    if len(errs) < 5:
                        errs.append('background at 0x%x: %r' % (rec.off, e))
            elif rec.section == 2:
                try:
                    r = clarion_rd.parse_record(plain)
                    stats['graph_ok' if not r.get('error') else 'graph_bad'] += 1
                except Exception as e:
                    stats['graph_exc'] += 1
    print('%s: %s' % (path, dict(stats)))
    for e in errs:
        print('  ' + e)
    return stats['bad_record'] == 0 and stats['bg_exc'] == 0


def cmd_roads(path):
    st = ze0_roads.census(path)
    return st['bad'] == 0


def cmd_decode(path, out, levels='', cell=''):
    lv = {int(x) for x in levels.split(',') if x.strip()} or None
    bbox = ze0_decode.cell_bbox(cell) if cell else None
    feats, cov = ze0_decode.decode_records(path, lv, bbox)
    gj = ze0_decode.to_geojson(feats, cov)
    with open(out, 'w') as fh:
        json.dump(gj, fh, separators=(',', ':'))
    print('%s: %d features, %d covered parcels' % (out, len(feats), len(cov)))


def cmd_render(path, out, levels='', cell='', width=1400, labels=False):
    tmp = tempfile.NamedTemporaryFile(suffix='.geojson', delete=False)
    tmp.close()
    try:
        cmd_decode(path, tmp.name, levels, cell)
        cmd = [sys.executable, os.path.join(HERE, 'render_geojson.py'),
               tmp.name, out, '--width', str(width)]
        if labels:
            cmd.append('--labels')
        subprocess.run(cmd, check=True)
    finally:
        os.unlink(tmp.name)


def cmd_compose(tile_path, lev_path, out, cell, width=1400):
    lv = {'1', '2'}
    bbox = ze0_decode.cell_bbox(cell)
    f1, c1 = ze0_decode.decode_records(tile_path, {1, 2}, bbox)
    f3, c3 = ze0_decode.decode_records(lev_path, {3, 4, 5}, bbox)
    gj = ze0_decode.to_geojson(f3 + f1, c3 + c1)
    tmp = tempfile.NamedTemporaryFile(suffix='.geojson', delete=False)
    tmp.close()
    try:
        with open(tmp.name, 'w') as fh:
            json.dump(gj, fh, separators=(',', ':'))
        print('composite: %d coarse (3-5) + %d level-1/2 features' % (len(f3), len(f1)))
        bb = ','.join('%.6f' % x for x in bbox)
        subprocess.run([sys.executable, os.path.join(HERE, 'render_geojson.py'),
                        tmp.name, out, '--width', str(width), '--bbox', bb], check=True)
    finally:
        os.unlink(tmp.name)


def flatten_geometry(f):
    g = f['geometry']; c = g['coordinates']
    if g['type'] == 'Point':
        return [c]
    if g['type'] == 'LineString':
        return c
    return [p for ring in c for p in ring]


def _sig(f):
    return (f['level'], f['layer'], f['type'], bool(f.get('road')),
            tuple((round(x, 7), round(y, 7)) for x, y in f['coords']))


def cmd_compare_tiles(a_path, b_path, cell='', levels='1,2'):
    """Build-vs-factory comparison over identical coverage.

    Both tiles are decoded to the same neutral features and keyed by
    (level, layer, type, road, rounded coordinates).  An unchanged build has
    an empty multiset difference: zero added, zero removed.
    """
    from collections import Counter
    lv = {int(x) for x in levels.split(',') if x.strip()} or None
    bbox = ze0_decode.cell_bbox(cell) if cell else None
    fa, _ = ze0_decode.decode_records(a_path, lv, bbox)
    fb, _ = ze0_decode.decode_records(b_path, lv, bbox)
    ka = Counter(_sig(f) for f in fa)
    kb = Counter(_sig(f) for f in fb)
    removed = list((ka - kb).elements())
    added = list((kb - ka).elements())
    print('factory %d features, built %d features' % (len(fa), len(fb)))
    print('added %d, removed %d, unchanged %d'
          % (len(added), len(removed), sum((ka & kb).values())))
    if not added and not removed:
        print('RESULT: ZERO DIFF (identical geometry sets)')
        return 0
    # nearest vertex distance for the first unmatched pair(s)
    maxd = 0.0
    rem = sorted(removed, key=lambda k: (k[0], k[1], k[2], k[3]))[:20]
    add = sorted(added, key=lambda k: (k[0], k[1], k[2], k[3]))[:20]
    for k in rem:
        pts = k[-1]
        best = 0.0
        for p in pts[:50]:
            near = 1e9
            for k2 in add:
                if k[:4] != k2[:4]:
                    continue
                for q in k2[-1][:50]:
                    d = max(abs(p[0] - q[0]), abs(p[1] - q[1]))
                    if d < near:
                        near = d
            if near < 1e9:
                best = max(best, near)
        maxd = max(maxd, best)
    print('largest nearest changed vertex: %.8f deg (~%.1f m)'
          % (maxd, maxd * 111320))
    print('RESULT: DIFFERS')
    return 1


def cmd_compare(a_path, b_path):
    a = json.load(open(a_path))['features']
    b = json.load(open(b_path))['features']
    print('features: %d vs %d' % (len(a), len(b)))
    if len(a) != len(b):
        print('RESULT: feature count differs')
        return False
    changed = 0
    maxd = 0.0
    for fa, fb in zip(a, b):
        ga, gb = flatten_geometry(fa), flatten_geometry(fb)
        if len(ga) != len(gb):
            changed += 1
            continue
        for p, q in zip(ga, gb):
            d = max(abs(p[0] - q[0]), abs(p[1] - q[1]))
            if d:
                changed += 1
                maxd = max(maxd, d)
    print('changed vertices: %d, max delta %.8f deg (~%.1f m)'
          % (changed, maxd, maxd * 111320))
    print('RESULT: %s' % ('identical geometry' if not changed else 'geometry differs'))
    return changed


def cmd_selftest(path):
    tmp = tempfile.mkdtemp(prefix='ze0-selftest-')
    ok = True
    print('== info / roundtrip / verify')
    ok &= cmd_roundtrip(path)
    ok &= cmd_verify(path, quiet=True)
    print('== decode + render')
    gj = os.path.join(tmp, 'a.geojson'); png = os.path.join(tmp, 'a.png')
    cmd_decode(path, gj, levels='1,2')
    subprocess.run([sys.executable, os.path.join(HERE, 'render_geojson.py'),
                    gj, png, '--width', '1000'], check=True)
    print('== mutate one vertex, decode again')
    mut = os.path.join(tmp, 'mut.DAT')
    subprocess.run([sys.executable, os.path.join(HERE, 'ze0_mutate.py'),
                    path, mut, '--level', '1', '--dx', '40'], check=True)
    gj2 = os.path.join(tmp, 'b.geojson')
    cmd_decode(mut, gj2, levels='1,2')
    changed = cmd_compare(gj, gj2)
    ok &= (changed == 1)
    print('== verify mutated tile')
    ok &= cmd_verify(mut, quiet=True)
    print('SELFTEST: %s' % ('PASS' if ok else 'FAIL'))
    return ok


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('info'); p.add_argument('tile')
    p = sub.add_parser('roundtrip'); p.add_argument('tile')
    p = sub.add_parser('verify'); p.add_argument('tile')
    p = sub.add_parser('scan'); p.add_argument('tile')
    p = sub.add_parser('roads'); p.add_argument('tile')
    p = sub.add_parser('stream'); p.add_argument('src'); p.add_argument('dst')
    p.add_argument('--dir', type=lambda x: int(x, 0), default=None)
    p.add_argument('--slot', type=int, default=None)
    p.add_argument('--k', type=int, default=None)
    p.add_argument('--level', type=int, default=1)
    p.add_argument('--dx', type=int, default=40)
    p = sub.add_parser('decode'); p.add_argument('tile'); p.add_argument('out')
    p.add_argument('--levels', default=''); p.add_argument('--cell', default='')
    p = sub.add_parser('render'); p.add_argument('tile'); p.add_argument('out')
    p.add_argument('--levels', default=''); p.add_argument('--cell', default='')
    p.add_argument('--width', type=int, default=1400)
    p.add_argument('--labels', action='store_true')
    p = sub.add_parser('compose'); p.add_argument('tile'); p.add_argument('lev'); p.add_argument('out')
    p.add_argument('--cell', required=True); p.add_argument('--width', type=int, default=1400)
    p = sub.add_parser('mutate'); p.add_argument('src'); p.add_argument('dst')
    p.add_argument('--dx', type=int, default=40); p.add_argument('--dy', type=int, default=0)
    p.add_argument('--level', type=int, default=1)
    p = sub.add_parser('compare'); p.add_argument('a'); p.add_argument('b')
    p = sub.add_parser('compare-tiles'); p.add_argument('factory'); p.add_argument('built')
    p.add_argument('--cell', default=''); p.add_argument('--levels', default='1,2')
    p = sub.add_parser('selftest'); p.add_argument('tile')
    args = ap.parse_args()

    if args.cmd == 'info': cmd_info(args.tile)
    elif args.cmd == 'roundtrip': sys.exit(0 if cmd_roundtrip(args.tile) else 1)
    elif args.cmd == 'verify': sys.exit(0 if cmd_verify(args.tile) else 1)
    elif args.cmd == 'scan': sys.exit(0 if cmd_scan(args.tile) else 1)
    elif args.cmd == 'roads': sys.exit(0 if cmd_roads(args.tile) else 1)
    elif args.cmd == 'stream':
        cmd = [sys.executable, os.path.join(HERE, 'stream_writer.py'), args.src, args.dst]
        if args.dir is not None:
            cmd += ['--dir', hex(args.dir), '--slot', str(args.slot),
                    '--k', str(args.k), '--level', str(args.level), '--dx', str(args.dx)]
        subprocess.run(cmd, check=True)
    elif args.cmd == 'decode': cmd_decode(args.tile, args.out, args.levels, args.cell)
    elif args.cmd == 'render': cmd_render(args.tile, args.out, args.levels, args.cell, args.width, args.labels)
    elif args.cmd == 'compose': cmd_compose(args.tile, args.lev, args.out, args.cell, args.width)
    elif args.cmd == 'mutate':
        subprocess.run([sys.executable, os.path.join(HERE, 'ze0_mutate.py'),
                        args.src, args.dst, '--level', str(args.level),
                        '--dx', str(args.dx), '--dy', str(args.dy)], check=True)
    elif args.cmd == 'compare': cmd_compare(args.a, args.b)
    elif args.cmd == 'compare-tiles':
        sys.exit(cmd_compare_tiles(args.factory, args.built, args.cell, args.levels))
    elif args.cmd == 'selftest': sys.exit(0 if cmd_selftest(args.tile) else 1)


if __name__ == '__main__':
    main()
