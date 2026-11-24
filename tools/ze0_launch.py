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
  uat3   vcan      tools/ze0_peers/vcan.py              model: ACC/power
                                                        frames of can.md;
                                                        wire framing open
                                                        (M8.H49)
  uat4   uat4      tools/ze0_peers/uart.py              raw bytes, TX dump
  =====  ========  ===================================  ==================

``uat3``/``uat4`` need ``ze0-h03-ext-uart.patch`` (M8.H3).

Each peer with a control socket gets ``WORK/<peer>.ctl`` for
``tools/ze0_ui.py`` (``--panel-sock WORK/panel.ctl``, ``--gps-sock
WORK/gps.ctl``); the HMP monitor is ``WORK/mon.sock`` (screenshots:
``tools/ze0_screenshot.py screen --monitor WORK/mon.sock -o x.png``).

Usage:
  ze0_launch.py --card CARD.img --flash NAND.bin [--peer gps] [--gdb 1240]
                [--workdir DIR] [--qemu PATH] [--timeout S] [--dry-run]
  ze0_launch.py --card CARD.img --flash anon     (no dump of your own: the
                image is built from firmware/unit-flash/, M6.24)
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
PEERS["vcan"] = ("uat3", lambda w: [
    sys.executable, os.path.join(HERE, "ze0_peers", "vcan.py"),
    "--socket", os.path.join(w, "uat3.sock"),
    "--control", os.path.join(w, "vcan.ctl")])
PEERS["uat4"] = ("uat4", lambda w: [
    sys.executable, os.path.join(HERE, "ze0_peers", "uart.py"),
    "--socket", os.path.join(w, "uat4.sock"),
    "--dump", os.path.join(w, "uat4.tx"),
    "--control", os.path.join(w, "uat4.ctl")])
UNAVAILABLE = {}


def resolve_flash(flash, work, nk, dry_run=False):
    """``anon`` -> WORK/flash-anon.bin built from the committed files."""
    if flash != "anon":
        return flash
    import unitflash_anon as ua
    out = os.path.join(work, "flash-anon.bin")
    if not dry_run:
        with open(out, "wb") as f:
            f.write(ua.build(ua.read(ua.PROD_DEFAULT_FILE), ua.read(nk),
                             ua.read(ua.SRAM_DEFAULT_FILE),
                             ua.read(ua.VFLASH_DEFAULT_FILE)))
    return out


