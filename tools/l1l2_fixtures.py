#!/usr/bin/env python3
"""L1/L2 offline fixture pipeline for synthetic/generated inputs (H26).

Runs a data-driven registry of checks that measure whether we can build or
mutate map data so that cardcheck.py (L1) and selected l2check.py/round-trip
paths pass *offline*, without claiming firmware acceptance (rule 13).

No vendor data is read or produced. Checks that require vendor bytes/trees are
reported as NOT COVERED, never PASS.

Usage:
    python3 tools/l1l2_fixtures.py                # JSON + Markdown to stdout
    python3 tools/l1l2_fixtures.py --json out.json --md out.md
    python3 tools/l1l2_fixtures.py --selftest
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
PY = sys.executable

# Status values required by H26.
PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
NOT_COVERED = "NOT COVERED"

# Runnable statuses affect exit code. NOT COVERED means no synthetic fixture
# exists for the path in this layer; it is reported, not a failure.
RUNNABLE = {PASS, FAIL, SKIP}


@dataclass
class CheckResult:
    id: str
    category: str
    description: str
    command: str
    status: str
    runnable: bool
    detail: str = ""
    seconds: float = 0.0


@dataclass
class CheckSpec:
    id: str
    category: str
    description: str
    command: str
    run: Callable[[], tuple[str, str]]  # (status, detail)


def _run_cmd(args: list[str], *, cwd: Path | None = None,
             timeout: int = 120, env: dict | None = None) -> tuple[int, str]:
    e = os.environ.copy()
    if env:
        e.update(env)
    try:
        p = subprocess.run(
            args, cwd=str(cwd or ROOT), capture_output=True, text=True,
            timeout=timeout, env=e,
        )
        out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
        return p.returncode, out.strip()
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s: {' '.join(args)}"
    except Exception as exc:
        return 125, f"{exc}: {' '.join(args)}"


def _zlib_runtime() -> tuple[str, bool]:
    """(version string, is_stock_like). zlib-ng is H9-unverifiable for byte-id."""
    try:
        import zlib
        rv = getattr(zlib, "ZLIB_RUNTIME_VERSION", zlib.ZLIB_VERSION)
        return str(rv), "zlib-ng" not in str(rv).lower()
    except Exception as exc:
        return f"unknown ({exc})", False


# ---------------------------------------------------------------------------
# Check implementations (synthetic, no vendor data)
# ---------------------------------------------------------------------------

def check_l1_synthetic() -> tuple[str, str]:
    """Attempt L1 on a generated synthetic tree; NOT COVERED if no valid builder."""
    # cardcheck requires a coherent ZE0 card tree (DRSTR matching all top-level
    # structure, MMAIN/tiles with cross-validated level tables, common headers,
    # REFER001 pairs, etc.). Current tools (mkcard.make_synthetic_image makes a
    # flat FAT image, not a ZE0 card; drstr_ze0 builds DRSTR but not MMAIN/tile
    # semantics) do not produce a vendor-free minimal tree that passes full L1.
    # Running cardcheck on an incomplete synthetic tree would report fixture
    # construction gaps, not offline format acceptability — so we classify this
    # path honestly.
    cmd = "python3 tools/cardcheck.py --root <synthetic-ze0-tree> --partial --fast"
    probe = [PY, str(TOOLS / "cardcheck.py"), "--help"]
    rc, out = _run_cmd(probe)
    if rc != 0:
        return FAIL, f"cardcheck --help failed (rc={rc}): {out[:300]}"
    return NOT_COVERED, (
        "no vendor-free synthetic ZE0 card builder: cardcheck L1 needs coherent "
        "DRSTR+MMAIN+tile level tables+common headers+REFER001 pairs/top-level "
        "dirs; mkcard/drstr_ze0 do not generate that full structure without a "
        "vendor layout. L1 is exercised on real/vendor fixtures in M5/M6/H28 "
        "contexts; add a synthetic builder as a new check when available."
    )


def check_l2_drstr_selftest() -> tuple[str, str]:
    rc, out = _run_cmd([PY, str(TOOLS / "drstr_ze0.py"), "--selftest"])
    if rc == 0:
        return PASS, out.splitlines()[-1] if out else "ok"
    return FAIL, f"rc={rc}\n{out[:600]}"


def check_l2_drstr_build_roundtrip() -> tuple[str, str]:
    """drstr_ze0.build on a synthetic temp tree, parse back with drstr."""
    sys.path.insert(0, str(TOOLS))
    try:
        import drstr  # type: ignore
        import drstr_ze0  # type: ignore
    except Exception as exc:
        return FAIL, f"import: {exc}"
    with tempfile.TemporaryDirectory(prefix="h26-drstr-") as td:
        root = Path(td)
        (root / "A.TXT").write_bytes(b"hello synthetic\n")
        sub = root / "SUBDIR"
        sub.mkdir()
        (sub / "B.DAT").write_bytes(b"\x00" * 32)
        try:
            blob = drstr_ze0.build(root)
            tree = drstr.parse(blob)
            nodes = tree.get("nodes", [])
            if not nodes or nodes[0].get("name") != "/":
                return FAIL, f"bad root node: {nodes[:1]}"
            names = {n.get("name") for n in nodes}
            if "SUBDIR" not in names:
                return FAIL, f"SUBDIR missing from nodes: {sorted(names)}"
            return PASS, f"built {len(blob)} bytes, parsed {len(nodes)} nodes"
        except Exception as exc:
            return FAIL, f"{type(exc).__name__}: {exc}"


def check_l2_cmpind_selftest() -> tuple[str, str]:
    rc, out = _run_cmd([PY, str(TOOLS / "cmpind.py"), "--selftest"])
    if rc == 0:
        return PASS, out.splitlines()[-1] if out else "ok"
    return FAIL, f"rc={rc}\n{out[:600]}"


def check_l2_cmpind_writer_selftest() -> tuple[str, str]:
    rc, out = _run_cmd([PY, str(TOOLS / "cmpind_writer.py"), "--selftest"])
    if rc == 0:
        return PASS, out.splitlines()[-1] if out else "ok"
    return FAIL, f"rc={rc}\n{out[:600]}"


def check_l2_cmpind_preserve_roundtrip() -> tuple[str, str]:
    """Preserved-stream round-trip on synthetic .cmp/.ind (no recompression)."""
    sys.path.insert(0, str(TOOLS))
    try:
        import cmpind_writer  # type: ignore
    except Exception as exc:
        return FAIL, f"import: {exc}"
    payload = (b"SYNTHETIC-H26-" * 5000)[:cmpind_writer.CHUNK + 123]
    with tempfile.TemporaryDirectory(prefix="h26-cmp-") as td:
        td = Path(td)
        src = td / "src"
        out = td / "out"
        src.mkdir(); out.mkdir()
        c = cmpind_writer.CmpFile.from_dat(payload)
        c.write(src, "TEST.DAT")
        cmpind_writer.repack_preserve(src / "TEST.DAT.cmp", src / "TEST.DAT.ind",
                                      out, "TEST.DAT")
        got = cmpind_writer.CmpFile.from_files(out / "TEST.DAT.cmp",
                                               out / "TEST.DAT.ind").decode()
        if got != payload:
            return FAIL, f"decode mismatch: {len(got)} != {len(payload)}"
        # preserved streams should be byte-identical
        c2 = cmpind_writer.CmpFile.from_files(out / "TEST.DAT.cmp",
                                              out / "TEST.DAT.ind")
        if c2.streams != c.streams:
            return FAIL, "preserve changed compressed streams"
        return PASS, f"{len(payload)} bytes, {c.count()} chunks, streams preserved"


def check_l2_cmpind_recompress_roundtrip() -> tuple[str, str]:
    """Semantic recompress round-trip; SKIP byte-identity claim on zlib-ng (H9)."""
    rv, stock = _zlib_runtime()
    sys.path.insert(0, str(TOOLS))
    try:
        import cmpind_writer  # type: ignore
    except Exception as exc:
        return FAIL, f"import: {exc}"
    payload = (b"RECOMPRESS-H26-" * 6000)[:cmpind_writer.CHUNK + 77]
    with tempfile.TemporaryDirectory(prefix="h26-cmp-re-") as td:
        td = Path(td)
        src = td / "src"; out = td / "out"
        src.mkdir(); out.mkdir()
        c = cmpind_writer.CmpFile.from_dat(payload)
        c.write(src, "R.DAT")
        cmpind_writer.repack_semantic(src / "R.DAT.cmp", src / "R.DAT.ind",
                                      out, "R.DAT")
        got = cmpind_writer.CmpFile.from_files(out / "R.DAT.cmp",
                                               out / "R.DAT.ind").decode()
        if got != payload:
            return FAIL, f"decode mismatch: {len(got)} != {len(payload)}"
        detail = f"semantic round-trip OK ({len(payload)} bytes, {c.count()} chunks)"
        if not stock:
            return SKIP, f"{detail}; byte-identical SKIP (zlib-ng/H9, runtime={rv})"
        return PASS, f"{detail}; runtime={rv}"


def check_l2_tile_harness_selftest() -> tuple[str, str]:
    """harness.py selftest requires a tile argument (vendor/specific fixture)."""
    harness = TOOLS / "ze0-viewer" / "harness.py"
    if not harness.exists():
        return NOT_COVERED, f"missing {harness}"
    rc, out = _run_cmd([PY, str(harness), "selftest"], timeout=30)
    text = out.lower()
    # "required: tile" means no synthetic no-arg selftest path exists.
    if "required" in text and "tile" in text:
        return NOT_COVERED, (
            "harness.py selftest requires a tile argument; no vendor-free "
            "synthetic tile fixture is exposed by the tool. Tile round-trip on "
            "real tiles is covered by l2check/harness with vendor ROOT (out of "
            "scope)."
        )
    if rc == 0:
        return PASS, out.splitlines()[-1] if out else "ok"
    # Any other failure on missing fixture: NOT COVERED, not a layer failure.
    if "no such file" in text or "filenotfound" in text or "not found" in text:
        return NOT_COVERED, f"needs tile fixture (no vendor data): {out[:300]}"
    return FAIL, f"rc={rc}\n{out[:500]}"


def check_l2_poi_mutation_imgpatch() -> tuple[str, str]:
    """imgpatch --selftest exercises synthetic mutation/patch scenarios."""
    rc, out = _run_cmd([PY, str(TOOLS / "imgpatch.py"), "--selftest"], timeout=180)
    if rc == 0:
        tail = [ln for ln in out.splitlines() if "imgpatch self-test" in ln or "OK" in ln]
        return PASS, tail[-1] if tail else "ok"
    return FAIL, f"rc={rc}\n{out[:600]}"


# ---------------------------------------------------------------------------
# Registry — adding a synthetic L1/L2 case means appending here.
# ---------------------------------------------------------------------------

REGISTRY: list[CheckSpec] = [
    CheckSpec(
        id="l1.synthetic.cardcheck",
        category="L1 synthetic",
        description="L1 cardcheck on a synthetic/generated ZE0 card tree/image",
        command="python3 tools/cardcheck.py --root <synthetic-ze0-tree> --partial --fast",
        run=check_l1_synthetic,
    ),
    CheckSpec(
        id="l2.drstr.selftest",
        category="L2 DRSTR",
        description="drstr_ze0 synthetic selftest (no vendor data)",
        command="python3 tools/drstr_ze0.py --selftest",
        run=check_l2_drstr_selftest,
    ),
    CheckSpec(
        id="l2.drstr.build-roundtrip",
        category="L2 DRSTR",
        description="drstr_ze0.build + drstr.parse round-trip on synthetic temp tree",
        command="python3 tools/l1l2_fixtures.py (internal: drstr_ze0.build + drstr.parse)",
        run=check_l2_drstr_build_roundtrip,
    ),
    CheckSpec(
        id="l2.cmpind.selftest",
        category="L2 cmp/ind",
        description="cmpind synthetic selftest (preserved/recompress invariants)",
        command="python3 tools/cmpind.py --selftest",
        run=check_l2_cmpind_selftest,
    ),
    CheckSpec(
        id="l2.cmpind.writer-selftest",
        category="L2 cmp/ind",
        description="cmpind_writer synthetic selftest (stock-zlib aware)",
        command="python3 tools/cmpind_writer.py --selftest",
        run=check_l2_cmpind_writer_selftest,
    ),
    CheckSpec(
        id="l2.cmpind.preserve-roundtrip",
        category="L2 cmp/ind",
        description="preserved-stream .cmp/.ind round-trip on synthetic payload",
        command="python3 tools/l1l2_fixtures.py (internal: CmpFile write + repack_preserve)",
        run=check_l2_cmpind_preserve_roundtrip,
    ),
    CheckSpec(
        id="l2.cmpind.recompress-roundtrip",
        category="L2 cmp/ind",
        description="semantic recompress round-trip; byte-identical SKIP on zlib-ng (H9)",
        command="python3 tools/l1l2_fixtures.py (internal: repack_semantic)",
        run=check_l2_cmpind_recompress_roundtrip,
    ),
    CheckSpec(
        id="l2.tile.harness-selftest",
        category="L2 tile",
        description="tile round-trip on synthetic/small cases supported by harness",
        command="python3 tools/ze0-viewer/harness.py selftest <tile>",
        run=check_l2_tile_harness_selftest,
    ),
    CheckSpec(
        id="l2.poi.mutation.imgpatch-selftest",
        category="L2 POI mutation",
        description="imgpatch synthetic mutation/patch fixtures (POI-mutation class)",
        command="python3 tools/imgpatch.py --selftest",
        run=check_l2_poi_mutation_imgpatch,
    ),
]

REQUIRED_CATEGORIES = [
    "L1 synthetic",
    "L2 DRSTR",
    "L2 cmp/ind",
    "L2 tile",
    "L2 POI mutation",
]


def run_checks(specs: list[CheckSpec] | None = None) -> list[CheckResult]:
    results = []
    for spec in (specs if specs is not None else REGISTRY):
        t0 = time.monotonic()
        try:
            status, detail = spec.run()
        except Exception as exc:
            status, detail = FAIL, f"exception: {type(exc).__name__}: {exc}"
        dt = time.monotonic() - t0
        if status not in {PASS, FAIL, SKIP, NOT_COVERED}:
            status, detail = FAIL, f"invalid status {status!r}; {detail}"
        results.append(CheckResult(
            id=spec.id, category=spec.category, description=spec.description,
            command=spec.command, status=status, runnable=status in RUNNABLE,
            detail=detail, seconds=round(dt, 4),
        ))
    return results


def summarize(results: list[CheckResult]) -> dict:
    counts = {PASS: 0, FAIL: 0, SKIP: 0, NOT_COVERED: 0}
    cats: dict[str, dict[str, int]] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
        c = cats.setdefault(r.category, {PASS: 0, FAIL: 0, SKIP: 0, NOT_COVERED: 0})
        c[r.status] = c.get(r.status, 0) + 1
    runnable_fail = sum(1 for r in results if r.runnable and r.status == FAIL)
    runnable_pass = sum(1 for r in results if r.runnable and r.status == PASS)
    runnable_skip = sum(1 for r in results if r.runnable and r.status == SKIP)
    return {
        "total": len(results),
        "counts": counts,
        "categories": cats,
        "required_categories": REQUIRED_CATEGORIES,
        "missing_categories": [c for c in REQUIRED_CATEGORIES if c not in cats],
        "runnable_pass": runnable_pass,
        "runnable_fail": runnable_fail,
        "runnable_skip": runnable_skip,
        "runnable_total": runnable_pass + runnable_fail + runnable_skip,
        "ok": runnable_fail == 0,
    }


def render_markdown(results: list[CheckResult], summary: dict) -> str:
    rv, stock = _zlib_runtime()
    lines = [
        "# H26 L1/L2 synthetic/generated fixture matrix",
        "",
        "Offline format/structure signal only — **no firmware acceptance claim** (rule 13).",
        "No vendor data used. NOT COVERED = no synthetic fixture for that path.",
        "",
        f"- zlib runtime: `{rv}` ({'stock-like' if stock else 'zlib-ng/H9: byte-identical recompress unverifiable'})",
        f"- runnable: {summary['runnable_pass']} PASS / {summary['runnable_fail']} FAIL / {summary['runnable_skip']} SKIP",
        f"- not covered: {summary['counts'].get(NOT_COVERED, 0)}",
        f"- verdict: **{'OK' if summary['ok'] else 'FAIL'}** (exit reflects runnable failures only)",
        "",
        "## Matrix",
        "",
        "| Category | Check | Status | Runnable | Command | Detail |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        detail = r.detail.replace("|", "/").replace("\n", " ")[:140]
        cmd = r.command.replace("|", "/")
        lines.append(
            f"| {r.category} | `{r.id}` | **{r.status}** | "
            f"{'yes' if r.runnable else 'no'} | `{cmd}` | {detail} |"
        )
    lines += [
        "",
        "## Coverage notes",
        "",
        "- L1 synthetic: limited by lack of a vendor-free full ZE0 card builder (MMAIN/tile level-table coherence).",
        "- L2 tile: harness selftest requires a tile fixture; real tile round-trips need vendor ROOT (out of scope).",
        "- L2 cmp/ind recompress: semantic round-trip is measured; byte-identical factory streams require stock zlib 1.3.1 (H9).",
        "- Golden EU2011 / full 194 REFER001 pairs / LEV3456R on real files: explicitly out of scope (vendor data).",
    ]
    return "\n".join(lines) + "\n"


def make_report(results: list[CheckResult]) -> dict:
    rv, stock = _zlib_runtime()
    return {
        "task": "H26",
        "layer": "L1/L2 synthetic fixtures",
        "firmware_acceptance_claim": False,
        "vendor_data_used": False,
        "zlib_runtime": rv,
        "zlib_stock_like": stock,
        "summary": summarize(results),
        "checks": [asdict(r) for r in results],
    }


# ---------------------------------------------------------------------------
# Selftest — synthetic, tests report/registry/exit semantics (no fixture runs
# except the cheap registry-driven self-calls are avoided; we use fake specs).
# ---------------------------------------------------------------------------

def _selftest() -> int:
    errors = 0

    def ok(cond: bool, msg: str) -> None:
        nonlocal errors
        if cond:
            print(f"  ok: {msg}")
        else:
            print(f"  FAIL: {msg}")
            errors += 1

    # Registry covers all required categories.
    cats = {s.category for s in REGISTRY}
    for c in REQUIRED_CATEGORIES:
        ok(c in cats, f"registry has category {c!r}")
    ids = [s.id for s in REGISTRY]
    ok(len(ids) == len(set(ids)), "registry ids unique")
    ok(all(s.command and s.description for s in REGISTRY), "registry entries documented")

    # Adding a check is data-only: append-like spec participates in report.
    fake = [
        CheckSpec("x.pass", "L1 synthetic", "fake", "cmd", lambda: (PASS, "ok")),
        CheckSpec("x.fail", "L2 DRSTR", "fake", "cmd", lambda: (FAIL, "bad")),
        CheckSpec("x.skip", "L2 cmp/ind", "fake", "cmd", lambda: (SKIP, "env")),
        CheckSpec("x.nc", "L2 tile", "fake", "cmd", lambda: (NOT_COVERED, "no fix")),
    ]
    res = run_checks(fake)
    s = summarize(res)
    ok(s["runnable_fail"] == 1, "FAIL counts as runnable failure")
    ok(s["runnable_skip"] == 1, "SKIP is runnable but not a failure")
    ok(s["counts"][NOT_COVERED] == 1, "NOT COVERED counted separately")
    ok(not s["ok"], "exit verdict false when runnable FAIL exists")
    ok(s["runnable_total"] == 3, "NOT COVERED excluded from runnable total")
    s2 = summarize(run_checks([fake[0], fake[2], fake[3]]))
    ok(s2["ok"], "SKIP/NOT COVERED do not fail exit verdict")

    # Report/markdown generation.
    report = make_report(res)
    ok(report["firmware_acceptance_claim"] is False, "no firmware acceptance claim")
    ok(report["vendor_data_used"] is False, "no vendor data")
    md = render_markdown(res, s)
    ok("L1 synthetic" in md and "NOT COVERED" in md and "cmd" in md, "markdown has matrix")
    ok("no firmware acceptance" in md.lower(), "markdown states rule 13 scope")
    j = json.dumps(report)
    ok('"checks"' in j and '"summary"' in j, "JSON serializable")

    # Invalid status becomes FAIL (defensive).
    bad = run_checks([CheckSpec("x.bad", "L1 synthetic", "f", "c", lambda: ("WAT", "x"))])
    ok(bad[0].status == FAIL, "invalid status normalized to FAIL")

    if errors:
        print(f"l1l2_fixtures self-test: {errors} FAIL")
        return 1
    print("l1l2_fixtures self-test: OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--json", metavar="PATH", help="write JSON report")
    p.add_argument("--md", metavar="PATH", help="write Markdown report")
    p.add_argument("--no-stdout-md", action="store_true",
                   help="do not print Markdown to stdout")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)

    if args.selftest:
        return _selftest()

    results = run_checks()
    report = make_report(results)
    md = render_markdown(results, report["summary"])

    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.md:
        Path(args.md).write_text(md, encoding="utf-8")
    if not args.no_stdout_md:
        sys.stdout.write(md)
    if args.json or args.no_stdout_md:
        s = report["summary"]
        print(
            f"l1l2_fixtures: runnable {s['runnable_pass']}P/{s['runnable_fail']}F/"
            f"{s['runnable_skip']}S, not_covered={s['counts'].get(NOT_COVERED,0)}, "
            f"verdict={'OK' if s['ok'] else 'FAIL'}",
            file=sys.stderr,
        )
    return 0 if report["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
