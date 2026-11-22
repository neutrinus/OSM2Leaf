#!/usr/bin/env python3
"""Build a complete ``RDSTM001/LCTBL001.DAT`` file (M5.17, H11 G5).

``LCTBL001.DAT`` is a small paged database: 30 TMC location tables, each with
a B-tree index (location code -> ordinal) and zlib-compressed record pages of
at most 500 records.  This tool decodes every structure of the file into a
model (``parse``) and writes the file back from that model (``build``).  The
layout was derived from the EU 2011 card (EXP-2026-11-20-M5.17-lctbl-builder)
and is checked by rebuilding that file byte for byte (``rebuild``).

Addresses
    Every file pointer is a *sector address*: a 0x100-byte sector number
    ``s`` stored as ``((s // 8) << 8) | (s % 8)`` (an 8-sector block plus a
    sector inside it).  Sizes are in 16-bit words unless stated otherwise.

Layout (byte offsets on the EU 2011 file)::

    0x0000  512-byte common Clarion header
    0x0200  constant fill (0xff/0x00 runs)
    0x05cc  range block: u32 0x80000000, header south/west words, u16 flag
            word, u32 0, u16 table count, then per table (u16 0x0220, u16 4,
            BCD4 first code, BCD4 last code)
    0x0800  300 x 6-byte slot table (u32 sector address, u16 sectors);
            slot 7 = the catalog
    0x1000  catalog: table list (46 B each), column schemas (376 B each),
            page directories list (34 B each); zero fill to a sector
    0x4600  per table: B-tree index, 0x1000-byte pages (root first)
    ...     per table: record pages, one zlib stream per <= 500 records,
            streams 4-byte aligned, table start sector aligned
    ...     per table: page directory (u16 500, u16 0, per page u32 word
            offset, u32 compressed words, u32 plain words), sector aligned
    EOF     zero fill to a sector boundary

B-tree page: ``u32 P0`` then ``(8-byte key, u32 P)`` pairs; the key is
``u32 ordinal`` + 4 bytes of BCD location code padded with ``0xf``; ``P`` is
the child's word offset inside the table's index (``0xffffffff`` in a leaf).
A table of <= 339 keys is a single leaf.  Otherwise there are
``L = max(16, ceil(n / 340))`` leaves of ``k = ceil(n / L) - 1`` keys (the last
leaf takes the rest), each followed by one separator key in the root; a
non-root leaf ends with ``u32 0``.  The rule reproduces all 49 two-level
indexes of the EU and US 2011 files.

Records are the C-884 field-directory records (``tools/tmc_fielddir.py``):
``u16 size_words``, a 12-byte field length table, then the fields.  Strings
are single-byte CP1252 (AGENTS: no ISO-8859-2) padded to even length with NUL.
Records are stored in location-code order (the B-tree key order); the names
are *not* collated (rdstm.md "Writer rules for names", rule 4).

Usage::

    lctbl_build.py rebuild LCTBL001.DAT [-o OUT]   # parse + build, byte compare
    lctbl_build.py check FILE                      # structural walk (L1)
    lctbl_build.py catalog FILE                    # codes as (CC, LTN) + per-country counts (M5.64)
    lctbl_build.py synth SPEC.json -o OUT [--header-from LCTBL001.DAT]
                                  [--table-code CC,DB]   # M5.64 generator rule
    lctbl_build.py example-spec -o SPEC.json         # synthetic Polish name set
    lctbl_build.py extract SD.img -o LCTBL001.DAT    # from a full card image
    lctbl_build.py tree ROOT FILE -o TREE           # card tree for cardcheck/l2check
    lctbl_build.py l3 IMG256 FILE                   # firmware field walk (PySh4)
    lctbl_build.py --selftest

Stdlib only.  No vendor bytes are written into the repository.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import random
import sys
import unicodedata
import zlib
from pathlib import Path

SECTOR = 0x100
PAGE = 0x1000
CATALOG_AT = 0x1000
SLOT_TABLE_AT = 0x800
SLOT_COUNT = 300
CATALOG_SLOT = 7
RANGE_BLOCK_AT = 0x5CC
RECORDS_PER_PAGE = 500
NFIELDS = 12
LEAF_ROOT_MAX = 339     # keys in a single-page (root leaf) index
LEAF_SPLIT = 340        # n / LEAF_SPLIT leaves when the index has two levels
MIN_LEAVES = 16
ZLIB_LEVEL = 6
NONE32 = 0xFFFFFFFF
NAME = b"Location Data"

# 0x200..0x5cc: fill runs (value, length), identical in the 2011 EU file.
FILL_RUNS = ((0xFF, 172), (0x00, 2), (0xFF, 254), (0x00, 322), (0xFF, 62), (0x00, 160))
# 0x5cc: u32 0x80000000, the header's south/west bound words (0x186/0x188,
# file-header.md), u16 flags (EU 0x0b0b, US 0x0f0f; meaning UNKNOWN, kept from
# the model), u32 0, then u16 table count.
RANGE_PREFIX_LEN = 14
RANGE_FLAGS_EU = 0x0B0B
RANGE_ENTRY_TAG = bytes.fromhex("02200004")

# Catalog table descriptor, constant tail (after the index address/size):
# u16 0, u16 0, u16 0x0800 (page words), u32 0, u16 0x1000 (page bytes),
# u16 0x000c (index entry bytes), u16 0x2000, then u16 table code.
TABLE_CONST = bytes.fromhex("000000000800000000001000000c2000")
COLUMN_FIRST_WORD = 0x16   # first column record, words from the schema start
PAGE_DIR_HEAD = RECORDS_PER_PAGE.to_bytes(2, "big") + b"\x00\x00"

# Column schema: (name, numeric?)  numeric columns are type 0x8000, strings
# 0x6000; the u16 after the type word pair is the max length in words.
COLUMNS = (
    ("kind code", True), ("road no", False), ("road name", False),
    ("first name", False), ("second name", False), ("area ref", True),
    ("liner ref", True), ("negative offset", True), ("positive offset", True),
    ("urban", True), ("exit/junction no", False), ("Inter-section code", True),
)
STRING_FIELDS = tuple(i for i, (_, numeric) in enumerate(COLUMNS) if not numeric)

HEADER_TEXT = {
    0x000: "CLARION", 0x040: "HITACHI", 0x080: "CLA-NAVI05-01",
    0x0A0: "FORMAT VERSION X08-02-00", 0x0E0: "DATA VERSION 11/06/27/01",
}
# 0x160: u16 0x1400 then "V05.00.00"; 0x180: binary block (file-header.md).
HEADER_160 = b"\x14\x00" + "V05.00.00".encode("utf-16-be")
HEADER_180 = bytes.fromhex("ffff24ff12c00500fb500ff0050402070a060814") + b"\x3f" * 12 + b"\x00" * 14


class LctblError(ValueError):
    """The file or the model breaks the documented layout."""


# --------------------------------------------------------------------------
# primitives

def u16(b: bytes, o: int) -> int:
    return int.from_bytes(b[o:o + 2], "big")


def u32(b: bytes, o: int) -> int:
    return int.from_bytes(b[o:o + 4], "big")


def p16(v: int) -> bytes:
    return v.to_bytes(2, "big")


def p32(v: int) -> bytes:
    return v.to_bytes(4, "big")


def enc_addr(offset: int) -> int:
    if offset % SECTOR:
        raise LctblError(f"address {offset:#x} is not sector aligned")
    s = offset // SECTOR
    return ((s // 8) << 8) | (s % 8)


def dec_addr(value: int) -> int:
    return ((value >> 8) * 8 + (value & 0xFF)) * SECTOR


def align(n: int, a: int) -> int:
    return (n + a - 1) // a * a


def bcd4(code: int) -> bytes:
    digits = str(code)
    if code < 0 or len(digits) > 8:
        raise LctblError(f"location code {code} does not fit 8 BCD digits")
    return bytes.fromhex(digits + "f" * (8 - len(digits)))


def unbcd4(b: bytes) -> int:
    digits = ""
    for x in b:
        for nib in (x >> 4, x & 15):
            if nib == 15:
                return int(digits)
            if nib > 9:
                raise LctblError(f"bad BCD {b.hex()}")
            digits += str(nib)
    return int(digits)


def lname(name: bytes) -> bytes:
    """u16 LE length, then the name padded with one NUL to an even length."""
    return len(name).to_bytes(2, "little") + name + b"\x00" * (len(name) % 2)


def generator_table_code(cc: int, ltn: int) -> int:
    """M5.64 rule: table code = ASCII hex digit of the RDS CC << 8 | LTN.

    This is the inverse of the firmware's request-side derivation
    (`lctbl_lookup_l3.table_code`): the generator must write the code into the
    catalog descriptor or the lookup cannot select the table at all.
    """
    return (ord("%X" % (cc & 0xF)) << 8) | (ltn & 0xFF)


def apply_table_code(spec: dict, cc: int, db: int) -> None:
    """Apply the rule to a synth spec: table i gets CC/DB+i (M5.64)."""
    for i, t in enumerate(spec["tables"]):
        t["code"] = generator_table_code(cc, db + i)


# --------------------------------------------------------------------------
# names: CP1252, letters outside it lose their diacritic (rdstm.md M3.9 rule 2)

_NO_DECOMP = {"ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "ø": "\xf8", "ß": "\xdf"}


def transliterate(text: str) -> str:
    """Keep CP1252 letters, strip the diacritic of any other letter (``Ż`` -> ``Z``)."""
    out = []
    for ch in text:
        try:
            ch.encode("cp1252")
            out.append(ch)
            continue
        except UnicodeEncodeError:
            pass
        if ch in _NO_DECOMP:
            out.append(_NO_DECOMP[ch])
            continue
        base = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
        try:
            base.encode("cp1252")
        except UnicodeEncodeError:
            raise LctblError(f"no CP1252 transliteration for {ch!r}") from None
        out.append(base)
    return "".join(out)


# --------------------------------------------------------------------------
# records (C-884 field directory, type 0)

def encode_record(fields: list) -> bytes:
    """``fields``: 12 values; str/bytes for string columns, int or None for numbers."""
    if len(fields) != NFIELDS:
        raise LctblError("a record has 12 fields")
    lens: list[int] = []
    body = b""
    for i, value in enumerate(fields):
        if value is None or value == "" or value == b"":
            raw = b""
        elif i in STRING_FIELDS:
            raw = value if isinstance(value, bytes) else value.encode("cp1252")
            if any(c < 0x20 or 0x7F <= c <= 0x9F for c in raw):
                raise LctblError(f"control byte in name {raw!r}")
            raw += b"\x00" * (len(raw) % 2)
        else:
            raw = p16(int(value))
        lens.append(len(raw) // 2)
        body += raw
    size_words = 1 + NFIELDS // 2 + len(body) // 2
    if size_words > 0x7FF or max(lens) > 0xFF:
        raise LctblError("record too long")
    return p16(size_words) + bytes(lens) + body


def decode_record(rec: bytes) -> list:
    size = 2 * (u16(rec, 0) & 0x7FF)
    if u16(rec, 0) >> 11 or size != len(rec):
        raise LctblError("record size word")
    lens = list(rec[2:2 + NFIELDS])
    pos = 2 + NFIELDS
    out: list = []
    for i, n in enumerate(lens):
        raw = rec[pos:pos + 2 * n]
        pos += 2 * n
        if not n:
            out.append(None)
        elif i in STRING_FIELDS:
            out.append(raw.rstrip(b"\x00").decode("cp1252", errors="replace"))
        else:
            out.append(int.from_bytes(raw, "big") if n == 1 else raw.hex())
    if pos != len(rec):
        raise LctblError("field lengths do not tile the record")
    return out


def split_page(plain: bytes) -> list[bytes]:
    recs, off = [], 0
    while off < len(plain):
        size = 2 * (u16(plain, off) & 0x7FF)
        if size < 2 + NFIELDS or off + size > len(plain):
            raise LctblError(f"record framing at {off:#x}")
        recs.append(plain[off:off + size])
        off += size
    return recs


# --------------------------------------------------------------------------
# B-tree index

def index_layout(n: int) -> list[list[int]]:
    """Ordinal lists: [root, leaf1, ...]; a single list for a one-page index."""
    if n <= 0:
        raise LctblError("a table needs at least one record")
    if n <= LEAF_ROOT_MAX:
        return [list(range(n))]
    leaves = max(MIN_LEAVES, math.ceil(n / LEAF_SPLIT))
    k = (n - 1) // leaves   # ceil(n / leaves) - 1: one slot per group is the separator
    if (leaves - 1) * (k + 1) >= n:
        raise LctblError(f"no B-tree split for {n} keys")
    pages: list[list[int]] = [[]]
    o = 0
    for i in range(leaves):
        pages.append(list(range(o, o + k)) if i < leaves - 1 else list(range(o, n)))
        o += k
        if i < leaves - 1:
            pages[0].append(o)
            o += 1
    if len(pages[0]) + 1 > LEAF_SPLIT:
        raise LctblError("index needs a third level (not modelled)")
    return pages


def build_index(codes: list[int]) -> bytes:
    pages = index_layout(len(codes))
    key = lambda o: p32(o) + bcd4(codes[o])  # noqa: E731
    out = b""
    if len(pages) == 1:
        page = p32(NONE32) + b"".join(key(o) + p32(NONE32) for o in pages[0])
        return page + b"\xff" * (PAGE - len(page))
    root = p32(PAGE // 2) + b"".join(
        key(o) + p32((i + 2) * PAGE // 2) for i, o in enumerate(pages[0]))
    out += root + b"\xff" * (PAGE - len(root))
    for leaf in pages[1:]:
        page = p32(NONE32) + b"".join(key(o) + p32(NONE32) for o in leaf) + p32(0)
        out += page + b"\xff" * (PAGE - len(page))
    return out


def parse_index(blob: bytes) -> dict[int, int]:
    """ordinal -> location code over every page of one table's index."""
    keys: dict[int, int] = {}
    for p in range(0, len(blob), PAGE):
        page = blob[p:p + PAGE]
        i = 4
        while i + 12 <= PAGE and page[i:i + 8] != b"\xff" * 8:
            ordinal = u32(page, i)
            raw = page[i + 4:i + 8]
            if raw == b"\xff" * 4:
                break  # non-root leaf terminator u32 0
            keys[ordinal] = unbcd4(raw)
            i += 12
    return keys


