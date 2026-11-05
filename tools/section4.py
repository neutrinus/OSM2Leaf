#!/usr/bin/env python3
"""ZE0 tile section 4: administrative/place-name index.

Input is a raw section-4 *payload*, not a whole tile.  Walk the tile container
with ``tools/ze0-viewer/ze0_section4.py`` first and feed each decompressed
record (or the concatenated zlib members) to this tool.  Two framings are
accepted:

* back-to-back independent zlib members, one decompressed record each (the
  normal tile layout); zero bytes between members are treated as padding;
* one decompressed record as plain bytes (no framing information).

Only fields documented in ``docs/format/map-tiles.md`` are interpreted:

    0x00  u16  parcel word 0
    0x02  u16  parcel word 1
    0x04  u16  record type 0x0009
    0x06  ...  unexplained
    0x10  u16  ISO 3166 numeric country
    0x12  ...  unexplained binary, then ``d=NAME`` strings

Everything else is reported as raw hex.  ``encode build`` refuses (exit 3)
rather than inventing bytes for the unknown parts.  ``encode preserve`` copies
the original payload byte-for-byte and is the default for unchanged tiles.

Usage::

    python3 tools/section4.py parse PAYLOAD [--json|--json-out FILE]
    python3 tools/section4.py encode preserve MODEL OUT
    python3 tools/section4.py encode build MODEL OUT
    python3 tools/section4.py verify PAYLOAD
    python3 tools/section4.py --selftest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import zlib

MODEL_FORMAT = "ze0-section4-model/1"
TYPE_TAG = 0x0009
COUNTRY_OFFSET = 0x10
HEADER_BYTES = 0x12
DEFAULT_MIN_NAME = 3

EXIT_OK = 0
EXIT_CHECK_FAILED = 1
EXIT_BAD_INPUT = 2
EXIT_UNKNOWN_FIELDS = 3

# Only offsets documented by the repo are interpreted.  Everything else is
# opaque hex.
DOCUMENTED_SPANS = ((0x00, 0x06), (COUNTRY_OFFSET, COUNTRY_OFFSET + 2))

# The only ISO 3166 numeric value documented in this repo.  This is not a
# country table; unknown codes are printed numerically.
COUNTRY_NAMES = {300: "Greece"}

# C-126 / EXP-2026-11-05-32: B30R048R.DAT, viewer ``0=`` splitter.  These are
# reference observations, not values this tool re-measures from a tile.
REFERENCE_SECTION4 = {
    2011: {"records": 20, "names": 68},
    2014: {"records": 24, "names": 126},
    2016: {"records": 24, "names": 129},
}
REFERENCE_SOURCE = "C-126, EXP-2026-11-05-32"

NAME_PREFIX = re.compile(rb"([0-9])=")


class BuildRefused(Exception):
    """The model asks build mode to invent bytes whose grammar is unknown."""

    def __init__(self, items):
        super().__init__("build refused")
        self.items = items


class ShapeError(Exception):
    """The input or model is malformed (exit 2)."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def split_zlib_members(data: bytes):
    """Return ``[(payload, compressed, padding_after), ...]`` or None.

    ``None`` means the input is not a clean sequence of zlib members and
    should be treated as one plain record.
    """
    if not data:
        return None
    members = []
    pos = 0
    size = len(data)
    while pos < size:
        if not members:
            if data[pos] != 0x78:
                return None
            padding = b""
        else:
            start = pos
            while pos < size and data[pos] == 0x00:
                pos += 1
            padding = data[start:pos]
            members[-1]["padding_after"] = padding
            if pos >= size:
                break
            if data[pos] != 0x78:
                return None
        obj = zlib.decompressobj()
        try:
            plain = obj.decompress(data[pos:]) + obj.flush()
        except zlib.error:
            return None
        if not obj.eof:
            return None
        consumed = size - pos - len(obj.unused_data)
        if consumed <= 0:
            return None
        members.append(
            {
                "payload": plain,
                "compressed": data[pos : pos + consumed],
                "padding_after": b"",
            }
        )
        pos += consumed
    return members


