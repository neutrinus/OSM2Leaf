#!/usr/bin/env python3
"""L1-L5 progress dashboard (H27/H47): aggregates reader-coverage, claims/TODO/
tool results into one view that separates offline proof, firmware/L3 proof,
emulator L4 (M8), and car/bench L5 (M6). It never promotes L2 to L3/L4/L5 and
never auto-passes manual L4/L5 states.

H47 extends the input/output contract (schema v3, backward-compatible with v2/
v1 consumers of stable top-level fields) to accept:
- H41 per-file/per-feature generated-fixture L1/L2 matrix JSON (auto-detected;
  stable row keys level,file,feature,status,command,reason; provisional schema,
  unknown-key tolerant).
- H43 generated-corpus L3 JSON (auto-detected; provisional corpus/evidence
  fields such as ran_on_our_generated_data, corpus_kind, evidence_kind). Generated-
  fixture corpus runs are reported separately and never promoted to firmware
  proof unless explicitly marked (non-synthetic l3_claim/firmware_proof PASS).

Sources of truth remain reader-coverage.md, claims.md, TODO.md and tool
results; this tool aggregates them. No vendor data is read.

Usage:
    python3 tools/progress_report.py                     # run local tools, read repo files
    python3 tools/progress_report.py --json out.json --md out.md
    python3 tools/progress_report.py --l1l2-json l1l2.json --l3-json l3.json
    python3 tools/progress_report.py --l1l2-matrix-json h41.json --l3-corpus-json h43.json
    python3 tools/progress_report.py --selftest

JSON output documents schema version and field contract in
``schema``/``schema_version``/``schema_contract``.
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
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
PY = sys.executable

try:
    import progress_schema as ps  # H47 schema contract
except Exception:  # pragma: no cover - keeps tool runnable if module missing
    ps = None

SCHEMA = "osm2leaf.progress_report/v3"
SCHEMA_V2 = "osm2leaf.progress_report/v2"
SCHEMA_LEGACY = "osm2leaf.progress_report/v1"
TASK = "H27"
CLAIMS = ["C-2770", "C-2771", "C-2772", "C-2773", "C-2774",
          "C-2775", "C-2776", "C-2777", "C-2778", "C-2779"]
H47_CLAIMS = ["C-3360", "C-3361", "C-3362", "C-3363", "C-3364",
              "C-3365", "C-3366", "C-3367", "C-3368", "C-3369"]
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


def _looks_like_l1l2_matrix(doc: dict) -> bool:
    schema = str(doc.get("schema") or "").lower()
    if "l1l2_matrix" in schema or "h41" in schema:
        return True
    for key in ("rows", "matrix", "per_file_feature", "entries"):
        if isinstance(doc.get(key), list):
            return True
    checks = doc.get("checks")
    if isinstance(checks, list) and checks:
        c0 = checks[0] if isinstance(checks[0], dict) else {}
        if {"level", "file", "feature"}.intersection(c0):
            return True
    return False


def normalize_l1l2_matrix(doc: Any, source: str) -> tuple[dict, list[Problem]]:
    """H41 per-file/per-feature matrix (provisional, unknown-key tolerant)."""
    problems: list[Problem] = []
    if not isinstance(doc, dict):
        return {"status": "invalid", "source": source}, [Problem(source, "not a JSON object")]
    rows_raw = None
    for key in ("rows", "matrix", "per_file_feature", "checks", "entries"):
        if isinstance(doc.get(key), list):
            rows_raw = doc[key]
            break
    if rows_raw is None:
        problems.append(Problem(source, "H41 matrix: missing rows/matrix/checks list"))
        rows_raw = []
    allowed = ("PASS", "FAIL", "SKIP", "NOT_COVERED", "NOT_RUNNABLE")
    counts = {s: 0 for s in allowed}
    counts["UNKNOWN"] = 0
    by_level: dict[str, dict[str, int]] = {}
    by_file: dict[str, dict[str, int]] = {}
    by_feature: dict[str, dict[str, int]] = {}
    rows = []
    for item in rows_raw:
        if not isinstance(item, dict):
            problems.append(Problem(source, "matrix row is not an object"))
            continue
        status = ps.normalize_status(item.get("status"), allowed) if ps else str(item.get("status") or "").upper()
        if status not in counts:
            status = "UNKNOWN"
        counts[status] += 1
        level = str(item.get("level") or "unknown")
        fname = str(item.get("file") or "unknown")
        feature = str(item.get("feature") or "unknown")
        by_level.setdefault(level, {s: 0 for s in [*allowed, "UNKNOWN"]})[status] += 1
        by_file.setdefault(fname, {s: 0 for s in [*allowed, "UNKNOWN"]})[status] += 1
        by_feature.setdefault(feature, {s: 0 for s in [*allowed, "UNKNOWN"]})[status] += 1
        row = {
            "level": level,
            "file": fname,
            "feature": feature,
            "status": status,
            "command": item.get("command"),
            "reason": item.get("reason"),
            # preserve known H41/TBD extension fields without guessing
            "corpus_kind": item.get("corpus_kind"),
            "generated_fixture": item.get("generated_fixture"),
            "fixture": item.get("fixture"),
        }
        # preserve extra unknown keys for forward compat
        for k, v in item.items():
            if k not in row:
                row[k] = v
        rows.append(row)
    runnable_pass = counts["PASS"]
    runnable_fail = counts["FAIL"]
    non_pass_separated = counts["SKIP"] + counts["NOT_COVERED"] + counts["NOT_RUNNABLE"]
    out = {
        "kind": "l1l2_matrix",
        "layer": "L1/L2",
        "provenance": "offline generated-fixture matrix (H41 contract, provisional)",
        "firmware_acceptance_claim": bool(doc.get("firmware_acceptance_claim", False)),
        "vendor_data_used": bool(doc.get("vendor_data_used", False)),
        "source": source,
        "schema": doc.get("schema") or (ps.SCHEMA_L1L2_MATRIX if ps else "osm2leaf.l1l2_matrix/provisional"),
        "matrix_contract": (ps.CONTRACT["l1l2_matrix_input"] if ps else None),
        "rows": rows,
        "counts": counts,
        "summary": {
            "total": len(rows),
            "pass": runnable_pass,
            "fail": runnable_fail,
            "skip": counts["SKIP"],
            "not_covered": counts["NOT_COVERED"],
            "not_runnable": counts["NOT_RUNNABLE"],
            "unknown": counts["UNKNOWN"],
            "non_pass_separated": non_pass_separated,
            "ok": runnable_fail == 0 and counts["UNKNOWN"] == 0,
        },
        "by_level": by_level,
        "by_file": by_file,
        "by_feature": by_feature,
        "note": "Offline generated-fixture per-file/per-feature signal only; SKIP/NOT_COVERED/NOT_RUNNABLE are separated from PASS and never firmware/L3/L4/L5 acceptance (rule 13).",
    }
    if out["firmware_acceptance_claim"]:
        problems.append(Problem(source, "input claims firmware_acceptance_claim=true — dashboard must not promote"))
    return out, problems


def normalize_l1l2(doc: Any, source: str) -> tuple[dict, list[Problem]]:
    problems: list[Problem] = []
    if not isinstance(doc, dict):
        return {"status": "invalid", "source": source}, [Problem(source, "not a JSON object")]
    # H47 auto-detect: H41 matrix shape takes the matrix path but also keeps
    # legacy-compatible fields where present.
    if _looks_like_l1l2_matrix(doc):
        matrix, probs = normalize_l1l2_matrix(doc, source)
        problems += probs
        # synthesize legacy fields for v1/v2 consumers
        if "summary" not in matrix or not isinstance(matrix.get("summary"), dict):
            matrix["summary"] = {}
        if "checks" not in matrix:
            matrix["checks"] = matrix.get("rows", [])
        matrix["verdict"] = matrix.get("summary", {}).get("ok")
        return matrix, problems
    summary = doc.get("summary")
    checks = doc.get("checks")
    if not isinstance(summary, dict) or not isinstance(checks, list):
        problems.append(Problem(source, "missing summary/checks (expected l1l2_fixtures schema)"))
    out = {
        "kind": "l1l2_legacy",
        "layer": "L1/L2",
        "provenance": "offline (synthetic/generated fixtures)",
        "firmware_acceptance_claim": bool(doc.get("firmware_acceptance_claim", False)),
        "vendor_data_used": bool(doc.get("vendor_data_used", True)),
        "source": source,
        "schema": doc.get("schema") or (ps.SCHEMA_L1L2_LEGACY if ps else "l1l2_fixtures"),
        "summary": summary or {},
        "checks": checks or [],
        "verdict": (summary or {}).get("ok"),
        "note": "Offline format/structure signal only; never firmware/L3/L4 acceptance (rule 13).",
    }
    if out["firmware_acceptance_claim"]:
        problems.append(Problem(source, "input claims firmware_acceptance_claim=true — dashboard must not promote"))
    return out, problems


def _looks_like_l3_corpus(doc: dict) -> bool:
    schema = str(doc.get("schema") or "").lower()
    if "l3_corpus" in schema or "h43" in schema or "generated_corpus" in schema:
        return True
    targets = doc.get("targets") or doc.get("entries") or []
    if isinstance(targets, list):
        for t in targets:
            if isinstance(t, dict) and any(k in t for k in (
                    "ran_on_our_generated_data", "corpus_kind", "corpus",
                    "evidence_kind", "generated_fixture")):
                return True
    return False


def normalize_l3(doc: Any, source: str) -> tuple[dict, list[Problem]]:
    problems: list[Problem] = []
    if not isinstance(doc, dict):
        return {"status": "invalid", "source": source}, [Problem(source, "not a JSON object")]
    targets = doc.get("targets")
    if targets is None and isinstance(doc.get("entries"), list):
        targets = doc.get("entries")
    counts = doc.get("counts")
    if not isinstance(targets, list) or (counts is not None and not isinstance(counts, dict)):
        if not isinstance(targets, list):
            problems.append(Problem(source, "missing targets/entries (expected l3check/l3_corpus schema)"))
        if counts is not None and not isinstance(counts, dict):
            problems.append(Problem(source, "counts must be an object when present"))
    targets = targets or []
    counts = counts or {}
    corpus_aware = _looks_like_l3_corpus(doc)
    rows = []
    firmware_passes = 0
    synthetic_passes = 0
    harness_only_passes = 0
    generated_fixture_targets = 0
    generated_fixture_firmware_proof_passes = 0
    by_corpus = {k: {"pass": 0, "fail": 0, "skip": 0, "blocked": 0, "not_runnable": 0, "total": 0}
                 for k in ("synthetic", "vendor", "factory", "generated_fixture", "unknown")}
    by_evidence = {k: 0 for k in ("firmware_proof", "harness_only", "unknown")}
    for t in targets:
        if not isinstance(t, dict):
            continue
        synthetic = bool(t.get("synthetic"))
        l3_claim = bool(t.get("l3_claim"))
        status = str(t.get("status") or "")
        ran_on_generated = t.get("ran_on_our_generated_data")
        corpus_kind = ps.normalize_corpus_kind(
            t.get("corpus_kind") or t.get("corpus") or t.get("corpus_type"),
            synthetic=synthetic, ran_on_generated=ran_on_generated,
        ) if ps else ("synthetic" if synthetic else "unknown")
        explicit_fp = t.get("firmware_proof")
        if explicit_fp is True:
            is_firmware_proof = (status == "PASS" and not synthetic)
        elif explicit_fp is False:
            is_firmware_proof = False
        else:
            is_firmware_proof = (status == "PASS" and not synthetic and l3_claim)
        evidence_kind = ps.normalize_evidence_kind(
            t.get("evidence_kind"), firmware_proof=is_firmware_proof,
            l3_claim=l3_claim, synthetic=synthetic, status=status,
        ) if ps else ("firmware_proof" if is_firmware_proof else ("harness_only" if synthetic else "unknown"))
        # rule 13 hardening
        if synthetic or corpus_kind == "synthetic":
            is_firmware_proof = False
            if evidence_kind == "firmware_proof":
                evidence_kind = "harness_only"
        if status == "PASS" and synthetic:
            synthetic_passes += 1
        if status == "PASS" and evidence_kind == "harness_only" and not synthetic:
            harness_only_passes += 1
        if is_firmware_proof:
            firmware_passes += 1
        if corpus_kind == "generated_fixture":
            generated_fixture_targets += 1
            if is_firmware_proof:
                generated_fixture_firmware_proof_passes += 1
        st_norm = str(status).upper().replace(" ", "_").replace("-", "_")
        bucket = "not_runnable" if st_norm in ("NOT_RUNNABLE", "NOTRUNNABLE") else st_norm.lower()
        if bucket not in by_corpus[corpus_kind]:
            bucket = "total"
        by_corpus[corpus_kind]["total"] += 1
        if bucket != "total":
            by_corpus[corpus_kind][bucket] = by_corpus[corpus_kind].get(bucket, 0) + 1
        by_evidence[evidence_kind] = by_evidence.get(evidence_kind, 0) + 1
        row = {
            "name": t.get("name"),
            "reader": t.get("reader"),
            "status": status,
            "synthetic": synthetic,
            "l3_claim": l3_claim,
            "firmware_proof": is_firmware_proof,
            "evidence_kind": evidence_kind,
            "corpus_kind": corpus_kind,
            "ran_on_our_generated_data": bool(ran_on_generated) if ran_on_generated is not None else (corpus_kind == "generated_fixture"),
            "reason": t.get("reason"),
            "claims": t.get("claims", []),
        }
        # preserve H43 extension keys and unknown keys
        for k in ("corpus", "corpus_type", "input_kind", "fixture", "artifact", "generated_fixture"):
            if k in t and k not in row:
                row[k] = t[k]
        for k, v in t.items():
            if k not in row:
                row[k] = v
        rows.append(row)
    out = {
        "kind": "l3_corpus" if corpus_aware else "l3_legacy",
        "layer": "L3",
        "provenance": "firmware/L3 harness (only explicitly marked non-synthetic l3_claim/firmware_proof PASS proves firmware reading)",
        "source": source,
        "schema": doc.get("schema"),
        "corpus_contract": (ps.CONTRACT["l3_corpus_input"] if ps else None),
        "corpus_aware": corpus_aware,
        "result": doc.get("result"),
        "counts": counts,
        "targets": rows,
        "firmware_proof_passes": firmware_passes,
        "synthetic_passes_not_firmware_proof": synthetic_passes,
        "harness_only_passes": harness_only_passes,
        "generated_fixture_targets": generated_fixture_targets,
        "generated_fixture_firmware_proof_passes": generated_fixture_firmware_proof_passes,
        "by_corpus_kind": by_corpus,
        "by_evidence_kind": by_evidence,
        "firmware_proven": bool(firmware_passes),
        "note": "Synthetic/harness results are never firmware proof. Generated-fixture corpus runs are reported as generated-fixture evidence and promoted to firmware proof only when explicitly marked (non-synthetic l3_claim/firmware_proof PASS). BLOCKED/SKIP/NOT_RUNNABLE claim nothing.",
    }
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
    lines.append(f"# H27/H47 progress dashboard (L1–L5)")
    lines.append("")
    lines.append(f"- schema: `{s['schema']}` · generated: `{s['generated_at']}`")
    lm = s.get("level_mapping") or {}
    if lm:
        lines.append(f"- **Level mapping (2026-11-09):** L3=fragments, L4=full-system emulator (M8), L5=bench/car (M6). Pre-2026-11-09 L4/L5 swapped.")
    lines.append(f"- **Rule 13 / ladder:** ten raport rozdziela warstwy i nigdy nie podnosi L2 do L3/L4/L5.")
    contract = s.get("schema_contract") or {}
    if contract:
        lines.append(f"- schema contract: backward_compatible={contract.get('backward_compatible')} auto_detect={contract.get('auto_detect')} unknown_keys={contract.get('unknown_keys','tolerated')}")
    lines.append("")
    if s.get("problems"):
        lines.append("## Parse/input problems")
        for p in s["problems"]:
            lines.append(f"- `{p['source']}`: {p['message']}")
        lines.append("")

    lines.append("## Udowodnione offline (L1/L2)")
    lines.append("")
    l1l2 = s.get("l1l2") or {}
    if l1l2.get("kind") == "l1l2_matrix":
        sm = l1l2.get("summary") or {}
        counts = l1l2.get("counts") or {}
        lines.append(f"- matrix verdict: **{'OK' if sm.get('ok') else sm.get('ok')}** (PASS={counts.get('PASS',0)} FAIL={counts.get('FAIL',0)} SKIP={counts.get('SKIP',0)} NOT_COVERED={counts.get('NOT_COVERED',0)} NOT_RUNNABLE={counts.get('NOT_RUNNABLE',0)} UNKNOWN={counts.get('UNKNOWN',0)})")
        lines.append(f"- source: `{l1l2.get('source','')}` · schema: `{l1l2.get('schema','')}` · firmware_acceptance_claim={l1l2.get('firmware_acceptance_claim')} · vendor_data_used={l1l2.get('vendor_data_used')}")
        if l1l2.get("by_file"):
            lines.append("- per-file counts (SKIP/NOT_COVERED/NOT_RUNNABLE separated from PASS):")
            for fname, fc in sorted(l1l2["by_file"].items()):
                parts = [f"{k}={v}" for k, v in fc.items() if v]
                lines.append(f"  - `{fname}`: {', '.join(parts)}")
        if l1l2.get("by_feature"):
            lines.append("- per-feature counts:")
            for feat, fc in sorted(l1l2["by_feature"].items()):
                parts = [f"{k}={v}" for k, v in fc.items() if v]
                lines.append(f"  - `{feat}`: {', '.join(parts)}")
    elif l1l2.get("summary"):
        sm = l1l2["summary"]
        lines.append(f"- verdict: **{'OK' if sm.get('ok') else sm.get('ok')}** (runnable {sm.get('runnable_pass')}P/{sm.get('runnable_fail')}F/{sm.get('runnable_skip')}S, not_covered={sm.get('counts',{}).get('NOT COVERED',0)})")
        lines.append(f"- source: `{l1l2.get('source','')}` · schema: `{l1l2.get('schema','')}` · firmware_acceptance_claim={l1l2.get('firmware_acceptance_claim')} · vendor_data_used={l1l2.get('vendor_data_used')}")
    else:
        lines.append("- no L1/L2 JSON provided/run in this report.")
    lines.append(f"- note: {l1l2.get('note','Offline only; never firmware/L3/L4/L5 acceptance.')}")

    lines.append("")
    lines.append("## Udowodnione przez firmware / L3 (tylko realne, nie syntetyczne)")
    lines.append("")
    l3 = s.get("l3") or {}
    if l3.get("targets"):
        lines.append(f"- harness result: `{l3.get('result')}` · firmware proof passes: **{l3.get('firmware_proof_passes',0)}** · synthetic passes (not firmware proof): {l3.get('synthetic_passes_not_firmware_proof',0)} · generated-fixture targets: {l3.get('generated_fixture_targets',0)} (firmware proof: {l3.get('generated_fixture_firmware_proof_passes',0)})")
        lines.append(f"- counts: {json.dumps(l3.get('counts',{}), ensure_ascii=False)}")
        if l3.get("corpus_aware"):
            lines.append(f"- corpus kinds: `{json.dumps(l3.get('by_corpus_kind',{}), ensure_ascii=False)}`")
            lines.append(f"- evidence kinds: `{json.dumps(l3.get('by_evidence_kind',{}), ensure_ascii=False)}`")
        lines.append("")
        headers = ["Target", "Reader", "Status", "Corpus", "Synthetic", "L3 claim", "Evidence", "Firmware proof"]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|---|---|---|---|---:|---:|---|---:|")
        for t in l3["targets"]:
            lines.append(f"| {t.get('name')} | {t.get('reader')} | **{t.get('status')}** | {t.get('corpus_kind','')} | {t.get('synthetic')} | {t.get('l3_claim')} | {t.get('evidence_kind','')} | {t.get('firmware_proof')} |")
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
        task_lookup = ", ".join(f"{k}={v.get('checked')}" for k, v in td.items())
        lines.append(f"- L5/M6 task lookup: {task_lookup}")
    lines.append(f"- H27 claim block (reserved): {', '.join(s.get('claims') or [])}")
    if s.get("h47_claims"):
        lines.append(f"- H47 claim block (reserved): {', '.join(s.get('h47_claims') or [])}")

    lines.append("")
    lines.append("## Mapowanie na regułę 13")
    lines.append("")
    lines.append("- **L1/L2 (offline)**: konieczne, nie wystarczające; ten raport pokazuje je tylko jako offline. H41 per-file/per-feature matrix (generated fixture) rozdziela PASS od SKIP/NOT_COVERED/NOT_RUNNABLE.")
    lines.append("- **L3 (fragmenty firmware)**: potwierdzenie dopiero gdy target ma zlokalizowany reader i wynik jest nie-syntetycznym `l3_claim`/`firmware_proof` PASS; raport liczy takie przypadki osobno. H43 generated-fixture corpus jest raportowany osobno i nigdy nie jest promowany do firmware proof bez jawnego oznaczenia.")
    lines.append("- **L4 (emulator pełnosystemowy, M8)**: integracja software przed autem; status jawny, nigdy auto-PASS.")
    lines.append("- **L5 (auto/stanowisko, M6)**: akceptacja końcowa; zawsze ręczna, nigdy podnoszona z L1–L4.")
    return "\n".join(lines) + "\n"


def build_report(args) -> dict:
    problems: list[Problem] = []
    t0 = time.time()

    # L1/L2 (legacy H26 and/or H41 matrix, auto-detected; explicit matrix flag wins)
    l1l2 = None
    l1l2_matrix_src = getattr(args, "l1l2_matrix_json", None) or getattr(args, "l1l2_json", None)
    if l1l2_matrix_src:
        doc, p = load_json_file(Path(l1l2_matrix_src)); problems += p
        if doc is not None:
            l1l2, p = normalize_l1l2(doc, str(l1l2_matrix_src)); problems += p
    elif getattr(args, "run_tools", False):
        rc, out = _run_cmd([PY, str(TOOLS / "l1l2_fixtures.py"), "--json",
                            "/tmp/opencode/h27-l1l2-auto.json", "--no-stdout-md"])
        doc, p = load_json_file(Path("/tmp/opencode/h27-l1l2-auto.json")); problems += p
        if doc is not None:
            l1l2, p = normalize_l1l2(doc, "l1l2_fixtures.py(auto)"); problems += p
        if rc not in (0, 1):  # 1 means runnable failures, still a report
            problems.append(Problem("l1l2_fixtures.py", f"unexpected exit {rc}"))

    # L3 (legacy l3check and/or H43 corpus-aware, auto-detected)
    l3 = None
    l3_src = getattr(args, "l3_corpus_json", None) or getattr(args, "l3_json", None)
    if l3_src:
        doc, p = load_json_file(Path(l3_src)); problems += p
        if doc is not None:
            l3, p = normalize_l3(doc, str(l3_src)); problems += p
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

    schema_contract = (ps.CONTRACT if ps else {
        "schema": SCHEMA, "schema_legacy_chain": [SCHEMA_V2, SCHEMA_LEGACY],
        "backward_compatible": True, "auto_detect": True,
        "note": "progress_schema module unavailable; minimal inline contract",
    })
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA,
        "schema_legacy_chain": [SCHEMA_V2, SCHEMA_LEGACY],
        "schema_legacy": SCHEMA_LEGACY,
        "schema_contract": schema_contract,
        "task": TASK,
        "tasks": [TASK, "H47"],
        "claims": CLAIMS,
        "h47_claims": H47_CLAIMS,
        "level_mapping": LEVEL_MAPPING,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_s": round(time.time() - t0, 3),
        "separation": {
            "offline_proven": "L1/L2 only (format/structure, synthetic/generated-fixture per-file/per-feature as scoped)",
            "firmware_l3_proven": "only explicitly marked non-synthetic l3_claim/firmware_proof PASS targets (firmware fragments)",
            "generated_fixture_l3_evidence": "generated-fixture corpus runs reported separately; never firmware proof unless explicitly marked",
            "emulator_l4": "full-system emulator (M8), explicit/manual status; never auto-passed",
            "car_required_l5": "bench/car (M6) explicit manual S0-S3; never auto-passed",
        },
        "problems": [asdict(p) for p in problems],
        "l1l2": l1l2,
        "l1l2_matrix": l1l2 if isinstance(l1l2, dict) and l1l2.get("kind") == "l1l2_matrix" else None,
        "l3": l3,
        "l3_corpus": l3 if isinstance(l3, dict) and l3.get("corpus_aware") else None,
        "reader_coverage": rc_doc,
        "l4_emulator": l4,
        "l5_car": l5,
        # backward-compat aliases (v1: l4 was car)
        "l4": l5,
        "todo_l5_tasks": {k: todo_tasks[k] for k in l5_ids if k in todo_tasks},
        "todo_l4_tasks": {k: todo_tasks[k] for k in l5_ids if k in todo_tasks},
        "claims_brief": claims,
    }


def _utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except Exception:
            pass


def selftest() -> int:
    _utf8_stdout()
    errors = 0
    import tempfile

    def ok(cond, msg):
        nonlocal errors
        print(f"  {'ok' if cond else 'FAIL'}: {msg}")
        if not cond:
            errors += 1

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
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "rc.md"
        p.write_text("| # | Wrong | columns |\n|---|---|---|\n|1|a|b|\n")
        rcb, probs = parse_reader_coverage(p)
        ok(probs, "header mismatch produces problems")
        ok(rcb.get("rows") == [] or rcb.get("row_count", 0) == 0 or probs, "broken contract not silently trusted as 30-row matrix")

    # H47 (1): legacy H26/H27 inputs still parse
    l1, p = normalize_l1l2({
        "firmware_acceptance_claim": False, "vendor_data_used": False,
        "summary": {"ok": True, "runnable_pass": 6, "runnable_fail": 0, "runnable_skip": 1,
                    "counts": {"NOT COVERED": 2}}, "checks": []}, "legacy-syn")
    ok(l1.get("kind") == "l1l2_legacy", "legacy H26 l1l2 detected")
    ok(l1["verdict"] is True and not p, "valid legacy l1l2 normalized")
    ok(l1["summary"]["runnable_pass"] == 6 and isinstance(l1["checks"], list), "legacy l1l2 fields preserved")
    l1b, p = normalize_l1l2({"firmware_acceptance_claim": True, "summary": {}, "checks": []}, "syn")
    ok(any("promote" in x.message for x in p), "firmware_acceptance_claim=true flagged")

    l3, p = normalize_l3({"schema": "osm2leaf.l3check/v1", "result": "PASS", "counts": {"pass": 1},
                          "targets": [
                              {"name": "probe", "reader": "synthetic", "status": "PASS", "synthetic": True, "l3_claim": False, "claims": []},
                              {"name": "real", "reader": "drstr", "status": "BLOCKED", "synthetic": False, "l3_claim": False, "claims": []},
                          ]}, "legacy-syn")
    ok(l3.get("kind") == "l3_legacy", "legacy l3check detected")
    ok(l3["firmware_proof_passes"] == 0, "synthetic PASS not counted as firmware proof")
    ok(l3["synthetic_passes_not_firmware_proof"] == 1, "synthetic pass counted separately")
    ok(l3["firmware_proven"] is False, "firmware_proven false when only synthetic")
    l3r, p = normalize_l3({"result": "PASS", "counts": {}, "targets": [
        {"name": "real", "reader": "drstr", "status": "PASS", "synthetic": False, "l3_claim": True, "claims": []}]}, "syn")
    ok(l3r["firmware_proof_passes"] == 1 and l3r["firmware_proven"] is True, "real l3_claim PASS is firmware proof")

    # H47 (2): synthetic H41-style per-file/per-feature JSON fixture
    h41_doc = {
        "schema": "osm2leaf.l1l2_matrix/v0-provisional",
        "vendor_data_used": False,
        "fixture": "generated-fixture:h40-synthetic",
        "rows": [
            {"level": "L1", "file": "DRSTR001.DAT", "feature": "structure", "status": "PASS", "command": "cardcheck", "reason": "ok"},
            {"level": "L2", "file": "REFER001/POINT.DAT", "feature": "POIs", "status": "PASS", "command": "roundtrip", "reason": "ok"},
            {"level": "L2", "file": "MAPAL001/B01R02.DAT", "feature": "roads", "status": "SKIP", "command": "harness", "reason": "vendor tile needed"},
            {"level": "L2", "file": "MAPAL001/B01R02.DAT", "feature": "geometry", "status": "NOT_COVERED", "command": "harness", "reason": "no generator"},
            {"level": "L2", "file": "REFER001/NAME.DAT", "feature": "names", "status": "NOT_RUNNABLE", "command": "decode", "reason": "missing writer"},
            {"level": "L2", "file": "REFER001/NAME.DAT", "feature": "names", "status": "FAIL", "command": "decode", "reason": "mismatch"},
            {"level": "L1", "file": "FUTURE.DAT", "feature": "structure", "status": "NOT_COVERED", "command": "cardcheck", "reason": "TBD", "tbd_key": "preserved"},
        ],
    }
    m41, p = normalize_l1l2(h41_doc, "h41-syn")
    ok(not p, f"H41 matrix parses without problems: {[x.message for x in p]}")
    ok(m41.get("kind") == "l1l2_matrix", "H41 matrix detected")
    ok(m41["counts"]["PASS"] == 2, "H41 PASS count")
    ok(m41["counts"]["SKIP"] == 1, "H41 SKIP separated")
    ok(m41["counts"]["NOT_COVERED"] == 2, "H41 NOT_COVERED separated")
    ok(m41["counts"]["NOT_RUNNABLE"] == 1, "H41 NOT_RUNNABLE separated")
    ok(m41["counts"]["FAIL"] == 1, "H41 FAIL counted")
    ok(m41["by_file"]["DRSTR001.DAT"]["PASS"] == 1, "H41 per-file counts")
    ok(m41["by_feature"]["POIs"]["PASS"] == 1 and m41["by_feature"]["roads"]["SKIP"] == 1, "H41 per-feature counts")
    ok(m41["by_feature"]["names"]["NOT_RUNNABLE"] == 1 and m41["by_feature"]["names"]["FAIL"] == 1, "H41 separates non-pass from fail per feature")
    ok(any(r.get("tbd_key") == "preserved" for r in m41["rows"]), "H41 unknown keys preserved/tolerated")
    ok(m41["summary"]["ok"] is False, "H41 FAIL makes matrix not ok")

    # H47 (3): synthetic H43-style generated-corpus L3 JSON
    h43_doc = {
        "schema": "osm2leaf.l3_corpus/v0-provisional",
        "result": "MIXED",
        "counts": {"pass": 1, "blocked": 2, "not_runnable": 1},
        "targets": [
            {"name": "tile_reader_gen", "reader": "tile", "status": "PASS", "synthetic": False, "l3_claim": False,
             "ran_on_our_generated_data": True, "corpus_kind": "generated_fixture", "evidence_kind": "harness_only",
             "reason": "ran on H40 generated tile, harness path only"},
            {"name": "tile_reader_gen_fp", "reader": "tile", "status": "PASS", "synthetic": False, "l3_claim": True,
             "ran_on_our_generated_data": True, "corpus_kind": "generated_fixture", "firmware_proof": True,
             "reason": "explicitly marked firmware proof on generated fixture"},
            {"name": "probe", "reader": "synthetic", "status": "PASS", "synthetic": True, "l3_claim": False,
             "corpus_kind": "synthetic", "reason": "probe"},
            {"name": "vendor_reader", "reader": "drstr", "status": "PASS", "synthetic": False, "l3_claim": True,
             "corpus_kind": "factory", "reason": "factory corpus"},
            {"name": "gen_blocked", "reader": "poi", "status": "BLOCKED", "synthetic": False, "l3_claim": False,
             "ran_on_our_generated_data": True, "corpus_kind": "generated_fixture", "reason": "reader not runnable"},
            {"name": "gen_nr", "reader": "name", "status": "NOT_RUNNABLE", "synthetic": False, "l3_claim": False,
             "ran_on_our_generated_data": True, "corpus_kind": "generated_fixture", "reason": "no target mapping"},
        ],
    }
    m43, p = normalize_l3(h43_doc, "h43-syn")
    ok(not p, f"H43 corpus parses without problems: {[x.message for x in p]}")
    ok(m43.get("corpus_aware") is True, "H43 corpus detected")
    ok(m43["generated_fixture_targets"] == 4, "H43 generated-fixture targets counted")
    ok(m43["generated_fixture_firmware_proof_passes"] == 1, "H43 explicit firmware proof counted")
    gen_harness = next(t for t in m43["targets"] if t["name"] == "tile_reader_gen")
    ok(gen_harness["corpus_kind"] == "generated_fixture", "generated fixture corpus kind")
    ok(gen_harness["firmware_proof"] is False, "generated-fixture harness PASS not promoted to firmware proof")
    ok(gen_harness["evidence_kind"] == "harness_only", "generated-fixture harness evidence kind")
    gen_fp = next(t for t in m43["targets"] if t["name"] == "tile_reader_gen_fp")
    ok(gen_fp["firmware_proof"] is True and gen_fp["evidence_kind"] == "firmware_proof", "explicitly marked generated-fixture firmware proof accepted")
    probe = next(t for t in m43["targets"] if t["name"] == "probe")
    ok(probe["firmware_proof"] is False and probe["corpus_kind"] == "synthetic", "synthetic probe never firmware proof")
    factory = next(t for t in m43["targets"] if t["name"] == "vendor_reader")
    ok(factory["firmware_proof"] is True and factory["corpus_kind"] == "factory", "factory non-synthetic l3_claim PASS is firmware proof")
    blocked = next(t for t in m43["targets"] if t["name"] == "gen_blocked")
    ok(blocked["status"] == "BLOCKED" and blocked["firmware_proof"] is False, "generated BLOCKED not a pass")
    ok(m43["by_corpus_kind"]["generated_fixture"]["total"] == 4, "corpus-kind breakdown")
    ok(m43["by_evidence_kind"]["firmware_proof"] == 2, "evidence-kind breakdown includes explicit+factory proofs")

    # H47 (4): L4 emulator and L5 bench manual states remain explicit/non-auto-pass
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
    l4c, p = build_l4(todo, None)
    ok(l4c["layer"] == "L5" and l4c["stages"] == l5["stages"], "build_l4 alias returns car-as-L5 (v1 compat)")
    todo_m8 = {"M8.A2": {"checked": False, "status_line": "blocked", "result": None},
               "M8.B5": {"checked": False, "status_line": "open", "result": None},
               "M8.E4": {"checked": False, "status_line": "open", "result": None},
               "M8.A1": {"checked": True, "status_line": "done", "result": "EXP"}}
    l4m, p = build_l4_emulator(todo_m8, None)
    ok(all(s["status"] == "NOT RUN" for s in l4m["stages"]), "L4/emulator defaults to NOT RUN")
    ok(l4m["layer"] == "L4", "emulator layer is L4")
    l4mp, p = build_l4_emulator(todo_m8, {"F0": {"status": "PASS"}})
    ok(l4mp["stages"][0]["status"] == "NOT RUN", "L4 emulator PASS without evidence demoted")
    l4me, p = build_l4_emulator(todo_m8, {"F0": {"status": "PASS", "evidence": "qemu log"}})
    ok(l4me["stages"][0]["status"] == "PASS" and not p, "L4 emulator PASS with evidence accepted")

    # full report on synthetic inputs (legacy path still works)
    class A:
        pass

    a = A()
    a.l1l2_json = a.l3_json = a.reader_coverage = a.todo = a.claims = None
    a.l1l2_matrix_json = a.l3_corpus_json = None
    a.l4_status = a.l5_status = a.l4_emulator_status = None
    a.run_tools = False
    a.reader_coverage = str(ROOT / "docs/research/reader-coverage.md")
    a.todo = str(ROOT / "TODO.md")
    a.claims = str(ROOT / "docs/research/claims.md")
    report = build_report(a)
    ok(report["schema"] == SCHEMA, "schema v3 set")
    ok(report.get("schema_version") == SCHEMA, "schema_version present")
    ok(report.get("schema_legacy") == SCHEMA_LEGACY, "legacy schema noted")
    ok(isinstance(report.get("schema_contract"), dict), "schema_contract documents field names/versions")
    ok(report["schema_contract"].get("l1l2_matrix_input"), "schema_contract documents H41 matrix input")
    ok(report["schema_contract"].get("l3_corpus_input"), "schema_contract documents H43 corpus input")
    ok(report["level_mapping"]["L4"] == "full-system emulator (QEMU ze0, M8)", "mapping L4=emulator")
    ok(report["level_mapping"]["L5"] == "bench/car (M6)", "mapping L5=car")
    ok(report["separation"]["emulator_l4"], "separation states emulator L4")
    ok(report["separation"]["car_required_l5"], "separation states car L5")
    ok(report["separation"]["generated_fixture_l3_evidence"], "separation states generated-fixture L3 evidence")
    ok(report["l4_emulator"]["layer"] == "L4" and report["l5_car"]["layer"] == "L5", "layer fields correct")
    ok(report["l4"] == report["l5_car"], "v1 compat alias l4->car")
    md = render_markdown(report)
    for must in ["Udowodnione offline", "Udowodnione przez firmware", "Emulator pełnosystemowy (L4, M8", "Wymaga auta/stanowiska (L5, M6", "nigdy nie podnosi L2 do L3/L4/L5", "regułę 13", "Level mapping"]:
        ok(must in md, f"markdown contains {ascii(must)}")
    ok("S0" in md and "S1" in md and "F0" in md, "markdown has L5 car stages and L4 emulator stages")
    ok(json.dumps(report), "report is JSON-serializable")

    # full report with H41/H43 synthetic inputs
    with tempfile.TemporaryDirectory() as td:
        h41p = Path(td) / "h41.json"
        h43p = Path(td) / "h43.json"
        h41p.write_text(json.dumps(h41_doc), encoding="utf-8")
        h43p.write_text(json.dumps(h43_doc), encoding="utf-8")
        b = A()
        b.l1l2_json = str(h41p)
        b.l1l2_matrix_json = b.l3_corpus_json = None
        b.l3_json = str(h43p)
        b.reader_coverage = str(ROOT / "docs/research/reader-coverage.md")
        b.todo = str(ROOT / "TODO.md")
        b.claims = str(ROOT / "docs/research/claims.md")
        b.l4_status = b.l5_status = b.l4_emulator_status = None
        b.run_tools = False
        rep = build_report(b)
        ok(rep["l1l2"]["kind"] == "l1l2_matrix", "report carries H41 matrix")
        ok(rep["l1l2"]["counts"]["NOT_COVERED"] == 2, "report preserves NOT_COVERED separation")
        ok(rep["l3"]["corpus_aware"] is True, "report carries H43 corpus-aware L3")
        ok(rep["l3"]["generated_fixture_firmware_proof_passes"] == 1, "report keeps explicit generated-fixture firmware proof")
        ok(rep["l3"]["firmware_proof_passes"] == 2, "total firmware proof includes factory+explicit generated")
        md2 = render_markdown(rep)
        ok("per-file counts" in md2 and "per-feature counts" in md2, "markdown shows H41 matrix breakdown")
        ok("generated-fixture" in md2 and "corpus kinds" in md2, "markdown shows H43 corpus classification")
        ok("NOT_COVERED" in md2 and "NOT_RUNNABLE" in md2, "markdown shows separated statuses")

    if errors:
        print(f"progress_report selftest: {errors} FAIL")
        return 1
    print("progress_report selftest: OK")
    return 0


def main(argv=None):
    _utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", metavar="PATH", help="write JSON report (includes schema_contract with schema version/field names)")
    ap.add_argument("--md", metavar="PATH", help="write Markdown report")
    ap.add_argument("--l1l2-json", help="H26/l1l2_fixtures JSON or H41 matrix JSON (auto-detected)")
    ap.add_argument("--l1l2-matrix-json", help="explicit H41 per-file/per-feature matrix JSON (alias of --l1l2-json)")
    ap.add_argument("--l3-json", help="l3check --json or H43 corpus-aware JSON (auto-detected)")
    ap.add_argument("--l3-corpus-json", help="explicit H43 generated-corpus L3 JSON (alias of --l3-json)")
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
        try:
            return selftest()
        except Exception:
            import traceback
            traceback.print_exc()
            return 1
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
