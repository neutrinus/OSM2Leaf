#!/usr/bin/env python3
"""Generate length-preserving variants of a card's VER_INFO/HDD_INFO.TXT.

Purpose: identify which of the six HDD_INFO lines the firmware validates, without
touching the original card and without any firmware reverse engineering.

All output variants keep the file **byte length identical** to the input (and the
same CRLF layout), so that any offset/size check in the firmware cannot be the
reason a variant is rejected.

Usage:
  python3 hddinfo_variants.py <HDD_INFO.TXT> <out_dir> [--sweep 0-5]

Safety: reads the input read-only; writes only under <out_dir>.
"""
import argparse
import os
import re
import sys


def load_raw(path):
    with open(path, 'rb') as fh:
        return fh.read()


def split_lines(raw):
    """Split on CRLF, keep the exact terminators."""
    parts = raw.split(b'\r\n')
    return parts


def rebuild(parts):
    return b'\r\n'.join(parts)


def variants_for_line(line, sweep):
    """Yield (label, new_line) keeping len(new_line) == len(line)."""
    if len(line) == 0:
        return
    # 1. last character change, same length
    last = line[-1:]
    alt = b'1' if last != b'1' else b'2'
    yield ('lastchar', line[:-1] + alt)
    # 2. numeric token sweep: replace every digit run with 0..N, left-padded
    for m in re.finditer(rb'\d+', line):
        tok = m.group()
        width = len(tok)
        for n in sweep:
            cand = str(n).encode().rjust(width, b'0')
            if cand == tok:
                continue
            # keep length: if the padded token is longer, skip
            if len(cand) != width:
                continue
            new = line[:m.start()] + cand + line[m.end():]
            yield ('digits@%d=%s' % (m.start(), cand.decode()), new)
    # 3. letter-token change of the same width (e.g. EVEUR -> EVXXX)
    for m in re.finditer(rb'[A-Z]{2,}', line):
        tok = m.group()
        cand = b'X' * len(tok)
        if cand != tok:
            new = line[:m.start()] + cand + line[m.end():]
            yield ('letters@%d=%s' % (m.start(), cand.decode()), new)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('hdd_info')
    ap.add_argument('out_dir')
    ap.add_argument('--sweep', default='0-5')
    args = ap.parse_args()

    lo, hi = (int(x) for x in args.sweep.split('-'))
    sweep = list(range(lo, hi + 1))

    raw = load_raw(args.hdd_info)
    parts = split_lines(raw)
    os.makedirs(args.out_dir, exist_ok=True)

    original_len = len(raw)
    manifest = []
    for idx, line in enumerate(parts):
        for label, new in variants_for_line(line, sweep):
            if new == line or len(new) != len(line):
                continue
            newparts = list(parts)
            newparts[idx] = new
            blob = rebuild(newparts)
            assert len(blob) == original_len, 'length changed!'
            name = 'line%d_%s.HDD_INFO.TXT' % (idx + 1, label.replace('@', '_').replace('=', '_'))
            path = os.path.join(args.out_dir, name)
            with open(path, 'wb') as fh:
                fh.write(blob)
            manifest.append((name, idx + 1, label, line, new))

    with open(os.path.join(args.out_dir, 'MANIFEST.txt'), 'w') as fh:
        fh.write('input: %s (%d bytes)\n' % (args.hdd_info, original_len))
        fh.write('all variants preserve total byte length\n\n')
        for name, line_no, label, old, new in manifest:
            fh.write('%-52s line %d  %-18s  %r -> %r\n' % (name, line_no, label, old, new))

    print('wrote %d variants to %s (all %d bytes, same as input)'
          % (len(manifest), args.out_dir, original_len))


if __name__ == '__main__':
    sys.exit(main())
