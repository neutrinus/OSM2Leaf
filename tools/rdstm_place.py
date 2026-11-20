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

Usage:
  rdstm_place.py probe RDSTM001.DAT MAPAL001 [--limit-tiles N]
  rdstm_place.py probe-decoded LCTBL001.DAT RDSTM001.DAT MAPAL001 [--tiles B48R058R.DAT]
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
    a = ap.parse_args(argv)
    if a.selftest:
        return cmd_selftest(a)
    if not hasattr(a, "func"):
        ap.print_help()
        return 2
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
