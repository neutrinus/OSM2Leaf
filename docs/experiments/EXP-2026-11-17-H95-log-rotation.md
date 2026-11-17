# EXP-2026-11-17-H95: The H95 target `MAINTENANCE.md` does not exist

- **Status:** done (negative — premise false, task blocked)
- **Date:** 2026-11-17
- **Sample:** `none (docs-only)` — no image or vendor bytes are read; the
  question is about repository text, so all evidence is `git`/`grep`/`find`
  over the tracked tree.
- **Tools:** `git 2.56.0`, `grep` (GNU), `find` (GNU), `gh 2.97.0`,
  `python3 3.15.0`; repo tools `tools/todo_check.py`,
  `tools/claims_check.py`.
- **Claims:** C-4210 (the single factual claim of this record)
- **Supersedes:** none
- **Superseded by:** none

## Question

Does `MAINTENANCE.md` exist and contain a log-rotation rule that counts
`dev_process/` log files, so H95's Goal (rewrite it to `N = max+1`) is a
docs-only edit to an existing file?

## Hypothesis

H95's Precheck assumes `grep -n 'dev_process' MAINTENANCE.md` prints a
rotation instruction. The **falsifier**: the file is absent — the `grep` exits 2
with "No such file or directory" and no `MAINTENANCE.md` exists in any branch,
PR or reachable history — so there is no rotation rule to correct and the task's
premise, not its wording, is wrong.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none (docs-only) |
| SHA-256 | n/a — no byte sample; the check is over `git` object names |
| Repository | `neutrinus/OSM2Leaf`, base commit `e84340f` (H95 branch based on `origin/main`) |
| Tool / version | `git 2.56.0`, `gh 2.97.0`, `python3 3.15.0` |
| Repo tool | `tools/todo_check.py`, `tools/claims_check.py` |

## Method

A **spec**: the same four existence probes, each with a positive and a
negative control, plus the `-S` history probe that names what introduced the
reference.

1. **Sample and hash.** No byte sample applies (docs-only): the object under
   test is a *file name* in the repository, not an image. This is stated rather
   than omitted (TEMPLATE: a record with no sample must say why).

2. **Commands.** Run from the repository root at `79c3f82` (the H95 claim
   commit); `origin/main` was `e84340f`.

   ```bash
   # Q1 tracked file names matching "maintenance" (case-insensitive)
   git ls-files | grep -ci maintenance
   # Q2 any file on disk named MAINTENANCE* anywhere in the worktree
   find . -iname 'MAINTENANCE*' -not -path './.git/*' | wc -l
   # Q3 any path in the entire reachable history named *maint*
   git rev-list --all --objects | grep -ci maint
   # Q4 commits scanned by Q3
   git rev-list --all --count
   # Q5 origin heads whose tree contains MAINTENANCE.md
   for r in $(git for-each-ref refs/remotes/origin --format='%(refname)' | grep -v 'origin/HEAD'); do
     git ls-tree -r --name-only "$r" | grep -q '^MAINTENANCE\.md$' && echo "FOUND $r"
   done
   # Q6 open+closed PR count scanned for a MAINTENANCE.md diff
   gh pr list --state all --limit 1000 --json number -q 'length'
   # Q7 the exact text H95 quotes (where does it live?)
   git grep -In 'dev_process/ logs older than\|count dev_process' -- '*.md' '*.txt'
   # Q8 what introduced the string "MAINTENANCE.md"
   git log --all --oneline -S 'MAINTENANCE.md' -- TODO.md
   # Q9 the H95 Precheck exactly as the task writes it
   grep -n 'dev_process' MAINTENANCE.md
   ```

3. **Controls.**

   - **Positive (name probes see a real file):**
     `git ls-files | grep -ci '^README.md$'` prints `1`;
     `find . -maxdepth 1 -name 'README.md' -not -path './.git/*' | wc -l` prints
     `1`; the Q5 loop over the same 12 origin heads finds `README.md` in all
     `12`. So Q1/Q2/Q3/Q5 are capable of returning non-zero for a file that
     exists.
   - **Positive (the phrase search works):**
     `grep -n 'max+1' prompt_common.txt` prints line `82 — the free `N` is
     `max+1`, not a count …`, so a text search over a present file does find its
     subject.
   - **Negative (a truly absent name returns the same 0):**
     `find . -maxdepth 1 -iname 'NO_SUCH_FILE*' -not -path './.git/*' | wc -l`
     prints `0` and `git ls-files | grep -ci 'NO_SUCH_FILE'` prints `0`, matching
     the Q1–Q3 result for `MAINTENANCE.md`. The 0 is the signature of absence,
     not a broken probe, because the positive controls above print non-zero.

4. **Scope.** The whole tracked tree (`git ls-files`), the whole worktree
   (`find`), all `874` reachable commits (`git rev-list --all --count`) and
   their objects, all `12` origin heads, and all `212` PRs. Excluded: nothing
   relevant — a repository file is either tracked, in an origin head, or in a
   PR diff; the three domains cover every way a file could reach `main`.
   Worktrees under `.claude/worktrees/` are not part of the tracked repo and
   were not counted as evidence.

5. **Falsifier.** If any one of Q1–Q6 returned non-zero (a tracked file, an
   object in history, an origin head, or a PR diff carrying `MAINTENANCE.md`),
   the premise would hold and the correction would be a real edit. Stated before
   the result.

## Observations

