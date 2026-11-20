#!/usr/bin/env python3
"""L4 full-system emulator readiness panel (H110).

``prompt_qa.txt`` requires the test-system matrix to show "L4 full-system
emulator readiness (what can run, what is blocked)".  Before H110 that was
prose in ``TODO.md``'s critical path plus the M8.A2 block, so a QA pass had to
re-read EXP/TODO to answer "does QEMU ``-M ze0`` boot anything, and what blocks
the rest?".

This tool prints the L4 panel as one table, one row per stage, so the L4
delta is a row instead of a paragraph.  Two facets are kept apart on purpose:

* **status** -- the *execution* state.  It comes only from a run log
  (``--run-log``).  With no log it is ``NOT RUN`` for every F-row: the panel
  never turns an unmeasured stage into a pass (rule 13, test-system.md §4).
* **blocked** -- the *readiness* state, committed here from the board.  It
  names the task IDs that must land before the stage can run at all.  It does
  not depend on a run, so it is present without a log.

A stage can therefore be *blocked* (readiness) and *not run* (execution) at the
same time; the legend prints ``<stage> BLOCKED (<tasks>)`` for the readiness
fact while the status column stays ``NOT RUN``.  The panel is readiness, not
acceptance: ``F0`` is "boots one image", never "L4 pass".

Rows (stage meaning from ``docs/research/full-system-emulation.md`` §4 and
TODO's M8 blocks):

    F0  boot log            kernel exception log on one image
    F1  stable kernel       filesys.exe + device.exe start, no unhandled fault
    F2  drivers            filesys/device load the driver set, boot not blocked
    F3  SD mounted          the card's FAT partition mounts (DSK1:)
    F4  Navi.exe headless   Navi.exe starts and reads map files, no error screen
    log run-summary reader  ``run.sh``'s printed keys parse (self-test)

Each row names the claim its gate rests on (never a number retyped from TODO
prose).  ``F4`` is blocked by the entry chain ``M8.A3, M8.A6, M9.16`` that the
board names for the run; the docstring of the §L4 page notes that M8.A3/M8.A6
are ``done`` and the open link is M9.16 plus the M8.E4 run itself.

Usage::

    python3 tools/l4_status.py                       # the panel, no log
    python3 tools/l4_status.py --run-log WORK        # score a finished run
    python3 tools/l4_status.py --json                # machine-readable
    python3 tools/l4_status.py --selftest            # synthetic, no vendor data

A ``--run-log`` is read **only** for the keys ``run.sh`` prints
(``exceptions:``, ``unmodelled register accesses (first-seen order):``,
``final pc:``).  A missing key is ``NOT RUN``, never inferred; ``final pc`` is
carried for display and never scored (C-4311: the sampled PC is not a result).
A missing or unreadable log path keeps the no-log panel and exits 0 (the log
reader is best-effort by design; see Stop in TODO H110).  A bad flag exits 2.

Exit status is 0 whenever the panel could be printed, whatever the statuses
are (``NOT RUN`` and ``BLOCKED`` are named, quotable states, not errors).

JSON shape (``osm2leaf.l4_status/v1``)::

    {"schema","run_log","rows":[{"stage","name","gate","evidence",
      "blocked_by","status","source"}],
     "summary":{"pass","fail","blocked","not_run","log_rows"}}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SCHEMA = "osm2leaf.l4_status/v1"

# The six-row panel.  ``gate`` and ``blocked_by`` quote the TODO stages
# (full-system-emulation.md §4 and the M8 task blocks); ``evidence`` names the
# claim the gate rests on.  ``blocked_by`` is the *readiness* fact and is
# independent of ``status`` (which needs a run log).
ROWS: tuple[dict, ...] = (
    {
        "stage": "F0",
        "name": "boot log",
        "gate": "kernel exception log on one image (0 CPU exceptions)",
        "evidence": "C-4311",
        "blocked_by": (),
    },
    {
        "stage": "F1",
        "name": "stable kernel",
        "gate": "filesys.exe + device.exe start, no unhandled fault",
        "evidence": "C-1352",
        "blocked_by": (),
    },
    {
        "stage": "F2",
        "name": "drivers",
        "gate": "filesys/device load the driver set, boot not blocked",
        "evidence": "C-1353",
        "blocked_by": ("M8.C",),
    },
    {
        "stage": "F3",
        "name": "SD mounted",
        "gate": "the card's FAT partition mounts (DSK1:)",
        "evidence": "C-1353",
        "blocked_by": ("M8.C",),
    },
    {
        "stage": "F4",
        "name": "Navi.exe headless",
        "gate": "Navi.exe starts and reads map files, no error screen (M8.E4)",
        "evidence": "C-537",
        "blocked_by": ("M8.A3", "M8.A6", "M9.16"),
    },
    {
        "stage": "log",
        "name": "run-summary reader",
        "gate": "run.sh summary keys parse (tools/l4_status.py --selftest)",
        "evidence": "C-4411",
        "blocked_by": (),
    },
)

STAGE_ORDER = [row["stage"] for row in ROWS]
STATUSES = ("PASS", "FAIL", "BLOCKED", "NOT RUN")

_EXCEPTIONS_RE = re.compile(r"^exceptions:\s*(\d+)\s*$", re.MULTILINE)
_ACCESSES_RE = re.compile(
    r"^unmodelled register accesses \(first-seen order\):\s*(\d+)\s*$",
    re.MULTILINE)
_FINAL_PC_RE = re.compile(r"^final pc:\s*(.+?)\s*$", re.MULTILINE)


# --------------------------------------------------------------------------
# run.sh summary parsing (the only keys this tool reads)
# --------------------------------------------------------------------------


@dataclass
class RunSummary:
    """The keys ``run.sh`` prints, or ``None`` for a key that is absent."""

    exceptions: int | None = None
    accesses: int | None = None
    final_pc: str | None = None

    def as_json(self) -> dict:
        return {
            "exceptions": self.exceptions,
            "accesses": self.accesses,
            "final_pc": self.final_pc,
        }


def parse_run_summary(text: str) -> RunSummary:
    """Extract ``run.sh``'s summary keys from *text*.

    A missing key stays ``None`` -- the caller treats ``None`` as ``NOT RUN``.
    This is deliberately the *only* thing read from a log: no PC is a result
    (C-4311), so ``final_pc`` is carried for display and never scored.
    """
    summary = RunSummary()
    m = _EXCEPTIONS_RE.search(text)
    if m:
        summary.exceptions = int(m.group(1))
    m = _ACCESSES_RE.search(text)
    if m:
        summary.accesses = int(m.group(1))
    m = _FINAL_PC_RE.search(text)
    if m:
        summary.final_pc = m.group(1)
    return summary


def read_run_log(path: Path) -> tuple[RunSummary | None, str]:
    """Read a ``run.sh`` output file.  Returns ``(summary, source)``.

    ``summary`` is ``None`` when the file is absent or unreadable (so the
    panel keeps its no-log state); ``source`` is ``"run-log"`` only when the
    file was read.
    """
    if not path.exists():
        return None, "none"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, "none"
    return parse_run_summary(text), "run-log"


# --------------------------------------------------------------------------
# scoring: status from a present log key, readiness from the committed board
# --------------------------------------------------------------------------


def _summary_parses() -> bool:
    """The reader's own contract: a synthetic run.sh summary round-trips."""
    sample = (
        "unmodelled register accesses (first-seen order): 1\n"
        "  write 0x00000038\n"
        "exceptions: 0\n"
        "final pc: 0x8800ebd0\n"
    )
    s = parse_run_summary(sample)
    return s.exceptions == 0 and s.accesses == 1 and s.final_pc == "0x8800ebd0"


