#!/usr/bin/env python3
"""Search POINT/ADDRE records for 0..2047-class sub-unit position fields.

M4.8d: M4.8b could not test local scale 1 vs 2 because no sub-unit
position field was decoded from packed POI ids.  This tool scans zlib-framed
POINT name records (tag 0x60/0x68) for u16 and 11-bit fields in the 0..2047
range and tests whether any correlate with the tile-local coordinates derived
from copy A (``coord.latlon_to_local``, scales 1 and 2).

A ``0..2047-class`` value is a field whose values fit in 11 bits (0..2047),
matching the firmware's intra-mesh coordinate bound.  Finding such a field
does not by itself make it a geographic position; correlation with local(A)
or with an independent reference is required.

Usage::

    poi_subunit.py --selftest
    poi_subunit.py scan ROOT SHARD [SHARD ...] [--limit N]
    poi_subunit.py refs --us US_ROOT --eu EU_ROOT REFS.tsv

ROOT is an extracted tree whose REFER001 holds POINTnnn.DAT.cmp/.ind.
``refs`` re-examines the M4.8b reference POIs and dumps 2047-class body
fields for each.
"""
from __future__ import annotations

import argparse
import collections
import math
import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import cmpind  # noqa: E402
import coord  # noqa: E402
import poi_icons  # noqa: E402


def ids_of(record: bytes) -> tuple[tuple[int, int], tuple[int, int]]:
    if len(record) < 16:
        raise ValueError("record shorter than 16 bytes")
    return struct.unpack_from(">HH", record, 2), struct.unpack_from(">HH", record, 12)


def iter_records(data: bytes):
    for stream_off, blob in poi_icons.iter_streams(data):
        for index, (tag, rec) in enumerate(poi_icons.iter_point_records(blob)):
            if len(rec) >= 16:
                yield stream_off, index, tag, rec


def decode_shard(root: Path, shard: str) -> bytes:
    data, _ = cmpind.decode(root / "REFER001" / f"{shard}.DAT.cmp",
                            root / "REFER001" / f"{shard}.DAT.ind")
    return data


def classify_u16_fields(records, max_off: int = 88):
    """Return {offset: stats} for aligned BE u16 fields over records."""
    stats = {}
    n = 0
    for _, _, _, rec in records:
        n += 1
        for off in range(0, min(len(rec) - 1, max_off), 2):
            v = struct.unpack_from(">H", rec, off)[0]
            s = stats.setdefault(off, {"n": 0, "min": 65535, "max": 0, "le2047": 0, "vals": collections.Counter()})
            s["n"] += 1
            if v < s["min"]:
                s["min"] = v
            if v > s["max"]:
                s["max"] = v
            if v <= 2047:
                s["le2047"] += 1
            if off <= 24 or s["n"] <= 20000:
                s["vals"][v] += 1
    return n, stats


def local_of_a(rec):
    ax, ay = struct.unpack_from(">HH", rec, 2)
    lat, lon = coord.xy_to_latlon(ax, ay)
    cell = coord.cell_for(lat, lon)
    lx2, ly2 = coord.latlon_to_local(lat, lon, cell, 2)
    lx1, ly1 = coord.latlon_to_local(lat, lon, cell, 1)
    return ax, ay, cell, (lx2, ly2), (lx1, ly1)


def correlation_scan(records, candidates, limit: int = 30000):
    """Test candidate field extractors against local(A) for scales 1 and 2.

    candidates: list of (name, fn(rec)->value_or_None).  Returns counts.
    """
    counts = {c[0]: {"n": 0, "eq_lx2": 0, "eq_ly2": 0, "eq_lx1": 0, "eq_ly1": 0} for c in candidates}
    n = 0
    for _, _, _, rec in records:
        try:
            _, _, _, (lx2, ly2), (lx1, ly1) = local_of_a(rec)
        except Exception:
            continue
        for name, fn in candidates:
            v = fn(rec)
            if v is None:
                continue
            c = counts[name]
            c["n"] += 1
            if v == lx2:
                c["eq_lx2"] += 1
            if v == ly2:
                c["eq_ly2"] += 1
            if v == lx1:
                c["eq_lx1"] += 1
            if v == ly1:
                c["eq_ly1"] += 1
        n += 1
        if n >= limit:
            break
    return n, counts


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def cmd_scan(args):
    recs = []
    for shard in args.shards:
        data = decode_shard(Path(args.root), shard)
        for item in iter_records(data):
            recs.append(item)
            if args.limit and len(recs) >= args.limit:
                break
        if args.limit and len(recs) >= args.limit:
            break
    n, stats = classify_u16_fields(recs)
    print(f"records={n}")
    for off in sorted(stats):
        s = stats[off]
        if s["n"] == 0:
            continue
        pct = s["le2047"] / s["n"] * 100
        cls = "2047-class" if pct > 99 else ("mixed" if pct > 50 else "wide")
        if s["max"] <= 2047 or off < 26 or pct > 90:
            top = s["vals"].most_common(4)
            print(f"  +{off:02d}: min={s['min']:5d} max={s['max']:5d} <=2047={pct:5.1f}% {cls} top={top}")
    # correlation for 2047-class candidates
    candidates = [
        ("+08", lambda r: struct.unpack_from(">H", r, 8)[0] if len(r) > 9 else None),
        ("+06&0x7ff", lambda r: struct.unpack_from(">H", r, 6)[0] & 0x7ff if len(r) > 7 else None),
        ("+16", lambda r: struct.unpack_from(">H", r, 16)[0] if len(r) > 17 else None),
        ("+20", lambda r: struct.unpack_from(">H", r, 20)[0] if len(r) > 21 else None),
    ]
    cn, counts = correlation_scan(recs, candidates, limit=min(args.limit or 30000, 30000))
    print(f"correlation n={cn} (match to local(A) derived from copy A):")
    for name, c in counts.items():
        print(f"  {name}: ==lx2 {c['eq_lx2']} ==ly2 {c['eq_ly2']} ==lx1 {c['eq_lx1']} ==ly1 {c['eq_ly1']} /{c['n']}")
    return 0


