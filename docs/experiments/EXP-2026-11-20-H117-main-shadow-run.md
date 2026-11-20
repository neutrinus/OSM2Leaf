# EXP-2026-11-20-H117-main-shadow-run: a red push run must block the next merge

- **Status:** done
- **Date:** 2026-11-20
- **Sample:** `none (workflow/CI task; the "sample" is the GitHub Actions run
  history of `neutrinus/OSM2Leaf`, read with `gh run list`, no vendor bytes)`
- **Tools:** `python3 3.13` (repo tools are standard-library only);
  `gh` 2.x CLI against `github.com/neutrinus/OSM2Leaf`; `.github/scripts/main_watch.py`
  (new, `--selftest`/`--replay`); `.github/workflows/main-watch.yml` (new)
- **Claims:** C-5750–C-5753
- **Supersedes:** none
- **Superseded by:** none

## Question

Can a red `push`-to-`main` run of the gate ride into `main` unnoticed, and can a
watchdog make it block the next merge without branch protection?

## Hypothesis

`ci.yml` runs on `push` to `main` with `concurrency: cancel-in-progress: true`,
so a push cancels the previous run. A red run is therefore either reported as
`cancelled` or shadowed by a *later green run on a different commit*, and H98's
branch protection (the preferred fix) is **not** applied to the repository, so
nothing refuses the next merge.

**Falsifier:** the run history contains no red `main` run that was superseded by
merge activity without a board line, or `main` is protected and required checks
already refuse a red merge.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none (no vendor data) |
| SHA-256 | none |
| Offset(s) / VA(s) | none |
| Tool / version | `gh` CLI (token scopes `repo`, `workflow`), `python3 3.13` |
| Repo tool | `.github/scripts/main_watch.py` (new; not in `tools/`) |

## Method

### 1. Sample and hash

The sample is the Actions run list of the two gate workflows on `branch=main`,
and the merged-PR list, read on 2026-11-20. No image and no vendor bytes are
involved (`gh` API only).

### 2. Commands

```bash
# run history of the gate on main (the H117 precheck command)
gh run list --workflow "CI quality gate" --branch main --limit 100 \
  --json databaseId,headSha,status,conclusion,createdAt,url,event \
  > /tmp/opencode/h117-runs.json

# merges in the burst window
gh pr list --state merged --limit 100 --json number,mergedAt,title

# branch-protection state (H98, the preferred policy)
gh api repos/neutrinus/OSM2Leaf/branches/main/protection
gh api repos/neutrinus/OSM2Leaf/rulesets

# the watchdog policy, offline
python3 .github/scripts/main_watch.py --selftest
python3 .github/scripts/main_watch.py --replay /tmp/opencode/h117-runs.json
python3 .github/scripts/main_watch.py --runs-json /tmp/opencode/h117-runs.json --dry-run
# a synthetic red tip (a deliberately-red commit's run list)
python3 .github/scripts/main_watch.py --runs-json /tmp/opencode/h117-fixture-red.json --dry-run
```

`h117-fixture-red.json` is two runs, the newest a `failure` (database id
`44675505188`, the real red `98e0e3eb`), the older a `success`, so the red is
the tip and is not shadowed.

### 3. Controls

- **Positive:** the same classifier on the real 04:12–04:36 window must find
  the four red runs of the task block; `--replay` prints 7 red-tip moments for
  the 100-run list. A deliberately red branch (`h117-red-control`, one
  duplicate claim row) must show `claims_check: FAILED` and red `quality`
  checks on its PR (the Done-when control).
