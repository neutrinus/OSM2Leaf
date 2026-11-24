#!/usr/bin/env python3
"""Guest PC-sampling profiler for a running ``-M ze0`` Windows CE guest.

Samples the guest program counter through QEMU's HMP ``info registers`` and
prints a module/function histogram, so a slow boot can be attributed to a
device poll rather than guessed (TODO M8.H23, expanding the manual sampling of
EXP-2026-11-22-M8.C1e).

Why module attribution needs care
---------------------------------
A PC VA alone cannot name a module: the guest loads image A (0x200200) and B
(0x3e00200) at once, and several modules share a vbase (e.g. 0x10000 in 14
modules).  Resolution order:

1. the LIVE guest module table (``ze0_ps.py``, read over HMP) — authoritative
   for user-slot DLLs;
2. the kernel P1 range against ``nk.exe`` of image B — the live CE module list
   does not include the kernel itself;
3. a static cerom vbase scan over A/B/C, accepted only when unique (otherwise
   ``AMBIGUOUS``, never a guess).

Function starts come from each module's ``.pdata`` exception directory via
``pdata.load_table``/``fn_of_factory``; a VA in a gap is reported GAP (no
start), never a fabricated name.  Every sample carries its attribution
provenance (``live`` / ``static-kernel`` / ``static`` / ``none``).

Usage:
  ze0_pcsample.py --monitor SOCK --n 500 --interval 0.05 [--modules-from-ps]
                  [--top 20] [--json] [--save CAPTURE] [--image IMG] [--cache DIR]
  ze0_pcsample.py --file CAPTURE [--top 20] [--json] [--image IMG]
  ze0_pcsample.py --selftest

A CAPTURE file stores one ``=== SAMPLE n ===`` block per raw HMP reply, so a
live run can be replayed and graded offline.  No vendor bytes are committed.

Method and results: docs/experiments/EXP-2026-11-24-M8.H23-pc-sampler.md
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import socket
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

SEGMENTS = (0x200200, 0x3E00200, 0x5200200)
KERNEL_SEGMENT = 0x3E00200
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\r")
PC_LINE = re.compile(r"^pc=0x([0-9a-fA-F]{8})\b", re.MULTILINE)
SAMPLE_MARK = re.compile(r"^=== SAMPLE (\d+) ===$", re.MULTILINE)


def strip_ansi(text: str) -> str:
    """Remove HMP terminal echoes/ANSI so a valid ``pc=`` line starts a line."""
    return ANSI.sub("", text)


def parse_pc(text: str) -> int | None:
    """Parse the anchored ``pc=0x........`` line of one ``info registers`` reply.

    ``spc=`` and ``delayed_pc=`` also contain the substring ``pc=0x`` (D6), so
    the match is anchored at line start.  A missing or malformed line returns
    None — never a fabricated VA.
    """
    m = PC_LINE.search(strip_ansi(text))
    return int(m.group(1), 16) if m else None


# ---------------------------------------------------------------------------
# Monitors: anything with .registers() -> one raw reply (or StopIteration)
# ---------------------------------------------------------------------------


class HmpMonitor:
    """One persistent HMP connection, draining to the ``(qemu)`` prompt."""

    def __init__(self, path: str, timeout: float = 5.0):
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.s.settimeout(timeout)
        self.s.connect(path)
        self._drain()

    def _drain(self) -> str:
        buf = b""
        while not buf.endswith(b"(qemu) "):
            chunk = self.s.recv(65536)
            if not chunk:
                break
            buf += chunk
        return buf.decode("latin1")

    def registers(self) -> str:
        self.s.sendall(b"info registers\n")
        return self._drain()

    def close(self) -> None:
        try:
            self.s.sendall(b"q\n")
        except OSError:
            pass
        self.s.close()


class ReplayMonitor:
    """Replay the raw replies saved by ``--save`` (no guest needed)."""

    def __init__(self, blocks: list[str]):
        self.blocks = list(blocks)
        self.i = 0

    def registers(self) -> str:
        if self.i >= len(self.blocks):
            raise StopIteration
        block = self.blocks[self.i]
        self.i += 1
        return block


def load_capture(path: str) -> list[str]:
    """Split a ``=== SAMPLE n ===`` capture into raw reply blocks."""
    with open(path, "r", errors="replace") as fh:
        text = fh.read()
    marks = list(SAMPLE_MARK.finditer(text))
    if not marks:
        return [text] if text.strip() else []
    return [text[m.end():marks[i + 1].start() if i + 1 < len(marks) else len(text)]
            for i, m in enumerate(marks)]


# ---------------------------------------------------------------------------
# Resolution: module (live/static) and function (pdata)
# ---------------------------------------------------------------------------


class Resolver:
    def __init__(self, image: str | None = None, live_modules=None,
                 cache: str | None = None):
        self.data = open(image, "rb").read() if image else None
        self.live = list(live_modules or [])
        self.cache = cache
        self._static: dict[int, list[tuple[int, int, str]]] = {}
        self._fns: dict[tuple[int, str], object] = {}
        self._build_static()

    def _build_static(self) -> None:
        if not self.data:
            return
        import cerom
        for seg in SEGMENTS:
            rom = cerom.CERom(self.data, seg)
            rows = []
            for mod in rom.modules():
                e = rom.e32(mod)
                rows.append((e["vbase"], e["vsize"], mod["name"]))
            self._static[seg] = rows

    def module_at(self, pc: int) -> tuple[str, str]:
        hits = [n for (n, vb, vs) in self.live if vs and vb <= pc < vb + vs]
        if len(hits) == 1:
            return hits[0], "live"
        if len(hits) > 1:
            return "AMBIGUOUS", "live"
        for vb, vs, n in self._static.get(KERNEL_SEGMENT, []):
            if n.lower() == "nk.exe" and vs and vb <= pc < vb + vs:
                return n, "static-kernel"
        names = {n for rows in self._static.values() for vb, vs, n in rows
                 if vs and vb <= pc < vb + vs}
        if len(names) == 1:
            return names.pop(), "static"
        if len(names) > 1:
            return "AMBIGUOUS", "static"
        return "?", "none"

    def _fn(self, seg: int, module: str):
        key = (seg, module)
        if key in self._fns:
            return self._fns[key]
        fn = None
        if self.data:
            import pdata
            try:
                recs, _meta = pdata.load_table(self.data, seg, module, self.cache)
                fn = pdata.fn_of_factory(recs)
            except Exception:  # noqa: BLE001 - a missing table is not a guess
                fn = None
        self._fns[key] = fn
        return fn

    def fn_at(self, pc: int, module: str, provenance: str | None = None):
        """Return the pdata function START of ``pc`` in ``module``, or None.

        ``provenance`` is recorded by the caller but does not change the table
        choice: every module's pdata is decoded from its own image segment.
        """
        if module in ("?", "AMBIGUOUS"):
            return None
        for seg in (KERNEL_SEGMENT, 0x200200, 0x5200200):
            fn = self._fn(seg, module)
            if fn is not None:
                start = fn(pc)
                if start is not None:
                    return start
        return None


def live_modules(sock: str):
    """Read the live CE module table via ze0_ps.py (empty list on failure)."""
    try:
        import ze0_ps
        mem = ze0_ps.Memory(ze0_ps.HmpMemory(sock))
        snap = ze0_ps.take_snapshot(mem, ze0_ps.KDATA_P1)
        return [(m.name, m.vbase, m.vsize) for m in snap.modules]
    except Exception:  # noqa: BLE001 - fall back to static attribution
        return []


# ---------------------------------------------------------------------------
# Sampling and reporting
# ---------------------------------------------------------------------------


def sample(monitor, n: int, interval: float, resolver: Resolver,
           save_path: str | None = None) -> dict:
    counts: collections.Counter = collections.Counter()
    provenance: collections.Counter = collections.Counter()
    mod_provenance: dict[str, str] = {}
    pcs: list[int] = []
    blocks: list[str] = []
    read = parsed = 0
    for i in range(n):
        try:
            text = monitor.registers()
        except StopIteration:
            break
        read += 1
        blocks.append(text)
        pc = parse_pc(text)
        if pc is None:
            continue
        parsed += 1
        pcs.append(pc)
        mod, prov = resolver.module_at(pc)
        fn = resolver.fn_at(pc, mod, prov)
        counts[(mod, fn)] += 1
        provenance[prov] += 1
        mod_provenance.setdefault(mod, prov)
        if interval and i < n - 1:
            time.sleep(interval)
    if save_path and blocks:
        with open(save_path, "w") as fh:
            for i, block in enumerate(blocks):
                fh.write("=== SAMPLE %d ===\n%s\n" % (i, block))
    return dict(read=read, parsed=parsed, pcs=pcs, counts=counts,
                provenance=provenance, mod_provenance=mod_provenance)


def report(result: dict, top: int, label: str, as_json: bool) -> None:
    counts = result["counts"]
    total = sum(counts.values()) or 1
    rows = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1] or 0))
    bymod: collections.Counter = collections.Counter()
    for (mod, _fn), c in counts.items():
        bymod[mod] += c
    if as_json:
        print(json.dumps({
            "label": label,
            "read": result["read"], "parsed": result["parsed"],
            "attributed": sum(counts.values()),
            "provenance": dict(result["provenance"]),
            "functions": [
                {"count": c, "pct": round(100.0 * c / total, 2),
                 "module": mod, "fn": "0x%08x" % fn if fn else None,
                 "provenance": result["mod_provenance"].get(mod, "?")}
                for (mod, fn), c in rows[:top]
            ],
            "modules": [{"count": c, "pct": round(100.0 * c / total, 2),
                         "module": m} for m, c in
                        sorted(bymod.items(), key=lambda kv: -kv[1])],
        }, indent=2))
        return
    print("== %s: %d raw, %d parsed, %d attributed ==" %
          (label, result["read"], result["parsed"], sum(counts.values())))
    print("provenance: %s" % ", ".join("%s=%d" % kv
                                       for kv in result["provenance"].most_common()))
    print("%6s %7s  %-22s %-12s" % ("count", "pct", "module", "fn"))
    for (mod, fn), c in rows[:top]:
        print("%6d %6.2f%%  %-22s %-12s" %
              (c, 100.0 * c / total, mod,
               "0x%08x" % fn if fn else "GAP"))
    print("-- by module --")
    for mod, c in sorted(bymod.items(), key=lambda kv: -kv[1]):
        print("%6d %6.2f%%  %s" % (c, 100.0 * c / total, mod))


# ---------------------------------------------------------------------------
# Selftest (hermetic: no vendor image, no QEMU)
# ---------------------------------------------------------------------------


def selftest() -> int:
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))

    reply = ("\x1b[K\x1b[Dinfo registers\x1b[K\r\n\r\nCPU#0\r\n"
             "pc=0x8803d266 sr=0x50008001 pr=0x8803ccc8\r\n"
             "spc=0x00015e3c ssr=0x40008000\r\n"
             "delayed_pc=0x8800ee44 fpul=0x00000000\r\n"
             "(qemu) ")
    check("anchored PC parse", parse_pc(reply), 0x8803D266)
    check("break at newline", parse_pc("CPU#0\npc=0x0398e8a2 sr=0\n"), 0x0398E8A2)
    check("spc is not PC", parse_pc("spc=0x00015e3c\n"), None)
    check("delayed_pc is not PC", parse_pc("delayed_pc=0x8800ee44\n"), None)
    check("corrupt pc rejected", parse_pc("pc=0xZZZZZZZZ sr=0\n"), None)
    check("short pc rejected", parse_pc("pc=0x123 sr=0\n"), None)
    check("no pc rejected", parse_pc("CPU#0\n(QEMU) "), None)

    # Replay from a capture file built by --save, including a corrupt sample.
    cap = ("=== SAMPLE 0 ===\n" + reply + "\n"
           "=== SAMPLE 1 ===\npc=0x0398e8a2 sr=0x50000000\n(qemu) \n"
           "=== SAMPLE 2 ===\npc=0xZZZZZZZZ sr=0\n(qemu) \n"
           "=== SAMPLE 3 ===\npc=0x8803d266 sr=0\n(qemu) \n")
    import tempfile
    with tempfile.TemporaryDirectory(prefix="ze0-pcsample-") as td:
        path = os.path.join(td, "capture.txt")
        with open(path, "w") as fh:
            fh.write(cap)
        blocks = load_capture(path)
        check("capture split", len(blocks), 4)
        # Synthetic resolver: two live modules + static nk.exe fallback.
        mods = [("serial_scif.dll", 0x03980000, 0x00013000)]
        r = Resolver(image=None, live_modules=mods)
        r._static[KERNEL_SEGMENT] = [(0x88000000, 0x00088000, "nk.exe")]
        r._fns[(KERNEL_SEGMENT, "nk.exe")] = lambda va: 0x8803D264
        r._fns[(KERNEL_SEGMENT, "serial_scif.dll")] = lambda va: 0x0398E888
        res = sample(ReplayMonitor(blocks), 10, 0, r)
        check("read four blocks", res["read"], 4)
        check("parsed three PCs", res["parsed"], 3)
        check("module nk.exe", r.module_at(0x8803d266)[0], "nk.exe")
        check("module serial_scif", r.module_at(0x0398e8a2)[0], "serial_scif.dll")
        check("provenance live", r.module_at(0x0398e8a2)[1], "live")
        check("provenance static-kernel", r.module_at(0x8803d266)[1], "static-kernel")
        check("fn nk.exe", hex(r.fn_at(0x8803d266, "nk.exe", "static-kernel")),
              "0x8803d264")
        check("fn serial_scif", hex(r.fn_at(0x0398e8a2, "serial_scif.dll", "live")),
              "0x398e888")
        check("counts top", res["counts"].most_common(1)[0][1], 2)
        # JSON report must not crash (D7) and must quote the same counts.
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            report(res, 10, "selftest", True)
        doc = json.loads(buf.getvalue())
        check("json read", doc["read"], 4)
        check("json parsed", doc["parsed"], 3)
        check("json attributed", doc["attributed"], 3)
        check("json provenance serial", doc["functions"][-1]["provenance"], "live")
        # Negative mutation: drop the valid sample -> parsed goes 3 -> 2.
        bad = cap.replace("pc=0x0398e8a2 sr=0x50000000", "pc=0xZZZZZZZZ sr=0x50000000")
        with open(path, "w") as fh:
            fh.write(bad)
        res2 = sample(ReplayMonitor(load_capture(path)), 10, 0, r)
        check("negative mutation parsed drops", res2["parsed"], 2)

    # Ambiguity must be reported, never guessed.
    r2 = Resolver(image=None)
    r2._static[0x200200] = [(0x00010000, 0x1000, "Navi.exe"),
                            (0x00010000, 0x1000, "shell.exe")]
    check("ambiguous static", r2.module_at(0x00010010),
          ("AMBIGUOUS", "static"))

    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def load_modules(path: str):
    """Load modules from a saved ``ze0_ps.py --json`` snapshot (D8).

    Accepts the JSON object's ``modules`` list or a bare list; each item is
    ``{name, vbase, vsize}`` with VAs as 0x-prefixed strings or integers.
    """
    data = json.load(open(path))
    items = data.get("modules", []) if isinstance(data, dict) else data
    out = []
    for m in items:
        vb = int(m["vbase"], 0)
        vs = int(m["vsize"], 0)
        out.append((m["name"], vb, vs))
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--monitor", metavar="SOCK", help="QEMU HMP UNIX socket")
    ap.add_argument("--file", metavar="CAPTURE", help="replay a saved capture")
    ap.add_argument("--n", type=int, default=500, help="samples (default 500)")
    ap.add_argument("--interval", type=float, default=0.05,
                    help="seconds between samples (default 0.05)")
    ap.add_argument("--modules-from-ps", action="store_true",
                    help="read the live module table via ze0_ps.py")
    ap.add_argument("--modules", metavar="FILE",
                    help="replay a saved ze0_ps.py --json module list (or a list of {name,vbase,vsize})")
    ap.add_argument("--image", metavar="IMG",
                    help="firmware image for module/pdata attribution")
    ap.add_argument("--cache", metavar="DIR", help="pdata decode cache directory")
    ap.add_argument("--top", type=int, default=20, help="rows to print (default 20)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--label", default="profile", help="label in the report")
    ap.add_argument("--save", metavar="CAPTURE", help="save raw replies for replay")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if bool(args.monitor) == bool(args.file):
        ap.error("give exactly one of --monitor SOCK or --file CAPTURE")

    mods = []
    monitor = None
    if args.monitor:
        if args.modules_from_ps:
            mods = live_modules(args.monitor)
        monitor = HmpMonitor(args.monitor)
    else:
        monitor = ReplayMonitor(load_capture(args.file))
    if args.modules:
        mods = load_modules(args.modules)
    resolver = Resolver(args.image, mods, args.cache)
    try:
        result = sample(monitor, args.n, args.interval, resolver, args.save)
    finally:
        if isinstance(monitor, HmpMonitor):
            monitor.close()
    if result["read"] == 0:
        print("ze0_pcsample: no samples read", file=sys.stderr)
        return 2
    report(result, args.top, args.label, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
