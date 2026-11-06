#!/usr/bin/env python3
"""Convert WGS84 latitude/longitude to and from the ZE0 map grid.

Coordinate spaces
-----------------

**1. Global packed ``u16`` pair ``(x, y)``** -- what `COORD001` region
bounding boxes, `POINT`/`ADDRE` ids and the `MAPAL001` stream keys store::

    x = 32768 + lat * 192          # 192 units per degree of latitude
    y = origin + lon * 128         # 128 units per degree of longitude

One packed unit is 1/192 deg latitude and 1/128 deg longitude (about 600 m).
A `BxxRyyR` cell spans exactly **1024 packed units on both axes**, because
8 grid units of 2/3 deg = 5.333 deg = 1024 / 192, and 8 grid units of 1 deg =
8 deg = 1024 / 128.

**2. Tile-local ``0..2047``** -- the firmware's 11-bit intra-mesh coordinate
(`RGD_JLocGet : t_start_x = 0,2047`).  A cell spans 2048 local units, so the
natural mapping is two local units per packed unit::

    local_x = 2 * (x - x0)         # x0 = 32768 + int(B,16) * 128
    local_y = 2 * (y - y0)         # y0 = origin + lon_min * 128

Every point strictly inside the cell is `0..2047`; the far edge is 2048 and
belongs to the next cell.  The factor 2 is a **HYPOTHESIS**: it is the only
simple mapping that explains why the runtime bound is 2047 rather than 1023,
but no byte-level sample has pinned it yet.  `--local-scale 1` tests the
alternative packed-relative form (`0..1023`).  Local coordinates do not
depend on the longitude origin; packed ``y`` does.

**3. Mesh cell** -- `BxxRyyR`, the 8 x 8 grid-unit file.  Its B and R digits
are hexadecimal.  The per-tile files carry the finest (level 6) data;
`LEV3456R.DAT` also holds coarse levels 3--5.  The subdivision of those
levels is UNKNOWN, so this tool exposes only the documented level 6 cell.

Longitude origins
-----------------

Two origins are in use and must not be mixed:

======  =======  ============================================================
origin  alias    used by
======  =======  ============================================================
52742   coord    `COORD001` bounding boxes, `POINT`/`ADDRE` ids (C-111)
52736   tile     `MAPAL001` zlib stream key ``B`` (C-048)
======  =======  ============================================================

The 6-unit difference is 6/128 deg = 0.046875 deg (about 3.5 km at 48 N) and
is unexplained (C-053).  Decoding a POI id with 52736 moves it 0.047 deg east;
encoding a stream key with 52742 moves it 0.047 deg west.  The default is
52742 because the documented `POINT`/`COORD001` examples use it.

Quantisation
------------

Stored coordinates are integers.  Encoding rounds to the nearest packed unit
(half up), so the worst-case round-trip error is half a packed unit:
1/384 deg latitude and 1/256 deg longitude (about 290 m each).  Local
coordinates at scale 2 have half that step.  Exact integer ``(x, y)`` and
integer local pairs round-trip exactly.

Usage::

    python3 tools/coord.py cell 51.1 17.03
    python3 tools/coord.py xy 43.7447916667 7.4296875 --cell B40R060R
    python3 tools/coord.py xy 43.7447916667 7.4296875 --origin tile
    python3 tools/coord.py latlon 41167 53693 --cell B40R060R
    python3 tools/coord.py latlon 414 878 --local --cell B40R060R
    python3 tools/coord.py bbox B48R058R
    python3 tools/coord.py levels
    python3 tools/coord.py --selftest

Formulas verified in `docs/format/map-tiles.md` and
`docs/format/coord-zcode-icode.md`; tool and self-test in
`docs/experiments/EXP-2026-11-06-M4.8-coord.md`.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Grid constants
# --------------------------------------------------------------------------

LAT_ORIGIN = 32768
LAT_SCALE = 192             # packed units per degree of latitude
LON_SCALE = 128             # packed units per degree of longitude

LON_ORIGIN_COORD = 52742    # COORD001, POINT, ADDRE
LON_ORIGIN_TILE = 52736     # MAPAL001 stream key B
ORIGIN_LABEL = {LON_ORIGIN_COORD: "coord", LON_ORIGIN_TILE: "tile"}
ORIGIN_DETAIL = {
    LON_ORIGIN_COORD: "COORD001 boxes and POINT/ADDRE ids",
    LON_ORIGIN_TILE: "MAPAL001 zlib stream key B",
}
ORIGIN_CHOICES = (LON_ORIGIN_COORD, LON_ORIGIN_TILE)
DEFAULT_ORIGIN = LON_ORIGIN_COORD

GRID_LAT_DEG = 2.0 / 3.0    # one grid unit of latitude
GRID_LON_DEG = 1.0          # one grid unit of longitude
CELL_GRID_UNITS = 8         # a BxxRyyR cell is 8 x 8 grid units
CELL_PACKED_UNITS = 1024    # 8 * 128 (lat) and 8 * 128 (lon): both axes
LOCAL_SPAN = 2 * CELL_PACKED_UNITS   # 2048 local units per cell axis
LOCAL_MAX = LOCAL_SPAN - 1           # 2047, the firmware 11-bit bound
DEFAULT_LOCAL_SCALE = 2             # local units per packed unit (hypothesis)
EPS = 1e-9                          # float noise on exact cell boundaries

#: The 2011 EU tile space: B28--B68, R048--R078, step 8 (C-566).
SHIPPED_B = tuple(range(0x28, 0x69, 8))
SHIPPED_R = tuple(range(0x48, 0x79, 8))

#: 2011 US / N-America tile space: 112 files, R in 0x0A0..0x110 (lon_max
#: 108-R gives −172..−52), B in 0x18..0x70. Not a full rectangle (gaps, plus
#: Hawaii/Alaska). The per-tile box formula and packed/local formulas are
#: identical to EU; only the lattice and longitudes differ (EXP-…-M4.8c).
US_TILE_COUNT = 112

TILE_RE = re.compile(r"^B([0-9A-F]{2})R([0-9A-F]{3})R?$")

LEVEL_CELL = 6
LEVEL_NOTE = (
    "level 6 is the finest storage level and is carried by the per-tile "
    "BxxRyyR files (and by LEV3456R.DAT); levels 3-5 are coarse overviews "
    "in LEV3456R.DAT whose cell subdivision is UNKNOWN"
)

# --------------------------------------------------------------------------
# Cell names
# --------------------------------------------------------------------------


def parse_cell(name: str) -> str:
    """Normalise ``B48R058``, ``B48R058R`` or ``B48R058R.DAT`` to a cell."""
    text = str(name).strip().upper()
    if text.endswith(".DAT"):
        text = text[:-4]
    match = TILE_RE.match(text)
    if not match:
        raise ValueError(f"not a BxxRyyR cell name: {name!r}")
    return f"B{int(match.group(1), 16):02X}R{int(match.group(2), 16):03X}R"


def cell_digits(cell: str) -> tuple[int, int]:
    """Return the integer ``(B, R)`` of a normalised cell name."""
    match = TILE_RE.match(parse_cell(cell))
    assert match is not None
    return int(match.group(1), 16), int(match.group(2), 16)


def is_cell_start(cell: str) -> bool:
    """Whether B and R are multiples of 8, i.e. a real 8 x 8 cell."""
    b, r = cell_digits(cell)
    return b % CELL_GRID_UNITS == 0 and r % CELL_GRID_UNITS == 0


def in_shipped_lattice(cell: str) -> bool:
    """Whether the cell is one of the 63 addressable 2011 EU lattice cells."""
    b, r = cell_digits(cell)
    return b in SHIPPED_B and r in SHIPPED_R


def cell_box(cell: str) -> tuple[float, float, float, float]:
    """Return ``(lat_min, lat_max, lon_min, lon_max)`` of a cell.

    The formula is the one verified in `docs/format/map-tiles.md`::

        lat_min = int(B, 16) * 2/3
        lon_max = 108 - int(R, 16)
        both spans are 8 grid units

    A cell name that is not a multiple of 8 is still expanded as an 8-unit
    box for diagnostics; callers can test :func:`is_cell_start`.
    """
    b, r = cell_digits(cell)
    lat_min = b * GRID_LAT_DEG
    lon_max = 108.0 - r * GRID_LON_DEG
    return (
        lat_min,
        lat_min + CELL_GRID_UNITS * GRID_LAT_DEG,
        lon_max - CELL_GRID_UNITS * GRID_LON_DEG,
        lon_max,
    )


def cell_for(lat: float, lon: float) -> str:
    """Return the BxxRyyR cell that contains ``(lat, lon)``.

    Cells are half-open: ``[lat_min, lat_max)`` and ``[lon_min, lon_max)``.
    """
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise ValueError("coordinate is not finite")
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError("coordinate outside WGS84 range")
    b = CELL_GRID_UNITS * math.floor(
        lat * 3.0 / (2.0 * CELL_GRID_UNITS) + EPS
    )
    steps = math.ceil((108.0 - lon) / CELL_GRID_UNITS - EPS)
    r = CELL_GRID_UNITS * (steps - 1)
    if not (0 <= b <= 0xF8 and 0 <= r <= 0x400):
        raise ValueError(f"no BxxRyyR cell for lat={lat} lon={lon}")
    return f"B{b:02X}R{r:03X}R"


def cell_contains(cell: str, lat: float, lon: float) -> bool:
    lat_min, lat_max, lon_min, lon_max = cell_box(cell)
    return lat_min <= lat < lat_max and lon_min <= lon < lon_max


# --------------------------------------------------------------------------
# Packed global coordinates
# --------------------------------------------------------------------------


def check_origin(origin: int) -> int:
    if origin not in ORIGIN_CHOICES:
        raise ValueError(
            f"unknown longitude origin {origin!r}; use 52742 (coord) or "
            "52736 (tile)"
        )
    return origin


def _round(value: float) -> int:
    """Round half up to the nearest integer (stored coordinates)."""
    return int(math.floor(value + 0.5))


def latlon_to_xy(lat: float, lon: float, origin: int = DEFAULT_ORIGIN) -> tuple[int, int]:
    """Encode ``(lat, lon)`` as the global packed ``(x, y)`` pair."""
    check_origin(origin)
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise ValueError("coordinate is not finite")
    x = _round(LAT_ORIGIN + lat * LAT_SCALE)
    y = _round(origin + lon * LON_SCALE)
    if not (0 <= x <= 0xFFFF and 0 <= y <= 0xFFFF):
        raise ValueError(f"packed coordinate does not fit u16: x={x} y={y}")
    return x, y


def xy_to_latlon(x: float, y: float, origin: int = DEFAULT_ORIGIN) -> tuple[float, float]:
    """Decode a global packed ``(x, y)`` pair to ``(lat, lon)``."""
    check_origin(origin)
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError("coordinate is not finite")
    return (x - LAT_ORIGIN) / LAT_SCALE, (y - origin) / LON_SCALE


def packed_origin(
    cell: str, origin: int = DEFAULT_ORIGIN
) -> tuple[int, int]:
    """Return the packed coordinate of the cell's south-west corner.

    ``x0 = 32768 + B * 128`` because ``B * 2/3 * 192 == B * 128``;
    ``y0 = origin + (100 - R) * 128`` because ``lon_min = 108 - R - 8``.
    """
    check_origin(origin)
    b, r = cell_digits(cell)
    return LAT_ORIGIN + b * 128, origin + (100 - r) * 128


def packed_bounds(cell: str, origin: int = DEFAULT_ORIGIN) -> dict[str, int]:
    x0, y0 = packed_origin(cell, origin)
    return {
        "x0": x0,
        "x1": x0 + CELL_PACKED_UNITS,
        "y0": y0,
        "y1": y0 + CELL_PACKED_UNITS,
    }


# --------------------------------------------------------------------------
# Tile-local 0..2047 coordinates
# --------------------------------------------------------------------------


def xy_to_local(
    x: int,
    y: int,
    cell: str,
    origin: int = DEFAULT_ORIGIN,
    scale: int = DEFAULT_LOCAL_SCALE,
) -> tuple[int, int]:
    """Convert a packed pair into tile-local coordinates (integer)."""
    if scale not in (1, 2):
        raise ValueError("local scale must be 1 or 2")
    x0, y0 = packed_origin(cell, origin)
    return scale * (x - x0), scale * (y - y0)


def local_to_xy(
    cell: str,
    lx: float,
    ly: float,
    origin: int = DEFAULT_ORIGIN,
    scale: int = DEFAULT_LOCAL_SCALE,
) -> tuple[float, float]:
    """Convert tile-local coordinates into packed coordinates (exact float)."""
    if scale not in (1, 2):
        raise ValueError("local scale must be 1 or 2")
    x0, y0 = packed_origin(cell, origin)
    return x0 + lx / scale, y0 + ly / scale


def latlon_to_local(
    lat: float,
    lon: float,
    cell: str,
    scale: int = DEFAULT_LOCAL_SCALE,
) -> tuple[int, int]:
    """Encode ``(lat, lon)`` as integer tile-local coordinates."""
    if scale not in (1, 2):
        raise ValueError("local scale must be 1 or 2")
    lat_min, _, lon_min, _ = cell_box(cell)
    return (
        _round(scale * LAT_SCALE * (lat - lat_min)),
        _round(scale * LON_SCALE * (lon - lon_min)),
    )


def local_to_latlon(
    cell: str, lx: float, ly: float, scale: int = DEFAULT_LOCAL_SCALE
) -> tuple[float, float]:
    """Decode tile-local coordinates to ``(lat, lon)``."""
    if scale not in (1, 2):
        raise ValueError("local scale must be 1 or 2")
    lat_min, _, lon_min, _ = cell_box(cell)
    return lat_min + lx / (scale * LAT_SCALE), lon_min + ly / (scale * LON_SCALE)


def local_in_bounds(lx: float, ly: float, scale: int = DEFAULT_LOCAL_SCALE) -> bool:
    """Whether a local pair is inside the firmware's 0..2047 runtime bound."""
    limit = scale * CELL_PACKED_UNITS - 1   # 2047 at scale 2, 1023 at scale 1
    return 0 <= lx <= limit and 0 <= ly <= limit


