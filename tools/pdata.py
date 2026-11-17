#!/usr/bin/env python3
"""Function table (SH-4 ``.pdata``) of every CE module in the ZE0 nav image.

Finds the ``.pdata`` section of a module from the e32 header's exception
directory entry (``cerom.e32()["exception"]`` = units[6:8] of the data
directory), not from "the last compressed section".  The exception directory
holds the RVA and size of the table; the table itself is 8-byte records
(``u32 begin``, ``u32`` packed word: bits 0-7 prologue length in 2-byte
instructions, bits 8-29 function length in instructions, bits 30/31 flags),
verified on ``Navi.exe`` (EU 2011, build A) by H51: 7,596 records, strictly
ascending, ``0x0032ed9c..0x00558300`` (C-3483).

Compressed sections are decoded with ``tools/nk_decomp.py`` (the firmware's
own kernel routine in PySh4) rather than re-implemented.  Decoded pdata
slices are cached on disk, keyed by the SHA-256 of the stored section bytes;
the default cache is ``/tmp/opencode/work/m1.20/decomp`` (override with
``--cache DIR`` or ``$OSM2LEAF_PDATA_CACHE``).  Nothing from the cache is
committed to the repo.

Usage:
  pdata.py table IMG --module M [--image-start 0x200200] [--json] [--cache DIR]
  pdata.py fn    IMG --module M [--image-start 0x200200] [--cache DIR] VA...
  pdata.py gaps  IMG --module M [--image-start 0x200200] [--cache DIR]
  pdata.py leaves IMG --module M [--cap 0x400] [--verbose] [--cache DIR]
  pdata.py census IMG [--image-start S] [--json] [--check-fixture FILE]
  pdata.py where IMG --module M [--image-start S] [--try-index N] [--cache DIR]
  pdata.py --selftest

``table`` prints one line per record and a trailing summary; ``--json``
emits one object with the full record list.  ``fn`` classifies each VA as
START / INSIDE / GAP / BEFORE.  ``gaps`` lists executable-section ranges
longer than 8 bytes with no record; a gap that is the target of a ``bsr`` or
of a directly-called ``mov.l`` literal is marked ``leaf`` (leaf functions
have no record).  A module with no exception directory is listed as such,
never guessed (exit 3).  An unsorted table fails loudly (exit 2).
``leaves`` is the census: over every gap it reports the total, the ``leaf``
count, how many end in their own ``rts`` inside the uncapped natural bound
(next pdata START / called entry / code end), how many have a natural bound
past the ``0x400`` cap with their ``rts`` at or beyond it (the cap class, one
VA per line), and how many have no ``rts`` at all (stubs), plus a histogram.  ``--called`` picks the call set
that bounds a gap: ``gaps`` (default) = every call target that is itself a gap
start (the docstring's "called GAP"), ``records`` = calls made from pdata-
recorded functions only (``fn_match``'s clamp), ``all`` = every halfword.

``census`` walks every module of one CE segment and prints
``module records section compressed`` per module (or ``NO-PDATA`` when the
e32 exception directory is ``(0, 0)``), then the loaded/without split and
the record total.  Only ``(0, 0)`` counts as no pdata: a decode or sort
failure is printed as ``ERROR``, is counted in no other bucket, and makes
the command exit 2 -- it is never hidden behind ``NO-PDATA``.  A module that
is not in the TOC is ``ERROR`` too (exit 2).  ``--check-fixture FILE``
compares the live census with a committed counts-only JSON (no vendor
bytes), printing one ``DRIFT`` line per module whose record count or
``NO-PDATA`` state differs and exiting 1 on any drift; the fixture's
``image_sha256`` must equal the image's SHA-256 or the run fails (exit 2).

``where`` answers "is the table in the section H51 assumed?" -- it prints the
e32 exception directory and, for every o32 section of the module, whether
that section holds the directory RVA and what its bytes decode to as a pdata
table (``sorted N records`` or the loud ``UNSORTED``/``NOT PDATA`` verdict).
A module whose table is not in sec2 (``atlce400.dll`` in build A, the
updaters and ``nk.exe`` in B/C) therefore shows the wrong index failing
instead of silently yielding a table from another section.  ``--try-index
N`` additionally decodes section ``N`` as if H51's "the last read-only
compressed section" rule had picked it, and prints the verdict -- that is how
the index-independence check is shown, not asserted.

``--image-start`` selects the CE segment: 0x200200 = build A, 0x3e00200 =
build B, 0x5200200 = build C (same image file).  Default 0x200200.

Stdlib only.  Build A pins:\n  Navi.exe  7,596 records, first 0x0032ed9c, last end 0x00558300
"""
import argparse
import bisect
import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import cerom  # noqa: E402
import nk_decomp  # noqa: E402
from sh4dis import Mem, bsr_target, jsr_reg, movl_pc_target  # noqa: E402

DEFAULT_IMAGE_START = 0x200200
DEFAULT_CACHE = os.environ.get("OSM2LEAF_PDATA_CACHE",
                               "/tmp/opencode/work/m1.20/decomp")
EXEC_FLAGS = cerom.CNT_CODE | cerom.MEM_EXECUTE
GAP_MIN = 8
DEFAULT_LEAF_CAP = 0x400
LEAF_WINDOW = 12

EXIT_NO_DIR = 3


class PdataError(Exception):
    pass


class NoPdata(PdataError):
    """The module's e32 exception directory is ``(0, 0)``: listed, not guessed.

    Distinct from a decode/sort failure so no caller can report a broken table
    as "no pdata".
    """


def exception_entry(rom, mod):
    """(rva, size) of the module's exception directory; (0, 0) when absent."""
    e = rom.e32(mod)
    exc = e.get("exception")
    if exc is None:
        # Pre-M1.23 cerom.e32() lacks the key; keep the fallback for old callers.
        o = rom.va2file(mod["e32"])
        units = struct.unpack_from("<18I", rom.d, o + 36)
        exc = (units[6], units[7])
    return exc


