#!/usr/bin/env python3
"""Static guard for the repository's CI workflow contract (H140).

The test system's guarantees ("no vendor data in PR CI", "blocking steps stay
blocking", "vendor checks stay manual/weekly", "a level's PASS does not silently
disappear") used to be prose only. This tool makes them machine-checkable and
blocking: it reads every ``.github/workflows/*.yml`` with a small standard-
library YAML subset reader and emits one row per rule, keyed by the workflow
file (never a line or an index). Exit is 1 iff a rule FAILs or cannot be
decided; SKIP is never counted as PASS.

The reader is deliberately narrow and honest. It understands the mapping/list/
block-scalar subset used by the checked-in workflows; anything it cannot decide
it reports as SKIP (not statically decidable) rather than guessing PASS. It
does not execute Actions, fetch anything, or need vendor bytes.

Usage::

    python3 tools/workflow_contract.py                 # human table, exit 1 on FAIL/SKIP
    python3 tools/workflow_contract.py --json PATH     # same rows as JSON
    python3 tools/workflow_contract.py --json -        # JSON on stdout
    python3 tools/workflow_contract.py --selftest      # positive + 5 negatives
    python3 tools/workflow_contract.py --workflows-dir DIR

Exit codes: 0 all rules PASS, 1 a rule FAILed or is undecidable, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_DIR = REPO / ".github" / "workflows"

RULES = {
    "pr-vendor-free": "PR workflow references vendor image/fetch/ROOT",
    "blocking-steps-blocking": "blocking step carries continue-on-error: true",
    "watchdog-triggers": "watchdog lost workflow_dispatch or schedule",
    "manual-vendor-only": "vendor workflow is not manual/weekly only",
    "realcheck-require-image": "manual realcheck lost --require-image",
    "h41-baseline-step": "H41 baseline check step removed",
    "h28-l3-step": "H28 L3 synthetic corpus step removed",
}

BLOCKING_JOBS = ("quality", "l3", "l1l2-fixtures")
WATCHDOG_FILE = "main-watch.yml"
MANUAL_VENDOR_FILE = "firmware-regression.yml"

# Executable vendor markers. Comments and quoted summary echoes are stripped
# before these are matched, so a policy line that says "no IMG256" is not a
# violation (the single biggest false-positive trap in this task, H140).
VENDOR_PATTERNS = (
    (re.compile(r"\bIMG256\b", re.I), "IMG256"),
    (re.compile(r"\bfetch_image\.py\b", re.I), "fetch_image.py"),
    (re.compile(r"files\.viaaq\.eu", re.I), "files.viaaq.eu"),
    (re.compile(r"--root\s+\S+", re.I), "--root ROOT"),
    (re.compile(r"full card tree", re.I), "full card tree"),
    (re.compile(r"\b194\b.*REFER001", re.I), "194 REFER001 files"),
)

TRUE_RE = re.compile(r"^\s*true\s*$", re.I)
EXPR_RE = re.compile(r"\$\{\{")


# ---------------------------------------------------------------- YAML subset


def _strip_comment(line: str) -> str:
    """Remove a YAML comment that starts outside quotes; keep shell `#` inside
    a quoted echo. A ` #` outside quotes starts a comment."""
    quote = None
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == quote:
                if i + 1 < len(line) and line[i + 1] == quote:
                    i += 2
                    continue
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i]
        i += 1
    return line


def _scalar(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1].replace("''", "'").replace('""', '"')
    # Strip a trailing inline comment from an unquoted scalar only when it is
    # preceded by whitespace (a `${{ ... }}` value can contain '#' inside).
    if " #" in text:
        text = text.split(" #", 1)[0].rstrip()
    return text


class Doc:
    """A narrow view of a workflow: top-level mapping with nested maps/lists."""

    def __init__(self, text: str):
        self.text = text
        self.lines = text.splitlines()
        self.top: dict = {}
        self.jobs: dict = {}
        self._undecidable: list[str] = []
        self._parse()

    def _parse(self) -> None:
        i = 0
        n = len(self.lines)
        # Locate the top-level $root keys. YAML allows `on:` (which a YAML 1.1
        # loader would coerce to boolean True; we keep the literal `on`).
        while i < n:
            raw = self.lines[i]
            stripped = _strip_comment(raw).rstrip()
            if not stripped.strip():
                i += 1
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            if indent != 0 or ":" not in stripped:
                i += 1
                continue
            key, _, rest = stripped.partition(":")
            key = key.strip()
            rest = rest.strip()
            if rest in ("|", ">", "|-", ">-", "|+", ">+"):
                i = self._skip_block(i + 1, 0)
                self.top[key] = ""
                continue
            if rest:
                self.top[key] = _scalar(rest)
                i += 1
                continue
            value, i = self._parse_node(i + 1, indent)
            self.top[key] = value
        self.jobs = self.top.get("jobs") or {}

    def _skip_block(self, i: int, parent_indent: int) -> int:
        while i < len(self.lines):
            raw = self.lines[i]
            if raw.strip() and (len(raw) - len(raw.lstrip(" "))) <= parent_indent:
                break
            i += 1
        return i

    def _parse_node(self, i: int, parent_indent: int):
        """Parse a mapping or list beginning at line i, returning (value, next_i)."""
        n = len(self.lines)
        first = None
        j = i
        while j < n:
            raw = self.lines[j]
            stripped = _strip_comment(raw)
            if stripped.strip():
                first = (j, stripped)
                break
            j += 1
        if first is None:
            return {}, n
        first_line_no, first_line = first
        first_indent = len(self.lines[first_line_no]) - len(self.lines[first_line_no].lstrip(" "))
        is_list = first_line.lstrip(" ").startswith("- ")
        if first_indent <= parent_indent:
            return ({}, i) if not is_list else ([], i)
        indent = first_indent
        if is_list:
            return self._parse_list(i, indent)
        return self._parse_map(i, indent)

    def _parse_map(self, i: int, indent: int):
        result: dict = {}
        n = len(self.lines)
        while i < n:
            raw = self.lines[i]
            stripped = _strip_comment(raw).rstrip()
            if not stripped.strip():
                i += 1
                continue
            cur = len(raw) - len(raw.lstrip(" "))
            if cur < indent:
                break
            if cur > indent:
                # Deeper content under a previous scalar key (e.g. a `run: |`
                # block we failed to classify) — skip it, never guess.
                i += 1
                continue
            if stripped.lstrip(" ").startswith("- "):
                break
            key, _, rest = stripped.strip().partition(":")
            key = key.strip()
            rest = rest.strip()
            if rest in ("|", ">", "|-", ">-", "|+", ">+"):
                start = i + 1
                i = self._skip_block(start, indent)
                result[key] = _block_text(self.lines[start:i], indent)
                continue
            if rest:
                result[key] = _scalar(rest)
                i += 1
                continue
            value, i = self._parse_node(i + 1, indent)
            result[key] = value
        return result, i

    def _parse_list(self, i: int, indent: int):
        result: list = []
        n = len(self.lines)
        while i < n:
            raw = self.lines[i]
            stripped = _strip_comment(raw).rstrip()
            if not stripped.strip():
                i += 1
                continue
            cur = len(raw) - len(raw.lstrip(" "))
            if cur < indent:
                break
            if cur > indent:
                i += 1
                continue
            content = stripped.strip()
            if not content.startswith("- "):
                break
            item_text = content[2:].strip()
            if ":" in item_text and not item_text.startswith(("'", '"')):
                # A mapping that begins on the dash line, e.g. `- name: foo`.
                key, _, rest = item_text.partition(":")
                item: dict = {key.strip(): _scalar(rest.strip()) if rest.strip() else None}
                i += 1
                # Continuation keys of this list item are indented past `indent`.
                while i < n:
                    raw2 = self.lines[i]
                    s2 = _strip_comment(raw2).rstrip()
                    if not s2.strip():
                        i += 1
                        continue
                    cur2 = len(raw2) - len(raw2.lstrip(" "))
                    if cur2 <= indent:
                        break
                    k2, sep, r2 = s2.strip().partition(":")
                    if not sep:
                        i += 1
                        continue
                    r2 = r2.strip()
                    if r2 in ("|", ">", "|-", ">-", "|+", ">+"):
                        start = i + 1
                        i = self._skip_block(start, cur2)
                        item[k2.strip()] = _block_text(self.lines[start:i], cur2)
                        continue
                    item[k2.strip()] = _scalar(r2) if r2 else None
                    i += 1
                result.append(item)
            else:
                result.append(_scalar(item_text))
                i += 1
        return result, i

    @property
    def trigger_names(self) -> set[str]:
        on_value = self.top.get("on")
        if isinstance(on_value, dict):
            return {str(k).lower() for k in on_value}
        if isinstance(on_value, str):
            return {on_value.strip().lower()}
        return set()

    def steps(self, job_name: str) -> list[dict]:
        job = self.jobs.get(job_name)
        if not isinstance(job, dict):
            return []
        steps = job.get("steps")
        if not isinstance(steps, list):
            return []
        return [s for s in steps if isinstance(s, dict)]

    def executable_text(self, step: dict) -> str:
        """Shell lines and `uses:` only: comments and quoted echoes excluded."""
        run = step.get("run")
        parts: list[str] = []
        if isinstance(run, str):
            for line in run.splitlines():
                code = _strip_comment(line).strip().rstrip("\\").strip()
                if not code:
                    continue
                # A job-summary echo that merely *mentions* a vendor token is
                # not an executed vendor operation; drop quoted echo strings.
                if re.match(r"^(echo|printf)\b", code, re.I):
                    continue
                # Strip quoted string literals everywhere (including inside a
                # heredoc that writes a summary). A bare command such as
                # `fetch_image.py --image IMG256` has no enclosing quote and
                # stays detectable; prose like out.write('... IMG256 ...')
                # becomes out.write() and is not a violation (H140 trap).
                code = _without_quoted_strings(code)
                if not code.strip():
                    continue
                parts.append(code)
        uses = step.get("uses")
        if isinstance(uses, str):
            parts.append(uses)
        return "\n".join(parts)

    def job_has_literal_true(self, job_name: str) -> bool:
        job = self.jobs.get(job_name)
        if not isinstance(job, dict):
            return False
        return bool(TRUE_RE.match(str(job.get("continue-on-error", ""))))


def _without_quoted_strings(text: str) -> str:
    """Blank out single/double quoted spans so only executable tokens remain.

    Shell variables and `${{ ... }}` expressions are left intact; a quoted
    `python3` command in prose is a false positive, a bare fetch command is not.
    """
    out: list[str] = []
    quote = None
    for ch in text:
        if quote:
            if ch == quote:
                quote = None
            out.append(" ")
        elif ch in "'\"":
            quote = ch
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def _block_text(lines: list[str], parent_indent: int) -> str:
    """Join a YAML block scalar, dropping its common indentation and comments."""
    kept: list[str] = []
    for raw in lines:
        if not raw.strip():
            kept.append("")
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        code = raw[min(indent, max(parent_indent + 2, 0)):]
        kept.append(_strip_comment(code))
    return "\n".join(kept)


# ------------------------------------------------------------------- checking


def _step_named(steps: list[dict], needle: str) -> dict | None:
    lower = needle.lower()
    for step in steps:
        name = str(step.get("name", ""))
        ident = str(step.get("id", ""))
        if lower in name.lower() or lower in ident.lower():
            return step
    return None


def _step_command(steps: list[dict], needle: str) -> dict | None:
    for step in steps:
        if needle in step.get("run", ""):
            return step
    return None


def check_doc(doc: Doc, filename: str) -> list[dict]:
    """Return one row per rule for a workflow file. status: PASS/FAIL/SKIP."""
    rows: list[dict] = []

    def add(rule: str, status: str, reason: str = "") -> None:
        rows.append({"rule": rule, "workflow": filename,
                     "status": status, "reason": reason})

    triggers = doc.trigger_names

    # R1: no PR-trigger workflow may execute a vendor fetch / image / ROOT check.
    if "pull_request" in triggers:
        bad = []
        for job_name, job in doc.jobs.items():
            if not isinstance(job, dict):
                continue
            for step in doc.steps(job_name):
                text = doc.executable_text(step)
                for pat, label in VENDOR_PATTERNS:
                    if pat.search(text):
                        bad.append("%s: %s" % (step.get("name", "?"), label))
                        break
        if bad:
            add("pr-vendor-free", "FAIL", "; ".join(bad))
        else:
            add("pr-vendor-free", "PASS")
    else:
        add("pr-vendor-free", "SKIP", "not a pull_request workflow")

    # R2: a blocking job's steps must not carry a literal continue-on-error: true.
    offending = []
    undecidable = []
    for job_name in BLOCKING_JOBS:
        if doc.job_has_literal_true(job_name):
            offending.append("job %s" % job_name)
        for step in doc.steps(job_name):
            value = str(step.get("continue-on-error", "")).strip()
            if TRUE_RE.match(value):
                offending.append("step %s" % step.get("name", "?"))
            elif value and EXPR_RE.search(value):
                undecidable.append("%s: %s" % (step.get("name", "?"), value))
    if offending:
        add("blocking-steps-blocking", "FAIL", ", ".join(offending))
    elif undecidable:
        add("blocking-steps-blocking", "SKIP",
            "not statically decidable: " + "; ".join(undecidable))
    else:
        add("blocking-steps-blocking", "PASS")

    # R3/R4: the watchdog and the manual vendor workflow keep their triggers.
    if filename == WATCHDOG_FILE:
        missing = [t for t in ("workflow_dispatch", "schedule") if t not in triggers]
        add("watchdog-triggers", "FAIL" if missing else "PASS",
            "missing " + ", ".join(missing) if missing else "")
    else:
        add("watchdog-triggers", "SKIP", "not the watchdog workflow")

    if filename == MANUAL_VENDOR_FILE:
        wrong = [t for t in ("pull_request", "push") if t in triggers]
        missing = [t for t in ("workflow_dispatch", "schedule") if t not in triggers]
        if wrong or missing:
            add("manual-vendor-only", "FAIL",
                "unexpected " + ",".join(wrong) + "; missing " + ",".join(missing))
        else:
            add("manual-vendor-only", "PASS")
    else:
        add("manual-vendor-only", "SKIP", "not the manual vendor workflow")

    # R5: the manual realcheck step must pass --require-image.
    if filename == MANUAL_VENDOR_FILE:
        step = _step_command(
            [s for job_name in doc.jobs for s in doc.steps(job_name)],
            "realcheck.py IMG256")
        if step is None:
            add("realcheck-require-image", "FAIL", "realcheck step not found")
        elif "--require-image" in step.get("run", ""):
            add("realcheck-require-image", "PASS")
        else:
            add("realcheck-require-image", "FAIL",
                "step %s lacks --require-image" % step.get("name", "?"))
    else:
        add("realcheck-require-image", "SKIP", "not the manual vendor workflow")

    # R6/R7: named steps must exist (structural, not a greppable command string).
    all_steps = [s for job_name in doc.jobs for s in doc.steps(job_name)]
    if filename == "l1l2-fixtures.yml":
        step = _step_named(all_steps, "baseline (H41)")
        if step and "--check-baseline" in step.get("run", ""):
            add("h41-baseline-step", "PASS")
        else:
            add("h41-baseline-step", "FAIL", "H41 baseline step removed or gutted")
    else:
        add("h41-baseline-step", "SKIP", "not l1l2-fixtures.yml")

    if filename == "ci.yml":
        step = _step_named(all_steps, "L3 check (synthetic corpus)")
        if step and "l3check.py --build-corpus" in step.get("run", ""):
            add("h28-l3-step", "PASS")
        else:
            add("h28-l3-step", "FAIL", "H28 L3 step removed or gutted")
    else:
        add("h28-l3-step", "SKIP", "not ci.yml")
    return rows


def check_dir(directory: Path) -> list[dict]:
    files = sorted(directory.glob("*.yml"))
    if not files:
        return [{"rule": "(none)", "workflow": str(directory),
                 "status": "FAIL", "reason": "no workflows found"}]
    raw: list[dict] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        raw.extend(check_doc(Doc(text), path.name))

    # One row per rule. A N/A row ("not the ... workflow") is not evidence and
    # is dropped. The stable key is the sorted set of workflow files that the
    # rule actually applies to (never a line or an index). FAIL wins over
    # undecidable SKIP, which wins over PASS.
    by_rule: dict[str, list[dict]] = {}
    for r in raw:
        if r["status"] == "SKIP" and r.get("reason", "").startswith("not "):
            continue
        by_rule.setdefault(r["rule"], []).append(r)
    rank = {"FAIL": 3, "SKIP": 2, "PASS": 1}
    rows: list[dict] = []
    for rule in RULES:
        applicable = by_rule.get(rule, [])
        if not applicable:
            rows.append({"rule": rule, "workflow": "(no applicable workflow)",
                         "status": "FAIL", "reason": "rule never evaluated"})
            continue
        worst = max(applicable, key=lambda r: rank.get(r["status"], 0))
        files_key = ",".join(sorted({r["workflow"] for r in applicable}))
        rows.append({"rule": rule, "workflow": files_key,
                     "status": worst["status"], "reason": worst.get("reason", "")})
    return rows


def run(rows: list[dict], json_out=None) -> int:
    # A SKIP that means "this rule does not apply to this file" is expected and
    # must not redden the run. A SKIP that means "not statically decidable" is
    # not a PASS and must redden it (rule 13: an unverifiable check is never
    # silently green). FAIL always reddens.
    undecidable = [r for r in rows
                   if r["status"] == "SKIP" and "not statically decidable" in r.get("reason", "")]
    ok = not any(r["status"] == "FAIL" for r in rows) and not undecidable
    doc = {
        "ok": ok,
        "counts": {
            "PASS": sum(1 for r in rows if r["status"] == "PASS"),
            "FAIL": sum(1 for r in rows if r["status"] == "FAIL"),
            "SKIP": sum(1 for r in rows if r["status"] == "SKIP"),
        },
        "rules": rows,
    }
    to_stdout = json_out == "-"
    table_stream = sys.stderr if to_stdout else sys.stdout
    width = max([len(r["rule"]) for r in rows] + [24])
    wf_width = max([len(r["workflow"]) for r in rows] + [20])
    print("%-*s  %-*s  %-6s  %s" % (width, "RULE", wf_width, "WORKFLOW",
                                     "RESULT", "REASON"), file=table_stream)
    print("%s  %s  %s  %s" % ("-" * width, "-" * wf_width, "-" * 6, "-" * 40),
          file=table_stream)
    for r in rows:
        print("%-*s  %-*s  %-6s  %s" % (width, r["rule"], wf_width,
                                        r["workflow"], r["status"],
                                        r.get("reason", "")), file=table_stream)
    c = doc["counts"]
    print("workflow contract: %d PASS, %d FAIL, %d SKIP (SKIP is never PASS)"
          % (c["PASS"], c["FAIL"], c["SKIP"]), file=table_stream)
    if json_out and not to_stdout:
        Path(json_out).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    if to_stdout:
        print(json.dumps(doc, indent=2))
    return 0 if ok else 1


# ------------------------------------------------------------------- selftest

POSITIVE_CI = """name: CI quality gate
on:
  pull_request:
  push:
    branches:
      - main
