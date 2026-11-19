# EXP-2026-11-19-H65: `progress_report` resolves an archived L4 prerequisite (M8.A1)

- **Status:** done
- **Date:** 2026-11-19
- **Sample:** none (tool-only task; inputs are repo files `TODO.md`,
  `docs/research/todo-history-2026-11-*.md` (9 files),
  `docs/research/reader-coverage.md`, `docs/research/claims.md`; no vendor data)
- **Tools:** `python3 3.13.18`; repo tools `tools/progress_report.py` (this
  change), `tools/selftest.py`
- **Claims:** C-3850–C-3853
- **Supersedes:** none
- **Superseded by:** none

## Question

Why does every default `progress_report.py` run print
`task M8.A1 not found`, and can the dashboard tell an archived prerequisite
from a broken board without putting M8.A1 back on `TODO.md`?

## Hypothesis

`L4_PREREQ` names `M8.A1`, whose block left `TODO.md` when it was archived;
`M8.A2` now reads `Depends: — (M8.A1, M8.A4 and M8.A5 are merged)`. If
`parse_todo_tasks` looks an absent ID up in the frozen board snapshots
(`docs/research/todo-history-*.md`, newest first), M8.A1 resolves as a done
`[x]` block and the problem disappears. **Falsifier:** no history file holds a
`- [x] **M8.A1` block (then the right fix is a live stand-in, not `archived`),
or the change also silences an ID that exists nowhere.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none (repo text files only) |
| SHA-256 | n/a (tool-only) |
| Offset(s) / VA(s) | none |
| Tool / version | `python3 3.13.18` |
| Repo tool | `tools/progress_report.py` (`parse_todo_tasks`, `find_archived_task`, `default_history_paths`) |

## Method

1. **Sample.** The board at the branch base (`origin/main` after the H62
   merge, `8e3b99f`) and its 9 history files.
2. **Commands.**

   ```bash
   grep -c '\*\*M8.A1' TODO.md
   grep -n '\*\*M8.A1' docs/research/todo-history-2026-11-05.md docs/research/todo-history-2026-11-09.md
   git stash && python3 tools/progress_report.py | grep -n 'M8.A1'; git stash pop
   python3 tools/progress_report.py | grep -n 'M8.A1\|not found'
   mkdir -p /home/user/scratch/h65 && cp TODO.md /home/user/scratch/h65/TODO.md
   python3 tools/progress_report.py --json /home/user/scratch/h65/r.json --md /home/user/scratch/h65/r.md
   python3 tools/progress_report.py --todo /home/user/scratch/h65/TODO.md | grep -n 'M8.A1'
   python3 tools/progress_report.py --selftest
   python3 tools/selftest.py --only progress_report
   ```

   (`git stash` is only the before-measurement on an uncommitted change; on
   `main` after the merge, `git show 8e3b99f:tools/progress_report.py >
   /home/user/scratch/h65/old_pr.py` reproduces it.)
3. **Controls.** *Positive:* the live board must read
   `prereq M8.A1: checked=True · archived (done) in todo-history-2026-11-09.md:1375`
   with zero problems; a synthetic `[x]` block in a history file resolves.
   *Negative:* the same `TODO.md` copied to a directory with no history files
   must still print `task M8.A1 not found (no block in TODO.md or 0 history
   files)`; a synthetic ID in no file stays `not found`; a synthetic block
   archived as `[ ]` is reported as `archived unfinished`.
4. **Scope.** 9 history files, 1 board; 9 task IDs parsed by the dashboard
   (stages `M6.2`, `M6.5`, `M6.6`, `M6.7`, `M8.A2`, `M8.B5`, `M8.E4`;
   prerequisites `M5.13b`, `M8.A1`); 8 resolve on the board, 1 from history. Only `tools/progress_report.py` changes;
   no M8 block and no layer verdict is edited.
5. **Falsifier.** As under Hypothesis, stated before the result.

## Observations

- `grep -c '\*\*M8.A1' TODO.md` → `1`, but the hit is the H65 block's own
  Precheck text (line 829), not a `- [ ] **M8.A1` header; no task block.
- History: `todo-history-2026-11-05.md:299` has `- [ ] **M8.A1 Build env.**`;
  `todo-history-2026-11-09.md:1375` has `- [x] **M8.A1 — Build env**` with
  inline `Status: done · Owner: session-ZMxuBT`.
- Before: report exit 0, problems section line 9
  `TODO.md: task M8.A1 not found`, line 23 `prereq M8.A1: checked=None · None`.
- After: report exit 0, no problems section; line 20
  `prereq M8.A1: checked=True · archived (done) in todo-history-2026-11-09.md:1375`.
  `--json`: `l4_emulator.prerequisites = [{task: M8.A1, checked: true,
  status: "archived (done) in todo-history-2026-11-09.md:1375"}]`,
  `problems: []`.
- Negative (board copy with no history next to it): `task M8.A1 not found (no
  block in TODO.md or 0 history files)`, `checked=None · None`.
- `--selftest`: 10 new checks (3 on the live report incl. the `--json` L4
  block, 7 on a synthetic board + two history files: newest file wins
  `[x]` over `[ ]`, archived-done is no problem, archived-unfinished is a
  problem, unknown ID is `not found … 2 history files`, no-history keeps the
  old behaviour, unresolved prereq stays `checked=None`); `progress_report
  selftest: OK`; `selftest.py --only progress_report`: `passed=1 failed=0`.

## Interpretation

- **FACT:** the problem line was a missing-block lookup, not a broken board:
  M8.A1 is done and archived in the 2026-11-09 snapshot.
- **OBSERVED:** the newer snapshot must win; the 2026-11-05 snapshot still
  shows M8.A1 open, so a first-match search in date order would have reported
  it unfinished.
- **HYPOTHESIS:** H60's general live/archived/ghost classifier can replace
  `find_archived_task`; until then this lookup is the dashboard's only one.

## Conclusion

`progress_report.py` now resolves a prerequisite ID that has no block on the
board from `docs/research/todo-history-*.md` (newest first) and prints it as
`archived (…) in <file>:<line>`; IDs found nowhere, or archived unfinished,
remain problems. Default run: exit 0, zero problems. Claims C-3850–C-3853.

## Reproduction

```bash
python3 tools/progress_report.py | grep -n 'M8.A1'   # expected: prereq `M8.A1`: checked=True · archived (done) in todo-history-2026-11-09.md:1375
python3 tools/progress_report.py --selftest          # expected: progress_report selftest: OK
```

## Follow-ups

- none new; H60 owns the general classifier.
