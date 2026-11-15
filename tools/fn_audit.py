#!/usr/bin/env python3
"""Audit every cited ``fn 0x…`` / ``sub_…`` VA against the module's `.pdata`.

H51/H52 found that three VAs the board and docs called functions are in fact
12–18 bytes inside a function (``0x0041c7e8``, ``0x00412bee``, ``0x00542256``):
a search for such an address finds nothing, and an L3 call that enters after
the prologue runs with a wrong stack frame.  This tool turns "is this VA a
function start?" into a failing command.

It does not decode anything itself: the function table comes from
``tools/pdata.py`` (``load_table`` / ``locate`` / ``gaps``), so the record
format and the leaf-caller heuristic have one implementation only.

Corpora (``--scope docs``, the M1.25 scope):
  * ``docs/format/*.md`` and ``TODO.md`` — every ``fn 0x…`` / ``sub_…``;
  * ``tools/l3_harness/targets.json`` — firmware ``entry.va`` values;
  * ``tools/*_l3.py`` — every ``0x…`` constant that lands in a pdata span.

A VA is resolved to a build (A ``0x200200`` / B ``0x3e00200`` / C ``0x5200200``
of the same image) and a module when the module's pdata span
``[first, last_end]`` contains it.  The strongest class across those holders
wins: ``START`` > ``INSIDE`` > ``GAP``.  ``GAP`` is not an error — a leaf
function has no record — so a gap is refined with ``pdata.gaps`` (a direct
``bsr``/``jsr``/pool caller makes it ``leaf``, otherwise ``DATA/UNKNOWN``).
Two holders that agree on the rank but disagree on the true start are
``AMBIGUOUS``; a constant outside every span is ``UNMAPPED`` and is not an
error (generic bit patterns such as ``0x40001000``).

Usage:
  fn_audit.py IMG [--scope docs] [--fix-list] [--cache DIR] [--quiet]
  fn_audit.py --selftest

Exit codes: 0 no mid-function citation, 1 any ``INSIDE`` (or an ``AMBIGUOUS``
whose candidates include one), 2 usage/image error, 3 the image has no build
A (nothing to audit).  ``--fix-list`` prints one sorted ``0x<mid> -> 0x<start>``
line per ``INSIDE`` VA and changes no file.
"""

import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cerom  # noqa: E402
import pdata  # noqa: E402

REPO = os.path.dirname(HERE)
BUILD_A = 0x200200
BUILDS = (0x200200, 0x3e00200, 0x5200200)
BUILD_NAME = {0x200200: "A", 0x3e00200: "B", 0x5200200: "C"}
RANK = {"START": 3, "INSIDE": 2, "GAP": 1}

FN_RE = re.compile(r"\b(fn|sub_)\s?(0x[0-9a-fA-F]{6,8})\b")
SUB_RE = re.compile(r"\bsub_([0-9a-fA-F]{6,8})\b")
CONST_RE = re.compile(r"0x[0-9a-fA-F]{6,8}\b")
BARE_RE = re.compile(r"0x[0-9a-fA-F]{6,8}\b")
CORRECTION_RE = re.compile(r"mid-function|not (?:a )?function|(?:->|→)\s*(?:fn|sub_)")

DOC_FILES = ("TODO.md", "docs/format/*.md")
TARGETS = "tools/l3_harness/targets.json"
L3_GLOB = "tools/*_l3.py"


class Citation:
    __slots__ = ("va", "where", "kind")

    def __init__(self, va, where, kind):
        self.va = va
        self.where = where
        self.kind = kind

    def __repr__(self):
        return "Citation(0x%08x, %s, %s)" % (self.va, self.where, self.kind)


def _line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def citations_markdown(paths):
    """``fn``/``sub_`` VAs from prose files, one Citation per occurrence."""
    for path in paths:
        text = open(path, encoding="utf-8", errors="replace").read()
        rel = os.path.relpath(path, REPO)
        hits = [(m.start(), int(m.group(2), 16), m.group(1))
                for m in FN_RE.finditer(text)]
        hits += [(m.start(), int(m.group(1), 16), "sub_")
                 for m in SUB_RE.finditer(text)
                 if not FN_RE.match(text, m.start())]
        prefixed = {pos for pos, _va, _kind in hits}
        # A line that corrects a label often cites the correct and the wrong VA
        # side by side (``0x00542256`` -> ``fn 0x00542250``); keep a bare VA
        # only on a line that carries a correction marker, so ordinary code
        # addresses in the same prose do not flood the audit.
        marked_lines = {_line_of(text, m.start()) for m in CORRECTION_RE.finditer(text)}
        for m in BARE_RE.finditer(text):
            if m.start() in prefixed or _line_of(text, m.start()) not in marked_lines:
                continue
            hits.append((m.start(), int(m.group(0), 16), "ctx"))
        for pos, va, kind in sorted(set(hits)):
            yield Citation(va, "%s:%d" % (rel, _line_of(text, pos)), kind)


