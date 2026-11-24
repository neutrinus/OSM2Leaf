#!/usr/bin/env python3
"""Run a routing scenario on a live ``-M ze0`` guest with an SD-read trace (M8.H41).

A scenario is a ``tools/ze0_ui.py`` step file.  This wrapper adds the two things
the step grammar does not have:

* a QEMU ``-trace enable=sdcard_read_block`` log, so every guest SD block read
  is attributable to a card file/byte range by ``tools/ze0_sdtrace.py``;
* ``# PHASE name`` markers on scenario lines.  After each marked step the
  wrapper counts the ``sdcard_read_block`` lines in the trace and records the
  count, so a phase window is an event ordinal slice ``[count_a:count_b]``
  (no dependency on host-clock trace timestamps).  A sample trace line is
  printed so the grammar can be checked before relying on the count.

The wrapper starts QEMU (using ``tools/ze0_launch.py``'s own argv builder, plus
``-qmp``, ``-trace`` and the ``panel``/``gps`` peers), waits for the peer control
sockets, then drives the scenario through ``ze0_ui.Runner``.  It prints every
step result, the final plane-1 PNG SHA-256, the per-phase trace counts, and a
JSON report.  Exit codes mirror ``ze0_ui.py``: 0 pass, 1 expectation failed,
2 usage error, 3 nothing runnable.  A stop screen is reported with its serial
log tail rather than hidden.

Usage:
  ze0_route_scenario.py run SCENARIO --card CARD --workdir DIR --gdb PORT
      [--qemu PATH] [--flash PATH] [--nk PATH] [--ui-start] [--timeout S]
      [--wait-timeout S] [--json FILE]
  ze0_route_scenario.py --selftest

Stdlib only.  Method and results: docs/experiments/EXP-2026-11-24-M8.H41-route-scenario.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ze0_launch  # noqa: E402
import ze0_ui  # noqa: E402

TRACE_EVENT = "sdcard_read_block"
TRACE_NEEDLE = TRACE_EVENT          # unanchored: QEMU may prefix trace lines
PHASE_RE = re.compile(r"PHASE\s+([A-Za-z0-9_]+)")


# ---------------------------------------------------------------------------
# Pure helpers (selftested)
# ---------------------------------------------------------------------------

def parse_phases(text):
    """Map scenario step ordinal (1-based) -> phase name.

    ``ze0_ui.parse_scenario`` drops blank/comment-only lines, so a ``PHASE``
    tail on a step maps to its step ordinal in ``steps``, not its physical line.
    A comment-only line with a PHASE tail produces no step and is ignored.
    """
    phases = {}
    steps = ze0_ui.parse_scenario(text)
    step_no = 0
    for raw in text.splitlines():
        code, sep, comment = raw.partition("#")
        if not code.strip():
            continue
        step_no += 1
        if sep:
            m = PHASE_RE.search(comment)
            if m:
                phases[step_no] = m.group(1)
    return phases


def trace_count(path):
    """Number of trace lines containing the event needle (unanchored)."""
    n = 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if TRACE_NEEDLE in line:
                n += 1
    return n


def trace_slice(path, start, end):
    """Return the trace lines in ordinal window ``[start:end]``."""
    out = []
    idx = 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if TRACE_NEEDLE not in line:
                continue
            if start <= idx < end:
                out.append(line.rstrip("\n"))
            idx += 1
    return out


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wait_for_socket(path, timeout=30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if os.path.exists(path):
            return True
        time.sleep(0.1)
    return False


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

def build_argv(args, work, trace_path, qmp_path):
    """QEMU argv from ze0_launch plus -qmp and -trace (derived, not guessed)."""
    lines = ["sci3", "sci7"]
    argv = ze0_launch.qemu_argv(
        args.qemu, args.card, args.nk, args.flash,
        os.path.join(work, "ipl.txt"), work, lines, args.gdb)
    argv += ["-qmp", "unix:%s,server,nowait" % qmp_path]
    argv += ["-trace", "enable=%s,file=%s" % (TRACE_EVENT, trace_path)]
    return argv


def run(args):
    scenario = os.path.abspath(args.scenario)
    if not os.path.exists(scenario):
        raise SystemExit("ze0_route_scenario: no scenario %s" % scenario)
    work = os.path.abspath(args.workdir)
    os.makedirs(work, exist_ok=True)
    trace_path = os.path.join(work, "sd-trace.log")
    qmp_path = os.path.join(work, "qmp.sock")
    shot_dir = os.path.join(work, "shots")
    os.makedirs(shot_dir, exist_ok=True)

    text = open(scenario, "r", encoding="utf-8").read()
    steps = ze0_ui.parse_scenario(text)
    phases = parse_phases(text)

    args.flash = ze0_launch.resolve_flash(args.flash, work, args.nk)
    ipl_cmd = [sys.executable, os.path.join(HERE, "ze0_ipl.py"), "patch",
               args.card, "-o", os.path.join(work, "ipl.txt"), "--nk", args.nk]
    subprocess.run(ipl_cmd, check=True, stdout=subprocess.DEVNULL)

    qemu_argv = build_argv(args, work, trace_path, qmp_path)
    print("qemu: %s" % " ".join(map(shlex.quote, qemu_argv)))

    panel = [sys.executable, os.path.join(HERE, "ze0_peers", "panel.py"),
             "--sci3", os.path.join(work, "sci3.sock"),
             "--control", os.path.join(work, "panel.ctl"), "--forever",
             "--out", os.path.join(work, "panel.events")]
    gps = [sys.executable, os.path.join(HERE, "ze0_peers", "gps.py"),
           "--socket", os.path.join(work, "sci7.sock"), "--no-fix",
           "--control", os.path.join(work, "gps.ctl")]
    uistart = [sys.executable, os.path.join(HERE, "ze0_uistart.py"), "run",
               args.card, "--port", str(args.gdb), "--touch-unlock",
               "--nk", args.nk] if args.ui_start else None

    procs = []
    code = 0
    results = []
    phase_counts = {}
    sample_trace = None
    try:
        q = subprocess.Popen(qemu_argv,
                             stdout=open(os.path.join(work, "qemu.out"), "w"),
                             stderr=subprocess.STDOUT)
        procs.append(q)
        for ln in ("sci3", "sci7"):
            wait_for_socket(os.path.join(work, ln + ".sock"))
        peer_spec = [("panel", panel), ("gps", gps)]
        if uistart:
            peer_spec.append(("uistart", uistart))
        for name, pargv in peer_spec:
            procs.append(subprocess.Popen(
                pargv, stdout=open(os.path.join(work, name + ".log"), "w"),
                stderr=subprocess.STDOUT))
        for ctl in ("panel.ctl", "gps.ctl"):
            if not wait_for_socket(os.path.join(work, ctl)):
                print("WARN control socket %s missing" % ctl)

        runner_args = argparse.Namespace(
            qmp=qmp_path, hmp=os.path.join(work, "mon.sock"),
            log=os.path.join(work, "serial.log"),
            panel_sock=os.path.join(work, "panel.ctl"),
            gps_sock=os.path.join(work, "gps.ctl"),
            shot_dir=shot_dir, shot_cmd=None, guest_clock=None,
            wait_timeout=args.wait_timeout, poll=0.5, quiet=False)
        runner = ze0_ui.Runner(runner_args)

        t0 = time.monotonic()
        for idx, step in enumerate(steps, 1):
            if args.timeout and time.monotonic() - t0 > args.timeout:
                print("harness timeout after %.0fs" % args.timeout)
                code = 1
                break
            try:
                detail = runner.run_step(step)
            except ze0_ui.NotRunnable as exc:
                print("SKIP step %d %-11s %s" % (idx, step.kind, exc))
                code = 3
                break
            except ze0_ui.StepError as exc:
                print("FAIL step %d %-11s %s" % (idx, step.kind, exc))
                code = 1
                break
            print("ok   step %d %-11s %s" % (idx, step.kind, detail))
            results.append({"step": idx, "kind": step.kind,
                            "raw": step.raw, "detail": detail})
            if idx in phases:
                name = phases[idx]
                cnt = trace_count(trace_path) if os.path.exists(trace_path) else 0
                phase_counts[name] = cnt
                print("phase %-20s trace_lines=%d" % (name, cnt))

        # A sample trace line, quoted so the grammar can be verified.
        if os.path.exists(trace_path):
            with open(trace_path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if TRACE_NEEDLE in line:
                        sample_trace = line.rstrip("\n")
                        break
        print("trace sample: %s" % (sample_trace or "(none)"))
    finally:
        for p in reversed(procs):
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
        for p in procs:
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()

    # final hashes of every shot, printed by sha256sum-equivalent
    hashes = {}
    for name in sorted(os.listdir(shot_dir)):
        path = os.path.join(shot_dir, name)
        if os.path.isfile(path):
            hashes[name] = sha256_file(path)
            print("sha256 %-24s %s" % (name, hashes[name]))

    windows = {}
    names = list(phase_counts)
    for a, b in zip(names, names[1:]):
        windows["%s->%s" % (a, b)] = {
            "start": phase_counts[a], "end": phase_counts[b],
            "lines": trace_slice(trace_path, phase_counts[a], phase_counts[b])
            if os.path.exists(trace_path) else []}

    serial = os.path.join(work, "serial.log")
    tail = []
    if os.path.exists(serial):
        with open(serial, "r", encoding="utf-8", errors="replace") as fh:
            tail = fh.read().splitlines()[-20:]
        print("serial tail:")
        for line in tail:
            print("  %s" % line)

    report = {
        "scenario": scenario, "exit": code, "steps": results,
        "phases": phase_counts, "windows": windows,
        "trace_sample": sample_trace, "shot_hashes": hashes,
        "serial_tail": tail,
    }
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print("json: %s" % args.json)
    return code


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------

def selftest():
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL",
                                        label, got, want))

    text = "\n".join([
        "wait-log READY",
        "shot before-calc  # PHASE before_calculate",
        "tap 100 200  # PHASE calculate",
        "shot after-calc  # PHASE route_shown",
        "# a comment-only PHASE ignored  # PHASE ignored",
        "expect-hash after-calc 0000",
    ])
    check("phase map", parse_phases(text),
          {2: "before_calculate", 3: "calculate", 4: "route_shown"})
    check("phase count", len(parse_phases(text)), 3)

    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "trace.log")
        # A prefixed line (backend tag) plus plain lines: unanchored count.
        open(p, "w").write(
            "1234.5 sdcard_read_block addr 0x100 size 0x200\n"
            "noise line\n"
            "sdcard_read_block addr 0x200 size 0x200\n"
            "sdcard_read_block addr 0x300 size 0x200\n")
        check("trace count", trace_count(p), 3)
        check("trace slice", trace_slice(p, 1, 3), [
            "sdcard_read_block addr 0x200 size 0x200",
            "sdcard_read_block addr 0x300 size 0x200"])
        check("sample line", open(p).readline().strip(),
              "1234.5 sdcard_read_block addr 0x100 size 0x200")
    # negative: no event in an empty trace -> 0, not an exception
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "trace.log")
        open(p, "w").write("nothing here\n")
        check("empty trace count", trace_count(p), 0)
    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL",
                                           fails))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    runp = sub.add_parser("run", help="run a scenario on a live guest")
    runp.add_argument("scenario")
    runp.add_argument("--card", required=True)
    runp.add_argument("--workdir", required=True)
    runp.add_argument("--gdb", type=int, required=True)
    runp.add_argument("--qemu", default=os.environ.get(
        "QEMU", "~/.cache/qemu-ze0/build/qemu-system-sh4"))
    runp.add_argument("--flash", default="anon")
    runp.add_argument("--nk", default=ze0_launch.DEFAULT_NK)
    runp.add_argument("--ui-start", action="store_true")
    runp.add_argument("--timeout", type=float, default=0)
    runp.add_argument("--wait-timeout", type=float, default=60)
    runp.add_argument("--json")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd != "run":
        ap.error("run SCENARIO ... or --selftest")
    args.qemu = os.path.expanduser(args.qemu)
    if not args.card or not args.workdir:
        ap.error("--card and --workdir required")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
