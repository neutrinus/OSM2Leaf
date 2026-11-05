#!/usr/bin/env python3
"""Self-tests for the repository tools, using synthetic data only.

No vendor files are needed. Run from anywhere:

    python3 tools/selftest.py
"""

from __future__ import annotations

import struct
import sys
import tempfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cmpind  # noqa: E402
import drstr  # noqa: E402


def test_cmpind() -> None:
    chunk0 = b"A" * 0x10000
    chunk1 = b"B" * 1000
    stream0 = zlib.compress(chunk0)
    stream1 = zlib.compress(chunk1)
    payload = stream0 + stream1

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cmp_path = tmp_path / "TEST.DAT.cmp"
        ind_path = tmp_path / "TEST.DAT.ind"
        cmp_path.write_bytes(payload)
        ind_path.write_bytes(
            struct.pack("<IIII", len(chunk0) + len(chunk1), len(payload), 2, 0x10000)
            + struct.pack("<II", 0, len(stream0))
        )

        blob, info = cmpind.decode(cmp_path, ind_path)
        assert blob == chunk0 + chunk1, "cmpind round-trip mismatch"
        assert info["chunk_count"] == 2
        assert len(info["offsets"]) == 2

        usize, csize, count, chunk_size, offsets = cmpind.read_index(ind_path)
        assert (usize, csize, count, chunk_size) == (
            len(chunk0) + len(chunk1),
            len(payload),
            2,
            0x10000,
        )
        assert offsets == (0, len(stream0))

        out = tmp_path / "TEST.DAT"
        cmpind.main(["extract", str(cmp_path), "-o", str(out)])
        assert out.read_bytes() == chunk0 + chunk1

        cmpind.main(["verify", str(tmp_path)])


def test_drstr() -> None:
    # Node 0 is the root "/". The table starts at 0x00; there is no header.
    listing_offset = 40
    node = (
        b"/\0\0\0\0\0\0\0"
        + b"\0" * 12
        + struct.pack("<HH", 1, 1)  # next=1, parent_plus_one=1 (root)
        + struct.pack("<I", 1)      # entry_count
        + struct.pack("<II", 0, 0)  # reserved
        + struct.pack("<I", listing_offset)
    )
    assert len(node) == 40

    entry = (
        b"FILE.TXT\0\0\0\0\0"       # 13-byte name field
        + b"\0" * 9
        + struct.pack("<H", 0)      # type 0 = file
        + struct.pack("<I", 0)      # reserved
        + struct.pack("<I", 123)    # logical size
    )
    assert len(entry) == 32

    tree = drstr.parse(node + entry)
    assert tree["node_count"] == 1
    assert tree["table_end"] == 40
    assert tree["nodes"][0]["name"] == "/"
    assert tree["nodes"][0]["parent"] == 0
    assert tree["nodes"][0]["entry_count"] == 1
    assert tree["nodes"][0]["entries"][0]["name"] == "FILE.TXT"
    assert tree["nodes"][0]["entries"][0]["value"] == 123


def main() -> int:
    test_cmpind()
    test_drstr()
    print("selftest: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
