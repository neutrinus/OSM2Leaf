#!/usr/bin/env python3
"""Read ``MAPAL001/LEV3456R.DAT`` (whole-database coarse map, levels 3 to 6).

The file is a tile container: 0x1000-byte header, a section table at 0x800 and
the section's level-group table at the address 0x800 points to.  Each level is
one directory per section covering the whole database (level 3 is one directory
per tile cell), and a directory is a 12-byte head plus, per row, a u32 block
address and one (compressed words, plain words) pair per record slot.

Record roles by section 1 level and slot parity:

* level 3 and 4, even slot: a road-shape record, kind ``0x00fa``;
* level 3 and 4, odd slot: a background record (sea, coast, land/area shapes);
* level 5: one record holds both the background block (w9/w10) and, when
  present, the road block (w7/w8); the names section is w11/w12.

Everything here is ``VERIFIED`` on the EU 2011 file
(``MAPAL001/LEV3456R.DAT``, sha256 ``08a584fe...``) except where a docstring
says otherwise.  See ``docs/format/map-tiles.md`` and
``docs/experiments/EXP-2026-11-06-M4.11-lev-coarse.md``.

Commands::

    python3 tools/lev3456.py info FILE
    python3 tools/lev3456.py verify FILE [--level 5] [--require-stock-zlib]
    python3 tools/lev3456.py rebuild FILE --level 5 -o OUT.DAT [--require-stock-zlib]
    python3 tools/lev3456.py --selftest

``verify`` and ``rebuild`` compare compressed bytes too, so they need stock
zlib 1.3.1.  Python builds that link zlib-ng (some 3.14 builds) reproduce none
of the factory streams; the tools print the runtime version through
``tools/zlibinfo.py`` and report a byte-identity mismatch as ``UNVERIFIABLE``
(exit 3) instead of ``FAIL`` (exit 1) on such a build, because the payload is
correct and only the compressor differs.  ``--require-stock-zlib`` refuses to
start on zlib-ng at all.
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib

import zlibinfo

SECT_OFF = 0x800
LEVEL_OFF = 0x1ac
GROUP_OFF = 0x1000
TABLE1 = 0x1000
ABSENT = 0xffffffff
EMPTY = 0x7fffffff
ZLIB_HEAD = b"\x78\x9c"

COARSE_LEVELS = (3, 4, 5, 6)


# ---------------------------------------------------------------------------
# addresses, containers
# ---------------------------------------------------------------------------


def addr_of(code: int) -> int:
    """A 16-bit page code to a byte offset (256-byte pages, 11-bit page number)."""
    return (code >> 8) * 2048 + (code & 0xFF) * 256


def addr_code(off: int) -> int:
    assert off % 256 == 0, off
    return ((off // 2048) << 8) | ((off % 2048) // 256)


def pad256(n: int) -> int:
    return (n + 255) // 256 * 256


def u16(d, p):
    return struct.unpack_from(">H", d, p)[0]


def u32(d, p):
    return struct.unpack_from(">I", d, p)[0]


def words(b):
    return list(struct.unpack(">%dH" % (len(b) // 2), b))


class Record:
    __slots__ = ("off", "words", "plain", "comp", "parts")

    def __init__(self, off, words_len, plain=None, comp=None, parts=None):
        self.off = off
        self.words = words_len
        self.plain = plain
        self.comp = comp
        self.parts = parts  # (a words, b words) for a raw two-part record

    @property
    def is_z(self):
        return self.plain is not None


class Dir:
    def __init__(self, off, box, head, rows, pairs):
        self.off = off
        self.box = box
        self.head = head
        self.rows = rows
        self.pairs = pairs

    @property
    def cols(self):
        return self.head[2]

    @property
    def nrows(self):
        return self.head[1]

    @property
    def typ(self):
        return self.head[5]


class Level:
    def __init__(self, level, typ, dirs):
        self.level = level
        self.typ = typ
        self.dirs = dirs

    def records(self):
        for di, D in enumerate(self.dirs):
            for ri, row in enumerate(D.rows):
                if not row:
                    continue
                for k, r in enumerate(row):
                    if r is not None:
                        yield di, ri, k, r


class Section:
    def __init__(self, sid, levels):
        self.id = sid
        self.levels = levels

    def level(self, n):
        for L in self.levels:
            if L.level == n:
                return L
        return None


class Container:
    """The coarse file as header fields, sections, levels, directories and records."""

    def __init__(self, data):
        self.data = data
        self.bounds, self.version = read_header(data)
        self.sections = read_sections(data)

    def section(self, sid):
        for s in self.sections:
            if s.id == sid:
                return s
        return None

    def level(self, sid, level):
        s = self.section(sid)
        return None if s is None else s.level(level)


def read_header(data):
    lat_max, lat_min, lon_min, lon_max = struct.unpack_from(">4h", data, 0x184)
    raw = bytes(data[0xE0:0xE0 + 48])
    try:
        version = raw.decode("utf-16-be")
        if not version.startswith("DATA VERSION "):
            version = None
        else:
            version = version[13:]
    except UnicodeDecodeError:
        version = None
    return (lat_max, lat_min, lon_min, lon_max), version


def read_level_tables(data):
    n = u16(data, LEVEL_OFF)
    p = LEVEL_OFF + 2
    out = []
    for _ in range(n):
        sid, cnt = data[p], data[p + 1]
        p += 2
        rows = []
        for _ in range(cnt):
            lvl, typ = data[p], data[p + 1]
            rows.append((lvl, typ, u16(data, p + 2)))
            p += 4
        out.append((sid, rows))
    return out


def read_section_table(data):
    out = []
    p = SECT_OFF
    while True:
        code, cnt = struct.unpack_from(">IH", data, p)
        p += 6
        if code == ABSENT:
            break
        out.append((addr_of(code), cnt))
    return out


def read_sections(data):
    tables = read_level_tables(data)
    groups = read_section_table(data)
    sections = []
    for (sid, rows), (ta, _count) in zip(tables, groups):
        nw = u16(data, ta)
        w = struct.unpack_from(">%dH" % nw, data, ta)
        levels = []
        for li, (lvl, typ, _count) in enumerate(rows):
            o = w[1 + li]
            dirs = []
            if o != 0xFFFF:
                assert w[o] == 2 + 6 * w[o + 1], ("group table", sid, lvl)
                for g in range(w[o + 1]):
                    y1, y0, x0, x1, hi, lo = w[o + 2 + 6 * g:o + 8 + 6 * g]
                    da = addr_of((hi << 16) | lo)
                    dirs.append(read_dir(data, da, (y1, y0, x0, x1)))
            levels.append(Level(lvl, typ, dirs))
        sections.append(Section(sid, levels))
    return sections


def read_dir(data, da, box):
    size, nrows, cols, y, x, typ = struct.unpack_from(">6H", data, da)
    if nrows == cols == 1:
        pairs = 1
    else:
        pairs = ((2 * size - 12) // nrows - 4) // 8
    # level 6's one-slot directory declares 10 words where it spans 12
    assert 12 + nrows * (4 + 8 * pairs) in (2 * size, 2 * size + 4), \
        ("directory", hex(da), size, pairs)
    rows = []
    q = da + 12
    for _ in range(nrows):
        tag = u32(data, q)
        pr = [struct.unpack_from(">II", data, q + 4 + 8 * k) for k in range(pairs)]
        if tag == ABSENT:
            rows.append(None)
        else:
            b = addr_of(tag)
            recs = []
            for ln, plain_words in pr:
                if ln == ABSENT:
                    recs.append(None)
                    continue
                if data[b:b + 2] == ZLIB_HEAD:
                    z = bytes(data[b:b + 2 * ln])
                    plain = zlib.decompress(z)
                    assert len(plain) == 2 * plain_words, ("record", hex(b))
                    recs.append(Record(b, plain_words, plain=plain, comp=z))
                    b += 2 * ln
                else:
                    part = bytes(data[b:b + 2 * ln])
                    part_b = bytes(data[b + 2 * ln:b + 2 * (ln + plain_words)])
                    recs.append(Record(b, plain_words, plain=part + part_b,
                                       comp=part + part_b, parts=(ln, plain_words)))
                    b += 2 * (ln + plain_words)
            rows.append(recs)
        q += 4 + 8 * pairs
    return Dir(da, box, (size, nrows, cols, y, x, typ), rows, pairs)


# ---------------------------------------------------------------------------
# background block: layer table, groups of shapes
# ---------------------------------------------------------------------------

def walk_shapes(d, q, kind, limit):
    """Walk self-delimiting shapes up to ``limit``.

    A group's count byte is one byte and wraps: 604 islets are written as 92.
    The layer length is the authority, and a shape always carries its own
    length, so walk until the limit instead of trusting the count.
    """
    shapes = []
    need = 8 if kind == 0 else 10
    while q + need <= limit:
        if kind == 0:
            typ, ref, x, y = struct.unpack_from(">HHHH", d, q)
            q += 8
            shapes.append({"type": typ, "ref": ref, "pts": [(x, y)]})
        else:
            cnt, typ, ref, x, y = struct.unpack_from(">HHHHH", d, q)
            if cnt == 0 or cnt > 5000:
                raise ValueError("bad shape count at %#x" % q)
            q += 10
            pts = [(x, y)]
            for _ in range(cnt - 1):
                if q + 2 > limit:
                    raise ValueError("truncated point")
                x += d[q] - 256 if d[q] > 127 else d[q]
                y += d[q + 1] - 256 if d[q + 1] > 127 else d[q + 1]
                pts.append((x, y))
                q += 2
            shapes.append({"type": typ, "ref": ref, "pts": pts})
    if any(d[q:limit]):
        raise ValueError("non-zero tail after shapes")
    return q, shapes


def parse_group(d, p, end):
    """One background group.  Returns (dict, end offset); ``raw`` when unknown."""
    start = p
    nsub, hw = struct.unpack_from(">HH", d, p)
    if nsub == 0 or nsub > 8 or hw != 2 + 2 * nsub - 1:
        return {"raw": d[p:end]}, end
    q = p + 4
    subs = []
    try:
        for i in range(nsub):
            kind, n = d[q], d[q + 1]
            q += 2
            stop = None
            if i < nsub - 1:
                stop = start + 2 * u16(d, q)
                q += 2
            subs.append((kind, n, stop))
        parsed = []
        for kind, n, stop in subs:
            limit = end if stop is None else stop
            q, shapes = walk_shapes(d, q, kind, limit)
            if stop is not None and q != stop:
                return {"raw": d[start:end]}, end
            parsed.append({"kind": kind, "shapes": shapes})
    except (struct.error, IndexError, ValueError):
        return {"raw": d[start:end]}, end
    q = (q + 3) // 4 * 4
    if q > end:
        return {"raw": d[start:end]}, end
    g = parsed[0]
    if len(parsed) > 1:
        g["more"] = parsed[1:]
    return g, q


def parse_layer(d, p, end):
    """A background layer: one group whose length is the layer's length."""
    g, _q = parse_group(d, p, end)
    return [g]


