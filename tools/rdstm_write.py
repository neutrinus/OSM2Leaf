#!/usr/bin/env python3
"""Write ``RDSTM001.DAT`` and TMC location records (M5.19).

Today every ``RDSTM001`` byte is copied from the factory card.  The link
references in that file are tied to the factory road graph: a reference
``(group, entry)`` names a 4-byte entry ``(node, link)`` of a MAPAL
section-2 parcel record (EXP-2026-11-20-M4.16e-rdstm-link-groups, C-5139),
and every TMC table places on its own country's nodes (C-5370, C-5400).  A
card whose section 2 is generated therefore needs a file whose references
point at the *generated* nodes.  This module is that writer.  It does not
edit or replace ``tools/rdstm_links.py`` (the M4.16e reader); it uses that
reader and ``tools/tmc_fielddir.py`` only as independent checks.

File model (EU 2011 layout, all words big-endian; *addr* = MAPAL container
address ``(v >> 8) * 0x800 + (v & 0xff) * 0x100``, *blocks* = 0x100 bytes)::

    0x0000  preamble (container header), copied
    0x1000  header: u16 words (0x180), u16 h1, u16 h2, 2 x set rows
    0x1300  set 0 tables, then set 1 tables; per table:
              link chunks (records, last record's size word 0xffff),
              triple block (u16 n, n x (code, negative, positive))
            set 0 group index, set 0 group data,
            set 1 group index, set 1 group data  (= EOF)

Every block is padded with zeros to whole 0x100 blocks and blocks follow
each other without gaps (all 68 table blocks and all 3,165 group data runs of
the factory file, EXP-2026-11-20-M5.19-rdstm-writer).

Re-pointing.  In a *target* model each reference is ``(parcel_key, a, b)``
instead of a ``u32``.  ``assign_groups`` turns targets into group index rows
and refs: set 1 groups are 4 x 4 level-2 parcel boxes in ascending key order
(the factory rule, 3,132/3,132 groups); set 0 groups follow a supplied
parcel -> group table (the level-4 grouping is not a clean box rule: 3 of 33
factory groups hold parcels outside their box).  Inside a group the parcels
are in key order and each parcel's entries in reference walk order (table,
chunk, record, role list, ref); one entry per reference.

TMC location records (the rows the firmware field directory walks,
``fn 0x003f61bc``): ``encode_tmc(fields)`` writes ``u16 size_words``, the
byte length table (field ``i`` length in words, padded to whole halfwords)
and the twelve fields (C-5130–C-5133).  ``l3`` runs the firmware accessor
``0x003f61bc`` and the length getter ``0x003f5d98`` (EU2011 build A
``Navi.exe``) in PySh4 on written records.

Commands::

    rdstm_write.py repack  RDSTM001.DAT [--out FILE]
    rdstm_write.py regroup RDSTM001.DAT [--out FILE]
    rdstm_write.py repoint RDSTM001.DAT MAPAL001 [--tiles B48R058R.DAT] [--seed 1]
    rdstm_write.py l3 IMG256 LCTBL001.DAT [--count 24] [--start 0] [--sample N]
    rdstm_write.py l3 IMG256 -          (24 synthetic Polish rows, no card data)
    rdstm_write.py --selftest

Stdlib only.  Reads vendor files; writes only ``--out``.
"""

from __future__ import annotations

import argparse
import hashlib
import random
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import rdstm_links  # noqa: E402  (reader, used as an independent check)
import tmc_fielddir  # noqa: E402

HEADER_AT = 0x1000
HEADER_WORDS = 0x180
BLOCK = 0x100
ID_MASK = 0x1FFF
END_RECORD = 0xFFFF
MAX_RECORD_WORDS = 0x7FF


class WriteError(ValueError):
    """The model cannot be written in this layout."""


# --------------------------------------------------------------------------
# primitives

