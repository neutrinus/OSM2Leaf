#!/usr/bin/env python3
"""L1 whole-card validator for a Leaf ZE0 map card.

The validator works on either a raw SD image (``--image``) or an extracted
card root (``--root``).  It checks the structures that must agree for the unit
to read the card:

* MBR partition and FAT32 geometry (image mode only);
* required top-level entries and the file/directory census;
* the common 512-byte Clarion header on map files;
* every ``REFER001/*.cmp`` against its ``.ind`` (sizes, offsets, zlib);
* ``DRSTR001.DAT`` against the real tree (paths, types, logical sizes);
* ``MMAIN001.DAT`` level-table totals against every tile header;
* ``VER_INFO/HDD_INFO.TXT``, ``CMP.LST`` and the image copy at ``0x06000000``.

The validator is read-only.  It prints a human summary by default and can
write a machine-readable JSON report with ``--json``.  Exit code 0 means no
errors; warnings do not fail unless ``--strict`` is used.

Usage:
    python3 tools/cardcheck.py --root /path/to/root
    python3 tools/cardcheck.py --image /path/to/leaf2011.img --json report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import sys
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import drstr  # noqa: E402
import leafimg  # noqa: E402
import mesh_grid  # noqa: E402

SECTOR = 512
FAT32_TYPES = (0x0B, 0x0C)
COMMON_HEADER_OFFSETS = {
    0x00: "clarion",
    0x40: "hitachi",
    0x80: "model",
}
COMMON_HEADER_EXPECTED = {
    "clarion": "CLARION",
    "hitachi": "HITACHI",
    "model": "CLA-NAVI05-01",
}
FORMAT_PREFIX = "FORMAT VERSION "
DATA_PREFIX = "DATA VERSION "
HDD_COPY_OFFSET = 0x06000000
HDD_COPY_LEN = 72
CMP_LIST = b"\\SystemSD\\REFER001\\"
REQUIRED_TOP = {
    "MMAIN001.DAT",
    "DRSTR001.DAT",
    "CMP.LST",
    "MAPAL001",
    "REFER001",
    "REFER002",
    "RDSTM001",
    "BICON001",
    "OPNG",
    "SPEECH",
    "TMC",
    "VER_INFO",
}
DUMP_ARTIFACTS = {".fseventsd", ".Spotlight-V100", ".Trashes", "System Volume Information"}


def is_dump_artifact(name: str, ignore: bool = False) -> bool:
    return bool(ignore) and (name.startswith("._") or name in DUMP_ARTIFACTS)


def path_has_artifact(path: str, ignore: bool = False) -> bool:
    return any(is_dump_artifact(part, ignore) for part in path.split("/") if part)


# ---------------------------------------------------------------------------
# data model


@dataclass
class Entry:
    name: str
    is_dir: bool
    size: int = 0
    cluster: int = 0
    path: str = ""


@dataclass
class LogicalEntry:
    name: str
    is_dir: bool
    size: int
    actual: str


@dataclass
class Check:
    id: str
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def error(self, message: str) -> None:
        self.ok = False
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


class Report:
    def __init__(self, layer: str, source: dict):
        self.layer = layer
        self.source = source
        self.checks: list[Check] = []

    def add(self, check: Check) -> Check:
        self.checks.append(check)
        return check

    def finish(self, strict: bool = False) -> dict:
        errors = [f"{c.id}: {e}" for c in self.checks for e in c.errors]
        warnings = [f"{c.id}: {w}" for c in self.checks for w in c.warnings]
        if strict:
            errors += [f"{c.id}: warning treated as error: {w}" for c in self.checks for w in c.warnings]
            warnings = []
        return {
            "layer": self.layer,
            "ok": not errors,
            "source": self.source,
            "checks": [asdict(c) for c in self.checks],
            "errors": errors,
            "warnings": warnings,
        }


# ---------------------------------------------------------------------------
# FAT32 reader (read-only, long-file-name aware)


@dataclass
class FatGeometry:
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


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from("<H", data, off)[0]


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def _be16(data: bytes, off: int) -> int:
    return struct.unpack_from(">H", data, off)[0]


def _lfn_checksum(short_name: bytes) -> int:
    total = 0
    for byte in short_name:
        total = ((total & 1) << 7) + (total >> 1) + byte
    return total & 0xFF


def _short_name(entry: bytes) -> str:
    base = entry[0:8]
    ext = entry[8:11]
    if base[:1] == b"\x05":
        base = b"\xe5" + base[1:]
    base_s = base.decode("ascii", "replace").rstrip(" \x00")
    ext_s = ext.decode("ascii", "replace").rstrip(" \x00")
    return f"{base_s}.{ext_s}" if ext_s else base_s


def parse_dir_entries(data: bytes) -> list[dict]:
    """Parse a FAT directory blob, including LFN entries.

    Pure helper used by self-tests; no filesystem access.
    """
    out: list[dict] = []
    lfn: list[tuple[int, str]] = []
    for off in range(0, len(data) - 31, 32):
        entry = data[off : off + 32]
        if entry[0] == 0x00:
            break
        if entry[0] == 0xE5:
            lfn = []
            continue
        attr = entry[11]
        if attr == 0x0F:
            seq = entry[0] & 0x1F
            raw = entry[1:11] + entry[14:26] + entry[28:32]
            text = raw.decode("utf-16le", "replace")
            text = text.split("\x00")[0]
            lfn.append((seq, text))
            continue
        if attr & 0x08:
            lfn = []
            continue
        short = _short_name(entry)
        if short in (".", ".."):
            lfn = []
            continue
        # The card's Windows CE FAT writes LFN checksums that do not match
        # the standard short-name checksum, but the sequence numbers are
        # consistent and the names are the ones 7z/mtools extract.  Trust a
        # contiguous sequence; fall back to the short name otherwise.
        if lfn:
            seqs = sorted(seq for seq, _ in lfn)
            if seqs == list(range(1, len(seqs) + 1)):
                name = "".join(text for _, text in sorted(lfn))
            else:
                name = short
        else:
            name = short
        lfn = []
        cluster = (_u16(entry, 20) << 16) | _u16(entry, 26)
        out.append(
            {
                "name": name,
                "short": short,
                "is_dir": bool(attr & 0x10),
                "cluster": cluster,
                "size": _u32(entry, 28),
                "attr": attr,
            }
        )
    return out


class Fat32Image:
    """Minimal read-only FAT32 reader for the map partition."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.handle = self.path.open("rb")
        self.size = self.path.stat().st_size
        entries = leafimg.mbr_entries(self.handle)
        partitions = [e for e in entries if e["type"] in FAT32_TYPES]
        if not partitions:
            raise ValueError("no FAT32 partition in MBR")
        self.partition = partitions[0]
        self.geometry = self._read_geometry(self.partition)
        self._fat = self._read_fat()
        self._dir_cache: dict[str, list[Entry]] = {}
        self._entry_cache: dict[str, Entry] = {}

    def close(self) -> None:
        self.handle.close()

    def _read_geometry(self, part: dict) -> FatGeometry:
        self.handle.seek(part["offset"])
        bs = self.handle.read(SECTOR)
        if len(bs) < 90:
            raise ValueError("short FAT boot sector")
        bps = _u16(bs, 11)
        spc = bs[13]
        reserved = _u16(bs, 14)
        fat_count = bs[16]
        total = _u32(bs, 32) or _u16(bs, 19)
        fat_size = _u32(bs, 36) or _u16(bs, 22)
        root_cluster = _u32(bs, 44)
        label = bs[71:82].decode("ascii", "replace").strip()
        if not label or label == "NO NAME":
            label = self._read_volume_label(part["offset"], bps, spc, reserved,
                                            fat_count, fat_size, root_cluster)
        if bps != SECTOR:
            raise ValueError(f"unsupported FAT sector size {bps}")
        if spc == 0 or fat_size == 0:
            raise ValueError("invalid FAT geometry")
        return FatGeometry(
            partition_offset=part["offset"],
            partition_bytes=part["bytes"],
            bytes_per_sector=bps,
            sectors_per_cluster=spc,
            cluster_bytes=bps * spc,
            reserved_sectors=reserved,
            fat_count=fat_count,
            fat_size_sectors=fat_size,
            total_sectors=total,
            root_cluster=root_cluster,
            label=label,
            oem=bs[3:11].decode("ascii", "replace").strip(),
        )

    def _read_volume_label(self, part_off, bps, spc, reserved, fat_count,
                           fat_size, root_cluster) -> str:
        data_off = part_off + (reserved + fat_count * fat_size) * bps
        root_off = data_off + (root_cluster - 2) * bps * spc
        self.handle.seek(root_off)
        block = self.handle.read(bps * spc)
        for off in range(0, len(block) - 31, 32):
            entry = block[off : off + 32]
            if entry[0] == 0x00:
                break
            if entry[11] == 0x08:
                return entry[0:11].decode("ascii", "replace").strip()
        return ""

    def _read_fat(self) -> bytes:
        geo = self.geometry
        off = geo.partition_offset + geo.reserved_sectors * geo.bytes_per_sector
        self.handle.seek(off)
        return self.handle.read(geo.fat_size_sectors * geo.bytes_per_sector)

    def _cluster_chain(self, start: int) -> list[int]:
        chain: list[int] = []
        seen: set[int] = set()
        cluster = start
        while 2 <= cluster < 0x0FFFFFF8:
            if cluster in seen:
                raise ValueError(f"FAT cycle at cluster {cluster}")
            seen.add(cluster)
            chain.append(cluster)
            cluster = _u32(self._fat, cluster * 4) & 0x0FFFFFFF
        return chain

    def _read_cluster(self, cluster: int) -> bytes:
        geo = self.geometry
        off = geo.partition_offset + (
            geo.reserved_sectors + geo.fat_count * geo.fat_size_sectors
        ) * geo.bytes_per_sector + (cluster - 2) * geo.cluster_bytes
        self.handle.seek(off)
        return self.handle.read(geo.cluster_bytes)

    def _read_chain(self, start: int, size: int | None = None) -> bytes:
        data = b"".join(self._read_cluster(c) for c in self._cluster_chain(start))
        return data[:size] if size is not None else data

    def _resolve(self, rel: str) -> Entry:
        rel = rel.strip("/")
        if rel in self._entry_cache:
            return self._entry_cache[rel]
        if not rel:
            entry = Entry("/", True, 0, self.geometry.root_cluster, "")
            self._entry_cache[rel] = entry
            return entry
        parts = rel.split("/")
        current = ""
        entry = Entry("/", True, 0, self.geometry.root_cluster, "")
        for part in parts:
            listing = self.list_dir(current)
            match = next((e for e in listing if e.name == part), None)
            if match is None:
                match = next((e for e in listing if e.name.lower() == part.lower()), None)
            if match is None:
                raise FileNotFoundError(rel)
            entry = match
            current = f"{current}/{part}".strip("/")
        self._entry_cache[rel] = entry
        return entry

    def list_dir(self, rel: str = "") -> list[Entry]:
        rel = rel.strip("/")
        if rel in self._dir_cache:
            return self._dir_cache[rel]
        entry = self._resolve(rel)
        if not entry.is_dir:
            raise NotADirectoryError(rel)
        data = self._read_chain(entry.cluster)
        parsed = parse_dir_entries(data)
        out = []
        for item in parsed:
            path = f"{rel}/{item['name']}".strip("/")
            out.append(
                Entry(
                    name=item["name"],
                    is_dir=item["is_dir"],
                    size=0 if item["is_dir"] else item["size"],
                    cluster=item["cluster"],
                    path=path,
                )
            )
        self._dir_cache[rel] = out
        return out

    def read(self, rel: str) -> bytes:
        entry = self._resolve(rel)
        if entry.is_dir:
            raise IsADirectoryError(rel)
        return self._read_chain(entry.cluster, entry.size)

    def read_range(self, rel: str, offset: int, length: int) -> bytes:
        entry = self._resolve(rel)
        if entry.is_dir:
            raise IsADirectoryError(rel)
        if offset >= entry.size or length <= 0:
            return b""
        length = min(length, entry.size - offset)
        cluster_bytes = self.geometry.cluster_bytes
        skip = offset // cluster_bytes
        within = offset % cluster_bytes
        out = bytearray()
        for cluster in self._cluster_chain(entry.cluster)[skip:]:
            block = self._read_cluster(cluster)
            part = block[within:within + length]
            out.extend(part)
            length -= len(part)
            within = 0
            if length <= 0:
                break
        return bytes(out)

    def read_absolute(self, offset: int, length: int) -> bytes:
        self.handle.seek(offset)
        return self.handle.read(length)

    def walk(self):
        def rec(rel: str):
            for entry in self.list_dir(rel):
                yield entry
                if entry.is_dir:
                    yield from rec(entry.path)
        yield from rec("")


