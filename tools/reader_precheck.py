#!/usr/bin/env python3
"""Precheck for firmware reader tasks (M1.12, AGENTS rule 14).

Run it before anyone searches a module for a reader. For one CE module it
reports, from the image headers alone:

  * bytes: executable (CODE|EXEC flagged) versus data, each split into
    decodable (plain) and compressed (IMAGE_SCN_COMPRESSED). Executable
    compressed bytes are the number that decides whether a search can
    succeed; compressed data bytes are not code.
  * calls INTO compressed sections from decodable code. Such a call is the
    failure mode of M3.15 (C-2206): the target section has no MEM_EXECUTE
    flag, yet decodable code calls it. Two edge forms are found:
      - ``bsr`` whose target lies in a compressed section;
      - ``mov.l @(disp,PC),Rn`` whose literal word lies in a compressed
        section. Each such load is classified by what follows it:
        ``direct`` (``jsr/jmp @Rn`` before any other use of Rn: the literal
        is the target), ``indirect`` (the literal is dereferenced and the
        result is called: the target is a pointer stored in compressed
        bytes), ``slot`` (dereferenced, not called), ``unclassified``,
        ``data`` (no call, no dereference).
    Calls are ``bsr``, ``direct`` and ``indirect``. Classes are lower
    bounds: computed jump targets are not followed.
  * for each ``--anchor VA``: the literal-pool xrefs in decodable code
    (``sh4xref.pool_entries`` + ``loads_of``), the functions that hold them
    (``sh4xref.function_start``), and the compressed calls those functions
    make. Verdicts and exit codes:
      0 DECODABLE          xref in decodable code, no holder calls compressed code
      1 ABSENT             no decodable xref and the module has no compressed bytes
      2 COMPRESSED-ANCHOR  the anchor VA itself lies in a compressed section
      2 ENTERS-COMPRESSED  a holder function calls into a compressed section
      2 INCONCLUSIVE       no decodable xref, and the module has compressed bytes
      2 OUTSIDE-MODULE     the anchor VA lies in no section of the module
    A non-zero verdict is not "impossible": it says the decodable bytes do
    not settle the question.

Stdlib only. Section table: ``tools/point_walk_l3.py`` (``module_sections``).
Decoding: ``tools/sh4dis.py`` (little-endian). Xrefs: ``tools/sh4xref.py``.
Scan engine/LE halfword primitive: ``tools/sh4scan.py`` (M3.19) is imported
and its ``halfword_array`` (``sh4dis.halfwords_le``) is delegated for the
edge scan; this satisfies M3.19's done-when clause "M1.12 imports it rather
than duplicating the scan" (EXP-2026-11-09-H48-reader-precheck-sh4scan).
Every address comes from ``tools/cerom.py``; nothing is a fitted delta.

Usage::

  reader_precheck.py [IMG] [--image-start 0x200200] --module Navi.exe
                     [--anchor 0x00179364 ...]
  reader_precheck.py [IMG] [--image-start 0x200200] --table
  reader_precheck.py --selftest [IMG]

``IMG`` defaults to ``$OSM2LEAF_IMG``, then ``archive/head256.img`` in this
checkout or in the main checkout. Exit 3 means no image (nothing runnable,
never a pass). ``--selftest`` runs the synthetic checks always and the real
build-A pins when an image is found (SKIP otherwise).

Method and results: docs/experiments/EXP-2026-11-08-M1.12-reader-precheck.md
"""
import argparse
import array
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cerom  # noqa: E402
import point_walk_l3 as pw  # noqa: E402  (module_sections, CODE, EXEC)
import sh4scan  # noqa: E402  (M3.19 scan engine; H48: delegated scan primitive)
import sh4xref  # noqa: E402
from sh4dis import Mem, bsr_target, is_rts, jsr_reg, movl_pc_target  # noqa: E402

DEFAULT_IMAGE_START = 0x200200
CALL_WINDOW = sh4xref.CALL_WINDOW
FUNC_LIMIT = sh4xref.FUNC_LIMIT
EXEC_FLAGS = pw.CODE | pw.EXEC
LIST_LIMIT = 8          # printed xrefs and compressed calls per anchor
IMG_RELATIVE = os.path.join("archive", "head256.img")

