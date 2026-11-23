#!/usr/bin/env python3
"""Deterministic synthetic OSM town for tests without network (M5.76).

The Claude sandbox cannot fetch OSM data (rule 12), so OSM-consuming compiler
tasks would otherwise stall or test on three hand-made ways.  This generator
produces one realistic, fully deterministic town as IMF v1 JSON Lines — the
exact record shape ``tools/tilewriter.py`` (``read_jsonl``) and
``tools/osm_ingest.py`` already read — from a seed and a ``BxxRyyR`` cell.

What the town contains, all clipped to one level-1 directory inside the cell
so ``tools/one_tile_pipeline.py --parcel`` accepts it:

* a street grid (residential/tertiary) with Polish names and diacritics
  (``ł ó ź Ż ś ą ę``), one-way pairs;
* a ring road (secondary, two-way) and a motorway across the town (one-way
  carriageways, ``maxspeed=120``) — the motorway is generated even though the
  card writer is roads-only, so compiler tasks have ``motorway`` input;
* turn restrictions (``no_left_turn`` / ``no_u_turn``) on the grid;
* 50 POIs over the ``POI_CATEGORY_KEYS`` categories, plus house-number
  addresses on two named streets;
* a river (``waterway=river``) and a lake (``natural=water``) — kept in the
  IMF even though the roads-only writer drops them (see ``--summary``).

Determinism is the whole contract: the output depends only on ``--seed`` and
``--tile`` (and the fixed grid/algorithm), the record order is fixed, and the
header carries no timestamp, so ``--seed 1`` is byte-identical across runs and
machines.  ``--selftest`` pins the SHA-256 of ``--seed 1`` and proves the
falsifier (same seed twice ⇒ identical; two seeds ⇒ different).

Usage::

    python3 tools/osm_synth.py --seed 1 --tile B50R058R -o town.jsonl
    python3 tools/osm_synth.py --seed 1 --tile B50R058R -o town.jsonl --summary
    python3 tools/osm_synth.py --summary            # counts to stdout, no file
    python3 tools/osm_synth.py --selftest

``-o -`` writes the JSONL to stdout and the summary (if any) to stderr.
Exit codes: ``0`` ok, ``2`` usage/IO, ``1`` an input that cannot be honoured
(``--tile`` out of the shipped grid, a box with no room for the town).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import imf_check  # noqa: E402  (sibling tool: tile box / tile_for / tile_in_grid)
import tilewriter  # noqa: E402  (sibling tool: parcel_of = the writer's own grid)

TOOL_VERSION = "1.0"
IMF_VERSION = 1

#: The town is laid out as a unit square scaled into this level-1 directory box,
#: in degrees.  Lengths are computed per axis, so a "grid line" is one column or
#: row of the square, not a number of degrees.
TOWN_LON_SPAN = 0.100
TOWN_LAT_SPAN = 0.080
#: Fraction of the span kept free around the town, so no node lands on the
#: directory border (a border node belongs to the next directory).
TOWN_MARGIN = 0.10
GRID = 5
POI_TARGET = 50

#: Polish names with the diacritics the task asks for (ł ó ź Ż ś ą ę).
STREET_NS = ["Lipowa", "Świerkowa", "Akacjowa", "Brzozowa", "Głęboka"]
STREET_EW = ["Wrocławska", "Śląska", "Żółkiewskiego", "Źródlana", "Wiejska"]
RING_NAME = "Obwodnica"
MOTORWAY_REF = "A8"
MOTORWAY_NAME = "Autostrada A8"
RIVER_NAME = "Bystrzyca"
LAKE_NAME = "Jezioro Śląskie"
HOUSE_STREETS = (("Wrocławska", "ew"), ("Świerkowa", "ns"))

#: (amenity/shop key, value, display name) — first entry of each is the
#: category key that ``osm_ingest`` maps to ``poi.category``.
POI_CLASSES = [
    ("amenity", "fuel", "Stacja paliw"),
    ("amenity", "restaurant", "Restauracja Pod Żabką"),
    ("amenity", "cafe", "Kawiarnia Źródło"),
    ("amenity", "pharmacy", "Apteka Śląska"),
    ("amenity", "bank", "Bank Wrocławski"),
    ("shop", "supermarket", "Supermarket Klonowa"),
    ("shop", "bakery", "Piekarnia Świąteczna"),
    ("shop", "butcher", "Rzeźnik Wiejski"),
    ("shop", "clothes", "Sklep Odzieżowy"),
    ("tourism", "hotel", "Hotel Bystrzyca"),
    ("tourism", "guest_house", "Zajazd Źródlany"),
    ("leisure", "park", "Park Świerkowy"),
    ("leisure", "playground", "Plac Zabaw"),
    ("office", "estate_agent", "Biuro Nieruchomości"),
    ("healthcare", "clinic", "Przychodnia Żółkiewskiego"),
]

RESTRICTIONS = ("no_left_turn", "no_u_turn")


class SynthError(Exception):
    """An input that cannot be honoured (always a usage or placement error)."""


# --------------------------------------------------------------------------
# deterministic randomness and geometry
# --------------------------------------------------------------------------


class Rand:
    """Tiny, explicit, platform-stable LCG (no ``random`` module surprises)."""

    A = 1103515245
    C = 12345
    M = 1 << 31

    def __init__(self, seed: int) -> None:
        self.state = seed & (self.M - 1)

    def next(self) -> int:
        self.state = (self.A * self.state + self.C) % self.M
        return self.state

    def rand(self) -> float:
        return self.next() / self.M

    def randint(self, lo: int, hi: int) -> int:
        """Inclusive ``[lo, hi]``."""
        return lo + self.next() % (hi - lo + 1)

    def choice(self, seq):
        return seq[self.next() % len(seq)]

    def shuffled(self, seq):
        items = list(seq)
        for i in range(len(items) - 1, 0, -1):
            j = self.next() % (i + 1)
            items[i], items[j] = items[j], items[i]
        return items


def _town_box(tile: str) -> dict[str, float]:
    """The directory box of ``tile``'s south-west cell, shrunk by the margin.

    Uses ``imf_check.tile_box`` (the validator's own cell formula) and
    ``tilewriter.parcel_of`` (the writer's own parcel grid), so the generated
    files land in the directory the pipeline will splice.
    """
    lat_min, lat_max, lon_min, lon_max = imf_check.tile_box(tile)
    # Anchor on the cell's *centre* directory, so the town lands in one
    # spliceable interior directory (the SW-corner directory can be a
    # preserve-only one, which the pipeline refuses).
    y0, x0, _row, _col = tilewriter.parcel_of(
        (lon_min + lon_max) / 2.0, (lat_min + lat_max) / 2.0, 1)
    lon0 = _mesh_to_lon(x0)
    lat0 = _mesh_to_lat(y0)
    lon1 = _mesh_to_lon(x0 + 1)
    lat1 = _mesh_to_lat(y0 + 1)
    pad_lon = TOWN_LON_SPAN * TOWN_MARGIN
    pad_lat = TOWN_LAT_SPAN * TOWN_MARGIN
    lo_lon = max(lon0, lon0 + (lon1 - lon0 - TOWN_LON_SPAN) / 2.0) + pad_lon
    lo_lat = max(lat0, lat0 + (lat1 - lat0 - TOWN_LAT_SPAN) / 2.0) + pad_lat
    box = {
        "lon_min": lo_lon,
        "lat_min": lo_lat,
        "lon_max": lo_lon + TOWN_LON_SPAN - 2 * pad_lon,
        "lat_max": lo_lat + TOWN_LAT_SPAN - 2 * pad_lat,
    }
    if box["lon_max"] <= box["lon_min"] or box["lat_max"] <= box["lat_min"]:
        raise SynthError("town does not fit the %s directory box" % tile)
    return box


def _mesh_to_lon(mesh: int) -> float:
    import clarion_bg  # noqa: E402  (sibling, inside tools/ze0-viewer/tools_ze0)
    return clarion_bg.mesh_to_lon(mesh)


def _mesh_to_lat(mesh: int) -> float:
    import clarion_bg  # noqa: E402

    return clarion_bg.mesh_to_lat(mesh)


class Layout:
    """The unit-square town mapped into the box; all coordinates are degrees."""

    def __init__(self, box: dict[str, float]) -> None:
        self.box = box

    def lon(self, f: float) -> float:
        return self.box["lon_min"] + f * (self.box["lon_max"] - self.box["lon_min"])

    def lat(self, f: float) -> float:
        return self.box["lat_min"] + f * (self.box["lat_max"] - self.box["lat_min"])

    def point(self, fx: float, fy: float) -> tuple[float, float]:
        return self.lon(fx), self.lat(fy)

    def jitter(self, pool: float) -> float:
        return pool * (1.0 / 12.0)


# --------------------------------------------------------------------------
# records
# --------------------------------------------------------------------------


#: The node tag keys that make ``poi.category`` (first present wins), and the
#: ``addr:*`` -> ``addr`` field map — the same rules ``tools/osm_ingest.py``
#: applies, so a node this generator tags as a POI is a POI to the validator.
POI_CATEGORY_KEYS = ("amenity", "shop", "tourism", "leisure", "office", "healthcare")
ADDR_FIELDS = (("addr:street", "street"), ("addr:housenumber", "housenumber"),
               ("addr:postcode", "postcode"), ("addr:city", "city"),
               ("addr:country", "country"))


def _feature_objects(tags: dict[str, str]):
    """``(addr, poi, name)`` for a node's tags, matching the IMF node shape."""
    addr = {field: tags[key] for key, field in ADDR_FIELDS if tags.get(key)}
    poi = None
    for key in POI_CATEGORY_KEYS:
        if tags.get(key):
            poi = {"category": "%s=%s" % (key, tags[key])}
            for extra in ("name", "brand", "operator"):
                if tags.get(extra):
                    poi[extra] = tags[extra]
            break
    return (addr or None), poi, tags.get("name")


class Builder:
    """Accumulates nodes, ways and relations and renders IMF v1 JSON Lines."""

    def __init__(self, seed: int, tile: str) -> None:
        self.seed = seed
        self.tile = tile
        self.nodes: list[dict[str, Any]] = []
        self._by_id: dict[str, dict[str, Any]] = {}
        self.ways: list[dict[str, Any]] = []
        self.relations: list[dict[str, Any]] = []
        self._next_node = 1
        self._next_way = 1
        self._next_rel = 1

    def add_node(self, lon: float, lat: float,
                 tags: dict[str, str] | None = None) -> str:
        tile = imf_check.tile_for(lat, lon)
        node_id = "n%d" % self._next_node
        self._next_node += 1
        record: dict[str, Any] = {
            "imf": IMF_VERSION,
            "type": "node",
            "id": node_id,
            "lat": round(lat, 7),
            "lon": round(lon, 7),
            "tile": tile,
        }
        if tags:
            record["tags"] = dict(tags)
            addr, poi, name = _feature_objects(tags)
            if addr:
                record["addr"] = addr
            if poi:
                record["poi"] = poi
            if name:
                record["name"] = name
        self.nodes.append(record)
        self._by_id[node_id] = record
        return node_id

    def add_way(self, node_ids: list[str], tags: dict[str, str],
                oneway: str | None = None,
                maxspeed_kmh: int | None = None) -> str:
        way_id = "w%d" % self._next_way
        self._next_way += 1
        tiles = []
        for node_id in node_ids:
            tile = self._by_id[node_id]["tile"]
            if tile not in tiles:
                tiles.append(tile)
        tiles.sort()
        record: dict[str, Any] = {
            "imf": IMF_VERSION,
            "type": "way",
            "id": way_id,
            "nodes": list(node_ids),
            "tile": tiles[0] if tiles else self.tile,
            "tiles": tiles,
            "tags": dict(tags),
        }
        if oneway is not None:
            record["oneway"] = oneway
        if maxspeed_kmh is not None:
            record["maxspeed_kmh"] = maxspeed_kmh
            record["maxspeed_cms"] = imf_check.kmh_to_cms(maxspeed_kmh)
        self.ways.append(record)
        return way_id

    def add_relation(self, members: list[dict[str, str]],
                     tags: dict[str, str]) -> str:
        rel_id = "r%d" % self._next_rel
        self._next_rel += 1
        self.relations.append({
            "imf": IMF_VERSION,
            "type": "relation",
            "id": rel_id,
            "members": members,
            "tags": dict(tags),
        })
        return rel_id

    def records(self) -> list[dict[str, Any]]:
        return [self._header()] + self.nodes + self.ways + self.relations

    def _header(self) -> dict[str, Any]:
        return {
            "imf": IMF_VERSION,
            "type": "header",
            "generator": "tools/osm_synth.py %s --seed %d --tile %s"
                         % (TOOL_VERSION, self.seed, self.tile),
            "source": {"name": "synthetic-town-seed-%d" % self.seed},
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


def render(records: list[dict[str, Any]]) -> str:
    """Canonical JSONL: fixed separators, no sort (field order is the schema)."""
    return "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":"),
                   allow_nan=False) + "\n"
        for record in records
    )


def render_osm(records: list[dict[str, Any]]) -> str:
    """The same town as OSM XML 0.6, the form ``one_tile_pipeline --osm`` ingests.

    IMF is the primary output (``tilewriter``'s input); this is the second view
    so a compiler task can also run the ``osm_ingest -> mesh_split ->
    tilewriter`` pipeline, which starts from OSM XML/PBF, on the same town.
    """
    from xml.sax.saxutils import quoteattr

    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<osm version="0.6" generator="tools/osm_synth.py %s">' % TOOL_VERSION,
    ]
    for record in records:
        if record["type"] == "node":
            line = ' <node id="%s" lat="%s" lon="%s"' % (
                record["id"][1:], repr(record["lat"]), repr(record["lon"]))
            tags = record.get("tags") or {}
            if tags:
                line += ">"
                out.append(line)
                for key in sorted(tags):
                    out.append("  <tag k=%s v=%s/>"
                               % (quoteattr(key), quoteattr(tags[key])))
                out.append(" </node>")
            else:
                out.append(line + "/>")
        elif record["type"] == "way":
            out.append(' <way id="%s">' % record["id"][1:])
            for ref in record["nodes"]:
                out.append('  <nd ref="%s"/>' % ref[1:])
            for key in sorted(record.get("tags") or {}):
                out.append("  <tag k=%s v=%s/>"
                           % (quoteattr(key), quoteattr(record["tags"][key])))
            out.append(" </way>")
        elif record["type"] == "relation":
            out.append(' <relation id="%s">' % record["id"][1:])
            for member in record["members"]:
                out.append('  <member type="%s" ref="%s" role=%s/>' % (
                    member["type"], member["ref"][1:], quoteattr(member["role"])))
            for key in sorted(record.get("tags") or {}):
                out.append("  <tag k=%s v=%s/>"
                           % (quoteattr(key), quoteattr(record["tags"][key])))
            out.append(" </relation>")
    out.append("</osm>")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# the town
