#!/usr/bin/env python3
"""Split IMF v1 ways at ``BxxRyyR`` cell borders (the M5.2 mesh splitter).

IMF keeps a way whole: [`docs/research/intermediate-format.md`] assigns a way
to the cell of its first node and lists every cell it touches in ``tiles``, so
a road that crosses a cell edge stays one record with several cells.  The ZE0
tile writer needs the opposite: one road fragment per ``BxxRyyR`` file, each
with geometry that belongs to that cell only.  This tool performs that split.

What it does
------------

* Every node keeps its record and its cell.  Nodes are never moved, renamed
  or re-numbered; the output repeats the input nodes in input order.
* Every way is cut at each ``BxxRyyR`` border it crosses.  The borders are
  the grid lines of the cell formula in
  [`docs/format/map-tiles.md`](../format/map-tiles.md)::

      lat = 16/3 * k        (multiples of 8 grid units of 2/3 deg)
      lon = 4 + 8 * k       (BxxRyyR columns are 4 mod 8, e.g. 12, 20, 28)

  The exact intersection point is inserted as a node, so the fragments keep
  the full geometry and the crossing is not left to the writer.
* Tags, the derived ``oneway``/``maxspeed_kmh``/``maxspeed_cms`` fields and
  any field this tool does not know are copied to every fragment unchanged.
  Fragment order is input order, then cell order along the way.
* Fragment ids are stable and digits-only (IMF ``E007`` allows nothing else)::

      w<osm><BB><RRR><nn>      e.g. w9000000104805800
      ^    ^  ^     ^
      |    |  |     +-- fragment index on the way, 00, 01, ...
      |    |  +-------- R column, three hex digits ("058")
      |    +----------- B row, two hex digits ("48")
      +---------------- original OSM way id

  A way that needs no split keeps its original id, so unsplit ways and every
  relation member that points at them are untouched.
* Relations: a ``way`` member that points at a split way is replaced by one
  member per fragment (same role, fragment order).  A ``restriction``
  relation that loses a ``from``/``to``/``via`` role is dropped and counted,
  because ``imf_check`` rejects it (``E017``).
* New nodes are numbered from ``9000000000000`` in creation order, a range no
  OSM node id will reach; the ids are therefore stable for a given input and
  cannot collide with a real node.

Half-open cells and why a crossing makes two nodes
--------------------------------------------------

Cells are half-open, ``[lat_min, lat_max) x [lon_min, lon_max)``, so a point
exactly on a border belongs to the cell north/east of it.  One shared node
on the border therefore cannot be the last node of the west fragment *and*
the first node of the east fragment: whichever fragment holds it would list
two cells in ``tiles`` and ``imf_check --assign-tiles`` would rewrite it.

The splitter resolves this the way the card does: the fragment that owns the
border point (east/north) gets the exact intersection point, and the other
fragment gets its own copy of that point pressed ``1e-7`` deg (about 1 cm)
inside its cell.  Every fragment therefore has exactly one cell in ``tiles``,
both fragments reach the border, and the writer joins the pieces across the
border (M5.5) by those two near-identical endpoints.

``--boundary-density METRES``
-----------------------------

The exact intersection point is always inserted.  With the flag, an edge
that runs *on* a cell border (both endpoints on the same border line, e.g. a
road along 20 deg E) is additionally subdivided into pieces no longer than
``METRES``, inserting points exactly on the border.  The neighbouring cell
can then stitch to the same polyline; without the flag a 3 km border-following
edge is a single segment.  The bare flag uses 500 m.

Usage::

    python3 tools/mesh_split.py map.imf.jsonl -o map.split.jsonl
    python3 tools/mesh_split.py map.imf.jsonl -o - --json
    python3 tools/mesh_split.py map.imf.jsonl -o out.jsonl --min-piece-m 25
    python3 tools/mesh_split.py map.imf.jsonl -o out.jsonl --boundary-density 250
    python3 tools/mesh_split.py --selftest

Exit codes: ``0`` the output validates and ``imf_check --assign-tiles``
reproduces it, ``1`` the input or the output fails validation, ``2`` usage or
I/O error.  ``.gz`` input/output is detected by suffix, ``-o -`` writes the
JSONL to stdout and the report to stderr.

The grid, the validator and the field order come from ``tools/imf_check.py``
itself (``tile_for``, ``validate_text``, ``assign_tiles``, ``_reorder``), so
the splitter and the validator cannot drift apart.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

try:  # running as `python3 tools/mesh_split.py` puts tools/ on sys.path
    from imf_check import (
        ID_RE,
        IMF_VERSION,
        NODE_FIELD_ORDER,
        WAY_FIELD_ORDER,
        _join,
        _reorder,
        _split,
        assign_tiles,
        kmh_to_cms,
        read_text,
        tile_for,
        validate_text,
        write_text,
    )
except ImportError:  # pragma: no cover - explicit path for odd sys.path setups
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from imf_check import (  # type: ignore[no-redef]
        ID_RE,
        IMF_VERSION,
        NODE_FIELD_ORDER,
        WAY_FIELD_ORDER,
        _join,
        _reorder,
        _split,
        assign_tiles,
        kmh_to_cms,
        read_text,
        tile_for,
        validate_text,
        write_text,
    )

#: Grid lines of a cell: lat = 16/3 * k, lon = 4 + 8 * k (see `map-tiles.md`).
LAT_BORDER_NUM = 16.0
LAT_BORDER_DEN = 3.0
LON_BORDER_BASE = 4.0
LON_BORDER_STEP = 8.0

#: A crossing's two per-side points are at most this far apart in degrees.
#: 1e-7 deg is the IMF coordinate resolution (about 1.1 cm of latitude).
INSET_DEG = 1e-7

#: Two crossing parameters closer than this are one point (a cell corner).
T_EPS = 1e-12

#: Tolerance for "this coordinate lies exactly on a border line".
BORDER_EPS = 1e-12

#: First id of the generated border nodes (no OSM node will ever reach it).
BORDER_NODE_BASE = 9_000_000_000_000

#: Default spacing of `--boundary-density` when the flag is given without a value.
DEFAULT_DENSITY_M = 500.0

#: Mean earth radius used by the length filter (metres).
EARTH_RADIUS_M = 6_371_008.8


# --------------------------------------------------------------------------
# Grid geometry
# --------------------------------------------------------------------------


def lat_border(k: int) -> float:
    """Latitude of border ``k``: ``16 * k / 3`` degrees."""
    return (8 * k) * (2.0 / 3.0)


def lon_border(k: int) -> float:
    """Longitude of border ``k``: ``4 + 8 * k`` degrees."""
    return LON_BORDER_BASE + LON_BORDER_STEP * k


def on_lat_border(lat: float) -> bool:
    """Whether *lat* lies on a cell border."""
    k = lat * 3.0 / 16.0
    return abs(k - round(k)) <= BORDER_EPS * max(1.0, abs(k))


def on_lon_border(lon: float) -> bool:
    """Whether *lon* lies on a cell border."""
    k = (lon - LON_BORDER_BASE) / LON_BORDER_STEP
    return abs(k - round(k)) <= BORDER_EPS * max(1.0, abs(k))


def crossings(a: tuple[float, float], b: tuple[float, float]) -> list[tuple[float, float]]:
    """Return the cell-border intersection points of segment ``a -> b``, in order.

    Both coordinates are exact: the crossed axis is set to the border value,
    the other one is the linear interpolation at the same parameter.  A
    segment that passes through a cell corner yields one point, not two.
    """
    lat1, lon1 = a
    lat2, lon2 = b
    hits: list[tuple[float, str, float, float]] = []

    if lat1 != lat2:
        lo, hi = (lat1, lat2) if lat1 < lat2 else (lat2, lat1)
        first = math.floor(lo * 3.0 / 16.0) + 1
        last = math.ceil(hi * 3.0 / 16.0) - 1
        for k in range(first, last + 1):
            value = lat_border(k)
            if lo < value < hi:
                t = (value - lat1) / (lat2 - lat1)
                hits.append((t, "lat", value, lon1 + t * (lon2 - lon1)))

    if lon1 != lon2:
        lo, hi = (lon1, lon2) if lon1 < lon2 else (lon2, lon1)
        first = math.floor((lo - LON_BORDER_BASE) / LON_BORDER_STEP) + 1
        last = math.ceil((hi - LON_BORDER_BASE) / LON_BORDER_STEP) - 1
        for k in range(first, last + 1):
            value = lon_border(k)
            if lo < value < hi:
                t = (value - lon1) / (lon2 - lon1)
                hits.append((t, "lon", lat1 + t * (lat2 - lat1), value))

    hits.sort(key=lambda hit: hit[0])
    points: list[tuple[float, float]] = []
    previous_t: float | None = None
    for t, axis, lat, lon in hits:
        if points and previous_t is not None and abs(t - previous_t) <= T_EPS:
            # A corner: the two border hits are the same point, each setting
            # one exact axis.  Merge them into one point.
            previous_lat, previous_lon = points[-1]
            points[-1] = (lat, previous_lon) if axis == "lat" else (previous_lat, lon)
        else:
            points.append((lat, lon))
        previous_t = t
    return points


def segment_cell(a: tuple[float, float], b: tuple[float, float]) -> str:
    """Cell a sub-segment lies in: the cell of its midpoint.

    Sub-segments are bounded by vertices or by border crossings, so the
    midpoint is never on a border (except for segments that run along one,
    which belong to the east/north cell - the half-open owner).
    """
    return tile_for((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in metres."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def path_length_m(points: Sequence[tuple[float, float]]) -> float:
    """Length of a polyline in metres."""
    return sum(haversine_m(a, b) for a, b in zip(points, points[1:]))


def press_inside(
    point: tuple[float, float],
    toward: tuple[float, float],
    cell: str,
) -> tuple[float, float]:
    """Move *point* a little way towards *toward*, staying inside *cell*.

    ``point`` is on a cell border; ``toward`` is another point of the same
    fragment, strictly inside ``cell``.  The result is at most ``INSET_DEG``
    away and always accepted by ``tile_for`` as ``cell``.
    """
    dlat = toward[0] - point[0]
    dlon = toward[1] - point[1]
    span = max(abs(dlat), abs(dlon))
    if span <= 0.0:
        return point
    fractions = [min(0.5, INSET_DEG / span), 0.25, 0.5]
    for fraction in fractions:
        candidate = (point[0] + dlat * fraction, point[1] + dlon * fraction)
        if tile_for(*candidate) == cell:
            return candidate
    return (point[0] + dlat * 0.5, point[1] + dlon * 0.5)


def on_same_border(
    a: tuple[float, float], b: tuple[float, float]
) -> str | None:
    """``"lat"``/``"lon"`` when both points sit on one border line, else ``None``."""
    if a[0] == b[0] and on_lat_border(a[0]):
        return "lat"
    if a[1] == b[1] and on_lon_border(a[1]):
        return "lon"
    return None


# --------------------------------------------------------------------------
# New nodes
# --------------------------------------------------------------------------


class NodeFactory:
    """Allocate the border/inset nodes a split needs, once per point."""

    def __init__(self, nodes: Iterable[dict[str, Any]], boundary_density: float | None):
        self.coords: dict[str, tuple[float, float]] = {
            str(n["id"]): (float(n["lat"]), float(n["lon"])) for n in nodes
        }
        self.tiles: dict[str, str] = {str(n["id"]): str(n["tile"]) for n in nodes}
        self.records: list[dict[str, Any]] = []
        self.boundary_density = boundary_density
        self.stats = {"intersection": 0, "inset": 0, "densified": 0}
        self._used = set(self.coords)
        self._exact: dict[tuple[float, float], str] = {}
        self._inset: dict[tuple[tuple[float, float], str], str] = {}
        self._next = 1

    # -- allocation -----------------------------------------------------
    def _add(self, point: tuple[float, float], cell: str) -> str:
        while True:
            node_id = f"n{BORDER_NODE_BASE + self._next}"
            self._next += 1
            if node_id not in self._used:
                break
        self._used.add(node_id)
        tile = tile_for(*point)
        if tile != cell:  # pragma: no cover - guarded by the callers
            raise AssertionError(f"new node {point} lands in {tile}, not {cell}")
        self.coords[node_id] = point
        self.tiles[node_id] = tile
        self.records.append(
            _reorder(
                {
                    "imf": IMF_VERSION,
                    "type": "node",
                    "id": node_id,
                    "lat": point[0],
                    "lon": point[1],
                    "tile": tile,
                },
                NODE_FIELD_ORDER,
            )
        )
        return node_id

    def exact(self, point: tuple[float, float]) -> str:
        """The node exactly on a border point (owned by the east/north cell)."""
        node_id = self._exact.get(point)
        if node_id is None:
            node_id = self._add(point, tile_for(*point))
            self._exact[point] = node_id
            self.stats["intersection"] += 1
        return node_id

    def inset(self, point: tuple[float, float], cell: str) -> str:
        """A node inside *cell*, pressed off a border point that cell does not own."""
        key = (point, cell)
        node_id = self._inset.get(key)
        if node_id is None:
            node_id = self._add(point, cell)
            self._inset[key] = node_id
            self.stats["inset"] += 1
        return node_id


# --------------------------------------------------------------------------
# Splitting one way
# --------------------------------------------------------------------------


def _events(
    way: dict[str, Any],
    node_cells: dict[str, str],
    factory: NodeFactory,
) -> list[tuple[str, str | None, tuple[float, float]]]:
    """Vertices of the way with every border crossing inserted between them."""
    refs = [str(ref) for ref in way["nodes"]]
    events: list[tuple[str, str | None, tuple[float, float]]] = [
        ("v", refs[0], factory.coords[refs[0]])
    ]
    for a, b in zip(refs, refs[1:]):
        if node_cells[a] != node_cells[b]:
            for point in crossings(factory.coords[a], factory.coords[b]):
                events.append(("x", None, point))
        events.append(("v", b, factory.coords[b]))
    return events


def _groups(
    events: list[tuple[str, str | None, tuple[float, float]]],
) -> list[tuple[str, list[tuple[str, str | None, tuple[float, float]]]]]:
    """Split the event list into maximal runs that lie in one cell."""
    groups: list[tuple[str, list[tuple[str, str | None, tuple[float, float]]]]] = []
    for first, second in zip(events, events[1:]):
        cell = segment_cell(first[2], second[2])
        if groups and groups[-1][0] == cell:
            groups[-1][1].append(second)
        else:
            groups.append((cell, [first, second]))
    return groups


def _node_for(
    point: tuple[str, str | None, tuple[float, float]],
    cell: str,
    other: tuple[str, str | None, tuple[float, float]],
    factory: NodeFactory,
) -> str | None:
    """The node that represents *point* inside *cell*, or ``None`` to drop it."""
    kind, ref, xy = point
    if kind == "v" and tile_for(*xy) == cell:
        return str(ref)
    if kind == "x" and tile_for(*xy) == cell:
        return factory.exact(xy)
    pressed = press_inside(xy, other[2], cell)
    if tile_for(*pressed) != cell:  # pathological geometry; do not invent a node
        return None
    return factory.inset(pressed, cell)


def _densify(
    nodes: list[str],
    factory: NodeFactory,
) -> list[str]:
    """Insert border points every ``boundary_density`` metres on border edges."""
    density = factory.boundary_density
    if density is None:
        return nodes
    out: list[str] = []
    for index, node_id in enumerate(nodes):
        out.append(node_id)
        if index + 1 >= len(nodes):
            break
        nxt = nodes[index + 1]
        start, end = factory.coords[node_id], factory.coords[nxt]
        if on_same_border(start, end) is None:
            continue
        length = haversine_m(start, end)
        if length <= density:
            continue
        steps = int(math.ceil(length / density))
        for step in range(1, steps):
            fraction = step / steps
            point = (
                start[0] + (end[0] - start[0]) * fraction,
                start[1] + (end[1] - start[1]) * fraction,
            )
            out.append(factory.exact(point))
            factory.stats["densified"] += 1
    return out


def split_way(
    way: dict[str, Any],
    node_cells: dict[str, str],
    factory: NodeFactory,
    stats: dict[str, int],
) -> list[tuple[str, list[str]]]:
    """Return ``[(cell, node ids), ...]`` fragments of *way* in travel order."""
    events = _events(way, node_cells, factory)
    pieces: list[tuple[str, list[str]]] = []
    for cell, points in _groups(events):
        nodes: list[str] = []
        for index, point in enumerate(points):
            other = points[index + 1] if index + 1 < len(points) else points[index - 1]
            node_id = _node_for(point, cell, other, factory)
            if node_id is None:
                stats["points_skipped"] += 1
                continue
            if nodes and nodes[-1] == node_id:
                continue
            nodes.append(node_id)
        if len(nodes) < 2:
            stats["degenerate"] += 1
            continue
        pieces.append((cell, _densify(nodes, factory)))
    return pieces


def fragment_id(osm: str, cell: str, index: int) -> str:
    """``w<osm><BB><RRR><nn>`` - digits only, because IMF ``E007`` demands it."""
    b_digits = cell[1:3]
    r_digits = cell[4:7]
    return f"w{osm}{b_digits}{r_digits}{index:02d}"


# --------------------------------------------------------------------------
# Splitting a file
# --------------------------------------------------------------------------


def _fragment_record(
    way: dict[str, Any],
    way_id: str,
    nodes: list[str],
    node_tiles: dict[str, str],
) -> dict[str, Any]:
    record = dict(way)
    record["id"] = way_id
    record["nodes"] = list(nodes)
    record["tile"] = node_tiles[nodes[0]]
    record["tiles"] = sorted({node_tiles[node] for node in nodes})
    return _reorder(record, WAY_FIELD_ORDER)


def _rewrite_relation(
    relation: dict[str, Any],
    fragments: dict[str, list[str]],
    stats: dict[str, int],
) -> dict[str, Any] | None:
    """Expand way members to fragments; ``None`` drops the relation."""
    record = dict(relation)
    members: list[dict[str, Any]] = []
    for member in relation.get("members") or []:
        if not isinstance(member, dict):
            members.append(member)
            continue
        if member.get("type") != "way":
            members.append(dict(member))
            continue
        refs = fragments.get(str(member.get("ref")))
        if refs is None:  # dangling in the input; let the validator report it
            members.append(dict(member))
            continue
        for ref in refs:
            expanded = dict(member)
            expanded["ref"] = ref
            members.append(expanded)
        stats["members_expanded"] += max(0, len(refs) - 1)
    record["members"] = members

    tags = record.get("tags")
    if isinstance(tags, dict) and tags.get("type") == "restriction":
        roles = {m.get("role") for m in members if isinstance(m, dict)}
        if not {"from", "to", "via"} <= roles:
            stats["relations_dropped"] += 1
            return None
    return record


def split_records(
    records: list[Any],
    *,
    boundary_density: float | None = None,
    min_piece_m: float = 0.0,
) -> tuple[list[Any], dict[str, Any]]:
    """Split an IMF record list; return ``(records out, report)``.

    The input must already validate (``validate_text``); the caller checks
    that so a half-broken file is never silently rewritten.
    """
    if not records or not isinstance(records[0], dict) or records[0].get("type") != "header":
        raise ValueError("input does not start with the IMF header")

    header = records[0]
    nodes = [r for r in records if isinstance(r, dict) and r.get("type") == "node"]
    ways = [r for r in records if isinstance(r, dict) and r.get("type") == "way"]
    relations = [r for r in records if isinstance(r, dict) and r.get("type") == "relation"]

    factory = NodeFactory(nodes, boundary_density)
    node_cells = dict(factory.tiles)
    stats = {
        "degenerate": 0,
        "points_skipped": 0,
        "min_piece": 0,
        "relations_dropped": 0,
        "members_expanded": 0,
        "split_ways": 0,
        "unsplit_ways": 0,
        "dropped_ways": 0,
    }
    used_way_ids = {str(way["id"]) for way in ways}
    by_cell: dict[str, int] = {}
    pending: list[tuple[dict[str, Any], list[tuple[str, str, list[str]]]]] = []

    for way in ways:
        pieces = split_way(way, node_cells, factory, stats)
        if not pieces:
            stats["dropped_ways"] += 1
            pending.append((way, []))
            continue
        if len(pieces) == 1:
            cell, nodes_of_piece = pieces[0]
            stats["unsplit_ways"] += 1
            pending.append((way, [(str(way["id"]), cell, nodes_of_piece)]))
            continue
        stats["split_ways"] += 1
        osm = str(way["id"])[1:]
        entries: list[tuple[str, str, list[str]]] = []
        for index, (cell, nodes_of_piece) in enumerate(pieces):
            candidate = fragment_id(osm, cell, index)
            salt = 0
            while candidate in used_way_ids:  # pathological id overlap
                salt += 1
                candidate = f"{fragment_id(osm, cell, index)}{salt}"
            used_way_ids.add(candidate)
            entries.append((candidate, cell, nodes_of_piece))
        pending.append((way, entries))

    # --min-piece-m: drop short fragments (length on the fragment's geometry).
    surviving: dict[str, list[str]] = {}
    way_records: list[dict[str, Any]] = []
    ways_out = 0
    node_tiles = factory.tiles
    for way, entries in pending:
        kept: list[tuple[str, str, list[str]]] = []
        for way_id, cell, nodes_of_piece in entries:
            length = path_length_m([factory.coords[n] for n in nodes_of_piece])
            if min_piece_m > 0.0 and length < min_piece_m:
                stats["min_piece"] += 1
                continue
            kept.append((way_id, cell, nodes_of_piece))
        surviving[str(way["id"])] = [entry[0] for entry in kept]
        for way_id, cell, nodes_of_piece in kept:
            way_records.append(_fragment_record(way, way_id, nodes_of_piece, node_tiles))
            by_cell[cell] = by_cell.get(cell, 0) + 1
            ways_out += 1

    relations_out: list[dict[str, Any]] = []
    for relation in relations:
        rewritten = _rewrite_relation(relation, surviving, stats)
        if rewritten is not None:
            relations_out.append(rewritten)

    out: list[Any] = [header]
    out.extend(nodes)
    out.extend(factory.records)
    out.extend(way_records)
    out.extend(relations_out)

    spans = sum(1 for record in way_records if len(record.get("tiles") or []) != 1)
    report: dict[str, Any] = {
        "records": {
            "nodes_in": len(nodes),
            "ways_in": len(ways),
            "relations_in": len(relations),
            "nodes_out": len(nodes) + len(factory.records),
            "ways_out": ways_out,
            "relations_out": len(relations_out),
        },
        "ways": {
            "split": stats["split_ways"],
            "unsplit": stats["unsplit_ways"],
            "dropped": stats["dropped_ways"],
            "cross_border": stats["split_ways"],
        },
        "fragments": {"total": ways_out, "by_cell": dict(sorted(by_cell.items()))},
        "nodes": {
            "added": len(factory.records),
            "intersection": factory.stats["intersection"],
            "inset": factory.stats["inset"],
            "densified": factory.stats["densified"],
        },
        "dropped": {
            "degenerate": stats["degenerate"],
            "min_piece": stats["min_piece"],
            "points": stats["points_skipped"],
        },
        "relations": {
            "dropped": stats["relations_dropped"],
            "members_expanded": stats["members_expanded"],
        },
        "mode": {
            "exact_clip": True,
            "boundary_density_m": factory.boundary_density,
            "min_piece_m": float(min_piece_m),
        },
        "spans": spans,
    }
    return out, report


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def print_report(report: dict[str, Any], *, stream: Any = None, path: str = "") -> None:
    out = stream or sys.stdout
    records = report["records"]
    ways = report["ways"]
    nodes = report["nodes"]
    mode = report["mode"]
    density = mode["boundary_density_m"]
    print(f"file        {path}", file=out)
    if density is None:
        print("mode        exact clip; boundary density off", file=out)
    else:
        print(f"mode        exact clip; boundary density {density:g} m", file=out)
    print(
        f"input       nodes={records['nodes_in']} ways={records['ways_in']} "
        f"relations={records['relations_in']}",
        file=out,
    )
    print(
        f"ways        split={ways['split']} unsplit={ways['unsplit']} "
        f"dropped={ways['dropped']} cross_border={ways['cross_border']}",
        file=out,
    )
    print(
        f"fragments   {report['fragments']['total']}  "
        + " ".join(
            f"{cell}={count}" for cell, count in report["fragments"]["by_cell"].items()
        ),
        file=out,
    )
    print(
        f"nodes       added={nodes['added']} (intersection={nodes['intersection']} "
        f"inset={nodes['inset']} densified={nodes['densified']}) "
        f"out={records['nodes_out']}",
        file=out,
    )
    print(
        f"relations   out={records['relations_out']} "
        f"dropped={report['relations']['dropped']} "
        f"members_expanded={report['relations']['members_expanded']}",
        file=out,
    )
    if (
        report["dropped"]["degenerate"]
        or report["dropped"]["min_piece"]
        or report["dropped"]["points"]
    ):
        print(
            f"dropped     pieces degenerate={report['dropped']['degenerate']} "
            f"min_piece={report['dropped']['min_piece']} "
            f"points={report['dropped']['points']}",
            file=out,
        )
    print(f"spans       {report['spans']} way(s) with more than one cell", file=out)
    print(
        f"assign      imf_check --assign-tiles "
        f"{'agrees' if report.get('assign_tiles') else 'DIFFERS'}",
        file=out,
    )
    print(
        f"errors      {report.get('errors', 0)}",
        file=out,
    )
    print(f"result      {'PASS' if report.get('ok') else 'FAIL'}", file=out)


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------


def _fixture() -> list[Any]:
    """A synthetic extract with every shape the splitter must handle.

    * ``w100`` crosses the 20 deg E border twice (west, east, west);
    * ``w101`` is a closed roundabout inside one cell (must not be touched);
    * ``w102`` runs through a node exactly on the border (``n1022``);
    * ``w103`` runs *along* the 20 deg E border (``--boundary-density``);
    * ``w104`` is a short cross-border stub (``--min-piece-m``);
    * ``r100`` is a turn restriction on the split ways.
    """
    header = {
        "imf": IMF_VERSION,
        "type": "header",
        "generated": "2026-11-06T00:00:00Z",
        "generator": "tools/mesh_split.py --selftest",
        "source": {
            "name": "synthetic-mesh-split.osm.pbf",
            "timestamp": "2026-11-06T00:00:00Z",
            "sequence": 1,
        },
        "license": {
            "database": "ODbL-1.0",
            "attribution": "© OpenStreetMap contributors",
            "url": "https://www.openstreetmap.org/copyright",
            "attribution_file": "ODbL.txt",
        },
        "grid": {
            "tile": "BxxRyyR (hex): lat_min=int(B,16)*2/3, lon_max=108-int(R,16)",
            "units": "WGS84 degrees, 7 decimals",
            "speed": "integer cm/s",
        },
    }

    nodes: list[dict[str, Any]] = []

    def node(node_id: str, lat: float, lon: float, **extra: Any) -> None:
        record: dict[str, Any] = {
            "imf": IMF_VERSION,
            "type": "node",
            "id": node_id,
            "lat": lat,
            "lon": lon,
            "tile": tile_for(lat, lon),
        }
        record.update(extra)
        nodes.append(_reorder(record, NODE_FIELD_ORDER))

    # w100: west, east, west (two crossings of the 20 E border).
    node("n1001", 51.10, 19.99)
    node("n1002", 51.20, 20.01)
    node("n1003", 51.30, 19.99)
    # w101: closed roundabout inside B48R058R.
    node("n1010", 51.000, 17.000)
    node("n1011", 51.001, 17.002)
    node("n1012", 51.002, 17.000)
    node("n1013", 51.001, 16.998)
    # w102: a vertex exactly on the 20 E border (n1022, owned by the east cell).
    node("n1020", 51.05, 19.990)
    node("n1021", 51.05, 19.995)
    node("n1022", 51.04, 20.0)
    node("n1023", 51.04, 20.010)
    # w103: both vertices on the 20 E border (a border-following edge).
    node("n1030", 51.02, 20.0)
    node("n1031", 51.05, 20.0)
    # w104: a short cross-border stub for --min-piece-m.
    node("n1040", 51.07, 19.9995)
    node("n1041", 51.07, 20.001)
    # w105: crosses the 53.3333 N border (B48R058R -> B50R058R).
    node("n1050", 53.320, 15.0)
    node("n1051", 53.340, 15.0)

    tiles = {str(record["id"]): str(record["tile"]) for record in nodes}

    def way(
        way_id: str,
        refs: list[str],
        tags: dict[str, str],
        **extra: Any,
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "imf": IMF_VERSION,
            "type": "way",
            "id": way_id,
            "nodes": refs,
            "tile": tiles[refs[0]],
            "tiles": sorted({tiles[ref] for ref in refs}),
            "tags": tags,
        }
        record.update(extra)
        return _reorder(record, WAY_FIELD_ORDER)

    def derived(tags: dict[str, str], oneway: str | None = None) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        if oneway is not None:
            extra["oneway"] = oneway
        raw = tags.get("maxspeed")
        if raw is not None and raw.isdigit():
            extra["maxspeed_kmh"] = int(raw)
            extra["maxspeed_cms"] = kmh_to_cms(int(raw))
        return extra

    w100_tags = {
        "highway": "secondary",
        "name": "ul. Graniczna",
        "maxspeed": "50",
        "lanes": "2",
        "surface": "asphalt",
    }
    w101_tags = {
        "highway": "residential",
        "junction": "roundabout",
        "oneway": "yes",
        "name": "Rondo Testowe",
        "maxspeed": "30",
    }
    w102_tags = {"highway": "secondary", "name": "ul. Sudecka", "maxspeed": "50"}
    w103_tags = {"highway": "service", "name": "Droga Graniczna", "maxspeed": "20"}
    w104_tags = {"highway": "residential", "name": "Zaułek", "maxspeed": "30"}
    w105_tags = {"highway": "primary", "name": "ul. Północna", "maxspeed": "70"}
    ways = [
        way("w100", ["n1001", "n1002", "n1003"], w100_tags, **derived(w100_tags, "no")),
        way(
            "w101",
            ["n1010", "n1011", "n1012", "n1013", "n1010"],
            w101_tags,
            **derived(w101_tags, "yes"),
        ),
        way("w102", ["n1020", "n1021", "n1022", "n1023"], w102_tags, **derived(w102_tags, "no")),
        way("w103", ["n1030", "n1031"], w103_tags, **derived(w103_tags, "no")),
        way("w104", ["n1040", "n1041"], w104_tags, **derived(w104_tags, "no")),
        way("w105", ["n1050", "n1051"], w105_tags, **derived(w105_tags, "no")),
    ]
    relations = [
        {
            "imf": IMF_VERSION,
            "type": "relation",
            "id": "r100",
            "members": [
                {"type": "way", "ref": "w100", "role": "from"},
                {"type": "node", "ref": "n1002", "role": "via"},
                {"type": "way", "ref": "w102", "role": "to"},
            ],
            "tags": {"type": "restriction", "restriction": "no_left_turn"},
        }
    ]
    return [header, *nodes, *ways, *relations]


def _find(records: list[Any], record_id: str) -> dict[str, Any]:
    for record in records:
        if isinstance(record, dict) and record.get("id") == record_id:
            return record
    raise KeyError(record_id)


def _ways_of(records: list[Any], osm_id: str) -> list[dict[str, Any]]:
    """Every way whose id is ``w<osm>`` or ``w<osm><cell><nn>``."""
    out = []
    for record in records:
        if not isinstance(record, dict) or record.get("type") != "way":
            continue
        rid = str(record.get("id"))
        if rid == osm_id:
            out.append(record)
            continue
        body = rid[1:]
        if body.startswith(osm_id[1:]) and len(body) - len(osm_id) + 1 == 7:
            out.append(record)
    return out


def selftest() -> int:
    """Synthetic split checks: counts, exact crossings, ids, tiling, relations."""
    print("mesh_split selftest")
    failures: list[str] = []
    count = 0

    def check(name: str, condition: bool, detail: str = "") -> None:
        nonlocal count
        count += 1
        print(f"  {name:<34} {'OK' if condition else 'FAIL'} {detail}".rstrip())
        if not condition:
            failures.append(name)

    source = _fixture()
    source_text = _join(source)
    source_report = validate_text(source_text, "fixture")
    check(
        "fixture validates",
        source_report.ok,
        f"nodes={source_report.nodes} ways={source_report.ways} "
        f"relations={source_report.relations}",
    )

    output, report = split_records(source)
    text = _join(output)
    report = {**report, "ok": True, "errors": 0, "assign_tiles": True}
    valid = validate_text(text, "split")
    check(
        "split validates",
        valid.ok,
        f"errors={len(valid.errors)} nodes={valid.nodes} ways={valid.ways} "
        f"relations={valid.relations}",
    )
    check("split has no warnings", not valid.warnings,
          str([w.code for w in valid.warnings][:4]))

    # -- fragment counts -------------------------------------------------
    w100 = _ways_of(output, "w100")
    w101 = _ways_of(output, "w101")
    w102 = _ways_of(output, "w102")
    w103 = _ways_of(output, "w103")
    w104 = _ways_of(output, "w104")
    w105 = _ways_of(output, "w105")
    check("w100 fragments", len(w100) == 3, f"{len(w100)}")
    check("roundabout fragment", len(w101) == 1, f"{len(w101)}")
    check("border-node way fragments", len(w102) == 2, f"{len(w102)}")
    check("border-following way", len(w103) == 1, f"{len(w103)}")
    check("stub fragments", len(w104) == 2, f"{len(w104)}")
    check("latitude-border way fragments", len(w105) == 2, f"{len(w105)}")
    check(
        "total fragments",
        report["fragments"]["total"] == 11,
        f"{report['fragments']['total']}",
    )
    check(
        "cross-border ways",
        report["ways"]["cross_border"] == 4,
        f"{report['ways']['cross_border']}",
    )
    check("no way spans cells", report["spans"] == 0, f"spans={report['spans']}")
    check(
        "every fragment one cell",
        all(len(way["tiles"]) == 1 for way in output if way.get("type") == "way"),
    )

    # -- exact intersection points ---------------------------------------
    middle = w100[1]
    start = _find(output, middle["nodes"][0])
    end = _find(output, middle["nodes"][-1])
    check(
        "crossing 1 exact",
        start["lon"] == 20.0 and abs(start["lat"] - 51.15) < 1e-9,
        f"{start['lat']!r},{start['lon']!r}",
    )
    check(
        "crossing 2 exact",
        end["lon"] == 20.0 and abs(end["lat"] - 51.25) < 1e-9,
        f"{end['lat']!r},{end['lon']!r}",
    )
    check(
        "middle fragment cell",
        middle["tiles"] == ["B48R050R"] and middle["tile"] == "B48R050R",
        str(middle["tiles"]),
    )
    check("crossing nodes differ", start["id"] != end["id"], f"{start['id']}")

    west = w100[0]
    tail = _find(output, west["nodes"][-1])
    check(
        "west side pressed inside",
        19.9999999 < tail["lon"] < 20.0 and tail["tile"] == "B48R058R",
        f"{tail['id']} lon={tail['lon']!r} tile={tail['tile']}",
    )
    check(
        "west/east pair within 1e-7 deg",
        abs(tail["lon"] - start["lon"]) <= INSET_DEG + 1e-15,
        f"{tail['lon']!r} vs {start['lon']!r}",
    )

    # -- latitude border --------------------------------------------------
    south, north = w105
    edge = _find(output, north["nodes"][0])
    check(
        "lat crossing exactly on 16/3",
        edge["lat"] == lat_border(10) and edge["lon"] == 15.0
        and edge["tile"] == "B50R058R",
        f"{edge['lat']!r},{edge['lon']!r} tile={edge['tile']}",
    )
    check(
        "lat border cells",
        south["tiles"] == ["B48R058R"] and north["tiles"] == ["B50R058R"],
        f"{south['tiles']} {north['tiles']}",
    )
    south_tail = _find(output, south["nodes"][-1])
    check(
        "lat south side pressed inside",
        south_tail["lat"] < lat_border(10) and south_tail["tile"] == "B48R058R",
        f"lat={south_tail['lat']!r} tile={south_tail['tile']}",
    )

    # -- tags and derived fields -----------------------------------------
    original = _find(source, "w100")
    check(
        "tags preserved",
        all(way["tags"] == original["tags"] for way in w100),
        str(w100[0]["tags"].get("name")),
    )
    check(
        "derived fields preserved",
        all(
            (way["oneway"], way["maxspeed_kmh"], way["maxspeed_cms"])
            == (original["oneway"], original["maxspeed_kmh"], original["maxspeed_cms"])
            for way in w100
        ),
        f"oneway={w100[0]['oneway']} kmh={w100[0]['maxspeed_kmh']}",
    )
    check(
        "fragment order follows the way",
        w100[0]["nodes"][0] == "n1001"
        and w100[1]["nodes"][0] == start["id"]
        and w100[2]["nodes"][-1] == "n1003"
        and _find(output, w100[2]["nodes"][0])["tile"] == "B48R058R"
        and _find(output, w100[2]["nodes"][0])["lon"] < 20.0,
        f"{w100[2]['nodes'][0]}",
    )

    # -- border node and roundabout --------------------------------------
    border_node = _find(output, "n1022")
    check(
        "border node kept as is",
        border_node["lat"] == 51.04 and border_node["lon"] == 20.0
        and border_node["tile"] == "B48R050R",
        f"tile={border_node['tile']}",
    )
    east = w102[1]
    check("border node starts east fragment", east["nodes"][0] == "n1022", east["nodes"][0])
    check("border node ends west fragment", w102[0]["nodes"][-1] != "n1022", w102[0]["nodes"][-1])
    check(
        "roundabout id and ring unchanged",
        w101[0]["id"] == "w101"
        and w101[0]["nodes"] == ["n1010", "n1011", "n1012", "n1013", "n1010"],
        str(w101[0]["nodes"]),
    )

    # -- ids and node cells ----------------------------------------------
    check(
        "all ids are digits only",
        all(ID_RE.match(str(record["id"])) for record in output
            if record.get("type") in ("node", "way", "relation")),
    )
    bad = dict(original)
    bad["id"] = "w100.B48R058R.0"
    bad["nodes"] = ["n1001", start["id"]]
    bad_text = _join([source[0], *[r for r in output if r.get("type") == "node"], bad])
    check(
        "dotted id is rejected (E007)",
        any(issue.code == "E007" for issue in validate_text(bad_text, "dotted").errors),
    )
    check(
        "fragment id shape",
        start.get("id") is not None and w100[1]["id"].startswith("w100") and
        w100[1]["id"].endswith("01") and len(w100[1]["id"]) == len("w100") + 7,
        w100[1]["id"],
    )
    check(
        "nodes keep their cell",
        all(record["tile"] == tile_for(float(record["lat"]), float(record["lon"]))
            for record in output if record.get("type") == "node"),
    )

    # -- --assign-tiles agreement ----------------------------------------
    assigned, issues = assign_tiles(_split(text))
    check(
        "assign-tiles reproduces the file",
        not issues and _join(assigned) == text,
        f"issues={len(issues)}",
    )

    # -- relation rewrite ------------------------------------------------
    relation = _find(output, "r100")
    roles: dict[str, list[str]] = {}
    for member in relation["members"]:
        roles.setdefault(member["role"], []).append(member["ref"])
    check("relation from expanded", len(roles.get("from", [])) == 3, str(roles.get("from")))
    check("relation to expanded", len(roles.get("to", [])) == 2, str(roles.get("to")))
    check("relation via kept", roles.get("via") == ["n1002"], str(roles.get("via")))

    # -- --min-piece-m ---------------------------------------------------
    filtered, filtered_report = split_records(source, min_piece_m=50.0)
    filtered_text = _join(filtered)
    check(
        "min-piece drops the 35 m piece",
        filtered_report["dropped"]["min_piece"] == 1
        and filtered_report["fragments"]["total"] == 10,
        f"dropped={filtered_report['dropped']['min_piece']} "
        f"total={filtered_report['fragments']['total']}",
    )
    check("min-piece output validates", validate_text(filtered_text, "min").ok)
    check(
        "min-piece keeps the long side",
        len(_ways_of(filtered, "w104")) == 1,
        str([way["id"] for way in _ways_of(filtered, "w104")]),
    )

    # -- --boundary-density ----------------------------------------------
    dense, dense_report = split_records(source, boundary_density=300.0)
    dense_text = _join(dense)
    dense_way = _ways_of(dense, "w103")[0]
    inserted = [node for node in dense_way["nodes"][1:-1]]
    lengths = []
    points = [(_find(dense, node)["lat"], _find(dense, node)["lon"]) for node in dense_way["nodes"]]
    lengths = [haversine_m(a, b) for a, b in zip(points, points[1:])]
    check(
        "density inserted nodes",
        len(inserted) == int(math.ceil(path_length_m(
            [
                (float(_find(source, "n1030")["lat"]), float(_find(source, "n1030")["lon"])),
                (float(_find(source, "n1031")["lat"]), float(_find(source, "n1031")["lon"])),
            ]
        ) / 300.0)) - 1,
        f"{len(inserted)} inserted",
    )
    check(
        "density points on the border",
        all(_find(dense, node)["lon"] == 20.0 and _find(dense, node)["tile"] == "B48R050R"
            for node in inserted),
    )
    check(
        "density spacing within METRES",
        all(length <= 300.0 + 1e-6 for length in lengths),
        f"max {max(lengths):.1f} m",
    )
    check("density output validates", validate_text(dense_text, "dense").ok)
    check(
        "density counts reported",
        dense_report["nodes"]["densified"] == len(inserted),
        f"{dense_report['nodes']['densified']}",
    )
    check(
        "density leaves cells alone",
        len(dense_way["tiles"]) == 1 and dense_way["tiles"] == ["B48R050R"],
        str(dense_way["tiles"]),
    )

    # -- a single segment that crosses several borders at once ------------
    long_nodes = [
        {
            "imf": IMF_VERSION,
            "type": "node",
            "id": "n2001",
            "lat": 48.1,
            "lon": 12.1,
            "tile": tile_for(48.1, 12.1),
        },
        {
            "imf": IMF_VERSION,
            "type": "node",
            "id": "n2002",
            "lat": 58.0,
            "lon": 35.0,
            "tile": tile_for(58.0, 35.0),
        },
    ]
    long_way = {
        "imf": IMF_VERSION,
        "type": "way",
        "id": "w2001",
        "nodes": ["n2001", "n2002"],
        "tile": long_nodes[0]["tile"],
        "tiles": sorted({str(node["tile"]) for node in long_nodes}),
        "tags": {"highway": "primary", "name": "Daleka"},
    }
    long_out, long_report = split_records([source[0], *long_nodes, long_way])
    check(
        "multi-border segment",
        long_report["fragments"]["total"] == 4
        and long_report["fragments"]["by_cell"]
        == {"B48R050R": 1, "B48R058R": 1, "B50R048R": 1, "B50R050R": 1},
        str(long_report["fragments"]["by_cell"]),
    )
    check(
        "multi-border output validates",
        validate_text(_join(long_out), "long").ok and long_report["spans"] == 0,
    )

    # -- determinism and idempotence -------------------------------------
    again, _ = split_records(source)
    check("deterministic bytes", _join(again) == text)
    twice, _ = split_records(_split(text))
    check("idempotent", _join(twice) == text)

    print(
        f"mesh_split selftest: {'OK' if not failures else 'FAILED'} "
        f"({count - len(failures)}/{count} checks)"
    )
    return 1 if failures else 0


def factory_coords(records: list[Any], node_id: str) -> tuple[float, float]:
    """Coordinate of an input node (kept for ad-hoc checks from the CLI)."""
    record = _find(records, node_id)
    return (float(record["lat"]), float(record["lon"]))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Split IMF v1 ways at BxxRyyR cell borders",
        epilog=(
            "Exit codes: 0 output validates and --assign-tiles reproduces it, "
            "1 validation failure, 2 usage or I/O error."
        ),
    )
    parser.add_argument("file", nargs="?", help="IMF JSON Lines input ('-' = stdin)")
    parser.add_argument(
        "-o",
        "--out",
        help="output path ('-' = stdout; gzip by .gz suffix); default stdout",
    )
    parser.add_argument(
        "--json", action="store_true", help="machine-readable report"
    )
    parser.add_argument(
        "--min-piece-m",
        type=float,
        default=0.0,
        metavar="METRES",
        help="drop fragments shorter than METRES (default 0 = keep all)",
    )
    parser.add_argument(
        "--boundary-density",
        type=float,
        nargs="?",
        const=DEFAULT_DENSITY_M,
        default=None,
        metavar="METRES",
        help=(
            "subdivide border-following edges at METRES spacing, inserting "
            f"points exactly on the border (bare flag: {DEFAULT_DENSITY_M:g} m)"
        ),
    )
    parser.add_argument("--selftest", action="store_true", help="run synthetic tests")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.file:
        parser.error("a file is required unless --selftest is used")
    if args.boundary_density is not None and args.boundary_density <= 0.0:
        parser.error("--boundary-density must be positive")
    if args.min_piece_m < 0.0:
        parser.error("--min-piece-m must not be negative")

    try:
        text = read_text(args.file)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: {args.file}: {exc}", file=sys.stderr)
        return 2
    try:
        records = _split(text)
    except json.JSONDecodeError as exc:
        print(f"error: {args.file}: invalid JSON: {exc.msg}", file=sys.stderr)
        return 2

    before = validate_text(text, args.file)
    if not before.ok:
        print(f"file        {args.file}", file=sys.stderr)
        print(f"errors      {len(before.errors)} (input must validate first)", file=sys.stderr)
        for issue in before.errors[:20]:
            print(f"  {issue.code} line {issue.line:>5}  {issue.message}", file=sys.stderr)
        return 1

    try:
        output, report = split_records(
            records,
            boundary_density=args.boundary_density,
            min_piece_m=args.min_piece_m,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out_text = _join(output)
    target = args.out or "-"
    if target != "-":
        try:
            write_text(target, out_text)
        except OSError as exc:
            print(f"error: {target}: {exc}", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(out_text)
        sys.stdout.flush()

    after = validate_text(out_text, target)
    assigned, issues = assign_tiles(_split(out_text))
    agrees = not issues and _join(assigned) == out_text
    report["path"] = target
    report["errors"] = len(after.errors)
    report["warnings"] = len(after.warnings)
    report["assign_tiles"] = agrees
    report["ok"] = after.ok and agrees and report["spans"] == 0

    stream = sys.stderr if target == "-" else sys.stdout
    if args.json:
        print(json.dumps(
            {
                **report,
                "validation": {
                    "errors": len(after.errors),
                    "warnings": len(after.warnings),
                },
            },
            indent=2,
        ), file=stream)
    else:
        print_report(report, stream=stream, path=target)
        for issue in after.errors[:20]:
            print(f"  {issue.code} line {issue.line:>5}  {issue.message}", file=stream)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
