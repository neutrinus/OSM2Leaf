#!/usr/bin/env python3
"""Structural census of a REFER001 ``POINTnnn.DAT`` and the fine POI position (M4.27).

A decoded POINT ``.DAT`` is not "name pages plus an undecoded rest".  Every
byte is reached from the 0x800 directory through descriptor records, and each
structure has a grammar this tool walks and checks:

  class            reached from        grammar
  ---------------  ------------------  ------------------------------------------
  header           file start          0x000..0x800 (maker strings, ``ff`` fill)
  directory        0x800               299 cells ``u32 block address, u16 blocks``
  descriptor       directory cells     records naming every structure below
  name-trie        cells 0x824, 0xe84, 12-byte entries ``u32 off_w, u16 size_w,
                   0xe8a, 0xe90        u16 0, u8 char, u24 count``; a child node
                                       is ``size_w`` words at ``off_w``; with
                                       ``size_w = 0`` the offset is a word offset
                                       into the trie's index chain
  index-chain      trie descriptors    ``4e20 0000``, n x ``u32 comp_w``, n zlib
                                       streams of fixed records (12 or 9 words)
  spatial-tree     cell 0x85a          16-byte entries ``0008, u32 ptr, u16
                                       size_w, u16 kx, u16 ky, u32 fine``; three
                                       inner levels keyed by the packed cell id
                                       (an optional fourth by category code),
                                       leaves = POI ordinal + fine position
  phone-btree      cell 0x82a          0x1000-byte nodes of 16-byte entries
                                       ``u32 child_w, u32 POI id, 8-byte BCD key``
  page-chain       cells 0x82a, 0xeba  the 1000/400/2000 chains (M5.26, M4.47)
  chain-table      cells 0x82a, 0xeba  their tables
  fill             -                   zero or ``ff`` bytes between structures

``census`` prints the byte count of every class per file and the bytes no
grammar reached (``unaccounted``).  ``joins`` checks the cross references: a
spatial leaf against the name record it points to, and an index record against
the key bytes of its name record.  ``refs`` checks the fine position model
against reference coordinates:

  u(v, fine) = (v & ~15) + 4 * (v & 3) + fine / 512      # packed units
  lat = (u(A.x, rec[8..9])           - 32768) / 192
  lon = (u(A.y, rec[6..7] & 0x7ff)   - 52736) / 128

(the low nibble of a copy-A word is ``11xx``: two marker bits and a 4-unit
sub-cell index, not a 1-unit coordinate).

Usage:
  python3 tools/point_census.py extract --card-image CARD OUTDIR      # never commit
  python3 tools/point_census.py census DIR [--json OUT]
  python3 tools/point_census.py joins DIR [--files POINT010 ...]
  python3 tools/point_census.py refs --us DIR --eu DIR --refs TSV
  python3 tools/point_census.py position DIR POINTnnn --stream OFF --record N
  python3 tools/point_census.py --selftest

DIR holds ``POINTnnn.DAT.cmp``/``.ind`` pairs (any letter case) copied from a
card.  Read-only; no vendor bytes are written anywhere.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import zlib
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cmpind  # noqa: E402
import coord  # noqa: E402
import point_pair_regen as regen  # noqa: E402

CELL_NAME_TRIE = 0x824
CELL_DICT = 0x82A
CELL_SPATIAL = 0x85A
CELL_CATEGORY = 0xE84
CELL_SUBCATEGORY = 0xE8A
CELL_AREA_TRIE = 0xE90
CELL_ADM = 0xEBA
KNOWN_CELLS = (CELL_NAME_TRIE, CELL_DICT, CELL_SPATIAL, CELL_CATEGORY,
               CELL_SUBCATEGORY, CELL_AREA_TRIE, CELL_ADM)

FLAG_SPATIAL = 0x8000
INDEX_RECORD_WORDS = {0x4C40: 12, 0x4D40: 9}     # trie flags -> index record size
INDEX_MAGIC = b"\x4e\x20\x00\x00"                # 20000 records per stream
INDEX_PER_STREAM = 20000
TRIE_ENTRY = struct.Struct(">IHHBBH")
SPATIAL_ENTRY = struct.Struct(">HIHHHI")
CELL_DEPTH = 3                                   # spatial levels keyed by position
KEY_MASK = (0x7F, 0x0F, 0x00)                    # low bits that are zero at each level
PHONE_NODE = 0x1000
EMPTY = 0xFFFFFFFF

LAT_ORIGIN, LAT_SCALE = 32768, 192
LON_ORIGIN, LON_SCALE = 52736, 128               # the tile origin (not 52742)
LEGACY_LON_ORIGIN = 52742
FINE_PER_UNIT = coord.FINE_PER_UNIT


class CensusError(ValueError):
    pass


# ---------------------------------------------------------------------------
# fine position
#
# The formula lives in ``coord`` (M4.61: one source, ``coord.decode_point_id`` /
# ``coord.encode_point_id``); these wrappers keep the record-level API used by
# the L3 harnesses and ``point_move_poi``.


def packed_units(word: int, fine: int) -> float:
    """Packed units of a copy-A word plus its 11-bit fine field."""
    return coord.packed_units(word, fine)


def fine_fields(rec: bytes) -> tuple[int, int, int, int]:
    """``(A.x, A.y, fine_lon, fine_lat)`` of a name record."""
    ax, ay, v6, v8 = struct.unpack_from(">4H", rec, 2)
    return ax, ay, v6 & 0x7FF, v8 & 0x7FF      # the firmware masks both (M3.34)


def fine_position(rec: bytes) -> tuple[float, float]:
    ax, ay, flon, flat = fine_fields(rec)
    return coord.decode_point_id(ax, ay, flon, flat)


def swapped_position(rec: bytes) -> tuple[float, float]:
    """Negative control: the two fine fields exchanged."""
    ax, ay, flon, flat = fine_fields(rec)
    return coord.decode_point_id(ax, ay, flat, flon)


def legacy_position(rec: bytes) -> tuple[float, float]:
    """The 1-unit reading used before M4.27 (refer.md, C-1880)."""
    ax, ay = struct.unpack_from(">HH", rec, 2)
    return (ax - LAT_ORIGIN) / LAT_SCALE, (ay - LEGACY_LON_ORIGIN) / LON_SCALE


def encode_position(lat: float, lon: float) -> tuple[int, int, int, int]:
    """Inverse of :func:`fine_position`: ``(A.x, A.y, rec[6..7], rec[8..9])``."""
    return coord.encode_point_id(lat, lon)


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371008.8 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# structure walkers


class Spans:
    """Claimed byte ranges of one file."""

    def __init__(self, size: int):
        self.size = size
        self.items: list[tuple[int, int, str]] = []

    def add(self, start: int, end: int, cls: str) -> None:
        if not 0 <= start <= end <= self.size:
            raise CensusError(f"{cls}: range {start:#x}..{end:#x} outside the file")
        if end > start:
            self.items.append((start, end, cls))

    def account(self, blob: bytes) -> dict:
        """Bytes per class, overlaps, and the unclaimed remainder split into
        fill (zero / ``ff``) and unaccounted (anything else)."""
        out = Counter()
        overlap = 0
        pos = 0
        gaps = []
        for start, end, cls in sorted(self.items):
            if start < pos:
                overlap += min(end, pos) - start
                start = pos
                if end <= start:
                    continue
            if start > pos:
                gaps.append((pos, start))
            out[cls] += end - start
            pos = end
        if pos < self.size:
            gaps.append((pos, self.size))
        loose = []
        for a, b in gaps:
            chunk = blob[a:b]
            plain = chunk.count(0) + chunk.count(0xFF)
            out["fill"] += plain
            if plain != len(chunk):
                out["unaccounted"] += len(chunk) - plain
                loose.append((a, b, len(chunk) - plain))
        return {"classes": dict(out), "overlap": overlap, "loose": loose}


def read_ref(blob: bytes, pos: int) -> dict:
    """Structure reference inside a descriptor record."""
    addr, words, zero, rootw, flags = struct.unpack_from(">IIIHH", blob, pos)
    ref = {"pos": pos, "start": regen.blk_off(addr), "words": words, "zero": zero,
           "root_words": rootw, "flags": flags}
    if flags != FLAG_SPATIAL:
        caddr, cwords = struct.unpack_from(">II", blob, pos + 16)
        ref["chain"] = regen.blk_off(caddr)
        ref["chain_words"] = cwords
    return ref


def read_ref_list(blob: bytes, record: int, limit: int) -> list[dict]:
    """Entries ``u16 next_w, reference, ...``; the last has ``next_w = ffff``."""
    out, pos = [], record
    while True:
        (nxt,) = struct.unpack_from(">H", blob, pos)
        out.append(read_ref(blob, pos + 2))
        if nxt == 0xFFFF:
            return out
        new = record + 2 * nxt
        if new <= pos or new >= record + limit:
            raise CensusError(f"descriptor list at {record:#x}: next offset {nxt:#x} at {pos:#x}")
        pos = new


def walk_trie(blob: bytes, ref: dict, record_words: int | None) -> dict:
    """Walk a name trie from its root; every byte of the region must belong to
    exactly one node and every leaf must point at a record of the index chain."""
    base, words = ref["start"], ref["words"]
    stack = [(0, ref["root_words"], EMPTY)]
    nodes = []
    stats = Counter()
    chain_words = ref.get("chain_words", 0)
    while stack:
        off, size, parent = stack.pop()
        if size % 6 or off + size > words:
            raise CensusError(f"trie {base:#x}: node {off:#x}+{size:#x} outside {words:#x} words")
        nodes.append((off, size))
        start = base + 2 * off
        for coff, csize, zero, ch, hi, n in TRIE_ENTRY.iter_unpack(blob[start:start + 2 * size]):
            if ch == 0xFF:
                # terminal: index offset of the node's first record, parent node
                # offset, count of names that end at this node
                stats["terminal"] += 1
                if (csize << 16 | zero) != parent:
                    stats["bad_terminal"] += 1
                if record_words and (coff % record_words or coff > chain_words):
                    stats["bad_leaf_offset"] += 1
                continue
            if zero:
                stats["nonzero_pad"] += 1
            if csize:
                stack.append((coff, csize, off))
                stats["inner"] += 1
            else:
                stats["leaf"] += 1
                if record_words and (coff % record_words or coff >= chain_words):
                    stats["bad_leaf_offset"] += 1
        stats["entries"] += size // 6
    nodes.sort()
    pos = 0
    for off, size in nodes:
        if off != pos:
            stats["gap_or_overlap"] += 1
        pos = max(pos, off + size)
    tail = words - pos
    stats["nodes"] = len(nodes)
    stats["tail_words"] = tail
    ok = (not stats["gap_or_overlap"] and not stats["bad_leaf_offset"]
          and not stats["nonzero_pad"] and not stats["bad_terminal"] and 0 <= tail and not any(blob[base + 2 * pos:base + 2 * words]))
    return {"ok": ok, **stats}


def read_index_chain(blob: bytes, start: int, words: int) -> tuple[bytes, int, int]:
    """``(inflated records, end offset, streams)`` of an index chain."""
    if blob[start:start + 4] != INDEX_MAGIC:
        raise CensusError(f"index chain {start:#x}: magic {blob[start:start + 4].hex()}")
    n = 1
    while blob[start + 4 + 4 * n] != 0x78:
        n += 1
        if n > 4096:
            raise CensusError(f"index chain {start:#x}: no stream after the length table")
    lens = struct.unpack_from(f">{n}I", blob, start + 4)
    pos = start + 4 + 4 * n
    parts = []
    for comp_w in lens:
        d = zlib.decompressobj()
        parts.append(d.decompress(blob[pos:pos + 2 * comp_w]))
        if not d.eof:
            raise CensusError(f"index chain {start:#x}: stream at {pos:#x} does not end in {comp_w:#x} words")
        pos += 2 * comp_w
    out = b"".join(parts)
    if len(out) != 2 * words:
        raise CensusError(f"index chain {start:#x}: {len(out)} B inflated, descriptor says {2 * words}")
    return out, pos, n


def walk_spatial(blob: bytes, ref: dict) -> dict:
    """Walk a spatial tree; returns its leaves ``(ptr, kx, ky, cell_x, cell_y)``."""
    base, words = ref["start"], ref["words"]
    stack = [(0, ref["root_words"], 0, (0, 0))]
    nodes, leaves = [], []
    stats = Counter()
    while stack:
        off, size, depth, key = stack.pop()
        if off + size > words:
            raise CensusError(f"spatial {base:#x}: node {off:#x}+{size:#x} outside {words:#x} words")
        nodes.append((off, size))
        pos, end = base + 2 * off, base + 2 * (off + size)
        while pos < end:
            (head,) = struct.unpack_from(">H", blob, pos)
            if head == 5:                      # terminator: 0005 ffffffff u32
                if blob[pos + 2:pos + 6] != b"\xff\xff\xff\xff":
                    stats["bad_terminator"] += 1
                pos += 10
                continue
            if head != 8:
                raise CensusError(f"spatial {base:#x}: entry head {head:#x} at {pos:#x}")
            _, ptr, csize, kx, ky, fine = SPATIAL_ENTRY.unpack_from(blob, pos)
            if csize:
                # levels 0..2 are keyed by the packed cell id (128-, 16- and
                # 1-nibble steps); a level below groups by a category code
                stack.append((ptr, csize, depth + 1, (kx, ky) if depth < CELL_DEPTH else key))
                stats[f"inner{depth}"] += 1
                if fine:
                    stats["inner_with_fine"] += 1
                if depth < CELL_DEPTH and (kx & KEY_MASK[depth] or ky & KEY_MASK[depth]
                                           or (depth == CELL_DEPTH - 1 and (kx & ky & 0xC) != 0xC)):
                    stats["bad_key"] += 1
            else:
                leaves.append((ptr, fine >> 16, fine & 0xFFFF, key[0], key[1]))
                stats[f"leaf{depth}"] += 1
                if depth < CELL_DEPTH:
                    stats["shallow_leaf"] += 1
            pos += 16
        if pos != end:
            stats["node_overrun"] += 1
    nodes.sort()
    pos = 0
    for off, size in nodes:
        # nodes start on 0x100 boundaries; the slack up to the next one is zero
        if off < pos or any(blob[base + 2 * pos:base + 2 * off]):
            stats["gap_or_overlap"] += 1
        pos = off + size
    ok = not (stats["gap_or_overlap"] or stats["node_overrun"] or stats["bad_terminator"]
              or stats["inner_with_fine"] or stats["shallow_leaf"] or stats["bad_key"]
              or any(blob[base + 2 * pos:base + 2 * words]))
    return {"ok": ok, "leaves": leaves, "nodes": len(nodes), **stats}


def walk_phone(blob: bytes, start: int, words: int) -> dict:
    """Walk the phone B-tree: 0x1000-byte nodes, 16-byte entries."""
    size = 2 * words
    if size % PHONE_NODE:
        raise CensusError(f"phone index {start:#x}: {size:#x} B is not whole nodes")
    stats = Counter()
    seen = set()
    stack = [0]
    keys = []
    entries = []
    while stack:
        node = stack.pop()
        if node in seen or node % PHONE_NODE or node >= size:
            stats["bad_child"] += 1
            continue
        seen.add(node)
        ended = False
        for child, poi, key in struct.iter_unpack(">II8s", blob[start + node:start + node + PHONE_NODE]):
            if child == EMPTY and poi == EMPTY:
                ended = True
                continue
            if ended:
                stats["entry_after_end"] += 1
            if child != EMPTY:
                stack.append(2 * child)
                stats["inner"] += 1
            else:
                stats["leaf"] += 1
            keys.append(key)
            entries.append((poi, key))
    stats["nodes"] = len(seen)
    bcd = sum(1 for k in keys if all((b >> 4) in (*range(10), 15) and (b & 15) in (*range(10), 15) for b in k))
    stats["bcd_keys"] = bcd
    unused = [n for n in range(0, size, PHONE_NODE) if n not in seen]
    stats["unused_nodes"] = len(unused)
    blank = all(blob[start + n:start + n + PHONE_NODE].count(0xFF) == PHONE_NODE for n in unused)
    ok = (not stats["bad_child"] and not stats["entry_after_end"] and bcd == len(keys) and blank)
    return {"ok": ok, "keys": len(keys), "entries": entries, **stats}


def chain_records(chain) -> list[bytes]:
    out = []
    for _, _, inner in chain.pages:
        recs = regen.walk_records(inner)
        if recs is None:
            raise CensusError(f"chain {chain.per_page}: a page does not walk")
        out.extend(inner[o:o + s] for o, s in recs)
    return out


def census(blob: bytes, want_joins: bool = False) -> dict:
    """Walk every structure of a decoded POINT ``.DAT``."""
    spans = Spans(len(blob))
    spans.add(0, regen.DIR_START, "header")
    spans.add(regen.DIR_START, regen.DIR_START + regen.DIR_CELL * regen.DIR_CELLS, "directory")
    cells = {cell: (rec, blocks) for cell, rec, blocks in regen.directory(blob)}
    report = {"size": len(blob), "cells": sorted(cells), "checks": [], "counts": Counter()}
    unknown = [c for c in cells if c not in KNOWN_CELLS]
    if unknown:
        report["checks"].append(("unknown directory cells " + ",".join(f"{c:#x}" for c in unknown), False))
    for cell, (rec, blocks) in cells.items():
        spans.add(rec, rec + blocks * regen.BLOCK, "descriptor")

    tries, spatial = [], []
    phone_entries = []
    for cell in (CELL_NAME_TRIE, CELL_AREA_TRIE):
        if cell in cells:
            tries.append((cell, read_ref(blob, cells[cell][0] + 2)))
    for cell in (CELL_CATEGORY, CELL_SUBCATEGORY):
        if cell in cells:
            rec, blocks = cells[cell]
            tries.extend((cell, r) for r in read_ref_list(blob, rec, blocks * regen.BLOCK))
    if CELL_SPATIAL in cells:
        rec, blocks = cells[CELL_SPATIAL]
        spatial = read_ref_list(blob, rec, blocks * regen.BLOCK)

    # name tries and their index chains
    trie_ok = chain_ok = 0
    index_records = {}
    for cell, ref in tries:
        if ref["flags"] == FLAG_SPATIAL:
            report["checks"].append((f"trie reference at {ref['pos']:#x} has the spatial flag", False))
            continue
        recw = INDEX_RECORD_WORDS.get(ref["flags"])
        res = walk_trie(blob, ref, recw)
        trie_ok += res["ok"]
        report["counts"]["trie_entries"] += res["entries"]
        report["counts"]["trie_nodes"] += res["nodes"]
        spans.add(ref["start"], ref["start"] + 2 * ref["words"], "name-trie")
        data, end, streams = read_index_chain(blob, ref["chain"], ref["chain_words"])
        chain_ok += bool(recw) and len(data) % (2 * recw) == 0
        report["counts"]["index_streams"] += streams
        report["counts"][f"index_records_{recw}w"] += len(data) // (2 * recw) if recw else 0
        spans.add(ref["chain"], end, "index-chain")
        if cell in (CELL_NAME_TRIE, CELL_AREA_TRIE):
            index_records[cell] = data
    report["counts"]["tries"] = len(tries)
    report["checks"].append((f"name tries tile their region and leaves hit index records: {trie_ok}/{len(tries)}",
                             trie_ok == len(tries)))
    report["checks"].append((f"index chains inflate to the descriptor length in whole records: {chain_ok}/{len(tries)}",
                             chain_ok == len(tries)))

    # spatial trees
    sp_ok = 0
    leaves = []
    for ref in spatial:
        res = walk_spatial(blob, ref)
        sp_ok += res["ok"]
        leaves.extend(res["leaves"])
        report["counts"]["spatial_nodes"] += res["nodes"]
        spans.add(ref["start"], ref["start"] + 2 * ref["words"], "spatial-tree")
    report["counts"]["spatial_trees"] = len(spatial)
    report["counts"]["spatial_leaves"] = len(leaves)
    report["checks"].append((f"spatial trees walk with zero slack only: {sp_ok}/{len(spatial)}",
                             sp_ok == len(spatial)))

    # dictionary record: phone index and the 1000/400 chains; ADM record: 2000
    chains = {}
    if CELL_DICT in cells:
        rec = cells[CELL_DICT][0]
        paddr, pwords = struct.unpack_from(">II", blob, rec + 4)
        if paddr != EMPTY and pwords:
            pstart = regen.blk_off(paddr)
            res = walk_phone(blob, pstart, pwords)
            phone_entries = res["entries"]
            report["counts"]["phone_keys"] = res["keys"]
            report["counts"]["phone_nodes"] = res["nodes"]
            report["checks"].append((f"phone B-tree: {res['nodes']} nodes, {res['keys']} BCD keys, "
                                     f"{res['unused_nodes']} blank nodes", res["ok"]))
            spans.add(pstart, pstart + 2 * pwords, "phone-btree")
    for per in (1000, 400, 2000):
        try:
            ch = regen.chain_via_locator(blob, per)
        except (KeyError, struct.error):
            ch = None
        if ch is None:
            if (CELL_ADM if per == 2000 else CELL_DICT) in cells:
                report["checks"].append((f"chain {per} not reachable through its locator", False))
            continue
        chains[per] = ch
        spans.add(ch.base, ch.end, f"page-chain-{per}")
        spans.add(ch.toc, ch.toc + ch.toc_size, "chain-table")
        report["counts"][f"pages_{per}"] = len(ch.pages)

    acc = spans.account(blob)
    report["classes"] = acc["classes"]
    report["loose"] = acc["loose"]
    report["checks"].append((f"no structure overlaps another ({acc['overlap']} B)", acc["overlap"] == 0))
    report["checks"].append((f"unaccounted bytes: {acc['classes'].get('unaccounted', 0)}",
                             acc["classes"].get("unaccounted", 0) == 0))

    if want_joins:
        report["joins"] = joins(blob, chains, leaves, index_records, phone_entries)
    report["counts"] = dict(report["counts"])
    report["ok"] = all(ok for _, ok in report["checks"])
    return report


# ---------------------------------------------------------------------------
# cross references


JOIN_SHIFT = 7919      # negative control: the same reference moved by a prime


def leaf_matches(leaf, rec: bytes) -> bool:
    ptr, fx, fy, cx, cy = leaf
    ax, ay, v6, v8 = struct.unpack_from(">4H", rec, 2)
    return (cx, cy) == (ax, ay) and fx & 0x7FF == v6 & 0x7FF and fy & 0x7FF == v8


def index_key(entry: bytes) -> bytes:
    """Key bytes an index record shares with its name record: words 0..1,
    the words 2..5 that are not ``ffff`` (area and category levels) and
    words 7..8 (sub-category, brand)."""
    opt = b"".join(entry[p:p + 2] for p in (4, 6, 8, 10) if entry[p:p + 2] != b"\xff\xff")
    return entry[0:4] + opt + entry[14:18]


def phone_digits(key: bytes) -> bytes:
    return key.hex().rstrip("f").encode()


def info_has_phone(info: bytes, digits: bytes) -> bool:
    """An INFORMATION record holds the number as one NUL-ended ASCII string."""
    return any(bytes(c for c in part if 0x30 <= c <= 0x39) == digits
               for part in info[4:].split(b"\x00") if part)


def joins(blob: bytes, chains: dict, leaves: list, index_records: dict, phone_entries: list) -> dict:
    out = {}
    names = chain_records(chains[1000]) if 1000 in chains else []
    out["name_records"] = len(names)
    n = len(names)
    if leaves and n:
        hit = sum(1 for leaf in leaves if leaf[0] < n and leaf_matches(leaf, names[leaf[0]]))
        ctl = sum(1 for leaf in leaves if leaf_matches(leaf, names[(leaf[0] + JOIN_SHIFT) % n]))
        ptrs = {leaf[0] for leaf in leaves}
        usual = sum(1 for leaf in leaves if leaf[1] >> 11 == 0x11 and leaf[2] >> 11 == 0x1F)
        out["spatial"] = {"leaves": len(leaves), "match": hit, "control": ctl, "usual_flags": usual,
                          "distinct_ptr": len(ptrs), "ptr_cover": len(ptrs & set(range(n)))}
    data = index_records.get(CELL_NAME_TRIE)
    if data and n:
        total = hit = ctl = bad = 0
        ids = set()
        for pos in range(0, len(data), 24):
            entry = data[pos:pos + 24]
            (poi,) = struct.unpack_from(">I", entry, 20)
            total += 1
            if poi >= n:
                bad += 1
                continue
            ids.add(poi)
            key = index_key(entry)
            hit += key in names[poi]
            ctl += key in names[(poi + JOIN_SHIFT) % n]
        out["index"] = {"records": total, "match": hit, "control": ctl, "id_out_of_range": bad,
                        "distinct_ids": len(ids)}
    nibbles = Counter()
    fine_hi = 0
    for rec in names:
        ax, ay, v6, v8 = struct.unpack_from(">4H", rec, 2)
        nibbles[(ax & 15) >> 2] += 1
        nibbles[(ay & 15) >> 2] += 1
        fine_hi += (v6 >> 11 != 1) or v8 > 0x7FF
    out["marker"] = {"records": n, "nibble_11xx": nibbles[3], "words": 2 * n, "fine_out_of_form": fine_hi}
    # the 400 chain holds one INFORMATION record per name record tagged 0x60,
    # in the same order; the phone B-tree key is that record's number
    info = chain_records(chains[400]) if 400 in chains else []
    out["records_400"] = len(info)
    rank, k = {}, 0
    for i, rec in enumerate(names):
        if rec[0] & 0xFC == 0x60:
            rank[i] = k
            k += 1
    out["names_tag_60"] = k
    if phone_entries and info:
        total = hit = ctl = norank = 0
        for poi, key in phone_entries:
            digits = phone_digits(key)
            if not digits:
                continue
            total += 1
            if poi not in rank or rank[poi] >= len(info):
                norank += 1
                continue
            hit += info_has_phone(info[rank[poi]], digits)
            ctl += info_has_phone(info[(rank[poi] + JOIN_SHIFT) % len(info)], digits)
        out["phone"] = {"keys": total, "match": hit, "control": ctl, "no_info_record": norank}
    if 2000 in chains:
        out["records_2000"] = len(chain_records(chains[2000]))
    return out


# ---------------------------------------------------------------------------
# files


def find_pairs(directory: Path, only: list[str] | None = None) -> list[tuple[str, Path, Path]]:
    cmps = {}
    inds = {}
    for p in Path(directory).iterdir():
        up = p.name.upper()
        if up.startswith("POINT") and up.endswith(".DAT.CMP"):
            cmps[up[:-8]] = p
        elif up.startswith("POINT") and up.endswith(".DAT.IND"):
            inds[up[:-8]] = p
    out = [(name, cmps[name], inds[name]) for name in sorted(cmps) if name in inds]
    if only:
        want = {o.upper() for o in only}
        out = [row for row in out if row[0] in want]
    return out


def load(cmp_path: Path, ind_path: Path) -> bytes:
    return cmpind.decode(cmp_path, ind_path)[0]


CLASS_ORDER = ("header", "directory", "descriptor", "name-trie", "index-chain", "spatial-tree",
               "phone-btree", "page-chain-1000", "page-chain-400", "page-chain-2000",
               "chain-table", "fill", "unaccounted")


def cmd_extract(args) -> int:
    """Copy every ``REFER001/POINTnnn.DAT.cmp/.ind`` of a card image to OUTDIR."""
    import vcard_l3

    src = vcard_l3.open_source(image=args.card_image)
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    count = size = 0
    for entry in src.list_dir("REFER001"):
        up = entry.name.upper()
        if up.startswith("POINT") and up.endswith((".DAT.CMP", ".DAT.IND")):
            (out / up).write_bytes(src.read_range(entry.path, 0, entry.size))
            count += 1
            size += entry.size
    print(f"{count} files, {size:,} B -> {out} (vendor data: do not commit)")
    return 0 if count else 1


def cmd_census(args) -> int:
    pairs = find_pairs(args.dir, args.files)
    if not pairs:
        print(f"no POINT pairs in {args.dir}")
        return 2
    total = Counter()
    counts = Counter()
    rows = []
    bad = 0
    for name, cmp_path, ind_path in pairs:
        blob = load(cmp_path, ind_path)
        try:
            rep = census(blob)
        except (CensusError, struct.error, zlib.error, ValueError) as exc:
            print(f"{name}: FAIL {exc}")
            bad += 1
            continue
        rows.append({"file": name, "size": rep["size"], "classes": rep["classes"],
                     "counts": rep["counts"], "ok": rep["ok"],
                     "failed": [text for text, ok in rep["checks"] if not ok]})
        total.update(rep["classes"])
        counts.update(rep["counts"])
        un = rep["classes"].get("unaccounted", 0)
        print(f"{name}: {rep['size']:>11,} B  cells={len(rep['cells'])}  tries={rep['counts'].get('tries', 0)}  "
              f"spatial={rep['counts'].get('spatial_trees', 0)}  unaccounted={un}  "
              f"{'OK' if rep['ok'] else 'FAIL'}")
        for text, ok in rep["checks"]:
            if not ok:
                print(f"    FAIL {text}")
                bad += 1
        for a, b, n in rep["loose"][:8]:
            print(f"    loose {a:#x}..{b:#x}: {n} B, head {blob[a:a + 16].hex()}")
    size = sum(r["size"] for r in rows)
    print(f"\nfiles: {len(rows)}/{len(pairs)}   decoded bytes: {size:,}")
    for cls in CLASS_ORDER:
        if total.get(cls) or cls == "unaccounted":
            print(f"  {cls:<16} {total.get(cls, 0):>14,} B  {100.0 * total.get(cls, 0) / max(size, 1):6.2f} %")
    for key in sorted(counts):
        print(f"  {key}: {counts[key]:,}")
    if args.json:
        Path(args.json).write_text(json.dumps({"files": rows, "total": dict(total), "counts": dict(counts)},
                                              indent=1) + "\n")
    ok = bad == 0 and len(rows) == len(pairs)
    print("VERDICT: " + ("every byte reached by a walked structure" if ok else "FAIL"))
    return 0 if ok else 1


def cmd_joins(args) -> int:
    pairs = find_pairs(args.dir, args.files)
    if not pairs:
        print(f"no POINT pairs in {args.dir}")
        return 2
    tot = Counter()
    for name, cmp_path, ind_path in pairs:
        blob = load(cmp_path, ind_path)
        rep = census(blob, want_joins=True)
        j = rep["joins"]
        sp, ix, mk = j.get("spatial"), j.get("index"), j["marker"]
        line = f"{name}: names={j['name_records']}"
        if sp:
            line += (f"  leaves={sp['leaves']} match={sp['match']} control={sp['control']} "
                     f"ptr_cover={sp['ptr_cover']}")
            tot["leaves"] += sp["leaves"]
            tot["leaf_match"] += sp["match"]
            tot["leaf_control"] += sp["control"]
            tot["ptr_cover"] += sp["ptr_cover"]
            tot["usual_flags"] += sp["usual_flags"]
        if ix:
            line += f"  index={ix['records']} key_match={ix['match']} control={ix['control']}"
            tot["index"] += ix["records"]
            tot["index_match"] += ix["match"]
            tot["index_control"] += ix["control"]
            tot["index_bad_id"] += ix["id_out_of_range"]
        ph = j.get("phone")
        if ph:
            line += f"  phone={ph['keys']} match={ph['match']} control={ph['control']}"
            tot["phone"] += ph["keys"]
            tot["phone_match"] += ph["match"]
            tot["phone_control"] += ph["control"]
        line += f"  info={j['records_400']}/tag60={j['names_tag_60']}"
        tot["tag60"] += j["names_tag_60"]
        line += f"  11xx={mk['nibble_11xx']}/{mk['words']} fine_bad={mk['fine_out_of_form']}"
        tot["names"] += j["name_records"]
        tot["marker"] += mk["nibble_11xx"]
        tot["marker_words"] += mk["words"]
        tot["fine_bad"] += mk["fine_out_of_form"]
        tot["records_400"] += j["records_400"]
        tot["records_2000"] += j.get("records_2000", 0)
        print(line)
    print(f"\nfiles: {len(pairs)}  name records: {tot['names']:,}  "
          f"400-chain records: {tot['records_400']:,}  2000-chain records: {tot['records_2000']:,}")
    print(f"spatial leaf = (cell of copy A, 11 low bits of rec[6..7], rec[8..9]) of name record ptr: "
          f"{tot['leaf_match']:,}/{tot['leaves']:,}; shifted-ptr control {tot['leaf_control']:,}; "
          f"leaves with the usual high bits 0x8800/0xf800 {tot['usual_flags']:,}; "
          f"name records with a leaf {tot['ptr_cover']:,}/{tot['names']:,}")
    print(f"index record key found in name record id: {tot['index_match']:,}/{tot['index']:,}; "
          f"shifted-id control {tot['index_control']:,}; ids out of range {tot['index_bad_id']:,}")
    print(f"phone B-tree key = number in the INFORMATION record of its POI: "
          f"{tot['phone_match']:,}/{tot['phone']:,}; shifted control {tot['phone_control']:,}; "
          f"INFORMATION records {tot['records_400']:,} vs name records tagged 0x60 {tot['tag60']:,}")
    print(f"copy-A words with low nibble 11xx: {tot['marker']:,}/{tot['marker_words']:,}; "
          f"fine fields out of form: {tot['fine_bad']:,}")
    ok = (tot["leaf_match"] == tot["leaves"] and tot["index_match"] == tot["index"]
          and tot["marker"] == tot["marker_words"] and not tot["fine_bad"] and not tot["index_bad_id"]
          and tot["leaf_control"] * 10 < max(tot["leaves"], 1)
          and tot["phone_match"] == tot["phone"] and tot["leaves"] and tot["index"] and tot["records_400"] == tot["tag60"])
    print("VERDICT: " + ("joins hold" if ok else "FAIL"))
    return 0 if ok else 1


def record_at(blob: bytes, stream: int, index: int) -> bytes:
    inner = zlib.decompressobj().decompress(blob[stream:stream + regen.WINDOW])
    recs = regen.walk_records(inner)
    if recs is None:
        raise CensusError(f"stream at {stream:#x} does not walk")
    off, size = recs[index]
    return inner[off:off + size]


def cmd_refs(args) -> int:
    rows = [line.rstrip("\n").split("\t") for line in Path(args.refs).read_text().splitlines()
            if line.strip() and not line.startswith("#")]
    dirs = {"US": args.us, "EU": args.eu}
    cache = {}
    fine_err, old_err, swap_err = [], [], []
    for pid, country, shard, stream, index, lat, lon, *_ in rows:
        if not dirs.get(country):
            continue
        key = (country, shard)
        if key not in cache:
            pair = find_pairs(dirs[country], [shard])
            if not pair:
                print(f"{pid}: {shard} not in {dirs[country]}")
                return 2
            cache[key] = load(pair[0][1], pair[0][2])
        rec = record_at(cache[key], int(stream, 16), int(index))
        lat, lon = float(lat), float(lon)
        f = haversine_m(lat, lon, *fine_position(rec))
        o = haversine_m(lat, lon, *legacy_position(rec))
        fine_err.append(f)
        old_err.append(o)
        swap_err.append(haversine_m(lat, lon, *swapped_position(rec)))
        ax, ay, flon, flat = fine_fields(rec)
        print(f"{pid} {country} {shard}: A=({ax:#06x},{ay:#06x}) fine=({flon},{flat})  "
              f"fine model {f:8.1f} m   1-unit reading {o:8.1f} m")
    if not fine_err:
        print("no reference rows")
        return 2
    fs, os_ = sorted(fine_err), sorted(old_err)
    med = lambda v: v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2  # noqa: E731
    better = sum(1 for f, o in zip(fine_err, old_err) if f < o)
    print(f"\nrows: {len(fs)}   fine model: median {med(fs):.1f} m, max {fs[-1]:.1f} m, "
          f"<= 100 m: {sum(1 for v in fs if v <= 100)}   1-unit reading: median {med(os_):.1f} m, "
          f"max {os_[-1]:.1f} m, <= 100 m: {sum(1 for v in os_ if v <= 100)}   fine closer: {better}/{len(fs)}")
    sw = sorted(swap_err)
    print(f"control, fine fields exchanged: median {med(sw):.1f} m, <= 100 m: {sum(1 for v in sw if v <= 100)}")
    ok = med(fs) * 5 < med(os_) and better * 10 >= len(fs) * 8 and med(fs) * 3 < med(sw)
    print("VERDICT: " + ("fine position model holds" if ok else "FAIL"))
    return 0 if ok else 1


def cmd_position(args) -> int:
    pair = find_pairs(args.dir, [args.file])
    if not pair:
        print(f"{args.file} not in {args.dir}")
        return 2
    rec = record_at(load(pair[0][1], pair[0][2]), int(args.stream, 0), args.record)
    lat, lon = fine_position(rec)
    olat, olon = legacy_position(rec)
    print(f"fine model: {lat:.6f}, {lon:.6f}   1-unit reading: {olat:.6f}, {olon:.6f}")
    return 0


# ---------------------------------------------------------------------------
# selftest


def _pad(buf: bytearray, align: int = 0x100) -> int:
    while len(buf) % align:
        buf.append(0)
    return len(buf)


def synth_blob() -> tuple[bytes, dict]:
    """A small file with every structure class, built from the grammar above."""
    enc = regen.Encoder.reference() if hasattr(regen.Encoder, "reference") else None
    comp = (lambda b: enc.compress(b)) if enc else (lambda b: zlib.compress(b, 9))
    buf = bytearray(b"\xff" * 0x800)
    buf += b"\xff\xff\xff\xff\x00\x00" * regen.DIR_CELLS
    while len(buf) < 0x1000:
        buf.append(0xFF)

    def cell(cell_off: int, rec_off: int, blocks: int) -> None:
        struct.pack_into(">IH", buf, cell_off, regen.blk_addr(rec_off), blocks)

    # name records: two POIs in one cell
    names = []
    points = [(52.2297, 21.0122, b"PALAC KULTURY"), (52.2301, 21.0131, b"DWORZEC CENTRALNY")]
    for lat, lon, text in points:
        ax, ay, v6, v8 = encode_position(lat, lon)
        key = struct.pack(">HHIHH", 1, 0x0B, 0x4D, 6, 0xFFFF)
        body = struct.pack(">4H", ax, ay, v6, v8) + b"\x06\x12" + struct.pack(">HH", ax, ay) + key + text
        if len(body) % 2:
            body += b"\x00"
        names.append(struct.pack(">H", 0x6000 | (len(body) + 2) // 2) + body)

    # descriptor records
    d_name = _pad(buf); buf += bytes(0x100)
    d_dict = _pad(buf); buf += bytes(0x200)
    d_spat = _pad(buf); buf += bytes(0x100)
    d_adm = _pad(buf); buf += bytes(0x100)

    # index chain: one 24-byte record per POI
    index = b"".join(struct.pack(">HHIIIHHI", 1, 0x0B, 0x4D, EMPTY, 6, 0xFFFF, 0x3F00, i)
                     for i in range(len(names)))
    # trie: root with two leaves and a terminal
    trie = b"".join((TRIE_ENTRY.pack(0, 0, 0, ord("D"), 0, 1), TRIE_ENTRY.pack(12, 0, 0, ord("P"), 0, 1),
                     struct.pack(">IIH2x", 0, EMPTY, 0xFF00)))
    o_trie = _pad(buf); buf += trie
    o_chain = _pad(buf)
    stream = comp(index)
    stream += bytes(-len(stream) % 2)
    buf += INDEX_MAGIC + struct.pack(">I", len(stream) // 2) + stream
    struct.pack_into(">HIIIHHII", buf, d_name, 0xFFFF, regen.blk_addr(o_trie), len(trie) // 2, 0,
                     len(trie) // 2, 0x4C40, regen.blk_addr(o_chain), len(index) // 2)
    cell(CELL_NAME_TRIE, d_name, 1)

    # spatial tree: root -> level 1 -> cell -> leaves
    o_sp = _pad(buf)
    ax, ay, _, _ = encode_position(*points[0][:2])
    leaves = b""
    for i, (lat, lon, _) in enumerate(points):
        px, py, v6, v8 = encode_position(lat, lon)
        assert (px, py) == (ax, ay)
        leaves += SPATIAL_ENTRY.pack(8, i, 0, 0, 0, (0x8000 | v6) << 16 | 0xF800 | v8)
    term = struct.pack(">HIHH", 5, EMPTY, 0, 0)
    node_w = (16 + 10) // 2
    tree = bytearray()
    for depth, key in enumerate(((ax & ~0x7F, ay & ~0x7F), (ax & ~15, ay & ~15), (ax, ay))):
        tree += SPATIAL_ENTRY.pack(8, (depth + 1) * 0x80, node_w if depth < 2 else (len(leaves) + 10) // 2,
                                   key[0], key[1], 0) + term
        tree += bytes(-len(tree) % 0x100)
    tree += leaves + term
    buf += tree
    struct.pack_into(">HIIIHHHHHHH", buf, d_spat, 0xFFFF, regen.blk_addr(o_sp), len(tree) // 2, 0,
                     node_w, FLAG_SPATIAL, 8, 0, 0, 1, 0)
    cell(CELL_SPATIAL, d_spat, 1)

    # phone B-tree: one node
    o_phone = _pad(buf)
    node = bytearray(b"\xff" * PHONE_NODE)
    struct.pack_into(">II8s", node, 0, EMPTY, 0, bytes.fromhex("48221234567fffff"))
    struct.pack_into(">II8s", node, 16, EMPTY, 1, bytes.fromhex("48227654321fffff"))
    buf += node

    def add_chain(per: int, pages: list[bytes]) -> tuple[int, int, int, int]:
        base = _pad(buf)
        entries, pos = [], 0
        for inner in pages:
            s = comp(inner)
            s += bytes(-len(s) % regen.PAGE_PAD)
            buf.extend(s)
            entries.append((pos // 2, len(s) // 2, len(inner) // 2))
            pos += len(s)
        toc = _pad(buf)
        buf.extend(regen.toc_bytes(per, entries))
        return base, pos, toc, 4 + 12 * len(entries)

    info = b"".join(struct.pack(">HH", 9, 7) + num + b"\x00\x00" for num in (b"48-221234567", b"48-227654321"))
    adm = struct.pack(">HHHHHIH", 10, 0x0401, 0x02FF, 1, 0x0B, 0, 3) + b"WAWA"
    refs = {}
    for per, pages in ((1000, [b"".join(names)]), (400, [info]), (2000, [adm])):
        refs[per] = add_chain(per, pages)
    _pad(buf)
    struct.pack_into(">HHII", buf, d_dict, 0xFFFF, 0x15, regen.blk_addr(o_phone), PHONE_NODE // 2)
    for per in (1000, 400):
        cellno, rb, rt = regen.LAYOUT[per]
        base, size, toc, toc_size = refs[per]
        struct.pack_into(">II", buf, d_dict + rb, regen.blk_addr(base), size // 2)
        struct.pack_into(">IIH", buf, d_dict + rt, regen.blk_addr(toc), toc_size // 2, per)
    cell(CELL_DICT, d_dict, 2)
    _, rb, rt = regen.LAYOUT[2000]
    base, size, toc, toc_size = refs[2000]
    struct.pack_into(">II", buf, d_adm + rb, regen.blk_addr(base), size // 2)
    struct.pack_into(">IIH", buf, d_adm + rt, regen.blk_addr(toc), toc_size // 2, 2000)
    cell(CELL_ADM, d_adm, 1)
    return bytes(buf), {"trie": o_trie, "spatial": o_sp, "chain": o_chain, "phone": o_phone,
                        "points": points, "name_base": refs[1000][0]}


def selftest() -> int:
    fails = []

    def ok(cond: bool, label: str) -> None:
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    # position model
    for lat, lon in ((52.2297, 21.0122), (19.72583, -155.08667), (36.143882, -5.349857), (64.1466, -21.9426)):
        ax, ay, v6, v8 = encode_position(lat, lon)
        rec = struct.pack(">5H", 0x6005, ax, ay, v6, v8)
        la, lo = fine_position(rec)
        ok(haversine_m(lat, lon, la, lo) < 2.0 and ax & 0xC == 0xC and ay & 0xC == 0xC and v6 >> 11 == 1
           and v8 <= 0x7FF, f"position round trip within 2 m at {lat},{lon}")
    ok(packed_units(0x8ECE, 1745) == 0x8EC0 + 8 + 1745 / 512, "packed_units: sub-cell 2 of nibble 0xe")
    rec = struct.pack(">5H", 0x6005, *encode_position(52.2297, 21.0122))
    ok(haversine_m(52.2297, 21.0122, *legacy_position(rec)) > 500, "negative control: 1-unit reading is > 500 m off")
    # M4.61: the formula has one source in ``coord``; assert the record-level
    # wrappers equal it exactly (no second copy of the arithmetic).
    same = all(
        encode_position(lat, lon) == coord.encode_point_id(lat, lon)
        and fine_position(rec := struct.pack(">5H", 0x6005, *coord.encode_point_id(lat, lon)))
        == coord.decode_point_id(*fine_fields(rec))
        for lat, lon in ((52.2297, 21.0122), (19.72583, -155.08667),
                         (36.143882, -5.349857), (64.1466, -21.9426))
    )
    ok(same, "wrapper equals coord.encode_point_id/decode_point_id")

    blob, info = synth_blob()
    rep = census(blob, want_joins=True)
    for text, good in rep["checks"]:
        ok(good, "synthetic file: " + text)
    ok(rep["ok"] and rep["classes"].get("unaccounted", 0) == 0, "synthetic file: census OK, 0 unaccounted")
    for cls in ("name-trie", "index-chain", "spatial-tree", "phone-btree", "page-chain-1000",
                "page-chain-400", "page-chain-2000", "chain-table", "descriptor"):
        ok(rep["classes"].get(cls, 0) > 0, f"synthetic file: class {cls} present")
    j = rep["joins"]
    ok(j["spatial"]["match"] == j["spatial"]["leaves"] == 2, "synthetic file: both spatial leaves match")
    ok(j["index"]["match"] == j["index"]["records"] == 2, "synthetic file: both index keys match")
    ok(j["phone"]["match"] == j["phone"]["keys"] == 2 and j["records_400"] == j["names_tag_60"] == 2,
       "synthetic file: both phone keys match their INFORMATION record")
    ok(j["marker"]["nibble_11xx"] == 4 and j["marker"]["fine_out_of_form"] == 0, "synthetic file: 11xx markers")

    # negative controls
    bad = bytearray(blob)
    bad[len(bad) - 0x40:len(bad) - 0x38] = b"VENDOR??"          # bytes no structure owns
    r = census(bytes(bad))
    ok(not r["ok"] and r["classes"].get("unaccounted", 0) == 8, "negative: 8 stray bytes are unaccounted")

    bad = bytearray(blob)
    struct.pack_into(">I", bad, info["trie"] + 12, 13)           # leaf offset not on a record
    r = census(bytes(bad))
    ok(not r["ok"], "negative: trie leaf off the record grid fails")

    bad = bytearray(blob)
    struct.pack_into(">H", bad, info["spatial"] + 6, 0x7FFF)     # root child size outside the tree
    try:
        census(bytes(bad))
        ok(False, "negative: spatial child outside the region raises")
    except CensusError:
        ok(True, "negative: spatial child outside the region raises")

    bad = bytearray(blob)
    leaf_pos = bad.rfind(SPATIAL_ENTRY.pack(8, 1, 0, 0, 0, 0)[:8])
    bad[leaf_pos + 14] ^= 0x01                                   # fine position of leaf 1
    r = census(bytes(bad), want_joins=True)
    ok(r["joins"]["spatial"]["match"] == 1, "negative: a changed leaf fine position no longer matches")

    bad = bytearray(blob)
    bad[info["phone"] + 8] = 0xAB                                # not a BCD digit
    r = census(bytes(bad))
    ok(not r["ok"], "negative: non-BCD phone key fails")

    bad = bytearray(blob)
    bad[info["chain"] + 3] = 1                                   # index chain magic
    try:
        census(bytes(bad))
        ok(False, "negative: bad index chain magic raises")
    except CensusError:
        ok(True, "negative: bad index chain magic raises")

    print("point_census selftest: " + ("OK" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    e = sub.add_parser("extract", help="copy the POINT pairs of a card image to a directory")
    e.add_argument("--card-image", required=True)
    e.add_argument("outdir")
    e.set_defaults(func=cmd_extract)
    c = sub.add_parser("census", help="bytes per structure class, per file")
    c.add_argument("dir")
    c.add_argument("--files", nargs="*")
    c.add_argument("--json")
    c.set_defaults(func=cmd_census)
    j = sub.add_parser("joins", help="spatial leaf / index record vs name record")
    j.add_argument("dir")
    j.add_argument("--files", nargs="*")
    j.set_defaults(func=cmd_joins)
    r = sub.add_parser("refs", help="fine position model vs reference coordinates")
    r.add_argument("--us")
    r.add_argument("--eu")
    r.add_argument("--refs", required=True)
    r.set_defaults(func=cmd_refs)
    p = sub.add_parser("position", help="fine position of one name record")
    p.add_argument("dir")
    p.add_argument("file")
    p.add_argument("--stream", required=True)
    p.add_argument("--record", type=int, required=True)
    p.set_defaults(func=cmd_position)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmd:
        ap.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
