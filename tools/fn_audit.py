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

The M1.26 l3 overlay (``--scope l3``) is the wider gate corpus, frozen into
its own snapshot so the docs base stays readable:
  * ``tools/l3_harness/targets.json`` — firmware ``entry.va`` values;
  * ``docs/format/firmware.md`` — every ``fn 0x…`` / ``sub_…``;
  * ``docs/experiments/EXP-*.md`` — parsed only (append-only, never written);
  * every ``0x…`` in an **open** ``TODO.md`` task block (``- [ ] **ID`` to the
    end of that block), as a bare ``l3`` citation.
A corpus without a parser is reported ``NOT SCANNED`` with the reason, never
guessed.  The overlay snapshot is
``docs/research/fn-audit-l3-corpus-2026-11-16.json``; ``--corpus`` takes an
optional ``overlay`` object and runs the H69 policy **per source**.

A VA is resolved to a build (A ``0x200200`` / B ``0x3e00200`` / C ``0x5200200``
of the same image) and a module when the module's pdata span
``[first, last_end]`` contains it.  The strongest class across those holders
wins: ``START`` > ``INSIDE`` > ``GAP``.  ``GAP`` is not an error — a leaf
function has no record — so a gap is refined with ``pdata.gaps`` (a direct
``bsr``/``jsr``/pool caller makes it ``leaf``, otherwise ``DATA/UNKNOWN``).
Two holders that agree on the rank but disagree on the true start are
``AMBIGUOUS``; a constant outside every span is ``UNMAPPED`` and is not an
error (generic bit patterns such as ``0x40001000``).

A *correction* is not a failure (M1.29).  Prose that records a fix pairs the
wrong VA with its true start (``0x00542256 → fn 0x00542250``,
``0x003f5fc2`→`0x003f5f48``).  When a correction line keeps a bare VA as a
``ctx`` citation and that VA's own pair names a start equal to
``pdata.locate``'s start, the citation is ``CORRECTED`` — an ``INSIDE`` the
line itself resolves.  The pair attaches only to the VA it names, so a repeated
bare ``0x…`` later on the same line does not inherit it (M1.25 feedback).  A VA
whose every occurrence in the corpus is correction prose but which never spells
the true start on its own line (a start on a neighbouring line, a ``jsr`` call
site) is covered by the explicit, commented ``CORRECTION_ONLY`` allowlist, and
only while the pin still matches the image.  A live label (``fn 0x…``,
``sub_…``, ``target``, ``const``) is never corrected by either path — the same
VA can be ``CORRECTED`` on one line and ``INSIDE`` on another, so the verdict
is per citation.

Usage:
  fn_audit.py IMG [--scope docs|l3] [--fix-list] [--cache DIR] [--quiet]
  fn_audit.py IMG --scope docs|l3 --write-snapshot PATH
  fn_audit.py IMG --corpus PATH [--overlay PATH] [--no-live-check] [--fix-list]
  fn_audit.py --selftest

Exit codes: 0 no unresolved mid-function citation, 1 any ``INSIDE`` (or an
``AMBIGUOUS`` whose candidates include one), 2 usage/image error, 3 the image
has no build A (nothing to audit).  ``--fix-list`` prints one sorted
``0x<mid> -> 0x<start>`` line per ``INSIDE`` VA and changes no file.

