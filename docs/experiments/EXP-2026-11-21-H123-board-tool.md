# EXP-2026-11-21-H123: `tools/board.py` — board edits as guarded splices

- **Status:** done
- **Date:** 2026-11-21
- **Sample:** none (tool-only task). Inputs are this repository's own
  `TODO.md` and `docs/research/claims.md` at commits `4900961`, `6ca7bc3`
  (PR #340) and `c4b5a90` (`origin/main` when the task started).
- **Tools:** `python3 3.13.18`, `git`; repo tools `tools/board.py`,
  `tools/fixtures/h123-board-conflict-replay.sh`, `tools/claims_check.py`,
  `tools/todo_check.py`
- **Claims:** C-6580–C-6584
- **Supersedes:** none
- **Superseded by:** none

## Question

Can every routine change to `TODO.md` and `claims.md` (claim, close, block,
set a field, add a task, add claim rows, archive, resolve a conflict) be made
by a script that edits only its own lines and refuses to drop an ID, so that
no agent has to rewrite the files (Marek, 2026-11-21)?

## Hypothesis

Yes: both files have a line grammar the checkers already parse (`TASK_RE`,
`FIELD_RE`, `ROW_RE`), so each operation is a splice of one task block or one
table, and a conflict can be merged per task ID / claim ID instead of per
line. **Falsifier:** an operation that changes a line outside its splice, a
`resolve` that drops an ID present on either side, or the guard accepting the
PR #340 tail cut.

## Method

1. **Sample and hash.** Git objects named above; no vendor data.
2. **Commands.**

   ```bash
   python3 tools/board.py --selftest
   python3 tools/board.py lost --base 4900961 --head 6ca7bc3
   python3 tools/board.py lost --base origin/main
   tools/fixtures/h123-board-conflict-replay.sh
   python3 tools/selftest.py --only board
   python3 tools/todo_check.py && python3 tools/claims_check.py
   ```

3. **Controls.** *Positive:* `lost` on PR #340's commit must name the lost
   tasks and claim rows; the replay's `resolve` must keep both branches' new
   task and claim row. *Negative:* the guard is fed a dropped task header, a
   dropped claim row, a wrong line delta, a change to a neighbouring block and
   a file changed on disk between read and write (selftest, each must be
   refused); in the replay, `lost --base replay-b --head replay-a` ("take our
   side") must report the other branch's task and row as lost.
4. **Scope.** The two board files and `docs/research/todo-history-*.md`
   (`next-id`, `archive`). Prose sections (rules, Priorities) are still edited
   by hand; the guard still checks IDs on those edits only when they go
   through the tool. H121 (the CI check against the merge base, with
   exemptions) is not done here; it reuses `lost_ids`.
5. **Falsifier.** As in Hypothesis.

## Observations

- `board.py --selftest`: `board selftest: OK (58 checks)`; covers claim,
  release, status, done, block, field (replace / append), add-task (stream end,
  duplicate ID, overlapping claim block, two blocks), archive (open task
  refused, done task moved, history file created), next-id, next-claims,
  add-claims (existing section, `--create`, duplicate ID, short row),
  claim-status with an escaped `\|`, the five guard refusals, `lost_ids`,
  `merge3` (both appends kept, one-sided edit taken, two-sided edit marked,
  claims row + new section), `resolve` CLI, `merge3` identity on the real
  `TODO.md` and `claims.md`, and `TASK_RE`/`FIELD_RE`/`ROW_RE` equal to the
  checkers' patterns.
- `lost --base 4900961 --head 6ca7bc3`: `TODO.md: LOST tasks=42 claims=0`
  (M1.33 and 41 `M9.*` headers) and `docs/research/claims.md: LOST tasks=0
  claims=199` (31 ranges, `(199 rows)`); exit 1.
- `lost --base origin/main` on this branch: both files `OK`, exit 0.
- Replay (`tools/fixtures/h123-board-conflict-replay.sh`, base `c4b5a90`):
  branch A adds M9.63, C-3205 and claims H122; branch B adds M9.64, C-3206,
  claims H121 and closes H122. Before merging, `lost --base replay-b --head
  replay-a` prints `tasks: M9.64` and `claims: C-3206 (1 rows)`, exit 1.
  `git merge` conflicts in both files (`TODO.md:2`, `claims.md:1` marker
  blocks). `resolve docs/research/claims.md` exits 0 with both rows;
  `resolve TODO.md` exits 1 naming `T H122` (changed on both sides) and leaves
  one marker block; M9.63 and M9.64 are both present, H121 carries
  `Owner: B`. Afterwards `lost --base replay-a` and `lost --base replay-b`
  both exit 0; `claims_check: OK`.

## Interpretation

The hypothesis holds: all routine board edits are splices, and the guard
catches the PR #340 shape. `resolve` turns the conflict that PR #340 resolved
by pasting an old copy into a by-ID merge where only a genuinely two-sided
edit needs a human, and it never drops either side's IDs. H121's title counts
7 lost tasks (the new blocks M9.56–M9.62); by header the cut removed 42
blocks, most of which came back as older copies. The difference is in what is
counted, not a contradiction.

## Next

H121 builds the CI check on `board.lost_ids` (its Input now says so). The
role prompts, AGENTS.md and TODO rules 3, 5, 6 and 9 name `board.py` as the
way to edit the board.
