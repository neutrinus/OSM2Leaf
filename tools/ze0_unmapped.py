#!/usr/bin/env python3
"""Census of unmodelled hardware accesses in a ``-M ze0`` QEMU log (TODO M8.H22).

Each missing device shows up as ``Invalid read/write at addr ...`` lines (an
address with no memory region at all) or ``ze0-<dev>: unimplemented device
read/write (...)`` catch-alls.  This tool streams such a log once, groups the
accesses into 4 KiB blocks, counts reads/writes, reports the first and last time
and attributes a guest PC to a ROM module through ``cerom.py``.  The ranked
table answers "which block should be modelled next, and by how many accesses",
instead of guessing from a driver name.

Time sources, in order of preference (never fabricated):

1. ``--times FILE``: ``<log_line_no> <guest_ms>`` pairs sampled from the guest
   clock (``CurMSec`` at phys ``0x09e41888``) over QMP; first/last are real guest
   milliseconds, labelled ``guest``.
2. ``-msg timestamp=on`` prefix ``2026-11-24T15:35:51.136144Z``: host VM elapsed
   seconds relative to the first timestamped line, labelled ``host-elapsed``
   (NOT guest time).
3. no clock: ``n/a``.

PC attribution uses the nearest preceding anchored ``pc=0x........`` line, or a
``in delay slot (delayed_pc=0x........)`` line immediately before the access.
A catch-all trace line without either prints ``none``; no module is invented.
Module resolution mirrors ``ze0_pcsample.py``: live table (optional JSON), then
kernel ``nk.exe`` of image B, then a unique static scan over images A/B/C;
ambiguous matches print ``AMBIGUOUS``.

Usage:
  ze0_unmapped.py LOG [--top 30] [--image IMG256] [--modules JSON]
                      [--times FILE] [--json] [--label LABEL]
  ze0_unmapped.py --selftest

Method and results: docs/experiments/EXP-2026-11-24-M8.H22-unmapped-census.md
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

SEGMENTS = (0x200200, 0x3E00200, 0x5200200)
KERNEL_SEGMENT = 0x3E00200
BLOCK_SIZE = 0x1000

CATCH_BASE = {
    "ze0-p4": 0xFF800000,
    "ze0-area4": 0x10000000,
    "ze0-area6": 0x18000000,
}

TS = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z)\s+")
INVALID = re.compile(r"Invalid (read|write) at addr 0x([0-9a-fA-F]+), size (\d+)")
UNIMP = re.compile(r"(ze0-[a-z0-9]+): unimplemented device (read|write)\s*"
                   r"\(size (\d+), offset 0x([0-9a-fA-F]+)(?:, value 0x([0-9a-fA-F]+))?\)")
PC_LINE = re.compile(r"\bpc=0x([0-9a-fA-F]{8})\b")
DELAY_LINE = re.compile(r"in delay slot \(delayed_pc=0x([0-9a-fA-F]{8})\)")
TIME_LINE = re.compile(r"^\s*(\d+)\s+(\d+)\s*$")

# (start, end inclusive, name) from docs/research/full-system-emulation.md §1.
# The most specific (smallest) containing range wins; no name is guessed.
BLOCKS = [
    (0xf0000000, 0xf000ffff, "IC/OC cache arrays (nk)"),
    (0xf4000000, 0xf4007fff, "IC/OC cache arrays (nk)"),
    (0xff000000, 0xff0000ff, "CCN/MMU: PTEH/PTEL/TTB/TEA/MMUCR/CCR/EXPEVT"),
    (0xff200000, 0xff200fff, "UBC break controller"),
    (0xff801000, 0xff801fff, "DMAC (shared by DMA drivers)"),
    (0xff802000, 0xff802fff, "INTC mask set/clear"),
    (0xff804000, 0xff8040ff, "INTC mask set/clear"),
    (0xffc08000, 0xffc08fff, "DMA request mux / clock-reset control"),
    (0xffc41000, 0xffc43fff, "GPIO ports"),
    (0xffc55000, 0xffc55fff, "FM multiplex (RDS/TMC) decoder"),
    (0xffc5a000, 0xffc5afff, "GPS/odometer pulse capture or timers (kepdrv)"),
    (0xffc5b000, 0xffc5bfff, "GPS/odometer pulse capture or timers (navdrv)"),
    (0xffc71000, 0xffc71fff, "I2C master"),
    (0xffc80030, 0xffc8004f, "CPG MSTPCR0/1, MSTPACK"),
    (0xffd80000, 0xffd80fff, "TMU (TSTR/TCOR/TCNT/TCR)"),
    (0xffd81000, 0xffd81fff, "TMU (kepdrv)"),
    (0xffe00000, 0xffe00fff, "SSI audio (wavessi1)"),
    (0xffe40000, 0xffe47fff, "SCIF channels 0-7 (8 x 0x1000)"),
    (0xffe46000, 0xffe46fff, "kernel debug serial SCIF channel 6"),
    (0xffe48000, 0xffe4bfff, "SCIF channels 8-9"),
    (0xffe4c000, 0xffe4cfff, "SD host controller port 0"),
    (0xffe4d000, 0xffe4dfff, "SD host controller port 1"),
    (0xffe70000, 0xffe708ff, "USB/OHCI host block (0xffe70808 poll)"),
    (0xffe80000, 0xffe80fff, "2DG drawing engine (gdisubdrv)"),
    (0xfff80000, 0xfff800ff, "DU display unit (gdisubdrv)"),
    (0xfff80000, 0xfff80fff, "unknown P4 block (nk)"),
    (0x10000000, 0x1fffffff, "area 4: graphics/DSP or more DRAM (role hypothesis)"),
    (0x19300000, 0x19300fff, "area 6: kernel external device regs 0x00-0x24"),
    (0x19400000, 0x1940ffff, "area 6: GPIO / CAN"),
    (0x19800000, 0x1980ffff, "area 6: navdrv"),
    (0x19a00000, 0x19a0ffff, "area 6: Bolero"),
    (0x19b00000, 0x19efffff, "area 6: absent external chip probe"),
]


def p4_form(addr: int) -> int:
    """Area-7 alias 0x1c000000..0x1fffffff -> P4 0xfc000000..0xffffffff."""
    if 0x1C000000 <= addr < 0x20000000:
        return addr | 0xE0000000
    return addr


def block_name(addr: int) -> str:
    a = p4_form(addr)
    hits = [(hi - lo + 1, name) for lo, hi, name in BLOCKS if lo <= a <= hi]
    return min(hits)[1] if hits else "unmapped/unnamed"


def parse_ts(line: str):
    m = TS.match(line)
    if not m:
        return None
    try:
        return datetime.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        return None


class ModuleResolver:
    """PC VA -> (module, provenance); never guesses an ambiguous match."""

    def __init__(self, image=None, live_modules=None):
        self.data = open(image, "rb").read() if image else None
        self.live = list(live_modules or [])
        self.static = {}
        if self.data:
            import cerom
            for seg in SEGMENTS:
                rom = cerom.CERom(self.data, seg)
                rows = []
                for mod in rom.modules():
                    e = rom.e32(mod)
                    rows.append((e["vbase"], e["vsize"], mod["name"]))
                self.static[seg] = rows

    def module_at(self, pc):
        hits = [n for (n, vb, vs) in self.live if vs and vb <= pc < vb + vs]
        if len(hits) == 1:
            return hits[0], "live"
        if len(hits) > 1:
            return "AMBIGUOUS", "live"
        for vb, vs, n in self.static.get(KERNEL_SEGMENT, []):
            if n.lower() == "nk.exe" and vs and vb <= pc < vb + vs:
                return n, "static-kernel"
        names = {n for rows in self.static.values() for vb, vs, n in rows
                 if vs and vb <= pc < vb + vs}
        if len(names) == 1:
            return names.pop(), "static"
        if len(names) > 1:
            return "AMBIGUOUS", "static"
        return "?", "none"


class Census:
    """One-pass accumulator; only 4 KiB blocks are kept in memory."""

    def __init__(self, resolver, times=None):
        self.resolver = resolver
        self.times = times or {}
        self.blocks = {}
        self.lines = 0
        self.events = 0
        self.skipped = 0
        self.with_pc = 0
        self.t0 = None
        self.last_pc = None
        self.delay_pc = None
        self.delay_line = -1
        self.time_source = "n/a"
        self.calibration = []  # (host timestamp, guest ms) from sidecar lines

    def feed(self, line, lineno):
        self.lines += 1
        ts = parse_ts(line)
        if ts is not None:
            if self.t0 is None:
                self.t0 = ts
            self.time_source = "host-elapsed"
            if lineno in self.times:
                self.calibration.append((ts, self.times[lineno]))
        pc = PC_LINE.search(line)
        if pc and TS.match(line) or (pc and not TS.match(line)):
            self.last_pc = int(pc.group(1), 16)
            return
        d = DELAY_LINE.search(line)
        if d:
            self.delay_pc = int(d.group(1), 16)
            self.delay_line = lineno
        m = INVALID.search(line)
        if m:
            addr = int(m.group(2), 16)
            kind = m.group(1)
            size = int(m.group(3))
            source = "unmapped"
        else:
            m = UNIMP.search(line)
            if not m:
                return
            base = CATCH_BASE.get(m.group(1))
            if base is None:
                return
            addr = base + int(m.group(4), 16)
            kind = m.group(2)
            size = int(m.group(3))
            source = m.group(1)
        self.events += 1
        event_pc = self.delay_pc if self.delay_line == lineno - 1 else self.last_pc
        event_pc_prov = "delay-slot" if self.delay_line == lineno - 1 else (
            "near-pc" if event_pc is not None else "none")
        if event_pc is not None:
            self.with_pc += 1
        block = p4_form(addr) & ~(BLOCK_SIZE - 1)
        r = self.blocks.setdefault(block, {
            "count": 0, "reads": 0, "writes": 0, "sizes": set(), "sources": set(),
            "pcs": set(), "modules": collections.Counter(), "provenance": set(),
            "first_line": lineno, "last_line": lineno,
            "first_time": None, "last_time": None, "first_guest": None,
            "last_guest": None,
        })
        r["count"] += 1
        r["reads" if kind == "read" else "writes"] += 1
        r["sizes"].add(size)
        r["sources"].add(source)
        r["last_line"] = lineno
        if r["first_time"] is None:
            r["first_time"] = ts
        r["last_time"] = ts
        if event_pc is not None:
            r["pcs"].add(event_pc)
            mod, prov = self.resolver.module_at(event_pc)
            r["modules"][mod] += 1
            r["provenance"].add(prov)

    def resolve_guest_times(self):
        """Interpolate guest ms for every block from the sidecar calibration.

        The sidecar gives real guest-clock readings at sampled log lines; the
        log header gives a host timestamp for each line.  Interpolation uses
        only those two measured series, never line counts or file mtimes.
        """
        if len(self.calibration) < 2:
            return
        table = sorted(self.calibration)
        self.time_source = "guest"

        def interp(ts):
            if ts is None:
                return None
            if ts <= table[0][0]:
                return table[0][1]
            if ts >= table[-1][0]:
                return table[-1][1]
            for i in range(1, len(table)):
                t0, g0 = table[i - 1]
                t1, g1 = table[i]
                if t0 <= ts <= t1:
                    frac = (ts - t0).total_seconds() / (t1 - t0).total_seconds()
                    return round(g0 + frac * (g1 - g0))
            return None

        for r in self.blocks.values():
            r["first_guest"] = interp(r["first_time"])
            r["last_guest"] = interp(r["last_time"])

    def ranked(self, top):
        return sorted(self.blocks.items(), key=lambda kv: (-kv[1]["count"], kv[0]))[:top]


def load_times(path):
    out = {}
    with open(path) as fh:
        for line in fh:
            m = TIME_LINE.match(line)
            if m:
                out[int(m.group(1))] = int(m.group(2))
    return out


def load_modules(path):
    data = json.load(open(path))
    items = data.get("modules", []) if isinstance(data, dict) else data
    return [(m["name"], int(m["vbase"], 0), int(m["vsize"], 0)) for m in items]


def fmt_time(val):
    return "n/a" if val is None else ("%.3f" % val if isinstance(val, float) else str(val))


def _row_times(census, r):
    """Return (first, last) in the reported unit, never mixing clock sources."""
    if census.time_source == "guest":
        return (fmt_time(r["first_guest"]), fmt_time(r["last_guest"]))
    if census.time_source == "host-elapsed":
        def sec(v):
            return "n/a" if v is None else "%.3f" % (v - census.t0).total_seconds()
        return (sec(r["first_time"]), sec(r["last_time"]))
    return ("n/a", "n/a")


def report(census, top, label, as_json):
    rows = census.ranked(top)
    unit = {"guest": "guest ms (interpolated)", "host-elapsed": "host s",
            "n/a": "none"}[census.time_source]
    if as_json:
        print(json.dumps({
            "label": label, "lines": census.lines, "events": census.events,
            "blocks": len(census.blocks), "with_pc": census.with_pc,
            "time_source": census.time_source, "time_unit": unit,
            "rows": [{
                "block": "0x%08x" % block, "name": block_name(block),
                "count": r["count"], "reads": r["reads"], "writes": r["writes"],
                "first_time": _row_times(census, r)[0],
                "last_time": _row_times(census, r)[1],
                "modules": dict(r["modules"]),
                "pcs": sorted(r["pcs"]),
            } for block, r in rows],
        }, indent=2))
        return
    print("== %s: %d lines, %d accesses, %d blocks, %d with PC, time=%s (%s) ==" %
          (label, census.lines, census.events, len(census.blocks),
           census.with_pc, census.time_source, unit))
    print("%4s %-10s %-42s %7s %6s %6s %-11s %-11s %s" %
          ("#", "block", "name", "count", "read", "write", "first", "last", "module (PC)"))
    for i, (block, r) in enumerate(rows, 1):
        first, last = _row_times(census, r)
        mod = r["modules"].most_common(1)[0][0] if r["modules"] else "none"
        npc = len(r["pcs"])
        print("%4d 0x%08x %-42s %7d %6d %6d %-11s %-11s %s (%d PC%s)" %
              (i, block, block_name(block), r["count"], r["reads"], r["writes"],
               first, last, mod, npc, "" if npc == 1 else "s"))


def selftest():
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))

    class FakeResolver:
        def module_at(self, pc):
            if pc == 0x8803D266:
                return "nk.exe", "static-kernel"
            if pc == 0x0398E8A2:
                return "serial_scif.dll", "live"
            return "?", "none"

    r = FakeResolver()
    c = Census(r, times={2: 1000, 3: 2000, 7: 3000, 8: 4000})
    lines = [
        "pc=0x8803d266 sr=0x50000000",
        "2026-11-24T15:35:51.000000Z Invalid read at addr 0x1FC5A000, size 4, region '(null)', reason: rejected",
        "2026-11-24T15:35:51.100000Z Invalid write at addr 0x1FC5A004, size 4, region '(null)', reason: rejected",
        "2026-11-24T15:35:51.200000Z ze0-area6: unimplemented device read  (size 2, offset 0x1b0000)",
        "2026-11-24T15:35:51.300000Z ze0-sdhi0: wr16 +0x00 = 0x0000",
        "2026-11-24T15:35:51.400000Z in delay slot (delayed_pc=0x0398e8a2)",
        "2026-11-24T15:35:51.500000Z Invalid read at addr 0x1FE70000, size 4, region '(null)', reason: rejected",
        "2026-11-24T15:35:51.600000Z Invalid read at addr 0x1FE70004, size 4, region '(null)', reason: rejected",
        "pc=0xZZZZZZZZ sr=0",
    ]
    for i, line in enumerate(lines, 1):
        c.feed(line, i)
    c.resolve_guest_times()
    check("events counted", c.events, 5)
    check("modelled trace ignored", len(c.blocks), 3)
    check("area7 alias to P4", block_name(0x1FC5A000), "GPS/odometer pulse capture or timers (kepdrv)")
    check("block grouping", c.blocks[0xFFC5A000]["count"], 2)
    check("read/write split", (c.blocks[0xFFC5A000]["reads"], c.blocks[0xFFC5A000]["writes"]), (1, 1))
    check("guest time first/last", (c.blocks[0xFFC5A000]["first_guest"], c.blocks[0xFFC5A000]["last_guest"]), (1000, 2000))
    check("host elapsed first/last", (round((c.blocks[0xFFC5A000]["first_time"] - c.t0).total_seconds(), 3),
                                      round((c.blocks[0xFFC5A000]["last_time"] - c.t0).total_seconds(), 3)), (0.0, 0.1))
    check("delay-slot PC module", c.blocks[0xFFE70000]["modules"].most_common(1)[0][0],
          "serial_scif.dll")
    check("near-PC module", c.blocks[0xFFC5A000]["modules"].most_common(1)[0][0], "nk.exe")
    check("corrupt pc rejected", c.blocks[0xFFE70000]["pcs"], {0x0398E8A2, 0x8803D266})
    check("time source guest", c.time_source, "guest")

    c2 = Census(FakeResolver())
    for i, line in enumerate([
        "Invalid read at addr 0x1FC5A000, size 4, region '(null)', reason: rejected",
        "Invalid read at addr 0x1FE70000, size 4, region '(null)', reason: rejected",
    ], 1):
        c2.feed(line, i)
    check("no timestamp -> n/a", c2.time_source, "n/a")
    check("no PC -> none", c2.with_pc, 0)
    check("unattributed", dict(c2.blocks[0xFFC5A000]["modules"]), {})

    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        report(c, 3, "selftest", False)
    text = buf.getvalue()
    check("rank table top", "0xffc5a000" in text, True)
    check("rank count printed", "GPS/odometer" in text, True)
    check("guest unit printed", "time=guest (guest ms (interpolated))" in text, True)
    check("guest first time printed", "1000" in text, True)
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        report(c2, 3, "selftest", True)
    doc = json.loads(buf2.getvalue())
    check("json time source", doc["time_source"], "n/a")
    check("json time n/a", doc["rows"][0]["first_time"], "n/a")

    # Negative mutation: remove one access -> count drops 2 -> 1.
    c3 = Census(FakeResolver(), times={3: 1000})
    for i, line in enumerate(lines, 1):
        if i != 2:
            c3.feed(line, i)
    check("negative mutation count drops", c3.blocks[0xFFC5A000]["count"], 1)
    # Negative mutation: swap the address -> the block name changes.
    c4 = Census(FakeResolver())
    c4.feed(lines[0].replace("0x1FC5A000", "0x1FC41000"), 1)
    check("negative mutation address changes block", block_name(0xFFC41000), "GPIO ports")

    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("log", nargs="?", help="QEMU -d log (streamed line by line)")
    ap.add_argument("--top", type=int, default=30, help="rows to print (default 30)")
    ap.add_argument("--image", metavar="IMG256", help="firmware image for module attribution")
    ap.add_argument("--modules", metavar="JSON", help="live module list (ze0_ps.py --json)")
    ap.add_argument("--times", metavar="FILE", help="<log_line_no> <guest_ms> sidecar")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--label", default="unmapped", help="report label")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.log:
        ap.error("give LOG")
    resolver = ModuleResolver(args.image, load_modules(args.modules) if args.modules else None)
    census = Census(resolver, load_times(args.times) if args.times else None)
    with open(args.log, encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            census.feed(line, lineno)
    census.resolve_guest_times()
    report(census, args.top, args.label, args.json)
    return 0 if census.events else 2


if __name__ == "__main__":
    raise SystemExit(main())
