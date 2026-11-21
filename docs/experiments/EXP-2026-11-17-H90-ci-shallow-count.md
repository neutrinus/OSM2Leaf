# EXP-2026-11-17-H90: CI red on `main` — a shallow checkout, not a bad ledger

- **Status:** done
- **Date:** 2026-11-17
- **Sample:** `none (CI/tool task)`; the git history of `origin/main` at
  `3d79bcc`. H94 measured it on 2026-11-21: `git rev-list --count 3d79bcc`
  prints `108` and `git count-objects -vH | grep size-pack` prints
  `size-pack: 19.74 MiB`. H90's original block quoted `809 commits, pack
  3.2 MiB` for the same SHA on its own tree; that number is H90's and is not
  re-typed here (H90's own measurement of `809` is pinned by C-4135).
- **Tools:** H94's own environment measured 2026-11-21: `git --version`
  prints `git version 2.56.0`, `python3 -V` prints `Python 3.15.0`; repo tools
  `tools/claims_check.py`, `tools/gate.py`, `.github/workflows/ci.yml`. H90's
  original block listed `git 2.5x, python3 3.15` as its own environment; that
  string is left quoted as H90's, not retyped as a measurement.
- **Claims:** C-4130–C-4139
- **Supersedes:** none
- **Superseded by:** none

## Question

`CI quality gate` has been red on `main` since H85 merged (PR #206) — 12
consecutive pushes, from `1889340` to `2b3d1b4`, the last success being
`3f9c0b2` (#205), in all three matrix jobs — while the same command is green
locally.
Is the ledger wrong (nine stale selftest counts to re-pin), or is CI running
the rule on a tree it cannot apply to?

## Hypothesis

`actions/checkout@v4` defaults to `fetch-depth: 1`. H78's `_exp_revision` finds
a claim's measurement revision with `git log --format=%H -- <EXP>` and takes
the newest commit that also changed a `tools/*.py`; in a one-commit clone that
is always the tip, so every claim is "pinned" to the tip and the *current*
tool count is compared with a count recorded at an older commit. **Falsifier:**
if a depth-1 clone of the same SHA is green, or if its COUNT lines name
revisions other than the tip, the history is not the cause.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `none (CI/tool task)` |
| SHA-256 | `none` |
| Repo state | `origin/main` = `2b3d1b4`, the 12th consecutive red push (`1889340`…`2b3d1b4`); the last green is `3f9c0b2` |
| Tool / version | `python3 -V` → `Python 3.15.0`, `git --version` → `git version 2.56.0` (H94's own measurement, 2026-11-21; H90's `3.15`/`2.5x` quoted as H90's environment) |
| Repo tools | `tools/claims_check.py`, `tools/gate.py`, `.github/workflows/ci.yml` |

## Method

1. **Sample.** The twelve `main` pushes whose `CI quality gate` run failed
   (1889340..2b3d1b4, last green 3f9c0b2), and a depth-1 clone of the same tree.
2. **Commands.**
   ```bash
   gh run list --workflow "CI quality gate" --branch main --limit 12 \
     --json createdAt,headSha,conclusion
   gh run view <id> --log-failed        # the nine COUNT lines
   X=$(mktemp -d); R=$PWD
   git clone --depth 1 file://$R "$X" && ( cd "$X" && \
     python3 tools/claims_check.py --strict --count-check; \
     git fetch -q --unshallow "$R" && \
     python3 tools/claims_check.py --strict --count-check )
   ```
3. **Controls.** *Positive*: a full checkout prints `count mismatches: 0`.
   *Negative 1*: in a full checkout, changing C-3704's `26` to `25` must still
   print `COUNT C-3704 claims 25, tools/fn_match.py prints 26 (334f092…)` and
   exit 1 — the rule must not be weakened. *Negative 2*: after the fix, a
   depth-1 clone must print the skip, and the same clone after `--unshallow`
   must print `0`.
4. **Scope.** `.github/workflows/ci.yml` (`fetch-depth: 0`) and
   `tools/claims_check.py`: a shallow-history probe, `_exp_revision` returns
   `None` there, and `main()` prints `count check: skipped (shallow clone …)`.
   No claim, EXP or gate-policy text changes.
5. **Falsifier.** Stated in the Hypothesis.

## Observations

CI, run `44045407959` on `3d79bcc` (py3.14 job; 3.11/3.13 identical; the
same nine lines appear at every red push, each with its own tip SHA):

```
claims_check  FAIL      3.46  exit 1
count mismatches: 9
  COUNT C-568 claims 46, tools/cerom.py prints 411 (3d79bccf3dd62c368eb8417e532a7d6d4b34bce2)
  COUNT C-570 claims 186, tools/cecompress.py prints 390 (3d79bccf…)
  COUNT C-650 claims 391, tools/cecompress.py prints 390 (3d79bccf…)
  COUNT C-3704 claims 26, tools/fn_match.py prints 33 (3d79bccf…)
  COUNT C-2085 claims 44, tools/hddinfo.py prints 62 (3d79bccf…)
  COUNT C-960 claims 15, tools/coord.py prints 19 (3d79bccf…)
  COUNT C-1060 claims 48, tools/tilewriter.py prints 68 (3d79bccf…)
  COUNT C-1994 claims 18, tools/coord.py prints 19 (3d79bccf…)
  COUNT C-3934 claims 58, tools/fn_audit.py prints 72 (3d79bccf…)
gate: 2 pass, 1 fail, 1 skip -- not covered: fn_audit (missing archive/head256.img)
```

Every `rev` is the tip: the fingerprint of a shallow history, not of nine
mis-typed numbers. The same tree, full history:

```
$ python3 tools/claims_check.py --strict --count-check | grep -E 'count mismatches|claims_check:'
count mismatches: 0
claims_check: OK
```

The tool's selftests print the same counts in both trees (`cerom 411`,
`cecompress 390`, `fn_match 33`, `hddinfo 62`, `coord 19`, `tilewriter 68`,
`fn_audit 72`), so the difference is the *revision*, not the tools.

After the fix, in a depth-1 clone of the same worktree:

```
$ git clone --depth 1 … && python3 tools/claims_check.py --strict --count-check
shallow=true commits=1
count check: skipped (shallow clone; fetch the full history to run it)
claims_check: OK
$ echo $?
0
$ git fetch --unshallow && python3 tools/claims_check.py --strict --count-check
count mismatches: 0
claims_check: OK
```

Negative control (full checkout, C-3704 `26`→`25`) still bites:

```
COUNT C-3704 claims 25, tools/fn_match.py prints 26 (334f0922653565e8ec15901a0ed6e64735d5346e)
claims_check: FAILED
```

Gate on a full checkout with the image after the fix: `selftest PASS`,
`claims_check PASS`, `todo_check PASS`, `fn_audit PASS`, `gate: 4 pass, 0
fail, 0 skip` (without the image the last row is a named SKIP, `3 pass, 1
skip`, never a pass);
`tools/selftest.py` `passed=91 failed=0 skipped=23 total=114`.

The tool's own selftest grows from 25 to 28 checks (three shallow-history
cases: `true`, `false`, and an unreadable answer treated as shallow), so the
one claim that quoted the old number, C-4015, is updated to `28 checks` in
the same commit (C-4137). It prints the same in a shallow and a full clone:

```
$ python3 tools/claims_check.py --selftest | tail -1
claims_check selftest: OK (28 checks)
```

## Interpretation

- **FACT:** CI was red for 12 consecutive `main` pushes, `1889340` (H85's
  merge) through `2b3d1b4`, and the nine `COUNT` lines all name that run's own
  tip revision. The cause was present at every one of them, not only at the
  first.
- **FACT:** a depth-1 clone of `3d79bcc` prints `count mismatches: 9`; the same
  commit with full history prints `0`. The ledger is correct; the checkout was
  not.
- **FACT:** the fix keeps the rule intact on a full checkout (the C-3704
  mutation still exits 1), and a shallow clone now says *skipped*, never
  "0 mismatches".
- **IMPLICATION:** H78's rule is only meaningful with history; CI must fetch it
  (`fetch-depth: 0`, ~3 MiB) and the tool must refuse to guess when it cannot.
- **LIMITATION:** the `--count-check` rule still does not run in any *other*
  shallow checkout (a developer's `--depth 1` clone); it prints a skip, so the
  number is not silently wrong, but it is not checked there either.

## Conclusion

The red CI was a shallow `actions/checkout`, not a bad ledger. CI now fetches
the full history (3.2 MiB) and `claims_check` treats a shallow history as "no
measurement revision exists" — the H78 skip rule it already had — printing
`count check: skipped (shallow clone …)` instead of nine false mismatches.

## Reproduction

```bash
# pinned to the PRE-fix tree 3d79bcc (navigator correction 2, H93); run from the repo root
R=$PWD; X=$(mktemp -d)
git init -q "$X" && git -C "$X" fetch -q --depth 1 "file://$R" 3d79bccf3dd62c368eb8417e532a7d6d4b34bce2
git -C "$X" checkout -q FETCH_HEAD && cd "$X"
python3 tools/claims_check.py --strict --count-check   # 9 COUNT lines, count mismatches: 9, exit 1
git fetch -q --unshallow "file://$R" 3d79bccf3dd62c368eb8417e532a7d6d4b34bce2
git rev-list --count HEAD                              # 809
python3 tools/claims_check.py --strict --count-check   # count mismatches: 0, exit 0
```

## Corrections after navigator review

Navigator round 1 (TL log `dev_process/2026-11-17-0859-42-tl.log`):
"APPROVE, with two non-blocking number flags (the red run is 12 consecutive
pushes 1889340..2b3d1b4, last green 3f9c0b2; the depth-1 recipe must pin the
pre-fix tool revision)". The log says "Both fixed before merge"; commit
`4e7ea5d` (`git show 4e7ea5d`) is that fix.

1. **Red-run span.** The record first said CI was red at five SHAs since H85.
   The navigator pinned it to 12 consecutive `main` pushes, `1889340` (H85's
   merge, #206) to `2b3d1b4`, with `3f9c0b2` (#205) the last green.
   `4e7ea5d` applied this to the Question, the Inputs row "Repo state", the
   first FACT under Interpretation, C-4130 and the H90 Goal. The Method's
   step-1 run count ("five") was not changed by `4e7ea5d`. This section
   leaves it as it is: H94 owns that line and the other typed counts.
2. **Depth-1 recipe pinned to the pre-fix tool.** `4e7ea5d` pinned C-4131
   to `git show 3d79bcc:tools/claims_check.py`. This record's Reproduction
   block still cloned the current tip
   (`git clone --depth 1 file://$PWD /tmp/x && cd /tmp/x`), which now prints the post-fix skip
   instead of the nine `COUNT` lines. H93 corrects that block in place to a
   depth-1 fetch of `3d79bcc` itself. Re-run on 2026-11-20 (branch
   `task/h93-h90-corrections-2`): shallow, 1 commit:
   `count mismatches: 9`, nine `COUNT` lines, exit 1. After
   `--unshallow`, `git rev-list --count HEAD` prints `809`: `count mismatches: 0`, `claims_check: OK`,
   exit 0. These are the same numbers as C-4131. The Method block (step 2) still
   shows the unpinned clone; H94 owns making the whole recipe one block.

No third flag was raised.

H93 navigator round (PR #377): no blockers, 2 should-fix, 2 nits. All four
are fixed:

1. *(should-fix, scope overlap)* H93 rewrote the Reproduction block above,
   which H94's Scope also claimed. H94's block in `TODO.md` now has a note
   that H93 did this, and the Reproduction clause is gone from its Scope and
   Falsifier.
2. *(should-fix)* The two typed `809` commit counts in this section and in
   Reproduction had no command beside them. Both now quote
   `git rev-list --count HEAD`. Correction 1 no longer quotes the Method's
   run-count phrase either, so H94's Done-when grep finds only H94's own lines.
3. *(nit)* The recipe used a relative `X` and `$OLDPWD`. It now uses
   `X=$(mktemp -d)` and `R=$PWD`.
4. *(nit)* Correction 2 now quotes the line it replaced:
   `git clone --depth 1 file://$PWD /tmp/x && cd /tmp/x`.
