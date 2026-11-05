#!/usr/bin/env python3
"""Inspect a Leaf ZE0 SD card image and the common map-file header.

Verified against ``LEAF_2011-2012_QSD-309-101_navi158_eu.img`` (SHA-256
``105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307``).
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

SECTOR = 512


def mbr_entries(image) -> list[dict]:
    image.seek(0)
    mbr = image.read(SECTOR)
    if len(mbr) < SECTOR:
        raise ValueError("image is smaller than one sector")
    entries = []
    for i in range(4):
        raw = mbr[446 + i * 16 : 446 + (i + 1) * 16]
        if not any(raw):
            continue
        boot = raw[0]
        ptype = raw[4]
        lba, sectors = struct.unpack_from("<II", raw, 8)
        entries.append(
            {
                "index": i,
                "boot": boot,
                "type": ptype,
                "lba": lba,
                "sectors": sectors,
                "offset": lba * SECTOR,
                "bytes": sectors * SECTOR,
            }
        )
    return entries


def read_root_label(
    image,
    offset: int,
    bytes_per_sector: int,
    sectors_per_cluster: int,
    reserved: int,
    fat_count: int,
    fat_size_sectors: int,
    root_cluster: int,
) -> str:
    """Read the volume label from the FAT32 root directory.

    FAT32 boot sectors often contain ``NO NAME`` even when the volume has a
    label; the real label lives in a 0x08-attribute root directory entry.
    """
    cluster_bytes = bytes_per_sector * sectors_per_cluster
    data_start = offset + (reserved + fat_count * fat_size_sectors) * bytes_per_sector
    root_offset = data_start + (root_cluster - 2) * cluster_bytes
    image.seek(root_offset)
    directory = image.read(cluster_bytes)
    for i in range(0, len(directory) - 32, 32):
        entry = directory[i : i + 32]
        if entry[0] == 0x00:
            break
        if entry[0] == 0xE5:
            continue
        if entry[11] == 0x08:
            return entry[0:11].decode("ascii", "replace").strip()
    return ""


def fat_info(image, offset: int) -> dict:
    image.seek(offset)
    bs = image.read(SECTOR)
    if len(bs) < 90:
        raise ValueError("short FAT boot sector")
    (bytes_per_sector,) = struct.unpack_from("<H", bs, 11)
    (sectors_per_cluster,) = struct.unpack_from("<B", bs, 13)
    (reserved,) = struct.unpack_from("<H", bs, 14)
    (fat_count,) = struct.unpack_from("<B", bs, 16)
    (total16,) = struct.unpack_from("<H", bs, 19)
    (fat16,) = struct.unpack_from("<H", bs, 22)
    (total32,) = struct.unpack_from("<I", bs, 32)
    (fat32,) = struct.unpack_from("<I", bs, 36)
    (root_cluster,) = struct.unpack_from("<I", bs, 44)
    label = bs[71:82].decode("ascii", "replace").strip()
    if not label or label == "NO NAME":
        label = read_root_label(
            image,
            offset,
            bytes_per_sector,
            sectors_per_cluster,
            reserved,
            fat_count,
            fat32 or fat16,
            root_cluster,
        )
    return {
        "oem": bs[3:11].decode("ascii", "replace").strip(),
        "bytes_per_sector": bytes_per_sector,
        "sectors_per_cluster": sectors_per_cluster,
        "cluster_bytes": bytes_per_sector * sectors_per_cluster,
        "reserved_sectors": reserved,
        "fat_count": fat_count,
        "total_sectors": total32 or total16,
        "fat_size_sectors": fat32 or fat16,
        "root_cluster": root_cluster,
        "label": label,
    }


def cmd_info(args: argparse.Namespace) -> int:
    path = Path(args.image)
    with path.open("rb") as image:
        size = path.stat().st_size
        print(f"image          {path}")
        print(f"size           {size} bytes")
        entries = mbr_entries(image)
        if not entries:
            print("no MBR partitions found")
            return 1
        for entry in entries:
            print(
                f"partition {entry['index']}    type=0x{entry['type']:02x} "
                f"boot=0x{entry['boot']:02x} lba={entry['lba']} "
                f"offset=0x{entry['offset']:x} bytes={entry['bytes']}"
            )
            if entry["type"] in (0x01, 0x04, 0x06, 0x0B, 0x0C, 0x0E):
                try:
                    info = fat_info(image, entry["offset"])
                except ValueError as exc:
                    print(f"  FAT             unreadable: {exc}")
                    continue
                print(f"  label           {info['label']!r}")
                print(
                    f"  cluster         {info['cluster_bytes']} bytes "
                    f"({info['sectors_per_cluster']} sectors)"
                )
                print(f"  oem             {info['oem']!r}")
                print(f"  total sectors   {info['total_sectors']}")
                print(f"  root cluster    {info['root_cluster']}")
    return 0


def decode_header(blob: bytes) -> list[str]:
    # Only the first 0x180 bytes are text; the rest is a binary descriptor.
    text = blob[:0x180].decode("utf-16-be", "replace")
    fields = []
    for part in text.split("\uffff"):
        cleaned = "".join(ch for ch in part if 0x20 <= ord(ch) <= 0x7E).strip()
        if cleaned:
            fields.append(cleaned)
    return fields


def cmd_header(args: argparse.Namespace) -> int:
    path = Path(args.file)
    blob = path.read_bytes()[:512]
    if len(blob) < 512:
        print(f"error: {path} is smaller than 512 bytes", file=sys.stderr)
        return 2
    print(f"file           {path}")
    print("UTF-16BE fields:")
    for field in decode_header(blob):
        print(f"  {field!r}")
    print(f"binary 0x180   {blob[0x180:0x1b8].hex(' ')}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_info = sub.add_parser("info", help="show MBR and FAT geometry")
    p_info.add_argument("image")
    p_info.set_defaults(func=cmd_info)

    p_header = sub.add_parser("header", help="dump the common 512-byte file header")
    p_header.add_argument("file")
    p_header.set_defaults(func=cmd_header)

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
