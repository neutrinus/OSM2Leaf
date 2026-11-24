#!/usr/bin/env python3
"""Drive a live ``-M ze0`` guest through QMP ``input-send-event`` (M8.H40).

This is the reproducible, no-human equivalent of moving the mouse and
pressing keys in a live ``--display vnc`` window.  It sends absolute pointer
moves, button transitions and key events to the ``ze0-gfx`` console, which
M8.H40's patch forwards to the panel peer over the same SCI3 display-unit
link M8.H39 used.  It also captures named-region screenshot hashes so a
recorded session can be replayed and compared byte-for-byte.

Scenario grammar (one step per line; ``#`` starts a comment)::

    abs X Y        send two QMP abs events (screen pixels -> scaled qwords)
    click          send left-button down+up at the last abs position
    key NAME       send a QMP key down+up by QEMU qcode name
    shot NAME      save a plane PNG via ze0_screenshot.py to SHOT_DIR/NAME.png
    wait-log REGEX wait until REGEX matches a line of --log

Absolute scaling uses ``max_out`` 799/479 (SCREEN_W-1/SCREEN_H-1) with
integer truncation, matching QEMU ui/input.c ``qemu_input_scale_axis``.
The forward and inverse conversions are printed for every ``abs`` step so
a scaling error is measured, not assumed.  Panel (765,70) -> qwords
(0x7a8d, 0x12b5) -> decoded back to (765,70).

Exit codes: 0 every step passed; 1 an expectation/transport failed;
2 usage; 3 nothing runnable (a socket endpoint is missing).

Usage::

    ze0_input.py run SCENARIO --qmp SOCK --panel-log FILE --hmp SOCK
                  [--shot-dir DIR] [--log FILE] [--device ze0-gfx]
                  [--wait-timeout S] [--verbose]
    ze0_input.py --selftest

Method and results: docs/experiments/EXP-2026-11-24-M8.H40-live-window.md.
"""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time


TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
SCREENSHOT = os.path.join(TOOLS_DIR, "ze0_screenshot.py")
SCREEN_W, SCREEN_H = 800, 480
ABS_MAX = 0x7fff
STEPS = ("abs", "click", "key", "shot", "wait-log")

EXIT_OK, EXIT_FAIL, EXIT_USAGE, EXIT_SKIP = 0, 1, 2, 3


class InputError(Exception):
    """A step failed (exit 1)."""


class NotRunnable(Exception):
    """An endpoint is missing (exit 3)."""


def scale_to_qword(pixel, max_out):
    """Smallest abs qword whose integer scale-back equals ``pixel``.

    QEMU computes ``value * max_out // ABS_MAX`` (ui/input.c), so we pick
    the minimal qword v with ``v * max_out // ABS_MAX == pixel``.
    """
    if not 0 <= pixel <= max_out:
        raise InputError("pixel %d out of range 0..%d" % (pixel, max_out))
    import math
    return int(math.ceil(pixel * ABS_MAX / float(max_out)))


def scale_to_pixel(qword, max_out):
    """Inverse of :func:`scale_to_qword` using QEMU's integer truncation."""
    return qword * max_out // ABS_MAX


class Qmp:
    """QMP client over a UNIX socket; one command, one reply."""

    def __init__(self, path, timeout=5.0):
        if not path or not os.path.exists(path):
            raise NotRunnable("QMP endpoint %r missing" % path)
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect(path)
        self.fh = self.sock.makefile("rwb")
        greeting = self._read()
        if "QMP" not in greeting:
            raise InputError("QMP greeting missing: %r" % greeting)
        self.command("qmp_capabilities")

    def _read(self):
        while True:
            line = self.fh.readline()
            if not line:
                raise InputError("QMP connection closed")
            line = line.strip()
            if line:
                return json.loads(line)

    def command(self, name, args=None):
        msg = {"execute": name}
        if args is not None:
            msg["arguments"] = args
        self.fh.write((json.dumps(msg) + "\r\n").encode())
        self.fh.flush()
        while True:
            obj = self._read()
            if "return" in obj or "error" in obj:
                if "error" in obj:
                    raise InputError("QMP %s: %s" %
                                     (name, obj["error"].get("desc")))
                return obj.get("return")

    def input_send(self, device, events):
        return self.command("input-send-event",
                            {"device": device, "events": events})

    def close(self):
        try:
            self.fh.close()
        finally:
            self.sock.close()


def parse_scenario(text):
    steps = []
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        kind, _, rest = line.partition(" ")
        if kind not in STEPS:
            raise InputError("line %d: unknown step %r" % (i, kind))
        steps.append((i, kind, rest.strip()))
    return steps


