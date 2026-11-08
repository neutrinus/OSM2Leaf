#!/usr/bin/env python3
"""Shared Leaf ZE0 ``.cmp`` / ``.ind`` chunk codec and inner-zlib helpers (M1.16).

Unifies the container layout and factory compression parameters used across the
writer/reader tools (``cmpind``, ``cmpind_writer``, ``slot_budget``,
``mutate_refer_poi``/``mutate_refer_page``, ``poi_copies``, ``ind_mutate`` and
readers that share the same primitives).

Container (verified on all 194 EU 2011 pairs; ``docs/format/cmp-ind.md``)::

    .ind  u32 LE uncompressed_size
          u32 LE compressed_size
          u32 LE chunk_count
          u32 LE chunk_size              (0x10000 in every observed file)
          u32 LE chunk_offset[chunk_count]
    .cmp  ``chunk_count`` independent zlib streams concatenated.

Every non-final chunk inflates to exactly ``chunk_size`` bytes.

Factory encoder (M1.13 / C-2570–C-2579, REFER001/POINT001–009 inner pages):
stock zlib **level 6, memLevel 8, wbits 15, default strategy**.  The same
parameter set is used for the outer 64 KiB ``.cmp`` chunks in the factory
files; zlib-ng does not reproduce those streams (H9 / C-2572).

This module is intentionally small and dependency-free (stdlib ``zlib`` and
``re``) so it can be imported by every tool without side effects.  It exposes
helpers, not a CLI; the existing tool CLIs remain the entry points.

Self-test (synthetic, no vendor data)::

    python3 tools/cmpind_codec.py --selftest
"""

from __future__ import annotations

import argparse
import hashlib
import re
import struct
import sys
import zlib
from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence

# ---------------------------------------------------------------------------
# factory parameters (M1.13 / C-2570–C-2579)
# ---------------------------------------------------------------------------

CHUNK = 0x10000
IND_HEADER = 16
PAGE_ALIGN = 0x100

FACTORY_LEVEL = 6
FACTORY_MEM = 8
FACTORY_WBITS = 15
FACTORY_STRATEGY = zlib.Z_DEFAULT_STRATEGY

#: A valid zlib stream header at the start of a byte string.
ZLIB_HEAD = re.compile(rb"\x78[\x01\x5e\x9c\xda]")


def factory_params() -> dict:
    """Return the pinned factory zlib parameters as a plain dict."""
    return {
        "level": FACTORY_LEVEL,
        "memLevel": FACTORY_MEM,
        "wbits": FACTORY_WBITS,
        "strategy": FACTORY_STRATEGY,
    }


def factory_compress(
    data: bytes,
    *,
    level: int = FACTORY_LEVEL,
    mem_level: int = FACTORY_MEM,
    wbits: int = FACTORY_WBITS,
    strategy: int = FACTORY_STRATEGY,
) -> bytes:
    """Compress *data* with the factory (stock zlib) parameters."""
    co = zlib.compressobj(level, zlib.DEFLATED, wbits, mem_level, strategy)
    return co.compress(data) + co.flush()


# ---------------------------------------------------------------------------
# .ind header
# ---------------------------------------------------------------------------


class FormatError(Exception):
    """A ``.cmp`` / ``.ind`` pair does not match the verified container layout."""


def read_ind(path: Path | str) -> tuple[int, int, int, int, tuple[int, ...]]:
    """Read a ``.ind`` file.

    Returns ``(usize, csize, count, chunk_size, offsets)``.  Raises
    :class:`FormatError` on a truncated or inconsistent header.
    """
    path = Path(path)
    data = path.read_bytes()
    if len(data) < IND_HEADER:
        raise FormatError(f"{path}: too short for .ind header")
    usize, csize, count, chunk_size = struct.unpack_from("<IIII", data, 0)
    expected = IND_HEADER + 4 * count
    if len(data) != expected:
        raise FormatError(f"{path}: size {len(data)} != 16 + 4*{count} = {expected}")
    offsets = struct.unpack_from(f"<{count}I", data, IND_HEADER)
    return usize, csize, count, chunk_size, offsets


