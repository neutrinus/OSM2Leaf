#!/usr/bin/env python3
"""Validate a ZE0 OSM build profile against ``profiles/schema.json``.

Standard library only: no ``jsonschema`` dependency. The tool interprets the
keyword subset in ``SUPPORTED_KEYWORDS`` and raises ``SchemaError`` on any
keyword it does not understand, so the schema cannot silently outgrow the
validator.

Two profile shapes are accepted:

* **version 2** -- the canonical shape in ``profiles/schema.json``: region
  bbox, coverage tiers, whole-tile mode, border buffer in degrees,
  attribution, limits, outputs.
* **version 1 (legacy)** -- the four files shipped on 2026-11-05
  (``name``/``description``/``sources``/``include``/``detail``/``routing``).
  It is normalized to version 2 with documented defaults and reported as a
  warning; new profiles must use version 2.

What is checked beyond JSON Schema:

* the bbox is ordered ``[west, south, east, north]``, in range, non-degenerate,
  and its buffered form stays inside the WGS84 world;
* the border buffer is within ``0..5`` degrees and reported in km;
* coverage tiers have unique ids, a resolvable default, and sane regions;
* every tile id is on the verified 9 x 7 ``BxxRyyR`` lattice
  (``docs/format/map-tiles.md``);
* include/exclude do not overlap and at least one tile resolves;
* ``limits.max_tiles`` is enforced against the resolved tile count;
* unknown keys are warnings (``--strict`` turns them into errors);
* informational findings are **notes** (``N001``), printed with the report but
  never promoted by ``--strict`` -- a wide selection is a property of the tile
  lattice (sea/empty cells), not a defect of the profile.

Tile geometry comes from ``tools/mesh_grid.py`` (imported, not copied). Exit
codes: ``0`` valid (warnings allowed), ``1`` validation errors, ``2`` usage or
I/O error (including an unsupported schema keyword).

Usage::

    python3 tools/profile_validate.py profiles/dolnoslaskie-detail.json
    python3 tools/profile_validate.py profiles/*.json --json
    python3 tools/profile_validate.py profiles/poland-full.json --strict
    python3 tools/profile_validate.py --selftest

``profiles/*.json`` also expands to ``profiles/schema.json``; that file is the
schema, not a profile, so it is skipped with a message instead of failing the
run.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import mesh_grid

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
SCHEMA_PATH = REPO_ROOT / "profiles" / "schema.json"

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2

TILE_ID_RE = re.compile(r"^B([0-9A-F]{2})R([0-9A-F]{3})R$")

# Addressable tile lattice of the EU 2011 map: 9 latitude rows x 7 longitude
# columns stepping by 8 hex units, i.e. 63 cells. Only 45 of them exist as
# files (docs/format/map-tiles.md and C-120); the other cells are sea or empty,
# and the exact subset is vendor data that is not in this repository. Tile
# geometry comes from mesh_grid.tile_box().
GRID_ROWS = tuple(range(0x28, 0x69, 8))
GRID_COLS = tuple(range(0x48, 0x79, 8))
GRID_TILES = tuple(f"B{row:02X}R{col:03X}R" for row in GRID_ROWS for col in GRID_COLS)
SHIPPED_TILE_COUNT = 45

KM_PER_DEG_LAT = 111.32
MIN_BBOX_SPAN_DEG = 0.01
MAX_BUFFER_DEG = 5.0

# Coarse national extents, used only when a version-1 profile has
# ``include.bbox: null``. Values are the outer extremes of the country polygon
# (~0.01 deg), not a Geofabrik polygon. Extend this table when a profile needs
# a country it does not yet cover; unknown codes are an error, never a guess.
COUNTRY_BBOX = {
    "PL": (14.12, 49.00, 24.15, 54.84),
}

RULES = {
    "E001": "profile file unreadable or not valid JSON",
    "E002": "root is not an object, or the shape is not recognized",
    "E003": "required property missing",
    "E004": "property has the wrong JSON type",
    "E005": "value violates const/enum/oneOf",
    "E006": "number outside the allowed range",
    "E007": "string violates pattern or length",
    "E008": "array violates cardinality or uniqueness",
    "E009": "additional property is not allowed",
    "E010": "validator does not support a schema keyword",
    "E011": "schema $ref cannot be resolved",
    "E020": "region bbox is degenerate, inverted or outside WGS84",
    "E021": "border buffer pushes the search area outside WGS84",
    "E022": "coverage tier ids are duplicated or the default is unknown",
    "E023": "tile id is malformed",
    "E024": "a tile is both included and excluded",
    "E025": "no tile resolves for this profile",
    "E026": "profile violates its own limits",
    "E027": "country code has no known bbox",
    "E030": "legacy profile is structurally unusable",
    "W001": "unknown key (warning; --strict makes it an error)",
    "W002": "legacy version-1 shape (normalized)",
    "W003": "attribution defaulted because the legacy profile has none",
    "W004": "outputs defaulted because the legacy profile has none",
    "W005": "legacy routing block retained as metadata only",
    "W006": "included tile is off the delivered lattice and will be skipped",
    "W007": "border buffer is at least one tile of latitude",
    "W008": "search area extends outside the delivered lattice",
    "N001": "selection is wider than the 45 tiles the factory image ships (upper bound)",
}

SUPPORTED_KEYWORDS = {
    "$ref",
    "type",
    "required",
    "properties",
    "additionalProperties",
    "items",
    "enum",
    "const",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minLength",
    "maxLength",
    "pattern",
    "oneOf",
    "anyOf",
    "allOf",
}

ANNOTATION_KEYWORDS = {
    "$schema",
    "$id",
    "$defs",
    "title",
    "description",
    "default",
    "examples",
    "$comment",
}


class SchemaError(Exception):
    """The validator cannot interpret the schema itself (never a profile bug)."""


@dataclass
class Issue:
    code: str
    path: str
    message: str
    severity: str = "error"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "path": self.path,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass
class Report:
    path: str = ""
    shape: str = ""
    name: str = ""
    region: list[float] | None = None
    border_buffer_deg: float = 0.0
    tiles: list[dict[str, Any]] = field(default_factory=list)
    tier_counts: dict[str, int] = field(default_factory=dict)
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    notes: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, code: str, path: str, message: str) -> None:
        self.errors.append(Issue(code, path, message))

    def warn(self, code: str, path: str, message: str) -> None:
        self.warnings.append(Issue(code, path, message, severity="warning"))

    def note(self, code: str, path: str, message: str) -> None:
        self.notes.append(Issue(code, path, message, severity="note"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "shape": self.shape,
            "name": self.name,
            "region": self.region,
            "border_buffer_deg": self.border_buffer_deg,
            "border_buffer_km": round(self.border_buffer_deg * KM_PER_DEG_LAT, 2),
            "tile_count": len(self.tiles),
            "tiles": self.tiles,
            "tier_counts": dict(sorted(self.tier_counts.items())),
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
            "notes": [issue.to_dict() for issue in self.notes],
        }


# --------------------------------------------------------------------------
# Minimal JSON Schema 2020-12 subset
# --------------------------------------------------------------------------


def load_schema(path: Path | str | None = None) -> dict[str, Any]:
    path = Path(SCHEMA_PATH if path is None else path)
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaError(f"{path}: {exc}") from exc
    if not isinstance(schema, dict):
        raise SchemaError(f"{path}: schema root is not an object")
    return schema


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    if expected in ("number", "integer"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if expected == "integer":
            return float(value).is_integer()
        return True
    raise SchemaError(f"unsupported type keyword {expected!r}")


def _resolve_ref(ref: str, root: dict[str, Any]) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise SchemaError(f"only local $ref is supported, got {ref!r}")
    node: Any = root
    for part in ref[2:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or key not in node:
            raise SchemaError(f"unresolved $ref {ref!r}")
        node = node[key]
    if not isinstance(node, dict):
        raise SchemaError(f"$ref {ref!r} does not point at a schema object")
    return node


def _child(path: str, key: Any) -> str:
    if isinstance(key, int):
        return f"{path}[{key}]" if path else f"[{key}]"
    return f"{path}.{key}" if path else str(key)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def check_schema(instance: Any, schema: dict[str, Any]) -> tuple[list[Issue], list[Issue]]:
    """Validate ``instance``; returns (errors, warnings)."""
    errors: list[Issue] = []
    warnings: list[Issue] = []
    _walk(instance, schema, "", schema, errors, warnings, 0)
    return errors, warnings


def _walk(
    instance: Any,
    schema: dict[str, Any],
    path: str,
    root: dict[str, Any],
    errors: list[Issue],
    warnings: list[Issue],
    depth: int,
) -> None:
    if depth > 40:
        raise SchemaError("schema nesting deeper than 40 levels")
    if not isinstance(schema, dict):
        raise SchemaError(f"schema node at {path or '<root>'} is not an object")

    if "$ref" in schema:
        _walk(instance, _resolve_ref(schema["$ref"], root), path, root, errors, warnings, depth + 1)
        return

    for keyword in schema:
        if keyword not in SUPPORTED_KEYWORDS and keyword not in ANNOTATION_KEYWORDS:
            raise SchemaError(f"unsupported JSON Schema keyword {keyword!r} at {path or '<root>'}")

    if "allOf" in schema:
        for sub in schema["allOf"]:
            _walk(instance, sub, path, root, errors, warnings, depth + 1)

    for combinator in ("oneOf", "anyOf"):
        if combinator not in schema:
            continue
        branches = schema[combinator]
        matched = 0
        first_errors: list[str] = []
        for sub in branches:
            sub_errors: list[Issue] = []
            sub_warnings: list[Issue] = []
            _walk(instance, sub, path, root, sub_errors, sub_warnings, depth + 1)
            if sub_errors:
                first_errors.append(sub_errors[0].message)
            else:
                matched += 1
        if combinator == "oneOf" and matched != 1:
            errors.append(
                Issue(
                    "E005",
                    path,
                    f"matches {matched} of {len(branches)} allowed shapes, exactly one required"
                    + (f" ({first_errors[0]})" if first_errors else ""),
                )
            )
        elif combinator == "anyOf" and matched < 1:
            errors.append(
                Issue(
                    "E005",
                    path,
                    "matches none of the allowed shapes"
                    + (f" ({first_errors[0]})" if first_errors else ""),
                )
            )

        # The oneOf/anyOf branches in schema.json carry no other constraint.

    expected = schema.get("type")
    if expected is not None:
        if not _type_ok(instance, expected):
            errors.append(
                Issue("E004", path, f"expected {expected}, got {_type_name(instance)}")
            )
            return

    if "const" in schema and instance != schema["const"]:
        errors.append(
            Issue(
                "E005",
                path,
                f"must be {_canonical(schema['const'])}, got {_canonical(instance)}",
            )
        )
    if "enum" in schema and instance not in schema["enum"]:
        allowed = ", ".join(_canonical(item) for item in schema["enum"])
        errors.append(Issue("E005", path, f"must be one of [{allowed}]"))

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        for keyword, violated, text in (
            ("minimum", instance < schema.get("minimum", -math.inf), "below minimum"),
            ("maximum", instance > schema.get("maximum", math.inf), "above maximum"),
            (
                "exclusiveMinimum",
                instance <= schema.get("exclusiveMinimum", -math.inf),
                "not above exclusiveMinimum",
            ),
            (
                "exclusiveMaximum",
                instance >= schema.get("exclusiveMaximum", math.inf),
                "not below exclusiveMaximum",
            ),
        ):
            if keyword in schema and violated:
                errors.append(
                    Issue("E006", path, f"{text} {schema[keyword]:g} (got {instance:g})")
                )

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(
                Issue("E007", path, f"shorter than minLength {schema['minLength']}")
            )
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(
                Issue("E007", path, f"longer than maxLength {schema['maxLength']}")
            )
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(
                Issue("E007", path, f"does not match pattern {schema['pattern']!r}")
            )

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(
                Issue("E008", path, f"needs at least {schema['minItems']} item(s)")
            )
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(
                Issue("E008", path, f"allows at most {schema['maxItems']} item(s)")
            )
        if schema.get("uniqueItems"):
            seen: dict[str, int] = {}
            for index, item in enumerate(instance):
                key = _canonical(item)
                if key in seen:
                    errors.append(
                        Issue(
                            "E008",
                            path,
                            f"duplicate item {item!r} at [{seen[key]}] and [{index}]",
                        )
                    )
                else:
                    seen[key] = index
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(instance):
                _walk(item, schema["items"], _child(path, index), root, errors, warnings, depth + 1)

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(Issue("E003", _child(path, key), "required property missing"))
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties", None)
        for key, value in instance.items():
            child = _child(path, key)
            if key in properties:
                _walk(value, properties[key], child, root, errors, warnings, depth + 1)
            elif isinstance(extra, dict):
                _walk(value, extra, child, root, errors, warnings, depth + 1)
            elif extra is False:
                errors.append(Issue("E009", child, f"property {key!r} is not allowed"))
            else:
                warnings.append(
                    Issue(
                        "W001",
                        child,
                        f"unknown key {key!r} (schema version 2 has no such property)",
                        severity="warning",
                    )
                )


# --------------------------------------------------------------------------
# Version-1 (legacy) adapter
# --------------------------------------------------------------------------

LEGACY_TOP_KEYS = {"name", "description", "sources", "include", "detail", "routing"}
LEGACY_INCLUDE_KEYS = {"countries", "bbox", "border_buffer_km", "tiles"}
LEGACY_TILES_KEYS = {"mode", "include", "exclude"}
LEGACY_DETAIL_KEYS = {
    "roads",
    "addresses",
    "pois",
    "admin_boundaries",
    "extra_network",
}
LEGACY_EXTRA_KEYS = {"bbox", "roads"}
LEGACY_ROUTING_KEYS = {"profile", "keep_cross_border"}

ROAD_KEYWORDS = {"all", "core", "none"}
POI_KEYWORDS = {"all", "none"}


def _warn_unknown(obj: Any, known: set[str], path: str, report: Report) -> None:
    if not isinstance(obj, dict):
        return
    for key in obj:
        if key not in known:
            report.warn("W001", _child(path, key), f"unknown key {key!r} in legacy profile")


def _detail_value(value: Any, keywords: set[str]) -> Any:
    """Legacy detail values may be ``"a,b,c"`` strings; split them into lists."""
    if not isinstance(value, str) or value in keywords:
        return value
    if "," in value:
        return [part.strip() for part in value.split(",") if part.strip()]
    return value


def _union_bbox(boxes: list[tuple[float, float, float, float]]) -> list[float] | None:
    if not boxes:
        return None
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "profile"


def normalize_legacy(raw: dict[str, Any], report: Report) -> dict[str, Any]:
    """Map the 2026-11-05 version-1 shape onto the version-2 schema."""
    report.warn(
        "W002",
        "",
        "legacy version-1 profile (include/detail/routing); normalized to version 2",
    )
    _warn_unknown(raw, LEGACY_TOP_KEYS, "", report)

    include = raw.get("include")
    detail = raw.get("detail")
    routing = raw.get("routing")
    if not isinstance(include, dict):
        report.add("E030", "include", "legacy profile needs an 'include' object")
        include = {}
    if not isinstance(detail, dict):
        report.add("E030", "detail", "legacy profile needs a 'detail' object")
        detail = {}
    _warn_unknown(include, LEGACY_INCLUDE_KEYS, "include", report)
    _warn_unknown(detail, LEGACY_DETAIL_KEYS, "detail", report)

    legacy_tiles = include.get("tiles")
    if not isinstance(legacy_tiles, dict):
        legacy_tiles = {}
        report.add("E030", "include.tiles", "legacy profile needs an 'include.tiles' object")
    _warn_unknown(legacy_tiles, LEGACY_TILES_KEYS, "include.tiles", report)
    if legacy_tiles.get("mode", "whole") != "whole":
        report.add(
            "E030",
            "include.tiles.mode",
            "legacy tile mode must be 'whole'; sub-tile clipping is not implemented",
        )

    bbox = include.get("bbox")
    countries = include.get("countries") or []
    if bbox is None:
        boxes = []
        for code in countries:
            box = COUNTRY_BBOX.get(code)
            if box is None:
                report.add("E027", "include.countries", f"no known bbox for country {code!r}")
            else:
                boxes.append(box)
        bbox = _union_bbox(boxes)
        if bbox is None:
            report.add(
                "E020",
                "include.bbox",
                "legacy profile has neither a bbox nor a country with a known extent",
            )
            bbox = [0.0, 0.0, 0.0, 0.0]

    buffer_km = include.get("border_buffer_km", 0)
    if isinstance(buffer_km, bool) or not isinstance(buffer_km, (int, float)):
        report.add("E004", "include.border_buffer_km", "expected a number of kilometres")
        buffer_km = 0.0

    tier: dict[str, Any] = {
        "id": "detail",
        "roads": _detail_value(detail.get("roads", "all"), ROAD_KEYWORDS),
        "addresses": bool(detail.get("addresses", False)),
        "pois": _detail_value(detail.get("pois", "none"), POI_KEYWORDS),
        "admin_boundaries": bool(detail.get("admin_boundaries", False)),
    }
    tiers = [tier]

    extra = detail.get("extra_network")
    if extra is not None:
        if not isinstance(extra, dict):
            report.add("E030", "detail.extra_network", "expected an object")
        else:
            _warn_unknown(extra, LEGACY_EXTRA_KEYS, "detail.extra_network", report)
            tiers.append(
                {
                    "id": "corridor",
                    "description": "legacy extra_network corridor",
                    "roads": list(extra.get("roads") or []),
                    "addresses": False,
                    "pois": "none",
                    "admin_boundaries": False,
                    "region": {"bbox": list(extra.get("bbox") or [])},
                }
            )

    if routing is not None:
        _warn_unknown(routing, LEGACY_ROUTING_KEYS, "routing", report)
        report.warn(
            "W005",
            "routing",
            "legacy routing block is metadata only; no routing graph is built yet",
        )

    name = raw.get("name")
    report.warn(
        "W003",
        "attribution",
        "legacy profile has no attribution block; defaulted to manifest + ODbL text",
    )
    report.warn(
        "W004",
        "outputs",
        "legacy profile has no outputs block; defaulted to <name>.img with manifest",
    )

    return {
        "version": 2,
        "name": name,
        "description": raw.get("description"),
        "sources": raw.get("sources") or [],
        "region": {
            "bbox": list(bbox),
            "countries": list(countries),
        },
        "coverage": {"default": tiers[0]["id"], "tiers": tiers},
        "tiles": {
            "mode": "whole-tiles",
            "include": list(legacy_tiles.get("include") or []),
            "exclude": list(legacy_tiles.get("exclude") or []),
        },
        "border_buffer_deg": round(float(buffer_km) / KM_PER_DEG_LAT, 6),
        "attribution": {
            "text": "Map data (c) OpenStreetMap contributors, ODbL 1.0",
            "location": "manifest",
            "odbl_version": "1.0",
        },
        "limits": {"max_tiles": len(GRID_TILES)},        "outputs": {
            "image_name": f"{_slug(name or 'profile')}.img",
            "manifest": True,
            "verify": False,
        },
    }


def detect_shape(raw: dict[str, Any]) -> str:
    if raw.get("version") == 1:
        return "legacy"
    if "region" in raw or "coverage" in raw or raw.get("version") == 2:
        return "v2"
    if "include" in raw or "detail" in raw:
        return "legacy"
    return "unknown"


# --------------------------------------------------------------------------
# Profile semantics and tile resolution
# --------------------------------------------------------------------------


def buffered_bbox(bbox: list[float], buffer_deg: float) -> tuple[float, float, float, float]:
    """Widen ``bbox`` by ``buffer_deg`` of latitude, keeping the km width."""
    west, south, east, north = (float(value) for value in bbox)
    mid = math.radians((south + north) / 2.0)
    lon_pad = buffer_deg / max(math.cos(mid), 0.2)
    return west - lon_pad, south - buffer_deg, east + lon_pad, north + buffer_deg


def tile_box(tile_id: str) -> tuple[float, float, float, float]:
    """``(lat_min, lat_max, lon_min, lon_max)`` -- mesh_grid's order."""
    return mesh_grid.tile_box(tile_id + ".DAT")


