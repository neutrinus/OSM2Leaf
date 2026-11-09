#!/usr/bin/env python3
"""L1-L4 progress dashboard (H27): aggregates reader-coverage, claims/TODO/tool
results into one view that separates offline proof, firmware/L3 proof, and
car-required (L4) work. It never promotes L2 to L3/L4 and never auto-passes L4.

Sources of truth remain reader-coverage.md, claims.md, TODO.md and tool
results; this tool aggregates them. No vendor data is read.

Usage:
    python3 tools/progress_report.py                     # run local tools, read repo files
    python3 tools/progress_report.py --json out.json --md out.md
    python3 tools/progress_report.py --l1l2-json l1l2.json --l3-json l3.json
    python3 tools/progress_report.py --selftest
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
PY = sys.executable
SCHEMA = "osm2leaf.progress_report/v2"
SCHEMA_LEGACY = "osm2leaf.progress_report/v1"
TASK = "H27"
CLAIMS = ["C-2770", "C-2771", "C-2772", "C-2773", "C-2774",
          "C-2775", "C-2776", "C-2777", "C-2778", "C-2779"]
LEVEL_MAPPING = {
    "effective_date": "2026-11-09",
    "L1": "structural offline",
    "L2": "semantic/golden offline",
    "L3": "firmware fragments (decoder/decompressor/reader harness on our data)",
    "L4": "full-system emulator (QEMU ze0, M8)",
    "L5": "bench/car (M6)",
    "pre_2026_11_09": {"L4": "bench/car", "L5": "full-system emulator"},
}
# L5 (car/bench, M6): explicit manual mapping. Never auto-passed.
L5_CAR_TASKS = [
    ("S0", "M6.2", "whole-card clone baseline (no changes)"),
    ("S1", "M6.5", "one-variable POI rename on spare card"),
    ("S2", "M6.6", "one-variable tile edit on spare card"),
    ("S3", "M6.7", "routing on a modified tile"),
]
L5_PREREQ = [("prep", "M5.13b", "S1/S2 test cards built (prerequisite)")]
# L4 (full-system emulator, M8): explicit manual/bounded status. Never auto-passed.
L4_EMULATOR_TASKS = [
    ("F0", "M8.A2", "QEMU ze0 machine skeleton / boot plumbing"),
    ("F1", "M8.B5", "kernel/userspace milestone (when defined)"),
    ("F4", "M8.E4", "Navi.exe on generated/factory card reaches map state (emulated)"),
]
L4_PREREQ = [("tooling", "M8.A1", "qemu-ze0 build env")]
# Backward-compatible aliases (v1 callers used L4 for car).
L4_TASKS = L5_CAR_TASKS

RC_HEADER_PREFIX = "| # | File type / path |"
RC_MIN_COLUMNS = 12


@dataclass
class Problem:
    source: str
    message: str


@dataclass
class RCRow:
    num: str
    file_type: str
    gen: str
    format_doc: str
    offline: str
    reader: str
    l3_target: str
    l3_result: str
    f4: str
    cross_year: str
    evidence: str
    next_action: str
    raw: dict = field(default_factory=dict)


def _run_cmd(args: list[str], timeout: int = 180) -> tuple[int, str]:
    try:
        p = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
    except subprocess.TimeoutExpired:
        return 124, f"timeout: {' '.join(args)}"
    except Exception as e:
        return 125, f"{e}: {' '.join(args)}"


def load_json_file(path: Path) -> tuple[Any, list[Problem]]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except Exception as e:
        return None, [Problem(str(path), f"cannot read/parse JSON: {e}")]


def _split_md_table_row(line: str) -> list[str] | None:
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        return None
    # drop outer pipes
    inner = s[1:-1]
    return [c.strip() for c in inner.split("|")]


def parse_reader_coverage(path: Path) -> tuple[dict, list[Problem]]:
    """Parse the main reader-coverage matrix table under an explicit contract.

    Contract (H27): table starts at a header line beginning with RC_HEADER_PREFIX;
    next line is a separator; data rows follow until a blank line or a line not
    starting with '|'. Columns follow the 12-column header in order. If the
    contract is not met, return a partial result plus Problems; never guess.
    """
    problems: list[Problem] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        return {"rows": [], "summary": {}, "contract": "unreadable"}, [Problem(str(path), str(e))]
    lines = text.splitlines()
    header_idx = None
    for i, ln in enumerate(lines):
        if ln.startswith(RC_HEADER_PREFIX):
            header_idx = i
            break
    if header_idx is None:
        problems.append(Problem(str(path), f"matrix header not found (expected prefix {RC_HEADER_PREFIX!r})"))
        return {"rows": [], "summary": {}, "contract": "missing_header"}, problems
    header = _split_md_table_row(lines[header_idx])
    if not header or len(header) < RC_MIN_COLUMNS:
        problems.append(Problem(str(path), f"header has {0 if not header else len(header)} columns, need >= {RC_MIN_COLUMNS}"))
        return {"rows": [], "summary": {}, "contract": "bad_header", "header": header}, problems
    expected_header = [
        "#", "File type / path", "Gen", "Format doc", "Offline proof",
        "Firmware reader (M3)", "L3 target (M9)", "L3 result", "F4 (M8.E4)",
        "Cross-year / market", "Evidence (claims, EXPs)", "Next action",
    ]
    if header[:len(expected_header)] != expected_header:
        problems.append(Problem(str(path), f"header mismatch; got {header!r}; contract requires exact leading columns"))
    # separator
    if header_idx + 1 >= len(lines) or not lines[header_idx + 1].strip().startswith("|"):
        problems.append(Problem(str(path), "missing separator after matrix header"))
        sep_idx = header_idx + 1
    else:
        sep_idx = header_idx + 1
    rows: list[RCRow] = []
    for ln in lines[sep_idx + 1:]:
        if not ln.strip():
            break
        if not ln.strip().startswith("|"):
            break
        cells = _split_md_table_row(ln)
        if cells is None:
            break
        # pad/trim to header length
        while len(cells) < len(header):
            cells.append("")
        cells = cells[:len(header)]
        raw = dict(zip(header, cells))
        rows.append(RCRow(
            num=cells[0], file_type=cells[1], gen=cells[2], format_doc=cells[3],
            offline=cells[4], reader=cells[5], l3_target=cells[6],
            l3_result=cells[7], f4=cells[8], cross_year=cells[9],
            evidence=cells[10], next_action=cells[11], raw=raw,
        ))
    if not rows:
        problems.append(Problem(str(path), "matrix header found but no data rows parsed"))

    def has(s: str, *needles: str) -> bool:
        sl = s.lower()
        return any(n.lower() in sl for n in needles)

    gen_counts = {"generate_exists": 0, "generate_partial": 0, "generate_none": 0,
                  "copy": 0, "absent": 0, "other": 0}
    reader_counts = {"located": 0, "partial": 0, "unlocated": 0, "not_needed": 0, "other": 0}
    l3_counts = {"blocked": 0, "planned": 0, "pass_firmware": 0, "gap": 0, "not_applicable": 0, "other": 0}
    for r in rows:
        g = r.gen
        if has(g, "absent on"):
            gen_counts["absent"] += 1
        elif g.strip().lower().startswith("copy"):
            gen_counts["copy"] += 1
        elif "generate · exists" in g or "generate exists" in g:
            gen_counts["generate_exists"] += 1
        elif "generate · partial" in g:
            gen_counts["generate_partial"] += 1
        elif "generate · none" in g or "generate only for" in g:
            gen_counts["generate_none"] += 1
        else:
            gen_counts["other"] += 1
        rd = r.reader
        if rd.strip().lower().startswith("located") or " located " in (" " + rd + " "):
            reader_counts["located"] += 1
        elif rd.strip().lower().startswith("partial"):
            reader_counts["partial"] += 1
        elif rd.strip().lower().startswith("unlocated"):
            reader_counts["unlocated"] += 1
        elif has(rd, "not needed", "not a file reader"):
            reader_counts["not_needed"] += 1
        else:
            reader_counts["other"] += 1
        lt = r.l3_target + " " + r.l3_result
        if "firmware" in lt.lower() and "pass" in lt.lower() and "no target" not in r.l3_target.lower():
            l3_counts["pass_firmware"] += 1
        elif has(r.l3_target, "gap (see") or has(r.l3_target, "no target — gap"):
            l3_counts["gap"] += 1
        elif has(r.l3_result, "BLOCKED") or has(r.l3_target, "blocked"):
            l3_counts["blocked"] += 1
        elif has(r.l3_target, "planned"):
            l3_counts["planned"] += 1
        elif r.l3_target.strip() in ("—", "-", "") or has(r.l3_target, "no target — nothing", "existence-only", "not registered"):
            l3_counts["not_applicable"] += 1
        else:
            l3_counts["other"] += 1

    return {
        "contract": "ok" if not problems else "ok_with_problems",
        "path": str(path),
        "header": header,
        "row_count": len(rows),
        "rows": [asdict(r) for r in rows],
        "summary": {
            "writer_gen": gen_counts,
            "firmware_reader": reader_counts,
            "l3_matrix": l3_counts,
        },
    }, problems


def parse_todo_tasks(path: Path, task_ids: list[str]) -> tuple[dict, list[Problem]]:
    """Bounded parse: find status/result for specific task IDs only."""
    problems: list[Problem] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        return {}, [Problem(str(path), str(e))]
    found: dict[str, dict] = {}
    for tid in task_ids:
        # match task header line
        m = re.search(rf'(?m)^- \[(?P<chk>[ xX])\] \*\*{re.escape(tid)}\b[^\n]*\n(?P<body>(?:  .*\n|\n)*)', text)
        if not m:
            problems.append(Problem(str(path), f"task {tid} not found"))
            continue
        block = m.group(0)
        status_m = re.search(r'(?m)^\s+- Status:\s*(.+)$', block)
        result_m = re.search(r'(?m)^\s+- Result:\s*(.+)$', block)
        found[tid] = {
            "checked": m.group("chk").lower() == "x",
            "status_line": (status_m.group(1).strip() if status_m else None),
            "result": (result_m.group(1).strip() if result_m else None),
            "contract": "bounded_task_block",
        }
        if not status_m:
            problems.append(Problem(str(path), f"task {tid} has no Status line"))
    return found, problems


def normalize_l1l2(doc: Any, source: str) -> tuple[dict, list[Problem]]:
    problems: list[Problem] = []
    if not isinstance(doc, dict):
        return {"status": "invalid", "source": source}, [Problem(source, "not a JSON object")]
    summary = doc.get("summary")
    checks = doc.get("checks")
    if not isinstance(summary, dict) or not isinstance(checks, list):
        problems.append(Problem(source, "missing summary/checks (expected l1l2_fixtures schema)"))
    out = {
        "layer": "L1/L2",
        "provenance": "offline (synthetic/generated fixtures)",
        "firmware_acceptance_claim": bool(doc.get("firmware_acceptance_claim", False)),
        "vendor_data_used": bool(doc.get("vendor_data_used", True)),
        "source": source,
        "summary": summary or {},
        "checks": checks or [],
        "verdict": (summary or {}).get("ok"),
        "note": "Offline format/structure signal only; never firmware/L3/L4 acceptance (rule 13).",
    }
    if out["firmware_acceptance_claim"]:
        problems.append(Problem(source, "input claims firmware_acceptance_claim=true — dashboard must not promote"))
    return out, problems


def normalize_l3(doc: Any, source: str) -> tuple[dict, list[Problem]]:
    problems: list[Problem] = []
    if not isinstance(doc, dict):
        return {"status": "invalid", "source": source}, [Problem(source, "not a JSON object")]
    targets = doc.get("targets")
    counts = doc.get("counts")
    if not isinstance(targets, list) or not isinstance(counts, dict):
        problems.append(Problem(source, "missing targets/counts (expected l3check schema)"))
    rows = []
    firmware_passes = 0
    synthetic_passes = 0
    for t in (targets or []):
        if not isinstance(t, dict):
            continue
        synthetic = bool(t.get("synthetic"))
        l3_claim = bool(t.get("l3_claim"))
        status = t.get("status")
        is_firmware_proof = (status == "PASS" and not synthetic and l3_claim)
        if status == "PASS" and synthetic:
            synthetic_passes += 1
        if is_firmware_proof:
            firmware_passes += 1
        rows.append({
            "name": t.get("name"),
            "reader": t.get("reader"),
            "status": status,
            "synthetic": synthetic,
            "l3_claim": l3_claim,
            "firmware_proof": is_firmware_proof,
            "reason": t.get("reason"),
            "claims": t.get("claims", []),
        })
    out = {
        "layer": "L3",
        "provenance": "firmware/L3 harness (only non-synthetic l3_claim targets prove firmware reading)",
        "source": source,
        "schema": doc.get("schema"),
        "result": doc.get("result"),
        "counts": counts or {},
        "targets": rows,
        "firmware_proof_passes": firmware_passes,
        "synthetic_passes_not_firmware_proof": synthetic_passes,
        "note": "A synthetic PASS proves the runner/dispatcher path, NOT firmware acceptance. BLOCKED/SKIP claim nothing.",
    }
    if firmware_passes:
        # keep explicit; promotion is allowed only when actually true
        out["firmware_proven"] = True
    else:
        out["firmware_proven"] = False
    return out, problems


def _build_manual_layer(todo_tasks: dict, status_input: dict | None, stages_def, prereq_def,
                        layer: str, provenance: str, note: str, source: str) -> tuple[dict, list[Problem]]:
    problems: list[Problem] = []
    overrides = {}
    if isinstance(status_input, dict):
        overrides = status_input.get("stages") or status_input
    stages = []
    for stage, tid, what in stages_def:
        ov = overrides.get(stage) if isinstance(overrides, dict) else None
        t = todo_tasks.get(tid, {})
        status = "NOT RUN"
        evidence = None
        if isinstance(ov, dict) and ov.get("status") in ("NOT RUN", "PASS", "FAIL"):
            status = ov["status"]
            evidence = ov.get("evidence")
            if status == "PASS" and not evidence:
                problems.append(Problem(source, f"{stage} PASS without evidence; demoted to NOT RUN"))
                status = "NOT RUN"
        stages.append({
            "stage": stage, "task": tid, "what": what, "status": status,
            "todo_checked": t.get("checked"), "todo_status": t.get("status_line"),
            "todo_result": t.get("result"), "evidence": evidence,
        })
    prereq = []
    for kind, tid, what in prereq_def:
        t = todo_tasks.get(tid, {})
        prereq.append({"task": tid, "what": what, "checked": t.get("checked"),
                       "status": t.get("status_line"), "result": t.get("result")})
    return {"layer": layer, "provenance": provenance, "stages": stages,
            "prerequisites": prereq, "note": note}, problems


def build_l5_car(todo_tasks: dict, l5_status_input: dict | None) -> tuple[dict, list[Problem]]:
    return _build_manual_layer(
        todo_tasks, l5_status_input, L5_CAR_TASKS, L5_PREREQ,
        "L5", "bench/car hardware (Marek) — explicit manual status only",
        "L5 cannot be automated in CI. No stage is auto-passed; PASS requires explicit recorded evidence outside this dashboard.",
        "l5-status")


def build_l4_emulator(todo_tasks: dict, l4_status_input: dict | None) -> tuple[dict, list[Problem]]:
    return _build_manual_layer(
        todo_tasks, l4_status_input, L4_EMULATOR_TASKS, L4_PREREQ,
        "L4", "full-system emulator (QEMU ze0, M8) — explicit/bounded status only",
        "L4 emulator progress is tracked via M8 milestones; this dashboard never auto-passes emulator acceptance.",
        "l4-emulator-status")


def build_l4(todo_tasks: dict, l4_status_input: dict | None) -> tuple[dict, list[Problem]]:
    """Backward-compatible alias: v1 L4 = car; maps to v2 L5."""
    return build_l5_car(todo_tasks, l4_status_input)


def claims_brief(path: Path) -> tuple[dict, list[Problem]]:
    problems: list[Problem] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        return {}, [Problem(str(path), str(e))]
    # bounded: count C-IDs and statuses mentioned in table-like rows; not a full parser
    ids = re.findall(r'\bC-\d+\b', text)
    retracted = len(re.findall(r'\bRETRACTED\b', text))
    return {
        "path": str(path),
        "claim_id_mentions": len(ids),
        "unique_claim_ids": len(set(ids)),
        "retracted_mentions": retracted,
        "contract": "bounded_counts_only (claims.md remains source of truth; H27 does not replace claims_check)",
    }, problems


def render_markdown(report: dict) -> str:
    s = report
    lines = []
    lines.append(f"# H27 progress dashboard (L1–L5)")
    lines.append("")
    lines.append(f"- schema: `{s['schema']}` · generated: `{s['generated_at']}`")
    lm = s.get("level_mapping") or {}
    if lm:
        lines.append(f"- **Level mapping (2026-11-09):** L3=fragments, L4=full-system emulator (M8), L5=bench/car (M6). Pre-2026-11-09 L4/L5 swapped.")
    lines.append(f"- **Rule 13 / ladder:** ten raport rozdziela warstwy i nigdy nie podnosi L2 do L3/L4/L5.")
    lines.append("")
    if s.get("problems"):
        lines.append("## Parse/input problems")
        for p in s["problems"]:
            lines.append(f"- `{p['source']}`: {p['message']}")
        lines.append("")

    lines.append("## Udowodnione offline (L1/L2)")
    lines.append("")
    l1l2 = s.get("l1l2") or {}
    if l1l2.get("summary"):
        sm = l1l2["summary"]
        lines.append(f"- verdict: **{'OK' if sm.get('ok') else sm.get('ok')}** (runnable {sm.get('runnable_pass')}P/{sm.get('runnable_fail')}F/{sm.get('runnable_skip')}S, not_covered={sm.get('counts',{}).get('NOT COVERED',0)})")
        lines.append(f"- source: `{l1l2.get('source','')}` · firmware_acceptance_claim={l1l2.get('firmware_acceptance_claim')} · vendor_data_used={l1l2.get('vendor_data_used')}")
    else:
        lines.append("- no L1/L2 JSON provided/run in this report.")
    lines.append(f"- note: {l1l2.get('note','Offline only; never firmware/L3/L4/L5 acceptance.')}")

    lines.append("")
    lines.append("## Udowodnione przez firmware / L3 (tylko realne, nie syntetyczne)")
    lines.append("")
    l3 = s.get("l3") or {}
    if l3.get("targets"):
        lines.append(f"- harness result: `{l3.get('result')}` · firmware proof passes: **{l3.get('firmware_proof_passes',0)}** · synthetic passes (not firmware proof): {l3.get('synthetic_passes_not_firmware_proof',0)}")
        lines.append(f"- counts: {json.dumps(l3.get('counts',{}), ensure_ascii=False)}")
        lines.append("")
        lines.append("| Target | Reader | Status | Synthetic | L3 claim | Firmware proof |")
        lines.append("|---|---|---|---:|---:|---:|")
        for t in l3["targets"]:
            lines.append(f"| {t['name']} | {t['reader']} | **{t['status']}** | {t['synthetic']} | {t['l3_claim']} | {t['firmware_proof']} |")
    else:
        lines.append("- no L3 JSON provided/run in this report.")
    lines.append(f"- note: {l3.get('note','Synthetic PASS is not firmware proof.')}")

    lines.append("")
    lines.append("## Emulator pełnosystemowy (L4, M8, ręczne/ograniczone)")
    lines.append("")
    l4e = s.get("l4_emulator") or s.get("l4") or {}
    for p in l4e.get("prerequisites", []):
        lines.append(f"- prereq `{p['task']}`: checked={p.get('checked')} · {p.get('status')}")
    if l4e.get("stages"):
        lines.append("")
        lines.append("| Stage | Task | Status (manual) | TODO status | Evidence |")
        lines.append("|---|---|---|---|---|")
        for st in l4e.get("stages", []):
            ev = (st.get("evidence") or "").replace("|", "/")
            ts = (st.get("todo_status") or "").replace("|", "/")
            lines.append(f"| {st['stage']} | {st['task']} | **{st['status']}** | {ts} | {ev} |")
    lines.append(f"- note: {l4e.get('note','')}")

    lines.append("")
    lines.append("## Wymaga auta/stanowiska (L5, M6, ręczne)")
    lines.append("")
    l5 = s.get("l5_car") or {}
    for p in l5.get("prerequisites", []):
        lines.append(f"- prereq `{p['task']}`: checked={p.get('checked')} · {p.get('status')}")
    if l5.get("stages"):
        lines.append("")
        lines.append("| Stage | Task | Status (manual) | TODO status | Evidence |")
        lines.append("|---|---|---|---|---|")
        for st in l5.get("stages", []):
            ev = (st.get("evidence") or "").replace("|", "/")
            ts = (st.get("todo_status") or "").replace("|", "/")
            lines.append(f"| {st['stage']} | {st['task']} | **{st['status']}** | {ts} | {ev} |")
    lines.append(f"- note: {l5.get('note','')}")

    lines.append("")
    lines.append("## Reader-coverage (agregat z macierzy)")
    lines.append("")
    rc = s.get("reader_coverage") or {}
    sm = rc.get("summary") or {}
    lines.append(f"- contract: `{rc.get('contract')}` · rows: {rc.get('row_count')} · source: `{rc.get('path','')}`")
    if sm:
        lines.append(f"- writer/gen: `{json.dumps(sm.get('writer_gen',{}), ensure_ascii=False)}`")
        lines.append(f"- firmware reader: `{json.dumps(sm.get('firmware_reader',{}), ensure_ascii=False)}`")
        lines.append(f"- L3 matrix cells: `{json.dumps(sm.get('l3_matrix',{}), ensure_ascii=False)}`")
    lines.append("- source of truth remains `docs/research/reader-coverage.md`; this is an aggregate view.")

    lines.append("")
    lines.append("## Claims/TODO (ograniczony sygnał)")
    lines.append("")
    cl = s.get("claims_brief") or {}
    if isinstance(cl, dict) and cl:
        lines.append(f"- claims mentions (bounded): {cl.get('claim_id_mentions')} ids, {cl.get('unique_claim_ids')} unique, RETRACTED mentions {cl.get('retracted_mentions')} · `{cl.get('contract')}`")
    td = s.get("todo_l4_tasks") or s.get("todo_l5_tasks") or {}
    if td:
        lines.append(f"- L5/M6 task lookup: {', '.join(f'{k}={v.get('checked')}' for k,v in td.items())}")
    lines.append(f"- H27 claim block (reserved): {', '.join(s.get('claims') or [])}")

    lines.append("")
    lines.append("## Mapowanie na regułę 13")
    lines.append("")
    lines.append("- **L1/L2 (offline)**: konieczne, nie wystarczające; ten raport pokazuje je tylko jako offline.")
    lines.append("- **L3 (fragmenty firmware)**: potwierdzenie dopiero gdy target ma zlokalizowany reader i wynik jest nie-syntetycznym `l3_claim` PASS; raport liczy takie przypadki osobno.")
    lines.append("- **L4 (emulator pełnosystemowy, M8)**: integracja software przed autem; status jawny, nigdy auto-PASS.")
    lines.append("- **L5 (auto/stanowisko, M6)**: akceptacja końcowa; zawsze ręczna, nigdy podnoszona z L1–L4.")
    return "\n".join(lines) + "\n"


def build_report(args) -> dict:
    problems: list[Problem] = []
    t0 = time.time()

    # L1/L2
    l1l2 = None
    if getattr(args, "l1l2_json", None):
        doc, p = load_json_file(Path(args.l1l2_json)); problems += p
        if doc is not None:
            l1l2, p = normalize_l1l2(doc, str(args.l1l2_json)); problems += p
    elif getattr(args, "run_tools", False):
        rc, out = _run_cmd([PY, str(TOOLS / "l1l2_fixtures.py"), "--json",
                            "/tmp/opencode/h27-l1l2-auto.json", "--no-stdout-md"])
        doc, p = load_json_file(Path("/tmp/opencode/h27-l1l2-auto.json")); problems += p
        if doc is not None:
            l1l2, p = normalize_l1l2(doc, "l1l2_fixtures.py(auto)"); problems += p
        if rc not in (0, 1):  # 1 means runnable failures, still a report
            problems.append(Problem("l1l2_fixtures.py", f"unexpected exit {rc}"))

    # L3
    l3 = None
    if getattr(args, "l3_json", None):
        doc, p = load_json_file(Path(args.l3_json)); problems += p
        if doc is not None:
            l3, p = normalize_l3(doc, str(args.l3_json)); problems += p
    elif getattr(args, "run_tools", False):
        rc, out = _run_cmd([PY, str(TOOLS / "l3check.py"), "--build-corpus", "--json"])
        try:
            doc = json.loads(out)
        except Exception as e:
            doc = None
            problems.append(Problem("l3check.py(auto)", f"not JSON: {e}; rc={rc}"))
        if doc is not None:
            l3, p = normalize_l3(doc, "l3check.py(auto --build-corpus)"); problems += p

    # reader-coverage
    rc_path = Path(getattr(args, "reader_coverage", None) or (ROOT / "docs/research/reader-coverage.md"))
    rc_doc, p = parse_reader_coverage(rc_path); problems += p

    # TODO/claims
    todo_path = Path(getattr(args, "todo", None) or (ROOT / "TODO.md"))
    l5_ids = [tid for _, tid, _ in L5_CAR_TASKS] + [tid for _, tid, _ in L5_PREREQ]
    l4_ids = [tid for _, tid, _ in L4_EMULATOR_TASKS] + [tid for _, tid, _ in L4_PREREQ]
    all_ids = list(dict.fromkeys(l5_ids + l4_ids))
    todo_tasks, p = parse_todo_tasks(todo_path, all_ids); problems += p
    # backward compat: --l4-status was v1 car status; prefer --l5-status
    l5_status_input = None
    l5_src = getattr(args, "l5_status", None) or getattr(args, "l4_status", None)
    if l5_src:
        l5_status_input, p = load_json_file(Path(l5_src)); problems += p
    l4_status_input = None
    if getattr(args, "l4_emulator_status", None):
        l4_status_input, p = load_json_file(Path(args.l4_emulator_status)); problems += p
    l5, p = build_l5_car({k: todo_tasks[k] for k in l5_ids if k in todo_tasks}, l5_status_input); problems += p
    l4, p = build_l4_emulator({k: todo_tasks[k] for k in l4_ids if k in todo_tasks}, l4_status_input); problems += p
    claims_path = Path(getattr(args, "claims", None) or (ROOT / "docs/research/claims.md"))
    claims, p = claims_brief(claims_path); problems += p

    return {
        "schema": SCHEMA,
        "schema_legacy": SCHEMA_LEGACY,
        "task": TASK,
        "claims": CLAIMS,
        "level_mapping": LEVEL_MAPPING,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_s": round(time.time() - t0, 3),
        "separation": {
            "offline_proven": "L1/L2 only (format/structure, synthetic/vendor-free as scoped)",
            "firmware_l3_proven": "only non-synthetic l3_claim PASS targets (firmware fragments)",
            "emulator_l4": "full-system emulator (M8), explicit/manual status; never auto-passed",
            "car_required_l5": "bench/car (M6) explicit manual S0-S3; never auto-passed",
        },
        "problems": [asdict(p) for p in problems],
        "l1l2": l1l2,
        "l3": l3,
        "reader_coverage": rc_doc,
        "l4_emulator": l4,
        "l5_car": l5,
        # backward-compat aliases (v1: l4 was car)
        "l4": l5,
        "todo_l5_tasks": {k: todo_tasks[k] for k in l5_ids if k in todo_tasks},
        "todo_l4_tasks": {k: todo_tasks[k] for k in l5_ids if k in todo_tasks},
        "claims_brief": claims,
    }


def selftest() -> int:
    errors = 0
    def ok(cond, msg):
        nonlocal errors
        print(f"  {'ok' if cond else 'FAIL'}: {msg}")
        if not cond: errors += 1

    # reader-coverage parser contract
    good = (ROOT / "docs/research/reader-coverage.md")
    rc, probs = parse_reader_coverage(good)
    ok(rc.get("row_count") == 30, f"parses 30 reader-coverage rows, got {rc.get('row_count')}")
    ok(not any("header not found" in p.message for p in probs), "header found")
    ok(rc["summary"]["firmware_reader"]["located"] >= 1, "has located readers")
    ok(rc["summary"]["firmware_reader"]["unlocated"] >= 1, "has unlocated readers")
    bad, probs = parse_reader_coverage(Path("/no/such/file.md"))
    ok(probs and bad["contract"] == "unreadable", "unreadable file reported, not guessed")
    # broken header
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "rc.md"
        p.write_text("| # | Wrong | columns |\n|---|---|---|\n|1|a|b|\n")
        rcb, probs = parse_reader_coverage(p)
        ok(probs, "header mismatch produces problems")
        ok(rcb.get("rows") == [] or rcb.get("row_count", 0) == 0 or probs, "broken contract not silently trusted as 30-row matrix")

    # L1/L2 normalization
    l1, p = normalize_l1l2({
        "firmware_acceptance_claim": False, "vendor_data_used": False,
        "summary": {"ok": True, "runnable_pass": 6, "runnable_fail": 0, "runnable_skip": 1,
                    "counts": {"NOT COVERED": 2}}, "checks": []}, "syn")
    ok(l1["verdict"] is True and not p, "valid l1l2 normalized")
    l1b, p = normalize_l1l2({"firmware_acceptance_claim": True, "summary": {}, "checks": []}, "syn")
    ok(any("promote" in x.message for x in p), "firmware_acceptance_claim=true flagged")

    # L3 normalization: synthetic pass is NOT firmware proof
    l3, p = normalize_l3({"schema": "osm2leaf.l3check/v1", "result": "PASS", "counts": {"pass": 1},
                          "targets": [
                              {"name": "probe", "reader": "synthetic", "status": "PASS", "synthetic": True, "l3_claim": False, "claims": []},
                              {"name": "real", "reader": "drstr", "status": "BLOCKED", "synthetic": False, "l3_claim": False, "claims": []},
                          ]}, "syn")
    ok(l3["firmware_proof_passes"] == 0, "synthetic PASS not counted as firmware proof")
    ok(l3["synthetic_passes_not_firmware_proof"] == 1, "synthetic pass counted separately")
    ok(l3["firmware_proven"] is False, "firmware_proven false when only synthetic")
    l3r, p = normalize_l3({"result": "PASS", "counts": {}, "targets": [
        {"name": "real", "reader": "drstr", "status": "PASS", "synthetic": False, "l3_claim": True, "claims": []}]}, "syn")
    ok(l3r["firmware_proof_passes"] == 1 and l3r["firmware_proven"] is True, "real l3_claim PASS is firmware proof")

    # L5 (car) never auto-passes; build_l4 alias remains backward-compatible
    todo = {"M6.2": {"checked": False, "status_line": "open", "result": None},
            "M6.5": {"checked": False, "status_line": "open", "result": None},
            "M6.6": {"checked": False, "status_line": "open", "result": None},
            "M6.7": {"checked": False, "status_line": "open", "result": None},
            "M5.13b": {"checked": True, "status_line": "done", "result": "EXP"}}
    l5, p = build_l5_car(todo, None)
    ok(all(s["status"] == "NOT RUN" for s in l5["stages"]), "L5/car defaults to NOT RUN, never auto-pass")
    ok(l5["layer"] == "L5", "car layer is L5")
    l5p, p = build_l5_car(todo, {"S1": {"status": "PASS"}})
    ok(l5p["stages"][1]["status"] == "NOT RUN", "L5 PASS without evidence demoted")
    ok(any("demoted" in x.message for x in p), "demotion reported")
    l5e, p = build_l5_car(todo, {"S1": {"status": "PASS", "evidence": "EXP-... photo"}})
    ok(l5e["stages"][1]["status"] == "PASS" and not p, "L5 PASS with explicit evidence accepted")
    # v1 compat alias
    l4c, p = build_l4(todo, None)
    ok(l4c["layer"] == "L5" and l4c["stages"] == l5["stages"], "build_l4 alias returns car-as-L5 (v1 compat)")
    # L4 emulator never auto-passes
    todo_m8 = {"M8.A2": {"checked": False, "status_line": "blocked", "result": None},
               "M8.B5": {"checked": False, "status_line": "open", "result": None},
               "M8.E4": {"checked": False, "status_line": "open", "result": None},
               "M8.A1": {"checked": True, "status_line": "done", "result": "EXP"}}
    l4m, p = build_l4_emulator(todo_m8, None)
    ok(all(s["status"] == "NOT RUN" for s in l4m["stages"]), "L4/emulator defaults to NOT RUN")
    ok(l4m["layer"] == "L4", "emulator layer is L4")

    # full report on synthetic inputs
    class A: pass
    a = A()
    a.l1l2_json = a.l3_json = a.reader_coverage = a.todo = a.claims = None
    a.l4_status = a.l5_status = a.l4_emulator_status = None
    a.run_tools = False
    a.reader_coverage = str(ROOT / "docs/research/reader-coverage.md")
    a.todo = str(ROOT / "TODO.md")
    a.claims = str(ROOT / "docs/research/claims.md")
    report = build_report(a)
    ok(report["schema"] == SCHEMA, "schema v2 set")
    ok(report.get("schema_legacy") == SCHEMA_LEGACY, "legacy schema noted")
    ok(report["level_mapping"]["L4"] == "full-system emulator (QEMU ze0, M8)", "mapping L4=emulator")
    ok(report["level_mapping"]["L5"] == "bench/car (M6)", "mapping L5=car")
    ok(report["separation"]["emulator_l4"], "separation states emulator L4")
    ok(report["separation"]["car_required_l5"], "separation states car L5")
    ok(report["l4_emulator"]["layer"] == "L4" and report["l5_car"]["layer"] == "L5", "layer fields correct")
    ok(report["l4"] == report["l5_car"], "v1 compat alias l4->car")
    md = render_markdown(report)
    for must in ["Udowodnione offline", "Udowodnione przez firmware", "Emulator pełnosystemowy (L4, M8", "Wymaga auta/stanowiska (L5, M6", "nigdy nie podnosi L2 do L3/L4/L5", "regułę 13", "Level mapping"]:
        ok(must in md, f"markdown contains {must!r}")
    ok("S0" in md and "S1" in md and "F0" in md, "markdown has L5 car stages and L4 emulator stages")
    ok(json.dumps(report), "report is JSON-serializable")

    if errors:
        print(f"progress_report selftest: {errors} FAIL")
        return 1
    print("progress_report selftest: OK")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", metavar="PATH", help="write JSON report")
    ap.add_argument("--md", metavar="PATH", help="write Markdown report")
    ap.add_argument("--l1l2-json", help="H26/l1l2_fixtures JSON input")
    ap.add_argument("--l3-json", help="l3check --json input")
    ap.add_argument("--reader-coverage", help="reader-coverage.md path")
    ap.add_argument("--todo", help="TODO.md path")
    ap.add_argument("--claims", help="claims.md path")
    ap.add_argument("--l5-status", help="explicit L5 car/bench status JSON ({stages:{S0:{status,evidence}}})")
    ap.add_argument("--l4-status", help="backward-compat alias for --l5-status (v1: car was L4)")
    ap.add_argument("--l4-emulator-status", help="explicit L4 emulator/M8 status JSON ({stages:{F0:{status,evidence}}})")
    ap.add_argument("--run-tools", action="store_true", help="run l1l2_fixtures/l3check (no vendor data)")
    ap.add_argument("--no-stdout", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    report = build_report(args)
    md = render_markdown(report)
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.md:
        Path(args.md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md).write_text(md, encoding="utf-8")
    if not args.no_stdout:
        sys.stdout.write(md)
    # exit 0 if report generated (problems are reported, not a crash); tool failures
    # in inputs are visible in problems. Keep simple/honest.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
