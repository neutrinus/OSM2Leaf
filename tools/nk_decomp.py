#!/usr/bin/env python3
"""Decompress CE ROM sections with the firmware's own routine, in PySh4 (H51).

The kernel of build B (``nk.exe``, ``--image-start 0x3e00200``) carries the
section decompressor ``DECOMP_SECT 0x88037464`` (M1.2c, M8.E1b).  It is a
plain function with seven arguments, the shape of ``CEDecompressROM``:

    r4 = src, r5 = psize, r6 = dest, r7 = vsize,
    @(16,sp) = skip (0), @(20,sp) = step/form word (1 or 2),
    @(24,sp) = block size (0x1000)

The first run of this tool (EXP-2026-11-11-H51) showed that the three stack
arguments were what M8.E1 was missing: with them the routine needs no kernel
context, no QEMU and no Ghidra.  It runs in the pure-Python ``PySh4`` engine
of the L3 harness and returns the number of bytes written.

No vendor byte is stored here: the tool reads the image the caller names.

Usage:
  nk_decomp.py --selftest
  nk_decomp.py section IMG256 --module Navi.exe --index 1 [-o OUT.bin]
  nk_decomp.py check   IMG256 [--module NAME] [--limit N] [--json OUT] [--cache]
  nk_decomp.py pdata   IMG256 --module Navi.exe [--index 2] VA [VA ...]

Library interface for other tools (M1.19).  Decode once, then read the cache:

  import nk_decomp
  data = nk_decomp.load_image("archive/head256.img")          # memoised
  init = nk_decomp.section_init(data, "Navi.exe", 1)          # stored bytes, len r0
  full = nk_decomp.section_bytes(data, "Navi.exe", 1)         # init + zero BSS, len vsize

Both take ``image_start`` (default build A, ``0x200200``); the kernel routine
always comes from build B of the same image (``0x3e00200``; byte-identical on
the EU2011 and US2011 cards).  A failed decode (``r0 = -1`` or ``r0 > vsize``)
raises ``DecompError`` and is never cached.  The cache holds one file per
section, ``<module>.sec<N>.<key12>.bin`` = the ``r0`` stored bytes, where
``key12`` is the first 12 hex digits of SHA-256 over (stored bytes, vsize):
content-addressed, so the EU and US images share entries for identical
sections and hashing a 7.5 GB card image is never needed.  The directory is
``$OSM2LEAF_DECOMP_CACHE`` or ``<repo>/archive/work/decomp`` (``archive/`` is
git-ignored: decoded bytes are vendor bytes and are never committed).
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE / "l3_harness"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import cerom  # noqa: E402
from engine import RETURN_VA, EngineError, PySh4  # noqa: E402

IMAGE_A = 0x200200
IMAGE_B = 0x3E00200
DECOMP_SECT = 0x88037464
BLOCK = 0x1000
SRC_VA, DST_VA, STK_VA = 0x90000000, 0x94000000, 0x9C000000
STK_SIZE = 0x40000
MAX_INSNS = 4_000_000_000
MINUS_ONE = 0xFFFFFFFF
CACHE_ENV = "OSM2LEAF_DECOMP_CACHE"
REPO = HERE.parent


class DecompError(RuntimeError):
    """The kernel routine did not decode a section (r0 = -1 or r0 > vsize)."""


def frame(skip: int = 0, step: int = 1, block: int = BLOCK) -> bytes:
    """The three stack arguments, as they sit at ``sp+16`` on entry."""
    return struct.pack("<III", skip, step, block)


def nk_regions(data: bytes, image_b: int = IMAGE_B):
    """(name, va, bytes, vsize) for every stored nk.exe section."""
    rom = cerom.CERom(data, image_b)
    out = []
    for i, s in enumerate(rom.o32(rom.module("nk.exe"))):
        if s["flags"] & cerom.IMAGE_SCN_COMPRESSED:
            raise SystemExit("nk.exe has a compressed section; not expected")
        blob = b""
        if s["psize"]:
            off = rom.va2file(s["dataptr"])
            blob = data[off:off + min(s["psize"], s["vsize"])]
        out.append(("nk%d" % i, s["realaddr"], blob, s["vsize"],
                    "rx" if s["flags"] & 0x20000000 else "rw"))
    return out


def decompress(data: bytes, file_off: int, psize: int, vsize: int,
               entry: int = DECOMP_SECT, regions=None) -> tuple[int, bytes]:
    """Run the kernel routine on one section.  Returns (r0, dest[:vsize])."""
    eng = PySh4(endian="little")
    for name, va, blob, size, perms in (regions or nk_regions(data)):
        buf = bytearray((size + 0xFFF) & ~0xFFF)
        buf[:len(blob)] = blob
        eng.map(name, va, buf, perms)
    eng.map("src", SRC_VA, bytearray(data[file_off:file_off + psize]) + bytearray(16), "rw")
    eng.map("dst", DST_VA, bytearray(vsize + BLOCK), "rw")
    eng.map("stack", STK_VA, bytearray(STK_SIZE), "rw")
    sp = STK_VA + STK_SIZE // 2
    eng.write_mem(sp + 16, frame())
    eng.set_regs(r15=sp, r4=SRC_VA, r5=psize, r6=DST_VA, r7=vsize, pr=RETURN_VA)
    eng.set_regs(pc=entry)
    eng.run_until(None, MAX_INSNS)
    r0 = eng._get_reg("r0") & 0xFFFFFFFF
    return r0, bytes(eng.read_mem(DST_VA, vsize))


# --------------------------------------------------------------------------
# cache + library interface (M1.19)

_IMAGES: dict = {}
_REGIONS: dict = {}


def load_image(path) -> bytes:
    """Read an image once per process (keyed by real path, size and mtime)."""
    real = os.path.realpath(str(path))
    st = os.stat(real)
    key = (real, st.st_size, st.st_mtime_ns)
    if key not in _IMAGES:
        _IMAGES.clear()
        with open(real, "rb") as handle:
            _IMAGES[key] = handle.read()
    return _IMAGES[key]


def _regions_for(data: bytes):
    key = id(data)
    hit = _REGIONS.get(key)
    if hit is None or hit[0] is not data:
        hit = (data, nk_regions(data))
        _REGIONS.clear()
        _REGIONS[key] = hit
    return hit[1]


def cache_dir() -> Path:
    return Path(os.environ.get(CACHE_ENV) or (REPO / "archive" / "work" / "decomp"))


def cache_key(stored: bytes, vsize: int) -> str:
    return hashlib.sha256(bytes(stored) + struct.pack("<I", vsize)).hexdigest()[:12]


def cache_path(module: str, index: int, stored: bytes, vsize: int) -> Path:
    return cache_dir() / ("%s.sec%d.%s.bin" % (module, index, cache_key(stored, vsize)))


def section_record(data: bytes, module: str, index: int, image_start: int = IMAGE_A):
    """(o32 record, file offset) of a compressed section; SystemExit-free."""
    rom = cerom.CERom(data, image_start)
    secs = list(rom.o32(rom.module(module)))
    if not 0 <= index < len(secs):
        raise DecompError("%s has no section %d" % (module, index))
    s = secs[index]
    if not s["flags"] & cerom.IMAGE_SCN_COMPRESSED:
        raise DecompError("%s sec%d is not compressed" % (module, index))
    return s, rom.va2file(s["dataptr"])


def decode_cached(data: bytes, file_off: int, psize: int, vsize: int,
                  module: str, index: int, cache: bool = True):
    """(r0, init bytes, source) for one section, through the cache.

    ``source`` is ``"cache"`` or ``"nk_decomp"``.  Raises ``DecompError``.
    """
    stored = data[file_off:file_off + psize]
    path = cache_path(module, index, stored, vsize)
    if cache and path.is_file():
        blob = path.read_bytes()
        if len(blob) <= vsize:
            return len(blob), blob, "cache"
    r0, out = decompress(data, file_off, psize, vsize, regions=_regions_for(data))
    if r0 == MINUS_ONE or r0 > vsize:
        raise DecompError("%s sec%d psize=%#x vsize=%#x: kernel routine returned r0=%#x"
                          % (module, index, psize, vsize, r0))
    if any(out[r0:]):
        raise DecompError("%s sec%d: bytes written past r0=%#x" % (module, index, r0))
    blob = out[:r0]
    if cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".%d.tmp" % os.getpid())
        tmp.write_bytes(blob)
        os.replace(tmp, path)   # atomic: parallel readers never see half a file
    return r0, blob, "nk_decomp"


def section_init(data: bytes, module: str, index: int, image_start: int = IMAGE_A,
                 cache: bool = True) -> bytes:
    """The initialised (stored) bytes of a compressed section, ``len == r0``."""
    s, off = section_record(data, module, index, image_start)
    return decode_cached(data, off, s["psize"], s["vsize"], module, index, cache)[1]


def section_bytes(data: bytes, module: str, index: int, image_start: int = IMAGE_A,
                  cache: bool = True) -> bytes:
    """What the loader puts at the section: init bytes then zero BSS (``vsize``)."""
    s, _ = section_record(data, module, index, image_start)
    init = section_init(data, module, index, image_start, cache)
    return init + bytes(s["vsize"] - len(init))


def compressed_sections(data: bytes, image_a: int = IMAGE_A):
    rom = cerom.CERom(data, image_a)
    for mod in rom.modules():
        name = mod["name"]
        for i, s in enumerate(rom.o32(mod)):
            if s["flags"] & cerom.IMAGE_SCN_COMPRESSED:
                yield name, i, s, rom.va2file(s["dataptr"])


def parse_pdata(blob: bytes):
    """SH-4 CE ``.pdata``: 8-byte records (begin VA, packed word).

    Packed word: bits 0-7 prologue length, bits 8-29 function length, both in
    2-byte instructions; bit 30 32-bit flag, bit 31 exception flag.
    """
    out = []
    for off in range(0, len(blob) - 7, 8):
        begin, word = struct.unpack_from("<II", blob, off)
        if begin:
            out.append((begin, (word & 0xFF) * 2, ((word >> 8) & 0x3FFFFF) * 2))
    return out


def locate(pdata, va: int):
    starts = [p[0] for p in pdata]
    i = bisect.bisect_right(starts, va) - 1
    if i < 0:
        return "BEFORE", None
    begin, prolog, length = pdata[i]
    if va == begin:
        return "START", pdata[i]
    if va < begin + length:
        return "INSIDE", pdata[i]
    return "GAP", pdata[i]


# --------------------------------------------------------------------------
def cmd_section(args) -> int:
    data = Path(args.image).read_bytes()
    rom = cerom.CERom(data, args.image_start)
    s = list(rom.o32(rom.module(args.module)))[args.index]
    if not s["flags"] & cerom.IMAGE_SCN_COMPRESSED:
        raise SystemExit("section %d of %s is not compressed" % (args.index, args.module))
    r0, out = decompress(data, rom.va2file(s["dataptr"]), s["psize"], s["vsize"])
    status = "ERROR" if r0 == 0xFFFFFFFF else "OK"
    print("%s sec%d va=%#010x vsize=%#x psize=%#x -> r0=%#x %s sha256(dest[:r0])=%s"
          % (args.module, args.index, s["realaddr"], s["vsize"], s["psize"], r0, status,
             hashlib.sha256(out[:r0]).hexdigest() if status == "OK" else "-"))
    if args.output and status == "OK":
        Path(args.output).write_bytes(out)   # full vsize: stored bytes + zero BSS
    return 0 if status == "OK" else 1


def cmd_check(args) -> int:
    data = Path(args.image).read_bytes()
    regions = nk_regions(data)
    rows, ok, bad = [], 0, 0
    for name, idx, s, off in compressed_sections(data, args.image_start):
        if args.module and name != args.module:
            continue
        if args.limit and len(rows) >= args.limit:
            break
        try:
            if args.cache:
                try:
                    r0, out, _src = decode_cached(data, off, s["psize"], s["vsize"],
                                                  name, idx)
                except DecompError as exc:
                    r0, out = MINUS_ONE, b""
                    print("exception: %s" % exc)
            else:
                r0, out = decompress(data, off, s["psize"], s["vsize"], regions=regions)
            err = None
        except EngineError as exc:
            r0, out, err = None, b"", str(exc)[:160]
        good = err is None and r0 != 0xFFFFFFFF and r0 <= s["vsize"]
        ok += good
        bad += not good
        rows.append({"module": name, "section": idx, "va": s["realaddr"],
                     "vsize": s["vsize"], "psize": s["psize"], "r0": r0,
                     "sha256": hashlib.sha256(out[:r0]).hexdigest() if good else None,
                     "error": err})
        if not good or args.verbose:
            print("%-22s sec%d vsize=%#x psize=%#x r0=%s %s"
                  % (name, idx, s["vsize"], s["psize"],
                     "-" if r0 is None else hex(r0), err or ("OK" if good else "ERROR")))
    total = sum(r["r0"] for r in rows if r["sha256"])
    print("%d OK, %d failed, %d sections, %d bytes decoded" % (ok, bad, len(rows), total))
    if args.json:
        Path(args.json).write_text(json.dumps({"schema": "osm2leaf.nk_decomp/v1",
                                               "sections": rows}, indent=1))
    return 0 if bad == 0 and rows else 1


def cmd_pdata(args) -> int:
    data = Path(args.image).read_bytes()
    rom = cerom.CERom(data, args.image_start)
    s = list(rom.o32(rom.module(args.module)))[args.index]
    r0, out = decompress(data, rom.va2file(s["dataptr"]), s["psize"], s["vsize"])
    pdata = parse_pdata(out[:r0])
    print("%s sec%d: %d function records, %#x..%#x"
          % (args.module, args.index, len(pdata), pdata[0][0], pdata[-1][0] + pdata[-1][2]))
    for text in args.va:
        va = int(text, 0)
        kind, rec = locate(pdata, va)
        if rec is None:
            print("%#010x BEFORE first record" % va)
        else:
            print("%#010x %-6s fn %#010x prologue %d B, length %#x, end %#010x"
                  % (va, kind, rec[0], rec[1], rec[2], rec[0] + rec[2]))
    return 0


def selftest() -> int:
    fails = []

    def check(name, cond):
        print("%s %s" % ("ok  " if cond else "FAIL", name))
        if not cond:
            fails.append(name)

    check("frame is skip, step, block as three LE words",
          frame() == bytes.fromhex("00000000" "01000000" "00100000"))
    blob = struct.pack("<IIII", 0x1000, (0x10 << 8) | 3, 0x1040, (0x08 << 8) | 2)
    pd = parse_pdata(blob + b"\0" * 8)
    check("pdata: two records, zero padding ignored", pd == [(0x1000, 6, 0x20), (0x1040, 4, 0x10)])
    check("pdata: START", locate(pd, 0x1000)[0] == "START")
    check("pdata: INSIDE (a VA six bytes into the prologue is not an entry)",
          locate(pd, 0x1006) == ("INSIDE", (0x1000, 6, 0x20)))
    check("pdata: GAP between functions (leaf code has no record)", locate(pd, 0x1030)[0] == "GAP")
    check("pdata: BEFORE", locate(pd, 0x800)[0] == "BEFORE")
    # the engine paths the decompressor needs (H51 engine fixes)
    eng = PySh4(endian="little")
    eng.map("d", 0x8C100000, bytearray(0x20), "rw")
    eng.set_regs(r0=0xFFFFFF84, r14=0x8C100000)
    eng._execute(0x80E8, 0x8C000000)
    check("engine: mov.b r0,@(8,r14) stores through r14", bytes(eng.read_mem(0x8C100008, 1)) == b"\x84")
    eng.set_regs(r13=7, r6=3)
    eng._execute(0x0D67, 0x8C000000)
    check("engine: mul.l r6,r13", eng._get_reg("macl") == 21)
    # cache (M1.19): content-addressed, failed decodes never cached
    import tempfile
    global decompress
    real_decompress, calls = decompress, []

    def fake(data, off, psize, vsize, entry=DECOMP_SECT, regions=None):
        calls.append(off)
        stored = data[off:off + psize]
        if stored.startswith(b"BAD"):
            return MINUS_ONE, bytes(vsize)
        return 4, stored[:4] + bytes(vsize - 4)

    old_env = os.environ.get(CACHE_ENV)
    with tempfile.TemporaryDirectory() as td:
        os.environ[CACHE_ENV] = td
        data = b"GOODbytes" + b"BADbytes!"
        decompress = fake
        globals()["nk_regions"], real_regions = (lambda d: []), nk_regions
        try:
            r0, blob, src = decode_cached(data, 0, 9, 0x20, "M.dll", 1)
            check("cache: first decode runs the routine", (r0, blob, src) == (4, b"GOOD", "nk_decomp"))
            r0, blob, src = decode_cached(data, 0, 9, 0x20, "M.dll", 1)
            check("cache: second decode is a cache hit", (src, len(calls)) == ("cache", 1))
            check("cache: key covers vsize", cache_key(b"x", 1) != cache_key(b"x", 2))
            try:
                decode_cached(data, 9, 9, 0x20, "M.dll", 2)
                check("cache: r0 = -1 raises DecompError", False)
            except DecompError as exc:
                check("cache: r0 = -1 raises DecompError", "r0=0xffffffff" in str(exc))
            check("cache: a failed decode is not cached",
                  sorted(x.name.split(".")[2] for x in Path(td).iterdir()) == ["sec1"])
        finally:
            decompress = real_decompress
            globals()["nk_regions"] = real_regions
            _REGIONS.clear()
            if old_env is None:
                os.environ.pop(CACHE_ENV, None)
            else:
                os.environ[CACHE_ENV] = old_env
    print("selftest: %s (%d failed)" % ("OK" if not fails else "FAIL", len(fails)))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("section", "check", "pdata"):
        p = sub.add_parser(name)
        p.add_argument("image")
        p.add_argument("--image-start", type=lambda x: int(x, 0), default=IMAGE_A)
        p.add_argument("--module", default=None if name == "check" else "Navi.exe")
        if name == "section":
            p.add_argument("--index", type=int, required=True)
            p.add_argument("-o", "--output")
        elif name == "check":
            p.add_argument("--limit", type=int, default=0)
            p.add_argument("--json")
            p.add_argument("-v", "--verbose", action="store_true")
            p.add_argument("--cache", action="store_true",
                           help="read/fill the decode cache (see cache_dir())")
        else:
            p.add_argument("--index", type=int, default=2)
            p.add_argument("va", nargs="+")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmd:
        ap.print_help()
        return 2
    return {"section": cmd_section, "check": cmd_check, "pdata": cmd_pdata}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
