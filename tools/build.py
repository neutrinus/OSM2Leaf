#!/usr/bin/env python3
"""Dry-run the size estimate for a ZE0 OSM build profile.

This is the skeleton of ``tools/build.py``: it validates the profile, resolves
the whole ``BxxRyyR`` tiles the profile selects, and prints a size breakdown.
It **never writes an image**. Without ``--dry-run`` it exits with code 3 and
says so; the writer is the remaining work in ``TODO.md`` ("Print a size
breakdown before writing an image", "Implement whole-tile selection").

The breakdown is an **ESTIMATE**, not a measurement:

* the tile count is exact for the verified grid
  (``docs/format/map-tiles.md``) and the profile's bbox + border buffer;
* the roads row uses the measured Dolnośląskie numbers
  (``docs/research/build-profiles.md``: 18.8 MB raw / 13.7 MB zlib for all
  drivable roads, 1.0 MB for motorway-secondary) as a per-tile budget;
* ``refer`` (names + address index) and ``poi`` rows are **placeholders** with
  no measurement behind them yet; they are printed with a PLACEHOLDER tag and
  must not be quoted as a result.

Usage::

    python3 tools/build.py --profile profiles/dolnoslaskie-detail.json --dry-run
    python3 tools/build.py --profile profiles/poland-full.json --dry-run --json
    python3 tools/build.py --selftest

Exit codes: ``0`` dry run finished, ``1`` profile invalid or over its limits,
``2`` usage or I/O error, ``3`` the writer is not implemented (no ``--dry-run``).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import profile_validate

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
EXIT_NOT_IMPLEMENTED = 3

MB = 1_000_000

#: Free space reported in docs/research/build-profiles.md ("about 2.35 GB").
CARD_FREE_BYTES = 2_350_000_000
#: Dense factory tile, docs/format/map-tiles.md. A ceiling, not a target.
FACTORY_DENSE_TILE_BYTES = 436_000_000

#: Per whole-tile budgets, zlib bytes. "documented" rows are anchored to a
#: measurement in the repo docs; "placeholder" rows have no measurement yet
#: and the estimator tags them as such.
#:
#: Roads: docs/research/osm-pipeline.md extrapolates 165 MB for all drivable
#: roads in Poland; the four tiles poland-full resolves therefore carry about
#: 41 MB each. The measured Dolnośląskie sample (18.8 MB raw / 13.7 MB zlib) is
#: one region inside a single tile, so it is only used for the core network.
BUDGET_ROADS_ALL = 41_000_000
BUDGET_ROADS_CORE = 1_000_000  # documented: Dolnośląskie, motorway-secondary
BUDGET_REFER_ALL = 2_000_000  # placeholder: names + address index, dense tier
BUDGET_REFER_CORE = 500_000  # placeholder: names only, sparse tier
BUDGET_POI_ALL = 1_500_000  # placeholder: every POI category
BUDGET_POI_SOME = 750_000  # placeholder: a POI category subset
BUDGET_ADMIN = 100_000  # placeholder: administrative boundaries

#: A road class list that touches any of these needs the "all roads" budget.
MINOR_ROAD_CLASSES = {
    "residential",
    "unclassified",
    "living_street",
    "service",
    "track",
    "road",
    "pedestrian",
    "footway",
    "cycleway",
    "path",
    "steps",
    "bridleway",
}


def tier_budget(tier: dict[str, Any]) -> dict[str, Any]:
    """Per-tile budget for one coverage tier, in bytes plus provenance tags."""
    roads = tier.get("roads", "none")
    if roads == "all":
        roads_bytes, roads_basis = BUDGET_ROADS_ALL, "documented"
    elif roads == "core":
        roads_bytes, roads_basis = BUDGET_ROADS_CORE, "documented"
    elif roads == "none":
        roads_bytes, roads_basis = 0, "documented"
    else:
        classes = {str(name) for name in roads}
        if classes & MINOR_ROAD_CLASSES:
            roads_bytes, roads_basis = BUDGET_ROADS_ALL, "documented (derived: minor classes)"
        else:
            roads_bytes, roads_basis = BUDGET_ROADS_CORE, "documented (derived: core classes)"

    addresses = bool(tier.get("addresses", False))
    if roads == "none" and not addresses:
        refer_bytes, refer_basis = 0, "documented (no names)"
    elif roads == "all" or addresses:
        refer_bytes, refer_basis = BUDGET_REFER_ALL, "placeholder"
    else:
        refer_bytes, refer_basis = BUDGET_REFER_CORE, "placeholder"

    pois = tier.get("pois", "none")
    if pois == "none":
        poi_bytes, poi_basis = 0, "documented (no POIs)"
    elif pois == "all":
        poi_bytes, poi_basis = BUDGET_POI_ALL, "placeholder"
    else:
        poi_bytes, poi_basis = BUDGET_POI_SOME, "placeholder"

    admin_bytes = BUDGET_ADMIN if tier.get("admin_boundaries") else 0
    admin_basis = "placeholder" if admin_bytes else "documented (no boundaries)"

    total = roads_bytes + refer_bytes + poi_bytes + admin_bytes
    return {
        "roads": roads_bytes,
        "refer": refer_bytes,
        "poi": poi_bytes,
        "admin": admin_bytes,
        "per_tile": total,
        "basis": {
            "roads": roads_basis,
            "refer": refer_basis,
            "poi": poi_basis,
            "admin": admin_basis,
        },
    }


def estimate(doc: dict[str, Any], report: profile_validate.Report) -> dict[str, Any]:
    """Size breakdown: resolved tiles x per-tile budget, per tier."""
    tiers = {tier["id"]: tier for tier in doc["coverage"]["tiers"]}
    counts = dict(report.tier_counts)
    rows = []
    total = 0
    for tier_id in sorted(counts):
        budget = tier_budget(tiers[tier_id])
        tile_count = counts[tier_id]
        size = budget["per_tile"] * tile_count
        rows.append(
            {
                "tier": tier_id,
                "tiles": tile_count,
                "per_tile": budget["per_tile"],
                "roads": budget["roads"] * tile_count,
                "refer": budget["refer"] * tile_count,
                "poi": budget["poi"] * tile_count,
                "admin": budget["admin"] * tile_count,
                "total": size,
                "basis": budget["basis"],
            }
        )
        total += size
    tile_count = sum(counts.values())
    return {
        "kind": "estimate",
        "tiles": tile_count,
        "rows": rows,
        "total": total,
        "card_free": CARD_FREE_BYTES,
        "card_use_ratio": (total / CARD_FREE_BYTES) if CARD_FREE_BYTES else 0.0,
        "factory_dense_tile": FACTORY_DENSE_TILE_BYTES,
    }


def print_estimate(payload: dict[str, Any], doc: dict[str, Any], file: Any = None) -> None:
    stream = file or sys.stdout
    print(
        "ESTIMATE (tile count x per-tile budget; NOT a measurement)", file=stream
    )
    print(
        "budget     roads documented (Poland 165 MB / 4 tiles; DS core 1 MB); "
        "refer/poi/admin PLACEHOLDER",
        file=stream,
    )
    print(
        f"{'tier':<12s} {'tiles':>5s} {'roads':>9s} {'refer':>8s} {'poi':>7s} "
        f"{'admin':>7s} {'total':>9s}  basis",
        file=stream,
    )
    for row in payload["rows"]:
        basis = ", ".join(
            f"{name} {kind}" for name, kind in row["basis"].items() if kind != "documented"
        ) or "all documented"
        print(
            f"{row['tier']:<12s} {row['tiles']:5d} "
            f"{row['roads'] / MB:9.2f} {row['refer'] / MB:8.2f} {row['poi'] / MB:7.2f} "
            f"{row['admin'] / MB:7.2f} {row['total'] / MB:9.2f}  {basis}",
            file=stream,
        )
    print(
        f"{'TOTAL':<12s} {payload['tiles']:5d} "
        f"{sum(row['roads'] for row in payload['rows']) / MB:9.2f} "
        f"{sum(row['refer'] for row in payload['rows']) / MB:8.2f} "
        f"{sum(row['poi'] for row in payload['rows']) / MB:7.2f} "
        f"{sum(row['admin'] for row in payload['rows']) / MB:7.2f} "
        f"{payload['total'] / MB:9.2f}",
        file=stream,
    )
    print(
        f"card free  {payload['card_free'] / MB:.0f} MB "
        f"(docs/research/build-profiles.md); this build would use "
        f"{payload['card_use_ratio'] * 100.0:.1f} %",
        file=stream,
    )
    print(
        f"reference  factory dense tile B48R060R is "
        f"{payload['factory_dense_tile'] / MB:.1f} MB "
        f"(docs/format/map-tiles.md) -- ceiling, not a target",
        file=stream,
    )
    print(
        "sources    roads: Poland all-drivable ~165 MB zlib / 4 tiles, core 1.0 MB; "
        "refer/poi/admin: PLACEHOLDER (no measurement yet)",
        file=stream,
    )
    outputs = doc.get("outputs") or {}
    print(
        f"output     {outputs.get('image_name', '<unset>')} "
        f"(manifest={outputs.get('manifest', False)}, verify={outputs.get('verify', False)})",
        file=stream,
    )


def check_limits(payload: dict[str, Any], doc: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    limits = doc.get("limits") or {}
    max_image_bytes = limits.get("max_image_bytes")
    if isinstance(max_image_bytes, int) and payload["total"] > max_image_bytes:
        problems.append(
            f"estimate {payload['total'] / MB:.2f} MB exceeds limits.max_image_bytes "
            f"({max_image_bytes / MB:.2f} MB)"
        )
    min_free_bytes = limits.get("min_free_bytes")
    if isinstance(min_free_bytes, int):
        free = CARD_FREE_BYTES - payload["total"]
        if free < min_free_bytes:
            problems.append(
                f"card free space after the build {free / MB:.2f} MB is below "
                f"limits.min_free_bytes ({min_free_bytes / MB:.2f} MB)"
            )
    return problems


def print_profile_summary(report: profile_validate.Report, file: Any) -> None:
    print(f"profile   {report.path}", file=file)
    print(f"shape     {report.shape or 'unknown'}", file=file)
    print(f"name      {report.name}", file=file)
    if report.region:
        west, south, east, north = report.region
        print(
            f"region    W {west:7.2f}  S {south:6.2f}  E {east:7.2f}  N {north:6.2f}",
            file=file,
        )
    print(
        f"buffer    {report.border_buffer_deg:.2f} deg "
        f"({report.border_buffer_deg * profile_validate.KM_PER_DEG_LAT:.0f} km)",
        file=file,
    )
    tiles = ", ".join(tile["tile"] for tile in report.tiles)
    print(f"tiles     {len(report.tiles)}: {tiles}", file=file)
    for issue in report.warnings:
        print(f"warning   {issue.code} {issue.message}", file=file)


def _load_profile_document(path: str) -> dict[str, Any]:
    """Re-run the normalization so the estimate sees the version-2 document."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict) and profile_validate.detect_shape(raw) == "legacy":
        scratch = profile_validate.Report(path=path)
        return profile_validate.normalize_legacy(raw, scratch)
    return raw


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Exit codes: 0 dry run, 1 invalid profile or limits, 2 usage, "
        "3 writer not implemented.",
    )
    parser.add_argument("--profile", help="profile JSON file to evaluate")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and print the ESTIMATE breakdown without writing anything",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable estimate")
    parser.add_argument("--selftest", action="store_true", help="run synthetic tests")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()

    if not args.dry_run:
        print(
            "error: the ZE0 map writer is not implemented yet; only --dry-run is "
            "available (see TODO.md, 'OSM pipeline and build profiles')",
            file=sys.stderr,
        )
        return EXIT_NOT_IMPLEMENTED
    if not args.profile:
        print("error: --profile is required with --dry-run", file=sys.stderr)
        return EXIT_USAGE

    report = profile_validate.validate_path(args.profile)
    if not report.ok:
        profile_validate.print_report(report, file=sys.stderr)
        return EXIT_INVALID

    doc = _load_profile_document(args.profile)
    payload = estimate(doc, report)
    problems = check_limits(payload, doc)

    if args.json:
        print(
            json.dumps(
                {
                    "ok": not problems,
                    "path": args.profile,
                    "shape": report.shape,
                    "name": report.name,
                    "border_buffer_deg": report.border_buffer_deg,
                    "tiles": report.tiles,
                    "estimate": payload,
                    "problems": problems,
                },
                indent=2,
            )
        )
    else:
        stream = sys.stderr if problems else sys.stdout
        print_profile_summary(report, stream)
        print(file=stream)
        print_estimate(payload, doc, stream)
        for problem in problems:
            print(f"ERROR     limits: {problem}", file=stream)

    return EXIT_INVALID if problems else EXIT_OK


