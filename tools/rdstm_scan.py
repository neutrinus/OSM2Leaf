#!/usr/bin/env python3
"""Structure scan for ``RDSTM001.DAT`` (Leaf ZE0, EU 2011 image).

Verified against ``RDSTM001.DAT`` (23,335,680 bytes,
SHA-256 ``f822044c0aab75327b9fb484e9a4c7c8dd5938b21efaacec0e5b2d8b23ab3e49``)
from the image ``105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307``.

Negative result recorded here: a sequential zlib scan from 0x200 finds **no**
streams.  The file is uncompressed structured binary (mostly 16-bit fields).

Sub-commands:

    layout   block map: header, zero/fill runs, entropy per 64 KiB
    zlib     sequential zlib scan (expected: no streams)
    codes    16-bit "mesh-like" codes found in the 0x1000 table, optionally
             compared with the catalog codes stored in LCTBL001.DAT
    dump     hexdump of a byte range
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import math
import sys
import zlib
from pathlib import Path

EXPECTED_SHA256 = "f822044c0aab75327b9fb484e9a4c7c8dd5938b21efaacec0e5b2d8b23ab3e49"
EXPECTED_SIZE = 23_335_680
HEADER_SIZE = 512
CATALOG_START = 0x1000  # first structured table after the 0x200..0xfff padding


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def entropy(blob: bytes) -> float:
    if not blob:
        return 0.0
    counts = collections.Counter(blob)
    size = len(blob)
    return -sum((n / size) * math.log2(n / size) for n in counts.values())


def runs_of(data: bytes, value: int, minimum: int = 1024) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    index = 0
    size = len(data)
    while index < size:
        if data[index] == value:
            end = index
            while end < size and data[end] == value:
                end += 1
            if end - index >= minimum:
                out.append((index, end))
            index = end
        else:
            index += 1
    return out


def cmd_layout(args: argparse.Namespace) -> int:
    data = Path(args.file).read_bytes()
    print(f"file        {args.file}")
    print(f"size        {len(data)}")
    print(f"sha256      {sha256(Path(args.file))}")
    if len(data) != EXPECTED_SIZE:
        print(f"warning: size differs from documented {EXPECTED_SIZE}", file=sys.stderr)

    first_nonzero = next((i for i in range(HEADER_SIZE, len(data)) if data[i]), None)
    print(f"first non-zero after header  {first_nonzero:#x}")

    zero_runs = [r for r in runs_of(data, 0x00, 64) if r[1] - r[0] >= 1024]
    fill_runs = [r for r in runs_of(data, 0xFF, 64) if r[1] - r[0] >= 128]
    print("zero runs >= 1024 bytes")
    for start, end in zero_runs[:5]:
        print(f"  {start:#08x}..{end:#08x}  {end - start} bytes")
    print("0xff runs >= 128 bytes")
    for start, end in fill_runs[:5]:
        print(f"  {start:#08x}..{end:#08x}  {end - start} bytes")

    print("entropy per 64 KiB")
    block = 1 << 16
    for offset in range(0, len(data), block):
        chunk = data[offset : offset + block]
        zeros = chunk.count(0) / len(chunk)
        small = sum(
            1
            for i in range(0, len(chunk) - 1, 2)
            if int.from_bytes(chunk[i : i + 2], "big") < 0x100
        ) / (len(chunk) / 2)
        if args.every or offset % (block * 32) == 0:
            print(
                f"  {offset:#08x}  H={entropy(chunk):.2f}  "
                f"zero={zeros:.2f}  small16={small:.2f}"
            )
    return 0


def cmd_zlib(args: argparse.Namespace) -> int:
    data = Path(args.file).read_bytes()
    hits = 0
    offset = HEADER_SIZE
    while offset < len(data) - 4:
        nxt = data.find(b"\x78\x9c", offset)
        if nxt < 0:
            break
        try:
            engine = zlib.decompressobj()
            payload = engine.decompress(data[nxt:])
            if engine.eof and len(payload) > 200:
                hits += 1
                print(f"{nxt:#08x} -> {len(payload)} bytes")
                offset = nxt + 1
                continue
        except zlib.error:
            pass
        offset = nxt + 1
    print(f"zlib streams found: {hits}")

    if args.bruteforce:
        # Raw deflate and gzip have no magic, so probe a fixed grid instead.
        probes = 0
        raw_hits = 0
        for offset in range(HEADER_SIZE, min(len(data), args.limit), args.step):
            for wbits in (-15, 31):
                probes += 1
                try:
                    engine = zlib.decompressobj(wbits)
                    payload = engine.decompress(data[offset : offset + 300_000])
                except zlib.error:
                    continue
                if engine.eof and len(payload) > 1000:
                    raw_hits += 1
                    print(f"raw/gzip {offset:#08x} wbits={wbits} -> {len(payload)} bytes")
        print(
            f"raw-deflate/gzip probes: {probes} over "
            f"{HEADER_SIZE:#x}..{min(len(data), args.limit):#x} step {args.step:#x}, "
            f"hits: {raw_hits}"
        )
    return 0


def catalog_codes(lctbl: bytes) -> list[int]:
    """Read the 2-byte code stored in each LCTBL 'Location Data' descriptor."""
    name = b"Location Data"
    codes: list[int] = []
    index = 0
    while True:
        index = lctbl.find(name, index)
        if index < 0:
            break
        header = lctbl[max(0, index - 32) : index]
        if len(header) == 32:
            codes.append(int.from_bytes(header[28:30], "big"))
        index += 1
    return codes


def cmd_codes(args: argparse.Namespace) -> int:
    data = Path(args.file).read_bytes()
    # The first table starts at 0x1000; the 16-bit code sits at +14 of each
    # 16-byte row for the first rows (framing drifts later, see docs/format/rdstm.md).
    rows = []
    for offset in range(CATALOG_START, args.limit, 16):
        code = int.from_bytes(data[offset + 14 : offset + 16], "big")
        rows.append((offset, code))
    print("16-byte rows from 0x1000 (last u16 = candidate mesh code)")
    for offset, code in rows[: args.rows]:
        words = [
            int.from_bytes(data[offset + i : offset + i + 2], "big")
            for i in range(0, 16, 2)
        ]
        print(f"  {offset:#06x}  {' '.join(f'{w:04x}' for w in words)}")

    if args.lctbl:
        codes = catalog_codes(Path(args.lctbl).read_bytes())
        print(f"LCTBL catalog codes ({len(codes)}):")
        print("  " + " ".join(f"{c:04x}" for c in codes[:30]))
        found = {code for _, code in rows}
        overlap = sorted(found & set(codes))
        print(f"RDSTM codes also present in the LCTBL catalog: {len(overlap)}")
        print("  " + " ".join(f"{c:04x}" for c in overlap))
    return 0


def cmd_dump(args: argparse.Namespace) -> int:
    data = Path(args.file).read_bytes()
    start = int(args.offset, 0)
    end = min(start + args.length, len(data))
    for offset in range(start, end, 16):
        chunk = data[offset : offset + 16]
        text = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in chunk)
        print(f"{offset:#08x}  {' '.join(f'{b:02x}' for b in chunk):<48s}  {text}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_layout = sub.add_parser("layout", help="block map and entropy")
    p_layout.add_argument("file")
    p_layout.add_argument("--every", action="store_true", help="print every 64 KiB block")
    p_layout.set_defaults(func=cmd_layout)

    p_zlib = sub.add_parser("zlib", help="sequential zlib scan")
    p_zlib.add_argument("file")
    p_zlib.add_argument(
        "--bruteforce",
        action="store_true",
        help="also probe raw deflate / gzip on a fixed grid",
    )
    p_zlib.add_argument("--limit", type=lambda v: int(v, 0), default=0x200000)
    p_zlib.add_argument("--step", type=lambda v: int(v, 0), default=0x200)
    p_zlib.set_defaults(func=cmd_zlib)

    p_codes = sub.add_parser("codes", help="dump the 0x1000 table and mesh codes")
    p_codes.add_argument("file")
    p_codes.add_argument("--lctbl", help="compare with LCTBL001.DAT catalog codes")
    p_codes.add_argument("--limit", type=lambda v: int(v, 0), default=0x1100)
    p_codes.add_argument("--rows", type=int, default=16)
    p_codes.set_defaults(func=cmd_codes)

    p_dump = sub.add_parser("dump", help="hexdump")
    p_dump.add_argument("file")
    p_dump.add_argument("offset")
    p_dump.add_argument("--length", type=lambda v: int(v, 0), default=0x100)
    p_dump.set_defaults(func=cmd_dump)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