# --------------------------------------------------------------------------


def generate(seed: int, tile: str) -> tuple[str, dict[str, Any]]:
    """Return ``(jsonl_text, summary)`` for one seed/tile pair."""
    if not imf_check.tile_in_grid(tile):
        raise SynthError("--tile %r is not a BxxRyyR cell of the shipped grid" % tile)
    rng = Rand(seed)
    box = _town_box(tile)
    layout = Layout(box)
    b = Builder(seed, tile)

    # Grid nodes: GRID x GRID intersections, each jittered a little (inside the
    # margin, so jitter can never reach the directory border).
    grid: list[list[str]] = []
    for j in range(GRID):
        row = []
        for i in range(GRID):
            fx = i / (GRID - 1)
            fy = j / (GRID - 1)
            d = layout.jitter(1.0 / GRID)
            lon, lat = layout.point(fx + rng.rand() * d - d / 2.0,
                                    fy + rng.rand() * d - d / 2.0)
            row.append(b.add_node(lon, lat))
        grid.append(row)

    # N-S and E-W grid streets.  One E-W street and one N-S street are the
    # one-way pair (opposite directions); the rest are two-way.
    oneway_ew_row = rng.randint(1, GRID - 2)
    oneway_ns_col = rng.randint(1, GRID - 2)
    streets: list[dict[str, Any]] = []
    for i in range(GRID):
        name = STREET_NS[i]
        for j in range(GRID - 1):
            oneway = "-1" if i == oneway_ns_col else None
            kw = {"highway": "residential", "name": name, "maxspeed": "30"}
            if oneway is not None:
                kw["oneway"] = oneway
            b.add_way([grid[j][i], grid[j + 1][i]], kw, oneway=oneway,
                      maxspeed_kmh=30)
        streets.append({"name": name, "axis": "ns", "col": i})
    for j in range(GRID):
        name = STREET_EW[j]
        for i in range(GRID - 1):
            oneway = "yes" if j == oneway_ew_row else None
            kw = {"highway": "tertiary", "name": name, "maxspeed": "40"}
            if oneway is not None:
                kw["oneway"] = oneway
            b.add_way([grid[j][i], grid[j][i + 1]], kw, oneway=oneway,
                      maxspeed_kmh=40)
        streets.append({"name": name, "axis": "ew", "row": j})

    # Ring road: a closed eight-node loop around the grid, secondary, two-way.
    ring_nodes = []
    for k in range(8):
        angle = 2.0 * math.pi * k / 8.0
        fx = 0.5 + 0.485 * math.cos(angle) * (1.0 + 0.02 * rng.rand())
        fy = 0.5 + 0.485 * math.sin(angle) * (1.0 + 0.02 * rng.rand())
        lon, lat = layout.point(fx, fy)
        ring_nodes.append(b.add_node(lon, lat))
    for k in range(8):
        b.add_way([ring_nodes[k], ring_nodes[(k + 1) % 8]],
                  {"highway": "secondary", "name": RING_NAME, "maxspeed": "50"},
                  maxspeed_kmh=50)

    # Motorway across the town: two one-way carriageways, 120 km/h.
    mw = []
    for lane, dy in (("east", -0.06), ("west", 0.06)):
        pts = []
        for k in range(4):
            fx = -0.02 + k * 0.36
            fy = 0.5 + dy + 0.02 * rng.rand()
            lon, lat = layout.point(fx, fy)
            pts.append(b.add_node(lon, lat))
        for k in range(3):
            nodes = [pts[k], pts[k + 1]]
            if lane == "west":
                nodes.reverse()
            b.add_way(nodes,
                      {"highway": "motorway", "ref": MOTORWAY_REF,
                       "name": MOTORWAY_NAME, "maxspeed": "120",
                       "oneway": "yes"},
                      oneway="yes", maxspeed_kmh=120)
        mw.append(pts)

    # Turn restrictions at two intersections: from one grid street to another
    # through a shared grid node.
    for k, restriction in enumerate(RESTRICTIONS):
        j = 1 + k
        i = GRID - 2
        via = grid[j][i]
        from_way = next(w for w in b.ways
                        if w["nodes"][-1] == via
                        and w["tags"].get("highway") == "tertiary")
        to_way = next(w for w in b.ways
                      if w["nodes"][0] == via
                      and w["tags"].get("highway") == "residential")
        b.add_relation(
            [{"type": "way", "ref": from_way["id"], "role": "from"},
             {"type": "node", "ref": via, "role": "via"},
             {"type": "way", "ref": to_way["id"], "role": "to"}],
            {"type": "restriction", "restriction": restriction})

    # Addresses on two named streets (house numbers along an E-W and an N-S
    # street); each address node is its own node with addr:* tags.
    for street, axis in HOUSE_STREETS:
        if axis == "ew":
            j = STREET_EW.index(street)
            anchors = [(grid[j][i], grid[j][i + 1]) for i in range(GRID - 1)]
        else:
            i = STREET_NS.index(street)
            anchors = [(grid[j][i], grid[j + 1][i]) for j in range(GRID - 1)]
        number = 1
        for a, c in anchors:
            for t in (0.25, 0.75):
                lon_a, lat_a = _node_xy(b, a)
                lon_c, lat_c = _node_xy(b, c)
                lon = lon_a + (lon_c - lon_a) * t
                lat = lat_a + (lat_c - lat_a) * t
                b.add_node(lon, lat, {
                    "addr:street": street,
                    "addr:housenumber": str(number),
                    "addr:city": "Wrocław",
                })
                number += 2

    # 50 POIs scattered over the box, alternating category so every one of the
    # six POI keys is used; each is at an intersection offset so POIs do not
    # coincide with grid vertices.
    poi_counts: list[int] = []
    for n in range(POI_TARGET):
        key, value, name = POI_CLASSES[n % len(POI_CLASSES)]
        fx = 0.03 + (n * 0.137 + 0.011 * rng.rand()) % 0.94
        fy = 0.03 + (n * 0.219 + 0.023 * rng.rand()) % 0.94
        lon, lat = layout.point(fx, fy)
        b.add_node(lon, lat, {key: value, "name": name})
        poi_counts.append(n % len(POI_CLASSES))

    # A river across the box and a lake (the roads-only writer drops these; they
    # are kept in the IMF so compile/ingest tasks see water).
    river = []
    for k in range(8):
        fx = k / 7.0
        fy = 0.15 + 0.7 * fx + 0.04 * math.sin(4.0 * fx + seed)
        lon, lat = layout.point(fx, fy)
        river.append(b.add_node(lon, lat))
    b.add_way(river,
              {"waterway": "river", "name": RIVER_NAME, "boat": "yes"})
    lake = []
    for k in range(10):
        angle = 2.0 * math.pi * k / 10.0
        lon, lat = layout.point(0.72 + 0.06 * math.cos(angle),
                                0.30 + 0.05 * math.sin(angle))
        lake.append(b.add_node(lon, lat))
    b.add_way(lake + [lake[0]],
              {"natural": "water", "water": "lake", "name": LAKE_NAME})

    records = b.records()
    text = render(records)
    summary = _summary(text, seed, tile, box, poi_counts)
    y0, x0, _r, _c = tilewriter.parcel_of(
        (box["lon_min"] + box["lon_max"]) / 2.0,
        (box["lat_min"] + box["lat_max"]) / 2.0, 1)
    summary["directory"] = [y0, x0]
    summary["osm_xml_sha256"] = hashlib.sha256(
        render_osm(records).encode("utf-8")).hexdigest()
    return text, summary