def qemu_argv(qemu, card, nk, flash, ipl, work, lines, gdb=None, stop=False,
              icount="shift=0,sleep=off", flash_rw=False, display="none",
              input=None, qmp=None):
    """The QEMU command line; ``lines`` is the list of SCIF names (sci3...)."""
    mopts = ["ze0", "dbgmsg=" + NK1_DBGMSG, "nk=" + nk, "ipl-patch=" + ipl,
             "flash=" + flash]
    if flash_rw:
        mopts.append("flash-rw=on")
    if display != "none":
        mopts.append("gfx-display=on")
        if input:
            mopts.append("gfx-input=cinput")
    mopts += ["%s=c%s" % (ln, ln) for ln in lines]
    argv = [qemu, "-M", ",".join(mopts), "-kernel", card,
            "-drive", "if=sd,index=0,id=sd0,file=%s,format=raw,snapshot=on" % card]
    for ln in lines:
        argv += ["-chardev", "socket,id=c%s,path=%s,server=on,wait=off" %
                 (ln, os.path.join(work, ln + ".sock"))]
    if display != "none" and input:
        argv += ["-chardev", "socket,id=cinput,path=%s,server=on,wait=off" %
                 os.path.join(work, "input.sock")]
    argv += ["-icount", icount]
    if display == "none":
        argv += ["-nographic"]
    else:
        argv += ["-display", display]
    argv += ["-serial", "file:" + os.path.join(work, "serial.log"),
             "-monitor", "unix:%s,server,nowait" % os.path.join(work, "mon.sock")]
    if qmp:
        argv += ["-qmp", "unix:%s,server,nowait" % qmp]
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
        pargv = build(args.workdir)
        if n == "panel" and getattr(args, "input", False):
            pargv += ["--input", os.path.join(args.workdir, "input.sock"),
                      "--keymap", os.path.join(HERE, "ze0_keymap.json")]
        peers.append((n, pargv))
    return lines, peers


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--card", help="SD card image (US or EU 2011)")
    ap.add_argument("--flash", help="unit NOR flash dump (8 MiB, never committed), or "
                    "'anon': build WORK/flash-anon.bin from the committed "
                    "files with unitflash_anon.py (M6.24)")
    ap.add_argument("--flash-rw", action="store_true",
                    help="keep the guest's flash writes in the --flash file (default: "
                         "a temporary overlay; use a copy of the dump; M8.H18)")
    ap.add_argument("--nk", default=DEFAULT_NK, help="NK1 kernel file")
    ap.add_argument("--qemu", default=os.environ.get("QEMU", "qemu-system-sh4"))
    ap.add_argument("--peer", action="append",
                    help="panel | gps | micon | bt (repeat; default panel)")
    ap.add_argument("--workdir")
    ap.add_argument("--gdb", type=int, help="gdbstub TCP port")
    ap.add_argument("--stop", action="store_true", help="freeze until gdb continues")
    ap.add_argument("--timeout", type=float, default=0, help="seconds, 0 = until ^C")
    ap.add_argument("--ipl-extra", action="append", default=[],
                    help="file of extra 'PHYS HEXBYTES' lines appended to the IPL "
                         "patch (emulator-only guest patches; NK1 reloads ROM image A "
                         "from the card, so lines for image A do not survive)")
    ap.add_argument("--display", default="none",
                    help="live display: none, vnc=HOST:N, gtk, sdl (M8.H40)")
    ap.add_argument("--input", action="store_true",
                    help="attach ze0-gfx input chardev to panel peer (M8.H40)")
    ap.add_argument("--qmp", action="store_true",
                    help="expose a QMP socket on WORK/qmp.sock (M8.H40)")
    ap.add_argument("--ui-start", action="store_true",
                    help="let the UI leave INI_STARTUP and accept touch without the "
                         "audio micom: runs ze0_uistart.py on the gdb stub until the "
                         "first touch (needs --gdb; M8.C1n)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.card or not args.flash:
        ap.error("--card and --flash are required")
    args.workdir = os.path.abspath(args.workdir or tempfile.mkdtemp(prefix="ze0-"))
    os.makedirs(args.workdir, exist_ok=True)
    args.flash = resolve_flash(args.flash, args.workdir, args.nk, args.dry_run)
    lines, peers = plan(args)
    if args.ui_start:
        if not args.gdb:
            ap.error("--ui-start needs --gdb PORT")
        peers.append(("uistart", [sys.executable, os.path.join(HERE, "ze0_uistart.py"),
                                  "run", args.card, "--port", str(args.gdb),
                                  "--touch-unlock", "--nk", args.nk]))
    ipl = os.path.join(args.workdir, "ipl.txt")
    ipl_cmd = [sys.executable, os.path.join(HERE, "ze0_ipl.py"), "patch",
               args.card, "-o", ipl, "--nk", args.nk]
    qargv = qemu_argv(args.qemu, args.card, args.nk, args.flash, ipl,
                      args.workdir, lines, args.gdb, args.stop,
                      flash_rw=args.flash_rw, display=args.display,
                      input=args.input,
                      qmp=os.path.join(args.workdir, "qmp.sock") if args.qmp else None)
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
    for extra in args.ipl_extra:
        with open(extra) as src, open(ipl, "a") as dst:
            dst.write(src.read())
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
             "flash=nand.bin,sci3=csci3,sci7=csci7")
    argv_rw = qemu_argv("q", "card.img", "nk1.bin", "f.bin", "/w/ipl.txt", w,
                        [], flash_rw=True)
    check("flash-rw passes through",
          "flash-rw=on" in argv_rw[argv_rw.index("-M") + 1].split(","), True)
    check("a dump path is kept", resolve_flash("nand.bin", w, "nk1.bin"), "nand.bin")
    check("anon builds into the work dir",
          resolve_flash("anon", w, "nk1.bin", dry_run=True), "/w/flash-anon.bin")
    check("chardev per line",
          [a for a in argv if a.startswith("socket,")],
          ["socket,id=csci3,path=/w/sci3.sock,server=on,wait=off",
           "socket,id=csci7,path=/w/sci7.sock,server=on,wait=off"])
    check("card is read-only", any("snapshot=on" in a for a in argv), True)
    check("gdb port", argv[argv.index("-gdb") + 1], "tcp::1240")
    # M8.H40: live display + forwarded input + QMP socket
    argv_live = qemu_argv("q", "card.img", "nk1.bin", "f.bin", "/w/ipl.txt", w,
                          ["sci3"], display="vnc=127.0.0.1:7", input=True,
                          qmp="/w/qmp.sock")
    m_live = argv_live[argv_live.index("-M") + 1]
    check("gfx-display on", "gfx-display=on" in m_live.split(","), True)
    check("gfx-input chardev", "gfx-input=cinput" in m_live.split(","), True)
    check("input chardev socket",
          "socket,id=cinput,path=/w/input.sock,server=on,wait=off" in argv_live, True)
    check("display arg", argv_live[argv_live.index("-display") + 1], "vnc=127.0.0.1:7")
    check("qmp socket", argv_live[argv_live.index("-qmp") + 1],
          "unix:/w/qmp.sock,server,nowait")
    check("no nographic with display", "-nographic" in argv_live, False)
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
    A.peer = ["vcan"]
    lines, peers = plan(A)
    check("vcan rides on uat3", lines, ["uat3"])
    check("uat3 chardev", "uat3=cuat3" in qemu_argv("q", "c", "n", "f", "i", w,
                                                    lines)[2], True)
    for bad, why in (("nope", "unknown peer"),):
        A.peer = [bad]
        try:
            plan(A)
            check("refuse " + bad, "accepted", "refused")
        except SystemExit as exc:
            check("refuse " + bad, why in str(exc), True)
    class A2:
        workdir = w
        peer = ["panel"]
        input = True
        display = "vnc=127.0.0.1:7"
    lines2, peers2 = plan(A2)
    check("panel --input wired", "--input" in peers2[0][1], True)
    check("panel keymap wired", os.path.join(HERE, "ze0_keymap.json") in peers2[0][1], True)
    check("input socket path", os.path.join(w, "input.sock") in peers2[0][1], True)
    check("NK1 file exists", os.path.exists(DEFAULT_NK), True)
    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
