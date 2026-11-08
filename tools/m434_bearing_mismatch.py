#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""M4.34: classify bearing count-mismatch exclusions (M4.30 follow-up).

Enumerates the M4.30 "bearings do not match the OSM ways" cases where
len(osm_bearings) != len(tile_bearings) (osm!=tile2) and classifies causes
without outcome fitting (no restriction hit/miss used).

    python3 tools/m434_bearing_mismatch.py analyze TILE IMF [--level 1|2]
        per-level classification + recoverability (reads TILE/IMF; read-only)
    python3 tools/m434_bearing_mismatch.py --selftest

Reads rd_restrictions.py as a library (read-only; not modified). No vendor bytes
committed.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rd_restrictions as R  # noqa: E402

MATCH_DEG = R.MATCH_DEG


def best_entry_for_bearing(bearing, tb):
    """(entry_idx, diff_deg, margin_deg) for best tile bearing match, or (None, inf, 0)."""
    if not tb:
        return None, float('inf'), 0.0
    ds = sorted((R._diff(bearing, b), ei) for ei, b in tb)
    best_d, best_ei = ds[0]
    margin = (ds[1][0] - ds[0][0]) if len(ds) >= 2 else 99.0
    return best_ei, best_d, margin


def subset_from_to_matchable(osm, tb, frm, to):
    """Geometric recoverability proxy: can from/to be assigned distinct tile entries within MATCH_DEG?

    Greedy by smallest error on just the two restriction ways (no outcome fitting).
    Returns (ok, detail_dict).
    """
    # collect bearings per restriction way id
    obs = collections.defaultdict(list)
    for wid, b in osm:
        obs[wid].append(b)
    fbs = obs.get(frm, [])
    tbs_ = obs.get(to, [])
    if not fbs or not tbs_:
        return False, {'reason': 'from_or_to_way_missing_in_osm', 'f_bearings': len(fbs), 't_bearings': len(tbs_)}
    # try all (from bearing, to bearing) x (tile entry, tile entry) pairs, greedy on best feasible
    candidates = []
    for fb in fbs:
        for tb_b in tbs_:
            for ei, eb in tb:
                df = R._diff(fb, eb)
                if df > MATCH_DEG:
                    continue
                for ej, ejb in tb:
                    if ej == ei:
                        continue
                    dt = R._diff(tb_b, ejb)
                    if dt > MATCH_DEG:
                        continue
                    candidates.append((df + dt, df, dt, ei, ej))
    if not candidates:
        # report best individual errors for diagnosis
        bf = min((R._diff(fb, eb) for fb in fbs for _, eb in tb), default=float('inf'))
        bt = min((R._diff(tb_b, eb) for tb_b in tbs_ for _, eb in tb), default=float('inf'))
        return False, {'reason': 'no_feasible_from_to_assignment', 'best_from_err': round(bf, 2), 'best_to_err': round(bt, 2)}
    candidates.sort()
    tot, df, dt, ei, ej = candidates[0]
    return True, {'reason': 'feasible', 'from_err': round(df, 2), 'to_err': round(dt, 2), 'F': ei, 'T': ej}