def tile_bbox(tile_id: str) -> tuple[float, float, float, float]:
    """``(west, south, east, north)`` -- the profile/bbox order."""
    lat_min, lat_max, lon_min, lon_max = tile_box(tile_id)
    return lon_min, lat_min, lon_max, lat_max


def _intersects(
    box: tuple[float, float, float, float], other: tuple[float, float, float, float]
) -> bool:
    west, south, east, north = box
    o_west, o_south, o_east, o_north = other
    eps = 1e-9
    return (
        west < o_east - eps
        and o_west < east - eps
        and south < o_north - eps
        and o_south < north - eps
    )


def lattice_bbox() -> tuple[float, float, float, float]:
    boxes = [tile_bbox(tile) for tile in GRID_TILES]
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def check_bbox(report: Report, bbox: Any, path: str) -> None:
    if not isinstance(bbox, list) or len(bbox) != 4:
        return  # shape errors are the schema's job
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in bbox):
        return
    west, south, east, north = (float(value) for value in bbox)
    if not (-180.0 <= west <= 180.0 and -180.0 <= east <= 180.0):
        report.add("E020", path, "longitude outside -180..180")
    if not (-90.0 <= south <= 90.0 and -90.0 <= north <= 90.0):
        report.add("E020", path, "latitude outside -90..90")
    if west >= east:
        report.add("E020", path, f"west {west:g} is not left of east {east:g}")
    if south >= north:
        report.add("E020", path, f"south {south:g} is not below north {north:g}")
    if east - west < MIN_BBOX_SPAN_DEG or north - south < MIN_BBOX_SPAN_DEG:
        report.add("E020", path, "bbox is degenerate (smaller than 0.01 deg)")


