# EXP-2026-11-17-H90: CI red on `main` — a shallow checkout, not a bad ledger

- **Status:** done
- **Date:** 2026-11-17
- **Sample:** `none (CI/tool task)`; the git history of `origin/main` at
  `3d79bcc` (809 commits, pack 3.2 MiB) and a `--depth 1` clone of it.
- **Tools:** git 2.5x, python3 3.15; `tools/claims_check.py`, `tools/gate.py`,
  `.github/workflows/ci.yml`
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
| Tool / version | python3 3.15, git 2.5x |
| Repo tools | `tools/claims_check.py`, `tools/gate.py`, `.github/workflows/ci.yml` |

## Method

1. **Sample.** The five `main` pushes whose `CI quality gate` run failed, and
   a depth-1 clone of the same tree.
2. **Commands.**
   ```bash
   gh run list --workflow "CI quality gate" --branch main --limit 12 \
     --json createdAt,headSha,conclusion
   gh run view <id> --log-failed        # the nine COUNT lines
   git clone --depth 1 file://$PWD /tmp/x && cd /tmp/x
   python3 tools/claims_check.py --strict --count-check
   git fetch --unshallow && python3 tools/claims_check.py --strict --count-check
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
rm -rf /tmp/x && git clone --depth 1 file://$PWD /tmp/x && cd /tmp/x
python3 tools/claims_check.py --strict --count-check   # 9 COUNT lines, exit 1
git fetch --unshallow
python3 tools/claims_check.py --strict --count-check   # count mismatches: 0, exit 0
```

## Corrections after navigator review

(empty until the navigator round returns)
