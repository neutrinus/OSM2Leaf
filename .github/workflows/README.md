# GitHub Actions workflows

## `ci.yml` — quality gate (H25)

Runs on `pull_request` and `push` to `main`. It is a deterministic **test-infrastructure quality gate**, not coverage and not card acceptance.

### Hard gate (blocking merge check)

On Python **3.11** and **3.13**:

- `python tools/selftest.py --json` — repo/tool selftests. Policy: tools with no `--selftest` and environment-missing dependencies are reported as **SKIP** by `selftest.py`; **SKIP is not PASS**. A FAIL blocks the check.
- `python tools/claims_check.py` — `docs/research/claims.md` ledger consistency.
- `python tools/todo_check.py TODO.md` — `TODO.md` board structure/claim-allocation lint (H24). Errors fail; warnings are reported.

### Informational (non-blocking)

Python **3.14** runs the same checks as an informational job (`continue-on-error`). Rationale: Python 3.14 environments may use `zlib-ng`, which does not reproduce stock zlib 1.3.1 byte-identical streams (H9). This workflow does not perform byte-identical vendor recompression claims; compression/rebuild byte-identity checks belong under stock zlib and are out of scope here.

### Deliberately out of scope

- No vendor images, firmware dumps, full card trees, or `IMG256`.
- No QEMU build, SH-4 runtime, or L4 hardware tests.
- No secrets or vendor data in workflow files or artifacts.

If a selftest becomes environment-unstable in GitHub Actions (missing `qemu-system-sh4`, `binutils-sh4`, disk pressure), classify it honestly as **SKIP with reason** in the tool/selftest rather than masking it as PASS. If the gate cannot be made green with honest classification, follow H25 Stop: open a task for the unstable case and mark H25 `blocked` with `Unblock:` only when appropriate.