def check_semantics(report: Report, doc: dict[str, Any]) -> None:
    region = doc["region"]
    bbox = region.get("bbox")
    report.region = [float(value) for value in bbox] if isinstance(bbox, list) else None
    check_bbox(report, bbox, "region.bbox")

    buffer_deg = doc.get("border_buffer_deg", 0)
    if isinstance(buffer_deg, (int, float)) and not isinstance(buffer_deg, bool):
        report.border_buffer_deg = float(buffer_deg)
        if buffer_deg >= 1.0:
            report.warn(
                "W007",
                "border_buffer_deg",
                f"{buffer_deg:g} deg is at least one tile of latitude",
            )
        if isinstance(bbox, list) and len(bbox) == 4:
            try:
                west, south, east, north = buffered_bbox(bbox, float(buffer_deg))
            except (TypeError, ValueError):
                west = south = east = north = 0.0
            if not (-90.0 <= south and north <= 90.0 and -180.0 <= west and east <= 180.0):
                report.add(
                    "E021",
                    "border_buffer_deg",
                    "buffer pushes the search area outside the WGS84 world",
                )

    coverage = doc.get("coverage")
    tiers = coverage.get("tiers") if isinstance(coverage, dict) else None
    if isinstance(tiers, list):
        ids = [tier.get("id") for tier in tiers if isinstance(tier, dict)]
        duplicates = sorted({tier_id for tier_id in ids if ids.count(tier_id) > 1})
        if duplicates:
            report.add("E022", "coverage.tiers", f"duplicate tier ids: {duplicates}")
        default = coverage.get("default")
        if default not in ids:
            report.add(
                "E022",
                "coverage.default",
                f"tier {default!r} is not defined (have {ids})",
            )
        for index, tier in enumerate(tiers):
            if not isinstance(tier, dict):
                continue
            if not tier.get("roads"):
                report.add("E030", f"coverage.tiers[{index}]", "tier has no road selection")
            tier_region = tier.get("region")
            if isinstance(tier_region, dict):
                check_bbox(report, tier_region.get("bbox"), f"coverage.tiers[{index}].region.bbox")

    tiles = doc.get("tiles")
    if isinstance(tiles, dict):
        include = tiles.get("include") or []
        exclude = tiles.get("exclude") or []
        for index, tile in enumerate(include):
            if isinstance(tile, str) and TILE_ID_RE.match(tile) and tile not in GRID_TILES:
                report.warn(
                    "W006",
                    f"tiles.include[{index}]",
                    f"{tile} is not one of the {len(GRID_TILES)} delivered lattice tiles",
                )
        overlap = sorted(set(include) & set(exclude))
        if overlap:
            report.add("E024", "tiles", f"tiles both included and excluded: {overlap}")


