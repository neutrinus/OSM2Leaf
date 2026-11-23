#!/usr/bin/env python3
"""H56: one-command per-level generated-card progress snapshot.

Composes the existing offline tools on a generated no-vendor fixture and prints
ONE table with columns ``level / runnable PASS / FAIL / SKIP / NOT_COVERED /
NOT_RUNNABLE / BLOCKED / verdict``. L4-emulator and L5-bench rows are readiness
flags only: ``NOT RUN (hardware/QEMU unavailable)`` unless an explicit status
JSON is supplied (PASS requires evidence). SKIP / NOT_COVERED / NOT_RUNNABLE /
BLOCKED / NOT RUN are never counted as PASS (rule 13).

Usage:
    python3 tools/progress_snapshot.py --selftest
    python3 tools/progress_snapshot.py [--out DIR] [--json PATH] [--md PATH]
    python3 tools/progress_snapshot.py --l4-status FILE --l5-status FILE

Exit codes: 0 no runnable FAIL and no baseline regression; 1 a runnable FAIL,
a baseline regression, or a tool/parse error; 2 usage error. No vendor bytes,
no QEMU, no network are used by any step.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
PY = sys.executable

import progress_report as pr  # H27/H47 aggregation, schema v3  # noqa: E402

SCHEMA = "osm2leaf.progress_snapshot/v1"
TASK = "H56"
CLAIMS = [f"C-{n}" for n in range(3720, 3730)]
COLUMNS = ("level", "runnable PASS", "FAIL", "SKIP", "NOT_COVERED",
           "NOT_RUNNABLE", "BLOCKED", "verdict")
LEVELS = ("L1", "L2", "L3", "L4-emulator", "L5-bench")
STATUSES = ("PASS", "FAIL", "SKIP", "NOT_COVERED", "NOT_RUNNABLE", "BLOCKED")
L4_STAGES = ("F0", "F1", "F4")
L5_STAGES = ("S0", "S1", "S2", "S3")
NOT_RUN_NOTE = "NOT RUN (hardware/QEMU unavailable)"


def _run(args: list[str], timeout: int = 600) -> tuple[int, str]:
    try:
        p = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s: {' '.join(args)}"


def _read_json(path: Path) -> tuple[dict | None, str]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return None, f"{path}: {e}"
    if not isinstance(doc, dict):
        return None, f"{path}: not a JSON object"
    return doc, ""


def _snapshot_row(level: str, counts: dict[str, int]) -> dict[str, Any]:
    """Counts already carry separate statuses; PASS is the runnable PASS only."""
    p, f = counts.get("PASS", 0), counts.get("FAIL", 0)
    non_pass = sum(counts.get(s, 0) for s in
                   ("SKIP", "NOT_COVERED", "NOT_RUNNABLE", "BLOCKED"))
    if f:
        verdict = "FAIL"
    elif p == 0:
        uncovered = (counts.get("NOT_COVERED", 0) +
                     counts.get("NOT_RUNNABLE", 0))
        verdict = ("NO RUNNABLE CHECK" if non_pass and not uncovered
                   else "NOT COVERED")
    else:
        verdict = "PASS WITH GAPS" if non_pass else "PASS"
    return {
        "level": level,
        "runnable PASS": p,
        "FAIL": f,
        "SKIP": counts.get("SKIP", 0),
        "NOT_COVERED": counts.get("NOT_COVERED", 0),
        "NOT_RUNNABLE": counts.get("NOT_RUNNABLE", 0),
        "BLOCKED": counts.get("BLOCKED", 0),
        "verdict": verdict,
    }


def _manual_row(level: str, stages: list[dict], note: str) -> dict[str, Any]:
    statuses = [s.get("status", "NOT RUN") for s in stages]
    if any(s not in ("NOT RUN", "PASS", "FAIL") for s in statuses):
        statuses = ["NOT RUN"] * len(statuses)
    if any(s.get("status") == "PASS" and not s.get("evidence")
           for s in stages):
        statuses = ["NOT RUN" if st == "PASS" else st for st in statuses]
    if "FAIL" in statuses:
        verdict = "FAIL"
    elif all(s == "PASS" for s in statuses) and statuses:
        verdict = "PASS"
    else:
        verdict = "NOT RUN"
    return {
        "level": level, "runnable PASS": statuses.count("PASS"),
        "FAIL": statuses.count("FAIL"), "SKIP": 0, "NOT_COVERED": 0,
        "NOT_RUNNABLE": 0, "BLOCKED": 0, "verdict": verdict,
        "stages": [{"stage": s.get("stage"), "status": s.get("status"),
                    "evidence": s.get("evidence")} for s in stages],
        "note": note if verdict == "NOT RUN" else "",
    }


def build_snapshot(out_dir: Path, l4_status: str | None = None,
                   l5_status: str | None = None,
                   l1l2_input: str | None = None,
                   l3_input: str | None = None,
                   baseline_input: str | None = None) -> dict[str, Any]:
    """Run the offline chain and return {rows, inputs, problems, exit_code}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    l1l2_path = out_dir / "l1l2.json"
    matrix_path = out_dir / "matrix.json"
    l3_path = out_dir / "l3.json"
    report_path = out_dir / "progress-report.json"
    baseline = Path(baseline_input) if baseline_input else TOOLS / "fixtures" / "l1l2-matrix-baseline.json"

    if l1l2_input:
        l1l2_path = Path(l1l2_input)
    else:
        rc, out = _run([PY, str(TOOLS / "l1l2_fixtures.py"), "--json",
                        str(l1l2_path), "--no-stdout-md"])
        if rc not in (0, 1) or not l1l2_path.exists():
            problems.append(f"l1l2_fixtures.py rc={rc}: {out.strip()[:240]}")

    baseline_rc = None
    baseline_out = ""
    if l1l2_path.exists():
        cmd = [PY, str(TOOLS / "l1l2_matrix.py"), "--input", str(l1l2_path),
               "--json", str(matrix_path), "--check-baseline", str(baseline)]
        baseline_rc, baseline_out = _run(cmd)
        if baseline_rc not in (0, 1) or not matrix_path.exists():
            problems.append(f"l1l2_matrix.py rc={baseline_rc}: {baseline_out.strip()[:240]}")
    else:
        problems.append("l1l2_matrix.py skipped: no H40 fixture report")

    if l3_input:
        l3_path = Path(l3_input)
        l3_rc, l3_out = 0, ""
    else:
        l3_rc, l3_out = _run([PY, str(TOOLS / "l3check.py"), "--build-corpus",
                              "--json", str(l3_path)])
    if l3_rc != 0 or not l3_path.exists():
        problems.append(f"l3check.py --build-corpus rc={l3_rc}: {l3_out.strip()[:240]}")

    args = [PY, str(TOOLS / "progress_report.py")]
    if matrix_path.exists():
        args += ["--l1l2-matrix-json", str(matrix_path)]
    if l3_path.exists():
        args += ["--l3-json", str(l3_path)]
    if l4_status:
        args += ["--l4-emulator-status", l4_status]
    if l5_status:
        args += ["--l5-status", l5_status]
    args += ["--json", str(report_path), "--no-stdout"]
    rc, out = _run(args)
    if rc != 0 or not report_path.exists():
        problems.append(f"progress_report.py rc={rc}: {out.strip()[:240]}")
        return {"schema": SCHEMA, "task": TASK, "claims": CLAIMS,
                "rows": [], "inputs": {}, "problems": problems,
                "baseline": {}, "exit_code": 1}

    report, err = _read_json(report_path)
    if err:
        problems.append(err)
        report = {}
    matrix_doc, _ = _read_json(matrix_path) if matrix_path.exists() else ({}, "")
    l3_doc, _ = _read_json(l3_path) if l3_path.exists() else ({}, "")

    rows: list[dict[str, Any]] = []
    by_level = (((report.get("l1l2") or {}).get("by_level")) or {})
    for level in ("L1", "L2"):
        if level in by_level:
            rows.append(_snapshot_row(level, by_level[level]))
        else:
            rows.append(_snapshot_row(level, {"NOT_COVERED": 1}))

    l3 = report.get("l3") or {}
    l3_counts: dict[str, int] = {}
    for target in l3.get("targets") or []:
        st = str(target.get("status") or "").upper().replace(" ", "_")
        if st not in STATUSES:
            continue
        l3_counts[st] = l3_counts.get(st, 0) + 1
    if not (l3.get("targets") or []):
        l3_counts["NOT_RUNNABLE"] = 1
    rows.append(_snapshot_row("L3", l3_counts))

    for level, key, stages in (("L4-emulator", "l4_emulator", L4_STAGES),
                               ("L5-bench", "l5_car", L5_STAGES)):
        layer = report.get(key) or {}
        supplied = l4_status if key == "l4_emulator" else l5_status
        if not supplied:
            rows.append(_manual_row(level, [], NOT_RUN_NOTE))
        else:
            rows.append(_manual_row(
                level,
                [{"stage": st.get("stage"), "status": st.get("status"),
                  "evidence": st.get("evidence")}
                 for st in layer.get("stages", []) if st.get("stage") in stages],
                ""))

    baseline_msgs = (matrix_doc or {}).get("baseline", {}).get("messages", [])
    regressions = [m for m in baseline_msgs if m.startswith("REGRESSION:")]
    exit_code = 1 if (problems or any(r["FAIL"] for r in rows) or regressions) else 0
    return {
        "schema": SCHEMA, "task": TASK, "claims": CLAIMS, "rows": rows,
        "inputs": {
            "l1l2": str(l1l2_path), "matrix": str(matrix_path),
            "l3": str(l3_path), "progress_report": str(report_path),
            "baseline": str(baseline), "l4_status": l4_status,
            "l5_status": l5_status,
        },
        "problems": problems,
        "baseline": {"rc": baseline_rc, "messages": baseline_msgs,
                     "regressions": regressions, "output": baseline_out.strip()},
        "firmware_proof_passes": l3.get("firmware_proof_passes", 0),
        "synthetic_passes_not_firmware_proof":
            l3.get("synthetic_passes_not_firmware_proof", 0),
        "exit_code": exit_code,
    }