def local_report(cell: str, lx: float, ly: float, scale: int) -> dict[str, Any]:
    return {
        "x": lx,
        "y": ly,
        "scale": scale,
        "max": scale * CELL_PACKED_UNITS - 1,
        "span": scale * CELL_PACKED_UNITS,
        "in_bounds": local_in_bounds(lx, ly, scale),
    }


# --------------------------------------------------------------------------
# Command results
# --------------------------------------------------------------------------


def cell_result(
    cell: str, origin: int = DEFAULT_ORIGIN, scale: int = DEFAULT_LOCAL_SCALE
) -> dict[str, Any]:
    box = cell_box(cell)
    bounds = packed_bounds(cell, origin)
    return {
        "cell": cell,
        "level": LEVEL_CELL,
        "level_status": "HYPOTHESIS (level number only)",
        "cell_start": is_cell_start(cell),
        "shipped_lattice": in_shipped_lattice(cell),
        "box": {
            "lat_min": box[0],
            "lat_max": box[1],
            "lon_min": box[2],
            "lon_max": box[3],
        },
        "packed": {
            "origin": origin,
            "origin_name": ORIGIN_LABEL[origin],
            **bounds,
        },
        "local": {
            "scale": scale,
            "min": 0,
            "max": scale * CELL_PACKED_UNITS - 1,
            "span": scale * CELL_PACKED_UNITS,
        },
    }


