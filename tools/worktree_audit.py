#!/usr/bin/env python3
"""Audit git worktrees and remote branches for leftovers (H54).

``git worktree list`` grows every parallel-agent session and hides which tree
is a live task and which is a 2026-11-08 leftover.  This tool joins three
cheap read-only sources -- ``git worktree list --porcelain``,
``git for-each-ref`` and the task statuses in ``TODO.md`` -- and prints one row
per non-main worktree and per remote branch that is ahead of ``main``:

    path | kind | commit | age | locked | task | todo status | flag

A row is ``STALE`` when either

* it is a detached tree older than seven days whose commit is an ancestor of
  ``main`` (the work is already on ``main`` and nothing references the tree),
  or
* it is a branch ahead of ``main`` whose task is already ``done``/``blocked``.

Task IDs come from the branch name (``task/h54-...`` -> ``H54``).  A tree or
branch without a task ID in its name is reported as ``UNKNOWN``; the tool
never guesses.  Locked trees are reported but never flagged or removed.

``--prune`` is a dry run: it prints the ``git worktree remove`` commands for
the stale, unlocked trees and deletes nothing.  ``--prune --apply`` runs those
commands.  The tool never deletes a branch and never force-removes a locked
tree.

Everything is standard library; ``--selftest`` builds a throwaway ``git init``
repository, so the check runs in CI with no vendor data and no network.

Usage::

    python3 tools/worktree_audit.py
    python3 tools/worktree_audit.py --json
    python3 tools/worktree_audit.py --prune
    python3 tools/worktree_audit.py --prune --apply
    python3 tools/worktree_audit.py --selftest

Exit codes: ``0`` report written (stale rows are a result, not an error),
``1`` ``--prune --apply`` failed to remove a tree, ``2`` usage or git error.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time

from pathlib import Path

SCHEMA = "osm2leaf.worktree_audit/v1"
DEFAULT_STALE_DAYS = 7.0
DEFAULT_REMOTE = "origin"
DEFAULT_MAIN = "main"

# Branch names carry the task ID as a path segment: task/h54-..., claude/m4.2-...
TASK_IN_BRANCH_RE = re.compile(
    r"(?:^|[/_])(?P<id>[HM]\d+(?:\.\d+[A-Za-z]?)?)(?=[-_/]|$)", re.IGNORECASE
)
DONE_STATUSES = {"done", "blocked"}


class GitError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# git plumbing
# --------------------------------------------------------------------------


def git(repo: Path, *args: str) -> str:
    """Run one git command in *repo* and return stdout (raises GitError)."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed ({proc.returncode}): "
            f"{(proc.stderr or proc.stdout).strip()}"
        )
    return proc.stdout


def git_ok(repo: Path, *args: str) -> int:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    ).returncode


def parse_worktrees(text: str) -> list[dict]:
    """Parse ``git worktree list --porcelain`` into a list of dicts."""
    worktrees: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        if not line.strip():
            if current is not None:
                worktrees.append(current)
                current = None
            continue
        if line.startswith("worktree "):
            if current is not None:
                worktrees.append(current)
            current = {
                "path": line[len("worktree ") :],
                "head": None,
                "branch": None,
                "detached": False,
                "locked": None,
                "prunable": None,
                "bare": False,
            }
            continue
        if current is None:
            continue
        key, _, value = line.partition(" ")
        if key == "HEAD":
            current["head"] = value
        elif key == "branch":
            current["branch"] = value
        elif key == "detached":
            current["detached"] = True
        elif key == "locked":
            current["locked"] = value or "locked"
        elif key == "prunable":
            current["prunable"] = value or "prunable"
        elif key == "bare":
            current["bare"] = True
    if current is not None:
        worktrees.append(current)
    return worktrees


