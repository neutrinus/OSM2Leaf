#!/usr/bin/env python3
"""Executed-function coverage from a QEMU TCG plugin trace of ``-M ze0``.

``tools/qemu-ze0/plugins/ze0_cov.c`` prints one ``VA,COUNT`` line per executed
basic block (visible with QEMU's ``-d plugin``).  This tool parses that trace,
maps each guest virtual PC to a CE module and a ``.pdata`` function start, and
prints executed-function coverage.  Reader VAs come from the located mount
readers in ``docs/research/reader-coverage.md`` (rows 3-4); the POINT walker
(row 10) is the negative control before any POI search.

The POINT walker is a ``.pdata`` GAP, not a START, so a function-start-only
check would be vacuous.  The JSON therefore carries the raw executed block
VAs too, and ``point_walker_absent`` is computed from the raw block set.

Usage:
  ze0_cov.py RUN --module Navi.exe --json [--log FILE] [--log2 FILE]
                 [--modules FILE] [--monitor SOCK] [--image IMG] [--cache DIR]
                 [--plugin PATH] [--label LABEL]
  ze0_cov.py DIFF A.json B.json [--module Navi.exe] [--json]
  ze0_cov.py --selftest

RUN with no --log launches QEMU (--qemu), boots the EU2011 head with the
plugin, and captures the log; --plugin/--period are passed to QEMU.  With
--log it replays a saved plugin log instead (no QEMU needed).  Two-run diff
is produced with --log2, or later with DIFF on two saved JSON documents.

Stdlib only. Method and results:
docs/experiments/EXP-2026-11-24-M8.H9-tcg-coverage.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# Located mount readers, quoted verbatim from docs/research/reader-coverage.md
# rows 3-4 (each re-verified with `tools/pdata.py fn`; see the EXP).
READERS = {
    "MMAIN001 reader": 0x0041A438,
    "DRSTR open": 0x00419684,
    "DRSTR parser": 0x00419350,
}
# POINT walker body, from `tools/sh4dis.py --va 0x003f5194 ...`: the loop ends
# at 0x003f51c8, jumps to the rts at 0x003f51d0 and its delay slot at
# 0x003f51d2; the literal pool starts at 0x003f51d4.
POINT_WALKER_START = 0x003F5194
POINT_WALKER_END = 0x003F51D4  # exclusive

PLUGIN_LINE = "ze0_cov: VA,COUNT"
STATS_LINE = "ze0_cov: period="
BLOCK_RE = re.compile(r"^0x([0-9a-fA-F]{1,16}),(\d+)$")


# ---------------------------------------------------------------------------
# Plugin log parsing
# ---------------------------------------------------------------------------


def parse_log(path: str) -> dict:
    """Return {blocks, stats} from a plugin log; blocks map VA -> summed count.

    Multiple TBs can share a start VA with different insn counts; the host
    aggregates them by VA (the raw VA set is what the walker check needs).
    """
    blocks: dict[int, int] = {}
    stats: dict[str, int] = {}
    seen_header = False
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith(STATS_LINE):
                # ze0_cov: period=1 translated=37613 recorded=31372 entries=31372
                for field in line[len(STATS_LINE):].split():
                    if "=" in field:
                        k, v = field.split("=", 1)
                        try:
                            stats[k] = int(v)
                        except ValueError:
                            pass
            elif line == PLUGIN_LINE:
                seen_header = True
            elif seen_header:
                m = BLOCK_RE.match(line)
                if m:
                    va = int(m.group(1), 16)
                    count = int(m.group(2))
                    blocks[va] = blocks.get(va, 0) + count
    if not seen_header and not blocks:
        raise ValueError("no ze0_cov block lines in %s (wrong -d plugin?)" % path)
    return {"blocks": blocks, "stats": stats}


# ---------------------------------------------------------------------------
# Live module list from a running guest
# ---------------------------------------------------------------------------


def load_modules(path: str | None) -> list[tuple[str, int, int]]:
    if not path:
        return []
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        data = data.get("modules", [])
    out = []
    for row in data:
        out.append((row["name"], int(row["vbase"], 0), int(row["vsize"], 0)))
    return out


def live_modules(sock_path: str) -> list[tuple[str, int, int]]:
    try:
        import ze0_ps
        mem = ze0_ps.Memory(ze0_ps.HmpMemory(sock_path))
        snap = ze0_ps.take_snapshot(mem, ze0_ps.KDATA_P1)
        return [(m.name, m.vbase, m.vsize) for m in snap.modules]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Coverage computation
# ---------------------------------------------------------------------------


def make_resolver(image, modules, cache):
    from ze0_pcsample import Resolver
    return Resolver(image=image, live_modules=modules, cache=cache)


def _fn_for_module(resolver, module):
    """Return fn_of(va) for *module* from the resolver's pdata tables.

    ``ze0_pcsample.Resolver`` decodes pdata per (segment, module).  We try each
    known segment in turn and keep the first table that yields a start for a
    VA; a module with no table yields None (GAP), never a guess.
    """
    if resolver is None or module in ("?", "AMBIGUOUS"):
        return None
    segments = (0x3E00200, 0x200200, 0x5200200)
    fns = []
    for seg in segments:
        try:
            fn = resolver._fn(seg, module)
        except Exception:
            fn = None
        if fn is not None:
            fns.append(fn)

    def fn_of(va):
        for fn in fns:
            start = fn(va)
            if start is not None:
                return start
        return None

    return fn_of if fns else None


def coverage(blocks: dict[int, int], module: str, resolver,
             walker_start=POINT_WALKER_START, walker_end=POINT_WALKER_END,
             readers=READERS) -> dict:
    fn_of = _fn_for_module(resolver, module)
    functions: dict[int, int] = {}
    unresolved = 0
    for va, count in blocks.items():
        fn = fn_of(va) if fn_of is not None else None
        if fn is None:
            unresolved += 1
        else:
            functions[fn] = functions.get(fn, 0) + count
    reader_hits = {}
    for name, va in readers.items():
        start = fn_of(va) if fn_of is not None else None
        reader_hits[name] = {
            "va": "0x%08x" % va,
            "executed": start in functions if start is not None else va in blocks,
            "function_start": ("0x%08x" % start) if start is not None else None,
        }
    walker_blocks = [va for va in blocks if walker_start <= va < walker_end]
    return {
        "module": module,
        "tb_count": len(blocks),
        "insn_executions": sum(blocks.values()),
        "executed_function_count": len(functions),
        "executed_functions": ["0x%08x" % v for v in sorted(functions)],
        "unresolved_blocks": unresolved,
        "reader_hits": reader_hits,
        "reader_hit_count": sum(1 for r in reader_hits.values() if r["executed"]),
        "point_walker": {
            "range": ["0x%08x" % walker_start, "0x%08x" % walker_end],
            "hits": ["0x%08x" % v for v in sorted(walker_blocks)],
            "absent": not walker_blocks,
        },
        "raw_blocks": {("0x%08x" % va): count for va, count in sorted(blocks.items())},
    }


def diff_cover(a: dict, b: dict) -> dict:
    def add(a, b):
        return sorted(set(b) - set(a))
    fa, fb = set(a["executed_functions"]), set(b["executed_functions"])
    ba, bb = set(a["raw_blocks"]), set(b["raw_blocks"])
    return {
        "functions_added": add(fa, fb),
        "functions_removed": add(fb, fa),
        "blocks_added": add(ba, bb),
        "blocks_removed": add(bb, ba),
        "function_count_delta": len(fb) - len(fa),
        "block_count_delta": len(bb) - len(ba),
    }


# ---------------------------------------------------------------------------
# Running QEMU with the plugin
# ---------------------------------------------------------------------------


def run_qemu(args, log_path: str) -> None:
    plugin = args.plugin
    if not plugin:
        plugin = os.path.join(HERE, "qemu-ze0", "plugins", "libze0_cov.so")
    if not os.path.isfile(plugin):
        raise SystemExit("ze0_cov: no plugin at %s (run make -C tools/qemu-ze0/plugins)" % plugin)
    qemu = args.qemu
    image = args.image
    cmd = [qemu, "-plugin", "file=%s" % plugin]
    if args.period and args.period != 1:
        cmd[-1] += ",period=%d" % args.period
    cmd += ["-M", "ze0", "-kernel", image, "-nographic", "-serial", "none",
            "-monitor", "none", "-icount", "shift=0,sleep=off",
            "-d", "plugin", "-D", log_path]
    print("ze0_cov: " + " ".join(cmd), file=sys.stderr)
    proc = subprocess.Popen(cmd)
    try:
        proc.wait(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


# ---------------------------------------------------------------------------
# Selftest on a synthetic trace
# ---------------------------------------------------------------------------


def selftest() -> int:
    passed = failed = 0

    def check(label, cond):
        nonlocal passed, failed
        if cond:
            passed += 1
            print("ok   %s" % label)
        else:
            failed += 1
            print("FAIL %s" % label, file=sys.stderr)

    # Synthetic resolver: one module with four function starts. The reader
    # function at 0x0041a438 spans 0xf4 bytes; the walk body is in a gap.
    class FakeResolver:
        def __init__(self):
            self.starts = [0x00419350, 0x00419684, 0x0041A438, 0x00558300]

        def _fn(self, seg, module):
            import bisect
            def fn_of(va):
                i = bisect.bisect_right(self.starts, va) - 1
                return self.starts[i] if i >= 0 else None
            return fn_of

    r = FakeResolver()
    # One block inside each reader, one elsewhere, and one in the walker body
    # (0x003f51b0 is inside [start, end)). Count the duplicate-VA aggregation.
    blocks = {
        0x0041A438: 5,
        0x00419684: 7,
        0x00419350: 3,
        0x00410000: 11,
        0x003F51B0: 1,
        0x0041A438 + 0x40: 2,  # second block in the MMAIN reader
    }
    cov = coverage(blocks, "Navi.exe", r)
    check("tb count is 6 (printed below)", cov["tb_count"] == 6)
    print("     tb_count = %d" % cov["tb_count"])
    check("executed-function count is 3", cov["executed_function_count"] == 3)
    print("     executed_function_count = %d" % cov["executed_function_count"])
    check("reader hit count is 3", cov["reader_hit_count"] == 3)
    print("     reader_hit_count = %d" % cov["reader_hit_count"])
    check("MMAIN reader executed", cov["reader_hits"]["MMAIN001 reader"]["executed"])
    check("DRSTR open executed", cov["reader_hits"]["DRSTR open"]["executed"])
    check("DRSTR parser executed", cov["reader_hits"]["DRSTR parser"]["executed"])
    check("walker body detected (negative control fails)",
          not cov["point_walker"]["absent"] and cov["point_walker"]["hits"] == ["0x003f51b0"])
    print("     walker hits = %s" % cov["point_walker"]["hits"])
    # Mutation: remove the walker block -> negative control passes, count drops.
    mutated = dict(blocks)
    del mutated[0x003F51B0]
    mcov = coverage(mutated, "Navi.exe", r)
    check("mutation: tb count drops to 5", mcov["tb_count"] == 5)
    print("     mutated tb_count = %d" % mcov["tb_count"])
    check("mutation: walker now absent", mcov["point_walker"]["absent"])
    check("mutation: reader count unchanged at 3", mcov["reader_hit_count"] == 3)
    # Mutation: drop one reader block -> hit count must drop and that reader fails.
    mutated2 = dict(mutated)
    del mutated2[0x00419684]
    m2 = coverage(mutated2, "Navi.exe", r)
    check("mutation: DRSTR open now absent", not m2["reader_hits"]["DRSTR open"]["executed"])
    check("mutation: reader count drops to 2", m2["reader_hit_count"] == 2)
    # Diff of two sets.
    d = diff_cover(cov, m2)
    check("diff: functions removed = 1", len(d["functions_removed"]) == 1)
    check("diff: block count delta = -2", d["block_count_delta"] == -2)
    print("     diff function_count_delta = %d, block_count_delta = %d"
          % (d["function_count_delta"], d["block_count_delta"]))

    # Log parsing on a synthetic file.
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "trace.log")
        with open(p, "w") as h:
            h.write("ze0_cov: period=1 translated=10 recorded=4 entries=2\n")
            h.write("ze0_cov: VA,COUNT\n0x000000000041a438,3\n0x000000000041a438,2\n")
        parsed = parse_log(p)
        check("parse: two VAs aggregated to one", len(parsed["blocks"]) == 1)
        check("parse: counts summed to 5", parsed["blocks"][0x41A438] == 5)
        check("parse: stats translated=10", parsed["stats"].get("translated") == 10)
    print("selftest: %d passed, %d failed" % (passed, failed))
    return 0 if failed == 0 else 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("action", nargs="?", default="RUN", metavar="RUN|DIFF",
                    help="RUN (default) or DIFF A.json B.json")
    ap.add_argument("files", nargs="*", help="two JSON files for DIFF")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--module", default="Navi.exe", help="module to attribute (default Navi.exe)")
    ap.add_argument("--log", metavar="FILE", help="replay a saved plugin log")
    ap.add_argument("--log2", metavar="FILE", help="second saved plugin log for the two-run diff")
    ap.add_argument("--modules", metavar="FILE", help="saved ze0_ps.py --json module list")
    ap.add_argument("--monitor", metavar="SOCK", help="live HMP socket for the module table")
    ap.add_argument("--image", default=os.path.join(HERE, "..", "archive", "head256.img"),
                    help="firmware image for pdata attribution")
    ap.add_argument("--cache", metavar="DIR", help="pdata decode cache")
    ap.add_argument("--qemu", default=os.path.expanduser("~/.cache/qemu-ze0/build/qemu-system-sh4"),
                    help="qemu-system-sh4 to launch with the plugin")
    ap.add_argument("--plugin", metavar="PATH", help="path to libze0_cov.so")
    ap.add_argument("--period", type=int, default=1, help="sample every Nth translated block")
    ap.add_argument("--timeout", type=int, default=60, help="seconds before killing QEMU (default 60)")
    ap.add_argument("--label", default="boot", help="label printed in the report")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    action = args.action.upper()
    if action == "DIFF":
        if len(args.files) != 2:
            ap.error("DIFF needs two JSON files")
        docs = []
        for path in args.files:
            with open(path, "r", encoding="utf-8") as h:
                docs.append(json.load(h))
        result = diff_cover(docs[0]["coverage"], docs[1]["coverage"])
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            for key in ("functions_added", "functions_removed",
                        "blocks_added", "blocks_removed"):
                print("%s: %d" % (key, len(result[key])))
            print("function_count_delta: %d, block_count_delta: %d"
                  % (result["function_count_delta"], result["block_count_delta"]))
        return 0

    if action != "RUN":
        ap.error("unknown action %r (want RUN or DIFF)" % args.action)

    logs = []
    if args.log:
        logs.append(args.log)
    else:
        p = tempfile.mktemp(prefix="ze0-cov-", suffix=".log",
                            dir=os.environ.get("TMPDIR") or None)
        run_qemu(args, p)
        logs.append(p)
    if args.log2:
        logs.append(args.log2)

    modules = load_modules(args.modules)
    if args.monitor:
        modules = live_modules(args.monitor) or modules
    resolver = None
    if os.path.isfile(args.image):
        resolver = make_resolver(args.image, modules, args.cache)

    covers = []
    for log in logs:
        parsed = parse_log(log)
        covers.append(coverage(parsed["blocks"], args.module, resolver))
        covers[-1]["label"] = os.path.basename(log)
        covers[-1]["plugin_stats"] = parsed["stats"]
        if not args.log:  # our own temporary log
            try:
                os.unlink(log)
            except OSError:
                pass

    doc = {
        "schema": "osm2leaf.ze0_cov/v1",
        "generator": "tools/ze0_cov.py",
        "label": args.label,
        "module": args.module,
        "coverage": covers[0],
    }
    if len(covers) == 2:
        doc["coverage2"] = covers[1]
        doc["diff"] = diff_cover(covers[0], covers[1])

    if args.json:
        print(json.dumps(doc, indent=2, sort_keys=True))
    else:
        c = covers[0]
        print("ze0_cov %s: %s" % (args.label, args.module))
        print("  executed functions: %d (blocks: %d, insn executions: %d)"
              % (c["executed_function_count"], c["tb_count"], c["insn_executions"]))
        for name, hit in c["reader_hits"].items():
            print("  reader %-18s %s (fn %s)"
                  % (name, "EXECUTED" if hit["executed"] else "absent",
                     hit["function_start"] or "-"))
        print("  reader hits: %d/%d" % (c["reader_hit_count"], len(c["reader_hits"])))
        print("  POINT walker %s: %s"
              % (c["point_walker"]["range"],
                 "ABSENT" if c["point_walker"]["absent"]
                 else "PRESENT " + ",".join(c["point_walker"]["hits"])))
        if len(covers) == 2:
            d = doc["diff"]
            print("  diff: functions +%d/-%d, blocks +%d/-%d"
                  % (len(d["functions_added"]), len(d["functions_removed"]),
                     len(d["blocks_added"]), len(d["blocks_removed"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