def cmd_refs(args):
    rows = []
    for line in Path(args.refs).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        pid, country, shard, stream, index, rlat, rlon, ref = line.split("\t")
        rows.append({"id": pid, "country": country, "shard": shard,
                     "stream": int(stream, 16), "index": int(index),
                     "ref_lat": float(rlat), "ref_lon": float(rlon)})
    roots = {"US": Path(args.us), "EU": Path(args.eu)}
    cache = {}
    for r in rows:
        key = (r["country"], r["shard"])
        if key not in cache:
            cache[key] = decode_shard(roots[r["country"]], r["shard"])
        rec = None
        for soff, idx, tag, rc in iter_records(cache[key]):
            if soff == r["stream"] and idx == r["index"]:
                rec = rc
                break
        if rec is None:
            print(r["id"], "NOT FOUND")
            return 1
        ax, ay, cell, (lx2, ly2), (lx1, ly1) = local_of_a(rec)
        v6, v8, v10 = struct.unpack_from(">HHH", rec, 6)
        v16, v18, v20, v22 = struct.unpack_from(">HHHH", rec, 16)
        p6 = v6 & 0x7ff
        # interpret (p6,v8) as local s2 in A's cell
        lat_p, lon_p = coord.local_to_latlon(cell, p6, v8, 2)
        d_ref = haversine_m(r["ref_lat"], r["ref_lon"], lat_p, lon_p)
        lat_a, lon_a = coord.xy_to_latlon(ax, ay)
        d_a = haversine_m(lat_a, lon_a, lat_p, lon_p)
        print(f"{r['id']} A={ax,ay} cell={cell} localA_s2={lx2,ly2} "
              f"v6=0x{v6:04x}(p6={p6}) v8={v8} v10=0x{v10:04x} v16={v16} v20={v20} "
              f"as_local(p6,v8,s2): d_ref={d_ref:.0f}m d_fromA={d_a:.0f}m")
    return 0


def selftest() -> int:
    failures = []

    def check(name, cond, detail=""):
        print(f"  {name:<44} {'OK' if cond else 'FAIL'} {detail}".rstrip())
        if not cond:
            failures.append(name)

    # synthetic 0x60 record with known A and body fields
    ax, ay = 41167, 53693  # M4.8 POI fixture A (Monaco, B40R060R)
    rec = bytearray(48)
    rec[0], rec[1] = 0x60, 24
    struct.pack_into(">HH", rec, 2, ax, ay)
    struct.pack_into(">HHH", rec, 6, 0x0800 | 100, 200, 0x0610)  # v6 has bit11, v8=200
    struct.pack_into(">HH", rec, 12, ax, ay)
    struct.pack_into(">HHHH", rec, 16, 576, 500, 832, 506)
    a, b = ids_of(bytes(rec))
    check("ids_of", a == (ax, ay) and b == (ax, ay))
    v6, v8, v10 = struct.unpack_from(">HHH", rec, 6)
    check("v6 bit11 flag, low 11 bits", (v6 >> 11) == 1 and (v6 & 0x7ff) == 100)
    check("v8 is 0..2047-class", 0 <= v8 <= 2047 and v8 == 200)
    v16, _, v20, _ = struct.unpack_from(">HHHH", rec, 16)
    check("v16/v20 2047-class discrete", v16 == 576 and v20 == 832)
    _, _, cell, (lx2, ly2), (lx1, ly1) = local_of_a(bytes(rec))
    check("local_of_a B40R060R fixture", cell == "B40R060R" and (lx2, ly2) == (414, 878))
    # classify_u16_fields on synthetic records
    recs = [(0, 0, 0x60, bytes(rec)) for _ in range(5)]
    n, stats = classify_u16_fields(recs)
    check("classify_u16_fields count", n == 5)
    check("+06 2047-class via low11 in data", stats[6]["max"] == (0x0800 | 100))
    check("+08 all <=2047", stats[8]["le2047"] == 5 and stats[8]["max"] == 200)
    check("+16 all <=2047", stats[16]["le2047"] == 5)
    # correlation: synthetic v8=200 does not equal lx2=414
    cands = [("+08", lambda r: struct.unpack_from(">H", r, 8)[0])]
    cn, counts = correlation_scan(recs, cands)
    check("correlation no false match", counts["+08"]["eq_lx2"] == 0 and counts["+08"]["eq_ly2"] == 0)

    print(f"poi_subunit selftest: {'OK' if not failures else 'FAILED'}")
    return 1 if failures else 0


def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    sc = sub.add_parser("scan", help="classify 0..2047-class fields and test correlation")
    sc.add_argument("root")
    sc.add_argument("shards", nargs="+")
    sc.add_argument("--limit", type=int, default=50000)
    sc.set_defaults(func=cmd_scan)
    sr = sub.add_parser("refs", help="dump 2047-class fields for M4.8b reference POIs")
    sr.add_argument("--us", required=True)
    sr.add_argument("--eu", required=True)
    sr.add_argument("refs")
    sr.set_defaults(func=cmd_refs)
    return p


def main(argv=None):
    p = build_parser()
    a = p.parse_args(argv)
    if a.selftest:
        return selftest()
    if not getattr(a, "func", None):
        p.print_help()
        return 2
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
