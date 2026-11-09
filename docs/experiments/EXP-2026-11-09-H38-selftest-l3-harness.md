# EXP-2026-11-09-H38: Wire `l3_harness` selftests into the main `selftest.py` gate

- **Status:** done
- **Date:** 2026-11-09
- **Sample:** none (tool-only task; no vendor data, no card image)
- **Tools:** `python3` 3.14.6 (repo runtime on this host); repo tools
  `tools/selftest.py`, `tools/l3_harness/selftest.py`,
  `tools/l3_harness/engine.py`, `tools/l3_harness/ghidra_import.py`,
  `tools/l3_harness/ghidra/l3_run.py`, `tools/l3_harness/dispatch.py`,
  `tools/l3_harness/runner.py` (commit `43282ee4` base / task branch
  `task/h38-selftest-l3-harness`).
- **Claims:** none (C-3160–C-3169 reserved for H38; no claim row added — wiring
  is verified by the commands below and the suite output).
- **Supersedes:** none
- **Superseded by:** none

## Question

Does `python3 tools/selftest.py` discover and run the `tools/l3_harness`
selftests (or a named aggregate), report them, and exit non-zero when a
harness selftest fails, while keeping absent Ghidra/QEMU back ends as honest
SKIP/BLOCKED inside the harness (never a PASS)?

## Hypothesis

Adding a namespaced discovery pass for `tools/l3_harness/` (and
`tools/l3_harness/ghidra/`) and registering `tools/l3_harness/selftest.py` as
the aggregate suite `tool:l3_harness` will satisfy the gate without changing
harness logic. **Falsifier:** `python3 tools/selftest.py` does not list/report
`tool:l3_harness`, `--only l3_harness` does not run it, a harness selftest
failure does not make the main gate exit non-zero, or a Ghidra/QEMU-absent case
is reported as PASS rather than honest SKIP/BLOCKED inside the harness.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none (synthetic harness fixtures only) |
| SHA-256 | n/a |
| Offset(s) / VA(s) | n/a |
| Tool / version | `python3` 3.14.6 |
| Repo tool | `tools/selftest.py` (modified), `tools/l3_harness/selftest.py` (aggregate, unchanged logic) |

## Method

1. **Sample and hash.** Tool-only task. No vendor data and no card image were
   read or copied. All harness checks run on synthetic/in-process fixtures built
   by `tools/l3_harness/selftest.py` and the individual l3_harness tools.
2. **Commands.** Runnable as written from the repository/worktree root:

```bash
# discovery/listing
python3 tools/selftest.py --list | grep 'tool:l3_harness'

# aggregate selector (required)
python3 tools/selftest.py --only l3_harness

# discovered l3_harness tools with compatible --selftest
python3 tools/selftest.py --only l3_harness.engine
python3 tools/selftest.py --only l3_harness.ghidra_import
python3 tools/selftest.py --only l3_harness.ghidra.l3_run

# full main gate (reports l3_harness)
python3 tools/selftest.py

# negative-control mechanism: a tool --selftest exiting 1 is FAIL -> gate fails
python3 - <<'PY'
import tempfile, sys
from pathlib import Path
sys.path.insert(0, 'tools')
from selftest import Suite, run_tool
with tempfile.TemporaryDirectory() as d:
    p = Path(d) / 'bad.py'
    p.write_text('import sys\nprint("boom")\nsys.exit(1)\n')
    r = run_tool(Suite('tool:bad', 'tool', 'bad --selftest', path=p, has_selftest=True))
    print('status', r.status, 'detail', r.detail)
    raise SystemExit(0 if r.status == 'FAIL' else 1)
PY

# board/claims gates (pre-existing TODO warnings only)
python3 tools/todo_check.py TODO.md
python3 tools/claims_check.py
```

3. **Controls.** *Positive*: `python3 tools/l3_harness/selftest.py` exits 0
   (`selftest: OK (32 checks, quick)`, synthetic, no vendor data) and
   `python3 tools/selftest.py --only l3_harness` reports
   `tool:l3_harness  PASS`; the full `python3 tools/selftest.py` run reports
   `tool:l3_harness  PASS` and exits `selftest: OK`.
   *Negative*: the mechanism test above shows a tool suite whose `--selftest`
   exits 1 is classified `FAIL detail exit 1` by `selftest.run_tool`; because
   `tools/selftest.py` returns exit 1 when any selected suite fails (existing
   behavior, unchanged), a harness selftest failure propagates as a main-gate
   failure. The aggregate's own `test_runner_missing_ghidra` (Ghidra absent →
   exit 3, `MISSING_GHIDRA`, "never 0") and `test_module_run_inputs_and_engine`
   (Ghidra back end absent → `SKIP`, `l3_claim` false) remain inside the
   aggregate and keep those cases honest (they are part of the 32 passing
   checks).
