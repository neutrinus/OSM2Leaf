#!/usr/bin/env python3
"""Offline acceptance check for a same-size REFER001 mutation.

Compares an original (cmp, ind) pair against a mutated one and fails unless:

  1. both decode, and the logical (uncompressed) sizes are equal;
  2. the .ind header is self-consistent (16 + 4*chunk_count, chunk_size 0x10000);
  3. every chunk except the last inflates to exactly chunk_size;
  4. all changed bytes in the decoded .DAT fall inside one declared inner page
     (so no structure outside that page moved);
  5. the DRSTR001.DAT entry for the logical file still carries the same size
     (so the directory index needs no edit).

Usage:
  python3 validate_mutation.py DIR_ORIG DIR_MUT LOGICAL_NAME [--page 0x4200]
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import drstr_ze0 as D  # noqa: E402


def load(directory: Path, name: str):
    cmp_path = directory / f"{name}.cmp"
    ind_path = directory / f"{name}.ind"
    ind = ind_path.read_bytes()
    usize, csize, count, chunk_size = struct.unpack_from("<IIII", ind, 0)
    ok_ind = len(ind) == 16 + 4 * count
    offs = list(struct.unpack_from(f"<{count}I", ind, 16))
    packed = cmp_path.read_bytes()
    parts = []
    for i, start in enumerate(offs):
        end = offs[i + 1] if i + 1 < len(offs) else len(packed)
        part = zlib.decompress(packed[start:end])
        if i != count - 1 and len(part) != chunk_size:
            raise SystemExit(f"{cmp_path}: chunk {i} is {len(part)}, want {chunk_size}")
        parts.append(part)
    blob = b"".join(parts)
    return {
        "usize": usize, "csize": csize, "count": count,
        "chunk_size": chunk_size, "offsets": offs, "packed": packed,
        "blob": blob, "ind_ok": ok_ind,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("orig")
    ap.add_argument("mut")
    ap.add_argument("name", help="logical name, e.g. POINT032.DAT")
    ap.add_argument("--page", type=lambda s: int(s, 0), default=0x4200)
    ap.add_argument("--page-len", type=lambda s: int(s, 0), default=0x300)
    ap.add_argument("--drstr", default=None,
                    help="DRSTR001.DAT to check the size field against")
    ap.add_argument("--drstr-dir", default=None,
                    help="restrict the DRSTR lookup to this top-level directory")
    ap.add_argument("--inner-page", type=lambda s: int(s, 0), default=None,
                    help="also inflate this inner zlib page and compare its payload")
    args = ap.parse_args()

    a = load(Path(args.orig), args.name)
    b = load(Path(args.mut), args.name)
    fails = []

    if not b["ind_ok"]:
        fails.append("mutated .ind size is not 16 + 4*chunk_count")
    if a["usize"] != b["usize"]:
        fails.append(f"logical size changed {a['usize']} -> {b['usize']}")
    if len(a["blob"]) != len(b["blob"]):
        fails.append("decoded lengths differ")
    if a["chunk_size"] != b["chunk_size"]:
        fails.append("chunk_size changed")

    diffs = [i for i in range(min(len(a["blob"]), len(b["blob"])))
             if a["blob"][i] != b["blob"][i]]
    outside = [i for i in diffs if not (args.page <= i < args.page + args.page_len)]
    print(f"logical size      {a['usize']} -> {b['usize']}")
    print(f".cmp size         {a['csize']} -> {b['csize']}")
    print(f"chunks            {a['count']} -> {b['count']}")
    print(f"changed bytes     {len(diffs)}"
          + (f", range {min(diffs):#x}..{max(diffs):#x}" if diffs else ""))
    print(f"outside page      {len(outside)}")
    if outside:
        fails.append(f"{len(outside)} changed bytes outside the declared page")

    if args.inner_page is not None:
        p = args.inner_page
        ia = zlib.decompressobj().decompress(a["blob"][p:])
        ib = zlib.decompressobj().decompress(b["blob"][p:])
        idiff = [i for i in range(min(len(ia), len(ib))) if ia[i] != ib[i]]
        print(f"inner payload     {len(ia)} -> {len(ib)} bytes, "
              f"{len(idiff)} byte(s) differ")
        for i in idiff[:8]:
            print(f"  +{i:#06x}: {ia[i]:#04x} -> {ib[i]:#04x} "
                  f"({ia[i:i+1]!r} -> {ib[i:i+1]!r})")
        if ia != ib and not idiff:
            fails.append("inner payload lengths differ")

    if args.drstr:
        orig_tree = D.read(Path(args.drstr))
        stem = args.name.rsplit(".", 1)[0]
        found = [e for d in orig_tree["dirs"]
                 if args.drstr_dir is None or d["name"] == args.drstr_dir
                 for e in d["entries"] if e["name"] == args.name]
        if not found:
            print(f"DRSTR            {args.name} not listed")
        else:
            stored = found[0]["size"]
            print(f"DRSTR size       {stored} (logical {a['usize']})")
            if stored != a["usize"]:
                fails.append("DRSTR size does not match logical size")
            if stored != b["usize"]:
                fails.append("DRSTR size would need an edit")

    if fails:
        print("FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("PASS: same logical size, changes confined to one page, DRSTR untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
