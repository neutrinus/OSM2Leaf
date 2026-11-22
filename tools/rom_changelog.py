#!/usr/bin/env python3
"""Per-module changelog between two ZE0 builds: functions, strings, exports, COM.

M1.36b's atlas says *which* modules read different after reloc masking; it does
not say *what* changed inside one. This tool diffs one module across two builds,
reusing what the repo already has:

  - **functions** from ``tools/pdata.py``; a module whose ``.pdata`` section is
    compressed is decoded with the **build's own kernel** ``DECOMP_SECT``. That
    routine moved (EU2011 ``0x88037464``, EU2014/EU2016 ``0x88037994``), so it
    is located by matching the reloc-masked digest of the EU2011 reference
    function in the build's own ``nk.exe`` (no fitted address);
  - **function identity** through ``tools/fn_match.py``'s reloc-masked
    fingerprint. Functions are compared as *digest sets*, not one-to-one: a
    module full of duplicated leaf bodies (``BT_ENG.dll``) otherwise loses rows
    to ``AMBIGUOUS`` and a code-identical module reads "changed";
  - **strings**: printable ASCII runs (>= 6 bytes) of the module's **plain**
    sections. Compressed sections decode only to their ``r0`` prefix (the
    import/BSS head), not their full VSIZE, so they are outside the diff corpus
    and every row counts them (``csec``);
  - **exports** from ``cerom``'s export table; **COM methods** from the plain
    ``.rgs`` co-class text (``rom_atlas.parse_rgs_classes``).

The **match rate** is ``shared / max(A, B)`` over the two digest sets: the
fraction of the larger build found in the other, so a module that only grew
reads high and one that replaced most of its code reads low. A module below
``REWRITE_THRESHOLD`` (0.50) is reported ``rewritten`` and its changed
functions are not named (Stop rule: a rewritten module is not diffed by hand).
``gap`` counts differing halfwords **outside** every ``.pdata`` record (leaf
code with no record, and literal-pool data): a module can have a 100 % recorded
match and still differ there, which is why the atlas calls it different.

Usage
-----
    rom_changelog.py --selftest
    rom_changelog.py table --left EU2011=PATH --right EU2014=PATH
        [--modules Navi.exe BT_MGR.dll ...] [--ref-kernel PATH]
        [--json OUT] [-o OUT.md]
    rom_changelog.py control --left EU2011=PATH --right US2011=PATH \\
        --build B

``--build B`` restricts ``control`` to build B; the control passes only when
every listed module has 0 added and 0 removed digest and a positive shared
count (EU2011 vs US2011 build B is byte-identical, C-6281).

Exit codes: 0 ok, 1 a row failed unexpectedly or a control disagreed, 2 usage or
unreadable input.
"""

from __future__ import annotations

import argparse
import bisect
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import cerom  # noqa: E402
import fn_match  # noqa: E402
import nk_decomp  # noqa: E402
import pdata  # noqa: E402
import rom_atlas  # noqa: E402

READ_LIMIT = 128 << 20
DEFAULT_STARTS = {"A": 0x200200, "B": 0x3e00200, "C": 0x5200200}
REWRITE_THRESHOLD = 0.50
MIN_STRING = 8
STRING_RE = re.compile(rb"[\x20-\x7e]{%d,}" % MIN_STRING)
# A raw printable run is the standard ``strings`` definition and is noisy
# inside a code section; the *sample* only keeps runs that read like a message
# (a word plus a space, or a printf/error marker) so a reader can judge.
_MESSAGE_CHARS = re.compile(r"[A-Za-z0-9 _.:%/()\[\]{},<>=\-+*'\"!?]")


def message_like(text: str) -> bool:
    if len(text) < MIN_STRING or " " not in text:
        return False
    if not any(c.isalpha() for c in text):
        return False
    good = sum(1 for c in text if _MESSAGE_CHARS.match(c))
    return good >= 0.95 * len(text)
REF_DECOMP_VA = 0x88037464          # EU2011 build-B DECOMP_SECT (C-662)
REF_KERNEL_DEFAULT = "archive/head256.img"

