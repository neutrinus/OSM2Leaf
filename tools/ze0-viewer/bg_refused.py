#!/usr/bin/env python3
"""Explain the background records that clarion_bg.parse_record refuses.

harness.py verify keeps a refused record verbatim (non-strict mode), so a tile
can round-trip byte-identically while some of its records are never rebuilt.
This tool names each refused record (directory, slot, record index, file
offset), prints the layer table that trips the invariant
``nlayers == len(table)``, and tests a candidate bound: read at most
``geo_len`` table entries, where ``geo_len`` is the geometry length the
header names. A refused record that rebuilds byte-identically under the bound
is evidence that the bound describes it; the cap must never bite on a record
that parses today (the control).

The bounded read is now implemented in clarion_bg.parse_record (M9.23), so the
three B30R048R records that M9.22 found are no longer refused; --selftest
verifies they parse and rebuild byte-identically with strict=True.

Usage:
    python3 bg_refused.py TILE.DAT [TILE.DAT ...]
    python3 bg_refused.py --selftest [TILE.DAT ...]

Exit: 0 ok, 1 a control failed, 2 a tile is missing (no sample, never a pass).
Standard library only; uses the checked-in tools_ze0 package.
"""
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'tools_ze0'))

import clarion_bg  # noqa: E402
import clarion_tile  # noqa: E402

DEFAULT_ROOT = Path('/home/marek/projekty/leafre-work/root/MAPAL001')
SELFTEST_REFUSED_TILE = 'B30R048R.DAT'
SELFTEST_CLEAN_TILES = ['B28R070R.DAT', 'B30R060R.DAT', 'B58R070R.DAT']


def odd_bg_records(path):
    """Yield (where, plain) for every odd-index background record in section 1."""
    tile = clarion_tile.read_tile(Path(path).read_bytes())
    for sec in tile['sections']:
        if sec['id'] != 1:
            continue
        for lvl in sec['levels']:
            for d in lvl['dirs']:
                for si, slot in d['slots'].items():
                    off = slot['block_off']
                    for rec in slot['recs']:
                        rec_off = off
                        off += len(rec['raw'])
                        if rec['k'] % 2 != 1:
                            continue
                        plain = (zlib.decompress(rec['raw'])
                                 if clarion_tile.is_zlib(rec['raw']) else rec['raw'])
                        yield dict(level=lvl['level'], dir=d['off'], slot=si,
                                   k=rec['k'], file_off=rec_off), plain


def bounded_rebuild(d):
    """Rebuild a record with the layer table capped at geo_len entries (strict)."""
    w = list(struct.unpack_from('>22H', d, 0))
    gi = clarion_bg.bg_slot(w)
    geo_off, geo_len = w[gi], w[gi + 1]
    base = 4 * geo_off
    nlayers = geo_len if geo_off != 0xffff else 0
    ents = [struct.unpack_from('>HH', d, base + 4 * i) for i in range(nlayers)]
    layers = {}
    for i, (off, ln) in enumerate(ents):
        if off == 0xffff:
            continue
        p = base + 4 * off
        layers[i] = clarion_bg.parse_group(d, p, p + 4 * ln)
    sections = {}
    for name, (oi, li) in dict(names=(11, 12), s13=(13, 14), points=(15, 16), s17=(17, 18)).items():
        if w[oi] != 0xffff and w[li]:
            sections[name] = d[4 * w[oi]:4 * w[oi] + 4 * w[li]]
        elif w[oi] != 0xffff and w[oi] != 0:
            sections[name] = b''
    r = dict(hdr=w, nlayers=nlayers, layers=layers, sections=sections, gi=gi,
             plain=None, opaque=False, strict=True)
    return clarion_bg.build_record(r), w, gi, geo_off, geo_len, ents


