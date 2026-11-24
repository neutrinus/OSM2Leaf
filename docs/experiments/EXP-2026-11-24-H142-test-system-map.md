# EXP-2026-11-24-H142: Test-system map names the CI that ships

- **Status:** done · **Date:** 2026-11-24 · **Claims:** none (docs-only; H142 says claims none)
- **Sample:** `none (tool-only task)` — no `.img`, `.DAT`, `.cmp`, `.ind` or vendor bytes opened; source of truth is `origin/main` at `74ee3ee7d02d6bddb30531291ad5e1c6e4475e31` (printed by `git rev-parse origin/main`)
- **Tools:** `python3 -VV` → `Python 3.15.0 (3.15.0-1.fc45.x86_64, Oct  9 2026, 00:00:00) [GCC 16.2.1 (Red Hat 16.2.1-2)]`; repo tools `tools/gate.py`, `tools/l3check.py`, `tools/l1l2_matrix.py`, `tools/todo_check.py`, `tools/board.py`; workflow sources `.github/workflows/{ci,l1l2-fixtures,progress,main-watch,firmware-regression}.yml` and `.github/workflows/README.md`
- **Claims:** none
- **Supersedes:** none
- **Superseded by:** none

## Question

Do the commands named in `docs/research/test-system.md` §2/§4/§6 and the L4-readiness row all exist verbatim in a workflow or tool `--help` on `origin/main`, and does the doc now say which gates are shipped versus still open?

## Hypothesis

The old map names the H25-era standalone commands (`selftest --json`, `claims_check.py`, `todo_check.py`) and calls the H28/H41/H117/H126 work "planned". These are actually shipped on `origin/main` (`tools/gate.py` five-row gate, blocking `l3check --build-corpus`, H41 matrix + committed baseline, watchdog + PR sweep, `progress.yml`), while H42/H43/H44/H104/H107/H108 are not closed. **Falsifier:** a command quoted in the refreshed doc cannot be found in the cited workflow or tool `--help`, or a shipped gate is still called "planned", or `git diff --check` fails / `todo_check.py` changes.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none (tool-only docs task) |
| SHA-256 | n/a (no vendor bytes; no recompression claim, so no `zlibinfo.py` stamp needed) |
| Offset(s) / VA(s) | n/a |
| Tool / version | Python 3.15.0 / zlib 1.3.1.zlib-ng on this host (no byte-identical claim) |
| Repo tool | `tools/gate.py`, `tools/l3check.py`, `tools/l1l2_matrix.py`, `tools/todo_check.py` (the commands that produced the quoted numbers) |

## Method

### 1. Sample and hash

No sample. Source of truth is `origin/main` at `74ee3ee7d02d6bddb30531291ad5e1c6e4475e31` (printed by `git rev-parse origin/main` after `git fetch origin`); the driver branch was rebased onto it before the final checks.

### 2. Commands

```bash
cd /home/marek/projekty/OSM2Leaf.task-h142-test-system-map
git fetch origin && git rev-parse origin/main
git show origin/main:TODO.md | grep -A2 '**H142 —'
python3 tools/board.py claim H142 --owner task/h142-test-system-map
python3 tools/gate.py --json /tmp/opencode/h142-gate.json
python3 tools/l3check.py --build-corpus --json /tmp/opencode/h142-l3.json
python3 tools/l1l2_matrix.py --input tools/fixtures/l1l2-matrix-baseline.json --json /tmp/opencode/h142-matrix.json --no-stdout-md
python3 tools/l1l2_matrix.py --input /tmp/opencode/h142-matrix.json --check-baseline tools/fixtures/l1l2-matrix-baseline.json --no-stdout-md
python3 tools/l4_status.py --selftest
python3 tools/l4check.py --selftest
python3 tools/todo_check.py > /tmp/opencode/h142-todo-base.txt
python3 tools/todo_check.py > /tmp/opencode/h142-todo-final.txt
diff -q /tmp/opencode/h142-todo-base.txt /tmp/opencode/h142-todo-final.txt
git diff --check
```

A separate Python audit (run in the worktree, no heredoc left behind) extracted every backticked token starting with `python`, `python3`, `bash`, `git`, `grep` or `--` from §2/§4/§6 and the L4-readiness row of `docs/research/test-system.md`, whitespace-normalised it, and searched all of `.github/**`, `tools/*.py`, `docs/**/*.md`, `AGENTS.md` plus the `--help` output of the named tools. Every one had to match a source other than the doc itself.

### 3. Controls

- **Positive:** the audit found 76 quoted command tokens with 0 misses after the final edit; `grep -c 'tools/gate.py'` on the doc printed 6, `main_watch` 3, `l1l2_matrix` 10, `H28` 11. `python3 tools/gate.py --selftest` printed `gate selftest: OK (20 checks, 0 failed)`; `python3 tools/l1l2_matrix.py --selftest` printed `l1l2_matrix self-test: 31/31 checks OK`; `python3 tools/progress_snapshot.py --selftest` printed `progress_snapshot self-test: 27/27 checks OK`.
- **Negative:** before the edit `grep -n 'Hard gate' docs/research/test-system.md` named `selftest.py --json` only, `grep -c 'tools/gate.py' docs/research/test-system.md` printed 0, `grep -c 'main_watch'` printed 0, and `grep -ci 'L3 synthetic corpus'` printed 0 — exactly the staleness the task describes. During the audit six candidate commands initially failed the verbatim check; each was rewritten to quote the source's real flag spelling or to quote flags separately (no `UNVERIFIED` guess was left in the doc).
- **Falsifier control:** the doc's 2026-11-09 L4/L5 mapping note (§1, lines 27–34) and §5 execution matrix were not touched; `git diff` hunk headers are only `@@ -43,31`, `@@ -110,10`, `@@ -126,50`, `@@ -184,6`.

