# EXP-2026-11-20-H53: `todo_check --strict` errors cut to the tasks active PRs hold

- **Status:** done (with the lowered Done-when the H53 Stop allows; see Conclusion)
- **Date:** 2026-11-20
- **Sample:** `none (tool-only task)`. The input is `TODO.md` at
  `ea15563` (this branch after merging `origin/main` `0499cc0`) and the
  result commit.
- **Tools:** Python 3.13.18, `tools/todo_check.py` (unchanged),
  `tools/l4_status.py`, `tools/l3_harness/ghidra_import.py --selftest`
  (used to check the new Precheck lines)
- **Claims:** C-3650–C-3652
- **Supersedes:** none
- **Superseded by:** none

## Question

Which firmware/search tasks still fail rule 14 under
`todo_check.py --strict`, and can the board reach zero `ERROR` lines without
relaxing the rule or editing tasks that other agents hold?

## Hypothesis

The task block's 69 errors (25 tasks) are an old count. Since then, tasks
closed as `done` drop from ERROR to WARN. The remaining errors are either
tasks nobody holds, which can get `Precheck`/`Scope`/`Stop` from their own
Goal and Notes, or tasks that an open PR holds. This record must not edit
the second group (collision rules: one owner per block).

**Falsifier:** an ERROR that the fields cannot fix (a bug in the strict path
of `todo_check.py`), or an unheld task whose Precheck cannot be written as a
command that can fail.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `TODO.md` |
| SHA-256 | none (repo text; commits `ea15563` before, this PR after) |
| Corpus | 13 tasks with ERROR lines before; 33 ERROR lines; 136 WARN lines |
| Tool / version | `tools/todo_check.py` at `ea15563` |
| Repo tool | `tools/todo_check.py --strict` |

## Method