class RootSource:
    """Extracted card tree."""

    def __init__(self, root: Path):
        self.root = Path(root)
        if not self.root.is_dir():
            raise ValueError(f"{self.root} is not a directory")
        self.label = ""

    def close(self) -> None:
        pass

    def _path(self, rel: str) -> Path:
        return self.root / rel.strip("/")

    def list_dir(self, rel: str = "") -> list[Entry]:
        path = self._path(rel)
        out = []
        for item in sorted(path.iterdir(), key=lambda p: p.name):
            out.append(
                Entry(
                    name=item.name,
                    is_dir=item.is_dir(),
                    size=0 if item.is_dir() else item.stat().st_size,
                    path=f"{rel}/{item.name}".strip("/"),
                )
            )
        return out

    def read(self, rel: str) -> bytes:
        path = self._path(rel)
        if not path.is_file():
            raise FileNotFoundError(rel)
        return path.read_bytes()

    def read_range(self, rel: str, offset: int, length: int) -> bytes:
        path = self._path(rel)
        if not path.is_file():
            raise FileNotFoundError(rel)
        with path.open("rb") as handle:
            handle.seek(offset)
            return handle.read(length)

    def read_absolute(self, offset: int, length: int) -> bytes:
        raise NotImplementedError("absolute reads need an image source")

    def walk(self):
        for dirpath, dirnames, filenames in os.walk(self.root):
            rel_dir = Path(dirpath).relative_to(self.root).as_posix()
            if rel_dir == ".":
                rel_dir = ""
            for name in sorted(dirnames):
                yield Entry(name, True, 0, path=f"{rel_dir}/{name}".strip("/"))
            for name in sorted(filenames):
                path = Path(dirpath) / name
                yield Entry(name, False, path.stat().st_size,
                            path=f"{rel_dir}/{name}".strip("/"))