# Build-A pins (AGENTS, C-2128, EXP-2026-11-08-M1.12). Checked only when the
# image is present; a mismatch means the discrepancy is recorded, not adjusted.
REAL_PINS = {
    "modules": 149,
    "modules_with_compressed": 133,
    "total_vsize": 53725980,
    "compressed_vsize": 30212810,
    "compressed_sections": 245,
    "exec_compressed": 0,
    "exec_plain": 22767466,
    "navi_compressed_vsize": 16778254,
    "navi_compressed_realaddrs": [0x0055D000, 0x0154F000],
    # Edges into compressed sections over all 149 modules (lower bounds).
    "edges_bsr": 4,
    "edges_direct": 1,
    "edges_indirect": 20879,
    "navi_edges_bsr": 0,
}

VERDICT_EXIT = {
    "DECODABLE": 0,
    "ABSENT": 1,
    "COMPRESSED-ANCHOR": 2,
    "ENTERS-COMPRESSED": 2,
    "INCONCLUSIVE": 2,
    "OUTSIDE-MODULE": 2,
}


# --------------------------------------------------------------------------
# Image and section table
# --------------------------------------------------------------------------

def default_image():
    env = os.environ.get("OSM2LEAF_IMG")
    if env:
        return env
    roots = [os.path.dirname(HERE)]
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"], cwd=HERE,
            capture_output=True, text=True, check=True).stdout.strip()
        roots.append(os.path.dirname(os.path.abspath(os.path.join(HERE, common))))
    except (OSError, subprocess.CalledProcessError):
        pass
    for root in roots:
        cand = os.path.join(root, IMG_RELATIVE)
        if os.path.isfile(cand):
            return cand
    return None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sections_of(data, image_start, module):
    """Section records of ``module``: realaddr, vsize, flags, compressed, exec, blob."""
    _, secs = pw.module_sections(data, image_start, module)
    out = []
    for s, comp, blob in secs:
        # Only vsize bytes are mapped at runtime; bytes between vsize and psize
        # are file padding. Navi sec0 has vsize 0x54bd16 and psize 0x54be00:
        # scanning psize would read 0x0055cd16..0x0055ce00 as code.
        if blob is not None:
            blob = blob[:s["vsize"]]
        out.append({
            "realaddr": s["realaddr"],
            "vsize": s["vsize"],
            "psize": s["psize"],
            "flags": s["flags"],
            "compressed": comp,
            "exec": bool(s["flags"] & EXEC_FLAGS),
            "blob": blob,
        })
    return out


def census(secs):
    c = {"sections": len(secs), "compressed_sections": 0, "total_vsize": 0,
         "compressed_vsize": 0, "exec_plain": 0, "exec_compressed": 0,
         "data_plain": 0, "data_compressed": 0}
    for s in secs:
        v = s["vsize"]
        c["total_vsize"] += v
        if s["compressed"]:
            c["compressed_sections"] += 1
            c["compressed_vsize"] += v
        key = ("exec" if s["exec"] else "data") + ("_compressed" if s["compressed"] else "_plain")
        c[key] += v
    c["compressed_share"] = (c["compressed_vsize"] / c["total_vsize"]) if c["total_vsize"] else 0.0
    return c


def compressed_ranges(secs):
    """Sorted (start, end, section index) of every compressed section."""
    return sorted((s["realaddr"], s["realaddr"] + s["vsize"], i)
                  for i, s in enumerate(secs) if s["compressed"])


def comp_at(ranges, va):
    for start, end, idx in ranges:
        if start <= va < end:
            return idx
    return None


def section_at(secs, va):
    for i, s in enumerate(secs):
        if s["realaddr"] <= va < s["realaddr"] + s["vsize"]:
            return i
    return None


def decodable_views(secs):
    """(Mem over plain sections, [(base, blob)] over plain executable sections)."""
    plain = [(s["realaddr"], s["blob"]) for s in secs if not s["compressed"]]
    exec_plain = [(s["realaddr"], s["blob"]) for s in secs
                  if not s["compressed"] and s["exec"]]
    return Mem(plain), exec_plain


# --------------------------------------------------------------------------
# Edges into compressed sections
# --------------------------------------------------------------------------