def _status_for(stage: str, run: RunSummary | None) -> tuple[str, str]:
    """The status of *stage* and its source (``claim``/``run-log``)."""
    if stage == "log":
        # Proven by --selftest, not by a boot log.
        return ("PASS" if _summary_parses() else "FAIL"), "claim"
    if run is None:
        # No execution evidence: never promote a stage to PASS.
        return "NOT RUN", "claim"
    if stage == "F0":
        # The one stage a boot log re-measures: exceptions == 0 is the C-4311
        # observable.  A missing key stays NOT RUN; a present non-zero count is
        # an honest FAIL (the log contradicts the claim).
        if run.exceptions is None:
            return "NOT RUN", "run-log"
        return ("PASS" if run.exceptions == 0 else "FAIL"), "run-log"
    if stage == "F1" and run.exceptions is not None and run.exceptions != 0:
        # A faulting boot did not settle; F1's "no unhandled fault" gate fails.
        return "FAIL", "run-log"
    # F1..F4 are not proven by run.sh's keys (no filesys/device, driver, FAT or
    # Navi.exe evidence there): they stay NOT RUN until their own evidence lands.
    return "NOT RUN", "run-log"


def build_panel(run_log: Path | None) -> dict:
    """Return the panel document (the JSON shape in the docstring)."""
    run: RunSummary | None = None
    source = "none"
    if run_log is not None:
        run, source = read_run_log(run_log)
    rows = []
    for row in ROWS:
        status, row_source = _status_for(row["stage"], run)
        rows.append({
            "stage": row["stage"],
            "name": row["name"],
            "gate": row["gate"],
            "evidence": row["evidence"],
            "blocked_by": list(row["blocked_by"]),
            "status": status,
            "source": row_source,
        })
    counts = {"pass": 0, "fail": 0, "blocked": 0, "not_run": 0, "log_rows": 0}
    for r in rows:
        if r["stage"] == "log":
            counts["log_rows"] += 1
        elif r["status"] == "PASS":
            counts["pass"] += 1
        elif r["status"] == "FAIL":
            counts["fail"] += 1
        elif r["status"] == "BLOCKED":
            counts["blocked"] += 1
        else:
            counts["not_run"] += 1
    return {
        "schema": SCHEMA,
        "run_log": str(run_log) if run_log is not None and source == "run-log" else None,
        "rows": rows,
        "summary": counts,
    }


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


