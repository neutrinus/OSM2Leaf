#!/usr/bin/env python3
"""One standing gate: run the four quality commands and apply one policy.

The TL/QA gate has been four commands with four exit semantics:

* ``selftest.py`` -- ``0`` green, ``1`` a suite failed, suites that need
  vendor data are ``SKIP`` inside its own report;
* ``claims_check.py [--strict]`` -- ``0`` clean, ``1`` a rule failed;
* ``todo_check.py [--strict]`` -- ``0`` no errors, ``1`` errors (warnings do
  not fail);
* ``fn_audit.py --corpus … --overlay …`` -- ``0`` clean, ``2`` the image is
  missing (a SKIP), ``1`` drift.

Agents re-made the "is exit 2 a failure?" judgement each cycle, and cycle 8
escaped through exactly that: a pair saw ``passed=89/90`` in a worktree where
``fn_audit_l3_image`` had ``skip_unless``-skipped on a missing
``archive/head256.img``.

This runner fixes one policy and prints it:

* **PASS** -- the gate ran and exited 0.
* **FAIL** -- the gate ran and exited non-zero for a reason other than a
  missing vendor input.
* **SKIP (reason)** -- the gate could not run because a vendor input is
  absent. A SKIP is never counted as a pass; the summary line prints both.

Exit code is ``1`` iff a runnable gate FAILed (and ``2`` only if the runner
itself is misused). A run where every vendor-dependent gate SKIPs but every
runnable gate PASSes exits ``0`` with a summary that says ``0 SKIP`` or names
the SKIPs -- the same contract ``realcheck.py``/``selftest.py`` use.

Usage::

    python3 tools/gate.py                 # human table, exit 1 on a FAIL
    python3 tools/gate.py --json          # same, machine-readable
    python3 tools/gate.py --no-count      # claims_check without --count-check
    python3 tools/gate.py --selftest      # prove PASS/FAIL/SKIP with stubs
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable

#: Missing-input markers a gate prints on stderr/stdout when it SKIPs instead
#: of failing. A gate's own exit code is not enough: ``fn_audit`` exits 2 for
#: a missing image but also 2 for a malformed snapshot, so the runner checks
#: the *message* and classifies exit 2 + one of these as SKIP, everything else
#: as FAIL. Keep this list narrow: a broad marker (e.g. "cannot verify") would
#: let a real "cannot verify the snapshot" error masquerade as a SKIP.
SKIP_MARKERS = (
    "no such file or directory: 'archive/",
    'no such file or directory: "archive/',
    "no image at ",
    "missing archive/",
)


class Gate:
    """One command in the standing gate."""

    __slots__ = ("name", "argv", "optional_input", "ok_exit")

    def __init__(self, name: str, argv: list[str], *, optional_input=None,
                 ok_exit=(0,)):
        self.name = name
        self.argv = argv
        #: A path whose absence means "this gate cannot run here" (a vendor
        #: input). When it is missing the gate is SKIP without being run.
        self.optional_input = optional_input
        #: Exit codes that mean PASS. Everything else is FAIL unless the
        #: output carries a SKIP marker.
        self.ok_exit = tuple(ok_exit)


def _run(gate: Gate, cwd: Path, timeout: float):
    """Run one gate; return a result dict with ``status``/``exit``/``output``."""
    started = time.time()
    if gate.optional_input is not None and not Path(gate.optional_input).exists():
        return {
            "gate": gate.name,
            "status": "SKIP",
            "reason": "missing %s" % _display(gate.optional_input),
            "exit": None,
            "seconds": 0.0,
            "output": "",
            "note": "",
        }
    try:
        proc = subprocess.run(
            gate.argv, cwd=str(cwd), capture_output=True, text=True,
            timeout=timeout)
    except FileNotFoundError as exc:
        return {
            "gate": gate.name, "status": "FAIL", "reason": "",
            "exit": None, "seconds": time.time() - started,
            "output": str(exc), "note": "command not found",
        }
    except subprocess.TimeoutExpired:
        return {
            "gate": gate.name, "status": "FAIL", "reason": "",
            "exit": None, "seconds": time.time() - started,
            "output": "", "note": "timeout after %gs" % timeout,
        }
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode in gate.ok_exit:
        status, reason = "PASS", ""
    else:
        low = out.lower()
        if proc.returncode == 2 and any(m in low for m in SKIP_MARKERS):
            status = "SKIP"
            reason = _first_marker_line(out)
        else:
            status, reason = "FAIL", ""
    return {
        "gate": gate.name,
        "status": status,
        "reason": reason,
        "exit": proc.returncode,
        "seconds": time.time() - started,
        "output": out,
        "note": "",
    }


def _display(path) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return str(p)


def _first_marker_line(out: str) -> str:
    for line in out.splitlines():
        low = line.lower()
        if any(m in low for m in SKIP_MARKERS):
            return line.strip()[:200]
    return "exit 2"


def standing_gate(*, count_check: bool = True, board_strict: bool = False,
                  corpus: str | None = None, overlay: str | None = None,
                  image: str | None = None) -> list[Gate]:
    """The four commands, in the fixed order the TL runs them."""
    claims = [PY, "tools/claims_check.py", "--strict"]
    if count_check:
        claims.append("--count-check")
    todo = [PY, "tools/todo_check.py"]
    if board_strict:
        todo.append("--strict")
    corpus = corpus or "docs/research/fn-audit-corpus-2026-11-16.json"
    overlay = overlay or "docs/research/fn-audit-l3-corpus-2026-11-20.json"
    image = image or "archive/head256.img"
    fn_audit = [PY, "tools/fn_audit.py", image, "--corpus", corpus,
                "--overlay", overlay, "--quiet"]
    return [
        Gate("selftest", [PY, "tools/selftest.py"]),
        Gate("claims_check", claims),
        Gate("todo_check", todo),
        Gate("fn_audit", fn_audit, optional_input=image),
    ]


def _print_table(results, stream=None) -> None:
    out = stream or sys.stdout
    width = max([len(r["gate"]) for r in results] + [10])
    print("%-*s  %-6s  %6s  %s" % (width, "GATE", "RESULT", "SECS", "NOTE"),
          file=out)
    print("%s  %s  %s  %s" % ("-" * width, "-" * 6, "-" * 6, "-" * 40),
          file=out)
    for r in results:
        note = r.get("reason") or r.get("note") or ""
        if r["status"] == "PASS" and not note:
            note = ""
        exited = "" if r["exit"] is None else "exit %s" % r["exit"]
        if exited and r["status"] != "PASS":
            note = ("%s; %s" % (exited, note)).strip("; ")
        print("%-*s  %-6s  %6.2f  %s" % (
            width, r["gate"], r["status"], r["seconds"], note), file=out)


def _summary(results) -> str:
    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    line = "gate: %d pass, %d fail, %d skip" % (
        counts["PASS"], counts["FAIL"], counts["SKIP"])
    skips = ["%s (%s)" % (r["gate"], r["reason"] or "skipped")
             for r in results if r["status"] == "SKIP"]
    if skips:
        line += " -- not covered: " + "; ".join(skips)
    return line


def run(*, cwd: Path = REPO, timeout: float = 900.0, json_out=None,
        **kwargs) -> int:
    gates = standing_gate(**kwargs)
    results = [_run(g, cwd, timeout) for g in gates]
    doc = {
        "ok": not any(r["status"] == "FAIL" for r in results),
        "counts": {
            "PASS": sum(1 for r in results if r["status"] == "PASS"),
            "FAIL": sum(1 for r in results if r["status"] == "FAIL"),
            "SKIP": sum(1 for r in results if r["status"] == "SKIP"),
        },
        "summary": _summary(results),
        "gates": [{k: v for k, v in r.items() if k != "output"}
                  for r in results],
    }
    to_stdout = json_out == "-"
    # When the JSON goes to stdout, the human table goes to stderr so the
    # stdout stream stays one parseable document.
    table_stream = sys.stderr if to_stdout else sys.stdout
    if json_out and not to_stdout:
        Path(json_out).write_text(json.dumps(doc, indent=2) + "\n",
                                  encoding="utf-8")
    _print_table(results, stream=table_stream)
    failed = [r for r in results if r["status"] == "FAIL"]
    for r in failed:
        print("\n--- %s output (tail) ---" % r["gate"], file=table_stream)
        print("\n".join((r["output"] or "").splitlines()[-40:]),
              file=table_stream)
    print(_summary(results), file=table_stream)
    if to_stdout:
        print(json.dumps(doc, indent=2))
    return 1 if failed else 0


# ------------------------------------------------------------------ selftest

#: Stub-gate programs the selftest writes. They prove the runner's own policy
#: (exit 0 is PASS, exit 1 is FAIL, exit 2 + a missing-input message is SKIP)
#: without any vendor data, exactly the H76 lesson applied to the aggregator.
_STUB_PASS = "import sys\nprint('stub ok')\nsys.exit(0)\n"
_STUB_FAIL = "import sys\nprint('boom: a rule failed')\nsys.exit(1)\n"
_STUB_SKIP = ("import sys\n"
              "print(\"error: [Errno 2] No such file or directory: "
              "'archive/head256.img'\", file=sys.stderr)\n"
              "sys.exit(2)\n")
_STUB_BAD2 = "import sys\nprint('error: snapshot image_sha256 does not match')\nsys.exit(2)\n"
#: A broad phrase the runner must NOT forgive: "cannot verify" is a real
#: failure message, not a missing-input SKIP (reviewer round 1).
_STUB_BROAD = ("import sys\n"
               "print('error: cannot verify the snapshot image')\n"
               "sys.exit(2)\n")


def selftest() -> int:
    ran: list[str] = []
    fails: list[str] = []

    def check(name, cond):
        ran.append(name)
        print("%s %s" % ("ok  " if cond else "FAIL", name))
        if not cond:
            fails.append(name)

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        stubs = {}
        for name, body in (("ok", _STUB_PASS), ("bad", _STUB_FAIL),
                           ("skip", _STUB_SKIP), ("bad2", _STUB_BAD2),
                           ("broad", _STUB_BROAD)):
            p = d / ("%s.py" % name)
            p.write_text(body)
            stubs[name] = [PY, str(p)]

        # A gate that exits 0 is PASS.
        r = _run(Gate("g", stubs["ok"]), d, 30)
        check("exit 0 -> PASS", r["status"] == "PASS" and r["exit"] == 0)

        # A gate that exits 1 is FAIL (and says so).
        r = _run(Gate("g", stubs["bad"]), d, 30)
        check("exit 1 -> FAIL", r["status"] == "FAIL" and r["exit"] == 1)

        # exit 2 + a missing-input message is SKIP, never PASS.
        r = _run(Gate("g", stubs["skip"]), d, 30)
        check("exit 2 + missing-input message -> SKIP (not PASS)",
              r["status"] == "SKIP" and "archive/head256.img" in r["reason"])

        # exit 2 *without* a missing-input marker is FAIL (a malformed input
        # is not a SKIP), so fn_audit's own exit 2 is not blanket-forgiven.
        r = _run(Gate("g", stubs["bad2"]), d, 30)
        check("exit 2 + no missing-input marker -> FAIL", r["status"] == "FAIL")

        # A broad phrase like "cannot verify" must not be forgiven either: a
        # real verification error is not a missing vendor input.
        r = _run(Gate("g", stubs["broad"]), d, 30)
        check("exit 2 + 'cannot verify' (not a missing-input marker) -> FAIL",
              r["status"] == "FAIL")

        # A declared optional input that is absent skips *before* running.
        r = _run(Gate("g", stubs["ok"], optional_input=d / "absent.img"), d, 30)
        check("declared-missing vendor input -> SKIP before running",
              r["status"] == "SKIP" and r["exit"] is None)

        # The aggregate exit code: one FAIL makes the run fail; a SKIP alone
        # does not.
        ok_and_skip = [_run(Gate("a", stubs["ok"]), d, 30),
                       _run(Gate("b", stubs["skip"]), d, 30)]
        check("PASS + SKIP counts as a pass (exit 0 policy)",
              not any(x["status"] == "FAIL" for x in ok_and_skip))
        one_fail = ok_and_skip + [_run(Gate("c", stubs["bad"]), d, 30)]
        check("any FAIL makes the run fail",
              any(x["status"] == "FAIL" for x in one_fail))

        # The summary line never hides the SKIP.
        line = _summary(ok_and_skip)
        check("summary names the SKIP and its reason",
              "0 fail" in line and "1 skip" in line
              and "b (error: [Errno 2]" in line)

        # JSON is the same data and a valid document.
        out = d / "gate.json"
        rc = _run_standing_stub(d, stubs, out)
        doc = json.loads(out.read_text()) if out.exists() else {}
        check("--json writes the same counts and is valid JSON",
              bool(doc) and doc.get("counts", {}).get("PASS", 0) >= 1
              and rc == 1)
        check("--json never records a SKIP as PASS",
              doc.get("counts", {}).get("SKIP", 0) >= 1)

    print("gate selftest: %s (%d checks, %d failed)"
          % ("OK" if not fails else "FAIL", len(ran), len(fails)))
    return 1 if fails else 0


def _run_standing_stub(d: Path, stubs, out: Path) -> int:
    """Run a stub version of the standing gate through ``run()``.

    This exercises the same code path CI uses (``run``/``_print_table``/
    ``--json``) with stub gates, so the JSON shape and the exit policy are
    tested end to end without a 48 s selftest or a vendor image.
    """
    global standing_gate
    original = standing_gate

    def stubbed(**kwargs):
        return [Gate("stub_pass", stubs["ok"]),
                Gate("stub_skip", stubs["skip"]),
                Gate("stub_fail", stubs["bad"])]

    standing_gate = stubbed
    try:
        return run(cwd=d, timeout=30, json_out=out)
    finally:
        standing_gate = original


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="One standing gate: selftest, claims_check, todo_check, "
                    "fn_audit with one PASS/FAIL/SKIP policy.")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", metavar="PATH", nargs="?", const="-",
                    help="write the machine-readable report (default stdout)")
    ap.add_argument("--no-count", action="store_true",
                    help="run claims_check --strict without --count-check")
    ap.add_argument("--board-clean", action="store_true",
                    help="run todo_check --strict (red until H53) instead of "
                         "the default gate")
    ap.add_argument("--corpus", help="fn_audit base snapshot")
    ap.add_argument("--overlay", help="fn_audit l3 overlay snapshot")
    ap.add_argument("--image", help="firmware head fn_audit classifies against")
    ap.add_argument("--cwd", help="run the gates in this directory (default "
                                  "the repo root)")
    ap.add_argument("--timeout", type=float, default=900.0)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    kwargs = {
        "count_check": not args.no_count,
        "board_strict": args.board_clean,
        "corpus": args.corpus,
        "overlay": args.overlay,
        "image": args.image,
    }
    cwd = Path(args.cwd).resolve() if args.cwd else REPO
    if not (cwd / "tools" / "gate.py").exists() and not (cwd / "TODO.md").exists():
        print("error: %s does not look like the repo root" % cwd,
              file=sys.stderr)
        return 2
    return run(cwd=cwd, timeout=args.timeout, json_out=args.json, **kwargs)


if __name__ == "__main__":
    raise SystemExit(main())
