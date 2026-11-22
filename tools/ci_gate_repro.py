#!/usr/bin/env python3
"""Reproduce the CI standing-gate step and prove the claims count rule blocks.

`.github/workflows/ci.yml` runs one blocking step::

    python tools/gate.py --json gate.json 2>&1 | tee gate.txt
    rc=${PIPESTATUS[0]}          # gate.py's exit, not tee's
    ...
    exit $rc

``gate.py``'s ``claims_check`` gate is ``claims_check.py --strict
--count-check`` (H85).  This tool documents and re-runs that contract offline:

* **default** -- run the three cases and print one table (clean / synthetic
  count mismatch / SKIP-only).  The synthetic case writes a temp ledger with
  one claim's ``N checks`` bumped by one and runs the same
  ``claims_check --strict --count-check`` command ``gate.py`` runs; on a full
  clone that exits 1 (the negative control), so no red PR is needed.  On a
  **shallow** clone the count rule prints ``count check: skipped`` and cannot
  fire -- ``--selftest`` uses the in-process ``count_problems`` instead, which
  measures the working-tree pin and works on any clone.
* **--selftest** -- a fast structural + logic check (no full gate run, so it
  fits ``selftest.py``'s 60 s budget): the CI step shape is present, the
  README names ``tools/gate.py`` and the SKIP policy, and
  ``claims_check.count_problems`` flags a synthetic ``N checks`` mismatch
  (claimed ``N+1``, got ``N``) while the unmutated ledger flags none.

Usage::

    python3 tools/ci_gate_repro.py            # run the three cases
    python3 tools/ci_gate_repro.py --selftest # fast assertions for CI

Exit codes: ``0`` every expectation held, ``1`` an expectation failed,
``2`` usage or a missing tool.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

GATE = REPO_ROOT / "tools" / "gate.py"
CLAIMS = REPO_ROOT / "docs" / "research" / "claims.md"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CI_README = REPO_ROOT / ".github" / "workflows" / "README.md"

#: The ledger row the synthetic mismatch edits (its count pins the working
#: tree, so no measurement revision is needed and it runs on a shallow clone).
MUTATION_TARGET = "C-2953"
PIN_RE = re.compile(r"(Selftest )(\d+)( checks)")

#: The CI step's shape: a ``gate.py | tee`` pipeline read through PIPESTATUS.
CI_STEP_RE = re.compile(
    r"python tools/gate\.py[^\n]*\|\s*tee[^\n]*\n[^\n]*PIPESTATUS\[0\]")


def _gate_step(json_path: Path, txt_path: Path) -> int:
    """Run the CI step's ``gate.py --json | tee`` command; return its exit."""
    proc = subprocess.run(
        [sys.executable, str(GATE), "--json", str(json_path)],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=600,
    )
    txt_path.write_text(proc.stdout + proc.stderr, encoding="utf-8")
    return proc.returncode


def _mutate_claims(tmp: Path) -> Path:
    """Copy the ledger with ``MUTATION_TARGET``'s pin bumped by one."""
    text = CLAIMS.read_text(encoding="utf-8")
    out = []
    bumped = False
    for line in text.splitlines(keepends=True):
        if f"| {MUTATION_TARGET} |" in line and not bumped:
            m = PIN_RE.search(line)
            if m:
                line = line[: m.start(2)] + str(int(m.group(2)) + 1) + line[m.end(2):]
                bumped = True
        out.append(line)
    if not bumped:
        raise SystemExit(f"could not find a pin to bump on {MUTATION_TARGET}")
    dst = tmp / "claims.md"
    dst.write_text("".join(out), encoding="utf-8")
    return dst


def _claims_gate(claims_path: Path, out: Path) -> int:
    """Run the command gate.py's claims gate runs, on ``claims_path``."""
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "claims_check.py"),
         "--strict", "--count-check", "--claims", str(claims_path)],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=600,
    )
    out.write_text(proc.stdout + proc.stderr, encoding="utf-8")
    return proc.returncode


def _shallow() -> bool:
    try:
        p = subprocess.run(["git", "rev-parse", "--is-shallow-repository"],
                           cwd=str(REPO_ROOT), capture_output=True, text=True,
                           timeout=30)
        return p.stdout.strip().lower() == "true"
    except (OSError, subprocess.SubprocessError):
        return True


def _note(path: Path, rc: int) -> str:
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            low = line.lower()
            if "count mismatch" in low or "count check: skipped" in low \
                    or line.startswith("gate:"):
                return f"rc={rc} {line.strip()}"
    return f"rc={rc}"


