# EXP-2026-11-21-H121: a PR cannot drop claim rows or task blocks it does not own

- **Status:** done
- **Date:** 2026-11-21
- **Sample:** `none (tool-only task)`; the board `TODO.md` and ledger
  `docs/research/claims.md` at `6ca7bc3` (the PR #340 loss), its base
  `4900961`, and the 50 merges at the head of `origin/main` at `ace1223b`.
- **Tools:** python3 3.11.17 / git 2.47; `tools/board.py`, `tools/gate.py`,
  `tools/selftest.py`, `tools/claims_check.py`, `tools/todo_check.py`
- **Claims:** C-6520–C-6529
- **Supersedes:** none
- **Superseded by:** none
- **Corrections after navigator review:** four defects in round 1 (PR #431),
  all fixed before merge — see "Corrections after navigator review" below:
  a raw-substring exemption, a selftest that could not see it, two claim rows
  quoting hashes their commands do not print, and this section itself.

## Question

Can the standing gate fail a pull request that drops claim rows or task blocks
it does not own — the PR #340 shape, where `6ca7bc3` replaced the tail of
`TODO.md` (42 task blocks) and of `docs/research/claims.md` (199 rows) with an
older copy while `todo_check` and `claims_check` both stayed green because each
judges only the file it is given?

## Hypothesis

Yes: diff the tree against the commit the PR branches from, list the IDs that
shipped in the base and not in the PR, and fail unless each lost ID is (a)
named in a task block the PR itself touched (a restore names what it restored),
(b) a task whose block is in a `docs/research/todo-history-*.md` file (an
archive move), or (c) a bare `RESERVED (…)` claim row (H100 retires the
owner's placeholders). **Falsifier:** a legitimate PR of the last 50 merged
that the check would fail (then the exemption is too narrow and must be
widened, and which one named).

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `none` (board text only; no vendor bytes) |
| SHA-256 | `none (tool-only task)` |
| Offset(s) / VA(s) | — (git commits `6ca7bc3`, `4900961`, `119a74e7`, `0d4916ab`, `73ff0da6`) |
| Tool / version | python3 3.11.17, git 2.47 |
| Repo tool | `tools/board.py` (`check`, `lost_ids`), `tools/gate.py` (the `board_check` row) |

## Method

1. **Sample and hash.** No file sample; the corpus is the two board files at
   named commits. `git show <rev>:TODO.md` and
   `git show <rev>:docs/research/claims.md` are the bytes the check reads.

2. **Commands.** Runnable as written from the repo root:

   ```bash
   # the reproducer: PR #340's own commit against the base it branched from (4900961)
   python3 tools/board.py check 6ca7bc3 ; echo "exit=$?"

   # the control: main and this branch are clean against their base
   python3 tools/board.py check origin/main ; echo "exit=$?"
   python3 tools/board.py check HEAD ; echo "exit=$?"

   # the falsifier: would any of the last 50 first-parent merges have failed?
   python3 tools/board.py --selftest          # the synthetic controls below
   python3 tools/gate.py --selftest           # the board row and its FAIL tail
   python3 tools/gate.py                      # the whole standing gate
   ```

   The per-merge falsifier evaluation is a counted loop; it is reproduced with
   the committed API rather than a throwaway script:

   ```bash
   python3 - <<'PY'
   import sys, subprocess
   sys.path.insert(0, "tools"); import board
   merges = [l.split()[0] for l in board.git_cmd(
       ["log", "--first-parent", "--merges", "--format=%H %s", "-60",
        "origin/main"]).stdout.splitlines()][:50]
   lost = fail = 0
   for sha in merges:
       p = board.git_cmd(["rev-list", "--parents", "-1", sha]).stdout.split()[1]
       bt = board.git_cmd(["show", p + ":TODO.md"]).stdout
       ht = board.git_cmd(["show", sha + ":TODO.md"]).stdout
       bc = board.git_cmd(["show", p + ":docs/research/claims.md"]).stdout
       hc = board.git_cmd(["show", sha + ":docs/research/claims.md"]).stdout
       v = board.board_loss_problems(bt, ht, bc, hc, board._history_texts(sha))
       lost += bool(v["tasks"] or v["claims"])
       if v["errors"]:
           fail += 1
   print("merges:", len(merges), "with any lost ID:", lost,
         "the check would fail:", fail)
   PY
   ```

3. **Controls.**
   - **Positive:** `6ca7bc3` against `4900961` — the shape the task names —
     must exit 1 and name the lost task IDs and the count of lost claim rows.
   - **Negative (a real 3-way merge that keeps what is not its own):**
     `0d4916ab` (PR #417) removed M9.29/M9.30 from `TODO.md` while they sat in
     `docs/research/todo-history-2026-11-20.md`; the check exits 0 with both
     exempt as archived.
   - **Negative (a retirement, not a loss):** `73ff0da6` (PR #338, H100)
     removed 317 `RESERVED (…)` claim rows; all 317 are exempt and the check
     exits 0.
   - **Negative (synthetic, `board.py --selftest`):** an unchanged board is
     clean; a deleted row fails; a deleted block fails; the same archive passes
     only *with* a history file; a dropped `RESERVED` row is exempt and a
     dropped `VERIFIED` row is not; a lost ID named in the PR's own block is
     exempt; a claim row the PR's own block renumbers is exempt.
   - **Negative (the gate's FAIL path, `gate.py --selftest`):** a synthetic
     git repo where the head drops `C-701` turns the `board_check` row `FAIL`
     and the FAIL tail names `C-701`.

4. **Scope.** The two board files (`TODO.md`, `docs/research/claims.md`) at a
   named ref and at one base; every task header (`TASK_RE`) and every claim
   row (`ROW_RE`), measured on the full 50-merge window `ace1223b..origin/main`
   head. Not covered: claim rows inside EXP prose, `README` links, or a file a
   PR deletes whole (the check reports "no FILE at ref" and exits 0, the same
   as a root commit — a whole-file delete is `todo_check`'s/`claims_check`'s
   failure, not this row's). CI runs it on the full `fetch-depth: 0` checkout
   plus a depth-200 `origin/main` fetch.

5. **Falsifier.** Stated above: any of the last 50 merged PRs that the check
   would fail. Measured before the result below.

## Observations

- `python3 tools/board.py check 6ca7bc3` prints
  `board check: 6ca7bc3 vs base 49009617d2bc: 42 task(s) and 199 claim row(s) lost, 5 exempt, 236 problem(s)`
  and exits 1; the named tasks are `M1.33` and 41 `M9.*` headers (`M9.11` …
  `M9.62`), the claim count is 199 rows.
- `python3 tools/board.py check origin/main` prints
  `board check: origin/main vs base 091a48880733: 0 task(s) and 0 claim row(s) lost, 0 exempt, 0 problem(s)`
  and exits 0; `check HEAD` on the final tree (`366da513`) prints
  `board check: HEAD vs base 7b43d68bc57e: 0 task(s) and 0 claim row(s) lost, 0 exempt, 0 problem(s)`
  and exits 0. Both bases are the hashes those commands print on this branch
  (`7b43d68b` is the `origin/main` tip it was rebased onto); they move as
  `main` moves, so the revision in the command is the stable part.
- `python3 tools/board.py check 0d4916ab` prints
  `board check: 0d4916ab vs base 39600b6cd9ac: 2 task(s) and 0 claim row(s) lost, 2 exempt, 0 problem(s)`,
  both exempt as archived, exit 0.
- `python3 tools/board.py check 73ff0da6` prints
  `board check: 73ff0da6 vs base 4cc97412749b: 0 task(s) and 317 claim row(s) lost, 317 exempt, 0 problem(s)`,
  exit 0.
- `python3 tools/board.py check 119a74e7` (the PR #340 merge itself, first
  parent `a6009fe9`) prints
  `board check: 119a74e7 vs base a6009fe921cc: 7 task(s) and 199 claim row(s) lost, 30 exempt, 176 problem(s)`
  and exits 1.
- Falsifier loop over the 50 first-parent merges at the `origin/main` head:
  `merges: 50 with any lost ID: 3 the check would fail: 1`. The three with any
  lost ID are `119a74e7` (the PR #340 merge, 206 IDs), `0d4916ab` (PR #417, 2
  archived tasks) and `73ff0da6` (PR #338, 317 `RESERVED` retirements). Only
  `119a74e7` fails.
- `python3 tools/board.py --selftest` prints `board selftest: OK (74 checks)`
  (58 before this task, 16 added: the eight `board_loss_problems` cases, the
  three whole-ID collision cases from navigator round 1, the two
  `segment_base` cases and the three `check_ref` cases in a synthetic repo).
- `python3 tools/gate.py --selftest` prints `gate selftest: OK (15 checks, 0 failed)`
  (11 before, 4 added: the `board_check` row is present, it can be turned off,
  `check HEAD` on this tree is PASS, and a dropped row turns it FAIL).
- `python3 tools/gate.py` on this branch with `archive/` symlinked prints
  `gate: 5 pass, 0 fail, 0 skip` and exits 0, with `TMPDIR` on disk scratch
  (`TMPDIR=/tmp/opencode`): `selftest PASS 121.60 s`, `claims_check PASS`,
  `todo_check PASS`, `board_check PASS 0.16 s`, `fn_audit PASS` (not SKIP).
  With the default `/tmp` (3.8 GiB tmpfs, 99 % full) the same run fails only
  `selftest` on three disk-heavy suites (`imgpatch`, `lev3456gen`, `mkcard`,
  each passing on its own with `TMPDIR` moved), the AGENTS `/tmp` constraint,
  not this change.
- CI clone timing: `git clone --depth 200` of the branch is 1146 commits;
  `git fetch --no-tags --depth=200 origin '+refs/heads/main:refs/remotes/origin/main'`
  then reports `5.860 s` in a clean `--depth 1` clone of the branch;
  `git rev-parse --is-shallow-repository` prints `true` and `check HEAD` still
  exits 0 with base `a0bf0d9815a3` (the merge base is in the window; that run
  was before the final rebase, whose tree prints base `7b43d68bc57e` above).
  A local refetch of an already-present `origin/main` takes `0.854 s`; the four
  historical verdicts were re-read on the final rebase (`origin/main` at
  `7b43d68b`) and are unchanged.
- The four historical checks run unchanged in that shallow clone: `6ca7bc3`
  exit 1, `119a74e7` exit 1, `0d4916ab` exit 0, `73ff0da6` exit 0.
- **Live CI (the oracle for the base path):** PR #431's `quality` job on run
  `44887804569` (py3.11, py3.13, py3.14) is all `pass`; that run's head is
  before the round-1 review fixes, but the fetched ref is the same
  `origin/main` path. The log prints
  `fetched origin/main in 207 ms (depth 200)` and
  `merge base with origin/main: 04872b503c1cc196eb6b79be6cb6a97b4bcc1a3f`,
  and the standing gate prints `board_check   PASS      0.16` and
  `gate: 5 pass, 0 fail, 0 skip`.

## Interpretation

- **FACT:** The check reproduces the task's Done-when: on `6ca7bc3` it exits 1
  and names 42 lost task IDs and 199 lost claim rows; on `main` and on this
  branch it exits 0; `--selftest` covers a deleted row, a deleted task block,
  an archived task and a dropped `RESERVED` row.
- **OBSERVED:** The exemption is not vacuous — it forgives two of the three
  real events in the window (an archive move and a retirement) and still fails
  the PR #340 merge. The falsifier found exactly one merge the check fails,
  and it is the loss the task is about (`119a74e7`, PR #340).
- **OBSERVED:** 30 IDs of the PR #340 merge are exempt that `6ca7bc3`'s own
  check does not exempt (236 problems vs 176). That is the restore PR's own
  naming: the merge commit `119a74e7` carries the restoration diff of PR #417,
  whose own task blocks name M9.56–M9.62, so the merge that *contains* the
  restore looks cleaner than the branch commit that made the loss. The
  branch-level shape (`6ca7bc3`) is the one the task's reproducer names and is
  the one that fails loudly.
- **FACT (live runner):** On GitHub's `pull_request` checkout the depth-200
  fetch puts `origin/main` in the window (207 ms) and the gate's `board_check`
  row PASSes against the merge base `04872b503c1c`; the local shallow-clone
  run predicted exactly this. `board.py check` falls back to the merge base
  with `origin/main` when the ref has one parent, and prints "no history to
  diff against" (exit 0) rather than guessing when it cannot see the base.
- **UNKNOWN:** Whether a PR that deletes `TODO.md` or `claims.md` whole should
  also fail this row; today the row says "no FILE at ref; nothing to judge" and
  exits 0, and the two checkers already fail a missing board.

## Conclusion

`tools/board.py` gained `board_loss_problems`, `segment_base`, `own_ids`,
`changed_task_blocks`, `history_ids`, `check_ref` and the `check [REF] [--base]`
command; `tools/gate.py` gained the `board_check` row between `todo_check` and
`fn_audit`; `.github/workflows/ci.yml` fetches `origin/main` at depth 200 in a
named "Board merge base (H121)" step and its summary names the new row. The
task's Done-when holds on the recorded inputs, the exemption is narrower than
the check's power (it fails PR #340 and passes both real archive/retirement
events), and `board.py --selftest` is `OK (74 checks)` with `gate.py --selftest`
`OK (15 checks, 0 failed)`, `gate: 5 pass, 0 fail, 0 skip`.

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/board.py check 6ca7bc3 ; echo "exit=$?"      # expect exit=1, 42 tasks / 199 claims
python3 tools/board.py check origin/main ; echo "exit=$?"  # expect exit=0
python3 tools/board.py --selftest                          # expect "board selftest: OK (74 checks)"
python3 tools/gate.py --selftest                           # expect "gate selftest: OK (15 checks, 0 failed)"
```

## Corrections after navigator review

Navigator round 1 (PR #431) returned four defects; all are fixed on this
branch (commit `366da513`, `tools/board.py` + this file, and the C-6521/C-6527
rows). The check's verdicts did not change: `6ca7bc3` still exits 1 with 42
tasks / 199 rows, `origin/main` and `HEAD` still exit 0.

1. *(blocking, silent false negative)* **The exemption was a raw substring
   test.** `board_loss_problems` had `elif t in own_text:`, so on this very
   branch a dropped `M9.5` was exempt as "named in the PR's own task block"
   because H121's own block names `M9.56–M9.62` and `M9.55` — exit 0,
   `errors []`. Fixed with `_names_id(text, tid)`, an exact whole-ID token:
   `(?<![A-Za-z0-9])<id>(?!\.[A-Za-z0-9])(?![A-Za-z0-9])`, so `M9.56`,
   `M9.55` and `M9.5.1` do not name `M9.5`, while `M9.5,`, `(M9.5)` and a
   sentence-ending `M9.5.` do. The navigator's repro on the real board now
   prints `tasks ['M9.5']`, `exempt {}`, `errors ['lost task M9.5 (not its
   own, not archived)']`.
2. *(blocking)* **The selftest could not see defect 1.** The old "named in the
   PR's own block" case used `H3` with no prefix collision, so `--selftest`
   stayed green with a substring match. Three cases added: a block that names
   `M9.56` while `M9.5` is dropped must FAIL, a positive control where it
   names `M9.5` must exempt, and `_names_id` token cases. The first fixture
   accidentally still kept `M9.5` in the head (so it passed for the wrong
   reason); it now drops it. `board.py --selftest` is `OK (74 checks)`
   (71 before).
3. *(blocking)* **C-6521/C-6527 quoted base hashes their cited commands do not
   print** (`67d9fcbc62ba`/`a0bf0d9815a3`, from an earlier rebase). Both rows
   now quote the hashes `check origin/main` and `check HEAD` print on this
   tree (`091a48880733` is what `check origin/main` prints; the branch merge
   base is `7b43d68bc57e`) and state the revision as the stable part. Edited
   through the new `board.py claim-row C-ID --text ROW` (a guarded one-line
   splice; it was added so claim edits no longer need a hand edit, the same
   reason every other board write is a `board.py` op) — both `+0 lines`.
4. *(blocking)* **This section was `pending`.** It is filled above; H90/H93
   require it filled or `none`.

The final ladder on `366da513` + these edits: `check 6ca7bc3` exit 1, `check
origin/main` exit 0, `check HEAD` exit 0, `board.py --selftest OK (74 checks)`,
`gate: 5 pass, 0 fail, 0 skip` (`board_check PASS`, `fn_audit PASS`, not
SKIP), `claims_check --strict --count-check` and `todo_check` PASS,
`board.py lost --base origin/main` exit 0.

## Follow-ups

- [x] A live GitHub Actions run on this PR confirmed the `pull_request` path:
  run `44887804569` fetches `origin/main` in `207 ms` (depth 200), merge base
  `04872b503c1c`, `board_check PASS`, all three `quality` jobs green.
- [ ] Decide whether a whole-file delete of `TODO.md`/`claims.md` should fail
  the `board_check` row (today it exits 0 and leaves it to the two checkers).
