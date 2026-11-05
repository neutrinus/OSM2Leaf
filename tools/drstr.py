#!/usr/bin/env python3
"""Parse ``DRSTR001.DAT``, the Leaf ZE0 map directory index.

Verified against ``DRSTR001.DAT`` from the EU 2011 image
(SHA-256 ``2b7f2fb8901bf18a2ad48334154a6d604c23a775083cb84754626d64417b25f6``).

Layout::

    0x00  u32  0x2f (semantics unknown; NOT the node count)
    0x04  ... zero padding to 0x28
    0x28  39 * 40-byte node records
    0x640 directory entry listings (arrays of 32-byte entries)

Node record (40 bytes), name first::

    +0x00 char name[8]          ASCII, zero padded
    +0x08 u32  zero
    +0x0c u32  zero
    +0x10 u32  zero
    +0x14 u16  next_index       next node index (1-based)
    +0x16 u16  type             0x01 = directory
    +0x18 u32  entry_count      number of entries in this directory
    +0x1c u32  reserved
    +0x20 u32  reserved
    +0x24 u32  listing_offset   offset of this directory's entry list

Entry record (32 bytes)::

    +0x00 char name[12]         "NAME.EXT", zero padded
    +0x0c u8   reserved[10]
    +0x16 u16  type             0 = file, 2 = directory
    +0x18 u32  reserved
    +0x1c u32  size             logical size for files; opaque for directories
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

HEADER_SIZE = 0x28
NODE_SIZE = 40
ENTRY_SIZE = 32


def parse(data: bytes) -> dict:
    if len(data) < HEADER_SIZE:
        raise ValueError("file too short for DRSTR header")

    (header_word,) = struct.unpack_from("<I", data, 0)
    nodes: list[dict] = []
    offset = HEADER_SIZE
    while offset + NODE_SIZE <= len(data):
        raw = data[offset : offset + NODE_SIZE]
        name = raw[0:8].split(b"\0")[0].decode("ascii", "replace")
        next_index, node_type = struct.unpack_from("<HH", raw, 0x14)
        entry_count, = struct.unpack_from("<I", raw, 0x18)
        listing_offset, = struct.unpack_from("<I", raw, 0x24)
        # The node table ends where the first listing begins. A real record has
        # a non-zero type and a listing that fits inside the file.
        if (
            not name
            or not name[0].isalnum()
            or node_type == 0
            or listing_offset < HEADER_SIZE
            or listing_offset + entry_count * ENTRY_SIZE > len(data)
        ):
            break
        node = {
            "index": len(nodes),
            "name": name,
            "next_index": next_index,
            "type": node_type,
            "entry_count": entry_count,
            "listing_offset": listing_offset,
        }
        node["entries"] = read_listing(data, listing_offset, entry_count)
        nodes.append(node)
        offset += NODE_SIZE

    return {"header_word": header_word, "node_count": len(nodes), "nodes": nodes}


def read_listing(data: bytes, offset: int, count: int) -> list[dict]:
    entries = []
    for j in range(count):
        start = offset + j * ENTRY_SIZE
        if start + ENTRY_SIZE > len(data):
            break
        raw = data[start : start + ENTRY_SIZE]
        name = raw[:12].split(b"\0")[0].decode("ascii", "replace")
        entry_type, = struct.unpack_from("<H", raw, 0x16)
        value, = struct.unpack_from("<I", raw, 0x1C)
        entries.append(
            {
                "index": j,
                "name": name,
                "type": entry_type,
                "size": value if entry_type == 0 else None,
                "value": value,
            }
        )
    return entries


def cmd_parse(args: argparse.Namespace) -> int:
    data = Path(args.file).read_bytes()
    tree = parse(data)

    if args.json:
        print(json.dumps(tree, indent=2))
        return 0

    print(f"header word : 0x{tree['header_word']:x} ({tree['header_word']})")
    print(f"nodes       : {tree['node_count']}")
    for node in tree["nodes"]:
        print(
            f"[{node['index']:2d}] {node['name']:<12s} type=0x{node['type']:02x} "
            f"entries={node['entry_count']:4d} listing=0x{node['listing_offset']:06x} "
            f"next={node['next_index']}"
        )
        for entry in node["entries"]:
            kind = "dir " if entry["type"] == 2 else "file"
            size = f"{entry['value']:>10d}" if entry["type"] == 0 else ""
            print(f"       {kind} {entry['name']:<16s} {size}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_parse = sub.add_parser("parse", help="print nodes and listings")
    p_parse.add_argument("file")
    p_parse.add_argument("--json", action="store_true", help="emit JSON")
    p_parse.set_defaults(func=cmd_parse)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
