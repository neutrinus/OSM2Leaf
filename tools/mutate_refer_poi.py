#!/usr/bin/env python3
"""Minimal in-place name mutation for a REFER001 .cmp/.ind pair.

Design constraints (see docs/research/minimal-change.md):
  * the logical .DAT size is unchanged, so DRSTR001.DAT needs no update;
  * the inner zlib page keeps its absolute offset, so every pointer table
    entry that references it stays valid;
  * the replacement text has exactly the same byte length, so no offset or
    length field inside the name page changes.

Only these bytes change: the name text, the inner zlib stream (recompressed,
zero-padded back to the page boundary), the outer .cmp (one zlib stream), and
the .ind compressed_size field.

Usage:
  python3 mutate_refer_poi.py CMP IND OUTDIR --page 0x4200 \
      --old "VATICAN MUSEUM" --new "OSM2LEAF PROBE"
"""

from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

CHUNK = 0x10000


def read_ind(path: Path):
    data = path.read_bytes()
    usize, csize, count, chunk_size = struct.unpack_from("<IIII", data, 0)
    assert len(data) == 16 + 4 * count, "unexpected .ind size"
    offsets = struct.unpack_from(f"<{count}I", data, 16)
    return usize, csize, count, chunk_size, list(offsets)


def decode(cmp_bytes: bytes, offsets: list[int]) -> bytes:
    parts = []
    for i, start in enumerate(offsets):
        end = offsets[i + 1] if i + 1 < len(offsets) else len(cmp_bytes)
        parts.append(zlib.decompress(cmp_bytes[start:end]))
    return b"".join(parts)


def encode(blob: bytes, chunk_size: int):
    streams = []
    for pos in range(0, len(blob), chunk_size):
        streams.append(zlib.compress(blob[pos : pos + chunk_size], 6))
    offsets = []
    pos = 0
    for s in streams:
        offsets.append(pos)
        pos += len(s)
    return b"".join(streams), offsets


def build_ind(usize: int, csize: int, chunk_size: int, offsets: list[int]) -> bytes:
    return (
        struct.pack("<IIII", usize, csize, len(offsets), chunk_size)
        + struct.pack(f"<{len(offsets)}I", *offsets)
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmp")
    ap.add_argument("ind")
    ap.add_argument("outdir")
    ap.add_argument("--page", type=lambda s: int(s, 0), required=True,
                    help="absolute offset of the inner zlib stream in the .DAT")
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    args = ap.parse_args()

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
    if len(old_b) != len(new_b):
        raise SystemExit(
            f"refusing: replacement is {len(new_b)} bytes, original {len(old_b)}; "
            "length must match to keep every offset stable"
        )

    # locate and decompress the inner page
    page = args.page
    dec = zlib.decompressobj()
    inner = dec.decompress(blob[page:])
    consumed = len(blob[page:]) - len(dec.unused_data)
    print(f"inner page {page:#x}: {len(inner)} bytes -> {consumed} compressed")

    hits = []
    start = 0
    while True:
        i = inner.find(old_b, start)
        if i < 0:
            break
        hits.append(i)
        start = i + 1
    if len(hits) != 1:
        raise SystemExit(f"refusing: {len(hits)} occurrences of {args.old!r}; need exactly 1")

    new_inner = inner[: hits[0]] + new_b + inner[hits[0] + len(old_b) :]
    assert len(new_inner) == len(inner)

    # find the next page boundary after the original stream; must fit
    limit = (page + consumed + 0xFF) & ~0xFF
    new_stream = zlib.compress(new_inner, 6)
    if page + len(new_stream) > limit:
        raise SystemExit(
            f"refusing: recompressed page is {len(new_stream)} bytes, "
            f"only {limit - page} available before {limit:#x}"
        )
    print(f"inner page recompressed: {len(new_stream)} bytes "
          f"(was {consumed}), {limit - page - len(new_stream)} bytes spare")

    new_blob = bytearray(blob)
    new_blob[page:limit] = new_stream.ljust(limit - page, b"\0")
    new_blob = bytes(new_blob)
    assert len(new_blob) == usize

    new_packed, new_offsets = encode(new_blob, chunk_size)
    out_cmp = outdir / cmp_path.name
    out_ind = outdir / ind_path.name
    out_cmp.write_bytes(new_packed)
    out_ind.write_bytes(build_ind(usize, len(new_packed), chunk_size, new_offsets))
    out_dat = outdir / (cmp_path.stem)
    out_dat.write_bytes(new_blob)

    print(f"outer .cmp {len(packed)} -> {len(new_packed)} bytes, "
          f"{len(new_offsets)} chunk(s)")
    print(f"logical size unchanged: {usize} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