# ---------------------------------------------------------------------------
# shared parsing helpers


def parse_level_table(data: bytes, offset: int = 0x1AC) -> list[dict]:
    """Parse a big-endian ``(section, level, type, count)`` table."""
    if offset + 2 > len(data):
        raise ValueError("level table offset out of range")
    count = _be16(data, offset)
    pos = offset + 2
    groups = []
    for _ in range(count):
        if pos + 2 > len(data):
            raise ValueError("truncated level table group")
        section, rows = data[pos], data[pos + 1]
        pos += 2
        if pos + rows * 4 > len(data):
            raise ValueError("truncated level table rows")
        entries = []
        for _ in range(rows):
            level, kind, value = struct.unpack_from(">BBH", data, pos)
            pos += 4
            entries.append({"level": level, "type": kind, "count": value})
        groups.append({"section": section, "rows": entries})
    return groups


def utf16be_field(data: bytes, offset: int, length: int) -> str:
    raw = data[offset : offset + length]
    text = raw.decode("utf-16-be", "replace")
    for stop in ("\uffff", "\x00"):
        text = text.split(stop)[0]
    return text.strip()


def header_fields(data: bytes) -> dict:
    if len(data) < 0x180:
        return {}
    return {
        "clarion": utf16be_field(data, 0x00, 0x40),
        "hitachi": utf16be_field(data, 0x40, 0x40),
        "model": utf16be_field(data, 0x80, 0x20),
        "format": utf16be_field(data, 0xA0, 0x40),
        "data": utf16be_field(data, 0xE0, 0x80),
        "version": utf16be_field(data, 0x160, 0x20),
    }