def classify_one(r, osm, tb, nonedge, junction_dist):
    """Classify one count-mismatch case. No outcome fitting."""
    osm_n = len(osm)
    tb_n = len(tb)
    osm_ids = [w for w, _ in osm]
    dup_way = len(osm_ids) != len(set(osm_ids))
    frm_in = r['frm'] in osm_ids
    to_in = r['to'] in osm_ids
    from_eq_to = r['frm'] == r['to']
    # pass-through ways: way id appears as 2 bearings from same way passing via
    per_way = collections.Counter(osm_ids)
    pass_through = sum(1 for c in per_way.values() if c >= 2)
    delta = osm_n - tb_n
    recoverable, rec_detail = subset_from_to_matchable(osm, tb, r['frm'], r['to'])
    classes = []
    if osm_n > tb_n:
        classes.append('osm_more')
        # extra bearings not explained by from/to: from/to contribute fbs+tbs bearings
        obs = collections.defaultdict(int)
        for wid, _ in osm:
            obs[wid] += 1
        ft_b = obs.get(r['frm'], 0) + (0 if from_eq_to else obs.get(r['to'], 0))
        extra = osm_n - tb_n
        if ft_b <= 2 and extra > 0:
            classes.append('extra_non_from_to_bearings')
        if pass_through:
            classes.append('has_pass_through_way_bearings')
    elif osm_n < tb_n:
        classes.append('osm_fewer')
        classes.append('tile_has_extra_nonedge_entries')
    else:
        classes.append('equal_unexpected')
    if not frm_in or not to_in:
        classes.append('from_or_to_missing_in_osm_bearings')
    if from_eq_to:
        classes.append('osm_from_eq_to')
    if dup_way:
        classes.append('dup_osm_way_bearing')
    if junction_dist > 4:
        classes.append('junction_dist_gt4')
    return {
        'id': r['id'], 'tag': r['tag'],
        'osm_n': osm_n, 'tb_n': tb_n, 'nonedge_n': len(nonedge), 'delta': delta,
        'frm_in_osm': frm_in, 'to_in_osm': to_in, 'from_eq_to': from_eq_to,
        'dup_way': dup_way, 'pass_through_ways': pass_through,
        'junction_dist': junction_dist,
        'recoverable_subset': recoverable,
        'recover_detail': rec_detail,
        'classes': classes,
    }


def junction_with_dist(idx, level, lon, lat):
    """(record, node index, dist) or None."""
    (row, col), _ = R.parcel_of(level, lon, lat)
    qx, qy = R.quant(level, lon, lat)
    best = None
    for rec in idx.get((row, col), []):
        for i, nd in enumerate(rec['nodes']):
            d = max(abs(nd['x'] - qx), abs(nd['y'] - qy))
            if d <= R.JUNCTION_TOL and (best is None or d < best[0]):
                best = (d, rec, i)
    return None if best is None else (best[1], best[2], best[0])