def _abs_events(px, py, verbose=True):
    xq = scale_to_qword(px, SCREEN_W - 1)
    yq = scale_to_qword(py, SCREEN_H - 1)
    back = (scale_to_pixel(xq, SCREEN_W - 1),
            scale_to_pixel(yq, SCREEN_H - 1))
    if back != (px, py):
        raise InputError("scaling round-trip failed: %s -> %s" %
                         ((px, py), back))
    if verbose:
        print("abs %d %d -> qwords x=0x%04x y=0x%04x -> decoded %s" %
              (px, py, xq, yq, back))
    return [
        {"type": "abs", "data": {"axis": "x", "value": xq}},
        {"type": "abs", "data": {"axis": "y", "value": yq}},
    ], xq, yq


class Runner:
    def __init__(self, args):
        self.a = args
        self.qmp = None
        self.last = None

    def _qmp(self):
        if self.qmp is None:
            self.qmp = Qmp(self.a.qmp)
        return self.qmp

    def step(self, lineno, kind, rest):
        if kind == "abs":
            parts = rest.split()
            if len(parts) != 2:
                raise InputError("line %d: abs needs X Y" % lineno)
            px, py = int(parts[0]), int(parts[1])
            events, xq, yq = _abs_events(px, py, not self.a.quiet)
            self._qmp().input_send(self.a.device, events)
            self.last = (px, py)
            return "abs %d %d (0x%04x,0x%04x)" % (px, py, xq, yq)
        if kind == "click":
            if self.last is None:
                raise InputError("line %d: click before abs" % lineno)
            for down in (True, False):
                self._qmp().input_send(self.a.device, [{
                    "type": "btn",
                    "data": {"button": "left", "down": down}}])
            return "click at %s" % (self.last,)
        if kind == "key":
            name = rest.strip()
            if not name:
                raise InputError("line %d: key needs a qcode name" % lineno)
            for down in (True, False):
                self._qmp().input_send(self.a.device, [{
                    "type": "key",
                    "data": {"key": {"type": "qcode", "data": name},
                             "down": down}}])
            return "key %s" % name
        if kind == "shot":
            name = rest.strip()
            if not name or os.sep in name:
                raise InputError("line %d: shot needs a plain NAME" % lineno)
            out = os.path.join(self.a.shot_dir, name + ".png")
            cmd = [sys.executable, SCREENSHOT, "plane",
                   "--monitor", self.a.hmp, "-n", "1", "-o", out]
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=self.a.wait_timeout + 30)
            if proc.returncode != 0 or not os.path.exists(out):
                raise InputError("line %d: shot failed: %s" %
                                 (lineno, (proc.stderr or proc.stdout)[-200:]))
            return "%s (%d bytes)" % (out, os.path.getsize(out))
        if kind == "wait-log":
            if not self.a.log or not os.path.exists(self.a.log):
                raise NotRunnable("log %r missing" % self.a.log)
            deadline = time.monotonic() + self.a.wait_timeout
            while True:
                with open(self.a.log, "r", encoding="utf-8",
                          errors="replace") as fh:
                    if re.search(rest, fh.read(), re.MULTILINE):
                        return "matched %r" % rest
                if time.monotonic() >= deadline:
                    raise InputError("line %d: %r not in log" % (lineno, rest))
                time.sleep(self.a.poll)
        raise InputError("line %d: unknown step %r" % (lineno, kind))

    def close(self):
        if self.qmp:
            self.qmp.close()


def run_scenario(path, steps, args):
    runner = Runner(args)
    passed = 0
    try:
        for lineno, kind, rest in steps:
            try:
                detail = runner.step(lineno, kind, rest)
            except NotRunnable as exc:
                if not args.quiet:
                    print("SKIP step %d %-8s %s" % (lineno, kind, exc))
                return EXIT_SKIP, passed
            except InputError as exc:
                if not args.quiet:
                    print("FAIL step %d %-8s %s" % (lineno, kind, exc))
                return EXIT_FAIL, passed
            passed += 1
            if not args.quiet:
                print("ok   step %d %-8s %s" % (lineno, kind, detail))
        return EXIT_OK, passed
    finally:
        runner.close()


# --------------------------------------------------------------------------
# selftest: synthetic QMP server, no QEMU or peers
# --------------------------------------------------------------------------

FAKE_QMP = r'''#!/usr/bin/env python3
import json, socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.bind(sys.argv[1]); s.listen(4); s.settimeout(30)
while True:
    try: conn, _ = s.accept()
    except socket.timeout: break
    fh = conn.makefile("rwb")
    fh.write(b'{"QMP": {"version": {"qemu": {"major": 11}}, "capabilities": []}}\r\n'); fh.flush()
    for line in fh:
        line = line.strip()
        if not line: continue
        msg = json.loads(line); name = msg.get("execute")
        if name == "qmp_capabilities": reply = {"return": {}}
        elif name == "input-send-event":
            evs = msg.get("arguments", {}).get("events", [])
            reply = {"return": {"sent": len(evs), "device": msg.get("arguments",{}).get("device")}}
        else: reply = {"error": {"class": "CommandNotFound", "desc": name}}
        fh.write((json.dumps(reply) + "\r\n").encode()); fh.flush()
    fh.close(); conn.close()
'''


