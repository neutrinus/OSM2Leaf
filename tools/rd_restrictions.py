#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Section-2 entry and regulation-word census, junction lookup and restriction match (M4.23/M4.25/M4.30).

    python3 tools/rd_restrictions.py census TILE...
        kinds, entries by one-way class, regulation words, part-b pairing, per level
    python3 tools/rd_restrictions.py match TILE IMF [--level 1|2] [--seed N] [--show N]
        OSM restrictions whose via node lies in TILE: from/to entry by bearing, word test
        for no_* and only_* relations, shuffle control, verdict against PASS
    python3 tools/rd_restrictions.py audit TILE IMF [--level 1|2] [--seed N]
        M4.25 mapping audit: named, counted miss classes for no_* and encoding candidates
        for only_*
    python3 tools/rd_restrictions.py deepen TILE IMF [--level 1|2] [--seed N]
        M4.30 deepening: per-stratum (entry class) hit/shuffle/verdict, mapping anomalies
        (count/angle bearing mismatch, duplicate OSM way bearings, ambiguous margin,
        osm from==to), miss clustering by tag/one-way geometry/M4.25 class/word form,
        and held-out (deterministic by relation id) subset verdicts. Read-only.
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
import argparse, collections, hashlib, json, math, os, random, struct, sys

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


def _match_core(tile, imf, level=1, seed=42, out=print):
    """Parse tile/IMF once and return (rels, reasons, rows, rng) for matched turn restrictions.
    rows: [(r, F, T, ents, nonedge, tag)] where F/T are tile entry indices of from/to."""
    rels, incident, coords = load_imf(imf, out)
    with open(tile, 'rb') as f:
        data = f.read()
    wanted = {parcel_of(level, coords[r['via']][1], coords[r['via']][0])[0] for r in rels if r['via'] in coords}
    idx = index_parcels(data, level, wanted)
    del data
    rng = random.Random(seed)
    reasons = collections.Counter()
    rows = []
    for r in rels:
        via = r['via']
        if via not in coords: reasons['via coordinates missing'] += 1; continue
        j = junction(idx, level, coords[via][1], coords[via][0])
        if j is None: reasons['no graph node within %d units' % JUNCTION_TOL] += 1; continue
        rec, i = j
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
        tag = r['tag']
        if not (tag.startswith('no_') or tag.startswith('only_')):
            reasons['tag %s not a turn restriction' % tag] += 1; continue
        rows.append((r, F, T, ents, nonedge, tag))
    return rels, reasons, rows, rng


def _word_ff(f, e):
    """True if entry e has a 0xff prohibition word naming entry f."""
    return any(w >> 12 == f and (w & 0xff) == 0xff for w in regs_of(e))


def _word_any(f, e):
    """True if entry e has any word naming entry f, regardless of byte1."""
    return any(w >> 12 == f for w in regs_of(e))


def _word_ff_on(entries, f, idxs):
    """Indices in idxs whose entry carries a 0xff word naming f."""
    return [k for k in idxs if _word_ff(f, entries[k])]


def _byte1s_naming(f, e):
    """Byte1 values of all words naming f on entry e."""
    return [w & 0xff for w in regs_of(e) if w >> 12 == f]