def find_pdata_section(rom, mod):
    """(index, section, offset_in_section) of the pdata bytes."""
    rva, size = exception_entry(rom, mod)
    if rva == 0 and size == 0:
        raise NoPdata("module %s: no exception directory (no function table)" % mod["name"])
    if size == 0:
        raise PdataError("module %s: exception directory at RVA 0x%x has size 0"
                         % (mod["name"], rva))
    if size % 8:
        raise PdataError("module %s: exception directory size 0x%x is not a multiple of 8"
                         % (mod["name"], size))
    exact = [(i, sec) for i, sec in enumerate(rom.o32(mod))
             if sec["rva"] == rva and sec["vsize"] == size]
    if exact:
        return exact[0][0], exact[0][1], 0
    plain = [(i, sec) for i, sec in enumerate(rom.o32(mod))
             if sec["rva"] == rva and sec["vsize"] >= size
             and not sec["flags"] & cerom.IMAGE_SCN_COMPRESSED]
    if plain:
        return plain[0][0], plain[0][1], 0
    for i, sec in enumerate(rom.o32(mod)):
        span = max(sec["vsize"], sec["psize"])
        if sec["rva"] <= rva and rva + size <= sec["rva"] + span:
            return i, sec, rva - sec["rva"]
    raise PdataError("module %s: exception directory RVA 0x%x size 0x%x lies in no section"
                     % (mod["name"], rva, size))


def _cache_path(cache_dir, stored_sha, size):
    return os.path.join(cache_dir, "%s-%x.bin" % (stored_sha[:32], size))


_NK_REGIONS = {}
_NK_REGIONS_KEEP = {}


def _nk_regions(data):
    """nk.exe mapped once per data buffer (re-mapping per section is slow)."""
    key = id(data)
    regions = _NK_REGIONS.get(key)
    if regions is None:
        regions = nk_decomp.nk_regions(data)
        _NK_REGIONS[key] = regions
        _NK_REGIONS_KEEP[key] = data
    return regions


def pdata_bytes(data, rom, mod, cache_dir=None):
    """The raw exception-directory bytes of ``mod`` (decompressed if needed)."""
    index, sec, off = find_pdata_section(rom, mod)
    rva, size = exception_entry(rom, mod)
    file_off = rom.va2file(sec["dataptr"])
    if sec["flags"] & cerom.IMAGE_SCN_COMPRESSED:
        stored = data[file_off:file_off + sec["psize"]]
        stored_sha = hashlib.sha256(stored).hexdigest()
        if cache_dir:
            path = _cache_path(cache_dir, stored_sha, size)
            try:
                blob = open(path, "rb").read()
            except OSError:
                blob = None
            if blob is not None and len(blob) == size:
                return blob, {"section": index, "compressed": True, "cached": True,
                              "exception_rva": rva, "exception_size": size,
                              "stored_sha256": stored_sha}
        try:
            r0, out = nk_decomp.decompress(data, file_off, sec["psize"], sec["vsize"],
                                           regions=_nk_regions(data))
        except Exception as exc:  # noqa: BLE001 - report, never guess
            raise PdataError("module %s sec%d: decompress failed: %s" % (mod["name"], index, exc))
        if off + size > r0:
            raise PdataError("module %s sec%d: decoded %#x bytes, exception directory "
                             "needs %#x..%#x" % (mod["name"], index, r0, off, off + size))
        blob = out[off:off + size]
        if cache_dir:
            try:
                os.makedirs(cache_dir, exist_ok=True)
                with open(_cache_path(cache_dir, stored_sha, size), "wb") as fh:
                    fh.write(blob)
            except OSError:
                pass
        return blob, {"section": index, "compressed": True, "cached": False,
                      "exception_rva": rva, "exception_size": size,
                      "stored_sha256": stored_sha}
    blob = data[file_off + off:file_off + off + size]
    if len(blob) != size:
        raise PdataError("module %s sec%d: short read for exception directory "
                         "(want %#x, got %#x)" % (mod["name"], index, size, len(blob)))
    return blob, {"section": index, "compressed": False, "cached": False,
                  "exception_rva": rva, "exception_size": size,
                  "stored_sha256": None}


def validate_sorted(records, where=""):
    """Strictly ascending begins; fail loudly otherwise."""
    for i in range(1, len(records)):
        if records[i][0] <= records[i - 1][0]:
            raise PdataError("%spdata table not sorted: record %d begins 0x%08x "
                             "after 0x%08x" % (where, i, records[i][0], records[i - 1][0]))
    return records


def load_table(data, image_start, module, cache_dir=None):
    """(records, meta) for one module. Records: (begin, prolog_bytes, length_bytes)."""
    if cache_dir is None:
        cache_dir = DEFAULT_CACHE
    rom = cerom.CERom(data, image_start)
    try:
        mod = rom.module(module)
    except KeyError:
        raise PdataError("module %r not found at image start 0x%x" % (module, image_start))
    blob, meta = pdata_bytes(data, rom, mod, cache_dir)
    records = nk_decomp.parse_pdata(blob)
    validate_sorted(records, "module %s: " % mod["name"])
    if not records:
        raise PdataError("module %s: exception directory holds no records" % mod["name"])
    meta = dict(meta)
    meta.update(module=mod["name"], image_start=image_start,
                record_count=len(records),
                first=records[0][0],
                last_end=records[-1][0] + records[-1][2])
    return records, meta


def locate(records, va):
    return nk_decomp.locate(records, va)


def fn_of_factory(records):
    """``fn_of(va)`` = pdata start of the function containing ``va``, else None.

    Starts are precomputed once so a caller scanning many loads pays one
    bisect per call, not one list build.  A VA in a gap (leaf function) has no
    record and yields None, which lets callers keep their heuristic fallback.
    """
    starts = [r[0] for r in records]

    def fn_of(va):
        i = bisect.bisect_right(starts, va) - 1
        if i < 0:
            return None
        begin, _prolog, length = records[i]
        return begin if begin <= va < begin + length else None

    return fn_of


def attach_fn_of(mem, records):
    """Attach ``mem.fn_of`` (a pdata-based function-start resolver) to a Mem."""
    mem.fn_of = fn_of_factory(records)
    return mem


