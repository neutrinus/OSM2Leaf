#!/usr/bin/env python3
"""Rebuild the S3 bench card (one moved vertex in one US tile) and say where it is.

M5.14 built the S3 card from a script that was never committed
(``/tmp/m5_14_patch.py``); this tool is that generator (M6.16).  The edit is
the M4.4 in-place one-vertex method:

* tile ``MAPAL001/B18R100R.DAT`` of the US 2011 card, section 1, level 1,
  directory ``(y, x) = (30, 65280)``, slot (parcel row) 8, record ``k = 17``
  (odd = background, parcel column ``k // 2 = 8``);
* background layer 8, shape 1, vertex 2: ``(1851, 52) -> (1891, 52)``
  (``dx = +40``, ``dy = 0`` parcel units);
* the record is rebuilt with ``clarion_bg`` (strict), recompressed with
  ``zlib.compress(plain, 9)``, word-padded and NUL-padded to the **original**
  compressed stream length (288 B), and written over the stream at file
  offset ``0x1150c0`` only.  The directory pair, every other stream and the
  file size are untouched.

Subcommands::

    s3_vertex_patch.py tile  FACTORY.DAT -o PATCHED.DAT [--json]
    s3_vertex_patch.py image --image BASE.img -o OUT.img [--tile-out T] [--json]
    s3_vertex_patch.py locate FACTORY.DAT [--json]
    s3_vertex_patch.py extract --image IMG [--file REL] -o OUT
    s3_vertex_patch.py --selftest

``tile`` reproduces the patched tile and compares it with the pinned
SHA-256 (``fc4d4bfc…``).  ``image`` reads the tile from ``BASE.img`` through
the FAT, patches it and writes it into a copy of the image with
``imgpatch.patch_image`` (same length, existing cluster chain); with the
factory image as base the result is the S3 card (``186f2ded…``).  Any base
that carries the factory tile works, e.g. the S2 card when stages stack.

``extract`` copies one file (default the tile) out of an image through the
FAT (``mkcard.img_read``) and prints its size and SHA-256.

``locate`` prints the moved vertex in WGS84 with the level-1 parcel grid
(``clarion_bg.parcel_geo``, M5.44) and a US-capable mesh column: a directory
header stores ``x`` as ``mesh_x - 1024`` in a signed 16-bit word
(``ze0_decode.py``, ``tilewriter.x_field``), so ``65280`` is mesh column 768,
longitude -156.  ``clarion_bg.mesh_to_lon`` applied to the raw word gives
64356 (the M6.13 symptom).  As a positive control it locates three capes of
the island of Hawaii from the factory tile's own sea polygons (layer 1,
vertices not on a parcel border) and compares them with gazetteer
coordinates; the same capes under a y-flipped parcel and under C-2054's
``coord.local_to_latlon`` reading are the negative controls.

Exit status: 0 ok / reproduced, 1 a check failed (hash differs, control
outside tolerance), 2 usage or input error.
"""
from __future__ import annotations

import argparse
import hashlib
import hashutil
import json
import math
import sys
import tempfile
import zlib
from dataclasses import dataclass, replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "ze0-viewer" / "tools_ze0")]

import clarion_bg  # noqa: E402
import clarion_tile  # noqa: E402

TILE_REL = "MAPAL001/B18R100R.DAT"
FACTORY_TILE_SHA256 = "79f4665541731d90d9db276419b54904d199696d91997e13a3170259d02d0519"
PATCHED_TILE_SHA256 = "fc4d4bfc8365647c61ff53b21096180e9d1317564b14e9eca7ec827ae9f3c421"
BASE_IMAGE_SHA256 = "53342430a1bb58d3ed6eb68c5563f079c710a400134d522e6192489b324c5383"
S3_IMAGE_SHA256 = "186f2ded6263120299fc52a91db15796d8e8ce06f8886353114709be239775c1"
TILE_SIZE = 1994496


@dataclass(frozen=True)
class Edit:
    """One vertex move inside one background record, located structurally."""
    level: int = 1
    dir_y: int = 30
    dir_x: int = 65280          # the raw directory-header word
    slot: int = 8               # parcel row
    k: int = 17                 # record index in the slot; odd = background
    layer: int = 8
    shape: int = 1
    vertex: int = 2
    old: tuple = (1851, 52)
    dx: int = 40
    dy: int = 0
    offset: int | None = 0x1150C0   # expected file offset of the stream
    length: int | None = 288        # expected compressed stream length
    zlevel: int = 9