def parse_refs(text: str) -> list[dict]:
    """Parse ``for-each-ref --format='%(refname:short)|%(objectname)|%(committerdate:unix)'``."""
    refs: list[dict] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) < 3:
            continue
        name, commit, epoch = parts[0], parts[1], parts[2]
        try:
            ts = int(epoch)
        except ValueError:
            continue
        refs.append({"name": name, "commit": commit, "timestamp": ts})
    return refs


# --------------------------------------------------------------------------
# TODO.md task statuses
# --------------------------------------------------------------------------


def parse_status(val: str) -> str:
    head = val.split("·")[0].strip().lower()
    for status in ("in progress", "open", "blocked", "done"):
        if head.startswith(status):
            return status
    return head or "UNKNOWN"


def load_task_statuses(todo_path: Path) -> dict[str, str]:
    """Return ``{task_id: status}`` from TODO.md; empty map when absent."""
    try:
        text = todo_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    statuses: dict[str, str] = {}
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import todo_check  # noqa: WPS433 (local, optional import)

        tasks = todo_check.parse_tasks(text)
        for task in tasks:
            statuses[task["id"]] = parse_status(task["fields"].get("Status", ""))
        return statuses
    except Exception:  # pragma: no cover - fallback keeps the audit usable
        pass
    # Fallback: same shape as todo_check for "ID" followed by a Status field.
    current = None
    for line in text.splitlines():
        m = re.match(r"^- \[[ xX]\] \*\*([A-Z][A-Za-z0-9./]*)", line)
        if m:
            current = m.group(1)
            continue
        if current:
            fm = re.match(r"^  - Status:\s*(.*)$", line)
            if fm:
                statuses[current] = parse_status(fm.group(1))
                current = None
    return statuses


# --------------------------------------------------------------------------
# classification
# --------------------------------------------------------------------------


def infer_task(name: str | None) -> str | None:
    """Extract the task ID from a branch name; ``None`` when absent."""
    if not name:
        return None
    m = TASK_IN_BRANCH_RE.search(name)
    return m.group("id").upper() if m else None


def short_branch(ref: str | None) -> str | None:
    if not ref:
        return None
    for prefix in ("refs/heads/", "refs/remotes/"):
        if ref.startswith(prefix):
            ref = ref[len(prefix) :]
            break
    return ref


def strip_remote(name: str, remote: str) -> str:
    prefix = remote + "/"
    return name[len(prefix) :] if name.startswith(prefix) else name


def classify_row(
    *,
    repo: Path,
    kind: str,
    path: str,
    branch: str | None,
    commit: str,
    timestamp: int,
    locked: bool,
    task: str | None,
    task_status: str,
    now: float,
    main_ref: str,
    stale_days: float,
) -> dict:
    age_days = max(0.0, (now - timestamp) / 86400.0)
    row = {
        "kind": kind,
        "path": path,
        "branch": branch,
        "commit": commit,
        "commit_short": commit[:7],
        "age_days": round(age_days, 1),
        "locked": locked,
        "task": task or "UNKNOWN",
        "task_status": task_status,
        "stale": False,
        "reasons": [],
    }
    if locked:
        return row
    if kind == "worktree" and branch is None:
        if age_days > stale_days and git_ok(
            repo, "merge-base", "--is-ancestor", commit, main_ref
        ) == 0:
            row["stale"] = True
            row["reasons"].append(
                f"detached, {age_days:.1f}d old, commit is an ancestor of {main_ref}"
            )
        return row
    if branch is not None:
        ahead = 0
        try:
            ahead = int(
                git(repo, "rev-list", "--count", f"{main_ref}..{commit}").strip()
            )
        except (GitError, ValueError):
            ahead = 0
        row["ahead"] = ahead
        if ahead > 0 and task_status in DONE_STATUSES:
            row["stale"] = True
            row["reasons"].append(
                f"ahead {ahead} of {main_ref}, task {task} is {task_status}"
            )
    return row