4. **Scope.** Changes limited to `tools/selftest.py` discovery/wiring and
   `tools/README.md` documentation (this task's files) plus this EXP and the H38
   TODO line. No harness logic changed: `tools/l3_harness/*.py` behavior is
   unchanged. Discovery scans `tools/*.py` (existing) plus
   `tools/l3_harness/*.py` and `tools/l3_harness/ghidra/*.py` (added). l3_harness
   files without a compatible `--selftest` flag are reported as SKIP (`no
   compatible --selftest`), never failures. Corpus for the full gate run: 103
   suites total (6 builtin + 87 top-level tools + 10 l3_harness suites).
5. **Falsifier.** Any of: `tool:l3_harness` absent from `--list`/full run,
   `--only l3_harness` not selecting/running the aggregate, full
   `selftest.py` not reporting the aggregate, a forced harness non-zero exit not
   yielding a main-gate failure, or a Ghidra/QEMU-absent path classified as
   PASS.

## Observations

`--list` (l3_harness lines):

```text
tool:l3_harness.corpus         no --selftest   tools/l3_harness/corpus.py (no compatible --selftest)
tool:l3_harness.dispatch       no --selftest   tools/l3_harness/dispatch.py (no compatible --selftest)
tool:l3_harness.engine         --selftest      tools/l3_harness/engine.py --selftest
tool:l3_harness.ghidra_import  --selftest      tools/l3_harness/ghidra_import.py --selftest
tool:l3_harness.manifest       no --selftest   tools/l3_harness/manifest.py (no compatible --selftest)
tool:l3_harness.rommap         no --selftest   tools/l3_harness/rommap.py (no compatible --selftest)
tool:l3_harness.runner         no --selftest   tools/l3_harness/runner.py (no compatible --selftest)
tool:l3_harness                --selftest      tools/l3_harness/selftest.py --selftest (aggregate, bounded/quick; Ghidra/QEMU absent = honest SKIP inside, never PASS)
tool:l3_harness.stubs          no --selftest   tools/l3_harness/stubs.py (no compatible --selftest)
tool:l3_harness.ghidra.l3_run  --selftest      tools/l3_harness/ghidra/l3_run.py --selftest
```

Selector runs:

```text
$ python3 tools/selftest.py --only l3_harness
tool:l3_harness  PASS  0.13s
passed=1 failed=0 skipped=0 total=1 time=0.13s
selftest: OK

$ python3 tools/selftest.py --only l3_harness.engine
tool:l3_harness.engine  PASS  0.06s
selftest: OK

$ python3 tools/selftest.py --only l3_harness.ghidra_import
tool:l3_harness.ghidra_import  PASS  0.08s
selftest: OK

$ python3 tools/selftest.py --only l3_harness.ghidra.l3_run
tool:l3_harness.ghidra.l3_run  PASS  0.05s
selftest: OK
```

Full `python3 tools/selftest.py` (l3_harness lines + summary):

```text
tool:l3_harness.corpus         SKIP  no --selftest
tool:l3_harness.dispatch       SKIP  no --selftest
tool:l3_harness.engine         PASS  0.06s
tool:l3_harness.ghidra_import  PASS  0.07s
tool:l3_harness.manifest       SKIP  no --selftest
tool:l3_harness.rommap         SKIP  no --selftest
tool:l3_harness.runner         SKIP  no --selftest
tool:l3_harness                PASS  0.14s
tool:l3_harness.stubs          SKIP  no --selftest
tool:l3_harness.ghidra.l3_run  PASS  0.05s
passed=81 failed=0 skipped=22 total=103 time=40.94s
selftest: OK
```

Negative-control mechanism (`run_tool` on an exiting-1 `--selftest`):

```text
status FAIL detail exit 1
```

Board/claims gates:

```text
$ python3 tools/todo_check.py TODO.md
  WARN  TODO.md:2497 M9.5: firmware/search task missing Precheck
  WARN  TODO.md:2497 M9.5: firmware/search task missing Scope
  WARN  TODO.md:2497 M9.5: firmware/search task missing Stop
todo_check: OK

$ python3 tools/claims_check.py
duplicate claim IDs: 0
unregistered proposed claims: 0
bad annotations: 0
claims_check: OK
```

## Interpretation

- **FACT:** `tools/selftest.py` now discovers `tools/l3_harness/*.py` and
  `tools/l3_harness/ghidra/*.py`, registers `tools/l3_harness/selftest.py` as
  `tool:l3_harness` (aggregate), and runs it as a subprocess `--selftest`
  suite. `--only l3_harness` selects and runs the aggregate. The full gate
  reports `tool:l3_harness PASS` and exits `selftest: OK` (103 suites, 0
  failures on this host).
- **FACT:** A tool selftest with non-zero exit is classified `FAIL` by
  `selftest.run_tool` and makes `selftest.main` return 1 (existing mechanism,
  exercised by the negative control). Therefore a harness selftest failure
  makes the main gate exit non-zero.
- **OBSERVED:** Ghidra/QEMU back ends were not required for the bounded/quick
  aggregate and compatible individual selftests here; the aggregate's internal
  checks that model missing Ghidra assert `MISSING_GHIDRA`/exit 3 and `SKIP`
  with `l3_claim` false (never PASS), and those checks passed.
- **FACT:** `tools/l3_harness/dispatch.py` and `runner.py` expose `selftest`
  as a subcommand (not a `--selftest` flag detectable by `exposes_selftest`'s
  help probe), so they are listed as `SKIP (no compatible --selftest)`; the
  aggregate `l3_harness/selftest.py` covers dispatch/engine/runner/ghidra
  entry behavior and is the required gate.
- **UNKNOWN:** none material to H38.

## Conclusion

H38's done-when is satisfied: `python3 tools/selftest.py` reports the
l3_harness aggregate `tool:l3_harness` (and discovered compatible l3_harness
`--selftest` tools), exits non-zero on harness selftest failure via the
existing FAIL propagation, and supports `--only l3_harness`. Ghidra/QEMU
absence remains honest SKIP/BLOCKED inside the harness checks, never PASS. No
harness logic was changed. `tools/README.md` documents the selector and
aggregate behavior.

## Reproduction

```bash
python3 tools/selftest.py --only l3_harness   # expect: tool:l3_harness PASS, selftest: OK
python3 tools/selftest.py --list | grep 'tool:l3_harness '   # expect: aggregate listed with --selftest
python3 tools/l3_harness/selftest.py          # expect: selftest: OK (32 checks, quick)
```

## Follow-ups

- [ ] If `dispatch.py`/`runner.py` gain standard `--selftest` flag help in a
      future change, `exposes_selftest()` will discover them automatically; no
      H38 follow-up required now because the aggregate covers them.