def _decode_name(raw: bytes):
    if all(byte < 0x80 for byte in raw):
        return raw.decode("ascii"), "ascii"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("latin-1"), "latin-1"


def _plausible_name(raw: bytes) -> bool:
    return any(
        0x41 <= byte <= 0x5A or 0x61 <= byte <= 0x7A or byte >= 0x80
        for byte in raw
    )


def scan_names(payload: bytes, start: int = HEADER_BYTES, min_name: int = DEFAULT_MIN_NAME):
    """Scan ``d=NAME`` strings from ``start`` to EOF.

    The splitter follows the observed viewer behaviour: a name starts at
    ``[0-9]=``, ends at NUL or before the next ``[0-9]=``, and may be adjacent
    to the previous name (``LINDOS0=RODOS``).  The name-list start offset is not
    documented, so this is explicitly heuristic.
    """
    names = []
    spans = []
    index = start
    while index < len(payload):
        match = NAME_PREFIX.search(payload, index)
        if not match:
            break
        text_start = match.end()
        cursor = text_start
        terminated = False
        while cursor < len(payload):
            byte = payload[cursor]
            if byte == 0x00:
                terminated = True
                break
            if byte < 0x20 or byte == 0x7F:
                break
            if (
                cursor > text_start
                and 0x30 <= byte <= 0x39
                and cursor + 1 < len(payload)
                and payload[cursor + 1] == 0x3D
            ):
                break
            cursor += 1
        raw = payload[text_start:cursor]
        if len(raw) >= min_name and _plausible_name(raw):
            text, encoding = _decode_name(raw)
            end = cursor + 1 if terminated else cursor
            names.append(
                {
                    "index": len(names),
                    "prefix": match.group(1)[0] - 0x30,
                    "text": text,
                    "offset": match.start(),
                    "raw_hex": payload[match.start() : end].hex(),
                    "encoding": encoding,
                    "terminated": terminated,
                    "status": "OBSERVED",
                }
            )
            spans.append((match.start(), end))
            index = end if end > match.start() else text_start
        else:
            index = text_start
    return names, spans


def _unexplained_ranges(length: int, spans):
    ordered = sorted((max(0, a), min(length, b)) for a, b in spans if b > a)
    merged = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    ranges = []
    cursor = 0
    for start, end in merged:
        if start > cursor:
            ranges.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < length:
        ranges.append((cursor, length))
    return ranges


def parse_record(payload: bytes, index: int, framing: str, min_name: int):
    record = {
        "index": index,
        "framing": framing,
        "length": len(payload),
        "sha256": sha256(payload),
        "payload_hex": payload.hex(),
        "status": "ok",
        "parcel_w0": None,
        "parcel_w1": None,
        "parcel_u32": None,
        "type_tag": None,
        "country_code": None,
        "country_name": None,
        "documented_fields": [],
        "u32_fields": [],
        "names": [],
        "opaque_binary": [],
    }
    spans = list(DOCUMENTED_SPANS)
    if len(payload) < HEADER_BYTES:
        record["status"] = "short"
        record["opaque_binary"] = [
            {
                "offset": 0,
                "length": len(payload),
                "hex": payload.hex(),
                "status": "UNKNOWN",
            }
        ]
        return record

    w0, w1, w2, _w3, _w4, _w5 = struct.unpack_from(">HHHHHH", payload, 0)
    country = struct.unpack_from(">H", payload, COUNTRY_OFFSET)[0]
    record.update(
        {
            "parcel_w0": w0,
            "parcel_w1": w1,
            "parcel_u32": (w0 << 16) | w1,
            "type_tag": w2,
            "country_code": country,
            "country_name": COUNTRY_NAMES.get(country),
            "documented_fields": [
                {"offset": 0x00, "size": 2, "name": "parcel_w0", "value": w0},
                {"offset": 0x02, "size": 2, "name": "parcel_w1", "value": w1},
                {"offset": 0x04, "size": 2, "name": "type_tag", "value": w2},
                {
                    "offset": COUNTRY_OFFSET,
                    "size": 2,
                    "name": "country_code",
                    "value": country,
                },
            ],
            "u32_fields": [
                {
                    "offset": 0x00,
                    "value": (w0 << 16) | w1,
                    "name": "parcel_code",
                    "status": "OBSERVED",
                    "note": "two u16 parcel words; row/col formula is not applied",
                }
            ],
        }
    )
    if w2 != TYPE_TAG:
        record["status"] = "not-section4"
    # Words 3..5 and the u32 at 0x0c (0x06..0x0f) are not documented.

    names, name_spans = scan_names(payload, HEADER_BYTES, min_name)
    record["names"] = names
    spans.extend(name_spans)
    opaque = []
    for start, end in _unexplained_ranges(len(payload), spans):
        chunk = payload[start:end]
        opaque.append(
            {
                "offset": start,
                "length": end - start,
                "hex": chunk.hex(),
                "status": "UNKNOWN",
            }
        )
    record["opaque_binary"] = opaque
    return record


