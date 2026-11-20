#!/usr/bin/env python3
"""Resolve ``RDSTM001.DAT`` link references to MAPAL section-2 links (M4.16e).

``tools/tmc_fielddir.py`` (M4.16b) joins a TMC location code to the
``RDSTM001.DAT`` location -> link records; each record carries ``u32`` link
references ``ref``.  This tool decodes what a ``ref`` points at
(EXP-2026-11-20-M4.16e-rdstm-link-groups):

* **File header** (``0x1000``, ``u16`` big-endian): ``u16 header_words``,
  ``u16 h1``, ``u16 h2`` (roles UNKNOWN), then two *sets*, each
  ``u32 group_index_addr, u16 group_index_blocks, u16 ntables`` followed by
  ``ntables`` rows ``u16 table_code, u16 nlink, nlink x (u32 addr, u16
  blocks), u32 triple_addr, u16 triple_blocks``.  An *addr* is the MAPAL tile
  container address: ``(v >> 8) * 0x800 + (v & 0xff) * 0x100``; *blocks* are
  0x100 bytes.
* **Group index** (one per set, at ``group_index_addr``): ``u16 ngroups``,
  then per group (4-byte aligned) ``u16 size_dwords, u32 data_addr, u16
  data_blocks, u32 key_min, u32 key_max, u16 n, n x (u32 parcel_key, u16
  count)``.  ``parcel_key`` is a MAPAL parcel code ``(w0 << 16) | w1`` (low
  nibble of ``w1`` = level: 4 in set 0, 2 in set 1).
* **Group data** at ``data_addr``: ``sum(count)`` 4-byte entries ``(u16 a,
  u16 b)``; the first ``count[0]`` belong to ``parcel_key[0]`` and so on.
* **Reference** ``ref`` of a location record in pair ``p`` (pairs 0..13 use
  set 0, 14..27 set 1): ``group = ref >> 16``, ``entry = ref & 0xffff``.
* **Entry**: ``a & 0x1fff`` = node index and ``b & 0x1fff`` = link id in the
  parcel's section-2 record of that level (node ``a`` is an end of link
  ``b``); ``b & 0x2000`` = the end flag of that link end at node ``a``.  The
  other bits (``a``: 0x4000/0x8000, ``b``: 0x4000/0x8000) are UNKNOWN.

Commands::

    rdstm_links.py header RDSTM001.DAT
    rdstm_links.py groups RDSTM001.DAT
    rdstm_links.py check RDSTM001.DAT MAPAL001 [--set 0|1] [--tiles A.DAT,B.DAT]
    rdstm_links.py place LCTBL001.DAT RDSTM001.DAT MAPAL001 [--table 0]
                         [--examples 25] [--seed 1]
    rdstm_links.py --selftest

``check`` tests the node/link rule on every entry whose parcel record is in
the given tiles, with a random-node and a shifted-entry control.  ``place``
maps the TMC records of one location table through their set-1 references to
level-2 node coordinates and tests them against the record country and the
TMC neighbour (positive offset) distance, with shuffled-key controls.

Stdlib only.  Reads vendor files; writes nothing.
"""

from __future__ import annotations

import argparse
import collections
import math
import random
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "ze0-viewer" / "tools_ze0"))

HEADER_AT = 0x1000
ID_MASK = 0x1FFF
END_FLAG = 0x2000
UNITS = 2048
# parcel size in degrees (lat, lon) by level: level 2 = 1/12 x 1/8, level 4 = 4/3 x 2
PARCEL_DEG = {2: (1.0 / 12.0, 1.0 / 8.0), 4: (4.0 / 3.0, 2.0)}


def addr(v: int) -> int:
    """MAPAL/RDSTM container address: 0x800 sectors + 0x100 sub-blocks."""
    return (v >> 8) * 0x800 + (v & 0xFF) * 0x100


# --------------------------------------------------------------------------
# file structure

