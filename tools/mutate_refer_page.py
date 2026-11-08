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
  python3 mutate_refer_page.py --selftest

Container/inner-page primitives are shared with ``cmpind_codec`` (M1.16).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmpind_codec  # noqa: E402


def read_ind(path: Path):
    usize, csize, count, chunk_size, offsets = cmpind_codec.read_ind(path)
    return usize, csize, count, chunk_size, list(offsets)


def decode(packed: bytes, offsets: list[int]) -> bytes:
    return cmpind_codec.decode_blob(packed, offsets, strict_nonfinal=False)


def encode(blob: bytes, chunk_size: int):
    return cmpind_codec.encode_chunks(blob, chunk_size, compress=cmpind_codec.factory_compress)


def selftest() -> int:
    import zlib

    inner = b"HELLO@" * 40
    st = cmpind_codec.factory_compress(inner)
    blob = st + b"\x00" * 0x100
    inn, consumed, slot, _ = cmpind_codec.inner_stream_slot(blob, 0, require_zero_padding=False)
    assert inn == inner and consumed == len(st)
    patched = bytearray(inner)
    patched[0:1] = b"J"
    new_st = cmpind_codec.factory_compress(bytes(patched))
    assert len(new_st) <= slot
    assert zlib.decompress(new_st) == bytes(patched)
    print("mutate_refer_page selftest: OK (1/1 checks)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmp", nargs="?")
    ap.add_argument("ind", nargs="?")
    ap.add_argument("outdir", nargs="?")
    ap.add_argument("--page", type=lambda s: int(s, 0))
    ap.add_argument("--patch", action="append",
                    help="inner_offset:hexbytes, repeatable")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not (args.cmp and args.ind and args.outdir and args.page is not None and args.patch):
        ap.error("CMP IND OUTDIR --page --patch are required (or --selftest)")

    cmp_path, ind_path = Path(args.cmp), Path(args.ind)
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    usize, csize, count, chunk_size, offsets = read_ind(ind_path)
    packed = cmp_path.read_bytes()
    blob = decode(packed, offsets)
    assert len(blob) == usize

    try:
        inner, consumed, slot, _ = cmpind_codec.inner_stream_slot(
            blob, args.page, require_zero_padding=False
        )
    except cmpind_codec.FormatError as exc:
        raise SystemExit(str(exc)) from exc
    inner = bytearray(inner)

    for item in args.patch:
        off_s, hex_s = item.split(":")
        off = int(off_s, 0)
        new = bytes.fromhex(hex_s)
        print(f"patch inner {off:#06x}: {inner[off:off+len(new)].hex(' ')} -> {new.hex(' ')}")
        inner[off : off + len(new)] = new

    stream = cmpind_codec.factory_compress(bytes(inner))
    if len(stream) > slot:
        raise SystemExit(f"refusing: {len(stream)} bytes does not fit in {slot}")
    print(f"page {args.page:#x}: {consumed} -> {len(stream)} bytes, "
          f"{slot - len(stream)} spare")

    new_blob = bytearray(blob)
    new_blob[args.page:args.page + slot] = cmpind_codec.refit_stream_in_slot(stream, slot)
    new_blob = bytes(new_blob)
    new_packed, new_offsets = encode(new_blob, chunk_size)

    (out / cmp_path.name).write_bytes(new_packed)
    (out / ind_path.name).write_bytes(
        cmpind_codec.build_ind(usize, len(new_packed), chunk_size, new_offsets)
    )
    (out / cmp_path.stem).write_bytes(new_blob)
    print(f"outer .cmp {len(packed)} -> {len(new_packed)} bytes, logical {usize}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
