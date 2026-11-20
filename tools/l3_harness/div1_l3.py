#!/usr/bin/env python3
"""Run the firmware's own ``div1`` divide routines on PySh4 (M9.48).

M9.48 models ``div0s``/``div0u``/``div1`` (SR.M, SR.Q, T) in
``l3_harness/engine.py``.  The engine self-test checks the manual's divide
sequences; this tool checks the model against the *firmware's* divide code:

* **sites** -- every ``div1`` halfword in the pdata-covered code of a module,
  split into *chain* functions (at least ``--min-div1`` ``div1``, a
  ``div0u``/``div0s`` and a ``rotcl`` next to a ``div1``: a real unrolled
  divide) and *scattered* halfwords (everything else, typically literal-pool
  data that happens to have the ``0x3nm4`` shape).
* **run** -- call each chain function (or ``--fn VA``) with ``(r4, r5)``
  operand pairs and report which of ``udiv``/``urem``/``sdiv``/``srem`` (C
  semantics: truncating division, remainder takes the dividend's sign) the
  returned ``r0`` matches on *every* pair.  A chain function that matches no
  oracle is a failure (exit 1).  ``--mq-blind`` runs the negative control: a
  ``div1`` that ignores M/Q must make the matches go away.

``rotcl``/``rotcr`` are modelled by the engine since M9.50.  The tool-local
shim that ran them for M9.48 is kept only as a fallback for an engine that
rejects them (``IllegalInstruction``), and ``run`` prints how many times it
fired: ``rotcl(shim)=0 rotcr(shim)=0`` means every instruction ran in the
bare engine.

The divisor-zero path of the routines calls an exception helper and is not
exercised (no pair has ``r5 == 0``).

* **isolate** -- run every non-FPU halfword once on the engine *before* the
  change (``--before``, e.g. ``git show REV:tools/l3_harness/engine.py``) and
  on the current one, from four register states, and list the forms whose
  outcome (registers, 4 KiB of memory, delay slot, or exception) differs.
  Anything outside ``--expect`` (default ``div0s,div0u,div1``) is a
  failure (exit 1).

Usage:
  div1_l3.py isolate --before PATH [--expect FORM,...]
  div1_l3.py sites IMG MODULE [--image-start 0x3e00200] [--min-div1 8]
  div1_l3.py run   IMG MODULE [--image-start 0x3e00200] [--fn VA ...]
                              [--mq-blind]
  div1_l3.py --selftest

A function that stops on an FPU instruction is reported ``SKIP`` (FPU is
out of scope and has its own census bucket), not as a failure.

Exit codes: 0 ok, 1 a runnable chain function matched no oracle (or, with
``--mq-blind``, every one still matched), 2 usage / module not found.
"""

from __future__ import annotations

import argparse
import sys
import os

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import cerom          # noqa: E402
import pdata          # noqa: E402
from l3_harness import engine  # noqa: E402

M32 = 0xFFFFFFFF
STACK_VA = 0x7F000000
STACK_SIZE = 0x1000


def is_div1(w):
    return w & 0xF00F == 0x3004


def is_div0(w):
    return w == 0x0019 or w & 0xF00F == 0x2007


def is_rotcl(w):
    return w & 0xF0FF == 0x4024


# --------------------------------------------------------------------------
# sites
# --------------------------------------------------------------------------

