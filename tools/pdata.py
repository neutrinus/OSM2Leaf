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
  pdata.py --selftest

``table`` prints one line per record and a trailing summary; ``--json``
emits one object with the full record list.  ``fn`` classifies each VA as
START / INSIDE / GAP / BEFORE.  ``gaps`` lists executable-section ranges
longer than 8 bytes with no record; a gap that is the target of a ``bsr`` or
of a directly-called ``mov.l`` literal is marked ``leaf`` (leaf functions
have no record).  A module with no exception directory is listed as such,
never guessed (exit 3).  An unsorted table fails loudly (exit 2).

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
LEAF_WINDOW = 12

EXIT_NO_DIR = 3


class PdataError(Exception):
    pass


def exception_entry(rom, mod):
    """(rva, size) of the module's exception directory; (0, 0) when absent."""
    e = rom.e32(mod)
    exc = e.get("exception")
    if exc is None:
        # cerom.e32 grew the exception key for this tool; tolerate older calls.
        o = rom.va2file(mod["e32"])
        units = struct.unpack_from("<18I", rom.d, o + 36)
        exc = (units[6], units[7])
    return exc


def find_pdata_section(rom, mod):
    """(index, section, offset_in_section) of the pdata bytes."""
    rva, size = exception_entry(rom, mod)
    if rva == 0 and size == 0:
        raise PdataError("module %s: no exception directory (no function table)" % mod["name"])
    if size == 0:
        raise PdataError("module %s: exception directory at RVA 0x%x has size 0" % (mod["name"], rva))
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


def table_or_none(data, image_start, module, cache_dir=None):
    try:
        return load_table(data, image_start, module, cache_dir)[0]
    except Exception:  # noqa: BLE001 - a broken or absent table never breaks callers
        return None


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
    except PdataError:
        return [], None
    exec_secs = list(exec_sections(rom, mod))
    mem = Mem([(base, blob) for _i, base, blob in exec_secs])
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
    called = set()
    for _, base, blob in exec_secs:
        for off in range(0, len(blob) - 1, 2):
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


def cmd_table(args):
    with open(args.image, "rb") as fh:
        data = fh.read(128 << 20)
    try:
        records, meta = load_table(data, args.image_start, args.module, args.cache)
    except PdataError as exc:
        if "no exception directory" in str(exc):
            print(str(exc))
            return EXIT_NO_DIR
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
    except PdataError as exc:
        if "no exception directory" in str(exc):
            print(str(exc))
            return EXIT_NO_DIR
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
    except PdataError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if meta is None:
        print("error: %s: no function table available (no exception directory, "
              "or module not found, or unreadable pdata)" % args.module, file=sys.stderr)
        return 2
    for row in rows:
        print("gap 0x%08x..0x%08x len 0x%x sec%d%s"
              % (row["start"], row["end"], row["length"], row["section"],
                 " leaf" if row["leaf"] else ""))
    print("%s: %d gaps > %d B, %d leaf (module %s)"
          % (args.module, len(rows), GAP_MIN, sum(1 for r in rows if r["leaf"]), args.module))
    return 0


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
    print("selftest: %s (%d failed)" % ("OK" if not fails else "FAIL", len(fails)))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--cache", default=DEFAULT_CACHE,
                    help="decoded-pdata cache directory (default %(default)s)")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("table", "fn", "gaps"):
        p = sub.add_parser(name)
        p.add_argument("image")
        p.add_argument("--image-start", type=lambda x: int(x, 0), default=DEFAULT_IMAGE_START)
        p.add_argument("--module", required=True)
        p.add_argument("--cache", default=DEFAULT_CACHE,
                       help="decoded-pdata cache directory (default %(default)s)")
        if name == "table":
            p.add_argument("--json", action="store_true")
        elif name == "fn":
            p.add_argument("va", nargs="+")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmd:
        ap.print_help()
        return 2
    return {"table": cmd_table, "fn": cmd_fn, "gaps": cmd_gaps}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
