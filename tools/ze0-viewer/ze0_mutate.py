#!/usr/bin/env python3
"""Synthesize one small change in a ZE0 tile and write a new tile.

    python3 ze0_mutate.py IN.DAT OUT.DAT [--level 1] [--dx 40] [--dy 0]

Picks the first background (odd-pair) record of the requested level, shifts
every point of its first shape by (dx, dy) parcel units, rebuilds the record,
recompresses it, updates the directory pair and rewrites the whole container.
A 2048-unit parcel is 0.0208 deg of latitude at level 1, so 40 units is about
130 m: visible in a diff, harmless to the rest of the file.

This is a harness self-test, not a map editor: it proves the decoder, the
record builder and the container writer agree on a change we made ourselves.
"""
import argparse
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools_ze0'))

import clarion_bg
import clarion_tile


def first_background(tile, level):
    for sec in tile['sections']:
        if sec['id'] != 1:
            continue
        for lvl in sec['levels']:
            if lvl['level'] != level:
                continue
            for d in lvl['dirs']:
                for row, slot in sorted(d['slots'].items()):
                    for rec in slot['recs']:
                        if rec['k'] % 2 == 1 and clarion_tile.is_zlib(rec['raw']):
                            return d, slot, rec
    raise SystemExit('no background record at level %d' % level)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--level', type=int, default=1)
    ap.add_argument('--dx', type=int, default=40)
    ap.add_argument('--dy', type=int, default=0)
    args = ap.parse_args()

    data = open(args.src, 'rb').read()
    tile = clarion_tile.read_tile(data)
    d, slot, rec = first_background(tile, args.level)

    plain = zlib.decompress(rec['raw'])
    parsed = clarion_bg.parse_record(plain)
    layer = next(li for li, g in parsed['layers'].items() if 'shapes' in g and g['shapes'])
    shape = next(g['shapes'][0] for g in parsed['layers'].values()
                 if 'shapes' in g and len(g['shapes'][0]['pts']) >= 3)
    old = list(shape['pts'])
    i = len(old) // 2
    x, y = old[i]
    shape['pts'] = list(old)
    shape['pts'][i] = (min(2047, max(0, x + args.dx)),
                       min(2047, max(0, y + args.dy)))
    new_plain = clarion_bg.build_record(parsed)

    comp = zlib.compress(new_plain, 6)
    if len(comp) % 2:
        comp += b'\x00'          # odd-length streams are padded to a word
    rec['raw'] = comp
    rec['words'] = len(new_plain) // 2
    assert len(new_plain) % 2 == 0

    # directory pair k is (compressed words, inflated words)
    body = bytearray(slot['body'])
    struct.pack_into('>II', body, rec['k'] * 8, len(comp) // 2, len(new_plain) // 2)
    slot['body'] = bytes(body)

    out = clarion_tile.write_tile(tile)
    open(args.dst, 'wb').write(out)

    # verify: the new file must round-trip and decode to the shifted point
    again = clarion_tile.read_tile(out)
    assert clarion_tile.write_tile(again) == out, 'mutated tile does not round-trip'
    print('wrote %s (%d bytes, was %d)' % (args.dst, len(out), len(data)))
    print('shifted record level %d dir %d/%d row %d k %d layer %d: vertex %d %s -> %s'
          % (args.level, d['y'], d['x'], 0, rec['k'], layer, i, old[i],
             shape['pts'][i]))


if __name__ == '__main__':
    main()
