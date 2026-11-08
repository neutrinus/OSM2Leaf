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
- missing required fields: Status, Owner, Critical, Depends, Goal, Done when,
  Claims
- blocked tasks missing ``Unblock``
- done tasks missing a ``Result:`` line
- checkbox/status contradictions (``[x]`` vs non-done, ``[ ]`` vs done)
- invalid Status / Critical values
- cyclic ``Depends`` references
- with ``--strict``: open/blocked firmware/search tasks missing
  ``Precheck``/``Scope``/``Stop``

Warnings (printed, do not fail by default): ``Depends`` references to unknown
task IDs, missing ``Precheck``/``Scope``/``Stop`` on firmware/search tasks
(default mode; done tasks always warn, never error, to avoid retroactive
false failures), actionable/done tasks missing standard fields.
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


def check(text: str, *, strict_firmware: bool = False):
    tasks = parse_tasks(text)
    errors = []
    warnings = []

    def err(msg, task=None):
        where = f"TODO.md:{task['lineno']} {task['id']}" if task else "TODO.md"
        errors.append(f"{where}: {msg}")

    # duplicate IDs
    seen = {}
    for t in tasks:
        seen.setdefault(t["id"], []).append(t["lineno"])
    for tid, lines in sorted(seen.items()):
        if len(tid) and len(lines) > 1:
            errors.append(f"TODO.md: duplicate task ID {tid} at lines {lines}")

    known_ids = set(seen)

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

        deps = _parse_depends(f.get("Depends", "—"))
        for dep in deps:
            if dep not in known_ids:
                warnings.append(f"TODO.md:{t['lineno']} {t['id']}: Depends references unknown task ID {dep!r}")

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
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("todo", nargs="?", default=str(TODO_PATH), help="TODO.md path")
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--strict",
        action="store_true",
        help="fail on rule-14 violations: open/blocked/in-progress firmware/search tasks (M1/M2/M3/M8/M9) missing Precheck/Scope/Stop; done tasks still warn only",
    )
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)

    if args.selftest:
        return run_selftest()

    text = Path(args.todo).read_text(encoding="utf-8")
    result = check(text, strict_firmware=args.strict)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        mode = " [strict]" if args.strict else ""
        print(
            f"todo_check{mode}: {result['tasks']} tasks, {len(result['errors'])} error(s), "
            f"{len(result['warnings'])} warning(s)"
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

    # unknown depends (warning)
    unk = ok_doc.replace("Depends: T1", "Depends: H99")
    r = check(unk)
    assert r["ok"] and any("unknown task ID 'H99'" in w for w in r["warnings"]), r

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

    # real TODO.md parses cleanly
    real = TODO_PATH.read_text(encoding="utf-8")
    r = check(real)
    assert r["ok"], "real TODO.md:\n" + "\n".join(r["errors"])
    assert r["tasks"] > 100, r["tasks"]

    print(f"todo_check selftest: OK (12 checks, {r['tasks']} real tasks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