def resolve_tiles(report: Report, doc: dict[str, Any]) -> dict[str, str]:
    """Return ``{tile_id: tier_id}`` for the whole tiles this profile selects."""
    tiles = doc.get("tiles") or {}
    coverage = doc["coverage"]
    tiers = coverage["tiers"]
    default_id = coverage["default"]
    buffer_deg = float(doc.get("border_buffer_deg", 0.0))
    region_bbox = doc["region"]["bbox"]

    tier_boxes: list[tuple[str, tuple[float, float, float, float]]] = []
    for tier in tiers:
        tier_bbox = (tier.get("region") or {}).get("bbox") or region_bbox
        tier_boxes.append((tier["id"], buffered_bbox(tier_bbox, buffer_deg)))

    def tier_for(tile_id: str) -> tuple[str, bool]:
        box = tile_bbox(tile_id)
        for tier_id, tier_box in tier_boxes:
            if _intersects(box, tier_box):
                return tier_id, True
        return default_id, False

    include = list(tiles.get("include") or [])
    exclude = set(tiles.get("exclude") or [])
    selected: dict[str, str] = {}

    if include:
        for tile_id in include:
            if not TILE_ID_RE.match(tile_id) or tile_id not in GRID_TILES:
                continue
            if tile_id in exclude:
                continue
            tier_id, matched = tier_for(tile_id)
            if not matched:
                report.warn(
                    "W006",
                    "tiles.include",
                    f"{tile_id} touches no tier region; assigned default tier {default_id!r}",
                )
            selected[tile_id] = tier_id
    else:
        for tile_id in GRID_TILES:
            if tile_id in exclude:
                continue
            box = tile_bbox(tile_id)
            for tier_id, tier_box in tier_boxes:
                if _intersects(box, tier_box):
                    selected[tile_id] = tier_id
                    break

    if not selected and report.ok:
        report.add("E025", "tiles", "no whole tile resolves for this profile")

    if len(selected) > SHIPPED_TILE_COUNT:
        report.note(
            "N001",
            "tiles",
            f"{len(selected)} addressable cells selected, but the factory image ships "
            f"only {SHIPPED_TILE_COUNT}; sea/empty cells inflate the tile count and the "
            "estimate is an upper bound",
        )

    west, south, east, north = lattice_bbox()
    search_west, search_south, search_east, search_north = buffered_bbox(region_bbox, buffer_deg)
    if (
        search_west < west
        or search_east > east
        or search_south < south
        or search_north > north
    ):
        report.warn(
            "W008",
            "region.bbox",
            f"search area extends outside the lattice "
            f"({south:.2f}..{north:.2f} N, {west:.2f}..{east:.2f} E); "
            "only lattice tiles are buildable",
        )

    limits = doc.get("limits") or {}
    max_tiles = limits.get("max_tiles")
    if isinstance(max_tiles, int) and len(selected) > max_tiles:
        report.add(
            "E026",
            "limits.max_tiles",
            f"{len(selected)} tiles resolved, limit is {max_tiles}",
        )

    return selected