def xy_result(
    lat: float,
    lon: float,
    origin: int,
    cell: str | None,
    scale: int,
) -> dict[str, Any]:
    derived = cell_for(lat, lon)
    if cell is not None:
        cell = parse_cell(cell)
        if not cell_contains(cell, lat, lon):
            raise ValueError(
                f"lat={lat} lon={lon} is outside {cell} "
                f"({cell_box(cell)}); derived cell is {derived}"
            )
    else:
        cell = derived
    x, y = latlon_to_xy(lat, lon, origin)
    x0, y0 = packed_origin(cell, origin)
    lx, ly = xy_to_local(x, y, cell, origin, scale)
    return {
        "lat": lat,
        "lon": lon,
        "cell": cell,
        "level": LEVEL_CELL,
        "origin": origin,
        "origin_name": ORIGIN_LABEL[origin],
        "x": x,
        "y": y,
        "tile_origin": {"x": x0, "y": y0},
        "local": local_report(cell, lx, ly, scale),
    }


def latlon_result(
    x: float,
    y: float,
    origin: int,
    cell: str | None,
    local: bool,
    scale: int,
) -> dict[str, Any]:
    if local:
        if cell is None:
            raise ValueError("--local needs --cell (a local pair has no cell)")
        cell = parse_cell(cell)
        lat, lon = local_to_latlon(cell, x, y, scale)
        inside = cell_contains(cell, lat, lon)
        packed_x, packed_y = latlon_to_xy(lat, lon, origin)
        lx, ly = x, y
        in_cell = inside
    else:
        lat, lon = xy_to_latlon(x, y, origin)
        derived = cell_for(lat, lon)
        if cell is not None:
            cell = parse_cell(cell)
            if not cell_contains(cell, lat, lon):
                raise ValueError(
                    f"x={x} y={y} decodes to lat={lat} lon={lon}, outside "
                    f"{cell}; derived cell is {derived}"
                )
        else:
            cell = derived
        packed_x, packed_y = x, y
        lx, ly = latlon_to_local(lat, lon, cell, scale)
        in_cell = cell_contains(cell, lat, lon)
    result: dict[str, Any] = {
        "lat": lat,
        "lon": lon,
        "cell": cell,
        "level": LEVEL_CELL,
        "origin": origin,
        "origin_name": ORIGIN_LABEL[origin],
        "local": local_report(cell, lx, ly, scale),
        "local_input": local,
        "in_cell": in_cell,
    }
    if local:
        result["x"] = packed_x
        result["y"] = packed_y
    else:
        result["x"] = x
        result["y"] = y
    return result