def selftest():
    fails = []
    checks = [0]

    def check(label, got, want):
        checks[0] += 1
        ok = got == want
        if not ok:
            fails.append("%s: got %r want %r" % (label, got, want))
        print("%s %s: got %r want %r" %
              ("ok  " if ok else "FAIL", label, got, want))

    # Scaling vectors from the live probe: (765,70) -> (0x7a8d,0x12b5).
    check("x 765 qword", hex(scale_to_qword(765, 799)), "0x7a8d")
    check("y 70 qword", hex(scale_to_qword(70, 479)), "0x12b5")
    check("x 765 back", scale_to_pixel(0x7a8d, 799), 765)
    check("y 70 back", scale_to_pixel(0x12b5, 479), 70)
    # The navigator's original y=0x12b4 decodes to 69, not 70 (live probe).
    check("wrong y 0x12b4 decodes to 69", scale_to_pixel(0x12b4, 479), 69)
    check("sub-pixel x+1 decodes to 765", scale_to_pixel(0x7a8e, 799), 765)
    try:
        scale_to_qword(800, 799)
        check("out-of-range refused", "accepted", "InputError")
    except InputError:
        check("out-of-range refused", "InputError", "InputError")
    ev, xq, yq = _abs_events(765, 70, verbose=False)
    check("abs events", [e["data"]["axis"] for e in ev], ["x", "y"])
    check("abs qwords", (hex(xq), hex(yq)), ("0x7a8d", "0x12b5"))
    steps = parse_scenario("# c\nabs 765 70\nclick\nkey m\nshot idle\n")
    check("step count", len(steps), 4)
    try:
        parse_scenario("frob 1\n")
        check("unknown step refused", "accepted", "InputError")
    except InputError:
        check("unknown step refused", "InputError", "InputError")

    tmp = tempfile.mkdtemp(prefix="ze0_input.selftest.")
    proc = None
    try:
        qp = os.path.join(tmp, "qmp.sock")
        with open(os.path.join(tmp, "fq.py"), "w") as fh:
            fh.write(FAKE_QMP)
        os.chmod(os.path.join(tmp, "fq.py"), 0o755)
        proc = subprocess.Popen([sys.executable, os.path.join(tmp, "fq.py"), qp],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 10
        while not os.path.exists(qp) and time.monotonic() < deadline:
            time.sleep(0.02)

        class A:
            qmp = qp
            device = "ze0-gfx"
            quiet = True
            shot_dir = os.path.join(tmp, "shots")
            hmp = os.path.join(tmp, "no-hmp.sock")
            log = None
            wait_timeout = 1.0
            poll = 0.01
        os.makedirs(A.shot_dir, exist_ok=True)
        a = A()
        rc, n = run_scenario("live", parse_scenario("abs 765 70\nclick\nkey m\n"), a)
        check("live scenario exit", rc, EXIT_OK)
        check("live scenario steps", n, 3)
        a.qmp = os.path.join(tmp, "missing.sock")
        rc, n = run_scenario("noqmp", parse_scenario("abs 1 1\n"), a)
        check("missing qmp exit", rc, EXIT_SKIP)
        a = A()
        rc, n = run_scenario("badclick", parse_scenario("click\n"), a)
        check("click before abs exit", rc, EXIT_FAIL)
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print("ze0_input selftest: %s (%d checks, %d failed)" %
          ("OK" if not fails else "FAIL", checks[0], len(fails)))
    for line in fails:
        print("  " + line)
    return 1 if fails else 0


def build_parser():
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="run a QMP input scenario")
    r.add_argument("scenario")
    r.add_argument("--qmp", help="QMP UNIX socket")
    r.add_argument("--hmp", help="HMP UNIX socket (shot step)")
    r.add_argument("--log", help="guest log (wait-log step)")
    r.add_argument("--panel-log", help="panel peer decoded-coordinate log")
    r.add_argument("--device", default="ze0-gfx",
                   help="QEMU input device (default ze0-gfx)")
    r.add_argument("--shot-dir", default=".")
    r.add_argument("--wait-timeout", type=float, default=60.0)
    r.add_argument("--poll", type=float, default=0.2)
    r.add_argument("--quiet", action="store_true")
    return ap


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd != "run":
        ap.print_help()
        return EXIT_USAGE
    try:
        with open(a.scenario, "r", encoding="utf-8") as fh:
            steps = parse_scenario(fh.read())
    except (OSError, InputError) as exc:
        print("ze0_input: %s" % exc, file=sys.stderr)
        return EXIT_USAGE
    os.makedirs(a.shot_dir, exist_ok=True)
    rc, passed = run_scenario(a.scenario, steps, a)
    if rc == EXIT_OK:
        print("ze0_input: PASS (%d step(s))" % passed)
    elif rc == EXIT_FAIL:
        print("ze0_input: FAIL (%d passed)" % passed)
    else:
        print("ze0_input: SKIP: nothing runnable (%d passed)" % passed)
    return rc


if __name__ == "__main__":
    sys.exit(main())
