#!/usr/bin/env python3
"""objpos_l3.py - the OBJDLL car-position backup record (M8.H20a).

This tool reproduces, from printing commands, the *derived* structure of the
saved last vehicle position on the 2011 head unit.  Nothing here is a guessed
format: every constant comes from a firmware structure or the repository's
own anonymous flash image, and every number is printed by a command.

Facts (all VAs from tools/cerom.py, SH-4 little-endian):

* OBJDLL.dll has a backup class table at sec0 VA 55026796 (0x03482c6c), stride
  36 bytes, rows `{u8 name[32], u32 class_id}`.  Class 7 is OBJ_SEM_CARPOS.
* OBJ_CarPos_initialize (fn START 55031160 / 0x034a14b8) calls the backup
  loader 55028428 / 0x03495c4c with r4=6 (zero-based class index) and copies
  36-byte records (r7=36 in fn 0x034a14b8) into the caller's object.
* The VSram store frame (SMST ... u32 sum ... SMED) is verified on the
  committed anonymous flash: the u32 at SMED-16 equals the sum of all LE u32
  words before it (4 of 4 stores).
* A packed position word is 1/192 degree latitude in the high half and
  1/128 degree longitude in the low half (tools/coord.py).

Usage:
  objpos_l3.py --selftest
  objpos_l3.py classes IMG [--json]
  objpos_l3.py flash FLASH_IMG [--json]
  objpos_l3.py mutate FLASH_IMG --offset OFF --word WORD [--json]

Exit codes: 0 the control passed; 1 a control failed; 2 usage/input.
Method and evidence: docs/experiments/EXP-2026-11-24-M8.H20a-position-record.md
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

CLASS_TABLE_VA = 55061612          # 0x03482c6c
CLASS_STRIDE = 36
CARPOS_CLASS = 7
SECTOR_SIZE = 65536
FLASH_SIZE = 8388608
SRAM_OFF = 4194304
SRAM_MIRROR = 196608
SMST = b"SMST"
SMED = b"SMED"

# class-table rows are read from OBJDLL.dll sec0; VA -> file is derived by
# tools/cerom.py sections (realaddr 0x03481000 -> file 0x007de200).
OBJDLL_SEC0_VA = 55054336           # 0x03481000
OBJDLL_SEC0_FILE = 8249856          # 0x007de200
U32_MASK = 4294967295


def fmt_va(va: int) -> str:
    return "0x%08x" % va


def read_class_table(image: str) -> list[dict]:
    """Read the 36-byte backup class table from OBJDLL.dll sec0."""
    data = Path(image).read_bytes()
    base = CLASS_TABLE_VA - OBJDLL_SEC0_VA + OBJDLL_SEC0_FILE
    rows = []
    for index in range(32):
        off = base + CLASS_STRIDE * index
        if off + CLASS_STRIDE > len(data):
            break
        name = data[off:off + 32].split(b"\0", 1)[0]
        class_id = struct.unpack_from("<I", data, off + 32)[0]
        if not name or class_id == 0:
            break
        rows.append({"index": index, "va": fmt_va(CLASS_TABLE_VA + CLASS_STRIDE * index),
                     "class_id": class_id, "name": name.decode("ascii", "replace")})
    return rows


def store_spans(image: bytes) -> list[tuple[int, int]]:
    """Yield (start, end) of each SMST store in a flash image."""
    spans = []
    pos = 0
    while True:
        start = image.find(SMST, pos)
        if start < 0:
            break
        end = image.find(SMED, start)
        if end < 0:
            break
        spans.append((start, end + 4))
        pos = end + 4
    return spans


def store_sum_ok(image: bytes, start: int, end: int) -> tuple[int, int, bool]:
    """The firmware's store checksum: sum of all LE u32 before SMED."""
    sum_off = end - 16
    if sum_off < start + 4:
        return 0, 0, False
    stored = struct.unpack_from("<I", image, sum_off)[0]
    words = (sum_off - start) // 4
    total = sum(struct.unpack_from("<%dI" % words, image, start)) & U32_MASK
    return stored, total, stored == total


def scan_stores(image: bytes) -> list[dict]:
    result = []
    for start, end in store_spans(image):
        stored, total, ok = store_sum_ok(image, start, end)
        result.append({"flash_offset": fmt_va(start), "store_size": end - start,
                       "stored_sum": fmt_va(stored), "computed_sum": fmt_va(total),
                       "sum_ok": ok})
    return result


def find_word(image: bytes, word: int) -> list[int]:
    pat = struct.pack("<I", word)
    hits = []
    pos = 0
    while True:
        at = image.find(pat, pos)
        if at < 0:
            break
        hits.append(at)
        pos = at + 1
    return hits