def bbox_result(cell: str, scale: int) -> dict[str, Any]:
    cell = parse_cell(cell)
    base = cell_result(cell, DEFAULT_ORIGIN, scale)
    base["packed_by_origin"] = {
        str(origin): {
            "name": ORIGIN_LABEL[origin],
            "used_by": ORIGIN_DETAIL[origin],
            **packed_bounds(cell, origin),
        }
        for origin in ORIGIN_CHOICES
    }
    return base


def levels_result() -> dict[str, Any]:
    return {
        "level_cell": LEVEL_CELL,
        "note": LEVEL_NOTE,
        "levels": [
            {
                "level": 6,
                "source": "BxxRyyR.DAT (per tile) and LEV3456R.DAT",
                "cell": "8 x 8 grid units = 1024 packed = 2048 local units",
                "status": "OBSERVED (level number is a HYPOTHESIS)",
            },
            {
                "level": 5,
                "source": "LEV3456R.DAT",
                "cell": "UNKNOWN (coarse overview; not modelled)",
                "status": "UNKNOWN",
            },
            {
                "level": 4,
                "source": "LEV3456R.DAT",
                "cell": "UNKNOWN (coarse overview; not modelled)",
                "status": "UNKNOWN",
            },
            {
                "level": 3,
                "source": "LEV3456R.DAT",
                "cell": "UNKNOWN (coarse overview; not modelled)",
                "status": "UNKNOWN",
            },
        ],
        "zoom": (
            "no verified zoom-number <-> level mapping; the firmware six-level "
            "table (L1..L6) is a storage LOD, not a rendering zoom index"
        ),
        "bbox_table": (
            "0x2ac entries are (level, flags, lat_top, lat_bottom, lon_left, "
            "lon_right) in signed arc-minutes per tile; parse them from a "
            "tile, not from a coordinate"
        ),
    }


# --------------------------------------------------------------------------
# CLI formatting
# --------------------------------------------------------------------------


def fmt_box(box: dict[str, float]) -> str:
    return (
        f"{box['lat_min']:.6f}..{box['lat_max']:.6f} N  "
        f"{box['lon_min']:.6f}..{box['lon_max']:.6f} E"
    )


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2))


def cmd_cell(args: argparse.Namespace) -> int:
    cell = cell_for(args.lat, args.lon)
    result = cell_result(cell, DEFAULT_ORIGIN, args.local_scale)
    if args.json:
        print_json({"command": "cell", "lat": args.lat, "lon": args.lon, **result})
        return 0
    print(f"lat {args.lat:.6f}  lon {args.lon:.6f}")
    print(f"cell {cell}  (level {LEVEL_CELL})")
    print(f"box  {fmt_box(result['box'])}")
    state = "EU shipped lattice" if result["shipped_lattice"] else "outside the EU shipped lattice"
    print(f"lattice: {state} (EU 2011: rows B28-B68, columns R048-R078, step 8)")
    if not result["cell_start"]:
        print("warning: B/R are not multiples of 8, not an 8 x 8 cell")
    return 0


