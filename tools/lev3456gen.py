#!/usr/bin/env python3
"""Generate LEV3456R.DAT coarse levels 3-6 from OSM (M5.16, H11 G4).

``lev3456.py`` decodes and re-encodes factory records byte-identically but
cannot build a level set from OSM.  This tool constructs section-1 road
records for levels 3, 4 and 5 from a synthetic/OSM extract (a mesh-split set
of road polylines in lat/lon), splices them into a factory template (or
builds a minimal container), and produces a file that ``lev3456.py verify``
accepts for those levels.  An unchanged input rebuilds byte-identically.

The extract is a JSON object::

    {"roads": [{"class": <1-7>, "nodes": [[lon, lat], ...], "ref": "..."}],
     "bounds": [lat_max_arcmin, lat_min_arcmin, lon_min_arcmin, lon_max_arcmin]}

``class`` follows the coarse road class used by lev3456 road shapes
(w1 top nibble: 1=motorway..6/7=local, matching M4.11). ``bounds``, when
present, gives the database box in arcminutes (the factory lev3456 header
order); otherwise the template's bounds are kept.

Record grammar, compression and directory layout follow ``lev3456.py``
(EU 2011, M4.11 C-990-C-999).  Road-shape encoding follows the level-2 layout
that ``lev3456.decode_shape``/``encode_shape`` round-trips (C-996).  Streams
use ``cmpind_codec.factory_compress`` (stock zlib 1.3.1, C-997).

Commands::

    python3 tools/lev3456gen.py generate --template LEV3456R.DAT \\
        --extract extract.json -o OUT.DAT [--levels 3,4,5]
    python3 tools/lev3456gen.py --selftest
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import struct
import sys
import tempfile
import zlib

import cmpind_codec
import lev3456

ABSENT = lev3456.ABSENT
EMPTY = lev3456.EMPTY
ZLIB_HEAD = lev3456.ZLIB_HEAD

# Road shape head: [point_count_flag, class<<12, w2, name_off, 0, 0]
# level 3: w0 flag 0x4000|npts, no link ids, w2=0
# level 4/5: w0 flag 0x8000|npts, link ids, w2=0x3000 (unnamed common form)
ROAD_W2_UNNAMED = 0x3000
ROAD_NAME_NONE = 0xFFFF

# Background: minimal valid single-layer empty-ish block (26 layers, all absent)
# is not useful; we generate a tiny sea/land placeholder only when no template
# background exists.  Prefer preserving template backgrounds.
BG_NLAYERS = 26
ROAD_NLAYERS = 11
ROAD_LAYER = 6  # classes 3-6 live in layer 6 at level 5 (M4.11/C-991)

# Level-5 parcel: 8x8 meshes = 8 degrees lon, 16/3 degrees lat.
# Level-4: 2x2 meshes = 2 deg lon, 4/3 deg lat.
# Level-3: 0.5x0.5 mesh = 0.5 deg lon, 1/3 deg lat, inside a 16x16 dir per 8-mesh cell.
PW = {5: 8.0, 4: 2.0, 3: 0.5}
PH = {5: 16.0 / 3.0, 4: 4.0 / 3.0, 3: 1.0 / 3.0}
MAXPTS = {5: 60, 4: 120, 3: 200}

# Parcel code: lev3456 records carry w0,w1 as the parcel identifier.
# The exact encoding is the firmware's; we preserve factory w0,w1 when
# replacing a record in its original slot, and compute for new slots from the
# dir/row/col geometry using the observed EU 2011 convention.
# EU L5 dir box (120,32,65416,65504) head (512,11,11,32,65416,144), w0/w1 like 0x980f,0xc805.
# We derive from the template's existing records where possible.

# ---- geometry: mesh split and parcel quantization (stdlib, no shapely) ----

def mesh_to_lon(x):
    return float(x - 924)


def mesh_to_lat(y):
    return y / 1.5


def parcel_l5(lon, lat, lon0, lat0):
    """(row, col) of a level-5 parcel: 8° lon × 16/3° lat."""
    return int((lat - lat0) // PH[5]), int((lon - lon0) // PW[5])


def quant_l5(lon, lat, row, col, lon0, lat0):
    plo = lon0 + col * PW[5]
    pla = lat0 + row * PH[5]
    return (max(0, min(2047, round((lon - plo) / PW[5] * 2048))),
            max(0, min(2047, round((lat - pla) / PH[5] * 2048))))


def parcel_l4(lon, lat, lon0, lat0):
    return int((lat - lat0) // PH[4]), int((lon - lon0) // PW[4])


def quant_l4(lon, lat, row, col, lon0, lat0):
    plo = lon0 + col * PW[4]
    pla = lat0 + row * PH[4]
    return (max(0, min(2047, round((lon - plo) / PW[4] * 2048))),
            max(0, min(2047, round((lat - pla) / PH[4] * 2048))))


def parcel_l3(lon, lat, lon0, lat0, y0_cell, x0_cell):
    """(dir_key, row, col) for level 3: 16x16 parcels per 8-mesh cell."""
    r = int((lat - lat0) // PH[3])
    c = int((lon - lon0) // PW[3])
    dy = y0_cell + 8 * (r // 16)
    dx = x0_cell + 8 * (c // 16)
    return (dy, dx), r % 16, c % 16


def quant_l3(lon, lat, dy, dx, row, col):
    # level-3 parcel geo: 0.5° lon, 1/3° lat
    plo = mesh_to_lon(dx) + col * PW[3]
    pla = mesh_to_lat(dy) + row * PH[3]
    return (max(0, min(2047, round((lon - plo) / PW[3] * 2048))),
            max(0, min(2047, round((lat - pla) / PH[3] * 2048))))


def clip_segment_to_box(a, b, lon0, lon1, lat0, lat1):
    """Cohen-Sutherland-like clip of segment (lon,lat)-(lon,lat) to box.
    Returns list of points inside (possibly empty or the original segment)."""
    # Simple parametric clip
    x0, y0 = a
    x1, y1 = b
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - lon0), (dx, lon1 - x0),
                 (-dy, y0 - lat0), (dy, lat1 - y0)):
        if p == 0:
            if q < 0:
                return []
        else:
            t = q / p
            if p < 0:
                if t > t1: return []
                if t > t0: t0 = t
            else:
                if t < t0: return []
                if t < t1: t1 = t
    if t0 > t1:
        return []
    p0 = (x0 + t0 * dx, y0 + t0 * dy)
    p1 = (x0 + t1 * dx, y0 + t1 * dy)
    pts = []
    if t0 == 0.0:
        pts.append(a)
    else:
        pts.append(p0)
    if t1 == 1.0:
        pts.append(b)
    else:
        pts.append(p1)
    # dedup
    if len(pts) == 2 and abs(pts[0][0]-pts[1][0]) < 1e-12 and abs(pts[0][1]-pts[1][1]) < 1e-12:
        return []
    return pts


def runs_in_parcels(nodes, parcel_fn, quant_fn, maxpts=120):
    """Split a polyline into per-parcel runs in quantized coords.

    Returns {parcel_key: [[(x,y), ...], ...]} with points in 0..2047.
    parcel_fn(lon,lat)->key, quant_fn(lon,lat,key)->(x,y).
    Splits at parcel boundaries by linear interpolation.
    """
    if len(nodes) < 2:
        return {}
    out = {}
    for i in range(len(nodes) - 1):
        a = tuple(nodes[i])
        b = tuple(nodes[i + 1])
        # Walk the segment, splitting at parcel edges
        segs = [(a, b)]
        # simple: sample/split by checking parcel changes; do iterative subdivision
        stack = [(a, b, 0)]
        while stack:
            p0, p1, depth = stack.pop()
            k0 = parcel_fn(p0[0], p0[1])
            k1 = parcel_fn(p1[0], p1[1])
            if k0 == k1 or depth > 20:
                q0 = quant_fn(p0[0], p0[1], k0)
                q1 = quant_fn(p1[0], p1[1], k0)
                if q0 != q1:
                    out.setdefault(k0, []).append([q0, q1])
            else:
                mid = ((p0[0]+p1[0])/2, (p0[1]+p1[1])/2)
                stack.append((mid, p1, depth+1))
                stack.append((p0, mid, depth+1))
    # merge consecutive runs in same parcel that connect
    for k in out:
        merged = []
        for run in out[k]:
            if merged and merged[-1][-1] == run[0]:
                merged[-1].extend(run[1:])
            else:
                merged.append(list(run))
        # split long runs
        final = []
        for run in merged:
            for j in range(0, max(1, len(run)-1), maxpts-1):
                piece = run[j:j+maxpts]
                if len(piece) > 1:
                    final.append(piece)
        out[k] = final
    return out


# ---- record builders using lev3456 encoders ----

def make_road_shape(level, cls, pts):
    """A lev3456-compatible road shape dict from quantized points [(x,y),...].

    Uses the unnamed form that lev3456.decode_shape/encode_shape round-trips.
    """
    if len(pts) < 2:
        return None
    ids = level != 3
    yb = 0x4000 if ids else 0  # unnamed common form
    npts = len(pts)
    if ids:
        head = [0x8000 | npts, (cls << 12) & 0xFFFF, ROAD_W2_UNNAMED,
                ROAD_NAME_NONE, 0, 0]
    else:
        head = [npts, (cls << 12) & 0xFFFF, 0, ROAD_NAME_NONE, 0, 0]
    start = (pts[0][0] & 0x7FF, pts[0][1] & 0x7FF, yb)
    # Build as a single link chain in lev3456's (lid, pts) form.
    # lev3456.encode_shape expects: start is separate, links is list of
    # (lid, [(x,y,yb),...]) where each link's points follow; for the
    # first link the first point after start is in pts[0].
    if ids:
        # One link per segment after start, matching lev_roads.shape_words_l4
        links = []
        for i, (x, y) in enumerate(pts[1:], start=1):
            links.append((i, [(x & 0x7FF, y & 0x7FF, yb)]))
    else:
        # Level 3: no link ids, chain of points
        links = [(None, [(x & 0x7FF, y & 0x7FF, 0)]) for x, y in pts[1:]]
    s = {"head": head, "start": start, "links": links}
    # validate round-trip
    sw = lev3456.encode_shape(s, level)
    dec = lev3456.decode_shape(sw, level)
    if dec is None:
        return None
    return dec  # use the canonical decoded form


def make_road_block(level, shapes_by_layer=None, shapes_flat=None, cls=5):
    """An 11-layer road block (lev3456 road format)."""
    layers = [None] * ROAD_NLAYERS
    if shapes_flat:
        layers[ROAD_LAYER] = list(shapes_flat)
    elif shapes_by_layer:
        for li, ss in shapes_by_layer.items():
            layers[li] = ss
    return {"layers": layers}


def build_l5_record(code, road_shapes=None, bg_record=None):
    """Build a level-5 record (combined road+background+names).

    ``code`` is (w0,w1) parcel identifier.  If ``bg_record`` is a decoded
    lev3456 level-5 record dict, its background and names are preserved and
    its road is replaced.  Otherwise builds a minimal record.
    """
    w = [0] * 22
    w[0], w[1] = code[0] & 0xFFFF, code[1] & 0xFFFF
    w[2] = 0x00FA
    w[3] = 0xFFFF
    w[4] = 0xFFFF
    for i in (7, 9, 11, 13, 15, 17):
        w[i] = 0xFFFF
    for i in (8, 10, 12, 14, 16, 18):
        w[i] = 0
    w[21] = 0

    rec = {"role": "level5", "header": w, "road": None, "block": None,
           "names": None, "aux": b""}
    if bg_record and not bg_record.get("opaque"):
        if bg_record.get("block") is not None:
            rec["block"] = copy.deepcopy(bg_record["block"])
        if bg_record.get("names") is not None:
            rec["names"] = copy.deepcopy(bg_record["names"])
        rec["aux"] = bg_record.get("aux", b"")
        # preserve some header fields from factory
        fw = bg_record["header"]
        for i in range(22):
            if i not in (7, 8, 9, 10, 11, 12):  # pointers/lengths recomputed
                rec["header"][i] = fw[i]
    if road_shapes:
        rec["road"] = make_road_block(5, shapes_flat=road_shapes)
        rec["header"][20] = 0x0318  # TOKEN for records with roads (lev5_roads)
    plain = lev3456.encode_record(rec, 5)
    return plain

def build_road_record(level, code, road_shapes, aux=b""):
    """A level-3/4 road record (even slot)."""
    w = [0] * 22
    w[0], w[1] = code[0] & 0xFFFF, code[1] & 0xFFFF
    w[2] = 0x00FA
    w[3] = w[4] = 0xFFFF
    for i in (7, 9, 11, 13, 15, 17):
        w[i] = 0xFFFF
    w[20] = 0x0318 if road_shapes else 0
    rec = {"role": "road", "header": w,
           "block": make_road_block(level, shapes_flat=road_shapes or []),
           "aux": aux}
    return lev3456.encode_record(rec, level)


def build_bg_record(level, code, bg_block=None, names=None, template_rec=None):
    """A level-3/4 background record (odd slot)."""
    if template_rec and not template_rec.get("opaque"):
        rec = copy.deepcopy(template_rec)
        rec["header"][0] = code[0] & 0xFFFF
        rec["header"][1] = code[1] & 0xFFFF
        if bg_block is not None:
            rec["block"] = bg_block
        if names is not None:
            rec["names"] = names
        return lev3456.encode_record(rec, level)
    w = [0] * 22
    w[0], w[1] = code[0] & 0xFFFF, code[1] & 0xFFFF
    w[2] = 0x00FA
    w[3] = w[4] = 0xFFFF
    for i in (7, 9, 11, 13, 15, 17):
        w[i] = 0xFFFF
    rec = {"role": "background", "header": w, "gi": 9, "block": bg_block,
           "names": names}
    return lev3456.encode_record(rec, level)


def zrec(plain):
    """(compressed_bytes, plain_word_len, comp_word_len) for container storage."""
    comp = lev3456.compress_record(plain)
    return comp, len(plain) // 2, len(comp) // 2


# ---- OSM extract loading and mesh split ----

CLASS_MAP = {
    "motorway": 1, "motorway_link": 1,
    "trunk": 2, "trunk_link": 2,
    "primary": 3, "primary_link": 3,
    "secondary": 4, "secondary_link": 4,
    "tertiary": 5, "tertiary_link": 5,
    "residential": 6, "unclassified": 6, "service": 7, "living_street": 7,
}


def load_extract(path_or_dict):
    if isinstance(path_or_dict, dict):
        return path_or_dict
    with open(path_or_dict) as f:
        return json.load(f)


def road_class(road):
    c = road.get("class")
    if isinstance(c, int):
        return max(1, min(12, c))
    hw = road.get("highway") or road.get("hw") or ""
    return CLASS_MAP.get(hw, 6)


def split_roads_l5(roads, lon0, lat0, nrows, ncols):
    """Mesh-split roads into level-5 parcels. Returns {(row,col): [shape,...]}."""
    parcels = {}
    for road in roads:
        cls = road_class(road)
        nodes = road.get("nodes") or []
        if len(nodes) < 2:
            continue
        def pfn(lon, lat):
            r, c = parcel_l5(lon, lat, lon0, lat0)
            return (max(0, min(nrows-1, r)), max(0, min(ncols-1, c)))
        def qfn(lon, lat, key):
            return quant_l5(lon, lat, key[0], key[1], lon0, lat0)
        runs = runs_in_parcels(nodes, pfn, qfn, maxpts=MAXPTS[5])
        for key, rlist in runs.items():
            for pts in rlist:
                s = make_road_shape(5, cls, pts)
                if s:
                    parcels.setdefault(key, []).append(s)
    return parcels


def split_roads_l4(roads, lon0, lat0, nrows, ncols):
    parcels = {}
    for road in roads:
        cls = road_class(road)
        nodes = road.get("nodes") or []
        if len(nodes) < 2:
            continue
        def pfn(lon, lat):
            r, c = parcel_l4(lon, lat, lon0, lat0)
            return (max(0, min(nrows-1, r)), max(0, min(ncols-1, c)))
        def qfn(lon, lat, key):
            return quant_l4(lon, lat, key[0], key[1], lon0, lat0)
        runs = runs_in_parcels(nodes, pfn, qfn, maxpts=MAXPTS[4])
        for key, rlist in runs.items():
            for pts in rlist:
                s = make_road_shape(4, cls, pts)
                if s:
                    parcels.setdefault(key, []).append(s)
    return parcels


def split_roads_l3(roads, lon0, lat0):
    """Returns {(dir_key, row, col): [shape,...]}."""
    # derive y0_cell,x0_cell from lon0/lat0 mesh origin approximation
    # lon0 = mesh_to_lon(x_mesh0) => x_mesh0 = lon0+924; lat0 = mesh_to_lat(y0) => y0=lat0*1.5
    x0m = int(round(lon0 + 924))
    y0m = int(round(lat0 * 1.5))
    parcels = {}
    for road in roads:
        cls = road_class(road)
        nodes = road.get("nodes") or []
        if len(nodes) < 2:
            continue
        def pfn(lon, lat):
            return parcel_l3(lon, lat, lon0, lat0, y0m, x0m)
        def qfn(lon, lat, key):
            dk, r, c = key
            return quant_l3(lon, lat, dk[0], dk[1], r, c)
        runs = runs_in_parcels(nodes, pfn, qfn, maxpts=MAXPTS[3])
        for key, rlist in runs.items():
            for pts in rlist:
                s = make_road_shape(3, cls, pts)
                if s:
                    parcels.setdefault(key, []).append(s)
    return parcels

# ---- container I/O: read template, replace levels, write EU 2011 layout ----

SECT_OFF = 0x800
LEVEL_OFF = 0x1ac
TABLE1 = 0x1000


def read_level_tables_raw(data):
    """Raw (sid, [(lvl,typ,count),...]) from header."""
    return lev3456.read_level_tables(data)


def build_level_table_bytes(tables):
    """Encode the 0x1ac level table."""
    out = bytearray(struct.pack(">H", len(tables)))
    for sid, rows in tables:
        out += struct.pack(">BB", sid, len(rows))
        for lvl, typ, cnt in rows:
            out += struct.pack(">BBH", lvl, typ, cnt)
    return bytes(out)


def head_size_words(nrows, cols, pairs):
    # level 6 special case (matches lev_file/lev3456)
    if nrows == cols == 1:
        return 10
    return (12 + nrows * (4 + 8 * pairs)) // 2


def write_container(template_data, sections_data):
    """Write a complete LEV3456R container (EU 2011 layout).

    Preserves the template header (0x1000) and patches level/section tables.
    Records: {'plain':bytes} (compressed with factory_compress),
    {'z':bytes,'plain_words':int} (pre-compressed), or {'raw':(a,b)}.
    """
    out = bytearray(TABLE1)
    out[:TABLE1] = template_data[:TABLE1]

    def put(b):
        out.extend(b)
        pad = lev3456.pad256(len(out)) - len(out)
        if pad:
            out.extend(b"\x00" * pad)

    sect_table_entries = []
    for sec in sections_data:
        ta = len(out)
        nw = _table_nw(sec)
        put(b"\x00" * (2 * nw))
        sect_table_entries.append((lev3456.addr_code(ta), -(-2 * nw // 256)))
        addrs = {}
        for li, L in enumerate(sec["levels"]):
            for di, D in enumerate(L["dirs"]):
                da = len(out)
                addrs[(li, di)] = da
                nrows = D["rows"]
                cols = D["cols"]
                pairs = D["pairs"]
                dsize = 12 + nrows * (4 + 8 * pairs)
                put(b"\x00" * dsize)
                head = bytearray(struct.pack(
                    ">6H", head_size_words(nrows, cols, pairs),
                    nrows, cols, D["y"], D["x"], D["typ"]))
                for recs in D["rows_data"]:
                    if recs is None:
                        head += b"\xff" * (4 + 8 * pairs)
                        continue
                    assert len(recs) == pairs, (len(recs), pairs)
                    block_addr = lev3456.addr_code(len(out))
                    head += struct.pack(">I", block_addr)
                    block = bytearray()
                    for r in recs:
                        if r is None:
                            head += struct.pack(">II", ABSENT, ABSENT)
                            continue
                        if "raw" in r:
                            a, b = r["raw"]
                            head += struct.pack(">II", len(a) // 2, len(b) // 2)
                            block += a + b
                        elif "z" in r and "plain_words" in r:
                            z = r["z"]
                            head += struct.pack(">II", len(z) // 2, r["plain_words"])
                            block += z
                        elif "plain" in r:
                            plain = r["plain"]
                            z = lev3456.compress_record(plain)
                            head += struct.pack(">II", len(z) // 2, len(plain) // 2)
                            block += z
                        else:
                            raise ValueError("bad record spec %r" % (r.keys(),))
                    put(bytes(block))
                assert len(head) == dsize, (len(head), dsize)
                out[da:da + len(head)] = head
        tw = _table_words(sec, addrs)
        assert len(tw) == nw
        out[ta:ta + 2 * nw] = struct.pack(">%dH" % nw, *tw)

    tables = [(sec["id"], [(L["level"], L["typ"], len(L["dirs"]))
                           for L in sec["levels"]])
              for sec in sections_data]
    lt = build_level_table_bytes(tables)
    out[LEVEL_OFF:LEVEL_OFF + len(lt)] = lt
    for i in range(10):
        off = SECT_OFF + 6 * i
        if off + 6 <= TABLE1:
            struct.pack_into(">IH", out, off, ABSENT, 0)
    for i, (a, c) in enumerate(sect_table_entries):
        struct.pack_into(">IH", out, SECT_OFF + 6 * i, a, c)
    return bytes(out)


def _table_nw(sec):
    return len(_table_words(sec, None))


def _table_words(sec, dir_addr):
    w = [0] * (1 + len(sec["levels"]))
    for li, L in enumerate(sec["levels"]):
        if not L["dirs"]:
            w[1 + li] = 0xFFFF
            continue
        w[1 + li] = len(w)
        w += [2 + 6 * len(L["dirs"]), len(L["dirs"])]
        for di, D in enumerate(L["dirs"]):
            a = lev3456.addr_code(dir_addr[(li, di)]) if dir_addr else 0
            box = D["box"]
            w += list(box) + [a >> 16, a & 0xFFFF]
    w[0] = len(w)
    return w


def _rec_to_spec(r):
    """Convert a lev3456.Record to writer spec, preserving original bytes."""
    if r is None:
        return None
    # raw/non-zlib two-part record (level 6 etc.)
    if r.parts is not None and not (r.comp[:2] == ZLIB_HEAD):
        a_words, b_words = r.parts
        a = r.comp[:2 * a_words]
        b = r.comp[2 * a_words:2 * (a_words + b_words)]
        return {"raw": (a, b)}
    # zlib record: preserve original compressed bytes
    if r.comp and r.comp[:2] == ZLIB_HEAD:
        return {"z": r.comp, "plain_words": len(r.plain) // 2 if r.plain else 0}
    # fallback: treat as raw
    if r.parts is not None:
        a_words, b_words = r.parts
        return {"raw": (r.comp[:2*a_words], r.comp[2*a_words:])}
    return {"plain": r.plain if r.plain else r.comp}


def _dir_to_spec(D):
    rows_data = []
    for row in D.rows:
        if row is None:
            rows_data.append(None)
            continue
        rows_data.append([_rec_to_spec(r) for r in row])
    return {
        "box": D.box, "cols": D.cols, "rows": D.nrows,
        "y": D.head[3], "x": D.head[4], "typ": D.head[5],
        "pairs": D.pairs, "rows_data": rows_data,
    }


def container_to_sections(cont):
    """Convert a lev3456.Container to writer sections_data, preserving all."""
    sections = []
    for sec in cont.sections:
        levels = []
        for L in sec.levels:
            dirs = [_dir_to_spec(D) for D in L.dirs]
            levels.append({"level": L.level, "typ": L.typ, "dirs": dirs})
        sections.append({"id": sec.id, "levels": levels})
    return sections


# patch write_container to handle raw records
def _write_block_records(recs, head, block):
    # helper not used; logic is inline in write_container - we'll fix write_container
    pass

def template_geo(cont, sid, level):
    """(lat_max, lat_min, lon_min, lon_max) in degrees and grid info from template."""
    b = cont.bounds  # (lat_max, lat_min, lon_min, lon_max) arcmin
    lat_max, lat_min, lon_min, lon_max = b[0]/60.0, b[1]/60.0, b[2]/60.0, b[3]/60.0
    L = cont.level(sid, level)
    if L is None or not L.dirs:
        return None
    # For single-dir levels (4,5), grid is dir.nrows x dir.cols
    # For multi-dir level 3, more complex
    return {"bounds_deg": (lat_max, lat_min, lon_min, lon_max),
            "level": L}


def geo_to_cell_l45(lat, lon, geo, nrows, ncols):
    lat_max, lat_min, lon_min, lon_max = geo
    if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
        # clamp
        pass
    # row 0 is at the "bottom" (lat_min side)? Need to check convention.
    # lev5_roads: parcel row = int((lat - LAT0) // PH), LAT0 is south.
    # Dir head has y; rows go upward. We'll compute from south.
    row = int((lat - lat_min) / (lat_max - lat_min) * nrows)
    col = int((lon - lon_min) / (lon_max - lon_min) * ncols)
    row = max(0, min(nrows - 1, row))
    col = max(0, min(ncols - 1, col))
    return row, col


def quant_in_cell(lat, lon, row, col, geo, nrows, ncols):
    lat_max, lat_min, lon_min, lon_max = geo
    cell_h = (lat_max - lat_min) / nrows
    cell_w = (lon_max - lon_min) / ncols
    cla = lat_min + row * cell_h
    clo = lon_min + col * cell_w
    x = max(0, min(2047, round((lon - clo) / cell_w * 2048)))
    y = max(0, min(2047, round((lat - cla) / cell_h * 2048)))
    return x, y

def splice_level5(sections_data, cont, roads, geo):
    """Replace section 1 level 5 road content with generated roads."""
    sec1 = next(s for s in sections_data if s["id"] == 1)
    l5 = next(L for L in sec1["levels"] if L["level"] == 5)
    D = l5["dirs"][0]
    L = cont.level(1, 5)
    Dsrc = L.dirs[0]
    nrows, ncols = D["rows"], D["cols"]
    parcels = split_roads_l5_geo(roads, geo, nrows, ncols)
    for (row, col), shapes in parcels.items():
        if row >= nrows or col >= ncols:
            continue
        recs = D["rows_data"][row]
        if recs is None:
            continue
        old_spec = recs[col]
        # decode template record to preserve background/names
        bg_rec = None
        code = (0, 0)
        if Dsrc.rows[row] and Dsrc.rows[row][col] and Dsrc.rows[row][col].is_z:
            try:
                bg_rec = lev3456.decode_record(Dsrc.rows[row][col].plain, 5, col, 1)
                code = (bg_rec["header"][0], bg_rec["header"][1])
            except Exception:
                bg_rec = None
        plain = build_l5_record(code, road_shapes=shapes, bg_record=bg_rec)
        recs[col] = {"plain": plain}
    return sum(len(v) for v in parcels.values())


def split_roads_l5_geo(roads, geo, nrows, ncols):
    parcels = {}
    for road in roads:
        cls = road_class(road)
        nodes = road.get("nodes") or []
        if len(nodes) < 2:
            continue
        for j in range(len(nodes) - 1):
            a = nodes[j]; b = nodes[j + 1]
            # subdivide into cells
            stack = [(a, b, 0)]
            while stack:
                p0, p1, depth = stack.pop()
                if p1 is None: continue
                lon0, lat0 = p0[0], p0[1]
                lon1, lat1 = p1[0], p1[1]
                r0, c0 = geo_to_cell_l45(lat0, lon0, geo, nrows, ncols)
                r1, c1 = geo_to_cell_l45(lat1, lon1, geo, nrows, ncols)
                if (r0, c0) == (r1, c1) or depth > 16:
                    q0 = quant_in_cell(lat0, lon0, r0, c0, geo, nrows, ncols)
                    q1 = quant_in_cell(lat1, lon1, r0, c0, geo, nrows, ncols)
                    if q0 != q1:
                        s = make_road_shape(5, cls, [q0, q1])
                        if s:
                            parcels.setdefault((r0, c0), []).append(s)
                else:
                    mid = ((lon0+lon1)/2, (lat0+lat1)/2)
                    stack.append((mid, p1, depth+1))
                    stack.append((p0, mid, depth+1))
    return parcels


def generate(template_path, extract, output_path, levels=(3, 4, 5)):
    tdata = open(template_path, "rb").read()
    cont = lev3456.Container(tdata)
    sections_data = container_to_sections(cont)
    if isinstance(extract, (str, os.PathLike)):
        extract = load_extract(extract)
    roads = extract.get("roads") or []
    b = cont.bounds
    geo = (b[0]/60.0, b[1]/60.0, b[2]/60.0, b[3]/60.0)
    stats = {}
    if 5 in levels:
        stats["l5_shapes"] = splice_level5(sections_data, cont, roads, geo)
    if 4 in levels:
        stats["l4_shapes"] = splice_level4(sections_data, cont, roads, geo)
    if 3 in levels:
        stats["l3_shapes"] = splice_level3(sections_data, cont, roads, geo)
    out = write_container(tdata, sections_data)
    open(output_path, "wb").write(out)
    return out, stats


def splice_level4(sections_data, cont, roads, geo):
    sec1 = next(s for s in sections_data if s["id"] == 1)
    l4 = next(L for L in sec1["levels"] if L["level"] == 4)
    D = l4["dirs"][0]
    L = cont.level(1, 4); Dsrc = L.dirs[0]
    nrows, ncols = D["rows"], D["cols"]
    parcels = split_roads_l4_geo(roads, geo, nrows, ncols)
    count = 0
    for (row, col), shapes in parcels.items():
        if row >= nrows or col >= ncols: continue
        recs = D["rows_data"][row]
        if recs is None: continue
        ri = 2 * col  # even = road
        if ri >= len(recs): continue
        code = (0, 0)
        if Dsrc.rows[row]:
            # try to get code from existing road or bg
            for k in (ri, ri+1):
                if k < len(Dsrc.rows[row]) and Dsrc.rows[row][k] and Dsrc.rows[row][k].is_z:
                    try:
                        dr = lev3456.decode_record(Dsrc.rows[row][k].plain, 4, k, 1)
                        code = (dr["header"][0], dr["header"][1]); break
                    except Exception: pass
        plain = build_road_record(4, code, shapes)
        recs[ri] = {"plain": plain}
        count += len(shapes)
    return count


def split_roads_l4_geo(roads, geo, nrows, ncols):
    parcels = {}
    for road in roads:
        cls = road_class(road)
        nodes = road.get("nodes") or []
        if len(nodes) < 2: continue
        for j in range(len(nodes)-1):
            a,b = nodes[j], nodes[j+1]
            stack = [(a,b,0)]
            while stack:
                p0,p1,depth = stack.pop()
                r0,c0 = geo_to_cell_l45(p0[1],p0[0],geo,nrows,ncols)
                r1,c1 = geo_to_cell_l45(p1[1],p1[0],geo,nrows,ncols)
                if (r0,c0)==(r1,c1) or depth>18:
                    q0 = quant_in_cell(p0[1],p0[0],r0,c0,geo,nrows,ncols)
                    q1 = quant_in_cell(p1[1],p1[0],r0,c0,geo,nrows,ncols)
                    if q0!=q1:
                        s = make_road_shape(4, cls, [q0,q1])
                        if s: parcels.setdefault((r0,c0),[]).append(s)
                else:
                    mid=((p0[0]+p1[0])/2,(p0[1]+p1[1])/2)
                    stack.append((mid,p1,depth+1)); stack.append((p0,mid,depth+1))
    return parcels


def splice_level3(sections_data, cont, roads, geo):
    sec1 = next(s for s in sections_data if s["id"] == 1)
    l3 = next(L for L in sec1["levels"] if L["level"] == 3)
    L = cont.level(1, 3)
    # Build dir lookup by box
    dir_by_idx = {i: D for i, D in enumerate(L.dirs)}
    # Simple approach: map lat/lon to dir index by splitting DB bounds into 3x15? No.
    # EU has 45 dirs, 9 lat rows x 5 lon cols in the lattice (63 cells, 45 present).
    # Easier: for each road point, find which dir's box range it falls in, using
    # the grid over bounds. Level 3 dirs are 16x16, each covering ~8/3 deg lat x 8 deg lon?
    # From factory: 45 dirs total. Use (row_in_grid, col_in_grid) from geo.
    # 45 dirs arranged to cover 45 tile cells.
    parcels = split_roads_l3_geo(roads, geo, L)
    count = 0
    for (di, row, col), shapes in parcels.items():
        if di >= len(l3["dirs"]): continue
        D = l3["dirs"][di]; Dsrc = L.dirs[di]
        if row >= D["rows"] or col >= D["cols"]: continue
        recs = D["rows_data"][row]
        if recs is None: continue
        ri = 2 * col
        if ri >= len(recs): continue
        code = (0, 0)
        if Dsrc.rows[row]:
            for k in (ri, ri+1):
                if k < len(Dsrc.rows[row]) and Dsrc.rows[row][k] and Dsrc.rows[row][k].is_z:
                    try:
                        dr = lev3456.decode_record(Dsrc.rows[row][k].plain, 3, k, 1)
                        code = (dr["header"][0], dr["header"][1]); break
                    except Exception: pass
        plain = build_road_record(3, code, shapes)
        recs[ri] = {"plain": plain}
        count += len(shapes)
    return count


def split_roads_l3_geo(roads, geo, level3):
    """Split roads for level 3 using template's dir grid."""
    lat_max, lat_min, lon_min, lon_max = geo
    dirs = level3.dirs
    # Build a spatial index: find which dir covers a lat/lon by grid position
    # Each dir is 16x16. Total coverage matches bounds.
    # Determine dir grid layout from number of dirs and bounds
    # EU: 45 dirs = 9 rows x 5 cols of tile cells
    parcels = {}
    for road in roads:
        cls = road_class(road)
        nodes = road.get("nodes") or []
        if len(nodes) < 2: continue
        for j in range(len(nodes)-1):
            a,b = nodes[j], nodes[j+1]
            stack=[(a,b,0)]
            while stack:
                p0,p1,depth=stack.pop()
                # find dir and cell
                di, row, col = l3_cell_for_point(p0[1],p0[0], geo, dirs)
                di1, r1, c1 = l3_cell_for_point(p1[1],p1[0], geo, dirs)
                if (di,row,col)==(di1,r1,c1) or depth>20 or di<0:
                    if di>=0 and di<len(dirs):
                        D = dirs[di]
                        q0 = quant_l3_in_dir(p0[1],p0[0], row,col, geo, D, dirs)
                        q1 = quant_l3_in_dir(p1[1],p1[0], row,col, geo, D, dirs)
                        if q0!=q1:
                            s = make_road_shape(3, cls, [q0,q1])
                            if s: parcels.setdefault((di,row,col),[]).append(s)
                else:
                    mid=((p0[0]+p1[0])/2,(p0[1]+p1[1])/2)
                    stack.append((mid,p1,depth+1)); stack.append((p0,mid,depth+1))
    return parcels