S3_EDIT = Edit()


class PatchError(Exception):
    pass


sha256 = hashutil.sha256_bytes


def signed16(v: int) -> int:
    return v - 65536 if v > 32767 else v


def mesh_x(dir_x: int) -> int:
    """Absolute mesh column of a directory-header ``x`` word (EU and US)."""
    return signed16(dir_x) + 1024


def vertex_lonlat(level, dir_y, dir_x, row, col, x, y, flip_y=False):
    """WGS84 ``(lon, lat)`` of parcel-local ``(x, y)`` with the M5.44 grid."""
    lon0, lat0, w, h = clarion_bg.parcel_geo(level, dir_y, mesh_x(dir_x), row, col)
    if flip_y:
        y = clarion_bg.UNITS - y
    return lon0 + x / clarion_bg.UNITS * w, lat0 + y / clarion_bg.UNITS * h


def metres(a, b) -> float:
    """Equirectangular distance in metres between two ``(lon, lat)`` points."""
    lat = math.radians((a[1] + b[1]) / 2)
    dx = (a[0] - b[0]) * math.cos(lat) * 111320.0
    dy = (a[1] - b[1]) * 110574.0
    return math.hypot(dx, dy)


def find_record(data: bytes, edit: Edit):
    """Return ``(offset, raw)`` of the edit's stream, or raise PatchError."""
    tile = clarion_tile.read_tile(data)
    for sec in tile["sections"]:
        if sec["id"] != 1:
            continue
        for lvl in sec["levels"]:
            if lvl["level"] != edit.level:
                continue
            for d in lvl["dirs"]:
                if (d["y"], d["x"]) != (edit.dir_y, edit.dir_x):
                    continue
                slot = d["slots"].get(edit.slot)
                if slot is None:
                    raise PatchError("slot %d is empty" % edit.slot)
                q = slot["block_off"]
                for rec in slot["recs"]:
                    if rec["k"] == edit.k:
                        return q, rec["raw"]
                    q += len(rec["raw"])
                raise PatchError("record k=%d not in slot %d" % (edit.k, edit.slot))
    raise PatchError("directory (%d,%d) not at level %d"
                     % (edit.dir_y, edit.dir_x, edit.level))


def patch_tile(data: bytes, edit: Edit = S3_EDIT):
    """Apply ``edit`` in place; return ``(new_bytes, report)``."""
    off, raw = find_record(data, edit)
    if edit.offset is not None and off != edit.offset:
        raise PatchError("stream at 0x%x, expected 0x%x" % (off, edit.offset))
    if edit.length is not None and len(raw) != edit.length:
        raise PatchError("stream is %d B, expected %d" % (len(raw), edit.length))
    if not clarion_tile.is_zlib(raw):
        raise PatchError("stream is not zlib")
    plain = zlib.decompressobj().decompress(raw)
    rec = clarion_bg.parse_record(plain)
    if rec.get("opaque"):
        raise PatchError("record is opaque to clarion_bg")
    group = rec["layers"].get(edit.layer)
    if not group or "shapes" not in group:
        raise PatchError("layer %d has no shapes" % edit.layer)
    shape = group["shapes"][edit.shape]
    old = tuple(shape["pts"][edit.vertex])
    if old != tuple(edit.old):
        raise PatchError("vertex is %r, expected %r" % (old, tuple(edit.old)))
    new = (old[0] + edit.dx, old[1] + edit.dy)
    if not all(0 <= v < clarion_bg.UNITS for v in new):
        raise PatchError("moved vertex %r leaves the parcel" % (new,))
    pts = list(shape["pts"])
    pts[edit.vertex] = new
    shape["pts"] = pts
    rec["strict"] = True
    new_plain = clarion_bg.build_record(rec)
    if new_plain == plain or len(new_plain) != len(plain):
        raise PatchError("rebuilt record unchanged or resized (%d -> %d)"
                         % (len(plain), len(new_plain)))
    comp = zlib.compress(new_plain, edit.zlevel)
    comp_len = len(comp)
    if len(comp) % 2:
        comp += b"\x00"
    if len(comp) > len(raw):
        raise PatchError("COMP TOO BIG: %d > %d" % (len(comp), len(raw)))
    comp += b"\x00" * (len(raw) - len(comp))
    out = bytearray(data)
    out[off:off + len(raw)] = comp
    out = bytes(out)
    differing = sum(1 for a, b in zip(raw, comp) if a != b)
    # read back: the new stream must decode to the moved vertex
    _off2, raw2 = find_record(out, edit)
    back = clarion_bg.parse_record(zlib.decompressobj().decompress(raw2))
    got = tuple(back["layers"][edit.layer]["shapes"][edit.shape]["pts"][edit.vertex])
    if got != new:
        raise PatchError("read-back vertex %r != %r" % (got, new))
    report = dict(offset=off, stream_len=len(raw), plain_len=len(plain),
                  comp_before=len(raw), comp_after=comp_len, old=list(old),
                  new=list(new), differing_bytes=differing,
                  size=len(out), size_same=len(out) == len(data),
                  sha256_in=sha256(data), sha256_out=sha256(out))
    return out, report