def _node_xy(b: Builder, node_id: str) -> tuple[float, float]:
    node = b._by_id[node_id]
    return node["lon"], node["lat"]


def _summary(text: str, seed: int, tile: str, box: dict[str, float],
             poi_counts: list[int]) -> dict[str, Any]:
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    nodes = [r for r in records if r["type"] == "node"]
    ways = [r for r in records if r["type"] == "way"]
    relations = [r for r in records if r["type"] == "relation"]
    highways = Counter(w["tags"]["highway"] for w in ways
                       if "highway" in w["tags"])
    category_keys = sorted({r["poi"]["category"].split("=", 1)[0]
                            for r in nodes if "poi" in r})
    named = sum(1 for w in ways if w["tags"].get("name"))
    oneway = sum(1 for w in ways if w.get("oneway") in ("yes", "-1"))
    addresses = sum(1 for r in nodes if "addr" in r)
    pois = sum(1 for r in nodes if "poi" in r)
    water = [w["tags"]["waterway"] if "waterway" in w["tags"] else "water"
             for w in ways if "waterway" in w["tags"] or "natural" in w["tags"]]
    encoded = text.encode("utf-8")
    return {
        "seed": seed,
        "tile": tile,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "bytes": len(encoded),
        "box": [round(box[k], 7) for k in ("lon_min", "lat_min",
                                           "lon_max", "lat_max")],
        "nodes": len(nodes),
        "ways": len(ways),
        "relations": len(relations),
        "highways": dict(sorted(highways.items())),
        "named_ways": named,
        "oneway_ways": oneway,
        "pois": pois,
        "poi_category_keys": category_keys,
        "poi_classes_used": len(set(poi_counts)),
        "addresses": addresses,
        "address_streets": sorted({r["addr"]["street"] for r in nodes
                                   if r.get("addr", {}).get("street")}),
        "restrictions": sum(1 for r in relations
                            if r["tags"].get("type") == "restriction"),
        "water": sorted(water),
        "tiles": sorted({n["tile"] for n in nodes}),
        "diacritics": [ch for ch in "łó źŻśąę".replace(" ", "") if ch in text],
        "validated": imf_check.validate_text(text, "osm_synth.jsonl").ok,
    }