def render_markdown(snap: dict[str, Any]) -> str:
    lines = [
        f"# H56 per-level generated-card progress snapshot ({snap['schema']})",
        "",
        "| " + " | ".join(COLUMNS) + " |",
        "| " + " | ".join("---" for _ in COLUMNS) + " |",
    ]
    for row in snap["rows"]:
        cells = [str(row.get(c, "")).replace("|", "/") for c in COLUMNS]
        if row["level"] in ("L4-emulator", "L5-bench") and row.get("note"):
            cells[-1] = row["note"]
        lines.append("| " + " | ".join(cells) + " |")
    lines += [
        "",
        f"Rule 13: SKIP / NOT_COVERED / NOT_RUNNABLE / BLOCKED / NOT RUN are "
        "never PASS. L4/L5 are readiness flags only; no emulator or bench "
        "execution is implied.",
    ]
    if snap.get("firmware_proof_passes") is not None:
        lines.append(
            f"L3 firmware-proof PASS={snap['firmware_proof_passes']}, "
            f"synthetic PASS (not firmware proof)="
            f"{snap['synthetic_passes_not_firmware_proof']}.")
    base = snap.get("baseline") or {}
    if base.get("messages"):
        lines.append("Baseline: " + "; ".join(base["messages"]))
    for p in snap.get("problems", []):
        lines.append(f"PROBLEM: {p}")
    return "\n".join(lines) + "\n"


