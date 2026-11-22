#!/usr/bin/env python3
"""One-command Poland card proof: compiler -> card -> L1 -> L2 -> L3 bundle (M5.35).

    python3 tools/mkpoland.py --osm EXTRACT --factory IMAGE -o OUT.img \
        --bundle BUNDLE [--position LAT,LON] [--card-mode fresh|reconcile]

Runs the existing M5.11/M5.29 compiler, the M5.10 card builder and the L1/L2/L3
validators as subprocesses.  Every stage verdict comes from *that tool's exit
code* (and, for L3, its JSON result), never from prose.  A SKIP, NOT RUN or
NOT RUNNABLE stage is never promoted to PASS (rule 13): the overall verdict is
``PASS`` only when all six stages passed, otherwise ``NOT_RUNNABLE`` (no stage
failed) or ``FAIL``.

    python3 tools/mkpoland.py --selftest

The self-test runs the no-vendor path on the committed synthetic fixture, then a
negative control that flips one byte in the generated tile: the real
``l2check.py --root`` must fail, the command must exit non-zero and the manifest
must record ``stage=l2, status=FAIL``.

Scratch defaults to ~/projekty/leafre-work/scratch/m5.35 and TMPDIR is pinned
there for subprocesses: the 3.8 GiB /tmp tmpfs on this host returned
``Errno 122 Disk quota exceeded`` for ``mkcard.py --selftest``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
HERE = TOOLS / "tools_ze0"

SCHEMA = "osm2leaf.mkpoland/v1"
STATUSES = ("PASS", "FAIL", "SKIP", "NOT_RUNNABLE", "NOT_IMPLEMENTED")
RULE13 = ("Rule 13: a generated format is accepted only when an L3/L4 run reads "
          "our file. SKIP, NOT RUN and NOT RUNNABLE are never PASS.")
DEFAULT_WORKDIR = Path.home() / "projekty" / "leafre-work" / "scratch" / "m5.35"
DEFAULT_FIXTURE = TOOLS / "fixtures" / "m5.37-splice.osm"
DEFAULT_HEAD = ROOT / "archive" / "head256.img"
DEFAULT_FACTORY = (ROOT / "archive" / "sd-images" /
                   "LEAF_2011-2012_QSD-309-101_navi158_eu.img")
COMPILER = "one_tile_pipeline.py"
STAGE_TOOLS = {
    "factory": ("cardcheck.py", "7z"),
    "compile": (COMPILER, "rebuild_manifests.py"),
    "card": ("mkcard.py",),
    "l1": ("cardcheck.py",),
    "l2": ("l2check.py", "7z"),
    "l3": ("l3check.py",),
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def run(argv: list[str], env: dict[str, str], *, cwd: Path = ROOT,
        timeout: int | None = None) -> subprocess.CompletedProcess:
    """Run a tool; the caller maps ``returncode`` to a stage verdict."""
    return subprocess.run(argv, cwd=str(cwd), env=env, capture_output=True,
                          text=True, errors="replace", timeout=timeout)


def py(tool: str, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    return run([sys.executable, str(TOOLS / tool), *map(str, args)], env=env)


def tail(text: str, n: int = 20) -> list[str]:
    return (text or "").strip().splitlines()[-n:]


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else None
    except (ValueError, OSError):
        return None


def tool_versions() -> dict[str, Any]:
    out: dict[str, Any] = {
        "python": platform.python_version(),
        "zlib_compile": zlib.ZLIB_VERSION,
        "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
    }
    for name in sorted({t for tools in STAGE_TOOLS.values() for t in tools if t.endswith(".py")}):
        p = TOOLS / name
        out[name] = {"path": f"tools/{name}", "sha256": sha256_file(p)} if p.is_file() else "missing"
    try:
        out["one_tile_pipeline_osm_sha256"] = hashlib.sha256(
            __import__("one_tile_pipeline").SYNTHETIC_OSM.encode("utf-8")).hexdigest()
    except Exception as exc:  # noqa: BLE001 - provenance only, never a stage verdict
        out["one_tile_pipeline_osm_sha256"] = f"unavailable: {exc}"
    return out


def overall_verdict(stages: list[dict[str, Any]]) -> str:
    """Pure verdict fold.  SKIP/NOT_RUNNABLE are terminal, never PASS.

    Exposed publicly so the self-test can prove the falsifier: an L3
    NOT_RUNNABLE row cannot make the overall verdict PASS.
    """
    statuses = [s["status"] for s in stages]
    if "FAIL" in statuses:
        return "FAIL"
    if "NOT_IMPLEMENTED" in statuses:
        return "BLOCKED"
    core = {"factory", "compile", "card", "l1", "l2"}
    core_stages = [s for s in stages if s["name"] in core]
    if not core_stages or any(s["status"] != "PASS" for s in core_stages):
        return "INCOMPLETE"
    if all(s["status"] == "PASS" for s in stages):
        return "PASS"
    return "NOT_RUNNABLE"


def change_summary(src_tree: Path, out_tree: Path, out_img: Path) -> dict[str, Any]:
    """Changed files -> the FAT data clusters they occupy in OUT.img.

    File-level content comparison (480 files on EU2011) is used instead of a
    byte-by-byte image diff: ``mkcard.diff_ranges`` walks all 7.6 GB in Python
    and was killed by resource limits on the real image.  The cluster numbers
    come from OUT.img's own FAT via ``mkcard._resolve``/``chain``, so they are
    the real chains the firmware reads, not an estimate.  The UNION of both
    sides is compared (H69): a file deleted from OUT.img is a change and is
    listed in ``deleted_files`` even though it has no cluster to map.
    """
    try:
        import mkcard

        def hashes(root: Path) -> dict[str, str]:
            return {str(p.relative_to(root)): sha256_file(p)
                    for p in root.rglob("*") if p.is_file()}

        before, after = hashes(src_tree), hashes(out_tree)
        # H69: iterate the UNION. A file present in --factory but missing from
        # OUT.img is a change and must be reported, not silently dropped by
        # walking only the output tree.
        union = sorted(set(before) | set(after))
        changed = [rel for rel in union if before.get(rel) != after.get(rel)]
        deleted = [rel for rel in union if rel in before and rel not in after]
        added = [rel for rel in union if rel not in before and rel in after]
        clusters: set[int] = set()
        unresolved: list[str] = []
        with out_img.open("rb") as fh:
            _part, geo, fat = mkcard.open_map_partition(fh)
            for rel in changed:
                if rel in deleted:
                    continue  # no cluster in OUT.img by definition
                try:
                    _entry, cluster = mkcard._resolve(fh, geo, fat, rel)
                    clusters.update(mkcard.chain(fat, cluster))
                except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
                    unresolved.append(f"{rel}: {exc}")
        return {
            "method": "SHA-256 per file in factory/out trees; FAT chain from OUT.img",
            "files_before": len(before),
            "files_after": len(after),
            "files_compared": len(union),
            "changed_files": changed,
            "deleted_files": deleted,
            "added_files": added,
            "changed_cluster_count": len(clusters),
            "changed_clusters": sorted(clusters),
            "unresolved": unresolved,
            "cluster_bytes": geo.cluster_bytes,
            "data_offset": geo.data_offset,
            "note": "Clusters of files whose content differs from --factory; "
                    "deleted files have no OUT.img cluster and are listed in "
                    "deleted_files; FAT/FSInfo and directory entries are not counted.",
        }
    except Exception as exc:  # noqa: BLE001 - evidence must not crash the bundle
        return {"error": f"{type(exc).__name__}: {exc}", "changed_files": [],
                "changed_cluster_count": 0, "changed_clusters": []}


def extract_image(image: Path, dest: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    return run(["7z", "x", "-y", f"-o{dest}", str(image)], env=env)


def _stage(name: str, cmd: list[str], proc: subprocess.CompletedProcess,
           status: str, *, report: Path | None = None,
           note: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "exit_code": proc.returncode,
        "command": " ".join(cmd),
        "stdout_tail": tail(proc.stdout),
        "stderr_tail": tail(proc.stderr),
        "report": str(report) if report else None,
        "note": note,
    }


def _tool_ok(tool: str) -> bool:
    return (TOOLS / tool).is_file()


def run_bundle(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    work: Path = args.workdir.resolve()
    bundle: Path = args.bundle.resolve()
    work.mkdir(parents=True, exist_ok=True)
    bundle.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["TMPDIR"] = str(work)  # keep generated images off the /tmp tmpfs
    osm = args.osm.resolve()
    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "tool": {"name": "tools/mkpoland.py", "sha256": sha256_file(Path(__file__).resolve())},
        "rule13": RULE13,
        "overall": None,
        "exit": None,
        "mode": "synthetic" if args.synthetic else "factory",
        "compiler_entry_point": f"tools/{COMPILER}",
        "inputs": {
            "osm": {"path": str(osm), "sha256": sha256_file(osm), "bytes": osm.stat().st_size},
            "factory_image": None,
            "firmware_head": None,
            "cell": args.cell,
            "parcel": args.parcel,
            "positions": [list(p) for p in args.positions],
            "card_mode": args.card_mode,
            "force_l2_fail": bool(args.force_l2_fail),
        },
        "tools": tool_versions(),
        "stages": [],
        "changed_files": [],
        "changed_clusters": {},
        "l3_targets": [],
        "notes": [],
    }
    stages: list[dict[str, Any]] = manifest["stages"]

    def add(name: str, cmd: list[str], proc: subprocess.CompletedProcess,
            status: str, **kw: Any) -> str:
        stages.append(_stage(name, cmd, proc, status, **kw))
        return status

    # A FAIL anywhere stops the chain; later stages are SKIP, never PASS.
    def stopped() -> bool:
        return any(s["status"] in ("FAIL", "NOT_IMPLEMENTED") for s in stages)

    # ---- Stage 1: factory input -------------------------------------------
    factory_img: Path
    factory_tree = work / "factory-tree"
    if args.synthetic:
        factory_img = work / "factory.img"
        # --generate-fixture writes into an existing dir without clearing it;
        # a prior factory-mode run in the same workdir would otherwise leave
        # 480 vendor-derived files behind and corrupt change_summary.
        if factory_tree.exists():
            shutil.rmtree(factory_tree)
        cmd = ["cardcheck.py", "--generate-fixture", str(factory_tree)]
        p1 = py(cmd[0], *cmd[1:], env=env)
        cmd2 = ["cardcheck.py", "--generate-fixture-image", str(factory_img)]
        p2 = py(cmd2[0], *cmd2[1:], env=env)
        ok = p1.returncode == 0 and p2.returncode == 0
        add("factory", cmd + ["&&"] + cmd2,
            p1 if p1.returncode else p2, "PASS" if ok else "FAIL",
            note="no-vendor cardcheck fixture tree + 100 MiB FAT32 image")
        manifest["inputs"]["factory_image"] = {
            "path": str(factory_img), "generated": True,
            "sha256": sha256_file(factory_img) if factory_img.is_file() else None,
        }
        manifest["notes"].append(
            "Synthetic compiler uses one_tile_pipeline --synthetic (its built-in "
            "SYNTHETIC_OSM); --osm is the named, hashed no-vendor fixture used for "
            "provenance and the compiler's overlap guard. The generated fixture tile "
            "has one 0x2046 directory at (72,936), so the (76,940) fixture geometry "
            "cannot be compiled against it without vendor data. The factory run does "
            "compile the named fixture against the extracted EU2011 root.")
    else:
        factory_img = args.factory.resolve()
        p = extract_image(factory_img, factory_tree, env)
        add("factory", ["7z", "x", "-y", f"-o{factory_tree}", str(factory_img)],
            p, "PASS" if p.returncode == 0 else "FAIL",
            note="extract factory image to a card root for the compiler")
        manifest["inputs"]["factory_image"] = {
            "path": str(factory_img), "generated": False,
            "sha256": sha256_file(factory_img), "bytes": factory_img.stat().st_size,
        }

    # ---- Stage 2: Poland compiler -----------------------------------------
    tree = work / "out-tree"
    # This is our own scratch path; a previous run's tree must not make the
    # compiler refuse with "non-empty existing --out" (one command = repeatable).
    if tree.exists():
        shutil.rmtree(tree)
    compile_json = work / "compile-report.json"
    if stopped():
        p = subprocess.CompletedProcess([], 0, "", "")
        add("compile", [COMPILER], p, "SKIP", note="earlier stage failed")
    elif not _tool_ok(COMPILER):
        p = subprocess.CompletedProcess([], 0, "", "compiler tool missing")
        add("compile", [COMPILER], p, "NOT_IMPLEMENTED",
            note="M5.11 entry point tools/one_tile_pipeline.py is not callable; block on M5.11")
    else:
        if args.synthetic:
            cmd = [sys.executable, str(TOOLS / COMPILER), "--synthetic",
                   "--osm", str(osm), "--out", str(tree), "--cell", args.cell,
                   "--json", str(compile_json)]
        else:
            cmd = [sys.executable, str(TOOLS / COMPILER), "--osm", str(osm),
                   "--factory-root", str(factory_tree), "--out", str(tree),
                   "--cell", args.cell, "--parcel", args.parcel,
                   "--json", str(compile_json)]
        p = run(cmd, env=env)
        status = "PASS" if p.returncode == 0 else "FAIL"
        add("compile", cmd, p, status, report=compile_json,
            note="M5.11/M5.29 one-tile compiler; exit code is the verdict")
        manifest["compiler_report"] = load_json(compile_json)
        cset = (manifest["compiler_report"] or {}).get("changed_set") or []
        manifest["changed_files"] = list(cset)

        # Synthetic scaffolding: the compiler's partial tree has no VER_INFO,
        # which cardcheck --image requires. Copy the generated (no-vendor) file
        # and rebuild manifests; both steps are part of this stage's verdict.
        if args.synthetic and p.returncode == 0:
            hdd_src = factory_tree / "VER_INFO" / "HDD_INFO.TXT"
            if not hdd_src.is_file():
                p = subprocess.CompletedProcess([], 1, "", "missing generated HDD_INFO.TXT")
                stages[-1]["status"] = "FAIL"
                stages[-1]["note"] += "; scaffold failed: no generated HDD_INFO.TXT"
            else:
                (tree / "VER_INFO").mkdir(parents=True, exist_ok=True)
                shutil.copyfile(hdd_src, tree / "VER_INFO" / "HDD_INFO.TXT")
                rp = py("rebuild_manifests.py", "--root", tree, "--partial", env=env)
                stages[-1]["post_steps"] = [{
                    "command": "tools/rebuild_manifests.py --root TREE --partial",
                    "exit_code": rp.returncode,
                    "stdout_tail": tail(rp.stdout, 8),
                }]
                manifest["notes"].append(
                    "Wrapper added VER_INFO/HDD_INFO.TXT from the no-vendor fixture "
                    "and rebuilt manifests so L1 can run on a complete card.")
                if rp.returncode != 0:
                    stages[-1]["status"] = "FAIL"

        # Negative control: corrupt the generated tile body. L1 (headers only)
        # stays PASS; the real l2check on the extracted card must FAIL.
        if args.force_l2_fail and stages[-1]["status"] == "PASS":
            tile = tree / "MAPAL001" / f"{args.cell}.DAT"
            if not tile.is_file():
                stages[-1]["status"] = "FAIL"
                stages[-1]["note"] += "; force-l2-fail: tile missing"
            else:
                data = bytearray(tile.read_bytes())
                offset = min(0x1000, len(data) - 1)
                data[offset] ^= 0xFF
                tile.write_bytes(data)
                manifest["notes"].append(
                    f"force-l2-fail: flipped one byte at 0x{offset:x} in "
                    f"MAPAL001/{args.cell}.DAT (L1 header checks unaffected).")

    # ---- Stage 3: card image ----------------------------------------------
    if stopped():
        p = subprocess.CompletedProcess([], 0, "", "")
        add("card", ["mkcard.py"], p, "SKIP", note="earlier stage failed")
    else:
        cmd = [sys.executable, str(TOOLS / "mkcard.py"), "--from-image",
               str(factory_img), "--tree", str(tree), "-o", str(out)]
        if args.card_mode == "reconcile":
            cmd.append("--reconcile")
        p = run(cmd, env=env)
        add("card", cmd, p, "PASS" if p.returncode == 0 and out.is_file() else "FAIL",
            note="M5.10 card builder; exit code is the verdict")
        if p.returncode == 0 and out.is_file():
            manifest["changed_clusters"] = change_summary(factory_tree, tree, out)
            manifest["inputs"]["output_image"] = {
                "path": str(out), "sha256": sha256_file(out), "bytes": out.stat().st_size,
            }

    # ---- Stage 4: L1 on the card image ------------------------------------
    l1_json = bundle / "l1-report.json"
    if stopped():
        p = subprocess.CompletedProcess([], 0, "", "")
        add("l1", ["cardcheck.py", "--image"], p, "SKIP", note="earlier stage failed")
    else:
        cmd = [sys.executable, str(TOOLS / "cardcheck.py"), "--image", str(out),
               "--json", str(l1_json)]
        p = run(cmd, env=env)
        add("l1", cmd, p, "PASS" if p.returncode == 0 else "FAIL",
            report=l1_json, note="cardcheck --image; exit code is the verdict")

    # ---- Stage 5: L2 on the tree extracted from OUT.img -------------------
    card_tree = work / "card-tree"
    l2_json = bundle / "l2-report.json"
    if stopped():
        p = subprocess.CompletedProcess([], 0, "", "")
        add("l2", ["l2check.py", "--root"], p, "SKIP", note="earlier stage failed")
    else:
        xp = extract_image(out, card_tree, env)
        if xp.returncode != 0:
            add("l2", ["7z", "x", str(out)], xp, "FAIL",
                note="could not extract OUT.img for the L2 --root check")
        else:
            cmd = [sys.executable, str(TOOLS / "l2check.py"), "--root", str(card_tree),
                   "--partial", "--no-golden", "--no-cmp", "--tiles",
                   f"{args.cell}.DAT", "--json", str(l2_json)]
            p = run(cmd, env=env)
            add("l2", cmd, p, "PASS" if p.returncode == 0 else "FAIL",
                report=l2_json,
                note="l2check --root on the tree extracted from OUT.img; exit code is the verdict")

    # ---- Stage 6: L3 card gate --------------------------------------------
    l3_json = bundle / "l3-report.json"
    if stopped():
        p = subprocess.CompletedProcess([], 0, "", "")
        add("l3", ["l3check.py", "--card-gate"], p, "SKIP",
            note="earlier stage failed")
    else:
        head = args.firmware_head.resolve()
        manifest["inputs"]["firmware_head"] = {
            "path": str(head), "present": head.is_file(),
            "sha256": sha256_file(head) if head.is_file() else None,
        }
        cmd = [sys.executable, str(TOOLS / "l3check.py"), "--card-gate",
               "--card", str(out), "--factory", str(factory_img)]
        for lat, lon in args.positions:
            cmd += ["--position", f"{lat},{lon}"]
        cmd += ["--json", str(l3_json)]
        p = run(cmd, env=env)
        doc = load_json(l3_json)
        result = (doc or {}).get("result")
        if p.returncode == 0 and result == "PASS":
            status = "PASS"
        elif p.returncode == 1 or result == "FAIL":
            status = "FAIL"
        else:
            status = "NOT_RUNNABLE"
        add("l3", cmd, p, status, report=l3_json,
            note=f"M9.60 card gate exit {p.returncode}, result {result!r}; "
                 "NOT RUN / exit 3 is NOT_RUNNABLE, never PASS")
        manifest["l3_targets"] = [
            {"row": r.get("row"), "status": r.get("status"),
             "detail": r.get("detail")}
            for r in (doc or {}).get("rows", [])
        ]

    manifest["overall"] = overall_verdict(stages)
    manifest["exit"] = 1 if manifest["overall"] == "FAIL" else (
        3 if manifest["overall"] == "BLOCKED" else 0)
    (bundle / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(bundle / "report.md", manifest)
    return int(manifest["exit"]), manifest


def write_report(path: Path, m: dict[str, Any]) -> None:
    lines = [
        "# Poland card proof bundle (M5.35)", "",
        f"- Schema: `{m['schema']}`",
        f"- Overall: **{m['overall']}** (exit {m['exit']})",
        f"- Mode: {m['mode']}",
        f"- Rule: {RULE13}", "",
        "## Inputs", "",
        f"- OSM: `{m['inputs']['osm']['path']}` SHA-256 `{m['inputs']['osm']['sha256']}`",
    ]
    fi = m["inputs"].get("factory_image") or {}
    lines.append(f"- Factory: `{fi.get('path')}` SHA-256 `{fi.get('sha256')}`"
                 f"{' (generated, no vendor)' if fi.get('generated') else ''}")
    head = m["inputs"].get("firmware_head") or {}
    if head:
        lines.append(f"- Firmware head: `{head.get('path')}` present={head.get('present')} "
                     f"SHA-256 `{head.get('sha256')}`")
    lines += ["", "## Stages", "",
              "| Stage | Verdict | Exit | Command |", "| --- | --- | --- | --- |"]
    for s in m["stages"]:
        cmd = s["command"].replace("|", "\\|")
        lines.append(f"| {s['name']} | {s['status']} | {s['exit_code']} | `{cmd[:160]}` |")
    lines += ["", "## L3 rows (verbatim from `l3check --card-gate` JSON)", ""]
    if m["l3_targets"]:
        for r in m["l3_targets"]:
            lines.append(f"- `{r['row']}`: **{r['status']}** — {r['detail']}")
    else:
        lines.append("- no L3 rows were produced")
    cc = m.get("changed_clusters") or {}
    lines += ["", "## Card diff", "",
              f"- Files before/after/union: {cc.get('files_before')} / "
              f"{cc.get('files_after')} / {cc.get('files_compared')}",
              f"- Deleted from OUT.img: {cc.get('deleted_files')}",
              f"- Changed files: {cc.get('changed_files')}",
              f"- Changed data clusters: {cc.get('changed_cluster_count')}",
              f"- Cluster numbers: {cc.get('changed_clusters')}",
              f"- Changed files (compiler `changed_set`): {m.get('changed_files')}", ""]
    notes = m.get("notes") or []
    if notes:
        lines += ["## Notes", ""] + [f"- {n}" for n in notes] + [""]
    lines += ["A `NOT_RUNNABLE` overall verdict means no stage failed but L3 did "
              "not produce a firmware verdict. It is **not** an acceptance (rule 13).", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def selftest() -> int:
    checks = 0
    fails: list[str] = []

    def chk(cond: bool, msg: str) -> None:
        nonlocal checks
        checks += 1
        if not cond:
            fails.append(msg)

    base = DEFAULT_WORKDIR / "selftest"
    base.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="mkpoland-", dir=base))
    try:
        def do(tag: str, *, force: bool) -> tuple[int, dict[str, Any]]:
            ns = argparse.Namespace(
                osm=DEFAULT_FIXTURE, factory=None, out=root / f"{tag}.img",
                bundle=root / f"bundle-{tag}", workdir=root / f"work-{tag}",
                cell="B48R058R", parcel="76,940",
                positions=[(51.70, 17.45)], firmware_head=DEFAULT_HEAD,
                synthetic=True, force_l2_fail=force, card_mode="fresh")
            return run_bundle(ns)

        rc, good = do("good", force=False)
        chk(rc == 0, f"positive control exit 0, got {rc}")
        chk(good["overall"] == "NOT_RUNNABLE",
            f"synthetic overall honest NOT_RUNNABLE, got {good['overall']}")
        by = {s["name"]: s for s in good["stages"]}
        for name in ("factory", "compile", "card", "l1", "l2"):
            chk(by.get(name, {}).get("status") == "PASS",
                f"positive {name} PASS: {by.get(name, {}).get('status')}")
        chk(by.get("l3", {}).get("status") == "NOT_RUNNABLE",
            f"positive l3 NOT_RUNNABLE: {by.get('l3', {}).get('status')}")
        chk(all(r["status"] == "NOT RUN" for r in good["l3_targets"]),
            "synthetic L3 rows are NOT RUN")
        chk(good["inputs"]["osm"]["sha256"] ==
            "a6300b161d7e642732872d8095b20271a4c956fcfff08a2ae665bb1e408caf25",
            "committed fixture SHA-256 recorded")
        chk(isinstance(good["tools"].get("mkcard.py"), dict) and
            "sha256" in good["tools"]["mkcard.py"], "tool versions recorded")
        chk(good["changed_clusters"].get("changed_cluster_count", 0) >= 1,
            "changed-cluster list non-empty")
        chk((root / "bundle-good" / "manifest.json").is_file() and
            (root / "bundle-good" / "report.md").is_file(), "positive bundle files")
        chk("Rule 13" in (root / "bundle-good" / "report.md").read_text(encoding="utf-8"),
            "report quotes rule 13")
        chk("SYNTHETIC_OSM" in " ".join(good["notes"]),
            "compiler built-in OSM mode disclosed")

        # H69 (navigator round 1): a file present in --factory but deleted
        # from OUT.img must be reported. Plant a sentinel only in the good
        # run's factory tree and re-run the pure mapper against the same
        # OUT.img -- no subprocess and no second card build.
        good_work = root / "work-good"
        sentinel = good_work / "factory-tree" / "DELETED_SENTINEL.DAT"
        sentinel.write_bytes(b"H69 sentinel\n" * 16)
        try:
            dsum = change_summary(good_work / "factory-tree",
                                  good_work / "out-tree", root / "good.img")
            base_before = good["changed_clusters"].get("files_before")
            chk("DELETED_SENTINEL.DAT" in dsum.get("changed_files", []),
                "H69: deleted file listed in changed_files")
            chk("DELETED_SENTINEL.DAT" in dsum.get("deleted_files", []),
                "H69: deleted file listed in deleted_files")
            chk(base_before is not None and
                dsum.get("files_before") == base_before + 1,
                f"H69: both-side count before +1 ({dsum.get('files_before')} vs {base_before})")
            chk(not any("DELETED_SENTINEL" in u for u in dsum.get("unresolved", [])),
                "H69: deleted file skipped for cluster lookup, not an error")
        finally:
            sentinel.unlink()

        rc2, bad = do("bad", force=True)
        by2 = {s["name"]: s for s in bad["stages"]}
        chk(rc2 != 0, f"negative control exit non-zero, got {rc2}")
        chk(by2.get("l2", {}).get("status") == "FAIL",
            f"negative l2 FAIL: {by2.get('l2', {}).get('status')}")
        chk(by2.get("l1", {}).get("status") == "PASS",
            f"negative l1 isolated PASS: {by2.get('l1', {}).get('status')}")
        chk(bad["overall"] == "FAIL", f"negative overall FAIL: {bad['overall']}")
        chk(bad["inputs"]["force_l2_fail"] is True, "forced flag recorded")
        chk("force-l2-fail" in " ".join(bad["notes"]), "forced byte flip disclosed")
        chk((root / "bundle-bad" / "manifest.json").is_file(), "negative bundle files")

        # Falsifier: a NOT_RUNNABLE L3 can never fold to PASS.
        fake = [
            {"name": n, "status": "PASS"}
            for n in ("factory", "compile", "card", "l1", "l2")
        ] + [{"name": "l3", "status": "NOT_RUNNABLE"}]
        chk(overall_verdict(fake) != "PASS", "falsifier: L3 NOT_RUNNABLE not promoted")
        chk(overall_verdict(fake[:-1] + [{"name": "l3", "status": "SKIP"}]) != "PASS",
            "falsifier: L3 SKIP not promoted")
        fake_fail = fake[:-1] + [{"name": "l3", "status": "PASS"}]
        fake_fail[1] = {"name": "compile", "status": "FAIL"}
        chk(overall_verdict(fake_fail) == "FAIL", "any FAIL dominates")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print(f"mkpoland self-test: OK ({checks} checks)" if not fails else
          f"mkpoland self-test: {len(fails)} failure(s): " + "; ".join(fails))
    return 0 if not fails else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--osm", type=Path, help="named OSM extract (committed fixture in CI)")
    ap.add_argument("--factory", type=Path, help="factory card image (required unless --synthetic)")
    ap.add_argument("-o", "--out", type=Path, help="output card image OUT.img")
    ap.add_argument("--bundle", type=Path, help="bundle directory (default: OUT.img parent / bundle)")
    ap.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR,
                    help="scratch root (default: ~/projekty/leafre-work/scratch/m5.35)")
    ap.add_argument("--cell", default="B48R058R")
    ap.add_argument("--parcel", default="76,940")
    ap.add_argument("--position", action="append", default=None, metavar="LAT,LON",
                    help="car position for the L3 mount row, e.g. 51.70,17.45 (repeatable)")
    ap.add_argument("--firmware-head", type=Path, default=DEFAULT_HEAD)
    ap.add_argument("--synthetic", action="store_true", help="no-vendor fixture path")
    ap.add_argument("--force-l2-fail", action="store_true",
                    help="selftest-only: flip one tile byte so the real L2 check fails")
    ap.add_argument("--card-mode", choices=("fresh", "reconcile"), default="fresh")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.osm is None or args.out is None:
        ap.error("--osm and -o/--out are required (or use --selftest)")
    if not args.osm.is_file():
        ap.error(f"OSM input not found: {args.osm}")
    if not args.synthetic and args.factory is None:
        ap.error("--factory is required unless --synthetic")
    if args.factory is not None and not args.factory.is_file():
        ap.error(f"factory image not found: {args.factory}")
    if args.force_l2_fail and not args.synthetic:
        ap.error("--force-l2-fail is a synthetic selftest control only")
    if args.bundle is None:
        args.bundle = args.out.parent / "bundle"
    if args.position is None:
        args.positions = [(51.70, 17.45)]
    else:
        try:
            args.positions = []
            for token in args.position:
                lat, lon = token.split(",", 1)
                args.positions.append((float(lat), float(lon)))
        except ValueError:
            ap.error("--position must be LAT,LON (e.g. 51.70,17.45)")
    rc, manifest = run_bundle(args)
    print(f"mkpoland: overall={manifest['overall']} exit={rc} bundle={args.bundle.resolve()}")
    for s in manifest["stages"]:
        print(f"  {s['name']:<8} {s['status']:<15} exit={s['exit_code']}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
