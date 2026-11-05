#!/usr/bin/env python3
"""DRSTR001.DAT reader/writer for the EU 2011 ZE0 card.

Correction to tools/drstr.py: there is no 0x28-byte header. Record 0 IS the
root directory and its name is "/" (byte 0x2f) -- which tools/drstr.py has been
reading as a mysterious "header word 0x2f". The 40 records run 0x000..0x63f and
the first child block starts at 0x640.

Record (0x28):
  +0x00 char[20] name
  +0x14 u16 own id (1-based)
  +0x16 u16 parent id (root = itself)
  +0x18 u16 child count
  +0x1a 10 bytes zero
  +0x24 u32 absolute offset of the child block

Child (0x20):
  +0x00 char[20] name
  +0x14 u16 zero
  +0x16 u16 2 = dir, 0 = file
  +0x18 u32 zero
  +0x1c u32 size (file: logical size; dir: sum of listed children mod 2^32)
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

DREC, CREC, NAMELEN = 0x28, 0x20, 20


def read(path: Path) -> dict:
    d = path.read_bytes()
    n = len(d) // DREC if len(d) >= DREC else 0
    # discover the record count from the first record's child offset
    first_off = struct.unpack_from("<I", d, 0x24)[0] if len(d) >= 0x28 else 0
    n = first_off // DREC if first_off % DREC == 0 else 0
    dirs = []
    for i in range(n):
        base = i * DREC
        name = d[base : base + NAMELEN].split(b"\0")[0].decode("ascii", "replace")
        own, parent, children = struct.unpack_from("<HHH", d, base + 0x14)
        off = struct.unpack_from("<I", d, base + 0x24)[0]
        entries = []
        for j in range(children):
            e = off + j * CREC
            ename = d[e : e + NAMELEN].split(b"\0")[0].decode("ascii", "replace")
            etype = struct.unpack_from("<H", d, e + 0x16)[0]
            size = struct.unpack_from("<I", d, e + 0x1C)[0]
            entries.append({"name": ename, "type": etype, "size": size})
        dirs.append(
            {"name": name, "own": own, "parent": parent, "children": children,
             "offset": off, "entries": entries}
        )
    return {"count": n, "dirs": dirs}


def listing(root: Path):
    out = []
    for e in os.scandir(root):
        if e.name == "DRSTR001.DAT":
            continue
        if e.name.endswith(".ind"):
            continue
        if e.name.endswith(".cmp"):
            ind = Path(str(e.path)[:-4] + ".ind")
            size = struct.unpack("<I", ind.read_bytes()[:4])[0]
            out.append((e.name[:-4], False, size))
        elif e.is_dir():
            out.append((e.name, True, tree_size(Path(e.path))))
        else:
            out.append((e.name, False, e.stat().st_size))
    return out


def tree_size(path: Path) -> int:
    return sum(size for _, _, size in listing(path)) & 0xFFFFFFFF


def build(root: Path) -> bytes:
    # breadth-first, readdir order (matches the card's own index)
    dirs = []
    queue = [(root, "/", 1)]
    while queue:
        path, name, parent = queue.pop(0)
        my_id = len(dirs) + 1
        dirs.append((path, name, parent))
        for child, is_dir, _ in listing(path):
            if is_dir:
                queue.append((path / child, child, my_id))

    blocks = [[(n, d, s & 0xFFFFFFFF) for n, d, s in listing(p)] for p, _, _ in dirs]
    out = bytearray(len(dirs) * DREC)
    off = len(out)
    for i, ((_, name, parent), rows) in enumerate(zip(dirs, blocks)):
        struct.pack_into("<20sHHH", out, i * DREC, name.encode().ljust(20, b"\0"),
                         i + 1, parent, len(rows))
        struct.pack_into("<I", out, i * DREC + 0x24, off)
        off += len(rows) * CREC
    for rows in blocks:
        for name, is_dir, size in rows:
            out += struct.pack("<20sHHII", name.encode().ljust(20, b"\0"), 0,
                               2 if is_dir else 0, 0, size)
    return bytes(out)


if __name__ == "__main__":
    root = Path(sys.argv[1])
    ref = Path(sys.argv[2])
    got = build(root)
    want = ref.read_bytes()
    print(f"built {len(got)} bytes, reference {len(want)} bytes")
    if got == want:
        print("BYTE-IDENTICAL")
    else:
        diffs = [i for i in range(min(len(got), len(want))) if got[i] != want[i]]
        print(f"{len(diffs)} differing bytes, first at {diffs[0]:#x}" if diffs else "prefix equal")
        for i in diffs[:20]:
            print(f"  {i:#06x}: {want[i]:02x} -> {got[i]:02x}")
