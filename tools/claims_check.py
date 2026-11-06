#!/usr/bin/env python3
"""Check the claim ledger for duplicate IDs and unregistered proposed claims."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAIMS_PATH = REPO_ROOT / "docs" / "research" / "claims.md"
EXP_DIR = REPO_ROOT / "docs" / "experiments"

ROW_RE = re.compile(r"^\|\s*(C-\d+)\s*\|")
PROPOSED_RE = re.compile(r"\bpropos", re.IGNORECASE)
CLAIM_ID_RE = re.compile(r"\bC-\d+\b")
WAS_PROPOSED_RE = re.compile(r"Was proposed as (C-\d+) in (EXP-[A-Za-z0-9.\-]+)")
RANGE_RE = re.compile(r"C-(\d+)\s*[…\-–]\s*C?(\d+)")

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


def check(claims_text, exp_files):
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

    return {
        "duplicate_ids": dups,
        "unregistered_proposed": unregistered,
        "bad_annotations": bad_annotations,
        "ok": not dups and not unregistered and not bad_annotations,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="claims_check")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()

    claims_text = CLAIMS_PATH.read_text(encoding="utf-8")
    exp_files = {}
    if EXP_DIR.exists():
        for p in sorted(EXP_DIR.glob("*.md")):
            exp_files[p.name] = p.read_text(encoding="utf-8")

    result = check(claims_text, exp_files)
    if args.json:
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
        print("claims_check: OK" if result["ok"] else "claims_check: FAILED")
    return 0 if result["ok"] else 1


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

    print("claims_check selftest: OK (4 checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
