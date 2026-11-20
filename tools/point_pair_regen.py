#!/usr/bin/env python3
"""Whole-chain regeneration of a REFER001 ``POINTnnn.DAT.cmp/.ind`` pair (M5.26).

M5.21 showed that a generated POI name page cannot grow inside its own slot:
98.6 % of the edited pages abut the next stream.  This tool works one level up.
A POINT ``.DAT`` stores its inner zlib pages as **chains**: pages packed back to
back on 4-byte boundaries from a 0x100-aligned chain base, described by a
**chain table** (``TOC``) at a 0x100-aligned offset elsewhere in the file::

    u16 per_page  (BE; 1000 = 0x03e8 on name chains, 400 = 0x0190 on others)
    u16 0
    n x { u32 start_w, u32 comp_w, u32 inner_w }   (BE, 16-bit words)

``start_w`` is the page offset from the chain base, ``comp_w`` the stream
length rounded up to 4 bytes, ``inner_w`` the inflated page length, all in
2-byte words; ``start_w[i+1] = start_w[i] + comp_w[i]`` (OBSERVED, M5.26 EXP).
The table carries no chain base: the base is located by matching the first
page.  The field that tells the reader *where* the chain base and the table
are (``chain locator``) is not known; therefore this tool never moves a chain
base or a table.  It regenerates every page of a chain, re-packs the chain
from the same base, rewrites the table's ``comp_w``/``inner_w``/``start_w``
and refuses when the new chain does not fit before the next non-zero byte
after the old chain (the ``chain slot``).  Pages may now grow into slack that
other pages of the same chain give back (pooled budget, not per page).

Recompression uses stock zlib at the factory setting (level 6, memLevel 8,
wbits 15, default strategy; M1.13/M1.16).  ``--libz PATH`` loads that zlib
through ``ctypes`` (``factory_zlib.Lib``) so the encoder is the pinned stock
1.3.1 build even when the interpreter links another one; without it the
interpreter's zlib must be stock 1.3.1 (``tools/zlibinfo.py``).  Before any
write each page of the chain is re-encoded from its own inflated bytes and
must reproduce the factory stream; a chain that does not is refused (the
encoder is not the factory one), so unchanged pages never get new bytes.

Name sets are JSON lists of edits, one per name::

    [{"page": "0x6a7f00", "at": 94, "old": "HANA", "new": "OSM2 TEST"}]

``page`` is the absolute offset of the page stream in the decoded ``.DAT``,
``at`` the offset of ``old`` inside the inflated page.  ``old`` must be
followed by ``@`` and lie inside one record.  Records are walked as the
firmware walks them (``fn 0x003f5194`` EU2011, C-2540): a BE ``u16`` header
whose low 10 bits are the record size in words.  A length change must be even
and is written into those 10 bits; the record count of the page never changes
(the ``f11`` index addresses records by page and slot, not by byte offset).

Commands::

  python3 tools/point_pair_regen.py scan DIR [--json OUT]
  python3 tools/point_pair_regen.py regen CMP OUTDIR --names NAMES.json [--libz PATH]
  python3 tools/point_pair_regen.py regen CMP OUTDIR --noop [--libz PATH]
  python3 tools/point_pair_regen.py regen CMP OUTDIR --generate N --grow K [--libz PATH]
  python3 tools/point_pair_regen.py verify CMP OUTDIR/POINTnnn.DAT.cmp --names NAMES.json
  python3 tools/point_pair_regen.py --selftest

Exit codes: 0 ok; 1 refused / verification failed; 2 usage; 3 encoder is not
stock zlib 1.3.1 (unverifiable, ``zlibinfo``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zlib
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmpind_codec  # noqa: E402
import zlibinfo  # noqa: E402

TOC_ALIGN = 0x100
PAGE_PAD = 4
NAME_END = ord("@")
WINDOW = 1 << 21
REFERENCE_ZLIB = "1.3.1"


class RegenError(ValueError):
    """A record/table constraint is violated; nothing is written."""


# ---------------------------------------------------------------------------
# encoder


class Encoder:
    """Factory deflate (L6/m8/w15/default) from a named stock zlib build."""

    def __init__(self, libz: str | None = None):
        if libz:
            import factory_zlib  # ctypes loader, M1.13

            self._lib = factory_zlib.Lib("libz", libz)
            self.version = self._lib.version
            self.source = f"ctypes {libz}"
            self.sha256 = self._lib.sha256
        else:
            self._lib = None
            rt = zlibinfo.current()
            self.version = rt.runtime if rt.flavour == zlibinfo.STOCK else rt.line()
            self.source = f"python {sys.version.split()[0]} zlib module"
            self.sha256 = None

    @property
    def is_reference(self) -> bool:
        return self.version == REFERENCE_ZLIB

    def compress(self, data: bytes) -> bytes:
        if self._lib is not None:
            return self._lib.deflate(
                data, cmpind_codec.FACTORY_LEVEL, cmpind_codec.FACTORY_MEM,
                cmpind_codec.FACTORY_STRATEGY,
            )
        return cmpind_codec.factory_compress(data)

    def describe(self) -> dict:
        return {"version": self.version, "source": self.source,
                "sha256": self.sha256, "reference": self.is_reference}


# ---------------------------------------------------------------------------
# chain model


@dataclass
class Chain:
    toc: int                 # absolute offset of the chain table
    per_page: int            # u16 at toc
    entries: list            # [(start_w, comp_w, inner_w)]
    base: int = -1           # absolute offset of page 0 (located by matching)
    pages: list = field(default_factory=list)   # [(offset, stream_len, inner)]
    slot_end: int = -1       # first non-zero byte after the chain

    @property
    def end(self) -> int:
        s, c, _ = self.entries[-1]
        return self.base + 2 * (s + c)

    @property
    def toc_size(self) -> int:
        return 4 + 12 * len(self.entries)


def parse_toc(blob: bytes, off: int, max_entries: int = 4096) -> Chain | None:
    """Parse a chain table candidate at *off*; ``None`` when it is not one."""
    if off + 16 > len(blob) or off % TOC_ALIGN:
        return None
    per, zero = struct.unpack_from(">HH", blob, off)
    if per == 0 or zero != 0:
        return None
    entries = []
    pos, expect = off + 4, 0
    while pos + 12 <= len(blob) and len(entries) < max_entries:
        s, c, n = struct.unpack_from(">III", blob, pos)
        if s != expect or c == 0 or n == 0 or c > WINDOW // 2 or n > (1 << 24):
            break
        entries.append((s, c, n))
        expect = s + c
        pos += 12
    if not entries:
        return None
    return Chain(off, per, entries)


def _stream_at(blob: bytes, off: int) -> tuple[int, bytes] | None:
    if off + 2 > len(blob) or blob[off] != 0x78:
        return None
    try:
        inner, used = cmpind_codec.decompress_stream_at(blob, off, WINDOW)
    except cmpind_codec.FormatError:
        return None
    return used, inner


def _page_matches(entry, stream: tuple[int, bytes] | None) -> bool:
    if stream is None:
        return False
    _, comp_w, inner_w = entry
    used, inner = stream
    return 2 * comp_w - PAGE_PAD < used <= 2 * comp_w and len(inner) in (2 * inner_w, 2 * inner_w - 1)


def locate_chain(blob: bytes, chain: Chain, candidates: list[int]) -> bool:
    """Find the chain base among *candidates* (stream offsets); verify every page."""
    first = chain.entries[0]
    for base in candidates:
        st = _stream_at(blob, base)
        if not _page_matches(first, st):
            continue
        pages = []
        ok = True
        for s, c, n in chain.entries:
            off = base + 2 * s
            st = _stream_at(blob, off)
            if not _page_matches((s, c, n), st):
                ok = False
                break
            used, inner = st
            if any(blob[off + used: off + 2 * c]):
                ok = False  # padding must be zero
                break
            pages.append((off, used, inner))
        if ok:
            chain.base, chain.pages = base, pages
            end = chain.end
            nz = end
            while nz < len(blob) and blob[nz] == 0:
                nz += 1
            chain.slot_end = nz
            return True
    return False


def _aligned_heads(blob: bytes) -> list[int]:
    """0x100-aligned offsets that carry a valid zlib header (cheap pre-filter)."""
    return [o for o in range(0, len(blob) - 2, TOC_ALIGN)
            if blob[o] == 0x78 and ((blob[o] << 8) | blob[o + 1]) % 31 == 0]


def find_chains(blob: bytes, unresolved: list | None = None) -> list[Chain]:
    """All chain tables whose pages are located and verified in *blob*.

    Chain bases are tried at 0x100-aligned zlib headers first; a table left
    unmatched is retried against every stream of the file.  Tables that still
    match no chain are appended to *unresolved* (when given).
    """
    heads = _aligned_heads(blob)
    chains, pending = [], []
    for off in range(0, len(blob) - 16, TOC_ALIGN):
        ch = parse_toc(blob, off)
        if ch is None:
            continue
        (chains if locate_chain(blob, ch, heads) else pending).append(ch)
    if pending:
        streams = [s for s, _, _ in cmpind_codec.find_zlib_streams(blob, window=WINDOW)]
        for ch in pending:
            if locate_chain(blob, ch, streams):
                chains.append(ch)
            elif unresolved is not None:
                unresolved.append(ch)
    chains.sort(key=lambda c: c.base)
    return chains


NAME_TAGS = (0x60, 0x68)
LEN_MASK = 0x3FF
TAG_MASK = 0xFC00
LONG_TAG = 0xFC00
LONG_LEN = 0x4E8


def walk_records(inner: bytes) -> list[tuple[int, int]] | None:
    """Records of a page as ``(offset, size)`` by the firmware walk (C-2540).

    Header = BE ``u16 w``; size = ``2 * (w & 0x3ff)`` words, or ``2 * 0x4e8``
    when ``(w & 0xfc00) == 0xfc00``; the walk stops on size 0.  ``None`` when
    the walk does not end exactly at the page end.
    """
    out = []
    pos = 0
    while pos + 2 <= len(inner):
        w = (inner[pos] << 8) | inner[pos + 1]
        n = LONG_LEN if (w & TAG_MASK) == LONG_TAG else (w & LEN_MASK)
        if n == 0:
            break
        out.append((pos, 2 * n))
        pos += 2 * n
    return out if pos == len(inner) else None


def is_name_page(inner: bytes) -> bool:
    """A page whose records all carry a ``0x60``/``0x68`` tag and walk exactly."""
    recs = walk_records(inner)
    return bool(recs) and all(inner[o] & 0xFC in NAME_TAGS for o, _ in recs)


# ---------------------------------------------------------------------------
# regeneration


def apply_names(inner: bytes, edits: list[dict]) -> bytes:
    """Apply name edits (descending ``at``) to one inflated name page.

    A same-length edit replaces bytes only.  A length change must be even
    (sizes are stored in 16-bit words) and is written into the record's 10-bit
    length field; the tag bits are kept.  The page must walk exactly before and
    after, and the record count must not change.
    """
    recs = walk_records(inner)
    if recs is None:
        raise RegenError("page does not walk as a record chain (C-2540); refused")
    count = len(recs)
    out = bytearray(inner)
    ats = [e["at"] for e in edits]
    if len(set(ats)) != len(ats):
        raise RegenError("two edits at the same offset")
    for e in sorted(edits, key=lambda e: -e["at"]):
        at = e["at"]
        old = e["old"].encode("latin-1")
        new = e["new"].encode("latin-1")
        if not old or not new or b"@" in new or b"\x00" in new or b"@" in old:
            raise RegenError(f"edit at {at:#x}: names must be non-empty, without '@' or NUL")
        if bytes(out[at:at + len(old)]) != old:
            raise RegenError(f"edit at {at:#x}: {old!r} is not at that offset")
        if at + len(old) >= len(out) or out[at + len(old)] != NAME_END:
            raise RegenError(f"edit at {at:#x}: {old!r} is not followed by '@'")
        rec = next(((o, n) for o, n in walk_records(bytes(out)) or [] if o <= at < o + n), None)
        if rec is None or at < rec[0] + 2 or at + len(old) + 1 > rec[0] + rec[1]:
            raise RegenError(f"edit at {at:#x}: name is not inside one record body")
        delta = len(new) - len(old)
        if delta % 2:
            raise RegenError(f"edit at {at:#x}: length change {delta:+d} is odd; record sizes "
                             "are stored in 16-bit words, so names change by an even count")
        if delta:
            o, n = rec
            w = (out[o] << 8) | out[o + 1]
            if (w & TAG_MASK) == LONG_TAG:
                raise RegenError(f"edit at {at:#x}: record has the fixed-size 0xfc00 tag")
            words = (n + delta) // 2
            if not 2 <= words <= LEN_MASK:
                raise RegenError(f"edit at {at:#x}: record would be {words} words; "
                                 f"the length field holds 2..{LEN_MASK}")
            w = (w & ~LEN_MASK & 0xFFFF) | words
            out[o:o + 2] = struct.pack(">H", w)
        out[at:at + len(old)] = new
    result = bytes(out)
    after = walk_records(result)
    if after is None or len(after) != count:
        raise RegenError("edited page no longer walks with the same record count")
    return result


def check_factory_encoder(blob: bytes, chain: Chain, enc: Encoder) -> list[int]:
    """Indexes of chain pages the encoder does not reproduce byte for byte."""
    return [i for i, (off, used, inner) in enumerate(chain.pages)
            if enc.compress(inner) != blob[off:off + used]]


def regen_chain(blob: bytearray, chain: Chain, new_inners: list[bytes],
                enc: Encoder, streams_old: list[bytes], force: bool = False) -> dict:
    """Re-pack *chain* with *new_inners*; mutate *blob* in place or raise."""
    streams = []
    for i, inner in enumerate(new_inners):
        if inner == chain.pages[i][2] and not force:
            streams.append(streams_old[i])  # unchanged page: factory stream
        else:
            streams.append(enc.compress(inner))
    entries, pos = [], 0
    body = bytearray()
    for st, inner in zip(streams, new_inners):
        comp = (len(st) + PAGE_PAD - 1) // PAGE_PAD * PAGE_PAD
        entries.append((pos // 2, comp // 2, (len(inner) + 1) // 2))
        body += st + bytes(comp - len(st))
        pos += comp
    old_len = chain.end - chain.base
    slot = chain.slot_end - chain.base
    report = {"base": chain.base, "toc": chain.toc, "pages": len(entries),
              "old_bytes": old_len, "new_bytes": len(body), "slot": slot,
              "slack": slot - len(body)}
    if len(body) > slot:
        raise RegenError(
            f"chain at {chain.base:#x} (table {chain.toc:#x}): new chain {len(body)} B "
            f"> chain slot {slot} B (next non-zero byte {chain.slot_end:#x}); growing "
            "past it needs the chain locator field (UNKNOWN, see the M5.26 EXP)"
        )
    if chain.base < chain.toc < chain.slot_end:
        raise RegenError(f"chain table {chain.toc:#x} lies inside the chain slot")
    blob[chain.base:chain.base + len(body)] = body
    blob[chain.base + len(body):max(chain.end, chain.base + len(body))] = bytes(
        max(chain.end, chain.base + len(body)) - (chain.base + len(body)))
    toc = bytearray(struct.pack(">HH", chain.per_page, 0))
    for e in entries:
        toc += struct.pack(">III", *e)
    if len(toc) != chain.toc_size:
        raise RegenError("chain table size changed")
    blob[chain.toc:chain.toc + len(toc)] = toc
    report["entries_changed"] = sum(1 for a, b in zip(entries, chain.entries) if a != b)
    return report


def regen_blob(blob: bytes, names: list[dict], enc: Encoder,
               chains: list[Chain] | None = None) -> tuple[bytes, list[dict]]:
    """Apply *names* to *blob*; regenerate every chain that holds an edited page."""
    if chains is None:
        chains = find_chains(blob)
    by_page: dict[int, list[dict]] = {}
    for e in names:
        page = int(e["page"], 0) if isinstance(e["page"], str) else int(e["page"])
        by_page.setdefault(page, []).append(e)
    page_chain = {off: (ch, i) for ch in chains for i, (off, _, _) in enumerate(ch.pages)}
    missing = [p for p in by_page if p not in page_chain]
    if missing:
        raise RegenError(
            f"{len(missing)} edited page(s) are in no located chain table (first {missing[0]:#x}); "
            "their table is not known, so they are refused")
    out = bytearray(blob)
    reports = []
    touched = sorted({id(page_chain[p][0]): page_chain[p][0] for p in by_page}.values(),
                     key=lambda c: c.base)
    for ch in touched:
        bad = check_factory_encoder(blob, ch, enc)
        if bad:
            raise RegenError(
                f"chain {ch.base:#x}: encoder {enc.version} does not reproduce "
                f"{len(bad)} of {len(ch.pages)} factory pages (first page {bad[0]}); refusing "
                "to re-encode (use stock zlib 1.3.1)")
        new_inners = []
        for off, used, inner in ch.pages:
            edits = by_page.get(off, [])
            new_inners.append(apply_names(inner, edits) if edits else inner)
        olds = [blob[off:off + used] for off, used, _ in ch.pages]
        rep = regen_chain(out, ch, new_inners, enc, olds)
        rep["edits"] = sum(len(by_page.get(off, [])) for off, _, _ in ch.pages)
        reports.append(rep)
    return bytes(out), reports


# ---------------------------------------------------------------------------
# name-set generation (deterministic, OSM-like Latin-1 upper case)

_WORDS = ["APTEKA", "PIEKARNIA", "SKLEP", "KAWIARNIA", "RESTAURACJA", "STACJA",
          "PALIW", "POCZTA", "BANK", "SZKOLA", "PRZYCHODNIA", "HOTEL", "BAR",
          "KWIACIARNIA", "APTEKA POD ORLEM", "ZABKA", "BIEDRONKA", "LIDL"]


def generated_name(key: str, length: int) -> str:
    """Deterministic name of exactly *length* bytes from *key* (``OSM2`` prefix)."""
    h = hashlib.sha256(key.encode()).digest()
    words = ["OSM2"]
    i = 0
    while len(" ".join(words)) < length:
        words.append(_WORDS[h[i % len(h)] % len(_WORDS)])
        i += 1
    return " ".join(words)[:length].rstrip().ljust(length, "X")


def plan_names(blob: bytes, chains: list[Chain], count: int, grow: int,
               name_pages_only: bool = True) -> list[dict]:
    """Pick *count* ``NAME@`` sites over the name chains; new names are ``grow`` bytes longer."""
    import re
    rx = re.compile(rb"(?<![A-Z0-9' &.\-])[A-Z0-9][A-Z0-9' &.\-]{3,39}@")
    plan = []
    for ch in chains:
        for off, _, inner in ch.pages:
            if name_pages_only and not is_name_page(inner):
                continue
            seen = set()
            for m in rx.finditer(inner):
                old = m.group()[:-1]
                if old in seen or inner.count(old + b"@") != 1:
                    continue
                seen.add(old)
                new_len = len(old) + grow
                if not 1 <= new_len <= 80:
                    continue
                plan.append({"page": hex(off), "at": m.start(),
                             "old": old.decode("latin-1"),
                             "new": generated_name(f"{off}:{m.start()}", new_len)})
                if len(plan) >= count:
                    return plan
    return plan


def plan_permuted(blob: bytes, chains: list[Chain], count: int, seed: int = 1) -> list[dict]:
    """Real-entropy name set: *count* factory names, each replaced by another
    factory name of the same length parity drawn from a different page site
    (a proxy for an OSM name set of real, varied lengths).  Deterministic."""
    import random
    import re
    rx = re.compile(rb"(?<![A-Z0-9' &.\-])[A-Z0-9][A-Z0-9' &.\-]{3,39}@")
    sites = []
    for ch in chains:
        for off, _, inner in ch.pages:
            if not is_name_page(inner):
                continue
            for m in rx.finditer(inner):
                sites.append((off, m.start(), m.group()[:-1].decode("latin-1")))
    rnd = random.Random(seed)
    rnd.shuffle(sites)
    chosen = sites[:count]
    donors = sites[count:] or sites
    plan = []
    for i, (off, at, old) in enumerate(chosen):
        for j in range(len(donors)):
            new = donors[(i * 7919 + j) % len(donors)][2]
            if new != old and (len(new) - len(old)) % 2 == 0:
                break
        else:
            continue
        plan.append({"page": hex(off), "at": at, "old": old, "new": new})
    return plan


# ---------------------------------------------------------------------------
# pair I/O


def read_pair(cmp_path: Path):
    cmp_path, ind_path = cmpind_codec.pair_paths(cmp_path)
    usize, csize, count, chunk, offsets = cmpind_codec.read_ind(ind_path)
    packed = cmp_path.read_bytes()
    if csize != len(packed):
        raise RegenError(f"{cmp_path.name}: .ind says {csize} B, file has {len(packed)}")
    blob = cmpind_codec.decode_blob(packed, offsets, usize=usize, chunk_size=chunk,
                                    name=cmp_path.name)
    return blob, packed, list(offsets), usize, chunk


def write_pair(packed, offsets, usize, chunk, blob_old, blob_new, enc: Encoder):
    return cmpind_codec.rebuild_pair_bytes(packed, offsets, usize, chunk, blob_old,
                                           blob_new, compress=enc.compress)


def verify_pair(cmp_new: Path, names: list[dict], blob_old: bytes, chains_old: list[Chain]) -> dict:
    """Decode the rebuilt pair with ``cmpind.py``'s codec and check tables and names."""
    blob, _, _, _, _ = read_pair(cmp_new)
    if len(blob) != len(blob_old):
        raise RegenError("logical size changed")
    chains = find_chains(blob)
    by_base = {c.base: c for c in chains}
    res = {"chains_old": len(chains_old), "chains_new": len(chains), "names": 0,
           "names_ok": 0, "pages_checked": 0, "errors": []}
    for old in chains_old:
        new = by_base.get(old.base)
        if new is None or new.toc != old.toc or len(new.pages) != len(old.pages):
            res["errors"].append(f"chain {old.base:#x} not re-located from its table")
            continue
        for (o1, _, i1), (o2, _, i2) in zip(old.pages, new.pages):
            res["pages_checked"] += 1
            if i1 != i2 and not any((int(e["page"], 0) if isinstance(e["page"], str) else e["page"]) == o1
                                    for e in names):
                res["errors"].append(f"page {o1:#x} changed without an edit")
    new_index = {}
    for old in chains_old:
        new = by_base.get(old.base)
        if new is None:
            continue
        for (o1, _, _), (o2, _, i2) in zip(old.pages, new.pages):
            new_index[o1] = i2
    for e in names:
        res["names"] += 1
        page = int(e["page"], 0) if isinstance(e["page"], str) else int(e["page"])
        inner = new_index.get(page)
        if inner is not None and (e["new"].encode("latin-1") + b"@") in inner:
            res["names_ok"] += 1
        else:
            res["errors"].append(f"name {e['new']!r} not found with '@' on page {page:#x}")
    # bytes outside the touched chains and tables must be unchanged
    allowed = []
    for old in chains_old:
        allowed.append((old.base, old.slot_end))
        allowed.append((old.toc, old.toc + old.toc_size))
    outside = 0
    step = 1 << 16
    for lo in range(0, len(blob), step):
        a, b = blob_old[lo:lo + step], blob[lo:lo + step]
        if a == b:
            continue
        for i in range(len(a)):
            if a[i] != b[i]:
                x = lo + i
                if not any(s <= x < e for s, e in allowed):
                    outside += 1
    res["outside_changed"] = outside
    if outside:
        res["errors"].append(f"{outside} bytes changed outside chain slots/tables")
    res["ok"] = not res["errors"]
    return res


