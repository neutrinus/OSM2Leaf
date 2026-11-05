#!/usr/bin/env python3
"""Inspect the binary block at ``0x180`` of the common Clarion map header.

The first ``0x180`` bytes of most map files are UTF-16**BE** text; the next
128 bytes (``0x180``-``0x1ff``) are a **little-endian** binary block.  Only a
small part of that block is decoded: the twelve-byte common prefix, the
class-dependent area at ``0x18c``, the twelve ``0xff`` bytes at ``0x1a0`` and
the descriptor container at ``0x1ac``.  The rest is reported as ``unknown``
with an explicit TODO marker.

The tool is deliberately read-only and standard-library only.  It does not
claim field semantics that the repository has not verified.

Commands::

    python3 tools/header_block.py dump FILE
    python3 tools/header_block.py class FILE
    python3 tools/header_block.py compare FILE_A FILE_B
    python3 tools/header_block.py check FILE [FILE ...]
    python3 tools/header_block.py --selftest

Exit codes: ``0`` success/all known invariants pass, ``1`` a verified
structural invariant failed, ``2`` usage or I/O error (including a header
shorter than 512 bytes for commands that need the full header).
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


HEADER_SIZE = 512
TEXT_END = 0x180
BLOCK_OFFSET = 0x180
BLOCK_SIZE = 0x80
BLOCK_END = BLOCK_OFFSET + BLOCK_SIZE
COMMON_PREFIX = bytes.fromhex("ff ff 24 ff 12 c0 05 00 fb 50 0f f0")
CLASS_AREA_OFFSET = 0x18C
CLASS_AREA_LENGTH = 20
RESERVED_OFFSET = 0x1A0
RESERVED_BYTES = b"\xff" * 12
DESCRIPTOR_OFFSET = 0x1AC
DESCRIPTOR_REL = DESCRIPTOR_OFFSET - BLOCK_OFFSET
FILLER_UNIT = b"\xff\xff"

# The strings are UTF-16BE and padded with 0xffff.  The slot table is the
# verified layout from docs/format/file-header.md and C-010.
TEXT_SLOTS = (
    ("clarion", 0x000, 0x040, "CLARION", "exact"),
    ("vendor", 0x040, 0x080, "HITACHI", "exact"),
    ("model", 0x080, 0x0A0, "CLA-NAVI", "prefix"),
    ("format_version", 0x0A0, 0x0E0, "FORMAT VERSION ", "prefix"),
    ("data_version", 0x0E0, 0x160, "DATA VERSION ", "prefix"),
    ("software_version", 0x160, 0x180, "V", "prefix"),
)

# A documented exception to the all-0xffff padding: the bytes immediately
# before the 0x160 version slot are observed as 16 00 (file-header.md).
VERSION_PREFIX_OFFSET = 0x15E
VERSION_PREFIX = b"\x16\x00"

# Class signatures documented in docs/format/file-header.md.  They identify
# the *variant*; they do not identify REFER vs MMAIN, which are byte-identical
# in the documented header fields.
LANGUAGE_AREA = bytes.fromhex("05 04 02 07 0a 06 08 14")
FILL_AREA = b"\x3f" * 20
FILL_AREA_HEAD = b"\x3f" * 8
FILL_AREA_TAIL = b"\x3f" * 12

# Field regions used by the dump and JSON output.  ``status`` is deliberately
# coarse: VERIFIED means the bytes/layout were seen in the documented samples,
# not that the meaning is known.
FIELD_MAP = (
    {
        "name": "common_prefix",
        "offset": "0x180",
        "length": 12,
        "status": "VERIFIED (bytes); UNKNOWN (words)",
        "evidence": "MMAIN001.DAT, REFER002/COORD001.DAT, "
        "MAPAL001/B28R070R.DAT, RDSTM001/RDSTM001.DAT @ 0x180; C-011",
        "todo": "TODO: six little-endian u16 meanings are unknown",
    },
    {
        "name": "class_area",
        "offset": "0x18c",
        "length": 20,
        "status": "OBSERVED (bytes); HYPOTHESIS (codes)",
        "evidence": "MMAIN001.DAT @ 0x18c; REFER002/COORD001.DAT @ 0x18c; "
        "MAPAL001/B28R070R.DAT @ 0x18c; RDSTM001/RDSTM001.DAT @ 0x18c",
        "todo": "TODO: 0x18c-0x19f semantics are unknown",
    },
    {
        "name": "reserved_run",
        "offset": "0x1a0",
        "length": 12,
        "status": "OBSERVED",
        "evidence": "same four samples @ 0x1a0; file-header.md",
        "todo": "TODO: reserved/absent-marker hypothesis is untested",
    },
    {
        "name": "descriptor_container",
        "offset": "0x1ac",
        "length": 84,
        "status": "VERIFIED (structure); HYPOTHESIS (entry semantics)",
        "evidence": "C-052; MAPAL001/B28R070R.DAT @ 0x1ac; "
        "MMAIN001.DAT @ 0x1ac; RDSTM001/RDSTM001.DAT @ 0x1ac",
        "todo": "TODO: level/kind/count meanings are hypotheses",
    },
)

UNKNOWN_FIELDS = (
    {
        "offset": "0x180",
        "length": 2,
        "name": "prefix_word_0",
        "status": "UNKNOWN",
        "todo": "TODO: no evidence for this little-endian u16",
    },
    {
        "offset": "0x182",
        "length": 2,
        "name": "prefix_word_1",
        "status": "UNKNOWN",
        "todo": "TODO: no evidence for this little-endian u16",
    },
    {
        "offset": "0x184",
        "length": 2,
        "name": "prefix_word_2",
        "status": "UNKNOWN",
        "todo": "TODO: no evidence for this little-endian u16",
    },
    {
        "offset": "0x186",
        "length": 2,
        "name": "prefix_word_3",
        "status": "UNKNOWN",
        "todo": "TODO: no evidence for this little-endian u16",
    },
    {
        "offset": "0x188",
        "length": 2,
        "name": "prefix_word_4",
        "status": "UNKNOWN",
        "todo": "TODO: no evidence for this little-endian u16",
    },
    {
        "offset": "0x18a",
        "length": 2,
        "name": "prefix_word_5",
        "status": "UNKNOWN",
        "todo": "TODO: no evidence for this little-endian u16",
    },
    {
        "offset": "0x18c",
        "length": 8,
        "name": "class_code_list",
        "status": "UNKNOWN",
        "todo": "TODO: 'per-language code list' is a hypothesis (C-037)",
    },
    {
        "offset": "0x194",
        "length": 12,
        "name": "class_fill_run",
        "status": "UNKNOWN",
        "todo": "TODO: 0x3f run meaning is unknown",
    },
    {
        "offset": "0x1a0",
        "length": 12,
        "name": "reserved_run",
        "status": "UNKNOWN",
        "todo": "TODO: reserved/absent-marker hypothesis is untested",
    },
    {
        "offset": "0x1ac",
        "length": 84,
        "name": "descriptor_tail",
        "status": "UNKNOWN",
        "todo": "TODO: bytes after the parsed container are unmapped",
    },
)


class InputError(Exception):
    """I/O or input-size error that maps to exit code 2."""


@dataclass(frozen=True)
class TextField:
    name: str
    offset: int
    slot_end: int
    value: str
    expected: str
    match_kind: str
    terminator: str
    matched: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "offset": hex(self.offset),
            "slot_end": hex(self.slot_end),
            "value": self.value,
            "expected": self.expected,
            "match": self.match_kind,
            "matched": self.matched,
            "terminator": self.terminator,
        }


def _read_utf16be(blob: bytes, start: int, end: int) -> tuple[str, str]:
    """Read one 0xffff-terminated UTF-16BE field from ``start`` to ``end``.

    Returns ``(text, terminator)`` where terminator is ``ffff``, ``nontext``
    or ``slot_end``.  The caller supplies the slot bound because the real
    slots are only approximately regular.
    """
    chars: list[str] = []
    pos = start
    end = min(end, len(blob))
    while pos + 1 < end:
        unit = int.from_bytes(blob[pos : pos + 2], "big")
        if unit == 0xFFFF:
            return "".join(chars), "ffff"
        if unit == 0x0000 or unit < 0x20 or unit == 0x7F:
            return "".join(chars), "nontext"
        chars.append(chr(unit))
        pos += 2
    return "".join(chars), "slot_end"


def parse_text_fields(blob: bytes) -> list[TextField]:
    """Decode the six documented UTF-16BE header slots."""
    fields: list[TextField] = []
    for name, start, end, expected, match_kind in TEXT_SLOTS:
        value, terminator = _read_utf16be(blob, start, end)
        if match_kind == "exact":
            matched = value == expected
        else:
            matched = value.startswith(expected)
        fields.append(
            TextField(
                name=name,
                offset=start,
                slot_end=end,
                value=value,
                expected=expected,
                match_kind=match_kind,
                terminator=terminator,
                matched=matched,
            )
        )
    return fields


def family_from_text(fields: list[TextField]) -> tuple[str, str]:
    """Classify the Clarion header family from its UTF-16BE strings.

    The strings are common to all ZE0 *file variants*; only the model number
    separates the ZE0 and QY8x families.  The variant is reported separately
    by :func:`variant_from_block` / :func:`variant_from_name`.
    """
    values = {field.name: field.value for field in fields}
    if values.get("clarion") != "CLARION" or values.get("vendor") != "HITACHI":
        return "unknown", "CLARION/HITACHI magic missing"
    model = values.get("model", "")
    if model.startswith("CLA-NAVI05-01"):
        return "clarion-ze0", "model string is CLA-NAVI05-01"
    if model.startswith("CLA-NAVI06-01"):
        return "clarion-qy8x", "model string is CLA-NAVI06-01"
    if model.startswith("CLA-NAVI"):
        return "clarion-other", f"model string is {model!r}"
    return "unknown", f"model string is {model!r}"


def variant_from_block(blob: bytes) -> tuple[str, str]:
    """Return the documented file variant implied by the 0x180 block.

    ``MMAIN-OR-REFER`` is an honest result: those two classes have the same
    bytes in every documented header field, so a filename is still needed.
    """
    if len(blob) < BLOCK_END:
        return "unknown", "header shorter than 0x200"
    class_area = blob[CLASS_AREA_OFFSET : CLASS_AREA_OFFSET + CLASS_AREA_LENGTH]
    lead = blob[DESCRIPTOR_OFFSET : DESCRIPTOR_OFFSET + 2]
    if class_area == FILL_AREA:
        if lead == b"\x00\x02":
            return "MAPAL", "0x18c=0x3f*20 and 0x1ac starts 00 02"
        if lead == b"\x00\x01":
            return "RDSTM", "0x18c=0x3f*20 and 0x1ac starts 00 01"
        return "unknown", f"0x3f*20 class area but 0x1ac starts {lead.hex(' ')}"
    if (
        class_area[:8] == LANGUAGE_AREA
        and class_area[8:] == FILL_AREA_TAIL
    ):
        if lead == b"\x00\x03":
            return "MMAIN-OR-REFER", "language list and 0x1ac starts 00 03"
        return "unknown", f"language list but 0x1ac starts {lead.hex(' ')}"
    return "unknown", f"unrecognised class area {class_area.hex(' ')}"


def variant_from_name(name: str | None) -> tuple[str | None, str]:
    """Guess the archive variant from a path or filename.

    This is a *hint*, not header evidence.  It resolves REFER vs MMAIN, which
    the documented header bytes cannot distinguish.
    """
    if not name:
        return None, "no filename supplied"
    path = Path(name)
    upper_parts = [part.upper() for part in path.parts]
    leaf = upper_parts[-1]
    if leaf == "MMAIN001.DAT":
        return "MMAIN", "filename is MMAIN001.DAT"
    if leaf.startswith("RDSTM"):
        return "RDSTM", f"filename starts with RDSTM ({leaf})"
    if (
        len(leaf) >= 12
        and leaf.startswith("B")
        and leaf[3:4] == "R"
        and leaf.endswith("R.DAT")
    ) or leaf == "LEV3456R.DAT":
        return "MAPAL", f"tile filename {leaf}"
    if "REFER001" in upper_parts or "REFER002" in upper_parts:
        return "REFER", "path contains REFER001/REFER002"
    if leaf.startswith(
        (
            "ADDRE",
            "COORD",
            "POINT",
            "INTER",
            "FRWAY",
            "ICODE",
            "ZCODE",
            "ZIPFR",
            "ICADM",
        )
    ):
        return "REFER", f"REFER-family filename {leaf}"
    if leaf.startswith("BICON"):
        return "BICON", f"filename {leaf}"
    return None, f"unrecognised filename {leaf}"


def classify(blob: bytes, name: str | None = None) -> dict[str, Any]:
    """Combine the text signature, block signature and filename hint."""
    fields = parse_text_fields(blob)
    family, family_evidence = family_from_text(fields)
    block_variant, block_evidence = variant_from_block(blob)
    name_variant, name_evidence = variant_from_name(name)
    notes: list[str] = []

    if block_variant == "MMAIN-OR-REFER":
        if name_variant in ("MMAIN", "REFER"):
            value = name_variant
            source = "block signature + filename (REFER/MMAIN are ambiguous)"
        else:
            value = "AMBIGUOUS"
            source = "block signature; REFER and MMAIN are byte-identical here"
    elif block_variant in ("MAPAL", "RDSTM"):
        value = block_variant
        source = "block signature"
        if name_variant and name_variant != value:
            notes.append(
                f"filename hint {name_variant} disagrees with block {value}"
            )
    elif name_variant:
        value = name_variant
        source = "filename hint (block signature unrecognised)"
    else:
        value = "UNKNOWN"
        source = "no usable signature"

    return {
        "class": value,
        "candidates": (
            ["MMAIN", "REFER"] if value == "AMBIGUOUS" else []
        ),
        "class_source": source,
        "header_family": family,
        "family_evidence": family_evidence,
        "block_variant": block_variant,
        "block_evidence": block_evidence,
        "name_variant": name_variant,
        "name_evidence": name_evidence,
        "notes": notes,
    }


def parse_descriptor(blob: bytes) -> dict[str, Any]:
    """Parse the ``00 | n_tables | {table_id, n_entries, entries...}`` container.

    The container structure is verified for map tiles (C-052) and observed in
    the other documented samples.  Entry bytes are named ``level``, ``kind``
    and ``count`` because that is their documented shape; their meaning is a
    hypothesis.
    """
    block = blob[BLOCK_OFFSET:BLOCK_END]
    result: dict[str, Any] = {
        "offset": hex(DESCRIPTOR_OFFSET),
        "ok": False,
        "error": None,
        "lead": None,
        "n_tables": None,
        "tables": [],
        "consumed_bytes": 0,
        "terminator_offset": None,
        "terminator_byte": None,
        "semantics": "HYPOTHESIS",
        "todo": "TODO: level/kind/count meanings are not established",
    }
    if len(block) < DESCRIPTOR_REL + 2:
        result["error"] = "header ends before 0x1ac"
        return result
    result["lead"] = block[DESCRIPTOR_REL]
    result["n_tables"] = block[DESCRIPTOR_REL + 1]
    if result["lead"] != 0x00:
        result["error"] = f"lead byte is 0x{result['lead']:02x}, expected 0x00"
        return result
    if not 1 <= result["n_tables"] <= 16:
        result["error"] = (
            f"n_tables={result['n_tables']} is outside the structural range 1..16"
        )
        return result

    pos = DESCRIPTOR_REL + 2
    for _ in range(result["n_tables"]):
        if pos + 2 > len(block):
            result["error"] = "table header runs past the available header"
            return result
        table_id = block[pos]
        n_entries = block[pos + 1]
        table_offset = pos
        pos += 2
        if n_entries > (len(block) - pos) // 4:
            result["error"] = (
                f"table {table_id} declares {n_entries} entries that do not fit"
            )
            return result
        entries = []
        for _ in range(n_entries):
            level = block[pos]
            kind = block[pos + 1]
            count = struct.unpack_from("<H", block, pos + 2)[0]
            entries.append(
                {
                    "offset": hex(BLOCK_OFFSET + pos),
                    "level": level,
                    "kind": kind,
                    "count": count,
                }
            )
            pos += 4
        result["tables"].append(
            {
                "offset": hex(BLOCK_OFFSET + table_offset),
                "table_id": table_id,
                "n_entries": n_entries,
                "entries": entries,
            }
        )
    result["consumed_bytes"] = pos - DESCRIPTOR_REL
    if pos < len(block):
        result["terminator_offset"] = hex(BLOCK_OFFSET + pos)
        result["terminator_byte"] = block[pos]
    result["ok"] = True
    return result


def extract_ascii_runs(
    data: bytes, base: int = 0, min_len: int = 3
) -> list[dict[str, Any]]:
    """Return printable-ASCII runs at least ``min_len`` bytes long."""
    runs: list[dict[str, Any]] = []
    start: int | None = None
    for index, byte in enumerate(data):
        printable = 0x20 <= byte <= 0x7E
        if printable and start is None:
            start = index
        elif not printable and start is not None:
            if index - start >= min_len:
                runs.append(
                    {
                        "offset": hex(base + start),
                        "length": index - start,
                        "text": data[start:index].decode("ascii", "replace"),
                        "hex": data[start:index].hex(" "),
                    }
                )
            start = None
    if start is not None and len(data) - start >= min_len:
        runs.append(
            {
                "offset": hex(base + start),
                "length": len(data) - start,
                "text": data[start:].decode("ascii", "replace"),
                "hex": data[start:].hex(" "),
            }
        )
    return runs


def dump_block(blob: bytes) -> dict[str, Any]:
    """Dump the 0x180 block as little-endian u32/u16 grids plus ASCII runs."""
    block = blob[BLOCK_OFFSET:BLOCK_END]
    u32 = [
        struct.unpack_from("<I", block, offset)[0]
        for offset in range(0, len(block) - 3, 4)
    ]
    u16 = [
        struct.unpack_from("<H", block, offset)[0]
        for offset in range(0, len(block) - 1, 2)
    ]
    return {
        "offset": hex(BLOCK_OFFSET),
        "expected_length": BLOCK_SIZE,
        "length": len(block),
        "truncated": len(block) < BLOCK_SIZE,
        "hex": block.hex(" "),
        "u32": u32,
        "u16": u16,
        "ascii_runs": extract_ascii_runs(block, base=BLOCK_OFFSET),
    }


def _invariant(
    ident: str,
    status: str,
    passed: bool,
    detail: str,
    evidence: str,
) -> dict[str, Any]:
    return {
        "id": ident,
        "status": status,
        "result": "pass" if passed else ("fail" if status == "VERIFIED" else "warn"),
        "detail": detail,
        "evidence": evidence,
    }


def _text_padding_warnings(blob: bytes, fields: list[TextField]) -> list[str]:
    """Check the documented 0xffff padding, allowing the 0x15e exception."""
    warnings: list[str] = []
    for field in fields:
        start = field.offset + len(field.value) * 2
        end = field.slot_end
        if field.terminator == "ffff":
            start += 2
        for pos in range(start, min(end, len(blob)) - 1, 2):
            chunk = blob[pos : pos + 2]
            if pos == VERSION_PREFIX_OFFSET and chunk == VERSION_PREFIX:
                continue
            if chunk != FILLER_UNIT:
                warnings.append(
                    f"{field.name}: padding at 0x{pos:03x} is {chunk.hex(' ')}, "
                    "not ff ff"
                )
                break
    return warnings


def check_header(blob: bytes) -> dict[str, Any]:
    """Validate the structural invariants that are actually established."""
    fields = parse_text_fields(blob)
    by_name = {field.name: field for field in fields}
    invariants: list[dict[str, Any]] = []

    invariants.append(
        _invariant(
            "header-size",
            "VERIFIED",
            len(blob) >= HEADER_SIZE,
            f"{len(blob)} bytes available, need {HEADER_SIZE}",
            "C-010; docs/format/file-header.md",
        )
    )

    magic_checks = (
        ("magic-clarion", "clarion", "exact at 0x000"),
        ("magic-hitachi", "vendor", "exact at 0x040"),
        ("magic-model", "model", "prefix at 0x080"),
        ("magic-format", "format_version", "prefix at 0x0a0"),
        ("magic-data", "data_version", "prefix at 0x0e0"),
        ("magic-version", "software_version", "prefix at 0x160"),
    )
    for ident, field_name, expectation in magic_checks:
        field = by_name[field_name]
        invariants.append(
            _invariant(
                ident,
                "VERIFIED",
                field.matched,
                f"0x{field.offset:03x} {field.value!r}; expected {expectation} "
                f"{field.expected!r}",
                "C-010; MMAIN001.DAT, MAPAL001/*.DAT, RDSTM001.DAT, "
                "REFER001 decompressed payloads",
            )
        )

    terminators_ok = all(
        field.terminator in ("ffff", "slot_end") for field in fields
    )
    invariants.append(
        _invariant(
            "text-terminators",
            "VERIFIED",
            terminators_ok,
            "; ".join(
                f"{field.name}={field.terminator}" for field in fields
            ),
            "C-010; header slots are 0xffff-terminated UTF-16BE",
        )
    )

    prefix_ok = len(blob) >= BLOCK_OFFSET + len(COMMON_PREFIX) and (
        blob[BLOCK_OFFSET : BLOCK_OFFSET + len(COMMON_PREFIX)] == COMMON_PREFIX
    )
    invariants.append(
        _invariant(
            "block-prefix",
            "VERIFIED",
            prefix_ok,
            f"0x180 starts {blob[BLOCK_OFFSET:BLOCK_OFFSET + 12].hex(' ')}",
            "C-011; four documented samples @ 0x180",
        )
    )

    reserved_ok = (
        len(blob) >= RESERVED_OFFSET + len(RESERVED_BYTES)
        and blob[RESERVED_OFFSET : RESERVED_OFFSET + len(RESERVED_BYTES)]
        == RESERVED_BYTES
    )
    invariants.append(
        _invariant(
            "reserved-run",
            "OBSERVED",
            reserved_ok,
            "0x1a0-0x1ab is "
            + blob[RESERVED_OFFSET : RESERVED_OFFSET + 12].hex(" "),
            "file-header.md; MMAIN/COORD/MAPAL/RDSTM @ 0x1a0",
        )
    )

    descriptor = parse_descriptor(blob)
    descriptor_ok = descriptor["ok"] and (
        DESCRIPTOR_REL + descriptor["consumed_bytes"] <= BLOCK_SIZE
    )
    class_area = blob[CLASS_AREA_OFFSET : CLASS_AREA_OFFSET + CLASS_AREA_LENGTH]
    descriptor_status = "VERIFIED" if class_area == FILL_AREA else "OBSERVED"
    invariants.append(
        _invariant(
            "descriptor-container",
            descriptor_status,
            descriptor_ok,
            descriptor["error"] or (
                f"n_tables={descriptor['n_tables']}, "
                f"{descriptor['consumed_bytes']} bytes consumed"
            ),
            "C-052 (MAPAL/RDSTM); docs/format/map-tiles.md; "
            "MMAIN/REFER container is OBSERVED",
        )
    )

    block_ok = len(blob) >= BLOCK_END
    invariants.append(
        _invariant(
            "block-trailer",
            "VERIFIED",
            block_ok,
            f"binary block is {max(0, min(len(blob), BLOCK_END) - BLOCK_OFFSET)} "
            f"of {BLOCK_SIZE} bytes; header ends at 0x200",
            "docs/format/file-header.md",
        )
    )

    known_class_area = (
        blob[CLASS_AREA_OFFSET : CLASS_AREA_OFFSET + CLASS_AREA_LENGTH]
        in (FILL_AREA, LANGUAGE_AREA + FILL_AREA_TAIL)
    )
    invariants.append(
        _invariant(
            "class-area-pattern",
            "OBSERVED",
            len(blob) >= CLASS_AREA_OFFSET + CLASS_AREA_LENGTH
            and known_class_area,
            "0x18c-0x19f is "
            + blob[CLASS_AREA_OFFSET : CLASS_AREA_OFFSET + 20].hex(" "),
            "file-header.md; four documented samples @ 0x18c",
        )
    )

    warnings = _text_padding_warnings(blob, fields)
    failures = [item for item in invariants if item["result"] == "fail"]
    return {
        "ok": not failures,
        "exit_code": 1 if failures else 0,
        "invariants": invariants,
        "padding_warnings": warnings,
    }


def _header_report(blob: bytes, name: str | None = None) -> dict[str, Any]:
    report = classify(blob, name)
    report["header_size"] = len(blob)
    report["text_fields"] = [field.as_dict() for field in parse_text_fields(blob)]
    report["block"] = dump_block(blob)
    report["descriptor"] = parse_descriptor(blob)
    report["field_map"] = list(FIELD_MAP)
    report["unknown_fields"] = list(UNKNOWN_FIELDS)
    report["check"] = check_header(blob)
    return report


def compare_headers(blob_a: bytes, blob_b: bytes, name_a: str | None = None,
                    name_b: str | None = None) -> dict[str, Any]:
    """Compare two 512-byte headers byte by byte, grouped into runs."""
    class_a = classify(blob_a, name_a)
    class_b = classify(blob_b, name_b)
    fields_a = {f.name: f for f in parse_text_fields(blob_a)}
    fields_b = {f.name: f for f in parse_text_fields(blob_b)}
    text_differences = []
    for field_name in fields_a:
        value_a = fields_a[field_name].value
        value_b = fields_b[field_name].value
        if value_a != value_b:
            text_differences.append(
                {
                    "name": field_name,
                    "offset": hex(fields_a[field_name].offset),
                    "a": value_a,
                    "b": value_b,
                }
            )

    common = min(len(blob_a), len(blob_b), HEADER_SIZE)
    differing = [
        offset for offset in range(common) if blob_a[offset] != blob_b[offset]
    ]
    runs: list[dict[str, Any]] = []
    if differing:
        start = differing[0]
        previous = differing[0]
        for offset in differing[1:]:
            if offset == previous + 1:
                previous = offset
                continue
            runs.append(_diff_run(blob_a, blob_b, start, previous + 1))
            start = offset
            previous = offset
        runs.append(_diff_run(blob_a, blob_b, start, previous + 1))

    block_start = BLOCK_OFFSET
    block_diff = sum(1 for offset in differing if offset >= block_start)
    return {
        "class_a": class_a,
        "class_b": class_b,
        "text_differences": text_differences,
        "differing_bytes": len(differing),
        "differing_block_bytes": block_diff,
        "byte_runs": runs,
        "header_equal": len(differing) == 0 and len(blob_a) == len(blob_b),
        "block_equal": len(blob_a) >= BLOCK_END
        and len(blob_b) >= BLOCK_END
        and blob_a[BLOCK_OFFSET:BLOCK_END] == blob_b[BLOCK_OFFSET:BLOCK_END],
    }


def _diff_run(blob_a: bytes, blob_b: bytes, start: int, end: int) -> dict[str, Any]:
    return {
        "offset": hex(start),
        "end": hex(end),
        "length": end - start,
        "a": blob_a[start:end].hex(" "),
        "b": blob_b[start:end].hex(" "),
    }


def _load(path: str, require_full: bool = True) -> tuple[bytes, int]:
    """Read at most the 512-byte header; return ``(blob, file_size)``.

    Map tiles can be hundreds of megabytes and images several gigabytes, so
    the commands must never slurp the whole file just to inspect its header.
    """
    target = Path(path)
    try:
        with target.open("rb") as handle:
            blob = handle.read(HEADER_SIZE)
        size = target.stat().st_size
    except OSError as exc:
        raise InputError(f"{path}: {exc}") from exc
    if require_full and len(blob) < HEADER_SIZE:
        raise InputError(
            f"{path}: {len(blob)} bytes, shorter than the 512-byte header"
        )
    return blob, size


def _print_fields(report: dict[str, Any]) -> None:
    print("text fields (UTF-16BE):")
    for field in report["text_fields"]:
        mark = "ok" if field["matched"] else "MISMATCH"
        print(
            f"  {field['offset']}  {field['name']:<17s} "
            f"{field['value']!r:<32s} {mark}"
        )


def _print_block(block: dict[str, Any]) -> None:
    print(
        f"block {block['offset']}..0x1ff "
        f"({block['length']}/{block['expected_length']} bytes, little-endian):"
    )
    print("  u32 grid (8 per row):")
    for index in range(0, len(block["u32"]), 8):
        row = block["u32"][index : index + 8]
        values = " ".join(f"{value:08x}" for value in row)
        print(f"    0x{BLOCK_OFFSET + index * 4:03x}  {values}")
    print("  u16 grid (8 per row):")
    for index in range(0, len(block["u16"]), 8):
        row = block["u16"][index : index + 8]
        values = " ".join(f"{value:04x}" for value in row)
        print(f"    0x{BLOCK_OFFSET + index * 2:03x}  {values}")
    print("  ascii runs:")
    if not block["ascii_runs"]:
        print("    none")
    for run in block["ascii_runs"]:
        print(f"    {run['offset']} len={run['length']} {run['text']!r}")


def _print_descriptor(descriptor: dict[str, Any]) -> None:
    print(f"descriptor at {descriptor['offset']} (entry semantics HYPOTHESIS):")
    if not descriptor["ok"]:
        print(f"  ERROR {descriptor['error']}")
        return
    print(
        f"  lead=0x{descriptor['lead']:02x} "
        f"n_tables={descriptor['n_tables']} "
        f"consumed={descriptor['consumed_bytes']} bytes"
    )
    for table in descriptor["tables"]:
        print(
            f"  table @{table['offset']} id={table['table_id']} "
            f"entries={table['n_entries']}"
        )
        for entry in table["entries"]:
            print(
                f"    +{entry['offset']} level={entry['level']} "
                f"kind=0x{entry['kind']:02x} count={entry['count']}"
            )
    if descriptor["terminator_offset"]:
        print(
            f"  first byte after container: {descriptor['terminator_offset']} = "
            f"0x{descriptor['terminator_byte']:02x} (tail is UNKNOWN)"
        )


def _print_check(check: dict[str, Any]) -> None:
    print("invariants:")
    for item in check["invariants"]:
        print(f"  {item['result']:<4s} {item['id']:<22s} {item['detail']}")
        print(f"       status={item['status']} evidence={item['evidence']}")
    for warning in check["padding_warnings"]:
        print(f"  warn text-padding: {warning}")
    print(f"result: {'PASS' if check['ok'] else 'FAIL'} (exit {check['exit_code']})")


def cmd_dump(args: argparse.Namespace) -> int:
    blob, file_size = _load(args.file)
    report = _header_report(blob, args.file)
    report["file"] = args.file
    report["file_size"] = file_size
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    print(f"file       {args.file}")
    print(f"size       {file_size} bytes ({report['header_size']} read)")
    print(f"family     {report['header_family']} ({report['family_evidence']})")
    print(f"class      {report['class']} ({report['class_source']})")
    if report["candidates"]:
        print(f"candidates {', '.join(report['candidates'])}")
    for note in report["notes"]:
        print(f"note       {note}")
    _print_fields(report)
    _print_block(report["block"])
    _print_descriptor(report["descriptor"])
    print("field map:")
    for field in report["field_map"]:
        print(
            f"  {field['offset']} +{field['length']:<3d} {field['name']:<20s} "
            f"{field['status']}"
        )
    print("unknown fields:")
    for field in report["unknown_fields"]:
        print(
            f"  {field['offset']} +{field['length']:<3d} {field['name']:<20s} "
            f"{field['todo']}"
        )
    _print_check(report["check"])
    return 0


def cmd_class(args: argparse.Namespace) -> int:
    blob, _ = _load(args.file)
    result = classify(blob, args.file)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    print(f"file       {args.file}")
    print(f"family     {result['header_family']} ({result['family_evidence']})")
    print(f"class      {result['class']} ({result['class_source']})")
    print(f"block      {result['block_variant']} ({result['block_evidence']})")
    print(f"filename   {result['name_variant']} ({result['name_evidence']})")
    if result["candidates"]:
        print(f"candidates {', '.join(result['candidates'])}")
        print(
            "note       REFER/MMAIN share every documented header byte; "
            "the filename or payload is required"
        )
    for note in result["notes"]:
        print(f"note       {note}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    blob_a, _ = _load(args.file_a)
    blob_b, _ = _load(args.file_b)
    result = compare_headers(blob_a, blob_b, args.file_a, args.file_b)
    result["file_a"] = args.file_a
    result["file_b"] = args.file_b
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    print(f"A          {args.file_a} -> {result['class_a']['class']}")
    print(f"B          {args.file_b} -> {result['class_b']['class']}")
    print("text differences:")
    if not result["text_differences"]:
        print("  none")
    for difference in result["text_differences"]:
        print(
            f"  {difference['offset']} {difference['name']}: "
            f"{difference['a']!r} -> {difference['b']!r}"
        )
    print("byte runs:")
    if not result["byte_runs"]:
        print("  none")
    for run in result["byte_runs"]:
        print(f"  {run['offset']}..{run['end']} ({run['length']} bytes)")
        print(f"    A: {run['a']}")
        print(f"    B: {run['b']}")
    print(
        f"summary    {result['differing_bytes']}/{HEADER_SIZE} bytes differ "
        f"({result['differing_block_bytes']} in the 0x180 block)"
    )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    results = []
    overall = 0
    for path in args.files:
        try:
            blob, file_size = _load(path, require_full=False)
        except InputError as exc:
            print(f"error: {exc}", file=sys.stderr)
            overall = 2
            continue
        check = check_header(blob)
        results.append(
            {
                "file": path,
                "file_size": file_size,
                "header_size": len(blob),
                **check,
            }
        )
        if check["exit_code"]:
            overall = 1
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        for result in results:
            print(f"file       {result['file']}")
            print(
                f"size       {result['file_size']} bytes "
                f"({result['header_size']} read)"
            )
            _print_check(result)
            print()
    return overall


def _write_text(header: bytearray, offset: int, text: str, end: int) -> None:
    raw = text.encode("utf-16-be")
    if offset + len(raw) > end:
        raise ValueError(f"{text!r} does not fit in slot 0x{offset:03x}")
    header[offset : offset + len(raw)] = raw


def _descriptor_bytes(tables: list[tuple[int, list[tuple[int, int, int]]]]) -> bytes:
    raw = bytearray([0x00, len(tables)])
    for table_id, entries in tables:
        raw += bytes([table_id, len(entries)])
        for level, kind, count in entries:
            raw += bytes([level, kind]) + struct.pack("<H", count)
    raw += b"\x00"
    return bytes(raw)


def _synthetic_block(variant: str) -> bytes:
    block = bytearray(BLOCK_SIZE)
    block[: len(COMMON_PREFIX)] = COMMON_PREFIX
    if variant in ("MAPAL", "RDSTM"):
        block[CLASS_AREA_OFFSET - BLOCK_OFFSET : RESERVED_OFFSET - BLOCK_OFFSET] = (
            FILL_AREA
        )
    else:
        block[CLASS_AREA_OFFSET - BLOCK_OFFSET : RESERVED_OFFSET - BLOCK_OFFSET] = (
            LANGUAGE_AREA + FILL_AREA_TAIL
        )
    block[RESERVED_OFFSET - BLOCK_OFFSET : DESCRIPTOR_REL] = RESERVED_BYTES
    if variant == "MMAIN":
        descriptor = _descriptor_bytes(
            [
                (1, [(6, 0x80, 1), (5, 0x90, 1), (4, 0xA0, 1),
                     (3, 0xB0, 1), (2, 0xC0, 1), (1, 0xD0, 1)]),
                (2, [(2, 0x10, 0)]),
                (3, [(1, 0x20, 0)]),
            ]
        )
    elif variant == "REFER":
        descriptor = _descriptor_bytes(
            [
                (1, [(6, 0x80, 1), (5, 0x90, 1), (4, 0xA0, 1),
                     (3, 0xB0, 1), (2, 0xC0, 1), (1, 0xD0, 1)]),
                (2, [(2, 0x10, 0)]),
                (3, [(1, 0x20, 0)]),
            ]
        )
    elif variant == "MAPAL":
        descriptor = _descriptor_bytes(
            [
                (1, [(6, 0x80, 0), (5, 0x90, 0), (4, 0xA0, 0),
                     (3, 0xB0, 0), (2, 0xC0, 0), (1, 0xD0, 0)]),
                (2, [(2, 0x10, 0)]),
            ]
        )
    elif variant == "RDSTM":
        descriptor = _descriptor_bytes(
            [(3, [(4, 0xFF, 0xFFFF), (2, 0xFF, 0xFFFF)])]
        )
    else:
        raise ValueError(f"unknown synthetic variant {variant}")
    block[DESCRIPTOR_REL : DESCRIPTOR_REL + len(descriptor)] = descriptor
    return bytes(block)


def synth_header(variant: str, model: str = "CLA-NAVI05-01") -> bytes:
    """Build a synthetic 512-byte header for one documented class."""
    header = bytearray(b"\xff" * HEADER_SIZE)
    _write_text(header, 0x000, "CLARION", 0x040)
    _write_text(header, 0x040, "HITACHI", 0x080)
    _write_text(header, 0x080, model, 0x0A0)
    _write_text(header, 0x0A0, "FORMAT VERSION X08-02-00", 0x0E0)
    _write_text(header, 0x0E0, "DATA VERSION 11/06/27/01", 0x160)
    header[VERSION_PREFIX_OFFSET : VERSION_PREFIX_OFFSET + 2] = VERSION_PREFIX
    _write_text(header, 0x160, "V05.00.00", 0x180)
    header[BLOCK_OFFSET:BLOCK_END] = _synthetic_block(variant)
    return bytes(header)


def run_selftest() -> int:
    """Synthetic-only tests; no vendor data is read."""
    tests: list[tuple[str, bool, str]] = []

    def expect(name: str, condition: bool, detail: str = "") -> None:
        tests.append((name, bool(condition), detail))

    fixtures = {
        "MMAIN": (synth_header("MMAIN"), "MMAIN001.DAT"),
        "REFER": (synth_header("REFER"), "REFER002/COORD001.DAT"),
        "MAPAL": (synth_header("MAPAL"), "MAPAL001/B28R070R.DAT"),
        "RDSTM": (synth_header("RDSTM"), "RDSTM001/RDSTM001.DAT"),
    }

    for expected, (blob, name) in fixtures.items():
        result = classify(blob, name)
        expect(
            f"classify {expected} from text+block+name",
            result["class"] == expected,
            f"got {result['class']}",
        )
        expect(
            f"family {expected} is clarion-ze0 from UTF-16BE text",
            result["header_family"] == "clarion-ze0",
            result["family_evidence"],
        )
        expect(
            f"text fields {expected} match slots 0x000-0x180",
            all(field.matched for field in parse_text_fields(blob)),
            "; ".join(
                f"{field.name}={field.terminator}"
                for field in parse_text_fields(blob)
            ),
        )

    expect(
        "MAPAL class from block alone",
        classify(fixtures["MAPAL"][0])["class"] == "MAPAL",
    )
    expect(
        "RDSTM class from block alone",
        classify(fixtures["RDSTM"][0])["class"] == "RDSTM",
    )
    ambiguous = classify(fixtures["MMAIN"][0])
    expect(
        "REFER/MMAIN header alone is honestly ambiguous",
        ambiguous["class"] == "AMBIGUOUS"
        and ambiguous["candidates"] == ["MMAIN", "REFER"],
        ambiguous["class_source"],
    )
    expect(
        "MMAIN filename resolves the ambiguity",
        classify(fixtures["MMAIN"][0], "MMAIN001.DAT")["class"] == "MMAIN",
    )

    dump = dump_block(fixtures["MAPAL"][0])
    expect("dump u32 grid has 32 entries", len(dump["u32"]) == 32)
    expect("dump u16 grid has 64 entries", len(dump["u16"]) == 64)
    expect("dump starts at 0x180", dump["offset"] == "0x180")
    expect("dump covers 128 bytes", dump["length"] == 128)
    expect("first u32 is ff24ffff (little-endian bytes ff ff 24 ff)",
           dump["u32"][0] == 0xFF24FFFF)
    expect("first u16 is ffff", dump["u16"][0] == 0xFFFF)
    expect(
        "block ASCII run is the 0x3f class fill",
        len(dump["ascii_runs"]) == 1
        and dump["ascii_runs"][0]["offset"] == "0x18c"
        and dump["ascii_runs"][0]["text"] == "?" * 20,
        str(dump["ascii_runs"]),
    )

    runs = extract_ascii_runs(b"\x00\x00ABC\x01DE\x00", base=0x1000, min_len=2)
    expect("ASCII runs are offset and length correct", len(runs) == 2,
           str(runs))
    expect(
        "first ASCII run starts at 0x1002",
        runs and runs[0]["offset"] == "0x1002" and runs[0]["text"] == "ABC",
    )

    for expected, (blob, _) in fixtures.items():
        check = check_header(blob)
        expect(
            f"invariants pass for synthetic {expected}",
            check["exit_code"] == 0 and check["ok"],
            "; ".join(
                item["id"] for item in check["invariants"]
                if item["result"] == "fail"
            ),
        )

    bad_magic = bytearray(fixtures["MMAIN"][0])
    bad_magic[0x000:0x00E] = b"\x00" * 14
    bad_magic_check = check_header(bytes(bad_magic))
    expect(
        "wrong CLARION magic fails magic-clarion",
        bad_magic_check["exit_code"] == 1
        and any(
            item["id"] == "magic-clarion" and item["result"] == "fail"
            for item in bad_magic_check["invariants"]
        ),
    )

    truncated = check_header(fixtures["MMAIN"][0][:400])
    expect(
        "truncated 400-byte header fails header-size",
        truncated["exit_code"] == 1
        and any(
            item["id"] == "header-size" and item["result"] == "fail"
            for item in truncated["invariants"]
        ),
    )

    bad_prefix = bytearray(fixtures["MAPAL"][0])
    bad_prefix[BLOCK_OFFSET:BLOCK_OFFSET + 12] = b"\x00" * 12
    bad_prefix_check = check_header(bytes(bad_prefix))
    expect(
        "wrong 0x180 prefix fails block-prefix",
        bad_prefix_check["exit_code"] == 1
        and any(
            item["id"] == "block-prefix" and item["result"] == "fail"
            for item in bad_prefix_check["invariants"]
        ),
    )

    bad_descriptor = bytearray(fixtures["MAPAL"][0])
    bad_descriptor[DESCRIPTOR_OFFSET + 1] = 200
    bad_descriptor_check = check_header(bytes(bad_descriptor))
    expect(
        "wrong n_tables fails descriptor-container",
        bad_descriptor_check["exit_code"] == 1
        and any(
            item["id"] == "descriptor-container" and item["result"] == "fail"
            for item in bad_descriptor_check["invariants"]
        ),
    )

    report = _header_report(fixtures["MAPAL"][0], "MAPAL001/B28R070R.DAT")
    try:
        json.dumps(report, sort_keys=True)
        json_ok = True
    except (TypeError, ValueError):
        json_ok = False
    expect("header report is JSON-serialisable", json_ok)

    difference = compare_headers(
        fixtures["MAPAL"][0], fixtures["RDSTM"][0],
        "MAPAL001/B28R070R.DAT", "RDSTM001/RDSTM001.DAT",
    )
    expect("compare finds differing bytes", difference["differing_bytes"] > 0)
    expect(
        "compare classes are MAPAL and RDSTM",
        difference["class_a"]["class"] == "MAPAL"
        and difference["class_b"]["class"] == "RDSTM",
    )
    expect(
        "compare reports 0x1ad descriptor run",
        any(run["offset"] == "0x1ad" for run in difference["byte_runs"]),
        str(difference["byte_runs"]),
    )

    failed = 0
    for name, passed, detail in tests:
        print(f"  {'ok  ' if passed else 'FAIL'} {name}")
        if not passed:
            failed += 1
            if detail:
                print(f"       {detail}")
    print(f"header_block selftest: {len(tests) - failed}/{len(tests)} passed")
    if failed:
        print(f"header_block selftest: FAIL ({failed} failures)")
        return 1
    print("header_block selftest: OK")
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="emit machine-readable JSON",
    )
    parser = argparse.ArgumentParser(
        description="inspect the little-endian binary block at 0x180"
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="run synthetic self-tests (no vendor data needed)",
    )
    sub = parser.add_subparsers(dest="command")

    p_dump = sub.add_parser("dump", parents=[common], help="dump the 0x180 block")
    p_dump.add_argument("file")
    p_dump.set_defaults(func=cmd_dump)

    p_class = sub.add_parser(
        "class", parents=[common], help="detect the header family/class"
    )
    p_class.add_argument("file")
    p_class.set_defaults(func=cmd_class)

    p_compare = sub.add_parser(
        "compare", parents=[common], help="compare two 512-byte headers"
    )
    p_compare.add_argument("file_a")
    p_compare.add_argument("file_b")
    p_compare.set_defaults(func=cmd_compare)

    p_check = sub.add_parser(
        "check", parents=[common], help="validate known structural invariants"
    )
    p_check.add_argument("files", nargs="+")
    p_check.set_defaults(func=cmd_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.selftest:
        return run_selftest()
    if not getattr(args, "command", None):
        parser.error("a command or --selftest is required")
    try:
        return args.func(args)
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
