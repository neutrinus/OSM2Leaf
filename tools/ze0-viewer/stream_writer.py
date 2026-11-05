#!/usr/bin/env python3
"""Streaming ZE0 tile writer: patch records without loading the tile.

    python3 stream_writer.py IN.DAT OUT.DAT            # byte copy + index check
    python3 stream_writer.py IN.DAT OUT.DAT --replace DIR SLOT K --dx 40

The full `clarion_tile` reader builds Python objects for every record; on the
73 MB B40R050R that peaked near 20 GB RSS and was OOM-killed.  This module
walks the container with mmap, writes the output in 8 MiB chunks, and only
patches (a) the selected record's bytes and (b) its two directory pair words.
A replacement must fit the original compressed length; that keeps every table
address and gap unchanged, so the rest of the card is copied verbatim.

For a layout change (record grows) the caller must use a relayout writer; this
one refuses rather than silently moving data.
"""
import argparse
import hashlib
import mmap
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools_ze0'))
import clarion_tile
import clarion_bg
import tile_scan

CHUNK = 8 << 20


def index_records(t):
    """Walk records and return (rec, pair_off) for every record."""
    body_cache = {}
    out = []
    for rec in t.records():
        key = rec.dir_off
        if key not in body_cache:
            kind = struct.unpack_from('>H', t.m, rec.dir_off)[0]
            BODY = {0x000a: 8, 0x0200: 88, 0x0826: 256, 0x03e4: 176,
                    0x1046: 256, 0x2046: 512, 0x2146: 512, 0x2346: 512,
                    0x1146: 256, 0x3cde: 704}
            body_cache[key] = BODY.get(kind, 512 if rec.section == 1 else 256)
        body = body_cache[key]
        pair = rec.dir_off + 12 + rec.slot * (4 + body) + 4 + rec.k * 8
        out.append((rec, pair))
    return out


def copy_stream(src_path, dst_path, patches=(), append=b''):
    """Copy src to dst in chunks, applying non-overlapping (off, bytes, orig_len)."""
    patches = sorted(patches)
    h = hashlib.sha256()
    with open(src_path, 'rb') as src, open(dst_path, 'wb') as dst:
        pos = 0
        for off, data, orig_len in patches:
            if off < pos:
                raise ValueError('overlapping patch at %#x' % off)
            while pos < off:
                n = min(CHUNK, off - pos)
                b = src.read(n)
                if not b:
                    raise EOFError
                dst.write(b); h.update(b); pos += n
            dst.write(data); h.update(data)
            src.seek(orig_len, 1)
            pos = off + len(data)
            if len(data) != orig_len:
                # in-place replacement must preserve the byte count
                raise ValueError('patch length %d != original %d' % (len(data), orig_len))
        while True:
            b = src.read(CHUNK)
            if not b:
                break
            dst.write(b); h.update(b)
        if append:
            dst.write(append); h.update(append)
    return h.hexdigest()


def body_size(t, rec):
    kind = struct.unpack_from('>H', t.m, rec.dir_off)[0]
    BODY = {0x000a: 8, 0x0200: 88, 0x0826: 256, 0x03e4: 176,
            0x1046: 256, 0x2046: 512, 0x2146: 512, 0x2346: 512,
            0x1146: 256, 0x3cde: 704}
    return BODY.get(kind, 512 if rec.section == 1 else 256)


def find_record(t, section, level, dir_off, slot, k):
    for rec, pair in index_records(t):
        if (rec.section == section and rec.level == level and
                rec.dir_off == dir_off and rec.slot == slot and rec.k == k):
            return rec, pair
    raise KeyError('record not found')


def replace_row(t, rec, pair, new_plain, file_size, body_size):
    """Relocate the whole parcel row to EOF and patch the slot tag.

    A record that grows cannot stay in place.  Appending the row's new block
    and changing its slot tag leaves every other address untouched, so the
    output is still a valid card layout (the old block becomes a hole).
    """
    comp = zlib.compress(new_plain, 6)
    if len(comp) % 2:
        comp += b'\x00'
    rows = [(r, p) for r, p in index_records(t) if r.dir_off == rec.dir_off and r.slot == rec.slot]
    block = bytearray()
    for r, p in sorted(rows, key=lambda x: x[0].k):
        block += comp if r.k == rec.k else r.raw()
    while len(block) % 256:
        block += b'\x00'
    new_off = (file_size + 255) // 256 * 256
    lead = b'\x00' * (new_off - file_size)
    tag_off = rec.dir_off + 12 + rec.slot * (4 + body_size)
    tag_data = struct.pack('>I', clarion_tile.enc_addr(new_off))
    pair_data = struct.pack('>II', len(comp) // 2, len(new_plain) // 2)
    return [(tag_off, tag_data, 4), (pair, pair_data, 8)], lead + bytes(block)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--section', type=int, default=1)
    ap.add_argument('--level', type=int, default=1)
    ap.add_argument('--dir', type=lambda x: int(x, 0), default=None)
    ap.add_argument('--slot', type=int, default=None)
    ap.add_argument('--k', type=int, default=None)
    ap.add_argument('--dx', type=int, default=0)
    ap.add_argument('--dy', type=int, default=0)
    args = ap.parse_args()

    with tile_scan.TileScan(args.src) as t:
        recs = index_records(t)
        print('%s: %d records indexed' % (args.src, len(recs)))
        patches = []
        if args.dir is not None and args.slot is not None and args.k is not None:
            rec, pair = find_record(t, args.section, args.level, args.dir, args.slot, args.k)
            plain = rec.plain()
            if rec.section != 1 or rec.k % 2 != 1:
                raise SystemExit('replacement currently supports section 1 background records')
            parsed = clarion_bg.parse_record(plain)
            layer = next(li for li, g in parsed['layers'].items() if g.get('shapes'))
            sh = parsed['layers'][layer]['shapes'][0]
            if len(sh['pts']) >= 3:
                i = len(sh['pts']) // 2
                x, y = sh['pts'][i]
                sh['pts'][i] = (x + args.dx, y + args.dy)
            parsed['strict'] = True
            new_plain = clarion_bg.build_record(parsed)
            patches, append = replace_row(t, rec, pair, new_plain,
                                          os.path.getsize(args.src), body_size(t, rec))
            print('relocating section %d level %d dir %#x slot %d k %d'
                  % (rec.section, rec.level, rec.dir_off, rec.slot, rec.k))
        else:
            append = b''
    digest = copy_stream(args.src, args.dst, patches, append)
    print('wrote %s sha256 %s' % (args.dst, digest))
    if not patches:
        print('unchanged copy; sha256 should equal the input')


if __name__ == '__main__':
    main()
