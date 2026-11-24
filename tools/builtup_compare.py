#!/usr/bin/env python3
"""builtup_compare.py — per-parcel factory vs generated built-up cover (M5.95).

For a factory tile and our from-zero tile, decompress every section-1 level-1
odd record, measure the area of layer-0 `0xc12b` (urban/built-up) polygons in
quantised 0..2047 units, and express it as a share of one parcel (2047**2 units,
clamped to 1). The two per-parcel share maps are compared at a 10 % tolerance,
and a sensitivity sweep over building-density thresholds selects the rule with
the best agreement. Only counts and shares are printed; no vendor bytes.

    builtup_compare.py FACTORY.DAT OURS.DAT --buildings BUILDINGS.json \\
        [--tol 0.10] [--areas AREAS.jsonl] [--sweep] [--json]
    builtup_compare.py --selftest
"""
from __future__ import annotations

import argparse
import collections
import json
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE / "ze0-viewer" / "tools_ze0", HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import clarion_bg  # noqa: E402
import s1_wide_dir  # noqa: E402
import tile_from_zero  # noqa: E402

URBAN = 0xC12B
UNITS = 2048


def ring_area(pts) -> float:
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:]))) / 2.0


def urban_share(plain: bytes) -> float:
    """Fraction of a parcel covered by 0xc12b polygons in one odd record."""
    rec = clarion_bg.parse_record(plain)
    total = 0.0
    for li, g in rec["layers"].items():
        if li != 0 or "raw" in g:
            continue
        for sub in [g] + g.get("more", []):
            for sh in sub["shapes"]:
                if sh["type"] == URBAN and len(sh["pts"]) >= 4:
                    total += ring_area(sh["pts"])
    return min(1.0, total / float((UNITS - 1) ** 2))


def odd_shares(tile: bytes) -> dict:
    """``{(y0, x0, row, col): urban_share}`` for every odd record of a tile."""
    out = {}
    for level, D in s1_wide_dir.section1_dirs(tile):
        if level != 1:
            continue
        y0 = D["y"]
        x0 = (D["x"] + 1024) & 0xFFFF  # X_FIELD_BIAS of tilewriter/s1_wide_dir
        for row in s1_wide_dir.parse_dir(tile, D["off"], 1, check=False)["rows"]:
            for rec in row["records"]:
                if rec["part"] != "odd" or rec["words"] == 0:
                    continue
                try:
                    plain = zlib.decompress(rec["raw"])
                    share = urban_share(plain)
                except (zlib.error, AssertionError, struct.error, IndexError):
                    continue
                out[(y0, x0, row["index"], rec["col"])] = share
    return out


def compare(factory: dict, ours: dict, tol: float = 0.10) -> dict:
    keys = sorted(set(factory) | set(ours))
    agree = disagree = 0
    exact = 0
    buckets = collections.Counter()
    for k in keys:
        f = factory.get(k, 0.0)
        o = ours.get(k, 0.0)
        if abs(f - o) <= tol:
            agree += 1
        else:
            disagree += 1
        if abs(f - o) < 1e-6:
            exact += 1
        if f >= 0.5 and o >= 0.5:
            bucket = "both_high"
        elif f < 0.5 and o < 0.5:
            bucket = "both_low"
        elif f >= 0.5:
            bucket = "factory_high"
        else:
            bucket = "ours_high"
        buckets[bucket] += 1
    return {"parcels": len(keys), "agree_at_tol": agree, "disagree": disagree,
            "exact": exact, "tolerance": tol, "buckets": dict(buckets)}


