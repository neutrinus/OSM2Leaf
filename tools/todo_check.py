#!/usr/bin/env python3
"""Lint TODO.md: syntax, task fields, and claim-block allocations.

This checks board *structure* (rule 9/14/16 hygiene), not task semantics.
It complements ``claims_check.py`` (which validates ``docs/research/claims.md``).

Firmware/search task shape (rule 14, C-2128/C-2129): any task whose ID starts
with one of M1, M2, M3, M8, M9 (``READER_STREAMS``). Rule 14 requires such tasks
that touch a firmware address/reader/search to carry truthful ``Precheck``,
``Scope`` and ``Stop`` fields before the search starts.

Checks reported as errors (exit 1):
- duplicate task IDs
- duplicate claim ranges allocated in TODO
- malformed ``Claims: C-xxxx–C-yyyy`` values
- a block header (``- [ ] **…`` or ``### **ID…`` heading) that ``TASK_RE``
  cannot parse — it would otherwise be absorbed into the previous block, so a
  dual-ID/comma/bold-only header silently vanishes from every count (H68)
- missing required fields: Status, Owner, Critical, Depends, Goal, Done when,
  Claims
- blocked tasks missing ``Unblock``
- done tasks missing a ``Result:`` line
- checkbox/status contradictions (``[x]`` vs non-done, ``[ ]`` vs done)
- invalid Status / Critical values
- cyclic ``Depends`` references
- with ``--strict``: open/blocked firmware/search tasks missing
  ``Precheck``/``Scope``/``Stop``
- with ``--strict``: a ``blocked`` task whose ``Unblock:`` names a task that is
  already ``done`` or is archived (the rule-15 hole: that re-open can never
  fire) — H125. In default mode the same reference is a warning, so
  ``tools/gate.py`` (non-strict) stays green while the board is repaired.

Warnings (printed, do not fail by default): ``Depends`` references to a
*ghost* ID (in neither the board nor an archive), missing
``Precheck``/``Scope``/``Stop`` on firmware/search tasks (default mode; done
tasks always warn, never error, to avoid retroactive false failures),
actionable/done tasks missing standard fields, and an ``open`` task whose
``Depends``/``Unblock`` says it "cannot be taken" on an ID that is also
``open`` (a chain of open doors; the M3.30 text is the fixture — H125). A
``blocked`` task whose ``Unblock`` names a ``done``/archived task is the same
reference as an ERROR under ``--strict``.

``Depends``/``Unblock`` references are split into three classes (H60):
``archived`` (a ``[x]`` block in ``docs/research/todo-history-*.md`` — H53's
archive pass, informational), ``ghost`` (nowhere — the error case) and
``blocked`` (a live block that is blocked). The summary line prints the counts.
H53 owns the ``--strict`` switch that turns a ghost reference into an error;
without that flag a ghost stays a warning, and a missing archive degrades to a
single ``unknown`` warning, never an error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TODO_PATH = REPO_ROOT / "TODO.md"

TASK_RE = re.compile(
    r"^- \[(?P<chk>[ xX])\] \*\*(?P<id>[A-Z][A-Za-z0-9./]*)(?:\s+[—–-]\s+|\*\*\s+)(?P<title>.+?)\*\*(?:\s.*)?$"
    r"|^- \[(?P<chk2>[ xX])\] \*\*(?P<id2>[A-Z][A-Za-z0-9./]*)(?:\s+[—–-]\s+|\*\*\s+)(?P<title2>.+?)$"
)
# A line that looks like a board block header but that TASK_RE rejects is an
# error (H68): otherwise it is folded into the previous block's body and
# silently disappears from every count. Both the normal ``- [ ] **…`` shape and
# a bold markdown heading (``### **ID — …**``) are headers.
HEADER_PREFIX_RE = re.compile(r"^- \[[ xX]\] \*\*")
HEADING_BOLD_RE = re.compile(r"^#{1,6}\s+\*\*")
FIELD_RE = re.compile(r"^  - (?P<key>[A-Za-z][A-Za-z ]*?):\s*(?P<val>.*)$")
CLAIMS_RANGE_RE = re.compile(r"^C-(?P<a>\d+)[–-]C-(?P<b>\d+)\b")
# Task IDs in this repo: H1, M1.2a, M9.11b, M8.E1b (segments: digits or
# letter-led like E1b/A2, separated by dots).
DEP_ID_RE = re.compile(r"\b((?:H|M)\d+(?:\.[A-Za-z]?\d+[A-Za-z]?)*)\b")
VALID_STATUS = {"open", "in progress", "blocked", "done"}
VALID_CRITICAL = {"yes", "no"}
# Required as first-class data. Owner/Critical live inside the Status line in
# the real TODO format ("Status: open · Owner: — · Critical: yes").
REQUIRED_ALWAYS = ["Status", "Claims"]
REQUIRED_ACTIONABLE = ["Depends", "Goal", "Done when"]  # open/blocked
READER_STREAMS = ("M1", "M2", "M3", "M8", "M9")
HISTORY_GLOB = "todo-history-*.md"
# A ``[x]`` block header in a frozen archive; the same TASK_RE shape minus its
# field body, so a duplicated/malformed archive line stays a non-match rather
# than raising.
# History files also carry prose bold headings ("**Checksums/validation …"),
# so an archived ID must have the board's task-ID shape, not any word.
HISTORY_HEADER_RE = re.compile(
    r"^- \[x\] \*\*((?:H|M)\d+(?:\.[A-Za-z]?\d+[A-Za-z]?)*)\b")


def _archived_ids(history_dir: Path | None = None) -> set[str]:
    """Task IDs that a ``[x]`` block header in ``todo-history-*.md`` names.

    Every frozen archive under ``docs/research/`` is read; a missing directory
    or no file is an empty set, so a fresh checkout keeps today's behaviour.
    """
    root = (Path(history_dir) if history_dir is not None
            else REPO_ROOT / "docs" / "research")
    ids: set[str] = set()
    for path in sorted(root.glob(HISTORY_GLOB)):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            m = HISTORY_HEADER_RE.match(line)
            if m:
                ids.add(m.group(1))
    return ids


def _unparsed_headers(text: str):
    """Return [(lineno, line)] for header-shaped lines TASK_RE cannot parse.

    Checkbox form (``- [ ] **…``) and bold heading form (``### **…**``) are
    both block headers. A heading without a bold ID is a sectional heading and
    is left alone. Fenced blocks are skipped, same as ``parse_tasks``.
    """
    out = []
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if TASK_RE.match(line):
            continue
        if HEADER_PREFIX_RE.match(line) or HEADING_BOLD_RE.match(line):
            out.append((lineno, line))
    return out


def parse_tasks(text: str):
    tasks = []
    current = None
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = TASK_RE.match(line)
        if m:
            if current:
                tasks.append(current)
            gd = m.groupdict()
            current = {
                "lineno": lineno,
                "id": gd.get("id") or gd.get("id2"),
                "title": (gd.get("title") or gd.get("title2") or "").strip(),
                "checkbox": (gd.get("chk") or gd.get("chk2") or " ").lower(),
                "fields": {},
                "raw_fields": {},
                "_field_cont": None,
            }
            continue
        if current:
            fm = FIELD_RE.match(line)
            if fm:
                key = fm.group("key").strip()
                val = fm.group("val").strip()
                current["fields"][key] = val
                current["raw_fields"].setdefault(key, []).append((lineno, val))
                current["_field_cont"] = key
            elif line.startswith("    ") and current.get("_field_cont"):
                # continuation: may carry "· Owner:" / "· Critical:" (M3.11 style)
                cont = line.strip()
                key = current["_field_cont"]
                current["fields"][key] = current["fields"][key] + " " + cont
            elif line.startswith("  - "):
                current["_field_cont"] = None
            elif line and not line.startswith("  ") and not line.startswith("- ["):
                current["_field_cont"] = None
    if current:
        tasks.append(current)
    return tasks


def _parse_claims(val: str):
    """Return (a,b) or None; accept annotations after the range."""
    m = CLAIMS_RANGE_RE.match(val.strip())
    if not m:
        return None
    return int(m.group("a")), int(m.group("b"))


def _parse_status(val: str) -> str:
    head = val.split("·")[0].strip().lower()
    # normalize parenthetical/template variants, keep base token
    for s in ("open", "in progress", "blocked", "done"):
        if head.startswith(s):
            return s
    return head


def _parse_owner_critical(status_val: str):
    owner = critical = None
    for part in status_val.split("·"):
        part = part.strip()
        if part.lower().startswith("owner:"):
            owner = part.split(":", 1)[1].strip()
        elif part.lower().startswith("critical:"):
            critical = part.split(":", 1)[1].strip().lower()
    return owner, critical


def _parse_depends(val: str):
    v = val.strip()
    # Parse declared deps; ignore parenthetical annotations (often contain
    # explanatory task IDs like "(accept facts: M2.x done)" or notes).
    head = v.split("(", 1)[0].strip()
    if head in ("—", "-", "–", "none", "None", ""):
        return []
    return DEP_ID_RE.findall(head)


def _strip_parens(val: str) -> str:
    """Drop parenthetical spans, keeping the text outside them (H125).

    An ``Unblock`` line often carries one annotated token and then a long note
    in parentheses that names examples, e.g. ``**M3.29** — … (M1.2f/M8.E1 are
    superseded)``. Those inside-parenthesis IDs are prose examples, not the
    blocker the task waits on; splitting at the *first* ``(`` instead would
    silently truncate a real one such as ``M4.24 (part b), M4.25 …``. Removing
    only the parenthetical bytes keeps both.
    """
    out = []
    depth = 0
    for ch in val:
        if ch == "(":
            depth += 1
            continue
        if ch == ")":
            if depth:
                depth -= 1
            continue
        if depth == 0:
            out.append(ch)
    return "".join(out)


def _unblock_points_at_done(t, archived_ids, status_of):
    """IDs in a block's ``Unblock:`` that resolve ``done`` or are archived (H125).

    Rule 15 re-opens a blocked task when the task its ``Unblock`` names merges.
    A named ID that is already ``done`` means that re-open can never fire; an
    archived ID means the token can merge again never. Both are the rule-15
    hole that left M3.29 (Unblock M9.53, done) and M4.23 (Unblock M4.25/M4.26,
    archived). Duplicates are collapsed; order follows the line.
    """
    value = t["fields"].get("Unblock") if t["fields"] else None
    if not value:
        return []
    found = []
    seen = set()
    for ref in DEP_ID_RE.findall(_strip_parens(value)):
        if ref in seen:
            continue
        seen.add(ref)
        if status_of.get(ref) == "done":
            found.append((ref, "done"))
        elif ref in archived_ids:
            found.append((ref, "archived"))
    return found


def _open_door_ids(t, status_of):
    """IDs an ``open`` task waits on behind a "cannot be taken" phrase (H125).

    Rule 1 says an open task's ``Depends``/``Unblock`` that names another
    *open* task is an open door onto an open room: neither is takeable until
    the other moves. ``M3.30``'s ``Depends: M3.29 (open). **Follow-on: cannot be
    taken until M3.29 merges done**`` is the fixture. Parenthetical spans are
    stripped (they carry the note, not a second token); duplicates collapse.
    Returns ``[(field, id), ...]`` for the IDs that are themselves still open.
    """
    found = []
    for field in ("Depends", "Unblock"):
        value = t["fields"].get(field) if t["fields"] else None
        if not value or "cannot be taken" not in value.lower():
            continue
        seen = set()
        for ref in DEP_ID_RE.findall(_strip_parens(value)):
            # A Depends continuation that names the task itself (M3.30's whole
            # note does) is not a door onto another room.
            if ref in seen or ref == t["id"]:
                continue
            seen.add(ref)
            if status_of.get(ref) == "open":
                found.append((field, ref))
    return found


def _classify_refs(t, field, known_ids, archived_ids, status_of, counters,
                   warnings):
    """Classify one block's ``Depends``/``Unblock`` IDs (H60).

    A live block's status decides ``blocked``; an archived ID is informational;
    anything else is a ghost. With no archive at all the archived case is
    indistinguishable from a ghost, so it keeps the old ``unknown`` wording and
    is never an error (a fresh checkout must not false-fail).
    """
    value = t["fields"].get(field) if t["fields"] else None
    if not value:
        return
    # A parenthetical annotation carries prose and example IDs (rule 16), so
    # only the declared head is classified; Unblock often has none.
    head = value.split("(", 1)[0].strip()
    if head in ("", "—", "-", "–", "none", "None"):
        return
    for ref in DEP_ID_RE.findall(head):
        where = f"TODO.md:{t['lineno']} {t['id']}: {field}"
        if ref in known_ids:
            if status_of.get(ref) == "blocked":
                counters["blocked"] += 1
                warnings.append(f"{where} references blocked task ID {ref!r}")
            continue
        if ref in archived_ids:
            counters["archived"] += 1
            warnings.append(f"{where} references archived task ID {ref!r}")
            continue
        counters["ghost"] += 1
        if not archived_ids:
            warnings.append(f"{where} references unknown task ID {ref!r}")
        else:
            warnings.append(f"{where} references ghost task ID {ref!r}")


def _find_dep_cycles(tasks, known_ids):
    """Return a list of cycle descriptions (lists of task IDs)."""
    graph = {}
    for t in tasks:
        deps = _parse_depends(t["fields"].get("Depends", "—")) if t["fields"] else []
        graph[t["id"]] = [d for d in deps if d in known_ids]
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in graph}
    stack = []
    cycles = []
    seen_cycles = set()

    def dfs(node):
        color[node] = GRAY
        stack.append(node)
        for nxt in graph.get(node, []):
            if nxt not in color:
                continue
            if color[nxt] == GRAY:
                idx = stack.index(nxt)
                cyc = stack[idx:] + [nxt]
                key = tuple(sorted(cyc[:-1]))
                if key not in seen_cycles:
                    seen_cycles.add(key)
                    cycles.append(cyc)
            elif color[nxt] == WHITE:
                dfs(nxt)
        stack.pop()
        color[node] = BLACK

    for tid in sorted(graph):
        if color[tid] == WHITE:
            dfs(tid)
    return cycles


def check(text: str, *, strict_firmware: bool = False,
          strict_unblock: bool = False, history_dir: Path | None = None):
    tasks = parse_tasks(text)
    errors = []
    warnings = []

    def err(msg, task=None):
        where = f"TODO.md:{task['lineno']} {task['id']}" if task else "TODO.md"
        errors.append(f"{where}: {msg}")
    # Unparsed block headers are errors (H68). A header-shaped line that
    # TASK_RE rejects is not counted as a task, so without this guard it is
    # absorbed into the previous block and vanishes silently. Dual-ID forms
    # (``**A / B —`` or ``**A, B —``) stay illegal on purpose: such a block has
    # one Claims range and cannot be split without the author (PO did so by
    # hand), so the fix is to flag and let the author split, not to guess.
    for lineno, line in _unparsed_headers(text):
        errors.append(
            f"TODO.md:{lineno}: block header not parsed by TASK_RE: {line.strip()}"
        )

    # duplicate IDs
    seen = {}
    for t in tasks:
        seen.setdefault(t["id"], []).append(t["lineno"])
    for tid, lines in sorted(seen.items()):
        if len(tid) and len(lines) > 1:
            errors.append(f"TODO.md: duplicate task ID {tid} at lines {lines}")

    known_ids = set(seen)
    archived_ids = _archived_ids(history_dir)
    status_of = {t["id"]: _parse_status(t["fields"].get("Status", ""))
                 for t in tasks if t["fields"]}
    # H60 counters, printed in the summary so a reader sees the split without
    # reading 46 warning lines.
    dep_classes = {"archived": 0, "ghost": 0, "blocked": 0}
    # H125: (task, field, id, target-status) rows for --fix-list.
    fix_list = []

    # claim ranges
    ranges = []
    for t in tasks:
        cval = t["fields"].get("Claims")
        if cval is None:
            continue
        if cval.strip().lower().startswith("none"):
            continue
        parsed = _parse_claims(cval)
        if parsed is None:
            if "next free block" in cval.lower():
                err("Claims is placeholder 'next free block at claim time'", t)
            else:
                err(f"malformed Claims range: {cval!r}", t)
            continue
        a, b = parsed
        if a > b:
            err(f"Claims range reversed C-{a}-C-{b}", t)
        ranges.append((a, b, t["id"], t["lineno"]))
    for i, (a1, b1, id1, l1) in enumerate(ranges):
        for a2, b2, id2, l2 in ranges[i + 1:]:
            if a1 <= b2 and a2 <= b1:
                errors.append(
                    f"TODO.md: overlapping claim ranges C-{a1}-{b1} ({id1}:{l1}) "
                    f"and C-{a2}-{b2} ({id2}:{l2})")

    for t in tasks:
        f = t["fields"]
        # compact/legacy tasks (M6.10, M7.x, M8.A1/B5 style) don't use the
        # standard "- Key: value" field format; lint what we can.
        compact = not f
        if compact:
            continue
        missing = [k for k in REQUIRED_ALWAYS if k not in f]
        if missing:
            err(f"missing required field(s): {', '.join(missing)}", t)
            continue

        status = _parse_status(f["Status"])
        if status not in VALID_STATUS:
            err(f"invalid Status {status!r} (expected one of {sorted(VALID_STATUS)})", t)

        owner, critical = _parse_owner_critical(f["Status"])
        if owner is None and "Owner" not in f:
            err("missing Owner (in Status line or as field)", t)
        if critical is None and "Critical" not in f:
            crit_src = f.get("Critical", "")
            critical = crit_src.split()[0].strip().lower().rstrip("·") if crit_src else None
        if critical not in VALID_CRITICAL and critical is not None:
            err(f"invalid Critical {critical!r}", t)
        elif critical is None:
            err("missing Critical (in Status line or as field)", t)

        done = status == "done"
        if t["checkbox"] == "x" and not done:
            err(f"checkbox [x] but Status is {status!r}", t)
        if t["checkbox"] == " " and done:
            err(f"checkbox [ ] but Status is done", t)

        if status == "blocked" and "Unblock" not in f:
            err("Status blocked but missing Unblock", t)
        if status == "done" and "Result" not in f:
            err("Status done but missing Result", t)

        if status in ("open", "in progress", "blocked"):
            for k in REQUIRED_ACTIONABLE:
                if k not in f:
                    warnings.append(f"TODO.md:{t['lineno']} {t['id']}: actionable task missing {k}")
        elif status == "done":
            for k in REQUIRED_ACTIONABLE:
                if k not in f:
                    warnings.append(f"TODO.md:{t['lineno']} {t['id']}: done task missing {k}")

        _classify_refs(t, "Depends", known_ids, archived_ids, status_of,
                       dep_classes, warnings)
        _classify_refs(t, "Unblock", known_ids, archived_ids, status_of,
                       dep_classes, warnings)

        # H125: a blocked task whose Unblock names an already-done/archived ID
        # can never be re-opened by rule 15. ERROR under --strict (the rule-15
        # hole that left M3.29 and M4.23); the board repair is M3.36.
        if status == "blocked":
            for ref, target in _unblock_points_at_done(t, archived_ids, status_of):
                fix_list.append((t["id"], "Unblock", ref, target))
                msg = (f"TODO.md:{t['lineno']} {t['id']}: Unblock references "
                       f"{target} task ID {ref!r}")
                if strict_unblock:
                    errors.append(msg)
                else:
                    warnings.append(msg)

        # H125 second clause: an open task whose Unblock/Depends says it
        # "cannot be taken" on an ID that is also open is a chain of open
        # doors (the M3.30 fixture). Always a WARN, never an ERROR: the target
        # may still be legitimately pending, the wording is what is checked.
        if status == "open":
            for field, ref in _open_door_ids(t, status_of):
                warnings.append(
                    f"TODO.md:{t['lineno']} {t['id']}: {field} says 'cannot be "
                    f"taken' on open task ID {ref!r} (open door onto an open room)")

        if any(t["id"].startswith(s) for s in READER_STREAMS):
            for k in ("Precheck", "Scope", "Stop"):
                if k not in f:
                    msg = f"TODO.md:{t['lineno']} {t['id']}: firmware/search task missing {k}"
                    # rule 14: enforceable for open/blocked firmware/search tasks in
                    # --strict mode. Done tasks are never made false-failing
                    # retroactively; default mode reports warnings for legacy hygiene.
                    if strict_firmware and status in ("open", "in progress", "blocked"):
                        errors.append(msg)
                    else:
                        warnings.append(msg)

    for cyc in _find_dep_cycles(tasks, known_ids):
        errors.append(f"TODO.md: cyclic Depends: {' -> '.join(cyc)}")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "tasks": len(tasks),
        "strict_firmware": strict_firmware,
        "dep_classes": dep_classes,
        "archived_ids": len(archived_ids),
        "fix_list": fix_list,
    }


def _git_revision() -> str:
    """The current HEAD SHA, or ``unknown`` when git is unavailable."""
    try:
        import subprocess
        p = subprocess.run(["git", "rev-parse", "HEAD"],
                           cwd=str(REPO_ROOT), capture_output=True, text=True,
                           timeout=30)
        return p.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _error_key(err_msg: str) -> tuple[str, str] | None:
    """Parse ``(task ID, missing field)`` from an error string, or None.

    Only rule-14 firmware errors carry a task and a field name; a structural
    error (duplicate ID, cyclic Depends, …) has no such key and is never
    baselined — a new structural error must always fail.
    """
    m = re.search(r"TODO\.md:\d+ ([A-Z][A-Za-z0-9./]*): "
                  r"firmware/search task missing (\w+)$", err_msg)
    if m:
        return (m.group(1), m.group(2))
    return None


def _load_baseline(path: Path) -> dict:
    """Read a committed baseline JSON; ``{}`` for a missing/empty file."""
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc.get("entries", {})


def _write_baseline(path: Path, entries: dict, revision: str) -> None:
    doc = {
        "note": ("A debt ledger for todo_check --strict (rule-14 firmware "
                 "four-field errors), keyed by (task ID, missing field), "
                 "never by line number (H71/H80).  Not a waiver: a new task "
                 "missing a field still fails on the first PR that adds it."),
        "revision": revision,
        "entries": {f"{tid}|{field}": True for (tid, field) in sorted(entries)},
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("todo", nargs="?", default=str(TODO_PATH), help="TODO.md path")
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--strict",
        action="store_true",
        help="fail on rule-14 violations: open/blocked/in-progress firmware/search tasks (M1/M2/M3/M8/M9) missing Precheck/Scope/Stop; done tasks still warn only",
    )
    p.add_argument(
        "--fix-list",
        action="store_true",
        help="print one 'task / field / id / target-status' row per Unblock "
        "reference to a done/archived task (H125; the rows the board repair "
        "M3.36 acts on)",
    )
    p.add_argument("--baseline", metavar="PATH",
                   help="with --strict: fail only on ERRORs whose (task ID, field) "
                        "is not in this baseline; a baselined ERROR that cleared is "
                        "printed as 'cleared:' and does not fail")
    p.add_argument("--update-baseline", metavar="PATH",
                   help="write the current strict ERROR keys to PATH as the new "
                        "baseline (prints the + / - rows); the file must be staged")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)

    if args.selftest:
        return run_selftest()

    text = Path(args.todo).read_text(encoding="utf-8")
    # The baseline is a ledger of the *strict* ERROR set, so --update-baseline
    # and --baseline imply --strict (H128).
    strict = args.strict or bool(args.baseline) or bool(args.update_baseline)
    if args.baseline or args.update_baseline:
        # The baseline is a ledger of the *rule-14 firmware* ERROR set only;
        # H125's Unblock rows are a separate board repair (M3.36) and must not
        # turn the baseline red (H128 Done-when).
        result = check(text, strict_firmware=True)
    else:
        result = check(text, strict_firmware=args.strict,
                       strict_unblock=args.strict)
    if args.fix_list:
        result = check(text, strict_firmware=args.strict,
                       strict_unblock=True)
        for task, field, ref, target in result["fix_list"]:
            print(f"{task} / {field} / {ref} / {target}")
        return 0 if result["ok"] else 1

    # Baseline (H128): the debt ledger for --strict rule-14 errors.
    current_keys = set()
    for e in result["errors"]:
        k = _error_key(e)
        if k:
            current_keys.add(k)
    if args.update_baseline:
        rev = _git_revision()
        old = set(_load_baseline(Path(args.update_baseline)))
        _write_baseline(Path(args.update_baseline), current_keys, rev)
        added = sorted(current_keys - old)
        removed = sorted(old - current_keys)
        for tid, field in added:
            print(f"  + {tid}|{field}")
        for tid, field in removed:
            print(f"  - {tid}|{field} (cleared)")
        print(f"baseline updated: {len(current_keys)} entries "
              f"({len(added)} added, {len(removed)} cleared) at {rev}")
        return 0
    if args.baseline:
        base = _load_baseline(Path(args.baseline))
        base_keys = {tuple(k.split("|", 1)) for k in base}
        new_keys = sorted(current_keys - base_keys)
        cleared = sorted(base_keys - current_keys)
        # An ERROR is real only if its (task, field) is new; structural errors
        # (no key) are never baselined and always fail.
        structural = [e for e in result["errors"] if _error_key(e) is None]
        failed = bool(new_keys) or bool(structural)
        for tid, field in new_keys:
            print(f"  NEW {tid}|{field}")
        for tid, field in cleared:
            print(f"  cleared: {tid}")
        dc = result["dep_classes"]
        print(
            f"todo_check [strict+baseline]: {result['tasks']} tasks, "
            f"{len(result['errors'])} error(s) over "
            f"{len({k[0] for k in current_keys})} task(s) "
            f"(baseline {len(base_keys)}, new {len(new_keys)}), "
            f"{len(result['warnings'])} warning(s); refs archived "
            f"{dc['archived']} / ghost {dc['ghost']} / blocked {dc['blocked']}"
        )
        for e in structural:
            print(f"  ERROR {e}")
        print("todo_check: FAILED" if failed else "todo_check: OK")
        return 1 if failed else 0

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        mode = " [strict]" if args.strict else ""
        dc = result["dep_classes"]
        print(
            f"todo_check{mode}: {result['tasks']} tasks, {len(result['errors'])} error(s), "
            f"{len(result['warnings'])} warning(s); refs archived {dc['archived']} / "
            f"ghost {dc['ghost']} / blocked {dc['blocked']} "
            f"({result['archived_ids']} archived IDs)"
        )
        for e in result["errors"]:
            print(f"  ERROR {e}")
        for w in result["warnings"]:
            print(f"  WARN  {w}")
        print("todo_check: OK" if result["ok"] else "todo_check: FAILED")
    return 0 if result["ok"] else 1


def run_selftest():
    ok_doc = """# TODO
- [ ] **T1 — one**
  - Status: open · Owner: — · Critical: no
  - Depends: —
  - Goal: g
  - Done when: d
  - Claims: C-100–C-109

- [x] **T2 — two**
  - Status: done · Owner: b · Critical: yes
  - Depends: T1
  - Goal: g
  - Done when: d
  - Claims: C-110–C-119
  - Result: commit abc
"""
    r = check(ok_doc)
    assert r["ok"], r

    dup = ok_doc.replace("**T2 — two**", "**T1 — two**")
    r = check(dup)
    assert not r["ok"] and any("duplicate task ID" in e for e in r["errors"]), r

    overlap = ok_doc.replace("C-110–C-119", "C-105–C-119")
    r = check(overlap)
    assert not r["ok"] and any("overlapping claim ranges" in e for e in r["errors"]), r

    bad_claims = ok_doc.replace("C-100–C-109", "C-100")
    r = check(bad_claims)
    assert not r["ok"] and any("malformed Claims" in e for e in r["errors"]), r

    blocked = """# TODO
- [ ] **M1.1 — b**
  - Status: blocked · Owner: — · Critical: yes
  - Depends: —
  - Goal: g
  - Precheck: p
  - Scope: s
  - Done when: d
  - Stop: st
  - Claims: C-200–C-209
"""
    r = check(blocked)
    assert not r["ok"] and any("missing Unblock" in e for e in r["errors"]), r

    # M1 requires Precheck/Scope/Stop (warnings by default; strict makes
    # open/blocked/in-progress firmware/search violations errors).
    missing_pss = """# TODO
- [ ] **M1.2 — b**
  - Status: open · Owner: — · Critical: yes
  - Depends: —
  - Goal: g
  - Done when: d
  - Claims: C-210–C-219
"""
    r = check(missing_pss)
    assert r["ok"] and any("missing Precheck" in w for w in r["warnings"]), r
    r = check(missing_pss, strict_firmware=True)
    assert not r["ok"] and any("missing Precheck" in e for e in r["errors"]), r

    # done firmware/search tasks warn but never fail retroactively, even strict
    done_missing_pss = """# TODO
- [x] **M9.99 — done legacy**
  - Status: done · Owner: b · Critical: no
  - Depends: —
  - Goal: g
  - Done when: d
  - Claims: C-220–C-229
  - Result: r
"""
    r = check(done_missing_pss, strict_firmware=True)
    assert r["ok"] and any("missing Precheck" in w for w in r["warnings"]), r

    # checkbox/status contradiction
    contra = ok_doc.replace("- [x] **T2 — two**", "- [ ] **T2 — two**")
    r = check(contra)
    assert not r["ok"] and any("checkbox" in e for e in r["errors"]), r

    # unknown depends (warning). H60 renames the default wording to "ghost"
    # whenever an archive exists (as here); a checkout without one says
    # "unknown", so the test accepts either wording and never an error.
    unk = ok_doc.replace("Depends: T1", "Depends: H99")
    r = check(unk)
    assert r["ok"] and any(("ghost task ID 'H99'" in w) or ("unknown task ID 'H99'" in w)
                           for w in r["warnings"]), r

    # cyclic depends
    cycle = """# TODO
- [ ] **H1 — one**
  - Status: open · Owner: — · Critical: no
  - Depends: H2
  - Goal: g
  - Done when: d
  - Claims: C-300–C-309

- [ ] **H2 — two**
  - Status: open · Owner: — · Critical: no
  - Depends: H1
  - Goal: g
  - Done when: d
  - Claims: C-310–C-319
"""
    r = check(cycle)
    assert not r["ok"] and any("cyclic Depends" in e for e in r["errors"]), r

    # H68: a header TASK_RE cannot parse must be an error, never absorbed.
    # Each malformed form is a negative; the well-formed single header is the
    # positive control (it must still parse as one task).
    dual_slash = """# TODO
- [ ] **H1 — base**
  - Status: done · Owner: b · Critical: no
  - Depends: —
  - Goal: g
  - Done when: d
  - Claims: C-400–C-409
  - Result: r
- [ ] **H2 / H3 — dual**
  - Status: open · Owner: — · Critical: no
  - Depends: —
  - Goal: g
  - Done when: d
  - Claims: C-410–C-419
"""
    r = check(dual_slash)
    assert not r["ok"] and any(
        "block header not parsed by TASK_RE" in e and "H2 / H3" in e
        for e in r["errors"]
    ), r
    assert r["tasks"] == 1, r  # the malformed header is not counted, it errors

    dual_comma = dual_slash.replace("**H2 / H3 — dual**", "**H2, H3 — dual**")
    r = check(dual_comma)
    assert not r["ok"] and any(
        "block header not parsed by TASK_RE" in e and "H2, H3" in e
        for e in r["errors"]
    ), r

    no_dash = dual_slash.replace("**H2 / H3 — dual**", "**H2**")
    r = check(no_dash)
    assert not r["ok"] and any(
        "block header not parsed by TASK_RE" in e and "**H2**" in e
        for e in r["errors"]
    ), r

    heading = dual_slash.replace(
        "- [ ] **H2 / H3 — dual**", "### **H2 — heading style**"
    )
    r = check(heading)
    assert not r["ok"] and any(
        "block header not parsed by TASK_RE" in e and "### **H2" in e
        for e in r["errors"]
    ), r

    # positive control: a well-formed single header still parses as one task
    positive = """- [ ] **H1 — t**
  - Status: open · Owner: — · Critical: no
  - Depends: —
  - Goal: g
  - Done when: d
  - Claims: C-420–C-429
"""
    r = check(positive)
    assert r["ok"] and r["tasks"] == 1, r

    # non-bold section headings are not block headers and must not error
    sections = "# TODO\n## H — Housekeeping\n### ID allocation\n" + positive
    r = check(sections)
    assert r["ok"] and r["tasks"] == 1, r

    # --- H60: Depends references split into archived / ghost / blocked ------
    # A temp board that depends on one live, one archived and one ghost ID, plus
    # a live block that is blocked; a temp archive names the archived one.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="todo-h60-") as td:
        hist_dir = Path(td)
        (hist_dir / "todo-history-2099-01-01.md").write_text(
            "- [x] **M9.1 — archived one**\n  - Status: done · Owner: b · Critical: no\n",
            encoding="utf-8")
        board = """# TODO
- [ ] **M1.1 — live**
  - Status: open · Owner: — · Critical: no
  - Depends: —
  - Goal: g
  - Done when: d
  - Claims: C-500–C-509
- [ ] **M1.2 — blocked**
  - Status: blocked · Owner: — · Critical: no
  - Depends: —
  - Goal: g
  - Done when: d
  - Unblock: M1.1
  - Claims: C-510–C-519
- [ ] **M1.3 — refs**
  - Status: open · Owner: — · Critical: no
  - Depends: M1.1, M9.1, H9999
  - Goal: g
  - Done when: d
  - Claims: C-520–C-529
- [ ] **M1.4 — uses a blocked dep**
  - Status: open · Owner: — · Critical: no
  - Depends: M1.2
  - Goal: g
  - Done when: d
  - Claims: C-530–C-539
- [ ] **M1.5 — Unblock names a ghost**
  - Status: blocked · Owner: — · Critical: no
  - Depends: —
  - Goal: g
  - Done when: d
  - Unblock: H9998
  - Claims: C-540–C-549
"""
        r = check(board, history_dir=hist_dir)
        assert r["ok"], r
        # M1.3: 1 archived + 1 ghost; M1.4: 1 blocked; M1.5's Unblock: 1 ghost.
        assert r["dep_classes"] == {"archived": 1, "ghost": 2, "blocked": 1}, r["dep_classes"]
        # An Unblock reference is classified too, and the line names the field.
        assert any("Unblock references ghost task ID 'H9998'" in w
                   for w in r["warnings"]), r["warnings"]
        assert any("archived task ID 'M9.1'" in w for w in r["warnings"]), r["warnings"]
        assert any("ghost task ID 'H9999'" in w for w in r["warnings"]), r["warnings"]
        assert any("blocked task ID 'M1.2'" in w for w in r["warnings"]), r["warnings"]
        # Negative 1: with no archive at all, the archived ID degrades to the old
        # wording and nothing errors (a fresh checkout must not false-fail).
        with tempfile.TemporaryDirectory(prefix="todo-h60-empty-") as empty:
            r2 = check(board, history_dir=Path(empty))
        assert r2["ok"] and r2["archived_ids"] == 0, r2
        assert any("unknown task ID 'M9.1'" in w for w in r2["warnings"]), r2["warnings"]
        assert r2["dep_classes"]["ghost"] == 3, r2["dep_classes"]
        # Negative 2: against the *real* archive set, a genuinely archived ID
        # is classified archived, and the same board with it changed to H9999
        # is classified ghost. This pins the classifier to the repo's own
        # history files, not only to the temp fixture above.
        real_archived = _archived_ids()
        assert real_archived, "no archived IDs found in docs/research/todo-history-*.md"
        probe = sorted(real_archived)[0]
        real_board = ("# TODO\n- [ ] **M9.60 — probe**\n"
                      "  - Status: open · Owner: — · Critical: no\n"
                      f"  - Depends: {probe}\n"
                      "  - Goal: g\n  - Done when: d\n  - Claims: C-540–C-549\n")
        r_a = check(real_board, history_dir=REPO_ROOT / "docs" / "research")
        assert r_a["dep_classes"] == {"archived": 1, "ghost": 0, "blocked": 0}, r_a["dep_classes"]
        ghost_board = real_board.replace(f"Depends: {probe}", "Depends: H9999")
        r_g = check(ghost_board, history_dir=REPO_ROOT / "docs" / "research")
        assert r_g["dep_classes"] == {"archived": 0, "ghost": 1, "blocked": 0}, r_g["dep_classes"]
        assert any("ghost task ID 'H9999'" in w for w in r_g["warnings"]), r_g["warnings"]

    # --- H125: a blocked task whose Unblock names a done/archived task ------
    # Three required cases: done target (ERROR), archived target (ERROR), an
    # open target (no error). H IDs keep the rule-14 firmware check out of the
    # way. A temp archive carries the archived ID; a board with no done/
    # archived Unblock is the exit-0 negative control.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="todo-h125-") as td:
        hist = Path(td)
        (hist / "todo-history-2099-01-01.md").write_text(
            "- [x] **H9 — archived one**\n  - Status: done · Owner: b · Critical: no\n",
            encoding="utf-8")
        h125_board = """# TODO
- [x] **H1 — done target**
  - Status: done · Owner: b · Critical: no
  - Depends: —
  - Goal: g
  - Done when: d
  - Claims: C-600–C-609
  - Result: r
- [ ] **H2 — blocked on a done task**
  - Status: blocked · Owner: — · Critical: no
  - Depends: —
  - Goal: g
  - Done when: d
  - Unblock: H1
  - Claims: C-610–C-619
- [ ] **H3 — blocked on an archived task**
  - Status: blocked · Owner: — · Critical: no
  - Depends: —
  - Goal: g
  - Done when: d
  - Unblock: H9 (archived 2026-11-09)
  - Claims: C-620–C-629
- [ ] **H4 — blocked on an open task**
  - Status: blocked · Owner: — · Critical: no
  - Depends: —
  - Goal: g
  - Done when: d
  - Unblock: H5
  - Claims: C-630–C-639
- [ ] **H5 — open target**
  - Status: open · Owner: — · Critical: no
  - Depends: —
  - Goal: g
  - Done when: d
  - Claims: C-640–C-649
"""
        # Done target -> ERROR naming the blocked task and the ID.
        r = check(h125_board, strict_unblock=True, history_dir=hist)
        assert not r["ok"], r
        assert any("H2: Unblock references done task ID 'H1'" in e
                   for e in r["errors"]), r["errors"]
        # Archived target -> ERROR too (the M4.23 case).
        assert any("H3: Unblock references archived task ID 'H9'" in e
                   for e in r["errors"]), r["errors"]
        # Open target -> no error (H4/H5), and the fix list names the two bad rows.
        assert not any("H4" in e for e in r["errors"]), r["errors"]
        assert ("H2", "Unblock", "H1", "done") in r["fix_list"], r["fix_list"]
        assert ("H3", "Unblock", "H9", "archived") in r["fix_list"], r["fix_list"]
        assert not any(row[0] == "H4" for row in r["fix_list"]), r["fix_list"]

        # Default mode: the same references are warnings, not errors, so
        # tools/gate.py (non-strict) stays green while the board is repaired.
        r_def = check(h125_board, history_dir=hist)
        assert r_def["ok"], r_def["errors"]
        assert any("H2: Unblock references done task ID 'H1'" in w
                   for w in r_def["warnings"]), r_def["warnings"]
        assert any("H3: Unblock references archived task ID 'H9'" in w
                   for w in r_def["warnings"]), r_def["warnings"]

        # Negative control: a board whose only blocked Unblock names an open
        # task exits 0 under the strict rule.
        clean = """# TODO
- [ ] **H4 — blocked on an open task**
  - Status: blocked · Owner: — · Critical: no
  - Depends: —
  - Goal: g
  - Done when: d
  - Unblock: H5
  - Claims: C-630–C-639
- [ ] **H5 — open target**
  - Status: open · Owner: — · Critical: no
  - Depends: —
  - Goal: g
  - Done when: d
  - Claims: C-640–C-649
"""
        r_clean = check(clean, strict_unblock=True, history_dir=hist)
        assert r_clean["ok"] and r_clean["fix_list"] == [], r_clean

        # Parenthetical example IDs are prose, not the waited-on token. H6 is a
        # REAL done block: H4 is blocked on the open H5 and names the done H6
        # only inside `(…)`, so H4 must NOT error; the same H6 outside the
        # parentheses MUST error (otherwise paren-stripping is doing nothing and
        # a _strip_parens = identity monkeypatch would pass this test).
        paren_board = clean + """- [x] **H6 — done example**
  - Status: done · Owner: b · Critical: no
  - Depends: —
  - Goal: g
  - Done when: d
  - Claims: C-650–C-659
  - Result: r
"""
        paren_ok = paren_board.replace("  - Unblock: H5\n",
                                       "  - Unblock: H5 (not H6, which is done)\n")
        r_paren = check(paren_ok, strict_unblock=True, history_dir=hist)
        assert not any("H4: Unblock references" in e for e in r_paren["errors"]), r_paren["errors"]
        # Positive control for the control: the SAME done H6 outside the
        # parentheses must be flagged, so the paren case proves stripping.
        outside = paren_board.replace("  - Unblock: H5\n", "  - Unblock: H5, H6\n")
        r_out = check(outside, strict_unblock=True, history_dir=hist)
        assert any("H4: Unblock references done task ID 'H6'" in e
                   for e in r_out["errors"]), r_out["errors"]

        # H125 second clause: an open task that "cannot be taken" until an
        # open task moves is a WARN (never an ERROR), M3.30-shaped.
        open_door = """# TODO
- [ ] **H7 — follow-on**
  - Status: open · Owner: — · Critical: no
  - Depends: H8 (open). **Follow-on: cannot be taken until H8 merges `done`** — reuses H8's run.
  - Goal: g
  - Done when: d
  - Claims: C-660–C-669
- [ ] **H8 — upstream**
  - Status: open · Owner: — · Critical: no
  - Depends: —
  - Goal: g
  - Done when: d
  - Claims: C-670–C-679
"""
        r_door = check(open_door, history_dir=hist)
        assert r_door["ok"], r_door["errors"]
        assert any("H7: Depends says 'cannot be taken' on open task ID 'H8'" in w
                   for w in r_door["warnings"]), r_door["warnings"]
        # Negative: the same phrasing naming a task that is NOT open (H8 done)
        # is not the open-door case.
        moved = open_door.replace("- [ ] **H8 — upstream**", "- [x] **H8 — upstream**") \
                          .replace("  - Status: open · Owner: — · Critical: no\n  - Depends: —\n  - Goal: g\n  - Done when: d\n  - Claims: C-670–C-679",
                                   "  - Status: done · Owner: b · Critical: no\n  - Depends: —\n  - Goal: g\n  - Done when: d\n  - Claims: C-670–C-679\n  - Result: r")
        r_moved = check(moved, history_dir=hist)
        assert r_moved["ok"], r_moved["errors"]
        assert not any("'cannot be taken'" in w for w in r_moved["warnings"]), r_moved["warnings"]

    # real TODO.md parses cleanly and has no ghost reference
    real = TODO_PATH.read_text(encoding="utf-8")
    r = check(real)
    assert r["ok"], "real TODO.md:\n" + "\n".join(r["errors"])
    assert r["tasks"] > 100, r["tasks"]
    assert r["dep_classes"]["ghost"] == 0, r["dep_classes"]
    real_tasks = r["tasks"]

    # --- H128: the --strict baseline (debt ledger) -------------------------
    # A baseline keyed by (task ID, missing field): a new firmware task
    # missing a field fails, a baselined one that clears does not, and a
    # structural error is never baselined.
    import tempfile as _tf
    fw = """# TODO
- [ ] **M1.1 — b**
  - Status: open · Owner: — · Critical: yes
  - Depends: —
  - Goal: g
  - Done when: d
  - Claims: C-550–C-559
"""
    r = check(fw, strict_firmware=True)
    keys = {k for e in r["errors"] if (k := _error_key(e))}
    assert keys == {("M1.1", "Precheck"), ("M1.1", "Scope"), ("M1.1", "Stop")}, keys

    with _tf.TemporaryDirectory(prefix="todo-h128-") as td:
        bp = Path(td) / "base.json"
        _write_baseline(bp, keys, "rev0")
        base = _load_baseline(bp)
        assert set(base) == {"M1.1|Precheck", "M1.1|Scope", "M1.1|Stop"}, base

        # All errors baselined -> no new key.
        new = keys - {tuple(k.split("|", 1)) for k in base}
        assert new == set(), new

        # A NEW firmware task (M9.99) missing Stop is not in the baseline.
        fw2 = fw + ("\n- [ ] **M9.99 — new**\n  - Status: open · Owner: — · "
                    "Critical: no\n  - Depends: —\n  - Goal: g\n  - Precheck: p\n"
                    "  - Scope: s\n  - Done when: d\n  - Claims: C-560–C-569\n")
        r2 = check(fw2, strict_firmware=True)
        keys2 = {k for e in r2["errors"] if (k := _error_key(e))}
        new2 = keys2 - {tuple(k.split("|", 1)) for k in base}
        assert new2 == {("M9.99", "Stop")}, new2

        # M1.1 made done -> its 3 keys clear (baseline entry that cleared).
        fw_done = fw.replace("- Status: open", "- Status: done", 1).replace(
            "  - Claims: C-550–C-559", "  - Claims: C-550–C-559\n  - Result: r", 1)
        r3 = check(fw_done, strict_firmware=True)
        keys3 = {k for e in r3["errors"] if (k := _error_key(e))}
        cleared = {tuple(k.split("|", 1)) for k in base} - keys3
        assert cleared == {("M1.1", "Precheck"), ("M1.1", "Scope"),
                           ("M1.1", "Stop")}, cleared

        # A structural error has no key and is never baselined.
        dup = fw.replace("**M1.1 — b**", "**M1.1 — dup**") + fw
        rd = check(dup, strict_firmware=True)
        assert any(_error_key(e) is None and "duplicate task ID" in e
                   for e in rd["errors"]), rd["errors"]

    import ast as _ast, inspect as _inspect
    _n = sum(isinstance(n, _ast.Assert) for n in _ast.walk(
        _ast.parse(_inspect.getsource(run_selftest))))
    print(f"todo_check selftest: OK ({_n} checks, {real_tasks} real tasks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
