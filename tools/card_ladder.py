#!/usr/bin/env python3
"""Card-ladder step board (M5.38): which ladder step each open M4/M5/M9 task serves.

The ladder (``docs/research/card-ladder.md``) has five content steps P0..P4
plus ``tooling`` for work that serves every step. Each open M4/M5/M9 block in
``TODO.md`` carries one line ``  - Step: P0`` (…``P4`` or ``tooling``). A block
whose owner holds it in an open PR may instead be listed in the page's
"Pending tags" table (``| M9.44 | P0 | … |``) until the owner merges.

Subcommands:

``steps [--todo PATH] [--page PATH] [--check]``
    Print the open M4/M5/M9 blocks grouped by step (``*`` = ``Critical: yes``,
    ``(page)`` = the step comes from the pending table), then one summary line
    ``card-ladder steps: open=N tagged=T pending=P missing=M bad=B stale=S``.
    With ``--check`` exit 1 when ``missing``, ``bad`` or ``stale`` is nonzero.
    ``bad`` = a Step value outside P0..P4/tooling; ``stale`` = a pending row for
    a block that is already tagged, closed, or absent.

``dirs CENSUS_JSON --bbox W,S,E,N``
    Read ``tools/parcel_census.py --json`` output for one tile and count, per
    section/level/class, the directories whose box intersects the bbox — the
    "how much of the region can today's writer touch" number of a step.

Stdlib only. ``--selftest`` runs on synthetic text, no vendor data.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STEPS = ("P0", "P1", "P2", "P3", "P4", "tooling")
STREAMS = ("M4.", "M5.", "M9.")

HEADER_RE = re.compile(r"^- \[(?P<chk>[ xX])\] \*\*(?P<id>M[0-9]+\.[A-Za-z0-9.]+)\s+[—–-]\s+(?P<title>.+?)(?:\*\*|$)")
ANY_HEADER_RE = re.compile(r"^- \[[ xX]\] \*\*")
SECTION_RE = re.compile(r"^#{1,3} ")
STATUS_RE = re.compile(r"^  - Status:\s*(?P<st>[^·]+?)\s*(?:·|$)")
STEP_RE = re.compile(r"^  - Step:\s*(?P<step>\S+)")
CRIT_RE = re.compile(r"Critical:\s*yes")
PENDING_RE = re.compile(r"^\|\s*(?P<id>M[0-9]+\.[A-Za-z0-9.]+)\s*\|\s*(?P<step>[A-Za-z0-9]+)\s*\|")


def parse_blocks(text: str) -> list[dict]:
    """Every M4/M5/M9 block: id, checked, status, step, critical, title."""
    blocks: list[dict] = []
    cur: dict | None = None
    for line in text.splitlines():
        if ANY_HEADER_RE.match(line) or SECTION_RE.match(line):
            cur = None
            m = HEADER_RE.match(line)
            if m and m.group("id").startswith(STREAMS):
                cur = {"id": m.group("id"), "done": m.group("chk") != " ",
                       "title": m.group("title").strip(), "status": "",
                       "step": None, "critical": False}
                blocks.append(cur)
            continue
        if cur is None:
            continue
        m = STATUS_RE.match(line)
        if m and not cur["status"]:
            cur["status"] = m.group("st").strip()
            cur["critical"] = bool(CRIT_RE.search(line))
            continue
        m = STEP_RE.match(line)
        if m and cur["step"] is None:
            cur["step"] = m.group("step")
    return blocks


def parse_pending(page: str) -> dict[str, str]:
    """Rows of the page's 'Pending tags' table: id -> step."""
    out: dict[str, str] = {}
    inside = False
    for line in page.splitlines():
        if line.startswith("## "):
            inside = line.strip().lower().startswith("## pending tags")
            continue
        if inside:
            m = PENDING_RE.match(line)
            if m:
                out[m.group("id")] = m.group("step")
    return out


def is_open(b: dict) -> bool:
    return not b["done"] and not b["status"].startswith("done")


