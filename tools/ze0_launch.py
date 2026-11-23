#!/usr/bin/env python3
"""Start the emulated head unit with its peers in one command (M8.H39).

One process tree: QEMU ``-M ze0`` booting the unit's own kernel (NK1 from
the unit flash) plus ROM image A from the card, with a host chardev socket
per serial line, and the host peers attached to those sockets.  Everything
goes into one work directory (sockets, logs, the IPL patch); the card is
opened with ``snapshot=on`` and is never written.  The guide is
``docs/emulator/running.md``.

Lines and peers (``--peer NAME``, repeatable; default ``panel``):

  =====  ========  ===================================  ==================
  line   peer      tool                                 state (2026-11-22)
  =====  ========  ===================================  ==================
  sci3   panel     tools/ze0_peers/panel.py --sci3      real protocol: the
                                                        handshake and touch
                                                        frames of lcddrv.dll
  sci7   gps       tools/ze0_peers/gps.py               model: frames from
                                                        docs, no fix yet
                                                        (M8.H73)
  sci1   micon     tools/ze0_peers/micon.py             model: replies not
                                                        accepted (M8.H45)
  sci8   bt        tools/ze0_peers/bt.py                stub (M8.H56)
  =====  ========  ===================================  ==================

``vcan`` (ACC/power on ``UAT3:``) needs the external UART model M8.H3 and
cannot be attached yet; the launcher refuses it with that reason.

Each peer with a control socket gets ``WORK/<peer>.ctl`` for
``tools/ze0_ui.py`` (``--panel-sock WORK/panel.ctl``, ``--gps-sock
WORK/gps.ctl``); the HMP monitor is ``WORK/mon.sock`` (screenshots:
``tools/ze0_screenshot.py screen --monitor WORK/mon.sock -o x.png``).

Usage:
  ze0_launch.py --card CARD.img --flash NAND.bin [--peer gps] [--gdb 1240]
                [--workdir DIR] [--qemu PATH] [--timeout S] [--dry-run]
  ze0_launch.py --selftest
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DEFAULT_NK = os.path.join(REPO, "firmware", "unit-flash", "nk1-QY7200ND.bin")
# Debug-string sink of NK1's nk.exe (dbgmsg=, M8.C1q).
NK1_DBGMSG = "0x880404c4"

# name -> (line, argv builder)
PEERS = {
    "panel": ("sci3", lambda w: [
        sys.executable, os.path.join(HERE, "ze0_peers", "panel.py"),
        "--sci3", os.path.join(w, "sci3.sock"),
        "--control", os.path.join(w, "panel.ctl"), "--forever",
        "--out", os.path.join(w, "panel.events")]),
    "gps": ("sci7", lambda w: [
        sys.executable, os.path.join(HERE, "ze0_peers", "gps.py"),
        "--socket", os.path.join(w, "sci7.sock"), "--no-fix",
        "--control", os.path.join(w, "gps.ctl")]),
    "micon": ("sci1", lambda w: [
        sys.executable, os.path.join(HERE, "ze0_peers", "micon.py"),
        "--socket", os.path.join(w, "sci1.sock"),
        "--control", os.path.join(w, "micon.ctl"),
        "--log", os.path.join(w, "micon.jsonl")]),
    "bt": ("sci8", lambda w: [
        sys.executable, os.path.join(HERE, "ze0_peers", "bt.py"),
        "--socket", os.path.join(w, "sci8.sock"), "--mode", "absent"]),
}
UNAVAILABLE = {
    "vcan": "UAT3: is not modelled on -M ze0 yet (TODO M8.H3)",
}


def qemu_argv(qemu, card, nk, flash, ipl, work, lines, gdb=None, stop=False,
              icount="shift=0,sleep=off"):
    """The QEMU command line; ``lines`` is the list of SCIF names (sci3...)."""
    mopts = ["ze0", "dbgmsg=" + NK1_DBGMSG, "nk=" + nk, "ipl-patch=" + ipl,
             "flash=" + flash]
    mopts += ["%s=c%s" % (ln, ln[3:]) for ln in lines]
    argv = [qemu, "-M", ",".join(mopts), "-kernel", card,
            "-drive", "if=sd,index=0,id=sd0,file=%s,format=raw,snapshot=on" % card]
    for ln in lines:
        argv += ["-chardev", "socket,id=c%s,path=%s,server=on,wait=off" %
                 (ln[3:], os.path.join(work, ln + ".sock"))]
    argv += ["-icount", icount, "-nographic",
             "-serial", "file:" + os.path.join(work, "serial.log"),
             "-monitor", "unix:%s,server,nowait" % os.path.join(work, "mon.sock")]
    if gdb:
        argv += ["-gdb", "tcp::%d" % gdb]
    if stop:
        argv += ["-S"]
    return argv


def plan(args):
    """Validate the peer list; return (lines, peer argvs) or raise SystemExit."""
    names = args.peer or ["panel"]
    bad = [n for n in names if n not in PEERS]
    for n in bad:
        raise SystemExit("ze0_launch: peer %r: %s" %
                         (n, UNAVAILABLE.get(n, "unknown peer; known: " +
                                             ", ".join(sorted(PEERS)))))
    lines = []
    peers = []
    for n in dict.fromkeys(names):
        line, build = PEERS[n]
        lines.append(line)
        peers.append((n, build(args.workdir)))
    return lines, peers


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--card", help="SD card image (US or EU 2011)")
    ap.add_argument("--flash", help="unit NOR flash dump (8 MiB, never committed)")
    ap.add_argument("--nk", default=DEFAULT_NK, help="NK1 kernel file")
    ap.add_argument("--qemu", default=os.environ.get("QEMU", "qemu-system-sh4"))
    ap.add_argument("--peer", action="append",
                    help="panel | gps | micon | bt (repeat; default panel)")
    ap.add_argument("--workdir")
    ap.add_argument("--gdb", type=int, help="gdbstub TCP port")
    ap.add_argument("--stop", action="store_true", help="freeze until gdb continues")
    ap.add_argument("--timeout", type=float, default=0, help="seconds, 0 = until ^C")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.card or not args.flash:
        ap.error("--card and --flash are required")
    args.workdir = os.path.abspath(args.workdir or tempfile.mkdtemp(prefix="ze0-"))
    os.makedirs(args.workdir, exist_ok=True)
    lines, peers = plan(args)
    ipl = os.path.join(args.workdir, "ipl.txt")
    ipl_cmd = [sys.executable, os.path.join(HERE, "ze0_ipl.py"), "patch",
               args.card, "-o", ipl, "--nk", args.nk]
    qargv = qemu_argv(args.qemu, args.card, args.nk, args.flash, ipl,
                      args.workdir, lines, args.gdb, args.stop)
    print("work dir: %s" % args.workdir)
    print("ipl:      %s" % " ".join(map(shlex.quote, ipl_cmd)))
    print("qemu:     %s" % " ".join(map(shlex.quote, qargv)))
    for name, pargv in peers:
        print("peer %-5s %s" % (name + ":", " ".join(map(shlex.quote, pargv))))
    if args.dry_run:
        return 0
    if shutil.which(args.qemu) is None and not os.path.exists(args.qemu):
        raise SystemExit("ze0_launch: no QEMU at %r (build: tools/qemu-ze0/build.sh)"
                         % args.qemu)
    subprocess.run(ipl_cmd, check=True, stdout=subprocess.DEVNULL)
    procs = []
    try:
        q = subprocess.Popen(qargv, stdout=open(os.path.join(args.workdir, "qemu.out"), "w"),
                             stderr=subprocess.STDOUT)
        procs.append(q)
        for ln in lines:
            sock = os.path.join(args.workdir, ln + ".sock")
            for _ in range(100):
                if os.path.exists(sock):
                    break
                time.sleep(0.1)
        for name, pargv in peers:
            procs.append(subprocess.Popen(
                pargv, stdout=open(os.path.join(args.workdir, name + ".log"), "w"),
                stderr=subprocess.STDOUT))
        print("running; serial log %s; ^C stops" % os.path.join(args.workdir, "serial.log"))
        t0 = time.time()
        while q.poll() is None:
            if args.timeout and time.time() - t0 > args.timeout:
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for p in reversed(procs):
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
        for p in procs:
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()
    return 0


def selftest():
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))

    w = "/w"
    argv = qemu_argv("q", "card.img", "nk1.bin", "nand.bin", "/w/ipl.txt", w,
                     ["sci3", "sci7"], gdb=1240)
    m = argv[argv.index("-M") + 1]
    check("machine options",
          m, "ze0,dbgmsg=0x880404c4,nk=nk1.bin,ipl-patch=/w/ipl.txt,"
             "flash=nand.bin,sci3=c3,sci7=c7")
    check("chardev per line",
          [a for a in argv if a.startswith("socket,")],
          ["socket,id=c3,path=/w/sci3.sock,server=on,wait=off",
           "socket,id=c7,path=/w/sci7.sock,server=on,wait=off"])
    check("card is read-only", any("snapshot=on" in a for a in argv), True)
    check("gdb port", argv[argv.index("-gdb") + 1], "tcp::1240")
    check("monitor socket", argv[argv.index("-monitor") + 1],
          "unix:/w/mon.sock,server,nowait")

    class A:
        workdir = w
        peer = None
    lines, peers = plan(A)
    check("default peer", [n for n, _ in peers], ["panel"])
    check("default line", lines, ["sci3"])
    check("panel talks to sci3", "/w/sci3.sock" in peers[0][1], True)
    A.peer = ["panel", "gps", "panel"]
    lines, peers = plan(A)
    check("duplicates folded", lines, ["sci3", "sci7"])
    # negative controls: an unmodelled line and an unknown name are refused
    for bad, why in (("vcan", "M8.H3"), ("nope", "unknown peer")):
        A.peer = [bad]
        try:
            plan(A)
            check("refuse " + bad, "accepted", "refused")
        except SystemExit as exc:
            check("refuse " + bad, why in str(exc), True)
    check("NK1 file exists", os.path.exists(DEFAULT_NK), True)
    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