def parse_payload(data: bytes, source: str, min_name: int = DEFAULT_MIN_NAME):
    if not data:
        raise ShapeError("empty payload")
    members = split_zlib_members(data)
    if members is None:
        members = [
            {"payload": data, "compressed": b"", "padding_after": b""}
        ]
        framing = "plain"
    else:
        framing = "zlib"
    records = []
    for index, member in enumerate(members):
        record = parse_record(member["payload"], index, framing, min_name)
        if framing == "zlib":
            record["compressed_hex"] = member["compressed"].hex()
        record["padding_after_hex"] = member["padding_after"].hex()
        records.append(record)
    name_count = sum(len(record["names"]) for record in records)
    unique_names = {
        name["text"] for record in records for name in record["names"]
    }
    return {
        "format": MODEL_FORMAT,
        "source": {
            "path": source,
            "size": len(data),
            "sha256": sha256(data),
            "framing": framing,
        },
        "raw_hex": data.hex(),
        "record_count": len(records),
        "name_count": name_count,
        "unique_name_count": len(unique_names),
        "reference": {
            "source": REFERENCE_SOURCE,
            "years": REFERENCE_SECTION4,
            "note": "reference observations for B30R048R.DAT; not re-measured here",
        },
        "records": records,
    }


def _fmt_hex(chunk: bytes, limit: int = 48) -> str:
    text = chunk[:limit].hex(" ")
    if len(chunk) > limit:
        text += " ..."
    return text


def print_model(model, out=sys.stdout):
    source = model["source"]
    print(
        "section4: %s (%d bytes, sha256 %s)"
        % (source["path"], source["size"], source["sha256"]),
        file=out,
    )
    print(
        "framing: %s, records: %d, names: %d (unique %d)"
        % (
            source["framing"],
            model["record_count"],
            model["name_count"],
            model["unique_name_count"],
        ),
        file=out,
    )
    for record in model["records"]:
        country = record["country_code"]
        country_text = ""
        if country is not None:
            name = record.get("country_name")
            country_text = " (%s)" % name if name else ""
        print(
            "record %d: %d B, type 0x%04x, country %s%s, parcel w0=0x%04x w1=0x%04x"
            % (
                record["index"],
                record["length"],
                record["type_tag"] or 0,
                country if country is not None else "?",
                country_text,
                record["parcel_w0"] or 0,
                record["parcel_w1"] or 0,
            ),
            file=out,
        )
        for field in record["u32_fields"]:
            print(
                "  u32[0x%04x] = 0x%08x  %s (%s)"
                % (
                    field["offset"],
                    field["value"],
                    field["name"],
                    field["status"],
                ),
                file=out,
            )
        if record["names"]:
            print("  names (%d):" % len(record["names"]), file=out)
            for name in record["names"]:
                print(
                    "    +0x%04x  %d=%s [%s]%s"
                    % (
                        name["offset"],
                        name["prefix"],
                        name["text"],
                        name["encoding"],
                        "" if name["terminated"] else " (no NUL)",
                    ),
                    file=out,
                )
        if record["opaque_binary"]:
            print("  opaque:", file=out)
            for item in record["opaque_binary"]:
                print(
                    "    +0x%04x..0x%04x (%d B): %s"
                    % (
                        item["offset"],
                        item["offset"] + item["length"] - 1,
                        item["length"],
                        _fmt_hex(bytes.fromhex(item["hex"])),
                    ),
                    file=out,
                )


