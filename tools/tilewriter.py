#!/usr/bin/env python3
"""Roads-only ZE0 tile writer (M5.4, tool half).

Takes an IMF v1 file that ``tools/mesh_split.py`` has already split (one way
fragment per ``BxxRyyR`` cell), clips each fragment to the cell's parcels,
builds one section-1 road-shape record per populated parcel with the checked-in
``tools/ze0-viewer/tools_ze0`` writer (``fa_encode``), and emits one tile
container.

Two container modes
-------------------

``--factory TILE.DAT`` (the normal case)
    The factory tile is the container template.  Its 0x1000 header, its level
    table (``0x1ac``), box table (``0x2ac``), section table (``0x800``) and
    every descriptor are **copied byte for byte**; the writer only touches the
    section-1 road pair of the parcels it regenerates.  Record blocks that
    still fit their original 256-byte-aligned region are written in place;
    a block that grew is appended and the slot's ``u32`` tag is repointed (the
    old bytes are left behind, like the factory's own append-style tools).
    Sections 2 and 4 and every background record are untouched.

    Section 4 goes through ``tools/section4.py``: each record's payload is
    parsed and re-encoded with ``encode preserve`` and the result must equal the
    original bytes before the tile is accepted.  Nothing in section 4 is
    rewritten.

no ``--factory``
    A fresh container is assembled (``tile_header.author`` for the header,
    ``clarion_tile.write_tile`` for the tables, directories and blocks) that
    holds **roads only**: no section-2 router graph, no section-4
    administrative index, no background.  It is a development artefact, not a
    unit-ready tile; the report says so.

Road classes
------------

``--class-table FILE`` is a JSON table ``{"format": "ze0-road-class-table/1",
"classes": {"highway_value": [layer, class], ...}}``; without it the writer
uses the checked-in upstream mapping (``fa_encode.CLASSES``), which is a
hypothesis for ZE0 until M5.3 lands.  A ``highway`` value that the table does
not map is a hard error, never a silent default.

Stream keys
-----------

Every road record's first six bytes are the documented stream key
``(A = 32768 + lat*192, B = 52736 + lon*128, tag = 0x00fa)`` where ``lat`` and
``lon`` are the parcel's south-west corner; ``parcel_code`` packs the remaining
sub-lattice bits into the low byte, so the high byte of ``A``/``B`` is exactly
the documented address and the low byte carries the parcel (see
``docs/format/map-tiles.md`` and ``clarion_bg.parcel_code``).

Not unit-ready
--------------

This tool does not and cannot prove that the unit reads the tile: the L2 check
needs a vendor tile and a matching card tree, and the OSM -> Clarion class and
speed mapping is M5.3/M4.2.  All reports carry ``"unit_ready": false``.

Usage::

    python3 tools/tilewriter.py map.split.jsonl --cell B48R058R \\
        --factory B48R058R.DAT --country 616 --out B48R058R.new.DAT
    python3 tools/tilewriter.py map.split.jsonl --cell B48R058R --out roads.DAT \\
        --country 616 --data-version 11/01/01/01
    python3 tools/tilewriter.py map.split.jsonl --cell B48R058R --out x.DAT \\
        --factory F.DAT --country 616 --json --dry-run
    python3 tools/tilewriter.py --selftest

Exit codes: ``0`` written (or dry-run) and every internal check passed, ``1`` a
check failed, ``2`` usage, input or I/O error (a class-table miss is an input
error).  ``.gz`` input is detected by suffix.
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import hashlib
import json
import math
import re
import struct
import sys
import zlib
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
ZE0_DIR = TOOLS_DIR / "ze0-viewer" / "tools_ze0"
for _path in (str(TOOLS_DIR), str(ZE0_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import clarion_bg  # noqa: E402
import clarion_tile  # noqa: E402
import fa_encode  # noqa: E402
import section4  # noqa: E402
import tile_header  # noqa: E402

REPORT_FORMAT = "ze0-tilewriter/1"
CLASS_TABLE_FORMAT = "ze0-road-class-table/1"

#: ZE0 (X08-02-00) streams are ``78 9c``: stock zlib, level 6, 15-bit window,
#: memLevel 8 (docs/format/map-tiles.md).  The checked-in writer compresses
#: with a 13-bit window (``58 85``, X08-03-00), so the record *bytes* come from
#: ``fa_encode`` and the framing is redone here.
ZW_BITS = 15
ZW_LEVEL = 6
ZW_MEMLEVEL = 8

#: Section-1 record tag of a road-shape record, and its pair parity (even).
ROAD_TAG = 0x00FA
PAIR_ROAD = 0

#: Parcel size per level in degrees (see ``clarion_bg.LEVELS``).
PARCEL_DEG = {1: (1.0 / 32.0, 1.0 / 48.0), 2: (1.0 / 8.0, 1.0 / 12.0)}
#: Directory span in mesh units (1 mesh = 1 deg lon x 2/3 deg lat).
DIR_MESHES = {1: 1, 2: 4}
UNITS = 2048
#: Points per link; longer runs are split into a chain of links.
MAX_LINK_POINTS = 64

CELL_RE = re.compile(r"^B[0-9A-F]{2}R[0-9A-F]{3}R$")
DATA_VERSION_RE = re.compile(r"^\d{2}/\d{2}/\d{2}/\d{2}$")

EXIT_OK = 0
EXIT_CHECK_FAILED = 1
EXIT_BAD_INPUT = 2

UNIT_READY = False
REASONS_NOT_READY = (
    "no vendor tile here: the L2 tile check of a generated tile cannot run",
    "OSM -> Clarion class/speed mapping is M5.3 (and M4.2 for one-way/speed)",
    "road names are not written (M5.7); name_off is 0xffff",
    "the router graph (section 2) is copied, never regenerated (M5.6)",
    "cross-tile connectivity is M5.5; border points land on the parcel edge",
    "nothing here has been read by the unit or the firmware",
)


class WriterError(Exception):
    """Usage, input or I/O problem (exit 2)."""


class ClassTableMiss(WriterError):
    """The IMF uses a ``highway=*`` value the class table does not map."""


class CheckFailed(Exception):
    """An internal consistency check failed (exit 1)."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------
# Small format helpers
# --------------------------------------------------------------------------


def compress(plain: bytes) -> bytes:
    """Word-aligned ZE0 zlib stream (``78 9c``) for one record body."""
    engine = zlib.compressobj(ZW_LEVEL, zlib.DEFLATED, ZW_BITS, ZW_MEMLEVEL)
    comp = engine.compress(plain) + engine.flush()
    if len(comp) % 2:
        comp += b"\x00"
    return comp


def cell_bounds(cell: str):
    """``(lat_min, lat_max, lon_min, lon_max)`` of a ``BxxRyyR`` cell, degrees."""
    if not CELL_RE.match(cell):
        raise WriterError("not a tile cell name: %r (want BbbRyyy)" % (cell,))
    b = int(cell[1:3], 16)
    r = int(cell[4:7], 16)
    lat_min = b * 2.0 / 3.0
    lon_max = 108 - r
    return lat_min, lat_min + 16.0 / 3.0, lon_max - 8.0, lon_max