def classify_load(mem, load, reg):
    """What the literal loaded at ``load`` into ``reg`` is used for.

    ``direct``       the literal is the call target (``jsr/jmp @Rreg`` first);
    ``indirect``     the literal is a slot: ``mov.l @Rreg,Rx`` then ``jsr @Rx``
                     calls the pointer stored there, so the target is unknown
                     and lies in whatever holds the slot (M3.15: sec1 0x0055d924);
    ``slot``         the literal is dereferenced and not called (a table read);
    ``unclassified`` ``reg`` is used in some other way first;
    ``data``         no call and no dereference within the window.
    """
    track, derefed = reg, False
    for k in range(1, CALL_WINDOW + 1):
        a = load + 2 * k
        w = mem.u16(a)
        if w is None or is_rts(w):
            break
        j = jsr_reg(w)
        if j and j[1] == track:
            return "indirect" if derefed else "direct"
        if not derefed and w & 0xF00F == 0x6002 and (w >> 4) & 15 == track:
            derefed = True                                  # mov.l @Rtrack,Rx
            track = (w >> 8) & 15
            continue
        if (w >> 8) & 15 == track or (w >> 4) & 15 == track:
            return "unclassified"
    return "slot" if derefed else "data"


def edge_at(mem, a, w, ranges):
    """Call-like edge into a compressed section at instruction ``a`` (word ``w``), or None."""
    t = bsr_target(a, w)
    if t is not None:
        idx = comp_at(ranges, t)
        return None if idx is None else {"site": a, "kind": "bsr", "target": t,
                                         "sec": idx, "class": "direct", "load": None}
    ld = movl_pc_target(a, w)
    if ld is None:
        return None
    reg, lit = ld
    value = mem.u32(lit)
    if value is None:
        return None
    idx = comp_at(ranges, value)
    if idx is None:
        return None
    return {"site": None, "load": a, "kind": "lit", "target": value, "sec": idx,
            "class": classify_load(mem, a, reg), "reg": reg}


def _words(blob):
    """LE halfwords of ``blob`` (edge-scan primitive), delegated to sh4scan (M3.19/H48)."""
    return sh4scan.halfword_array(blob)


def module_edges(mem, exec_plain, ranges):
    """Every edge into a compressed section from decodable executable bytes."""
    out = []
    for base, blob in exec_plain:
        for i, w in enumerate(_words(blob)):
            top = w & 0xF000
            if top != 0xB000 and top != 0xD000:
                continue
            e = edge_at(mem, base + 2 * i, w, ranges)
            if e is not None:
                if e["kind"] == "bsr":
                    e["site"] = base + 2 * i
                out.append(e)
    return out


def function_edges(mem, fn, ranges):
    """Edges into compressed sections in the function at ``fn`` (up to its rts)."""
    out = []
    for k in range(0, FUNC_LIMIT, 2):
        a = fn + k
        w = mem.u16(a)
        if w is None or (k and is_rts(w)):
            break
        e = edge_at(mem, a, w, ranges)
        if e is not None:
            if e["kind"] == "bsr":
                e["site"] = a
            out.append(e)
    return out


TALLY_KEYS = ("bsr_direct", "lit_direct", "lit_indirect", "lit_slot",
              "lit_unclassified", "lit_data")


def tally_edges(edges):
    t = dict.fromkeys(TALLY_KEYS, 0)
    for e in edges:
        t["bsr_direct" if e["kind"] == "bsr" else "lit_" + e["class"]] += 1
    return t


def calls_into_compressed(edges):
    """Edges that are calls: bsr, a direct literal call, or an indirect call through a slot."""
    return [e for e in edges if e["kind"] == "bsr" or e["class"] in ("direct", "indirect")]


# --------------------------------------------------------------------------
# Anchors
# --------------------------------------------------------------------------

def anchor_verdict(anchor_sec, secs, xrefs, callees, module_has_compressed):
    if anchor_sec is None:
        return "OUTSIDE-MODULE"
    if secs[anchor_sec]["compressed"]:
        return "COMPRESSED-ANCHOR"
    if not xrefs:
        return "INCONCLUSIVE" if module_has_compressed else "ABSENT"
    if callees:
        return "ENTERS-COMPRESSED"
    return "DECODABLE"


