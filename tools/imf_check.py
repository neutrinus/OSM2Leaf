#!/usr/bin/env python3
"""Validate, tile-assign and generate IMF (intermediate map format) files.

IMF is the file-based intermediate representation between an OSM extract and
the ZE0 tile writer. It is specified in ``docs/research/intermediate-format.md``;
this tool is the executable definition of that document.

What is checked (one error code per rule, see ``RULES``):

* JSON Lines shape, ``imf`` version, header first, one header only
* record schema per kind (``node``, ``way``, ``relation``) and tag types
* stable-ID syntax (``n|w|r`` + positive OSM id) and uniqueness
* WGS84 coordinate range and the ``BxxRyyR`` tile a record is assigned to
* way node references resolve (nodes must precede the ways using them)
* the way's derived ``tile`` (anchor = first node) and ``tiles`` list
* ``oneway`` / ``maxspeed`` / ``access`` sanity and unit conversion
* relation member references and the supported relation subsets
* header provenance: source snapshot and ODbL attribution

Usage::

    python3 tools/imf_check.py map.imf.jsonl
    python3 tools/imf_check.py map.imf.jsonl --json
    python3 tools/imf_check.py map.imf.jsonl --assign-tiles -o map.imf.jsonl
    python3 tools/imf_check.py --sample -o map.imf.jsonl
    python3 tools/imf_check.py --selftest

``.gz`` input/output is detected by suffix. Exit codes: ``0`` the file
validates (warnings allowed), ``1`` validation errors, ``2`` usage or I/O
error. ``--sample`` and ``--assign-tiles`` exit with the exit code of the
validation they perform on their own output.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

IMF_VERSION = 1

TILE_RE = re.compile(r"B([0-9A-F]{2})R([0-9A-F]{3})R\Z")
ID_RE = re.compile(r"([nwr])([1-9][0-9]{0,18})\Z")
NODE_REF_RE = re.compile(r"n[1-9][0-9]{0,18}\Z")

# Grid: lat_min = int(B,16)*2/3, lon_max = 108-int(R,16), span 8 units both ways.
LAT_UNIT = 2.0 / 3.0
SPAN = 8
LON_ORIGIN = 108
# Absorbs float noise on exact cell boundaries (e.g. lat = 160/3).
EPS = 1e-9

ONEWAY_VALUES = ("yes", "no", "-1")

HIGHWAY_VALUES = {
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "unclassified", "residential", "living_street", "service", "track",
    "motorway_link", "trunk_link", "primary_link", "secondary_link",
    "tertiary_link", "road", "pedestrian", "footway", "cycleway", "path",
    "steps", "bridleway", "construction", "busway",
}

ACCESS_VALUES = {
    "yes", "no", "private", "permissive", "destination", "delivery",
    "customers", "agricultural", "forestry", "unknown", "dismount",
    "emergency", "psv", "bus", "taxi", "hov", "designated",
}

RELATION_SUBSET = ("restriction", "boundary", "route")

#: Every error code this tool can emit. ``--selftest`` fails if a code has no
#: synthetic failure case, so the list cannot drift away from the checks.
RULES = {
    "E001": "first record is not the IMF header",
    "E002": "unsupported or missing imf version",
    "E003": "line is not valid JSON",
    "E004": "record is missing a required field",
    "E005": "unknown record type",
    "E006": "duplicate record id",
    "E007": "record id does not match its type (n/w/r prefix)",
    "E008": "coordinate outside the WGS84 range or not a finite number",
    "E009": "node tile does not match the mesh computed from its coordinates",
    "E010": "malformed tile id, or a way with fewer than two nodes",
    "E011": "way node reference does not resolve (nodes must precede ways)",
    "E012": "way tile is not the tile of its first node",
    "E013": "way tiles list does not equal the set of its nodes' tiles",
    "E014": "oneway value is not yes/no/-1, or is set without highway",
    "E015": "maxspeed is out of range or maxspeed_cms disagrees with km/h",
    "E016": "relation member reference does not resolve",
    "E017": "restriction relation is missing a tag or a from/via/to member",
    "E018": "tags/addr/poi is not a string-to-string object",
    "E019": "way repeats the same node consecutively",
    "E020": "header lacks ODbL licence information",
    "E021": "header lacks a source snapshot",
    "E022": "access value is not in the supported set",
}

WARNINGS = {
    "W001": "highway way has no name",
    "W002": "highway way has no numeric maxspeed",
    "W003": "highway value is outside the known set",
    "W004": "node is not used by any way and is not an address or POI",
    "W005": "relation is outside the supported subset or lacks fields",
    "W006": "way has no highway tag but a routing attribute",
}


# --------------------------------------------------------------------------
# Grid and unit helpers
# --------------------------------------------------------------------------


def tile_box(name: str) -> tuple[float, float, float, float]:
    """Return ``(lat_min, lat_max, lon_min, lon_max)`` for ``BxxRyyR``."""
    match = TILE_RE.match(name)
    if not match:
        raise ValueError(f"not a BxxRyyR tile id: {name!r}")
    b = int(match.group(1), 16)
    r = int(match.group(2), 16)
    lat_min = b * LAT_UNIT
    lon_max = LON_ORIGIN - r
    return lat_min, lat_min + SPAN * LAT_UNIT, lon_max - SPAN, lon_max


def tile_for(lat: float, lon: float) -> str:
    """Return the whole ``BxxRyyR`` cell that contains ``(lat, lon)``.

    Cells are half-open on all sides: ``[lat_min, lat_max)`` and
    ``[lon_min, lon_max)``. B and R are multiples of ``SPAN`` because a tile
    is 8 x 8 grid units.
    """
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise ValueError("coordinate is not finite")
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError("coordinate outside WGS84")
    b = SPAN * math.floor(lat * 3.0 / (2.0 * SPAN) + EPS)
    steps = math.ceil((LON_ORIGIN - lon) / SPAN - EPS)
    r = SPAN * (steps - 1)
    if not (0 <= b <= 0xF8) or not (0 <= r <= 0x400):
        raise ValueError("coordinate has no BxxRyyR cell in the shipped grid")
    return f"B{b:02X}R{r:03X}R"


def tile_in_grid(name: str) -> bool:
    """Whether *name* is a syntactically valid cell of the 8 x 8 unit grid."""
    match = TILE_RE.match(name)
    if not match:
        return False
    b = int(match.group(1), 16)
    r = int(match.group(2), 16)
    return b % SPAN == 0 and r % SPAN == 0 and 0 <= b <= 0xF8 and 0 <= r <= 0x400


def kmh_to_cms(kmh: int) -> int:
    """Integer cm/s, rounded half up. 1 cm/s is 0.036 km/h."""
    return (kmh * 250 + 4) // 9


def cms_to_kmh(cms: int) -> int:
    """Nearest integer km/h, rounded half up."""
    return (cms * 9 + 125) // 250


# --------------------------------------------------------------------------
# Report model
# --------------------------------------------------------------------------


@dataclass
class Issue:
    code: str
    line: int
    message: str
    severity: str = "error"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "line": self.line,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass
class Report:
    path: str = ""
    nodes: int = 0
    ways: int = 0
    relations: int = 0
    named_ways: int = 0
    speed_ways: int = 0
    oneway_ways: int = 0
    addresses: int = 0
    pois: int = 0
    tiles: dict[str, dict[str, int]] = field(default_factory=dict)
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, code: str, line: int, message: str) -> None:
        self.errors.append(Issue(code, line, message))

    def warn(self, code: str, line: int, message: str) -> None:
        self.warnings.append(Issue(code, line, message, severity="warning"))

    def note_tile(self, tile: str | None, kind: str) -> None:
        if not tile:
            return
        bucket = self.tiles.setdefault(tile, {"nodes": 0, "ways": 0})
        bucket[kind] += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "records": {
                "nodes": self.nodes,
                "ways": self.ways,
                "relations": self.relations,
            },
            "attributes": {
                "named_ways": self.named_ways,
                "maxspeed_ways": self.speed_ways,
                "oneway_ways": self.oneway_ways,
                "addresses": self.addresses,
                "pois": self.pois,
            },
            "tiles": dict(sorted(self.tiles.items())),
            "errors": [i.to_dict() for i in self.errors],
            "warnings": [i.to_dict() for i in self.warnings],
        }


# --------------------------------------------------------------------------
# Validator
# --------------------------------------------------------------------------


class Validator:
    """Streaming validator; nodes must appear before the ways that use them."""

    def __init__(self, path: str = "<text>", *, warnings: bool = True) -> None:
        self.report = Report(path=path)
        self.keep_warnings = warnings
        self.header: dict[str, Any] | None = None
        self.node_tiles: dict[str, list[Any]] = {}  # id -> [tile, used]
        self.way_tiles: dict[str, tuple[str, ...]] = {}
        self.relation_ids: set[str] = set()
        self.seen_header = False

    # -- helpers --------------------------------------------------------
    def _error(self, code: str, line: int, message: str) -> None:
        self.report.add(code, line, message)

    def _warn(self, code: str, line: int, message: str) -> None:
        if self.keep_warnings:
            self.report.warn(code, line, message)

    def _string_map(self, line: int, name: str, value: Any) -> bool:
        if not isinstance(value, dict):
            self._error("E018", line, f"{name} must be an object")
            return False
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                self._error("E018", line, f"{name} has a non-string or empty key")
                return False
            if not isinstance(item, str):
                self._error("E018", line, f"{name}.{key} is not a string")
                return False
        return True

    def _check_id(self, line: int, obj: dict[str, Any], kind: str) -> str | None:
        rid = obj.get("id")
        if not isinstance(rid, str):
            self._error("E004", line, f"{kind}: missing required field 'id'")
            return None
        match = ID_RE.match(rid)
        if not match:
            self._error("E007", line, f"{kind}: malformed id {rid!r}")
            return None
        if match.group(1) != kind[0]:
            self._error(
                "E007", line, f"{kind}: id {rid!r} must start with {kind[0]!r}"
            )
            return None
        return rid

    def _check_tags(self, line: int, obj: dict[str, Any]) -> None:
        if "tags" in obj:
            self._string_map(line, "tags", obj["tags"])
        if "addr" in obj:
            self._string_map(line, "addr", obj["addr"])
        if "poi" in obj:
            self._string_map(line, "poi", obj["poi"])

    # -- header ---------------------------------------------------------
    def _check_header(self, line: int, obj: dict[str, Any]) -> None:
        self.header = obj
        source = obj.get("source")
        if not isinstance(source, dict) or not isinstance(source.get("name"), str):
            self._error("E021", line, "header.source.name (the pinned snapshot) is required")
        licence = obj.get("license")
        if not isinstance(licence, dict):
            self._error("E020", line, "header.license object is required")
            return
        database = licence.get("database")
        if not isinstance(database, str) or "ODbL" not in database:
            self._error("E020", line, "header.license.database must name ODbL")
        if not isinstance(licence.get("attribution"), str) or not licence["attribution"].strip():
            self._error("E020", line, "header.license.attribution is required")

    # -- node -----------------------------------------------------------
    def _node(self, line: int, obj: dict[str, Any]) -> None:
        self.report.nodes += 1
        rid = self._check_id(line, obj, "node")
        if rid is not None:
            if rid in self.node_tiles:
                self._error("E006", line, f"node {rid} appears twice")
            self.node_tiles[rid] = [None, False]

        lat, lon = obj.get("lat"), obj.get("lon")
        usable = True
        for name, value in (("lat", lat), ("lon", lon)):
            if name not in obj:
                self._error("E004", line, f"node: missing required field '{name}'")
                usable = False
            elif isinstance(value, bool) or not isinstance(value, (int, float)):
                self._error("E008", line, f"node: {name} is not a number")
                usable = False
            elif not math.isfinite(float(value)) or not (
                -90.0 <= float(value) <= 90.0 if name == "lat" else -180.0 <= float(value) <= 180.0
            ):
                self._error("E008", line, f"node: {name}={value} outside WGS84")
                usable = False

        computed: str | None = None
        if usable:
            try:
                computed = tile_for(float(lat), float(lon))
            except ValueError as exc:
                self._error("E008", line, f"node: {exc}")
                usable = False

        tile = obj.get("tile")
        if not isinstance(tile, str):
            self._error("E004", line, "node: missing required field 'tile'")
        elif not tile_in_grid(tile):
            self._error("E010", line, f"node: malformed tile id {tile!r}")
        elif computed is not None and tile != computed:
            self._error(
                "E009",
                line,
                f"node: tile {tile} but coordinates fall in {computed}",
            )

        self._check_tags(line, obj)
        addr = obj.get("addr")
        poi = obj.get("poi")
        if isinstance(addr, dict) and addr:
            self.report.addresses += 1
        if isinstance(poi, dict) and poi.get("category"):
            self.report.pois += 1
        if addr or poi or (isinstance(obj.get("tags"), dict) and obj["tags"].get("place")):
            if rid is not None and rid in self.node_tiles:
                self.node_tiles[rid][1] = True

        if rid is not None and rid in self.node_tiles:
            self.node_tiles[rid][0] = computed or (tile if isinstance(tile, str) else None)
        self.report.note_tile(tile if isinstance(tile, str) else None, "nodes")

    # -- way ------------------------------------------------------------
    def _way(self, line: int, obj: dict[str, Any]) -> None:
        self.report.ways += 1
        rid = self._check_id(line, obj, "way")
        if rid is not None and rid in self.way_tiles:
            self._error("E006", line, f"way {rid} appears twice")

        refs = obj.get("nodes")
        node_tiles: list[str] = []
        if not isinstance(refs, list):
            self._error("E004", line, "way: missing required field 'nodes'")
            refs = []
        elif len(refs) < 2:
            self._error("E010", line, f"way: {len(refs)} node(s), at least 2 required")

        for index, ref in enumerate(refs):
            if not isinstance(ref, str) or not NODE_REF_RE.match(ref):
                self._error("E011", line, f"way: node ref {ref!r} is not a node id")
                continue
            if index and ref == refs[index - 1]:
                self._error("E019", line, f"way: node {ref} repeated consecutively")
            entry = self.node_tiles.get(ref)
            if entry is None or entry[0] is None:
                self._error(
                    "E011",
                    line,
                    f"way: node {ref} is not defined earlier in the file",
                )
                continue
            entry[1] = True
            node_tiles.append(str(entry[0]))

        if node_tiles:
            anchor = node_tiles[0]
            tile = obj.get("tile")
            if not isinstance(tile, str):
                self._error("E004", line, "way: missing required field 'tile'")
            elif not tile_in_grid(tile):
                self._error("E010", line, f"way: malformed tile id {tile!r}")
            elif tile != anchor:
                self._error(
                    "E012", line, f"way: tile {tile} is not the first node's tile {anchor}"
                )

            derived = sorted(set(node_tiles))
            given = obj.get("tiles")
            if not isinstance(given, list) or not all(isinstance(t, str) for t in given):
                self._error("E004", line, "way: missing required string list 'tiles'")
            elif given != derived:
                self._error(
                    "E013",
                    line,
                    f"way: tiles {given} does not equal the derived {derived}",
                )

        tags = obj.get("tags")
        self._check_tags(line, obj)
        if not isinstance(tags, dict):
            tags = {}

        highway = tags.get("highway")
        if isinstance(highway, str):
            if highway not in HIGHWAY_VALUES:
                self._warn("W003", line, f"way: unknown highway value {highway!r}")
            if not tags.get("name"):
                self._warn("W001", line, f"way: {highway} way has no name")
        else:
            for key in ("oneway", "maxspeed", "lanes", "ref"):
                if key in tags:
                    self._warn("W006", line, f"way: tag {key!r} without highway")

        if "oneway" in obj:
            oneway = obj["oneway"]
            if oneway not in ONEWAY_VALUES:
                self._error("E014", line, f"way: oneway={oneway!r} (want yes/no/-1)")
            elif not isinstance(highway, str):
                self._error("E014", line, "way: oneway is set but the way has no highway")
            elif oneway == "yes":
                self.report.oneway_ways += 1

        self._way_speed(line, obj, tags)

        access = tags.get("access")
        if access is not None and access not in ACCESS_VALUES:
            self._error("E022", line, f"way: access={access!r} not in the supported set")

        if tags.get("name"):
            self.report.named_ways += 1
        if rid is not None:
            self.way_tiles[rid] = tuple(sorted(set(node_tiles)))
        self.report.note_tile(obj.get("tile") if isinstance(obj.get("tile"), str) else None, "ways")

    def _way_speed(self, line: int, obj: dict[str, Any], tags: dict[str, Any]) -> None:
        kmh = obj.get("maxspeed_kmh")
        cms = obj.get("maxspeed_cms")
        for name, value, limit in (
            ("maxspeed_kmh", kmh, 300),
            ("maxspeed_cms", cms, kmh_to_cms(300)),
        ):
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                self._error("E015", line, f"way: {name} must be an integer")
            elif not 1 <= value <= limit:
                self._error("E015", line, f"way: {name}={value} outside 1..{limit}")
        if (
            isinstance(kmh, int)
            and not isinstance(kmh, bool)
            and isinstance(cms, int)
            and not isinstance(cms, bool)
        ):
            if kmh_to_cms(kmh) != cms:
                self._error(
                    "E015",
                    line,
                    f"way: maxspeed_cms={cms} != {kmh_to_cms(kmh)} for {kmh} km/h",
                )

        raw = tags.get("maxspeed")
        if isinstance(raw, str) and raw.strip().isdigit():
            expected = int(raw.strip())
            if kmh is None:
                self._error(
                    "E015", line, f"way: tags.maxspeed={raw} but maxspeed_kmh is missing"
                )
            elif kmh != expected:
                self._error(
                    "E015", line, f"way: tags.maxspeed={raw} but maxspeed_kmh={kmh}"
                )
        if isinstance(kmh, int) and not isinstance(kmh, bool) and 1 <= kmh <= 300:
            self.report.speed_ways += 1
        elif isinstance(tags.get("highway"), str):
            self._warn("W002", line, "way: highway way has no numeric maxspeed")

    # -- relation -------------------------------------------------------
    def _relation(self, line: int, obj: dict[str, Any]) -> None:
        self.report.relations += 1
        rid = self._check_id(line, obj, "relation")
        if rid is not None:
            if rid in self.relation_ids:
                self._error("E006", line, f"relation {rid} appears twice")
            self.relation_ids.add(rid)

        members = obj.get("members")
        roles: dict[str, int] = {}
        if not isinstance(members, list):
            self._error("E004", line, "relation: missing required field 'members'")
            members = []
        for member in members:
            if not isinstance(member, dict):
                self._error("E016", line, "relation: member is not an object")
                continue
            mtype, ref, role = member.get("type"), member.get("ref"), member.get("role")
            if (
                mtype not in ("node", "way", "relation")
                or not isinstance(ref, str)
                or not isinstance(role, str)
            ):
                self._error("E016", line, f"relation: malformed member {member!r}")
                continue
            roles[role] = roles.get(role, 0) + 1
            if mtype == "node" and ref not in self.node_tiles:
                self._error("E016", line, f"relation: node {ref} does not resolve")
            elif mtype == "way" and ref not in self.way_tiles:
                self._error("E016", line, f"relation: way {ref} does not resolve")
            elif mtype == "relation":
                self._warn("W005", line, f"relation: nested member {ref} is not resolved")

        self._check_tags(line, obj)
        tags = obj.get("tags") if isinstance(obj.get("tags"), dict) else {}
        kind = tags.get("type")
        if kind == "restriction":
            if not tags.get("restriction"):
                self._error("E017", line, "restriction relation has no restriction tag")
            for role in ("from", "to", "via"):
                if not roles.get(role):
                    self._error("E017", line, f"restriction relation has no {role} member")
        elif kind == "boundary":
            if tags.get("boundary") != "administrative":
                self._warn("W005", line, "boundary relation is not administrative")
            if not tags.get("admin_level") or not tags.get("name"):
                self._warn("W005", line, "boundary relation lacks admin_level or name")
        elif kind == "route":
            if not tags.get("route"):
                self._warn("W005", line, "route relation has no route tag")
        elif kind is None:
            self._warn("W005", line, "relation has no tags.type")
        else:
            self._warn("W005", line, f"relation type {kind!r} is outside the IMF subset")

    # -- driver ---------------------------------------------------------
    def feed(self, line: int, obj: Any) -> None:
        if not isinstance(obj, dict):
            self._error("E003", line, "line is not a JSON object")
            return
        rtype = obj.get("type")
        if not self.seen_header:
            self.seen_header = True
            if rtype != "header":
                self._error("E001", line, "the first record must be the IMF header")
                return
        elif rtype == "header":
            self._error("E001", line, "a second header record is not allowed")
            return

        version = obj.get("imf")
        if version != IMF_VERSION:
            self._error(
                "E002", line, f"imf={version!r}; this tool reads version {IMF_VERSION}"
            )
            return

        if rtype == "header":
            self._check_header(line, obj)
        elif rtype == "node":
            self._node(line, obj)
        elif rtype == "way":
            self._way(line, obj)
        elif rtype == "relation":
            self._relation(line, obj)
        else:
            self._error("E005", line, f"unknown record type {rtype!r}")

    def finish(self) -> Report:
        for rid, (_, used) in self.node_tiles.items():
            if not used:
                self._warn(
                    "W004",
                    0,
                    f"node {rid} is not referenced by a way, address or POI",
                )
        return self.report


def parse_lines(text: str, report: Report) -> Iterator[tuple[int, Any]]:
    for lineno, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            yield lineno, json.loads(raw)
        except json.JSONDecodeError as exc:
            report.add("E003", lineno, f"invalid JSON: {exc.msg}")


def validate_text(text: str, path: str = "<text>", *, warnings: bool = True) -> Report:
    report = Report(path=path)
    validator = Validator(path=path, warnings=warnings)
    validator.report = report
    for lineno, obj in parse_lines(text, report):
        validator.feed(lineno, obj)
    return validator.finish()


def read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    if path.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return handle.read()
    return Path(path).read_text(encoding="utf-8")


def write_text(path: str | None, text: str) -> None:
    if path is None or path == "-":
        sys.stdout.write(text)
        return
    if path.endswith(".gz"):
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(text)
        return
    Path(path).write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------
# Tile assignment
# --------------------------------------------------------------------------


NODE_FIELD_ORDER = ("imf", "type", "id", "lat", "lon", "tile", "tags", "addr", "poi", "name")
WAY_FIELD_ORDER = (
    "imf", "type", "id", "nodes", "tile", "tiles", "tags",
    "oneway", "maxspeed_kmh", "maxspeed_cms",
)


def _reorder(record: dict[str, Any], order: tuple[str, ...]) -> dict[str, Any]:
    """Stable field order so a re-run produces the same bytes."""
    out = {key: record[key] for key in order if key in record}
    for key, value in record.items():
        if key not in out:
            out[key] = value
    return out


def assign_tiles(lines: list[Any]) -> tuple[list[Any], list[Issue]]:
    """Return *lines* with node/way ``tile``/``tiles`` recomputed."""
    issues: list[Issue] = []
    node_tiles: dict[str, str] = {}
    out: list[Any] = []
    for lineno, obj in enumerate(lines, 1):
        if not isinstance(obj, dict):
            issues.append(Issue("E003", lineno, "line is not a JSON object"))
            out.append(obj)
            continue
        rtype = obj.get("type")
        if rtype == "node":
            try:
                tile = tile_for(float(obj["lat"]), float(obj["lon"]))
            except (KeyError, TypeError, ValueError) as exc:
                issues.append(Issue("E008", lineno, f"node: {exc}"))
                out.append(obj)
                continue
            obj["tile"] = tile
            if isinstance(obj.get("id"), str):
                node_tiles[obj["id"]] = tile
            out.append(_reorder(obj, NODE_FIELD_ORDER))
        elif rtype == "way":
            refs = obj.get("nodes") if isinstance(obj.get("nodes"), list) else []
            tiles: list[str] = []
            ok = True
            for ref in refs:
                tile = node_tiles.get(ref) if isinstance(ref, str) else None
                if tile is None:
                    issues.append(Issue("E011", lineno, f"way: node {ref!r} does not resolve"))
                    ok = False
                    continue
                tiles.append(tile)
            if ok and tiles:
                obj["tile"] = tiles[0]
                obj["tiles"] = sorted(set(tiles))
            out.append(_reorder(obj, WAY_FIELD_ORDER))
        else:
            out.append(obj)
    return out, issues


# --------------------------------------------------------------------------
# Synthetic sample
# --------------------------------------------------------------------------

SAMPLE_GENERATED = "2026-11-05T00:00:00Z"


def sample_records() -> list[dict[str, Any]]:
    """A small, valid, self-contained IMF file (Wrocław area, invented ids)."""

    def node(rid: str, lat: float, lon: float, **extra: Any) -> dict[str, Any]:
        record: dict[str, Any] = {"imf": IMF_VERSION, "type": "node", "id": rid,
                                  "lat": lat, "lon": lon, "tile": tile_for(lat, lon)}
        record.update(extra)
        return record

    def way(rid: str, refs: list[str], tags: dict[str, str], **extra: Any) -> dict[str, Any]:
        record: dict[str, Any] = {
            "imf": IMF_VERSION,
            "type": "way",
            "id": rid,
            "nodes": refs,
            "tile": _sample_node_tile[refs[0]],
            "tiles": sorted({_sample_node_tile[ref] for ref in refs}),
            "tags": tags,
        }
        record.update(extra)
        return record

    header = {
        "imf": IMF_VERSION,
        "type": "header",
        "generated": SAMPLE_GENERATED,
        "generator": "tools/imf_check.py --sample",
        "source": {
            "name": "dolnoslaskie-latest.osm.pbf",
            "url": "https://download.geofabrik.de/europe/poland/dolnoslaskie-latest.osm.pbf",
            "md5": "0a78af165163f38a1e22737888a9fd57",
            "timestamp": "2026-11-03T21:24:23Z",
            "sequence": 4024,
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

    nodes = [
        # A8 motorway, west of Wrocław.
        node("n900000001", 51.1090000, 16.8800000),
        node("n900000002", 51.1120000, 16.9200000),
        node("n900000003", 51.1150000, 16.9600000),
        node("n900000004", 51.1180000, 17.0000000),
        # ul. Legnicka: two ways sharing the via node.
        node("n900000020", 51.1100000, 16.9000000,
             addr={"street": "ul. Legnicka", "housenumber": "7",
                   "postcode": "54-001", "city": "Wrocław"}),
        node("n900000021", 51.1115000, 16.9100000),
        node("n900000022", 51.1130000, 16.9200000),
        # POI and place nodes.
        node("n900000030", 51.1110000, 16.9050000,
             poi={"category": "fuel", "name": "Orlen"},
             addr={"street": "ul. Legnicka", "housenumber": "9"}),
        node("n900000040", 51.1100000, 17.0300000,
             tags={"place": "city"}, name="Wrocław"),
        # Boundary ring (ways carry no highway tag).
        node("n900000050", 50.9000000, 16.8000000),
        node("n900000051", 50.9000000, 17.2000000),
        node("n900000052", 51.3000000, 17.2000000),
        node("n900000053", 51.3000000, 16.8000000),
        # Road that crosses the 20.00 E cell boundary (B48R058R -> B48R050R).
        node("n900000060", 51.1000000, 19.9990000),
        node("n900000061", 51.1000000, 20.0010000),
    ]
    global _sample_node_tile
    _sample_node_tile = {n["id"]: n["tile"] for n in nodes}

    ways = [
        way(
            "w900000001",
            ["n900000001", "n900000002", "n900000003", "n900000004"],
            {"highway": "motorway", "ref": "A8", "name": "Autostrada A8",
             "oneway": "yes", "maxspeed": "140", "lanes": "2",
             "surface": "asphalt"},
            oneway="yes", maxspeed_kmh=140, maxspeed_cms=kmh_to_cms(140),
        ),
        way(
            "w900000005",
            ["n900000020", "n900000021"],
            {"highway": "secondary", "name": "ul. Legnicka", "maxspeed": "50"},
            oneway="no", maxspeed_kmh=50, maxspeed_cms=kmh_to_cms(50),
        ),
        way(
            "w900000006",
            ["n900000021", "n900000022"],
            {"highway": "secondary", "name": "ul. Legnicka", "maxspeed": "50"},
            oneway="no", maxspeed_kmh=50, maxspeed_cms=kmh_to_cms(50),
        ),
        way(
            "w900000030",
            ["n900000050", "n900000051", "n900000052", "n900000053", "n900000050"],
            {"boundary": "administrative", "admin_level": "4"},
        ),
        way(
            "w900000010",
            ["n900000060", "n900000061"],
            {"highway": "primary", "name": "ul. Graniczna", "maxspeed": "70"},
            maxspeed_kmh=70, maxspeed_cms=kmh_to_cms(70),
        ),
    ]

    relations = [
        {
            "imf": IMF_VERSION,
            "type": "relation",
            "id": "r900000100",
            "members": [
                {"type": "way", "ref": "w900000005", "role": "from"},
                {"type": "node", "ref": "n900000021", "role": "via"},
                {"type": "way", "ref": "w900000006", "role": "to"},
            ],
            "tags": {"type": "restriction", "restriction": "no_left_turn"},
        },
        {
            "imf": IMF_VERSION,
            "type": "relation",
            "id": "r900000101",
            "members": [{"type": "way", "ref": "w900000030", "role": "outer"}],
            "tags": {"type": "boundary", "boundary": "administrative",
                     "admin_level": "4", "name": "Dolnośląskie"},
        },
    ]
    return [
        header,
        *(_reorder(record, NODE_FIELD_ORDER) for record in nodes),
        *(_reorder(record, WAY_FIELD_ORDER) for record in ways),
        *relations,
    ]


_sample_node_tile: dict[str, str] = {}


def sample_text() -> str:
    records = sample_records()
    return "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def print_report(report: Report, *, warnings: bool = True, file: Any = None) -> None:
    stream = file or sys.stdout
    print(f"file        {report.path}", file=stream)
    print(
        f"records     nodes={report.nodes} ways={report.ways} "
        f"relations={report.relations}",
        file=stream,
    )
    print(
        f"attributes  named={report.named_ways} "
        f"maxspeed={report.speed_ways} oneway={report.oneway_ways} "
        f"addresses={report.addresses} pois={report.pois}",
        file=stream,
    )
    if report.tiles:
        inventory = " ".join(
            f"{tile}({counts['nodes']}n/{counts['ways']}w)"
            for tile, counts in sorted(report.tiles.items())
        )
        print(f"tiles       {inventory}", file=stream)
    if warnings and report.warnings:
        print(f"warnings    {len(report.warnings)}", file=stream)
        for issue in report.warnings[:50]:
            where = f"line {issue.line}" if issue.line else "end"
            print(f"  {issue.code} {where:>8}  {issue.message}", file=stream)
        if len(report.warnings) > 50:
            print(f"  ... {len(report.warnings) - 50} more", file=stream)
    print(f"errors      {len(report.errors)}", file=stream)
    for issue in report.errors[:50]:
        print(f"  {issue.code} line {issue.line:>5}  {issue.message}", file=stream)
    if len(report.errors) > 50:
        print(f"  ... {len(report.errors) - 50} more", file=stream)
    print("result      " + ("PASS" if report.ok else "FAIL"), file=stream)


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------


def _split(text: str) -> list[Any]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _join(records: list[Any]) -> str:
    return "".join(
        json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in records
    )


def _find(records: list[Any], rid: str) -> dict[str, Any]:
    for record in records:
        if isinstance(record, dict) and record.get("id") == rid:
            return record
    raise KeyError(rid)


def selftest() -> int:
    """Synthetic valid file plus exactly one failure per rule."""
    print("imf_check selftest")
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        print(f"  {name:<28} {'OK' if condition else 'FAIL'} {detail}".rstrip())
        if not condition:
            failures.append(name)

    # Grid: the tool's inverse must agree with tools/mesh_grid.py.
    expected_tiles = {
        "B48R058R": (51.11, 17.03),
        "B48R050R": (51.10, 20.001),
        "B28R070R": (28.5, -5.0),
        "B58R070R": (60.0, -6.0),
        "B68R058R": (70.0, 14.0),
    }
    grid_ok = True
    detail = ""
    for tile, (lat, lon) in expected_tiles.items():
        got = tile_for(lat, lon)
        lat_min, lat_max, lon_min, lon_max = tile_box(tile)
        inside = lat_min <= lat < lat_max and lon_min <= lon < lon_max
        if got != tile or not inside:
            grid_ok = False
            detail += f" {tile}->{got}"
    try:
        import mesh_grid  # sibling tool, same formula

        for tile in ("B28R070R", "B30R048R", "B48R058R", "B58R070R", "B68R058R"):
            if mesh_grid.tile_box(tile + ".DAT") != tile_box(tile):
                grid_ok = False
                detail += f" mesh_grid:{tile}"
    except ImportError:
        pass
    check("grid inverse", grid_ok, detail.strip())

    speed_ok = all(cms_to_kmh(kmh_to_cms(v)) == v for v in range(1, 301))
    check("speed round-trip", speed_ok, "1..300 km/h")

    text = sample_text()
    report = validate_text(text, "sample")
    check(
        "valid sample",
        report.ok,
        f"nodes={report.nodes} ways={report.ways} relations={report.relations}",
    )
    check("sample warnings", not report.warnings, str([w.code for w in report.warnings]))

    # One case per rule. E003 is a raw-line case, the rest are record edits.
    def mutate(fn) -> str:
        records = _split(text)
        fn(records)
        return _join(records)

    cases: dict[str, Any] = {
        "E001": lambda r: r.pop(0),
        "E002": lambda r: r[0].__setitem__("imf", 2),
        "E003": lambda r: None,  # handled separately
        "E004": lambda r: _find(r, "n900000001").pop("lat"),
        "E005": lambda r: _find(r, "n900000001").__setitem__("type", "nodex"),
        "E006": lambda r: _find(r, "n900000002").__setitem__("id", "n900000001"),
        "E007": lambda r: _find(r, "n900000001").__setitem__("id", "w900000001"),
        "E008": lambda r: _find(r, "n900000001").__setitem__("lat", 95.0),
        "E009": lambda r: _find(r, "n900000001").__setitem__("tile", "B48R050R"),
        "E010": lambda r: _find(r, "w900000005").__setitem__("nodes", ["n900000020"]),
        "E011": lambda r: _find(r, "w900000005")["nodes"].__setitem__(1, "n999999999"),
        "E012": lambda r: _find(r, "w900000005").__setitem__("tile", "B48R050R"),
        "E013": lambda r: _find(r, "w900000010").__setitem__("tiles", ["B48R058R"]),
        "E014": lambda r: _find(r, "w900000005").__setitem__("oneway", "true"),
        "E015": lambda r: _find(r, "w900000005").__setitem__("maxspeed_cms", 1000),
        "E016": lambda r: _find(r, "r900000100")["members"][0].__setitem__(
            "ref", "w999999999"
        ),
        "E017": lambda r: _find(r, "r900000100")["tags"].pop("restriction"),
        "E018": lambda r: _find(r, "w900000005")["tags"].__setitem__("name", 5),
        "E019": lambda r: _find(r, "w900000005")["nodes"].insert(0, "n900000020"),
        "E020": lambda r: r[0]["license"].pop("attribution"),
        "E021": lambda r: r[0]["source"].pop("name"),
        "E022": lambda r: _find(r, "w900000005")["tags"].__setitem__(
            "access", "sometimes"
        ),
    }

    missing = sorted(set(RULES) - set(cases))
    check("every rule has a case", not missing, ",".join(missing))

    caught: list[str] = []
    for code in sorted(cases):
        if code == "E003":
            bad = text.replace('"type":"node"', '"type":node', 1)
        else:
            bad = mutate(cases[code])
        errors = validate_text(bad, "case").errors
        if any(error.code == code for error in errors):
            caught.append(code)
        else:
            print(f"  {code} not triggered: {[e.code for e in errors]}")
    check("failure cases", len(caught) == len(cases), f"{len(caught)}/{len(cases)}")

    # Warnings must not fail validation.
    warn_text = mutate(lambda r: _find(r, "w900000005")["tags"].pop("name"))
    warn_report = validate_text(warn_text, "warn")
    check(
        "warnings are non-fatal",
        warn_report.ok and any(w.code == "W001" for w in warn_report.warnings),
    )

    # --assign-tiles restores a file whose tile fields were dropped.
    def strip(records: list[Any]) -> None:
        for record in records:
            record.pop("tile", None)
            record.pop("tiles", None)

    stripped = _split(text)
    strip(stripped)
    assigned, issues = assign_tiles(stripped)
    restored = _split(_join(assigned))
    reference = _split(text)
    check(
        "--assign-tiles round-trip",
        not issues and restored == reference,
        f"issues={len(issues)}",
    )

    print(f"selftest: {'OK' if not failures else 'FAILED'}")
    return 0 if not failures else 1


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Exit codes: 0 ok, 1 validation errors, 2 usage or I/O error.",
    )
    parser.add_argument(
        "file", nargs="?", help="IMF JSON Lines file to validate ('-' = stdin)"
    )
    parser.add_argument(
        "--assign-tiles",
        action="store_true",
        help="recompute node/way tile and tiles fields",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="write a synthetic valid IMF file (use -o; default stdout)",
    )
    parser.add_argument(
        "-o",
        "--out",
        help="output path for --sample / --assign-tiles (default: stdout, or in place)",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument(
        "--no-warnings", action="store_true", help="do not compute or print warnings"
    )
    parser.add_argument("--selftest", action="store_true", help="run synthetic tests")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    if args.sample:
        if args.file:
            parser.error("--sample writes with -o/--out; drop the positional file")
        text = sample_text()
        write_text(args.out, text)
        report = validate_text(text, args.out or "<stdout>", warnings=not args.no_warnings)
        # Without -o the JSONL goes to stdout, so the report must not mix in.
        stream = sys.stderr if args.out is None else sys.stdout
        if args.json:
            print(json.dumps(report.to_dict(), indent=2), file=stream)
        else:
            print_report(report, warnings=not args.no_warnings, file=stream)
        return 0 if report.ok else 1

    if not args.file:
        parser.error("a file is required unless --sample or --selftest is used")

    try:
        text = read_text(args.file)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: {args.file}: {exc}", file=sys.stderr)
        return 2

    if args.assign_tiles:
        records = _split(text)
        assigned, issues = assign_tiles(records)
        output = _join(assigned)
        if issues:
            for issue in issues:
                print(f"{issue.code} line {issue.line}  {issue.message}", file=sys.stderr)
            return 1
        if args.out:
            write_text(args.out, output)
            target = args.out
            to_stdout = False
        elif args.file == "-":
            sys.stdout.write(output)
            target = "<stdout>"
            to_stdout = True
        else:
            Path(args.file).write_text(output, encoding="utf-8")
            target = args.file
            to_stdout = False
        report = validate_text(output, target, warnings=not args.no_warnings)
        stream = sys.stderr if to_stdout else sys.stdout
        if args.json:
            print(json.dumps(report.to_dict(), indent=2), file=stream)
        else:
            print_report(report, warnings=not args.no_warnings, file=stream)
        return 0 if report.ok else 1

    report = validate_text(text, args.file, warnings=not args.no_warnings)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_report(report, warnings=not args.no_warnings)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