def first_diff(a: bytes, b: bytes):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return None if len(a) == len(b) else min(len(a), len(b))


# --- location ---------------------------------------------------------------

# Gazetteer coordinates (lon, lat) of three capes of the island of Hawaii and
# their stated precision in degrees (arc-second or arc-minute source).  Entered
# by hand from the public gazetteer entries (Wikipedia / USGS GNIS); not
# fetched in the sandbox.  Each is the extreme sea-polygon coast vertex of a
# window that contains only that cape.
CAPES = {
    "Ka Lae (South Point)": dict(ref=(-155.6811, 18.9108), prec=0.0003,
                                 window=dict(lat=(18.6, 19.2), lon=(-156.0, -155.0)),
                                 pick="min_lat"),
    "Cape Kumukahi (east point)": dict(ref=(-154.8167, 19.5167), prec=0.0167,
                                       window=dict(lat=(19.3, 19.8), lon=(-155.0, -154.5)),
                                       pick="max_lon"),
    "Upolu Point (north point)": dict(ref=(-155.85, 20.2667), prec=0.0167,
                                      window=dict(lat=(19.9, 20.5), lon=(-156.0, -155.0)),
                                      pick="max_lat"),
}
CAPE_TOL_M = 500.0     # added to the reference precision (converted to metres)


