# EXP-2026-11-09-H37: 24h senior-engineer review of completed tasks

- **Status:** done
- **Date:** 2026-11-09
- **Sample:** none (tool-only task). Reviewed commits `88332de..65e6ae2` on `origin/main` (24h window ending 2026-11-09), 80 commits, 43 EXP files added/updated in `docs/experiments/EXP-2026-11-08-*` and later in that range.
- **Tools:** `git` (repo); `python3 tools/claims_check.py` (passed, 0 duplicates, 0 unregistered); `python3 tools/todo_check.py` (passed, 0 errors, 211 warnings on legacy M8/M9 metadata); `python3 tools/factory_zlib.py --selftest` (25 checks OK); `python3 tools/road_class_probe.py --selftest` (OK); `python3 tools/chunk_decoder_l3.py --selftest` (OK); `python3.13 tools/tilewriter.py --selftest` (68/68 OK); `python3 tools/sh4scan.py --selftest` (OK).
- **Claims:** none (review creates no format/firmware claim)
- **Supersedes:** none
- **Superseded by:** none

## Question

Did tasks completed in the 24h window meet their own `Done when`, follow `docs/experiments/TEMPLATE.md`, back new claims with reproducible commands, and avoid retired leads/traps from `AGENTS.md`? What defects, deepening opportunities, and technical debt warrant new TODO tasks?

## Hypothesis

Exploratory / audit. **Falsifier:** a sampled `done` task whose `Done when` command cannot be reproduced or whose EXP lacks the required method elements (sample+hash, runnable commands, controls, counted corpus, falsifier, observations separate from interpretation) without an existing follow-up task is a defect this review must record as a new task.

## Inputs

| Item | Value |
| --- | --- |
| Commit range | `88332de97fc9..65e6ae2ba925` (`git --no-pager log --since=24.hours origin/main`) |
| EXP files added | 43 files (`git --no-pager log --since=24.hours --name-status --diff-filter=A origin/main -- docs/experiments/EXP-*`) |
| Repo checks | `claims_check.py`: OK; `todo_check.py`: OK, 211 warnings |
| Cheap re-runs | `factory_zlib --selftest`, `road_class_probe --selftest`, `chunk_decoder_l3 --selftest`, `tilewriter --selftest` (py3.13), `sh4scan --selftest` |

## Method

1. **Sample and hash.** No vendor sample. Evidence is the git range above and the EXP files listed by git.
2. **Commands.**
   ```bash
   git --no-pager log --since=24.hours --oneline origin/main
   git --no-pager log --since=24.hours --name-status --diff-filter=A origin/main -- docs/experiments/EXP-*
   python3 tools/claims_check.py
   python3 tools/todo_check.py
   python3 tools/factory_zlib.py --selftest
   python3 tools/road_class_probe.py --selftest
   python3 tools/chunk_decoder_l3.py --selftest
   python3.13 tools/tilewriter.py --selftest
   python3 tools/sh4scan.py --selftest
   ```
