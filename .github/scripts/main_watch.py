#!/usr/bin/env python3
"""main_watch -- a red push-to-main gate run must not be a shadow run.

H117: `.github/workflows/ci.yml` runs on `push` to `main` with
`concurrency: cancel-in-progress: true`, so the next push cancels the previous
run.  A red run therefore disappears from the list as "cancelled" or is
shadowed by a *later* green run on a *different* commit, and nothing refuses
the next merge (2026-11-20 04:12-04:36Z: 4 red runs, 16 merges).

This watchdog reads the run list of the gate workflow on `main`, keeps every
red conclusion that has **no later green run** on the branch (`salient`), and
opens (or updates) one `[H117] fix:` issue naming the SHA, the failing step and
the run URL.  It exits non-zero while such a red is unaddressed, so the
watchdog run itself is the board line.  A red that a later green run already
replaced is `shadowed`, counted in the metrics line, and does not fail.

Policy (the (b) fallback of H117, because H98 branch protection is not
applied to this repo yet):
  * a red tip run opens the issue within one watchdog run and fails it;
  * the issue is closed only by a later green run of the gate on `main`, or by
    a human who accepts the risk (then the same red stays quiet: the marker
    `<!-- h117-salient: <run id> -->` in the issue body records it);
  * a *new* red after a closed one re-opens the issue and fails again.

Exit codes (the repo convention used by realcheck/l3check):
  0  no salient red (green tip, or a red a human already accepted), and no
     stale PR head (`--prs`)
  1  salient red, or (`--prs`) a stale PR head: the watchdog opened/updated
     the issue and fails
  2  cannot verify (no runs at all, gh missing, API error) -- never a pass

`--selftest` is offline: it classifies fixed run lists and builds the issue
body.  `--runs-json PATH` reads a saved `gh run list --json ...` document, and
`--dry-run` prints the actions without writing, so the policy can be replayed
(see EXP-2026-11-20-H117-main-shadow-run).

H126 (the `pull_request` twin): `--prs` sweeps every open non-draft PR and is
`stale` when the *current head* has no completed, non-cancelled gate check-run
(#394: head `99d0b54` has 0, previous `6b55ccd0` has 6, and no branch run ever
lists `99d0b54`).  A queued/in-progress run waits, a draft is out of scope, and
the sweep never re-runs or re-pushes for the author: it opens/updates one
`[H126] fix:` issue and fails.  `--replay-pr PATH` replays a saved open-PR
document (the #394 fixture) offline.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field

RED = frozenset({"failure", "timed_out", "startup_failure"})
GREEN = frozenset({"success"})
MARKER = "<!-- h117-main-watch -->"
SALIENT_RE = "<!-- h117-salient: {} -->"
TITLE_PREFIX = "[H117] fix: main gate red at "


@dataclass
class Verdict:
    tip_sha: str | None = None
    tip_conclusion: str | None = None
    salient: list = field(default_factory=list)
    shadowed: list = field(default_factory=list)
    cancelled: int = 0
    success: int = 0
    failure: int = 0
    total: int = 0
    runs: list = field(default_factory=list)

    def as_json(self) -> dict:
        return {
            "schema": "osm2leaf.main_watch/v1",
            "tip_sha": self.tip_sha,
            "tip_conclusion": self.tip_conclusion,
            "counts": {
                "runs": self.total,
                "success": self.success,
                "failure": self.failure,
                "cancelled": self.cancelled,
                "salient": len(self.salient),
                "shadowed": len(self.shadowed),
            },
            "salient": [short(r) for r in self.salient],
            "shadowed": [short(r) for r in self.shadowed],
        }


def short(run: dict) -> dict:
    return {
        "id": int(run["databaseId"]),
        "sha": run["headSha"],
        "short": run["headSha"][:8],
        "conclusion": run["conclusion"],
        "createdAt": run["createdAt"],
        "url": run.get("url", ""),
    }


def is_red(run: dict) -> bool:
    return run.get("conclusion") in RED


def is_green(run: dict) -> bool:
    return run.get("conclusion") in GREEN


def classify(runs: list) -> Verdict:
    """Split red runs into salient (no later green) and shadowed.

    `runs` is the `gh run list --branch <b>` order-independent list; newest is
    the tip.  For `main` the history is linear, so a run created later is on a
    descendant commit and a later green *does* cover an older red.  A run that
    is newer but `cancelled` covers nothing: that is the shadow-run defect.
    """
    ordered = sorted(
        runs, key=lambda r: (r.get("createdAt", ""), int(r.get("databaseId", 0))), reverse=True
    )
    v = Verdict(total=len(ordered), runs=ordered)
    if ordered:
        v.tip_sha = ordered[0].get("headSha")
        v.tip_conclusion = ordered[0].get("conclusion")
    later_green = False
    for run in ordered:
        if is_green(run):
            v.success += 1
            later_green = True
            continue
        if is_red(run):
            v.failure += 1
            (v.shadowed if later_green else v.salient).append(run)
        elif run.get("conclusion") == "cancelled":
            v.cancelled += 1
    return v


STEP_HINTS = (
    "FAILED GATES",
    "claims_check:",
    "todo_check:",
    "selftest:",
    "gate:",
    "mismatch",
    "duplicate task ID",
    "##[error]Process completed with exit code",
    "Traceback (most recent call last)",
)


def failure_steps(jobs: list) -> list:
    """`(job, step)` pairs whose conclusion is a failure, from `--json jobs`."""
    out = []
    for job in jobs or []:
        for step in job.get("steps") or []:
            if step.get("conclusion") in RED:
                out.append((job.get("name", "?"), step.get("name", "?")))
    return out


def salient_lines(text: str, limit: int = 8) -> str:
    """Keep only the lines that name what failed, not the runner noise."""
    keep = []
    for raw in text.splitlines():
        payload = raw.rstrip().split("\t", 2)[-1]
        if any(h in payload for h in STEP_HINTS):
            keep.append(payload)
    return "\n".join(keep[:limit])


def failing_step(run: dict, repo: str | None, runner) -> str:
    """Best-effort: name the failed job/step; never fail the watchdog on it."""
    base = ["gh", "run", "view", str(run["databaseId"])]
    if repo:
        base += ["--repo", repo]
    try:
        meta = json.loads(runner(base + ["--json", "jobs"], check=False) or "{}")
    except (OSError, ValueError):
        meta = {}
    steps = failure_steps(meta.get("jobs") or [])
    head = "\n".join(f"- {job} :: {step}" for job, step in steps) or "- (no failed job in the run metadata)"
    try:
        log = runner(base + ["--log-failed"], check=False)
    except OSError:
        log = ""
    tail = salient_lines(log or "")
    if not tail.strip():
        return head
    return head + "\n\n" + tail


def issue_body(v: Verdict, run: dict, tail: str) -> str:
    return "\n".join(
        [
            MARKER,
            SALIENT_RE.format(int(run["databaseId"])),
            "",
            "A `push` run of the **CI quality gate** on `main` is red and no later",
            "green run on `main` covers it. Under the old policy the next push",
            "cancelled this run and the next merge went in anyway (H117).",
            "",
            f"- commit: `{run['headSha']}`",
            f"- conclusion: **{run['conclusion']}**",
            f"- run: {run.get('url', '')}",
            f"- created: {run['createdAt']}",
            "",
            "## Failing step",
            "",
            "```",
            tail.strip() or "(none)",
            "```",
            "",
            "## Policy",
            "",
            "- This issue is the block: the watchdog run is red while it is open.",
            "- It closes itself when a later `main` run of the gate is green.",
            "- Closing it by hand accepts the red; the same run stays quiet, a new",
            "  red re-opens it.",
            "",
            "Metrics: "
            f"{len(v.salient)} salient red, {len(v.shadowed)} shadowed red, "
            f"{v.cancelled} cancelled, {v.total} runs read.",
        ]
    )


def run_json(args) -> Verdict:
    cmd = [
        "gh",
        "run",
        "list",
        "--workflow",
        args.workflow,
        "--branch",
        args.branch,
        "--limit",
        str(args.limit),
        "--json",
        "databaseId,headSha,status,conclusion,createdAt,url,event",
    ]
    if args.repo:
        cmd += ["--repo", args.repo]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"main_watch: gh run list failed: {out.stderr.strip()}")
    return classify(json.loads(out.stdout))


def find_issue(gh, repo: str | None, prefix: str = TITLE_PREFIX,
               marker: str = MARKER) -> dict | None:
    cmd = [
        "gh", "issue", "list", "--state", "all",
        "--search", f'"{prefix}" in:title',
        "--json", "number,title,state,body",
        "--limit", "20",
    ]
    if repo:
        cmd += ["--repo", repo]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"main_watch: gh issue list failed: {out.stderr.strip()}")
    issues = json.loads(out.stdout)
    mine = [i for i in issues if marker in (i.get("body") or "")]
    if not mine:
        return None
    mine.sort(key=lambda i: i["number"], reverse=True)
    return mine[0]


def marker_id(body: str) -> int | None:
    for line in (body or "").splitlines():
        if line.startswith("<!-- h117-salient: "):
            try:
                return int(line.split(":", 1)[1].replace("-->", "").strip())
            except ValueError:
                return None
    return None


def gh_write(cmd, repo: str | None, dry: bool) -> str:
    if repo:
        cmd = cmd + ["--repo", repo]
    if dry:
        print("DRY-RUN:", " ".join(cmd))
        return ""
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"main_watch: {' '.join(cmd[:3])} failed: {out.stderr.strip()}")
    return out.stdout


def act(v: Verdict, args) -> int:
    if v.total == 0:
        print(f"main_watch: 0 runs for {args.branch}/{args.workflow} -- cannot verify")
        return 2
    repo = args.repo
    issue = find_issue(None, repo)
    if not v.salient:
        if issue and issue["state"] == "OPEN":
            gh_write(["gh", "issue", "comment", str(issue["number"]), "--body",
                      "A later green run on `main` covers this red; closing."], repo, args.dry_run)
            gh_write(["gh", "issue", "close", str(issue["number"]), "--reason", "completed"],
                     repo, args.dry_run)
            print(f"main_watch: GREEN -- closed issue #{issue['number']}")
        else:
            print("main_watch: GREEN -- no salient red on " + str(args.branch))
        return 0

    tip = v.salient[0]
    marker = marker_id(issue["body"]) if issue else None
    if issue and issue["state"] == "CLOSED" and marker == int(tip["databaseId"]):
        print(
            f"main_watch: red {tip['headSha'][:8]} accepted by hand "
            f"(issue #{issue['number']} closed); not reopening"
        )
        return 0

    tail = failing_step(tip, repo, lambda c, check=True: subprocess.run(
        c, capture_output=True, text=True, check=check).stdout)
    body = issue_body(v, tip, tail)
    title = TITLE_PREFIX + tip["headSha"][:8]

    if issue is None:
        out = gh_write(["gh", "issue", "create", "--title", title, "--body", body],
                       repo, args.dry_run)
        print(f"main_watch: RED -- opened {out.strip() or '(dry-run) issue'}")
        return 1

    if issue["state"] == "CLOSED":
        gh_write(["gh", "issue", "reopen", str(issue["number"])], repo, args.dry_run)
        gh_write(["gh", "issue", "comment", str(issue["number"]), "--body",
                  f"New salient red `{tip['headSha'][:8]}`; re-opening."], repo, args.dry_run)
    gh_write(["gh", "issue", "edit", str(issue["number"]), "--title", title, "--body", body],
             repo, args.dry_run)
    print(
        f"main_watch: RED -- {'updated' if issue['state'] == 'OPEN' else 'reopened'} "
        f"issue #{issue['number']} for {tip['headSha'][:8]}"
    )
    return 1


# ------------------------------------------------------------- PR-head sweep
#
# H126: a `pull_request` run fires on a pushed head, but a force-push, a
# rebase, or a push GitHub coalesced can leave an open PR whose *current* head
# has **no** check-run at all (M8.C1 #394: head `99d0b54` has 0, the previous
# head `6b55ccd0` has 6, and no branch run ever lists `99d0b54`).  Reviewers
# then read "no checks reported" as green.  This sweep reads every open
# non-draft PR, asks the commit check-runs API for its head, and is `stale`
# when no completed gate check-run exists.  It never re-runs or re-pushes for
# the author; it only reports and fails the watchdog (no branch protection yet,
# H98).

PR_MARKER = "<!-- h126-stale-pr -->"
PR_TITLE_PREFIX = "[H126] fix: open PR head has no completed gate check-run: "
#: Check-runs on a head count as "tested" when one is a completed run of a gate
#: workflow.  A gate run is any check-run whose `app`/`name` names the gate;
#: the `name` is the workflow (`CI quality gate`) or a job like
#: `quality (py3.11)`.  Bare `/`-free names such as `Self-hosted` are ignored.
GATE_CHECK_HINTS = ("quality", "gate", "l1/l2", "synthetic fixtures", "ci")


@dataclass
class PrVerdict:
    """One open PR and whether its head is tested."""
    number: int
    title: str
    head_sha: str
    is_draft: bool = False
    check_runs: list = field(default_factory=list)
    #: `tested` -- >=1 completed, non-cancelled gate check-run;
    #: `pending` -- a run is queued/in_progress (wait, never stale);
    #: `stale`   -- 0 check-runs, or only cancelled / non-gate ones;
    #: `draft`   -- a draft is out of scope (opening the gate is the author's).
    state: str = "stale"
    #: The last branch head that *does* have a completed gate run, if any.
    last_tested_sha: str | None = None
    #: How many gate check-runs were completed and non-cancelled.
    tested_count: int = 0

    def as_json(self) -> dict:
        return {
            "number": self.number,
            "title": self.title,
            "head_sha": self.head_sha,
            "head_short": self.head_sha[:8],
            "is_draft": self.is_draft,
            "state": self.state,
            "tested_count": self.tested_count,
            "last_tested_sha": self.last_tested_sha,
            "check_runs": self.check_runs,
        }


def is_gate_check(check_run: dict) -> bool:
    """Whether one check-run belongs to the gate (never a neutral app)."""
    name = (check_run.get("name") or "").lower()
    app = (check_run.get("app") or {}).get("slug", "") if isinstance(
        check_run.get("app"), dict) else ""
    if app in ("github-actions",):
        # A gate job name still names the gate; a bare runner name does not.
        return any(h in name for h in GATE_CHECK_HINTS)
    return any(h in name for h in GATE_CHECK_HINTS)


def classify_pr(pr: dict, check_runs: list,
                branch_runs: list | None = None) -> PrVerdict:
    """Classify one open PR's head from its check-runs and branch history.

    ``check_runs`` is the check-runs API list for ``pr['headRefOid']``;
    ``branch_runs`` is an optional ``gh run list --branch <head branch>``
    document so ``last_tested_sha`` can name the previous tested head.
    """
    head = pr.get("headRefOid") or pr.get("head_sha") or ""
    v = PrVerdict(number=int(pr.get("number", 0)),
                  title=pr.get("title", ""),
                  head_sha=head,
                  is_draft=bool(pr.get("isDraft", False)),
                  check_runs=[_check_short(c) for c in check_runs or []])
    if v.is_draft:
        v.state = "draft"
        return v
    completed = [c for c in (check_runs or [])
                 if c.get("status") == "completed"]
    pending = [c for c in (check_runs or [])
               if c.get("status") in ("queued", "in_progress")]
    tested = [c for c in completed if c.get("conclusion") != "cancelled"
              and is_gate_check(c)]
    v.tested_count = len(tested)
    if tested:
        v.state = "tested"
    elif pending:
        # A queued/in_progress run means the head *is* being tested; wait.
        v.state = "pending"
    else:
        v.state = "stale"
    # Name the most recent tested head from the branch run list (H126's
    # #394 fixture: `99d0b54` stale, last tested `6b55ccd0`).
    if branch_runs:
        for r in branch_runs:
            sha = r.get("headSha") or ""
            if sha and sha != head and r.get("conclusion") == "success":
                v.last_tested_sha = sha
                break
    return v


def _check_short(c: dict) -> dict:
    return {
        "name": c.get("name", "?"),
        "status": c.get("status", "?"),
        "conclusion": c.get("conclusion"),
    }


def stale_prs(verdicts: list) -> list:
    """The non-draft PRs whose head has no completed gate check-run."""
    return [v for v in verdicts if v.state == "stale"]


def fetch_pr_heads(repo: str | None, runner) -> list:
    """Read every open PR and its head check-runs via `gh api`.

    Returns `(pr, check_runs)` dicts; an API error raises so the watchdog
    exits 2 (never a quiet pass).
    """
    base = ["gh", "pr", "list", "--state", "open", "--limit", "100",
            "--json", "number,title,headRefOid,isDraft,headRefName"]
    if repo:
        base += ["--repo", repo]
    out = runner(base, check=True)
    prs = json.loads(out or "[]")
    result = []
    for pr in prs:
        sha = pr.get("headRefOid") or ""
        cr_cmd = (["gh", "api",
                   f"repos/{repo or 'OWNER/REPO'}/commits/{sha}/check-runs"]
                  if sha else None)
        checks = []
        if cr_cmd:
            raw = runner(cr_cmd, check=True)
            checks = (json.loads(raw or "{}").get("check_runs") or [])
        result.append((pr, checks))
    return result


def pr_issue_body(stale: list, total: int) -> str:
    rows = ["| PR | head | last tested |", "| --- | --- | --- |"]
    for v in stale:
        rows.append(f"| #{v.number} `{v.title[:50]}` | `{v.head_sha[:8]}` "
                    f"| `{(v.last_tested_sha or 'none')[:8]}` |")
    return "\n".join([
        PR_MARKER,
        "",
        "An open non-draft PR's **current head** has no completed gate",
        "check-run, so a reviewer sees `no checks reported` and a",
        "green-looking PR whose tip was never tested (H126, the `pull_request`",
        "twin of H117). A push that GitHub coalesced or a force-push during a",
        "rebase drops the run; `pull_request` fires on the next push only.",
        "",
        *rows,
        "",
        "## Policy",
        "",
        "- This sweep never re-runs or re-pushes for the author; it reports.",
        "- A `pending` run (queued/in_progress) is not stale: the sweep waits.",
        "- A draft PR is out of scope: opening it for review is the author's.",
        f"- The watchdog run is red while {len(stale)} of {total} open",
        "  non-draft PR(s) are stale.",
        "- A re-push of the head (or a rebase onto the base) starts a fresh",
        "  gate run and clears the row.",
    ])


def act_prs(verdicts: list, args) -> int:
    """Report (and fail on) stale PR heads; never re-run or re-push (H126)."""
    repo = args.repo
    stale = stale_prs(verdicts)
    total = [v for v in verdicts if v.state != "draft"]
    issue = find_issue(None, repo, PR_TITLE_PREFIX, PR_MARKER)
    if not stale:
        if issue and issue["state"] == "OPEN":
            gh_write(["gh", "issue", "comment", str(issue["number"]), "--body",
                      "Every open non-draft PR head now has a completed gate "
                      "check-run; closing."], repo, args.dry_run)
            gh_write(["gh", "issue", "close", str(issue["number"]),
                      "--reason", "completed"], repo, args.dry_run)
            print(f"main_watch: PR HEADS OK -- closed issue #{issue['number']}")
        else:
            print(f"main_watch: PR HEADS OK -- {len(total)} open non-draft PR(s) "
                  "all tested")
        return 0

    body = pr_issue_body(stale, len(total))
    title = PR_TITLE_PREFIX + ", ".join(f"#{v.number}" for v in stale[:3])
    if issue is None:
        out = gh_write(["gh", "issue", "create", "--title", title,
                        "--body", body], repo, args.dry_run)
        print(f"main_watch: PR HEADS STALE -- opened "
              f"{out.strip() or '(dry-run) issue'}")
        return 1
    if issue["state"] == "CLOSED":
        gh_write(["gh", "issue", "reopen", str(issue["number"])], repo,
                 args.dry_run)
    gh_write(["gh", "issue", "edit", str(issue["number"]), "--title", title,
              "--body", body], repo, args.dry_run)
    print(f"main_watch: PR HEADS STALE -- "
          f"{'updated' if issue['state'] == 'OPEN' else 'reopened'} "
          f"issue #{issue['number']} for "
          + ", ".join(f"#{v.number} ({v.head_sha[:8]})" for v in stale))
    return 1


def run_pr_sweep(args) -> tuple[list, int]:
    """Read open PRs and classify each head; return (verdicts, read count)."""
    repo = args.repo

    def runner(cmd, check=True):
        out = subprocess.run(cmd, capture_output=True, text=True)
        if out.returncode != 0:
            raise SystemExit(f"main_watch: {' '.join(cmd[:3])} failed: "
                             f"{out.stderr.strip()}")
        return out.stdout

    pairs = fetch_pr_heads(repo, runner)
    verdicts = []
    for pr, checks in pairs:
        branch = pr.get("headRefName") or ""
        branch_runs = []
        if branch:
            try:
                raw = runner(["gh", "run", "list", "--workflow",
                              "CI quality gate", "--branch", branch,
                              "--limit", "8", "--json",
                              "headSha,conclusion"] +
                             (["--repo", repo] if repo else []))
                branch_runs = json.loads(raw or "[]")
            except (SystemExit, ValueError):
                branch_runs = []
        verdicts.append(classify_pr(pr, checks, branch_runs))
    return verdicts, len(pairs)


# ---------------------------------------------------------------- selftest

def _run(i, sha, conclusion, minute):
    return {
        "databaseId": i,
        "headSha": sha,
        "conclusion": conclusion,
        "createdAt": f"2026-11-20T04:{minute:02d}:00Z",
        "url": f"https://example.invalid/{i}",
        "event": "push",
    }


def selftest() -> int:
    checks = 0

    def eq(name, got, want):
        nonlocal checks
        if got != want:
            raise AssertionError(f"{name}: got {got!r}, want {want!r}")
        checks += 1

    # 1. red tip: nothing covers it.
    v = classify([_run(1, "a" * 40, "success", 1), _run(2, "b" * 40, "failure", 2)])
    eq("red tip salient", [r["databaseId"] for r in v.salient], [2])
    eq("red tip shadowed", v.shadowed, [])
    eq("red tip conclusion", v.tip_conclusion, "failure")

    # 2. the 04:12-04:36 burst shape: a red followed by a later green is shadowed.
    v = classify([
        _run(10, "c" * 40, "failure", 10),
        _run(11, "d" * 40, "failure", 11),
        _run(12, "e" * 40, "success", 12),
    ])
    eq("burst salient", v.salient, [])
    eq("burst shadowed", [r["databaseId"] for r in v.shadowed], [11, 10])
    eq("burst failure count", v.failure, 2)

    # 3. a cancelled run covers nothing (the 08:45 shape).
    v = classify([
        _run(20, "f" * 40, "cancelled", 20),
        _run(21, "0" * 40, "failure", 21),
    ])
    eq("cancelled tip not green", [r["databaseId"] for r in v.salient], [21])
    eq("cancelled counted", v.cancelled, 1)

    # 4. red, green, red: only the newest red is salient.
    v = classify([
        _run(30, "1" * 40, "failure", 30),
        _run(31, "2" * 40, "success", 31),
        _run(32, "3" * 40, "failure", 32),
    ])
    eq("red-green-red salient", [r["databaseId"] for r in v.salient], [32])
    eq("red-green-red shadowed", [r["databaseId"] for r in v.shadowed], [30])

    # 5. empty list is never green.
    v = classify([])
    eq("empty total", v.total, 0)
    eq("empty tip", v.tip_sha, None)

    # 6. body carries the marker the next run reads back.
    v = classify([_run(40, "4" * 40, "failure", 40)])
    body = issue_body(v, v.salient[0], "- quality (py3.11) :: Standing gate (tools/gate.py)")
    eq("body marker", marker_id(body), 40)
    eq("body names sha", "4" * 40 in body, True)
    eq("body names step", "Standing gate" in body, True)

    # 6b. the failing step comes from job metadata, not the log noise.
    jobs = [
        {"name": "quality (py3.11)", "steps": [
            {"name": "Checkout", "conclusion": "success"},
            {"name": "Standing gate (tools/gate.py)", "conclusion": "failure"},
        ]},
        {"name": "quality (py3.14, informational)", "steps": [
            {"name": "Standing gate (tools/gate.py)", "conclusion": "failure"},
        ]},
    ]
    eq("failure steps",
       failure_steps(jobs),
       [("quality (py3.11)", "Standing gate (tools/gate.py)"),
        ("quality (py3.14, informational)", "Standing gate (tools/gate.py)")])
    eq("salient lines keep the verdict",
       salient_lines("j\tx\t2026Z claims_check: FAILED\nj\tx\t2026Z Runner noise\n"), "2026Z claims_check: FAILED")

    # 7. a green list closes nothing and never fails.
    v = classify([_run(50, "5" * 40, "success", 50)])
    eq("green salient", v.salient, [])
    eq("green tip", v.tip_conclusion, "success")

    # --- H126: the PR-head sweep --------------------------------------------
    def _check(name, status, conclusion=None):
        return {"name": name, "status": status, "conclusion": conclusion,
                "app": {"slug": "github-actions"}}

    # 8. the #394 fixture: a stale head (0 check-runs) and a tested head.
    prs = [
        {"number": 394, "title": "M8.C1 HPB DMAC", "headRefOid": "99d0b54" + "0" * 33,
         "isDraft": False, "headRefName": "task/m8.c1-hpb-dmac"},
        {"number": 999, "title": "tested PR", "headRefOid": "ce1a35cc" + "0" * 32,
         "isDraft": False, "headRefName": "task/x"},
    ]
    checks_by_pr = {
        394: [],  # no run ever listed the coalesced head
        999: [_check("quality (py3.11)", "completed", "success"),
              _check("quality (py3.13)", "completed", "success")],
    }
    branch_runs = {
        394: [{"headSha": "ce1a35cc" + "0" * 32, "conclusion": "success"},
              {"headSha": "6b55ccd0" + "0" * 32, "conclusion": "success"},
              {"headSha": "19748d25" + "0" * 32, "conclusion": "success"}],
        999: [],
    }
    verdicts = [classify_pr(pr, checks_by_pr[pr["number"]],
                            branch_runs[pr["number"]])
                for pr in prs]
    eq("394 stale", verdicts[0].state, "stale")
    eq("394 head", verdicts[0].head_sha.startswith("99d0b54"), True)
    eq("394 last tested", verdicts[0].last_tested_sha[:8], "ce1a35cc")
    eq("999 tested", verdicts[1].state, "tested")
    eq("999 tested count", verdicts[1].tested_count, 2)
    eq("stale set is #394 only", [v.number for v in stale_prs(verdicts)], [394])

    # 8b. a pending (queued/in_progress) run is not stale: wait, do not fail.
    pending = classify_pr(
        {"number": 7, "title": "p", "headRefOid": "abc" + "0" * 37, "isDraft": False},
        [_check("quality (py3.11)", "in_progress")])
    eq("pending is not stale", pending.state, "pending")
    eq("pending not in stale", stale_prs([pending]), [])

    # 8c. a cancelled-only head is stale (cancelled covers nothing, H117).
    cancelled = classify_pr(
        {"number": 8, "title": "c", "headRefOid": "def" + "0" * 37, "isDraft": False},
        [_check("quality (py3.11)", "completed", "cancelled")])
    eq("cancelled-only is stale", cancelled.state, "stale")

    # 8d. a non-gate check-run (e.g. a neutral app) does not count as tested.
    neutral = classify_pr(
        {"number": 9, "title": "n", "headRefOid": "123" + "0" * 37, "isDraft": False},
        [{"name": "Self-hosted runner", "status": "completed",
          "conclusion": "success", "app": {"slug": "someone-else"}}])
    eq("neutral check-run is not a gate test", neutral.state, "stale")

    # 8e. a draft is out of scope and never reported stale.
    draft = classify_pr(
        {"number": 10, "title": "d", "headRefOid": "456" + "0" * 37, "isDraft": True},
        [])
    eq("draft out of scope", draft.state, "draft")
    eq("draft not stale", stale_prs([draft]), [])

    # 8f. the PR issue body carries the second marker and names the row.
    body = pr_issue_body(stale_prs(verdicts), 2)
    eq("PR body marker", PR_MARKER in body, True)
    eq("PR body names 394", "#394" in body, True)
    eq("PR body names head", "99d0b54" in body, True)

    print(f"main_watch selftest: OK ({checks} checks)")
    return 0


def replay_pr(path: str) -> int:
    """Replay a saved open-PR document and print its stale rows (H126).

    The document is a JSON list of objects ``{"pr": …, "check_runs": […],
    "branch_runs": […]}`` (the H126 #394 fixture), so the stale verdict and its
    last-tested SHA reproduce offline.
    """
    doc = json.load(open(path, encoding="utf-8"))
    verdicts = []
    for row in doc:
        if "pr" in row:
            verdicts.append(classify_pr(row["pr"], row.get("check_runs") or [],
                                        row.get("branch_runs") or []))
        else:
            pr, checks = row
            verdicts.append(classify_pr(pr, checks))
    stale = stale_prs(verdicts)
    print(f"replay: {len(verdicts)} open PR(s), {len(stale)} stale")
    for v in stale:
        print(f"  stale #{v.number} head {v.head_sha[:8]} "
              f"last tested {(v.last_tested_sha or 'none')[:8]}")
    return 1 if stale else 0


def replay(path: str) -> int:
    """Walk the history and print every moment the tip run was red.

    Each step classifies the run window that ended at that run (as the
    watchdog would have seen it), so a red that a later green covers is a
    red-tip moment here but not a salient one at the end of the window.
    """
    runs = json.load(open(path, encoding="utf-8"))
    ordered = sorted(
        runs, key=lambda r: (r.get("createdAt", ""), int(r.get("databaseId", 0)))
    )
    red_tips = []
    for i in range(len(ordered)):
        window = ordered[max(0, i - 39): i + 1]
        v = classify(window)
        if v.tip_conclusion in RED:
            red_tips.append((ordered[i]["createdAt"], ordered[i]["headSha"][:8], v.tip_conclusion))
    print(f"replay: {len(ordered)} runs, {len(red_tips)} red-tip moments")
    for created, sha, conclusion in red_tips:
        print(f"  {created} {sha} {conclusion}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="H117/H126: fail on an unaddressed red gate run on main, or on a stale PR head")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--workflow", default="CI quality gate")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--json", dest="json_path", help="write the verdict document (or - for stdout)")
    ap.add_argument("--runs-json", help="read a saved gh run list --json document instead of gh")
    ap.add_argument("--dry-run", action="store_true", help="print issue writes, do not apply")
    ap.add_argument("--replay", metavar="RUNS_JSON", help="list red-tip moments in a run list")
    ap.add_argument("--prs", action="store_true",
                    help="H126: sweep open non-draft PR heads for a missing gate check-run")
    ap.add_argument("--replay-pr", metavar="PR_JSON",
                    help="H126: replay a saved open-PR document (the #394 fixture)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.replay:
        return replay(args.replay)
    if args.replay_pr:
        return replay_pr(args.replay_pr)

    if args.prs:
        verdicts, total = run_pr_sweep(args)
        non_draft = [v for v in verdicts if v.state != "draft"]
        doc = {
            "schema": "osm2leaf.main_watch.prs/v1",
            "counts": {"open": total,
                       "open_non_draft": len(non_draft),
                       "stale": len(stale_prs(verdicts))},
            "prs": [v.as_json() for v in verdicts],
        }
        if args.json_path == "-":
            print(json.dumps(doc, indent=2))
        elif args.json_path:
            with open(args.json_path, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2)
                f.write("\n")
        print(f"main_watch: {len(non_draft)} open non-draft PR(s) "
              f"({total} open incl. drafts), "
              f"{len(stale_prs(verdicts))} stale head(s)")
        return act_prs(verdicts, args)

    v = classify(json.load(open(args.runs_json, encoding="utf-8"))) if args.runs_json else run_json(args)
    doc = v.as_json()
    if args.json_path == "-":
        print(json.dumps(doc, indent=2))
    elif args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
            f.write("\n")
    print(
        f"main_watch: {args.branch} tip {str(v.tip_sha)[:8]} "
        f"{v.tip_conclusion}: {len(v.salient)} salient, {len(v.shadowed)} shadowed, "
        f"{v.cancelled} cancelled, {v.total} runs"
    )
    return act(v, args)


if __name__ == "__main__":
    sys.exit(main())
