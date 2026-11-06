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
        by_upper = {row[0].upper(): row for row in rows}
        if order is not None and relpath in order:
            ordered_rows = []
            seen_upper = set()
            for ref_name in order[relpath]:
                row = by_name.get(ref_name) or by_upper.get(ref_name.upper())
                if row is None:
                    continue
                # Preserve the DRSTR's stored name (factory case may differ from
                # the on-disk/FAT name, e.g. US XMD records ltntbl.dat lowercase).
                ordered_rows.append((ref_name, row[1], row[2]))
                seen_upper.add(row[0].upper())
            for row in sorted(rows, key=lambda r: r[0]):
                if row[0].upper() not in seen_upper:
                    ordered_rows.append(row)
            rows = ordered_rows
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


def _selftest() -> int:
    import tempfile

    with tempfile.TemporaryDirectory(prefix="drstr-ze0-") as tmp:
        root = Path(tmp)
        # Synthetic tree: root has XMD/ with one file whose on-disk name is
        # uppercase but the factory DRSTR records it lowercase (US M4.20 case).
        (root / "XMD").mkdir()
        (root / "XMD" / "LTNTBL.DAT").write_bytes(b"x" * 320)
        first = build(root)
        # Patch the entry name to lowercase in the DRSTR bytes, preserving
        # the 20-byte name field layout used by this builder.
        data = bytearray(first)
        # find XMD node
        n = struct.unpack_from("<I", data, 0x24)[0] // DREC
        patched = bytearray(first)
        for i in range(n):
            b = i * DREC
            name = patched[b:b + NAMELEN].split(b"\0")[0].decode("ascii")
            if name != "XMD":
                continue
            children = struct.unpack_from("<H", patched, b + 0x18)[0]
            off = struct.unpack_from("<I", patched, b + 0x24)[0]
            for j in range(children):
                e = off + j * CREC
                en = patched[e:e + NAMELEN].split(b"\0")[0].decode("ascii")
                if en == "LTNTBL.DAT":
                    patched[e:e + len(b"ltntbl.dat")] = b"ltntbl.dat"
                    # keep rest of 20-byte field zero
                    patched[e + len(b"ltntbl.dat"):e + NAMELEN] = b"\0" * (
                        NAMELEN - len(b"ltntbl.dat"))
        if patched == data:
            print("FAIL: synthetic patch did not change DRSTR")
            return 1
        (root / "DRSTR001.DAT").write_bytes(bytes(patched))
        rebuilt = build(root)
        if rebuilt != bytes(patched):
            diffs = [i for i,(a,b) in enumerate(zip(patched, rebuilt)) if a!=b]
            print(f"FAIL: case-preserving rebuild differs at {diffs[:5]}")
            return 1
        print("OK: case-preserving round-trip (US name form)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        raise SystemExit(_selftest())
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
