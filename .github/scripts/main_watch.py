#!/usr/bin/env python3
"""main_watch -- a red push-to-main gate run must not be a shadow run.

H117: `.github/workflows/ci.yml` runs on `push` to `main` with
`concurrency: cancel-in-progress: true`, so the next push cancels the previous
run.  A red run therefore disappears from the list as "cancelled" or is
shadowed by a *later* green run on a *different* commit, and nothing refuses
the next merge (2026-11-20 04:12-04:36Z: 4 red runs, 16 merges).

This watchdog reads the run list of the gate workflow on `main`, keeps every
red conclusion that has **no later green run of the same workflow** on the
branch (`salient`), and opens (or updates) one `[H117] fix:` issue naming the
SHA, the failing step and the run URL.  It exits non-zero while such a red is
unaddressed, so the watchdog run itself is the board line.  A red that a later
green run of *the same workflow* already replaced is `shadowed`, counted in the
metrics line, and does not fail.  A green run of a *different* workflow (the
`L1/L2 synthetic fixtures` workflow beside the gate) proves nothing about the
gate's selftest/claims_check/todo_check and is counted as `unrelated-green`
(M9.64).

Policy (the (b) fallback of H117, because H98 branch protection is not
applied to this repo yet):
  * a red tip run opens the issue within one watchdog run and fails it;
  * the issue is closed only by a later green run of the gate on `main`, or by
    a human who accepts the risk (then the same red stays quiet: the marker
    `<!-- h117-salient: <run id> -->` in the issue body records it);
  * a *new* red after a closed one re-opens the issue and fails again.

Exit codes (the repo convention used by realcheck/l3check):
  0  no salient red (green tip, or a red a human already accepted)
  1  salient red: the watchdog opened/updated the issue and fails
  2  cannot verify (no runs at all, gh missing, API error) -- never a pass

`--selftest` is offline: it classifies fixed run lists and builds the issue
body.  `--runs-json PATH` reads a saved `gh run list --json ...` document, and
`--dry-run` prints the actions without writing, so the policy can be replayed
(see EXP-2026-11-20-H117-main-shadow-run).
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
    unrelated_green: list = field(default_factory=list)
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
                "unrelated_green": len(self.unrelated_green),
            },
            "salient": [short(r) for r in self.salient],
            "shadowed": [short(r) for r in self.shadowed],
            "unrelated_green": [short(r) for r in self.unrelated_green],
        }


def short(run: dict) -> dict:
    return {
        "id": int(run["databaseId"]),
        "sha": run["headSha"],
        "short": run["headSha"][:8],
        "workflow": run.get("workflowName", ""),
        "conclusion": run["conclusion"],
        "createdAt": run["createdAt"],
        "url": run.get("url", ""),
    }


def is_red(run: dict) -> bool:
    return run.get("conclusion") in RED


def is_green(run: dict) -> bool:
    return run.get("conclusion") in GREEN


def classify(runs: list) -> Verdict:
    """Split red runs into salient (no later green of the same workflow) and shadowed.

    `runs` is the `gh run list --branch <b>` order-independent list; newest is
    the tip.  For `main` the history is linear, so a run created later is on a
    descendant commit and a later green *of the same workflow* does cover an
    older red.  A green run of a *different* workflow does not: `CI quality
    gate` runs selftest/claims_check/todo_check/fn_audit, while `L1/L2
    synthetic fixtures` runs the card round-trips, so a green L1/L2 proves
    nothing about a red gate (M9.64).  Such a green is counted as
    `unrelated_green`.  A run that is newer but `cancelled` covers nothing
    either: that is the shadow-run defect.
    """
    ordered = sorted(
        runs, key=lambda r: (r.get("createdAt", ""), int(r.get("databaseId", 0))), reverse=True
    )
    v = Verdict(total=len(ordered), runs=ordered)
    if ordered:
        v.tip_sha = ordered[0].get("headSha")
        v.tip_conclusion = ordered[0].get("conclusion")
    later_green = set()
    for run in ordered:
        workflow = run.get("workflowName", "")
        if is_green(run):
            v.success += 1
            later_green.add(workflow)
            continue
        if is_red(run):
            v.failure += 1
            if workflow in later_green:
                v.shadowed.append(run)
            else:
                v.salient.append(run)
        elif run.get("conclusion") == "cancelled":
            v.cancelled += 1
    red_workflows = {run.get("workflowName", "") for run in ordered if is_red(run)}
    if red_workflows:
        for run in ordered:
            if is_green(run) and run.get("workflowName", "") not in red_workflows:
                v.unrelated_green.append(run)
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
            f"{len(v.unrelated_green)} unrelated green, "
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
        "databaseId,headSha,status,conclusion,createdAt,url,event,workflowName",
    ]
    if args.repo:
        cmd += ["--repo", args.repo]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"main_watch: gh run list failed: {out.stderr.strip()}")
    return classify(json.loads(out.stdout))


def find_issue(gh, repo: str | None) -> dict | None:
    cmd = [
        "gh", "issue", "list", "--state", "all",
        "--search", f'"{TITLE_PREFIX}" in:title',
        "--json", "number,title,state,body",
        "--limit", "20",
    ]
    if repo:
        cmd += ["--repo", repo]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"main_watch: gh issue list failed: {out.stderr.strip()}")
    issues = json.loads(out.stdout)
    mine = [i for i in issues if MARKER in (i.get("body") or "")]
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


# ---------------------------------------------------------------- selftest

def _run(i, sha, conclusion, minute, workflow="CI quality gate"):
    return {
        "databaseId": i,
        "headSha": sha,
        "conclusion": conclusion,
        "createdAt": f"2026-11-20T04:{minute:02d}:00Z",
        "url": f"https://example.invalid/{i}",
        "event": "push",
        "workflowName": workflow,
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

    # 8. M9.64: a green run of another workflow does not cover a red gate run.
    #    gate red at :10, L1/L2 green at :20 -> the gate red is still salient.
    v = classify([
        _run(60, "6" * 40, "failure", 10, "CI quality gate"),
        _run(61, "7" * 40, "success", 20, "L1/L2 synthetic fixtures"),
    ])
    eq("gate-red then l1l2-green salient", [r["databaseId"] for r in v.salient], [60])
    eq("gate-red then l1l2-green shadowed", v.shadowed, [])
    eq("l1l2 green counted unrelated", [r["databaseId"] for r in v.unrelated_green], [61])

    # 9. the same-workflow rule still holds: gate red then gate green -> shadowed.
    v = classify([
        _run(70, "8" * 40, "failure", 10, "CI quality gate"),
        _run(71, "9" * 40, "success", 20, "CI quality gate"),
    ])
    eq("gate-red then gate-green salient", v.salient, [])
    eq("gate-red then gate-green shadowed", [r["databaseId"] for r in v.shadowed], [70])
    eq("gate green not unrelated", v.unrelated_green, [])

    # 10. the reverse direction: an L1/L2 red is not covered by a green gate.
    v = classify([
        _run(80, "a" * 40, "failure", 10, "L1/L2 synthetic fixtures"),
        _run(81, "b" * 40, "success", 20, "CI quality gate"),
    ])
    eq("l1l2-red then gate-green salient", [r["databaseId"] for r in v.salient], [80])
    eq("l1l2-red then gate-green shadowed", v.shadowed, [])

    # 11. within one workflow, "later" is createdAt; a green only covers older reds.
    v = classify([
        _run(90, "c" * 40, "success", 10, "CI quality gate"),
        _run(91, "d" * 40, "failure", 20, "CI quality gate"),
        _run(92, "e" * 40, "success", 30, "L1/L2 synthetic fixtures"),
    ])
    eq("gate red after gate green is salient", [r["databaseId"] for r in v.salient], [91])
    eq("later l1l2 green unrelated", [r["databaseId"] for r in v.unrelated_green], [92])

    # 12. the recorded 09:04:51 pair (gate failure, L1/L2 success, same second,
    #     higher L1/L2 databaseId) is 1 salient, not shadowed.
    import os
    fixture = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "main_watch-crossworkflow.json")
    pair = json.load(open(fixture, encoding="utf-8"))
    v = classify(pair)
    eq("fixture salient", [r["databaseId"] for r in v.salient], [45005779931])
    eq("fixture shadowed", v.shadowed, [])
    eq("fixture unrelated green", [r["databaseId"] for r in v.unrelated_green], [45005780000])

    print(f"main_watch selftest: OK ({checks} checks)")
    return 0


def replay(path: str) -> int:
    """Walk the history and print every moment the tip run was red.

    Each step classifies the run window that ended at that run (as the
    watchdog would have seen it), so a red that a later green covers is a
    red-tip moment here but not a salient one at the end of the window.
    The window keeps the runs of the tip's own workflow only (M9.64): a
    saved two-workflow list must not let an L1/L2 green cover a gate red.
    """
    runs = json.load(open(path, encoding="utf-8"))
    ordered = sorted(
        runs, key=lambda r: (r.get("createdAt", ""), int(r.get("databaseId", 0)))
    )
    red_tips = []
    for i in range(len(ordered)):
        workflow = ordered[i].get("workflowName", "")
        same = [r for r in ordered[: i + 1] if r.get("workflowName", "") == workflow]
        window = same[-40:]
        v = classify(window)
        tip = same[-1]
        if tip.get("conclusion") in RED:
            red_tips.append((ordered[i]["createdAt"], ordered[i]["headSha"][:8],
                             tip.get("conclusion"), workflow))
    print(f"replay: {len(ordered)} runs, {len(red_tips)} red-tip moments")
    multi = len({r.get("workflowName", "") for r in ordered}) > 1
    for created, sha, conclusion, workflow in red_tips:
        tag = f" [{workflow}]" if multi else ""
        print(f"  {created} {sha} {conclusion}{tag}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="H117: fail on an unaddressed red gate run on main")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--workflow", default="CI quality gate")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--json", dest="json_path", help="write the verdict document (or - for stdout)")
    ap.add_argument("--runs-json", help="read a saved gh run list --json document instead of gh")
    ap.add_argument("--dry-run", action="store_true", help="print issue writes, do not apply")
    ap.add_argument("--replay", metavar="RUNS_JSON", help="list red-tip moments in a run list")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.replay:
        return replay(args.replay)

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
        f"{len(v.unrelated_green)} unrelated green, "
        f"{v.cancelled} cancelled, {v.total} runs"
    )
    return act(v, args)


if __name__ == "__main__":
    sys.exit(main())
