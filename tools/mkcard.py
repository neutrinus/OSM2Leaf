#!/usr/bin/env python3
"""Build a Leaf ZE0 SD card image from a map tree.

Copies firmware/pre-partition regions verbatim from a source image and
rebuilds the FAT32 map partition from a card tree, following the factory
layout (MBR, FAT32 partition 0, 64 KiB clusters, label QSD-309-101, root
order including MMAIN001.DAT in the root directory cluster 2, and the
0x06000000 HDD_INFO copy that cardcheck.py --image checks).

On a fresh build the root volume-label entry (attr 0x08, factory EU
`QSD-309-101`, US `QSD-301-103`; the US BPB label is `NO NAME`) and the
factory root directory order are preserved from the source image. The BPB
label is copied verbatim with the reserved sectors and is independent of
the root label entry. `--label` overrides the root label entry,
`--no-preserve-root-order` falls back to alphabetical root order.

For an unchanged tree the output is byte-identical to the source image (or
every differing byte range is listed and explained). The tool cannot
reproduce the SD lock state or the card CID.

Usage:
    python3 tools/mkcard.py --from-image IMG --tree ROOT -o out.img
    python3 tools/mkcard.py --from-image IMG --tree ROOT -o out.img --label QSD-301-103
    python3 tools/mkcard.py --from-image IMG --tree ROOT --compare-only
    python3 tools/mkcard.py --selftest
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import struct
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

SECTOR = 512
FAT32_TYPES = (0x0B, 0x0C)
HDD_COPY_OFFSET = 0x06000000
COPY_CHUNK = 8 << 20


def _u16(b: bytes, o: int) -> int:
    return struct.unpack_from("<H", b, o)[0]


def _u32(b: bytes, o: int) -> int:
    return struct.unpack_from("<I", b, o)[0]


def _p16(v: int) -> bytes:
    return struct.pack("<H", v & 0xFFFF)


def _p32(v: int) -> bytes:
    return struct.pack("<I", v & 0xFFFFFFFF)


def sha256_file(path: Path) -> str:
    d = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(COPY_CHUNK), b""):
            d.update(b)
    return d.hexdigest()


def mbr_entries(data: bytes) -> list[dict]:
    if len(data) < SECTOR:
        raise ValueError("short MBR")
    out = []
    for i in range(4):
        raw = data[446 + i * 16 : 446 + (i + 1) * 16]
        if not any(raw):
            continue
        ptype = raw[4]
        lba, sectors = struct.unpack_from("<II", raw, 8)
        out.append({"index": i, "type": ptype, "lba": lba, "sectors": sectors,
                    "offset": lba * SECTOR, "bytes": sectors * SECTOR})
    return out


@dataclass
class FatGeo:
    part_offset: int
    part_bytes: int
    bps: int
    spc: int
    cluster_bytes: int
    reserved: int
    fat_count: int
    fat_sectors: int
    total_sectors: int
    root_cluster: int
    label: str
    oem: bytes
    fsinfo_sector: int
    backup_boot: int

    @property
    def fat_offset(self) -> int:
        return self.part_offset + self.reserved * self.bps

    @property
    def data_offset(self) -> int:
        return self.part_offset + (self.reserved + self.fat_count * self.fat_sectors) * self.bps

    @property
    def fat_bytes(self) -> int:
        return self.fat_sectors * self.bps

    def cluster_offset(self, cluster: int) -> int:
        return self.data_offset + (cluster - 2) * self.cluster_bytes


def read_geo(handle, part: dict) -> FatGeo:
    handle.seek(part["offset"])
    bs = handle.read(SECTOR)
    if len(bs) < 90:
        raise ValueError("short boot sector")
    bps = _u16(bs, 11)
    spc = bs[13]
    reserved = _u16(bs, 14)
    fat_count = bs[16]
    total = _u32(bs, 32) or _u16(bs, 19)
    fat_sectors = _u32(bs, 36) or _u16(bs, 22)
    root_cluster = _u32(bs, 44)
    fsinfo = _u16(bs, 48)
    backup = _u16(bs, 50)
    label = bs[71:82].decode("ascii", "replace").strip()
    return FatGeo(part["offset"], part["bytes"], bps, spc, bps * spc, reserved,
                  fat_count, fat_sectors, total, root_cluster, label, bs[3:11],
                  fsinfo, backup)


def read_fat(handle, geo: FatGeo) -> bytearray:
    handle.seek(geo.fat_offset)
    return bytearray(handle.read(geo.fat_bytes))


def fat_get(fat: bytes, cluster: int) -> int:
    return _u32(fat, cluster * 4) & 0x0FFFFFFF


def fat_set(fat: bytearray, cluster: int, value: int) -> None:
    off = cluster * 4
    old = _u32(fat, off)
    struct.pack_into("<I", fat, off, (old & 0xF0000000) | (value & 0x0FFFFFFF))


def chain(fat: bytes, start: int) -> list[int]:
    out = []
    seen = set()
    c = start
    while 2 <= c < 0x0FFFFFF8:
        if c in seen:
            raise ValueError(f"FAT cycle at cluster {c}")
        seen.add(c)
        out.append(c)
        c = fat_get(fat, c)
    return out


def read_cluster(handle, geo: FatGeo, cluster: int) -> bytes:
    handle.seek(geo.cluster_offset(cluster))
    return handle.read(geo.cluster_bytes)


def read_chain(handle, geo: FatGeo, fat: bytes, start: int, size: int | None = None) -> bytes:
    data = b"".join(read_cluster(handle, geo, c) for c in chain(fat, start))
    return data[:size] if size is not None else data


# --- directory parsing, preserving raw slot groups ---

@dataclass
class RawEntry:
    name: str
    short: str
    is_dir: bool
    size: int
    cluster: int
    attr: int
    slot_offset: int       # offset of first slot (LFN or short) within dir blob
    slot_count: int        # number of 32-byte slots
    raw_slots: bytes       # exact bytes of all slots


def _short_name(entry: bytes) -> str:
    base = entry[0:8]
    ext = entry[8:11]
    if base[:1] == b"\x05":
        base = b"\xe5" + base[1:]
    base_s = base.decode("ascii", "replace").rstrip(" \x00")
    ext_s = ext.decode("ascii", "replace").rstrip(" \x00")
    # NT case flags (byte 12): 0x08 = base lower-case, 0x10 = extension
    # lower-case. The factory US image stores XMD/ltntbl.dat this way (flags
    # 0x18, short name LTNTBL.DAT); without the flags the name is upper-case
    # and a tree compare reports a phantom add/remove pair.
    flags = entry[12] if len(entry) > 12 else 0  # make_dir_slots passes 11 bytes
    if flags & 0x08:
        base_s = base_s.lower()
    if flags & 0x10:
        ext_s = ext_s.lower()
    return f"{base_s}.{ext_s}" if ext_s else base_s


def parse_dir_raw(data: bytes) -> list[RawEntry]:
    out = []
    lfn: list[tuple[int, str]] = []
    lfn_start = None
    i = 0
    while i + 32 <= len(data):
        entry = data[i : i + 32]
        if entry[0] == 0x00:
            break
        if entry[0] == 0xE5:
            lfn = []
            lfn_start = None
            i += 32
            continue
        attr = entry[11]
        if attr == 0x0F:
            if lfn_start is None:
                lfn_start = i
            seq = entry[0] & 0x1F
            raw = entry[1:11] + entry[14:26] + entry[28:32]
            text = raw.decode("utf-16le", "replace").split("\x00")[0]
            lfn.append((seq, text))
            i += 32
            continue
        if attr & 0x08:
            # volume label - preserve as a pseudo entry? skip for file listing
            lfn = []
            lfn_start = None
            i += 32
            continue
        short = _short_name(entry)
        if short in (".", ".."):
            lfn = []
            lfn_start = None
            i += 32
            continue
        if lfn:
            seqs = sorted(seq for seq, _ in lfn)
            name = "".join(text for _, text in sorted(lfn)) if seqs == list(range(1, len(seqs) + 1)) else short
        else:
            name = short
        start = lfn_start if lfn_start is not None else i
        slots = data[start : i + 32]
        cluster = (_u16(entry, 20) << 16) | _u16(entry, 26)
        out.append(RawEntry(name, short, bool(attr & 0x10),
                            0 if attr & 0x10 else _u32(entry, 28), cluster, attr,
                            start, (i + 32 - start) // 32, slots))
        lfn = []
        lfn_start = None
        i += 32
    return out


def open_map_partition(handle):
    handle.seek(0)
    mbr = handle.read(SECTOR)
    parts = [p for p in mbr_entries(mbr) if p["type"] in FAT32_TYPES]
    if not parts:
        raise ValueError("no FAT32 partition")
    geo = read_geo(handle, parts[0])
    fat = read_fat(handle, geo)
    return parts[0], geo, fat


def _resolve(handle, geo, fat, rel: str):
    rel = rel.strip("/")
    if not rel:
        return None, geo.root_cluster  # root
    parts = rel.split("/")
    cur_cluster = geo.root_cluster
    entry = None
    for idx, part in enumerate(parts):
        data = read_chain(handle, geo, fat, cur_cluster)
        entries = parse_dir_raw(data)
        match = next((e for e in entries if e.name == part), None)
        if match is None:
            match = next((e for e in entries if e.name.lower() == part.lower()), None)
        if match is None:
            raise FileNotFoundError(rel)
        entry = match
        if idx < len(parts) - 1:
            if not entry.is_dir:
                raise NotADirectoryError(rel)
            cur_cluster = entry.cluster
    return entry, entry.cluster


def img_list_dir(handle, geo, fat, rel: str = "") -> list[RawEntry]:
    if not rel.strip("/"):
        data = read_chain(handle, geo, fat, geo.root_cluster)
    else:
        entry, _ = _resolve(handle, geo, fat, rel)
        if entry is None or not entry.is_dir:
            raise NotADirectoryError(rel)
        data = read_chain(handle, geo, fat, entry.cluster)
    return parse_dir_raw(data)


@dataclass
class RootLayout:
    label_raw: bytes | None   # exact 32-byte attr-0x08 slot, if present
    label_name: str           # decoded label, "" when absent
    order: list[str]          # live root entries in on-disk order


def root_layout(handle, geo: FatGeo, fat: bytes) -> RootLayout:
    """Read the factory root label entry and the live root entry order.

    `parse_dir_raw` deliberately drops attr-0x08 entries and deleted slots, so
    the label slot is read separately and `order` keeps only live file/dir
    entries in the order they appear on disk.
    """
    data = read_chain(handle, geo, fat, geo.root_cluster)
    label_raw = None
    label_name = ""
    for i in range(0, len(data) - 31, 32):
        entry = data[i : i + 32]
        if entry[0] == 0x00:
            break
        if entry[0] == 0xE5:
            continue
        if entry[11] == 0x08 and label_raw is None:
            label_raw = bytes(entry)
            label_name = entry[0:11].decode("ascii", "replace").strip()
    return RootLayout(label_raw, label_name, [e.name for e in parse_dir_raw(data)])


def make_label_entry(name: str) -> bytes:
    """Build a 32-byte volume-label slot (attr 0x08, no cluster/size)."""
    text = name.strip().upper()
    if not text or len(text) > 11:
        raise ValueError(f"volume label must be 1..11 characters: {name!r}")
    try:
        raw = text.encode("ascii").ljust(11, b" ")
    except UnicodeEncodeError as exc:
        raise ValueError(f"volume label must be ASCII: {name!r}") from exc
    return make_short_entry(raw, 0x08, 0, 0)


def img_read(handle, geo, fat, rel: str) -> bytes:
    entry, _ = _resolve(handle, geo, fat, rel)
    if entry is None or entry.is_dir:
        raise IsADirectoryError(rel)
    return read_chain(handle, geo, fat, entry.cluster, entry.size)


def img_walk_files(handle, geo, fat, rel: str = ""):
    for e in img_list_dir(handle, geo, fat, rel):
        path = f"{rel}/{e.name}".strip("/") if rel else e.name
        if e.is_dir:
            yield from img_walk_files(handle, geo, fat, path)
        else:
            yield path, e


def collect_tree(root: Path) -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            out.append(p.relative_to(root).as_posix())
    return out


def compare_tree_to_image(img_path: Path, root: Path) -> list[tuple]:
    diffs = []
    with img_path.open("rb") as h:
        _, geo, fat = open_map_partition(h)
        tree_files = set(collect_tree(root))
        img_files = set()
        for rel, _ in img_walk_files(h, geo, fat):
            img_files.add(rel)
        for rel in sorted(tree_files - img_files):
            diffs.append(("added", rel))
        for rel in sorted(img_files - tree_files):
            diffs.append(("removed", rel))
        for rel in sorted(tree_files & img_files):
            a = (root / rel).read_bytes()
            b = img_read(h, geo, fat, rel)
            if a != b:
                diffs.append(("changed", rel, len(a), len(b)))
    return diffs


def diff_ranges(a_path: Path, b_path: Path, limit: int = 200) -> list[tuple[int, int]]:
    """Return list of (start,end) byte ranges where files differ."""
    ranges = []
    size_a = a_path.stat().st_size
    size_b = b_path.stat().st_size
    common = min(size_a, size_b)
    with a_path.open("rb") as fa, b_path.open("rb") as fb:
        off = 0
        in_diff = False
        start = 0
        while off < common:
            ca = fa.read(COPY_CHUNK)
            cb = fb.read(COPY_CHUNK)
            if ca == cb:
                if in_diff:
                    ranges.append((start, off))
                    in_diff = False
                    if len(ranges) >= limit:
                        return ranges
                off += len(ca)
                continue
            for i, (x, y) in enumerate(zip(ca, cb)):
                if x != y and not in_diff:
                    in_diff = True
                    start = off + i
                elif x == y and in_diff:
                    ranges.append((start, off + i))
                    in_diff = False
                    if len(ranges) >= limit:
                        return ranges
            off += len(ca)
        if in_diff:
            ranges.append((start, common))
    if size_a != size_b and len(ranges) < limit:
        ranges.append((common, max(size_a, size_b)))
    return ranges


def explain_range(img_path: Path, start: int, end: int) -> str:
    """Best-effort explanation of a differing byte range."""
    try:
        with img_path.open("rb") as h:
            _, geo, _ = open_map_partition(h)
    except Exception:
        return "unknown"
    notes = []
    if start <= HDD_COPY_OFFSET < end or start < HDD_COPY_OFFSET + 72 <= end or (HDD_COPY_OFFSET <= start < HDD_COPY_OFFSET + 72):
        notes.append("HDD_INFO copy at 0x06000000")
    # FAT areas
    for copy in range(geo.fat_count):
        f0 = geo.fat_offset + copy * geo.fat_bytes
        f1 = f0 + geo.fat_bytes
        if not (end <= f0 or start >= f1):
            notes.append(f"FAT copy {copy}")
    # BPB / reserved
    r0 = geo.part_offset
    r1 = geo.part_offset + geo.reserved * geo.bps
    if not (end <= r0 or start >= r1):
        notes.append("reserved/BPB/FSInfo/boot backup area")
    d0 = geo.data_offset
    d1 = geo.part_offset + geo.part_bytes
    if not (end <= d0 or start >= d1) and not notes:
        # map to cluster
        if start >= d0:
            cl = (start - d0) // geo.cluster_bytes + 2
            notes.append(f"data area (cluster ~{cl})")
        else:
            notes.append("data area boundary")
    if start < geo.part_offset:
        notes.append("pre-partition/firmware region")
    return "; ".join(notes) if notes else "unknown (possibly timestamps or allocation metadata)"

# --- FAT32 writer helpers (for fresh build / reconcile) ---

def _fat_time(dt_tuple=None):
    """Return (dos_time, dos_date). If None, use fixed epoch-like values."""
    # fixed timestamp for reproducibility in fresh builds? Or zero.
    # Factory images have real timestamps; we can't reproduce them without source.
    return 0, 0x0021  # 1980-01-01


def lfn_checksum(short11: bytes) -> int:
    s = 0
    for b in short11:
        s = (((s & 1) << 7) + (s >> 1) + b) & 0xFF
    return s


def make_short_name(name: str, existing: set[str]) -> tuple[bytes, bytes]:
    base, dot, ext = name.rpartition(".")
    if not dot:
        base, ext = name, ""
    def clean(s):
        out = []
        for c in s.upper():
            if c in ' ."+,;=[]' :
                out.append('_')
            elif ord(c) < 128:
                out.append(c)
            else:
                out.append('_')
        return "".join(out)
    b = clean(base)[:8] or "_"
    e = clean(ext)[:3]
    candidate = (b.ljust(8) + e.ljust(3)).encode("ascii", "replace")
    # avoid collisions
    for n in range(1, 10000):
        key = _short_name(candidate + b"\x20" * 21)  # hack not right; use bytes
        sn = _short_name(candidate)
        if sn.upper() not in existing:
            existing.add(sn.upper())
            return candidate[:8], candidate[8:11]
        tail = f"~{n}"
        b2 = (clean(base)[: 8 - len(tail)] + tail)[:8]
        candidate = (b2.ljust(8) + e.ljust(3)).encode("ascii", "replace")
    raise ValueError(f"cannot make short name for {name!r}")


def make_dir_slots(name: str, short11: bytes, attr: int, cluster: int, size: int,
                   dos_time: int = 0, dos_date: int = 0x0021) -> bytes:
    need_lfn = False
    # check if name fits 8.3 upper ASCII
    sn = _short_name(short11)
    if name != sn and name.upper() != sn.upper():
        need_lfn = True
    if not need_lfn:
        return make_short_entry(short11, attr, cluster, size, dos_time, dos_date)
    # LFN slots: parts[0] is the first 13 UTF-16 chars of the name (seq 1),
    # stored last physically; parts[-1] is last and stored first with 0x40.
    u = name.encode("utf-16le")
    parts = [u[i:i+26] for i in range(0, len(u) + 2, 26)]
    # pad last with 0x0000 terminator then 0xffff
    if parts and len(parts[-1]) < 26:
        parts[-1] = parts[-1] + b"\x00\x00"
    while len(parts[-1]) < 26:
        parts[-1] += b"\xff\xff"
    parts = [p[:26].ljust(26, b"\xff") for p in parts]
    csum = lfn_checksum(short11)
    slots = bytearray()
    total = len(parts)
    for seq in range(total, 0, -1):
        part = parts[seq - 1]
        seqb = seq | (0x40 if seq == total else 0)
        e = bytearray(32)
        e[0] = seqb
        e[1:11] = part[0:10]
        e[11] = 0x0F
        e[12] = 0
        e[13] = csum
        e[14:26] = part[10:22]
        struct.pack_into("<H", e, 26, 0)
        e[28:32] = part[22:26]
        slots.extend(e)
    slots.extend(make_short_entry(short11, attr, cluster, size, dos_time, dos_date))
    return bytes(slots)


def make_short_entry(short11: bytes, attr: int, cluster: int, size: int,
                     dos_time: int = 0, dos_date: int = 0x0021) -> bytes:
    e = bytearray(32)
    e[0:11] = short11
    e[11] = attr
    struct.pack_into("<H", e, 14, 0)  # ctime
    struct.pack_into("<H", e, 16, dos_date)
    struct.pack_into("<H", e, 18, 0)
    struct.pack_into("<H", e, 20, (cluster >> 16) & 0xFFFF)
    struct.pack_into("<H", e, 22, dos_time)
    struct.pack_into("<H", e, 24, dos_date)
    struct.pack_into("<H", e, 26, cluster & 0xFFFF)
    struct.pack_into("<I", e, 28, 0 if (attr & 0x10) else size)
    return bytes(e)


def clusters_needed(size: int, cluster_bytes: int) -> int:
    if size <= 0:
        return 0
    return (size + cluster_bytes - 1) // cluster_bytes


def alloc_clusters(fat: bytearray, count: int, start_hint: int = 2) -> list[int]:
    if count <= 0:
        return []
    total = len(fat) // 4
    out = []
    c = max(2, start_hint)
    scanned = 0
    while len(out) < count and scanned < total:
        if c >= total:
            c = 2
        if fat_get(fat, c) == 0:
            out.append(c)
        c += 1
        scanned += 1
    if len(out) < count:
        raise ValueError(f"no space: need {count} clusters, got {len(out)}")
    for i, cl in enumerate(out):
        fat_set(fat, cl, out[i + 1] if i + 1 < len(out) else 0x0FFFFFF8)
    return out


def write_chain(handle, geo: FatGeo, clusters: list[int], data: bytes) -> None:
    cb = geo.cluster_bytes
    padded = data + b"\x00" * ((len(clusters) * cb - len(data)) % cb) if clusters else b""
    for i, cl in enumerate(clusters):
        handle.seek(geo.cluster_offset(cl))
        handle.write(padded[i * cb : (i + 1) * cb])


def build_fresh_partition(handle, geo: FatGeo, src_handle, src_geo: FatGeo,
                          tree: Path, label: str | None = None,
                          preserve_root_order: bool = True) -> dict:
    """Build a fresh FAT32 filesystem in the map partition from tree.

    Copies BPB/reserved layout and FSInfo/backup boot from source; resets FAT
    and data. The factory root volume-label entry (attr 0x08) is written as
    root slot 0 and the source root entry order is kept for names that also
    exist in the tree. Returns a report of what was preserved.

    This still produces a valid card but NOT byte-identical timestamps/LFN
    quirks/allocation to factory images.
    """
    # copy reserved sectors (BPB + FSInfo + backup boot) from source
    src_handle.seek(src_geo.part_offset)
    reserved = src_handle.read(src_geo.reserved * src_geo.bps)
    handle.seek(geo.part_offset)
    handle.write(reserved)
    # factory root label + order from the source image
    src_root = root_layout(src_handle, src_geo, read_fat(src_handle, src_geo))
    source_label = src_root.label_name
    requested = label.strip().upper() if label is not None else None
    if requested is not None:
        if src_root.label_raw is not None and source_label == requested:
            label_raw = src_root.label_raw
            label_action = "preserved"
        else:
            label_raw = make_label_entry(requested)
            label_action = "overridden" if source_label else "created"
    else:
        label_raw = src_root.label_raw
        label_action = "preserved" if label_raw is not None else "absent"
    label_mismatch = (requested is not None and source_label not in ("", requested))
    # fresh FATs
    fat = bytearray(geo.fat_bytes)
    # cluster 0,1 media/eoc
    struct.pack_into("<I", fat, 0, 0x0FFFFFF8)
    struct.pack_into("<I", fat, 4, 0x0FFFFFFF)
    # root dir cluster
    fat_set(fat, geo.root_cluster, 0x0FFFFFF8)
    # write files recursively
    hint = [geo.root_cluster + 1]

    def ensure_dir_chain(size_bytes: int) -> list[int]:
        need = max(1, clusters_needed(size_bytes, geo.cluster_bytes))
        return alloc_clusters(fat, need, hint[0])

    # We'll build directory contents bottom-up isn't necessary; do recursively.
    dir_cluster_map = {"": geo.root_cluster}
    root_names = set(os.listdir(tree))

    def populate_dir(rel: str, parent_cluster: int):
        dir_path = tree / rel if rel else tree
        entries = []
        names = sorted(os.listdir(dir_path))
        # build dir slots
        existing_shorts: set[str] = set()
        slots = bytearray()
        # . and ..
        if rel:
            # find parent
            slots.extend(make_short_entry(b".          ", 0x10, dir_cluster_map[rel], 0))
            slots.extend(make_short_entry(b"..         ", 0x10, parent_cluster, 0))
        subdirs = []
        files = []
        for name in names:
            p = dir_path / name
            if p.is_dir():
                subdirs.append(name)
            else:
                files.append(name)
        # Factory root slot 0 is the attr-0x08 volume label, then the live
        # entries in the source order. Subdirectories stay alphabetical.
        ordered = list(names)
        if not rel:
            if label_raw is not None:
                slots.extend(label_raw)
            if preserve_root_order and src_root.order:
                wanted = [n for n in src_root.order if n in names]
                ordered = wanted + sorted(n for n in names if n not in wanted)
            else:
                ordered = sorted(names)
        for name in ordered:
            p = dir_path / name
            base11 = (name.upper().replace('.', '')[:8].ljust(8) + (name.upper().split('.')[-1][:3].ljust(3) if '.' in name else '   ')).encode('ascii','replace')
            # better short name
            short = bytearray(11)
            existing_shorts  # unused here; simplified
            if p.is_dir():
                bname = name.upper()[:8].encode('ascii','replace').ljust(8)
                s11 = bname + b'   '
                # allocate dir cluster
                dcl = alloc_clusters(fat, 1, hint[0])[0]
                hint[0] = dcl + 1
                dir_cluster_map[f"{rel}/{name}".strip("/")] = dcl
                slots.extend(make_dir_slots(name, s11, 0x10, dcl, 0))
            else:
                data = p.read_bytes()
                sz = len(data)
                base, dot, ext = name.partition('.')
                if not dot:
                    base, ext = name, ''
                s11 = base.upper()[:8].encode('ascii','replace').ljust(8) + ext.upper()[:3].encode('ascii','replace').ljust(3)
                cls = alloc_clusters(fat, clusters_needed(sz, geo.cluster_bytes), hint[0]) if sz else []
                if cls:
                    hint[0] = cls[-1] + 1
                    write_chain(handle, geo, cls, data)
                slots.extend(make_dir_slots(name, s11, 0x20, cls[0] if cls else 0, sz))
        # write dir data
        dir_data = bytes(slots)
        # ensure directory has enough clusters
        need = max(1, clusters_needed(len(dir_data) + 32, geo.cluster_bytes))
        # for root, cluster is fixed
        my_rel = rel
        start = dir_cluster_map[my_rel]
        existing = chain(fat, start)
        if len(existing) < need:
            extra = alloc_clusters(fat, need - len(existing), hint[0])
            fat_set(fat, existing[-1], extra[0])
            for i, cl in enumerate(extra):
                fat_set(fat, cl, extra[i+1] if i+1 < len(extra) else 0x0FFFFFF8)
            existing.extend(extra)
        elif len(existing) > need:
            for cl in existing[need:]:
                fat_set(fat, cl, 0)
            fat_set(fat, existing[need-1], 0x0FFFFFF8)
            existing = existing[:need]
        if rel == "" and existing[0] != geo.root_cluster:
            # shouldn't happen
            pass
        write_chain(handle, geo, existing, dir_data)
        # recurse into subdirs
        for name in sorted(names):
            p = dir_path / name
            if p.is_dir():
                child_rel = f"{rel}/{name}".strip("/")
                populate_dir(child_rel, dir_cluster_map[rel])

    populate_dir("", 0)
    # write FATs
    for copy in range(geo.fat_count):
        handle.seek(geo.fat_offset + copy * geo.fat_bytes)
        handle.write(fat)
    # update FSInfo if present
    if geo.fsinfo_sector:
        try:
            handle.seek(geo.part_offset + geo.fsinfo_sector * geo.bps)
            fs = bytearray(handle.read(geo.bps))
            if fs[0:4] == b"RRaA":
                free = sum(1 for c in range(2, len(fat)//4) if fat_get(fat, c) == 0)
                struct.pack_into("<I", fs, 0x1E8, 0x61417272)
                struct.pack_into("<I", fs, 0x1E8+4, free)
                struct.pack_into("<I", fs, 0x1E8+8, hint[0])
                handle.seek(geo.part_offset + geo.fsinfo_sector * geo.bps)
                handle.write(fs)
        except Exception:
            pass

    # report what the written root actually contains
    actual = root_layout(handle, geo, bytes(fat))
    src_index = {n: i for i, n in enumerate(src_root.order)}
    matched = [n for n in actual.order if n in src_index]
    in_order = all(src_index[matched[i]] < src_index[matched[i + 1]]
                   for i in range(len(matched) - 1))
    return {
        "label": label_raw[0:11].decode("ascii", "replace").strip() if label_raw else None,
        "label_action": label_action,
        "label_mismatch": label_mismatch,
        "source_label": source_label or None,
        "requested_label": requested,
        "bpb_label": src_geo.label or "NO NAME",
        "root_order_mode": "source" if preserve_root_order else "alpha",
        "root_order": actual.order,
        "root_order_source": src_root.order,
        "root_order_total": len(src_root.order),
        "root_order_preserved": len(matched),
        "root_order_in_source_order": in_order,
        "root_order_appended": [n for n in actual.order if n not in src_index],
        "root_order_removed": [n for n in src_root.order if n not in root_names],
    }


def format_root_report(rep: dict | None) -> str:
    """One-line summary of the preserved root label and order."""
    if not rep:
        return "root: not rebuilt (unchanged tree)"
    if rep["label"]:
        line = (f"root: label '{rep['label']}' (attr 0x08) {rep['label_action']} "
                f"at slot 0 (BPB label '{rep['bpb_label']}' unchanged)")
    else:
        line = "root: no root volume-label entry (source had none)"
    if rep["label_mismatch"]:
        line += (f"; LABEL MISMATCH: source '{rep['source_label']}' vs "
                 f"requested '{rep['requested_label']}'")
    if rep["root_order_mode"] == "source":
        line += (f"; order preserved for {rep['root_order_preserved']}"
                 f"/{rep['root_order_total']} source entries")
        if not rep["root_order_in_source_order"]:
            line += " (ORDER MISMATCH)"
        if rep["root_order_appended"]:
            line += f"; appended: {', '.join(rep['root_order_appended'])}"
        if rep["root_order_removed"]:
            line += f"; not in tree: {', '.join(rep['root_order_removed'])}"
    else:
        line += (f"; order NOT preserved (--no-preserve-root-order): "
                 f"{', '.join(rep['root_order'][:20])}")
    return line

def outside_ranges(ranges, allowed) -> list[tuple[int, int]]:
    """Parts of each (start, end) range that no allowed (start, end) covers."""
    merged: list[list[int]] = []
    for s, e in sorted(allowed):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    out = []
    for s, e in ranges:
        cur = s
        for ms, me in merged:
            if cur >= e:
                break
            if ms <= cur < me:
                cur = min(me, e)
        if cur < e:
            out.append((cur, e))
    return out


def reconcile_partition(out: Path, tree: Path, changed: list[str]) -> dict:
    """Write each changed file into the copy ``out`` through the imgpatch chain writer.

    ``out`` must already be a byte copy of the factory image. Each file keeps
    its factory cluster chain (grown or shrunk only as its size needs), and the
    only bytes that may differ are the file's clusters, its 32-byte directory
    entry, the FAT entries of clusters it gains or loses, and FSInfo on a
    cluster-count change. The returned ``allowed`` list is built from the
    chain report, not from the writes, so the caller can check the diff against
    it independently.
    """
    import imgpatch  # local: imgpatch imports mkcard at module level

    with out.open("rb") as h:
        _, geo, _ = open_map_partition(h)
    allowed: list[tuple[int, int]] = []
    patches = []
    for rel in changed:
        rep = imgpatch.patch_image(out, rel, tree / rel, None, allow_resize=True)
        patches.append({
            "file": rel,
            "ok": rep["ok"],
            "old_size": rep["old_size"],
            "new_size": rep["new_size"],
            "clusters_before": rep["clusters_before"],
            "clusters_after": rep["clusters_after"],
            "verify": rep["verify"],
        })
        _add_envelope(allowed, geo, rep)
    drstr = _reconcile_drstr(out, geo, allowed)
    if drstr["patch"] is not None:
        patches.append({
            "file": "DRSTR001.DAT",
            "ok": drstr["patch"]["ok"],
            "old_size": drstr["patch"]["old_size"],
            "new_size": drstr["patch"]["new_size"],
            "clusters_before": drstr["patch"]["clusters_before"],
            "clusters_after": drstr["patch"]["clusters_after"],
            "verify": drstr["patch"]["verify"],
            "reason": f"{drstr['updated']} directory-total value(s) changed",
        })
    return {"patches": patches, "allowed": allowed, "drstr": drstr,
            "ok": all(p["ok"] for p in patches)}


def _add_envelope(allowed: list, geo: FatGeo, rep: dict) -> None:
    """Add the bytes an imgpatch report may touch, from its chain report only."""
    for c in set(rep["chain_before"]) | set(rep["chain_after"]):
        start = geo.cluster_offset(c)
        allowed.append((start, start + geo.cluster_bytes))
    dir_off = rep["dir_entry"]["offset"]
    allowed.append((dir_off, dir_off + 32))
    for fc in rep["fat_changes"]:
        for copy in range(geo.fat_count):
            off = geo.fat_offset + copy * geo.fat_bytes + fc["cluster"] * 4
            allowed.append((off, off + 4))
    for item in rep["fsinfo"]:
        for w in item["writes"]:
            allowed.append((w["offset"], w["offset"] + w["length"]))


def _reconcile_drstr(out: Path, geo: FatGeo, allowed: list) -> dict:
    """Bring DRSTR001.DAT's file and directory values in line with the card.

    cardcheck requires each DRSTR entry value to equal the logical size (file)
    or the recursive total (directory). A resize therefore changes the value of
    the file's own entry and of every ancestor directory's entry. Only those
    4-byte values change; the DRSTR file is rewritten through the chain writer
    at its unchanged length, and its clusters join the allowed envelope.
    """
    import cardcheck  # local: cardcheck is a sibling tool, imported on demand
    import drstr as drstr_mod
    import imgpatch

    img = cardcheck.Fat32Image(out)
    try:
        logical, _dirs = cardcheck.logical_tree(img)
        try:
            data = bytearray(img.read("DRSTR001.DAT"))
        except FileNotFoundError:
            return {"updated": 0, "entries": [], "patch": None, "absent": True}
    finally:
        img.close()
    tree = drstr_mod.parse(bytes(data))
    paths: dict[int, str] = {}
    updates: list[dict] = []
    for i, node in enumerate(tree["nodes"]):
        if i == 0:
            path = ""
        else:
            parent = node["parent"]
            if parent is None or parent not in paths:
                continue
            path = f"{paths[parent]}/{node['name']}".strip("/")
        paths[i] = path
        listing = logical.get(path)
        if listing is None:
            continue
        for j, entry in enumerate(node["entries"]):
            actual = listing.get(entry["name"])
            if actual is None:
                # cardcheck matches DRSTR names case-insensitively (the factory
                # keeps XMD/ltntbl.dat lower-case in DRSTR, see _short_name)
                same = [v for k, v in listing.items()
                        if k.lower() == entry["name"].lower()]
                if not same and len(entry["name"]) == 13:
                    # DRSTR names are 13-byte fields: a long FAT name is cut
                    same = [v for k, v in listing.items()
                            if k.lower().startswith(entry["name"].lower())]
                actual = same[0] if len(same) == 1 else None
            if actual is None or entry["value"] == actual.size:
                continue
            off = node["listing_offset"] + j * 32 + 0x1C
            struct.pack_into("<I", data, off, actual.size)
            updates.append({"path": path, "name": entry["name"],
                            "before": entry["value"], "after": actual.size,
                            "offset": off})
    if not updates:
        return {"updated": 0, "entries": [], "patch": None}
    with tempfile.TemporaryDirectory() as td:
        host = Path(td) / "DRSTR001.DAT"
        host.write_bytes(bytes(data))
        rep = imgpatch.patch_image(out, "DRSTR001.DAT", host, None, allow_resize=False)
    _add_envelope(allowed, geo, rep)
    return {"updated": len(updates), "entries": updates, "patch": rep}


# --- high-level operations ---

def copy_image(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open("rb") as fi, dst.open("wb") as fo:
        fo.truncate(0)
        while True:
            pos = fi.tell()
            buf = fi.read(COPY_CHUNK)
            if not buf:
                break
            if buf == b"\x00" * len(buf):
                pass  # leave hole
            else:
                fo.seek(pos)
                fo.write(buf)
        fo.truncate(src.stat().st_size)


def mkcard(from_image: Path, tree: Path, out: Path, compare_only: bool = False,
           explain: bool = True, verbose: bool = False,
           label: str | None = None,
           preserve_root_order: bool = True,
           reconcile: bool = False) -> dict:
    """Build a card from ``tree`` on top of the factory image ``from_image``.

    Unchanged tree: byte copy. Changed tree: a fresh rebuild of the map
    partition (default), or with ``reconcile`` the factory layout is kept and
    only the changed files are rewritten (see ``reconcile_partition``). A tree
    with added or removed files cannot be reconciled and falls back to the
    fresh build, with the reason in ``result["reconcile"]``.
    """
    if reconcile and label is not None:
        raise ValueError("--label is not supported with --reconcile "
                         "(reconcile keeps the factory root entry)")
    result = {"ok": False, "identical": False, "diffs": [], "ranges": [],
              "cannot_reproduce": ["SD lock state", "SD card CID"]}
    tree_diffs = compare_tree_to_image(from_image, tree)
    result["tree_diffs"] = tree_diffs
    if verbose:
        print(f"tree vs image: {len(tree_diffs)} difference(s)")
        for d in tree_diffs[:20]:
            print(" ", d)

    if compare_only:
        result["ok"] = len(tree_diffs) == 0
        result["identical"] = result["ok"]
        return result

    # Copy entire source image (firmware/pre-partition, 0x06000000, map partition)
    copy_image(from_image, out)
    src_hash = None

    if not tree_diffs:
        # unchanged tree: output is byte-identical by construction
        result["identical"] = True
        result["ok"] = True
        if explain:
            # verify
            src_hash = sha256_file(from_image)
            out_hash = sha256_file(out)
            if src_hash != out_hash:
                result["identical"] = False
                result["ok"] = False
                result["ranges"] = diff_ranges(from_image, out)
                for s, e in result["ranges"][:50]:
                    result["diffs"].append({"range": [s, e], "bytes": e - s,
                                            "explain": explain_range(from_image, s, e)})
        return result

    if reconcile:
        structural = [d for d in tree_diffs if d[0] in ("added", "removed")]
        if not structural:
            changed = [d[1] for d in tree_diffs if d[0] == "changed"]
            rec = reconcile_partition(out, tree, changed)
            ranges = diff_ranges(from_image, out, limit=1 << 30)
            outside = outside_ranges(ranges, rec["allowed"])
            rec["ranges"] = len(ranges)
            rec["outside"] = [list(r) for r in outside[:50]]
            rec["outside_count"] = len(outside)
            rec["fallback"] = None
            result["reconcile"] = rec
            result["ranges_raw"] = ranges
            result["ranges"] = [{"range": [s, e], "bytes": e - s,
                                 "explain": "inside factory-chain envelope"}
                                for s, e in ranges[:200]
                                if not outside_ranges([(s, e)], rec["allowed"])]
            result["ranges"] += [{"range": [s, e], "bytes": e - s,
                                  "explain": "OUTSIDE envelope"}
                                 for s, e in outside[:50]]
            result["identical"] = False
            result["ok"] = rec["ok"] and not outside
            return result
        result["reconcile"] = {"fallback": "structural", "structural": structural}

    # Changed tree: rebuild map partition
    with out.open("r+b") as h, from_image.open("rb") as sh:
        _, geo, _ = open_map_partition(h)
        _, sgeo, _ = open_map_partition(sh)
        # zero the map partition data+FAT area for a clean rebuild? That would
        # destroy layout but be valid. Safer: rebuild in place.
        result["root_report"] = build_fresh_partition(
            h, geo, sh, sgeo, tree, label=label,
            preserve_root_order=preserve_root_order)

    # report diffs vs source
    result["ranges_raw"] = diff_ranges(from_image, out)
    for s, e in result["ranges_raw"][:200]:
        result["ranges"].append({"range": [s, e], "bytes": e - s,
                                 "explain": explain_range(from_image, s, e)})
    result["identical"] = len(result["ranges_raw"]) == 0
    result["ok"] = True  # built; cardcheck will validate
    return result


def run_cardcheck_image(path: Path) -> tuple[bool, str]:
    try:
        import cardcheck
        src = cardcheck.Fat32Image(path)
        try:
            report = cardcheck.Report("L1", {"kind": "image", "path": str(path)})
            cardcheck.check_mbr(src, report)
            cardcheck.check_fat(src, report)
            cardcheck.check_tree(src, report)
            cardcheck.check_headers(src, report)
            cardcheck.check_cmp(src, report)
            cardcheck.check_drstr(src, report)
            cardcheck.check_mmain(src, report)
            cardcheck.check_version(src, report)
            res = report.finish()
            lines = [f"cardcheck: {'PASS' if res['ok'] else 'FAIL'}"]
            for c in res["checks"]:
                if c["errors"]:
                    lines.append(f"  [{c['id']}] FAIL: {c['errors'][0]}")
            return res["ok"], "\n".join(lines)
        finally:
            src.close()
    except Exception as e:
        return False, f"cardcheck error: {e}"


# --- self-test ---

def _write_le32(b, o, v): struct.pack_into("<I", b, o, v & 0xFFFFFFFF)
def _write_le16(b, o, v): struct.pack_into("<H", b, o, v & 0xFFFF)


SYNTH_HDD = b"QSD-302-100\r\nQSD-309-101\r\n02-110100-00\r\nSDC08-EVEUR\r\n11-05\r\n470323501005"

SYNTH_HDD = b"QSD-302-100\r\nQSD-309-101\r\n02-110100-00\r\nSDC08-EVEUR\r\n11-05\r\n470323501005"

def make_synthetic_image(path: Path, files: dict[str, bytes], *,
                         part_lba: int | None = None, total_sectors: int | None = None,
                         spc: int = 1, bps: int = 512, label: str = "TESTCARD   ") -> Path:
    """Create a tiny FAT32 image with an MBR and one partition.
    Partition is placed after HDD_COPY_OFFSET so 0x06000000 is in the image."""
    if part_lba is None:
        part_lba = (HDD_COPY_OFFSET // bps) + 256
    if total_sectors is None:
        total_sectors = part_lba + 131072
    part_off = part_lba * bps
    part_sectors = total_sectors - part_lba
    cluster_bytes = bps * spc
    reserved = 32
    fats = 2
    clusters_approx = (part_sectors - reserved) // spc
    fat_sectors = max(1, (clusters_approx * 4 + bps - 1) // bps)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.truncate(total_sectors * bps)
        mbr = bytearray(bps)
        pe = bytearray(16)
        pe[4] = 0x0C
        _write_le32(pe, 8, part_lba)
        _write_le32(pe, 12, part_sectors)
        mbr[446:462] = pe
        mbr[510:512] = b"\x55\xaa"
        f.seek(0); f.write(mbr)
        f.seek(HDD_COPY_OFFSET); f.write(SYNTH_HDD)
        bs = bytearray(bps)
        bs[0:3] = b"\xeb\x58\x90"
        bs[3:11] = b"MSDOS5.0"
        _write_le16(bs, 11, bps); bs[13] = spc
        _write_le16(bs, 14, reserved); bs[16] = fats
        _write_le32(bs, 32, part_sectors); _write_le32(bs, 36, fat_sectors)
        _write_le32(bs, 44, 2); _write_le16(bs, 48, 1); _write_le16(bs, 50, 6)
        bs[66] = 0x29
        bs[71:82] = label[:11].ljust(11).encode("ascii")
        bs[82:90] = b"FAT32   "; bs[510:512] = b"\x55\xaa"
        f.seek(part_off); f.write(bs)
        fsi = bytearray(bps)
        fsi[0:4] = b"RRaA"; fsi[0x1e4:0x1e8] = b"rrAa"
        _write_le32(fsi, 0x1e8, 0xFFFFFFFF); _write_le32(fsi, 0x1ec, 3)
        fsi[510:512] = b"\x55\xaa"
        f.seek(part_off + bps); f.write(fsi)
        f.seek(part_off + 6*bps); f.write(bs)
        fat_off = part_off + reserved * bps
        fat = bytearray(fat_sectors * bps)
        _write_le32(fat, 0, 0x0FFFFFF8); _write_le32(fat, 4, 0x0FFFFFFF)
        _write_le32(fat, 8, 0x0FFFFFF8)
        data_off = fat_off + fats * fat_sectors * bps
        next_cl = 3
        root_slots = bytearray()
        vl = bytearray(32); vl[0:11] = label[:11].ljust(11).encode("ascii"); vl[11] = 0x08
        root_slots.extend(vl)
        for name, data in files.items():
            bname, ext = (name.upper().split('.') + [''])[:2]
            s11 = bname[:8].ljust(8).encode('ascii') + ext[:3].ljust(3).encode('ascii')
            sz = len(data)
            need = max(1, (sz + cluster_bytes - 1) // cluster_bytes) if sz else 0
            start = 0
            if need:
                start = next_cl
                for i in range(need):
                    cl = next_cl + i
                    _write_le32(fat, cl*4, cl+1 if i+1 < need else 0x0FFFFFF8)
                    dst = data_off + (cl - 2) * cluster_bytes
                    chunk = data[i*cluster_bytes:(i+1)*cluster_bytes]
                    f.seek(dst); f.write(chunk)
                next_cl += need
            root_slots.extend(make_short_entry(s11, 0x20, start, sz, 0, 0x0021))
        f.seek(data_off); f.write(root_slots)
        for c in range(fats):
            f.seek(fat_off + c*fat_sectors*bps); f.write(fat)
    return path


def _synth_drstr(sizes: dict[str, int]) -> bytes:
    """A one-node DRSTR001.DAT: root '/' listing the given root files (drstr.py layout)."""
    names = sorted(sizes)
    node = bytearray(40)
    node[0:1] = b"/"
    struct.pack_into("<H", node, 0x14, 1)                 # next_index
    struct.pack_into("<H", node, 0x16, 1)                 # parent+1 (root -> itself)
    struct.pack_into("<I", node, 0x18, len(names))        # entry_count
    struct.pack_into("<I", node, 0x24, 40)                # listing_offset
    listing = bytearray()
    for n in names:
        e = bytearray(32)
        e[0:len(n)] = n.encode("ascii")
        struct.pack_into("<I", e, 0x1C, sizes[n])
        listing += e
    return bytes(node + listing)


def _selftest_reconcile() -> int:
    """--reconcile on a synthetic factory image (positive and negative controls)."""
    print("mkcard reconcile self-test")
    errors = 0

    def check(ok: bool, msg: str) -> int:
        print(f"  {'ok' if ok else 'FAIL'}: {msg}")
        return 0 if ok else 1

    # NT case flags: the factory XMD/ltntbl.dat entry is LTNTBL  DAT with byte 12 = 0x18
    nt = b"LTNTBL  DAT" + bytes([0x20, 0x18]) + bytes(20)
    errors += check(_short_name(nt) == "ltntbl.dat" and _short_name(b"BSAIDX~1DAT" + bytes(21)) == "BSAIDX~1.DAT",
                    "short name honours NT case flags (ltntbl.dat), upper-case without them")

    base = {"A.TXT": bytes(range(256)) * 4,     # 1024 B = 2 clusters
            "B.TXT": b"b" * 700,                # 2 clusters
            "C.TXT": b"c" * 300}                # 1 cluster
    # DRSTR spells B.TXT in lower case, as the factory does for ltntbl.dat
    sizes = {("b.txt" if k == "B.TXT" else k): len(v) for k, v in base.items()}
    sizes["DRSTR001.DAT"] = 40 + 4 * 32         # root node + 4 entries
    base["DRSTR001.DAT"] = _synth_drstr(sizes)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        img = make_synthetic_image(td / "src.img", base)
        with img.open("rb") as h:
            _, geo, fat = open_map_partition(h)
            before_chain = {rel: chain(fat, e.cluster) for rel, e in img_walk_files(h, geo, fat)}

        def tree_with(changes: dict, *, extra: dict | None = None) -> Path:
            t = td / f"tree{len(list(td.iterdir()))}"
            t.mkdir()
            files = {**base, **changes}
            for k, v in files.items():
                if v is not None:
                    (t / k).write_bytes(v)
            for k, v in (extra or {}).items():
                (t / k).write_bytes(v)
            return t

        # R1: unchanged tree stays byte-identical under --reconcile
        t0 = tree_with({})
        o0 = td / "r0.img"
        r0 = mkcard(img, t0, o0, reconcile=True)
        errors += check(r0["identical"] and sha256_file(o0) == sha256_file(img),
                        "reconcile: unchanged tree is byte-identical")

        # R2: same-length change in A.TXT -> only its clusters and dir entry differ
        new_a = bytes(reversed(base["A.TXT"]))
        t1 = tree_with({"A.TXT": new_a})
        o1 = td / "r1.img"
        r1 = mkcard(img, t1, o1, reconcile=True)
        rec1 = r1.get("reconcile", {})
        errors += check(r1["ok"] and not rec1.get("outside_count", 1)
                        and rec1.get("ranges", 0) > 0 and not rec1.get("fallback"),
                        f"reconcile: same-length change, diff inside envelope "
                        f"({rec1.get('ranges')} range(s), outside {rec1.get('outside_count')})")
        with o1.open("rb") as h:
            _, g1, f1 = open_map_partition(h)
            got_a = img_read(h, g1, f1, "A.TXT")
            chains_now = {rel: chain(f1, e.cluster) for rel, e in img_walk_files(h, g1, f1)}
        errors += check(got_a == new_a, "reconcile: A.TXT reads back the new bytes")
        errors += check(chains_now == before_chain,
                        "reconcile: every file keeps its factory cluster chain")

        # R3: resize B.TXT up, C.TXT down -> FAT links and dir sizes change, still inside envelope
        t2 = tree_with({"B.TXT": b"B" * 1300, "C.TXT": b"C" * 100})
        o2 = td / "r2.img"
        r2 = mkcard(img, t2, o2, reconcile=True)
        rec2 = r2.get("reconcile", {})
        errors += check(r2["ok"] and rec2.get("outside_count", 1) == 0,
                        f"reconcile: grow and shrink stay inside envelope "
                        f"(outside {rec2.get('outside_count')})")
        d2 = rec2.get("drstr") or {}
        errors += check(d2.get("updated") == 2,
                        f"reconcile: DRSTR values follow the resize (updated {d2.get('updated')})")
        errors += check(rec1.get("drstr", {}).get("updated") == 0,
                        "reconcile: same-length change leaves DRSTR values alone")
        with o2.open("rb") as h:
            _, g2b, f2b = open_map_partition(h)
            drstr_now = img_read(h, g2b, f2b, "DRSTR001.DAT")
        errors += check(_synth_drstr({"A.TXT": 1024, "b.txt": 1300, "C.TXT": 100,
                                      "DRSTR001.DAT": 40 + 4 * 32}) == drstr_now,
                        "reconcile: DRSTR001.DAT holds the new file sizes")
        with o2.open("rb") as h:
            _, g2, f2 = open_map_partition(h)
            ok_sizes = (img_read(h, g2, f2, "B.TXT") == b"B" * 1300
                        and img_read(h, g2, f2, "C.TXT") == b"C" * 100
                        and img_read(h, g2, f2, "A.TXT") == base["A.TXT"])
        errors += check(ok_sizes, "reconcile: resized files read back exactly")

        # R4: added file -> documented fallback to the fresh build
        t3 = tree_with({}, extra={"NEW.TXT": b"new\n"})
        o3 = td / "r3.img"
        r3 = mkcard(img, t3, o3, reconcile=True)
        errors += check((r3.get("reconcile") or {}).get("fallback") == "structural"
                        and r3["ok"],
                        "reconcile: added file falls back to the fresh build (reported)")

        # R5 negative control: a stray byte outside the envelope is caught
        bad = td / "bad.img"
        shutil.copyfile(o1, bad)
        with bad.open("r+b") as h:
            _, g, f = open_map_partition(h)
            free_cluster = max(c for c in range(2, len(f) // 4) if fat_get(f, c) == 0)
            # an untouched free cluster, far from A.TXT / B.TXT / C.TXT
            h.seek(g.cluster_offset(free_cluster))
            h.write(b"\xa5")
        ranges = diff_ranges(img, bad, limit=1 << 30)
        allowed = []
        with o1.open("rb") as h:
            _, g1, f1 = open_map_partition(h)
        for rel in ("A.TXT",):
            for c in chains_now[rel]:
                s = g1.cluster_offset(c)
                allowed.append((s, s + g1.cluster_bytes))
        errors += check(bool(outside_ranges(ranges, allowed)),
                        "reconcile: a stray byte outside the envelope is reported")
        # R6 positive control for the checker: nothing allowed -> everything outside
        errors += check(outside_ranges(ranges, []) == ranges,
                        "reconcile: empty envelope reports every range as outside")
    return errors


def selftest() -> int:
    print("mkcard self-test")
    errors = 0
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # 1) synthetic image + unchanged tree -> byte-identical copy path
        files = {
            "HELLO.TXT": b"hello world\n",
            "DATA.BIN": bytes(range(256)) * 10,
        }
        img = make_synthetic_image(td / "src.img", files)
        tree = td / "tree"
        tree.mkdir()
        for k, v in files.items():
            (tree / k).write_bytes(v)
        # copy HDD_INFO.TXT into tree? not in synthetic root, so it will differ.
        # For a true unchanged-tree test, extract what the image has.
        out = td / "out.img"
        # compare-only on mismatched tree
        res = mkcard(img, td / "empty", td / "x.img", compare_only=True)
        empty = td / "empty"; empty.mkdir()
        # build matching tree from image
        tree2 = td / "tree2"; tree2.mkdir()
        with img.open("rb") as h:
            _, geo, fat = open_map_partition(h)
            for rel, e in img_walk_files(h, geo, fat):
                dst = tree2 / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(img_read(h, geo, fat, rel))
        res = mkcard(img, tree2, out, compare_only=True)
        if not res["identical"] or res["tree_diffs"]:
            print(f"  FAIL: compare-only on identical tree: {res['tree_diffs']}")
            errors += 1
        else:
            print("  ok: compare-only identical tree")
        res = mkcard(img, tree2, out)
        if not res["identical"]:
            print(f"  FAIL: unchanged tree not byte-identical: {res.get('ranges',[])[:3]}")
            errors += 1
        else:
            print("  ok: unchanged tree byte-identical")
        if sha256_file(img) != sha256_file(out):
            print("  FAIL: sha256 mismatch on unchanged tree")
            errors += 1
        else:
            print("  ok: sha256 match")
        # diff_ranges sanity
        a = td/"a.bin"; b = td/"b.bin"
        a.write_bytes(b"\x00"*100); b.write_bytes(b"\x00"*50 + b"\xff"*10 + b"\x00"*40)
        rr = diff_ranges(a,b)
        if rr != [(50,60)]:
            print(f"  FAIL: diff_ranges {rr}")
            errors += 1
        else:
            print("  ok: diff_ranges")
        # explain_range doesn't crash
        ex = explain_range(img, HDD_COPY_OFFSET, HDD_COPY_OFFSET+10)
        print(f"  ok: explain_range -> {ex}")

        # 2) fresh build on a changed tree produces a readable FAT32
        tree3 = td / "tree3"; tree3.mkdir()
        (tree3 / "HELLO.TXT").write_bytes(b"changed content here\n")
        (tree3 / "SUB").mkdir()
        (tree3 / "SUB" / "INNER.TXT").write_bytes(b"inner")
        out3 = td / "out3.img"
        res3 = mkcard(img, tree3, out3)
        if not res3["ranges"]:
            # changed vs source, so ranges should exist (or identical impossible)
            pass
        # verify the output has a valid FAT32 and contains our files
        try:
            with out3.open("rb") as h:
                _, geo, fat = open_map_partition(h)
                got = img_read(h, geo, fat, "HELLO.TXT")
                if got != b"changed content here\n":
                    print(f"  FAIL: fresh build content mismatch: {got!r}")
                    errors += 1
                else:
                    print("  ok: fresh build reads back changed file")
                got2 = img_read(h, geo, fat, "SUB/INNER.TXT")
                if got2 != b"inner":
                    print(f"  FAIL: fresh build subdir: {got2!r}")
                    errors += 1
                else:
                    print("  ok: fresh build subdir file")
        except Exception as e:
            print(f"  FAIL: fresh build verify: {e}")
            errors += 1
        # source firmware region preserved
        plba = (HDD_COPY_OFFSET // 512) + 256
        with img.open("rb") as f1, out3.open("rb") as f2:
            pre = f1.read(plba * 512)
            if f2.read(plba * 512) != pre:
                print("  FAIL: pre-partition not preserved")
                errors += 1
            else:
                print("  ok: pre-partition preserved")
            f1.seek(HDD_COPY_OFFSET); f2.seek(HDD_COPY_OFFSET)
            if f1.read(72) != SYNTH_HDD or f2.read(72) != SYNTH_HDD:
                print("  FAIL: 0x06000000 HDD_INFO not preserved")
                errors += 1
            else:
                print("  ok: 0x06000000 HDD_INFO preserved")

        # 3) fresh build keeps the factory root label entry (attr 0x08) and
        #    the source root order; a --label mismatch is reported.
        order_files = {"BETA.TXT": b"beta\n", "ALPHA.TXT": b"alpha\n"}
        label_img = make_synthetic_image(td / "label.img", order_files,
                                         label="QSD-301-103")
        with label_img.open("rb") as h:
            _, lgeo, lfat = open_map_partition(h)
            src_root = root_layout(h, lgeo, lfat)
        if (src_root.label_name != "QSD-301-103"
                or src_root.label_raw is None or src_root.label_raw[11] != 0x08):
            print(f"  FAIL: synthetic source label: {src_root.label_name!r}")
            errors += 1
        else:
            print("  ok: synthetic source label entry (attr 0x08)")
        if src_root.order != ["BETA.TXT", "ALPHA.TXT"]:
            print(f"  FAIL: synthetic source root order: {src_root.order}")
            errors += 1
        else:
            print("  ok: synthetic source root order is non-alphabetical")
        label_tree = td / "label_tree"; label_tree.mkdir()
        (label_tree / "BETA.TXT").write_bytes(b"beta changed\n")
        (label_tree / "ALPHA.TXT").write_bytes(b"alpha\n")
        label_out = td / "label_out.img"
        lres = mkcard(label_img, label_tree, label_out)
        lrep = lres.get("root_report") or {}
        try:
            with label_out.open("rb") as h:
                _, ogeo, ofat = open_map_partition(h)
                out_root = root_layout(h, ogeo, ofat)
            ok_label = (out_root.label_raw is not None
                        and out_root.label_raw[11] == 0x08
                        and out_root.label_name == "QSD-301-103")
            if not ok_label:
                print(f"  FAIL: fresh build label: {out_root.label_name!r} "
                      f"attr={out_root.label_raw[11] if out_root.label_raw else None}")
                errors += 1
            else:
                print("  ok: fresh build keeps root label QSD-301-103 (attr 0x08)")
            if out_root.order != ["BETA.TXT", "ALPHA.TXT"]:
                print(f"  FAIL: fresh build root order: {out_root.order}")
                errors += 1
            else:
                print("  ok: fresh build keeps source root order")
            if (lrep.get("root_order_preserved") != 2
                    or not lrep.get("root_order_in_source_order")):
                print(f"  FAIL: fresh build root report: {lrep}")
                errors += 1
            else:
                print("  ok: fresh build reports preserved root order")
            line = format_root_report(lrep)
            if "preserved" not in line or "QSD-301-103" not in line:
                print(f"  FAIL: root report line: {line}")
                errors += 1
            else:
                print(f"  ok: root report -> {line}")
        except Exception as e:
            print(f"  FAIL: fresh build label verify: {e}")
            errors += 1
        # --label override: new root label, mismatch against source reported
        override_out = td / "label_override.img"
        ores = mkcard(label_img, label_tree, override_out, label="QSD-999-999")
        orep = ores.get("root_report") or {}
        try:
            with override_out.open("rb") as h:
                _, ogeo, ofat = open_map_partition(h)
                oroot = root_layout(h, ogeo, ofat)
            if oroot.label_name != "QSD-999-999" or oroot.label_raw[11] != 0x08:
                print(f"  FAIL: --label override: {oroot.label_name!r}")
                errors += 1
            elif not orep.get("label_mismatch"):
                print(f"  FAIL: --label mismatch not flagged: {orep}")
                errors += 1
            elif "LABEL MISMATCH" not in format_root_report(orep):
                print("  FAIL: --label mismatch missing from report line")
                errors += 1
            else:
                print("  ok: --label override + mismatch reported")
        except Exception as e:
            print(f"  FAIL: --label override verify: {e}")
            errors += 1
        # --no-preserve-root-order: alphabetical fallback reported
        alpha_out = td / "label_alpha.img"
        ares = mkcard(label_img, label_tree, alpha_out, preserve_root_order=False)
        arep = ares.get("root_report") or {}
        try:
            with alpha_out.open("rb") as h:
                _, ogeo, ofat = open_map_partition(h)
                aroot = root_layout(h, ogeo, ofat)
            if aroot.order != ["ALPHA.TXT", "BETA.TXT"]:
                print(f"  FAIL: --no-preserve-root-order: {aroot.order}")
                errors += 1
            elif "NOT preserved" not in format_root_report(arep):
                print("  FAIL: --no-preserve-root-order not reported")
                errors += 1
            else:
                print("  ok: --no-preserve-root-order reports alphabetical order")
        except Exception as e:
            print(f"  FAIL: --no-preserve-root-order verify: {e}")
            errors += 1

    errors += _selftest_reconcile()

    if errors:
        print(f"mkcard self-test: {errors} FAILED")
        return 1
    print("mkcard self-test: OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--from-image", help="source SD image (factory layout)")
    p.add_argument("--tree", help="card root tree to write")
    p.add_argument("-o", "--out", help="output image path")
    p.add_argument("--compare-only", action="store_true",
                   help="compare tree to image; do not write output")
    p.add_argument("--no-explain", action="store_true", help="skip diff verification/explanation")
    p.add_argument("--cardcheck", action="store_true", help="run cardcheck --image on output")
    p.add_argument("--label", help="override the root volume-label entry (attr 0x08, max 11 chars)")
    p.add_argument("--preserve-root-order", action=argparse.BooleanOptionalAction,
                   default=True,
                   help="keep the source root directory order on a fresh build (default: on)")
    p.add_argument("--reconcile", action="store_true",
                   help="changed tree: keep the factory layout and rewrite only the "
                        "changed files (imgpatch chain writer); added/removed files "
                        "fall back to the fresh build")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.from_image or not args.tree:
        p.error("--from-image and --tree are required (or use --selftest)")
    if not args.compare_only and not args.out:
        p.error("-o/--out is required unless --compare-only")
    if args.reconcile and args.label is not None:
        p.error("--label is not supported with --reconcile")

    res = mkcard(Path(args.from_image), Path(args.tree),
                 Path(args.out) if args.out else Path("/dev/null"),
                 compare_only=args.compare_only, explain=not args.no_explain,
                 verbose=args.verbose, label=args.label,
                 preserve_root_order=args.preserve_root_order,
                 reconcile=args.reconcile)
    if args.compare_only:
        print(f"tree_diffs={len(res['tree_diffs'])} identical={res['identical']}")
        for d in res["tree_diffs"]:
            print(" ", d)
        return 0 if res["identical"] else 1

    print(f"wrote {args.out}")
    print(f"identical={res['identical']} tree_diffs={len(res['tree_diffs'])} diff_ranges={len(res['ranges'])}")
    print(format_root_report(res.get("root_report")))
    rec = res.get("reconcile")
    if rec and rec.get("fallback"):
        print(f"reconcile: fell back to fresh build ({rec['fallback']}: {rec['structural']})")
    elif rec:
        print(f"reconcile: {len(rec['patches'])} file(s) patched in place; "
              f"{rec['ranges']} diff range(s), {rec['outside_count']} outside envelope")
        for pt in rec["patches"]:
            print(f"  {pt['file']}: {pt['old_size']} -> {pt['new_size']} B, "
                  f"{pt['clusters_before']} -> {pt['clusters_after']} clusters, "
                  f"verify {'OK' if pt['verify']['ok'] else 'FAIL'}")
    print(f"cannot reproduce: {', '.join(res['cannot_reproduce'])}")
    if res["ranges"] and not res["identical"]:
        shown = 0
        for r in res["ranges"][:30]:
            print(f"  0x{r['range'][0]:08x}-0x{r['range'][1]:08x} ({r['bytes']} B): {r['explain']}")
            shown += 1
        if len(res["ranges"]) > shown:
            print(f"  ... {len(res['ranges'])-shown} more ranges")
    if args.cardcheck:
        ok, msg = run_cardcheck_image(Path(args.out))
        print(msg)
        if not ok:
            return 1
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