def analyse(path):
    refused = []
    parsed = cap_bites = 0
    for where, plain in odd_bg_records(path):
        try:
            p = clarion_bg.parse_record(plain)
        except AssertionError as e:
            rebuilt, w, gi, geo_off, geo_len, ents = bounded_rebuild(plain)
            past = [(i, *struct.unpack_from('>HH', plain, 4 * geo_off + 4 * i))
                    for i in range(geo_len, geo_len + 8)]
            past = [t for t in past if (t[1], t[2]) != (0xffff, 0)]
            refused.append(dict(where, args=e.args, geo_off=geo_off, geo_len=geo_len,
                                region_empty=all(o == 0xffff and l == 0 for o, l in ents[:geo_len]),
                                used=past, bounded_ok=rebuilt == plain))
            continue
        parsed += 1
        w = list(struct.unpack_from('>22H', plain, 0))
        if p['nlayers'] > w[clarion_bg.bg_slot(w) + 1]:
            cap_bites += 1
    return refused, parsed, cap_bites


def report(path):
    refused, parsed, cap_bites = analyse(path)
    print('%s: parsed %d | refused %d | cap would bite on parsed %d'
          % (Path(path).name, parsed, len(refused), cap_bites))
    for r in refused:
        print('  level %d dir 0x%x slot %d k %d file_off 0x%x: parse_record assert %r '
              '(nlayers, table length); geo_len %d, region empty %s, '
              'entries past the region (index, off, len) %s, bounded rebuild == source %s'
              % (r['level'], r['dir'], r['slot'], r['k'], r['file_off'], r['args'],
                 r['geo_len'], r['region_empty'], r['used'][:3], r['bounded_ok']))
    return refused, cap_bites


# The three records M9.22 found and M9.23 modelled (dir, slot).
M923_TARGETS = {(0x2ad00, 6), (0x2ad00, 8), (0x2ad00, 11)}


def check_m923(path):
    """Verify the M9.23 target records parse and rebuild byte-identically (strict)."""
    found = []
    for where, plain in odd_bg_records(path):
        if (where['dir'], where['slot']) not in M923_TARGETS or where['k'] != 1:
            continue
        p = clarion_bg.parse_record(plain)
        b = clarion_bg.build_record(dict(p, strict=True))
        w = list(struct.unpack_from('>22H', plain, 0))
        gi = clarion_bg.bg_slot(w)
        geo_len = w[gi + 1]
        found.append(dict(where, parsed_ok=True, rebuild_ok=b == plain,
                          nlayers=p['nlayers'], geo_len=geo_len,
                          bounded=p['nlayers'] == geo_len))
    return found


def selftest():
    refused_path = DEFAULT_ROOT / SELFTEST_REFUSED_TILE
    if not refused_path.exists():
        print('selftest: no tile at %s (exit 2, nothing checked)' % refused_path)
        return 2
    refused, cap_bites = report(refused_path)
    m923 = check_m923(refused_path)
    checks = [
        ('B30R048R has no refusals (M9.23 bounded read)', len(refused) == 0),
        ('M9.23 targets found (3 records)', len(m923) == 3),
        ('M9.23 targets parse and rebuild byte-identically (strict)',
         all(r['parsed_ok'] and r['rebuild_ok'] for r in m923)),
        ('M9.23 targets bounded to geo_len (nlayers == geo_len)',
         all(r['bounded'] for r in m923)),
        ('cap does not bite on parsed records of B30R048R', cap_bites == 0),
    ]
    for name in SELFTEST_CLEAN_TILES:
        p = DEFAULT_ROOT / name
        if not p.exists():
            print('selftest: no control tile at %s (exit 2)' % p)
            return 2
        r2, _, cb = analyse(p)
        checks.append(('control %s: no refusals, cap never bites' % name,
                       not r2 and cb == 0))
    bad = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print('%s %s' % ('ok  ' if ok else 'FAIL', name))
    print('selftest: %s (%d checks)' % ('OK' if not bad else 'FAILED', len(checks)))
    return 0 if not bad else 1


def main(argv):
    if argv[:1] == ['--selftest']:
        return selftest()
    if not argv:
        print(__doc__)
        return 2
    status = 0
    for path in argv:
        if not Path(path).exists():
            print('%s: missing' % path)
            return 2
        report(path)
    return status


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