```
Q1  git ls-files | grep -ci maintenance              -> 0
Q2  find . -iname 'MAINTENANCE*' | wc -l             -> 0
Q3  git rev-list --all --objects | grep -ci maint    -> 0
Q4  git rev-list --all --count                       -> 874
Q5  origin heads containing MAINTENANCE.md           -> 0   (12 heads scanned)
Q6  all PRs scanned                                  -> 212
Q7  quoted text `dev_process/ logs older than`       -> only TODO.md:939 (H95's own Note)
Q8  git log -S 'MAINTENANCE.md' -- TODO.md           -> fdba381 (SE cycle-12 review)
Q9  grep -n 'dev_process' MAINTENANCE.md             -> exit 2, "No such file or directory"

POS  git ls-files | grep -ci '^README.md$'           -> 1
POS  find . -maxdepth 1 -name README.md | wc -l      -> 1
POS  origin heads containing README.md               -> 12
POS  grep -n 'max+1' prompt_common.txt               -> line 82
NEG  find . -maxdepth 1 -iname 'NO_SUCH_FILE*' | wc -l -> 0
NEG  git ls-files | grep -ci 'NO_SUCH_FILE'          -> 0
```

`git show --name-only fdba381` lists only `TODO.md` and
`dev_process/2026-11-17-1125-44-se.log`, so the commit that first contains the
string `MAINTENANCE.md` adds it to `TODO.md` as prose — it does not add the
file. `git grep -Il 'MAINTENANCE'` finds the string in exactly one tracked file
outside `TODO.md`, the SE log line 54 that queued H95.

The prompts contain no log-rotation rule either: `grep -niE
'rotat|archive.*log|log.*archive|logs older|N days' prompt_sm.txt
prompt_common.txt` exits 1 (no match); `prompt_common.txt` §Work log defines
`N` (`max+1`, line 82) but says nothing about archiving or counting logs, and
`prompt_sm.txt` does not mention rotation.

## Interpretation

- **FACT:** `MAINTENANCE.md` does not exist — it is in no commit's tree, no
  origin head, no PR, and not on disk (Q1–Q6 all `0` against positive controls
  that print `1`/`12`). The H95 article "`MAINTENANCE.md` tells the SM to
  'count dev_process/ logs older than N days and archive'" describes a file that
  was never committed.
- **FACT:** No prompt encodes a log-rotation/archive rule (the prompt grep
  exits 1), so H95's Stop clause ("if the rotation rule is also encoded in a
  prompt, stop and hand the prompt half to the SM retro") does **not** fire —
  there is no prompt half to hand over either.
- **OBSERVED:** The reference originated in the SE cycle-12 review `fdba381`,
  which wrote the H95 Note; the same commit added only `TODO.md` and the SE
  log. The `max+1` naming that H95 wants the rule to "match" is real and lives
  in `prompt_common.txt:82`.
- **HYPOTHESIS:** The SE authored H95 against a planned or remembered
  `MAINTENANCE.md` that never landed, so the "count vs `max+1`" disagreement is
  about a document that does not exist. This is why the SE-vs-reality gap
  persisted: `claims_check` validates claim text, not whether a task's named
  input file exists.
- **UNKNOWN:** Whether a `MAINTENANCE.md` *should* exist (a lifecycle/archiving
  page the repo lacks) is a process decision, not something this task can
  establish from the data. Creating one is out of H95's Scope ("`MAINTENANCE.md`
  only" presumes it exists; H95 explicitly forbids prompt edits and does not
  author a new file).

## Conclusion

H95's Done-when cannot be met because its input does not exist: `grep -n
'dev_process' MAINTENANCE.md` exits 2, and a controlled search of the tracked
tree, the whole worktree, all `874` commits, all `12` origin heads and all
`212` PRs finds no `MAINTENANCE.md` and no log-rotation rule in any prompt.
The honest result is `Status: blocked`, not `done`: writing a new
`MAINTENANCE.md` (or inventing a rotation rule) would fabricate the very text
the task says to correct and would exceed H95's Scope. No `MAINTENANCE.md` edit
was made; no prompt was edited. The one factual claim (the file's absence and
the rule's absence from prompts) is registered as C-4210; the follow-up that
decides whether a maintenance/lifecycle page should exist is an SM decision,
not a task this branch can author.

## Reproduction

```bash
# expect every number to match the Observations block
git ls-files | grep -ci maintenance                 # 0
git rev-list --all --objects | grep -ci maint       # 0
git rev-list --all --count                          # 874
for r in $(git for-each-ref refs/remotes/origin --format='%(refname)' | grep -v 'origin/HEAD'); do \
  git ls-tree -r --name-only "$r" | grep -q '^MAINTENANCE\.md$' && echo "FOUND $r"; done   # nothing
grep -n 'dev_process' MAINTENANCE.md                # exit 2, no such file
grep -n 'max+1' prompt_common.txt                   # line 82 exists
git log --all --oneline -S 'MAINTENANCE.md' -- TODO.md   # fdba381 only
```

## Corrections after navigator review

solo run — no navigator (H95 is `Pair: solo`).

## Follow-ups

- [ ] **SM decision (`<human>`/SM retro)** — decide whether the repo needs a
  `MAINTENANCE.md` lifecycle page that states `N = max+1` and that a gap in a
  day's log numbering is normal. H95 cannot author it (its Scope says
  "`MAINTENANCE.md` only", and prompts stay with the SM); if the SM creates
  such a page and it needs the correction, H95 can be re-opened. No task ID is
  reserved for this because it is a process decision, not new research.
