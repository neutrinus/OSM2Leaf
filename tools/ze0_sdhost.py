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

  dmatrace LOG [--card CARD.img]
        Decode the HPB-DMAC transfers of a ``-d unimp`` log of ``-M
        ze0,sdhi-trace=on,hpbdmac-trace=on`` (M8.C1b): every ``ze0-hpbdmac:
        chN read|write`` line is paired with the SD command and argument
        before it.  With ``--card`` each CMD17/CMD18 read is compared with
        the card image: CRC-32 of ``bytes`` at block ``arg`` (SDHC block
        addressing) must equal the CRC-32 the model logged.

  serial LOG
        Count the SD milestones in a kernel debug log (``run.sh --serial``
        with ``dbgmsg``, M8.B6): ``SD Check Error``, ``ActivateSDCardDriver
        ... Start``/``End(OK``/``End(NG``, ``EventID = 2 Timeout``,
        ``EVT_SD_SYS_MOUNT``, ``ACM::WaitModule Timeout ID[37]``, and the
        launcher lines after the unlock (``SD Card Security Unlocked!``,
        ``Mount System SD Proc Start``, the lock/no-security error) and
        the F3 lines (``Store Mgr Ready! [DSK1:]``, ``Mount Time of
        PartNN``, ``AppLch >> Error Proc<``, ``FailSafe.exe Start``).

Usage:
  ze0_sdhost.py inttable archive/head256.img [--find-sysintr 0x1f]
  ze0_sdhost.py sdtrace qemu-unimp.log
  ze0_sdhost.py dmatrace qemu-unimp.log --card CARD.img
  ze0_sdhost.py serial serial.log
  ze0_sdhost.py --selftest

Method and results: docs/experiments/EXP-2026-11-20-M8.C10-sd-host.md and
docs/experiments/EXP-2026-11-21-M8.C1b-hpb-dmac-model.md
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
    ("lock_unlock_call", "SDHC_Lock_Unlock_Card() byFlag["),
    ("lock_unlock_err", "SDHC_Lock_Unlock_Card() Err"),
    ("security_unlocked", "SD Card Security Unlocked!"),
    ("security_error", "SD Card is [Security lock state] or [no Security]"),
    ("mount_sd_start", "Mount System SD Proc Start"),
    ("store_ready", "Store Mgr Ready! [DSK1:]"),
    ("part_mounted", "Mount Time of Part"),
    ("applch_error", "AppLch >> Error Proc<"),
    ("failsafe_start", "*** FailSafe.exe Start ***"),
    ("verinf_mismatch", "VerInf:"),
    ("mapdb_out_of_range", "MapDBVer : "),
    ("launch_not_create", "Launch Process Not Create!!!"),
]

CMD_RE = re.compile(r"ze0-sdhi(\d): wr\d+ \+0x00 = 0x([0-9a-f]+)")
DMA_RE = re.compile(r"ze0-sdhi(\d): DMA mode requested")
ARG_RE = re.compile(r"ze0-sdhi(\d): wr\d+ \+0x0([46]) = 0x([0-9a-f]+)")
XFER_RE = re.compile(r"ze0-hpbdmac: ch(\d+) (read|write) (\d+) bytes, D[DS]AR 0x([0-9a-f]+), "
                     r"left (\d+), crc32 0x([0-9a-f]+)")
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


def decode_dma(text):
    """[(port, cmd name, arg, direction, bytes, guest address, left, crc32)]"""
    arg = {}
    last = {}
    out = []
    for line in text.splitlines():
        m = ARG_RE.search(line)
        if m:
            port, reg, v = int(m.group(1)), m.group(2), int(m.group(3), 16)
            a = arg.get(port, 0)
            arg[port] = (a & 0xFFFF0000) | v if reg == "4" else (a & 0xFFFF) | (v << 16)
            continue
        m = CMD_RE.search(line)
        if m:
            port = int(m.group(1))
            last[port] = (cmd_name(int(m.group(2), 16)), arg.get(port, 0))
            continue
        m = XFER_RE.search(line)
        if m:
            port = int(m.group(1)) - 8
            name, a = last.get(port, ("?", 0))
            out.append((port, name, a, m.group(2), int(m.group(3)), int(m.group(4), 16),
                        int(m.group(5)), int(m.group(6), 16)))
    return out


def check_card(xfers, read_at):
    """Compare CMD17/CMD18 reads with the card: (checked, mismatches)."""
    import zlib
    checked = bad = 0
    for port, name, a, direction, nbytes, _addr, _left, crc in xfers:
        if direction != "read" or name not in ("CMD17+data", "CMD18+data"):
            continue
        checked += 1
        if zlib.crc32(read_at(a * 512, nbytes)) & 0xFFFFFFFF != crc:
            bad += 1
    return checked, bad


def cmd_dmatrace(args):
    with open(args.log, encoding="utf-8", errors="replace") as fh:
        xfers = decode_dma(fh.read())
    kinds = {}
    for port, name, a, direction, nbytes, addr, left, crc in xfers:
        k = kinds.setdefault((port, name, direction), [0, 0])
        k[0] += 1
        k[1] += nbytes
    print("transfers %d, bytes %d, incomplete %d"
          % (len(xfers), sum(x[4] for x in xfers), sum(1 for x in xfers if x[6])))
    for (port, name, direction), (n, b) in sorted(kinds.items()):
        print("  port %d %-12s %-5s x%-4d %d bytes" % (port, name, direction, n, b))
    if args.list:
        for port, name, a, direction, nbytes, addr, left, crc in xfers:
            print("  port %d %s arg 0x%08x %s %d bytes -> 0x%08x crc32 0x%08x"
                  % (port, name, a, direction, nbytes, addr, crc))
    if args.card:
        with open(args.card, "rb") as fh:
            def read_at(off, n):
                fh.seek(off)
                return fh.read(n)
            checked, bad = check_card(xfers, read_at)
        print("card check: %d block reads compared, %d mismatch(es)" % (checked, bad))
        return 1 if bad or not checked else 0
    return 0


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

    dlog = "\n".join([
        "ze0-sdhi0: wr16 +0x04 = 0x0002",
        "ze0-sdhi0: wr16 +0x06 = 0x0000",
        "ze0-sdhi0: wr16 +0x00 = 0x1811",
        "ze0-hpbdmac: ch8 read 512 bytes, DDAR 0xa99c1000, left 0, crc32 0x%08x, head 00"
        % __import__("zlib").crc32(bytes([7]) * 512),
        "ze0-sdhi0: wr16 +0x00 = 0x184d",
        "ze0-hpbdmac: ch8 read 64 bytes, DDAR 0xa99c1000, left 0, crc32 0x00000001, head 00",
    ])
    xf = decode_dma(dlog)
    check("dma transfers", [(x[1], x[2], x[4]) for x in xf],
          [("CMD17+data", 2, 512), ("ACMD13+data", 2, 64)])
    card = bytes(1024) + bytes([7]) * 512
    check("card check equal", check_card(xf, lambda o, n: card[o:o + n]), (1, 0))
    check("card check wrong block (negative)",
          check_card(xf, lambda o, n: card[o - 512:o - 512 + n]), (1, 1))
    check("non-block reads are not compared", check_card(xf[1:], lambda o, n: b""), (0, 0))

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
    d = sub.add_parser("dmatrace")
    d.add_argument("log")
    d.add_argument("--card")
    d.add_argument("--list", action="store_true")
    r = sub.add_parser("serial")
    r.add_argument("log")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "inttable":
        return cmd_inttable(args)
    if args.cmd == "sdtrace":
        return cmd_sdtrace(args)
    if args.cmd == "dmatrace":
        return cmd_dmatrace(args)
    if args.cmd == "serial":
        return cmd_serial(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