def coast_vertices(data: bytes, level: int = 1, layer: int = 1):
    """Sea-polygon vertices that are not on a parcel border, as grid tuples."""
    tile = clarion_tile.read_tile(data)
    out = []
    for sec in tile["sections"]:
        if sec["id"] != 1:
            continue
        for lvl in sec["levels"]:
            if lvl["level"] != level:
                continue
            for d in lvl["dirs"]:
                for row, slot in d["slots"].items():
                    for rec in slot["recs"]:
                        if rec["k"] % 2 != 1 or not clarion_tile.is_zlib(rec["raw"]):
                            continue
                        parsed = clarion_bg.parse_record(zlib.decompress(rec["raw"]))
                        g = parsed["layers"].get(layer)
                        if not g or "shapes" not in g:
                            continue
                        for sh in g["shapes"]:
                            for x, y in sh["pts"]:
                                if x in (0, 2047, 2048) or y in (0, 2047, 2048):
                                    continue
                                out.append((d["y"], d["x"], row, rec["k"] // 2, x, y))
    return out


def _coord_c2054(cell, x, y):
    import coord
    lat, lon = coord.local_to_latlon(cell, x, y, scale=2)
    return lon, lat


def cape_controls(data: bytes, cell: str = "B18R100R"):
    verts = coast_vertices(data)
    mappings = {
        "grid": lambda v: vertex_lonlat(1, *v),
        "grid_flip_y": lambda v: vertex_lonlat(1, *v, flip_y=True),
        "c2054_coord_scale2": lambda v: _coord_c2054(cell, v[4], v[5]),
    }
    rows = []
    for name, cape in CAPES.items():
        row = dict(cape=name, ref=list(cape["ref"]), ref_prec_deg=cape["prec"])
        tol = CAPE_TOL_M + cape["prec"] * 111320.0
        row["tol_m"] = round(tol)
        for mname, fn in mappings.items():
            pts = [fn(v) for v in verts]
            win = cape["window"]
            pts = [p for p in pts if win["lat"][0] <= p[1] <= win["lat"][1]
                   and win["lon"][0] <= p[0] <= win["lon"][1]]
            if not pts:
                row[mname] = dict(found=None, err_m=None, ok=False)
                continue
            key = {"min_lat": lambda p: p[1], "max_lat": lambda p: -p[1],
                   "max_lon": lambda p: -p[0]}[cape["pick"]]
            best = min(pts, key=key)
            err = metres(best, cape["ref"])
            row[mname] = dict(found=[round(best[0], 5), round(best[1], 5)],
                              err_m=round(err), ok=err <= tol)
        rows.append(row)
    return dict(coast_vertices=len(verts), capes=rows,
                positive_ok=all(r["grid"]["ok"] for r in rows),
                negatives_fail=all(not all(r[m]["ok"] for r in rows)
                                   for m in ("grid_flip_y", "c2054_coord_scale2")))


def locate(data: bytes, edit: Edit = S3_EDIT, controls: bool = True):
    col = edit.k // 2
    old = tuple(edit.old)
    new = (old[0] + edit.dx, old[1] + edit.dy)
    lon0, lat0, w, h = clarion_bg.parcel_geo(edit.level, edit.dir_y,
                                             mesh_x(edit.dir_x), edit.slot, col)
    a = vertex_lonlat(edit.level, edit.dir_y, edit.dir_x, edit.slot, col, *old)
    b = vertex_lonlat(edit.level, edit.dir_y, edit.dir_x, edit.slot, col, *new)
    dlon, dlat, _w, _h = clarion_bg.parcel_geo(edit.level, edit.dir_y,
                                               mesh_x(edit.dir_x), 0, 0)
    spec = clarion_bg.LEVELS[edit.level]
    out = dict(
        mesh_x=mesh_x(edit.dir_x),
        directory_box=dict(lon=[dlon, dlon + spec["cols"] * w],
                           lat=[dlat, dlat + spec["rows"] * h]),
        parcel=dict(row=edit.slot, col=col, lon0=lon0, lat0=lat0, w=w, h=h),
        before=[round(a[0], 6), round(a[1], 6)],
        after=[round(b[0], 6), round(b[1], 6)],
        shift_m=round(metres(a, b), 1),
        shift_bearing="east" if edit.dx > 0 and edit.dy == 0 else "see dx/dy",
    )
    if controls:
        out["controls"] = cape_controls(data)
    return out


# --- image ------------------------------------------------------------------

def read_tile_from_image(image: Path, rel: str = TILE_REL) -> bytes:
    import mkcard
    with image.open("rb") as h:
        _part, geo, fat = mkcard.open_map_partition(h)
        return mkcard.img_read(h, geo, fat, rel)


def build_image(image: Path, out: Path, tile_out: Path | None = None,
                edit: Edit = S3_EDIT) -> dict:
    import imgpatch
    factory = read_tile_from_image(image)
    patched, rep = patch_tile(factory, edit)
    report = dict(tile=rep)
    with tempfile.TemporaryDirectory(dir=str(out.parent)) as tmp:
        tpath = Path(tile_out) if tile_out else Path(tmp) / "B18R100R.DAT"
        tpath.write_bytes(patched)
        res = imgpatch.patch_image(str(image), TILE_REL, str(tpath), str(out),
                                   hash_output=True)
    report["imgpatch_ok"] = bool(res.get("ok"))
    report["image_sha256"] = res.get("output_sha256")
    return report


# --- selftest ---------------------------------------------------------------

def selftest() -> int:
    import tilewriter
    fails = []

    def check(name, cond, detail=""):
        print("%s %s%s" % ("ok  " if cond else "FAIL", name, (": " + detail) if detail else ""))
        if not cond:
            fails.append(name)

    # synthetic factory tile at the S3 cell (no vendor bytes); its x word is
    # 65280 like the real US directory
    data = tilewriter.make_factory("B18R100R")
    tile = clarion_tile.read_tile(data)
    d = next(dd for lv in tile["sections"][0]["levels"] if lv["level"] == 1
             for dd in lv["dirs"])
    check("synthetic dir x word is the US 65280", d["x"] == 65280, str(d["x"]))
    # slot 4 holds k=6 (road) then k=7 (background): the offset sum is exercised
    edit = Edit(dir_y=d["y"], dir_x=d["x"], slot=4, k=7, layer=0, shape=0,
                vertex=1, old=(340, 440), dx=-40, dy=-40, offset=None, length=None)
    off, raw = find_record(data, edit)
    check("record found after its road partner", off == d["slots"][4]["block_off"]
          + len(d["slots"][4]["recs"][0]["raw"]), hex(off))
    out, rep = patch_tile(data, replace(edit, offset=off, length=len(raw)))
    check("size unchanged", len(out) == len(data))
    diff = [i for i in range(len(data)) if data[i] != out[i]]
    check("bytes changed only inside the stream",
          bool(diff) and min(diff) >= off and max(diff) < off + len(raw),
          "%d bytes" % len(diff))
    check("vertex moved", rep["new"] == [300, 400], str(rep["new"]))
    check("deterministic", patch_tile(data, edit)[0] == out)
    # negative controls: each guard refuses
    for name, bad in (("wrong old vertex", replace(edit, old=(1, 1))),
                      ("wrong offset", replace(edit, offset=off + 2)),
                      ("wrong length", replace(edit, length=len(raw) + 2)),
                      ("leaves parcel", replace(edit, dx=4000)),
                      ("missing record", replace(edit, k=9)),
                      ("missing dir", replace(edit, dir_y=edit.dir_y + 1))):
        try:
            patch_tile(data, bad)
            check("refuses " + name, False)
        except PatchError as exc:
            check("refuses " + name, True, str(exc))
    # COMP TOO BIG: recompressed stream must not exceed the original slot.
    # The overflow case is zlib-implementation-sensitive (stock 1.3.1 vs
    # zlib-ng / newer runtimes compress the same edit differently), so force
    # the guard instead of relying on one observed delta.
    orig_compress = zlib.compress
    try:
        zlib.compress = lambda b, level=9: b"\x00" * (len(raw) + 10)
        patch_tile(data, replace(edit, dx=40, dy=0))
        check("refuses COMP TOO BIG", False)
    except PatchError as exc:
        check("refuses COMP TOO BIG", "TOO BIG" in str(exc), str(exc))
    finally:
        zlib.compress = orig_compress
    # mesh column: US word 65280 -> -156, EU B48R058R word -> 6..
    check("US mesh_x(65280) = 768 (lon -156)", mesh_x(65280) == 768
          and clarion_bg.mesh_to_lon(mesh_x(65280)) == -156)
    check("EU mesh_x round-trips tilewriter.x_field",
          all(mesh_x(tilewriter.x_field(x0)) == x0 for x0 in (930, 940, 768, 1000)))
    lon, lat = vertex_lonlat(1, 30, 65280, 8, 8, 1851, 52)
    check("S3 vertex in directory (30,65280) parcel (8,8)",
          -155.75 <= lon < -155.71875 and 20.1666 <= lat < 20.1875,
          "%.6f %.6f" % (lon, lat))
    a = (-155.0, 20.0)
    check("metres: 0.001 deg lat ~ 111 m", 100 < metres(a, (-155.0, 20.001)) < 120)
    # coast_vertices on the synthetic tile: polygon layer 0, none of layer 1
    check("coast_vertices reads layer only", coast_vertices(data, layer=0)
          and not coast_vertices(data, layer=1))
    print("%d failed" % len(fails) if fails else "selftest: all checks passed")
    return 1 if fails else 0


# --- CLI --------------------------------------------------------------------

def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true",
                    help="synthetic checks (no vendor data)")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("tile", help="patch a factory tile")
    p.add_argument("src")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("image", help="patch the tile inside a copy of an image")
    p.add_argument("--image", required=True)
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--tile-out")
    p.add_argument("--expect-sha256", default=None,
                   help="compare the output image SHA-256 with this value "
                        "(the S3 card: %s...)" % S3_IMAGE_SHA256[:16])
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("extract", help="copy one file out of an image")
    p.add_argument("--image", required=True)
    p.add_argument("--file", default=TILE_REL)
    p.add_argument("-o", "--out", required=True)
    p = sub.add_parser("locate", help="vertex lat/lon and cape controls")
    p.add_argument("src")
    p.add_argument("--no-controls", action="store_true")
    p.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmd:
        ap.error("a subcommand is required")

    try:
        if args.cmd == "extract":
            data = read_tile_from_image(Path(args.image), args.file)
            Path(args.out).write_bytes(data)
            print("%s %d %s" % (args.file, len(data), sha256(data)))
            return 0
        if args.cmd == "tile":
            data = Path(args.src).read_bytes()
            out, rep = patch_tile(data)
            Path(args.out).write_bytes(out)
            rep["factory_sha256_match"] = rep["sha256_in"] == FACTORY_TILE_SHA256
            rep["reproduced"] = rep["sha256_out"] == PATCHED_TILE_SHA256
            if not rep["reproduced"]:
                rep["note"] = "expected %s" % PATCHED_TILE_SHA256
            ok = rep["reproduced"]
            if args.json:
                print(json.dumps(rep, indent=1))
            else:
                print("stream 0x%x len %d: vertex %s -> %s, comp %d -> %d (pad to %d), "
                      "%d bytes differ, size same %s"
                      % (rep["offset"], rep["stream_len"], tuple(rep["old"]),
                         tuple(rep["new"]), rep["comp_before"], rep["comp_after"],
                         rep["stream_len"], rep["differing_bytes"], rep["size_same"]))
                print("in  %s factory=%s" % (rep["sha256_in"], rep["factory_sha256_match"]))
                print("out %s reproduced=%s" % (rep["sha256_out"], rep["reproduced"]))
            return 0 if ok else 1
        if args.cmd == "image":
            image, out = Path(args.image), Path(args.out)
            rep = build_image(image, out, Path(args.tile_out) if args.tile_out else None)
            rep["tile"]["reproduced"] = rep["tile"]["sha256_out"] == PATCHED_TILE_SHA256
            exp = args.expect_sha256
            rep["expect_sha256"] = exp
            rep["image_match"] = None if exp is None else rep["image_sha256"] == exp
            ok = rep["imgpatch_ok"] and rep["tile"]["reproduced"] and rep["image_match"] is not False
            if args.json:
                print(json.dumps(rep, indent=1))
            else:
                print("tile %s reproduced=%s" % (rep["tile"]["sha256_out"], rep["tile"]["reproduced"]))
                print("image %s imgpatch ok=%s match=%s"
                      % (rep["image_sha256"], rep["imgpatch_ok"], rep["image_match"]))
            return 0 if ok else 1
        if args.cmd == "locate":
            data = Path(args.src).read_bytes()
            rep = locate(data, controls=not args.no_controls)
            rep["factory_sha256_match"] = sha256(data) == FACTORY_TILE_SHA256
            ok = True
            if "controls" in rep:
                ok = rep["controls"]["positive_ok"] and rep["controls"]["negatives_fail"]
            if args.json:
                print(json.dumps(rep, indent=1))
            else:
                print("mesh column %d; parcel row %d col %d at lon %.6f lat %.6f (%.5f x %.6f deg)"
                      % (rep["mesh_x"], rep["parcel"]["row"], rep["parcel"]["col"],
                         rep["parcel"]["lon0"], rep["parcel"]["lat0"],
                         rep["parcel"]["w"], rep["parcel"]["h"]))
                print("before lon %.6f lat %.6f" % tuple(rep["before"]))
                print("after  lon %.6f lat %.6f  shift %.1f m %s"
                      % (rep["after"][0], rep["after"][1], rep["shift_m"], rep["shift_bearing"]))
                if "controls" in rep:
                    c = rep["controls"]
                    print("coast vertices %d" % c["coast_vertices"])
                    for r in c["capes"]:
                        print("  %-28s ref %s tol %d m" % (r["cape"], r["ref"], r["tol_m"]))
                        for m in ("grid", "grid_flip_y", "c2054_coord_scale2"):
                            e = r[m]
                            print("    %-20s %s err %s m ok=%s" % (m, e["found"], e["err_m"], e["ok"]))
                    print("positive (grid) ok=%s; negatives fail=%s"
                          % (c["positive_ok"], c["negatives_fail"]))
            return 0 if ok else 1
    except (PatchError, OSError, ValueError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