# --------------------------------------------------------------------------
# Selftest
# --------------------------------------------------------------------------


def _v2_profile() -> dict[str, Any]:
    return {
        "version": 2,
        "name": "selftest-build",
        "description": "Synthetic profile used by tools/build.py --selftest.",
        "region": {"bbox": [12.0, 48.0, 20.0, 53.0]},
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
        "border_buffer_deg": 0.0,
        "attribution": {
            "text": "Map data (c) OpenStreetMap contributors, ODbL 1.0",
            "location": "manifest",
        },
        "limits": {},
        "outputs": {"image_name": "selftest-build.img", "manifest": True},
    }


def _write_temp(document: dict[str, Any], directory: str) -> str:
    path = os.path.join(directory, "profile.json")
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(document, stream)
    return path


def selftest() -> int:
    checks = 0
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if condition:
            print(f"  ok   {name}")
        else:
            failures.append(f"{name}: {detail}" if detail else name)
            print(f"  FAIL {name} {detail}".rstrip())

    with tempfile.TemporaryDirectory() as tmp:
        good = _write_temp(_v2_profile(), tmp)
        legacy = _write_temp(
            {
                "name": "selftest-legacy-build",
                "description": "Synthetic legacy profile used by build.py selftest.",
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
            },
            tmp,
        )
        bad = os.path.join(tmp, "bad.json")
        with open(bad, "w", encoding="utf-8") as stream:
            document = _v2_profile()
            document["region"]["bbox"] = [20.0, 53.0, 12.0, 48.0]
            json.dump(document, stream)

        over = os.path.join(tmp, "over.json")
        with open(over, "w", encoding="utf-8") as stream:
            document = _v2_profile()
            document["limits"] = {"max_image_bytes": 1_000_000}
            json.dump(document, stream)

        # 1. Dry run on a valid canonical profile.
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--profile", good, "--dry-run"])
        check("v2 dry run exits 0", code == EXIT_OK, str(code))
        text = out.getvalue()
        check("output is labelled ESTIMATE", "ESTIMATE" in text, text[:200])
        check("roads row is documented", "roads documented" in text)
        check("refer row is a placeholder", "refer placeholder" in text, text)
        check("placeholder sources line", "PLACEHOLDER" in text)

        # 2. Legacy profile: same pipeline, legacy warnings surface.
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--profile", legacy, "--dry-run"])
        check("legacy dry run exits 0", code == EXIT_OK, str(code))
        check("legacy shape reported", "legacy" in out.getvalue())
        check("legacy resolves one tile", "tiles     1:" in out.getvalue(), out.getvalue()[:300])

        # 3. Invalid profile: exit 1, nothing on stdout.
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--profile", bad, "--dry-run"])
        check("invalid profile exits 1", code == EXIT_INVALID, str(code))
        check("invalid profile explains why", "E020" in err.getvalue(), err.getvalue())
        check("invalid profile writes no estimate", "ESTIMATE" not in out.getvalue())

        # 4. Limits are enforced against the estimate.
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main(["--profile", over, "--dry-run"])
        check("over-limit exits 1", code == EXIT_INVALID, str(code))
        check("over-limit names the limit", "max_image_bytes" in err.getvalue(), err.getvalue())

        # 5. Writer is not implemented: exit 3, no output.
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main(["--profile", good])
        check("no --dry-run exits 3", code == EXIT_NOT_IMPLEMENTED, str(code))
        check("writer message on stderr", "not implemented" in err.getvalue())

        # 6. Usage error.
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main(["--dry-run"])
        check("missing --profile exits 2", code == EXIT_USAGE, str(code))

        # 7. Estimate arithmetic: per-tile budgets x tiles.
        report = profile_validate.validate_path(good)
        document = _load_profile_document(good)
        payload = estimate(document, report)
        expected_per_tile = (
            BUDGET_ROADS_ALL + BUDGET_REFER_ALL + BUDGET_POI_ALL + BUDGET_ADMIN
        )
        check(
            "estimate uses documented + placeholder budgets",
            payload["rows"][0]["per_tile"] == expected_per_tile,
            str(payload["rows"][0]["per_tile"]),
        )
        check(
            "estimate multiplies by tile count",
            payload["total"] == expected_per_tile * payload["tiles"],
            str(payload),
        )

        # 8. A core-only tier uses the measured core budget.
        core = tier_budget({"id": "core", "roads": "core", "pois": "none"})
        check("core roads budget is documented", core["roads"] == BUDGET_ROADS_CORE)
        check("no POIs means no POI budget", core["poi"] == 0)
        check("core tier pays the sparse refer budget", core["refer"] == BUDGET_REFER_CORE)

        # 9. A minor-class list falls back to the all-roads budget.
        mixed = tier_budget(
            {"id": "mixed", "roads": ["motorway", "residential"], "pois": ["fuel"]}
        )
        check("minor class list uses all-roads budget", mixed["roads"] == BUDGET_ROADS_ALL)
        check("POI subset uses the some-POI budget", mixed["poi"] == BUDGET_POI_SOME)

    print(f"\nchecks: {checks}, failures: {len(failures)}")
    if failures:
        for failure in failures:
            print(f"  FAILED {failure}")
        return 1
    print("selftest: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