def build_shapes(kind, shapes):
    out = bytearray()
    for s in shapes:
        pts = s["pts"]
        if kind == 0:
            out += struct.pack(">HHHH", s["type"], s["ref"], pts[0][0], pts[0][1])
        else:
            out += struct.pack(">HHHHH", len(pts), s["type"], s["ref"], pts[0][0], pts[0][1])
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                dx, dy = x1 - x0, y1 - y0
                if not (-128 <= dx <= 127 and -128 <= dy <= 127):
                    raise ValueError("background delta out of range")
                out += struct.pack(">bb", dx, dy)
    return bytes(out)


def build_group(g):
    if "raw" in g:
        return g["raw"]
    subs = [g] + g.get("more", [])
    bodies = [build_shapes(s["kind"], s["shapes"]) for s in subs]
    hw = 2 + 2 * len(subs) - 1
    out = bytearray(struct.pack(">HH", len(subs), hw))
    pos = 2 * hw
    for i, (s, body) in enumerate(zip(subs, bodies)):
        out += bytes([s["kind"] & 0xFF, len(s["shapes"]) & 0xFF])
        pos += len(body)
        if i < len(subs) - 1:
            out += struct.pack(">H", pos // 2)
    for body in bodies:
        out += body
    while len(out) % 4:
        out.append(0)
    return bytes(out)


def build_layer(groups):
    return b"".join(build_group(g) for g in groups)


def block_is_raw(block):
    return any(any("raw" in grp for grp in groups)
               for groups in block["layers"] if groups)


def decode_block(plain, unit, nlayers=None):
    """A background/coarse block: (offset, length) pairs in 4-byte units.

    The table size is not fixed: a background block reserves 26 units and a
    road block 11, and the first non-empty layer's offset is exactly the table
    size (the data follows the table).  When ``nlayers`` is None it is read
    from that first offset.
    """
    base = 4 * unit
    table = []
    if nlayers is None:
        while True:
            off, ln = struct.unpack_from(">HH", plain, base + 4 * len(table))
            table.append((off, ln))
            if nlayers is None and off != 0xFFFF:
                if not 1 <= off <= 64:
                    raise ValueError("implausible block table at %#x" % base)
                nlayers = off
            if nlayers is not None and len(table) == nlayers:
                break
    else:
        for i in range(nlayers):
            table.append(struct.unpack_from(">HH", plain, base + 4 * i))
    layers = []
    for off, ln in table:
        if off == 0xFFFF:
            layers.append(None)
        else:
            p = base + 4 * off
            layers.append(parse_layer(plain, p, p + 4 * ln))
    return {"table": table, "layers": layers}


def encode_block(block, nlayers=None):
    layers = block["layers"]
    n = len(layers) if nlayers is None else nlayers
    assert len(layers) == n
    bodies = []
    unit = n  # 4-byte units; the table itself is n units
    out = bytearray(b"\xff\xff\x00\x00" * n)
    for i, groups in enumerate(layers):
        if groups is None:
            continue
        b = build_layer(groups)
        assert len(b) % 4 == 0
        struct.pack_into(">HH", out, 4 * i, unit, len(b) // 4)
        bodies.append(b)
        unit += len(b) // 4
    return bytes(out) + b"".join(bodies)


# ---------------------------------------------------------------------------
# road-shape records: level-2 layout, shapes carry a class nibble
# ---------------------------------------------------------------------------

GRAMMAR_Y = 0x2800


def shape_header_len(w0):
    return 7 + (1 if w0 & 0x2000 else 0) + (2 if w0 & 0x4000 else 0)


def decode_shape(sw, level):
    """A coarse road shape as (head, start, links); None when it is not the grammar."""
    sw = list(sw)
    n = sw[0] & 0x1FFF
    if n != len(sw):
        return None
    h = shape_header_len(sw[0])
    head = sw[1:h]
    q = h
    if q + 2 > n:
        return None
    sx, sy = sw[q], sw[q + 1]
    q += 2
    ids = level != 3
    if sx & 0xF800 != 0x0800:
        return None
    if ids and (sy & GRAMMAR_Y) != 0x0800:
        return None
    if not ids and sy & GRAMMAR_Y:
        return None
    start = (sx & 0x7FF, sy & 0x7FF, sy & ~(0x7FF | GRAMMAR_Y) & 0xFFFF)
    links = []
    prev_y = sy
    while q < n:
        lid = None
        if ids:
            if not prev_y & 0x0800 or prev_y & 0x2000:
                return None
            lid = sw[q]
            q += 1
        pts = []
        while True:
            if q + 1 >= n + 1:
                return None
            if q + 1 >= n:
                return None
            x, y = sw[q], sw[q + 1]
            q += 2
            last = q >= n
            end = not (x & 0x1000)
            pts.append((x & 0x7FF, y & 0x7FF, y & ~(0x7FF | GRAMMAR_Y) & 0xFFFF))
            prev_y = y
            if end or last:
                break
        links.append((lid, pts))
        if q >= n:
            break
    if not links:
        return None
    s = {"head": head, "start": start, "links": links}
    if encode_shape(s, level) != sw:
        return None
    return s


def encode_shape(s, level):
    ids = level != 3
    sx, sy, sb = s["start"]
    out = list(s["head"]) + [0x0800 | sx, sy | sb | (0x0800 if ids else 0)]
    n = len(s["links"])
    for i, (lid, pts) in enumerate(s["links"]):
        if ids:
            out.append(lid)
        for k, (x, y, yb) in enumerate(pts):
            link_end = k == len(pts) - 1
            chain_end = i == n - 1
            xf = ((0x2000 if k == 0 and ids else 0)
                  | (0 if link_end and not chain_end else 0x1000)
                  | (0 if link_end else 0x0800))
            yf = 0x0800 if link_end and not chain_end and ids else 0
            out += [xf | x, y | yb | yf]
    hl = 1 + len(s["head"])
    n = len(out) + 1
    w0 = n | (0x2000 if hl == 8 else 0x4000 if hl == 9 else 0x6000 if hl == 10 else 0)
    return [w0] + out


def decode_road(plain, level):
    """A level-3/4 road-shape record or a level-5 road block; 11 layer pairs."""
    w = words(plain)
    layers = []
    for li in range(11):
        off, cnt = w[2 * li], w[2 * li + 1]
        if off == 0xFFFF:
            layers.append(None)
            continue
        q = 2 * off
        shapes = []
        for _ in range(cnt):
            n = w[q] & 0x1FFF
            raw = w[q:q + n]
            s = decode_shape(raw, level)
            if s is None:
                return None
            shapes.append(s)
            q += n
        layers.append(shapes)
    return {"layers": layers}


def encode_road(block, level):
    layers = block["layers"]
    n = len(layers)
    table = [0xFFFF, 0] * n
    body = []
    pos = 2 * n  # words after the table
    for li, shapes in enumerate(layers):
        if shapes is None:
            continue
        table[2 * li] = pos // 2
        table[2 * li + 1] = len(shapes)
        for s in shapes:
            w = encode_shape(s, level)
            body += w
            pos += len(w)
        if pos % 2:
            body.append(0)
            pos += 1
    return table + body


# ---------------------------------------------------------------------------
# names
# ---------------------------------------------------------------------------


def decode_names(b, level=5):
    """Header ``ver, count, 5 x (offset, length)`` then name entries.

    An entry is an 8-byte key, an optional u16 0x2c00 for place labels
    (key word 1 = 0x4800), a u16 byte length and the text.  The section is
    padded to a 4-byte boundary with zeros.  VERIFIED over all 48 level-5
    names sections of the EU 2011 file.
    """
    ver, cnt = struct.unpack_from(">HH", b, 0)
    pairs = [struct.unpack_from(">HH", b, 4 + 4 * i) for i in range(5)]
    p = 24
    entries = []
    for _ in range(cnt):
        key = b[p:p + 8]
        w1 = struct.unpack_from(">H", b, p + 2)[0]
        extra = None
        p += 8
        if w1 == 0x4800:
            extra = struct.unpack_from(">H", b, p)[0]
            p += 2
        ln = struct.unpack_from(">H", b, p)[0]
        p += 2
        entries.append({"key": key, "extra": extra, "text": b[p:p + ln]})
        p += ln
    tail = b[p:]
    return {"version": ver, "pairs": pairs, "entries": entries, "tail": tail}


def encode_names(nm):
    out = bytearray(struct.pack(">HH", nm["version"], len(nm["entries"])))
    for a, b in nm["pairs"]:
        out += struct.pack(">HH", a, b)
    for e in nm["entries"]:
        out += e["key"]
        if e["extra"] is not None:
            out += struct.pack(">H", e["extra"])
        out += struct.pack(">H", len(e["text"]))
        out += e["text"]
    out += nm.get("tail", b"")
    return bytes(out)


# ---------------------------------------------------------------------------
# level-5 records
# ---------------------------------------------------------------------------


def record_role(sid, level, pair):
    if sid != 1:
        return "graph"
    if level in (3, 4):
        return "road" if pair % 2 == 0 else "background"
    return "level5"


def decode_record(plain, level, pair, sid=1):
    """Decode one level-3/4/5 record into a semantic dict."""
    try:
        return _decode_record(plain, level, pair, sid)
    except (ValueError, IndexError, struct.error) as e:
        return {"role": record_role(sid, level, pair), "opaque": True,
                "plain": plain, "error": str(e)}


def _decode_record(plain, level, pair, sid=1):
    role = record_role(sid, level, pair)
    if role == "graph":
        return {"role": "graph", "opaque": True, "plain": plain}
    if role == "level5":
        return decode_l5(plain)
    if role == "road":
        w = words(plain[:44])
        if w[7] in (0, 0xFFFF) or not w[8]:
            return {"role": "road", "opaque": True, "plain": plain}
        aux = plain[44:4 * w[7]] if w[7] > 11 else b""
        blk = decode_road(plain[4 * w[7]:4 * (w[7] + w[8])], level)
        if blk is None:
            return {"role": "road", "opaque": True, "plain": plain}
        return {"role": "road", "header": w, "block": blk, "aux": aux}
    # background record: 44-byte header, geometry at w9/w10, names at w11/w12
    w = words(plain[:44])
    gi = 9 if w[9] not in (0, 0xFFFF) and w[10] else 7
    if w[gi] == 0xFFFF:
        block = None
    else:
        block = decode_block(plain, w[gi])
        if block_is_raw(block):
            return {"role": "background", "opaque": True, "plain": plain}
    nm = None
    if w[11] != 0xFFFF:
        raw = plain[4 * w[11]:4 * (w[11] + w[12])]
        nm = decode_names(raw, level) if level == 5 else {"raw": raw}
    rec = {"role": "background", "header": w, "gi": gi, "block": block, "names": nm}
    if any(w[i] != 0xFFFF for i in (13, 15, 17)):
        rec["opaque"] = True
        rec["plain"] = plain
    return rec


def decode_l5(plain):
    w = words(plain[:44])
    rec = {"role": "level5", "header": w, "road": None, "block": None,
           "names": None, "aux": b""}
    if w[7] not in (0, 0xFFFF) and w[8]:
        if w[7] > 11:
            rec["aux"] = plain[44:4 * w[7]]
        blk = decode_road(plain[4 * w[7]:4 * (w[7] + w[8])], 5)
        if blk is None:
            rec["opaque"] = True
            rec["plain"] = plain
            return rec
        rec["road"] = blk
    if w[9] not in (0, 0xFFFF) and w[10]:
        blk = decode_block(plain, w[9])
        if block_is_raw(blk):
            rec["opaque"] = True
            rec["plain"] = plain
            return rec
        rec["block"] = blk
    if w[11] != 0xFFFF:
        rec["names"] = decode_names(plain[4 * w[11]:4 * (w[11] + w[12])], 5)
    if any(w[i] != 0xFFFF for i in (13, 15, 17)):
        rec["opaque"] = True
        rec["plain"] = plain
    return rec


def encode_record(rec, level):
    if rec.get("opaque"):
        return rec["plain"]
    w = list(rec["header"])
    if rec["role"] == "road":
        body = encode_road(rec["block"], level)
        aux = rec.get("aux", b"")
        w[7], w[8] = 11 + len(aux) // 4, len(body) // 2
        return (struct.pack(">22H", *w[:22]) + aux
                + struct.pack(">%dH" % len(body), *body))
    pos = 11  # first block starts at unit 11 (44 bytes)
    road_b = b""
    bg_b = b""
    nm_b = b""
    aux = rec.get("aux", b"")
    if rec.get("road") is not None:
        assert len(aux) % 4 == 0
        body = encode_road(rec["road"], level)
        road_b = struct.pack(">%dH" % len(body), *body)
        w[7], w[8] = pos + len(aux) // 4, len(road_b) // 4
        pos = w[7] + w[8]
    else:
        assert not aux
        w[7], w[8] = 0xFFFF, 0
    if rec.get("block") is not None:
        bg_b = encode_block(rec["block"])
        w[9], w[10] = pos, len(bg_b) // 4
        pos += len(bg_b) // 4
    else:
        w[9], w[10] = 0xFFFF, 0
    if rec.get("names") is not None:
        nm_b = (rec["names"]["raw"] if "raw" in rec["names"]
                else encode_names(rec["names"]))
        w[11], w[12] = pos, len(nm_b) // 4
        pos += len(nm_b) // 4
    else:
        w[11], w[12] = 0xFFFF, 0
    out = bytearray(struct.pack(">22H", *w))
    out += aux + road_b + bg_b + nm_b
    return bytes(out)


def compress_record(plain):
    c = zlib.compressobj(6, zlib.DEFLATED, 15, 8)
    z = c.compress(plain) + c.flush()
    if len(z) % 4:
        z += b"\x00" * (4 - len(z) % 4)
    return z


# ---------------------------------------------------------------------------
# level rebuilding
# ---------------------------------------------------------------------------


def level_extent(cont, sid, level):
    """(start, end) of a level's directories and row blocks, 256-byte aligned."""
    Ds = cont.level(sid, level).dirs
    own = set()
    occupied = []
    for D in Ds:
        own.add(D.off)
        occupied.append((D.off, D.off + 12 + D.nrows * (4 + 8 * D.pairs)))
        for row in D.rows:
            if not row:
                continue
            for r in row:
                if r is None:
                    continue
                own.add(r.off)
                occupied.append((r.off, r.off + len(r.comp)))
    start = min(a for a, _ in occupied)
    end = max(b for _, b in occupied)
    limits = []
    for ta, _c in read_section_table(cont.data):
        if ta >= end:
            limits.append(ta)
    for sec in cont.sections:
        for L in sec.levels:
            for D in L.dirs:
                if D.off >= end and D.off not in own:
                    limits.append(D.off)
                for row in D.rows:
                    if not row:
                        continue
                    for r in row:
                        if r is not None and r.off >= end and r.off not in own:
                            limits.append(r.off)
    nxt = min(limits) if limits else len(cont.data)
    return start, min(nxt, len(cont.data)), end


def rebuild_level(cont, sid, level):
    """The bytes of one level, rebuilt from decoded records.

    Returns (bytes, stats); raises when the decoded model does not reproduce
    the source bytes.
    """
    L = cont.level(sid, level)
    if L is None:
        raise SystemExit("no section %d level %d" % (sid, level))
    start, next_off, used_end = level_extent(cont, sid, level)
    out = bytearray()
    stats = {"records": 0, "plain": 0, "streams": 0, "opaque": 0}
    for D in L.dirs:
        dstart = start + len(out)
        size, nrows, cols, y, x, typ = D.head
        out += struct.pack(">6H", size, nrows, cols, y, x, typ)
        slots = bytearray()
        blocks = []
        for row in D.rows:
            if not row:
                slots += struct.pack(">I", ABSENT)
                slots += struct.pack(">%dI" % (2 * D.pairs), *([ABSENT, ABSENT] * D.pairs))
                blocks.append(None)
                continue
            pairs = []
            body = bytearray()
            for r in row:
                if r is None:
                    pairs += [ABSENT, ABSENT]
                    continue
                if not r.is_z:
                    assert r.parts is not None
                    pairs += [r.parts[0], r.parts[1]]
                    body += r.comp
                    stats["opaque"] += 1
                    continue
                rec = decode_record(r.plain, level, len(pairs) // 2, sid)
                plain = encode_record(rec, level)
                comp = compress_record(plain)
                stats["records"] += 1
                stats["plain"] += plain == r.plain
                stats["streams"] += comp == r.comp
                if comp != r.comp:
                    if level == 5:
                        raise ValueError("stream differs at %#x (plain %s)"
                                         % (r.off, plain == r.plain))
                    pairs += [len(r.comp) // 2, len(r.plain) // 2]
                    body += r.comp
                    stats["opaque"] += 1
                    continue
                pairs += [len(comp) // 2, len(plain) // 2]
                body += comp
            blocks.append(body)
            # address placeholder, filled once the directory size is known
            slots += b"\x00\x00\x00\x00"
            slots += struct.pack(">%dI" % (2 * D.pairs), *pairs)
        # lay blocks after the directory, addressed from the absolute position
        out += slots
        body_start = pad256(start + len(out))
        out += b"\x00" * (body_start - (start + len(out)))
        slot_off = dstart - start + 12
        for row, body in zip(D.rows, blocks):
            if body is None:
                slot_off += 4 + 8 * D.pairs
                continue
            abs_block = start + len(out)
            struct.pack_into(">I", out, slot_off, addr_code(abs_block))
            out += body
            pad_to = pad256(start + len(out))
            out += b"\x00" * (pad_to - (start + len(out)))
            slot_off += 4 + 8 * D.pairs
        pad_to = pad256(start + len(out))
        out += b"\x00" * (pad_to - (start + len(out)))
    src = cont.data[start:next_off]
    if len(out) < len(src):
        if any(src[len(out):]):
            raise ValueError("non-zero gap after the last block")
        out += src[len(out):]
    if len(out) != len(src):
        raise ValueError("level length %d, source region %d" % (len(out), len(src)))
    if bytes(out) != src:
        i = next(i for i in range(len(out)) if out[i] != src[i])
        raise ValueError("level differs at %#x (%s vs %s)"
                         % (start + i, src[i:i + 8].hex(), out[i:i + 8].hex()))
    stats["bytes"] = len(out)
    stats["used"] = used_end - start
    return bytes(out), stats


# ---------------------------------------------------------------------------
# inspection
# ---------------------------------------------------------------------------


def shape_stats(block):
    """Counts by layer, shape type and class, and points."""
    out = {"shapes": 0, "points": 0, "layers": {}, "types": {}, "classes": {}}
    if block is None:
        return out
    for li, groups in enumerate(block["layers"]):
        if not groups:
            continue
        for g in groups:
            if "raw" in g:
                continue
            subs = [g] + g.get("more", [])
            for sub in subs:
                for s in sub["shapes"]:
                    out["shapes"] += 1
                    out["points"] += len(s["pts"])
                    out["layers"][li] = out["layers"].get(li, 0) + 1
                    if "type" in s:
                        t = s["type"]
                        out["types"][t] = out["types"].get(t, 0) + 1
                        if t & 0x8000:
                            cls = (t >> 12) & 0xF
                            out["classes"][cls] = out["classes"].get(cls, 0) + 1
    return out


def road_stats(block, level):
    out = {"shapes": 0, "points": 0, "layers": {}, "classes": {}, "named": 0,
           "links": 0}
    if block is None:
        return out
    for li, shapes in enumerate(block["layers"]):
        if shapes is None:
            continue
        for s in shapes:
            out["shapes"] += 1
            out["layers"][li] = out["layers"].get(li, 0) + 1
            out["links"] += len(s["links"])
            out["points"] += 1 + sum(len(p) for _, p in s["links"])
            head = s["head"]
            if len(head) >= 4:
                cls = (head[1] >> 12) & 0xF
                out["classes"][cls] = out["classes"].get(cls, 0) + 1
                if head[3] != 0xFFFF:
                    out["named"] += 1
    return out


def summarise(cont, sid, level):
    L = cont.level(sid, level)
    if L is None:
        return None
    info = {
        "section": sid,
        "level": level,
        "type": L.typ,
        "dirs": len(L.dirs),
        "slots": 0,
        "records": 0,
        "roads": 0,
        "background": 0,
        "road_shapes": 0,
        "road_points": 0,
        "road_classes": {},
        "bg_shapes": 0,
        "bg_points": 0,
        "bg_types": {},
        "names_sections": 0,
        "names_raw": 0,
        "name_entries": 0,
        "name_kinds": {},
        "opaque": 0,
        "grid": None,
    }
    shapes = {"shapes": 0, "points": 0, "layers": {}, "types": {}, "classes": {}}
    rstats = {"shapes": 0, "points": 0, "layers": {}, "classes": {}, "named": 0, "links": 0}
    for D in L.dirs:
        info["slots"] += D.nrows * D.pairs
        if info["grid"] is None:
            info["grid"] = {"rows": D.nrows, "cols": D.cols, "pairs": D.pairs,
                            "box": D.box, "head": D.head}
    for di, ri, k, r in L.records():
        info["records"] += 1
        role = record_role(sid, level, k)
        if not r.is_z:
            info["opaque"] += 1
            continue
        rec = decode_record(r.plain, level, k, sid)
        if rec.get("opaque"):
            info["opaque"] += 1
            continue
        if role == "road" or (role == "level5" and rec.get("road") is not None):
            info["roads"] += 1
            rs = road_stats(rec.get("road") or rec.get("block"), level)
            for key in ("shapes", "points", "links"):
                rstats[key] += rs[key]
            for c, n in rs["classes"].items():
                rstats["classes"][c] = rstats["classes"].get(c, 0) + n
        if role == "background" or (role == "level5" and rec.get("block") is not None):
            info["background"] += 1
            blk = rec["block"]
            ss = shape_stats(blk)
            for key in ("shapes", "points"):
                shapes[key] += ss[key]
            for t, n in ss["types"].items():
                shapes["types"][t] = shapes["types"].get(t, 0) + n
            for c, n in ss["classes"].items():
                shapes["classes"][c] = shapes["classes"].get(c, 0) + n
        nm = rec.get("names")
        if nm:
            info["names_sections"] += 1
            if "raw" in nm:
                info["names_raw"] += 1
            else:
                info["name_entries"] += len(nm["entries"])
                for e in nm["entries"]:
                    kk = e["key"][:4].hex()
                    info["name_kinds"][kk] = info["name_kinds"].get(kk, 0) + 1
    info["road_shapes"] = rstats["shapes"]
    info["road_points"] = rstats["points"]
    info["road_classes"] = rstats["classes"]
    info["bg_shapes"] = shapes["shapes"]
    info["bg_points"] = shapes["points"]
    info["bg_types"] = shapes["types"]
    return info


def fmt(v):
    if isinstance(v, dict):
        return "{" + ", ".join("%s: %s" % (k, v[k]) for k in sorted(v)) + "}"
    return str(v)


def cmd_info(args):
    data = open(args.file, "rb").read()
    cont = Container(data)
    print("file %d bytes, sha256 %s" % (len(data), sha256(data)))
    print("bounds %s, data version %s" % (cont.bounds, cont.version))
    for sec in cont.sections:
        print("section %d" % sec.id)
        for L in sec.levels:
            if L.level not in COARSE_LEVELS:
                continue
            s = summarise(cont, sec.id, L.level)
            print("  level %d type %#04x dirs %d slots %d records %d"
                  % (L.level, L.typ, s["dirs"], s["slots"], s["records"]))
            if s["grid"]:
                print("    grid %dx%d, %d pairs/row, head %s"
                      % (s["grid"]["rows"], s["grid"]["cols"], s["grid"]["pairs"],
                         s["grid"]["head"]))
            print("    roads %d records, %d shapes, %d points, classes %s"
                  % (s["roads"], s["road_shapes"], s["road_points"], fmt(s["road_classes"])))
            print("    background %d records, %d shapes, %d points, types %s"
                  % (s["background"], s["bg_shapes"], s["bg_points"],
                     fmt({hex(k): v for k, v in s["bg_types"].items()})))
            print("    names %d sections, %d entries, %d raw, kinds %s"
                  % (s["names_sections"], s["name_entries"], s["names_raw"],
                     fmt(s["name_kinds"])))
            print("    opaque %d" % s["opaque"])
    return 0


def sha256(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


def identity_only_error(exc: BaseException) -> bool:
    """A rebuild error that only the compressor build can explain.

    ``rebuild_level`` raises ``stream differs at 0x… (plain True)`` when the
    decoded record re-encodes to the same payload but not to the same stream.
    That is a compressor mismatch (zlib-ng), not a model error; the other
    errors name lengths or byte offsets and are real failures.
    """
    msg = str(exc)
    return msg.startswith("stream differs") and msg.endswith("(plain True)")


def verify_verdict(rt, data_bad, identity_bad, tool="lev3456.py verify"):
    """The exit code for the verify counters, separating data from identity.

    ``data_bad`` = the decoded model or payload is wrong -> ``FAIL`` (1).
    ``identity_bad`` = payloads reproduce but the streams/region do not.  That
    is only a ``FAIL`` on a trusted compressor; on zlib-ng it is
    ``UNVERIFIABLE`` (3), because the same source would pass on stock zlib.
    """
    if data_bad:
        print("FAIL: %d data check(s) failed (decoded payloads or model)"
              % data_bad)
        return 1
    if identity_bad:
        if rt.ok:
            print("FAIL: %d byte-identity check(s) failed on the reference zlib"
                  % identity_bad)
            return 1
        return zlibinfo.unverifiable(
            rt, tool,
            "%d byte-identity check(s) differ while every payload re-encodes; "
            "the compressor, not the data, differs" % identity_bad)
    print("OK (section 1 level 5 strict; levels 3/4 best-effort)")
    return 0


def rebuild_verdict(rt, same, plain, records, tool="lev3456.py rebuild"):
    """The exit code after writing a rebuilt level."""
    if same:
        return 0
    if not rt.ok and plain == records:
        return zlibinfo.unverifiable(
            rt, tool,
            "the rebuilt file differs although every decoded record re-encodes "
            "to its factory payload")
    return 1


def cmd_verify(args):
    tool = "lev3456.py verify"
    rt = zlibinfo.guard(tool=tool, require_stock=args.require_stock_zlib,
                        claims_identity=True)
    data = open(args.file, "rb").read()
    cont = Container(data)
    levels = args.level or [3, 4, 5]
    data_bad = identity_bad = 0
    for sid in (1, 2):
        for lvl in levels:
            L = cont.level(sid, lvl)
            if L is None:
                continue
            n = plain_ok = stream_ok = opaque = 0
            for di, ri, k, r in L.records():
                if not r.is_z:
                    opaque += 1
                    continue
                rec = decode_record(r.plain, lvl, k, sid)
                if rec.get("opaque"):
                    opaque += 1
                    continue
                n += 1
                plain = encode_record(rec, lvl)
                plain_ok += plain == r.plain
                stream_ok += compress_record(plain) == r.comp
            region_diff = False
            try:
                _b, st = rebuild_level(cont, sid, lvl)
                region = "identical %d B" % st["bytes"]
            except ValueError as e:
                region = "DIFFERS: %s" % e
                region_diff = True
            print("section %d level %d: records %d, plain %d/%d, streams %d/%d,"
                  " opaque %d, region %s"
                  % (sid, lvl, n, plain_ok, n, stream_ok, n, opaque, region))
            plain_match = plain_ok == n
            if sid == 1 and lvl == 5:
                # the decoded-record proof is strict at level 5
                if not plain_match or opaque:
                    data_bad += 1
                if stream_ok != n:
                    identity_bad += 1
            if region_diff:
                # a region that differs while every payload reproduces can
                # only come from the compressor; otherwise the model is wrong
                if plain_match:
                    identity_bad += 1
                else:
                    data_bad += 1
    return verify_verdict(rt, data_bad, identity_bad)


def cmd_rebuild(args):
    tool = "lev3456.py rebuild --level %d" % args.level
    rt = zlibinfo.guard(tool=tool, require_stock=args.require_stock_zlib,
                        claims_identity=True)
    data = open(args.file, "rb").read()
    cont = Container(data)
    lvl = args.level
    start, next_off, used_end = level_extent(cont, 1, lvl)
    try:
        body, st = rebuild_level(cont, 1, lvl)
    except ValueError as exc:
        if not rt.ok and identity_only_error(exc):
            return zlibinfo.unverifiable(rt, tool, str(exc))
        print("rebuild failed: %s" % exc)
        return 1
    if len(body) != next_off - start:
        # keep the source padding if the rebuilt level is shorter
        pad = data[start + len(body):next_off]
        if not any(pad):
            body += pad
        else:
            raise SystemExit("rebuilt level leaves non-zero source bytes")
    out = data[:start] + body + data[next_off:]
    open(args.output, "wb").write(out)
    same = out == data
    print("level %d rebuilt from %d records: %d B, %d plain, %d streams; %s"
          % (lvl, st["records"], st["bytes"], st["plain"], st["streams"],
             "byte-identical" if same else "DIFFERS"))
    return rebuild_verdict(rt, same, st["plain"], st["records"], tool=tool)


# ---------------------------------------------------------------------------
# selftest
# ---------------------------------------------------------------------------


def selftest():
    # background group: one sea polygon with 4 points
    g = {"kind": 0x80, "shapes": [{"type": 0x8012, "ref": 0xFFFF,
                                   "pts": [(10, 20), (30, 20), (30, 40), (10, 40)]}]}
    b = build_group(g)
    pg, pend = parse_group(b, 0, len(b))
    assert pg == g and pend == len(b), "background group round-trip"

    # level-5 background block: layer 0 at unit 11
    blk = {"layers": [[g]] + [None] * 10}
    eb = encode_block(blk)
    db = decode_block(eb, 0)
    assert db["layers"][0] == [g] and encode_block(db) == eb, "background block"

    # road shape: two links, class 4, unnamed
    shape = {"head": [0x8003, 0x4000, 0x3000, 0xFFFF, 0, 0],
             "start": (100, 200, 0),
             "links": [(1, [(300, 200, 0x4000)]), (2, [(300, 400, 0x4000)])]}
    sw = encode_shape(shape, 5)
    assert decode_shape(sw, 5) == shape, "road shape round-trip"
    road = {"layers": [None, None, None, None, None, None, [shape]] + [None] * 4,
            "tail": []}
    er = encode_road(road, 5)
    assert decode_road(struct.pack(">%dH" % len(er), *er), 5) is not None, "road block"

    # names: two entries, one place label with the extra word, one route ref
    nm = {"version": 6, "pairs": [(0xFFFF, 0), (0xFFFF, 0), (0xFFFF, 0),
                                  (0xFFFF, 0), (0xFFFF, 0)],
          "entries": [{"key": bytes.fromhex("8068480006a50637"), "extra": 0x2C00,
                       "text": b"M\xc1LAGA"},
                      {"key": bytes.fromhex("00ff280000000000"), "extra": None,
                       "text": b"2=A-92"}], "tail": b"\x00\x00"}
    eb = encode_names(nm)
    assert decode_names(eb) == nm, "names round-trip"

    # a whole level-5 record: header + background + road + names
    plain = bytearray(struct.pack(">22H", *([0] * 22)))
    bg_b = encode_block(blk)
    rd_w = encode_road(road, 5)
    rd_b = struct.pack(">%dH" % len(rd_w), *rd_w)
    nm_b = encode_names(nm)
    body = rd_b + bg_b + nm_b
    w = [0x900F, 0xC405, 0x00FA, 0xFFFF, 0xFFFF, 0, 0,
         11, len(rd_b) // 4, 11 + len(rd_b) // 4, len(bg_b) // 4,
         11 + (len(rd_b) + len(bg_b)) // 4, len(nm_b) // 4,
         0xFFFF, 0, 0xFFFF, 0, 0xFFFF, 0, 0, 0x026C, 0]
    plain = struct.pack(">22H", *w) + body
    rec = decode_l5(plain)
    assert not rec.get("opaque"), "level-5 record decoded"
    assert encode_record(rec, 5) == plain, "level-5 record round-trip"
    z = compress_record(plain)
    assert zlib.decompress(z) == plain, "compressed stream"

    # the zlib guard: a fake zlib-ng runtime must not produce a data FAIL
    ng = zlibinfo.classify("1.3.1.zlib-ng", "1.3.1.zlib-ng")
    stock = zlibinfo.classify("1.3.1", "1.3.1")
    assert not ng.ok and ng.flavour == zlibinfo.ZLIB_NG and stock.ok
    assert identity_only_error(
        ValueError("stream differs at 0x1200 (plain True)"))
    assert not identity_only_error(ValueError("stream differs at 0x1200 (plain False)"))
    assert not identity_only_error(ValueError("level differs at 0x1200 (aa vs bb)"))
    try:
        zlibinfo.guard(tool="lev3456.py verify", require_stock=True,
                       runtime=ng, stream=zlibinfo._null())
    except SystemExit as exc:
        assert exc.code == zlibinfo.EXIT_UNVERIFIABLE, exc.code
    else:
        raise AssertionError("--require-stock-zlib must refuse on zlib-ng")

    # verdicts: identity-only mismatch is UNVERIFIABLE on zlib-ng, FAIL on stock
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        assert verify_verdict(ng, 0, 1) == zlibinfo.EXIT_UNVERIFIABLE
        assert verify_verdict(stock, 0, 1) == 1
        assert verify_verdict(ng, 1, 1) == 1
        assert verify_verdict(ng, 0, 0) == 0
        assert rebuild_verdict(ng, False, 62, 62) == zlibinfo.EXIT_UNVERIFIABLE
        assert rebuild_verdict(ng, False, 61, 62) == 1
        assert rebuild_verdict(stock, False, 62, 62) == 1
        assert rebuild_verdict(ng, True, 62, 62) == 0
    print("selftest OK")
    return 0


# ---------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("info", help="header, directories and content counts")
    p.add_argument("file")
    p = sub.add_parser("verify", help="decode and rebuild records and level regions")
    p.add_argument("file")
    p.add_argument("--level", type=int, action="append")
    p.add_argument(
        "--require-stock-zlib",
        action="store_true",
        help="refuse to run (exit 3, unverifiable) when zlib is not stock 1.3.1",
    )
    p = sub.add_parser("rebuild", help="write a copy with one level rebuilt")
    p.add_argument("file")
    p.add_argument("--level", type=int, required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument(
        "--require-stock-zlib",
        action="store_true",
        help="refuse to run (exit 3, unverifiable) when zlib is not stock 1.3.1",
    )
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "info":
        return cmd_info(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    if args.cmd == "rebuild":
        return cmd_rebuild(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