def audit(tile, imf, level=1, seed=42, out=print):
    """M4.25 mapping audit: named, counted checks for no_* misses and only_* encoding candidates.
    B48R058R/dolnoslaskie scope; read-only. Reports every miss class with a count."""
    rels, reasons, rows, rng = _match_core(tile, imf, level, seed, out)
    no = collections.Counter()          # all no_* matched
    miss = collections.Counter()        # named miss buckets (a miss may increment several)
    miss_excl = collections.Counter()   # first matching explanation, for a partition view
    only_c = collections.Counter()      # only_* encoding candidates
    only_detail = collections.defaultdict(collections.Counter)
    no_uturn = collections.Counter()

    def explain_no(r, F, T, ents, nonedge, tag):
        hit = _word_ff(F, ents[T])
        no['n'] += 1; no['hit'] += hit
        no['tag:' + tag] += 1; no['tag-hit:' + tag] += hit
        no['class:%s->%s' % (kind_of(ents[F]), kind_of(ents[T]))] += 1
        if hit:
            no['class-hit:%s->%s' % (kind_of(ents[F]), kind_of(ents[T]))] += 1
            return
        no['miss'] += 1
        flags = []
        if _word_ff(T, ents[F]): flags.append('reverse_ff_on_F_names_T')
        if any(w >> 12 == F and (w & 0xff) != 0xff for w in regs_of(ents[T])):
            flags.append('other_byte1_on_T_names_F'); miss['other_byte1_values_on_T:' + repr(_byte1s_naming(F, ents[T]))] += 1
        if any(w >> 12 == T and (w & 0xff) != 0xff for w in regs_of(ents[F])):
            flags.append('other_byte1_on_F_names_T')
        locs = _word_ff_on(ents, F, [k for k in nonedge if k != T])
        if locs: flags.append('ff_naming_F_on_other_entries:' + repr(locs))
        any_f = _word_ff_on(ents, F, nonedge)
        if not any_f: flags.append('no_ff_word_naming_F_anywhere')
        any_tname = [k for k in nonedge if _word_ff(T, ents[k])]
        if any_tname and 'reverse_ff_on_F_names_T' not in flags:
            flags.append('ff_naming_T_exists_not_on_F:' + repr(any_tname))
        # T carries ff words naming whom?
        t_ff_names = [w >> 12 for w in regs_of(ents[T]) if (w & 0xff) == 0xff]
        if t_ff_names: flags.append('T_has_ff_naming:' + repr(t_ff_names))
        else: flags.append('T_has_no_ff_words')
        # f nibble present with 0xff on T? (already checked) any nibble==F at all on T?
        if _word_any(F, ents[T]): flags.append('T_names_F_nonff_only_or_mixed')
        if r['frm'] == r['to']: flags.append('osm_from_eq_to')
        if tag == 'no_u_turn':
            no_uturn['n'] += 1
            if kind_of(ents[F]) == kind_of(ents[T]) == 'two': no_uturn['F_two_T_two'] += 1
            if not any_f: no_uturn['no_ff_naming_F'] += 1
            if flags and flags[0].startswith('reverse'): no_uturn['reverse'] += 1
        for fl in flags: miss[fl.split(':')[0] if ':' in fl and not fl.startswith('other_byte1_values') else fl] += 1
        # partition: first/primary explanation
        for cand in ('reverse_ff_on_F_names_T', 'other_byte1_on_T_names_F', 'ff_naming_F_on_other_entries',
                     'no_ff_word_naming_F_anywhere', 'osm_from_eq_to'):
            if any(f.startswith(cand) for f in flags):
                miss_excl[cand] += 1; break
        else:
            miss_excl['unexplained_residual'] += 1
        miss['tag-miss:' + tag] += 1

    def explain_only(r, F, T, ents, nonedge, tag):
        forb = [k for k in nonedge if k not in (F, T) and kind_of(ents[k]) != 'arr']
        exits = [k for k in nonedge if k not in (F, T) and kind_of(ents[k]) != 'arr']
        all_nonft = [k for k in nonedge if k not in (F, T)]
        only_c['n'] += 1; only_c['tag:' + tag] += 1
        # candidates (named)
        c_all_ff = bool(forb) and all(_word_ff(F, ents[k]) for k in forb)
        only_c['all_other_exits_ff_naming_F'] += c_all_ff
        only_c['T_has_ff_naming_F'] += _word_ff(F, ents[T])
        only_c['T_has_any_naming_F'] += _word_any(F, ents[T])
        only_c['F_has_ff_naming_T'] += _word_ff(T, ents[F])
        only_c['F_has_any_naming_T'] += _word_any(T, ents[F])
        # any ff naming F on T with F-specific check: T is the allowed target; if it carried ff naming F
        # that would mean "forbidden from F" contradicting only_*. count it.
        t_b1 = _byte1s_naming(F, ents[T])
        if t_b1: only_detail['T_byte1_naming_F'][repr(sorted(set(t_b1)))] += 1
        # is "only" encoded as: no other exit is traversable-from-F except T? check words on others naming F
        n_forb_ff = sum(1 for k in forb if _word_ff(F, ents[k]))
        only_c['forb_with_ff_naming_F_total'] += n_forb_ff
        only_c['forb_slots_total'] += len(forb)
        only_detail['forb_ff_count'][str(n_forb_ff) + '/' + str(len(forb))] += 1
        # all non-F,T including arrivals with ff naming F?
        n_all_ff = sum(1 for k in all_nonft if _word_ff(F, ents[k]))
        only_c['all_nonft_with_ff_naming_F_total'] += n_all_ff
        only_c['all_nonft_slots_total'] += len(all_nonft)
        # "only" = T carries a 0xff naming 0xf (all entries barred?) or specific marker?
        only_c['T_has_ff_naming_0xf'] += any(w >> 12 == 0xf and (w & 0xff) == 0xff for w in regs_of(ents[T]))
        only_c['F_has_ff_naming_0xf'] += any(w >> 12 == 0xf and (w & 0xff) == 0xff for w in regs_of(ents[F]))
        # baseline: for a random (node, entry, named) how often ff naming appears? approximate by F->random exit
        if exits:
            U = rng.choice(exits)
            only_c['baseline_ff_naming_F_on_random_exit'] += _word_ff(F, ents[U])
            only_c['baseline_n'] += 1
        only_c['F_arrival'] += (kind_of(ents[F]) == 'arr')
        only_c['F_class:' + kind_of(ents[F])] += 1

    for r, F, T, ents, nonedge, tag in rows:
        if tag.startswith('no_'): explain_no(r, F, T, ents, nonedge, tag)
        elif tag.startswith('only_'): explain_only(r, F, T, ents, nonedge, tag)

    out('=== M4.25 audit: %s level %d ===' % (os.path.basename(tile), level))
    out('restrictions read: %d; not matched: %s' % (len(rels), dict(reasons)))
    out('no_* matched: n=%d hit=%d miss=%d (%.1f%% hit)' % (no['n'], no['hit'], no['miss'], 100*no['hit']/no['n'] if no['n'] else 0))
    ok, why = verdict(no['n'], no['hit'], 0)  # shuffle not re-run; report primary only
    out('primary verdict (no shuffle rerun): %s (%s)' % ('PASS' if ok else 'FAIL', why))
    out('-- no_* hits/misses by tag --')
    for k in sorted(k for k in no if k.startswith('tag:')):
        tag = k[4:]; out('  %-18s n=%d hit=%d miss=%d' % (tag, no[k], no.get('tag-hit:'+tag,0), no[k]-no.get('tag-hit:'+tag,0)))
    out('-- no_* hits/misses by entry class (from->to) --')
    for k in sorted(k for k in no if k.startswith('class:')):
        cls = k[6:]; n = no[k]; h = no.get('class-hit:'+cls,0); out('  %-12s n=%d hit=%d miss=%d (%.1f%%)' % (cls, n, h, n-h, 100*h/n if n else 0))
    out('-- no_* miss: named checks (flags; a miss may count in several) --')
    for k, v in miss.most_common():
        if k.startswith('tag-') or k.startswith('other_byte1_values'): continue
        out('  %-45s %d' % (k, v))
    out('-- no_* miss: exclusive primary partition (first match) --')
    for k, v in miss_excl.most_common():
        out('  %-45s %d / %d' % (k, v, no['miss']))
    out('-- no_* miss: other byte1 values on T naming F --')
    for k, v in miss.most_common():
        if k.startswith('other_byte1_values_on_T:'): out('  %s %d' % (k.split(':',1)[1], v))
    out('-- no_u_turn detail --')
    for k, v in sorted(no_uturn.items()): out('  %s %d' % (k, v))
    out('-- only_* encoding candidates (named, counted) --')
    for k, v in sorted(only_c.items()):
        if not k.startswith('tag:'): out('  %-45s %s' % (k, v))
    for k in sorted(k for k in only_c if k.startswith('tag:')):
        out('  %s %d' % (k, only_c[k]))
    for name, ctr in sorted(only_detail.items()):
        out('  detail %s: %s' % (name, dict(ctr.most_common(12))))
    if only_c['forb_slots_total']:
        out('  density ff_naming_F on forb slots: %d/%d (%.1f%%)' % (
            only_c['forb_with_ff_naming_F_total'], only_c['forb_slots_total'],
            100*only_c['forb_with_ff_naming_F_total']/only_c['forb_slots_total']))
    if only_c['baseline_n']:
        out('  baseline ff_naming_F on random exit: %d/%d (%.1f%%)' % (
            only_c['baseline_ff_naming_F_on_random_exit'], only_c['baseline_n'],
            100*only_c['baseline_ff_naming_F_on_random_exit']/only_c['baseline_n']))
    return {'no_n': no['n'], 'no_hit': no['hit'], 'no_miss': no['miss'],
            'only_n': only_c['n'], 'miss_excl': dict(miss_excl), 'only': dict(only_c)}