def citations_targets(path):
    """Firmware-call entry VAs from the L3 target list (synthetic ones skipped)."""
    doc = json.load(open(path, encoding="utf-8"))
    rel = os.path.relpath(path, REPO)
    for target in doc.get("targets", []):
        entry = target.get("entry") or {}
        if entry.get("kind") != "firmware_call":
            continue
        va = entry.get("va")
        if not va:
            continue
        yield Citation(int(va, 16), "%s:%s" % (rel, target.get("name", "?")), "target")


def citations_l3_constants(paths):
    """Every 0x… constant in the ``*_l3.py`` programs (filtered by span later)."""
    for path in paths:
        rel = os.path.relpath(path, REPO)
        for lineno, line in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
            for m in CONST_RE.finditer(line):
                yield Citation(int(m.group(0), 16), "%s:%d" % (rel, lineno), "const")


def collect(scope="docs"):
    """(citations, files_scanned) for the requested scope."""
    if scope != "docs":
        raise SystemExit("fn_audit: scope %r is not implemented here; --scope l3 is M1.26" % scope)
    files = []
    md = [os.path.join(REPO, p) for p in DOC_FILES]
    md = [p for pattern in md for p in sorted(glob.glob(pattern))]
    files.extend(md)
    files.append(os.path.join(REPO, TARGETS))
    l3 = sorted(glob.glob(os.path.join(REPO, L3_GLOB)))
    files.extend(l3)
    cites = list(citations_markdown(md))
    cites.extend(citations_targets(os.path.join(REPO, TARGETS)))
    cites.extend(citations_l3_constants(l3))
    return cites, [os.path.relpath(p, REPO) for p in files]


# --------------------------------------------------------------------------
# Classification (pure: works on injected tables, so the selftest needs no image)
# --------------------------------------------------------------------------


class Table:
    """One build's module -> pdata records, with the span precomputed."""

    __slots__ = ("build", "modules")

    def __init__(self, build, modules):
        self.build = build
        self.modules = {}
        for name, records in modules.items():
            if not records:
                continue
            first = records[0][0]
            last = records[-1][0] + records[-1][2]
            self.modules[name] = (records, first, last)

    def holders(self, va):
        """[(module, records)] whose pdata span contains ``va``."""
        out = []
        for name, (records, first, last) in self.modules.items():
            if first <= va <= last:
                out.append((name, records))
        return out


class Verdict:
    __slots__ = ("va", "klass", "start", "module", "build", "leaf", "candidates")

    def __init__(self, va, klass, start=None, module=None, build=None,
                 leaf=None, candidates=()):
        self.va = va
        self.klass = klass
        self.start = start
        self.module = module
        self.build = build
        self.leaf = leaf
        self.candidates = list(candidates)

    @property
    def is_failure(self):
        if self.klass == "INSIDE":
            return True
        return self.klass == "AMBIGUOUS" and any(c[2] == "INSIDE" for c in self.candidates)

    def label(self):
        if self.klass == "INSIDE":
            return "INSIDE 0x%08x" % self.start
        if self.klass == "GAP":
            return "GAP(%s)" % ("leaf" if self.leaf else "DATA/UNKNOWN")
        return self.klass


def classify(tables, va, leaf_lookup=None):
    """Best-class verdict for ``va`` across ``tables`` (list of Table).

    ``leaf_lookup(module, build, va)`` -> True/False/None refines a GAP; with
    no lookup a gap is reported as ``GAP(?)``.
    """
    hits = []
    for table in tables:
        for module, records in table.holders(va):
            kind, rec = pdata.locate(records, va)
            hits.append((table.build, module, kind, rec[0] if rec else None))
    if not hits:
        return Verdict(va, "UNMAPPED")
    best = max(RANK[h[2]] for h in hits)
    top = [h for h in hits if RANK[h[2]] == best]
    starts = {h[3] for h in top}
    if len(starts) > 1:
        return Verdict(va, "AMBIGUOUS", candidates=[(BUILD_NAME[h[0]], h[1], h[2], h[3]) for h in hits])
    build, module, kind, start = top[0]
    leaf = None
    if kind == "GAP":
        leaf = leaf_lookup(module, build, va) if leaf_lookup else None
    return Verdict(va, kind, start=start, module=module, build=build, leaf=leaf,
                   candidates=[(BUILD_NAME[h[0]], h[1], h[2], h[3]) for h in hits] if len(hits) > 1 else [])


# --------------------------------------------------------------------------
# Real-image driver
# --------------------------------------------------------------------------