def enc_addr(off: int) -> int:
    """Inverse of ``rdstm_links.addr`` for a 0x100-aligned offset."""
    if off % BLOCK:
        raise WriteError("address 0x%x not 0x100-aligned" % off)
    return (off // 0x800) << 8 | (off % 0x800) // BLOCK


def pad_block(b: bytes) -> bytes:
    return b + bytes(-len(b) % BLOCK)


def blocks(b: bytes) -> int:
    return len(b) // BLOCK


def encode_link_record(code: int, roles: list, last: bool) -> bytes:
    """``u16 size|0xffff, u16 code, u16 n, n x (u16 k, (k>>2) x u32 ref)``."""
    body = b""
    for role, refs in roles:
        if not 0 <= role <= 3:
            raise WriteError("role %r" % role)
        if len(refs) > 0x3FFF:
            raise WriteError("too many refs in one role list")
        body += struct.pack(">H", len(refs) << 2 | role)
        body += b"".join(struct.pack(">I", r) for r in refs)
    size = 6 + len(body)
    if size // 2 > MAX_RECORD_WORDS:
        raise WriteError("link record %d is %d words" % (code, size // 2))
    w = END_RECORD if last else size // 2
    return struct.pack(">HHH", w, code, len(roles)) + body


def encode_chunk(records: list) -> bytes:
    out = b""
    for i, (code, roles) in enumerate(records):
        out += encode_link_record(code, roles, i == len(records) - 1)
    return pad_block(out)


def encode_triples(triples: list) -> bytes:
    out = struct.pack(">H", len(triples))
    out += b"".join(struct.pack(">HHH", c, n, p) for c, n, p in triples)
    return pad_block(out)


def encode_group_head(data_addr: int, data_blocks: int, g: dict) -> bytes:
    head = struct.pack(">IHIIH", enc_addr(data_addr), data_blocks, g["kmin"], g["kmax"],
                       len(g["parcels"]))
    head += b"".join(struct.pack(">IH", key, len(ents)) for key, ents in g["parcels"])
    size = 2 + len(head)
    size += -size % 4
    return struct.pack(">H", size // 4) + head + bytes(size - 2 - len(head))


def encode_group_data(g: dict) -> bytes:
    return pad_block(b"".join(struct.pack(">HH", a, b) for _k, ents in g["parcels"]
                              for a, b in ents))


# --------------------------------------------------------------------------
# writer

def write(model: dict) -> bytes:
    """Bytes of an ``RDSTM001.DAT`` for *model* (see module doc)."""
    pre = model["preamble"]
    if len(pre) != HEADER_AT:
        raise WriteError("preamble must be 0x%x bytes" % HEADER_AT)
    words = model.get("words", HEADER_WORDS)
    sets = model["sets"]
    if len(sets) != 2:
        raise WriteError("two sets expected")
    # pass 1: encode every block (contents do not depend on addresses)
    tab_blobs = [[([encode_chunk(c) for c in t["chunks"]], encode_triples(t["triples"]))
                  for t in s["tables"]] for s in sets]
    data_blobs = [[encode_group_data(g) for g in s["groups"]] for s in sets]
    # index size is fixed by the parcel counts; build with dummy addresses first
    idx_sizes = [len(pad_block(struct.pack(">H", len(s["groups"])) + b"".join(
        encode_group_head(0, 0, g) for g in s["groups"]))) for s in sets]
    # pass 2: lay out
    off = HEADER_AT + 2 * words
    tab_addr = []
    for st in tab_blobs:
        rows = []
        for chunks, tri in st:
            la = []
            for c in chunks:
                la.append((off, blocks(c)))
                off += len(c)
            rows.append((la, (off, blocks(tri))))
            off += len(tri)
        tab_addr.append(rows)
    idx_addr, data_addr = [], []
    for si, s in enumerate(sets):
        idx_addr.append(off)
        off += idx_sizes[si]
        da = []
        for blob in data_blobs[si]:
            da.append((off, blocks(blob)))
            off += len(blob)
        data_addr.append(da)
    # header
    hdr = struct.pack(">HHH", words, model.get("h1", 0), model.get("h2", 0))
    for si, s in enumerate(sets):
        hdr += struct.pack(">IHH", enc_addr(idx_addr[si]), idx_sizes[si] // BLOCK, len(s["tables"]))
        for t, (la, (ta, tb)) in zip(s["tables"], tab_addr[si]):
            hdr += struct.pack(">HH", t["code"], len(la))
            hdr += b"".join(struct.pack(">IH", enc_addr(a), b) for a, b in la)
            hdr += struct.pack(">IH", enc_addr(ta), tb)
    if len(hdr) > 2 * words:
        raise WriteError("header needs %d bytes, has %d" % (len(hdr), 2 * words))
    out = bytearray(pre) + hdr + bytes(2 * words - len(hdr))
    for st in tab_blobs:
        for chunks, tri in st:
            for c in chunks:
                out += c
            out += tri
    for si, s in enumerate(sets):
        idx = struct.pack(">H", len(s["groups"]))
        for g, (a, b) in zip(s["groups"], data_addr[si]):
            idx += encode_group_head(a, b, g)
        out += pad_block(idx)
        for blob in data_blobs[si]:
            out += blob
    if len(out) != off:
        raise WriteError("layout mismatch")
    return bytes(out)


# --------------------------------------------------------------------------
# reader -> model (for repack / regroup / repoint)

def read_chunk(d: bytes, off: int) -> list:
    recs = []
    while True:
        w, code, n = struct.unpack_from(">HHH", d, off)
        p = off + 6
        roles = []
        for _ in range(n):
            k = struct.unpack_from(">H", d, p)[0]
            refs = list(struct.unpack_from(">%dI" % (k >> 2), d, p + 2))
            roles.append((k & 3, refs))
            p += 2 + 4 * (k >> 2)
        recs.append((code, roles))
        off = p
        if w == END_RECORD:
            return recs


def read_model(d: bytes) -> dict:
    h = rdstm_links.parse_header(d)
    sets = []
    for s in h["sets"]:
        tables = []
        for t in s["tables"]:
            chunks = [read_chunk(d, a) for a, _b in t["links"]]
            ta = t["triples"][0]
            n = struct.unpack_from(">H", d, ta)[0]
            tri = [struct.unpack_from(">HHH", d, ta + 2 + 6 * i) for i in range(n)]
            tables.append({"code": t["code"], "chunks": chunks, "triples": tri})
        groups = []
        for g in rdstm_links.parse_groups(d, s["index_at"]):
            ents = rdstm_links.group_entries(d, g)
            parcels, e = [], 0
            for key, cnt in g["parcels"]:
                parcels.append((key, [(a, b) for _k, a, b in ents[e:e + cnt]]))
                e += cnt
            groups.append({"kmin": g["kmin"], "kmax": g["kmax"], "parcels": parcels})
        sets.append({"tables": tables, "groups": groups})
    return {"preamble": d[:HEADER_AT], "words": h["words"], "h1": h["h1"], "h2": h["h2"],
            "sets": sets}


def walk_refs(s: dict):
    """Yield (table, chunk, record, role, index, ref) in walk order."""
    for ti, t in enumerate(s["tables"]):
        for ci, c in enumerate(t["chunks"]):
            for ri, (_code, roles) in enumerate(c):
                for li, (_role, refs) in enumerate(roles):
                    for j, ref in enumerate(refs):
                        yield ti, ci, ri, li, j, ref


def to_targets(model: dict) -> dict:
    """Copy of *model* whose refs are ``(parcel_key, a, b)`` and with no groups.

    Returns also ``group_of`` per set: {parcel_key: group number} of the input.
    """
    out = {k: v for k, v in model.items() if k != "sets"}
    out["sets"] = []
    for s in model["sets"]:
        flat = []
        for g in s["groups"]:
            flat.append([(key, a, b) for key, ents in g["parcels"] for a, b in ents])
        group_of = {key: gi for gi, g in enumerate(s["groups"]) for key, _e in g["parcels"]}
        boxes = [(g["kmin"], g["kmax"]) for g in s["groups"]]
        tables = []
        for t in s["tables"]:
            chunks = [[(code, [(role, [flat[r >> 16][r & 0xFFFF] for r in refs])
                               for role, refs in roles]) for code, roles in c]
                      for c in t["chunks"]]
            tables.append({"code": t["code"], "chunks": chunks, "triples": list(t["triples"])})
        out["sets"].append({"tables": tables, "group_of": group_of, "boxes": boxes})
    return out


# --------------------------------------------------------------------------
# group assignment (re-pointing)

def l2_rc(key: int) -> tuple[int, int]:
    w0, w1 = key >> 16, key & 0xFFFF
    chi = ((w0 >> 15) << 8) | (w1 >> 8)
    return ((w0 >> 8) & 0x7F) << 4 | (w0 >> 4) & 0xF, chi << 4 | (w1 >> 4) & 0xF


def l2_key(row: int, col: int, low0: int = 0xF, level: int = 2) -> int:
    """Level-2 parcel code for (row, col); inverse of ``l2_rc``."""
    if not (0 <= row < 0x800 and 0 <= col < 0x2000):
        raise WriteError("parcel row/col out of range")
    w0 = (col >> 12) << 15 | (row >> 4) << 8 | (row & 0xF) << 4 | low0
    w1 = ((col >> 4) & 0xFF) << 8 | (col & 0xF) << 4 | level
    return w0 << 16 | w1


def box4(key: int) -> tuple[int, int]:
    """Set 1 group box: the aligned 4 x 4 level-2 parcels holding *key*."""
    if key & 0xF != 2:
        raise WriteError("set 1 parcel 0x%08x is not level 2" % key)
    r, c = l2_rc(key)
    r0, c0 = r - r % 4, c - c % 4
    low0 = (key >> 16) & 0xF
    return l2_key(r0, c0, low0), l2_key(r0 + 4, c0 + 4, low0)


def code_order(t: dict, order: str = "code") -> list:
    """A table's records in location-code order.

    Entries are numbered in this order, not in file order: the factory stores
    a four-chunk table's code ranges as chunks 0, 2, 1, 3 (tables ``4401`` and
    ``4620`` of set 1), and its entries follow the codes.
    """
    recs = [r for c in t["chunks"] for r in c]
    codes = [code for code, _r in recs]
    if len(set(codes)) != len(codes):
        raise WriteError("table %04x repeats a location code" % t["code"])
    return recs if order == "file" else sorted(recs, key=lambda r: r[0])


def split_chunks(records: list, nchunks: int) -> list:
    """Sorted records -> *nchunks* chunks of equal count (the remainder goes to
    the last chunks) in the factory storage order (0, 1) or (0, 2, 1, 3)."""
    recs = sorted(records, key=lambda r: r[0])
    base, extra = divmod(len(recs), nchunks)
    sizes = [base + (i >= nchunks - extra) for i in range(nchunks)]
    parts, p = [], 0
    for n in sizes:
        parts.append(recs[p:p + n])
        p += n
    order = {1: [0], 2: [0, 1], 4: [0, 2, 1, 3]}.get(nchunks)
    if order is None:
        raise WriteError("chunk count %d not seen on the factory card" % nchunks)
    return [parts[i] for i in order]


CHUNK_LIMIT = 0x80000  # HYPOTHESIS: fits all 28 factory tables (506,394 B -> 1, 575,240 B -> 2)


def default_chunks(records: list) -> int:
    """Smallest of 1, 2, 4 chunks whose mean record bytes stay <= CHUNK_LIMIT."""
    total = sum(6 + sum(2 + 4 * len(refs) for _role, refs in roles) for _c, roles in records)
    for m in (1, 2, 4):
        if total <= m * CHUNK_LIMIT:
            return m
    raise WriteError("table of %d bytes needs more than 4 chunks" % total)


def build_table(code: int, records: list, triples: dict, nchunks: int | None = None) -> dict:
    """A table from its location records and ``{code: (negative, positive)}``.

    Triples follow the chunk storage order (the factory order, 28/28 tables).
    """
    if set(triples) != {c for c, _r in records}:
        raise WriteError("triples and records name different codes")
    chunks = split_chunks(records, nchunks or default_chunks(records))
    tri = [(c, *triples[c]) for ch in chunks for c, _r in ch]
    return {"code": code, "chunks": chunks, "triples": tri}


def rebuild_tables(model: dict) -> dict:
    """Copy of *model* whose tables are rebuilt from records + triples only."""
    out = dict(model)
    out["sets"] = []
    for s in model["sets"]:
        tables = []
        for t in s["tables"]:
            recs = [r for c in t["chunks"] for r in c]
            tables.append(build_table(t["code"], recs, {c: (n, p) for c, n, p in t["triples"]}))
        out["sets"].append({**s, "tables": tables})
    return out


def assign_groups(tset: dict, rule: str, order: str = "code") -> dict:
    """Groups + u32 refs for one target set; *rule* ``box4`` or ``given``."""
    by_group: dict = {}  # group id -> {parcel: [entries]} in walk order
    for t in tset["tables"]:
        for _code, roles in code_order(t, order):
            if True:
                for _role, refs in roles:
                    for key, a, b in refs:
                        gid = box4(key) if rule == "box4" else tset["group_of"][key]
                        by_group.setdefault(gid, {}).setdefault(key, []).append((a, b))
    if rule == "box4":
        gids = sorted(by_group)
        boxes = {g: g for g in gids}
    else:
        gids = sorted(by_group)
        boxes = {g: tset["boxes"][g] for g in gids}
    groups, where = [], {}
    for gn, gid in enumerate(gids):
        parcels = sorted(by_group[gid].items())
        e = 0
        for key, ents in parcels:
            where[(gn, key)] = e
            e += len(ents)
        if e > 0x10000:
            raise WriteError("group %d has %d entries" % (gn, e))
        groups.append({"kmin": boxes[gid][0], "kmax": boxes[gid][1], "parcels": parcels})
    gnum = {gid: gn for gn, gid in enumerate(gids)}
    tables = []
    for t in tset["tables"]:
        new_roles = {}
        for code, roles in code_order(t, order):
            if True:
                rl = []
                for role, refs in roles:
                    out = []
                    for key, _a, _b in refs:
                        gid = box4(key) if rule == "box4" else tset["group_of"][key]
                        gn = gnum[gid]
                        out.append(gn << 16 | where[(gn, key)])
                        where[(gn, key)] += 1
                    rl.append((role, out))
                new_roles[code] = rl
        chunks = [[(code, new_roles[code]) for code, _r in c] for c in t["chunks"]]
        tables.append({"code": t["code"], "chunks": chunks, "triples": t["triples"]})
    return {"tables": tables, "groups": groups}


def from_targets(tmodel: dict, rules=("given", "box4"), order: str = "code") -> dict:
    out = {k: v for k, v in tmodel.items() if k != "sets"}
    out["sets"] = [assign_groups(s, r, order) for s, r in zip(tmodel["sets"], rules)]
    return out


def remap_targets(tmodel: dict, set_index: int, remap) -> int:
    """Apply ``remap(key, a, b) -> (key, a, b) | None`` to one set; count changes."""
    n = 0
    s = tmodel["sets"][set_index]
    for t in s["tables"]:
        for c in t["chunks"]:
            for i, (code, roles) in enumerate(c):
                new_roles = []
                for role, refs in roles:
                    new = []
                    for ref in refs:
                        r = remap(*ref)
                        if r is not None and r != ref:
                            n += 1
                            ref = r
                        new.append(ref)
                    new_roles.append((role, new))
                c[i] = (code, new_roles)
    return n


# --------------------------------------------------------------------------
# TMC location record (rows walked by fn 0x003f61bc)

def encode_tmc(fields: list[bytes]) -> bytes:
    """``u16 size_words`` (type 0), length bytes, fields (each whole words)."""
    if len(fields) != tmc_fielddir.NFIELDS:
        raise WriteError("%d fields" % len(fields))
    lens = []
    for f in fields:
        if len(f) % 2 or len(f) // 2 > 0xFF:
            raise WriteError("field of %d bytes" % len(f))
        lens.append(len(f) // 2)
    body = bytes(lens) + bytes(len(lens) % 2) + b"".join(fields)
    words = 1 + len(body) // 2
    if words > MAX_RECORD_WORDS:
        raise WriteError("record of %d words" % words)
    return struct.pack(">H", words) + body


# --------------------------------------------------------------------------
# L3: fn 0x003f61bc / 0x003f5d98 on written records (EU2011 build A Navi.exe)

IMAGE_START = 0x200200
FN_FIELD = 0x003F61BC
FN_LEN = 0x003F5D98
HANDLE_TABLE = 0x00D53500   # BSS sec1; key at +12, block pointer at +16 (fn 0x003f51e0)
SLOT_TASKID = 0x0055D8F0    # IAT OSMDLL #21 taskIdSelf, called first by 0x003f51e0
STUB_VA = 0x0F000000
BLOCK_VA = 0x0F100000
REC_VA = 0x0F200000
STK_VA = 0x0F300000
STK_SIZE = 0x10000
HANDLE = 0x5A5A0001
HDR_WORDS = 8               # block -> hdr = block + 2*u16[block+2]


def l3_engine(image: bytes, nfields: int = tmc_fielddir.NFIELDS):
    import cerom
    from l3_harness.engine import PySh4, StubReturn

    rom = cerom.CERom(image, IMAGE_START)
    mod = rom.module("Navi.exe")
    eng = PySh4(endian="little")
    for sec in rom.o32(mod):
        name = "sec@%08x" % sec["realaddr"]
        if sec["flags"] & cerom.IMAGE_SCN_COMPRESSED:
            eng.map(name, sec["realaddr"], bytearray(sec["vsize"]), "rw")
            continue
        off = rom.va2file(sec["dataptr"])
        blob = bytearray(image[off:off + sec["psize"]])
        blob += bytearray(max(0, sec["vsize"] - len(blob)))
        eng.map(name, sec["realaddr"], blob, "rwx")
    eng.map("stub", STUB_VA, bytearray(0x100), "rx")
    eng.map("tmc_block", BLOCK_VA, tmc_block(nfields), "rw")
    eng.map("record", REC_VA, bytearray(0x1000), "rw")
    eng.map("stack", STK_VA, bytearray(STK_SIZE), "rw")
    eng.write_mem(SLOT_TASKID, struct.pack("<I", STUB_VA))
    eng.write_mem(HANDLE_TABLE + 12, struct.pack("<II", HANDLE, BLOCK_VA))
    eng.on_exec(STUB_VA, lambda e, va: StubReturn(1))
    return eng


def tmc_block(nfields: int, desc_words: int = 16, desc_size: int = 16) -> bytearray:
    """The handle block ``fn 0x003f51e0`` returns, as far as the walk reads it.

    ``hdr = block + 2 * u16[block + 2]``; ``u16[hdr + 26]`` = field count
    (``0x003f57a8``); ``u16[hdr + 24]`` = word offset of the first field
    descriptor, each descriptor's ``u16[+0]`` = word offset of the next and
    ``u16[+12]`` = its field index, which ``0x003f56bc`` requires to equal the
    requested index.  Native (little-endian) halfwords: a RAM structure.
    """
    block = bytearray(0x400)
    hdr = 2 * HDR_WORDS
    struct.pack_into("<H", block, 2, HDR_WORDS)
    struct.pack_into("<HH", block, hdr + 24, desc_words, nfields)
    for i in range(max(nfields, tmc_fielddir.NFIELDS) + 1):
        at = hdr + 2 * desc_words + desc_size * i
        struct.pack_into("<H", block, at, desc_words + desc_size // 2 * (i + 1))
        struct.pack_into("<H", block, at + 12, i)
    return block


def swap16(b: bytes) -> bytes:
    """Card record (big-endian halfwords) -> the native halfwords the walk reads.

    ``0x003f56bc`` and ``0x003f5d98`` read ``mov.w`` (little-endian) and take
    field ``2k`` from the *high* byte, so the card order is seen only after a
    16-bit swap (ASSUMPTION: the page loader that swaps is not located).
    """
    if len(b) % 2:
        raise WriteError("odd record length")
    return bytes(x for i in range(0, len(b), 2) for x in (b[i + 1], b[i]))


def l3_record(eng, rec: bytes, nfields: int = tmc_fielddir.NFIELDS, swap: bool = True) -> list:
    """[(pointer offset or None, length)] per field from the firmware."""
    ram = swap16(rec) if swap else rec
    eng.write_mem(REC_VA, ram + bytes(0x1000 - len(ram)))
    out = []
    for i in range(nfields):
        eng.set_regs(r15=STK_VA + STK_SIZE // 2)
        p = eng.call(FN_FIELD, [HANDLE, REC_VA, i])
        eng.set_regs(r15=STK_VA + STK_SIZE // 2)
        n = eng.call(FN_LEN, [HANDLE, REC_VA, i])
        out.append((None if p in (0, 0xFFFFFFFF) else p - REC_VA, n))
    return out


def expected_walk(rec: bytes, nfields: int = tmc_fielddir.NFIELDS) -> list:
    st = tmc_fielddir.data_start(rec)
    return [(tmc_fielddir.field_offset(rec, st, nfields, i), tmc_fielddir.field_len(rec, st, i))
            for i in range(nfields)]


# --------------------------------------------------------------------------
# commands

def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def first_diff(a: bytes, b: bytes):
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            return i
    return None if len(a) == len(b) else min(len(a), len(b))


def report(name: str, ref: bytes, out: bytes, path) -> int:
    same = ref == out
    print("%s: in %d B sha %s" % (name, len(ref), sha(ref)[:16]))
    print("%s: out %d B sha %s identical %s" % (name, len(out), sha(out)[:16], same))
    if not same:
        print("%s: first difference at 0x%x" % (name, first_diff(ref, out)))
    if path:
        Path(path).write_bytes(out)
    return 0 if same else 1


def cmd_repack(a) -> int:
    d = Path(a.rdstm).read_bytes()
    m = read_model(d)
    for si, s in enumerate(m["sets"]):
        nrec = sum(len(c) for t in s["tables"] for c in t["chunks"])
        nref = sum(1 for _ in walk_refs(s))
        print("set %d: tables %d records %d refs %d groups %d"
              % (si, len(s["tables"]), nrec, nref, len(s["groups"])))
    return report("repack", d, write(m), a.out)


def cmd_regroup(a) -> int:
    d = Path(a.rdstm).read_bytes()
    t = rebuild_tables(to_targets(read_model(d)))
    out = write(from_targets(t, order=a.entry_order))
    rc = report("regroup", d, out, a.out)
    # negative control: entries numbered in file (chunk) order, not code order
    m = read_model(d)
    shuffled = 0
    for s in m["sets"]:
        for t_ in s["tables"]:
            shuffled += [c for ch in t_["chunks"] for c, _r in ch] != [c for c, _r in code_order(t_)]
    print("regroup: tables whose file order != code order (where a file-order "
          "numbering would differ): %d" % shuffled)
    return rc


def cmd_repoint(a) -> int:
    """Renumber nodes/links of the set-1 parcels in --tiles (a stand-in for a
    generated section 2), re-point with the writer, and resolve both files."""
    mapal = Path(a.mapal)
    d = Path(a.rdstm).read_bytes()
    paths = [mapal / n for n in a.tiles.split(",")]
    sec2 = rdstm_links.load_sec2(paths, 2)
    rnd = random.Random(a.seed)
    perm = {}
    gen = {}
    for key, rec in sec2.items():
        nn = len(rec["nodes"])
        pn = list(range(nn))
        rnd.shuffle(pn)
        lids = sorted(rec["ends"])
        pl = dict(zip(lids, rnd.sample(lids, len(lids))))
        perm[key] = (pn, pl)
        ends = {}
        for lid, nodes in rec["ends"].items():
            ends[pl[lid]] = {pn[n]: w for n, w in nodes.items()}
        gen[key] = {"nodes": [None] * nn, "ends": ends}
        for i, xy in enumerate(rec["nodes"]):
            gen[key]["nodes"][pn[i]] = xy

    def remap(key, a_, b_):
        if key not in perm:
            return None
        pn, pl = perm[key]
        n, lk = a_ & ID_MASK, b_ & ID_MASK
        if n >= len(pn) or lk not in pl:
            return None
        return key, (a_ & ~ID_MASK) | pn[n], (b_ & ~ID_MASK) | pl[lk]

    tm = to_targets(read_model(d))
    changed = remap_targets(tm, 1, remap)
    out = write(from_targets(tm))

    def score(blob: bytes, recs: dict) -> tuple[int, int]:
        h = rdstm_links.parse_header(blob)
        s = h["sets"][1]
        groups = rdstm_links.parse_groups(blob, s["index_at"])
        tried = hit = 0
        for g in groups:
            for key, a_, b_ in rdstm_links.group_entries(blob, g):
                if key in recs:
                    tried += 1
                    hit += rdstm_links.resolve(recs[key], a_, b_) is not None
        return hit, tried

    print("repoint: tiles %s parcels %d refs re-pointed %d" % (a.tiles, len(sec2), changed))
    for label, blob, recs in (("factory file vs factory sec2", d, sec2),
                              ("factory file vs generated sec2 (copy)", d, gen),
                              ("written file vs generated sec2", out, gen),
                              ("written file vs factory sec2", out, sec2)):
        hit, tried = score(blob, recs)
        print("  %-40s %d / %d" % (label, hit, tried))
    # every TMC record keeps its refs' node coordinates under the renumbering
    same = moved = 0
    fm, om = read_model(d), read_model(out)
    for (fs, os_) in ((fm["sets"][1], om["sets"][1]),):
        fflat = [[(k, a_, b_) for k, ents in g["parcels"] for a_, b_ in ents] for g in fs["groups"]]
        oflat = [[(k, a_, b_) for k, ents in g["parcels"] for a_, b_ in ents] for g in os_["groups"]]
        for (_t, _c, _r, _l, _j, r1), (_t2, _c2, _r2, _l2, _j2, r2) in zip(walk_refs(fs), walk_refs(os_)):
            k1, a1, _b1 = fflat[r1 >> 16][r1 & 0xFFFF]
            k2, a2, _b2 = oflat[r2 >> 16][r2 & 0xFFFF]
            if k1 not in sec2 or k1 != k2:
                continue
            n1, n2 = a1 & ID_MASK, a2 & ID_MASK
            if n1 < len(sec2[k1]["nodes"]) and n2 < len(gen[k2]["nodes"]):
                if sec2[k1]["nodes"][n1] == gen[k2]["nodes"][n2]:
                    same += 1
                else:
                    moved += 1
    print("  refs whose node (x, y) is kept: %d, changed: %d" % (same, moved))
    if a.out:
        Path(a.out).write_bytes(out)
    return 0


# Synthetic Polish rows (public place names along the A2/A4, no vendor bytes):
# (type, road number, road name, name, second name, exit number).
PL_ROWS = (
    (20111, "A2", "Autostrada Wolnosci", "Swiecko", "", "1"),
    (20111, "A2", "Autostrada Wolnosci", "Rzepin", "", "10"),
    (20111, "A2", "Autostrada Wolnosci", "Torzym", "", "21"),
    (20111, "A2", "Autostrada Wolnosci", "Jordanowo", "", "30"),
    (20111, "A2", "Autostrada Wolnosci", "Nowy Tomysl", "", "47"),
    (20111, "A2", "Autostrada Wolnosci", "Poznan-Komorniki", "", "79"),
    (20111, "A2", "Autostrada Wolnosci", "Poznan-Krzesiny", "", "106"),
    (20111, "A2", "Autostrada Wolnosci", "Wrzesnia", "", "137"),
    (20111, "A2", "Autostrada Wolnosci", "Konin", "", "181"),
    (20111, "A2", "Autostrada Wolnosci", "Kolo", "", "208"),
    (20111, "A2", "Autostrada Wolnosci", "Strykow", "Lodz", "283"),
    (20111, "A2", "Autostrada Wolnosci", "Warszawa-Konotopa", "", "462"),
    (20111, "A4", "", "Jedrzychowice", "", "1"),
    (20111, "A4", "", "Zgorzelec", "", "3"),
    (20111, "A4", "", "Legnica", "", "65"),
    (20111, "A4", "", "Wroclaw-Bielany", "", "150"),
    (20111, "A4", "", "Opole", "", "230"),
    (20111, "A4", "", "Gliwice-Sosnica", "", "290"),
    (20111, "A4", "", "Katowice", "", "330"),
    (20111, "A4", "", "Krakow-Balice", "", "400"),
    (20111, "A4", "", "Tarnow", "", "468"),
    (20111, "A4", "", "Rzeszow-Wschod", "", "560"),
    (20111, "A4", "", "Jaroslaw", "", "600"),
    (20111, "A4", "", "Korczowa", "", "670"),
)


def text_field(t: str) -> bytes:
    b = t.encode("cp1252")
    return b + bytes(len(b) % 2)


def pl_fields(i: int, row: tuple) -> list[bytes]:
    typ, rno, rname, name, second, exitno = row
    code = 100 + i
    neg = code - 1 if i else 0
    pos = code + 1 if i + 1 < len(PL_ROWS) else 0
    return [struct.pack(">H", typ), text_field(rno), text_field(rname), text_field(name),
            text_field(second), struct.pack(">H", 1), struct.pack(">H", 2),
            struct.pack(">H", neg), struct.pack(">H", pos), struct.pack(">H", 0),
            text_field(exitno), struct.pack(">H", 0)]


def cmd_l3(a) -> int:
    image = Path(a.image).read_bytes()
    eng = l3_engine(image)
    if a.lctbl == "-":
        ok = 0
        for i, row in enumerate(PL_ROWS):
            fields = pl_fields(i, row)
            w = encode_tmc(fields)
            got = l3_record(eng, w)
            vals = [w[o:o + 2 * n] for o, n in got] if all(o is not None for o, _ in got) else None
            match = vals == fields
            ok += match
            print("pl row %2d: %-20s %3d B firmware fields == writer input %s"
                  % (i, row[3], len(w), match))
        print("l3 synthetic PL: rows %d firmware fields == writer input %d" % (len(PL_ROWS), ok))
        return 0 if ok == len(PL_ROWS) else 1
    lctbl = Path(a.lctbl).read_bytes()
    recs = tmc_fielddir.load_records(lctbl)
    print("image sha %s; LCTBL sha %s; records %d" % (sha(image)[:16], sha(lctbl)[:16], len(recs)))
    ok = exact = 0
    if a.sample:
        picks = sorted(random.Random(a.seed).sample(range(len(recs)), a.sample))
    else:
        picks = list(range(a.start, a.start + a.count))
    chosen = [recs[i] for i in picks]
    for idx, rec in enumerate(chosen):
        dec = tmc_fielddir.decode_record(rec)
        written = encode_tmc(dec["fields"])
        exact += written == rec
        exp = expected_walk(written)
        got = l3_record(eng, written)
        values = [written[o:o + 2 * n] for o, n in exp]
        match = got == exp and values == dec["fields"]
        ok += match
        if idx < a.show or not match:
            f0 = dec["fields"][0]
            print("row %d: size %d type %s name %r fw==expected %s"
                  % (picks[idx], len(written), f0.hex(),
                     tmc_fielddir.text(dec["fields"][3]), match))
            if not match:
                print("   fw  %s\n   exp %s" % (got, exp))
    print("l3: rows %d written==factory %d firmware walk == expected (12 fields, offset+length) %d"
          % (len(chosen), exact, ok))
    # negative controls
    bad = bytearray(encode_tmc(tmc_fielddir.decode_record(chosen[0])["fields"]))
    bad[0] |= 0xE0  # type 7: rejected by 0x003f56bc
    got = l3_record(eng, bytes(bad))
    print("control type 7: fields returned %d / 12" % sum(p is not None for p, _ in got))
    eng13 = l3_engine(image, nfields=13)
    raw = noswap = 0
    for rec in chosen:
        w = encode_tmc(tmc_fielddir.decode_record(rec)["fields"])
        raw += l3_record(eng13, w) == expected_walk(w)
        noswap += l3_record(eng, w, swap=False) == expected_walk(w)
    print("control block field count 13: rows walked as expected %d / %d" % (raw, len(chosen)))
    print("control card byte order without the 16-bit swap: rows walked as expected %d / %d"
          % (noswap, len(chosen)))
    return 0 if ok == len(chosen) else 1


# --------------------------------------------------------------------------
# self-test (synthetic, no vendor bytes)

def _synthetic_targets(seed: int = 7) -> dict:
    rnd = random.Random(seed)
    keys1 = [l2_key(r, c) for r in range(330, 340) for c in range(7260, 7270)]
    keys0 = [0x940FC604, 0x950FC504, 0x980FC804]
    sets = []
    for si, keys in enumerate((keys0, keys1)):
        tables = []
        for code in (0x3219, 0x4401):
            chunks = []
            for _ in range(2 if code == 0x4401 else 1):
                recs = []
                for loc in range(rnd.randrange(3, 7)):
                    roles = []
                    for role in range(rnd.randrange(1, 3)):
                        roles.append((role, [(rnd.choice(keys), rnd.randrange(1, 40) | 0x4000,
                                              rnd.randrange(1, 60) | 0x2000)
                                             for _ in range(rnd.randrange(0, 5))]))
                    recs.append((1000 * si + 10 * len(chunks) + loc + (code & 0xF), roles))
                chunks.append(recs)
            tri = [(code_, code_ - 1, code_ + 1) for c in chunks for code_, _r in c]
            tables.append({"code": code, "chunks": chunks, "triples": tri})
        group_of = {k: i % 2 for i, k in enumerate(keys0)} if si == 0 else {}
        boxes = [(0x940FC404, 0x980FC804), (0x980FC804, 0x9C0FCC04)]
        sets.append({"tables": tables, "group_of": group_of, "boxes": boxes})
    pre = bytes(0x200) + b"\xff" * 0x10 + bytes(HEADER_AT - 0x210)
    return {"preamble": pre, "words": HEADER_WORDS, "h1": 3, "h2": 122, "sets": sets}


def _selftest() -> int:
    fails = []
    done = []

    def check(name, cond, detail=""):
        print(("PASS " if cond else "FAIL ") + name + ("" if cond else " " + str(detail)))
        done.append(name)
        if not cond:
            fails.append(name)

    # 1 address codec
    check("enc_addr inverse", all(rdstm_links.addr(enc_addr(o)) == o
                                  for o in (0x1300, 0xcda000, 0xe78500, 0x1641200)))
    # 2 level-2 key codec against the M4.16e coordinate rule
    k = 0x94DFC622
    check("l2_key inverse", l2_key(*l2_rc(k), low0=0xF) == k)
    # 3 set-1 box rule on the factory example (group 0: 94cfc602..950fc642)
    check("box4 example", box4(0x94DFC622) == (0x94CFC602, 0x950FC642), [hex(x) for x in box4(k)])
    tm = _synthetic_targets()
    model = from_targets(tm)
    blob = write(model)
    # 4 header parses with the M4.16e reader
    h = rdstm_links.parse_header(blob)
    check("header words/h1/h2", (h["words"], h["h1"], h["h2"]) == (HEADER_WORDS, 3, 122))
    # 5 link/triple pairs walk with the M4.16b block walker
    pairs = tmc_fielddir.rdstm_pairs(blob)
    check("rdstm_pairs walk", len(pairs) == 4 and pairs[0]["links_at"] == 0x1300, len(pairs))
    # 6 header rows equal the walked pairs
    rows = [t["links"][0][0] for s in h["sets"] for t in s["tables"]]
    check("header rows == walk", rows == [p["links_at"] for p in pairs])
    # 7 every ref resolves to its target through the reader
    okn = tot = 0
    for si, (s, ts) in enumerate(zip(model["sets"], tm["sets"])):
        groups = rdstm_links.parse_groups(blob, h["sets"][si]["index_at"])
        ents = [rdstm_links.group_entries(blob, g) for g in groups]
        for (_t, _c, _r, _l, _j, ref), (*_x, tgt) in zip(walk_refs(s), walk_refs(ts)):
            tot += 1
            okn += ents[ref >> 16][ref & 0xFFFF] == tgt
    check("refs resolve to targets", okn == tot and tot > 20, (okn, tot))
    # 8 one entry per reference, every entry referenced
    n_ent = sum(len(e) for s in model["sets"] for g in s["groups"] for _k, e in g["parcels"])
    check("entries == refs", n_ent == tot, (n_ent, tot))
    # 9 repack: read_model(write(m)) writes the same bytes
    check("repack round trip", write(read_model(blob)) == blob)
    # 10 regroup: targets of the written file regroup to the same bytes
    check("regroup round trip", write(from_targets(to_targets(read_model(blob)))) == blob)
    # 11 re-point: a node renumbering is carried into the refs
    tm2 = _synthetic_targets()
    n = remap_targets(tm2, 1, lambda key, a_, b_: (key, (a_ & ~ID_MASK) | (a_ & ID_MASK) + 100, b_))
    m2 = from_targets(tm2)
    blob2 = write(m2)
    g2 = rdstm_links.parse_groups(blob2, rdstm_links.parse_header(blob2)["sets"][1]["index_at"])
    nodes = {a_ & ID_MASK for g in g2 for _k, a_, _b in rdstm_links.group_entries(blob2, g)}
    check("remap carried", n > 0 and min(nodes) >= 101, (n, min(nodes) if nodes else None))
    # 12 negative: a copied file keeps the old node numbers
    g1 = rdstm_links.parse_groups(blob, h["sets"][1]["index_at"])
    old = {a_ & ID_MASK for g in g1 for _k, a_, _b in rdstm_links.group_entries(blob, g)}
    check("copy keeps old nodes", max(old) < 101)
    # 13 TMC record encoder vs the M4.16b decoder
    fields = [b"\x4e\x63", b"D5", b"", b"Plzen\x00", b"", b"\x00\x01", b"\x00\x02",
              b"\x04\xb3", b"\x04\xb5", b"\x00\x00", b"20", b"\x00\x00"]
    rec = encode_tmc(fields)
    dec = tmc_fielddir.decode_record(rec)
    check("tmc encode/decode", dec["ok"] and dec["fields"] == fields, dec)
    # 14 TMC encoder equals the M4.16b fixture builder
    check("tmc == build_record", rec == tmc_fielddir.build_record(fields))
    # 15 bad inputs raise
    try:
        encode_tmc([b"x"] + fields[1:])
        check("odd field rejected", False)
    except WriteError:
        check("odd field rejected", True)
    try:
        encode_link_record(1, [(0, [0] * 1100)], False)
        check("oversize record rejected", False)
    except WriteError:
        check("oversize record rejected", True)
    # 17 synthetic Polish rows decode back to the writer input
    check("PL rows decode", all(tmc_fielddir.decode_record(encode_tmc(pl_fields(i, r)))["fields"]
                                == pl_fields(i, r) for i, r in enumerate(PL_ROWS)))
    # 18 table rebuild: chunk split and storage order 0, 2, 1, 3
    recs = [(c, [(0, [])]) for c in range(400, 0, -1)]
    ch = split_chunks(recs, 4)
    check("split_chunks order", [c[0][0] for c in ch] == [1, 201, 101, 301]
          and [len(c) for c in ch] == [100] * 4, [c[0][0] for c in ch])
    # 19 set-1 entries are numbered in code order, not file order
    tm3 = _synthetic_targets()
    t0 = tm3["sets"][1]["tables"][1]
    t0["chunks"] = t0["chunks"][::-1]
    a1 = write(from_targets(tm3))
    tm3["sets"][1]["tables"][1]["chunks"] = t0["chunks"][::-1]
    check("entry numbering ignores chunk order",
          [g["parcels"] for g in from_targets(tm3)["sets"][1]["groups"]]
          == [g["parcels"] for g in read_model(a1)["sets"][1]["groups"]])
    # 20 the L3 handle block carries the descriptor chain the walk follows
    blk = tmc_block(12)
    hdr = 2 * HDR_WORDS
    at = hdr + 2 * struct.unpack_from("<H", blk, hdr + 24)[0]
    idx = []
    for _ in range(12):
        idx.append(struct.unpack_from("<H", blk, at + 12)[0])
        at = hdr + 2 * struct.unpack_from("<H", blk, at)[0]
    check("tmc_block chain", idx == list(range(12)) and swap16(b"\x00\x0d") == b"\x0d\x00")
    print("selftest: %s (%d checks)" % ("OK" if not fails else "FAIL", len(done)))
    return 0 if not fails else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("repack", help="read the model and write it back")
    s.add_argument("rdstm")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_repack)
    s = sub.add_parser("regroup", help="refs -> targets -> groups re-assigned by the writer")
    s.add_argument("rdstm")
    s.add_argument("--out")
    s.add_argument("--entry-order", choices=("code", "file"), default="code",
                   help="number entries in location-code order (factory) or file order (control)")
    s.set_defaults(fn=cmd_regroup)
    s = sub.add_parser("repoint", help="renumbered section 2: copy vs re-pointed file")
    s.add_argument("rdstm")
    s.add_argument("mapal")
    s.add_argument("--tiles", default="B48R058R.DAT")
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--out")
    s.set_defaults(fn=cmd_repoint)
    s = sub.add_parser("l3", help="firmware field walk on written TMC records")
    s.add_argument("image")
    s.add_argument("lctbl")
    s.add_argument("--count", type=int, default=24)
    s.add_argument("--start", type=int, default=0)
    s.add_argument("--show", type=int, default=24)
    s.add_argument("--sample", type=int, default=0, help="random rows instead of a run")
    s.add_argument("--seed", type=int, default=1)
    s.set_defaults(fn=cmd_l3)
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    if a.selftest:
        return _selftest()
    if not getattr(a, "fn", None):
        build_parser().print_help()
        return 2
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
