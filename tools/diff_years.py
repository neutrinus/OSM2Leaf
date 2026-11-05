#!/usr/bin/env python3
"""Differential comparison of two Leaf ZE0 card trees or card images.

Compares, in this order:

1. tree census (top-level entries, file/directory counts, sizes);
2. ``VER_INFO/HDD_INFO.TXT`` line by line, plus the ``0x06000000`` image copy
   when a raw image is one of the inputs;
3. the common 512-byte header (UTF-16BE text through ``0x180`` and the binary
   block from ``0x180``; descriptor tables at ``0x1ac`` are left to the owner
   section so they are not reported twice);
4. ``DRSTR001.DAT`` layout, its leading ``u32`` and every node/entry;
5. the ``MMAIN001.DAT`` level table at ``0x1ac``;
6. the ``MAPAL001`` tile inventory and the per-tile ``0x1ac``/``0x2ac``
   descriptor bytes;
7. SHA-256 file hashes (equal-size files by default).

Sources are auto-detected: a directory is an extracted card root, anything
else is a raw SD image read through :mod:`cardcheck`/:mod:`leafimg` helpers.
``--image`` forces image mode for both inputs.

Both inputs are read-only.  The tool imports the existing parsers instead of
re-deriving ``DRSTR``, the header fields or the level table:

* :func:`drstr.parse` for ``DRSTR001.DAT``;
* :func:`cardcheck.RootSource` / :func:`cardcheck.Fat32Image` for files;
* :func:`cardcheck.header_fields` for the common header;
* :func:`cardcheck.parse_level_table` for the ``0x1ac`` level table;
* :func:`leafimg.mbr_entries` for the image partition summary.

Usage::

    python3 tools/diff_years.py A B
    python3 tools/diff_years.py A B --json
    python3 tools/diff_years.py --image img1.img img2.img --no-hashes
    python3 tools/diff_years.py A B --partial --ignore-dump-artifacts
    python3 tools/diff_years.py --selftest

Exit codes: 0 = identical (suppressed diffs do not count), 1 = differences,
2 = usage/IO error or failed self-test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import cardcheck  # noqa: E402
import drstr  # noqa: E402
import leafimg  # noqa: E402

# Constants from docs/format/file-header.md, docs/format/drstr.md,
# docs/format/drstr.md "Related files", docs/format/validation.md and
# docs/format/map-tiles.md.
HEADER_TEXT_END = 0x180
HEADER_BINARY_START = 0x180
HEADER_BINARY_END = 0x200
HEADER_BINARY_TRUNCATED = 0x1AC  # tables parsed by their own sections
HDD_INFO_PATH = "VER_INFO/HDD_INFO.TXT"
HDD_INFO_SIZE = 72
HDD_COPY_OFFSET = 0x06000000
DRSTR_PATH = "DRSTR001.DAT"
MMAIN_PATH = "MMAIN001.DAT"
MAPAL_DIR = "MAPAL001"
LEVEL_TABLE_OFFSET = 0x1AC
BBOX_TABLE_OFFSET = 0x2AC
HASH_CHUNK = 8 << 20

HEADER_FILES = (
    MMAIN_PATH,
    "RDSTM001/RDSTM001.DAT",
    "REFER002/COORD001.DAT",
    "BICON001/BICON001.DAT",
    "MAPAL001/LEV3456R.DAT",
)
HEADER_TEXT_KEYS = ("clarion", "hitachi", "model", "format", "data", "version")
LEVEL_ROW_NAMES = ("level", "type", "count")
BBOX_ROW_NAMES = (
    "level",
    "flags",
    "lat_top",
    "lat_bottom",
    "lon_left",
    "lon_right",
)


# ---------------------------------------------------------------------------
# reporting model


class Section:
    """One comparison category with its diffs, suppressions and notes."""

    def __init__(self, sid: str, title: str):
        self.id = sid
        self.title = title
        self.available = True
        self.diffs: list[str] = []
        self.suppressed: list[str] = []
        self.notes: list[str] = []
        self.summary = ""
        self.stats: dict = {}

    def add(self, message: str, suppressed: bool = False) -> None:
        (self.suppressed if suppressed else self.diffs).append(message)

    def note(self, message: str) -> None:
        self.notes.append(message)

    def unavailable(self, message: str) -> None:
        self.available = False
        self.note(message)

    def to_dict(self) -> dict:
        if not self.available:
            status = "unavailable"
        elif self.diffs:
            status = "different"
        else:
            status = "same"
        return {
            "id": self.id,
            "title": self.title,
            "status": status,
            "summary": self.summary,
            "diffs": self.diffs,
            "suppressed": self.suppressed,
            "notes": self.notes,
            "stats": self.stats,
        }


def find_section(result: dict, sid: str) -> dict:
    return next(section for section in result["sections"] if section["id"] == sid)


# ---------------------------------------------------------------------------
# sources and small helpers


def open_source(path: str | Path, assume: str = "auto"):
    target = Path(path)
    if assume == "image" or (assume == "auto" and not target.is_dir()):
        return cardcheck.Fat32Image(target)
    if assume == "root" or target.is_dir():
        return cardcheck.RootSource(target)
    raise ValueError(f"cannot open {target!r} as a root or image")


def source_description(source, path: str | Path, kind: str) -> dict:
    info: dict = {"kind": kind, "path": str(Path(path))}
    if isinstance(source, cardcheck.Fat32Image):
        info["size"] = source.size
        info["label"] = source.geometry.label
        info["partitions"] = [
            {key: entry[key] for key in ("index", "type", "lba", "offset", "bytes")}
            for entry in leafimg.mbr_entries(source.handle)
        ]
    return info


def read_optional(source, rel: str) -> bytes | None:
    try:
        return source.read(rel)
    except (OSError, ValueError):
        return None


def is_ver_info(path: str) -> bool:
    return path == "VER_INFO" or path.startswith("VER_INFO/")


def tree_label(path: str, meta: dict) -> str:
    return path + "/" if meta["dir"] else path


def tree_stats(tree: dict) -> dict:
    files = sum(1 for meta in tree.values() if not meta["dir"])
    dirs = sum(1 for meta in tree.values() if meta["dir"])
    total = sum(meta["size"] for meta in tree.values() if not meta["dir"])
    top = sorted(tree_label(path, tree[path]) for path in tree if "/" not in path)
    return {"files": files, "dirs": dirs, "bytes": total, "top": top}


def collect_tree(source, ignore_artifacts: bool) -> dict[str, dict]:
    tree = {}
    for entry in source.walk():
        if cardcheck.path_has_artifact(entry.path, ignore_artifacts):
            continue
        tree[entry.path] = {
            "dir": entry.is_dir,
            "size": 0 if entry.is_dir else entry.size,
        }
    return tree


def hash_file(source, rel: str, size: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    while offset < size:
        block = source.read_range(rel, offset, min(HASH_CHUNK, size - offset))
        if not block:
            break
        digest.update(block)
        offset += len(block)
    return digest.hexdigest()


def differing_offsets(left: bytes, right: bytes) -> list[int]:
    return [
        index
        for index in range(min(len(left), len(right)))
        if left[index] != right[index]
    ]


# ---------------------------------------------------------------------------
# 1. tree census


def check_tree(section: Section, ctx: dict) -> None:
    left = ctx["a_tree"]
    right = ctx["b_tree"]
    partial = ctx["partial"]
    suppress_ver = partial and ctx["ver_info_missing"]

    stats_a = tree_stats(left)
    stats_b = tree_stats(right)
    section.stats = {"a": stats_a, "b": stats_b}
    section.summary = (
        f"A files={stats_a['files']} dirs={stats_a['dirs']} "
        f"bytes={stats_a['bytes']}; B files={stats_b['files']} "
        f"dirs={stats_b['dirs']} bytes={stats_b['bytes']}"
    )

    for path in sorted(set(left) - set(right)):
        section.add(
            f"only in A: {tree_label(path, left[path])}",
            suppressed=suppress_ver and is_ver_info(path),
        )
    for path in sorted(set(right) - set(left)):
        section.add(
            f"only in B: {tree_label(path, right[path])}",
            suppressed=suppress_ver and is_ver_info(path),
        )
    for path in sorted(set(left) & set(right)):
        meta_a = left[path]
        meta_b = right[path]
        suppressed = suppress_ver and is_ver_info(path)
        if meta_a["dir"] != meta_b["dir"]:
            section.add(
                f"{path}: type {'dir' if meta_a['dir'] else 'file'} in A, "
                f"{'dir' if meta_b['dir'] else 'file'} in B",
                suppressed=suppressed,
            )
        elif not meta_a["dir"] and meta_a["size"] != meta_b["size"]:
            section.add(
                f"{path}: size {meta_a['size']} -> {meta_b['size']}",
                suppressed=suppressed,
            )


# ---------------------------------------------------------------------------
# 2. VER_INFO/HDD_INFO.TXT and the 0x06000000 copy


def hdd_lines(blob: bytes) -> tuple[list[bytes], bool]:
    lines = blob.split(b"\r\n")
    trailing = bool(lines) and lines[-1] == b""
    if trailing:
        lines = lines[:-1]
    return lines, trailing


def show_line(line: bytes) -> str:
    return repr(line.decode("ascii", "backslashreplace"))


def hdd_image_copy(source) -> bytes | None:
    if not isinstance(source, cardcheck.Fat32Image):
        return None
    try:
        blob = source.read_absolute(HDD_COPY_OFFSET, HDD_INFO_SIZE)
    except (OSError, ValueError):
        return None
    return blob if len(blob) == HDD_INFO_SIZE else None


def check_hdd_info(section: Section, ctx: dict, a_source, b_source) -> None:
    left = read_optional(a_source, HDD_INFO_PATH)
    right = read_optional(b_source, HDD_INFO_PATH)
    partial = ctx["partial"]

    if left is None or right is None:
        if partial:
            section.add(
                f"{HDD_INFO_PATH}: missing on one side (partial tree)", suppressed=True
            )
            section.summary = "partial: absence suppressed"
            if left is None and right is None:
                section.unavailable("absent in both trees")
            return
        if left is None and right is None:
            section.unavailable(f"{HDD_INFO_PATH} is absent from both trees")
            return
        if left is None:
            section.add(f"only in B: {HDD_INFO_PATH}")
        if right is None:
            section.add(f"only in A: {HDD_INFO_PATH}")
        section.summary = "missing on one side"
        return

    section.stats = {"a_size": len(left), "b_size": len(right)}
    section.summary = f"A {len(left)} bytes, B {len(right)} bytes"

    if len(left) != len(right):
        section.add(f"{HDD_INFO_PATH}: size {len(left)} -> {len(right)}")
    if left == right:
        section.note(f"{HDD_INFO_PATH} is byte-identical")
    else:
        lines_a, trailing_a = hdd_lines(left)
        lines_b, trailing_b = hdd_lines(right)
        if trailing_a != trailing_b:
            section.add(
                f"{HDD_INFO_PATH}: trailing CRLF "
                f"{'present' if trailing_a else 'absent'} in A, "
                f"{'present' if trailing_b else 'absent'} in B"
            )
        for index in range(max(len(lines_a), len(lines_b))):
            line_a = lines_a[index] if index < len(lines_a) else None
            line_b = lines_b[index] if index < len(lines_b) else None
            if line_a != line_b:
                section.add(
                    f"{HDD_INFO_PATH} line {index + 1}: "
                    f"{show_line(line_a) if line_a is not None else '(missing)'} "
                    f"-> {show_line(line_b) if line_b is not None else '(missing)'}"
                )
        if len(lines_a) != 6 or len(lines_b) != 6:
            section.note(
                f"line count A={len(lines_a)} B={len(lines_b)}; "
                "the factory file is six CRLF lines, 72 bytes"
            )

    copy_a = hdd_image_copy(a_source)
    copy_b = hdd_image_copy(b_source)
    if copy_a is not None and copy_a != left:
        section.add("A: 0x06000000 copy differs from its VER_INFO/HDD_INFO.TXT")
    if copy_b is not None and copy_b != right:
        section.add("B: 0x06000000 copy differs from its VER_INFO/HDD_INFO.TXT")
    if copy_a is not None and copy_b is not None:
        section.stats["image_copy"] = "both"
        if copy_a != copy_b:
            section.add("0x06000000 copies differ between A and B")
        else:
            section.note("0x06000000 copies are byte-identical")
    elif copy_a is not None:
        section.stats["image_copy"] = "A only"
        if copy_a != right:
            section.add("A 0x06000000 copy differs from B VER_INFO/HDD_INFO.TXT")
        else:
            section.note("A 0x06000000 copy matches B VER_INFO/HDD_INFO.TXT")
    elif copy_b is not None:
        section.stats["image_copy"] = "B only"
        if copy_b != left:
            section.add("B 0x06000000 copy differs from A VER_INFO/HDD_INFO.TXT")
        else:
            section.note("B 0x06000000 copy matches A VER_INFO/HDD_INFO.TXT")
    else:
        section.stats["image_copy"] = "not available"
        section.note("0x06000000 copy is only readable from a raw image")


# ---------------------------------------------------------------------------
# 3. common 512-byte header


def header_text_fields(blob: bytes) -> dict[str, str]:
    fields = cardcheck.header_fields(blob)
    # Drop the non-printable prefix (the factory stores ``16 00`` before the
    # version string at 0x160) so the diff shows stable text.
    return {
        key: "".join(ch for ch in value if 0x20 <= ord(ch) <= 0x7E)
        for key, value in fields.items()
    }


def header_binary_end(rel: str) -> int:
    if rel == MMAIN_PATH or rel.startswith(MAPAL_DIR + "/"):
        return HEADER_BINARY_TRUNCATED
    return HEADER_BINARY_END


def header_targets(ctx: dict) -> list[str]:
    left = ctx["a_tree"]
    right = ctx["b_tree"]

    def present(rel: str) -> bool:
        return (
            rel in left
            and rel in right
            and not left[rel]["dir"]
            and not right[rel]["dir"]
        )

    targets = [rel for rel in HEADER_FILES if present(rel)]
    for name in sorted(ctx["common_tiles"]):
        rel = f"{MAPAL_DIR}/{name}"
        if rel == "MAPAL001/LEV3456R.DAT":
            continue  # already in HEADER_FILES
        if present(rel):
            targets.append(rel)
    return targets


def check_headers(section: Section, ctx: dict, a_source, b_source) -> None:
    targets = header_targets(ctx)
    compared = differing = 0
    for rel in targets:
        try:
            left = a_source.read_range(rel, 0, HEADER_BINARY_END)
            right = b_source.read_range(rel, 0, HEADER_BINARY_END)
        except (OSError, ValueError) as exc:
            section.add(f"{rel}: cannot read header: {exc}")
            continue
        if len(left) < HEADER_TEXT_END or len(right) < HEADER_TEXT_END:
            section.note(f"{rel}: shorter than 0x180; header compared as raw bytes")
            if left == right:
                continue
            first = differing_offsets(left, right)
            if first:
                section.add(f"{rel}: raw header differs at 0x{first[0]:x}")
            else:
                section.add(f"{rel}: raw header length differs")
            differing += 1
            compared += 1
            continue
        compared += 1
        before = len(section.diffs)
        fields_a = header_text_fields(left)
        fields_b = header_text_fields(right)
        for key in HEADER_TEXT_KEYS:
            value_a = fields_a.get(key, "")
            value_b = fields_b.get(key, "")
            if value_a != value_b:
                section.add(f"{rel}: header {key} {value_a!r} -> {value_b!r}")

        end = header_binary_end(rel)
        binary_a = left[HEADER_BINARY_START:end]
        binary_b = right[HEADER_BINARY_START:end]
        if binary_a != binary_b:
            offsets = differing_offsets(binary_a, binary_b)
            if offsets:
                first = HEADER_BINARY_START + offsets[0]
                section.add(
                    f"{rel}: 0x180 block differs in {len(offsets)} byte(s); "
                    f"first at 0x{first:x} "
                    f"({left[first]:02x} -> {right[first]:02x})"
                )
            else:
                section.add(
                    f"{rel}: 0x180 block length differs "
                    f"({len(binary_a)} -> {len(binary_b)})"
                )
        if len(section.diffs) != before:
            differing += 1
    section.stats = {"compared": compared, "differing": differing}
    section.summary = f"compared={compared} differing={differing}"
    if not targets:
        section.unavailable("no common header-bearing files")


# ---------------------------------------------------------------------------
# 4. DRSTR001.DAT


def load_drstr(source):
    blob = read_optional(source, DRSTR_PATH)
    if blob is None:
        return None
    try:
        return {"data": blob, "tree": drstr.parse(blob), "error": ""}
    except ValueError as exc:
        return {"data": blob, "tree": None, "error": str(exc)}


def drstr_paths(tree: dict) -> dict[int, str]:
    paths: dict[int, str] = {}
    for index, node in enumerate(tree["nodes"]):
        if index == 0:
            paths[index] = ""
            continue
        parent = node["parent"]
        if parent is None or parent >= index or parent not in paths:
            paths[index] = f"<bad:{index}>"
        else:
            paths[index] = f"{paths[parent]}/{node['name']}".strip("/")
    return paths


def drstr_layout(data: bytes, tree: dict) -> dict:
    entries = sum(len(node["entries"]) for node in tree["nodes"])
    node_table_end = tree["node_count"] * drstr.NODE_SIZE
    listing_end = max(
        (node["listing_offset"] + len(node["entries"]) * drstr.ENTRY_SIZE
         for node in tree["nodes"]),
        default=node_table_end,
    )
    return {
        "leading_u32": struct.unpack_from("<I", data, 0)[0],
        "size": len(data),
        "nodes": tree["node_count"],
        "entries": entries,
        "node_table_end": node_table_end,
        "listing_end": listing_end,
    }


def check_drstr(section: Section, ctx: dict, a_source, b_source) -> None:
    left = load_drstr(a_source)
    right = load_drstr(b_source)
    if left is None or right is None:
        if left is None:
            section.add(f"only in B: {DRSTR_PATH}")
        if right is None:
            section.add(f"only in A: {DRSTR_PATH}")
        section.summary = "missing on one side"
        return
    if left["tree"] is None or right["tree"] is None:
        if left["tree"] is None:
            section.add(f"A: {DRSTR_PATH} parse failed: {left['error']}")
        if right["tree"] is None:
            section.add(f"B: {DRSTR_PATH} parse failed: {right['error']}")
        section.summary = "parse failure"
        return

    layout_a = drstr_layout(left["data"], left["tree"])
    layout_b = drstr_layout(right["data"], right["tree"])
    section.stats = {
        "a": {key: layout_a[key] for key in ("size", "nodes", "entries")},
        "b": {key: layout_b[key] for key in ("size", "nodes", "entries")},
    }
    section.summary = (
        f"A size={layout_a['size']} nodes={layout_a['nodes']} "
        f"entries={layout_a['entries']}; B size={layout_b['size']} "
        f"nodes={layout_b['nodes']} entries={layout_b['entries']}"
    )
    section.note(
        "leading u32 is the root node's name bytes ('/'), not a count"
    )

    if layout_a["leading_u32"] != layout_b["leading_u32"]:
        section.add(
            f"leading u32 0x{layout_a['leading_u32']:08x} -> "
            f"0x{layout_b['leading_u32']:08x}"
        )
    for key in ("size", "nodes", "entries", "node_table_end", "listing_end"):
        if layout_a[key] != layout_b[key]:
            section.add(f"layout {key} {layout_a[key]} -> {layout_b[key]}")

    partial = ctx["partial"]
    suppress_ver = partial and ctx["ver_info_missing"]
    paths_a = drstr_paths(left["tree"])
    paths_b = drstr_paths(right["tree"])
    nodes_a = {paths_a[i]: node for i, node in enumerate(left["tree"]["nodes"])}
    nodes_b = {paths_b[i]: node for i, node in enumerate(right["tree"]["nodes"])}

    for path in sorted(set(nodes_a) - set(nodes_b)):
        section.add(
            f"directory {path or '/'} listed only in A",
            suppressed=suppress_ver and is_ver_info(path),
        )
    for path in sorted(set(nodes_b) - set(nodes_a)):
        section.add(
            f"directory {path or '/'} listed only in B",
            suppressed=suppress_ver and is_ver_info(path),
        )
    for path in sorted(set(nodes_a) & set(nodes_b)):
        node_a = nodes_a[path]
        node_b = nodes_b[path]
        suppressed = suppress_ver and is_ver_info(path)
        for key in ("parent", "next_index", "entry_count", "listing_offset"):
            if node_a[key] != node_b[key]:
                section.add(
                    f"node {path or '/'}: {key} {node_a[key]} -> {node_b[key]}",
                    suppressed=suppressed,
                )
        entries_a = {entry["name"]: entry for entry in node_a["entries"]}
        entries_b = {entry["name"]: entry for entry in node_b["entries"]}
        for name in sorted(set(entries_a) - set(entries_b)):
            section.add(
                f"{path or '/'}: entry {name!r} only in A",
                suppressed=suppressed
                or (suppress_ver and path == "" and name == "VER_INFO"),
            )
        for name in sorted(set(entries_b) - set(entries_a)):
            section.add(
                f"{path or '/'}: entry {name!r} only in B",
                suppressed=suppressed
                or (suppress_ver and path == "" and name == "VER_INFO"),
            )
        for name in sorted(set(entries_a) & set(entries_b)):
            entry_a = entries_a[name]
            entry_b = entries_b[name]
            entry_suppressed = suppressed or (
                suppress_ver and path == "" and name == "VER_INFO"
            )
            if entry_a["type"] != entry_b["type"]:
                section.add(
                    f"{path or '/'}/{name}: type {entry_a['type']} -> {entry_b['type']}",
                    suppressed=entry_suppressed,
                )
            if entry_a["value"] != entry_b["value"]:
                section.add(
                    f"{path or '/'}/{name}: value {entry_a['value']} -> "
                    f"{entry_b['value']}",
                    suppressed=entry_suppressed,
                )


# ---------------------------------------------------------------------------
# 5. MMAIN001.DAT level table


def level_rows(groups: list[dict]) -> dict[tuple[int, int], dict]:
    rows = {}
    for group in groups:
        for row in group["rows"]:
            rows[(group["section"], row["level"])] = row
    return rows


def check_mmain(section: Section, ctx: dict, a_source, b_source) -> None:
    left = read_optional(a_source, MMAIN_PATH)
    right = read_optional(b_source, MMAIN_PATH)
    if left is None or right is None:
        if left is None:
            section.add(f"only in B: {MMAIN_PATH}")
        if right is None:
            section.add(f"only in A: {MMAIN_PATH}")
        section.summary = "missing on one side"
        return
    try:
        groups_a = cardcheck.parse_level_table(left, LEVEL_TABLE_OFFSET)
        groups_b = cardcheck.parse_level_table(right, LEVEL_TABLE_OFFSET)
    except ValueError as exc:
        section.add(f"{MMAIN_PATH} level table: {exc}")
        section.summary = "parse failure"
        return

    rows_a = level_rows(groups_a)
    rows_b = level_rows(groups_b)
    section.stats = {
        "a": {"bytes": len(left), "groups": len(groups_a), "rows": len(rows_a)},
        "b": {"bytes": len(right), "groups": len(groups_b), "rows": len(rows_b)},
    }
    section.summary = (
        f"A groups={len(groups_a)} rows={len(rows_a)}; "
        f"B groups={len(groups_b)} rows={len(rows_b)}"
    )
    if len(groups_a) != len(groups_b):
        section.add(f"level-table group count {len(groups_a)} -> {len(groups_b)}")
    for key in sorted(set(rows_a) | set(rows_b)):
        if key not in rows_b:
            section.add(f"section {key[0]} level {key[1]} only in A")
        elif key not in rows_a:
            section.add(f"section {key[0]} level {key[1]} only in B")
        else:
            row_a = rows_a[key]
            row_b = rows_b[key]
            if row_a["type"] != row_b["type"]:
                section.add(
                    f"section {key[0]} level {key[1]}: type "
                    f"0x{row_a['type']:02x} -> 0x{row_b['type']:02x}"
                )
            if row_a["count"] != row_b["count"]:
                section.add(
                    f"section {key[0]} level {key[1]}: count "
                    f"{row_a['count']} -> {row_b['count']}"
                )


# ---------------------------------------------------------------------------
# 6. MAPAL001 tiles and their 0x1ac/0x2ac descriptors


def tile_names(tree: dict) -> set[str]:
    names = set()
    for path, meta in tree.items():
        if meta["dir"]:
            continue
        parts = path.split("/")
        if len(parts) == 2 and parts[0] == MAPAL_DIR and parts[1].endswith(".DAT"):
            names.add(parts[1])
    return names


def parse_descriptor_table(
    data: bytes,
    offset: int,
    row_size: int,
    row_format: str,
    row_names: tuple[str, ...],
    max_groups: int = 64,
) -> tuple[list[dict], int]:
    """Parse the shared ``u16 count | {id, n, rows...}`` container."""
    if offset + 2 > len(data):
        raise ValueError(f"table offset 0x{offset:x} outside {len(data)} bytes")
    count = struct.unpack_from(">H", data, offset)[0]
    if count > max_groups:
        raise ValueError(f"implausible group count {count} at 0x{offset:x}")
    position = offset + 2
    groups = []
    for _ in range(count):
        if position + 2 > len(data):
            raise ValueError("truncated group header")
        section_id = data[position]
        rows = data[position + 1]
        position += 2
        parsed = []
        for _ in range(rows):
            if position + row_size > len(data):
                raise ValueError("truncated descriptor row")
            values = struct.unpack_from(row_format, data, position)
            position += row_size
            parsed.append(dict(zip(row_names, values)))
        groups.append({"section": section_id, "rows": parsed})
    return groups, position


def level_table_end(groups: list[dict], offset: int) -> int:
    end = offset + 2
    for group in groups:
        end += 2 + 4 * len(group["rows"])
    return end


def flatten_level(groups: list[dict]) -> list[tuple]:
    return [
        (group["section"], row["level"], row["type"], row["count"])
        for group in groups
        for row in group["rows"]
    ]


def flatten_bbox(groups: list[dict]) -> list[tuple]:
    return [
        (
            group["section"],
            row["level"],
            row["flags"],
            row["lat_top"],
            row["lat_bottom"],
            row["lon_left"],
            row["lon_right"],
        )
        for group in groups
        for row in group["rows"]
    ]


def compare_descriptor(
    section: Section,
    rel: str,
    name: str,
    offset: int,
    left_data: bytes,
    right_data: bytes,
    left_groups: list[dict] | None,
    right_groups: list[dict] | None,
    left_end: int | None,
    right_end: int | None,
    flatten,
    row_label,
) -> bool:
    """Compare one descriptor table; return True when anything differed."""
    before = len(section.diffs)
    if left_groups is None or right_groups is None:
        end = offset + (0x54 if offset == LEVEL_TABLE_OFFSET else 0x30)
        raw_a = left_data[offset:end]
        raw_b = right_data[offset:end]
        if raw_a != raw_b:
            offsets = differing_offsets(raw_a, raw_b)
            first = offset + offsets[0] if offsets else offset
            section.add(
                f"{rel}: {name} descriptor differs (fallback raw compare; "
                f"first at 0x{first:x})"
            )
        return len(section.diffs) != before

    raw_a = left_data[offset:left_end]
    raw_b = right_data[offset:right_end]
    if raw_a != raw_b:
        offsets = differing_offsets(raw_a, raw_b)
        if offsets:
            first = offset + offsets[0]
            section.add(
                f"{rel}: {name} descriptor bytes differ in {len(offsets)} byte(s); "
                f"first at 0x{first:x} "
                f"({left_data[first]:02x} -> {right_data[first]:02x})"
            )
        else:
            section.add(
                f"{rel}: {name} descriptor length {len(raw_a)} -> {len(raw_b)}"
            )

    rows_a = flatten(left_groups)
    rows_b = flatten(right_groups)
    for index in range(max(len(rows_a), len(rows_b))):
        row_a = rows_a[index] if index < len(rows_a) else None
        row_b = rows_b[index] if index < len(rows_b) else None
        if row_a == row_b:
            continue
        if row_a is None:
            section.add(f"{rel}: {name} extra row {row_b}")
        elif row_b is None:
            section.add(f"{rel}: {name} missing row {row_a}")
        else:
            section.add(
                f"{rel}: {name} {row_label(row_a)} -> {row_label(row_b)}"
            )
    return len(section.diffs) != before


def level_row_label(row: tuple) -> str:
    section_id, level, kind, count = row
    return (
        f"section {section_id} level {level} type 0x{kind:02x} count {count}"
    )


def bbox_row_label(row: tuple) -> str:
    section_id, level, flags, lat_top, lat_bottom, lon_left, lon_right = row
    return (
        f"section {section_id} level {level} flags 0x{flags:02x} "
        f"lat {lat_bottom}..{lat_top} lon {lon_left}..{lon_right} arcmin"
    )


def check_tiles(section: Section, ctx: dict, a_source, b_source) -> None:
    names_a = tile_names(ctx["a_tree"])
    names_b = tile_names(ctx["b_tree"])
    section.stats = {"a_tiles": len(names_a), "b_tiles": len(names_b)}

    for name in sorted(names_a - names_b):
        section.add(f"only in A: {MAPAL_DIR}/{name}")
    for name in sorted(names_b - names_a):
        section.add(f"only in B: {MAPAL_DIR}/{name}")

    common = sorted(names_a & names_b)
    section.stats["common"] = len(common)
    compared = differing = 0
    for name in common:
        rel = f"{MAPAL_DIR}/{name}"
        size_a = ctx["a_tree"][rel]["size"]
        size_b = ctx["b_tree"][rel]["size"]
        if size_a != size_b:
            section.add(f"{rel}: size {size_a} -> {size_b}")
        try:
            head_a = a_source.read_range(rel, 0, 0x400)
            head_b = b_source.read_range(rel, 0, 0x400)
        except (OSError, ValueError) as exc:
            section.add(f"{rel}: cannot read descriptors: {exc}")
            continue
        compared += 1
        before = len(section.diffs)

        try:
            level_a = cardcheck.parse_level_table(head_a, LEVEL_TABLE_OFFSET)
            level_b = cardcheck.parse_level_table(head_b, LEVEL_TABLE_OFFSET)
            level_error = None
        except ValueError:
            level_a = level_b = None
            level_error = True
        try:
            bbox_a, bbox_end_a = parse_descriptor_table(
                head_a, BBOX_TABLE_OFFSET, 10, ">BBhhhh", BBOX_ROW_NAMES
            )
            bbox_b, bbox_end_b = parse_descriptor_table(
                head_b, BBOX_TABLE_OFFSET, 10, ">BBhhhh", BBOX_ROW_NAMES
            )
            bbox_error = None
        except ValueError:
            bbox_a = bbox_b = None
            bbox_end_a = bbox_end_b = None
            bbox_error = True

        compare_descriptor(
            section,
            rel,
            "0x1ac",
            LEVEL_TABLE_OFFSET,
            head_a,
            head_b,
            level_a,
            level_b,
            level_table_end(level_a, LEVEL_TABLE_OFFSET) if level_a is not None else None,
            level_table_end(level_b, LEVEL_TABLE_OFFSET) if level_b is not None else None,
            flatten_level,
            level_row_label,
        )
        if level_error:
            section.note(f"{rel}: 0x1ac is not a parseable level table")
        compare_descriptor(
            section,
            rel,
            "0x2ac",
            BBOX_TABLE_OFFSET,
            head_a,
            head_b,
            bbox_a,
            bbox_b,
            bbox_end_a,
            bbox_end_b,
            flatten_bbox,
            bbox_row_label,
        )
        if bbox_error:
            section.note(f"{rel}: 0x2ac is not a parseable bbox table")

        if len(section.diffs) != before:
            differing += 1

    section.stats.update({"descriptors_compared": compared, "differing": differing})
    section.summary = (
        f"A {len(names_a)} tiles, B {len(names_b)} tiles; "
        f"descriptors compared={compared} differing={differing}"
    )
    if not names_a and not names_b:
        section.unavailable("no MAPAL001 tiles on either side")


# ---------------------------------------------------------------------------
# 7. file hashes


def check_hashes(section: Section, ctx: dict, a_source, b_source) -> None:
    if not ctx["hashes"]:
        section.unavailable("disabled by --no-hashes")
        return
    left = ctx["a_tree"]
    right = ctx["b_tree"]
    compared = identical = skipped = 0
    for path in sorted(set(left) & set(right)):
        if left[path]["dir"] or right[path]["dir"]:
            continue
        size_a = left[path]["size"]
        size_b = right[path]["size"]
        if size_a != size_b and not ctx["hash_all"]:
            skipped += 1
            continue
        try:
            hash_a = hash_file(a_source, path, size_a)
            hash_b = hash_file(b_source, path, size_b)
        except (OSError, ValueError) as exc:
            section.add(f"{path}: cannot hash: {exc}")
            continue
        compared += 1
        if hash_a != hash_b:
            section.add(
                f"{path}: SHA-256 {hash_a[:16]}… -> {hash_b[:16]}…"
            )
        else:
            identical += 1
    section.stats = {
        "compared": compared,
        "identical": identical,
        "skipped_size_mismatch": skipped,
    }
    section.summary = (
        f"compared={compared} identical={identical} "
        f"skipped(size mismatch)={skipped}"
    )
    if not ctx["hash_all"]:
        section.note(
            "files with different sizes are reported by the tree section and "
            "not hashed; use --hash-all to hash them too"
        )


# ---------------------------------------------------------------------------
# driver


def compare(
    a_path: str | Path,
    b_path: str | Path,
    *,
    assume: str = "auto",
    ignore_artifacts: bool = False,
    partial: bool = False,
    hashes: bool = True,
    hash_all: bool = False,
) -> dict:
    a_source = b_source = None
    try:
        a_source = open_source(a_path, assume)
        b_source = open_source(b_path, assume)
        kind_a = "image" if isinstance(a_source, cardcheck.Fat32Image) else "root"
        kind_b = "image" if isinstance(b_source, cardcheck.Fat32Image) else "root"

        a_tree = collect_tree(a_source, ignore_artifacts)
        b_tree = collect_tree(b_source, ignore_artifacts)
        has_ver_a = "VER_INFO" in a_tree
        has_ver_b = "VER_INFO" in b_tree
        ctx = {
            "a_tree": a_tree,
            "b_tree": b_tree,
            "common_tiles": tile_names(a_tree) & tile_names(b_tree),
            "ignore_artifacts": ignore_artifacts,
            "partial": partial,
            "ver_info_missing": has_ver_a != has_ver_b,
            "hashes": hashes,
            "hash_all": hash_all,
        }

        sections = [
            Section("tree", "tree census"),
            Section("hdd_info", "VER_INFO/HDD_INFO.TXT and 0x06000000 copy"),
            Section("headers", "common 512-byte header"),
            Section("drstr", "DRSTR001.DAT"),
            Section("mmain", "MMAIN001.DAT level table"),
            Section("tiles", "MAPAL001 tile inventory and descriptors"),
            Section("hashes", "file hashes"),
        ]
        by_id = {section.id: section for section in sections}

        check_tree(by_id["tree"], ctx)
        check_hdd_info(by_id["hdd_info"], ctx, a_source, b_source)
        check_headers(by_id["headers"], ctx, a_source, b_source)
        check_drstr(by_id["drstr"], ctx, a_source, b_source)
        check_mmain(by_id["mmain"], ctx, a_source, b_source)
        check_tiles(by_id["tiles"], ctx, a_source, b_source)
        check_hashes(by_id["hashes"], ctx, a_source, b_source)

        payload = [section.to_dict() for section in sections]
        different = [s["id"] for s in payload if s["status"] == "different"]
        return {
            "tool": "diff_years",
            "a": source_description(a_source, a_path, kind_a),
            "b": source_description(b_source, b_path, kind_b),
            "options": {
                "assume": assume,
                "ignore_dump_artifacts": ignore_artifacts,
                "partial": partial,
                "hashes": hashes,
                "hash_all": hash_all,
            },
            "identical": not different,
            "sections": payload,
            "summary": {
                "different_categories": different,
                "differences": sum(len(s["diffs"]) for s in payload),
                "suppressed": sum(len(s["suppressed"]) for s in payload),
            },
        }
    finally:
        if a_source is not None:
            a_source.close()
        if b_source is not None:
            b_source.close()


def render_human(result: dict, max_diffs: int = 40) -> str:
    max_diffs = max(0, max_diffs)
    lines = [f"A ({result['a']['kind']}): {result['a']['path']}"]
    if result["a"].get("label"):
        lines[0] += f"  label={result['a']['label']}"
    lines.append(f"B ({result['b']['kind']}): {result['b']['path']}")
    if result["b"].get("label"):
        lines[-1] += f"  label={result['b']['label']}"
    if result["options"]["partial"]:
        lines.append("options: partial (VER_INFO absence suppressed)")
    if result["options"]["ignore_dump_artifacts"]:
        lines.append("options: ignore dump artifacts")

    for section in result["sections"]:
        status = section["status"].upper()
        summary = f"  {section['summary']}" if section["summary"] else ""
        lines.append(f"[{section['id']}] {status}{summary}")
        for message in section["notes"]:
            lines.append(f"  . {message}")
        for message in section["diffs"][:max_diffs]:
            lines.append(f"  - {message}")
        remaining = len(section["diffs"]) - max_diffs
        if remaining > 0:
            lines.append(f"  - ... {remaining} more difference(s) (see --json)")
        for message in section["suppressed"][:max_diffs]:
            lines.append(f"  ~ suppressed: {message}")
        remaining = len(section["suppressed"]) - max_diffs
        if remaining > 0:
            lines.append(f"  ~ ... {remaining} more suppressed")

    summary = result["summary"]
    if result["identical"]:
        lines.append(
            f"RESULT: IDENTICAL ({summary['suppressed']} suppressed difference(s))"
        )
    else:
        lines.append(
            f"RESULT: DIFFERENT ({len(summary['different_categories'])} "
            f"categories, {summary['differences']} difference(s), "
            f"{summary['suppressed']} suppressed)"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# synthetic self-test (no vendor data)


def put_utf16be(buffer: bytearray, offset: int, text: str) -> None:
    raw = text.encode("utf-16-be")
    buffer[offset : offset + len(raw)] = raw


def synth_header(
    *,
    model: str = "CLA-NAVI05-01",
    fmt: str = "FORMAT VERSION X08-02-00",
    data_version: str = "DATA VERSION 11/06/27/01",
    binary_18c: bytes = b"\x3f" * 20,
) -> bytearray:
    """Build a 512-byte common header with the documented text fields."""
    buffer = bytearray(b"\xff" * 512)
    put_utf16be(buffer, 0x000, "CLARION")
    put_utf16be(buffer, 0x040, "HITACHI")
    put_utf16be(buffer, 0x080, model)
    put_utf16be(buffer, 0x0A0, fmt)
    put_utf16be(buffer, 0x0E0, data_version)
    buffer[0x160:0x162] = b"\x16\x00"
    put_utf16be(buffer, 0x162, "V05.00.00")
    buffer[0x180:0x18C] = bytes.fromhex("ff ff 24 ff 12 c0 05 00 fb 50 0f f0")
    buffer[0x18C:0x1A0] = binary_18c[:20].ljust(20, b"\x3f")
    buffer[0x1A0:0x1AC] = b"\xff" * 12
    return buffer


def write_level_table(buffer: bytearray, groups: list[tuple[int, list[tuple]]]) -> None:
    struct.pack_into(">H", buffer, LEVEL_TABLE_OFFSET, len(groups))
    position = LEVEL_TABLE_OFFSET + 2
    for section_id, rows in groups:
        buffer[position] = section_id
        buffer[position + 1] = len(rows)
        position += 2
        for level, kind, count in rows:
            struct.pack_into(">BBH", buffer, position, level, kind, count)
            position += 4


def write_bbox_table(
    buffer: bytearray, groups: list[tuple[int, list[tuple]]]
) -> None:
    struct.pack_into(">H", buffer, BBOX_TABLE_OFFSET, len(groups))
    position = BBOX_TABLE_OFFSET + 2
    for section_id, rows in groups:
        buffer[position] = section_id
        buffer[position + 1] = len(rows)
        position += 2
        for level, flags, lat_top, lat_bottom, lon_left, lon_right in rows:
            struct.pack_into(
                ">BBhhhh",
                buffer,
                position,
                level,
                flags,
                lat_top,
                lat_bottom,
                lon_left,
                lon_right,
            )
            position += 10


def synth_mmain(
    count6: int = 1,
    count5: int = 1,
    model: str = "CLA-NAVI05-01",
    data_version: str = "DATA VERSION 11/06/27/01",
) -> bytes:
    buffer = synth_header(
        model=model,
        data_version=data_version,
        binary_18c=b"\x05\x04\x02\x07\x0a\x06\x08\x14" + b"\x3f" * 12,
    )
    buffer.extend(b"\x00" * (0x1000 - len(buffer)))
    write_level_table(
        buffer,
        [(1, [(6, 0x80, count6), (5, 0x90, count5)])],
    )
    return bytes(buffer)


def synth_tile(bbox_lat_top: int = 1920, size: int = 0x400) -> bytes:
    buffer = synth_header(binary_18c=b"\x3f" * 20)
    buffer.extend(b"\x00" * (size - len(buffer)))
    write_level_table(buffer, [(1, [(6, 0x80, 0), (5, 0x90, 0)])])
    write_bbox_table(
        buffer,
        [(1, [(2, 0, bbox_lat_top, 1685, -720, -562)])],
    )
    return bytes(buffer)


def synth_drstr(nodes: list[dict]) -> bytes:
    table_end = len(nodes) * drstr.NODE_SIZE
    listings = []
    position = table_end
    for node in nodes:
        listings.append(position)
        position += len(node["entries"]) * drstr.ENTRY_SIZE
    buffer = bytearray(position)
    for index, node in enumerate(nodes):
        raw = bytearray(drstr.NODE_SIZE)
        name = node["name"].encode("ascii")
        raw[: len(name)] = name
        struct.pack_into("<H", raw, 0x14, index + 1)
        parent_plus_one = (
            node["parent"] + 1 if node["parent"] is not None else index + 1
        )
        struct.pack_into("<H", raw, 0x16, parent_plus_one)
        struct.pack_into("<I", raw, 0x18, len(node["entries"]))
        struct.pack_into("<I", raw, 0x24, listings[index])
        buffer[index * drstr.NODE_SIZE : (index + 1) * drstr.NODE_SIZE] = raw
        for entry_index, (entry_name, entry_type, value) in enumerate(node["entries"]):
            entry = bytearray(drstr.ENTRY_SIZE)
            encoded = entry_name.encode("ascii")
            entry[: len(encoded)] = encoded
            struct.pack_into("<H", entry, 0x16, entry_type)
            struct.pack_into("<I", entry, 0x1C, value)
            start = listings[index] + entry_index * drstr.ENTRY_SIZE
            buffer[start : start + drstr.ENTRY_SIZE] = entry
    return bytes(buffer)


HDD_2011 = b"QSD-302-100\r\nQSD-309-101\r\n02-110100-00\r\nSDC08-EVEUR\r\n11-05\r\n470323501005"
HDD_2014 = b"QSD-302-100\r\nQSD-357-101\r\n02-140300-00\r\nSDC08-EVEUR\r\n14-06\r\n470516001006"
CMP_LIST = b"\\SystemSD\\REFER001\\"


def synthesize_root(
    root: Path,
    *,
    hdd: bytes = HDD_2011,
    model: str = "CLA-NAVI05-01",
    data_version: str = "DATA VERSION 11/06/27/01",
    mmain_count6: int = 1,
    bbox_lat_top: int = 1920,
    drstr_mmain_value: int | None = None,
    include_ver_info: bool = True,
    extra_artifact: bool = False,
) -> None:
    """Write a tiny but structurally valid ZE0-shaped card root."""
    root.mkdir(parents=True, exist_ok=True)
    (root / MAPAL_DIR).mkdir(exist_ok=True)
    tile = synth_tile(bbox_lat_top)
    lev = synth_tile(bbox_lat_top, size=0x500)
    (root / MAPAL_DIR / "B48R060R.DAT").write_bytes(tile)
    (root / MAPAL_DIR / "LEV3456R.DAT").write_bytes(lev)
    mmain = synth_mmain(count6=mmain_count6, model=model, data_version=data_version)
    (root / "MMAIN001.DAT").write_bytes(mmain)
    (root / "CMP.LST").write_bytes(CMP_LIST)
    if include_ver_info:
        (root / "VER_INFO").mkdir(exist_ok=True)
        (root / "VER_INFO" / "HDD_INFO.TXT").write_bytes(hdd)
    if extra_artifact:
        (root / "._CMP.LST").write_bytes(b"artifact")

    mmain_value = drstr_mmain_value if drstr_mmain_value is not None else len(mmain)
    entries_root = [
        ("MAPAL001", 2, len(tile) + len(lev)),
        ("MMAIN001.DAT", 0, mmain_value),
        ("DRSTR001.DAT", 0, 0),
        ("CMP.LST", 0, len(CMP_LIST)),
    ]
    if include_ver_info:
        entries_root.append(("VER_INFO", 2, len(hdd)))
    nodes = [
        {"name": "/", "parent": None, "entries": entries_root},
        {
            "name": "MAPAL001",
            "parent": 0,
            "entries": [
                ("B48R060R.DAT", 0, len(tile)),
                ("LEV3456R.DAT", 0, len(lev)),
            ],
        },
    ]
    if include_ver_info:
        nodes.append(
            {
                "name": "VER_INFO",
                "parent": 0,
                "entries": [("HDD_INFO.TXT", 0, len(hdd))],
            }
        )
    drstr_blob = synth_drstr(nodes)
    # The DRSTR size does not depend on its own value field, so a second pass
    # can store the real length.
    nodes[0]["entries"][2] = ("DRSTR001.DAT", 0, len(drstr_blob))
    (root / DRSTR_PATH).write_bytes(synth_drstr(nodes))


def _check(name: str, condition: bool, failures: list[str]) -> None:
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}")
        failures.append(name)


def selftest() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="diff-years-") as tmp:
        tmpdir = Path(tmp)
        base = tmpdir / "base"
        synthesize_root(base)

        def variant(name: str, **kwargs) -> Path:
            path = tmpdir / name
            synthesize_root(path, **kwargs)
            return path

        print("base vs copy")
        result = compare(base, base, assume="root")
        _check("identical roots report no differences", result["identical"], failures)
        tree = find_section(result, "tree")
        _check(
            "census counts files/dirs",
            tree["stats"]["a"]["files"] == 6 and tree["stats"]["a"]["dirs"] == 2,
            failures,
        )
        _check(
            "identical runs report every section as same",
            all(section["status"] == "same" for section in result["sections"]),
            failures,
        )

        print("HDD_INFO field difference")
        result = compare(base, variant("hdd", hdd=HDD_2014), assume="root")
        hdd = find_section(result, "hdd_info")
        _check("HDD line 2 difference detected", hdd["status"] == "different", failures)
        _check(
            "HDD diff names line 2",
            any("line 2" in message for message in hdd["diffs"]),
            failures,
        )
        _check(
            "HDD line 1 stays equal",
            not any("line 1:" in message for message in hdd["diffs"]),
            failures,
        )

        print("common header difference")
        result = compare(
            base,
            variant("header", data_version="DATA VERSION 14/03/01/01"),
            assume="root",
        )
        headers = find_section(result, "headers")
        _check("header data-version change detected", headers["status"] == "different", failures)
        _check(
            "header diff is reported for MMAIN",
            any("MMAIN001.DAT" in message for message in headers["diffs"]),
            failures,
        )

        print("common header 0x180 binary difference")
        binary_root = tmpdir / "binary"
        shutil.copytree(base, binary_root)
        blob = bytearray((binary_root / "MMAIN001.DAT").read_bytes())
        blob[0x190] ^= 0x01
        (binary_root / "MMAIN001.DAT").write_bytes(blob)
        result = compare(base, binary_root, assume="root")
        _check(
            "0x180 binary block change detected",
            find_section(result, "headers")["status"] == "different",
            failures,
        )
        _check(
            "0x180 diff is reported for MMAIN",
            any(
                "MMAIN001.DAT" in message and "0x180 block" in message
                for message in find_section(result, "headers")["diffs"]
            ),
            failures,
        )

        print("DRSTR entry value difference")
        result = compare(
            base,
            variant("drstr", drstr_mmain_value=0x0FFF),
            assume="root",
        )
        drstr_section = find_section(result, "drstr")
        _check("DRSTR change detected", drstr_section["status"] == "different", failures)
        _check(
            "DRSTR entry value is named",
            any("MMAIN001.DAT" in message for message in drstr_section["diffs"]),
            failures,
        )

        print("DRSTR leading u32 difference")
        lead_root = tmpdir / "lead"
        shutil.copytree(base, lead_root)
        blob = bytearray((lead_root / "DRSTR001.DAT").read_bytes())
        blob[0] = ord("0")
        (lead_root / "DRSTR001.DAT").write_bytes(blob)
        result = compare(base, lead_root, assume="root")
        _check(
            "leading u32 change detected",
            any(
                "leading u32" in message
                for message in find_section(result, "drstr")["diffs"]
            ),
            failures,
        )

        print("MMAIN level-table difference")
        result = compare(base, variant("mmain", mmain_count6=2), assume="root")
        mmain = find_section(result, "mmain")
        _check("MMAIN count change detected", mmain["status"] == "different", failures)
        _check(
            "MMAIN diff names section 1 level 6",
            any("section 1 level 6" in message for message in mmain["diffs"]),
            failures,
        )

        print("tile descriptor difference")
        result = compare(base, variant("tile", bbox_lat_top=1921), assume="root")
        tiles = find_section(result, "tiles")
        _check("tile 0x2ac difference detected", tiles["status"] == "different", failures)
        _check(
            "tile diff is reported for B48R060R 0x2ac",
            any("B48R060R" in message and "0x2ac" in message for message in tiles["diffs"]),
            failures,
        )

        print("same-size content change (hash only)")
        changed_cmp = tmpdir / "cmp"
        synthesize_root(changed_cmp)
        (changed_cmp / "CMP.LST").write_bytes(b"\\SystemSD\\REFER002\\")
        result = compare(base, changed_cmp, assume="root")
        _check("hash change detected", find_section(result, "hashes")["status"] == "different", failures)
        _check(
            "hash-only change leaves tree/headers/drstr/mmain/tiles same",
            all(
                find_section(result, sid)["status"] == "same"
                for sid in ("tree", "headers", "drstr", "mmain", "tiles")
            ),
            failures,
        )

        print("dump artifacts")
        artifact = variant("artifact", extra_artifact=True)
        result = compare(base, artifact, assume="root")
        _check("artifact file is a tree difference by default", find_section(result, "tree")["status"] == "different", failures)
        result = compare(base, artifact, assume="root", ignore_artifacts=True)
        _check("--ignore-dump-artifacts suppresses it", find_section(result, "tree")["status"] == "same", failures)

        print("partial tree (VER_INFO absent)")
        # A real map-only tree keeps the stale VER_INFO node in DRSTR while
        # the directory is missing, so copy the complete root and delete only
        # the directory.
        partial_root = tmpdir / "partial"
        shutil.copytree(base, partial_root)
        shutil.rmtree(partial_root / "VER_INFO")
        result = compare(base, partial_root, assume="root")
        _check(
            "without --partial, missing VER_INFO is a tree difference",
            find_section(result, "tree")["status"] == "different",
            failures,
        )
        _check(
            "without --partial, HDD_INFO absence is a difference",
            find_section(result, "hdd_info")["status"] == "different",
            failures,
        )
        result = compare(base, partial_root, assume="root", partial=True)
        tree = find_section(result, "tree")
        hdd = find_section(result, "hdd_info")
        _check("--partial keeps tree same", tree["status"] == "same", failures)
        _check(
            "--partial records suppressed VER_INFO paths",
            any("VER_INFO" in message for message in tree["suppressed"]),
            failures,
        )
        _check("--partial keeps HDD section same", hdd["status"] == "same", failures)
        _check(
            "--partial records the suppressed HDD absence",
            bool(hdd["suppressed"]),
            failures,
        )
        _check(
            "--partial does not hide unrelated tile differences",
            compare(base, variant("partial-tile", bbox_lat_top=1921),
                    assume="root", partial=True)["identical"] is False,
            failures,
        )

        print("no-hash mode")
        result = compare(base, base, assume="root", hashes=False)
        _check(
            "--no-hashes marks the hash section unavailable",
            find_section(result, "hashes")["status"] == "unavailable",
            failures,
        )

    total = len(failures)
    if total:
        print(f"selftest: FAILED ({total} check(s))")
        return 1
    print("selftest: PASS")
    return 0


# ---------------------------------------------------------------------------
# CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("a", nargs="?", help="first card root or image")
    parser.add_argument("b", nargs="?", help="second card root or image")
    parser.add_argument(
        "--assume",
        choices=("auto", "root", "image"),
        default="auto",
        help="source kind (default: auto; a directory is a root)",
    )
    parser.add_argument(
        "--image",
        action="store_true",
        help="force both inputs to be raw SD images (same as --assume image)",
    )
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument(
        "--max-diffs",
        type=int,
        default=40,
        help="human output cap per section (default: 40)",
    )
    parser.add_argument(
        "--partial",
        action="store_true",
        help="map-only trees: suppress differences caused by a missing VER_INFO",
    )
    parser.add_argument(
        "--ignore-dump-artifacts",
        action="store_true",
        help="ignore macOS ._*, .fseventsd, System Volume Information",
    )
    parser.add_argument(
        "--no-hashes",
        action="store_true",
        help="skip the SHA-256 file comparison",
    )
    parser.add_argument(
        "--hash-all",
        action="store_true",
        help="hash every common file, including size-mismatched ones",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="build two synthetic roots and verify detected/suppressed diffs",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return 0 if selftest() == 0 else 2
    if not args.a or not args.b:
        print("error: two card roots or images are required (or --selftest)",
              file=sys.stderr)
        return 2
    assume = "image" if args.image else args.assume
    try:
        result = compare(
            args.a,
            args.b,
            assume=assume,
            ignore_artifacts=args.ignore_dump_artifacts,
            partial=args.partial,
            hashes=not args.no_hashes,
            hash_all=args.hash_all,
        )
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_human(result, max_diffs=args.max_diffs))
    return 0 if result["identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
