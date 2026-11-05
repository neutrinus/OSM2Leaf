#!/usr/bin/env python3
"""Parse ``DRSTR001.DAT``, the Leaf ZE0 map directory index.

Verified against ``DRSTR001.DAT`` from the EU 2011 image
(SHA-256 ``2b7f2fb8901bf18a2ad48334154a6d604c23a775083cb84754626d64417b25f6``)
and cross-checked on 2014/2016 map sets.

There is **no file header**. The file starts with the root node record.

Layout::

    0x0000  40 * 40-byte node records (node 0 = root "/")
    0x0640  directory entry listings (324 * 32 bytes in the 2011 sample)
    EOF

In the 2011 sample: ``40 * 40 + 324 * 32 = 11968`` = file size exactly.

Node record (40 bytes), name first::

    +0x00 char name[8]          ASCII, zero padded ("/" for root)
    +0x08 u8   unknown[12]
    +0x14 u16  next_index       always index + 1; last = node count
    +0x16 u16  parent_index+1   0 means none; root points to itself
    +0x18 u32  entry_count
    +0x1c u32  reserved (zero)
    +0x20 u32  reserved (zero)
    +0x24 u32  listing_offset

Entry record (32 bytes)::

    +0x00 char name[13]         "NAME.EXT", zero padded; 13 bytes, not 12
    +0x0d u8   unknown[9]
    +0x16 u16  type             0 = file, 2 = directory
    +0x18 u32  reserved (zero)
    +0x1c u32  value            file: logical size; dir: recursive subtree total

Earlier notes claimed a 0x28-byte header, a 0x2f node count and a one-node
shift. All three were wrong: 0x2f is the ASCII '/' of the root name.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

NODE_SIZE = 40
ENTRY_SIZE = 32
NAME_LEN = 8
ENTRY_NAME_LEN = 13


def parse(data: bytes) -> dict:
    nodes: list[dict] = []
    prev_listing = -1
    offset = 0

    while offset + NODE_SIZE <= len(data):
        raw = data[offset : offset + NODE_SIZE]
        name = raw[:NAME_LEN].split(b"\0")[0].decode("ascii", "replace")
        if not name or not all(0x20 <= ord(ch) < 0x7F for ch in name):
            break
        next_index, parent_plus_one = struct.unpack_from("<HH", raw, 0x14)
        entry_count, = struct.unpack_from("<I", raw, 0x18)
        reserved0, reserved1 = struct.unpack_from("<II", raw, 0x1C)
        listing_offset, = struct.unpack_from("<I", raw, 0x24)

        # A record is plausible only if its listing lies after the table,
        # fits in the file, and listings do not move backwards.
        table_end = offset + NODE_SIZE
        if listing_offset < table_end:
            break
        if listing_offset + entry_count * ENTRY_SIZE > len(data):
            break
        if listing_offset < prev_listing:
            break

        prev_listing = listing_offset
        node = {
            "index": len(nodes),
            "offset": offset,
            "name": name,
            "next_index": next_index,
            "parent": parent_plus_one - 1 if parent_plus_one else None,
            "entry_count": entry_count,
            "reserved0": reserved0,
            "reserved1": reserved1,
            "listing_offset": listing_offset,
            "entries": read_listing(data, listing_offset, entry_count),
        }
        nodes.append(node)
        offset += NODE_SIZE

    if not nodes:
        raise ValueError("no node records found")

    return {
        "node_count": len(nodes),
        "table_end": len(nodes) * NODE_SIZE,
        "nodes": nodes,
    }


def read_listing(data: bytes, offset: int, count: int) -> list[dict]:
    entries = []
    for j in range(count):
        start = offset + j * ENTRY_SIZE
        if start + ENTRY_SIZE > len(data):
            break
        raw = data[start : start + ENTRY_SIZE]
        name = raw[:ENTRY_NAME_LEN].split(b"\0")[0].decode("ascii", "replace")
        entry_type, = struct.unpack_from("<H", raw, 0x16)
        reserved, = struct.unpack_from("<I", raw, 0x18)
        value, = struct.unpack_from("<I", raw, 0x1C)
        entries.append(
            {
                "index": j,
                "name": name,
                "type": entry_type,
                "reserved": reserved,
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

    print(f"nodes       : {tree['node_count']} (node 0 = root '/')")
    print(f"node table  : 0x0000..0x{tree['table_end']:04x}")
    for node in tree["nodes"]:
        parent = "none" if node["parent"] is None else str(node["parent"])
        print(
            f"[{node['index']:2d}] {node['name']:<12s} parent={parent:<4s} "
            f"next={node['next_index']:<3d} entries={node['entry_count']:4d} "
            f"listing=0x{node['listing_offset']:06x}"
        )
        for entry in node["entries"]:
            kind = "dir " if entry["type"] == 2 else "file"
            print(f"       {kind} {entry['name']:<16s} {entry['value']:>12d}")
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