def check_common_header(data: bytes, label: str, check: Check) -> None:
    fields = header_fields(data)
    for offset, field_name in COMMON_HEADER_OFFSETS.items():
        actual = fields.get(field_name)
        expected = COMMON_HEADER_EXPECTED[field_name]
        if actual != expected:
            check.error(
                f"{label}: header field 0x{offset:02x} is {actual!r}, "
                f"expected {expected!r}"
            )
    fmt = fields.get("format", "")
    if not fmt.startswith(FORMAT_PREFIX):
        check.warn(f"{label}: no {FORMAT_PREFIX!r} string (got {fmt!r})")
    elif fmt != "FORMAT VERSION X08-02-00":
        check.warn(f"{label}: format version is {fmt!r}, not X08-02-00")
    if not fields.get("data", "").startswith(DATA_PREFIX):
        check.warn(f"{label}: no {DATA_PREFIX!r} string")


def ind_values(data: bytes) -> tuple[int, int, int, int, tuple[int, ...]]:
    if len(data) < 16:
        raise ValueError("short .ind header")
    usize, csize, count, chunk_size = struct.unpack_from("<IIII", data, 0)
    if len(data) != 16 + 4 * count:
        raise ValueError(f".ind size {len(data)} != 16 + 4*{count}")
    offsets = struct.unpack_from(f"<{count}I", data, 16)
    if count:
        if offsets[0] != 0:
            raise ValueError(".ind first chunk offset is not 0")
        if list(offsets) != sorted(offsets):
            raise ValueError(".ind offsets are not sorted")
        if offsets[-1] >= csize:
            raise ValueError(".ind last chunk offset is outside .cmp")
    return usize, csize, count, chunk_size, offsets


def decode_cmp(cmp_data: bytes, ind_data: bytes) -> tuple[bytes, dict]:
    usize, csize, count, chunk_size, offsets = ind_values(ind_data)
    if csize != len(cmp_data):
        raise ValueError(f".ind declares {csize} compressed bytes, .cmp has {len(cmp_data)}")
    parts = []
    for i, start in enumerate(offsets):
        end = offsets[i + 1] if i + 1 < len(offsets) else len(cmp_data)
        if not (0 <= start < end <= len(cmp_data)):
            raise ValueError(f"chunk {i} range {start}:{end} out of bounds")
        try:
            part = zlib.decompress(cmp_data[start:end])
        except zlib.error as exc:
            raise ValueError(f"chunk {i} zlib error: {exc}") from exc
        if i != count - 1 and len(part) != chunk_size:
            raise ValueError(f"chunk {i} inflates to {len(part)}, expected {chunk_size}")
        parts.append(part)
    blob = b"".join(parts)
    if len(blob) != usize:
        raise ValueError(f"decoded {len(blob)} bytes, .ind declares {usize}")
    return blob, {
        "uncompressed": usize,
        "compressed": csize,
        "chunks": count,
        "chunk_size": chunk_size,
    }


def logical_listing(source, rel: str, cache: dict | None = None,
                    ignore_artifacts: bool = False) -> dict[str, LogicalEntry]:
    """Map logical names (DRSTR names) to actual entries in one directory."""
    cache_key = (rel, ignore_artifacts)
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    out: dict[str, LogicalEntry] = {}
    for entry in source.list_dir(rel):
        if is_dump_artifact(entry.name, ignore_artifacts):
            continue
        if entry.name == "DRSTR001.DAT" or entry.name.endswith(".ind"):
            continue
        if entry.name.endswith(".cmp"):
            logical = entry.name[:-4]
            ind_rel = f"{rel}/{logical}.ind".strip("/")
            try:
                ind = source.read_range(ind_rel, 0, 4)
                usize = _u32(ind, 0)
            except (FileNotFoundError, ValueError) as exc:
                raise ValueError(f"{rel}/{entry.name}: missing or bad .ind: {exc}") from exc
            out[logical] = LogicalEntry(logical, False, usize, entry.name)
        elif entry.is_dir:
            out[entry.name] = LogicalEntry(
                entry.name, True,
                tree_size(source, entry.path, cache, ignore_artifacts),
                entry.name,
            )
        else:
            out[entry.name] = LogicalEntry(entry.name, False, entry.size, entry.name)
    if cache is not None:
        cache[cache_key] = out
    return out


