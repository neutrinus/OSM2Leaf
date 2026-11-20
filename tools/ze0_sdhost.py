#!/usr/bin/env python3
"""SD host bring-up evidence for the QEMU ``ze0`` machine (TODO M8.C10, EU2011).

Sub-commands:

  inttable IMG [--start VA] [--image-start 0x3e00200]
        Print the OAL interrupt table of ``nk.exe``: 16-byte rows
        ``{INTEVT, ISR, IntrPrio, SYSINTR}`` from ``--start`` (default
        ``0x88005bc8``, EU2011) until a row's ISR leaves ``nk.exe`` code
        (``0x88000000..0x88100000``).  ``--find-sysintr N`` marks the rows
        whose SYSINTR is N.  This is how the SD host ports get their INTEVT
        (``0xae0``/``0xb00``) and SYSINTR (``0x1f``/``0x20``).

  sdtrace LOG
        Decode a QEMU ``-d unimp`` log of ``-M ze0,sdhi-trace=on``: every
        write of SD_CMD (``+0x00``) per port becomes ``CMDn``/``ACMDn``
        (bit 6 = application command), with ``+data`` when bits 11..12 are
        set; repeats are collapsed (``x67``).  Also counts DMA-mode requests
        (``CC_EXT_MODE`` bit 1) and commands that got no response.

  serial LOG
        Count the SD milestones in a kernel debug log (``run.sh --serial``
        with ``dbgmsg``, M8.B6): ``SD Check Error``, ``ActivateSDCardDriver
        ... Start``/``End(OK``/``End(NG``, ``EventID = 2 Timeout``,
        ``EVT_SD_SYS_MOUNT``, ``ACM::WaitModule Timeout ID[37]``.

Usage:
  ze0_sdhost.py inttable archive/head256.img [--find-sysintr 0x1f]
  ze0_sdhost.py sdtrace qemu-unimp.log
  ze0_sdhost.py serial serial.log
  ze0_sdhost.py --selftest

Method and results: docs/experiments/EXP-2026-11-20-M8.C10-sd-host.md
"""

import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

INTTABLE_EU2011 = 0x88005BC8
NK_CODE = (0x88000000, 0x88100000)

MARKERS = [
    ("sd_check_error", "SD Check Error"),
    ("activate_start", "ActivateSDCardDriver(lpszDevKey=Drivers\\SD\\Card) Start"),
    ("activate_ok", "ActivateSDCardDriver(lpszDevKey=Drivers\\SD\\Card) End(OK"),
    ("activate_ng", "ActivateSDCardDriver(lpszDevKey=Drivers\\SD\\Card) End(NG"),
    ("event2_timeout", "EventID = 2 Timeout"),
    ("sys_mount_event", "Stub_SetEvent[EVT_SD_SYS_MOUNT]"),
    ("wait37_timeout", "ACM::WaitModule Timeout ID[37]"),
]

CMD_RE = re.compile(r"ze0-sdhi(\d): wr\d+ \+0x00 = 0x([0-9a-f]+)")
DMA_RE = re.compile(r"ze0-sdhi(\d): DMA mode requested")
NORSP_RE = re.compile(r"ze0-sdhi(\d): CMD(\d+) arg 0x[0-9a-f]+: no response")


def table_rows(read_u32, start, limit=256):
    rows = []
    for i in range(limit):
        va = start + 16 * i
        ev, isr, prio, sysintr = (read_u32(va + 4 * k) for k in range(4))
        if not NK_CODE[0] <= isr < NK_CODE[1]:
            break
        rows.append((va, ev, isr, prio, sysintr))
    return rows


def cmd_name(v):
    idx = v & 0x3F
    name = ("ACMD%d" if v & 0x40 else "CMD%d") % idx
    if v & 0x1800:
        name += "+data"
    return name


def decode_trace(text):
    seq = {}
    dma = {}
    norsp = {}
    for line in text.splitlines():
        m = CMD_RE.search(line)
        if m:
            port = int(m.group(1))
            name = cmd_name(int(m.group(2), 16))
            s = seq.setdefault(port, [])
            if s and s[-1][0] == name:
                s[-1][1] += 1
            else:
                s.append([name, 1])
            continue
        m = DMA_RE.search(line)
        if m:
            dma[int(m.group(1))] = dma.get(int(m.group(1)), 0) + 1
            continue
        m = NORSP_RE.search(line)
        if m:
            norsp[int(m.group(1))] = norsp.get(int(m.group(1)), 0) + 1
    return seq, dma, norsp


def fmt_seq(s):
    return " ".join(n if c == 1 else "%sx%d" % (n, c) for n, c in s)