def match(tile, imf, level=1, seed=42, show=0, out=print):
    rels, reasons, rows, rng = _match_core(tile, imf, level, seed, out)
    per = collections.defaultdict(collections.Counter)
    shown = 0
    pairs = collections.defaultdict(lambda: [0, 0])     # no_* by (from entry class -> to entry class): n, hit
    for r, F, T, ents, nonedge, tag in rows:
        cand = [k for k in nonedge if k not in (F, T)]
        if tag.startswith('no_'):
            hit = _word_ff(F, ents[T])
            U = rng.choice(cand) if cand else None
            sh = _word_ff(F, ents[U]) if U is not None else False
        elif tag.startswith('only_'):
            forb = [k for k in nonedge if k not in (F, T) and kind_of(ents[k]) != 'arr']
            hit = bool(forb) and all(_word_ff(F, ents[k]) for k in forb)
            exits = [k for k in cand if kind_of(ents[k]) != 'arr']
            U = rng.choice(exits) if exits else None
            sh = _word_ff(F, ents[U]) if U is not None else False
        else:
            continue
        rev = _word_ff(T, ents[F])
        other = any(w >> 12 == F and (w & 0xff) != 0xff for w in regs_of(ents[T]))
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



# ---- M4.30 deepening ------------------------------------------------------------