def tree_size(source, rel: str, cache: dict | None = None,
              ignore_artifacts: bool = False) -> int:
    return sum(e.size for e in logical_listing(source, rel, cache,
                                               ignore_artifacts).values()) & 0xFFFFFFFF


def safe_list_dir(source, rel: str) -> list[Entry]:
    try:
        return source.list_dir(rel)
    except (OSError, ValueError):
        return []


def logical_tree(source, ignore_artifacts: bool = False) -> tuple[dict[str, dict[str, LogicalEntry]], set[str]]:
    cache: dict[tuple[str, bool], dict[str, LogicalEntry]] = {}
    by_path: dict[str, dict[str, LogicalEntry]] = {}
    dirs: set[str] = set()

    def rec(rel: str):
        dirs.add(rel)
        listing = logical_listing(source, rel, cache, ignore_artifacts)
        by_path[rel] = listing
        for entry in listing.values():
            if entry.is_dir:
                rec(f"{rel}/{entry.name}".strip("/"))

    rec("")
    return by_path, dirs


# ---------------------------------------------------------------------------
# checks


def check_mbr(source, report: Report) -> None:
    check = report.add(Check("mbr"))
    if not isinstance(source, Fat32Image):
        check.stats["skipped"] = "root source has no MBR"
        return
    entries = leafimg.mbr_entries(source.handle)
    check.stats["partitions"] = entries
    fat = [e for e in entries if e["type"] in FAT32_TYPES]
    if not fat:
        check.error("no FAT32 partition (type 0x0b/0x0c)")
        return
    if len(fat) > 1:
        check.warn(f"{len(fat)} FAT32 partitions; using the first")
    part = fat[0]
    if part["offset"] + part["bytes"] > source.size:
        check.error(
            f"partition ends at {part['offset'] + part['bytes']}, image has {source.size}"
        )
    if part["offset"] == 0:
        check.error("FAT partition starts at offset 0; expected an MBR")
    check.stats["partition"] = part


def check_fat(source, report: Report) -> None:
    check = report.add(Check("fat"))
    if not isinstance(source, Fat32Image):
        check.stats["skipped"] = "root source has no FAT geometry"
        return
    geo = source.geometry
    check.stats.update(asdict(geo))
    if geo.cluster_bytes != 65536:
        check.warn(f"cluster size is {geo.cluster_bytes}, expected 65536")
    if geo.fat_count < 1:
        check.error("no FAT copy")
    if geo.root_cluster < 2:
        check.error(f"invalid root cluster {geo.root_cluster}")
    if not geo.label:
        check.warn("no volume label")
    if geo.total_sectors * geo.bytes_per_sector > geo.partition_bytes:
        check.error("FAT total sectors exceed the partition size")


def check_tree(source, report: Report, partial: bool = False,
               ignore_artifacts: bool = False) -> None:
    check = report.add(Check("tree"))
    top = {e.name for e in source.list_dir("") if not is_dump_artifact(e.name, ignore_artifacts)}
    required = REQUIRED_TOP - ({"VER_INFO"} if partial else set()) - {"TMC"}
    if not (top & {"TMC", "XMD"}):
        check.error("missing top-level entry 'TMC' or 'XMD'")
    missing = sorted(required - top)
    for name in missing:
        check.error(f"missing top-level entry {name!r}")
    extra = sorted(top - REQUIRED_TOP - {"XMD"})
    if partial:
        check.stats["partial"] = True
    if extra:
        check.warn(f"unexpected top-level entries: {', '.join(extra)}")
    files = dirs = total = 0
    for entry in source.walk():
        if path_has_artifact(entry.path, ignore_artifacts):
            continue
        if entry.is_dir:
            dirs += 1
        else:
            files += 1
            total += entry.size
    check.stats.update(files=files, dirs=dirs, bytes=total)
    if files == 0:
        check.error("card contains no files")
    if total == 0:
        check.error("card contains no file bytes")
    mapal = safe_list_dir(source, "MAPAL001")
    if not mapal:
        check.error("MAPAL001 is empty or missing")
    elif not any(e.name == "LEV3456R.DAT" for e in mapal):
        check.error("MAPAL001/LEV3456R.DAT is missing")
    refer = safe_list_dir(source, "REFER001")
    if not any(e.name.endswith(".cmp") for e in refer):
        check.error("REFER001 contains no .cmp files")
    if not any(e.name.endswith(".ind") for e in refer):
        check.error("REFER001 contains no .ind files")


def check_headers(source, report: Report, ignore_artifacts: bool = False) -> None:
    check = report.add(Check("headers"))
    targets = ["MMAIN001.DAT"]
    for rel in ("MAPAL001", "RDSTM001", "REFER002"):
        for entry in safe_list_dir(source, rel):
            if is_dump_artifact(entry.name, ignore_artifacts):
                continue
            if not entry.is_dir and entry.name.endswith(".DAT"):
                targets.append(entry.path)
    if any(e.name == "BICON001.DAT" for e in safe_list_dir(source, "BICON001")):
        targets.append("BICON001/BICON001.DAT")
    checked = 0
    for rel in targets:
        try:
            data = source.read_range(rel, 0, 512)
        except OSError as exc:
            check.error(f"{rel}: {exc}")
            continue
        before = len(check.errors)
        check_common_header(data, rel, check)
        if len(check.errors) == before:
            checked += 1
    check.stats["files"] = len(targets)
    check.stats["ok"] = checked