def attach_fn_of_from_image(mem, data, image_start, module, cache_dir=None):
    """Attach ``mem.fn_of`` from the module's pdata; None when unavailable."""
    try:
        records, _meta = load_table(data, image_start, module, cache_dir)
    except Exception:  # noqa: BLE001 - no table never breaks the caller
        return None
    return attach_fn_of(mem, records)


def table_or_none(data, image_start, module, cache_dir=None):
    try:
        return load_table(data, image_start, module, cache_dir)[0]
    except Exception:  # noqa: BLE001 - a broken or absent table never breaks callers
        return None


CENSUS_SCHEMA = "osm2leaf.pdata-census/v1"
CENSUS_BUILDS = (("A", 0x200200), ("B", 0x3e00200), ("C", 0x5200200))


def file_sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def census_row(name, rva, size, loader):
    """One census row.  ``NO-PDATA`` only when the e32 directory is (0, 0).

    ``loader(name)`` returns ``(records, meta)`` or raises ``PdataError``; a
    raised error is an ``ERROR`` row (the caller exits non-zero and never
    reports it as "no pdata"), while the absent directory is a legitimate
    listed result.
    """
    if rva == 0 and size == 0:
        return dict(module=name, status="NO-PDATA", records=0)
    try:
        _records, meta = loader(name)
    except PdataError as exc:
        return dict(module=name, status="ERROR", records=0, error=str(exc))
    except Exception as exc:  # noqa: BLE001 - a fault is an ERROR, not NO-PDATA
        return dict(module=name, status="ERROR", records=0,
                    error="%s: %s" % (type(exc).__name__, exc))
    return dict(module=name, status="OK", records=meta["record_count"],
                section=meta["section"], compressed=bool(meta["compressed"]),
                exception_rva=meta["exception_rva"],
                exception_size=meta["exception_size"],
                first=meta["first"], last_end=meta["last_end"])


def census(data, image_start, cache_dir=None, modules=None):
    """Rows (dicts) for every module of one CE segment, in TOC order."""
    rom = cerom.CERom(data, image_start)
    wanted = set(modules) if modules else None
    rows, seen = [], set()
    for mod in rom.modules():
        if wanted is not None and mod["name"] not in wanted:
            continue
        seen.add(mod["name"])
        rva, size = exception_entry(rom, mod)
        rows.append(census_row(mod["name"], rva, size,
                               lambda n: load_table(data, image_start, n, cache_dir)))
    for name in sorted(wanted or ()):  # a requested module absent from the TOC
        if name not in seen:
            rows.append(dict(module=name, status="ERROR", records=0,
                             error="module not in TOC"))
    return rows


def census_totals(rows):
    return dict(modules=len(rows),
                with_pdata=sum(1 for r in rows if r["status"] == "OK"),
                without=sum(1 for r in rows if r["status"] == "NO-PDATA"),
                errors=sum(1 for r in rows if r["status"] == "ERROR"),
                records=sum(r["records"] for r in rows))


def census_line(row):
    """One printed census row: ``module records secN plain|compressed``.

    ``NO-PDATA`` is only the e32 ``(0, 0)`` case; an ``ERROR`` row prints its
    reason and is what makes the command exit non-zero -- it is never rendered
    as "no pdata".
    """
    if row["status"] == "OK":
        return ("%-32s %8d  sec%d  %s"
                % (row["module"], row["records"], row["section"],
                   "compressed" if row["compressed"] else "plain"))
    if row["status"] == "NO-PDATA":
        return ("%-32s %8s  no exception directory (e32 rva=0 size=0)"
                % (row["module"], "NO-PDATA"))
    return "%-32s %8s  %s" % (row["module"], "ERROR", row.get("error", ""))


def census_exit(rows):
    """0 unless a row is an ERROR (a fault is never a "listed as such" exit)."""
    return 2 if any(r["status"] == "ERROR" for r in rows) else 0


def census_doc(rows, image_start, label, image_sha256, image_bytes):
    return dict(schema=CENSUS_SCHEMA, label=label,
                image_start="0x%x" % image_start,
                image_sha256=image_sha256, image_bytes=image_bytes,
                totals=census_totals(rows), modules=rows)


def fixture_drift(rows, fixture, image_sha256=None, label=None):
    """Differences between a live census and a counts-only fixture.

    Returns ``(problems, drifts)``: ``problems`` are fatal fixture/identity
    mismatches (wrong image, wrong build), ``drifts`` per-module record-count
    or status changes.  A missing fixture row is a drift, and a fixture row
    with no live module is a drift.
    """
    problems, drifts = [], []
    if fixture.get("schema") != CENSUS_SCHEMA:
        problems.append("fixture schema %r != %r"
                        % (fixture.get("schema"), CENSUS_SCHEMA))
    if image_sha256 and fixture.get("image_sha256") != image_sha256:
        problems.append("fixture image_sha256 %s != image %s"
                        % (fixture.get("image_sha256"), image_sha256))
    if label is not None and fixture.get("label") not in (None, label):
        problems.append("fixture label %r != build %r"
                        % (fixture.get("label"), label))
    live = {r["module"]: r for r in rows}
    pinned = {r["module"]: r for r in fixture.get("modules", [])}
    for name in sorted(set(live) | set(pinned)):
        a, b = pinned.get(name), live.get(name)
        if a is None:
            drifts.append("%s: not in fixture (live %s %d)"
                          % (name, b["status"], b["records"]))
        elif b is None:
            drifts.append("%s: in fixture (%s %d), not live"
                          % (name, a.get("status"), a.get("records", 0)))
        elif (a.get("status"), a.get("records", 0)) != (b["status"], b["records"]):
            drifts.append("%s: fixture %s %d != live %s %d"
                          % (name, a.get("status"), a.get("records", 0),
                             b["status"], b["records"]))
    return problems, drifts


def exec_sections(rom, mod):
    """Uncompressed executable o32 sections as (realaddr, blob, index)."""
    for i, s in enumerate(rom.o32(mod)):
        if s["flags"] & cerom.IMAGE_SCN_COMPRESSED:
            continue
        if not (s["flags"] & EXEC_FLAGS):
            continue
        off = rom.va2file(s["dataptr"])
        yield i, s["realaddr"], data_slice(rom.d, off, s["vsize"])