def _holdout(rel_id, mod=2, bucket=0):
    """Deterministic hold-out split by relation id (stable across runs/levels)."""
    h = int(hashlib.sha256(str(rel_id).encode()).hexdigest(), 16)
    return (h % mod) == bucket


def _amb_margin(osm, tb, frm, to, m):
    """Min margin (2nd-best minus best bearing diff) for the relation's from/to ways."""
    tbe = dict(tb)
    scores = []
    for wid in (frm, to):
        obs = [b for w, b in osm if w == wid]
        if not obs or m.get(wid) not in tbe:
            continue
        ds = sorted(_diff(obs[0], b) for _, b in tb)
        if len(ds) >= 2:
            scores.append(ds[1] - ds[0])
    return min(scores) if scores else 99.0


def _deep_rows(tile, imf, level=1, seed=42, out=print):
    """Like _match_core but also returns mapping diagnostics per matched row and mismatch reasons.
    Returns (rels, reasons, rows, rng, mapping) where rows carry extra mapping fields:
    (r, F, T, ents, nonedge, tag, amb_margin, dup_way, from_eq_to)."""
    rels, incident, coords = load_imf(imf, out)
    with open(tile, 'rb') as f:
        data = f.read()
    wanted = {parcel_of(level, coords[r['via']][1], coords[r['via']][0])[0]
              for r in rels if r['via'] in coords}
    idx = index_parcels(data, level, wanted)
    del data
    rng = random.Random(seed)
    reasons = collections.Counter()
    mapping = collections.Counter()
    rows = []
    for r in rels:
        via = r['via']
        if via not in coords:
            reasons['via coordinates missing'] += 1; continue
        j = junction(idx, level, coords[via][1], coords[via][0])
        if j is None:
            reasons['no graph node within %d units' % JUNCTION_TOL] += 1; continue
        rec, i = j
        ways = incident.get(via, [])
        osm = osm_bearings(via, ways, coords)
        tb = tile_bearings(rec, i, level, coords[via][0])
        nonedge = [k for k, e in enumerate(rec['nodes'][i]['entries']) if kind_of(e) != 'edge']
        osm_ids = [w for w, _ in osm]
        dup_way = len(osm_ids) != len(set(osm_ids))
        if dup_way:
            mapping['vias_with_dup_osm_way_bearing'] += 1
        if len(tb) != len(nonedge):
            reasons['tile bearing missing (far node in another record)'] += 1
            mapping['mismatch_count_osm!=tile'] += 1
            if dup_way:
                mapping['mismatch_count_with_dup_way'] += 1
            continue
        m = match_bearings(osm, tb)
        if m is None:
            reasons['bearings do not match the OSM ways'] += 1
            if len(osm) != len(tb):
                mapping['mismatch_count_osm!=tile2'] += 1
            else:
                mapping['mismatch_angle'] += 1
                if dup_way:
                    mapping['mismatch_angle_with_dup_way'] += 1
            continue
        if r['frm'] not in m or r['to'] not in m:
            reasons['from or to way not at the node'] += 1; continue
        F, T = m[r['frm']], m[r['to']]
        ents = rec['nodes'][i]['entries']
        tag = r['tag']
        if not (tag.startswith('no_') or tag.startswith('only_')):
            reasons['tag %s not a turn restriction' % tag] += 1; continue
        am = _amb_margin(osm, tb, r['frm'], r['to'], m)
        feq = r['frm'] == r['to']
        rows.append((r, F, T, ents, nonedge, tag, am, dup_way, feq))
    return rels, reasons, rows, rng, mapping