def collect(
    repo: Path,
    todo_path: Path,
    *,
    remote: str = DEFAULT_REMOTE,
    stale_days: float = DEFAULT_STALE_DAYS,
    now: float | None = None,
) -> dict:
    """Build the audit document for *repo* without printing anything."""
    repo = repo.resolve()
    now = time.time() if now is None else now
    main_ref = DEFAULT_MAIN
    if git_ok(repo, "rev-parse", "--verify", "--quiet", main_ref) != 0:
        raise GitError(f"main branch '{main_ref}' not found")
    main_commit = git(repo, "rev-parse", main_ref).strip()
    statuses = load_task_statuses(todo_path)

    worktrees = parse_worktrees(git(repo, "worktree", "list", "--porcelain"))
    main_tree = next(
        (w for w in worktrees if short_branch(w.get("branch")) == main_ref), None
    )
    main_path = main_tree["path"] if main_tree else str(repo)

    rows: list[dict] = []
    checked_out_branches: set[str] = set()
    for wt in worktrees:
        branch = short_branch(wt.get("branch"))
        if branch == main_ref:
            continue
        if branch:
            checked_out_branches.add(branch)
        commit = wt.get("head") or ""
        timestamp = 0
        if commit:
            try:
                timestamp = int(
                    git(repo, "show", "-s", "--format=%ct", commit).strip()
                )
            except (GitError, ValueError):
                timestamp = 0
        task = infer_task(branch)
        status = statuses.get(task, "UNKNOWN") if task else "UNKNOWN"
        row = classify_row(
            repo=repo,
            kind="worktree",
            path=wt["path"],
            branch=branch,
            commit=commit,
            timestamp=timestamp,
            locked=bool(wt.get("locked")),
            task=task,
            task_status=status,
            now=now,
            main_ref=main_ref,
            stale_days=stale_days,
        )
        row["detached"] = bool(wt.get("detached")) or branch is None
        row["lock_reason"] = wt.get("locked")
        rows.append(row)

    refs = parse_refs(
        git(
            repo,
            "for-each-ref",
            "--format=%(refname:short)|%(objectname)|%(committerdate:unix)",
            f"refs/remotes/{remote}",
        )
    )
    branches_ahead = 0
    for ref in refs:
        name = ref["name"]
        if name in (remote, f"{remote}/HEAD", f"{remote}/{main_ref}"):
            continue
        if git_ok(repo, "merge-base", "--is-ancestor", ref["commit"], main_ref) == 0:
            continue
        branches_ahead += 1
        local = strip_remote(name, remote)
        if local in checked_out_branches:
            # Already listed as a worktree row; do not double-count it.
            continue
        task = infer_task(local)
        status = statuses.get(task, "UNKNOWN") if task else "UNKNOWN"
        row = classify_row(
            repo=repo,
            kind="branch",
            path=f"({name})",
            branch=local,
            commit=ref["commit"],
            timestamp=ref["timestamp"],
            locked=False,
            task=task,
            task_status=status,
            now=now,
            main_ref=main_ref,
            stale_days=stale_days,
        )
        rows.append(row)

    rows.sort(key=lambda r: (r["kind"], r["path"]))
    stale = [r for r in rows if r["stale"]]
    prune = [
        r
        for r in stale
        if r["kind"] == "worktree" and not r["locked"] and r["path"] != main_path
    ]
    return {
        "schema": SCHEMA,
        "now": int(now),
        "stale_days": stale_days,
        "main": {"branch": main_ref, "commit": main_commit, "path": main_path},
        "counts": {
            "worktrees_non_main": sum(1 for r in rows if r["kind"] == "worktree"),
            "worktrees_locked": sum(
                1 for r in rows if r["kind"] == "worktree" and r["locked"]
            ),
            "branches_ahead": branches_ahead,
            "stale": len(stale),
            "prunable": len(prune),
        },
        "rows": rows,
        "stale_rows": [r["path"] for r in stale],
        "prune_commands": [
            f"git worktree remove -- {shlex.quote(r['path'])}" for r in prune
        ],
    }


# --------------------------------------------------------------------------
# rendering and pruning
# --------------------------------------------------------------------------


