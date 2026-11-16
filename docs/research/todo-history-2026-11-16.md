# TODO history — 2026-11-16 (PO grooming archive)

Done tasks moved from `TODO.md` on 2026-11-16: `Status: done`, block no
open/in-progress/blocked task's `Depends:` or `Unblock:` (fixpoint over the
whole live board), and completed on `origin/main` more than 24 h ago (commit
dates on `origin/main` are the authority). Earlier archives:
`todo-history-2026-11-05.md`, `-06.md`, `-09.md`, `-13.md`, `-15.md`.

All other 41 done blocks stay on the board: a live `Depends:`/`Unblock:` names
each of them. M7.4 is a pointer-only stub from the 3rd pass; H54 shipped
`tools/worktree_audit.py` on 2026-11-15 21:55 (+0100).

## H

- [x] **H54 — `worktree_audit.py`: a command that lists stale `.claude/worktrees` and ahead-branches before they rot**
  - Status: done · Owner: task/h54-worktree-audit · Critical: no · Pair: solo
  - Depends: —
  - Goal: 34 detached `.claude/worktrees` (2 locked) and 5 branches ahead of `main` have been unchanged across two retros (2026-11-13, 2026-11-15); every agent that runs `git worktree list` pays for it and nobody can tell a live tree from a 2026-11-08 leftover. Make the audit a reproducible command so the human cleanup (retro action 4) is cheap and re-checkable.
  - Precheck: `git worktree list | wc -l` and `git branch -r` show the counts in the 2026-11-15 retro; `python3 tools/worktree_audit.py --help` exits 2 (tool absent).
  - Scope: new `tools/worktree_audit.py` (`--selftest`, stdlib only): parse `git worktree list --porcelain` and `git for-each-ref`; for each non-main worktree/branch report `path · branch|detached · commit · age · locked · task ID from the branch name · task status in TODO.md`; flag `STALE` when the tree is detached, older than 7 days and its commit is an ancestor of `main`, or when the branch is ahead of `main` for a task already `done`/`blocked`; `--prune` (optional, dry-run by default) removes only `STALE` unlocked trees and prints the commands it would run. It never deletes a branch or force-removes a locked tree.
  - Input: `git worktree list --porcelain`, `git for-each-ref --format`, `TODO.md` status lines (reuse `todo_check.parse` if it exposes one, else a small regex), the 2026-11-15 retro numbers.
  - Hints: two trees are `locked` — report them and skip; `.claude/` is outside the repo's history, so the tool is read-only except for its explicit `--prune`. Test with a temp repo (`selftest` builds one with `git init` plus a fake detached tree) so the check runs in CI with no vendor data.
  - Done when: the tool reproduces the retro's counts (34 trees, 5 ahead) on this checkout; `--prune` dry-run names the same stale set and deletes nothing; selftest covers stale/active/locked/ahead-for-done; wired into `tools/selftest.py`.
  - Stop: if a tree's task cannot be inferred from the branch name, list it as `UNKNOWN` rather than guessing.
  - Claims: C-3690–C-3699
  - Result: EXP-2026-11-15-H54-worktree-audit; `tools/worktree_audit.py` reports 35 non-main worktrees (2 locked), 7 ahead branches, 19 STALE / 18 prunable on `eccace9`; `--prune` is a 18-command dry run that deletes nothing; selftest 14 checks. Claims C-3690–C-3695.

## M7

- [x] **M7.4** (archived 2026-11-09, 3rd pass) — profiles schema v2/writer. See `docs/research/todo-history-2026-11-09.md` (M7).
  - Status: done · Owner: — · Critical: no
  - Result: EXP-2026-11-06-M7.4-profiles-v2, C-1210 (archived 2026-11-09).
  - Claims: C-1210–C-1219
