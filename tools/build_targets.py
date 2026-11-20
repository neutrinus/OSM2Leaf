#!/usr/bin/env python3
"""One owner for the per-build L3 reuse points (M1.32).

M1.22 located the US 2011 ``Navi.exe`` twins of the EU ``POINT`` walkers and
the ``.cmp`` chunk engine, plus the helpers/data cells those runs need.  Before
M1.32 the same VAs were typed by hand into five places (``targets.json``, the
two tools' ``BUILD_TARGETS``, ``fn_audit.US_BUILD_STARTS`` and the
``docs/format/firmware.md`` table); H91 was the first symptom of that copy
drifting.  This module is now the only place the values are written:

* ``point_walk_l3.BUILD_TARGETS`` and ``chunk_decoder_l3.BUILD_TARGETS`` are
  built by ``tool_map`` (same ``{build: {key: va}}`` shape as before);
* ``fn_audit.US_BUILD_STARTS`` is ``us_starts()``: the ``start`` roles below,
  the US side of the frozen M1.28/M1.22b EU->US fixture and the US entry.
  Helpers, data cells and constants are never starts (the over-broad-skip bug
  of M1.22's first draft), which ``kind`` enforces;
* ``tools/l3_harness/targets.json`` stays the machine list the runner reads,
  and the ``firmware.md`` table stays prose: ``check`` asserts both equal this
  module, and prints ``only-in-*`` counts per copy.

Every value is a whole image VA (or, for ``escape_len``, a record length in
halfwords) located by M1.22 / M9.11 / M3.11; evidence:
EXP-2026-11-17-M1.22-us-build-census (pool-slot transcripts) and
EXP-2026-11-08-M9.11-chunk-decoder.

Usage::

  build_targets.py --selftest
  build_targets.py show [--build us2011]
  build_targets.py check [--root DIR]     # exit 1 on any only-in-*
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BUILDS = ("eu2011", "us2011")

# (key, tool, kind, EU2011 value, US2011 value, what it is)
#   kind: start  -- a function entry the harness calls (fn_audit skips the US one)
#         helper -- a function the harness stubs (not a reader start)
#         data   -- a data cell / table the harness maps or fills
#         const  -- a code-visible constant, not an address
ROLES = (
    ("nth", "point_walk_l3", "start", 0x003F5194, 0x0041DB44,
     "POINT nth reader record_at(page, n)"),
    ("skip", "point_walk_l3", "start", 0x003F39C0, 0x0041C370,
     "POINT skip walker (globals)"),
    ("dispatch", "point_walk_l3", "start", 0x003F5CDC, 0x0041E63C,
     "POINT dispatcher (its pool names the two walkers)"),
    ("global_count", "point_walk_l3", "data", 0x00D5E4D0, 0x00C8C0D0,
     "POINT global: record count of the loaded page"),
    ("global_page", "point_walk_l3", "data", 0x00D5E4E4, 0x00C8C0E4,
     "POINT global: current page base"),
    ("globals_base", "point_walk_l3", "data", 0x00D5E4C0, 0x00C8C0C0,
     "POINT globals RW region the harness maps"),
    ("escape_len", "point_walk_l3", "const", 0x4E8, 0x4D8,
     "POINT escape record length (halfwords)"),
    ("fn_chunk", "chunk_decoder_l3", "start", 0x0041C7DC, 0x00444540,
     "CMP chunk engine"),
    ("memcpy", "chunk_decoder_l3", "helper", 0x003D146C, 0x00400944,
     "COREDLL #1044 memcpy thunk (engine pool slot)"),
    ("mod_helper", "chunk_decoder_l3", "helper", 0x003D140C, 0x004008E4,
     "mod helper thunk (engine pool slot)"),
    ("mod31", "chunk_decoder_l3", "helper", 0x003D1484, 0x0040098C,
     "COREDLL #2006 r4 % r5 thunk (engine pool slot)"),
    # the two zlib trampolines, found by their unique 6-halfword shape
    # (`mov r5,r4; mov.l @(pc),r3; mov.l @r3,r3; jmp @r3; ...`): exactly one
    # calloc-shape and one free-shape hit in each build's text.
    ("zcalloc", "chunk_decoder_l3", "helper", 0x00543A98, 0x00565D94,
     "zlib zcalloc trampoline"),
    ("zcfree", "chunk_decoder_l3", "helper", 0x00543AA8, 0x00565DA4,
     "zlib zcfree trampoline"),
    # the `shll2 r2; mov.l @(pc),r3; mov.l @(r0,r3),r2; and r12,r2` sequence
    # is unique in each build's text; each build's site loads this address.
    ("inflate_mask", "chunk_decoder_l3", "data", 0x00574DE0, 0x005987B0,
     "zlib inflate_mask[17]"),
    ("inflate_wrapper", "chunk_decoder_l3", "helper", 0x00542148, 0x00564444,
     "zlib inflate wrapper (engine pool slot)"),
    # M4.52: the POINT chain-locator path (EXP-2026-11-20-M4.52-point-locator-
    # reader).  Every entry is a function start in both builds (pdata START,
    # or a leaf with no pdata record right after the preceding one: decode,
    # hdr_tail); the stubbed ones are starts too, so they are kind ``start``.
    ("header", "point_locator_l3", "start", 0x003F930C, 0x00421C3C,
     "POINT .DAT header parser (directory cells -> object)"),
    ("loader", "point_locator_l3", "start", 0x003FE2D4, 0x00426480,
     "POINT page loader (reads the base reference D+4)"),
    ("decode", "point_locator_l3", "start", 0x0040F00C, 0x00436F58,
     "block address -> 256-byte block number (leaf)"),
    ("lookup", "point_locator_l3", "start", 0x0040EE4C, 0x00436DD4,
     "header-table entry lookup (100 x 80 B)"),
    ("cache", "point_locator_l3", "start", 0x00407724, 0x0042F824,
     "sector cache lookup (stubbed: miss)"),
    ("alloc", "point_locator_l3", "start", 0x004086B4, 0x004307B4,
     "sector cache allocate (stubbed: host buffer)"),
    ("log", "point_locator_l3", "start", 0x003EC9FC, 0x0041551C,
     "debug log (stubbed: no-op)"),
    ("request", "point_locator_l3", "start", 0x003F6C88, 0x0041F5E8,
     "read request (stubbed: served from the .DAT)"),
    ("hdr_tail", "point_locator_l3", "start", 0x0040A8D0, 0x004329D0,
     "header parser tail call (leaf, stubbed: 0)"),
    ("memset", "point_locator_l3", "helper", 0x003D13C4, 0x0040089C,
     "COREDLL memset thunk (loader pool slot)"),
    ("divlu", "point_locator_l3", "helper", 0x003D140C, 0x004008E4,
     "_divlu thunk (loader pool slot; = mod_helper)"),
    # M9.14: the map-file layer vcard_l3.py runs (EXP-2026-11-20-M9.14-drstr-
    # parser-l3).  Functions: fn_match pairs, pdata START with equal lengths
    # in both builds; data: the pool value at the same load index of the
    # paired function (`vcard_l3.py port` re-derives and checks them).
    ("layer_init", "vcard_l3", "start", 0x00417924, 0x0043F688,
     "map-file layer init (tables, pools, state 0)"),
    ("layer_event", "vcard_l3", "start", 0x00419C38, 0x0044199C,
     "map-file layer event: handler for (state, kind)"),
    ("layer_read", "vcard_l3", "start", 0x0041841C, 0x00440180,
     "map-file layer: queue a read (12-byte stub)"),
    ("layer_resolve", "vcard_l3", "start", 0x0040B358, 0x00433458,
     "map-file layer: (directory, name) -> file id"),
    ("layer_cancel", "vcard_l3", "start", 0x00418428, 0x0044018C,
     "map-file layer: withdraw a queued read"),
    ("layer_logger", "vcard_l3", "start", 0x0041BBEC, 0x00443950,
     "map-file layer error logger"),
    ("read_clamp", "vcard_l3", "start", 0x00409BA0, 0x00431CA0,
     "read API client: range clamp"),
    ("read_request", "vcard_l3", "start", 0x003F6C88, 0x0041F5E8,
     "read API client: read request (= point_locator request)"),
    ("read_wrap_a", "vcard_l3", "start", 0x003F7384, 0x0041FCE4,
     "read API client: wrapper A"),
    ("read_wrap_b", "vcard_l3", "start", 0x003F73DC, 0x0041FD3C,
     "read API client: wrapper B"),
    ("drstr_parser", "vcard_l3", "start", 0x00419350, 0x004410B4,
     "DRSTR001.DAT parser"),
    ("drstr_caller", "vcard_l3", "start", 0x00419684, 0x004413E8,
     "DRSTR parser caller (volume table build)"),
    ("mmain_reader", "vcard_l3", "start", 0x0041A438, 0x0044219C,
     "MMAIN001.DAT reader"),
    ("layer_state", "vcard_l3", "data", 0x009CFCE0, 0x00A10EA8,
     "map-file layer state-machine state"),
    ("layer_mount", "vcard_l3", "data", 0x009CFCE4, 0x00A10EAC,
     "map-file layer mount state (= state + 4)"),
    ("layer_ndirs", "vcard_l3", "data", 0x009CFCD4, 0x00A10E9C,
     "volume table directory count"),
    ("layer_dirs", "vcard_l3", "data", 0x00E25420, 0x00D53020,
     "volume table: 36-byte directory records"),
    ("mmain_buf", "vcard_l3", "data", 0x00E23CC0, 0x00D518C0,
     "0x1000-byte MMAIN001.DAT buffer"),
    # image base 0x10000 + rva, written as sums so fn_audit does not read a VA
    ("volume_root_w", "vcard_l3", "data", 0x10000 + 0x39FD4, 0x10000 + 0x46634,
     "L\"\\SystemSD\" (UTF-16), the prefix of every file name"),
)
KINDS = ("start", "helper", "data", "const")

# US 2011 Navi.exe entry point (C-3487); a start, but not an L3 reuse point.
US_ENTRY = 0x0035D894
FIXTURE = HERE / "fixtures" / "fn_match_eu_us_2011.json"
DOC_HEADING = "## The US build at L3"
# targets.json readers whose firmware VAs are roles here (the POINT walkers
# have no targets.json entry yet; their runner is point_walk_l3 itself).
OWNED_READERS = ("cmp_ind", "point_walk")


def roles(build: str, kinds=KINDS, tool: str | None = None) -> dict:
    """``{key: value}`` for *build*, filtered by kind and owning tool."""
    col = 3 + BUILDS.index(build)
    return {r[0]: r[col] for r in ROLES
            if r[2] in kinds and (tool is None or r[1] == tool)}


def tool_map(tool: str) -> dict:
    """The ``BUILD_TARGETS`` dict a tool used to write by hand."""
    out = {b: roles(b, tool=tool) for b in BUILDS}
    if not out["eu2011"]:
        raise KeyError("no roles for tool %r" % tool)
    return out


def fixture_us_starts(path: Path = FIXTURE) -> set:
    """US-side VAs of the frozen EU->US fixture (UNIQUE ``us_va`` and
    DIFFERENT ``us_candidate``; NOMATCH rows carry none)."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    out = set()
    for row in doc["rows"]:
        va = row.get("us_va") or row.get("us_candidate")
        if va:
            out.add(int(va, 16))
    return out


