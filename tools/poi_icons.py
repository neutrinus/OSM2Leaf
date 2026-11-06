#!/usr/bin/env python3
"""`BICON001` icon table and `POINT` category/brand ids.

`BICON001.DAT` is a flat PNG container of 103 32x32 icons.  Most of them are
chain logos (fuel, supermarket, hotel); a few are generic glyphs (fuel pump,
restaurant, pharmacy cross, parking, hotel bed).

`POINT0nn` records are length-prefixed bit/byte mixtures.  The facility-name
block is bracketed by two 16-bit codes:

    <tag> <category:u16> NAME \\0 [house@street] <brand:u16>

The first code is the top-level category (petrol station, restaurant, hotel);
the trailing code is the brand sub-category (e.g. 0x0dad = Best Western).  For
a record whose brand equals its category, both copies are the same value.

This tool reads the icon container and the extracted (uncompressed) POINT
files; it never writes vendor data.  The icon index -> logo identification is
manual, recorded in ``MAPPING`` and in ``docs/format/assets.md`` /
``EXP-2026-11-06-M4.10-poi-icons.md``.

Usage::

    python3 tools/poi_icons.py bicon BICON001/BICON001.DAT
    python3 tools/poi_icons.py codes /tmp/poi
    python3 tools/poi_icons.py verify /tmp/poi
    python3 tools/poi_icons.py --selftest

``/tmp/poi`` must contain ``POINT0nn.DAT`` files already extracted with
``tools/cmpind.py extract``.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import zlib

from collections import Counter, defaultdict
from pathlib import Path

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
BICON_COUNT_OFF = 0x100A
BICON_TABLE_OFF = 0x100E
BICON_DATA_OFF = 0x1408
ICON_UNIT = 2  # table start/size are stored in 2-byte units

#: Verified category/brand code -> BICON index -> visible logo.
#: name_prefix is the record name used to count occurrences.
MAPPING = [
    # generic categories
    (0x0190, 0, "petrol station (generic)", ""),
    (0x0391, 18, "restaurant/cafe (generic)", ""),
    (0x0DAC, 21, "hotel (unbranded)", ""),
    # fuel / shop brands (0x01xx)
    (0x0193, 1, "BP", "BP"),
    (0x0195, 2, "ASDA", "ASDA"),
    (0x01A1, 3, "Carrefour", "CARREFOUR"),
    (0x01BC, 6, "Aral", "ARAL"),
    (0x01BE, 7, "Intermarche", "INTERMARCH"),
    (0x01CF, 8, "Preem", "PREEM"),
    (0x01D9, 9, "Tamoil", "TAMOIL"),
    (0x01E2, 12, "Cora", "CORA"),
    # hotel brands (0x0dxx / 0x0exx)
    (0x0DAD, 22, "Best Western", "BEST WESTERN"),
    (0x0DB1, 23, "Crowne Plaza", "CROWNE PLAZA"),
    (0x0DB7, 24, "Hilton", "HILTON"),
    (0x0DB8, 25, "Holiday Inn", "HOLIDAY INN"),
    (0x0DBB, 26, "InterContinental", "INTERCONTINENTAL"),
    (0x0DBE, 27, "balladins", "BALLADINS"),
    (0x0DBF, 28, "Quality", "QUALITY"),
    (0x0DC6, 31, "Sheraton", "SHERATON"),
    (0x0DCC, 33, "Concorde", "CONCORDE"),
    (0x0DC3, 35, "Campanile", "CAMPANILE"),
    (0x0DD1, 34, "Comfort", "COMFORT"),
    (0x0DDA, 36, "Golden Tulip", "GOLDEN TULIP"),
    (0x0DBC, 37, "B&B Hotels", "B & B"),
    (0x0DF2, 39, "Mercure", "MERCURE"),
    (0x0E0D, 44, "Scandic", "SCANDIC"),
    (0x0DBD, 62, "Marriott", "MARRIOTT"),
    (0x0DC0, 29, "Radisson Blu (first block)", "RADISSON BLU"),
    (0x0E2E, 57, "Radisson Blu (second block)", "RADISSON"),
    (0x0E2A, 53, "Radisson Edwardian", "RADISSON"),
    (0x0E24, 47, "Clarion", "CLARION"),
    (0x0E29, 51, "Park Inn", "PARK INN"),
    (0x0E32, 61, "Andaz", "ANDAZ"),
    (0x0E39, 65, "Citadines", "CITADINES"),
]

CODE_NAME_RE = re.compile(rb"([\x00-\xff]{2})([A-Z][A-Za-z0-9 &'\x2c./-]{3,})")
POINT_TAGS = (0x60, 0x68)


def read_bicon(path):
    """Return (count, icons) for a BICON001.DAT file.

    ``icons`` is a list of dicts with the table start/size and, for PNG
    entries, width/height parsed from the IHDR chunk.
    """
    data = Path(path).read_bytes()
    if len(data) < BICON_DATA_OFF:
        raise ValueError("short BICON001")
    count = struct.unpack_from(">H", data, BICON_COUNT_OFF)[0]
    icons = []
    for i in range(count):
        pos = BICON_TABLE_OFF + i * 8
        start, size = struct.unpack_from(">II", data, pos)
        off = BICON_DATA_OFF + start * ICON_UNIT
        length = size * ICON_UNIT
        icon = {"index": i, "offset": off, "size": length, "png": False}
        if data[off:off + 8] == PNG_MAGIC and off + 24 <= len(data):
            w, h = struct.unpack_from(">II", data, off + 16)
            icon.update(png=True, width=w, height=h)
        icons.append(icon)
    return count, icons


def iter_streams(data):
    """Yield zlib payloads embedded in a logical .DAT file."""
    for match in re.finditer(rb"\x78[\x01\x9c\xda\x5e]", data):
        try:
            out = zlib.decompressobj().decompress(data[match.start():match.start() + 400000])
        except zlib.error:
            continue
        if 2000 < len(out) < 400000:
            yield match.start(), out


def iter_point_records(blob):
    """Yield POINT records (tag, bytes) from one decompressed stream."""
    p = 0
    while p + 2 < len(blob):
        tag = blob[p]
        length = blob[p + 1] * 2
        if tag not in POINT_TAGS or length < 8 or p + length > len(blob):
            break
        yield tag, blob[p:p + length]
        p += length


def iter_named_records(path):
    """Yield (category, brand, name) tuples from one extracted POINT0nn.DAT."""
    data = Path(path).read_bytes()
    for _, blob in iter_streams(data):
        for tag, rec in iter_point_records(blob):
            if tag != 0x60:
                continue
            brand = int.from_bytes(rec[-2:], "big")
            if brand == 0xFFFF:
                continue
            for match in CODE_NAME_RE.finditer(rec[18:]):
                category = int.from_bytes(match.group(1), "big")
                if category == 0xFFFF:
                    continue
                yield category, brand, match.group(2).decode("latin1")


def scan(directory, shards=None):
    """Return {brand: Counter(names)} for POINT0nn.DAT files in directory."""
    names = defaultdict(Counter)
    for path in sorted(Path(directory).glob("POINT*.DAT")):
        if shards and path.stem[5:8] not in shards:
            continue
        for _, brand, name in iter_named_records(path):
            names[brand][name] += 1
    return names


def count_for(names, code, prefix):
    counter = names.get(code)
    if not counter:
        return 0
    if not prefix:
        return sum(counter.values())
    return sum(n for name, n in counter.items() if name.upper().startswith(prefix))


def format_bicon(count, icons):
    dims = Counter((icon["width"], icon["height"]) for icon in icons if icon["png"])
    lines = [f"icons={count} png={sum(1 for i in icons if i['png'])} "
             f"sizes={dict(dims)}"]
    for icon in icons:
        if icon["png"]:
            lines.append(
                f"{icon['index']:3d} off=0x{icon['offset']:05x} "
                f"size={icon['size']:4d} {icon['width']}x{icon['height']}")
        else:
            lines.append(f"{icon['index']:3d} off=0x{icon['offset']:05x} "
                         f"size={icon['size']:4d} (not PNG)")
    return "\n".join(lines)


def cmd_bicon(args):
    count, icons = read_bicon(args.bicon)
    print(format_bicon(count, icons))
    return 0


def cmd_codes(args):
    names = scan(args.directory, set(args.shards) if args.shards else None)
    for code, icon, label, prefix in MAPPING:
        n = count_for(names, code, prefix)
        top = ""
        counter = names.get(code)
        if counter:
            top = counter.most_common(1)[0][0]
        print(f"0x{code:04x} {code:5d} icon={icon:3d} {label:24s} n={n:6d} {top[:40]}")
    return 0


def cmd_verify(args):
    count, icons = read_bicon(args.bicon)
    names = scan(args.directory, set(args.shards) if args.shards else None)
    problems = []
    for code, icon, label, prefix in MAPPING:
        if icon >= count or not icons[icon]["png"]:
            problems.append(f"icon {icon} missing for {label}")
        n = count_for(names, code, prefix)
        if n == 0:
            problems.append(f"code 0x{code:04x} ({label}) not seen in POINT")
    print(f"checked {len(MAPPING)} mappings against {count} icons")
    if problems:
        for problem in problems:
            print("FAIL", problem)
        return 1
    print("RESULT: PASS")
    return 0


# ---------------------------------------------------------------------------
# Synthetic self-test
# ---------------------------------------------------------------------------


def _png(w, h):
    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + b"\x00" * w * 4 for _ in range(h))
    return (PNG_MAGIC + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _record(name, category, brand, tag=0x60):
    """Build a minimal POINT record with a name block."""
    body = b"\x02" + category.to_bytes(2, "big") + name.encode("latin1") + b"\x00"
    if len(body) % 2:
        body += b"\x00"
    rec = bytes([tag, 0]) + b"\x00" * 18 + body + brand.to_bytes(2, "big")
    return rec[:1] + bytes([len(rec) // 2]) + rec[2:]


def selftest():
    import tempfile

    # 1. BICON container with three icons.
    blobs = []
    for w in (32, 30, 32):
        blob = _png(w, w)
        if len(blob) % 2:
            blob += b"\x00"
        blobs.append(blob)
    table = b""
    start = 0
    for blob in blobs:
        table += struct.pack(">II", start // ICON_UNIT, len(blob) // ICON_UNIT)
        start += len(blob)
    header = bytearray(BICON_DATA_OFF)
    struct.pack_into(">H", header, BICON_COUNT_OFF, len(blobs))
    header[BICON_TABLE_OFF:BICON_TABLE_OFF + len(table)] = table
    with tempfile.TemporaryDirectory() as tmp:
        bicon = Path(tmp) / "BICON001.DAT"
        bicon.write_bytes(bytes(header) + b"".join(blobs))
        count, icons = read_bicon(bicon)
        assert count == 3, count
        assert icons[0]["png"] and icons[0]["width"] == 32
        assert icons[1]["width"] == 30 and icons[1]["height"] == 30
        assert icons[2]["offset"] == BICON_DATA_OFF + len(blobs[0]) + len(blobs[1])

        # 2. POINT stream large enough for the 2 KiB stream filter.
        unit = (_record("BEST WESTERN TEST", 0x0DAC, 0x0DAD)
                + _record("HILTON TEST", 0x0DAC, 0x0DB7, tag=0x68)
                + _record("PLAIN HOTEL", 0x0DAC, 0x0DAC))
        records = unit * 20
        point = Path(tmp) / "POINT999.DAT"
        point.write_bytes(zlib.compress(records))

        got = list(iter_named_records(point))
        assert (0x0DAC, 0x0DAD, "BEST WESTERN TEST") in got, got
        names = scan(tmp)
        assert count_for(names, 0x0DAD, "BEST WESTERN") == 20
        assert count_for(names, 0x0DAC, "") == 20
        # the 0x68 twin is parsed but skipped by the name scanner
        twin = _record("HILTON TEST", 0x0DAC, 0x0DB7, tag=0x68)
        assert list(iter_point_records(zlib.decompress(zlib.compress(twin))))[0][0] == 0x68

    print("selftest: OK (bicon table, POINT records, mapping counts)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true", help="run synthetic tests")
    sub = parser.add_subparsers(dest="command")

    bicon = sub.add_parser("bicon", help="list the BICON001 icon table")
    bicon.add_argument("bicon")
    bicon.set_defaults(func=cmd_bicon)

    codes = sub.add_parser("codes", help="count the mapped codes in extracted POINT files")
    codes.add_argument("directory")
    codes.add_argument("--shards", nargs="*", help="three-digit shard numbers")
    codes.set_defaults(func=cmd_codes)

    verify = sub.add_parser("verify", help="check every mapping against BICON and POINT")
    verify.add_argument("directory")
    verify.add_argument("--bicon", default="BICON001/BICON001.DAT")
    verify.add_argument("--shards", nargs="*")
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
