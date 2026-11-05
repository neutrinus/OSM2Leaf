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
* a same-length POI rename passes the offline mutation validator.

A golden profile for the EU 2011 sample lives in ``tools/golden/eu2011.json``.
Generate or refresh it intentionally with ``--update-golden``; do not update it
just to make a failing run pass.

Usage:
    python3 tools/l2check.py --root /path/to/root
    python3 tools/l2check.py --root /path/to/root --cmp-limit 20 --no-tiles
    python3 tools/l2check.py --root /path/to/root --update-golden tools/golden/eu2011.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cardcheck  # noqa: E402
import cmpind_writer  # noqa: E402
import drstr_ze0  # noqa: E402

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


def census(root: Path) -> dict:
    files = dirs = total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirs += len(dirnames)
        for name in filenames:
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
    return clarion_tile, stream_decode


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


def generate_golden(root: Path, image: Path | None, include_lev: bool) -> dict:
    profile: dict = {
        "profile_version": 1,
        "sample": "LEAF_2011-2012_QSD-309-101_navi158_eu.img",
        "tree": census(root),
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
        _clarion_tile, stream_decode = _import_viewer()
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


def check_census(root: Path, profile: dict | None, report: cardcheck.Report) -> None:
    check = report.add(cardcheck.Check("census"))
    actual = census(root)
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


def check_drstr(root: Path, profile: dict | None, report: cardcheck.Report) -> None:
    check = report.add(cardcheck.Check("drstr_roundtrip"))
    path = root / "DRSTR001.DAT"
    if not path.is_file():
        check.error("DRSTR001.DAT is missing")
        return
    reference = path.read_bytes()
    try:
        built = drstr_ze0.build(root)
    except (OSError, ValueError) as exc:
        check.error(f"build failed: {exc}")
        return
    check.stats["size"] = len(built)
    if built != reference:
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
        clarion_tile, _stream_decode = _import_viewer()
    except ImportError as exc:
        check.error(f"viewer not available: {exc}; run tools/ze0-viewer/setup.sh")
        return
    for name in tiles:
        path = root / "MAPAL001" / name
        if not path.is_file():
            check.error(f"MAPAL001/{name}: missing")
            continue
        try:
            data = path.read_bytes()
            tile = clarion_tile.read_tile(data)
            out = clarion_tile.write_tile(tile)
        except Exception as exc:  # noqa: BLE001 - report every tile
            check.error(f"{name}: {exc}")
            continue
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
    check.stats["tiles"] = len(tiles)


def check_tile_semantic(root: Path, profile: dict | None,
                        report: cardcheck.Report, tiles: list[str],
                        include_lev: bool) -> None:
    check = report.add(cardcheck.Check("tile_semantic"))
    try:
        _clarion_tile, stream_decode = _import_viewer()
    except ImportError as exc:
        check.error(f"viewer not available: {exc}; run tools/ze0-viewer/setup.sh")
        return
    for name in tiles:
        path = root / "MAPAL001" / name
        if not path.is_file():
            check.error(f"MAPAL001/{name}: missing")
            continue
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


def check_tile_mutation(root: Path, report: cardcheck.Report,
                        tile: str = "B30R060R.DAT") -> None:
    check = report.add(cardcheck.Check("tile_mutation"))
    src = root / "MAPAL001" / tile
    if not src.is_file():
        check.error(f"MAPAL001/{tile}: missing")
        return
    try:
        clarion_tile, stream_decode = _import_viewer()
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


def check_refer_mutation(root: Path, report: cardcheck.Report) -> None:
    check = report.add(cardcheck.Check("refer_mutation"))
    cmp_path = root / "REFER001" / f"{REFER_POI}.cmp"
    ind_path = root / "REFER001" / f"{REFER_POI}.ind"
    drstr_path = root / "DRSTR001.DAT"
    if not cmp_path.is_file() or not ind_path.is_file():
        check.error(f"{REFER_POI}.cmp/.ind is missing")
        return
    with tempfile.TemporaryDirectory(prefix="l2-refer-") as tmp:
        outdir = Path(tmp) / "mut"
        proc = subprocess.run(
            [sys.executable, str(TOOLS / "mutate_refer_poi.py"),
             str(cmp_path), str(ind_path), str(outdir),
             "--page", hex(REFER_PAGE), "--old", REFER_OLD, "--new", REFER_NEW],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            check.error(f"mutate_refer_poi.py failed: {proc.stderr.strip() or proc.stdout.strip()}")
            return
        proc = subprocess.run(
            [sys.executable, str(TOOLS / "validate_mutation.py"),
             str(root / "REFER001"), str(outdir), REFER_POI,
             "--page", hex(REFER_PAGE), "--drstr", str(drstr_path),
             "--inner-page", hex(REFER_PAGE)],
            capture_output=True, text=True,
        )
        check.stats["validate"] = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        if proc.returncode != 0 or "PASS" not in proc.stdout:
            check.error(f"validate_mutation.py failed: {proc.stderr.strip() or proc.stdout.strip()}")


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
# CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True, help="extracted card root")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE),
                        help="golden profile (default: tools/golden/eu2011.json)")
    parser.add_argument("--json", help="write a JSON report to this path")
    parser.add_argument("--json-only", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-golden", action="store_true",
                        help="skip all profile comparisons")
    parser.add_argument("--cmp-limit", type=int, default=0,
                        help="check only the first N .cmp pairs (0 = all)")
    parser.add_argument("--no-cmp", action="store_true")
    parser.add_argument("--no-tiles", action="store_true")
    parser.add_argument("--tiles", default=",".join(ROUNDTRIP_TILES),
                        help="comma-separated tiles for the round-trip check")
    parser.add_argument("--semantic-tiles", default=",".join(SEMANTIC_TILES),
                        help="comma-separated tiles for the geometry digest")
    parser.add_argument("--include-lev", action="store_true",
                        help="also decode LEV3456R (slow)")
    parser.add_argument("--skip-mutation", action="store_true")
    parser.add_argument("--image", help="optional raw image for the golden hash")
    parser.add_argument("--hash-image", action="store_true",
                        help="hash --image and compare it with the profile")
    parser.add_argument("--update-golden", metavar="PATH",
                        help="write a new golden profile and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    image = Path(args.image) if args.image else None

    if args.update_golden:
        profile = generate_golden(root, image, args.include_lev)
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
    check_census(root, profile, report)
    check_files(root, profile, report)
    check_drstr(root, profile, report)
    if not args.no_cmp:
        check_cmp_roundtrip(root, profile, report, limit=args.cmp_limit)
    if not args.no_tiles:
        tiles = [t.strip() for t in args.tiles.split(",") if t.strip()]
        semantic = [t.strip() for t in args.semantic_tiles.split(",") if t.strip()]
        check_tile_roundtrip(root, profile, report, tiles)
        check_tile_semantic(root, profile, report, semantic, args.include_lev)
        if not args.skip_mutation:
            check_tile_mutation(root, report)
    if not args.skip_mutation:
        check_refer_mutation(root, report)
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


if __name__ == "__main__":
    raise SystemExit(main())
