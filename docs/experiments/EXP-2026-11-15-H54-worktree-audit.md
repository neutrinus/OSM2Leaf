# EXP-2026-11-15-H54: `worktree_audit.py` lists stale trees and ahead-branches

- **Status:** done
- **Date:** 2026-11-15
- **Sample:** none (tool-only task) — no card or firmware bytes are read; the
  selftest builds a throwaway `git init` repository and the checkout audit only
  reads git metadata and `TODO.md`.
- **Tools:** `python3 3.15.0` (stdlib only), `git 2.56.0`;
  `tools/worktree_audit.py`, `tools/selftest.py`.
- **Claims:** C-3690, C-3691, C-3692, C-3693, C-3694, C-3695
- **Supersedes:** none
- **Superseded by:** none

## Question

Can one repository command classify every non-main worktree and every branch
ahead of `main` as live or stale, join each to its `TODO.md` task status, and
name the exact set a human may prune — without deleting a branch and without
touching a locked tree?

## Hypothesis

`git worktree list --porcelain` plus `git for-each-ref` plus the `TODO.md`
`Status:` lines are enough: a detached tree older than seven days whose commit
is an ancestor of `main` is a leftover, and a branch ahead of `main` for a task
already `done`/`blocked` is closed work that was never merged. **Falsifier:** a
tree/branch with no task ID in its name gets a guessed ID, a locked tree is
pruned, a branch is deleted, the `--prune` dry run deletes anything, or the
selftest cannot separate stale from active/locked/ahead-for-done without vendor
data.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none (git metadata of this checkout, `TODO.md`) |
| SHA-256 | n/a — no vendor data |
| Offset(s) / VA(s) | n/a |
| Tool / version | `python3 3.15.0`, `git 2.56.0` |
| Repo tool | `tools/worktree_audit.py` (new), `tools/selftest.py` |

## Method

1. **Sample and hash.** No vendor sample. The corpus is the git state of this
   checkout at `origin/main` = `eccace9` (2026-11-15) plus the synthetic
   fixture built by `--selftest`.
2. **Commands.**

   ```bash
   python3 tools/worktree_audit.py --selftest
   python3 tools/worktree_audit.py
   python3 tools/worktree_audit.py --json > /tmp/opencode/h54.json
   python3 tools/worktree_audit.py --prune
   git worktree list | wc -l
   git for-each-ref --format='%(refname:short)' refs/remotes/origin \
     | while read b; do n=$(git rev-list --count origin/main.."$b"); \
       [ "$n" -gt 0 ] && echo "$b ahead=$n"; done
   ```

3. **Controls.** *Positive*: `git worktree list` and the `rev-list` loop above
   are the independent oracle for the tree and ahead counts in Observations.
   *Negative*: in the selftest fixture, a recent detached tree must stay
   active, a locked old tree must stay `LOCKED` and be absent from
   `prune_commands`, a merged branch must not be listed at all, and `--prune`
   without `--apply` must leave the tree on disk.
4. **Scope.** This checkout only: every entry of `git worktree list
   --porcelain` except the tree that has `main` checked out (36 trees → 35
   rows) and every `refs/remotes/origin/*` branch not an ancestor of `main`
   and not listed as a worktree row (4 extra rows). Task statuses come from
   the whole of `TODO.md`; a task whose `Status:` line is absent is reported
   `UNKNOWN`, never inferred. Vendor data is not read.
5. **Falsifier.** See Hypothesis.

## Observations

Real checkout (`origin/main eccace9`, audit run from a separate worktree at
`task/h54-worktree-audit`):

```
$ git worktree list | wc -l
36                                       # 1 main + 35 non-main
counts worktrees=35 locked=2 ahead=7 stale=19 prunable=18
```

* 35 non-main worktrees, **2 locked** (both `claude agent ... (pid 16394)`),
  both reported `LOCKED` and excluded from the stale/prune set.
* **7 branches ahead of `main`** (independent `rev-list` loop lists the same 7:
  `chore/decomp-oracle-restore` 1, `claude/m5.12c-blocked` 1,
  `claude/todo-length-strategy` 1, `task/h54-worktree-audit` 1,
  `task/m1.25-fn-audit` 1, `task/m4.29-classcode-control` 1,
  `task/m5.29-factory-eu-rerun` 2). Four are not in a worktree row: three have
  task status `UNKNOWN`/`UNKNOWN`/`UNKNOWN` (no ID in the name:
  `chore/…`, `claude/…`), one is `M4.29`-`blocked` and is `STALE`.