- **Negative:** a run list whose newest run is `success` must be `0 salient`
  and exit 0 (`--dry-run` on today's tip); an empty run list must be exit **2**
  ("cannot verify"), never 0; a `cancelled` run must not count as a green that
  covers an older red (selftest case 3).

### 4. Scope

The run list of **`CI quality gate`** on `main` (100 runs, 2026-11-19T23:xx …
2026-11-20T11:09Z) and, for completeness, **`L1/L2 synthetic fixtures`** (100
runs). Only `main`; a PR run is not gated by this tool. The watchdog workflow
itself cannot be executed before it is on `main` (`gh workflow run` needs the
default branch), so its effect on future pushes is unmeasured — only the policy
is measured, on the recorded history. Excluded: H98 (branch protection) and H90
(the shallow-clone cause) are not re-litigated.

### 5. Falsifier

Stated before the result: a burst with a red `main` run and a later merge, with
no issue/board line naming it, refutes "nothing refused the merge" being a
defect the policy closes.

## Observations

`gh run list --workflow "CI quality gate" --branch main --limit 100`:

```
total 100
Counter({'success': 72, 'cancelled': 21, 'failure': 7})
```

Runs in `2026-11-20T04:00`–`04:45`:

```
04:43:37Z success 52acb7c7
04:41:47Z success 7dc22c3b
04:36:05Z failure 98e0e3eb
04:33:43Z failure a480a8a6
04:27:08Z failure b3333cde
04:17:22Z success ac2a1995
04:12:12Z failure 6270c0cc
04:09:43Z success 2bbf085e
04:07:09Z success 6842510c
04:01:11Z failure eb7e53f8
```

`gh pr list --state merged ...` in `04:05Z`–`04:45Z`: **16** merges
(`283,292,284,295,296,273,293,303,301,299,274,291,305,310,294,288`).

`--replay /tmp/opencode/h117-runs.json`:

```
replay: 100 runs, 7 red-tip moments
  2026-11-20T03:55:49Z ec0c9b43 failure
  2026-11-20T03:59:42Z ef808740 failure
  2026-11-20T04:01:11Z eb7e53f8 failure
  2026-11-20T04:12:12Z 6270c0cc failure
  2026-11-20T04:27:08Z b3333cde failure
  2026-11-20T04:33:43Z a480a8a6 failure
  2026-11-20T04:36:05Z 98e0e3eb failure
```

Current verdict (`--runs-json … --dry-run`, limit 40):

```
main_watch: main tip d2fb7b48 success: 0 salient, 3 shadowed, 9 cancelled, 40 runs
main_watch: GREEN -- no salient red on main
```

The report command, `--branch main --limit 20`: `0 salient, 0 shadowed, 1
cancelled, 20 runs`, tip `d2fb7b48` `success` — no red without a board line.

Synthetic red tip (`--runs-json h117-fixture-red.json --dry-run`) exits **1**:

```
main_watch: main tip 99999999 failure: 1 salient, 0 shadowed, 0 cancelled, 2 runs
DRY-RUN: gh issue create --title [H117] fix: main gate red at 99999999 ...
main_watch: RED -- opened (dry-run) issue
```

Empty list exits **2** (`0 runs for main/CI quality gate -- cannot verify`).

`--selftest`: `main_watch selftest: OK (19 checks)`.

**Control on a real red PR** (branches off `origin/main` at `d2fb7b4`, one row
`| C-5540 | control: … |` appended to `claims.md`, pushed as
`h117-red-control`, PR #335):

```
duplicate claim IDs: 1
claims_check: FAILED                       # rc=1
gate: 1 pass, 2 fail, 1 skip -- not covered: fn_audit (missing archive/head256.img)   # gate rc=1

gh pr checks 335
quality (py3.11)  fail  1m0s
quality (py3.13)  fail  1m3s
quality (py3.14, informational)  fail  1m12s
l1l2 (py3.11)  pass
l1l2 (py3.13)  pass
```

The control PR was closed unmerged and its branch deleted; it proves a red
verdict is visible on the PR and that `main` is unprotected (a red PR can still
be merged by a push — the gap C-5750 records).

Branch protection:

```
{"message":"Branch not protected", ... "status":"404"}
rulesets: []
permissions: {"admin":true,"maintain":true,"pull":true,"push":true,"triage":true}
```

Cycle after the burst (`08:43`–`11:10`): `Counter({'success': 22, 'cancelled': 5})`,
4 `cancelled` in `08:45`–`09:30`; **0 red**. `L1/L2 synthetic fixtures`,
100 runs: `Counter({'success': 95, 'cancelled': 5})`.

## Interpretation

- **FACT:** `main` has no branch protection (`404`), no rulesets (`[]`), and the
  account has `admin: true`, so the preferred policy (H98) is *available* but
  not applied.
- **FACT:** the 04:12–04:36 burst is 4 red gate runs and 16 merges in the same
  40-minute window; the latest red (`98e0e3eb`) is covered only by a later
  green on a *different* commit (`52acb7c7`, `04:43:37Z`), not by a red-free
  tip.
- **FACT:** the control PR #335 (one duplicate claim row on `origin/main`) runs
  `quality (py3.11)` and `quality (py3.13)` to **fail** (`1m0s`, `1m3s`), so a
  red verdict is visible on the PR; the same red is mergeable by any push
  because `main` is unprotected.
- **OBSERVED:** under the new policy the same 100-run history has **7** red-tip
  moments (each would have failed the watchdog), and **3** shadowed reds in the
  newest 40 runs. The `cancelled` rows (21/100) are the concurrency de-dup and
  are *not* counted as green.
- **HYPOTHESIS:** with `main-watch.yml` on `main`, a red push opens a `[H117]
  fix:` issue on the `workflow_run` of that push and fails the watchdog, so the
  same burst would leave five board lines instead of zero.
- **UNKNOWN:** whether the owner will enable H98 protection (then policy (a)
  makes this watchdog redundant but harmless); the watchdog cannot be run
  before it is merged.

## Conclusion

Policy **(b)** is shipped: `.github/workflows/main-watch.yml` plus
`.github/scripts/main_watch.py`, a `main`-only watchdog on `workflow_run`
(completed gate run on `main`), an hourly sweep (a cancelled run emits no
`workflow_run`) and `workflow_dispatch`. It opens one `[H117] fix:` issue naming
the SHA and the failing job/step while a red tip has no later green, and exits
1; it exits 2 ("cannot verify") on an empty list. Policy **(a)** stays the
preferred shape and is parked on H98: `main` is unprotected today
(`gh api …/protection` → 404), so (a) alone cannot be tested here. Claims
C-5750–C-5753; `tools/gate.py` and every gate tool are untouched.

## Overtaken by a later commit

none (new record)

## Reproduction

```bash
gh run list --workflow "CI quality gate" --branch main --limit 100 \
  --json databaseId,headSha,status,conclusion,createdAt,url,event > /tmp/runs.json
python3 .github/scripts/main_watch.py --replay /tmp/runs.json          # 7 red-tip moments
python3 .github/scripts/main_watch.py --runs-json /tmp/runs.json --dry-run
python3 .github/scripts/main_watch.py --selftest                       # OK (19 checks)

# the Done-when control: a deliberately red branch shows a red PR check
git worktree add -b h117-red-control /tmp/h117-red origin/main
printf '\n| C-5540 | control: duplicate claim ID must fail claims_check | VERIFIED | H | EXP-2026-11-20-H117-main-shadow-run |\n' \
  >> /tmp/h117-red/docs/research/claims.md
(cd /tmp/h117-red && python3 tools/claims_check.py; git commit -am control && git push -u origin h117-red-control)
gh pr checks <the control PR>          # quality (py3.11)/(py3.13) fail
```

## Follow-ups

- [ ] When H98 lands branch protection, require `quality (py3.11)` and
  `quality (py3.13)` and keep this watchdog as the `main`-only audit.
- [ ] The watchdog's first real run needs it merged: check
  `gh run list --workflow "Main gate watchdog" --branch main` after the next
  red push and confirm the `[H117] fix:` issue appears.