def data_slice(d, off, size):
    return d[off:off + size]


def called_entries(exec_secs, records=None):
    """Sorted VAs that are a direct ``bsr`` target or a directly-called
    ``mov.l`` literal (the leaf-entry set ``gaps`` flags ``leaf`` rows with).

    ``records`` (pdata triples) restricts the scan to instructions inside
    pdata-recorded functions, which is the narrower set ``fn_match`` derives
    from ``leaf_call_sites``; a call made from inside a GAP is then invisible.
    ``records=None`` scans every executable halfword (the full set).
    """
    mem = Mem([(base, blob) for _i, base, blob in exec_secs])
    spans = []
    if records is None:
        spans = [(base, 0, len(blob)) for _i, base, blob in exec_secs]
    else:
        for i, base, blob in exec_secs:
            lo, hi = base, base + len(blob)
            for begin, _p, length in records:
                if begin >= hi:
                    break
                if length > 0 and begin + length > lo and begin < hi:
                    spans.append((base, max(begin, lo) - base,
                                  min(begin + length, hi) - base))
    called = set()
    blob_of = {base: blob for _i, base, blob in exec_secs}
    for base, start, end in spans:
        blob = blob_of[base]
        for off in range(start, end - 1, 2):
            w = struct.unpack_from("<H", blob, off)[0]
            t = bsr_target(base + off, w)
            if t is not None:
                called.add(t)
            ld = movl_pc_target(base + off, w)
            if ld is not None:
                value = mem.u32(ld[1])
                if value is None:
                    continue
                reg = ld[0]
                for k in range(1, LEAF_WINDOW + 1):
                    nw = mem.u16(base + off + 2 * k)
                    if nw is None:
                        break
                    j = jsr_reg(nw)
                    if j and j[1] == reg and j[0] in ("jsr", "jmp"):
                        called.add(value)
                        break
                    if (nw >> 8) & 0xF == reg or (nw >> 4) & 0xF == reg:
                        break
    return sorted(called)


def natural_bound(va, starts, called, code_end):
    """Uncapped byte bound of a GAP leaf: next pdata START, next called entry,
    or the end of the code section -- whichever comes first.  This is the same
    clamp ``fn_match.leaf_window_limit`` applies before its ``0x400`` cap."""
    i = bisect.bisect_right(starts, va)
    nxt = starts[i] if i < len(starts) else code_end
    j = bisect.bisect_right(called, va)
    if j < len(called):
        nxt = min(nxt, called[j])
    return max(0, min(nxt, code_end) - va)


def first_rts(blob, va, base, bound):
    """Byte offset of the first ``rts`` (0x000b) in ``[va, va+bound)``, or None."""
    for k in range(0, bound, 2):
        o = va - base + k
        if o + 2 > len(blob):
            break
        if blob[o] == 0x0B and blob[o + 1] == 0x00:
            return k
    return None


def gap_containing(va, rows):
    """The gap row strictly containing ``va`` (a call made from inside a GAP),
    or None when ``va`` is a function entry or outside every gap."""
    for r in rows:
        if r["start"] < va < r["end"]:
            return r
    return None


def leaf_census(data, image_start, module, cache_dir=None, cap=DEFAULT_LEAF_CAP,
                called_scope="records"):
    """Census of a module's pdata GAPs: can the ``cap``-limited leaf window see
    each whole function, and does it end in its own ``rts``?

    Rows are classified with the *uncapped* natural bound (next START / called
    entry / code end), so the count of gaps the ``cap`` hides is visible even
    though ``fn_match`` still caps its windows.  Returns a dict; see ``cmd_leaves``.
    """
    rows, meta = gaps(data, image_start, module, cache_dir)
    if meta is None:
        return None
    rom = cerom.CERom(data, image_start)
    exec_secs = list(exec_sections(rom, rom.module(module)))
    blob_of = {i: blob for i, _base, blob in exec_secs}
    sec_of = {i: (base, base + len(blob)) for i, base, blob in exec_secs}
    records = load_table(data, image_start, module, cache_dir)[0]
    starts = sorted(r[0] for r in records)
    if called_scope == "records":
        called = called_entries(exec_secs, records)
    else:
        called = called_entries(exec_secs)
        if called_scope == "gaps":
            gap_starts = {r["start"] for r in rows}
            called = [t for t in called if t in gap_starts]
    detail = []
    for r in rows:
        base, code_end = sec_of[r["section"]]
        blob = blob_of[r["section"]]
        va = r["start"]
        bound = natural_bound(va, starts, called, code_end)
        rts = first_rts(blob, va, base, bound)
        if rts is None:
            cls = "stub"
        elif bound > cap and rts >= cap:
            cls = "truncated"
        else:
            cls = "complete"
        detail.append(dict(va=va, length=r["length"], leaf=r["leaf"],
                           bound=bound, rts=rts, cls=cls,
                           pre_table=va < starts[0]))
    return dict(meta=meta, cap=cap, detail=detail,
                gaps=len(detail),
                leaf=sum(1 for d in detail if d["leaf"]),
                complete=sum(1 for d in detail if d["cls"] == "complete"),
                truncated=[d for d in detail if d["cls"] == "truncated"],
                stub=[d for d in detail if d["cls"] == "stub"],
                complete_leaf=sum(1 for d in detail if d["leaf"] and d["cls"] == "complete"),
                truncated_leaf=[d for d in detail if d["leaf"] and d["cls"] == "truncated"],
                stub_leaf=sum(1 for d in detail if d["leaf"] and d["cls"] == "stub"))


