# GitHub Actions workflows

## `l1l2-fixtures.yml` — L1/L2 fixtures and progress matrix (H26/H41)

Runs `tools/l1l2_fixtures.py` on Python 3.11/3.13 (blocking) and 3.14
(informational, zlib-ng/H9). H41 adds `tools/l1l2_matrix.py`, which maps the
ten registry checks to rows keyed `level,file,feature` with explicit
claim/tool evidence (`C-3270–C-3274`, `C-2760`, `C-4340`) and emits
`l1l2-matrix.json`/`.md` artifacts and a job summary. Feature attribution is
data keyed by check ID; unmapped checks and ADDRE/section-4 names are reported
`NOT_COVERED`, never inferred.

**Regression policy (H41/H43).** `tools/fixtures/l1l2-matrix-baseline.json`
is the committed no-vendor baseline for the generated fixture. The matrix step
fails on a runnable `FAIL`, on a baseline row that drops status (including
`PASS→FAIL`, `PASS→SKIP`) and on a baseline key that disappears from the report
(H69 set equality). A status rise (`FAIL→PASS`) is printed as an improvement,
not an error; a new key is informational. `SKIP`, `NOT_COVERED` and
`NOT_RUNNABLE` are never counted as PASS. Baseline refresh requires an EXP/PR
rationale, never a change made to make a failure pass. H43 consumes this same
baseline file and `level,file,feature` key — no second schema and no second
`--check-baseline`. No firmware acceptance claim (rule 13), no vendor data.

## `main-watch.yml` — gate verdict on `main` (H117)

The `push` run of `ci.yml` is cancelled by the next push, so a red gate could
ride into `main` unnoticed (2026-11-20: 4 red runs beside 16 merges). This
workflow (`workflow_run` after a completed `CI quality gate`/`L1/L2 synthetic
fixtures` run on `main`, plus an hourly sweep and `workflow_dispatch`) runs
`.github/scripts/main_watch.py` **once per workflow**, each with its own
`--workflow` (`M9.64`: a green `L1/L2 synthetic fixtures` run tests the card
round-trips and never covers a red `CI quality gate` run, which tests
selftest/claims_check/todo_check/fn_audit):

- **salient red** (no later green run **of the same workflow** on `main`) → one
  `[H117] fix:` issue naming the SHA and the failed job/step, and the job fails;
- **shadowed red** (a later green run of the same workflow covers it) →
  counted, not failed;
- **unrelated green** (a green run of the *other* workflow) → counted, never
  shadowing;
- **`cancelled`** → counted as the concurrency de-dup, never as a green;
- **no runs** → exit 2, never a pass.

Policy (H98) stays preferred: required PR checks make the PR run and the push
run the same verdict; `main` is unprotected today, so this watchdog is the
fallback. `python3 .github/scripts/main_watch.py --selftest` and `--replay
RUNS_JSON` run the same policy offline. `tools/gate.py` is unchanged.

## `ci.yml` — quality gate (H25)

Runs on `pull_request` and `push` to `main`. It has two independent blocking jobs: `quality` (the standing gate) and `l3` (H28, synthetic corpus). Both are deterministic **test-infrastructure quality checks**, not coverage and not card acceptance.

### Hard gate (blocking merge check)

On Python **3.11** and **3.13** the one blocking step is:

- `python tools/gate.py` — the standing gate (H85). It runs four commands in a fixed order and applies one **PASS / FAIL / SKIP** policy:

  | gate | command it runs |
  | --- | --- |
  | `selftest` | `python tools/selftest.py` |
  | `claims_check` | `python tools/claims_check.py --strict --count-check` |
  | `todo_check` | `python tools/todo_check.py` (strict on under `--board-clean`, red until H53) |
  | `fn_audit` | `python tools/fn_audit.py archive/head256.img --corpus … --overlay …` |

- **SKIP is never PASS.** Each gate is `PASS` (ran, exit 0), `FAIL` (ran, non-zero for a real defect) or `SKIP (reason)` (a vendor input is absent, so the gate never ran). The job summary prints the SKIPs and the step exits 1 only when a *runnable* gate FAILs — a SKIP-only image gate does not make the step green-as-passed.
- `fn_audit` is the gate that **SKIPs in PR CI**: `archive/head256.img` is not on the runner. It must **PASS** in the separate manual H84 real-image workflow, which has the image (`--require-image` turns a missing head into a FAIL there). That workflow is **not** H28's synthetic L3 job.

