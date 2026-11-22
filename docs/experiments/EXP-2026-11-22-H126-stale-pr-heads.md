# EXP-2026-11-22-H126: an open PR head with no completed gate check-run fails the watchdog

- **Status:** done (2026-11-22: re-ran the done-when — `main_watch.py --selftest`
  OK (34 checks) classifying a stale head (0 check-runs) and a tested head;
  `--replay-pr tools/fixtures/h126_pr394_heads.json` prints
  `stale #394 head 99d0b54b last tested 6b55ccd0` and exits 1; the live sweep
  `--prs --repo neutrinus/OSM2Leaf` names 0 stale heads today and exits 0; the
  stale `act_prs` path opens/updates the `[H126] fix:` issue and exits 1
  (offline, `find_issue` stubbed); `tools/gate.py` 0 fail)
- **Date:** 2026-11-22
- **Sample:** none (CI/tool task) — no vendor bytes; the subject is
  `.github/scripts/main_watch.py`, `.github/workflows/main-watch.yml`, the head
  of M8.C1 PR #394 (`99d0b54…` = 0 check-runs, previous `6b55ccd0…` = 6).
- **Tools:** `python3 3.15.0`; `gh` 2.x; `tools/gate.py`.
- **Claims:** C-6670
- **Supersedes:** none (H117 is the `main`-branch half; this is the PR-head half)
- **Superseded by:** none

## Question

Can the existing watchdog fail on an open non-draft PR whose **current head**
has no completed gate check-run, so a reviewer no longer reads
`no checks reported` as green (M8.C1 #394), without re-running or re-pushing
for the author and without changing `tools/gate.py`?

## Hypothesis

`pull_request` fires on a pushed head, but a force-push during a rebase, or a
push GitHub coalesced, can leave the new head with **0** check-runs while the
previous head's run stays listed. #394's head `99d0b54` (authored on `main` as
`b90f9d47`) has 0 check-runs and is absent from every branch run; `6b55ccd0`
has 6. A second sweep beside the `main` one, reading
`gh api …/commits/<head>/check-runs` for each open non-draft PR, is `stale`
when no completed gate check-run exists (a queued/in_progress run is
`pending` — wait; a draft is out of scope), and fails the watchdog naming the
PR, head and last-tested SHA. **Falsifier:** an open non-draft PR head with 0
completed gate check-runs and the sweep still exits 0.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `.github/scripts/main_watch.py`, `.github/workflows/main-watch.yml`, `tools/fixtures/h126_pr394_heads.json` |
| SHA-256 | n/a (text files) |
| Offset(s) / VA(s) | n/a |
| Tool / version | `python3 3.15.0`, `gh` 2.x |
| Repo tool | `.github/scripts/main_watch.py`, `tools/gate.py` |

## Method

1. **Sample and hash.** The watchdog script/workflow; the #394 head pair
   (`99d0b54` → 0, `6b55ccd0` → 6) read live with `gh api`.
2. **Commands.**

   ```bash
   # offline policy (fixed stale + tested heads)
   python3 .github/scripts/main_watch.py --selftest          # OK (34 checks)

   # the #394 fixture: stale head, last tested 6b55ccd0
   python3 .github/scripts/main_watch.py --replay-pr tools/fixtures/h126_pr394_heads.json
   #   -> stale #394 head 99d0b54b last tested 6b55ccd0, rc=1

   # live: every open non-draft PR head must have a completed gate check-run
   python3 .github/scripts/main_watch.py --prs --repo neutrinus/OSM2Leaf

   # the gate is unchanged
   python3 tools/gate.py                                     # 0 fail
   ```

3. **Controls.** *Positive:* #394's `99d0b54` has 0 check-runs and the replay
   is `stale`; the live sweep names 0 stale heads today (all open non-draft
   heads tested). *Negative:* a head with one completed non-cancelled gate
   check-run is `tested` (not stale); a `queued`/`in_progress` run is `pending`
   (not stale); a cancelled-only head is `stale`; a non-gate check-run is not
   a test; a draft is out of scope.
4. **Scope.** `.github/scripts/main_watch.py` (`PrVerdict`, `classify_pr`,
   `stale_prs`, `fetch_pr_heads`, `act_prs`, `run_pr_sweep`, `--prs`,
   `--replay-pr`) and `.github/workflows/main-watch.yml` (the `PR-head
   verdict` step, `pull-requests: read`, the summary). No gate-semantics
   change; `tools/gate.py` untouched; never re-runs or re-pushes for the
   author.
5. **Falsifier.** An open non-draft PR head with 0 completed gate check-runs
   and the sweep exits 0.

## Observations

Fixture, live:

```
$ gh api repos/neutrinus/OSM2Leaf/commits/99d0b54…/check-runs -q .total_count
0
$ gh api repos/neutrinus/OSM2Leaf/commits/6b55ccd0…/check-runs -q .total_count
6
```

Selftest and replay:

```
$ python3 .github/scripts/main_watch.py --selftest
main_watch selftest: OK (34 checks)
$ python3 .github/scripts/main_watch.py --replay-pr tools/fixtures/h126_pr394_heads.json
replay: 1 open PR(s), 1 stale
  stale #394 head 99d0b54b last tested 6b55ccd0
rc=1
```

Live sweep (today) and stale action (offline):

```
$ python3 .github/scripts/main_watch.py --prs --repo neutrinus/OSM2Leaf
main_watch: 1 open non-draft PR(s) (20 open incl. drafts), 0 stale head(s)
main_watch: PR HEADS OK -- 1 open non-draft PR(s) all tested        rc=0
# fabricated stale verdict:
DRY-RUN: gh issue create --title [H126] fix: open PR head has no completed gate check-run: #394 …
main_watch: PR HEADS STALE -- opened (dry-run) issue                rc=1
```

Gate:

```
$ python3 tools/gate.py
selftest      PASS
claims_check  PASS
todo_check    PASS
board_check   PASS
fn_audit      PASS
gate: 5 pass, 0 fail, 0 skip                                        rc=0
```

## Conclusion

`main_watch.py` now carries a PR-head sweep beside the `main` sweep: for every
open non-draft PR it reads the head's `/check-runs`, and a head with no
completed, non-cancelled gate check-run is `stale`. The sweep opens/updates one
`[H126] fix:` issue (`<!-- h126-stale-pr -->` marker) naming the PR, head and
last-tested SHA, and fails the watchdog while one exists; a `pending`
(queued/in_progress) run waits, a draft is out of scope, and it never re-runs
or re-pushes for the author. The workflow runs it from the existing hourly
`schedule`/`workflow_dispatch` with `pull-requests: read`. `tools/gate.py` is
unchanged (0 fail). All Done-when conditions hold; the Falsifier (0 check-runs
but exit 0) does not occur.

## Reproduce

```bash
git clone <repo> && cd <repo>
python3 .github/scripts/main_watch.py --selftest
python3 .github/scripts/main_watch.py --replay-pr tools/fixtures/h126_pr394_heads.json   # rc=1
python3 .github/scripts/main_watch.py --prs --repo neutrinus/OSM2Leaf
python3 tools/gate.py
```
