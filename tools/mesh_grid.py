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
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TILE_RE = re.compile(r"^B([0-9A-Fa-f]{2})R([0-9A-Fa-f]{3})R\.DAT$")
LAT_UNIT = 2.0 / 3.0
LON_UNIT = 1.0
SPAN = 8


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

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