# ---------------------------------------------------------------------------
# commands


def _require_encoder(args) -> Encoder:
    enc = Encoder(args.libz)
    if not enc.is_reference and not args.allow_nonreference:
        print(f"encoder: {enc.describe()} is not stock zlib {REFERENCE_ZLIB}; refusing "
              "(pass --libz PATH to a stock 1.3.1 libz)", file=sys.stderr)
        raise SystemExit(zlibinfo.EXIT_UNVERIFIABLE)
    return enc


def scan_file(cmp_path: Path, count_streams: bool = False) -> dict:
    blob, *_ = read_pair(cmp_path)
    unresolved: list = []
    chains = find_chains(blob, unresolved)
    name_chains = [c for c in chains if c.pages and all(is_name_page(p[2]) for p in c.pages)]
    walk_ok = sum(1 for c in chains for p in c.pages if walk_records(p[2]) is not None)
    row = {"file": cmp_path.name, "size": len(blob), "chains": len(chains),
           "pages_in_chains": sum(len(c.pages) for c in chains),
           "pages_walk_exact": walk_ok,
           "name_chains": len(name_chains),
           "name_pages": sum(len(c.pages) for c in name_chains),
           "name_records": sum(len(walk_records(p[2]) or []) for c in name_chains for p in c.pages),
           "per_page": sorted(c.per_page for c in chains),
           "unresolved_tables": len(unresolved),
           "name_chain_slack": [c.slot_end - c.end for c in name_chains],
           "name_chain_bytes": [c.end - c.base for c in name_chains],
           "chains_detail": [{"toc": c.toc, "base": c.base, "per_page": c.per_page,
                              "pages": len(c.pages), "end": c.end, "slot_end": c.slot_end}
                             for c in chains]}
    if count_streams:
        streams = list(cmpind_codec.find_zlib_streams(blob, window=WINDOW))
        row["streams"] = len(streams)
        row["stream_bytes"] = sum(c for _, c, _ in streams)
        row["chain_stream_bytes"] = sum(u for c in chains for _, u, _ in c.pages)
    return row