def format_row(row: dict) -> str:
    branch = row["branch"] or "detached"
    flag = "STALE" if row["stale"] else ("LOCKED" if row["locked"] else "ok")
    reason = row.get("lock_reason")
    locked = f"locked({reason})" if reason else "-"
    fields = [
        row["path"],
        row["kind"],
        branch,
        row["commit_short"],
        f"{row['age_days']:.1f}d",
        locked,
        row["task"],
        row["task_status"],
        flag,
    ]
    line = " · ".join(fields)
    if row["reasons"]:
        line += " — " + "; ".join(row["reasons"])
    return line


def render(doc: dict) -> str:
    lines = [
        f"main {doc['main']['branch']} {doc['main']['commit'][:7]} "
        f"at {doc['main']['path']}"
    ]
    for row in doc["rows"]:
        lines.append(format_row(row))
    counts = doc["counts"]
    lines.append(
        "counts "
        f"worktrees={counts['worktrees_non_main']} "
        f"locked={counts['worktrees_locked']} "
        f"ahead={counts['branches_ahead']} "
        f"stale={counts['stale']} "
        f"prunable={counts['prunable']}"
    )
    return "\n".join(lines)


def prune(doc: dict, repo: Path, *, apply: bool) -> int:
    commands = doc["prune_commands"]
    if not commands:
        print("prune: nothing to remove (no unlocked stale worktrees)")
        return 0
    print(("prune: running" if apply else "prune: dry run (pass --apply to run)"))
    failed = 0
    for command in commands:
        print(f"  {command}")
        if not apply:
            continue
        args = shlex.split(command)
        # "git worktree remove -- PATH"
        proc = subprocess.run(args, cwd=str(repo), capture_output=True, text=True)
        if proc.returncode != 0:
            failed += 1
            print(
                f"  FAILED ({proc.returncode}): "
                f"{(proc.stderr or proc.stdout).strip()}"
            )
    return 1 if failed else 0


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------


def _git(repo: Path, *args: str, env: dict | None = None) -> None:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"fixture git {' '.join(args)} failed: {proc.stderr or proc.stdout}"
        )


