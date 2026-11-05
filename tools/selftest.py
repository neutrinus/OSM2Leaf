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
    header = struct.pack("<I", 0x2F) + b"\0" * 36
    listing_offset = 0x28 + 40
    name = b"TESTDIR\0"
    node = (
        name
        + b"\0" * 12
        + struct.pack("<HH", 2, 1)
        + struct.pack("<I", 1)
        + struct.pack("<II", 0, 0)
        + struct.pack("<I", listing_offset)
    )
    assert len(node) == 40

    entry = (
        b"FILE.TXT\0\0\0\0"
        + b"\0" * 10
        + struct.pack("<H", 0)
        + struct.pack("<I", 0)
        + struct.pack("<I", 123)
    )
    assert len(entry) == 32

    tree = drstr.parse(header + node + entry)
    assert tree["header_word"] == 0x2F
    assert tree["node_count"] == 1
    assert tree["nodes"][0]["name"] == "TESTDIR"
    assert tree["nodes"][0]["type"] == 1
    assert tree["nodes"][0]["entry_count"] == 1
    assert tree["nodes"][0]["entries"][0]["name"] == "FILE.TXT"
    assert tree["nodes"][0]["entries"][0]["size"] == 123


def main() -> int:
    test_cmpind()
    test_drstr()
    print("selftest: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
