#!/usr/bin/env python3
"""H41: per-file / per-feature L1/L2 matrix and regression baseline.

Consumes the H26/H40 registry report from ``tools/l1l2_fixtures.py`` and emits
rows keyed ``level,file,feature`` with the status tokens required by H41:
``PASS|FAIL|SKIP|NOT_COVERED|NOT_RUNNABLE`` (plus ``BLOCKED``/``NOT_RUN`` for
upstream reports). ``SKIP``, ``NOT_COVERED`` and ``NOT_RUNNABLE`` are always
reported as themselves and never counted as PASS.

Feature attribution is a DATA table keyed by the ten existing check IDs, not
by line numbers or by guessed format semantics. A check with no evidence-backed
feature mapping is reported as ``NOT_COVERED`` with its claim/tool reason.

Usage::

    python3 tools/l1l2_matrix.py --selftest
    python3 tools/l1l2_matrix.py --input l1l2.json --json matrix.json --md matrix.md
    python3 tools/l1l2_matrix.py --input matrix.json --check-baseline tools/fixtures/l1l2-matrix-baseline.json
    python3 tools/l1l2_matrix.py --input matrix.json --write-baseline PATH

Exit code: 1 on a runnable FAIL or a baseline REGRESSION (including a lost
PASS key); 0 otherwise. DROPPED/NEW/DUPLICATE/IMPROVEMENT are printed but do
not fail. No vendor bytes, no firmware acceptance claim.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCHEMA = "osm2leaf.l1l2-matrix/v1"
BASELINE_SCHEMA = "osm2leaf.l1l2-matrix-baseline/v1"
KEY = ("level", "file", "feature")
STATUSES = ("PASS", "FAIL", "SKIP", "NOT_COVERED", "NOT_RUNNABLE",
            "BLOCKED", "NOT_RUN")
# Monotone quality tiers for the bidirectional baseline check (H57). A lower
# tier is always worse: PASS (3) > honest non-PASS (2) > FAIL (1). The old
# ordering put FAIL above SKIP, so SKIP -> FAIL printed as an IMPROVEMENT and a
# gate stayed green; FAIL is never better than SKIP. All honest non-PASS tokens
# (SKIP, NOT_COVERED, NOT_RUNNABLE, BLOCKED, NOT_RUN) share one tier, so a move
# between them is intentionally reported as neither regression nor improvement.
TIER = {"PASS": 3, "FAIL": 1, "SKIP": 2, "NOT_COVERED": 2,
        "NOT_RUNNABLE": 2, "BLOCKED": 2, "NOT_RUN": 2}
RUNNABLE = {"PASS", "FAIL", "SKIP"}

# Evidence: C-3270..C-3274 (H40), C-2760 (H26), C-4340..C-4349 (H103) and
# docs/research/reader-coverage.md rows 4, 10, 17. Keys are check IDs only.
MAPPING: tuple[dict[str, str], ...] = (
    dict(check_id="l1.synthetic.cardcheck", level="L1",
         file="ZE0 generated fixture tree", feature="structural",
         evidence="C-3271, C-3272, C-4340: cardcheck --generate-fixture and "
                  "the H105 break control; L1 structural, no semantic feature"),
    dict(check_id="l2.drstr.selftest", level="L2", file="DRSTR001.DAT",
         feature="names",
         evidence="C-3273; reader-coverage row 4 (DRSTR/name entries)"),
    dict(check_id="l2.drstr.build-roundtrip", level="L2",
         file="DRSTR001.DAT (build+parse)", feature="names",
         evidence="C-3273 (176 B, 2 nodes); reader-coverage row 4"),
    dict(check_id="l2.cmpind.selftest", level="L2",
         file="REFER001/*.cmp/.ind (cmpind verify)", feature="container",
         evidence="C-3274, C-2760: container check, no feature attribution"),
    dict(check_id="l2.cmpind.writer-selftest", level="L2",
         file="REFER001/*.cmp/.ind (writer)", feature="container",
         evidence="C-3274, C-2760: container check, no feature attribution"),
    dict(check_id="l2.cmpind.preserve-roundtrip", level="L2",
         file="REFER001/*.cmp/.ind (preserve)", feature="container",
         evidence="C-3273, C-3274: stream preservation, not a named feature"),
    dict(check_id="l2.cmpind.recompress-roundtrip", level="L2",
         file="REFER001/*.cmp/.ind (recompress)", feature="container",
         evidence="C-3274: semantic-only, byte-identical SKIP on zlib-ng (H9)"),
    dict(check_id="l2.tile.harness-selftest", level="L2",
         file="MAPAL001/BxxRyyR.DAT (harness)", feature="NOT_COVERED",
         evidence="C-3274: no vendor-free synthetic tile fixture for harness"),
    dict(check_id="l2.tile.class-roundtrip", level="L2",
         file="MAPAL001/BxxRyyR.DAT", feature="roads",
         evidence="C-3273; reader-coverage row 17 (tile section 1 roads)"),
    dict(check_id="l2.tile.class-roundtrip", level="L2",
         file="MAPAL001/BxxRyyR.DAT (parcels/shapes)", feature="geometry",
         evidence="C-3273 (2 parcels, 3 shapes); H41 Scope section-1 geometry; "
                  "reader-coverage row 17"),
    dict(check_id="l2.poi.mutation.imgpatch-selftest", level="L2",
         file="REFER001/POINT0nn", feature="POIs",
         evidence="C-3273; reader-coverage row 10 (POINT POIs)"),
)

# Data-driven gaps: a feature named by H41 with no registry row. Report it,
# never infer it from a neighbouring check (H41 Stop, navigator fix 4).
FEATURE_GAPS: tuple[dict[str, str], ...] = (
    dict(level="L2", file="REFER001/ADDRE0nn + MAPAL001 section 4",
         feature="names", status="NOT_COVERED",
         reason="No registry check maps ADDRE/section-4 names; C-3274, "
                "C-2760. Reported as a gap, not inferred from DRSTR."),
)


def normalize_status(value: str) -> str:
    """Map the H26 spelling ('NOT COVERED') to the H41 token."""
    token = " ".join(str(value).upper().split()).replace(" ", "_")
    if token in ("NOT_RUN", "NOTRUN"):
        return "NOT_RUN"
    return token if token in STATUSES else "FAIL"


def _row(level: str, file: str, feature: str, status: str, command: str,
         reason: str, check_id: str = "") -> dict[str, str]:
    return dict(level=level, file=file, feature=feature,
                status=normalize_status(status), command=command,
                reason=reason, check_id=check_id)


def rows_from_checks(checks: list[dict], mapping=MAPPING) -> list[dict]:
    """Map each registry check by ID. Unknown IDs become honest NOT_COVERED."""
    by_id: dict[str, list[dict]] = {}
    for spec in mapping:
        by_id.setdefault(spec["check_id"], []).append(spec)
    rows: list[dict] = []
    for check in checks:
        check_id = str(check.get("id", ""))
        status = normalize_status(check.get("status", "FAIL"))
        detail = str(check.get("detail", ""))[:240]
        command = str(check.get("command", "tools/l1l2_fixtures.py"))
        for spec in by_id.get(check_id, ()):
            feature = spec["feature"]
            if feature == "NOT_COVERED" and status == "PASS":
                # A passing container check is not feature coverage.
                row_status = "NOT_COVERED"
            else:
                row_status = status
            rows.append(_row(
                spec["level"], spec["file"], feature, row_status, command,
                f"{spec['evidence']}; source {check_id} {status}: {detail}",
                check_id))
        if check_id not in by_id:
            rows.append(_row(
                "UNKNOWN", check_id, "NOT_COVERED", "NOT_COVERED", command,
                f"No evidence mapping for check {check_id}; C-3274, C-2760. "
                f"Source {status}: {detail}", check_id))
    for gap in FEATURE_GAPS:
        rows.append(_row(gap["level"], gap["file"], gap["feature"],
                         gap["status"], "none (no registry check)",
                         gap["reason"]))
    return rows


def load_rows(path: str, mapping=MAPPING) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "rows" in data:  # already a matrix report
        return [_row(**{k: r.get(k, "") for k in
                        ("level", "file", "feature", "status", "command",
                         "reason", "check_id")}) for r in data["rows"]]
    return rows_from_checks(data.get("checks", []), mapping)


def summarize(rows: list[dict]) -> dict:
    counts = {status: 0 for status in STATUSES}
    for row in rows:
        counts[row["status"]] += 1
    return {
        "total": len(rows), "counts": counts,
        "runnable_pass": counts["PASS"],
        "runnable_fail": counts["FAIL"],
        "runnable_skip": counts["SKIP"],
        "runnable_total": sum(counts[s] for s in RUNNABLE),
        "ok": counts["FAIL"] == 0,
    }


def make_report(rows: list[dict], baseline_path: str = "",
                baseline_messages: list[str] | None = None) -> dict:
    report = {
        "task": "H41", "schema": SCHEMA, "key": list(KEY),
        "firmware_acceptance_claim": False, "vendor_data_used": False,
        "summary": summarize(rows), "rows": rows,
    }
    if baseline_path:
        report["baseline"] = dict(path=baseline_path,
                                  messages=baseline_messages or [])
    return report


def baseline_rows(path: str) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("rows", [])


def check_baseline(rows: list[dict], base: list[dict]) -> list[tuple[str, str]]:
    """Return (kind, message) for every missing/regression/improvement.

    H57's monotone rule: a drop to a lower quality tier is a REGRESSION
    (PASS -> anything-not-PASS, and SKIP/NOT_COVERED/... -> FAIL), a rise is an
    IMPROVEMENT (FAIL -> SKIP/PASS, SKIP -> PASS). A key that disappears from
    the report is a DROPPED regression only when the baseline expected PASS; a
    lost FAIL/SKIP row is reported but does not fail the gate. A key present
    only in the report is NEW (informational). Duplicate report rows are
    reported so a silent loss of uniqueness cannot pass unnoticed.
    """
    reported: dict[tuple[str, ...], int] = {}
    current: dict[tuple[str, ...], str] = {}
    for r in rows:
        key = tuple(r.get(k, "") for k in KEY)
        reported[key] = reported.get(key, 0) + 1
        current[key] = r["status"]
    result: list[tuple[str, str]] = []
    base_keys: set[tuple[str, ...]] = set()
    for expected in base:
        key = tuple(expected.get(k, "") for k in KEY)
        base_keys.add(key)
        label = "|".join(key)
        if reported.get(key, 0) > 1:
            result.append(("DUPLICATE", f"{label}: {reported[key]} rows in report"))
        if key not in current:
            kind = "REGRESSION" if expected["status"] == "PASS" else "DROPPED"
            result.append((kind, f"MISSING {label} (was {expected['status']})"))
            continue
        got = current[key]
        want = TIER.get(expected["status"], 2)
        now = TIER.get(got, 2)
        if now < want:
            result.append(("REGRESSION",
                           f"{label}: {expected['status']} -> {got}"))
        elif now > want:
            result.append(("IMPROVEMENT",
                           f"{label}: {expected['status']} -> {got}"))
    for key in current:
        if key not in base_keys:
            result.append(("NEW", "|".join(key) + ": " + current[key]))
    return result


def write_baseline(rows: list[dict], path: str) -> None:
    document = {
        "schema": BASELINE_SCHEMA, "task": "H41", "key": list(KEY),
        "fixture": "H40 generated fixture via tools/l1l2_fixtures.py",
        "note": "No vendor bytes. H43 consumes this file and key; no second "
                "schema and no second --check-baseline.",
        "rows": [dict(**{k: r[k] for k in KEY}, status=r["status"])
                 for r in rows],
    }
    Path(path).write_text(json.dumps(document, indent=2) + "\n",
                          encoding="utf-8")


def render_markdown(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "# L1/L2 progress matrix (H41)", "",
        f"Schema `{report['schema']}`; key `level,file,feature`. "
        "No vendor data, no firmware acceptance claim (rule 13).", "",
        "Statuses are kept distinct: PASS / FAIL / SKIP / NOT_COVERED / "
        "NOT_RUNNABLE. SKIP, NOT_COVERED and NOT_RUNNABLE are never PASS.", "",
        f"Rows: {summary['total']}; runnable "
        f"{summary['runnable_pass']} PASS / {summary['runnable_fail']} FAIL / "
        f"{summary['runnable_skip']} SKIP "
        f"(runnable total {summary['runnable_total']}).", "",
        "| level | file | feature | status | command | reason |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["rows"]:
        reason = row["reason"].replace("|", "\\|").replace("\n", " ")
        command = row["command"].replace("|", "\\|")
        lines.append(f"| {row['level']} | {row['file']} | {row['feature']} | "
                     f"**{row['status']}** | `{command}` | {reason} |")
    lines.append("")
    if "baseline" in report:
        lines += ["## Regression baseline", "",
                  f"`{report['baseline']['path']}`",
                  ""]
        for message in report["baseline"]["messages"]:
            lines.append(f"- {message}")
        if not report["baseline"]["messages"]:
            lines.append("- baseline matches (no regression, improvement or new key)")
        lines.append("")
    return "\n".join(lines) + "\n"


def _selftest() -> int:
    errors: list[str] = []
    count = 0

    def ok(cond: bool, msg: str) -> None:
        nonlocal count
        count += 1
        if not cond:
            errors.append(msg)

    # (3) Status tokens: H26's space spelling normalizes to the H41 token.
    ok(normalize_status("NOT COVERED") == "NOT_COVERED", "NOT COVERED token")
    ok(normalize_status("not runnable") == "NOT_RUNNABLE", "NOT_RUNNABLE token")
    ok(normalize_status("PASS") == "PASS", "PASS token unchanged")
    ok(normalize_status("nonsense") == "FAIL", "invalid status is FAIL")

    rows = [
        _row("L2", "F", "roads", "PASS", "cmd", "d"),
        _row("L2", "F", "names", "FAIL", "cmd", "d"),
        _row("L2", "F", "POIs", "SKIP", "cmd", "d"),
        _row("L2", "F", "geometry", "NOT COVERED", "cmd", "d"),
        _row("L1", "F", "structural", "NOT_RUNNABLE", "cmd", "d"),
    ]
    tokens = [r["status"] for r in rows]
    ok("NOT_COVERED" in tokens and "NOT_RUNNABLE" in tokens,
       "underscore tokens emitted")
    ok(not any(" " in t for t in tokens), "no space spelling survives")
    report = make_report(rows)
    counts = report["summary"]["counts"]
    for token in ("PASS", "FAIL", "SKIP", "NOT_COVERED", "NOT_RUNNABLE"):
        ok(counts[token] == 1, f"distinct count for {token}")
    ok(report["summary"]["runnable_pass"] == 1 and
       report["summary"]["runnable_fail"] == 1 and
       report["summary"]["runnable_skip"] == 1,
       "runnable totals exclude NOT_COVERED/NOT_RUNNABLE")
    ok(report["summary"]["ok"] is False, "FAIL is a failure")
    ok(make_report(rows[:1] + rows[2:])["summary"]["ok"] is True,
       "SKIP/NOT_COVERED/NOT_RUNNABLE alone are not a runnable failure")

    # (4) Mapping discipline: strict check-ID keys, unknown -> NOT_COVERED,
    # data-only addition of a check (no report-logic change).
    checks = [
        dict(id="l1.synthetic.cardcheck", status="PASS", command="c", detail="d"),
        dict(id="brand.new.check", status="NOT COVERED", command="c", detail="d"),
    ]
    mapped = rows_from_checks(checks)
    ok(any(r["status"] == "NOT_COVERED" and r["check_id"] == "brand.new.check"
           and "C-3274" in r["reason"] for r in mapped),
       "unknown check ID is NOT_COVERED with claim reason")
    ok(all(r["status"] != "PASS" for r in mapped
           if r["feature"] == "NOT_COVERED"), "unmapped never PASS")
    extended = MAPPING + (dict(check_id="brand.new.check", level="L2",
                               file="NEW.DAT", feature="roads",
                               evidence="C-3280 (test)"),)
    mapped2 = rows_from_checks(checks, extended)
    ok(any(r["file"] == "NEW.DAT" and r["status"] == "NOT_COVERED"
           for r in mapped2), "new check mapped by data, not report surgery")
    ok(all(r["check_id"] in {"l1.synthetic.cardcheck", "brand.new.check", ""}
           for r in mapped2), "mapping keys are check IDs")
    ok("NOT_COVERED" in [r["status"] for r in mapped2], "feature gap row kept")

    # (2) Monotone baseline (H57): PASS -> anything-not-PASS and SKIP -> FAIL
    # both regress; FAIL -> SKIP/PASS and SKIP -> PASS are improvements; a lost
    # PASS key fails, a lost non-PASS key is DROPPED (report only), duplicates
    # and new keys are informational.
    base = [dict(level="L2", file="F", feature="roads", status="PASS"),
            dict(level="L2", file="F", feature="names", status="FAIL"),
            dict(level="L2", file="F", feature="POIs", status="SKIP")]
    good = [dict(r) for r in base]
    statuses = lambda res: [k for k, _ in res]
    ok(statuses(check_baseline(good, base)) == [], "identical baseline clean")
    degraded = [dict(r) for r in good]
    degraded[0]["status"] = "FAIL"
    ok("REGRESSION" in statuses(check_baseline(degraded, base)),
       "PASS->FAIL regresses")
    skipped = [dict(r) for r in good]
    skipped[0]["status"] = "SKIP"
    ok("REGRESSION" in statuses(check_baseline(skipped, base)),
       "PASS->SKIP regresses")
    not_covered = [dict(r) for r in good]
    not_covered[0]["status"] = "NOT_COVERED"
    ok("REGRESSION" in statuses(check_baseline(not_covered, base)),
       "PASS->NOT_COVERED regresses")
    missing_pass = [r for r in good if r["feature"] != "roads"]
    ok(any(k == "REGRESSION" and "MISSING" in m
           for k, m in check_baseline(missing_pass, base)),
       "deleted PASS key regresses")
    missing_skip = [r for r in good if r["feature"] != "POIs"]
    ok(any(k == "DROPPED" and "MISSING" in m
           for k, m in check_baseline(missing_skip, base)),
       "deleted non-PASS key is DROPPED (report only)")
    improved = [dict(r) for r in good]
    improved[1]["status"] = "PASS"
    ok("IMPROVEMENT" in statuses(check_baseline(improved, base)) and
       "REGRESSION" not in statuses(check_baseline(improved, base)),
       "FAIL->PASS is improvement only")
    improved[1]["status"] = "SKIP"
    ok("IMPROVEMENT" in statuses(check_baseline(improved, base)) and
       "REGRESSION" not in statuses(check_baseline(improved, base)),
       "FAIL->SKIP is improvement only")
    skip_to_pass = [dict(r) for r in good]
    skip_to_pass[2]["status"] = "PASS"
    ok("IMPROVEMENT" in statuses(check_baseline(skip_to_pass, base)),
       "SKIP->PASS is improvement")
    skip_to_fail = [dict(r) for r in good]
    skip_to_fail[2]["status"] = "FAIL"
    ok("REGRESSION" in statuses(check_baseline(skip_to_fail, base)),
       "SKIP->FAIL regresses (H57 falsifier)")
    ok("NEW" in statuses(check_baseline(good + [
        dict(level="L2", file="F", feature="geometry", status="PASS")], base)),
        "new key is informational")
    ok("DUPLICATE" in statuses(check_baseline(good + [dict(good[0])], base)),
       "duplicate baseline key is reported")
    for error in errors:
        print("SELFTEST FAIL:", error)
    print(f"l1l2_matrix self-test: {count - len(errors)}/{count} checks OK")
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--input", metavar="PATH",
                        help="l1l2_fixtures JSON (checks) or matrix JSON (rows)")
    parser.add_argument("--json", metavar="PATH", help="write matrix JSON")
    parser.add_argument("--md", metavar="PATH", help="write matrix Markdown")
    parser.add_argument("--no-stdout-md", action="store_true")
    parser.add_argument("--check-baseline", metavar="PATH")
    parser.add_argument("--write-baseline", metavar="PATH",
                        help="write a baseline from --input (no vendor bytes)")
    args = parser.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not args.input:
        parser.error("--input PATH is required unless --selftest is used")

    rows = load_rows(args.input)
    messages: list[tuple[str, str]] = []
    if args.check_baseline:
        messages = check_baseline(rows, baseline_rows(args.check_baseline))
    if args.write_baseline:
        write_baseline(rows, args.write_baseline)

    rendered = [f"{kind}: {msg}" for kind, msg in messages]
    report = make_report(rows, args.check_baseline or "", rendered)
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n",
                                   encoding="utf-8")
    md = render_markdown(report)
    if args.md:
        Path(args.md).write_text(md, encoding="utf-8")
    if not args.no_stdout_md and not (args.json or args.md):
        print(md, end="")
    for line in rendered:
        print(line)
    regression = any(kind == "REGRESSION" for kind, _ in messages)
    return 1 if regression or not report["summary"]["ok"] else 0


if __name__ == "__main__":
    sys.exit(main())
