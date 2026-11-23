#!/usr/bin/env python3
"""tile_from_zero.py — write OSM roads into a tile that holds no factory record (M5.88, Z3).

The splice writer (``tilewriter.py --factory``) can only replace records in
slots the factory tile already has (M5.70); a from-zero tile has none.  This
tool takes the container of a tile (``tile_relayout.read_model`` +
``empty_model``: section tables and every directory, all empty; M5.87), builds
one level-1 road record per parcel with ``tilewriter.build_road_record`` from
mesh-split IMF, puts each record into its directory row and column (even
pair; the odd partner stays empty), and lets ``tile_relayout.write_model``
lay the tile out.  No factory record is copied (``tile_provenance.py
--require-zero`` is the gate).

    tile_from_zero.py SPLIT.jsonl --template TILE.DAT --cell B48R068R \\
        --class-table CLASS.json --country 826 -o OUT.DAT [--json] [--no-names]
    tile_from_zero.py --selftest

The template supplies only the container (header strings, level/box tables,
directory boxes); M5.86 counts those bytes.  Level 1 only.  Exit codes: 0 ok,
1 check failed, 2 usage.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE / "ze0-viewer" / "tools_ze0", HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import fa_encode  # noqa: E402
import tile_relayout  # noqa: E402
import tilewriter  # noqa: E402

UNITS = 2048
EMPTY1 = 0x7FFFFFFF  # empty even pair, level 1
EMPTY_ODD = 0xFFFFFFFF  # empty odd pair, level 1 (0x7fffffff here moves the read 4 GiB, M5.88)
# No record-size ceiling is known: the firmware inflates into a window of the
# record's size rounded up to 256 (L3, M5.88: 101,128 B and 156,356 B records
# read with reply sub 3, the 101,128-B start parcel draws at L4).  --max-plain
# keeps a cap for the capacity probe (M5.92): it drops a parcel's least
# important roads until the record fits.


class CheckFailed(Exception):
    pass


def level1_dirs(m: dict) -> dict:
    """``{(y0, x0): directory model}`` of section 1 level 1."""
    out = {}
    for sec in m["sections"]:
        if sec["id"] != 1:
            continue
        for L in sec["levels"]:
            if L["level"] != 1:
                continue
            for dm in L["dirs"]:
                wm = dm["wm"]
                out[(wm["y"], tilewriter.dir_x0(wm))] = dm
    return out


def place(m: dict, built: dict, odd: dict | None = None) -> dict:
    """Put ``{parcel: (plain, comp)}`` road records (even) and background
    records (``odd``) into the level-1 directories of ``m``.

    A row block holds, column by column, the even record then the odd one
    (the order ``s1_wide_dir`` reads); an empty even pair is ``0x7fffffff``,
    an empty odd pair ``0xffffffff`` (M5.88)."""
    odd = odd or {}
    dirs = level1_dirs(m)
    rows = collections.defaultdict(dict)
    missing = 0
    for part, recs in (("even", built), ("odd", odd)):
        for (y0, x0, row, col), rec in recs.items():
            if (y0, x0) not in dirs:
                missing += 1
                continue
            rows[(y0, x0, row)].setdefault(col, {})[part] = rec
    if missing:
        raise CheckFailed("%d parcel(s) have no level-1 directory in the template" % missing)
    stats = collections.Counter()
    for (y0, x0, row), cols in rows.items():
        dm = dirs[(y0, x0)]
        r = dm["wm"]["rows"][row]
        if r["wide"]:
            raise CheckFailed("template row is wide; run tile_relayout empty first")
        block = b""
        recs = []
        for c in range(len(r["cols"])):
            if c not in cols:
                continue
            pair = {}
            for part, empty in (("even", (EMPTY1, EMPTY1)), ("odd", (EMPTY_ODD, EMPTY_ODD))):
                if part not in cols[c]:
                    pair[part] = empty
                    continue
                plain, comp = cols[c][part]
                if len(comp) % 2 or len(plain) % 2:
                    raise CheckFailed("record not word aligned")
                pair[part] = (len(comp) // 2, len(plain) // 2)
                block += comp
                recs.append(comp)
                stats["records"] += 1
                stats[part + "_records"] += 1
                stats["plain_bytes"] += len(plain)
                stats["comp_bytes"] += len(comp)
            r["cols"][c] = dict(even=pair["even"], odd=pair["odd"], subs=[])
        unit = dm["units"][row]
        unit.update(live=True, old=("new", y0, x0, row), block=block, recs=recs, tag=0)
        stats["rows"] += 1
    return dict(stats)


# --------------------------------------------------------------------------
# Background (odd) records from osm_areas.py features (M5.89, Z4)
# --------------------------------------------------------------------------

# (layer, shape type) per kind, from the London tile's level-1 census
# (EXP-2026-11-23-M5.89): layer 0 0xc12b urban area, layer 3 0xc11a forest /
# 0xc11b heath / 0xc11d park, layer 7 0xc114 river area / 0xc115 water.
BG_TYPES = {"urban": (0, 0xC12B), "forest": (3, 0xC11A), "heath": (3, 0xC11B), "park": (3, 0xC11D),
            "riverarea": (7, 0xC114), "water": (7, 0xC115)}
BG_TOLERANCE_M = 3.0  # M5.75 level-1 default
BG_W34 = (0x347A, 0x2AEF)  # level-1 header words 3/4 (clarion_bg.LEVELS[1]["w34"])
MAX_SUBS, MAX_PER_SUB = 8, 255  # parse_group: <= 8 sub-groups of <= 255 shapes


# Place labels (M5.90): the factory start parcel stores district names
# (MAYFAIR, SOHO, ...) as names-section entries ``type 0xc068, flags 0x4800,
# x, y, 0x0c00, len, text`` after the area names and before the road names,
# and a layer-25 point group (kind byte 3) of ``0xc00c, 0xffff, x, y`` at the
# same coordinates in the same order.
PLACE_TYPE, PLACE_FLAGS, PLACE_STYLE, POINT_TYPE = 0xC068, 0x4800, 0x0C00, 0xC00C
PLACE_KINDS = {"city", "town", "suburb", "quarter", "neighbourhood", "village"}


def _entries_end(sec: bytes) -> int:
    n = struct.unpack_from(">H", sec, 2)[0]
    i = 24
    for _ in range(n):
        flags = struct.unpack_from(">H", sec, i + 2)[0]
        head = 12 if flags & 0x4000 else 10  # place entries carry one more word
        ln = struct.unpack_from(">H", sec, i + head - 2)[0]
        i += head + ln + (ln & 1)
    return i


def names_with_places(sec: bytes | None, places) -> bytes:
    """A names section (fa_encode layout) with place-label entries appended
    after the road-name entries; road word offsets do not move."""
    if sec is None:
        sec = struct.pack(">HH", 6, 0) + b"\xff\xff\x00\x00" + struct.pack(">HH", 6, 0) + b"\xff\xff\x00\x00" * 3 \
            + struct.pack(">HH", 8, 0) + b"\xff\xff\x00\x00" * 3
    n = struct.unpack_from(">H", sec, 2)[0]
    end = _entries_end(sec)
    sub_at = 4 * struct.unpack_from(">H", sec, 8)[0]
    body = bytearray(sec[24:end])
    for x, y, text in places:
        t = text.encode("latin-1", "replace")
        if len(t) % 2:
            t += b"\0"
        body += struct.pack(">6H", PLACE_TYPE, PLACE_FLAGS, x, y, PLACE_STYLE, len(t)) + t
    # a place entry has one more word than a road entry: the walker keys on
    # the type, so road offsets are kept and places follow them
    while len(body) % 4:
        body += b"\0"
    out = bytearray(sec[:24]) + body + sec[sub_at:]
    struct.pack_into(">H", out, 2, n + len(places))
    struct.pack_into(">H", out, 8, (24 + len(body)) // 4)
    return bytes(out)


def place_points_group(places) -> dict:
    g = struct.pack(">HH", 1, 3) + bytes([3, len(places)])
    for x, y, _t in places:
        g += struct.pack(">4H", POINT_TYPE, 0xFFFF, x, y)
    while len(g) % 4:
        g += b"\0"
    return dict(raw=g)


def _ring_area(pts) -> float:
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:]))) / 2


def _parcels_over(bbox, level=1):
    """Every level-1 parcel a lon/lat bbox touches."""
    import clarion_bg
    w, s, e, n = bbox
    p0 = tilewriter.parcel_of(w, s, level)
    lon0, lat0, pw, ph = clarion_bg.parcel_geo(level, *p0)
    out = set()
    lat = lat0 + ph / 2
    while lat - ph / 2 <= n:
        lon = lon0 + pw / 2
        while lon - pw / 2 <= e:
            out.add(tilewriter.parcel_of(lon, lat, level))
            lon += pw
        lat += ph
    return out


def build_background(areas_path: str | None, country: int, only: set | None = None, urban_fill: float = 0.0,
                     names: dict | None = None, with_places: bool = False):
    """``{parcel: plain}`` background records and stats from an osm_areas JSONL."""
    import clarion_bg
    from bg_writer import clip_polygon
    from slot_budget import dp_simplify
    shapes = collections.defaultdict(lambda: collections.defaultdict(list))
    stats = collections.Counter()
    names = names or {}
    places = collections.defaultdict(list)
    translit = None
    if with_places:
        from transliterate import apply, load_table
        present, mapping, _t = load_table()
        translit = lambda t: apply(t, present, mapping)  # noqa: E731
    with open(areas_path or "/dev/null", encoding="utf-8") as fh:
        for line in fh:
            f = json.loads(line)
            kind = f["kind"]
            if kind == "place":
                if f.get("place") in PLACE_KINDS and with_places:
                    lon, lat = f["point"]
                    parcel = tilewriter.parcel_of(lon, lat, 1)
                    lon0, lat0, pw, ph = clarion_bg.parcel_geo(1, *parcel)
                    x, y = tilewriter.quantise(lon, lat, lon0, lat0, pw, ph)
                    name = f["name"].upper()
                    if translit:
                        name = translit(name)
                    places[parcel].append((x, y, name))
                    stats["places"] += 1
                continue
            if kind not in BG_TYPES or only and kind not in only:
                stats["skipped_" + kind] += 1
                continue
            stats["holes_ignored"] += len(f.get("holes", []))
            for ring in f["rings"]:
                ring = [tuple(p) for p in ring]
                simp, _err = dp_simplify(ring, BG_TOLERANCE_M)
                if len(simp) < 4:
                    stats["degenerate"] += 1
                    continue
                xs = [p[0] for p in simp]
                ys = [p[1] for p in simp]
                for parcel in _parcels_over((min(xs), min(ys), max(xs), max(ys))):
                    lon0, lat0, pw, ph = clarion_bg.parcel_geo(1, *parcel)
                    clipped = clip_polygon(simp, (lon0, lat0, lon0 + pw, lat0 + ph))
                    if len(clipped) < 3:
                        continue
                    q = [tilewriter.quantise(lon, lat, lon0, lat0, pw, ph) for lon, lat in clipped]
                    ded = [q[0]]
                    for p in q[1:]:
                        if p != ded[-1]:
                            ded.append(p)
                    if ded[0] != ded[-1]:
                        ded.append(ded[0])
                    if len(ded) < 4 or _ring_area(ded) < 1:
                        continue
                    shapes[parcel][kind].append(ded)
                    stats["shapes_" + kind] += 1
    out = {}
    full = [(0, 0), (UNITS - 1, 0), (UNITS - 1, UNITS - 1), (0, UNITS - 1), (0, 0)]
    for parcel in set(names) | set(places):
        shapes.setdefault(parcel, collections.defaultdict(list))
    for parcel, by_kind in shapes.items():
        if urban_fill and by_kind.get("urban"):
            # Generalised built-up area (HYPOTHESIS, M5.89): the factory's
            # level-1 0xc12b is one parcel-wide polygon in central London,
            # while OSM landuse covers blocks.  A parcel whose urban rings
            # cover >= urban_fill of it (sum of ring areas, capped at 1) gets
            # one full-parcel ring instead.
            share = min(1.0, sum(_ring_area(r) for r in by_kind["urban"]) / float((UNITS - 1) ** 2))
            if share >= urban_fill:
                stats["urban_filled_parcels"] += 1
                by_kind["urban"] = [list(full)]
        layers = collections.defaultdict(list)
        for kind, rings in by_kind.items():
            layer, typ = BG_TYPES[kind]
            for pts in rings:
                layers[layer].append(dict(type=typ, ref=0xFFFF, pts=pts))
        model_layers = {}
        for layer, items in layers.items():
            items.sort(key=lambda sh: -_ring_area(sh["pts"]))  # big first, small drawn on top
            cap = MAX_SUBS * MAX_PER_SUB
            if len(items) > cap:
                stats["dropped_small"] += len(items) - cap
                items = items[:cap]
            subs = [dict(kind=0x80, shapes=items[i:i + MAX_PER_SUB]) for i in range(0, len(items), MAX_PER_SUB)]
            model_layers[layer] = dict(subs[0], more=subs[1:]) if len(subs) > 1 else subs[0]
        y0, x0, row, col = parcel
        per = clarion_bg.LEVELS[1]["rows"] // clarion_bg.LEVELS[1]["dir_meshes"]
        hdr = [0] * 22
        hdr[0], hdr[1] = clarion_bg.parcel_code(1, y0 * per + row, x0 * per + col)
        hdr[2], (hdr[3], hdr[4]) = 0xFA, BG_W34
        hdr[20] = country
        if places.get(parcel):
            pl = places[parcel][:255]
            model_layers[25] = place_points_group(pl)
            names[parcel] = names_with_places(names.get(parcel), pl)
        sections = {"names": names[parcel]} if parcel in names else {}
        if sections:
            stats["names_sections"] += 1
        plain = clarion_bg.build_record(dict(hdr=hdr, nlayers=26, layers=model_layers, sections=sections,
                                             gi=9, strict=True))
        back = clarion_bg.parse_record(plain)
        got = collections.Counter(sh["type"] for g in back["layers"].values() if "raw" not in g
                                  for s in [g] + g.get("more", []) for sh in s["shapes"])
        want = collections.Counter(sh["type"] for items in layers.values() for sh in items[:MAX_SUBS * MAX_PER_SUB])
        got.pop(0xFFFF, None)  # the raw layer-25 point group parses as one pseudo shape
        if sections and back["sections"].get("names") != sections["names"]:
            raise CheckFailed("names section of %r does not read back" % (parcel,))
        if got != want:
            raise CheckFailed("background record of %r does not read back: %s vs %s" % (parcel, got, want))
        out[parcel] = plain
        stats["records"] += 1
    return out, dict(stats)


def label_of(name: str, ref: str, translit=None) -> str:
    """``1=NAME;2=REF`` as the factory writes it (EU2011 London: upper case,
    first ``ref`` only, flags ``0x2800``; EXP-2026-11-23-M5.90)."""
    name = name[2:] if name.startswith("1=") else name
    name = name.strip().upper()
    ref = (ref or "").split(";")[0].strip().upper()
    if translit:
        name = translit(name)
    parts = []
    if name:
        parts.append("1=" + name)
    if ref:
        parts.append("2=" + ref)
    return ";".join(parts)


NAME_FLAGS = 0x2800  # every road-name entry of the factory London start parcel (712/712)


def set_name_flags(sec: bytes, flags: int = NAME_FLAGS) -> bytes:
    """Rewrite the flags word of every ``0x00ff`` road-name entry of a names
    section built by ``fa_encode.names_section`` (it writes ``0x2000``)."""
    out = bytearray(sec)
    n = struct.unpack_from(">H", out, 2)[0]
    i = 24
    for _ in range(n):
        typ, _fl, _x, _y, ln = struct.unpack_from(">HHHHH", out, i)
        if typ != 0x00FF:
            raise CheckFailed("names entry at %d is not 0x00ff" % i)
        struct.pack_into(">H", out, i + 2, flags)
        i += 10 + ln + (ln & 1)
    return bytes(out)


# Road-number shields (M5.97): the firmware draws the `2=REF` part of a road
# name as a shield only on roads of class <= 4; `provisional-v0` gives
# primary/secondary class 5 (brown, no shield).  Class 4 keeps the brown
# style and draws the shields at the factory's places (A4, A40, A400, A401,
# A3201 on the London start screen).
DEFAULT_CLASS_OVERRIDE = "primary=4,primary_link=4,secondary=4,secondary_link=4"


def apply_class_override(table: dict, spec: str) -> dict:
    """``highway=cls,...`` -> a copy of ``table`` with those classes replaced."""
    out = dict(table)
    for item in filter(None, (spec or "").split(",")):
        hw, cls = item.split("=")
        if hw not in out:
            raise CheckFailed("class override for %s: not in the class table" % hw)
        out[hw] = (out[hw][0], int(cls))
    return out


def build_records(split: str, cell: str, class_table: str | None, country: int, write_names: bool,
                  limit: int = 0, names_out: dict | None = None, class_override: str = ""):
    table, _src = tilewriter.load_class_table(class_table)
    table = apply_class_override(table, class_override)
    ways, imf_stats = tilewriter.load_imf(split, cell)
    if write_names:
        from transliterate import apply, load_table
        present, mapping, _t = load_table()
        for way in ways:
            way["name"] = label_of(way.get("name", ""), way.get("ref", ""),
                                   lambda t: apply(t, present, mapping))
    runs = tilewriter.ways_to_runs(ways, 1, table, cell)
    built, sizes = {}, []
    trim = collections.Counter()
    for parcel in sorted(runs):
        res, dropped = fit_record(parcel, runs[parcel], table, country, write_names, limit)
        if dropped:
            trim["parcels"] += 1
            trim["runs"] += dropped
        if res is None:
            continue
        plain, comp, names_sec, _info = res
        built[parcel] = (plain, comp)
        if names_sec and names_out is not None:
            names_out[parcel] = set_name_flags(names_sec)
        sizes.append(len(plain))
    imf_stats = dict(imf_stats, trimmed=dict(trim))
    return built, sizes, imf_stats


def fit_record(parcel, runs, table, country, write_names, limit=0):
    """Build the record; drop the least important runs until it fits ``limit``.

    The class table's second value is the rank (1 motorway ... 9 service);
    runs are dropped from the highest rank, longest first being kept.
    Returns ``(result, dropped_runs)``.
    """
    rank = lambda r: table[tilewriter._run_fields(r)[1]][1]  # noqa: E731
    order = sorted(runs, key=lambda r: (rank(r), -len(tilewriter._run_fields(r)[0])))
    keep = len(order)
    res = tilewriter.build_road_record(1, parcel, order, table, country, write_names=write_names)
    while limit and res is not None and len(res[0]) > limit and keep > 1:
        keep = max(1, keep - max(1, keep // 10))
        res = tilewriter.build_road_record(1, parcel, order[:keep], table, country, write_names=write_names)
    if limit and res is not None and len(res[0]) > limit:
        raise CheckFailed("parcel %r: one run alone exceeds %d B" % (parcel, limit))
    return res, len(order) - keep


def from_zero(template: bytes, built: dict, pad: bool = True, odd: dict | None = None) -> tuple[bytes, dict]:
    m = tile_relayout.empty_model(tile_relayout.read_model(template))
    st = place(m, built, odd)
    out, wst = tile_relayout.write_model(m)
    if pad:
        out = tilewriter.pad_directory_reads(out)
    st.update(size=len(out), dirs=wst["dirs"])
    # read back: every placed record is a zlib stream that inflates to its body
    back = tile_relayout.read_model(out)
    got = 0
    for sec in back["sections"]:
        for L in sec["levels"]:
            for dm in L["dirs"]:
                for u in dm["units"]:
                    for raw in u["recs"]:
                        if raw:
                            zlib.decompress(raw)
                            got += 1
    if got != st.get("records", 0):
        raise CheckFailed("read back %d records, placed %d" % (got, st.get("records", 0)))
    return out, st


def selftest() -> int:
    fails = 0

    def ok(cond, msg):
        nonlocal fails
        print(("ok   " if cond else "FAIL ") + msg)
        fails += 0 if cond else 1

    # A one-directory section-1 level-1 template from s1_wide_dir's synthetic
    # directory, wrapped in a minimal tile.
    import s1_wide_dir
    TABLE1_OFF, SECT_OFF = tile_relayout.TABLE1_OFF, tile_relayout.SECT_OFF
    enc, pad = tile_relayout.enc_addr, tile_relayout.pad256
    hdr = bytearray(TABLE1_OFF)
    lo = tile_relayout.clarion_tile.LEVEL_OFF
    struct.pack_into(">H", hdr, lo, 1)
    hdr[lo + 2:lo + 4] = bytes([1, 1])
    hdr[lo + 4:lo + 8] = bytes([1, 0x92]) + struct.pack(">H", 1)
    struct.pack_into(">IH", hdr, SECT_OFF + 6, 0xFFFFFFFF, 0)
    y0, x0 = 77, 923
    d = bytearray(struct.pack(">6H", 0x2046, 0, 32, y0, tilewriter.x_field(x0), 0))
    for _ in range(32):
        d += struct.pack(">I", 0xFFFFFFFF) + struct.pack(">I", EMPTY1) * 128
    table_at, dir_at = TABLE1_OFF, TABLE1_OFF + 256
    out = bytearray(pad(dir_at + len(d)))
    out[:TABLE1_OFF] = hdr
    struct.pack_into(">IH", out, SECT_OFF, enc(table_at), 1)
    a = enc(dir_at)
    out[table_at:table_at + 20] = struct.pack(">10H", 10, 2, 8, 1, 100, 0, 0, 100, a >> 16, a & 0xFFFF)
    out[dir_at:dir_at + len(d)] = d
    tmpl = bytes(out)
    ok(s1_wide_dir.census(tmpl)["counts"]["dirs"] == 1, "template: one level-1 directory")
    table = tilewriter.default_class_table()
    lon0, lat0 = -0.15625, 51.5
    runs = [([(lon0 + 0.001, lat0 + 0.001), (lon0 + 0.02, lat0 + 0.015), (lon0 + 0.03, lat0 + 0.002)],
             "residential", "")]
    parcel = tilewriter.parcel_of(lon0 + 0.001, lat0 + 0.001, 1)
    plain, comp, _n, _i = tilewriter.build_road_record(1, parcel, runs, table, 826, write_names=False)
    blob, st = from_zero(tmpl, {parcel: (plain, comp)}, pad=False)
    ok(st["records"] == 1 and st["rows"] == 1, "one record placed in one row")
    c = s1_wide_dir.census(blob)
    ok(s1_wide_dir.census_ok(c) and c["counts"]["records"] == 1, "s1_wide_dir census accepts the tile, 1 record")
    m = tile_relayout.read_model(blob)
    rec = [r for sec in m["sections"] for L in sec["levels"] for dm in L["dirs"] for u in dm["units"] for r in u["recs"]]
    ok(zlib.decompress(rec[0]) == plain, "the record inflates to the built body")
    _code, _g, shapes = fa_encode.parse_record(zlib.decompress(rec[0]), 1)
    ok(shapes and all(s["ok"] for s in shapes), "fa_encode re-reads the shapes")
    try:
        from_zero(tmpl, {(y0 + 1, x0, 0, 0): (plain, comp)}, pad=False)
        ok(False, "a parcel outside the template is refused (negative control)")
    except CheckFailed:
        ok(True, "a parcel outside the template is refused (negative control)")
    # a long run is split into shapes of <= 255 points (M5.88)
    long_run = [([(lon0 + 0.0001 * i, lat0 + 0.0005 + 0.00001 * (i % 7)) for i in range(300)], "residential", "")]
    p2 = tilewriter.parcel_of(lon0 + 0.0001, lat0 + 0.0005, 1)
    pl2, _c2, _n2, _i2 = tilewriter.build_road_record(1, p2, long_run, table, 826, write_names=False)
    _code, _g, sh2 = fa_encode.parse_record(pl2, 1)
    ok(len(sh2) >= 2 and all(s["ok"] for s in sh2), "a 300-point run becomes >= 2 readable shapes (%d)" % len(sh2))
    # empty level-1 odd pairs are 0xffffffff (0x7fffffff moved the read 4 GiB, M5.88)
    cols = [col for _l, D in s1_wide_dir.section1_dirs(blob)
            for r in s1_wide_dir.parse_dir(blob, D["off"], 1, check=False)["rows"] for col in r["cols"]]
    ok(all(c["odd"][0] == EMPTY_ODD for c in cols) and sum(c["even"][0] != EMPTY1 for c in cols) == 1,
       "empty odd pairs 0xffffffff, one even record")
    # --max-plain drops the least important runs first
    two = runs + [([(lon0 + 0.002, lat0 + 0.003), (lon0 + 0.025, lat0 + 0.01)], "motorway", "")]
    full, _ = fit_record(parcel, two, table, 826, False)
    small, dropped = fit_record(parcel, two, table, 826, False, limit=len(full[0]) - 1)
    ok(dropped == 1 and len(small[0]) < len(full[0]), "a cap drops one run (the residential one)")
    # a background record next to the road record (Z4)
    lon_p, lat_p, pw, ph = __import__("clarion_bg").parcel_geo(1, *parcel)
    import tempfile, os
    sq = [[lon_p + pw * a, lat_p + ph * b] for a, b in ((0.1, 0.1), (0.6, 0.1), (0.6, 0.6), (0.1, 0.6), (0.1, 0.1))]
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
        fh.write(json.dumps(dict(id="w1", kind="park", rings=[sq], holes=[])) + "\n")
        fh.write(json.dumps(dict(id="w2", kind="water", rings=[[[x - pw * 0.05, y] for x, y in sq]], holes=[])) + "\n")
    bg, bst = build_background(fh.name, 826)
    os.unlink(fh.name)
    ok(list(bg) == [parcel] and bst["shapes_park"] == 1 and bst["shapes_water"] == 1,
       "park + water square -> one background record in the road parcel")
    blob2, st2 = from_zero(tmpl, {parcel: (plain, comp)}, pad=False,
                           odd={parcel: (bg[parcel], tilewriter.compress(bg[parcel]))})
    ok(st2["even_records"] == 1 and st2["odd_records"] == 1, "even + odd placed")
    c2 = s1_wide_dir.census(blob2)
    ok(s1_wide_dir.census_ok(c2) and c2["counts"]["records"] == 2, "census: 2 records")
    m2 = tile_relayout.read_model(blob2)
    raws = [r for sec in m2["sections"] for L in sec["levels"] for dm in L["dirs"] for u in dm["units"] for r in u["recs"]]
    ok([zlib.decompress(r) for r in raws] == [plain, bg[parcel]], "block order: even then odd")
    # place labels after road names: road offsets unchanged, entries walk (M5.90)
    road_sec, offs = fa_encode.names_section(["1=KING STREET;2=A4"], [[0] * 9])
    both = names_with_places(road_sec, [(100, 200, "SOHO"), (300, 400, "MAYFAIR")])
    ok(struct.unpack_from(">H", both, 2)[0] == 3 and _entries_end(both) <= 4 * struct.unpack_from(">H", both, 8)[0]
       and both[2 * offs["1=KING STREET;2=A4"]:][:2] == b"\x00\xff"
       and both[4 * struct.unpack_from(">H", both, 8)[0]:] == road_sec[4 * struct.unpack_from(">H", road_sec, 8)[0]:],
       "places appended: 3 entries, road offset kept, sub-table moved intact")
    ok(label_of("1=King Street", "A4;A400") == "1=KING STREET;2=A4" and label_of("", "A4") == "2=A4",
       "label: upper case, first ref")
    t2 = apply_class_override({"primary": (6, 5), "residential": (5, 8)}, "primary=4")
    ok(t2 == {"primary": (6, 4), "residential": (5, 8)}, "class override keeps the layer, replaces the class")
    try:
        apply_class_override({"primary": (6, 5)}, "motorway=1")
        ok(False, "override of an unknown highway is refused")
    except CheckFailed:
        ok(True, "override of an unknown highway is refused")
    print("tile_from_zero selftest: %s (%d failure(s))" % ("OK" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("split", nargs="?")
    ap.add_argument("--template")
    ap.add_argument("--cell")
    ap.add_argument("--class-table")
    ap.add_argument("--country", type=int, default=616)
    ap.add_argument("--no-names", action="store_true")
    ap.add_argument("--areas", help="osm_areas.py JSONL: write level-1 background records (Z4)")
    ap.add_argument("--urban-fill", type=float, default=0.0,
                    help="fill a parcel with one urban ring when its urban rings cover >= this share (0 = off)")
    ap.add_argument("--class-override", default=DEFAULT_CLASS_OVERRIDE,
                    help="highway=cls,... replacing classes of the table (default: %(default)s; '' = none)")
    ap.add_argument("--places", action="store_true", help="write place=* labels from --areas (M5.90)")
    ap.add_argument("--areas-kinds", help="comma list of kinds to write (default: all of BG_TYPES)")
    ap.add_argument("--max-plain", type=lambda v: int(v, 0), default=0,
                    help="drop the least important roads of a parcel until its record fits (0 = no limit)")
    ap.add_argument("-o", "--out")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not (args.split and args.template and args.cell and args.out):
        ap.print_usage(sys.stderr)
        return 2
    try:
        names = {}
        built, sizes, imf_stats = build_records(args.split, args.cell, args.class_table, args.country,
                                                not args.no_names, args.max_plain, names_out=names,
                                                class_override=args.class_override)
        odd, bg_stats = {}, {}
        if args.areas or names:
            only = set(args.areas_kinds.split(",")) if args.areas_kinds else None
            plains, bg_stats = build_background(args.areas, args.country, only, args.urban_fill, names, args.places)
            odd = {k: (v, tilewriter.compress(v)) for k, v in plains.items()}
        out, st = from_zero(Path(args.template).read_bytes(), built, odd=odd)
        st["background"] = bg_stats
    except (CheckFailed, tilewriter.CheckFailed, tilewriter.WriterError) as exc:
        print("tile_from_zero: FAIL %s" % exc)
        return 1
    Path(args.out).write_bytes(out)
    sizes.sort()
    q = lambda f: sizes[min(len(sizes) - 1, int(f * len(sizes)))] if sizes else 0  # noqa: E731
    st.update(parcels=len(built), plain_min=sizes[0] if sizes else 0, plain_median=q(0.5),
              plain_p99=q(0.99), plain_max=sizes[-1] if sizes else 0,
              sha256=hashlib.sha256(out).hexdigest(), imf=imf_stats)
    if args.json:
        print(json.dumps(st, indent=1, default=str))
    else:
        print("from-zero: parcels=%d records=%d rows=%d size=%d B sha256 %s"
              % (st["parcels"], st["records"], st["rows"], st["size"], st["sha256"]))
        print("record plain bytes: min %d median %d p99 %d max %d"
              % (st["plain_min"], st["plain_median"], st["plain_p99"], st["plain_max"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
