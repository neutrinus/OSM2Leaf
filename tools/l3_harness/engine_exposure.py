#!/usr/bin/env python3
"""Did an L3 run execute any instruction the engine now runs differently? (M9.36)

An engine fix changes recorded L3 results only if the run executed an
instruction whose outcome differs between the old and the new engine.  This
tool answers that per run, without trusting the code reading:

1. ``changed``: every non-FPU halfword is run once on the *before* engine
   (an ``engine.py`` file, e.g. ``git show 116c826:tools/l3_harness/engine.py``)
   and once on the current one, from the four register states of
   ``div1_l3.isolate``; a halfword whose outcome (registers, memory, delay
   slot, or raised exception) differs in any state is *changed*.
2. ``run``: the tool after ``--`` runs as ``__main__`` with
   ``PySh4._execute`` wrapped (as in ``arm_census.py``); every executed
   halfword is counted, and the report lists the executed halfwords that are
   in the changed set, by form, with their first sites.

Because PySh4 is deterministic, a run that executes **no** changed halfword
takes the same path and produces the same values on the before engine as on
the current one (same tool, same inputs): its recorded result cannot have
been produced by the old defects.  A run with ``exposed > 0`` must be
compared with its recorded number (or re-run on the old engine).

Wrapping ``_execute`` turns the M9.45 fast path off for the run (stepped
engine; same results, C-5322), so a run is about ten times slower.

Usage:
  engine_exposure.py changed --before ENGINE.py [--before ENGINE2.py ...] [--cache JSON]
  engine_exposure.py run --before ENGINE.py [...] [--cache JSON] [--json OUT] -- TOOL.py ARGS...

``--before`` may be repeated (every engine a recorded run may have used);
the changed set is then the union over all of them.
  engine_exposure.py static --before ENGINE.py [--cache JSON] IMAGE --module M --image-start S
                     [--length VA=LEN ...] VA...
  engine_exposure.py --selftest

``static`` answers the same question for a run that cannot be repeated (its
script was never committed): it lists the changed halfwords in the code
from each VA up to ``VA+LEN`` (``--length``, e.g. a pdata length) or, for a
leaf without a record, up to the first ``rts`` and its delay slot.  It is a
bound on the straight-line code, not the executed path.

Exit code of ``run``: the tool's own exit code.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for path in (HERE, TOOLS):
    if path not in sys.path:
        sys.path.insert(0, path)

import engine as engine_plain              # noqa: E402
from l3_harness import engine as engine_pkg  # noqa: E402
import div1_l3                              # noqa: E402


def changed_words(before, after=engine_plain, words=range(0xF000)):
    """``{word: form}`` for every halfword whose outcome differs."""
    out = {}
    for w in words:
        if (w >> 12) == 0xF:
            continue
        for state in div1_l3.STATES:
            if div1_l3._one(before, w, state) != div1_l3._one(after, w, state):
                out[w] = after.decode_fields(w)[0]
                break
    return out


def load_changed(before_paths, cache: str | None):
    """Union of the changed sets of every *before* engine (cached as JSON)."""
    key = [os.path.abspath(p) for p in before_paths]
    if cache and os.path.exists(cache):
        with open(cache) as fh:
            doc = json.load(fh)
        if doc.get("before") == key:
            return {int(k, 16): v for k, v in doc["changed"].items()}
    changed = {}
    for i, path in enumerate(before_paths):
        before = div1_l3.load_module(path) if i == 0 else _load_as(path, i)
        changed.update(changed_words(before))
    if cache:
        with open(cache, "w") as fh:
            json.dump({"before": key,
                       "changed": {"%04x" % k: v for k, v in sorted(changed.items())}},
                      fh, indent=0)
    return changed


def _load_as(path: str, i: int):
    import importlib.util
    name = "engine_exposure_before_%d" % i
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def install(words: collections.Counter, sites: dict):
    """Wrap ``PySh4._execute`` in both engine modules; return an undo."""
    saved = []
    for mod in {id(engine_plain): engine_plain, id(engine_pkg): engine_pkg}.values():
        cls = mod.PySh4
        orig = cls._execute

        def wrapped(self, insn, pc, _orig=orig):
            words[insn] += 1
            words[(insn, pc >> 24)] += 1
            per = sites.get(insn)
            if per is None:
                per = sites[insn] = collections.Counter()
            if len(per) < 16 or pc in per:
                per[pc & 0xFFFFFFFF] += 1
            return _orig(self, insn, pc)

        cls._execute = wrapped
        saved.append((cls, orig))

    def undo():
        for cls, orig in saved:
            cls._execute = orig
    return undo


def run_tool(argv, words, sites) -> int:
    undo = install(words, sites)
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


def summarise(words, sites, changed):
    total = sum(n for w, n in words.items() if isinstance(w, int))
    by_form = collections.Counter()
    by_area = collections.Counter()
    form_sites = {}
    for w, n in words.items():
        if isinstance(w, tuple):
            if w[0] in changed:
                by_area["%02x" % w[1]] += n
            continue
        form = changed.get(w)
        if form is None:
            continue
        by_form[form] += n
        fs = form_sites.setdefault(form, collections.Counter())
        for pc, k in sites.get(w, {}).items():
            fs["%#010x:%04x" % (pc, w)] += k
    return {
        "executed": total,
        "distinct_words": sum(1 for w in words if isinstance(w, int)),
        "exposed": sum(by_form.values()),
        "exposed_by_va_top_byte": dict(sorted(by_area.items())),
        "forms": {f: {"count": n, "sites": dict(sorted(form_sites[f].items())[:8])}
                  for f, n in by_form.most_common()},
    }


def print_summary(doc, out=sys.stdout):
    print("engine_exposure: executed %d instructions (%d distinct halfwords)"
          % (doc["executed"], doc["distinct_words"]), file=out)
    print("engine_exposure: exposed %d (executed halfwords whose outcome changed)"
          % doc["exposed"], file=out)
    if doc["exposed"]:
        print("engine_exposure: exposed by VA top byte %s" % ", ".join(
            "0x%sxxxxxx=%d" % kv for kv in doc["exposed_by_va_top_byte"].items()), file=out)
    for form, row in doc["forms"].items():
        where = ", ".join("%s x%d" % kv for kv in row["sites"].items())
        print("  %-22s %10d  at %s" % (form, row["count"], where), file=out)


def static_scan(mem_u16, va: int, changed, length: int | None = None, cap: int = 4096):
    """``(halfwords scanned, [(va, word, form)])`` from *va* to *va+length*
    or to the first ``rts`` plus its delay slot."""
    hits, n, stop = [], 0, None
    end = va + length if length else va + 2 * cap
    a = va
    while a < end:
        w = mem_u16(a)
        if w is None:
            break
        n += 1
        if w in changed:
            hits.append((a, w, changed[w]))
        if stop is not None and a >= stop:
            break
        if length is None and w == 0x000B and stop is None:
            stop = a + 2
        a += 2
    return n, hits


# --------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------

def selftest() -> int:
    import io
    import tempfile
    import types
    fails = []

    # A "before" engine whose mov.w R0,@(disp,Rn) stores through r0 (the
    # H51 defect shape), built by subclassing the current engine.
    class _Old(engine_plain.PySh4):
        def _exec_branch8(self, insn, n, m, pc):
            if (insn >> 8) == 0x81:
                base = self._regs["r0"]
                self._store((base + (insn & 0xF) * 2) & 0xFFFFFFFF, 2,
                            self._regs["r0"] & 0xFFFF)
                self._arm = "mov.w_r0_at_disp_m"
                return
            return super()._exec_branch8(insn, n, m, pc)
    old = types.SimpleNamespace(PySh4=_Old)
    sample = [0xE105, 0x8114, 0x8014, 0x6013, 0x0009]
    got = changed_words(old, words=sample)
    if set(got) != {0x8114}:
        fails.append("changed set %r != {0x8114}" % sorted(map(hex, got)))
    if changed_words(engine_plain, words=sample):
        fails.append("negative control: current vs current is not empty")

    body = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "from engine import PySh4, RETURN_VA\n"
        "e = PySh4(endian='little')\n"
        # mov #5,r2 (unchanged form); mov.w r0,@(4,r1) twice; rts; nop
        "words = [0xE205, 0x8112, 0x8112, 0x000B, 0x0009]\n"
        "e.map('c', 0x8C000000, b''.join(w.to_bytes(2, 'little') for w in words), 'rx')\n"
        "e.map('d', 0x8C100000, 0x100, 'rw')\n"
        "e.set_regs(pc=0x8C000000, pr=RETURN_VA, r1=0x8C100000, r0=7)\n"
        "e.run_until(None, 100)\n"
        "sys.exit(0 if e.read_mem(0x8C100004, 2) == b'\\x07\\x00' else 3)\n" % HERE)
    with tempfile.TemporaryDirectory() as tmp:
        script = os.path.join(tmp, "probe.py")
        with open(script, "w") as fh:
            fh.write(body)
        words, sites = collections.Counter(), {}
        code = run_tool([script], words, sites)
        if code != 0:
            fails.append("probe exit %r" % code)
        plain = {k: v for k, v in words.items() if isinstance(k, int)}
        if plain != {0xE205: 1, 0x8112: 2, 0x000B: 1, 0x0009: 1}:
            fails.append("words %r" % {hex(k): v for k, v in plain.items()})
        doc = summarise(words, sites, {0x8112: "mov.w_r0_at_disp_m"})
        if (doc["exposed"] != 2 or list(doc["forms"]) != ["mov.w_r0_at_disp_m"]
                or doc["exposed_by_va_top_byte"] != {"8c": 2} or doc["executed"] != 5):
            fails.append("summary %r" % doc)
        if summarise(words, sites, {0x8114: "x"})["exposed"] != 0:
            fails.append("unexecuted changed word counted")
        print_summary(doc, out=io.StringIO())
        code = {0x100: 0x8112, 0x102: 0x000B, 0x104: 0x8113, 0x106: 0x8114}
        n, hits = static_scan(code.get, 0x100, {0x8112: "a", 0x8113: "b", 0x8114: "c"})
        if n != 3 or [h[0] for h in hits] != [0x100, 0x104]:
            fails.append("static leaf scan %r %r" % (n, hits))
        n, hits = static_scan(code.get, 0x100, {0x8114: "c"}, length=8)
        if n != 4 or [h[0] for h in hits] != [0x106]:
            fails.append("static length scan %r %r" % (n, hits))
        if engine_plain.PySh4._execute.__name__ == "wrapped":
            fails.append("wrapper not removed")
    for line in fails:
        print("FAIL", line)
    print("engine_exposure selftest: %s" % ("OK" if not fails else "FAILED"))
    return 0 if not fails else 1


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return selftest()
    tool = []
    if "--" in argv:
        split = argv.index("--")
        argv, tool = argv[:split], argv[split + 1:]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="run the synthetic self-test")
    ap.add_argument("cmd", choices=["changed", "run", "static"])
    ap.add_argument("image", nargs="?")
    ap.add_argument("vas", nargs="*")
    ap.add_argument("--module", default="Navi.exe")
    ap.add_argument("--image-start", default="0x200200")
    ap.add_argument("--length", action="append", default=[], help="VA=LEN")
    ap.add_argument("--before", action="append", required=True,
                    help="engine.py before the change (repeat: union of changed sets)")
    ap.add_argument("--cache", help="JSON cache of the changed set")
    ap.add_argument("--json", help="write the run summary here")
    args = ap.parse_args(argv)
    changed = load_changed(args.before, args.cache)
    if args.cmd == "changed":
        forms = collections.Counter(changed.values())
        print("changed halfwords %d (FPU excluded), %d states"
              % (len(changed), len(div1_l3.STATES)))
        for form, n in sorted(forms.items()):
            print("  %-22s %5d" % (form, n))
        return 0
    if args.cmd == "static":
        import sh4dis
        if not args.image or not args.vas:
            ap.error("static needs IMAGE and at least one VA")
        mem, _segs, _sections = sh4dis.load_segments(
            args.image, int(args.image_start, 0), args.module)
        lengths = {int(k, 0): int(v, 0) for k, v in (x.split("=") for x in args.length)}
        total = 0
        for text in args.vas:
            va = int(text, 0)
            n, hits = static_scan(mem.u16, va, changed, lengths.get(va))
            total += len(hits)
            print("%s 0x%08x: %d halfwords scanned (%s), changed %d%s" % (
                args.module, va, n, "length 0x%x" % lengths[va] if va in lengths
                else "to first rts", len(hits),
                "".join("\n  0x%08x %04x %s" % h for h in hits)))
        print("static: %d changed halfword(s) in %d function(s)" % (total, len(args.vas)))
        return 0
    if not tool:
        ap.error("run needs a tool after --")
    words, sites = collections.Counter(), {}
    code = run_tool(tool, words, sites)
    doc = summarise(words, sites, changed)
    doc["tool"] = tool
    doc["exit"] = code
    print_summary(doc)
    print("tool exit code %r" % code)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(doc, fh, indent=1)
    return code


if __name__ == "__main__":
    sys.exit(main())