### Informational (non-blocking)

Python **3.14** runs the same checks as an informational job (`continue-on-error`). Rationale: Python 3.14 environments may use `zlib-ng`, which does not reproduce stock zlib 1.3.1 byte-identical streams (H9). This workflow does not perform byte-identical vendor recompression claims; compression/rebuild byte-identity checks belong under stock zlib and are out of scope here.

### L3 synthetic corpus job (H28)

A separate **blocking** job (`l3`, Python 3.11, `timeout-minutes: 20`) runs
`python3 tools/l3check.py --build-corpus --json l3.json` and uploads
`l3.json`/`l3.txt`. The `quality` matrix stays blocking on Python 3.11/3.13
(3.14 informational); the L3 job has one leg because the synthetic corpus and
the PySh4 backend have no zlib-version variant. There is **no
`continue-on-error`** on any L3 step.

The job summary is built from the *real* `l3check` schema — no `summary` key
(that belongs to `gate.py`). It reads `counts` (`pass`, `fail`, `skip`,
`blocked`, `runnable`, `total`, all lowercase), `targets` (each with an
uppercase `status`), `result` (`PASS`, `FAIL`, `NO_RUNNABLE`), `exit`,
`corpus.entries` and `target_count`. It prints one row per target with its
reader, entry kind, claims and result, then the counts line. A missing JSON
file (usage error, exit 2) fails the parser step rather than becoming a pass.

**Verdict policy**

- The tool exit is propagated unchanged: `0` PASS, `1` FAIL, `2` usage error,
  `3` NO_RUNNABLE. Exit 3 is explicitly labelled **`NO RUNNABLE TARGETS`**
  and stays RED — never a green SKIP, never a PASS.
- `BLOCKED` (no located reader entry point) is **counted, not failed and not
  passed**. It is a different thing from `gate.py`'s `SKIP` (a missing vendor
  input); neither is evidence.

Measured baseline at `HEAD 6073164e` (see the H28 EXP): `counts` =
`pass 3 / fail 0 / skip 0 / blocked 10 / runnable 3 / total 13`, `result PASS`,
`exit 0`, `corpus.entries 111` with one declared skip (no vendor ADDRE pair),
`target_count 13`. The three PASS rows differ: `probe-zlib-cmf` is
`synthetic: true, l3_claim: false` (runner/dispatcher fixture), while
`point_walk_us2011` and `poi_record_decode` are `synthetic: false,
l3_claim: true` firmware-fragment runs **on synthetic corpus data**. None is
card acceptance (rule 13); the job reports no L4/L5 verdict.

### Manual IMG256 real-image mode — contract only (documented by H28)

The *default PR jobs stay vendor-free*: no image fetch, no network step and no
`IMG256` in `ci.yml`. H28 only documents the contract of a **separate**
`workflow_dispatch` job (owned and implemented by H84, not by this PR):

- input `run_img256` (boolean, default `false`); manual dispatch only, on an
  approved/self-hosted runner if `files.viaaq.eu` is unavailable; never runs on
  every PR without an explicit cost justification;
- `tools/fetch_image.py --image IMG256` fetches **only the 256 MiB firmware
  head**, verified against its pinned SHA-256, into a cache keyed by that
  digest, then `tools/realcheck.py IMG256` runs the pinned head checks;
- limits: no full `ROOT`, no card tree, no 7 GB image, timeout **≤ 20 min**;
- the result is labelled **"firmware-head regression"** — a real-bytes
  regression check, *not* full L3 on a card and not rule-13 acceptance.

### Deliberately out of scope (default PR jobs)

- No vendor images, firmware dumps, full card trees, or `IMG256` in the default PR jobs.
- No QEMU build, SH-4 runtime, or L4 hardware tests.
- No secrets or vendor data in workflow files or artifacts.

If a selftest becomes environment-unstable in GitHub Actions (missing `qemu-system-sh4`, `binutils-sh4`, disk pressure), classify it honestly as **SKIP with reason** in the tool/selftest rather than masking it as PASS. If the gate cannot be made green with honest classification, follow H25 Stop: open a task for the unstable case and mark H25 `blocked` with `Unblock:` only when appropriate.
