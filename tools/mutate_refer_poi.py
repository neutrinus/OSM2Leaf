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

Only these bytes change: the name text, the record length byte (``--resize``),
the inner zlib stream (recompressed, zero-padded back to the page boundary),
the outer ``.cmp`` (one zlib stream) and the ``.ind`` compressed-size field.

Usage:
  python3 mutate_refer_poi.py CMP IND OUTDIR --page 0x4200 \
      --old "VATICAN MUSEUM" --new "OSM2LEAF PROBE"
  python3 mutate_refer_poi.py CMP IND OUTDIR --page 0x4200 --resize \
      --old "VATICAN MUSEUM" --new "OSM2LEAF PROBE POI"
  python3 mutate_refer_poi.py CMP IND OUTDIR --batch EDITS.json
  python3 mutate_refer_poi.py --selftest

``--batch`` takes a JSON list of pages, each with same-length edits::

  [{"page": 8649488, "edits": [{"at": 94, "old": "HANA HEALTH CENTER",
                                 "new": "OSM2LEAF TEST POI1"}]}]

``at`` is the offset of ``old`` inside the inner page. Every edit must match
the bytes there and be followed by ``@`` (a POI name, not an address part).
Each edited page must still parse as a record chain. The file is decoded once,
all pages are rewritten, and the pair is encoded once.
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

CHUNK = cmpind_codec.CHUNK
PAGE_ALIGN = cmpind_codec.PAGE_ALIGN
#: First byte of a POINT name record.  Other POINT pages are a different
#: (bit-packed) page type and start ``00 xx 00 yy``.
RECORD_TAGS = (0x60, 0x68)
#: Every record ends with this marker, after its display text.
RECORD_TERMINATOR = b"\xff\xff"
MAX_RECORD = 2 * 0xFF


class PageError(ValueError):
    """The page is not the record chain this tool understands."""


class FitError(PageError):
    """The edited page does not fit its original slot in any tried encoder."""


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


def verify_resize(
    old_page: bytes, new_page: bytes, info: dict, old: bytes, new: bytes
) -> None:
    """Assert that only the renamed record changed and the chain still parses."""
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
    for other, (before, after) in enumerate(zip(old_records, new_records)):
        if other == index:
            continue
        if before["bytes"] != after["bytes"]:
            raise PageError(f"record {other} at {before['offset']:#x} changed")
    if len(new_page) != len(old_page) + info["delta"]:
        raise PageError("page length does not match the name delta")