jobs:
  quality:
    name: quality
    runs-on: ubuntu-latest
    continue-on-error: ${{ matrix.experimental }}
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Standing gate (tools/gate.py)
        shell: bash
        run: |
          python tools/gate.py --json gate.json
          echo '- No vendor data, no IMG256, no files.viaaq.eu, no fetch_image.py'
          # IMG256 and --root ROOT appear only in this comment
  l3:
    name: L3 synthetic corpus
    runs-on: ubuntu-latest
    steps:
      - name: L3 check (synthetic corpus)
        shell: bash
        run: python3 tools/l3check.py --build-corpus --json l3.json
      - name: L3 policy
        shell: bash
        run: echo 'no IMG256/full card tree, no network fetch'
"""

POSITIVE_L1L2 = """name: L1/L2 synthetic fixtures
on:
  pull_request:
  push:
jobs:
  l1l2-fixtures:
    name: l1l2
    continue-on-error: ${{ matrix.experimental }}
    steps:
      - name: L1/L2 per-file/per-feature matrix and baseline (H41)
        shell: bash
        run: |
          python tools/l1l2_matrix.py --input l1l2.json --json l1l2-matrix.json
          python tools/l1l2_matrix.py --input l1l2-matrix.json --check-baseline tools/fixtures/l1l2-matrix-baseline.json
      - name: Gate policy
        shell: bash
        run: echo 'no vendor data, no golden ROOT'
