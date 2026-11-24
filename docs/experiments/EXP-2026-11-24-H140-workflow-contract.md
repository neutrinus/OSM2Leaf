# EXP-2026-11-24-H140 — static guard for the CI workflow contract

- **Status:** done
- **Date:** 2026-11-24
- **Task:** TODO **H140** (workflow contract guard)
- **Sample:** `none (tool-only task)` — the corpus is the 5 checked-in
  `.github/workflows/*.yml` files, no image and no vendor bytes; the negatives
  are tool-local synthetic YAML fixtures and scratch copies of those 5 files.
- **Tools:** Python 3.13 (stdlib only); repo tools `workflow_contract.py`,
  `selftest.py`, `gate.py`, `board.py`; worktree HEAD
  `f9853b146aa0cc6216346b941fd524b40b3d7845`.
- **Claims:** C-10020–C-10029
- **Supersedes:** none
- **Superseded by:** none

## Question

Can a static, stdlib-only guard on the checked-in workflow files make the four
CI guarantees machine-checkable and blocking — PR workflows vendor-free,
blocking steps blocking, vendor checks manual/weekly, and a level's PASS not
silently disappearing — while passing on today's files and failing loudly on
each injected break?

## Hypothesis

Yes. A narrow YAML-subset reader can decide seven rules statically if it strips
comments, quoted echoes and job-summary strings before matching. Falsifier: an
injected break still exits 0, a legitimate comment saying "no IMG256" is
flagged, a step-level `continue-on-error: true` is missed, or a SKIP is counted
as PASS.

## Inputs

| Item | Value |
| --- | --- |
| Corpus | `.github/workflows/{ci,firmware-regression,l1l2-fixtures,main-watch,progress}.yml` |
| Corpus count | `5` files (`ls .github/workflows/*.yml \| wc -l`) |
| PR-trigger files | `3` (`grep -lE '^  pull_request:' ... \| wc -l`) |
| dispatch/schedule files | `2` (`grep -lE 'workflow_dispatch\|schedule' ... \| wc -l`) |
| literal `continue-on-error: true` | `0` (`grep -rEc ... \| awk` sum) |
| Repo tool | `tools/workflow_contract.py` (the tool that produced the numbers) |
| Sample SHA-256 | none (no vendor sample) |

## Method

1. **Sample and hash.** No vendor sample. `HEAD=f9853b1…` above pins the
   tool revision; `files=5`, `pr_files=3`, `dispatch_files=2`, `literal_true=0`
   are quoted from the commands in part 2. The H84 "0 files" and H140 "prints
   `main-watch.yml`" (1 file) dispatch/schedule premises are both stale; the
   measured value is `2` and neither stale number is reused.

2. **Commands.** From the repository root:

```bash
python3 tools/workflow_contract.py --json /tmp/opencode/wf.json; echo "exit=$?"
python3 -c 'import json; d=json.load(open("/tmp/opencode/wf.json")); print(d["counts"], d["ok"], len(d["rules"]))'
python3 tools/workflow_contract.py --selftest; echo "exit=$?"
python3 tools/selftest.py --only workflow_contract
python3 tools/gate.py --selftest | tail -1
python3 tools/gate.py --json /tmp/opencode/wf-gate.json >/dev/null 2>&1; echo "gate_exit=$?"
```

Negative controls are performed in a scratch copy, never on the worktree:

```bash
S=/home/marek/projekty/leafre-work/scratch/H140
mkdir -p "$S"; cp .github/workflows/*.yml "$S/"
python3 - <<'PY'
from pathlib import Path
p = Path('/home/marek/projekty/leafre-work/scratch/H140/ci.yml')
t = p.read_text().replace(
  '      - name: Standing gate (tools/gate.py)\n        id: gate',
  '      - name: Standing gate (tools/gate.py)\n        continue-on-error: true\n        id: gate')
p.write_text(t)
q = Path('/home/marek/projekty/leafre-work/scratch/H140/firmware-regression.yml')
q.write_text(q.read_text().replace(
  'python3 tools/realcheck.py IMG256 --require-image',
  'python3 tools/realcheck.py IMG256'))
PY
python3 tools/workflow_contract.py --workflows-dir "$S" 2>&1 | grep -E 'FAIL|contract:'; echo "exit=${PIPESTATUS[0]}"
```

N2 (IMG256 fetch in a PR workflow) is exercised by `--selftest` negative N2,
which injects `python3 tools/fetch_image.py --image IMG256` into the quality
step's `run:` on a synthetic ci.yml and asserts a FAIL naming that file.

3. **Controls.** *Positive:* today's 5 workflows with their informational
   comments, quoted echoes and job-summary "no IMG256" strings must produce 7
   PASS rows and exit 0; the synthetic fixture's comment/quote positives must
   stay green. *Negatives:* N1 injects a step-level `continue-on-error: true`
   on the quality step; N2 injects an executable IMG256 fetch into a PR
   workflow's blocking step; N3 removes `--require-image` from the manual
   realcheck step; N4 removes the watchdog's `schedule`; N5 removes the H41
   baseline and H28 L3 steps. Each must exit 1 and name the injected file.

4. **Scope.** 5 workflow files and the tool-local synthetic YAML only. No
   vendor image, no fetch, no workflow file edited, no existing gate assertion
   changed. Rules are keyed by rule name plus the workflow-file set, never by a
   line number or index. Genuinely undecidable rules print SKIP and exit 1;
   N/A rules print no row at all, so a clean tree shows exactly one PASS row
   per rule.

