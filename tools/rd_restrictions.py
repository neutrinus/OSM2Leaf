#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Section-2 entry and regulation-word census, junction lookup and restriction match (M4.23).

    python3 tools/rd_restrictions.py census TILE...
        kinds, entries by one-way class, regulation words, part-b pairing, per level
    python3 tools/rd_restrictions.py match TILE IMF [--level 1|2] [--seed N] [--show N]
        OSM restrictions whose via node lies in TILE: from/to entry by bearing, word test
        for no_* and only_* relations, shuffle control, verdict against PASS
    python3 tools/rd_restrictions.py --selftest

Reads only. The tile reader is ze0-viewer/tools_ze0 (TileScan, clarion_rd, rd_check.rowcol
and rd_check.part_a). rd_check.check_tile and its kind assertion are not used, so the
section-2 kinds 0x2046 and 0x03e4 are read; the body check is rd_check.check.

Layout the census and match rely on (factory bytes; EXP-2026-11-08-M4.23-restriction-encoding):
unit 0 is the unit that pairs[0] points at (word 27 on most level-2 records; the offset is read,
not assumed). A node is three words (entry count << 12 | x, class << 12 | y, flags);
an entry is seven words (far node index, w4, w5, link id, class word, travel time, length)
then w5 bits 6-11 regulation words. Observed, not proven: a regulation word's high nibble names
an entry of the same node (0xf = every entry) and byte1 0xff marks "not allowed"; bits 11-8 are
not the carrying entry's index (EXP, nibble check). Levels 2, 4 and 5 come in pairs by slot
index: even k is unit 0; odd k is part b, whose grammar is NOT established (the checker reports
mismatches and counts the unexplained values; it is not a decoder).
"""
import argparse, collections, json, math, os, random, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'ze0-viewer', 'tools_ze0'))
import clarion_rd, rd_check                                  # noqa: E402
from tile_scan import TileScan                               # noqa: E402

# parcel size in degrees and the modulus of the absolute parcel code (rd_check.rowcol), levels 1, 2
PW = {1: 1 / 32, 2: 1 / 8}
PH = {1: 1 / 48, 2: 1 / 12}
MOD_ROW = {1: 8192, 2: 2048}
MOD_COL = {1: 16384, 2: 4096}
PAIRED = (2, 4, 5)         # levels whose records come in even (unit 0) / odd (part b) pairs
M_PER_DEG = 111320.0
MATCH_DEG = 25.0           # largest bearing error accepted between an OSM way and a tile entry
JUNCTION_TOL = 8           # largest node offset, in 2048 units, accepted as the via node
PASS = {'min_n': 20, 'min_hit': 0.80, 'max_shuffle': 0.30, 'min_gap': 0.50}   # pre-stated for M4.23


def parcel_of(level, lon, lat):
    """((row, col) in rd_check.rowcol units, (corner lon, corner lat)) of the parcel holding (lon, lat)."""
    row = math.floor(lat / PH[level]); col = math.floor((lon + 924) / PW[level])
    return (row % MOD_ROW[level], col % MOD_COL[level]), (col * PW[level] - 924, row * PH[level])


def quant(level, lon, lat):
    """(x, y) in 2048 units of a point inside its parcel, as rd_build.quant computes it."""
    _, (lon0, lat0) = parcel_of(level, lon, lat)
    return (max(0, min(2047, round((lon - lon0) / PW[level] * 2048))),
            max(0, min(2047, round((lat - lat0) / PH[level] * 2048))))


def kind_of(e):
    """'edge' for a parcel-edge entry, 'arr' (w5 0x8000), 'lv' (0x4000) or 'two' (both bits or neither)."""
    if e['cls'] & 0x8000: return 'edge'
    return {0x8000: 'arr', 0x4000: 'lv'}.get(e['w5'] & 0xc000, 'two')


def regs_of(e):
    return e['extra'][:(e['w5'] >> 6) & 0x3f]


def records(tile, level):
    """Yield (kind, k, slot, plain, unit-0 record or None) for every section-2 record of one level."""
    with TileScan(tile) as t:
        for r in t.records(section=2, level=level):
            kind = struct.unpack_from('>H', t.m, r.dir_off)[0]
            plain = r.plain()
            odd_part_b = level in PAIRED and r.k % 2
            rec = None if odd_part_b else clarion_rd.parse_record(rd_check.part_a(plain, level))
            yield kind, r.k, r.slot, plain, rec


def part_b_check(part_a, plain_b):
    """Check an odd (part-b) record against the even record of its slot, as factory bytes lay it out:
    unit 1 = [node count, mark, then per node (0x2000, i, S, i) and per entry (other, T, other-or-not)],
    then the parcel code words. Returns (mismatches, notes); notes count the observed-but-unexplained
    values (the mark's high nibble and the side word S) so they are reported, not assumed."""
    bad, notes = [], collections.Counter()
    o, n = struct.unpack_from('>II', plain_b, 20)
    if o == 0xffffffff:
        return ['part b has no unit 1'], notes
    w = struct.unpack_from('>%dH' % n, plain_b, 2 * o)
    code = struct.unpack_from('>HH', plain_b, 0)
    nodes = part_a['nodes']
    nn = len(nodes); ent = sum(len(nd['entries']) for nd in nodes)
    if n != 2 + 4 * nn + 3 * ent + 2: bad.append('length %d, want %d' % (n, 2 + 4 * nn + 3 * ent + 2))
    if w[0] != nn: bad.append('node count %d, want %d' % (w[0], nn))
    notes['length = 2+4n+3E+2 (factory)' if n == 2 + 4 * nn + 3 * ent + 2 else 'length != 2+4n+3E+2'] += 1
    notes['length = 2+4n+3E+3 (writer)' if n == 2 + 4 * nn + 3 * ent + 3 else 'length != 2+4n+3E+3'] += 1
    if w[1] & 0xff != 0x00: bad.append('mark %#06x low byte not 0x00' % w[1])
    notes['mark high nibble %x' % (w[1] >> 12)] += 1
    if tuple(w[-2:]) != code: bad.append('tail %s, want parcel code %s' % ([hex(x) for x in w[-2:]], [hex(x) for x in code]))
    p = 2
    for i, nd in enumerate(nodes):
        if (w[p], w[p + 1], w[p + 3]) != (0x2000, i, i):
            bad.append('node %d block %s' % (i, [hex(x) for x in w[p:p + 4]])); break
        notes['node side word %#06x' % w[p + 2]] += 1
        p += 4
        for e in nd['entries']:
            edge = bool(e['cls'] & 0x8000)
            if w[p] != e['other']:
                bad.append('entry first word %d, want other %d' % (w[p], e['other'])); break
            notes[('edge' if edge else 'non-edge') + ' entry middle word %#06x' % w[p + 1]] += 1
            if not edge and w[p + 2] != e['other']: notes['non-edge entry third word not other'] += 1
            p += 3
        if bad: break
    return bad, notes


def census(paths, out=print):
    """Per level and directory kind: records, body check, pairing, entry classes and regulation words."""
    stats = collections.Counter()
    for path in paths:
        with open(path, 'rb') as f:
            tile = f.read()
        out('== %s (%d bytes)' % (os.path.basename(path), len(tile)))
        for lev in (1, 2, 4, 5):
            last = {}
            for kind, k, slot, plain, rec in records(tile, lev):
                key = (lev, kind)
                stats[key + ('records',)] += 1
                if lev in PAIRED and k % 2:
                    a = last.pop(slot, None)
                    if a is None or 'nnodes' not in a:
                        stats[key + ('part b without part a',)] += 1
                    else:
                        bad, notes = part_b_check(a, plain)
                        stats[key + ('part b ok' if not bad else 'part b bad',)] += 1
                        for note, cnt in notes.items(): stats[key + ('part b note', note)] += cnt
                        if bad and stats[key + ('part b first', 'shown')] < 2:
                            stats[key + ('part b first', 'shown')] += 1
                            out('   first part b mismatch, level %d slot %d: %s' % (lev, slot, bad[0]))
                    continue
                if lev in PAIRED: last[slot] = rec
                if 'nnodes' not in rec:
                    stats[key + ('no unit 0',)] += 1
                    continue
                _, bp = rd_check.check(plain, lev, None)
                stats[key + ('body ok' if not bp else 'body bad',)] += 1
                for nd in rec['nodes']:
                    for e in nd['entries']:
                        c = kind_of(e)
                        stats[key + ('entries', c)] += 1
                        if c == 'edge': continue
                        if e['w5'] & 0xf: stats[key + ('tail count nonzero', c)] += 1
                        regs = regs_of(e)
                        if c == 'arr':
                            stats[key + ('arriving entries', 'with regulation words' if regs else 'without')] += 1
                            if 0xf0ff in regs: stats[key + ('arriving entries with 0xf0ff', 'yes')] += 1
                        for wd in regs:
                            if wd & 0xff == 0xff:
                                stats[key + ('0xff words', 'named nibble 0xf' if wd >> 12 == 0xf else 'named entry')] += 1
                            else:
                                stats[key + ('other low byte words',)] += 1
                    # a 0xff word names an entry of the same node; record the class pair
                    for ki, e in enumerate(nd['entries']):
                        if kind_of(e) == 'edge': continue
                        for wd in regs_of(e):
                            if wd & 0xff == 0xff and wd >> 12 < len(nd['entries']):
                                stats[key + ('0xff pair', kind_of(nd['entries'][wd >> 12]) + ' -> ' + kind_of(e))] += 1
                                n2 = (wd >> 8) & 0xf
                                stats[key + ('0xff bits 11-8', 'equal to carrier index' if n2 == ki else
                                             'equal to high nibble' if n2 == wd >> 12 else 'other')] += 1
    for key in sorted(stats, key=lambda k: (k[0], k[1], str(k[2:]))):
        out('  level %d kind %#06x %s: %d' % (key[0], key[1], ' '.join(map(str, key[2:])), stats[key]))
    return stats


def _bearing_m(lat0, lon0, lat1, lon1):
    return ((lon1 - lon0) * math.cos(math.radians(lat0)) * M_PER_DEG, (lat1 - lat0) * M_PER_DEG)


def _angle(v):
    return math.degrees(math.atan2(v[1], v[0])) % 360


def _diff(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def match_bearings(osm, tile):
    """osm: [(way id, bearing deg)], tile: [(entry index, bearing deg)]. Greedy one-to-one match by
    smallest error. Returns {way id: entry index} or None when any bearing is above MATCH_DEG or
    the counts differ."""
    if len(osm) != len(tile): return None
    pairs = sorted((_diff(a, b), i, j) for i, (_, a) in enumerate(osm) for j, (_, b) in enumerate(tile))
    used_i, used_j, out = set(), set(), {}
    for d, i, j in pairs:
        if i in used_i or j in used_j: continue
        if d > MATCH_DEG: return None
        used_i.add(i); used_j.add(j); out[osm[i][0]] = tile[j][0]
    return out if len(out) == len(osm) else None


def verdict(n, hits, shuffled):
    """(passes, reason) under PASS: enough cases, observed rate, shuffle ceiling and gap."""
    if n < PASS['min_n']: return False, 'n %d below %d' % (n, PASS['min_n'])
    rate, base = hits / n, shuffled / n
    if rate < PASS['min_hit']: return False, 'hit rate %.3f below %.2f' % (rate, PASS['min_hit'])
    if base > PASS['max_shuffle']: return False, 'shuffle rate %.3f above %.2f' % (base, PASS['max_shuffle'])
    if rate - base < PASS['min_gap']: return False, 'gap %.3f below %.2f' % (rate - base, PASS['min_gap'])
    return True, 'rate %.3f, shuffle %.3f' % (rate, base)


def load_imf(path, log=print):
    """Restriction relations with a node via and from/to ways; the ways and nodes at their vias."""
    rels = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            if '"type":"relation"' not in line or '"restriction"' not in line: continue
            d = json.loads(line)
            m = {x['role']: x for x in d.get('members', [])}
            if 'via' not in m or m['via']['type'] != 'node' or 'from' not in m or 'to' not in m: continue
            rels.append(dict(id=d['id'], tag=d.get('tags', {}).get('restriction'),
                             frm=m['from']['ref'], to=m['to']['ref'], via=m['via']['ref']))
    vias = {r['via'] for r in rels}
    incident = collections.defaultdict(list)
    with open(path, encoding='utf-8') as f:
        for line in f:
            if '"type":"way"' not in line: continue
            d = json.loads(line)
            ns = d.get('nodes') or []
            for n in ns:
                if n in vias: incident[n].append((d['id'], ns))
    need = {n for ws in incident.values() for _, ns in ws for n in ns} | vias
    coords = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            if '"type":"node"' not in line: continue
            i = line.find('"id":"') + 6
            nid = line[i:line.find('"', i)]
            if nid in need:
                d = json.loads(line)
                if 'lat' in d: coords[nid] = (d['lat'], d['lon'])
    log('restriction relations with a node via: %d; vias %d; coordinates %d' % (len(rels), len(vias), len(coords)))
    return rels, incident, coords


def osm_bearings(via, ways, coords):
    """[(way id, bearing deg)] for every way end or pass at the via node."""
    out = []
    vlat, vlon = coords[via]
    for wid, ns in ways:
        for k, n in enumerate(ns):
            if n != via: continue
            for j in (k - 1, k + 1):
                if 0 <= j < len(ns) and ns[j] in coords:
                    lat, lon = coords[ns[j]]
                    out.append((wid, _angle(_bearing_m(vlat, vlon, lat, lon))))
    return out


def index_parcels(tile, level, wanted):
    """{(row, col): [unit-0 record]} for the parcels in `wanted` only (a whole tile is too large to parse)."""
    idx = collections.defaultdict(list)
    with TileScan(tile) as t:
        for r in t.records(section=2, level=level):
            if level in PAIRED and r.k % 2: continue
            plain = r.plain()
            rc = rd_check.rowcol(level, *struct.unpack_from('>HH', plain, 0))
            if rc not in wanted: continue
            rec = clarion_rd.parse_record(rd_check.part_a(plain, level))
            if 'nnodes' in rec: idx[rc].append(rec)
    return idx


def junction(idx, level, lon, lat):
    """(record, node index, node dict) of the graph node at (lon, lat), or None."""
    (row, col), _ = parcel_of(level, lon, lat)
    qx, qy = quant(level, lon, lat)
    best = None
    for rec in idx.get((row, col), []):
        for i, nd in enumerate(rec['nodes']):
            d = max(abs(nd['x'] - qx), abs(nd['y'] - qy))
            if d <= JUNCTION_TOL and (best is None or d < best[0]):
                best = (d, rec, i)
    return None if best is None else best[1:]


def tile_bearings(rec, i, level, lat):
    """[(entry index, bearing deg)] of the non-edge entries of node i whose far node is in this record."""
    nodes = rec['nodes']; v = nodes[i]; out = []
    for k, e in enumerate(v['entries']):
        if kind_of(e) == 'edge': continue
        if e['other'] & 0x4000 or e['other'] >= len(nodes): continue
        far = nodes[e['other']]
        dx = (far['x'] - v['x']) * PW[level] / 2048 * M_PER_DEG * math.cos(math.radians(lat))
        dy = (far['y'] - v['y']) * PH[level] / 2048 * M_PER_DEG
        out.append((k, _angle((dx, dy))))
    return out


def match(tile, imf, level=1, seed=42, show=0, out=print):
    rels, incident, coords = load_imf(imf, out)
    with open(tile, 'rb') as f:
        data = f.read()
    wanted = {parcel_of(level, coords[r['via']][1], coords[r['via']][0])[0] for r in rels if r['via'] in coords}
    idx = index_parcels(data, level, wanted)
    del data
    rng = random.Random(seed)
    per = collections.defaultdict(collections.Counter)
    shown = 0
    reasons = collections.Counter()
    pairs = collections.defaultdict(lambda: [0, 0])     # no_* by (from entry class -> to entry class): n, hit
    for r in rels:
        via = r['via']
        if via not in coords: reasons['via coordinates missing'] += 1; continue
        j = junction(idx, level, coords[via][1], coords[via][0])
        if j is None: reasons['no graph node within %d units' % JUNCTION_TOL] += 1; continue
        rec, i, = j
        ways = incident.get(via, [])
        osm = osm_bearings(via, ways, coords)
        tb = tile_bearings(rec, i, level, coords[via][0])
        nonedge = [k for k, e in enumerate(rec['nodes'][i]['entries']) if kind_of(e) != 'edge']
        if len(tb) != len(nonedge): reasons['tile bearing missing (far node in another record)'] += 1; continue
        m = match_bearings(osm, tb)
        if m is None: reasons['bearings do not match the OSM ways'] += 1; continue
        if r['frm'] not in m or r['to'] not in m: reasons['from or to way not at the node'] += 1; continue
        F, T = m[r['frm']], m[r['to']]
        ents = rec['nodes'][i]['entries']
        word = lambda f, e: any(w >> 12 == f and w & 0xff == 0xff for w in regs_of(e))
        tag = r['tag']
        cand = [k for k in nonedge if k not in (F, T)]
        if tag.startswith('no_'):
            hit = word(F, ents[T])
            U = rng.choice(cand) if cand else None
            sh = word(F, ents[U]) if U is not None else False
        elif tag.startswith('only_'):
            forb = [k for k in nonedge if k not in (F, T) and kind_of(ents[k]) != 'arr']
            hit = bool(forb) and all(word(F, ents[k]) for k in forb)
            exits = [k for k in cand if kind_of(ents[k]) != 'arr']
            U = rng.choice(exits) if exits else None
            sh = word(F, ents[U]) if U is not None else False
        else:
            reasons['tag %s not a turn restriction' % tag] += 1; continue
        # exploratory variants, reported beside the pre-stated test and not used for the verdict:
        # the word naming the to-entry at the from-entry, and any word naming F at T that is not 0xff
        rev = word(T, ents[F])
        other = any(w >> 12 == F and w & 0xff != 0xff for w in regs_of(ents[T]))
        per[tag]['n'] += 1; per[tag]['hit'] += hit; per[tag]['shuffle'] += sh
        per[tag]['reverse'] += rev; per[tag]['other low byte'] += other
        if tag.startswith('no_'):
            pairs['%s -> %s' % (kind_of(ents[F]), kind_of(ents[T]))][0] += 1
            pairs['%s -> %s' % (kind_of(ents[F]), kind_of(ents[T]))][1] += hit
        if show and shown < show:
            shown += 1
            out('  %s %s F=%d(%s) T=%d(%s) hit=%s shuffle=%s' % (r['id'], tag, F, kind_of(ents[F]), T, kind_of(ents[T]), hit, sh))
    out('restrictions read: %d; not matched: %s' % (len(rels), dict(reasons)))
    for tag in sorted(per):
        c = per[tag]
        out('  %-18s n=%d hit=%d shuffle=%d | variants: reverse=%d other-low-byte=%d' % (
            tag, c['n'], c['hit'], c['shuffle'], c['reverse'], c['other low byte']))
    for key in sorted(pairs):
        out('  no_* entry classes %-12s n=%d hit=%d' % (key, pairs[key][0], pairs[key][1]))
    no = collections.Counter()
    for tag in per:
        if tag.startswith('no_'): no.update(per[tag])
    ok, why = verdict(no['n'], no['hit'], no['shuffle'])
    out('no_* verdict under PASS=%s: %s (%s)' % (PASS, 'PASS' if ok else 'FAIL', why))
    return ok


# ---- selftest: no images, no network -------------------------------------------------

def coarse(lev_tile, lon, lat, out=print):
    """Levels 4 and 5 of LEV3456R at (lon, lat): the parcel code the writer's clarion_bg.parcel_code
    gives for the point, the records carrying that code, and the nearest node in metres. The control
    is the file itself: every level-4/5 record code is inverted over a grid and must land in a box."""
    import clarion_bg as B
    with open(lev_tile, 'rb') as f:
        data = f.read()
    for lev in (4, 5):
        L = B.LEVELS[lev]
        w = B.MESH_W * L['dir_meshes'] / L['cols']; h = B.MESH_H * L['dir_meshes'] / L['rows']
        codes = {}
        for row in range(0, 200):
            for col in range(0, 600):
                codes.setdefault(B.parcel_code(lev, row, col), (row, col))
        inside = total = found = 0
        here = []
        with TileScan(data) as t:
            for r in t.records(section=2, level=lev):
                if r.k % 2: continue
                rec = clarion_rd.parse_record(rd_check.part_a(r.plain(), lev))
                if 'nnodes' not in rec: continue
                total += 1
                rc = codes.get(tuple(rec['code']))
                if rc is None: continue
                found += 1
                lon0, lat0 = rc[1] * w - 924, rc[0] * h
                if 0 <= lon0 <= 40 and 30 <= lat0 <= 70: inside += 1
                if (lon0 <= lon < lon0 + w and lat0 <= lat < lat0 + h):
                    best = []
                    for nd in rec['nodes']:
                        dx = (lon0 + nd['x'] / 2048 * w - lon) * math.cos(math.radians(lat)) * M_PER_DEG
                        dy = (lat0 + nd['y'] / 2048 * h - lat) * M_PER_DEG
                        best.append(math.hypot(dx, dy))
                    here.append((rec['code'], len(rec['nodes']), round(min(best)) if best else None))
        row, col = math.floor(lat / h), math.floor((lon + 924) / w)
        out('level %d: %d unit-0 records; %d codes found by parcel_code over the grid; %d decode into Europe '
            '(lon 0..40, lat 30..70); point parcel row %d col %d, code %s; records with that code: %s' % (
                lev, total, found, inside, row, col, tuple(hex(x) for x in B.parcel_code(lev, row, col)), here))
    return 0


def selftest():
    n = 0
    # junction arithmetic: the via node of r120176 (51.1013827 N, 17.0293801 E)
    lon, lat = 17.0293801, 51.1013827
    assert parcel_of(1, lon, lat)[0] == (2452, 13728); n += 1
    assert parcel_of(2, lon, lat)[0] == (613, 3432); n += 1
    assert quant(1, lon, lat) == (1925, 1774); n += 1
    try:
        import rd_build                                      # the writer's own quant, when importable
        pc = rd_build.parcel_of(lon, lat, 1)
        assert rd_build.quant((lon, lat), pc, 1) == quant(1, lon, lat); n += 1
    except ImportError:
        pass
    # bearing match: four ways, one per compass point, and tile entries in another order
    osm = [('a', 0.0), ('b', 90.0), ('c', 180.0), ('d', 270.0)]
    tile = [(0, 181.0), (1, 268.0), (2, 2.0), (3, 91.0)]
    assert match_bearings(osm, tile) == {'c': 0, 'd': 1, 'a': 2, 'b': 3}; n += 1
    assert match_bearings(osm, [(0, 45.0), (1, 90.0), (2, 180.0), (3, 270.0)]) is None; n += 1
    # verdict thresholds
    assert verdict(30, 28, 5)[0]; n += 1
    assert not verdict(30, 15, 12)[0]; n += 1
    assert not verdict(10, 10, 0)[0]; n += 1
    # part b: a part-a record of two nodes (one parcel-edge entry, three entries in all) and the
    # part-b unit laid out as the writer lays it out; it must pass, and one wrong word must fail
    part_a = {'nodes': [{'entries': [{'other': 1, 'cls': 0x0a1a, 'w5': 0}, {'other': 1, 'cls': 0x8a1a, 'w5': 0}]},
                        {'entries': [{'other': 0, 'cls': 0x0a1a, 'w5': 0}]}]}
    code = [0x96bf, 0xc802]
    unit = [2, 0x6100,
            0x2000, 0, 0xc000, 0, 1, 0xc000, 1, 1, 0, 1,
            0x2000, 1, 0xc000, 1, 0, 0xc000, 0,
            code[0], code[1]]
    assert len(unit) == 2 + 4 * 2 + 3 * 3 + 2; n += 1
    plain = bytearray(54 + 2 * len(unit))
    struct.pack_into('>HH', plain, 0, *code)
    struct.pack_into('>II', plain, 12, 0xffffffff, 0)
    struct.pack_into('>II', plain, 20, 27, len(unit))
    struct.pack_into('>%dH' % len(unit), plain, 54, *unit)
    bad, notes = part_b_check(part_a, bytes(plain))
    assert bad == [] and notes['mark high nibble 6'] == 1; n += 1
    flip = bytearray(plain); struct.pack_into('>H', flip, 54 + 2 * 2, 0x2001)
    assert part_b_check(part_a, bytes(flip))[0]; n += 1
    short = bytearray(plain); struct.pack_into('>II', short, 20, 27, len(unit) - 1)
    assert part_b_check(part_a, bytes(short))[0]; n += 1
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--selftest', action='store_true')
    sub = ap.add_subparsers(dest='cmd')
    c = sub.add_parser('census'); c.add_argument('tiles', nargs='+')
    m = sub.add_parser('match'); m.add_argument('tile'); m.add_argument('imf')
    m.add_argument('--level', type=int, choices=(1, 2), default=1)
    m.add_argument('--seed', type=int, default=42); m.add_argument('--show', type=int, default=0)
    cc = sub.add_parser('coarse'); cc.add_argument('lev_tile'); cc.add_argument('lon', type=float)
    cc.add_argument('lat', type=float)
    a = ap.parse_args(argv)
    if a.selftest:
        n = selftest()
        print('rd_restrictions selftest: OK (%d checks)' % n)
        return 0
    if a.cmd == 'census':
        census(a.tiles); return 0
    if a.cmd == 'match':
        return 0 if match(a.tile, a.imf, a.level, a.seed, a.show) else 1
    if a.cmd == 'coarse':
        return coarse(a.lev_tile, a.lon, a.lat)
    ap.print_help(); return 2


if __name__ == '__main__':
    sys.exit(main())