def board(text: str, page: str) -> dict:
    blocks = parse_blocks(text)
    pending = parse_pending(page)
    open_ = [b for b in blocks if is_open(b)]
    ids_open = {b["id"] for b in open_}
    groups: dict[str, list[str]] = {s: [] for s in STEPS}
    missing, bad, stale = [], [], []
    tagged = pend = 0
    for b in open_:
        step, src = b["step"], ""
        if step is None and b["id"] in pending:
            step, src = pending[b["id"]], "(page)"
            pend += 1
        elif step is not None:
            tagged += 1
        if step is None:
            missing.append(b["id"])
            continue
        if step not in STEPS:
            bad.append(f"{b['id']}={step}")
            continue
        groups[step].append(b["id"] + ("*" if b["critical"] else "") + src)
    for pid, pstep in pending.items():
        tagged_already = any(b["id"] == pid and b["step"] for b in open_)
        if pid not in ids_open or tagged_already:
            stale.append(pid)
        elif pstep not in STEPS:
            bad.append(f"{pid}={pstep}(page)")
    return {"open": len(open_), "tagged": tagged, "pending": pend,
            "missing": missing, "bad": bad, "stale": stale, "groups": groups}


def render(r: dict) -> str:
    lines = []
    for s in STEPS:
        lines.append(f"{s} ({len(r['groups'][s])}): " + " ".join(r["groups"][s]))
    if r["missing"]:
        lines.append("missing: " + " ".join(r["missing"]))
    if r["bad"]:
        lines.append("bad: " + " ".join(r["bad"]))
    if r["stale"]:
        lines.append("stale pending rows: " + " ".join(r["stale"]))
    lines.append(
        f"card-ladder steps: open={r['open']} tagged={r['tagged']} pending={r['pending']} "
        f"missing={len(r['missing'])} bad={len(r['bad'])} stale={len(r['stale'])}")
    return "\n".join(lines)


def count_dirs(rows: list[dict], bbox: tuple[float, float, float, float]) -> Counter:
    w, s, e, n = bbox
    c: Counter = Counter()
    for x in rows:
        hit = not (x["lon_max"] <= w or x["lon_min"] >= e or x["lat_max"] <= s or x["lat_min"] >= n)
        if hit:
            c[(x["section"], x["level"], x["class"])] += 1
    return c


def render_dirs(c: Counter) -> str:
    lines = [f"section={k[0]} level={k[1]} class={k[2]} dirs={v}" for k, v in sorted(c.items())]
    s1 = {cls: sum(v for k, v in c.items() if k[0] == 1 and k[2] == cls)
          for cls in ("spliceable", "preserve-only", "unmodelled")}
    total = sum(s1.values())
    lines.append(f"section1 in bbox: total={total} spliceable={s1['spliceable']} "
                 f"preserve-only={s1['preserve-only']} unmodelled={s1['unmodelled']}")
    return "\n".join(lines)


