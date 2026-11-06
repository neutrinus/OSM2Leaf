#!/usr/bin/env python3
"""ind_mutate.py - build an offline mutation matrix for a real .ind file.

Writes ONLY new .ind variants into an output directory; it never touches the
source .ind/.cmp or anything in the repository.  Pair each variant with the
ORIGINAL .cmp on a spare card.

Usage:
  python3 ind_mutate.py \
      --ind /home/marek/projekty/leafre-work/root/REFER001/ADDRE001.DAT.ind \
      --out ./mut

The default sample (ADDRE001.DAT.ind) is 24 bytes:
  uncompressed 0x13600, compressed 0xbed4, count 2,
  chunk_size 0x10000, offsets [0x0, 0x8a17]
The .cmp has zlib headers 78 9c at 0x0 and 0x8a17.

This tool never recompresses: it only rewrites the 16-byte index and the
offset table, and pairs with the ORIGINAL .cmp.  A non-stock zlib (zlib-ng)
therefore cannot affect the variants; on such a build the tool says so once
through ``tools/zlibinfo.py``.
"""
import argparse
import os
import struct

import zlibinfo

DEFAULT_IND = '/home/marek/projekty/leafre-work/root/REFER001/ADDRE001.DAT.ind'


def read_ind(path):
    d = bytearray(open(path, 'rb').read())
    u, comp, n, cs = struct.unpack_from('<4I', d, 0)
    return d, u, comp, n, cs


def save(out, name, d):
    p = os.path.join(out, name + '.ind')
    with open(p, 'wb') as f:
        f.write(d)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ind', default=DEFAULT_IND)
    ap.add_argument('--out', default='mut')
    args = ap.parse_args()

    zlibinfo.note_if_nonstock(
        tool='ind_mutate.py',
        note='the variants reuse the ORIGINAL .cmp, so the zlib build does '
             'not affect them; no byte-identity claim is made here',
    )

    src, u, comp, n, cs = read_ind(args.ind)
    os.makedirs(args.out, exist_ok=True)
    rows = []

    def emit(name, d, edit, hypothesis):
        save(args.out, name, d)
        rows.append((name, edit, hypothesis))

    # 1/2: chunk_size
    d = bytearray(src)
    struct.pack_into('<I', d, 0x0c, 0x20000)
    emit('size_20000', d, 'dword @0x0C = 0x00020000',
         'reject => firmware compares chunk_size to 0x10000; accept => it uses the '
         'field only as an output buffer size or ignores it')

    d = bytearray(src)
    struct.pack_into('<I', d, 0x0c, 0x8000)
    emit('size_8000', d, 'dword @0x0C = 0x00008000',
         'reject/partial => output buffer is sized from chunk_size; accept+correct '
         '=> reader loops until stream end and ignores chunk_size')

    # 3: chunk_count + 1, append an offset == compressed_size (zero-length stream)
    d = bytearray(src)
    struct.pack_into('<I', d, 0x08, n + 1)
    d.extend(struct.pack('<I', comp))
    emit('count_p1', d, 'dword @0x08 += 1; append u32 offset = compressed_size',
         'reject => count is trusted and the extra stream is opened (zlib error); '
         'accept => count is ignored or bounds-checked against uncompressed_size')

    # 4: chunk_count - 1, drop the last offset
    if n >= 2:
        d = bytearray(src[:16 + 4 * (n - 1)])
        struct.pack_into('<I', d, 0x08, n - 1)
        emit('count_m1', d, 'dword @0x08 -= 1; truncate last offset',
             'reject => final size == uncompressed_size is checked; accept+truncated '
             'map => count is trusted and no total-size check exists')

    # 5/6: shift the second chunk offset by -1 / +1
    if n >= 2:
        off_last = struct.unpack_from('<I', src, 16 + 4 * (n - 1))[0]

        d = bytearray(src)
        struct.pack_into('<I', d, 16 + 4 * (n - 1), off_last - 1)
        emit('off_last_m1', d, 'last chunk_offset -= 1',
             'reject => reader seeks exactly by the index and feeds a non-78 9c byte '
             'to inflate; accept => reader scans forward for 78 9c')

        d = bytearray(src)
        struct.pack_into('<I', d, 16 + 4 * (n - 1), off_last + 1)
        emit('off_last_p1', d, 'last chunk_offset += 1',
             'same discriminator as off_last_m1 (header at +1 is 0x9c, not 0x78)')

    # 7: first chunk offset != 0
    d = bytearray(src)
    struct.pack_into('<I', d, 0x10, 1)
    emit('off0_1', d, 'chunk_offset[0] = 1',
         'reject => chunk 0 is read at offset[0]; accept => chunk 0 is always read at 0 '
         '(index 0 special-cased)')

    # 8: overlap the last chunk with the previous one
    if n >= 2:
        d = bytearray(src)
        struct.pack_into('<I', d, 16 + 4 * (n - 1), 0)
        emit('off_last_0', d, 'last chunk_offset = 0',
             'reject => the reader trusts the offset even when it overlaps chunk 0; '
             'accept => it validates monotonic offsets')

    # manifest
    man = os.path.join(args.out, 'MANIFEST.txt')
    with open(man, 'w') as f:
        f.write('source: %s\n' % os.path.abspath(args.ind))
        f.write('uncompressed=%#x compressed=%#x count=%d chunk_size=%#x\n\n'
                % (u, comp, n, cs))
        f.write('Pair every variant .ind with the ORIGINAL .cmp on a spare card.\n'
                'Each row: variant | edit | expected discriminator\n\n')
        for name, edit, hyp in rows:
            f.write('%-14s | %-52s | %s\n' % (name, edit, hyp))
    print('wrote %d variants + MANIFEST.txt to %s' % (len(rows), args.out))
    for name, edit, _ in rows:
        print('  %-14s %s' % (name, edit))


if __name__ == '__main__':
    main()
