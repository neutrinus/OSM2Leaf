#!/usr/bin/env python3
"""Single cross-year verifier for a Leaf ZE0 map card or map tree.

Runs L1 (``cardcheck.py``) and, unless disabled, L2 (``l2check.py``) with the
right flags for the detected generation:

* ZE0 2011: golden L2 profile;
* ZE0 2014/2016: ``--no-golden --ignore-dump-artifacts``;
* map-only tree without ``VER_INFO``: ``--partial``;
* QY8x 2019 (``CLA-NAVI06-01``/ZENRIN): reported as unsupported, exit 3.

For ``--image`` the L2 run needs a root, so the image is extracted to a
temporary directory with ``7z``. Use ``--no-l2`` to validate the image
structurally without extracting it.

Usage:
    python3 tools/verify.py --root /path/to/root
    python3 tools/verify.py --image archive/images/LEAF_2014_EU_QSD-357-101.img
    python3 tools/verify.py --image ... --no-l2 --json report.json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cardcheck  # noqa: E402

TOOLS = Path(__file__).resolve().parent
DEFAULT_WORKDIR = TOOLS.parent / "archive" / "work"
NAVI05 = "CLA-NAVI05-01"
NAVI06 = "CLA-NAVI06-01"


def _read(source, rel: str) -> bytes | None:
    try:
        return source.read(rel)
    except (OSError, ValueError):
        return None


def _artifacts(source) -> bool:
    for entry in source.walk():
        if cardcheck.is_dump_artifact(entry.name, True):
            return True
    return False


def detect(source) -> dict:
    top = {e.name for e in source.list_dir("")}
    mmain = _read(source, "MMAIN001.DAT") or b""
    fields = cardcheck.header_fields(mmain[:0x180])
    model = fields.get("model", "")
    fmt = fields.get("format", "")
    hdd = _read(source, "VER_INFO/HDD_INFO.TXT") or b""
    lines = hdd.decode("ascii", "replace").split("\r\n") if hdd else []
    year = None
    if len(lines) > 4:
        match = re.match(r"(\d{2})-", lines[4])
        if match:
            year = 2000 + int(match.group(1))
    engine = "UNKNOWN"
    if model == NAVI06 or fmt.startswith("FORMAT VERSION X08-03-00"):
        engine = "QY8X"
    elif model == NAVI05 or fmt.startswith("FORMAT VERSION X08-02-00"):
        engine = "ZE0"
    elif "MAPAL001" in top and "DRSTR001.DAT" in top:
        engine = "ZE0"
    partial = "VER_INFO" not in top
    label = getattr(source, "label", "") or (getattr(source, "geometry", None) and source.geometry.label) or ""
    return {
        "engine": engine,
        "year": year,
        "label": label,
        "partial": partial,
        "artifacts": _artifacts(source),
        "top": sorted(top),
        "hdd_line5": lines[4] if len(lines) > 4 else "",
    }


def run_tool(path: Path, args: list[str]) -> tuple[int, dict | None, str]:
    proc = subprocess.run(
        [sys.executable, str(path), *args],
        capture_output=True, text=True,
    )
    return proc.returncode, None, proc.stdout + proc.stderr


def load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def run_l1(source_args: list[str], info: dict, json_path: Path, strict: bool):
    args = [*source_args, "--json", str(json_path)]
    if info["partial"]:
        args.append("--partial")
    if info["artifacts"]:
        args.append("--ignore-dump-artifacts")
    if strict:
        args.append("--strict")
    code, _, output = run_tool(TOOLS / "cardcheck.py", args)
    return code, load_json(json_path), output


def run_l2(root: Path, info: dict, json_path: Path, strict: bool,
           no_golden: bool, profile: str | None):
    args = ["--root", str(root), "--json", str(json_path)]
    if info["partial"]:
        args.append("--partial")
    if info["artifacts"]:
        args.append("--ignore-dump-artifacts")
    if no_golden or info["year"] != 2011:
        args.append("--no-golden")
    if profile:
        args.extend(["--profile", profile])
    if strict:
        args.append("--strict")
    code, _, output = run_tool(TOOLS / "l2check.py", args)
    return code, load_json(json_path), output


def extract_image(image: Path, workdir: Path) -> tuple[Path | None, str]:
    if not shutil.which("7z"):
        return None, "7z not found; L2 skipped"
    workdir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="verify-", dir=workdir))
    proc = subprocess.run(
        ["7z", "x", "-y", f"-o{tmp}", str(image)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        return None, f"7z extraction failed: {proc.stderr.strip() or proc.stdout.strip()}"
    return tmp, ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", help="raw SD image")
    src.add_argument("--root", help="extracted card root or map tree")
    parser.add_argument("--json", help="write a combined JSON report")
    parser.add_argument("--workdir", default=str(DEFAULT_WORKDIR),
                        help="temporary extraction directory (default: archive/work)")
    parser.add_argument("--keep-work", action="store_true",
                        help="keep the extracted L2 root")
    parser.add_argument("--no-l2", action="store_true",
                        help="run L1 only")
    parser.add_argument("--no-golden", action="store_true",
                        help="skip golden profile comparisons")
    parser.add_argument("--profile", help="explicit L2 golden profile")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    source = None
    extract_dir = None
    try:
        if args.image:
            image = Path(args.image)
            try:
                source = cardcheck.Fat32Image(image)
            except (OSError, ValueError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            source_args = ["--image", str(image)]
            source_desc = {"kind": "image", "path": str(image)}
        else:
            root = Path(args.root)
            try:
                source = cardcheck.RootSource(root)
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            source_args = ["--root", str(root)]
            source_desc = {"kind": "root", "path": str(root)}

        info = detect(source)
        result = {
            "ok": False,
            "source": source_desc,
            "detected": info,
            "l1": None,
            "l2": None,
            "warnings": [],
        }

        if info["engine"] == "QY8X":
            result["warnings"].append(
                "QY8x detected (CLA-NAVI06-01 / X08-03-00); not a ZE0 card"
            )
            print("Card: QY8x (CLA-NAVI06-01 / X08-03-00)")
            print("RESULT: UNSUPPORTED (different navigation engine; 2019 e-NV200)")
            if args.json:
                Path(args.json).write_text(json.dumps(result, indent=2) + "\n")
            return 3

        with tempfile.TemporaryDirectory(prefix="verify-json-") as tmp:
            tmpdir = Path(tmp)
            l1_path = tmpdir / "l1.json"
            l1_code, l1, l1_output = run_l1(source_args, info, l1_path, args.strict)
            result["l1"] = l1 or {"ok": False, "errors": [l1_output.strip()]}

            if not args.no_l2:
                if args.image:
                    extract_dir, err = extract_image(Path(args.image),
                                                     Path(args.workdir))
                    if extract_dir is None:
                        result["warnings"].append(err)
                        result["l2"] = {"ok": True, "skipped": err}
                    else:
                        l2_path = tmpdir / "l2.json"
                        l2_code, l2, l2_output = run_l2(
                            extract_dir, info, l2_path, args.strict,
                            args.no_golden, args.profile)
                        result["l2"] = l2 or {"ok": False, "errors": [l2_output.strip()]}
                else:
                    l2_path = tmpdir / "l2.json"
                    l2_code, l2, l2_output = run_l2(
                        Path(args.root), info, l2_path, args.strict,
                        args.no_golden, args.profile)
                    result["l2"] = l2 or {"ok": False, "errors": [l2_output.strip()]}

        l1_ok = bool(result["l1"] and result["l1"].get("ok"))
        l2_ok = bool(result["l2"] and result["l2"].get("ok"))
        result["ok"] = l1_ok and (args.no_l2 or l2_ok)

        if args.json:
            Path(args.json).write_text(json.dumps(result, indent=2) + "\n")

        print(f"Card: {info['engine']} {info['year'] or 'year?'} "
              f"({source_desc['kind']}={source_desc['path']})")
        print(f"  label={info['label'] or '-'} partial={info['partial']} "
              f"artifacts={info['artifacts']}")
        print(f"  L1: {'PASS' if l1_ok else 'FAIL'}")
        if result["l1"]:
            for error in result["l1"].get("errors", [])[:8]:
                print(f"    ERROR {error}")
        if not args.no_l2:
            l2 = result["l2"]
            if l2 and l2.get("skipped"):
                print(f"  L2: SKIP ({l2['skipped']})")
            else:
                print(f"  L2: {'PASS' if l2_ok else 'FAIL'}")
                if l2:
                    for check in l2.get("checks", []):
                        stats = check.get("stats", {})
                        if check["id"] in ("cmp_roundtrip", "tile_roundtrip",
                                           "tile_semantic", "refer_mutation",
                                           "refer_rename_resize"):
                            detail = ", ".join(
                                f"{k}={v}" for k, v in stats.items()
                                if isinstance(v, (int, str, float))
                            )
                            print(f"    [{check['id']}] "
                                  f"{'OK' if check['ok'] else 'FAIL'}"
                                  + (f" ({detail})" if detail else ""))
                    for error in l2.get("errors", [])[:8]:
                        print(f"    ERROR {error}")
        print("RESULT:", "PASS" if result["ok"] else "FAIL")
        return 0 if result["ok"] else 1
    finally:
        if source is not None:
            source.close()
        if extract_dir is not None and not args.keep_work:
            shutil.rmtree(extract_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