class Image:
    """The three build contexts of one image, with a lazy per-module gap cache."""

    def __init__(self, path, cache_dir=None):
        self.data = open(path, "rb").read(128 << 20)
        self.cache_dir = cache_dir
        self.tables = []
        self._gaps = {}
        for start in BUILDS:
            try:
                rom = cerom.CERom(self.data, start)
                modules = {}
                for mod in rom.modules():
                    records = pdata.table_or_none(self.data, start, mod["name"], cache_dir)
                    if records:
                        modules[mod["name"]] = records
            except Exception:  # noqa: BLE001 - a missing build is reported, not fatal
                continue
            self.tables.append(Table(start, modules))

    def leaf_of(self, module, build, va):
        key = (build, module)
        if key not in self._gaps:
            try:
                rows, _meta = pdata.gaps(self.data, build, module, self.cache_dir)
            except Exception:  # noqa: BLE001 - no table -> not a leaf claim
                rows = []
            self._gaps[key] = rows
        row = next((r for r in self._gaps[key] if r["start"] <= va < r["end"]), None)
        return bool(row and row["leaf"])


def audit(cites, image):
    """Classify every citation; drop UNMAPPED constants (generic bit patterns)."""
    verdicts = []
    seen = {}
    for cite in cites:
        if cite.va not in seen:
            seen[cite.va] = classify(image.tables, cite.va, image.leaf_of)
        verdicts.append((cite, seen[cite.va]))
    keep = []
    for cite, verdict in verdicts:
        if verdict.klass == "UNMAPPED" and cite.kind in ("const", "ctx"):
            continue
        keep.append((cite, verdict))
    return keep


def stats(cites, kept):
    unique = {c.va for c in cites}
    counts = {}
    for _cite, verdict in kept:
        counts[verdict.klass] = counts.get(verdict.klass, 0) + 1
    unmapped = sum(1 for c in cites if c.kind in ("const", "ctx")) - sum(
        1 for cite, _v in kept if cite.kind in ("const", "ctx"))
    return unique, counts, unmapped


def report(kept, files, cites, unique, counts, unmapped, quiet=False, verbose=False):
    advisory = 0
    if not quiet:
        for cite, verdict in kept:
            print("0x%08x  %-32s  %-18s  %-12s  %s"
                  % (verdict.va, cite.where, verdict.label(),
                     verdict.module or "-", BUILD_NAME.get(verdict.build, "-")))
            if verdict.klass == "AMBIGUOUS":
                for cand in verdict.candidates:
                    print("            candidate %s %s %s 0x%08x"
                          % (cand[0], cand[1], cand[2], cand[3] or 0))
            elif verdict.candidates:
                advisory += 1
                if verbose:
                    for cand in verdict.candidates:
                        print("            also %s %s %s 0x%08x"
                              % (cand[0], cand[1], cand[2], cand[3] or 0))
    if advisory and not verbose:
        print("fn_audit: %d citation(s) whose VA is also INSIDE another build/module "
              "(shown with --verbose)" % advisory)
    gaps = [v for _c, v in kept if v.klass == "GAP"]
    leaf = sum(1 for v in gaps if v.leaf)
    print("fn_audit: %d file(s) scanned, %d citation(s), %d unique VA(s)"
          % (len(files), len(cites), len(unique)))
    print("fn_audit: START %d, INSIDE %d, GAP %d (leaf %d), AMBIGUOUS %d, UNMAPPED %d"
          % (counts.get("START", 0), counts.get("INSIDE", 0), len(gaps), leaf,
             counts.get("AMBIGUOUS", 0), unmapped))


def fix_list(kept, unique):
    """One ``0x<mid> -> 0x<start>`` line per INSIDE VA, sorted, no prose."""
    rows = {}
    for _cite, verdict in kept:
        if verdict.klass == "INSIDE":
            rows[verdict.va] = verdict.start
    return ["0x%08x -> 0x%08x" % (va, rows[va]) for va in sorted(rows)]


# --------------------------------------------------------------------------
# Selftest (no image, no vendor bytes)
# --------------------------------------------------------------------------


def _synth_records(*spans):
    return [(begin, 0x10, length) for begin, length in spans]


