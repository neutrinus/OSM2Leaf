#!/usr/bin/env python3
"""Ingest an OpenStreetMap extract into IMF v1 (JSON Lines).

IMF is specified in ``docs/research/intermediate-format.md``; this tool is the
extractor on its OSM side.  It reads ``.osm`` XML and ``.osm.pbf`` with the
standard library only and writes one IMF file: a header, the nodes used by
drivable ways, those ways, and the turn-restriction relations whose members
survive the filter.

Kept from OSM, nothing else:

* ``highway`` values a car can drive on (motorway … residential, ``service``,
  ``track``, ``road`` and the ``*_link`` variants) — footways, cycleways,
  paths, steps, pedestrian zones and ``construction`` are dropped;
* the nodes those ways reference, plus the ``via`` nodes of the turn
  restrictions that survive, and no other node (no node tags: address and POI
  nodes are a later task);
* the whitelisted way tags of the IMF document plus the Polish class helpers
  (``highway:category:pl``, ``highway:class:pl``);
* ``type=restriction`` relations whose ``from``/``to``/``via`` members are all
  in the output, so the IMF validator can resolve every reference.

The PBF reader is a minimal protobuf wire decoder for the OSM file format:
``BlobHeader``/``Blob`` framing (``raw`` and ``zlib`` payloads), the
``OSMHeader`` block for the replication timestamp, and ``PrimitiveBlock`` with
``DenseNodes``/``Node``/``Way``/``Relation``.  No third-party package, no
network, no vendor data.

Usage::

    python3 tools/osm_ingest.py region.osm.pbf -o region.imf.jsonl
    python3 tools/osm_ingest.py fixture.osm -o fixture.imf.jsonl --json
    python3 tools/osm_ingest.py region.osm.pbf -o cut.imf.jsonl \\
        --bbox 14.8,50.0,17.8,51.8
    python3 tools/osm_ingest.py --selftest

``--bbox`` is ``MINLON,MINLAT,MAXLON,MAXLAT`` (osmium's order).  A way is kept
when at least one of its vertices is inside the box; all of its vertices are
then kept too, so a way is never left with a dangling reference (the same
rule as ``osmium extract --strategy complete_ways``).

Exit codes: ``0`` ok, ``1`` malformed input or an input that cannot be
represented in IMF v1, ``2`` usage or I/O error.
"""

from __future__ import annotations

import argparse
import bz2
import calendar
import contextlib
import gzip
import json
import math
import os
import sys
import tempfile
import time
import zlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Iterator
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import imf_check  # noqa: E402  (sibling tool: one source for tiles and cm/s)

TOOL_VERSION = "1.0"
IMF_VERSION = 1

#: ``highway`` values a car can drive on.  ``track`` and ``service`` are kept
#: because dropping them is a build-profile decision (open question in
#: ``docs/research/osm-pipeline.md``), not an extractor decision.
DRIVABLE_HIGHWAYS = frozenset({
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "unclassified", "residential", "living_street", "service", "track",
    "road", "busway",
    "motorway_link", "trunk_link", "primary_link", "secondary_link",
    "tertiary_link",
})

#: Way tags copied verbatim; the list is the "Tags carried" table of
#: ``docs/research/intermediate-format.md`` restricted to the road rows.
WAY_TAGS = frozenset({
    "highway", "oneway", "junction",
    "maxspeed",
    "access", "motor_vehicle", "hgv", "bus",
    "ref", "int_ref", "name", "name:pl", "name:en",
    "surface", "lanes", "bridge", "tunnel", "width",
    "highway:category:pl", "highway:class:pl",
})

ONEWAY_VALUES = ("yes", "no", "-1")

#: Tile strings repeat thousands of times; intern them so ``node_tile`` holds
#: one object per cell instead of one per node.
_TILES: dict[str, str] = {}

MAX_BLOB_HEADER = 64 * 1024
MAX_BLOB = 32 * 1024 * 1024  # PBF spec: Blob must stay below 32 MiB

IMPLICIT_SPEED_LIMIT = 300  # IMF: maxspeed_kmh is 1..300


class IngestError(Exception):
    """Malformed input, or an input that cannot be represented in IMF v1."""


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _dumps(record: dict[str, Any]) -> str:
    """One canonical IMF line (the same encoder ``imf_check`` uses)."""
    return json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"


def _local(tag: str) -> str:
    """Element tag without a ``{namespace}`` prefix."""
    return tag.rsplit("}", 1)[-1]


def _finite(text: Any, what: str) -> float:
    try:
        value = float(text)
    except (TypeError, ValueError):
        raise IngestError(f"{what}: not a number: {text!r}") from None
    if not math.isfinite(value):
        raise IngestError(f"{what}: not a finite number: {text!r}")
    return round(value, 7)


def _tile(lat: float, lon: float) -> str:
    try:
        tile = imf_check.tile_for(lat, lon)
    except ValueError as exc:
        raise IngestError(f"{lat},{lon}: {exc}") from None
    return _TILES.setdefault(tile, tile)


