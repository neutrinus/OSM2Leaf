#!/usr/bin/env python3
"""Hypothesis harness for ``RDSTM001.DAT`` (Leaf ZE0) — standard library only.

This tool does **not** decode ``RDSTM001.DAT``.  It measures how well a
candidate record framing explains the bytes, how a candidate field layout
behaves as a graph (reciprocity / back references), and how well a 2-byte code
joins to ``LCTBL001.DAT``.  Every number it prints is a score or a count,
never a decoded field.

Evidence status (see ``docs/format/rdstm.md``):

* VERIFIED — 512-byte container header, negative zlib result, 2-byte codes
  shared with the LCTBL catalog;
* HYPOTHESIS — ``0x1000`` records, graph tuples below ``0x1a700``;
* UNKNOWN — field semantics, speed / one-way / turn restrictions.

Why a grid and a score: at ``0x10a0`` the row framing moves its 2-byte code
from ``+14`` to ``+4`` (C-106), so the record size is not established.  The
scanner tries a ``--block-size`` x ``--record-size`` grid and ranks the
framings by four measured properties:

``align``    one minus the mean per-column byte diversity; correct framing
             lines fields up and mixes fewer field values per byte column.
             The estimator is unbiased in the record count, so large record
             sizes cannot win by having fewer samples.
``small``    fraction of 16-bit slots ``<= --small-max`` (id-like values).
``pointer``  best fraction of records whose ``u32`` slot points inside the
             analysed window (absolute file offsets only).
``shape``    frequency of the modal "tuple shape": each 16-bit slot
             categorised as 0 (zero), 1 (small), 2 (mid) or 3 (high bit set).

``score = 0.30*align + 0.20*small + 0.25*pointer + 0.25*shape``.

A score cannot settle the "one record or two sub-records" ambiguity: if a
smaller record size scores within ``--tolerance`` of a larger multiple, the
larger one is flagged ``multiple_of``, its score is reduced by the same
tolerance and the primitive period ranks first.  ``score_raw`` in ``--json``
keeps the unpenalised value.

Sub-commands:

    scan     block/record grid; ranked table (``--json`` for machine output)
    layout   decode a user layout; graph reciprocity / back-reference checks
    join     2-byte code -> LCTBL001 catalog/name-index hit rate
    selftest synthetic RDSTM + LCTBL, no vendor data (also ``--selftest``)

Layout grammar (``--layout``)::

    NAME=OFF:TYPE[:ROLE][,OFF:TYPE[:ROLE]...]

``TYPE`` is ``u8``, ``u16``, ``u32``, ``u16le`` or ``u32le`` (big-endian is
the default, matching the documented u16 codes).  ``ROLE`` is optional and one
of ``id``, ``src``, ``dst``, ``ref``, ``code``, ``flag``; ``src``/``dst``
enable the graph checks, ``ref`` the pointer check and ``code`` the LCTBL
join.  A field may be labelled ``label@OFF:TYPE`` for readable output.

The record size defaults to the end of the last field, so a layout must cover
trailing padding too (add a role-less field) or ``--record-size`` must be
passed.  A layout that stops before the record end silently loses the
trailing bytes, so pass ``--record-size`` when in doubt.

Every sub-command reads a window from ``--start`` (default ``0x1000``) and
``--length`` (default ``0x10000``); ``--length 0`` means "to end of file".

Example::

    python3 tools/rdstm_schema.py scan RDSTM001.DAT --top 10
    python3 tools/rdstm_schema.py layout RDSTM001.DAT \
        --layout "link=0:u16:id,4:u32:ref,8:u16:src,10:u16:dst,12:u16:code" \
        --record-size 16 --lctbl LCTBL001.DAT
    python3 tools/rdstm_schema.py join RDSTM001.DAT --lctbl LCTBL001.DAT \
        --code-offset 0xe --code-type u16 --record-size 0x10
    python3 tools/rdstm_schema.py --selftest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import lctbl_names  # noqa: E402  (sibling tool, read-only import)
import rdstm_scan  # noqa: E402  (catalog code reader, read-only import)

HEADER_SIZE = 0x200
DEFAULT_START = 0x1000
DEFAULT_LENGTH = 0x10000
DEFAULT_BLOCK_SIZES = (0x400, 0x1000, 0x4000)
DEFAULT_RECORD_SIZES = (2, 4, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 64)
SMALL_MAX = 0xFF
MIN_RECORDS = 4
TYPE_WIDTH = {"u8": 1, "u16": 2, "u16le": 2, "u32": 4, "u32le": 4}
ROLES = ("id", "src", "dst", "ref", "code", "flag")
WEIGHTS = {"align": 0.30, "small": 0.20, "pointer": 0.25, "shape": 0.25}
SELFTEST_LAYOUT = (
    "link=0:u16:id,4:u32:ref,8:u16:src,10:u16:dst,12:u16:code,14:u16"
)
SELFTEST_RECORDS = 256
SELFTEST_NAMES = 32
SELFTEST_FIRST_CODE = 0x4A80


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def _int(text: str) -> int:
    return int(text, 0)


def _int_list(text: str) -> list[int]:
    values: list[int] = []
    for part in text.replace(" ", "").split(","):
        if part:
            values.append(int(part, 0))
    return values


def _flatten(chunks: list[list[int]] | None) -> list[int]:
    out: list[int] = []
    for chunk in chunks or []:
        out.extend(chunk)
    return out


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def byte_diversity(column: bytes) -> float:
    """Unbiased Gini-Simpson diversity of a byte column (0 = constant).

    A plain entropy estimate falls with the sample count, so a 16-record block
    would look more ordered than a 256-record one and large record sizes would
    win by sampling bias alone.  This estimator is unbiased in the sample
    count, which keeps columns comparable across the grid.
    """
    size = len(column)
    if size < 2:
        return 0.0
    counts = Counter(column)
    same = sum(n * (n - 1) for n in counts.values())
    return 1.0 - same / (size * (size - 1))


def percent(value: float) -> str:
    return f"{100.0 * value:5.1f}%"


# --------------------------------------------------------------------------
# framing scorer
# --------------------------------------------------------------------------


def slot_category(value: int, small_max: int = SMALL_MAX) -> int:
    if value == 0:
        return 0
    if value <= small_max:
        return 1
    if value < 0x8000:
        return 2
    return 3


def score_window(
    blob: bytes, record_size: int, base: int, small_max: int = SMALL_MAX
) -> dict | None:
    """Score one candidate record size over one window.

    ``base`` is the absolute file offset of ``blob``; the pointer check needs
    it because a pointer is only "pointer-like" when it points into the data
    that is actually present.
    """
    if record_size < 2 or record_size % 2:
        return None
    count = len(blob) // record_size
    if count < MIN_RECORDS:
        return None

    slots = record_size // 2
    rows: list[list[int]] = []
    for index in range(count):
        start = index * record_size
        rows.append(
            [
                int.from_bytes(blob[start + 2 * slot : start + 2 * slot + 2], "big")
                for slot in range(slots)
            ]
        )

    flat = [value for row in rows for value in row]
    small = sum(1 for value in flat if value <= small_max) / len(flat)

    shapes = Counter(
        tuple(slot_category(value, small_max) for value in row) for row in rows
    )
    modal = shapes.most_common(1)[0][1]
    shape = modal / count

    columns = [blob[column::record_size][:count] for column in range(record_size)]
    mean_diversity = sum(byte_diversity(column) for column in columns) / record_size
    align = 1.0 - mean_diversity

    low = base
    high = base + len(blob)
    best_fraction = 0.0
    best_offset: int | None = None
    for offset in range(0, record_size - 3, 2):
        hits = 0
        for index in range(count):
            start = index * record_size + offset
            value = int.from_bytes(blob[start : start + 4], "big")
            if low <= value < high:
                hits += 1
        fraction = hits / count
        if fraction > best_fraction:
            best_fraction, best_offset = fraction, offset

    best_run = 0
    if best_offset is not None and best_fraction > 0.0:
        run = 0
        for index in range(count):
            start = index * record_size + best_offset
            value = int.from_bytes(blob[start : start + 4], "big")
            if low <= value < high:
                run += 1
                best_run = max(best_run, run)
            else:
                run = 0

    score = (
        WEIGHTS["align"] * align
        + WEIGHTS["small"] * small
        + WEIGHTS["pointer"] * best_fraction
        + WEIGHTS["shape"] * shape
    )
    return {
        "record_size": record_size,
        "records": count,
        "slots": slots,
        "align": align,
        "small": small,
        "pointer": best_fraction,
        "pointer_offset": best_offset,
        "pointer_run": best_run,
        "shape": shape,
        "distinct_shapes": len(shapes),
        "score": score,
    }


def scan_grid(
    data: bytes,
    start: int,
    length: int,
    block_sizes: list[int],
    record_sizes: list[int],
    small_max: int = SMALL_MAX,
) -> list[dict]:
    """Average the window score per ``(block_size, record_size)`` pair."""
    end = len(data) if not length else min(len(data), start + length)
    rows: list[dict] = []
    for block_size in block_sizes:
        blocks: list[tuple[int, bytes]] = []
        offset = start
        while offset < end:
            stop = min(offset + block_size, end)
            blocks.append((offset, data[offset:stop]))
            offset = stop
        for record_size in record_sizes:
            parts = [
                score_window(blob, record_size, base, small_max)
                for base, blob in blocks
            ]
            parts = [part for part in parts if part]
            if not parts:
                continue
            row: dict = {
                "block_size": block_size,
                "record_size": record_size,
                "blocks": len(parts),
                "records": sum(part["records"] for part in parts),
                "pointer_offset": parts[0]["pointer_offset"],
                "pointer_run": max(part["pointer_run"] for part in parts),
                "distinct_shapes": max(part["distinct_shapes"] for part in parts),
            }
            for key in ("align", "small", "pointer", "shape", "score"):
                row[key] = sum(part[key] for part in parts) / len(parts)
            rows.append(row)
    return rows


def rank_rows(rows: list[dict], tolerance: float = 0.03) -> list[dict]:
    """Rank by score; a framing ``multiple_of`` a smaller period is penalised.

    The penalty equals ``--tolerance`` and is applied to the composite score,
    so a smaller (primitive) period always outranks a larger multiple that
    explains the same bytes.  ``score_raw`` keeps the unpenalised value.
    """
    for row in rows:
        multiples = [
            other
            for other in rows
            if other is not row
            and other["block_size"] == row["block_size"]
            and row["record_size"] % other["record_size"] == 0
            and other["score"] >= row["score"] - tolerance
        ]
        row["multiple_of"] = (
            min(multiples, key=lambda other: other["record_size"])["record_size"]
            if multiples
            else None
        )
    for row in rows:
        row["score_raw"] = row["score"]
        if row["multiple_of"]:
            row["score"] = row["score_raw"] - tolerance
    rows.sort(key=lambda row: (-row["score"], row["record_size"]))
    for position, row in enumerate(rows, 1):
        row["rank"] = position
    return rows


def print_scan(rows: list[dict]) -> None:
    header = (
        f"{'rank':>4} {'block':>7} {'record':>6} {'score':>6} {'align':>6} "
        f"{'small':>6} {'pointer':>7} {'run':>4} {'shape':>6} {'shapes':>6}  note"
    )
    print(header)
    for row in rows:
        note = ""
        if row.get("multiple_of"):
            note = f"multiple of {row['multiple_of']}"
        print(
            f"{row['rank']:>4} {row['block_size']:#7x} {row['record_size']:>6} "
            f"{row['score']:6.3f} {row['align']:6.3f} {row['small']:6.3f} "
            f"{row['pointer']:7.3f} {row['pointer_run']:>4} {row['shape']:6.3f} "
            f"{row['distinct_shapes']:>6}  {note}".rstrip()
        )


# --------------------------------------------------------------------------
# user layouts
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Field:
    offset: int
    type: str
    role: str = ""
    name: str = ""

    @property
    def width(self) -> int:
        return TYPE_WIDTH[self.type]

    @property
    def label(self) -> str:
        return self.name or f"f{self.offset:04x}"

    @property
    def little_endian(self) -> bool:
        return self.type.endswith("le")


def parse_layout(spec: str) -> tuple[str, list[Field], int]:
    if "=" not in spec:
        raise ValueError(f"layout {spec!r}: expected NAME=OFF:TYPE[,...]")
    name, body = spec.split("=", 1)
    name = name.strip()
    fields: list[Field] = []
    for token in body.split(","):
        token = token.strip()
        if not token:
            continue
        label = ""
        if "@" in token:
            label, token = token.split("@", 1)
        parts = token.split(":")
        if len(parts) not in (2, 3):
            raise ValueError(f"layout {spec!r}: field {token!r} is not OFF:TYPE[:ROLE]")
        offset = int(parts[0], 0)
        if offset < 0:
            raise ValueError(f"layout {spec!r}: negative offset {offset}")
        field_type = parts[1].lower()
        if field_type not in TYPE_WIDTH:
            raise ValueError(
                f"layout {spec!r}: unknown type {field_type!r} "
                f"(use {'/'.join(sorted(TYPE_WIDTH))})"
            )
        role = parts[2].lower() if len(parts) == 3 else ""
        if role and role not in ROLES:
            raise ValueError(f"layout {spec!r}: unknown role {role!r}")
        fields.append(Field(offset, field_type, role, label.strip()))
    if not fields:
        raise ValueError(f"layout {spec!r}: no fields")
    fields.sort(key=lambda field: field.offset)
    for first, second in zip(fields, fields[1:]):
        if second.offset < first.offset + first.width:
            raise ValueError(
                f"layout {spec!r}: fields at {first.offset:#x} and "
                f"{second.offset:#x} overlap"
            )
    record_size = max(field.offset + field.width for field in fields)
    if record_size % 2:
        record_size += 1
    return name, fields, record_size


def decode_field(blob: bytes, position: int, field: Field) -> int | None:
    raw = blob[position : position + field.width]
    if len(raw) < field.width:
        return None
    return int.from_bytes(raw, "little" if field.little_endian else "big")


def read_records(
    blob: bytes, base: int, fields: list[Field], record_size: int
) -> list[dict]:
    count = len(blob) // record_size
    records: list[dict] = []
    for index in range(count):
        start = index * record_size
        record: dict = {"_index": index, "_offset": base + start}
        for field in fields:
            record[field.label] = decode_field(blob, start + field.offset, field)
        records.append(record)
    return records


def field_stats(values: list[int], base: int, span: int) -> dict:
    present = [value for value in values if value is not None]
    if not present:
        return {"count": 0}
    return {
        "count": len(present),
        "min": min(present),
        "max": max(present),
        "distinct": len(set(present)),
        "small": sum(1 for value in present if value <= SMALL_MAX) / len(present),
        "pointer": sum(1 for value in present if base <= value < base + span)
        / len(present),
    }


def graph_checks(
    records: list[dict], fields: list[Field], record_size: int, base: int
) -> dict | None:
    """Reciprocity and back-reference checks for a ``src``/``dst`` layout."""
    by_role = {field.role: field for field in fields if field.role}
    if "src" not in by_role or "dst" not in by_role:
        return None
    src_field, dst_field = by_role["src"], by_role["dst"]
    nodes = len(records)
    edges: list[tuple[int, int]] = []
    out_of_range = 0
    self_loops = 0
    for record in records:
        src, dst = record[src_field.label], record[dst_field.label]
        if src is None or dst is None:
            continue
        if not (0 <= src < nodes and 0 <= dst < nodes):
            out_of_range += 1
            continue
        edges.append((src, dst))
        if src == dst:
            self_loops += 1

    edge_set = set(edges)
    reciprocal = sum(1 for src, dst in edges if (dst, src) in edge_set)
    sources = {src for src, _ in edges}
    targets = {dst for _, dst in edges}
    out_degree = Counter(src for src, _ in edges)
    in_degree = Counter(dst for _, dst in edges)
    return {
        "nodes": nodes,
        "edges": len(edges),
        "out_of_range": out_of_range,
        "self_loops": self_loops,
        "self_loop_rate": self_loops / len(edges) if edges else 0.0,
        "reciprocal_edges": reciprocal,
        "reciprocity": reciprocal / len(edges) if edges else 0.0,
        "distinct_sources": len(sources),
        "distinct_targets": len(targets),
        "node_coverage": len(sources | targets) / nodes if nodes else 0.0,
        "back_reference": len(targets & sources) / len(targets) if targets else 0.0,
        "mean_out_degree": len(edges) / len(sources) if sources else 0.0,
        "top_out_degree": out_degree.most_common(5),
        "top_in_degree": in_degree.most_common(5),
        "fields": [src_field.label, dst_field.label],
        "record_size": record_size,
        "base": base,
    }


# --------------------------------------------------------------------------
# LCTBL001 join probe
# --------------------------------------------------------------------------


def lctbl_index(lctbl_bytes: bytes, stream_start: int | None = None) -> dict:
    """Catalog codes + name-string prefixes + name records of ``LCTBL001``."""
    catalog = rdstm_scan.catalog_codes(lctbl_bytes)
    start = lctbl_names.FIRST_STREAM if stream_start is None else stream_start
    if stream_start is None and len(lctbl_bytes) <= start:
        # Small synthetic files do not reach the documented 0x316600 offset.
        start = 0x1000
    streams = lctbl_names.scan_streams(lctbl_bytes, start=start)
    plain = b"".join(stream["data"] for stream in streams)
    names = lctbl_names.extract_names(plain)
    prefixes = {int(name["prefix"], 16) for name in names if name["prefix"]}
    return {
        "catalog": catalog,
        "catalog_set": set(catalog),
        "stream_start": start,
        "streams": len(streams),
        "plain": len(plain),
        "names": len(names),
        "prefixes": prefixes,
    }


def join_probe(codes: list[int | None], index: dict) -> dict:
    """Hit rate of 2-byte codes against the LCTBL index code sets.

    A "hit" means the code occurs as a catalog descriptor code or as a 2-byte
    name-string prefix.  That is the only join the sample supports (C-105);
    the rate is a necessary condition, not proof of a name index.
    """
    values = [code for code in codes if code is not None]
    if not values:
        return {"occurrences": 0, "unique": 0, "index_hit": 0.0}
    unique = set(values)
    catalog = index["catalog_set"]
    prefixes = index["prefixes"]
    known = catalog | prefixes

    def rate(members: set[int]) -> tuple[float, float]:
        occurrence = sum(1 for code in values if code in members) / len(values)
        distinct = sum(1 for code in unique if code in members) / len(unique)
        return occurrence, distinct

    occurrence, distinct = rate(known)
    catalog_occurrence, catalog_distinct = rate(catalog)
    prefix_occurrence, prefix_distinct = rate(prefixes)
    return {
        "occurrences": len(values),
        "unique": len(unique),
        "index_hit": occurrence,
        "index_hit_unique": distinct,
        "catalog_hit": catalog_occurrence,
        "catalog_hit_unique": catalog_distinct,
        "prefix_hit": prefix_occurrence,
        "prefix_hit_unique": prefix_distinct,
        "lctbl_catalog_codes": len(catalog),
        "lctbl_prefixes": len(prefixes),
        "lctbl_names": index["names"],
    }


def print_join(probe: dict) -> None:
    print(
        f"codes          {probe['occurrences']} occurrences, "
        f"{probe['unique']} unique"
    )
    print(
        f"index hit      {percent(probe['index_hit'])} occurrences, "
        f"{percent(probe['index_hit_unique'])} unique"
    )
    print(
        f"  catalog      {percent(probe['catalog_hit'])} occurrences, "
        f"{percent(probe['catalog_hit_unique'])} unique "
        f"({probe['lctbl_catalog_codes']} catalog codes)"
    )
    print(
        f"  name prefix  {percent(probe['prefix_hit'])} occurrences, "
        f"{percent(probe['prefix_hit_unique'])} unique "
        f"({probe['lctbl_prefixes']} prefixes, {probe['lctbl_names']} names)"
    )


# --------------------------------------------------------------------------
# sub-commands
# --------------------------------------------------------------------------


def cmd_scan(args: argparse.Namespace) -> int:
    data = Path(args.file).read_bytes()
    if len(data) < HEADER_SIZE:
        print(f"error: {args.file} is shorter than the header", file=sys.stderr)
        return 1
    block_sizes = _flatten(args.block_size) or list(DEFAULT_BLOCK_SIZES)
    record_sizes = _flatten(args.record_size) or list(DEFAULT_RECORD_SIZES)
    rows = rank_rows(
        scan_grid(data, args.start, args.length, block_sizes, record_sizes, args.small_max),
        args.tolerance,
    )
    if not rows:
        print("error: no window had enough records to score", file=sys.stderr)
        return 1
    top = rows[: args.top] if args.top else rows

    if args.json:
        print(
            json.dumps(
                {
                    "file": str(args.file),
                    "size": len(data),
                    "sha256": sha256(data),
                    "start": args.start,
                    "length": args.length,
                    "block_sizes": block_sizes,
                    "record_sizes": record_sizes,
                    "weights": WEIGHTS,
                    "tolerance": args.tolerance,
                    "rows": top,
                },
                indent=1,
            )
        )
        return 0

    print(f"file           {args.file}")
    print(f"size           {len(data)}")
    print(f"sha256         {sha256(data)}")
    print(f"window         {args.start:#x} + {args.length:#x}")
    print(f"grid           blocks {len(block_sizes)} x records {len(record_sizes)}")
    print(f"tolerance      {args.tolerance:.2f} (multiple-of penalty)")
    print(
        "weights        "
        + " ".join(f"{key}={value:.2f}" for key, value in WEIGHTS.items())
    )
    print_scan(top)
    print(
        "note           scores rank hypotheses; 'multiple of N' marks a framing "
        "explained equally well by a smaller record size"
    )
    return 0


def cmd_layout(args: argparse.Namespace) -> int:
    data = Path(args.file).read_bytes()
    end = len(data) if not args.length else min(len(data), args.start + args.length)
    blob = data[args.start : end]
    if not blob:
        print("error: empty window", file=sys.stderr)
        return 1

    index = None
    if args.lctbl:
        index = lctbl_index(Path(args.lctbl).read_bytes(), args.stream_start)

    results = []
    for spec in args.layout:
        name, fields, record_size = parse_layout(spec)
        if args.record_size:
            record_size = args.record_size
        if record_size < max(field.offset + field.width for field in fields):
            print(
                f"error: --record-size {record_size:#x} is smaller than layout {name}",
                file=sys.stderr,
            )
            return 1
        records = read_records(blob, args.start, fields, record_size)
        entry: dict = {
            "layout": name,
            "spec": spec,
            "record_size": record_size,
            "start": args.start,
            "records": len(records),
            "fields": [],
        }
        for field in fields:
            stats = field_stats(
                [record[field.label] for record in records], args.start, len(blob)
            )
            entry["fields"].append(
                {"label": field.label, "role": field.role, "offset": field.offset,
                 "type": field.type, **stats}
            )

        graph = graph_checks(records, fields, record_size, args.start)
        entry["graph"] = graph

        probe = None
        code_fields = [field for field in fields if field.role == "code"]
        if index is not None and code_fields:
            probe = join_probe(
                [record[code_fields[0].label] for record in records], index
            )
        entry["join"] = probe

        results.append(entry)

        print(f"layout         {name}")
        print(f"spec           {spec}")
        print(
            f"record size    {record_size:#x}  records {len(records)}  "
            f"window {args.start:#x}+{len(blob):#x}"
        )
        print("fields")
        for field, row in zip(fields, entry["fields"]):
            if not row.get("count"):
                continue
            print(
                f"  {field.label:>10s} +{field.offset:#04x} {field.type:>5s} "
                f"{field.role or '-':>4s}  min {row['min']:#x} max {row['max']:#x} "
                f"distinct {row['distinct']} small {row['small']:.2f} "
                f"pointer {row['pointer']:.2f}"
            )
        if graph:
            print(
                f"graph          {graph['edges']} edges over {graph['nodes']} records, "
                f"{graph['out_of_range']} out of range"
            )
            print(
                f"  reciprocity  {percent(graph['reciprocity'])} "
                f"({graph['reciprocal_edges']} pairs)  "
                f"self loops {percent(graph['self_loop_rate'])}"
            )
            print(
                f"  targets      {graph['distinct_targets']} distinct, "
                f"back-reference {percent(graph['back_reference'])}  "
                f"node coverage {percent(graph['node_coverage'])}"
            )
        if probe:
            print_join(probe)
        if args.sample:
            print(f"sample ({args.sample} records)")
            for record in records[: args.sample]:
                body = " ".join(
                    f"{field.label}={record[field.label]}"
                    for field in fields
                    if record[field.label] is not None
                )
                print(f"  {record['_offset']:#08x}  {body}")

    if args.json:
        print(json.dumps(results, indent=1))
    return 0


def cmd_join(args: argparse.Namespace) -> int:
    data = Path(args.file).read_bytes()
    end = len(data) if not args.length else min(len(data), args.start + args.length)
    blob = data[args.start : end]

    if args.layout:
        name, fields, record_size = parse_layout(args.layout)
        code_fields = [field for field in fields if field.role == "code"]
        if not code_fields:
            print(
                f"error: layout {name} has no field with role 'code'",
                file=sys.stderr,
            )
            return 1
        if args.record_size:
            record_size = args.record_size
        records = read_records(blob, args.start, fields, record_size)
        codes = [record[code_fields[0].label] for record in records]
        description = f"layout {name} field {code_fields[0].label}"
    else:
        if args.code_offset is None:
            print(
                "error: pass --layout NAME=..., or --code-offset with --record-size",
                file=sys.stderr,
            )
            return 1
        record_size = args.record_size or 0x10
        field = Field(args.code_offset, args.code_type, "code")
        records = read_records(blob, args.start, [field], record_size)
        codes = [record[field.label] for record in records]
        description = f"offset {field.offset:#x} type {field.type}"

    index = lctbl_index(Path(args.lctbl).read_bytes(), args.stream_start)
    probe = join_probe(codes, index)

    if args.json:
        print(
            json.dumps(
                {
                    "file": str(args.file),
                    "lctbl": str(args.lctbl),
                    "code": description,
                    "record_size": record_size,
                    "start": args.start,
                    "records": len(records),
                    "index": {
                        "stream_start": index["stream_start"],
                        "streams": index["streams"],
                        "plain": index["plain"],
                        "names": index["names"],
                        "catalog_codes": len(index["catalog"]),
                        "prefixes": len(index["prefixes"]),
                    },
                    "probe": probe,
                },
                indent=1,
            )
        )
        return 0

    print(f"file           {args.file}")
    print(f"lctbl          {args.lctbl}")
    print(f"code           {description}")
    print(
        f"records        {len(records)} at {record_size:#x} from {args.start:#x}"
    )
    print(
        f"lctbl index    {index['streams']} streams, {index['plain']} plain bytes, "
        f"{index['names']} names"
    )
    print_join(probe)
    print(
        "note           'index hit' = code appears as a catalog code or a "
        "2-byte name prefix; necessary condition, not a decoded index"
    )
    return 0


# --------------------------------------------------------------------------
# synthetic self-test
# --------------------------------------------------------------------------


def build_synthetic_blob(count: int = SELFTEST_RECORDS) -> bytes:
    """A 0x1000 record table that follows ``SELFTEST_LAYOUT`` exactly."""
    header = bytearray(HEADER_SIZE)
    header[0:14] = "CLARION".encode("utf-16-be")
    body = bytearray(count * 16)
    for index in range(count):
        target = index + 1 if index % 2 == 0 else index - 1
        code = SELFTEST_FIRST_CODE + (index % SELFTEST_NAMES)
        record = struct.pack(
            ">HHIHHHH",
            index,  # id
            0,  # padding
            DEFAULT_START + index * 16,  # absolute pointer into this window
            index,  # src
            target,  # dst (reciprocal pairs)
            code,  # 2-byte code joined to LCTBL
            0,  # padding
        )
        body[index * 16 : (index + 1) * 16] = record
    return bytes(header) + bytes(DEFAULT_START - HEADER_SIZE) + bytes(body)


def build_synthetic_lctbl(count: int = SELFTEST_NAMES) -> bytes:
    """Catalog codes + one zlib stream of prefixed names, no vendor data."""
    blob = bytearray(HEADER_SIZE)
    blob[0:14] = "CLARION".encode("utf-16-be")
    blob += bytes(DEFAULT_START - len(blob))
    for index in range(count):
        code = SELFTEST_FIRST_CODE + index
        blob += (
            bytes(28)
            + struct.pack(">H", code)
            + struct.pack("<H", len(b"Location Data"))
            + b"Location Data"
        )
    blob += bytes(0x2000 - len(blob))
    plain = b"".join(
        bytes(16)
        + bytes([SELFTEST_FIRST_CODE >> 8, (SELFTEST_FIRST_CODE & 0xFF) + index])
        + b"Street%03d" % index
        + b"\x00"
        for index in range(count)
    )
    blob += zlib.compress(plain, 6)
    return bytes(blob)


def cmd_selftest(args: argparse.Namespace) -> int:
    failures: list[str] = []
    blob = build_synthetic_blob()
    lctbl_blob = build_synthetic_lctbl()
    print(
        f"synthetic RDSTM {len(blob)} bytes, sha256 {sha256(blob)}, "
        f"{SELFTEST_RECORDS} records of 16 bytes"
    )
    print(
        f"synthetic LCTBL {len(lctbl_blob)} bytes, sha256 {sha256(lctbl_blob)}, "
        f"{SELFTEST_NAMES} names"
    )

    rows = rank_rows(scan_grid(blob, DEFAULT_START, 0, list(DEFAULT_BLOCK_SIZES),
                               list(DEFAULT_RECORD_SIZES)))
    if not rows:
        failures.append("scan produced no rows")
    else:
        print("scan (top 6)")
        for row in rows[:6]:
            note = f" multiple of {row['multiple_of']}" if row["multiple_of"] else ""
            print(
                f"  {row['rank']:>2} block {row['block_size']:#06x} "
                f"record {row['record_size']:>3} score {row['score']:.3f} "
                f"align {row['align']:.3f} small {row['small']:.3f} "
                f"pointer {row['pointer']:.3f} shape {row['shape']:.3f}{note}"
            )
        top = rows[0]
        if top["record_size"] != 16:
            failures.append(
                f"scorer ranked record size {top['record_size']}, expected 16"
            )
        if not any(row["record_size"] == 32 and row["multiple_of"] == 16 for row in rows):
            failures.append("record size 32 was not flagged as a multiple of 16")
        print(
            f"  -> top record size {top['record_size']}, "
            f"score {top['score']:.3f}"
        )

    name, fields, record_size = parse_layout(SELFTEST_LAYOUT)
    window = blob[DEFAULT_START:]
    records = read_records(window, DEFAULT_START, fields, record_size)
    graph = graph_checks(records, fields, record_size, DEFAULT_START)
    assert graph is not None
    ref_field = next(field for field in fields if field.role == "ref")
    ref_pointer = field_stats(
        [record[ref_field.label] for record in records],
        DEFAULT_START,
        len(window),
    )["pointer"]
    print(
        f"layout {name}: {len(records)} records, "
        f"reciprocity {percent(graph['reciprocity'])}, "
        f"back-reference {percent(graph['back_reference'])}, "
        f"pointers {percent(ref_pointer)}"
    )
    if len(records) != SELFTEST_RECORDS:
        failures.append(f"decoded {len(records)} records, expected {SELFTEST_RECORDS}")
    if graph["out_of_range"]:
        failures.append(f"{graph['out_of_range']} graph tuples out of range")
    if graph["reciprocity"] < 0.99:
        failures.append(f"reciprocity {graph['reciprocity']:.3f} < 0.99")
    if ref_pointer < 0.99:
        failures.append(f"pointer rate {ref_pointer:.3f} < 0.99")

    index = lctbl_index(lctbl_blob)
    code_field = next(field for field in fields if field.role == "code")
    probe = join_probe([record[code_field.label] for record in records], index)
    print(
        f"join: {probe['occurrences']} codes, {probe['unique']} unique, "
        f"index hit {percent(probe['index_hit'])}, "
        f"catalog {percent(probe['catalog_hit'])}, "
        f"prefix {percent(probe['prefix_hit'])}"
    )
    if probe["index_hit"] < 1.0:
        failures.append(f"join index hit {probe['index_hit']:.3f} != 1.0")
    if probe["catalog_hit"] < 1.0 or probe["prefix_hit"] < 1.0:
        failures.append("catalog/prefix join component below 100%")

    for failure in failures:
        print(f"FAIL {failure}")
    print("selftest: OK" if not failures else "selftest: FAILED")
    return 0 if not failures else 1


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Hypothesis harness for RDSTM001.DAT (no vendor data needed)."
    )
    parser.add_argument(
        "--selftest", action="store_true", help="run the synthetic self-test and exit"
    )
    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan", help="rank record framings over a block grid")
    p_scan.add_argument("file")
    p_scan.add_argument("--start", type=_int, default=DEFAULT_START)
    p_scan.add_argument("--length", type=_int, default=DEFAULT_LENGTH)
    p_scan.add_argument(
        "--block-size", action="append", type=_int_list, metavar="LIST",
        help=f"comma list, repeatable (default {DEFAULT_BLOCK_SIZES})",
    )
    p_scan.add_argument(
        "--record-size", action="append", type=_int_list, metavar="LIST",
        help=f"comma list, repeatable (default {DEFAULT_RECORD_SIZES})",
    )
    p_scan.add_argument("--small-max", type=_int, default=SMALL_MAX)
    p_scan.add_argument("--top", type=int, default=12)
    p_scan.add_argument("--tolerance", type=float, default=0.03)
    p_scan.add_argument("--json", action="store_true")
    p_scan.set_defaults(func=cmd_scan)

    p_layout = sub.add_parser("layout", help="decode a layout and check the graph")
    p_layout.add_argument("file")
    p_layout.add_argument(
        "--layout", action="append", required=True, metavar="NAME=OFF:TYPE[:ROLE],...",
    )
    p_layout.add_argument("--start", type=_int, default=DEFAULT_START)
    p_layout.add_argument("--length", type=_int, default=DEFAULT_LENGTH)
    p_layout.add_argument("--record-size", type=_int, default=0)
    p_layout.add_argument("--lctbl", help="LCTBL001.DAT for the code join")
    p_layout.add_argument("--stream-start", type=_int, default=None)
    p_layout.add_argument("--sample", type=int, default=0)
    p_layout.add_argument("--json", action="store_true")
    p_layout.set_defaults(func=cmd_layout)

    p_join = sub.add_parser("join", help="2-byte code -> LCTBL001 hit rate")
    p_join.add_argument("file")
    p_join.add_argument("--lctbl", required=True)
    p_join.add_argument("--layout", help="layout with a field of role 'code'")
    p_join.add_argument("--code-offset", type=_int, default=None)
    p_join.add_argument("--code-type", default="u16", choices=sorted(TYPE_WIDTH))
    p_join.add_argument("--record-size", type=_int, default=0)
    p_join.add_argument("--start", type=_int, default=DEFAULT_START)
    p_join.add_argument("--length", type=_int, default=DEFAULT_LENGTH)
    p_join.add_argument("--stream-start", type=_int, default=None)
    p_join.add_argument("--json", action="store_true")
    p_join.set_defaults(func=cmd_join)

    p_self = sub.add_parser("selftest", help="synthetic checks, no vendor data")
    p_self.set_defaults(func=cmd_selftest)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return cmd_selftest(args)
    if not hasattr(args, "func"):
        build_parser().print_help()
        return 2
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