def cell_mesh(cell: str):
    """South-west mesh ``(y0, x0)`` of a cell (``clarion_bg.tile_cell``)."""
    b = int(cell[1:3], 16)
    r = int(cell[4:7], 16)
    return b, 1024 - r


def cell_db_bounds(cell: str):
    """The four header words (arc-minutes) of a cell-sized database box."""
    lat_min, lat_max, lon_min, lon_max = cell_bounds(cell)
    return (
        int(round(lat_max * 60)),
        int(round(lat_min * 60)),
        int(round(lon_min * 60)),
        int(round(lon_max * 60)),
    )


def parcel_of(lon: float, lat: float, level: int):
    """``(dir_y, dir_x, row, col)`` of the parcel containing ``(lon, lat)``."""
    step_x, step_y = PARCEL_DEG[level]
    m = DIR_MESHES[level]
    x0 = 924 + math.floor(lon)
    y0 = math.floor(lat * 1.5)
    x0 -= (x0 - 904) % m
    y0 -= (y0 - 32) % m
    lon0 = clarion_bg.mesh_to_lon(x0)
    lat0 = clarion_bg.mesh_to_lat(y0)
    per_row = clarion_bg.LEVELS[level]["rows"] // m
    per_col = clarion_bg.LEVELS[level]["cols"] // m
    col = min(per_col - 1, max(0, int((lon - lon0) / step_x)))
    row = min(per_row - 1, max(0, int((lat - lat0) / step_y)))
    return y0, x0, row, col


def _crossings(a, b, step_x, step_y):
    """Parameters ``t`` in (0, 1) at which segment a-b crosses the parcel grid."""
    params = []
    for start, end, step in ((a[0], b[0], step_x), (a[1], b[1], step_y)):
        if start == end:
            continue
        low, high = (start, end) if start < end else (end, start)
        k = math.floor(low / step)
        while True:
            k += 1
            line = k * step
            if line >= high:
                break
            if line <= low:
                continue
            t = (line - start) / (end - start)
            if 0.0 < t < 1.0:
                params.append(t)
    params.sort()
    unique = []
    for t in params:
        if not unique or t - unique[-1] > 1e-12:
            unique.append(t)
    return unique


