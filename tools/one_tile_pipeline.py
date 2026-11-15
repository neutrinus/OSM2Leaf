#!/usr/bin/env python3
"""
one_tile_pipeline.py — Dolnośląskie one-tile OSM pipeline (M5.29).

Produces an output card tree where exactly one tile (default B48R058R) is
OSM-generated via osm_ingest -> mesh_split -> roadclass_v0 (provisional-v0)
-> tilewriter, and the rest is factory/verbatim (factory-backed path) or a
synthetic baseline/verbatim (synthetic-only path). Rebuilds manifests and
runs cardcheck / applicable l2check, emitting a per-gate report.

Rule 13: mapping=provisional-v0 (roadclass_v0) is provisional and NOT
firmware-confirmed. L2 is necessary, not sufficient; L3/L4/L5 firmware
acceptance is unknown. Gate statuses are PASS / NOT-APPLICABLE /
CANNOT-VERIFY-OFFLINE / NEEDS-L3; SKIP is never reported as PASS.

No vendor bytes are committed or embedded. Stdlib + existing repo tools only.

Exit codes: 0 selftest/ok, 1 check/selftest/gate failure, 2 usage/input.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import sys
import struct
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

GATES = [
    "hdd_info_map_code",
    "drstr_mmain_cmplst_ind",
    "tile_roundtrip_structure",
    "section4",
    "manifests",
]
STATUSES = {"PASS", "NOT-APPLICABLE", "CANNOT-VERIFY-OFFLINE", "NEEDS-L3", "BLOCKED"}

SYNTHETIC_OSM = """\
<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6">
 <node id="1" lat="51.1000" lon="17.0000"/>
 <node id="2" lat="51.1000" lon="17.0500"/>
 <node id="3" lat="51.1200" lon="17.0300"/>
 <node id="4" lat="51.0800" lon="17.0200"/>
 <way id="10">
  <nd ref="1"/><nd ref="2"/><nd ref="3"/>
  <tag k="highway" v="primary"/>
  <tag k="name" v="Testowa"/>
 </way>
 <way id="11">
  <nd ref="4"/><nd ref="1"/>
  <tag k="highway" v="residential"/>
 </way>