def gaps(data, image_start, module, cache_dir=None):
    """Executable ranges with no pdata record.

    Returns (rows, meta); each row is dict(start, end, length, section,
    leaf) where ``leaf`` marks gaps that are the target of a ``bsr`` or of a
    directly-called ``mov.l`` literal.
    """
    rom = cerom.CERom(data, image_start)
    try:
        mod = rom.module(module)
    except KeyError:
        raise PdataError("module %r not found at image start 0x%x" % (module, image_start))
    try:
        records, meta = load_table(data, image_start, module, cache_dir)
    except NoPdata:
        return [], None
    exec_secs = list(exec_sections(rom, mod))
    exec_ranges = [(base, base + len(blob), _i) for _i, base, blob in exec_secs]
    begins = [r[0] for r in records]
    covered = []  # merged exec-covered pdata intervals per section
    for i, (base, end, idx) in enumerate(exec_ranges):
        lo = bisect.bisect_left(begins, base)
        hi = bisect.bisect_right(begins, end - 1)
        for r in records[lo:hi]:
            b, _p, length = r
            covered.append((max(b, base), min(b + length, end)))
    covered.sort()
    rows = []
    for base, end, idx in exec_ranges:
        ivs = [(s, e) for s, e in covered if s < end and e > base]
        pos = base
        for s, e in ivs:
            if s > pos and s - pos > GAP_MIN:
                rows.append(dict(start=pos, end=s, length=s - pos, section=idx, leaf=False))
            pos = max(pos, e)
        if end - pos > GAP_MIN:
            rows.append(dict(start=pos, end=end, length=end - pos, section=idx, leaf=False))
    # Leaf detection: bsr targets and directly-called mov.l literals.
    called = called_entries(exec_secs)
    for row in rows:
        for t in called:
            if row["start"] <= t < row["end"]:
                row["leaf"] = True
                break
    meta = dict(meta)
    meta["gaps"] = len(rows)
    meta["leaf_gaps"] = sum(1 for r in rows if r["leaf"])
    return rows, meta


def _fmt_rec(kind, rec, va):
    if rec is None:
        return "%#010x BEFORE first record" % va
    begin, prolog, length = rec
    return ("%#010x %-6s fn 0x%08x prologue %d B, length %#x, end 0x%08x"
            % (va, kind, begin, prolog, length, begin + length))


def _octave(n):
    return 0 if n <= 0 else n.bit_length() - 1


def cmd_leaves(args):
    with open(args.image, "rb") as fh:
        data = fh.read(128 << 20)
    try:
        rep = leaf_census(data, args.image_start, args.module, args.cache,
                           args.cap, args.called)
    except PdataError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if rep is None:
        print("error: %s: no function table available" % args.module, file=sys.stderr)
        return EXIT_NO_DIR
    leaf = rep["leaf"]
    print("%s: %d gaps > %d B, %d leaf"
          % (args.module, rep["gaps"], GAP_MIN, leaf))
    print("complete %d (leaf %d), no-rts stub %d (leaf %d), cap 0x%x"
          % (rep["complete"], rep["complete_leaf"], len(rep["stub"]),
             rep["stub_leaf"], rep["cap"]))
    print("rts beyond cap (%s call set): %d%s"
          % (args.called, len(rep["truncated"]),
             (" " + " ".join("0x%08x(rts+%d,bound %#x%s)"
                             % (d["va"], d["rts"], d["bound"],
                                ",pre-table" if d["pre_table"] else "")
                             for d in rep["truncated"])) if rep["truncated"] else ""))
    hist = {}
    for d in rep["detail"]:
        if d["leaf"]:
            hist[_octave(d["bound"])] = hist.get(_octave(d["bound"]), 0) + 1
    print("leaf natural-bound histogram (octave): "
          + " ".join("%d:%d" % (lo, hist[lo]) for lo in sorted(hist)))
    if args.verbose:
        for d in rep["detail"]:
            print("gap 0x%08x len 0x%x%s bound 0x%x rts %s %s"
                  % (d["va"], d["length"], " leaf" if d["leaf"] else "",
                     d["bound"], "+%d" % d["rts"] if d["rts"] is not None else "-",
                     d["cls"]))
    return 0


def cmd_table(args):
    with open(args.image, "rb") as fh:
        data = fh.read(128 << 20)
    try:
        records, meta = load_table(data, args.image_start, args.module, args.cache)
    except NoPdata as exc:
        print(str(exc))
        return EXIT_NO_DIR
    except PdataError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if args.json:
        doc = dict(meta)
        doc.update(schema="osm2leaf.pdata/v1", sorted=True,
                   records=[[b, p, l] for b, p, l in records])
        print(json.dumps(doc))
        return 0
    mod = args.module
    comp = "compressed" if meta["compressed"] else "plain"
    cached = " (cache hit)" if meta.get("cached") else ""
    print("%s: %d records in exception directory (sec%d, %s%s, exc rva 0x%x size 0x%x)"
          % (mod, meta["record_count"], meta["section"], comp, cached,
             meta["exception_rva"], meta["exception_size"]))
    for begin, prolog, length in records:
        print("0x%08x  end 0x%08x  prologue %3d B  length 0x%x" % (begin, begin + length, prolog, length))
    print("%d records, first 0x%08x, last ends 0x%08x"
          % (meta["record_count"], meta["first"], meta["last_end"]))
    return 0


def cmd_fn(args):
    with open(args.image, "rb") as fh:
        data = fh.read(128 << 20)
    try:
        records, _meta = load_table(data, args.image_start, args.module, args.cache)
    except NoPdata as exc:
        print(str(exc))
        return EXIT_NO_DIR
    except PdataError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    for text in args.va:
        va = int(text, 0)
        kind, rec = locate(records, va)
        print(_fmt_rec(kind, rec, va))
    return 0


def cmd_gaps(args):
    with open(args.image, "rb") as fh:
        data = fh.read(128 << 20)
    try:
        rows, meta = gaps(data, args.image_start, args.module, args.cache)
    except NoPdata as exc:
        print(str(exc))
        return EXIT_NO_DIR
    except PdataError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if meta is None:  # unreachable: gaps() raises NoPdata instead of returning None
        print("error: %s: gaps() returned no table" % args.module, file=sys.stderr)
        return 2
    for row in rows:
        print("gap 0x%08x..0x%08x len 0x%x sec%d%s"
              % (row["start"], row["end"], row["length"], row["section"],
                 " leaf" if row["leaf"] else ""))
    print("%s: %d gaps > %d B, %d leaf (module %s)"
          % (args.module, len(rows), GAP_MIN, sum(1 for r in rows if r["leaf"]), args.module))
    return 0