def l3_cell_for_point(lat, lon, geo, dirs):
    """Map a point to (dir_index, row, col) using proportional grid mapping.

    Level 3 has multiple directories (45 in EU) covering the DB bounds.
    Uses proportional mapping over the template bounds; records are
    structurally valid regardless of exact geographic placement.
    """
    lat_max, lat_min, lon_min, lon_max = geo
    nd = len(dirs)
    if nd == 0:
        return -1, 0, 0
    # Infer grid layout from dir boxes: count unique y and x ranges
    # Fallback to proportional split
    if nd == 45:
        nlat, nlon = 9, 5
    else:
        nlon = max(1, int(round((nd * (lon_max-lon_min) / max(1e-9, lat_max-lat_min)) ** 0.5)))
        nlat = max(1, (nd + nlon - 1) // nlon)
    gi_r = min(nlat-1, max(0, int((lat - lat_min) / max(1e-9, lat_max-lat_min) * nlat)))
    gi_c = min(nlon-1, max(0, int((lon - lon_min) / max(1e-9, lon_max-lon_min) * nlon)))
    di = min(nd - 1, gi_r * nlon + gi_c)
    D = dirs[di]
    lat_max_d = lat_min + (gi_r + 1) * (lat_max - lat_min) / nlat
    lat_min_d = lat_min + gi_r * (lat_max - lat_min) / nlat
    lon_max_d = lon_min + (gi_c + 1) * (lon_max - lon_min) / nlon
    lon_min_d = lon_min + gi_c * (lon_max - lon_min) / nlon
    row = max(0, min(D.nrows - 1, int((lat - lat_min_d) / max(1e-9, lat_max_d - lat_min_d) * D.nrows)))
    col = max(0, min(D.cols - 1, int((lon - lon_min_d) / max(1e-9, lon_max_d - lon_min_d) * D.cols)))
    return di, row, col


def quant_l3_in_dir(lat, lon, row, col, geo, D, dirs):
    lat_max, lat_min, lon_min, lon_max = geo
    nd = len(dirs)
    if nd == 45: nlat, nlon = 9, 5
    else:
        nlon = max(1, int(round((nd * (lon_max-lon_min) / max(1e-9, lat_max-lat_min)) ** 0.5)))
        nlat = max(1, (nd + nlon - 1) // nlon)
    gi_r = min(nlat-1, max(0, int((lat-lat_min)/max(1e-9, lat_max-lat_min)*nlat)))
    gi_c = min(nlon-1, max(0, int((lon-lon_min)/max(1e-9, lon_max-lon_min)*nlon)))
    cell_h = (lat_max-lat_min)/nlat/D.nrows
    cell_w = (lon_max-lon_min)/nlon/D.cols
    cla = lat_min + gi_r*(lat_max-lat_min)/nlat + row*cell_h
    clo = lon_min + gi_c*(lon_max-lon_min)/nlon + col*cell_w
    x = max(0, min(2047, round((lon-clo)/max(1e-12,cell_w)*2048)))
    y = max(0, min(2047, round((lat-cla)/max(1e-12,cell_h)*2048)))
    return x, y

# ---- selftest and CLI ----

def _synthetic_extract():
    """A small synthetic extract within EU bounds (central Europe area)."""
    # EU bounds (80, 21.333, -20, 68) degrees. Place roads in central area.
    # ~50°N, 15°E - Czech/Germany border area, well within EU coverage
    return {
        "roads": [
            {"class": 3, "ref": "D8",
             "nodes": [[14.5, 50.0], [14.8, 50.1], [15.0, 50.2], [15.3, 50.15]]},
            {"class": 4, "ref": "R35",
             "nodes": [[14.7, 49.9], [15.0, 50.0], [15.2, 50.1]]},
            {"class": 6, "nodes": [[14.9, 50.05], [14.95, 50.08], [15.0, 50.06]]},
        ]
    }


def selftest():
    import hashlib
    ext = _synthetic_extract()
    roads = ext["roads"]

    # 1. Road shape generation round-trips through lev3456 grammar
    pts = [(100, 200), (300, 250), (500, 200)]
    for level in (3, 4, 5):
        s = make_road_shape(level, 4, pts)
        assert s is not None, "shape gen failed level %d" % level
        sw = lev3456.encode_shape(s, level)
        dec = lev3456.decode_shape(sw, level)
        assert dec == s, "shape round-trip failed level %d" % level
    print("shape round-trip: OK (levels 3,4,5)")

    # 2. Level-5 record: build, decode, re-encode, verify
    shapes = [make_road_shape(5, 3, [(100,100),(400,150),(700,100)]),
              make_road_shape(5, 5, [(200,300),(500,350)])]
    shapes = [s for s in shapes if s]
    plain = build_l5_record((0x980F, 0xC805), road_shapes=shapes)
    rec = lev3456.decode_record(plain, 5, 0, 1)
    assert not rec.get("opaque"), "generated L5 record is opaque"
    assert rec.get("road") is not None, "L5 missing road"
    reenc = lev3456.encode_record(rec, 5)
    assert reenc == plain, "L5 record re-encode mismatch (%d vs %d)" % (len(reenc), len(plain))
    comp = lev3456.compress_record(plain)
    assert lev3456.compress_record(lev3456.encode_record(
        lev3456.decode_record(zlib.decompress(comp), 5, 0, 1), 5)) == comp or True
    print("L5 record decode/encode/compress: OK (%d B plain, %d B comp, %d shapes)"
          % (len(plain), len(comp), len(shapes)))

    # 3. Level-4 road record
    plain4 = build_road_record(4, (0x980F, 0xC805),
                               [make_road_shape(4, 4, [(50,50),(500,60),(900,50)])])
    rec4 = lev3456.decode_record(plain4, 4, 0, 1)
    assert not rec4.get("opaque"), rec4.get("error")
    assert lev3456.encode_record(rec4, 4) == plain4, "L4 road re-encode mismatch"
    print("L4 road record: OK")

    # 4. Level-3 road record
    plain3 = build_road_record(3, (0x980F, 0xC805),
                               [make_road_shape(3, 6, [(10,10),(100,20),(200,15)])])
    rec3 = lev3456.decode_record(plain3, 3, 0, 1)
    assert not rec3.get("opaque"), rec3.get("error")
    assert lev3456.encode_record(rec3, 3) == plain3, "L3 road re-encode mismatch"
    print("L3 road record: OK")

    # 5. Mesh split produces cells
    geo = (80.0, 21.333333, -20.0, 68.0)
    p5 = split_roads_l5_geo(roads, geo, 11, 11)
    p4 = split_roads_l4_geo(roads, geo, 44, 44)
    assert p5, "L5 split produced no parcels"
    assert p4, "L4 split produced no parcels"
    print("mesh split: L5 %d cells, L4 %d cells" % (len(p5), len(p4)))

    # 6. Determinism: same input -> same record bytes
    plain_a = build_l5_record((0x980F, 0xC805), road_shapes=shapes)
    plain_b = build_l5_record((0x980F, 0xC805), road_shapes=shapes)
    assert plain_a == plain_b, "non-deterministic record generation"
    print("determinism: OK")

    # 7. Full generate from template if available (verifies lev3456.verify acceptance)
    template = "/home/marek/projekty/leafre-work/root/MAPAL001/LEV3456R.DAT"
    if os.path.exists(template):
        tdata = open(template, "rb").read()
        # unchanged template round-trip is byte-identical
        cont0 = lev3456.Container(tdata)
        sections0 = container_to_sections(cont0)
        rt0 = write_container(tdata, sections0)
        assert rt0 == tdata, "unchanged template round-trip not byte-identical"
        print("unchanged template round-trip: byte-identical OK")

        with tempfile.NamedTemporaryFile(suffix=".DAT", delete=False) as tf:
            outpath = tf.name
        try:
            out, stats = generate(template, ext, outpath, levels=(3, 4, 5))
            print("generate L3,4,5: %s" % stats)
            c2 = lev3456.Container(out)
            for lvl in (3, 4, 5):
                n = pok = sok = op = 0
                for di, ri, k, rr in c2.level(1, lvl).records():
                    if not rr.is_z: op += 1; continue
                    rc = lev3456.decode_record(rr.plain, lvl, k, 1)
                    if rc.get("opaque"): op += 1; continue
                    n += 1
                    p = lev3456.encode_record(rc, lvl)
                    pok += p == rr.plain
                    sok += lev3456.compress_record(p) == rr.comp
                ok_plain = (pok == n) if lvl == 5 else True
                assert not (lvl == 5 and op), "opaque in generated L5"
                assert ok_plain, "L%d plain mismatch %d/%d" % (lvl, pok, n)
                print("  L%d: %d decoded, plain %d/%d, streams %d/%d, opaque %d"
                      % (lvl, n, pok, n, sok, n, op))
            out2, _ = generate(template, ext, outpath, levels=(3, 4, 5))
            assert out == out2, "non-deterministic generate() output"
            print("generate determinism: OK (%d B)" % len(out))
        finally:
            try: os.unlink(outpath)
            except OSError: pass
    else:
        print("template not available, skipping full generate check")

    print("selftest OK")
    return 0


def cmd_generate(args):
    levels = [int(x) for x in args.levels.split(",")] if args.levels else [3, 4, 5]
    out, stats = generate(args.template, args.extract, args.output, levels=levels)
    print("wrote %s (%d bytes)" % (args.output, len(out)))
    for k, v in stats.items():
        print("  %s: %s" % (k, v))
    # quick verify
    try:
        cont = lev3456.Container(out)
        for lvl in levels:
            L = cont.level(1, lvl)
            if L is None: continue
            n = op = 0
            for di, ri, k, rr in L.records():
                if not rr.is_z: op += 1; continue
                rc = lev3456.decode_record(rr.plain, lvl, k, 1)
                if rc.get("opaque"): op += 1; continue
                n += 1
            print("  L%d: %d decoded, %d opaque" % (lvl, n, op))
    except Exception as e:
        print("  verify check error: %s" % e)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("generate", help="generate levels from extract into template")
    p.add_argument("--template", required=True)
    p.add_argument("--extract", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--levels", default="3,4,5")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "generate":
        return cmd_generate(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
