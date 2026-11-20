#!/usr/bin/env python3
"""Count the PySh4 forms a tool run actually executes (M9.51).

Before an engine change, the question "did any L3 run execute this form?" is
answered by running the tool with every ``PySh4._execute`` call counted, not
by reading code.  This wrapper imports the engine under both names the tools
use (``engine`` with ``tools/l3_harness`` on ``sys.path``, and
``l3_harness.engine``), wraps ``PySh4._execute`` in each, runs the tool as
``__main__`` with its own arguments, and prints the executed forms.

Wrapping ``_execute`` on the class turns the M9.45 fast path off for the run
(every instruction is stepped and counted), so the run is slower but its
results are the stepped engine's, which equal the fast path's (C-5322).

Usage:
  arm_census.py [--form FORM ...] [--top N] -- TOOL.py ARGS...
  arm_census.py --selftest

Exit code: the tool's own exit code (``SystemExit``), or 1 if a ``--form``
was executed and ``--fail-if-executed`` is given.
"""

from __future__ import annotations

import argparse
import collections
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for path in (HERE, TOOLS):
    if path not in sys.path:
        sys.path.insert(0, path)

import engine as engine_plain              # noqa: E402  (``from engine import``)
from l3_harness import engine as engine_pkg  # noqa: E402


def install(counts: collections.Counter, sites: dict):
    """Wrap ``PySh4._execute`` in both engine modules; return an undo."""
    saved = []
    for mod in {id(engine_plain): engine_plain, id(engine_pkg): engine_pkg}.values():
        cls = mod.PySh4
        orig = cls._execute

        def wrapped(self, insn, pc, _orig=orig):
            self._arm = None
            try:
                _orig(self, insn, pc)
            finally:
                arm = self._arm or "(unnamed %#06x)" % (insn & 0xF00F)
                counts[arm] += 1
                sites.setdefault(arm, collections.Counter())[pc & 0xFFFFFFFF] += 1

        cls._execute = wrapped
        saved.append((cls, orig))

    def undo():
        for cls, orig in saved:
            cls._execute = orig
    return undo


def run_tool(argv: list[str], counts, sites) -> int:
    undo = install(counts, sites)
    old_argv = sys.argv[:]
    sys.argv = list(argv)
    code = 0
    try:
        runpy.run_path(argv[0], run_name="__main__")
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    finally:
        sys.argv = old_argv
        undo()
    return code


def report(counts, sites, forms, top, out=sys.stdout) -> bool:
    total = sum(counts.values())
    print("arm_census: %d instructions executed, %d forms" % (total, len(counts)), file=out)
    for arm, n in counts.most_common(top or None):
        print("  %-28s %10d" % (arm, n), file=out)
    hit = False
    for form in forms:
        n = counts.get(form, 0)
        hit = hit or n > 0
        where = ", ".join("%#010x x%d" % kv for kv in sorted(sites.get(form, {}).items())[:8])
        print("form %-12s executed %d time(s)%s" % (form, n, (" at " + where) if n else ""),
              file=out)
    return hit


def selftest() -> int:
    import io
    import tempfile
    fails = []
    body = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "from engine import PySh4, RETURN_VA\n"
        "e = PySh4(endian='little')\n"
        "words = [0xE105, 0x7101, 0x000B, 0x0009]\n"   # mov #5,r1; add #1,r1; rts; nop
        "e.map('c', 0x8C000000, b''.join(w.to_bytes(2, 'little') for w in words), 'rx')\n"
        "e.set_regs(pc=0x8C000000, pr=RETURN_VA)\n"
        "e.run_until(None, 100)\n"
        "sys.exit(0 if e.get_regs()['r1'] == 6 else 3)\n" % HERE)
    with tempfile.TemporaryDirectory() as tmp:
        script = os.path.join(tmp, "probe.py")
        with open(script, "w") as fh:
            fh.write(body)
        counts, sites = collections.Counter(), {}
        code = run_tool([script], counts, sites)
        if code != 0:
            fails.append("probe exit %r" % code)
        want = {"mov_imm": 1, "add_imm": 1, "rts": 1, "nop": 1}
        if dict(counts) != want:
            fails.append("counts %r != %r" % (dict(counts), want))
        buf = io.StringIO()
        if report(counts, sites, ["mac.l"], 0, out=buf):
            fails.append("mac.l reported as executed")
        if not report(counts, sites, ["add_imm"], 0, out=io.StringIO()):
            fails.append("add_imm not reported as executed")
        if engine_plain.PySh4._execute.__name__ == "wrapped":
            fails.append("wrapper not removed")
    for line in fails:
        print("FAIL", line)
    print("arm_census selftest: %s" % ("OK" if not fails else "FAILED"))
    return 0 if not fails else 1


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return selftest()
    if "--" not in argv:
        print(__doc__)
        return 2
    split = argv.index("--")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--form", action="append", default=[])
    ap.add_argument("--top", type=int, default=0)
    ap.add_argument("--fail-if-executed", action="store_true")
    args = ap.parse_args(argv[:split])
    tool = argv[split + 1:]
    if not tool:
        ap.error("no tool after --")
    counts, sites = collections.Counter(), {}
    code = run_tool(tool, counts, sites)
    hit = report(counts, sites, args.form, args.top)
    print("tool exit code %r" % code)
    if args.fail_if_executed and hit:
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