def parse_header(d: bytes, at: int = HEADER_AT) -> dict:
    words, h1, h2 = struct.unpack_from(">HHH", d, at)
    p = at + 6
    sets = []
    for _ in range(2):
        gaddr, gblocks, ntab = struct.unpack_from(">IHH", d, p)
        p += 8
        tables = []
        for _ in range(ntab):
            code, nlink = struct.unpack_from(">HH", d, p)
            p += 4
            links = []
            for _ in range(nlink):
                a, b = struct.unpack_from(">IH", d, p)
                links.append((addr(a), b))
                p += 6
            ta, tb = struct.unpack_from(">IH", d, p)
            p += 6
            tables.append({"code": code, "links": links, "triples": (addr(ta), tb)})
        sets.append({"index_at": addr(gaddr), "index_blocks": gblocks, "tables": tables})
    return {"words": words, "h1": h1, "h2": h2, "sets": sets, "end": p}


def parse_groups(d: bytes, at: int) -> list[dict]:
    n = struct.unpack_from(">H", d, at)[0]
    p = at + 2
    out = []
    for _ in range(n):
        size, da, db, kmin, kmax, ne = struct.unpack_from(">HIHIIH", d, p)
        ents = [struct.unpack_from(">IH", d, p + 18 + 6 * j) for j in range(ne)]
        out.append({"at": p, "size": size, "data_at": addr(da), "data_blocks": db,
                    "kmin": kmin, "kmax": kmax, "parcels": ents})
        p += 4 * size
    return out


def group_entries(d: bytes, g: dict) -> list[tuple[int, int, int]]:
    """[(parcel_key, a, b)] in entry order."""
    out = []
    e = 0
    for key, cnt in g["parcels"]:
        for _ in range(cnt):
            a, b = struct.unpack_from(">HH", d, g["data_at"] + 4 * e)
            out.append((key, a, b))
            e += 1
    return out


def in_box(key: int, kmin: int, kmax: int) -> bool:
    """Both parcel words inside [min, max) of the group box."""
    return all((lo >> sh) & 0xFFFF <= (key >> sh) & 0xFFFF < (hi >> sh) & 0xFFFF
               for sh, lo, hi in ((16, kmin, kmax), (0, kmin, kmax)))


def key_level(key: int) -> int:
    return key & 0xF


def parcel_origin(key: int) -> tuple[float, float]:
    """(lat, lon) of the south-west corner of a level-2 or level-4 parcel."""
    w0, w1 = key >> 16, key & 0xFFFF
    lv = key_level(key)
    chi = ((w0 >> 15) << 8) | (w1 >> 8)
    if lv == 2:
        row = ((w0 >> 8) & 0x7F) << 4 | (w0 >> 4) & 0xF
        col = chi << 4 | (w1 >> 4) & 0xF
        return row / 12.0, col / 8.0 - 924
    if lv == 4:
        row = ((w0 >> 8) & 0x7F) << 2 | ((w0 >> 7) & 1) << 1 | (w0 >> 4) & 1
        col = chi << 2 | ((w1 >> 7) & 1) << 1 | (w1 >> 4) & 1
        return row / 3.0, col / 2.0 - 924
    raise ValueError("level %d" % lv)


def node_latlon(key: int, x: int, y: int) -> tuple[float, float]:
    lat0, lon0 = parcel_origin(key)
    h, w = PARCEL_DEG[key_level(key)]
    return lat0 + y / UNITS * h, lon0 + x / UNITS * w


def tile_of(lat: float, lon: float) -> str:
    """Grid tile name ``BxxRyyyR.DAT`` holding (lat, lon) (8 x 1-mesh rows, 8 deg columns)."""
    b = int(math.floor(lat * 1.5 / 8)) * 8
    lon_max = 12 + 8 * int(math.floor((lon - 4) / 8))
    return "B%02XR%03XR.DAT" % (b, int(108 - lon_max))


# --------------------------------------------------------------------------
# section-2 records