DEFAULT_MODULES = ["Navi.exe", "Audio.exe", "BT_MGR.dll", "BT_ENG.dll",
                   "BT_FW.dll", "Speech.exe", "DriveComputerCC.dll"]


# --------------------------------------------------------------------------
# Kernel DECOMP_SECT discovery (the newer kernels moved the routine)
# --------------------------------------------------------------------------


def _nk_functions(data, start):
    rom = cerom.CERom(data, start)
    mod = rom.module("nk.exe")
    recs, _meta = pdata.load_table(data, start, "nk.exe")
    secs = list(rom.o32(mod))
    lo = min(s["realaddr"] for s in secs)
    hi = max(s["realaddr"] + s["vsize"] for s in secs)
    code = next((s for s in secs if s["flags"] & cerom.MEM_EXECUTE), secs[0])
    off = rom.va2file(code["dataptr"])
    return fn_match.collect_functions(data, code, off, recs, (lo, hi))


def discover_decomp_sect(data, ref_data):
    """VA of this image's kernel ``DECOMP_SECT``, matched from the reference.

    ``ref_data`` is an image whose build B holds ``DECOMP_SECT`` at
    ``REF_DECOMP_VA`` (EU2011). The reference function's reloc-masked digest is
    looked up in *this* image's ``nk.exe``; a single hit is that build's
    ``DECOMP_SECT``. Returns ``None`` when it is not found exactly once (the
    caller then reports, never guesses).
    """
    want = None
    for va, words, lr, cb, base in _nk_functions(ref_data, DEFAULT_STARTS["B"]):
        if va == REF_DECOMP_VA:
            want = fn_match.fingerprint(words, va, lr, cb, base)[0]
            break
    if want is None:
        return None
    hits = [va for va, words, lr, cb, base in
            _nk_functions(data, DEFAULT_STARTS["B"])
            if fn_match.fingerprint(words, va, lr, cb, base)[0] == want]
    return hits[0] if len(hits) == 1 else None


# --------------------------------------------------------------------------
# Function table of one module
# --------------------------------------------------------------------------


def module_records(data, start, module, entry):
    rom = cerom.CERom(data, start)
    mod = rom.module(module)
    index, sec, off = pdata.find_pdata_section(rom, mod)
    rva, size = pdata.exception_entry(rom, mod)
    compressed = bool(sec["flags"] & cerom.IMAGE_SCN_COMPRESSED)
    if compressed:
        if entry is None:
            raise pdata.PdataError(
                "module %s sec%d: .pdata compressed, no kernel DECOMP_SECT"
                % (module, index))
        file_off = rom.va2file(sec["dataptr"])
        r0, out = nk_decomp.decompress(data, file_off, sec["psize"],
                                       sec["vsize"], entry=entry)
        if off + size > r0:
            raise pdata.PdataError(
                "module %s sec%d: decoded %#x < .pdata end %#x"
                % (module, index, r0, off + size))
        blob = out[off:off + size]
    else:
        file_off = rom.va2file(sec["dataptr"])
        blob = data[file_off + off:file_off + off + size]
    records = nk_decomp.parse_pdata(blob)
    pdata.validate_sorted(records, "module %s: " % module)
    return records, {"section": index, "compressed": compressed,
                     "count": len(records)}


def module_functions(data, start, module, entry):
    """``[(va, digest, words)]`` for every ``.pdata`` record inside the code."""
    rom = cerom.CERom(data, start)
    mod = rom.module(module)
    recs, meta = module_records(data, start, module, entry)
    secs = list(rom.o32(mod))
    lo = min(s["realaddr"] for s in secs)
    hi = max(s["realaddr"] + s["vsize"] for s in secs)
    code = next((s for s in secs if s["flags"] & cerom.MEM_EXECUTE), secs[0])
    off = rom.va2file(code["dataptr"])
    funcs = fn_match.collect_functions(data, code, off, recs, (lo, hi))
    out = []
    for va, words, lr, cb, base in funcs:
        digest, _bsr, _pool = fn_match.fingerprint(words, va, lr, cb, base)
        out.append((va, digest, words))
    meta["in_code"] = len(out)
    return out, meta


