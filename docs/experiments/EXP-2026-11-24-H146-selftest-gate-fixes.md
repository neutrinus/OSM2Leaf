# EXP-2026-11-24-H146-selftest-gate-fixes

- **Status:** done
- **Date:** 2026-11-24
- **Sample:** `none (tool-only task)` — static check of `tools/inter_l3_probe.py`, `tools/todo_check.py` and `TODO.md`
- **Tools:** python3 3.15.0 (stdlib), repo tools `tools/inter_l3_probe.py`, `tools/todo_check.py`, `tools/claims_check.py`, `tools/selftest.py`, `tools/board.py`
- **Claims:** C-10300–C-10303
- **Supersedes:** none
- **Superseded by:** none

## Question

Why did the standing `CI quality gate` on `origin/main` `f98a617f` report `selftest FAIL` and `claims_check FAIL`, while the same commands passed in the primary checkout?

## Hypothesis

Three independent defects, all invisible locally: (1) `tools/inter_l3_probe.py:selftest()` ends with `return 0 if fails else 1`, the inverse of every other tool, so a clean PASS exits 1; (2) `tools/todo_check.py --selftest` asserts the real board has `dep_classes['ghost'] == 0`, but `M8.H5: Unblock: M8.H5a` and `M8.H16: Unblock: M8.H81` name task blocks that exist only on open PR branches, never added to `main`; (3) C-7194 pins `26 checks` while its measurement revision `57146bb7` printed 22 (the later tool-only commit `1322037e` raised it to 26). Falsifier: after the fixes a clean clone still fails any of those three checks, or a deliberately failing `inter_l3_probe` check exits 0.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `tools/inter_l3_probe.py`, `tools/todo_check.py`, `TODO.md`, `docs/research/claims.md` |
| SHA-256 | none (tool-only task) |
| Offset(s) / VA(s) | n/a |
| Tool / version | python3 3.15.0 |
| Repo tool | `tools/claims_check.py` (numbers), `tools/inter_l3_probe.py`, `tools/todo_check.py` |

## Method

1. **Sample and hash.** No vendor bytes: static tool/board state at `origin/main` `f98a617f`.
2. **Commands.**
   ```bash
   git clone --no-checkout <repo> scratch/h146-clean && cd scratch/h146-clean && git checkout -q f98a617f
   python3 tools/inter_l3_probe.py --selftest
   python3 tools/todo_check.py --selftest
   python3 tools/selftest.py --only todo_check
   python3 tools/claims_check.py --strict --count-check
   ```
3. **Controls.** *Positive*: a clean `inter_l3_probe --selftest` prints `selftest: PASS` and a passing `todo_check --selftest` prints `OK (80 checks, 427 real tasks)`. *Negative*: a copy of `inter_l3_probe.py` with `sorted(FAMILIES) == [5, 6]` flipped to `[5, 7]` prints `selftest: FAIL (1)` and exits 1; at the pinned revision `57146bb7` `ze0_unmapped.py --selftest` prints 22 `ok` lines (not 26).
4. **Scope.** Three tools and the board/ledger text; no firmware image or vendor data is read. The two task blocks M8.H5a and M8.H81 were copied verbatim from branches `task/m8.h5-savevm` and `task/m8.h16-testmode-kernel`, with only their claim ranges moved to free IDs (C-10310–C-10319 and C-10320–C-10329). Excluded: the still-open `eu2014` missing-evidence rows (H145, PR #793) and other agents' in-flight work.
5. **Falsifier.** See Hypothesis.

## Observations

```text
$ python3 tools/inter_l3_probe.py --selftest     # before, origin/main
selftest: PASS
exit 1                                          # inverted return

$ python3 tools/inter_l3_probe.py --selftest     # after
selftest: PASS
exit 0

$ python3 - <<'PY'                              # negative control
# flip one expectation in a copy of the module, then call selftest()
PY
selftest: FAIL (1)
exit 1

$ python3 tools/todo_check.py --selftest        # before, clean clone
AssertionError: {'archived': 48, 'ghost': 2, 'blocked': 38}
  TODO.md:4848 M8.H5: Unblock references ghost task ID 'M8.H5a'
  TODO.md:5006 M8.H16: Unblock references ghost task ID 'M8.H81'

$ python3 tools/todo_check.py --selftest        # after adding both task blocks
todo_check selftest: OK (80 checks, 427 real tasks)
exit 0

$ python3 tools/claims_check.py --strict --count-check   # before
count mismatches: 1
  COUNT C-7194 claims 26, tools/ze0_unmapped.py prints 22 (57146bb7)
claims_check: FAILED

$ python3 tools/claims_check.py --strict --count-check   # after
count mismatches: 0
claims_check: OK
exit 0

$ python3 tools/board.py lost --base origin/main
TODO.md: OK tasks=0 claims=0
docs/research/claims.md: OK tasks=0 claims=0
```

## Interpretation

- **FACT:** `inter_l3_probe.py` had an inverted selftest exit code; every other tool returns `1 if fails else 0`.
- **FACT:** two `Unblock:` IDs pointed to task blocks that were never merged to `main`, so `todo_check --selftest` failed only in a clean clone.
- **FACT:** C-7194 was measured at `57146bb7` (22 checks); the `26` quoted the post-`1322037e` tool without moving the EXP and tool together, so the count rule flagged it.
- **OBSERVED:** `claims_check` now reports 0 duplicate IDs, 0 genuine missing paths and 0 count mismatches on this branch.
- **UNKNOWN:** none for this task.

## Conclusion

`tools/inter_l3_probe.py` now returns 0 on PASS and 1 on a failed check. `TODO.md` carries the two unblock task blocks M8.H5a and M8.H81 so rule 15 can re-open their parents and the ghost-reference lint is clean in a clean clone. C-7194 now quotes its pinned 22 checks, with the later 26 recorded in the M8.H22 EXP Corrections/Overtaken sections. The three `selftest`/`claims_check` failures attributable to this branch are gone.

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/inter_l3_probe.py --selftest              # expected: selftest: PASS, exit 0
python3 tools/todo_check.py --selftest                   # expected: OK (80 checks, 427 real tasks)
python3 tools/claims_check.py --strict --count-check     # expected: count mismatches: 0; claims_check: OK
```

## Follow-ups

- [ ] Merge the eu2014 head fix (H145, PR #793) to clear the four remaining missing-evidence rows on `main`.