def check_cmp(source, report: Report, fast: bool = False,
              ignore_artifacts: bool = False) -> None:
    check = report.add(Check("cmp"))
    directory = "REFER001"
    pairs = 0
    logical = stored = 0
    headers_ok = 0
    listing = safe_list_dir(source, directory)
    for entry in sorted(listing, key=lambda e: e.name):
        if is_dump_artifact(entry.name, ignore_artifacts):
            continue
        if not entry.name.endswith(".ind"):
            continue
        pairs += 1
        stem = entry.name[:-4]
        cmp_name = f"{stem}.cmp"
        try:
            ind_data = source.read(entry.path)
            cmp_data = source.read(f"{directory}/{cmp_name}")
            usize, csize, count, chunk_size, offsets = ind_values(ind_data)
            logical += usize
            stored += csize
            if fast:
                continue
            blob, info = decode_cmp(cmp_data, ind_data)
            before = len(check.errors)
            check_common_header(blob, f"{directory}/{stem}", check)
            if len(check.errors) == before:
                headers_ok += 1
        except (OSError, ValueError) as exc:
            check.error(f"{entry.path}: {exc}")
    check.stats.update(
        pairs=pairs, logical=logical, stored=stored, headers_ok=headers_ok,
        fast=fast,
    )
    if pairs == 0:
        check.error("no .ind/.cmp pairs found")
    if not fast and headers_ok != pairs:
        check.error(f"{pairs - headers_ok} decompressed file(s) lack the common header")


def check_drstr(source, report: Report, partial: bool = False,
                ignore_artifacts: bool = False) -> None:
    check = report.add(Check("drstr"))
    try:
        data = source.read("DRSTR001.DAT")
    except OSError as exc:
        check.error(f"DRSTR001.DAT: {exc}")
        return
    try:
        tree = drstr.parse(data)
    except ValueError as exc:
        check.error(f"DRSTR001.DAT parse failed: {exc}")
        return
    nodes = tree["nodes"]
    check.stats["nodes"] = len(nodes)
    check.stats["table_end"] = tree["table_end"]

    paths: dict[int, str] = {}
    for i, node in enumerate(nodes):
        if i == 0:
            if node["name"] != "/":
                check.error(f"node 0 name is {node['name']!r}, expected '/'")
            path = ""
        else:
            parent = node["parent"]
            if parent is None or parent >= i or parent not in paths:
                check.error(f"node {i} ({node['name']}): bad parent {parent}")
                path = f"<bad:{i}>"
            else:
                path = f"{paths[parent]}/{node['name']}".strip("/")
        paths[i] = path
        if node["next_index"] != i + 1:
            check.error(
                f"node {i}: next_index {node['next_index']} != {i + 1}"
            )
        if node["entry_count"] != len(node["entries"]):
            check.error(
                f"node {i}: entry_count {node['entry_count']} != "
                f"{len(node['entries'])} parsed"
            )
        if node["listing_offset"] < tree["table_end"]:
            check.error(
                f"node {i}: listing offset 0x{node['listing_offset']:x} "
                f"is inside the node table"
            )

    if len({p for p in paths.values()}) != len(paths):
        check.error("duplicate directory paths in DRSTR")

    intervals = sorted(
        (n["listing_offset"], n["listing_offset"] + n["entry_count"] * 32)
        for n in nodes
    )
    prev_end = tree["table_end"]
    for start, end in intervals:
        if start < prev_end:
            check.error(f"overlapping DRSTR listings at 0x{start:x}")
        prev_end = max(prev_end, end)
    if prev_end > len(data):
        check.error(f"DRSTR listing ends at 0x{prev_end:x}, file is 0x{len(data):x}")
    elif prev_end < len(data):
        check.warn(f"DRSTR has {len(data) - prev_end} trailing bytes")

    try:
        logical, actual_dirs = logical_tree(source, ignore_artifacts)
    except (OSError, ValueError) as exc:
        check.error(f"cannot build logical tree: {exc}")
        return

    drstr_dirs = set(paths.values())
    missing_dirs = drstr_dirs - actual_dirs
    if partial:
        allowed = {p for p in missing_dirs if p == "VER_INFO" or p.startswith("VER_INFO/")}
        missing_dirs -= allowed
    for path in sorted(missing_dirs):
        check.error(f"DRSTR directory {path!r} does not exist")
    for path in sorted(actual_dirs - drstr_dirs):
        check.error(f"directory {path!r} is not listed in DRSTR")

    entry_count = 0
    for i, node in enumerate(nodes):
        path = paths[i]
        listing = logical.get(path)
        if listing is None:
            continue
        drstr_names = {e["name"] for e in node["entries"]}
        actual_names = set(listing)
        ignored_names: set[str] = set()
        if partial and path == "" and "VER_INFO" in drstr_names:
            ignored_names.add("VER_INFO")
            check.warn("partial tree: DRSTR lists 'VER_INFO', which is not present")
        # DRSTR names are fixed 13-byte fields. A longer FAT long name is
        # stored as its first 13 bytes, and FAT short names may differ only in
        # case, so compare normalized 13-byte, case-insensitive keys.
        def _drstr_key(name: str) -> str:
            return name.lower()[:13]

        drstr_keys: dict[str, str] = {}
        for name in drstr_names:
            if name in ignored_names:
                continue
            drstr_keys.setdefault(_drstr_key(name), name)
        actual_keys: dict[str, str] = {}
        for name in actual_names:
            actual_keys.setdefault(_drstr_key(name), name)

        for key in sorted(set(drstr_keys) - set(actual_keys)):
            check.error(f"{path or '/'}: DRSTR lists {drstr_keys[key]!r}, not on card")
        for key in sorted(set(actual_keys) - set(drstr_keys)):
            check.error(f"{path or '/'}: {actual_keys[key]!r} is on card but not in DRSTR")

        for entry in node["entries"]:
            if entry["name"] in ignored_names:
                continue
            entry_count += 1
            actual = listing.get(entry["name"])
            if actual is None:
                matches = [
                    item for name, item in listing.items()
                    if name.lower() == entry["name"].lower()
                ]
                if not matches and len(entry["name"]) == 13:
                    matches = [
                        item for name, item in listing.items()
                        if name.lower().startswith(entry["name"].lower())
                    ]
                if len(matches) == 1:
                    actual = matches[0]
                elif len(matches) > 1:
                    check.error(
                        f"{path or '/'}/{entry['name']}: ambiguous DRSTR name"
                    )
                    continue
            if actual is None:
                continue
            expected_dir = entry["type"] == 2
            if entry["type"] not in (0, 2):
                check.error(
                    f"{path or '/'}/{entry['name']}: unknown type {entry['type']}"
                )
            if expected_dir != actual.is_dir:
                check.error(
                    f"{path or '/'}/{entry['name']}: DRSTR type {entry['type']} "
                    f"but actual {'dir' if actual.is_dir else 'file'}"
                )
            if entry["value"] != actual.size:
                check.error(
                    f"{path or '/'}/{entry['name']}: DRSTR size {entry['value']} "
                    f"!= actual {actual.size}"
                )
    check.stats["entries"] = entry_count
    check.stats["dirs"] = len(drstr_dirs)
    check.stats["files"] = entry_count - sum(
        1 for n in nodes for e in n["entries"] if e["type"] == 2
    )