def _iso_utc(seconds: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


@contextlib.contextmanager
def _open_binary(path: str | Path) -> Iterator[BinaryIO]:
    """Open *path* transparently, also for ``.gz``/``.bz2`` XML extracts."""
    with open(path, "rb") as probe:
        magic = probe.read(3)
    if magic[:2] == b"\x1f\x8b":
        with gzip.open(path, "rb") as handle:
            yield handle
    elif magic == b"BZh":
        with bz2.open(path, "rb") as handle:
            yield handle
    else:
        with open(path, "rb") as handle:
            yield handle


def detect_format(path: str | Path) -> str:
    """``"xml"`` or ``"pbf"``, from the suffix and the (decompressed) magic."""
    name = Path(path).name.lower()
    if name.endswith(".pbf"):
        return "pbf"
    if name.endswith((".osm", ".xml", ".osm.gz", ".osm.bz2", ".xml.gz")):
        return "xml"
    try:
        with _open_binary(path) as handle:
            head = handle.read(8)
    except OSError as exc:
        raise IngestError(f"{path}: {exc}") from None
    if head.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<"):
        return "xml"
    return "pbf"


def parse_bbox(text: str) -> tuple[float, float, float, float]:
    """``MINLON,MINLAT,MAXLON,MAXLAT`` (osmium order, spaces allowed)."""
    parts = [part for part in text.replace(",", " ").split() if part]
    if len(parts) != 4:
        raise IngestError(
            f"--bbox needs MINLON,MINLAT,MAXLON,MAXLAT (4 numbers), got {text!r}"
        )
    minlon, minlat, maxlon, maxlat = (_finite(part, "--bbox") for part in parts)
    if not (-180.0 <= minlon < maxlon <= 180.0):
        raise IngestError(f"--bbox: longitude range {minlon}..{maxlon} is invalid")
    if not (-90.0 <= minlat < maxlat <= 90.0):
        raise IngestError(f"--bbox: latitude range {minlat}..{maxlat} is invalid")
    return minlon, minlat, maxlon, maxlat


def _in_bbox(lat: float, lon: float, bbox: tuple[float, float, float, float]) -> bool:
    minlon, minlat, maxlon, maxlat = bbox
    return minlat <= lat <= maxlat and minlon <= lon <= maxlon


# --------------------------------------------------------------------------
# OSM data model (only the parts IMF needs)
# --------------------------------------------------------------------------


@dataclass
class OsmWay:
    id: int
    refs: list[int]
    tags: dict[str, str]


@dataclass
class OsmRelation:
    id: int
    members: list[tuple[str, int, str]]
    tags: dict[str, str]


# --------------------------------------------------------------------------
# Protobuf wire decoding (PBF)
# --------------------------------------------------------------------------


def _varint(buf: bytes, pos: int) -> tuple[int, int]:
    shift = 0
    value = 0
    while True:
        if pos >= len(buf):
            raise IngestError("truncated protobuf varint")
        byte = buf[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7
        if shift > 63:
            raise IngestError("protobuf varint longer than 64 bits")


def _fields(buf: bytes) -> Iterator[tuple[int, int, Any]]:
    """Yield ``(field, wire_type, value)`` for one protobuf message.

    Varints come back as unsigned ints, length-delimited fields as ``bytes``,
    fixed32/64 as ints; groups are rejected (they do not occur in PBF).
    """
    pos = 0
    end = len(buf)
    while pos < end:
        key, pos = _varint(buf, pos)
        number, wire = key >> 3, key & 7
        if number == 0:
            raise IngestError("protobuf field number 0")
        if wire == 0:
            value, pos = _varint(buf, pos)
        elif wire == 2:
            size, pos = _varint(buf, pos)
            if pos + size > end:
                raise IngestError("truncated length-delimited protobuf field")
            value = buf[pos:pos + size]
            pos += size
        elif wire == 1:
            if pos + 8 > end:
                raise IngestError("truncated fixed64 field")
            value = int.from_bytes(buf[pos:pos + 8], "little")
            pos += 8
        elif wire == 5:
            if pos + 4 > end:
                raise IngestError("truncated fixed32 field")
            value = int.from_bytes(buf[pos:pos + 4], "little")
            pos += 4
        else:
            raise IngestError(f"unsupported protobuf wire type {wire}")
        yield number, wire, value


def _int64(value: int) -> int:
    """Reinterpret an unsigned varint as two's-complement int64."""
    return value - (1 << 64) if value >= (1 << 63) else value


def _sint(value: int) -> int:
    """Zigzag-decode a sint32/sint64 varint."""
    return (value >> 1) ^ -(value & 1)


def _packed(buf: bytes) -> list[int]:
    values: list[int] = []
    pos = 0
    while pos < len(buf):
        value, pos = _varint(buf, pos)
        values.append(value)
    return values


def _packed_sints(buf: bytes) -> list[int]:
    return [_sint(value) for value in _packed(buf)]


def _deltas(values: list[int]) -> list[int]:
    out: list[int] = []
    total = 0
    for value in values:
        total += value
        out.append(total)
    return out


def _string_table(buf: bytes) -> list[str]:
    """Decode a ``StringTable`` into an index-addressable list.

    The table is used exactly as stored: **index 0 is the empty string kept in
    the file**, because the PBF specification reserves that slot as the
    DenseNodes ``keys_vals`` delimiter (``(...)* 0``) and every writer emits it
    as the first ``s`` entry.  Prepending a second empty string here would
    shift every tag, role and user index by one.

    A non-conforming table that omits slot 0 is tolerated by inserting one
    empty string, so index arithmetic still matches the spec.
    """
    strings: list[str] = []
    for number, wire, value in _fields(buf):
        if number == 1 and wire == 2:
            try:
                strings.append(value.decode("utf-8"))
            except UnicodeDecodeError:
                raise IngestError("string table entry is not UTF-8") from None
    if not strings or strings[0] != "":
        strings.insert(0, "")
    return strings


def _blob_header(buf: bytes) -> tuple[str, int]:
    btype: str | None = None
    datasize: int | None = None
    for number, wire, value in _fields(buf):
        if number == 1 and wire == 2:
            try:
                btype = value.decode("ascii")
            except UnicodeDecodeError:
                raise IngestError("BlobHeader.type is not ASCII") from None
        elif number == 3 and wire == 0:
            datasize = value
    if btype is None or datasize is None:
        raise IngestError("BlobHeader lacks type or datasize")
    return btype, datasize


def _blob_payload(buf: bytes) -> bytes:
    raw: bytes | None = None
    raw_size: int | None = None
    packed: bytes | None = None
    other: str | None = None
    names = {4: "lzma", 5: "bzip2", 6: "lz4", 7: "zstd"}
    for number, wire, value in _fields(buf):
        if wire != 2:
            continue
        if number == 1:
            raw = value
        elif number == 2:
            raw_size = value
        elif number == 3:
            packed = value
        elif number in names:
            other = names[number]
    if raw is not None:
        return raw
    if packed is not None:
        try:
            data = zlib.decompress(packed)
        except zlib.error as exc:
            raise IngestError(f"PBF blob is not valid zlib: {exc}") from None
        if raw_size is not None and len(data) != raw_size:
            raise IngestError(
                f"PBF blob inflates to {len(data)} bytes, header says {raw_size}"
            )
        return data
    if other is not None:
        raise IngestError(
            f"PBF blob uses {other} compression; only raw and zlib are read"
        )
    raise IngestError("PBF blob carries no payload")


def _header_block(buf: bytes) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    required: list[str] = []
    for number, wire, value in _fields(buf):
        if number == 4 and wire == 2:
            try:
                required.append(value.decode("utf-8"))
            except UnicodeDecodeError:
                raise IngestError("OSMHeader required_feature is not UTF-8") from None
        elif wire != 0:
            continue
        elif number == 32:
            meta["timestamp"] = _iso_utc(_int64(value))
        elif number == 33:
            meta["sequence"] = _int64(value)
    # A history file carries deleted elements and a per-object ``visible``
    # flag that this reader does not inspect; without the check a deleted way
    # would be emitted as live data.
    if "HistoricalInformation" in required:
        raise IngestError(
            "input contains history (required feature HistoricalInformation); "
            "ingest a current snapshot instead"
        )
    return meta


def _tags(keys: list[int], values: list[int], strings: list[str]) -> dict[str, str]:
    if len(keys) != len(values):
        raise IngestError("tag key/value count differs in a PBF record")
    tags: dict[str, str] = {}
    for key, value in zip(keys, values):
        if not (0 < key < len(strings)) or not (0 <= value < len(strings)):
            raise IngestError("tag index outside the PBF string table")
        tags[strings[key]] = strings[value]
    return tags


def _node(
    buf: bytes, strings: list[str], granularity: int, lat_offset: int, lon_offset: int
) -> Iterator[tuple[Any, ...]]:
    osm_id: int | None = None
    lat_raw: int | None = None
    lon_raw: int | None = None
    for number, wire, value in _fields(buf):
        if wire != 0:
            continue
        if number == 1:
            osm_id = _sint(value)
        elif number == 8:
            lat_raw = _sint(value)
        elif number == 9:
            lon_raw = _sint(value)
    if osm_id is None or lat_raw is None or lon_raw is None:
        raise IngestError("PBF Node lacks id/lat/lon")
    yield (
        "node",
        osm_id,
        round((lat_offset + granularity * lat_raw) / 1e9, 7),
        round((lon_offset + granularity * lon_raw) / 1e9, 7),
    )


def _dense_nodes(
    buf: bytes, strings: list[str], granularity: int, lat_offset: int, lon_offset: int
) -> Iterator[tuple[Any, ...]]:
    ids: list[int] = []
    lats: list[int] = []
    lons: list[int] = []
    for number, wire, value in _fields(buf):
        if wire != 2:
            continue
        if number == 1:
            ids = _deltas(_packed_sints(value))
        elif number == 8:
            lats = _deltas(_packed_sints(value))
        elif number == 9:
            lons = _deltas(_packed_sints(value))
        # field 10 (keys_vals) is node tags, which IMF does not carry here
    if not (len(ids) == len(lats) == len(lons)):
        raise IngestError(
            f"DenseNodes id/lat/lon counts differ: {len(ids)}/{len(lats)}/{len(lons)}"
        )
    for osm_id, lat_raw, lon_raw in zip(ids, lats, lons):
        yield (
            "node",
            osm_id,
            round((lat_offset + granularity * lat_raw) / 1e9, 7),
            round((lon_offset + granularity * lon_raw) / 1e9, 7),
        )


def _way(buf: bytes, strings: list[str]) -> OsmWay:
    osm_id: int | None = None
    keys: list[int] = []
    values: list[int] = []
    refs: list[int] = []
    for number, wire, value in _fields(buf):
        if number == 1 and wire == 0:
            osm_id = _int64(value)
        elif number == 2 and wire == 2:
            keys = _packed(value)
        elif number == 3 and wire == 2:
            values = _packed(value)
        elif number == 8 and wire == 2:
            refs = _deltas(_packed_sints(value))
    if osm_id is None:
        raise IngestError("PBF Way lacks an id")
    return OsmWay(osm_id, refs, _tags(keys, values, strings))


def _relation(buf: bytes, strings: list[str]) -> OsmRelation:
    osm_id: int | None = None
    keys: list[int] = []
    values: list[int] = []
    roles: list[int] = []
    memids: list[int] = []
    types: list[int] = []
    for number, wire, value in _fields(buf):
        if number == 1 and wire == 0:
            osm_id = _int64(value)
        elif number == 2 and wire == 2:
            keys = _packed(value)
        elif number == 3 and wire == 2:
            values = _packed(value)
        elif number == 8 and wire == 2:
            roles = _packed(value)
        elif number == 9 and wire == 2:
            memids = _deltas(_packed_sints(value))
        elif number == 10 and wire == 2:
            types = _packed(value)
    if osm_id is None:
        raise IngestError("PBF Relation lacks an id")
    if not (len(roles) == len(memids) == len(types)):
        raise IngestError(
            f"Relation member arrays differ: {len(roles)}/{len(memids)}/{len(types)}"
        )
    kind = {0: "node", 1: "way", 2: "relation"}
    members: list[tuple[str, int, str]] = []
    for role, memid, member_type in zip(roles, memids, types):
        if member_type not in kind:
            raise IngestError(f"relation member has unknown type {member_type}")
        if not 0 <= role < len(strings):
            raise IngestError("relation role index outside the string table")
        members.append((kind[member_type], memid, strings[role]))
    return OsmRelation(osm_id, members, _tags(keys, values, strings))


def _primitive_group(
    buf: bytes, strings: list[str], granularity: int, lat_offset: int, lon_offset: int
) -> Iterator[tuple[Any, ...]]:
    for number, wire, value in _fields(buf):
        if wire != 2:
            continue
        if number == 1:  # Node
            yield from _node(value, strings, granularity, lat_offset, lon_offset)
        elif number == 2:  # DenseNodes
            yield from _dense_nodes(value, strings, granularity, lat_offset, lon_offset)
        elif number == 3:  # Way
            yield ("way", _way(value, strings))
        elif number == 4:  # Relation
            yield ("relation", _relation(value, strings))


def _primitive_block(buf: bytes) -> Iterator[tuple[Any, ...]]:
    strings: list[str] = []
    groups: list[bytes] = []
    granularity = 100
    lat_offset = 0
    lon_offset = 0
    for number, wire, value in _fields(buf):
        if number == 1 and wire == 2:
            strings = _string_table(value)
        elif number == 2 and wire == 2:
            groups.append(value)
        elif number == 17 and wire == 0:
            granularity = value or 100
        elif number == 19 and wire == 0:
            lat_offset = _int64(value)
        elif number == 20 and wire == 0:
            lon_offset = _int64(value)
    if not strings:
        raise IngestError("PrimitiveBlock without a usable string table")
    for group in groups:
        yield from _primitive_group(group, strings, granularity, lat_offset, lon_offset)


def iter_pbf(path: str | Path) -> Iterator[tuple[Any, ...]]:
    """Yield ``("header", meta)``, then nodes, ways and relations."""
    seen_header = False
    with _open_binary(path) as handle:
        while True:
            head = handle.read(4)
            if not head:
                return
            if len(head) != 4:
                raise IngestError("truncated PBF blob-header length")
            size = int.from_bytes(head, "big")
            if not 0 < size <= MAX_BLOB_HEADER:
                raise IngestError(f"implausible PBF BlobHeader size {size}")
            header = handle.read(size)
            if len(header) != size:
                raise IngestError("truncated PBF BlobHeader")
            btype, datasize = _blob_header(header)
            if not 0 < datasize <= MAX_BLOB:
                raise IngestError(f"implausible PBF Blob size {datasize} ({btype})")
            blob = handle.read(datasize)
            if len(blob) != datasize:
                raise IngestError(f"truncated PBF Blob ({btype})")
            payload = _blob_payload(blob)
            if btype == "OSMHeader":
                seen_header = True
                yield ("header", _header_block(payload))
            elif btype == "OSMData":
                if not seen_header:
                    raise IngestError("OSMData block before any OSMHeader block")
                yield from _primitive_block(payload)
            # Unknown block types are skipped, as the file format requires.


# --------------------------------------------------------------------------
# OSM XML
# --------------------------------------------------------------------------


def _children(elem: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    """Child elements with the local tag *name* (namespace-tolerant)."""
    return [child for child in elem if _local(child.tag) == name]


def iter_xml(path: str | Path) -> Iterator[tuple[Any, ...]]:
    """Yield ``("header", meta)``, then nodes, ways and relations."""
    with _open_binary(path) as handle:
        try:
            context = ElementTree.iterparse(handle, events=("start", "end"))
            _, root = next(context)
        except (ElementTree.ParseError, StopIteration) as exc:
            raise IngestError(f"not a readable XML document: {exc}") from None
        if _local(root.tag) != "osm":
            raise IngestError(f"XML root is <{_local(root.tag)}>, expected <osm>")

        meta: dict[str, Any] = {}
        stamp = root.attrib.get("osmosis_replication_timestamp")
        if stamp and stamp.strip():
            meta["timestamp"] = stamp.strip()
        sequence = root.attrib.get("osmosis_replication_sequence_number")
        if sequence and sequence.strip().lstrip("-").isdigit():
            meta["sequence"] = int(sequence.strip())
        yield ("header", meta)

        for event, elem in context:
            if event != "end":
                continue
            tag = _local(elem.tag)
            # <nd>, <tag>, <member> and <bounds> belong to their parent, which
            # is processed at its own "end" event; clearing on them would cut
            # a way's children away while it is still being read.
            if tag not in ("node", "way", "relation"):
                continue
            if tag == "node":
                osm_id = elem.get("id")
                if osm_id is None:
                    raise IngestError("<node> without an id")
                yield (
                    "node",
                    int(osm_id),
                    _finite(elem.get("lat"), f"node {osm_id} lat"),
                    _finite(elem.get("lon"), f"node {osm_id} lon"),
                )
            elif tag == "way":
                osm_id = elem.get("id")
                if osm_id is None:
                    raise IngestError("<way> without an id")
                refs = [
                    int(nd.get("ref"))
                    for nd in _children(elem, "nd")
                    if nd.get("ref") is not None
                ]
                tags = {
                    item.get("k"): item.get("v")
                    for item in _children(elem, "tag")
                    if item.get("k") is not None and item.get("v") is not None
                }
                yield ("way", OsmWay(int(osm_id), refs, tags))
            else:  # relation
                osm_id = elem.get("id")
                if osm_id is None:
                    raise IngestError("<relation> without an id")
                members: list[tuple[str, int, str]] = []
                for item in _children(elem, "member"):
                    mtype = item.get("type")
                    ref = item.get("ref")
                    if mtype not in ("node", "way", "relation") or ref is None:
                        continue
                    members.append((mtype, int(ref), item.get("role") or ""))
                tags = {
                    item.get("k"): item.get("v")
                    for item in _children(elem, "tag")
                    if item.get("k") is not None and item.get("v") is not None
                }
                yield ("relation", OsmRelation(int(osm_id), members, tags))
            # The element is complete and consumed: drop it (and every earlier
            # top-level element) so a region extract stays memory-bounded.
            root.clear()


def iter_elements(path: str | Path, fmt: str) -> Iterator[tuple[Any, ...]]:
    return iter_pbf(path) if fmt == "pbf" else iter_xml(path)


# --------------------------------------------------------------------------
# IMF records
# --------------------------------------------------------------------------


def _way_tags(way: OsmWay, stats: "Stats") -> dict[str, str]:
    tags: dict[str, str] = {}
    for key in sorted(way.tags):
        if key in WAY_TAGS:
            value = way.tags[key]
            if isinstance(value, str) and value:
                tags[key] = value
    access = tags.get("access")
    if access is not None and access not in imf_check.ACCESS_VALUES:
        # E022: IMF v1 has a closed access vocabulary; anything else would
        # make the file invalid, so the raw tag is dropped and counted.
        del tags["access"]
        stats.dropped_access += 1
    return tags


def _speed(tags: dict[str, str], stats: "Stats") -> int | None:
    """Parse a plain integer km/h; drop a numeric value outside IMF's range."""
    raw = tags.get("maxspeed")
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text.isdigit():
        return None  # "none", "walk", "PL:urban": raw tag only (IMF E015)
    value = int(text)
    if 1 <= value <= IMPLICIT_SPEED_LIMIT:
        return value
    # A numeric raw value must have a matching maxspeed_kmh (E015), and 0 or
    # 999 km/h is outside IMF's range, so the only valid action is to drop it.
    del tags["maxspeed"]
    stats.dropped_speed += 1
    return None


def _way_record(
    way: OsmWay, node_tile: dict[int, str], stats: "Stats"
) -> dict[str, Any] | None:
    refs: list[int] = []
    for ref in way.refs:
        if refs and refs[-1] == ref:
            continue  # E019: IMF forbids a consecutively repeated node
        refs.append(ref)
    if len(refs) < 2:
        stats.dropped_short += 1
        return None
    tiles: list[str] = []
    for ref in refs:
        tile = node_tile.get(ref)
        if tile is None:
            stats.dropped_missing_nodes += 1
            return None
        tiles.append(tile)

    tags = _way_tags(way, stats)
    record: dict[str, Any] = {
        "imf": IMF_VERSION,
        "type": "way",
        "id": f"w{way.id}",
        "nodes": [f"n{ref}" for ref in refs],
        "tile": tiles[0],
        "tiles": sorted(set(tiles)),
        "tags": tags,
    }
    oneway = tags.get("oneway")
    if oneway in ONEWAY_VALUES:
        record["oneway"] = oneway
    speed = _speed(tags, stats)
    if speed is not None:
        record["maxspeed_kmh"] = speed
        record["maxspeed_cms"] = imf_check.kmh_to_cms(speed)
    stats.highway_counts[tags["highway"]] += 1
    return record


def _relation_record(
    rel: OsmRelation,
    way_ids: set[int],
    node_tile: dict[int, str],
    stats: "Stats",
) -> dict[str, Any] | None:
    tags = rel.tags
    if tags.get("type") != "restriction":
        stats.ignored_relations += 1
        return None
    if not tags.get("restriction"):
        stats.relations_incomplete += 1
        return None

    members: list[dict[str, str]] = []
    roles: set[str] = set()
    for mtype, ref, role in rel.members:
        if mtype == "node":
            if ref not in node_tile:
                stats.relations_unresolved += 1
                return None
        elif mtype == "way":
            if ref not in way_ids:
                stats.relations_unresolved += 1
                return None
        else:
            stats.relations_unresolved += 1
            return None
        roles.add(role)
        members.append({"type": mtype, "ref": f"{mtype[0]}{ref}", "role": role})

    if not {"from", "to", "via"} <= roles:
        # E017: a restriction needs one from, one to and one via member.
        stats.relations_incomplete += 1
        return None

    out_tags = {"type": "restriction"}
    for key in sorted(tags):
        if key == "restriction" or key.startswith("restriction:"):
            out_tags[key] = tags[key]
    return {
        "imf": IMF_VERSION,
        "type": "relation",
        "id": f"r{rel.id}",
        "members": members,
        "tags": out_tags,
    }


def _build_header(
    source_name: str, meta: dict[str, Any], generated: str | None
) -> dict[str, Any]:
    header: dict[str, Any] = {"imf": IMF_VERSION, "type": "header"}
    if generated:
        header["generated"] = generated
    # No argv in ``generator``: the bytes must not depend on how the tool was
    # called (``in.osm`` and ``in.osm.pbf`` have to produce the same file).
    header["generator"] = f"tools/osm_ingest.py {TOOL_VERSION}"
    source: dict[str, Any] = {"name": source_name}
    if meta.get("timestamp"):
        source["timestamp"] = meta["timestamp"]
    if meta.get("sequence") is not None:
        source["sequence"] = meta["sequence"]
    header["source"] = source
    header["license"] = {
        "database": "ODbL-1.0",
        "attribution": "© OpenStreetMap contributors",
        "url": "https://www.openstreetmap.org/copyright",
        "attribution_file": "ODbL.txt",
    }
    header["grid"] = {
        "tile": "BxxRyyR (hex): lat_min=int(B,16)*2/3, lon_max=108-int(R,16)",
        "units": "WGS84 degrees, 7 decimals",
        "speed": "integer cm/s",
    }
    return header


# --------------------------------------------------------------------------
# Ingest
# --------------------------------------------------------------------------


@dataclass
class Stats:
    fmt: str = ""
    source_name: str = ""
    nodes: int = 0
    ways: int = 0
    relations: int = 0
    ways_not_drivable: int = 0
    dropped_short: int = 0
    dropped_missing_nodes: int = 0
    dropped_outside_bbox: int = 0
    relations_unresolved: int = 0
    relations_incomplete: int = 0
    ignored_relations: int = 0
    dropped_access: int = 0
    dropped_speed: int = 0
    highway_counts: Counter[str] = field(default_factory=Counter)
    bytes_written: int = 0
    output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.fmt,
            "source": {"name": self.source_name},
            "output": self.output,
            "records": {
                "nodes": self.nodes,
                "ways": self.ways,
                "relations": self.relations,
            },
            "highways": dict(sorted(self.highway_counts.items())),
            "dropped": {
                "ways_not_drivable": self.ways_not_drivable,
                "ways_too_short": self.dropped_short,
                "ways_missing_nodes": self.dropped_missing_nodes,
                "ways_outside_bbox": self.dropped_outside_bbox,
                "relations_unresolved": self.relations_unresolved,
                "relations_incomplete": self.relations_incomplete,
                "relations_ignored": self.ignored_relations,
                "access_values": self.dropped_access,
                "maxspeed_values": self.dropped_speed,
            },
            "bytes": self.bytes_written,
        }


@contextlib.contextmanager
def _open_output(path: str) -> Iterator[Any]:
    """Text output; a file is written next to its target and renamed."""
    if path == "-":
        yield sys.stdout
        return
    target = Path(path)
    temporary = target.with_name(target.name + ".part")
    handle = open(temporary, "w", encoding="utf-8", newline="\n")
    try:
        yield handle
        handle.close()
        os.replace(temporary, target)
    except BaseException:
        handle.close()
        with contextlib.suppress(OSError):
            temporary.unlink()
        raise


def ingest(
    input_path: str | Path,
    output_path: str | Path,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    source_name: str | None = None,
    generated: str | None = None,
    fmt: str | None = None,
) -> Stats:
    """Read one OSM file and write one IMF file; return the run statistics."""
    fmt = fmt or detect_format(input_path)
    stats = Stats(fmt=fmt)
    ways: dict[int, OsmWay] = {}
    relations: list[OsmRelation] = []
    meta: dict[str, Any] = {}

    # Pass 1: the ways decide which nodes are worth a second pass.
    for event in iter_elements(input_path, fmt):
        kind = event[0]
        if kind == "header":
            meta = event[1]
        elif kind == "way":
            way: OsmWay = event[1]
            if way.tags.get("highway") not in DRIVABLE_HIGHWAYS:
                stats.ways_not_drivable += 1
                continue
            if len(way.refs) < 2:
                stats.dropped_short += 1
                continue
            ways[way.id] = way
        elif kind == "relation":
            rel: OsmRelation = event[1]
            if rel.tags.get("type") != "restriction":
                # IMF v1 carries only restriction relations; keeping the rest
                # in a region extract would cost memory for nothing.
                stats.ignored_relations += 1
                continue
            relations.append(rel)

    source_name = source_name or Path(input_path).name
    stats.source_name = source_name
    header = _build_header(source_name, meta, generated)
    needed = {ref for way in ways.values() for ref in way.refs}
    # A restriction's ``via`` node must reach the output even when it is not a
    # vertex of a kept way (a split ``from``/``to`` way, or a ``via`` way), or
    # the relation cannot be written without tripping E016.  Only relations
    # whose ``from``/``to`` ways survive are considered, so a relation that
    # will be dropped drags no stray node into the file.
    for rel in relations:
        anchors = [
            ref
            for mtype, ref, role in rel.members
            if mtype == "way" and role in ("from", "to")
        ]
        if not anchors or any(ref not in ways for ref in anchors):
            continue
        needed.update(ref for mtype, ref, _ in rel.members if mtype == "node")

    stats.output = str(output_path)
    node_tile: dict[int, str] = {}
    kept_ways: list[OsmWay] = []
    coords: dict[int, tuple[float, float]] = {}

    with _open_output(str(output_path)) as handle:

        def write(record: dict[str, Any]) -> None:
            line = _dumps(record)
            handle.write(line)
            stats.bytes_written += len(line.encode("utf-8"))

        write(header)

        if bbox is None:
            # Pass 2: nodes, streamed in input order (ascending id in a
            # standard extract, which is the order IMF wants anyway).
            for event in iter_elements(input_path, fmt):
                if event[0] != "node":
                    continue
                _, osm_id, lat, lon = event
                if osm_id not in needed or osm_id in node_tile:
                    continue
                tile = _tile(lat, lon)
                node_tile[osm_id] = tile
                write({
                    "imf": IMF_VERSION,
                    "type": "node",
                    "id": f"n{osm_id}",
                    "lat": lat,
                    "lon": lon,
                    "tile": tile,
                })
                stats.nodes += 1
            for way_id in sorted(ways):
                way = ways[way_id]
                if any(ref not in node_tile for ref in way.refs):
                    stats.dropped_missing_nodes += 1
                    continue
                kept_ways.append(way)
        else:
            # ``--bbox`` needs coordinates before the first node is written,
            # because a way that stays outside the box must not drag its
            # nodes into the file.  Only candidate vertices are buffered.
            for event in iter_elements(input_path, fmt):
                if event[0] != "node":
                    continue
                _, osm_id, lat, lon = event
                if osm_id in needed:
                    coords[osm_id] = (lat, lon)
            for way_id in sorted(ways):
                way = ways[way_id]
                if any(ref not in coords for ref in way.refs):
                    stats.dropped_missing_nodes += 1
                    continue
                if not any(_in_bbox(*coords[ref], bbox) for ref in way.refs):
                    stats.dropped_outside_bbox += 1
                    continue
                kept_ways.append(way)
            for osm_id in sorted({ref for way in kept_ways for ref in way.refs}):
                lat, lon = coords[osm_id]
                tile = _tile(lat, lon)
                node_tile[osm_id] = tile
                write({
                    "imf": IMF_VERSION,
                    "type": "node",
                    "id": f"n{osm_id}",
                    "lat": lat,
                    "lon": lon,
                    "tile": tile,
                })
                stats.nodes += 1

        way_ids: set[int] = set()
        for way in kept_ways:
            record = _way_record(way, node_tile, stats)
            if record is None:
                continue
            write(record)
            way_ids.add(way.id)
            stats.ways += 1

        for rel in sorted(relations, key=lambda item: item.id):
            record = _relation_record(rel, way_ids, node_tile, stats)
            if record is None:
                continue
            write(record)
            stats.relations += 1

    return stats


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def print_report(stats: Stats, *, as_json: bool, file: Any = None) -> None:
    stream = file or sys.stderr
    if as_json:
        print(json.dumps(stats.to_dict(), indent=2), file=stream)
        return
    print(f"input       {stats.fmt}", file=stream)
    print(f"output      {stats.output} ({stats.bytes_written} bytes)", file=stream)
    print(
        f"records     nodes={stats.nodes} ways={stats.ways} "
        f"relations={stats.relations}",
        file=stream,
    )
    highways = " ".join(
        f"{value}={count}" for value, count in sorted(stats.highway_counts.items())
    )
    print(f"highways    {highways or '-'}", file=stream)
    print(
        "dropped     "
        f"not_drivable={stats.ways_not_drivable} "
        f"too_short={stats.dropped_short} "
        f"missing_nodes={stats.dropped_missing_nodes} "
        f"bbox={stats.dropped_outside_bbox} "
        f"relations={stats.relations_unresolved + stats.relations_incomplete} "
        f"access={stats.dropped_access} "
        f"maxspeed={stats.dropped_speed}",
        file=stream,
    )
    print("result      OK", file=stream)


# --------------------------------------------------------------------------
# Synthetic fixtures (self-test and reproducibility)
# --------------------------------------------------------------------------
#
# Invented ids and geometry, real cell: every coordinate below is inside
# B48R058R (48-53.33 N, 12-20 E), the Wroclaw cell of the IMF document.
# Ways: a one-way street with a numeric maxspeed, its continuation with a
# non-numeric maxspeed, a roundabout, a reversed one-way primary road, one
# service road (no name/speed) and one footway that must be dropped.

FIXTURE_NODES: tuple[tuple[int, float, float], ...] = (
    (101, 51.1000000, 16.9000000),
    (102, 51.1005000, 16.9010000),
    (103, 51.1010000, 16.9020000),
    (104, 51.1015000, 16.9030000),
    (105, 51.1020000, 16.9040000),
    (201, 51.1100000, 16.9100000),
    (202, 51.1100000, 16.9120000),
    (203, 51.1120000, 16.9120000),
    (204, 51.1120000, 16.9100000),
    (301, 51.1050000, 16.9200000),
    (302, 51.1060000, 16.9210000),
    (401, 51.1080000, 16.9060000),
    (402, 51.1085000, 16.9070000),
    (501, 51.1070000, 16.9220000),
)

FIXTURE_WAYS: tuple[tuple[int, tuple[int, ...], dict[str, str]], ...] = (
    (
        1001,
        (101, 102, 103),
        {
            "highway": "residential",
            "oneway": "yes",
            "maxspeed": "30",
            "name": "ul. Testowa",
            "access": "destination",
        },
    ),
    (
        1002,
        (103, 104, 105),
        {
            "highway": "residential",
            "maxspeed": "none",
            "ref": "DW 123",
            "name": "ul. Testowa",
            "surface": "asphalt",
        },
    ),
    (
        1003,
        (201, 202, 203, 204, 201),
        {
            "highway": "secondary",
            "junction": "roundabout",
            "name": "Rondo Testowe",
        },
    ),
    (
        1004,
        (301, 302),
        {
            "highway": "primary",
            "oneway": "-1",
            "maxspeed": "70",
            "name": "ul. Jednokierunkowa",
            "ref": "DK 94",
        },
    ),
    (
        1005,
        (401, 402),
        {"highway": "footway", "name": "sciezka"},
    ),
    (
        1006,
        (302, 501),
        {"highway": "service", "surface": "paving_stones"},
    ),
)

FIXTURE_RELATIONS: tuple[
    tuple[int, tuple[tuple[str, int, str], ...], dict[str, str]], ...
] = (
    (
        9001,
        (("way", 1001, "from"), ("node", 103, "via"), ("way", 1002, "to")),
        {"type": "restriction", "restriction": "no_left_turn"},
    ),
    # A route relation: outside the M5.1 slice and outside IMF's strict set.
    (9002, (("way", 1001, ""),), {"type": "route", "route": "road"}),
    # A restriction whose from-way (footway) is not kept: must be dropped,
    # otherwise E016 would fire on an unresolved member.
    (
        9003,
        (("way", 1005, "from"), ("node", 402, "via"), ("way", 1002, "to")),
        {"type": "restriction", "restriction": "no_u_turn"},
    ),
)

FIXTURE_TIMESTAMP = "2026-11-06T00:00:00Z"
FIXTURE_SEQUENCE = 4024

#: A restriction whose ``via`` node is not a vertex of any kept way (a split
#: ``from``/``to`` way looks like this in real data).  The node must still be
#: written, or the relation cannot resolve its ``via`` member (IMF E016).
VIA_NODE = (601, 51.1040000, 16.9050000)
VIA_RELATION = (
    9004,
    (("way", 1001, "from"), ("node", 601, "via"), ("way", 1002, "to")),
    {"type": "restriction", "restriction": "no_straight_on"},
)


def write_osm_xml(path: str | Path, *, timestamp: str | None = FIXTURE_TIMESTAMP,
                  sequence: int | None = FIXTURE_SEQUENCE,
                  nodes: tuple[tuple[int, float, float], ...] = FIXTURE_NODES,
                  relations: tuple[
                      tuple[int, tuple[tuple[str, int, str], ...], dict[str, str]],
                      ...,
                  ] = FIXTURE_RELATIONS) -> Path:
    """Write the synthetic fixture as ``.osm`` XML (UTF-8)."""
    from xml.sax.saxutils import quoteattr

    attributes = ' version="0.6" generator="tools/osm_ingest.py selftest"'
    if timestamp:
        attributes += f" osmosis_replication_timestamp={quoteattr(timestamp)}"
    if sequence is not None:
        attributes += (
            f" osmosis_replication_sequence_number={quoteattr(str(sequence))}"
        )
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', f"<osm{attributes}>"]
    for osm_id, lat, lon in nodes:
        lines.append(f'  <node id="{osm_id}" lat="{lat:.7f}" lon="{lon:.7f}"/>')
    for osm_id, refs, tags in FIXTURE_WAYS:
        lines.append(f'  <way id="{osm_id}">')
        lines.extend(f'    <nd ref="{ref}"/>' for ref in refs)
        lines.extend(
            f"    <tag k={quoteattr(key)} v={quoteattr(value)}/>"
            for key, value in tags.items()
        )
        lines.append("  </way>")
    for osm_id, members, tags in relations:
        lines.append(f'  <relation id="{osm_id}">')
        lines.extend(
            f"    <member type={quoteattr(mtype)} ref={quoteattr(str(ref))} "
            f"role={quoteattr(role)}/>"
            for mtype, ref, role in members
        )
        lines.extend(
            f"    <tag k={quoteattr(key)} v={quoteattr(value)}/>"
            for key, value in tags.items()
        )
        lines.append("  </relation>")
    lines.append("</osm>")
    target = Path(path)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


# -- minimal PBF writer (self-test only) -----------------------------------


def _pb_varint(value: int) -> bytes:
    if value < 0:
        value += 1 << 64
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _pb_key(number: int, wire: int) -> bytes:
    return _pb_varint((number << 3) | wire)


def _pb_uint(number: int, value: int) -> bytes:
    return _pb_key(number, 0) + _pb_varint(value)


def _pb_len(number: int, payload: bytes) -> bytes:
    return _pb_key(number, 2) + _pb_varint(len(payload)) + payload


def _zigzag(value: int) -> int:
    return value << 1 if value >= 0 else ((-value) << 1) - 1


def _pb_packed(number: int, values: list[int], *, zigzag: bool = False) -> bytes:
    payload = b"".join(
        _pb_varint(_zigzag(value) if zigzag else value) for value in values
    )
    return _pb_len(number, payload)


def _pb_delta(values: list[int]) -> list[int]:
    out: list[int] = []
    previous = 0
    for value in values:
        out.append(value - previous)
        previous = value
    return out


def _pb_nanos(degrees: float) -> int:
    """Degrees -> integer nanodegrees, exact for the fixture's 1e-7 grid."""
    nanos = int(round(round(degrees, 7) * 1_000_000_000))
    if nanos % 100:
        raise ValueError(f"{degrees!r} is not on the 1e-7 degree grid")
    return nanos


class _StringTable:
    def __init__(self) -> None:
        self.items: list[str] = [""]
        self.index: dict[str, int] = {"": 0}

    def add(self, value: str) -> int:
        if value not in self.index:
            self.index[value] = len(self.items)
            self.items.append(value)
        return self.index[value]


def _pb_write_blob(handle: BinaryIO, btype: str, payload: bytes, *,
                   compress: bool = True) -> None:
    if compress:
        packed = zlib.compress(payload, 6)
        blob = _pb_uint(2, len(payload)) + _pb_len(3, packed)
    else:
        blob = _pb_len(1, payload)
    header = _pb_len(1, btype.encode("ascii")) + _pb_uint(3, len(blob))
    handle.write(len(header).to_bytes(4, "big"))
    handle.write(header)
    handle.write(blob)


def _pb_header_block(timestamp: str | None, sequence: int | None) -> bytes:
    block = _pb_len(4, b"OsmSchema-V0.6") + _pb_len(4, b"DenseNodes")
    block += _pb_len(16, b"tools/osm_ingest.py selftest")
    if timestamp:
        block += _pb_len(17, b"synthetic fixture")
        epoch = calendar.timegm(time.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ"))
        block += _pb_uint(32, epoch)
    if sequence is not None:
        block += _pb_uint(33, sequence)
    return block


def _pb_dense_nodes(
    nodes: tuple[tuple[int, float, float], ...]
) -> bytes:
    node_ids = [osm_id for osm_id, _, _ in nodes]
    lat_raw = [_pb_nanos(lat) // 100 for _, lat, _ in nodes]
    lon_raw = [_pb_nanos(lon) // 100 for _, _, lon in nodes]
    return (
        _pb_packed(1, _pb_delta(node_ids), zigzag=True)
        + _pb_packed(8, _pb_delta(lat_raw), zigzag=True)
        + _pb_packed(9, _pb_delta(lon_raw), zigzag=True)
    )


def _pb_way_message(strings: _StringTable, osm_id: int, refs: tuple[int, ...],
                    tags: dict[str, str]) -> bytes:
    return (
        _pb_uint(1, osm_id)
        + _pb_packed(2, [strings.add(key) for key in tags])
        + _pb_packed(3, [strings.add(value) for value in tags.values()])
        + _pb_packed(8, _pb_delta(list(refs)), zigzag=True)
    )


def _pb_relation_message(
    strings: _StringTable,
    osm_id: int,
    members: tuple[tuple[str, int, str], ...],
    tags: dict[str, str],
) -> bytes:
    return (
        _pb_uint(1, osm_id)
        + _pb_packed(2, [strings.add(key) for key in tags])
        + _pb_packed(3, [strings.add(value) for value in tags.values()])
        + _pb_packed(8, [strings.add(role) for _, _, role in members])
        + _pb_packed(9, _pb_delta([ref for _, ref, _ in members]), zigzag=True)
        + _pb_packed(10, [{"node": 0, "way": 1, "relation": 2}[mtype]
                          for mtype, _, _ in members])
    )


def _pb_string_table(strings: _StringTable) -> bytes:
    return b"".join(_pb_len(1, item.encode("utf-8")) for item in strings.items)


def write_osm_pbf(path: str | Path, *, timestamp: str | None = FIXTURE_TIMESTAMP,
                  sequence: int | None = FIXTURE_SEQUENCE,
                  nodes: tuple[tuple[int, float, float], ...] = FIXTURE_NODES,
                  relations: tuple[
                      tuple[int, tuple[tuple[str, int, str], ...], dict[str, str]],
                      ...,
                  ] = FIXTURE_RELATIONS) -> Path:
    """Write the same fixture as a minimal ``.osm.pbf`` (one block)."""
    strings = _StringTable()
    way_messages = [
        _pb_way_message(strings, osm_id, refs, tags)
        for osm_id, refs, tags in FIXTURE_WAYS
    ]
    relation_messages = [
        _pb_relation_message(strings, osm_id, members, tags)
        for osm_id, members, tags in relations
    ]

    block = _pb_len(1, _pb_string_table(strings))
    block += _pb_len(2, _pb_len(2, _pb_dense_nodes(nodes)))
    block += b"".join(_pb_len(2, _pb_len(3, msg)) for msg in way_messages)
    block += b"".join(_pb_len(2, _pb_len(4, msg)) for msg in relation_messages)

    target = Path(path)
    with open(target, "wb") as handle:
        _pb_write_blob(handle, "OSMHeader", _pb_header_block(timestamp, sequence))
        _pb_write_blob(handle, "OSMData", block)
    return target


def write_osm_pbf_spec(
    path: str | Path,
    *,
    timestamp: str | None = FIXTURE_TIMESTAMP,
    sequence: int | None = FIXTURE_SEQUENCE,
    nodes: tuple[tuple[int, float, float], ...] = FIXTURE_NODES,
    relations: tuple[
        tuple[int, tuple[tuple[str, int, str], ...], dict[str, str]], ...
    ] = FIXTURE_RELATIONS,
) -> Path:
    """Write the fixture the way a real extract is framed.

    A Geofabrik file does not look like the single-block fixture above: every
    ``PrimitiveGroup`` holds one kind (never nodes and ways together), each
    ``PrimitiveBlock`` carries its **own** string table (so a reader that
    caches the first table instead of the current one mis-decodes every tag),
    and the header blob may be stored uncompressed.  This writer produces that
    shape so the reader path, not just the writer, is exercised.
    """
    node_block = _pb_len(1, _pb_string_table(_StringTable()))
    node_block += _pb_len(2, _pb_len(2, _pb_dense_nodes(nodes)))

    way_strings = _StringTable()
    way_group = b"".join(
        _pb_len(3, _pb_way_message(way_strings, osm_id, refs, tags))
        for osm_id, refs, tags in FIXTURE_WAYS
    )
    way_block = _pb_len(1, _pb_string_table(way_strings)) + _pb_len(2, way_group)

    rel_strings = _StringTable()
    rel_group = b"".join(
        _pb_len(4, _pb_relation_message(rel_strings, osm_id, members, tags))
        for osm_id, members, tags in relations
    )
    rel_block = _pb_len(1, _pb_string_table(rel_strings)) + _pb_len(2, rel_group)

    target = Path(path)
    with open(target, "wb") as handle:
        _pb_write_blob(handle, "OSMHeader", _pb_header_block(timestamp, sequence),
                       compress=False)  # the ``raw`` blob path
        _pb_write_blob(handle, "OSMData", node_block)
        _pb_write_blob(handle, "OSMData", way_block)
        _pb_write_blob(handle, "OSMData", rel_block)
    return target


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------

#: What the fixture must ingest to: 12 way vertices (the footway's two nodes
#: are not referenced by a drivable way), 5 drivable ways, 1 restriction.
EXPECTED_COUNTS = (12, 5, 1)

BBOX_ROUNDABOUT = "16.909,51.109,16.913,51.113"


def selftest() -> int:
    """XML and PBF of the same fixture must produce identical IMF bytes."""
    print("osm_ingest selftest")
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        print(f"  {name:<32} {'OK' if condition else 'FAIL'} {detail}".rstrip())
        if not condition:
            failures.append(name)

    def split(text: str) -> list[Any]:
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    common = ("--source-name", "synthetic-fixture.osm.pbf")

    with tempfile.TemporaryDirectory(prefix="osm_ingest_") as directory:
        root = Path(directory)
        xml_path = root / "fixture.osm"
        pbf_path = root / "fixture.osm.pbf"
        write_osm_xml(xml_path)
        write_osm_pbf(pbf_path)

        out_xml = root / "xml.imf.jsonl"
        out_pbf = root / "pbf.imf.jsonl"
        code_xml = main([str(xml_path), "-o", str(out_xml), *common])
        code_pbf = main([str(pbf_path), "-o", str(out_pbf), *common])
        check("CLI xml", code_xml == 0, f"exit={code_xml}")
        check("CLI pbf", code_pbf == 0, f"exit={code_pbf}")

        text_xml = out_xml.read_text(encoding="utf-8")
        text_pbf = out_pbf.read_text(encoding="utf-8")
        records_xml = split(text_xml)
        records_pbf = split(text_pbf)
        check("same records", records_xml == records_pbf)
        check("byte-identical", text_xml == text_pbf)

        report_xml = imf_check.validate_text(text_xml, "xml.imf.jsonl")
        report_pbf = imf_check.validate_text(text_pbf, "pbf.imf.jsonl")
        check("imf_check xml", report_xml.ok,
              f"errors={len(report_xml.errors)}")
        check("imf_check pbf", report_pbf.ok,
              f"errors={len(report_pbf.errors)}")
        counts = (report_xml.nodes, report_xml.ways, report_xml.relations)
        check("record counts", counts == EXPECTED_COUNTS, str(counts))
        check(
            "same counts",
            counts == (report_pbf.nodes, report_pbf.ways, report_pbf.relations),
        )
        check(
            "no errors on either",
            not report_xml.errors and not report_pbf.errors,
            "; ".join(e.code for e in report_xml.errors[:4]),
        )

        # A spec-shaped extract (one group per kind, a fresh string table per
        # block, an uncompressed header blob) must produce the same bytes as
        # the XML: the fixture above uses one block, so it cannot catch a
        # reader that reuses a stale string table.
        spec_path = root / "spec.osm.pbf"
        write_osm_pbf_spec(spec_path)
        out_spec = root / "spec.imf.jsonl"
        code_spec = main([str(spec_path), "-o", str(out_spec), *common])
        text_spec = out_spec.read_text(encoding="utf-8")
        check("CLI spec pbf", code_spec == 0, f"exit={code_spec}")
        check("spec pbf identical", text_spec == text_xml)
        check(
            "spec pbf validates",
            imf_check.validate_text(text_spec, "spec.imf.jsonl").ok,
        )

        # The via node of a surviving restriction must be written even when no
        # kept way references it, or the relation is dropped for E016.
        via_path = root / "via.osm.pbf"
        write_osm_pbf_spec(
            via_path,
            nodes=FIXTURE_NODES + (VIA_NODE,),
            relations=FIXTURE_RELATIONS + (VIA_RELATION,),
        )
        out_via = root / "via.imf.jsonl"
        code_via = main([str(via_path), "-o", str(out_via), *common])
        via_text = out_via.read_text(encoding="utf-8")
        via_records = split(via_text)
        via_nodes = {r["id"] for r in via_records if r["type"] == "node"}
        via_rels = {r["id"] for r in via_records if r["type"] == "relation"}
        check("CLI via pbf", code_via == 0, f"exit={code_via}")
        check("via node kept", "n601" in via_nodes)
        check("via relation kept", "r9004" in via_rels)
        check(
            "via file validates",
            imf_check.validate_text(via_text, "via.imf.jsonl").ok,
        )

        header = records_xml[0]
        source = header.get("source", {})
        check(
            "header provenance",
            source.get("name") == "synthetic-fixture.osm.pbf"
            and source.get("timestamp") == FIXTURE_TIMESTAMP
            and source.get("sequence") == FIXTURE_SEQUENCE,
            json.dumps(source),
        )
        check("no wall-clock", "generated" not in header)

        ways = {r["id"]: r for r in records_xml if r["type"] == "way"}
        nodes = {r["id"]: r for r in records_xml if r["type"] == "node"}
        relations = [r for r in records_xml if r["type"] == "relation"]
        check("oneway yes", ways["w1001"]["oneway"] == "yes")
        check("oneway -1", ways["w1004"]["oneway"] == "-1")
        check(
            "maxspeed 30",
            ways["w1001"]["maxspeed_kmh"] == 30
            and ways["w1001"]["maxspeed_cms"] == imf_check.kmh_to_cms(30),
            str(ways["w1001"].get("maxspeed_cms")),
        )
        check(
            "maxspeed 'none'",
            "maxspeed_kmh" not in ways["w1002"]
            and ways["w1002"]["tags"]["maxspeed"] == "none",
        )
        check(
            "roundabout tag",
            ways["w1003"]["tags"]["junction"] == "roundabout"
            and len(ways["w1003"]["nodes"]) == 5,
        )
        check("footway dropped", "w1005" not in ways)
        check("footway nodes dropped",
              "n401" not in nodes and "n402" not in nodes)
        check(
            "tags whitelist",
            set(ways["w1004"]["tags"]) == {"highway", "oneway", "maxspeed",
                                           "name", "ref"},
            str(sorted(ways["w1004"]["tags"])),
        )
        check(
            "restriction kept",
            len(relations) == 1
            and relations[0]["id"] == "r9001"
            and relations[0]["tags"]["restriction"] == "no_left_turn",
        )
        check(
            "restriction members resolve",
            all(
                member["ref"] in nodes or member["ref"] in ways
                for member in relations[0]["members"]
            ),
        )
        check("route relation ignored", "r9002" not in {r["id"] for r in relations})
        check("unresolved restriction dropped",
              "r9003" not in {r["id"] for r in relations})

        # --assign-tiles must be a byte-identical no-op on our own field order.
        assigned_texts = []
        for text in (text_xml, text_pbf):
            assigned, issues = imf_check.assign_tiles(split(text))
            assigned_texts.append(
                "".join(
                    json.dumps(record, ensure_ascii=False, separators=(",", ":"))
                    + "\n"
                    for record in assigned
                )
            )
            check("assign-tiles issues", not issues, str(len(issues)))
        check("assign-tiles identical", assigned_texts[0] == assigned_texts[1])
        check("assign-tiles preserves bytes", assigned_texts[0] == text_xml)

        # Determinism: the same input twice, byte for byte.
        again = root / "again.imf.jsonl"
        main([str(xml_path), "-o", str(again), *common])
        check("deterministic", again.read_text(encoding="utf-8") == text_xml)

        # --bbox keeps the roundabout only; the restriction loses its ways.
        out_bbox = root / "bbox.imf.jsonl"
        code_bbox = main(
            [str(pbf_path), "-o", str(out_bbox), *common, "--bbox", BBOX_ROUNDABOUT]
        )
        bbox_text = out_bbox.read_text(encoding="utf-8")
        bbox_report = imf_check.validate_text(bbox_text, "bbox.imf.jsonl")
        bbox_counts = (bbox_report.nodes, bbox_report.ways, bbox_report.relations)
        check("bbox exit", code_bbox == 0, f"exit={code_bbox}")
        check("bbox validates", bbox_report.ok,
              "; ".join(e.code for e in bbox_report.errors[:4]))
        check("bbox records", bbox_counts == (4, 1, 0), str(bbox_counts))

        # A truncated PBF must be rejected, not silently half-read.
        broken = root / "broken.osm.pbf"
        broken.write_bytes(b"\x00\x00\x00\x0aOSMHeader")
        code_broken = main([str(broken), "-o", str(root / "broken.jsonl")])
        check("truncated pbf rejected", code_broken == 1, f"exit={code_broken}")

    print(f"selftest: {'OK' if not failures else 'FAILED'}")
    return 0 if not failures else 1


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog=(
            "Exit codes: 0 ok, 1 malformed input, 2 usage or I/O error. "
            "Output is IMF v1 JSON Lines; validate it with tools/imf_check.py."
        ),
    )
    parser.add_argument(
        "input", nargs="?", help=".osm (XML) or .osm.pbf extract ('-' unsupported)"
    )
    parser.add_argument(
        "-o", "--out", help="output IMF path ('-' = stdout)"
    )
    parser.add_argument(
        "--bbox",
        metavar="MINLON,MINLAT,MAXLON,MAXLAT",
        help="keep ways with at least one vertex in this box (osmium order)",
    )
    parser.add_argument(
        "--source-name",
        help="source.name for the IMF header (default: the input file name)",
    )
    parser.add_argument(
        "--generated",
        help="ISO-8601 UTC run timestamp; omitted by default so builds are "
             "reproducible",
    )
    parser.add_argument(
        "--format",
        choices=("xml", "pbf"),
        help="override format detection",
    )
    parser.add_argument(
        "--json", action="store_true", help="machine-readable ingest report"
    )
    parser.add_argument("--selftest", action="store_true", help="run synthetic tests")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    if not args.input:
        parser.error("an input .osm/.osm.pbf file is required (or --selftest)")
    if not args.out:
        parser.error("-o/--out is required for an ingest")

    bbox = None
    if args.bbox:
        try:
            bbox = parse_bbox(args.bbox)
        except IngestError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    try:
        stats = ingest(
            args.input,
            args.out,
            bbox=bbox,
            source_name=args.source_name,
            generated=args.generated,
            fmt=args.format,
        )
    except IngestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print_report(
        stats,
        as_json=args.json,
        # The report always goes to stderr: with ``-o -`` stdout carries the
        # IMF itself and a report line would corrupt the last record.
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
