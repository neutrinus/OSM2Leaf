#!/usr/bin/env python3
"""Apply a small in-page byte patch to a REFER001 .cmp/.ind pair.

For experiments that must not change any length: e.g. nudge a POI coordinate
(u16 BE A at record+2, u16 BE B at record+4) inside an inner zlib page.

Guarantees the same checks as mutate_refer_poi.py: the logical .DAT size is
unchanged, the inner page stays at the same absolute offset, and the new
stream must fit before the next 0x100 boundary.

Usage:
  python3 mutate_refer_page.py CMP IND OUTDIR --page 0x4200 \
      --patch 0x2a2:9f70 --patch 0x2a4:d43f
"""

from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path


def read_ind(path: Path):
    data = path.read_bytes()
    usize, csize, count, chunk_size = struct.unpack_from("<IIII", data, 0)
    assert len(data) == 16 + 4 * count
    return usize, csize, count, chunk_size, list(struct.unpack_from(f"<{count}I", data, 16))


def decode(packed: bytes, offsets: list[int]) -> bytes:
    parts = []
    for i, start in enumerate(offsets):
        end = offsets[i + 1] if i + 1 < len(offsets) else len(packed)
        parts.append(zlib.decompress(packed[start:end]))
    return b"".join(parts)


def encode(blob: bytes, chunk_size: int):
    streams, offsets, pos = [], [], 0
    for p in range(0, len(blob), chunk_size):
        s = zlib.compress(blob[p : p + chunk_size], 6)
        offsets.append(pos)
        pos += len(s)
        streams.append(s)
    return b"".join(streams), offsets


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmp")
    ap.add_argument("ind")
    ap.add_argument("outdir")
    ap.add_argument("--page", type=lambda s: int(s, 0), required=True)
    ap.add_argument("--patch", action="append", required=True,
                    help="inner_offset:hexbytes, repeatable")
    args = ap.parse_args()

    cmp_path, ind_path = Path(args.cmp), Path(args.ind)
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    usize, csize, count, chunk_size, offsets = read_ind(ind_path)
    packed = cmp_path.read_bytes()
    blob = decode(packed, offsets)
    assert len(blob) == usize

    d = zlib.decompressobj()
    inner = bytearray(d.decompress(blob[args.page:]))
    consumed = len(blob[args.page:]) - len(d.unused_data)

    for item in args.patch:
        off_s, hex_s = item.split(":")
        off = int(off_s, 0)
        new = bytes.fromhex(hex_s)
        print(f"patch inner {off:#06x}: {inner[off:off+len(new)].hex(' ')} -> {new.hex(' ')}")
        inner[off : off + len(new)] = new

    limit = (args.page + consumed + 0xFF) & ~0xFF
    stream = zlib.compress(bytes(inner), 6)
    if args.page + len(stream) > limit:
        raise SystemExit(f"refusing: {len(stream)} bytes does not fit in {limit - args.page}")
    print(f"page {args.page:#x}: {consumed} -> {len(stream)} bytes, "
          f"{limit - args.page - len(stream)} spare")

    new_blob = bytearray(blob)
    new_blob[args.page:limit] = stream.ljust(limit - args.page, b"\0")
    new_blob = bytes(new_blob)
    new_packed, new_offsets = encode(new_blob, chunk_size)

    (out / cmp_path.name).write_bytes(new_packed)
    (out / ind_path.name).write_bytes(
        struct.pack("<IIII", usize, len(new_packed), len(new_offsets), chunk_size)
        + struct.pack(f"<{len(new_offsets)}I", *new_offsets)
    )
    (out / cmp_path.stem).write_bytes(new_blob)
    print(f"outer .cmp {len(packed)} -> {len(new_packed)} bytes, logical {usize}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