def digest_sets(va_rows):
    """``{digest: [VA, ...]}`` -- set comparison, duplicate bodies kept."""
    out: dict[str, list[int]] = {}
    for va, digest, _w in va_rows:
        out.setdefault(digest, []).append(va)
    return out


# --------------------------------------------------------------------------
# Strings, exports, COM co-classes
# --------------------------------------------------------------------------


def module_strings(data, start, module):
    """Printable ASCII runs of the module's plain sections + compressed count."""
    rom = cerom.CERom(data, start)
    mod = rom.module(module)
    strings, compressed = set(), 0
    for sec in rom.o32(mod):
        if sec["flags"] & cerom.IMAGE_SCN_COMPRESSED:
            compressed += 1
            continue
        off = rom.va2file(sec["dataptr"])
        for m in STRING_RE.finditer(data[off:off + sec["vsize"]]):
            strings.add(m.group(0).decode("latin1"))
    return strings, compressed


def function_strings(rom, module, va, words):
    """C strings a function *names*, from its literal-pool pointers.

    A pool load's target is read from the module's code section (the pool may
    sit past the function's ``.pdata`` length); a value inside the module's own
    VA range is followed through ``realaddr2file`` to a printable ASCII run.
    Returns at most three, sorted; an empty list when the function names none.
    """
    mod = rom.module(module)
    secs = list(rom.o32(mod))
    lo = min(s["realaddr"] for s in secs)
    hi = max(s["realaddr"] + s["vsize"] for s in secs)
    code = next((x for x in secs if x["flags"] & cerom.MEM_EXECUTE), None)
    if code is None:
        return []
    off = rom.va2file(code["dataptr"])
    cb = rom.d[off:off + code["vsize"]]
    base = code["realaddr"]
    found: list[str] = []
    for i, w in enumerate(words):
        if not fn_match.is_mov_pc(w):
            continue
        lit = fn_match.pool_addr(va + 2 * i, w)
        po = lit - base
        if not (0 <= po and po + 4 <= len(cb)):
            continue
        val = int.from_bytes(cb[po:po + 4], "little")
        if not (lo <= val < hi):
            continue
        fo = rom.realaddr2file(val)
        if fo is None:
            continue
        m = STRING_RE.match(rom.d, fo)
        if m:
            found.append(m.group(0).decode("latin1"))
    return sorted(set(found))[:3]


def module_exports(rom, module):
    mod = rom.module(module)
    return {name for _o, name, _r in rom.exports(mod)}


def module_com(rom, module):
    mod = rom.module(module)
    return {"%s.%s" % c for c in rom_atlas.module_com_classes(rom, mod)}


def raw_section_equal(data_a, start_a, data_b, start_b, module):
    """True when the two builds' executable section bytes are identical.

    This is the raw (unmasked) equality ``rom_atlas`` reports as "different";
    quoting it next to the function match shows whether a 100 % recorded match
    (with a small ``gap``) is the only difference, or the code really moved.
    """
    _ra, ca, cb_a = _code_bytes(data_a, start_a, module)
    _rb, cb_, cb_b = _code_bytes(data_b, start_b, module)
    if ca is None or cb_ is None:
        return None
    n = min(ca["vsize"], cb_["vsize"], len(cb_a), len(cb_b))
    return cb_a[:n] == cb_b[:n] and ca["vsize"] == cb_["vsize"]


# --------------------------------------------------------------------------
# Gap halfwords (leaf code with no .pdata record, and literal-pool data)
# --------------------------------------------------------------------------


def _code_bytes(data, start, module):
    rom = cerom.CERom(data, start)
    code = next((s for s in rom.o32(rom.module(module))
                 if s["flags"] & cerom.MEM_EXECUTE), None)
    if code is None:
        return rom, None, None
    off = rom.va2file(code["dataptr"])
    return rom, code, data[off:off + code["vsize"]]