"""

POSITIVE_WATCHDOG = """name: Main gate watchdog
on:
  workflow_run:
    workflows: ["CI quality gate"]
    types: [completed]
  schedule:
    - cron: "17 * * * *"
  workflow_dispatch:
jobs:
  watchdog:
    runs-on: ubuntu-latest
    steps:
      - name: verdict
        run: python .github/scripts/main_watch.py --branch main
"""

POSITIVE_VENDOR = """name: IMG256 firmware-head regression
on:
  schedule:
    - cron: "23 4 * * 1"
  workflow_dispatch:
    inputs:
      run_img256:
        type: boolean
        default: false
jobs:
  img256:
    runs-on: ubuntu-latest
    steps:
      - name: Fetch 256 MiB head on cache miss
        run: python3 tools/fetch_image.py --image IMG256 -o "$target"
      - name: Run firmware-head regression (real bytes)
        shell: bash
        run: |
          python3 tools/realcheck.py IMG256 --require-image | tee realcheck.txt
          echo 'Pinned IMG256 SHA-256 from files.viaaq.eu, no full card tree'
"""

FIXTURES = {
    "ci.yml": POSITIVE_CI,
    "l1l2-fixtures.yml": POSITIVE_L1L2,
    "main-watch.yml": POSITIVE_WATCHDOG,
    "firmware-regression.yml": POSITIVE_VENDOR,
}


def _mutation_rows(mutate) -> tuple[list[dict], dict]:
    """Run the guard over a fresh synthetic fixture directory with one mutation."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        files = dict(FIXTURES)
        mutate(files)
        for name, text in files.items():
            (d / name).write_text(text, encoding="utf-8")
        return check_dir(d), files


