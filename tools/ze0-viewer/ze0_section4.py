#!/usr/bin/env python3
"""Section-4 administrative/place-name index.

    python3 ze0_section4.py TILE.DAT [OUT.geojson]

ZE0 section 4 (type 0x93, directory kind 0x1146, 256-byte bodies) is not
geometry.  Each record starts with the level-1 parcel code, word 2 = 0x0009,
word 8 = ISO 3166 numeric country, then a packed list of administrative names
as NUL-separated ASCII (e.g. ``0=RODOS``, ``0=ARCHIPOLI``).  The record is
emitted as a point at the parcel centre with ``names`` and ``country``.
"""
import json
import os
import re
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools_ze0'))
import clarion_tile
import clarion_bg

ASCII = re.compile(rb'[ -~]{3,}')


def parcel_from_code(w0, w1):
    """Level-1 absolute (row, col); the section-4 x base is 512 less than the tile."""
    row = ((w0 >> 8) & 0xff) * 64 + ((w0 >> 4) & 0xf) * 4 + (w0 & 3)
    col = ((w1 >> 8) & 0xff) * 64 + ((w1 >> 4) & 0xf) * 4 + (w1 & 3)
    return row, col


def names_from(plain):
    # The packed index uses ``0=NAME`` / ``1=NAME`` prefixes without a NUL
    # between adjacent names (e.g. ``LINDOS0=RODOS``).  Split on those
    # prefixes, then on control bytes.
    text = ''.join(chr(b) if 32 <= b < 127 else '\n' for b in plain)
    out = []
    for part in re.split(r'[0-9]=', text):
        for line in part.split('\n'):
            s = line.strip(' :,;')
            if len(s) >= 3 and s not in out:
                out.append(s)
    return out


def records(path):
    data = open(path, 'rb').read()
    tile = clarion_tile.read_tile(data)
    for sec in tile['sections']:
        if sec['id'] != 4:
            continue
        for lvl in sec['levels']:
            for d in lvl['dirs']:
                mesh_x = (d['x'] - 65536 if d['x'] > 32767 else d['x']) + 1024
                for slot, s in d['slots'].items():
                    for rec in s['recs']:
                        plain = (zlib.decompress(rec['raw'])
                                 if clarion_tile.is_zlib(rec['raw']) else rec['raw'])
                        if len(plain) < 20:
                            continue
                        w0, w1, w2 = struct.unpack_from('>HHH', plain, 0)
                        country = struct.unpack_from('>H', plain, 16)[0]
                        row, col = parcel_from_code(w0, w1)
                        # cross-check against the directory; section-4 x uses a 512 offset
                        if row // 32 != d['y'] or col // 32 + 512 != mesh_x:
                            row, col = d['y'] * 32 + slot, (mesh_x - 512) * 32 + rec['k']
                        lon = (mesh_x - 924) + (col % 32) * (1 / 32) + 0.5 / 32
                        lat = d['y'] / 1.5 + slot * (1 / 48) + 0.5 / 48
                        yield dict(level=1, layer=400, kind=0, type=0x0009,
                                   section4=True, country=country,
                                   names=names_from(plain), coords=[(lon, lat)],
                                   row=row, col=col,
                                   dir_y=d['y'], dir_x=mesh_x, slot=slot, k=rec['k'])


def to_geojson(recs):
    feats = []
    for r in recs:
        props = {k: v for k, v in r.items() if k != 'coords'}
        props['type'] = '0x%04x' % props['type']
        feats.append(dict(type='Feature',
                          geometry=dict(type='Point', coordinates=list(r['coords'][0])),
                          properties=props))
    return dict(type='FeatureCollection', features=feats)


def main():
    path = sys.argv[1]
    recs = list(records(path))
    print('%s: %d section-4 records, %d names'
          % (path, len(recs), sum(len(r['names']) for r in recs)))
    for r in recs[:8]:
        print('  parcel row %d col %d country %d: %s'
              % (r['row'], r['col'], r['country'], ', '.join(r['names'][:4])))
    if len(sys.argv) > 2:
        with open(sys.argv[2], 'w') as fh:
            json.dump(to_geojson(recs), fh, separators=(',', ':'))


if __name__ == '__main__':
    main()