def anchor_report(mem, exec_plain, secs, ranges, va, module_has_compressed):
    anchor_sec = section_at(secs, va)
    xrefs = []
    for pool in sh4xref.pool_entries(mem, exec_plain, va):
        for load, reg in sh4xref.loads_of(mem, pool):
            xrefs.append({"kind": "pool", "pool": pool, "load": load, "reg": reg})
    for load, reg in sh4xref.loads_of(mem, va):
        xrefs.append({"kind": "slot", "pool": va, "load": load, "reg": reg})
    holders = {}
    for x in xrefs:
        x["fn"] = sh4xref.function_start(mem, x["load"])
        if x["fn"] is not None and x["fn"] not in holders:
            holders[x["fn"]] = function_edges(mem, x["fn"], ranges)
    callees = [e for fn in holders for e in calls_into_compressed(holders[fn])]
    verdict = anchor_verdict(anchor_sec, secs, xrefs, callees, module_has_compressed)
    return {
        "va": va,
        "section": anchor_sec,
        "xrefs": xrefs,
        "holders": sorted(holders),
        "callees": callees,
        "verdict": verdict,
        "exit": VERDICT_EXIT[verdict],
    }


# --------------------------------------------------------------------------
# Module report
# --------------------------------------------------------------------------

def module_report(data, image_start, module, anchors=()):
    secs = sections_of(data, image_start, module)
    c = census(secs)
    ranges = compressed_ranges(secs)
    mem, exec_plain = decodable_views(secs)
    edges = module_edges(mem, exec_plain, ranges)
    by_sec = {}
    for e in edges:
        by_sec.setdefault(e["sec"], []).append(e)
    module_has_compressed = c["compressed_sections"] > 0
    anchor_rows = [anchor_report(mem, exec_plain, secs, ranges, va, module_has_compressed)
                   for va in anchors]
    return {
        "module": module,
        "census": c,
        "compressed": [{"index": i, "realaddr": s["realaddr"], "vsize": s["vsize"],
                        "psize": s["psize"], "flags": s["flags"]}
                       for i, s in enumerate(secs) if s["compressed"]],
        "edges": tally_edges(edges),
        "edge_sections": {idx: tally_edges(es) for idx, es in sorted(by_sec.items())},
        "edge_section_va": {idx: secs[idx]["realaddr"] for idx in by_sec},
        "anchors": anchor_rows,
    }