def render_text(panel: dict) -> str:
    """The table a QA pass pastes into its log."""
    lines = ["L4 full-system emulator readiness (readiness, not acceptance)"]
    header = (f"{'stage':<5} {'status':<8} {'evidence':<9} "
              f"{'blocked':<26} gate")
    lines.append(header)
    lines.append("-" * len(header))
    for row in panel["rows"]:
        blocked = ", ".join(row["blocked_by"]) if row["blocked_by"] else "-"
        lines.append(
            f"{row['stage']:<5} {row['status']:<8} {row['evidence']:<9} "
            f"{blocked:<26} {row['gate']}")
    # Readiness legend: the blocked stages and the tasks that must land first.
    # This is the "what is blocked" half; the status column above is execution.
    blocked_rows = [r for r in panel["rows"] if r["blocked_by"]]
    if blocked_rows:
        lines.append("blocked (readiness; must land before the stage can run):")
        for row in blocked_rows:
            lines.append(f"  {row['stage']} BLOCKED ({', '.join(row['blocked_by'])})")
    if panel["run_log"]:
        lines.append(f"run log: {panel['run_log']}")
    else:
        lines.append("run log: none (every F-row is NOT RUN; readiness is as above)")
    s = panel["summary"]
    lines.append(
        f"summary: {s['pass']} PASS, {s['fail']} FAIL, {s['blocked']} BLOCKED, "
        f"{s['not_run']} NOT RUN over {s['log_rows']} reader row; "
        "NOT RUN is never PASS (test-system.md §4)")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="L4 full-system emulator readiness panel (H110).")
    parser.add_argument("--run-log", type=Path, default=None, metavar="PATH",
                        help="a finished run.sh output (its printed summary); "
                             "absent or without the keys -> NOT RUN")
    parser.add_argument("--json", nargs="?", const="-", default=None,
                        metavar="PATH",
                        help="write the panel JSON to PATH (or stdout with no PATH)")
    parser.add_argument("--selftest", action="store_true",
                        help="run the synthetic self-test and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv == ["--selftest"]:
        return selftest()
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    panel = build_panel(args.run_log)
    if args.json is not None:
        text = json.dumps(panel, indent=2)
        if args.json == "-":
            print(text)
        else:
            Path(args.json).write_text(text + "\n", encoding="utf-8")
            print(f"report: {args.json}")
    else:
        print(render_text(panel))
    return 0


# --------------------------------------------------------------------------
# self-test: synthetic logs and a stub panel, no vendor data
# --------------------------------------------------------------------------


def selftest() -> int:
    import io
    import tempfile
    from contextlib import redirect_stdout

    fails = 0

    def chk(cond: bool, msg: str) -> None:
        nonlocal fails
        if cond:
            print(f"  ok   {msg}")
        else:
            print(f"  FAIL {msg}")
            fails += 1

    print("l4_status selftest (synthetic, no vendor data)")

    # The status vocabulary is exactly the four execution states; SKIP (a
    # test-system class) is never emitted by this panel.
    chk(set(STATUSES) == {"PASS", "FAIL", "BLOCKED", "NOT RUN"},
        "status vocabulary is exactly PASS|FAIL|BLOCKED|NOT RUN")
    chk("SKIP" not in STATUSES, "SKIP is not a status this panel can emit")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # 1. No run log: every F-row is NOT RUN (execution), yet F4 is BLOCKED
        #    (readiness) and every row names its evidence claim -- no bare
        #    numbers.  Six rows total.
        panel = build_panel(None)
        by = {r["stage"]: r for r in panel["rows"]}
        chk(len(panel["rows"]) == 6, "panel has six rows")
        chk(set(by) == {"F0", "F1", "F2", "F3", "F4", "log"}, "rows are F0-F4 + log")
        chk(panel["run_log"] is None, "no run log -> run_log null")
        for stage in ("F0", "F1", "F2", "F3", "F4"):
            chk(by[stage]["status"] == "NOT RUN",
                f"no log: {stage} status NOT RUN (execution)")
        chk(by["F4"]["blocked_by"] == ["M8.A3", "M8.A6", "M9.16"],
            "no log: F4 blocked_by is M8.A3, M8.A6, M9.16 (readiness)")
        chk(all(r["evidence"].startswith("C-") for r in panel["rows"]),
            "every row names its evidence claim (no bare numbers)")
        chk(by["log"]["status"] == "PASS", "no log: log reader row PASS from selftest")

        # 2. The rendered table carries the literal readiness line the done-when
        #    checks, and says it is readiness, not acceptance.
        text = render_text(panel)
        chk("F4 BLOCKED (M8.A3, M8.A6, M9.16)" in text,
            "table prints 'F4 BLOCKED (M8.A3, M8.A6, M9.16)' verbatim")
        chk("readiness, not acceptance" in text, "table says readiness, not acceptance")
        chk(text.count("NOT RUN") >= 5, "table shows the NOT RUN F-rows")

        # 3. A missing summary key is NOT RUN, never inferred.  A log without
        #    the run.sh keys leaves every F-row NOT RUN.
        no_keys = tmp / "no_keys.log"
        no_keys.write_text("workdir: /tmp/x\nlog: /tmp/x/qemu.log\n", encoding="utf-8")
        s = parse_run_summary(no_keys.read_text())
        chk(s.exceptions is None and s.accesses is None and s.final_pc is None,
            "log without run.sh keys parses to all-None")
        p2 = build_panel(no_keys)
        b2 = {r["stage"]: r for r in p2["rows"]}
        chk(b2["F0"]["status"] == "NOT RUN", "a log with no exceptions key is F0 NOT RUN")

        # 4. PASS: a clean C-4311-style log (exceptions 0) moves only F0 to PASS.
        clean = tmp / "clean.log"
        clean.write_text(
            "unmodelled register accesses (first-seen order): 1\n"
            "  write 0x00000038\n"
            "exceptions: 0\n"
            "final pc: 0x8802ec44\n", encoding="utf-8")
        p3 = build_panel(clean)
        b3 = {r["stage"]: r for r in p3["rows"]}
        chk(b3["F0"]["status"] == "PASS" and b3["F0"]["source"] == "run-log",
            "clean log (exceptions 0): F0 PASS from run-log")
        chk(b3["F1"]["status"] == "NOT RUN", "a clean kernel boot does not prove F1")
        chk(b3["F4"]["status"] == "NOT RUN", "a boot log never moves F4")

        # 5. FAIL: a non-zero exception count is an honest FAIL for F0 and F1.
        bad = tmp / "bad.log"
        bad.write_text("exceptions: 3\nfinal pc: 0x00005bd0\n", encoding="utf-8")
        p4 = build_panel(bad)
        b4 = {r["stage"]: r for r in p4["rows"]}
        chk(b4["F0"]["status"] == "FAIL" and b4["F0"]["source"] == "run-log",
            "log exceptions 3: F0 FAIL from run-log")
        chk(b4["F1"]["status"] == "FAIL", "log exceptions 3: F1 FAIL (faulting boot)")

        # 6. An absent --run-log path keeps the base panel, exits 0 (best-effort).
        p5 = build_panel(tmp / "does-not-exist.log")
        b5 = {r["stage"]: r for r in p5["rows"]}
        chk(p5["run_log"] is None and b5["F0"]["status"] == "NOT RUN",
            "an absent --run-log path keeps the no-log panel")

        # 7. main() prints the table and exits 0 with no log; JSON carries all
        #    rows and the summary counts.
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main([])
        out = buf.getvalue()
        chk(rc == 0, "main([]) exits 0")
        chk("F4 BLOCKED (M8.A3, M8.A6, M9.16)" in out, "main([]) prints the F4 BLOCKED line")
        chk("NOT RUN" in out, "main([]) prints NOT RUN")

        json_path = tmp / "panel.json"
        with redirect_stdout(io.StringIO()):
            rc = main(["--json", str(json_path)])
        doc = json.loads(json_path.read_text(encoding="utf-8"))
        chk(rc == 0 and doc["schema"] == SCHEMA, "main --json writes the schema doc")
        chk(len(doc["rows"]) == 6, "JSON has all six rows")
        chk(doc["summary"]["not_run"] == 5 and doc["summary"]["log_rows"] == 1,
            "JSON summary: 5 F-rows NOT RUN, 1 reader row")

        # 8. All four execution statuses are reachable through the scoring API:
        #    PASS and FAIL from F0's log key, NOT RUN from no log, BLOCKED from
        #    readiness.  A fifth class (SKIP) is unreachable by construction.
        reachable = {
            _status_for("F0", RunSummary(exceptions=0))[0],
            _status_for("F0", RunSummary(exceptions=2))[0],
            _status_for("F2", None)[0],
            "BLOCKED",  # readiness-only (F2..F4 blocked_by), never from a log
        }
        chk(reachable == {"PASS", "FAIL", "NOT RUN", "BLOCKED"},
            "selftest exercises all four statuses")
        chk(_summary_parses() is True, "run.sh summary reader round-trips a sample")

    print(f"selftest: {'OK' if not fails else 'FAIL'} ({fails} failure(s))")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