1. **Sample.** `TODO.md` before (`ea15563`) and after (this PR's head).
2. **Commands** (worktree root; `F` is any scratch path):

   ```bash
   git show ea15563:TODO.md > F
   python3 tools/todo_check.py --strict F | grep -cE '^  ERROR'
   python3 tools/todo_check.py --strict F | grep ERROR | sed -E 's/.*TODO.md:[0-9]+ ([^:]+):.*/\1/' | sort | uniq -c
   python3 tools/todo_check.py --strict | grep -cE '^  ERROR'
   python3 tools/todo_check.py --strict | grep ERROR | sed -E 's/.*TODO.md:[0-9]+ ([^:]+):.*/\1/' | sort | uniq -c
   python3 tools/todo_check.py; echo $?
   python3 tools/selftest.py --only todo_check
   python3 tools/l4_status.py | grep 'F4 BLOCKED'
   python3 tools/l3_harness/ghidra_import.py --selftest
   grep -c '^- \[x\] \*\*M8.B5 — Milestone F1' TODO.md
   ```

   The holder of each task was read from the open PR list (GitHub, 2026-11-20,
   titles `[ID] …`).
3. **Controls.**
   - *Positive:* each task that got fields has no ERROR line after the
     change (per-task `uniq -c` above).
   - *Negative:* the seven held tasks were not edited and still print their
     ERROR lines (17). This shows the drop came from the edits, not from a
     change in the checker. `todo_check.py` is byte-identical to `ea15563`.
   - Each new Precheck names a command that was run here. `l4_status`
     prints `F4 BLOCKED (M8.A3, M8.A6, M9.16)`, the ghidra selftest prints
     `OK (13 checks …)`, and the M8.B5 grep prints `1`. M9.2's
     `command -v analyzeHeadless || python3 -c 'import pyghidra'` fails in
     this sandbox, as its `Runner: non-Claude` flag says it should.
4. **Scope.** `TODO.md` task blocks M3.16, M8.D1, M8.D2, M8.E3, M8.E4 and
   M9.2 (fields added only; no other line changed), plus the H53 block.
   Not edited: M1.4 (#370), M3.13 (#351), M3.29 (#341, other TL batch),
   M8.A8 (#372), M8.B6 (#379), M8.C (#355), M8.E2 (#371). These are
   in progress under those PRs. `tools/todo_check.py` was not changed:
   no strict-path bug was found.
5. **Falsifier.** As in Hypothesis.

## Observations

Before (`ea15563`): `33` ERROR lines, default run exit `0`, strict exit `1`:

| task | missing | holder |
| --- | --- | --- |
| M1.4 | Precheck Scope Stop | PR #370 |
| M3.13 | Precheck Scope Stop | PR #351 |
| M3.16 | Stop | none (blocked) |
| M3.29 | Precheck | PR #341 |
| M8.A8 | Precheck Scope Stop | PR #372 |
| M8.B6 | Precheck | PR #379 |
| M8.C | Precheck Scope Stop | PR #355 |
| M8.D1 | Precheck Scope Stop | none |
| M8.D2 | Precheck Scope Stop | none |
| M8.E2 | Precheck Scope Stop | PR #371 |
| M8.E3 | Precheck Scope Stop | none |
| M8.E4 | Precheck Scope Stop | none |
| M9.2 | Precheck Scope Stop | none |

After: `17` ERROR lines (M1.4 3, M3.13 3, M3.29 1, M8.A8 3, M8.B6 1, M8.C 3,
M8.E2 3), all on held tasks; `0` on the six unheld tasks. WARN lines `136`
before and after. Default run exit `0`. `selftest.py --only todo_check`:
`passed=1 failed=0`.

On the held branches as pushed (`git show origin/task/<branch>:TODO.md`),
each of the seven tasks still errors (3, 3, 1, 3, 1, 3, 3). Each one clears
when its PR lands as `done` (a `done` task warns only), or must add its own
fields if it lands `blocked`.

Fields given, by source:

- **M3.16 Stop:** the Scope sentence already said "Stop: after two signature
  families fail". It is now a field tied to the M3.29 split and the H51 rule
  (no fifth signature family).
- **M8.D1 / M8.D2:** Precheck is the trigger (M8.B5 `[x]`; an `F3 PASS`
  boot log). Scope is the decision only. Stop: the decision is Marek's, so
  without his answer the task becomes `blocked · Unblock: Marek (human
  decision)`.
- **M8.E3 / M8.E4:** Precheck names the upstream gate (`M8.E4` / `M9.16`
  `[x]` and `l4_status --run-log` F3/F4 `PASS`). Scope keeps every dump
  and log in `archive/work/` (vendor-derived). Stop is a stall recorded in
  an EXP.
- **M9.2:** Precheck is the tool selftest plus the Ghidra presence check.
  Stop is exit 3 `MISSING_GHIDRA` (stays open for a non-Claude runner).

## Interpretation

- **FACT:** `--strict` works as documented. The 69 → 33 drop before this
  task came from tasks that were closed `done`, and this record takes it
  from 33 to 17. No checker change was needed.
- **FACT:** every remaining ERROR is on a task an open PR holds right now.
  Editing those blocks would break the one-owner rule and collide with the
  PRs.
- **OBSERVED:** none of the seven held PR branches adds its own missing
  fields. They clear only by landing `done`.
- **UNKNOWN:** whether all seven land `done`. Any that lands `blocked`
  keeps its ERROR until a later pass adds the fields.

## Conclusion

The board is down to zero ERROR lines on every task this cycle can own
(33 → 17; the 17 are on M1.4, M3.13, M3.29, M8.A8, M8.B6, M8.C, M8.E2, all
held by open PRs). That meets the lowered Done-when that H53's Stop allows
("no ERROR for tasks this cycle can own"). The rule and the checker are
unchanged. `todo_check --strict` exits 0 on `main` once those seven PRs
land `done`; a `blocked` landing has to bring its own fields (rule 14).
C-3650–C-3652.

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/todo_check.py --strict | grep -cE '^  ERROR'   # expected: 17 at this PR's head (only held tasks)
python3 tools/todo_check.py; echo $?                          # expected: 0
```

## Follow-ups

- [ ] The next PO/QA pass re-runs `todo_check --strict` after PRs #341, #351,
  #355, #370, #371, #372 and #379 merge. Any of those tasks that lands
  `blocked` without `Precheck`/`Scope`/`Stop` is fixed in place (rule 17,
  "a record defect is fixed where it is found").