def check_mmain(source, report: Report, ignore_artifacts: bool = False) -> None:
    check = report.add(Check("mmain"))
    try:
        mmain = source.read("MMAIN001.DAT")
    except OSError as exc:
        check.error(f"MMAIN001.DAT: {exc}")
        return
    try:
        master = parse_level_table(mmain)
    except ValueError as exc:
        check.error(f"MMAIN001.DAT level table: {exc}")
        return
    check_common_header(mmain, "MMAIN001.DAT", check)

    tiles = [
        e for e in safe_list_dir(source, "MAPAL001")
        if not is_dump_artifact(e.name, ignore_artifacts)
        and not e.is_dir and e.name.endswith(".DAT")
    ]
    tile_names = {e.name for e in tiles}
    for entry in tiles:
        if entry.name == "LEV3456R.DAT":
            continue
        if not mesh_grid.TILE_RE.match(entry.name):
            check.error(f"MAPAL001/{entry.name}: not a BxxRyyR.DAT tile")
    if "LEV3456R.DAT" not in tile_names:
        check.error("MAPAL001/LEV3456R.DAT is missing")

    totals: dict[tuple[int, int], int] = {}
    types: dict[tuple[int, int], int] = {}
    for entry in tiles:
        try:
            head = source.read_range(entry.path, 0, 0x400)
            groups = parse_level_table(head)
        except (OSError, ValueError) as exc:
            check.error(f"{entry.path}: {exc}")
            continue
        for group in groups:
            for row in group["rows"]:
                key = (group["section"], row["level"])
                totals[key] = totals.get(key, 0) + row["count"]
                types[key] = row["type"]

    rows = 0
    ok = 0
    for group in master:
        for row in group["rows"]:
            rows += 1
            key = (group["section"], row["level"])
            expected = totals.get(key, 0)
            if row["count"] == expected:
                ok += 1
            else:
                check.error(
                    f"MMAIN section {key[0]} level {key[1]}: "
                    f"count {row['count']} != tile sum {expected}"
                )
            if types.get(key, row["type"]) != row["type"]:
                check.warn(
                    f"MMAIN section {key[0]} level {key[1]}: "
                    f"type {row['type']} != tile type {types[key]}"
                )
    for key in sorted(set(totals) - {(g["section"], r["level"]) for g in master for r in g["rows"]}):
        check.error(f"tile table has section {key[0]} level {key[1]} not in MMAIN")
    check.stats.update(tiles=len(tiles), rows=rows, ok=ok)


