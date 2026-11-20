#!/usr/bin/env python3
"""Probe candidate join keys between RDSTM001 16-byte rows and tile road records.

M4.16 asks for a row -> tile/mesh -> coordinate link. M4.15 showed the M4.1
16-byte row framing (ref/src/dst) is not a reciprocal graph and the record
framing drifts at 0x10a0 (C-1800-C-1802). M3.7 showed RDSTM001 is a TMC
location record table, not a routing graph (C-886-C-887). This tool tests
candidate join keys and reports match counts against random controls; it does
not claim a join exists.

Rows are read as M4.1 16-byte records: id,pad2,ref(u32),src(u16),dst(u16),
code(u16),tail(u16) (HYPOTHESIS field meanings, C-106). Tile identifiers come
from section 1 road-shape link ids and section 2 graph link/entry ids.

M4.16b adds ``probe-decoded``: the keys come from the C-884 field directory
(``tools/tmc_fielddir.py``): TMC location code (LCTBL index), the decoded u16
fields (area, linear, negative, positive, intersection) and the RDSTM001
link references of each location (``u32`` = group ``hi16`` + index
``lo16``).  Each key family is tested against the tile id sets with a random
control drawn from the same value space.

M4.16b (second pass, after M4.16e) adds ``place-all``: every TMC location
record of every set-1 table that joins ``RDSTM001.DAT`` by location code
(neg/pos agree) is carried through its link references to MAPAL section-2
nodes (``tools/rdstm_links.py`` rule) at level 2 (set 1) **and** level 4
(set 0, the same location tables linked to the coarse graph).  Per table it
reports the record country vs random references, the TMC positive neighbour
distance vs a shuffled neighbour, and the level-4 vs level-2 distance of the
same record vs a shuffled record (an independent cross-level control), plus
the share of records whose role-1 link list is the role-0 list reversed.

Usage:
  rdstm_place.py probe RDSTM001.DAT MAPAL001 [--limit-tiles N]
  rdstm_place.py probe-decoded LCTBL001.DAT RDSTM001.DAT MAPAL001 [--tiles B48R058R.DAT]
  rdstm_place.py place-all LCTBL001.DAT RDSTM001.DAT MAPAL001 [--tables 0,9] [--join negpos|code-only] [--seed 1]
  rdstm_place.py --selftest
"""
from __future__ import annotations

