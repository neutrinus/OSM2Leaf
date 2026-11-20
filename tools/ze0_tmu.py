#!/usr/bin/env python3
"""Watch the EU2011 kernel's CurMSec against the host clock under QEMU ``-M ze0`` (TODO M8.B2).

EU2011 ``nk.exe`` runs a variable-tick timer on TMU0: the OAL timer
descriptor (``0x88004cf8``) gives the count rate as 2 625 000 Hz, the setup
``fn 0x8803d060`` stores counts/ms (``0x89e6cad8`` = 0xa41) and the maximum
period in ms (``0x89e6cac4``), and the TMU0 ISR ``fn 0x8803cb34`` writes
``CurMSec`` (``0x89e41888``) from the programmed target ``0x89e6cae4``.
When nothing is scheduled the kernel programs the maximum period, so
``CurMSec`` jumps once per period; if the TMU's input clock matches the
OAL's assumption, the jump comes after as many host seconds as ``CurMSec``
moves in thousands.

Sub-commands:

  sample -o CSV --duration S [--interval S] -- QEMU-ARGV...
        Start QEMU (its argv after ``--``) with an HMP monitor on a unix
        socket in a temp dir, and every interval read ``CurMSec``, TCNT0,
        TCOR0 and counts/ms through ``xp``.  Writes ``t,curmsec,tcnt0,
        tcor0,cpms`` rows (t = host seconds since QEMU was started), then
        kills QEMU.

  rate CSV
        Find each ``CurMSec`` jump: the plateau it left (value, first time
        seen) and the new value.  Prints the ratio
        (CurMSec delta / 1000) / (host seconds between the plateau start
        and the jump), with its bound from the sample interval.  A ratio of
        1 means CurMSec follows real time; no jump means it did not
        advance.

Usage:
  ze0_tmu.py sample -o run.csv --duration 900 --interval 2 -- qemu-system-sh4 -M ze0 -kernel IMG -nographic -serial null
  ze0_tmu.py rate run.csv
  ze0_tmu.py --selftest

Method and results: docs/experiments/EXP-2026-11-20-M8.B2-ze0-tmu.md
"""

import argparse
import csv
import os
import re
import socket
import subprocess
import sys
import tempfile
import time

CURMSEC_EU2011 = 0x89E41888
CPMS_EU2011 = 0x89E6CAD8
TMU0_TCOR = 0xFFD80008
TMU0_TCNT = 0xFFD8000C
FIELDS = ("t", "curmsec", "tcnt0", "tcor0", "cpms")


def phys(va):
    return va & 0x1FFFFFFF if va < 0xE0000000 else va


class Hmp:
    def __init__(self, path, timeout=5.0):
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.s.settimeout(timeout)
        self.s.connect(path)
        self._drain()

    def _drain(self):
        buf = b""
        while not buf.endswith(b"(qemu) "):
            chunk = self.s.recv(65536)
            if not chunk:
                break
            buf += chunk
        return buf.decode("latin1")

    def word(self, addr):
        self.s.sendall(b"xp /1wx 0x%x\n" % addr)
        text = self._drain()
        m = re.search(r"%016x: (0x[0-9a-f]{8})" % addr, text)
        return int(m.group(1), 16) if m else None

    def close(self):
        try:
            self.s.sendall(b"q\n")
        except OSError:
            pass
        self.s.close()


def cmd_sample(args):
    if not args.qemu_argv:
        print("sample: give the QEMU argv after --")
        return 2
    tmp = tempfile.mkdtemp(prefix="ze0_tmu.")
    sock = os.path.join(tmp, "hmp.sock")
    argv = list(args.qemu_argv) + ["-monitor", "unix:%s,server,nowait" % sock]
    t0 = time.monotonic()
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL)
    rows = []
    try:
        hmp = None
        while hmp is None:
            if proc.poll() is not None:
                print("sample: QEMU exited with %s before the monitor came up" % proc.returncode)
                return 1
            try:
                hmp = Hmp(sock)
            except OSError:
                time.sleep(0.1)
        next_t = 0.0
        while True:
            now = time.monotonic() - t0
            if now > args.duration or proc.poll() is not None:
                break
            if now >= next_t:
                vals = [hmp.word(phys(CURMSEC_EU2011)), hmp.word(TMU0_TCNT),
                        hmp.word(TMU0_TCOR), hmp.word(phys(CPMS_EU2011))]
                rows.append([round(now, 3)] + vals)
                next_t += args.interval
            time.sleep(0.05)
        hmp.close()
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(FIELDS)
        for r in rows:
            w.writerow([r[0]] + ["" if v is None else "0x%08x" % v for v in r[1:]])
    print("sample: %d rows over %.1f s -> %s" % (len(rows), rows[-1][0] if rows else 0.0, args.out))
    return 0


def load_rows(path):
    out = []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            if r["curmsec"]:
                out.append((float(r["t"]), int(r["curmsec"], 16)))
    return out


