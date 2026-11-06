#!/usr/bin/env python3
"""L3 rung of the verification ladder: run every declared L3 target.

``l3check.py`` is the L3 counterpart of ``cardcheck.py`` (L1) and
``l2check.py`` (L2).  It takes a corpus built by
``tools/l3_harness/corpus.py`` (or one supplied with ``--corpus``), asks
``tools/l3_harness/runner.py`` to run every target declared in
``tools/l3_harness/targets.json``, and reports one status per target:

============  ==============================================================
``PASS``      the engine's verdict matched the target's expectation
``FAIL``      a mismatch, an invalid input, or a target that could not run
``SKIP``      the requested back end is absent; nothing is claimed
``BLOCKED``   the reader has no located entry point; nothing is claimed
============  ==============================================================

Exit codes: ``0`` every runnable target passed (blocked/skipped targets are
counted, not failed), ``1`` a target failed or the corpus/inputs were invalid,
``2`` usage error, ``3`` nothing was runnable (every target blocked or
skipped; no verdict is claimed).

The tool never fakes a pass.  A reader that is not located is ``BLOCKED`` no
matter how good the corpus is, an absent back end is ``SKIP``, a missing
corpus file is a ``FAIL``, and a synthetic PASS proves only that the
runner/dispatcher path works -- not that the firmware accepts a card.  Every
row carries its reader ID and the claim IDs its evidence rests on.

``--root`` and ``--image`` are accepted for the ladder interface and recorded
in the report, but card-level L3 is **M9.12** (``l3check.py --card``); today
they are not evidence and are reported as such.

Usage::

    python3 tools/l3check.py --build-corpus
    python3 tools/l3check.py --corpus /tmp/opencode/l3-corpus
    python3 tools/l3check.py --corpus /tmp/opencode/l3-corpus --target probe-zlib-cmf
    python3 tools/l3check.py --corpus /tmp/opencode/l3-corpus --json
    python3 tools/l3check.py --selftest
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from l3_harness import corpus as corpus_mod  # noqa: E402
from l3_harness import engine as engine_mod  # noqa: E402
from l3_harness import manifest as manifest_mod  # noqa: E402
from l3_harness import runner as runner_mod  # noqa: E402

SCHEMA = "osm2leaf.l3check/v1"

#: Reservation from TODO M9.8 (C-1700-C-1709); this tool uses C-1700.
TOOL_CLAIM = "C-1700"
EXP_RECORD = "EXP-2026-11-06-M9.8-l3check"

#: One row per target in ``targets.json``: the reader under test and the claim
#: IDs its evidence rests on.  C-1670 is the runner, C-1690 the corpus (both
#: pipeline evidence); a blocked row names the claims that describe its
#: blocker, and C-520/C-528 mark the retired map-code comparator.  The table is
#: validated against ``targets.json`` on every run: a target added or renamed
#: there makes this tool FAIL instead of silently dropping it.
TARGET_EVIDENCE = {
    "probe-zlib-cmf": {
        "reader": "synthetic",
        "claims": ("C-1670", "C-1690"),
        "note": "runner and corpus claim; the probe is a pipeline fixture",
    },
    "hddinfo_compare": {
        "reader": "hdd_info",
        "claims": ("C-521",),
        "note": "HDD_INFO literals are located; the parser is behind a COM object",
    },
    "cmp_ind_reader": {
        "reader": "cmp_ind",
        "claims": (),
        "note": "no .cmp/.ind reader entry point yet",
    },
    "tile_reader": {
        "reader": "tile",
        "claims": (),
        "note": "no tile reader entry point yet",
    },
    "drstr_parser": {
        "reader": "drstr",
        "claims": (),
        "note": "no DRSTR parser entry point yet",
    },
    "mapcode_comparator": {
        "reader": "hdd_info",
        "claims": ("C-520", "C-528"),
        "note": "retired BT_MGR.dll chain; kept blocked on purpose",
    },
}

STATUSES = ("PASS", "FAIL", "SKIP", "BLOCKED")

#: ``runner.py`` status -> ladder status.  A missing entry means the runner
#: returned something this tool does not understand, which is a FAIL.
_RUNNER_STATUS = {
    "PASS": "PASS",
    "SKIP": "SKIP",
    "BLOCKED": "BLOCKED",
    "MISMATCH": "FAIL",
    "INVALID": "FAIL",
}

_CLAIM_RE = re.compile(r"^C-\d+$")


class UsageError(ValueError):
    """The command line cannot be turned into a run."""


# --------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------


def _temp_corpus_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="l3check-corpus-"))


def _resolve_corpus(args) -> tuple[dict, dict | None]:
    """Build or validate the corpus; never invent one that was not asked for."""

    if getattr(args, "corpus", None) and getattr(args, "build_corpus", False):
        raise UsageError("pass either --corpus DIR or --build-corpus, not both")

    built = None
    if getattr(args, "corpus", None):
        root = Path(args.corpus).expanduser()
        source = "supplied"
    else:
        root = _temp_corpus_root()
        source = "built"
        try:
            built = corpus_mod.build_corpus(root)
        except (corpus_mod.CorpusError, manifest_mod.ManifestError, OSError) as exc:
            return (
                {
                    "root": str(root),
                    "manifest": str(root / "manifest.json"),
                    "source": source,
                    "entries": 0,
                    "problems": [f"corpus build failed: {exc}"],
                    "kept": True,
                },
                None,
            )

    manifest_path = root / "manifest.json"
    info = {
        "root": str(root),
        "manifest": str(manifest_path),
        "source": source,
        "entries": 0,
        "problems": [],
        "kept": source == "built",
    }
    if built is not None:
        info["build"] = {
            "entries": built["entries"],
            "skipped": list(built["skipped"]),
        }

    try:
        doc = manifest_mod.load(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        info["problems"].append(f"cannot read {manifest_path}: {exc}")
        return info, None

    info["entries"] = len(doc.get("corpus", []))
    info["problems"] = manifest_mod.validate(doc, root=root)
    return info, doc


def _card_info(args) -> dict | None:
    if not (getattr(args, "root", None) or getattr(args, "image", None)):
        return None
    return {
        "status": "NOT_IMPLEMENTED",
        "checked": False,
        "task": "M9.12",
        "root": getattr(args, "root", None),
        "image": getattr(args, "image", None),
        "note": (
            "card-level L3 (l3check.py --card) is M9.12; these paths are "
            "recorded, not checked, and are not evidence"
        ),
    }


# --------------------------------------------------------------------------
# Targets
# --------------------------------------------------------------------------


def _evidence_problems(by_name: dict[str, dict]) -> list[str]:
    """Return every drift between ``TARGET_EVIDENCE`` and ``targets.json``."""

    problems: list[str] = []
    declared = set(by_name)
    known = set(TARGET_EVIDENCE)
    for name in sorted(declared - known):
        problems.append(
            f"target {name!r} has no reader/claim row in TARGET_EVIDENCE"
        )
    for name in sorted(known - declared):
        problems.append(
            f"TARGET_EVIDENCE lists {name!r}, which targets.json does not declare"
        )
    for name in sorted(declared & known):
        row = TARGET_EVIDENCE[name]
        target = by_name[name]
        if row["reader"] != target["reader"]:
            problems.append(
                f"{name}: evidence reader {row['reader']!r} != target reader "
                f"{target['reader']!r}"
            )
        for claim in row["claims"]:
            if not _CLAIM_RE.match(claim):
                problems.append(f"{name}: {claim!r} is not a claim ID")
    return problems


def _select_targets(by_name: dict[str, dict], requested) -> list[dict]:
    if not requested:
        return list(by_name.values())
    unknown = [name for name in requested if name not in by_name]
    if unknown:
        raise UsageError(
            f"unknown target(s) {', '.join(repr(n) for n in unknown)}; known: "
            f"{', '.join(sorted(by_name))}"
        )
    selected: list[str] = []
    for name in requested:
        if name not in selected:
            selected.append(name)
    return [by_name[name] for name in selected]


def _run_one(target: dict, corpus_root: Path, engine: str) -> dict:
    """Run one target through ``runner.run_target``; never raise at the caller."""

    evidence = TARGET_EVIDENCE[target["name"]]
    namespace = argparse.Namespace(
        engine=engine,
        input=None,
        corpus=str(corpus_root),
        max_insns=engine_mod.DEFAULT_MAX_INSNS,
        dry_run=False,
    )
    try:
        payload = runner_mod.run_target(target, namespace)
    except Exception as exc:  # noqa: BLE001 - one target must not abort the run
        payload = {
            "status": "INVALID",
            "exit": runner_mod.EXIT_INVALID,
            "problems": [f"runner error: {type(exc).__name__}: {exc}"],
            "reason": None,
            "l3_claim": False,
        }

    status = _RUNNER_STATUS.get(payload.get("status"), "FAIL")
    problems = list(payload.get("problems") or [])
    if payload.get("status") not in _RUNNER_STATUS:
        problems.append(f"runner returned unknown status {payload.get('status')!r}")
    expect = (target.get("expect") or {}).get("verdict")
    input_info = payload.get("input") or None

    return {
        "name": target["name"],
        "reader": target["reader"],
        "entry": (target.get("entry") or {}).get("kind"),
        "claims": list(evidence["claims"]),
        "claim_note": evidence["note"],
        "expected": expect,
        "status": status,
        "verdict": payload.get("verdict"),
        "accepted": payload.get("accepted"),
        "reason": payload.get("reason"),
        "problems": problems,
        "engine": payload.get("engine") or engine,
        "backend": payload.get("backend"),
        "synthetic": payload.get("synthetic"),
        "l3_claim": payload.get("l3_claim", False),
        "steps": payload.get("cycles"),
        "stub_calls": len(payload.get("stub_calls") or []),
        "input": input_info,
        "runner_exit": payload.get("exit"),
    }


def _counts(rows: list[dict]) -> dict:
    counts = {"pass": 0, "fail": 0, "skip": 0, "blocked": 0}
    for row in rows:
        counts[row["status"].lower()] += 1
    counts["runnable"] = counts["pass"] + counts["fail"]
    counts["total"] = len(rows)
    return counts


def _result(counts: dict) -> tuple[str, int]:
    if counts["fail"]:
        return "FAIL", 1
    if counts["runnable"] == 0:
        return "NO_RUNNABLE", 3
    return "PASS", 0


def build_report(args) -> dict:
    """Build the whole report; the CLI and the self-test share this path."""

    try:
        by_name, targets_doc = runner_mod.load_targets(
            getattr(args, "targets", None)
        )
    except runner_mod.TargetError as exc:
        return {
            "schema": SCHEMA,
            "command": "l3check",
            "claim": TOOL_CLAIM,
            "exp": EXP_RECORD,
            "engine": getattr(args, "engine", "pysh4"),
            "corpus": None,
            "card": _card_info(args),
            "targets": [],
            "counts": {"pass": 0, "fail": 0, "skip": 0, "blocked": 0,
                       "runnable": 0, "total": 0},
            "result": "FAIL",
            "exit": 1,
            "problems": [f"targets.json: {problem}" for problem in exc.problems],
            "note": "no target ran; a broken target table is not a pass",
        }

    problems = _evidence_problems(by_name)
    if problems:
        return {
            "schema": SCHEMA,
            "command": "l3check",
            "claim": TOOL_CLAIM,
            "exp": EXP_RECORD,
            "engine": getattr(args, "engine", "pysh4"),
            "corpus": None,
            "card": _card_info(args),
            "targets": [],
            "counts": {"pass": 0, "fail": 0, "skip": 0, "blocked": 0,
                       "runnable": 0, "total": 0},
            "result": "FAIL",
            "exit": 1,
            "problems": problems,
            "note": "the reader/claim table is out of step with targets.json",
        }

    corpus_info, corpus_doc = _resolve_corpus(args)
    if corpus_info["problems"]:
        return {
            "schema": SCHEMA,
            "command": "l3check",
            "claim": TOOL_CLAIM,
            "exp": EXP_RECORD,
            "engine": getattr(args, "engine", "pysh4"),
            "corpus": corpus_info,
            "card": _card_info(args),
            "targets": [],
            "counts": {"pass": 0, "fail": 0, "skip": 0, "blocked": 0,
                       "runnable": 0, "total": 0},
            "result": "FAIL",
            "exit": 1,
            "problems": list(corpus_info["problems"]),
            "note": "the corpus is invalid, so no target was run",
        }

    selected = _select_targets(by_name, getattr(args, "target", None) or [])
    engine = getattr(args, "engine", "pysh4")
    root = Path(corpus_info["root"])
    rows = [_run_one(target, root, engine) for target in selected]
    counts = _counts(rows)
    result, exit_code = _result(counts)

    return {
        "schema": SCHEMA,
        "command": "l3check",
        "claim": TOOL_CLAIM,
        "exp": EXP_RECORD,
        "engine": engine,
        "corpus": corpus_info,
        "card": _card_info(args),
        "targets": rows,
        "counts": counts,
        "result": result,
        "exit": exit_code,
        "problems": [],
        "target_count": len(targets_doc.get("targets", [])),
        "note": (
            "a PASS on a synthetic target proves the runner/dispatcher path, "
            "not that the firmware accepts a card; BLOCKED and SKIP claim "
            "nothing and are counted, not failed"
        ),
    }


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def _detail(row: dict) -> str:
    if row["status"] == "PASS":
        text = f"{row['verdict']} (expected {row['expected']})"
        extra = []
        if row["steps"] is not None:
            extra.append(f"{row['steps']} steps")
        if row["engine"]:
            extra.append(row["engine"])
        if row["input"] and row["input"].get("path"):
            extra.append(row["input"]["path"])
        return text + (", " + ", ".join(extra) if extra else "")
    if row["status"] in ("SKIP", "BLOCKED"):
        return row["reason"] or "-"
    return "; ".join(row["problems"]) or row["reason"] or "no detail"


def _print_report(report: dict) -> None:
    print(f"l3check: L3 rung of the verification ladder (claim {TOOL_CLAIM})")
    print(f"exp      {EXP_RECORD}")
    if report["corpus"] is None:
        print("corpus   -")
    else:
        corpus = report["corpus"]
        print(
            f"corpus   {corpus['root']} ({corpus['source']}"
            f"; {corpus['entries']} entries"
            + (", kept" if corpus.get("kept") else "")
            + ")"
        )
    if report["card"]:
        print("card     not checked (--root/--image recorded; card mode is M9.12)")
    print(f"engine   {report['engine']}")

    for problem in report.get("problems", []):
        print(f"FAIL {problem}")
    if not report["targets"]:
        print(f"RESULT: {report['result']} (no target ran; exit {report['exit']})")
        return

    header = ("target", "reader", "entry", "claims", "RESULT")
    rows = [
        (
            row["name"],
            row["reader"],
            row["entry"] or "-",
            ",".join(row["claims"]) or "-",
            row["status"],
        )
        for row in report["targets"]
    ]
    widths = [len(item) for item in header]
    for row in rows:
        widths = [max(width, len(cell)) for width, cell in zip(widths, row)]
    print()
    print("  ".join(cell.ljust(width) for cell, width in zip(header, widths)))
    for row in rows:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)))

    details = [
        (row["name"], row["status"], _detail(row))
        for row in report["targets"]
        if row["status"] != "PASS"
    ]
    if details:
        print()
        for name, status, detail in details:
            print(f"  {status} {name}: {detail}")

    counts = report["counts"]
    print()
    print(
        f"counts   pass={counts['pass']} fail={counts['fail']} "
        f"skip={counts['skip']} blocked={counts['blocked']} "
        f"runnable={counts['runnable']}/{counts['total']}"
    )
    if report["result"] == "PASS":
        print(
            "RESULT: PASS (every runnable target passed; "
            f"{counts['blocked']} blocked, {counts['skip']} skipped)"
        )
    elif report["result"] == "NO_RUNNABLE":
        print(
            "RESULT: NO_RUNNABLE (exit 3; every target is blocked or skipped, "
            "nothing was claimed)"
        )
    else:
        print(f"RESULT: FAIL ({counts['fail']} target(s) failed; exit 1)")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="L3 rung of the verification ladder (M9.8)",
        epilog=(
            "Exit codes: 0 every runnable target passed, 1 a target failed or "
            "an input was invalid, 2 usage error, 3 nothing was runnable."
        ),
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--root", help="card tree (recorded; card mode is M9.12)")
    source.add_argument("--image", help="card image (recorded; card mode is M9.12)")
    parser.add_argument(
        "--corpus",
        help="corpus root built by tools/l3_harness/corpus.py (needs manifest.json)",
    )
    parser.add_argument(
        "--build-corpus",
        action="store_true",
        help="build a fresh corpus in a new temporary directory",
    )
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        metavar="NAME",
        help="run only this target (repeatable; default: every declared target)",
    )
    parser.add_argument(
        "--engine",
        default="pysh4",
        help="back end for every target: %s (default: pysh4)"
        % ", ".join(sorted(engine_mod.BACKENDS)),
    )
    parser.add_argument(
        "--targets",
        help="path to targets.json (default: tools/l3_harness/targets.json)",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="synthetic self-test: probe target, blocked target, FAIL/SKIP paths",
    )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()

    if args.engine not in engine_mod.BACKENDS:
        print(
            f"error: unknown engine {args.engine!r} "
            f"(known: {', '.join(sorted(engine_mod.BACKENDS))})",
            file=sys.stderr,
        )
        return 2

    try:
        report = build_report(args)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report)
    return report["exit"]


# --------------------------------------------------------------------------
# Self-test: synthetic target + blocked target + honest FAIL/SKIP paths
# --------------------------------------------------------------------------

CHECKS: list[tuple[str, callable]] = []
SKIPS: list[str] = []
_SELFTEST_CORPUS: Path | None = None
_SELFTEST_TMP: Path | None = None


def check(name):
    def register(func):
        CHECKS.append((name, func))
        return func

    return register


def _cli(argv) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        code = main(argv)
    return code, buffer.getvalue()


def _json_cli(argv) -> tuple[int, dict]:
    code, output = _cli([*argv, "--json"])
    try:
        return code, json.loads(output)
    except json.JSONDecodeError:
        raise AssertionError(f"not JSON (exit {code}): {output}") from None


def _corpus() -> Path:
    assert _SELFTEST_CORPUS is not None
    return _SELFTEST_CORPUS


@check("targets: targets.json and the reader/claim table agree")
def test_evidence_table():
    by_name, _doc = runner_mod.load_targets()
    problems = _evidence_problems(by_name)
    assert not problems, problems
    assert TOOL_CLAIM == "C-1700"
    assert TARGET_EVIDENCE["probe-zlib-cmf"]["reader"] == "synthetic"
    assert TARGET_EVIDENCE["mapcode_comparator"]["claims"] == ("C-520", "C-528")
    for row in TARGET_EVIDENCE.values():
        for claim in row["claims"]:
            assert _CLAIM_RE.match(claim), claim


@check("run: the synthetic target PASSes and the five unlocated readers are BLOCKED")
def test_full_run():
    code, report = _json_cli(["--corpus", str(_corpus())])
    assert code == 0, report
    assert report["result"] == "PASS", report
    assert report["claim"] == "C-1700"
    assert report["engine"] == "pysh4"
    assert report["corpus"]["source"] == "supplied", report["corpus"]
    assert report["corpus"]["entries"] == 108, report["corpus"]
    rows = {row["name"]: row for row in report["targets"]}
    probe = rows["probe-zlib-cmf"]
    assert probe["status"] == "PASS", probe
    assert probe["verdict"] == "ACCEPT" and probe["expected"] == "ACCEPT", probe
    assert probe["claims"] == ["C-1670", "C-1690"], probe
    assert probe["synthetic"] is True and probe["l3_claim"] is False, probe
    assert probe["input"]["manifest_sha256_match"] is True, probe["input"]
    assert probe["steps"] and probe["steps"] > 0, probe
    blocked = sorted(name for name, row in rows.items() if row["status"] == "BLOCKED")
    assert blocked == [
        "cmp_ind_reader",
        "drstr_parser",
        "hddinfo_compare",
        "mapcode_comparator",
        "tile_reader",
    ], blocked
    for name in blocked:
        row = rows[name]
        assert row["verdict"] is None and row["accepted"] is None, row
        assert row["l3_claim"] is False and row["reason"], row
        assert row["claims"] == list(TARGET_EVIDENCE[name]["claims"]), row
    assert report["counts"] == {
        "pass": 1, "fail": 0, "skip": 0, "blocked": 5,
        "runnable": 1, "total": 6,
    }, report["counts"]


@check("run: --target selects exactly one target (PASS)")
def test_single_target():
    code, report = _json_cli(
        ["--corpus", str(_corpus()), "--target", "probe-zlib-cmf"]
    )
    assert code == 0, report
    assert [row["name"] for row in report["targets"]] == ["probe-zlib-cmf"], report
    assert report["counts"]["total"] == 1, report["counts"]
    assert report["targets"][0]["status"] == "PASS", report["targets"]


@check("run: a blocked target is exit 3 and claims no verdict")
def test_blocked_target():
    code, report = _json_cli(
        ["--corpus", str(_corpus()), "--target", "hddinfo_compare"]
    )
    assert code == 3, report
    assert report["result"] == "NO_RUNNABLE", report
    row = report["targets"][0]
    assert row["status"] == "BLOCKED" and row["verdict"] is None, row
    assert row["l3_claim"] is False and row["reason"], row
    assert report["counts"]["runnable"] == 0, report["counts"]
    assert report["counts"]["blocked"] == 1, report["counts"]


@check("run: a blocked target needs no corpus input (nothing is invented)")
def test_blocked_needs_no_input():
    missing = Path(_SELFTEST_TMP) / "no-such-corpus"
    by_name, _doc = runner_mod.load_targets()
    row = _run_one(by_name["cmp_ind_reader"], missing, "pysh4")
    assert row["status"] == "BLOCKED", row
    assert row["verdict"] is None and row["input"] is None, row
    assert row["l3_claim"] is False, row


@check("run: a tampered corpus makes the probe FAIL (never a pass)")
def test_tampered_corpus():
    target = Path(_SELFTEST_TMP) / "tampered"
    shutil.copytree(_corpus(), target)
    relative = "cmp/factory/ADDRE001.DAT.cmp"
    victim = target / relative
    data = bytearray(victim.read_bytes())
    data[0] = 0x00                      # no longer the zlib CMF 0x78
    victim.write_bytes(bytes(data))

    manifest_path = target / "manifest.json"
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    import hashlib

    digest = hashlib.sha256(bytes(data)).hexdigest()
    for entry in doc["corpus"]:
        if entry["path"] == relative:
            entry["sha256"] = digest
            entry["size"] = len(data)
    manifest_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    code, report = _json_cli(
        ["--corpus", str(target), "--target", "probe-zlib-cmf"]
    )
    assert code == 1, report
    assert report["result"] == "FAIL", report
    row = report["targets"][0]
    assert row["status"] == "FAIL", row
    assert row["verdict"] == "REJECT", row
    assert any("expects ACCEPT" in problem for problem in row["problems"]), row
    assert row["input"]["manifest_sha256_match"] is True, row["input"]


@check("run: a corpus without manifest.json is invalid and runs nothing")
def test_missing_manifest():
    empty = Path(_SELFTEST_TMP) / "empty-corpus"
    empty.mkdir()
    code, report = _json_cli(["--corpus", str(empty)])
    assert code == 1, report
    assert report["result"] == "FAIL" and report["targets"] == [], report
    assert any("manifest.json" in problem for problem in report["problems"]), report


@check("run: an absent back end is SKIP, never PASS")
def test_backend_skip():
    available = next(
        item for item in engine_mod.probe_all(["ghidra"])
    )
    code, report = _json_cli(
        ["--corpus", str(_corpus()), "--target", "probe-zlib-cmf",
         "--engine", "ghidra"]
    )
    row = report["targets"][0]
    if not available.available:
        assert available.code == "MISSING_GHIDRA", available.as_dict()
        assert code == 3, report
        assert row["status"] == "SKIP" and row["verdict"] is None, row
        assert row["l3_claim"] is False, row
        assert "MISSING_GHIDRA" in row["reason"], row
        SKIPS.append(f"ghidra: {available.code} - {available.detail}")
        return
    assert row["status"] != "SKIP", row


@check("run: --build-corpus builds into a temporary directory")
def test_build_corpus():
    code, report = _json_cli(
        ["--build-corpus", "--target", "probe-zlib-cmf"]
    )
    try:
        assert code == 0, report
        corpus = report["corpus"]
        assert corpus["source"] == "built" and corpus["kept"] is True, corpus
        assert corpus["entries"] == 108, corpus
        assert Path(corpus["root"]).is_dir(), corpus
        assert (Path(corpus["root"]) / "manifest.json").is_file(), corpus
        assert report["targets"][0]["status"] == "PASS", report["targets"]
    finally:
        root = (report.get("corpus") or {}).get("root")
        if root:
            shutil.rmtree(root, ignore_errors=True)


@check("cli: an unknown --target is a usage error (exit 2)")
def test_unknown_target():
    code, output = _cli(
        ["--corpus", str(_corpus()), "--target", "no-such-target"]
    )
    assert code == 2, output
    assert "unknown target" in output, output


@check("cli: --corpus together with --build-corpus is a usage error")
def test_conflicting_corpus_flags():
    code, output = _cli(["--corpus", str(_corpus()), "--build-corpus"])
    assert code == 2, output
    assert "not both" in output, output


@check("run: two runs give the same verdicts")
def test_determinism():
    first = _json_cli(["--corpus", str(_corpus())])[1]
    second = _json_cli(["--corpus", str(_corpus())])[1]
    assert first == second, "two runs differ"


def run_selftest() -> int:
    global _SELFTEST_CORPUS, _SELFTEST_TMP

    failures = 0
    with tempfile.TemporaryDirectory(prefix="l3check-selftest-") as tmp:
        _SELFTEST_TMP = Path(tmp)
        _SELFTEST_CORPUS = Path(tmp) / "corpus"
        try:
            corpus_mod.build_corpus(_SELFTEST_CORPUS)
        except (corpus_mod.CorpusError, manifest_mod.ManifestError, OSError) as exc:
            print(f"FAIL corpus fixture: {exc}")
            print("\nl3check selftest: FAILED (0/1 checks)")
            return 1

        for name, func in CHECKS:
            try:
                func()
            except Exception as exc:  # noqa: BLE001 - report, do not abort
                failures += 1
                print(f"FAIL {name}: {exc}")
                if "--verbose" in sys.argv[1:]:
                    import traceback

                    traceback.print_exc()
            else:
                print(f"ok   {name}")
        for skip in SKIPS:
            print(f"skip {skip}")

    total = len(CHECKS)
    print()
    if failures:
        print(f"l3check selftest: FAILED ({failures}/{total} checks)")
        return 1
    print(
        f"l3check selftest: OK ({total} checks"
        + (f", {len(SKIPS)} skipped" if SKIPS else "")
        + ")"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
