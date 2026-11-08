# EXP-2026-11-08-H24: `todo_check.py` TODO lint + tmp-safe mkcard selftest

- **Status:** done
- **Date:** 2026-11-08
- **Sample:** none (tool-only task) — lints `TODO.md` structure and claim allocations; mkcard change is in synthetic selftest only.
- **Tools:** `python3` (repo runtime), `tools/todo_check.py` (new), `tools/mkcard.py` (modified), `tools/claims_check.py`, `tools/selftest.py` discovery.
- **Claims:** C-2720–C-2729 (H24 claim block, allocated in TODO; no new format claim registered in `claims.md` by this EXP — board/tooling hygiene).
- **Supersedes:** none
- **Superseded by:** none

## Question

Can we lint `TODO.md` syntax, claim allocations, and required task fields, and make selftests that create large temp images safe on constrained tmpfs, without breaking the existing board or claim ledger?

## Hypothesis

A stdlib parser over the real TODO task format can detect duplicate IDs, claim-range overlaps/malformed ranges, missing required fields, status/checkbox contradictions, blocked-without-Unblock, and done-without-Result. `mkcard --selftest`'s reconcile R5 negative control can avoid a whole-image `copyfile` on tmpfs by reusing an existing temp image. Falsifier: `todo_check.py --selftest` fails, or `todo_check.py TODO.md` reports no actionable signal while known defects exist, or `mkcard.py --selftest` still fails with `ENOSPC`/quota on constrained tmp.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `TODO.md`, `tools/mkcard.py` synthetic image in temp dir |
| SHA-256 | n/a (repo text / synthetic) |
| Offset(s) / VA(s) | n/a |
| Tool / version | `python3` (repo), stdlib only in `todo_check.py` |
| Repo tool | `tools/todo_check.py`, `tools/mkcard.py` |

## Method

1. **Sample and hash.** No vendor image. Real board checked: `TODO.md` on branch `task/h24-todo-check` (220 parsed tasks at selftest time). Synthetic data is generated inside tests.
2. **Commands.**
   ```bash
   python3 tools/todo_check.py --selftest
   python3 tools/todo_check.py TODO.md
   python3 tools/mkcard.py --selftest
   python3 tools/claims_check.py
   python3 tools/selftest.py --list | grep todo_check
   ```
   Expected: `todo_check selftest: OK ...`, `todo_check: OK` or errors listing specific TODO defects, `mkcard self-test: OK`, `claims_check: OK`, `tool:todo_check` listed.
3. **Controls.** Positive (selftest): valid two-task document parses OK; real `TODO.md` parses and reports counts. Negative (selftest): duplicate task ID, overlapping claim ranges, malformed claims, blocked missing `Unblock`, checkbox/status contradiction, unknown `Depends` (warning) are detected as specified. Negative/operational: `mkcard` R5 previously failed on constrained tmp with `OSError: [Errno 122] Disk quota exceeded` during full-image copy; fixed by `o1.replace(bad)` and reopening for range computation.
4. **Scope.** Covers `TODO.md` task blocks with `- [x| ] **ID — title**` headers and `- Key: value` fields; ignores fenced code blocks; treats compact/legacy tasks (no standard fields) as skipped for standard-field checks. Checks structure/hygiene, not task semantics. Does not validate EXP file contents or `claims.md` rows (that is `claims_check.py`).
5. **Falsifier.** Known real-board defects (missing `Result` on done tasks, claim overlaps found during implementation) are not reported; or `mkcard --selftest` regresses on constrained tmp; or `selftest.py` fails to discover `todo_check.py`.

## Observations

- `todo_check.py` selftest: `OK (9 checks, 220 real tasks)`.
- Initial `todo_check.py TODO.md` on this branch reported 5 errors: done tasks missing `Result` (M2.16, M3.11, M5.13, M5.12b, M6.12). Factual `Result:` fields were added with EXP/commit refs; re-run: `todo_check: OK` (warnings only: missing Precheck/Scope/Stop on some firmware/search tasks, actionable missing standard fields on legacy/open tasks — reported, not errors).
- Real overlaps fixed during H24 (factual TODO repairs): M3.11c `C-2548-2549` → `C-2920-2929`, M4.8d `C-1908-1909` → `C-2930-2939`, M9.11b `C-2157-2159` → `C-2940-2949`. M4.16 checkbox corrected `[x]`→`[ ]` (blocked).
- `mkcard.py --selftest`: `OK` after R5 tmp-safe change.
- `claims_check.py`: `OK`.
- `tools/selftest.py --list` includes `tool:todo_check`.

## Interpretation

- **FACT:** `tools/todo_check.py` lints TODO structure/claim allocations and has `--selftest`; it is discovered by `tools/selftest.py`. `mkcard` reconcile R5 avoids a full synthetic-image copy.
- **OBSERVED:** The board had real structural defects that `claims_check.py` did not cover (done-without-Result, claim overlaps in TODO allocations); `todo_check` surfaced and the minimal factual fixes were applied.
- **UNKNOWN:** Whether CI should fail on warnings (P/S/S/legacy fields) — currently errors fail, warnings are reported.

## Conclusion

H24 adds a stdlib TODO linter (`tools/todo_check.py`) with selftest/JSON output and documents it in `tools/README.md`. It makes `mkcard --selftest` tmp-safe for the R5 reconcile negative control. The real board is clean of `todo_check` errors; remaining warnings are legacy/pre-rule-14 hygiene and are reported for follow-up.

## Reproduction

```bash
python3 tools/todo_check.py --selftest
python3 tools/todo_check.py TODO.md
python3 tools/mkcard.py --selftest
python3 tools/claims_check.py
```