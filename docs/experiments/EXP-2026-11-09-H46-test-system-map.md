# EXP-2026-11-09-H46-test-system-map: Test system map (L1–L5)

- **Status:** done
- **Date:** 2026-11-09
- **Sample:** `none (doc task)` — design/doc consolidation from repo sources; no vendor bytes, no image fixture.
- **Tools:** `python3 3.14`/repo stdlib environment (local), `git 2.47` (observed via shell), repo tools `tools/todo_check.py`, `tools/claims_check.py`, `tools/selftest.py`, `tools/progress_report.py --help`, `tools/l3check.py --help`, `tools/l1l2_fixtures.py --help`, `tools/cardcheck.py --help`, `tools/l2check.py --help`, `tools/realcheck.py --help`, `tools/fetch_image.py --help`.
- **Claims:** C-3350, C-3351, C-3352, C-3353, C-3354
- **Supersedes:** none
- **Superseded by:** none

## Question

Can a single living design document map the QA target ("generated SD card images
the car would read") to concrete L1–L5 tools, workflows, fixtures, status
classes, execution environments, and gap-closure tasks without conflating
offline proof, firmware/L3 proof, L4 emulator evidence, and L5 bench/car/manual
acceptance?

## Hypothesis

`docs/research/test-system.md` can satisfy H46's required headings/sections by
restating existing repo facts and tool interfaces, following the 2026-11-09
level mapping (L4 emulator/M8, L5 bench/car) and rule 13. **Falsifier:** any
required section is missing; the doc claims firmware/car acceptance from
L1/L2/synthetic evidence; it treats `SKIP`/`NOT_COVERED`/`NOT_RUNNABLE`/
`BLOCKED`/`NOT_RUN` as `PASS`; or `todo_check.py`/`claims_check.py` fail after
adding the doc/claims/task update.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none (doc task) |
| SHA-256 | n/a |
| Offset(s) / VA(s) | n/a |
| Tool / version | `python3` (local), repo tools listed above |
| Repo tool | `tools/todo_check.py`, `tools/claims_check.py`, `tools/selftest.py` |

Sources read (names only): `AGENTS.md`, `prompt_common.txt`, `TODO.md` (H46,
H25–H29, H38, H40–H45, H47, M9.8/M9.12/M9.31 context),
`docs/research/feedback-loop.md`, `docs/research/reader-coverage.md`,
`docs/research/card-test-plan.md`,
`.github/workflows/ci.yml`, `.github/workflows/l1l2-fixtures.yml`,
`.github/workflows/README.md`, tool `--help` outputs listed above.

## Method

1. **Sample and hash.** No vendor/sample bytes used; task is documentation and
   repo-interface mapping only.
2. **Commands.**

```bash
test -f docs/research/test-system.md
grep -n "^## 1\." docs/research/test-system.md
grep -n "^## 2\." docs/research/test-system.md
grep -n "^## 3\." docs/research/test-system.md
grep -n "^## 4\." docs/research/test-system.md
grep -n "^## 5\." docs/research/test-system.md
grep -n "^## 6\." docs/research/test-system.md
grep -n "L4 readiness" docs/research/test-system.md
grep -n "SKIP.*NOT_COVERED.*NOT_RUNNABLE.*BLOCKED" docs/research/test-system.md
python3 tools/todo_check.py TODO.md
python3 tools/claims_check.py
python3 tools/selftest.py
```

3. **Controls.** *Positive:* `ci.yml`/`l1l2-fixtures.yml` and tool `--help`
   outputs exist and are cited in the doc; `test -f` passes for the new doc.
   *Negative:* the doc must not state that `SKIP/NOT_COVERED/NOT_RUNNABLE/
   BLOCKED/NOT_RUN` are `PASS`, must not claim L5/L4 acceptance from offline
   gates, and must not introduce vendor bytes.
4. **Scope.** Covers H46 deliverable only: `docs/research/test-system.md`, this
   EXP, H46 TODO status/result, and C-3350–C-3354 claims. No workflow/tool code
   changes. Tool behavior descriptions are limited to observed interfaces/help,
   workflow files, TODO task text, and cited claims.
5. **Falsifier.** Missing required section, incorrect level mapping vs
   2026-11-09 AGENTS/feedback-loop, invented tool behavior presented as fact,
   status-class promotion to PASS, or failing `todo_check.py`/`claims_check.py`.

## Observations

- `docs/research/test-system.md` created with sections 1–6 covering: level
  mapping L1–L5 (2026-11-09) + rule 13 + explicit "L4 readiness (bench
  package) maps to L5 readiness" note; existing tools/workflows with
  command/fixture; gap-closure dependency/order for
  H28,H29,H38,H40–H45,H47,M9.31; status classes
  `PASS|FAIL|SKIP|NOT_COVERED|NOT_RUNNABLE|BLOCKED|NOT_RUN` and never-PASS
  rule; execution matrix (PR CI no vendor / local-only vendor / M8 L4 emulator
  / L5 bench-manual); regression gate policy.
- `progress_report.py --help` shows `--l4-emulator-status`,
  `--l5-status`, and backward-compatible `--l4-status` alias (v1 car naming);
  documented as terminology migration, not a blocking contradiction.
- `python3 tools/todo_check.py TODO.md`, `python3 tools/claims_check.py`, and
  `python3 tools/selftest.py` were run in the H46 worktree before final commit
  (results recorded in PR/commit message context).

## Interpretation

- **FACT:** The repo contains CI/workflow and tool artifacts named by H46
  (`ci.yml`, `l1l2-fixtures.yml`, `l1l2_fixtures.py`, `progress_report.py`,
  `l3check.py`, `cardcheck.py`, `l2check.py`, `realcheck.py`, `fetch_image.py`).
- **OBSERVED:** `progress_report.py` exposes both L4 emulator and L5 bench
  status inputs with a legacy L4 alias; this matches the 2026-11-09 mapping
  migration but older prose may still say "L4 car".
- **HYPOTHESIS:** The test-system map reduces ambiguous progress claims by
  making level/fixture/status boundaries explicit for future tasks.
- **UNKNOWN:** Future task implementations (H28,H29,H38,H40–H45,H47,M9.31,M8
  gates) may change interfaces; this document must be updated in the same PRs
  that change those contracts.

## Conclusion

H46 adds `docs/research/test-system.md` as the living L1–L5 test-system map
with the required sections, explicit 2026-11-09 mapping/rule-13 boundaries, a
never-PASS status-class policy, and an execution matrix separating PR CI (no
vendor), local vendor, M8 L4 emulator, and L5 bench/manual work. It documents a
terminology migration (`progress_report` L4/L5 flags and older "L4 car" prose)
without inventing tool behavior. Firmware or car acceptance remains unproven by
this doc task.

## Reproduction

```bash
test -f docs/research/test-system.md
python3 tools/todo_check.py TODO.md   # expected: OK / 0 errors
python3 tools/claims_check.py         # expected: OK
```

## Follow-ups

- [ ] H47: land `progress_report` schema contract for H41/H43 before/with H42.
- [ ] H28/H42/H43: wire synthetic/generated L3+L1/L2 progress into CI artifacts without vendor data.
- [ ] H44/H29: machine-checkable L5 readiness and manual result registration (hardware unavailable).
- [ ] Update `test-system.md` in the same PR when a referenced tool/workflow interface or status vocabulary changes.
