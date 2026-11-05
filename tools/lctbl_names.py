#!/usr/bin/env python3
"""Decode ``LCTBL001.DAT`` (Leaf ZE0, EU 2011 image).

Verified against ``LCTBL001.DAT`` (7,489,024 bytes,
SHA-256 ``8cab17754114b5f7ca47d4f46d55c95c6acf841629e1fcc42e6da45063353e9d``)
from the image ``105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307``.

Layout (see docs/format/rdstm.md):

    0x000000  512-byte common Clarion/Hitachi header
    0x000200  0xff fill
    0x001000  catalog: 90 x ("Location Data" table descriptor [+ 12 columns])
    0x004600  binary index/geometry block (not decoded)
    0x316600  517 independent zlib streams (place + street names)
    0x7217df  0xff padding to end of file

This tool:

* ``streams``  lists every zlib stream and writes the concatenated plain text;
* ``names``    extracts NUL-terminated name strings from the plain text;
* ``verify``   re-runs the stream scan and asserts the documented totals.

Record framing inside the plain text is only partially decoded (see docs/format/rdstm.md):
each record is a 16-byte metadata block, a 2-byte class code and one or more
NUL-terminated Latin-2 strings.  ``names`` therefore extracts strings, not
whole records, and reports the two bytes that precede each string.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
import zlib
from pathlib import Path

EXPECTED_SHA256 = "8cab17754114b5f7ca47d4f46d55c95c6acf841629e1fcc42e6da45063353e9d"
EXPECTED_SIZE = 7_489_024
EXPECTED_STREAMS = 517
EXPECTED_PLAIN_BYTES = 11_481_060
FIRST_STREAM = 0x316600

# A name record is a 16-byte metadata block, a u16 record type and a
# NUL-terminated name.  The last six metadata bytes are zero in every
# observed record; that is the anchor used by the extractor.


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_streams(data: bytes, start: int = FIRST_STREAM) -> list[dict]:
    """Walk zlib streams sequentially, resynchronising on 0x78 0x9c."""
    streams: list[dict] = []
    offset = start
    while offset < len(data) - 2:
        if data[offset] != 0x78:
            nxt = data.find(b"\x78\x9c", offset)
            if nxt < 0:
                break
            offset = nxt
        try:
            engine = zlib.decompressobj()
            payload = engine.decompress(data[offset:])
        except zlib.error:
            nxt = data.find(b"\x78\x9c", offset + 1)
            if nxt < 0:
                break
            offset = nxt
            continue
        if not engine.eof:
            nxt = data.find(b"\x78\x9c", offset + 1)
            if nxt < 0:
                break
            offset = nxt
            continue
        consumed = len(data) - offset - len(engine.unused_data)
        streams.append(
            {
                "offset": offset,
                "compressed": consumed,
                "plain": len(payload),
                "data": payload,
            }
        )
        offset += consumed
    return streams


def normalise(run: bytes) -> tuple[bytes, str]:
    """Strip the 2-byte street-record prefix and return (name, prefix hex)."""
    if len(run) >= 3 and 0x4A <= run[0] <= 0x50 and 0x80 <= run[1] <= 0x9F:
        return run[2:], run[:2].hex()
    return run, ""


def looks_like_name(run: bytes) -> bool:
    """Reject binary noise that happens to be printable."""
    if not 2 <= len(run) <= 120:
        return False
    if any(0x80 <= byte <= 0x9F for byte in run):
        return False
    letters_and_digits = sum(
        1
        for byte in run
        if 0x30 <= byte <= 0x39 or 0x41 <= byte <= 0x5A or 0x61 <= byte <= 0x7A
    )
    return letters_and_digits >= 2


def extract_names(plain: bytes) -> list[dict]:
    """Extract NUL-terminated strings and their 2-byte prefix.

    The prefix is the class code for the first string of a record and the tail
    of the previous string's record for continuation strings, so treat it as
    advisory only.
    """
    records: list[dict] = []
    pattern = re.compile(rb"[\x20-\xff]{2,200}\x00")
    for match in pattern.finditer(plain):
        start = match.start()
        run, inline_prefix = normalise(match.group()[:-1])
        if not looks_like_name(run):
            continue
        records.append(
            {
                "offset": start,
                "prefix": inline_prefix or plain[max(0, start - 2) : start].hex(),
                "name": run.decode("latin-1"),
            }
        )
    return records


def cmd_streams(args: argparse.Namespace) -> int:
    data = Path(args.file).read_bytes()
    if len(data) != EXPECTED_SIZE:
        print(f"warning: size {len(data)} != documented {EXPECTED_SIZE}", file=sys.stderr)
    digest = sha256(Path(args.file))
    if digest != EXPECTED_SHA256:
        print(f"warning: sha256 {digest} != documented sample", file=sys.stderr)

    streams = scan_streams(data)
    total_plain = sum(s["plain"] for s in streams)
    print(f"file            {args.file}")
    print(f"sha256          {digest}")
    print(f"streams         {len(streams)}")
    print(f"plain bytes     {total_plain}")
    print(f"first stream    {streams[0]['offset']:#x}")
    print(f"last stream     {streams[-1]['offset']:#x}")
    for stream in streams[:3]:
        print(
            f"  {stream['offset']:#08x} -> {stream['plain']:6d} bytes "
            f"{stream['data'][:52]!r}"
        )
    if args.output:
        out = Path(args.output)
        out.write_bytes(b"".join(s["data"] for s in streams))
        print(f"wrote           {out} ({total_plain} bytes)")
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "offset": s["offset"],
                        "compressed": s["compressed"],
                        "plain": s["plain"],
                    }
                    for s in streams
                ],
                indent=1,
            )
        )
    return 0


def cmd_names(args: argparse.Namespace) -> int:
    data = Path(args.file).read_bytes()
    streams = scan_streams(data)
    plain = b"".join(s["data"] for s in streams)
    records = extract_names(plain)

    print(f"plain bytes     {len(plain)}")
    print(f"strings         {len(records)}")

    if records:
        lengths = [len(r["name"]) for r in records]
        print(
            f"name length     min {min(lengths)} median "
            f"{statistics.median(lengths):.0f} max {max(lengths)}"
        )
        prefixes = {}
        for record in records:
            prefixes[record["prefix"]] = prefixes.get(record["prefix"], 0) + 1
        print("top prefixes")
        for value, count in sorted(prefixes.items(), key=lambda kv: -kv[1])[:8]:
            print(f"  {value}  {count:7d}")

    if args.contains:
        needle = args.contains.encode("latin-1")
        records = [r for r in records if needle in r["name"].encode("latin-1")]

    if args.output:
        out = Path(args.output)
        with out.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(f"{record['offset']:#08x}\t{record['prefix']}\t{record['name']}\n")
        print(f"wrote           {out} ({len(records)} rows)")

    if args.sample:
        for record in records[: args.sample]:
            print(f"  {record['offset']:#08x} [{record['prefix']}] {record['name']}")
    return 0


def cmd_catalog(args: argparse.Namespace) -> int:
    """Print the catalog of 'Location Data' descriptors and their columns."""
    data = Path(args.file).read_bytes()
    name = b"Location Data"
    positions: list[int] = []
    index = 0
    while True:
        index = data.find(name, index)
        if index < 0:
            break
        positions.append(index)
        index += 1

    print(f"'Location Data' descriptors: {len(positions)}")
    codes: list[str] = []
    for position in positions:
        header = data[position - 32 : position]
        code = header[28:30]
        codes.append(code.hex())
        if args.verbose:
            print(
                f"  {position:#08x} name_len={data[position - 2]} "
                f"code={code.hex()} header={header.hex(' ')}"
            )
    print("distinct codes:", len(set(codes)))
    print("  " + " ".join(codes[:30]))

    vocabulary = [
        b"kind code", b"road no", b"road name", b"first name",
        b"second name", b"area ref", b"liner ref", b"negative offset",
        b"positive offset", b"urban", b"exit/junction no",
        b"Inter-section code",
    ]
    fields: list[str] = []
    for position in positions:
        window = data[position : position + 512]
        found = []
        for word in vocabulary:
            where = window.find(word)
            if where < 0:
                break
            found.append((where, word.decode("ascii")))
        if len(found) == len(vocabulary):
            fields = [word for _, word in sorted(found)]

    print(f"column descriptors of the first inline schema ({len(fields)}):")
    for position, field in enumerate(fields):
        print(f"  {position:2d} {field}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    data = Path(args.file).read_bytes()
    failures: list[str] = []
    if len(data) != EXPECTED_SIZE:
        failures.append(f"size {len(data)} != {EXPECTED_SIZE}")
    if sha256(Path(args.file)) != EXPECTED_SHA256:
        failures.append("sha256 does not match the documented sample")

    streams = scan_streams(data)
    if len(streams) != EXPECTED_STREAMS:
        failures.append(f"{len(streams)} streams != {EXPECTED_STREAMS}")
    total = sum(s["plain"] for s in streams)
    if total != EXPECTED_PLAIN_BYTES:
        failures.append(f"{total} plain bytes != {EXPECTED_PLAIN_BYTES}")

    plain = b"".join(s["data"] for s in streams)
    if not plain.startswith(b"\x00\x0b\x01\x00\x00\x03"):
        failures.append("unexpected first record bytes")
    if b"Evropa" not in plain[:64]:
        failures.append("'Evropa' not in the first record")
    if b"Praha" not in plain:
        failures.append("'Praha' not found in the name table")

    records = extract_names(plain)
    if len(records) < 200_000:
        failures.append(f"only {len(records)} name strings extracted")
    if not any(r["name"] == "Praha" for r in records):
        failures.append("'Praha' missing from the extracted strings")

    print(f"streams   {len(streams)}")
    print(f"plain     {total} bytes")
    print(f"records   {len(records)}")
    for failure in failures:
        print(f"FAIL {failure}")
    print("OK" if not failures else "FAILED")
    return 0 if not failures else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_streams = sub.add_parser("streams", help="list and dump the zlib streams")
    p_streams.add_argument("file")
    p_streams.add_argument("-o", "--output", help="write the concatenated plain text")
    p_streams.add_argument("--json", action="store_true")
    p_streams.set_defaults(func=cmd_streams)

    p_names = sub.add_parser("names", help="extract name records")
    p_names.add_argument("file")
    p_names.add_argument("-o", "--output", help="write a TSV of records")
    p_names.add_argument("--contains", help="keep strings containing this text")
    p_names.add_argument("--sample", type=int, default=0)
    p_names.set_defaults(func=cmd_names)

    p_catalog = sub.add_parser("catalog", help="list the 'Location Data' schema catalog")
    p_catalog.add_argument("file")
    p_catalog.add_argument("--verbose", action="store_true")
    p_catalog.set_defaults(func=cmd_catalog)

    p_verify = sub.add_parser("verify", help="re-check documented totals")
    p_verify.add_argument("file")
    p_verify.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