def build_ind(usize: int, csize: int, chunk_size: int, offsets: Sequence[int]) -> bytes:
    """Serialize a ``.ind`` header."""
    return struct.pack("<IIII", usize, csize, len(offsets), chunk_size) + struct.pack(
        f"<{len(offsets)}I", *offsets
    )


def pair_paths(cmp_path: Path | str, ind_path: Path | str | None = None) -> tuple[Path, Path]:
    cmp_path = Path(cmp_path)
    if ind_path is None:
        ind_path = cmp_path.with_suffix(".ind")
    return cmp_path, Path(ind_path)


# ---------------------------------------------------------------------------
# outer container decode / encode
# ---------------------------------------------------------------------------


def chunk_ranges(cmp_size: int, offsets: Sequence[int]) -> Iterator[tuple[int, int, int]]:
    """Yield ``(index, start, end)`` for each chunk in *offsets*."""
    for i, start in enumerate(offsets):
        end = offsets[i + 1] if i + 1 < len(offsets) else cmp_size
        yield i, start, end


def decode_blob(
    cmp_bytes: bytes,
    offsets: Sequence[int],
    *,
    usize: int | None = None,
    chunk_size: int | None = None,
    strict_nonfinal: bool = True,
    name: str = ".cmp",
) -> bytes:
    """Inflate a ``.cmp`` payload given its chunk offsets.

    When *strict_nonfinal* is true every non-final chunk must inflate to exactly
    *chunk_size* bytes (the verified container invariant).  When *usize* is set
    the joined output must match it.
    """
    parts: list[bytes] = []
    count = len(offsets)
    for i, start, end in chunk_ranges(len(cmp_bytes), offsets):
        if not (0 <= start < end <= len(cmp_bytes)):
            raise FormatError(f"{name}: chunk {i} range {start}:{end} out of bounds")
        try:
            part = zlib.decompress(cmp_bytes[start:end])
        except zlib.error as exc:
            raise FormatError(f"{name}: chunk {i} ({start}:{end}): {exc}") from exc
        if strict_nonfinal and chunk_size is not None and i != count - 1 and len(part) != chunk_size:
            raise FormatError(f"{name}: chunk {i} decoded to {len(part)}, expected {chunk_size}")
        parts.append(part)
    blob = b"".join(parts)
    if usize is not None and len(blob) != usize:
        raise FormatError(f"{name}: decoded {len(blob)} bytes, .ind declares {usize}")
    return blob


def decode(
    cmp_path: Path | str,
    ind_path: Path | str | None = None,
    *,
    strict_nonfinal: bool = True,
) -> tuple[bytes, dict]:
    """Decode a ``.cmp`` / ``.ind`` pair.  Returns ``(blob, info)``."""
    cmp_path, ind_path = pair_paths(cmp_path, ind_path)
    usize, csize, count, chunk_size, offsets = read_ind(ind_path)
    packed = cmp_path.read_bytes()
    if csize != len(packed):
        raise FormatError(f"{cmp_path}: .ind says {csize} compressed bytes, file has {len(packed)}")
    blob = decode_blob(
        packed, offsets, usize=usize, chunk_size=chunk_size,
        strict_nonfinal=strict_nonfinal, name=str(cmp_path),
    )
    info = {
        "uncompressed_size": usize,
        "compressed_size": csize,
        "chunk_count": count,
        "chunk_size": chunk_size,
        "offsets": offsets,
        "cmp_path": cmp_path,
        "ind_path": ind_path,
    }
    return blob, info


def encode_chunks(
    blob: bytes,
    chunk_size: int = CHUNK,
    *,
    compress: Callable[[bytes], bytes] | None = None,
) -> tuple[bytes, list[int]]:
    """Split *blob* into outer chunks and compress each independently.

    Returns ``(cmp_bytes, offsets)``.
    """
    if compress is None:
        compress = factory_compress
    streams: list[bytes] = []
    for pos in range(0, len(blob), chunk_size):
        streams.append(compress(blob[pos : pos + chunk_size]))
    offsets: list[int] = []
    pos = 0
    for stream in streams:
        offsets.append(pos)
        pos += len(stream)
    return b"".join(streams), offsets


