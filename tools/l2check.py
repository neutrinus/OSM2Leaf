#!/usr/bin/env python3
"""L2 semantic and golden checks for a Leaf ZE0 map card.

L2 sits above the structural validator (``cardcheck.py``).  It proves that the
tools still understand the data and that a rebuild is faithful:

* ``DRSTR001.DAT`` rebuilt from the tree is byte-identical;
* every ``REFER001`` ``.cmp``/``.ind`` pair survives a preserved-stream
  round-trip byte-identically;
* the five target tiles rebuild byte-identically;
* the decoded geometry of the target tiles matches a stored golden digest;
* a one-vertex tile mutation changes exactly one vertex;
* with ``--graph-tiles``, section 2 decodes to the emitted route graph
  (``tile_graph_roundtrip``, M5.37; ``preserved`` when nothing was emitted);
* with ``--class-tiles``, the level-1 road class the writer emitted decodes
  back unchanged (``tile_class_roundtrip``, M5.36; ``decoded`` census without
  an emitted map, never a PASS);
* every ``BxxRyyyR.DAT`` tile named on the command line lists three sections
  at header ``0x800``/``0x806``/``0x80c`` (``tile_section_list``, M5.62); the
  firmware leaves a tile whose third entry is ``ff ff ff ff`` and goes on in
  box 0 (C-6080–C-6083).  A factory tile kept verbatim, and a short tile
  reached only by the default list (unknown provenance), are INFO, not a
  failure;
* a same-length POI rename passes the offline mutation validator;
* a different-length POI rename passes the offline mutation validator and the
  page re-parses into the same records (one record changed, the rest byte
  identical modulo the shift).

A golden profile for the EU 2011 sample lives in ``tools/golden/eu2011.json``.
Generate or refresh it intentionally with ``--update-golden``; do not update it
just to make a failing run pass.

Usage:
    python3 tools/l2check.py --root /path/to/root
    python3 tools/l2check.py --root /path/to/root --cmp-limit 20 --no-tiles
    python3 tools/l2check.py --root /path/to/root --update-golden tools/golden/eu2011.json
    python3 tools/l2check.py --root /path/to/root --tiles B48R058R.DAT
    python3 tools/l2check.py --selftest

``--tiles``/``--semantic-tiles`` take ``MAPAL001`` **file** names
(``B48R058R.DAT``).  An explicitly requested name that is not a file on the
card is a usage error (exit 2) that names the ``.DAT`` form, because a bare
cell name used to check 0 tiles and still print ``RESULT: PASS`` (C-3566,
M5.39).  The default tile list keeps its skip-with-warning behaviour.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zlib
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cardcheck  # noqa: E402
import cmpind_writer  # noqa: E402
import drstr_ze0  # noqa: E402
import mutate_refer_poi  # noqa: E402
import tile_drop_l3  # noqa: E402

TOOLS = Path(__file__).resolve().parent
VIEWER = TOOLS / "ze0-viewer"
DEFAULT_PROFILE = TOOLS / "golden" / "eu2011.json"
ROUNDTRIP_TILES = [
    "B28R070R.DAT",
    "B30R060R.DAT",
    "B58R070R.DAT",
    "B30R048R.DAT",
    "LEV3456R.DAT",
]
SEMANTIC_TILES = [
    "B28R070R.DAT",
    "B30R060R.DAT",
    "B58R070R.DAT",
    "B30R048R.DAT",
]
LEV_TILE = "LEV3456R.DAT"
REFER_POI = "POINT032.DAT"
REFER_PAGE = 0x4200
REFER_OLD = "VATICAN MUSEUM"
REFER_NEW = "OSM2LEAF PROBE"
REFER_RESIZE_OLD = "VATICAN MUSEUM"
REFER_RESIZE_NEW = "OSM2LEAF PROBE POI"
RESIZE_SUFFIX = " OSM"
CELL_RE = re.compile(r"^(B[0-9A-F]{2}R[0-9A-F]{3}R|LEV3456R)$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# helpers


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def file_info(path: Path) -> dict:
    return {"size": path.stat().st_size, "sha256": sha256_file(path)}


def census(root: Path, ignore_artifacts: bool = False) -> dict:
    files = dirs = total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if not drstr_ze0.is_dump_artifact(d, ignore_artifacts)]
        dirs += len(dirnames)
        for name in filenames:
            if drstr_ze0.is_dump_artifact(name, ignore_artifacts):
                continue
            files += 1
            total += (Path(dirpath) / name).stat().st_size
    return {"files": files, "dirs": dirs, "bytes": total}


def cmp_stats(root: Path) -> dict:
    pairs = logical = stored = 0
    for ind in sorted((root / "REFER001").glob("*.ind")):
        data = ind.read_bytes()
        if len(data) < 16:
            continue
        usize, csize, count, _chunk = struct_unpack_ind(data)
        pairs += 1
        logical += usize
        stored += csize
    return {"pairs": pairs, "logical": logical, "stored": stored}


def struct_unpack_ind(data: bytes):
    import struct
    return struct.unpack_from("<IIII", data, 0)


def mmain_stats(root: Path) -> dict:
    path = root / "MMAIN001.DAT"
    data = path.read_bytes()
    groups = cardcheck.parse_level_table(data)
    rows = sum(len(g["rows"]) for g in groups)
    return {"size": len(data), "sha256": sha256_file(path), "rows": rows}


def _import_viewer():
    if str(VIEWER) not in sys.path:
        sys.path.insert(0, str(VIEWER))
    tools_ze0 = str(VIEWER / "tools_ze0")
    if tools_ze0 not in sys.path:
        sys.path.insert(0, tools_ze0)
    import clarion_tile  # noqa: F401
    import stream_decode  # noqa: F401
    import ze0_tile_io
    return clarion_tile, stream_decode, ze0_tile_io


def feature_sig(feature: dict):
    coords = tuple(
        (round(float(x), 7), round(float(y), 7))
        for x, y in feature["coords"]
    )
    return (
        feature["level"],
        feature["layer"],
        feature["type"],
        bool(feature.get("road")),
        coords,
    )


def feature_digest(features) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    for feature in features:
        sig = feature_sig(feature)
        digest.update(json.dumps(sig, separators=(",", ":")).encode("ascii"))
        digest.update(b"\n")
        count += 1
    return count, digest.hexdigest()


def tile_levels(name: str, include_lev: bool) -> list[int] | None:
    if name == LEV_TILE:
        return [3, 4, 5, 6] if include_lev else None
    return [1, 2]


def load_profile(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# golden generation


def generate_golden(root: Path, image: Path | None, include_lev: bool,
                    ignore_artifacts: bool = False) -> dict:
    profile: dict = {
        "profile_version": 1,
        "sample": "LEAF_2011-2012_QSD-309-101_navi158_eu.img",
        "tree": census(root, ignore_artifacts),
        "drstr": file_info(root / "DRSTR001.DAT"),
        "cmp": cmp_stats(root),
        "mmain": mmain_stats(root),
        "files": {},
        "tiles": {},
    }
    wanted = [
        "MMAIN001.DAT",
        "DRSTR001.DAT",
        "CMP.LST",
        "VER_INFO/HDD_INFO.TXT",
        "REFER002/COORD001.DAT",
        "REFER001/POINT032.DAT.cmp",
        "REFER001/POINT032.DAT.ind",
        "REFER001/ADDRE001.DAT.cmp",
        "REFER001/ADDRE001.DAT.ind",
        "RDSTM001/LCTBL001.DAT",
        "RDSTM001/RDSTM001.DAT",
        "BICON001/BICON001.DAT",
    ] + [f"MAPAL001/{name}" for name in ROUNDTRIP_TILES]
    for rel in wanted:
        path = root / rel
        if path.is_file():
            profile["files"][rel] = file_info(path)

    if image is not None:
        profile["image"] = file_info(image)

    semantic = list(SEMANTIC_TILES)
    if include_lev:
        semantic.append(LEV_TILE)
    try:
        _clarion_tile, stream_decode, _ze0_tile_io = _import_viewer()
    except ImportError as exc:
        profile["viewer_error"] = str(exc)
    else:
        for name in semantic:
            path = root / "MAPAL001" / name
            if not path.is_file():
                continue
            levels = tile_levels(name, include_lev)
            count, digest = feature_digest(
                stream_decode.features(str(path), levels=set(levels or []))
            )
            entry = profile["tiles"].setdefault(name, {})
            entry.update(
                size=path.stat().st_size,
                sha256=sha256_file(path),
                features=count,
                digest=digest,
                levels=levels or [],
            )
    for name in ROUNDTRIP_TILES:
        path = root / "MAPAL001" / name
        if path.is_file():
            profile["tiles"].setdefault(name, {}).update(
                size=path.stat().st_size, sha256=sha256_file(path)
            )
    return profile


# ---------------------------------------------------------------------------
# checks


def check_census(root: Path, profile: dict | None, report: cardcheck.Report,
                  ignore_artifacts: bool = False) -> None:
    check = report.add(cardcheck.Check("census"))
    actual = census(root, ignore_artifacts)
    check.stats.update(actual)
    if profile and "tree" in profile:
        expected = profile["tree"]
        for key in ("files", "dirs", "bytes"):
            if actual.get(key) != expected.get(key):
                check.error(f"{key} {actual.get(key)} != golden {expected.get(key)}")


def check_files(root: Path, profile: dict | None, report: cardcheck.Report) -> None:
    check = report.add(cardcheck.Check("files"))
    if not profile:
        check.stats["skipped"] = "no golden profile"
        return
    files = profile.get("files", {})
    check.stats["expected"] = len(files)
    for rel, expected in sorted(files.items()):
        path = root / rel
        if not path.is_file():
            check.error(f"{rel}: missing")
            continue
        actual = file_info(path)
        if actual["size"] != expected["size"]:
            check.error(f"{rel}: size {actual['size']} != golden {expected['size']}")
        if actual["sha256"] != expected["sha256"]:
            check.error(f"{rel}: sha256 differs from golden")


def check_drstr(root: Path, profile: dict | None, report: cardcheck.Report,
                ignore_artifacts: bool = False, partial: bool = False) -> None:
    check = report.add(cardcheck.Check("drstr_roundtrip"))
    path = root / "DRSTR001.DAT"
    if not path.is_file():
        check.error("DRSTR001.DAT is missing")
        return
    reference = path.read_bytes()
    try:
        built = drstr_ze0.build(root, ignore_dump=ignore_artifacts)
    except (OSError, ValueError) as exc:
        check.error(f"build failed: {exc}")
        return
    check.stats["size"] = len(built)
    if built != reference:
        if partial and not (root / "VER_INFO").is_dir():
            check.warn(
                "partial tree: DRSTR reference lists VER_INFO; "
                "byte-identical rebuild skipped"
            )
            check.stats["skipped"] = "partial VER_INFO"
        else:
            first = next(
                (i for i in range(min(len(built), len(reference))) if built[i] != reference[i]),
                min(len(built), len(reference)),
            )
            check.error(
                f"rebuilt DRSTR differs: {len(built)} vs {len(reference)} bytes, "
                f"first diff 0x{first:x}"
            )
    if profile and "drstr" in profile:
        actual = file_info(path)
        if actual["size"] != profile["drstr"]["size"]:
            check.error("DRSTR size differs from golden")
        if actual["sha256"] != profile["drstr"]["sha256"]:
            check.error("DRSTR sha256 differs from golden")


def check_cmp_roundtrip(root: Path, profile: dict | None,
                        report: cardcheck.Report, limit: int = 0) -> None:
    check = report.add(cardcheck.Check("cmp_roundtrip"))
    directory = root / "REFER001"
    if not directory.is_dir():
        check.error("REFER001 is missing")
        return
    pairs = ok = logical = stored = 0
    with tempfile.TemporaryDirectory(prefix="l2-cmp-") as tmp:
        outdir = Path(tmp)
        for ind in sorted(directory.glob("*.ind")):
            pairs += 1
            stem = ind.name[:-4]
            cmp_path = directory / f"{stem}.cmp"
            try:
                obj = cmpind_writer.CmpFile.from_files(cmp_path, ind)
                logical += obj.usize
                stored += len(obj.cmp_bytes())
                out_cmp, out_ind = obj.write(outdir, stem)
                if out_cmp.read_bytes() == cmp_path.read_bytes() and \
                        out_ind.read_bytes() == ind.read_bytes():
                    ok += 1
                else:
                    check.error(f"{ind.name}: preserved round-trip is not byte-identical")
            except Exception as exc:  # noqa: BLE001 - report every pair
                check.error(f"{ind.name}: {exc}")
            if limit and pairs >= limit:
                break
    check.stats.update(pairs=pairs, ok=ok, logical=logical, stored=stored)
    if pairs == 0:
        check.error("no .ind files found")
    if ok != pairs:
        check.error(f"{pairs - ok} pair(s) failed the preserved round-trip")
    if profile and "cmp" in profile and not limit:
        expected = profile["cmp"]
        for key in ("pairs", "logical", "stored"):
            if check.stats.get(key) != expected[key]:
                check.error(f"{key} {check.stats.get(key)} != golden {expected[key]}")


def check_tile_roundtrip(root: Path, profile: dict | None,
                         report: cardcheck.Report, tiles: list[str]) -> None:
    check = report.add(cardcheck.Check("tile_roundtrip"))
    try:
        clarion_tile, _stream_decode, ze0_tile_io = _import_viewer()
    except ImportError as exc:
        check.error(f"viewer not available: {exc}; run tools/ze0-viewer/setup.sh")
        return
    preserved = 0
    checked = 0
    for name in tiles:
        path = root / "MAPAL001" / name
        if not path.is_file():
            check.warn(f"MAPAL001/{name}: not present on this card; skipped")
            continue
        checked += 1
        try:
            data = path.read_bytes()
            tile = clarion_tile.read_tile(data)
            out = ze0_tile_io.write_tile(tile)
        except Exception as exc:  # noqa: BLE001 - report every tile
            check.error(f"{name}: {exc}")
            continue
        if tile.get("_preserved"):
            preserved += 1
            check.warn(f"{name}: unchanged tile uses preserved layout")
        if out != data:
            first = next((i for i in range(min(len(out), len(data))) if out[i] != data[i]),
                         min(len(out), len(data)))
            check.error(f"{name}: rebuild differs at 0x{first:x}")
        if profile and name in profile.get("tiles", {}):
            expected = profile["tiles"][name]
            if len(data) != expected.get("size"):
                check.error(f"{name}: size {len(data)} != golden {expected.get('size')}")
            if sha256_file(path) != expected.get("sha256"):
                check.error(f"{name}: sha256 differs from golden")
    check.stats["tiles"] = checked
    check.stats["preserved"] = preserved
    if checked == 0:
        check.warn("none of the requested tiles are present on this card")


def check_tile_semantic(root: Path, profile: dict | None,
                        report: cardcheck.Report, tiles: list[str],
                        include_lev: bool) -> None:
    check = report.add(cardcheck.Check("tile_semantic"))
    try:
        _clarion_tile, stream_decode, _ze0_tile_io = _import_viewer()
    except ImportError as exc:
        check.error(f"viewer not available: {exc}; run tools/ze0-viewer/setup.sh")
        return
    checked = 0
    for name in tiles:
        path = root / "MAPAL001" / name
        if not path.is_file():
            check.warn(f"MAPAL001/{name}: not present on this card; skipped")
            continue
        checked += 1
        levels = tile_levels(name, include_lev)
        if levels is None:
            continue
        try:
            count, digest = feature_digest(
                stream_decode.features(str(path), levels=set(levels))
            )
        except Exception as exc:  # noqa: BLE001
            check.error(f"{name}: decode failed: {exc}")
            continue
        check.stats[name] = {"features": count, "digest": digest}
        if profile and name in profile.get("tiles", {}):
            expected = profile["tiles"][name]
            if count != expected.get("features"):
                check.error(
                    f"{name}: {count} features != golden {expected.get('features')}"
                )
            if digest != expected.get("digest"):
                check.error(f"{name}: geometry digest differs from golden")


def check_tile_graph(root: Path, report: cardcheck.Report, tiles: list[str],
                     emitted: Path | None, factory_root: Path | None) -> None:
    """M5.37: section 2 decodes to the node/link graph the writer emitted.

    Verdicts per tile come from ``tools/tile_graph_roundtrip.py``: ``PASS``
    (every emitted record decodes to its emitted framing, every other record
    byte-identical to the factory), ``preserved`` (no emitted record, section 2
    identical to the factory: a preservation result, never a graph match) or
    ``FAIL``."""
    check = report.add(cardcheck.Check("tile_graph_roundtrip"))
    import tile_graph_roundtrip as tgr  # noqa: PLC0415
    graph = tgr.load_graph(emitted) if emitted else None
    for name in tiles:
        path = root / "MAPAL001" / name
        if not path.is_file():
            check.error(f"MAPAL001/{name}: not present on this card")
            continue
        ref = factory_root / "MAPAL001" / name if factory_root else None
        if ref is not None and not ref.is_file():
            check.error(f"factory MAPAL001/{name}: not present")
            continue
        res = tgr.check_tile(path, graph, ref)
        check.stats[name] = (f"{res['verdict']} match={res['match']} "
                             f"preserved={res['preserved']} changed={res['changed']}")
        if res["verdict"] == "preserved":
            check.warn(f"{name}: section 2 preserved; no emitted graph checked")
        elif res["verdict"] != "PASS":
            for err in res["errors"][:5]:
                check.error(f"{name}: {err}")
            check.error(f"{name}: tile_graph_roundtrip {res['verdict']}")


def check_tile_class(root: Path, report: cardcheck.Report, tiles: list[str],
                     emitted: Path | None) -> None:
    """M5.36: the road class the writer emitted decodes back unchanged.

    Verdicts per tile come from ``tools/tile_class_roundtrip.py``: ``PASS``
    when every emitted ``(layer, cls)`` list is decoded from the tile exactly,
    ``FAIL`` on a one-value mismatch, a missing record or an empty map.  With
    no emitted map the check decodes the tile's class rows and says
    ``decoded`` in its stats: a census, never a PASS."""
    check = report.add(cardcheck.Check("tile_class_roundtrip"))
    import tile_class_roundtrip as tcr  # noqa: PLC0415
    explicit = tcr.load_expected(emitted) if emitted else None
    for name in tiles:
        path = root / "MAPAL001" / name
        if not path.is_file():
            check.error(f"MAPAL001/{name}: not present on this card")
            continue
        expected = explicit
        if expected is None:
            side = path.with_name(path.name + ".class.json")
            if side.is_file():
                expected = tcr.load_expected(side)
        res = tcr.check_tile(path, expected)
        check.stats[name] = (f"{res['verdict']} records={res['records']} "
                             f"shapes={res['shapes']} match={res['match']} "
                             f"fail={res['fail']} missing={res['missing']}")
        if res["verdict"] == "decoded":
            check.warn(f"{name}: no emitted class map; decoded {res['records']} "
                       f"record(s) as a census, no round-trip claim")
        elif res["verdict"] != "PASS":
            for err in res["errors"][:5]:
                check.error(f"{name}: {err}")
            check.error(f"{name}: tile_class_roundtrip {res['verdict']}")


def check_tile_section_list(root: Path, report: cardcheck.Report,
                            tiles: list[str],
                            factory_root: Path | None,
                            explicit: set[str]) -> None:
    """M5.62: a generated ``BxxRyyyR.DAT`` must list three sections at 0x800.

    The firmware's header check (`0x0040acb8`, EU2011) asks every tile box for
    parts 0, 1 and 2, reading the 6-byte section-list entries at header
    `0x800`, `0x806` and `0x80c`; an entry `ff ff ff ff` with the tile not yet
    mounted sets box status 3, the tile is left after its header and the mount
    goes on in box 0 (C-6080–C-6083).  L2 never said so (a writer that dropped
    an empty section passed every gate).

    A tile named on the command line (``--tiles``/``--semantic-tiles``/
    ``--class-tiles``) is a generated target and held to the rule.  A short
    list that is factory bytes kept verbatim — the run's ``--factory-root``
    MAPAL001 file with the same name, byte-identical — is INFO, not a failure
    (8 of 45 factory tiles have fewer, C-6085).  A tile reached only through
    the default list has unknown provenance and is INFO too: a raw factory
    card sweep must not fail on the firmware's own files.  ``LEV3456R.DAT``
    lists two by design and is out of scope."""
    check = report.add(cardcheck.Check("tile_section_list"))
    short = factory_kept = unnamed = checked = 0
    for name in tiles:
        if name.upper() == LEV_TILE:
            continue
        path = root / "MAPAL001" / name
        if not path.is_file():
            check.warn(f"MAPAL001/{name}: not present on this card; skipped")
            continue
        checked += 1
        try:
            raw = path.read_bytes()
        except OSError as exc:
            check.error(f"{name}: {exc}")
            continue
        entries = tile_drop_l3.parse_section_list(
            raw[tile_drop_l3.SECT_OFF:tile_drop_l3.SECT_OFF + 18], 3)
        check.stats[name] = len(entries)
        if len(entries) >= 3:
            continue
        short += 1
        reference = factory_root / "MAPAL001" / name if factory_root else None
        if reference is not None and reference.is_file() and \
                reference.read_bytes() == raw:
            factory_kept += 1
            check.warn(f"{name}: {len(entries)} section entries, factory bytes "
                       f"kept verbatim (INFO, not a failure)")
            continue
        if name not in explicit:
            unnamed += 1
            check.warn(f"{name}: {len(entries)} section entries, not a named "
                       f"generated target (INFO; pass --tiles to enforce)")
            continue
        missing = ", ".join(f"0x{tile_drop_l3.SECT_OFF + 6 * i:03x}"
                            for i in range(len(entries), 3))
        check.error(
            f"{name}: section list has {len(entries)} entr"
            f"{'y' if len(entries) == 1 else 'ies'} at 0x800; the firmware "
            f"leaves the tile without three (entries {missing} are ff ff ff ff)"
        )
    check.stats["checked"] = checked
    check.stats["short"] = short
    check.stats["factory_verbatim"] = factory_kept
    check.stats["unnamed"] = unnamed


def check_tile_mutation(root: Path, report: cardcheck.Report,
                        tile: str = "B30R060R.DAT") -> None:
    check = report.add(cardcheck.Check("tile_mutation"))
    src = root / "MAPAL001" / tile
    if not src.is_file():
        check.warn(f"MAPAL001/{tile}: not present on this card; skipped")
        check.stats["skipped"] = "tile missing"
        return
    try:
        clarion_tile, stream_decode, _ze0_tile_io = _import_viewer()
    except ImportError as exc:
        check.error(f"viewer not available: {exc}; run tools/ze0-viewer/setup.sh")
        return
    with tempfile.TemporaryDirectory(prefix="l2-tile-") as tmp:
        dst = Path(tmp) / tile
        proc = subprocess.run(
            [sys.executable, str(VIEWER / "ze0_mutate.py"), str(src), str(dst),
             "--level", "1", "--dx", "1"],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            check.error(f"ze0_mutate.py failed: {proc.stderr.strip() or proc.stdout.strip()}")
            return
        data = dst.read_bytes()
        try:
            if clarion_tile.write_tile(clarion_tile.read_tile(data)) != data:
                check.error("mutated tile does not round-trip")
        except Exception as exc:  # noqa: BLE001
            check.error(f"mutated tile round-trip failed: {exc}")
            return
        before = Counter(feature_sig(f) for f in
                         stream_decode.features(str(src), levels={1, 2}))
        after = Counter(feature_sig(f) for f in
                        stream_decode.features(str(dst), levels={1, 2}))
        removed = list((before - after).elements())
        added = list((after - before).elements())
        check.stats.update(removed=len(removed), added=len(added))
        if len(removed) != 1 or len(added) != 1:
            check.error(
                f"expected one removed and one added feature, got "
                f"{len(removed)} and {len(added)}"
            )
            return
        a, b = removed[0], added[0]
        if a[:4] != b[:4]:
            check.error("mutated feature changed level/layer/type/road")
            return
        if len(a[4]) != len(b[4]):
            check.error("mutated feature changed vertex count")
            return
        changed = sum(1 for p, q in zip(a[4], b[4]) if p != q)
        max_delta = max((max(abs(p[0] - q[0]), abs(p[1] - q[1]))
                         for p, q in zip(a[4], b[4])), default=0.0)
        check.stats.update(changed_vertices=changed, max_delta=max_delta)
        if changed != 1:
            check.error(f"expected one changed vertex, got {changed}")
        if max_delta <= 0:
            check.error("mutated vertex did not move")


def _refer_blob(cmp_path: Path) -> bytes:
    obj = cmpind_writer.CmpFile.from_files(cmp_path, cmp_path.with_suffix(".ind"))
    return obj.decode()


def _inner_page(blob: bytes, page: int) -> tuple[bytes, int] | None:
    try:
        dec = zlib.decompressobj()
        inner = dec.decompress(blob[page:])
        used = len(blob[page:]) - len(dec.unused_data)
    except zlib.error:
        return None
    return inner, used


def _refer_candidate(inner: bytes, page: int, used: int,
                     start: int, old: str):
    """Return a same-length replacement that still fits the next page."""
    old_b = old.encode("latin-1")
    limit = (page + used + 0xFF) & ~0xFF
    for ch in "XYZ0123456789":
        if ch == old[-1]:
            continue
        new = old[:-1] + ch
        new_b = new.encode("latin-1")
        if len(new_b) != len(old_b):
            continue
        new_inner = inner[:start] + new_b + inner[start + len(old_b):]
        new_stream = zlib.compress(new_inner, 6)
        if page + len(new_stream) <= limit:
            return old, new
    return None


def find_refer_fixture(root: Path):
    """Find a same-length POI rename that works on this year.

    The 2011 page 0x4200/``VATICAN MUSEUM`` fixture is tried first.  Other
    years use a deterministic scan of ``POINT*.DAT.cmp`` inner pages for a
    unique printable run, then replace its last character.
    """
    known = root / "REFER001" / f"{REFER_POI}.cmp"
    if known.is_file():
        try:
            blob = _refer_blob(known)
            page = _inner_page(blob, REFER_PAGE)
            if page is not None:
                inner, used = page
                old_b = REFER_OLD.encode("latin-1")
                new_b = REFER_NEW.encode("latin-1")
                if inner.count(old_b) == 1:
                    limit = (REFER_PAGE + used + 0xFF) & ~0xFF
                    new_inner = inner.replace(old_b, new_b, 1)
                    if len(new_b) == len(old_b) and \
                            REFER_PAGE + len(zlib.compress(new_inner, 6)) <= limit:
                        return REFER_POI, REFER_PAGE, REFER_OLD, REFER_NEW, max(0x1000, used)
                    fit = _refer_candidate(inner, REFER_PAGE, used, inner.find(old_b), REFER_OLD)
                    if fit is not None:
                        return REFER_POI, REFER_PAGE, fit[0], fit[1], max(0x1000, used)
        except (OSError, ValueError):
            pass

    for cmp_path in sorted((root / "REFER001").glob("POINT*.DAT.cmp")):
        try:
            blob = _refer_blob(cmp_path)
        except (OSError, ValueError):
            continue
        pos = 0
        while True:
            page = blob.find(b"\x78\x9c", pos)
            if page < 0:
                break
            parsed = _inner_page(blob, page)
            if parsed is None:
                pos = page + 2
                continue
            inner, used = parsed
            for match in re.finditer(rb"[ -~]{8,}", inner):
                old = match.group().decode("latin-1").strip()
                if len(old) < 8 or len(old) > 80:
                    continue
                if sum(ch.isalnum() for ch in old) < 6:
                    continue
                old_b = old.encode("latin-1")
                if inner.count(old_b) != 1:
                    continue
                fit = _refer_candidate(inner, page, used, match.start(), old)
                if fit is None:
                    continue
                return (
                    cmp_path.name[:-4],
                    page,
                    fit[0],
                    fit[1],
                    max(0x1000, used),
                )
            pos = page + max(used, 2)
    return None


def check_refer_mutation(root: Path, report: cardcheck.Report) -> None:
    check = report.add(cardcheck.Check("refer_mutation"))
    fixture = find_refer_fixture(root)
    if fixture is None:
        check.warn("no same-length REFER001 fixture found for this year")
        check.stats["skipped"] = "no fixture"
        return
    name, page, old, new, page_len = fixture
    check.stats.update(file=name, page=hex(page), old=old, new=new)
    cmp_path = root / "REFER001" / f"{name}.cmp"
    ind_path = root / "REFER001" / f"{name}.ind"
    drstr_path = root / "DRSTR001.DAT"
    if not cmp_path.is_file() or not ind_path.is_file():
        check.error(f"{name}.cmp/.ind is missing")
        return
    with tempfile.TemporaryDirectory(prefix="l2-refer-") as tmp:
        outdir = Path(tmp) / "mut"
        proc = subprocess.run(
            [sys.executable, str(TOOLS / "mutate_refer_poi.py"),
             str(cmp_path), str(ind_path), str(outdir),
             "--page", hex(page), "--old", old, "--new", new],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            check.error(f"mutate_refer_poi.py failed: {proc.stderr.strip() or proc.stdout.strip()}")
            return
        proc = subprocess.run(
            [sys.executable, str(TOOLS / "validate_mutation.py"),
             str(root / "REFER001"), str(outdir), name,
             "--page", hex(page), "--page-len", hex(max(page_len, 0x300)),
             "--drstr", str(drstr_path), "--drstr-dir", "REFER001",
             "--inner-page", hex(page)],
            capture_output=True, text=True,
        )
        check.stats["validate"] = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        if proc.returncode != 0 or "PASS" not in proc.stdout:
            check.error(f"validate_mutation.py failed: {proc.stderr.strip() or proc.stdout.strip()}")


def _page_gap(page: int, used: int) -> int:
    """Bytes reserved for the stream, up to the next 0x100-aligned offset."""
    return ((page + used + 0xFF) & ~0xFF) - page


def _page_records(inner: bytes) -> list[dict] | None:
    try:
        return mutate_refer_poi.parse_page(inner)
    except mutate_refer_poi.PageError:
        return None


def _expected_resize_record(before: bytes, hit: int, old_b: bytes,
                            new: str | bytes, delta: int) -> bytes:
    """Expected record bytes after an M5.52 ``--resize``.

    The rename moves the text and patches two bytes: the record length byte
    (``len2``) and, since M5.52 (``608f949``), the field-5 length byte (the
    name, in 16-bit words) because the firmware accessor places field 5 from
    it (C-5115/C-5117).  A rename-only expectation (only ``len2`` patched)
    was the pre-M5.52 edit and no longer matches what the tool writes.

    Raises :class:`mutate_refer_poi.PageError` when the pre-mutation record's
    field 5 cannot be placed.
    """
    _start, words, layout = mutate_refer_poi.name_field(before)
    length_at = layout["loc"] + mutate_refer_poi.NAME_FIELD
    new_b = new.encode("latin-1") if isinstance(new, str) else new
    new_total = len(before) + delta
    return (
        before[:1]
        + bytes([new_total // 2])
        + before[2:length_at]
        + bytes([words + delta // 2])
        + before[length_at + 1:hit]
        + new_b
        + before[hit + len(old_b):]
    )


def _resize_candidate(inner: bytes, page: int, used: int,
                      old: str, new: str) -> tuple[str, str] | None:
    """Return ``(old, new)`` when the rename parses and fits the page."""
    old_b, new_b = old.encode("latin-1"), new.encode("latin-1")
    if not old_b or len(old_b) == len(new_b):
        return None
    if inner.count(old_b) != 1:
        return None
    try:
        new_inner, _info = mutate_refer_poi.resize_name(inner, old_b, new_b)
    except mutate_refer_poi.PageError:
        return None
    if page + len(zlib.compress(new_inner, 6)) > page + _page_gap(page, used):
        return None
    return old, new


def find_resize_fixture(root: Path):
    """Find a POI name page where a different-length rename fits.

    The 2011 ``POINT032`` page ``0x4200`` fixture is tried first; other years
    fall back to a deterministic scan of POINT name pages for a unique
    printable string and append an even-length suffix.
    """
    known = root / "REFER001" / f"{REFER_POI}.cmp"
    if known.is_file():
        try:
            blob = _refer_blob(known)
            parsed = _inner_page(blob, REFER_PAGE)
            if parsed is not None:
                inner, used = parsed
                fit = _resize_candidate(
                    inner, REFER_PAGE, used, REFER_RESIZE_OLD, REFER_RESIZE_NEW
                )
                if fit is not None:
                    return (
                        REFER_POI,
                        REFER_PAGE,
                        fit[0],
                        fit[1],
                        _page_gap(REFER_PAGE, used),
                    )
        except (OSError, ValueError):
            pass

    for cmp_path in sorted((root / "REFER001").glob("POINT*.DAT.cmp")):
        if cmp_path == known:
            continue
        try:
            blob = _refer_blob(cmp_path)
        except (OSError, ValueError):
            continue
        pos = 0
        while True:
            page = blob.find(b"\x78\x9c", pos)
            if page < 0:
                break
            parsed = _inner_page(blob, page)
            if parsed is None:
                pos = page + 2
                continue
            inner, used = parsed
            records = _page_records(inner)
            if records is not None:
                for record in records:
                    for match in re.finditer(rb"[ -~]{8,60}\x00", record["bytes"]):
                        old = match.group()[:-1].decode("latin-1")
                        if sum(ch.isalpha() for ch in old) < 4:
                            continue
                        new = old + RESIZE_SUFFIX
                        fit = _resize_candidate(inner, page, used, old, new)
                        if fit is not None:
                            return (
                                cmp_path.name[:-4],
                                page,
                                fit[0],
                                fit[1],
                                _page_gap(page, used),
                            )
            pos = page + max(used, 2)
    return None


def check_refer_rename_resize(root: Path, report: cardcheck.Report) -> None:
    """Mutate a POI name to a different length and prove the page still parses."""
    check = report.add(cardcheck.Check("refer_rename_resize"))
    fixture = find_resize_fixture(root)
    if fixture is None:
        check.warn("no different-length REFER001 fixture found for this year")
        check.stats["skipped"] = "no fixture"
        return
    name, page, old, new, page_len = fixture
    delta = len(new) - len(old)
    check.stats.update(file=name, page=hex(page), old=old, new=new, delta=delta)
    cmp_path = root / "REFER001" / f"{name}.cmp"
    ind_path = root / "REFER001" / f"{name}.ind"
    drstr_path = root / "DRSTR001.DAT"
    if not cmp_path.is_file() or not ind_path.is_file():
        check.error(f"{name}.cmp/.ind is missing")
        return
    with tempfile.TemporaryDirectory(prefix="l2-refer-resize-") as tmp:
        outdir = Path(tmp) / "mut"
        proc = subprocess.run(
            [sys.executable, str(TOOLS / "mutate_refer_poi.py"),
             str(cmp_path), str(ind_path), str(outdir),
             "--page", hex(page), "--resize", "--old", old, "--new", new],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            check.error(
                f"mutate_refer_poi.py --resize failed: "
                f"{proc.stderr.strip() or proc.stdout.strip()}"
            )
            return
        proc = subprocess.run(
            [sys.executable, str(TOOLS / "validate_mutation.py"),
             str(root / "REFER001"), str(outdir), name,
             "--page", hex(page), "--page-len", hex(page_len),
             "--drstr", str(drstr_path), "--drstr-dir", "REFER001",
             "--inner-page", hex(page)],
            capture_output=True, text=True,
        )
        check.stats["validate"] = (
            proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        )
        if proc.returncode != 0 or "PASS" not in proc.stdout:
            check.error(
                f"validate_mutation.py failed: "
                f"{proc.stderr.strip() or proc.stdout.strip()}"
            )
            return

        # Independent record-level check: the page must still be a record
        # chain with the same record count, exactly one changed record, and
        # every other record byte-identical after the shift.
        try:
            old_blob = _refer_blob(cmp_path)
            new_blob = (outdir / name).read_bytes()
        except (OSError, ValueError) as exc:
            check.error(f"cannot reload the mutated pair: {exc}")
            return
        old_page = _inner_page(old_blob, page)
        new_page = _inner_page(new_blob, page)
        if old_page is None or new_page is None:
            check.error("inner page does not inflate after the mutation")
            return
        old_records = _page_records(old_page[0])
        new_records = _page_records(new_page[0])
        if old_records is None or new_records is None:
            check.error("page is not a record chain before or after the mutation")
            return
        check.stats["records"] = len(new_records)
        if len(new_records) != len(old_records):
            check.error(
                f"record count changed {len(old_records)} -> {len(new_records)}"
            )
            return
        changed = [
            index
            for index, (before, after) in enumerate(zip(old_records, new_records))
            if before["bytes"] != after["bytes"]
        ]
        old_b = old.encode("latin-1")
        renamed = [
            index for index, record in enumerate(old_records)
            if old_b in record["bytes"]
        ]
        check.stats["changed_records"] = len(changed)
        if len(renamed) != 1:
            check.error(f"old text occurs in {len(renamed)} records; need exactly 1")
            return
        if changed != renamed:
            check.error(
                f"expected exactly record {renamed[0]} to change, got {changed}"
            )
            return
        record = new_records[changed[0]]
        before = old_records[changed[0]]["bytes"]
        after = record["bytes"]
        hit = before.find(old_b)
        if hit < 2:
            check.error("old text is not in the header-free part of the record")
            return
        new_total = len(before) + delta
        # M5.52 (608f949): --resize also patches the field-5 length byte; the
        # expected record therefore includes that patch (see the helper).
        try:
            expected = _expected_resize_record(before, hit, old_b, new, delta)
        except mutate_refer_poi.PageError as exc:
            check.error(f"record {changed[0]} field 5 cannot be placed: {exc}")
            return
        if after != expected:
            check.error(
                f"record {changed[0]} is not the M5.52 rename+field-5 edit "
                f"(got {len(after)} bytes, expected {new_total})"
            )
            return
        if record["total"] != new_total:
            check.error(
                f"record {changed[0]} is {record['total']} bytes, "
                f"expected {new_total}"
            )


def check_image(image: Path | None, profile: dict | None,
                report: cardcheck.Report) -> None:
    check = report.add(cardcheck.Check("image"))
    if image is None:
        check.stats["skipped"] = "no --image"
        return
    if not image.is_file():
        check.error(f"{image}: missing")
        return
    actual = file_info(image)
    check.stats.update(actual)
    if profile and "image" in profile:
        expected = profile["image"]
        if actual["size"] != expected["size"]:
            check.error(f"image size {actual['size']} != golden {expected['size']}")
        if actual["sha256"] != expected["sha256"]:
            check.error("image sha256 differs from golden")


# ---------------------------------------------------------------------------
# requested tile names (M5.39, C-3566)


def split_tiles(value: str) -> list[str]:
    return [t.strip() for t in value.split(",") if t.strip()]


def missing_tile_requests(root: Path, option: str, names: list[str]) -> list[str]:
    """Usage errors for explicitly requested tiles that are not files on the card.

    A bare cell name (``B48R058R``) gets the ``.DAT`` file name to use, so the
    caller cannot read ``tiles=0`` + ``RESULT: PASS`` as a passing tile gate.
    """
    problems = []
    for name in names:
        if (root / "MAPAL001" / name).is_file():
            continue
        msg = f"{option} {name}: MAPAL001/{name} is not a file on this card"
        if CELL_RE.match(name):
            msg += (f"; tile names are file names: use {option} {name}.DAT"
                    + ("" if (root / "MAPAL001" / f"{name}.DAT").is_file()
                       else f" (MAPAL001/{name}.DAT is not present either)"))
        problems.append(msg)
    return problems


# ---------------------------------------------------------------------------
# CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", help="extracted card root (required unless --selftest)")
    parser.add_argument("--selftest", action="store_true",
                        help="run the vendor-free self-test and exit")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE),
                        help="golden profile (default: tools/golden/eu2011.json)")
    parser.add_argument("--json", help="write a JSON report to this path")
    parser.add_argument("--json-only", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-golden", action="store_true",
                        help="skip all profile comparisons")
    parser.add_argument("--ignore-dump-artifacts", action="store_true",
                        help="ignore macOS ._*, .fseventsd, System Volume Information")
    parser.add_argument("--partial", action="store_true",
                        help="map-only tree without VER_INFO")
    parser.add_argument("--cmp-limit", type=int, default=0,
                        help="check only the first N .cmp pairs (0 = all)")
    parser.add_argument("--no-cmp", action="store_true")
    parser.add_argument("--no-tiles", action="store_true")
    parser.add_argument("--tiles", default=None,
                        help="comma-separated MAPAL001 file names for the round-trip "
                             "check, e.g. B48R058R.DAT (default: the five target "
                             "tiles, skipped with a warning when absent); an "
                             "explicit name that is not a file is exit 2")
    parser.add_argument("--semantic-tiles", default=None,
                        help="comma-separated MAPAL001 file names for the geometry "
                             "digest (default: the four target cells); an explicit "
                             "name that is not a file is exit 2")
    parser.add_argument("--include-lev", action="store_true",
                        help="also decode LEV3456R (slow)")
    parser.add_argument("--graph-tiles", default="",
                        help="comma-separated tiles for tile_graph_roundtrip (M5.37); off when empty")
    parser.add_argument("--graph-emitted", help="emitted section-2 graph JSON (ze0-sec2-graph/1)")
    parser.add_argument("--graph-factory", help="factory card root the non-emitted records must equal")
    parser.add_argument("--class-tiles", default="",
                        help="comma-separated tiles for tile_class_roundtrip (M5.36); off when empty")
    parser.add_argument("--class-emitted", help="emitted road-class map (ze0-road-class/1)")
    parser.add_argument("--factory-root",
                        help="factory card root: a tile identical to its MAPAL001/<name> "
                             "is factory bytes kept verbatim, so a short section list there "
                             "is INFO, not a failure (M5.62)")
    parser.add_argument("--skip-mutation", action="store_true")
    parser.add_argument("--image", help="optional raw image for the golden hash")
    parser.add_argument("--hash-image", action="store_true",
                        help="hash --image and compare it with the profile")
    parser.add_argument("--update-golden", metavar="PATH",
                        help="write a new golden profile and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.root:
        parser.error("--root is required")
    root = Path(args.root)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    tiles = split_tiles(args.tiles) if args.tiles is not None else list(ROUNDTRIP_TILES)
    semantic = (split_tiles(args.semantic_tiles) if args.semantic_tiles is not None
                else list(SEMANTIC_TILES))
    if not args.no_tiles:
        problems = []
        if args.tiles is not None:
            problems += missing_tile_requests(root, "--tiles", tiles)
        if args.semantic_tiles is not None:
            problems += missing_tile_requests(root, "--semantic-tiles", semantic)
        if problems:
            for problem in problems:
                print(f"error: {problem}", file=sys.stderr)
            print("error: requested tiles not checked; no RESULT printed (exit 2)",
                  file=sys.stderr)
            return 2
    image = Path(args.image) if args.image else None

    if args.update_golden:
        profile = generate_golden(root, image, args.include_lev,
                                  args.ignore_dump_artifacts)
        out = Path(args.update_golden)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n")
        print(f"wrote {out}: {profile['tree']}")
        return 0

    profile = None
    if not args.no_golden:
        profile = load_profile(Path(args.profile))
        if profile is None:
            print(f"warning: no golden profile at {args.profile}; "
                  "running semantic checks only", file=sys.stderr)

    report = cardcheck.Report("L2", {"kind": "root", "path": str(root)})
    check_census(root, profile, report, args.ignore_dump_artifacts)
    check_files(root, profile, report)
    check_drstr(root, profile, report, args.ignore_dump_artifacts,
                args.partial)
    if not args.no_cmp:
        check_cmp_roundtrip(root, profile, report, limit=args.cmp_limit)
    if not args.no_tiles:
        check_tile_roundtrip(root, profile, report, tiles)
        check_tile_semantic(root, profile, report, semantic, args.include_lev)
        section_tiles = list(dict.fromkeys(tiles + semantic + [
            t.strip() for t in args.class_tiles.split(",") if t.strip()
        ]))
        explicit = set()
        if args.tiles is not None:
            explicit.update(tiles)
        if args.semantic_tiles is not None:
            explicit.update(semantic)
        explicit.update(t.strip() for t in args.class_tiles.split(",") if t.strip())
        check_tile_section_list(
            root, report, section_tiles,
            Path(args.factory_root) if args.factory_root else None, explicit,
        )
        graph_tiles = [t.strip() for t in args.graph_tiles.split(",") if t.strip()]
        if graph_tiles:
            check_tile_graph(root, report, graph_tiles,
                             Path(args.graph_emitted) if args.graph_emitted else None,
                             Path(args.graph_factory) if args.graph_factory else None)
        class_tiles = [t.strip() for t in args.class_tiles.split(",") if t.strip()]
        if class_tiles:
            check_tile_class(root, report, class_tiles,
                             Path(args.class_emitted) if args.class_emitted else None)
        if not args.skip_mutation:
            check_tile_mutation(root, report)
    if not args.skip_mutation:
        check_refer_mutation(root, report)
        check_refer_rename_resize(root, report)
    if args.hash_image:
        check_image(image, profile, report)
    result = report.finish(strict=args.strict)

    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2) + "\n")
    if not args.json_only:
        print(f"L2 semantic validation: {root}")
        for check in result["checks"]:
            status = "OK" if check["ok"] else "FAIL"
            details = []
            for key, value in check["stats"].items():
                if isinstance(value, dict):
                    details.append(f"{key}={value.get('features', value)}")
                elif isinstance(value, (int, str, float)):
                    details.append(f"{key}={value}")
            print(f"  [{check['id']}] {status}"
                  + (f" ({'; '.join(details)})" if details else ""))
            for error in check["errors"]:
                print(f"    ERROR {error}")
            for warning in check["warnings"]:
                print(f"    WARN  {warning}")
        print("RESULT:", "PASS" if result["ok"] else "FAIL")
    return 0 if result["ok"] else 1


# ---------------------------------------------------------------------------
# self-test (no vendor data)


def _fixture_root(root: Path, cell: str = "B48R058R") -> Path:
    """A partial card root: one synthetic tile (tilewriter.make_factory) + DRSTR."""
    import tilewriter

    (root / "MAPAL001").mkdir(parents=True, exist_ok=True)
    tile = root / "MAPAL001" / f"{cell}.DAT"
    tile.write_bytes(tilewriter.make_factory(cell))
    drstr = root / "DRSTR001.DAT"
    drstr.write_bytes(b"")
    for _ in range(4):  # DRSTR lists its own size: iterate to a fixed point
        built = drstr_ze0.build(root)
        if built == drstr.read_bytes():
            break
        drstr.write_bytes(built)
    return tile


def _run_main(argv: list[str]) -> tuple[int, str, str]:
    import contextlib
    import io

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = main(argv)
        except SystemExit as exc:  # argparse usage errors
            rc = exc.code if isinstance(exc.code, int) else 2
    return rc, out.getvalue(), err.getvalue()


def selftest() -> int:
    failures = 0

    def ok(cond: bool, msg: str) -> None:
        nonlocal failures
        print(("  ok   " if cond else "  FAIL ") + msg)
        if not cond:
            failures += 1

    print("l2check selftest (synthetic tile, no vendor data)")
    base = ["--partial", "--no-golden", "--no-cmp"]
    with tempfile.TemporaryDirectory(prefix="l2check-") as tmp:
        root = Path(tmp) / "root"
        tile = _fixture_root(root)
        args = ["--root", str(root)] + base

        ok(CELL_RE.match("B48R058R") is not None and CELL_RE.match("B48R058R.DAT") is None,
           "CELL_RE: bare cell matches, file name does not")
        ok(missing_tile_requests(root, "--tiles", ["B48R058R.DAT"]) == [],
           "present file name -> no usage error")

        # The C-3566 footgun: a bare cell name.
        rc, out, err = _run_main(args + ["--tiles", "B48R058R"])
        ok(rc == 2, f"--tiles B48R058R -> exit 2 (got {rc})")
        ok("B48R058R.DAT" in err and "--tiles B48R058R.DAT" in err,
           "usage error names the .DAT form")
        ok("RESULT: PASS" not in out and "tiles=0" not in out,
           "no tiles=0 / RESULT: PASS printed")
        rc, out, err = _run_main(args + ["--tiles", "B48R058R.DAT",
                                         "--semantic-tiles", "B48R058R"])
        ok(rc == 2 and "--semantic-tiles B48R058R.DAT" in err,
           "--semantic-tiles bare cell -> exit 2 naming the .DAT form")
        rc, out, err = _run_main(args + ["--tiles", "B30R060R.DAT"])
        ok(rc == 2 and "MAPAL001/B30R060R.DAT is not a file" in err,
           "absent file name -> exit 2")
        rc, out, err = _run_main(args + ["--tiles", "B30R060R"])
        ok(rc == 2 and "not present either" in err,
           "bare cell with no .DAT file either -> exit 2, says so")

        # Positive control: the file name checks exactly one tile and passes.
        rc, out, err = _run_main(args + ["--tiles", "B48R058R.DAT",
                                         "--semantic-tiles", "B48R058R.DAT"])
        ok(rc == 0, f"--tiles B48R058R.DAT -> exit 0 (got {rc}; {err.strip()[:200]})")
        ok("[tile_roundtrip] OK (tiles=1; preserved=0)" in out, "tiles=1 printed")
        ok("RESULT: PASS" in out, "RESULT: PASS printed")
        ok("not present" not in out.split("[tile_mutation]")[0],
           "no 'not present' warning for the requested tile")

        # Unchanged: --no-tiles ignores the names; defaults still skip-with-warn.
        rc, out, _err = _run_main(args + ["--no-tiles", "--tiles", "B48R058R"])
        ok(rc == 0 and "tile_roundtrip" not in out, "--no-tiles: names not validated")
        rc, out, _err = _run_main(args)
        ok(rc == 0 and "tiles=0" in out and "not present on this card" in out,
           "default tile list: absent tiles still a warning (behaviour unchanged)")

        # Negative control: a broken requested tile fails the tile gate (exit 1).
        tile.write_bytes(tile.read_bytes()[:1000])
        rc, out, _err = _run_main(args + ["--tiles", "B48R058R.DAT",
                                          "--semantic-tiles", "B48R058R.DAT"])
        ok(rc == 1 and "[tile_roundtrip] FAIL" in out and "RESULT: FAIL" in out,
           f"truncated tile -> tile_roundtrip FAIL, exit 1 (got {rc})")

    # M5.62: a generated tile must list three sections at header 0x800; a
    # factory tile kept verbatim is the only short list that does not fail.
    with tempfile.TemporaryDirectory(prefix="l2check-sections-") as tmp:
        root = Path(tmp) / "root"
        tile = _fixture_root(root)
        base = ["--partial", "--no-golden", "--no-cmp"]
        pristine = tile.read_bytes()
        ok(len(tile_drop_l3.parse_section_list(pristine[0x800:0x812], 3)) == 3,
           "fixture tile lists three sections")
        rc, out, err = _run_main(["--root", str(root)] + base
                                 + ["--tiles", "B48R058R.DAT"])
        ok(rc == 0 and "[tile_section_list] OK" in out,
           f"three-section tile -> tile_section_list OK, exit 0 (got {rc}; {err.strip()[:160]})")
        blanked = bytearray(pristine)
        blanked[0x80c:0x812] = b"\xff\xff\xff\xff\x00\x00"
        tile.write_bytes(bytes(blanked))
        rc, out, _err = _run_main(["--root", str(root)] + base
                                  + ["--tiles", "B48R058R.DAT"])
        ok(rc == 1 and "[tile_section_list] FAIL" in out and "0x80c" in out,
           f"third entry blanked -> tile_section_list FAIL names 0x80c, exit 1 (got {rc})")
        # The default list does NOT enforce (unknown provenance): a raw factory
        # card sweep or a generated tree's sibling must not fail.  Only a tile
        # named on the command line is a generated target.
        tile.write_bytes(bytes(blanked))
        (root / "MAPAL001" / "B30R060R.DAT").write_bytes(bytes(blanked))
        rc, out, _err = _run_main(["--root", str(root)] + base)
        ok(rc == 0 and "not a named generated target" in out,
           f"default list -> short tile INFO, not a failure (got {rc})")
        # Factory verbatim: identical to --factory-root -> INFO, not a failure.
        factory = Path(tmp) / "factory"
        (factory / "MAPAL001").mkdir(parents=True, exist_ok=True)
        (factory / "MAPAL001" / "B48R058R.DAT").write_bytes(bytes(blanked))
        tile.write_bytes(bytes(blanked))
        (root / "MAPAL001" / "B30R060R.DAT").unlink()
        rc, out, _err = _run_main(["--root", str(root)] + base
                                 + ["--tiles", "B48R058R.DAT",
                                    "--factory-root", str(factory)])
        ok(rc == 0 and "factory bytes kept verbatim" in out
           and "[tile_section_list] OK" in out,
           f"factory verbatim short list -> INFO/OK, exit 0 (got {rc})")
        # A different byte changes it from factory-verbatim to generated:
        # the rule must still fail it.
        changed = bytearray(blanked)
        changed[0x100] ^= 0x01
        tile.write_bytes(bytes(changed))
        rc, out, _err = _run_main(["--root", str(root)] + base
                                 + ["--tiles", "B48R058R.DAT",
                                    "--factory-root", str(factory)])
        ok(rc == 1 and "[tile_section_list] FAIL" in out,
           f"short list differing from factory -> FAIL (got {rc})")

    # M5.36: tile_class_roundtrip on a tile whose class the writer emitted.
    import tile_class_roundtrip as tcr
    import tilewriter as _tw
    with tempfile.TemporaryDirectory(prefix="l2check-class-") as tmp:
        root = Path(tmp) / "root"
        tile = _fixture_root(root)
        base = ["--partial", "--no-golden", "--no-cmp"]
        emitted = Path(tmp) / "B48R058R.DAT.class.json"
        decoded, _stats = tcr.extract_tile(tile)
        side = tile.with_name(tile.name + ".class.json")
        tcr.dump_expected(str(side), decoded, cell="B48R058R")
        rc, out, err = _run_main(["--root", str(root)] + base
                                 + ["--class-tiles", "B48R058R.DAT"])
        ok(rc == 0 and "[tile_class_roundtrip] OK" in out and "PASS" in out,
           f"class sidecar -> tile_class_roundtrip PASS, exit 0 (got {rc}; {err.strip()[:160]})")
        ok("tile_class_roundtrip FAIL" not in out, "class sidecar: no class FAIL")
        # A one-value mutant of the sidecar is a FAIL (the falsifier).
        mutant = tcr.mutate(decoded)
        tcr.dump_expected(str(side), mutant, cell="B48R058R")
        rc, out, _err = _run_main(["--root", str(root)] + base
                                  + ["--class-tiles", "B48R058R.DAT"])
        ok(rc == 1 and "[tile_class_roundtrip] FAIL" in out,
           f"one-value class mutant -> tile_class_roundtrip FAIL, exit 1 (got {rc})")
        # No sidecar: decoded census, never a PASS row.
        side.unlink()
        rc, out, _err = _run_main(["--root", str(root)] + base
                                  + ["--class-tiles", "B48R058R.DAT"])
        ok("[tile_class_roundtrip] OK" in out
           and "no emitted class map" in out and "decoded" in out,
           "no sidecar -> decoded census with a warning, not a PASS claim")

    # M5.55: the expected record must include M5.52's field-5 length patch, so
    # a rename-only expectation (the pre-M5.52 edit) is a FAIL.  The synthetic
    # record uses the real field layout, and resize_name is the actual writer.
    rec = mutate_refer_poi._synth_record(0x60, b"ALPHA MUSEUM",
                                         b"1@VIA ONE\x00")
    page = rec + mutate_refer_poi._synth_record(0x68, b"BETA MUSEUMS",
                                                b"@VIA TWO", w10=0x0102)
    old_b, new = b"ALPHA MUSEUM", b"ALPHA MUSEUM TWO"
    delta = len(new) - len(old_b)
    mutated, _info = mutate_refer_poi.resize_name(page, old_b, new)
    before = mutate_refer_poi.parse_page(page)[0]["bytes"]
    after = mutate_refer_poi.parse_page(mutated)[0]["bytes"]
    hit = before.find(old_b)
    expected = _expected_resize_record(before, hit, old_b, new, delta)
    ok(expected == after,
       "M5.52 rename: expected record (len2 + field-5 length) == writer")
    stale = (
        before[:1]
        + bytes([(len(before) + delta) // 2])
        + before[2:hit]
        + new
        + before[hit + len(old_b):]
    )
    ok(stale != after and expected != stale,
       "pre-M5.52 rename-only (field 5 stale) is not the M5.52 edit")

    print(f"l2check selftest: {'PASS' if failures == 0 else 'FAIL'} ({failures} failure(s))")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