def resize_name(inner: bytes, old: bytes, new: bytes) -> tuple[bytes, dict]:
    """Replace ``old`` with ``new`` in a record page, fixing the length byte.

    ``new`` may differ in length from ``old``; the byte delta must keep the
    record size even because the framing stores ``size/2`` in one byte.
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
    new_total = record["total"] + delta
    if new_total % 2:
        raise PageError(
            f"record {record['offset']:#x} would be {new_total} bytes (odd); "
            "the framing stores size/2, so change the name by an even number "
            "of bytes"
        )
    if not 4 <= new_total <= MAX_RECORD:
        raise PageError(
            f"record {record['offset']:#x} would be {new_total} bytes, "
            f"outside 4..{MAX_RECORD}"
        )
    new_inner = inner[:hit] + new + inner[hit + len(old) :]
    new_len2 = new_total // 2
    new_inner = (
        new_inner[: record["offset"] + 1]
        + bytes([new_len2])
        + new_inner[record["offset"] + 2 :]
    )
    info = {
        "index": records.index(record),
        "record_offset": record["offset"],
        "old_total": record["total"],
        "new_total": new_total,
        "old_len2": record["len2"],
        "new_len2": new_len2,
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


def build_ind(usize: int, csize: int, chunk_size: int, offsets: list[int]) -> bytes:
    return cmpind_codec.build_ind(usize, csize, chunk_size, offsets)


# ---------------------------------------------------------------------------
# self-test (synthetic page, no vendor data)


def _synth_record(tag: int, body: bytes, names: bytes) -> bytes:
    payload = body + names + RECORD_TERMINATOR
    total = 2 + len(payload)
    if total % 2:
        raise AssertionError("synthetic record must be even-sized")
    if total > MAX_RECORD:
        raise AssertionError("synthetic record too large")
    return bytes([tag, total // 2]) + payload


def selftest() -> int:
    body = bytes.fromhex("9f6fd43e0c76046a0600")
    page = b"".join(
        [
            _synth_record(0x60, body, b"ALPHA MUSEUM\0@VIA ONE\0"),
            _synth_record(0x68, body, b"BETA MUSEUM@VIA TWO\0"),
            _synth_record(0x60, body, b"GAMMA@VIA THREE\0"),
        ]
    )
    checks = 0

    records = parse_page(page)
    assert len(records) == 3
    assert records[0]["offset"] == 0
    assert records[1]["offset"] == records[0]["total"]
    assert records[2]["offset"] == records[1]["offset"] + records[1]["total"]
    checks += 1

    # same-length rename keeps the page size and every length byte
    same, info = resize_name(page, b"ALPHA MUSEUM", b"ALPHA MUSEU?")
    assert len(same) == len(page)
    assert info["delta"] == 0
    assert parse_page(same)[0]["len2"] == records[0]["len2"]
    assert b"ALPHA MUSEU?" in same
    checks += 1

    # +4 bytes: the length byte grows by 2 and the page grows by 4
    grown, info = resize_name(page, b"ALPHA MUSEUM", b"ALPHA MUSEUM TWO")
    assert len(grown) == len(page) + 4
    assert info["delta"] == 4
    assert info["new_len2"] == records[0]["len2"] + 2
    after = parse_page(grown)
    assert len(after) == 3
    assert after[1]["bytes"] == records[1]["bytes"]
    assert after[2]["bytes"] == records[2]["bytes"]
    checks += 1

    # -2 bytes on the middle record
    short, info = resize_name(page, b"BETA MUSEUM", b"BETA MUSE")
    assert len(short) == len(page) - 2
    assert info["delta"] == -2
    assert len(parse_page(short)) == 3
    checks += 1

    for bad, message in (
        ((b"ALPHA MUSEUM", b"ALPHA MUSEUMS"), "odd"),
        ((b"NO SUCH NAME", b"NO SUCH NAME"), "occurrences"),
        ((b"ALPHA MUSEUM", b"ALPHA\x00MUSEUM"), "NUL"),
    ):
        try:
            resize_name(page, *bad)
        except PageError as exc:
            assert message.lower() in str(exc).lower(), (message, exc)
        else:
            raise AssertionError(f"expected PageError for {bad!r}")
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

    # batch edits: same-length, followed by '@', framing preserved
    beta_at = page.find(b"BETA MUSEUM")
    new_inner, applied = edit_inner(page, [
        {"at": beta_at, "old": "BETA MUSEUM", "new": "OSM2 TEST  "},
    ])
    assert new_inner.find(b"OSM2 TEST  @VIA TWO") > 0 and len(new_inner) == len(page)
    assert len(parse_page(new_inner)) == 3
    checks += 1
    alpha_at = page.find(b"ALPHA MUSEUM")  # followed by NUL, not '@': refused
    for bad in (
        {"at": beta_at, "old": "BETA MUSEUM", "new": "SHORT"},
        {"at": beta_at + 1, "old": "BETA MUSEUM", "new": "OSM2 TEST  "},
        {"at": alpha_at, "old": "ALPHA MUSEUM", "new": "OSM2 TEST   "},
    ):
        try:
            edit_inner(page, [bad])
        except PageError:
            pass
        else:
            raise AssertionError(f"batch edit accepted: {bad!r}")
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
                         "length byte (POINT name-page framing)")
    ap.add_argument("--batch", help="JSON list of same-length POI-name edits "
                                    "(one decode, one encode)")
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
    """Return (level, memLevel) that reproduces the original stream exactly."""
    for mem_level in (8, 9, 7, 6, 5, 4, 3, 2, 1):
        for level in (9, 6, 8, 7, 5, 4, 3, 2, 1):
            if _deflate(inner, level, mem_level) == stream:
                return level, mem_level
    return None


def refit_page(blob: bytes, page: int, new_inner: bytes) -> bytes:
    """Recompress one inner stream into its original slot.

    The slot is the original stream plus any zero padding up to the next
    0x100 boundary. POINT pages can abut the next page, so padding is used
    only when the original bytes there are all zero. The encoder settings
    that reproduce the original stream are used first, so an unchanged name
    gives back the same bytes.
    """
    try:
        inner, consumed, slot, original = cmpind_codec.inner_stream_slot(blob, page)
    except cmpind_codec.FormatError as exc:
        raise PageError(str(exc)) from exc
    setting = page_encoder(original, inner)
    candidates = [setting] if setting else []
    candidates += [(level, mem) for level in range(9, 0, -1) for mem in (8, 9)]
    for level, mem_level in candidates:
        stream = _deflate(new_inner, level, mem_level)
        if len(stream) <= slot:
            new_blob = bytearray(blob)
            new_blob[page: page + slot] = cmpind_codec.refit_stream_in_slot(stream, slot)
            return bytes(new_blob)
    raise FitError(f"page {page:#x}: no encoder fits {slot} bytes")


def batch_edit(blob: bytes, plan: list[dict]) -> tuple[bytes, list[dict]]:
    """Apply a batch plan to a decoded blob; pages are independent.

    A page whose edited stream does not fit its slot is skipped and returned
    in the skip list; its names stay as they were. Any other error stops the
    batch.
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
            blob = refit_page(blob, page, new_inner)
        except FitError as exc:
            skipped.append({"page": page, "edits": len(entry["edits"]), "reason": str(exc)})
            print(f"SKIP page {page:#x}: {len(entry['edits'])} edit(s) left unchanged ({exc})")
            continue
        print(f"page {page:#x}: {len(applied)} edit(s)")
    return blob, skipped