def cmd_xy(args: argparse.Namespace) -> int:
    result = xy_result(args.lat, args.lon, args.origin, args.cell, args.local_scale)
    if args.json:
        print_json({"command": "xy", **result})
        return 0
    print(f"lat {result['lat']:.6f}  lon {result['lon']:.6f} -> {result['cell']}")
    print(
        f"origin {result['origin']} ({result['origin_name']}: "
        f"{ORIGIN_DETAIL[result['origin']]})"
    )
    print(f"global x {result['x']}  y {result['y']}")
    print(
        f"tile origin x {result['tile_origin']['x']}  "
        f"y {result['tile_origin']['y']}"
    )
    local = result["local"]
    state = "in bounds" if local["in_bounds"] else "OUT OF BOUNDS"
    print(
        f"local x {local['x']}  y {local['y']}  "
        f"(0..{local['max']}, scale {local['scale']})  {state}"
    )
    return 0


def cmd_latlon(args: argparse.Namespace) -> int:
    result = latlon_result(
        args.x, args.y, args.origin, args.cell, args.local, args.local_scale
    )
    if args.json:
        print_json({"command": "latlon", **result})
        return 0
    if result["local_input"]:
        print(
            f"local x {result['local']['x']:g}  y {result['local']['y']:g} "
            f"for {result['cell']} (scale {result['local']['scale']})"
        )
        print(
            f"global x {result['x']}  y {result['y']}  "
            f"origin {result['origin']} ({result['origin_name']})"
        )
    else:
        print(
            f"global x {result['x']:g}  y {result['y']:g}  "
            f"origin {result['origin']} ({result['origin_name']})"
        )
    print(f"lat {result['lat']:.6f}  lon {result['lon']:.6f}")
    print(f"cell {result['cell']}  (level {LEVEL_CELL})")
    local = result["local"]
    if not result["local_input"]:
        state = "in bounds" if local["in_bounds"] else "OUT OF BOUNDS"
        print(
            f"local x {local['x']:g}  y {local['y']:g}  "
            f"(0..{local['max']}, scale {local['scale']})  {state}"
        )
    if not result["in_cell"]:
        print("warning: point is outside the named cell (half-open edges)")
    return 0


def cmd_bbox(args: argparse.Namespace) -> int:
    result = bbox_result(args.cell, args.local_scale)
    if args.json:
        print_json({"command": "bbox", **result})
        return 0
    print(f"{result['cell']}  (level {LEVEL_CELL}; level number is a hypothesis)")
    print(f"box {fmt_box(result['box'])}")
    print(
        f"packed x {result['packed']['x0']}..{result['packed']['x1']}  "
        f"(1024 units)"
    )
    for origin in ORIGIN_CHOICES:
        entry = result["packed_by_origin"][str(origin)]
        print(
            f"packed y @{origin} ({entry['name']}: {entry['used_by']}) "
            f"{entry['y0']}..{entry['y1']}"
        )
    print(
        f"local 0..{result['local']['span']} per axis at scale "
        f"{result['local']['scale']} (0..{result['local']['max']} strictly inside)"
    )
    print(f"level: {LEVEL_NOTE}")
    if not result["shipped_lattice"]:
        print("lattice: not one of the 63 shipped 2011 EU cells")
    return 0


def cmd_levels(args: argparse.Namespace) -> int:
    result = levels_result()
    if args.json:
        print_json({"command": "levels", **result})
        return 0
    print(f"finest storage level: {result['level_cell']}")
    for entry in result["levels"]:
        print(f"  level {entry['level']}: {entry['source']}")
        print(f"    cell: {entry['cell']}  [{entry['status']}]")
    print(f"zoom: {result['zoom']}")
    print(f"bbox table: {result['bbox_table']}")
    return 0


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------


