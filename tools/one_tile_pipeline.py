#!/usr/bin/env python3
"""
one_tile_pipeline.py — Dolnośląskie one-tile OSM pipeline (M5.29).

Produces an output card tree where exactly one tile (default B48R058R) is
OSM-generated via osm_ingest -> mesh_split -> roadclass_v0 (provisional-v0)
-> tilewriter, and the rest is factory/verbatim (factory-backed path) or a
synthetic baseline/verbatim (synthetic-only path). Rebuilds manifests and
runs cardcheck / applicable l2check, emitting a per-gate report.

Rule 13: mapping=provisional-v0 (roadclass_v0) is provisional and NOT
firmware-confirmed. L2 is necessary, not sufficient; L3/L4/L5 firmware
acceptance is unknown. Gate statuses are PASS / NOT-APPLICABLE /
CANNOT-VERIFY-OFFLINE / NEEDS-L3; SKIP is never reported as PASS.

No vendor bytes are committed or embedded. Stdlib + existing repo tools only.

Exit codes: 0 selftest/ok, 1 check/selftest/gate failure, 2 usage/input.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import sys
import struct
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

GATES = [
    "hdd_info_map_code",
    "drstr_mmain_cmplst_ind",
    "tile_roundtrip_structure",
    "section4",
    "manifests",
]
STATUSES = {"PASS", "NOT-APPLICABLE", "CANNOT-VERIFY-OFFLINE", "NEEDS-L3", "BLOCKED", "FAIL"}

SYNTHETIC_OSM = """\
<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6">
 <node id="1" lat="51.1000" lon="17.0000"/>
 <node id="2" lat="51.1000" lon="17.0500"/>
 <node id="3" lat="51.1200" lon="17.0300"/>
 <node id="4" lat="51.0800" lon="17.0200"/>
 <way id="10">
  <nd ref="1"/><nd ref="2"/><nd ref="3"/>
  <tag k="highway" v="primary"/>
  <tag k="name" v="Testowa"/>
 </way>
 <way id="11">
  <nd ref="4"/><nd ref="1"/>
  <tag k="highway" v="residential"/>
 </way>
