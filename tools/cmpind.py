#!/usr/bin/env python3
"""Decode and verify Leaf ZE0 ``.cmp`` / ``.ind`` containers.

Verified against all 194 pairs in the EU 2011 image
``LEAF_2011-2012_QSD-309-101_navi158_eu.img`` (SHA-256
``105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307``).

Format::

    u32 uncompressed_size
    u32 compressed_size        # must equal the .cmp file size
    u32 chunk_count
    u32 chunk_size              # 0x10000 in every observed file
    u32 chunk_offset[chunk_count]

Each chunk is an independent zlib stream.  Concatenating the decompressed
chunks yields exactly ``uncompressed_size`` bytes.
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

HEADER = 16


class FormatError(Exception):
    pass


def read_index(ind_path: Path) -> tuple[int, int, int, int, tuple[int, ...]]:
    data = ind_path.read_bytes()
    if len(data) < HEADER:
        raise FormatError(f"{ind_path}: too short for .ind header")
    usize, csize, count, chunk_size = struct.unpack_from("<IIII", data, 0)
    expected = HEADER + 4 * count
    if len(data) != expected:
        raise FormatError(
            f"{ind_path}: size {len(data)} != 16 + 4*{count} = {expected}"
        )
    offsets = struct.unpack_from(f"<{count}I", data, HEADER)
    return usize, csize, count, chunk_size, offsets


def chunk_ranges(cmp_size: int, offsets: tuple[int, ...]):
    for i, start in enumerate(offsets):
        end = offsets[i + 1] if i + 1 < len(offsets) else cmp_size
        yield i, start, end


def decode(cmp_path: Path, ind_path: Path | None = None) -> tuple[bytes, dict]:
    if ind_path is None:
        if cmp_path.suffix != ".cmp":
            raise FormatError(f"{cmp_path}: expected a .cmp file")
        ind_path = cmp_path.with_suffix(".ind")

    usize, csize, count, chunk_size, offsets = read_index(ind_path)
    packed = cmp_path.read_bytes()

    if csize != len(packed):
        raise FormatError(
            f"{cmp_path}: .ind says {csize} compressed bytes, file has {len(packed)}"
        )

    parts: list[bytes] = []
    for i, start, end in chunk_ranges(len(packed), offsets):
        if not (0 <= start < end <= len(packed)):
            raise FormatError(f"{cmp_path}: chunk {i} range {start}:{end} out of bounds")
        try:
            part = zlib.decompress(packed[start:end])
        except zlib.error as exc:
            raise FormatError(f"{cmp_path}: chunk {i} ({start}:{end}): {exc}") from exc
        if i != count - 1 and len(part) != chunk_size:
            raise FormatError(
                f"{cmp_path}: chunk {i} decoded to {len(part)}, expected {chunk_size}"
            )
        parts.append(part)

    blob = b"".join(parts)
    if len(blob) != usize:
        raise FormatError(
            f"{cmp_path}: decoded {len(blob)} bytes, .ind declares {usize}"
        )

    info = {
        "uncompressed_size": usize,
        "compressed_size": csize,
        "chunk_count": count,
        "chunk_size": chunk_size,
        "offsets": offsets,
        "ind_path": ind_path,
    }
    return blob, info


def cmd_info(args: argparse.Namespace) -> int:
    usize, csize, count, chunk_size, offsets = read_index(Path(args.ind))
    print(f"index          {args.ind}")
    print(f"uncompressed   {usize} bytes")
    print(f"compressed     {csize} bytes")
    print(f"chunks         {count}")
    print(f"chunk size     {chunk_size}")
    print("offsets        " + ", ".join(f"0x{o:x}" for o in offsets[:10]))
    if len(offsets) > 10:
        print(f"               ... ({len(offsets) - 10} more)")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    cmp_path = Path(args.cmp)
    ind_path = Path(args.ind) if args.ind else None
    blob, info = decode(cmp_path, ind_path)

    out = Path(args.output)
    if out.resolve() == cmp_path.resolve():
        print("error: refusing to overwrite input", file=sys.stderr)
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    print(
        f"{cmp_path} -> {out}: {len(blob)} bytes "
        f"({info['chunk_count']} chunk(s))",
        file=sys.stderr,
    )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    root = Path(args.directory)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    inds = sorted(root.glob("*.ind"))
    if not inds:
        print(f"error: no .ind files in {root}", file=sys.stderr)
        return 2

    ok = 0
    failures: list[tuple[Path, str]] = []
    total_uncompressed = 0
    total_compressed = 0

    for ind in inds:
        cmp_path = ind.with_suffix(".cmp")
        if not cmp_path.exists():
            failures.append((ind, f"missing {cmp_path.name}"))
            continue
        try:
            blob, info = decode(cmp_path, ind)
        except (FormatError, OSError) as exc:
            failures.append((ind, str(exc)))
            continue
        ok += 1
        total_uncompressed += info["uncompressed_size"]
        total_compressed += info["compressed_size"]

    print(f"checked   {len(inds)} pair(s)")
    print(f"ok        {ok}")
    print(f"failed    {len(failures)}")
    print(f"logical   {total_uncompressed} bytes")
    print(f"stored    {total_compressed} bytes")
    for path, reason in failures:
        print(f"FAIL {path}: {reason}", file=sys.stderr)
    return 0 if not failures else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_info = sub.add_parser("info", help="print an .ind header")
    p_info.add_argument("ind")
    p_info.set_defaults(func=cmd_info)

    p_extract = sub.add_parser("extract", help="decompress a .cmp into a .DAT")
    p_extract.add_argument("cmp")
    p_extract.add_argument("--ind", help="index path (default: same stem with .ind)")
    p_extract.add_argument("-o", "--output", required=True)
    p_extract.set_defaults(func=cmd_extract)

    p_verify = sub.add_parser("verify", help="verify every .cmp/.ind pair in a directory")
    p_verify.add_argument("directory")
    p_verify.set_defaults(func=cmd_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (FormatError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