# --------------------------------------------------------------------------
# model -> bytes

def build_header(data_version: str = "11/06/27/01") -> bytes:
    h = bytearray(b"\xff" * 0x200)
    for off, text in HEADER_TEXT.items():
        if off == 0x0E0:
            text = "DATA VERSION " + data_version
        raw = text.encode("utf-16-be")
        h[off:off + len(raw)] = raw
    h[0x160:0x160 + len(HEADER_160)] = HEADER_160
    h[0x180:0x200] = HEADER_180 + b"\xff" * (0x80 - len(HEADER_180))
    return bytes(h)


def build_column_schema(maxlens: list[int]) -> bytes:
    out = b""
    base = 2 * COLUMN_FIRST_WORD
    recs = []
    for i, (name, numeric) in enumerate(COLUMNS):
        body = p16(0) + p16(maxlens[i]) + (b"\x80\x00" if numeric else b"\x60\x00")
        body += b"\x00" * 4 + p16(i) + lname(name.encode("ascii"))
        recs.append(body)
    pos = base
    for i, body in enumerate(recs):
        nxt = 0xFFFF if i == len(recs) - 1 else (pos + 2 + len(body)) // 2
        out += p16(nxt) + body
        pos += 2 + len(body)
    return out


def build(model: dict) -> bytes:
    tables = model["tables"]
    nt = len(tables)
    if not 1 <= nt <= 0xFFFF:
        raise LctblError("table count")
    # --- per-table payloads
    prepared = []
    for t in tables:
        recs = t["records"]
        codes = t["codes"]
        if len(recs) != len(codes) or any(a >= b for a, b in zip(codes, codes[1:])):
            raise LctblError(f"table {t['code']:#06x}: codes must be strictly ascending, one per record")
        index = build_index(codes)
        pages = [recs[i:i + RECORDS_PER_PAGE] for i in range(0, len(recs), RECORDS_PER_PAGE)]
        streams = [zlib.compress(b"".join(p), ZLIB_LEVEL) for p in pages]
        lens = [[] for _ in range(NFIELDS)]
        for r in recs:
            for i, n in enumerate(r[2:2 + NFIELDS]):
                lens[i].append(n)
        prepared.append({
            "t": t, "index": index, "pages": pages, "streams": streams,
            "maxlens": [max(x) for x in lens],
            "maxwords": max(len(r) for r in recs) // 2,
        })
    # --- catalog geometry
    g1_size = 30 + len(lname(NAME))
    g2_size = 28 + len(lname(NAME)) + len(build_column_schema([0] * NFIELDS))
    g3_size = 18 + len(lname(NAME))
    g1_at = CATALOG_AT
    g2_at = g1_at + nt * g1_size
    g3_at = g2_at + nt * g2_size
    cat_end = align(g3_at + nt * g3_size, SECTOR)
    # --- region placement
    pos = cat_end
    for p in prepared:
        p["index_at"] = pos
        pos += len(p["index"])
    for p in prepared:
        p["data_at"] = pos = align(pos, SECTOR)
        entries, off = [], 0
        for s, page in zip(p["streams"], p["pages"]):
            entries.append((off // 2, align(len(s), 4) // 2, len(b"".join(page)) // 2))
            off += align(len(s), 4)
        p["entries"] = entries
        p["data_words"] = off // 2
        p["data_bytes"] = off
        pos += off
    for p in prepared:
        p["dir_at"] = pos = align(pos, SECTOR)
        p["dir"] = PAGE_DIR_HEAD + b"".join(p32(a) + p32(b) + p32(c) for a, b, c in p["entries"])
        pos += len(p["dir"])
    total = align(pos, SECTOR)
    # --- assemble
    out = bytearray(total)
    out[0:0x200] = model.get("header") or build_header()
    if len(out[0:0x200]) != 0x200:
        raise LctblError("header must be 512 bytes")
    o = 0x200
    for value, n in FILL_RUNS:
        out[o:o + n] = bytes([value]) * n
        o += n
    header = model.get("header") or build_header()
    rb = (p32(0x80000000) + header[0x186:0x18A] + p16(model.get("range_flags", RANGE_FLAGS_EU))
          + p32(0) + p16(nt))
    for p in prepared:
        c = p["t"]["codes"]
        rb += RANGE_ENTRY_TAG + bcd4(c[0]) + bcd4(c[-1])
    if RANGE_BLOCK_AT + len(rb) > SLOT_TABLE_AT:
        raise LctblError("too many tables for the range block")
    out[RANGE_BLOCK_AT:RANGE_BLOCK_AT + len(rb)] = rb
    out[RANGE_BLOCK_AT + len(rb):SLOT_TABLE_AT] = b"\xff" * (SLOT_TABLE_AT - RANGE_BLOCK_AT - len(rb))
    slots = b""
    for i in range(SLOT_COUNT):
        if i == CATALOG_SLOT:
            slots += p32(enc_addr(CATALOG_AT)) + p16((cat_end - CATALOG_AT) // SECTOR)
        else:
            slots += p32(NONE32) + p16(0)
    out[SLOT_TABLE_AT:SLOT_TABLE_AT + len(slots)] = slots
    for i, p in enumerate(prepared):
        a1 = g1_at + i * g1_size
        a2 = g2_at + i * g2_size
        a3 = g3_at + i * g3_size
        nxt = 0xFFFF if i == nt - 1 else (a1 + g1_size - CATALOG_AT) // 2
        g1 = (p16(nxt) + p16((a2 - CATALOG_AT) // 2) + p32(enc_addr(p["index_at"]))
              + p32(len(p["index"]) // 2) + TABLE_CONST + p16(p["t"]["code"]) + lname(NAME))
        g2 = (p16(0xFFFF) + p16((a3 - CATALOG_AT) // 2) + p32(enc_addr(p["data_at"]))
              + p32(p["data_words"]) + p32(0) + p16(p["maxwords"]) + b"\x00" * 6
              + p16(COLUMN_FIRST_WORD) + p16(NFIELDS) + lname(NAME)
              + build_column_schema(p["maxlens"]))
        g3 = (p32(enc_addr(p["dir_at"])) + p32(len(p["dir"]) // 2) + p16(RECORDS_PER_PAGE)
              + b"\x00" * 8 + lname(NAME))
        assert len(g1) == g1_size and len(g2) == g2_size and len(g3) == g3_size
        out[a1:a1 + g1_size] = g1
        out[a2:a2 + g2_size] = g2
        out[a3:a3 + g3_size] = g3
        out[p["index_at"]:p["index_at"] + len(p["index"])] = p["index"]
        o = p["data_at"]
        for s in p["streams"]:
            out[o:o + len(s)] = s
            o += align(len(s), 4)
        out[p["dir_at"]:p["dir_at"] + len(p["dir"])] = p["dir"]
    return bytes(out)


# --------------------------------------------------------------------------
# bytes -> model (and the structural walk used by ``check``)

def walk(data: bytes) -> dict:
    """Decode every structure; raise ``LctblError`` on any layout break."""
    if len(data) < CATALOG_AT or len(data) % SECTOR:
        raise LctblError("file size is not a whole number of sectors")
    slot = data[SLOT_TABLE_AT + 6 * CATALOG_SLOT:SLOT_TABLE_AT + 6 * CATALOG_SLOT + 6]
    if dec_addr(u32(slot, 0)) != CATALOG_AT:
        raise LctblError("slot 7 does not point at the catalog")
    nt = u16(data, RANGE_BLOCK_AT + RANGE_PREFIX_LEN)
    range_flags = u16(data, RANGE_BLOCK_AT + 8)
    tables = []
    o = CATALOG_AT
    while True:
        if data[o + 30:o + 30 + len(lname(NAME))] != lname(NAME):
            raise LctblError(f"table descriptor name at {o:#x}")
        nxt = u16(data, o)
        g2 = CATALOG_AT + 2 * u16(data, o + 2)
        idx_at, idx_words = dec_addr(u32(data, o + 4)), u32(data, o + 8)
        code = u16(data, o + 28)
        g3 = CATALOG_AT + 2 * u16(data, g2 + 2)
        data_at, data_words = dec_addr(u32(data, g2 + 4)), u32(data, g2 + 8)
        maxwords = u16(data, g2 + 16)
        col = g2 + 2 * u16(data, g2 + 24)
        maxlens = []
        while True:
            maxlens.append(u16(data, col + 4))
            w = u16(data, col)
            if w == 0xFFFF:
                break
            col = g2 + 2 * w
        dir_at, dir_words = dec_addr(u32(data, g3)), u32(data, g3 + 4)
        if u16(data, g3 + 8) != RECORDS_PER_PAGE or data[dir_at:dir_at + 4] != PAGE_DIR_HEAD:
            raise LctblError(f"page directory of table {code:#06x}")
        npages = (dir_words * 2 - 4) // 12
        records = []
        for k in range(npages):
            e = dir_at + 4 + 12 * k
            off, cw, pw = u32(data, e), u32(data, e + 4), u32(data, e + 8)
            start = data_at + 2 * off
            eng = zlib.decompressobj()
            plain = eng.decompress(data[start:start + 2 * cw + 4])
            if not eng.eof or len(plain) != 2 * pw:
                raise LctblError(f"table {code:#06x} page {k}: stream")
            page = split_page(plain)
            if k < npages - 1 and len(page) != RECORDS_PER_PAGE:
                raise LctblError(f"table {code:#06x} page {k}: {len(page)} records")
            records.extend(page)
        keys = parse_index(data[idx_at:idx_at + 2 * idx_words])
        if sorted(keys) != list(range(len(records))):
            raise LctblError(f"table {code:#06x}: index ordinals != records")
        codes = [keys[i] for i in range(len(records))]
        tables.append({
            "code": code, "records": records, "codes": codes,
            "maxlens": maxlens, "maxwords": maxwords, "pages": npages,
            "index_pages": 2 * idx_words // PAGE, "data_words": data_words,
        })
        if nxt == 0xFFFF:
            break
        o = CATALOG_AT + 2 * nxt
    if len(tables) != nt:
        raise LctblError(f"range block says {nt} tables, catalog lists {len(tables)}")
    return {"header": data[:0x200], "range_flags": range_flags, "tables": tables}


def parse(data: bytes) -> dict:
    return walk(data)


def first_diff(a: bytes, b: bytes) -> int:
    n = min(len(a), len(b))
    for i in range(0, n, 4096):
        if a[i:i + 4096] != b[i:i + 4096]:
            for j in range(i, min(n, i + 4096)):
                if a[j] != b[j]:
                    return j
    return -1 if len(a) == len(b) else n


# --------------------------------------------------------------------------
# synthetic name set

def model_from_spec(spec: dict, header: bytes | None = None) -> dict:
    """Spec: {"tables": [{"code": 12825, "records": [{"location": 1, "fields": [...12]}]}]}.

    String fields are transliterated to CP1252 (``Łódź`` -> ``Lódz``); records
    are ordered by location code, the B-tree key.
    """
    tables = []
    for t in spec["tables"]:
        rows = sorted(t["records"], key=lambda r: r["location"])
        recs = []
        for r in rows:
            fields = [transliterate(v) if isinstance(v, str) and i in STRING_FIELDS else v
                      for i, v in enumerate(r["fields"])]
            recs.append(encode_record(fields))
        tables.append({
            "code": int(t["code"]),
            "codes": [int(r["location"]) for r in rows],
            "records": recs,
        })
    model = {"header": header, "tables": tables}
    if "range_flags" in spec:
        model["range_flags"] = int(spec["range_flags"])
    return model


# --------------------------------------------------------------------------
# commands

def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def summary(model: dict) -> str:
    t = model["tables"]
    return (f"tables {len(t)} records {sum(len(x['records']) for x in t)} "
            f"pages {sum(math.ceil(len(x['records']) / RECORDS_PER_PAGE) for x in t)}")


def cmd_catalog(a) -> int:
    """List every catalog table code, decoded to (CC, LTN), with per-country counts."""
    import tmc_reception

    data = Path(a.file).read_bytes()
    model = parse(data)
    tables_cc, records_cc = collections.Counter(), collections.Counter()
    print(f"file    {len(data)} B sha256 {sha(data)}")
    print(f"walk    {summary(model)}")
    print("row   code  CC LTN  records  codes")
    for i, t in enumerate(model["tables"]):
        pair = tmc_reception.code_cc_ltn(t["code"])
        cc, ltn = pair if pair else (None, None)
        if cc is not None:
            tables_cc[cc] += 1
            records_cc[cc] += len(t["records"])
        print(f"{i:3d}  {t['code']:04x}  {str(cc):>2} {str(ltn):>3}  "
              f"{len(t['records']):7d}  {t['codes'][0]}..{t['codes'][-1]}")
    print("per country (CC: tables, records):")
    for cc in sorted(tables_cc):
        print(f"  CC {cc:x}: {tables_cc[cc]:2d} tables, {records_cc[cc]:7d} records")
    print(f"Poland CC 3: {tables_cc.get(3, 0)} tables, {records_cc.get(3, 0)} records")
    return 0


def cmd_rebuild(a) -> int:
    data = Path(a.file).read_bytes()
    model = parse(data)
    out = build(model)
    print(f"input   {len(data)} B sha256 {sha(data)}")
    print(f"model   {summary(model)}")
    print(f"rebuilt {len(out)} B sha256 {sha(out)}")
    if a.output:
        Path(a.output).write_bytes(out)
    d = first_diff(data, out)
    print("IDENTICAL" if d < 0 else f"DIFFERENT first byte {d:#x}")
    return 0 if d < 0 else 1


def cmd_check(a) -> int:
    data = Path(a.file).read_bytes()
    model = walk(data)
    print(f"file    {len(data)} B sha256 {sha(data)}")
    print(f"walk    {summary(model)}")
    for i, t in enumerate(model["tables"]):
        if a.verbose:
            print(f"  table {i:2d} code {t['code']:04x} records {len(t['records']):6d} "
                  f"pages {t['pages']:3d} index pages {t['index_pages']:3d} "
                  f"codes {t['codes'][0]}..{t['codes'][-1]}")
    print("OK")
    return 0


def cmd_synth(a) -> int:
    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    if a.table_code:
        parts = [int(x, 0) for x in a.table_code.split(",")]
        if len(parts) != 2:
            raise LctblError("--table-code needs CC,DB, got %r" % a.table_code)
        apply_table_code(spec, *parts)
        print(f"table code rule: CC {parts[0]}, DB {parts[1]} -> " +
              ", ".join("%#06x" % t["code"] for t in spec["tables"]))
    header = Path(a.header_from).read_bytes()[:0x200] if a.header_from else None
    model = model_from_spec(spec, header)
    out = build(model)
    Path(a.output).write_bytes(out)
    back = walk(out)
    ok = all(x["records"] == y["records"] and x["codes"] == y["codes"]
             for x, y in zip(model["tables"], back["tables"]))
    print(f"wrote   {a.output} {len(out)} B sha256 {sha(out)}")
    print(f"model   {summary(model)}; walk-back {'OK' if ok else 'MISMATCH'}")
    return 0 if ok else 1


def cmd_tree(a) -> int:
    """Symlink a card tree, put FILE in as RDSTM001/LCTBL001.DAT, rebuild DRSTR001.DAT."""
    import os
    import drstr_ze0
    src, dst = Path(a.root).resolve(), Path(a.output)
    if dst.exists():
        raise LctblError(f"{dst} exists")
    for dirpath, dirnames, filenames in os.walk(src):
        rel = Path(dirpath).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for name in filenames:
            if rel / name in (Path("RDSTM001/LCTBL001.DAT"), Path("DRSTR001.DAT")):
                continue
            (dst / rel / name).symlink_to(Path(dirpath) / name)
    (dst / "RDSTM001" / "LCTBL001.DAT").write_bytes(Path(a.file).read_bytes())
    (dst / "DRSTR001.DAT").symlink_to(src / "DRSTR001.DAT")  # case/order reference
    drstr = drstr_ze0.build(dst)
    (dst / "DRSTR001.DAT").unlink()
    (dst / "DRSTR001.DAT").write_bytes(drstr)
    same = drstr == (src / "DRSTR001.DAT").read_bytes()
    print(f"tree    {dst}: LCTBL001.DAT sha256 {sha(Path(a.file).read_bytes())}")
    print(f"drstr   {len(drstr)} B, identical to the source DRSTR001.DAT: {same}")
    return 0


def cmd_extract(a) -> int:
    """Copy RDSTM001/LCTBL001.DAT out of a full SD image (FAT walk, mkcard)."""
    import mkcard
    with open(a.image, "rb") as h:
        _, geo, fat = mkcard.open_map_partition(h)
        data = mkcard.img_read(h, geo, fat, a.path)
    Path(a.output).write_bytes(data)
    print(f"extract {a.path}: {len(data)} B sha256 {sha(data)}")
    return 0


def cmd_example_spec(a) -> int:
    spec = _synthetic_spec()
    Path(a.output).write_text(json.dumps(spec, ensure_ascii=False, indent=0), encoding="utf-8")
    n = sum(len(t["records"]) for t in spec["tables"])
    print(f"wrote   {a.output}: {len(spec['tables'])} tables, {n} records (synthetic Polish names)")
    return 0


# --------------------------------------------------------------------------
# L3: the firmware field walk reads our catalog descriptor and our records

def catalog_descriptor(data: bytes, table: int) -> bytes:
    """Bytes of table ``table``'s column-schema descriptor (catalog group 2)."""
    o = CATALOG_AT
    for _ in range(table):
        nxt = u16(data, o)
        if nxt == 0xFFFF:
            raise LctblError(f"no table {table}")
        o = CATALOG_AT + 2 * nxt
    g2 = CATALOG_AT + 2 * u16(data, o + 2)
    col = g2 + 2 * u16(data, g2 + 24)
    while u16(data, col) != 0xFFFF:
        col = g2 + 2 * u16(data, col)
    end = col + 14 + len(lname(b"x" * data[col + 14]))
    return data[g2:end]


def handle_block(desc: bytes) -> bytearray:
    """RAM handle block for ``fn 0x003f51e0``: u16[+2] = header word offset, then
    the catalog descriptor as native halfwords (ASSUMPTION: the loader swaps)."""
    import rdstm_write
    block = bytearray(0x400)
    hdr_words = rdstm_write.HDR_WORDS
    block[2:4] = hdr_words.to_bytes(2, "little")
    sw = rdstm_write.swap16(desc[: len(desc) // 2 * 2])
    block[2 * hdr_words:2 * hdr_words + len(sw)] = sw[: 0x400 - 2 * hdr_words]
    return block


def cmd_l3(a) -> int:
    import rdstm_write
    image = Path(a.image).read_bytes()
    data = Path(a.file).read_bytes()
    model = walk(data)
    eng = rdstm_write.l3_engine(image)
    print(f"image   sha256 {sha(image)}")
    print(f"file    sha256 {sha(data)} ({summary(model)})")
    rows = ok = 0
    for ti, t in enumerate(model["tables"]):
        eng.write_mem(rdstm_write.BLOCK_VA, bytes(handle_block(catalog_descriptor(data, ti))))
        recs = t["records"]
        picks = range(len(recs)) if len(recs) <= a.per_table else sorted(
            random.Random(ti).sample(range(len(recs)), a.per_table))
        good = 0
        for i in picks:
            rec = recs[i]
            got = rdstm_write.l3_record(eng, rec)
            exp = rdstm_write.expected_walk(rec)
            fields = [rec[o:o + 2 * n] for o, n in got] if all(o is not None for o, _ in got) else None
            want = decode_record(rec)
            back = None
            if fields is not None:
                back = [None if not f else (f.rstrip(b"\x00").decode("cp1252") if k in STRING_FIELDS
                                            else int.from_bytes(f, "big"))
                        for k, f in enumerate(fields)]
            match = got == exp and back == want
            good += match
            if not match and a.verbose:
                print(f"  table {ti} record {i}: firmware {got} expected {exp}")
        rows += len(picks)
        ok += good
        print(f"  table {ti:2d} code {t['code']:04x}: records walked {len(picks):4d} "
              f"firmware fields == model {good}")
    print(f"l3: records {rows} firmware 0x003f61bc/0x003f5d98 fields == model {ok}")
    # negative controls on the first table's first record
    rec = model["tables"][0]["records"][0]
    desc = bytearray(catalog_descriptor(data, 0))
    desc[26:28] = p16(NFIELDS - 1)           # catalog says 11 fields
    eng.write_mem(rdstm_write.BLOCK_VA, bytes(handle_block(bytes(desc))))
    neg1 = rdstm_write.l3_record(eng, rec) != rdstm_write.expected_walk(rec)
    eng.write_mem(rdstm_write.BLOCK_VA, bytes(handle_block(catalog_descriptor(data, 0))))
    bad = bytearray(rec)
    bad[0] |= 0xE0                            # record type 7: rejected by 0x003f56bc
    neg2 = all(o is None for o, _ in rdstm_write.l3_record(eng, bytes(bad)))
    print(f"negative: 11-field catalog changes the walk {neg1}; type-7 record rejected {neg2}")
    return 0 if ok == rows and neg1 and neg2 else 1


# --------------------------------------------------------------------------
# self-test (synthetic, no vendor bytes)

PL_PLACES = ("Łódź", "Gdańsk", "Kraków", "Poznań", "Wrocław", "Białystok", "Zielona Góra",
             "Bielsko-Biała", "Świecko", "Żółkiewka", "Częstochowa", "Rzeszów")
PL_STREETS = ("ulica Żółta", "aleja Niepodległości", "ulica Świętokrzyska", "plac Grunwaldzki",
              "ulica Łąkowa", "ulica Mickiewicza")


def _synthetic_spec(sizes=(1, 5, 603, 2359, 700), seed: int = 17) -> dict:
    """A deterministic synthetic Polish name set (no card data)."""
    rnd = random.Random(seed)
    tables = []
    for ti, n in enumerate(sizes):
        recs = []
        for k in range(n):
            loc = 1 + 3 * k + ti
            place = PL_PLACES[rnd.randrange(len(PL_PLACES))]
            recs.append({"location": loc, "fields": [
                20111 if k else 100, "A%d" % (k % 9) if k % 3 == 0 else None,
                "Autostrada Wolności" if k % 3 == 0 else None,
                "%s %d" % (PL_STREETS[k % len(PL_STREETS)], k) if k else "Polska",
                place if k % 2 else None,
                k % 50, None if k % 4 else 3, max(loc - 3, 0), loc + 3, k % 2,
                "%d" % (k % 70) if k % 5 == 0 else None, 0,
            ]})
        rnd.shuffle(recs)  # the builder must order by location code
        tables.append({"code": 0x2E01 + ti, "records": recs})
    return {"tables": tables}


def _selftest() -> int:
    fails: list[str] = []

    def check(name, cond):
        if not cond:
            fails.append(name)

    check("addr 0x4600", enc_addr(0x4600) == 0x0806 and dec_addr(0x0806) == 0x4600)
    check("addr 0x721800", enc_addr(0x721800) == 0x0E4300)
    check("addr 0x316600", enc_addr(0x316600) == 0x062C06)
    check("bcd", bcd4(23523) == bytes.fromhex("23523fff") and unbcd4(bytes.fromhex("1fffffff")) == 1)
    rec = encode_record([20111, "D5", None, "Praha", None, 50, None, 7210, 7212, 1, None, 7])
    check("record walk", decode_record(rec) == [20111, "D5", None, "Praha", None, 50, None, 7210, 7212, 1, None, 7])
    check("record size word", u16(rec, 0) * 2 == len(rec) and rec[2] == 1)
    check("cp1252", encode_record([1, None, None, "Zólta", None, None, None, None, None, None, None, None])[16:21]
          == b"Z\xf3lta")
    check("cp1252 offset", encode_record([1] + [None] * 11)[14:16] == b"\x00\x01")
    try:
        encode_record([1, None, None, "Żółta", None, None, None, None, None, None, None, None])
        check("latin-2 rejected", False)
    except UnicodeEncodeError:
        pass
    # B-tree split, pinned to the EU 2011 shapes (table sizes 603, 2359, 16634)
    check("leaf 1", len(index_layout(1)) == 1)
    lay = index_layout(603)
    check("603 -> 16 leaves of 37", len(lay) == 17 and len(lay[1]) == 37 and len(lay[-1]) == 33)
    check("16634 -> 49 leaves", len(index_layout(16634)) == 50 and len(index_layout(16634)[1]) == 339)
    for n in (340, 341, 5000, 16634):
        lay = index_layout(n)
        check(f"layout {n} covers", sorted(o for p in lay for o in p) == list(range(n)))

    spec = _synthetic_spec()
    model = model_from_spec(spec)
    blob = build(model)
    back = walk(blob)
    check("table count", len(back["tables"]) == 5)
    check("records survive", all(x["records"] == y["records"] for x, y in zip(model["tables"], back["tables"])))
    check("codes ascending", all(t["codes"] == sorted(t["codes"]) for t in back["tables"]))
    check("pages of 500", back["tables"][3]["pages"] == 5)
    check("16-leaf index", back["tables"][2]["index_pages"] == 17)
    check("deterministic", build(model) == blob)
    check("descriptor size", len(catalog_descriptor(blob, 1)) == 376)
    hb = handle_block(catalog_descriptor(blob, 1))
    check("handle block fields", int.from_bytes(hb[16 + 24:16 + 28], "little") == 0x0C0016)
    check("rebuild identical", build(parse(blob)) == blob)
    first = decode_record(back["tables"][2]["records"][0])
    check("name decodes", first[3] == "Polska")
    check("transliteration", transliterate("Łódź Żółta Świecko") == "Lódz Zólta Swiecko")
    check("pl name stored cp1252", decode_record(back["tables"][2]["records"][6])[3] == "ulica Zólta 6")
    # negative controls: a corrupted stream / catalog must fail the walk
    for label, off in (("stream", back_off(blob, "data")), ("catalog", CATALOG_AT + 31)):
        bad = bytearray(blob)
        bad[off] ^= 0xFF
        try:
            walk(bytes(bad))
            check(f"corrupt {label} rejected", False)
        except (LctblError, zlib.error, KeyError, IndexError, ValueError):
            pass
    unsorted = {"code": 1, "codes": [5, 3], "records": [rec, rec]}
    try:
        build({"tables": [unsorted]})
        check("unsorted codes rejected", False)
    except LctblError:
        pass
    # M5.64: the generator rule and its lctbl_lookup_l3 negative control.
    import lctbl_lookup_l3 as LL
    check("poland code 3/16 is 0x3310", generator_table_code(3, 0x10) == 0x3310)
    check("poland code 3/25 is 0x3319", generator_table_code(3, 25) == 0x3319)
    spec_code = {"tables": [
        {"records": [{"location": 1234, "fields": [100] + [None] * 11}]},
        {"records": [{"location": 1234, "fields": [20111] + [None] * 11}]},
    ]}
    apply_table_code(spec_code, 3, 0x10)
    check("flag assigns 0x3310/0x3311",
          [t["code"] for t in spec_code["tables"]] == [0x3310, 0x3311])
    model_code = parse(build(model_from_spec(spec_code)))
    present, expected = LL.model_record(model_code, 3, 0x11, 1234)
    check("catalog code holds the expected record", present and expected is not None)
    wrong_present, _ = LL.model_record(model_code, 4, 0x11, 1234)
    check("wrong code is not in the lookup model", not wrong_present)
    check("wrong code makes the lookup miss", not LL.judge(True, expected, LL.NOT_FOUND, None)[1])
    print(f"negative: a wrong country (4 instead of 3) misses the record "
          f"the 0x3311 catalog holds: {not wrong_present}")
    print(f"selftest: {'OK' if not fails else 'FAIL ' + ', '.join(fails)}")
    return 0 if not fails else 1


def back_off(blob: bytes, what: str) -> int:
    """Byte offset of the first record stream (for the negative control)."""
    g2 = CATALOG_AT + 2 * u16(blob, CATALOG_AT + 2)
    return dec_addr(u32(blob, g2 + 4)) + 10


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("rebuild", help="parse a factory file and write it back; compare bytes")
    p.add_argument("file")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_rebuild)
    p = sub.add_parser("check", help="structural walk of a built or factory file")
    p.add_argument("file")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("catalog", help="list catalog codes as (CC, LTN) with per-country counts")
    p.add_argument("file")
    p.set_defaults(func=cmd_catalog)
    p = sub.add_parser("synth", help="build a file from a JSON name-set spec")
    p.add_argument("spec")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--header-from", help="copy the 512-byte header from this file")
    p.add_argument("--table-code", metavar="CC,DB",
                   help="write table codes as ord(hex digit of CC) << 8 | DB+i (M5.64 rule)")
    p.set_defaults(func=cmd_synth)
    p = sub.add_parser("tree", help="symlinked card tree with FILE as LCTBL001.DAT (for cardcheck/l2check)")
    p.add_argument("root", help="extracted card root")
    p.add_argument("file")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_tree)
    p = sub.add_parser("extract", help="copy LCTBL001.DAT out of a full SD image")
    p.add_argument("image")
    p.add_argument("--path", default="RDSTM001/LCTBL001.DAT")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_extract)
    p = sub.add_parser("example-spec", help="write the synthetic Polish name-set spec")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_example_spec)
    p = sub.add_parser("l3", help="run the firmware field walk (PySh4) on a built file")
    p.add_argument("image", help="IMG256 (EU2011 build A Navi.exe)")
    p.add_argument("file")
    p.add_argument("--per-table", type=int, default=200)
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_l3)
    return ap


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    if a.selftest:
        return _selftest()
    if not getattr(a, "func", None):
        build_parser().print_help()
        return 2
    try:
        return a.func(a)
    except (OSError, LctblError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
