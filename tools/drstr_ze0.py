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
DUMP_ARTIFACTS = {".fseventsd", ".Spotlight-V100", ".Trashes", "System Volume Information"}


def is_dump_artifact(name: str, ignore: bool = False) -> bool:
    return bool(ignore) and (name.startswith("._") or name in DUMP_ARTIFACTS)


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


def listing(root: Path, ignore_dump: bool = False):
    out = []
    for e in os.scandir(root):
        if is_dump_artifact(e.name, ignore_dump):
            continue
        if e.name == "DRSTR001.DAT":
            continue
        if e.name.endswith(".ind"):
            continue
        if e.name.endswith(".cmp"):
            ind = Path(str(e.path)[:-4] + ".ind")
            size = struct.unpack("<I", ind.read_bytes()[:4])[0]
            out.append((e.name[:-4], False, size))
        elif e.is_dir():
            out.append((e.name, True, tree_size(Path(e.path), ignore_dump)))
        else:
            out.append((e.name, False, e.stat().st_size))
    return out


def tree_size(path: Path, ignore_dump: bool = False) -> int:
    return sum(size for _, _, size in listing(path, ignore_dump)) & 0xFFFFFFFF


def _read_order(data: bytes) -> dict[str, list[str]]:
    """Recover directory/file order from an existing DRSTR001.DAT."""
    dirs: list[dict] = []
    off = 0
    while off + DREC <= len(data):
        raw = data[off:off + DREC]
        name = raw[:NAMELEN].split(b"\0")[0].decode("ascii", "replace")
        if not name:
            break
        own, parent, children = struct.unpack_from("<HHH", raw, 0x14)
        listing_off = struct.unpack_from("<I", raw, 0x24)[0]
        entries = []
        for j in range(children):
            e = listing_off + j * CREC
            if e + CREC > len(data):
                break
            ename = data[e:e + NAMELEN].split(b"\0")[0].decode("ascii", "replace")
            entries.append(ename)
        dirs.append({"own": own, "parent": parent, "name": name,
                     "entries": entries})
        off += DREC

    paths: dict[int, str] = {}
    order: dict[str, list[str]] = {}
    for i, node in enumerate(dirs):
        if i == 0:
            path = ""
        else:
            parent_idx = node["parent"] - 1
            parent_path = paths.get(parent_idx, "")
            path = f"{parent_path}/{node['name']}".strip("/")
        paths[i] = path
        order[path] = node["entries"]
    return order


def build(root: Path, ignore_dump: bool = False,
         order: dict[str, list[str]] | None = None) -> bytes:
    if order is None:
        ref = root / "DRSTR001.DAT"
        if ref.is_file():
            try:
                order = _read_order(ref.read_bytes())
            except (OSError, ValueError):
                order = None

    # breadth-first.  Preserve an existing DRSTR's order when validating an
    # unchanged tree; otherwise use a deterministic sorted order.
    dirs = []
    queue = [(root, "", "/", 1)]
    while queue:
        path, relpath, name, parent = queue.pop(0)
        my_id = len(dirs) + 1
        rows = listing(path, ignore_dump)
        by_name = {row[0]: row for row in rows}
        if order is not None and relpath in order:
            ordered = [name for name in order[relpath] if name in by_name]
            ordered += sorted(name for name in by_name if name not in set(order[relpath]))
            rows = [by_name[name] for name in ordered]
        else:
            rows = sorted(rows, key=lambda row: row[0])
        dirs.append((path, relpath, name, parent, rows))
        for row in rows:
            child = row[0]
            if not row[1]:
                continue
            child_rel = f"{relpath}/{child}".strip("/")
            queue.append((path / child, child_rel, child, my_id))

    blocks = [[(n, d, s & 0xFFFFFFFF) for n, d, s in rowset]
              for _, _, _, _, rowset in dirs]
    out = bytearray(len(dirs) * DREC)
    off = len(out)
    for i, (entry, rows) in enumerate(zip(dirs, blocks)):
        _, _, name, parent, _ = entry
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