def _records_osm(seed: int, tile: str) -> str:
    """Rebuild the town's records and render them as OSM XML (deterministic)."""
    # generate() builds the same records from (seed, tile); the JSONL text is
    # the source of truth, so re-parse it rather than duplicate the layout.
    text, _ = generate(seed, tile)
    return render_osm([json.loads(line) for line in text.splitlines() if line.strip()])


def print_summary(summary: dict[str, Any], file=None) -> None:
    out = file or sys.stdout
    print("osm_synth summary", file=out)
    print("  seed %d tile %s" % (summary["seed"], summary["tile"]), file=out)
    print("  sha256 %s" % summary["sha256"], file=out)
    print("  nodes %d ways %d relations %d bytes %d"
          % (summary["nodes"], summary["ways"], summary["relations"],
             summary["bytes"]), file=out)
    print("  highways %s" % json.dumps(summary["highways"], sort_keys=True),
          file=out)
    print("  named %d oneway %d restrictions %d"
          % (summary["named_ways"], summary["oneway_ways"],
             summary["restrictions"]), file=out)
    print("  pois %d keys=%s classes=%d addresses %d streets=%s"
          % (summary["pois"], ",".join(summary["poi_category_keys"]),
             summary["poi_classes_used"], summary["addresses"],
             ",".join(summary["address_streets"])), file=out)
    print("  water %s diacritics %s"
          % (",".join(summary["water"]), "".join(summary["diacritics"])),
          file=out)
    print("  directory y=%d x=%d tiles %s validated=%s"
          % (summary["directory"][0], summary["directory"][1],
             ",".join(summary["tiles"]), summary["validated"]), file=out)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic synthetic OSM town as IMF v1 JSON Lines.",
    )
    parser.add_argument("--seed", type=int, default=1,
                        help="integer seed; the output depends only on seed+tile "
                             "(default 1)")
    parser.add_argument("--tile", default="B50R058R",
                        help="BxxRyyR cell the town is generated inside "
                             "(default B50R058R)")
    parser.add_argument("-o", "--out", metavar="FILE",
                        help="write JSONL here ('-' = stdout)")
    parser.add_argument("--osm-xml", metavar="FILE",
                        help="also write the same town as OSM XML 0.6 (the form "
                             "one_tile_pipeline.py --osm ingests)")
    parser.add_argument("--summary", action="store_true",
                        help="print the counts/SHA-256 summary (to stderr if "
                             "--out is '-', else stdout)")
    parser.add_argument("--selftest", action="store_true",
                        help="run the deterministic self-test")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.out and not args.summary and not args.osm_xml:
        parser.error("give -o/--out, --osm-xml, --summary, or --selftest")

    try:
        text, summary = generate(args.seed, args.tile)
    except SynthError as exc:
        print("osm_synth: %s" % exc, file=sys.stderr)
        return 1

    if args.osm_xml:
        try:
            Path(args.osm_xml).write_text(_records_osm(args.seed, args.tile),
                                          encoding="utf-8")
        except OSError as exc:
            print("osm_synth: cannot write %s: %s" % (args.osm_xml, exc),
                  file=sys.stderr)
            return 2

    if args.out == "-":
        sys.stdout.write(text)
        if args.summary:
            print_summary(summary, file=sys.stderr)
    else:
        if args.out:
            try:
                Path(args.out).write_text(text, encoding="utf-8")
            except OSError as exc:
                print("osm_synth: cannot write %s: %s" % (args.out, exc),
                      file=sys.stderr)
                return 2
        if args.summary:
            print_summary(summary)
    return 0