def selftest() -> int:
    count = 0
    errors: list[str] = []

    def ok(cond: bool, msg: str) -> None:
        nonlocal count
        count += 1
        if not cond:
            errors.append(msg)

    row = _snapshot_row("L1", {"PASS": 2, "FAIL": 0, "SKIP": 1,
                               "NOT_COVERED": 1, "NOT_RUNNABLE": 1,
                               "BLOCKED": 1})
    ok(row["runnable PASS"] == 2 and row["FAIL"] == 0, "runnable PASS only")
    ok(row["SKIP"] == 1 and row["NOT_COVERED"] == 1 and
       row["NOT_RUNNABLE"] == 1 and row["BLOCKED"] == 1,
       "non-PASS kept in separate columns")
    ok(row["verdict"] == "PASS WITH GAPS", "PASS with gaps is not bare PASS")
    ok(_snapshot_row("L1", {"SKIP": 1})["verdict"] != "PASS",
       "SKIP alone is never PASS")
    ok(_snapshot_row("L1", {"NOT_RUNNABLE": 1})["verdict"] != "PASS",
       "NOT_RUNNABLE alone is never PASS")
    ok(_snapshot_row("L1", {"BLOCKED": 1})["verdict"] != "PASS",
       "BLOCKED alone is never PASS")
    ok(_snapshot_row("L1", {"NOT_COVERED": 1})["verdict"] == "NOT COVERED",
       "NOT_COVERED level reports NOT COVERED")
    ok(_snapshot_row("L1", {})["verdict"] == "NOT COVERED",
       "empty level reports NOT COVERED")
    ok(_snapshot_row("L1", {"PASS": 1, "FAIL": 1})["verdict"] == "FAIL",
       "FAIL verdict on any runnable failure")
    ok(all(c in COLUMNS for c in ("level", "runnable PASS", "FAIL", "SKIP",
                                  "NOT_COVERED", "NOT_RUNNABLE", "BLOCKED",
                                  "verdict")), "all required columns")
    manual = _manual_row("L4-emulator", [], NOT_RUN_NOTE)
    ok(manual["verdict"] == "NOT RUN" and manual["note"] == NOT_RUN_NOTE,
       "L4/L5 NOT RUN without status JSON")
    ok(_manual_row("L5-bench", [{"stage": "S0", "status": "PASS"}], "")["verdict"]
       == "NOT RUN", "manual PASS without evidence is not auto-accepted")
    ok(_manual_row("L5-bench", [{"stage": "S0", "status": "FAIL"}], "")["verdict"]
       == "FAIL", "manual FAIL is honest")
    ok(_manual_row("L4-emulator", [
        {"stage": "F0", "status": "PASS", "evidence": "e"},
        {"stage": "F1", "status": "PASS", "evidence": "e"},
        {"stage": "F4", "status": "PASS", "evidence": "e"}], "")["verdict"]
       == "PASS", "evidenced manual PASS after status JSON")

    with tempfile.TemporaryDirectory(prefix="h56-selftest-") as td:
        d = Path(td)
        l1l2 = d / "l1l2.json"
        matrix = d / "matrix.json"
        l3 = d / "l3.json"
        l1l2.write_text(json.dumps({"checks": []}), encoding="utf-8")
        rc, _ = _run([PY, str(TOOLS / "l1l2_matrix.py"), "--input", str(l1l2),
                      "--json", str(matrix)])
        ok(rc == 0 and matrix.exists(), "selftest fixture matrix built")
        l3.write_text(json.dumps({
            "schema": "osm2leaf.l3check/v1", "result": "PASS",
            "counts": {"pass": 1, "fail": 0, "skip": 0, "blocked": 1},
            "targets": [
                {"name": "probe", "status": "PASS", "synthetic": True,
                 "l3_claim": False},
                {"name": "blocked", "status": "BLOCKED", "synthetic": False,
                 "l3_claim": False},
            ]}), encoding="utf-8")
        args = [PY, str(TOOLS / "progress_report.py"),
                "--l1l2-matrix-json", str(matrix), "--l3-json", str(l3),
                "--json", str(d / "report.json"), "--no-stdout"]
        rc, out = _run(args)
        ok(rc == 0, f"selftest progress_report rc={rc}: {out[:160]}")
        report, err = _read_json(d / "report.json")
        ok(not err and report.get("l3", {}).get("synthetic_passes_not_firmware_proof") == 1,
           "synthetic PASS not firmware proof")
        ok(report.get("l3", {}).get("firmware_proof_passes", -1) == 0,
           "no firmware proof from synthetic row")
        md = render_markdown({"schema": SCHEMA, "rows": [
            _snapshot_row("L1", {"PASS": 1}),
            _manual_row("L4-emulator", [], NOT_RUN_NOTE),
            _manual_row("L5-bench", [], NOT_RUN_NOTE)],
            "baseline": {}, "problems": [], "firmware_proof_passes": 0,
            "synthetic_passes_not_firmware_proof": 1})
        ok("NOT RUN (hardware/QEMU unavailable)" in md,
           "Markdown renders not-run rows")
        ok("| runnable PASS | FAIL | SKIP | NOT_COVERED | NOT_RUNNABLE | BLOCKED | verdict |" in md,
           "Markdown header matches required columns")

        fixture = d / "l1l2-fixture.json"
        fixture.write_text(json.dumps({"checks": [
            {"id": "l1.synthetic.cardcheck", "status": "PASS",
             "command": "c", "detail": "d"}]}), encoding="utf-8")
        basepath = d / "baseline.json"
        _run([PY, str(TOOLS / "l1l2_matrix.py"), "--input", str(fixture),
              "--write-baseline", str(basepath)])
        snap_good = build_snapshot(d / "snap-good", l1l2_input=str(fixture),
                                   l3_input=str(l3),
                                   baseline_input=str(basepath))
        ok(snap_good["exit_code"] == 0,
           f"synthetic snapshot exit 0: {snap_good['problems']}")
        ok(len(snap_good["rows"]) == 5, "five level rows")
        ok(any(r["level"] == "L4-emulator" and r["verdict"] == "NOT RUN"
               for r in snap_good["rows"]), "L4 NOT RUN in full pipeline")
        ok(any(r["level"] == "L5-bench" and r["verdict"] == "NOT RUN"
               for r in snap_good["rows"]), "L5 NOT RUN in full pipeline")
        mutant = d / "l1l2-mutant.json"
        mutant.write_text(json.dumps({"checks": [
            {"id": "l1.synthetic.cardcheck", "status": "FAIL",
             "command": "c", "detail": "d"}]}), encoding="utf-8")
        snap_bad = build_snapshot(d / "snap-bad", l1l2_input=str(mutant),
                                  l3_input=str(l3),
                                  baseline_input=str(basepath))
        ok(snap_bad["exit_code"] == 1,
           "PASS->FAIL mutation makes the snapshot exit 1")
        ok(any(r["level"] == "L1" and r["FAIL"] == 1
               for r in snap_bad["rows"]), "mutant FAIL counted in FAIL column")
        ok(not any(r["level"] == "L1" and r["runnable PASS"] > 0
                   for r in snap_bad["rows"]), "mutant has no runnable PASS")

    for error in errors:
        print("SELFTEST FAIL:", error)
    print(f"progress_snapshot self-test: {count - len(errors)}/{count} checks OK")
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", metavar="DIR",
                    help="scratch work dir for intermediate JSON (default: temp dir)")
    ap.add_argument("--json", metavar="PATH", help="write snapshot JSON")
    ap.add_argument("--md", metavar="PATH", help="write snapshot Markdown")
    ap.add_argument("--l4-status", metavar="FILE", help="explicit L4 emulator status JSON")
    ap.add_argument("--l5-status", metavar="FILE", help="explicit L5 bench status JSON")
    ap.add_argument("--l1l2-input", metavar="PATH",
                    help="use an existing l1l2_fixtures JSON instead of running the tool")
    ap.add_argument("--l3-input", metavar="PATH",
                    help="use an existing l3check JSON instead of --build-corpus")
    ap.add_argument("--baseline", metavar="PATH",
                    help="baseline JSON (default: H41 committed fixture baseline)")
    ap.add_argument("--no-stdout", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    own_temp = not args.out
    td = tempfile.TemporaryDirectory(prefix="h56-snapshot-") if own_temp else None
    out_dir = Path(td.name) if td else Path(args.out)
    try:
        snap = build_snapshot(out_dir, args.l4_status, args.l5_status,
                              args.l1l2_input, args.l3_input, args.baseline)
        md = render_markdown(snap)
        if args.json:
            Path(args.json).parent.mkdir(parents=True, exist_ok=True)
            Path(args.json).write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
        if args.md:
            Path(args.md).parent.mkdir(parents=True, exist_ok=True)
            Path(args.md).write_text(md, encoding="utf-8")
        if not args.no_stdout:
            sys.stdout.write(md)
        return snap["exit_code"]
    finally:
        if td:
            td.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