### 4. Scope

Docs only. Edited `docs/research/test-system.md` §2 (tool/workflow table), §4 (status classes, added `NO_RUNNABLE` and source quotes), §6 (regression policy, shipped vs open) and the L4-readiness paragraph. No workflow, tool, TODO status or claim file was edited; no new verifier was added. The 76 quoted commands come from 6 workflow files, `AGENTS.md`, tool docstrings/`--help` and EXP records already on `origin/main`. Excluded: no vendor image, no L3/L4/L5 run against real data, no claim-row change (H142 assigns none).

### 5. Falsifier

If a quoted command had no source, or the doc still called a shipped gate "planned", or `git diff --check` failed, or `todo_check.py` output changed, the task would be `blocked` with a negative EXP. Stated before the result.

## Observations

1. `git rev-parse origin/main` → `74ee3ee7d02d6bddb30531291ad5e1c6e4475e31`; `git show origin/main:TODO.md | grep -A2 '**H142 —'` showed `Status: open` at claim time. PR #774 opened as draft.
2. `python3 tools/gate.py --json /tmp/opencode/h142-gate.json` → `gate: 5 pass, 0 fail, 0 skip`; gates in order `selftest | PASS`, `claims_check | PASS`, `todo_check | PASS`, `board_check | PASS`, `fn_audit | PASS`.
3. `python3 tools/l3check.py --build-corpus --json /tmp/opencode/h142-l3.json` → `counts = {pass: 3, fail: 0, skip: 0, blocked: 10, runnable: 3, total: 13}`, `result PASS`, `exit 0`, `target_count 13`, `corpus.entries 111`; the three PASS rows are `probe-zlib-cmf` (`synthetic: true, l3_claim: false`), `point_walk_us2011` and `poi_record_decode` (`synthetic: false, l3_claim: true`).
4. `python3 tools/l1l2_matrix.py --input tools/fixtures/l1l2-matrix-baseline.json --json /tmp/opencode/h142-matrix.json --no-stdout-md` and the `--check-baseline` comparison both exited 0; `tools/l1l2_matrix.py` docstring prints `python3 tools/l1l2_matrix.py --input matrix.json --check-baseline tools/fixtures/l1l2-matrix-baseline.json`.
5. `python3 tools/l4_status.py --selftest` printed `ok   table prints 'F4 BLOCKED (M8.A3, M8.A6, M9.16)' verbatim`; `python3 tools/l4check.py --selftest` printed `selftest: OK (0 failure(s))`.
6. Board status via `git show origin/main:TODO.md`: H28 `done`, H41 `done`, H42 `in progress`, H43 `open`, H44 `open`, H57 `done`, H84 `done`, H104 `open`, H107 `open`, H108 `open`, H117 `done`, H126 `done`.
7. Final verbatim-command audit: `total quoted commands: 76`, `MISS: 0` (§2/§4/§6/L4 combined).
8. `git diff --check` → clean; `python3 tools/todo_check.py` → `todo_check: OK` (rc 0) and `diff -q` against the pre-edit output printed nothing (unchanged).
9. `grep -n 'Hard gate' docs/research/test-system.md` now shows the `tools/gate.py` row; `grep -ci 'L3 synthetic corpus'` on the doc is 0 and `grep -n 'L3 synthetic corpus' .github/workflows/ci.yml` hits, so the stale "planned" claim is gone.

## Interpretation

- **FACT:** all 76 command tokens in the refreshed sections are quoted verbatim from a workflow, tool `--help`/docstring or an existing EXP on `origin/main` (observation 7); none was guessed.
- **FACT:** the doc now distinguishes shipped (H28 L3 job, H41/H57 baseline, H84 IMG256 workflow, H117/H126 watchers, H42 workflow) from open tasks (H42, H43, H44, H104, H107, H108), using the board statuses quoted in observation 6.
- **FACT:** `git diff --check` is clean and `todo_check.py` output is byte-for-byte unchanged (observation 8), so the docs-only scope held.
- **OBSERVED:** the 2026-11-09 mapping note and §5 execution matrix were not edited (hunk list in Method part 3).
- **UNKNOWN:** nothing here establishes firmware or car acceptance (rule 13); the quoted PASS numbers are from synthetic/tool-only runs on this host.

## Conclusion

`docs/research/test-system.md` §2/§4/§6 and its L4 paragraph now name the CI that actually ships, with each command quoted from the workflow or tool that prints it, and with shipped jobs separated from still-open tasks by their board IDs and statuses. No workflow, tool, TODO status or claim row was changed; no claims were allocated. H142 meets its Done when and closes with this EXP. H42/H43/H44/H104/H107/H108 remain open.

## Overtaken by a later commit

none

## Reproduction

```bash
cd /home/marek/projekty/OSM2Leaf.task-h142-test-system-map
git fetch origin && git show origin/main:TODO.md | grep -A2 '**H142 —'
python3 tools/gate.py --json gate.json
python3 tools/l3check.py --build-corpus --json l3.json
python3 tools/l1l2_matrix.py --selftest
python3 tools/todo_check.py
git diff --check
```

## Follow-ups

- [ ] H42 closes the task whose `progress.yml` workflow already ships.
- [ ] H43 adds generated-fixture L3 reporting; H104 adds the L1 `cardcheck` baseline; H107 splits the L3 `blocked` bucket; H108 makes the CI-tip audit mechanical.

## Corrections after navigator review

Solo task (TL reviews); none.