def count_markers(text):
    return {key: text.count(needle) for key, needle in MARKERS}


def cmd_inttable(args):
    import cerom
    with open(args.image, "rb") as fh:
        data = fh.read()
    rom = cerom.CERom(data, args.image_start)

    def read_u32(va):
        off = rom.va2file(va)
        return struct.unpack_from("<I", data, off)[0]

    rows = table_rows(read_u32, args.start)
    print("rows %d from 0x%08x (16 B: INTEVT, ISR, IntrPrio, SYSINTR)" % (len(rows), args.start))
    for va, ev, isr, prio, si in rows:
        mark = "  <-" if args.find_sysintr is not None and si == args.find_sysintr else ""
        print("0x%08x  INTEVT 0x%03x  ISR 0x%08x  prio %2d  SYSINTR 0x%02x%s" % (va, ev, isr, prio, si, mark))
    return 0


def cmd_sdtrace(args):
    with open(args.log, encoding="utf-8", errors="replace") as fh:
        seq, dma, norsp = decode_trace(fh.read())
    for port in sorted(set(seq) | set(dma) | set(norsp)):
        n = sum(c for _, c in seq.get(port, []))
        print("port %d: %d commands, DMA-mode requests %d, no-response %d"
              % (port, n, dma.get(port, 0), norsp.get(port, 0)))
        print("  " + fmt_seq(seq.get(port, [])))
    if not seq:
        print("no SD_CMD writes (sdhi-trace off, or the driver never issued a command)")
    return 0


def cmd_serial(args):
    with open(args.log, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    lines = [ln for ln in text.splitlines() if ln.strip()]
    print("lines %d" % len(lines))
    for key, n in count_markers(text).items():
        print("  %-16s %d" % (key, n))
    return 0


def selftest():
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))

    words = {}
    base = 0x88001000
    for i, row in enumerate([(0xAE0, 0x8803FCDC, 9, 0x1F), (0xB00, 0x8803FD40, 9, 0x20),
                             (0x123, 0x12345678, 0, 0)]):
        for k, v in enumerate(row):
            words[base + 16 * i + 4 * k] = v
    rows = table_rows(lambda va: words.get(va, 0), base)
    check("table stops at a non-nk ISR (negative)", len(rows), 2)
    check("table row", rows[0][1:], (0xAE0, 0x8803FCDC, 9, 0x1F))
    check("empty table", table_rows(lambda va: 0, base), [])

    check("cmd name", cmd_name(0x0069), "ACMD41")
    check("cmd data", cmd_name(0x184D), "ACMD13+data")
    check("plain cmd", cmd_name(0x0011), "CMD17")
    log = "\n".join([
        "ze0-sdhi0: wr16 +0x00 = 0x0000",
        "ze0-sdhi0: wr16 +0x00 = 0x000d",
        "ze0-sdhi0: wr16 +0x00 = 0x000d",
        "ze0-sdhi0: wr16 +0x04 = 0x0000",
        "ze0-sdhi0: DMA mode requested (CC_EXT_MODE 0x0002), not modelled",
        "ze0-sdhi1: CMD8 arg 0x000001aa: no response",
        "ze0-sdhi1: wr16 +0x00 = 0x0008",
    ])
    seq, dma, norsp = decode_trace(log)
    check("trace port 0", fmt_seq(seq[0]), "CMD0 CMD13x2")
    check("trace port 1", fmt_seq(seq[1]), "CMD8")
    check("dma count", dma, {0: 1})
    check("no-response count", norsp, {1: 1})
    check("argument write is not a command", sum(c for _, c in seq[0]), 3)

    m = count_markers("AppLch > SD Check Error\n###SDHC(Port=0)-->ActivateSDCardDriver"
                      "(lpszDevKey=Drivers\\SD\\Card) End(NG??]\n")
    check("marker check error", m["sd_check_error"], 1)
    check("marker NG", (m["activate_ng"], m["activate_ok"]), (1, 0))

    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def _int(s):
    return int(s, 0)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    t = sub.add_parser("inttable")
    t.add_argument("image")
    t.add_argument("--image-start", type=_int, default=0x3E00200)
    t.add_argument("--start", type=_int, default=INTTABLE_EU2011)
    t.add_argument("--find-sysintr", type=_int)
    s = sub.add_parser("sdtrace")
    s.add_argument("log")
    r = sub.add_parser("serial")
    r.add_argument("log")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "inttable":
        return cmd_inttable(args)
    if args.cmd == "sdtrace":
        return cmd_sdtrace(args)
    if args.cmd == "serial":
        return cmd_serial(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