def _no_row(r, F, T, ents, nonedge, tag, rng):
    hit = _word_ff(F, ents[T])
    cand = [k for k in nonedge if k not in (F, T)]
    U = rng.choice(cand) if cand else None
    sh = _word_ff(F, ents[U]) if U is not None else False
    mclass = 'hit'
    if not hit:
        if _word_ff(T, ents[F]):
            mclass = 'reverse_ff_on_F_names_T'
        elif any(w >> 12 == F and (w & 0xff) != 0xff for w in regs_of(ents[T])):
            mclass = 'other_byte1_on_T_names_F'
        elif _word_ff_on(ents, F, [k for k in nonedge if k != T]):
            mclass = 'ff_naming_F_on_other_entries'
        elif not _word_ff_on(ents, F, nonedge):
            mclass = 'no_ff_word_naming_F_anywhere'
        else:
            mclass = 'unexplained_residual'
    t_ff_names = [w >> 12 for w in regs_of(ents[T]) if (w & 0xff) == 0xff]
    t_names_f = [w for w in regs_of(ents[T]) if w >> 12 == F]
    t_f_byte1s = tuple(sorted(set(w & 0xff for w in t_names_f))) if t_names_f else ()
    return dict(hit=hit, sh=sh, mclass=mclass, t_ff_count=len(t_ff_names),
                t_f_byte1s=t_f_byte1s, t_has_ff_naming_other=bool(t_ff_names),
                fclass=kind_of(ents[F]), tclass=kind_of(ents[T]))


