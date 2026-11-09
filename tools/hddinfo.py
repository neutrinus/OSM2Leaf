#!/usr/bin/env python3
"""Parse ``VER_INFO/HDD_INFO.TXT`` and model the AppLaunch map checks (M2.15).

On-disk the block is six CRLF-separated ASCII lines (no trailing CRLF in the
factory 72-byte form); ``parse``/``to_bytes`` round-trip byte-identically,
including any bytes after the sixth line (``tail``).

The ``Navi.exe`` reader ``HDD_INFO_read`` at ``0x004e7b8c`` (build A,
C-1711/C-721–C-728) reads with ``fgetws``/``wcschr``/``wcsncpy`` into inline
wide-char fields (whole stripped line per field).  ``HDD_INFO_FIELDS`` is the
canonical line→field→type→struct-offset mapping (M2.3, C-740+).

The AppLaunch launcher checks (M2.5/M2.15, VERIFIED static, IMG256
``92aa525d…``) parse ``\\SystemSD\\VER_INFO\\HDD_INFO.TXT`` into 16-byte slots
cached at global ``0x01f74b30`` (slot 0 = line 1, slot 2 = line 3) and compare
against the NAND/system kernel target-info record from
``KernelIoControl(IOCTL 0x0101302C)``:

1. ``DIFFERENT MAP CODE`` (0x50, B ``fn 0x03bd2ad8`` / C ``0x03bb2858``): 11
   bytes, line 1 ``base_code`` slot 0 bytes 0-10 (file offset 0x00, len 11)
   vs target-info ``+0x60`` (+96), 11 bytes.
2. ``MAP DATA BASE UNMATCH`` (0x51, B ``fn 0x03bd2ce4`` / C ``0x03bb2a64``):
   line 3 ``build`` slot 2 positions 5,6,7 (0-based, file offsets 31-33 for the
   factory file) converted by B ``fn 0x03bd2a40`` (``0-9a-fA-F`` → 0-15,
   not-found → 0) to ``MapDBVer = ((d5*16)+d6)*16+d7``; must satisfy
   ``target[+112] <= MapDBVer <= target[+114]`` (16-bit BE bounds at
   target-info ``+0x70``/``+0x72``).

``classify`` models these checks offline.  Check 1 compares the SD card line 1
against a reference (``--target-line1`` or the ``sys`` HDD_INFO file's line 1,
a proxy for unit target-info +96).  Check 2 needs the unit bounds
(``--mapdbver-min``/``--mapdbver-max``); without them the extracted MapDBVer is
reported and the range verdict is ``BOUNDS_UNKNOWN`` (the bounds live in
kernel target-info, not in HDD_INFO).

Exit codes: 0 all evaluated checks pass, 1 a check fails (DIFFERENT MAP CODE or
MAP DATA BASE UNMATCH), 2 usage/parse/IO error.

Usage::

    python3 tools/hddinfo.py parse VER_INFO/HDD_INFO.TXT [--json]
    python3 tools/hddinfo.py classify SYS.TXT SD.TXT [--json]
                                     [--target-line1 CODE]
                                     [--mapdbver-min N] [--mapdbver-max N]
    python3 tools/hddinfo.py matrix BASE.TXT OUT_DIR [--sys SYS.TXT]
                                     [--sweep 0-5] [--no-permute] [--json]
    python3 tools/hddinfo.py --selftest [--json]

``matrix`` calls ``tools/hddinfo_variants.py`` and annotates each variant with
the M2.15 model (check 1 vs ``sys`` line 1; check 2 MapDBVer extracted, bounds
unknown unless ``--mapdbver-min``/``--mapdbver-max`` given).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

SIZE = 72


@dataclass(frozen=True)
class FieldDef:
    """One HDD_INFO field as read by ``HDD_INFO_read`` (C-1711/C-721+)."""

    line: int            # 1-based line number in HDD_INFO.TXT
    name: str            # semantic name used by this tool
    file_type: str       # on-disk representation
    mem_type: str        # in-memory representation (firmware)
    offset: int          # byte offset in output struct base r8
    max_wchars: int      # wcsncpy wchar_t count (firmware max)
    description: str


# Canonical line -> field -> type -> struct offset mapping (M2.3).
# Source: Navi.exe fn 0x004e7b8c (build A) reads 6 CRLF lines with fgetws
# (r15+0x40, 0x20 wchar_t), strips CR/LF via wcschr, wcsncpy's the whole
# stripped line into r8+offset with max_wchars. Accept check: len < max-1.
# EXP-2026-11-06-M2.1-hddinfo-fn-complete (C-721-C-728), C-1711.
HDD_INFO_FIELDS = (
    FieldDef(1, "base_code",   "ASCII text line (CRLF)", "wchar_t[] (UTF-16LE in memory)", 0x00, 12,
             "market/family base code, e.g. QSD-302-100"),
    FieldDef(2, "map_set",     "ASCII text line (CRLF)", "wchar_t[] (UTF-16LE in memory)", 0x18, 12,
             "map set code, tracks FAT volume label"),
    FieldDef(3, "build",       "ASCII text line (CRLF)", "wchar_t[] (UTF-16LE in memory)", 0x30, 13,
             "build/version string"),
    FieldDef(4, "map_code",    "ASCII text line (CRLF)", "wchar_t[] (UTF-16LE in memory)", 0x4a, 12,
             "manufacturer + destination token, e.g. SDC08-EVEUR"),
    FieldDef(5, "year_month",  "ASCII text line (CRLF)", "wchar_t[] (UTF-16LE in memory)", 0x62, 12,
             "map data year-month"),
    FieldDef(6, "part_number", "ASCII text line (CRLF)", "wchar_t[] (UTF-16LE in memory)", 0x7a, 13,
             "part number"),
)
HDD_INFO_FIELD_BY_NAME = {f.name: f for f in HDD_INFO_FIELDS}
HDD_INFO_FIELD_BY_OFFSET = {f.offset: f for f in HDD_INFO_FIELDS}

LINE_NAMES = tuple(f.name for f in HDD_INFO_FIELDS)

# --- M2.15 AppLaunch checks (VERIFIED static, IMG256 92aa525d…) ---
# Check 1: DIFFERENT MAP CODE (0x50), B fn 0x03bd2ad8 / C 0x03bb2858.
#   card: HDD_INFO line 1 slot 0 bytes 0-10 (11 bytes) vs unit target-info +0x60.
CHECK1_LINE = 1
CHECK1_LEN = 11
CHECK1_CODE = "DIFFERENT MAP CODE"
# Check 2: MAP DATA BASE UNMATCH (0x51), B fn 0x03bd2ce4 / C 0x03bb2a64.
#   card: line 3 slot 2 stripped positions 5,6,7 → 3 nibbles via fn 0x03bd2a40.
#   unit: target-info +112 (min, u16 BE) / +114 (max, u16 BE).
CHECK2_LINE = 3
CHECK2_POS = (5, 6, 7)  # 0-based within stripped line content
CHECK2_CODE = "MAP DATA BASE UNMATCH"
# fn 0x03bd2a40 lookup table: indices 0-9='0'-'9', 10-15='a'-'f', 16-21='A'-'F'
_CONV_TABLE = b"0123456789abcdefABCDEF"

# Legacy M0 identifiers retained for reference; classify uses the M2.15 model.
FIELD_ORDER = ("manufacturer_id", "userdata_type", "destination_id")
USERDATA_MIN, USERDATA_MAX = 0, 5
DESTINATION_IDS = {"EVEUR": 0x01}

MODEL_ID = "M2.15-AppLaunch"
MODEL_STATUS = "VERIFIED (static)"
MODEL_SOURCE = (
    "AppLaunch.dll B fn 0x03bd2ad8/0x03bd2ce4, C 0x03bb2858/0x03bb2a64 "
    "(EXP-2026-11-06-M2.5, EXP-2026-11-06-M2.15, C-760-C-769, C-2080-C-2089)"
)
MODEL_NOTE = (
    "check 1 vs reference line 1 (proxy for unit target-info +96); "
    "check 2 needs unit bounds --mapdbver-min/--mapdbver-max (target-info +112/+114)"
)

EXIT_OK, EXIT_DIFFERENT, EXIT_ERROR = 0, 1, 2
# M2.18 strict predictor: ACCEPT exit only when both checks pass against
# explicitly stated unit inputs (+0x60 target line 1, +112/+114 bounds).
# Any non-ACCEPT (including BOUNDS_UNKNOWN / failures) is non-zero so gates fail.
PREDICT_ACCEPT, PREDICT_NOT_ACCEPTED, PREDICT_ERROR = 0, 1, 2
PREDICT_VERDICTS = (
    "ACCEPT",
    CHECK1_CODE,
    CHECK2_CODE,
    "BOUNDS_UNKNOWN",
)


@dataclass
class HddInfo:
    """Six named lines plus the exact bytes that follow the sixth line."""

    lines: list[bytes]
    tail: bytes = b""

    @classmethod
    def parse(cls, raw: bytes) -> "HddInfo":
        parts = raw.split(b"\r\n", len(LINE_NAMES) - 1)
        if len(parts) < len(LINE_NAMES):
            raise ValueError(
                f"expected {len(LINE_NAMES)} CRLF-separated lines, found {len(parts)}"
            )
        *head, last = parts
        line6, sep, tail = last.partition(b"\r\n")
        return cls(list(head) + [line6], sep + tail)

    def to_bytes(self) -> bytes:
        return b"\r\n".join(self.lines) + self.tail

    @property
    def size(self) -> int:
        return len(self.to_bytes())

    def text(self, name: str) -> str:
        return self.lines[LINE_NAMES.index(name)].decode("latin-1")

    def with_line(self, name: str, value: bytes) -> "HddInfo":
        lines = list(self.lines)
        lines[LINE_NAMES.index(name)] = value
        return HddInfo(lines, self.tail)


@dataclass
class FieldRead:
    """One field as read from one side of the comparison (legacy M0 helper)."""

    raw: str | None
    value: int | None
    out_of_range: bool = False
    rule: str = ""


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_file(path: Path) -> bytes:
    return path.read_bytes()


def hexval(value: int | None) -> str:
    return "n/a" if value is None else "0x%04x" % value


def _conv_nibble(byte_val: int) -> int:
    """AppLaunch B fn 0x03bd2a40: '0'-'9a-fA-F' -> 0-15, not found -> 0."""
    idx = _CONV_TABLE.find(byte_val)
    if idx < 0:
        return 0
    if idx <= 15:
        return idx
    return idx - 6  # A-F at 16-21 -> 10-15


def line1_compare_bytes(record: HddInfo) -> bytes:
    """Check 1 card/unit field: line 1 slot 0 bytes 0-10 (11 bytes).

    The firmware copies 11 bytes from global parse slot 0 (line 1 stripped
    content). For a stripped line shorter than 11 bytes the remaining slot
    bytes are zero in the freshly-parsed path; we model that as zero-padding.
    """
    line = record.lines[CHECK1_LINE - 1]
    return (line[:CHECK1_LEN] + b"\x00" * CHECK1_LEN)[:CHECK1_LEN]


def _normalize_target_line1(value: bytes | str) -> bytes:
    if isinstance(value, str):
        value = value.encode("latin-1")
    return (value[:CHECK1_LEN] + b"\x00" * CHECK1_LEN)[:CHECK1_LEN]


def predict(
    sd_record: HddInfo,
    *,
    target_line1: bytes | str | None = None,
    target_line1_provenance: str | None = None,
    mapdbver_min: int | None = None,
    mapdbver_max: int | None = None,
) -> dict:
    """M2.18 strict offline acceptance predictor (pre-L3 gate, rule 13).

    Verdict is ``ACCEPT`` ONLY when check 1 is evaluated against an explicitly
    stated ``target_line1`` (unit target-info +0x60, 11 bytes, C-2081) AND check
    2 is evaluated against explicitly stated ``mapdbver_min``/``mapdbver_max``
    (unit +112/+114 u16 BE bounds, C-2084) AND both checks pass.

    If either unit input is not explicitly stated, the corresponding check is
    indeterminate and the overall verdict is ``BOUNDS_UNKNOWN`` (never
    ``ACCEPT``, never a pass verdict). A reference/sys line 1 is not sufficient
    for ``ACCEPT`` unless the caller passes it explicitly as ``target_line1``
    and provenance is recorded. Unit +0x60/+112/+114 values are unknown
    statically (C-2087); this is an offline model, not a firmware verdict
    (M9.6/M2.4 still required).
    """
    sd_l1 = line1_compare_bytes(sd_record)
    mv = extract_mapdbver(sd_record)
    bounds_both = mapdbver_min is not None and mapdbver_max is not None
    bounds_either = mapdbver_min is not None or mapdbver_max is not None

    check1: dict
    check1_pass: bool | None
    if target_line1 is None:
        check1_pass = None
        check1 = {
            "name": CHECK1_CODE,
            "error_code": "0x50",
            "verdict": "BOUNDS_UNKNOWN",
            "evaluated": False,
            "line": CHECK1_LINE,
            "file_offset": 0,
            "length": CHECK1_LEN,
            "sd_value": sd_record.text("base_code"),
            "sd_bytes_hex": sd_l1.hex(),
            "ref_bytes_hex": None,
            "ref_source": "NOT STATED (explicit --target-line1 required for ACCEPT)",
            "target_line1_provenance": target_line1_provenance or "not provided",
            "unit_source": "KernelIoControl(0x0101302C) output +0x60, 11 bytes",
            "va": "B fn 0x03bd2ad8 / C fn 0x03bb2858",
            "note": "unit +0x60 unknown statically (C-2087); never pass without explicit input",
        }
    else:
        ref_bytes = _normalize_target_line1(target_line1)
        check1_pass = sd_l1 == ref_bytes
        prov = target_line1_provenance or "explicit --target-line1 (caller-supplied proxy/input)"
        check1 = {
            "name": CHECK1_CODE,
            "error_code": "0x50",
            "verdict": "PASS" if check1_pass else CHECK1_CODE,
            "evaluated": True,
            "line": CHECK1_LINE,
            "file_offset": 0,
            "length": CHECK1_LEN,
            "sd_value": sd_record.text("base_code"),
            "sd_bytes_hex": sd_l1.hex(),
            "ref_bytes_hex": ref_bytes.hex(),
            "ref_source": "--target-line1 (explicit unit target-info +0x60 input/proxy)",
            "target_line1_provenance": prov,
            "unit_source": "KernelIoControl(0x0101302C) output +0x60, 11 bytes",
            "va": "B fn 0x03bd2ad8 / C fn 0x03bb2858",
        }

    check2: dict
    check2_pass: bool | None
    if not bounds_both:
        check2_pass = None
        check2 = {
            "name": CHECK2_CODE,
            "error_code": "0x51",
            "verdict": "BOUNDS_UNKNOWN",
            "evaluated": False,
            "mapdbver": mv,
            "bounds": {
                "min": mapdbver_min,
                "max": mapdbver_max,
                "known": False,
                "partial": bounds_either,
            },
            "range_check": "bounds unknown (explicit --mapdbver-min/--mapdbver-max required)",
            "unit_source": "KernelIoControl(0x0101302C) output +112(min)/+114(max), u16 BE",
            "va": "B fn 0x03bd2ce4 / C fn 0x03bb2a64",
            "note": "unit +112/+114 unknown statically (C-2087); never pass without explicit bounds",
        }
    else:
        check2_pass = mapdbver_min <= mv["value"] <= mapdbver_max
        check2 = {
            "name": CHECK2_CODE,
            "error_code": "0x51",
            "verdict": "PASS" if check2_pass else CHECK2_CODE,
            "evaluated": True,
            "mapdbver": mv,
            "bounds": {"min": mapdbver_min, "max": mapdbver_max, "known": True},
            "range_check": "%d <= %d <= %d" % (mapdbver_min, mv["value"], mapdbver_max),
            "unit_source": "KernelIoControl(0x0101302C) output +112(min)/+114(max), u16 BE",
            "va": "B fn 0x03bd2ce4 / C fn 0x03bb2a64",
        }

    failures = []
    unknowns = []
    if check1_pass is False:
        failures.append(CHECK1_CODE)
    elif check1_pass is None:
        unknowns.append(CHECK1_CODE)
    if check2_pass is False:
        failures.append(CHECK2_CODE)
    elif check2_pass is None:
        unknowns.append(CHECK2_CODE)

    accepted = check1_pass is True and check2_pass is True
    if failures:
        verdict = failures[0]
    elif unknowns:
        verdict = "BOUNDS_UNKNOWN"
    else:
        verdict = "ACCEPT"

    reasons = []
    if check1_pass is False:
        reasons.append("%s: SD line1 %r != explicit target %r" % (
            CHECK1_CODE, check1["sd_value"],
            _normalize_target_line1(target_line1).decode("latin-1", "replace").rstrip("\x00")))
    if check1_pass is None:
        reasons.append("%s: explicit --target-line1 not stated (C-2087)" % CHECK1_CODE)
    if check2_pass is False:
        reasons.append("%s: %s" % (CHECK2_CODE, check2["range_check"]))
    if check2_pass is None:
        reasons.append("%s: explicit --mapdbver-min/--mapdbver-max not stated (C-2087)" % CHECK2_CODE)

    return {
        "model": MODEL_ID,
        "model_status": MODEL_STATUS,
        "predictor": "M2.18-strict",
        "predictor_note": (
            "Offline pre-L3 gate (rule 13). ACCEPT only when both checks pass "
            "against explicitly stated unit inputs (+0x60 target, +112/+114 bounds). "
            "Unknown inputs => BOUNDS_UNKNOWN, never ACCEPT. Firmware verdicts "
            "still require M9.6/M2.4."
        ),
        "verdict": verdict,
        "accepted": accepted,
        "no_proven_failure": False,
        "exit_code": PREDICT_ACCEPT if accepted else PREDICT_NOT_ACCEPTED,
        "check1_different_map_code": check1,
        "check2_map_data_base_unmatch": check2,
        "failures": failures,
        "unknowns": unknowns,
        "reasons": reasons,
    }


def extract_mapdbver(record: HddInfo) -> dict:
    """Check 2 card field (B fn 0x03bd2ce4, C 0x03bb2a64): line 3 pos 5,6,7.

    Returns the 3 source chars (or None per position if the line is short),
    their nibble values and the combined ``MapDBVer = ((d5*16)+d6)*16+d7``.
    """
    line = record.lines[CHECK2_LINE - 1]
    chars, nibbles = [], []
    for pos in CHECK2_POS:
        if pos < len(line):
            b = line[pos]
            chars.append(chr(b) if 32 <= b < 127 else "\\x%02x" % b)
            nibbles.append(_conv_nibble(b))
        else:
            chars.append(None)
            nibbles.append(_conv_nibble(0))
    value = ((nibbles[0] * 16) + nibbles[1]) * 16 + nibbles[2]
    # file offset of line 3 start (sum of prior lines + CRLFs)
    l3_file_off = sum(len(record.lines[i]) + 2 for i in range(CHECK2_LINE - 1))
    return {
        "line": CHECK2_LINE,
        "line_name": "build",
        "slot": 2,
        "positions": list(CHECK2_POS),
        "file_offsets": [l3_file_off + p for p in CHECK2_POS],
        "chars": chars,
        "nibbles": nibbles,
        "value": value,
        "hex": "0x%03x" % value,
        "source": "B fn 0x03bd2ce4 0x03bd2e3a-0x03bd2e68 (C 0x03bb2a64 0x03bb2bba)",
    }


def model_fields(record: HddInfo) -> dict[str, FieldRead]:
    """Legacy M0 derivations from lines 1/4 (HYPOTHESIS, retained for reference)."""
    base = record.text("base_code")
    code = record.text("map_code")

    family = re.search(r"\d+", base)
    if family:
        token = family.group(0)
        value = int(token[0])
        userdata = FieldRead(
            token,
            value,
            not (USERDATA_MIN <= value <= USERDATA_MAX),
            "leading digit of the first number on line 1",
        )
    else:
        userdata = FieldRead(None, None, False, "no number on line 1")

    prefix, sep, suffix = code.partition("-")
    digits = re.search(r"\d+", prefix)
    if digits:
        manufacturer = FieldRead(
            digits.group(0),
            int(digits.group(0)) & 0xFFFF,
            False,
            "digits of the line-4 prefix",
        )
    else:
        manufacturer = FieldRead(None, None, False, "no digits in the line-4 prefix")

    if sep and suffix:
        destination = FieldRead(
            suffix,
            DESTINATION_IDS.get(suffix),
            False,
            "line-4 suffix, model-local token table",
        )
    else:
        destination = FieldRead(None, None, False, "no line-4 suffix")

    return {
        "manufacturer_id": manufacturer,
        "userdata_type": userdata,
        "destination_id": destination,
    }


def classify(
    sys_record: HddInfo,
    sd_record: HddInfo,
    *,
    target_line1: bytes | str | None = None,
    mapdbver_min: int | None = None,
    mapdbver_max: int | None = None,
) -> dict:
    """Model the two AppLaunch launcher checks (M2.15, VERIFIED static).

    Check 1 compares SD line 1 bytes 0-10 against ``target_line1`` or, if not
    given, the ``sys_record`` line 1 (offline proxy for unit target-info +96).
    Check 2 range-checks SD MapDBVer (line 3 pos 5,6,7) against the unit
    bounds; without bounds the value is reported as ``BOUNDS_UNKNOWN``.

    M2.18 note: this M2.15 model may report "no proven failure" when bounds are
    unknown. For an L2 pre-gate that never emits a pass without explicit unit
    inputs, use ``predict()`` / the ``predict`` subcommand.
    """
    ref = target_line1
    if ref is None:
        ref_bytes = line1_compare_bytes(sys_record)
        ref_src = "sys line 1 (proxy for unit target-info +0x60)"
    else:
        if isinstance(ref, str):
            ref = ref.encode("latin-1")
        ref_bytes = (ref[:CHECK1_LEN] + b"\x00" * CHECK1_LEN)[:CHECK1_LEN]
        ref_src = "--target-line1 (unit target-info +0x60)"

    sd_l1 = line1_compare_bytes(sd_record)
    c1_pass = sd_l1 == ref_bytes
    check1 = {
        "name": CHECK1_CODE,
        "error_code": "0x50",
        "verdict": "PASS" if c1_pass else CHECK1_CODE,
        "line": CHECK1_LINE,
        "file_offset": 0,
        "length": CHECK1_LEN,
        "sd_value": sd_record.text("base_code"),
        "sd_bytes_hex": sd_l1.hex(),
        "ref_bytes_hex": ref_bytes.hex(),
        "ref_source": ref_src,
        "unit_source": "KernelIoControl(0x0101302C) output +0x60, 11 bytes",
        "va": "B fn 0x03bd2ad8 / C fn 0x03bb2858",
    }

    mv = extract_mapdbver(sd_record)
    if mapdbver_min is not None and mapdbver_max is not None:
        c2_pass = mapdbver_min <= mv["value"] <= mapdbver_max
        c2_verdict = "PASS" if c2_pass else CHECK2_CODE
        bounds = {"min": mapdbver_min, "max": mapdbver_max, "known": True}
    else:
        c2_pass = None
        c2_verdict = "BOUNDS_UNKNOWN"
        bounds = {"min": mapdbver_min, "max": mapdbver_max, "known": False}
    check2 = {
        "name": CHECK2_CODE,
        "error_code": "0x51",
        "verdict": c2_verdict,
        "mapdbver": mv,
        "bounds": bounds,
        "range_check": "%d <= %d <= %d" % (mapdbver_min, mv["value"], mapdbver_max)
        if bounds["known"]
        else "bounds unknown (unit target-info +112/+114 required)",
        "unit_source": "KernelIoControl(0x0101302C) output +112(min)/+114(max), u16 BE",
        "va": "B fn 0x03bd2ce4 / C fn 0x03bb2a64",
    }

    # AppLaunch router evaluates both checks (dispatches per failure).
    failures = []
    if not c1_pass:
        failures.append(CHECK1_CODE)
    if c2_pass is False:
        failures.append(CHECK2_CODE)
    accepted = c1_pass and c2_pass is True
    no_proven_failure = c1_pass and c2_pass is not False
    overall = failures[0] if failures else ("ACCEPT" if c2_pass is True else "ACCEPT (check1); check2 BOUNDS_UNKNOWN")

    return {
        "model": MODEL_ID,
        "model_status": MODEL_STATUS,
        "model_note": MODEL_NOTE,
        "verdict": overall,
        "accepted": accepted,
        "no_proven_failure": no_proven_failure,
        "check1_different_map_code": check1,
        "check2_map_data_base_unmatch": check2,
        "failures": failures,
        "reasons": [
            "%s: SD line1 %r vs ref %r" % (CHECK1_CODE, check1["sd_value"], ref_bytes.decode("latin-1", "replace").rstrip("\x00"))
        ] * (0 if c1_pass else 1)
        + (["%s: %s" % (CHECK2_CODE, check2["range_check"])] if c2_pass is False else []),
    }


def field_layout_json() -> list[dict]:
    return [
        {
            "line": f.line,
            "name": f.name,
            "file_type": f.file_type,
            "mem_type": f.mem_type,
            "struct_offset": "0x%02x" % f.offset,
            "struct_offset_bytes": f.offset,
            "max_wchars": f.max_wchars,
            "description": f.description,
        }
        for f in HDD_INFO_FIELDS
    ]


def record_json(record: HddInfo, path: Path, raw: bytes) -> dict:
    return {
        "path": str(path),
        "size": record.size,
        "size_ok": record.size == SIZE,
        "sha256": sha256(raw),
        "lines": {name: record.text(name) for name in LINE_NAMES},
        "tail_hex": record.tail.hex(),
        "field_layout": field_layout_json(),
        "check1_line1_bytes0_10": line1_compare_bytes(record).hex(),
        "check2_mapdbver": extract_mapdbver(record),
        "legacy_m0_fields": {
            name: {
                "raw": read.raw,
                "value": read.value,
                "hex": hexval(read.value),
                "out_of_range": read.out_of_range,
                "rule": read.rule,
            }
            for name, read in model_fields(record).items()
        },
    }


def format_record(record: HddInfo, path: Path, raw: bytes) -> str:
    out = [
        "%s  %d bytes%s" % (
            path,
            record.size,
            "" if record.size == SIZE else "  (expected %d)" % SIZE,
        ),
        "  sha256       %s" % sha256(raw),
    ]
    for f in HDD_INFO_FIELDS:
        out.append(
            "  L%d %-12s r8+0x%02x max=%-2d  %r"
            % (f.line, f.name, f.offset, f.max_wchars, record.text(f.name))
        )
    out.append("  %-12s %s" % ("tail", record.tail.hex() if record.tail else "(none)"))
    out.append("  mapping      Navi.exe fn 0x004e7b8c (C-1711/C-721+): 6 CRLF lines, fgetws/wcschr/wcsncpy")
    l1 = line1_compare_bytes(record)
    out.append("  check1 (0x50) L1 bytes 0-10  %s  %r" % (l1.hex(), record.text("base_code")))
    mv = extract_mapdbver(record)
    out.append(
        "  check2 (0x51) L3 pos %s chars=%s  MapDBVer=%s (%d)  file_off=%s"
        % (mv["positions"], mv["chars"], mv["hex"], mv["value"], mv["file_offsets"])
    )
    return "\n".join(out)


def format_classification(result: dict, sys_name: str, sd_name: str) -> str:
    out = [
        "model %s (%s): ref=%s  SD=%s"
        % (MODEL_ID, MODEL_STATUS, sys_name, sd_name)
    ]
    c1 = result["check1_different_map_code"]
    out.append(
        "  check1 %-22s %s  L1=%r  sd=%s ref=%s (%s)"
        % (CHECK1_CODE, c1["verdict"], c1["sd_value"], c1["sd_bytes_hex"], c1["ref_bytes_hex"], c1["ref_source"])
    )
    c2 = result["check2_map_data_base_unmatch"]
    mv = c2["mapdbver"]
    out.append(
        "  check2 %-22s %s  L3 pos%s %s -> %s (%d)  %s"
        % (CHECK2_CODE, c2["verdict"], mv["positions"], mv["chars"], mv["hex"], mv["value"], c2["range_check"])
    )
    out.append("verdict: %s" % result["verdict"])
    for reason in result["reasons"]:
        out.append("  ! %s" % reason)
    return "\n".join(out)


def short_line(value: bytes, limit: int = 32) -> str:
    text = value.decode("latin-1")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def describe_change(base: HddInfo, variant: HddInfo) -> tuple[int, str]:
    changed = [
        index for index in range(len(LINE_NAMES)) if base.lines[index] != variant.lines[index]
    ]
    if not changed:
        return 0, "unchanged"
    if len(changed) == 1:
        index = changed[0]
        return index + 1, "%s -> %s" % (
            short_line(base.lines[index]),
            short_line(variant.lines[index]),
        )
    if sorted(base.lines) == sorted(variant.lines):
        return 0, "permutation of lines"
    return 0, "lines " + ",".join(str(index + 1) for index in changed)


def run_variant_tool(base: Path, out_dir: Path, sweep: str, permute: bool) -> str:
    tool = Path(__file__).resolve().with_name("hddinfo_variants.py")
    if not tool.is_file():
        raise RuntimeError("missing %s" % tool)
    command = [sys.executable, str(tool), str(base), str(out_dir), "--sweep", sweep]
    if not permute:
        command.append("--no-permute")
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            "%s failed (%d): %s" % (tool.name, proc.returncode, proc.stderr.strip())
        )
    return proc.stdout.strip()


def cmd_parse(args: argparse.Namespace) -> int:
    path = Path(args.file)
    raw = read_file(path)
    record = HddInfo.parse(raw)
    if args.json:
        print(json.dumps(record_json(record, path, raw), indent=2))
    else:
        print(format_record(record, path, raw))
        if record.size != SIZE:
            print("warning: %d bytes, the card block is %d" % (record.size, SIZE), file=sys.stderr)
    return EXIT_OK


def cmd_classify(args: argparse.Namespace) -> int:
    sys_path, sd_path = Path(args.sys_file), Path(args.sd_file)
    sys_raw, sd_raw = read_file(sys_path), read_file(sd_path)
    result = classify(
        HddInfo.parse(sys_raw),
        HddInfo.parse(sd_raw),
        target_line1=getattr(args, "target_line1", None),
        mapdbver_min=getattr(args, "mapdbver_min", None),
        mapdbver_max=getattr(args, "mapdbver_max", None),
    )
    if args.json:
        payload = dict(result)
        payload["sys"] = record_json(HddInfo.parse(sys_raw), sys_path, sys_raw)
        payload["sd"] = record_json(HddInfo.parse(sd_raw), sd_path, sd_raw)
        print(json.dumps(payload, indent=2))
    else:
        print(format_classification(result, sys_path.name, sd_path.name))
    return EXIT_OK if result["no_proven_failure"] else EXIT_DIFFERENT


def cmd_matrix(args: argparse.Namespace) -> int:
    base_path = Path(args.base)
    out_dir = Path(args.out_dir)
    base_raw = read_file(base_path)
    base_record = HddInfo.parse(base_raw)
    sys_path = Path(args.sys) if args.sys else base_path
    sys_record = HddInfo.parse(read_file(sys_path)) if args.sys else base_record
    mapdbver_min = getattr(args, "mapdbver_min", None)
    mapdbver_max = getattr(args, "mapdbver_max", None)
    target_line1 = getattr(args, "target_line1", None)

    out_dir.mkdir(parents=True, exist_ok=True)
    before = {
        path.name: path.stat().st_mtime_ns
        for path in out_dir.glob("*.HDD_INFO.TXT")
    }
    summary = run_variant_tool(base_path, out_dir, args.sweep, not args.no_permute)
    if args.json:
        print(summary, file=sys.stderr)
    else:
        print(summary)

    # Files left over from an earlier run (different sweep/permute settings)
    # keep their old mtime and would silently distort the matrix.
    stale = sorted(
        path.name
        for path in out_dir.glob("*.HDD_INFO.TXT")
        if before.get(path.name) == path.stat().st_mtime_ns
    )
    if stale:
        print(
            "warning: %d pre-existing variant(s) not regenerated, excluded from "
            "the manifest: %s" % (len(stale), ", ".join(stale)),
            file=sys.stderr,
        )

    old_manifest = out_dir / "MANIFEST.txt"
    if old_manifest.exists():
        old_manifest.replace(out_dir / "MANIFEST.variants.txt")

    rows = []
    for path in sorted(out_dir.glob("*.HDD_INFO.TXT")):
        if path.name in stale:
            continue
        raw = read_file(path)
        if len(raw) != len(base_raw):
            raise RuntimeError(
                "%s changed length: %d != %d" % (path.name, len(raw), len(base_raw))
            )
        record = HddInfo.parse(raw)
        result = classify(
            sys_record,
            record,
            target_line1=target_line1,
            mapdbver_min=mapdbver_min,
            mapdbver_max=mapdbver_max,
        )
        line, edit = describe_change(base_record, record)
        c1 = result["check1_different_map_code"]["verdict"]
        mv = result["check2_map_data_base_unmatch"]["mapdbver"]
        c2 = result["check2_map_data_base_unmatch"]["verdict"]
        rows.append(
            {
                "file": path.name,
                "line": line,
                "edit": edit,
                "verdict": result["verdict"],
                "reasons": result["reasons"],
                "check1": c1,
                "check2": c2,
                "mapdbver": mv["value"],
                "mapdbver_hex": mv["hex"],
                "mapdbver_chars": mv["chars"],
                "l1": record.text("base_code"),
            }
        )

    verdicts = Counter(row["verdict"] for row in rows)
    c1_counts = Counter(row["check1"] for row in rows)
    c2_counts = Counter(row["check2"] for row in rows)

    manifest = [
        "HDD_INFO.TXT map-code matrix (M2.15 AppLaunch model, predictions/checks)",
        "",
        "model:      %s (%s)" % (MODEL_ID, MODEL_STATUS),
        "source:     %s" % MODEL_SOURCE,
        "note:       %s." % MODEL_NOTE,
        "base:       %s (%d bytes, sha256 %s)"
        % (base_path, len(base_raw), sha256(base_raw)),
        "sys/ref:    %s%s"
        % (
            sys_path,
            " (= base, line1 proxy)" if not args.sys else " (sha256 %s)" % sha256(read_file(sys_path)),
        ),
        "bounds:     %s"
        % (
            "min=%s max=%s (unit target-info +112/+114)" % (mapdbver_min, mapdbver_max)
            if mapdbver_min is not None and mapdbver_max is not None
            else "UNKNOWN (check 2 reports MapDBVer only)"
        ),
        "variants:   %d, all %d bytes" % (len(rows), len(base_raw)),
        *(
            ["excluded:   %d stale file(s): %s" % (len(stale), ", ".join(stale))]
            if stale
            else []
        ),
        "",
        "overall verdicts:",
    ]
    for verdict, count in sorted(verdicts.items()):
        manifest.append("  %-38s %3d" % (verdict, count))
    manifest.append("check 1 (0x50 line1 bytes 0-10 vs unit +0x60):")
    for verdict, count in sorted(c1_counts.items()):
        manifest.append("  %-38s %3d" % (verdict, count))
    manifest.append("check 2 (0x51 L3 pos 5,6,7 vs unit +112/+114):")
    for verdict, count in sorted(c2_counts.items()):
        manifest.append("  %-38s %3d" % (verdict, count))
    manifest += [
        "",
        "%-50s %-4s %-22s %-10s %-12s %s"
        % ("file", "line", "check1(0x50)", "check2(0x51)", "MapDBVer", "edit"),
        "%-50s %-4s %-22s %-10s %-12s %s"
        % ("-" * 50, "-" * 4, "-" * 22, "-" * 10, "-" * 12, "-" * 30),
    ]
    for row in rows:
        manifest.append(
            "%-50s %-4s %-22s %-10s %-12s %s"
            % (row["file"], row["line"] or "-", row["check1"], row["check2"], row["mapdbver_hex"], row["edit"])
        )
    manifest += [
        "",
        "The variant tool's own manifest is MANIFEST.variants.txt.",
        "Run this matrix on a spare card only; the original card stays read-only.",
    ]
    (out_dir / "MANIFEST.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")

    if args.json:
        print(
            json.dumps(
                {
                    "model": MODEL_ID,
                    "model_status": MODEL_STATUS,
                    "model_note": MODEL_NOTE,
                    "base": {
                        "path": str(base_path),
                        "size": len(base_raw),
                        "sha256": sha256(base_raw),
                    },
                    "sys": {
                        "path": str(sys_path),
                        "sha256": sha256(read_file(sys_path)),
                    },
                    "bounds": {"min": mapdbver_min, "max": mapdbver_max},
                    "out_dir": str(out_dir),
                    "counts": dict(verdicts),
                    "check1_counts": dict(c1_counts),
                    "check2_counts": dict(c2_counts),
                    "variants": rows,
                },
                indent=2,
            )
        )
    else:
        print("%d variants, all %d bytes" % (len(rows), len(base_raw)))
        print("  check1 (DIFFERENT MAP CODE):")
        for verdict, count in sorted(c1_counts.items()):
            print("    %-22s %3d" % (verdict, count))
        print("  check2 (MAP DATA BASE UNMATCH):")
        for verdict, count in sorted(c2_counts.items()):
            print("    %-22s %3d" % (verdict, count))
        print("manifest: %s" % (out_dir / "MANIFEST.txt"))
    return EXIT_OK


def format_predict(result: dict, sd_name: str) -> str:
    out = [
        "predictor %s (%s): SD=%s" % (result["predictor"], MODEL_STATUS, sd_name),
        "  verdict: %s  (exit %d, accepted=%s)" % (
            result["verdict"], result["exit_code"], result["accepted"]),
    ]
    c1 = result["check1_different_map_code"]
    out.append("  check1 %-22s %s  evaluated=%s  prov=%s" % (
        CHECK1_CODE, c1["verdict"], c1["evaluated"], c1.get("target_line1_provenance", c1.get("ref_source", ""))))
    c2 = result["check2_map_data_base_unmatch"]
    mv = c2["mapdbver"]
    out.append("  check2 %-22s %s  evaluated=%s  MapDBVer=%s %s" % (
        CHECK2_CODE, c2["verdict"], c2["evaluated"], mv["hex"], c2["range_check"]))
    for reason in result["reasons"]:
        out.append("  ! %s" % reason)
    out.append("  note: offline pre-L3 gate (rule 13); M9.6/M2.4 still required")
    return "\n".join(out)


def cmd_predict(args: argparse.Namespace) -> int:
    sd_path = Path(args.sd_file)
    sd_raw = read_file(sd_path)
    sd_record = HddInfo.parse(sd_raw)
    if (args.mapdbver_min is None) != (args.mapdbver_max is None):
        raise ValueError("--mapdbver-min and --mapdbver-max must be provided together")
    result = predict(
        sd_record,
        target_line1=args.target_line1,
        target_line1_provenance=args.target_line1_provenance,
        mapdbver_min=args.mapdbver_min,
        mapdbver_max=args.mapdbver_max,
    )
    if args.json:
        payload = dict(result)
        payload["sd"] = {
            "path": str(sd_path),
            "size": len(sd_raw),
            "sha256": sha256(sd_raw),
        }
        print(json.dumps(payload, indent=2))
    else:
        print(format_predict(result, sd_path.name))
    # M2.18: only ACCEPT exits 0; any non-ACCEPT (incl. BOUNDS_UNKNOWN/fail) non-zero.
    return result["exit_code"]


def _variant_edit(base: HddInfo, variant: HddInfo) -> tuple[int, str]:
    return describe_change(base, variant)


def cmd_predict_table(args: argparse.Namespace) -> int:
    base_path = Path(args.base)
    base_raw = read_file(base_path)
    base_record = HddInfo.parse(base_raw)
    if (args.mapdbver_min is None) != (args.mapdbver_max is None):
        raise ValueError("--mapdbver-min and --mapdbver-max must be provided together")

    if args.variants_dir:
        var_dir = Path(args.variants_dir)
        temp = None
    else:
        temp = tempfile.TemporaryDirectory(prefix="hddinfo-predict-")
        var_dir = Path(temp.name)
        run_variant_tool(base_path, var_dir, args.sweep, not args.no_permute)

    try:
        variant_files = sorted(p for p in var_dir.glob("*.HDD_INFO.TXT"))
        rows = []
        for path in variant_files:
            raw = read_file(path)
            if len(raw) != len(base_raw):
                raise RuntimeError("%s length %d != base %d" % (path.name, len(raw), len(base_raw)))
            record = HddInfo.parse(raw)
            result = predict(
                record,
                target_line1=args.target_line1,
                target_line1_provenance=args.target_line1_provenance,
                mapdbver_min=args.mapdbver_min,
                mapdbver_max=args.mapdbver_max,
            )
            line, edit = _variant_edit(base_record, record)
            c1 = result["check1_different_map_code"]
            c2 = result["check2_map_data_base_unmatch"]
            mv = c2["mapdbver"]
            rows.append({
                "variant": path.name,
                "line": line,
                "edit": edit,
                "l1_base_code": record.text("base_code"),
                "check1_verdict": c1["verdict"],
                "check2_verdict": c2["verdict"],
                "mapdbver": mv["value"],
                "mapdbver_hex": mv["hex"],
                "mapdbver_chars": "".join("?" if c is None else c for c in mv["chars"]),
                "overall_verdict": result["verdict"],
                "accepted": result["accepted"],
                "firmware_still_required": "M9.6/M2.4 (rule 13)",
            })

        verdicts = Counter(r["overall_verdict"] for r in rows)
        c1_counts = Counter(r["check1_verdict"] for r in rows)
        c2_counts = Counter(r["check2_verdict"] for r in rows)
        mapdbver_changes = [r for r in rows if r["mapdbver"] != extract_mapdbver(base_record)["value"]]
        meta = {
            "tool": "hddinfo.py predict-table (M2.18)",
            "model": MODEL_ID,
            "model_status": MODEL_STATUS,
            "predictor": "M2.18-strict",
            "base_sha256": sha256(base_raw),
            "base_size": len(base_raw),
            "base_provenance_note": args.base_provenance or "",
            "target_line1_provided": args.target_line1 is not None,
            "target_line1_provenance": args.target_line1_provenance or "",
            "mapdbver_bounds_provided": args.mapdbver_min is not None and args.mapdbver_max is not None,
            "mapdbver_min": args.mapdbver_min,
            "mapdbver_max": args.mapdbver_max,
            "sweep": args.sweep,
            "permute": not args.no_permute,
            "variant_count": len(rows),
            "overall_counts": dict(verdicts),
            "check1_counts": dict(c1_counts),
            "check2_counts": dict(c2_counts),
            "mapdbver_change_count": len(mapdbver_changes),
            "ref_mapdbver": extract_mapdbver(base_record)["value"],
            "ref_mapdbver_hex": extract_mapdbver(base_record)["hex"],
            "firmware_still_required": "M9.6/M2.4 for all acceptance verdicts (rule 13)",
            "no_vendor_bytes_committed": True,
        }

        if args.format == "json":
            print(json.dumps({"meta": meta, "rows": rows}, indent=2))
        elif args.format == "tsv":
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()) if rows else [
                "variant","line","edit","l1_base_code","check1_verdict","check2_verdict",
                "mapdbver","mapdbver_hex","mapdbver_chars","overall_verdict","accepted","firmware_still_required"], delimiter="\t", lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
            text = "# " + json.dumps(meta, separators=(",", ":")) + "\n" + buf.getvalue()
            if args.out:
                Path(args.out).write_text(text, encoding="utf-8")
                print("wrote %d rows to %s" % (len(rows), args.out), file=sys.stderr)
            else:
                sys.stdout.write(text)
        else:
            out = [
                "M2.18 predict-table: %d variants, base sha256=%s (%dB)" % (len(rows), meta["base_sha256"], len(base_raw)),
                "  overall: %s" % dict(verdicts),
                "  check1:  %s" % dict(c1_counts),
                "  check2:  %s" % dict(c2_counts),
                "  MapDBVer changes: %d (ref %s)" % (len(mapdbver_changes), meta["ref_mapdbver_hex"]),
            ]
            if args.base_provenance:
                out.append("  base provenance: %s" % args.base_provenance)
            print("\n".join(out))
            if args.out:
                Path(args.out).write_text(json.dumps({"meta": meta, "rows": rows}, indent=2) + "\n", encoding="utf-8")

        # sanity exit: non-zero only on tool error; table is evidence output.
        return EXIT_OK
    finally:
        if temp is not None:
            temp.cleanup()


def cmd_selftest(json_out: bool = False) -> int:
    """Synthetic six-line blocks only; no vendor data is read."""
    checks: list[tuple[bool, str]] = []

    def check(condition: bool, label: str) -> None:
        checks.append((bool(condition), label))

    synthetic = [
        b"TST-302-100",   # line 1 base_code (11 chars)
        b"TST-309-101",   # line 2
        b"02-990100-00",  # line 3 build: pos 5,6,7 = '0','1','0' -> 0x010
        b"TST08-EVEUR",   # line 4
        b"99-05",         # line 5
        b"990323501005",  # line 6
    ]
    raw = b"\r\n".join(synthetic)
    check(len(raw) == SIZE, "synthetic block is exactly %d bytes" % SIZE)

    record = HddInfo.parse(raw)
    check(record.size == SIZE, "parsed record size is %d" % SIZE)
    check(record.to_bytes() == raw, "parse/serialise round-trip is byte-identical")
    check(record.lines == synthetic, "all six named lines retain their bytes")
    check(record.tail == b"", "no tail bytes in the canonical block")

    # M2.3 line->field->type->struct offset mapping (C-1711/C-721-C-728).
    check(len(HDD_INFO_FIELDS) == 6, "mapping has 6 HDD_INFO fields")
    check(tuple(f.name for f in HDD_INFO_FIELDS) == LINE_NAMES, "LINE_NAMES follows mapping order")
    check(tuple(f.line for f in HDD_INFO_FIELDS) == (1, 2, 3, 4, 5, 6), "mapping lines are 1..6 in order")
    check(tuple(f.offset for f in HDD_INFO_FIELDS) == (0x00, 0x18, 0x30, 0x4a, 0x62, 0x7a),
          "struct offsets match M2.1 (r8+0x00,18,30,4a,62,7a)")
    check(tuple(f.max_wchars for f in HDD_INFO_FIELDS) == (12, 12, 13, 12, 12, 13),
          "max wchar_t counts match M2.1 wcsncpy maxima")
    check(all(f.file_type.startswith("ASCII text line") for f in HDD_INFO_FIELDS),
          "file type is ASCII CRLF text lines")
    check(all("wchar_t" in f.mem_type for f in HDD_INFO_FIELDS),
          "memory type is wchar_t[] per M2.1 reader")
    check(HDD_INFO_FIELD_BY_NAME["map_code"].offset == 0x4a, "map_code (line 4) is r8+0x4a")
    check(HDD_INFO_FIELD_BY_OFFSET[0x7a].name == "part_number", "r8+0x7a is part_number (line 6)")

    trailing = HddInfo.parse(raw + b"\r\n")
    check(trailing.to_bytes() == raw + b"\r\n", "trailing CRLF is retained")
    check(trailing.tail == b"\r\n", "trailing CRLF is kept in tail, not in line 6")

    padded = raw + b"\r\n\x00\x00"
    padded_record = HddInfo.parse(padded)
    check(padded_record.to_bytes() == padded, "arbitrary tail bytes round-trip")
    check(padded_record.tail == b"\r\n\x00\x00", "arbitrary tail bytes stay in tail")

    # M2.15 check 1 extraction: line 1, 11 bytes (file offset 0, len 11)
    check(line1_compare_bytes(record) == b"TST-302-100", "check1 line1 bytes 0-10 match")
    check(len(line1_compare_bytes(record)) == 11, "check1 compare field is 11 bytes")
    # M2.15 check 2 extraction: line 3 pos 5,6,7 = '0','1','0' -> 0x010
    mv = extract_mapdbver(record)
    check(mv["line"] == 3 and mv["positions"] == [5, 6, 7], "check2 reads line 3 pos 5,6,7")
    check(mv["chars"] == ["0", "1", "0"], "check2 chars are '0','1','0' for 02-990100-00")
    check(mv["value"] == 0x010, "check2 MapDBVer 010 -> 0x010 (16)")
    check(mv["file_offsets"] == [31, 32, 33], "check2 file offsets 31-33 for factory-like layout")
    # converter: 0-9, a-f, A-F, not-found -> 0 (fn 0x03bd2a40)
    check(_conv_nibble(ord("0")) == 0 and _conv_nibble(ord("9")) == 9, "converter 0-9")
    check(_conv_nibble(ord("a")) == 10 and _conv_nibble(ord("f")) == 15, "converter a-f")
    check(_conv_nibble(ord("A")) == 10 and _conv_nibble(ord("F")) == 15, "converter A-F")
    check(_conv_nibble(ord("-")) == 0 and _conv_nibble(ord("X")) == 0, "converter not-found -> 0")

    # M2.15: "self-test must pin one pass and one fail per check"
    bounds = dict(mapdbver_min=0x010, mapdbver_max=0x010)  # exact match for 010
    # check 1 PASS, check 2 PASS
    c1p = classify(record, record, **bounds)
    check(c1p["check1_different_map_code"]["verdict"] == "PASS", "M2.15 check1 PASS (line1 match)")
    check(c1p["check2_map_data_base_unmatch"]["verdict"] == "PASS", "M2.15 check2 PASS (MapDBVer in range)")
    check(c1p["accepted"] is True and c1p["failures"] == [], "M2.15 both pass -> ACCEPT")
    # check 1 FAIL (DIFFERENT MAP CODE): change line 1
    sd1 = record.with_line("base_code", b"TST-999-100")
    c1f = classify(record, sd1, **bounds)
    check(c1f["check1_different_map_code"]["verdict"] == CHECK1_CODE, "M2.15 check1 FAIL -> DIFFERENT MAP CODE")
    check(CHECK1_CODE in c1f["failures"], "M2.15 check1 failure recorded")
    check(c1f["accepted"] is False, "M2.15 check1 fail -> not accepted")
    # check 2 FAIL (MAP DATA BASE UNMATCH): change line 3 pos 5-7 (010 -> 005)
    sd2 = record.with_line("build", b"02-990050-00")  # pos 5,6,7 = '0','0','5' -> 0x005
    check(extract_mapdbver(sd2)["value"] == 0x005, "M2.15 check2 fail setup: MapDBVer 005")
    c2f = classify(record, sd2, **bounds)
    check(c2f["check1_different_map_code"]["verdict"] == "PASS", "M2.15 check2-fail case: check1 still PASS")
    check(c2f["check2_map_data_base_unmatch"]["verdict"] == CHECK2_CODE, "M2.15 check2 FAIL -> MAP DATA BASE UNMATCH")
    check(CHECK2_CODE in c2f["failures"], "M2.15 check2 failure recorded")
    check(c2f["accepted"] is False, "M2.15 check2 fail -> not accepted")
    # without bounds, check 2 is BOUNDS_UNKNOWN but check 1 is definitive
    c1only = classify(record, sd1)
    check(c1only["check1_different_map_code"]["verdict"] == CHECK1_CODE, "M2.15 check1 fail definitive without bounds")
    c2unk = classify(record, record)
    check(c2unk["check2_map_data_base_unmatch"]["verdict"] == "BOUNDS_UNKNOWN", "M2.15 check2 BOUNDS_UNKNOWN without bounds")
    check(c2unk["no_proven_failure"] is True, "M2.15 no bounds, check1 pass -> no proven failure")

    # M2.18 strict predictor: ACCEPT only with explicit unit inputs (+0x60, +112/+114).
    # Missing target_line1 and/or missing bounds => BOUNDS_UNKNOWN, never ACCEPT/pass.
    tline1 = record.text("base_code")  # explicit caller-supplied proxy/provenance in real use
    p_ok = predict(record, target_line1=tline1, target_line1_provenance="selftest explicit",
                   mapdbver_min=0x010, mapdbver_max=0x010)
    check(p_ok["verdict"] == "ACCEPT", "M2.18 predict ACCEPT with explicit target_line1+bounds")
    check(p_ok["accepted"] is True and p_ok["exit_code"] == PREDICT_ACCEPT, "M2.18 ACCEPT exits 0")
    check(p_ok["check1_different_map_code"]["evaluated"] is True, "M2.18 check1 evaluated with target")
    check(p_ok["check2_map_data_base_unmatch"]["evaluated"] is True, "M2.18 check2 evaluated with bounds")
    p_c1f = predict(sd1, target_line1=tline1, target_line1_provenance="selftest explicit",
                    mapdbver_min=0x010, mapdbver_max=0x010)
    check(p_c1f["verdict"] == CHECK1_CODE, "M2.18 predict check1 FAIL -> DIFFERENT MAP CODE")
    check(p_c1f["accepted"] is False and p_c1f["exit_code"] == PREDICT_NOT_ACCEPTED, "M2.18 check1 fail non-zero")
    p_c2f = predict(sd2, target_line1=tline1, target_line1_provenance="selftest explicit",
                    mapdbver_min=0x010, mapdbver_max=0x010)
    check(p_c2f["verdict"] == CHECK2_CODE, "M2.18 predict check2 FAIL -> MAP DATA BASE UNMATCH")
    check(p_c2f["accepted"] is False and p_c2f["exit_code"] == PREDICT_NOT_ACCEPTED, "M2.18 check2 fail non-zero")
    # unknown-never-pass: missing target_line1 and/or missing bounds
    p_no_t = predict(record, mapdbver_min=0x010, mapdbver_max=0x010)
    check(p_no_t["verdict"] == "BOUNDS_UNKNOWN", "M2.18 missing target_line1 => BOUNDS_UNKNOWN")
    check(p_no_t["accepted"] is False and p_no_t["exit_code"] == PREDICT_NOT_ACCEPTED, "M2.18 missing target never ACCEPT/exit0")
    p_no_b = predict(record, target_line1=tline1, target_line1_provenance="selftest explicit")
    check(p_no_b["verdict"] == "BOUNDS_UNKNOWN", "M2.18 missing bounds => BOUNDS_UNKNOWN")
    check(p_no_b["accepted"] is False and p_no_b["exit_code"] == PREDICT_NOT_ACCEPTED, "M2.18 missing bounds never ACCEPT/exit0")
    p_none = predict(record)
    check(p_none["verdict"] == "BOUNDS_UNKNOWN" and p_none["accepted"] is False, "M2.18 no inputs => BOUNDS_UNKNOWN")
    check(p_none["exit_code"] == PREDICT_NOT_ACCEPTED, "M2.18 no inputs non-zero")
    # case where check1 would pass but bounds unknown — overall must still be non-ACCEPT
    p_c1ok_nob = predict(record, target_line1=tline1, target_line1_provenance="selftest explicit")
    check(p_c1ok_nob["check1_different_map_code"]["verdict"] == "PASS", "M2.18 check1 pass but bounds unknown: check1 PASS")
    check(p_c1ok_nob["verdict"] == "BOUNDS_UNKNOWN", "M2.18 check1 pass + bounds unknown => overall BOUNDS_UNKNOWN")
    check(p_c1ok_nob["accepted"] is False and p_c1ok_nob["exit_code"] != PREDICT_ACCEPT, "M2.18 check1 pass+bounds unknown never ACCEPT")
    # check1 fail takes precedence over unknown bounds? explicit input failed => report failure
    p_c1f_nob = predict(sd1, target_line1=tline1, target_line1_provenance="selftest explicit")
    check(p_c1f_nob["verdict"] == CHECK1_CODE, "M2.18 check1 fail reported even if bounds unknown")

    short_ok = False
    try:
        HddInfo.parse(b"A\r\nB\r\nC")
    except ValueError:
        short_ok = True
    check(short_ok, "fewer than six lines raises ValueError")

    serial = True
    try:
        json.dumps(c1p)
    except (TypeError, ValueError):
        serial = False
    check(serial, "classification result is JSON-serialisable")

    failures = [label for ok, label in checks if not ok]
    if json_out:
        print(
            json.dumps(
                {
                    "model": MODEL_ID,
                    "model_status": MODEL_STATUS,
                    "checks": len(checks),
                    "failures": failures,
                    "ok": not failures,
                },
                indent=2,
            )
        )
    else:
        for ok, label in checks:
            print("  %s  %s" % ("ok  " if ok else "FAIL", label))
        print(
            "selftest: %s (%d checks)"
            % ("OK" if not failures else "FAILED", len(checks))
        )
    return EXIT_OK if not failures else EXIT_DIFFERENT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="M2.15 AppLaunch model (VERIFIED static). Check 2 needs unit target-info bounds.",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="run the synthetic self-test and exit (handled before subcommands)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_parse = sub.add_parser("parse", help="parse one HDD_INFO.TXT block")
    p_parse.add_argument("file")
    p_parse.add_argument("--json", action="store_true")
    p_parse.set_defaults(func=cmd_parse)

    p_class = sub.add_parser("classify", help="model AppLaunch checks (M2.15) for one Sys/SD pair")
    p_class.add_argument("sys_file", help="Sys/reference side (line1 proxy for unit target-info +0x60)")
    p_class.add_argument("sd_file", help="SD side (card VER_INFO/HDD_INFO.TXT)")
    p_class.add_argument("--target-line1", help="explicit 11-byte unit target-info +0x60 value (overrides sys line1)")
    p_class.add_argument("--mapdbver-min", type=int, help="unit target-info +112 (u16 BE) lower bound")
    p_class.add_argument("--mapdbver-max", type=int, help="unit target-info +114 (u16 BE) upper bound")
    p_class.add_argument("--json", action="store_true")
    p_class.set_defaults(func=cmd_classify)

    p_pred = sub.add_parser(
        "predict",
        help="M2.18 strict offline predictor: ACCEPT only with explicit unit inputs (pre-L3 gate)",
    )
    p_pred.add_argument("sd_file", help="candidate HDD_INFO.TXT to classify")
    p_pred.add_argument(
        "--target-line1",
        help=("explicit 11-byte unit target-info +0x60 value (C-2081). "
              "Caller-supplied input/proxy; NOT a 'factory value' unless caller states provenance. "
              "Required for ACCEPT; missing => BOUNDS_UNKNOWN (never pass)."),
    )
    p_pred.add_argument(
        "--target-line1-provenance",
        help="human-readable provenance for --target-line1 (recorded in output)",
    )
    p_pred.add_argument("--mapdbver-min", type=int, help="explicit unit target-info +112 u16 BE min (C-2084)")
    p_pred.add_argument("--mapdbver-max", type=int, help="explicit unit target-info +114 u16 BE max (C-2084)")
    p_pred.add_argument("--json", action="store_true", help="stable JSON verdict + per-check fields")
    p_pred.set_defaults(func=cmd_predict)

    p_ptab = sub.add_parser(
        "predict-table",
        help="M2.18: classify HDD_INFO variants and emit derived per-variant table (no vendor bytes)",
    )
    p_ptab.add_argument("base", help="base HDD_INFO.TXT (caller-supplied, outside repo; not committed)")
    p_ptab.add_argument("--variants-dir", help="directory of *.HDD_INFO.TXT variants (else generated via hddinfo_variants.py)")
    p_ptab.add_argument("--out", help="write derived table to this path (TSV/JSON by --format)")
    p_ptab.add_argument("--format", choices=("tsv", "json", "summary"), default="tsv")
    p_ptab.add_argument("--sweep", default="0-5", help="digit sweep range when generating (default 0-5)")
    p_ptab.add_argument("--no-permute", action="store_true")
    p_ptab.add_argument("--target-line1", help="explicit unit +0x60 input/proxy (see predict)")
    p_ptab.add_argument("--target-line1-provenance", help="provenance for --target-line1")
    p_ptab.add_argument("--mapdbver-min", type=int)
    p_ptab.add_argument("--mapdbver-max", type=int)
    p_ptab.add_argument("--base-provenance", help="derived-only provenance note (e.g. sha256, not in repo)")
    p_ptab.set_defaults(func=cmd_predict_table)

    p_matrix = sub.add_parser("matrix", help="emit variants with M2.15 check results")
    p_matrix.add_argument("base", help="base HDD_INFO.TXT (72 bytes)")
    p_matrix.add_argument("out_dir")
    p_matrix.add_argument(
        "--sys", help="Sys/reference side for check 1 (default: the base file itself)"
    )
    p_matrix.add_argument("--target-line1", help="explicit unit target-info +0x60 value")
    p_matrix.add_argument("--mapdbver-min", type=int, help="unit target-info +112 bound")
    p_matrix.add_argument("--mapdbver-max", type=int, help="unit target-info +114 bound")
    p_matrix.add_argument("--sweep", default="0-5", help="digit sweep range (default 0-5)")
    p_matrix.add_argument(
        "--no-permute", action="store_true", help="skip line swaps and the reverse variant"
    )
    p_matrix.add_argument("--json", action="store_true")
    p_matrix.set_defaults(func=cmd_matrix)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return cmd_selftest(json_out="--json" in argv)

    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
