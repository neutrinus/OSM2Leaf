# EXP-2026-11-08-H30: Fix M9 rule-14 metadata and tighten `todo_check` firmware-task classification

- **Status:** done
- **Date:** 2026-11-08
- **Sample:** none (tool-only / board-metadata task) — edits `TODO.md` task fields and `tools/todo_check.py`; no vendor bytes.
- **Tools:** `python3` (repo runtime), `tools/todo_check.py` (modified), `tools/selftest.py`, `tools/claims_check.py`.
- **Claims:** C-2980–C-2989 (H30 TODO allocation; board/tooling hygiene, no new format claim registered in `docs/research/claims.md`).
- **Supersedes:** none
- **Superseded by:** none

## Question

Can rule 14 be made enforceable on the board by adding truthful `Precheck`/`Scope`/`Stop` metadata to the warned open/blocked M9 tasks and tightening `todo_check.py`'s firmware/search classification, without making done tasks false-failing retroactively or changing task semantics?

## Hypothesis

Adding truthful rule-14 fields to the listed M9 tasks removes their default-mode warnings, and an explicit `--strict` mode can fail open/blocked/in-progress firmware/search tasks (M1/M2/M3/M8/M9) missing `Precheck`/`Scope`/`Stop` while keeping done tasks as warnings. Falsifier: `todo_check.py TODO.md` still warns for a targeted M9 task after metadata is added; or `--strict` makes done tasks fail; or `--selftest`/real board default check regress.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `TODO.md`, `tools/todo_check.py` |
| SHA-256 | n/a (repo text) |
| Offset(s) / VA(s) | n/a |
| Tool / version | `python3` (repo), stdlib only |
| Repo tool | `tools/todo_check.py`, `tools/selftest.py --only todo_check`, `tools/claims_check.py` |

## Method

1. **Sample and hash.** No vendor sample. Board checked: `TODO.md` on branch `task/h30-m9-rule14-metadata` from `origin/main` @ `c143625`.
2. **Commands.**
   ```bash
   python3 tools/todo_check.py --selftest
   python3 tools/todo_check.py TODO.md
   python3 tools/todo_check.py TODO.md --strict 2>&1 | grep 'ERROR.*M9\.'
   python3 tools/selftest.py --only todo_check
   python3 tools/claims_check.py
   ```
   Expected: selftests OK (12 checks); default `TODO.md` has no M9.10/11/11b/12-18/20/21/24 missing-P/S/S warnings and M9.14 has no missing-Goal warning; `--strict` reports no errors for those targeted M9 tasks (other legacy M1/M2/M3/M8/M9 tasks may still error, out of scope); `claims_check` OK.
3. **Controls.** Positive (synthetic, selftest): open firmware/search task missing `Precheck`/`Scope`/`Stop` is a warning in default mode and an error in `--strict`. Negative/retroactive guard (synthetic, selftest): done firmware/search task missing `Precheck`/`Scope`/`Stop` remains a warning (ok) even in `--strict`. Real-board positive: targeted M9 tasks no longer warn in default mode after truthful metadata added. Real-board strict negative (expected, out of scope): open M9.2/M9.6 and many M1/M2/M3 tasks still error in `--strict` because H30 did not add their metadata.
4. **Scope.** Covered `TODO.md` metadata for open/blocked warned M9 tasks: M9.10, M9.11, M9.11b, M9.12–M9.18, M9.24 (truthful `Precheck`/`Scope`/`Stop` consistent with blocker/result/deps), M9.14 (`Goal` added). Trivial/correct `Precheck`/`Scope`/`Stop` also added to done M9.20 and M9.21 (from their Results/EXPs). `tools/todo_check.py` classification/severity only. Excluded: task semantics/status changes, format claims, metadata for non-listed M1/M2/M3/M8/M9 tasks, making legacy firmware/search tasks strict-clean.
5. **Falsifier.** A targeted M9 task still produces a default-mode missing `Precheck`/`Scope`/`Stop`/`Goal` warning; or `--strict` errors on a done firmware/search task missing those fields; or default `todo_check.py TODO.md` / `claims_check.py` / todo_check selftest fails.

## Observations

- `todo_check.py --selftest`: `OK (12 checks, 224 real tasks)`.
- `todo_check.py TODO.md` (default): `224 tasks, 0 error(s), 228 warning(s)`, `todo_check: OK`. No warnings for M9.10, M9.11, M9.11b, M9.12–M9.18, M9.20, M9.21, M9.24; M9.14 missing-Goal warning gone. Remaining M9 warnings are done/legacy M9.1, M9.3–M9.5 missing `Precheck`/`Scope`/`Stop` (and M9.1 missing `Goal`) and open M9.2, M9.6 missing `Precheck`/`Scope`/`Stop` — outside H30 scope.
- `todo_check.py TODO.md --strict | grep 'ERROR.*M9\.'`: only `M9.2` and `M9.6` (open, missing `Precheck`/`Scope`/`Stop`) — expected, not in H30's listed set.
- `selftest.py --only todo_check`: `PASS`, `selftest: OK`.
- `claims_check.py`: `OK`.

## Interpretation

- **FACT:** `todo_check.py` documents M1/M2/M3/M8/M9 as firmware/search task shapes (rule 14) and provides `--strict` mode where open/blocked/in-progress firmware/search tasks missing `Precheck`/`Scope`/`Stop` are errors; done firmware/search tasks warn only in strict/default mode.
- **FACT:** The warned open/blocked M9 tasks listed by H30 (M9.10, M9.11, M9.11b, M9.12–M9.18, M9.24) now have truthful `Precheck`/`Scope`/`Stop` fields consistent with their current blockers/results/deps; M9.14 has `Goal`. Done M9.20/M9.21 received trivial/correct `Precheck`/`Scope`/`Stop`.
- **OBSERVED:** `--strict` still fails on many legacy M1/M2/M3/M8/M9 tasks outside H30 scope; this is intentional — H30 did not add metadata for them.
- **UNKNOWN:** Whether CI should adopt `--strict` before legacy firmware/search tasks are retrofitted; H30 makes the mode available and covered by selftest.

## Conclusion

Rule 14 is now enforceable for the targeted M9 tasks via explicit `--strict` (or auditable in default warnings, which are gone for the target set). No task semantics or status changed except metadata additions; no format claim registered in `claims.md`. `TODO.md` and `tools/todo_check.py` updated; H30 done.

## Reproduction

```bash
python3 tools/todo_check.py --selftest
python3 tools/todo_check.py TODO.md
python3 tools/todo_check.py TODO.md --strict 2>&1 | grep 'ERROR.*M9\.'
python3 tools/selftest.py --only todo_check
python3 tools/claims_check.py
```

## Follow-ups

- [ ] Retrofit `Precheck`/`Scope`/`Stop` for remaining open firmware/search tasks (e.g. M9.2, M9.6, legacy M1/M2/M3) if `--strict` is adopted in CI — separate task(s), not H30.
- [ ] Consider done-task M9.1 metadata as trivial hygiene in a docs pass (not required; strict mode does not fail done tasks).