import argparse
import os
import random
import struct
import sys
import zlib
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
ZE0 = TOOLS_DIR / "ze0-viewer"
for p in (ZE0, ZE0 / "tools_ze0"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

ROW = 0x10
DEFAULT_START = 0x1000


def read_rows(path: str, start: int = DEFAULT_START, limit: int = 0) -> list[dict]:
    data = Path(path).read_bytes()
    rows = []
    for off in range(start, len(data) - ROW + 1, ROW):
        if limit and len(rows) >= limit:
            break
        chunk = data[off : off + ROW]
        if chunk == b"\x00" * ROW:
            continue
        id_, pad2, ref, src, dst, code, tail = struct.unpack("<HHIHHHH", chunk)
        rows.append(
            dict(offset=off, id=id_, pad2=pad2, ref=ref, src=src, dst=dst, code=code, tail=tail)
        )
    return rows


def tile_ids(mapal_dir: str, limit_tiles: int = 0, names: list[str] | None = None) -> dict[str, set[int]]:
    import clarion_tile, clarion_rd, ze0_roads

    sec1_lid: set[int] = set()
    sec2_id: set[int] = set()
    parcels: set[int] = set()
    parcel_w: set[int] = set()
    tiles = sorted(
        f for f in os.listdir(mapal_dir) if f.startswith("B") and f.endswith(".DAT")
    )
    if names:
        tiles = [t for t in tiles if t in names]
    if limit_tiles:
        tiles = tiles[:limit_tiles]
    for tf in tiles:
        data = open(os.path.join(mapal_dir, tf), "rb").read()
        try:
            t = clarion_tile.read_tile(data)
        except Exception:
            continue
        for sec in t["sections"]:
            for L in sec["levels"]:
                for D in L["dirs"]:
                    for slot in D["slots"].values():
                        for r in slot["recs"]:
                            try:
                                p = (
                                    zlib.decompress(r["raw"])
                                    if clarion_tile.is_zlib(r["raw"])
                                    else r["raw"]
                                )
                            except Exception:
                                p = r["raw"]
                            if sec["id"] == 1 and r["k"] % 2 == 0:
                                try:
                                    rec = ze0_roads.parse_record(p)
                                    for shapes in rec["layers"].values():
                                        for sh in shapes:
                                            for lk in sh["links"]:
                                                if lk["id"] is not None:
                                                    sec1_lid.add(lk["id"] & 0xFFFF)
                                except Exception:
                                    pass
                            elif sec["id"] == 2:
                                try:
                                    rd = clarion_rd.parse_record(p)
                                    if "error" in rd:
                                        continue
                                    parcels.add((rd["code"][0] << 16) | rd["code"][1])
                                    parcel_w.add(rd["code"][0])
                                    parcel_w.add(rd["code"][1])
                                    lks, _ = clarion_rd.links(rd)
                                    for lid, *_ in lks:
                                        sec2_id.add(lid & 0x1FFF)
                                    for nd in rd["nodes"]:
                                        for e in nd["entries"]:
                                            sec2_id.add(e["id"] & 0x1FFF)
                                except Exception:
                                    pass
    return {"sec1_lid": sec1_lid, "sec2_id": sec2_id, "parcels": parcels,
            "parcel_w": parcel_w, "tiles": len(tiles)}


def probe(rows: list[dict], ids: dict[str, set[int]], seed: int = 1) -> list[dict]:
    rng = random.Random(seed)
    candidates = {
        "src_vs_sec1_lid": ([r["src"] for r in rows], ids["sec1_lid"], 0x10000),
        "dst_vs_sec1_lid": ([r["dst"] for r in rows], ids["sec1_lid"], 0x10000),
        "src_vs_sec2_id": ([r["src"] & 0x1FFF for r in rows], ids["sec2_id"], 0x2000),
        "dst_vs_sec2_id": ([r["dst"] & 0x1FFF for r in rows], ids["sec2_id"], 0x2000),
        "code_vs_sec1_lid": ([r["code"] for r in rows], ids["sec1_lid"], 0x10000),
        "ref_vs_parcel": ([r["ref"] for r in rows], ids["parcels"], None),
    }
    out = []
    for name, (vals, target, space) in candidates.items():
        vset = set(vals)
        hit = len(vset & target)
        if space and target:
            # random control: sample |target| ids from the same value space
            ctrl = set(rng.sample(range(space), min(len(target), space)))
            ctrl_hit = len(vset & ctrl)
            expected = len(vset) * len(target) / space
        else:
            ctrl_hit = 0
            expected = 0.0
        out.append(
            dict(
                key=name,
                row_values=len(vset),
                target_ids=len(target),
                hits=hit,
                random_control=ctrl_hit,
                expected=round(expected, 1),
            )
        )
    return out


def probe_keys(cands: dict, seed: int = 1) -> list[dict]:
    """``cands``: name -> (values, target set, value space or None)."""
    rng = random.Random(seed)
    out = []
    for name, (vals, target, space) in cands.items():
        vset = set(vals)
        hit = len(vset & target)
        if space and target:
            ctrl = set(rng.sample(range(space), min(len(target), space)))
            ctrl_hit = len(vset & ctrl)
            expected = len(vset) * len(target) / space
        else:
            ctrl_hit = 0
            expected = 0.0
        out.append(dict(key=name, row_values=len(vset), target_ids=len(target), hits=hit,
                        random_control=ctrl_hit, expected=round(expected, 1)))
    return out


def decoded_keys(lctbl: str, rdstm: str) -> dict[str, list[int]]:
    """Key families from the decoded TMC records (M4.16b)."""
    import tmc_fielddir as tf

    ldata = Path(lctbl).read_bytes()
    recs = tf.load_records(ldata)
    tables = tf.parse_index(ldata)
    keys: dict[str, list[int]] = {k: [] for k in
                                  ("loc_code", "area", "linear", "negative", "positive", "intersection")}
    base = 0
    for t in tables:
        n = max(t) + 1
        for k in range(n):
            if k in t:
                keys["loc_code"].append(t[k])
            f = tf.decode_record(recs[base + k])["fields"]
            for name, idx in (("area", 5), ("linear", 6), ("negative", 7), ("positive", 8), ("intersection", 11)):
                v = tf.u16(f[idx])
                if v is not None:
                    keys[name].append(v)
        base += n
    refs: list[int] = []
    for pr in tf.rdstm_pairs(Path(rdstm).read_bytes()):
        for groups in pr["links"].values():
            for _, rl in groups:
                refs.extend(rl)
    keys["ref_hi16"] = [r >> 16 for r in refs]
    keys["ref_lo16"] = [r & 0xFFFF for r in refs]
    keys["ref_u32"] = refs
    return keys


def decoded_candidates(keys: dict[str, list[int]], ids: dict[str, set[int]]) -> dict:
    c = {}
    for name in ("loc_code", "area", "negative", "positive", "intersection", "ref_lo16"):
        c[f"{name}_vs_sec1_lid"] = (keys[name], ids["sec1_lid"], 0x10000)
        c[f"{name}_vs_sec2_id"] = ([v & 0x1FFF for v in keys[name]], ids["sec2_id"], 0x2000)
    c["ref_hi16_vs_parcel_word"] = (keys["ref_hi16"], ids["parcel_w"], 0x10000)
    c["loc_code_vs_parcel_word"] = (keys["loc_code"], ids["parcel_w"], 0x10000)
    c["ref_u32_vs_parcel"] = (keys["ref_u32"], ids["parcels"], None)
    return c


def print_table(res: list[dict]) -> None:
    print(f"{'key':<28} {'row_vals':>8} {'target':>8} {'hits':>6} {'random':>7} {'expect':>8}  verdict")
    for r in res:
        verdict = "NO JOIN" if r["hits"] <= max(r["random_control"] * 1.15, r["expected"] * 1.15 + 1) else "CHECK"
        print(f"{r['key']:<28} {r['row_values']:>8} {r['target_ids']:>8} {r['hits']:>6} "
              f"{r['random_control']:>7} {r['expected']:>8.1f}  {verdict}")


def cmd_probe_decoded(args: argparse.Namespace) -> int:
    keys = decoded_keys(args.lctbl, args.rdstm)
    ids = tile_ids(args.mapal, limit_tiles=args.limit_tiles, names=args.tiles)
    print(f"decoded keys: " + ", ".join(f"{k} {len(set(v))}" for k, v in keys.items()))
    print(f"tiles {ids['tiles']} sec1_lid {len(ids['sec1_lid'])} sec2_id {len(ids['sec2_id'])} "
          f"parcels {len(ids['parcels'])} parcel_words {len(ids['parcel_w'])}")
    print_table(probe_keys(decoded_candidates(keys, ids)))
    print("note: CHECK = above chance; it is a lead, not a join. A join also needs the per-record")
    print("      key to land on the matching tile id (one-to-one), not only set overlap.")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    rows = read_rows(args.rdstm, limit=args.limit_rows)
    ids = tile_ids(args.mapal, limit_tiles=args.limit_tiles)
    res = probe(rows, ids)
    print(f"rows {len(rows)} from {args.rdstm} start 0x{DEFAULT_START:x}")
    print(f"tiles {ids['tiles']} sec1_lid {len(ids['sec1_lid'])} sec2_id {len(ids['sec2_id'])} parcels {len(ids['parcels'])}")
    print(f"{'key':<20} {'row_vals':>8} {'target':>8} {'hits':>6} {'random':>7} {'expect':>8}  verdict")
    for r in res:
        verdict = "NO JOIN" if r["hits"] <= max(r["random_control"] * 1.15, r["expected"] * 1.15 + 1) else "CHECK"
        print(
            f"{r['key']:<20} {r['row_values']:>8} {r['target_ids']:>8} {r['hits']:>6} "
            f"{r['random_control']:>7} {r['expected']:>8.1f}  {verdict}"
        )
    print("note: NO JOIN means hits are at or below chance given the value space.")
    print("      M4.1 field meanings are HYPOTHESIS; M4.15 disproved 16-byte graph framing (C-1800).")
    return 0


# --------------------------------------------------------------------------
# place-all (M4.16b second pass): every set-1 table, level 2 and level 4


def majority(counter) -> int | None:
    return counter.most_common(1)[0][0] if counter else None


def min_dist(ps, qs) -> float:
    import rdstm_links as rl

    return min(rl.haversine(p, q) for p in ps for q in qs)


def role_links(groups, entry) -> dict[int, list[tuple[int, int]]]:
    """{role: [(parcel_key, link_id)]} of one location record."""
    out: dict[int, list[tuple[int, int]]] = {}
    for role, refs in groups:
        out.setdefault(role, []).extend((entry(r)[0], entry(r)[2] & 0x1FFF) for r in refs)
    return out


def reversed_pair(rl_: dict) -> bool | None:
    """True if the role-1 link list is the role-0 list reversed (None if one is missing)."""
    if 0 not in rl_ or 1 not in rl_:
        return None
    return rl_[1] == rl_[0][::-1]


def disagree_kind(tri: tuple, np_: tuple) -> str:
    """Why a code-matched record's LCTBL (neg, pos) differs from the RDSTM triple."""
    if None in np_:
        kind = "lctbl_field_absent"
    elif tri[0] == np_[0]:
        kind = "pos_differs"
    elif tri[1] == np_[1]:
        kind = "neg_differs"
    else:
        kind = "both_differ"
    return kind + ("_rdstm_has_0" if 0 in tri else "")


def cmd_place_all(args: argparse.Namespace) -> int:
    import collections

    import rdstm_links as rl
    import tmc_fielddir as tf

    ldata = Path(args.lctbl).read_bytes()
    d = Path(args.rdstm).read_bytes()
    h = rl.parse_header(d)
    recs = tf.load_records(ldata)
    tables = tf.parse_index(ldata)
    slices = tf.table_slices(tables)
    pairs = tf.rdstm_pairs(d)
    nps = tf.neg_pos(recs)
    ntab = len(h["sets"][0]["tables"])
    gsets = [rl.parse_groups(d, s["index_at"]) for s in h["sets"]]
    cache: dict = {}

    def entry(si, ref):
        g = ref >> 16
        if (si, g) not in cache:
            cache[(si, g)] = rl.group_entries(d, gsets[si][g])
        return cache[(si, g)][ref & 0xFFFF]

    rng = random.Random(args.seed)
    nent1 = [sum(c for _, c in g["parcels"]) for g in gsets[1]]
    rows = list(range(ntab)) if not args.tables else [int(x) for x in args.tables.split(",")]
    plan = []
    keys = {2: set(), 4: set()}
    why = collections.Counter()
    for t in rows:
        pr1, pr0 = pairs[ntab + t], pairs[t]
        best = max(range(len(tables)), key=lambda ti: tf.join_table(nps, tables[ti], pr1, slices[ti][0], 0)[0])
        s0, s1 = slices[best]
        with_link = joined = 0
        codes = []
        for k in range(s1 - s0):
            code = tables[best].get(k)
            if code is None or code not in pr1["links"]:
                continue
            with_link += 1
            agree = pr1["triples"].get(code) == nps[s0 + k]
            if not agree:
                why[disagree_kind(pr1["triples"][code], nps[s0 + k])] += 1
            if agree != (args.join == "negpos"):
                continue
            joined += 1
            codes.append(code)
            for _r, refs in pr1["links"][code]:
                keys[2].update(entry(1, r)[0] for r in refs)
            for _r, refs in pr0["links"].get(code, ()):
                keys[4].update(entry(0, r)[0] for r in refs)
        rnd = []
        for _ in range(min(2000, len(codes))):
            g = rng.randrange(len(nent1))
            while not nent1[g]:
                g = rng.randrange(len(nent1))
            r = (g << 16) | rng.randrange(nent1[g])
            rnd.append(r)
            keys[2].add(entry(1, r)[0])
        plan.append(dict(t=t, loc_table=best, n=s1 - s0, with_link=with_link, codes=codes, rnd=rnd))
    tiles = sorted({rl.tile_of(*rl.parcel_origin(k)) for k in keys[2]})
    mapal = Path(args.mapal)
    sec = {2: rl.load_sec2([mapal / n for n in tiles if (mapal / n).exists()], 2, keys[2]),
           4: rl.load_sec2([mapal / "LEV3456R.DAT"], 4, keys[4])}
    print(f"level-2 parcels {len(sec[2])}/{len(keys[2])} in {len(tiles)} tiles; "
          f"level-4 parcels {len(sec[4])}/{len(keys[4])}")

    def points(si, level, groups):
        pts = []
        for _r, refs in groups:
            for r in refs:
                key, ea, eb = entry(si, r)
                rec = sec[level].get(key)
                hit = rl.resolve(rec, ea, eb) if rec else None
                if hit:
                    x, y = rec["nodes"][hit[0]]
                    pts.append((rl.node_latlon(key, x, y), rec["countries"]))
        return pts

    tot = collections.Counter()
    print("row loc_table records with_link joined placed_L2 country real/n random/n "
          "nbr_pairs nbr<1km shuffled<1km placed_L4 L4-L2 median_km <5km shuffled<5km role1=rev(role0)")
    for p in plan:
        t = p["t"]
        pr1, pr0 = pairs[ntab + t], pairs[t]
        l2, l4, ctry = {}, {}, collections.Counter()
        rev = collections.Counter()
        for code in p["codes"]:
            pts = points(1, 2, pr1["links"][code])
            if pts:
                l2[code] = pts
                for _ll, cs in pts:
                    ctry.update(cs)
            q = points(0, 4, pr0["links"].get(code, ()))
            if q:
                l4[code] = q
            rev[reversed_pair(role_links(pr1["links"][code], lambda r: entry(1, r)))] += 1
        main_c = majority(ctry)
        real_c = sum(any(main_c in cs for _ll, cs in pts) for pts in l2.values())
        rn = rc = 0
        for r in p["rnd"]:
            key, ea, eb = entry(1, r)
            rec = sec[2].get(key)
            if rec and rl.resolve(rec, ea, eb):
                rn += 1
                rc += main_c in rec["countries"]
        codes = list(l2)
        nb = nb1 = sh1 = 0
        for c in codes:
            pos = pr1["triples"][c][1]
            if pos in l2 and pos != c:
                nb += 1
                nb1 += min_dist([x for x, _ in l2[c]], [x for x, _ in l2[pos]]) < 1.0
                o = codes[rng.randrange(len(codes))]
                sh1 += min_dist([x for x, _ in l2[c]], [x for x, _ in l2[o]]) < 1.0
        both = [c for c in l4 if c in l2]
        cross, cross_sh = [], []
        for c in both:
            cross.append(min_dist([x for x, _ in l4[c]], [x for x, _ in l2[c]]))
            o = both[rng.randrange(len(both))]
            cross_sh.append(min_dist([x for x, _ in l4[c]], [x for x, _ in l2[o]]))
        med = sorted(cross)[len(cross) // 2] if cross else float("nan")
        c5, s5 = sum(x < 5.0 for x in cross), sum(x < 5.0 for x in cross_sh)
        print(f"{t:3d} {p['loc_table']:9d} {p['n']:7d} {p['with_link']:9d} {len(p['codes']):6d} {len(l2):9d} "
              f"{main_c!s:>7} {real_c}/{len(l2)} {rc}/{rn} {nb:9d} {nb1:7d} {sh1:12d} {len(l4):9d} "
              f"{med:16.2f} {c5:5d} {s5:12d} {rev[True]}/{rev[True] + rev[False]}")
        for k, v in (("records", p["n"]), ("with_link", p["with_link"]), ("joined", len(p["codes"])),
                     ("placed_l2", len(l2)), ("country_real", real_c), ("rnd_n", rn), ("rnd_c", rc),
                     ("nbr", nb), ("nbr1", nb1), ("sh1", sh1), ("placed_l4", len(l4)), ("cross", len(cross)),
                     ("c5", c5), ("s5", s5), ("rev", rev[True]), ("rev_n", rev[True] + rev[False])):
            tot[k] += v
    print("total: " + " ".join(f"{k} {v}" for k, v in tot.items()))
    print("neg/pos disagreements of code-matched records: " + ", ".join(f"{k} {v}" for k, v in why.most_common()))
    return 0


def cmd_selftest(_args: argparse.Namespace) -> int:
    fails = []

    def check(name, cond):
        if not cond:
            fails.append(name)

    # synthetic rows
    rows = [dict(src=i, dst=i + 1000, code=i + 2000, ref=0xA0000000 + i, id=i, pad2=0, tail=0, offset=0) for i in range(100)]
    # target that overlaps exactly on src
    ids = {"sec1_lid": set(range(50)), "sec2_id": set(range(20)), "parcels": {0xB0000000}}
    res = probe(rows, ids, seed=7)
    by = {r["key"]: r for r in res}
    check("src overlap 50", by["src_vs_sec1_lid"]["hits"] == 50)
    check("dst no real overlap", by["dst_vs_sec1_lid"]["hits"] <= by["dst_vs_sec1_lid"]["random_control"] * 2 + 5)
    check("ref no parcel", by["ref_vs_parcel"]["hits"] == 0)
    # decoded-key candidates (M4.16b): exact overlap is found, disjoint values give 0
    keys = {k: list(range(100)) for k in ("loc_code", "area", "negative", "positive", "intersection")}
    keys.update(ref_lo16=list(range(100)), ref_hi16=[5000, 5001], ref_u32=[0xB0000000])
    ids2 = {"sec1_lid": set(range(40)), "sec2_id": set(range(20)), "parcels": {0xB0000000},
            "parcel_w": {7000}}
    by2 = {r["key"]: r for r in probe_keys(decoded_candidates(keys, ids2), seed=3)}
    check("decoded loc overlap", by2["loc_code_vs_sec1_lid"]["hits"] == 40)
    check("decoded hi16 disjoint", by2["ref_hi16_vs_parcel_word"]["hits"] == 0)
    check("decoded u32 parcel", by2["ref_u32_vs_parcel"]["hits"] == 1)
    # place-all helpers (M4.16b second pass)
    import collections

    check("majority", majority(collections.Counter([203, 203, 276])) == 203 and majority(collections.Counter()) is None)
    check("min_dist 0", min_dist([(50.0, 14.0)], [(49.0, 14.0), (50.0, 14.0)]) == 0.0)
    check("min_dist 1 deg lat", abs(min_dist([(50.0, 14.0)], [(51.0, 14.0)]) - 111.19) < 0.1)
    ent = {1: (0xA, 0, 5), 2: (0xA, 0, 0x2006), 3: (0xB, 0, 7)}
    rl_ = role_links([(0, [1, 2]), (1, [2, 1]), (2, [3])], ent.__getitem__)
    check("role links", rl_ == {0: [(0xA, 5), (0xA, 6)], 1: [(0xA, 6), (0xA, 5)], 2: [(0xB, 7)]})
    check("role1 reversed", reversed_pair(rl_) is True)
    check("role1 not reversed", reversed_pair({0: [(1, 2), (1, 3)], 1: [(1, 2), (1, 3)]}) is False)
    check("role1 missing", reversed_pair({0: [(1, 2)]}) is None)
    check("disagree kinds", disagree_kind((5, 0), (5, None)) == "lctbl_field_absent_rdstm_has_0"
          and disagree_kind((5, 6), (5, 7)) == "pos_differs" and disagree_kind((5, 6), (4, 6)) == "neg_differs")
    print(f"selftest: {'OK' if not fails else 'FAIL ' + ', '.join(fails)}")
    return 0 if not fails else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("probe")
    p.add_argument("rdstm")
    p.add_argument("mapal")
    p.add_argument("--limit-rows", type=int, default=0)
    p.add_argument("--limit-tiles", type=int, default=0)
    p.set_defaults(func=cmd_probe)
    p = sub.add_parser("probe-decoded")
    p.add_argument("lctbl")
    p.add_argument("rdstm")
    p.add_argument("mapal")
    p.add_argument("--limit-tiles", type=int, default=0)
    p.add_argument("--tiles", nargs="*", default=None, help="tile file names (default: all)")
    p.set_defaults(func=cmd_probe_decoded)
    p = sub.add_parser("place-all")
    p.add_argument("lctbl")
    p.add_argument("rdstm")
    p.add_argument("mapal")
    p.add_argument("--tables", default=None, help="set-1 table rows, e.g. 0,9 (default: all)")
    p.add_argument("--join", choices=("negpos", "code-only"), default="negpos",
                   help="negpos: code match with neg/pos agreeing (M4.16b rule); "
                        "code-only: the code-matched records whose neg/pos disagree (control)")
    p.add_argument("--seed", type=int, default=1)
    p.set_defaults(func=cmd_place_all)
    a = ap.parse_args(argv)
    if a.selftest:
        return cmd_selftest(a)
    if not hasattr(a, "func"):
        ap.print_help()
        return 2
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