def parcel_runs(points, level):
    """Split a polyline at parcel borders; return ``[(parcel, [lon, lat]...), ...]``."""
    step_x, step_y = PARCEL_DEG[level]
    pieces = []
    for a, b in zip(points, points[1:]):
        cuts = [0.0] + _crossings(a, b, step_x, step_y) + [1.0]
        for t0, t1 in zip(cuts, cuts[1:]):
            p = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
            q = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
            if p == q:
                continue
            mid = ((p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0)
            pieces.append((parcel_of(mid[0], mid[1], level), p, q))
    runs = []
    for parcel, p, q in pieces:
        if runs and runs[-1][0] == parcel and runs[-1][1][-1] == p:
            runs[-1][1].append(q)
        else:
            runs.append((parcel, [p, q]))
    return runs


def quantise(lon, lat, lon0, lat0, width, height):
    """Parcel-local coordinates on the runtime ``0..2047`` lattice."""
    x = int(round((lon - lon0) / width * UNITS))
    y = int(round((lat - lat0) / height * UNITS))
    return min(UNITS - 1, max(0, x)), min(UNITS - 1, max(0, y))


# --------------------------------------------------------------------------
# Road class table
# --------------------------------------------------------------------------


def default_class_table():
    """The checked-in upstream mapping as ``{highway: (layer, class)}``."""
    return {
        hw: (entry[0][0], entry[0][1])
        for hw, entry in fa_encode.CLASSES.items()
    }


def load_class_table(path: str | None):
    if not path:
        return default_class_table(), "default (fa_encode.CLASSES, hypothesis until M5.3)"
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise WriterError("cannot read class table %s: %s" % (path, exc)) from exc
    except json.JSONDecodeError as exc:
        raise WriterError("class table %s is not JSON: %s" % (path, exc)) from exc
    if data.get("format") != CLASS_TABLE_FORMAT:
        raise WriterError(
            "class table %s: format must be %r" % (path, CLASS_TABLE_FORMAT)
        )
    classes = data.get("classes")
    if not isinstance(classes, dict) or not classes:
        raise WriterError("class table %s: 'classes' must be a non-empty object" % path)
    table = {}
    for hw, value in classes.items():
        if not isinstance(value, list) or len(value) != 2:
            raise WriterError(
                "class table %s: %r must be [layer, class]" % (path, hw)
            )
        layer, cls = int(value[0]), int(value[1])
        if not 0 <= layer <= 11:
            raise WriterError("class table %s: %r layer %d outside 0..11" % (path, hw, layer))
        if not 1 <= cls <= 15:
            raise WriterError("class table %s: %r class %d outside 1..15" % (path, hw, cls))
        table[str(hw)] = (layer, cls)
    return table, "file %s" % path


@contextlib.contextmanager
def _class_mapping(table):
    """Install ``table`` for the duration of one ``fa_encode`` call.

    ``fa_encode.layer_class`` reads a module-level dict; swapping it is the only
    extension point the checked-in writer offers without editing it.
    """
    saved = fa_encode.CLASSES
    fa_encode.CLASSES = {
        hw: ((layer, cls), cls, cls) for hw, (layer, cls) in table.items()
    }
    try:
        yield fa_encode.CLASSES
    finally:
        fa_encode.CLASSES = saved


# --------------------------------------------------------------------------
# IMF input
# --------------------------------------------------------------------------


def _read_text(path: str) -> str:
    try:
        if path.endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                return handle.read()
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise WriterError("cannot read %s: %s" % (path, exc)) from exc


def read_jsonl(path: str):
    records = []
    for number, line in enumerate(_read_text(path).splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise WriterError("%s:%d is not JSON: %s" % (path, number, exc)) from exc
    if not records:
        raise WriterError("%s: no IMF records" % path)
    return records


def load_imf(path: str, cell: str):
    """Return ``(ways, stats)`` for one cell.

    ``ways`` is ``[{"id", "highway", "points": [(lon, lat), ...]}]``.  A way that
    still carries more than one cell means the input was not mesh-split; that
    is an input error, not something to guess around.
    """
    records = read_jsonl(path)
    nodes = {}
    for record in records:
        if record.get("type") != "node":
            continue
        try:
            nodes[str(record["id"])] = (float(record["lon"]), float(record["lat"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise WriterError("node record %r is malformed: %s" % (record.get("id"), exc))
    stats = {"nodes": len(nodes), "ways": 0, "ways_other_cells": 0,
             "ways_short": 0, "ways_multi_cell": 0, "ways_no_highway": 0}
    multi = []
    missing = []
    ways = []
    for record in records:
        if record.get("type") != "way":
            continue
        stats["ways"] += 1
        tiles = record.get("tiles")
        if not isinstance(tiles, list) or not tiles:
            tiles = [record.get("tile")] if record.get("tile") else []
        cells = sorted({str(t) for t in tiles if t})
        if cell not in cells:
            stats["ways_other_cells"] += 1
            continue
        if len(cells) > 1:
            stats["ways_multi_cell"] += 1
            multi.append(str(record.get("id")))
            continue
        ids = record.get("nodes") or []
        points = []
        broken = False
        for node_id in ids:
            point = nodes.get(str(node_id))
            if point is None:
                broken = True
                missing.append(str(node_id))
                break
            points.append(point)
        if broken:
            continue
        if len(points) < 2:
            stats["ways_short"] += 1
            continue
        tags = record.get("tags") if isinstance(record.get("tags"), dict) else {}
        highway = tags.get("highway")
        if not highway:
            stats["ways_no_highway"] += 1
            continue
        ways.append({"id": str(record.get("id")), "highway": str(highway),
                     "points": points})
    if multi:
        raise WriterError(
            "%d way(s) still span several cells (%s); run tools/mesh_split.py "
            "first" % (len(multi), ", ".join(multi[:5]))
        )
    if missing:
        raise WriterError(
            "%d way node(s) have no node record (e.g. %s); the IMF file is "
            "incomplete" % (len(missing), ", ".join(sorted(set(missing))[:5]))
        )
    return ways, stats


def ways_to_runs(ways, level: int, table, cell: str):
    """Clip every way to parcels; return ``(runs_by_parcel, misses)``."""
    yb, xb = cell_mesh(cell)
    runs = {}
    misses = {}
    for way in ways:
        entry = table.get(way["highway"])
        if entry is None:
            misses.setdefault(way["highway"], []).append(way["id"])
            continue
        for parcel, points in parcel_runs(way["points"], level):
            y0, x0, row, col = parcel
            # A point pressed onto the cell border must not create a directory
            # outside this file: clamp into the cell and say so in the report.
            y0 = min(max(y0, yb), yb + 8 - DIR_MESHES[level])
            x0 = min(max(x0, xb), xb + 8 - DIR_MESHES[level])
            runs.setdefault((y0, x0, row, col), []).append((points, way["highway"]))
    if misses:
        detail = ", ".join(
            "%s (%d way(s): %s)" % (hw, len(ids), ", ".join(sorted(ids)[:3]))
            for hw, ids in sorted(misses.items())
        )
        raise ClassTableMiss(
            "class table has no entry for highway=%s; add it to the table or "
            "drop the way (unknown values are never mapped to a default)"
            % detail
        )
    return runs


# --------------------------------------------------------------------------
# Road-shape records
# --------------------------------------------------------------------------


def build_road_record(level, parcel, runs, table, country):
    """One ``0x00fa`` record: ``(plain, comp, info)``, or ``None`` when empty."""
    y0, x0, row, col = parcel
    lon0, lat0, width, height = clarion_bg.parcel_geo(level, y0, x0, row, col)
    nodes = []
    chains = []
    hws = []
    points = 0
    for points_, highway in runs:
        local = []
        for lon, lat in points_:
            xy = quantise(lon, lat, lon0, lat0, width, height)
            if local and local[-1] == xy:
                continue
            local.append(xy)
        if len(local) < 2:
            continue
        base = len(nodes)
        nodes.extend(local)
        links = []
        link_id = 1
        step = MAX_LINK_POINTS - 1
        start = 0
        while start < len(local) - 1:
            stop = min(start + step, len(local) - 1)
            links.append((link_id, base + start, base + stop, local[start + 1:stop]))
            link_id += 1
            start = stop
        chains.append(links)
        hws.append(highway)
        points += len(local)
    if not chains:
        return None
    with _class_mapping(table):
        plain, _upstream_comp = fa_encode.build_record(
            level, y0, x0, row, col, nodes, chains, hws=hws, country=country
        )
    comp = compress(plain)
    code = struct.unpack_from(">HH", plain, 0)
    tag = struct.unpack_from(">H", plain, 4)[0]
    if tag != ROAD_TAG:
        raise CheckFailed("built record tag 0x%04x is not 0x%04x" % (tag, ROAD_TAG))
    _code, _unit, shapes = fa_encode.parse_record(plain, level)
    if not shapes or not all(shape["ok"] for shape in shapes):
        raise CheckFailed(
            "the checked-in reader cannot re-read the record at parcel %r" % (parcel,)
        )
    doc_a = 32768 + int(round(lat0 * 192))
    doc_b = 52736 + int(round(lon0 * 128))
    info = dict(
        parcel=dict(y0=y0, x0=x0, row=row, col=col),
        code=[code[0], code[1]],
        key=[code[0], code[1], tag],
        doc_key=[doc_a, doc_b, ROAD_TAG],
        delta=[code[0] - doc_a, code[1] - doc_b],
        shapes=len(shapes),
        links=sum(len(shape["links"]) for shape in shapes),
        points=points,
        plain_bytes=len(plain),
        compressed_bytes=len(comp),
        highways=sorted({hw for _, hw in runs}),
    )
    if (code[0] >> 8) != (doc_a >> 8) or (code[1] >> 8) != (doc_b >> 8):
        raise CheckFailed(
            "stream key %04x %04x is off the documented lattice of %04x %04x"
            % (code[0], code[1], doc_a, doc_b)
        )
    return plain, comp, info


# --------------------------------------------------------------------------
# Factory container: read, patch, verify
# --------------------------------------------------------------------------


def _section(tile, section_id):
    for sec in tile["sections"]:
        if sec["id"] == section_id:
            return sec
    return None


def _empty_pair(index, level):
    if level == 1 and index % 2 == PAIR_ROAD:
        return b"\x7f\xff\xff\xff\x7f\xff\xff\xff"
    return b"\xff" * 8


def _slot_body(level, nslots_body, slot=None):
    if slot is not None:
        return bytearray(slot["body"])
    npairs = nslots_body // 8
    return bytearray(b"".join(_empty_pair(k, level) for k in range(npairs)))


def road_level(tile, level):
    """The section-1 level object for ``level`` or ``None``."""
    sec = _section(tile, 1)
    if sec is None:
        return None
    for entry in sec["levels"]:
        if entry["level"] == level:
            return entry
    return None


def sector_fingerprint(tile, section_id):
    """A comparable snapshot of one section: heads, slot bodies, record bytes."""
    sec = _section(tile, section_id)
    if sec is None:
        return None
    levels = []
    for entry in sec["levels"]:
        dirs = []
        for directory in entry["dirs"]:
            slots = []
            for index in sorted(directory["slots"]):
                slot = directory["slots"][index]
                slots.append(
                    (index, bytes(slot["body"]),
                     tuple(bytes(rec["raw"]) for rec in slot["recs"]))
                )
            dirs.append((directory["kind"], directory["y"], directory["x"],
                         directory["typ"], tuple(directory["box"]), tuple(slots)))
        levels.append((entry["level"], entry["typ"], tuple(dirs)))
    return tuple(levels)


def records_by_position(tile, section_id, level=None):
    """``{(dir_y, dir_x, slot, pair): raw}`` for one section (optionally one level)."""
    out = {}
    sec = _section(tile, section_id)
    if sec is None:
        return out
    for entry in sec["levels"]:
        if level is not None and entry["level"] != level:
            continue
        for directory in entry["dirs"]:
            for index, slot in directory["slots"].items():
                for rec in slot["recs"]:
                    out[(directory["y"], directory["x"], index, rec["k"])] = bytes(
                        rec["raw"]
                    )
    return out


def check_section4(tile):
    """Parse and re-encode every section-4 record with ``section4 preserve``."""
    records = 0
    names = 0
    for record in records_by_position(tile, 4).values():
        try:
            model = section4.parse_payload(record, "section4-record")
            again = section4.encode_preserve(model)
        except section4.ShapeError as exc:
            raise CheckFailed("section 4 record does not parse: %s" % exc) from exc
        if again != record:
            raise CheckFailed(
                "section4 encode preserve is not byte-identical (%d vs %d bytes)"
                % (len(again), len(record))
            )
        records += 1
        names += model["name_count"]
    return dict(records=records, names=names, preserved=True)


def splice_factory(factory: bytes, level: int, built):
    """Patch the factory bytes in place; return ``(out, container_info)``."""
    tile = clarion_tile.read_tile(factory)
    entry = road_level(tile, level)
    if entry is None:
        raise WriterError(
            "factory tile has no section-1 level %d; cannot add a level in place"
            % level
        )
    dirs = {(directory["y"], directory["x"]): directory for directory in entry["dirs"]}

    # Group the new records per directory row: one slot block holds every pair.
    groups: dict[tuple[int, int, int], dict[int, Any]] = {}
    for parcel, rec in built.items():
        y0, x0, row, col = parcel
        if (y0, x0) not in dirs:
            raise WriterError(
                "factory tile has no level-%d directory at y=%d x=%d; adding "
                "directories changes the header, so this is refused (use a "
                "factory tile that covers the cell, or write without --factory)"
                % (level, y0, x0)
            )
        groups.setdefault((y0, x0, row), {})[2 * col + PAIR_ROAD] = rec

    out = bytearray(factory)
    in_place = 0
    appended = 0
    superseded = 0
    for (y0, x0, row), pairs in sorted(groups.items()):
        directory = dirs[(y0, x0)]
        slot = directory["slots"].get(row)
        body = _slot_body(level, directory["body"], slot)
        old_records = list(slot["recs"]) if slot else []
        for pair, rec in sorted(pairs.items()):
            old_records = [old for old in old_records if old["k"] != pair]
            old_records.append(
                dict(k=pair, raw=rec["comp"], words=len(rec["plain"]) // 2, flag=0)
            )
        old_records.sort(key=lambda item: item["k"])
        block = b"".join(bytes(old["raw"]) for old in old_records)
        for pair in sorted(pairs):
            rec = pairs[pair]
            struct.pack_into(">II", body, 8 * pair,
                             len(rec["comp"]) // 2, len(rec["plain"]) // 2)
        slot_off = directory["off"] + 12 + row * (4 + directory["body"])
        old_off = slot["block_off"] if slot else None
        old_block = clarion_tile.block_bytes(slot) if slot else b""
        # Overwrite only bytes the reader modelled and that are really there.
        # Anything the reader did not model (a raw slot tail) stays untouched;
        # a block that grew is appended and the slot tag repointed instead.
        fits = (old_off is not None and 0 < len(block) <= len(old_block)
                and out[old_off:old_off + len(old_block)] == old_block)
        if fits:
            out[old_off:old_off + len(block)] = block
            out[old_off + len(block):old_off + len(old_block)] = b"\x00" * (
                len(old_block) - len(block)
            )
            in_place += 1
        else:
            offset = clarion_tile.pad256(len(out))
            out.extend(b"\x00" * (offset - len(out)))
            out.extend(block)
            struct.pack_into(">I", out, slot_off, clarion_tile.enc_addr(offset))
            appended += 1
            superseded += len(old_block)
        out[slot_off + 4:slot_off + 4 + directory["body"]] = bytes(body)
    return bytes(out), dict(in_place=in_place, appended=appended,
                            superseded_bytes=superseded)


def verify_factory(factory: bytes, blob: bytes, level: int, built):
    """Fail loudly if the splice broke the header or any unchanged section."""
    before = clarion_tile.read_tile(factory)
    after = clarion_tile.read_tile(blob)
    if bytes(after["header"]) != bytes(before["header"]):
        raise CheckFailed("the 0x1000 header changed during the factory splice")
    for section_id in (2, 3, 4):
        if sector_fingerprint(before, section_id) != sector_fingerprint(after, section_id):
            raise CheckFailed("section %d is not byte-identical" % section_id)
    old = records_by_position(before, 1)
    new = records_by_position(after, 1)
    changed = set()
    for parcel, rec in built.items():
        y0, x0, row, col = parcel
        changed.add((y0, x0, row, 2 * col + PAIR_ROAD))
    for key in set(old) | set(new):
        if key in changed:
            continue
        if old.get(key) != new.get(key):
            raise CheckFailed(
                "section-1 record at %r changed but was not regenerated" % (key,)
            )
    return check_section4(after)


# --------------------------------------------------------------------------
# Synthetic container (no factory tile)
# --------------------------------------------------------------------------


def make_dir(level, y0, x0, parcels):
    """A ``clarion_tile`` directory object holding road records for one mesh."""
    spec = clarion_bg.LEVELS[level]
    body = spec["body"]
    nslots = spec["slots"]
    npairs = body // 8
    empty = b"".join(_empty_pair(k, level) for k in range(npairs))
    slots = {}
    for row, columns in sorted(parcels.items()):
        pairs = [bytearray(_empty_pair(k, level)) for k in range(npairs)]
        recs = []
        for col, rec in sorted(columns.items()):
            pair = 2 * col + PAIR_ROAD
            pairs[pair] = bytearray(
                struct.pack(">II", len(rec["comp"]) // 2, len(rec["plain"]) // 2)
            )
            recs.append(dict(k=pair, raw=rec["comp"],
                             words=len(rec["plain"]) // 2, flag=0))
        slots[row] = dict(body=b"".join(bytes(p) for p in pairs), recs=recs,
                          block_off=0, block_end=0)
    span = DIR_MESHES[level]
    return dict(kind=spec["kind"], ab=spec["ab"], y=y0, x=x0, typ=spec["typ"],
                body=body, nslots=nslots, slots=slots,
                empty_bodies={i: empty for i in range(nslots) if i not in slots},
                box=(y0 + span, y0, x0, x0 + span))


def synthetic_tile(built, level, cell, data_version):
    """Assemble a roads-only container with the checked-in container writer."""
    grouped: dict[tuple[int, int], dict[int, dict[int, Any]]] = {}
    for parcel, rec in built.items():
        y0, x0, row, col = parcel
        grouped.setdefault((y0, x0), {}).setdefault(row, {})[col] = rec
    dirs = [make_dir(level, y0, x0, parcels) for (y0, x0), parcels in sorted(grouped.items())]

    def empty_section(section_id, used):
        return dict(
            id=section_id,
            count=0,
            levels=[dict(level=lvl, typ=typ, dirs=(dirs if lvl == level and used else []))
                    for lvl, typ in tile_header.LEVELS[section_id]],
        )

    tile = dict(sections=[
        empty_section(1, True),
        empty_section(2, False),
        empty_section(4, False),
    ])
    for sec in tile["sections"]:
        words, _offsets, _groups = clarion_tile.table_words(sec)
        sec["count"] = -(-2 * words // 256)
    tile["header"] = tile_header.author(
        tile_header.level_groups(tile), [], cell_db_bounds(cell), data_version
    )
    return clarion_tile.write_tile(tile)


def verify_synthetic(blob: bytes, level: int, built):
    tile = clarion_tile.read_tile(blob)
    found = 0
    for parcel, rec in built.items():
        y0, x0, row, col = parcel
        slot, record = find_record(tile, level, y0, x0, row, 2 * col + PAIR_ROAD)
        if zlib.decompress(bytes(record["raw"])) != rec["plain"]:
            raise CheckFailed("record at %r does not decompress to the built body" % (parcel,))
        found += 1
    if found != len(built):
        raise CheckFailed("only %d of %d records survived the write" % (found, len(built)))
    return check_section4(tile)


def find_record(tile, level, y0, x0, row, pair):
    entry = road_level(tile, level)
    if entry is None:
        raise CheckFailed("no section-1 level %d in the written tile" % level)
    for directory in entry["dirs"]:
        if (directory["y"], directory["x"]) != (y0, x0):
            continue
        slot = directory["slots"].get(row)
        if slot is None:
            break
        for record in slot["recs"]:
            if record["k"] == pair:
                return slot, record
        break
    raise CheckFailed("no record at dir y=%d x=%d slot %d pair %d" % (y0, x0, row, pair))


# --------------------------------------------------------------------------
# The write
# --------------------------------------------------------------------------


def build(imf_path: str, cell: str, *, factory_path: str | None = None,
          class_table_path: str | None = None, level: int = 1, country: int = 616,
          data_version: str | None = None, output: str | None = None):
    """Build the tile bytes and the report; raise on any broken invariant."""
    if not 0 <= country <= 0xFFFF:
        raise WriterError("--country %d does not fit a u16" % country)
    table, table_source = load_class_table(class_table_path)
    ways, imf_stats = load_imf(imf_path, cell)
    runs = ways_to_runs(ways, level, table, cell)
    if not runs:
        raise WriterError(
            "no way of %s maps to a parcel at level %d; nothing to write" % (cell, level)
        )

    built = {}
    infos = []
    for parcel in sorted(runs):
        result = build_road_record(level, parcel, runs[parcel], table, country)
        if result is None:
            continue
        plain, comp, info = result
        built[parcel] = dict(plain=plain, comp=comp)
        infos.append(info)
    if not built:
        raise WriterError("every run degenerated to fewer than two points")

    report: dict[str, Any] = {
        "format": REPORT_FORMAT,
        "cell": cell,
        "level": level,
        "country": country,
        "imf": dict(path=imf_path, **imf_stats),
        "class_table": table_source,
        "parcels": infos,
        "unit_ready": UNIT_READY,
        "reasons": list(REASONS_NOT_READY),
    }

    if factory_path:
        factory_bytes = _read_bytes(factory_path)
        blob, container = splice_factory(factory_bytes, level, built)
        section4_info = verify_factory(factory_bytes, blob, level, built)
        report.update(
            mode="factory",
            factory=dict(path=factory_path, size=len(factory_bytes),
                         sha256=sha256(factory_bytes)),
            container=dict(**container, factory_size=len(factory_bytes),
                           size=len(blob)),
            section4=section4_info,
        )
    else:
        if not data_version:
            raise WriterError(
                "without --factory the header is synthesised; pass "
                "--data-version yy/mm/dd/nn so the header says which card it "
                "targets"
            )
        if not DATA_VERSION_RE.match(data_version):
            raise WriterError(
                "--data-version must look like yy/mm/dd/nn, got %r" % (data_version,)
            )
        blob = synthetic_tile(built, level, cell, data_version)
        section4_info = verify_synthetic(blob, level, built)
        report.update(
            mode="synthetic",
            data_version=data_version,
            container=dict(factory_size=0, size=len(blob), in_place=0,
                           appended=len(built), superseded_bytes=0),
            section4=section4_info,
        )
        report["reasons"] = ["no factory tile: header and tables are synthesised"] + \
            list(REASONS_NOT_READY)

    tile = clarion_tile.read_tile(blob)
    for info in infos:
        y0, x0, row, col = (info["parcel"][key] for key in ("y0", "x0", "row", "col"))
        slot, _record = find_record(tile, level, y0, x0, row, 2 * col + PAIR_ROAD)
        info["block_offset"] = int(slot["block_off"])

    report.update(size=len(blob), sha256=sha256(blob), output=output)
    return blob, report


def _read_bytes(path: str) -> bytes:
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError as exc:
        raise WriterError("cannot read %s: %s" % (path, exc)) from exc


def _write_bytes(path: str, data: bytes):
    try:
        with open(path, "wb") as handle:
            handle.write(data)
    except OSError as exc:
        raise WriterError("cannot write %s: %s" % (path, exc)) from exc


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def print_report(report, out=None):
    out = out or sys.stdout
    print("tilewriter %s -> %s" % (report["cell"], report.get("output") or "-"), file=out)
    print("mode        %s%s" % (report["mode"],
                                " (header and descriptor tables preserved)"
                                if report["mode"] == "factory" else
                                " (synthesised header; not unit-ready)"), file=out)
    if report["mode"] == "factory":
        factory = report["factory"]
        print("factory     %s (%d bytes, sha256 %s)"
              % (factory["path"], factory["size"], factory["sha256"]), file=out)
    else:
        print("data ver    %s" % report["data_version"], file=out)
    imf = report["imf"]
    print("imf         %s nodes=%d ways=%d other_cells=%d short=%d multi_cell=%d"
          % (imf["path"], imf["nodes"], imf["ways"], imf["ways_other_cells"],
             imf["ways_short"], imf["ways_multi_cell"]), file=out)
    print("classes     %s" % report["class_table"], file=out)
    print("parcels     %d (level %d, country %d)"
          % (len(report["parcels"]), report["level"], report["country"]), file=out)
    for info in report["parcels"]:
        parcel = info["parcel"]
        print("  y=%d x=%d row=%d col=%d key=%04x,%04x,%04x doc=%04x,%04x shapes=%d "
              "links=%d points=%d %dB -> %dB"
              % (parcel["y0"], parcel["x0"], parcel["row"], parcel["col"],
                 info["key"][0], info["key"][1], info["key"][2],
                 info["doc_key"][0], info["doc_key"][1],
                 info["shapes"], info["links"], info["points"],
                 info["plain_bytes"], info["compressed_bytes"]), file=out)
        print("    block at 0x%06x, highways %s"
              % (info["block_offset"] or 0, ", ".join(info["highways"])), file=out)
    section = report["section4"]
    print("section4    %d record(s), %d name(s), preserve byte-identical"
          % (section["records"], section["names"]), file=out)
    container = report["container"]
    print("container   %d bytes, in-place %d, appended %d, superseded %d B"
          % (container["size"], container["in_place"], container["appended"],
             container["superseded_bytes"]), file=out)
    print("sha256      %s" % report["sha256"], file=out)
    if report.get("dry_run"):
        print("dry-run     nothing written", file=out)
    if not report["unit_ready"]:
        print("unit ready  NO", file=out)
        for reason in report["reasons"]:
            print("  - %s" % reason, file=out)
    print("result      PASS", file=out)


# --------------------------------------------------------------------------
# Self-test (no vendor data)
# --------------------------------------------------------------------------


def _background_record(points, parcel=(0x1234, 0x5678)):
    group = {"kind": 0x80,
             "shapes": [{"type": 0x0001, "ref": 0, "pts": list(points)}]}
    layer = clarion_bg.build_group(group)
    geometry = bytearray(struct.pack(">HH", 1, len(layer) // 4)) + layer
    header = [0] * 22
    header[0], header[1] = parcel
    header[2] = 0x19
    for word in (7, 8, 11, 12, 13, 14, 15, 16, 17, 18):
        header[word] = 0xFFFF
    header[9], header[10] = 11, len(geometry) // 4
    out = bytearray(44)
    struct.pack_into(">22H", out, 0, *header)
    out += geometry
    plain = bytes(out)
    if clarion_bg.build_record(clarion_bg.parse_record(plain)) != plain:
        raise RuntimeError("synthetic background record does not round-trip")
    return plain


def _section4_payload(country=616):
    header = struct.pack(">HHHHHH", 0x1234, 0x5678, section4.TYPE_TAG,
                         0xDEAD, 0x1111, 0x2222)
    header += struct.pack(">I", 0xAABBCCDD)
    header += struct.pack(">H", country)
    return header + b"\x00" + b"0=RODOS\x00" + b"0=LINDOS\x00"


def _slot(plain_comp, words, body_len, pair=0, level=1):
    """A directory slot dict with one record at ``pair``."""
    pairs = [_empty_pair(k, level) for k in range(body_len // 8)]
    pairs[pair] = struct.pack(">II", len(plain_comp) // 2, words)
    return dict(tag=0, body=b"".join(pairs),
                recs=[dict(k=pair, raw=plain_comp, words=words, flag=0)],
                block_off=0, block_end=len(plain_comp))


def _directory(level, y0, x0, slots):
    spec = clarion_bg.LEVELS[level]
    span = DIR_MESHES[level]
    return dict(off=0, kind=spec["kind"], ab=spec["ab"], y=y0, x=x0,
                typ=spec["typ"], box=(y0 + span, y0, x0, x0 + span),
                body=spec["body"], nslots=spec["slots"], slots=slots,
                empty_bodies={}, empty_tags={})


def _section4_directory(y0, x0, slots):
    """A section-4 level-1 directory: kind 0x1146's sibling 0x1046, 256-byte bodies."""
    return dict(off=0, kind=0x1046, ab=(0x20, 0x20), y=y0, x=x0, typ=0x93,
                box=(y0 + 1, y0, x0, x0 + 1), body=256, nslots=32, slots=slots,
                empty_bodies={}, empty_tags={})


def make_factory(cell="B48R058R", level=1):
    """A three-section synthetic factory tile at ``cell`` (no vendor data)."""
    yb, xb = cell_mesh(cell)
    background = _background_record([(300, 400), (340, 440), (300, 440)])
    bg_comp = compress(background)
    # The factory stub at row 4 col 3 is deliberately larger than the record the
    # writer produces, so one splice goes in place and one is appended.
    road_fixture_nodes = [(0x0040 + 8 * i, 0x0040 + 6 * i) for i in range(40)]
    with _class_mapping(default_class_table()):
        stub_plain, _ = fa_encode.build_record(
            level, yb, xb, 4, 3, road_fixture_nodes,
            [[(1, 0, 39, road_fixture_nodes[1:39])]],
            hws=["secondary"], country=616,
        )
    section1 = {0: _slot(bg_comp, len(background) // 2, 512, pair=1, level=level),
                4: _slot(compress(stub_plain), len(stub_plain) // 2, 512,
                         pair=6, level=level)}
    section4_plain = _section4_payload()
    section4_comp = compress(section4_plain)
    sections = [
        dict(id=1, count=0, levels=[dict(level=lvl, typ=typ,
                                         dirs=[_directory(level, yb, xb, section1)]
                                         if lvl == level else [])
                                   for lvl, typ in tile_header.LEVELS[1]]),
        dict(id=2, count=0, levels=[dict(level=lvl, typ=typ, dirs=[])
                                   for lvl, typ in tile_header.LEVELS[2]]),
        dict(id=4, count=0, levels=[dict(level=lvl, typ=typ,
                                         dirs=[_section4_directory(yb, xb, {
                                             0: _slot(section4_comp,
                                                      len(section4_plain) // 2, 256,
                                                      pair=0, level=1)})]
                                         if lvl == 1 else [])
                                   for lvl, typ in tile_header.LEVELS[4]]),
    ]
    tile = dict(sections=sections)
    for sec in tile["sections"]:
        words, _offsets, _groups = clarion_tile.table_words(sec)
        sec["count"] = -(-2 * words // 256)
    boxes = [(1, [(1, 0, cell_db_bounds(cell))])]
    tile["header"] = tile_header.author(tile_header.level_groups(tile), boxes,
                                       cell_db_bounds(cell), "11/01/01/01")
    return clarion_tile.write_tile(tile)


def _fixture_imf(cell="B48R058R"):
    """IMF v1 records: two ways in ``cell`` plus one in another cell."""
    lat = 48.0 + 4.0 / 48.0 + 0.2 / 48.0
    lon = 12.0 + 3.0 / 32.0 + 0.2 / 32.0
    nodes = [
        ("n1001", lat, lon),
        ("n1002", lat + 0.4 / 48.0, lon + 0.005),
        ("n1003", lat + 0.9 / 48.0, lon + 0.006),
        ("n1004", lat, lon + 0.002),
        ("n1101", 60.0, 20.0),
    ]
    records = [dict(imf=1, type="node", id=nid, lat=la, lon=lo, tile=cell)
               for nid, la, lo in nodes]
    records.append(dict(imf=1, type="way", id="w100", tile=cell, tiles=[cell],
                        nodes=["n1001", "n1002", "n1003"],
                        tags={"highway": "secondary", "name": "ul. Testowa"},
                        oneway=0, maxspeed_kmh=50))
    records.append(dict(imf=1, type="way", id="w101", tile=cell, tiles=[cell],
                        nodes=["n1004", "n1002"],
                        tags={"highway": "residential"}))
    records.append(dict(imf=1, type="way", id="w200", tile="B50R058R",
                        tiles=["B50R058R"], nodes=["n1101", "n1001"],
                        tags={"highway": "primary"}))
    return records


def selftest():
    import contextlib
    import io
    import tempfile

    checks = []

    def check(name, condition, detail=""):
        checks.append((name, bool(condition), detail))
        print("  %-42s %s%s" % (name, "OK" if condition else "FAIL",
                                (" " + str(detail)) if detail and not condition else ""))

    print("tilewriter selftest")
    cell = "B48R058R"
    with tempfile.TemporaryDirectory(prefix="tilewriter-") as tmp:
        root = Path(tmp)
        factory_path = root / (cell + ".DAT")
        factory = make_factory(cell)
        factory_path.write_bytes(factory)
        check("factory fixture parses",
              clarion_tile.read_tile(factory)["sections"][0]["id"] == 1)
        check("factory fixture round-trips",
              clarion_tile.write_tile(clarion_tile.read_tile(factory)) == factory)

        imf_path = root / "fixture.imf.jsonl"
        imf_path.write_text(
            "".join(json.dumps(record, sort_keys=True) + "\n"
                    for record in _fixture_imf(cell)),
            encoding="utf-8",
        )

        blob, report = build(str(imf_path), cell, factory_path=str(factory_path),
                             level=1, country=616,
                             output=str(root / "out.DAT"))
        check("factory mode", report["mode"] == "factory")
        check("two parcels written", len(report["parcels"]) == 2,
              [p["parcel"] for p in report["parcels"]])
        rows = [p["parcel"]["row"] for p in report["parcels"]]
        check("parcel rows are 4 and 5", rows == [4, 5], rows)
        check("both parcels are col 3",
              all(p["parcel"]["col"] == 3 for p in report["parcels"]))
        check("way from another cell skipped",
              report["imf"]["ways_other_cells"] == 1)

        check("header byte-identical", blob[:0x1000] == factory[:0x1000])
        before = clarion_tile.read_tile(factory)
        after = clarion_tile.read_tile(blob)
        check("level table preserved", blob[0x1AC:0x2AC] == factory[0x1AC:0x2AC])
        check("box table preserved", blob[0x2AC:0x300] == factory[0x2AC:0x300])
        check("section table preserved", blob[0x800:0x806] == factory[0x800:0x806])
        check("section 2 byte-identical",
              sector_fingerprint(before, 2) == sector_fingerprint(after, 2))
        check("section 4 byte-identical",
              sector_fingerprint(before, 4) == sector_fingerprint(after, 4))
        check("section 4 preserve", report["section4"] == dict(records=1, names=2,
                                                               preserved=True),
              report["section4"])
        old = records_by_position(before, 1)
        new = records_by_position(after, 1)
        bg_keys = [key for key in old if key[3] % 2 == 1]
        check("background record preserved",
              bool(bg_keys) and all(old[key] == new.get(key) for key in bg_keys), bg_keys)
        roads = [key for key in new if key[3] % 2 == 0]
        check("exactly two road streams",
              sorted(roads) == [(72, 936, 4, 6), (72, 936, 5, 6)], roads)
        slot, record = find_record(after, 1, 72, 936, 4, 6)
        plain = zlib.decompress(bytes(record["raw"]))
        check("road stream is a 0x00fa record",
              struct.unpack_from(">H", plain, 4)[0] == 0x00FA)
        shapes = fa_encode.parse_record(plain, 1)[2]
        check("replaced pair holds both runs", len(shapes) == 2, len(shapes))
        check("shapes are grouped by layer",
              [shape["layer"] for shape in shapes] == [5, 6],
              [shape["layer"] for shape in shapes])
        check("runs keep three and two points",
              [len(shape["points"]) for shape in shapes] == [2, 3],
              [len(shape["points"]) for shape in shapes])
        _slot5, record5 = find_record(after, 1, 72, 936, 5, 6)
        plain5 = zlib.decompress(bytes(record5["raw"]))
        shapes5 = fa_encode.parse_record(plain5, 1)[2]
        check("new pair holds the clipped run", len(shapes5) == 1, len(shapes5))
        check("new pair has two points",
              len(shapes5[0]["points"]) == 2, len(shapes5[0]["points"]))
        code_a, code_b = struct.unpack_from(">HH", plain, 0)
        doc_a = 32768 + int(round((48.0 + 4.0 / 48.0) * 192))
        doc_b = 52736 + int(round((12.0 + 3.0 / 32.0) * 128))
        check("key on the documented lattice",
              code_a >> 8 == doc_a >> 8 and code_b >> 8 == doc_b >> 8,
              "%04x %04x vs %04x %04x" % (code_a, code_b, doc_a, doc_b))
        check("parcel code is parcel_code()", [code_a, code_b] ==
              list(clarion_bg.parcel_code(1, 72 * 32 + 4, 936 * 32 + 3)),
              [code_a, code_b])
        check("stream is 78 9c", bytes(record["raw"][:2]) == b"\x78\x9c",
              bytes(record["raw"][:2]).hex())
        check("report key matches the record",
              report["parcels"][0]["key"] == [code_a, code_b, 0x00FA])
        check("block offsets are 256-aligned",
              slot["block_off"] % 256 == 0 and _slot5["block_off"] % 256 == 0,
              (slot["block_off"], _slot5["block_off"]))
        container = report["container"]
        check("in-place and append both exercised",
              container["in_place"] == 1 and container["appended"] == 1, container)
        check("file not smaller than the factory", len(blob) >= len(factory))

        again, _report = build(str(imf_path), cell, factory_path=str(factory_path),
                               level=1, country=616)
        check("deterministic bytes", again == blob)

        # A factory that does not cover the parcel must be refused, not guessed.
        other = root / "B48R050R.DAT"
        other.write_bytes(make_factory("B48R050R"))
        failed = ""
        try:
            build(str(imf_path), cell, factory_path=str(other), level=1, country=616)
        except WriterError as exc:
            failed = str(exc)
        check("foreign factory refused", "no level-1 directory" in failed, failed)

        # A class-table miss is a clear error naming the highway value.
        table_path = root / "classes.json"
        table_path.write_text(json.dumps({
            "format": CLASS_TABLE_FORMAT,
            "classes": {"residential": [5, 8]},
        }), encoding="utf-8")
        miss = ""
        try:
            build(str(imf_path), cell, factory_path=str(factory_path),
                  class_table_path=str(table_path), level=1, country=616)
        except ClassTableMiss as exc:
            miss = str(exc)
        check("class-table miss is an error", "highway=secondary" in miss, miss)
        check("class-table miss names the way", "w100" in miss, miss)
        with contextlib.redirect_stderr(io.StringIO()):
            code = main([str(imf_path), "--cell", cell, "--factory",
                         str(factory_path), "--class-table", str(table_path),
                         "--country", "616", "--out", str(root / "miss.DAT")])
        check("class-table miss exits 2", code == EXIT_BAD_INPUT, code)

        # No factory: synthesise the container and say it is not unit-ready.
        roads_only, synthetic = build(str(imf_path), cell, level=1, country=616,
                                      data_version="11/01/01/01")
        check("synthetic mode", synthetic["mode"] == "synthetic")
        check("synthetic tile is not unit-ready", synthetic["unit_ready"] is False)
        check("synthetic header is authored",
              roads_only[:14] == "CLARION".encode("utf-16-be"), roads_only[:14].hex())
        parsed = clarion_tile.read_tile(roads_only)
        check("synthetic tile parses", len(parsed["sections"]) == 3)
        _slot_, road = find_record(parsed, 1, 72, 936, 4, 6)
        check("synthetic road stream present",
              struct.unpack_from(">H", zlib.decompress(bytes(road["raw"])), 4)[0] == 0x00FA)
        check("synthetic section 4 absent",
              sector_fingerprint(parsed, 4) == tuple(
                  (lvl, typ, ()) for lvl, typ in tile_header.LEVELS[4]),
              sector_fingerprint(parsed, 4))
        check("synthetic report says why", "synthesised" in synthetic["reasons"][0])

        # The same code path at level 2 (parcel 1/8 x 1/12 deg); the fixture's
        # two ways share one level-2 parcel.
        lev2, report2 = build(str(imf_path), cell, level=2, country=616,
                              data_version="11/01/01/01")
        check("level 2 parcel", report2["parcels"][0]["parcel"]["row"] == 1,
              report2["parcels"][0]["parcel"])
        parsed2 = clarion_tile.read_tile(lev2)
        parcel2 = report2["parcels"][0]["parcel"]
        _slot2, road2 = find_record(parsed2, 2, 72, 936, parcel2["row"],
                                    2 * parcel2["col"] + PAIR_ROAD)
        check("level 2 road stream present",
              struct.unpack_from(">H", zlib.decompress(bytes(road2["raw"])), 4)[0] == 0x00FA)
        level2_missing = ""
        try:
            build(str(imf_path), cell, factory_path=str(factory_path), level=2,
                  country=616)
        except WriterError as exc:
            level2_missing = str(exc)
        check("factory without a level-2 dir refused",
              "no level-2 directory" in level2_missing, level2_missing)

        # CLI: write, then re-read the file from disk.
        out_path = root / "cli.DAT"
        with contextlib.redirect_stdout(io.StringIO()):
            code = main([str(imf_path), "--cell", cell, "--factory",
                         str(factory_path), "--country", "616", "--out",
                         str(out_path), "--json"])
        check("CLI exit 0", code == EXIT_OK, code)
        check("CLI wrote the built bytes", out_path.read_bytes() == blob)
        witten = clarion_tile.read_tile(out_path.read_bytes())
        check("CLI output re-reads with read_tile",
              sector_fingerprint(witten, 4) == sector_fingerprint(before, 4))

        # Dry run writes nothing.
        dry_path = root / "dry.DAT"
        with contextlib.redirect_stdout(io.StringIO()):
            code = main([str(imf_path), "--cell", cell, "--factory",
                         str(factory_path), "--country", "616", "--out",
                         str(dry_path), "--dry-run"])
        check("dry-run exit 0 and no file",
              code == EXIT_OK and not dry_path.exists(), code)

    failed = [name for name, ok, _detail in checks if not ok]
    print("tilewriter selftest: %s (%d/%d checks)"
          % ("OK" if not failed else "FAIL " + ", ".join(failed),
             len(checks) - len(failed), len(checks)))
    return EXIT_OK if not failed else EXIT_CHECK_FAILED



# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser():
    parser = argparse.ArgumentParser(
        description="Write a roads-only ZE0 map tile from mesh-split IMF v1.",
    )
    parser.add_argument("imf", nargs="?", help="mesh-split IMF v1 JSON Lines")
    parser.add_argument("--out", metavar="TILE.DAT", help="output tile path")
    parser.add_argument("--cell", help="tile cell, e.g. B48R058R (default: from --factory)")
    parser.add_argument("--factory", metavar="TILE.DAT",
                        help="factory tile to copy the header, tables and sections from")
    parser.add_argument("--level", type=int, choices=(1, 2), default=1,
                        help="section-1 level to write (default 1)")
    parser.add_argument("--country", type=int, default=616,
                        help="ISO 3166 numeric country for the records (default 616)")
    parser.add_argument("--class-table", metavar="FILE",
                        help="JSON highway -> [layer, class] table")
    parser.add_argument("--data-version", metavar="yy/mm/dd/nn",
                        help="header DATA VERSION (required without --factory)")
    parser.add_argument("--json", action="store_true", help="write the report as JSON")
    parser.add_argument("--dry-run", action="store_true", help="build and check, write nothing")
    parser.add_argument("--selftest", action="store_true", help="run the synthetic test")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.imf or not args.out:
        parser.error("IMF and --out are required (or use --selftest)")

    cell = args.cell
    if cell is None and args.factory:
        stem = Path(args.factory).name.split(".")[0]
        if CELL_RE.match(stem):
            cell = stem
    if cell is None:
        parser.error("--cell is required (or pass a factory tile named BxxRyyR.DAT)")
    if not CELL_RE.match(cell):
        parser.error("--cell %r is not a BxxRyyR name" % (cell,))

    try:
        blob, report = build(
            args.imf, cell,
            factory_path=args.factory,
            class_table_path=args.class_table,
            level=args.level,
            country=args.country,
            data_version=args.data_version,
            output=args.out,
        )
        report["dry_run"] = bool(args.dry_run)
        if not args.dry_run:
            _write_bytes(args.out, blob)
    except ClassTableMiss as exc:
        print("tilewriter: %s" % exc, file=sys.stderr)
        return EXIT_BAD_INPUT
    except WriterError as exc:
        print("tilewriter: %s" % exc, file=sys.stderr)
        return EXIT_BAD_INPUT
    except CheckFailed as exc:
        print("tilewriter: check failed: %s" % exc, file=sys.stderr)
        return EXIT_CHECK_FAILED

    if args.json:
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print_report(report)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