def _coverage_offsets(records, base):
    """Sorted ``[(lo_off, hi_off)]`` of a build's records, section-relative."""
    iv = sorted((r[0] - base, r[0] - base + r[2]) for r in records)
    merged = []
    for lo, hi in iv:
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def _covered(merged, off):
    i = bisect.bisect_right(merged, (off, float("inf"))) - 1
    return i >= 0 and merged[i][0] <= off < merged[i][1]


def gap_halfwords_changed(data_a, start_a, data_b, start_b, module,
                          entry_a, entry_b):
    """``(differing halfwords, total)`` at equal section offsets outside records.

    A module can have a 100 % recorded-function match and still differ in a
    leaf body (no record) or a literal pool in a gap; the section hash
    ``rom_atlas`` uses sees that, the function digest does not. A halfword is
    "outside records" only when no ``.pdata`` record of *either* build covers
    that section offset. The count includes relocated literal-pool words, so it
    is a lower bound of what the function diff did not look at, not a semantic
    change count.
    """
    rom_a, code_a, cb_a = _code_bytes(data_a, start_a, module)
    _rom_b, code_b, cb_b = _code_bytes(data_b, start_b, module)
    if code_a is None or code_b is None:
        return 0, 0
    rec_a, _ = module_records(data_a, start_a, module, entry_a)
    rec_b, _ = module_records(data_b, start_b, module, entry_b)
    cov_a = _coverage_offsets(rec_a, code_a["realaddr"])
    cov_b = _coverage_offsets(rec_b, code_b["realaddr"])
    size = min(code_a["vsize"], len(cb_a), code_b["vsize"], len(cb_b))
    diff = total = 0
    for o in range(0, size - 1, 2):
        if _covered(cov_a, o) or _covered(cov_b, o):
            continue
        total += 1
        if cb_a[o] != cb_b[o] or cb_a[o + 1] != cb_b[o + 1]:
            diff += 1
    return diff, total


# --------------------------------------------------------------------------
# One module diff
# --------------------------------------------------------------------------


def diff_module(data_a, start_a, data_b, start_b, module, entry_a, entry_b):
    fa, meta_a = module_functions(data_a, start_a, module, entry_a)
    fb, meta_b = module_functions(data_b, start_b, module, entry_b)
    da, db = digest_sets(fa), digest_sets(fb)
    shared = set(da) & set(db)
    only_a, only_b = set(da) - set(db), set(db) - set(da)
    larger = max(len(da), len(db))
    match_rate = (len(shared) / larger) if larger else 1.0
    rewritten = match_rate < REWRITE_THRESHOLD
    gap_diff, gap_halfwords = gap_halfwords_changed(
        data_a, start_a, data_b, start_b, module, entry_a, entry_b)
    row = {
        "module": module,
        "funcs_a": meta_a["in_code"], "funcs_b": meta_b["in_code"],
        "digests_a": len(da), "digests_b": len(db),
        "shared": len(shared), "only_a": len(only_a), "only_b": len(only_b),
        "match_rate": round(match_rate, 4), "rewritten": rewritten,
        "gap_diff": gap_diff, "gap_halfwords": gap_halfwords,
        "raw_section_equal": raw_section_equal(
            data_a, start_a, data_b, start_b, module),
    }
    sa, ca = module_strings(data_a, start_a, module)
    sb, cb = module_strings(data_b, start_b, module)
    row.update({
        "strings_a": len(sa), "strings_b": len(sb),
        "strings_added": len(sb - sa), "strings_removed": len(sa - sb),
        "compressed_sections_a": ca, "compressed_sections_b": cb,
        "strings_added_sample": [x for x in sorted(sb - sa) if message_like(x)][:8],
        "strings_removed_sample": [x for x in sorted(sa - sb) if message_like(x)][:8],
    })
    rom_a, rom_b = cerom.CERom(data_a, start_a), cerom.CERom(data_b, start_b)
    ea, eb = module_exports(rom_a, module), module_exports(rom_b, module)
    row.update({"exports_a": len(ea), "exports_b": len(eb),
                "exports_added": sorted(eb - ea),
                "exports_removed": sorted(ea - eb)})
    com_a, com_b = module_com(rom_a, module), module_com(rom_b, module)
    row.update({"com_a": sorted(com_a), "com_b": sorted(com_b),
                "com_added": sorted(com_b - com_a),
                "com_removed": sorted(com_a - com_b)})
    changed = []
    if not rewritten:
        items = []
        for digest in only_a | only_b:
            in_a, in_b = da.get(digest), db.get(digest)
            rows = fa if in_a else fb
            va = (in_a or in_b)[0]
            words = next(w for v, _d, w in rows if v == va)
            tag = "changed" if in_a and in_b else ("removed" if in_a else "added")
            items.append((len(words), va, tag, words))
        items.sort(reverse=True)
        by_va = {}
        for _n, va, tag, words in items:
            prev = by_va.get(va)
            if prev is not None and prev["tag"] != tag:
                # same address in both builds, different code: rewritten in place
                prev["tag"] = "changed"
                continue
            by_va[va] = {"va": "0x%x" % va, "tag": tag,
                         "strings": function_strings(rom_a, module, va, words)}
        changed = list(by_va.values())[:20]
    row["top_changed"] = changed
    return row