def print_module(rep, img_name, img_sha, image_start):
    c = rep["census"]
    print("image     %s sha256=%s image_start=0x%08x" % (img_name, img_sha, image_start))
    print("module    %s sections=%d" % (rep["module"], c["sections"]))
    print("bytes (by vsize, the runtime extent)")
    print("  executable decodable %12d B" % c["exec_plain"])
    print("  executable compressed %10d B" % c["exec_compressed"])
    print("  data decodable       %12d B" % c["data_plain"])
    print("  data compressed      %12d B" % c["data_compressed"])
    print("  total vsize          %12d B, compressed %d B (%.1f %%)" % (
        c["total_vsize"], c["compressed_vsize"], 100 * c["compressed_share"]))
    for s in rep["compressed"]:
        print("  compressed section %d realaddr=0x%08x vsize=0x%08x stored psize=0x%08x flags=0x%08x" % (
            s["index"], s["realaddr"], s["vsize"], s["psize"], s["flags"]))
    e = rep["edges"]
    print("calls into compressed sections (decodable code, lower bounds):")
    print("  bsr %d | literal direct %d | literal indirect (through slot) %d | "
          "slot read %d | unclassified %d | data pointer %d" % (
              e["bsr_direct"], e["lit_direct"], e["lit_indirect"], e["lit_slot"],
              e["lit_unclassified"], e["lit_data"]))
    for idx, t in rep["edge_sections"].items():
        print("  -> compressed section %d (realaddr 0x%08x): bsr %d, direct %d, "
              "indirect %d, slot %d, unclassified %d, data %d" % (
                  idx, rep["edge_section_va"][idx], t["bsr_direct"], t["lit_direct"],
                  t["lit_indirect"], t["lit_slot"], t["lit_unclassified"], t["lit_data"]))
    for a in rep["anchors"]:
        print("anchor    0x%08x %s (exit %d) section=%s xrefs=%d holders=%d" % (
            a["va"], a["verdict"], a["exit"],
            "none" if a["section"] is None else str(a["section"]),
            len(a["xrefs"]), len(a["holders"])))
        note = {
            "COMPRESSED-ANCHOR": "the anchor's own bytes are in a compressed section",
            "ENTERS-COMPRESSED": "a decodable call leaves into a compressed section; its "
                                 "target is not readable from decodable bytes and may be "
                                 "plain code (UNKNOWN until the stored stream is decoded)",
            "INCONCLUSIVE": "no decodable xref; the module has compressed bytes",
            "ABSENT": "no decodable xref; the module has no compressed bytes",
        }.get(a["verdict"])
        if note:
            print("  note: " + note)
        for x in a["xrefs"][:LIST_LIMIT]:
            print("  %s load=0x%08x pool=0x%08x fn=%s" % (
                x["kind"], x["load"], x["pool"],
                "?" if x["fn"] is None else "0x%08x" % x["fn"]))
        if len(a["xrefs"]) > LIST_LIMIT:
            print("  ... %d more xrefs" % (len(a["xrefs"]) - LIST_LIMIT))
        for k in a["callees"][:LIST_LIMIT]:
            print("  holder calls compressed %s site=0x%08x target=0x%08x class=%s" % (
                k["kind"], k["site"] if k["site"] is not None else k["load"],
                k["target"], k["class"]))
        if len(a["callees"]) > LIST_LIMIT:
            print("  ... %d more compressed calls" % (len(a["callees"]) - LIST_LIMIT))


def table_rows(data, image_start):
    rom = cerom.CERom(data, image_start)
    rows = []
    for mod in rom.modules():
        name = mod["name"] if isinstance(mod, dict) else mod
        try:
            secs = sections_of(data, image_start, name)
        except Exception:
            continue
        c = census(secs)
        ranges = compressed_ranges(secs)
        mem, exec_plain = decodable_views(secs)
        t = tally_edges(module_edges(mem, exec_plain, ranges))
        rows.append((name, c, t))
    return rows


def print_table(rows, img_name, img_sha, image_start):
    print("image %s sha256=%s image_start=0x%08x" % (img_name, img_sha, image_start))
    print("%-22s %4s %10s %10s %6s %10s %6s %6s %6s" % (
        "module", "secs", "vsize", "compressed", "share", "exec_comp", "bsr", "direct", "indir"))
    for name, c, t in rows:
        print("%-22s %4d %10d %10d %5.1f%% %10d %6d %6d %6d" % (
            name, c["sections"], c["total_vsize"], c["compressed_vsize"],
            100 * c["compressed_share"], c["exec_compressed"],
            t["bsr_direct"], t["lit_direct"], t["lit_indirect"]))
    total = {k: sum(c[k] for _, c, _ in rows) for k in
             ("total_vsize", "compressed_vsize", "exec_compressed", "compressed_sections",
              "exec_plain", "data_plain", "data_compressed")}
    with_comp = sum(1 for _, c, _ in rows if c["compressed_sections"])
    print("modules %d, with a compressed section %d; compressed sections %d" % (
        len(rows), with_comp, total["compressed_sections"]))
    print("total vsize %d, compressed %d (%.1f %%), executable compressed %d, "
          "executable decodable %d" % (
              total["total_vsize"], total["compressed_vsize"],
              100 * total["compressed_vsize"] / max(1, total["total_vsize"]),
              total["exec_compressed"], total["exec_plain"]))


# --------------------------------------------------------------------------
# Self-test: synthetic SH-4 bytes, no vendor data
# --------------------------------------------------------------------------

def _w(buf, base, addr, word):
    buf[addr - base:addr - base + 2] = (word & 0xFFFF).to_bytes(2, "little")


def _l(buf, base, addr, value):
    buf[addr - base:addr - base + 4] = (value & 0xFFFFFFFF).to_bytes(4, "little")


