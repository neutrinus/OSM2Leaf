#!/usr/bin/env python3
"""Run a scripted scenario against a live ``-M ze0`` guest (TODO M8.H7).

A scenario is a text file of one step per line, so an L4 test is a file in
the repository and not a shell history.  The runner drives three kinds of
endpoint:

* the QEMU monitor, over QMP (``--qmp UNIX_SOCK``) for guest time and over
  HMP (``--hmp UNIX_SOCK``) for the screenshot step, which reuses
  ``tools/ze0_screenshot.py screen``;
* the peer control sockets of ``docs/research/qemu-connectors.md``
  (``--panel-sock`` for ``tap``/``key``, ``--gps-sock`` for ``gps``), each a
  UNIX stream socket that accepts one command line and answers one line
  starting with ``OK``;
* the guest log file (``--log FILE``) for ``wait-log``.

Step grammar (one per line, ``#`` starts a comment, blank lines ignored)::

    wait-log REGEX          wait until REGEX matches a line of --log
    sleep-guest SECONDS     wait SECONDS of guest time (QMP), or wall clock
    tap X Y                 send a tap at screen pixel X Y to the panel peer
    key NAME                send a key by name to the panel peer
    gps LAT LON             send a position in decimal degrees to the GPS peer
    shot NAME               save the screen to SHOT_DIR/NAME.png
    expect-hash NAME SHA    require sha256(SHOT_DIR/NAME.png) == SHA

Arguments after the step keyword are split on whitespace; the ``wait-log``
pattern is the rest of the line verbatim, so it may contain spaces.

``tap``, ``key`` and ``gps`` call the peer when it exists and exit ``3``
(nothing runnable) when its socket is absent.  ``sleep-guest`` needs ``--qmp``
and ``shot`` needs ``--hmp``; a step whose endpoint is missing is also ``3``.
``wait-log`` needs ``--log`` to exist.

Exit codes:

===== ==============================================================
``0`` every step passed
``1`` an expectation failed (a hash mismatch, a ``wait-log`` timeout, a
      peer answer that is not ``OK``, a screenshot command that failed)
``2`` usage error (bad argument, missing scenario file)
``3`` nothing runnable: a step's endpoint does not exist
===== ==============================================================

Usage::

    ze0_ui.py run SCENARIO [--qmp SOCK] [--hmp SOCK] [--log FILE]
                [--panel-sock SOCK] [--gps-sock SOCK] [--shot-dir DIR]
                [--guest-clock VA] [--wait-timeout S] [--verbose]
    ze0_ui.py --selftest

``--guest-clock`` is a physical word the guest clock counts in (EU2011
``CurMSec`` is ``0x09e41888``); without it ``sleep-guest`` falls back to a
wall-clock sleep and says so.  ``--shot-cmd`` replaces the screenshot
command for a synthetic test (it is called as ``CMD --monitor SOCK -o OUT``).

Peer commands run verbatim as ``tap X Y``, ``key NAME``, ``gps LAT LON``.
Method and results: docs/experiments/EXP-2026-11-22-M8.H7-ui-scenario.md.
"""

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
SCREENSHOT = os.path.join(TOOLS_DIR, "ze0_screenshot.py")
STEP_WORDS = ("wait-log", "sleep-guest", "tap", "key", "gps", "shot",
              "expect-hash")

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_SKIP = 3


class StepError(Exception):
    """A step failed its expectation (exit 1)."""


class NotRunnable(Exception):
    """A step's endpoint does not exist (exit 3)."""


class Step:
    __slots__ = ("lineno", "kind", "args", "raw")

    def __init__(self, lineno, kind, args, raw):
        self.lineno = lineno
        self.kind = kind
        self.args = args
        self.raw = raw

    def __repr__(self):
        return "Step(%d, %s, %r)" % (self.lineno, self.kind, self.args)


def parse_scenario(text):
    """Parse scenario text into steps; a bad line is a ``StepError``."""
    steps = []
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        kind, _, rest = line.partition(" ")
        if kind not in STEP_WORDS:
            raise StepError("line %d: unknown step %r" % (i, kind))
        steps.append(Step(i, kind, rest.strip(), line))
    return steps


