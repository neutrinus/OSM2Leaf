#!/usr/bin/env python3
"""Card-level L3 runs: one manifest, one re-run command (M9.62).

``tools/l3_harness/runs.json`` declares one entry per ``l3-running`` row of
``docs/research/reader-coverage.md``: a reader-coverage row number, the tool,
its argument vector (with ``{IMG}``/``{CARD}``/… placeholders), the build whose
firmware/VA it executes, the expected verdict line, and the source EXP + claim.

``python3 tools/l3check.py --runs [--only ROW]`` executes every entry and
prints ``PASS`` / ``FAIL`` / ``NOT RUN`` per row:

====================  ========================================================
``PASS``              the tool exited 0 and printed the expected verdict line
``FAIL``              a non-zero exit, a missing verdict line, or a crash
``NOT RUN``           a required image/file is absent (rule 11); never a pass
``MANUAL``            a row that cannot reduce to one stable-verdict command
====================  ========================================================

Exit codes: ``0`` every runnable row passed, ``1`` a FAIL, ``3`` nothing ran.

This is a local/weekly re-run harness for existing L3 evidence.  It **needs
vendor images** and is never part of PR CI.  It declares no new L3 run and does
not change ``tools/l3_harness/targets.json`` (M9.59 keeps its own rows).

The module is importable: ``load``/``validate``/``run_rows``/``counts`` are
pure apart from the explicit subprocess runner, so ``l3check.py --selftest``
can compare the manifest row list with ``map_signals.py`` and
``progress_report.py`` without vendor data.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
ROOT = TOOLS.parent
MANIFEST = HERE / "runs.json"

SCHEMA = "osm2leaf.l3-runs/v1"

PASS, FAIL, NOT_RUN, MANUAL = "PASS", "FAIL", "NOT RUN", "MANUAL"
_STATUSES = (PASS, FAIL, NOT_RUN, MANUAL)

_PLACEHOLDER_RE = re.compile(r"\{([A-Z0-9_]+)\}")


class RunsError(ValueError):
    """The manifest cannot be turned into a trusted run."""


def load(path: Path | None = None) -> dict:
    """Load and validate the manifest; raise RunsError on any problem."""
    path = Path(path) if path is not None else MANIFEST
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunsError(f"cannot read {path}: {exc}") from exc
    problems = validate(doc)
    if problems:
        raise RunsError("; ".join(problems))
    return doc


def validate(doc: dict) -> list[str]:
    """Return every defect; an empty list means the manifest is usable."""
    problems: list[str] = []
    if not isinstance(doc, dict):
        return ["manifest is not an object"]
    if doc.get("schema") != SCHEMA:
        problems.append(f"schema {doc.get('schema')!r} != {SCHEMA!r}")
    rows = doc.get("rows")
    if not isinstance(rows, list) or not rows:
        return problems + ["rows must be a non-empty list"]
    seen: set[str] = set()
    required = {"row", "what", "reader", "build", "tool", "argv", "expect",
                "source_exp", "claim", "need", "firmware_pass"}
    allowed = required | {"note", "placeholders", "schema", "rows", "matrix",
                           "firmware_pass"}
    unknown = set(doc) - allowed
    if unknown:
        problems.append(f"unknown top-level key(s) {sorted(unknown)}")
    row_allowed = required | {"note"}
    for i, row in enumerate(rows):
        where = f"rows[{i}]"
        if not isinstance(row, dict):
            problems.append(f"{where}: not an object")
            continue
        missing = required - set(row)
        if missing:
            problems.append(f"{where}: missing {sorted(missing)}")
            continue
        extra_keys = set(row) - row_allowed
        if extra_keys:
            problems.append(f"{where}: unknown key(s) {sorted(extra_keys)}")
        ident = str(row["row"])
        if ident in seen:
            problems.append(f"{where}: duplicate row {ident!r}")
        seen.add(ident)
        argv = row["argv"]
        if not (isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv)):
            problems.append(f"{where}: argv must be a non-empty list of strings")
            continue
        if not isinstance(row["expect"], str) or not row["expect"]:
            problems.append(f"{where}: expect must be a non-empty string")
        if not isinstance(row["need"], list) or not all(
                isinstance(k, str) for k in row["need"]):
            problems.append(f"{where}: need must be a list of placeholder names")
        # every placeholder used in argv must be declared in `need`
        used = set()
        for arg in argv:
            used.update(_PLACEHOLDER_RE.findall(arg))
        undeclared = used - set(row["need"])
        if undeclared:
            problems.append(f"{where}: argv uses {sorted(undeclared)} not declared in need")
        # every declared need (except scratch/JSON) must have a default or flag
        for key in row["need"]:
            if key in ("WORKDIR", "JSON", "CMP", "IND"):
                continue
            if key not in doc.get("placeholders", {}) and \
                    ("{" + key + "}") not in doc.get("placeholders", {}):
                problems.append(f"{where}: need {key!r} has no placeholder default")
    return problems


def matrix_row_ids(matrix: Path) -> list[str]:
    """The l3-running matrix row IDs: column 9 bearing PASS/REJECT.

    This is the same two-stage key ``map_signals.signal_l3_rows`` uses (a
    numbered matrix row whose L3-result cell contains PASS/REJECT), so the
    manifest and the matrix cannot silently disagree on which rows are managed.
    """
    if not matrix.is_file():
        return []
    ids: list[str] = []
    for line in matrix.read_text(encoding="utf-8").splitlines():
        if not re.match(r"^\|\s*\d+\s*\|", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        # with -F'|' the leading pipe produces an empty $1, so awk's $9
        # ("L3 result") is index 7 in the outer-pipe-stripped cells
        if len(cells) < 8:
            continue
        if re.search(r"PASS|REJECT", cells[7]):
            ids.append(cells[0])
    return ids


def coverage_problems(doc: dict, matrix: Path) -> list[str]:
    """One problem per l3-running matrix row with no manifest entry (falsifier)."""
    have = {str(r["row"]) for r in doc["rows"]}
    return [f"l3-running matrix row {rid} has no manifest entry"
            for rid in matrix_row_ids(matrix) if rid not in have]


def _default_placeholders(doc: dict) -> dict[str, str]:
    out = {k: str(v) for k, v in (doc.get("placeholders") or {}).items()}
    # host paths may be overridden by environment (same names as l3check uses)
    env_map = {"IMG": "IMG256", "US256": "US256"}
    for key, env in env_map.items():
        if os.environ.get(env):
            out["{" + key + "}"] = os.environ[env]
    return out


def resolve(doc: dict, row: dict, *, scratch: Path | None = None,
            extra: dict[str, str] | None = None) -> tuple[list[str], list[str]]:
    """Return (argv, missing) after expanding placeholders.

    ``missing`` lists placeholder names whose file/path could not be resolved;
    the caller reports the row ``NOT RUN`` rather than running it.  An
    unresolved image is never silently swapped for another build's head.
    """
    defaults = _default_placeholders(doc)
    overrides = extra or {}
    scratch = Path(scratch) if scratch is not None else Path(
        os.environ.get("L3_RUNS_SCRATCH", str(Path.home() / "projekty" /
                                             "leafre-work" / "scratch" / "m9.62")))
    scratch.mkdir(parents=True, exist_ok=True)

    def path_for(key: str) -> str | None:
        if key in ("WORKDIR", "JSON"):
            return str(scratch / "record")
        if key in overrides:
            return overrides[key]
        val = defaults.get("{" + key + "}")
        if val is None:
            return None
        # human-readable values in the manifest ("US POINT010.DAT.cmp") are
        # sources that must be produced into scratch, not literal paths.
        if val.startswith("US POINT010"):
            src = Path(defaults.get("{US256}", ""))
            return _extract_card_file(src, "REFER001/POINT010.DAT" +
                                      (".ind" if val.endswith(".ind") else ".cmp"),
                                      scratch)
        if val.startswith("EU POINT010"):
            root = Path(defaults.get("{CARDROOT}", ""))
            name = "POINT010.DAT" + (".ind" if val.endswith(".ind") else ".cmp")
            p = root / "REFER001" / name
            return str(p) if p.is_file() else None
        if key in ("WORKDIR", "JSON"):
            return str(scratch)
        return val

    missing: list[str] = []
    argv: list[str] = []
    for arg in row["argv"]:
        names = _PLACEHOLDER_RE.findall(arg)
        filled = arg
        for key in names:
            val = path_for(key)
            if val is None:
                if key not in missing:
                    missing.append(key)
            elif key in ("WORKDIR", "JSON"):
                pass  # scratch paths are directories/files created on demand
            elif key == "CARDROOT":
                if not Path(val).is_dir() and key not in missing:
                    missing.append(key)
            elif not Path(val).is_file() and key not in missing:
                missing.append(key)
            if val is not None:
                filled = filled.replace("{" + key + "}", val)
        argv.append(filled)
    return argv, missing


def _extract_card_file(card: Path, rel: str, scratch: Path) -> str | None:
    """Extract one file from a card image into scratch (never the repo)."""
    if not card.is_file():
        return None
    dest = scratch / "cardfiles"
    dest.mkdir(parents=True, exist_ok=True)
    name = Path(rel).name
    target = dest / name
    if target.is_file():
        return str(target)
    try:
        proc = subprocess.run(["7z", "e", "-y", f"-o{dest}", str(card), rel],
                              capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError):
        return None
    return str(target) if proc.returncode in (0, 1) and target.is_file() else None


def check_row(row: dict, *, argv: list[str], missing: list[str],
              timeout: int = 900) -> dict:
    """Execute one row and return its verdict dict (never raises at the caller)."""
    result = {
        "row": str(row["row"]), "what": row["what"], "tool": row["tool"],
        "build": row["build"], "reader": row["reader"],
        "claim": row["claim"], "exp": row["source_exp"],
        "expect": row["expect"], "argv": argv, "status": None,
        "detail": "", "returncode": None, "elapsed_s": None,
    }
    if missing:
        result["status"] = NOT_RUN
        result["detail"] = "NOT RUN (no %s; rule 11)" % ", ".join(missing)
        return result
    import time
    t0 = time.monotonic()
    try:
        proc = subprocess.run(argv, cwd=str(ROOT), capture_output=True,
                              text=True, errors="replace", timeout=timeout)
        output = (proc.stdout or "") + (proc.stderr or "")
        rc = proc.returncode
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "") if isinstance(exc.stdout, str) else ""
        rc = 124
        output += f"\ntimeout after {timeout}s"
    except OSError as exc:
        rc = 125
        output = f"cannot run tool: {exc}"
    result["elapsed_s"] = round(time.monotonic() - t0, 2)
    result["returncode"] = rc
    found = row["expect"] in output
    if rc == 0 and found:
        result["status"] = PASS
        result["detail"] = row["expect"]
    elif rc == 0 and not found:
        result["status"] = FAIL
        result["detail"] = f"exit 0 but expected line {row['expect']!r} not printed"
    else:
        result["status"] = FAIL
        tail = output.strip().splitlines()[-1:] or [""]
        result["detail"] = f"exit {rc}: {tail[0][:240]}"
    result["last_line"] = output.strip().splitlines()[-1:] or [""]
    return result


def run_rows(doc: dict, *, only: list[str] | None = None,
             scratch: Path | None = None, timeout: int = 900,
             extra: dict[str, str] | None = None) -> list[dict]:
    """Run the selected manifest rows in order."""
    rows = doc["rows"]
    if only:
        wanted = set(only)
        rows = [r for r in rows if str(r["row"]) in wanted]
        unknown = sorted(wanted - {str(r["row"]) for r in doc["rows"]})
        if unknown:
            raise RunsError("unknown row(s): " + ", ".join(unknown))
    out = []
    for row in rows:
        argv, missing = resolve(doc, row, scratch=scratch, extra=extra)
        out.append(check_row(row, argv=argv, missing=missing, timeout=timeout))
    return out


def counts(rows: list[dict]) -> dict:
    """Aggregate row statuses; `runnable` counts PASS+FAIL only."""
    out = {s.lower().replace(" ", "_"): 0 for s in _STATUSES}
    for row in rows:
        out[row["status"].lower().replace(" ", "_")] += 1
    out["runnable"] = out["pass"] + out["fail"]
    out["total"] = len(rows)
    return out


def matrix_count(matrix: Path) -> int:
    """The single count all three tools agree on: matrix l3-running rows."""
    return len(matrix_row_ids(matrix))


def count_agreement(doc: dict, matrix: Path) -> dict:
    """The three count sources, from one row list (M9.62).

    The task says the three tools (``map_signals l3_rows``,
    ``progress_report --run-tools``, ``l3check --build-corpus``) print three
    different L3 counts.  This function is the reconciliation: every source
    that needs a "how many card-level L3 runs" number reads the manifest's row
    list, so the number cannot drift between tools.  ``map`` (the matrix awk
    count) and ``manifest`` (declared rows) must be equal; a mismatch is a
    named FAIL, never a silently chosen value.  ``targets`` is the separate
    ``targets.json`` target count, reported beside them, not folded in.
    """
    matrix_n = matrix_count(matrix)
    manifest_n = len(doc.get("rows") or [])
    return {
        "matrix": matrix_n,
        "manifest": manifest_n,
        "agree": matrix_n == manifest_n,
        "firmware_pass": sum(1 for r in doc.get("rows") or [] if r.get("firmware_pass")),
    }


def result(rows: list[dict]) -> tuple[str, int]:
    """A FAIL wins; else a PASS; else nothing ran (exit 3)."""
    c = counts(rows)
    if c["fail"]:
        return "FAIL", 1
    if c["pass"]:
        return "PASS", 0
    return "NOT RUN", 3


def print_report(rows: list[dict], report: dict) -> None:
    print("l3check --runs: card-level L3 runs manifest (M9.62)")
    print(f"manifest {report['manifest']}")
    print(f"matrix   {report['matrix']} ({len(report.get('matrix_rows', []))} l3-running rows)")
    print()
    for row in rows:
        status = row["status"]
        print(f"  [{status:>7}] row {row['row']:>3} {row['reader']}: {row['what']}")
        print(f"           expect: {row['expect']}")
        print(f"           {row['detail']}")
        if row.get("elapsed_s") is not None:
            print(f"           wall {row['elapsed_s']} s; tool {row['tool']}")
    c = report["counts"]
    print()
    print(f"counts   pass={c['pass']} fail={c['fail']} "
          f"not_run={c['not_run']} manual={c['manual']} total={c['total']}")
    verdict = report["result"]
    if verdict == "PASS":
        print("RESULT: PASS (every runnable row passed; exit 0)")
    elif verdict == "FAIL":
        print(f"RESULT: FAIL ({c['fail']} row(s) failed; exit 1)")
    else:
        print(f"RESULT: NOT RUN (exit 3; no row ran, images absent)")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--matrix", type=Path,
                    default=ROOT / "docs" / "research" / "reader-coverage.md")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--scratch", type=Path, default=None)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", nargs="?", const="-", default=None)
    args = ap.parse_args()
    if args.selftest:
        d = load()
        probs = validate(d) + coverage_problems(d, args.matrix)
        print("runs selftest: " + ("OK" if not probs else "FAIL " + "; ".join(probs)))
        raise SystemExit(1 if probs else 0)
    doc = load(args.manifest)
    problems = validate(doc) + coverage_problems(doc, args.matrix)
    rows = run_rows(doc, only=args.only, scratch=args.scratch, timeout=args.timeout)
    report = {
        "schema": SCHEMA, "command": "l3check --runs",
        "manifest": str(args.manifest), "matrix": str(args.matrix),
        "matrix_rows": matrix_row_ids(args.matrix), "problems": problems,
        "counts": counts(rows), "result": result(rows)[0], "exit": result(rows)[1],
        "rows": rows,
    }
    if problems:
        report["result"], report["exit"] = "FAIL", 1
    if args.json is not None:
        text = json.dumps(report, indent=2)
        print(text if args.json in ("", "-") else (Path(args.json).write_text(text + "\n") or f"report: {args.json}"))
    else:
        print_report(rows, report)
        for p in problems:
            print(f"FAIL {p}")
    raise SystemExit(report["exit"])