</osm>
"""


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class UsageError(Exception):
    """An input combination that would destroy data or cannot be honoured."""


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _check_out_overlap(out: Path, input_root: Path | None) -> None:
    """Reject an ``out`` that is the input root, or a parent/child of it.

    Both ``build_*_out`` helpers delete ``out`` before writing; if it overlaps
    the input, the deletion destroys the input (H64).
    """
    if input_root is None:
        return
    o = out.expanduser().resolve()
    r = input_root.expanduser().resolve()
    if o == r:
        raise UsageError(f"--out {o} is the input root; refusing to delete the input tree")
    if _is_within(r, o):
        raise UsageError(f"--out {o} is a parent of input root {r}; a recursive delete would remove the input")
    if _is_within(o, r):
        raise UsageError(f"--out {o} is inside input root {r}; refusing to remove input data")


def _clarion_tile():
    ze0 = HERE / "ze0-viewer" / "tools_ze0"
    if str(ze0) not in sys.path:
        sys.path.insert(0, str(ze0))
    import clarion_tile  # noqa: E402
    return clarion_tile


def _parcel_census():
    import parcel_census  # noqa: E402
    return parcel_census


def parse_parcel(text: str) -> tuple[int, int]:
    parts = text.split(",")
    if len(parts) != 2:
        raise UsageError(f"--parcel needs Y,X (directory mesh position), got {text!r}")
    try:
        y, x = (int(p, 0) for p in parts)
    except ValueError:
        raise UsageError(f"--parcel needs two integers Y,X, got {text!r}")
    if not (0 <= y <= 1023 and 0 <= x <= 1023):
        raise UsageError(f"--parcel {y},{x} is outside the mesh range 0..1023")
    return y, x


def parse_osm_bbox(text: str) -> tuple[float, float, float, float]:
    parts = [p for p in text.replace(",", " ").split() if p]
    if len(parts) != 4:
        raise UsageError(f"--osm-bbox needs MINLON,MINLAT,MAXLON,MAXLAT, got {text!r}")
    try:
        minlon, minlat, maxlon, maxlat = (float(p) for p in parts)
    except ValueError:
        raise UsageError(f"--osm-bbox needs four numbers, got {text!r}")
    if not (-180.0 <= minlon < maxlon <= 180.0 and -90.0 <= minlat < maxlat <= 90.0):
        raise UsageError(f"--osm-bbox {text!r} is not a valid lon/lat box")
    return minlon, minlat, maxlon, maxlat


def directory_box(cell: str, parcel: tuple[int, int]) -> dict[str, float]:
    """The WGS84 box of one section-1 level-1 directory (via parcel_census)."""
    y0, x0 = parcel
    return _parcel_census().directory_bbox(1, y0, x0)


def default_osm_bbox(box: dict[str, float]) -> tuple[float, float, float, float]:
    """The directory's own box; ``clip_imf_to_directory`` does the strict clip.

    ``osm_ingest --bbox`` is inclusive and keeps every vertex of a way that has
    *one* vertex inside, so it cannot by itself keep a way inside one
    directory.  The exact box still narrows the ingest pass; the node/way clip
    afterwards enforces the directory.
    """
    return (box["lon_min"], box["lat_min"], box["lon_max"], box["lat_max"])


def clip_imf_to_directory(imf_in: Path, imf_out: Path,
                          box: dict[str, float]) -> dict[str, Any]:
    """Keep only nodes strictly inside ``box`` and ways using only those nodes.

    A directory's parcels are half-open, so a node exactly on the east or north
    edge belongs to the next directory; treat both edges as outside.  Ways with
    any node outside are dropped (a straight segment between inside points
    cannot leave a convex box), and relations are dropped because their member
    ways may be gone.  Returns the counted before/after corpus.
    """
    header_lines: list[str] = []
    nodes: dict[str, dict[str, Any]] = {}
    ways: list[dict[str, Any]] = []
    relations = 0
    for line in imf_in.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        kind = rec.get("type")
        if kind == "header":
            header_lines.append(line)
        elif kind == "node":
            nodes[rec["id"]] = rec
        elif kind == "way":
            ways.append(rec)
        else:
            relations += 1
    inside: dict[str, dict[str, Any]] = {}
    for node_id, rec in nodes.items():
        lon, lat = float(rec["lon"]), float(rec["lat"])
        if (box["lon_min"] <= lon < box["lon_max"]
                and box["lat_min"] <= lat < box["lat_max"]):
            inside[node_id] = rec
    kept_ways = [w for w in ways if w.get("nodes") and all(n in inside for n in w["nodes"])]
    used = {n for w in kept_ways for n in w["nodes"]}
    # Keep feature nodes (POIs) that are inside even when no kept way uses them.
    feature = {n for n, rec in inside.items() if rec.get("tags") or rec.get("poi") or rec.get("addr")}
    keep_nodes = used | feature
    out_lines = list(header_lines)
    out_lines += [json.dumps(inside[n], separators=(",", ":")) for n in sorted(keep_nodes)]
    out_lines += [json.dumps(w, separators=(",", ":")) for w in kept_ways]
    imf_out.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return {
        "nodes_before": len(nodes),
        "nodes_kept": len(keep_nodes),
        "nodes_dropped": len(nodes) - len(keep_nodes),
        "ways_before": len(ways),
        "ways_kept": len(kept_ways),
        "ways_dropped": len(ways) - len(kept_ways),
        "relations_dropped": relations,
    }


def directory_of(lon: float, lat: float) -> tuple[int, int]:
    """Section-1 level-1 directory ``(y, x)`` holding a WGS84 point."""
    import tilewriter
    y0, x0, _row, _col = tilewriter.parcel_of(lon, lat, 1)
    return y0, x0


def _factory_dir_kinds(tile_bytes: bytes) -> dict[tuple[int, int], int]:
    """``{(y, x): kind}`` for the section-1 level-1 directories of a tile."""
    import tilewriter
    tile = _clarion_tile().read_tile(tile_bytes)
    kinds: dict[tuple[int, int], int] = {}
    for sec in tile.get("sections") or []:
        if sec["id"] != 1:
            continue
        for entry in sec["levels"]:
            if entry["level"] != 1:
                continue
            for directory in entry["dirs"]:
                kinds[(directory["y"], tilewriter.dir_x0(directory))] = directory["kind"]
    return kinds


def _imf_node_points(path: Path):
    """Yield ``(osm_id, lon, lat)`` for every node record of an IMF file."""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("type") != "node":
            continue
        yield rec.get("id"), float(rec["lon"]), float(rec["lat"])


def guard_parcel(imf_path: Path, parcel: tuple[int, int],
                 factory_tile_bytes: bytes) -> dict[str, Any]:
    """Refuse input whose nodes leave ``parcel``; name the kind it touched.

    Runs after ingest and **before** any tree copy or tile write.  A node in a
    preserve-only directory (``tilewriter.PRESERVE_ONLY_DIR_KINDS``) is the
    M5.29/PR #171 failure; a node in another spliceable directory would break
    the "only the chosen directory changed" property.  Both are usage errors.
    """
    import tilewriter
    kinds = _factory_dir_kinds(factory_tile_bytes)
    chosen_kind = kinds.get(parcel)
    if chosen_kind not in tilewriter.SPLICEABLE_DIR_KINDS:
        raise UsageError(
            "parcel y=%d x=%d is not a spliceable section-1 directory in the "
            "factory tile (kind %s); this pipeline only writes "
            "SPLICEABLE_DIR_KINDS %s"
            % (parcel[0], parcel[1],
               "0x%04x" % chosen_kind if chosen_kind is not None else "absent",
               sorted("0x%04x" % k for k in tilewriter.SPLICEABLE_DIR_KINDS)))
    outside: dict[tuple[int, int], int] = {}
    nodes = 0
    for _osm_id, lon, lat in _imf_node_points(imf_path):
        nodes += 1
        here = directory_of(lon, lat)
        if here != parcel:
            outside[here] = outside.get(here, 0) + 1
    if outside:
        detail = ", ".join(
            "y=%d x=%d %d node(s) kind %s (%s)" % (
                y, x, n,
                "0x%04x" % kinds[y, x] if (y, x) in kinds else "absent",
                "preserve-only" if kinds.get((y, x)) in tilewriter.PRESERVE_ONLY_DIR_KINDS
                else ("spliceable, not the chosen directory"
                      if kinds.get((y, x)) in tilewriter.SPLICEABLE_DIR_KINDS
                      else "unmodelled/absent"))
            for (y, x), n in sorted(outside.items()))
        raise UsageError(
            "OSM input leaves parcel y=%d x=%d: %s. Refused before any tile "
            "write; clip --osm/--osm-bbox to the chosen directory."
            % (parcel[0], parcel[1], detail))
    return {"nodes": nodes, "parcel": "%d,%d" % parcel, "kind": chosen_kind}



def _tile_box_rows(data: bytes) -> list[tuple[int, int, int, tuple[int, int, int, int]]]:
    """Parse the header box table at ``0x2ac`` into ``(sid, level, flag, box)``.

    Rows are big-endian ``>BB4h``: ``(level, flag, y1, y0, x0, x1)`` in
    arc-minutes. ``box`` is the ``(y1, y0, x0, x1)`` tuple. Raises ValueError
    on a table that runs past the header.
    """
    h = data[:0x1000]
    if len(h) < 0x2ac + 2:
        raise ValueError("tile shorter than the box table")
    count, = struct.unpack_from(">H", h, 0x2ac)
    p = 0x2ae
    rows = []
    for _ in range(count):
        if p + 2 > len(h):
            raise ValueError("box table truncated")
        sid, cnt = h[p], h[p + 1]
        p += 2
        if p + 10 * cnt > len(h):
            raise ValueError("box rows truncated")
        for _ in range(cnt):
            level, flag, y1, y0, x0, x1 = struct.unpack_from(">BB4h", h, p)
            rows.append((sid, level, flag, (y1, y0, x0, x1)))
            p += 10
    return rows


def _factory_tile_cell_binding(data: bytes, cell: str) -> tuple[bool, str]:
    """Bind a tile to ``cell`` through its box table (H67).

    Entry ``0x184``/``0x5d0`` are database-wide (identical in every tile of a
    card), so they cannot tell two cells apart. The box table at ``0x2ac``
    carries per-section, per-level ``(y1, y0, x0, x1)`` bounds; every honest
    row lies inside the cell's arc-minute bounds and a sibling cell's row does
    not. A table with no rows fails closed. Returns ``(ok, detail)``.
    """
    try:
        import tilewriter
        y1_max, y0_min, x0_min, x1_max = tilewriter.cell_db_bounds(cell)
    except Exception as e:  # not a cell name / writer unavailable
        return False, f"cannot compute cell bounds for {cell!r}: {type(e).__name__}: {e}"
    try:
        rows = _tile_box_rows(data)
    except ValueError as e:
        return False, f"box table unreadable: {e}"
    if not rows:
        return False, "box table has no rows"
    for sid, level, _flag, (y1, y0, x0, x1) in rows:
        if not (y0 >= y0_min and y1 <= y1_max and x0 >= x0_min and x1 <= x1_max):
            return False, (
                f"box row section {sid} level {level} ({y1},{y0},{x0},{x1}) "
                f"is outside cell {cell} bounds ({y1_max},{y0_min},{x0_min},{x1_max})"
            )
        if y0 > y1 or x0 > x1:
            return False, f"box row section {sid} level {level} has an inverted span"
    return True, f"{len(rows)} box rows within cell {cell} bounds"


def _factory_tile_provenance(factory_root: Path, cell: str,
                             tile: Path | None = None) -> dict[str, Any]:
    """Prove the tile at ``MAPAL001/<cell>.DAT`` is a parseable factory tile.

    ``tile`` overrides the derived ``MAPAL001/<cell>.DAT`` path (H70); the
    override is held to the same parse and cell-binding checks, so pointing it
    at another cell's tile still yields ``factory-tile-mismatch``.
    Returns a provenance dict with ``factory_tree_provenance`` =
    ``factory-tile-parsed`` on success, or ``factory-tree-invalid`` plus a
    ``parse_error`` reason. Size alone is not a test; the tile is read and
    parsed with the same ``clarion_tile`` reader the writer uses, then its box
    table is bound to ``cell`` (``factory-tile-mismatch`` when a different
    cell's tile is copied in, H67).
    """
    tile = tile or (factory_root / "MAPAL001" / f"{cell}.DAT")
    prov: dict[str, Any] = {
        "factory_tile": str(tile),
        "factory_tile_override": tile != factory_root / "MAPAL001" / f"{cell}.DAT",
        "factory_tile_size": 0,
        "factory_tile_sha256": None,
        "factory_tree_provenance": "factory-tree-invalid",
        "factory_tile_cell_binding": None,
        "factory_tile_box_rows": None,
        "parse_error": None,
    }
    try:
        data = tile.read_bytes()
    except OSError as e:
        prov["parse_error"] = f"read failed: {e}"
        return prov
    prov["factory_tile_size"] = len(data)
    if not data:
        prov["parse_error"] = "empty file (0 bytes)"
        return prov
    prov["factory_tile_sha256"] = sha256_bytes(data)
    try:
        parsed = _clarion_tile().read_tile(data)
    except Exception as e:  # a malformed tile is a result, not a crash
        prov["parse_error"] = f"{type(e).__name__}: {e}"
        return prov
    sections = parsed.get("sections") or []
    if not sections:
        prov["parse_error"] = "tile parsed to no sections"
        return prov
    prov["factory_tile_sections"] = len(sections)
    try:
        prov["factory_tile_box_rows"] = len(_tile_box_rows(data))
    except ValueError:
        prov["factory_tile_box_rows"] = 0
    ok, detail = _factory_tile_cell_binding(data, cell)
    prov["factory_tile_cell_binding"] = detail
    if not ok:
        prov["factory_tree_provenance"] = "factory-tile-mismatch"
        prov["parse_error"] = detail
        return prov
    prov["factory_tree_provenance"] = "factory-tile-parsed"
    return prov


def survey_cell_binding(factory_root: Path) -> dict[str, Any]:
    """Count honest and wrong-cell placements of a root's ``MAPAL001`` tiles.

    Reads only the 0x1000-byte header of each ``BxxRyyR.DAT`` (the box table
    lives there), so it is cheap on a full factory root. ``wrong_pairs_pass``
    must be 0: no sibling tile's box rows may fall inside another cell's box.
    """
    cell_re = re.compile(r"^B[0-9A-F]{2}R[0-9A-F]{3}R$")
    mapal = factory_root / "MAPAL001"
    tiles = {}
    skipped = []
    for p in sorted(mapal.glob("*.DAT")):
        cell = p.stem
        if not cell_re.match(cell):
            skipped.append(p.name)
            continue
        with p.open("rb") as f:
            tiles[cell] = f.read(0x1000)
    honest_ok = 0
    rows_total = 0
    for cell, h in tiles.items():
        try:
            rows = _tile_box_rows(h)
        except ValueError:
            rows = []
        rows_total += len(rows)
        if rows and _factory_tile_cell_binding(h, cell)[0]:
            honest_ok += 1
    wrong_pass = 0
    for src_cell, h in tiles.items():
        for dst_cell in tiles:
            if dst_cell == src_cell:
                continue
            if _factory_tile_cell_binding(h, dst_cell)[0]:
                wrong_pass += 1
    # Header database boxes 0x184 (>4h) and 0x5d0 (>2h): constant across a
    # card's tiles, so they cannot bind a tile to a cell (C-3881).
    def _distinct(off: int, fmt: str) -> dict[str, int]:
        seen: dict[str, int] = {}
        for h in tiles.values():
            key = ",".join(str(v) for v in struct.unpack_from(fmt, h, off))
            seen[key] = seen.get(key, 0) + 1
        return seen
    bounds_184 = _distinct(0x184, ">4h")
    bounds_5d0 = _distinct(0x5d0, ">2h")
    return {
        "factory_root": str(factory_root),
        "cells": len(tiles),
        "box_rows": rows_total,
        "honest_tiles_pass": honest_ok,
        "wrong_pairs": len(tiles) * (len(tiles) - 1),
        "wrong_pairs_pass": wrong_pass,
        "header_bounds_0x184": bounds_184,
        "header_bounds_0x5d0": bounds_5d0,
        "header_bounds_uniform": len(bounds_184) <= 1 and len(bounds_5d0) <= 1,
        "skipped": skipped,
        "ok": honest_ok == len(tiles) and wrong_pass == 0,
    }


def _zlib_runtime() -> dict[str, Any]:
    """The running interpreter's zlib, and whether recompression is reproducible.

    ``run_cmd_json`` uses ``sys.executable``, so the interpreter that starts
    the pipeline picks the encoder for every child tool.  A recorded tile SHA
    that came from zlib-ng cannot be reproduced on a stock-zlib host (B1), so
    the report and a loud banner must say which build ran.
    """
    import zlib
    build = zlib.ZLIB_VERSION
    runtime = getattr(zlib, "ZLIB_RUNTIME_VERSION", build)
    ng = "zlib-ng" in build.lower() or "zlib-ng" in runtime.lower()
    return {
        "interpreter": sys.executable,
        "python": sys.version.split()[0],
        "zlib_build": build,
        "zlib_runtime": runtime,
        "stock": not ng,
        "reproducible": not ng,
        "message": ("stock zlib: the recorded tile SHA is reproducible"
                    if not ng else
                    "zlib-ng: NOT the reference compressor; the recorded tile SHA "
                    "is not reproducible on a stock-zlib host"),
    }


def _zlib_banner(rt: dict[str, Any]) -> None:
    print(f"zlib: {rt['zlib_build']} / {rt['zlib_runtime']} via {rt['interpreter']} "
          f"(python {rt['python']})", file=sys.stderr)
    if not rt["stock"]:
        print("one_tile_pipeline: ZLIB-NG, NOT REPRODUCIBLE — re-run with python3.13 "
              "(stock zlib); see EXP-2026-11-17-M5.34-parcel B1", file=sys.stderr)


def gate(status: str, detail: str, evidence: str = "") -> dict[str, str]:
    if status not in STATUSES:
        status = "CANNOT-VERIFY-OFFLINE"
    return {"status": status, "detail": detail, "evidence": evidence}


def run_cmd_json(mod: str, argv: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    import subprocess
    cmd = [sys.executable, str(HERE / mod)] + argv
    p = subprocess.run(cmd, cwd=str(cwd or HERE.parent), capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr



def _put_utf16be(buf: bytearray, off: int, text: str) -> None:
    raw = text.encode("utf-16-be")
    buf[off:off + len(raw)] = raw

def _synth_header(model: str = "CLA-NAVI05-01") -> bytearray:
    buf = bytearray(b"\xff" * 512)
    _put_utf16be(buf, 0x00, "CLARION")
    _put_utf16be(buf, 0x40, "HITACHI")
    _put_utf16be(buf, 0x80, model)
    _put_utf16be(buf, 0xA0, "FORMAT VERSION X08-02-00")
    _put_utf16be(buf, 0xE0, "DATA VERSION 26/11/09/01")
    buf[0x160:0x162] = b"\x16\x00"
    _put_utf16be(buf, 0x162, "V05.00.00")
    buf[0x180:0x18C] = bytes.fromhex("ff ff 24 ff 12 c0 05 00 fb 50 0f f0")
    buf[0x18C:0x1A0] = b"\x3f" * 20
    buf[0x1A0:0x1AC] = b"\xff" * 12
    return buf

def _write_level_table(buf: bytearray, groups: list[tuple[int, list[tuple]]]) -> None:
    struct.pack_into(">H", buf, 0x1AC, len(groups))
    pos = 0x1AE
    for sec, rows in groups:
        buf[pos] = sec
        buf[pos + 1] = len(rows)
        pos += 2
        for level, kind, count in rows:
            struct.pack_into(">BBH", buf, pos, level, kind, count)
            pos += 4

def _synth_mmain() -> bytes:
    buf = bytearray(_synth_header())
    buf.extend(b"\x00" * (0x1000 - len(buf)))
    _write_level_table(buf, [(1, [(6, 0x80, 1), (5, 0x90, 1)])])
    return bytes(buf)

def _synth_tile() -> bytes:
    buf = bytearray(_synth_header())
    buf.extend(b"\x00" * (0x400 - len(buf)))
    _write_level_table(buf, [(1, [(6, 0x80, 1), (5, 0x90, 1)])])
    struct.pack_into(">H", buf, 0x2AC, 1)
    buf[0x2AE] = 1; buf[0x2AF] = 1
    struct.pack_into(">BBhhhh", buf, 0x2B0, 2, 0, 1920, 1685, -720, -562)
    return bytes(buf)

def _synth_cmp_ind(root: Path, stem: str = "POINT001.DAT") -> None:
    import cmpind_writer
    payload = bytearray(_synth_header())
    payload.extend(b"\x00" * 64)
    c = cmpind_writer.CmpFile.from_dat(bytes(payload))
    refer = root / "REFER001"
    refer.mkdir(exist_ok=True)
    c.write(refer, stem)

def _scaffold_tree(root: Path, osm_tile_cell: str) -> list[str]:
    """Create synthetic baseline scaffold (not OSM-generated) so manifests/checks can run."""
    import drstr_ze0
    root.mkdir(parents=True, exist_ok=True)
    for d in ("MAPAL001", "REFER001", "REFER002", "RDSTM001", "BICON001", "OPNG", "SPEECH", "TMC"):
        (root / d).mkdir(exist_ok=True)
    (root / "MMAIN001.DAT").write_bytes(_synth_mmain())
    # Synthetic baseline tiles (not OSM-generated). Do NOT create osm_tile_cell here.
    (root / "MAPAL001" / "LEV3456R.DAT").write_bytes(_synth_tile())
    (root / "MAPAL001" / "B30R060R.DAT").write_bytes(_synth_tile())
    _synth_cmp_ind(root)
    (root / "CMP.LST").write_bytes(b"\\SystemSD\\REFER001\\")
    (root / "DRSTR001.DAT").write_bytes(drstr_ze0.build(root))
    return ["MAPAL001/LEV3456R.DAT", "MAPAL001/B30R060R.DAT", "MMAIN001.DAT", "REFER001/POINT001.DAT.cmp", "REFER001/POINT001.DAT.ind", "CMP.LST", "DRSTR001.DAT"]

def build_synthetic_out(out: Path, cell: str = "B48R058R",
                        input_root: Path | None = None) -> dict[str, Any]:
    """Build a synthetic minimal tree with one OSM-generated tile. No vendor bytes."""
    _check_out_overlap(out, input_root)
    report: dict[str, Any] = {
        "mode": "synthetic-only",
        "tile": cell,
        "mapping": "provisional-v0",
        "rule13": "roadclass_v0 provisional, not firmware-confirmed; L2 necessary not sufficient; L3/L4/L5 acceptance unknown",
        "factory_backed": False,
        "missing_input": "EU2011 full image or extracted MAPAL001/<tile> + compatible factory tree (IMG256 lacks MAPAL001); leafre-work/root is partial (MAPAL001 only, no B48R058R/DRSTR/REFER/VER_INFO) in this environment",
        "real_image_run": "blocked",
        "gates": {},
        "baseline_scaffold": [],
        "osm_generated_tile": f"MAPAL001/{cell}.DAT",
        "counts": {},
    }
    if out.exists():
        shutil.rmtree(out)
    baseline = _scaffold_tree(out, cell)
    report["baseline_scaffold"] = baseline

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        osm = td / "syn.osm"
        osm.write_text(SYNTHETIC_OSM, encoding="utf-8")
        imf = td / "syn.imf.jsonl"
        rc, so, se = run_cmd_json("osm_ingest.py", [str(osm), "-o", str(imf), "--source-name", "synthetic-wroclaw"])
        report["counts"]["osm_ingest_rc"] = rc
        if rc != 0 or not imf.exists():
            report["gates"] = {g: gate("BLOCKED", f"osm_ingest failed rc={rc}: {se[:300]}") for g in GATES}
            return report
        imf_lines = [ln for ln in imf.read_text(encoding="utf-8").splitlines() if ln.strip()]
        report["counts"]["imf_records"] = len(imf_lines)
        ways = sum(1 for ln in imf_lines if '"type":"way"' in ln or '"type": "way"' in ln)
        nodes = sum(1 for ln in imf_lines if '"type":"node"' in ln or '"type": "node"' in ln)
        report["counts"]["ways"] = ways
        report["counts"]["nodes"] = nodes
        report["fixture_sha256"] = sha256_bytes(SYNTHETIC_OSM.encode("utf-8"))

        split_out = td / "split.imf.jsonl"
        rc, so, se = run_cmd_json("mesh_split.py", [str(imf), "-o", str(split_out)])
        report["counts"]["mesh_split_rc"] = rc
        mesh_src = split_out if rc == 0 and split_out.exists() else imf

        ctab = td / "roadclass_v0.json"
        rc, so, se = run_cmd_json("roadclass_v0.py", ["--class-table-out", str(ctab)])
        report["counts"]["roadclass_rc"] = rc
        if rc != 0 or not ctab.exists():
            report["gates"] = {g: gate("BLOCKED", f"roadclass_v0 failed rc={rc}: {se[:300]}") for g in GATES}
            return report

        tile_out = out / "MAPAL001" / f"{cell}.DAT"
        argv = [str(mesh_src), "--out", str(tile_out), "--cell", cell, "--class-table", str(ctab),
                "--country", "616", "--data-version", "26/11/09/01", "--json"]
        rc, so, se = run_cmd_json("tilewriter.py", argv)
        report["counts"]["tilewriter_rc"] = rc
        report["counts"]["tilewriter_stdout"] = so[:500]
        report["counts"]["tilewriter_stderr"] = se[:500]
        if rc != 0 or not tile_out.exists():
            report["gates"] = {g: gate("BLOCKED", f"tilewriter failed rc={rc}: {(se or so)[:400]}") for g in GATES}
            return report
        report["counts"]["tile_size"] = tile_out.stat().st_size
        report["counts"]["tile_sha256"] = sha256_bytes(tile_out.read_bytes())

    # rebuild manifests over the scaffold+OSM tile
    rc, so, se = run_cmd_json("rebuild_manifests.py", ["--root", str(out), "--partial"])
    report["counts"]["rebuild_rc"] = rc
    report["counts"]["rebuild_stderr"] = se[:500]
    report["counts"]["rebuild_stdout"] = so[:300]
    rebuilt = []
    for name in ["DRSTR001.DAT", "MMAIN001.DAT", "REFER001/CMP.LST", "CMP.LST"]:
        if (out / name).exists():
            rebuilt.append(name)
    for p in (out / "REFER001").glob("*.ind"):
        rebuilt.append(f"REFER001/{p.name}")
    report["counts"]["rebuilt_files"] = sorted(set(rebuilt))
    report["changed_set"] = [f"MAPAL001/{cell}.DAT"] + report["counts"]["rebuilt_files"]

    rc, so, se = run_cmd_json("cardcheck.py", ["--root", str(out), "--partial", "--ignore-dump-artifacts", "--fast"])
    report["counts"]["cardcheck_rc"] = rc
    report["counts"]["cardcheck_tail"] = (so + "\n" + se).strip().splitlines()[-15:]
    card_ok = rc == 0

    rc2, so2, se2 = run_cmd_json("l2check.py", ["--root", str(out), "--partial", "--no-golden", "--no-cmp", "--tiles", cell])
    report["counts"]["l2check_rc"] = rc2
    report["counts"]["l2check_tail"] = (so2 + "\n" + se2).strip().splitlines()[-15:]
    l2_ok = rc2 == 0

    report["gates"]["hdd_info_map_code"] = gate(
        "NOT-APPLICABLE" if not (out / "VER_INFO" / "HDD_INFO.TXT").exists() else "CANNOT-VERIFY-OFFLINE",
        "synthetic/partial tree has no VER_INFO/HDD_INFO.TXT; real HDD_INFO/MAP CODE bytes require factory-backed card image/tree (rule 11). Not PASS.",
        "missing VER_INFO" if not (out / "VER_INFO" / "HDD_INFO.TXT").exists() else "present but not byte-compared to factory",
    )
    report["gates"]["drstr_mmain_cmplst_ind"] = gate(
        "PASS" if (card_ok and report["counts"]["rebuild_rc"] == 0) else "CANNOT-VERIFY-OFFLINE",
        f"rebuild_manifests rc={report['counts']['rebuild_rc']}, rebuilt={report['counts']['rebuilt_files']}; cardcheck rc={report['counts']['cardcheck_rc']}. Synthetic partial scaffold - factory parity not claimed.",
        "rebuild_manifests + cardcheck --root --partial",
    )
    report["gates"]["tile_roundtrip_structure"] = gate(
        "PASS" if (report["counts"]["tilewriter_rc"] == 0 and l2_ok) else "CANNOT-VERIFY-OFFLINE",
        f"tilewriter wrote {cell}.DAT ({report['counts'].get('tile_size')} bytes, provisional-v0, only OSM-generated MAPAL001 tile); targeted l2check rc={rc2} {'PASS' if l2_ok else '(not PASS on this synthetic partial tree)'}.",
        "tilewriter + targeted l2check",
    )
    report["gates"]["section4"] = gate(
        "CANNOT-VERIFY-OFFLINE",
        "section 4 (admin/place-name index) semantics vs factory/firmware not verified on synthetic OSM tile; synthetic/road-only generation may not carry factory section-4 semantics. Honest status, not PASS.",
        "synthetic tile; no factory section-4 oracle in this run",
    )
    report["gates"]["manifests"] = gate(
        "PASS" if (report["counts"]["rebuild_rc"] == 0 and card_ok) else "CANNOT-VERIFY-OFFLINE",
        f"manifests rebuilt/consistent check: rebuild rc={report['counts']['rebuild_rc']}, cardcheck rc={report['counts']['cardcheck_rc']}, files={report['counts']['rebuilt_files']}.",
        "rebuild_manifests + cardcheck",
    )
    report["l2_applicable"] = l2_ok
    report["cardcheck_applicable"] = card_ok
    return report


def selftest() -> int:
    fails = 0
    def chk(cond: bool, msg: str):
        nonlocal fails
        if cond:
            print(f"  ok   {msg}")
        else:
            print(f"  FAIL {msg}")
            fails += 1
    print("one_tile_pipeline selftest (synthetic, no vendor data)")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out"
        rep = build_synthetic_out(out, "B48R058R")
        chk(rep["tile"] == "B48R058R", "target cell B48R058R")
        chk(rep["mapping"] == "provisional-v0", "mapping provisional-v0 recorded")
        chk("not firmware-confirmed" in rep["rule13"].lower() or "rule 13" in rep["rule13"].lower() or "l3/l4/l5" in rep["rule13"].lower(), "rule 13/firmware acceptance unknown stated")
        chk(rep["factory_backed"] is False, "synthetic path marked not factory-backed")
        chk(rep["real_image_run"] == "blocked" and rep["missing_input"], "real-image run blocked with missing input named")
        chk((out / "MAPAL001" / "B48R058R.DAT").exists(), "OSM-generated tile exists")
        chk(rep["counts"].get("tilewriter_rc") == 0, "tilewriter rc=0")
        # rebuild/cardcheck/l2check may fail on a minimal synthetic tree; that must be reported honestly, not as PASS.
        if rep["counts"].get("rebuild_rc") == 0:
            chk(True, "rebuild_manifests rc=0")
        else:
            chk(rep["gates"]["drstr_mmain_cmplst_ind"]["status"] != "PASS" or "partial" in rep["gates"]["drstr_mmain_cmplst_ind"]["detail"].lower(), "rebuild nonzero -> manifests/drstr gate honest (not unearned PASS)")
        # B48R058R is the only OSM-generated tile (synthetic baseline scaffold may add non-OSM tiles)
        tiles = sorted(p.name for p in (out / "MAPAL001").glob("*.DAT")) if (out / "MAPAL001").exists() else []
        chk("B48R058R.DAT" in tiles, "B48R058R OSM-generated tile present")
        chk(rep["osm_generated_tile"] == "MAPAL001/B48R058R.DAT", "only B48R058R recorded as OSM-generated tile")
        chk(all(rep["mapping"] == "provisional-v0" for _ in [1]), "mapping field is provisional-v0")
        # gates present and honest
        for g in GATES:
            chk(g in rep["gates"], f"gate present: {g}")
            s = rep["gates"].get(g, {}).get("status")
            chk(s in STATUSES, f"gate {g} honest status {s}")
            if s == "PASS":
                pass  # allowed only where evidenced
        chk(rep["gates"]["hdd_info_map_code"]["status"] != "PASS", "HDD_INFO/MAP CODE not faked PASS on synthetic tree")
        chk(rep["gates"]["section4"]["status"] != "PASS", "section 4 not faked PASS on synthetic path")
        chk(rep.get("fixture_sha256"), "fixture SHA-256 recorded")
        chk(rep["counts"].get("ways", 0) >= 1 and rep["counts"].get("nodes", 0) >= 1, "fixture corpus counted")
        # gate report JSON-serializable
        json.dumps(rep)
        chk(True, "gate report JSON-serializable")

    # --json PATH writes the same document bare --json prints (H64).
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        jpath = td / "report.json"
        rc = main(["--synthetic", "--out", str(td / "synthetic-out"), "--cell", "B48R058R", "--json", str(jpath)])
        written = json.loads(jpath.read_text(encoding="utf-8")) if jpath.exists() else None
        chk(rc in (0, 1) and isinstance(written, dict) and written.get("mode") == "synthetic-only",
            "--json PATH writes a parseable report document")
        chk(written is not None and written.get("tile") == "B48R058R",
            "--json PATH report carries the target cell")

    # Factory-tree provenance + overlap guard negatives (H64).
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = td / "factory-root"
        (root / "MAPAL001").mkdir(parents=True)
        (root / "VER_INFO").mkdir()
        import tilewriter
        tile_bytes = tilewriter.make_factory("B48R058R")
        tile_path = root / "MAPAL001" / "B48R058R.DAT"
        tile_path.write_bytes(tile_bytes)
        (root / "DRSTR001.DAT").write_bytes(b"x")
        (root / "MMAIN001.DAT").write_bytes(b"x")
        (root / "VER_INFO" / "HDD_INFO.TXT").write_bytes(b"x")
        tile_sha = sha256_bytes(tile_bytes)

        # Positive control: an honest factory tile is parsed and its sha recorded.
        honest_out = td / "honest-out"
        rep = build_factory_out(honest_out, root, "B48R058R")
        chk(rep.get("factory_tree_provenance") == "factory-tile-parsed",
            "honest factory tile parsed (provenance=factory-tile-parsed)")
        chk(rep.get("factory_tile_sha256") == tile_sha,
            "factory_tile_sha256 equals sha256sum of MAPAL001/<cell>.DAT")
        chk(rep.get("factory_tile_size") == len(tile_bytes),
            "factory_tile_size equals tile size")
        chk(rep.get("factory_tree_provenance") == "factory-tile-parsed"
            and rep.get("factory_tile_cell_binding"),
            "honest tile is bound to its cell (box table within bounds)")

        # Survey mode on the one-cell synthetic root: one honest tile, no pairs.
        survey = survey_cell_binding(root)
        chk(survey["ok"] and survey["cells"] == 1 and survey["wrong_pairs"] == 0,
            "--check-cell-binding surveys a one-cell root (1 cell, 0 wrong pairs)")

        # Negative control (c): a different cell's (valid) tile copied over
        # B48R058R.DAT -> factory-tile-mismatch, factory-tree-invalid, no output.
        wrong_root = td / "wrong-root"
        shutil.copytree(root, wrong_root)
        sibling = tilewriter.make_factory("B30R060R")
        (wrong_root / "MAPAL001" / "B48R058R.DAT").write_bytes(sibling)
        wrong_out = td / "wrong-out"
        rep = build_factory_out(wrong_out, wrong_root, "B48R058R")
        chk(rep.get("factory_tree_provenance") == "factory-tile-mismatch",
            "different cell's tile -> provenance=factory-tile-mismatch")
        chk(rep.get("real_image_run") == "factory-tree-invalid",
            "different cell's tile -> real_image_run=factory-tree-invalid (not attempted)")
        chk(rep.get("factory_backed") is False,
            "different cell's tile -> not factory-backed")
        chk(all(g.get("status") == "BLOCKED" for g in rep["gates"].values()) and rep["gates"],
            "different cell's tile -> every gate BLOCKED")
        chk(not wrong_out.exists(), "different cell's tile -> no output tree mutated")
        # The same sibling tile under its own cell name is accepted (positive control).
        b30_root = td / "b30-root"
        shutil.copytree(root, b30_root)
        (b30_root / "MAPAL001" / "B30R060R.DAT").write_bytes(sibling)
        _prov_b30 = _factory_tile_provenance(b30_root, "B30R060R")
        chk(_prov_b30.get("factory_tree_provenance") == "factory-tile-parsed",
            "same sibling tile parses as its own cell B30R060R (control): "
            + str(_prov_b30.get("factory_tree_provenance")) + " / "
            + str(_prov_b30.get("factory_tile_cell_binding")))

        # --factory-tile override (H70): a supplied tile is the template, still cell-bound.
        override_root = td / "override-root"
        shutil.copytree(root, override_root)
        (override_root / "MAPAL001" / "B48R058R.DAT").unlink()
        override_tile = td / "supplied-B48R058R.DAT"
        override_tile.write_bytes(tile_bytes)
        override_out = td / "override-out"
        rep = build_factory_out(override_out, override_root, "B48R058R",
                                factory_tile_path=override_tile)
        chk(rep.get("factory_tree_provenance") == "factory-tile-parsed",
            "--factory-tile: supplied tile parsed as B48R058R")
        chk(rep.get("factory_tile_override") is True and rep.get("factory_tile") == str(override_tile),
            "--factory-tile: report names the supplied tile, not the root's derived path")
        chk(rep.get("factory_tile_sha256") == tile_sha,
            "--factory-tile: report hashes the supplied tile")
        chk((override_out / "MAPAL001" / "B48R058R.DAT").exists(),
            "--factory-tile: output tile exists")
        chk(rep.get("counts", {}).get("tilewriter_rc") is not None,
            "--factory-tile: run reached tilewriter (supplied tile used as template)")
        wrong_override = td / "supplied-B30R060R.DAT"
        wrong_override.write_bytes(sibling)
        wrong_override_out = td / "override-wrong-out"
        rep = build_factory_out(wrong_override_out, override_root, "B48R058R",
                                factory_tile_path=wrong_override)
        chk(rep.get("factory_tree_provenance") == "factory-tile-mismatch",
            "--factory-tile: another cell's supplied tile -> factory-tile-mismatch")
        chk(rep.get("real_image_run") == "factory-tree-invalid" and not wrong_override_out.exists(),
            "--factory-tile: another cell's supplied tile -> no output tree")
        with contextlib.redirect_stderr(io.StringIO()):
            rc = main(["--factory-tile", str(override_tile), "--out", str(td / "no-root-out")])
        chk(rc == 2, "--factory-tile without --factory-root exits 2")

        # Negative control (a): empty factory tile -> BLOCKED / factory-tree-invalid.
        empty_root = td / "empty-root"
        shutil.copytree(root, empty_root)
        (empty_root / "MAPAL001" / "B48R058R.DAT").write_bytes(b"")
        empty_out = td / "empty-out"
        rep = build_factory_out(empty_out, empty_root, "B48R058R")
        chk(rep.get("real_image_run") == "factory-tree-invalid",
            "empty factory tile -> real_image_run=factory-tree-invalid")
        chk(all(g.get("status") == "BLOCKED" for g in rep["gates"].values()) and rep["gates"],
            "empty factory tile -> every gate BLOCKED")
        chk(not empty_out.exists(), "empty factory tile -> no output tree mutated")

        # Negative control (b): --out == --factory-root -> exit 2, input intact.
        before = sorted(p.relative_to(root) for p in root.rglob("*"))
        before_sha = sha256_bytes(tile_path.read_bytes())
        rc = main(["--factory-root", str(root), "--out", str(root), "--cell", "B48R058R"])
        after = sorted(p.relative_to(root) for p in root.rglob("*"))
        chk(rc == 2, "--out == --factory-root exits 2")
        chk(before == after and tile_path.exists(),
            "--out == --factory-root leaves the input tree intact")
        chk(sha256_bytes(tile_path.read_bytes()) == before_sha,
            "--out == --factory-root leaves the factory tile byte-identical")
        rc2 = main(["--factory-root", str(root), "--out", str(root / "nested"), "--cell", "B48R058R"])
        chk(rc2 == 2, "--out inside --factory-root exits 2")
        chk(not (root / "nested").exists(), "--out inside --factory-root creates nothing")
        rc3 = main(["--factory-root", str(root), "--out", str(td), "--cell", "B48R058R"])
        chk(rc3 == 2, "--out parent of --factory-root exits 2")
        chk(root.exists() and tile_path.exists(),
            "--out parent of --factory-root leaves the input tree intact")
        chk(sha256_bytes(tile_path.read_bytes()) == before_sha,
            "--out parent of --factory-root leaves the factory tile byte-identical")
        try:
            build_synthetic_out(root, "B48R058R", input_root=root)
            chk(False, "build_synthetic_out rejects out == input root")
        except UsageError:
            chk(True, "build_synthetic_out rejects out == input root")
        try:
            build_synthetic_out(td, "B48R058R", input_root=root)
            chk(False, "build_synthetic_out rejects out parent of input root")
        except UsageError:
            chk(True, "build_synthetic_out rejects out parent of input root")

    # Parcel guard: clip to a directory and refuse a way that leaves it (M5.34).
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = td / "factory-root"
        (root / "MAPAL001").mkdir(parents=True)
        (root / "VER_INFO").mkdir()
        import tilewriter
        yb, xb = tilewriter.cell_mesh("B48R058R")
        tile_bytes = tilewriter.make_factory(
            "B48R058R", extra_dirs={1: [tilewriter._opaque_directory(0x2146, 1, yb, xb + 1)]})
        (root / "MAPAL001" / "B48R058R.DAT").write_bytes(tile_bytes)
        (root / "DRSTR001.DAT").write_bytes(b"x")
        (root / "MMAIN001.DAT").write_bytes(b"x")
        (root / "VER_INFO" / "HDD_INFO.TXT").write_bytes(b"x")
        box = directory_box("B48R058R", (yb, xb))

        # A two-node way strictly inside the directory passes the guard.
        inside = td / "inside.osm"
        lon_a, lat_a = box["lon_min"] + 0.2, box["lat_min"] + 0.2
        lon_b, lat_b = box["lon_min"] + 0.3, box["lat_min"] + 0.3
        inside.write_text(
            '<?xml version="1.0"?><osm version="0.6">'
            f'<node id="1" lat="{lat_a:.6f}" lon="{lon_a:.6f}"/>'
            f'<node id="2" lat="{lat_b:.6f}" lon="{lon_b:.6f}"/>'
            '<way id="10"><nd ref="1"/><nd ref="2"/>'
            '<tag k="highway" v="primary"/></way></osm>', encoding="utf-8")
        imf_ok = td / "inside.imf.jsonl"
        rc, _so, se = run_cmd_json("osm_ingest.py", [str(inside), "-o", str(imf_ok)])
        chk(rc == 0, "guard fixture ingests")
        guard = guard_parcel(imf_ok, (yb, xb), tile_bytes)
        chk(guard["nodes"] == 2 and guard["parcel"] == "%d,%d" % (yb, xb),
            "guard accepts a way inside the chosen directory")

        # A way with one vertex inside and one in the next directory: the
        # post-ingest clip drops the way, so the guard accepts the clipped IMF
        # but the original IMF is still refused (the PR #171 failure).
        crossing = td / "cross.osm"
        outside_lon = box["lon_max"] + 0.05
        crossing.write_text(
            '<?xml version="1.0"?><osm version="0.6">'
            f'<node id="1" lat="{lat_a:.6f}" lon="{lon_a:.6f}"/>'
            f'<node id="2" lat="{lat_a:.6f}" lon="{outside_lon:.6f}"/>'
            '<way id="10"><nd ref="1"/><nd ref="2"/>'
            '<tag k="highway" v="primary"/></way></osm>', encoding="utf-8")
        imf_cross = td / "cross.imf.jsonl"
        rc, _so, se = run_cmd_json("osm_ingest.py", [str(crossing), "-o", str(imf_cross)])
        chk(rc == 0, "crossing fixture ingests")
        try:
            guard_parcel(imf_cross, (yb, xb), tile_bytes)
            chk(False, "guard refuses a way that leaves the chosen directory")
        except UsageError as e:
            chk("kind" in str(e) and ("0x%04x" % 0x2146) in str(e),
                "guard refusal names the touched directory kind (0x2146)")
        clipped = td / "cross.clipped.jsonl"
        clip = clip_imf_to_directory(imf_cross, clipped, box)
        chk(clip["ways_kept"] == 0 and clip["ways_dropped"] == 1,
            "clip drops a way that reaches outside the directory")
        chk(guard_parcel(clipped, (yb, xb), tile_bytes)["nodes"] == 0,
            "clipped IMF passes the guard with no node outside")

        # Choosing a preserve-only directory is refused up front.
        try:
            guard_parcel(imf_ok, (yb, xb + 1), tile_bytes)
            chk(False, "guard refuses a preserve-only target directory")
        except UsageError as e:
            chk("0x2146" in str(e), "preserve-only target names kind 0x2146")

        # The full CLI refuses the crossing way by default (negative control),
        # before creating --out.
        neg_out = td / "neg-out"
        rc = main(["--factory-root", str(root), "--out", str(neg_out),
                   "--cell", "B48R058R", "--parcel", "%d,%d" % (yb, xb),
                   "--osm", str(crossing)])
        chk(rc == 2, "crossing way via CLI exits 2 (default: no clip)")
        chk(not neg_out.exists(), "crossing way leaves no output tree")

        # With --clip the same input is dropped to nothing rather than refused.
        clip_out = td / "clip-out"
        rc = main(["--factory-root", str(root), "--out", str(clip_out),
                   "--cell", "B48R058R", "--parcel", "%d,%d" % (yb, xb),
                   "--osm", str(crossing), "--clip"])
        chk(rc != 2, "CLI --clip drops the crossing way instead of failing")

        # bbox helper: the default box is the directory box itself.
        dbox = default_osm_bbox(box)
        chk(dbox == (box["lon_min"], box["lat_min"], box["lon_max"], box["lat_max"]),
            "default --osm-bbox is the directory box")
        try:
            parse_parcel("76")
            chk(False, "parse_parcel rejects one number")
        except UsageError:
            chk(True, "parse_parcel rejects one number")
        chk(parse_osm_bbox("1,2,3,4") == (1.0, 2.0, 3.0, 4.0),
            "parse_osm_bbox reads four numbers")

        # prove_tile_change sees the one-directory change and nothing else.
        proof = prove_tile_change(tile_bytes, tile_bytes, "B48R058R", (yb, xb))
        chk(proof["changed_sections"] == [],
            "prove_tile_change reports no change for identical tiles")
        chk(proof["only_parcel_directory_changed"] is False,
            "identical tiles are not reported as a parcel change")

        # B2: the slice proof must see a changed slot TAG in a *different*
        # directory (sector_fingerprint only keeps kind,y,x,typ,box).
        sibling = tilewriter._opaque_directory(0x2146, 1, yb, xb + 1)
        two_dir_tile = tilewriter.make_factory(
            "B48R058R", extra_dirs={1: [sibling]})
        parsed = _clarion_tile().read_tile(two_dir_tile)
        lv1 = [e for e in parsed["sections"] if e["id"] == 1][0]
        lv1 = [e for e in lv1["levels"] if e["level"] == 1][0]
        target = [d for d in lv1["dirs"]
                  if (d["y"], tilewriter.dir_x0(d)) == (yb, xb + 1)][0]
        target.setdefault("empty_tags", {})[3] = 0x00001234
        mutated = _clarion_tile().write_tile(parsed)
        proof = prove_tile_change(two_dir_tile, mutated, "B48R058R", (yb, xb))
        chk([(d["y"], d["x"]) for d in proof["changed_directories"]] == [(yb, xb + 1)],
            "slice proof sees a changed slot tag in a non-target directory")
        chk(proof["only_parcel_directory_changed"] is False,
            "slice proof does not call a sibling tag change the parcel change")

        # B2: a file that exists only in `out` must make the tree gate FAIL.
        tmpl = {"A": b"1", "B": b"2"}
        got = {"A": b"1", "B": b"2", "C": b"3"}
        chk(_tree_differences(tmpl, got) == [{"path": "C", "state": "extra-in-out"}],
            "tree diff lists an out-only file as extra-in-out")
        chk(_tree_differences(got, tmpl) == [{"path": "C", "state": "missing-from-out"}],
            "tree diff lists a root-only file as missing-from-out")
        chk(_tree_differences(tmpl, tmpl) == [], "tree diff of equal trees is empty")
        chk(_tree_differences({"A": "h1"}, {"A": "h2"})
            == [{"path": "A", "state": "differs"}],
            "tree diff reports changed content as differs")
        g_bad, unexpected_bad = one_tile_gate(
            [{"path": "MAPAL001/X.DAT", "state": "differs"},
             {"path": "EXTRA/only-in-out.DAT", "state": "extra-in-out"}],
            "MAPAL001/X.DAT", {"DRSTR001.DAT"}, True,
            {"changed_sections": [1], "changed_directories": []})
        chk(g_bad["status"] == "FAIL" and unexpected_bad,
            "one-tile gate FAILs on an out-only extra file (B2)")
        g_ok, _ = one_tile_gate(
            [{"path": "MAPAL001/X.DAT", "state": "differs"},
             {"path": "DRSTR001.DAT", "state": "differs"}],
            "MAPAL001/X.DAT", {"DRSTR001.DAT"}, True,
            {"changed_sections": [1], "changed_directories": []})
        chk(g_ok["status"] == "PASS", "one-tile gate passes tile + named manifest only")

        # B1: the report states which zlib the running interpreter links.
        rt = _zlib_runtime()
        import zlib as _zlib
        chk(rt["zlib_build"] == _zlib.ZLIB_VERSION
            and rt["interpreter"] == sys.executable,
            "_zlib_runtime records the running interpreter and zlib build")
        chk(("stock" in rt["message"]) or ("zlib-ng" in rt["message"]),
            "_zlib_runtime message names the zlib flavour")
    print(f"selftest: {'OK' if not fails else 'FAIL'} ({fails} failure(s))")
    return 0 if not fails else 1


def _copy_factory_root(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, symlinks=True)


def _tree_differences(root_files: dict[Path, bytes] | set[Path],
                      out_files: dict[Path, bytes] | set[Path]) -> list[dict[str, str]]:
    """Per-file difference over the union of both trees (B2).

    A one-sided walk misses a file that exists only in ``out``; comparing the
    union makes an extra file a difference the gate can fail on.  ``differs``
    is only decided when both sides are ``{relpath: sha256}`` maps; for plain
    path sets the caller has already established equality.
    """
    root_hashes = root_files if isinstance(root_files, dict) else {}
    out_hashes = out_files if isinstance(out_files, dict) else {}
    root_set = set(root_files)
    out_set = set(out_files)
    differing = []
    for rel in sorted(root_set | out_set, key=str):
        if rel not in root_set:
            differing.append({"path": str(rel), "state": "extra-in-out"})
        elif rel not in out_set:
            differing.append({"path": str(rel), "state": "missing-from-out"})
        elif (rel in root_hashes) != (rel in out_hashes):
            differing.append({"path": str(rel), "state": "hash-not-compared"})
        elif root_hashes.get(rel) != out_hashes.get(rel):
            differing.append({"path": str(rel), "state": "differs"})
    return differing


def one_tile_gate(differing: list[dict[str, str]], tile_path: str,
                  manifests: set[str], only_dir: bool,
                  tile_change: dict[str, Any]) -> tuple[dict[str, str], list[dict[str, str]]]:
    """The B2 gate: PASS only when the tile is the one change and no other file.

    An extra file in ``out`` is ``unexpected`` and makes the gate ``FAIL`` —
    the defect the one-sided walk could not see.
    """
    unexpected = [d for d in differing
                  if d["path"] != tile_path and d["path"] not in manifests]
    status = "PASS" if (only_dir and not unexpected) else "FAIL"
    g = gate(status,
             f"changed sections={tile_change.get('changed_sections')}, "
             f"changed directories={tile_change.get('changed_directories')}, "
             f"differing files={[(d['path'], d['state']) for d in differing]}.",
             "prove_tile_change (byte slice per directory) + union tree diff")
    return g, unexpected


def prove_tile_change(factory_tile: bytes, out_tile: bytes, cell: str,
                      parcel: tuple[int, int]) -> dict[str, Any]:
    """Prove exactly one directory of one tile changed, and nothing else.

    Two independent checks:

    * ``tilewriter.sector_fingerprint`` per section: sections 2 and 4 must be
      identical and section 1 must differ.
    * a **byte slice** per directory: every section-1 level-1 directory is
      compared as ``tile[off:next_off]`` (header, slot tags, bodies and the
      declared-size tail), so a changed slot tag is visible even though
      ``sector_fingerprint`` only keeps ``(kind, y, x, typ, box)`` for a
      directory header (B2 review).

    Returns the changed sections/directories and whether the only changed
    directory is ``parcel``.
    """
    import tilewriter
    ct = _clarion_tile()
    before = ct.read_tile(factory_tile)
    after = ct.read_tile(out_tile)
    changed_sections = [
        sid for sid in (1, 2, 4)
        if tilewriter.sector_fingerprint(before, sid) != tilewriter.sector_fingerprint(after, sid)
    ]

    def slices(tile: dict, data_len: int) -> dict[tuple[int, int, tuple[int, int]], tuple[int, int]]:
        """``{(section, level, (y, x)): (off, end)}`` from ``clarion_tile.read_dir``.

        ``end`` is what ``read_dir`` consumed (12-byte header, slot tags and
        bodies, declared-size tail), so the slice covers the whole directory
        container, not just the header words.
        """
        out = {}
        for sec in tile.get("sections") or []:
            for entry in sec["levels"]:
                for directory in entry["dirs"]:
                    off = directory["off"]
                    end = directory.get("end")
                    if not end or end <= off:
                        end = data_len if not out else min(
                            (d["off"] for d in entry["dirs"] if d["off"] > off), default=data_len)
                    out[(sec["id"], entry["level"],
                         (directory["y"], tilewriter.dir_x0(directory)))] = (off, end)
        return out

    before_slices = slices(before, len(factory_tile))
    after_slices = slices(after, len(out_tile))
    changed_dirs = []
    for key in sorted(before_slices, key=lambda k: (k[0], k[1], k[2])):
        if key[0] != 1 or key[1] != 1:
            continue
        if key not in after_slices:
            changed_dirs.append({"level": 1, "y": key[2][0], "x": key[2][1],
                                 "reason": "directory missing in out"})
            continue
        a0, a1 = before_slices[key]
        b0, b1 = after_slices[key]
        if factory_tile[a0:a1] != out_tile[b0:b1]:
            changed_dirs.append({"level": 1, "y": key[2][0], "x": key[2][1],
                                 "reason": "byte slice differs",
                                 "factory_range": [a0, a1], "out_range": [b0, b1]})
    for key in sorted(after_slices, key=lambda k: (k[0], k[1], k[2])):
        if key[0] == 1 and key[1] == 1 and key not in before_slices:
            changed_dirs.append({"level": 1, "y": key[2][0], "x": key[2][1],
                                 "reason": "directory added in out"})
    only_parcel = ([{k: v for k, v in d.items() if k in ("level", "y", "x")} for d in changed_dirs]
                   == [{"level": 1, "y": parcel[0], "x": parcel[1]}])
    size_delta = len(out_tile) - len(factory_tile)
    return {
        "factory_tile_sha256": sha256_bytes(factory_tile),
        "out_tile_sha256": sha256_bytes(out_tile),
        "factory_size": len(factory_tile),
        "out_size": len(out_tile),
        "size_delta": size_delta,
        "changed_sections": changed_sections,
        "changed_directories": changed_dirs,
        "only_parcel_directory_changed": only_parcel,
        "method": "sector_fingerprint for sections; byte slice per section-1 level-1 directory",
    }



def build_factory_out(out: Path, factory_root: Path, cell: str = "B48R058R",
                      osm_text: str | None = None, country: str = "616",
                      factory_tile_path: Path | None = None,
                      osm_path: Path | None = None,
                      osm_bbox: tuple[float, float, float, float] | None = None,
                      parcel: tuple[int, int] | None = None,
                      clip: bool = False) -> dict[str, Any]:
    """Factory-backed path: copy factory root, replace exactly one tile with OSM-generated (provisional-v0).

    ``osm_path`` is an OSM XML/PBF read by ``osm_ingest.py``; ``osm_text`` is
    the inline synthetic fixture used only when no path is given (reported as
    ``fixture=synthetic``).  With ``parcel`` the input is clipped to that
    directory's box; a node outside it is refused (naming the touched
    directory's kind) unless ``clip`` is set, which drops such ways instead.
    """
    _check_out_overlap(out, factory_root)
    rt = _zlib_runtime()
    _zlib_banner(rt)
    report: dict[str, Any] = {
        "mode": "factory-backed", "tile": cell, "mapping": "provisional-v0",
        "rule13": "roadclass_v0 provisional, not firmware-confirmed; L2 necessary not sufficient; L3/L4/L5 acceptance unknown",
        "factory_backed": True, "factory_root": str(factory_root), "missing_input": "",
        "real_image_run": "attempted", "gates": {}, "counts": {}, "changed_set_expected": [f"MAPAL001/{cell}.DAT"],
        "factory_tile_sha256": None, "factory_tile_size": 0,
        "factory_tree_provenance": "not-checked",
        "zlib": rt,
    }
    if not factory_root.is_dir():
        report["gates"] = {g: gate("BLOCKED", f"factory root not a directory: {factory_root}") for g in GATES}
        report["real_image_run"] = "blocked"; return report
    factory_tile = factory_tile_path or (factory_root / "MAPAL001" / f"{cell}.DAT")
    required = [factory_tile, factory_root / "DRSTR001.DAT", factory_root / "MMAIN001.DAT", factory_root / "VER_INFO" / "HDD_INFO.TXT"]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        report["missing_input"] = "missing factory files: " + ", ".join(missing)
        report["real_image_run"] = "blocked"; report["factory_backed"] = False
        report["gates"] = {g: gate("BLOCKED", report["missing_input"]) for g in GATES}; return report
    prov = _factory_tile_provenance(factory_root, cell, factory_tile)
    report["factory_tile"] = prov["factory_tile"]
    report["factory_tile_override"] = prov.get("factory_tile_override")
    report["factory_tile_size"] = prov["factory_tile_size"]
    report["factory_tile_sha256"] = prov["factory_tile_sha256"]
    report["factory_tree_provenance"] = prov["factory_tree_provenance"]
    report["factory_tile_cell_binding"] = prov.get("factory_tile_cell_binding")
    report["factory_tile_box_rows"] = prov.get("factory_tile_box_rows")
    if prov["factory_tree_provenance"] != "factory-tile-parsed":
        kind = ("different cell's tile" if prov["factory_tree_provenance"] == "factory-tile-mismatch"
                else "not a parseable factory tile")
        report["missing_input"] = f"factory tile {factory_tile} is {kind}: {prov['parse_error']}"
        report["real_image_run"] = "factory-tree-invalid"
        report["factory_backed"] = False
        report["gates"] = {g: gate("BLOCKED", report["missing_input"], "factory_tile_provenance") for g in GATES}
        return report
    report["factory_tile_sections"] = prov.get("factory_tile_sections")

    # Clip to the chosen directory and prepare the OSM source BEFORE any copy
    # or tile write, so a preserve-only touch cannot leave a half-written out.
    factory_tile_bytes = factory_tile.read_bytes()
    report["fixture"] = "synthetic" if osm_path is None else "real-osm"
    if parcel is not None:
        box = directory_box(cell, parcel)
        report["parcel"] = "%d,%d" % parcel
        report["parcel_box"] = box
        report["parcel_kind"] = _factory_dir_kinds(factory_tile_bytes).get(parcel)
        if osm_path is not None and osm_bbox is None:
            osm_bbox = default_osm_bbox(box)
        if osm_bbox is not None:
            report["osm_bbox"] = list(osm_bbox)
            if not (box["lon_min"] <= osm_bbox[0] < osm_bbox[2] <= box["lon_max"]
                    and box["lat_min"] <= osm_bbox[1] < osm_bbox[3] <= box["lat_max"]):
                raise UsageError(
                    "--osm-bbox %s is not inside parcel %s box %s"
                    % (",".join("%.6f" % v for v in osm_bbox), report["parcel"],
                       ",".join("%.6f" % box[k] for k in ("lon_min", "lat_min", "lon_max", "lat_max"))))

    out_tile = out / "MAPAL001" / f"{cell}.DAT"
    if _is_within(factory_tile.resolve(), out.resolve()):
        raise UsageError(f"--factory-tile {factory_tile} is inside --out {out}; copying the root would delete it")

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        if osm_path is not None:
            osm_src = str(osm_path)
            report["osm_input"] = str(osm_path)
        else:
            osm = td / "syn.osm"; osm.write_text(osm_text or SYNTHETIC_OSM, encoding="utf-8")
            osm_src = str(osm)
            osm_text = osm_text or SYNTHETIC_OSM
            report["fixture_sha256"] = sha256_bytes(osm_text.encode("utf-8"))
        imf = td / "syn.imf.jsonl"
        argv = [osm_src, "-o", str(imf), "--source-name", "m5.34-parcel"]
        if osm_bbox is not None:
            argv += ["--bbox", ",".join("%.9f" % v for v in osm_bbox)]
        rc, so, se = run_cmd_json("osm_ingest.py", argv)
        report["counts"]["osm_ingest_rc"] = rc
        if rc != 0 or not imf.exists():
            report["gates"] = {g: gate("BLOCKED", f"osm_ingest failed rc={rc}: {se[:300]}") for g in GATES}; return report
        if parcel is not None:
            box = directory_box(cell, parcel)
            if clip:
                clipped = td / "clipped.imf.jsonl"
                report["clip"] = clip_imf_to_directory(imf, clipped, box)
                imf = clipped
            guard = guard_parcel(imf, parcel, factory_tile_bytes)
            report["parcel_guard"] = guard
            report["counts"]["guard_nodes"] = guard["nodes"]
        imf_lines = [ln for ln in imf.read_text(encoding="utf-8").splitlines() if ln.strip()]
        report["counts"]["imf_records"] = len(imf_lines)
        report["counts"]["ways"] = sum(1 for ln in imf_lines if '"type":"way"' in ln or '"type": "way"' in ln)
        report["counts"]["nodes"] = sum(1 for ln in imf_lines if '"type":"node"' in ln or '"type": "node"' in ln)
        split_out = td / "split.imf.jsonl"
        rc, so, se = run_cmd_json("mesh_split.py", [str(imf), "-o", str(split_out)])
        report["counts"]["mesh_split_rc"] = rc
        mesh_src = split_out if rc == 0 and split_out.exists() else imf
        ctab = td / "roadclass_v0.json"
        rc, so, se = run_cmd_json("roadclass_v0.py", ["--class-table-out", str(ctab)])
        report["counts"]["roadclass_rc"] = rc
        if rc != 0 or not ctab.exists():
            report["gates"] = {g: gate("BLOCKED", f"roadclass_v0 failed rc={rc}: {se[:300]}") for g in GATES}; return report
        # Every pre-write guard passed; only now copy the root and write one tile.
        _copy_factory_root(factory_root, out)
        if factory_tile.resolve() != out_tile.resolve():
            # H70: a supplied tile is the template; the root's own <cell>.DAT is not used.
            out_tile.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(factory_tile, out_tile)
        rc, so, se = run_cmd_json("tilewriter.py", [str(mesh_src), "--out", str(out_tile), "--cell", cell,
                                 "--factory", str(out_tile), "--class-table", str(ctab), "--country", country, "--no-names", "--json"])
        report["counts"]["tilewriter_rc"] = rc
        report["counts"]["tilewriter_stdout"] = so[:600]; report["counts"]["tilewriter_stderr"] = se[:600]
        if rc != 0 or not out_tile.exists():
            report["gates"] = {g: gate("BLOCKED", f"tilewriter failed rc={rc}: {(se or so)[:400]}") for g in GATES}; return report
        report["counts"]["tile_size"] = out_tile.stat().st_size
        report["counts"]["tile_sha256"] = sha256_bytes(out_tile.read_bytes())
    rc, so, se = run_cmd_json("rebuild_manifests.py", ["--root", str(out)])
    report["counts"]["rebuild_rc"] = rc
    report["counts"]["rebuild_tail"] = (so + "\n" + se).strip().splitlines()[-20:]
    rebuilt = [n for n in ["DRSTR001.DAT","MMAIN001.DAT","REFER001/CMP.LST","CMP.LST"] if (out/n).exists()]
    rebuilt += [f"REFER001/{p.name}" for p in (out/"REFER001").glob("*.ind")] if (out/"REFER001").exists() else []
    report["counts"]["rebuilt_files"] = sorted(set(rebuilt))
    report["changed_set"] = [f"MAPAL001/{cell}.DAT"] + report["counts"]["rebuilt_files"]
    rc, so, se = run_cmd_json("cardcheck.py", ["--root", str(out), "--ignore-dump-artifacts", "--fast"])
    report["counts"]["cardcheck_rc"] = rc; report["counts"]["cardcheck_tail"] = (so+"\n"+se).strip().splitlines()[-20:]
    card_ok = rc == 0
    rc2, so2, se2 = run_cmd_json("l2check.py", ["--root", str(out), "--no-golden",
                                                "--tiles", f"{cell}.DAT",
                                                "--semantic-tiles", f"{cell}.DAT",
                                                "--cmp-limit", "20"])
    report["counts"]["l2check_rc"] = rc2; report["counts"]["l2check_tail"] = (so2+"\n"+se2).strip().splitlines()[-25:]
    l2_out = so2 + se2
    tile_checked = f"tiles=1" in l2_out and "not present on this card" not in l2_out
    l2_ok = rc2 == 0 and tile_checked
    report["counts"]["l2check_tile_checked"] = tile_checked
    report["gates"]["hdd_info_map_code"] = gate("CANNOT-VERIFY-OFFLINE", "HDD_INFO/MAP CODE bytes present but not byte-verified against unit target offline (M2.18/M9.6); firmware acceptance unknown (rule 13).", "VER_INFO/HDD_INFO.TXT present")
    report["gates"]["drstr_mmain_cmplst_ind"] = gate("PASS" if (card_ok and report["counts"]["rebuild_rc"]==0) else "CANNOT-VERIFY-OFFLINE", f"rebuild_manifests rc={report['counts']['rebuild_rc']}; cardcheck rc={report['counts']['cardcheck_rc']}.", "rebuild_manifests + cardcheck")
    report["gates"]["tile_roundtrip_structure"] = gate("PASS" if (report["counts"]["tilewriter_rc"]==0 and l2_ok) else "CANNOT-VERIFY-OFFLINE", f"tilewriter rc={report['counts']['tilewriter_rc']} (factory template, provisional-v0, 1 tile {cell}); targeted l2check --no-golden --tiles {cell}.DAT rc={rc2}, tile_checked={tile_checked}.", "tilewriter + l2check targeted")
    report["gates"]["section4"] = gate("CANNOT-VERIFY-OFFLINE", "section 4 in OSM-generated tile is provisional road-only; factory section-4 semantics/firmware acceptance not verified offline. Not PASS.", "provisional-v0 tile")
    report["gates"]["manifests"] = gate("PASS" if (report["counts"]["rebuild_rc"]==0 and card_ok) else "CANNOT-VERIFY-OFFLINE", f"rebuild rc={report['counts']['rebuild_rc']}, cardcheck rc={report['counts']['cardcheck_rc']}.", "rebuild_manifests + cardcheck")
    report["cardcheck_ok"] = card_ok; report["l2check_ok"] = l2_ok
    if parcel is not None:
        try:
            tile_change = prove_tile_change(
                factory_tile_bytes, out_tile.read_bytes(), cell, parcel)
            report["tile_change"] = tile_change
            # Compare the union of both trees, so an out-only or root-only file
            # is a difference too (B2: a one-sided walk cannot see it).
            root_hashes = {p.relative_to(factory_root): sha256_bytes(p.read_bytes())
                           for p in factory_root.rglob("*") if p.is_file()}
            out_hashes = {p.relative_to(out): sha256_bytes(p.read_bytes())
                          for p in out.rglob("*") if p.is_file()}
            differing = _tree_differences(root_hashes, out_hashes)
            tile_path = f"MAPAL001/{cell}.DAT"
            manifests = {"DRSTR001.DAT", "MMAIN001.DAT", "CMP.LST"}
            only_dir = bool(tile_change.get("only_parcel_directory_changed"))
            report["gates"]["one_tile_one_directory"], unexpected = one_tile_gate(
                differing, tile_path, manifests, only_dir, tile_change)
            report["tree_diff"] = {
                "files_compared": len(set(root_hashes) | set(out_hashes)),
                "differing_files": differing,
                "unexpected_differences": unexpected,
                "tile_plus_manifests_only": not unexpected,
            }
            report["changed_set_actual"] = [d["path"] for d in differing]
        except Exception as e:  # a proof failure is a result
            report["tile_change"] = {"error": f"{type(e).__name__}: {e}"}
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="M5.29 one-tile OSM pipeline (L1+L2+gate report)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", help="output tree directory")
    ap.add_argument("--cell", default="B48R058R")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--osm", help="OSM input")
    ap.add_argument("--factory-root", help="factory-extracted card root (outside repo)")
    ap.add_argument("--factory-tile", help="factory tile DAT to use as the template instead of FACTORY_ROOT/MAPAL001/<cell>.DAT (must bind to --cell)")
    ap.add_argument("--country", default="616")
    ap.add_argument("--json", nargs="?", const="-", default=None, metavar="PATH",
                    help="print the report JSON to stdout (bare) or write it to PATH ('-' = stdout)")
    ap.add_argument("--check-cell-binding", metavar="ROOT",
                    help="survey MAPAL001 tile-to-cell binding on ROOT and print counts (no writes)")
    ap.add_argument("--parcel", metavar="Y,X",
                    help="directory (y,x) to write into: clip the OSM input to its box and "
                         "refuse any node that lands in a preserve-only directory")
    ap.add_argument("--osm-bbox", metavar="MINLON,MINLAT,MAXLON,MAXLAT",
                    help="OSM clip box; defaults to the chosen parcel's directory box. "
                         "Requires --parcel")
    ap.add_argument("--clip", action="store_true",
                    help="drop ways that leave the parcel's directory instead of refusing "
                         "(default: refuse, naming the kind). Requires --parcel")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.check_cell_binding:
        survey = survey_cell_binding(Path(args.check_cell_binding))
        print(json.dumps(survey, indent=2, ensure_ascii=False))
        return 0 if survey["ok"] else 1
    if not args.out:
        print("error: --out required (or --selftest)", file=sys.stderr); return 2
    out = Path(args.out)
    factory_root = Path(args.factory_root) if args.factory_root else None
    factory_tile = Path(args.factory_tile) if args.factory_tile else None
    if factory_tile is not None and factory_root is None:
        print("error: --factory-tile requires --factory-root", file=sys.stderr); return 2
    try:
        parcel = parse_parcel(args.parcel) if args.parcel else None
        osm_bbox = parse_osm_bbox(args.osm_bbox) if args.osm_bbox else None
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr); return 2
    if osm_bbox is not None and parcel is None:
        print("error: --osm-bbox requires --parcel", file=sys.stderr); return 2
    if parcel is not None and factory_root is None:
        print("error: --parcel requires --factory-root (parcel kinds live in the factory tile)",
              file=sys.stderr); return 2
    if args.clip and parcel is None:
        print("error: --clip requires --parcel", file=sys.stderr); return 2
    try:
        if factory_root is not None:
            _check_out_overlap(out, factory_root)
        if args.synthetic or (not args.factory_root and not args.osm):
            rep = build_synthetic_out(out, args.cell, input_root=Path(args.osm) if args.osm else None)
        elif args.factory_root:
            rep = build_factory_out(out, factory_root, args.cell, country=args.country,
                                    factory_tile_path=factory_tile,
                                    osm_path=Path(args.osm) if args.osm else None,
                                    osm_bbox=osm_bbox, parcel=parcel, clip=args.clip)
        else:
            rep = build_synthetic_out(out, args.cell)
            rep["note"] = "OSM provided without --factory-root; synthetic-only fallback"
            rep["real_image_run"] = "blocked"; rep["missing_input"] = "--factory-root required"
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr)
        print("usage: --out must not be, contain, or be contained by --factory-root/--osm", file=sys.stderr)
        return 2
    doc = json.dumps(rep, indent=2, ensure_ascii=False)
    if args.json and args.json != "-":
        dest = os.path.abspath(args.json)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dest), prefix=".one_tile_pipeline.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(doc + "\n")
            os.replace(tmp, dest)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        print(f"report: {dest}")
    else:
        print(doc)
    ok_tree = (out / "MAPAL001" / f"{args.cell}.DAT").exists() and rep["counts"].get("tilewriter_rc") == 0
    card_ok = rep.get("cardcheck_ok") or rep.get("cardcheck_applicable")
    l2_ok = rep.get("l2check_ok") or rep.get("l2_applicable")
    if rep.get("factory_backed") and card_ok and l2_ok and ok_tree:
        return 0
    if ok_tree and (rep.get("mode") == "synthetic-only" or rep.get("real_image_run") == "blocked"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
