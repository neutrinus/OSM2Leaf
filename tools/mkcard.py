#!/usr/bin/env python3
"""Rebuild a Leaf ZE0 map-card SD image from an extracted card tree (M5.10).

The image is produced by a **layout-preserving rebuild**:

* the MBR, the pre-partition firmware area and the post-partition tail are
  copied from the source image verbatim (the source image is read-only and is
  never committed anywhere);
* the FAT32 map partition is opened with its factory geometry (512-byte
  sectors, 64 KiB clusters, label, FAT count, root cluster) and every file the
  tree keeps unchanged stays in its factory cluster chain with its factory
  directory entry bytes;
* only what the tree changes is rewritten: file contents, directory entries,
  FAT entries, FSInfo counts, and the hidden ``VER_INFO/HDD_INFO.TXT`` copy at
  ``0x06000000`` that ``cardcheck.py`` compares against the visible file.

Why not format from scratch: the unit's tolerance of a non-factory allocation
order is unknown, and the card test plan starts with a byte-identical no-op
rebuild (S0).  A layout-preserving rebuild makes that the default: an unchanged
tree produces a byte-identical image, and a changed file produces exactly the
changed bytes (plus the size field when the length changes).

Geometry is never invented: cluster size, sector size, FAT count, reserved
sectors, label and volume id all come from the source image.  The tool refuses
to write anything except the explicit ``-o`` image (and an explicit ``--json``
report); it never modifies the source image or the tree.

Usage:

    python3 tools/mkcard.py --from-image IMG --tree ROOT -o OUT.img
    python3 tools/mkcard.py --from-image IMG --tree ROOT --dry-run --json -
    python3 tools/mkcard.py --selftest

``--dry-run`` prints the plan and writes nothing.  ``--json PATH`` writes the
machine-readable plan/report (``-`` = stdout).  A real build needs ``-o`` and
refuses to overwrite an existing file unless ``--overwrite`` is given.

Exit codes: 0 built (or planned) cleanly, 1 the plan has errors, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cardcheck  # noqa: E402  (HDD copy offset and the L1 checks)
import leafimg  # noqa: E402

SECTOR = 512
FAT32_TYPES = (0x0B, 0x0C)
FAT_EOC = 0x0FFFFFFF
FAT_BAD = 0x0FFFFFF7
HDD_COPY_OFFSET = cardcheck.HDD_COPY_OFFSET
HDD_COPY_REL = "VER_INFO/HDD_INFO.TXT"
COPY_BLOCK = 8 << 20
ATTR_VOLUME = 0x08
ATTR_DIR = 0x10
ATTR_ARCHIVE = 0x20
# The factory FAT modification time recorded in docs/format/sd-card-layout.md.
# New entries use it so two builds of the same tree are byte-identical.
DEFAULT_TIMESTAMP = "2011-08-23 21:20:54"
SHORT_LEGAL = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$%'-_@~`!(){}^#&"
)


class UsageError(Exception):
    """Bad invocation or unsafe output path."""


class BuildError(Exception):
    """The requested tree cannot be laid out on this image."""


def _ceil_div(value: int, divisor: int) -> int:
    return (value + divisor - 1) // divisor


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _lfn_checksum(short_name: bytes) -> int:
    total = 0
    for byte in short_name:
        total = (((total & 1) << 7) + (total >> 1) + byte) & 0xFF
    return total


def _lfn_text(entry: bytes) -> str:
    raw = entry[1:11] + entry[14:26] + entry[28:32]
    text = raw.decode("utf-16-le", "replace")
    for stop in ("\x00", "\uffff"):
        text = text.split(stop)[0]
    return text


def read_short_name(entry: bytes) -> str:
    base = entry[0:8]
    ext = entry[8:11]
    if base[:1] == b"\x05":
        base = b"\xe5" + base[1:]
    base_s = base.decode("ascii", "replace").rstrip(" \x00")
    ext_s = ext.decode("ascii", "replace").rstrip(" \x00")
    return f"{base_s}.{ext_s}" if ext_s else base_s


@dataclass
class Record:
    """One logical directory entry (its LFN slots plus the short slot)."""

    name: str
    short: str
    attr: int
    cluster: int
    size: int
    slots: list[int]

    @property
    def is_dir(self) -> bool:
        return bool(self.attr & ATTR_DIR)


def parse_dir_slots(data: bytes) -> tuple[list[Record], list[str]]:
    """Parse a FAT directory blob into records with their 32-byte slot indices.

    Follows ``cardcheck.parse_dir_entries``: a contiguous LFN sequence is
    trusted even when the checksum does not match (the factory WinCE FAT writes
    non-standard checksums); otherwise the short name is used.
    """
    records: list[Record] = []
    warnings: list[str] = []
    lfn: list[tuple[int, bytes]] = []
    for slot in range(len(data) // 32):
        entry = data[slot * 32 : (slot + 1) * 32]
        if entry[0] == 0x00:
            break
        if entry[0] == 0xE5:
            lfn = []
            continue
        attr = entry[11]
        if attr == 0x0F:
            lfn.append((slot, entry))
            continue
        if attr & ATTR_VOLUME:
            lfn = []
            continue
        short = read_short_name(entry)
        if short in (".", "..") or not short:
            lfn = []
            continue
        name = short
        slots = [slot]
        if lfn:
            seqs = sorted(item[1][0] & 0x1F for item in lfn)
            if seqs == list(range(1, len(seqs) + 1)):
                ordered = sorted(lfn, key=lambda item: item[1][0] & 0x1F)
                name = "".join(_lfn_text(item[1]) for item in ordered)
                slots = [item[0] for item in ordered] + [slot]
            else:
                warnings.append(
                    f"slot {slot}: non-contiguous LFN sequence, using {short!r}"
                )
        records.append(
            Record(
                name=name,
                short=short,
                attr=attr,
                cluster=(_u16(entry, 20) << 16) | _u16(entry, 26),
                size=_u32(entry, 28),
                slots=slots,
            )
        )
        lfn = []
    return records, warnings


@dataclass
class Geometry:
    partition_offset: int
    partition_bytes: int
    bytes_per_sector: int
    sectors_per_cluster: int
    cluster_bytes: int
    reserved_sectors: int
    fat_count: int
    fat_size_sectors: int
    total_sectors: int
    root_cluster: int
    label: str
    oem: str
    volume_id: int
    fsinfo_sector: int
    backup_boot_sector: int
    hidden_sectors: int

    @property
    def fat_offset(self) -> int:
        return self.partition_offset + self.reserved_sectors * self.bytes_per_sector

    @property
    def data_offset(self) -> int:
        return self.partition_offset + (
            self.reserved_sectors + self.fat_count * self.fat_size_sectors
        ) * self.bytes_per_sector

    @property
    def cluster_count(self) -> int:
        data_sectors = (
            self.total_sectors
            - self.reserved_sectors
            - self.fat_count * self.fat_size_sectors
        )
        return data_sectors // self.sectors_per_cluster

    @property
    def max_cluster(self) -> int:
        return self.cluster_count + 1

    def describe(self) -> dict:
        return {
            "partition_offset": self.partition_offset,
            "partition_bytes": self.partition_bytes,
            "bytes_per_sector": self.bytes_per_sector,
            "sectors_per_cluster": self.sectors_per_cluster,
            "cluster_bytes": self.cluster_bytes,
            "reserved_sectors": self.reserved_sectors,
            "fat_count": self.fat_count,
            "fat_size_sectors": self.fat_size_sectors,
            "total_sectors": self.total_sectors,
            "root_cluster": self.root_cluster,
            "label": self.label,
            "oem": self.oem,
            "volume_id": self.volume_id,
            "fsinfo_sector": self.fsinfo_sector,
            "backup_boot_sector": self.backup_boot_sector,
            "hidden_sectors": self.hidden_sectors,
            "cluster_count": self.cluster_count,
        }


class SourceCard:
    """Read-only view of the factory image: MBR, FAT32 partition and FAT."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.handle = self.path.open("rb")
        self.size = self.path.stat().st_size
        try:
            entries = leafimg.mbr_entries(self.handle)
        except ValueError as exc:
            self.handle.close()
            raise UsageError(f"{self.path}: {exc}") from exc
        fat_parts = [e for e in entries if e["type"] in FAT32_TYPES]
        if not fat_parts:
            self.handle.close()
            raise UsageError(f"{self.path}: no FAT32 partition (type 0x0b/0x0c)")
        if len(fat_parts) > 1:
            self.handle.close()
            raise UsageError(
                f"{self.path}: {len(fat_parts)} FAT32 partitions; refusing to guess"
            )
        self.partition = fat_parts[0]
        if self.partition["offset"] + self.partition["bytes"] > self.size:
            self.handle.close()
            raise UsageError(
                f"{self.path}: FAT partition ends past the image "
                f"({self.partition['offset'] + self.partition['bytes']} > {self.size})"
            )
        try:
            self.geometry = self._read_geometry()
            self.fat = bytearray(self._read_fat())
        except (OSError, ValueError) as exc:
            self.handle.close()
            raise UsageError(f"{self.path}: {exc}") from exc

    def close(self) -> None:
        self.handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _read_geometry(self) -> Geometry:
        self.handle.seek(self.partition["offset"])
        bs = self.handle.read(SECTOR)
        if len(bs) < 90 or bs[510:512] != b"\x55\xaa":
            raise ValueError("FAT32 boot sector missing or short")
        bps = _u16(bs, 11)
        if bps != SECTOR:
            raise ValueError(f"unsupported FAT sector size {bps}")
        spc = bs[13]
        reserved = _u16(bs, 14)
        fats = bs[16]
        total = _u32(bs, 32) or _u16(bs, 19)
        fat_size = _u32(bs, 36) or _u16(bs, 22)
        root = _u32(bs, 44)
        fsinfo = _u16(bs, 48)
        bkbs = _u16(bs, 50)
        if not spc or not fat_size or not total:
            raise ValueError("invalid FAT32 geometry")
        if not (2 <= root <= total):
            raise ValueError(f"invalid root cluster {root}")
        return Geometry(
            partition_offset=self.partition["offset"],
            partition_bytes=self.partition["bytes"],
            bytes_per_sector=bps,
            sectors_per_cluster=spc,
            cluster_bytes=bps * spc,
            reserved_sectors=reserved,
            fat_count=fats,
            fat_size_sectors=fat_size,
            total_sectors=total,
            root_cluster=root,
            label=bs[71:82].decode("ascii", "replace").strip(),
            oem=bs[3:11].decode("ascii", "replace").strip(),
            volume_id=_u32(bs, 67),
            fsinfo_sector=fsinfo,
            backup_boot_sector=bkbs,
            hidden_sectors=_u32(bs, 28),
        )

    def _read_fat(self) -> bytes:
        geo = self.geometry
        self.handle.seek(geo.fat_offset)
        return self.handle.read(geo.fat_size_sectors * geo.bytes_per_sector)

    def fat_get(self, cluster: int) -> int:
        return _u32(self.fat, cluster * 4) & 0x0FFFFFFF

    def cluster_offset(self, cluster: int) -> int:
        if not 2 <= cluster <= self.geometry.max_cluster:
            raise BuildError(
                f"cluster {cluster} outside the {self.geometry.cluster_count} "
                "data clusters"
            )
        return self.geometry.data_offset + (cluster - 2) * self.geometry.cluster_bytes

    def chain(self, start: int) -> list[int]:
        chain: list[int] = []
        seen: set[int] = set()
        cluster = start
        while 2 <= cluster < FAT_BAD:
            if cluster in seen:
                raise BuildError(f"FAT cycle at cluster {cluster}")
            if cluster > self.geometry.max_cluster:
                raise BuildError(f"cluster {cluster} outside the volume")
            seen.add(cluster)
            chain.append(cluster)
            cluster = self.fat_get(cluster)
        if not chain:
            raise BuildError(f"empty cluster chain at {start}")
        return chain

    def read_cluster(self, cluster: int) -> bytes:
        self.handle.seek(self.cluster_offset(cluster))
        data = self.handle.read(self.geometry.cluster_bytes)
        if len(data) != self.geometry.cluster_bytes:
            raise BuildError(f"short read at cluster {cluster}")
        return data

    def read_chain_bytes(self, start: int) -> bytes:
        return b"".join(self.read_cluster(c) for c in self.chain(start))

    def read_at(self, offset: int, length: int) -> bytes:
        if offset < 0 or offset + length > self.size:
            raise BuildError(f"read 0x{offset:x}+{length} outside the image")
        self.handle.seek(offset)
        data = self.handle.read(length)
        if len(data) != length:
            raise BuildError(f"short read at 0x{offset:x}")
        return data