def cmd_scan(args) -> int:
    paths = sorted(Path(args.dir).glob("POINT*.DAT.cmp"))
    if args.jobs > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(args.jobs) as ex:
            rows = list(ex.map(scan_file, paths, [args.streams] * len(paths)))
    else:
        rows = [scan_file(p, args.streams) for p in paths]
    for row in rows:
        extra = (f", streams {row['streams']} ({row['chain_stream_bytes']}/{row['stream_bytes']} B in chains)"
                 if "streams" in row else "")
        print(f"{row['file']}: chains {row['chains']} per_page {row['per_page']} "
              f"({row['pages_in_chains']} pages, {row['pages_walk_exact']} walk exactly), "
              f"name chains {row['name_chains']} ({row['name_pages']} pages, "
              f"{row['name_records']} records, slack {row['name_chain_slack']} B), "
              f"unresolved tables {row['unresolved_tables']}{extra}")
    keys = ["chains", "pages_in_chains", "pages_walk_exact", "name_chains", "name_pages",
            "name_records", "unresolved_tables"]
    tot = {k: sum(r[k] for r in rows) for k in keys}
    tot["files"] = len(rows)
    tot["name_chain_slack"] = sum(sum(r["name_chain_slack"]) for r in rows)
    tot["name_chain_bytes"] = sum(sum(r["name_chain_bytes"]) for r in rows)
    print("total: " + ", ".join(f"{k} {v}" for k, v in tot.items()))
    if args.json:
        Path(args.json).write_text(json.dumps({"files": rows, "total": tot}, indent=1))
    return 0