5. **Falsifier.** Claim refuted if an injected break exits 0; the guard passes
   while a PR workflow executes an IMG256 fetch; today's comment/echo mentions
   or the job-level `${{ matrix.experimental }}` are flagged; a SKIP is counted
   as PASS; or any workflow file / existing gate assertion is changed.

## Observations

- Positive control:
  `python3 tools/workflow_contract.py --json /tmp/opencode/wf.json` printed 7
  rows, all PASS, and `workflow contract: 7 PASS, 0 FAIL, 0 SKIP` with
  `exit=0`; the JSON document printed `{'PASS': 7, 'FAIL': 0, 'SKIP': 0} True 7`.
- The 7 rows are `pr-vendor-free` on
  `ci.yml,l1l2-fixtures.yml,progress.yml`; `blocking-steps-blocking` on all 5;
  `watchdog-triggers` on `main-watch.yml`; `manual-vendor-only` and
  `realcheck-require-image` on `firmware-regression.yml`; `h41-baseline-step`
  on `l1l2-fixtures.yml`; `h28-l3-step` on `ci.yml`.
- `python3 tools/workflow_contract.py --selftest` printed
  `workflow_contract selftest: OK (12 checks, 0 failed)` with `exit=0`: the
  positive control plus N1–N5 all passed.
- `python3 tools/selftest.py --only workflow_contract` printed
  `tool:workflow_contract  PASS  0.27s` and `passed=1 failed=0 skipped=0 total=1`.
- `python3 tools/gate.py --selftest | tail -1` printed
  `gate selftest: OK (20 checks, 0 failed)` — unchanged from baseline.
- `python3 tools/gate.py --json /tmp/opencode/wf-gate.json` printed
  `gate_exit=0`.
- Under heavy parallel-agent load, a later full `gate.py` run printed
  `gate: 4 pass, 1 fail, 0 skip`: `selftest` failed only because several suites
  timed out at the runner's 60 s cap or hit `[Errno 122] Disk quota exceeded`
  on the 3.8 GiB `/tmp` tmpfs (`df -h /tmp`: 3.1G used, 764M free). With
  `TMPDIR=/home/marek/projekty/leafre-work/scratch/tl-tmp2` the same gate
  printed `claims_check PASS`, `todo_check PASS`, `board_check PASS`,
  `fn_audit PASS` and only `ci_gate_repro FAIL timeout after 60s (60.09s)`;
  `selftest.py --only ci_gate_repro --timeout 180` then printed PASS in
  100.20 s. No failure came from `workflow_contract`, which passed in every
  run.
- Real-file negatives (scratch copies of the 5 workflows with N1 and N3
  injected) printed:
  `blocking-steps-blocking … FAIL step Standing gate (tools/gate.py)` and
  `realcheck-require-image … FAIL step Run firmware-head regression (real bytes) lacks --require-image`,
  with `workflow contract: 5 PASS, 2 FAIL, 0 SKIP` and `exit=1`.
- `grep -rEc 'continue-on-error:[[:space:]]*true' .github/workflows/*.yml`
  summed to `0`; the two real `continue-on-error:` lines are expressions on
  the informational 3.14 matrix leg and were not flagged.

## Interpretation

- **FACT:** the guard reports exactly one PASS row per rule (7) and exits 0 on
  today's files; each of the five injected breaks (N1–N5) exits 1 and names the
  injected workflow file.
- **FACT:** `gate.py --selftest` still prints `OK (20 checks, 0 failed)` and the
  new tool is auto-discovered as `tool:workflow_contract`.
- **OBSERVED:** comments, quoted echoes and Python job-summary strings that
  mention IMG256 did not false-positive; stripping quoted spans before matching
  was necessary — progress.yml writes `out.write('… IMG256 …')` as prose.
- **HYPOTHESIS:** the tool's YAML subset reader covers the subset used by the
  checked-in workflows; a future workflow using a construct outside that
  subset could be mis-scanned, which is why undecidable steps are SKIP and
  redden the run rather than silently passing.
- **UNKNOWN:** whether GitHub Actions resolves the workflows identically; the
  guard is deliberately static and does not execute Actions (rule 13 unchanged).

## Conclusion

`tools/workflow_contract.py` makes the H140 CI contract machine-checkable and
blocking without touching any workflow file or existing gate. Today's 5
workflows produce 7 PASS rows and exit 0; all five injected breaks fail loudly
with the injected file named. No format doc changes; claims C-10020–C-10029
record the guard, the false-positive trap, the SKIP policy and the negatives.
The stale dispatch/schedule premise is corrected by the measured value `2`.

## Corrections after navigator review

- Round 1: weakened the guard's verdict so N/A rows produce no row at all,
  leaving exactly one PASS per rule on today's files (C1/C5), and scoped every
  negative assertion to its injected file (C2). No tool logic beyond reporting
  was changed after the navigator's APPROVE.

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/workflow_contract.py --json /tmp/opencode/wf.json; echo "exit=$?"  # 7 PASS, 0 FAIL, 0 SKIP; exit=0
python3 tools/workflow_contract.py --selftest; echo "exit=$?"                       # OK (12 checks, 0 failed); exit=0
python3 tools/selftest.py --only workflow_contract                                   # PASS
```

## Follow-ups

- [ ] Wire `workflow_contract.py` into `tools/gate.py` only if TL decides the
      guard should be a standing gate row (H140 deliberately adds a separate
      blocking tool and does not change any existing gate assertion).