def load_sec2(paths, level: int, keys: set | None = None) -> dict:
    """{parcel_key: {"nodes": [(x, y)], "ends": {link_id: {node: id_word}}, "countries": [...]}}."""
    import clarion_rd  # noqa: E402
    import rd_check  # noqa: E402
    from tile_scan import TileScan  # noqa: E402

    out = {}
    for path in paths:
        with TileScan(str(path)) as t:
            for r in t.records(section=2, level=level):
                if level in (2, 4, 5) and r.k % 2:
                    continue
                plain = r.plain()
                key = struct.unpack_from(">I", plain, 0)[0]
                if keys is not None and key not in keys:
                    continue
                rec = clarion_rd.parse_record(rd_check.part_a(plain, level))
                if "nnodes" not in rec:
                    continue
                out[key] = record_view(rec, path)
    return out


def record_view(rec: dict, path=None) -> dict:
    ends: dict = collections.defaultdict(dict)
    for i, nd in enumerate(rec["nodes"]):
        for e in nd["entries"]:
            if e["cls"] & 0x8000:
                continue
            ends[e["id"] & ID_MASK][i] = e["id"]
    return {"nodes": [(nd["x"], nd["y"]) for nd in rec["nodes"]], "ends": dict(ends),
            "countries": list(rec.get("countries", [])), "tile": Path(path).name if path else None}


def resolve(rec: dict, a: int, b: int):
    """(node, link, id_word) if node ``a`` is an end of link ``b`` in ``rec``, else None."""
    node, link = a & ID_MASK, b & ID_MASK
    w = rec["ends"].get(link, {}).get(node)
    if w is None:
        return None
    return node, link, w


# --------------------------------------------------------------------------
# commands

def cmd_header(a) -> int:
    d = Path(a.rdstm).read_bytes()
    h = parse_header(d)
    print(f"header words 0x{h['words']:x} h1 {h['h1']} h2 {h['h2']} parsed to 0x{h['end']:x}")
    for si, s in enumerate(h["sets"]):
        print(f"set {si}: group index @0x{s['index_at']:x} blocks {s['index_blocks']} tables {len(s['tables'])}")
        for t in s["tables"]:
            ls = " ".join(f"0x{x:x}+{b:#x}" for x, b in t["links"])
            print(f"  table {t['code']:04x}: links {ls}; triples 0x{t['triples'][0]:x}+{t['triples'][1]:#x}")
    try:
        import tmc_fielddir
        pairs = tmc_fielddir.rdstm_pairs(d)
        flat = [(t["links"][0][0], t["triples"][0]) for s in h["sets"] for t in s["tables"]]
        got = [(p["links_at"], p["triples_at"]) for p in pairs]
        print(f"pairs walked (tmc_fielddir) {len(got)}; header rows {len(flat)}; equal {flat == got}")
    except ImportError:
        pass
    return 0


def ref_census(d: bytes, h: dict):
    import tmc_fielddir
    pairs = tmc_fielddir.rdstm_pairs(d)
    per_set = [collections.defaultdict(set), collections.defaultdict(set)]
    nref = [0, 0]
    ntab0 = len(h["sets"][0]["tables"])
    for pi, p in enumerate(pairs):
        si = 0 if pi < ntab0 else 1
        for groups in p["links"].values():
            for _role, refs in groups:
                for r in refs:
                    per_set[si][r >> 16].add(r & 0xFFFF)
                    nref[si] += 1
    return pairs, per_set, nref