# --------------------------------------------------------------------------
# Pairs and control
# --------------------------------------------------------------------------


def load_head(path):
    with open(path, "rb") as fh:
        return fh.read(READ_LIMIT)


def locate_segment(data, module, want_build=None):
    """``(start, key)`` of the segment that holds ``module``."""
    segments, _dups = cerom.find_segments(data)
    by_start = {start: key for key, start in DEFAULT_STARTS.items()}
    for seg in segments:
        key = by_start.get(seg.start, "?")
        if want_build and key != want_build:
            continue
        for m in seg.modules():
            if m["name"] and m["name"].lower() == module.lower():
                return seg.start, key
    raise KeyError(module)


class Context:
    """One image: its bytes, kernel DECOMP_SECT and a segment-name cache."""

    def __init__(self, path, ref_data):
        self.path = path
        self.data = load_head(path)
        self.sha = rom_atlas.sha256_of(path)
        self.entry = discover_decomp_sect(self.data, ref_data)

    def locate(self, module, want_build=None):
        return locate_segment(self.data, module, want_build)


def diff_pair(label_a, ctx_a, label_b, ctx_b, modules):
    rows = []
    for module in modules:
        try:
            start_a, key_a = ctx_a.locate(module)
            start_b, key_b = ctx_b.locate(module)
        except KeyError:
            rows.append({"module": module, "absent": True})
            continue
        try:
            row = diff_module(ctx_a.data, start_a, ctx_b.data, start_b,
                              module, ctx_a.entry, ctx_b.entry)
        except pdata.PdataError as exc:
            rows.append({"module": module, "error": str(exc)})
            continue
        row["segment"] = key_a if key_a == key_b else "%s/%s" % (key_a, key_b)
        rows.append(row)
    return {"left": label_a, "right": label_b,
            "left_sha": ctx_a.sha, "right_sha": ctx_b.sha,
            "decomp_sect": {"left": None if ctx_a.entry is None else "0x%x" % ctx_a.entry,
                            "right": None if ctx_b.entry is None else "0x%x" % ctx_b.entry},
            "rows": rows}


def render_pair(pair):
    out = ["#### %s -> %s" % (pair["left"], pair["right"]), "",
           "left `%s`  right `%s`  DECOMP_SECT %s / %s" % (
               pair["left_sha"], pair["right_sha"],
               pair["decomp_sect"]["left"], pair["decomp_sect"]["right"]), "",
           "| module | seg | fn A | fn B | shared | +fn | -fn | match | "
           "verdict | gap | sec | csec | +str | -str | +exp | +COM |",
           "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- "
           "| ---: | :-: | ---: | ---: | ---: | ---: | ---: |"]
    for r in pair["rows"]:
        if r.get("absent"):
            out.append("| %s | - | - | - | - | - | - | - | absent | - | - "
                       "| - | - | - | - | - |" % r["module"])
            continue
        if r.get("error"):
            out.append("| %s | - | - | - | - | - | - | - | error: %s "
                       "| - | - | - | - | - | - | - |" % (r["module"], r["error"][:36]))
            continue
        verdict = "rewritten" if r["rewritten"] else "diffed"
        sec = "yes" if r["raw_section_equal"] else "no"
        out.append("| %s | %s | %d | %d | %d | %d | %d | %.1f%% | %s | %d "
                   "| %s | %d | %d | %d | %d | %d |" % (
                       r["module"], r["segment"], r["funcs_a"], r["funcs_b"],
                       r["shared"], r["only_b"], r["only_a"],
                       100 * r["match_rate"], verdict, r["gap_diff"], sec,
                       r["compressed_sections_a"], r["strings_added"],
                       r["strings_removed"], len(r["exports_added"]),
                       len(r["com_added"])))
    out.append("")
    return out