3. **Controls.** Positive: `claims_check.py` passes; sampled tool selftests pass. Negative: `todo_check.py` reports 211 warnings (legacy M8/M9 rule-14 metadata) — confirms the linter runs but does not make those warnings the subject of a silent edit. Not applicable as a format control (review task).
4. **Scope.** Covered: task status/result lines and EXPs for M5.13b, M5.4, M1.13, M9.11, M9.14/M9.14-reopen, M9.17/M9.17-reopen, M9.13, M9.20, M9.21, M9.22, M9.6, M3.14, M3.15, M3.19, M3.11b, M4.16b, M4.17, M4.23, M4.22, M4.8b, M4.2, M4.3, M5.12c, M5.20, M5.1b, M5.1c, M1.11, M1.12, H14, H16, H20 and related follow-ups visible in the range. Read in detail: M5.4, M1.13, M9.11, M4.17, M5.12c, M5.13b, M5.20, M9.14-reopen, M4.23, M9.20. Excluded: full re-execution of vendor-image checks (no IMG256/ROOT present in this session's cheap pass beyond selftests), QEMU/Ghidra, and line-by-line audit of every EXP.
5. **Falsifier.** Stated above. A `done` task whose `Done when` was not met and has no follow-up would falsify the "board is honest" hypothesis; this pass found no such case requiring status reversal, but found documented scope limits worth follow-ups.

## Observations

- `claims_check.py`: `duplicate claim IDs: 0`, `unregistered proposed claims: 0`, `bad annotations: 0`.
- `todo_check.py`: `todo_check: OK` (0 errors, 211 warnings, `strict_firmware: false`). Warnings are concentrated on legacy M8/M9 task metadata (Precheck/Scope/Stop/Goal).
- Sampled `done` tasks met their `Done when` or recorded an explicit negative/partial result consistent with the task: M5.4 (L2 structural pass on a real factory tile; limitations and N1-N3 controls documented), M1.13 (471/471 factory pages reproduced, encoder named), M4.17 (≥5 numbered roads, 7 classes, control; road-class field not established — done-when allowed negative), M9.21, M1.11, M5.1b/c, M9.20 (plumbing delivered; Ghidra run out of scope recorded), M5.13b (S1 byte-identical, S2 cardcheck PASS; zlib 1.3.2 deviation recorded, later made moot by M1.13).
- `blocked` tasks generally carried EXPs with controls/falsifiers and honest blockers (M9.11 blocked on target registration despite firmware path passing; M9.14/M9.17 re-blocked on compressed sec1 `.data` after M9.20 — rule 15 followed; M3.14/M3.15/M4.16b/M4.22/M4.23/M5.12c/M4.2/M4.3/M4.8b blocked with reasons).
- M5.12c: TODO is `blocked` and M5.27 tracks reconciliation; EXP header still says `Status: done (...)`. M5.27 already exists.
- M5.20: marked `done`; same-length case met the strict diff envelope exactly. Resize case includes DRSTR001.DAT value bytes and zero-fill ranges (EU grow 246 ranges, 0 outside envelope); EXP documents this and interprets DRSTR bytes as directory-entry/index updates. The strict done-when wording is not literally met for resizes; result is honest. Fresh-build contrast was not re-measured.
- M9.20 EXP notes `tools/selftest.py` does not discover `tools/l3_harness/` selftests (32 checks live in `l3_harness/selftest.py`).
- M5.4 EXP notes `harness.py info` crashes on B48R058R (`zlib.error` in `cmd_info`, pre-existing); `harness.py verify` runs.
- No retired-lead traps observed in sampled records (no big-endian search used as refutation, no fitted deltas, compression premise corrected per H20/C-2128 context; M3.14/M3.15 correctly attribute compressed sec1 as `.data`/helper path).

## Interpretation

- **FACT:** `claims_check.py` passes. Sampled selftests pass. Most sampled tasks have EXPs with runnable commands and controls; blocked tasks record blockers and unblocks.
- **OBSERVED:** EXP status headers sometimes use labels like "done (negative)" / "failed (blocked)" / "partly established" while TODO carries the authoritative task status. M5.27 already covers M5.12c reconciliation; broader normalization is hygiene, not a data defect.
- **OBSERVED:** M5.20's resize envelope includes DRSTR index bytes and stale-tail zero fills. This is documented and cardcheck-passing, but weakens the "one bad byte is visible" property for resizes.
- **OBSERVED:** L3 harness selftests are not in `tools/selftest.py` discovery; harness `info` crashes on opaque/unparseable records seen in M5.4.
- **HYPOTHESIS:** Integrating `l3_harness` selftests into the main selftest runner and hardening `harness.py info` would reduce silent regressions at low cost.
- **UNKNOWN:** Whether M5.12c's 5 unfit POI pages can be resolved by M5.21's slot-budget/repack strategy given M1.13's encoder result (stock zlib L6/m8). M5.21 is `done` but M5.12c remains blocked on its own scan/reconciliation; the unfit-page resolution path needs an explicit follow-up check.

## Conclusion

The 24h window produced substantial, mostly well-documented work: key L3 plumbing (M9.20/M9.21), a real tile splice passing structural L2 (M5.4), factory encoder identification (M1.13), real S1/S2 US images (M5.13b), and several honest blocked negatives that reopened or recorded new blockers (M9.14/17 reopen on compressed sec1 `.data`, M4.23 partial restriction layout). No sampled `done` task required silent status reversal. Follow-ups were added to TODO for selftest coverage, harness robustness, mkcard reconcile resize semantics, M5.12c unfit pages, class_code deepening, and module-entry input regions.

## Reproduction

```bash
git --no-pager log --since=24.hours --oneline origin/main | wc -l   # expected: 80 (at time of review)
python3 tools/claims_check.py                                      # expected: claims_check: OK
python3 tools/todo_check.py                                        # expected: todo_check: OK (warnings possible)
python3 tools/l3_harness/selftest.py                               # expected: selftest: OK (32 checks)
```

## Follow-ups

- [x] Added TODO tasks H38, M5.31, H39, M5.32, M4.35, M9.28 (and this H37 record) — see TODO.md.
