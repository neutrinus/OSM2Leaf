#!/usr/bin/env python3
"""Build a ZE0 card image from a factory image and OSM, or dry-run a profile.

Two modes:

``--dry-run`` validates the profile, resolves the whole ``BxxRyyR`` tiles it
selects, prints the M5 stage chain and a size ESTIMATE. It writes nothing.

Write mode (M5.15) takes a factory card image, an OSM extract and a profile
and writes a card image, then runs every check and refuses to report success
if one fails::

    factory image --(FAT read)--> factory tree
    OSM --one_tile_pipeline--> tree with one generated tile + rebuilt manifests
    copy of the image --imgpatch (in place, per changed file)--> out.img
    checks: readback, check-diff --strict-metadata, cardcheck --image,
            l2check (incl. --graph-tiles), 7z t, no HDD_CHK.ATT,
            HDD_INFO == factory, [L3 map-code compare with --firmware]

The report lists, per file family, whether it is *generated*, *rebuilt*,
*copied* or *not yet generated (factory kept)*, each check's verdict, the
gates that cannot be decided offline, and the card-ladder step
(``docs/research/card-ladder.md``) the image reaches. First milestone: one
tile, one section-1 directory (the M5.11 path); every new writer adds its
family. A failed build removes the image (``--keep-failed`` keeps it).

The breakdown printed by ``--dry-run`` is an **ESTIMATE**, not a measurement:

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
    python3 tools/build.py --profile profiles/dolnoslaskie-test.json \\
        --from-image FACTORY.img --osm EXTRACT.osm -o out.img \\
        [--factory-root TREE] [--firmware archive/head256.img] [--report r.json]
    python3 tools/build.py --selftest

Exit codes: ``0`` dry run finished / card built and every check PASS, ``1``
profile invalid, over its limits, or a stage/check FAIL, ``2`` usage or I/O
error, ``3`` the request needs a writer that is not implemented (several
tiles, a file added or removed).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import profile_validate  # noqa: E402

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
EXIT_NOT_IMPLEMENTED = 3

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent

MB = 1_000_000

#: The M5 compiler spine, in execution order (TODO.md). ``--dry-run`` prints
#: this plan; write mode runs it for one tile (M5.15).
M5_STAGES: tuple[dict[str, Any], ...] = (
    {
        "id": "osm_ingest",
        "flow": "*.osm.pbf -> IMF v1",
        "tool": "tools/osm_ingest.py",
        "status": "write mode: via one_tile_pipeline.py (M5.15)",
        "implemented": True,
    },
    {
        "id": "mesh_split",
        "flow": "IMF v1 -> whole BxxRyyR tiles",
        "tool": "tools/mesh_split.py",
        "status": "write mode: via one_tile_pipeline.py (M5.15)",
        "implemented": True,
    },
    {
        "id": "tile writer",
        "flow": "tile model -> tile .DAT/.cmp",
        "tool": "tools/tilewriter.py",
        "status": "write mode: one section-1 directory of one tile (M5.11)",
        "implemented": True,
    },
    {
        "id": "manifests",
        "flow": "tiles -> DRSTR/MMAIN/.ind",
        "tool": "tools/rebuild_manifests.py",
        "status": "write mode: via one_tile_pipeline.py (M5.6)",
        "implemented": True,
    },
)

#: The image writer is the rung after the four stages (M5.13, M5.15).
WRITER_STAGE = {
    "id": "card image",
    "flow": "card tree -> <image>.img",
    "tool": "tools/imgpatch.py",
    "status": "write mode: in-place patch of a factory image copy (M5.13/M5.15)",
    "implemented": True,
}

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


def stage_plan() -> list[dict[str, Any]]:
    """The M5 stage chain plus the image writer, as plain dictionaries."""
    return [dict(stage) for stage in M5_STAGES] + [dict(WRITER_STAGE)]


def print_plan(file: Any = None) -> None:
    stream = file or sys.stdout
    print(
        "plan      M5 stage chain (--dry-run executes nothing)",
        file=stream,
    )
    for index, stage in enumerate(M5_STAGES, start=1):
        print(
            f"  {index}  {stage['id']:<12s} {stage['flow']:<30s} {stage['status']}",
            file=stream,
        )
    print(
        f"  -> {WRITER_STAGE['id']:<12s} {WRITER_STAGE['flow']:<30s} "
        f"{WRITER_STAGE['status']}",
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
    for issue in report.notes:
        print(f"note      {issue.code} {issue.message}", file=file)
    for issue in report.warnings:
        print(f"warning   {issue.code} {issue.message}", file=file)


def _load_profile_document(path: str) -> dict[str, Any]:
    """Re-run the normalization so the estimate sees the version-2 document."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict) and profile_validate.detect_shape(raw) == "legacy":
        scratch = profile_validate.Report(path=path)
        return profile_validate.normalize_legacy(raw, scratch)
    return raw


# --------------------------------------------------------------------------
# Write mode (M5.15): factory image + OSM -> card image -> checks
# --------------------------------------------------------------------------

PASS, FAIL, SKIPPED = "PASS", "FAIL", "SKIPPED"
CANNOT_VERIFY = "CANNOT-VERIFY-OFFLINE"

#: Manifests the M5.6 rebuild re-emits; byte-identical when no tile size moves.
MANIFEST_NAMES = ("DRSTR001.DAT", "MMAIN001.DAT", "CMP.LST")

#: The attestation file of the updater path (validation.md, C-2090): a built
#: card must not gain one.
ATTESTATION_NAME = "HDD_CHK.ATT"

#: Families the profile *replaces* but no writer produces yet. The value names
#: the task that adds the writer (reader-coverage.md rows; card-ladder.md).
NOT_YET_GENERATED = {
    "LEV3456R": "M5.16 (levels 3-6 from OSM, blocked on M9.18)",
    "REFER001/POINT": "M5.18 (POINT page builder)",
    "REFER001/ADDRE": "M5.18 (ADDRE writer)",
    "REFER001/INTER": "no writer (reader-coverage row 12)",
    "REFER001/FRWAY": "no writer (reader-coverage row 13)",
    "REFER001/ICADM": "no writer (reader-coverage row 14)",
    "REFER001/ZIPFR": "no writer (reader-coverage row 15)",
    "RDSTM001/RDSTM001": "M3.17 says generate; no writer",
    "RDSTM001/LCTBL001": "M5.17 (LCTBL builder)",
}

