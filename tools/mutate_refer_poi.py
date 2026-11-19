#!/usr/bin/env python3
"""In-place name mutation for a REFER001 ``.cmp``/``.ind`` pair.

Design constraints (see docs/research/minimal-change.md):

  * the logical ``.DAT`` size is unchanged, so ``DRSTR001.DAT`` needs no
    update;
  * the inner zlib page keeps its absolute offset, so every pointer table
    entry that references it stays valid;
  * by default the replacement text has exactly the same byte length, so no
    offset or length field inside the name page changes.

``--resize`` additionally understands the POINT name-page framing
(docs/format/refer.md).  Such a page is a chain of self-describing records:

    u8 tag (0x60 | 0x68) | u8 len2 | body | text | ff ff

The record size is ``2*len2`` bytes, records are packed without gaps, and the
display text is the printable suffix before the final ``ff ff``.  There is no
offset table in the page: record *n+1* starts at ``record_n.offset +
2*record_n.len2``.  A name of a different length changes the record size, so
``len2`` is patched and the rest of the page shifts.  The ``.DAT`` logical
size and the page offset still do not change; only the compressed page may
grow, and the tool refuses if it would cross the next page boundary.

The firmware does not find the name through that framing (M3.11c, C-5115):
its accessor takes the field area of the record (header class ``w>>13`` 3 or
2: ``rec + 2*(hi+lo+8)`` of ``u16[rec+10]``), which starts with one length
byte per field in 16-bit words, and field *f* starts after the
``(n+1)/2``-word length table plus the lengths of fields ``0..f-1`` (``n`` =
9 fields in the POINT dictionary, C-5114).  The name is field 5.  So
``--resize`` (M5.52) also patches the field-5 length byte, requires the old
text to lie inside field 5, and refuses a delta that is not a whole number of
words or a record whose field area it cannot place.

Only these bytes change: the name text, the record length byte and the
field-5 length byte (``--resize``),
the inner zlib stream (recompressed, zero-padded back to the page boundary),
and the outer chunk that holds that page.  By default (M9.43) the outer
container is rebuilt chunk-preservingly: ``cmpind_codec.repack_changed_chunks``
keeps every unchanged 64 KiB stream byte-verbatim and recompresses only the
chunk the inner page lives in, so one outer stream differs instead of all of
them.  ``--whole-blob`` keeps the old behaviour (every outer stream recompressed
at factory parameters), which the M5.12c copy/round-trip scans rely on.

Usage:
  python3 mutate_refer_poi.py CMP IND OUTDIR --page 0x4200 \
      --old "VATICAN MUSEUM" --new "OSM2LEAF PROBE"
  python3 mutate_refer_poi.py CMP IND OUTDIR --page 0x4200 --resize \
      --old "VATICAN MUSEUM" --new "OSM2LEAF PROBE POI"
  python3 mutate_refer_poi.py CMP IND OUTDIR --page 0x4200 --batch EDITS.json
  python3 mutate_refer_poi.py CMP IND OUTDIR --page 0x4200 --old A --new B --whole-blob
  python3 mutate_refer_poi.py --selftest

``--batch`` takes a JSON list of pages, each with same-length edits::

  [{"page": 8649488, "edits": [{"at": 94, "old": "HANA HEALTH CENTER",
                                 "new": "OSM2LEAF TEST POI1"}]}]

``at`` is the offset of ``old`` inside the inner page. Every edit must match
the bytes there and be followed by ``@`` (a POI name, not an address part).
Each edited page must still parse as a record chain. The file is decoded once,
all pages are rewritten, and the pair is encoded once.

Reconciled entrypoint (M5.25): performs same-length and refit edits with the
M5.21 slot budget (``--headroom``, default ``slot_budget.HEADROOM_RATIO`` for
batch / ``0.0`` for single edits to preserve existing CLI behavior), uses
factory zlib params from M1.13/M1.16, refuses pages that cannot fit and reports
every refused page. "Find every copy" of a name (M5.12c goal, blocked on the
uncompressed-files scan — M5.27) is served by ``tools/poi_copies.py``; once
M5.12c unblocks, run it with ``--inner`` to report copies.
"""

from __future__ import annotations

import argparse
import json
import sys
import zlib
from pathlib import Path

# Shared codec (M1.16): factory params, container, inner-page primitives.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmpind_codec  # noqa: E402
import slot_budget  # noqa: E402

CHUNK = cmpind_codec.CHUNK
PAGE_ALIGN = cmpind_codec.PAGE_ALIGN
#: First byte of a POINT name record.  Other POINT pages are a different
#: (bit-packed) page type and start ``00 xx 00 yy``.
RECORD_TAGS = (0x60, 0x68)
#: Every record ends with this marker, after its display text.
RECORD_TERMINATOR = b"\xff\xff"
MAX_RECORD = 2 * 0xFF
#: Fields in the POINT field dictionary (C-5114); the name is field 5 and the
#: address field 6 (C-5112).
POINT_FIELDS = 9
NAME_FIELD = 5
#: Header classes ``u16[rec] >> 13`` whose field area ``fn 0x003f56bc``
#: (EU2011) places from ``u16[rec+10]`` (C-5115).
PLACEABLE_CLASSES = (2, 3)


class PageError(ValueError):
    """The page is not the record chain this tool understands."""


class FitError(PageError):
    """The edited page does not fit its slot minus headroom."""

    def __init__(self, message: str, row: dict | None = None):
        super().__init__(message)
        self.row = row if row is not None else {"decision": "refuse", "reason": message}


# ---------------------------------------------------------------------------
# page record framing


