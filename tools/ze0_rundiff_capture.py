#!/usr/bin/env python3
"""Capture one ``-M ze0`` boot into a run directory for ``ze0_rundiff.py``.

The four channels are written at a *fixed guest milestone*: the Nth occurrence
of a kernel debug string in the serial log (default
``MSG_PROCESS_NAVI_MAP_CC`` x2, a guest event, not a wall-clock timeout).  The
compared ``serial.log``/``dbgmsg.log`` are cut just after that occurrence; the
uncut capture is kept as ``serial-full.log`` so the host stop-latency window
that follows the milestone stays visible.  VRAM is dumped with HMP ``pmemsave``
immediately after the QMP stop and hashed into ``vram.sha256``.  ``sd-reads.txt``
comes from a ``sdhi-trace=on,hpbdmac-trace=on`` log decoded with
``tools/ze0_sdhost.py``.

Usage:
    python3 tools/ze0_rundiff_capture.py OUTDIR \
        --qemu /path/to/qemu-system-sh4 --ipl-patch ipl.txt

    python3 tools/ze0_rundiff_capture.py --selftest   # offline, no QEMU/data

Method and measurements: docs/experiments/EXP-2026-11-22-M8.H6-run-determinism.md
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
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ze0_sdhost  # noqa: E402

VRAM_PHYS = 0x0E700000
VRAM_SIZE = 0x01860000
CURMSEC_PHYS = 0x09E41888  # VA 0x89e41888 - 0x80000000 (M8.B3)


def cut_at_milestone(raw, marker, count):
    """Bytes through the end of the *count*-th line containing *marker*."""
    pos = 0
    for _ in range(count):
        i = raw.find(marker, pos)
        if i < 0:
            return None
        nl = raw.find(b"\n", i)
        pos = len(raw) if nl < 0 else nl + 1
    return raw[:pos]


def decode_reads(log_text):
    """Ordered SD block reads as channel lines (writes excluded)."""
    lines = []
    for port, name, arg, direction, nbytes, _addr, _left, crc in ze0_sdhost.decode_dma(log_text):
        if direction == "read":
            lines.append("port %d %s arg 0x%08x %d bytes crc32 0x%08x\n"
                         % (port, name, arg, nbytes, crc))
    return lines


def hmp_command(sock_path, command, settle=0.2, timeout=120):
    """Send one HMP command; return the raw monitor bytes."""
    end = time.time() + timeout
    sock = None
    while time.time() < end:
        sock = socket.socket(socket.AF_UNIX)
        sock.settimeout(timeout)
        try:
            sock.connect(sock_path)
            break
        except (FileNotFoundError, ConnectionRefusedError):
            sock.close()
            sock = None
            time.sleep(0.1)
    if sock is None:
        raise RuntimeError("cannot connect to HMP socket %s" % sock_path)
    buf = b""
    while b"(qemu)" not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
    sock.sendall(command.encode() + b"\n")
    buf = b""
    end = time.time() + timeout
    while b"(qemu)" not in buf and time.time() < end:
        try:
            chunk = sock.recv(65536)
        except socket.timeout:
            break
        if not chunk:
            break
        buf += chunk
    time.sleep(settle)
    sock.close()
    return buf


def guest_msec(hmp_output):
    """CurMSec from an ``xp /1wx`` monitor reply, or None."""
    m = re.search(rb"09e41888:\s+0x([0-9a-fA-F]+)", hmp_output)
    return int(m.group(1), 16) if m else None


def qmp_command(qf, command):
    qf.write((json.dumps(command) + "\n").encode())
    qf.flush()
    while True:
        line = qf.readline()
        if not line:
            return None
        obj = json.loads(line)
        if "event" not in obj:
            return obj


def write_channels(outdir, marker, count, msec_text, replay):
    """Build the four compared channels from the raw captures in OUTDIR."""
    serial_path = os.path.join(outdir, "serial.log")
    with open(serial_path, "rb") as fh:
        full = fh.read()
    with open(os.path.join(outdir, "serial-full.log"), "wb") as fh:
        fh.write(full)
    cut = cut_at_milestone(full, marker.encode(), count)
    if cut is None:
        raise RuntimeError("milestone %r x%d not reached; see serial-full.log" % (marker, count))
    with open(serial_path, "wb") as fh:
        fh.write(cut)
    with open(os.path.join(outdir, "dbgmsg.log"), "wb") as fh:
        fh.write(cut.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
    with open(os.path.join(outdir, "qemu.log"), encoding="utf-8", errors="replace") as fh:
        reads = decode_reads(fh.read())
    with open(os.path.join(outdir, "sd-reads.txt"), "w") as fh:
        fh.writelines(reads)
    with open(os.path.join(outdir, "vram.bin"), "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    with open(os.path.join(outdir, "vram.sha256"), "w") as fh:
        fh.write("%s  %s#%d\n" % (digest, marker, count))
    with open(os.path.join(outdir, "guest-msec.txt"), "w") as fh:
        fh.write(msec_text or "unreadable\n")
    with open(os.path.join(outdir, "meta.txt"), "w") as fh:
        if replay:
            fh.write("query-replay %s\n" % json.dumps(replay))
        fh.write("milestone %s x%d\n" % (marker, count))
    return len(full), len(cut), len(reads), digest


def capture(args):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "qemu-ze0"))
    import mkoverlay

    size = args.size_gib << 30
    if os.path.getsize(args.card) > size or size & (size - 1):
        raise RuntimeError("card does not fit a %d GiB qcow2 overlay" % args.size_gib)
    os.makedirs(args.outdir, exist_ok=True)
    card = os.path.join(args.outdir, "card.qcow2")
    with open(card, "wb") as fh:
        fh.write(mkoverlay.build(args.card, size))
    serial = os.path.join(args.outdir, "serial.log")
    mopts = ("ze0,kernel-off=0x%x,app-off=0x%x,dbgmsg=0x%x,verinf=%s,mapdb=%s,"
             "ipl-patch=%s,sdhi-trace=on,hpbdmac-trace=on"
             % (args.kernel_off, args.app_off, args.dbgmsg, args.verinf,
                args.mapdb, args.ipl_patch))
    argv = [args.qemu, "-M", mopts, "-kernel", args.image,
            "-drive", "if=sd,index=0,file=" + card,
            "-icount", "shift=0,sleep=off",
            "-nographic", "-serial", "file:" + serial,
            "-qmp", "unix:" + args.outdir + "/qmp.sock,server,nowait",
            "-monitor", "unix:" + args.outdir + "/hmp.sock,server,nowait",
            "-d", "unimp,invalid_mem", "-D", os.path.join(args.outdir, "qemu.log")]
    with open(os.path.join(args.outdir, "qemu-argv.txt"), "w") as fh:
        fh.write(" ".join(argv) + "\n")
    proc = subprocess.Popen(argv, stdout=open(os.path.join(args.outdir, "stdout.txt"), "wb"),
                            stderr=subprocess.STDOUT)
    t0 = time.monotonic()
    msec = replay = None
    try:
        end = time.time() + 60
        qsock = None
        while time.time() < end:
            qsock = socket.socket(socket.AF_UNIX)
            qsock.settimeout(60)
            try:
                qsock.connect(os.path.join(args.outdir, "qmp.sock"))
                break
            except (FileNotFoundError, ConnectionRefusedError):
                qsock.close()
                qsock = None
                time.sleep(0.1)
        if qsock is None:
            raise RuntimeError("cannot connect to QMP socket")
        qf = qsock.makefile("rwb")
        qmp_command(qf, {"execute": "qmp_capabilities"})
        while time.monotonic() - t0 < args.maxwall and proc.poll() is None:
            raw = open(serial, "rb").read() if os.path.exists(serial) else b""
            if raw.count(args.marker.encode()) >= args.count:
                break
            time.sleep(0.2)
        deadline = time.monotonic() + args.maxwall
        while True:
            msec = hmp_command(os.path.join(args.outdir, "hmp.sock"),
                               "xp /1wx 0x%08x" % CURMSEC_PHYS, settle=0.0, timeout=20)
            now = guest_msec(msec)
            if not args.msec_target or (now is not None and now >= args.msec_target):
                break
            if time.monotonic() > deadline or proc.poll() is not None:
                break
            time.sleep(0.05)
        qmp_command(qf, {"execute": "stop"})
        replay = qmp_command(qf, {"execute": "query-replay"})
        hmp_command(os.path.join(args.outdir, "hmp.sock"),
                    'pmemsave 0x%x 0x%x "%s"'
                    % (VRAM_PHYS, VRAM_SIZE, os.path.join(args.outdir, "vram.bin")))
        vram = os.path.join(args.outdir, "vram.bin")
        for _ in range(200):
            if os.path.exists(vram) and os.path.getsize(vram) == VRAM_SIZE:
                break
            time.sleep(0.2)
        qmp_command(qf, {"execute": "quit"})
    finally:
        try:
            proc.wait(20)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    full_n, cut_n, reads_n, digest = write_channels(
        args.outdir, args.marker, args.count,
        msec.decode(errors="replace") if msec else "", replay)
    print("wall %.1fs, serial %d -> %d bytes, %d SD reads, VRAM %s"
          % (time.monotonic() - t0, full_n, cut_n, reads_n, digest))
    return 0 if proc.returncode == 0 else 1


# ---------------------------------------------------------------------------
# Offline selftest: parsing and channel writing, no QEMU and no vendor bytes.
# ---------------------------------------------------------------------------

def selftest():
    fails = []

    def check(label, got, want):
        ok = got == want
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))
        if not ok:
            fails.append(label)

    mark = b"MSG_PROCESS_NAVI_MAP_CC"
    raw = b"one\n" + mark + b" first\nmid\n" + mark + b" second\ntail\n"
    check("cut includes the Nth milestone line", cut_at_milestone(raw, mark, 2),
          b"one\n" + mark + b" first\nmid\n" + mark + b" second\n")
    check("cut returns None when unavailable", cut_at_milestone(raw, mark, 3), None)
    check("CurMSec reply parses", guest_msec(b"junk\r\n09e41888: 0x00007cea\r\n(qemu) "), 0x7CEA)
    check("CurMSec absent is None", guest_msec(b"(qemu) "), None)

    log = "\n".join([
        "ze0-sdhi0: wr16 +0x04 = 0x0002",
        "ze0-sdhi0: wr16 +0x00 = 0x1811",
        "ze0-hpbdmac: ch8 read 512 bytes, DDAR 0xa99c1000, left 0, crc32 0x00000007, head 00",
        "ze0-sdhi0: wr16 +0x00 = 0x1812",
        "ze0-hpbdmac: ch8 write 512 bytes, DSAR 0xa99c1000, left 0, crc32 0x00000008, head 00",
    ])
    check("only SD reads become channel lines", decode_reads(log),
          ["port 0 CMD17+data arg 0x00000002 512 bytes crc32 0x00000007\n"])

    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "serial.log"), "wb") as fh:
            fh.write(raw)
        with open(os.path.join(d, "qemu.log"), "w") as fh:
            fh.write(log)
        with open(os.path.join(d, "vram.bin"), "wb") as fh:
            fh.write(b"VRAM")
        full_n, cut_n, reads_n, digest = write_channels(d, "MSG_PROCESS_NAVI_MAP_CC", 2,
                                                        "0x1234\n", None)
        check("serial-full keeps the tail", full_n, len(raw))
        check("compared serial is cut", cut_n,
              len(b"one\n" + mark + b" first\nmid\n" + mark + b" second\n"))
        check("dbgmsg is LF-normalised",
              open(os.path.join(d, "dbgmsg.log"), "rb").read(),
              b"one\n" + mark + b" first\nmid\n" + mark + b" second\n")
        check("one SD read line", reads_n, 1)
        check("VRAM hash", digest, hashlib.sha256(b"VRAM").hexdigest())
        check("vram.sha256 names the milestone",
              open(os.path.join(d, "vram.sha256")).read().strip().endswith("MSG_PROCESS_NAVI_MAP_CC#2"), True)
    print("selftest: %d failed" % len(fails))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true", help="offline test of the channel builder")
    ap.add_argument("outdir", nargs="?", help="run directory to write (must be fresh)")
    ap.add_argument("--qemu", default="qemu-system-sh4")
    ap.add_argument("--image", default="archive/head256.img")
    ap.add_argument("--card", default="archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img")
    ap.add_argument("--ipl-patch", help="file from tools/ze0_ipl.py patch")
    ap.add_argument("--marker", default="MSG_PROCESS_NAVI_MAP_CC")
    ap.add_argument("--count", type=int, default=2)
    ap.add_argument("--maxwall", type=float, default=420.0)
    ap.add_argument("--msec-target", type=int, default=0,
                    help="also wait for CurMSec >= N (a true fixed guest-time capture)")
    ap.add_argument("--size-gib", type=int, default=8)
    ap.add_argument("--kernel-off", type=lambda s: int(s, 0), default=0x3E00200)
    ap.add_argument("--app-off", type=lambda s: int(s, 0), default=0x200200)
    ap.add_argument("--dbgmsg", type=lambda s: int(s, 0), default=0x880404F4)
    ap.add_argument("--verinf", default="QSD-302-100")
    ap.add_argument("--mapdb", default="16-16")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.outdir or not args.ipl_patch:
        ap.error("OUTDIR and --ipl-patch are required for a live capture")
    if args.count < 1:
        ap.error("--count must be >= 1")
    return capture(args)


if __name__ == "__main__":
    sys.exit(main())