def print_reference(out=sys.stdout, measured=None, reference_year=None):
    print(
        "reference counts (%s; observed, not re-measured):" % REFERENCE_SOURCE,
        file=out,
    )
    print("  year  records  names", file=out)
    base = REFERENCE_SECTION4[2011]["records"]
    for year in sorted(REFERENCE_SECTION4):
        row = REFERENCE_SECTION4[year]
        print("  %d  %6d  %5d" % (year, row["records"], row["names"]), file=out)
    print(
        "  record delta vs 2011: 2014 +%d, 2016 +%d"
        % (
            REFERENCE_SECTION4[2014]["records"] - base,
            REFERENCE_SECTION4[2016]["records"] - base,
        ),
        file=out,
    )
    if measured is not None:
        print(
            "  measured payload: %d records / %d names"
            % (measured["record_count"], measured["name_count"]),
            file=out,
        )
        if reference_year in REFERENCE_SECTION4:
            row = REFERENCE_SECTION4[reference_year]
            match = (
                measured["record_count"] == row["records"]
                and measured["name_count"] == row["names"]
            )
            print(
                "  cmp %d: records %d/%d, names %d/%d -> %s"
                % (
                    reference_year,
                    measured["record_count"],
                    row["records"],
                    measured["name_count"],
                    row["names"],
                    "MATCH" if match else "DIFFERS",
                ),
                file=out,
            )
        else:
            print(
                "  reference comparison: not requested (pass --reference-year)",
                file=out,
            )


def encode_preserve(model):
    """Return the exact original payload bytes; never recompress."""
    raw_hex = model.get("raw_hex")
    if not raw_hex:
        raise ShapeError("preserve: model has no raw_hex (parse it again)")
    try:
        data = bytes.fromhex(raw_hex)
    except ValueError as exc:
        raise ShapeError("preserve: raw_hex is not valid hex: %s" % exc) from exc
    expected = model.get("source", {}).get("sha256")
    if expected and sha256(data) != expected:
        raise ShapeError(
            "preserve: raw_hex hash %s != source.sha256 %s"
            % (sha256(data), expected)
        )
    return data


def _coverage(length: int, spans):
    covered = bytearray(length)
    for start, end in spans:
        for pos in range(max(0, start), min(length, end)):
            covered[pos] = 1
    return covered


def _hole_ranges(covered):
    ranges = []
    cursor = 0
    size = len(covered)
    while cursor < size:
        if covered[cursor]:
            cursor += 1
            continue
        start = cursor
        while cursor < size and not covered[cursor]:
            cursor += 1
        ranges.append((start, cursor))
    return ranges