def _need(path, what):
    if not path:
        raise NotRunnable("%s endpoint not given" % what)
    if not os.path.exists(path):
        raise NotRunnable("%s endpoint %s does not exist" % (what, path))
    return path


def _connect(path, timeout=5.0):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(path)
    return s


class Qmp:
    """Minimal QMP client: capabilities, then ``human-monitor-command``."""

    def __init__(self, path, timeout=5.0):
        self.sock = _connect(path, timeout)
        self.fh = self.sock.makefile("rwb")
        greeting = self._read_line()
        if "QMP" not in greeting:
            raise StepError("QMP greeting missing: %r" % greeting)
        self.command("qmp_capabilities")

    def _read_line(self):
        while True:
            line = self.fh.readline()
            if not line:
                raise StepError("QMP connection closed")
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except ValueError:
                raise StepError("QMP sent a non-JSON line: %r" % line[:80])

    def _read_reply(self):
        while True:
            obj = self._read_line()
            if "return" in obj or "error" in obj:
                return obj

    def command(self, name, arguments=None):
        msg = {"execute": name}
        if arguments is not None:
            msg["arguments"] = arguments
        self.fh.write((json.dumps(msg) + "\r\n").encode())
        self.fh.flush()
        obj = self._read_reply()
        if "error" in obj:
            raise StepError("QMP %s: %s" % (name, obj["error"].get("desc")))
        return obj.get("return")

    def hmp(self, command):
        return self.command("human-monitor-command",
                            {"command-line": command})

    def guest_word(self, va):
        text = self.hmp("xp /1wx 0x%x" % va) or ""
        m = re.search(r":\s*(0x[0-9a-fA-F]+)", text)
        return int(m.group(1), 16) if m else None

    def close(self):
        try:
            self.fh.close()
        finally:
            self.sock.close()


def peer_command(path, command, timeout=5.0):
    """Send one command line to a peer control socket, return its answer."""
    s = _connect(path, timeout)
    fh = s.makefile("rwb")
    try:
        fh.write(command.encode() + b"\n")
        fh.flush()
        reply = fh.readline().decode("utf-8", "replace").strip()
    finally:
        fh.close()
        s.close()
    if not reply:
        raise StepError("peer %s closed without an answer to %r"
                        % (path, command))
    if not reply.startswith("OK"):
        raise StepError("peer %s rejected %r: %s" % (path, command, reply))
    return reply


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def parse_hash(value):
    value = value.strip().lower()
    if value.startswith("sha256:"):
        value = value[7:]
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise StepError("expect-hash wants a 64-hex sha256, got %r" % value)
    return value


def _log_contains(path, pattern):
    try:
        with open(path, "rb") as fh:
            text = fh.read().decode("utf-8", "replace")
    except OSError:
        return False
    return re.search(pattern, text, re.MULTILINE) is not None


