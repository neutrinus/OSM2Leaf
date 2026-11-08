#!/usr/bin/env python3
"""Decode POI coordinate ids from POINT shards and compare with reference points.

Each POINT name record (tag 0x60 or 0x68) carries its position twice as a
packed u16 pair: copy A at bytes 2..5 and copy B at bytes 12..15 of the record
(EXP-2026-11-08-M4.8b). A decodes with the COORD001 formula
(`coord.xy_to_latlon`, origin 52742 by default). This tool reads the POINT
shards through the committed `cmpind` and `poi_icons` helpers, prints the
ids of a record, and compares decoded A points with a reference table of
Wikipedia coordinates (no vendor names are written by this tool into the
repository; `find` prints names to the terminal only).

Usage::

  poi_point_check.py --selftest
  poi_point_check.py find ROOT SHARD --a X Y        # SHARD like POINT004
  poi_point_check.py check --us US_ROOT --eu EU_ROOT REFS.tsv

REFS.tsv columns: id, country (US|EU), shard, stream_offset (hex),
record_index, ref_lat, ref_lon, reference (URL). Records are addressed by
position, not by name, so the committed table holds no vendor strings.

ROOT is an extracted tree whose REFER001 holds POINTnnn.DAT.cmp/.ind.
"""

from __future__ import annotations

import argparse
import math
import re
import statistics
import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import coord  # noqa: E402
import cmpind  # noqa: E402
import poi_icons  # noqa: E402

EARTH_RADIUS_M = 6371008.8
M_PER_DEG = 111320.0
NAME_RE = re.compile(rb"([A-Z0-9][A-Z0-9 &'./,@-]{2,})")


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def ids_of(record: bytes) -> tuple[tuple[int, int], tuple[int, int]]:
    """Return copy A and copy B as (x, y) packed u16 pairs."""
    if len(record) < 16:
        raise ValueError("record shorter than 16 bytes")
    return struct.unpack_from(">HH", record, 2), struct.unpack_from(">HH", record, 12)


def iter_records(data: bytes):
    """Yield (stream_offset, record_index, tag, record) for every name record."""
    for stream_off, blob in poi_icons.iter_streams(data):
        for index, (tag, rec) in enumerate(poi_icons.iter_point_records(blob)):
            if len(rec) >= 16:
                yield stream_off, index, tag, rec


def decode_shard(root: Path, shard: str) -> bytes:
    cmp_path = root / "REFER001" / f"{shard}.DAT.cmp"
    ind_path = root / "REFER001" / f"{shard}.DAT.ind"
    data, _ = cmpind.decode(cmp_path, ind_path)
    return data


def cmd_find(args: argparse.Namespace) -> int:
    data = decode_shard(Path(args.root), args.shard)
    want = (args.a[0], args.a[1])
    hits = 0
    for stream_off, index, tag, rec in iter_records(data):
        a, b = ids_of(rec)
        if a == want:
            hits += 1
            name = NAME_RE.findall(rec[:-2])
            label = name[-1].decode("latin1") if name else ""
            print(f"{args.shard} stream={stream_off:#x} index={index} tag={tag:#04x} "
                  f"A={a} B={b} name={label}")
    print(f"matches: {hits}")
    return 0 if hits else 1