def batch_main(args, cmp_path: Path, ind_path: Path, outdir: Path) -> int:
    plan = json.loads(Path(args.batch).read_text(encoding="utf-8"))
    usize, csize, count, chunk_size, offsets = read_ind(ind_path)
    packed = cmp_path.read_bytes()
    assert csize == len(packed)
    blob = decode(packed, offsets)
    assert len(blob) == usize
    try:
        new_blob, skipped = batch_edit(blob, plan)
    except PageError as exc:
        raise SystemExit(f"refusing: {exc}") from exc
    assert len(new_blob) == usize
    if skipped:
        (outdir / (cmp_path.stem + ".skipped.json")).write_text(
            json.dumps(skipped, indent=2), encoding="utf-8")
    new_packed, new_offsets = encode(new_blob, chunk_size)
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
    if args.batch:
        if not (args.cmp and args.ind and args.outdir):
            ap.error("--batch needs CMP IND OUTDIR")
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
              f"(len2 {info['old_len2']} -> {info['new_len2']})")
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

    # find the next page boundary after the original stream; must fit
    limit = (page + consumed + PAGE_ALIGN - 1) & ~(PAGE_ALIGN - 1)
    new_stream = cmpind_codec.factory_compress(new_inner, level=6)
    level_used = 6
    if page + len(new_stream) > limit:
        # zlib-ng or content changes can make level 6 grow; level 9 may fit.
        new_stream9 = cmpind_codec.factory_compress(new_inner, level=9)
        if page + len(new_stream9) <= limit:
            new_stream = new_stream9
            level_used = 9
        else:
            raise SystemExit(
                f"refusing: recompressed page is {len(new_stream)} bytes (L6) / "
                f"{len(new_stream9)} bytes (L9), only {limit - page} available "
                f"before {limit:#x}"
            )
    print(f"inner page recompressed: {len(new_stream)} bytes "
          f"(was {consumed}, L{level_used}), {limit - page - len(new_stream)} bytes spare")

    new_blob = bytearray(blob)
    new_blob[page:limit] = new_stream + bytes(limit - page - len(new_stream))
    new_blob = bytes(new_blob)
    assert len(new_blob) == usize

    new_packed, new_offsets = encode(new_blob, chunk_size)
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
