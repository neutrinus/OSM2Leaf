#!/usr/bin/env python3
"""parcel_census.py — list a ZE0 tile's directories and their WGS84 parcels (M5.34).

For one ``MAPAL001/BxxRyyR.DAT`` this prints every directory as
``(section, level, y, x, kind, slots, bbox)`` and marks whether
``tools/tilewriter.py`` may splice roads into it (``0x2046`` in section 1) or
must keep it byte-for-byte (the ``PRESERVE_ONLY_DIR_KINDS`` family).  With
``--parcel Y,X`` it prints the 32 x 32 parcel bounding boxes of one directory,
the geometry ``--parcel`` clipping in ``tools/one_tile_pipeline.py`` uses.

Geometry comes from the checked-in model, never from hand arithmetic:

* directory header ``x``  -> ``tilewriter.dir_x0`` (``x + 1024`` mod 2**16)
* mesh -> degrees          -> ``clarion_bg.mesh_to_lon`` / ``mesh_to_lat``
* parcel lower-left + size -> ``clarion_bg.parcel_geo``

No vendor bytes are read into the repo: give the tool a tile path outside the
checkout.  Exit codes: 0 ok, 1 the tile does not parse, 2 usage.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
for _p in (HERE / "ze0-viewer" / "tools_ze0", HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import clarion_bg  # noqa: E402
import clarion_tile  # noqa: E402
import tilewriter  # noqa: E402

GEOMETRY_KEYS = ("lon_min", "lat_min", "lon_max", "lat_max")


def directory_bbox(level: int, y0: int, x0: int) -> dict[str, float]:
    """The WGS84 box covered by one directory (all its parcels).

    Derived from ``clarion_bg.parcel_geo`` at the first and last parcel of the
    directory, so the box is the union of the parcel grid, not a hand formula.
    Every directory always has ``clarion_bg.LEVELS[level]["rows"]`` x
    ``["cols"]`` parcels, independent of the level's directory span (M5.44: the
    level-2 directory holds 4 x 4 meshes, so the parcel count, not
    ``lines // DIR_MESHES``, gives the box).
    """
    rows = clarion_bg.LEVELS[level]["rows"]
    cols = clarion_bg.LEVELS[level]["cols"]
    lon0, lat0, width, height = clarion_bg.parcel_geo(level, y0, x0, 0, 0)
    lon_end, lat_end, _, _ = clarion_bg.parcel_geo(
        level, y0, x0, rows - 1, cols - 1)
    return {
        "lon_min": lon0,
        "lat_min": lat0,
        "lon_max": lon_end + width,
        "lat_max": lat_end + height,
    }


def parcel_bbox(level: int, y0: int, x0: int, row: int, col: int) -> dict[str, float]:
    """The WGS84 box of one parcel inside a directory."""
    lon0, lat0, width, height = clarion_bg.parcel_geo(level, y0, x0, row, col)
    return {
        "lon_min": lon0,
        "lat_min": lat0,
        "lon_max": lon0 + width,
        "lat_max": lat0 + height,
    }


def classify(section: int, kind: int) -> str:
    """What the writer may do with a directory of this section/kind."""
    if section != 1:
        return "router-graph" if section == 2 else "other-section"
    if kind in tilewriter.SPLICEABLE_DIR_KINDS:
        return "spliceable"
    if kind in tilewriter.PRESERVE_ONLY_DIR_KINDS:
        return "preserve-only"
    return "unmodelled"


def census(tile: dict, sections: tuple[int, ...] | None = None,
           levels: tuple[int, ...] | None = None) -> list[dict[str, Any]]:
    """One row per directory of the parsed tile, sorted by section/level/y/x."""
    rows: list[dict[str, Any]] = []
    for sec in tile.get("sections") or []:
        sid = sec["id"]
        if sections is not None and sid not in sections:
            continue
        for entry in sec["levels"]:
            level = entry["level"]
            if levels is not None and level not in levels:
                continue
            for directory in entry["dirs"]:
                y0 = directory["y"]
                x0 = tilewriter.dir_x0(directory)
                box = directory_bbox(level, y0, x0)
                rows.append({
                    "section": sid,
                    "level": level,
                    "y": y0,
                    "x": x0,
                    "kind": directory["kind"],
                    "kind_hex": "0x%04x" % directory["kind"],
                    "slots": directory["nslots"],
                    "class": classify(sid, directory["kind"]),
                    **box,
                })
    rows.sort(key=lambda r: (r["section"], r["level"], r["y"], r["x"]))
    return rows


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_class: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for row in rows:
        by_class[row["class"]] = by_class.get(row["class"], 0) + 1
        by_kind[row["kind_hex"]] = by_kind.get(row["kind_hex"], 0) + 1
    spliceable_sec1 = [r for r in rows if r["section"] == 1 and r["class"] == "spliceable"]
    return {
        "directories": len(rows),
        "by_class": dict(sorted(by_class.items())),
        "by_kind": dict(sorted(by_kind.items())),
        "section1_spliceable": len(spliceable_sec1),
    }


def fmt_bbox(row: dict[str, Any]) -> str:
    return "%.5f,%.5f,%.5f,%.5f" % (
        row["lon_min"], row["lat_min"], row["lon_max"], row["lat_max"])


def render_text(rows: list[dict[str, Any]], path: str) -> str:
    out = [f"tile {path}: {len(rows)} director{'y' if len(rows) == 1 else 'ies'}",
           "sec lvl   y    x  kind   slots  class          bbox (lon_min,lat_min,lon_max,lat_max)"]
    for row in rows:
        out.append(
            "%3d %3d %3d %4d  %s %5d  %-13s  %s" % (
                row["section"], row["level"], row["y"], row["x"],
                row["kind_hex"], row["slots"], row["class"], fmt_bbox(row)))
    s = summarise(rows)
    out.append("summary: " + json.dumps(s, sort_keys=True))
    return "\n".join(out)


def load_tile(path: Path) -> dict:
    return clarion_tile.read_tile(path.read_bytes())


def selftest() -> int:
    fails = 0

    def chk(cond: bool, msg: str) -> None:
        nonlocal fails
        if cond:
            print(f"  ok   {msg}")
        else:
            print(f"  FAIL {msg}")
            fails += 1

    print("parcel_census selftest (synthetic tile, no vendor data)")
    cell = "B48R058R"
    yb, xb = tilewriter.cell_mesh(cell)          # (72, 936)
    extra = {1: [tilewriter._opaque_directory(0x2146, 1, yb, xb + 1)]}
    data = tilewriter.make_factory(cell, extra_dirs=extra)
    tile = clarion_tile.read_tile(data)
    rows = census(tile, sections=(1,))
    by_pos = {(r["y"], r["x"]): r for r in rows if r["level"] == 1}
    chk((yb, xb) in by_pos and (yb, xb + 1) in by_pos,
        "census lists both section-1 level-1 directories")
    chk(by_pos[(yb, xb)]["kind"] == 0x2046
        and by_pos[(yb, xb)]["class"] == "spliceable",
        "0x2046 directory classified spliceable")
    chk(by_pos[(yb, xb + 1)]["kind"] == 0x2146
        and by_pos[(yb, xb + 1)]["class"] == "preserve-only",
        "0x2146 directory classified preserve-only")
    chk(all(r["slots"] == 32 for r in by_pos.values()),
        "every directory reports 32 slots")

    # Directory bbox is the union of its 32x32 parcel grid (formula-derived).
    box = by_pos[(yb, xb)]
    lon0, lat0, w, h = clarion_bg.parcel_geo(1, yb, xb, 0, 0)
    chk(abs(box["lon_min"] - lon0) < 1e-12 and abs(box["lat_min"] - lat0) < 1e-12,
        "directory bbox starts at parcel (0,0) lower-left")
    chk(abs(box["lon_max"] - (lon0 + 32 * w)) < 1e-9
        and abs(box["lat_max"] - (lat0 + 32 * h)) < 1e-9,
        "directory bbox ends after parcel (31,31)")
    chk(abs((box["lon_max"] - box["lon_min"]) - 1.0) < 1e-9
        and abs((box["lat_max"] - box["lat_min"]) - 2.0 / 3.0) < 1e-9,
        "level-1 directory spans 1 deg lon x 2/3 deg lat")

    # Level 2: the same 32 x 32 parcel grid covers a 4-mesh directory
    # (clarion_bg.LEVELS[2]["dir_meshes"] = 4), so the box is 4 x 8/3 deg.
    # The old "rows // DIR_MESHES[level]" gave 8 x 8 (a 1/4-size box); these
    # assertions are red on that value (M5.44).
    box2 = directory_bbox(2, yb, xb)
    p2 = parcel_bbox(2, yb, xb, 0, 0)
    chk(abs((p2["lon_max"] - p2["lon_min"]) - 1.0 / 8) < 1e-12
        and abs((p2["lat_max"] - p2["lat_min"]) - (2.0 / 3.0) / 8) < 1e-12,
        "level-2 parcel spans 1/8 deg lon x (2/3)/8 deg lat")
    chk(abs((box2["lon_max"] - box2["lon_min"]) - 4.0) < 1e-9
        and abs((box2["lat_max"] - box2["lat_min"]) - 8.0 / 3.0) < 1e-9,
        "level-2 directory spans 4 deg lon x 8/3 deg lat")
    chk(abs((box2["lon_max"] - box2["lon_min"]) - 32 * (1.0 / 8)) < 1e-9
        and abs((box2["lat_max"] - box2["lat_min"])
                - 32 * ((2.0 / 3.0) / 8)) < 1e-9,
        "level-2 32x32 parcel grid fills the directory box")

    # A parcel bbox sits inside its directory and is 1/32 of it.
    pb = parcel_bbox(1, yb, xb, 0, 0)
    chk(box["lon_min"] <= pb["lon_min"] < pb["lon_max"] <= box["lon_max"]
        and box["lat_min"] <= pb["lat_min"] < pb["lat_max"] <= box["lat_max"],
        "parcel bbox lies inside the directory bbox")
    chk(abs((pb["lon_max"] - pb["lon_min"]) - 1.0 / 32) < 1e-12
        and abs((pb["lat_max"] - pb["lat_min"]) - (2.0 / 3.0) / 32) < 1e-12,
        "parcel spans 1/32 of the directory in each axis")

    # Adjacent parcels tile the directory without gaps or overlap.
    a = parcel_bbox(1, yb, xb, 0, 0)
    b = parcel_bbox(1, yb, xb, 0, 1)
    chk(abs(a["lon_max"] - b["lon_min"]) < 1e-12, "neighbouring parcels share an edge")

    # Section 2 is never reported as road-spliceable.
    s2 = census(tile, sections=(2,))
    chk(all(r["class"] != "spliceable" for r in s2),
        "section 2 directories never classified spliceable")

    summary = summarise(rows)
    chk(summary["section1_spliceable"] == 1, "summary counts one spliceable section-1 directory")
    json.dumps(rows)
    chk(True, "census rows are JSON-serializable")
    chk("0x2146" in render_text(rows, str(cell)), "text render names the preserve-only kind")

    # Usage failures are loud.
    import contextlib
    import io
    with contextlib.redirect_stderr(io.StringIO()):
        rc = main(["/nonexistent/B48R058R.DAT"])
    chk(rc == 2, "missing tile file exits 2")
    with contextlib.redirect_stderr(io.StringIO()):
        rc = main(["/nonexistent/B48R058R.DAT", "--parcel", "76"])
    chk(rc == 2, "malformed --parcel exits 2")

    print(f"selftest: {'OK' if not fails else 'FAIL'} ({fails} failure(s))")
    return 0 if not fails else 1


def parse_parcel(text: str) -> tuple[int, int]:
    parts = text.split(",")
    if len(parts) != 2:
        raise ValueError("--parcel needs Y,X")
    y, x = (int(p, 0) for p in parts)
    if not (0 <= y <= 1023 and 0 <= x <= 1023):
        raise ValueError("--parcel Y,X out of the mesh range 0..1023")
    return y, x


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="List a ZE0 tile's directories and WGS84 parcel boxes (M5.34)")
    ap.add_argument("tile", nargs="?", help="path to MAPAL001/BxxRyyR.DAT (outside the repo)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--sections", default="1,2", help="comma-separated section ids (default 1,2)")
    ap.add_argument("--levels", default="", help="comma-separated levels (default all present)")
    ap.add_argument("--parcel", metavar="Y,X",
                    help="print the 32x32 parcel boxes of this directory instead")
    ap.add_argument("--json", nargs="?", const="-", default=None, metavar="PATH")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.tile:
        print("error: a tile path is required (or --selftest)", file=sys.stderr)
        return 2
    try:
        sections = tuple(int(s) for s in args.sections.split(",") if s.strip())
        levels = tuple(int(s) for s in args.levels.split(",") if s.strip()) or None
        want_parcel = parse_parcel(args.parcel) if args.parcel else None
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    path = Path(args.tile)
    try:
        tile = load_tile(path)
    except OSError as e:
        print(f"error: cannot read {path}: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # a malformed tile is a result, not a crash
        print(f"error: {path} does not parse as a tile: {type(e).__name__}: {e}",
              file=sys.stderr)
        return 1
    rows = census(tile, sections=sections, levels=levels)
    if want_parcel is not None:
        y0, x0 = want_parcel
        match = [r for r in rows if r["section"] == 1 and r["level"] == 1
                 and r["y"] == y0 and r["x"] == x0 and r["class"] == "spliceable"]
        if not match:
            print(f"error: {path} has no spliceable section-1 level-1 directory "
                  f"at y={y0} x={x0}", file=sys.stderr)
            return 1
        span = tilewriter.DIR_MESHES[1]
        rows = []
        for row in range(32):
            for col in range(32):
                rows.append({"section": 1, "level": 1, "y": y0, "x": x0, "row": row,
                             "col": col, **parcel_bbox(1, y0, x0, row, col)})
        doc: Any = {"tile": str(path), "directory": {"y": y0, "x": x0},
                    "parcels": 32 * 32, "rows": rows}
    else:
        doc = {"tile": str(path), "rows": rows, "summary": summarise(rows)}
    if args.json is not None:
        text = json.dumps(doc, indent=2, sort_keys=True)
        if args.json == "-":
            print(text)
        else:
            Path(args.json).write_text(text + "\n", encoding="utf-8")
            print(f"report: {args.json}")
    elif want_parcel is not None:
        print(f"tile {path}: directory y={y0} x={x0} parcel grid (32 x 32)")
        for row in rows:
            print("row %2d col %2d  %s" % (row["row"], row["col"], fmt_bbox(row)))
    else:
        print(render_text(rows, str(path)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