def validate_document(raw: Any, path: str = "<memory>") -> Report:
    report = Report(path=path)
    if not isinstance(raw, dict):
        report.add("E002", "", f"profile must be an object, got {_type_name(raw)}")
        return report

    shape = detect_shape(raw)
    if shape == "legacy":
        doc = normalize_legacy(raw, report)
        report.shape = "version 1 (legacy, normalized)"
    elif shape == "v2":
        doc = raw
        report.shape = "version 2"
    else:
        report.add(
            "E002",
            "",
            "unrecognized profile shape: expected version 2 (region/coverage/tiles) "
            "or version 1 (include/detail/routing)",
        )
        return report

    errors, warnings = check_schema(doc, load_schema())
    report.errors.extend(errors)
    report.warnings.extend(warnings)

    report.name = str(doc.get("name") or "")
    if not report.ok:
        return report

    check_semantics(report, doc)
    if not report.ok:
        return report

    selected = resolve_tiles(report, doc)
    report.tiles = [
        {
            "tile": tile_id,
            "tier": tier_id,
            "lat_min": round(tile_box(tile_id)[0], 4),
            "lat_max": round(tile_box(tile_id)[1], 4),
            "lon_min": round(tile_box(tile_id)[2], 4),
            "lon_max": round(tile_box(tile_id)[3], 4),
        }
        for tile_id, tier_id in sorted(selected.items())
    ]
    counts: dict[str, int] = {}
    for tile in report.tiles:
        counts[tile["tier"]] = counts.get(tile["tier"], 0) + 1
    report.tier_counts = counts
    return report