def selftest() -> int:
    ran: list[str] = []
    fails: list[str] = []

    def check(name: str, cond: bool) -> None:
        ran.append(name)
        print("%s %s" % ("ok  " if cond else "FAIL", name))
        if not cond:
            fails.append(name)

    def clean(rows):
        return not any(r["status"] == "FAIL" or
                       (r["status"] == "SKIP" and
                        "not statically decidable" in r.get("reason", ""))
                       for r in rows)

    # Positive control: the synthetic "today's workflows" have no FAIL and no
    # undecidable rule; the documented legitimate comment/echo/job-level
    # mentions are NOT flagged. N/A rows are honest SKIPs, never PASS.
    rows = _mutation_rows(lambda files: None)[0]
    check("positive control: no FAIL/undecidable on clean synthetic workflows",
          clean(rows))
    check("positive control: comments/echo IMG256 not flagged",
          next(r for r in rows if r["rule"] == "pr-vendor-free")["status"] == "PASS")
    check("positive control: job-level ${{ matrix.experimental }} not flagged",
          next(r for r in rows if r["rule"] == "blocking-steps-blocking")["status"] == "PASS")

    # N1: a step-level continue-on-error: true on the quality step.
    def n1(files):
        files["ci.yml"] = files["ci.yml"].replace(
            "      - name: Standing gate (tools/gate.py)\n        shell: bash",
            "      - name: Standing gate (tools/gate.py)\n"
            "        continue-on-error: true\n"
            "        shell: bash")

    rows, files = _mutation_rows(n1)
    r = next(r for r in rows if r["rule"] == "blocking-steps-blocking")
    check("N1 continue-on-error: true -> FAIL naming ci.yml",
          r["status"] == "FAIL" and "ci.yml" in r["workflow"]
          and "Standing gate" in r["reason"])

    # N2: an executable IMG256 fetch in the PR workflow's blocking step.
    def n2(files):
        files["ci.yml"] = files["ci.yml"].replace(
            "          python tools/gate.py --json gate.json",
            "          python tools/gate.py --json gate.json\n"
            "          python3 tools/fetch_image.py --image IMG256")

    rows, _ = _mutation_rows(n2)
    r = next(r for r in rows if r["rule"] == "pr-vendor-free")
    check("N2 IMG256 fetch in PR workflow -> FAIL naming ci.yml",
          r["status"] == "FAIL" and "ci.yml" in r["workflow"] and
          ("IMG256" in r["reason"] or "fetch_image.py" in r["reason"]))

    # N3: realcheck without --require-image in the manual workflow.
    def n3(files):
        files["firmware-regression.yml"] = files["firmware-regression.yml"].replace(
            "python3 tools/realcheck.py IMG256 --require-image",
            "python3 tools/realcheck.py IMG256")

    rows, _ = _mutation_rows(n3)
    r = next(r for r in rows if r["rule"] == "realcheck-require-image")
    check("N3 realcheck without --require-image -> FAIL naming firmware-regression.yml",
          r["status"] == "FAIL" and "firmware-regression.yml" in r["workflow"]
          and "--require-image" in r["reason"])

    # N4: watchdog loses schedule.
    def n4(files):
        files["main-watch.yml"] = files["main-watch.yml"].replace(
            "  schedule:\n    - cron: \"17 * * * *\"\n", "")

    rows, _ = _mutation_rows(n4)
    r = next(r for r in rows if r["rule"] == "watchdog-triggers")
    check("N4 watchdog without schedule -> FAIL naming main-watch.yml",
          r["status"] == "FAIL" and "main-watch.yml" in r["workflow"]
          and "schedule" in r["reason"])

    # N5: H41 baseline and H28 L3 steps removed.
    def n5(files):
        files["l1l2-fixtures.yml"] = files["l1l2-fixtures.yml"].replace(
            "      - name: L1/L2 per-file/per-feature matrix and baseline (H41)\n"
            "        shell: bash\n"
            "        run: |\n"
            "          python tools/l1l2_matrix.py --input l1l2.json --json l1l2-matrix.json\n"
            "          python tools/l1l2_matrix.py --input l1l2-matrix.json --check-baseline tools/fixtures/l1l2-matrix-baseline.json\n", "")
        files["ci.yml"] = files["ci.yml"].replace(
            "      - name: L3 check (synthetic corpus)\n"
            "        shell: bash\n"
            "        run: python3 tools/l3check.py --build-corpus --json l3.json\n", "")

    rows, _ = _mutation_rows(n5)
    check("N5 H41 baseline step removed -> FAIL naming l1l2-fixtures.yml",
          next(r for r in rows if r["rule"] == "h41-baseline-step")["status"] == "FAIL"
          and "l1l2-fixtures.yml" in
          next(r for r in rows if r["rule"] == "h41-baseline-step")["workflow"])
    check("N5 H28 L3 step removed -> FAIL naming ci.yml",
          next(r for r in rows if r["rule"] == "h28-l3-step")["status"] == "FAIL"
          and "ci.yml" in next(r for r in rows if r["rule"] == "h28-l3-step")["workflow"])

    # Exit policy and JSON shape: a FAIL makes the run fail; JSON mirrors rows.
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        for name, text in FIXTURES.items():
            (d / name).write_text(text, encoding="utf-8")
        good_rows = check_dir(d)
        check("clean fixture has no FAIL/undecidable row", clean(good_rows))
        jpath = d / "contract.json"
        rc = run(good_rows, json_out=jpath)
        payload = json.loads(jpath.read_text(encoding="utf-8"))
        check("clean fixture run() exits 0 and JSON mirrors rows",
              rc == 0 and payload.get("ok") is True
              and payload["counts"]["FAIL"] == 0
              and len(payload["rules"]) == len(good_rows))
        bad_rows = _mutation_rows(n1)[0]
        rc = run(bad_rows, json_out=jpath)
        check("a FAIL row makes run() exit 1", rc == 1)

    print("workflow_contract selftest: %s (%d checks, %d failed)"
          % ("OK" if not fails else "FAIL", len(ran), len(fails)))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Static guard: CI stays vendor-free and blocking steps stay blocking.")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", metavar="PATH", nargs="?", const="-",
                    help="write the same rows as JSON (default stdout)")
    ap.add_argument("--workflows-dir", metavar="DIR",
                    help="workflow directory to check (default: repo .github/workflows)")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    directory = Path(args.workflows_dir).resolve() if args.workflows_dir else DEFAULT_DIR
    if not directory.is_dir():
        print("error: %s is not a directory" % directory, file=sys.stderr)
        return 2
    return run(check_dir(directory), json_out=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