def cmd_groups(a) -> int:
    d = Path(a.rdstm).read_bytes()
    h = parse_header(d)
    _pairs, per_set, nref = ref_census(d, h)
    for si, s in enumerate(h["sets"]):
        gs = parse_groups(d, s["index_at"])
        ents = sum(c for g in gs for _, c in g["parcels"])
        fits = sum(4 * sum(c for _, c in g["parcels"]) <= 0x100 * g["data_blocks"] for g in gs)
        chain = sum(gs[i]["data_at"] + 0x100 * gs[i]["data_blocks"] == gs[i + 1]["data_at"] for i in range(len(gs) - 1))
        levels = collections.Counter(key_level(k) for g in gs for k, _ in g["parcels"])
        inside = sum(in_box(k, g["kmin"], g["kmax"]) for g in gs for k, _ in g["parcels"])
        refs = per_set[si]
        covered = sum(len(refs.get(gi, ())) == sum(c for _, c in g["parcels"]) for gi, g in enumerate(gs))
        beyond = sum(max(refs.get(gi, {-1})) >= sum(c for _, c in g["parcels"]) for gi, g in enumerate(gs))
        end = gs[-1]["data_at"] + 0x100 * gs[-1]["data_blocks"]
        print(f"set {si}: groups {len(gs)} parcels {sum(len(g['parcels']) for g in gs)} entries {ents} "
              f"data 0x{gs[0]['data_at']:x}..0x{end:x}; data fits blocks {fits}/{len(gs)}; "
              f"contiguous {chain}/{len(gs) - 1}; key levels {dict(levels)}; keys in group box {inside}")
        print(f"       refs {nref[si]} -> groups {len(refs)} (max {max(refs)}); "
              f"groups whose entries are all referenced {covered}/{len(gs)}; refs past the group end {beyond}")
    print(f"file size 0x{len(d):x}")
    return 0


def tile_paths(mapal: Path, names: str | None, level: int):
    if names:
        return [mapal / n for n in names.split(",")]
    if level >= 3:
        return [mapal / "LEV3456R.DAT"]
    return sorted(p for p in mapal.glob("B*R*R.DAT"))


