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

## `progress.yml` — per-level progress dashboard on every PR/push (H42)

Runs on `pull_request` and `push` to `main` (Python 3.11, **blocking**, one job).
It is self-contained: a cross-job artifact hand-off with `ci.yml` /
`l1l2-fixtures.yml` is fragile, so this job runs the offline chain itself and
publishes the result rather than relying on another job's output.

- Step 1 runs `python3 tools/progress_snapshot.py --out artifacts/snapshot --json progress.json --md progress.md`. The tool composes `l1l2_fixtures.py` (H26), `l1l2_matrix.py` (H41), `l3check.py --build-corpus --json PATH` (H28/H55) and `progress_report.py` (H27, schema `osm2leaf.progress_report/v3`). The exit is propagated unchanged: `0` no runnable FAIL/regression, `1` a runnable FAIL, a baseline regression, an `l3check` non-zero exit (including rc=3 `NO_RUNNABLE`) or a tool/parse error. No `continue-on-error`.
- Step 2 reads **the emitted files** and writes the job summary: the per-level table from `progress.md` (`level / runnable PASS / FAIL / SKIP / NOT_COVERED / NOT_RUNNABLE / BLOCKED / verdict`, schema `osm2leaf.progress_snapshot/v1`); the H41 per-file/per-feature matrix from `artifacts/snapshot/matrix.json` (`level,file,feature,status` — per-feature rows are **not** in `progress.json`, so a missing/unparseable matrix is a named failure); L3 firmware-proof PASS vs synthetic/harness PASS separation (rule 13) from the snapshot's `firmware_proof_passes` / `synthetic_passes_not_firmware_proof`; explicit **NOT RUN** rows for L4 emulator (M8) and L5 car/bench (M6); and a distinct **LOCAL-ONLY / NOT RUNNABLE — not run in CI, vendor data required** section (`realcheck IMG256`, golden `ROOT`, full 194 `REFER001`, real `LEV3456R`, QEMU/M8, L5 car).
- The publisher fails loudly when the snapshot schema is not `osm2leaf.progress_snapshot/v1`, the five level rows are missing/misordered, L4/L5 are not explicit `NOT RUN`, any row has a runnable FAIL, `exit_code != 0`, a baseline regression or any snapshot problem is present. A `l3check` rc=3 problem is labelled **`NO RUNNABLE TARGETS (RED)`** — never a green SKIP, never a PASS. The honest summary is written before the failure so a red run still publishes its true status.
- Step 3 uploads `progress.json`, `progress.md`, the snapshot log and the intermediate `artifacts/snapshot/{l1l2,matrix,l3,progress-report}.json` as the `progress-h42` artifact.

**No vendor data.** No IMG256/full card tree, no `ROOT`/golden image, no network fetch, no QEMU build and no L5 bench execution in this workflow. Local/vendor checks are listed only. Level mapping effective 2026-11-09: L3=firmware fragments, L4=full-system emulator (M8), L5=bench/car (M6). SKIP / NOT_COVERED / NOT_RUNNABLE / BLOCKED / NOT RUN are never counted as PASS (rule 13); no card acceptance claim is made.

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
- `fn_audit` is the gate that **SKIPs in PR CI**: `archive/head256.img` is not on the runner. It must **PASS** in the separate manual H84 real-image workflow, which has the image (`--require-image` turns a missing head into a FAIL there). That workflow is **not** H28's synthetic L3 job. See `firmware-regression.yml` below.

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

### Manual IMG256 real-image mode — `firmware-regression.yml` (H84)

The default PR jobs stay vendor-free: no image fetch, no network step and no
`IMG256` in `ci.yml`. The real-bytes regression instead lives in a separate
workflow, `.github/workflows/firmware-regression.yml`, which is **implemented**
by H84 (H28 only documented its contract):

- **Triggers:** `workflow_dispatch` (primary, manual QA run) and `schedule`
  (weekly, cron `23 4 * * 1`) **only** — never `pull_request`, never `push`. It
  is not a merge gate. The boolean input `run_img256` (default `false`) gates
  **only** the optional synthetic L3 corpus step on a manual dispatch; a
  `schedule` event has no dispatch inputs, so it never gates the core realcheck.
  The core `realcheck.py IMG256 --require-image` runs on both schedule and
  dispatch regardless of the input — otherwise the "weekly regression" would be
  a permanent no-op (H84 navigator must-fix).
- **Image resolution:** a `actions/cache` keyed by the pinned IMG256 digest
  holds the 256 MiB firmware head; on a miss, `tools/fetch_image.py --image
  IMG256` fetches **only the 256 MiB head** from `files.viaaq.eu` (rule-11
  fetch; no 7.4 GB card). `tools/fetch_image.py --verify` confirms the pinned
  SHA-256 (`92aa525d…007f9`, quoted from `tools/fetch_image.py --list`) before
  any check runs. Job timeout is 20 min.
- **Check:** with a verified head, `python3 tools/realcheck.py IMG256
  --require-image` runs the eight pinned real-bytes checks. The job summary
  lists PASS/FAIL per check and `realcheck.txt` is uploaded as an artifact. A
  genuine FAIL makes the job red.
- **Honest skip:** with no verified head (cache miss and no/failed network
  fetch), the summary states `SKIP (no image on this runner)` explicitly and
  the job exits 0 — a SKIP is **neither green-as-passed nor red**. This is the
  H28/H84 Hints policy: a scheduled job that turns "no cache" into red trains
  people to ignore it. Re-run via `workflow_dispatch` on an approved runner
  with a cache or network access.
- **Cost/network:** ~256 MiB download on the first run; a cached run is local
  only. The 7.4 GB full images are out of scope, and no head is vendored into
  the repository.
- **Not rule 13:** the result is a *firmware-head regression* — a real-bytes
  regression of the CE ROM tools, not full L3 on a card, not L4/L5 and not card
  acceptance. No `l3check --card` gate lives here (that is M9.12/H43), and
  `tools/selftest.py` is unchanged.

### Deliberately out of scope (default PR jobs)

- No vendor images, firmware dumps, full card trees, or `IMG256` in the default PR jobs.
- No QEMU build, SH-4 runtime, or L4 hardware tests.
- No secrets or vendor data in workflow files or artifacts.

If a selftest becomes environment-unstable in GitHub Actions (missing `qemu-system-sh4`, `binutils-sh4`, disk pressure), classify it honestly as **SKIP with reason** in the tool/selftest rather than masking it as PASS. If the gate cannot be made green with honest classification, follow H25 Stop: open a task for the unstable case and mark H25 `blocked` with `Unblock:` only when appropriate.