A frozen corpus (M1.30) is a committed JSON snapshot written once by
``--write-snapshot`` (one ``{file,line,va,kind,class,true_start}`` row per
citation plus the exact summary the writer printed and the image's SHA-256).
``--corpus`` takes the same image and re-derives every row's class from
``.pdata`` — the frozen part is only ``file/line/va/kind`` — and by default
also compares the snapshot against a live ``--scope docs`` scan.  A source
line that moved without changing its ``(file,va,kind,class)`` identity is
``CORPUS DRIFT``: it warns and exits 0 (H69, line moves are prose).  A line
that was added or removed, or a verdict change at an unchanged key, is
``CORPUS STALE`` and exits 1.  The standing gate (M1.26) runs on the
snapshot so board prose cannot move the counts; a diff to the snapshot is the
review artefact.

With ``--overlay PATH`` the l3 snapshot is read beside the docs base and each
source gets its own live comparison and its own H69 verdict: a moved-only
change in either layer warns and exits 0; ``new``/``gone``/a count delta/a
verdict change in either layer is ``CORPUS STALE`` and exits 1.  The summary
names both totals so an l3 line move can never fold into the docs ``moved``
count, and an ``AMBIGUOUS`` row in the overlay exercises H72's candidate-set
comparison.
"""

import argparse
import glob
import hashlib
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
# A correction pair names the true start next to the bare VA it corrects:
# ``0x00542256 → fn 0x00542250`` or the Precheck style
# ``0x003f5fc2`→`0x003f5f48`` (arrow, optional ``fn``/``sub_``, backticks/spaces
# free).  A cross-build mapping (``0x0041c7dc→0x00444540``) is not a correction
# because the named start is not ``pdata.locate``'s start for the left VA.
CORRECTION_PAIR_RE = re.compile(
    r"0x([0-9a-fA-F]{6,8})(`?)\s*`?\s*(?:->|→)\s*`?\s*(?:fn|sub_)?\s?"
    r"0x([0-9a-fA-F]{6,8})\b")
# Pairs whose left-hand VA was not a ``fn``/``sub_`` label but a call site or
# an address range (``0x00419684`→`sub_00419350`` is a correction;
# ``0x00419462-0x00419468`` is a range).  The tight form requires the arrow to
# touch the left VA through backticks, which is how a corrected label is
# written (``0x003f5fc2`→`0x003f5f48``).
CORRECTION_PAIR_TIGHT_RE = re.compile(
    r"0x([0-9a-fA-F]{6,8})`\s*`?(?:->|→)\s*`?\s*(?:fn|sub_)?\s?"
    r"0x([0-9a-fA-F]{6,8})\b")

DOC_FILES = ("TODO.md", "docs/format/*.md")
TARGETS = "tools/l3_harness/targets.json"
L3_GLOB = "tools/*_l3.py"
FIRMWARE_DOC = "docs/format/firmware.md"
EXP_GLOB = "docs/experiments/EXP-*.md"
OPEN_TASK_RE = re.compile(r"^- \[ \] \*\*[A-Za-z0-9]")

# Bare VAs whose every remaining occurrence is correction prose that does not
# spell the true start on that same line (the M1.29 Stop clause: an explicit,
# commented allowlist beats a regex that can hide a real mislabel).  These are
# never function labels: a live ``fn 0x…``/``sub_…``/target/const citation of
# the same VA is still classified and still fails.  True starts are pinned by
# the selftest fixture so a wrong entry is visible, and `--verbose` prints the
# allowlist in use.
CORRECTION_ONLY = {
    0x003F5FC2: "H49 range end; its true start `0x003f5f48` is on a different line",
    0x00413AF4: "`jsr` instruction at the call site inside `fn 0x00413a6c`",
    0x00542256: "H51/H52 non-start; true start `0x00542250`",
}

# Starts in the US 2011 `Navi.exe`, not the EU head this audit classifies
# against.  The US build is a different binary (C-3487): `0x0035d894` is its
# entry and the CMP chain sits at `0x00444540…`, so classifying these against
# the EU `.pdata` reports a valid US address as an EU ``INSIDE`` (M1.26
# blocker 2).  Every entry is a verified US start, not a range guess: the
# M1.28 fixture's US side (C-3740/C-3703) plus M1.22b's six pool-only twins
# (C-3622).  The EU→US table lives in `docs/format/firmware.md` ("EU→US
# function matches"); a per-module build map is `build` in
# `tools/l3_harness/targets.json`, and a per-module census over every US
# module is still the follow-up M1.22 asks for.
US_BUILD_STARTS = frozenset({
    0x0035D894,  # US Navi.exe entry (C-3487)
    0x00444540,  # CMP chunk engine          (EU 0x0041c7dc)
    0x004446F4,  # CMP chunk-table loop      (EU 0x0041c990)
    0x00443DA8,  # CMP/.ind opener           (EU 0x0041c044)
    0x0041EC8C,  # POI name accessor         (EU 0x003f632c)
    0x0056454C,  # zlib purge                (EU 0x00542250)
    # M1.22b: the six readers whose masked instruction-form stream is unique
    # in the US build (C-3622). Same form stream, moved literal pool.
    0x0044219C,  # MMAIN                  (EU 0x0041a438)
    0x004410B4,  # DRSTR                  (EU 0x00419350)
    0x0043A378,  # REFER access path      (EU 0x004125a8)
    0x00433458,  # ADDRE0 resolve         (EU 0x0040b358)
    0x003EC274,  # RDSTM                  (EU 0x003bc960)
    0x0041EB1C,  # POI field accessor     (EU 0x003f61bc)
})


class Citation:
    __slots__ = ("va", "where", "kind", "correction")

    def __init__(self, va, where, kind, correction=None):
        self.va = va
        self.where = where
        self.kind = kind
        self.correction = correction

    def __repr__(self):
        return "Citation(0x%08x, %s, %s)" % (self.va, self.where, self.kind)


def _line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def citations_markdown(paths, strict=False):
    """``fn``/``sub_`` VAs from prose files, one Citation per occurrence.

    ``strict`` is the l3 discipline (M1.26 navigator): on a correction-marker
    line a bare VA is a ``ctx`` only when its own arrow pair names a start or
    it is a documented ``CORRECTION_ONLY`` pin.  A bare VA that merely shares a
    line with an arrow (a call site such as ``0x003f2d34 jsr @r3 ->
    sub_003f06a8``, where the arrow is the callee) is not a correction and is
    skipped, and a US-build start is skipped for every kind.  The docs base
    keeps the old rule (``strict=False``) so its frozen snapshot is unchanged.
    """
    for path in paths:
        text = open(path, encoding="utf-8", errors="replace").read()
        rel = os.path.relpath(path, REPO)
        hits = [(m.start(), int(m.group(2), 16), m.group(1), None)
                for m in FN_RE.finditer(text)
                if int(m.group(2), 16) not in US_BUILD_STARTS]
        hits += [(m.start(), int(m.group(1), 16), "sub_", None)
                 for m in SUB_RE.finditer(text)
                 if not FN_RE.match(text, m.start())
                 and int(m.group(1), 16) not in US_BUILD_STARTS]
        prefixed = {pos for pos, _va, _kind, _corr in hits}
        # A line that corrects a label keeps every bare VA as a ``ctx`` citation
        # (M1.25 rule), and each bare VA carries the true start its *own* pair
        # names.  Both pair forms require an arrow, so a range
        # (``0x00419462-0x00419468``) and a call chain
        # (``0x0041c044 → 0x0041c990``) are not pairs; a cross-build map
        # (``0x0041c7dc→0x00444540``) is a pair shape whose named start is not
        # the left VA's ``pdata.locate`` start, so it resolves to nothing.
        offset = 0
        for line in text.split("\n"):
            pairs = {}
            for m in CORRECTION_PAIR_RE.finditer(line):
                pairs.setdefault(m.start(), int(m.group(3), 16))
            for m in CORRECTION_PAIR_TIGHT_RE.finditer(line):
                pairs.setdefault(m.start(), int(m.group(2), 16))
            if CORRECTION_RE.search(line):
                for m in BARE_RE.finditer(line):
                    pos = offset + m.start()
                    if pos in prefixed:
                        continue
                    va = int(m.group(0), 16)
                    corr = pairs.get(m.start())
                    if va in US_BUILD_STARTS:
                        continue
                    if strict and corr is None and va not in CORRECTION_ONLY:
                        continue
                    hits.append((pos, va, "ctx", corr))
            offset += len(line) + 1
        for pos, va, kind, correction in sorted(hits):
            yield Citation(va, "%s:%d" % (rel, _line_of(text, pos)), kind,
                           correction=correction)


def _open_blocks(lines):
    """(start, end) line spans of the open ``TODO.md`` task blocks.

    Shared by ``citations_open_tasks`` and ``open_block_counts`` so the
    reported block count and the scanned span cannot drift apart.
    """
    starts = [i for i, line in enumerate(lines) if OPEN_TASK_RE.match(line)]
    blocks = []
    for start in starts:
        end = start + 1
        while (end < len(lines)
               and not OPEN_TASK_RE.match(lines[end])
               and not lines[end].startswith("- [")
               and not lines[end].startswith("## ")):
            end += 1
        blocks.append((start, end))
    return blocks


def open_block_counts(text, cites=None):
    """(open blocks, contributing blocks, citation lines) for the open TODOs.

    A block is the span ``citations_open_tasks`` scans, counted **before** any
    kind filter; a contributing block yields at least one citation.  The 61
    open-block citations of M1.26 come from 18 contributing blocks but sit on
    35 citation lines, so "blocks" and "lines" are not interchangeable.
    """
    lines = text.split("\n")
    blocks = _open_blocks(lines)
    if cites is None:
        cites = list(citations_open_tasks(text))
    contributing = set()
    for cite in cites:
        _file, _, line = cite.where.rpartition(":")
        if not line.isdigit():
            continue
        lineno = int(line) - 1
        for index, (start, end) in enumerate(blocks):
            if start <= lineno < end:
                contributing.add(index)
                break
    return len(blocks), len(contributing), len({c.where for c in cites})


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


def citations_open_tasks(text):
    """``fn``/``sub_`` labels, correction ``ctx`` and pins in an open block.

    A block runs from ``- [ ] **<ID>`` to the next block header or section
    boundary.  Closed blocks, prose above the first block, and headings are
    out of scope: this is the "open task blocks" corpus of M1.26.

    The block is scanned with the **docs discipline**, not "every hex token":
    a bare ``0x…`` is cited only when it is a correction the block itself
    documents, and a bare data address, path offset, range or US-build VA is
    not a function citation (M1.26 navigator: the bare-hex rule turned a data
    reference nobody can "fix" into a gate failure).  Concretely a VA is cited
    when it is

    * prefixed ``fn``/``sub_`` — a live label, so it still fails if mid-function;
    * on a correction-marker line — a ``ctx`` with its own arrow pair, exactly
      as ``citations_markdown`` does (so ``0xMID → fn 0xSTART`` is ``CORRECTED``);
    * a documented ``CORRECTION_ONLY`` pin — a ``ctx`` that ``_resolved`` can
      resolve against the pinned start even when the line names no start.

    Everything else is skipped, and a US-build VA is skipped for every kind
    (it is not a start in the EU head this gate classifies against).
    """
    lines = text.split("\n")
    for start, end in _open_blocks(lines):
        for lineno in range(start, end):
            line = lines[lineno]
            pairs = {}
            for m in CORRECTION_PAIR_RE.finditer(line):
                pairs.setdefault(m.start(), int(m.group(3), 16))
            for m in CORRECTION_PAIR_TIGHT_RE.finditer(line):
                pairs.setdefault(m.start(), int(m.group(2), 16))
            marked = bool(CORRECTION_RE.search(line))
            for m in BARE_RE.finditer(line):
                va = int(m.group(0), 16)
                if va in US_BUILD_STARTS:
                    # A US-build start is not a start in the EU head this
                    # image classifies against; citing it here would label a
                    # valid US address as an EU ``INSIDE`` (M1.26 blocker 2).
                    continue
                # A live ``fn``/``sub_`` label keeps its failure class, exactly
                # as in ``citations_markdown``.  On a correction-marker line
                # every bare VA is a ``ctx`` with its own pair (M1.29), so a
                # block that records ``0xMID → fn 0xSTART`` is ``CORRECTED``
                # and the same VA used as an unpaired target still fails.
                prefix = line[:m.start()]
                if re.search(r"(?:fn|sub_)\s?$", prefix):
                    kind = "sub_" if prefix.rstrip().endswith("sub_") else "fn"
                    corr = None
                elif marked or va in CORRECTION_ONLY:
                    # A pin is a documented correction even when its line
                    # names no start (H63); ``_resolved`` still requires the
                    # pinned start to match the image, so a live label beside
                    # it and a stale pin both stay failures.
                    kind, corr = "ctx", pairs.get(m.start())
                else:
                    continue
                yield Citation(va, "TODO.md:%d" % (lineno + 1), kind,
                               correction=corr)


def collect_l3():
    """(citations, files_scanned, not_scanned) for the M1.26 l3 overlay.

    Four corpora, each with a reproducible parser.  A path that does not exist
    is reported in ``not_scanned`` rather than silently yielding nothing.
    """
    files, not_scanned, cites = [], [], []

    targets = os.path.join(REPO, TARGETS)
    if os.path.exists(targets):
        files.append(targets)
        cites.extend(citations_targets(targets))
    else:
        not_scanned.append("%s: file missing" % TARGETS)

    firmware = os.path.join(REPO, FIRMWARE_DOC)
    if os.path.exists(firmware):
        files.append(firmware)
        cites.extend(citations_markdown([firmware], strict=True))
    else:
        not_scanned.append("%s: file missing" % FIRMWARE_DOC)

    exps = sorted(glob.glob(os.path.join(REPO, EXP_GLOB)))
    if exps:
        files.extend(exps)
        cites.extend(citations_markdown(exps, strict=True))
    else:
        not_scanned.append("%s: no EXP records" % EXP_GLOB)

    todo = os.path.join(REPO, "TODO.md")
    if os.path.exists(todo):
        files.append(todo)
        cites.extend(citations_open_tasks(open(todo, encoding="utf-8").read()))
    else:
        not_scanned.append("TODO.md: file missing")

    return cites, [os.path.relpath(p, REPO) for p in files], not_scanned


def collect(scope="docs"):
    """(citations, files_scanned[, not_scanned]) for the requested scope."""
    if scope == "l3":
        return collect_l3()
    if scope != "docs":
        raise SystemExit("fn_audit: scope %r is not supported" % scope)
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
        if self.klass == "CORRECTED":
            return "CORRECTED 0x%08x" % self.start
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
    """Classify every citation, including ``UNMAPPED`` const/ctx rows.

    ``UNMAPPED`` is not an error (a generic constant outside every span), but
    M1.30's snapshot must carry every citation so ``--corpus`` can re-render the
    exact ``UNMAPPED n`` summary the writer printed; dropping them here made the
    two summaries disagree.
    """
    verdicts = []
    seen = {}
    for cite in cites:
        if cite.va not in seen:
            seen[cite.va] = classify(image.tables, cite.va, image.leaf_of)
        verdict = seen[cite.va]
        if (verdict.klass == "INSIDE" and cite.kind == "ctx"
                and _resolved(cite, verdict, image)):
            verdict = Verdict(verdict.va, "CORRECTED", start=verdict.start,
                              module=verdict.module, build=verdict.build,
                              candidates=verdict.candidates)
        verdicts.append((cite, verdict))
    return verdicts


def _resolved(cite, verdict, image):
    """Is this bare citation a correction the line itself resolves?

    Two ways, in order.  (1) The line pairs the VA with a start that equals
    ``pdata.locate``'s (``0x00542256 → fn 0x00542250``).  (2) The VA is on the
    explicit ``CORRECTION_ONLY`` allowlist and still resolves to the pinned
    start — the allowlist is prose about a fix whose target sits on another
    line.  A ``fn 0x…``/``sub_…``/target/const citation never takes either
    path; that is what keeps a live mislabel failing.
    """
    if cite.correction is not None:
        return cite.correction == verdict.start
    pinned = CORRECTION_ONLY.get(cite.va)
    if pinned is None:
        return False
    return "0x%08x" % verdict.start in pinned


def stats(cites, kept):
    unique = {c.va for c in cites}
    counts = {}
    for _cite, verdict in kept:
        counts[verdict.klass] = counts.get(verdict.klass, 0) + 1
    # Every ``UNMAPPED`` citation counts as unmapped regardless of kind:
    # ``snapshot_summary`` counts rows, so the live writer must use the same
    # rule or an l3 overlay row (kind ``l3``/``fn``) would make the frozen and
    # live summaries disagree (M1.26).  The docs corpus is unchanged because
    # all 32 of its unmapped citations are ``const``.
    unmapped = sum(1 for _cite, verdict in kept
                   if verdict.klass == "UNMAPPED")
    return unique, counts, unmapped


def summary_counts(files, cites, unique, counts, unmapped, kept):
    """The exact numbers ``report`` prints, as a dict (M1.30 freezes these)."""
    gaps = [v for _c, v in kept if v.klass == "GAP"]
    return {
        "files": len(files),
        "citations": len(cites),
        "unique_va": len(unique),
        "start": counts.get("START", 0),
        "inside": counts.get("INSIDE", 0),
        "corrected": counts.get("CORRECTED", 0),
        "gap": len(gaps),
        "leaf": sum(1 for v in gaps if v.leaf),
        "ambiguous": counts.get("AMBIGUOUS", 0),
        "unmapped": unmapped,
    }


def summary_lines(summary):
    """The two-line summary, identical for a live run and ``--corpus``."""
    return [
        "fn_audit: %d file(s) scanned, %d citation(s), %d unique VA(s)"
        % (summary["files"], summary["citations"], summary["unique_va"]),
        "fn_audit: START %d, INSIDE %d, CORRECTED %d, GAP %d (leaf %d), "
        "AMBIGUOUS %d, UNMAPPED %d"
        % (summary["start"], summary["inside"], summary["corrected"],
           summary["gap"], summary["leaf"], summary["ambiguous"],
           summary["unmapped"]),
    ]


def report(kept, files, cites, unique, counts, unmapped, quiet=False, verbose=False):
    advisory = 0
    if not quiet:
        for cite, verdict in kept:
            if verdict.klass == "UNMAPPED" and cite.kind in ("const", "ctx"):
                continue  # generic bit patterns: counted, not listed (as before)
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
    for line in summary_lines(summary_counts(files, cites, unique, counts,
                                            unmapped, kept)):
        print(line)
    if verbose and CORRECTION_ONLY:
        for va in sorted(CORRECTION_ONLY):
            print("fn_audit: CORRECTION_ONLY 0x%08x  (%s)" % (va, CORRECTION_ONLY[va]))
    only = corrected_only(kept)
    if only:
        print("fn_audit: correction-only (no live label): %s"
              % ", ".join("0x%08x" % va for va in only))


def fix_list(kept, unique):
    """One ``0x<mid> -> 0x<start>`` line per INSIDE VA, sorted, no prose."""
    rows = {}
    for _cite, verdict in kept:
        if verdict.klass == "INSIDE":
            rows[verdict.va] = verdict.start
    return ["0x%08x -> 0x%08x" % (va, rows[va]) for va in sorted(rows)]


def corrected_only(kept):
    """Allowlisted VAs that appear only as resolved corrections in the corpus."""
    inside = {v.va for _c, v in kept if v.klass == "INSIDE"}
    return [va for va in sorted(CORRECTION_ONLY) if va not in inside]


# --------------------------------------------------------------------------
# Frozen corpus snapshot (M1.30): write once, audit the file, never re-scan
# --------------------------------------------------------------------------

SNAPSHOT_VERSION = 1
# A snapshot row keeps only what the gate needs to re-render the verdict; the
# citation *kind* is stored so a hand-added ``const``/``ctx`` row is treated
# like a live one when the tool recomputes ``unmapped``.
SNAPSHOT_CLASSES = ("START", "INSIDE", "CORRECTED", "GAP", "AMBIGUOUS", "UNMAPPED")


def _split_where(where):
    """``TODO.md:42`` -> ``("TODO.md", 42)``; a target row keeps ``file:name``."""
    file, _, rest = where.rpartition(":")
    if rest.isdigit():
        return file, int(rest)
    return where, 0


def _row_class(verdict):
    """The class token a snapshot stores (leaf is a separate counter)."""
    return verdict.klass


def _row_start(verdict):
    if verdict.klass in ("INSIDE", "CORRECTED") and verdict.start is not None:
        return "0x%08x" % verdict.start
    return None


def snapshot_rows(kept):
    """One ``{file,line,va,kind,class,true_start}`` row per kept citation.

    ``GAP`` rows add ``leaf``, ``AMBIGUOUS`` rows add ``candidates``, and a
    ``ctx`` row keeps the ``correction`` start its own line pairs it with, so
    ``--corpus`` can re-derive the verdict from the image instead of trusting
    the stored ``class``.
    """
    rows = []
    for cite, verdict in kept:
        file, line = _split_where(cite.where)
        row = {
            "file": file,
            "line": line,
            "va": "0x%08x" % verdict.va,
            "kind": cite.kind,
            "class": _row_class(verdict),
            "true_start": _row_start(verdict),
            "class_sha256": row_fingerprint(_row_class(verdict),
                                            _row_start(verdict)),
        }
        if cite.correction is not None:
            row["correction"] = "0x%08x" % cite.correction
        if verdict.klass == "GAP":
            row["leaf"] = bool(verdict.leaf)
        if verdict.klass == "AMBIGUOUS":
            row["candidates"] = [list(c) for c in verdict.candidates]
        rows.append(row)
    rows.sort(key=lambda r: (r["file"], r["line"], r["va"], r["kind"]))
    return rows


def write_snapshot(path, files, rows, summary, image_path, scope="docs",
                   not_scanned=None):
    doc = {
        "tool": "fn_audit",
        "snapshot_version": SNAPSHOT_VERSION,
        "scope": scope,
        "image": os.path.basename(image_path) if image_path else None,
        "image_sha256": image_sha256(image_path),
        "files": sorted(files),
        "summary": summary,
        "rows": rows,
    }
    if not_scanned:
        doc["not_scanned"] = list(not_scanned)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, sort_keys=False)
        fh.write("\n")
    os.replace(tmp, path)
    return doc


def image_sha256(path):
    if not path:
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _image_sha_or_error(path):
    """``(sha, None)`` for a readable image, ``(None, 2)`` with the live
    path's own wording for a missing one (H88).

    ``image_sha256`` opens the file, so on a checkout without the image the
    ``--corpus`` path used to die with a ``FileNotFoundError`` traceback while
    the live path printed ``error: [Errno 2] No such file or directory: …`` and
    returned 2.  Routing both through the same wording keeps
    ``tools/gate.py``'s ``no such file or directory: 'archive/`` SKIP marker
    meaningful for a direct caller, not just through the gate.
    """
    try:
        return image_sha256(path), None
    except OSError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return None, 2


def load_corpus(path):
    """The snapshot document, validated to the row schema ``--corpus`` needs."""
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if doc.get("tool") != "fn_audit":
        raise ValueError("not an fn_audit snapshot: tool=%r" % doc.get("tool"))
    if doc.get("snapshot_version") != SNAPSHOT_VERSION:
        raise ValueError("unsupported snapshot_version %r (want %d)"
                         % (doc.get("snapshot_version"), SNAPSHOT_VERSION))
    rows = doc.get("rows")
    if not isinstance(rows, list):
        raise ValueError("snapshot has no rows list")
    for i, row in enumerate(rows, 1):
        missing = [k for k in ("file", "line", "va", "kind", "class", "class_sha256")
                   if k not in row]
        if missing:
            raise ValueError("row %d missing %s" % (i, ", ".join(missing)))
        if row["class"] not in SNAPSHOT_CLASSES:
            raise ValueError("row %d has unknown class %r" % (i, row["class"]))
        try:
            int(row["va"], 16)
        except (TypeError, ValueError):
            raise ValueError("row %d has a non-hex va %r" % (i, row["va"]))
        # An AMBIGUOUS row's verdict is its whole candidate set, so the gate
        # cannot tell "unchanged" from "absent": require the key rather than
        # silently comparing an empty set (H72 Stop condition).
        if row["class"] == "AMBIGUOUS" and not isinstance(
                row.get("candidates"), list):
            raise ValueError("row %d is AMBIGUOUS without a candidates list"
                             % i)
    if not doc.get("image_sha256"):
        raise ValueError("snapshot has no image_sha256; --corpus re-classifies "
                         "each row against the image, so the image is required")
    return doc


def snapshot_summary(doc):
    """Re-render the summary purely from the frozen rows (no image, no docs)."""
    rows = doc["rows"]
    counts = singleton_class_counts(rows)
    leaf = sum(1 for r in rows if r["class"] == "GAP" and r.get("leaf"))
    return {
        "files": len(doc.get("files") or []),
        "citations": len(rows),
        "unique_va": len({_canon_va(r["va"]) for r in rows}),
        "start": counts.get("START", 0),
        "inside": counts.get("INSIDE", 0),
        "corrected": counts.get("CORRECTED", 0),
        "gap": counts.get("GAP", 0),
        "leaf": leaf,
        "ambiguous": counts.get("AMBIGUOUS", 0),
        "unmapped": counts.get("UNMAPPED", 0),
    }


def rows_have_failures(rows):
    """``INSIDE`` always; ``AMBIGUOUS`` only when a candidate is ``INSIDE``."""
    for row in rows:
        if row["class"] == "INSIDE":
            return True
        if row["class"] == "AMBIGUOUS":
            for cand in row.get("candidates") or []:
                if len(cand) > 2 and cand[2] == "INSIDE":
                    return True
    return False


def row_fingerprint(klass, true_start):
    return hashlib.sha256(("%s|%s" % (klass, true_start or "")).encode()).hexdigest()


def singleton_class_counts(rows):
    names = ("START", "INSIDE", "CORRECTED", "GAP", "AMBIGUOUS", "UNMAPPED")
    counts = {name: 0 for name in names}
    for row in rows:
        if row["class"] in counts:
            counts[row["class"]] += 1
    return counts


def _canon_va(va):
    """``va`` as the one canonical ``0x%08x`` form the tool writes.

    A snapshot is JSON a human can edit, so ``0x900000`` and ``0x00900000``
    are the same VA but different strings.  Every keying site goes through
    here so padding cannot manufacture ``new``/``gone`` (H72).
    """
    return "0x%08x" % int(va, 16)


def _candidate_set(row):
    """The stored ``candidates`` as a set of ``(build, module, kind, start)``.

    ``snapshot_rows`` writes each candidate tuple as a JSON list, so a
    round-tripped row holds lists; normalise back to tuples.  Only
    ``AMBIGUOUS`` rows carry ``candidates`` (their verdict depends on the whole
    holder set), and ``load_corpus`` rejects an ``AMBIGUOUS`` row that lacks
    the key, so a missing key is never silently read as an empty set here.
    """
    return frozenset(tuple(c) for c in (row.get("candidates") or []))


def _row_key(row):
    return (row["file"], int(row["line"]), _canon_va(row["va"]), row["kind"])




def _cite_from_row(row):
    corr = int(row["correction"], 16) if row.get("correction") else None
    return Citation(int(row["va"], 16), "%s:%s" % (row["file"], row["line"]),
                    row["kind"], correction=corr)


def reclassify_rows(doc, image):
    """Re-derive every row's class from the image, using only the frozen
    ``file/line/va/kind`` (and a ``ctx`` row's paired ``correction`` start).

    The stored ``class`` is never consulted here, so a hand-edited class is
    caught.  Returns ``[(row, verdict)]`` in row order.
    """
    out = []
    seen = {}
    for row in doc["rows"]:
        va = int(row["va"], 16)
        if va not in seen:
            seen[va] = classify(image.tables, va, image.leaf_of)
        verdict = seen[va]
        cite = _cite_from_row(row)
        if (verdict.klass == "INSIDE" and cite.kind == "ctx"
                and _resolved(cite, verdict, image)):
            verdict = Verdict(verdict.va, "CORRECTED", start=verdict.start,
                              module=verdict.module, build=verdict.build,
                              candidates=verdict.candidates)
        out.append((row, verdict))
    return out


def corpus_class_drift(doc, image):
    """Rows whose stored class/true_start disagree with the image."""
    drift = []
    for row, verdict in reclassify_rows(doc, image):
        want = _row_class(verdict)
        start = _row_start(verdict)
        if (row["class"] != want or (row.get("true_start") or None) != start
                or (want == "GAP" and bool(row.get("leaf")) != bool(verdict.leaf))):
            drift.append((row, want, start))
    return drift


def compare_live(doc, image):
    """(new, gone, moved, changed) between the frozen rows and a live scan.

    ``new``/``gone`` are ``(file,line,va,kind)`` keys and are computed over
    occurrences, not over distinct keys: repeating the same key is a
    multiset count, so a deleted duplicate is ``gone`` and an added duplicate
    is ``new``.  ``moved`` pairs the frozen and live occurrence of the same
    ``(file,va,kind)`` whose line changed and whose verdict did not;
    ``changed`` is a row whose verdict changed, at an unchanged key or
    together with a line move (H69: a move never masks a verdict change).

    A verdict is ``(class, true_start)`` plus, for the two classes whose
    ``class`` alone hides the failure, the stored detail: the whole candidate
    set of an ``AMBIGUOUS`` row and the ``leaf`` flag of a ``GAP`` row (H72).
    ``va`` is compared canonically, so hex padding is not a change.

    The scope comes from the document, so an l3 overlay snapshot compares
    against a fresh l3 scan and the docs base against a fresh docs scan; the
    two layers never mix (M1.26 per-source policy).
    """
    from collections import Counter, defaultdict

    cites = collect(doc.get("scope", "docs"))[0]
    live_rows = snapshot_rows(audit(cites, image))
    frozen_by_key = {_row_key(r): r for r in doc["rows"]}
    live_by_key = {_row_key(r): r for r in live_rows}
    frozen_count = Counter(_row_key(r) for r in doc["rows"])
    live_count = Counter(_row_key(r) for r in live_rows)

    def verdict_differs(a, b):
        if (a["class"] != b["class"]
                or (a.get("true_start") or None) != (b.get("true_start") or None)):
            return True
        # AMBIGUOUS: an INSIDE candidate appearing (or a kind change) flips
        # is_failure without changing class; compare the whole holder set.
        if a["class"] == "AMBIGUOUS" and _candidate_set(a) != _candidate_set(b):
            return True
        # GAP: a leaf<->data flip is a different verdict at the same key.
        if a["class"] == "GAP" and bool(a.get("leaf")) != bool(b.get("leaf")):
            return True
        return False

    # Occurrences are a multiset, not a set: a deleted duplicate and an added
    # duplicate of an existing (file,line,va,kind) both have to count (H69
    # navigator).  Leftovers per exact key are what moved/new/gone explain.
    left_frozen, left_live = [], []
    for k in sorted(set(frozen_count) | set(live_count)):
        fc, lc = frozen_count.get(k, 0), live_count.get(k, 0)
        if fc > lc:
            left_frozen.extend([k] * (fc - lc))
        elif lc > fc:
            left_live.extend([k] * (lc - fc))

    def short(k):
        return (k[0], k[2], k[3])

    frozen_base, live_base = defaultdict(list), defaultdict(list)
    for k in left_frozen:
        frozen_base[short(k)].append(k)
    for k in left_live:
        live_base[short(k)].append(k)

    moved, changed, new, gone = [], [], [], []
    for b in sorted(set(frozen_base) | set(live_base)):
        fl, ll = sorted(frozen_base.get(b, [])), sorted(live_base.get(b, []))
        paired = min(len(fl), len(ll))
        for i in range(paired):
            a = frozen_by_key[fl[i]]
            z = live_by_key[ll[i]]
            if verdict_differs(a, z):
                changed.append((ll[i], a, z))
            else:
                moved.append((fl[i], ll[i]))
        # A count delta is new/gone even when the identity also moved: the
        # surviving occurrences may be moves, the extras are a lost or an
        # invented citation.
        gone.extend(fl[paired:])
        new.extend(ll[paired:])
    # A verdict change at an unchanged exact key never reaches the leftovers.
    for k in sorted(set(frozen_count) & set(live_count)):
        a, z = frozen_by_key[k], live_by_key[k]
        if verdict_differs(a, z):
            changed.append((k, a, z))
    changed.sort(key=lambda item: item[0])
    return sorted(new), sorted(gone), moved, changed


def corpus_fix_list(doc):
    """One ``0x<mid> -> 0x<start>`` per snapshot-INSIDE row (frozen, sorted)."""
    rows = {}
    for row in doc["rows"]:
        if row["class"] == "INSIDE":
            rows[_canon_va(row["va"])] = row.get("true_start") or "0x????????"
    return ["%s -> %s" % (va, rows[va]) for va in sorted(rows)]


def _source_label(doc):
    """The histogram label for one snapshot layer (docs base vs l3 overlay)."""
    return "L3 OVERLAY" if doc.get("scope") == "l3" else "DOCS BASE"


def _source_problems(doc, image):
    """Integrity + re-classification problems for one snapshot layer."""
    problems = []
    frozen = doc.get("summary") or {}
    got = snapshot_summary(doc)
    if got != frozen:
        problems.append(("summary", frozen, got))
    for row in doc["rows"]:
        if row.get("class_sha256") and row["class_sha256"] != row_fingerprint(
                row["class"], row.get("true_start")):
            problems.append(("integrity", row, None))
    for row, want, start in corpus_class_drift(doc, image):
        problems.append(("class", (row["file"], row["line"], row["va"],
                                   row["class"], row.get("true_start")),
                         (want, start)))
    return got, problems


def _report_problems(problems):
    for kind, a, b in problems:
        if kind == "summary":
            print("fn_audit: snapshot summary mismatch")
            for key in a:
                if a.get(key) != b.get(key):
                    print("fn_audit:   %s frozen=%s rows=%s"
                          % (key, a.get(key), b.get(key)))
        elif kind == "integrity":
            print("fn_audit: snapshot row failed its class_sha256: %s:%s %s"
                  % (a["file"], a["line"], a["va"]))
        else:
            print("fn_audit: row class disagrees with the image: "
                  "%s:%s %s frozen=%s/%s image=%s/%s" % (a[0], a[1], a[2],
                                                         a[3], a[4], b[0], b[1]))


def _report_drift(drift, stale, label=None, fix_list_mode=False):
    """Print one layer's drift.  ``label`` is set only when a second source
    (the l3 overlay) is present, so the histogram names both totals."""
    new, gone, moved, changed = drift
    tag = "CORPUS STALE" if stale else "CORPUS DRIFT"
    mid = "%s: " % label if label else ""
    if new or gone or moved:
        print("%s: %s%d new / %d gone / %d moved"
              % (tag, mid, len(new), len(gone), len(moved)))
    if changed:
        print("%s: %s%d verdict change(s) (at an unchanged key or with a "
              "line move)" % (tag, mid, len(changed)))
    if not new and not gone and not moved and not changed:
        print("%s: %s0 new / 0 gone / 0 moved" % (tag, mid))
    if not stale:
        print("fn_audit: warning: %sline-only drift; identity set unchanged, "
              "refresh the snapshot when convenient (H69)" % mid.lower())
    if fix_list_mode:
        return
    # ``--fix-list`` is machine-readable: only its ``0x… -> 0x…`` lines may
    # carry ``->``, so the drift detail stays out of that mode.
    prefix = "%s " % label if label else ""
    for kind, keys in (("new", new), ("gone", gone)):
        for key in sorted(keys)[:10]:
            print("fn_audit:   %s%s %s:%s %s"
                  % (prefix, kind, key[0], key[1], key[2]))
    for old, new_key in moved[:10]:
        print("fn_audit:   %smoved %s:%s->%s %s"
              % (prefix, old[0], old[1], new_key[1], old[2]))
    for key, _a, _b in changed[:10]:
        print("fn_audit:   %schanged %s:%s %s" % (prefix, key[0], key[1], key[2]))


def _audit_layer(doc, image, live_check, quiet, show_summary=True, label=None,
                 fix_list_mode=False):
    """Summary, integrity and live drift for one layer; returns
    (problems, drift, stale, moved_only, got)."""
    got, problems = _source_problems(doc, image)
    drift = None
    if live_check:
        new, gone, moved, changed = compare_live(doc, image)
        if new or gone or moved or changed:
            drift = (new, gone, moved, changed)
    # A moved-only drift is prose: the protected identity set
    # ``(file,va,kind,class)`` is unchanged, only ``line`` moved.  It warns and
    # exits 0 (H69); ``new``/``gone``/a verdict change still fails.
    stale = drift is not None and bool(drift[0] or drift[1] or drift[3])
    moved_only = drift is not None and not stale
    # When a second source is present its ``label`` is set, and both totals
    # must be printed, so the histogram names them (M1.26).
    if show_summary and (not quiet or problems or drift or label):
        if label:
            print("fn_audit: %s:" % label)
        for line in summary_lines(got):
            print(line)
    _report_problems(problems)
    if drift:
        _report_drift(drift, stale, label=label,
                      fix_list_mode=fix_list_mode)
    elif live_check and label:
        print("CORPUS OK: %s: 0 new / 0 gone / 0 moved" % label)
    return problems, drift, stale, moved_only, got


def audit_corpus(doc, image, quiet=False, live_check=True, fix_list_mode=False,
                 overlay=None):
    """Audit a frozen snapshot: summary, integrity, re-classification, live.

    The image is required (the frozen part is ``file/line/va/kind``); every
    stored ``class``/``true_start`` is re-derived from the image and a
    disagreement fails.  With ``live_check`` the live scan of the document's
    own scope is compared row-for-row.  A ``moved`` row set (same
    ``(file,va,kind,class)`` identity, only ``line`` changed) is prose drift:
    it prints ``CORPUS DRIFT`` and does **not** fail, because the row
    identities are unchanged.  ``new``/``gone`` rows or a verdict change at an
    unchanged key report ``CORPUS STALE`` and exit 1 — those are what the
    frozen corpus protects.

    ``overlay`` is the M1.26 l3 snapshot.  It is audited with the same rules
    as the docs base but with its own live comparison (``--scope l3``), and
    the H69 policy is applied **per source**: a moved-only drift in either
    layer warns and exits 0, while ``new``/``gone``/a count delta/a verdict
    change in either layer is ``CORPUS STALE`` and exits 1.  The histogram
    names each layer, so l3 line churn cannot fold into the docs ``moved``
    count.  An ``AMBIGUOUS`` overlay row exercises H72's candidate-set
    comparison.

    ``--fix-list`` is not an escape hatch: the summary, integrity,
    re-classification and staleness checks run first, so a snapshot tampered
    ``INSIDE -> CORRECTED`` exits non-zero even here; only then is the frozen
    ``INSIDE`` list printed.
    """
    base_label = "DOCS BASE" if overlay else None
    base_problems, base_drift, base_stale, _moved, _got = _audit_layer(
        doc, image, live_check, quiet, show_summary=not fix_list_mode,
        label=base_label, fix_list_mode=fix_list_mode)
    overlay_problems, overlay_drift, overlay_stale, _omoved, _ogot = (
        _audit_layer(overlay, image, live_check, quiet,
                     show_summary=not fix_list_mode, label="L3 OVERLAY",
                     fix_list_mode=fix_list_mode)
        if overlay else ([], None, False, False, None))

    problems = base_problems + overlay_problems
    stale = base_stale or overlay_stale
    drift = base_drift or overlay_drift

    # The docs base has no frozen ``INSIDE``; a snapshot written with one is a
    # defect and must fail.  The l3 overlay is different by design: it freezes
    # the *whole* l3 corpus, including append-only EXP history that cannot be
    # edited (M1.26), so its frozen ``INSIDE`` rows are the register, not a
    # regression.  Drift still protects the overlay: a new citation or a class
    # change to ``INSIDE`` is ``new``/``changed`` and exits 1, and a snapshot
    # edited by hand is caught by ``corpus_class_drift``.  This is the same
    # baseline semantics as H69/H72: the frozen state is the review artefact.
    failing = rows_have_failures(doc["rows"])
    if (not quiet and not problems and not drift and not live_check
            and not fix_list_mode):
        print("fn_audit: live check skipped (--no-live-check)")
    if fix_list_mode:
        lines = corpus_fix_list(doc)
        if overlay:
            lines = lines + corpus_fix_list(overlay)
        for line in lines:
            print(line)
        return 1 if (lines or problems or stale) else 0
    return 1 if (failing or problems or stale) else 0


# --------------------------------------------------------------------------
# Selftest (no image, no vendor bytes)
# --------------------------------------------------------------------------


def _synth_records(*spans):
    return [(begin, 0x10, length) for begin, length in spans]


def selftest():
    fails = []
    ran = []

    def check(name, cond):
        ran.append(name)
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
        # M1.26: an open block uses the docs discipline — a live label, a
        # correction pair and a documented pin are cited; a bare data address
        # and a US-build start are not.
        block = (
            "- [ ] **H999 — probe**\n"
            "  - bare `0x00d53500` sec1 data\n"
            "  - live fn 0x0041c7e8 label\n"
            "  - mid-function `0x00542256` → fn 0x00542250\n"
            "  - pin 0x003f5fc2 names no start here\n"
            "  - US `0x00444540` and fn 0x004446f4\n"
        )
        opened = {c.va: (c.kind, c.correction)
                  for c in citations_open_tasks(block)}
        check("open-block skips a bare data address", 0x00D53500 not in opened)
        check("open-block keeps a live label", opened.get(0x0041C7E8) == ("fn", None))
        check("open-block keeps a correction pair",
              opened.get(0x00542256) == ("ctx", 0x00542250))
        check("open-block keeps a documented pin as ctx",
              opened.get(0x003F5FC2) == ("ctx", None))
        check("open-block skips US-build starts",
              0x00444540 not in opened and 0x004446F4 not in opened)
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

    # M1.29: a documented correction is CORRECTED, a live label still fails.
    class StubImage:
        tables = [table]

        @staticmethod
        def leaf_of(module, build, va):
            return leaf_lookup(module, build, va)

    stub = StubImage()
    paired = Citation(0x401048, "doc.md:1", "ctx", correction=0x401040)
    wrong_start = Citation(0x401048, "doc.md:2", "ctx", correction=0x401100)
    live = Citation(0x401048, "doc.md:3", "fn")
    kept = audit([paired, wrong_start, live], stub)
    check("correction pair is CORRECTED, not a failure",
          kept[0][1].klass == "CORRECTED" and not kept[0][1].is_failure)
    check("pair naming the wrong start stays INSIDE",
          kept[1][1].klass == "INSIDE" and kept[1][1].is_failure)
    check("a live fn label is INSIDE even beside a corrected bare VA",
          kept[2][1].klass == "INSIDE" and kept[2][1].is_failure)
    check("--fix-list ignores CORRECTED",
          fix_list(kept, {0x401048}) == ["0x00401048 -> 0x00401040"])
    check("live VA is not reported correction-only",
          0x401048 not in corrected_only(kept))

    old_allow = dict(CORRECTION_ONLY)
    CORRECTION_ONLY[0x401048] = "true start 0x00401040 is on another line"
    try:
        only = audit([Citation(0x401048, "doc.md:4", "ctx")], stub)
        check("allowlisted correction is CORRECTED",
              only[0][1].klass == "CORRECTED" and not only[0][1].is_failure)
        CORRECTION_ONLY[0x401048] = "pinned to 0x00401000 instead"
        bad_allow = audit([Citation(0x401048, "doc.md:5", "ctx")], stub)
        check("allowlist with a wrong pinned start stays INSIDE",
              bad_allow[0][1].klass == "INSIDE")
    finally:
        CORRECTION_ONLY.clear()
        CORRECTION_ONLY.update(old_allow)

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        md = os.path.join(tmp, "corr.md")
        with open(md, "w", encoding="utf-8") as fh:
            fh.write("mid-function `0x00542256` → `fn 0x00542250` names the start\n"
                     "not a function `0x003f5fc2`→`0x003f5f48` backticked style\n"
                     "the H49 list `0x003f5a1e…0x003f5fc2` is mid-function\n"
                     "a live `fn 0x00512340` label on a mid-function line\n"
                     "`0x003f5e78` → `0x003f61bc` a pair with no marker word\n"
                     "mid-function `0x00542256` -> `fn 0x00542250` then bare "
                     "`0x00542256` again\n"
                     "mid-function: `0x0041c7dc→0x00444540` is not a pair\n")
        got = list(citations_markdown([md]))
        by_line = {}
        for c in got:
            lineno = c.where.rsplit(":", 1)[1]
            if c.correction is not None:
                by_line.setdefault(lineno, []).append((c.va, c.correction))
        check("pair extractor keeps the named start",
              by_line.get("1") == [(0x00542256, 0x00542250)])
        check("pair extractor accepts the bare arrow form",
              by_line.get("2") == [(0x003F5FC2, 0x003F5F48)])
        check("a marked line with no pair gives no correction",
              by_line.get("3") is None)
        # The marker regex is deliberately narrow (``→ fn`` glued); a bare
        # arrow pair without it is not scanned, as on the real corpus today.
        check("a bare pair without the marker word is not scanned",
              not [c for c in got if c.where.endswith(":5")])
        # A cross-build map is a pair shape, but its "start" is the other
        # build's function: the wrong-start test above proves this resolves to
        # INSIDE, never CORRECTED.
        check("a cross-build map parses as a pair shape, not as a start",
              by_line.get("7") == [(0x0041C7DC, 0x00444540)])
        # The pair's left VA is corrected; every later bare VA on the line,
        # including the pair's right VA, matches no pair and stays unresolved.
        left = [c for c in got if c.where.endswith(":6") and c.correction is not None]
        check("a repeated bare VA after the pair takes no correction",
              [(c.va, c.correction) for c in left] ==
              [(0x00542256, 0x00542250)])
        after = [(c.va, c.kind) for c in got
                 if c.where.endswith(":6") and c.correction is None]
        check("the pair's right VA and a repeated bare VA stay unresolved",
              after == [(0x00542250, "fn"), (0x00542250, "ctx"),
                        (0x00542256, "ctx")])
        # A live label is never turned into a correction by its line.
        live = [(c.va, c.correction) for c in got
                if c.where.endswith(":4") and c.kind == "fn"]
        check("a live fn label takes no correction",
              live == [(0x00512340, None)])

    # M1.30: snapshot write/read, image re-classification, and staleness.
    import contextlib
    import io
    import tempfile
    snap_cites = [
        Citation(0x401040, "doc.md:1", "fn"),
        Citation(0x401048, "doc.md:1", "ctx", correction=0x401040),
        Citation(0x401080, "doc.md:2", "const"),
        Citation(0x900000, "doc.md:3", "const"),
    ]
    snap_kept = [
        (snap_cites[0], good),
        (snap_cites[1], Verdict(0x401048, "CORRECTED", start=0x401040)),
        (snap_cites[2], gap_leaf),
        (snap_cites[3], Verdict(0x900000, "UNMAPPED")),
    ]
    snap_files = ["doc.md"]
    snap_unique = {c.va for c in snap_cites}
    snap_counts = {"START": 1, "CORRECTED": 1, "GAP": 1, "UNMAPPED": 1}
    snap_summary = summary_counts(snap_files, snap_cites, snap_unique,
                                  snap_counts, 1, snap_kept)
    with tempfile.TemporaryDirectory() as tmp:
        img = os.path.join(tmp, "synth.img")
        with open(img, "wb") as fh:
            fh.write(b"synthetic-not-vendor")
        path = os.path.join(tmp, "fa.json")
        rows = snapshot_rows(snap_kept)
        write_snapshot(path, snap_files, rows, snap_summary, img)
        first = open(path, "rb").read()
        doc = load_corpus(path)
        check("snapshot summary round-trips",
              snapshot_summary(doc) == snap_summary)
        with contextlib.redirect_stdout(io.StringIO()):
            rc = audit_corpus(doc, stub, quiet=True, live_check=False)
        check("write-then-read snapshot exits 0", rc == 0)
        check("snapshot rows are sorted by file:line:va",
              rows == sorted(rows, key=lambda r: (r["file"], r["line"],
                                                  r["va"], r["kind"])))
        check("snapshot keeps a GAP leaf flag",
              [r.get("leaf") for r in rows if r["class"] == "GAP"] == [True])
        check("snapshot stores the image SHA-256, not image bytes",
              doc["image_sha256"] == image_sha256(img)
              and len(first) < 4096)

        # Rewriting the same kept list is byte-identical (stable sort, no time).
        write_snapshot(path + "2", snap_files, snapshot_rows(snap_kept),
                       snap_summary, img)
        check("snapshot write is deterministic",
              open(path + "2", "rb").read() == first)

        # Negative control: relabel one CORRECTED row as INSIDE and re-sign
        # its fingerprint + summary; the image re-classification still fails.
        mutated = json.loads(first.decode("utf-8"))
        for row in mutated["rows"]:
            if row["class"] == "CORRECTED":
                row["class"] = "INSIDE"
                row["true_start"] = "0x00401040"
                row["class_sha256"] = row_fingerprint("INSIDE", "0x00401040")
                break
        mutated["summary"]["inside"] = 1
        mutated["summary"]["corrected"] = 0
        mpath = os.path.join(tmp, "fa-mut.json")
        json.dump(mutated, open(mpath, "w", encoding="utf-8"))
        with contextlib.redirect_stdout(io.StringIO()):
            mr = audit_corpus(load_corpus(mpath), stub, quiet=True,
                              live_check=False)
        check("mutated CORRECTED->INSIDE exits 1", mr == 1)

        # C-3865: a consistent snapshot with one INSIDE row -> one fix line,
        # exit 1, and corpus_fix_list is what printed it.
        fix_cites = [Citation(0x401040, "doc.md:1", "fn"),
                     Citation(0x401048, "doc.md:2", "fn")]
        fix_kept = [(fix_cites[0], good), (fix_cites[1], ins)]
        fix_counts = {"START": 1, "INSIDE": 1}
        fix_summary = summary_counts(["doc.md"], fix_cites,
                                     {c.va for c in fix_cites}, fix_counts,
                                     0, fix_kept)
        fpath = os.path.join(tmp, "fa-fix.json")
        write_snapshot(fpath, ["doc.md"], snapshot_rows(fix_kept),
                       fix_summary, img)
        fdoc = load_corpus(fpath)
        check("corpus_fix_list has one line for one INSIDE row",
              corpus_fix_list(fdoc) == ["0x00401048 -> 0x00401040"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fr = audit_corpus(fdoc, stub, quiet=True, live_check=False,
                              fix_list_mode=True)
        check("--fix-list on a consistent INSIDE snapshot prints the line, exit 1",
              fr == 1 and buf.getvalue().strip() == "0x00401048 -> 0x00401040")

        # C-3865/C-3864: --fix-list must not bypass the integrity checks; a
        # snapshot tampered INSIDE -> CORRECTED (fingerprint + summary
        # re-signed) prints no fix line and exits 1 via class drift.
        tam = json.load(open(fpath, encoding="utf-8"))
        for row in tam["rows"]:
            if row["class"] == "INSIDE":
                row["class"] = "CORRECTED"
                row["class_sha256"] = row_fingerprint("CORRECTED",
                                                      row["true_start"])
                break
        tam["summary"]["inside"] = 0
        tam["summary"]["corrected"] = 1
        tpath2 = os.path.join(tmp, "fa-tamper-fix.json")
        json.dump(tam, open(tpath2, "w", encoding="utf-8"))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            tf = audit_corpus(load_corpus(tpath2), stub, quiet=True,
                              live_check=False, fix_list_mode=True)
        check("--fix-list on a tampered INSIDE->CORRECTED snapshot exits 1",
              tf == 1 and "->" not in buf.getvalue())

        # Negative control: a fingerprint that no longer matches its class.
        tampered = json.loads(first.decode("utf-8"))
        for row in tampered["rows"]:
            if row["class"] == "CORRECTED":
                row["class_sha256"] = "0" * 64
                break
        tpath = os.path.join(tmp, "fa-tamper.json")
        json.dump(tampered, open(tpath, "w", encoding="utf-8"))
        with contextlib.redirect_stdout(io.StringIO()):
            tr = audit_corpus(load_corpus(tpath), stub, quiet=True,
                              live_check=False)
        check("a class_sha256 that no longer matches exits 1", tr == 1)

        # Negative control: a moved/added/removed source line is CORPUS STALE.
        live_cites = [
            Citation(0x401040, "doc.md:5", "fn"),
            Citation(0x401080, "doc.md:2", "const"),
            Citation(0x900000, "doc.md:3", "const"),
            Citation(0x401100, "doc.md:9", "fn"),
        ]
        live_rows = snapshot_rows([
            (live_cites[0], good), (live_cites[1], gap_leaf),
            (live_cites[2], Verdict(0x900000, "UNMAPPED")),
            (live_cites[3], Verdict(0x401100, "START", start=0x401100)),
        ])
        saved_collect, saved_audit = collect, audit
        glb = globals()

        def run_live(cites, kept):
            glb["collect"] = lambda scope="docs": (cites, snap_files)
            glb["audit"] = lambda c, img: list(kept)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = audit_corpus(doc, stub, live_check=True)
            return rc, buf.getvalue()

        try:
            glb["collect"] = lambda scope="docs": (live_cites, snap_files)
            glb["audit"] = lambda c, img: [
                (live_cites[0], good), (live_cites[1], gap_leaf),
                (live_cites[2], Verdict(0x900000, "UNMAPPED")),
                (live_cites[3], Verdict(0x401100, "START", start=0x401100))]
            new, gone, moved, changed = compare_live(doc, stub)
            check("compare_live reports moved/new/gone",
                  len(new) == 1 and len(gone) == 1 and len(moved) == 1)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                sr = audit_corpus(doc, stub, live_check=True)
            out = buf.getvalue()
            check("a stale live corpus exits 1 and says CORPUS STALE",
                  sr == 1 and "CORPUS STALE: 1 new / 1 gone / 1 moved" in out)

            # H69: moved-only is prose drift -> warn + exit 0.  The frozen doc
            # rows are doc.md:1 (0x401040 fn), doc.md:1 (0x401048 ctx corr),
            # doc.md:2 (0x401080 const), doc.md:3 (0x900000 const).  Move three
            # of them to new lines, keeping (file,va,kind) and the verdict.
            moved_cites = [
                Citation(0x401040, "doc.md:4", "fn"),
                Citation(0x401048, "doc.md:4", "ctx", correction=0x401040),
                Citation(0x401080, "doc.md:7", "const"),
                Citation(0x900000, "doc.md:9", "const"),
            ]
            moved_kept = [
                (moved_cites[0], good),
                (moved_cites[1], Verdict(0x401048, "CORRECTED", start=0x401040)),
                (moved_cites[2], gap_leaf),
                (moved_cites[3], Verdict(0x900000, "UNMAPPED")),
            ]
            mr, mout = run_live(moved_cites, moved_kept)
            check("moved-only drift exits 0 with a warning",
                  mr == 0 and "CORPUS DRIFT: 0 new / 0 gone / 4 moved" in mout
                  and "line-only drift" in mout)
            # --fix-list on a moved-only snapshot: no '->' line (that mode is
            # machine-readable; the moved detail is suppressed), exit 0.
            glb["collect"] = lambda scope="docs": (moved_cites, snap_files)
            glb["audit"] = lambda c, i: list(moved_kept)
            fbuf = io.StringIO()
            with contextlib.redirect_stdout(fbuf):
                fmoved = audit_corpus(doc, stub, live_check=True,
                                      fix_list_mode=True)
            check("--fix-list on moved-only prints no '->' line and exits 0",
                  fmoved == 0 and "->" not in fbuf.getvalue())
            # new only -> exit 1
            nr, nout = run_live(moved_cites + [
                Citation(0x401100, "doc.md:12", "fn")],
                moved_kept + [(Citation(0x401100, "doc.md:12", "fn"),
                               Verdict(0x401100, "START", start=0x401100))])
            check("a new row exits 1", nr == 1 and "CORPUS STALE: 1 new" in nout)
            # gone only -> exit 1
            gr, gout = run_live(moved_cites[:3], moved_kept[:3])
            check("a gone row exits 1",
                  gr == 1 and "CORPUS STALE: 0 new / 1 gone" in gout)
            # verdict change at an unchanged key -> exit 1
            same_cites = [Citation(0x401040, "doc.md:1", "fn"),
                          Citation(0x401048, "doc.md:1", "ctx",
                                   correction=0x401040),
                          Citation(0x401080, "doc.md:2", "const"),
                          Citation(0x900000, "doc.md:3", "const")]
            same_kept = list(moved_kept)
            same_kept[2] = (same_cites[2], Verdict(0x401080, "UNMAPPED"))
            cr, cout = run_live(same_cites, same_kept)
            check("a verdict change at an unchanged key exits 1",
                  cr == 1 and "verdict change" in cout)
            # a moved row whose verdict also changed is still a change, not a
            # benign move -> exit 1
            mc2 = list(moved_cites)
            mk2 = list(moved_kept)
            mk2[2] = (mc2[2], Verdict(0x401080, "UNMAPPED"))
            mcr, mcout = run_live(mc2, mk2)
            check("a verdict change on a moved row exits 1",
                  mcr == 1 and "verdict change" in mcout
                  and "3 moved" in mcout)

            # H69 navigator: occurrences are a multiset.  A snapshot with the
            # same (file,line,va,kind) twice must not collapse to one row.
            dup_frozen = [
                Citation(0x401040, "doc.md:1", "fn"),
                Citation(0x401040, "doc.md:1", "fn"),
                Citation(0x401048, "doc.md:1", "ctx", correction=0x401040),
                Citation(0x401080, "doc.md:2", "const"),
                Citation(0x900000, "doc.md:3", "const"),
            ]
            dup_kept = [
                (dup_frozen[0], good), (dup_frozen[1], good),
                (dup_frozen[2], Verdict(0x401048, "CORRECTED", start=0x401040)),
                (dup_frozen[3], gap_leaf),
                (dup_frozen[4], Verdict(0x900000, "UNMAPPED")),
            ]
            dup_summary = summary_counts(
                ["doc.md"], dup_frozen, {c.va for c in dup_frozen},
                {"START": 2, "CORRECTED": 1, "GAP": 1, "UNMAPPED": 1}, 1,
                dup_kept)
            dpath = os.path.join(tmp, "fa-dup.json")
            write_snapshot(dpath, ["doc.md"], snapshot_rows(dup_kept),
                           dup_summary, img)

            def run_dup(cites, kept):
                glb["collect"] = lambda scope="docs": (cites, snap_files)
                glb["audit"] = lambda c, i: list(kept)
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = audit_corpus(load_corpus(dpath), stub, live_check=True)
                return rc, buf.getvalue()

            # One of the two identical rows deleted -> gone, exit 1.
            del_cites = [dup_frozen[0], dup_frozen[2], dup_frozen[3],
                         dup_frozen[4]]
            del_kept = [dup_kept[0], dup_kept[2], dup_kept[3], dup_kept[4]]
            dr, dout = run_dup(del_cites, del_kept)
            check("a deleted duplicate row is gone and exits 1",
                  dr == 1 and "CORPUS STALE: 0 new / 1 gone" in dout)
            # A duplicate added for an existing key -> new, exit 1.
            add_cites = dup_frozen + [Citation(0x401040, "doc.md:1", "fn")]
            add_kept = dup_kept + [(add_cites[-1], good)]
            ar, aout = run_dup(add_cites, add_kept)
            check("a duplicated row is new and exits 1",
                  ar == 1 and "CORPUS STALE: 1 new" in aout)
            # Both duplicate rows moved to a new line, count unchanged ->
            # moved only, warn, exit 0.
            mv_cites = [Citation(0x401040, "doc.md:5", "fn"),
                        Citation(0x401040, "doc.md:5", "fn"),
                        dup_frozen[2], dup_frozen[3], dup_frozen[4]]
            mv_kept = [(mv_cites[0], good), (mv_cites[1], good),
                       dup_kept[2], dup_kept[3], dup_kept[4]]
            mr2, mout2 = run_dup(mv_cites, mv_kept)
            check("a moved duplicate pair is moved-only and exits 0",
                  mr2 == 0 and "CORPUS DRIFT: 0 new / 0 gone / 2 moved" in mout2
                  and "line-only drift" in mout2)

            # H72: verdict_differs must also compare the AMBIGUOUS candidate
            # set and the GAP leaf flag, not just class/true_start.  A second
            # build table makes 0x401048 an AMBIGUOUS row (two INSIDE starts),
            # so the frozen class matches the image and only the live verdict
            # drives the outcome -- the pre-H72 hole.
            class AmbImage:
                tables = [table, Table(0x3e00200, {
                    "synth.dll": _synth_records((0x401030, 0x80))})]

                @staticmethod
                def leaf_of(module, build, va):
                    return leaf_lookup(module, build, va)

            amb_img = AmbImage()
            benign = [("A", "synth.dll", "START", 0x401048),
                      ("B", "synth.dll", "START", 0x401030)]
            gain = benign + [("A", "synth.dll", "INSIDE", 0x401040)]
            amb_cite = Citation(0x401048, "doc.md:1", "fn")
            amb_frozen = (amb_cite, Verdict(0x401048, "AMBIGUOUS",
                                            candidates=benign))
            amb_summary = summary_counts(["doc.md"], [amb_cite], {0x401048},
                                         {"AMBIGUOUS": 1}, 0, [amb_frozen])
            apath = os.path.join(tmp, "fa-amb.json")
            write_snapshot(apath, ["doc.md"], snapshot_rows([amb_frozen]),
                           amb_summary, img)
            check("H72 fixture: an AMBIGUOUS snapshot row stores candidates",
                  [r.get("candidates") for r in snapshot_rows([amb_frozen])]
                  == [[list(c) for c in benign]])

            def run_h72(docp, image, cites, kept):
                glb["collect"] = lambda scope="docs": (cites, ["doc.md"])
                glb["audit"] = lambda c, i: list(kept)
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = audit_corpus(load_corpus(docp), image, live_check=True)
                return rc, buf.getvalue()

            # (3) unchanged candidates, line moved only -> moved-only, exit 0.
            mc = Citation(0x401048, "doc.md:4", "fn")
            r_ok, o_ok = run_h72(
                apath, amb_img, [mc],
                [(mc, Verdict(0x401048, "AMBIGUOUS", candidates=benign))])
            check("H72 unchanged AMBIGUOUS candidates stay moved-only (exit 0)",
                  r_ok == 0 and "CORPUS DRIFT: 0 new / 0 gone / 1 moved" in o_ok
                  and "verdict change" not in o_ok)
            # (1) a live candidate set that gains INSIDE -> verdict change.
            r_gain, o_gain = run_h72(
                apath, amb_img, [amb_cite],
                [(amb_cite, Verdict(0x401048, "AMBIGUOUS", candidates=gain))])
            check("H72 AMBIGUOUS candidate gains INSIDE -> CORPUS STALE exit 1",
                  r_gain == 1 and "CORPUS STALE" in o_gain
                  and "verdict change" in o_gain)

            # (2) GAP leaf True -> False at an unchanged key -> exit 1.  The
            # frozen class still matches the image (stub leaf True), so only
            # the live comparison can catch the flip.
            gap2 = Citation(0x401080, "doc.md:2", "const")
            gap2_frozen = (gap2, gap_leaf)
            gap2_summary = summary_counts(["doc.md"], [gap2], {0x401080},
                                          {"GAP": 1}, 0, [gap2_frozen])
            gpath2 = os.path.join(tmp, "fa-gapflip.json")
            write_snapshot(gpath2, ["doc.md"], snapshot_rows([gap2_frozen]),
                           gap2_summary, img)
            r_leaf, o_leaf = run_h72(
                gpath2, stub, [gap2], [(gap2, Verdict(0x401080, "GAP",
                                                     leaf=False))])
            check("H72 GAP leaf True->False -> CORPUS STALE exit 1",
                  r_leaf == 1 and "verdict change" in o_leaf)

            # unpadded `va` is the same VA: reject the spurious new/gone that
            # a raw-string _row_key printed (H72 padding).
            updoc = json.load(open(apath, encoding="utf-8"))
            updoc["rows"][0]["va"] = "0x401048"
            uppath = os.path.join(tmp, "fa-unpadded.json")
            json.dump(updoc, open(uppath, "w", encoding="utf-8"))
            r_pad, o_pad = run_h72(
                uppath, amb_img, [amb_cite],
                [(amb_cite, Verdict(0x401048, "AMBIGUOUS", candidates=benign))])
            check("H72 unpadded va prints no spurious new/gone",
                  r_pad == 0 and "new" not in o_pad and "gone" not in o_pad)

            # M1.26: the l3 overlay is a second source with its own live pass
            # and its own H69 verdict.  ``collect`` is routed by scope so the
            # docs base and the overlay never share a scan.
            def write_layer(path, scope, cite, verdict, files,
                            snapshot=True):
                kept = [(cite, verdict)]
                summary = summary_counts(files, [cite], {cite.va},
                                         {verdict.klass: 1}, 0, kept)
                if snapshot:
                    write_snapshot(path, files, snapshot_rows(kept), summary,
                                   img, scope=scope)
                return load_corpus(path)

            l3_inside = Citation(0x401048, "l3doc.md:1", "l3")
            l3_start = Citation(0x401040, "l3doc.md:1", "l3")
            l3_amb_frozen = Verdict(0x401048, "AMBIGUOUS", candidates=benign)
            ov_path = os.path.join(tmp, "fa-ov.json")
            ov_doc = write_layer(ov_path, "l3", l3_inside,
                                 Verdict(0x401048, "INSIDE", start=0x401040),
                                 ["l3doc.md"])
            base_path = os.path.join(tmp, "fa-base.json")
            base_doc = write_layer(base_path, "docs", snap_cites[0], good,
                                   ["doc.md"])

            state = {}

            def run_overlay(overlay_cites, overlay_kept, base_cites=None,
                            base_kept=None):
                base_cites = base_cites if base_cites is not None else [snap_cites[0]]
                base_kept = base_kept if base_kept is not None else [(snap_cites[0], good)]

                def fake_collect(scope="docs"):
                    state["scope"] = scope
                    if scope == "l3":
                        return overlay_cites, ["l3doc.md"], []
                    return base_cites, ["doc.md"]
                glb["collect"] = fake_collect
                glb["audit"] = lambda c, i: list(
                    overlay_kept if state.get("scope") == "l3" else base_kept)
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = audit_corpus(load_corpus(base_path), stub,
                                      live_check=True, overlay=ov_doc)
                return rc, buf.getvalue()

            move_cite = Citation(0x401048, "l3doc.md:9", "l3")
            r_ov, o_ov = run_overlay(
                [move_cite], [(move_cite, Verdict(0x401048, "INSIDE", start=0x401040))])
            check("M1.26 moved-only l3 drift warns and exits 0",
                  r_ov == 0 and "L3 OVERLAY" in o_ov
                  and "CORPUS DRIFT: L3 OVERLAY: 0 new / 0 gone / 1 moved" in o_ov)
            check("M1.26 both source totals are named",
                  "DOCS BASE" in o_ov and "CORPUS OK: DOCS BASE" in o_ov)

            # An l3 INSIDE that is new relative to the overlay -> stale, exit 1.
            r_new, o_new = run_overlay(
                [move_cite, Citation(0x401080, "l3doc.md:3", "l3")],
                [(move_cite, Verdict(0x401048, "INSIDE", start=0x401040)),
                 (Citation(0x401080, "l3doc.md:3", "l3"), gap_leaf)])
            check("M1.26 new l3 row exits 1",
                  r_new == 1 and "CORPUS STALE: L3 OVERLAY: 1 new" in o_new)
            # Removed l3 row -> gone, exit 1.
            r_gone, o_gone = run_overlay([], [])
            check("M1.26 gone l3 row exits 1",
                  r_gone == 1 and "CORPUS STALE: L3 OVERLAY: 0 new / 1 gone" in o_gone)

            # A benign AMBIGUOUS frozen overlay row moved -> exit 0.
            amb_l3 = Citation(0x401048, "l3doc.md:1", "l3")
            ov_amb_path = os.path.join(tmp, "fa-ov-amb.json")
            ov_amb_doc = write_layer(ov_amb_path, "l3", amb_l3, l3_amb_frozen,
                                     ["l3doc.md"])
            saved_drift = glb["corpus_class_drift"]

            def run_amb(overlay_kept):
                def fake_collect(scope="docs"):
                    state["scope"] = scope
                    if scope == "l3":
                        return [amb_l3], ["l3doc.md"], []
                    return [snap_cites[0]], ["doc.md"]
                glb["collect"] = fake_collect
                glb["audit"] = lambda c, i: list(
                    overlay_kept if state.get("scope") == "l3"
                    else [(snap_cites[0], good)])
                # The frozen overlay is exercised through its live pass only;
                # the class-vs-image drift is H72's own fixture above.
                glb["corpus_class_drift"] = lambda doc, image: []
                buf = io.StringIO()
                try:
                    with contextlib.redirect_stdout(buf):
                        rc = audit_corpus(load_corpus(base_path), stub,
                                          live_check=True, overlay=ov_amb_doc)
                finally:
                    glb["corpus_class_drift"] = saved_drift
                return rc, buf.getvalue()

            r_ambok, o_ambok = run_amb([(amb_l3, l3_amb_frozen)])
            check("M1.26 overlay AMBIGUOUS unchanged exits 0", r_ambok == 0)
            # The same AMBIGUOUS row gains an INSIDE candidate -> H72 catches
            # it through the overlay's own live pass: exit 1, verdict change.
            r_ambgain, o_ambgain = run_amb(
                [(amb_l3, Verdict(0x401048, "AMBIGUOUS", candidates=gain))])
            check("M1.26 overlay AMBIGUOUS gains INSIDE -> exit 1",
                  r_ambgain == 1 and "verdict change" in o_ambgain)
            # A docs-base failure is still a failure even when the overlay is
            # clean (per-source verdicts are ANDed, not ORed).
            r_docsbad, o_docsbad = run_overlay(
                [move_cite], [(move_cite, Verdict(0x401048, "INSIDE", start=0x401040))],
                base_cites=[Citation(0x401040, "doc.md:1", "fn")],
                base_kept=[(Citation(0x401040, "doc.md:1", "fn"),
                            Verdict(0x401040, "UNMAPPED"))])
            check("M1.26 docs-base verdict change still exits 1",
                  r_docsbad == 1 and "CORPUS STALE: DOCS BASE" in o_docsbad)
        finally:
            glb["collect"], glb["audit"] = saved_collect, saved_audit

        # A snapshot from another tool is rejected by load_corpus.
        wrong = json.loads(first.decode("utf-8"))
        wrong["tool"] = "not_fn_audit"
        wpath = os.path.join(tmp, "fa-wrong.json")
        json.dump(wrong, open(wpath, "w", encoding="utf-8"))
        try:
            load_corpus(wpath)
            rejected = False
        except ValueError:
            rejected = True
        check("load_corpus rejects a foreign snapshot", rejected)

        # H88: --corpus with a missing image must print the live path's error
        # and return 2, not a FileNotFoundError traceback.  The snapshot has to
        # load first (load_corpus runs before the image is hashed), so write a
        # real one against the synthetic image.
        missing = os.path.join(tmp, "no-such.img")
        path_h88 = os.path.join(tmp, "fa-h88.json")
        write_snapshot(path_h88, snap_files, rows, snap_summary, img)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc_missing = main([missing, "--corpus", path_h88])
        msg = err.getvalue()
        check("H88 --corpus + missing image exits 2 without a traceback",
              rc_missing == 2 and "Traceback" not in msg
              and "No such file or directory" in msg)
        check("H88 --corpus + missing image names the path in the error",
              missing in msg)

    print("selftest: %s (%d checks, %d failed)"
          % ("OK" if not fails else "FAIL", len(ran), len(fails)))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("image", nargs="?", help="256 MiB firmware head (e.g. archive/head256.img)")
    ap.add_argument("--scope", default="docs", choices=("docs", "l3"))
    ap.add_argument("--fix-list", action="store_true",
                    help="print one '0x<mid> -> 0x<start>' line per INSIDE VA")
    ap.add_argument("--write-snapshot", metavar="PATH",
                    help="freeze every citation + verdict to a JSON snapshot")
    ap.add_argument("--corpus", metavar="PATH",
                    help="audit a frozen snapshot instead of re-scanning docs "
                         "(the image re-classifies every row)")
    ap.add_argument("--overlay", metavar="PATH",
                    help="with --corpus, also audit the l3 overlay snapshot "
                         "(each source gets its own live comparison)")
    ap.add_argument("--no-live-check", action="store_true",
                    help="with --corpus, skip the live row-set comparison "
                         "(offline; the snapshot may then be stale)")
    ap.add_argument("--cache", default=pdata.DEFAULT_CACHE,
                    help="decoded-pdata cache directory (default %(default)s)")
    ap.add_argument("--quiet", action="store_true", help="summary and --fix-list only")
    ap.add_argument("--verbose", action="store_true",
                    help="also list the other build/module holders of a VA")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.corpus and args.write_snapshot:
        print("error: --corpus and --write-snapshot are exclusive",
              file=sys.stderr)
        return 2
    if args.overlay and not args.corpus:
        print("error: --overlay requires --corpus", file=sys.stderr)
        return 2
    if args.corpus:
        if not args.image:
            print("error: --corpus re-classifies every row against the image; "
                  "pass the image the snapshot names", file=sys.stderr)
            return 2
        try:
            doc = load_corpus(args.corpus)
        except (OSError, ValueError) as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2
        expected, err = _image_sha_or_error(args.image)
        if err is not None:
            return err
        if doc.get("image_sha256") != expected:
            print("error: snapshot image_sha256 %r does not match %s"
                  % (doc.get("image_sha256"), args.image), file=sys.stderr)
            return 2
        overlay = None
        if args.overlay:
            try:
                overlay = load_corpus(args.overlay)
            except (OSError, ValueError) as exc:
                print("error: %s" % exc, file=sys.stderr)
                return 2
            if overlay.get("scope") != "l3":
                print("error: --overlay snapshot scope is %r, want 'l3'"
                      % overlay.get("scope"), file=sys.stderr)
                return 2
            if overlay.get("image_sha256") != doc.get("image_sha256"):
                print("error: overlay image_sha256 differs from the base",
                      file=sys.stderr)
                return 2
        try:
            image = Image(args.image, args.cache)
        except OSError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2
        if not image.tables or not image.tables[0].modules:
            print("error: no build A function tables in %s" % args.image,
                  file=sys.stderr)
            return 3
        return audit_corpus(doc, image, quiet=args.quiet,
                            live_check=not args.no_live_check,
                            fix_list_mode=args.fix_list, overlay=overlay)
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
    collected = collect(args.scope)
    cites, files = collected[0], collected[1]
    not_scanned = collected[2] if len(collected) > 2 else []
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
    if args.scope == "l3":
        todo = os.path.join(REPO, "TODO.md")
        if os.path.exists(todo):
            blocks, contributing, lines = open_block_counts(
                open(todo, encoding="utf-8").read())
            print("fn_audit: open blocks %d, contributing %d, "
                  "citation lines %d" % (blocks, contributing, lines))
    for item in not_scanned:
        print("fn_audit: NOT SCANNED %s" % item)
    if args.write_snapshot:
        summary = summary_counts(files, cites, unique, counts, unmapped, kept)
        write_snapshot(args.write_snapshot, files, snapshot_rows(kept), summary,
                       args.image, scope=args.scope, not_scanned=not_scanned)
    if failing:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