LOCATOR_UNITS = (1, 2, 4, 0x100, 0x200, 0x800)
LOCATOR_RELS = (0, 0x200, 0x1000)
LOCATOR_FMTS = (">I", "<I", ">H", "<H")


def locator_hits(blob: bytes, targets: dict, window: int) -> set:
    """Encodings ``(target, rel, unit, fmt, pos)`` of each target value in ``blob[:window]``."""
    seen = set()
    for tname, v in targets.items():
        for rel in LOCATOR_RELS:
            for unit in LOCATOR_UNITS:
                x = v - rel
                if x < 0 or x % unit:
                    continue
                x //= unit
                for fmt in LOCATOR_FMTS:
                    if x < 16 or x >= 1 << (8 * struct.calcsize(fmt)):
                        continue
                    pat = struct.pack(fmt, x)
                    i = blob.find(pat, 0, window)
                    while i != -1:
                        seen.add((tname, rel, unit, fmt, i))
                        i = blob.find(pat, i + 1, window)
    return seen


def locator_targets(chains: list[Chain], blob_len: int) -> dict:
    t = {"size": blob_len}
    for c in chains:
        t[f"base{c.per_page}"] = c.base
        t[f"table{c.per_page}"] = c.toc
        t[f"end{c.per_page}"] = c.end
        # positive control: page 0's comp_w is stored at table+8 by definition
        t[f"control_comp0_{c.per_page}"] = c.entries[0][1]
    return t


