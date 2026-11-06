#!/usr/bin/env python3
"""Decode the name records inside the ``LCTBL001.DAT`` zlib streams (M4.18).

The compressed block at ``0x316600`` is a list of independent zlib streams.
Each stream is a *page* of up to 500 fixed-format records; a record is a
16-byte header, four fixed-size name slots and an opaque binary footer.

Record layout (big-endian fields, verified on the EU 2011 sample and used
unchanged on the 2014/2016 samples)::

    +0   u16  size_words   record length in bytes = 2 * value
    +2   u8   marker       always 0x01
    +3   u8   len1         name slot 1 length in 2-byte units (0 = absent)
    +4   u8   len2
    +5   u8   len3
    +6   u8   len4
    +7   7 x u8  attributes (roles UNKNOWN; kept verbatim)
    +14  u16  class        hierarchy level / record kind (semantics HYPOTHESIS)

Then the four names, in order, each occupying ``2 * lenN`` bytes.  A name is
Latin-2 text padded with ``0x00`` to an even length, so a slot is either the
name exactly (even length) or the name plus one NUL (odd length).  The rest of
the record (``size - 16 - sum(2 * lenN)`` bytes, 0..22, always even) is a
footer this tool keeps opaque; it is not decoded.

Evidence: ``docs/format/rdstm.md``, ``EXP-2026-11-06-M4.18-lctbl-framing``.

Usage::

    lctbl_records.py stats LCTBL001.DAT
    python3 tools/lctbl_records.py dump LCTBL001.DAT --stream 0 --limit 10
    python3 tools/lctbl_records.py roundtrip LCTBL001.DAT --stream 0
    python3 tools/lctbl_records.py verify LCTBL001.DAT
    python3 tools/lctbl_records.py --selftest
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lctbl_names  # noqa: E402  (sibling tool: stream scanner + sample pins)

# Pins for the EU 2011 sample.  ``verify`` fails loudly when they change.
EXPECTED_SHA256 = lctbl_names.EXPECTED_SHA256
EXPECTED_STREAMS = lctbl_names.EXPECTED_STREAMS
EXPECTED_PLAIN = lctbl_names.EXPECTED_PLAIN_BYTES
EXPECTED_RECORDS = 247_089
EXPECTED_FIELD_NONEMPTY = (36_461, 66_189, 243_907, 109_944)

HEADER = 16
SLOTS = 4
MARKER = 0x01
PAGE_LIMIT = 500
FOOTER_MAX = 22


class RecordError(ValueError):
    """A stream does not satisfy the documented record framing."""


def parse_stream(plain: bytes) -> list[dict]:
    """Split one decompressed stream into records (raises ``RecordError``)."""
    records: list[dict] = []
    offset = 0
    while offset < len(plain):
        if offset + HEADER > len(plain):
            raise RecordError(f"truncated header at {offset:#x}")
        header = plain[offset : offset + HEADER]
        size_words = int.from_bytes(header[0:2], "big")
        size = size_words * 2
        if size < HEADER:
            raise RecordError(f"record size {size} < {HEADER} at {offset:#x}")
        if offset + size > len(plain):
            raise RecordError(f"record size {size} overruns stream at {offset:#x}")
        if header[2] != MARKER:
            raise RecordError(f"marker {header[2]:#x} != {MARKER:#x} at {offset:#x}")
        lengths = list(header[3:7])
        body = plain[offset + HEADER : offset + size]
        slots = [2 * value for value in lengths]
        if sum(slots) > len(body):
            raise RecordError(f"name slots overrun record at {offset:#x}")
        names: list[bytes] = []
        position = 0
        for length in slots:
            slot = body[position : position + length]
            position += length
            name = slot.split(b"\x00")[0]
            pad = length - len(name)
            if pad not in (0, 1):
                raise RecordError(f"slot padding {pad} at {offset:#x}")
            if pad and (message := slot[len(name) :]) != b"\x00":
                raise RecordError(f"non-NUL padding {message!r} at {offset:#x}")
            if any(byte < 0x20 or 0x7F <= byte <= 0x9F for byte in name):
                raise RecordError(f"non-text byte in name at {offset:#x}")
            names.append(name)
        records.append(
            {
                "offset": offset,
                "size": size,
                "size_words": size_words,
                "marker": header[2],
                "lengths": lengths,
                "attrs": header[7:14],
                "class_code": int.from_bytes(header[14:16], "big"),
                "names": names,
                "footer": body[position:],
            }
        )
        offset += size
    return records


def encode_record(record: dict) -> bytes:
    """Rebuild one record from the decoded fields (inverse of ``parse_stream``)."""
    header = (
        record["size_words"].to_bytes(2, "big")
        + bytes([record["marker"]])
        + bytes(record["lengths"])
        + record["attrs"]
        + record["class_code"].to_bytes(2, "big")
    )
    body = bytearray()
    for name, half in zip(record["names"], record["lengths"]):
        slot = 2 * half
        if len(name) > slot:
            raise RecordError("name longer than its slot")
        body += name + b"\x00" * (slot - len(name))
    body += record["footer"]
    if len(header) + len(body) != record["size"]:
        raise RecordError("encoded record length does not match size_words")
    return header + bytes(body)


def encode_stream(records: list[dict]) -> bytes:
    return b"".join(encode_record(record) for record in records)


def load_streams(path: Path) -> tuple[bytes, list[dict]]:
    data = path.read_bytes()
    return data, lctbl_names.scan_streams(data)


def per_field_names(records: list[dict], index: int) -> list[bytes]:
    return [record["names"][index] for record in records]


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def cmd_stats(args: argparse.Namespace) -> int:
    path = Path(args.file)
    data, streams = load_streams(path)
    digest = hashlib.sha256(data).hexdigest()
    all_records: list[dict] = []
    total_names = 0
    for stream in streams:
        records = parse_stream(stream["data"])
        if args.page_limit and len(records) > PAGE_LIMIT:
            print(
                f"warning: stream {stream['offset']:#x} has {len(records)} records",
                file=sys.stderr,
            )
        all_records.extend(records)
        total_names += sum(1 for record in records for name in record["names"] if name)

    print(f"file        {path}")
    print(f"sha256      {digest}")
    print(f"streams     {len(streams)}")
    print(f"plain       {sum(stream['plain'] for stream in streams)} bytes")
    print(f"records     {len(all_records)}")
    print(f"names       {total_names} non-empty slots")
    print(f"record size min {min(r['size'] for r in all_records)} "
          f"max {max(r['size'] for r in all_records)} "
          f"mean {statistics.mean(r['size'] for r in all_records):.1f}")
    print()
    print("field  nonempty   empty   min median   mean   max  slot_max  distinct")
    for index in range(SLOTS):
        names = per_field_names(all_records, index)
        filled = [name for name in names if name]
        lengths = [len(name) for name in filled]
        slot_max = max(2 * record["lengths"][index] for record in all_records)
        print(
            f"{index + 1:5d} {len(filled):9d} {len(names) - len(filled):7d} "
            f"{min(lengths):5d} {statistics.median(lengths):6.0f} "
            f"{statistics.mean(lengths):6.1f} {max(lengths):6d} "
            f"{slot_max:9d} {len(set(filled)):9d}"
        )
    print()
    pages = collections.Counter()
    for stream in streams:
        pages[len(parse_stream(stream["data"]))] += 1
    print(f"records/stream  min {min(pages)} max {max(pages)} "
          f"full({PAGE_LIMIT}) {pages[PAGE_LIMIT]}")
    footers = collections.Counter(len(record["footer"]) for record in all_records)
    print(f"footer bytes    max {max(footers)} "
          f"values {sorted(footers)}")
    classes = collections.Counter(record["class_code"] for record in all_records)
    print(f"class values    {len(classes)} distinct")
    print("top classes     " + " ".join(
        f"{value}:{count}" for value, count in classes.most_common(8)
    ))
    combos = collections.Counter(
        tuple(bool(name) for name in record["names"]) for record in all_records
    )
    print("slot patterns   " + " ".join(
        f"{''.join('1' if present else '0' for present in pattern)}:{count}"
        for pattern, count in combos.most_common(6)
    ))
    if args.json:
        print(json.dumps(
            [
                {
                    "offset": record["offset"],
                    "size": record["size"],
                    "class": record["class_code"],
                    "names": [name.decode("iso-8859-2") for name in record["names"]],
                    "footer": record["footer"].hex(),
                }
                for record in all_records[: args.json]
            ],
            indent=1,
        ))
    return 0


def cmd_dump(args: argparse.Namespace) -> int:
    path = Path(args.file)
    _data, streams = load_streams(path)
    if args.stream >= len(streams):
        print(f"error: stream {args.stream} of {len(streams)}", file=sys.stderr)
        return 1
    records = parse_stream(streams[args.stream]["data"])
    for record in records[: args.limit or len(records)]:
        names = "\t".join(name.decode("iso-8859-2") for name in record["names"])
        print(
            f"{record['offset']:#06x}\t{record['size']:4d}\t"
            f"{record['class_code']:6d}\t{names}\t{record['footer'].hex()}"
        )
    return 0


def cmd_roundtrip(args: argparse.Namespace) -> int:
    path = Path(args.file)
    _data, streams = load_streams(path)
    targets = range(len(streams)) if args.all else [args.stream]
    failures = 0
    for index in targets:
        if index >= len(streams):
            print(f"error: stream {index} of {len(streams)}", file=sys.stderr)
            return 1
        plain = streams[index]["data"]
        rebuilt = encode_stream(parse_stream(plain))
        ok = rebuilt == plain
        failures += not ok
        print(
            f"stream {index:3d} @{streams[index]['offset']:#08x} "
            f"plain {len(plain):7d} rebuilt {len(rebuilt):7d} "
            f"{'OK' if ok else 'MISMATCH'}"
        )
        if not ok:
            print(f"  sha256 plain   {hashlib.sha256(plain).hexdigest()}")
            print(f"  sha256 rebuilt {hashlib.sha256(rebuilt).hexdigest()}")
    print("OK" if not failures else f"FAILED ({failures})")
    return 0 if not failures else 1


def cmd_verify(args: argparse.Namespace) -> int:
    path = Path(args.file)
    data, streams = load_streams(path)
    failures: list[str] = []
    if hashlib.sha256(data).hexdigest() != EXPECTED_SHA256:
        failures.append("sha256 differs from the documented EU 2011 sample")
    if len(streams) != EXPECTED_STREAMS:
        failures.append(f"{len(streams)} streams != {EXPECTED_STREAMS}")
    plain_total = sum(stream["plain"] for stream in streams)
    if plain_total != EXPECTED_PLAIN:
        failures.append(f"{plain_total} plain bytes != {EXPECTED_PLAIN}")

    records = [record for stream in streams for record in parse_stream(stream["data"])]
    if len(records) != EXPECTED_RECORDS:
        failures.append(f"{len(records)} records != {EXPECTED_RECORDS}")
    if sum(record["size"] for record in records) != plain_total:
        failures.append("record sizes do not tile the plain bytes")
    filled = tuple(sum(1 for name in per_field_names(records, i) if name)
                   for i in range(SLOTS))
    if filled != EXPECTED_FIELD_NONEMPTY:
        failures.append(f"non-empty per field {filled} != {EXPECTED_FIELD_NONEMPTY}")
    bad = [i for i, stream in enumerate(streams)
           if encode_stream(parse_stream(stream["data"])) != stream["data"]]
    if bad:
        failures.append(f"{len(bad)} streams do not round-trip (first {bad[0]})")

    print(f"streams  {len(streams)}")
    print(f"plain    {plain_total} bytes")
    print(f"records  {len(records)}")
    print(f"fields   {filled}")
    for failure in failures:
        print(f"FAIL {failure}")
    print("OK" if not failures else "FAILED")
    return 0 if not failures else 1


# --------------------------------------------------------------------------
# Synthetic self-test (no vendor data)
# --------------------------------------------------------------------------


def _build_record(names, class_code=100, attrs=b"\x01\x00\x00\x00\x00\x00\x00",
                  footer=b"") -> bytes:
    lengths = [(len(name) + 1) // 2 for name in names]
    body = b"".join(
        name + b"\x00" * (2 * half - len(name)) for name, half in zip(names, lengths)
    )
    size = HEADER + len(body) + len(footer)
    header = (
        (size // 2).to_bytes(2, "big") + b"\x01" + bytes(lengths) + attrs
        + class_code.to_bytes(2, "big")
    )
    return header + body + footer


def _selftest() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        if not condition:
            failures.append(name)

    plain = (
        _build_record([b"", b"", b"Evropa", b""], class_code=100)
        + _build_record([b"I/34", b"", b"Cesk\xe9 Budejovice", b"Jindrichuv Hradec"],
                        class_code=10300, footer=b"\x00\x52")
        + _build_record([b"", b"", b"Beranov\xfdch", b""], class_code=20110,
                        footer=b"\x00\xc2\x05\x8b")
    )
    records = parse_stream(plain)
    check("three records", len(records) == 3)
    check("tiles the stream", sum(record["size"] for record in records) == len(plain))
    check("names decode", records[1]["names"][2] == b"Cesk\xe9 Budejovice")
    check("even name has no pad", len(records[2]["names"][2]) == 2 * records[2]["lengths"][2])
    check("odd name padded", records[0]["names"][2] == b"Evropa"
          and records[0]["lengths"][2] * 2 == len(b"Evropa"))
    check("footer kept", records[1]["footer"] == b"\x00\x52")
    check("roundtrip", encode_stream(records) == plain)

    # A wrong size must fail loudly, not silently resynchronise.
    broken = bytearray(plain)
    broken[0:2] = (5).to_bytes(2, "big")
    try:
        parse_stream(bytes(broken))
        check("bad size rejected", False)
    except RecordError:
        check("bad size rejected", True)

    # A non-NUL pad byte must fail the slot check.
    odd = _build_record([b"", b"", b"abc", b""])
    slot_start = HEADER + len(b"abc")
    odd = odd[:slot_start] + b"\x01" + odd[slot_start + 1 :]
    try:
        parse_stream(odd)
        check("non-NUL pad rejected", False)
    except RecordError:
        check("non-NUL pad rejected", True)

    print(f"selftest: {'OK' if not failures else 'FAIL ' + ', '.join(failures)}")
    return 0 if not failures else 1


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true", help="synthetic checks")
    sub = parser.add_subparsers(dest="command")

    p_stats = sub.add_parser("stats", help="records, per-field counts and lengths")
    p_stats.add_argument("file")
    p_stats.add_argument("--json", type=int, default=0,
                         help="also print the first N records as JSON")
    p_stats.add_argument("--page-limit", type=int, default=PAGE_LIMIT,
                         help="warn when a stream exceeds this record count")
    p_stats.set_defaults(func=cmd_stats)

    p_dump = sub.add_parser("dump", help="one record per line (TSV)")
    p_dump.add_argument("file")
    p_dump.add_argument("--stream", type=int, default=0)
    p_dump.add_argument("--limit", type=int, default=0)
    p_dump.set_defaults(func=cmd_dump)

    p_rt = sub.add_parser("roundtrip", help="decode + re-encode a stream")
    p_rt.add_argument("file")
    p_rt.add_argument("--stream", type=int, default=0)
    p_rt.add_argument("--all", action="store_true")
    p_rt.set_defaults(func=cmd_roundtrip)

    p_verify = sub.add_parser("verify", help="documented totals + all-stream round-trip")
    p_verify.add_argument("file")
    p_verify.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return _selftest()
    if not getattr(args, "func", None):
        build_parser().print_help()
        return 2
    try:
        return args.func(args)
    except (OSError, RecordError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