def section_verdict(blob, where=""):
    """How ``blob`` parses as a pdata table: ("sorted", n), ("UNSORTED", msg).

    Used by ``where`` to show that a section picked by index alone is not a
    table; the message is the same one ``validate_sorted`` raises.
    """
    records = nk_decomp.parse_pdata(blob)
    if not records:
        return "EMPTY", "0 records"
    try:
        validate_sorted(records, where)
    except PdataError as exc:
        return "UNSORTED", str(exc)
    return "sorted", "%d records" % len(records)


def cmd_where(args):
    with open(args.image, "rb") as fh:
        data = fh.read(128 << 20)
    rom = cerom.CERom(data, args.image_start)
    try:
        mod = rom.module(args.module)
    except KeyError:
        print("error: module %r not found at image start 0x%x"
              % (args.module, args.image_start), file=sys.stderr)
        return 2
    rva, size = exception_entry(rom, mod)
    print("%s: exception directory rva 0x%x size 0x%x (%s)"
          % (mod["name"], rva, size,
             "no pdata" if (rva == 0 and size == 0) else "%d records" % (size // 8)))
    if rva == 0 and size == 0:
        return EXIT_NO_DIR
    chosen = None
    try:
        chosen = find_pdata_section(rom, mod)
    except PdataError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    for i, sec in enumerate(rom.o32(mod)):
        holds = sec["rva"] <= rva and rva + size <= sec["rva"] + max(sec["vsize"], sec["psize"])
        tag = "chosen" if chosen and chosen[0] == i else "      "
        comp = "compressed" if sec["flags"] & cerom.IMAGE_SCN_COMPRESSED else "plain"
        note = ""
        if holds and sec["rva"] == rva and sec["vsize"] == size:
            note = "exact RVA+vsize match"
        elif holds:
            note = "contains the directory (0x%x+0x%x)" % (rva, size)
        print("sec%d %s rva=0x%08x vsize=0x%08x psize=0x%08x %-10s %s"
              % (i, tag, sec["rva"], sec["vsize"], sec["psize"], comp, note))
        if not holds and (args.try_index is None or i != args.try_index):
            continue
        file_off = rom.va2file(sec["dataptr"])
        if sec["flags"] & cerom.IMAGE_SCN_COMPRESSED:
            try:
                r0, out = nk_decomp.decompress(data, file_off, sec["psize"],
                                               sec["vsize"], regions=_nk_regions(data))
            except Exception as exc:  # noqa: BLE001 - a verdict, not a crash
                print("       as pdata: DECODE ERROR %s" % exc)
                continue
            blob = out[:r0]
        else:
            blob = data[file_off:file_off + sec["vsize"]]
        verdict, detail = section_verdict(blob, "sec%d: " % i)
        print("       as pdata: %s (%s)" % (verdict, detail))
    if chosen:
        print("chosen: sec%d at 0x%08x for exception rva 0x%x"
              % (chosen[0], chosen[1]["rva"], rva))
    return 0


def cmd_census(args):
    """One CE segment's function-table census; NO-PDATA is not an error."""
    with open(args.image, "rb") as fh:
        data = fh.read(128 << 20)
    label = args.label or {0x200200: "A", 0x3e00200: "B",
                           0x5200200: "C"}.get(args.image_start, "0x%x" % args.image_start)
    image_sha = file_sha256(args.image)
    try:
        rows = census(data, args.image_start, args.cache)
    except (OSError, ValueError) as exc:
        print("error: cannot census image start 0x%x: %s"
              % (args.image_start, exc), file=sys.stderr)
        return 2
    totals = census_totals(rows)
    doc = census_doc(rows, args.image_start, label, image_sha,
                     os.path.getsize(args.image))
    if args.check_fixture:
        try:
            with open(args.check_fixture) as fh:
                fixture = json.load(fh)
        except (OSError, ValueError) as exc:
            print("error: cannot read fixture %s: %s"
                  % (args.check_fixture, exc), file=sys.stderr)
            return 2
        if isinstance(fixture, dict) and "schema" not in fixture:
            # A multi-build fixture ({"A": doc, "B": doc, ...}) -- pick this one.
            if label not in fixture:
                print("error: fixture %s has no %r build (has %s)"
                      % (args.check_fixture, label, ", ".join(sorted(fixture))),
                      file=sys.stderr)
                return 2
            fixture = fixture[label]
        problems, drifts = fixture_drift(rows, fixture, image_sha, label)
        for text in problems:
            print("FIXTURE PROBLEM: %s" % text)
        for text in drifts:
            print("DRIFT: %s" % text)
        if problems:
            print("census --check-fixture: %d fixture problem(s)" % len(problems))
            return 2
        if drifts:
            print("census --check-fixture: %d drift(s) against %s"
                  % (len(drifts), args.check_fixture))
            return 1
        print("census --check-fixture: 0 drift (%d modules, %d records)"
              % (totals["modules"], totals["records"]))
        return 0
    if args.json:
        print(json.dumps(doc))
        return census_exit(rows)
    for row in rows:
        print(census_line(row))
    print("%s: %d modules, %d with pdata, %d without (NO-PDATA), %d errors, %d records"
          % (label, totals["modules"], totals["with_pdata"], totals["without"],
             totals["errors"], totals["records"]))
    return census_exit(rows)


def selftest():
    fails = []

    def check(name, cond):
        print("%s %s" % ("ok  " if cond else "FAIL", name))
        if not cond:
            fails.append(name)

    blob = struct.pack("<IIIIII",
                       0x1000, (0x10 << 8) | 3,
                       0x1040, (0x08 << 8) | 2,
                       0x1100, (0x20 << 8) | 5)
    pd = validate_sorted(nk_decomp.parse_pdata(blob))
    check("three records parse", pd == [(0x1000, 6, 0x20), (0x1040, 4, 0x10), (0x1100, 10, 0x40)])
    check("START", locate(pd, 0x1000)[0] == "START")
    check("INSIDE", locate(pd, 0x1010) == ("INSIDE", (0x1000, 6, 0x20)))
    check("GAP", locate(pd, 0x1060)[0] == "GAP")
    check("BEFORE", locate(pd, 0x800)[0] == "BEFORE")
    check("START at last record", locate(pd, 0x1100)[0] == "START")
    fn_of = fn_of_factory(pd)
    check("fn_of START", fn_of(0x1000) == 0x1000)
    check("fn_of INSIDE", fn_of(0x1010) == 0x1000)
    check("fn_of GAP is None", fn_of(0x1060) is None)
    check("fn_of BEFORE is None", fn_of(0x800) is None)
    check("fn_of last INSIDE", fn_of(0x1120) == 0x1100)
    fm = Mem([(0x1000, b"\x00" * 0x200)])
    check("attach_fn_of returns the Mem", attach_fn_of(fm, pd) is fm)
    check("attached fn_of resolves", fm.fn_of(0x1044) == 0x1040)
    unsorted = [(0x1000, 6, 0x20), (0x0F00, 4, 0x10)]
    try:
        validate_sorted(unsorted, "selftest: ")
        check("unsorted table fails loudly", False)
    except PdataError:
        check("unsorted table fails loudly", True)
    dup = [(0x1000, 6, 0x20), (0x1000, 4, 0x10)]
    try:
        validate_sorted(dup)
        check("duplicate begin fails loudly", False)
    except PdataError:
        check("duplicate begin fails loudly", True)
    raw = b"\x00" * 36 + struct.pack("<18I", *([0] * 6 + [0x153f000, 0xed60] + [0] * 10))
    check("exception dir units[6:8] parse",
          struct.unpack_from("<18I", raw, 36)[6:8] == (0x153f000, 0xed60))
    # M1.31 census helpers: natural bound, rts offset, gap lookup, call scope.
    blob = bytearray(0x800)
    struct.pack_into("<H", blob, 0x10, 0x0009)
    struct.pack_into("<H", blob, 0x12, 0x000B)      # rts at +0x12
    blob = bytes(blob)
    check("natural_bound: next START bounds it",
          natural_bound(0x1000, [0x2000], [], 0x8000) == 0x1000)
    check("natural_bound: next called entry bounds it",
          natural_bound(0x1000, [0x3000], [0x1800], 0x8000) == 0x800)
    check("natural_bound: code end is the last bound",
          natural_bound(0x1000, [0x3000], [], 0x2000) == 0x1000)
    check("natural_bound is not capped at 0x400",
          natural_bound(0x1000, [0x3000], [], 0x3000) == 0x2000)
    check("first_rts finds the offset before the bound",
          first_rts(blob, 0x1000, 0x1000, 0x40) == 0x12)
    check("first_rts misses a no-rts stub",
          first_rts(blob, 0x1000, 0x1000, 0x12) is None)
    gaps_rows = [dict(start=0x1000, end=0x1100), dict(start=0x2000, end=0x2100)]
    check("gap_containing finds a call inside a gap",
          gap_containing(0x1040, gaps_rows)["start"] == 0x1000)
    check("gap_containing: a gap start is an entry, not inside",
          gap_containing(0x1000, gaps_rows) is None)
    blob_a = struct.pack("<HHHH", 0x0009, 0xB002, 0x0009, 0x000B)  # bsr +0x?
    secs = [(0, 0x1000, blob_a)]
    full = called_entries(secs)
    check("called_entries: a bsr target is in the full set",
          bsr_target(0x1002, 0xB002) == 0x100A and 0x100A in full)
    narrow = called_entries(secs, [(0x1000, 0, len(blob_a))])
    check("called_entries: a pdata-recorded caller keeps the target",
          0x100A in narrow)
    outside = called_entries(secs, [(0x2000, 0, 4)])
    check("called_entries: a caller outside every record adds nothing",
          outside == [])
    # M1.20 census: NO-PDATA vs ERROR, index independence, fixture drift.
    import tempfile
    real_sorted = blob
    with tempfile.TemporaryDirectory(prefix="pdata-selftest-") as td:
        good_p = os.path.join(td, "good.img")
        zero_p = os.path.join(td, "zero.img")
        with open(good_p, "wb") as fh:
            fh.write(real_sorted)
        with open(zero_p, "wb") as fh:
            fh.write(b"\0" * 16)
        with open(os.path.join(td, "broken.dll"), "wb") as fh:
            fh.write(b"x")

        def fake_rom(_data, _start):
            mods = [dict(name="good.dll", e32=0, o32=0),
                    dict(name="zero.dll", e32=1, o32=1),
                    dict(name="broken.dll", e32=2, o32=2)]

            class R:
                def modules(self):
                    return iter(mods)
            return R()

        def fake_exc(_rom, mod):
            return {"good.dll": (0x1000, 0x18), "zero.dll": (0, 0),
                    "broken.dll": (0x2000, 0x18)}[mod["name"]]

        def fake_load(_data, _start, name, _cache=None):
            if name == "broken.dll":
                raise PdataError("module broken.dll sec2: decompress failed: r0=-1")
            return [], dict(record_count=3, section=2, compressed=True,
                            exception_rva=0x1000, exception_size=0x18,
                            first=0x2000, last_end=0x2040)

        g = globals()
        old_rom = cerom.CERom
        old_exc, old_load = g["exception_entry"], g["load_table"]
        cerom.CERom = fake_rom
        g["exception_entry"], g["load_table"] = fake_exc, fake_load
        try:
            rows = census(b"", 0x200200)
            check("census: a real directory+table is OK, (0,0) is NO-PDATA, "
                  "a fault is ERROR",
                  [r["status"] for r in rows] == ["OK", "NO-PDATA", "ERROR"])
            check("census: exit 0 with only NO-PDATA rows",
                  census_exit([r for r in rows if r["status"] == "NO-PDATA"]) == 0)
            check("census: exit non-zero on a decode ERROR",
                  census_exit(rows) == 2)
            check("census: the ERROR row is not printed as NO-PDATA",
                  "NO-PDATA" not in census_line(rows[2])
                  and "decompress failed" in census_line(rows[2]))
            only = census(b"", 0x200200, modules=["good.dll", "absent.dll"])
            check("census: a requested module outside the TOC is ERROR",
                  [r["status"] for r in only] == ["OK", "ERROR"]
                  and "TOC" in only[1]["error"])
        finally:
            cerom.CERom = old_rom
            g["exception_entry"], g["load_table"] = old_exc, old_load

        def ok_loader(_name):
            return [], dict(record_count=3, section=2, compressed=True,
                            exception_rva=0x1000, exception_size=0x18,
                            first=0x2000, last_end=0x2040)

        check("census temp image round-trips file_sha256",
              file_sha256(good_p) == hashlib.sha256(real_sorted).hexdigest())

    def burst_loader(_name):
        raise PdataError("module X sec2: decompress failed: r0=-1")

    def type_loader(_name):
        raise struct.error("unpack_from requires a buffer of at least 8 bytes")

    check("census (0,0) is NO-PDATA, not an error",
          census_row("nostub.dll", 0, 0, ok_loader)["status"] == "NO-PDATA")
    check("census NO-PDATA row carries 0 records",
          census_row("nostub.dll", 0, 0, ok_loader)["records"] == 0)
    good = census_row("good.dll", 0x1000, 0x18, ok_loader)
    check("census with a directory and a table is OK with its count",
          good["status"] == "OK" and good["records"] == 3
          and good["section"] == 2 and good["compressed"] is True)
    bad = census_row("broken.dll", 0x1000, 0x18, burst_loader)
    check("census decode failure is ERROR, never NO-PDATA",
          bad["status"] == "ERROR" and "decompress failed" in bad["error"])
    bad2 = census_row("broken2.dll", 0x1000, 0x18, type_loader)
    check("census non-PdataError fault is ERROR, never NO-PDATA",
          bad2["status"] == "ERROR" and bad2["error"].startswith("error:"))
    check("census totals split with/without and count ERROR separately",
          census_totals([census_row("nostub.dll", 0, 0, ok_loader), good, bad])
          == dict(modules=3, with_pdata=1, without=1, errors=1, records=3))
    # Index independence: a later section whose first word looks like a begin
    # parses as an unsorted "table"; the verdict makes the wrong index loud.
    fake = struct.pack("<IIII", 0x1000, (0x4 << 8) | 2, 0x0F00, (0x2 << 8) | 1)
    verdict, detail = section_verdict(fake, "sec2: ")
    check("section_verdict: a later section is UNSORTED, not a table",
          verdict == "UNSORTED" and "not sorted" in detail)
    check("section_verdict: the real table is sorted",
          section_verdict(blob)[0] == "sorted")
    # Fixture drift: a counts-only fixture that disagrees fails, one that
    # matches passes, and an image-identity mismatch is a fatal problem.
    live = [census_row("a.dll", 0x1000, 0x18, ok_loader),
            census_row("b.dll", 0, 0, ok_loader)]
    fx = dict(schema=CENSUS_SCHEMA, image_sha256="00" * 32,
              modules=[dict(module="a.dll", status="OK", records=3),
                       dict(module="b.dll", status="NO-PDATA", records=0)])
    problems, drifts = fixture_drift(live, fx, image_sha256="00" * 32)
    check("fixture: a matching counts-only fixture has no drift",
          problems == [] and drifts == [])
    fx_bad = dict(fx, modules=[dict(module="a.dll", status="OK", records=4),
                               dict(module="b.dll", status="NO-PDATA", records=0)])
    problems, drifts = fixture_drift(live, fx_bad, image_sha256="00" * 32)
    check("fixture: a planted wrong record count drifts and names the module",
          problems == [] and len(drifts) == 1 and "a.dll" in drifts[0]
          and "4" in drifts[0] and "3" in drifts[0])
    problems, drifts = fixture_drift(live, fx, image_sha256="11" * 32)
    check("fixture: an image-SHA mismatch is a fatal problem",
          len(problems) == 1 and "image_sha256" in problems[0])
    fx_missing = dict(fx, modules=[dict(module="a.dll", status="OK", records=3)])
    problems, drifts = fixture_drift(live, fx_missing, image_sha256="00" * 32)
    check("fixture: a module missing from the fixture is a drift",
          problems == [] and any("b.dll" in d for d in drifts))
    print("selftest: %s (%d failed)" % ("OK" if not fails else "FAIL", len(fails)))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--cache", default=DEFAULT_CACHE,
                    help="decoded-pdata cache directory (default %(default)s)")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("table", "fn", "gaps", "leaves", "census", "where"):
        p = sub.add_parser(name)
        p.add_argument("image")
        p.add_argument("--image-start", type=lambda x: int(x, 0), default=DEFAULT_IMAGE_START)
        if name != "census":
            p.add_argument("--module", required=True)
        p.add_argument("--cache", default=DEFAULT_CACHE,
                       help="decoded-pdata cache directory (default %(default)s)")
        if name == "table":
            p.add_argument("--json", action="store_true")
        elif name == "where":
            p.add_argument("--try-index", type=int, default=None, metavar="N",
                           help="also decode section N as a pdata candidate "
                                "(e.g. 2, H51's assumption)")
        elif name == "census":
            p.add_argument("--json", action="store_true")
            p.add_argument("--label", default=None,
                           help="build label for the totals line (default from --image-start)")
            p.add_argument("--check-fixture", default=None, metavar="FILE",
                           help="compare with a counts-only census fixture; "
                                "exit 1 on drift, 2 on a fixture/identity problem")
        elif name == "fn":
            p.add_argument("va", nargs="+")
        elif name == "leaves":
            p.add_argument("--cap", type=lambda x: int(x, 0), default=DEFAULT_LEAF_CAP,
                           help="leaf window cap in bytes (default %(default)#x)")
            p.add_argument("--called", choices=("records", "gaps", "all"),
                           default="records",
                           help="call set bounding a leaf: calls from pdata-"
                                "recorded functions only (fn_match's clamp), "
                                "call targets that are gap starts (the "
                                "docstring's \"called GAP\"), or every halfword")
            p.add_argument("--verbose", action="store_true",
                           help="print one line per gap")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmd:
        ap.print_help()
        return 2
    return {"table": cmd_table, "fn": cmd_fn, "gaps": cmd_gaps,
            "leaves": cmd_leaves, "census": cmd_census,
            "where": cmd_where}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
