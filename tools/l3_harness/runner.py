#!/usr/bin/env python3
"""L3 harness runner: validate the plan, print it, and refuse to fake a pass.

Three commands:

``check``
    Validate the corpus manifest (shape, hashes when ``--root`` is given) and
    the Ghidra memory map.  Exit ``1`` on any problem.
``plan``
    Print the trace targets, the readers that still have no entry point, the
    stubs each reader needs and the remaining blockers.  Never claims a reader
    is runnable.
``run``
    Look for Ghidra's ``analyzeHeadless``.  Without it, print
    ``MISSING_GHIDRA`` plus exact install instructions and exit ``3``.  With
    Ghidra but without the harness script, a located reader or the firmware
    image, print ``BLOCKED`` and exit ``4``.  Only an actual Ghidra run whose
    result matches every manifest verdict may exit ``0``.

Exit codes: ``0`` pass, ``1`` invalid inputs, ``2`` usage error,
``3`` Ghidra missing, ``4`` blocked, ``5`` result mismatch.

Usage::

    python3 tools/l3_harness/runner.py check --manifest m.json --rommap r.json
    python3 tools/l3_harness/runner.py plan  --manifest m.json --rommap r.json
    python3 tools/l3_harness/runner.py run   --manifest m.json --rommap r.json \\
        --image archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img
    python3 tools/l3_harness/runner.py selftest
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from l3_harness import manifest as manifest_mod  # noqa: E402
from l3_harness import rommap as rommap_mod  # noqa: E402
from l3_harness import stubs as stubs_mod  # noqa: E402

HERE = Path(__file__).resolve().parent
HARNESS_SCRIPT = HERE / "ghidra" / "l3_run.py"

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_MISSING_GHIDRA = 3
EXIT_BLOCKED = 4
EXIT_MISMATCH = 5

DEFAULT_SEARCH_ROOTS = ("/opt", "/usr/local", "/usr/share", "~")

#: Anchors recorded by earlier firmware work.  ``status`` deliberately
#: distinguishes a file offset from a link-time VA: a file offset is not
#: runnable until the memory map binds it.
TRACE_TARGETS = [
    {
        "id": "mapcode-comparator",
        "reader": "hdd_info",
        "role": "helper",
        "what": "map-code comparator chain (Sys[...] vs SD[...])",
        "anchor": "0x6fab2c -> 0x6faeb0 -> 0x6fb05c, data delta 0x02800000",
        "status": "located-file-offset",
        "note": (
            "file offsets, not VAs; the HDD_INFO parser itself is behind a "
            "runtime COM object and is not located"
        ),
    },
    {
        "id": "hdd-info-parser",
        "reader": "hdd_info",
        "role": "reader",
        "what": "HDD_INFO.TXT parser",
        "anchor": None,
        "status": "unknown",
        "note": "reached through a runtime COM object",
    },
    {
        "id": "cmp-ind-reader",
        "reader": "cmp_ind",
        "role": "reader",
        "what": ".cmp/.ind container reader (zlib calls, descriptor fields)",
        "anchor": None,
        "status": "unknown",
        "note": "no literal map filename exists; must be traced from the TOC",
    },
    {
        "id": "tile-reader",
        "reader": "tile",
        "role": "reader",
        "what": "MAPAL001 tile reader (MESH_ID/DIVID, 0x1ac level table)",
        "anchor": None,
        "status": "unknown",
        "note": "no entry point recovered",
    },
    {
        "id": "drstr-parser",
        "reader": "drstr",
        "role": "reader",
        "what": "DRSTR001.DAT tree parser (40-byte nodes, 32-byte entries)",
        "anchor": None,
        "status": "unknown",
        "note": "no entry point recovered",
    },
    {
        "id": "cmp-lst-opener",
        "reader": "cmp_lst",
        "role": "reader",
        "what": "CMP.LST / map-path opener",
        "anchor": "0xc438a4",
        "status": "refuted",
        "note": (
            "0xc438a4 is a stats formatter, not the opener; map filenames "
            "have zero literal references"
        ),
    },
    {
        "id": "anchor-c0ebf8",
        "reader": None,
        "role": "anchor",
        "what": "old call-graph anchor",
        "anchor": "0xc0ebf8",
        "status": "anchor-only",
        "note": "proposed in feedback-loop.md; no reader proven",
    },
    {
        "id": "anchor-c48380",
        "reader": None,
        "role": "anchor",
        "what": "old call-graph anchor",
        "anchor": "0xc48380",
        "status": "anchor-only",
        "note": "proposed in feedback-loop.md; no reader proven",
    },
    {
        "id": "anchor-c42520",
        "reader": None,
        "role": "anchor",
        "what": "NaviStateCC fd method candidate",
        "anchor": "0xc42520",
        "status": "anchor-only",
        "note": "COM vtable is built at runtime, so a static hook is missing",
    },
]


def _load_inputs(args):
    """Load and validate both input documents; return (docs, problems)."""

    problems: list[str] = []
    docs: dict[str, dict] = {}

    try:
        docs["manifest"] = manifest_mod.load(args.manifest)
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"manifest: cannot read {args.manifest}: {exc}")
    else:
        root = getattr(args, "root", None)
        for problem in manifest_mod.validate(
            docs["manifest"], root=root, check_files=bool(root)
        ):
            problems.append(f"manifest: {problem}")

    try:
        docs["rommap"] = rommap_mod.load(args.rommap)
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"rommap: cannot read {args.rommap}: {exc}")
    else:
        for problem in rommap_mod.validate(docs["rommap"]):
            problems.append(f"rommap: {problem}")

    return docs, problems


def _corpus_summary(doc):
    readers: dict[str, dict] = {}
    for entry in doc.get("corpus", []):
        reader = entry.get("reader")
        info = readers.setdefault(
            reader, {"entries": 0, "cases": [], "verdicts": []}
        )
        info["entries"] += 1
        if entry.get("case") not in info["cases"]:
            info["cases"].append(entry.get("case"))
        if entry.get("expected") not in info["verdicts"]:
            info["verdicts"].append(entry.get("expected"))
    return readers


def build_plan(manifest_doc, rommap_doc) -> dict:
    readers = _corpus_summary(manifest_doc)
    located = {
        target["reader"]
        for target in TRACE_TARGETS
        if target["status"] == "located-file-offset"
        and target.get("role") == "reader"
        and target["reader"]
    }

    reader_plan = []
    for reader in sorted(readers):
        reader_plan.append(
            {
                "reader": reader,
                "entries": readers[reader]["entries"],
                "cases": sorted(readers[reader]["cases"]),
                "verdicts": sorted(readers[reader]["verdicts"]),
                "stubs": stubs_mod.READER_STUBS.get(reader, []),
                "entry_point": (
                    "located-file-offset"
                    if reader in located
                    else "UNKNOWN (no runnable entry point)"
                ),
            }
        )

    blockers = [
        f"reader {reader} has no runnable entry point"
        for reader in sorted(readers)
        if reader not in located
    ]
    blockers.append(
        f"Ghidra harness script {HARNESS_SCRIPT.relative_to(HERE.parent.parent)} "
        "is not written"
    )
    blockers.append(
        "no Ghidra run has produced a result JSON yet; L3 is not claimed"
    )

    blocks = rommap_doc.get("blocks", [])
    return {
        "status": "BLOCKED",
        "corpus": {
            "entries": len(manifest_doc.get("corpus", [])),
            "readers": reader_plan,
        },
        "rommap": {
            "segment_index": rommap_doc.get("source", {}).get("segment_index"),
            "segment_base": rommap_doc.get("source", {}).get("segment_base"),
            "processor": rommap_doc.get("processor", {}).get("id"),
            "processor_verified": rommap_doc.get("processor", {}).get("verified"),
            "blocks": len(blocks),
            "loadable": sum(1 for b in blocks if b.get("loadable")),
            "ram": rommap_doc.get("ram") is not None,
            "skipped": len(rommap_doc.get("skipped", [])),
        },
        "stubs": {
            "modeled": sum(1 for s in stubs_mod.STUBS if s["status"] == "modeled"),
            "planned": sum(1 for s in stubs_mod.STUBS if s["status"] == "planned"),
        },
        "trace_targets": TRACE_TARGETS,
        "blockers": blockers,
        "first_run_needs": [
            "tools/cerom.py section table (va, file_offset, size, "
            "characteristics, compressed) for one build",
            "rommap.py convert of that report (one segment, no compressed "
            "sections or an explicit --skip-compressed)",
            "one located reader entry point with a VA from the memory map",
            "Ghidra 12.2+ with analyzeHeadless and a JDK it supports",
            "tools/l3_harness/ghidra/l3_run.py (P-code harness script)",
            "a corpus root matching the manifest, with hashes verified",
            "the firmware image for -import and the reader's expected VA",
        ],
    }


def _ghidra_instructions(args) -> str:
    manifest_arg = args.manifest
    rommap_arg = args.rommap
    image_arg = getattr(args, "image", None) or "<firmware-image>"
    return "\n".join(
        [
            "MISSING_GHIDRA: analyzeHeadless was not found.",
            "",
            "Install Ghidra (12.2 or newer) and a JDK it supports, then either",
            "put analyzeHeadless on PATH or export GHIDRA_INSTALL_DIR:",
            "",
            "  # 1. download and unpack, e.g. to /opt",
            "  #    https://github.com/NationalSecurityAgency/ghidra/releases",
            "  export GHIDRA_INSTALL_DIR=/opt/ghidra_12.2_PUBLIC",
            "  ls \"$GHIDRA_INSTALL_DIR/support/analyzeHeadless\"",
            "",
            "  # 2. re-run the check (no Ghidra needed for this step)",
            f"  python3 tools/l3_harness/runner.py check "
            f"--manifest {manifest_arg} --rommap {rommap_arg}",
            "",
            "  # 3. re-run the harness",
            f"  python3 tools/l3_harness/runner.py run "
            f"--manifest {manifest_arg} --rommap {rommap_arg} "
            f"--image {image_arg}",
            "",
            "A run is only reported as PASS after a real analyzeHeadless run",
            "matches every manifest verdict. Missing Ghidra is exit 3, never 0.",
        ]
    )


def detect_ghidra(explicit=None, env=None, extra_roots=None):
    """Return ``(path_or_None, searched)``.

    ``searched`` is a list of ``(source, candidate)`` pairs, so a failed run
    can tell the user exactly where it looked.
    """

    env = os.environ if env is None else env
    searched: list[tuple[str, str]] = []

    def usable(candidate: Path) -> bool:
        return candidate.is_file() and os.access(candidate, os.X_OK)

    if explicit:
        candidate = Path(explicit).expanduser()
        searched.append(("--headless", str(candidate)))
        return (str(candidate), searched) if usable(candidate) else (None, searched)

    for variable in ("GHIDRA_INSTALL_DIR", "GHIDRA_HOME"):
        value = env.get(variable)
        if not value:
            searched.append((f"${variable}", "unset"))
            continue
        candidate = Path(value) / "support" / "analyzeHeadless"
        searched.append((f"${variable}", str(candidate)))
        if usable(candidate):
            return str(candidate), searched

    on_path = shutil.which(
        "analyzeHeadless", path=env.get("PATH", os.defpath)
    )
    searched.append(("$PATH", on_path or "not found"))
    if on_path:
        return on_path, searched

    roots = DEFAULT_SEARCH_ROOTS if extra_roots is None else tuple(extra_roots)
    home = env.get("HOME")
    for root in roots:
        if root == "~":
            if not home:
                continue
            root = home
        base = Path(root)
        if not base.is_dir():
            continue
        for match in sorted(base.glob("ghidra*")):
            candidate = match / "support" / "analyzeHeadless"
            searched.append(("glob", str(candidate)))
            if usable(candidate):
                return str(candidate), searched

    return None, searched


def cmd_check(args) -> int:
    docs, problems = _load_inputs(args)

    payload = {
        "command": "check",
        "manifest": str(args.manifest),
        "rommap": str(args.rommap),
        "root": getattr(args, "root", None),
        "entries": 0,
        "blocks": 0,
        "problems": problems,
        "result": "FAIL" if problems else "PASS",
    }
    if "manifest" in docs:
        payload["entries"] = len(docs["manifest"].get("corpus", []))
    if "rommap" in docs:
        payload["blocks"] = len(docs["rommap"].get("blocks", []))

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for problem in problems:
            print(f"FAIL {problem}")
        if not problems:
            print(
                f"manifest: {payload['entries']} entries"
                + (
                    f", files verified under {args.root}"
                    if getattr(args, "root", None)
                    else ", file hashes not verified (no --root)"
                )
            )
            print(
                f"rommap: {payload['blocks']} blocks, "
                f"processor {docs['rommap'].get('processor', {}).get('id')} "
                f"(verified={docs['rommap'].get('processor', {}).get('verified')})"
            )
            print("RESULT: PASS")
        else:
            print(f"RESULT: FAIL ({len(problems)} problem(s))")

    return EXIT_OK if not problems else EXIT_INVALID


def _print_plan(plan: dict) -> None:
    corpus = plan["corpus"]
    print("L3 plan (design only; nothing below is claimed as run)")
    print("=" * 66)
    print(f"corpus: {corpus['entries']} entries")
    for reader in corpus["readers"]:
        verdicts = "/".join(reader["verdicts"])
        cases = ", ".join(reader["cases"])
        print(
            f"  {reader['reader']:<9} {reader['entries']:>2} entries "
            f"[{verdicts}] {cases}"
        )
        print(f"            entry point: {reader['entry_point']}")
        print(f"            stubs: {', '.join(reader['stubs'])}")

    rommap = plan["rommap"]
    print()
    print(
        f"rommap: segment {rommap['segment_index']} "
        f"({rommap['segment_base']}), {rommap['blocks']} blocks, "
        f"{rommap['loadable']} loadable, ram={'yes' if rommap['ram'] else 'no'}, "
        f"{rommap['skipped']} skipped"
    )
    print(
        f"processor: {rommap['processor']} "
        f"(verified={rommap['processor_verified']})"
    )
    print(
        f"stubs: {plan['stubs']['modeled']} modeled, "
        f"{plan['stubs']['planned']} planned"
    )

    print()
    print("trace targets:")
    for target in plan["trace_targets"]:
        anchor = target["anchor"] or "-"
        reader = target["reader"] or "(unassigned)"
        print(
            f"  [{target['status']:<20}] {target.get('role', 'reader'):<6} "
            f"{reader:<9} {anchor}"
        )
        print(f"                          {target['what']}")
        if target["note"]:
            print(f"                          {target['note']}")

    print()
    print("blockers:")
    for blocker in plan["blockers"]:
        print(f"  - {blocker}")

    print()
    print("first real run needs:")
    for item in plan["first_run_needs"]:
        print(f"  - {item}")


def cmd_plan(args) -> int:
    docs, problems = _load_inputs(args)
    if problems:
        for problem in problems:
            print(f"FAIL {problem}", file=sys.stderr)
        print(
            f"RESULT: FAIL ({len(problems)} problem(s)); fix the inputs first",
            file=sys.stderr,
        )
        return EXIT_INVALID

    plan = build_plan(docs["manifest"], docs["rommap"])
    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        _print_plan(plan)
    return EXIT_OK


def _emit_run(payload, as_json, lines) -> None:
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        for line in lines:
            print(line)


def cmd_run(args, env=None) -> int:
    docs, problems = _load_inputs(args)
    if problems:
        payload = {
            "command": "run",
            "status": "INVALID",
            "exit": EXIT_INVALID,
            "problems": problems,
        }
        _emit_run(
            payload,
            args.json,
            [f"FAIL {problem}" for problem in problems]
            + [f"RESULT: FAIL ({len(problems)} problem(s))"],
        )
        return EXIT_INVALID

    headless, searched = detect_ghidra(
        explicit=args.headless,
        env=env,
        extra_roots=args.search_root or None,
    )
    if not headless:
        payload = {
            "command": "run",
            "status": "MISSING_GHIDRA",
            "exit": EXIT_MISSING_GHIDRA,
            "searched": [{"source": source, "candidate": candidate} for source, candidate in searched],
        }
        _emit_run(
            payload,
            args.json,
            [_ghidra_instructions(args), "", "RESULT: MISSING_GHIDRA (exit 3)"],
        )
        return EXIT_MISSING_GHIDRA

    if not HARNESS_SCRIPT.is_file():
        payload = {
            "command": "run",
            "status": "BLOCKED",
            "exit": EXIT_BLOCKED,
            "reason": f"harness script missing: {HARNESS_SCRIPT}",
            "ghidra": headless,
        }
        _emit_run(
            payload,
            args.json,
            [
                f"BLOCKED: Ghidra found at {headless}",
                f"BLOCKED: harness script missing: {HARNESS_SCRIPT}",
                "The P-code harness and a located reader entry point are the",
                "next step; no result is produced and no pass is claimed.",
                "RESULT: BLOCKED (exit 4)",
            ],
        )
        return EXIT_BLOCKED

    image = args.image
    if not image or not Path(image).is_file():
        payload = {
            "command": "run",
            "status": "BLOCKED",
            "exit": EXIT_BLOCKED,
            "reason": "firmware image not provided or not readable",
            "ghidra": headless,
            "image": image,
        }
        _emit_run(
            payload,
            args.json,
            [
                f"BLOCKED: Ghidra found at {headless}",
                f"BLOCKED: firmware image missing: {image}",
                "Pass --image <the vendor image>; it is never committed.",
                "RESULT: BLOCKED (exit 4)",
            ],
        )
        return EXIT_BLOCKED

    blocks = [
        block
        for block in docs["rommap"].get("blocks", [])
        if block.get("loadable")
    ]
    if not blocks:
        payload = {
            "command": "run",
            "status": "BLOCKED",
            "exit": EXIT_BLOCKED,
            "reason": "memory map has no loadable blocks",
        }
        _emit_run(
            payload,
            args.json,
            ["BLOCKED: the memory map has no loadable blocks", "RESULT: BLOCKED (exit 4)"],
        )
        return EXIT_BLOCKED

    project_dir = args.project_dir
    result_path = Path(args.result or (Path(project_dir) / "l3-result.json"))
    command = [
        headless,
        project_dir,
        "l3",
        "-import",
        image,
        "-processor",
        docs["rommap"]["processor"]["id"],
        "-scriptPath",
        str(HARNESS_SCRIPT.parent),
        "-postScript",
        HARNESS_SCRIPT.name,
        str(args.rommap),
        str(args.manifest),
        str(result_path),
    ]

    if args.dry_run:
        payload = {
            "command": "run",
            "status": "DRY_RUN",
            "exit": EXIT_OK,
            "command": command,
            "note": "no Ghidra process was started and no verdict is claimed",
        }
        _emit_run(payload, args.json, [" ".join(command), "RESULT: DRY_RUN (exit 0)"])
        return EXIT_OK

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        payload = {
            "command": "run",
            "status": "BLOCKED",
            "exit": EXIT_BLOCKED,
            "reason": f"analyzeHeadless failed to run: {exc}",
            "command": command,
        }
        _emit_run(payload, args.json, [f"BLOCKED: {exc}", "RESULT: BLOCKED (exit 4)"])
        return EXIT_BLOCKED

    if completed.returncode != 0:
        payload = {
            "command": "run",
            "status": "BLOCKED",
            "exit": EXIT_BLOCKED,
            "reason": f"analyzeHeadless exit {completed.returncode}",
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "command": command,
        }
        _emit_run(
            payload,
            args.json,
            [
                f"BLOCKED: analyzeHeadless exit {completed.returncode}",
                completed.stderr[-2000:],
                "RESULT: BLOCKED (exit 4)",
            ],
        )
        return EXIT_BLOCKED

    if not result_path.is_file():
        payload = {
            "command": "run",
            "status": "BLOCKED",
            "exit": EXIT_BLOCKED,
            "reason": "analyzeHeadless finished but wrote no result JSON",
            "command": command,
        }
        _emit_run(
            payload,
            args.json,
            ["BLOCKED: no result JSON; a missing result is not a pass", "RESULT: BLOCKED (exit 4)"],
        )
        return EXIT_BLOCKED

    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        payload = {
            "command": "run",
            "status": "BLOCKED",
            "exit": EXIT_BLOCKED,
            "reason": f"unreadable result JSON: {exc}",
        }
        _emit_run(payload, args.json, [f"BLOCKED: {exc}", "RESULT: BLOCKED (exit 4)"])
        return EXIT_BLOCKED

    mismatches = _compare_result(docs["manifest"], result)
    payload = {
        "command": "run",
        "status": "PASS" if not mismatches else "MISMATCH",
        "exit": EXIT_OK if not mismatches else EXIT_MISMATCH,
        "mismatches": mismatches,
        "result": str(result_path),
    }
    _emit_run(
        payload,
        args.json,
        [f"MISMATCH {item}" for item in mismatches]
        + [
            "RESULT: PASS"
            if not mismatches
            else f"RESULT: MISMATCH ({len(mismatches)})",
        ],
    )
    return payload["exit"]


def _compare_result(manifest_doc, result: dict) -> list[str]:
    """Compare harness verdicts with the manifest expectations.

    Missing cases are mismatches: a harness that skips an entry has not
    passed it.
    """

    mismatches: list[str] = []
    observed = {}
    for case in result.get("cases", []) if isinstance(result, dict) else []:
        if isinstance(case, dict) and isinstance(case.get("id"), str):
            observed[case["id"]] = case.get("verdict")

    for entry in manifest_doc.get("corpus", []):
        entry_id = entry.get("id")
        expected = entry.get("expected")
        if entry_id not in observed:
            mismatches.append(f"{entry_id}: no verdict in the harness result")
        elif observed[entry_id] != expected:
            mismatches.append(
                f"{entry_id}: harness {observed[entry_id]!r}, "
                f"manifest {expected!r}"
            )
    return mismatches


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="L3 harness runner (design-only)")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_inputs(cmd):
        cmd.add_argument("--manifest", required=True, help="corpus manifest JSON")
        cmd.add_argument("--rommap", required=True, help="memory map JSON")
        cmd.add_argument(
            "--root",
            help="corpus root; enables size/SHA-256 checks",
        )
        cmd.add_argument("--json", action="store_true")

    check_cmd = sub.add_parser("check", help="validate manifest and memory map")
    add_inputs(check_cmd)

    plan_cmd = sub.add_parser("plan", help="print trace targets, stubs and blockers")
    add_inputs(plan_cmd)

    run_cmd = sub.add_parser("run", help="detect Ghidra and refuse to fake a pass")
    add_inputs(run_cmd)
    run_cmd.add_argument("--headless", help="path to analyzeHeadless")
    run_cmd.add_argument(
        "--search-root",
        action="append",
        default=[],
        help="extra directory to glob for ghidra* (repeatable)",
    )
    run_cmd.add_argument("--image", help="firmware image for -import")
    run_cmd.add_argument("--project-dir", default="/tmp/opencode/l3-ghidra")
    run_cmd.add_argument("--result", help="result JSON path")
    run_cmd.add_argument("--timeout", type=float, default=1800.0)
    run_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="print the analyzeHeadless command without running it",
    )

    sub.add_parser("selftest", help="run the package self-test")
    return parser


def main(argv=None, env=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--selftest"]:
        argv = ["selftest"]

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "selftest":
        from l3_harness import selftest

        return selftest.main([])
    if args.command == "check":
        return cmd_check(args)
    if args.command == "plan":
        return cmd_plan(args)
    if args.command == "run":
        return cmd_run(args, env=env)
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
