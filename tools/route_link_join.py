#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Route-link id (M4.39): which tile section-2 field can a name, an ADDRE street or a
LCTBL001 road be joined to? Controlled join tests with shuffled/rotated nulls.

Section 2 (router graph, level 1) is read with `clarion_rd.parse_record`; section 1
(drawn shapes, level-1 `0x00fa` even records + odd partner names) with
`fa_encode.parse_record`. Every test states its key, its corpus and its null.

    route_link_join.py sec1  TILE [--every K] [--seed S]
        each section-2 entry field F (link id, w4, w5, travel time a, length b, far node
        index, own node index) used as a key (parcel, class, F) into the parcel's drawn
        shape links; a hit = a shape link with that key has a drawn end at the entry's
        node.  Null 1: F shuffled among the record's entries.  Null 2: the shape record
        of another parcel.  Also the node-coordinate key and the named share of hits.
    route_link_join.py addre TILE ADDRE.cmp [ADDRE.cmp ...] [--every K]
        every ADDRE street record whose parcel is in TILE: its point refs (word offset
        from the shape record's geometry unit) followed to a drawn point, its shape label
        compared with the street name, and the point's link (class, id) looked up in the
        parcel's section-2 record.  Null: the same refs applied to another record's parcel.
    route_link_join.py lctbl TILE LCTBL001.DAT [--every K]
        names of section-2-joined shapes against LCTBL001 name slots, then every numeric
        LCTBL field (attrs, class, footer u16) against every section-2 field of the
        name-matched pairs.  Null: the pairs re-drawn at random from the matched pool.
    route_link_join.py --selftest

Read-only; prints counts only (no vendor bytes).
"""
import argparse, collections, os, random, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'ze0-viewer', 'tools_ze0'))
import clarion_rd, fa_encode, rd_check, clarion_bg       # noqa: E402
from tile_scan import TileScan                            # noqa: E402

# section-2 entry fields tested as a link key (name -> getter on (node index, entry))
FIELDS = collections.OrderedDict([
    ('link id (word 3 & 0x1fff)', lambda i, e: e['id'] & 0x1fff),
    ('w4 (word 1)', lambda i, e: e['w4']),
    ('w5 (word 2)', lambda i, e: e['w5']),
    ('travel time a (word 5)', lambda i, e: e['a']),
    ('length b (word 6)', lambda i, e: e['b']),
    ('far node index (word 0)', lambda i, e: e['other'] & 0x3fff),
    ('own node index', lambda i, e: i),
])


# ---------------------------------------------------------------- tile access

def bg_labels(bg):
    """{word offset: label} of an odd partner record's names section (Latin-1)."""
    r = clarion_bg.parse_record(bg)
    s = r['sections'].get('names')
    out = {}
    if not s: return out
    nl = struct.unpack_from('>H', s, 2)[0]; p = 24
    for _ in range(nl):
        if p + 10 > len(s): break
        _typ, flags = struct.unpack_from('>HH', s, p)
        q = p + 8 + (2 if flags & 0x4000 else 0); ln = struct.unpack_from('>H', s, q)[0]
        out[p // 2] = s[q + 2:q + 2 + ln].rstrip(b'\0').decode('latin-1')
        p = q + 2 + ln + (ln & 1)
    return out


def label_parts(label):
    """Upper-case name strings of a `1=NAME:ALT;2=REF` label."""
    out = []
    for part in label.split(';'):
        if len(part) > 2 and part[1] == '=': part = part[2:]
        out += [x.strip().upper() for x in part.split(':') if x.strip()]
    return out


def plain(r):
    try:
        return r.plain()
    except Exception:
        return None


class Tile:
    """Level-1 section-2 records and their section-1 shape partners, by parcel code."""

    def __init__(self, path, every=1):
        self.t = TileScan(path)
        self.sec2 = {}; self.unreadable = collections.Counter()
        for n, r in enumerate(self.t.records(section=2, level=1)):
            if n % every: continue
            pl = plain(r)
            if pl is None: self.unreadable['section 2'] += 1; continue
            self.sec2[struct.unpack_from('>HH', pl, 0)] = r
        by = {}
        for r in self.t.records(section=1, level=1):
            by[(r.dir_off, r.slot, r.k)] = r
        self.shape_rec = {}
        for (d, s, k), r in by.items():
            if k % 2: continue
            pl = plain(r)
            if pl is None: self.unreadable['section 1 even'] += 1; continue
            if len(pl) < 44 or struct.unpack_from('>H', pl, 4)[0] != 0x00fa: continue
            self.shape_rec[struct.unpack_from('>HH', pl, 0)] = (r, by.get((d, s, k + 1)))
        self._shapes = {}; self._graphs = {}

    def graph(self, code):
        if code in self._graphs: return self._graphs[code]
        r = self.sec2.get(code)
        rec = clarion_rd.parse_record(rd_check.part_a(plain(r), 1)) if r is not None else {}
        rec = rec if 'nnodes' in rec and not rec.get('error') else None
        if len(self._graphs) > 4096: self._graphs.clear()
        self._graphs[code] = rec
        return rec

    def shapes(self, code):
        """(plain words, unit, shapes with 'label') of a parcel's drawn record, or None."""
        if code in self._shapes: return self._shapes[code]
        out = None
        if code in self.shape_rec:
            r, bg = self.shape_rec[code]
            pl = plain(r); bgp = plain(bg) if bg else None
            try:
                _, unit, shapes = fa_encode.parse_record(pl)
            except Exception:
                shapes = None
            if shapes is not None:
                names = bg_labels(bgp) if bgp else {}
                for s in shapes: s['label'] = names.get(s['name'], '')
                w = struct.unpack('>%dH' % (len(pl) // 2), pl)
                out = (w, unit, shapes)
        if len(self._shapes) > 4096: self._shapes.clear()
        self._shapes[code] = out
        return out


# ---------------------------------------------------------------- joins (pure)

def link_ends(shapes):
    """{(class, link id & 0x1fff): (first point, last point, label)} of drawn shapes."""
    out = {}
    for s in shapes:
        for lid, (a, b) in zip(s['links'], s['ends']):
            out.setdefault((s['cls'], lid & 0x1fff), (a, b, s.get('label', '')))
    return out


def entries(rec):
    """[(node index, node (x, y), entry)] of the record's in-parcel (non-edge) entries."""
    return [(i, (nd['x'], nd['y']), e) for i, nd in enumerate(rec['nodes'])
            for e in nd['entries'] if not e['cls'] & 0x8000]


def key_hits(ents, ends, getter, values=None):
    """Entries whose (class, value) names a drawn link with an end at the entry's node."""
    n = 0
    for k, (i, xy, e) in enumerate(ents):
        v = getter(i, e) if values is None else values[k]
        hit = ends.get((e['cls'] & 0xf, v & 0x1fff))
        if hit and xy in hit[:2]: n += 1
    return n


def sec1_test(pairs, rng):
    """pairs: [(rec, shapes, other parcel's shapes or None)] -> counters per field."""
    c = collections.Counter()
    for rec, shapes, other in pairs:
        ents = entries(rec)
        if not ents: continue
        ends = link_ends(shapes)
        oends = link_ends(other) if other is not None else None
        c['records'] += 1; c['entries'] += len(ents)
        nodes = {xy for _, xy, _ in ents}
        pts = {p for a, b, _ in ends.values() for p in (a, b)}
        c['node coord in drawn link ends'] += len(nodes & pts); c['nodes'] += len(nodes)
        if oends is not None:
            opts = {p for a, b, _ in oends.values() for p in (a, b)}
            c['node coord, other parcel'] += len(nodes & opts); c['nodes, other parcel'] += len(nodes)
        for name, get in FIELDS.items():
            c[(name, 'hit')] += key_hits(ents, ends, get)
            vals = [get(i, e) for i, _, e in ents]; rng.shuffle(vals)
            c[(name, 'shuffled')] += key_hits(ents, ends, get, vals)
            if oends is not None:
                c[(name, 'other parcel')] += key_hits(ents, oends, get)
                c[(name, 'other n')] += len(ents)
        # names of the links reached through the link id
        for i, xy, e in ents:
            hit = ends.get((e['cls'] & 0xf, e['id'] & 0x1fff))
            if hit and xy in hit[:2]:
                c['linked'] += 1; c['linked named'] += bool(hit[2])
    return c


HOPS = {0x40: (1, 0), 0x50: (0, 1), 0x60: (-1, 0), 0x70: (0, -1)}


def resolve_refs(refs, code, get_shapes, get_graph):
    """Follow one ADDRE record's refs from parcel `code`. Yields per ref a dict or a
    string why it stopped (unknown hop tag / parcel not read)."""
    rc = code_rc(*code)
    if rc is None:
        yield 'sub-parcel code'; return
    row, col = rc
    for tag, flag, v in refs:
        if tag >= 0x40:
            if tag not in HOPS:
                yield 'hop tag %#x not decoded' % tag; return
            dr, dc = HOPS[tag]; row, col = row + dr, col + dc
            continue
        pc = clarion_bg.parcel_code(1, row, col)
        sh = get_shapes(pc)
        if sh is None:
            yield 'parcel not read'; continue
        w, unit, shapes = sh
        word = unit + v
        s = next((s for s in shapes if s['at'] <= word < s['at'] + s['length']), None)
        role = s['points'].get(word) if s else None
        out = dict(lands=role is not None, label=s['label'] if s else '', link=None, node=None, sec2=None)
        if role is not None:
            out['role'] = role[0]
            xy = (w[word] & 0x7ff, w[word + 1] & 0x7ff)
            g = get_graph(pc)
            if g is not None:
                keys = {(e['cls'] & 0xf, e['id'] & 0x1fff) for nd in g['nodes'] for e in nd['entries']
                        if not e['cls'] & 0x8000}
                out['sec2'] = True
                out['link'] = role[1] is not None and (s['cls'], role[1] & 0x1fff) in keys
                if role[0] in ('start', 'end'):
                    out['node'] = xy in {(nd['x'], nd['y']) for nd in g['nodes']}
        yield out


def code_rc(la, lo):
    """Absolute level-1 (row, col) of a whole-parcel code; None for a sub-parcel."""
    if (la >> 2) & 3 != 3 or (lo >> 2) & 3 != 3: return None
    c = ((la >> 15) & 1) << 8 | lo >> 8
    return (((la >> 8) & 0x7f) << 6 | ((la >> 4) & 15) << 2 | (la & 3),
            c << 6 | ((lo >> 4) & 15) << 2 | (lo & 3))


def addre_tally(c, prefix, street, outs):
    for o in outs:
        if isinstance(o, str):
            c[(prefix, 'stopped: ' + o)] += 1; continue
        c[(prefix, 'refs')] += 1
        c[(prefix, 'lands on a drawn point')] += o['lands']
        if o['lands']:
            c[(prefix, 'label names the street')] += street.upper() in label_parts(o['label'])
            if o['sec2']:
                c[(prefix, 'with a section-2 record')] += 1
                c[(prefix, 'point link (class, id) in section 2')] += bool(o['link'])
            if o['node'] is not None:
                c[(prefix, 'node refs (start/end)')] += 1
                c[(prefix, 'node coord is a section-2 node')] += o['node']


# ---------------------------------------------------------------- ADDRE / LCTBL input

def street_name(r):
    """Street name of a 2011 c0 record: the last 2*LL bytes, LL the second byte of the
    name section that follows the refs and items (`TT LL 00 ff`; TT is per shard,
    0x03/0x04/0x05 seen). None for a c8 continuation record."""
    if r[0] != 0xc0: return None
    p = 8 + r[2] * 2 - 4 + r[3] * 2
    if p + 4 > len(r) or r[p + 2:p + 4] != b'\x00\xff': return None
    ll = r[p + 1]
    return r[len(r) - 2 * ll:].rstrip(b'\0').decode('latin-1').strip('"')


def addre_records(path, keep=None):
    """[(street name, parcel code, refs)] of an ADDRE .cmp (2011 framing: c0/c8 records,
    stops at the first record of the undecoded c1 kind). A c8 record continues the
    street of the c0 before it."""
    import addre, addre_io
    d = addre.sections(addre.load_blob(path))['record_bytes']
    out, pos, last = [], 0, None
    while pos + 2 <= len(d) and d[pos] in (0xc0, 0xc8):
        r = d[pos:pos + 2 * d[pos + 1]]; pos += 2 * d[pos + 1]
        p = addre_io.parse_name_record(r)
        if r[0] == 0xc0: last = street_name(r)
        if keep is None or (p['lat'], p['lon']) in keep:
            out.append((last or '', (p['lat'], p['lon']), p['refs']))
    return out


def lctbl_index(path):
    import lctbl_names, lctbl_records
    from pathlib import Path
    data = Path(path).read_bytes()
    out = collections.defaultdict(list)
    for st in lctbl_names.scan_streams(data):
        for rec in lctbl_records.parse_stream(st['data']):
            for nm in rec['names']:
                if nm: out[nm.decode('latin-1').strip().upper()].append(rec)
    return out


def lctbl_numbers(rec):
    f = rec['footer']
    return ([('attr%d' % i, b) for i, b in enumerate(rec['attrs'])] + [('class', rec['class_code'])]
            + [('footer u16 %d' % i, struct.unpack_from('>H', f, 2 * i)[0]) for i in range(len(f) // 2)])


def link_numbers(code, xy, e):
    return [('link id', e['id'] & 0x1fff), ('w4', e['w4']), ('w5', e['w5']), ('a', e['a']), ('b', e['b']),
            ('class word', e['cls']), ('parcel w0', code[0]), ('parcel w1', code[1]), ('node x', xy[0]), ('node y', xy[1])]


def numeric_join(pairs, rng):
    """pairs: [(sec2 numbers, LCTBL numbers)] -> {(sec2 field, lctbl field): (hits, shuffled hits)}."""
    out = collections.Counter()
    if not pairs: return out
    lt = [b for _, b in pairs]
    sh = lt[:]; rng.shuffle(sh)
    for (a, b), b2 in zip(pairs, sh):
        for fa, va in a:
            for fb, vb in b:
                if va == vb: out[(fa, fb, 'hit')] += 1
            for fb, vb in b2:
                if va == vb: out[(fa, fb, 'null')] += 1
    return out


# ---------------------------------------------------------------- commands

def pct(a, b):
    return '%d/%d (%.1f%%)' % (a, b, 100.0 * a / b) if b else '0/0'


def cmd_sec1(a):
    rng = random.Random(a.seed)
    T = Tile(a.tile, a.every)
    codes = sorted(c for c in T.sec2 if c in T.shape_rec)
    pairs = []
    for k, code in enumerate(codes):
        g = T.graph(code); sh = T.shapes(code)
        if g is None or sh is None: continue
        oth = T.shapes(codes[(k + 1) % len(codes)]) if len(codes) > 1 else None
        pairs.append((g, sh[2], oth[2] if oth else None))
        if len(pairs) >= 512:
            c = sec1_test(pairs, rng); a.c.update(c); pairs = []
    a.c.update(sec1_test(pairs, rng))
    c = a.c
    print('%s: level-1 section-2 records read %d (every %d), with a drawn partner %d, tested %d'
          % (os.path.basename(a.tile), len(T.sec2), a.every, len(codes), c['records']))
    print('entries (in-parcel) %d; unreadable records skipped %s' % (c['entries'], dict(T.unreadable)))
    print('%-28s %-24s %-24s %-24s' % ('key field', 'hit', 'shuffled null', 'other-parcel null'))
    for name in FIELDS:
        print('%-28s %-24s %-24s %-24s' % (name, pct(c[(name, 'hit')], c['entries']),
                                           pct(c[(name, 'shuffled')], c['entries']),
                                           pct(c[(name, 'other parcel')], c[(name, 'other n')])))
    print('node coordinate in drawn link ends: %s; other parcel null: %s'
          % (pct(c['node coord in drawn link ends'], c['nodes']), pct(c['node coord, other parcel'], c['nodes, other parcel'])))
    print('entries linked by link id %d, of them on a named shape %s' % (c['linked'], pct(c['linked named'], c['linked'])))
    return 0


def cmd_addre(a):
    T = Tile(a.tile)
    parcels = set(T.shape_rec)
    recs = []
    for path in a.addre:
        recs += addre_records(path, parcels)
    recs = recs[::a.every]
    c = collections.Counter()
    names = collections.Counter()
    for k, (name, code, refs) in enumerate(recs):
        addre_tally(c, 'real', name, list(resolve_refs(refs, code, T.shapes, T.graph)))
        # null: same refs from the next record's parcel (a different parcel)
        j = k + 1
        while j < len(recs) + k and recs[j % len(recs)][1] == code: j += 1
        oc = recs[j % len(recs)][1]
        if oc != code:
            addre_tally(c, 'null', name, list(resolve_refs(refs, oc, T.shapes, T.graph)))
        names[name] += 1
    print('%s: ADDRE street records with a parcel in the tile %d (%d distinct names)'
          % (os.path.basename(a.tile), len(recs), len(names)))
    keys = ['refs', 'lands on a drawn point', 'label names the street', 'with a section-2 record',
            'point link (class, id) in section 2', 'node refs (start/end)', 'node coord is a section-2 node']
    print('%-40s %-26s %-26s' % ('outcome', 'real', 'parcel-rotation null'))
    for k in keys:
        print('%-40s %-26s %-26s' % (k, c[('real', k)], c[('null', k)]))
    for (p, k), v in sorted(c.items()):
        if k.startswith('stopped'): print('%s %s: %d' % (p, k, v))
    return 0


def cmd_lctbl(a):
    rng = random.Random(a.seed)
    T = Tile(a.tile, a.every)
    idx = lctbl_index(a.lctbl)
    c = collections.Counter(); pairs = []; multi = collections.Counter()
    for code in sorted(T.sec2):
        g = T.graph(code); sh = T.shapes(code)
        if g is None or sh is None: continue
        ends = link_ends(sh[2])
        for i, xy, e in entries(g):
            hit = ends.get((e['cls'] & 0xf, e['id'] & 0x1fff))
            if not (hit and xy in hit[:2]): continue
            c['linked'] += 1
            parts = label_parts(hit[2])
            if not parts: continue
            c['named'] += 1
            m = [r for p in parts for r in idx.get(p, [])]
            if m:
                c['name in LCTBL'] += 1; multi[min(len(m), 100)] += 1
                pairs.append((link_numbers(code, xy, e), lctbl_numbers(rng.choice(m))))
    print('%s: section-2 entries linked to a drawn shape %d, named %d, name found in LCTBL %s'
          % (os.path.basename(a.tile), c['linked'], c['named'], pct(c['name in LCTBL'], c['named'])))
    print('LCTBL records per matched name: median %s, one-to-one %d'
          % (sorted(multi.elements())[len(pairs) // 2] if pairs else '-', multi[1]))
    nj = numeric_join(pairs, rng)
    print('numeric equality, sec2 field vs LCTBL field over %d name-matched pairs (hit vs shuffled pairing):' % len(pairs))
    rows = sorted({(fa, fb) for fa, fb, _ in nj}, key=lambda k: -nj[k + ('hit',)])
    print('  top by hits:')
    for fa, fb in rows[:a.top]:
        h, n = nj[(fa, fb, 'hit')], nj[(fa, fb, 'null')]
        print('  %-12s = %-14s %-24s null %6d  ratio %.2f' % (fa, fb, pct(h, len(pairs)), n, h / max(n, 1)))
    rows = [k for k in rows if nj[k + ('hit',)] >= 100]
    rows.sort(key=lambda k: -nj[k + ('hit',)] / max(nj[k + ('null',)], 1))
    print('  top by hit/null ratio (hits >= 100):')
    for fa, fb in rows[:a.top]:
        h, n = nj[(fa, fb, 'hit')], nj[(fa, fb, 'null')]
        print('  %-12s = %-14s %-24s null %6d  ratio %.2f' % (fa, fb, pct(h, len(pairs)), n, h / max(n, 1)))
    return 0


# ---------------------------------------------------------------- selftest

def _synth():
    """One parcel: three links in class 2 between four nodes; shapes drawn on them."""
    nodes = [(10, 10), (20, 10), (20, 30), (40, 30)]
    links = [(1, 0, 1), (2, 1, 2), (3, 2, 3)]
    rec = dict(nodes=[dict(x=x, y=y, entries=[]) for x, y in nodes])
    for lid, i, j in links:
        for me, far, flag in ((i, j, 0), (j, i, 0x2000)):
            rec['nodes'][me]['entries'].append(dict(other=far, w4=7, w5=0, id=lid | flag, cls=0x0202,
                                                    a=lid * 5, b=lid * 11))
    shapes = [dict(cls=2, links=[1, 2], ends=[(nodes[0], nodes[1]), (nodes[1], nodes[2])], label='1=MAIN ST;2=A1'),
              dict(cls=2, links=[3], ends=[(nodes[2], nodes[3])], label='')]
    other = [dict(cls=2, links=[1, 2, 3], ends=[((0, 0), (1, 1)), ((1, 1), (2, 2)), ((2, 2), (3, 3))], label='')]
    return rec, shapes, other


def selftest():
    rec, shapes, other = _synth()
    c = sec1_test([(rec, shapes, other)], random.Random(1))
    assert c['entries'] == 6, c
    assert c[('link id (word 3 & 0x1fff)', 'hit')] == 6
    assert c[('link id (word 3 & 0x1fff)', 'other parcel')] == 0
    assert c[('w4 (word 1)', 'hit')] == 0          # constant 7 names no link
    assert c[('travel time a (word 5)', 'hit')] == 0
    assert c['node coord in drawn link ends'] == 4 and c['node coord, other parcel'] == 0
    assert c['linked'] == 6 and c['linked named'] == 4
    assert label_parts('1=PERIMETRALE:VIA SCAURI;2=SP54') == ['PERIMETRALE', 'VIA SCAURI', 'SP54']
    # ADDRE resolution on a synthetic drawn record: unit 0, shape at word 0, points at words 7/9/11
    w = [0] * 7 + [10, 10, 20, 10, 20, 30]
    shp = [dict(at=0, length=13, cls=2, label='1=MAIN ST', points={7: ('start', 1), 9: ('end', 1), 11: ('end', 2)})]
    code = clarion_bg.parcel_code(1, 100, 200)
    assert code_rc(*code) == (100, 200)
    gs = lambda pc: (w, 0, shp) if pc == code else None
    gg = lambda pc: rec if pc == code else None
    outs = list(resolve_refs([(2, 0x40, 9), (3, 0x40, 11)], code, gs, gg))
    assert all(o['lands'] and o['link'] and o['node'] for o in outs), outs
    cc = collections.Counter(); addre_tally(cc, 'real', 'Main St', outs)
    assert cc[('real', 'label names the street')] == 2 and cc[('real', 'node coord is a section-2 node')] == 2
    outs = list(resolve_refs([(0x50, 0x40, 0), (2, 0x40, 9)], code, gs, gg))
    assert outs == ['parcel not read'], outs
    assert list(resolve_refs([(0x80, 0x40, 0)], code, gs, gg)) == ['hop tag 0x80 not decoded']
    nj = numeric_join([([('link id', 3)], [('footer u16 0', 3)])] * 4, random.Random(0))
    assert nj[('link id', 'footer u16 0', 'hit')] == 4
    rec = bytes.fromhex('c018' '0a00' 'a61ed11f' '02400470' '02400477' '40400690' '0340069d'
                        '0505' '00ff' '0004000900' '2e000300' '0b' '2250524f42535445 4922'.replace(' ', ''))
    assert street_name(rec) == 'PROBSTEI', street_name(rec)
    assert street_name(b'\xc8' + rec[1:]) is None
    print('route_link_join selftest: OK')
    return 0


def main(argv=None):
    if argv is None: argv = sys.argv[1:]
    if '--selftest' in argv: return selftest()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    for n in ('sec1', 'addre', 'lctbl'):
        p = sp.add_parser(n); p.add_argument('tile')
        p.add_argument('--every', type=int, default=1, help='read every K-th section-2 record')
        p.add_argument('--seed', type=int, default=4039)
        if n == 'addre': p.add_argument('addre', nargs='+')
        if n == 'lctbl':
            p.add_argument('lctbl'); p.add_argument('--top', type=int, default=12)
    a = ap.parse_args(argv); a.c = collections.Counter()
    return {'sec1': cmd_sec1, 'addre': cmd_addre, 'lctbl': cmd_lctbl}[a.cmd](a)


if __name__ == '__main__':
    sys.exit(main())