def _movl(addr, reg, lit):
    d = (lit - ((addr + 4) & ~3)) // 4
    assert 0 <= d <= 0xFF and (lit - ((addr + 4) & ~3)) % 4 == 0
    return 0xD000 | reg << 8 | d


def _bsr(addr, target):
    d = (target - (addr + 4)) // 2
    assert -0x800 <= d < 0x800
    return 0xB000 | (d & 0xFFF)


JSR = lambda reg: 0x400B | reg << 8           # noqa: E731
MOVL_DEREF = lambda n, m: 0x6002 | n << 8 | m << 4  # noqa: E731
PROLOGUE = 0x2FE6
RTS = 0x000B
NOP = 0x0009


def _synthetic_image(with_compressed=True):
    """Plain code at 0x1000, compressed code at 0x1c00, compressed data at 0x2000,
    plain data at 0x2400. Every function is ``rts; nop; prologue; body``."""
    base = 0x1000
    buf = bytearray(0x800)
    code = {
        0x1000: RTS, 0x1002: NOP,
        0x1004: PROLOGUE, 0x1006: _movl(0x1006, 1, 0x1040), 0x1008: RTS, 0x100A: NOP,
        0x100C: PROLOGUE, 0x100E: _bsr(0x100E, 0x1C00), 0x1010: NOP, 0x1012: RTS, 0x1014: NOP,
        0x1016: PROLOGUE, 0x1018: _movl(0x1018, 2, 0x1400), 0x101A: JSR(2), 0x101C: NOP,
        0x101E: RTS, 0x1020: NOP,
        0x1022: PROLOGUE, 0x1024: _movl(0x1024, 3, 0x1404), 0x1026: _movl(0x1026, 2, 0x1408),
        0x1028: JSR(2), 0x102A: NOP, 0x102C: RTS, 0x102E: NOP,
        0x1030: PROLOGUE, 0x1032: _movl(0x1032, 5, 0x140C), 0x1034: MOVL_DEREF(6, 5),
        0x1036: JSR(6), 0x1038: NOP, 0x103A: RTS, 0x103C: NOP,
        0x1044: PROLOGUE, 0x1046: _movl(0x1046, 7, 0x1410), 0x1048: RTS, 0x104A: NOP,
        0x104C: PROLOGUE, 0x104E: _movl(0x104E, 9, 0x1414), 0x1050: MOVL_DEREF(10, 9),
        0x1052: RTS, 0x1054: NOP,
    }
    for a, w in code.items():
        _w(buf, base, a, w)
    for a, v in {0x1040: 0x1500, 0x1400: 0x1C20, 0x1404: 0x1600, 0x1408: 0x1C20,
                 0x140C: 0x1D00, 0x1410: 0x1C40, 0x1414: 0x1C50}.items():
        _l(buf, base, a, v)
    secs = [
        {"realaddr": 0x1000, "vsize": 0x800, "flags": 0x60000020, "compressed": False,
         "exec": True, "blob": bytes(buf)},
        {"realaddr": 0x2400, "vsize": 0x100, "flags": 0xC8000040, "compressed": False,
         "exec": False, "blob": bytes(0x100)},
    ]
    if with_compressed:
        secs += [
            {"realaddr": 0x1C00, "vsize": 0x400, "flags": 0x60002020, "compressed": True,
             "exec": True, "blob": None},
            {"realaddr": 0x2000, "vsize": 0x100, "flags": 0xC8002040, "compressed": True,
             "exec": False, "blob": None},
        ]
    return secs


def _check(fails, label, got, want):
    if got != want:
        fails.append("%s: got %r want %r" % (label, got, want))