def validate_path(path: str | Path, *, strict: bool = False) -> Report:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report = Report(path=str(path))
        report.add("E001", "", f"cannot read profile: {exc}")
        return report
    report = validate_document(raw, str(path))
    if strict:
        for issue in report.warnings:
            report.add(issue.code, issue.path, issue.message + " (strict)")
        report.warnings.clear()
    return report


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def print_report(report: Report, file: Any = None) -> None:
    stream = file or sys.stdout
    print(f"profile   {report.path}", file=stream)
    print(f"shape     {report.shape or 'unknown'}", file=stream)
    if report.name:
        print(f"name      {report.name}", file=stream)
    if report.region:
        west, south, east, north = report.region
        print(
            f"region    W {west:7.2f}  S {south:6.2f}  E {east:7.2f}  N {north:6.2f}  "
            f"({east - west:.2f} x {north - south:.2f} deg)",
            file=stream,
        )
        mid = math.radians((south + north) / 2.0)
        lon_pad = report.border_buffer_deg / max(math.cos(mid), 0.2)
        print(
            f"buffer    {report.border_buffer_deg:.2f} deg "
            f"({report.border_buffer_deg * KM_PER_DEG_LAT:.0f} km; "
            f"longitude padding {lon_pad:.2f} deg at {mid * 180.0 / math.pi:.2f} N)",
            file=stream,
        )
    if report.tier_counts:
        counts = ", ".join(f"{tier} {count}" for tier, count in sorted(report.tier_counts.items()))
        print(f"tiers     {counts}", file=stream)
    if report.tiles:
        print(f"tiles     {len(report.tiles)}", file=stream)
        for tile in report.tiles:
            print(
                f"  {tile['tile']}  {tile['lat_min']:6.2f}..{tile['lat_max']:6.2f} N  "
                f"{tile['lon_min']:7.2f}..{tile['lon_max']:6.2f} E  tier={tile['tier']}",
                file=stream,
            )
    for issue in report.notes:
        location = f" at {issue.path}" if issue.path else ""
        print(f"note      {issue.code} {issue.message}{location}", file=stream)
    for issue in report.warnings:
        location = f" at {issue.path}" if issue.path else ""
        print(f"warning {issue.code} {issue.message}{location}", file=stream)
    for issue in report.errors:
        location = f" at {issue.path}" if issue.path else ""
        print(f"ERROR   {issue.code} {issue.message}{location}", file=stream)
    print(
        f"result    {'OK' if report.ok else 'FAILED'}"
        f" ({len(report.errors)} error(s), {len(report.warnings)} warning(s))",
        file=stream,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Exit codes: 0 valid (warnings allowed), 1 validation errors, "
        "2 usage or I/O error.",
    )
    parser.add_argument("profile", nargs="*", help="JSON profile file(s) to validate")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument(
        "--strict", action="store_true", help="treat warnings (unknown keys, legacy) as errors"
    )
    parser.add_argument(
        "--schema", default=str(SCHEMA_PATH), help="schema path (default: profiles/schema.json)"
    )
    parser.add_argument("--selftest", action="store_true", help="run synthetic tests")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()

    if not args.profile:
        print("error: no profile given (use --selftest for the synthetic tests)", file=sys.stderr)
        return EXIT_USAGE

    global SCHEMA_PATH
    SCHEMA_PATH = Path(args.schema)

    schema_path = SCHEMA_PATH.resolve()
    reports: list[Report] = []
    skipped: list[str] = []
    try:
        for path in args.profile:
            if Path(path).resolve() == schema_path:
                skipped.append(str(path))
                continue
            reports.append(validate_path(path, strict=args.strict))
    except SchemaError as exc:
        print(f"error: schema: {exc}", file=sys.stderr)
        return EXIT_USAGE

    for path in skipped:
        print(f"skip      {path} (the schema, not a profile)", file=sys.stderr)
    if not reports:
        print(
            "error: no profile given (only the schema file was passed)",
            file=sys.stderr,
        )
        return EXIT_USAGE

    if args.json:
        payload = reports[0].to_dict() if len(reports) == 1 else [r.to_dict() for r in reports]
        print(json.dumps(payload, indent=2))
    else:
        for index, report in enumerate(reports):
            if index:
                print()
            print_report(report)

    if any(issue.code == "E001" for report in reports for issue in report.errors):
        return EXIT_USAGE
    return EXIT_OK if all(report.ok for report in reports) else EXIT_INVALID