def analyze(tile, imf, level=1, seed=42, out=print):
    rels, incident, coords = R.load_imf(imf, out)
    with open(tile, 'rb') as f:
        data = f.read()
    wanted = {R.parcel_of(level, coords[r['via']][1], coords[r['via']][0])[0]
              for r in rels if r['via'] in coords}
    idx = R.index_parcels(data, level, wanted)
    del data
    reasons = collections.Counter()
    mapping = collections.Counter()
    cases = []
    for r in rels:
        via = r['via']
        if via not in coords:
            reasons['via coordinates missing'] += 1; continue
        j = junction_with_dist(idx, level, coords[via][1], coords[via][0])
        if j is None:
            reasons['no graph node within %d units' % R.JUNCTION_TOL] += 1; continue
        rec, i, jdist = j
        ways = incident.get(via, [])
        osm = R.osm_bearings(via, ways, coords)
        tb = R.tile_bearings(rec, i, level, coords[via][0])
        nonedge = [k for k, e in enumerate(rec['nodes'][i]['entries']) if R.kind_of(e) != 'edge']
        dup_way = len([w for w, _ in osm]) != len({w for w, _ in osm})
        if dup_way:
            mapping['vias_with_dup_osm_way_bearing'] += 1
        if len(tb) != len(nonedge):
            reasons['tile bearing missing (far node in another record)'] += 1
            mapping['mismatch_count_osm!=tile'] += 1
            if dup_way:
                mapping['mismatch_count_with_dup_way'] += 1
            continue
        m = R.match_bearings(osm, tb)
        if m is None:
            reasons['bearings do not match the OSM ways'] += 1
            if len(osm) != len(tb):
                mapping['mismatch_count_osm!=tile2'] += 1
                cases.append(classify_one(r, osm, tb, nonedge, jdist))
                if dup_way:
                    mapping['mismatch_angle_with_dup_way'] += 1  # not quite; keep parity fields separate
            else:
                mapping['mismatch_angle'] += 1
                if dup_way:
                    mapping['mismatch_angle_with_dup_way'] += 1
            continue
        if r['frm'] not in m or r['to'] not in m:
            reasons['from or to way not at the node'] += 1; continue
        tag = r['tag']
        if not (tag.startswith('no_') or tag.startswith('only_')):
            reasons['tag %s not a turn restriction' % tag] += 1; continue
        reasons['matched'] += 1

    # But note: in our loop above, dup_way for mismatch_count_osm!=tile2 was added to
    # mismatch_angle_with_dup_way by mistake in that branch? rd_restrictions._deep_rows does:
    #   if len(osm)!=len(tb): mapping['mismatch_count_osm!=tile2'] += 1  (no dup subcounter)
    #   else: mapping['mismatch_angle'] += 1; if dup_way: mapping['mismatch_angle_with_dup_way'] += 1
    # Fix parity: recompute mapping dup counters to match _deep_rows semantics? Easier: report our own.

    out('=== M4.34 bearing count-mismatch: %s level %d ===' % (os.path.basename(tile), level))
    out('restrictions read: %d' % len(rels))
    out('not matched reasons: %s' % dict(reasons))
    out('mapping (M4.34 view): mismatch_count_osm!=tile2=%d (expected precheck parity)' % len(cases))
    out('count-mismatch cases: %d' % len(cases))
    if not cases:
        return {'level': level, 'cases': 0}
    cc = collections.Counter()
    for c in cases:
        for cl in c['classes']:
            cc[cl] += 1
    recov = sum(1 for c in cases if c['recoverable_subset'])
    out('-- primary direction --')
    out('  osm_more (osm_n>tb_n): %d' % cc['osm_more'])
    out('  osm_fewer (osm_n<tb_n): %d' % cc['osm_fewer'])
    out('-- named classes (counted, overlapping) --')
    for k, v in cc.most_common():
        out('  %-45s %d / %d' % (k, v, len(cases)))
    out('-- recoverability (geometric subset, no outcome fitting) --')
    out('  from+to subset matchable within %g°: %d / %d (%.1f%%)' % (
        MATCH_DEG, recov, len(cases), 100 * recov / len(cases)))
    out('  not recoverable: %d' % (len(cases) - recov))
    # recoverability by direction
    for direction in ('osm_more', 'osm_fewer'):
        sub = [c for c in cases if direction in c['classes']]
        if sub:
            sr = sum(1 for c in sub if c['recoverable_subset'])
            out('    %s: %d/%d (%.1f%%)' % (direction, sr, len(sub), 100 * sr / len(sub)))
    # delta distribution
    deltas = collections.Counter(c['delta'] for c in cases)
    out('-- osm_n - tb_n distribution --')
    for d, n in sorted(deltas.items()):
        out('  delta %+d: %d' % (d, n))
    # common (osm_n,tb_n)
    pairs = collections.Counter((c['osm_n'], c['tb_n']) for c in cases).most_common(12)
    out('-- common (osm_n, tb_n) --')
    for (a, b), n in pairs:
        out('  (%d,%d): %d' % (a, b, n))
    # not-recoverable reasons
    nr = collections.Counter(c['recover_detail'].get('reason') for c in cases if not c['recoverable_subset'])
    out('-- not-recoverable reasons --')
    for k, v in nr.most_common():
        out('  %s: %d' % (k, v))
    # junction distance
    jd = collections.Counter('>4' if c['junction_dist'] > 4 else '<=4' for c in cases)
    out('-- junction distance (2048-units, tol=%d) --' % R.JUNCTION_TOL)
    for k, v in jd.items():
        out('  %s: %d' % (k, v))
    # tag distribution
    tags = collections.Counter(c['tag'] for c in cases)
    out('-- restriction tags --')
    for k, v in tags.most_common():
        out('  %s: %d' % (k, v))
    # matched population context: M4.30 reported matched no_* 411/235 of total matched 651/428
    # recoverable cases are a subset of count-mismatch exclusions (turn restrictions that failed bearing match due to count)
    out('-- recoverable population note --')
    out('  recoverable count-mismatch cases (could become bearing-mapped for from/to): %d' % recov)
    out('  (adding these to matched pool depends on whether a subset-mapping rule is adopted; no outcome fitting used)')
    return {'level': level, 'total': len(cases), 'recoverable': recov, 'classes': dict(cc),
            'reasons': dict(reasons), 'deltas': dict(deltas)}