def cmd_locator(args) -> int:
    """Search one position/encoding that holds a chain base or table in every file."""
    import collections
    counts = collections.Counter()
    nfiles = 0
    control = collections.Counter()
    for cmp_path in sorted(Path(args.dir).glob("POINT*.DAT.cmp")):
        blob, *_ = read_pair(cmp_path)
        chains = find_chains(blob)
        nfiles += 1
        targets = locator_targets(chains, len(blob))
        hits = locator_hits(blob, {k: v for k, v in targets.items()
                                   if not k.startswith("control")}, args.window)
        counts.update(hits)
        for c in chains:
            got = locator_hits(blob, {"c": c.entries[0][1]}, len(blob))
            if any(h[2] == 1 and h[3] == ">I" and h[1] == 0 and h[4] == c.toc + 8 for h in got):
                control[c.per_page] += 1
    best = counts.most_common(args.top)
    print(f"files {nfiles}; window {args.window:#x}; encodings: units {LOCATOR_UNITS}, "
          f"relative to {[hex(r) for r in LOCATOR_RELS]}, {LOCATOR_FMTS}")
    print("positive control (page-0 comp_w found at table+8 as >I): "
          + ", ".join(f"per_page {k}: {v}/{nfiles}" for k, v in sorted(control.items())))
    for key, n in best:
        print(f"{n}/{nfiles} files: target {key[0]} rel {key[1]:#x} unit {key[2]:#x} {key[3]} at {key[4]:#x}")
    found = [k for k, n in best if n == nfiles]
    print("locator:", "FOUND " + str(found) if found else
          f"NOT FOUND (best {best[0][1] if best else 0}/{nfiles} files share a position)")
    return 0