def us_starts(fixture: Path = FIXTURE) -> frozenset:
    """Every verified US 2011 ``Navi.exe`` function start the EU audit skips."""
    return frozenset(set(roles("us2011", kinds=("start",)).values())
                     | fixture_us_starts(fixture) | {US_ENTRY})


# ---------------------------------------------------------------------------
# copies and the check

HEX_RE = re.compile(r"0x[0-9A-Fa-f]+")
VA_RE = re.compile(r"\b0x[0-9A-Fa-f]{8}\b")


def _pairs() -> set:
    """Owner (EU, US) pairs for every role."""
    return {(r[3], r[4]) for r in ROLES}


def doc_pairs(text: str) -> set:
    """(EU, US) pairs from the firmware.md ``US build at L3`` table."""
    start = text.find(DOC_HEADING)
    if start < 0:
        raise ValueError("heading %r not found" % DOC_HEADING)
    end = text.find("\n## ", start + 1)
    section = text[start:end if end > 0 else len(text)]
    out = set()
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not line.lstrip().startswith("|"):
            continue
        eu = [int(x, 16) for x in HEX_RE.findall(cells[1])]
        us = [int(x, 16) for x in HEX_RE.findall(cells[2])]
        if not eu or len(eu) != len(us):
            continue
        out.update(zip(eu, us))
    return out


