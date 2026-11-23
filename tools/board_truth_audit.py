#!/usr/bin/env python3
"""Audit stale Unblock/Depends pointers in TODO.md (H125 / M3.36).

Two classes are counted:

A. any task whose ``Unblock`` names an ID whose recorded status is ``done`` —
   rule 15 should have re-opened the task, so the pointer can never fire;
B. any task whose ``Depends``/``Unblock`` says ``(done)``/``(blocked)`` next to
   an ID whose recorded status contradicts that parenthetical (an open door
   onto a locked task).

The audit is intentionally narrow: it does not judge whether a task *should*
be done, only whether the board's own pointers are self-consistent.  IDs are
matched by the board's own format (M3.29, M8.H11, H53, M1.2f).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TASK_RE = re.compile(r"^- \[[ x]\] \*\*([A-Z]+\d+(?:\.\d+[a-z]?)?) —")
ID_RE = re.compile(r"\b([A-Z]+\d+(?:\.\d+[a-z]?)?)\b")
STATUS_RE = re.compile(r"Status:\s*(open|in progress|blocked|done)\b")
FIELD_RE = re.compile(r"^\s*- (Depends|Unblock):\s*(.*)$")
CLAIMED_RE = re.compile(r"\((done|blocked|open|in progress)\)")


def parse(text: str) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    statuses: dict[str, str] = {}
    fields: dict[str, dict[str, str]] = {}
    current = None
    for line in text.splitlines():
        m = TASK_RE.match(line)
        if m:
            current = m.group(1)
            fields.setdefault(current, {})
            continue
        if current is None:
            continue
        st = STATUS_RE.search(line)
        if st:
            statuses[current] = st.group(1)
        fm = FIELD_RE.match(line)
        if fm:
            fields[current][fm.group(1)] = fm.group(2)
    return statuses, fields


def audit(text: str, scope: set[str] | None = None) -> dict:
    statuses, fields = parse(text)
    if scope is not None:
        fields = {tid: row for tid, row in fields.items() if tid in scope}
    class_a: list[dict] = []
    class_b: list[dict] = []
    for tid, row in fields.items():
        ub = row.get("Unblock", "")
        ids = ID_RE.findall(ub)
        # Only the first ID is the unblocker; later IDs are historical
        # references (e.g. the M3.23 candidate list inside M3.14's Unblock).
        if ids:
            other = ids[0]
            if other != tid and statuses.get(other) == "done":
                class_a.append({"task": tid, "names": other, "status": statuses.get(tid, "?")})
        for key in ("Depends", "Unblock"):
            value = row.get(key, "")
            # only parenthetical statuses adjacent to an ID on the same line
            for id_match in ID_RE.finditer(value):
                tail = value[id_match.end():id_match.end() + 8]
                pm = CLAIMED_RE.match(tail.lstrip(" ,;·"))
                if not pm:
                    continue
                claimed, actual = pm.group(1), statuses.get(id_match.group(1))
                if actual is not None and actual != claimed:
                    class_b.append({"task": tid, "field": key, "names": id_match.group(1),
                                    "says": claimed, "actual": actual})
    return {"statuses": len(statuses), "class_a": class_a, "class_b": class_b,
            "count": len(class_a) + len(class_b)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("todo", nargs="?", default="TODO.md")
    p.add_argument("--json", action="store_true")
    p.add_argument("--scope", help="comma-separated task IDs to audit (default: all)")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest:
        text = "\n".join([
            "- [ ] **M3.29 — stale unblock**",
            "  - Status: open · Owner: —",
            "  - Unblock: M9.53 — the mount half merged",
            "- [ ] **M3.30 — stale depends**",
            "  - Status: open · Owner: —",
            "  - Depends: M3.29 (done); M9.38 (done)",
            "- [x] **M9.53 — real**",
            "  - Status: done · Owner: task/x",
            "- [ ] **M4.23 — healthy**",
            "  - Status: blocked · Owner: task/y",
            "  - Unblock: M4.24 (section-2 grammar, still blocked). Re-opens when it merges.",
        ])
        r = audit(text)
        ok = (r["statuses"] == 4 and len(r["class_a"]) == 1
              and r["class_a"][0]["task"] == "M3.29"
              and len(r["class_b"]) == 1
              and r["class_b"][0]["task"] == "M3.30")
        print(f"selftest: {'OK' if ok else 'FAIL'} "
              f"({len(r['class_a'])} A, {len(r['class_b'])} B, {r['statuses']} tasks)")
        return 0 if ok else 1
    scope = set(args.scope.split(",")) if args.scope else None
    rep = audit(Path(args.todo).read_text(), scope)
    if args.json:
        import json
        print(json.dumps(rep, indent=1))
    else:
        print(f"board truth: {rep['statuses']} tasks, "
              f"class A (Unblock names DONE) = {len(rep['class_a'])}, "
              f"class B (Depends/Unblock contradicts status) = {len(rep['class_b'])}, "
              f"total = {rep['count']}")
        for row in rep["class_a"]:
            print(f"  A {row['task']} [{row['status']}] -> {row['names']} is done")
        for row in rep["class_b"]:
            print(f"  B {row['task']} {row['field']}: {row['names']} says "
                  f"{row['says']}, actually {row['actual']}")
    return 0 if rep["count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