def repack_changed_chunks(
    packed_old: bytes,
    offsets_old: Sequence[int],
    usize: int,
    chunk_size: int,
    blob_old: bytes,
    blob_new: bytes,
    *,
    compress: Callable[[bytes], bytes] | None = None,
) -> tuple[bytes, list[int]]:
    """Rebuild an outer container, keeping unchanged compressed chunks verbatim.

    A chunk is kept when its logical payload ``blob_old[lo:hi]`` equals
    ``blob_new[lo:hi]``; changed chunks are recompressed with *compress*
    (defaults to :func:`factory_compress`).  Returns ``(cmp_bytes, offsets)``.
    """
    if compress is None:
        compress = factory_compress
    if len(blob_old) != len(blob_new) or len(blob_new) != usize:
        raise ValueError("blob_old/blob_new must both have length usize")
    count = len(offsets_old)
    out = bytearray()
    offsets: list[int] = []
    for i, start in enumerate(offsets_old):
        end = offsets_old[i + 1] if i + 1 < count else len(packed_old)
        lo, hi = i * chunk_size, min((i + 1) * chunk_size, usize)
        offsets.append(len(out))
        if blob_old[lo:hi] == blob_new[lo:hi]:
            out += packed_old[start:end]
        else:
            out += compress(blob_new[lo:hi])
    return bytes(out), offsets


def rebuild_pair_bytes(
    packed_old: bytes,
    offsets_old: Sequence[int],
    usize: int,
    chunk_size: int,
    blob_old: bytes,
    blob_new: bytes,
    *,
    compress: Callable[[bytes], bytes] | None = None,
) -> tuple[bytes, bytes]:
    """Like :func:`repack_changed_chunks` but also returns the ``.ind`` bytes."""
    cmp_bytes, offsets = repack_changed_chunks(
        packed_old, offsets_old, usize, chunk_size, blob_old, blob_new, compress=compress
    )
    return cmp_bytes, build_ind(usize, len(cmp_bytes), chunk_size, offsets)


# ---------------------------------------------------------------------------
# inner complete-zlib page helpers
# ---------------------------------------------------------------------------


def decompress_stream_at(
    blob: bytes,
    offset: int,
    window: int = 1 << 20,
) -> tuple[bytes, int]:
    """Inflate one complete zlib stream starting at *offset*.

    Returns ``(inner, consumed)`` where *consumed* is the number of compressed
    bytes the stream occupies (``window`` minus trailing unused data).  Raises
    :class:`FormatError` if the stream is incomplete or invalid.
    """
    view = memoryview(blob)[offset : offset + window]
    dec = zlib.decompressobj()
    try:
        inner = dec.decompress(view)
    except zlib.error as exc:
        raise FormatError(f"zlib stream at {offset:#x}: {exc}") from exc
    if not dec.eof:
        raise FormatError(f"zlib stream at {offset:#x} is not complete within {window} bytes")
    consumed = len(view) - len(dec.unused_data)
    return inner, consumed


def find_aligned_pages(blob: bytes, *, align: int = PAGE_ALIGN, window: int = 1 << 20):
    """Yield ``(offset, consumed, inner)`` for complete aligned zlib pages.

    Scans *align*-byte boundaries (the REFER001 inner-page layout used by
    ``factory_zlib``).  Non-stream / incomplete candidates are skipped.
    """
    mv = memoryview(blob)
    for off in range(0, len(blob) - 2, align):
        b0, b1 = blob[off], blob[off + 1]
        if b0 & 0x0F != 8 or ((b0 << 8) | b1) % 31 != 0:
            continue
        view = mv[off : off + window]
        dec = zlib.decompressobj()
        try:
            inner = dec.decompress(view)
        except zlib.error:
            continue
        if not dec.eof:
            continue
        consumed = len(view) - len(dec.unused_data)
        yield off, consumed, inner