def cmd_summarize(args) -> int:
    """Count fitted/refused regen runs from the ``--json`` files in DIR."""
    rows = []
    for f in sorted(Path(args.dir).glob("*.json")):
        d = json.loads(f.read_text())
        if "refused" in d:
            over = d["refused"].split("new chain ")[1].split(" B")[0] if "new chain " in d["refused"] else "?"
            slot = d["refused"].split("chain slot ")[1].split(" B")[0] if "chain slot " in d["refused"] else "?"
            rows.append((f.stem, "REFUSED", d["names"], f"needs {over} B, slot {slot} B"))
        else:
            v = d["verify"]
            ch = d["chains"][0] if d["chains"] else {}
            rows.append((f.stem, "PASS" if v["ok"] else "FAIL", v["names"],
                         f"names {v['names_ok']}/{v['names']}, slack left {ch.get('slack')} B, "
                         f"outside {v['outside_changed']}"))
    for r in rows:
        print(f"{r[0]}: {r[1]} ({r[3]})")
    n_pass = sum(r[1] == "PASS" for r in rows)
    n_ref = sum(r[1] == "REFUSED" for r in rows)
    n_fail = sum(r[1] == "FAIL" for r in rows)
    print(f"runs {len(rows)}: pass {n_pass}, refused {n_ref}, fail {n_fail}")
    return 1 if n_fail else 0


def cmd_regen(args) -> int:
    enc = _require_encoder(args)
    print(f"encoder: zlib {enc.version} via {enc.source}")
    cmp_path = Path(args.cmp)
    blob, packed, offsets, usize, chunk = read_pair(cmp_path)
    chains = find_chains(blob)
    name_chains = [c for c in chains if any(is_name_page(p[2]) for p in c.pages)]
    if args.names:
        names = json.loads(Path(args.names).read_text())
    elif args.generate:
        names = plan_names(blob, name_chains, args.generate, args.grow)
    elif args.permute:
        names = plan_permuted(blob, name_chains, args.permute)
    else:
        names = []
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = cmp_path.name
    if args.noop:
        # control: regenerate every name chain with its own names
        for ch in name_chains:
            if check_factory_encoder(blob, ch, enc):
                print(f"REFUSED: chain {ch.base:#x}: encoder does not reproduce the factory pages")
                return 1
        new = bytearray(blob)
        reps = []
        for ch in name_chains:
            olds = [blob[o:o + u] for o, u, _ in ch.pages]
            inners = [enc_roundtrip(enc, blob, ch, i) for i in range(len(ch.pages))]
            reps.append(regen_chain(new, ch, inners, enc, olds, force=True))
        blob_new = bytes(new)
    else:
        try:
            blob_new, reps = regen_blob(blob, names, enc, chains)
        except RegenError as exc:
            print(f"REFUSED: {exc}")
            if args.json:
                Path(args.json).write_text(json.dumps({"refused": str(exc), "names": len(names)}))
            return 1
    if args.reencode_outer:
        cmp_new, offs_new = cmpind_codec.encode_chunks(blob_new, chunk, compress=enc.compress)
        ind_new = cmpind_codec.build_ind(usize, len(cmp_new), chunk, offs_new)
    else:
        cmp_new, ind_new = write_pair(packed, offsets, usize, chunk, blob, blob_new, enc)
    (outdir / stem).write_bytes(cmp_new)
    (outdir / stem.replace(".cmp", ".ind")).write_bytes(ind_new)
    if names:
        (outdir / (stem + ".names.json")).write_text(json.dumps(names, indent=1))
    ver = verify_pair(outdir / stem, names, blob, [c for c in chains if c.base in {r["base"] for r in reps}])
    summary = {"file": stem, "encoder": enc.describe(), "names": len(names), "chains": reps,
               "verify": ver, "blob_identical": blob_new == blob,
               "cmp_identical": cmp_new == packed,
               "ind_identical": ind_new == cmpind_codec.pair_paths(cmp_path)[1].read_bytes(),
               "sha256_cmp": hashlib.sha256(cmp_new).hexdigest()}
    for r in reps:
        print(f"chain {r['base']:#x} table {r['toc']:#x}: {r['pages']} pages, "
              f"{r['old_bytes']} -> {r['new_bytes']} B, slot {r['slot']} B, slack {r['slack']} B, "
              f"table entries changed {r['entries_changed']}")
    print(f"names {ver['names_ok']}/{ver['names']} present with '@'; pages checked "
          f"{ver['pages_checked']}; bytes changed outside slots/tables {ver['outside_changed']}")
    print(f"blob identical {summary['blob_identical']}, .cmp identical {summary['cmp_identical']}, "
          f".ind identical {summary['ind_identical']}")
    if args.json:
        Path(args.json).write_text(json.dumps(summary, indent=1))
    print("verify:", "PASS" if ver["ok"] else "FAIL " + "; ".join(ver["errors"][:5]))
    return 0 if ver["ok"] else 1


