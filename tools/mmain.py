#!/usr/bin/env python3
"""MMAIN001.DAT header: parse, write and round-trip (H8).

`MMAIN001.DAT` is the 4,096-byte database header, **not** a file listing and
**not** a FAT log. Layout on the EU 2011 card (docs/format/drstr.md):

  0x000-0x17f  common header text, UTF-16BE: `CLARION`, `HITACHI`,
               `CLA-NAVI05-01`, `FORMAT VERSION ...`, `DATA VERSION ...`,
               version string (C-010)
  0x180-0x183  common binary prefix `ff ff 24 ff` (C-011)
  0x184-0x18b  four big-endian i16 arc-minute bounds (C-1724)
  0x18c-0x193  eight-byte code list, language/volume reading (C-551)
  0x194-0x19f  twelve `0x3f` bytes; 0x1a0-0x1ab twelve `0xff` bytes (C-552)
  0x1ac        three-table descriptor: `u16` big-endian table count, then per
               table `(section u8, rows u8)` and `rows` × `(level u8,
               type u8, count u16 big-endian)`; `0x00` terminator at 0x1e0
               (C-550 structure, C-1788 big-endian counts)
  0x1e0-0xfff  header constants and the 0x800 slot table; kept verbatim

The writer rebuilds the file from the parsed fields; a rebuilt file equal to
the input proves the fields cover every non-zero byte. It does not prove what
the unit does with them (the firmware only reads 0x1000 bytes and byte-swaps
every `u16`, docs/format/drstr.md).

`tools/mmain.py` used to read the **FAT32 root directory** instead of this file
(EXP-2026-11-05-M4.5, retracted by C-1721). That parser is kept, unchanged in
behaviour but named for what it reads, under `--fat-root`.

Usage:
  mmain.py FILE [--list]              MMAIN001.DAT header, summary, round-trip
  mmain.py --fat-root FILE [--list]   FAT32 root directory (old behaviour)
  mmain.py --selftest                 synthetic checks for both parsers
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# MMAIN001.DAT header (the file this tool is named after)
# ---------------------------------------------------------------------------

MMAIN_SIZE = 0x1000
MMAIN_TEXT_END = 0x180
MMAIN_PREFIX = (0x180, 0x184)
MMAIN_BOUNDS = (0x184, 4)
MMAIN_CODES = (0x18c, 0x194)
MMAIN_RUNS = (0x194, 0x1ac)
MMAIN_TABLES = 0x1ac
MMAIN_TABLE_ENTRY = 4
MMAIN_REPEAT_BOUNDS = 0x5d0

# (offset, length) of the UTF-16BE text fields in the common header. The
# version string starts after the `16 00` word at 0x160 (file-header.md).
MMAIN_TEXT_FIELDS = (
    ("clarion", 0x00, 0x40),
    ("hitachi", 0x40, 0x40),
    ("model", 0x80, 0x20),
    ("format", 0xA0, 0x40),
    ("data", 0xE0, 0x80),
    ("version", 0x162, 0x1E),
)


def _utf16be_field(data: bytes, offset: int, length: int) -> str:
    text = data[offset:offset + length].decode("utf-16-be", "replace")
    for stop in ("\uffff", "\x00"):
        text = text.split(stop)[0]
    return text.strip()


def looks_like_mmain(blob: bytes) -> bool:
    """True when 0x000 starts with the UTF-16BE common-header `CLARION`."""
    return len(blob) >= 0x10 and blob[0:0x0E].decode("utf-16-be", "replace") == "CLARION"


def parse_mmain(blob: bytes) -> dict:
    if len(blob) != MMAIN_SIZE:
        raise ValueError(f"expected {MMAIN_SIZE} bytes, got {len(blob)}")
    if not looks_like_mmain(blob):
        raise ValueError(
            "not an MMAIN001.DAT header: 0x000 is not UTF-16BE 'CLARION' "
            "(a FAT32 root directory needs --fat-root)")
    tables = []
    pos = MMAIN_TABLES
    if pos + 2 > len(blob):
        raise ValueError("truncated table count at 0x1ac")
    count = struct.unpack_from(">H", blob, pos)[0]
    pos += 2
    for _ in range(count):
        if pos + 2 > len(blob):
            raise ValueError("truncated table group header")
        section, rows = blob[pos], blob[pos + 1]
        pos += 2
        entries = []
        for _ in range(rows):
            if pos + MMAIN_TABLE_ENTRY > len(blob):
                raise ValueError("truncated table entry")
            level, kind, value = struct.unpack_from(">BBH", blob, pos)
            entries.append({"level": level, "type": kind, "count": value})
            pos += MMAIN_TABLE_ENTRY
        tables.append({"section": section, "entries": entries})
    return {
        "header": blob[0:MMAIN_TEXT_END].hex(),
        "prefix": blob[MMAIN_PREFIX[0]:MMAIN_PREFIX[1]].hex(),
        "bounds": list(struct.unpack_from(">hhhh", blob, MMAIN_BOUNDS[0])),
        "codes": blob[MMAIN_CODES[0]:MMAIN_CODES[1]].hex(),
        "runs": blob[MMAIN_RUNS[0]:MMAIN_RUNS[1]].hex(),
        "tables": tables,
        "tail": blob[pos:].hex(),
    }


def _fixed_hex(text: str, length: int, label: str) -> bytes:
    raw = bytes.fromhex(text)
    if len(raw) != length:
        raise ValueError(f"{label} must be {length} bytes, got {len(raw)}")
    return raw


def write_mmain(doc: dict) -> bytes:
    out = bytearray(MMAIN_SIZE)
    header = _fixed_hex(doc["header"], MMAIN_TEXT_END, "header")
    out[0:MMAIN_TEXT_END] = header
    out[MMAIN_PREFIX[0]:MMAIN_PREFIX[1]] = _fixed_hex(
        doc["prefix"], MMAIN_PREFIX[1] - MMAIN_PREFIX[0], "prefix")
    struct.pack_into(">hhhh", out, MMAIN_BOUNDS[0], *doc["bounds"])
    out[MMAIN_CODES[0]:MMAIN_CODES[1]] = _fixed_hex(
        doc["codes"], MMAIN_CODES[1] - MMAIN_CODES[0], "codes")
    out[MMAIN_RUNS[0]:MMAIN_RUNS[1]] = _fixed_hex(
        doc["runs"], MMAIN_RUNS[1] - MMAIN_RUNS[0], "runs")
    tables = doc["tables"]
    if len(tables) > 0xFFFF:
        raise ValueError("too many tables")
    struct.pack_into(">H", out, MMAIN_TABLES, len(tables))
    pos = MMAIN_TABLES + 2
    for group in tables:
        entries = group["entries"]
        if len(entries) > 0xFF:
            raise ValueError("too many entries in a table")
        out[pos] = group["section"]
        out[pos + 1] = len(entries)
        pos += 2
        for entry in entries:
            struct.pack_into(">BBH", out, pos,
                             entry["level"], entry["type"], entry["count"])
            pos += MMAIN_TABLE_ENTRY
    tail = bytes.fromhex(doc["tail"])
    out[pos:pos + len(tail)] = tail
    return bytes(out)


def mmain_fields(doc: dict) -> dict:
    """Decoded common-header text fields."""
    header = bytes.fromhex(doc["header"])
    return {name: _utf16be_field(header, offset, length)
            for name, offset, length in MMAIN_TEXT_FIELDS}


def table_totals(doc: dict) -> list[dict]:
    """Per-table row count and summed `count` (the 0x1ac tile-set totals)."""
    return [{
        "section": group["section"],
        "rows": len(group["entries"]),
        "total": sum(entry["count"] for entry in group["entries"]),
    } for group in doc["tables"]]


# ---------------------------------------------------------------------------
# FAT32 root directory (what the old `parse()` really read, C-1721/C-1722)
# ---------------------------------------------------------------------------

FAT_ROOT_SIZE = 0x1000
FAT_ROOT_HDR_END = 0x020
FAT_ROOT_REC = 0x20
FAT_ROOT_REC_END = 0x680
ATTR_NAMES = {0x01: "RO", 0x02: "HID", 0x04: "SYS", 0x08: "VOL", 0x10: "DIR", 0x20: "ARC"}


def parse_fat_root(blob: bytes) -> dict:
    if len(blob) != FAT_ROOT_SIZE:
        raise ValueError(f"expected {FAT_ROOT_SIZE} bytes, got {len(blob)}")
    recs = []
    for off in range(FAT_ROOT_HDR_END, FAT_ROOT_REC_END, FAT_ROOT_REC):
        e = blob[off:off + FAT_ROOT_REC]
        recs.append({
            "name": e[0:8].hex(),       # raw bytes, keeps 0xE5 and padding
            "ext": e[8:11].hex(),
            "attr": e[11],
            "nt": e[12],
            "ctime_fine": e[13],
            "ctime": e[14:16].hex(),
            "cdate": e[16:18].hex(),
            "adate": e[18:20].hex(),
            "cluster_hi": e[20:22].hex(),
            "mtime": e[22:24].hex(),
            "mdate": e[24:26].hex(),
            "cluster": struct.unpack("<H", e[26:28])[0],
            "size": struct.unpack("<I", e[28:32])[0],
        })
    return {"header": blob[:FAT_ROOT_HDR_END].hex(), "records": recs,
            "tail": blob[FAT_ROOT_REC_END:].hex()}


def write_fat_root(doc: dict) -> bytes:
    out = bytearray(FAT_ROOT_SIZE)
    hdr = bytes.fromhex(doc["header"])
    out[0:len(hdr)] = hdr
    for i, r in enumerate(doc["records"]):
        off = FAT_ROOT_HDR_END + i * FAT_ROOT_REC
        e = bytearray(FAT_ROOT_REC)
        e[0:8] = bytes.fromhex(r["name"])
        e[8:11] = bytes.fromhex(r["ext"])
        e[11] = r["attr"]
        e[12] = r["nt"]
        e[13] = r["ctime_fine"]
        e[14:16] = bytes.fromhex(r["ctime"])
        e[16:18] = bytes.fromhex(r["cdate"])
        e[18:20] = bytes.fromhex(r["adate"])
        e[20:22] = bytes.fromhex(r["cluster_hi"])
        e[22:24] = bytes.fromhex(r["mtime"])
        e[24:26] = bytes.fromhex(r["mdate"])
        struct.pack_into("<H", e, 26, r["cluster"])
        struct.pack_into("<I", e, 28, r["size"])
        out[off:off + FAT_ROOT_REC] = e
    tail = bytes.fromhex(doc["tail"])
    out[FAT_ROOT_REC_END:FAT_ROOT_REC_END + len(tail)] = tail
    return bytes(out)


def fat_root_live_listing(doc: dict) -> list[dict]:
    rows = []
    for r in doc["records"]:
        name = bytes.fromhex(r["name"])
        if name[0] in (0x00, 0xE5):
            continue
        base = name.decode("latin1").rstrip()
        ext = bytes.fromhex(r["ext"]).decode("latin1").rstrip()
        full = base + ("." + ext if ext else "")
        # FAT32 first cluster: high word at +0x14, low word at +0x1a.  Printing
        # only the low word is how M4.5 mistook the root directory for
        # MMAIN001.DAT (C-1722), so the listing combines both.
        cluster_hi = int.from_bytes(bytes.fromhex(r["cluster_hi"]), "little")
        cluster = r["cluster"] | (cluster_hi << 16)
        rows.append({"name": full, "attr": r["attr"], "cluster": cluster,
                     "size": r["size"]})
    return rows


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def report_mmain(blob: bytes, doc: dict, do_list: bool) -> int:
    ok = write_mmain(doc) == blob
    repeat = struct.unpack_from(">hh", blob, MMAIN_REPEAT_BOUNDS)
    fields = mmain_fields(doc)
    print(f"size={len(blob)} sha256={hashlib.sha256(blob).hexdigest()}")
    print("header: " + " ".join(f"{name}={value!r}" for name, value in fields.items()))
    print("bounds@0x184=%d,%d,%d,%d" % tuple(doc["bounds"]))
    print("bounds@0x5d0=%d,%d consistent=%s"
          % (repeat[0], repeat[1], repeat == tuple(doc["bounds"][1:3])))
    print("codes@0x18c=%s (%d)" % (bytes.fromhex(doc["codes"]).hex(" "),
                                   len(bytes.fromhex(doc["codes"]))))
    print("tables=%d entries=%d"
          % (len(doc["tables"]), sum(len(group["entries"]) for group in doc["tables"])))
    for row in table_totals(doc):
        print("  section %02x: %d rows, total=%d"
              % (row["section"], row["rows"], row["total"]))
        if do_list:
            for entry in next(group["entries"] for group in doc["tables"]
                              if group["section"] == row["section"]):
                print("    level=%d type=%#04x count=%d"
                      % (entry["level"], entry["type"], entry["count"]))
    print(f"roundtrip={'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


def report_fat_root(blob: bytes, doc: dict, do_list: bool) -> int:
    ok = write_fat_root(doc) == blob
    live = fat_root_live_listing(doc)
    deleted = sum(1 for r in doc["records"] if r["name"][:2] == "e5")
    print(f"records={len(doc['records'])} deleted={deleted} live={len(live)}")
    if do_list:
        for r in live:
            attr = "+".join(v for k, v in ATTR_NAMES.items() if r["attr"] & k) or "-"
            print(f"  {r['name']:<12} attr={attr:<4} cluster={r['cluster']:#06x} size={r['size']}")
    print(f"roundtrip={'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# Self-test (synthetic, no vendor data)
# ---------------------------------------------------------------------------


def _synthetic_mmain() -> tuple[bytes, int]:
    """A 4 KiB MMAIN001.DAT header with the EU 2011 field values."""
    blob = bytearray(MMAIN_SIZE)
    for name, offset, length in MMAIN_TEXT_FIELDS:
        text = {
            "clarion": "CLARION",
            "hitachi": "HITACHI",
            "model": "CLA-NAVI05-01",
            "format": "FORMAT VERSION X08-02-00",
            "data": "DATA VERSION 11/06/27/01",
            "version": "V05.00.00",
        }[name].encode("utf-16-be")
        blob[offset:offset + len(text)] = text
    blob[0x180:0x184] = bytes.fromhex("ffff24ff")
    struct.pack_into(">hhhh", blob, 0x184, 4800, 1280, -1200, 4080)
    blob[0x18c:0x194] = bytes.fromhex("050402070a060814")
    blob[0x194:0x1a0] = b"\x3f" * 12
    blob[0x1a0:0x1ac] = b"\xff" * 12
    rows = {
        0x01: [(6, 0x80, 1), (5, 0x90, 1), (4, 0x91, 1), (3, 0x91, 45),
               (2, 0x91, 138), (1, 0x92, 1717)],
        0x02: [(3, 0x91, 1), (2, 0x91, 3), (1, 0x91, 3), (0, 0x91, 258)],
        0x04: [(1, 0x90, 1)],
    }
    struct.pack_into(">H", blob, MMAIN_TABLES, len(rows))
    pos = MMAIN_TABLES + 2
    for section, entries in rows.items():
        blob[pos] = section
        blob[pos + 1] = len(entries)
        pos += 2
        for level, kind, count in entries:
            struct.pack_into(">BBH", blob, pos, level, kind, count)
            pos += MMAIN_TABLE_ENTRY
    blob[pos] = 0x00                       # terminator, expected at 0x1e0
    struct.pack_into(">hh", blob, MMAIN_REPEAT_BOUNDS, 1280, -1200)
    return bytes(blob), pos


def _synthetic_fat_root() -> bytes:
    blob = bytearray(FAT_ROOT_SIZE)
    blob[0:11] = b"SYN-000-000"
    e = bytearray(FAT_ROOT_REC)
    e[0:8] = b"DEMO    "
    e[8:11] = b"DAT"
    e[11] = 0x20
    struct.pack_into("<H", e, 20, 1)   # FAT32 cluster high word
    struct.pack_into("<H", e, 26, 2)   # cluster low word -> 0x10002
    struct.pack_into("<I", e, 28, 4096)
    blob[FAT_ROOT_HDR_END:FAT_ROOT_HDR_END + FAT_ROOT_REC] = e
    e2 = bytearray(FAT_ROOT_REC)
    e2[0:8] = b"\xe5OLD    "
    e2[8:11] = b"LST"
    e2[11] = 0x20
    struct.pack_into("<H", e2, 26, 5)
    struct.pack_into("<I", e2, 28, 19)
    blob[FAT_ROOT_HDR_END + FAT_ROOT_REC:FAT_ROOT_HDR_END + 2 * FAT_ROOT_REC] = e2
    return bytes(blob)


def _raises(fn) -> bool:
    try:
        fn()
    except ValueError:
        return True
    return False


def _selftest() -> int:
    fails = []

    def check(name, cond):
        if not cond:
            fails.append(name)

    # MMAIN001.DAT header: parse, decode, write back byte-identically.
    blob, table_end = _synthetic_mmain()
    doc = parse_mmain(blob)
    fields = mmain_fields(doc)
    check("mmain sniff", looks_like_mmain(blob))
    check("mmain size", len(blob) == MMAIN_SIZE)
    check("mmain header text",
          fields == {"clarion": "CLARION", "hitachi": "HITACHI",
                     "model": "CLA-NAVI05-01",
                     "format": "FORMAT VERSION X08-02-00",
                     "data": "DATA VERSION 11/06/27/01",
                     "version": "V05.00.00"})
    check("mmain bounds", doc["bounds"] == [4800, 1280, -1200, 4080])
    check("mmain bounds repeat", struct.unpack_from(">hh", blob, MMAIN_REPEAT_BOUNDS)
          == tuple(doc["bounds"][1:3]))
    check("mmain codes", doc["codes"] == "050402070a060814")
    check("mmain table sections", [g["section"] for g in doc["tables"]] == [1, 2, 4])
    check("mmain table entries",
          sum(len(g["entries"]) for g in doc["tables"]) == 11)
    check("mmain terminator at 0x1e0", table_end == 0x1e0)
    check("mmain table totals",
          [row["total"] for row in table_totals(doc)] == [1903, 265, 1])
    check("mmain round-trip", write_mmain(doc) == blob)
    check("mmain bad length refused", _raises(lambda: parse_mmain(b"\x00" * 10)))

    # The retracted case: a FAT root directory must not parse as MMAIN.
    root = _synthetic_fat_root()
    check("fat root rejected by mmain parser", _raises(lambda: parse_mmain(root)))

    # FAT32 root directory parser (the old behaviour, explicit name).
    root_doc = parse_fat_root(root)
    check("fat root record count", len(root_doc["records"]) == 51)
    check("fat root round-trip", write_fat_root(root_doc) == root)
    rows = fat_root_live_listing(root_doc)
    check("fat root live listing",
          rows == [{"name": "DEMO.DAT", "attr": 0x20, "cluster": 0x10002,
                    "size": 4096}])
    check("fat root bad length refused", _raises(lambda: parse_fat_root(b"\x00" * 10)))

    print(f"selftest: {'OK' if not fails else 'FAIL ' + ', '.join(fails)}")
    return 0 if not fails else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Parse and round-trip MMAIN001.DAT (or the FAT32 root "
                    "directory with --fat-root).")
    ap.add_argument("file", nargs="?")
    ap.add_argument("--list", action="store_true",
                    help="list every table entry / live directory record")
    ap.add_argument("--fat-root", action="store_true",
                    help="parse the FAT32 root directory (the old, retracted "
                         "reading of M4.5) instead of MMAIN001.DAT")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if not a.file:
        ap.error("FILE is required")
    blob = Path(a.file).read_bytes()
    try:
        if a.fat_root:
            return report_fat_root(blob, parse_fat_root(blob), a.list)
        return report_mmain(blob, parse_mmain(blob), a.list)
    except ValueError as exc:
        print(f"mmain: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