class DirBuffer:
    """Working copy of one directory: cluster chain, slot bytes, short names."""

    def __init__(self, builder: "Builder", rel: str, chain: list[int],
                 data: bytes, is_new: bool):
        self.builder = builder
        self.rel = rel
        self.chain = list(chain)
        self.data = bytearray(data)
        self.is_new = is_new
        records, _ = parse_dir_slots(bytes(data))
        self.taken = {record.short.lower() for record in records}

    def used_end(self) -> int:
        for slot in range(len(self.data) // 32 - 1, -1, -1):
            if any(self.data[slot * 32 : (slot + 1) * 32]):
                return slot + 1
        return 0

    def ensure_slots(self, need: int) -> int:
        cb = self.builder.geometry.cluster_bytes
        per_cluster = cb // 32
        used = self.used_end()
        have = len(self.data) // 32
        if used + need > have:
            extra_slots = used + need - have
            extra_clusters = _ceil_div(extra_slots, per_cluster)
            new = self.builder.allocate(
                extra_clusters, f"grow directory {self.rel or '/'}"
            )
            self.builder.fat_set(self.chain[-1], new[0])
            self.chain.extend(new)
            self.data.extend(b"\x00" * (extra_clusters * cb))
        return used

    def append(self, entries: list[bytes]) -> list[int]:
        start = self.ensure_slots(len(entries))
        blob = b"".join(entries)
        self.data[start * 32 : (start + len(entries)) * 32] = blob
        end = start + len(entries)
        if end * 32 < len(self.data):
            self.data[end * 32 : (end + 1) * 32] = b"\x00" * 32
        return list(range(start, end))

    def mark_deleted(self, slots: list[int]) -> None:
        for slot in slots:
            self.data[slot * 32] = 0xE5

def _fat_stamp(when: datetime) -> tuple[int, int]:
    if when.year < 1980:
        raise UsageError("--timestamp must be 1980 or later")
    date = ((when.year - 1980) << 9) | (when.month << 5) | when.day
    time = (when.hour << 11) | (when.minute << 5) | (when.second // 2)
    return time, date


def _parse_timestamp(text: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise UsageError(f"cannot parse timestamp {text!r}")


def _lfn_entries(name: str, checksum: int) -> list[bytes]:
    raw = name.encode("utf-16-le")
    if len(raw) % 26:
        raw += b"\x00\x00"
    raw += b"\xff" * ((-len(raw)) % 26)
    count = len(raw) // 26
    entries: list[bytes] = []
    for index in range(count):
        entry = bytearray(32)
        entry[0] = (index + 1) | (0x40 if index == count - 1 else 0)
        entry[11] = 0x0F
        entry[12] = 0
        entry[13] = checksum
        chunk = raw[index * 26 : (index + 1) * 26]
        entry[1:11] = chunk[0:10]
        entry[14:26] = chunk[10:22]
        entry[28:32] = chunk[22:26]
        entries.append(bytes(entry))
    return entries


def _short_entry(short: str, attr: int, cluster: int, size: int,
                 stamp: tuple[int, int]) -> bytes:
    entry = bytearray(32)
    if short in (".", ".."):
        base, ext = short, ""
    elif "." in short:
        base, ext = short.split(".", 1)
    else:
        base, ext = short, ""
    entry[0:8] = base.encode("ascii").ljust(8, b" ")[:8]
    entry[8:11] = ext.encode("ascii").ljust(3, b" ")[:3]
    entry[11] = attr
    entry[12] = 0
    entry[13] = 0
    struct.pack_into("<H", entry, 14, stamp[0])
    struct.pack_into("<H", entry, 16, stamp[1])
    struct.pack_into("<H", entry, 18, stamp[1])
    struct.pack_into("<H", entry, 20, (cluster >> 16) & 0xFFFF)
    struct.pack_into("<H", entry, 22, stamp[0])
    struct.pack_into("<H", entry, 24, stamp[1])
    struct.pack_into("<H", entry, 26, cluster & 0xFFFF)
    struct.pack_into("<I", entry, 28, size)
    return bytes(entry)


def _sanitize_part(text: str, limit: int) -> str:
    out = []
    for char in text.upper():
        out.append(char if char in SHORT_LEGAL else "_")
    cleaned = "".join(out).strip(" ")
    return cleaned[:limit] if cleaned else "_"


@dataclass
class TreeChild:
    name: str
    path: Path
    is_dir: bool


class Builder:
    """Plans the rebuild and renders it into the output image."""

    def __init__(self, src: SourceCard, tree: Path, *, include_artifacts: bool,
                 allow_label_mismatch: bool, stamp: tuple[int, int]):
        self.src = src
        self.tree = Path(tree)
        self.geometry = src.geometry
        self.cb = src.geometry.cluster_bytes
        self.include_artifacts = include_artifacts
        self.allow_label_mismatch = allow_label_mismatch
        self.stamp = stamp
        self.fat = bytearray(src.fat)
        self.fat_dirty: set[int] = set()
        self.allocated: list[int] = []
        self.freed: list[int] = []
        self.alloc_cursor = 2
        self.patches: list[tuple[int, bytes, str, str]] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.stats = {
            "keep": 0, "update": 0, "create": 0, "delete": 0,
            "mkdir": 0, "rmdir": 0,
        }
        self.detail: list[dict] = []
        self.tree_stats = {"directories": 0, "files": 0, "bytes": 0}
        self.hdd_copy = {"offset": HDD_COPY_OFFSET, "status": "skipped",
                         "length": 0}

    # -- FAT helpers ------------------------------------------------------

    def fat_value(self, cluster: int) -> int:
        return _u32(self.fat, cluster * 4) & 0x0FFFFFFF

    def fat_set(self, cluster: int, value: int) -> None:
        struct.pack_into("<I", self.fat, cluster * 4, value & 0x0FFFFFFF)
        self.fat_dirty.add(cluster)

    def fat_free(self, cluster: int) -> None:
        if cluster in self.allocated:
            self.allocated.remove(cluster)
        elif cluster not in self.freed:
            self.freed.append(cluster)
        struct.pack_into("<I", self.fat, cluster * 4, 0)
        self.fat_dirty.add(cluster)

    def chain_from_fat(self, start: int) -> list[int]:
        chain: list[int] = []
        seen: set[int] = set()
        cluster = start
        while 2 <= cluster < FAT_BAD:
            if cluster in seen:
                raise BuildError(f"FAT cycle at cluster {cluster}")
            if cluster > self.geometry.max_cluster:
                raise BuildError(f"cluster {cluster} outside the volume")
            seen.add(cluster)
            chain.append(cluster)
            cluster = self.fat_value(cluster)
        return chain

    def allocate(self, count: int, why: str) -> list[int]:
        if count <= 0:
            return []
        out: list[int] = []
        cluster = max(2, self.alloc_cursor)
        while len(out) < count:
            if cluster > self.geometry.max_cluster:
                raise BuildError(
                    f"no free cluster for {why!r}: want {count}, found {len(out)}"
                )
            if self.fat_value(cluster) == 0:
                out.append(cluster)
                if cluster in self.freed:
                    self.freed.remove(cluster)
            cluster += 1
        for first, second in zip(out, out[1:]):
            self.fat_set(first, second)
        self.fat_set(out[-1], FAT_EOC)
        self.alloc_cursor = out[-1] + 1
        self.allocated.extend(out)
        return out

    def free_chain(self, start: int) -> None:
        if not start:
            return
        for cluster in self.chain_from_fat(start):
            self.fat_free(cluster)

    # -- patching ---------------------------------------------------------

    def patch(self, offset: int, data: bytes, kind: str, detail: str) -> None:
        if not data:
            return
        old = self.src.read_at(offset, len(data))
        if old == data:
            return
        start = 0
        end = len(data)
        while start < end and data[start] == old[start]:
            start += 1
        while end > start and data[end - 1] == old[end - 1]:
            end -= 1
        self.patches.append((offset + start, data[start:end], kind, detail))

    # -- tree scan --------------------------------------------------------

    def scan(self, rel: str) -> list[TreeChild]:
        path = self.tree / rel if rel else self.tree
        children: list[TreeChild] = []
        seen: dict[str, str] = {}
        for entry in sorted(os.scandir(path), key=lambda item: item.name):
            name = entry.name
            if not self.include_artifacts and cardcheck.is_dump_artifact(
                name, ignore=True
            ):
                continue
            if entry.is_symlink():
                raise BuildError(f"{rel or '/'}: symlink {name!r} is not map data")
            is_dir = entry.is_dir()
            _validate_name(name, rel)
            key = name.lower()
            if key in seen:
                raise BuildError(
                    f"{rel or '/'}: {name!r} and {seen[key]!r} differ only by case"
                )
            seen[key] = name
            children.append(TreeChild(name, Path(entry.path), is_dir))
            if is_dir:
                self.tree_stats["directories"] += 1
            else:
                self.tree_stats["files"] += 1
                self.tree_stats["bytes"] += entry.stat().st_size
        return children

    # -- planning ---------------------------------------------------------

    def run(self) -> None:
        root_chain = self.src.chain(self.geometry.root_cluster)
        root_data = self.src.read_chain_bytes(self.geometry.root_cluster)
        root = DirBuffer(self, "", root_chain, root_data, False)
        self._plan_dir(root, "")
        self._emit_dir(root)
        self._finish_hdd_copy()
        self._emit_fat_patches()
        self._emit_fsinfo()
        self.patches.sort(key=lambda item: item[0])

    def _plan_dir(self, buf: DirBuffer, rel: str) -> None:
        records, warnings = parse_dir_slots(bytes(buf.data))
        self.warnings.extend(f"{rel or '/'}: {w}" for w in warnings)
        children = self.scan(rel)
        by_name = {child.name: child for child in children}
        lowered: dict[str, TreeChild] = {}
        for child in children:
            lowered.setdefault(child.name.lower(), child)
        used: set[str] = set()
        for record in records:
            child = by_name.get(record.name)
            if child is None:
                child = lowered.get(record.name.lower())
                if child is not None:
                    self.warnings.append(
                        f"{rel or '/'}: case-only rename {record.name!r} -> "
                        f"{child.name!r} ignored (image name kept)"
                    )
            if child is None:
                self._delete(buf, record, rel)
                continue
            if child.is_dir != record.is_dir:
                self._delete(buf, record, rel)
                self._create(buf, child, rel)
                used.add(child.name)
                continue
            used.add(child.name)
            if record.is_dir:
                sub = f"{rel}/{child.name}".strip("/")
                sub_buf = DirBuffer(
                    self, sub, self.src.chain(record.cluster),
                    self.src.read_chain_bytes(record.cluster), False,
                )
                self._plan_dir(sub_buf, sub)
                self._emit_dir(sub_buf)
            else:
                self._plan_file(buf, record, child, rel)
        for child in children:
            if child.name not in used:
                self._create(buf, child, rel)

    def _plan_file(self, buf: DirBuffer, record: Record,
                   child: TreeChild, rel: str) -> None:
        path = child.path
        size = path.stat().st_size
        sub = f"{rel}/{child.name}".strip("/")
        if size == record.size and self._same_content(record, path):
            self.stats["keep"] += 1
            return
        chain = self.src.chain(record.cluster) if record.cluster else []
        need = _ceil_div(size, self.cb) if size else 0
        extended = False
        if need and not chain:
            chain = self.allocate(need, sub)
            extended = True
        elif len(chain) < need:
            extra = self.allocate(need - len(chain), sub)
            self.fat_set(chain[-1], extra[0])
            chain.extend(extra)
            extended = True
        elif len(chain) > need:
            for cluster in chain[need:]:
                self.fat_free(cluster)
            if need:
                self.fat_set(chain[need - 1], FAT_EOC)
            chain = chain[:need]
        first = chain[0] if chain else 0
        slot = record.slots[-1]
        if record.size != size:
            struct.pack_into("<I", buf.data, slot * 32 + 28, size)
        if record.cluster != first:
            struct.pack_into("<H", buf.data, slot * 32 + 20, (first >> 16) & 0xFFFF)
            struct.pack_into("<H", buf.data, slot * 32 + 26, first & 0xFFFF)
        self.stats["update"] += 1
        self.detail.append({"op": "update", "path": sub,
                            "old_size": record.size, "new_size": size})
        if chain:
            self._write_file(path, chain, size, sub, zero_slack=extended)

    def _same_content(self, record: Record, path: Path) -> bool:
        if not record.cluster:
            return record.size == 0
        remaining = record.size
        with path.open("rb") as handle:
            for cluster in self.src.chain(record.cluster):
                take = min(self.cb, remaining)
                if take <= 0:
                    break
                if self.src.read_cluster(cluster)[:take] != handle.read(take):
                    return False
                remaining -= take
            return remaining == 0 and handle.read(1) == b""

    def _write_file(self, path: Path, chain: list[int], size: int,
                    rel: str, zero_slack: bool) -> None:
        remaining = size
        with path.open("rb") as handle:
            for cluster in chain:
                if remaining <= 0:
                    break
                take = min(self.cb, remaining)
                chunk = handle.read(take)
                if len(chunk) != take:
                    raise BuildError(f"{rel}: file changed size during the build")
                offset = self.src.cluster_offset(cluster)
                self.patch(offset, chunk, "file", rel)
                if zero_slack and take < self.cb:
                    self.patch(offset + take, b"\x00" * (self.cb - take),
                               "file", rel)
                remaining -= take
        if remaining:
            raise BuildError(f"{rel}: short write, {remaining} bytes left")

    def _delete(self, buf: DirBuffer, record: Record, rel: str) -> None:
        buf.mark_deleted(record.slots)
        sub = f"{rel}/{record.name}".strip("/")
        if record.is_dir:
            self._delete_dir_tree(sub, record.cluster)
            self.stats["rmdir"] += 1
            self.detail.append({"op": "rmdir", "path": sub})
        else:
            self.free_chain(record.cluster)
            self.stats["delete"] += 1
            self.detail.append({"op": "delete", "path": sub})
        buf.taken.add(record.short.lower())

    def _delete_dir_tree(self, rel: str, cluster: int) -> None:
        records, _ = parse_dir_slots(self.src.read_chain_bytes(cluster))
        for record in records:
            sub = f"{rel}/{record.name}"
            if record.is_dir:
                self._delete_dir_tree(sub, record.cluster)
                self.stats["rmdir"] += 1
                self.detail.append({"op": "rmdir", "path": sub})
            else:
                self.free_chain(record.cluster)
                self.stats["delete"] += 1
                self.detail.append({"op": "delete", "path": sub})
        self.free_chain(cluster)

    def _create(self, buf: DirBuffer, child: TreeChild, rel: str) -> None:
        sub = f"{rel}/{child.name}".strip("/")
        if child.is_dir:
            chain = self.allocate(1, f"directory {sub}")
            parent_cluster = 0 if not rel else buf.chain[0]
            sub_buf = DirBuffer(self, sub, chain, b"\x00" * self.cb, True)
            sub_buf.append([
                _short_entry(".", ATTR_DIR, chain[0], 0, self.stamp),
                _short_entry("..", ATTR_DIR, parent_cluster, 0, self.stamp),
            ])
            buf.append(self._entries_for(buf, child.name, ATTR_DIR, chain[0], 0))
            self.stats["mkdir"] += 1
            self.detail.append({"op": "mkdir", "path": sub})
            self._plan_dir(sub_buf, sub)
            self._emit_dir(sub_buf)
            return
        size = child.path.stat().st_size
        need = _ceil_div(size, self.cb) if size else 0
        chain = self.allocate(need, sub) if need else []
        buf.append(self._entries_for(
            buf, child.name, ATTR_ARCHIVE, chain[0] if chain else 0, size
        ))
        self.stats["create"] += 1
        self.detail.append({"op": "create", "path": sub, "size": size})
        if chain:
            self._write_file(child.path, chain, size, sub, zero_slack=True)

    def _entries_for(self, buf: DirBuffer, name: str, attr: int,
                     cluster: int, size: int) -> list[bytes]:
        short = self._short_name_for(buf, name)
        short_raw = _short_entry(short, attr, cluster, size, self.stamp)
        if name == short:
            return [short_raw]
        checksum = _lfn_checksum(short_raw[0:11])
        return list(reversed(_lfn_entries(name, checksum))) + [short_raw]

    def _short_name_for(self, buf: DirBuffer, name: str) -> str:
        if "." in name:
            base_raw, ext_raw = name.rsplit(".", 1)
        else:
            base_raw, ext_raw = name, ""
        base = _sanitize_part(base_raw, 8)
        ext = _sanitize_part(ext_raw, 3) if ext_raw else ""
        candidate = f"{base}.{ext}" if ext else base
        if name == candidate and candidate.lower() not in buf.taken:
            buf.taken.add(candidate.lower())
            return candidate
        for number in range(1, 1_000_000):
            tail = f"~{number}"
            stem = base[: max(1, 8 - len(tail))] + tail
            candidate = f"{stem}.{ext}" if ext else stem
            if candidate.lower() not in buf.taken:
                buf.taken.add(candidate.lower())
                return candidate
        raise BuildError(f"cannot build a short name for {name!r}")

    def _emit_dir(self, buf: DirBuffer) -> None:
        for index, cluster in enumerate(buf.chain):
            block = bytes(buf.data[index * self.cb : (index + 1) * self.cb])
            self.patch(self.src.cluster_offset(cluster), block,
                       "directory", buf.rel or "/")

    def _finish_hdd_copy(self) -> None:
        path = self.tree / HDD_COPY_REL
        if not path.is_file():
            self.warnings.append(
                f"{HDD_COPY_REL} not in the tree; the image copy at "
                f"0x{HDD_COPY_OFFSET:08x} is left unchanged"
            )
            return
        data = path.read_bytes()
        self.hdd_copy = {"offset": HDD_COPY_OFFSET, "status": "unchanged",
                         "length": len(data)}
        if HDD_COPY_OFFSET + len(data) > self.geometry.partition_offset:
            self.errors.append(
                f"{HDD_COPY_REL} copy at 0x{HDD_COPY_OFFSET:08x} would overlap "
                f"the FAT partition at 0x{self.geometry.partition_offset:08x}"
            )
            self.hdd_copy["status"] = "error"
            return
        if HDD_COPY_OFFSET + len(data) > self.src.size:
            self.errors.append(
                f"source image is smaller than the {HDD_COPY_REL} copy offset"
            )
            self.hdd_copy["status"] = "error"
            return
        before = len(self.patches)
        self.patch(HDD_COPY_OFFSET, data, "hdd_copy", HDD_COPY_REL)
        if len(self.patches) != before:
            self.hdd_copy["status"] = "updated"
        self._check_label(data)

    def _check_label(self, hdd: bytes) -> None:
        lines = hdd.split(b"\r\n")
        if len(lines) < 2:
            self.errors.append(f"{HDD_COPY_REL} has no second line")
            return
        line2 = lines[1].decode("ascii", "replace")
        label = self.geometry.label
        if not label:
            self.warnings.append("source image has no FAT volume label")
            return
        if line2 != label:
            message = (
                f"{HDD_COPY_REL} line 2 {line2!r} != FAT label {label!r}; "
                "cardcheck will fail the version check"
            )
            if self.allow_label_mismatch:
                self.warnings.append(message)
            else:
                self.errors.append(
                    message + " (pass --allow-label-mismatch to build anyway)"
                )

    def _emit_fat_patches(self) -> None:
        geo = self.geometry
        for cluster in sorted(self.fat_dirty):
            new = bytes(self.fat[cluster * 4 : cluster * 4 + 4])
            if new == self.src.fat[cluster * 4 : cluster * 4 + 4]:
                continue
            for copy in range(geo.fat_count):
                offset = (
                    geo.fat_offset
                    + copy * geo.fat_size_sectors * geo.bytes_per_sector
                    + cluster * 4
                )
                self.patch(offset, new, "fat", f"entry {cluster}")

    def _emit_fsinfo(self) -> None:
        if not (self.allocated or self.freed):
            return
        geo = self.geometry
        sector = geo.fsinfo_sector * geo.bytes_per_sector
        if not sector or sector + SECTOR > geo.reserved_sectors * geo.bytes_per_sector:
            return
        self._patch_fsinfo(geo.partition_offset + sector)
        if geo.backup_boot_sector:
            backup = (
                geo.partition_offset
                + (geo.backup_boot_sector + 1) * geo.bytes_per_sector
            )
            if backup + SECTOR <= geo.partition_offset + geo.partition_bytes:
                self._patch_fsinfo(backup)

    def _patch_fsinfo(self, offset: int) -> None:
        sector = self.src.read_at(offset, SECTOR)
        if (_u32(sector, 0) != 0x41615252 or _u32(sector, 0x1E4) != 0x61417272
                or _u32(sector, 0x1FC) != 0xAA550000):
            return
        free = _u32(sector, 0x1E8)
        next_free = _u32(sector, 0x1EC)
        if free == 0xFFFFFFFF:
            return
        new_free = max(0, free - len(self.allocated) + len(self.freed))
        self.patch(offset + 0x1E8, struct.pack("<I", new_free), "fsinfo",
                   "free count")
        if next_free != 0xFFFFFFFF and self.allocated:
            new_next = min(self.allocated)
            self.patch(offset + 0x1EC, struct.pack("<I", new_next), "fsinfo",
                       "next free")

    # -- output -----------------------------------------------------------

    def write(self, out: Path) -> None:
        need = self.src.size
        usage = shutil.disk_usage(out.parent)
        if usage.free < need:
            raise UsageError(
                f"{out.parent} has {usage.free} free bytes, the image needs {need}"
            )
        try:
            with self.src.path.open("rb") as source, out.open("wb") as target:
                while True:
                    block = source.read(COPY_BLOCK)
                    if not block:
                        break
                    target.write(block)
                previous_end = -1
                for offset, data, _kind, _detail in self.patches:
                    if offset < previous_end:
                        raise BuildError(
                            f"overlapping patches at 0x{offset:x}; refusing to write"
                        )
                    target.seek(offset)
                    target.write(data)
                    previous_end = offset + len(data)
                target.truncate(self.src.size)
        except OSError:
            out.unlink(missing_ok=True)
            raise

    def report(self) -> dict:
        changes = [
            {"offset": offset, "length": len(data), "kind": kind,
             "detail": detail}
            for offset, data, kind, detail in self.patches
        ]
        return {
            "ok": not self.errors,
            "geometry": self.geometry.describe(),
            "tree": dict(self.tree_stats),
            "ops": dict(self.stats),
            "detail": list(self.detail),
            "changes": changes,
            "change_bytes": sum(len(data) for _, data, _, _ in self.patches),
            "hdd_copy": dict(self.hdd_copy),
            "allocated_clusters": len(self.allocated),
            "freed_clusters": len(self.freed),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


def _validate_name(name: str, rel: str) -> None:
    where = rel or "/"
    if not name or name in (".", ".."):
        raise BuildError(f"{where}: invalid name {name!r}")
    if len(name) > 255:
        raise BuildError(f"{where}: name longer than 255 characters")
    if any(char in name for char in '"*/:<>?\\|'):
        raise BuildError(f"{where}: {name!r} contains a FAT-forbidden character")
    if name != name.rstrip(" ."):
        raise BuildError(f"{where}: {name!r} ends with a space or a dot")
    if any(ord(char) < 0x20 for char in name):
        raise BuildError(f"{where}: {name!r} contains a control character")


def _check_paths(args: argparse.Namespace) -> tuple[Path, Path, Path | None,
                                                    Path | None]:
    source = Path(args.from_image).expanduser()
    tree = Path(args.tree).expanduser()
    if not source.is_file():
        raise UsageError(f"--from-image {source} is not a file")
    if not tree.is_dir():
        raise UsageError(f"--tree {tree} is not a directory")
    tree_resolved = tree.resolve()
    output = Path(args.output).expanduser() if args.output else None
    report = Path(args.json).expanduser() if args.json else None

    if output is None:
        if not args.dry_run:
            raise UsageError(
                "a real build needs -o/--output; use --dry-run to plan without one"
            )
    else:
        resolved = output.resolve()
        if resolved == source.resolve():
            raise UsageError("refusing to write over the source image")
        if resolved == tree_resolved or tree_resolved in resolved.parents:
            raise UsageError("refusing to write the image inside the tree")
        if output.is_symlink():
            raise UsageError(f"refusing to write through the symlink {output}")
        if output.exists():
            if output.is_dir():
                raise UsageError(f"{output} is a directory")
            if not args.overwrite and not args.dry_run:
                raise UsageError(f"{output} exists; pass --overwrite to replace it")
        if not output.parent.is_dir():
            raise UsageError(f"{output.parent} is not a directory")
    if report is not None and str(report) != "-":
        resolved = report.resolve()
        if resolved == source.resolve():
            raise UsageError("the JSON report cannot be the source image")
        if resolved == tree_resolved or tree_resolved in resolved.parents:
            raise UsageError("refusing to write the JSON report inside the tree")
        if output is not None and resolved == output.resolve():
            raise UsageError("the JSON report cannot be the image path")
        if not report.parent.is_dir():
            raise UsageError(f"{report.parent} is not a directory")
    return source, tree, output, report


def run_build(args: argparse.Namespace) -> tuple[int, dict]:
    source_path, tree, output, _report_path = _check_paths(args)
    stamp = _fat_stamp(_parse_timestamp(args.timestamp))
    with SourceCard(source_path) as src:
        if src.geometry.cluster_bytes != 65536:
            print(
                f"warning: cluster size is {src.geometry.cluster_bytes}, "
                "the factory card uses 65536 (kept anyway)",
                file=sys.stderr,
            )
        builder = Builder(
            src, tree,
            include_artifacts=args.include_artifacts,
            allow_label_mismatch=args.allow_label_mismatch,
            stamp=stamp,
        )
        try:
            builder.run()
        except BuildError as exc:
            builder.errors.append(str(exc))
        result = builder.report()
        result["source"] = {"path": str(source_path), "size": src.size,
                            "partition": src.partition}
        result["output"] = str(output) if output else None
        result["dry_run"] = bool(args.dry_run)
        result["timestamp"] = args.timestamp
        if not result["ok"]:
            return 1, result
        if not args.dry_run:
            try:
                builder.write(output)
            except (OSError, UsageError, BuildError) as exc:
                result["errors"].append(str(exc))
                result["ok"] = False
                return 1, result
            result["written"] = str(output)
    return 0, result


def print_plan(result: dict) -> None:
    geo = result["geometry"]
    source = result["source"]
    mode = "plan" if result["dry_run"] else "build"
    print(f"mkcard {mode}: {source['path']} + {result['output'] or '<no output>'}")
    print(
        f"  partition   0x{geo['partition_offset']:08x} + "
        f"{geo['partition_bytes']} bytes, {geo['cluster_count']} clusters"
    )
    print(
        f"  geometry    {geo['bytes_per_sector']} B sectors, "
        f"{geo['cluster_bytes']} B clusters, {geo['fat_count']} FATs, "
        f"label {geo['label']!r}"
    )
    pre = geo["partition_offset"]
    tail = source["size"] - (geo["partition_offset"] + geo["partition_bytes"])
    print(f"  verbatim    pre-partition {pre} B, tail {tail} B, MBR included")
    tree = result["tree"]
    print(
        f"  tree        {tree['directories']} directories, {tree['files']} files, "
        f"{tree['bytes']} bytes"
    )
    ops = result["ops"]
    print(
        "  objects     keep={keep} update={update} create={create} "
        "delete={delete} mkdir={mkdir} rmdir={rmdir}".format(**ops)
    )
    copy = result["hdd_copy"]
    print(
        f"  hdd copy    0x{copy['offset']:08x} {copy['status']} "
        f"({copy['length']} B)"
    )
    print(
        f"  changes     {len(result['changes'])} ranges, "
        f"{result['change_bytes']} bytes"
    )
    for item in result["detail"][:12]:
        suffix = ""
        if item["op"] == "update":
            suffix = f" ({item['old_size']} -> {item['new_size']} B)"
        elif item["op"] == "create":
            suffix = f" ({item['size']} B)"
        print(f"    {item['op']:<7} {item['path']}{suffix}")
    if len(result["detail"]) > 12:
        print(f"    ... {len(result['detail']) - 12} more")
    for warning in result["warnings"][:10]:
        print(f"  WARN  {warning}")
    if len(result["warnings"]) > 10:
        print(f"  ... {len(result['warnings']) - 10} more warnings")
    for error in result["errors"]:
        print(f"  ERROR {error}")
    print("RESULT:", "PASS" if result["ok"] else "FAIL")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rebuild a Leaf ZE0 map-card image from an extracted card tree",
        epilog="Exit codes: 0 ok, 1 plan/build error, 2 usage error.",
    )
    parser.add_argument("--from-image", help="factory SD image to copy geometry from")
    parser.add_argument("--tree", help="extracted card root to write into the image")
    parser.add_argument("-o", "--output", help="image to create (required to build)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the plan and write nothing")
    parser.add_argument("--json", metavar="PATH",
                        help="write the machine-readable report (PATH '-' = stdout)")
    parser.add_argument("--overwrite", action="store_true",
                        help="replace an existing output image")
    parser.add_argument("--timestamp", default=DEFAULT_TIMESTAMP,
                        help=f"creation time for new entries (default {DEFAULT_TIMESTAMP!r})")
    parser.add_argument("--include-artifacts", action="store_true",
                        help="keep macOS ._* / .fseventsd entries found in the tree")
    parser.add_argument("--allow-label-mismatch", action="store_true",
                        help="build even if HDD_INFO line 2 differs from the FAT label")
    parser.add_argument("--selftest", action="store_true",
                        help="build a synthetic image and check the round-trip")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return run_selftest()
    if not args.from_image or not args.tree:
        print("error: --from-image and --tree are required", file=sys.stderr)
        return 2
    try:
        code, result = run_build(args)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    json_to_stdout = args.json == "-"
    if json_to_stdout:
        print(json.dumps(result, indent=2))
    else:
        print_plan(result)
        if args.json:
            Path(args.json).write_text(json.dumps(result, indent=2) + "\n")
    return code


# ---------------------------------------------------------------------------
# synthetic fixture (self-test and reproducible demo; no vendor bytes)
# ---------------------------------------------------------------------------


def _fixture_header() -> bytes:
    """A common 512-byte map-file header using the documented field values."""
    header = bytearray(512)
    for offset, text in (
        (0x00, "CLARION"),
        (0x40, "HITACHI"),
        (0x80, "CLA-NAVI05-01"),
        (0xA0, "FORMAT VERSION X08-02-00"),
        (0xE0, "DATA VERSION 11/06/27/01"),
    ):
        raw = text.encode("utf-16-be")
        header[offset : offset + len(raw)] = raw
    return bytes(header)


def _fixture_hdd_info(label: str) -> bytes:
    lines = ["0000000001", label, "2222222222", "3333333333",
             "4444444444", "55555555555"]
    blob = "\r\n".join(lines).encode("ascii")
    assert len(blob) == 72, len(blob)
    return blob


def _drstr_entry(name: str, kind: int, value: int) -> bytes:
    entry = bytearray(32)
    entry[0:13] = name.encode("ascii")[:13].ljust(13, b"\0")
    struct.pack_into("<H", entry, 0x16, kind)
    struct.pack_into("<I", entry, 0x1C, value & 0xFFFFFFFF)
    return bytes(entry)


def _fixture_drstr(files: dict[str, bytes]) -> bytes:
    """A DRSTR001.DAT that agrees with ``files`` (cardcheck's own size rules)."""
    dirs = {""}
    for rel in files:
        parts = rel.split("/")
        for index in range(1, len(parts)):
            dirs.add("/".join(parts[:index]))
    order = [""] + sorted(directory for directory in dirs if directory)
    node_index = {rel: index for index, rel in enumerate(order)}
    children: dict[str, list[str]] = {directory: [] for directory in order}
    for rel in files:
        if rel.endswith(".ind") or rel == "DRSTR001.DAT":
            continue
        parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
        children[parent].append(rel)
    for directory in dirs:
        if not directory:
            continue
        parent = directory.rsplit("/", 1)[0] if "/" in directory else ""
        children[parent].append(directory)
    for directory in children:
        children[directory].sort()

    def logical_size(rel: str) -> int:
        if rel.endswith(".cmp"):
            return _u32(files[rel[:-4] + ".ind"], 0)
        return len(files[rel])

    totals: dict[str, int] = {}

    def total(rel: str) -> int:
        if rel not in totals:
            value = 0
            for child in children[rel]:
                value += total(child) if child in dirs else logical_size(child)
            totals[rel] = value & 0xFFFFFFFF
        return totals[rel]

    table_end = len(order) * 40
    listings: list[tuple[int, int, bytes]] = []
    offset = table_end
    for directory in order:
        entries = b""
        for child in children[directory]:
            name = child.rsplit("/", 1)[-1]
            if child in dirs:
                entries += _drstr_entry(name, 2, total(child))
            else:
                if name.endswith(".cmp"):
                    name = name[:-4]
                entries += _drstr_entry(name, 0, logical_size(child))
        listings.append((offset, len(children[directory]), entries))
        offset += len(entries)

    blob = bytearray()
    for index, directory in enumerate(order):
        name = "/" if not directory else directory.rsplit("/", 1)[-1]
        parent = (
            0 if not directory
            else node_index[directory.rsplit("/", 1)[0] if "/" in directory else ""] + 1
        )
        node = bytearray(40)
        node[0:8] = name.encode("ascii")[:8].ljust(8, b"\0")
        struct.pack_into("<H", node, 0x14, index + 1)
        struct.pack_into("<H", node, 0x16, parent)
        struct.pack_into("<I", node, 0x18, len(children[directory]))
        struct.pack_into("<I", node, 0x24, listings[index][0])
        blob += node
    for _offset, _count, entries in listings:
        blob += entries
    return bytes(blob)


def fixture_files(label: str = "QSD-309-101") -> dict[str, bytes]:
    """Invented map-tree contents with the factory shape (no vendor bytes)."""
    import zlib

    header = _fixture_header()
    blob = header + bytes(0x400)
    stream = zlib.compress(blob, 6)
    ind = struct.pack("<IIII", len(blob), len(stream), 1, 0x10000) + struct.pack(
        "<I", 0
    )
    big = bytes(((index * 29 + 13) & 0xFF) for index in range(0x1C000))
    files = {
        "MMAIN001.DAT": header + bytes(0x300),
        "CMP.LST": b"\\SystemSD\\REFER001\\",
        "MAPAL001/B48R058R.DAT": header + bytes(0x300),
        "MAPAL001/LEV3456R.DAT": header + bytes(0x100),
        "REFER001/A.DAT.cmp": stream,
        "REFER001/A.DAT.ind": ind,
        "REFER002/EV.DAT": header + bytes(0x100),
        "RDSTM001/RD.DAT": header + bytes(0x100),
        "BICON001/BICON001.DAT": header + bytes(0x80),
        "OPNG/ICON.PNG": bytes(((index * 7 + 3) & 0xFF) for index in range(300)),
        "OPNG/BIG.DAT": big,
        "SPEECH/EN/VR.DAT": bytes(((index * 11 + 5) & 0xFF) for index in range(100)),
        "TMC/TMC.DAT": bytes(((index * 17 + 9) & 0xFF) for index in range(64)),
        HDD_COPY_REL: _fixture_hdd_info(label),
    }
    files["DRSTR001.DAT"] = _fixture_drstr(files)
    return files


FIXTURE_SHORT = {
    "A.DAT.cmp": "ADAT~1.CMP",
    "A.DAT.ind": "ADAT~1.IND",
}

FIXTURE_LABEL = "QSD-309-101"
FIXTURE_SPC = 128
FIXTURE_RESERVED = 32
FIXTURE_FATS = 2
FIXTURE_FAT_SECTORS = 1
FIXTURE_CLUSTERS = 40
FIXTURE_PARTITION_OFFSET = 0x06010000
FIXTURE_PRE_BLOCKS = FIXTURE_PARTITION_OFFSET // 0x10000
FIXTURE_TAIL_BLOCKS = 8
FIXTURE_HIDDEN = FIXTURE_PARTITION_OFFSET // SECTOR
FIXTURE_TOTAL_SECTORS = (
    FIXTURE_RESERVED + FIXTURE_FATS * FIXTURE_FAT_SECTORS + FIXTURE_CLUSTERS * FIXTURE_SPC
)
PRE_PATTERN = bytes(((index * 37 + 11) & 0xFF) for index in range(0x10000))
TAIL_PATTERN = bytes(((index * 53 + 7) & 0xFF) for index in range(0x10000))


def _materialize_tree(root: Path, files: dict[str, bytes]) -> None:
    if root.exists():
        if not root.is_dir():
            raise BuildError(f"{root} exists and is not a directory")
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def _fixture_boot_sector() -> bytes:
    sector = bytearray(SECTOR)
    sector[0:3] = b"\xeb\x58\x90"
    sector[3:11] = b"MSWIN4.1"
    struct.pack_into("<H", sector, 11, SECTOR)
    sector[13] = FIXTURE_SPC
    struct.pack_into("<H", sector, 14, FIXTURE_RESERVED)
    sector[16] = FIXTURE_FATS
    struct.pack_into("<H", sector, 17, 0)
    struct.pack_into("<H", sector, 19, 0)
    sector[21] = 0xF8
    struct.pack_into("<H", sector, 22, 0)
    struct.pack_into("<H", sector, 24, 32)
    struct.pack_into("<H", sector, 26, 64)
    struct.pack_into("<I", sector, 28, FIXTURE_HIDDEN)
    struct.pack_into("<I", sector, 32, FIXTURE_TOTAL_SECTORS)
    struct.pack_into("<I", sector, 36, FIXTURE_FAT_SECTORS)
    struct.pack_into("<H", sector, 40, 0)
    struct.pack_into("<H", sector, 42, 0)
    struct.pack_into("<I", sector, 44, 2)
    struct.pack_into("<H", sector, 48, 1)
    struct.pack_into("<H", sector, 50, 0xFFFF)
    sector[64] = 0x80
    sector[66] = 0x29
    struct.pack_into("<I", sector, 67, 0x2A1F5D7B)
    sector[71:82] = FIXTURE_LABEL.encode("ascii").ljust(11, b" ")
    sector[82:90] = b"FAT32   "
    sector[510:512] = b"\x55\xaa"
    return bytes(sector)


def _fixture_fsinfo(free: int, next_free: int) -> bytes:
    sector = bytearray(SECTOR)
    struct.pack_into("<I", sector, 0, 0x41615252)
    struct.pack_into("<I", sector, 0x1E4, 0x61417272)
    struct.pack_into("<I", sector, 0x1E8, free)
    struct.pack_into("<I", sector, 0x1EC, next_free)
    struct.pack_into("<I", sector, 0x1FC, 0xAA550000)
    return bytes(sector)


def _fixture_entries(name: str, short: str, attr: int, cluster: int,
                     size: int) -> list[bytes]:
    stamp = _fat_stamp(_parse_timestamp(DEFAULT_TIMESTAMP))
    short_raw = _short_entry(short, attr, cluster, size, stamp)
    if name == short:
        return [short_raw]
    return list(reversed(_lfn_entries(name, _lfn_checksum(short_raw[0:11])))) + [
        short_raw
    ]


def make_fixture(image_path: Path, tree_root: Path,
                 label: str = FIXTURE_LABEL) -> dict:
    """Write a synthetic factory image and its tree; return the layout manifest.

    Geometry mirrors the factory card in every structural respect that matters
    here (512-byte sectors, 64 KiB clusters, two FATs, FAT32, MBR + tail, and
    the ``0x06000000`` HDD_INFO copy) but is only ~99 MiB so the self-test can
    run quickly.  Everything is invented; no vendor byte is used.
    """
    image_path = Path(image_path)
    tree_root = Path(tree_root)
    files = fixture_files(label)
    _materialize_tree(tree_root, files)

    cluster_bytes = SECTOR * FIXTURE_SPC
    dirs: dict[str, dict] = {}
    file_layout: dict[str, dict] = {}
    state = {"next": 3}

    def allocate(count: int = 1) -> int:
        start = state["next"]
        state["next"] += count
        return start

    def scan(rel: str) -> list[tuple[str, bool]]:
        path = tree_root / rel if rel else tree_root
        return [
            (entry.name, entry.is_dir())
            for entry in sorted(os.scandir(path), key=lambda item: item.name)
        ]

    def plan(rel: str) -> None:
        items = scan(rel)
        child_dirs = [name for name, is_dir in items if is_dir]
        for name in child_dirs:
            plan(f"{rel}/{name}".strip("/"))
        for name, is_dir in items:
            if is_dir:
                continue
            data = (tree_root / rel / name).read_bytes()
            count = max(1, _ceil_div(len(data), cluster_bytes)) if data else 0
            cluster = allocate(count) if count else 0
            file_layout[f"{rel}/{name}".strip("/")] = {
                "name": name, "cluster": cluster, "size": len(data),
                "data": data, "parent": rel,
            }
        entries: list[bytes] = []
        short_slots: dict[str, int] = {}
        if not rel:
            entries.append(_short_entry(
                FIXTURE_LABEL, ATTR_VOLUME, 0, 0,
                _fat_stamp(_parse_timestamp(DEFAULT_TIMESTAMP)),
            ))
        else:
            # slots 0 and 1 hold "." and "..", filled in when the image is written
            entries.extend([b"\x00" * 32, b"\x00" * 32])
        for name, is_dir in items:
            if is_dir:
                sub = f"{rel}/{name}".strip("/")
                cluster = dirs[sub]["cluster"]
                short = name
                attr = ATTR_DIR
                size = 0
            else:
                sub = f"{rel}/{name}".strip("/")
                cluster = file_layout[sub]["cluster"]
                short = FIXTURE_SHORT.get(name, name)
                attr = ATTR_ARCHIVE
                size = file_layout[sub]["size"]
            entries.extend(_fixture_entries(name, short, attr, cluster, size))
            short_slots[sub] = len(entries) - 1
        cluster = 2 if not rel else allocate(
            max(1, _ceil_div(len(entries) * 32, cluster_bytes))
        )
        dirs[rel] = {"cluster": cluster, "entries": b"".join(entries)}
        for sub, slot in short_slots.items():
            target = file_layout.get(sub) or dirs.get(sub)
            target["slot"] = slot

    plan("")

    if state["next"] - 1 > FIXTURE_CLUSTERS + 1:
        raise BuildError("fixture needs more clusters than the geometry offers")

    fat = bytearray(FIXTURE_FAT_SECTORS * SECTOR)
    struct.pack_into("<I", fat, 0, 0x0FFFFFF8)
    struct.pack_into("<I", fat, 4, 0x0FFFFFFF)

    def link(chain: list[int]) -> None:
        for first, second in zip(chain, chain[1:]):
            struct.pack_into("<I", fat, first * 4, second)
        struct.pack_into("<I", fat, chain[-1] * 4, FAT_EOC)

    for entry in dirs.values():
        link([entry["cluster"]])
    for entry in file_layout.values():
        if entry["size"]:
            count = _ceil_div(entry["size"], cluster_bytes)
            link([entry["cluster"] + offset for offset in range(count)])

    data_area = bytearray(FIXTURE_CLUSTERS * cluster_bytes)

    def cluster_offset(cluster: int) -> int:
        return (cluster - 2) * cluster_bytes

    for rel, entry in dirs.items():
        start = cluster_offset(entry["cluster"])
        data_area[start : start + len(entry["entries"])] = entry["entries"]
        if not rel:
            continue
        parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
        parent_cluster = dirs[parent]["cluster"] if parent else 0
        dot = _fixture_entries(".", ".", ATTR_DIR, entry["cluster"], 0)
        dotdot = _fixture_entries("..", "..", ATTR_DIR, parent_cluster, 0)
        data_area[start : start + 64] = b"".join(dot + dotdot)
    for entry in file_layout.values():
        start = cluster_offset(entry["cluster"])
        data_area[start : start + entry["size"]] = entry["data"]

    used = {entry["cluster"] for entry in dirs.values()}
    for entry in file_layout.values():
        if entry["size"]:
            count = _ceil_div(entry["size"], cluster_bytes)
            used.update(entry["cluster"] + offset for offset in range(count))
    free = FIXTURE_CLUSTERS - len(used)
    next_free = 2
    while next_free in used:
        next_free += 1

    mbr = bytearray(SECTOR)
    entry = 446
    mbr[entry] = 0
    mbr[entry + 4] = 0x0B
    struct.pack_into("<II", mbr, entry + 8, FIXTURE_HIDDEN,
                     FIXTURE_TOTAL_SECTORS)
    mbr[510:512] = b"\x55\xaa"

    partition = bytearray(FIXTURE_TOTAL_SECTORS * SECTOR)
    boot = _fixture_boot_sector()
    partition[0:SECTOR] = boot
    partition[SECTOR : 2 * SECTOR] = _fixture_fsinfo(free, next_free)
    fat_offset = FIXTURE_RESERVED * SECTOR
    partition[fat_offset : fat_offset + SECTOR] = fat
    partition[fat_offset + SECTOR : fat_offset + 2 * SECTOR] = fat
    partition[FIXTURE_RESERVED * SECTOR + FIXTURE_FATS * FIXTURE_FAT_SECTORS * SECTOR :] = data_area

    hdd = files[HDD_COPY_REL]
    with image_path.open("wb") as handle:
        for block in range(FIXTURE_PRE_BLOCKS):
            payload = PRE_PATTERN
            if block == 0:
                payload = mbr + payload[SECTOR:]
            elif block == HDD_COPY_OFFSET // 0x10000:
                payload = hdd + payload[len(hdd) :]
            handle.write(payload)
        handle.write(partition)
        for _ in range(FIXTURE_TAIL_BLOCKS):
            handle.write(TAIL_PATTERN)

    data_start = (
        FIXTURE_PARTITION_OFFSET
        + (FIXTURE_RESERVED + FIXTURE_FATS * FIXTURE_FAT_SECTORS) * SECTOR
    )
    manifest = {
        "image": str(image_path),
        "tree": str(tree_root),
        "label": label,
        "cluster_bytes": cluster_bytes,
        "data_start": data_start,
        "partition_offset": FIXTURE_PARTITION_OFFSET,
        "partition_bytes": FIXTURE_TOTAL_SECTORS * SECTOR,
        "hdd_copy_offset": HDD_COPY_OFFSET,
        "files": {
            rel: {
                "cluster": entry["cluster"],
                "size": entry["size"],
                "data_offset": data_start + (entry["cluster"] - 2) * cluster_bytes,
                "slot_offset": data_start
                + (dirs[entry["parent"]]["cluster"] - 2) * cluster_bytes
                + entry["slot"] * 32,
            }
            for rel, entry in file_layout.items()
        },
    }
    return manifest


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(COPY_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def _diff_ranges(path_a: Path, path_b: Path, block: int = 1 << 20):
    ranges: list[tuple[int, int]] = []
    position = 0
    with Path(path_a).open("rb") as left, Path(path_b).open("rb") as right:
        while True:
            a = left.read(block)
            b = right.read(block)
            if not a and not b:
                break
            if len(a) != len(b):
                raise AssertionError("images differ in size")
            if a != b:
                index = 0
                while index < len(a):
                    if a[index] != b[index]:
                        end = index
                        while end < len(a) and a[end] != b[end]:
                            end += 1
                        start = position + index
                        length = end - index
                        if ranges and ranges[-1][0] + ranges[-1][1] == start:
                            ranges[-1] = (ranges[-1][0], ranges[-1][1] + length)
                        else:
                            ranges.append((start, length))
                        index = end
                    else:
                        index += 1
            position += len(a)
    return ranges


def _tree_digest(root: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        if rel_dir == ".":
            rel_dir = ""
        for name in dirnames:
            out[f"{rel_dir}/{name}".strip("/") + "/"] = b""
        for name in sorted(filenames):
            path = Path(dirpath) / name
            out[f"{rel_dir}/{name}".strip("/")] = path.read_bytes()
    return out


def _read_image_tree(path: Path) -> dict[str, bytes]:
    source = cardcheck.Fat32Image(Path(path))
    try:
        out: dict[str, bytes] = {}
        for entry in source.walk():
            if entry.is_dir:
                out[entry.path + "/"] = b""
            else:
                out[entry.path] = source.read(entry.path)
        return out
    finally:
        source.close()


def _tree_files(root: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        if rel_dir == ".":
            rel_dir = ""
        for name in filenames:
            out[f"{rel_dir}/{name}".strip("/")] = (Path(dirpath) / name).read_bytes()
    return out


def _lfn_checksums_ok(path: Path, dir_rel: str) -> bool:
    """Every LFN in one directory must carry the standard short-name checksum."""
    image = cardcheck.Fat32Image(Path(path))
    try:
        entry = image._resolve(dir_rel)
        data = image._read_chain(entry.cluster)
    finally:
        image.close()
    lfn: list[bytes] = []
    for slot in range(len(data) // 32):
        item = data[slot * 32 : (slot + 1) * 32]
        if item[0] == 0x00:
            break
        if item[0] == 0xE5:
            lfn = []
            continue
        if item[11] == 0x0F:
            lfn.append(item)
            continue
        if item[11] & 0x08:
            lfn = []
            continue
        if lfn:
            want = _lfn_checksum(item[0:11])
            if any(entry[13] != want for entry in lfn):
                return False
            lfn = []
    return True


def _l1_full(path: Path) -> dict:
    """Run every cardcheck L1 check (the same set cardcheck.main runs)."""
    source = cardcheck.Fat32Image(Path(path))
    try:
        report = cardcheck.Report("L1", {"kind": "image", "path": str(path)})
        cardcheck.check_mbr(source, report)
        cardcheck.check_fat(source, report)
        cardcheck.check_tree(source, report)
        cardcheck.check_headers(source, report)
        cardcheck.check_cmp(source, report)
        cardcheck.check_drstr(source, report)
        cardcheck.check_mmain(source, report)
        cardcheck.check_version(source, report)
        return report.finish()
    finally:
        source.close()


def _capture(argv: list[str]) -> tuple[int, str, str]:
    import contextlib
    import io

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def run_selftest() -> int:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, note: str = "") -> None:
        checks.append((name, bool(ok), note))
        print(f"  {name:<32} {'OK' if ok else 'FAIL'}" + (f" {note}" if note else ""))

    temp = Path(tempfile.mkdtemp(prefix="mkcard-selftest-"))
    try:
        source = temp / "src.img"
        tree = temp / "tree"
        out = temp / "out.img"
        print("mkcard selftest")
        manifest = make_fixture(source, tree)
        check("fixture geometry", manifest["cluster_bytes"] == 65536,
              f"cluster={manifest['cluster_bytes']} "
              f"label={manifest['label']}")
        check("fixture image size", source.stat().st_size
              == FIXTURE_PRE_BLOCKS * 0x10000
              + manifest["partition_bytes"] + FIXTURE_TAIL_BLOCKS * 0x10000,
              f"{source.stat().st_size} bytes")

        original = _tree_digest(tree)
        try:
            read_back = _read_image_tree(source)
            check("fixture reads back", read_back == original,
                  f"{len(original)} entries")
        except (OSError, ValueError) as exc:
            check("fixture reads back", False, str(exc))

        args = build_parser().parse_args([
            "--from-image", str(source), "--tree", str(tree),
            "-o", str(out), "--overwrite",
        ])
        code, report = run_build(args)
        check("identity build exit", code == 0,
              ", ".join(report.get("errors", [])) or "exit 0")
        if code == 0:
            digest_source = _sha256(source)
            digest_output = _sha256(out)
            check("identity byte-identical",
                  digest_source == digest_output, digest_output[:16])
            check("identity no changed ranges", not report["changes"],
                  f"{len(report['changes'])} ranges")
            check("identity hdd copy unchanged",
                  report["hdd_copy"]["status"] == "unchanged")

        # 1. same-size content edit: exactly the edited byte must move.
        big = tree / "OPNG/BIG.DAT"
        big_original = big.read_bytes()
        data = bytearray(big_original)
        edit_at = 0x100
        data[edit_at] ^= 0xFF
        big.write_bytes(bytes(data))
        code, report = run_build(args)
        expected = [(manifest["files"]["OPNG/BIG.DAT"]["data_offset"] + edit_at, 1)]
        check("same-size edit: one range", code == 0 and
              _diff_ranges(source, out) == expected,
              f"{_diff_ranges(source, out)}")

        # 2. append inside the last cluster: size field + appended bytes only.
        big.write_bytes(big_original)
        tmc = tree / "TMC/TMC.DAT"
        old_size = tmc.stat().st_size
        appended = bytes(((index * 19 + 1) & 0xFF) | 0x80 for index in range(100))
        tmc.write_bytes(tmc.read_bytes() + appended)
        code, report = run_build(args)
        ranges = _diff_ranges(source, out)
        layout = manifest["files"]["TMC/TMC.DAT"]
        size_bytes = struct.pack("<I", old_size)
        new_size = struct.pack("<I", old_size + len(appended))
        first = 0
        while size_bytes[first] == new_size[first]:
            first += 1
        expected = sorted([
            (layout["slot_offset"] + 28 + first, 1),
            (layout["data_offset"] + old_size, len(appended)),
        ])
        check("append: two ranges", code == 0 and ranges == expected,
              f"{ranges}")

        # 3. create + delete + grow + HDD_INFO edit, then read the tree back.
        (tree / "TMC/NEW.DAT").write_bytes(b"new file body\n" * 100)
        (tree / "TMC/VERY LONG FILE NAME.TXT").write_bytes(b"long name\n" * 50)
        (tree / "OPNG/BIG.DAT").unlink()
        tmc.write_bytes(tmc.read_bytes() + b"G" * 70000)
        hdd_path = tree / HDD_COPY_REL
        hdd_old = hdd_path.read_bytes()
        hdd_new = b"9999999999" + hdd_old[10:]
        hdd_path.write_bytes(hdd_new)
        # DRSTR must describe the edited tree, as the M5.6 rebuild would make it.
        (tree / "DRSTR001.DAT").write_bytes(_fixture_drstr(_tree_files(tree)))
        code, report = run_build(args)
        expected_tree = _tree_digest(tree)
        try:
            read_back = _read_image_tree(out)
            check("create/delete round-trip",
                  code == 0 and read_back == expected_tree,
                  f"{len(read_back)} entries")
        except (OSError, ValueError) as exc:
            check("create/delete round-trip", False, str(exc))
        with out.open("rb") as handle:
            handle.seek(HDD_COPY_OFFSET)
            copy = handle.read(len(hdd_new))
        check("hdd copy updated", copy == hdd_new,
              f"0x{HDD_COPY_OFFSET:08x}, {len(copy)} B")
        check("LFN checksums (TMC)", _lfn_checksums_ok(out, "TMC"))
        ranges = _diff_ranges(source, out)
        check("hdd copy in change list",
              any(offset <= HDD_COPY_OFFSET < offset + length
                  for offset, length in ranges),
              f"{len(ranges)} ranges")

        # 3b. rebuilding from the rebuilt image is a no-op.
        again = temp / "again.img"
        args2 = build_parser().parse_args([
            "--from-image", str(out), "--tree", str(tree),
            "-o", str(again), "--overwrite",
        ])
        code, report = run_build(args2)
        check("idempotent rebuild",
              code == 0 and not report["changes"]
              and _sha256(out) == _sha256(again),
              f"{len(report['changes'])} ranges")

        # 4. the full cardcheck L1 pass, on the fixture and on the rebuild.
        for path, label in ((source, "fixture"), (out, "rebuilt")):
            result = _l1_full(path)
            failed = [item["id"] for item in result["checks"] if not item["ok"]]
            check(f"cardcheck L1 ({label})", result["ok"], ", ".join(failed))

        # 5. dry run writes nothing and emits JSON.
        never = temp / "never.img"
        json_path = temp / "plan.json"
        code, stdout, _stderr = _capture([
            "--from-image", str(source), "--tree", str(tree),
            "-o", str(never), "--dry-run", "--json", str(json_path),
        ])
        dry = json.loads(json_path.read_text()) if json_path.exists() else {}
        check("dry-run writes nothing", code == 0 and not never.exists()
              and dry.get("dry_run") is True and dry.get("ok") is True)

        # 6. refusals: source path, tree path and an existing output.
        digest = _sha256(source)
        code, _out, _err = _capture([
            "--from-image", str(source), "--tree", str(tree), "-o", str(source),
        ])
        again = _sha256(source)
        check("refuses output = source", code == 2 and again == digest)
        code, _out, _err = _capture([
            "--from-image", str(source), "--tree", str(tree),
            "-o", str(tree / "inside.img"),
        ])
        check("refuses output inside tree", code == 2
              and not (tree / "inside.img").exists())
        code, _out, _err = _capture([
            "--from-image", str(source), "--tree", str(tree), "-o", str(out),
        ])
        check("refuses existing output", code == 2)
        code, _out, _err = _capture([
            "--from-image", str(source), "--tree", str(tree), "--dry-run",
        ])
        check("dry-run needs no output", code == 0)
    finally:
        shutil.rmtree(temp, ignore_errors=True)

    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        print(f"mkcard selftest: FAILED ({', '.join(failed)})")
        return 1
    print(f"mkcard selftest: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