def render_detail(pair):
    """Per-module detail: counts, string samples, top changed functions."""
    out = ["#### %s -> %s — per-module detail" % (pair["left"], pair["right"]), ""]
    for r in pair["rows"]:
        if r.get("absent") or r.get("error"):
            continue
        out.append("**%s** — %d -> %d records, %d shared, +%d / -%d functions, "
                   "match %.1f%%, gap %d differs, raw exec section %s" % (
                       r["module"], r["funcs_a"], r["funcs_b"], r["shared"],
                       r["only_b"], r["only_a"], 100 * r["match_rate"],
                       r["gap_diff"],
                       "equal" if r["raw_section_equal"] else "different"))
        out.append("")
        out.append("strings %d -> %d (+%d / -%d); exports %d -> %d; COM %d -> %d"
                   % (r["strings_a"], r["strings_b"], r["strings_added"],
                      r["strings_removed"], r["exports_a"], r["exports_b"],
                      len(r["com_a"]), len(r["com_b"])))
        for label, sample in (("added", r["strings_added_sample"]),
                              ("removed", r["strings_removed_sample"])):
            if sample:
                out.append("- strings %s: %s" % (
                    label, "; ".join("`%s`" % x[:60] for x in sample[:4])))
        if r["exports_added"]:
            out.append("- exports added: %s" % ", ".join(
                "`%s`" % x for x in r["exports_added"][:10]))
        if r["exports_removed"]:
            out.append("- exports removed: %s" % ", ".join(
                "`%s`" % x for x in r["exports_removed"][:10]))
        if r["com_added"] or r["com_removed"]:
            out.append("- COM +%s -%s" % (r["com_added"], r["com_removed"]))
        if r["rewritten"]:
            out.append("- **rewritten** (match < 50%): changed functions not "
                       "named, per the Stop rule")
        elif r["top_changed"]:
            out.append("")
            out.append("| # | VA | change | strings |")
            out.append("| ---: | --- | --- | --- |")
            for i, c in enumerate(r["top_changed"], 1):
                out.append("| %d | `%s` | %s | %s |" % (
                    i, c["va"], c["tag"],
                    "; ".join("`%s`" % x[:70] for x in c["strings"][:2])))
        else:
            out.append("- no recorded function changes")
        out.append("")
    return out


# --------------------------------------------------------------------------
# Selftest (synthetic, no vendor bytes)
# --------------------------------------------------------------------------