def json_vas(doc: dict) -> dict:
    """``{build: set(VA)}`` that ``targets.json`` names for the owned targets.

    A target is owned when its ``reader`` is in ``OWNED_READERS`` (the
    readers whose VAs this module holds).
    Its ``entry.va``, ``entry.sec1_table.va`` and every 8-digit VA in
    ``what``/``note``/``notes``/``expect.rule`` are collected; the
    ``sec1_table.provenance`` text quotes instruction sites, not roles, and
    is left out.
    """
    out = {b: set() for b in BUILDS}
    for t in doc.get("targets", []):
        build = t.get("build")
        entry = t.get("entry") or {}
        if build not in BUILDS or not isinstance(entry.get("va"), str):
            continue
        if t.get("reader") not in OWNED_READERS:
            continue
        found = {int(entry["va"], 16)}
        tab = entry.get("sec1_table") or {}
        if "va" in tab:
            found.add(int(tab["va"], 16))
        texts = [t.get("what", ""), entry.get("note", ""),
                 (t.get("expect") or {}).get("rule", "")]
        texts += list(t.get("notes", []))
        for s in texts:
            found.update(int(x, 16) for x in VA_RE.findall(s))
        out[build] |= found
    return out


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    sys.path.insert(1, str(path.parent / "l3_harness"))
    try:
        spec.loader.exec_module(mod)
    finally:
        del sys.path[0:2]
    return mod


