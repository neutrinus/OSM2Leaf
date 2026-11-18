#!/usr/bin/env python3
"""Map ``MAPAL001/BxxRyyR.DAT`` tile names to latitude/longitude.

Verified against the EU 2011 tile set: every bounding box in each tile's
``0x2ac`` descriptor lies inside the rectangle computed here.

The B and R components are hexadecimal. One grid unit is 1 degree of
longitude and 2/3 degree of latitude; a tile is 8 x 8 units::

    lat_min = int(B, 16) * 2/3
    lat_max = lat_min + 16/3          # 5.333 degrees
    lon_max = 108 - int(R, 16)
    lon_min = lon_max - 8             # 8 degrees

The ``cover`` subcommand (M5.46) is a read-only census: it reads a build
profile's ``region.bbox`` and classifies every ``BxxRyyR`` tile as

* ``contained`` — the profile's whole region box lies inside this one tile
  box (the tile covers the region, a P1 copy-whole candidate);
* ``intersects`` — the tile only overlaps the region box widened by the
  profile's ``border_buffer_deg`` (an edge tile the buffer decides);
* ``outside`` — the tile touches neither (not needed by this profile).

The default text table prints the non-``outside`` rows (plus any ``include``
tile); ``--all`` prints all 63 lattice rows and ``--json`` always carries
them.  Only tile **names** are read; no tile bytes and no OSM data.  The
buffer padding is the same rule ``profile_validate.buffered_bbox`` uses (1 deg
of latitude, longitude padded by ``buffer / cos(mid-latitude)``).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

TILE_RE = re.compile(r"^B([0-9A-Fa-f]{2})R([0-9A-Fa-f]{3})R\.DAT$")
LAT_UNIT = 2.0 / 3.0
LON_UNIT = 1.0
SPAN = 8
# EU 2011 addressable lattice: rows B28..B68 and columns R048..R078, step 8.
LATTICE_B = tuple(range(0x28, 0x69, 0x08))
LATTICE_R = tuple(range(0x48, 0x79, 0x08))


def tile_box(name: str) -> tuple[float, float, float, float]:
    match = TILE_RE.match(name)
    if not match:
        raise ValueError(f"not a BxxRyyR.DAT name: {name}")
    b = int(match.group(1), 16)
    r = int(match.group(2), 16)
    lat_min = b * LAT_UNIT
    lon_max = 108 - r * LON_UNIT
    return lat_min, lat_min + SPAN * LAT_UNIT, lon_max - SPAN * LON_UNIT, lon_max


def collect(directory: Path) -> list[tuple[str, tuple[float, float, float, float]]]:
    tiles = []
    for path in sorted(directory.glob("B*R*R.DAT")):
        try:
            tiles.append((path.name, tile_box(path.name)))
        except ValueError:
            continue
    return tiles


def fmt_box(box: tuple[float, float, float, float]) -> str:
    lat_min, lat_max, lon_min, lon_max = box
    return f"{lat_min:6.2f}..{lat_max:6.2f} N  {lon_min:7.2f}..{lon_max:6.2f} E"


def buffered_bbox(bbox: list[float], buffer_deg: float) -> tuple[float, float, float, float]:
    """Widen ``bbox`` (W,S,E,N) by ``buffer_deg`` of latitude, keeping km width.

    Same rule as ``profile_validate.buffered_bbox``: longitude is padded by
    ``buffer / cos(mid-latitude)`` so the buffer is roughly isotropic on the
    ground.
    """
    west, south, east, north = (float(value) for value in bbox)
    mid = math.radians((south + north) / 2.0)
    lon_pad = buffer_deg / max(math.cos(mid), 0.2)
    return west - lon_pad, south - buffer_deg, east + lon_pad, north + buffer_deg


def classify_tile(
    box: tuple[float, float, float, float],
    bbox: list[float],
    buffer_deg: float = 0.0,
) -> str:
    """Classify one tile ``(lat_min, lat_max, lon_min, lon_max)`` against a region.

    ``contained``  — the **whole region** ``bbox`` lies inside this one tile
                     box, so the tile alone covers the region and is the P1
                     copy-whole candidate (P0's `B48R058R` for Dolnośląskie).
    ``intersects`` — the tile overlaps the region bbox widened by the buffer
                     but does not cover the whole region (an edge tile the
                     profile's ``border_buffer_deg`` decides).
    ``outside``    — no overlap with the buffered region box.

    ``contained`` is tested against the raw region bbox; the buffer only
    widens the overlap test, because cross-border routing does not make a
    partly-covered neighbour a whole-region tile.
    """
    west, south, east, north = (float(value) for value in bbox)
    lat_min, lat_max, lon_min, lon_max = box
    eps = 1e-9
    if (west >= lon_min - eps and east <= lon_max + eps
            and south >= lat_min - eps and north <= lat_max + eps):
        return "contained"
    bw, bs, be, bn = buffered_bbox(list(bbox), buffer_deg)
    if lon_min < be - eps and bw < lon_max - eps and lat_min < bn - eps and bs < lat_max - eps:
        return "intersects"
    return "outside"


def lattice_names() -> list[str]:
    """Every addressable ``BxxRyyR`` cell (63 rows x columns of the EU grid)."""
    return [f"B{b:02X}R{r:03X}R.DAT" for b in LATTICE_B for r in LATTICE_R]


def census(
    profile: dict,
    present: dict[str, tuple[float, float, float, float]] | None = None,
) -> dict:
    """One row per lattice tile, classified against the profile's region.

    ``present`` maps a tile name to its box for tiles that exist as files (the
    factory directory, if given).  A lattice tile that is absent from it is
    still listed (the lattice, not the 45-file inventory, is the universe) and
    is marked ``factory=False``.
    """
    region = profile.get("region")
    if not isinstance(region, dict) or "bbox" not in region:
        raise ValueError("profile has no region.bbox")
    bbox = region["bbox"]
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError("region.bbox must be [west, south, east, north]")
    buffer_deg = float(profile.get("border_buffer_deg", 0.0) or 0.0)
    include = list((profile.get("tiles") or {}).get("include") or [])
    present = present or {}

    rows = []
    for name in lattice_names():
        box = present.get(name) or tile_box(name)
        rows.append({
            "tile": name[:-4],
            "box": box,
            "class": classify_tile(box, bbox, buffer_deg),
            "factory": name in present,
            "include": name[:-4] in include,
        })
    counts = {"contained": 0, "intersects": 0, "outside": 0}
    for row in rows:
        counts[row["class"]] += 1
    return {
        "profile": profile.get("name"),
        "region": region.get("name"),
        "bbox": [float(value) for value in bbox],
        "border_buffer_deg": buffer_deg,
        "buffered_bbox": list(buffered_bbox(bbox, buffer_deg)),
        "include": include,
        "lattice": len(rows),
        "factory_tiles": len(present),
        "counts": counts,
        "rows": rows,
    }


def fmt_cover(doc: dict, show_all: bool = False) -> str:
    west, south, east, north = doc["bbox"]
    bw, bs, be, bn = doc["buffered_bbox"]
    buffer_deg = doc["border_buffer_deg"]
    out = [
        f"profile {doc['profile']}  region {doc['region']}",
        f"bbox        {west:.2f}..{east:.2f} E  {south:.2f}..{north:.2f} N",
        f"buffered    {bw:.2f}..{be:.2f} E  {bs:.2f}..{bn:.2f} N  "
        f"(border_buffer_deg {buffer_deg:.2f})",
        f"include     {doc['include'] or '(none)'}",
        f"{'tile':<10s} {'latitude':>16s}  {'longitude':>18s}  class       factory include",
    ]
    for row in doc["rows"]:
        if row["class"] == "outside" and not row["include"] and not show_all:
            continue
        out.append(
            f"{row['tile']:<10s} {fmt_box(row['box'])}  "
            f"{row['class']:<11s} {'yes' if row['factory'] else 'no ':<7s} "
            f"{'yes' if row['include'] else 'no'}")
    c = doc["counts"]
    out.append(
        f"census: contained={c['contained']} intersects={c['intersects']} "
        f"outside={c['outside']} lattice={doc['lattice']} "
        f"factory_tiles={doc['factory_tiles']}")
    return "\n".join(out)


def cmd_cover(args: argparse.Namespace) -> int:
    try:
        profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"error: cannot read profile {args.profile}: {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"error: {args.profile} is not JSON: {exc}", file=sys.stderr)
        return 1
    present: dict[str, tuple[float, float, float, float]] = {}
    if args.directory:
        present = dict(collect(Path(args.directory)))
    try:
        doc = census(profile, present)
    except ValueError as exc:
        print(f"error: {args.profile}: {exc}", file=sys.stderr)
        return 1
    if args.json is not None:
        text = json.dumps(doc, indent=2)
        if args.json == "-":
            print(text)
        else:
            Path(args.json).write_text(text + "\n", encoding="utf-8")
            print(f"report: {args.json}")
    else:
        print(fmt_cover(doc, show_all=args.all))
    return 0


def selftest() -> int:
    fails = 0

    def chk(cond: bool, msg: str) -> None:
        nonlocal fails
        if cond:
            print(f"  ok   {msg}")
        else:
            print(f"  FAIL {msg}")
            fails += 1

    print("mesh_grid selftest (synthetic, no vendor data)")

    # Tile box mapping stays pinned.
    lat_min, lat_max, lon_min, lon_max = tile_box("B48R058R.DAT")
    chk(abs(lat_min - 48.0) < 1e-9 and abs(lat_max - 53.3333333333) < 1e-6
        and abs(lon_min - 12.0) < 1e-9 and abs(lon_max - 20.0) < 1e-9,
        "B48R058R is 48.00..53.33 N, 12..20 E")

    ds = {"name": "dolnoslaskie-test",
          "region": {"name": "Dolnośląskie", "bbox": [14.0, 49.9, 17.9, 51.9]},
          "tiles": {"include": ["B48R058R"]}, "border_buffer_deg": 0.09}
    doc = census(ds, {"B48R058R.DAT": tile_box("B48R058R.DAT")})
    by = {row["tile"]: row for row in doc["rows"]}
    chk(by["B48R058R"]["class"] == "contained", "P0 tile B48R058R is contained")
    chk(doc["counts"]["contained"] == 1, "dolnoslaskie census has exactly one contained tile")
    chk(by["B48R058R"]["include"] is True, "include list marks B48R058R")
    chk(by["B48R058R"]["factory"] is True, "factory flag set for a present tile")

    # Edge tile: a box reaching past 51.9 N / 17.9 E is only intersected.
    edge = {"name": "edge", "region": {"bbox": [15.0, 50.0, 21.0, 51.0]},
            "border_buffer_deg": 0.0, "tiles": {"include": []}}
    edoc = census(edge, {})
    emap = {row["tile"]: row for row in edoc["rows"]}
    chk(emap["B48R058R"]["class"] == "intersects",
        "a region crossing a tile edge makes it intersect, not contained")
    chk(edoc["counts"]["contained"] == 0,
        "edge-box census has no contained tile")

    # Empty box (Atlantic): nothing intersects or is contained.
    atlantic = {"name": "atlantic", "region": {"bbox": [-30.0, 30.0, -20.0, 40.0]},
                "border_buffer_deg": 0.0, "tiles": {"include": []}}
    adoc = census(atlantic, {})
    chk(adoc["counts"]["contained"] == 0 and adoc["counts"]["intersects"] == 0,
        "Atlantic box selects nothing (negative control)")
    chk(adoc["counts"]["outside"] == adoc["lattice"],
        "every lattice tile is outside the Atlantic box")

    # Buffer test: region [12.5,49.0,19.5,53.0] sits inside B48R058R and stops
    # 0.5 deg short of B48R050R (lon 20..28). With no buffer B48R050R is
    # outside; a 0.45 deg buffer pads longitude by 0.45/cos(51 deg) ~ 0.715 deg
    # and reaches into it. Dropping the buffer/cos(mid) padding leaves this
    # green->red: the padded box would only reach 19.95 E, still short of 20.
    base = {"name": "buffer", "region": {"bbox": [12.5, 49.0, 19.5, 53.0]},
            "tiles": {"include": []}}
    n0 = {r["tile"]: r for r in census({**base, "border_buffer_deg": 0.0}, {})["rows"]}
    b45 = {r["tile"]: r for r in census({**base, "border_buffer_deg": 0.45}, {})["rows"]}
    chk(n0["B48R050R"]["class"] == "outside",
        "no buffer: B48R050R (lon 20..28) is outside a box ending at 19.5 E")
    chk(b45["B48R050R"]["class"] == "intersects",
        "0.45 deg buffer pads to ~20.22 E and makes B48R050R intersect")
    chk(b45["B48R058R"]["class"] == "contained",
        "the buffered box is still contained in B48R058R")

    # --all prints every lattice row; the default text table is filtered.
    chk(len(fmt_cover(doc).splitlines()) < len(fmt_cover(doc, show_all=True).splitlines()),
        "default table is filtered, --all is not")
    tile_rows = 0
    for line in fmt_cover(adoc, show_all=True).splitlines():
        fields = line.split()
        if fields and TILE_RE.match(fields[0] + ".DAT"):
            tile_rows += 1
    chk(tile_rows == 63, "--all prints all 63 lattice rows for a fully-outside profile")

    # A profile without region.bbox is refused loudly, never guessed.
    try:
        census({"name": "no-bbox", "tiles": {"include": ["B48R058R"]}}, {})
        chk(False, "missing region.bbox raises")
    except ValueError:
        chk(True, "missing region.bbox raises")

    # The lattice is the 63-cell EU grid, not the 45-file inventory.
    chk(len(lattice_names()) == 63, "lattice has 63 cells")

    print(f"selftest: {'OK' if not fails else 'FAIL'} ({fails} failure(s))")
    return 0 if not fails else 1


def cmd_list(args: argparse.Namespace) -> int:
    tiles = collect(Path(args.directory))
    if not tiles:
        print(f"error: no BxxRyyR.DAT tiles in {args.directory}", file=sys.stderr)
        return 1
    print(f"{'tile':<12s} {'latitude':>16s}  {'longitude':>18s}")
    for name, box in tiles:
        print(f"{name:<12s} {fmt_box(box)}")
    return 0


def cmd_matrix(args: argparse.Namespace) -> int:
    tiles = collect(Path(args.directory))
    if not tiles:
        print(f"error: no BxxRyyR.DAT tiles in {args.directory}", file=sys.stderr)
        return 1
    rows = sorted({int(TILE_RE.match(n).group(1), 16) for n, _ in tiles})
    cols = sorted({int(TILE_RE.match(n).group(2), 16) for n, _ in tiles})
    present = {n for n, _ in tiles}
    header = "      " + "".join(f"{c:>7X}" for c in cols)
    print(header)
    for b in rows:
        line = f"B{b:02X}   "
        for r in cols:
            name = f"B{b:02X}R{r:03X}R.DAT"
            line += f"{'X' if name in present else '.':>7s}"
        print(line)
    return 0


def cmd_cell(args: argparse.Namespace) -> int:
    name = args.name
    if not name.upper().endswith(".DAT"):
        name += ".DAT"
    # Accept both B48R058 and the full B48R058R.DAT form.
    if not name.upper().endswith("R.DAT"):
        name = name[:-4] + "R.DAT"
    try:
        box = tile_box(name)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{name}: {fmt_box(box)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list every tile with its lat/lon box")
    p_list.add_argument("directory")
    p_list.set_defaults(func=cmd_list)

    p_matrix = sub.add_parser("matrix", help="print the present/absent tile matrix")
    p_matrix.add_argument("directory")
    p_matrix.set_defaults(func=cmd_matrix)

    p_cell = sub.add_parser("cell", help="print one tile's lat/lon box")
    p_cell.add_argument("name", help="e.g. B48R060 or B48R060R.DAT")
    p_cell.set_defaults(func=cmd_cell)

    p_cover = sub.add_parser(
        "cover", help="census: classify every lattice tile against a profile's region")
    p_cover.add_argument("profile", help="a build profile JSON (region.bbox)")
    p_cover.add_argument("directory", nargs="?",
                         help="MAPAL001 directory for the factory-present flag (optional)")
    p_cover.add_argument("--all", action="store_true",
                         help="print all 63 lattice rows (default: non-outside + included)")
    p_cover.add_argument("--json", nargs="?", const="-", default=None, metavar="PATH")
    p_cover.set_defaults(func=cmd_cover)

    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv == ["--selftest"]:
        return selftest()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
