# GitHub Actions workflows

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

Runs on `pull_request` and `push` to `main`. It is a deterministic **test-infrastructure quality gate**, not coverage and not card acceptance.

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
- `fn_audit` is the gate that **SKIPs in PR CI**: `archive/head256.img` is not on the runner. It must **PASS** in H84's manual IMG256 job, which has the image (`--require-image` turns a missing head into a FAIL there).

### Informational (non-blocking)

Python **3.14** runs the same checks as an informational job (`continue-on-error`). Rationale: Python 3.14 environments may use `zlib-ng`, which does not reproduce stock zlib 1.3.1 byte-identical streams (H9). This workflow does not perform byte-identical vendor recompression claims; compression/rebuild byte-identity checks belong under stock zlib and are out of scope here.

### Deliberately out of scope

- No vendor images, firmware dumps, full card trees, or `IMG256`.
- No QEMU build, SH-4 runtime, or L4 hardware tests.
- No secrets or vendor data in workflow files or artifacts.

If a selftest becomes environment-unstable in GitHub Actions (missing `qemu-system-sh4`, `binutils-sh4`, disk pressure), classify it honestly as **SKIP with reason** in the tool/selftest rather than masking it as PASS. If the gate cannot be made green with honest classification, follow H25 Stop: open a task for the unstable case and mark H25 `blocked` with `Unblock:` only when appropriate.
