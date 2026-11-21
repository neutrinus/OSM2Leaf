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
    skipped: str = ""

    def error(self, message: str) -> None:
        self.ok = False
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def skip(self, reason: str) -> None:
        """A check the source cannot satisfy is SKIP, never PASS.

        ``ok`` stays true so a clean run still exits 0, but the JSON carries
        ``status: SKIP`` and this reason so a skipped check is never read as a
        pass (H103, H104 key on this).
        """
        self.skipped = reason
        self.stats.setdefault("skipped", reason)

    def status(self, strict: bool = False) -> str:
        if not self.ok:
            return "FAIL"
        if strict and self.warnings:
            return "FAIL"
        return "SKIP" if self.skipped else "PASS"


class Report:
    def __init__(self, layer: str, source: dict, fixture: str | None = None):
        self.layer = layer
        self.source = source
        self.fixture = fixture
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
        checks = []
        for c in self.checks:
            row = asdict(c)
            row["status"] = c.status(strict=strict)
            row["skipped"] = c.skipped or None
            checks.append(row)
        counts = {"pass": 0, "fail": 0, "skip": 0}
        for c in self.checks:
            counts[c.status(strict=strict).lower()] += 1
        result = {
            "layer": self.layer,
            "ok": not errors,
            "source": self.source,
            "checks": checks,
            "counts": counts,
            "errors": errors,
            "warnings": warnings,
        }
        # H103: a --generate-fixture run sets ``fixture`` to "none", so a
        # vendor-backed run (fixture absent) can never be mistaken for a
        # fixture run downstream (the L1 registry row keys on this).
        if self.fixture is not None:
            result["fixture"] = self.fixture
        return result


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

    @property
    def cluster_count(self) -> int:
        """Data clusters the FAT geometry can address (2 .. cluster_count+1)."""
        return ((self.partition_bytes // self.bytes_per_sector)
                - self.reserved_sectors
                - self.fat_count * self.fat_size_sectors) // self.sectors_per_cluster


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
        # H105: every out-of-range cluster the walker refused to read. A check
        # that walks the tree turns this into a named failure (fat) instead of
        # an empty tree, so a card whose FAT/DIRENT chain runs past the data
        # area cannot pass by reading as "no files".
        self.cluster_errors: list[str] = []

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
        if cluster >= 2 + geo.cluster_count:
            msg = (f"cluster {cluster} out of range "
                   f"(data area holds clusters 2..{geo.cluster_count + 1})")
            if msg not in self.cluster_errors:
                self.cluster_errors.append(msg)
            return b""
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
        check.skip("root source has no MBR")
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
        check.skip("root source has no FAT geometry")
        return
    geo = source.geometry
    check.stats.update(asdict(geo))
    try:
        for _entry in source.walk():
            pass
    except (OSError, ValueError):
        pass
    for message in getattr(source, "cluster_errors", ()):
        check.error(message)
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
        check.skip("root source has no image hash")
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
# Deterministic no-vendor fixture tree (H103)
# ---------------------------------------------------------------------------


FIXTURE_DATA_VERSION = "11/06/27/01"
FIXTURE_CELL = "B48R058R"
FIXTURE_HDD_INFO = (
    b"TST-000-000\r\nTST-000-000\r\n00-000000-00\r\n"
    b"TST00-EVEUR\r\n11-05\r\n000000000000"
)


def _fixture_put_utf16be(buf: bytearray, off: int, text: str) -> None:
    raw = text.encode("utf-16-be")
    buf[off:off + len(raw)] = raw


def _fixture_header() -> bytearray:
    """A 512-byte clone of a ZE0 common header, built from format fields only.

    All values are format constants that ``check_common_header`` asserts; no
    vendor file is read.  Used as the decoded payload of the REFER001 pair.
    """
    buf = bytearray(b"\xff" * 512)
    _fixture_put_utf16be(buf, 0x00, "CLARION")
    _fixture_put_utf16be(buf, 0x40, "HITACHI")
    _fixture_put_utf16be(buf, 0x80, "CLA-NAVI05-01")
    _fixture_put_utf16be(buf, 0xA0, "FORMAT VERSION X08-02-00")
    _fixture_put_utf16be(buf, 0xE0, "DATA VERSION " + FIXTURE_DATA_VERSION)
    buf[0x160:0x162] = b"\x16\x00"
    _fixture_put_utf16be(buf, 0x162, "V05.00.00")
    buf[0x180:0x18C] = bytes.fromhex("ff ff 24 ff 12 c0 05 00 fb 50 0f f0")
    buf[0x18C:0x1A0] = b"\x3f" * 20
    buf[0x1A0:0x1AC] = b"\xff" * 12
    return buf


def _fixture_lev_tile(ze0_tile_header, clarion_tile) -> bytes:
    """``LEV3456R.DAT``: sections 1 and 2, no directories, ZE0 header."""
    sections = [
        dict(id=sid, count=0,
             levels=[dict(level=lvl, typ=typ, dirs=[])
                     for lvl, typ in ze0_tile_header.LEVELS[sid]])
        for sid in (1, 2)
    ]
    for sec in sections:
        words, _offsets, _groups = clarion_tile.table_words(sec)
        sec["count"] = -(-2 * words // 256)
    tile = dict(sections=sections)
    groups = [(sec["id"], [(L["level"], L["typ"], 0) for L in sec["levels"]])
              for sec in sections]
    tile["header"] = ze0_tile_header.author(
        groups, [], (0, 0, 0, 0), FIXTURE_DATA_VERSION, ())
    return clarion_tile.write_tile(tile)


def _fixture_mmain(ze0_tile_header, totals: dict) -> bytes:
    """MMAIN001.DAT whose level-table counts equal the tile-header sums."""
    groups = []
    for sid, rows in sorted(ze0_tile_header.LEVELS.items()):
        groups.append((sid, [
            (lvl, typ, totals.get((sid, lvl), [typ, 0])[1])
            for lvl, typ in rows
        ]))
    return bytes(ze0_tile_header.author(
        groups, [], (0, 0, 0, 0), FIXTURE_DATA_VERSION, ()))


def _fixture_tile_totals(root: Path) -> dict:
    totals: dict[tuple[int, int], list[int]] = {}
    for path in sorted((root / "MAPAL001").glob("*.DAT")):
        for group in parse_level_table(path.read_bytes()[:0x400], 0x1AC):
            for row in group["rows"]:
                acc = totals.setdefault((group["section"], row["level"]),
                                        [row["type"], 0])
                acc[0] = row["type"]
                acc[1] += row["count"]
    return totals


def generate_fixture(root, break_kind: str | None = None) -> Path:
    """Write a deterministic, vendor-free card tree ``cardcheck`` accepts.

    The tree satisfies every L1 check a FAT32-root tree can (``tree``,
    ``headers``, ``cmp``, ``drstr``, ``mmain``, ``version``); ``mbr``/``fat``/
    ``sha256`` are image-only and are reported SKIP with a reason, never PASS.

    Every level/box/header value is derived from the existing modules
    (``ze0_tile_header`` for ZE0 headers, ``tilewriter.make_factory`` +
    ``ze0_tile_header.convert`` for the tile body, ``tilewriter.cell_db_bounds``
    for the box, and the tile headers themselves for the MMAIN counts and the
    DRSTR sizes via ``drstr_ze0.build``).  Fixed timestamps keep it
    byte-identical across runs.  No OSM input, no vendor bytes.

    ``break_kind`` (H105) applies one deliberate defect after the tree is
    otherwise complete; the matching cardcheck rule then fails. The FAT kind
    needs clusters, so it lives in ``generate_fixture_image``.
    """
    import cmpind_writer
    import drstr_ze0
    import tilewriter
    import ze0_tile_header

    root = Path(root)
    clarion_tile = tilewriter.clarion_tile
    for name in ("MAPAL001", "REFER001", "REFER002", "RDSTM001",
                 "BICON001", "OPNG", "SPEECH", "TMC", "VER_INFO"):
        (root / name).mkdir(parents=True, exist_ok=True)

    # MAPAL001: the LEV file and one real-grid BxxRyyR tile whose body comes
    # from tilewriter.make_factory and whose header is re-authored to ZE0.
    (root / "MAPAL001" / "LEV3456R.DAT").write_bytes(
        _fixture_lev_tile(ze0_tile_header, clarion_tile))
    box = tilewriter.cell_db_bounds(FIXTURE_CELL)
    tile = ze0_tile_header.convert(
        tilewriter.make_factory(FIXTURE_CELL), box=box,
        data_version=FIXTURE_DATA_VERSION)
    (root / "MAPAL001" / f"{FIXTURE_CELL}.DAT").write_bytes(tile)

    # MMAIN001.DAT level-table counts = the sum over every tile header.
    (root / "MMAIN001.DAT").write_bytes(
        _fixture_mmain(ze0_tile_header, _fixture_tile_totals(root)))

    # REFER001: one .cmp/.ind pair whose decoded payload carries the header.
    payload = bytearray(_fixture_header())
    payload.extend(b"\x00" * 64)
    cmpind_writer.CmpFile.from_dat(bytes(payload)).write(
        root / "REFER001", "POINT001.DAT")

    (root / "CMP.LST").write_bytes(CMP_LIST)
    (root / "VER_INFO" / "HDD_INFO.TXT").write_bytes(FIXTURE_HDD_INFO)

    # DRSTR001.DAT last: it sizes every file/dir actually on disk.
    (root / "DRSTR001.DAT").write_bytes(drstr_ze0.build(root))
    if break_kind is not None:
        if break_kind in IMAGE_ONLY_BREAKS:
            raise ValueError(
                f"break {break_kind!r} needs a FAT/MMAIN-aware image; use "
                f"--generate-fixture-image instead of --generate-fixture")
        _apply_break(root, break_kind)
    return root


# ---------------------------------------------------------------------------
# H105: deliberate breaks — the negative control for H103's fixture
# ---------------------------------------------------------------------------
#
# A tree that passes but cannot fail proves nothing. Every kind below trips an
# *existing* cardcheck rule on a tree the checker otherwise accepts, so
# ``good rc=0 -> break rc=1 -> same check id`` tests the checker (a check that
# degraded to ``return PASS`` would leave the broken tree at rc=0), not a new
# rule. No new validator rule, no vendor bytes (H105 scope).

BREAK_KINDS = (
    "mmain-missing-tile-level",
    "drstr-size-mismatch",
    "tile-level-not-in-mmain",
    "fat-cluster-out-of-range",
    "header-magic",
)

# kind -> the check id the good fixture passes and the break must fail.
BREAK_TARGET = {
    "mmain-missing-tile-level": "mmain",
    "drstr-size-mismatch": "drstr",
    "tile-level-not-in-mmain": "mmain",
    "fat-cluster-out-of-range": "fat",
    "header-magic": "headers",
}

# The FAT kind reads the MBR/FAT/data-area geometry, which a ``--root`` tree
# does not carry (``fat`` is SKIP there). It needs ``--generate-fixture-image``.
IMAGE_ONLY_BREAKS = frozenset({"fat-cluster-out-of-range"})

FIXTURE_IMAGE_LABEL = "TST-000-000"
FIXTURE_IMAGE_PART_LBA = 2048             # 1 MiB: the MBR sits at sector 0
FIXTURE_IMAGE_SECTORS_PER_CLUSTER = 128   # 64 KiB, the factory cluster size
FIXTURE_IMAGE_TAIL_SECTORS = 8192         # room for a few 64 KiB clusters
FIXTURE_IMAGE_HDD_SECTOR = HDD_COPY_OFFSET // SECTOR
FIXTURE_IMAGE_TOTAL_SECTORS = FIXTURE_IMAGE_HDD_SECTOR + FIXTURE_IMAGE_TAIL_SECTORS


def _fixture_level_table_positions(data: bytes, offset: int = 0x1AC):
    """Yield (section, level, type, count, count_offset) from a level table."""
    if offset + 2 > len(data):
        raise ValueError("level table offset out of range")
    count = _be16(data, offset)
    pos = offset + 2
    for _ in range(count):
        if pos + 2 > len(data):
            raise ValueError("truncated level table group")
        section, rows = data[pos], data[pos + 1]
        pos += 2
        for _ in range(rows):
            if pos + 4 > len(data):
                raise ValueError("truncated level table rows")
            level, kind, value = struct.unpack_from(">BBH", data, pos)
            yield section, level, kind, value, pos + 2
            pos += 4


def _break_mmain_missing_section(root, section: int = 4) -> None:
    """Drop one section's group from MMAIN001.DAT.

    ``check_mmain`` then finds a tile level whose section is absent from the
    master table (``tile table has section 4 level 1 not in MMAIN``) — mmain.
    """
    path = Path(root) / "MMAIN001.DAT"
    data = bytearray(path.read_bytes())
    groups = [g for g in parse_level_table(bytes(data), 0x1AC)
              if g["section"] != section]
    if len(groups) == _be16(data, 0x1AC):
        raise ValueError(f"MMAIN has no section {section} to drop")
    table = bytearray(struct.pack(">H", len(groups)))
    for group in groups:
        table += bytes([group["section"], len(group["rows"])])
        for row in group["rows"]:
            table += struct.pack(">BBH", row["level"], row["type"], row["count"])
    data[0x1AC:0x1AC + len(table)] = table
    path.write_bytes(bytes(data))


def _break_drstr_size(root, delta: int = 1) -> None:
    """Add ``delta`` to the first file entry's DRSTR size.

    ``check_drstr`` compares each entry's logical size with the file on disk and
    fails ``DRSTR size N != actual M`` — drstr.
    """
    path = Path(root) / "DRSTR001.DAT"
    data = bytearray(path.read_bytes())
    for node in drstr.parse(bytes(data))["nodes"]:
        for entry in node["entries"]:
            if entry["type"] != 0:
                continue
            off = node["listing_offset"] + entry["index"] * 32 + 0x1C
            value = struct.unpack_from("<I", data, off)[0]
            struct.pack_into("<I", data, off, (value + delta) & 0xFFFFFFFF)
            path.write_bytes(bytes(data))
            return
    raise ValueError("DRSTR has no file entry to resize")


def _break_tile_level_not_in_mmain(root, section: int = 4,
                                   level: int = 1, count: int = 7) -> None:
    """Raise one tile-header level count above the MMAIN total.

    ``check_mmain`` compares the tile sum with the master count and fails
    ``MMAIN section 4 level 1: count 1 != tile sum 7`` — mmain.
    """
    for path in sorted((Path(root) / "MAPAL001").glob("*.DAT")):
        data = bytearray(path.read_bytes())
        try:
            rows = list(_fixture_level_table_positions(bytes(data), 0x1AC))
        except ValueError:
            continue
        for sid, lvl, _kind, _value, count_off in rows:
            if (sid, lvl) == (section, level):
                struct.pack_into(">H", data, count_off, count)
                path.write_bytes(bytes(data))
                return
    raise ValueError(f"no tile header lists section {section} level {level}")


def _break_header_magic(root, rel: str = f"MAPAL001/{FIXTURE_CELL}.DAT") -> None:
    """Overwrite the CLARION magic at 0x00 of one header.

    ``check_headers`` asks every header for its identity strings and fails
    ``header field 0x00 is ... expected 'CLARION'`` — headers.
    """
    path = Path(root) / rel
    data = bytearray(path.read_bytes())
    data[0x00:0x0C] = "XARION".encode("utf-16-be")
    data[0x0C:0x0E] = b"\xff\xff"
    path.write_bytes(bytes(data))


def _break_fat_cluster_range(img) -> None:
    """Point MAPAL001/LEV3456R.DAT's directory entry past the data area.

    ``check_fat`` fails ``cluster N out of range`` — fat. The cluster is read
    by ``check_mmain`` and ``check_headers`` too, so it also shows up as an
    empty file there; the row asserts only that ``fat`` is among the FAILs
    (H105 Stop rule).
    """
    img = Path(img)
    source = Fat32Image(img)
    try:
        geo = source.geometry
        bad = 2 + geo.cluster_count + 16
        data_off = geo.partition_offset + (
            geo.reserved_sectors + geo.fat_count * geo.fat_size_sectors
        ) * geo.bytes_per_sector
        listing_off = data_off + (geo.root_cluster - 2) * geo.cluster_bytes
        with img.open("r+b") as handle:
            handle.seek(listing_off)
            listing = handle.read(geo.cluster_bytes)
            for i in range(0, len(listing) - 31, 32):
                slot = listing[i:i + 32]
                if slot[0] in (0x00, 0xE5) or slot[11] == 0x08:
                    continue
                if slot[0:11] == b"MAPAL001   ":
                    patched = bytearray(slot)
                    struct.pack_into("<H", patched, 20, (bad >> 16) & 0xFFFF)
                    struct.pack_into("<H", patched, 26, bad & 0xFFFF)
                    handle.seek(listing_off + i)
                    handle.write(patched)
                    return
    finally:
        source.close()
    raise ValueError("MAPAL001 directory entry not found in the image")


def _apply_break(root, kind: str, img=None) -> None:
    if kind == "mmain-missing-tile-level":
        _break_mmain_missing_section(root)
    elif kind == "drstr-size-mismatch":
        _break_drstr_size(root)
    elif kind == "tile-level-not-in-mmain":
        _break_tile_level_not_in_mmain(root)
    elif kind == "header-magic":
        _break_header_magic(root)
    elif kind == "fat-cluster-out-of-range":
        if img is None:
            raise ValueError("fat-cluster-out-of-range needs an image")
        _break_fat_cluster_range(img)
    else:
        raise ValueError(
            f"unknown break kind {kind!r}; choose from {', '.join(BREAK_KINDS)}")


def _build_fixture_image(tree, img) -> Path:
    """Write a FAT32 image carrying ``tree``, mirroring HDD_INFO at 0x06000000.

    The partition sits after ``0x06000000`` (the copy ``check_version``
    compares) and uses 64 KiB clusters, the factory geometry. The ~100 MiB file
    is sparse (~8 MiB written) and holds no vendor bytes.
    """
    import mkcard

    tree, img = Path(tree), Path(img)
    template = img.with_name(img.name + ".tmpl")
    mkcard.make_synthetic_image(
        template, {"X.TXT": b"x" * 64},
        part_lba=FIXTURE_IMAGE_PART_LBA,
        total_sectors=FIXTURE_IMAGE_TOTAL_SECTORS,
        spc=FIXTURE_IMAGE_SECTORS_PER_CLUSTER, label=FIXTURE_IMAGE_LABEL)
    mkcard.mkcard(template, tree, img, explain=False,
                  label=FIXTURE_IMAGE_LABEL)
    template.unlink()
    hdd = (tree / "VER_INFO" / "HDD_INFO.TXT").read_bytes()
    with img.open("r+b") as handle:
        handle.seek(HDD_COPY_OFFSET)
        handle.write(hdd)
    return img


def generate_fixture_image(img, break_kind: str | None = None) -> Path:
    """Write a vendor-free FAT32 image that ``cardcheck --image`` accepts.

    The tree-level break kinds are applied to the tree before it is written, so
    the image carries the same defect on disk; the FAT kind is applied to the
    built image's directory entry (a tree has no clusters to repoint).
    """
    img = Path(img)
    tree = img.with_name(img.name + ".tree")
    generate_fixture(tree)
    if break_kind not in (None, "fat-cluster-out-of-range"):
        if break_kind not in BREAK_KINDS:
            raise ValueError(f"unknown break kind {break_kind!r}")
        _apply_break(tree, break_kind)
    _build_fixture_image(tree, img)
    if break_kind == "fat-cluster-out-of-range":
        _apply_break(tree, break_kind, img=img)
    return img


def _run_checks(source, report: Report, *, partial: bool = False,
                fast: bool = False, ignore_artifacts: bool = False,
                do_hash: bool = False, expect_sha256: str | None = None,
                strict: bool = False) -> dict:
    """Run the fixed L1 check set against ``source`` and finish the report."""
    check_mbr(source, report)
    check_fat(source, report)
    check_tree(source, report, partial=partial, ignore_artifacts=ignore_artifacts)
    check_headers(source, report, ignore_artifacts=ignore_artifacts)
    check_cmp(source, report, fast=fast, ignore_artifacts=ignore_artifacts)
    check_drstr(source, report, partial=partial, ignore_artifacts=ignore_artifacts)
    check_mmain(source, report, ignore_artifacts=ignore_artifacts)
    check_version(source, report, partial=partial)
    if do_hash:
        check_hash(source, report, expect_sha256)
    return report.finish(strict=strict)


# ---------------------------------------------------------------------------
# CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--image", help="raw SD image")
    source.add_argument("--root", help="extracted card root")
    source.add_argument("--generate-fixture", metavar="DIR",
                        help="write a deterministic no-vendor tree to DIR and "
                             "validate it in the same run (H103)")
    source.add_argument("--generate-fixture-image", metavar="IMG",
                        help="write a deterministic no-vendor FAT32 image to IMG "
                             "(with the HDD_INFO copy at 0x06000000) and validate "
                             "it in the same run (H105)")
    parser.add_argument("--break", dest="break_kind", metavar="KIND",
                        choices=BREAK_KINDS,
                        help="with --generate-fixture/--generate-fixture-image, "
                             "inject one deliberate defect so the matching check "
                             "FAILs (the negative control): "
                             + ", ".join(BREAK_KINDS))
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
    parser.add_argument("--selftest", action="store_true",
                        help="run the synthetic fixture self-test (no vendor data)")
    return parser


def _fixture_sha_list(root: Path) -> dict[str, str]:
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()).hexdigest()
    return out


def _selftest() -> int:
    """H103: the builder is deterministic, accepted, and can fail loudly."""
    import tempfile

    failures = 0

    def ok(cond: bool, msg: str) -> None:
        nonlocal failures
        print(("  ok   " if cond else "  FAIL ") + msg)
        failures += 0 if cond else 1

    print("cardcheck --generate-fixture selftest (synthetic, no vendor data)")
    with tempfile.TemporaryDirectory(prefix="cardcheck-fixture-") as tmp:
        base = Path(tmp)
        tree_a = generate_fixture(base / "a")
        tree_b = generate_fixture(base / "b")

        # Deterministic: a sorted file list with SHA-256 matches across runs.
        ok(_fixture_sha_list(tree_a) == _fixture_sha_list(tree_b),
           "two runs are byte-identical (sorted file list + sha256)")

        def run(root: Path) -> dict:
            source = RootSource(root)
            try:
                report = Report("L1", {"kind": "root", "path": str(root)},
                                fixture="none")
                return _run_checks(source, report)
            finally:
                source.close()

        result = run(tree_a)
        ok(result["ok"], "generated tree passes L1 (exit-0 equivalent)")
        ok(result["fixture"] == "none", "JSON names fixture=none")
        by_id = {c["id"]: c for c in result["checks"]}
        ok(by_id["tree"]["status"] == "PASS", "tree check PASS")
        ok(by_id["headers"]["status"] == "PASS", "headers check PASS")
        ok(by_id["cmp"]["status"] == "PASS", "cmp check PASS")
        ok(by_id["drstr"]["status"] == "PASS", "drstr check PASS")
        ok(by_id["mmain"]["status"] == "PASS", "mmain check PASS")
        ok(by_id["version"]["status"] == "PASS", "version check PASS")
        ok(by_id["mbr"]["status"] == "SKIP" and by_id["mbr"]["skipped"],
           "mbr is SKIP with a reason (image-only), never a fake PASS")
        ok(by_id["fat"]["status"] == "SKIP" and by_id["fat"]["skipped"],
           "fat is SKIP with a reason (image-only), never a fake PASS")
        ok(result["counts"]["fail"] == 0, "no FAIL in the generated tree")

        # Negative control: drop the tile's MAPAL001 entry from DRSTR and the
        # drstr check must fail, so a PASS above is not vacuous.
        broken = base / "broken"
        generate_fixture(broken)
        drstr_path = broken / "DRSTR001.DAT"
        data = bytearray(drstr_path.read_bytes())
        # Flip the first byte of the B48R058R.DAT entry name so DRSTR no longer
        # lists the tile that is on disk.
        idx = data.find("B48R058R.DAT".encode())
        ok(idx >= 0, "fixture DRSTR lists the tile (positive control)")
        if idx >= 0:
            data[idx] = ord("X")
            drstr_path.write_bytes(bytes(data))
            neg = run(broken)
            ok(not neg["ok"], "a DRSTR/tile mismatch makes L1 FAIL")
            names = {c["id"] for c in neg["checks"] if c["status"] == "FAIL"}
            ok("drstr" in names, "the failing check is named drstr")

        # Negative control 2: a tile level not in MMAIN is named mmain.
        broken2 = base / "broken2"
        generate_fixture(broken2)
        mm = bytearray((broken2 / "MMAIN001.DAT").read_bytes())
        # Zero the counted totals: section 1 level 1 row has no matching tile sum.
        totals = _fixture_tile_totals(broken2)
        groups = parse_level_table(bytes(mm), 0x1AC)
        # find a row with a non-zero tile sum and set the MMAIN count to 0xFFFF
        # (a wrong count) so mmain must disagree.
        pos = 0x1AC + 2
        patched = False
        for g in groups:
            pos += 2
            for row in g["rows"]:
                if totals.get((g["section"], row["level"]), [None, 0])[1] > 0:
                    struct.pack_into(">H", mm, pos + 2, 0xBEEF)
                    patched = True
                    break
                pos += 4
            else:
                continue
            break
        ok(patched, "a non-zero MMAIN row exists to break (positive control)")
        (broken2 / "MMAIN001.DAT").write_bytes(bytes(mm))
        neg2 = run(broken2)
        ok(not neg2["ok"], "a wrong MMAIN count makes L1 FAIL")
        ok("mmain" in {c["id"] for c in neg2["checks"] if c["status"] == "FAIL"},
           "the failing check is named mmain")

        # H105: every --break kind is a negative control — rc=1 and the check
        # the good tree passed is among the FAILs. A kind the checker ignores
        # would leave rc=0 here (the exact defect H105 exists to catch).
        def run_image(path: Path) -> dict:
            source = Fat32Image(path)
            try:
                report = Report("L1", {"kind": "image", "path": str(path)},
                                fixture="none")
                return _run_checks(source, report)
            finally:
                source.close()

        for kind in BREAK_KINDS:
            target = BREAK_TARGET[kind]
            if kind in IMAGE_ONLY_BREAKS:
                img = base / f"break-{kind}.img"
                generate_fixture_image(img, break_kind=kind)
                bad = run_image(img)
            else:
                tree = base / f"break-{kind}"
                generate_fixture(tree, break_kind=kind)
                bad = run(tree)
            failed = {c["id"] for c in bad["checks"] if c["status"] == "FAIL"}
            ok(not bad["ok"], f"--break {kind}: L1 FAIL (rc=1)")
            ok(target in failed,
               f"--break {kind}: the failing check includes {target!r}")

        # Positive control for the image path: the unbroken image passes, so
        # the FAT break above is not passing only because images fail anyway.
        image = base / "good.img"
        generate_fixture_image(image)
        good_img = run_image(image)
        ok(good_img["ok"], "unbroken --generate-fixture-image passes all 8 (no SKIP)")
        ok(good_img["counts"]["skip"] == 0,
           "an image has no image-only SKIP: mbr/fat PASS, not SKIP")

    print(f"cardcheck selftest: {'PASS' if failures == 0 else 'FAIL'} "
          f"({failures} failure(s))")
    return 0 if failures == 0 else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return _selftest()
    if not (args.image or args.root or args.generate_fixture
            or args.generate_fixture_image):
        parser = build_parser()
        parser.error("one of the arguments --image --root --generate-fixture "
                     "--generate-fixture-image is required")
    if args.break_kind and not (args.break_kind in IMAGE_ONLY_BREAKS
                                and args.generate_fixture_image):
        if args.break_kind in IMAGE_ONLY_BREAKS:
            build_parser().error(
                f"--break {args.break_kind} needs --generate-fixture-image")
        if not (args.generate_fixture or args.generate_fixture_image):
            build_parser().error("--break needs --generate-fixture or "
                                 "--generate-fixture-image")
    if args.expect_sha256 and not args.hash:
        args.hash = True
    fixture = None
    if args.generate_fixture:
        try:
            generate_fixture(Path(args.generate_fixture), break_kind=args.break_kind)
        except (OSError, ValueError) as exc:
            print(f"error: --generate-fixture: {exc}", file=sys.stderr)
            return 2
        root = str(Path(args.generate_fixture))
        fixture = "none"
        source_info = {"kind": "root", "path": root, "fixture": fixture}
        try:
            source = RootSource(Path(root))
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    elif args.generate_fixture_image:
        try:
            generate_fixture_image(Path(args.generate_fixture_image),
                                   break_kind=args.break_kind)
        except (OSError, ValueError) as exc:
            print(f"error: --generate-fixture-image: {exc}", file=sys.stderr)
            return 2
        image = str(Path(args.generate_fixture_image))
        fixture = "none"
        try:
            source = Fat32Image(Path(image))
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        source_info = {"kind": "image", "path": image, "size": source.size,
                       "fixture": fixture}
    else:
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
        report = Report("L1", source_info, fixture=fixture)
        result = _run_checks(
            source, report,
            partial=args.partial,
            fast=args.fast,
            ignore_artifacts=args.ignore_dump_artifacts,
            do_hash=args.hash,
            expect_sha256=args.expect_sha256,
            strict=args.strict,
        )
    finally:
        source.close()

    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2) + "\n")
    if not args.json_only:
        print(f"L1 whole-card validation: {source_info['path']}")
        if fixture is not None:
            print(f"fixture={fixture} (no vendor bytes)")
        if args.break_kind:
            print(f"break={args.break_kind} (expected to FAIL "
                  f"{BREAK_TARGET[args.break_kind]})")
        for check in result["checks"]:
            status = {"PASS": "OK", "SKIP": "SKIP", "FAIL": "FAIL"}[check["status"]]
            details = []
            if check["stats"]:
                details.append(", ".join(f"{k}={v}" for k, v in check["stats"].items()
                                         if not isinstance(v, (dict, list))))
            print(f"  [{check['id']}] {status}"
                  + (f" ({'; '.join(details)})" if details else ""))
            if check.get("skipped"):
                print(f"    SKIP  {check['skipped']}")
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
