#!/usr/bin/env python3
"""Check the claim ledger for duplicate IDs, unregistered claims, evidence
paths that do not exist, and selftest counts a claim's own command never prints.

The evidence column is only worth what a reader can re-run. Two mechanical
defects are caught here (H74):

* a backticked ``archive/…`` or ``docs/…`` path anywhere after the first ``;``
  in an evidence cell must resolve from the repository root (``…``/``<…>``
  placeholders are skipped);
* a claim that pins an ``N checks`` or ``N/N`` count and cites a
  ``tools/X.py --selftest`` command must pin the number that command prints at
  the revision the text names (an explicit commit in the evidence, else the
  newest commit that changed the EXP record *and* a tool), not an intermediate
  one and not the record's latest docs-only edit (H78).

The default run stays a fast warning pass over the real ledger (exit 0). The
path rule and the count rule both fail under ``--strict``; ``--count-check`` is
the explicit way to run only the count rule (H78: ``--strict`` used to leave it
off, hiding C-3704 from the standing gate).

``--prose-counts`` is the other direction of the count rule (H92): a claim's
*evidence cell* may quote a count a command prints, and that number goes stale
when a later merge changes the tree. Only three mechanical shapes are re-run,
and only when the quoted command is one of an allowlist:

* a backticked command ending in ``prints N`` (``grep -c`` or ``python3 -c``);
* a claim that says ``stays N`` (the H87 defect: a list that later grew);
* the exact selftest footer ``OK (N checks`` for a tool the cell names.

A prose count with no measurement revision (an explicit commit, or an EXP whose
own history moved a tool — H78's rule) is skipped, never failed. The mode is
off by default; it does not run in the standing gate yet.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAIMS_PATH = REPO_ROOT / "docs" / "research" / "claims.md"
EXP_DIR = REPO_ROOT / "docs" / "experiments"
GITIGNORE_PATH = REPO_ROOT / ".gitignore"

ROW_RE = re.compile(r"^\|\s*(C-\d+)\s*\|")
PROPOSED_RE = re.compile(r"\bpropos", re.IGNORECASE)
CLAIM_ID_RE = re.compile(r"\bC-\d+\b")
WAS_PROPOSED_RE = re.compile(r"Was proposed as (C-\d+) in (EXP-[A-Za-z0-9.\-]+)")
RANGE_RE = re.compile(r"C-(\d+)\s*[…\-–]\s*C?(\d+)")

EXP_TOKEN_RE = re.compile(r"EXP-\d{4}-\d{2}-\d{2}-[A-Za-z0-9.\-]+")
# ``N checks`` / ``N check`` — the pinned selftest size.
CHECK_COUNT_RE = re.compile(r"\b(\d+)\s+checks?\b", re.IGNORECASE)
# ``N/N`` immediately describing checks/self-tests (both halves equal), e.g.
# ``37/37 checks`` or ``37/37 synthetic self-tests`` — not a hit rate (5/7).
RATIO_RE = re.compile(
    r"\b(\d+)\s*/\s*(\d+)\s+(?:synthetic\s+)?(?:checks?|self-?tests?)\b",
    re.IGNORECASE)
# A runnable selftest invocation inside a backticked span.
SELFTEST_RE = re.compile(r"(tools/[\w./-]+\.py)\s+--selftest\b")
# Any repository tool named in the evidence, used when the text says
# `--selftest` but the evidence cell only shows the tool's other command.
TOOL_RE = re.compile(r"tools/[\w./-]+\.py")
# A revision named in the text (an explicit 7–40 hex commit).
REV_RE = re.compile(r"\b([0-9a-f]{7,40})\b")
BACKTICK_RE = re.compile(r"`([^`]+)`")
# A repository path in an evidence span (archive data or a checked-in doc).
EVIDENCE_PATH_RE = re.compile(r"(?:archive|docs)/[^\s`'\"()\[\],;]+")
# A selftest footer's check count, e.g. ``OK (26 checks, 0 failed)`` or
# ``46 checks OK`` — the honest count the tool prints about itself.
FOOTER_RE = re.compile(r"(\d+)\s+checks?\b", re.IGNORECASE)

# --- H92: prose counts ------------------------------------------------------
# ``<backticked command> prints N`` — the evidence cell is the only surface;
# the quoted command is the text before ``prints`` and must be allowlisted.
PROSE_PRINT_RE = re.compile(r"`([^`]+)`\s*(?:,\s*)?prints?\s+`?(\d[\d,]*)", re.I)
# ``stays N`` — a claim asserting a count that another merge can move (H87).
PROSE_STAYS_RE = re.compile(r"\bstays\s+`?(\d[\d,]*)`?", re.I)
# The exact selftest footer a reader re-runs: ``OK (N checks``.
PROSE_OK_RE = re.compile(r"OK\s*\((\d+)\s*checks?", re.I)
# A command shape that is safe to re-run: a file count or a python one-liner.
# A ``git show <rev>:<file> | … | grep -c`` pipeline is a count of a historical
# tree (H91's pinned-C-4101 form) and is safe for the same reason.
PROSE_ALLOW = (
    ("grep -c", re.compile(r"\bgrep\s+-c")),
    ("python3 -c", re.compile(r"\bpython3?\s+-c\b")),
)
# ``archive/…`` inputs in such a command are a vendor-pin (rule 11): a two-way
# probe of some other task's image is not this rule's price.
PROSE_VENDOR_RE = re.compile(r"\barchive/")

TARGET_EXPS = {
    "EXP-2026-11-05-38",
    "EXP-2026-11-05-41",
    "EXP-2026-11-05-42",
    "EXP-2026-11-05-43",
    "EXP-2026-11-05-44",
    "EXP-2026-11-05-46",
    "EXP-2026-11-05-47",
    "EXP-2026-11-05-48",
}


def parse_claim_rows(text):
    rows = []
    for line in text.splitlines():
        m = ROW_RE.match(line)
        if m:
            rows.append((m.group(1), line))
    return rows


def duplicate_ids(rows):
    seen = {}
    for cid, _ in rows:
        seen[cid] = seen.get(cid, 0) + 1
    return sorted(cid for cid, n in seen.items() if n > 1)


def _expand_ids(text):
    ids = set()
    for m in RANGE_RE.finditer(text):
        a, b = int(m.group(1)), int(m.group(2))
        for n in range(a, b + 1):
            ids.add("C-%d" % n)
    ids.update(CLAIM_ID_RE.findall(text))
    return ids


def proposed_ids_in_exp(text):
    ids = set()
    for line in text.splitlines():
        if not PROPOSED_RE.search(line):
            continue
        lower = line.lower()
        idx = lower.find("propos")
        after = line[idx:]
        before = line[:idx]
        found = _expand_ids(after)
        if not found:
            found = _expand_ids(before)
        ids.update(found)
    return ids


def registration_index(claims_text):
    result = {}
    for cid, line in parse_claim_rows(claims_text):
        for m in WAS_PROPOSED_RE.finditer(line):
            pid = m.group(1)
            result.setdefault(pid, []).append(cid)
    return result


def _is_target_exp(name):
    return any(t in name for t in TARGET_EXPS)


def row_cells(line):
    """Cells after the leading ``| C-xxx |``: (text, status, confidence, evidence)."""
    fields = [p.strip() for p in line.split("|")[2:]]
    if fields and fields[-1] == "":
        fields = fields[:-1]
    return fields


def evidence_cell(line):
    cells = row_cells(line)
    return cells[-1] if cells else ""


def claim_text(line):
    cells = row_cells(line)
    return cells[0] if cells else ""


def check_count_token(text):
    """The count a claim pins, or None.

    ``N checks`` is authoritative (the selftest size). ``N/N`` pins a size only
    when both halves are equal and a `checks`/`self-tests` word follows it, so
    a hit rate (5/7) or a forked frequency (16/3) is not a count. A text with
    several distinct `N checks` numbers pins no single size.
    """
    found = [int(m.group(1)) for m in CHECK_COUNT_RE.finditer(text)]
    found = list(dict.fromkeys(found))
    if len(found) == 1:
        return found[0]
    if found:
        return None
    ratios = []
    for m in RATIO_RE.finditer(text):
        if m.group(1) != m.group(2):
            continue
        ratios.append(int(m.group(1)))
    ratios = list(dict.fromkeys(ratios))
    if len(ratios) == 1:
        return int(ratios[0])
    return None


def selftest_tools(evidence):
    """The tool a claim's `--selftest` number belongs to.

    A backticked ``tools/X.py --selftest`` wins. When the text says
    `--selftest` but the evidence cell only shows the tool's other command
    (C-3704), take the sole tool the evidence names.
    """
    tools = []
    for span in BACKTICK_RE.findall(evidence):
        for m in SELFTEST_RE.finditer(span):
            rel = m.group(1)
            if rel not in tools:
                tools.append(rel)
    if tools:
        return tools
    named = []
    for span in BACKTICK_RE.findall(evidence):
        for rel in TOOL_RE.findall(span):
            if rel not in named:
                named.append(rel)
    return named if len(named) == 1 else []


def _skip_placeholder(path):
    return any(ch in path for ch in "…<>*")


def exp_record(exp_name):
    """The EXP record file whose stem is *exp_name* (a ``-slug`` suffix allowed)."""
    if not exp_name or not EXP_DIR.exists():
        return None
    for p in sorted(EXP_DIR.iterdir()):
        if p.suffix == ".md" and (p.stem == exp_name or p.stem.startswith(exp_name + "-")):
            return p
    return None


def evidence_path_class(path):
    """Classify an evidence path (H74 navigator round 1).

    * ``tracked`` — a ``docs/…`` file: must exist.
    * ``vendor-dir`` — under ``archive/images/`` or ``archive/sd-images/``:
      vendor data rule 11 makes fetchable, never committed; exempt.
    * ``vendor-pin`` — a pinned head the repo knows how to fetch (``IMG256`` ->
      ``archive/head256.img``); exempt as a re-creatable reference.
    * ``gd`` — another git-ignored ``archive/…`` file: genuine unless its row
      also names a ``vendor-pin`` sibling (that row's inputs are the same
      fetch story; only a row whose *entire* input set is unpinned is a defect).
    """
    if path.startswith("docs/"):
        return "tracked"
    if path.startswith(("archive/images/", "archive/sd-images/")):
        return "vendor-dir"
    if path in PINNED_HEAD_PATHS:
        return "vendor-pin"
    return "gd"


def _is_git_ignored(path):
    proc = subprocess.run(["git", "check-ignore", "-q", "--", path],
                          cwd=str(REPO_ROOT))
    return proc.returncode == 0


# A pinned head the repository can fetch by key (`fetch_image.py --image IMG256`
# writes the IMG256 head; `archive/head256.img` is its documented local name,
# TODO "Shared inputs"). Add the US head here only when H62 pins a `US256` key.
PINNED_HEAD_PATHS = {"archive/head256.img"}

# A path is additionally ``vendor-pin`` when its evidence cell carries a way to
# re-create it (a fetch command or a pinned SHA-256).
FETCH_RE = re.compile(r"fetch_image|curl\b|head\s+-c|US256|IMG256")
SHA_RE = re.compile(r"\b[0-9a-f]{16,64}\b")


def path_problems(rows):
    """Backticked archive/docs paths after a ';' in the evidence cell.

    * a ``docs/…`` path (or a checked-in file) must exist;
    * ``archive/images/**`` / ``archive/sd-images/**`` and the pinned
      ``archive/head256.img`` are exempt (vendor data / a re-creatable head);
    * a git-ignored ``archive/…`` file is exempt when its cell names a fetch
      command or a pinned SHA, or when the same row names a pinned head;
    * otherwise a missing git-ignored path is a genuine defect.
    A ``…``/``<…>`` placeholder is skipped; a repeated ``(id, path)`` once.
    """
    problems = []
    for cid, line in rows:
        ev = evidence_cell(line)
        if ";" not in ev:
            continue
        tail = ev.split(";", 1)[1]
        has_pin = bool(FETCH_RE.search(tail) or SHA_RE.search(tail))
        spans = []
        seen = set()
        for span in BACKTICK_RE.findall(tail):
            for raw in EVIDENCE_PATH_RE.findall(span):
                path = re.sub(r":\d+$", "", raw.rstrip(".,;:'\""))
                if _skip_placeholder(path) or (cid, path) in seen:
                    continue
                seen.add((cid, path))
                spans.append(path)
        classes = {p: evidence_path_class(p) for p in spans}
        row_has_pinned = any(c == "vendor-pin" for c in classes.values())
        for path in spans:
            cls = classes[path]
            if (REPO_ROOT / path).exists():
                continue
            if cls == "vendor-dir":
                problems.append({"id": cid, "path": path, "kind": "vendor-dir",
                                 "genuine": False})
                continue
            if cls == "vendor-pin":
                problems.append({"id": cid, "path": path, "kind": "vendor-pin",
                                 "genuine": False})
                continue
            if _is_git_ignored(path) and has_pin:
                problems.append({"id": cid, "path": path, "kind": "vendor-pin",
                                 "genuine": False})
                continue
            if _is_git_ignored(path) and row_has_pinned:
                problems.append({"id": cid, "path": path, "kind": "vendor-sibling",
                                 "genuine": False})
                continue
            problems.append({"id": cid, "path": path, "kind": "gd",
                             "genuine": True})
    return problems


def genuine_path_problems(problems):
    return [p for p in problems if p.get("genuine")]


def _git_bytes(args):
    return subprocess.run(["git", *args], cwd=str(REPO_ROOT), capture_output=True)


def _git(args):
    return subprocess.run(["git", *args], cwd=str(REPO_ROOT),
                          capture_output=True, text=True)


def history_is_shallow(git=None):
    """True when the checkout carries no history to measure a revision against.

    ``actions/checkout`` defaults to ``fetch-depth: 1``; in such a tree
    ``git log -- <EXP>`` lists only the tip, so ``_exp_revision`` would "pin"
    every claim to the tip and report today's tool counts as mismatches
    (H90: 9 false ``COUNT`` lines, all at the tip SHA, and the CI job red on a
    tree whose own tools are green).  A shallow history cannot answer "which
    commit measured this record", so the count rule must skip it, never guess.
    ``git rev-parse --is-shallow-repository`` prints ``true``/``false``
    (git >= 2.15); an unreadable answer is treated as shallow, because guessing
    is what H78 forbids.
    """
    git = git or _git
    out = git(["rev-parse", "--is-shallow-repository"]).stdout.strip().lower()
    if out in ("true", "false"):
        return out == "true"
    gd = git(["rev-parse", "--git-dir"]).stdout.strip()
    if not gd:
        return True
    return os.path.exists(os.path.join(str(REPO_ROOT), gd, "shallow"))


def _explicit_revision(evidence):
    """A commit the evidence text itself names, or None."""
    revs = REV_RE.findall(evidence)
    return revs[0] if len(revs) == 1 else None


def _exp_revision(exp_name, git=None):
    """The newest commit that changed the EXP record *and* a tool, or None.

    The measurement revision is the one where the record and the tool moved
    together: that is what a selftest-size claim describes. A later *docs-only*
    edit to the record (H75's required `Correction` section, an H69 refresh)
    must not re-pin a claim against a tool version the record never measured —
    that was the H78 defect: C-3704 says 26, the M1.27 EXP's record described 26
    at `334f092`, and H75's append moved the file head to `ec58d12`, where the
    tool prints 29. `git log` is newest-first, so the first commit whose diff
    touches both the record and a ``tools/*.py`` file is the measured one; a
    record with no such commit (an EXP that only quoted earlier runs) has no
    measurement revision and is skipped, never measured at the working tree.
    """
    path = exp_record(exp_name)
    if path is None:
        return None
    git = git or _git
    rel = path.relative_to(REPO_ROOT)
    for commit in git(["log", "--format=%H", "--", str(rel)]).stdout.split():
        changed = git(["diff-tree", "--no-commit-id", "--name-only", "-r",
                       "--root", commit]).stdout.split("\n")
        if any(f.startswith("tools/") and f.endswith(".py") for f in changed):
            return commit
    return None


def _pinned_revision(evidence, exp_name):
    return _explicit_revision(evidence) or _exp_revision(exp_name)


def _parse_footer(stdout):
    """The check count a selftest footer states, or None.

    Prefer a line that is about the selftest (``… selftest: OK (26 checks, 0
    failed)`` or ``cerom selftest: 46 checks OK``); take the last such line.
    """
    for line in reversed(stdout.splitlines()):
        low = line.lower()
        if "checks" in low and ("selftest" in low or "ok" in low or "failed" in low
                                or "passed" in low):
            m = FOOTER_RE.search(line)
            if m:
                return int(m.group(1))
    return None


def _run_selftest(tool_rel, rev=None):
    """Run *tool_rel* `--selftest` and return (checks, failed) or None.

    ``rev`` runs the tool as of that git revision via ``git archive``; no
    revision runs the working tree file. The count comes from the tool's own
    footer (H74 makes ``fn_match``/``fn_audit`` print it; the rest already do).
    The repository ``tools/`` stays on ``PYTHONPATH`` so helper imports resolve.
    """
    with tempfile.TemporaryDirectory(prefix="claims-count-") as td:
        src = Path(td) / tool_rel
        src.parent.mkdir(parents=True, exist_ok=True)
        if rev:
            arc = _git_bytes(["archive", rev, "tools"])
            if arc.returncode != 0:
                return None
            tar = subprocess.run(["tar", "-x", "-C", td], input=arc.stdout,
                                 capture_output=True)
            if tar.returncode != 0:
                return None
        else:
            origin = REPO_ROOT / tool_rel
            if not origin.exists():
                return None
            src.write_text(origin.read_text(encoding="utf-8"), encoding="utf-8")

        tools_dir = REPO_ROOT / "tools"
        env = dict(os.environ)
        extra = [str(Path(td) / "tools"), str(tools_dir)]
        env["PYTHONPATH"] = os.pathsep.join(
            extra + [env.get("PYTHONPATH", "")]).strip(os.pathsep)
        try:
            proc = subprocess.run([sys.executable, str(src), "--selftest"],
                                  cwd=str(REPO_ROOT), env=env,
                                  capture_output=True, text=True, timeout=300)
        except (subprocess.TimeoutExpired, OSError):
            return None
        n = _parse_footer(proc.stdout)
        if n is None:
            # A revision whose footer predates H74 prints no count; count the
            # per-check `ok` lines instead (the ledger's own positive control
            # against the past merge used this and got 26 for 334f092). A tool
            # whose selftest prints neither a footer count nor `ok` lines is
            # not measurable here and is skipped, never counted as 0.
            n = sum(1 for line in proc.stdout.splitlines() if line.startswith("ok"))
            if n == 0:
                return None
        return (n, 0 if proc.returncode == 0 else 1)


def count_problems(rows, runner=_run_selftest):
    """Claims whose pinned ``N checks`` differs from what the command prints."""
    problems = []
    cache = {}
    for cid, line in rows:
        text = claim_text(line)
        claimed = check_count_token(text)
        if claimed is None:
            continue
        ev = evidence_cell(line)
        if "--selftest" not in text and "--selftest" not in ev:
            continue
        tools = selftest_tools(ev)
        if not tools:
            continue
        exps = EXP_TOKEN_RE.findall(ev) or EXP_TOKEN_RE.findall(text)
        exp_name = exps[0] if exps else ""
        rev = _pinned_revision(ev, exp_name)
        if rev is None and exp_name and exp_record(exp_name) is not None:
            # A real record whose history never moved a tool has no measurement
            # revision. Measuring it at the working tree would pin today's tool
            # to a record that never described it (H78); skip, do not guess.
            continue
        key = (tools[0], rev)
        if key not in cache:
            cache[key] = runner(tools[0], rev)
        got = cache[key]
        if got is None:
            continue
        checks, _failed = got
        if checks != claimed:
            problems.append({"id": cid, "tool": tools[0], "claimed": claimed,
                             "got": checks, "rev": rev or "working tree"})
    return problems


def _prose_allowed(cmd):
    """The allowlist name for a command shape, or None.

    ``grep -c`` and ``python3 -c`` are the two shapes whose whole job is to
    print one count. Anything else (a tool with a fixture, a shell pipeline, a
    vendor image) is not re-run here: the rejected shapes are listed in the
    H92 EXP rather than guessed at.
    """
    if PROSE_VENDOR_RE.search(cmd):
        return None
    for name, rx in PROSE_ALLOW:
        if rx.search(cmd):
            return name
    return None


def _prose_value(text):
    return int(text.replace(",", "").replace(" ", ""))


def _cell_spans(evidence):
    return BACKTICK_RE.findall(evidence)


def prose_count_problems(rows, runner=None, cmd_runner=None):
    """Claims whose evidence quotes a count the tree no longer prints (H92).

    Three shapes, each re-run only when the shape owns a command:

    * ``<backticked command> prints N`` — re-runs an allowlisted ``grep -c`` or
      ``python3 -c`` and compares N with what it prints now;
    * ``stays N`` in the claim text — fails only when the cell also names a
      ``tools/X.py --selftest`` and its footer prints a different N (H87's
      ``US_BUILD_STARTS`` was a Python list, so the footer is its measurement);
    * ``OK (N checks`` in the cell — re-runs that cell's sole
      ``tools/X.py --selftest``.

    A shape with no measurement revision (``_pinned_revision``: an explicit
    commit, else the EXP commit that moved a tool — H78) is skipped, never
    failed. The revision is what makes a quote checkable: without it the
    number could be right for the commit the author had.
    """
    runner = runner or _run_selftest
    cmd_runner = cmd_runner or _run_prose_command
    problems = []
    cache = {}
    for cid, line in rows:
        text = claim_text(line)
        ev = evidence_cell(line)
        spans = _cell_spans(ev)
        selftests = [s for s in spans if SELFTEST_RE.search(s)]
        exp_name = (EXP_TOKEN_RE.findall(ev) or EXP_TOKEN_RE.findall(text) or [""])[0]
        rev = _pinned_revision(ev, exp_name)

        def measure(tool):
            key = (tool, rev)
            if key not in cache:
                cache[key] = runner(tool, rev)
            return cache[key]

        # (1) a quoted command that prints N.
        for m in PROSE_PRINT_RE.finditer(ev):
            cmd, quoted = m.group(1), _prose_value(m.group(2))
            shape = _prose_allowed(cmd)
            if shape is None:
                continue
            if rev is None:
                continue
            got = cmd_runner(cmd)
            if got is None or got == quoted:
                continue
            problems.append({"id": cid, "shape": "prints", "claimed": quoted,
                             "got": got, "rev": rev, "cmd": cmd})

        # (2) `stays N`, the H87 defect. Two mechanical measurements: an
        # allowlisted `grep -c` the cell already quotes (the list that grew),
        # or the cell's own selftest footer when the list lives in a tool.
        # A bare `stays N` with neither is not measurable and stays untouched.
        for m in PROSE_STAYS_RE.finditer(text):
            quoted = _prose_value(m.group(1))
            if rev is None:
                continue
            got = None
            how = None
            for span in spans:
                if _prose_allowed(span) is not None:
                    got = cmd_runner(span)
                    if got is not None:
                        how = ("command", span)
                        break
            if got is None and selftests:
                tool = SELFTEST_RE.search(selftests[0]).group(1)
                measured = measure(tool)
                if measured is not None:
                    got, how = measured[0], ("tool", tool)
            if got is None or got == quoted:
                continue
            problems.append({"id": cid, "shape": "stays", "claimed": quoted,
                             "got": got, "rev": rev, "how": how[0],
                             "detail": how[1]})

        # (3) a selftest footer quoted in the cell.
        ok_here = PROSE_OK_RE.findall(ev)
        if len(set(ok_here)) == 1 and len(selftests) == 1:
            quoted = int(ok_here[0])
            if rev is not None:
                tool = SELFTEST_RE.search(selftests[0]).group(1)
                got = measure(tool)
                if got is not None and got[0] != quoted:
                    problems.append({"id": cid, "shape": "footer",
                                     "claimed": quoted, "got": got[0],
                                     "rev": rev, "tool": tool})
    return problems


def _run_prose_command(cmd):
    """Run one allowlisted command shape; return its first integer or None.

    Only ``grep -c`` and ``python3 -c`` are allowed (``_prose_allowed`` has
    already filtered). ``grep -c`` runs with ``shell=True`` because the quote
    style varies; the text comes from the ledger, so a command substitution is
    a ledger defect, not an input. ``python3 -c`` uses the same interpreter.
    """
    if PROSE_VENDOR_RE.search(cmd):
        return None
    try:
        if re.search(r"\bgrep\s+-c", cmd):
            proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True,
                                  text=True, timeout=60, shell=True)
            first = (proc.stdout or "").split()
            if not first:
                return 0
            return int(first[0].replace(",", ""))
        if re.search(r"\bpython3?\s+-c\b", cmd):
            code = re.sub(r"^.*?python3?\s+-c\s+", "", cmd, count=1)
            if code[:1] in ("'", '"'):
                quote = code[0]
                end = code.find(quote, 1)
                if end < 0:
                    return None
                code = code[1:end]
            proc = subprocess.run([sys.executable, "-c", code],
                                  cwd=str(REPO_ROOT), capture_output=True,
                                  text=True, timeout=60)
            first = (proc.stdout or "").split()
            if not first:
                return None
            return int(first[0].replace(",", ""))
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None
    return None


def exp_count_problems(rows, exp_files):
    """A claim and the EXP it cites must pin the same selftest count.

    An EXP record reproduces a `--selftest` number in its own text; a claim that
    re-quotes a different number for the same tool/record is a transcription
    defect (H74 negative control: C-3704 `26` vs the M1.27 EXP's `22`). The
    check is on text, so it sees the same corpus from any checkout.
    """
    problems = []
    for cid, line in rows:
        text = claim_text(line)
        claimed = check_count_token(text)
        if claimed is None:
            continue
        ev = evidence_cell(line)
        tools = selftest_tools(ev)
        if not tools:
            continue
        exps = EXP_TOKEN_RE.findall(ev) or EXP_TOKEN_RE.findall(text)
        if not exps:
            continue
        exp_name = exps[0]
        et = ""
        for name, body in exp_files.items():
            stem = name[:-3] if name.endswith(".md") else name
            if stem == exp_name or stem.startswith(exp_name + "-"):
                et = body
                break
        if not et:
            continue
        exp_count = check_count_token(et)
        if exp_count is None:
            continue
        exp_tools = set()
        for span in BACKTICK_RE.findall(et):
            exp_tools.update(SELFTEST_RE.findall(span))
        if exp_tools and tools[0] not in exp_tools:
            continue
        if exp_count != claimed:
            problems.append({"id": cid, "tool": tools[0], "claim": claimed,
                             "exp": exp_name, "exp_count": exp_count})
    return problems


def _run_counts(args):
    """The count rule runs under ``--count-check`` and under ``--strict``.

    H78: ``--strict`` used to leave the count rule off, so the only red part of
    the ledger (C-3704) was invisible to the standing gate and H75's Result
    could claim ``count mismatches: 0``. ``--count-check`` stays the explicit,
    fast way to ask for just that rule.
    """
    return bool(args.count_check or args.strict)


def check(claims_text, exp_files, run_counts=False, runner=_run_selftest,
          run_prose=False, prose_runner=None, prose_cmd_runner=None):
    rows = parse_claim_rows(claims_text)
    dups = duplicate_ids(rows)
    reg = registration_index(claims_text)

    unregistered = []
    for name, text in exp_files.items():
        if not _is_target_exp(name):
            continue
        for pid in sorted(proposed_ids_in_exp(text)):
            if pid not in reg or not reg[pid]:
                unregistered.append({"exp": name, "proposed": pid})

    bad_annotations = []
    for m in WAS_PROPOSED_RE.finditer(claims_text):
        pid = m.group(1)
        expname = m.group(2)
        if not any(expname in fn for fn in exp_files):
            bad_annotations.append({"proposed": pid, "exp": expname})

    paths = path_problems(rows)
    counts = count_problems(rows, runner=runner) if run_counts else []
    exp_counts = exp_count_problems(rows, exp_files)
    prose = (prose_count_problems(rows, runner=prose_runner,
                                  cmd_runner=prose_cmd_runner)
             if run_prose else [])

    return {
        "duplicate_ids": dups,
        "unregistered_proposed": unregistered,
        "bad_annotations": bad_annotations,
        "bad_paths": paths,
        "bad_counts": counts,
        "exp_count_conflicts": exp_counts,
        "bad_prose_counts": prose,
        "ok": not dups and not unregistered and not bad_annotations,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="claims_check")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--strict", action="store_true",
                        help="missing evidence paths and (with --count-check) "
                             "count mismatches exit 1")
    parser.add_argument("--count-check", action="store_true",
                        help="run each cited tools/X.py --selftest and compare "
                             "the printed check count with the claim")
    parser.add_argument("--prose-counts", action="store_true",
                        help="re-run the allowlisted command a claim's evidence "
                             "quotes and report a count the tree no longer "
                             "prints (H92; off by default, not in the gate yet)")
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()

    claims_text = CLAIMS_PATH.read_text(encoding="utf-8")
    exp_files = {}
    if EXP_DIR.exists():
        for p in sorted(EXP_DIR.glob("*.md")):
            exp_files[p.name] = p.read_text(encoding="utf-8")

    run_counts = _run_counts(args)
    shallow = run_counts and history_is_shallow()
    if shallow:
        # H90: do not measure a history that is not there. The rule still runs
        # on any full checkout; here it says so instead of printing 9 false
        # COUNT lines. This is a printed skip, never a quiet "0 mismatches".
        run_counts = False
    # H92: a shallow history has no measurement revision either, so the prose
    # rule would skip every row; say so instead of printing a false "0".
    run_prose = bool(args.prose_counts)
    prose_skip = run_prose and history_is_shallow()
    if prose_skip:
        run_prose = False
    result = check(claims_text, exp_files, run_counts=run_counts,
                   run_prose=run_prose)
    genuine = genuine_path_problems(result["bad_paths"])
    path_fail = args.strict and bool(genuine)
    count_fail = args.strict and bool(result["bad_counts"])
    conflict_fail = args.strict and bool(result["exp_count_conflicts"])
    prose_fail = bool(args.prose_counts and result["bad_prose_counts"])
    failed = (not result["ok"] or path_fail or count_fail or conflict_fail
              or prose_fail)
    if args.json:
        result["genuine_paths"] = genuine
        result["strict_failed"] = failed
        print(json.dumps(result, indent=2))
    else:
        print("duplicate claim IDs: %d" % len(result["duplicate_ids"]))
        if result["duplicate_ids"]:
            for cid in result["duplicate_ids"]:
                print("  DUP %s" % cid)
        print("unregistered proposed claims: %d" % len(result["unregistered_proposed"]))
        for u in result["unregistered_proposed"]:
            print("  UNREG %s in %s" % (u["proposed"], u["exp"]))
        print("bad annotations: %d" % len(result["bad_annotations"]))
        for b in result["bad_annotations"]:
            print("  BAD %s -> %s" % (b["proposed"], b["exp"]))
        print("genuine missing evidence paths: %d" % len(genuine))
        for p in genuine:
            print("  MISSING %s %s" % (p["id"], p["path"]))
        exempt = [p for p in result["bad_paths"] if not p.get("genuine")]
        print("exempt vendor references: %d" % len(exempt))
        for p in exempt:
            print("  EXEMPT %s %s (%s)" % (p["id"], p["path"], p["kind"]))
        if shallow:
            print("count check: skipped (shallow clone; fetch the full history "
                  "to run it)")
        elif run_counts:
            print("count mismatches: %d" % len(result["bad_counts"]))
            for c in result["bad_counts"]:
                print("  COUNT %s claims %d, %s prints %d (%s)"
                      % (c["id"], c["claimed"], c["tool"], c["got"], c["rev"]))
        else:
            print("count check: off (--count-check)")
        print("claim/EXP count conflicts: %d" % len(result["exp_count_conflicts"]))
        for c in result["exp_count_conflicts"]:
            print("  CONFLICT %s claims %d, %s quotes %d (%s)"
                  % (c["id"], c["claim"], c["tool"], c["exp_count"], c["exp"]))
        if prose_skip:
            print("prose count check: skipped (shallow clone; fetch the full "
                  "history to run it)")
        elif run_prose:
            print("stale prose counts: %d" % len(result["bad_prose_counts"]))
            for c in result["bad_prose_counts"]:
                if c["shape"] == "prints":
                    print("  STALE COUNT %s: claims %d, command prints %d (%s)"
                          % (c["id"], c["claimed"], c["got"], c["rev"]))
                elif c["shape"] == "stays":
                    where = ("the quoted command" if c["how"] == "command"
                             else c["detail"])
                    print("  STALE COUNT %s: claims %d, %s prints %d (%s)"
                          % (c["id"], c["claimed"], where, c["got"],
                             c["rev"]))
                else:
                    print("  STALE COUNT %s: claims %d, %s footer prints %d (%s)"
                          % (c["id"], c["claimed"], c["tool"], c["got"],
                             c["rev"]))
        else:
            print("prose count check: off (--prose-counts)")
        print("claims_check: OK" if not failed else "claims_check: FAILED")
    return 0 if not failed else 1


def _stub_runner(table):
    def runner(tool_rel, rev=None):
        return table.get((tool_rel, rev))
    return runner


def run_selftest():
    text = "| C-1 | x | VERIFIED | H | ev |\n| C-1 | y | VERIFIED | H | ev |\n| C-2 | z | VERIFIED | H | ev |\n"
    rows = parse_claim_rows(text)
    assert len(rows) == 3
    assert duplicate_ids(rows) == ["C-1"]

    claims = "| C-10 | c | VERIFIED | H | ev; Was proposed as C-5 in EXP-2026-11-05-38 |\n"
    exps = {"EXP-2026-11-05-38-foo.md": "- **Claims:** C-5 (proposed)\n"}
    r = check(claims, exps)
    assert r["ok"], r
    assert r["duplicate_ids"] == []
    assert r["unregistered_proposed"] == []

    claims2 = "| C-10 | c | VERIFIED | H | ev |\n"
    exps2 = {"EXP-2026-11-05-38-bar.md": "- **Claims:** C-7 (proposed)\n"}
    r2 = check(claims2, exps2)
    assert not r2["ok"]
    assert r2["unregistered_proposed"] == [{"exp": "EXP-2026-11-05-38-bar.md", "proposed": "C-7"}]

    claims3 = "| C-10 | c | VERIFIED | H | ev; Was proposed as C-5 in EXP-missing |\n"
    exps3 = {}
    r3 = check(claims3, exps3)
    assert not r3["ok"]
    assert r3["bad_annotations"]

    # --- H74: count rule ---------------------------------------------------
    # (a) a claim that pins 22 while its --selftest prints 26 fails.
    disagree = ("| C-9001 | The tool runs 22 checks in `tools/stub.py --selftest`. "
                "| VERIFIED (tool) | H | EXP-2026-11-16-H74-fixture; "
                "`python3 tools/stub.py --selftest` |\n")
    exps_fixture = {"EXP-2026-11-16-H74-fixture.md": "`fn_match.py --selftest`: 22 checks\n"}
    r4 = check(disagree, exps_fixture, run_counts=True,
               runner=_stub_runner({("tools/stub.py", None): (26, 0)}))
    assert [c["id"] for c in r4["bad_counts"]] == ["C-9001"], r4["bad_counts"]
    assert r4["bad_counts"][0]["claimed"] == 22 and r4["bad_counts"][0]["got"] == 26

    # (b) the same shape with 26 against a 26-check command passes.
    agree = disagree.replace("22 checks", "26 checks")
    r5 = check(agree, exps_fixture, run_counts=True,
               runner=_stub_runner({("tools/stub.py", None): (26, 0)}))
    assert r5["bad_counts"] == [], r5["bad_counts"]

    # (b2) the pinned revision is what is measured, not the working tree: a
    # claim pinning the M1.27 EXP's 22 against `334f092` names the 26 the tool
    # prints at that commit (the 22 belongs to the intermediate 92550d6).
    pinned = ("| C-9002 | `fn_match --selftest` is 22 checks at commit `334f092`. "
              "| VERIFIED (tool) | H | EXP-2026-11-16-H74-fixture; "
              "`python3 tools/fn_match.py --selftest` at `334f092` |\n")
    exps_pin = {"EXP-2026-11-16-H74-fixture.md":
                "`fn_match.py --selftest`: 22 checks at 334f092\n"}
    r6 = check(pinned, exps_pin, run_counts=True,
               runner=_stub_runner({("tools/fn_match.py", "334f092"): (26, 0)}))
    assert [c["id"] for c in r6["bad_counts"]] == ["C-9002"], r6["bad_counts"]
    assert r6["bad_counts"][0]["rev"] == "334f092"
    assert r6["bad_counts"][0]["claimed"] == 22 and r6["bad_counts"][0]["got"] == 26

    # (b4) the same shape against the real tool at the M1.27 merge commit: 22
    # there is 26. Skipped (not failed) only when the commit is not in this
    # clone, so a shallow checkout cannot turn it into a silent pass.
    if _run_selftest("tools/fn_match.py", "334f092") is not None:
        real = check(pinned, exps_pin, run_counts=True)
        assert [c["id"] for c in real["bad_counts"]] == ["C-9002"], real["bad_counts"]
        assert real["bad_counts"][0]["got"] == 26

    # (b3) a lopsided ratio (5/7, a hit rate) is not a pinned check count.
    assert check_count_token("unique: 5/7 rows") is None
    assert check_count_token("37/37 checks") == 37
    assert check_count_token("passes 37/37 synthetic self-tests") == 37
    assert check_count_token("26 checks") == 26
    assert check_count_token("no number here") is None
    # the footer parser reads both H74 and pre-H74 footers.
    assert _parse_footer("fn_match selftest: OK (26 checks, 0 failed)") == 26
    assert _parse_footer("cerom selftest: 46 checks OK (synthetic ROM)") == 46

    # --- H74: path rule ----------------------------------------------------
    # (c) a missing archive/ path after a ';' is named and fails under strict.
    missing = ("| C-9003 | The run reads an image. | VERIFIED (tool) | H | "
               "EXP-2026-11-16-H74-fixture; `python3 tools/fn_match.py --fixture "
               "tools/fixtures/fn_match_eu_us_2011.json --us archive/us256-h74-missing.img "
               "--module Navi.exe` |\n")
    r7 = check(missing, exps_fixture, run_counts=False)
    assert [p["path"] for p in r7["bad_paths"]] == ["archive/us256-h74-missing.img"], r7["bad_paths"]
    assert r7["ok"]  # a path defect is a warning by default, not a base failure

    # (c2) a placeholder or an existing path is skipped/clean; the checked-in
    # fixture path stays green.
    okpath = ("| C-9004 | The run reads a fixture. | VERIFIED (tool) | H | "
              "EXP-2026-11-16-H74-fixture; `python3 tools/fn_match.py --fixture "
              "tools/fixtures/fn_match_eu_us_2011.json --us archive/<image>.img` |\n")
    r8 = check(okpath, exps_fixture, run_counts=False)
    assert r8["bad_paths"] == [], r8["bad_paths"]
    real = ("| C-9005 | The run names a tool. | VERIFIED (tool) | H | "
            "EXP-2026-11-16-H74-fixture; `python3 tools/claims_check.py "
            "--only tools/fn_match.py` |\n")
    r9 = check(real, exps_fixture, run_counts=False)
    assert r9["bad_paths"] == [], r9["bad_paths"]
    # a path with no ';' is not in scope (H61 keeps naming-only rows).
    nosemi = ("| C-9006 | reads `archive/nope.img`. | VERIFIED | H | "
              "`python3 tools/fn_audit.py archive/nope.img` |\n")
    r10 = check(nosemi, {}, run_counts=False)
    assert r10["bad_paths"] == [], r10["bad_paths"]

    # --- H74 round 2: path classes ----------------------------------------
    # (d) archive/images/** and archive/sd-images/** are vendor data rule 11
    # fetches; missing there is exempt, not a defect.
    vdir = ("| C-9008 | The run reads a card image. | VERIFIED (tool) | H | "
            "EXP-2026-11-16-H74-fixture; `python3 tools/cerom.py --image-start "
            "0x200200 archive/images/h74-eu.img romhdr` |\n")
    r11 = check(vdir, exps_fixture, run_counts=False)
    assert [p["kind"] for p in r11["bad_paths"]] == ["vendor-dir"], r11["bad_paths"]
    assert genuine_path_problems(r11["bad_paths"]) == []

    vd = ("| C-9009 | The run reconciles a card. | VERIFIED (tool) | H | "
          "EXP-2026-11-16-H74-fixture; `python3 tools/mkcard.py --from-image "
          "archive/sd-images/h74-us.img --reconcile` |\n")
    r12 = check(vd, exps_fixture, run_counts=False)
    assert [p["kind"] for p in r12["bad_paths"]] == ["vendor-dir"], r12["bad_paths"]

    # (e) the pinned head (fetch_image IMG256) is a re-creatable reference.
    PINNED_HEAD_PATHS.add("archive/h74-pinned-head.img")
    try:
        vpin = ("| C-9010 | The run reads the pinned head. | VERIFIED (tool) | H | "
                "EXP-2026-11-16-H74-fixture; `python3 tools/head_block.py "
                "archive/h74-pinned-head.img` |\n")
        r13 = check(vpin, exps_fixture, run_counts=False)
        assert [p["kind"] for p in r13["bad_paths"]] == ["vendor-pin"], r13["bad_paths"]
        assert genuine_path_problems(r13["bad_paths"]) == []

        # (e2) an unpinned sibling of a pinned head is exempt on the same row.
        vsib = ("| C-9011 | The run diffs two heads. | VERIFIED (tool) | H | "
                "EXP-2026-11-16-H74-fixture; `python3 tools/fn_match.py match "
                "archive/h74-pinned-head.img archive/h74-sibling.img` |\n")
        r14 = check(vsib, exps_fixture, run_counts=False)
        kinds = sorted(p["kind"] for p in r14["bad_paths"])
        assert kinds == ["vendor-pin", "vendor-sibling"], r14["bad_paths"]
        assert genuine_path_problems(r14["bad_paths"]) == []
    finally:
        PINNED_HEAD_PATHS.discard("archive/h74-pinned-head.img")

    # (e3) an unpinned archive/ file with no pinned row is the genuine defect
    # (C-3703 shape: `archive/us256.img`, no H62 fetch yet).
    solo = ("| C-9012 | The run reads an unfetched head. | VERIFIED (tool) | H | "
            "EXP-2026-11-16-H74-fixture; `python3 tools/fn_match.py match "
            "archive/h74-solo.img archive/head256.img` |\n")
    solo = solo.replace(" archive/head256.img`", "`")
    r15 = check(solo, exps_fixture, run_counts=False)
    assert [p["kind"] for p in r15["bad_paths"]] == ["gd"], r15["bad_paths"]
    assert [p["id"] for p in genuine_path_problems(r15["bad_paths"])] == ["C-9012"]

    # --- H74 round 2: claim vs cited EXP count ----------------------------
    # (f) a claim's `26 checks` against an EXP that quotes `22` is a conflict;
    # the same number in both is not.
    conflict = ("| C-9013 | The leaf guard is 26 checks. | VERIFIED (tool) | H | "
                "EXP-2026-11-16-H74-fixture; `python3 tools/stub.py --selftest` |\n")
    exp_conflict = {"EXP-2026-11-16-H74-fixture.md":
                    "`stub.py --selftest`: 22 checks\n"}
    r16 = check(conflict, exp_conflict, run_counts=False)
    assert [c["id"] for c in r16["exp_count_conflicts"]] == ["C-9013"], \
        r16["exp_count_conflicts"]
    assert r16["exp_count_conflicts"][0]["claim"] == 26
    assert r16["exp_count_conflicts"][0]["exp_count"] == 22
    same = conflict.replace("26 checks", "22 checks")
    r17 = check(same, exp_conflict, run_counts=False)
    assert r17["exp_count_conflicts"] == [], r17["exp_count_conflicts"]

    # --- H78: the docs-only-append rule, and --strict runs the counts ------
    # (g) the measurement revision is the newest commit that moved the EXP and
    # a tool together. A later docs-only edit to the same EXP (H75's required
    # `Correction` section) must NOT re-pin the claim: the M1.27 EXP at
    # `334f092` printed 26 and its H75 append at `ec58d12` printed 29, and 26
    # is what C-3704 states. The fake git mirrors that history: EXP+tool at
    # `aaa`, a docs-only append at `bbb`.
    class _Out:
        def __init__(self, text):
            self.stdout = text

    def _fake_git(args):
        if args[0] == "log":
            return _Out("bbb\naaa\n")
        if args[0] == "diff-tree":
            return _Out("docs/experiments/x.md\ntools/stub.py\n" if args[-1] == "aaa"
                        else "docs/experiments/x.md\n")
        return _Out("")

    import builtins
    fake_path = REPO_ROOT / "docs" / "experiments" / "x.md"
    real_exp_record = builtins.__dict__.get("exp_record")
    try:
        app = sys.modules[__name__]
        app.exp_record = lambda name: fake_path
        assert _exp_revision("x", git=_fake_git) == "aaa"
        # a record whose history never moved a tool has no measurement revision
        def _docs_only(args):
            return _Out("bbb\n") if args[0] == "log" else _Out("docs/experiments/x.md\n")
        assert _exp_revision("x", git=_docs_only) is None
    finally:
        app.exp_record = real_exp_record

    # (i) a record that never moved a tool is skipped, not measured at the
    # working tree (H78 navigator): _pinned_revision is None, so no run happens.
    calls = []
    def _counting_runner(tool, rev=None):
        calls.append((tool, rev))
        return (29, 0)
    no_rev = ("| C-9014 | The record never moved the tool. | VERIFIED (tool) | H | "
              "EXP-2026-11-16-H74-fixture; `python3 tools/stub.py --selftest` |\n")
    saved_pin = count_problems.__globals__["_pinned_revision"]
    count_problems.__globals__["_pinned_revision"] = lambda ev, name: None
    try:
        r18 = count_problems(parse_claim_rows(no_rev), runner=_counting_runner)
    finally:
        count_problems.__globals__["_pinned_revision"] = saved_pin
    assert r18 == [], r18
    # the record exists but has no measurement revision, so no run happens and
    # nothing is reported as `rev: working tree`.
    assert calls == [], calls

    # --- H90: a shallow checkout is skipped, not mis-measured ---------------
    def _shallow_git(answer):
        def _g(args):
            if args[:2] == ["rev-parse", "--is-shallow-repository"]:
                return _Out(answer)
            return _Out("")
        return _g
    assert history_is_shallow(_shallow_git("true")) is True
    assert history_is_shallow(_shallow_git("false")) is False
    # git < 2.15 prints nothing for --is-shallow-repository: with no git-dir
    # either, the history is unreadable and is treated as shallow.
    assert history_is_shallow(_shallow_git("")) is True

    # (h) --strict selects the count rule (H78: it used to select nothing).
    class _Args:
        def __init__(self, strict, count):
            self.strict, self.count_check = strict, count
    assert _run_counts(_Args(strict=True, count=False)) is True
    assert _run_counts(_Args(strict=False, count=True)) is True
    assert _run_counts(_Args(strict=False, count=False)) is False

    # --- H92: a prose count the tree no longer prints ----------------------
    # (j) `stays N` with the cell's `grep -c`: the command prints 15 against a
    # claim that says 12 (the exact H87 defect); the same 15 is green, and a
    # row with no measurement revision is skipped, not failed.
    stays_row = ("| C-9101 | `US_BUILD_STARTS` stays `12`. | VERIFIED (tool) | H | "
                 "EXP-2026-11-16-H74-fixture; at `334f092`; "
                 "`grep -c '0x` tools/stub.py` |\n")
    saved_pin = prose_count_problems.__globals__["_pinned_revision"]
    prose_count_problems.__globals__["_pinned_revision"] = lambda ev, name: "334f092"
    try:
        r19 = prose_count_problems(
            parse_claim_rows(stays_row), cmd_runner=lambda cmd: 15)
        assert [p["shape"] for p in r19] == ["stays"], r19
        assert r19[0]["claimed"] == 12 and r19[0]["got"] == 15
        # negative control: the correct count is clean.
        fresh = stays_row.replace("stays `12`", "stays `15`")
        r20 = prose_count_problems(
            parse_claim_rows(fresh), cmd_runner=lambda cmd: 15)
        assert r20 == [], r20
        # a `stays N` measured by a selftest footer instead of a command.
        tool_row = ("| C-9105 | The list stays `12`. | VERIFIED (tool) | H | "
                    "EXP-2026-11-16-H74-fixture; `python3 tools/stub.py --selftest`; "
                    "at `334f092` |\n")
        r20b = prose_count_problems(
            parse_claim_rows(tool_row),
            runner=_stub_runner({("tools/stub.py", "334f092"): (15, 0)}))
        assert [p["shape"] for p in r20b] == ["stays"], r20b
        assert r20b[0]["how"] == "tool" and r20b[0]["got"] == 15
        # a revision-less row is skipped, never failed (H78's rule).
        prose_count_problems.__globals__["_pinned_revision"] = lambda ev, name: None
        r21 = prose_count_problems(
            parse_claim_rows(stays_row), cmd_runner=lambda cmd: 15)
        assert r21 == [], r21
    finally:
        prose_count_problems.__globals__["_pinned_revision"] = saved_pin

    # (k) `<command> prints N`: the command is re-run, so a quoted 13 against a
    # command that now prints 14 is STALE; the allowlist rejects a non-count
    # command; and a command with an `archive/` input is not re-run (rule 11).
    prints_row = ("| C-9102 | The fixture prints 13 rows. | VERIFIED (tool) | H | "
                  "EXP-2026-11-16-H74-fixture; `python3 -c \"print(len('x'))\"` "
                  "prints `13`; at `334f092` |\n")
    prose_count_problems.__globals__["_pinned_revision"] = lambda ev, name: "334f092"
    try:
        r22 = prose_count_problems(
            parse_claim_rows(prints_row),
            cmd_runner=lambda cmd: 14)
        assert [p["shape"] for p in r22] == ["prints"], r22
        assert r22[0]["claimed"] == 13 and r22[0]["got"] == 14
        r23 = prose_count_problems(
            parse_claim_rows(prints_row),
            cmd_runner=lambda cmd: 13)
        assert r23 == [], r23
        # the allowlist is the shape, not the number: a tool invocation with
        # no `grep -c`/`python3 -c` is not re-run, even if it would disagree.
        other = ("| C-9103 | `python3 tools/fn_match.py --fixture x` prints `13`. "
                 "| VERIFIED (tool) | H | EXP-2026-11-16-H74-fixture; "
                 "`python3 tools/fn_match.py --fixture x` prints `13`; at `334f092` |\n")
        r24 = prose_count_problems(
            parse_claim_rows(other), cmd_runner=lambda cmd: 14)
        assert r24 == [], r24
        vendor = prints_row.replace('python3 -c "print(len(\'x\'))"',
                                    'grep -c x archive/head256.img')
        r25 = prose_count_problems(
            parse_claim_rows(vendor), cmd_runner=lambda cmd: 14)
        assert r25 == [], r25
    finally:
        prose_count_problems.__globals__["_pinned_revision"] = saved_pin

    # (l) the exact footer `OK (N checks` in the cell is checked against the
    # cell's sole selftest tool: 29 quoted against a 33-check tool is STALE.
    footer_row = ("| C-9104 | `tools/stub.py --selftest` is quoted below. "
                  "| VERIFIED (tool) | H | EXP-2026-11-16-H74-fixture; "
                  "`python3 tools/stub.py --selftest` prints `OK (29 checks, 0 failed)`; "
                  "at `334f092` |\n")
    prose_count_problems.__globals__["_pinned_revision"] = lambda ev, name: "334f092"
    try:
        r26 = prose_count_problems(
            parse_claim_rows(footer_row),
            runner=_stub_runner({("tools/stub.py", "334f092"): (33, 0)}))
        assert [p["shape"] for p in r26] == ["footer"], r26
        assert r26[0]["claimed"] == 29 and r26[0]["got"] == 33
        r27 = prose_count_problems(
            parse_claim_rows(footer_row.replace("29 checks", "33 checks")),
            runner=_stub_runner({("tools/stub.py", "334f092"): (33, 0)}))
        assert r27 == [], r27
        # no revision -> skipped (`_pinned_revision` is restored above).
        r28 = prose_count_problems(
            parse_claim_rows(footer_row),
            runner=_stub_runner({("tools/stub.py", None): (33, 0)}))
        assert r28 == [], r28
    finally:
        prose_count_problems.__globals__["_pinned_revision"] = saved_pin

    # (n) `<N> at <sha>`: a correct count at the named revision is clean, and a
    # wrong one is measured at that revision, not at HEAD.
    at_row = ("| C-9106 | `grep -c 'x' tools/stub.py` prints `15` at `398db35`. "
              "| VERIFIED (tool) | H | EXP-2026-11-16-H74-fixture; at `398db35`; "
              "`grep -c 'x' tools/stub.py` prints `15` |\n")
    saved_pin = prose_count_problems.__globals__["_pinned_revision"]
    try:
        r31 = prose_count_problems(parse_claim_rows(at_row),
                                   cmd_runner=lambda cmd: 15)
        assert r31 == [], r31
        bad_at = at_row.replace("prints `15`", "prints `12`")
        r32 = prose_count_problems(parse_claim_rows(bad_at),
                                   cmd_runner=lambda cmd: 15)
        assert [p["rev"] for p in r32] == ["398db35"], r32
    finally:
        prose_count_problems.__globals__["_pinned_revision"] = saved_pin

    # (m) the default run does not run the prose rule (`run_prose=False`), and
    # `check()` carries it through with the injected runners.
    r29 = check(stays_row, {"EXP-2026-11-16-H74-fixture.md": "x"},
                run_counts=False, run_prose=False)
    assert r29["bad_prose_counts"] == []
    prose_count_problems.__globals__["_pinned_revision"] = lambda ev, name: "334f092"
    try:
        r30 = check(stays_row, {"EXP-2026-11-16-H74-fixture.md": "x"},
                    run_prose=True,
                    prose_runner=_stub_runner({("tools/stub.py", "334f092"): (15, 0)}))
        assert [p["shape"] for p in r30["bad_prose_counts"]] == ["stays"]
    finally:
        prose_count_problems.__globals__["_pinned_revision"] = saved_pin

    print("claims_check selftest: OK (37 checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