def enc_roundtrip(enc: Encoder, blob: bytes, ch: Chain, i: int) -> bytes:
    """Inflate page *i* again from the factory stream (no record byte is invented)."""
    off, used, _ = ch.pages[i]
    return zlib.decompress(blob[off:off + used])


def cmd_verify(args) -> int:
    blob, *_ = read_pair(Path(args.factory))
    chains = find_chains(blob)
    names = json.loads(Path(args.names).read_text()) if args.names else []
    pages = {int(e["page"], 0) for e in names}
    touched = [c for c in chains if any(o in pages for o, _, _ in c.pages)]
    res = verify_pair(Path(args.built), names, blob, touched)
    print(json.dumps({k: v for k, v in res.items() if k != "errors"}))
    for e in res["errors"][:20]:
        print("error:", e)
    print("verify:", "PASS" if res["ok"] else "FAIL")
    return 0 if res["ok"] else 1


# ---------------------------------------------------------------------------
# self-test (synthetic, no vendor bytes)


def _synth_record(name: bytes, body: bytes = b"\x11" * 44) -> bytes:
    payload = body + name + b"@MAIN STREET\x00"
    if (2 + len(payload) + 2) % 2:
        payload += b"\x00"
    total = 2 + len(payload) + 2
    return bytes([0x60, total // 2]) + payload + b"\xff\xff"


def synth_blob(enc: Encoder, names_per_page=(6, 5, 7), extra_slack: int = 0x40,
               seed: int = 1) -> tuple[bytes, dict]:
    """Factory-like decoded POINT ``.DAT``: header, a name chain, its table, a tail."""
    import random
    rnd = random.Random(seed)
    pages = []
    k = 0
    for n in names_per_page:
        recs = b""
        for _ in range(n):
            nm = ("POI %03d " % k).encode() + bytes(rnd.choice(b"ABCDEFGHKLMNOPRSTUWZ")
                                                   for _ in range(rnd.randrange(4, 16)))
            if len(nm) % 2:
                nm += b"X"
            recs += _synth_record(nm, bytes(rnd.randrange(256) for _ in range(44)))
            k += 1
        pages.append(recs)
    hdr = bytearray(b"\xff" * 0x200)
    hdr[0:14] = "CLARION".encode("utf-16-be")
    base = 0x1000
    body = bytearray()
    entries = []
    for inner in pages:
        st = enc.compress(inner)
        comp = (len(st) + 3) // 4 * 4
        entries.append((len(body) // 2, comp // 2, len(inner) // 2))
        body += st + bytes(comp - len(st))
    toc_off = (base + len(body) + extra_slack + 0xff) // 0x100 * 0x100
    blob = bytearray(hdr + bytes(base - 0x200))
    blob += body
    blob += bytes(toc_off - len(blob))
    blob += struct.pack(">HH", 1000, 0) + b"".join(struct.pack(">III", *e) for e in entries)
    blob += bytes((-len(blob)) % 0x100)
    blob += b"\xffTAIL-STRUCTURE\xff" * 8  # non-zero neighbour after the table
    return bytes(blob), {"base": base, "toc": toc_off, "pages": pages}


def _pair_from_blob(blob: bytes, enc: Encoder, chunk: int = 0x1000):
    packed, offsets = cmpind_codec.encode_chunks(blob, chunk, compress=enc.compress)
    ind = cmpind_codec.build_ind(len(blob), len(packed), chunk, offsets)
    return packed, ind


def selftest() -> int:
    import tempfile
    checks = 0
    enc = Encoder(None)

    def ok(cond, msg):
        nonlocal checks
        if not cond:
            raise AssertionError(msg)
        checks += 1

    blob, meta = synth_blob(enc)
    chains = find_chains(blob)
    ok(len(chains) == 1 and chains[0].base == meta["base"] and chains[0].toc == meta["toc"],
       "chain table located at its base")
    ch = chains[0]
    ok([p[2] for p in ch.pages] == meta["pages"], "pages read back from the table")
    ok(ch.slot_end > ch.end, "synthetic chain has slack before the table")
    ok(parse_toc(blob, meta["toc"] + 0x100) is None, "no table where there is none")

    # negative control: a table whose start_w chain is broken is not a table
    bad = bytearray(blob)
    struct.pack_into(">I", bad, meta["toc"] + 4 + 12, 7)
    ok(len(parse_toc(bytes(bad), meta["toc"]).entries) == 1, "broken start_w stops the table")

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        packed, ind = _pair_from_blob(blob, enc)
        (td / "POINT099.DAT.cmp").write_bytes(packed)
        (td / "POINT099.DAT.ind").write_bytes(ind)

        # control: no-op regeneration -> byte-identical blob and pair
        b0, packed0, offs0, us0, ch0 = read_pair(td / "POINT099.DAT.cmp")
        new = bytearray(b0)
        olds = [b0[o:o + u] for o, u, _ in ch.pages]
        regen_chain(new, ch, [zlib.decompress(s) for s in olds], enc, olds, force=True)
        ok(bytes(new) == b0, "no-op regeneration is byte-identical (no invented bytes)")
        c2, i2 = write_pair(packed0, offs0, us0, ch0, b0, bytes(new), enc)
        ok(c2 == packed and i2 == ind, "no-op pair is byte-identical")

        # growth beyond each page slot, inside the pooled chain slot
        plan = plan_names(blob, chains, 9, grow=2)
        ok(len(plan) == 9, "nine names planned")
        blob2, reps = regen_blob(blob, plan, enc, chains)
        ok(reps[0]["new_bytes"] > reps[0]["old_bytes"], "chain grew")
        ok(any(len(enc.compress(apply_names(inner, [e for e in plan if int(e["page"], 0) == o])))
               > (ch.entries[i][1] * 2) for i, (o, u, inner) in enumerate(ch.pages)), "a page outgrew its own slot")
        c3, i3 = write_pair(packed0, offs0, us0, ch0, b0, blob2, enc)
        out = td / "out"
        out.mkdir()
        (out / "POINT099.DAT.cmp").write_bytes(c3)
        (out / "POINT099.DAT.ind").write_bytes(i3)
        import cmpind
        dec_blob, _ = cmpind.decode(out / "POINT099.DAT.cmp", out / "POINT099.DAT.ind")
        ok(dec_blob == blob2, "cmpind decodes the rebuilt pair")
        ver = verify_pair(out / "POINT099.DAT.cmp", plan, blob, chains)
        ok(ver["ok"] and ver["names_ok"] == 9, "all nine names present with '@', tables consistent")
        # negative control: a rebuilt pair with one table word broken fails verify
        bad2 = bytearray(blob2)
        struct.pack_into(">I", bad2, meta["toc"] + 4 + 12 + 4, 1)
        c4, i4 = write_pair(packed0, offs0, us0, ch0, b0, bytes(bad2), enc)
        (out / "POINT099.DAT.cmp").write_bytes(c4)
        (out / "POINT099.DAT.ind").write_bytes(i4)
        ok(not verify_pair(out / "POINT099.DAT.cmp", plan, blob, chains)["ok"],
           "verify fails on a broken chain table")
        # negative control: a name missing from the rebuilt pair fails verify
        (out / "POINT099.DAT.cmp").write_bytes(c3)
        (out / "POINT099.DAT.ind").write_bytes(i3)
        fake = [dict(plan[0], new="NEVER WRITTEN")]
        ok(not verify_pair(out / "POINT099.DAT.cmp", plan + fake, blob, chains)["ok"],
           "verify fails on a name that is not in the pair")
        ch2 = find_chains(blob2)[0]
        ok(all(is_name_page(p[2]) for p in ch2.pages), "regenerated pages parse as record chains")
        ok(ch2.toc == ch.toc and ch2.base == ch.base, "chain base and table did not move")

        # refusal 1: chain slot exceeded
        bigplan = [dict(e, new="".join(chr(65 + b % 26) for b in hashlib.sha256(
                    e["old"].encode()).digest() * 2)[:len(e["old"]) + 40])
                   for e in plan_names(blob, chains, 18, grow=0)]
        try:
            regen_blob(blob, bigplan, enc, chains)
            ok(False, "oversized chain refused")
        except RegenError as exc:
            ok("chain slot" in str(exc), "oversized chain refused with the slot named")
        # refusal 2: odd record size
        odd = [dict(plan[0], new=plan[0]["old"] + "Y")]
        try:
            regen_blob(blob, odd, enc, chains)
            ok(False, "odd record refused")
        except RegenError as exc:
            ok("odd" in str(exc) or "even" in str(exc), "odd-sized record refused")
        # refusal 3: wrong old text / no '@'
        try:
            regen_blob(blob, [dict(plan[0], old="NOT THERE")], enc, chains)
            ok(False, "missing name refused")
        except RegenError:
            ok(True, "")
        # refusal 4: page not in any table
        try:
            regen_blob(blob, [dict(plan[0], page=hex(meta["base"] + 1))], enc, chains)
            ok(False, "page outside tables refused")
        except RegenError as exc:
            ok("no located chain table" in str(exc), "page outside every table refused")
        # refusal 5: encoder that does not reproduce the factory pages
        class Wrong(Encoder):
            def compress(self, data):
                return zlib.compress(data, 1)
        try:
            regen_blob(blob, plan, Wrong(None), chains)
            ok(False, "non-factory encoder refused")
        except RegenError as exc:
            ok("does not reproduce" in str(exc), "non-factory encoder refused")

    print(f"point_pair_regen selftest: {checks} checks OK "
          f"(encoder zlib {enc.version}; byte-identity uses this runtime)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("scan", help="locate and verify chain tables in POINT*.DAT.cmp of DIR")
    p.add_argument("dir")
    p.add_argument("--json")
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--streams", action="store_true", help="also count every inner zlib stream (slow)")
    p = sub.add_parser("locator", help="search the chain-base/table locator in DIR (negative so far)")
    p.add_argument("dir")
    p.add_argument("--window", type=lambda x: int(x, 0), default=0x8000)
    p.add_argument("--top", type=int, default=8)
    p = sub.add_parser("summarize", help="count PASS/REFUSED regen --json results in DIR")
    p.add_argument("dir")
    p = sub.add_parser("regen", help="regenerate the chains of one pair")
    p.add_argument("cmp")
    p.add_argument("outdir")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--names", help="JSON name set")
    g.add_argument("--noop", action="store_true", help="control: regenerate with the factory names")
    g.add_argument("--generate", type=int, help="plan N OSM-like names on name pages")
    g.add_argument("--permute", type=int,
                   help="plan N names: real factory names moved to other sites (varied lengths)")
    p.add_argument("--grow", type=int, default=0, help="bytes added to each generated name (even)")
    p.add_argument("--libz", help="stock zlib shared library to compress with (ctypes)")
    p.add_argument("--allow-nonreference", action="store_true",
                   help="accept a stock zlib other than 1.3.1 (the factory check still runs)")
    p.add_argument("--reencode-outer", action="store_true",
                   help="deflate every outer 64 KiB chunk (default keeps unchanged chunks verbatim)")
    p.add_argument("--json")
    p = sub.add_parser("verify", help="check a rebuilt pair against the factory pair and a name set")
    p.add_argument("factory")
    p.add_argument("built")
    p.add_argument("--names")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "scan":
        return cmd_scan(args)
    if args.cmd == "regen":
        return cmd_regen(args)
    if args.cmd == "summarize":
        return cmd_summarize(args)
    if args.cmd == "locator":
        return cmd_locator(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