def load_refs(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        pid, country, shard, stream, index, rlat, rlon, ref = line.split("\t")
        rows.append({
            "id": pid, "country": country, "shard": shard,
            "stream": int(stream, 16), "index": int(index),
            "ref_lat": float(rlat), "ref_lon": float(rlon), "ref": ref,
        })
    return rows


def cmd_check(args: argparse.Namespace) -> int:
    roots = {"US": Path(args.us), "EU": Path(args.eu)}
    rows = load_refs(Path(args.refs))
    shards: dict[tuple[str, str], bytes] = {}
    results = []
    for row in rows:
        key = (row["country"], row["shard"])
        if key not in shards:
            shards[key] = decode_shard(roots[row["country"]], row["shard"])
        found = None
        for stream_off, index, _, rec in iter_records(shards[key]):
            if stream_off == row["stream"] and index == row["index"]:
                found = rec
                break
        if found is None:
            print(f"{row['id']}: record not found at stream {row['stream']:#x} index {row['index']}")
            return 1
        a, _ = ids_of(found)
        lat, lon = coord.xy_to_latlon(a[0], a[1], coord.LON_ORIGIN_COORD)
        _, lon_tile = coord.xy_to_latlon(a[0], a[1], coord.LON_ORIGIN_TILE)
        results.append({
            "id": row["id"], "a": a, "lat": lat, "lon": lon, "lon_tile": lon_tile,
            "ref_lat": row["ref_lat"], "ref_lon": row["ref_lon"],
            "err_m": haversine_m(row["ref_lat"], row["ref_lon"], lat, lon),
            "err_tile_m": haversine_m(row["ref_lat"], row["ref_lon"], lat, lon_tile),
            "dlat_m": (lat - row["ref_lat"]) * M_PER_DEG,
            "dlon_m": (lon - row["ref_lon"]) * M_PER_DEG * math.cos(math.radians(row["ref_lat"])),
        })
    print(f"{'id':4} {'A':>17} {'dlat_m':>9} {'dlon_m':>9} {'err52742_m':>11} {'err52736_m':>11}")
    for r in results:
        print(f"{r['id']:4} {str(r['a']):>17} {r['dlat_m']:9.0f} {r['dlon_m']:9.0f} "
              f"{r['err_m']:11.0f} {r['err_tile_m']:11.0f}")
    n = len(results)
    print(f"n={n}")
    print(f"median err origin 52742: {statistics.median(r['err_m'] for r in results):.0f} m")
    print(f"median err origin 52736: {statistics.median(r['err_tile_m'] for r in results):.0f} m")
    print(f"median dlat: {statistics.median(r['dlat_m'] for r in results):.0f} m")
    print(f"median dlon (52742): {statistics.median(r['dlon_m'] for r in results):.0f} m")
    # negative control: each decoded point against the next POI's reference
    neg = []
    for i, r in enumerate(results):
        nxt = results[(i + 1) % n]
        neg.append(haversine_m(nxt["ref_lat"], nxt["ref_lon"], r["lat"], r["lon"]))
    print(f"negative control (shifted reference) median: {statistics.median(neg):.0f} m, "
          f"min: {min(neg):.0f} m")
    return 0


def selftest() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"  {name:<40} {'OK' if cond else 'FAIL'} {detail}".rstrip())
        if not cond:
            failures.append(name)

    # Synthetic 0x60 record: tag, len2, two ids, padding. A at 2..5, B at 12..15.
    x, y = 39071, 40348  # packed pair from a real Dallas-area record (no names)
    rec = bytearray(16)
    rec[0], rec[1] = 0x60, 8
    struct.pack_into(">HH", rec, 2, x, y)
    struct.pack_into(">HH", rec, 12, x, y)
    a, b = ids_of(bytes(rec))
    check("ids_of copy A and B", a == (x, y) and b == (x, y))
    try:
        ids_of(b"\x60\x02")
        check("short record rejected", False)
    except ValueError:
        check("short record rejected", True)
    lat, lon = coord.xy_to_latlon(x, y, coord.LON_ORIGIN_COORD)
    check("decode matches coord.py", coord.latlon_to_xy(lat, lon, coord.LON_ORIGIN_COORD) == (x, y),
          f"lat={lat:.4f} lon={lon:.4f}")
    check("haversine zero", haversine_m(lat, lon, lat, lon) == 0.0)
    km = haversine_m(0.0, 0.0, 0.0, 1.0)
    check("haversine 1 deg equator", abs(km - 111195.0) < 50.0, f"{km:.0f} m")
    print(f"poi_point_check selftest: {'OK' if not failures else 'FAILED'}")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    find = sub.add_parser("find", help="locate records by copy-A ids in one shard")
    find.add_argument("root")
    find.add_argument("shard")
    find.add_argument("--a", nargs=2, type=int, required=True, metavar=("X", "Y"))
    find.set_defaults(func=cmd_find)
    check = sub.add_parser("check", help="compare decoded A points with references")
    check.add_argument("--us", required=True, help="extracted US tree (REFER001 inside)")
    check.add_argument("--eu", required=True, help="extracted EU tree (REFER001 inside)")
    check.add_argument("refs")
    check.set_defaults(func=cmd_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
