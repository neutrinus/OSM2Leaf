#!/usr/bin/env python3
"""List Latin-1 text strings inside the inner zlib pages of a REFER001 file.

The POI/street display names in a decompressed REFER*.DAT are plain text
inside small zlib pages, not encrypted and not a custom codec. This tool makes
the page offset and the text visible so a same-length rename can be chosen.

Usage:
  python3 scan_refer_names.py REFER001/POINT032.DAT.cmp [--min 5]
"""

from __future__ import annotations

import argparse
import re
import struct
import zlib
from pathlib import Path


def load(cmp_path: Path):
    ind = cmp_path.with_suffix(".ind").read_bytes()
    usize, csize, count, chunk_size = struct.unpack_from("<IIII", ind, 0)
    offs = struct.unpack_from(f"<{count}I", ind, 16)
    packed = cmp_path.read_bytes()
    parts = []
    for i, start in enumerate(offs):
        end = offs[i + 1] if i + 1 < len(offs) else len(packed)
        parts.append(zlib.decompress(packed[start:end]))
    return b"".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmp")
    ap.add_argument("--min", type=int, default=5)
    args = ap.parse_args()

    blob = load(Path(args.cmp))
    print(f"{args.cmp}: {len(blob)} bytes decoded")
    pos = 0
    while True:
        page = blob.find(b"\x78\x9c", pos)
        if page < 0:
            break
        try:
            d = zlib.decompressobj()
            inner = d.decompress(blob[page:])
            used = len(blob[page:]) - len(d.unused_data)
        except zlib.error:
            pos = page + 2
            continue
        found = False
        for m in re.finditer(rb"[ -~]{%d,}" % args.min, inner):
            if not found:
                print(f"\npage {page:#06x}  inflated {len(inner)}  compressed {used}")
                found = True
            print(f"  +{m.start():#06x}  {m.group().decode('latin-1')}")
        pos = page + max(used, 2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