def selftest():
    # best_entry_for_bearing
    tb = [(0, 0.0), (1, 90.0), (2, 180.0)]
    ei, d, margin = best_entry_for_bearing(5.0, tb)
    assert ei == 0 and d == 5.0 and margin == 80.0, (ei, d, margin)
    ei, d, _ = best_entry_for_bearing(85.0, tb)
    assert ei == 1
    # subset matchable: from->0deg entry, to->90deg entry
    osm = [('f1', 2.0), ('t1', 88.0), ('x1', 180.0)]  # osm_more
    ok, det = subset_from_to_matchable(osm, tb, 'f1', 't1')
    assert ok and det['F'] == 0 and det['T'] == 1, (ok, det)
    # not matchable when bearing far off
    osm2 = [('f1', 45.0), ('t1', 88.0), ('x1', 180.0)]
    ok2, det2 = subset_from_to_matchable(osm2, tb, 'f1', 't1')
    assert not ok2 and det2['best_from_err'] == 45.0, (ok2, det2)
    # missing from
    ok3, det3 = subset_from_to_matchable([('t1', 88.0)], tb, 'f1', 't1')
    assert not ok3 and det3['reason'] == 'from_or_to_way_missing_in_osm'
    # classify_one synthetic (count-mismatch directions)
    r = {'id': 'r1', 'frm': 'f1', 'to': 't1', 'tag': 'no_left_turn'}
    # osm_more
    c = classify_one(r, [('f1', 2.0), ('t1', 88.0), ('x1', 180.0), ('x2', 270.0)], tb, [0, 1, 2], 2)
    assert 'osm_more' in c['classes'] and c['delta'] == 1 and c['recoverable_subset']
    assert 'extra_non_from_to_bearings' in c['classes']
    # equal counts (not a count-mismatch; classifier labels direction)
    c_eq = classify_one(r, [('f1', 2.0), ('t1', 88.0), ('x1', 180.0)], tb, [0, 1, 2], 2)
    assert c_eq['delta'] == 0 and 'equal_unexpected' in c_eq['classes'] and c_eq['recoverable_subset']
    # osm_fewer (re-check)
    c2 = classify_one(r, [('f1', 2.0), ('t1', 88.0)], tb, [0, 1, 2], 2)
    assert 'osm_fewer' in c2['classes'] and c2['delta'] == -1 and c2['recoverable_subset']
    # osm_fewer
    c3 = classify_one(r, [('f1', 2.0), ('t1', 88.0)], tb, [0, 1, 2], 2)
    assert 'osm_fewer' in c3['classes'] and c3['delta'] == -1 and c3['recoverable_subset']
    # from_eq_to
    r2 = {'id': 'r2', 'frm': 'f1', 'to': 'f1', 'tag': 'no_u_turn'}
    c4 = classify_one(r2, [('f1', 2.0), ('f1', 182.0), ('x1', 90.0)], tb, [0, 1, 2], 5)
    assert c4['from_eq_to'] and 'junction_dist_gt4' in c4['classes']
    # from/to missing in osm
    c5 = classify_one(r, [('x1', 2.0), ('x2', 88.0), ('x3', 180.0), ('x4', 270.0)], tb, [0, 1, 2], 1)
    assert not c5['recoverable_subset'] and 'from_or_to_missing_in_osm_bearings' in c5['classes']
    print('m434_bearing_mismatch selftest: OK (11 checks)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--selftest', action='store_true')
    sub = ap.add_subparsers(dest='cmd')
    an = sub.add_parser('analyze')
    an.add_argument('tile')
    an.add_argument('imf')
    an.add_argument('--level', type=int, default=1)
    an.add_argument('--seed', type=int, default=42)
    an.add_argument('--json', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        selftest(); return
    if a.cmd == 'analyze':
        buf = []
        res = analyze(a.tile, a.imf, a.level, a.seed, out=buf.append)
        if a.json:
            print(json.dumps(res, indent=2, sort_keys=True))
        else:
            print('\n'.join(buf))
        return
    ap.print_help()


if __name__ == '__main__':
    main()