class Runner:
    def __init__(self, args):
        self.a = args
        self.qmp = None

    def _qmp(self):
        _need(self.a.qmp, "QMP")
        if self.qmp is None:
            self.qmp = Qmp(self.a.qmp)
        return self.qmp

    def run_step(self, step):
        kind = step.kind
        if kind == "wait-log":
            return self.wait_log(step)
        if kind == "sleep-guest":
            return self.sleep_guest(step)
        if kind in ("tap", "key"):
            return self.panel(step)
        if kind == "gps":
            return self.gps(step)
        if kind == "shot":
            return self.shot(step)
        if kind == "expect-hash":
            return self.expect_hash(step)
        raise StepError("line %d: unknown step %r" % (step.lineno, kind))

    def wait_log(self, step):
        _need(self.a.log, "log")
        pattern = step.args
        if not pattern:
            raise StepError("line %d: wait-log needs a regex" % step.lineno)
        try:
            re.compile(pattern)
        except re.error as exc:
            raise StepError("line %d: bad regex %r: %s"
                            % (step.lineno, pattern, exc))
        deadline = time.monotonic() + self.a.wait_timeout
        while True:
            if _log_contains(self.a.log, pattern):
                return "matched %r" % pattern
            if time.monotonic() >= deadline:
                raise StepError("line %d: %r not in %s within %.1fs"
                                % (step.lineno, pattern, self.a.log,
                                   self.a.wait_timeout))
            time.sleep(self.a.poll)

    def sleep_guest(self, step):
        try:
            seconds = float(step.args)
        except ValueError:
            raise StepError("line %d: sleep-guest needs a number"
                            % step.lineno)
        if seconds < 0:
            raise StepError("line %d: sleep-guest needs a positive number"
                            % step.lineno)
        if self.a.guest_clock is None:
            time.sleep(seconds)
            return "slept %.3fs wall clock (no --guest-clock)" % seconds
        qmp = self._qmp()
        start = qmp.guest_word(self.a.guest_clock)
        if start is None:
            raise StepError("line %d: cannot read --guest-clock 0x%x"
                            % (step.lineno, self.a.guest_clock))
        target = start + int(round(seconds * 1000))
        deadline = time.monotonic() + self.a.wait_timeout
        while True:
            now = qmp.guest_word(self.a.guest_clock)
            if now is not None and now >= target:
                return "guest clock 0x%x -> 0x%x (+%d ms)" % (
                    start, now, now - start)
            if time.monotonic() >= deadline:
                raise StepError("line %d: guest clock did not advance %d ms "
                                "within %.1fs" % (step.lineno,
                                                  target - start,
                                                  self.a.wait_timeout))
            time.sleep(self.a.poll)

    def panel(self, step):
        _need(self.a.panel_sock, "panel")
        if step.kind == "tap":
            parts = step.args.split()
            if len(parts) != 2:
                raise StepError("line %d: tap needs X Y" % step.lineno)
            try:
                int(parts[0]), int(parts[1])
            except ValueError:
                raise StepError("line %d: tap needs integer X Y" % step.lineno)
        else:
            if not step.args:
                raise StepError("line %d: key needs a name" % step.lineno)
        return peer_command(self.a.panel_sock, step.raw)

    def gps(self, step):
        _need(self.a.gps_sock, "GPS")
        parts = step.args.split()
        if len(parts) != 2:
            raise StepError("line %d: gps needs LAT LON" % step.lineno)
        try:
            lat, lon = float(parts[0]), float(parts[1])
        except ValueError:
            raise StepError("line %d: gps needs decimal LAT LON" % step.lineno)
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            raise StepError("line %d: gps %g %g out of range"
                            % (step.lineno, lat, lon))
        return peer_command(self.a.gps_sock, step.raw)

    def shot(self, step):
        _need(self.a.hmp, "HMP")
        name = step.args
        if not name or os.sep in name:
            raise StepError("line %d: shot needs a plain NAME" % step.lineno)
        out = os.path.join(self.a.shot_dir, name + ".png")
        cmd = list(self.a.shot_cmd) if self.a.shot_cmd else [
            sys.executable, SCREENSHOT, "screen"]
        cmd += ["--monitor", self.a.hmp, "-o", out]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=self.a.wait_timeout + 30.0)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise StepError("line %d: screenshot command failed: %s"
                            % (step.lineno, exc))
        if proc.returncode != 0:
            raise StepError("line %d: screenshot command failed (%d): %s"
                            % (step.lineno, proc.returncode,
                               (proc.stderr or proc.stdout).strip()[-300:]))
        if not os.path.exists(out):
            raise StepError("line %d: screenshot %s was not written"
                            % (step.lineno, out))
        return "%s (%d bytes)" % (out, os.path.getsize(out))

    def expect_hash(self, step):
        parts = step.args.split()
        if len(parts) != 2:
            raise StepError("line %d: expect-hash needs NAME SHA"
                            % step.lineno)
        name, want = parts[0], parse_hash(parts[1])
        path = os.path.join(self.a.shot_dir, name + ".png")
        if not os.path.exists(path):
            raise StepError("line %d: %s does not exist (no shot?)"
                            % (step.lineno, path))
        got = sha256_file(path)
        if got != want:
            raise StepError("line %d: %s sha256 %s != expected %s"
                            % (step.lineno, name, got, want))
        return "%s sha256 %s" % (name, got)


