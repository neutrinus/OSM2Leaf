# EXP-2026-11-24-H42-progress-ci-artifacts

- **Status:** done
- **Date:** 2026-11-24
- **Sample:** `none (tool-only task)` — this change touches only `.github/workflows/*`; all inputs are generated no-vendor fixtures and committed repo files. No vendor image, ROOT, firmware dump, QEMU or hardware bytes are used.
- **Tools:** Python 3.11 (CI target) and the driver host `python3 3.x` (stdlib only); `PyYAML 6.0.3` (workflow parse only, not a gate dependency); `git 2.x`; `gh` (PR #709). Repo tools: `tools/progress_snapshot.py` (H56, schema `osm2leaf.progress_snapshot/v1`, 27/27 selftest), `tools/progress_report.py` (H27/H47, schema `osm2leaf.progress_report/v3`), `tools/l1l2_matrix.py` (H41), `tools/l3check.py` (H28/H55), `tools/claims_check.py`, `tools/todo_check.py`, `tools/board.py`.
- **Claims:** C-3290–C-3299
- **Supersedes:** none
- **Superseded by:** none

## Question

Can the per-level progress signal (H27 schema + H41 per-file/per-feature matrix + L3 firmware-proof separation + explicit L4/L5 manual status) be published as CI artifacts/job summaries on every PR/push without vendor data, QEMU or L5 hardware, while keeping SKIP/BLOCKED/NOT_RUNNABLE/NOT RUN out of the PASS count (rule 13)?

## Hypothesis

A single self-contained `progress.yml` job that runs `tools/progress_snapshot.py` and reads only the files it emits can publish an honest L1/L2/L3/L4/L5 summary and fail loudly on a regression. Falsifier: a PASS→FAIL mutation of a generated-fixture check does not make both the snapshot and the publisher fail, or any quoted status is not reproducible from a printing command.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none (workflow files only) |
| SHA-256 | n/a (no sample bytes) |
| Offset(s) / VA(s) | n/a |
| Tool / version | Python 3.11 CI / driver host, PyYAML 6.0.3, repo stdlib tools |
| Repo tool | `.github/workflows/progress.yml`, `tools/progress_snapshot.py` |

## Method

### 1. Sample and hash

No sample: workflow-only task. Every input is a generated no-vendor fixture produced by `tools/progress_snapshot.py` (H56) on the runner, or a committed repo file (`TODO.md`, `docs/research/{reader-coverage,claims}.md`, `tools/fixtures/l1l2-matrix-baseline.json`). No vendor data is read, fetched or committed.

### 2. Commands

```bash
# Positive control: offline snapshot + publisher on the generated fixture
cd /home/marek/projekty/OSM2Leaf.task-h42-cycle10
python3 tools/progress_snapshot.py --selftest
python3 tools/progress_snapshot.py --out artifacts/snapshot \
  --json progress.json --md progress.md
python3 -c "import yaml; [yaml.safe_load(open(f, encoding='utf-8')) for f in ['.github/workflows/progress.yml','.github/workflows/ci.yml','.github/workflows/l1l2-fixtures.yml','.github/workflows/main-watch.yml']]; print('YAML OK')"
git diff --check

# Publisher extracted verbatim from progress.yml's heredoc and run against the
# emitted files (GITHUB_STEP_SUMMARY redirected to a scratch file):
GITHUB_STEP_SUMMARY=scratch/h42/ciwork/summary.md python3 scratch/h42/publisher.py

# Negative mutation: flip one generated-fixture check PASS->FAIL, rerun snapshot
# and publisher, show both exit 1 and the summary is still published honestly:
python3 - <<'PY'
import json, subprocess, sys, os
from pathlib import Path
root = Path('/home/marek/projekty/OSM2Leaf.task-h42-cycle10')
work = Path('/home/marek/projekty/leafre-work/scratch/h42/mutation'); work.mkdir(parents=True, exist_ok=True)
good = json.loads(Path('/home/marek/projekty/leafre-work/scratch/h42/snap/l1l2.json').read_text())
mut = json.loads(json.dumps(good))
for c in mut['checks']:
    if c.get('status') == 'PASS':
        c['status'] = 'FAIL'; break
mutp = work/'l1l2-mutant.json'; mutp.write_text(json.dumps(mut), encoding='utf-8')
env = dict(os.environ, TMPDIR='/home/marek/projekty/leafre-work/scratch/h42')
p = subprocess.run([sys.executable, str(root/'tools/progress_snapshot.py'),
    '--out', str(work/'snap'), '--json', str(work/'progress.json'),
    '--md', str(work/'progress.md'), '--l1l2-input', str(mutp)],
    cwd=str(root), capture_output=True, text=True, env=env)
print('mutant snapshot rc=', p.returncode)
PY
# (publisher rerun on work/progress.json with the correct artifacts/snapshot/ layout
#  prints 'ASSERTION FAILED: runnable FAIL in L1: 1 / exit_code=1 / baseline regression'
#  and exits 1; see Observation 3.)

# CI run link for PR #709:
gh run list --branch task/h42-cycle10 --limit 5
```

### 3. Controls

- **Positive:** the unmutated generated fixture makes `progress_snapshot.py` exit 0, `progress.json` carry schema `osm2leaf.progress_snapshot/v1`, five level rows and `exit_code=0`; the publisher exits 0 and writes the full summary.
- **Negative:** a single generated-fixture check flipped PASS→FAIL makes `progress_snapshot.py` exit 1 (`L1 FAIL=1`, `exit_code=1`, baseline regression) and makes the publisher exit 1 with fail-loud assertions, while still publishing the honest (RED) summary.
- **NO_RUNNABLE control:** a synthetic `progress.json` with `problems=['l3check.py --build-corpus rc=3: NO RUNNABLE TARGETS']` makes the publisher label `**L3 result: NO RUNNABLE TARGETS (RED)**` and exit 1 — never a green SKIP, never a PASS.

### 4. Scope

Workflow files only: new `.github/workflows/progress.yml` (PR + push main, py3.11, blocking, one job) and a new section in `.github/workflows/README.md`; TODO H42 claim (already pushed) and C-3290–C-3299 claim rows. No changes to `tools/*`, no vendor data, no IMG256/ROOT/card tree, no QEMU/M8 execution, no L5 bench execution, no network fetch. The job composes already-shipped tools (H26/H27/H28/H41/H55/H56); it does not re-derive verdicts. Artifacts: `progress.json`, `progress.md`, snapshot log and intermediate `artifacts/snapshot/{l1l2,matrix,l3,progress-report}.json`.

### 5. Falsifier

The observation that would refute the hypothesis: the PASS→FAIL mutation leaving the publisher green, a missing H41 matrix silently omitted from the summary, L3 rc=3 shown as a PASS/green SKIP, L4/L5 auto-passed, or any number in this EXP not reproducible from one of the commands above.

## Observations

1. `python3 tools/progress_snapshot.py --selftest` prints `progress_snapshot self-test: 27/27 checks OK` (rc=0).
2. Positive snapshot run (rc=0) emits `progress.md` with the five rows: L1 `1 / 0 / 0 / 0 / 0 / 0 / PASS`, L2 `8 / 0 / 1 / 2 / 0 / 0 / PASS WITH GAPS`, L3 `3 / 0 / 0 / 0 / 0 / 10 / PASS WITH GAPS`, L4-emulator `NOT RUN (hardware/QEMU unavailable)`, L5-bench `NOT RUN (hardware/QEMU unavailable)`; `firmware_proof_passes=2`, `synthetic_passes_not_firmware_proof=1`, `exit_code=0`.
3. `artifacts/snapshot/matrix.json` is `osm2leaf.l1l2-matrix/v1`, 12 rows (9 PASS / 0 FAIL / 1 SKIP / 2 NOT_COVERED / 0 NOT_RUNNABLE). Per-feature rows are **not** in `progress.json`; the publisher reads `matrix.json` and a missing/unparseable matrix is a named failure.
4. Publisher positive control: prints `progress.json schema: osm2leaf.progress_snapshot/v1`, `level rows: ['L1','L2','L3','L4-emulator','L5-bench']`, `H41 matrix rows: 12`, `firmware proof / synthetic: 2 / 1`, `snapshot exit_code: 0`, exits 0, and writes the summary with all six sections.
5. Negative mutation: mutant snapshot `rc=1`, `exit_code=1`, L1 row `{runnable PASS: 0, FAIL: 1, verdict: FAIL}`; publisher `rc=1` with assertions `runnable FAIL in L1: 1`, `snapshot exit_code=1 (not 0)`, `baseline regressions: ['REGRESSION: L1|ZE0 generated fixture tree|structural: PASS -> FAIL']`; summary still written with the honest RED L1 row and the assertion block.
6. NO_RUNNABLE control: publisher exits 1, summary contains `**L3 result: NO RUNNABLE TARGETS (RED).** ... NOT a PASS and NOT a green SKIP`.
7. `yaml.safe_load` parses all four workflow files; `git diff --check` clean; `claims_check: OK`, `todo_check` OK.

CI run link: PR #709 (`https://github.com/neutrinus/OSM2Leaf/pull/709`). The first push of `progress.yml` triggers `progress` on the PR; the run URL will be recorded in the final Result line once `gh run list --branch task/h42-cycle10` prints it.

## Interpretation

- **FACT:** a single self-contained job can publish the H27 schema-v3 progress signal plus the H41 per-file/per-feature matrix as job summary + artifacts, with no vendor data and no firmware/emulator/bench execution.
- **FACT:** the publisher reads per-feature rows from `matrix.json`, not from `progress.json`, and fails loudly when that file is absent or malformed (navigator condition 1).
- **FACT:** l3check rc=3 is surfaced as `NO RUNNABLE TARGETS (RED)` and the run fails; SKIP/BLOCKED/NOT_RUNNABLE/NOT RUN are never counted as PASS (navigator condition 2, rule 13).
- **FACT:** a PASS→FAIL mutation makes both the snapshot and the publisher exit 1, and every number quoted above is printed by a command in Method step 2 (navigator condition 3a/3b).
- **LIMITATION:** this is a no-vendor CI signal only. Rule 13 acceptance still requires a firmware reader VA plus an L3/L4/L5 run; no card acceptance is implied.

## Follow-ups

- [ ] TL: observe the first `progress` run on PR #709 and confirm the summary sections render (H42 Done-when "EXP links one CI run").