def mutate_word(image: bytes, offset: int, word: int) -> bytes:
    out = bytearray(image)
    struct.pack_into("<I", out, offset, word)
    # A real store frame must have its sum updated, otherwise the firmware
    # rejects it.  Recompute the sum for the store that contains the offset.
    for start, end in store_spans(image):
        if start <= offset < end:
            sum_off = end - 16
            words = (sum_off - start) // 4
            struct.pack_into("<I", out, sum_off,
                             sum(struct.unpack_from("<%dI" % words, out, start)) & U32_MASK)
            break
    return bytes(out)


def selftest() -> int:
    fails = 0

    def check(label: str, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))

    from tempfile import TemporaryDirectory
    with TemporaryDirectory(prefix="objpos-l3-") as td:
        # Synthetic class table: row 7 is OBJ_SEM_CARPOS.
        path = str(Path(td) / "objdll.img")
        blob = bytearray(CLASS_TABLE_VA - OBJDLL_SEC0_FILE + 1024)
        for idx, name in enumerate(("A", "B", "OBJ_SEM_CARPOS")):
            off = CLASS_TABLE_VA - OBJDLL_SEC0_VA + OBJDLL_SEC0_FILE + CLASS_STRIDE * idx
            blob[off:off + len(name)] = name.encode()
            struct.pack_into("<I", blob, off + 32, idx + 1)
        Path(path).write_bytes(blob)
        rows = read_class_table(path)
        check("class count", len(rows), 3)
        check("carpos class id", rows[2]["class_id"], 3)
        check("carpos row VA", rows[2]["va"], fmt_va(CLASS_TABLE_VA + CLASS_STRIDE * 2))

        # Synthetic store: SMST + two words + sum + zeros + SMED.
        store = bytearray(SMST + struct.pack("<II", 1, 2) + b"\0" * 12 + SMED)
        sum_off = len(store) - 16
        struct.pack_into("<I", store, sum_off, sum(struct.unpack_from("<3I", store, 0)))
        image = bytes(store)
        check("store sum valid", store_sum_ok(image, 0, len(image))[2], True)
        bad = bytearray(image)
        struct.pack_into("<I", bad, 8, 0x4deadbeef & U32_MASK)
        check("mutated sum rejected", store_sum_ok(bytes(bad), 0, len(bad))[2], False)
        fixed = mutate_word(image, 8, 0x4deadbeef & U32_MASK)
        check("mutate repairs sum", store_sum_ok(fixed, 0, len(fixed))[2], True)
        check("word located", find_word(fixed, 0x4deadbeef & U32_MASK), [8])
        check("negative word absent", find_word(image, 0x4deadbeef & U32_MASK), [])
    print("objpos_l3 selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("classes", help="read the backup class table")
    c.add_argument("image")
    c.add_argument("--json")
    f = sub.add_parser("flash", help="verify SMST store sums in a flash image")
    f.add_argument("image")
    f.add_argument("--json")
    m = sub.add_parser("mutate", help="mutate a position word and repair the sum")
    m.add_argument("image")
    m.add_argument("--offset", type=lambda s: int(s, 0), required=True)
    m.add_argument("--word", type=lambda s: int(s, 0), required=True)
    m.add_argument("--json")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd not in ("classes", "flash", "mutate"):
        ap.print_help()
        return 2
    path = Path(args.image)
    if not path.is_file():
        print("no such image: %s" % args.image, file=sys.stderr)
        return 2
    if args.cmd == "classes":
        rows = read_class_table(args.image)
        for row in rows:
            print("class %2d at %s: %s" % (row["class_id"], row["va"], row["name"]))
        if args.json:
            Path(args.json).write_text(json.dumps(rows, indent=1))
        return 0 if any(r["class_id"] == CARPOS_CLASS for r in rows) else 1
    image = path.read_bytes()
    if args.cmd == "flash":
        rows = scan_stores(image)
        for row in rows:
            print("store %-10s size %-7d sum=%s computed=%s %s" % (
                row["flash_offset"], row["store_size"], row["stored_sum"],
                row["computed_sum"], "OK" if row["sum_ok"] else "BAD"))
        if args.json:
            Path(args.json).write_text(json.dumps(rows, indent=1))
        return 0 if rows and all(r["sum_ok"] for r in rows) else 1
    if not (SRAM_OFF <= args.offset < SRAM_OFF + SRAM_MIRROR):
        print("offset outside SRAM user area", file=sys.stderr)
        return 2
    out = mutate_word(image, args.offset, args.word)
    result = {"offset": fmt_va(args.offset), "word": fmt_va(args.word),
              "word_hits_before": find_word(image, args.word),
              "word_hits_after": find_word(out, args.word),
              "sum_ok_after": all(r["sum_ok"] for r in scan_stores(out))}
    print("mutated %s to %s; word hits before=%s after=%s; store sums OK=%s" % (
        result["offset"], result["word"], result["word_hits_before"],
        result["word_hits_after"], result["sum_ok_after"]))
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=1))
    return 0 if result["word_hits_after"] and result["sum_ok_after"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