def selftest_synthetic():
    fails = []
    secs = _synthetic_image(True)
    c = census(secs)
    _check(fails, "census total", c["total_vsize"], 0x800 + 0x400 + 0x100 + 0x100)
    _check(fails, "census compressed", c["compressed_vsize"], 0x500)
    _check(fails, "census exec compressed", c["exec_compressed"], 0x400)
    _check(fails, "census exec decodable", c["exec_plain"], 0x800)
    _check(fails, "census data compressed", c["data_compressed"], 0x100)
    _check(fails, "census data decodable", c["data_plain"], 0x100)
    _check(fails, "census sections", c["compressed_sections"], 2)

    ranges = compressed_ranges(secs)
    mem, exec_plain = decodable_views(secs)
    edges = module_edges(mem, exec_plain, ranges)
    classes = sorted((e["kind"], e["class"]) for e in edges)
    _check(fails, "edge classes", classes, sorted([
        ("bsr", "direct"), ("lit", "direct"), ("lit", "direct"), ("lit", "indirect"),
        ("lit", "slot"), ("lit", "data")]))
    _check(fails, "bsr target", [e["target"] for e in edges if e["kind"] == "bsr"], [0x1C00])
    # index of the compressed code section in the section list (plain, plain, comp, comp)
    _check(fails, "compressed sec index", {e["sec"] for e in edges}, {2})
    _check(fails, "calls exclude slot reads", len(calls_into_compressed(edges)), 4)

    def rep(va):
        return anchor_report(mem, exec_plain, secs, ranges, va, True)

    r = rep(0x1500)
    _check(fails, "plain anchor verdict", (r["verdict"], r["exit"]), ("DECODABLE", 0))
    r = rep(0x1600)
    _check(fails, "holder-calls-compressed verdict", (r["verdict"], r["exit"]),
           ("ENTERS-COMPRESSED", 2))
    _check(fails, "holder-calls-compressed xrefs", len(r["xrefs"]), 1)
    _check(fails, "holder callee class", [e["class"] for e in r["callees"]], ["direct"])
    r = rep(0x1C20)
    _check(fails, "compressed anchor verdict", (r["verdict"], r["exit"]),
           ("COMPRESSED-ANCHOR", 2))
    _check(fails, "compressed anchor pools", sorted(x["pool"] for x in r["xrefs"]),
           [0x1400, 0x1408])
    r = rep(0x1700)
    _check(fails, "no-xref with compressed bytes", (r["verdict"], r["exit"]),
           ("INCONCLUSIVE", 2))
    r = rep(0x3000)
    _check(fails, "outside module", (r["verdict"], r["exit"]), ("OUTSIDE-MODULE", 2))

    plain_only = _synthetic_image(False)
    pr = plain_only
    pranges = compressed_ranges(pr)
    pmem, pexec = decodable_views(pr)
    r = anchor_report(pmem, pexec, pr, pranges, 0x1700, False)
    _check(fails, "no-xref, no compressed bytes", (r["verdict"], r["exit"]), ("ABSENT", 1))
    r = anchor_report(pmem, pexec, pr, pranges, 0x1500, False)
    _check(fails, "plain-only module anchor", (r["verdict"], r["exit"]), ("DECODABLE", 0))
    return fails


