# SPDX-License-Identifier: GPL-3.0-or-later
"""Clarion X08-03-00 map tile: read the container into objects and write it back. Header is 0x1000 bytes (strings, level table at 0x1ac, bbox table at 0x2ac, section table at 0x800); past it, each section has a table, directories and record blocks, all 256-byte aligned. Addresses are u32: (offset // 2048) << 8 | (offset % 2048) // 256."""
import struct, zlib

SLOTS = 32
LEVEL_OFF, BBOX_OFF, SECT_OFF, TABLE1_OFF = 0x1ac, 0x2ac, 0x800, 0x1000

def is_zlib(b, off=0):
    """Any zlib stream: CMF low nibble 8, and the 16-bit header checksum valid.
    X08-02-00 (ZE0 2011) uses 78 9c; X08-03-00 uses 58 85 (8 KiB window)."""
    if off + 2 > len(b): return False
    cmf, flg = b[off], b[off + 1]
    return (cmf & 0x0f) == 8 and ((cmf << 8) | flg) % 31 == 0

def addr_of(v): return (v >> 8) * 2048 + (v & 0xff) * 256
def enc_addr(off):
    assert off % 256 == 0
    return (off // 2048) << 8 | (off % 2048) // 256
def pad256(n): return (n + 255) // 256 * 256

def walk(d, off, elen):
    n = struct.unpack_from('>H', d, off)[0]; p = off + 2; out = []
    for _ in range(n):
        sid, cnt = d[p], d[p+1]; p += 2
        out.append((sid, [d[p+i*elen:p+(i+1)*elen] for i in range(cnt)])); p += cnt*elen
    return out, p

def read_tile(d):
    t = dict(header=bytearray(d[:TABLE1_OFF]), sections=[], order=[], _src=d)
    levels, _ = walk(d, LEVEL_OFF, 4)
    sect_entries = []
    p = SECT_OFF
    while True:
        a, c = struct.unpack_from('>IH', d, p); p += 6
        if a == 0xffffffff: break
        sect_entries.append((addr_of(a), c, a))
    for (sid, lv), (taddr, count, ttag) in zip(levels, sect_entries):
        nlev = len(lv)
        nw = struct.unpack_from('>H', d, taddr)[0]
        w = struct.unpack_from('>%dH' % nw, d, taddr)
        sec = dict(id=sid, count=count, taddr=taddr, ttag=ttag, levels=[], table_words=nw)
        si = len(t['sections']); t['order'].append((taddr, 'table', si))
        for li, e in enumerate(lv):
            level, typ, cnt = e[0], e[1], struct.unpack('>H', e[2:])[0]
            o = w[1+li]
            L = dict(level=level, typ=typ, dirs=[])
            if o != 0xffff:
                glen, gcnt = w[o], w[o+1]
                assert glen == 2 + 6*gcnt and gcnt == cnt, (glen, gcnt, cnt)
                for k in range(gcnt):
                    y1, y0, x0, x1, z, tg = w[o+2+6*k:o+8+6*k]
                    D = read_dir(d, addr_of((z << 16) | tg), box=(y1, y0, x0, x1), nslots=16 if level == 3 else SLOTS,
                                section=sid)
                    D['ptr_tag'] = (z << 16) | tg
                    di = len(L['dirs']); L['dirs'].append(D)
                    t['order'].append((D['off'], 'dir', si, li, di))
                    if D['slots']:
                        t['order'].append((min(s['block_off'] for s in D['slots'].values()), 'blocks', si, li, di))
            else:
                assert cnt == 0
            sec['levels'].append(L)
        t['sections'].append(sec)
    t['order'].sort()
    return t

def read_dir(d, off, box, nslots=SLOTS, section=1):
    kind, a, b, y, x, typ = struct.unpack_from('>HHHHHH', d, off)
    # ZE0 X08-02-00: body size follows the directory kind (the first header word)
    # and the row count is the header's third word. 2017 cards use 256 for section
    # 2 at both levels; ZE0's section-2 level-2 directory is 512 instead, and its
    # level-4/5 bodies are 704/176. 0x000a (level 6) holds one raw 8-byte pair.
    BODY = {0x000a: 8, 0x0200: 88, 0x0826: 256, 0x03e4: 176,
            0x1046: 256, 0x2046: 512, 0x2146: 512, 0x2346: 512,
            0x1146: 256, 0x3cde: 704}
    body = BODY.get(kind, 512 if section == 1 else 256)
    nslots = b or nslots
    D = dict(off=off, kind=kind, ab=(a, b), y=y, x=x, typ=typ, box=box, body=body, slots={}, nslots=nslots)
    p = off + 12
    for i in range(nslots):
        tag = struct.unpack_from('>I', d, p)[0]
        raw = d[p+4:p+4+body]
        if tag not in (0xffffffff, 0x7fffffff):
            q0 = addr_of(tag)
            # A plausible block starts after the 0x1000 header and is not a
            # 0xFF fill.  B30R048's 0x2146 directory has a 0x40 tag pointing
            # into the level-2 directory; treat that as an empty slot.
            if q0 < TABLE1_OFF or q0 + 2 > len(d) or d[q0:q0+2] == b'\xff\xff' or tag & 0x80000000:
                D.setdefault('empty_bodies', {})[i] = raw
                D.setdefault('empty_tags', {})[i] = tag
                p += 4 + body
                continue
            words = struct.unpack_from('>%dI' % (body//4), raw)
            recs = []
            q = q0
            for k in range(body//8):
                ln, X = words[2*k], words[2*k+1]
                if ln in (0xffffffff, 0x7fffffff): continue
                flag = ln & 0x80000000
                ln &= 0x7fffffff
                # A slot body can end its pair table early and carry a raw
                # tail (B30R048 slot 21 at body+0xE8).  Sizes above 0x10000
                # words are not pairs; stop and leave the tail in the body.
                if ln > 0x10000 or X > 0x10000:
                    break
                # zlib records: ln = compressed words, X = inflated words.
                # raw records (no 58 85 magic): two parts of ln and X words.
                n = 2*ln if is_zlib(d, q) else 2*(ln + X)
                recs.append(dict(k=k, raw=d[q:q+n], words=X, flag=flag)); q += n
            D['slots'][i] = dict(tag=tag, body=raw, recs=recs, block_off=addr_of(tag), block_end=q)
        else:
            D.setdefault('empty_bodies', {})[i] = raw
            D.setdefault('empty_tags', {})[i] = tag
        p += 4 + body
    # Some ZE0 directories (kind 0x2146 and relatives) declare a larger size
    # in header word 0 than 12 + nslots*(4+body).  The difference is a trailing
    # table after the slots; keep it verbatim so the directory round-trips.
    declared = 2 * struct.unpack_from('>H', d, off)[0]
    extra = declared - (12 + nslots * (4 + body))
    if 0 < extra <= 4096 and p + extra <= len(d):
        D['tail'] = d[p:p + extra]
        p += extra
    D['end'] = p
    return D

def dir_bytes(D, slot_addrs):
    out = bytearray(struct.pack('>HHHHHH', D['kind'], *D['ab'], D['y'], D['x'], D['typ']))
    for i in range(D.get('nslots', SLOTS)):
        s = D['slots'].get(i)
        if s is None:
            tag = D.get('empty_tags', {}).get(i)
            out += (struct.pack('>I', tag) if tag is not None else b'\xff' * 4)
            out += D.get('empty_bodies', {}).get(i, b'\xff' * D['body']); continue
        addr = slot_addrs[i]
        if addr == s['block_off']:
            tag = s['tag']
        else:
            tag = enc_addr(addr)
        out += struct.pack('>I', tag) + s['body']
    out += D.get('tail', b'')
    return bytes(out)

def block_bytes(s):
    return b''.join(r['raw'] for r in s['recs'])

def table_words(sec):
    lv_offs = []; groups = []
    pos = 1 + len(sec['levels'])
    for L in sec['levels']:
        if not L['dirs']: lv_offs.append(0xffff); continue
        lv_offs.append(pos); groups.append(L); pos += 2 + 6*len(L['dirs'])
    return pos, lv_offs, groups

def default_order(t):
    """Layout for a new tile: per section, table, then per level its dirs, then its blocks."""
    order = []
    for si, sec in enumerate(t['sections']):
        order.append((0, 'table', si))
        for li, L in enumerate(sec['levels']):
            for di in range(len(L['dirs'])): order.append((0, 'dir', si, li, di))
            for di, D in enumerate(L['dirs']):
                if D['slots']: order.append((0, 'blocks', si, li, di))
    return order

def _try_preserve_random(t, order, src):
    """Place every component at its original offset (random access).

    Returns the rebuilt bytes when the tile is unchanged (all component bytes
    match src at their original offsets and intervals are disjoint), else None.
    Handles non-monotonic layouts such as B30R048R, where a slot block can live
    in an earlier gap."""
    where = {}
    for o in order:
        kind = o[1]
        if kind == 'table':
            where[('table', o[2])] = o[0]
        elif kind == 'dir':
            where[('dir', o[2], o[3], o[4])] = o[0]
        else:
            si, li, di = o[2:]
            D = t['sections'][si]['levels'][li]['dirs'][di]
            for i in D['slots']:
                where[('slot', si, li, di, i)] = D['slots'][i]['block_off']

    intervals = []
    slot_bytes = {}
    for o in order:
        if o[1] != 'blocks':
            continue
        si, li, di = o[2:]
        D = t['sections'][si]['levels'][li]['dirs'][di]
        for i in D['slots']:
            bb = block_bytes(D['slots'][i])
            off = where[('slot', si, li, di, i)]
            slot_bytes[('slot', si, li, di, i)] = bb
            if off < TABLE1_OFF or off + len(bb) > len(src):
                return None
            if src[off:off + len(bb)] != bb:
                return None
            intervals.append((off, off + pad256(len(bb))))

    dir_bytes_map = {}
    for o in order:
        if o[1] != 'dir':
            continue
        si, li, di = o[2:]
        D = t['sections'][si]['levels'][li]['dirs'][di]
        db = dir_bytes(D, {i: where[('slot', si, li, di, i)] for i in D['slots']})
        dir_bytes_map[('dir', si, li, di)] = db
        off = where[('dir', si, li, di)]
        if off < TABLE1_OFF or off + len(db) > len(src):
            return None
        if src[off:off + len(db)] != db:
            return None
        intervals.append((off, off + pad256(len(db))))

    table_bytes_map = {}
    for o in order:
        if o[1] != 'table':
            continue
        si = o[2]
        sec = t['sections'][si]
        nw, lv_offs, groups = table_words(sec)
        w = [nw] + lv_offs
        for L in groups:
            li = sec['levels'].index(L)
            w += [2 + 6 * len(L['dirs']), len(L['dirs'])]
            for di, D in enumerate(L['dirs']):
                off_dir = where[('dir', si, li, di)]
                if off_dir == D['off'] and 'ptr_tag' in D:
                    a = D['ptr_tag']
                else:
                    a = enc_addr(off_dir)
                w += [D['box'][0], D['box'][1], D['box'][2], D['box'][3], a >> 16, a & 0xffff]
        tb = struct.pack('>%dH' % nw, *w)
        table_bytes_map[('table', si)] = tb
        off = where[('table', si)]
        if off < TABLE1_OFF or off + len(tb) > len(src):
            return None
        # compare against src using original table tag if unchanged
        # rebuild the raw section-table entry comparison is done below; here compare tb
        # but tb uses enc_addr for dir pointers which may differ in canonical form.
        # For unchanged tiles the factory may use non-canonical encodings for dir
        # pointers too; handle by using original tags when offset matches.
        if src[off:off + len(tb)] != tb:
            return None
        intervals.append((off, off + pad256(len(tb))))

    out = bytearray(src)
    out[0:TABLE1_OFF] = t['header']
    for key, data in table_bytes_map.items():
        out[where[key]:where[key] + len(data)] = data
    for key, data in dir_bytes_map.items():
        out[where[key]:where[key] + len(data)] = data
    for key, data in slot_bytes.items():
        out[where[key]:where[key] + len(data)] = data
    p = SECT_OFF
    for si, sec in enumerate(t['sections']):
        # use original section table tag when unchanged
        orig = sec.get('ttag') if where[('table', si)] == sec['taddr'] else None
        tag = orig if orig is not None else enc_addr(where[('table', si)])
        struct.pack_into('>IH', out, p, tag, sec['count'])
        p += 6
    if len(out) != len(src):
        return None
    return bytes(out)


def write_tile(t, order=None, preserve_gaps=True):
    order = order or t.get('order') or default_order(t)
    src = t.get('_src')
    preserve = bool(src) and preserve_gaps

    if preserve:
        res = _try_preserve_random(t, order, src)
        if res is not None:
            return res

    # original sequential path (compact / fallback)
    preserve = False
    pos = TABLE1_OFF; where = {}
    for o in order:
        kind = o[1]
        # Keep the original offset when nothing before it grew.  This leaves
        # room for byte ranges the reader does not model (B30R048 has a 55 KiB
        # run after the 0x2146 directory's blocks); those are copied verbatim
        # in pass 2.
        if preserve and o[0] >= pos and o[0] >= TABLE1_OFF:
            pos = o[0]
        elif o[0] < pos:
            preserve = False
        if kind == 'table':
            sec = t['sections'][o[2]]; nw, _, _ = table_words(sec)
            where[o[1:]] = pos; pos = pad256(pos + 2*nw)
        elif kind == 'dir':
            D = t['sections'][o[2]]['levels'][o[3]]['dirs'][o[4]]
            where[o[1:]] = pos; pos = pad256(pos + 12 + D.get('nslots', SLOTS)*(4 + D['body']) + len(D.get('tail', b'')))
        else:
            D = t['sections'][o[2]]['levels'][o[3]]['dirs'][o[4]]
            sl = sorted(D['slots'], key=lambda i: D['slots'][i]['block_off'] if preserve else i)
            for i in sl:
                s0 = D['slots'][i]
                if preserve and s0['block_off'] >= pos:
                    pos = s0['block_off']
                elif s0['block_off'] < pos:
                    preserve = False
                where[('slot',) + o[2:] + (i,)] = pos
                pos = pad256(pos + len(block_bytes(s0)))
    out = bytearray(t['header']); assert len(out) == TABLE1_OFF

    def fill_to(preserve, p):
        if len(out) < p:
            if preserve and src:
                take = min(p - len(out), max(0, len(src) - len(out)))
                out.extend(src[len(out):len(out) + take])
            out.extend(b'\0' * (p - len(out)))

    def pad_out(preserve):
        n = pad256(len(out))
        if preserve and src and len(out) < n <= len(src):
            out.extend(src[len(out):n])
        else:
            out.extend(b'\0' * (n - len(out)))
    for o in order:
        kind = o[1]; p = where[o[1:]] if kind != 'blocks' else None
        if p is not None:
            fill_to(preserve, p)
        if kind == 'table':
            si = o[2]; sec = t['sections'][si]; nw, lv_offs, groups = table_words(sec)
            w = [nw] + lv_offs
            for L in groups:
                li = sec['levels'].index(L)
                w += [2 + 6*len(L['dirs']), len(L['dirs'])]
                for di, D in enumerate(L['dirs']):
                    a = enc_addr(where[('dir', si, li, di)])
                    w += [D['box'][0], D['box'][1], D['box'][2], D['box'][3], a >> 16, a & 0xffff]
            assert len(out) == p
            out += struct.pack('>%dH' % nw, *w)
        elif kind == 'dir':
            si, li, di = o[2:]; D = t['sections'][si]['levels'][li]['dirs'][di]
            assert len(out) == p
            out += dir_bytes(D, {i: where[('slot', si, li, di, i)] for i in D['slots']})
        else:
            si, li, di = o[2:]; D = t['sections'][si]['levels'][li]['dirs'][di]
            sl = sorted(D['slots'], key=lambda i: D['slots'][i]['block_off'] if preserve else i)
            for i in sl:
                wp = where[('slot', si, li, di, i)]
                fill_to(preserve, wp)
                assert len(out) == wp
                out += block_bytes(D['slots'][i]); pad_out(preserve)
        pad_out(preserve)
    p = SECT_OFF
    for si, sec in enumerate(t['sections']):
        struct.pack_into('>IH', out, p, enc_addr(where[('table', si)]), sec['count']); p += 6
    if preserve and len(out) < len(src):
        out += src[len(out):]
    return bytes(out)

if __name__ == '__main__':
    import sys
    for fn in sys.argv[1:]:
        d = open(fn, 'rb').read()
        t = read_tile(d)
        b = write_tile(t)
        if b == d: print(fn, 'byte-identical rebuild OK', len(d))
        else:
            i = next((i for i in range(min(len(b), len(d))) if b[i] != d[i]), min(len(b), len(d)))
            print(fn, 'MISMATCH len', len(d), len(b), 'first diff', hex(i), d[i:i+16].hex(), b[i:i+16].hex())