def find_zlib_streams(blob: bytes, *, window: int = 1 << 20):
    """Yield ``(offset, consumed, inner)`` for complete zlib streams by header scan.

    Walks the blob in stream order (like ``slot_budget.find_pages``): after a
    complete stream the next candidate starts at ``offset + consumed``.  A
    header that fails to inflate is skipped and the scan continues.
    """
    pos = 0
    for match in ZLIB_HEAD.finditer(blob):
        start = match.start()
        if start < pos:
            continue
        try:
            inner, consumed = decompress_stream_at(blob, start, window)
        except FormatError:
            continue
        yield start, consumed, inner
        pos = start + consumed


def inner_stream_slot(
    blob: bytes,
    page: int,
    *,
    align: int = PAGE_ALIGN,
    window: int = 1 << 20,
    require_zero_padding: bool = True,
) -> tuple[bytes, int, int, bytes]:
    """Return ``(inner, consumed, slot, original_stream)`` for an inner stream.

    The *slot* is the number of bytes available to the stream: the original
    stream plus any zero padding up to the next *align* boundary.  When
    *require_zero_padding* is true, non-zero bytes after the stream up to that
    boundary cap the slot at *consumed* (pages may abut a neighbour).  When it
    is false, the slot is always rounded up to *align* (``mutate_refer_page``
    behavior).  A zlib stream never starts with ``0x00``.
    """
    inner, consumed = decompress_stream_at(blob, page, window)
    original = blob[page : page + consumed]
    limit = (page + consumed + align - 1) & ~(align - 1)
    if require_zero_padding and any(blob[page + consumed : limit]):
        limit = page + consumed
    return inner, consumed, limit - page, original