# --------------------------------------------------------------------------
# Selftest
# --------------------------------------------------------------------------


def _valid_v2() -> dict[str, Any]:
    return {
        "version": 2,
        "name": "selftest-detail",
        "description": "Synthetic single-tier profile for the validator selftest.",
        "sources": ["synthetic.osm.pbf"],
        "region": {"bbox": [14.0, 49.9, 17.9, 51.9], "countries": ["PL"]},
        "coverage": {
            "default": "detail",
            "tiers": [
                {
                    "id": "detail",
                    "roads": "all",
                    "addresses": True,
                    "pois": "all",
                    "admin_boundaries": True,
                }
            ],
        },
        "tiles": {"mode": "whole-tiles", "include": [], "exclude": []},
        "border_buffer_deg": 0.45,
        "attribution": {
            "text": "Map data (c) OpenStreetMap contributors, ODbL 1.0",
            "location": "manifest",
        },
        "limits": {"max_tiles": 63},
        "outputs": {"image_name": "selftest-detail.img", "manifest": True},
    }


def _legacy_v1() -> dict[str, Any]:
    return {
        "name": "selftest-legacy",
        "description": "Synthetic version-1 profile for the validator selftest.",
        "sources": ["synthetic.osm.pbf"],
        "include": {
            "countries": ["PL"],
            "bbox": [14.0, 49.9, 17.9, 51.9],
            "border_buffer_km": 50,
            "tiles": {"mode": "whole", "include": [], "exclude": []},
        },
        "detail": {
            "roads": "all",
            "addresses": True,
            "pois": "all",
            "admin_boundaries": True,
        },
        "routing": {"profile": "car", "keep_cross_border": True},
    }