def run_scenario(path, steps, args):
    runner = Runner(args)
    passed = 0
    for step in steps:
        try:
            detail = runner.run_step(step)
        except NotRunnable as exc:
            if not args.quiet:
                print("SKIP step %d %-11s %s" % (step.lineno, step.kind, exc))
            return EXIT_SKIP, passed
        except StepError as exc:
            if not args.quiet:
                print("FAIL step %d %-11s %s" % (step.lineno, step.kind, exc))
            return EXIT_FAIL, passed
        passed += 1
        if not args.quiet:
            print("ok   step %d %-11s %s" % (step.lineno, step.kind, detail))
    return EXIT_OK, passed


def load_steps(path):
    with open(path, "r", encoding="utf-8") as fh:
        return parse_scenario(fh.read())


# --------------------------------------------------------------------------
# Selftest: a synthetic QMP server, peer servers and a fake screenshot
# --------------------------------------------------------------------------

FAKE_SHOT = r'''#!/usr/bin/env python3
import sys, os
args = sys.argv[1:]
out = args[args.index("-o") + 1] if "-o" in args else None
if not out:
    sys.exit("fake shot: no -o")
# a fixed 4x2 RGB PNG-like byte string is enough: the runner only hashes it
os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
with open(out, "wb") as fh:
    fh.write(b"\x89PNG\r\n\x1a\n" + b"ze0-ui-selftest-frame" * 8)
print("fake shot -> %s" % out)
'''

FAKE_QMP = r'''#!/usr/bin/env python3
import json, os, socket, sys, threading

def serve(path):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(path)
    s.listen(4)
    s.settimeout(30)
    clock = [0x1000]
    while True:
        try:
            conn, _ = s.accept()
        except socket.timeout:
            return
        fh = conn.makefile("rwb")
        fh.write(b'{"QMP": {"version": {"qemu": {"major": 11}}, "capabilities": []}}\r\n')
        fh.flush()
        for line in fh:
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line)
            name = msg.get("execute")
            if name == "qmp_capabilities":
                reply = {"return": {}}
            elif name == "human-monitor-command":
                cmd = msg.get("arguments", {}).get("command-line", "")
                if cmd.startswith("xp"):
                    clock[0] += 0x800
                    addr = cmd.split()[-1]
                    reply = {"return": "%016x: 0x%08x\n" % (int(addr, 16), clock[0])}
                else:
                    reply = {"return": "fake hmp: %s\n" % cmd}
            else:
                reply = {"error": {"class": "CommandNotFound", "desc": name}}
            fh.write((json.dumps(reply) + "\r\n").encode())
            fh.flush()
        fh.close()
        conn.close()

serve(sys.argv[1])
'''

FAKE_PEER = r'''#!/usr/bin/env python3
import socket, sys, json

path, log = sys.argv[1], sys.argv[2]

def serve():
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(path)
    s.listen(4)
    s.settimeout(30)
    out = open(log, "a", buffering=1)
    while True:
        try:
            conn, _ = s.accept()
        except socket.timeout:
            break
        fh = conn.makefile("rwb")
        line = fh.readline().decode().strip()
        if line:
            word = line.split()[0]
            ok = word in ("tap", "key", "gps")
            out.write(line + "\n")
            fh.write((("OK %s" if ok else "ERR unknown %s") % line).encode() + b"\n")
            fh.flush()
        fh.close()
        conn.close()
    out.close()

serve()
'''


