#!/usr/bin/env python3
"""Solve a module's code->data delta from its literal pools.

For a code window, collect every literal-pool value that could be a data VA
(0x01000000..0x04000000).  For each candidate delta D (0x1000 grid) count how
many values map onto a *valid string start* in the image.  The correct delta is
the one where many independent literals land exactly on string starts; a wrong
delta lands on suffixes/bit noise.

Usage: solve_data_delta.py <image> <lo> <hi> [--top N]
"""
import struct
import sys


def main():
    path, lo, hi = sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3], 0)
    top = 8
    if '--top' in sys.argv:
        top = int(sys.argv[sys.argv.index('--top') + 1])
    data = open(path, 'rb').read()

    def w(a):
        return struct.unpack_from('<H', data, a)[0]

    def dw(a):
        return struct.unpack_from('<I', data, a)[0]

    vals = set()
    for a in range(lo, hi - 2, 2):
        x = w(a)
        if (x & 0xF000) != 0xD000:
            continue
        p = ((a + 4) & ~3) + (x & 0xFF) * 4
        if p + 4 > len(data):
            continue
        v = dw(p)
        if 0x01000000 <= v < 0x04000000:
            vals.add(v)
    print('window %#x-%#x : %d distinct candidate VAs' % (lo, hi, len(vals)))

    def is_utf16_start(o):
        if o < 4 or o + 8 > len(data) or (o & 1):
            return False
        if data[o - 1] != 0 or data[o - 2] != 0:
            return False
        n = 0
        while o + 2 * n + 1 < len(data) and n < 24:
            c = data[o + 2 * n] | (data[o + 2 * n + 1] << 8)
            if c == 0:
                break
            if not (32 <= c < 0x3000):
                return False
            n += 1
        return n >= 4 and o + 2 * n < len(data) and data[o + 2 * n] == 0

    def is_ascii_start(o):
        if o < 1 or o + 6 > len(data):
            return False
        if data[o - 1] not in (0, 0x0a, 0x0d, 0x20) and data[o - 1] > 0x20:
            return False
        n = 0
        while o + n < len(data) and n < 24 and 32 <= data[o + n] < 127:
            n += 1
        return n >= 5 and o + n < len(data) and data[o + n] == 0

    step = 0x1000
    lo_d, hi_d = 0x01000000, 0x03000000
    if '--step' in sys.argv:
        step = int(sys.argv[sys.argv.index('--step') + 1], 0)
    if '--around' in sys.argv:
        centre = int(sys.argv[sys.argv.index('--around') + 1], 0)
        span = int(sys.argv[sys.argv.index('--span') + 1], 0) \
            if '--span' in sys.argv else 0x4000
        lo_d, hi_d = centre - span, centre + span + 1

    scores = []
    for D in range(lo_d, hi_d, step):
        u = a_ = 0
        for v in vals:
            t = v - D
            if is_utf16_start(t):
                u += 1
            elif is_ascii_start(t):
                a_ += 1
        scores.append((u * 2 + a_, u, a_, D))
    scores.sort(reverse=True)
    print('  score utf16 ascii   delta      (score = 2*utf16 + ascii)')
    for s, u, a_, D in scores[:top]:
        print('   %4d  %4d  %4d   %#010x' % (s, u, a_, D))
    return scores


if __name__ == '__main__':
    main()