def compare(name: str, copy: set, owner: set) -> tuple:
    return name, sorted(copy - owner), sorted(owner - copy)


def collect(root: Path) -> list:
    """Compare every copy under *root* with this module; list of
    ``(copy, only_in_copy, only_in_owner)``."""
    root = Path(root)
    rows = []
    owner_all = {b: set(roles(b, kinds=("start", "helper", "data")).values())
                 for b in BUILDS}
    # targets.json: every role VA it names must be owned; it must name the
    # owner's chunk-engine start, inflate_mask and stubbed helpers per build
    # it carries a target for.
    doc = json.loads((root / "tools/l3_harness/targets.json").read_text(
        encoding="utf-8"))
    jv = json_vas(doc)
    for b in BUILDS:
        if not jv[b]:
            continue
        need = {roles(b)[k] for k in ("fn_chunk", "inflate_mask")}
        if b == "us2011":
            need |= {roles(b)[k] for k in ("memcpy", "mod31", "zcalloc",
                                           "zcfree")}
        extra = {v for v in jv[b] if v not in owner_all["eu2011"]
                 | owner_all["us2011"]}
        rows.append(("targets.json[%s]" % b, sorted(extra),
                     sorted(need - jv[b])))
    # the two tools' BUILD_TARGETS, imported from *root*.
    for tool in ("point_walk_l3", "chunk_decoder_l3"):
        mod = _load(root / "tools" / ("%s.py" % tool), "_bt_" + tool)
        got = getattr(mod, "BUILD_TARGETS")
        want = tool_map(tool)
        for b in BUILDS:
            copy = {(k, v) for k, v in got.get(b, {}).items()}
            own = set(want[b].items())
            rows.append(("%s[%s]" % (tool, b), sorted(copy - own),
                         sorted(own - copy)))
    # fn_audit.US_BUILD_STARTS
    fa = _load(root / "tools" / "fn_audit.py", "_bt_fn_audit")
    rows.append(compare("fn_audit.US_BUILD_STARTS", set(fa.US_BUILD_STARTS),
                        set(us_starts(root / "tools/fixtures/fn_match_eu_us_2011.json"))))
    # firmware.md table: every owner role is a row (EU, US) pair.
    text = (root / "docs/format/firmware.md").read_text(encoding="utf-8")
    rows.append(compare("firmware.md table", doc_pairs(text), _pairs()))
    return rows


