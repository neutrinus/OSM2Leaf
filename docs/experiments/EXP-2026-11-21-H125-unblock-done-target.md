# EXP-2026-11-21-H125: todo_check flags a blocked task whose Unblock names a done/archived task

- **Status:** done
- **Date:** 2026-11-21
- **Sample:** `none (tool-only task)` — the tool reads the checked-in
  `TODO.md` and `docs/research/todo-history-*.md`, no vendor bytes
- **Tools:** `python3` 3.15.0, repo tools `tools/todo_check.py`,
  `tools/gate.py`, `tools/selftest.py`, `tools/claims_check.py`
- **Claims:** C-6590–C-6593
- **Supersedes:** none
- **Superseded by:** none

## Question

Does `tools/todo_check.py --strict` fail on a `blocked` task whose `Unblock:`
names a task that is already `done`, or one that is archived (the rule-15
hole that left M3.29 and M4.23), and can it do so while `tools/gate.py`
(run non-strict) and the default `todo_check` run stay green?

## Hypothesis

Rule 15 re-opens a blocked task in the PR that lands the task its `Unblock:`
names. A named ID that already resolves `done` — or is archived in
`docs/research/todo-history-*.md` — can therefore never trigger that re-open,
and nothing in the checker reports it today. Add one rule: under `--strict`,
such a reference is an ERROR naming the blocked task and the ID; in default
mode it stays a warning so `gate.py` (which runs `todo_check` without
`--strict`) stays green while the board is repaired by M3.36.

**Falsifier** (stated before the run): a `blocked` task on `main` whose
`Unblock:` names a `done` task that the new rule does **not** print. If one
exists, the rule reads the wrong field and the fix is in the field parsing,
not the test. The companion falsifier for the escape hatch: a default-mode
`todo_check` (or `gate.py`) that goes red on the current board after the
change — that would mean the rule was not confined to `--strict`.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `TODO.md` (305 tasks) at the H125 claim commit `d585f8a7` and `docs/research/todo-history-*.md` (181 archived IDs); the tool is the branch head, not `d585f8a7` |
| SHA-256 | `none (tool-only task)` |
| Offset(s) / VA(s) | n/a |
| Tool / version | `python3` 3.15.0 |
| Repo tool | `tools/todo_check.py` (the one that produced the numbers) |

## Method

1. **Sample and hash.** `TODO.md` and the frozen archives only; no binary
   sample. The board at the claim commit `d585f8a7` carries 305 task blocks
   (printed by the tool's own summary line) and 181 archived IDs (`grep -c` of
   the `HISTORY_HEADER_RE` hits across `docs/research/todo-history-*.md`).

2. **Commands.** Runnable as written from the repository root:

   ```bash
   python3 tools/todo_check.py --strict > /tmp/opencode/h125_strict.txt 2>&1; echo "strict exit=$?"
   grep -cE '^  ERROR' /tmp/opencode/h125_strict.txt
   grep -E 'M3\.29: Unblock references done task ID .M9\.53.|M4\.23: Unblock references archived task ID .M4\.25.' /tmp/opencode/h125_strict.txt
   python3 tools/todo_check.py; echo "default exit=$?"
   python3 tools/todo_check.py --fix-list
   python3 tools/todo_check.py --selftest
   ```

3. **Controls.**
   - *Positive* (the rule must fire): `M3.29` (`Unblock: M9.53`, done) and
     `M4.23` (`Unblock: M4.24 (part b), M4.25 … M4.26 …`, with M4.25/M4.26
     archived `[x]` in `docs/research/todo-history-2026-11-09.md`) must each
     be printed as an ERROR under `--strict`.
   - *Negative* (must not fire): a `blocked` task whose `Unblock:` names only
     an `open`/`blocked` task (the `H125` selftest fixture `H4` → `H5`, and
     the parenthetical-example fixture where the only done ID sits inside
     `(…)` prose) must produce no error and an empty `--fix-list`.