def selftest():
    fails = []

    def check(name, cond):
        print("%s %s" % ("ok  " if cond else "FAIL", name))
        if not cond:
            fails.append(name)

    table = Table(BUILD_A, {
        "synth.dll": _synth_records((0x401000, 0x40), (0x401040, 0x20), (0x401100, 0x30)),
        "other.dll": _synth_records((0x500000, 0x100)),
    })
    tables = [table]
    lookup = {
        (0x401080, "synth.dll"): True,    # a gap with a direct caller (leaf)
        (0x401060, "synth.dll"): False,   # a gap nobody calls (data)
    }
    leaf_lookup = lambda module, build, va: lookup.get((va, module))

    check("START", classify(tables, 0x401040).klass == "START")
    ins = classify(tables, 0x401048)
    check("INSIDE carries the true start", ins.klass == "INSIDE" and ins.start == 0x401040)
    gap_leaf = classify(tables, 0x401080, leaf_lookup)
    check("GAP leaf", gap_leaf.klass == "GAP" and gap_leaf.leaf is True)
    gap_data = classify(tables, 0x401060, leaf_lookup)
    check("GAP data", gap_data.klass == "GAP" and gap_data.leaf is False)
    check("BEFORE (below the first record is UNMAPPED, never a guess)",
          classify(tables, 0x400800).klass == "UNMAPPED")
    amb = classify([table, Table(0x3e00200, {
        "synth.dll": _synth_records((0x401030, 0x80))})], 0x401048)
    check("AMBIGUOUS (two INSIDE starts)",
          amb.klass == "AMBIGUOUS" and amb.is_failure
          and {c[3] for c in amb.candidates} == {0x401040, 0x401030})
    check("AMBIGUOUS with a START candidate is not a failure",
          not classify([table, Table(0x3e00200, {
              "synth.dll": _synth_records((0x401048, 0x40))})], 0x401048).is_failure)
    check("UNMAPPED", classify(tables, 0x900000).klass == "UNMAPPED")
    check("INSIDE is a failure", ins.is_failure)
    check("START is not a failure", not classify(tables, 0x401040).is_failure)

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        md = os.path.join(tmp, "doc.md")
        with open(md, "w", encoding="utf-8") as fh:
            fh.write("see fn 0x0041c7e8 and sub_004e989c and `sub_ 0x00542256`\n"
                     "and fn 0x004125a8 twice: fn 0x004125a8\n")
        got = [(c.va, c.kind) for c in citations_markdown([md])]
        check("markdown extractor", got == [
            (0x0041c7e8, "fn"), (0x004e989c, "sub_"), (0x00542256, "sub_"),
            (0x004125a8, "fn"), (0x004125a8, "fn")])
        tj = os.path.join(tmp, "t.json")
        json.dump({"targets": [
            {"name": "fw", "entry": {"kind": "firmware_call", "va": "0x0041c7e8"}},
            {"name": "syn", "entry": {"kind": "synthetic", "va": "0x8c100000"}},
        ]}, open(tj, "w", encoding="utf-8"))
        check("targets extractor skips synthetic",
              [(c.va, c.kind) for c in citations_targets(tj)] == [(0x0041c7e8, "target")])
        l3 = os.path.join(tmp, "x_l3.py")
        with open(l3, "w", encoding="utf-8") as fh:
            fh.write("A = 0x0041c802\nB = 0x40001000\nC = 0xffffffff\n")
        check("constant extractor",
              [c.va for c in citations_l3_constants([l3])] == [0x0041c802, 0x40001000, 0xFFFFFFFF])

    bad = Verdict(0x401048, "INSIDE", start=0x401040)
    good = Verdict(0x401040, "START", start=0x401040)
    check("fix-list format", fix_list([(None, good), (None, bad)], {0x401048}) ==
          ["0x00401048 -> 0x00401040"])
    check("fix-list skips non-INSIDE", fix_list([(None, good)], {0x401040}) == [])

    print("selftest: %s (%d failed)" % ("OK" if not fails else "FAIL", len(fails)))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("image", nargs="?", help="256 MiB firmware head (e.g. archive/head256.img)")
    ap.add_argument("--scope", default="docs", choices=("docs",))
    ap.add_argument("--fix-list", action="store_true",
                    help="print one '0x<mid> -> 0x<start>' line per INSIDE VA")
    ap.add_argument("--cache", default=pdata.DEFAULT_CACHE,
                    help="decoded-pdata cache directory (default %(default)s)")
    ap.add_argument("--quiet", action="store_true", help="summary and --fix-list only")
    ap.add_argument("--verbose", action="store_true",
                    help="also list the other build/module holders of a VA")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.image:
        ap.print_help()
        return 2
    try:
        image = Image(args.image, args.cache)
    except OSError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if not image.tables or not image.tables[0].modules:
        print("error: no build A function tables in %s" % args.image, file=sys.stderr)
        return 3
    cites, files = collect(args.scope)
    kept = audit(cites, image)
    unique, counts, unmapped = stats(cites, kept)
    failing = [v for _c, v in kept if v.is_failure]
    if args.fix_list:
        # Machine-readable on purpose: one sorted line per INSIDE VA, no prose.
        for line in fix_list(kept, unique):
            print(line)
        return 1 if failing else 0
    report(kept, files, cites, unique, counts, unmapped, quiet=args.quiet,
           verbose=args.verbose)
    lines = []
    if failing:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
