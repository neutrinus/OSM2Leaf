#!/usr/bin/env python3
"""Run Navi.exe's own POINT page record walker (M3.11, second pass).

M3.11 (first pass) looked for ``cmp/eq #0x60`` / ``#0x68`` tag tests and a
``mov.b @(1,Rm)`` length read and found nothing; it concluded that the walker
must sit in the compressed ``Navi.exe`` sec1.  Two facts change that:

* ``Navi.exe`` sec1/sec2 carry no ``CNT_CODE``/``MEM_EXECUTE`` flag (sec1
  ``0xc8002040`` = RW initialised data, sec2 ``0x48002040`` = R data); in
  build A **no compressed section is executable** (C-530, re-measured by
  ``sections``).  The walker has to be in sec0.
* The firmware reads the record header as **one native u16 word**:
  ``type = w >> 10`` (6 bits) and ``len = w & 0x3ff`` (10 bits, in 2-byte
  units); ``type == 0x3f`` (``w & 0xfc00 == 0xfc00``) is an escape with a
  fixed length of ``0x4e8`` words.  The file bytes ``tag, len2`` are that
  word in big-endian order: tag ``0x60`` -> type ``0x18``, ``0x68`` ->
  ``0x1a``.  No ``#0x60`` immediate ever appears.

``fn 0x003f5194(page, n)`` returns a pointer to record *n* (or 0): it loops at
most 20000 records, stops on ``len == 0`` and advances by ``2*len``.  This tool
executes that function, byte for byte from the ROM, in the repository's
pure-Python SH-4 interpreter (``tools/l3_harness/engine.py``, run as
``PySh4(endian="little")``: the default is big-endian), and compares it with
``mutate_refer_poi.parse_page``.

``skip`` runs ``fn 0x003f39c0(page, n)`` (M9.21), which first checks
``page == *0x00d5e4e4`` and ``n < *0x00d5e4d0``; the tool sets those two
globals itself (they live in data the image does not map in decoded form).

Usage::

  point_walk_l3.py --selftest
  point_walk_l3.py sections IMG [--image-start 0x200200]
  point_walk_l3.py consts IMG [--module Navi.exe]
  point_walk_l3.py walk IMG --cmp POINT010.DAT.cmp --ind POINT010.DAT.ind \
      --page 0x840ba0 [--page-len 42848] [--n 0,1,2,500,999,1000]
  point_walk_l3.py skip IMG --cmp ... --ind ... --page 0x840ba0 [--page-len ...]

Method and results: docs/experiments/EXP-2026-11-07-M3.11-point-reader-2.md
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
import zlib
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "l3_harness"))

import cerom  # noqa: E402
from engine import PySh4  # noqa: E402

WALK_NTH = 0x003F5194      # record_at(page, n)
WALK_SKIP = 0x003F39C0     # skip n records from the loaded page (globals)
WALK_DISPATCH = 0x003F5CDC  # chooses 0x3f5b88 / 0x3f5194 / 0x3f39c0 by buffer
GLOBAL_COUNT = 0x00D5E4D0   # *GLOBAL_COUNT: record count of the current page
GLOBAL_PAGE = 0x00D5E4E4    # *GLOBAL_PAGE: current page base (guard of 0x3f39c0)
GLOBALS_BASE = 0x00D5E4C0   # scratch RW region that holds both cells
ESCAPE_TYPE = 0x3F
ESCAPE_LEN = 0x4E8
MAX_RECORDS = 20000
PAGE_VA = 0x20000000
STACK_VA = 0x30000000
EXEC = 0x20000000
CODE = 0x20


# ---------------------------------------------------------------------------
# Python model of the firmware walker


def swap16(data: bytes) -> bytes:
    """Swap every 2-byte word (file big-endian u16 -> SH-4 native)."""
    if len(data) % 2:
        data = data + b"\x00"
    out = bytearray(len(data))
    out[0::2] = data[1::2]
    out[1::2] = data[0::2]
    return bytes(out)


def header(raw: bytes, pos: int) -> tuple[int, int]:
    """(type, length in bytes) of the record at *pos* of a raw (file) page."""
    word = (raw[pos] << 8) | raw[pos + 1]
    rtype = word >> 10
    words = ESCAPE_LEN if rtype == ESCAPE_TYPE else word & 0x3FF
    return rtype, 2 * words


def model_nth(raw: bytes, n: int) -> int | None:
    """What ``fn 0x003f5194`` returns for record *n*, as an offset."""
    pos = 0
    for i in range(MAX_RECORDS):
        if pos + 2 > len(raw):
            return None
        _, size = header(raw, pos)
        if size == 0:
            return None
        if i == n:
            return pos
        pos += size
    return None


# ---------------------------------------------------------------------------
# firmware execution


def load_image(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(128 << 20)


def module_sections(data: bytes, image_start: int, module: str):
    rom = cerom.CERom(data, image_start)
    mod = rom.module(module)
    out = []
    for s in rom.o32(mod):
        comp = bool(s["flags"] & cerom.IMAGE_SCN_COMPRESSED)
        blob = None
        if not comp:
            off = rom.va2file(s["dataptr"])
            blob = data[off:off + s["psize"]]
        out.append((s, comp, blob))
    return rom, out


def navi_text(data: bytes, image_start: int) -> tuple[int, bytes]:
    _, secs = module_sections(data, image_start, "Navi.exe")
    for s, comp, blob in secs:
        if not comp and s["flags"] & EXEC:
            return s["realaddr"], blob
    raise SystemExit("Navi.exe has no uncompressed executable section")


def run_nth(text_va: int, text: bytes, page_native: bytes, n: int):
    eng = PySh4(endian="little")
    eng.map("text", text_va, text, "rx")
    eng.map("page", PAGE_VA, bytearray(page_native) + bytearray(0x40), "rw")
    eng.map("stack", STACK_VA, bytearray(0x1000), "rw")
    eng.set_regs(r15=STACK_VA + 0xF00)
    ret = eng.call(WALK_NTH, [PAGE_VA, n])
    return None if ret == 0 else ret - PAGE_VA


def run_skip(text_va: int, text: bytes, page_native: bytes, count: int,
             page_arg: int, n: int):
    """Run fn 0x3f39c0(page_arg, n) with the two globals set by the tool."""
    eng = PySh4(endian="little")
    eng.map("text", text_va, text, "rx")
    eng.map("page", PAGE_VA, bytearray(page_native) + bytearray(0x40), "rw")
    eng.map("globals", GLOBALS_BASE, bytearray(0x40), "rw")
    eng.map("stack", STACK_VA, bytearray(0x1000), "rw")
    eng.write_mem(GLOBAL_COUNT, struct.pack("<I", count))
    eng.write_mem(GLOBAL_PAGE, struct.pack("<I", PAGE_VA))
    eng.set_regs(r15=STACK_VA + 0xF00)
    ret = eng.call(WALK_SKIP, [page_arg, n])
    return None if ret == 0 else ret - PAGE_VA


# ---------------------------------------------------------------------------
# commands


def cmd_sections(args) -> int:
    data = load_image(args.image)
    rom = cerom.CERom(data, args.image_start)
    tally = {}
    for mod in rom.modules():
        name = mod["name"] if isinstance(mod, dict) else mod
        try:
            _, secs = module_sections(data, args.image_start, name)
        except Exception:
            continue
        for s, comp, _ in secs:
            code = bool(s["flags"] & (CODE | EXEC))
            key = (comp, code)
            cnt, size = tally.get(key, (0, 0))
            tally[key] = (cnt + 1, size + s["vsize"])
            if name == "Navi.exe":
                print("Navi.exe realaddr=%08x vsize=%08x flags=%08x %s %s" % (
                    s["realaddr"], s["vsize"], s["flags"],
                    "COMPRESSED" if comp else "plain",
                    "CODE" if code else "DATA"))
    for (comp, code), (cnt, size) in sorted(tally.items()):
        print("compressed=%-5s code=%-5s sections=%4d vsize=%10d" % (
            comp, code, cnt, size))
    bad = tally.get((True, True), (0, 0))[0]
    print("compressed executable sections:", bad)
    return 0 if bad == 0 else 1


def literal_hits(text_va: int, text: bytes, values) -> dict:
    hits = {v: [] for v in values}
    for off in range(0, len(text) - 1, 2):
        va = text_va + off
        w = struct.unpack_from("<H", text, off)[0]
        if (w & 0xF000) == 0x9000:      # mov.w @(disp,PC),Rn
            la = va + 4 + (w & 0xFF) * 2 - text_va
            if la + 2 <= len(text):
                v = struct.unpack_from("<H", text, la)[0]
                if v in hits:
                    hits[v].append(va)
        elif (w & 0xF000) == 0xD000:    # mov.l @(disp,PC),Rn
            la = (va & ~3) + 4 + (w & 0xFF) * 4 - text_va
            if la + 4 <= len(text):
                v = struct.unpack_from("<I", text, la)[0]
                if v in hits:
                    hits[v].append(va)
    return hits


def cmd_consts(args) -> int:
    data = load_image(args.image)
    text_va, text = navi_text(data, args.image_start)
    hits = literal_hits(text_va, text, (0x03FF, 0xFC00))
    for v, sites in hits.items():
        print("%#06x: %d loads" % (v, len(sites)))
        print("  " + " ".join("%#x" % s for s in sites))
    print("anchor %#x in 0x3ff list: %s" % (0x3F51AE, 0x3F51AE in hits[0x03FF]))
    return 0


def cmd_walk(args) -> int:
    import mutate_refer_poi as mrp

    data = load_image(args.image)
    text_va, text = navi_text(data, args.image_start)
    cmp_bytes = Path(args.cmp).read_bytes()
    _, _, _, _, offsets = mrp.read_ind(Path(args.ind))
    dat = mrp.decode(cmp_bytes, offsets)
    end = args.page + args.page_len if args.page_len else len(dat)
    raw = zlib.decompressobj().decompress(dat[args.page:end])
    recs = mrp.parse_page(raw)
    print("page %#x: %d bytes, parse_page: %d records" % (
        args.page, len(raw), len(recs)))
    count = len(recs)
    ns = [int(x, 0) for x in args.n.split(",")] if args.n else sorted(
        {0, 1, 2, 3, 10, count // 2, count - 2, count - 1, count})
    native = swap16(raw)
    fails = 0
    for n in ns:
        fw = run_nth(text_va, text, native, n)
        py = recs[n]["offset"] if n < count else None
        md = model_nth(raw, n)
        ok = fw == py == md
        fails += not ok
        print("n=%-5d firmware=%-8s parse_page=%-8s model=%-8s %s" % (
            n, fw if fw is None else hex(fw), py if py is None else hex(py),
            md if md is None else hex(md), "OK" if ok else "MISMATCH"))
    neg = [run_nth(text_va, text, raw, n) for n in (1, 2)]
    print("negative control (page not swapped): n=1,2 -> %s, expected %s" % (
        [hex(x) if x is not None else None for x in neg],
        [hex(recs[1]["offset"]), hex(recs[2]["offset"])]))
    if neg == [recs[1]["offset"], recs[2]["offset"]]:
        print("negative control FAILED: unswapped page walks the same")
        fails += 1
    print("result:", "PASS" if not fails else "FAIL (%d)" % fails)
    return 0 if not fails else 1


def cmd_skip(args) -> int:
    import mutate_refer_poi as mrp

    data = load_image(args.image)
    text_va, text = navi_text(data, args.image_start)
    cmp_bytes = Path(args.cmp).read_bytes()
    _, _, _, _, offsets = mrp.read_ind(Path(args.ind))
    dat = mrp.decode(cmp_bytes, offsets)
    end = args.page + args.page_len if args.page_len else len(dat)
    raw = zlib.decompressobj().decompress(dat[args.page:end])
    recs = mrp.parse_page(raw)
    count = len(recs)
    print("page %#x: %d bytes, parse_page: %d records; globals count=%d "
          "page=%#x" % (args.page, len(raw), count, count, PAGE_VA))
    ns = [int(x, 0) for x in args.n.split(",")] if args.n else sorted(
        {0, 1, 2, 3, 10, count // 2, count - 2, count - 1, count})
    native = swap16(raw)
    fails = 0
    for n in ns:
        fw = run_skip(text_va, text, native, count, PAGE_VA, n)
        py = recs[n]["offset"] if n < count else None
        md = model_nth(raw, n)
        ok = fw == py == md
        fails += not ok
        print("n=%-5d firmware=%-8s parse_page=%-8s model=%-8s %s" % (
            n, fw if fw is None else hex(fw), py if py is None else hex(py),
            md if md is None else hex(md), "OK" if ok else "MISMATCH"))
    # guard control: a page argument that is not the current page base must
    # return 0 whatever n is (the 0x3f39c0 prologue compares p with the global)
    guard = run_skip(text_va, text, native, count, PAGE_VA + 2, 1)
    print("guard control (p != current page base): n=1 -> %s, expected None"
          % (hex(guard) if guard is not None else None))
    if guard is not None:
        print("guard control FAILED")
        fails += 1
    # count control: the count cell is set to 500 while the page still holds
    # 1000 records; n = 499 must give record 499, n = 500 (= count) must give 0
    half = 500
    last = run_skip(text_va, text, native, half, PAGE_VA, half - 1)
    past = run_skip(text_va, text, native, half, PAGE_VA, half)
    want = recs[half - 1]["offset"]
    print("count control (count cell 500): n=499 -> %s, expected %s; "
          "n=500 -> %s, expected None" % (
              hex(last) if last is not None else None, hex(want),
              hex(past) if past is not None else None))
    if last != want or past is not None:
        print("count control FAILED")
        fails += 1
    print("result:", "PASS" if not fails else "FAIL (%d)" % fails)
    return 0 if not fails else 1


# ---------------------------------------------------------------------------
# self-test (no vendor data)


def _synth(records) -> bytes:
    out = b""
    for tag, body in records:
        size = 2 + len(body) + 2
        assert size % 2 == 0
        out += bytes([tag, size // 2]) + body + b"\xff\xff"
    return out + b"\x00\x00"


def selftest() -> int:
    fails = 0

    def check(name, cond):
        nonlocal fails
        print("%-52s %s" % (name, "ok" if cond else "FAIL"))
        fails += not cond

    recs = [(0x60, b"A" * 44 + b"HANA HEALTH CENTER4590@HANA HWY\x00"),
            (0x68, b"B" * 84 + b"OSM2LEAF\x00\x00"),
            (0x60, b"C" * 44 + b"X\x00")]
    raw = _synth(recs)
    check("tag 0x60 -> type 0x18", header(raw, 0)[0] == 0x18)
    check("tag 0x68 -> type 0x1a", header(raw, 0x50)[0] == 0x1A)
    check("record 0 at 0", model_nth(raw, 0) == 0)
    check("record 1 at 2*len2(rec0)", model_nth(raw, 1) == 0x50)
    check("record 2", model_nth(raw, 2) == 0xB2)
    check("len 0 ends the page", model_nth(raw, 3) is None)
    big = bytes([0x61, 0x10]) + b"\x00" * (2 * 0x110 - 4) + b"\xff\xff" + b"\x00\x00"
    check("tag low bits extend len (0x61,0x10 -> 0x110 words)",
          header(big, 0)[1] == 2 * 0x110)
    esc = bytes([0xFC, 0x00]) + b"\x00" * (2 * ESCAPE_LEN - 2) + _synth(recs[:1])
    check("escape 0xfc00 -> fixed 0x4e8 words", model_nth(esc, 1) == 2 * ESCAPE_LEN)
    check("swap16 round trip", swap16(swap16(raw)) == raw)
    check("swap16 puts tag in the high byte",
          struct.unpack_from("<H", swap16(raw), 0)[0] == (0x60 << 8) | raw[1])
    print("selftest:", "PASS" if not fails else "FAIL (%d)" % fails)
    return 0 if not fails else 1


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("sections", "consts", "walk", "skip"):
        p = sub.add_parser(name)
        p.add_argument("image", help="IMG256 (first 256 MiB of the EU card)")
        p.add_argument("--image-start", type=lambda s: int(s, 0), default=0x200200)
        if name in ("walk", "skip"):
            p.add_argument("--cmp", required=True)
            p.add_argument("--ind", required=True)
            p.add_argument("--page", type=lambda s: int(s, 0), required=True)
            p.add_argument("--page-len", type=lambda s: int(s, 0), default=0)
            p.add_argument("--n", help="comma-separated record numbers")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "sections":
        return cmd_sections(args)
    if args.cmd == "consts":
        return cmd_consts(args)
    if args.cmd == "walk":
        return cmd_walk(args)
    if args.cmd == "skip":
        return cmd_skip(args)
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
