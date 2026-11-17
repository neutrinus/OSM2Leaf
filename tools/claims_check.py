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


def check(claims_text, exp_files, run_counts=False, runner=_run_selftest):
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

    return {
        "duplicate_ids": dups,
        "unregistered_proposed": unregistered,
        "bad_annotations": bad_annotations,
        "bad_paths": paths,
        "bad_counts": counts,
        "exp_count_conflicts": exp_counts,
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
    result = check(claims_text, exp_files, run_counts=run_counts)
    genuine = genuine_path_problems(result["bad_paths"])
    path_fail = args.strict and bool(genuine)
    count_fail = args.strict and bool(result["bad_counts"])
    conflict_fail = args.strict and bool(result["exp_count_conflicts"])
    failed = (not result["ok"] or path_fail or count_fail or conflict_fail)
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

    print("claims_check selftest: OK (28 checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