def _commit_file(
    repo: Path, name: str, text: str, message: str, *, age_days: float | None = None
) -> str:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(repo, "add", name)
    env = dict(os.environ)
    if age_days is not None:
        stamp = f"@{int(time.time() - age_days * 86400)} +0000"
        env["GIT_AUTHOR_DATE"] = stamp
        env["GIT_COMMITTER_DATE"] = stamp
    _git(repo, "commit", "-q", "-m", message, env=env)
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def selftest() -> int:
    checks = 0
    with tempfile.TemporaryDirectory(prefix="worktree-audit-") as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        _git(repo, "init", "-q", "-b", DEFAULT_MAIN)
        _git(repo, "config", "user.email", "audit@example.invalid")
        _git(repo, "config", "user.name", "Audit Selftest")
        _git(repo, "config", "commit.gpgsign", "false")

        todo = (
            "# TODO\n\n"
            "- [x] **H1 — active task**\n"
            "  - Status: in progress · Owner: fixture · Critical: no\n"
            "- [ ] **H2 — open task**\n"
            "  - Status: open · Owner: — · Critical: no\n"
            "- [ ] **H3 — blocked task**\n"
            "  - Status: blocked · Owner: — · Critical: no\n"
            "- [x] **H4 — done task**\n"
            "  - Status: done · Owner: — · Critical: no\n"
            "- [x] **H5 — merged task**\n"
            "  - Status: done · Owner: — · Critical: no\n"
        )
        old = _commit_file(repo, "TODO.md", todo, "old base", age_days=10)
        tip = _commit_file(repo, "main.txt", "tip\n", "main tip")

        # Detached, old, ancestor of main -> STALE.
        _git(repo, "worktree", "add", "-q", "--detach", str(Path(tmp) / "wt-stale"), old)
        # Detached, recent -> active.
        _git(repo, "worktree", "add", "-q", "--detach", str(Path(tmp) / "wt-active"), tip)
        # Detached, old, ancestor, locked -> reported, never stale/pruned.
        locked_path = Path(tmp) / "wt-locked"
        _git(repo, "worktree", "add", "-q", "--detach", str(locked_path), old)
        _git(repo, "worktree", "lock", str(locked_path))

        # Local branch ahead of main for a done task -> STALE tree.
        done_branch = Path(tmp) / "wt-done"
        _git(repo, "worktree", "add", "-q", "-b", "task/h4-done", str(done_branch), tip)
        _commit_file(done_branch, "done.txt", "done\n", "done work")
        _git(repo, "update-ref", "refs/remotes/origin/task/h4-done",
             git(repo, "rev-parse", "task/h4-done").strip())
        # Local branch ahead of main for an open task -> active tree.
        open_branch = Path(tmp) / "wt-open"
        _git(repo, "worktree", "add", "-q", "-b", "task/h2-open", str(open_branch), tip)
        _commit_file(open_branch, "open.txt", "open\n", "open work")
        # Old merged branch (not ahead) -> not reported.
        _git(repo, "branch", "task/h5-merged", old)

        # Remote branches that have no worktree: the ahead-branch half.
        _git(repo, "update-ref", "refs/remotes/origin/task/h3-blocked", old)
        blocked_branch = Path(tmp) / "wt-blocked-src"
        _git(repo, "worktree", "add", "-q", "-b", "tmp/h3-work", str(blocked_branch), tip)
        blocked_sha = _commit_file(blocked_branch, "blocked.txt", "b\n", "blocked work")
        _git(repo, "update-ref", "refs/remotes/origin/task/h3-blocked", blocked_sha)
        _git(repo, "worktree", "remove", str(blocked_branch))
        _git(repo, "update-ref", "-d", "refs/heads/tmp/h3-work")
        _git(repo, "update-ref", "refs/remotes/origin/task/h1-active", blocked_sha)
        _git(repo, "update-ref", "refs/remotes/origin/task/h5-merged", old)

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(
                [
                    "--repo",
                    str(repo),
                    "--todo",
                    str(repo / "TODO.md"),
                    "--json",
                ]
            )
        assert rc == 0, rc
        doc = json.loads(out.getvalue())
        def row_key(r: dict) -> tuple[str, str]:
            if r["kind"] == "branch":
                return ("branch", r["branch"])
            return ("worktree", r["path"].rsplit("/", 1)[-1])

        rows = {row_key(r): r for r in doc["rows"]}

        stale = rows[("worktree", "wt-stale")]
        assert stale["stale"] and stale["task"] == "UNKNOWN", stale
        checks += 1
        print("ok   detached 10-day ancestor is STALE with UNKNOWN task")

        active = rows[("worktree", "wt-active")]
        assert not active["stale"] and active["age_days"] < 1, active
        checks += 1
        print("ok   recent detached tree is active")

        locked = rows[("worktree", "wt-locked")]
        assert locked["locked"] and not locked["stale"], locked
        checks += 1
        print("ok   locked tree is reported, never STALE")

        done = rows[("worktree", "wt-done")]
        assert done["stale"] and done["task"] == "H4", done
        checks += 1
        print("ok   tree ahead for a done task is STALE")

        assert ("branch", "task/h4-done") not in rows, rows
        checks += 1
        print("ok   remote branch checked out in a worktree is not double-listed")

        open_row = rows[("worktree", "wt-open")]
        assert not open_row["stale"] and open_row["task"] == "H2", open_row
        checks += 1
        print("ok   tree ahead for an open task is active")

        blocked_row = rows[("branch", "task/h3-blocked")]
        assert blocked_row["stale"] and blocked_row["task"] == "H3", blocked_row
        checks += 1
        print("ok   remote branch ahead for a blocked task is STALE")

        active_branch = rows[("branch", "task/h1-active")]
        assert not active_branch["stale"] and active_branch["task"] == "H1"
        checks += 1
        print("ok   remote branch ahead for an in-progress task is active")

        merged = [
            r
            for r in doc["rows"]
            if r.get("branch") in ("task/h5-merged", "origin/task/h5-merged")
        ]
        assert not merged, doc["rows"]
        checks += 1
        print("ok   merged branch behind main is not listed")

        assert doc["counts"] == {
            "worktrees_non_main": 5,
            "worktrees_locked": 1,
            "branches_ahead": 3,
            "stale": 3,
            "prunable": 2,
        }, doc["counts"]
        checks += 1
        print("ok   counts: 5 trees (1 locked), 3 ahead, 3 stale, 2 prunable")

        expected_prune = sorted(
            [
                f"git worktree remove -- {Path(tmp) / 'wt-stale'}",
                f"git worktree remove -- {Path(tmp) / 'wt-done'}",
            ]
        )
        assert sorted(doc["prune_commands"]) == expected_prune, doc["prune_commands"]
        checks += 1
        print("ok   prune plan names only the unlocked stale trees")

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(
                [
                    "--repo",
                    str(repo),
                    "--todo",
                    str(repo / "TODO.md"),
                    "--prune",
                ]
            )
        assert rc == 0, rc
        assert "dry run" in out.getvalue(), out.getvalue()
        assert (Path(tmp) / "wt-stale").exists()
        checks += 1
        print("ok   --prune dry run prints commands and deletes nothing")

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(
                [
                    "--repo",
                    str(repo),
                    "--todo",
                    str(repo / "TODO.md"),
                    "--prune",
                    "--apply",
                ]
            )
        assert rc == 0, rc
        assert not (Path(tmp) / "wt-stale").exists()
        assert not done_branch.exists()
        assert locked_path.exists() and open_branch.exists()
        checks += 1
        print("ok   --prune --apply removes only the stale trees; locked/active stay")

        branches = subprocess.run(
            ["git", "-C", str(repo), "branch", "--format=%(refname:short)"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        assert "task/h4-done" in branches and "task/h5-merged" in branches
        checks += 1
        print("ok   no branch was deleted by --prune")

    print(f"worktree_audit selftest: OK ({checks} checks)")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit non-main git worktrees and branches ahead of main, joined "
            "with TODO.md task statuses."
        )
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="git repository to audit (default: the repository of this tool)",
    )
    parser.add_argument(
        "--todo",
        type=Path,
        default=None,
        help="TODO.md path (default: REPO/TODO.md)",
    )
    parser.add_argument(
        "--remote",
        default=DEFAULT_REMOTE,
        help="remote whose branches are inspected (default: origin)",
    )
    parser.add_argument(
        "--stale-days",
        type=float,
        default=DEFAULT_STALE_DAYS,
        help="age in days after which a detached ancestor tree is stale "
        f"(default: {DEFAULT_STALE_DAYS:g})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the audit document as JSON instead of the text report",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="print (dry run) git worktree remove for stale unlocked trees",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="with --prune, actually run the removals; never touches branches",
    )
    parser.add_argument("--selftest", action="store_true", help="run the self-test")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.apply and not args.prune:
        parser.error("--apply requires --prune")

    repo = args.repo
    if repo is None:
        try:
            repo = Path(
                git(Path.cwd(), "rev-parse", "--show-toplevel").strip()
            )
        except GitError as exc:
            print(f"worktree_audit: {exc}", file=sys.stderr)
            return 2
    todo = args.todo or (repo / "TODO.md")

    try:
        doc = collect(
            repo,
            todo,
            remote=args.remote,
            stale_days=args.stale_days,
        )
    except GitError as exc:
        print(f"worktree_audit: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(doc, indent=2, sort_keys=True))
    else:
        print(render(doc))

    if args.prune:
        if args.json:
            for command in doc["prune_commands"]:
                print(f"  {command}")
        return prune(doc, repo, apply=args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