def encode_build(model):
    """Rebuild only the documented fields plus caller-supplied opaque bytes.

    Raises BuildRefused with a precise item list when any byte would have to be
    invented.  zlib framing is recompressed at level 6 (not byte-identical).
    """
    if model.get("format") != MODEL_FORMAT:
        raise ShapeError("build: expected model format %s" % MODEL_FORMAT)
    records = model.get("records")
    if not records:
        raise ShapeError("build: model has no records")
    output = bytearray()
    refusals = []

    for position, record in enumerate(records):
        index = record.get("index", position)
        record_refusals = []

        names = record.get("names") or []
        for name in names:
            record_refusals.append(
                {
                    "field": "records[%s].names[%s]"
                    % (index, name.get("index", "?")),
                    "offset": name.get("offset"),
                    "detail": (
                        "name-list placement/terminator grammar is UNKNOWN; "
                        "cannot rebuild %r without guessing"
                        % name.get("text", "")
                    ),
                }
            )
        if names:
            refusals.extend(record_refusals)
            continue

        required = ("parcel_w0", "parcel_w1", "type_tag", "country_code", "length")
        missing = [key for key in required if record.get(key) is None]
        for key in missing:
            record_refusals.append(
                {
                    "field": "records[%s].%s" % (index, key),
                    "offset": None,
                    "detail": "documented field is missing from the model",
                }
            )
        if record_refusals:
            refusals.extend(record_refusals)
            continue

        length = record["length"]
        if not isinstance(length, int) or length < HEADER_BYTES:
            record_refusals.append(
                {
                    "field": "records[%s].length" % index,
                    "offset": None,
                    "detail": "record must be at least 0x12 bytes",
                }
            )
        if record["type_tag"] != TYPE_TAG:
            raise ShapeError(
                "build: records[%s].type_tag is 0x%04x, expected 0x%04x"
                % (index, record["type_tag"], TYPE_TAG)
            )
        for key in ("parcel_w0", "parcel_w1", "country_code"):
            value = record[key]
            if not isinstance(value, int) or not 0 <= value <= 0xFFFF:
                record_refusals.append(
                    {
                        "field": "records[%s].%s" % (index, key),
                        "offset": None,
                        "detail": "value must fit in u16",
                    }
                )
        if record_refusals:
            refusals.extend(record_refusals)
            continue

        opaque = record.get("opaque_binary") or []
        spans = list(DOCUMENTED_SPANS)
        for item in opaque:
            offset = item.get("offset")
            hex_text = item.get("hex")
            if not isinstance(offset, int) or not isinstance(hex_text, str):
                record_refusals.append(
                    {
                        "field": "records[%s].opaque_binary" % index,
                        "offset": offset,
                        "detail": "opaque entry needs integer offset and hex string",
                    }
                )
                continue
            try:
                chunk = bytes.fromhex(hex_text)
            except ValueError:
                record_refusals.append(
                    {
                        "field": "records[%s].opaque_binary" % index,
                        "offset": offset,
                        "detail": "opaque hex is not valid hex",
                    }
                )
                continue
            if offset < 0 or offset + len(chunk) > length:
                record_refusals.append(
                    {
                        "field": "records[%s].opaque_binary" % index,
                        "offset": offset,
                        "detail": "opaque span lies outside the record",
                    }
                )
                continue
            for known_start, known_end in DOCUMENTED_SPANS:
                if offset < known_end and offset + len(chunk) > known_start:
                    record_refusals.append(
                        {
                            "field": "records[%s].opaque_binary" % index,
                            "offset": offset,
                            "detail": (
                                "opaque span overlaps documented field "
                                "0x%04x..0x%04x" % (known_start, known_end - 1)
                            ),
                        }
                    )
            spans.append((offset, offset + len(chunk)))

        for start, end in _hole_ranges(_coverage(length, spans)):
            record_refusals.append(
                {
                    "field": "records[%s].opaque_binary" % index,
                    "offset": start,
                    "length": end - start,
                    "detail": (
                        "undocumented bytes 0x%04x..0x%04x have no opaque hex"
                        % (start, end - 1)
                    ),
                }
            )
        if record_refusals:
            refusals.extend(record_refusals)
            continue

        buffer = bytearray(length)
        struct.pack_into(
            ">HHH", buffer, 0, record["parcel_w0"], record["parcel_w1"], TYPE_TAG
        )
        struct.pack_into(">H", buffer, COUNTRY_OFFSET, record["country_code"])
        for item in opaque:
            chunk = bytes.fromhex(item["hex"])
            buffer[item["offset"] : item["offset"] + len(chunk)] = chunk
        if record.get("framing") == "zlib":
            output.extend(zlib.compress(bytes(buffer), 6))
        else:
            output.extend(buffer)
        padding = record.get("padding_after_hex") or ""
        try:
            output.extend(bytes.fromhex(padding))
        except ValueError as exc:
            raise ShapeError(
                "build: records[%s].padding_after_hex is invalid: %s"
                % (index, exc)
            ) from exc

    if refusals:
        raise BuildRefused(refusals)
    return bytes(output)


def _read_bytes(path: str) -> bytes:
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError as exc:
        raise ShapeError("cannot read %s: %s" % (path, exc)) from exc