def refit_stream_in_slot(
    stream: bytes,
    slot: int,
) -> bytes:
    """Pad *stream* with zeros to fill *slot*, or raise if it does not fit."""
    if len(stream) > slot:
        raise FormatError(f"stream {len(stream)} bytes does not fit slot {slot}")
    return stream + bytes(slot - len(stream))


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def selftest() -> int:
    checks = 0

    def ok(cond: bool, name: str) -> None:
        nonlocal checks
        if not cond:
            raise AssertionError(name)
        checks += 1

    # factory params
    p = factory_params()
    ok(p["level"] == 6 and p["memLevel"] == 8 and p["wbits"] == 15, "factory params")
    s = factory_compress(b"hello " * 100)
    ok(zlib.decompress(s) == b"hello " * 100, "factory_compress round-trip")
    ok(factory_compress(b"x" * 10, level=9) != factory_compress(b"x" * 10, level=1),
       "level respected")

    # .ind round-trip
    ind = build_ind(0x12345, 0x678, 0x10000, (0, 0x100, 0x200))
    usu, csz, cnt, ch = struct.unpack_from("<IIII", ind, 0)
    offs = struct.unpack_from("<3I", ind, IND_HEADER)
    ok((usu, csz, cnt, ch, offs) == (0x12345, 0x678, 3, 0x10000, (0, 0x100, 0x200)), "ind header")
    import tempfile

    with tempfile.TemporaryDirectory(prefix="cmpind-codec-") as td:
        base = Path(td)
        (base / "x.ind").write_bytes(ind)
        r = read_ind(base / "x.ind")
        ok(r == (0x12345, 0x678, 3, 0x10000, (0, 0x100, 0x200)), "read_ind")

        # outer container: three chunks, last partial, changed-chunk repack
        chunks = [b"A" * 0x10000, bytes(i * 31 & 0xFF for i in range(0x10000)), b"z" * 300]
        blob = b"".join(chunks)
        cmp_bytes, offsets = encode_chunks(blob)
        indb = build_ind(len(blob), len(cmp_bytes), CHUNK, offsets)
        (base / "p.cmp").write_bytes(cmp_bytes)
        (base / "p.ind").write_bytes(indb)
        dec, info = decode(base / "p.cmp")
        ok(dec == blob and info["chunk_count"] == 3, "decode round-trip")
        ok(info["chunk_size"] == CHUNK and info["uncompressed_size"] == len(blob), "decode info")

        blob2 = bytearray(blob)
        blob2[500:510] = b"BBBBBBBBBB"  # touches chunk 0 only
        cmp2, off2 = repack_changed_chunks(cmp_bytes, offsets, len(blob), CHUNK, blob, bytes(blob2))
        ok(decode_blob(cmp2, off2, usize=len(blob), chunk_size=CHUNK) == bytes(blob2),
           "changed-chunk repack decodes")
        # unchanged chunks (1,2) keep their compressed bytes verbatim
        i1s, i1e = offsets[1], offsets[2]
        j1s, j1e = off2[1], off2[2]
        ok(cmp_bytes[i1s:i1e] == cmp2[j1s:j1e], "unchanged chunk 1 preserved")
        i2s = offsets[2]
        j2s = off2[2]
        ok(cmp_bytes[i2s:] == cmp2[j2s:], "unchanged chunk 2 preserved")
        ok(cmp2[:j1s] != cmp_bytes[:i1s], "changed chunk 0 differs (positive control)")

        bad_off = list(offsets)
        bad_off[1] += 3
        try:
            decode_blob(cmp_bytes, bad_off, usize=len(blob), chunk_size=CHUNK)
            ok(False, "bad offset must raise")
        except (FormatError, zlib.error):
            ok(True, "bad offset rejected")

    # inner pages
    inner1 = b"NAME ONE@" * 200
    inner2 = b"DEST TWO@" * 150
    st1 = factory_compress(inner1)
    st2 = factory_compress(inner2)

    def pad(b: bytes, align: int = PAGE_ALIGN) -> bytes:
        return b + bytes(-len(b) % align)

    page0, page1 = 0, len(pad(st1))
    blobp = pad(st1) + pad(st2) + bytes(PAGE_ALIGN)
    aligned = list(find_aligned_pages(blobp))
    ok(len(aligned) == 2 and aligned[0][0] == page0 and aligned[1][0] == page1, "find_aligned_pages")
    ok(aligned[0][2] == inner1 and aligned[1][1] == len(st2), "aligned page content")

    streams = list(find_zlib_streams(pad(st1) + st2))  # abutting (no align gap before st2)
    ok(len(streams) == 2 and streams[0][0] == 0 and streams[1][0] == len(pad(st1)),
       "find_zlib_streams abutting")

    inn, consumed = decompress_stream_at(blobp, 0)
    ok(inn == inner1 and consumed == len(st1), "decompress_stream_at")

    # non-zero byte appears in the padding area before the 0x100 boundary
    nonzero_pad = st1 + b"\x01" + b"\x00" * ((-((len(st1) + 1) % PAGE_ALIGN)) % PAGE_ALIGN)
    bloba = bytearray(nonzero_pad + b"\x78" * 4)
    inn, con, slot, orig = inner_stream_slot(bytes(bloba), 0)
    ok(slot == con and orig == st1, "slot capped when abutting non-zero")
    blobz = bytearray(st1 + b"\x00" * 0x100 + b"\x01")
    _, conz, slotz, _ = inner_stream_slot(bytes(blobz), 0)
    ok(slotz == ((conz + 0xFF) & ~0xFF), "slot rounds over zero padding")
    _, _, slotnz, _ = inner_stream_slot(bytes(blobz), 0, require_zero_padding=False)
    ok(slotnz == slotz, "require_zero_padding False on zero still rounds")
    try:
        refit_stream_in_slot(b"x" * 10, 5)
        ok(False, "refit must raise on overflow")
    except FormatError:
        ok(True, "refit overflow rejected")
    ok(refit_stream_in_slot(b"abc", 5) == b"abc\x00\x00", "refit pads")

    print(f"cmpind_codec selftest: {checks} checks OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
