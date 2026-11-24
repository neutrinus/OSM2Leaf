#!/usr/bin/env python3
"""Boot-time budget from a QEMU ``-M ze0`` run.out + sampled TSV (TODO M8.H25).

The kernel debug text that ``run.sh`` prints under ``-nographic`` has no
per-line timestamp.  This tool attributes host and guest time to boot phases
by joining two streams that were captured together:

  * ``run.out`` -- stdout/stderr of ``run.sh``, containing the kernel debug
    text; a phase is a stable marker string (never a line number, H71);
  * a TSV sampled during the boot with columns ``t_host bytes cur_raw``,
    where ``t_host`` is ``date +%s.%N``, ``bytes`` is ``wc -c < run.out`` and
    ``cur_raw`` is the HMP reply to ``xp/4xb 0x09e41888`` (CurMSec, SH-4 LE).

For each marker its byte offset in ``run.out`` is interpolated against the
TSV ``bytes`` column, giving host seconds and CurMSec milliseconds at that
marker.  Phase cost is the difference between consecutive markers.

Usage:
  ze0_bootbudget.py table TSV RUN_OUT
  ze0_bootbudget.py --selftest

Method and results: docs/experiments/EXP-2026-11-24-M8.H25-boot-budget.md
"""

import argparse
import os
import re
import sys

MARKERS = [
    ("kernel", re.compile(rb"Windows CE Kernel for Hitachi SH")),
    ("display", re.compile(rb"Display: HWR built")),
    ("sd_start", re.compile(rb"ActivateSDCardDriver\([^\r\n]*\) Start\.")),
    ("sd_end", re.compile(rb"ActivateSDCardDriver\([^\r\n]*\) End\(OK!!!!\)")),
    ("store_ready", re.compile(rb"Store Mgr Ready! \[DSK1:\]")),
    ("app_create", re.compile(rb"AppLch >> Process Create!!! -> \\windows")),
    ("wait_timeout", re.compile(rb"ACM::WaitModule Timeout")),
    ("idle", re.compile(rb"AppLch >> Finish Launch Threads!")),
]


def load_tsv(path):
    """[(host_epoch_s, bytes, cur_ms)] from the sampled TSV, sorted by bytes."""
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) < 2 or parts[0] == "t_host":
                continue
            try:
                t = float(parts[0])
                n = int(parts[1])
            except ValueError:
                continue
            ms = None
            if len(parts) >= 3:
                found = re.search(r"09e41888:\s*((?:0x[0-9a-fA-F]{2}\s*){4})", line)
                if found:
                    hexes = re.findall(r"0x([0-9a-fA-F]{2})", found.group(1))
                    if len(hexes) == 4:
                        ms = int.from_bytes(bytes(int(h, 16) for h in hexes), "little")
            rows.append((t, n, ms))
    return rows


def interpolate(rows, field, target):
    """Linearly interpolate column ``field`` (1=bytes, 2=cur_ms) at bytes=target."""
    pts = [(r[1], r[field]) for r in rows if r[field] is not None]
    if not pts:
        return None
    pts.sort()
    if target <= pts[0][0]:
        return float(pts[0][1])
    if target >= pts[-1][0]:
        return float(pts[-1][1])
    for (b0, v0), (b1, v1) in zip(pts, pts[1:]):
        if b0 <= target <= b1 and b1 > b0:
            return v0 + (v1 - v0) * (target - b0) / (b1 - b0)
    return float(pts[-1][1])


def read_log(path):
    with open(path, "rb") as handle:
        return handle.read()


def table(tsv_path, log_path):
    rows = load_tsv(tsv_path)
    data = read_log(log_path)
    first_t = rows[0][0]
    found = []
    for name, rx in MARKERS:
        match = rx.search(data)
        if match is None:
            found.append((name, None, None, None))
            continue
        offset = match.start()
        t = interpolate(rows, 0, offset)
        ms = interpolate(rows, 2, offset)
        found.append((name, t - first_t if t is not None else None, ms, offset))
    # Present markers in the order they occur in the log, so phase deltas
    # (differences between consecutive rows) are always non-negative.
    found_with_offset = [f for f in found if f[3] is not None]
    found_with_offset.sort(key=lambda f: f[3])
    found = found_with_offset + [f for f in found if f[3] is None]
    print("marker       host_s     guest_ms   byte_offset")
    print("NOTE: guest_ms is CurMSec at the marker; under -icount it is a")
    print("      wall sample affected by host load (C-7536), not phase guest time.")
    prev_t = 0.0
    prev_ms = 0.0
    for name, t, ms, off in found:
        ht = "MISSING" if t is None else "%.2f" % t
        gm = "MISSING" if ms is None else "%.0f" % ms
        ph = "" if t is None else "  (+%.2f s host, +%.0f ms guest)" % (t - prev_t, (ms or 0) - prev_ms)
        print("%-12s %-9s %-10s %s%s" % (name, ht, gm, off if off is not None else "MISSING", ph))
        if t is not None:
            prev_t = t
        if ms is not None:
            prev_ms = ms
    return found


def selftest():
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))

    data = (b"prefix\r\nWindows CE Kernel for Hitachi SH\r\n"
            b"Display: HWR built\r\nACM::WaitModule Timeout ID[81]\r\n")
    rows = [(100.0, 0, None), (101.0, 10, 0), (102.0, 20, 1000),
            (103.0, len(data), 2000), (104.0, len(data) + 10, 3000)]
    check("interp bytes", interpolate(rows, 0, 15), 101.5)
    check("interp cur", interpolate(rows, 2, 15), 500.0)
    check("kernel offset", data.find(b"Windows CE Kernel"), 8)
    check("display regex", MARKERS[1][1].search(data) is not None, True)
    check("LE decode", int.from_bytes(bytes([0x71, 0x90, 0x01, 0x00]), "little"), 102513)
    check("negative marker", MARKERS[7][1].search(data) is None, True)
    check("LE decode", int.from_bytes(bytes([0x71, 0x90, 0x01, 0x00]), "little"), 102513)
    # D10: deltas must follow log order, never MARKERS declaration order.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="ze0_bootbudget.") as tmp:
        tsv = os.path.join(tmp, "tsv")
        log = os.path.join(tmp, "out")
        with open(tsv, "w") as fh:
            fh.write("t_host bytes cur_raw\n")
            for i in range(6):
                fh.write("100.%d %d 09e41888: %s\n" % (i, i * 100,
                         " ".join("0x%02x" % b for b in (i * 100).to_bytes(4, "little"))))
        with open(log, "wb") as fh:
            fh.write(b"Windows CE Kernel\r\nACM::WaitModule Timeout\r\nDisplay: HWR built\r\n")
        rows = table(tsv, log)
    offsets = [r[3] for r in rows if r[3] is not None]
    check("markers in log order", offsets, sorted(offsets))
    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    t = sub.add_parser("table")
    t.add_argument("tsv")
    t.add_argument("run_out")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "table":
        table(args.tsv, args.run_out)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