def _all_row_shuffle(r, F, T, ents, nonedge, tag, rng):
    """Consume RNG exactly as match() does for each matched turn restriction (M4.23 baseline)."""
    cand = [k for k in nonedge if k not in (F, T)]
    if tag.startswith('no_'):
        U = rng.choice(cand) if cand else None
        return _word_ff(F, ents[U]) if U is not None else False
    if tag.startswith('only_'):
        exits = [k for k in cand if kind_of(ents[k]) != 'arr']
        U = rng.choice(exits) if exits else None
        return _word_ff(F, ents[U]) if U is not None else False
    return False


def _strat_report(all_rows, rng, name, out, holdout_mod=2):
    """Stratify no_* rows; RNG consumed in all_rows order (same as match()) for M4.23 shuffle parity."""
    strata = collections.defaultdict(list)
    for row in all_rows:
        r, F, T, ents, nonedge, tag = row[:6]
        sh = _all_row_shuffle(r, F, T, ents, nonedge, tag, rng)
        if not tag.startswith('no_'):
            continue
        info = _no_row(r, F, T, ents, nonedge, tag, random.Random(0))  # hit/mclass only
        info['sh'] = sh
        key = info['fclass'] + '->' + info['tclass']
        strata[key].append((row, info))
        strata['ALL'].append((row, info))
    out('-- %s: per-stratum n/hit/shuffle/verdict (PASS=%s) --' % (name, PASS))
    results = {}
    for key in sorted(strata, key=lambda k: (-len(strata[k]), k)):
        items = strata[key]
        n = len(items); hit = sum(1 for _, i in items if i['hit']); sh = sum(1 for _, i in items if i['sh'])
        ok, why = verdict(n, hit, sh)
        tr = [(rw, i) for rw, i in items if not _holdout(rw[0]['id'], holdout_mod, 1)]
        te = [(rw, i) for rw, i in items if _holdout(rw[0]['id'], holdout_mod, 1)]

        def _v(it):
            if not it:
                return (0, 0, 0, False, 'n=0')
            nn = len(it); hh = sum(1 for _, i in it if i['hit']); ss = sum(1 for _, i in it if i['sh'])
            o, w = verdict(nn, hh, ss); return (nn, hh, ss, o, w)
        tn, th, ts, tok, twhy = _v(tr)
        en, eh, es, eok, ewhy = _v(te)
        out('  %-10s n=%4d hit=%4d (%.1f%%) shuf=%4d (%.1f%%) gap=%+.3f  %s (%s)' % (
            key, n, hit, 100 * hit / n if n else 0, sh, 100 * sh / n if n else 0,
            (hit - sh) / n if n else 0, 'PASS' if ok else 'FAIL', why))
        if key != 'ALL' and n >= 10:
            out('    holdout(train id%%2==0): n=%d hit=%d (%.1f%%) %s | test(id%%2==1): n=%d hit=%d (%.1f%%) %s' % (
                tn, th, 100 * th / tn if tn else 0, 'PASS' if tok else 'FAIL',
                en, eh, 100 * eh / en if en else 0, 'PASS' if eok else 'FAIL'))
        results[key] = dict(n=n, hit=hit, shuf=sh, ok=ok,
                            train=dict(n=tn, hit=th, shuf=ts, ok=tok),
                            test=dict(n=en, hit=eh, shuf=es, ok=eok))
    return strata, results