# --------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------


def selftest() -> int:
    """Prove determinism and the task's required content; pin seed 1's SHA."""
    print("osm_synth selftest")
    failures: list[str] = []
    checks_run = [0]

    def check(name: str, condition: bool, detail: str = "") -> None:
        checks_run[0] += 1
        print("  %-46s %s %s" % (name, "OK" if condition else "FAIL", detail))
        if not condition:
            failures.append(name)

    try:
        first, summary = generate(1, "B50R058R")
        second, _ = generate(1, "B50R058R")
        other, other_summary = generate(2, "B50R058R")
    except SynthError as exc:
        print("  generate FAIL: %s" % exc)
        return 1

    check("same seed is byte-identical", first == second,
          "falsifier: two runs with the same seed differ")
    check("two seeds differ", first != other,
          "seed 1 %s seed 2 %s" % (summary["sha256"][:12],
                                  other_summary["sha256"][:12]))

    pinned = "bf857e9c613685708be0e7677b1ea933a126cbf2e731827079e87697b2d40b18"
    check("seed 1 SHA-256 is pinned", summary["sha256"] == pinned,
          summary["sha256"])

    check("imf_check validates without errors", summary["validated"] is True)
    check("all records validate strictly too",
          imf_check.validate_text(first, "osm_synth.jsonl").ok and not
          imf_check.validate_text(first, "osm_synth.jsonl").warnings,
          "expected: no W001/W002 (every way named+speed) and no W003+")

    check("one tile only", summary["tiles"] == ["B50R058R"],
          str(summary["tiles"]))
    check("street grid plus ring road",
          summary["highways"].get("residential", 0) >= 4
          and summary["highways"].get("tertiary", 0) >= 4
          and summary["highways"].get("secondary", 1) >= 8,
          json.dumps(summary["highways"], sort_keys=True))
    check("motorway is generated", summary["highways"].get("motorway", 0) >= 2,
          str(summary["highways"].get("motorway")))
    check("Polish diacritics present",
          all(ch in first for ch in ("ł", "ó", "ź", "Ż", "ś", "ą", "ę")),
          "".join(summary["diacritics"]))
    check("one-way streets exist", summary["oneway_ways"] >= 2,
          str(summary["oneway_ways"]))
    check("turn restrictions exist", summary["restrictions"] == 2,
          str(summary["restrictions"]))
    check("50 POIs", summary["pois"] == POI_TARGET, str(summary["pois"]))
    check("every POI key category used",
          summary["poi_category_keys"]
          == sorted({k for k, _v, _n in POI_CLASSES}),
          ",".join(summary["poi_category_keys"]))
    check("house numbers on two streets",
          len(summary["address_streets"]) == 2 and summary["addresses"] >= 4,
          "%d on %s" % (summary["addresses"],
                        ",".join(summary["address_streets"])))
    check("river and lake",
          summary["water"] == ["river", "water"], str(summary["water"]))

    # The output is the writer's input shape: its own parser must read it, and
    # every way must fall in the target cell (no multi-cell way without a split).
    import tempfile  # noqa: E402
    with tempfile.TemporaryDirectory(prefix="osm_synth_") as directory:
        path = Path(directory) / "town.jsonl"
        path.write_text(first, encoding="utf-8")
        records = list(tilewriter.read_jsonl(str(path)))
        check("tilewriter.read_jsonl reads it",
              len(records) == 1 + summary["nodes"] + summary["ways"]
              + summary["relations"], str(len(records)))
        ways, stats = tilewriter.load_imf(str(path), "B50R058R")
        check("every way is in B50R058R",
              stats["ways_other_cells"] == 0 and stats["ways_multi_cell"] == 0,
              json.dumps(stats, sort_keys=True))
        check("tilewriter accepts every highway",
              len(ways) == summary["ways"] - len(summary["water"]),
              "%d road ways of %d ways" % (len(ways), summary["ways"]))

        # The pipeline (osm_ingest) starts from OSM XML, not IMF: the same town
        # must round-trip through it with the water dropped and nothing else.
        import osm_ingest  # noqa: E402
        osm_path = Path(directory) / "town.osm"
        osm_path.write_text(render_osm(records), encoding="utf-8")
        imf_path = Path(directory) / "town.imf.jsonl"
        rc = osm_ingest.main([str(osm_path), "-o", str(imf_path),
                              "--source-name", "osm_synth-selftest"])
        check("osm_ingest ingests the XML view", rc == 0, "exit=%d" % rc)
        ingested = [json.loads(line)
                    for line in imf_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()]
        iways = [r for r in ingested if r["type"] == "way"]
        ipois = [r for r in ingested if r["type"] == "node" and "poi" in r]
        iaddr = [r for r in ingested if r["type"] == "node" and "addr" in r]
        check("XML view keeps 50 POIs", len(ipois) == POI_TARGET, str(len(ipois)))
        check("XML view keeps 16 addresses", len(iaddr) == 16, str(len(iaddr)))
        check("XML view keeps 54 road ways",
              len(iways) == summary["ways"] - len(summary["water"]),
              str(len(iways)))
        check("XML view drops only the river and lake",
              summary["ways"] - len(iways) == 2,
              "%d dropped" % (summary["ways"] - len(iways)))
        check("XML view validates",
              imf_check.validate_text(imf_path.read_text(encoding="utf-8"),
                                      "town.imf.jsonl").ok)

    total = checks_run[0]
    failed = len(failures)
    print("osm_synth selftest: %s (%d/%d checks)"
          % ("OK" if not failed else "FAIL " + ", ".join(failures),
             total - failed, total))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