#: Families M3.17 keeps verbatim (reader-coverage.md rows 5, 7-9, 24-30).
VERBATIM_COPY = (
    "BICON001", "OPNG", "SPEECH", "TMC", "XMD", "TFTBL001", "REFER002",
    "REFER001/COORD", "REFER001/ZCODE", "REFER001/ICODE",
)


def file_family(rel: str) -> str:
    """Group one card path into the family names used in the report."""
    rel = rel.replace("\\", "/")
    parts = rel.split("/")
    top = parts[0].upper()
    name = parts[-1].upper()
    if len(parts) == 1:
        return name
    if top == "MAPAL001":
        if name.startswith("LEV3456R"):
            return "LEV3456R"
        return "MAPAL001 tile"
    if top == "REFER001":
        if name == "CMP.LST":
            return "CMP.LST"
        if name.endswith(".IND"):
            return "REFER001 .ind"
        return "REFER001/" + name[:5]
    if top == "RDSTM001":
        return "RDSTM001/" + name.split(".")[0]
    if top == "VER_INFO":
        return "VER_INFO"
    return top


def classify_files(files: list[str], changed: set[str], profile_tiles: set[str],
                   tier: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Per-family rows: generated / rebuilt / copied / not yet generated."""
    tier = tier or {}
    asks_names = bool(tier.get("addresses")) or tier.get("pois", "none") != "none"
    rows: dict[str, dict[str, Any]] = {}
    for rel in sorted(files):
        fam = file_family(rel)
        stem = rel.split("/")[-1].split(".")[0].upper()
        key = fam
        if fam == "MAPAL001 tile":
            key = f"MAPAL001 tile {stem}" if stem in profile_tiles else "MAPAL001 tiles outside profile"
        row = rows.setdefault(key, {"family": key, "files": 0, "changed": 0,
                                    "status": "", "note": ""})
        row["files"] += 1
        if rel in changed:
            row["changed"] += 1
    for key, row in rows.items():
        if key.startswith("MAPAL001 tile ") and key != "MAPAL001 tiles outside profile":
            if row["changed"]:
                row["status"] = "generated"
                row["note"] = ("section 1 from OSM (tilewriter, provisional-v0 classes); "
                               "sections 2 and 4 factory")
            else:
                row["status"] = "not yet generated (factory kept)"
                row["note"] = "profile tile, OSM output identical to factory"
        elif key == "MAPAL001 tiles outside profile":
            row["status"] = "copied"
            row["note"] = "outside the profile's tiles"
        elif key in MANIFEST_NAMES or key == "REFER001 .ind":
            row["status"] = "rebuilt" + (" (changed)" if row["changed"] else " (byte-identical)")
            row["note"] = "rebuild_manifests.py (M5.6)"
        elif key == "VER_INFO":
            row["status"] = "copied" + (" (changed!)" if row["changed"] else "")
            row["note"] = "factory HDD_INFO kept: the map-code gate input stays the accepted card's"
        elif key in NOT_YET_GENERATED:
            name_family = key.startswith("REFER001/") or key.startswith("RDSTM001/")
            if name_family and not asks_names and key in ("REFER001/POINT", "REFER001/ADDRE"):
                row["status"] = "copied (profile keeps factory)"
                row["note"] = "profile tier asks no addresses/POIs"
            else:
                row["status"] = "not yet generated (factory kept)"
                row["note"] = NOT_YET_GENERATED[key]
        elif any(key == v or key.startswith(v) for v in VERBATIM_COPY):
            row["status"] = "copied"
            row["note"] = "verbatim-copy set (M3.17)"
        else:
            row["status"] = "copied"
            row["note"] = "no writer; factory bytes"
        if row["changed"] and row["status"].startswith(("copied", "not yet")):
            row["status"] = "UNEXPECTED CHANGE"
    return sorted(rows.values(), key=lambda r: r["family"])


def ladder_step(tile_change: dict[str, Any] | None, families: list[dict[str, Any]]) -> dict[str, str]:
    """Name the card-ladder step (docs/research/card-ladder.md) this card reaches."""
    generated = {row["family"] for row in families if row["status"] == "generated"}
    if any(f.startswith(("REFER001/POINT", "REFER001/ADDRE")) for f in generated):
        return {"step": "P4", "why": "REFER POINT/ADDRE generated"}
    if any(f.startswith("RDSTM001/") for f in generated):
        return {"step": "P3", "why": "names (RDSTM/LCTBL) generated"}
    if "LEV3456R" in generated:
        return {"step": "P2", "why": "LEV3456R generated"}
    tiles = [f for f in generated if f.startswith("MAPAL001 tile ")]
    if not tiles:
        return {"step": "none", "why": "no OSM-generated family: the card is a factory copy"}
    sections = (tile_change or {}).get("changed_sections") or []
    dirs = (tile_change or {}).get("changed_directories") or []
    if 2 in sections:
        return {"step": "P2", "why": "tile section 2 changed"}
    if 4 in sections:
        return {"step": "P3", "why": "tile section 4 changed"}
    if len(dirs) == 1:
        d = dirs[0]
        return {"step": "P0",
                "why": f"one section-1 directory ({d.get('y')},{d.get('x')}) level "
                       f"{d.get('level')} in {len(tiles)} tile"}
    return {"step": "P0+",
            "why": f"{len(dirs)} section-1 directories; P1 needs every directory over the region"}


def derive_parcel(osm_path: Path, level: int) -> tuple[int, int]:
    """The single section-1 directory holding every node of an OSM XML file."""
    import xml.etree.ElementTree as ET
    import one_tile_pipeline

    if osm_path.suffix.lower() == ".pbf":
        raise ValueError("cannot derive --parcel from a .pbf; pass --parcel Y,X")
    dirs: set[tuple[int, int]] = set()
    for _event, elem in ET.iterparse(str(osm_path)):
        if elem.tag == "node" and elem.get("lat") is not None:
            dirs.add(one_tile_pipeline.directory_of(float(elem.get("lon")),
                                                    float(elem.get("lat")), level))
        elem.clear()
    if not dirs:
        raise ValueError(f"{osm_path}: no nodes")
    if len(dirs) != 1:
        raise ValueError(
            f"{osm_path}: nodes span {len(dirs)} section-1 directories "
            f"{sorted(dirs)[:6]}; pass --parcel Y,X --clip (P1, every directory, "
            f"is not implemented)")
    return next(iter(dirs))


def image_files(image: Path) -> dict[str, int]:
    """Every file on the image's map partition -> size (mkcard FAT reader)."""
    import mkcard
    with image.open("rb") as handle:
        _part, geo, fat = mkcard.open_map_partition(handle)
        return {rel: entry.size for rel, entry in mkcard.img_walk_files(handle, geo, fat)}


def image_read(image: Path, rel: str) -> bytes:
    import mkcard
    with image.open("rb") as handle:
        _part, geo, fat = mkcard.open_map_partition(handle)
        return mkcard.img_read(handle, geo, fat, rel)


def extract_tree(image: Path, dest: Path) -> int:
    """Extract the map partition to ``dest`` (stdlib FAT reader). Returns files."""
    import mkcard
    count = 0
    with image.open("rb") as handle:
        _part, geo, fat = mkcard.open_map_partition(handle)
        for rel, entry in mkcard.img_walk_files(handle, geo, fat):
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(mkcard.read_chain(handle, geo, fat, entry.cluster, entry.size))
            count += 1
    return count


def check_factory_root(image: Path, root: Path, cell: str) -> dict[str, Any]:
    """The factory tree is the image's tree: same paths and sizes, same key bytes."""
    import mkcard
    img = image_files(image)
    tree = {rel: (root / rel).stat().st_size for rel in mkcard.collect_tree(root)}
    problems: list[str] = []
    only_img = sorted(set(img) - set(tree))
    only_tree = sorted(set(tree) - set(img))
    if only_img:
        problems.append(f"{len(only_img)} image files missing from the tree: {only_img[:5]}")
    if only_tree:
        problems.append(f"{len(only_tree)} tree files not on the image: {only_tree[:5]}")
    sized = [rel for rel in set(img) & set(tree) if img[rel] != tree[rel]]
    if sized:
        problems.append(f"{len(sized)} files differ in size: {sorted(sized)[:5]}")
    key = [rel for rel in img if rel.upper() in (
        "DRSTR001.DAT", "MMAIN001.DAT", "CMP.LST", "VER_INFO/HDD_INFO.TXT",
        f"MAPAL001/{cell}.DAT")]
    for rel in sorted(key):
        if rel in tree and image_read(image, rel) != (root / rel).read_bytes():
            problems.append(f"{rel}: bytes differ between image and tree")
    return {"id": "factory_root_is_image", "verdict": FAIL if problems else PASS,
            "detail": "; ".join(problems) or
                      f"{len(img)} paths and sizes equal; {len(key)} key files byte-equal",
            "files": len(img)}


def _run(argv: list[str], timeout: int = 7200) -> tuple[int, str]:
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, (proc.stdout + proc.stderr)


def _tail(text: str, lines: int = 12) -> list[str]:
    return text.strip().splitlines()[-lines:]


def default_runner(name: str, ctx: dict[str, Any]) -> tuple[int, str]:
    """Run one external stage or check; ``ctx`` carries the paths."""
    py = sys.executable
    tools = str(TOOLS_DIR)
    if name == "pipeline":
        argv = [py, f"{tools}/one_tile_pipeline.py", "--factory-root", str(ctx["factory_root"]),
                "--cell", ctx["cell"], "--parcel", "%d,%d" % ctx["parcel"],
                "--level", str(ctx["level"]), "--osm", str(ctx["osm"]),
                "--out", str(ctx["tree"]), "--json", str(ctx["pipeline_json"])]
        if ctx.get("clip"):
            argv.append("--clip")
        return _run(argv)
    if name == "cardcheck":
        return _run([py, f"{tools}/cardcheck.py", "--image", str(ctx["out"])])
    if name == "l2check":
        tile = f"{ctx['cell']}.DAT"
        return _run([py, f"{tools}/l2check.py", "--root", str(ctx["tree"]), "--no-golden",
                     "--tiles", tile, "--semantic-tiles", tile, "--cmp-limit", "20",
                     "--graph-tiles", tile, "--graph-factory", str(ctx["factory_root"])])
    if name == "7z":
        if shutil.which("7z") is None:
            return -1, "7z not installed"
        return _run(["7z", "t", str(ctx["out"])])
    if name == "mapcode_l3":
        return _run([py, f"{tools}/l3_harness/runner.py", "run", "applaunch_mapcode_compare",
                     "--image", str(ctx["firmware"]), "--input", str(ctx["hdd_out"]),
                     "--unit-from", str(ctx["hdd_factory"])], timeout=1800)
    raise ValueError(name)


def run_checks(ctx: dict[str, Any], changed: list[str], runner) -> list[dict[str, Any]]:
    """Every check on the written image and its tree, in a fixed order."""
    import imgpatch

    checks: list[dict[str, Any]] = []
    out, image = ctx["out"], ctx["image"]

    bad = []
    for rel in changed:
        try:
            res = imgpatch.verify_image(out, rel, ctx["tree"] / rel)
            if not res["ok"]:
                bad.append(rel)
        except imgpatch.PatchError as exc:
            bad.append(f"{rel}: {exc.message}")
    checks.append({"id": "readback", "verdict": FAIL if bad else PASS,
                   "detail": f"{len(changed)} patched files read back equal" if not bad
                   else f"mismatch: {bad}"})

    if changed:
        diff = imgpatch.check_diff_ranges(out, image, changed, strict_metadata=True)
        ok = bool(diff.get("ok"))
        checks.append({"id": "check_diff", "verdict": PASS if ok else FAIL,
                       "detail": f"diff ranges {diff['diff_range_count']}, bytes "
                                 f"{diff['diff_bytes']}, outside {diff['outside_range_count']}, "
                                 f"unexpected metadata {diff['unexpected_metadata_count']}"})
    else:
        checks.append({"id": "check_diff", "verdict": SKIPPED,
                       "detail": "no file changed; image is a factory copy"})

    rc, text = runner("cardcheck", ctx)
    checks.append({"id": "cardcheck_image", "verdict": PASS if rc == 0 else FAIL,
                   "detail": f"exit {rc}", "tail": _tail(text)})

    rc, text = runner("l2check", ctx)
    checks.append({"id": "l2check_tree", "verdict": PASS if rc == 0 else FAIL,
                   "detail": f"exit {rc}", "tail": _tail(text)})

    rc, text = runner("7z", ctx)
    if rc == -1:
        checks.append({"id": "7z_test", "verdict": SKIPPED, "detail": text})
    else:
        checks.append({"id": "7z_test",
                       "verdict": PASS if rc == 0 and "Everything is Ok" in text else FAIL,
                       "detail": f"exit {rc}", "tail": _tail(text, 6)})

    names = image_files(out)
    att = [rel for rel in names if rel.split("/")[-1].upper() == ATTESTATION_NAME]
    checks.append({"id": "no_attestation_file", "verdict": FAIL if att else PASS,
                   "detail": f"{ATTESTATION_NAME} present: {att}" if att
                   else f"{ATTESTATION_NAME} absent ({len(names)} files)"})

    hdd = "VER_INFO/HDD_INFO.TXT"
    try:
        hdd_out, hdd_fac = image_read(out, hdd), image_read(image, hdd)
        same = hdd_out == hdd_fac
        checks.append({"id": "hdd_info_is_factory", "verdict": PASS if same else FAIL,
                       "detail": f"{len(hdd_out)} B sha256 {hashlib.sha256(hdd_out).hexdigest()[:16]}"
                                 + ("" if same else " differs from the factory card")})
    except (FileNotFoundError, IsADirectoryError) as exc:
        hdd_out = hdd_fac = None
        checks.append({"id": "hdd_info_is_factory", "verdict": FAIL, "detail": f"missing {exc}"})

    if ctx.get("firmware") and hdd_out is not None:
        ctx["hdd_out"] = ctx["work"] / "HDD_INFO.out.TXT"
        ctx["hdd_factory"] = ctx["work"] / "HDD_INFO.factory.TXT"
        ctx["hdd_out"].write_bytes(hdd_out)
        ctx["hdd_factory"].write_bytes(hdd_fac)
        rc, text = runner("mapcode_l3", ctx)
        accept = rc == 0 and "ACCEPT" in text
        checks.append({"id": "mapcode_l3", "verdict": PASS if accept else FAIL,
                       "detail": f"applaunch_mapcode_compare exit {rc} "
                                 f"({'ACCEPT' if accept else 'not ACCEPT'}) under the factory unit record",
                       "tail": _tail(text, 6)})
    else:
        checks.append({"id": "mapcode_l3", "verdict": SKIPPED,
                       "detail": "no --firmware image given"})
    return checks


#: Gates the build cannot decide offline (EXP-2026-11-19-M5.11 gate table).
OFFLINE_GATES = (
    ("tile_reader", "tile reader L3 target BLOCKED (exit 4): no reader entry (M3.6/M9.13)"),
    ("mapdbver_range", "map code check 2: unit MapDBVer bounds unknown, no L3 target"),
    ("sd_lock", "CMD42 lock state is a property of the physical card"),
)


def write_card(args: argparse.Namespace, report: profile_validate.Report,
               doc: dict[str, Any], runner=None) -> tuple[int, dict[str, Any]]:
    """Build ``args.out`` from ``args.from_image`` + ``args.osm``; run every check."""
    runner = runner or default_runner
    image = Path(args.from_image)
    out = Path(args.out)
    osm = Path(args.osm)
    result: dict[str, Any] = {"profile": args.profile, "image": str(image),
                              "osm": str(osm), "out": str(out), "ok": False,
                              "stages": [], "checks": [], "families": []}

    def stage(name: str, verdict: str, detail: str) -> None:
        result["stages"].append({"id": name, "verdict": verdict, "detail": detail})

    if len(report.tiles) != 1:
        stage("profile", FAIL, f"{len(report.tiles)} tiles resolved; write mode builds one tile "
                               f"(first milestone, M5.11); multi-tile is not implemented")
        return EXIT_NOT_IMPLEMENTED, result
    cell = report.tiles[0]["tile"]
    tier_id = report.tiles[0].get("tier")
    tier = next((t for t in doc["coverage"]["tiers"] if t["id"] == tier_id), None)
    result["cell"] = cell

    for path, what in ((image, "--from-image"), (osm, "--osm")):
        if not path.is_file():
            stage("inputs", FAIL, f"{what} {path}: no such file")
            return EXIT_USAGE, result
    if out.exists() and out.resolve() == image.resolve():
        stage("inputs", FAIL, "-o names the factory image")
        return EXIT_USAGE, result
    if out.exists() and not args.force:
        stage("inputs", FAIL, f"-o {out} exists; pass --force to replace it")
        return EXIT_USAGE, result

    try:
        parcel = (one_tile_parse_parcel(args.parcel) if args.parcel
                  else derive_parcel(osm, args.level))
    except ValueError as exc:
        stage("parcel", FAIL, str(exc))
        return EXIT_USAGE, result
    result["parcel"] = list(parcel)
    result["level"] = args.level
    stage("parcel", PASS, f"({parcel[0]},{parcel[1]}) level {args.level}"
                          + (" (given)" if args.parcel else " (derived from the OSM nodes)"))

    work = Path(args.work) if args.work else out.parent / (out.name + ".work")
    if work.exists() and any(work.iterdir()):
        stage("inputs", FAIL, f"--work {work} is not empty")
        return EXIT_USAGE, result
    work.mkdir(parents=True, exist_ok=True)
    result["work"] = str(work)
    tree = work / "tree"
    ctx: dict[str, Any] = {"image": image, "out": out, "osm": osm, "cell": cell,
                           "parcel": parcel, "level": args.level, "clip": args.clip,
                           "work": work, "tree": tree, "pipeline_json": work / "pipeline.json",
                           "firmware": Path(args.firmware) if args.firmware else None}

    def finish(code: int) -> tuple[int, dict[str, Any]]:
        if code != EXIT_OK and out.exists() and result.get("out_written") and not args.keep_failed:
            out.unlink()
            result["out_removed"] = True
        if not args.keep_work:
            shutil.rmtree(work, ignore_errors=True)
        return code, result

    # 1. factory tree: given, or extracted from the image
    if args.factory_root:
        factory_root = Path(args.factory_root)
        prov = check_factory_root(image, factory_root, cell)
        stage("factory_tree", prov["verdict"], f"--factory-root {factory_root}: {prov['detail']}")
        if prov["verdict"] != PASS:
            return finish(EXIT_INVALID)
    else:
        factory_root = work / "factory"
        count = extract_tree(image, factory_root)
        stage("factory_tree", PASS, f"extracted {count} files from the image to {factory_root}")
    ctx["factory_root"] = factory_root

    # 2. OSM -> tile -> tree (one_tile_pipeline: ingest, split, classes, tilewriter, manifests)
    rc, text = runner("pipeline", ctx)
    pipe: dict[str, Any] = {}
    if ctx["pipeline_json"].exists():
        pipe = json.loads(ctx["pipeline_json"].read_text(encoding="utf-8"))
    result["pipeline"] = {k: pipe.get(k) for k in ("counts", "gates", "tile_change", "tree_diff")}
    if rc != 0 or not tree.is_dir():
        stage("pipeline", FAIL, f"one_tile_pipeline exit {rc}: {' | '.join(_tail(text, 4))}")
        return finish(EXIT_INVALID)
    differing = (pipe.get("tree_diff") or {}).get("differing_files")
    if differing is None:
        stage("pipeline", FAIL, "pipeline report has no tree_diff")
        return finish(EXIT_INVALID)
    # one_tile_pipeline._tree_differences states: differs / extra-in-out /
    # missing-from-out / hash-not-compared. Only "differs" can be patched in place.
    unexpected = [(d["path"], d.get("state")) for d in differing if d.get("state") != "differs"]
    if unexpected:
        stage("pipeline", FAIL, f"files not patchable in place: {unexpected}; the in-place "
                                f"writer only replaces existing files (mkcard path not wired)")
        return finish(EXIT_NOT_IMPLEMENTED)
    changed = sorted(d["path"] for d in differing)
    gates = pipe.get("gates") or {}
    failed_gates = [g for g, v in gates.items() if v.get("status") in ("FAIL", "BLOCKED")]
    stage("pipeline", FAIL if failed_gates else PASS,
          f"changed {changed}; pipeline gates " +
          ", ".join(f"{g}={v.get('status')}" for g, v in sorted(gates.items())))
    if failed_gates:
        return finish(EXIT_INVALID)

    # 3. the card: copy the factory image, patch each changed file in place
    import imgpatch
    import mkcard
    if out.exists():
        out.unlink()
    mkcard.copy_image(image, out)
    result["out_written"] = True
    for rel in changed:
        try:
            rep = imgpatch.patch_image(out, rel, tree / rel, allow_resize=args.allow_resize)
        except imgpatch.PatchError as exc:
            stage("patch", FAIL, f"{rel}: {exc.reason}: {exc.message}")
            return finish(EXIT_INVALID)
        if not rep.get("ok"):
            stage("patch", FAIL, f"{rel}: readback mismatch")
            return finish(EXIT_INVALID)
    stage("patch", PASS, f"{len(changed)} files patched in place into a copy of the image")

    # 4. checks
    result["checks"] = run_checks(ctx, changed, runner)
    result["offline_gates"] = [{"id": g, "verdict": CANNOT_VERIFY, "detail": d}
                               for g, d in OFFLINE_GATES]
    for g, v in sorted(gates.items()):
        if v.get("status") in (CANNOT_VERIFY, "NEEDS-L3"):
            result["offline_gates"].append({"id": f"pipeline:{g}", "verdict": v["status"],
                                            "detail": v.get("detail", "")})

    # 5. families and ladder step
    files = sorted(image_files(out))
    result["families"] = classify_files(files, set(changed), {cell}, tier)
    result["ladder"] = ladder_step(pipe.get("tile_change"), result["families"])
    if any(r["status"] == "UNEXPECTED CHANGE" for r in result["families"]):
        result["checks"].append({"id": "families", "verdict": FAIL,
                                 "detail": "a copied family changed"})
    if args.hash:
        result["out_sha256"] = mkcard.sha256_file(out)
    failed = [c["id"] for c in result["checks"] if c["verdict"] == FAIL]
    result["failed_checks"] = failed
    result["ok"] = not failed
    return finish(EXIT_OK if not failed else EXIT_INVALID)


def one_tile_parse_parcel(text: str) -> tuple[int, int]:
    import one_tile_pipeline
    try:
        return one_tile_pipeline.parse_parcel(text)
    except one_tile_pipeline.UsageError as exc:
        raise ValueError(str(exc)) from exc


def print_write_report(result: dict[str, Any], file: Any = None) -> None:
    stream = file or sys.stdout
    print(f"build     {result.get('profile')} -> {result.get('out')}", file=stream)
    print(f"from      {result.get('image')}", file=stream)
    print(f"osm       {result.get('osm')}", file=stream)
    for st in result["stages"]:
        print(f"stage     {st['id']:<14s} {st['verdict']:<5s} {st['detail']}", file=stream)
    if result["families"]:
        print("families  (generated / rebuilt / copied / not yet generated, factory kept)",
              file=stream)
        for row in result["families"]:
            print(f"  {row['family']:<32s} {row['files']:4d} files {row['changed']:3d} changed  "
                  f"{row['status']:<34s} {row['note']}", file=stream)
    for chk in result["checks"]:
        print(f"check     {chk['id']:<20s} {chk['verdict']:<7s} {chk['detail']}", file=stream)
    for gate_row in result.get("offline_gates", []):
        print(f"gate      {gate_row['id']:<32s} {gate_row['verdict']}  {gate_row['detail'][:90]}",
              file=stream)
    if "ladder" in result:
        print(f"ladder    {result['ladder']['step']}  ({result['ladder']['why']})", file=stream)
    if result.get("out_sha256"):
        print(f"sha256    {result['out_sha256']}", file=stream)
    if result.get("ok"):
        print("RESULT: BUILT (every check PASS; gates listed above are not decided offline)",
              file=stream)
    else:
        removed = " (image removed)" if result.get("out_removed") else ""
        failed = result.get("failed_checks") or [
            s["id"] for s in result["stages"] if s["verdict"] == FAIL]
        print(f"RESULT: FAILED {failed}{removed}", file=stream)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Exit codes: 0 dry run / card built with every check PASS, 1 invalid "
        "profile, limits, or a FAIL, 2 usage, 3 needs a writer that is not implemented.",
    )
    parser.add_argument("--profile", help="profile JSON file to evaluate")
    write = parser.add_argument_group("write mode (M5.15)")
    write.add_argument("--from-image", metavar="IMG", help="factory card image (read only)")
    write.add_argument("--osm", metavar="EXTRACT", help="OSM XML/PBF extract (outside the repo)")
    write.add_argument("-o", "--out", metavar="OUT.img", help="card image to write")
    write.add_argument("--factory-root", metavar="DIR",
                       help="already-extracted factory tree of --from-image (checked against "
                            "the image); default: extract it into the work directory")
    write.add_argument("--work", metavar="DIR",
                       help="scratch directory (default OUT.img.work; removed at the end)")
    write.add_argument("--parcel", metavar="Y,X",
                       help="section-1 directory to write; default: the one directory "
                            "holding every OSM node")
    write.add_argument("--level", type=int, choices=(1, 2), default=1,
                       help="section-1 road level (default 1)")
    write.add_argument("--clip", action="store_true",
                       help="drop ways that leave the directory instead of refusing")
    write.add_argument("--firmware", metavar="HEAD_IMG",
                       help="firmware image for the L3 map-code compare (e.g. archive/head256.img)")
    write.add_argument("--allow-resize", action="store_true",
                       help="let imgpatch change a file's cluster count")
    write.add_argument("--force", action="store_true", help="replace an existing -o")
    write.add_argument("--keep-work", action="store_true", help="keep the work directory")
    write.add_argument("--keep-failed", action="store_true",
                       help="keep the image when a check fails (default: remove it)")
    write.add_argument("--hash", action="store_true", help="SHA-256 the written image")
    write.add_argument("--report", metavar="PATH", help="write the build report JSON here")
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

    write_args = (args.from_image, args.osm, args.out)
    if not args.dry_run and not all(write_args):
        print(
            "error: write mode needs --from-image, --osm and -o (or use --dry-run)",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if not args.profile:
        print("error: --profile is required", file=sys.stderr)
        return EXIT_USAGE

    report = profile_validate.validate_path(args.profile)
    if not report.ok:
        profile_validate.print_report(report, file=sys.stderr)
        return EXIT_INVALID

    doc = _load_profile_document(args.profile)
    payload = estimate(doc, report)
    problems = check_limits(payload, doc)

    if not args.dry_run:
        if problems:
            for problem in problems:
                print(f"ERROR     limits: {problem}", file=sys.stderr)
            return EXIT_INVALID
        code, result = write_card(args, report, doc)
        result["exit"] = code
        print_write_report(result, sys.stdout if code == EXIT_OK else sys.stderr)
        if args.report:
            Path(args.report).write_text(json.dumps(result, indent=2, default=str) + "\n",
                                         encoding="utf-8")
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        return code

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
                    "stages": stage_plan(),
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
        print_plan(stream)
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

        # 1b. The dry run prints the M5 stage chain with explicit markers.
        positions = [text.find(stage["id"]) for stage in M5_STAGES]
        check(
            "plan lists the four M5 stages in order",
            all(position >= 0 for position in positions)
            and positions == sorted(positions),
            str(positions),
        )
        check(
            "every M5 stage is marked NOT IMPLEMENTED",
            all(stage["status"] in text for stage in M5_STAGES),
            text,
        )
        check("image writer is marked NOT IMPLEMENTED", WRITER_STAGE["status"] in text)

        # 1c. --json carries the same plan.
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--profile", good, "--dry-run", "--json"])
        check("json dry run exits 0", code == EXIT_OK, str(code))
        payload = json.loads(out.getvalue())
        check(
            "json lists the four stages plus the writer",
            len(payload["stages"]) == len(M5_STAGES) + 1,
            str(len(payload["stages"])),
        )
        check(
            "json stages are flagged implemented (write mode wired)",
            all(stage["implemented"] is True for stage in payload["stages"]),
            str(payload["stages"]),
        )

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

        # 5. Write mode without its inputs: usage error, no output.
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main(["--profile", good])
        check("no --dry-run and no inputs exits 2", code == EXIT_USAGE, str(code))
        check("write-mode message on stderr", "--from-image" in err.getvalue())

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

        # 10. Shipped-profile regression: the resolved counts and ESTIMATE
        #     totals recorded in EXP-2026-11-05-45 must not drift when the
        #     profiles move to schema version 2.
        for name, expected_tiles, expected_total in (
            ("dolnoslaskie-detail.json", 1, 44_600_000),
            ("dolnoslaskie-test.json", 1, 1_500_000),
            ("poland-full.json", 4, 178_400_000),
            ("europe-motorways.json", 56, 253_400_000),
        ):
            path = REPO_ROOT / "profiles" / name
            if not path.exists():
                check(f"shipped {name} estimate", False, "missing")
                continue
            shipped_report = profile_validate.validate_path(str(path), strict=True)
            document = _load_profile_document(str(path))
            shipped_payload = estimate(document, shipped_report)
            check(
                f"shipped {name} strict valid",
                shipped_report.ok,
                str([issue.message for issue in shipped_report.errors]),
            )
            check(
                f"shipped {name} tiles={expected_tiles}",
                shipped_payload["tiles"] == expected_tiles,
                str(shipped_payload["tiles"]),
            )
            check(
                f"shipped {name} total={expected_total / MB:.1f} MB",
                shipped_payload["total"] == expected_total,
                str(shipped_payload["total"]),
            )

    _selftest_write(check)

    print(f"\nchecks: {checks}, failures: {len(failures)}")
    if failures:
        for failure in failures:
            print(f"  FAILED {failure}")
        return 1
    print("selftest: OK")
    return 0



# --------------------------------------------------------------------------
# Write-mode selftest: synthetic FAT32 image, stubbed external checks
# --------------------------------------------------------------------------

SELFTEST_TILE = "MAPAL001/B48R058R.DAT"
SELFTEST_OSM = """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6">
 <node id="1" lat="51.1000" lon="16.9000"/>
 <node id="2" lat="51.1100" lon="16.9400"/>
 <way id="10"><nd ref="1"/><nd ref="2"/><tag k="highway" v="primary"/></way>
</osm>
"""


def _selftest_image(path: Path, att: bool = False) -> None:
    """imgpatch's fixture plus MAPAL001/B48R058R.DAT (and optionally HDD_CHK.ATT)."""
    import imgpatch
    import mkcard

    imgpatch.make_selftest_image(path)
    tile = bytes((i * 7) & 0xFF for i in range(6000))
    with path.open("r+b") as handle:
        _part, geo, fat = mkcard.open_map_partition(handle)
        dir_cluster = mkcard.alloc_clusters(fat, 1, 3)[0]
        need = mkcard.clusters_needed(len(tile), geo.cluster_bytes)
        file_clusters = mkcard.alloc_clusters(fat, need, 3)
        slots = (mkcard.make_short_entry(b".          ", 0x10, dir_cluster, 0)
                 + mkcard.make_short_entry(b"..         ", 0x10, geo.root_cluster, 0)
                 + mkcard.make_short_entry(b"B48R058RDAT", 0x20, file_clusters[0], len(tile)))
        mkcard.write_chain(handle, geo, [dir_cluster], slots)
        mkcard.write_chain(handle, geo, file_clusters, tile)
        root_offset = geo.cluster_offset(geo.root_cluster)
        root = mkcard.read_cluster(handle, geo, geo.root_cluster)
        free = [o for o in range(0, len(root), 32) if root[o] == 0x00]
        handle.seek(root_offset + free[0])
        handle.write(mkcard.make_short_entry(b"MAPAL001   ", 0x10, dir_cluster, 0))
        if att:
            handle.seek(root_offset + free[1])
            handle.write(mkcard.make_short_entry(b"HDD_CHK ATT", 0x20, 0, 0))
        for copy in range(geo.fat_count):
            handle.seek(geo.fat_offset + copy * geo.fat_bytes)
            handle.write(fat)


def _stub_runner(fail: str = "", touch: str = SELFTEST_TILE, state: str = "differs"):
    """A runner whose pipeline flips bytes of ``touch``; ``fail`` names a check to fail."""

    def runner(name: str, ctx: dict[str, Any]) -> tuple[int, str]:
        if name == "pipeline":
            shutil.copytree(ctx["factory_root"], ctx["tree"])
            target = ctx["tree"] / touch
            data = bytearray(target.read_bytes())
            data[100:110] = b"OSM-ROADS!"
            target.write_bytes(bytes(data))
            ctx["pipeline_json"].write_text(json.dumps({
                "gates": {"manifests": {"status": "PASS"},
                          "section4": {"status": CANNOT_VERIFY, "detail": "stub"}},
                "tile_change": {"changed_sections": [1], "changed_directories": [
                    {"level": ctx["level"], "y": ctx["parcel"][0], "x": ctx["parcel"][1]}]},
                "tree_diff": {"differing_files": [{"path": touch, "state": state}]},
            }))
            return 0, "stub pipeline"
        if name == fail:
            return 1, f"stub {name}: FAIL"
        return 0, f"stub {name}: Everything is Ok ACCEPT"

    return runner


def _write_args(**over: Any) -> argparse.Namespace:
    base = dict(profile=str(REPO_ROOT / "profiles" / "dolnoslaskie-test.json"),
                from_image=None, osm=None, out=None, factory_root=None, work=None,
                parcel=None, level=1, clip=False, firmware=None, allow_resize=False,
                force=False, keep_work=False, keep_failed=False, hash=True, report=None)
    base.update(over)
    return argparse.Namespace(**base)


def _selftest_write(check) -> None:
    profile = REPO_ROOT / "profiles" / "dolnoslaskie-test.json"
    report = profile_validate.validate_path(str(profile))
    doc = _load_profile_document(str(profile))
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        img = t / "factory.img"
        _selftest_image(img)
        osm = t / "in.osm"
        osm.write_text(SELFTEST_OSM, encoding="utf-8")
        factory_sha = hashlib.sha256(img.read_bytes()).hexdigest()

        # W1. positive: one changed tile -> image written, every check PASS, P0
        out = t / "out.img"
        code, res = write_card(_write_args(from_image=str(img), osm=str(osm), out=str(out)),
                               report, doc, runner=_stub_runner())
        check("write: positive exits 0", code == EXIT_OK,
              f"{code} {res['stages']} {res.get('checks')}")
        check("write: image written", out.is_file())
        check("write: parcel derived (76,940)", res.get("parcel") == [76, 940], str(res.get("parcel")))
        verdicts = {c["id"]: c["verdict"] for c in res["checks"]}
        for cid in ("readback", "check_diff", "no_attestation_file", "hdd_info_is_factory"):
            check(f"write: {cid} PASS on synthetic image", verdicts.get(cid) == PASS, str(verdicts))
        check("write: mapcode_l3 SKIPPED without --firmware",
              verdicts.get("mapcode_l3") == SKIPPED, str(verdicts))
        fam = {r["family"]: r["status"] for r in res["families"]}
        check("write: tile family generated", fam.get("MAPAL001 tile B48R058R") == "generated", str(fam))
        check("write: HDD_INFO family copied", fam.get("VER_INFO") == "copied", str(fam))
        check("write: ladder P0", res.get("ladder", {}).get("step") == "P0", str(res.get("ladder")))
        check("write: work dir removed", not (t / "out.img.work").exists())
        check("write: factory image untouched",
              hashlib.sha256(img.read_bytes()).hexdigest() == factory_sha)
        tile = image_read(out, SELFTEST_TILE)
        check("write: tile carries the change", tile[100:110] == b"OSM-ROADS!")
        text = io.StringIO()
        print_write_report(res, text)
        check("write: report prints RESULT: BUILT", "RESULT: BUILT" in text.getvalue())

        # W2. a failing check -> exit 1, image removed, RESULT: FAILED
        out2 = t / "out2.img"
        code, res = write_card(_write_args(from_image=str(img), osm=str(osm), out=str(out2)),
                               report, doc, runner=_stub_runner(fail="cardcheck"))
        check("write: failing cardcheck exits 1", code == EXIT_INVALID, str(code))
        check("write: failed image removed", not out2.exists() and res.get("out_removed"))
        text = io.StringIO()
        print_write_report(res, text)
        check("write: failure is not reported as success",
              "RESULT: FAILED" in text.getvalue() and "BUILT" not in text.getvalue(),
              text.getvalue()[-300:])

        # W3. --keep-failed keeps the image
        out3 = t / "out3.img"
        code, _res = write_card(_write_args(from_image=str(img), osm=str(osm), out=str(out3),
                                            keep_failed=True),
                                report, doc, runner=_stub_runner(fail="l2check"))
        check("write: --keep-failed keeps a failed image", code == EXIT_INVALID and out3.exists())

        # W4. a copied family that changes is a FAIL (families check)
        out4 = t / "out4.img"
        code, res = write_card(_write_args(from_image=str(img), osm=str(osm), out=str(out4)),
                               report, doc, runner=_stub_runner(touch="REPORT.BIN"))
        fam = {r["family"]: r["status"] for r in res["families"]}
        check("write: copied family change exits 1",
              code == EXIT_INVALID and fam.get("REPORT.BIN") == "UNEXPECTED CHANGE", str(fam))
        check("write: ladder none when no family is generated",
              res.get("ladder", {}).get("step") == "none", str(res.get("ladder")))

        # W5. a factory tree that is not the image's -> FAIL before any write
        bad_root = t / "badroot"
        extract_tree(img, bad_root)
        (bad_root / "SMALL.BIN").write_bytes(b"y" * 99)
        out5 = t / "out5.img"
        code, res = write_card(_write_args(from_image=str(img), osm=str(osm), out=str(out5),
                                           factory_root=str(bad_root)),
                               report, doc, runner=_stub_runner())
        check("write: mismatched --factory-root exits 1 and writes nothing",
              code == EXIT_INVALID and not out5.exists(), f"{code} {res['stages']}")

        # W6. HDD_CHK.ATT on the source card -> FAIL
        img_att = t / "att.img"
        _selftest_image(img_att, att=True)
        out6 = t / "out6.img"
        code, res = write_card(_write_args(from_image=str(img_att), osm=str(osm), out=str(out6)),
                               report, doc, runner=_stub_runner())
        verdicts = {c["id"]: c["verdict"] for c in res["checks"]}
        check("write: attestation file is a FAIL",
              code == EXIT_INVALID and verdicts.get("no_attestation_file") == FAIL, str(verdicts))

        # W7. guards: -o is the image; existing -o; nodes in two directories
        code, _ = write_card(_write_args(from_image=str(img), osm=str(osm), out=str(img)),
                             report, doc, runner=_stub_runner())
        check("write: -o same as image exits 2", code == EXIT_USAGE, str(code))
        code, _ = write_card(_write_args(from_image=str(img), osm=str(osm), out=str(out3)),
                             report, doc, runner=_stub_runner())
        check("write: existing -o without --force exits 2", code == EXIT_USAGE, str(code))
        wide = t / "wide.osm"
        wide.write_text(SELFTEST_OSM.replace('lon="16.9400"', 'lon="17.6000"'), encoding="utf-8")
        code, res = write_card(_write_args(from_image=str(img), osm=str(wide), out=str(t / "o7.img")),
                               report, doc, runner=_stub_runner())
        check("write: OSM over two directories is refused without --parcel",
              code == EXIT_USAGE and "directories" in res["stages"][-1]["detail"], str(res["stages"]))

        # W7b. a file the pipeline added (state extra-in-out) is not patchable: exit 3
        code, res = write_card(_write_args(from_image=str(img), osm=str(osm), out=str(t / "o7b.img")),
                               report, doc, runner=_stub_runner(state="extra-in-out"))
        check("write: added file exits 3, no image",
              code == EXIT_NOT_IMPLEMENTED and not (t / "o7b.img").exists(), str(res["stages"]))

        # W8. a multi-tile profile is not implemented (exit 3)
        multi = profile_validate.validate_path(str(REPO_ROOT / "profiles" / "poland-full.json"))
        mdoc = _load_profile_document(str(REPO_ROOT / "profiles" / "poland-full.json"))
        code, _ = write_card(_write_args(from_image=str(img), osm=str(osm), out=str(t / "o8.img")),
                             multi, mdoc, runner=_stub_runner())
        check("write: multi-tile profile exits 3", code == EXIT_NOT_IMPLEMENTED, str(code))

    check("family: LEV3456R", file_family("MAPAL001/LEV3456R.DAT") == "LEV3456R")
    check("family: POINT", file_family("REFER001/POINT010.DAT.cmp") == "REFER001/POINT")
    check("family: ind", file_family("REFER001/POINT010.DAT.ind") == "REFER001 .ind")


if __name__ == "__main__":
    raise SystemExit(main())