def deepen(tile, imf, level=1, seed=42, out=print):
    """M4.30: stratify by entry class, detect mapping anomalies, cluster remaining misses,
    test held-out subset verdicts. Pre-stated PASS not lowered."""
    rels, reasons, rows, rng, mapping = _deep_rows(tile, imf, level, seed, out)
    out('=== M4.30 deepen: %s level %d (seed=%d) ===' % (os.path.basename(tile), level, seed))
    out('restrictions read: %d' % len(rels))
    out('not matched reasons: %s' % dict(reasons))
    out('mapping diagnostics (named): %s' % dict(mapping))
    out('note: "bearings do not match the OSM ways" conflates count mismatch (osm bearings != tile non-edge entries) and angle mismatch; mapping diagnostics disambiguate.')
    no_rows = [rw for rw in rows if rw[5].startswith('no_')]
    only_rows = [rw for rw in rows if rw[5].startswith('only_')]
    out('matched turn restrictions: total=%d no_*=%d only_*=%d' % (len(rows), len(no_rows), len(only_rows)))
    mq = collections.Counter()
    for rw in no_rows:
        am, dup, feq = rw[6], rw[7], rw[8]
        if dup:
            mq['dup_osm_way_bearing'] += 1
        if feq:
            mq['osm_from_eq_to'] += 1
        if am < 10:
            mq['ambiguous_margin_lt10deg'] += 1
        elif am < 15:
            mq['ambiguous_margin_10-15deg'] += 1
        elif am < 25:
            mq['ambiguous_margin_15-25deg'] += 1
        else:
            mq['ambiguous_margin_ge25deg_or_unique'] += 1
    out('-- matched no_* mapping quality (named, counted) --')
    for k in ('dup_osm_way_bearing', 'osm_from_eq_to', 'ambiguous_margin_lt10deg',
              'ambiguous_margin_10-15deg', 'ambiguous_margin_15-25deg',
              'ambiguous_margin_ge25deg_or_unique'):
        out('  %-42s %d / %d' % (k, mq[k], len(no_rows)))
    rng2 = random.Random(seed)
    strata, results = _strat_report(rows, rng2, 'no_*', out)  # RNG consumed in match() order
    rng3 = random.Random(seed)
    miss = collections.Counter()
    for rw in no_rows:
        r, F, T, ents, nonedge, tag = rw[:6]
        info = _no_row(r, F, T, ents, nonedge, tag, rng3)
        if info['hit']:
            continue
        miss['total'] += 1
        miss['mclass:' + info['mclass']] += 1
        miss['tag:' + tag] += 1
        miss['stratum:' + info['fclass'] + '->' + info['tclass']] += 1
        if rw[8]:
            miss['osm_from_eq_to'] += 1
        if rw[7]:
            miss['dup_osm_way_bearing'] += 1
        if rw[6] < 15:
            miss['ambiguous_margin_lt15'] += 1
        if info['t_has_ff_naming_other']:
            miss['T_has_ff_naming_other'] += 1
        if info['t_ff_count'] == 0:
            miss['T_has_no_ff_words'] += 1
        if info['t_f_byte1s']:
            miss['T_has_word_naming_F_byte1:' + str(info['t_f_byte1s'])] += 1
    out('-- no_* miss clustering (named, counted; over %d misses) --' % miss['total'])
    for k in ('osm_from_eq_to', 'dup_osm_way_bearing', 'ambiguous_margin_lt15',
              'T_has_ff_naming_other', 'T_has_no_ff_words'):
        if k in miss:
            out('  %-42s %d' % (k, miss[k]))
    for prefix in ('mclass:', 'tag:', 'stratum:'):
        out('  [%s]' % prefix[:-1])
        for k, v in sorted(((k, v) for k, v in miss.items() if k.startswith(prefix)), key=lambda x: -x[1]):
            out('    %-40s %d' % (k[len(prefix):], v))
    for sk in ('arr->lv', 'two->lv', 'arr->two', 'two->two'):
        items = strata.get(sk, [])  # (row, info) pairs
        rngs = random.Random(seed)
        mitems = []
        for row, _ in items:
            r, F, T, ents, nonedge, tag = row[:6]
            info = _no_row(r, F, T, ents, nonedge, tag, rngs)
            if not info['hit']:
                mitems.append((row, info))
        if not mitems:
            continue
        sub = collections.Counter()
        for row, info in mitems:
            sub['mclass:' + info['mclass']] += 1
            sub['tag:' + row[5]] += 1
            if row[8]:
                sub['osm_from_eq_to'] += 1
            if row[6] < 15:
                sub['ambiguous_margin_lt15'] += 1
            if info['t_has_ff_naming_other']:
                sub['T_has_ff_naming_other'] += 1
        out('-- misses within stratum %s (n_miss=%d of %d) --' % (sk, len(mitems), len(items)))
        for k, v in sub.most_common():
            out('    %-40s %d' % (k, v))
    passing = [(k, v) for k, v in results.items() if v['ok'] and k != 'ALL']
    passing_test = [(k, v) for k, v in results.items()
                    if v['test'].get('ok') and k != 'ALL' and v['test']['n'] >= 20]
    out('-- held-out (deterministic by relation id sha256 mod2, bucket1=test) --')
    out('  pre-defined strata (entry-class pairs, no outcome fitting); evaluated on held-out test bucket.')
    if passing_test:
        for k, v in passing_test:
            out('  CANDIDATE reaching PASS on held-out test: %s test n=%d hit=%d' % (k, v['test']['n'], v['test']['hit']))
    else:
        out('  no pre-defined stratum reaches PASS on held-out test (n>=20).')
    if passing and not passing_test:
        out('  note: strata passing on full set but not on held-out test: %s' % [k for k, _ in passing])
    out('-- conclusion inputs --')
    allr = results.get('ALL', {})
    out('  overall no_*: n=%s hit=%s shuf=%s %s' % (allr.get('n'), allr.get('hit'), allr.get('shuf'),
                                                      'PASS' if allr.get('ok') else 'FAIL'))
    return dict(level=level, no_n=len(no_rows), results=results, mapping=dict(mapping), reasons=dict(reasons))


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
    # M4.30: holdout deterministic and roughly balanced
    assert _holdout('r120176', 2, 1) == _holdout('r120176', 2, 1); n += 1
    buckets = [_holdout('r%d' % i, 2, 1) for i in range(200)]
    assert 60 < sum(buckets) < 140; n += 1
    osm2 = [('a', 0.0), ('b', 90.0)]; tb2 = [(0, 1.0), (1, 89.0)]; m2 = {'a': 0, 'b': 1}
    assert _amb_margin(osm2, tb2, 'a', 'b', m2) > 80; n += 1
    osm3 = [('a', 0.0), ('b', 90.0)]; tb3 = [(0, 1.0), (1, 8.0), (2, 89.0)]; m3 = {'a': 0, 'b': 2}
    assert _amb_margin(osm3, tb3, 'a', 'b', m3) < 10; n += 1
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--selftest', action='store_true')
    sub = ap.add_subparsers(dest='cmd')
    c = sub.add_parser('census'); c.add_argument('tiles', nargs='+')
    m = sub.add_parser('match'); m.add_argument('tile'); m.add_argument('imf')
    m.add_argument('--level', type=int, choices=(1, 2), default=1)
    m.add_argument('--seed', type=int, default=42); m.add_argument('--show', type=int, default=0)
    au = sub.add_parser('audit'); au.add_argument('tile'); au.add_argument('imf')
    au.add_argument('--level', type=int, choices=(1, 2), default=1)
    au.add_argument('--seed', type=int, default=42)
    dp = sub.add_parser('deepen'); dp.add_argument('tile'); dp.add_argument('imf')
    dp.add_argument('--level', type=int, choices=(1, 2), default=1)
    dp.add_argument('--seed', type=int, default=42)
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
    if a.cmd == 'audit':
        audit(a.tile, a.imf, a.level, a.seed); return 0
    if a.cmd == 'deepen':
        deepen(a.tile, a.imf, a.level, a.seed); return 0
    if a.cmd == 'coarse':
        return coarse(a.lev_tile, a.lon, a.lat)
    ap.print_help(); return 2


if __name__ == '__main__':
    sys.exit(main())