def _start(path, script, *argv):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(script)
    os.chmod(path, 0o755)
    proc = subprocess.Popen([sys.executable, path] + list(argv),
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    return proc


def _wait_socket(path, proc, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(path):
            return
        if proc.poll() is not None:
            raise RuntimeError("server %s exited %s" % (path, proc.returncode))
        time.sleep(0.02)
    raise RuntimeError("server %s did not appear" % path)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def selftest():
    fails = []
    checks = [0]

    def check(label, got, want):
        checks[0] += 1
        ok = got == want
        if not ok:
            fails.append("%s: got %r want %r" % (label, got, want))
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label,
                                         got, want))

    # ---- grammar, hashes, and pure helpers --------------------------------
    text = ("# a comment\n"
            "\n"
            "wait-log Store Mgr Ready! \\[DSK1:\\]\n"
            "sleep-guest 1\n"
            "tap 400 240\n"
            "key HOME\n"
            "gps 51.5074 -0.1278\n"
            "shot idle\n"
            "expect-hash idle " + "a" * 64 + "\n")
    steps = parse_scenario(text)
    check("step count", len(steps), 7)
    check("first step", (steps[0].kind, steps[0].args),
          ("wait-log", r"Store Mgr Ready! \[DSK1:\]"))
    check("last step", (steps[-1].kind, steps[-1].args.split()[0]),
          ("expect-hash", "idle"))
    try:
        parse_scenario("frobnicate 1\n")
        check("unknown step refused", "no error", "StepError")
    except StepError:
        check("unknown step refused", "StepError", "StepError")
    check("hash parser strips prefix", parse_hash("sha256:" + "b" * 64),
          "b" * 64)
    try:
        parse_hash("deadbeef")
        check("short hash refused", "no error", "StepError")
    except StepError:
        check("short hash refused", "StepError", "StepError")
    check("sha of empty", _sha(b""),
          "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")

    # ---- a live synthetic run --------------------------------------------
    tmp = tempfile.mkdtemp(prefix="ze0_ui.selftest.")
    procs = []
    try:
        qmp_path = os.path.join(tmp, "qmp.sock")
        panel_path = os.path.join(tmp, "panel.sock")
        gps_path = os.path.join(tmp, "gps.sock")
        panel_log = os.path.join(tmp, "panel.log")
        gps_log = os.path.join(tmp, "gps.log")
        qmp_script = os.path.join(tmp, "fake_qmp.py")
        peer_script = os.path.join(tmp, "fake_peer.py")
        shot_script = os.path.join(tmp, "fake_shot.py")
        with open(shot_script, "w", encoding="utf-8") as fh:
            fh.write(FAKE_SHOT)

        q = _start(qmp_script, FAKE_QMP, qmp_path)
        p = _start(peer_script, FAKE_PEER, panel_path, panel_log)
        g = _start(peer_script, FAKE_PEER, gps_path, gps_log)
        procs += [q, p, g]
        _wait_socket(qmp_path, q)
        _wait_socket(panel_path, p)
        _wait_socket(gps_path, g)

        frame = b"\x89PNG\r\n\x1a\n" + b"ze0-ui-selftest-frame" * 8
        good = _sha(frame)
        log = os.path.join(tmp, "serial.log")
        with open(log, "w") as fh:
            fh.write("junk\nStore Mgr Ready! [DSK1:]\nmap drawn\n")

        def args_for(shot_dir):
            a = argparse.Namespace()
            a.qmp, a.hmp = qmp_path, qmp_path
            a.log = log
            a.panel_sock, a.gps_sock = panel_path, gps_path
            a.shot_dir = shot_dir
            a.guest_clock = 0x09E41888
            a.wait_timeout = 5.0
            a.poll = 0.02
            a.quiet = True
            a.shot_cmd = [sys.executable, shot_script]
            return a

        shot_dir = os.path.join(tmp, "shots")
        os.makedirs(shot_dir)
        good_text = ("wait-log Store Mgr Ready! \\[DSK1:\\]\n"
                     "gps 51.5074 -0.1278\n"
                     "tap 400 240\n"
                     "key HOME\n"
                     "sleep-guest 1\n"
                     "shot idle\n"
                     "expect-hash idle %s\n" % good)
        rc, n = run_scenario("good", parse_scenario(good_text), args_for(shot_dir))
        check("good scenario exit", rc, EXIT_OK)
        check("good scenario steps", n, 7)
        check("panel got tap+key",
              open(panel_log).read().split("\n")[:2], ["tap 400 240", "key HOME"])
        check("gps got fix", open(gps_log).read().split("\n")[0],
              "gps 51.5074 -0.1278")

        # negative control: a wrong expect-hash fails (exit 1)
        bad_text = good_text.replace(good, "0" * 64)
        rc, n = run_scenario("badhash", parse_scenario(bad_text),
                             args_for(shot_dir))
        check("wrong hash exit", rc, EXIT_FAIL)
        check("wrong hash stops before the last step", n, 6)

        # exit-3: a tap with no panel socket is nothing runnable
        a = args_for(shot_dir)
        a.panel_sock = os.path.join(tmp, "no-panel.sock")
        rc, n = run_scenario("nopanel", parse_scenario("tap 1 1\n"), a)
        check("missing panel socket exit", rc, EXIT_SKIP)
        check("missing panel socket ran none", n, 0)
        a = args_for(shot_dir)
        a.qmp = os.path.join(tmp, "no-qmp.sock")
        rc, n = run_scenario("noqmp", parse_scenario("sleep-guest 1\n"), a)
        check("missing qmp exit", rc, EXIT_SKIP)
        a = args_for(shot_dir)
        a.log = os.path.join(tmp, "no-serial.log")
        rc, n = run_scenario("nolog", parse_scenario("wait-log x\n"), a)
        check("missing log exit", rc, EXIT_SKIP)

        # negative: wait-log timeout is exit 1, not 3 (the log exists)
        a = args_for(shot_dir)
        a.wait_timeout = 0.2
        rc, n = run_scenario("timeout", parse_scenario("wait-log NEVER-HERE\n"), a)
        check("wait-log timeout exit", rc, EXIT_FAIL)

        # negative: a peer that rejects the command is an expectation failure
        rc, n = run_scenario("badpeer", parse_scenario("tap 1\n"), args_for(shot_dir))
        check("malformed tap exit", rc, EXIT_FAIL)

        # negative: an out-of-range position is refused before the peer
        rc, n = run_scenario("badgps", parse_scenario("gps 91 0\n"),
                             args_for(shot_dir))
        check("out-of-range gps exit", rc, EXIT_FAIL)
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        for name in os.listdir(tmp):
            path = os.path.join(tmp, name)
            if os.path.isfile(path):
                os.unlink(path)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print("ze0_ui selftest: %s (%d checks, %d failed)"
          % ("OK" if not fails else "FAIL", checks[0], len(fails)))
    for line in fails:
        print("  " + line)
    return 0 if not fails else 1


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser():
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true",
                    help="run the synthetic self-test (no QEMU, no peers)")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="run a scenario file against a live guest")
    r.add_argument("scenario")
    r.add_argument("--qmp", help="QMP unix socket (guest time)")
    r.add_argument("--hmp", help="HMP unix socket (screenshot)")
    r.add_argument("--log", help="guest log file (wait-log)")
    r.add_argument("--panel-sock", help="panel peer control socket (tap, key)")
    r.add_argument("--gps-sock", help="GPS peer control socket (gps)")
    r.add_argument("--shot-dir", default=".",
                   help="where shot writes NAME.png (default: .)")
    r.add_argument("--guest-clock", type=lambda s: int(s, 0),
                   help="physical guest-clock word for sleep-guest (EU2011 "
                        "CurMSec 0x09e41888); default wall clock")
    r.add_argument("--wait-timeout", type=float, default=60.0,
                   help="seconds a wait-log or sleep-guest may take")
    r.add_argument("--poll", type=float, default=0.2,
                   help="poll interval in seconds")
    r.add_argument("--shot-cmd", nargs="+",
                   help="screenshot command prefix (default: ze0_screenshot "
                        "screen); called with --monitor SOCK -o OUT")
    r.add_argument("--quiet", action="store_true", help="only the verdict")
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
        steps = load_steps(a.scenario)
    except OSError as exc:
        print("ze0_ui: cannot read %s: %s" % (a.scenario, exc), file=sys.stderr)
        return EXIT_USAGE
    except StepError as exc:
        print("ze0_ui: %s" % exc, file=sys.stderr)
        return EXIT_USAGE
    try:
        os.makedirs(a.shot_dir, exist_ok=True)
    except OSError as exc:
        print("ze0_ui: cannot create %s: %s" % (a.shot_dir, exc),
              file=sys.stderr)
        return EXIT_USAGE
    rc, passed = run_scenario(a.scenario, steps, a)
    if rc == EXIT_OK:
        print("ze0_ui: PASS (%d step(s))" % passed)
    elif rc == EXIT_FAIL:
        print("ze0_ui: FAIL at step %d (%d passed)" % (passed + 1, passed))
    else:
        print("ze0_ui: SKIP: nothing runnable (%d passed)" % passed)
    return rc


if __name__ == "__main__":
    sys.exit(main())