def functions(data, image_start, module):
    """``[(begin, [halfwords])]`` for every readable pdata record, and the
    module's executable sections as ``[(base, blob)]``."""
    rom = cerom.CERom(data, image_start)
    mod = rom.module(module)
    records, _meta = pdata.load_table(data, image_start, module)
    sections = [(base, blob) for _i, base, blob in pdata.exec_sections(rom, mod)]
    out = []
    for begin, _prolog, length in records:
        for base, blob in sections:
            if base <= begin and begin + length <= base + len(blob):
                chunk = blob[begin - base:begin - base + length]
                words = [chunk[i] | (chunk[i + 1] << 8)
                         for i in range(0, len(chunk) // 2 * 2, 2)]
                out.append((begin, words))
                break
    return out, sections


def classify_sites(funcs, min_div1=8):
    """Split div1 halfwords into chain functions and scattered halfwords."""
    chains = []
    scattered = 0
    for begin, words in funcs:
        idx = [i for i, w in enumerate(words) if is_div1(w)]
        if not idx:
            continue
        rot_adjacent = any(
            is_rotcl(words[j]) for i in idx
            for j in (i - 1, i + 1) if 0 <= j < len(words))
        div0 = sum(1 for w in words if is_div0(w))
        if len(idx) >= min_div1 and div0 and rot_adjacent:
            chains.append({"fn": begin, "div1": len(idx),
                           "div0u": words.count(0x0019),
                           "div0s": sum(1 for w in words if w & 0xF00F == 0x2007),
                           "length": 2 * len(words)})
        else:
            scattered += len(idx)
    return chains, scattered


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------

COUNTED = ("div0s", "div0u", "div1", "rotcl", "rotcr")


class ShimSh4(engine.PySh4):
    """PySh4 that counts the div/rotc forms run; a ``rotcl``/``rotcr`` the
    engine rejects falls back to a tool-local shim (counted separately)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.counts = {"rotcl(shim)": 0, "rotcr(shim)": 0}
        self.counts.update((name, 0) for name in COUNTED)

    def _execute(self, insn, pc):
        # Not every engine arm names itself; clear the label so a stale one
        # from the previous instruction is never counted twice.
        self._arm = None
        try:
            super()._execute(insn, pc)
        except engine.IllegalInstruction:
            if insn & 0xF0FE != 0x4024:
                raise
            self._shim_rotc(insn)
            return
        if self._arm in self.counts:
            self.counts[self._arm] += 1

    def _shim_rotc(self, insn):
        reg = "r%d" % ((insn >> 8) & 0xF)
        value = self._regs[reg]
        t = 1 if self._t() else 0
        if insn & 1:                                 # rotcr Rn
            self._regs[reg] = (value >> 1) | (t << 31)
            self._set_t(value & 1)
            name = "rotcr(shim)"
        else:                                        # rotcl Rn
            self._regs[reg] = ((value << 1) | t) & M32
            self._set_t(value >> 31)
            name = "rotcl(shim)"
        self._arm = name
        self.counts[name] += 1


ORACLES = (
    ("udiv", lambda a, b: (a // b) & M32),
    ("urem", lambda a, b: (a % b) & M32),
    ("sdiv", lambda a, b: _sdiv(a, b) & M32),
    ("srem", lambda a, b: (_s(a) - _sdiv(a, b) * _s(b)) & M32),
)


def _s(v):
    return v - (1 << 32) if v & 0x80000000 else v


def _sdiv(a, b):
    a, b = _s(a), _s(b)
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


#: Operand pairs (r4, r5): every sign case, extremes, exact and inexact.
PAIRS = tuple((a & M32, b & M32) for a, b in (
    (100, 7), (-100, 7), (100, -7), (-100, -7), (7, 100), (-7, 100),
    (0, 5), (12345678, 1000), (-12345678, 1000), (12345678, -1000),
    (0x7FFFFFFF, 2), (-0x80000000, 3), (-0x80000000, -2), (0x7FFFFFFF, -1),
    (0xFFFFFFFF, 1), (0xFFFFFFFF, 0xFFFFFFFF), (0x80000000, 0x10),
    (1000, 0x7FFFFFFF), (99, 33), (-99, 33),
))


def build_engine(sections):
    eng = ShimSh4(endian="little")
    for i, (base, blob) in enumerate(sections):
        eng.map("sec%d" % i, base, bytes(blob), "rx")
    eng.map("stack", STACK_VA, STACK_SIZE, "rw")
    return eng


def run_fn(sections, fn, pairs=PAIRS, max_insns=2000):
    """Call *fn* on every pair; return ``(matches, results, counts, error)``."""
    eng = build_engine(sections)
    results = []
    error = None
    for a, b in pairs:
        eng.set_regs(r15=STACK_VA + STACK_SIZE - 0x100, sr=0)
        try:
            eng.set_regs(pc=fn, pr=engine.RETURN_VA, r4=a, r5=b)
            eng.run_until(max_insns=max_insns)
        except engine.EngineError as exc:
            error = "%s: %s" % (type(exc).__name__, exc)
            break
        results.append(eng.get_regs()["r0"])
    matches = []
    if error is None:
        for name, oracle in ORACLES:
            if all(r == oracle(a, b) for r, (a, b) in zip(results, pairs)):
                matches.append(name)
    return matches, results, dict(eng.counts), error


# --------------------------------------------------------------------------
# isolate: no other instruction changed
# --------------------------------------------------------------------------

#: Register states every halfword runs from (sr covers T/S/Q/M on and off).
STATES = (
    {"sr": 0x00000000, "seed": 0x01234567},
    {"sr": 0x00000303, "seed": 0x89ABCDEF},
    {"sr": 0x40000101, "seed": 0x80000001},
    {"sr": 0x00000200, "seed": 0x7FFFFFFE},
)


def _one(mod, word, state):
    """Run *word* once on engine module *mod*; return a comparable outcome."""
    eng = mod.PySh4(endian="little")
    eng.map("c", 0x1000, 0x100, "rwx")
    eng.map("d", 0x8C000000, 0x1000, "rw")
    regs = {"r%d" % i: (0x8C000400 + 16 * i) for i in range(16)}
    regs["r0"] = state["seed"]
    regs["r1"] = state["seed"] ^ 0xFFFFFFFF
    regs.update(pc=0x1000, sr=state["sr"], gbr=0x8C000800, mach=0x11,
                macl=0x22, pr=0x1040)
    eng.set_regs(**regs)
    try:
        eng._execute(word, 0x1000)
    except Exception as exc:  # noqa: BLE001 - a host-side crash is an outcome too
        return ("raise", type(exc).__name__)
    return ("ok", tuple(sorted(eng.get_regs().items())),
            bytes(eng.read_mem(0x8C000000, 0x1000)), eng._delay)


def isolate(before, after, words=range(0x10000)):
    """Forms (by the *after* engine's table) whose outcome differs."""
    changed = {}
    for w in words:
        if (w >> 12) == 0xF:
            continue
        for state in STATES:
            if _one(before, w, state) != _one(after, w, state):
                form = after.decode_fields(w)[0]
                changed[form] = changed.get(form, 0) + 1
                break
    return changed


def load_module(path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("div1_l3_before", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["div1_l3_before"] = module
    spec.loader.exec_module(module)
    return module


def cmd_isolate(args):
    before = load_module(args.before)
    changed = isolate(before, engine)
    allowed = set(f for f in args.expect.split(",") if f)
    print("halfwords run  %d (FPU 0xF000-0xFFFF excluded), %d register states"
          % (0xF000, len(STATES)))
    for form in sorted(changed):
        print("changed %-12s %5d halfwords%s"
              % (form, changed[form], "" if form in allowed else "  UNEXPECTED"))
    extra = sorted(set(changed) - allowed)
    print("result: %s" % ("only %s changed" % "/".join(sorted(allowed))
                          if not extra
                          else "OTHER FORMS CHANGED: " + ", ".join(extra)))
    return 1 if extra else 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _load(args):
    with open(args.image, "rb") as fh:
        data = fh.read()
    try:
        return functions(data, args.image_start, args.module)
    except KeyError:
        print("module %r not found at image start 0x%x"
              % (args.module, args.image_start), file=sys.stderr)
        raise SystemExit(2)


def cmd_sites(args):
    funcs, _sections = _load(args)
    chains, scattered = classify_sites(funcs, args.min_div1)
    total = sum(c["div1"] for c in chains) + scattered
    print("module          %s @ 0x%x" % (args.module, args.image_start))
    print("pdata functions %d read" % len(funcs))
    print("div1 halfwords  %d (chain %d in %d functions, scattered %d)"
          % (total, total - scattered, len(chains), scattered))
    for c in chains:
        print("chain fn 0x%08x len %4d div1 %2d div0u %d div0s %d"
              % (c["fn"], c["length"], c["div1"], c["div0u"], c["div0s"]))
    return 0


def cmd_run(args):
    funcs, sections = _load(args)
    if args.fn:
        targets = [int(v, 0) for v in args.fn]
    else:
        targets = [c["fn"] for c in classify_sites(funcs, args.min_div1)[0]]
    saved = engine._div1_step
    if args.mq_blind:
        real = saved
        engine._div1_step = lambda rn, rm, t, q, m: real(rn, rm, t, 0, 0)
    try:
        print("module %s @ 0x%x, %d operand pairs, div1 %s"
              % (args.module, args.image_start, len(PAIRS),
                 "M/Q-BLIND (negative control)" if args.mq_blind else "engine"))
        unmatched = 0
        skipped = 0
        for fn in targets:
            matches, _res, counts, error = run_fn(sections, fn)
            if error and "FPU instruction" in error:
                # Out of M9.48's scope (FPU is a census bucket of its own).
                print("fn 0x%08x  SKIP  %s" % (fn, error))
                skipped += 1
                continue
            if error:
                print("fn 0x%08x  STOP  %s" % (fn, error))
                unmatched += 1
                continue
            print("fn 0x%08x  match=%-10s div0s=%d div0u=%d div1=%d "
                  "rotcl=%d rotcr=%d rotcl(shim)=%d rotcr(shim)=%d"
                  % (fn, ",".join(matches) or "NONE", counts["div0s"],
                     counts["div0u"], counts["div1"], counts["rotcl"],
                     counts["rotcr"], counts["rotcl(shim)"],
                     counts["rotcr(shim)"]))
            if not matches:
                unmatched += 1
        runnable = len(targets) - skipped
        print("result: %d/%d runnable functions match an oracle "
              "(%d skipped: FPU)" % (runnable - unmatched, runnable, skipped))
    finally:
        engine._div1_step = saved
    if args.mq_blind:
        return 0 if runnable and unmatched == runnable else 1
    return 1 if unmatched or not runnable else 0


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------

def _synthetic_udiv():
    """A little-endian unsigned-divide leaf in the firmware's shape:
    ``mov #0,r2; div0u; 32 x (rotcl r4; div1 r5,r2); rotcl r4; rts; mov r4,r0``."""
    words = [0xE200, 0x0019]
    for _ in range(32):
        words += [0x4424, 0x3254]
    words += [0x4424, 0x000B, 0x6043]
    return b"".join(w.to_bytes(2, "little") for w in words), words


def selftest():
    fails = []

    def check(label, got, want):
        if got != want:
            fails.append("%s: got %r want %r" % (label, got, want))

    blob, words = _synthetic_udiv()
    base = 0x8C001000
    sections = [(base, blob)]
    chains, scattered = classify_sites(
        [(base, words), (base + 0x1000, [0x0001, 0x3624, 0x0001])])
    check("sites: one chain", [c["fn"] for c in chains], [base])
    check("sites: chain div1", chains[0]["div1"], 32)
    check("sites: scattered data-shaped div1", scattered, 1)

    matches, _r, counts, error = run_fn(sections, base)
    check("run: no stop", error, None)
    check("run: synthetic udiv matches udiv only", matches, ["udiv"])
    check("run: div1 count", counts["div1"], 32 * len(PAIRS))
    check("run: rotcl in the engine", counts["rotcl"], 33 * len(PAIRS))
    check("run: rotcl shim never fired (M9.50)", counts["rotcl(shim)"], 0)

    saved = engine._div1_step
    real = saved
    engine._div1_step = lambda rn, rm, t, q, m: real(rn, rm, t, 0, 0)
    try:
        blind, _r, _c, _e = run_fn(sections, base)
    finally:
        engine._div1_step = saved
    check("negative control: Q-blind div1 matches nothing", blind, [])

    # isolate: the engine against itself changes nothing; a copy whose div1
    # is M/Q-blind changes div1 only.
    sample = (0x0009, 0x0019, 0x2B67, 0x3624, 0x3104, 0x6043, 0xE200, 0x4424)
    check("isolate: engine vs itself", isolate(engine, engine, sample), {})

    class _Blind:
        pass
    blind_mod = _Blind()
    blind_mod.__dict__.update(engine.__dict__)

    class _BlindSh4(engine.PySh4):
        def _execute(self, insn, pc):
            if insn & 0xF00F == 0x3004:
                self._regs["sr"] &= ~(engine.SR_M | engine.SR_Q)
            super()._execute(insn, pc)
    blind_mod.PySh4 = _BlindSh4
    check("isolate: M/Q-blind div1 copy differs on div1 only",
          sorted(isolate(blind_mod, engine, sample)), ["div1"])

    # Oracles on C semantics.
    check("oracle sdiv -100/7", dict(ORACLES)["sdiv"](-100 & M32, 7), -14 & M32)
    check("oracle srem -100/7", dict(ORACLES)["srem"](-100 & M32, 7), -2 & M32)
    check("oracle srem 100/-7", dict(ORACLES)["srem"](100, -7 & M32), 2)

    for line in fails:
        print("FAIL", line)
    print("div1_l3 selftest: %s" % ("OK" if not fails else "FAILED"))
    return 0 if not fails else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true",
                        help="run the synthetic self-test and exit")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("isolate")
    p.add_argument("--before", required=True,
                   help="engine.py before the change (e.g. git show REV:...)")
    p.add_argument("--expect", default="div0s,div0u,div1",
                   help="comma-separated forms the change may touch "
                        "(default: the M9.48 set; M9.49: mac.w)")
    for name in ("sites", "run"):
        p = sub.add_parser(name)
        p.add_argument("image")
        p.add_argument("module")
        p.add_argument("--image-start", type=lambda s: int(s, 0),
                       default=0x3E00200)
        p.add_argument("--min-div1", type=int, default=8)
        if name == "run":
            p.add_argument("--fn", action="append", default=[])
            p.add_argument("--mq-blind", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "isolate":
        return cmd_isolate(args)
    if args.cmd == "sites":
        return cmd_sites(args)
    if args.cmd == "run":
        return cmd_run(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        raise SystemExit(selftest())
    raise SystemExit(main())