def sweep(areas_path: str | None, buildings_path: str | None, factory: dict,
          thresholds=(0.05, 0.10, 0.15, 0.20, 0.25, 0.30)) -> dict:
    """Sensitivity: build the rule at each threshold (areas-only) and compare."""
    if not areas_path:
        return {}
    from tile_from_zero import built_up_share, load_building_stats
    b = load_building_stats(buildings_path)
    # Read area rings per parcel from the JSONL the same way build_background
    # does, but only keep urban rings (the only kind this rule consumes).
    by_parcel = collections.defaultdict(lambda: collections.defaultdict(list))
    import tilewriter
    with open(areas_path, encoding="utf-8") as fh:
        for line in fh:
            f = json.loads(line)
            if f.get("kind") != "urban" or "rings" not in f:
                continue
            for ring in f["rings"]:
                pts = [tuple(p) for p in ring]
                shp = tile_from_zero._ring_area(pts)
                if shp < 1:
                    continue
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                for parcel in tile_from_zero._parcels_over((min(xs), min(ys), max(xs), max(ys))):
                    q = [tilewriter.quantise(lon, lat, *__import__("clarion_bg").parcel_geo(1, *parcel))
                         for lon, lat in pts]
                    if len(q) >= 4 and tile_from_zero._ring_area(q) >= 1:
                        by_parcel[parcel]["urban"].append(q)
    out = {}
    for t in thresholds:
        ours = {}
        for p, kinds in by_parcel.items():
            share, _l, _b = built_up_share(p, kinds, b, 1)
            if share >= t:
                ours[p] = 1.0
        for p in b:
            share, _l, _bb = built_up_share(p, {}, b, 1)
            if share >= t:
                ours[p] = 1.0
        c = compare(factory, ours, 0.10)
        out[str(t)] = {"agree_at_tol": c["agree_at_tol"], "parcels": c["parcels"],
                       "filled": len(ours)}
    return out


def selftest() -> int:
    fails = 0

    def ok(cond, msg):
        nonlocal fails
        print(("ok   " if cond else "FAIL ") + msg)
        fails += 0 if cond else 1

    full = [(0, 0), (2047, 0), (2047, 2047), (0, 2047), (0, 0)]
    half = [(0, 0), (2047, 0), (2047, 1023), (0, 1023), (0, 0)]
    ok(abs(urban_share(_record(full)) - 1.0) < 1e-6, "a full 0xc12b ring has share 1.0")
    ok(abs(urban_share(_record(half)) - 0.5) < 0.01, "a half-height ring has share 0.5")
    ok(urban_share(_record([], typ=0xC11D)) == 0.0, "a park record has no urban share")
    c = compare({(1, 2, 3, 4): 1.0}, {(1, 2, 3, 4): 0.95, (9, 9, 9, 9): 0.0}, 0.10)
    ok(c["agree_at_tol"] == 2 and c["disagree"] == 0 and c["exact"] == 1,
       "10%% tolerance: 2/2 agree, 1 exact: %s" % c)
    print("builtup_compare selftest: %s (%d failure(s))" % ("OK" if not fails else "FAIL", fails))
    return 1 if fails else 0


def _record(rings, typ=URBAN) -> bytes:
    layers = {}
    if rings:
        shapes = [dict(type=typ, ref=0xFFFF, pts=rings)]
        layers[0] = dict(kind=0x80, shapes=shapes)
    hdr = [0] * 22
    hdr[0], hdr[1] = 0x2046, 0x00FA
    hdr[2] = 0x19
    return clarion_bg.build_record(dict(hdr=hdr, nlayers=26, layers=layers,
                                        sections={}, gi=9, strict=True))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("factory", nargs="?")
    ap.add_argument("ours", nargs="?")
    ap.add_argument("--buildings")
    ap.add_argument("--areas")
    ap.add_argument("--tol", type=float, default=0.10)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not (args.factory and args.ours):
        ap.print_usage(sys.stderr)
        return 2
    f = odd_shares(Path(args.factory).read_bytes())
    o = odd_shares(Path(args.ours).read_bytes())
    result = {"factory_parcels_with_urban": sum(1 for v in f.values() if v > 0),
              "ours_parcels_with_urban": sum(1 for v in o.values() if v > 0),
              "comparison": compare(f, o, args.tol)}
    if args.sweep:
        result["sensitivity"] = sweep(args.areas, args.buildings, f)
    print(json.dumps(result, indent=1, default=str) if args.json else
          "factory urban parcels %d, ours %d; agree %d/%d at %.0f%%" %
          (result["factory_parcels_with_urban"], result["ours_parcels_with_urban"],
           result["comparison"]["agree_at_tol"], result["comparison"]["parcels"],
           args.tol * 100))
    return 0


if __name__ == "__main__":
    sys.exit(main())