def selftest_real(img):
    fails = []
    with open(img, "rb") as fh:
        data = fh.read(128 << 20)
    image_start = DEFAULT_IMAGE_START
    rom = cerom.CERom(data, image_start)
    names = [m["name"] if isinstance(m, dict) else m for m in rom.modules()]
    tot = {"total_vsize": 0, "compressed_vsize": 0, "exec_compressed": 0,
           "exec_plain": 0, "compressed_sections": 0}
    with_comp = 0
    navi = None
    edges = {"bsr": 0, "direct": 0, "indirect": 0}
    for name in names:
        secs = sections_of(data, image_start, name)
        c = census(secs)
        for k in tot:
            tot[k] += c[k]
        with_comp += 1 if c["compressed_sections"] else 0
        mem, exec_plain = decodable_views(secs)
        mod_edges = calls_into_compressed(module_edges(mem, exec_plain, compressed_ranges(secs)))
        for e in mod_edges:
            edges["bsr" if e["kind"] == "bsr" else e["class"]] += 1
        if name == "Navi.exe":
            navi = (c, secs, sum(1 for e in mod_edges if e["kind"] == "bsr"))
    _check(fails, "modules", len(names), REAL_PINS["modules"])
    _check(fails, "modules with compressed section", with_comp,
           REAL_PINS["modules_with_compressed"])
    for k in tot:
        _check(fails, k, tot[k], REAL_PINS[k])
    c, secs, navi_bsr = navi
    _check(fails, "Navi bsr edges into compressed", navi_bsr, REAL_PINS["navi_edges_bsr"])
    _check(fails, "edges bsr", edges["bsr"], REAL_PINS["edges_bsr"])
    _check(fails, "edges direct", edges["direct"], REAL_PINS["edges_direct"])
    _check(fails, "edges indirect", edges["indirect"], REAL_PINS["edges_indirect"])
    _check(fails, "Navi compressed vsize", c["compressed_vsize"],
           REAL_PINS["navi_compressed_vsize"])
    _check(fails, "Navi compressed realaddrs",
           [s["realaddr"] for s in secs if s["compressed"]],
           REAL_PINS["navi_compressed_realaddrs"])

    # Controls on the M3.15 path (C-2200..C-2202): the literal-pool counts agree
    # with sh4xref.py --to, and the call site at 0x004125de is an indirect call
    # through the slot 0x0055d924 (C-2207).
    ranges = compressed_ranges(secs)
    mem, exec_plain = decodable_views(secs)
    pools = sh4xref.pool_entries(mem, exec_plain, 0x0055D924)
    loads = [x for p in pools for x in sh4xref.loads_of(mem, p)]
    _check(fails, "pools of 0x0055d924", len(pools), 25)
    _check(fails, "loads of 0x0055d924", len(loads), 29)
    pools = sh4xref.pool_entries(mem, exec_plain, 0x0055D954)
    loads = [x for p in pools for x in sh4xref.loads_of(mem, p)]
    _check(fails, "pools of 0x0055d954", len(pools), 320)
    _check(fails, "loads of 0x0055d954", len(loads), 663)
    edges = function_edges(mem, 0x004125A8, ranges)
    _check(fails, "fn 0x004125a8 compressed edges",
           [(e["load"], e["target"], e["class"]) for e in edges],
           [(0x004125DE, 0x0055D924, "indirect"),
            (0x004125EE, 0x00D94100, "unclassified"),
            (0x00412650, 0x00D535B8, "unclassified")])
    r = anchor_report(mem, exec_plain, secs, ranges, 0x0055D924, True)
    _check(fails, "anchor 0x0055d924 in compressed sec1", r["verdict"], "COMPRESSED-ANCHOR")
    return fails


def selftest(img=None):
    failures = selftest_synthetic()
    print("synthetic checks: %s" % ("PASS" if not failures else "FAIL"))
    status = 0 if not failures else 1
    for f in failures:
        print("  FAIL", f)
    if img is None:
        print("real build-A pins: SKIP (no image; pass IMG or set OSM2LEAF_IMG)")
        return status
    real = selftest_real(img)
    print("real build-A pins (%s): %s" % (os.path.basename(img), "PASS" if not real else "FAIL"))
    for f in real:
        print("  FAIL", f)
    return status or (1 if real else 0)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("image", nargs="?", help="firmware image (default: $OSM2LEAF_IMG or archive/head256.img)")
    p.add_argument("--image-start", type=lambda s: int(s, 0), default=DEFAULT_IMAGE_START)
    p.add_argument("--module", help="module name, e.g. Navi.exe")
    p.add_argument("--anchor", action="append", default=[], type=lambda s: int(s, 0),
                   metavar="VA", help="anchor VA (repeatable)")
    p.add_argument("--table", action="store_true", help="per-module table for every module")
    p.add_argument("--selftest", action="store_true", help="synthetic checks, plus real pins if an image is found")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.selftest:
        img = args.image or default_image()
        return selftest(img if img and os.path.isfile(img) else None)
    if not args.module and not args.table:
        build_parser().error("give --module NAME or --table")
    img = args.image or default_image()
    if img is None or not os.path.isfile(img):
        print("reader_precheck: no image (pass IMG or set OSM2LEAF_IMG); nothing runnable",
              file=sys.stderr)
        return 3
    data = pw.load_image(img)
    img_name = os.path.basename(img)
    img_sha = sha256_file(img)
    if args.table:
        print_table(table_rows(data, args.image_start), img_name, img_sha, args.image_start)
        return 0
    rep = module_report(data, args.image_start, args.module, args.anchor)
    print_module(rep, img_name, img_sha, args.image_start)
    codes = [a["exit"] for a in rep["anchors"]]
    return max(codes) if codes else 0


if __name__ == "__main__":
    sys.exit(main())