def selftest() -> int:
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))
        print("%s %s" % ("ok  " if cond else "FAIL", name))

    rows = [(0x10, "aa", [1, 2]), (0x20, "aa", [3, 4]), (0x30, "bb", [5, 6])]
    ds = digest_sets(rows)
    check("digest_sets groups duplicate bodies", ds["aa"] == [0x10, 0x20])
    check("digest_sets keeps a singleton", ds["bb"] == [0x30])
    check("duplicate-insensitive shared count",
          len(set(ds) & {"aa"}) == 1)

    blob = b"ABCDEFGH"
    check("STRING_RE finds an 8-byte ASCII run",
          STRING_RE.search(blob).group(0) == b"ABCDEFGH")
    check("STRING_RE rejects a 5-byte run", STRING_RE.search(b"abcde") is None)
    check("message_like accepts a printf message",
          message_like("meshID(%x) x,y(%d,%d)"))
    check("message_like rejects binary noise", not message_like(" 7-o{sZ"))
    # The match-rate definition: shared / max(A, B).
    rate = lambda a, b: len(set(a) & set(b)) / max(len(set(a)), len(set(b)))
    check("match rate identical is 1.0", rate(["x", "y"], ["y", "x"]) == 1.0)
    check("match rate disjoint is 0.0", rate(["x"], ["y"]) == 0.0)
    check("match rate of a doubled set is 0.5", rate(["x", "y"], ["x", "y", "z", "w"]) == 0.5)
    check("REWRITE_THRESHOLD is the Stop rule", REWRITE_THRESHOLD == 0.50)

    bad = [n for n, ok in checks if not ok]
    print("%d checks, %d failures" % (len(checks), len(bad)))
    return 1 if bad else 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_named(items):
    out = {}
    for item in items:
        name, _, path = item.partition("=")
        out[name] = path
    return out


def single(named):
    if len(named) != 1:
        raise SystemExit("need exactly one NAME=PATH")
    return next(iter(named.items()))


def cmd_table(args):
    la, pa = single(parse_named(args.left))
    lb, pb = single(parse_named(args.right))
    ref = load_head(args.ref_kernel) if args.ref_kernel else load_head(REF_KERNEL_DEFAULT)
    ctx_a, ctx_b = Context(pa, ref), Context(pb, ref)
    pair = diff_pair(la, ctx_a, lb, ctx_b, args.modules or DEFAULT_MODULES)
    pair["ref_kernel"] = args.ref_kernel or REF_KERNEL_DEFAULT
    lines = render_pair(pair)
    if args.detail:
        lines += render_detail(pair)
    text = "\n".join(lines)
    if args.json:
        Path(args.json).write_text(json.dumps(pair, indent=1))
    if args.output:
        Path(args.output).write_text(text + "\n")
    else:
        print(text)
    return 1 if any(r.get("error") for r in pair["rows"]) else 0


def cmd_control(args):
    la, pa = single(parse_named(args.left))
    lb, pb = single(parse_named(args.right))
    ref = load_head(args.ref_kernel) if args.ref_kernel else load_head(REF_KERNEL_DEFAULT)
    ctx_a, ctx_b = Context(pa, ref), Context(pb, ref)
    print("control %s -> %s  build %s" % (la, lb, args.build))
    ok = True
    for module in args.modules or DEFAULT_MODULES:
        try:
            start_a, _ = ctx_a.locate(module, args.build)
            start_b, _ = ctx_b.locate(module, args.build)
        except KeyError:
            print("  %-22s absent in build %s" % (module, args.build))
            ok = False
            continue
        fa, _ = module_functions(ctx_a.data, start_a, module, ctx_a.entry)
        fb, _ = module_functions(ctx_b.data, start_b, module, ctx_b.entry)
        da, db = digest_sets(fa), digest_sets(fb)
        shared = len(set(da) & set(db))
        only_a, only_b = len(set(da) - set(db)), len(set(db) - set(da))
        good = only_a == 0 and only_b == 0 and shared > 0
        ok = ok and good
        print("  %-22s shared=%d +%d -%d %s" % (
            module, shared, only_b, only_a, "OK" if good else "CHANGED"))
    print("control %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("table", "control"):
        p = sub.add_parser(name)
        p.add_argument("--left", action="append", required=True, metavar="N=PATH")
        p.add_argument("--right", action="append", required=True, metavar="N=PATH")
        p.add_argument("--modules", nargs="*", default=None)
        p.add_argument("--ref-kernel", default=None)
        if name == "table":
            p.add_argument("--json", default=None)
            p.add_argument("-o", "--output", default=None)
            p.add_argument("--detail", action="store_true",
                           help="append the per-module changed-function detail")
        else:
            p.add_argument("--build", default="B", choices=sorted(DEFAULT_STARTS))
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "table":
        return cmd_table(args)
    if args.cmd == "control":
        return cmd_control(args)
    print("--selftest or a subcommand is required", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
