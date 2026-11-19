#!/usr/bin/env python3
"""Walk the C-884 per-record field directory of the TMC location records (M4.16b).

The firmware accessor ``fn 0x003f61bc(handle, record, index)`` (EU2011 build A
``Navi.exe``) resolves a field through three helpers, read from the code
(EXP-2026-11-19-M4.16b-tmc-field-directory):

* ``0x003f56bc`` -- data start.  ``w = u16 record[0]``; ``(w & 0xe000) <=
  0xc000`` and ``(w >> 11) & 3`` in ``{0, 1}`` or the record is rejected; type
  ``w >> 13``: 0 -> ``record + 2``; 5 -> ``record + 8``; 2/3 -> ``record +
  2*(hi + lo + 8)`` of ``u16 record[10]``; 6 -> ``record + 2*(hi + lo + 2)`` of
  ``u16 record[2]``; anything else -> invalid.
* ``0x003f57a8`` -- the field count (``u16`` at ``+26`` of a block reached
  through the handle; runtime state, 12 for this record type).
* ``0x003f5d98`` -- length of field ``i`` in 16-bit words: byte ``i`` of a
  length table at the data start, even ``i`` = high byte of the halfword.
* ``0x003f5e10`` -- offset of field ``i``: ``data + 2 * ((n + 1) // 2 +
  sum(len[0:i]))`` -- the length table is padded to whole halfwords.

``0x003f51e0`` (the ``0x00d53500`` lookup) only maps the handle to that block;
it does not hold field lengths.  Halfwords are read as native ``u16``; the card
stores them big-endian, so ``even index = first byte`` on disk.

The records live in the zlib pages of ``LCTBL001.DAT`` (the volume pairs
``RDSTM001`` with ``LCTBL001.DAT``, type ``0x14e4``).  The location code is
not a record field: it comes from the ordinal -> BCD code index at
``0x4600..0x316600`` of the same file (one run per location table).
``RDSTM001.DAT`` carries, per location table, a block of location -> link
records and a block of ``(code, negative, positive)`` triples; ``join``
checks the decoded records against those triples.

Usage::

    tmc_fielddir.py walk LCTBL001.DAT [--fields 12] [--pairing be|le]
    tmc_fielddir.py index LCTBL001.DAT
    tmc_fielddir.py join LCTBL001.DAT RDSTM001.DAT [--shift K] [--examples N]
    tmc_fielddir.py --selftest

Stdlib only.  No vendor bytes are written anywhere.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import struct
import sys
import zlib
from pathlib import Path

NFIELDS = 12
FIELD_NAMES = (
    "type", "road_no", "road_name", "first_name", "second_name", "area",
    "linear", "negative", "positive", "urban", "exit_no", "intersection",
)
STRING_FIELDS = (1, 2, 3, 4, 10)
INDEX_START = 0x4600
INDEX_END = 0x316600
FIRST_STREAM = 0x316600
RDSTM_FIRST_BLOCK = 0x1300


# --------------------------------------------------------------------------
# firmware rules (0x003f56bc / 0x003f5d98 / 0x003f5e10)

def data_start(rec: bytes) -> int:
    """Byte offset of the length table, or -1 (``0x003f56bc``)."""
    if len(rec) < 2:
        return -1
    w = int.from_bytes(rec[0:2], "big")
    if (w & 0xE000) > 0xC000:
        return -1
    if ((w & 0x1800) >> 11) not in (0, 1):
        return -1
    kind = w >> 13
    if kind in (2, 3):
        v = int.from_bytes(rec[10:12], "big")
        return 2 * ((v >> 8) + (v & 0xFF) + 8)
    if kind == 5:
        return 8
    if kind == 6:
        v = int.from_bytes(rec[2:4], "big")
        return 2 * ((v >> 8) + (v & 0xFF) + 2)
    if kind == 0:
        return 2
    return -1


def field_len(rec: bytes, start: int, index: int, pairing: str = "be") -> int:
    """Length of field ``index`` in 16-bit words (``0x003f5d98``)."""
    half = rec[start + 2 * (index >> 1) : start + 2 * (index >> 1) + 2]
    if len(half) < 2:
        return -1
    hi, lo = (half[0], half[1]) if pairing == "be" else (half[1], half[0])
    return hi if index % 2 == 0 else lo


def field_offset(rec: bytes, start: int, nfields: int, index: int, pairing: str = "be") -> int:
    """Byte offset of field ``index`` (``0x003f5e10``)."""
    words = (nfields + 1) // 2
    for k in range(index):
        words += field_len(rec, start, k, pairing)
    return start + 2 * words


def decode_record(rec: bytes, nfields: int = NFIELDS, pairing: str = "be") -> dict:
    start = data_start(rec)
    if start < 0:
        return {"ok": False, "why": "type"}
    lens = [field_len(rec, start, i, pairing) for i in range(nfields)]
    if min(lens) < 0:
        return {"ok": False, "why": "short"}
    fields = []
    for i in range(nfields):
        off = field_offset(rec, start, nfields, i, pairing)
        fields.append(rec[off : off + 2 * lens[i]])
    end = field_offset(rec, start, nfields, nfields, pairing)
    return {"ok": end == len(rec), "lens": lens, "fields": fields, "end": end, "size": len(rec)}


def u16(b: bytes):
    return int.from_bytes(b, "big") if len(b) == 2 else None


def text(b: bytes) -> str:
    return b.rstrip(b"\x00").decode("latin-1")


# --------------------------------------------------------------------------
# LCTBL001: pages and index

def scan_streams(data: bytes, start: int = FIRST_STREAM) -> list[bytes]:
    out = []
    off = start
    while off < len(data) - 2:
        if data[off] != 0x78:
            nxt = data.find(b"\x78\x9c", off)
            if nxt < 0:
                break
            off = nxt
        eng = zlib.decompressobj()
        try:
            plain = eng.decompress(data[off:])
        except zlib.error:
            nxt = data.find(b"\x78\x9c", off + 1)
            if nxt < 0:
                break
            off = nxt
            continue
        if not eng.eof:
            nxt = data.find(b"\x78\x9c", off + 1)
            if nxt < 0:
                break
            off = nxt
            continue
        out.append(plain)
        off = len(data) - len(eng.unused_data)
    return out


def split_records(plain: bytes) -> list[bytes]:
    """Records by the size word (low 11 bits = size in words)."""
    recs = []
    off = 0
    while off + 2 <= len(plain):
        w = int.from_bytes(plain[off : off + 2], "big")
        size = 2 * (w & 0x7FF)
        if size == 0:
            break
        recs.append(plain[off : off + size])
        off += size
    return recs


def load_records(lctbl: bytes) -> list[bytes]:
    recs = []
    for plain in scan_streams(lctbl):
        recs.extend(split_records(plain))
    return recs


def bcd(b: bytes):
    digits = ""
    for x in b:
        for nib in (x >> 4, x & 15):
            if nib == 15:
                return digits or None
            if nib > 9:
                return None
            digits += str(nib)
    return digits or None


PAGE = 0x1000
LEAF_ENTRIES = 340


def parse_index(lctbl: bytes, start: int = INDEX_START, end: int = INDEX_END) -> list[dict]:
    """Ordinal -> location code runs from the index leaf pages.

    The index is a set of 0x1000-byte pages from ``0x4600``.  A leaf page
    starts with ``ffffffff`` and holds up to 340 entries of 12 bytes:
    ``u32 ordinal`` + 8 bytes of BCD digits padded with ``0xf``.  Upper pages
    (first word ``0x00000800``) are skipped.  A run starts at ordinal 0; there
    is one run per location table.
    """
    tables: list[dict] = []
    for page in range(start, end, PAGE):
        if lctbl[page : page + 4] != b"\xff\xff\xff\xff":
            continue
        for i in range(LEAF_ENTRIES):
            e = lctbl[page + 4 + 12 * i : page + 16 + 12 * i]
            if len(e) < 12 or e == b"\xff" * 12:
                break
            ordinal = int.from_bytes(e[:4], "big")
            code = bcd(e[4:])
            if code is None:
                break
            if ordinal == 0:
                tables.append({})
            if tables:
                tables[-1][ordinal] = int(code)
    return tables


def table_slices(tables: list[dict]) -> list[tuple[int, int]]:
    """Record ranges per table: table ``t`` holds ``max(ordinal)+1`` records."""
    out = []
    base = 0
    for t in tables:
        n = max(t) + 1
        out.append((base, base + n))
        base += n
    return out


# --------------------------------------------------------------------------
# RDSTM001: location -> link records and (code, neg, pos) triples

def next_nonzero(d: bytes, off: int) -> int:
    while off < len(d) and d[off] == 0:
        off += 1
    return off & ~1


def parse_link_block(d: bytes, off: int):
    """Records ``u16 size|0xffff, u16 code, u16 n, n x (u16 k, (k>>2) x u32 ref)``."""
    recs = {}
    while off + 6 <= len(d):
        w = int.from_bytes(d[off : off + 2], "big")
        if w == 0:
            return None
        code = int.from_bytes(d[off + 2 : off + 4], "big")
        n = int.from_bytes(d[off + 4 : off + 6], "big")
        p = off + 6
        groups = []
        for _ in range(n):
            k = int.from_bytes(d[p : p + 2], "big")
            refs = [int.from_bytes(d[p + 2 + 4 * j : p + 6 + 4 * j], "big") for j in range(k >> 2)]
            groups.append((k & 3, refs))
            p += 2 + 4 * (k >> 2)
        if w != 0xFFFF and 2 * (w & 0x7FF) != p - off:
            return None
        recs[code] = groups
        off = p
        if w == 0xFFFF:
            return recs, off
    return None


def parse_triples(d: bytes, off: int):
    n = int.from_bytes(d[off : off + 2], "big")
    tri = {}
    for i in range(n):
        a = off + 2 + 6 * i
        c, neg, pos = struct.unpack(">HHH", d[a : a + 6])
        tri[c] = (neg, pos)
    return tri, off + 2 + 6 * n


def rdstm_pairs(d: bytes, start: int = RDSTM_FIRST_BLOCK, limit: int = 0) -> list[dict]:
    """Consecutive (link block, triple block) pairs from ``start``.

    Each block starts on a 0x100 boundary; the walk stops at the first block
    that does not parse (the file carries other structures after the pairs).
    """
    out = []
    off = start
    while off < len(d):
        lb = parse_link_block(d, off)
        if lb is None:
            break
        links, end = lb
        toff = (next_nonzero(d, end) // 0x100) * 0x100
        while True:  # a table's link records may span several 0xffff-closed blocks
            more = parse_link_block(d, toff)
            if more is None:
                break
            links.update(more[0])
            toff = (next_nonzero(d, more[1]) // 0x100) * 0x100
        tri, tend = parse_triples(d, toff)
        if set(tri) != set(links):
            break
        out.append({"links_at": off, "triples_at": toff, "links": links, "triples": tri})
        if limit and len(out) >= limit:
            break
        off = (next_nonzero(d, tend) // 0x100) * 0x100
    return out


# --------------------------------------------------------------------------
# commands

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def walk_stats(recs: list[bytes], nfields: int, pairing: str):
    ok = bad = 0
    kinds = collections.Counter()
    hist = [collections.Counter() for _ in range(nfields)]
    for r in recs:
        kinds[int.from_bytes(r[0:2], "big") >> 13] += 1
        dec = decode_record(r, nfields, pairing)
        if dec.get("ok"):
            ok += 1
            for i, n in enumerate(dec["lens"]):
                hist[i][n] += 1
        else:
            bad += 1
    return ok, bad, kinds, hist


def cmd_walk(a) -> int:
    path = Path(a.lctbl)
    data = path.read_bytes()
    recs = load_records(data)
    ok, bad, kinds, hist = walk_stats(recs, a.fields, a.pairing)
    print(f"file {path.name} sha256 {hashlib.sha256(data).hexdigest()}")
    print(f"records {len(recs)} fields {a.fields} pairing {a.pairing}: directory exact {ok}, mismatch {bad}")
    print(f"record type (w>>13): {dict(sorted(kinds.items()))}")
    if ok:
        print(f"field 0 is one word in {hist[0][1]} of {ok} records (type code)")
        for i in range(a.fields):
            name = FIELD_NAMES[i] if a.fields == NFIELDS else f"f{i}"
            nz = sum(v for k, v in hist[i].items() if k)
            print(f"  field {i:2d} {name:<13} present {nz:7d}  max_words {max(hist[i])}")
    return 0 if bad == 0 else 1


def cmd_index(a) -> int:
    data = Path(a.lctbl).read_bytes()
    tables = parse_index(data)
    recs = load_records(data)
    slices = table_slices(tables)
    total = sum(e - s for s, e in slices)
    entries = sum(len(t) for t in tables)
    print(f"index runs {len(tables)} entries {entries} records-by-index {total} records-in-pages {len(recs)}")
    for ti, (t, (s, e)) in enumerate(zip(tables, slices)):
        if e - s >= a.min_records:
            name = ""
            for r in recs[s : min(e, s + 4)]:
                dec = decode_record(r)
                if dec.get("ok") and u16(dec["fields"][0]) == 300:
                    name = text(dec["fields"][3])
            print(f"  table {ti:2d} records {e - s:6d} entries {len(t):6d} codes {min(t.values())}..{max(t.values())} {name}")
    return 0 if total == len(recs) else 1


def neg_pos(recs: list[bytes]) -> list:
    out = []
    for r in recs:
        f = decode_record(r)["fields"]
        out.append((u16(f[7]), u16(f[8])))
    return out


def join_table(np_list, table, rd_pair, base, shift):
    """neg/pos of record ``base+k`` vs the RDSTM triple of code ``table[k+shift]``."""
    tri = rd_pair["triples"]
    agree = tested = 0
    for k in range(max(table) + 1):
        code = table.get(k + shift)
        if code is None or code not in tri or base + k >= len(np_list):
            continue
        neg, pos = np_list[base + k]
        if neg is None or pos is None:
            continue
        tested += 1
        agree += tri[code] == (neg, pos)
    return agree, tested


def cmd_join(a) -> int:
    ldata = Path(a.lctbl).read_bytes()
    rdata = Path(a.rdstm).read_bytes()
    recs = load_records(ldata)
    tables = parse_index(ldata)
    slices = table_slices(tables)
    pairs = rdstm_pairs(rdata)
    nps = neg_pos(recs)
    print(f"LCTBL records {len(recs)} tables {len(tables)}; RDSTM block pairs {len(pairs)}")
    big = [i for i, (s, e) in enumerate(slices) if e - s >= a.min_records]
    total_agree = total_tested = 0
    first = None
    for pi, pr in enumerate(pairs):
        best = None
        for ti in big:
            s, _ = slices[ti]
            agree, tested = join_table(nps, tables[ti], pr, s, 0)
            if best is None or agree > best[1]:
                best = (ti, agree, tested)
        ti, agree, tested = best
        ctl = [join_table(nps, tables[ti], pr, slices[ti][0], k)[0] for k in (1, -1, 2)]
        if a.shift:
            agree, tested = join_table(nps, tables[ti], pr, slices[ti][0], a.shift)
        print(f"  pair {pi:2d} @0x{pr['links_at']:x}/0x{pr['triples_at']:x} codes {len(pr['links']):6d} "
              f"-> table {ti:2d}: neg/pos agree {agree}/{tested}; shift +1/-1/+2 control {ctl}")
        total_agree += agree
        total_tested += tested
        if first is None and agree:
            first = (pr, ti)
    print(f"total neg/pos agree {total_agree}/{total_tested} (shift {a.shift})")
    if first and a.examples:
        pr, ti = first
        s, e = slices[ti]
        print(f"examples (table {ti}, records joined by location code to RDSTM link records):")
        shown = 0
        for k in range(e - s):
            code = tables[ti].get(k)
            if code is None or code not in pr["links"]:
                continue
            dec = decode_record(recs[s + k])
            f = dec["fields"]
            if pr["triples"].get(code) != (u16(f[7]), u16(f[8])):
                continue
            refs = [f"{g[0]}:" + ",".join(f"{r:08x}" for r in g[1]) for g in pr["links"][code]]
            print(f"  ord {k:5d} code {code:5d} type {u16(f[0])} road {text(f[1])!r} "
                  f"name {text(f[3])!r} area {u16(f[5])} neg {u16(f[7])} pos {u16(f[8])} links {' '.join(refs)}")
            shown += 1
            if shown >= a.examples:
                break
    return 0


# --------------------------------------------------------------------------
# self-test (synthetic, no vendor bytes)

def build_record(fields: list[bytes]) -> bytes:
    lens = [len(f) // 2 for f in fields]
    table = bytes(lens) + (b"\x00" if len(lens) % 2 else b"")
    body = table + b"".join(fields)
    size_words = (2 + len(body)) // 2
    return size_words.to_bytes(2, "big") + body


def _selftest() -> int:
    fails = []

    def check(name, cond):
        if not cond:
            fails.append(name)

    f = [b"\x4e\x8f", b"D5A\x00", b"", b"Praha\x00", b"", b"\x00\x32", b"", b"\x1c\x2a",
         b"\x1c\x2c", b"\x00\x01", b"", b"\x00\x07"]
    rec = build_record(f)
    dec = decode_record(rec)
    check("exact framing", dec["ok"])
    check("type code", u16(dec["fields"][0]) == 20111)
    check("string", text(dec["fields"][3]) == "Praha")
    check("negative/positive", (u16(dec["fields"][7]), u16(dec["fields"][8])) == (0x1C2A, 0x1C2C))
    # the length sum is pairing-invariant; the pairing decides which field is which
    le = decode_record(rec, pairing="le")
    check("le pairing moves fields", le["ok"] and le["lens"][0] == 2
          and le["fields"][0] == b"\x4e\x8fD5")
    check("11 fields fails", not decode_record(rec, 11)["ok"])
    check("13 fields fails", not decode_record(rec, 13)["ok"])
    # 0x003f56bc type rules
    check("type0 start", data_start(b"\x00\x05" + b"\x00" * 8) == 2)
    check("type5 start", data_start(b"\xa0\x05" + b"\x00" * 8) == 8)
    check("type7 rejected", data_start(b"\xe0\x05" + b"\x00" * 8) == -1)
    check("bits11-12=2 rejected", data_start(b"\x10\x05" + b"\x00" * 8) == -1)
    t6 = b"\xc0\x05\x01\x02" + b"\x00" * 8
    check("type6 start", data_start(t6) == 2 * (1 + 2 + 2))
    # odd field count pads the length table to whole halfwords
    check("odd n padding", field_offset(rec, 2, 11, 0) == 2 + 2 * 6)
    # index: two runs, BCD codes padded with 0xf
    idx = b""
    for ordinal, code in ((0, "1"), (1, "10"), (2, "1459"), (0, "7")):
        nib = code + "f" * (16 - len(code))
        idx += ordinal.to_bytes(4, "big") + bytes.fromhex(nib)
    blob = b"\xff" * 4 + idx + b"\xff" * 16
    blob += b"\xff" * (PAGE - len(blob))
    blob += b"\x00\x00\x08\x00" + idx  # an upper page is skipped
    blob += b"\xff" * (2 * PAGE - len(blob))
    tabs = parse_index(blob, 0, len(blob))
    check("index runs", len(tabs) == 2 and tabs[0] == {0: 1, 1: 10, 2: 1459} and tabs[1] == {0: 7})
    check("slices", table_slices(tabs) == [(0, 3), (3, 4)])
    # stream split
    plain = rec + build_record([b"\x00\x64"] + [b""] * 11)
    check("split", len(split_records(plain)) == 2)
    # RDSTM link block + triples
    r1 = struct.pack(">HHH", 0, 1201, 1) + struct.pack(">HI", 4, 0x001227FD)
    r1 = struct.pack(">H", len(r1) // 2) + r1[2:]
    r2 = struct.pack(">HHH", 0xFFFF, 1203, 1) + struct.pack(">HII", 8 | 3, 0x00122800, 0x00122801)
    blk = b"\x00" * 0x100 + r1 + r2
    blk += b"\x00" * (0x200 - len(blk))
    blk += struct.pack(">H", 2) + struct.pack(">HHH", 1201, 0, 1203) + struct.pack(">HHH", 1203, 1201, 0)
    blk += b"\x00" * (0x300 - len(blk))
    pairs = rdstm_pairs(blk, 0x100)
    check("rdstm pair", len(pairs) == 1 and pairs[0]["triples"][1203] == (1201, 0))
    check("rdstm links", pairs and pairs[0]["links"][1203] == [(3, [0x00122800, 0x00122801])])
    print(f"selftest: {'OK' if not fails else 'FAIL ' + ', '.join(fails)}")
    return 0 if not fails else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("walk", help="apply the firmware directory rule to every record")
    p.add_argument("lctbl")
    p.add_argument("--fields", type=int, default=NFIELDS)
    p.add_argument("--pairing", choices=("be", "le"), default="be")
    p.set_defaults(func=cmd_walk)
    p = sub.add_parser("index", help="ordinal -> location code runs")
    p.add_argument("lctbl")
    p.add_argument("--min-records", type=int, default=1000)
    p.set_defaults(func=cmd_index)
    p = sub.add_parser("join", help="decoded records vs RDSTM001 (code, neg, pos) triples")
    p.add_argument("lctbl")
    p.add_argument("rdstm")
    p.add_argument("--shift", type=int, default=0)
    p.add_argument("--examples", type=int, default=0)
    p.add_argument("--min-records", type=int, default=1000)
    p.set_defaults(func=cmd_join)
    return ap


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    if a.selftest:
        return _selftest()
    if not getattr(a, "func", None):
        build_parser().print_help()
        return 2
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