4. **Scope.** Two clauses, both shipped:
   - Every `blocked` task's `Unblock:` (parenthetical spans stripped,
     duplicates collapsed) is classified against the live `Status` (`done`)
     and the archive set (`docs/research/todo-history-*.md`); a hit is an
     ERROR under `--strict`, a WARN by default.
   - Every `open` task whose `Depends:`/`Unblock:` says *cannot be taken* is
     checked for an ID that is also `open`; a hit is a WARN (never an ERROR)
     naming the task and the ID — the "open door onto an open room", with
     M3.30's text as the fixture. A task's own ID in that text (M3.30's whole
     continuation repeats it) is not a door onto another room and is skipped.

   The rule does **not** edit any block and does not judge `Depends:` beyond
   the open-door WARN (the archived/ghost/blocked split is H60's). `M3.36`
   repairs the rows; this task ships the checker only.

5. **Falsifier.** As above: a done/archived `Unblock` the rule misses, or a
   non-strict run that turns red.

## Observations

- New rule under `--strict`, new tool over the claim-commit board
  `d585f8a7:TODO.md` (board untouched; the tool is the branch head, not the
  old tool at that commit):

  ```text
  todo_check [strict]: 305 tasks, 17 error(s), 181 warning(s); refs archived 55 /
  ghost 0 / blocked 27 (181 archived IDs)
  strict exit=1
  17
    ERROR TODO.md:2268 M3.29: Unblock references done task ID 'M9.53'
    ERROR TODO.md:1621 M4.23: Unblock references archived task ID 'M4.25'
  ```

  The 17 ERRORs are the 8 pre-existing `--strict` errors (H53's debt:
  `M1.38`, `M3.13`, `M3.29`, `M8.C` firmware-field gaps) plus **9** new
  `Unblock` errors over **5** blocked tasks: `M3.16` (M9.38, M1.2f, M8.E1
  done), `M3.18` (M9.38, M3.23 done), `M3.29` (M9.53 done), `M4.23` (M4.25,
  M4.26 archived), `M4.51` (M4.53 done).
- The done-when named two offenders (M3.29, M4.23) and asked for those; the
  rule is universal and the honest census is five — the extra three are the
  same class (a `blocked` task whose `Unblock` names an already-merged
  token), not a false positive. See Interpretation.
- Default mode (`gate.py`'s call) stays green:

  ```text
  todo_check: 305 tasks, 0 error(s), 198 warning(s); …
  default exit=0
  ```

  The same references appear there as `WARN  … Unblock references done task
  ID …` / `… archived task ID …`, never as ERROR — the fix-list still lists
  them:

  ```text
  M4.23 / Unblock / M4.25 / archived
  M3.16 / Unblock / M9.38 / done
  M3.29 / Unblock / M9.53 / done
  M4.51 / Unblock / M4.53 / done
  ```
- The Done-when escape hatch, on a temp copy of `TODO.md` with only the two
  named offenders' `Unblock:` blanked:

  ```text
  test -f /tmp/opencode/todo_two.md   # M3.29 + M4.23 Unblock: blanked
  python3 tools/todo_check.py /tmp/opencode/todo_two.md --strict   # 14 error(s), no M3.29/M4.23 Unblock row
  python3 tools/todo_check.py /tmp/opencode/todo_two.md            # exit 0
  ```

  `--strict` drops 17 → 14 (the 3 references on the two named blocks) and no
  longer names M3.29/M4.23; the default run stays exit 0. The 6 remaining
  `Unblock` errors are the three extra offenders (`M3.16`, `M3.18`, `M4.51`).
- The open-door clause: on the real board at this commit no `open` task says
  *cannot be taken* on an `open` ID (`grep "cannot be taken"` on the default
  output: none), because M3.30's target M3.29 is `blocked`; its own-ID mention
  in the continuation is skipped. The selftest covers the case with an
  M3.30-shaped fixture (WARN) and a not-open negative control.
- `python3 tools/todo_check.py --selftest` → `todo_check selftest: OK (43
  checks, 305 real tasks)`; `python3 tools/selftest.py --only todo_check` →
  `PASS`. Monkeypatching `_strip_parens = identity` makes the selftest raise
  `AssertionError: ["TODO.md:2 H4: Unblock references done task ID 'H6'"]`, so
  the paren case is live, not vacuous.
- `python3 tools/claims_check.py` → `claims_check: OK` (exit 0).
- `python3 tools/gate.py` (base gate; `todo_check` runs **non-strict**) stays
  green, with `fn_audit` PASS and not SKIP:

  ```text
  $ git rev-parse --short HEAD
  0e04cb10
  GATE          RESULT    SECS  NOTE
  ------------  ------  ------  ----------------------------------------
  selftest      PASS    103.53
  claims_check  PASS      0.53
  todo_check    PASS      0.07
  fn_audit      PASS      4.74
  gate: 4 pass, 0 fail, 0 skip
  ```

  The table is the run at `0e04cb10` (the branch rebased onto `origin/main`
  `01a67a6e`); `fn_audit` took the real-image path (PASS, not SKIP). The
  verdict (`4 pass, 0 fail, 0 skip`) is stable across runs; the SECS column is
  host- and load-dependent.

## Interpretation

- **FACT:** `--strict` exits `1` and prints `M3.29: Unblock references done
  task ID 'M9.53'` and `M4.23: Unblock references archived task ID 'M4.25'`
  (and `'M4.26'`); both are the two blocks the task names.
- **FACT:** default `todo_check` exits `0` with the same references as WARN,
  so `tools/gate.py`, which runs `todo_check` non-strict, is unaffected.
- **OBSERVED:** the universal rule finds five offender blocks, not two. The
  extra three (`M3.16`, `M3.18`, `M4.51`) each name a task that is now
  `done`, exactly the rule-15 hole. `M3.16`'s done IDs sit in a "confirmed
  by M9.38" clause and a "`M1.2f`/`M8.E1` are superseded" parenthetical;
  stripping the parenthetical removes the superseded pair but `M9.38`
  (outside the parenthesis) remains a real, already-done confirmation token.
- **HYPOTHESIS:** M3.36's repair must also address `M3.16`, `M3.18` and
  `M4.51`, or `--strict` will keep printing 9 `Unblock` errors after the two
  named blocks are fixed.
- **UNKNOWN:** whether the M3.16/M3.18/M4.51 blocks are *correctly* blocked
  on their other, still-open tokens (they are not in H125's scope to judge).

## Conclusion

`tools/todo_check.py` gained two clauses of one rule. (a) Under `--strict`, a
`blocked` task whose `Unblock:` names a `done` or archived task is an ERROR
naming the task and the ID; default mode keeps it a warning so `gate.py`
(non-strict) stays at 4 pass / 0 fail / 0 skip. (b) An `open` task whose
`Depends:`/`Unblock:` says *cannot be taken* on an `open` ID is a WARN (never
an ERROR) — the open-door chain, M3.30's text as fixture, its own-ID mention
skipped. A `--fix-list` prints `task / field / id / target-status` rows. On the
claim-commit board `d585f8a7` this correctly fails `--strict` (17 errors = 8
prior + 9 new over 5 tasks) and names M3.29 and M4.23; the board repair is
M3.36 and is not done here. The rule is paren-stripping rather than the old
split-at-first-`(`, which had silently truncated M4.23's `Unblock: M4.24 (part
b), M4.25 … M4.26` at `M4.24` and so never saw the archived M4.25/M4.26.

## Overtaken by a later commit

- `Observations` census "5 blocked tasks / 9 refs" | rebase onto `origin/main`
  `01a67a6e` (H125 branch, merge prep) | the new rule now finds **6 tasks /
  10 refs**: the 5 above plus `M4.59` (its `Unblock:` names a done task), so
  `--strict` reports `18 error(s), 181 warning(s)` = 8 prior firmware-field +
  10 new. The rule is unchanged; the drift is main adding one more instance of
  the same class (`M4.59`), which M3.36's repair must also cover. Command:
  `python3 tools/todo_check.py --strict | grep -cE '^  ERROR.*Unblock references'`
  → `10`.

## Reproduction

```bash
python3 tools/todo_check.py --strict >/dev/null 2>&1; echo $?                 # expected: 1
python3 tools/todo_check.py --strict 2>&1 | grep 'M3.29: Unblock references'  # expected: ... 'M9.53'
python3 tools/todo_check.py            >/dev/null 2>&1; echo $?               # expected: 0
python3 tools/todo_check.py --selftest                                        # expected: OK (43 checks …)
```

## Corrections after navigator review

Round 1 returned CHANGES; four fixes, rule unchanged (strict exit 1 names
M3.29/M4.23; default exit 0; gate 4/0/0):

- **Dead paren selftest.** The old case replaced `**H5 — open target**` with
  `**H6 — done\n**`, a malformed header whose status stayed `open`, so no done
  ID ever sat inside `(…)` and the assert was vacuous (with `_strip_parens =
  identity` the selftest still passed). Now `H6` is a real `[x]` done block:
  blocked `H4` on open `H5` naming done `H6` only inside `(…)` must not error,
  and the same `H6` outside the parentheses **must** error. The identity
  monkeypatch now raises `AssertionError: ["TODO.md:2 H4: Unblock references
  done task ID 'H6'"]`. Selftest grew 36 → 43 checks.
- **Sample SHA.** "at `e1b71a75`" was false — that commit carries the old
  tool. The observation is the new tool over the claim-commit board
  `d585f8a7:TODO.md` (17 errors / 181 warnings, exit 1); the sample row and
  the observation now cite `d585f8a7`.
- **Scope second clause.** The task's Scope also requires a WARN for an `open`
  task whose `Unblock`/`Depends` says *cannot be taken* on an `open` ID
  (M3.30 fixture); it was not implemented and unmentioned. It is now
  implemented (`_open_door_ids`, self-reference skipped) with an
  M3.30-shaped WARN fixture and a not-open negative control in the selftest,
  and the Scope/Conclusion record both clauses.
- **Gate SHA.** The gate table was quoted at `ece6408c`, an unreachable
  scratch commit. It is now the run at `719ae582`, a branch commit on
  `origin`, and `fn_audit` is PASS (not SKIP).

C-6590 gained the open-door clause and C-6591's sample SHA became
`d585f8a7:TODO.md` in the same push; `claims_check --strict --count-check`
stays `OK`.

## Follow-ups

- [ ] M3.36: repair the `Unblock:` rows that carry done/archived IDs. The
  validator's census is 5 blocks / 9 references — `M3.29` (1), `M4.23` (2)
  named in H125, plus `M3.16` (3), `M3.18` (2), `M4.51` (1) — so fixing only
  the two named blocks leaves **6** `Unblock` ERRORs under `--strict`
  (`M3.16`, `M3.18`, `M4.51`).
- [ ] M3.36 (or a follow-up): when M3.29 is repaired, M3.30's `Depends` text
  ("cannot be taken until M3.29 merges done", naming M3.29) becomes an
  open-door WARN only if M3.29 is `open`; while it is `blocked` the WARN does
  not fire, which matches the fixture's intent.
