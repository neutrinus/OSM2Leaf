# EXP-2026-11-24-H146-selftest-gate-fixes

- **Status:** done
- **Date:** 2026-11-24
- **Sample:** `none (tool-only task)` — static check of `tools/inter_l3_probe.py` and the claim ledger
- **Tools:** python3 3.15.0 (stdlib), repo tools `tools/inter_l3_probe.py`, `tools/claims_check.py`, `tools/todo_check.py`, `tools/selftest.py`, `tools/board.py`
- **Claims:** C-10340–C-10343
- **Supersedes:** none
- **Superseded by:** none

## Question

Why did the standing `CI quality gate` on `origin/main` `007d6cd3` still report `selftest FAIL` and `claims_check FAIL`?

## Hypothesis

Two independent defects: (1) `tools/inter_l3_probe.py:selftest()` ends with `return 0 if fails else 1`, the inverse of every other tool, so a clean PASS exits 1 and `selftest.py` reports `tool:inter_l3_probe FAIL`; (2) C-7194 pins `26 checks`, but `_exp_revision()` resolves its measurement revision to `57146bb7` (the newest commit that moved both the M8.H22 EXP and `tools/ze0_unmapped.py`), where the tool printed 22 `ok` lines — the later tool-only `1322037e` raised it to 26 without moving the record. Falsifier: after the fixes a clean run still fails either check, or a deliberately failing `inter_l3_probe` check exits 0.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `tools/inter_l3_probe.py`, `docs/research/claims.md`, `tools/claims_check.py` |
| SHA-256 | none (tool-only task) |
| Offset(s) / VA(s) | n/a |
| Tool / version | python3 3.15.0 |
| Repo tool | `tools/claims_check.py` (the number), `tools/inter_l3_probe.py`, `tools/selftest.py` |

## Method

1. **Sample and hash.** No vendor bytes: static tool/ledger state at `origin/main` `007d6cd3`.
2. **Commands.**
   ```bash
   python3 tools/inter_l3_probe.py --selftest
   python3 tools/claims_check.py --strict --count-check
   python3 tools/selftest.py --only inter_l3_probe
   python3 tools/selftest.py --only claims_check
   ```
3. **Controls.** *Positive*: a clean `inter_l3_probe --selftest` prints `selftest: PASS` and exits 0. *Negative*: a copy of `inter_l3_probe.py` with `sorted(FAMILIES) == [5, 6]` flipped to `[5, 7]` prints `selftest: FAIL (1)` and exits 1. For the count rule, `git show 57146bb7:tools/ze0_unmapped.py` prints 22 `ok` lines while the current tool prints 26, so a claim of 26 at the pinned revision is wrong and 22 is right.
4. **Scope.** Two tools and one claim row; no firmware image or vendor data is read. The earlier ghost-`Unblock` half of this gate failure (M8.H5a/M8.H81) was already fixed upstream in commit `007d6cd3` and is not repeated here. Excluded: the `eu2014` missing-evidence rows (H145, PR #793) and other agents' in-flight work.
5. **Falsifier.** See Hypothesis.

## Observations

```text
$ python3 tools/inter_l3_probe.py --selftest     # before
selftest: PASS
exit 1

$ python3 tools/inter_l3_probe.py --selftest     # after
selftest: PASS
exit 0

$ python3 - <<'PY'                              # negative control
# flip one expectation in a copy of the module, then call selftest()
PY
selftest: FAIL (1)
exit 1

$ python3 tools/claims_check.py --strict --count-check   # before
count mismatches: 1
  COUNT C-7194 claims 26, tools/ze0_unmapped.py prints 22 (57146bb7)
claims_check: FAILED

$ python3 tools/claims_check.py --strict --count-check   # after
count mismatches: 0
claims_check: OK
exit 0

$ python3 tools/selftest.py --only inter_l3_probe && python3 tools/selftest.py --only claims_check
tool:inter_l3_probe  PASS
tool:claims_check    PASS
```

`git show 57146bb7:tools/ze0_unmapped.py --selftest` prints 22 `ok` lines; `1322037e` (tool-only) and the current tree print 26.

## Interpretation

- **FACT:** `inter_l3_probe.py` had an inverted selftest exit code; every other tool returns `1 if fails else 0`.
- **FACT:** C-7194's 26 came from a tool-only commit that did not move the EXP, so the H78 pin stayed at `57146bb7` (22); quoting 22 at that pin clears the mismatch. The 26 remains true on `main` and is recorded here for the record reader.
- **OBSERVED:** `claims_check` now reports 0 duplicate IDs, 0 count mismatches; `todo_check --selftest` is clean (ghost refs fixed upstream).
- **UNKNOWN:** none for this task.

## Conclusion

`tools/inter_l3_probe.py` now returns 0 on PASS and 1 on a failed check. C-7194 quotes its pinned 22 checks, with the later 26 noted above. The two `selftest`/`claims_check` failures attributable to this branch are gone; the `eu2014` missing-evidence rows belong to H145 (PR #793).

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/inter_l3_probe.py --selftest              # expected: selftest: PASS, exit 0
python3 tools/claims_check.py --strict --count-check     # expected: count mismatches: 0; claims_check: OK
```

## Follow-ups

- [ ] Merge the eu2014 head fix (H145, PR #793) to clear the four remaining missing-evidence rows on `main`.