def load_tcnt(path):
    out = []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            if r["tcnt0"] and r["tcor0"]:
                out.append((float(r["t"]), int(r["tcnt0"], 16), int(r["tcor0"], 16)))
    return out


def tcnt_rate(samples):
    """Counts per host second over the longest run without a reload, or None."""
    best = None
    i = 0
    while i < len(samples):
        j = i
        while j + 1 < len(samples) and samples[j + 1][2] == samples[i][2] \
                and samples[j + 1][1] < samples[j][1]:
            j += 1
        if j > i and (best is None or samples[j][0] - samples[i][0] > best[0]):
            best = (samples[j][0] - samples[i][0],
                    (samples[i][1] - samples[j][1]) / (samples[j][0] - samples[i][0]))
        i = j + 1
    return None if best is None else best[1]


def jumps(rows, interval):
    """[(plateau value, plateau start t, jump t, new value, ratio, lo, hi)]."""
    res = []
    if not rows:
        return res
    start_t, val = rows[0]
    prev_t = rows[0][0]
    for t, v in rows[1:]:
        if v != val:
            dt = t - start_t
            dms = (v - val) & 0xFFFFFFFF
            ratio = (dms / 1000.0) / dt if dt > 0 else float("inf")
            # the plateau may have begun up to one interval before start_t, the
            # jump up to one interval before t
            hi = (dms / 1000.0) / max(dt - interval, 1e-9)
            lo = (dms / 1000.0) / (dt + interval)
            res.append((val, start_t, t, v, ratio, lo, hi))
            start_t, val = t, v
        prev_t = t
    del prev_t
    return res


def cmd_rate(args):
    rows = load_rows(args.csv)
    if not rows:
        print("rate: no samples")
        return 1
    interval = args.interval
    if interval is None:
        ts = [t for t, _v in rows]
        interval = max(b - a for a, b in zip(ts, ts[1:])) if len(ts) > 1 else 0.0
    print("rate: %d samples, %.1f..%.1f s, interval <= %.2f s, CurMSec first 0x%x last 0x%x"
          % (len(rows), rows[0][0], rows[-1][0], interval, rows[0][1], rows[-1][1]))
    hz = tcnt_rate(load_tcnt(args.csv))
    if hz is not None:
        print("TMU0 TCNT0 rate: %.0f counts per host second (OAL assumes 2625000)" % hz)
    js = jumps(rows, interval)
    big = [j for j in js if ((j[3] - j[0]) & 0xFFFFFFFF) >= args.min_jump]
    for val, st, jt, new, ratio, lo, hi in js:
        print("  CurMSec 0x%x (from %.1f s) -> 0x%x at %.1f s: +%d ms in %.1f s, ratio %.4f [%.4f..%.4f]%s"
              % (val, st, new, jt, (new - val) & 0xFFFFFFFF, jt - st, ratio, lo, hi,
                 "" if ((new - val) & 0xFFFFFFFF) >= args.min_jump else "  (small, ignored)"))
    if not big:
        print("rate: CurMSec made no jump >= %d ms: it did not advance" % args.min_jump)
        return 3
    return 0


def selftest():
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))

    rows = [(0.5, 0)] + [(float(t), 0x110) for t in range(2, 820, 2)] + [(820.0, 0x110 + 818088)]
    js = jumps(rows, 2.0)
    check("two jumps", len(js), 2)
    val, st, jt, new, ratio, lo, hi = js[1]
    check("plateau start", (val, st), (0x110, 2.0))
    check("ratio ~1", round(ratio, 3), round(818.088 / 818.0, 3))
    check("bound brackets 1", lo <= 1.0 <= hi, True)
    fast = [(float(t), 0x110) for t in range(2, 574, 2)] + [(574.0, 0x110 + 818088)]
    r2 = jumps(fast, 2.0)[0]
    check("60 MHz-like run is fast", r2[5] > 1.3, True)
    check("flat run has no jump", jumps([(float(t), 0x110) for t in range(0, 100, 2)], 2.0), [])
    check("tcnt rate", round(tcnt_rate([(0.0, 1000000, 9), (2.0, 750000, 9), (4.0, 500000, 9),
                                        (5.0, 999999, 9)])), 125000)
    check("phys of P1", phys(CURMSEC_EU2011), 0x09E41888)
    check("phys of P4", phys(TMU0_TCNT), TMU0_TCNT)
    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    qemu_argv = []
    if "--" in argv:
        i = argv.index("--")
        argv, qemu_argv = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("sample")
    s.add_argument("-o", "--out", required=True)
    s.add_argument("--duration", type=float, required=True)
    s.add_argument("--interval", type=float, default=2.0)
    r = sub.add_parser("rate")
    r.add_argument("csv")
    r.add_argument("--interval", type=float)
    r.add_argument("--min-jump", type=int, default=1000)
    args = ap.parse_args(argv)
    args.qemu_argv = qemu_argv
    if args.selftest:
        return selftest()
    if args.cmd == "sample":
        return cmd_sample(args)
    if args.cmd == "rate":
        return cmd_rate(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