def _read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise ShapeError("cannot read %s: %s" % (path, exc)) from exc
    except json.JSONDecodeError as exc:
        raise ShapeError("cannot parse %s: %s" % (path, exc)) from exc


def _write_bytes(path: str, data: bytes):
    try:
        with open(path, "wb") as handle:
            handle.write(data)
    except OSError as exc:
        raise ShapeError("cannot write %s: %s" % (path, exc)) from exc


def _report_refusal(exc: BuildRefused, out=sys.stderr):
    print(
        "section4: build refused: %d unknown field(s); "
        "no output written" % len(exc.items),
        file=out,
    )
    for item in exc.items:
        location = ""
        if item.get("offset") is not None:
            location = " at 0x%04x" % item["offset"]
        print(
            "  - %s%s: %s"
            % (item.get("field", "?"), location, item.get("detail", "")),
            file=out,
        )


def command_parse(args):
    data = _read_bytes(args.payload)
    model = parse_payload(data, args.payload, args.min_name)
    if args.json_out:
        try:
            with open(args.json_out, "w", encoding="utf-8") as handle:
                json.dump(model, handle, indent=2)
                handle.write("\n")
        except OSError as exc:
            raise ShapeError(
                "cannot write %s: %s" % (args.json_out, exc)
            ) from exc
    if args.json:
        json.dump(model, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print_model(model)
    return EXIT_OK


def command_encode(args):
    model = _read_json(args.model)
    if args.mode == "preserve":
        data = encode_preserve(model)
    else:
        data = encode_build(model)
    _write_bytes(args.output, data)
    print(
        "section4: %s %s -> %s (%d bytes, sha256 %s)"
        % (args.mode, args.model, args.output, len(data), sha256(data))
    )
    return EXIT_OK


def command_verify(args):
    data = _read_bytes(args.payload)
    model = parse_payload(data, args.payload, args.min_name)
    rebuilt = encode_preserve(model)
    ok = rebuilt == data
    print("verify: %s" % args.payload)
    print("  bytes: %d" % len(data))
    print("  sha256: %s" % sha256(data))
    print(
        "  records: %d, names: %d (unique %d)"
        % (
            model["record_count"],
            model["name_count"],
            model["unique_name_count"],
        )
    )
    print(
        "  preserve round-trip: %s (%d bytes)"
        % ("OK byte-identical" if ok else "FAILED", len(rebuilt))
    )
    print_reference(sys.stdout, model, args.reference_year)
    return EXIT_OK if ok else EXIT_CHECK_FAILED


def _synthetic_record(names, country=300):
    header = struct.pack(
        ">HHHHHH", 0x1234, 0x5678, TYPE_TAG, 0xDEAD, 0x1111, 0x2222
    )
    header += struct.pack(">I", 0xAABBCCDD)  # 0x0c..0x0f: undocumented
    header += struct.pack(">H", country)  # 0x10
    body = bytearray(b"\x00")
    for prefix, text in names:
        body.extend(bytes([0x30 + prefix]))
        body.extend(b"=")
        body.extend(text)
        body.append(0x00)
    return header + bytes(body)


def selftest():
    record0 = _synthetic_record([(0, b"RODOS"), (0, b"LINDOS")])
    record1 = _synthetic_record([(1, b"ZIGHID\xcc")])  # Latin-1 Ì
    record2 = _synthetic_record(
        [(0, b"PARALIA AFANTOU"), (0, b"ARCHIPOLI:ELEOUSA")]
    )
    members = [zlib.compress(record, 6) for record in (record0, record1, record2)]
    data = members[0] + b"\x00" + members[1] + members[2]

    model = parse_payload(data, "synthetic")
    assert model["record_count"] == 3, model["record_count"]
    assert model["name_count"] == 5, model["name_count"]
    assert len(model["records"]) == 3
    assert all(record["country_code"] == 300 for record in model["records"])
    assert all(record["type_tag"] == TYPE_TAG for record in model["records"])
    assert model["records"][0]["parcel_w0"] == 0x1234
    assert model["records"][0]["u32_fields"][0]["value"] == 0x12345678
    texts = [name["text"] for record in model["records"] for name in record["names"]]
    assert texts == [
        "RODOS",
        "LINDOS",
        "ZIGHIDÌ",
        "PARALIA AFANTOU",
        "ARCHIPOLI:ELEOUSA",
    ], texts
    assert any(
        name["encoding"] == "latin-1"
        for record in model["records"]
        for name in record["names"]
    )
    first_opaque = model["records"][0]["opaque_binary"]
    assert any(item["offset"] == 0x06 for item in first_opaque), first_opaque

    preserved = encode_preserve(model)
    assert preserved == data, "preserve is not byte-identical"

    refused = 0
    try:
        encode_build(model)
    except BuildRefused as exc:
        assert EXIT_UNKNOWN_FIELDS == 3
        assert len(exc.items) == 5, exc.items
        assert all("names" in item["field"] for item in exc.items)
        refused = len(exc.items)
    else:
        raise AssertionError("build accepted a record with unmodelled names")

    clean = _synthetic_record([])
    clean_model = parse_payload(zlib.compress(clean, 6), "synthetic-clean")
    rebuilt = encode_build(clean_model)
    reparsed = parse_payload(rebuilt, "synthetic-clean-rebuilt")
    assert reparsed["records"][0]["country_code"] == 300
    assert reparsed["record_count"] == 1

    print(
        "section4 selftest: 3 records, 5 names, payload sha256 %s"
        % sha256(data)
    )
    print("  parse: OK (countries [300, 300, 300], type 0x0009)")
    print("  preserve: OK (byte-identical, %d bytes)" % len(preserved))
    print(
        "  build refusal: OK (%d unknown name fields, exit %d)"
        % (refused, EXIT_UNKNOWN_FIELDS)
    )
    print("  build nameless record: OK (country 300)")
    print("selftest: OK")
    return EXIT_OK


def build_parser():
    parser = argparse.ArgumentParser(
        description="Parse, preserve and verify ZE0 tile section 4.",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="run the synthetic no-vendor-data test",
    )
    subparsers = parser.add_subparsers(dest="command")

    parse_parser = subparsers.add_parser("parse", help="parse a raw payload")
    parse_parser.add_argument("payload", help="zlib-framed or plain payload")
    parse_parser.add_argument(
        "--json", action="store_true", help="write the model as JSON to stdout"
    )
    parse_parser.add_argument(
        "--json-out", metavar="FILE", help="write the model as JSON to FILE"
    )
    parse_parser.add_argument(
        "--min-name",
        type=int,
        default=DEFAULT_MIN_NAME,
        help="minimum name length (default %d)" % DEFAULT_MIN_NAME,
    )
    parse_parser.set_defaults(func=command_parse)

    encode_parser = subparsers.add_parser(
        "encode", help="encode from a parse model"
    )
    encode_parser.add_argument("mode", choices=("preserve", "build"))
    encode_parser.add_argument("model", help="JSON model from parse")
    encode_parser.add_argument("output", help="output payload path")
    encode_parser.set_defaults(func=command_encode)

    verify_parser = subparsers.add_parser(
        "verify", help="parse -> preserve round-trip and reference counts"
    )
    verify_parser.add_argument("payload")
    verify_parser.add_argument(
        "--min-name",
        type=int,
        default=DEFAULT_MIN_NAME,
        help="minimum name length (default %d)" % DEFAULT_MIN_NAME,
    )
    verify_parser.add_argument(
        "--reference-year",
        type=int,
        choices=tuple(sorted(REFERENCE_SECTION4)),
        help="compare measured counts with a reference year",
    )
    verify_parser.set_defaults(func=command_verify)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not getattr(args, "command", None):
        parser.error("choose parse, encode or verify (or use --selftest)")
    try:
        return args.func(args)
    except BuildRefused as exc:
        _report_refusal(exc)
        return EXIT_UNKNOWN_FIELDS
    except ShapeError as exc:
        print("section4: %s" % exc, file=sys.stderr)
        return EXIT_BAD_INPUT


if __name__ == "__main__":
    sys.exit(main())