* **19 `STALE` rows**: 15 detached worktrees (7.4–7.5 d old, commit an
  ancestor of `main`), 4 ahead rows whose task is `done`/`blocked`
  (`task/m4.29-classcode-control` branch, `task/m5.29-*` ×2, `task/m9.11-*`).
  One of the 19 (`M4.29`, a branch) is not prunable — branches are never
  deleted.
* `prune_commands` = the 18 stale, unlocked worktrees; the set equals the
  `STALE` worktree rows (`sorted(stale)==sorted(prune)` → `True`).
* `--prune` exit 0, printed 18 `git worktree remove -- PATH` lines, and
  `git worktree list | wc -l` was 36 before and after (deleted nothing).
* **27 of 39 rows are `UNKNOWN`**: 25 detached trees (no branch name) and 2
  named branches without a task ID. The tool reports them as `UNKNOWN`; it does
  not match their commit message against the board.
* Retro's 34 non-main trees / 5 ahead: this checkout now measures 35 / 7
  because two worktrees were added after the retro (`task/h54-…` and
  `task/m1.25-…`, both ahead of `main`), and the audit is counted in its own
  list. The difference is the measured drift, not a disagreement.

Selftest:

```
$ python3 tools/worktree_audit.py --selftest
ok   detached 10-day ancestor is STALE with UNKNOWN task
ok   recent detached tree is active
ok   locked tree is reported, never STALE
ok   tree ahead for a done task is STALE
ok   remote branch checked out in a worktree is not double-listed
ok   tree ahead for an open task is active
ok   remote branch ahead for a blocked task is STALE
ok   remote branch ahead for an in-progress task is active
ok   merged branch behind main is not listed
ok   counts: 5 trees (1 locked), 3 ahead, 3 stale, 2 prunable
ok   prune plan names only the unlocked stale trees
ok   --prune dry run prints commands and deletes nothing
ok   --prune --apply removes only the stale trees; locked/active stay
ok   no branch was deleted by --prune
worktree_audit selftest: OK (14 checks)
$ python3 tools/selftest.py --only worktree_audit
tool:worktree_audit  PASS
```

## Interpretation

- **FACT:** the tool reproduces the independent `git` oracle for the two
  counts it depends on (35 non-main trees, 2 locked, 7 ahead) and names 19
  stale rows, 18 of them prunable worktrees.
- **FACT:** `--prune` without `--apply` changed nothing (36 trees before and
  after) and its command set equals the `STALE` worktree rows.
- **OBSERVED:** most of the rot is detached trees with no branch (`UNKNOWN`):
  they cannot be attributed to a task from their name, so age + ancestor is the
  only safe signal the tool can use. Attaching a task ID when the tree is
  created would make the audit exact; the tool must not guess.
- **OBSERVED:** the 2026-11-15 retro's 34/5 drifted to 35/7 within the day;
  that drift is why a re-runnable command, not a retro number, is the oracle.
- **UNKNOWN:** no check yet proves that a tree is abandoned by its owner rather
  than paused; `STALE` is a candidate list for a human, not a deletion verdict.

## Conclusion

`tools/worktree_audit.py` (stdlib, `--selftest`, `--json`, `--prune` dry run,
`--prune --apply`) lists every non-main worktree and every branch ahead of
`main`, joins them to `TODO.md` statuses, flags detached ancestors older than
seven days and ahead branches for `done`/`blocked` tasks as `STALE`, and
prints only the unlocked stale worktrees as prune commands. It never deletes a
branch and never removes a locked tree. No format doc changes: this is a
repository-hygiene tool. Claims C-3690–C-3695 in
`docs/research/claims.md`. Follow-up (rule 9): task names/IDs are missing on
detached trees, so `UNKNOWN` dominates the stale set.

## Reproduction

```bash
python3 tools/worktree_audit.py --selftest        # expected: OK (14 checks)
python3 tools/worktree_audit.py                   # expected: counts worktrees=35 locked=2 ahead=7 stale=19 prunable=18
python3 tools/worktree_audit.py --prune           # expected: 18 `git worktree remove` lines, tree count unchanged
```