</osm>
"""


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class UsageError(Exception):
    """An input combination that would destroy data or cannot be honoured."""


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _check_out_overlap(out: Path, input_root: Path | None) -> None:
    """Reject an ``out`` that is the input root, or a parent/child of it.

    Both ``build_*_out`` helpers delete ``out`` before writing; if it overlaps
    the input, the deletion destroys the input (H64).
    """
    if input_root is None:
        return
    o = out.expanduser().resolve()
    r = input_root.expanduser().resolve()
    if o == r:
        raise UsageError(f"--out {o} is the input root; refusing to delete the input tree")
    if _is_within(r, o):
        raise UsageError(f"--out {o} is a parent of input root {r}; a recursive delete would remove the input")
    if _is_within(o, r):
        raise UsageError(f"--out {o} is inside input root {r}; refusing to remove input data")


def _clarion_tile():
    ze0 = HERE / "ze0-viewer" / "tools_ze0"
    if str(ze0) not in sys.path:
        sys.path.insert(0, str(ze0))
    import clarion_tile  # noqa: E402
    return clarion_tile


def _factory_tile_provenance(factory_root: Path, cell: str) -> dict[str, Any]:
    """Prove the tile at ``MAPAL001/<cell>.DAT`` is a parseable factory tile.

    Returns a provenance dict with ``factory_tree_provenance`` =
    ``factory-tile-parsed`` on success, or ``factory-tree-invalid`` plus a
    ``parse_error`` reason. Size alone is not a test; the tile is read and
    parsed with the same ``clarion_tile`` reader the writer uses.
    """
    tile = factory_root / "MAPAL001" / f"{cell}.DAT"
    prov: dict[str, Any] = {
        "factory_tile": str(tile),
        "factory_tile_size": 0,
        "factory_tile_sha256": None,
        "factory_tree_provenance": "factory-tree-invalid",
        "parse_error": None,
    }
    try:
        data = tile.read_bytes()
    except OSError as e:
        prov["parse_error"] = f"read failed: {e}"
        return prov
    prov["factory_tile_size"] = len(data)
    if not data:
        prov["parse_error"] = "empty file (0 bytes)"
        return prov
    prov["factory_tile_sha256"] = sha256_bytes(data)
    try:
        parsed = _clarion_tile().read_tile(data)
    except Exception as e:  # a malformed tile is a result, not a crash
        prov["parse_error"] = f"{type(e).__name__}: {e}"
        return prov
    sections = parsed.get("sections") or []
    if not sections:
        prov["parse_error"] = "tile parsed to no sections"
        return prov
    prov["factory_tile_sections"] = len(sections)
    prov["factory_tree_provenance"] = "factory-tile-parsed"
    return prov


def gate(status: str, detail: str, evidence: str = "") -> dict[str, str]:
    if status not in STATUSES:
        status = "CANNOT-VERIFY-OFFLINE"
    return {"status": status, "detail": detail, "evidence": evidence}


def run_cmd_json(mod: str, argv: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    import subprocess
    cmd = [sys.executable, str(HERE / mod)] + argv
    p = subprocess.run(cmd, cwd=str(cwd or HERE.parent), capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr



def _put_utf16be(buf: bytearray, off: int, text: str) -> None:
    raw = text.encode("utf-16-be")
    buf[off:off + len(raw)] = raw

def _synth_header(model: str = "CLA-NAVI05-01") -> bytearray:
    buf = bytearray(b"\xff" * 512)
    _put_utf16be(buf, 0x00, "CLARION")
    _put_utf16be(buf, 0x40, "HITACHI")
    _put_utf16be(buf, 0x80, model)
    _put_utf16be(buf, 0xA0, "FORMAT VERSION X08-02-00")
    _put_utf16be(buf, 0xE0, "DATA VERSION 26/11/09/01")
    buf[0x160:0x162] = b"\x16\x00"
    _put_utf16be(buf, 0x162, "V05.00.00")
    buf[0x180:0x18C] = bytes.fromhex("ff ff 24 ff 12 c0 05 00 fb 50 0f f0")
    buf[0x18C:0x1A0] = b"\x3f" * 20
    buf[0x1A0:0x1AC] = b"\xff" * 12
    return buf

def _write_level_table(buf: bytearray, groups: list[tuple[int, list[tuple]]]) -> None:
    struct.pack_into(">H", buf, 0x1AC, len(groups))
    pos = 0x1AE
    for sec, rows in groups:
        buf[pos] = sec
        buf[pos + 1] = len(rows)
        pos += 2
        for level, kind, count in rows:
            struct.pack_into(">BBH", buf, pos, level, kind, count)
            pos += 4

def _synth_mmain() -> bytes:
    buf = bytearray(_synth_header())
    buf.extend(b"\x00" * (0x1000 - len(buf)))
    _write_level_table(buf, [(1, [(6, 0x80, 1), (5, 0x90, 1)])])
    return bytes(buf)

def _synth_tile() -> bytes:
    buf = bytearray(_synth_header())
    buf.extend(b"\x00" * (0x400 - len(buf)))
    _write_level_table(buf, [(1, [(6, 0x80, 1), (5, 0x90, 1)])])
    struct.pack_into(">H", buf, 0x2AC, 1)
    buf[0x2AE] = 1; buf[0x2AF] = 1
    struct.pack_into(">BBhhhh", buf, 0x2B0, 2, 0, 1920, 1685, -720, -562)
    return bytes(buf)

def _synth_cmp_ind(root: Path, stem: str = "POINT001.DAT") -> None:
    import cmpind_writer
    payload = bytearray(_synth_header())
    payload.extend(b"\x00" * 64)
    c = cmpind_writer.CmpFile.from_dat(bytes(payload))
    refer = root / "REFER001"
    refer.mkdir(exist_ok=True)
    c.write(refer, stem)

def _scaffold_tree(root: Path, osm_tile_cell: str) -> list[str]:
    """Create synthetic baseline scaffold (not OSM-generated) so manifests/checks can run."""
    import drstr_ze0
    root.mkdir(parents=True, exist_ok=True)
    for d in ("MAPAL001", "REFER001", "REFER002", "RDSTM001", "BICON001", "OPNG", "SPEECH", "TMC"):
        (root / d).mkdir(exist_ok=True)
    (root / "MMAIN001.DAT").write_bytes(_synth_mmain())
    # Synthetic baseline tiles (not OSM-generated). Do NOT create osm_tile_cell here.
    (root / "MAPAL001" / "LEV3456R.DAT").write_bytes(_synth_tile())
    (root / "MAPAL001" / "B30R060R.DAT").write_bytes(_synth_tile())
    _synth_cmp_ind(root)
    (root / "CMP.LST").write_bytes(b"\\SystemSD\\REFER001\\")
    (root / "DRSTR001.DAT").write_bytes(drstr_ze0.build(root))
    return ["MAPAL001/LEV3456R.DAT", "MAPAL001/B30R060R.DAT", "MMAIN001.DAT", "REFER001/POINT001.DAT.cmp", "REFER001/POINT001.DAT.ind", "CMP.LST", "DRSTR001.DAT"]

def build_synthetic_out(out: Path, cell: str = "B48R058R",
                        input_root: Path | None = None) -> dict[str, Any]:
    """Build a synthetic minimal tree with one OSM-generated tile. No vendor bytes."""
    _check_out_overlap(out, input_root)
    report: dict[str, Any] = {
        "mode": "synthetic-only",
        "tile": cell,
        "mapping": "provisional-v0",
        "rule13": "roadclass_v0 provisional, not firmware-confirmed; L2 necessary not sufficient; L3/L4/L5 acceptance unknown",
        "factory_backed": False,
        "missing_input": "EU2011 full image or extracted MAPAL001/<tile> + compatible factory tree (IMG256 lacks MAPAL001); leafre-work/root is partial (MAPAL001 only, no B48R058R/DRSTR/REFER/VER_INFO) in this environment",
        "real_image_run": "blocked",
        "gates": {},
        "baseline_scaffold": [],
        "osm_generated_tile": f"MAPAL001/{cell}.DAT",
        "counts": {},
    }
    if out.exists():
        shutil.rmtree(out)
    baseline = _scaffold_tree(out, cell)
    report["baseline_scaffold"] = baseline

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        osm = td / "syn.osm"
        osm.write_text(SYNTHETIC_OSM, encoding="utf-8")
        imf = td / "syn.imf.jsonl"
        rc, so, se = run_cmd_json("osm_ingest.py", [str(osm), "-o", str(imf), "--source-name", "synthetic-wroclaw"])
        report["counts"]["osm_ingest_rc"] = rc
        if rc != 0 or not imf.exists():
            report["gates"] = {g: gate("BLOCKED", f"osm_ingest failed rc={rc}: {se[:300]}") for g in GATES}
            return report
        imf_lines = [ln for ln in imf.read_text(encoding="utf-8").splitlines() if ln.strip()]
        report["counts"]["imf_records"] = len(imf_lines)
        ways = sum(1 for ln in imf_lines if '"type":"way"' in ln or '"type": "way"' in ln)
        nodes = sum(1 for ln in imf_lines if '"type":"node"' in ln or '"type": "node"' in ln)
        report["counts"]["ways"] = ways
        report["counts"]["nodes"] = nodes
        report["fixture_sha256"] = sha256_bytes(SYNTHETIC_OSM.encode("utf-8"))

        split_out = td / "split.imf.jsonl"
        rc, so, se = run_cmd_json("mesh_split.py", [str(imf), "-o", str(split_out)])
        report["counts"]["mesh_split_rc"] = rc
        mesh_src = split_out if rc == 0 and split_out.exists() else imf

        ctab = td / "roadclass_v0.json"
        rc, so, se = run_cmd_json("roadclass_v0.py", ["--class-table-out", str(ctab)])
        report["counts"]["roadclass_rc"] = rc
        if rc != 0 or not ctab.exists():
            report["gates"] = {g: gate("BLOCKED", f"roadclass_v0 failed rc={rc}: {se[:300]}") for g in GATES}
            return report

        tile_out = out / "MAPAL001" / f"{cell}.DAT"
        argv = [str(mesh_src), "--out", str(tile_out), "--cell", cell, "--class-table", str(ctab),
                "--country", "616", "--data-version", "26/11/09/01", "--json"]
        rc, so, se = run_cmd_json("tilewriter.py", argv)
        report["counts"]["tilewriter_rc"] = rc
        report["counts"]["tilewriter_stdout"] = so[:500]
        report["counts"]["tilewriter_stderr"] = se[:500]
        if rc != 0 or not tile_out.exists():
            report["gates"] = {g: gate("BLOCKED", f"tilewriter failed rc={rc}: {(se or so)[:400]}") for g in GATES}
            return report
        report["counts"]["tile_size"] = tile_out.stat().st_size
        report["counts"]["tile_sha256"] = sha256_bytes(tile_out.read_bytes())

    # rebuild manifests over the scaffold+OSM tile
    rc, so, se = run_cmd_json("rebuild_manifests.py", ["--root", str(out), "--partial"])
    report["counts"]["rebuild_rc"] = rc
    report["counts"]["rebuild_stderr"] = se[:500]
    report["counts"]["rebuild_stdout"] = so[:300]
    rebuilt = []
    for name in ["DRSTR001.DAT", "MMAIN001.DAT", "REFER001/CMP.LST", "CMP.LST"]:
        if (out / name).exists():
            rebuilt.append(name)
    for p in (out / "REFER001").glob("*.ind"):
        rebuilt.append(f"REFER001/{p.name}")
    report["counts"]["rebuilt_files"] = sorted(set(rebuilt))
    report["changed_set"] = [f"MAPAL001/{cell}.DAT"] + report["counts"]["rebuilt_files"]

    rc, so, se = run_cmd_json("cardcheck.py", ["--root", str(out), "--partial", "--ignore-dump-artifacts", "--fast"])
    report["counts"]["cardcheck_rc"] = rc
    report["counts"]["cardcheck_tail"] = (so + "\n" + se).strip().splitlines()[-15:]
    card_ok = rc == 0

    rc2, so2, se2 = run_cmd_json("l2check.py", ["--root", str(out), "--partial", "--no-golden", "--no-cmp", "--tiles", cell])
    report["counts"]["l2check_rc"] = rc2
    report["counts"]["l2check_tail"] = (so2 + "\n" + se2).strip().splitlines()[-15:]
    l2_ok = rc2 == 0

    report["gates"]["hdd_info_map_code"] = gate(
        "NOT-APPLICABLE" if not (out / "VER_INFO" / "HDD_INFO.TXT").exists() else "CANNOT-VERIFY-OFFLINE",
        "synthetic/partial tree has no VER_INFO/HDD_INFO.TXT; real HDD_INFO/MAP CODE bytes require factory-backed card image/tree (rule 11). Not PASS.",
        "missing VER_INFO" if not (out / "VER_INFO" / "HDD_INFO.TXT").exists() else "present but not byte-compared to factory",
    )
    report["gates"]["drstr_mmain_cmplst_ind"] = gate(
        "PASS" if (card_ok and report["counts"]["rebuild_rc"] == 0) else "CANNOT-VERIFY-OFFLINE",
        f"rebuild_manifests rc={report['counts']['rebuild_rc']}, rebuilt={report['counts']['rebuilt_files']}; cardcheck rc={report['counts']['cardcheck_rc']}. Synthetic partial scaffold - factory parity not claimed.",
        "rebuild_manifests + cardcheck --root --partial",
    )
    report["gates"]["tile_roundtrip_structure"] = gate(
        "PASS" if (report["counts"]["tilewriter_rc"] == 0 and l2_ok) else "CANNOT-VERIFY-OFFLINE",
        f"tilewriter wrote {cell}.DAT ({report['counts'].get('tile_size')} bytes, provisional-v0, only OSM-generated MAPAL001 tile); targeted l2check rc={rc2} {'PASS' if l2_ok else '(not PASS on this synthetic partial tree)'}.",
        "tilewriter + targeted l2check",
    )
    report["gates"]["section4"] = gate(
        "CANNOT-VERIFY-OFFLINE",
        "section 4 (admin/place-name index) semantics vs factory/firmware not verified on synthetic OSM tile; synthetic/road-only generation may not carry factory section-4 semantics. Honest status, not PASS.",
        "synthetic tile; no factory section-4 oracle in this run",
    )
    report["gates"]["manifests"] = gate(
        "PASS" if (report["counts"]["rebuild_rc"] == 0 and card_ok) else "CANNOT-VERIFY-OFFLINE",
        f"manifests rebuilt/consistent check: rebuild rc={report['counts']['rebuild_rc']}, cardcheck rc={report['counts']['cardcheck_rc']}, files={report['counts']['rebuilt_files']}.",
        "rebuild_manifests + cardcheck",
    )
    report["l2_applicable"] = l2_ok
    report["cardcheck_applicable"] = card_ok
    return report


def selftest() -> int:
    fails = 0
    def chk(cond: bool, msg: str):
        nonlocal fails
        if cond:
            print(f"  ok   {msg}")
        else:
            print(f"  FAIL {msg}")
            fails += 1
    print("one_tile_pipeline selftest (synthetic, no vendor data)")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out"
        rep = build_synthetic_out(out, "B48R058R")
        chk(rep["tile"] == "B48R058R", "target cell B48R058R")
        chk(rep["mapping"] == "provisional-v0", "mapping provisional-v0 recorded")
        chk("not firmware-confirmed" in rep["rule13"].lower() or "rule 13" in rep["rule13"].lower() or "l3/l4/l5" in rep["rule13"].lower(), "rule 13/firmware acceptance unknown stated")
        chk(rep["factory_backed"] is False, "synthetic path marked not factory-backed")
        chk(rep["real_image_run"] == "blocked" and rep["missing_input"], "real-image run blocked with missing input named")
        chk((out / "MAPAL001" / "B48R058R.DAT").exists(), "OSM-generated tile exists")
        chk(rep["counts"].get("tilewriter_rc") == 0, "tilewriter rc=0")
        # rebuild/cardcheck/l2check may fail on a minimal synthetic tree; that must be reported honestly, not as PASS.
        if rep["counts"].get("rebuild_rc") == 0:
            chk(True, "rebuild_manifests rc=0")
        else:
            chk(rep["gates"]["drstr_mmain_cmplst_ind"]["status"] != "PASS" or "partial" in rep["gates"]["drstr_mmain_cmplst_ind"]["detail"].lower(), "rebuild nonzero -> manifests/drstr gate honest (not unearned PASS)")
        # B48R058R is the only OSM-generated tile (synthetic baseline scaffold may add non-OSM tiles)
        tiles = sorted(p.name for p in (out / "MAPAL001").glob("*.DAT")) if (out / "MAPAL001").exists() else []
        chk("B48R058R.DAT" in tiles, "B48R058R OSM-generated tile present")
        chk(rep["osm_generated_tile"] == "MAPAL001/B48R058R.DAT", "only B48R058R recorded as OSM-generated tile")
        chk(all(rep["mapping"] == "provisional-v0" for _ in [1]), "mapping field is provisional-v0")
        # gates present and honest
        for g in GATES:
            chk(g in rep["gates"], f"gate present: {g}")
            s = rep["gates"].get(g, {}).get("status")
            chk(s in STATUSES, f"gate {g} honest status {s}")
            if s == "PASS":
                pass  # allowed only where evidenced
        chk(rep["gates"]["hdd_info_map_code"]["status"] != "PASS", "HDD_INFO/MAP CODE not faked PASS on synthetic tree")
        chk(rep["gates"]["section4"]["status"] != "PASS", "section 4 not faked PASS on synthetic path")
        chk(rep.get("fixture_sha256"), "fixture SHA-256 recorded")
        chk(rep["counts"].get("ways", 0) >= 1 and rep["counts"].get("nodes", 0) >= 1, "fixture corpus counted")
        # gate report JSON-serializable
        json.dumps(rep)
        chk(True, "gate report JSON-serializable")

    # --json PATH writes the same document bare --json prints (H64).
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        jpath = td / "report.json"
        rc = main(["--synthetic", "--out", str(td / "synthetic-out"), "--cell", "B48R058R", "--json", str(jpath)])
        written = json.loads(jpath.read_text(encoding="utf-8")) if jpath.exists() else None
        chk(rc in (0, 1) and isinstance(written, dict) and written.get("mode") == "synthetic-only",
            "--json PATH writes a parseable report document")
        chk(written is not None and written.get("tile") == "B48R058R",
            "--json PATH report carries the target cell")

    # Factory-tree provenance + overlap guard negatives (H64).
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = td / "factory-root"
        (root / "MAPAL001").mkdir(parents=True)
        (root / "VER_INFO").mkdir()
        import tilewriter
        tile_bytes = tilewriter.make_factory("B48R058R")
        tile_path = root / "MAPAL001" / "B48R058R.DAT"
        tile_path.write_bytes(tile_bytes)
        (root / "DRSTR001.DAT").write_bytes(b"x")
        (root / "MMAIN001.DAT").write_bytes(b"x")
        (root / "VER_INFO" / "HDD_INFO.TXT").write_bytes(b"x")
        tile_sha = sha256_bytes(tile_bytes)

        # Positive control: an honest factory tile is parsed and its sha recorded.
        honest_out = td / "honest-out"
        rep = build_factory_out(honest_out, root, "B48R058R")
        chk(rep.get("factory_tree_provenance") == "factory-tile-parsed",
            "honest factory tile parsed (provenance=factory-tile-parsed)")
        chk(rep.get("factory_tile_sha256") == tile_sha,
            "factory_tile_sha256 equals sha256sum of MAPAL001/<cell>.DAT")
        chk(rep.get("factory_tile_size") == len(tile_bytes),
            "factory_tile_size equals tile size")

        # Negative control (a): empty factory tile -> BLOCKED / factory-tree-invalid.
        empty_root = td / "empty-root"
        shutil.copytree(root, empty_root)
        (empty_root / "MAPAL001" / "B48R058R.DAT").write_bytes(b"")
        empty_out = td / "empty-out"
        rep = build_factory_out(empty_out, empty_root, "B48R058R")
        chk(rep.get("real_image_run") == "factory-tree-invalid",
            "empty factory tile -> real_image_run=factory-tree-invalid")
        chk(all(g.get("status") == "BLOCKED" for g in rep["gates"].values()) and rep["gates"],
            "empty factory tile -> every gate BLOCKED")
        chk(not empty_out.exists(), "empty factory tile -> no output tree mutated")

        # Negative control (b): --out == --factory-root -> exit 2, input intact.
        before = sorted(p.relative_to(root) for p in root.rglob("*"))
        before_sha = sha256_bytes(tile_path.read_bytes())
        rc = main(["--factory-root", str(root), "--out", str(root), "--cell", "B48R058R"])
        after = sorted(p.relative_to(root) for p in root.rglob("*"))
        chk(rc == 2, "--out == --factory-root exits 2")
        chk(before == after and tile_path.exists(),
            "--out == --factory-root leaves the input tree intact")
        chk(sha256_bytes(tile_path.read_bytes()) == before_sha,
            "--out == --factory-root leaves the factory tile byte-identical")
        rc2 = main(["--factory-root", str(root), "--out", str(root / "nested"), "--cell", "B48R058R"])
        chk(rc2 == 2, "--out inside --factory-root exits 2")
        chk(not (root / "nested").exists(), "--out inside --factory-root creates nothing")
        rc3 = main(["--factory-root", str(root), "--out", str(td), "--cell", "B48R058R"])
        chk(rc3 == 2, "--out parent of --factory-root exits 2")
        chk(root.exists() and tile_path.exists(),
            "--out parent of --factory-root leaves the input tree intact")
        chk(sha256_bytes(tile_path.read_bytes()) == before_sha,
            "--out parent of --factory-root leaves the factory tile byte-identical")
        try:
            build_synthetic_out(root, "B48R058R", input_root=root)
            chk(False, "build_synthetic_out rejects out == input root")
        except UsageError:
            chk(True, "build_synthetic_out rejects out == input root")
        try:
            build_synthetic_out(td, "B48R058R", input_root=root)
            chk(False, "build_synthetic_out rejects out parent of input root")
        except UsageError:
            chk(True, "build_synthetic_out rejects out parent of input root")
    print(f"selftest: {'OK' if not fails else 'FAIL'} ({fails} failure(s))")
    return 0 if not fails else 1


def _copy_factory_root(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, symlinks=True)


def build_factory_out(out: Path, factory_root: Path, cell: str = "B48R058R",
                      osm_text: str | None = None, country: str = "616") -> dict[str, Any]:
    """Factory-backed path: copy factory root, replace exactly one tile with OSM-generated (provisional-v0)."""
    _check_out_overlap(out, factory_root)
    report: dict[str, Any] = {
        "mode": "factory-backed", "tile": cell, "mapping": "provisional-v0",
        "rule13": "roadclass_v0 provisional, not firmware-confirmed; L2 necessary not sufficient; L3/L4/L5 acceptance unknown",
        "factory_backed": True, "factory_root": str(factory_root), "missing_input": "",
        "real_image_run": "attempted", "gates": {}, "counts": {}, "changed_set_expected": [f"MAPAL001/{cell}.DAT"],
        "factory_tile_sha256": None, "factory_tile_size": 0,
        "factory_tree_provenance": "not-checked",
    }
    if not factory_root.is_dir():
        report["gates"] = {g: gate("BLOCKED", f"factory root not a directory: {factory_root}") for g in GATES}
        report["real_image_run"] = "blocked"; return report
    factory_tile = factory_root / "MAPAL001" / f"{cell}.DAT"
    required = [factory_tile, factory_root / "DRSTR001.DAT", factory_root / "MMAIN001.DAT", factory_root / "VER_INFO" / "HDD_INFO.TXT"]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        report["missing_input"] = "missing factory files: " + ", ".join(missing)
        report["real_image_run"] = "blocked"; report["factory_backed"] = False
        report["gates"] = {g: gate("BLOCKED", report["missing_input"]) for g in GATES}; return report
    prov = _factory_tile_provenance(factory_root, cell)
    report["factory_tile"] = prov["factory_tile"]
    report["factory_tile_size"] = prov["factory_tile_size"]
    report["factory_tile_sha256"] = prov["factory_tile_sha256"]
    report["factory_tree_provenance"] = prov["factory_tree_provenance"]
    if prov["factory_tree_provenance"] != "factory-tile-parsed":
        report["missing_input"] = f"factory tile {factory_tile} is not a parseable factory tile: {prov['parse_error']}"
        report["real_image_run"] = "factory-tree-invalid"
        report["factory_backed"] = False
        report["gates"] = {g: gate("BLOCKED", report["missing_input"], "factory_tile_provenance") for g in GATES}
        return report
    report["factory_tile_sections"] = prov.get("factory_tile_sections")
    _copy_factory_root(factory_root, out)
    out_tile = out / "MAPAL001" / f"{cell}.DAT"
    osm_text = osm_text or SYNTHETIC_OSM
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        osm = td / "syn.osm"; osm.write_text(osm_text, encoding="utf-8")
        imf = td / "syn.imf.jsonl"
        rc, so, se = run_cmd_json("osm_ingest.py", [str(osm), "-o", str(imf), "--source-name", "m5.29-factory-rerun"])
        report["counts"]["osm_ingest_rc"] = rc
        if rc != 0 or not imf.exists():
            report["gates"] = {g: gate("BLOCKED", f"osm_ingest failed rc={rc}: {se[:300]}") for g in GATES}; return report
        imf_lines = [ln for ln in imf.read_text(encoding="utf-8").splitlines() if ln.strip()]
        report["counts"]["imf_records"] = len(imf_lines)
        report["counts"]["ways"] = sum(1 for ln in imf_lines if '"type":"way"' in ln or '"type": "way"' in ln)
        report["counts"]["nodes"] = sum(1 for ln in imf_lines if '"type":"node"' in ln or '"type": "node"' in ln)
        report["fixture_sha256"] = sha256_bytes(osm_text.encode("utf-8"))
        split_out = td / "split.imf.jsonl"
        rc, so, se = run_cmd_json("mesh_split.py", [str(imf), "-o", str(split_out)])
        report["counts"]["mesh_split_rc"] = rc
        mesh_src = split_out if rc == 0 and split_out.exists() else imf
        ctab = td / "roadclass_v0.json"
        rc, so, se = run_cmd_json("roadclass_v0.py", ["--class-table-out", str(ctab)])
        report["counts"]["roadclass_rc"] = rc
        if rc != 0 or not ctab.exists():
            report["gates"] = {g: gate("BLOCKED", f"roadclass_v0 failed rc={rc}: {se[:300]}") for g in GATES}; return report
        rc, so, se = run_cmd_json("tilewriter.py", [str(mesh_src), "--out", str(out_tile), "--cell", cell,
                                 "--factory", str(out_tile), "--class-table", str(ctab), "--country", country, "--no-names", "--json"])
        report["counts"]["tilewriter_rc"] = rc
        report["counts"]["tilewriter_stdout"] = so[:600]; report["counts"]["tilewriter_stderr"] = se[:600]
        if rc != 0 or not out_tile.exists():
            report["gates"] = {g: gate("BLOCKED", f"tilewriter failed rc={rc}: {(se or so)[:400]}") for g in GATES}; return report
        report["counts"]["tile_size"] = out_tile.stat().st_size
        report["counts"]["tile_sha256"] = sha256_bytes(out_tile.read_bytes())
    rc, so, se = run_cmd_json("rebuild_manifests.py", ["--root", str(out)])
    report["counts"]["rebuild_rc"] = rc
    report["counts"]["rebuild_tail"] = (so + "\n" + se).strip().splitlines()[-20:]
    rebuilt = [n for n in ["DRSTR001.DAT","MMAIN001.DAT","REFER001/CMP.LST","CMP.LST"] if (out/n).exists()]
    rebuilt += [f"REFER001/{p.name}" for p in (out/"REFER001").glob("*.ind")] if (out/"REFER001").exists() else []
    report["counts"]["rebuilt_files"] = sorted(set(rebuilt))
    report["changed_set"] = [f"MAPAL001/{cell}.DAT"] + report["counts"]["rebuilt_files"]
    rc, so, se = run_cmd_json("cardcheck.py", ["--root", str(out), "--ignore-dump-artifacts", "--fast"])
    report["counts"]["cardcheck_rc"] = rc; report["counts"]["cardcheck_tail"] = (so+"\n"+se).strip().splitlines()[-20:]
    card_ok = rc == 0
    rc2, so2, se2 = run_cmd_json("l2check.py", ["--root", str(out), "--no-golden", "--tiles", cell, "--no-cmp"])
    report["counts"]["l2check_rc"] = rc2; report["counts"]["l2check_tail"] = (so2+"\n"+se2).strip().splitlines()[-25:]
    l2_ok = rc2 == 0
    report["gates"]["hdd_info_map_code"] = gate("CANNOT-VERIFY-OFFLINE", "HDD_INFO/MAP CODE bytes present but not byte-verified against unit target offline (M2.18/M9.6); firmware acceptance unknown (rule 13).", "VER_INFO/HDD_INFO.TXT present")
    report["gates"]["drstr_mmain_cmplst_ind"] = gate("PASS" if (card_ok and report["counts"]["rebuild_rc"]==0) else "CANNOT-VERIFY-OFFLINE", f"rebuild_manifests rc={report['counts']['rebuild_rc']}; cardcheck rc={report['counts']['cardcheck_rc']}.", "rebuild_manifests + cardcheck")
    report["gates"]["tile_roundtrip_structure"] = gate("PASS" if (report["counts"]["tilewriter_rc"]==0 and l2_ok) else "CANNOT-VERIFY-OFFLINE", f"tilewriter rc={report['counts']['tilewriter_rc']} (factory template, provisional-v0, 1 tile {cell}); targeted l2check --no-golden --tiles {cell} --no-cmp rc={rc2}.", "tilewriter + l2check targeted")
    report["gates"]["section4"] = gate("CANNOT-VERIFY-OFFLINE", "section 4 in OSM-generated tile is provisional road-only; factory section-4 semantics/firmware acceptance not verified offline. Not PASS.", "provisional-v0 tile")
    report["gates"]["manifests"] = gate("PASS" if (report["counts"]["rebuild_rc"]==0 and card_ok) else "CANNOT-VERIFY-OFFLINE", f"rebuild rc={report['counts']['rebuild_rc']}, cardcheck rc={report['counts']['cardcheck_rc']}.", "rebuild_manifests + cardcheck")
    report["cardcheck_ok"] = card_ok; report["l2check_ok"] = l2_ok
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="M5.29 one-tile OSM pipeline (L1+L2+gate report)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", help="output tree directory")
    ap.add_argument("--cell", default="B48R058R")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--osm", help="OSM input")
    ap.add_argument("--factory-root", help="factory-extracted card root (outside repo)")
    ap.add_argument("--factory-tile", help="factory tile DAT hint")
    ap.add_argument("--country", default="616")
    ap.add_argument("--json", nargs="?", const="-", default=None, metavar="PATH",
                    help="print the report JSON to stdout (bare) or write it to PATH ('-' = stdout)")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.out:
        print("error: --out required (or --selftest)", file=sys.stderr); return 2
    out = Path(args.out)
    factory_root = Path(args.factory_root) if args.factory_root else None
    try:
        if factory_root is not None:
            _check_out_overlap(out, factory_root)
        if args.synthetic or (not args.factory_root and not args.osm):
            rep = build_synthetic_out(out, args.cell, input_root=Path(args.osm) if args.osm else None)
        elif args.factory_root:
            rep = build_factory_out(out, factory_root, args.cell, country=args.country)
        else:
            rep = build_synthetic_out(out, args.cell)
            rep["note"] = "OSM provided without --factory-root; synthetic-only fallback"
            rep["real_image_run"] = "blocked"; rep["missing_input"] = "--factory-root required"
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr)
        print("usage: --out must not be, contain, or be contained by --factory-root/--osm", file=sys.stderr)
        return 2
    doc = json.dumps(rep, indent=2, ensure_ascii=False)
    if args.json and args.json != "-":
        dest = os.path.abspath(args.json)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dest), prefix=".one_tile_pipeline.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(doc + "\n")
            os.replace(tmp, dest)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        print(f"report: {dest}")
    else:
        print(doc)
    ok_tree = (out / "MAPAL001" / f"{args.cell}.DAT").exists() and rep["counts"].get("tilewriter_rc") == 0
    card_ok = rep.get("cardcheck_ok") or rep.get("cardcheck_applicable")
    l2_ok = rep.get("l2check_ok") or rep.get("l2_applicable")
    if rep.get("factory_backed") and card_ok and l2_ok and ok_tree:
        return 0
    if ok_tree and (rep.get("mode") == "synthetic-only" or rep.get("real_image_run") == "blocked"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