def selftest() -> int:
    fails = 0

    def chk(cond: bool, msg: str) -> None:
        nonlocal fails
        print(("ok   " if cond else "FAIL ") + msg)
        fails += 0 if cond else 1

    todo = "\n".join([
        "## M4 — x",
        "- [ ] **M4.1 — a**",
        "  - Status: open · Owner: — · Critical: yes",
        "  - Step: P2",
        "- [x] **M4.2 — done one**",
        "  - Status: done · Owner: b · Critical: no",
        "- [ ] **M5.1 — untagged**",
        "  - Status: blocked · Owner: — · Critical: no",
        "- [ ] **M5.2 — pending**",
        "  - Status: in progress · Owner: t · Critical: no",
        "- [ ] **M9.1 — bad step**",
        "  - Status: open · Owner: — · Critical: no",
        "  - Step: P7",
        "- [ ] **M3.1 — other stream**",
        "  - Status: open · Owner: — · Critical: no",
        "## M9 — y",
        "  - Step: P0",
        "- [ ] **M9.2 — tooling**",
        "  - Status: open · Owner: — · Critical: no",
        "  - Note: Step: P1 inside text is not a tag",
        "  - Step: tooling",
    ])
    page = "\n".join(["## Pending tags", "| ID | Step | why |", "| --- | --- | --- |",
                      "| M5.2 | P1 | owner PR |", "| M4.1 | P2 | dup |", "| M4.2 | P0 | closed |",
                      "## Other", "| M5.1 | P0 | not in table |"])
    r = board(todo, page)
    chk(r["open"] == 5, "five open M4/M5/M9 blocks (done and M3 excluded)")
    chk(r["groups"]["P2"] == ["M4.1*"], "tagged critical block grouped with '*'")
    chk(r["groups"]["P1"] == ["M5.2(page)"], "pending row supplies the step")
    chk(r["groups"]["tooling"] == ["M9.2"], "tooling tag read; stray Step under a heading ignored")
    chk(r["missing"] == ["M5.1"], "untagged block reported missing (row outside the table ignored)")
    chk(r["bad"] == ["M9.1=P7"], "invalid step value reported")
    chk(sorted(r["stale"]) == ["M4.1", "M4.2"], "pending rows for tagged/closed blocks are stale")
    out = render(r)
    chk(out.splitlines()[-1] == "card-ladder steps: open=5 tagged=3 pending=1 missing=1 bad=1 stale=2",
        "summary line")
    clean = board(todo.replace("  - Step: P7", "  - Step: P3").replace(
        "- [ ] **M5.1 — untagged**\n  - Status: blocked · Owner: — · Critical: no",
        "- [ ] **M5.1 — untagged**\n  - Status: blocked · Owner: — · Critical: no\n  - Step: P4"),
        "## Pending tags\n| M5.2 | P1 | x |")
    chk(not clean["missing"] and not clean["bad"] and not clean["stale"], "clean board has no defects")

    rows = [
        {"section": 1, "level": 1, "class": "spliceable", "lon_min": 16, "lon_max": 17, "lat_min": 50, "lat_max": 50.6},
        {"section": 1, "level": 1, "class": "preserve-only", "lon_min": 17, "lon_max": 18, "lat_min": 50, "lat_max": 50.6},
        {"section": 1, "level": 1, "class": "spliceable", "lon_min": 12, "lon_max": 13, "lat_min": 48, "lat_max": 48.6},
        {"section": 2, "level": 1, "class": "router-graph", "lon_min": 16, "lon_max": 17, "lat_min": 50, "lat_max": 50.6},
        {"section": 1, "level": 1, "class": "spliceable", "lon_min": 18, "lon_max": 19, "lat_min": 50, "lat_max": 50.6},
    ]
    c = count_dirs(rows, (14.0, 49.9, 17.9, 51.9))
    txt = render_dirs(c)
    chk("section1 in bbox: total=2 spliceable=1 preserve-only=1 unmodelled=0" in txt,
        "dirs counts only intersecting boxes (edge-touching box at lon 18 excluded)")
    chk("section=2 level=1 class=router-graph dirs=1" in txt, "dirs reports other sections")
    print(f"selftest: {'OK' if not fails else 'FAIL'} ({fails} failure(s))")
    return 1 if fails else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    sp = sub.add_parser("steps", help="open M4/M5/M9 blocks grouped by ladder step")
    sp.add_argument("--todo", default=str(REPO / "TODO.md"))
    sp.add_argument("--page", default=str(REPO / "docs/research/card-ladder.md"))
    sp.add_argument("--check", action="store_true")
    dp = sub.add_parser("dirs", help="tile directories intersecting a bbox (parcel_census --json)")
    dp.add_argument("census")
    dp.add_argument("--bbox", required=True, help="W,S,E,N in degrees")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "steps":
        page = Path(a.page).read_text(encoding="utf-8") if Path(a.page).exists() else ""
        r = board(Path(a.todo).read_text(encoding="utf-8"), page)
        print(render(r))
        return 1 if a.check and (r["missing"] or r["bad"] or r["stale"]) else 0
    if a.cmd == "dirs":
        w, s, e, n = (float(v) for v in a.bbox.split(","))
        rows = json.loads(Path(a.census).read_text(encoding="utf-8"))["rows"]
        print(render_dirs(count_dirs(rows, (w, s, e, n))))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