def parse_page(inner: bytes) -> list[dict]:
    """Split a POINT name page into ``tag,len2`` records.

    Raises :class:`PageError` when the page is not a clean record chain
    (different page type, truncated record, missing ``ff ff`` terminator).
    """
    if not inner:
        raise PageError("empty page")
    records: list[dict] = []
    pos = 0
    while pos < len(inner):
        if pos + 2 > len(inner):
            raise PageError(f"truncated record header at {pos:#x}")
        tag = inner[pos]
        len2 = inner[pos + 1]
        total = len2 * 2
        if tag not in RECORD_TAGS:
            raise PageError(
                f"unexpected record tag {tag:#04x} at {pos:#x} "
                f"(expected 0x60/0x68; this page is not a name page)"
            )
        if total < 4:
            raise PageError(f"record at {pos:#x} has impossible size {total}")
        if pos + total > len(inner):
            raise PageError(
                f"record at {pos:#x} runs past the page "
                f"({pos:#x} + {total} > {len(inner)})"
            )
        end = pos + total
        if inner[end - 2 : end] != RECORD_TERMINATOR:
            raise PageError(f"record at {pos:#x} does not end with ff ff")
        records.append(
            {
                "offset": pos,
                "tag": tag,
                "len2": len2,
                "total": total,
                "bytes": inner[pos:end],
            }
        )
        pos = end
    return records


def record_at(records: list[dict], offset: int) -> dict | None:
    for record in records:
        if record["offset"] <= offset < record["offset"] + record["total"]:
            return record
    return None