def run() -> list[tuple[str, int, int, str]]:
    """Run the three cases; return (name, exit, expected, note)."""
    shallow = _shallow()
    results = []
    # (1) clean: the real ledger through gate.py (CI shape).
    with tempfile.TemporaryDirectory(prefix="ci-gate-clean-") as td:
        t = Path(td)
        rc = _gate_step(t / "gate.json", t / "gate.txt")
        results.append(("clean", rc, 0, _note(t / "gate.txt", rc)))
    # (2) synthetic count mismatch: mutate a temp ledger, run the claims gate.
    #     On a shallow clone the count rule is skipped, so the expectation
    #     relaxes to 0 and the note says so; the --selftest path below still
    #     proves the rule fires via count_problems.
    with tempfile.TemporaryDirectory(prefix="ci-gate-mut-") as td:
        t = Path(td)
        mutated = _mutate_claims(t)
        rc = _claims_gate(mutated, t / "claims.txt")
        want = 0 if shallow else 1
        note = _note(t / "claims.txt", rc)
        if shallow:
            note += " [shallow: count rule skipped]"
        results.append(("synthetic count mismatch", rc, want, note))
    # (3) SKIP-only: gate.py's own selftest proves PASS+SKIP -> exit 0.
    proc = subprocess.run(
        [sys.executable, str(GATE), "--selftest"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=600,
    )
    results.append(("SKIP-only (gate --selftest)", proc.returncode, 0,
                    "PASS+SKIP policy" if proc.returncode == 0
                    else "gate selftest FAILED"))
    return results


def _selftest() -> int:
    """Fast structural + logic assertions (no full gate run)."""
    import claims_check as cc

    failures = []
    # 1. The CI step shape exists in ci.yml.
    ci = CI_YML.read_text(encoding="utf-8")
    if not CI_STEP_RE.search(ci):
        failures.append("ci.yml: gate.py | tee ... PIPESTATUS[0] shape missing")
    # 2. The README names tools/gate.py and the SKIP policy.
    readme = CI_README.read_text(encoding="utf-8")
    if "tools/gate.py" not in readme:
        failures.append("README: does not name tools/gate.py")
    if "SKIP is never PASS" not in readme:
        failures.append("README: SKIP-never-PASS policy missing")
    # 3. count_problems flags a synthetic mismatch on the working-tree pin.
    text = CLAIMS.read_text(encoding="utf-8")
    rows = cc.parse_claim_rows(text)
    # One measurement cache for both passes: the mutation changes only the
    # claimed count, never what a selftest prints, so re-running every pinned
    # selftest a second time only doubles the time (it hit the 60 s budget).
    measured = {}

    def runner(tool, rev=None):
        if (tool, rev) not in measured:
            measured[(tool, rev)] = cc._run_selftest(tool, rev)
        return measured[(tool, rev)]
    baseline = {p["id"] for p in cc.count_problems(rows, runner)}
    if MUTATION_TARGET in baseline:
        failures.append(f"{MUTATION_TARGET} already mismatches on the clean ledger")
    # Mutate the pin in memory and re-measure.
    mut_lines = []
    for line in text.splitlines(keepends=True):
        if f"| {MUTATION_TARGET} |" in line:
            m = PIN_RE.search(line)
            line = line[: m.start(2)] + str(int(m.group(2)) + 1) + line[m.end(2):]
        mut_lines.append(line)
    mut_rows = cc.parse_claim_rows("".join(mut_lines))
    mut_problems = {p["id"]: p for p in cc.count_problems(mut_rows, runner)}
    if MUTATION_TARGET not in mut_problems:
        failures.append(f"count_problems did not flag the bumped {MUTATION_TARGET}")
    else:
        p = mut_problems[MUTATION_TARGET]
        if p["got"] != p["claimed"] - 1:
            failures.append(
                f"{MUTATION_TARGET}: got {p['got']} != claimed-1 {p['claimed']-1}")

    if failures:
        print("ci_gate_repro selftest: FAILED")
        for f in failures:
            print(" -", f)
        return 1
    print("ci_gate_repro selftest: OK "
          "(ci.yml step shape, README gate contract, count_problems "
          "flags a bumped pin and not the clean one)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--selftest", action="store_true",
                   help="fast structural + logic assertions for CI")
    p.add_argument("--json", action="store_true", help="emit a JSON document")
    args = p.parse_args(argv)

    if args.selftest:
        return _selftest()

    results = run()
    ok = all(rc == want for _, rc, want, _ in results)
    if args.json:
        print(json.dumps({
            "cases": [{"case": n, "exit": rc, "expected_exit": want,
                       "note": note, "ok": rc == want}
                      for n, rc, want, note in results],
            "shallow": _shallow(),
            "ok": ok,
        }, indent=2))
    else:
        print(f"{'case':30} {'exit':>4}  {'want':>4}  note")
        for name, rc, want, note in results:
            mark = "ok" if rc == want else "MISMATCH"
            print(f"{name:30} {rc:>4}  {want:>4}  {mark}  {note}")
        print("ci gate repro:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