def cmd_check(a) -> int:
    d = Path(a.rdstm).read_bytes()
    h = parse_header(d)
    rng = random.Random(a.seed)
    sets = [a.set] if a.set is not None else [0, 1]
    for si in sets:
        gs = parse_groups(d, h["sets"][si]["index_at"])
        level = key_level(gs[0]["parcels"][0][0])
        paths = tile_paths(Path(a.mapal), a.tiles, level)
        keys = {k for g in gs for k, _ in g["parcels"]}
        recs = load_sec2(paths, level, keys)
        st = collections.Counter()
        miss_flags = collections.Counter()
        flag_ok = collections.Counter()
        for g in gs:
            ents = group_entries(d, g)
            for i, (key, ea, eb) in enumerate(ents):
                rec = recs.get(key)
                if rec is None:
                    st["no_record"] += 1
                    continue
                st["tested"] += 1
                hit = resolve(rec, ea, eb)
                if hit:
                    st["hit"] += 1
                    flag_ok[(eb & END_FLAG) == (hit[2] & END_FLAG)] += 1
                else:
                    miss_flags[(ea >> 13, eb >> 13)] += 1
                nn = len(rec["nodes"])
                st["ctl_random_node"] += resolve(rec, rng.randrange(max(nn, 1)), eb) is not None
                nk, na, _ = ents[(i + 1) % len(ents)]
                st["ctl_shift_node"] += nk == key and na != ea and resolve(rec, na, eb) is not None
        print(f"set {si} level {level}: tiles {len(paths)} parcel records {len(recs)}/{len(keys)}; "
              f"entries tested {st['tested']} (no record {st['no_record']}): node is an end of link "
              f"{st['hit']}; random-node control {st['ctl_random_node']}; (observation: next entry's node also an end "
              f"of this link {st['ctl_shift_node']}); "
              f"end flag b&0x2000 = id word&0x2000 {flag_ok[True]}/{sum(flag_ok.values())}")
        if miss_flags:
            print("   misses by (a>>13, b>>13): " + ", ".join(f"{k}:{v}" for k, v in miss_flags.most_common(8)))
        # wrong-parcel control: entries resolved against another parcel's record
        wrong = tested = 0
        klist = sorted(recs)
        for g in gs[:: max(1, len(gs) // 200)]:
            for key, ea, eb in group_entries(d, g)[:50]:
                if key not in recs:
                    continue
                other = recs[klist[(klist.index(key) + len(klist) // 2) % len(klist)]]
                tested += 1
                wrong += resolve(other, ea, eb) is not None
        print(f"   wrong-parcel control: {wrong}/{tested}")
    return 0


def haversine(p, q) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (p[0], p[1], q[0], q[1]))
    x = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(min(1.0, x)))


def median(v):
    v = sorted(v)
    return v[len(v) // 2] if v else float("nan")


def cmd_place(a) -> int:
    import tmc_fielddir as tf

    ldata = Path(a.lctbl).read_bytes()
    d = Path(a.rdstm).read_bytes()
    h = parse_header(d)
    recs = tf.load_records(ldata)
    tables = tf.parse_index(ldata)
    slices = tf.table_slices(tables)
    pairs = tf.rdstm_pairs(d)
    nps = tf.neg_pos(recs)
    ntab0 = len(h["sets"][0]["tables"])
    pi = ntab0 + a.table_pair
    pr = pairs[pi]
    # find the location table this pair belongs to (best neg/pos agreement, as tmc_fielddir join)
    best = max(range(len(tables)), key=lambda ti: tf.join_table(nps, tables[ti], pr, slices[ti][0], 0)[0])
    s0, s1 = slices[best]
    gs = parse_groups(d, h["sets"][1]["index_at"])
    gents = {}

    def entry(ref):
        g = ref >> 16
        if g not in gents:
            gents[g] = group_entries(d, gs[g])
        return gents[g][ref & 0xFFFF]

    # records joined by code (neg/pos must agree, as the M4.16b join)
    joined = []
    for k in range(s1 - s0):
        code = tables[best].get(k)
        if code is None or code not in pr["links"]:
            continue
        if pr["triples"].get(code) != nps[s0 + k]:
            continue
        joined.append((k, code))
    keys = set()
    for _k, code in joined:
        for _role, refs in pr["links"][code]:
            for r in refs:
                keys.add(entry(r)[0])
    tiles = sorted({tile_of(*parcel_origin(k)) for k in keys})
    paths = [Path(a.mapal) / t for t in tiles if (Path(a.mapal) / t).exists()]
    sec = load_sec2(paths, 2, keys)
    print(f"pair {pi} (set 1, table {a.table_pair}) -> location table {best} records {s1 - s0}; "
          f"joined by code {len(joined)}; parcels {len(keys)} in tiles {','.join(tiles)} (records found {len(sec)})")

    def place(code, refs_of=None):
        pts = []
        for _role, refs in (refs_of or pr["links"])[code]:
            for r in refs:
                key, ea, eb = entry(r)
                rec = sec.get(key)
                if rec is None:
                    continue
                hit = resolve(rec, ea, eb)
                if hit is None:
                    continue
                x, y = rec["nodes"][hit[0]]
                pts.append((key, hit, node_latlon(key, x, y), rec))
        return pts

    loc = {}
    st = collections.Counter()
    ctry = collections.Counter()
    for k, code in joined:
        pts = place(code)
        st["records"] += 1
        st["refs"] += sum(len(r) for _x, r in pr["links"][code])
        st["resolved"] += len(pts)
        if pts:
            st["placed"] += 1
            loc[code] = pts
            for p in pts:
                for c in p[3]["countries"]:
                    ctry[c] += 1
    main_c = ctry.most_common(1)[0][0] if ctry else None
    print(f"records {st['records']} refs {st['refs']} resolved to a node/link {st['resolved']}; "
          f"records placed {st['placed']}; parcel countries {ctry.most_common(5)}")
    # control 1: country of the record's parcels, real vs random refs of the same set
    rng = random.Random(a.seed)
    allrefs = [(g << 16) | e for g in range(len(gs)) for e in range(sum(c for _, c in gs[g]["parcels"]))]
    real_c = sum(any(main_c in p[3]["countries"] for p in pts) for pts in loc.values())
    rnd_c = rnd_n = 0
    rsec_keys = set()
    sample = [rng.choice(allrefs) for _ in range(min(2000, len(loc)))]
    for r in sample:
        rsec_keys.add(entry(r)[0])
    rtiles = sorted({tile_of(*parcel_origin(k)) for k in rsec_keys})
    rsec = load_sec2([Path(a.mapal) / t for t in rtiles if (Path(a.mapal) / t).exists()], 2, rsec_keys)
    for r in sample:
        key, ea, eb = entry(r)
        rec = rsec.get(key)
        if rec is None or resolve(rec, ea, eb) is None:
            continue
        rnd_n += 1
        rnd_c += main_c in rec["countries"]
    print(f"country {main_c}: records with a node in a {main_c} parcel {real_c}/{len(loc)}; "
          f"random refs {rnd_c}/{rnd_n}")
    # control 2: distance to the TMC positive neighbour vs a shuffled neighbour
    first = {c: pts[0][2] for c, pts in loc.items()}
    dists, ctl = [], []
    codes = list(first)
    for c in codes:
        pos = pr["triples"][c][1]
        if pos in first and pos != c:
            dists.append(min(haversine(p[2], q[2]) for p in loc[c] for q in loc[pos]))
            o = codes[rng.randrange(len(codes))]
            ctl.append(min(haversine(p[2], q[2]) for p in loc[c] for q in loc[o]))
    within = sum(x < 1.0 for x in dists)
    within_c = sum(x < 1.0 for x in ctl)
    print(f"positive neighbour: pairs {len(dists)}, min node distance median {median(dists):.2f} km, "
          f"< 1 km {within}; shuffled neighbour median {median(ctl):.2f} km, < 1 km {within_c}")
    print(f"examples (code, type, road, name -> tile parcel node link lat lon):")
    shown = 0
    for k, code in joined:
        if code not in loc:
            continue
        f = tf.decode_record(recs[s0 + k])["fields"]
        key, (node, link, idw), (lat, lon), rec = loc[code][0]
        print(f"  {code:5d} type {tf.u16(f[0])} road {tf.text(f[1])!r} name {tf.text(f[3])!r} -> {rec['tile']} "
              f"parcel {key:08x} node {node} link {link}{'e' if idw & END_FLAG else ''} "
              f"{lat:.5f} {lon:.5f} ({len(loc[code])} nodes)")
        shown += 1
        if shown >= a.examples:
            break
    return 0


# --------------------------------------------------------------------------
# self-test (synthetic)

def _selftest() -> int:
    fails = 0

    def check(name, cond):
        nonlocal fails
        print(("ok   " if cond else "FAIL ") + name)
        fails += not cond

    check("addr", addr(0x0019B501) == 0xCDA900 and addr(0x0002_03) == 0x1300)
    # level-2 parcel of the Canary group 0 and a level-4 parcel
    la, lo = parcel_origin(0x94DFC622)
    check("level-2 origin", abs(la - 333 / 12) < 1e-9 and abs(lo - (-16 + 2 / 8)) < 1e-9)
    la4, lo4 = parcel_origin(0x940FC404)
    check("level-4 origin", abs(la4 - 80 / 3) < 1e-9 and abs(lo4 + 20) < 1e-9)
    check("tile of Canary", tile_of(28.0, -15.5) == "B28R078R.DAT")
    check("tile of Prague", tile_of(50.08, 14.42) == "B48R058R.DAT")
    check("tile of Koeln", tile_of(50.94, 6.96) == "B48R060R.DAT")
    # synthetic file: header with one table per set, group index, group data
    d = bytearray(0x3000)
    hdr = struct.pack(">HHH", 0x180, 3, 0x7A)
    hdr += struct.pack(">IHH", 0x000200, 1, 1) + struct.pack(">HH", 0x3219, 1) + struct.pack(">IH", 0x000005, 1) + struct.pack(">IH", 0x000006, 1)
    hdr += struct.pack(">IHH", 0x000201, 1, 1) + struct.pack(">HH", 0x3219, 1) + struct.pack(">IH", 0x000007, 1) + struct.pack(">IH", 0x000008, 1)
    d[HEADER_AT:HEADER_AT + len(hdr)] = hdr
    h = parse_header(bytes(d))
    check("header sets", [s["index_at"] for s in h["sets"]] == [0x1000, 0x1100] and h["sets"][1]["tables"][0]["links"] == [(0x700, 1)])
    # group index at 0x1100: two groups
    gi = struct.pack(">H", 2)
    g0 = struct.pack(">HIHIIH", 0, 0x000202, 1, 0x94CFC602, 0x950FC642, 2) + struct.pack(">IHIH", 0x94DFC622, 2, 0x94DFC632, 1)
    g0 = struct.pack(">H", (len(g0) + 3) // 4) + g0[2:]
    g0 += b"\0" * (-len(g0) % 4)
    g1 = struct.pack(">HIHIIH", 0, 0x000203, 1, 0, 0, 1) + struct.pack(">IH", 0x94DFC622, 1)
    g1 = struct.pack(">H", (len(g1) + 3) // 4) + g1[2:]
    g1 += b"\0" * (-len(g1) % 4)
    blob = gi + g0 + g1
    d[0x1100:0x1100 + len(blob)] = blob
    d[0x1200:0x120C] = struct.pack(">HHHHHH", 0x0001, 0x4002, 0x4001, 0x6002, 0x0000, 0x0001)
    d[0x1300:0x1304] = struct.pack(">HH", 0x0002, 0x6003)
    gs = parse_groups(bytes(d), 0x1100)
    check("groups", len(gs) == 2 and gs[0]["data_at"] == 0x1200 and gs[1]["data_at"] == 0x1300)
    ents = group_entries(bytes(d), gs[0])
    check("entries by parcel", [e[0] for e in ents] == [0x94DFC622, 0x94DFC622, 0x94DFC632])
    rec = {"nodes": [(0, 0), (1024, 1024), (2047, 0)],
           "ends": {2: {1: 0x0002, 0: 0x2002}, 1: {0: 0x0001, 2: 0x2001}}, "countries": [724]}
    check("resolve hit", resolve(rec, ents[0][1], ents[0][2]) == (1, 2, 0x0002))
    check("resolve end flag", resolve(rec, 0x4000, 0x6002) == (0, 2, 0x2002))
    check("resolve miss", resolve(rec, 0x0001, 0x4001) is None)
    lat, lon = node_latlon(0x94DFC622, 1024, 1024)
    check("node lat/lon", abs(lat - (333 / 12 + 1 / 24)) < 1e-9 and abs(lon - (-15.75 + 1 / 16)) < 1e-9)
    print("selftest:", "FAIL" if fails else "PASS")
    return 1 if fails else 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("header")
    p.add_argument("rdstm")
    p = sub.add_parser("groups")
    p.add_argument("rdstm")
    p = sub.add_parser("check")
    p.add_argument("rdstm")
    p.add_argument("mapal")
    p.add_argument("--set", type=int, choices=(0, 1))
    p.add_argument("--tiles")
    p.add_argument("--seed", type=int, default=1)
    p = sub.add_parser("place")
    p.add_argument("lctbl")
    p.add_argument("rdstm")
    p.add_argument("mapal")
    p.add_argument("--table-pair", type=int, default=0, help="table row within set 1 (0..13)")
    p.add_argument("--examples", type=int, default=25)
    p.add_argument("--seed", type=int, default=1)
    return ap


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    if a.selftest:
        return _selftest()
    cmds = {"header": cmd_header, "groups": cmd_groups, "check": cmd_check, "place": cmd_place}
    if a.cmd not in cmds:
        build_parser().print_help()
        return 2
    return cmds[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