def selftest() -> int:
    checks = 0
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(f"{name}: {detail}" if detail else name)
            print(f"  FAIL {name} {detail}".rstrip())
        else:
            print(f"  ok   {name}")

    # 1. Every keyword in the schema is understood by the validator.
    schema = load_schema()
    keywords: set[str] = set()

    def collect(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("properties", "$defs"):
                    for child in value.values():
                        collect(child)
                elif key == "items":
                    collect(value)
                elif key in ("oneOf", "anyOf", "allOf"):
                    for child in value:
                        collect(child)
                else:
                    keywords.add(key)

    collect(schema)
    unsupported = sorted(
        keyword
        for keyword in keywords
        if keyword not in SUPPORTED_KEYWORDS and keyword not in ANNOTATION_KEYWORDS
    )
    check("schema keywords supported", not unsupported, str(unsupported))

    # 2. Lattice size and agreement with mesh_grid's geometry.
    check("addressable lattice is 9x7 = 63", len(GRID_TILES) == 63, str(len(GRID_TILES)))
    check("shipped tile count is 45", SHIPPED_TILE_COUNT == 45)
    check(
        "mesh_grid agrees with lattice",
        mesh_grid.tile_box("B48R058R.DAT") == tile_box("B48R058R"),
        str(tile_box("B48R058R")),
    )

    # 3. A canonical version-2 profile validates and resolves one tile.
    report = validate_document(_valid_v2(), "<selftest-v2>")
    check("v2 profile valid", report.ok, str([i.message for i in report.errors]))
    check("v2 tile count 1", len(report.tiles) == 1, str(report.tiles))
    check(
        "v2 resolves B48R058R",
        [tile["tile"] for tile in report.tiles] == ["B48R058R"],
        str([tile["tile"] for tile in report.tiles]),
    )

    # 4. Border buffer widens the tile set (0 deg vs 3 deg).
    doc = _valid_v2()
    doc["border_buffer_deg"] = 0.0
    narrow = validate_document(doc, "<selftest-nobuffer>")
    doc["border_buffer_deg"] = 3.0
    wide = validate_document(doc, "<selftest-widebuffer>")
    check("buffer widens selection", len(wide.tiles) > len(narrow.tiles),
          f"{len(narrow.tiles)} -> {len(wide.tiles)}")
    check("wide buffer warns", any(i.code == "W007" for i in wide.warnings), str(wide.warnings))

    # 5. Legacy shape normalizes, warns, and keeps the same tile.
    legacy = validate_document(_legacy_v1(), "<selftest-v1>")
    check("legacy profile valid", legacy.ok, str([i.message for i in legacy.errors]))
    check("legacy warns W002", any(i.code == "W002" for i in legacy.warnings))
    check("legacy warns W003/W004", {i.code for i in legacy.warnings} >= {"W003", "W004"})
    check(
        "legacy tile matches v2",
        [tile["tile"] for tile in legacy.tiles]
        == [tile["tile"] for tile in report.tiles],
    )
    check("legacy buffer degrees", abs(legacy.border_buffer_deg - 0.449) < 0.01,
          str(legacy.border_buffer_deg))

    # 6. Failure cases: each must produce the expected code.
    def mutated(mutate) -> Report:
        doc = _valid_v2()
        mutate(doc)
        return validate_document(doc, "<selftest-mutated>")

    cases = [
        (
            "inverted bbox",
            lambda doc: doc["region"].update({"bbox": [18.0, 49.9, 14.0, 51.9]}),
            "E020",
        ),
        (
            "bbox out of range",
            lambda doc: doc["region"].update({"bbox": [14.0, 49.9, 17.9, 91.0]}),
            "E020",
        ),
        (
            "buffer out of range",
            lambda doc: doc.update({"border_buffer_deg": 9.0}),
            "E006",
        ),
        (
            "negative buffer",
            lambda doc: doc.update({"border_buffer_deg": -1.0}),
            "E006",
        ),
        (
            "duplicate tier",
            lambda doc: doc["coverage"]["tiers"].append(dict(doc["coverage"]["tiers"][0])),
            "E022",
        ),
        (
            "unknown default tier",
            lambda doc: doc["coverage"].update({"default": "nope"}),
            "E022",
        ),
        (
            "legacy tile mode",
            lambda doc: doc["tiles"].update({"mode": "whole"}),
            "E005",
        ),
        (
            "bad tile id",
            lambda doc: doc["tiles"].update({"include": ["B4AR58R"]}),
            "E007",
        ),
        (
            "include and exclude",
            lambda doc: doc["tiles"].update(
                {"include": ["B48R058R"], "exclude": ["B48R058R"]}
            ),
            "E024",
        ),
        (
            "missing outputs",
            lambda doc: doc.pop("outputs"),
            "E003",
        ),
        (
            "unknown key",
            lambda doc: doc.update({"detail": {"roads": "all"}}),
            "W001",
        ),
        (
            "max_tiles limit",
            lambda doc: (
                doc.update({"border_buffer_deg": 3.0}),
                doc.update({"limits": {"max_tiles": 1}}),
            ),
            "E026",
        ),
    ]
    for name, mutate, code in cases:
        case = mutated(mutate)
        found = {issue.code for issue in case.errors + case.warnings}
        check(f"{name} -> {code}", code in found, str(sorted(found)))

    # 7. Empty tile set is an error, not a silent zero.
    doc = _valid_v2()
    doc["region"]["bbox"] = [-60.0, -10.0, -55.0, -5.0]
    offgrid = validate_document(doc, "<selftest-offgrid>")
    check("no tiles -> E025", any(i.code == "E025" for i in offgrid.errors),
          str([i.message for i in offgrid.errors]))

    # 8. Strict mode turns warnings into errors.
    doc = _valid_v2()
    doc["extra"] = True
    with _temp_profile(doc) as path:
        lenient = validate_path(path)
        strict = validate_path(path, strict=True)
    check("unknown key warns", lenient.ok and any(i.code == "W001" for i in lenient.warnings))
    check("strict rejects warning", not strict.ok and strict.warnings == [])

    # 9. Shipped profiles are schema version 2 and pass --strict with no
    #    warnings. The tile counts are the regression values from EXP-45.
    for name, expected in (
        ("dolnoslaskie-detail.json", 1),
        ("dolnoslaskie-test.json", 1),
        ("poland-full.json", 4),
        ("europe-motorways.json", 56),
    ):
        path = REPO_ROOT / "profiles" / name
        if not path.exists():
            check(f"shipped {name}", False, "missing")
            continue
        shipped = validate_path(path, strict=True)
        check(
            f"shipped {name} strict valid",
            shipped.ok,
            str([i.message for i in shipped.errors]),
        )
        check(
            f"shipped {name} has no warnings",
            shipped.warnings == [],
            str([i.code for i in shipped.warnings]),
        )
        check(f"shipped {name} is version 2", shipped.shape == "version 2", shipped.shape)
        check(
            f"shipped {name} tiles={expected}",
            len(shipped.tiles) == expected,
            str([tile["tile"] for tile in shipped.tiles]),
        )

    # 10. A wide selection is an informational note, so it never fails --strict.
    doc = _valid_v2()
    doc["region"]["bbox"] = list(lattice_bbox())
    doc["border_buffer_deg"] = 0.0
    wide = validate_document(doc, "<selftest-wide-selection>")
    check("wide selection is valid", wide.ok, str([i.message for i in wide.errors]))
    check("wide selection is a note", any(i.code == "N001" for i in wide.notes),
          str([i.code for i in wide.notes]))
    check("notes are not warnings", wide.warnings == [],
          str([i.code for i in wide.warnings]))

    # 11. A shell wildcard that expands to the schema skips it, not fails.
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(
            [str(SCHEMA_PATH), str(REPO_ROOT / "profiles" / "poland-full.json")]
        )
    check("schema file is skipped", code == EXIT_OK, str(code))
    check(
        "skip is explained",
        "the schema, not a profile" in err.getvalue(),
        err.getvalue(),
    )
    check(
        "real profile still reported",
        "poland-full" in out.getvalue(),
        out.getvalue()[:200],
    )

    print(f"\nchecks: {checks}, failures: {len(failures)}")
    if failures:
        for failure in failures:
            print(f"  FAILED {failure}")
        return 1
    print("selftest: OK")
    return 0


class _temp_profile:
    """Context manager writing a JSON document to a temporary file."""

    def __init__(self, document: Any) -> None:
        self.document = document
        self.path = ""

    def __enter__(self) -> Path:
        handle, name = tempfile.mkstemp(suffix=".json", prefix="profile-selftest-")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(self.document, stream)
        self.path = name
        return Path(name)

    def __exit__(self, *exc_info: Any) -> None:
        try:
            os.unlink(self.path)
        except OSError:
            pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SchemaError as exc:
        print(f"error: schema: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