def check_version(source, report: Report, partial: bool = False) -> None:
    check = report.add(Check("version"))
    hdd = b""
    try:
        hdd = source.read("VER_INFO/HDD_INFO.TXT")
    except OSError as exc:
        if partial:
            check.warn(f"partial tree: VER_INFO/HDD_INFO.TXT missing ({exc})")
        else:
            check.error(f"VER_INFO/HDD_INFO.TXT: {exc}")
            return
    if hdd:
        check.stats["hdd_size"] = len(hdd)
        lines = hdd.split(b"\r\n")
        if len(lines) != 6:
            check.error(f"HDD_INFO.TXT has {len(lines)} CRLF-separated lines, expected 6")
        for i, line in enumerate(lines):
            if not line:
                check.error(f"HDD_INFO.TXT line {i + 1} is empty")
            if any(b < 0x20 or b > 0x7E for b in line):
                check.error(f"HDD_INFO.TXT line {i + 1} is not printable ASCII")
        if hdd.endswith(b"\r\n"):
            check.warn("HDD_INFO.TXT ends with CRLF; the factory file does not")

        label = getattr(source, "label", "")
        if label and len(lines) >= 2:
            line2 = lines[1].decode("ascii", "replace")
            if line2 != label:
                check.error(f"HDD_INFO line 2 {line2!r} != FAT label {label!r}")
            else:
                check.stats["label_match"] = True

    try:
        cmp_list = source.read("CMP.LST")
    except OSError as exc:
        check.error(f"CMP.LST: {exc}")
    else:
        if cmp_list != CMP_LIST:
            check.error(f"CMP.LST is {cmp_list!r}, expected {CMP_LIST!r}")

    if isinstance(source, Fat32Image):
        copy = source.read_absolute(HDD_COPY_OFFSET, len(hdd))
        if copy != hdd:
            check.error(
                f"image copy at 0x{HDD_COPY_OFFSET:08x} differs from "
                f"VER_INFO/HDD_INFO.TXT"
            )
        else:
            check.stats["image_copy"] = "identical"


def check_hash(source, report: Report, expect: str | None) -> None:
    check = report.add(Check("sha256"))
    if not isinstance(source, Fat32Image):
        check.stats["skipped"] = "root source has no image hash"
        return
    digest = hashlib.sha256()
    source.handle.seek(0)
    for block in iter(lambda: source.handle.read(8 << 20), b""):
        digest.update(block)
    actual = digest.hexdigest()
    check.stats["sha256"] = actual
    if expect and actual != expect:
        check.error(f"image SHA-256 {actual} != expected {expect}")


# ---------------------------------------------------------------------------
# CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image", help="raw SD image")
    source.add_argument("--root", help="extracted card root")
    parser.add_argument("--json", help="write a JSON report to this path")
    parser.add_argument("--json-only", action="store_true",
                        help="do not print the human summary")
    parser.add_argument("--strict", action="store_true",
                        help="treat warnings as errors")
    parser.add_argument("--fast", action="store_true",
                        help="skip zlib decompression of .cmp payloads")
    parser.add_argument("--partial", action="store_true",
                        help="map-only tree: allow a missing VER_INFO directory")
    parser.add_argument("--ignore-dump-artifacts", action="store_true",
                        help="ignore macOS ._*, .fseventsd, System Volume Information")
    parser.add_argument("--hash", action="store_true",
                        help="compute the image SHA-256 (slow)")
    parser.add_argument("--expect-sha256",
                        help="fail if the image SHA-256 does not match")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.expect_sha256 and not args.hash:
        args.hash = True
    try:
        if args.image:
            source = Fat32Image(Path(args.image))
            source_info = {
                "kind": "image",
                "path": str(Path(args.image)),
                "size": source.size,
            }
        else:
            source = RootSource(Path(args.root))
            source_info = {"kind": "root", "path": str(Path(args.root))}
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        report = Report("L1", source_info)
        check_mbr(source, report)
        check_fat(source, report)
        check_tree(source, report, partial=args.partial,
                   ignore_artifacts=args.ignore_dump_artifacts)
        check_headers(source, report, ignore_artifacts=args.ignore_dump_artifacts)
        check_cmp(source, report, fast=args.fast,
                  ignore_artifacts=args.ignore_dump_artifacts)
        check_drstr(source, report, partial=args.partial,
                    ignore_artifacts=args.ignore_dump_artifacts)
        check_mmain(source, report, ignore_artifacts=args.ignore_dump_artifacts)
        check_version(source, report, partial=args.partial)
        if args.hash:
            check_hash(source, report, args.expect_sha256)
        result = report.finish(strict=args.strict)
    finally:
        source.close()

    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2) + "\n")
    if not args.json_only:
        print(f"L1 whole-card validation: {source_info['path']}")
        for check in result["checks"]:
            status = "OK" if check["ok"] else "FAIL"
            details = []
            if check["stats"]:
                details.append(", ".join(f"{k}={v}" for k, v in check["stats"].items()
                                         if not isinstance(v, (dict, list))))
            print(f"  [{check['id']}] {status}"
                  + (f" ({'; '.join(details)})" if details else ""))
            for error in check["errors"]:
                print(f"    ERROR {error}")
            for warning in check["warnings"]:
                print(f"    WARN  {warning}")
        print("RESULT:", "PASS" if result["ok"] else "FAIL")
        if result["warnings"]:
            print(f"warnings: {len(result['warnings'])}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
