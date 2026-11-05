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

import cardcheck  # noqa: E402
import cmpind  # noqa: E402
import drstr  # noqa: E402
import mesh_grid  # noqa: E402


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


def test_mesh_grid() -> None:
    lat_min, lat_max, lon_min, lon_max = mesh_grid.tile_box("B48R058R.DAT")
    assert abs(lat_min - 48.0) < 1e-9
    assert abs(lat_max - 53.3333333333) < 1e-6
    assert abs(lon_min - 12.0) < 1e-9
    assert abs(lon_max - 20.0) < 1e-9


def _lfn_entry(seq: int, text: str) -> bytes:
    entry = bytearray(32)
    entry[0] = seq
    entry[11] = 0x0F
    raw = text.encode("utf-16le")
    if len(raw) < 26:
        raw += b"\x00\x00"
    raw = raw[:26].ljust(26, b"\xff")
    entry[1:11] = raw[:10]
    entry[14:26] = raw[10:22]
    entry[28:32] = raw[22:26]
    return bytes(entry)


def _short_entry(name: str, attr: int = 0x20, cluster: int = 0, size: int = 0) -> bytes:
    entry = bytearray(32)
    encoded = name.encode("ascii")
    entry[0:11] = encoded.ljust(11, b" ")[:11]
    entry[11] = attr
    struct.pack_into("<H", entry, 20, cluster >> 16)
    struct.pack_into("<H", entry, 26, cluster & 0xFFFF)
    struct.pack_into("<I", entry, 28, size)
    return bytes(entry)


def test_cardcheck_helpers() -> None:
    # Level table: one section, one row.
    table = struct.pack(">HBBBBH", 1, 1, 1, 2, 0x91, 123)
    groups = cardcheck.parse_level_table(table, 0)
    assert groups == [
        {"section": 1, "rows": [{"level": 2, "type": 0x91, "count": 123}]}
    ]

    # Common header fields.
    header = bytearray(0x180)
    for off, text in (
        (0x00, "CLARION"),
        (0x40, "HITACHI"),
        (0x80, "CLA-NAVI05-01"),
        (0xA0, "FORMAT VERSION X08-02-00"),
        (0xE0, "DATA VERSION 11/06/27/01"),
    ):
        raw = text.encode("utf-16-be")
        header[off : off + len(raw)] = raw
    fields = cardcheck.header_fields(bytes(header))
    assert fields["clarion"] == "CLARION"
    assert fields["model"] == "CLA-NAVI05-01"
    assert fields["format"] == "FORMAT VERSION X08-02-00"

    # LFN + short entry.  The card's WinCE FAT checksums do not match the
    # standard algorithm, so the parser deliberately trusts a contiguous
    # sequence instead.
    directory = _lfn_entry(0x41, "TESTFILE.TXT") + _short_entry(
        "TESTFI~1TXT", size=42
    )
    entries = cardcheck.parse_dir_entries(directory)
    assert len(entries) == 1
    assert entries[0]["name"] == "TESTFILE.TXT"
    assert entries[0]["size"] == 42

    # .cmp/.ind decode helper.
    chunk0 = b"A" * 0x10000
    chunk1 = b"B" * 100
    stream0 = zlib.compress(chunk0)
    stream1 = zlib.compress(chunk1)
    packed = stream0 + stream1
    ind = (
        struct.pack("<IIII", len(chunk0) + len(chunk1), len(packed), 2, 0x10000)
        + struct.pack("<II", 0, len(stream0))
    )
    blob, info = cardcheck.decode_cmp(packed, ind)
    assert blob == chunk0 + chunk1
    assert info["chunks"] == 2

    # Logical listing: .cmp/.ind maps to the .ind uncompressed size; DRSTR
    # itself and .ind files are not logical entries.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "A.DAT.cmp").write_bytes(b"x")
        (root / "A.DAT.ind").write_bytes(struct.pack("<I", 100))
        (root / "B.DAT").write_bytes(b"12345")
        (root / "DRSTR001.DAT").write_bytes(b"x")
        source = cardcheck.RootSource(root)
        listing = cardcheck.logical_listing(source, "")
        assert set(listing) == {"A.DAT", "B.DAT"}
        assert listing["A.DAT"].size == 100
        assert listing["B.DAT"].size == 5
        assert cardcheck.tree_size(source, "") == 105


def main() -> int:
    test_cmpind()
    test_drstr()
    test_mesh_grid()
    test_cardcheck_helpers()
    print("selftest: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