def field_layout(rec: bytes, nfields: int = POINT_FIELDS) -> dict:
    """Place a record's fields the way the firmware accessor does (C-5115).

    ``rec`` is one record in file order (big-endian u16, the native order the
    walker sees after the swap).  ``fn 0x003f56bc`` (EU2011; reached from the
    US2011 accessor ``0x0041ec8c`` the same way) takes the field area from the
    header class ``w >> 13`` of ``w = u16[rec]``: 3 or 2 → ``rec + 2*(hi+lo+8)``
    of ``u16[rec+10]``.  ``fn 0x003f5e10`` reads ``(n+1)/2`` words of
    byte-sized lengths (high byte = even field), so field *f*'s length is the
    file byte ``loc + f`` and its data starts at
    ``loc + 2*((n+1)/2 + sum(len[0..f-1]))``.

    Raises :class:`PageError` for a class it cannot place (escape records
    ``w & 0xfc00 == 0xfc00`` and classes 0/5/6 are read differently) or a
    field area that does not fit the record.
    """
    if len(rec) < 12:
        raise PageError(f"record of {len(rec)} bytes has no u16[rec+10]")
    w = (rec[0] << 8) | rec[1]
    cls = w >> 13
    if w & 0xFC00 == 0xFC00 or cls not in PLACEABLE_CLASSES:
        raise PageError(
            f"header class {cls} (u16[rec]={w:#06x}) cannot be placed: only "
            f"classes {PLACEABLE_CLASSES} have the field area at u16[rec+10]"
        )
    w10 = (rec[10] << 8) | rec[11]
    loc = 2 * ((w10 >> 8) + (w10 & 0xFF) + 8)
    table = 2 * ((nfields + 1) // 2)
    if loc + table > len(rec):
        raise PageError(
            f"field area at +{loc:#x} (+{table} B length table) runs past the "
            f"{len(rec)}-byte record"
        )
    lens = list(rec[loc : loc + nfields])
    starts = []
    pos = loc + table
    for words in lens:
        starts.append(pos)
        pos += 2 * words
    return {"class": cls, "loc": loc, "lens": lens, "starts": starts, "end": pos}


def name_field(rec: bytes, nfields: int = POINT_FIELDS) -> tuple[int, int, dict]:
    """``(start, words, layout)`` of field 5 in ``rec``; the fields must
    account for every byte of the record (as on 2000/2000 real records)."""
    layout = field_layout(rec, nfields)
    if layout["end"] != len(rec):
        raise PageError(
            f"field lengths {layout['lens']} end at +{layout['end']:#x}, not at "
            f"the record end +{len(rec):#x}: field area cannot be placed"
        )
    return layout["starts"][NAME_FIELD], layout["lens"][NAME_FIELD], layout


def census(inner: bytes) -> dict:
    """Header classes and placeable records of one name page (M5.52 Stop)."""
    classes: dict[int, int] = {}
    placed = 0
    refused: dict[str, int] = {}
    records = parse_page(inner)
    for rec in records:
        w = (rec["bytes"][0] << 8) | rec["bytes"][1]
        classes[w >> 13] = classes.get(w >> 13, 0) + 1
        try:
            name_field(rec["bytes"])
        except PageError as exc:
            key = str(exc).split(":")[0][:40]
            refused[key] = refused.get(key, 0) + 1
        else:
            placed += 1
    return {"records": len(records), "classes": classes, "placed": placed,
            "refused": refused}


def format_census(c: dict) -> str:
    cls = " ".join(f"class{k}={v}" for k, v in sorted(c["classes"].items()))
    ref = " ".join(f"[{k}]={v}" for k, v in sorted(c["refused"].items())) or "none"
    return (f"records={c['records']} {cls} placed={c['placed']} "
            f"refused={c['records'] - c['placed']} ({ref})")


def verify_resize(
    old_page: bytes, new_page: bytes, info: dict, old: bytes, new: bytes
) -> None:
    """Assert that only the renamed record changed and the chain still parses.

    In the renamed record, every field other than 5 must keep its length and
    bytes, the field-5 length byte must hold the new word count, and field 5
    must contain the new text (M5.52).
    """
    old_records = parse_page(old_page)
    new_records = parse_page(new_page)
    if len(old_records) != len(new_records):
        raise PageError(
            f"record count changed {len(old_records)} -> {len(new_records)}"
        )
    index = info["index"]
    if new_records[index]["total"] != info["new_total"]:
        raise PageError("record length byte does not match the new record size")
    if old not in old_records[index]["bytes"]:
        raise PageError("old text is not in the selected record")
    if new not in new_records[index]["bytes"]:
        raise PageError("new text is not in the renamed record")
    before_rec = old_records[index]["bytes"]
    after_rec = new_records[index]["bytes"]
    _s0, _w0, lay0 = name_field(before_rec)
    s1, w1, lay1 = name_field(after_rec)
    if w1 != info["new_name_words"]:
        raise PageError(
            f"field-5 length byte is {w1} words, expected {info['new_name_words']}"
        )
    if new not in after_rec[s1 : s1 + 2 * w1]:
        raise PageError("new text is not inside field 5 of the renamed record")
    if lay0["loc"] != lay1["loc"] or before_rec[2 : lay0["loc"]] != after_rec[2 : lay1["loc"]]:
        raise PageError("record header changed outside the length byte")
    for f in range(len(lay0["lens"])):
        if f == NAME_FIELD:
            continue
        a = before_rec[lay0["starts"][f] : lay0["starts"][f] + 2 * lay0["lens"][f]]
        b = after_rec[lay1["starts"][f] : lay1["starts"][f] + 2 * lay1["lens"][f]]
        if lay0["lens"][f] != lay1["lens"][f] or a != b:
            raise PageError(f"field {f} of the renamed record changed")
    for other, (before, after) in enumerate(zip(old_records, new_records)):
        if other == index:
            continue
        if before["bytes"] != after["bytes"]:
            raise PageError(f"record {other} at {before['offset']:#x} changed")
    if len(new_page) != len(old_page) + info["delta"]:
        raise PageError("page length does not match the name delta")


def resize_name(inner: bytes, old: bytes, new: bytes) -> tuple[bytes, dict]:
    """Replace ``old`` with ``new`` in a record page, fixing both length bytes.

    ``new`` may differ in length from ``old`` by a whole number of 16-bit
    words.  ``old`` must lie inside the record's field 5 (the name, as the
    firmware accessor places it).  The record length byte ``len2`` and the
    field-5 length byte (in words, C-5115) are patched; nothing else in the
    record moves except the bytes after the name.
    """
    if not old or not new:
        raise PageError("old and new text must be non-empty")
    if b"\x00" in new:
        raise PageError("replacement text must not contain NUL")
    if inner.count(old) != 1:
        raise PageError(f"{inner.count(old)} occurrences of {old!r}; need exactly 1")
    hit = inner.find(old)
    records = parse_page(inner)
    record = record_at(records, hit)
    if record is None:
        raise PageError(f"replacement at {hit:#x} is outside every record")
    if hit < record["offset"] + 2:
        raise PageError("replacement starts inside the record header")
    delta = len(new) - len(old)
    if delta % 2:
        raise PageError(
            f"name delta {delta:+d} bytes is odd: the record length and the "
            "field-5 length are counted in 16-bit words, so change the name by "
            "a whole number of words (an even number of bytes)"
        )
    new_total = record["total"] + delta
    if not 4 <= new_total <= MAX_RECORD:
        raise PageError(
            f"record {record['offset']:#x} would be {new_total} bytes, "
            f"outside 4..{MAX_RECORD}"
        )
    start, words, layout = name_field(record["bytes"])
    rel = hit - record["offset"]
    if not (start <= rel and rel + len(old) <= start + 2 * words):
        raise PageError(
            f"{old!r} at record +{rel:#x} is not inside field 5 "
            f"(+{start:#x}..+{start + 2 * words:#x}, {words} words); "
            "--resize renames only the name field"
        )
    new_words = words + delta // 2
    if not 1 <= new_words <= 0xFF:
        raise PageError(f"field 5 would be {new_words} words, outside 1..255")
    len_at = record["offset"] + layout["loc"] + NAME_FIELD
    new_len2 = new_total // 2
    out = bytearray(inner[:hit] + new + inner[hit + len(old) :])
    # both length bytes lie before the name, so the splice did not move them
    out[record["offset"] + 1] = new_len2
    out[len_at] = new_words
    new_inner = bytes(out)
    info = {
        "index": records.index(record),
        "record_offset": record["offset"],
        "old_total": record["total"],
        "new_total": new_total,
        "old_len2": record["len2"],
        "new_len2": new_len2,
        "name_len_offset": len_at,
        "old_name_words": words,
        "new_name_words": new_words,
        "delta": delta,
        "records": len(records),
    }
    verify_resize(inner, new_inner, info, old, new)
    return new_inner, info


# ---------------------------------------------------------------------------
# container helpers (shared codec M1.16; signatures kept for factory_zlib/callers)


def read_ind(path: Path):
    usize, csize, count, chunk_size, offsets = cmpind_codec.read_ind(path)
    return usize, csize, count, chunk_size, list(offsets)


def decode(cmp_bytes: bytes, offsets: list[int]) -> bytes:
    return cmpind_codec.decode_blob(cmp_bytes, offsets, strict_nonfinal=False)


def encode(blob: bytes, chunk_size: int):
    return cmpind_codec.encode_chunks(blob, chunk_size, compress=cmpind_codec.factory_compress)


def encode_preserving(packed: bytes, offsets: list[int], blob_old: bytes,
                      blob_new: bytes, usize: int, chunk_size: int):
    """Rebuild the outer container keeping unchanged outer streams verbatim.

    M9.43: this is the chunk-preserving path (``cmpind_codec.
    repack_changed_chunks``) so an edit that touches one inner page changes one
    outer 64 KiB stream, not all of them.  Returns ``(cmp_bytes, offsets)``.

    The chunk that holds the edited page is freshly deflated, so unless the
    host's zlib reproduces the factory stream it will differ byte-wise from the
    factory chunk; the other streams are byte-verbatim copies.
    """
    return cmpind_codec.repack_changed_chunks(
        packed, offsets, usize, chunk_size, blob_old, blob_new,
        compress=cmpind_codec.factory_compress,
    )


def build_ind(usize: int, csize: int, chunk_size: int, offsets: list[int]) -> bytes:
    return cmpind_codec.build_ind(usize, csize, chunk_size, offsets)


def _outer_stream(packed: bytes, offsets: list[int], i: int) -> bytes:
    end = offsets[i + 1] if i + 1 < len(offsets) else len(packed)
    return packed[offsets[i]:end]


def _changed_chunks(blob_old: bytes, blob_new: bytes, chunk_size: int) -> list[int]:
    """Outer-chunk indexes whose logical 64 KiB payload differs."""
    return [
        i
        for i in range((len(blob_old) + chunk_size - 1) // chunk_size)
        if blob_old[i * chunk_size:(i + 1) * chunk_size]
        != blob_new[i * chunk_size:(i + 1) * chunk_size]
    ]


# ---------------------------------------------------------------------------
# self-test (synthetic page, no vendor data)


def _synth_record(tag: int, name: bytes, addr: bytes, w10: int = 0) -> bytes:
    """A record with the real field layout (C-5115): 12-byte header whose
    ``u16[+10]`` places the field area, 9 length bytes (+1 pad), fields 0..2,
    field 5 (name), field 6 (address) and field 8 = the ``ff ff`` terminator."""
    if len(name) % 2 or len(addr) % 2:
        raise AssertionError("synthetic fields must be whole words")
    loc = 2 * ((w10 >> 8) + (w10 & 0xFF) + 8)
    head = bytes([tag, 0]) + bytes.fromhex("9f6fd43e0c76046a") + w10.to_bytes(2, "big")
    head += b"\x00" * (loc - len(head))
    fields = [b"\x01\x02\x03\x04\x05\x06\x07\x08", b"\x00\x09", b"\xff\xff",
              b"", b"", name, addr, b"", RECORD_TERMINATOR]
    table = bytes(len(f) // 2 for f in fields) + b"\x00"
    rec = bytearray(head + table + b"".join(fields))
    if len(rec) > MAX_RECORD:
        raise AssertionError("synthetic record too large")
    rec[1] = len(rec) // 2
    return bytes(rec)


def selftest() -> int:
    page = b"".join(
        [
            _synth_record(0x60, b"ALPHA MUSEUM", b"1@VIA ONE\x00"),
            _synth_record(0x68, b"BETA MUSEUMS", b"@VIA TWO", w10=0x0102),
            _synth_record(0x60, b"GAMMA\x00", b"@VIA THREE\x00\x00"),
        ]
    )
    checks = 0

    records = parse_page(page)
    assert len(records) == 3
    assert records[0]["offset"] == 0
    assert records[1]["offset"] == records[0]["total"]
    assert records[2]["offset"] == records[1]["offset"] + records[1]["total"]
    checks += 1

    # the firmware layout: field 5 is the name, field 6 the address (C-5115)
    for rec, name, addr in zip(records, (b"ALPHA MUSEUM", b"BETA MUSEUMS", b"GAMMA\x00"),
                               (b"1@VIA ONE\x00", b"@VIA TWO", b"@VIA THREE\x00\x00")):
        start, words, lay = name_field(rec["bytes"])
        assert rec["bytes"][start:start + 2 * words] == name
        s6 = lay["starts"][6]
        assert rec["bytes"][s6:s6 + 2 * lay["lens"][6]] == addr
    assert field_layout(records[1]["bytes"])["loc"] == 2 * (1 + 2 + 8)
    checks += 1

    def name_of(pg: bytes, i: int) -> bytes:
        rec = parse_page(pg)[i]["bytes"]
        start, words, _lay = name_field(rec)
        return rec[start:start + 2 * words]

    def addr_of(pg: bytes, i: int) -> bytes:
        lay = field_layout(parse_page(pg)[i]["bytes"])
        rec = parse_page(pg)[i]["bytes"]
        return rec[lay["starts"][6]:lay["starts"][6] + 2 * lay["lens"][6]]

    # same-length rename keeps the page size and every length byte
    same, info = resize_name(page, b"ALPHA MUSEUM", b"ALPHA MUSEU?")
    assert len(same) == len(page)
    assert info["delta"] == 0
    assert parse_page(same)[0]["len2"] == records[0]["len2"]
    assert info["old_name_words"] == info["new_name_words"] == 6
    assert name_of(same, 0) == b"ALPHA MUSEU?"
    checks += 1

    # +4 bytes: len2 and the field-5 length both grow by 2 words, the
    # address is read unchanged after the longer name
    grown, info = resize_name(page, b"ALPHA MUSEUM", b"ALPHA MUSEUM TWO")
    assert len(grown) == len(page) + 4
    assert info["delta"] == 4
    assert info["new_len2"] == records[0]["len2"] + 2
    assert info["new_name_words"] == info["old_name_words"] + 2
    assert name_of(grown, 0) == b"ALPHA MUSEUM TWO"
    assert addr_of(grown, 0) == b"1@VIA ONE\x00"
    after = parse_page(grown)
    assert len(after) == 3
    assert after[1]["bytes"] == records[1]["bytes"]
    assert after[2]["bytes"] == records[2]["bytes"]
    checks += 1

    # -2 bytes on the middle record (header class 3 with w10 != 0)
    short, info = resize_name(page, b"BETA MUSEUMS", b"BETA MUSEU")
    assert len(short) == len(page) - 2
    assert info["delta"] == -2
    assert info["new_name_words"] == 5
    assert name_of(short, 1) == b"BETA MUSEU" and addr_of(short, 1) == b"@VIA TWO"
    assert len(parse_page(short)) == 3
    checks += 1

    # the defect M5.52 fixes: patching only len2 leaves field 5 at its old
    # length, so the reader takes the old-length prefix and shifts the rest
    # into the address (C-5117)
    _grown, grown_info = resize_name(page, b"ALPHA MUSEUM", b"ALPHA MUSEUM TWO")
    stale = bytearray(grown)
    stale[grown_info["name_len_offset"]] = 6        # the pre-M5.52 output
    stale_rec = parse_page(bytes(stale))[0]["bytes"]
    slay = field_layout(stale_rec)
    s5, s6 = slay["starts"][5], slay["starts"][6]
    assert stale_rec[s5:s5 + 2 * slay["lens"][5]] == b"ALPHA MUSEUM"
    assert stale_rec[s6:s6 + 2 * slay["lens"][6]].startswith(b" TWO")
    try:
        name_field(stale_rec)
    except PageError as exc:
        assert "cannot be placed" in str(exc)
    else:
        raise AssertionError("a stale field-5 length was accepted")
    checks += 1

    for bad, message in (
        ((b"ALPHA MUSEUM", b"ALPHA MUSEUMS"), "whole number of words"),
        ((b"NO SUCH NAME", b"NO SUCH NAME"), "occurrences"),
        ((b"ALPHA MUSEUM", b"ALPHA\x00MUSEUM"), "NUL"),
        ((b"VIA ONE", b"VIA ONE!!"), "not inside field 5"),
        ((b"MUSEUM1@", b"MUSEUM2@XX"), "not inside field 5"),
        ((b"GAMMA", b"GAMM"), "whole number of words"),
    ):
        try:
            resize_name(page, *bad)
        except PageError as exc:
            assert message.lower() in str(exc).lower(), (message, exc)
        else:
            raise AssertionError(f"expected PageError for {bad!r}")
    checks += 1

    # records whose field area cannot be placed are refused, not mutated:
    # a header class the accessor reads differently (5 = rec+8, 6, 0, escape
    # 0xfc..), a field area past the record, and field lengths that do not
    # add up to the record size
    for w0, message in ((0xA0, "class 5"), (0xC0, "class 6"), (0x00, "class 0"),
                        (0xFC, "class 7")):
        rec = bytearray(records[0]["bytes"])
        rec[0] = w0
        try:
            field_layout(bytes(rec))
        except PageError as exc:
            assert message in str(exc) and "cannot be placed" in str(exc), exc
        else:
            raise AssertionError(f"class byte {w0:#x} was placed")
    two = bytearray(records[0]["bytes"])
    two[0] = 0x40                       # class 2: placed like class 3
    assert name_field(bytes(two))[1] == 6
    far = bytearray(page)
    far[10] = 0x7F                      # u16[rec+10] puts the field area past rec 0
    lens_off = field_layout(records[0]["bytes"])["loc"] + 6   # field-6 length byte
    off = bytearray(page)
    off[lens_off] += 1                  # lengths no longer end at the record end
    for broken in (bytes(far), bytes(off)):
        try:
            resize_name(broken, b"ALPHA MUSEUM", b"ALPHA MUSEUM TWO")
        except PageError as exc:
            assert "cannot be placed" in str(exc) or "runs past" in str(exc), exc
        else:
            raise AssertionError("an unplaceable record was resized")
    checks += 1

    # a bit-packed page and a truncated page must be rejected, not "mutated"
    for broken in (bytes.fromhex("00020000") * 8, page[:-1]):
        try:
            parse_page(broken)
        except PageError:
            pass
        else:
            raise AssertionError("malformed page was accepted")
    checks += 1

    # census: every synthetic record is class 3 and placeable; a corrupted
    # length byte is counted as refused
    c = census(page)
    assert c == {"records": 3, "classes": {3: 3}, "placed": 3, "refused": {}}, c
    bad_len = bytearray(page)
    bad_len[field_layout(records[0]["bytes"])["loc"] + 5] += 1
    c = census(bytes(bad_len))
    assert c["placed"] == 2 and sum(c["refused"].values()) == 1, c
    assert "placed=2 refused=1" in format_census(c)
    checks += 1

    # batch edits: same-length, followed by '@', framing preserved
    beta_at = page.find(b"BETA MUSEUMS")
    new_inner, applied = edit_inner(page, [
        {"at": beta_at, "old": "BETA MUSEUMS", "new": "OSM2 TEST   "},
    ])
    assert new_inner.find(b"OSM2 TEST   @VIA TWO") > 0 and len(new_inner) == len(page)
    assert len(parse_page(new_inner)) == 3
    checks += 1
    alpha_at = page.find(b"ALPHA MUSEUM")  # followed by '1', not '@': refused
    for bad in (
        {"at": beta_at, "old": "BETA MUSEUMS", "new": "SHORT"},
        {"at": beta_at + 1, "old": "BETA MUSEUMS", "new": "OSM2 TEST   "},
        {"at": alpha_at, "old": "ALPHA MUSEUM", "new": "OSM2 TEST   "},
    ):
        try:
            edit_inner(page, [bad])
        except PageError:
            pass
        else:
            raise AssertionError(f"batch edit accepted: {bad!r}")
    checks += 1

    # M5.25: synthetic fitting refit and over-budget refusal (M5.21 budget).
    stream = cmpind_codec.factory_compress(page)
    consumed = len(stream)
    slot = (consumed + PAGE_ALIGN - 1) & ~(PAGE_ALIGN - 1)
    blob = bytearray(stream + b"\x00" * (slot - consumed) + b"\x99" * 0x80)
    before = bytes(blob)
    edited, _applied = edit_inner(page, [
        {"at": beta_at, "old": "BETA MUSEUMS", "new": "OSM2 TEST   "},
    ])
    new_blob, row = refit_page_budget(bytes(blob), 0, edited, headroom_ratio=0.0)
    assert row["decision"] == "fit"
    assert new_blob[slot:] == before[slot:], "fitting refit touched bytes outside slot"
    assert b"OSM2 TEST   @VIA TWO" in zlib.decompress(new_blob[:row["new_stream"]])
    checks += 1
    try:
        refit_page_budget(bytes(blob), 0, edited, headroom_ratio=10.0)
        raise AssertionError("over-budget refusal was accepted")
    except FitError as exc:
        assert bytes(blob) == before, "refusal mutated the blob"
        assert getattr(exc, "row", None) is not None or "limit" in str(exc).lower() or "slot" in str(exc).lower() or "stream" in str(exc).lower()
    checks += 1

    # M9.43: the chunk-preserving rebuild changes only the outer stream(s)
    # that hold a changed logical chunk, and keeps every other stream verbatim.
    chunk = 0x40
    logical = (
        b"A" * 20 + b"old-name" + b"@road\0" + b"." * (chunk - 34)
        + b"B" * chunk
        + b"C" * chunk
        + b"\x00" * chunk
    )
    assert len(logical) == 4 * chunk
    usize = len(logical)
    packed, offs = encode(logical, chunk)
    assert len(offs) == 4

    at = logical.find(b"old-name")
    blob2 = logical[:at] + b"new-name" + logical[at + 8:]
    changed = _changed_chunks(logical, blob2, chunk)
    assert changed == [0], changed

    cmp2, offs2 = encode_preserving(packed, offs, logical, blob2, usize, chunk)
    assert len(offs2) == len(offs)
    assert _outer_stream(packed, offs, 0) != _outer_stream(cmp2, offs2, 0)
    for i in (1, 2, 3):
        assert _outer_stream(packed, offs, i) == _outer_stream(cmp2, offs2, i), i
    assert decode(cmp2, offs2) == blob2
    checks += 1

    # The old whole-blob path recompresses every stream at factory params: a
    # stream that was not factory-encoded is rewritten even when its payload
    # is unchanged, which is exactly what the chunk-preserving mode avoids.
    mixed_streams = [
        cmpind_codec.factory_compress(logical[0:chunk]),
        cmpind_codec.factory_compress(logical[chunk:2 * chunk]),
        cmpind_codec.factory_compress(logical[2 * chunk:3 * chunk], level=9, mem_level=9),
        cmpind_codec.factory_compress(logical[3 * chunk:4 * chunk]),
    ]
    mixed_offs, pos = [], 0
    for s in mixed_streams:
        mixed_offs.append(pos)
        pos += len(s)
    mixed = b"".join(mixed_streams)
    whole, whole_offs = encode(logical, chunk)
    assert _outer_stream(mixed, mixed_offs, 2) != _outer_stream(whole, whole_offs, 2)
    kept, kept_offs = encode_preserving(mixed, mixed_offs, logical, logical, usize, chunk)
    assert kept == mixed and kept_offs == mixed_offs
    assert decode(whole, whole_offs) == logical
    checks += 1

    # The single-differing-stream property for an unchanged blob: no chunk
    # differs, so every stream is a byte-verbatim copy.
    same_packed, same_offs = encode_preserving(packed, offs, logical, logical, usize, chunk)
    assert bytes(same_packed) == bytes(packed)
    assert same_offs == list(offs)
    checks += 1

    print(f"mutate_refer_poi selftest: OK ({checks}/{checks} checks)")
    return 0


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="In-place REFER001 name mutation",
        epilog="Exit codes: 0 success, 1 refusal/error, 2 usage error.",
    )
    ap.add_argument("cmp", nargs="?", help="REFER001/*.DAT.cmp")
    ap.add_argument("ind", nargs="?", help="REFER001/*.DAT.ind")
    ap.add_argument("outdir", nargs="?", help="output directory for the pair")
    ap.add_argument("--page", type=lambda s: int(s, 0),
                    help="absolute offset of the inner zlib stream in the .DAT")
    ap.add_argument("--old", help="existing Latin-1 text")
    ap.add_argument("--new", help="replacement Latin-1 text")
    ap.add_argument("--resize", action="store_true",
                    help="allow a different-length name and patch the record "
                         "length byte and the field-5 length byte (POINT "
                         "name-page framing, M5.52)")
    ap.add_argument("--census", action="store_true",
                    help="with CMP IND --page: count header classes and records "
                         "whose field area --resize can place, then exit")
    ap.add_argument("--batch", help="JSON list of same-length POI-name edits "
                                    "(one decode, one encode)")
    ap.add_argument("--headroom", type=float, default=None,
                    help="M5.21 slot headroom as fraction of the factory stream "
                         f"(batch default {slot_budget.HEADROOM_RATIO}, single-edit default 0.0; "
                         "refuses when stream > slot-headroom, never overflows)")
    ap.add_argument("--copies-report", metavar="JSON",
                    help="poi_copies.py JSON report to attach for 'every copy' "
                         "reporting (M5.12c; M5.27 unblocks the scan)")
    ap.add_argument("--whole-blob", action="store_true",
                    help="recompress every outer 64 KiB stream at factory params; "
                         "the pre-M9.43 path, kept for the M5.12c copy/round-trip "
                         "scan that expects every stream to be rewritten")
    ap.add_argument("--chunk-preserving", action="store_false", dest="whole_blob",
                    help="keep unchanged outer 64 KiB streams byte-verbatim "
                         "(the default; the opposite of --whole-blob)")
    ap.add_argument("--selftest", action="store_true",
                    help="run the synthetic page-framing checks and exit")
    return ap


# ---------------------------------------------------------------------------
# batch edits


POI_NAME_END = ord("@")


def edit_inner(inner: bytes, edits: list[dict]) -> tuple[bytes, list[dict]]:
    """Apply same-length name edits to one inner page.

    Each edit is ``{"at", "old", "new"}``. Raises :class:`PageError` when the
    bytes do not match, the name is not followed by ``@``, the replacement
    length differs, or the page no longer parses as records.
    """
    out = bytearray(inner)
    applied = []
    for edit in edits:
        at, old_b, new_b = edit["at"], edit["old"].encode("latin-1"), edit["new"].encode("latin-1")
        if len(old_b) != len(new_b):
            raise PageError(f"edit at {at:#x}: {len(new_b)} bytes for {len(old_b)}")
        if inner[at: at + len(old_b)] != old_b:
            raise PageError(f"edit at {at:#x}: {old_b!r} not found there")
        if at + len(old_b) >= len(inner) or inner[at + len(old_b)] != POI_NAME_END:
            raise PageError(f"edit at {at:#x}: {old_b!r} is not followed by '@'")
        out[at: at + len(old_b)] = new_b
        applied.append({"at": at, "old": edit["old"], "new": edit["new"]})
    new_inner = bytes(out)
    # Same length means no offset moves. When the page also parses as the
    # ff ff record chain (POINT010 style), the chain must still parse.
    try:
        parse_page(inner)
    except PageError:
        pass  # other POINT page framing: the byte-level check below is the guard
    else:
        parse_page(new_inner)
    changed = [i for i, (a, b) in enumerate(zip(inner, new_inner)) if a != b]
    covered = {i for e in applied for i in range(e["at"], e["at"] + len(e["old"]))}
    if not set(changed) <= covered or len(new_inner) != len(inner):
        raise PageError("page changed outside the edited names")
    return new_inner, applied


def _deflate(data: bytes, level: int, mem_level: int) -> bytes:
    return cmpind_codec.factory_compress(
        data, level=level, mem_level=mem_level,
        wbits=cmpind_codec.FACTORY_WBITS, strategy=cmpind_codec.FACTORY_STRATEGY,
    )


def page_encoder(stream: bytes, inner: bytes) -> tuple[int, int] | None:
    """Return (level, memLevel) that reproduces the original stream exactly.

    Delegates to ``slot_budget.reproducing_encoder`` (wide search, M5.12c/M5.25)
    so an unchanged page round-trips to the same bytes when reproducible.
    """
    return slot_budget.reproducing_encoder(stream, inner, wide=True)


def refit_page_budget(blob: bytes, page: int, new_inner: bytes,
                       headroom_ratio: float = 0.0) -> tuple[bytes, dict]:
    """Recompress one inner stream into its slot using the M5.21 budget.

    ``headroom_ratio`` (M5.21): fraction of the factory stream kept free; 0.0
    preserves the legacy "fits in slot" behavior. With a non-zero ratio the
    edit is refused when ``new_stream > slot - headroom`` (never overflow).
    Returns ``(new_blob, budget_row)``. Raises :class:`FitError` on refusal and
    :class:`PageError` when the page layout is not understood.
    """
    try:
        buf = bytearray(blob)
        row = slot_budget.fit_page_inplace(buf, page, new_inner, headroom_ratio)
        return bytes(buf), row
    except slot_budget.FitError as exc:
        raise FitError(str(exc), getattr(exc, "row", None)) from exc
    except slot_budget.PageError as exc:
        raise PageError(str(exc)) from exc
    except cmpind_codec.FormatError as exc:
        raise PageError(str(exc)) from exc


def refit_page(blob: bytes, page: int, new_inner: bytes,
               headroom_ratio: float = 0.0) -> bytes:
    """Recompress one inner stream into its slot (M5.21 budget). Returns the
    new blob. See ``refit_page_budget`` for the budget row."""
    new_blob, _ = refit_page_budget(blob, page, new_inner, headroom_ratio=headroom_ratio)
    return new_blob


def batch_edit(blob: bytes, plan: list[dict],
               headroom_ratio: float = slot_budget.HEADROOM_RATIO) -> tuple[bytes, list[dict]]:
    """Apply a batch plan to a decoded blob; pages are independent.

    Uses the M5.21 slot budget (M5.25): a page whose edited stream does not fit
    ``slot - headroom`` is refused and returned in the skip list with its budget
    row; its names stay as they were. Any other error stops the batch.
    """
    skipped = []
    for entry in plan:
        page = entry["page"]
        try:
            inner, _ = cmpind_codec.decompress_stream_at(blob, page)
        except cmpind_codec.FormatError as exc:
            raise PageError(str(exc)) from exc
        new_inner, applied = edit_inner(inner, entry["edits"])
        try:
            blob, row = refit_page_budget(blob, page, new_inner, headroom_ratio=headroom_ratio)
        except FitError as exc:
            row = getattr(exc, "row", {}) or {}
            skipped.append({
                "page": page, "edits": len(entry["edits"]),
                "reason": str(exc), "budget": row,
            })
            print(f"SKIP page {page:#x}: {len(entry['edits'])} edit(s) left unchanged ({exc})")
            continue
        print(f"page {page:#x}: {len(applied)} edit(s) [{row.get('decision')} new={row.get('new_stream')} limit={row.get('limit')}]")
    return blob, skipped


def batch_main(args, cmp_path: Path, ind_path: Path, outdir: Path) -> int:
    plan = json.loads(Path(args.batch).read_text(encoding="utf-8"))
    headroom = getattr(args, "headroom", slot_budget.HEADROOM_RATIO)
    usize, csize, count, chunk_size, offsets = read_ind(ind_path)
    packed = cmp_path.read_bytes()
    assert csize == len(packed)
    blob = decode(packed, offsets)
    assert len(blob) == usize
    try:
        new_blob, skipped = batch_edit(blob, plan, headroom_ratio=headroom)
    except PageError as exc:
        raise SystemExit(f"refusing: {exc}") from exc
    assert len(new_blob) == usize
    if skipped:
        (outdir / (cmp_path.stem + ".skipped.json")).write_text(
            json.dumps(skipped, indent=2), encoding="utf-8")
        print(f"refused: {len(skipped)} page(s) left unchanged (see {cmp_path.stem}.skipped.json)")
    if getattr(args, "whole_blob", False):
        new_packed, new_offsets = encode(new_blob, chunk_size)
        print(f"outer rebuild: whole-blob ({len(new_offsets)} stream(s))")
    else:
        changed = _changed_chunks(blob, new_blob, chunk_size)
        new_packed, new_offsets = encode_preserving(
            packed, offsets, blob, new_blob, usize, chunk_size)
        print(f"outer rebuild: chunk-preserving, changed chunk(s) "
              f"{changed} ({len(changed)}/{len(new_offsets)} stream(s) differ)")
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / cmp_path.name).write_bytes(new_packed)
    (outdir / ind_path.name).write_bytes(build_ind(usize, len(new_packed), chunk_size, new_offsets))
    (outdir / cmp_path.stem).write_bytes(new_blob)
    print(f"outer .cmp {len(packed)} -> {len(new_packed)} bytes; logical size unchanged: {usize}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.census:
        if not (args.cmp and args.ind and args.page is not None):
            ap.error("--census needs CMP IND --page")
        _u, _c, _n, _ch, offs = read_ind(Path(args.ind))
        blob = decode(Path(args.cmp).read_bytes(), offs)
        inner, _used = cmpind_codec.decompress_stream_at(
            blob, args.page, window=len(blob[args.page:]) or 1)
        try:
            print(format_census(census(inner)))
        except PageError as exc:
            raise SystemExit(f"not a record page: {exc}") from exc
        return 0
    if args.batch:
        if not (args.cmp and args.ind and args.outdir):
            ap.error("--batch needs CMP IND OUTDIR")
        if args.headroom is None:
            args.headroom = slot_budget.HEADROOM_RATIO
        return batch_main(args, Path(args.cmp), Path(args.ind), Path(args.outdir))
    missing = [
        name
        for name in ("cmp", "ind", "outdir", "page", "old", "new")
        if getattr(args, name) in (None, "")
    ]
    if missing:
        ap.error("missing: " + ", ".join(missing))

    cmp_path, ind_path = Path(args.cmp), Path(args.ind)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    usize, csize, count, chunk_size, offsets = read_ind(ind_path)
    packed = cmp_path.read_bytes()
    assert csize == len(packed)
    blob = decode(packed, offsets)
    assert len(blob) == usize

    old_b = args.old.encode("latin-1")
    new_b = args.new.encode("latin-1")
    if len(old_b) != len(new_b) and not args.resize:
        raise SystemExit(
            f"refusing: replacement is {len(new_b)} bytes, original {len(old_b)}; "
            "length must match to keep every offset stable (use --resize for a "
            "POINT name page)"
        )

    # locate and decompress the inner page
    page = args.page
    try:
        inner, consumed = cmpind_codec.decompress_stream_at(blob, page, window=len(blob[page:]) or 1)
    except cmpind_codec.FormatError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"inner page {page:#x}: {len(inner)} bytes -> {consumed} compressed")

    if args.resize:
        try:
            records = parse_page(inner)
        except PageError as exc:
            raise SystemExit(f"refusing --resize: {exc}") from exc
        print(f"record page: {len(records)} record(s), plain {len(inner)} bytes")
        try:
            new_inner, info = resize_name(inner, old_b, new_b)
        except PageError as exc:
            raise SystemExit(f"refusing --resize: {exc}") from exc
        print(f"record {info['index']} at {info['record_offset']:#06x}: "
              f"{info['old_total']} -> {info['new_total']} bytes "
              f"(len2 {info['old_len2']} -> {info['new_len2']}; field-5 length "
              f"byte at {info['name_len_offset']:#06x}: {info['old_name_words']} -> "
              f"{info['new_name_words']} words)")
        print(f"name {len(old_b)} -> {len(new_b)} bytes "
              f"(delta {info['delta']:+d}); {info['records']} records re-parsed")
    else:
        hits = []
        start = 0
        while True:
            i = inner.find(old_b, start)
            if i < 0:
                break
            hits.append(i)
            start = i + 1
        if len(hits) != 1:
            raise SystemExit(
                f"refusing: {len(hits)} occurrences of {args.old!r}; need exactly 1"
            )
        new_inner = inner[: hits[0]] + new_b + inner[hits[0] + len(old_b) :]
        assert len(new_inner) == len(inner)

    # M5.25: unified M5.21 slot budget (factory params M1.13/M1.16, refuse+report).
    headroom = 0.0 if args.headroom is None else args.headroom
    try:
        new_blob, row = refit_page_budget(blob, page, new_inner, headroom_ratio=headroom)
    except FitError as exc:
        raise SystemExit(f"refusing: {exc}") from exc
    limit = page + row["slot"]
    print(f"inner page recompressed: {row['new_stream']} bytes "
          f"(was {row['stream']}, enc {row.get('encoder')}), "
          f"slot {row['slot']} limit {row['limit']} headroom {row['headroom']}")
    assert len(new_blob) == usize
    if args.copies_report:
        try:
            copies = json.loads(Path(args.copies_report).read_text(encoding="utf-8"))
            print(f"copies report attached: {len(copies) if isinstance(copies, list) else 'ok'} entries")
        except Exception as exc:
            print(f"copies report unreadable ({exc}); run poi_copies.py --inner (M5.27 unblocks scan)")

    if args.whole_blob:
        new_packed, new_offsets = encode(new_blob, chunk_size)
        differing = [
            i for i in range(len(offsets))
            if _outer_stream(packed, offsets, i) != _outer_stream(new_packed, new_offsets, i)
        ]
        print(f"outer rebuild: whole-blob ({len(differing)}/{len(new_offsets)} "
              f"stream(s) differ)")
    else:
        changed = _changed_chunks(blob, new_blob, chunk_size)
        new_packed, new_offsets = encode_preserving(
            packed, offsets, blob, new_blob, usize, chunk_size)
        print(f"outer rebuild: chunk-preserving, changed chunk(s) "
              f"{changed} ({len(changed)}/{len(new_offsets)} stream(s) differ)")
    out_cmp = outdir / cmp_path.name
    out_ind = outdir / ind_path.name
    out_cmp.write_bytes(new_packed)
    out_ind.write_bytes(build_ind(usize, len(new_packed), chunk_size, new_offsets))
    out_dat = outdir / cmp_path.stem
    out_dat.write_bytes(new_blob)

    print(f"outer .cmp {len(packed)} -> {len(new_packed)} bytes, "
          f"{len(new_offsets)} chunk(s)")
    print(f"logical size unchanged: {usize} bytes")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