def selftest() -> int:
    """Synthetic checks: documented boxes, formulas, fixtures, round-trips."""
    failures: list[str] = []
    count = 0

    def check(name: str, condition: bool, detail: str = "") -> None:
        nonlocal count
        count += 1
        print(f"  {name:<38} {'OK' if condition else 'FAIL'} {detail}".rstrip())
        if not condition:
            failures.append(name)

    # 1. Documented boxes (docs/format/map-tiles.md table and the 0x2ac sample).
    documented = {
        "B48R058R": (48.0, 160.0 / 3.0, 12.0, 20.0),
        "B40R060R": (128.0 / 3.0, 48.0, 4.0, 12.0),
        "B58R070R": (176.0 / 3.0, 64.0, -12.0, -4.0),
        "B30R048R": (32.0, 112.0 / 3.0, 28.0, 36.0),
        "B68R058R": (208.0 / 3.0, 224.0 / 3.0, 12.0, 20.0),
        "B28R070R": (80.0 / 3.0, 32.0, -12.0, -4.0),
    }
    boxes_ok = True
    for name, expected in documented.items():
        got = cell_box(name)
        if any(abs(a - b) > 1e-9 for a, b in zip(got, expected)):
            boxes_ok = False
    check("documented cell boxes", boxes_ok, f"{len(documented)} cells")

    # 2. Agreement with tools/mesh_grid.py over the full shipped lattice.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import mesh_grid  # noqa: E402

        grid_ok = all(
            cell_box(f"B{b:02X}R{r:03X}R")
            == mesh_grid.tile_box(f"B{b:02X}R{r:03X}R.DAT")
            for b in SHIPPED_B
            for r in SHIPPED_R
        )
        mesh_detail = f"{len(SHIPPED_B) * len(SHIPPED_R)} cells"
    except Exception as exc:  # pragma: no cover - import should work
        grid_ok = False
        mesh_detail = f"mesh_grid unavailable: {exc}"
    check("mesh_grid agreement", grid_ok, mesh_detail)

    # 3. Cell corners map to the packed origin and origin + 1024.
    corner_ok = True
    for cell in documented:
        lat_min, lat_max, lon_min, lon_max = cell_box(cell)
        for origin in ORIGIN_CHOICES:
            x0, y0 = packed_origin(cell, origin)
            if latlon_to_xy(lat_min, lon_min, origin) != (x0, y0):
                corner_ok = False
            x1, y1 = latlon_to_xy(lat_max, lon_max, origin)
            if (x1, y1) != (x0 + CELL_PACKED_UNITS, y0 + CELL_PACKED_UNITS):
                corner_ok = False
    check("corners -> packed origin + 1024", corner_ok)

    # 4. Global integer (x, y) round-trips exactly, both origins.
    pairs = [(32768, 52742), (41167, 53693), (41155, 53681),
             (43008, 55302), (40000, 50000), (38000, 56000), (35000, 61000)]
    xy_ok = True
    for origin in ORIGIN_CHOICES:
        for x, y in pairs:
            lat, lon = xy_to_latlon(x, y, origin)
            if latlon_to_xy(lat, lon, origin) != (x, y):
                xy_ok = False
    check("global (x,y) round-trip", xy_ok, f"{len(pairs)} pairs x 2 origins")

    # 5. Documented POI fixture: POINT017 "AUTO KONCEPT", Monaco, A copy.
    #    id a0cfd1bd -> x=0xa0cf=41167, y=0xd1bd=53693 (C-150/C-211, EXP-08).
    ax, ay = 0xA0CF, 0xD1BD
    alat, alon = xy_to_latlon(ax, ay, LON_ORIGIN_COORD)
    cell_a = cell_for(alat, alon)
    lx, ly = latlon_to_local(alat, alon, cell_a)
    check(
        "POI fixture A (a0cfd1bd)",
        abs(alat - 43.7447916667) < 1e-9
        and abs(alon - 7.4296875) < 1e-9
        and cell_a == "B40R060R"
        and (lx, ly) == (414, 878),
        f"lat={alat:.7f} lon={alon:.7f} cell={cell_a} local=({lx},{ly})",
    )
    bx, by = 0xA0C3, 0xD1B1
    blat, blon = xy_to_latlon(bx, by, LON_ORIGIN_COORD)
    cell_b = cell_for(blat, blon)
    lx_b, ly_b = latlon_to_local(blat, blon, cell_b)
    check(
        "POI fixture B (a0c3d1b1)",
        abs(blat - 43.6822916667) < 1e-9
        and abs(blon - 7.3359375) < 1e-9
        and cell_b == "B40R060R"
        and (lx_b, ly_b) == (390, 854),
        f"lat={blat:.7f} lon={blon:.7f} local=({lx_b},{ly_b})",
    )

    # 6. Cell-boundary fixtures from EXP-2026-11-05-44.
    boundary = [
        (51.1, 19.999, "B48R058R"),
        (51.1, 20.001, "B48R050R"),
        (51.1, 20.0, "B48R050R"),
        (51.1, 12.0, "B48R058R"),
        (51.1, 11.999, "B48R060R"),
    ]
    check(
        "cell boundary fixtures",
        all(cell_for(lat, lon) == want for lat, lon, want in boundary),
        "half-open edges",
    )

    # 7. The fixtures already used by tools/imf_check.py.
    imf = {
        "B48R058R": (51.11, 17.03),
        "B48R050R": (51.10, 20.001),
        "B28R070R": (28.5, -5.0),
        "B58R070R": (60.0, -6.0),
        "B68R058R": (70.0, 14.0),
    }
    check(
        "imf_check fixtures",
        all(cell_for(lat, lon) == want for want, (lat, lon) in imf.items()),
        f"{len(imf)} points",
    )

    # 8. The 6-unit origin difference is exactly 0.046875 deg of longitude.
    lon_coord = xy_to_latlon(41167, 53693, LON_ORIGIN_COORD)[1]
    lon_tile = xy_to_latlon(41167, 53693, LON_ORIGIN_TILE)[1]
    check(
        "52742 vs 52736 = 6/128 deg",
        abs(abs(lon_coord - lon_tile) - 0.046875) < 1e-12,
        f"{lon_coord:.7f} vs {lon_tile:.7f}",
    )

    # 9. Local integer pairs round-trip exactly through lat/lon.
    local_ok = True
    for cell in ("B48R058R", "B40R060R", "B28R070R", "B68R058R"):
        for scale in (1, 2):
            limit = scale * CELL_PACKED_UNITS - 1
            for lx, ly in ((0, 0), (limit, limit), (1, 1), (511, 1023)):
                lat, lon = local_to_latlon(cell, lx, ly, scale)
                if latlon_to_local(lat, lon, cell, scale) != (lx, ly):
                    local_ok = False
    check("local -> latlon -> local round-trip", local_ok, "4 cells x 2 scales")

    # 10. packed -> local -> packed round-trips exactly (local is even at scale 2).
    packed_ok = True
    for origin in ORIGIN_CHOICES:
        x0, y0 = packed_origin("B48R058R", origin)
        for dx, dy in ((0, 0), (1, 1), (1023, 1023), (512, 768)):
            x, y = x0 + dx, y0 + dy
            lx, ly = xy_to_local(x, y, "B48R058R", origin)
            lx_r, ly_r = local_to_xy("B48R058R", lx, ly, origin)
            if (lx_r, ly_r) != (x, y):
                packed_ok = False
    check("packed -> local -> packed round-trip", packed_ok)

    # 11. Bounds: 2047 is the last inside value at scale 2; 2048 is the edge.
    check(
        "0..2047 local bound",
        local_in_bounds(0, 0)
        and local_in_bounds(2047, 2047)
        and not local_in_bounds(2048, 0)
        and not local_in_bounds(0, 2048)
        and not local_in_bounds(-1, 0)
        and local_in_bounds(1023, 1023, scale=1)
        and not local_in_bounds(1024, 1024, scale=1),
    )

    # 12. All 63 lattice cells are found by their own midpoint.
    cells_ok = all(
        cell_for(
            (cell_box(f"B{b:02X}R{r:03X}R")[0] + cell_box(f"B{b:02X}R{r:03X}R")[1]) / 2,
            (cell_box(f"B{b:02X}R{r:03X}R")[2] + cell_box(f"B{b:02X}R{r:03X}R")[3]) / 2,
        )
        == f"B{b:02X}R{r:03X}R"
        for b in SHIPPED_B
        for r in SHIPPED_R
    )
    check(
        "lattice midpoint -> cell",
        cells_ok,
        f"{len(SHIPPED_B) * len(SHIPPED_R)} cells (C-566)",
    )

    # 13. The documented 0x2ac sample box lies inside B28R070R.
    #     B28R070R 0x2ac arc-minutes: 0x0780=1920', 0x0695=1685',
    #     0xfd30=-720', 0xfdce=-562' (docs/format/map-tiles.md).
    lat_min, lat_max, lon_min, lon_max = cell_box("B28R070R")
    sample_ok = (
        lat_min - EPS <= 1685 / 60.0 < 1920 / 60.0 <= lat_max + EPS
        and lon_min - EPS <= -720 / 60.0 < -562 / 60.0 <= lon_max + EPS
    )
    check("0x2ac sample inside B28R070R", sample_ok, "28.08..32.00 N, -12..-9.37 E")

    # 14. A non-cell R is reported as such, not silently accepted.
    check(
        "R057 is not a cell start",
        not is_cell_start("B48R057R") and is_cell_start("B48R058R"),
    )

    # 15. US grid (EXP-…-M4.8c): R >= 0xA0 gives lon_max = 108-R < 0 (negative
    #     longitudes). Same formula, 3-digit R, B/R multiples of 8.
    us_boxes = {
        "B38R0B0R": (37.0 + 1.0 / 3.0, 42.0 + 2.0 / 3.0, -76.0, -68.0),
        "B38R0B8R": (37.0 + 1.0 / 3.0, 42.0 + 2.0 / 3.0, -84.0, -76.0),
        "B38R0E0R": (37.0 + 1.0 / 3.0, 42.0 + 2.0 / 3.0, -124.0, -116.0),
        "B40R0E0R": (42.0 + 2.0 / 3.0, 48.0, -124.0, -116.0),
        "B38R0C0R": (37.0 + 1.0 / 3.0, 42.0 + 2.0 / 3.0, -92.0, -84.0),
        "B18R100R": (16.0, 21.0 + 1.0 / 3.0, -156.0, -148.0),  # Hawaii
        "B48R110R": (48.0, 53.0 + 1.0 / 3.0, -172.0, -164.0),  # Aleutians
    }
    us_boxes_ok = all(
        all(abs(a - b) < 1e-9 for a, b in zip(cell_box(n), exp))
        and is_cell_start(n)
        and not in_shipped_lattice(n)
        for n, exp in us_boxes.items()
    )
    check("US cell boxes (R>=0xA0, neg lon)", us_boxes_ok, f"{len(us_boxes)} cells")

    # 16. US landmarks (Wikipedia coords, not OSM) -> correct tile/cell, inside
    #     box, local in bounds, packed round-trip error < 350 m (quantisation).
    us_landmarks = [
        # (name, lat, lon, cell, local_x_s2, local_y_s2)
        ("Statue of Liberty", 40.689249, -74.044500, "B38R0B0R", 1289, 501),
        ("White House", 38.897676, -77.036530, "B38R0B8R", 601, 1783),
        ("Golden Gate Bridge", 37.819929, -122.478255, "B38R0E0R", 187, 390),
        ("Space Needle", 47.620506, -122.349277, "B40R0E0R", 1902, 423),
        ("Willis Tower", 41.878876, -87.635915, "B38R0C0R", 1745, 1117),
    ]
    us_lm_ok = True
    for _, lat, lon, want, lx_w, ly_w in us_landmarks:
        cell = cell_for(lat, lon)
        x, y = latlon_to_xy(lat, lon, LON_ORIGIN_COORD)
        lat2, lon2 = xy_to_latlon(x, y, LON_ORIGIN_COORD)
        lx, ly = latlon_to_local(lat, lon, cell)
        dlat = (lat2 - lat) * 111320.0
        dlon = (lon2 - lon) * 111320.0 * math.cos(math.radians(lat))
        err = math.hypot(dlat, dlon)
        if (cell != want or not cell_contains(cell, lat, lon)
                or (lx, ly) != (lx_w, ly_w) or not local_in_bounds(lx, ly)
                or err > 350.0):
            us_lm_ok = False
    check(
        "US landmarks -> tile/cell (<350 m)",
        us_lm_ok,
        f"{len(us_landmarks)} landmarks, Wikipedia coords",
    )

    # 17. US packed round-trip over negative longitudes, both origins.
    us_pairs = [(39951, 43010), (40580, 43264), (40236, 42881),
                (41911, 37081), (40809, 41525)]
    us_xy_ok = True
    for origin in ORIGIN_CHOICES:
        for x, y in us_pairs:
            lat, lon = xy_to_latlon(x, y, origin)
            if latlon_to_xy(lat, lon, origin) != (x, y) or lon >= 0:
                us_xy_ok = False
    check(
        "US packed (x,y) round-trip (lon<0)",
        us_xy_ok,
        f"{len(us_pairs)} pairs x 2 origins",
    )

    print(
        f"coord selftest: {'OK' if not failures else 'FAILED'} "
        f"({count - len(failures)}/{count} checks)"
    )
    return 1 if failures else 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_origin(value: str) -> int:
    key = value.strip().lower()
    if key in {"52742", "coord", "coords", "refer", "refer001", "point", "addre"}:
        return LON_ORIGIN_COORD
    if key in {"52736", "tile", "map", "mapal", "mapal001", "stream"}:
        return LON_ORIGIN_TILE
    raise argparse.ArgumentTypeError(
        f"unknown origin {value!r}; use 52742/coord or 52736/tile"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert ZE0 map coordinates (BxxRyyR, packed u16, 0..2047)",
        epilog="Exit codes: 0 success, 1 error, 2 usage error.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="machine-readable output (also accepted after the command)",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="run the synthetic coordinate checks and exit",
    )
    sub = parser.add_subparsers(dest="command")

    def add_json(p: argparse.ArgumentParser) -> None:
        # SUPPRESS keeps a --json given before the subcommand.
        p.add_argument(
            "--json",
            action="store_true",
            default=argparse.SUPPRESS,
            help="machine-readable output",
        )

    p_cell = sub.add_parser("cell", help="lat/lon -> BxxRyyR cell")
    p_cell.add_argument("lat", type=float)
    p_cell.add_argument("lon", type=float)
    p_cell.add_argument(
        "--local-scale",
        type=int,
        choices=(1, 2),
        default=DEFAULT_LOCAL_SCALE,
        help="local units per packed unit (default 2)",
    )
    add_json(p_cell)
    p_cell.set_defaults(func=cmd_cell)

    p_xy = sub.add_parser("xy", help="lat/lon -> packed (x, y) and local 0..2047")
    p_xy.add_argument("lat", type=float)
    p_xy.add_argument("lon", type=float)
    p_xy.add_argument(
        "--origin",
        type=parse_origin,
        default=DEFAULT_ORIGIN,
        metavar="52742|52736",
        help="longitude origin: 52742/coord (default) or 52736/tile",
    )
    p_xy.add_argument("--cell", help="assert the point is inside this cell")
    p_xy.add_argument(
        "--local-scale",
        type=int,
        choices=(1, 2),
        default=DEFAULT_LOCAL_SCALE,
        help="local units per packed unit (default 2, the 0..2047 hypothesis)",
    )
    add_json(p_xy)
    p_xy.set_defaults(func=cmd_xy)

    p_latlon = sub.add_parser("latlon", help="packed or local -> lat/lon")
    p_latlon.add_argument("x", type=float)
    p_latlon.add_argument("y", type=float)
    p_latlon.add_argument(
        "--origin",
        type=parse_origin,
        default=DEFAULT_ORIGIN,
        metavar="52742|52736",
        help="longitude origin: 52742/coord (default) or 52736/tile",
    )
    p_latlon.add_argument("--cell", help="cell for local input or a containment check")
    p_latlon.add_argument(
        "--local",
        action="store_true",
        help="treat X Y as tile-local 0..2047 (requires --cell)",
    )
    p_latlon.add_argument(
        "--local-scale",
        type=int,
        choices=(1, 2),
        default=DEFAULT_LOCAL_SCALE,
        help="local units per packed unit (default 2)",
    )
    add_json(p_latlon)
    p_latlon.set_defaults(func=cmd_latlon)

    p_bbox = sub.add_parser("bbox", help="print a cell's lat/lon, packed and local box")
    p_bbox.add_argument("cell", help="e.g. B48R058 or B48R058R.DAT")
    p_bbox.add_argument(
        "--local-scale",
        type=int,
        choices=(1, 2),
        default=DEFAULT_LOCAL_SCALE,
        help="local units per packed unit (default 2)",
    )
    add_json(p_bbox)
    p_bbox.set_defaults(func=cmd_bbox)

    p_levels = sub.add_parser("levels", help="documented level/zoom semantics")
    add_json(p_levels)
    p_levels.set_defaults(func=cmd_levels)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
