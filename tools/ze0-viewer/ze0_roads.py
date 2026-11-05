#!/usr/bin/env python3
"""ZE0 road-shape record (section 1, even pair) reader and builder.

The record shares the background header (parcel code, word 2 = 0x00fa,
0x347a 0x2aef) but its geometry unit is a layer table of (dword offset,
shape count) pairs and self-describing shapes.  Each shape is a chain of
points; link headers (style/value/id) are interleaved between link runs.

    python3 ze0_roads.py TILE.DAT          # census + rebuild check
    python3 ze0_roads.py TILE.DAT --dump   # first record as words

The parser is deliberately tolerant: points are recognised by the 0x1000
flag, link headers by the absence of it.  That is enough to draw the road
alignments; it does not yet name a link or apply the one-way/speed words.
"""
import argparse
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools_ze0'))
import clarion_tile
import clarion_bg


def _u16(p, off):
    return struct.unpack_from('>H', p, off)[0]


def parse_shape(p, q, level2=False):
    """One shape at byte q; returns (next_q, shape dict).

    Link headers have known positions: after the start node, then after each
    link's end node (y has 0x0800; y with 0x2000 also carries a style word).
    Points between headers carry 0x1000 in x.  Parsing headers explicitly
    keeps a style word such as 0x1031 from being mistaken for a point.
    """
    ln = _u16(p, q)
    end = min(q + 2 * ln, len(p))
    truncated = q + 2 * ln > len(p)
    nwords = min(11, ln, max(0, (len(p) - q) // 2))
    w = [_u16(p, q + 2 * i) for i in range(nwords)]
    npts = w[1] & 0x7fff if len(w) > 1 else 0
    start = ((w[7] & 0x07ff, w[8] & 0x07ff) if len(w) >= 9 else (0, 0))
    i = q + 2 * (9 if level2 else 9)
    style = lid = None
    # first header: style, value, id (level 1) or style, id (level 2)
    if level2:
        if i + 4 <= end:
            style, lid = _u16(p, i), _u16(p, i + 2); i += 4
    else:
        if i + 6 <= end:
            style, _value, lid = _u16(p, i), _u16(p, i + 2), _u16(p, i + 4); i += 6
    lines, links = [], []
    cur = [start]
    while i + 4 <= end:
        a, b = _u16(p, i), _u16(p, i + 2)
        if a & 0x1000:                    # point inside a link
            cur.append((a & 0x07ff, b & 0x07ff))
            i += 4
            continue
        # end node; finish this link
        pt = (a & 0x07ff, b & 0x07ff)
        cur.append(pt)
        if len(cur) >= 2:
            lines.append(list(cur)); links.append(dict(style=style, id=lid))
        cur = [pt]
        i += 4                            # consume the end-node pair
        if b & 0x2000:                    # a style follows
            if i + 6 > end:
                break
            style, _value, lid = _u16(p, i), _u16(p, i + 2), _u16(p, i + 4)
            i += 6
        else:
            if i + 4 > end:
                break
            _value, lid = _u16(p, i), _u16(p, i + 2)
            i += 4
    if len(cur) >= 2:
        lines.append(list(cur)); links.append(dict(style=style, id=lid))
    pts = [pt for line in lines for pt in line]
    return end, dict(words=w, npoints=npts, points=pts, lines=lines, links=links,
                     start=start, _raw=p[q:end], _truncated=truncated)


def parse_record(plain):
    """Parse one road-shape record into header, layers, shapes and tail."""
    hdr = list(struct.unpack_from('>22H', plain, 0))
    level2 = hdr[3] == 0xffff and hdr[4] == 0xffff
    gi = 7 if hdr[9] in (0xffff, 0) else 9
    geo_off, geo_len = hdr[gi], hdr[gi + 1]
    base = 4 * geo_off
    if level2:
        # eleven pairs from word 22, no count word; shapes at dword 11
        nlayers = 11
        pairs = [struct.unpack_from('>HH', plain, 44 + 4 * k) for k in range(11)]
    else:
        nlayers = _u16(plain, base)
        pairs = [struct.unpack_from('>HH', plain, base + 2 + 4 * k) for k in range(12)]
    layers = {}
    skipped = False
    for layer, (off, count) in enumerate(pairs):
        if off == 0xffff or count > 2048 or off == 0:
            if off != 0xffff:
                skipped = True
            continue
        q = base + 4 * off
        if q >= len(plain):
            continue
        shapes = []
        for _ in range(count):
            if q + 2 > len(plain):
                break
            q, sh = parse_shape(plain, q, level2)
            shapes.append(sh)
        layers[layer] = shapes
    tail_at = 4 * hdr[17] if hdr[17] not in (0xffff, 0) and hdr[18] else None
    tail = plain[tail_at:] if tail_at is not None and tail_at <= len(plain) else b''
    return dict(hdr=hdr, gi=gi, base=base, geo_len=geo_len, nlayers=nlayers,
                head=0 if level2 else _u16(plain, base), level2=level2,
                layers=layers, tail=tail, plain=plain,
                truncated=skipped or any(sh.get('_truncated') for v in layers.values() for sh in v))


def _build_shape(sh, level2=False):
    """A shape's original bytes, or a minimal valid shape from its points."""
    if sh.get('_raw'):
        return sh['_raw']
    pts = sh.get('points') or []
    if not pts:
        return b''
    pts = [(p[0], p[1]) for p in pts]
    link = [0x201e, 0, 1] if not level2 else [0x201e, 1]
    w = [0, 0x8000 | len(pts), 0x8000, 0x0140, 0xffff, 0, 0,
         pts[0][0], pts[0][1]]
    w[0] = 9 + len(link) + 2 * max(0, len(pts) - 1)
    out = bytearray(struct.pack('>9H', *w))
    out += struct.pack('>%dH' % len(link), *link)
    for i, (x, y) in enumerate(pts[1:]):
        out += struct.pack('>HH', (0x5000 if i == 0 else 0x1000) | x, y)
    return bytes(out)


def build_record(rec):
    """Rebuild a road-shape record; unchanged shapes are emitted verbatim."""
    if rec.get('truncated') and rec.get('plain'):
        return rec['plain']          # shape ran past the record; keep the source
    hdr = list(rec['hdr'])
    layers = rec['layers']
    level2 = rec.get('level2', False)
    present = [l for l in range(12) if layers.get(l)]
    if level2:
        geo = bytearray()
        table_dwords = 11
        pos = table_dwords
    else:
        geo = bytearray(struct.pack('>H', rec.get('head', 0x0a)))
        table_dwords = 13
        pos = table_dwords
    offsets = {}
    bodies = {}
    for layer in present:
        shapes = layers[layer]
        b = bytearray(b''.join(_build_shape(sh, level2) for sh in shapes))
        while len(b) % 4:
            b += b'\x00'
        bodies[layer] = bytes(b)
        offsets[layer] = pos
        pos += len(bodies[layer]) // 4
    if level2:
        for l in range(11):
            geo += struct.pack('>HH', offsets.get(l, 0xffff), len(layers.get(l, [])))
    else:
        for l in range(12):
            geo += struct.pack('>HH', offsets.get(l, 0xffff), len(layers.get(l, [])))
        geo += b'\x00\x00'                 # pad to a dword boundary
    for layer in present:
        geo += bodies[layer]
    while len(geo) % 4:
        geo += b'\x00'
    hdr[7], hdr[8] = 11, len(geo) // 4
    out = bytearray(struct.pack('>22H', *hdr))
    out += geo
    if rec['tail']:
        hdr[17], hdr[18] = len(out) // 4, len(rec['tail']) // 4
        struct.pack_into('>22H', out, 0, *hdr)
        out += rec['tail']
    return bytes(out)


def make_record(points_by_layer, level=1, parcel=(0, 0)):
    """Build a new road-shape record from {layer: [(x, y), ...]} in parcel units."""
    level2 = level == 2
    hdr = [parcel[0], parcel[1], 0x00fa,
           0xffff if level2 else 0x347a, 0xffff if level2 else 0x2aef,
           0, 0, 11, 0, 0xffff, 0, 0xffff, 0, 0xffff, 0, 0xffff, 0, 0,
           0, 0, 0x17c, 0]
    layers = {layer: [dict(points=list(pts), _raw=None)] for layer, pts in points_by_layer.items()}
    return build_record(dict(hdr=hdr, level2=level2, head=0x0a, layers=layers, tail=b''))


def census(path):
    d = open(path, 'rb').read()
    t = clarion_tile.read_tile(d)
    stats = dict(records=0, parsed=0, shape=0, points=0, rebuilt=0, bad=0)
    for sec in t['sections']:
        if sec['id'] != 1:
            continue
        for L in sec['levels']:
            for D in L['dirs']:
                for slot in D['slots'].values():
                    for r in slot['recs']:
                        if r['k'] % 2 == 0:
                            stats['records'] += 1
                            plain = zlib.decompress(r['raw']) if clarion_tile.is_zlib(r['raw']) else r['raw']
                            try:
                                rec = parse_record(plain)
                                stats['parsed'] += 1
                                stats['shape'] += sum(len(v) for v in rec['layers'].values())
                                stats['points'] += sum(len(sh['points']) for v in rec['layers'].values() for sh in v)
                                b = build_record(rec)
                                if b == plain:
                                    stats['rebuilt'] += 1
                                else:
                                    stats['bad'] += 1
                            except Exception:
                                stats['bad'] += 1
    print(path, stats)
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('tile')
    ap.add_argument('--dump', action='store_true')
    args = ap.parse_args()
    if args.dump:
        d = open(args.tile, 'rb').read()
        t = clarion_tile.read_tile(d)
        for sec in t['sections']:
            if sec['id'] != 1:
                continue
            for L in sec['levels']:
                for D in L['dirs']:
                    for slot in D['slots'].values():
                        for r in slot['recs']:
                            if r['k'] % 2 == 0:
                                p = zlib.decompress(r['raw']) if clarion_tile.is_zlib(r['raw']) else r['raw']
                                print('dir %#x slot %d k %d plain %d' % (D['off'], slot['tag'], r['k'], len(p)))
                                print([hex(x) for x in struct.unpack_from('>22H', p, 0)])
                                rec = parse_record(p)
                                print('layers', {k: len(v) for k, v in rec['layers'].items()})
                                return
    census(args.tile)


if __name__ == '__main__':
    main()