def _fmt(v):
    if isinstance(v, tuple) and isinstance(v[0], str):
        return "%s=%#x" % v
    if isinstance(v, tuple):
        return "EU2011 %#010x / US2011 %#010x" % v
    return "%#010x" % v


def report(rows, out=sys.stdout) -> int:
    total = 0
    for name, only_copy, only_owner in rows:
        n = len(only_copy) + len(only_owner)
        total += n
        print("%-36s only-in-copy: %d  only-in-owner: %d" %
              (name, len(only_copy), len(only_owner)), file=out)
        for v in only_copy:
            print("    only in %s: %s" % (name, _fmt(v)), file=out)
        for v in only_owner:
            print("    only in build_targets: %s" % _fmt(v), file=out)
    print("TOTAL only-in-*: %d across %d copies" % (total, len(rows)), file=out)
    return total


# ---------------------------------------------------------------------------
# selftest


def selftest() -> int:
    import io
    import shutil
    import tempfile
    n = [0, 0]

    def check(name, cond):
        n[0] += 1
        if not cond:
            n[1] += 1
            print("FAIL", name)

    keys = [r[0] for r in ROLES]
    check("role keys unique", len(keys) == len(set(keys)))
    check("every kind known", all(r[2] in KINDS for r in ROLES))
    starts = us_starts()
    for r in ROLES:
        if r[2] != "start":
            check("non-start %s kept out of US starts" % r[0], r[4] not in starts)
    check("US starts are 33 (15 at H91/C-4140, +9 M4.52, +9 new of 13 M9.14 layer starts)", len(starts) == 33)
    check("US entry is a start", US_ENTRY in starts)
    check("tool_map shape", set(tool_map("point_walk_l3")["us2011"]) ==
          {"nth", "skip", "dispatch", "global_count", "global_page",
           "globals_base", "escape_len"})
    try:
        tool_map("nope")
        check("unknown tool raises", False)
    except KeyError:
        check("unknown tool raises", True)

    # doc parser on a synthetic table
    syn = ("# x\n\n%s: y\n\n| Role | EU2011 VA | US2011 VA | How |\n"
           "| --- | --- | --- | --- |\n"
           "| a | `0x10` | `0x20` | `0x999` |\n"
           "| b/c | `0x1`/`0x2` | `0x3`/`0x4` | x |\n\n## next\n"
           "| z | `0x5` | `0x6` | |\n" % DOC_HEADING)
    check("doc_pairs parses pairs and stops at next heading",
          doc_pairs(syn) == {(0x10, 0x20), (0x1, 0x3), (0x2, 0x4)})

    # The live tree must be clean.
    buf = io.StringIO()
    check("live tree: 0 only-in-*", report(collect(REPO), out=buf) == 0)
    if n[1]:
        print(buf.getvalue())

    # Mutations (falsifier): a one-halfword drift in each copy goes red.
    tmp = Path(tempfile.mkdtemp(prefix="build_targets_"))
    try:
        for rel in ("tools/l3_harness/targets.json", "docs/format/firmware.md",
                    "tools/point_walk_l3.py", "tools/chunk_decoder_l3.py",
                    "tools/fn_audit.py", "tools/fixtures/fn_match_eu_us_2011.json",
                    "tools/build_targets.py"):
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / rel, tmp / rel)
        # tools import siblings at import time
        for dep in ("cerom.py", "cmpind.py", "pdata.py"):
            if (REPO / "tools" / dep).exists():
                shutil.copy2(REPO / "tools" / dep, tmp / "tools" / dep)
        if (REPO / "tools/l3_harness/engine.py").exists():
            shutil.copy2(REPO / "tools/l3_harness/engine.py",
                         tmp / "tools/l3_harness/engine.py")
        base = {rel: (tmp / rel).read_text(encoding="utf-8") for rel in
                ("tools/l3_harness/targets.json", "docs/format/firmware.md",
                 "tools/point_walk_l3.py", "tools/chunk_decoder_l3.py",
                 "tools/fn_audit.py")}
        quiet = io.StringIO()
        check("copied tree: 0 only-in-*", report(collect(tmp), out=quiet) == 0)
        # Drifted values are computed, never spelled: fn_audit scans this
        # file's 0x constants, and a literal mid-function VA would be an
        # INSIDE citation.
        us = roles("us2011")

        def h(v, upper=False):
            return ("0x%08X" if upper else "0x%08x") % v

        def hand(tool, key):
            line = "BUILD_TARGETS = build_targets.tool_map(\"%s\")" % tool
            return (line, line + "\nBUILD_TARGETS[\"us2011\"] = dict("
                    "BUILD_TARGETS[\"us2011\"], %s=%s)" % (key, h(us[key] + 2)))

        cases = (
            ("targets.json entry.va +2", "tools/l3_harness/targets.json",
             '"va": "%s"' % h(us["fn_chunk"]),
             '"va": "%s"' % h(us["fn_chunk"] + 2)),
            ("firmware.md US skip walker +2", "docs/format/firmware.md",
             "`%s`" % h(us["skip"]), "`%s`" % h(us["skip"] + 2)),
            ("point_walk_l3 hand-written US nth +2", "tools/point_walk_l3.py")
            + hand("point_walk_l3", "nth"),
            ("chunk_decoder_l3 hand-written US zcfree +2",
             "tools/chunk_decoder_l3.py") + hand("chunk_decoder_l3", "zcfree"),
            ("fn_audit adds a US helper to the skip set", "tools/fn_audit.py",
             "US_BUILD_STARTS = build_targets.us_starts()",
             "US_BUILD_STARTS = build_targets.us_starts() | {%s}"
             % h(us["memcpy"])),
        )
        for name, rel, old, new in cases:
            text = base[rel]
            check("mutation site present: " + name, text.count(old) >= 1)
            (tmp / rel).write_text(text.replace(old, new, 1), encoding="utf-8")
            check("mutation red: " + name,
                  report(collect(tmp), out=io.StringIO()) > 0)
            (tmp / rel).write_text(text, encoding="utf-8")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("build_targets selftest: %s (%d checks, %d failed)"
          % ("OK" if not n[1] else "FAIL", n[0], n[1]))
    return 1 if n[1] else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    sh = sub.add_parser("show", help="print the owned roles")
    sh.add_argument("--build", choices=BUILDS)
    ck = sub.add_parser("check", help="compare every copy with the owner")
    ck.add_argument("--root", default=str(REPO),
                    help="repository tree to check (default: this one)")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "show":
        for r in ROLES:
            vals = {"eu2011": r[3], "us2011": r[4]}
            if args.build:
                print("%-16s %-17s %-6s %#010x  %s" % (
                    r[0], r[1], r[2], vals[args.build], r[5]))
            else:
                print("%-16s %-17s %-6s EU2011 %#010x  US2011 %#010x  %s" % (
                    r[0], r[1], r[2], r[3], r[4], r[5]))
        print("US starts (fn_audit skip set): %d" % len(us_starts()))
        return 0
    if args.cmd == "check":
        return 1 if report(collect(Path(args.root))) else 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
