#!/usr/bin/env python3
"""Decode the `ADDRE0nn.DAT` container, directory and address records.

What is decoded here (see `docs/format/refer.md`):

* container: the `.cmp`/`.ind` pair, the inner index zlib chain, the single
  0x100-byte schema block and the inner record zlib chain;
* the **12-byte directory cells** at `0x1108`
  (`u8 initial, u8 0, u16 n, u16 0, u16 offset, u16 length, u16 0`), with the
  `length = 0xffff` sentinel on the last row;
* the **6-byte cells** in the table at `0x2000` addressed by
  `offset`/`length`; two shapes are recognised: `(0, value, count)` and
  `(pointer, 0xff00, 0)`, where the pointer is 6-byte aligned;
* the address records (`c0`/`c8`, size `2 * L`), their coordinate id,
  point tokens (`02..05 40 XX YY`), house-range tokens (`06/07 54/58
  :N:;:M:`) and the `03 LL 00 ff` name section;
* the per-file trailer (`01 f4 00 00` marker, then 12-byte
  `(start, length, value)` rows that form a contiguous partition): one row
  per record zlib block, `length` = compressed size / 2 and `value` =
  uncompressed size / 2, both in 16-bit words.

The *semantics* of the point magnitudes and of the trailer key space are
still `UNKNOWN`; the tool prints them raw and never invents coordinates.

Usage::

    python3 tools/addre.py layout  REFER001/ADDRE001.DAT.cmp
    python3 tools/addre.py table   REFER001/ADDRE001.DAT.cmp
    python3 tools/addre.py cells   REFER001/ADDRE001.DAT.cmp --id A
    python3 tools/addre.py records REFER001/ADDRE001.DAT.cmp --limit 5
    python3 tools/addre.py stats   REFER001/ADDRE001.DAT.cmp
    python3 tools/addre.py trailer REFER001/ADDRE001.DAT.cmp
    python3 tools/addre.py verify  REFER001/ADDRE001.DAT.cmp
    python3 tools/addre.py --selftest

Exit codes: ``0`` success, ``1`` a verification check failed, ``2`` bad
input.  Vendor data is never written.
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

TABLE_OFF = 0x1108
CELL_OFF = 0x2000
SCHEMA_SIG = bytes.fromhex("ffff0010ffffffff00000000ffffffff")
CHAIN_SIG = b"N \x00\x00"
TRAILER_SIG = bytes.fromhex("01f40000")
INDEX_REC = 22
CELL_SIZE = 6

TAG_REC_FULL = 0xC0
TAG_REC_PART = 0xC8
RANGE_SUBTYPES = (0x54, 0x58, 0x64, 0x68)


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


class AddreError(Exception):
    pass


def load_blob(path: Path) -> bytes:
    """Return the logical file bytes (decompressed for a `.cmp`)."""
    path = Path(path)
    if path.suffix != ".cmp":
        return path.read_bytes()
    ind_path = path.with_suffix("").with_suffix(".ind")
    if not ind_path.exists():
        alt = Path(str(path)[:-4] + ".ind")
        if alt.exists():
            ind_path = alt
        else:
            raise AddreError(f"missing index file for {path}")
    ind = ind_path.read_bytes()
    if len(ind) < 16:
        raise AddreError(f"{ind_path}: shorter than the 16-byte header")
    usize, csize, count, chunk = struct.unpack_from("<IIII", ind, 0)
    if count == 0 or 16 + 4 * count > len(ind):
        raise AddreError(f"{ind_path}: bad chunk count {count}")
    offs = struct.unpack_from(f"<{count}I", ind, 16)
    packed = path.read_bytes()
    parts = []
    for i, start in enumerate(offs):
        end = offs[i + 1] if i + 1 < len(offs) else len(packed)
        if start > end or end > len(packed):
            raise AddreError(f"{path}: chunk {i} outside the file")
        try:
            parts.append(zlib.decompress(packed[start:end]))
        except zlib.error as exc:
            raise AddreError(f"{path}: chunk {i}: {exc}") from exc
    blob = b"".join(parts)
    if len(blob) != usize:
        raise AddreError(f"{path}: logical size {len(blob)} != {usize}")
    return blob


# --------------------------------------------------------------------------
# Inner zlib chains
# --------------------------------------------------------------------------


def _zlib_at(blob: bytes, pos: int) -> tuple[bytes, int] | None:
    if pos >= len(blob) or blob[pos] != 0x78 or blob[pos + 1] not in (0x01, 0x5E, 0x9C, 0xDA):
        return None
    dec = zlib.decompressobj()
    try:
        data = dec.decompress(blob[pos:])
    except zlib.error:
        return None
    if not dec.eof or len(data) == 0:
        return None
    return data, len(blob) - len(dec.unused_data)


def _chain_from(blob: bytes, pos: int, stop: int) -> list[tuple[int, int, bytes]]:
    """Decompress consecutive zlib streams from ``pos`` up to ``stop``."""
    out = []
    while pos < stop:
        hit = None
        for pad in range(0, 4):
            hit = _zlib_at(blob, pos + pad)
            if hit:
                break
        if not hit:
            break
        data, end = hit
        out.append((pos, end, data))
        pos = end
    return out


def _find_index_chain(blob: bytes, schema: int) -> list[tuple[int, int, bytes]]:
    """Locate the index chain header (last ``4e 20 00 00`` before schema)."""
    search = schema
    for _ in range(256):
        pos = blob.rfind(CHAIN_SIG, 0, search)
        if pos < 0:
            break
        for delta in range(8, 8192, 4):
            if _zlib_at(blob, pos + delta):
                return _chain_from(blob, pos + delta, schema)
        search = pos
    raise AddreError("index zlib chain not found before the schema block")


def sections(blob: bytes) -> dict:
    schema = blob.find(SCHEMA_SIG)
    if schema < 0:
        raise AddreError("schema block signature not found")
    index = _find_index_chain(blob, schema)
    records = _chain_from(blob, schema + 0x100, len(blob))
    if not index:
        raise AddreError("empty index chain")
    if not records:
        raise AddreError("empty record chain")
    return {
        "schema": schema,
        "index": index,
        "records": records,
        "index_bytes": b"".join(d for _, _, d in index),
        "record_bytes": b"".join(d for _, _, d in records),
    }


# --------------------------------------------------------------------------
# 12-byte directory and 6-byte cells
# --------------------------------------------------------------------------


def read_table(blob: bytes) -> list[dict]:
    rows = []
    pos = TABLE_OFF
    while pos + 12 <= len(blob):
        ident, zero, count, block, offset, length, tail = struct.unpack_from(
            ">BBHHHHH", blob, pos
        )
        rows.append(
            {
                "pos": pos,
                "id": ident,
                "initial": chr(ident) if 32 <= ident < 127 else None,
                "count": count,
                "block": block,
                "offset": offset,
                "length": length,
                "last": length == 0xFFFF,
            }
        )
        pos += 12
        if length == 0xFFFF:
            return rows
    raise AddreError("directory table is not terminated")


def read_cells(blob: bytes, offset: int, length: int, base: int = CELL_OFF) -> list[dict]:
    cells = []
    for k in range(0, length, CELL_SIZE):
        pos = base + offset + k
        raw = blob[pos : pos + CELL_SIZE]
        if len(raw) < CELL_SIZE:
            raise AddreError(f"cell at {pos:#x} outside the file")
        a, b, c = struct.unpack(">3H", raw)
        if b == 0xFF00 and a != 0:
            kind = "pointer"
        elif b == 0xFF00:
            kind = "empty"
        elif a <= 3:
            kind = "value"
        else:
            kind = "unknown"
        cells.append({"pos": pos, "raw": raw, "a": a, "b": b, "c": c, "kind": kind})
    return cells


# --------------------------------------------------------------------------
# Address records
# --------------------------------------------------------------------------


def split_records(data: bytes) -> list[bytes]:
    out = []
    pos = 0
    while pos < len(data):
        tag = data[pos]
        if tag not in (TAG_REC_FULL, TAG_REC_PART):
            raise AddreError(f"record at {pos:#x}: bad tag {tag:#04x}")
        if pos + 2 > len(data):
            raise AddreError(f"record at {pos:#x}: truncated length")
        length = data[pos + 1]
        end = pos + 2 * length
        if end > len(data):
            raise AddreError(f"record at {pos:#x}: length {length} runs past the stream")
        out.append(data[pos:end])
        pos = end
    return out


def _range_string(rec: bytes, start: int) -> tuple[bytes, int]:
    i = start
    while i < len(rec) and rec[i] in b"0123456789:;":
        i += 1
    return rec[start:i], i


def parse_record(rec: bytes) -> dict:
    if len(rec) < 2 or rec[0] not in (TAG_REC_FULL, TAG_REC_PART):
        raise AddreError("not an address record")
    full = rec[0] == TAG_REC_FULL
    out = {
        "tag": rec[0],
        "path": "c0" if full else "c8",
        "length": rec[1],
        "coord": None,
        "points": [],
        "ranges": [],
        "name": None,
        "name_half": None,
        "unknown": 0,
    }
    i = 2
    while i < len(rec) and i + 3 < len(rec):
        if all(byte in (0x00, 0xFF) for byte in rec[i:]):
            break
        if (
            rec[i] in (0x03, 0x04)
            and rec[i + 2] == 0x00
            and rec[i + 3] == 0xFF
            and 0 < rec[i + 1] <= 0x7F
        ):
            half = rec[i + 1]
            start = len(rec) - 2 * half
            if start > i + 4:
                text = rec[start:]
                if text.endswith(b"\x00"):
                    text = text[:-1]
                if text and all(byte >= 0x20 and byte != 0x7F for byte in text):
                    out["name_half"] = half
                    out["name_header"] = rec[i + 4 : start]
                    out["name"] = text
                    break
        tag = rec[i]
        sub = rec[i + 1]
        if sub == 0x40:
            out["points"].append(
                {
                    "tag": tag,
                    "pos": i,
                    "marker": sub,
                    "x": rec[i + 2],
                    "y": rec[i + 3],
                }
            )
            i += 4
        elif 0x06 <= tag <= 0x1F:
            if sub in RANGE_SUBTYPES:
                text, end = _range_string(rec, i + 4)
                out["ranges"].append(
                    {"prefix": tag, "subtype": sub, "text": text, "pos": i}
                )
                i = end
                if i < len(rec) and rec[i] == 0:
                    i += 1
            else:
                if i + 6 > len(rec):
                    out["unknown"] += 1
                    break
                if out["coord"] is None:
                    out["coord"] = struct.unpack_from(">HH", rec, i + 2)
                out.setdefault("extra_ids", []).append(
                    {"pos": i, "tag": tag, "subtype": sub, "value": rec[i + 2 : i + 6].hex()}
                )
                i += 6
        else:
            out["unknown"] += 1
            i += 1
    return out


# --------------------------------------------------------------------------
# Trailer
# --------------------------------------------------------------------------


def read_trailer(blob: bytes) -> dict:
    pos = blob.rfind(TRAILER_SIG)
    if pos < 0:
        raise AddreError("trailer marker not found")
    rows = []
    off = pos + 4
    while off + 12 <= len(blob):
        start, length, value = struct.unpack_from(">3I", blob, off)
        if start == 0 and length == 0 and value == 0:
            break
        rows.append(
            {"pos": off, "start": start, "length": length, "value": value}
        )
        off += 12
    if not rows:
        raise AddreError("trailer marker has no rows")
    chain = sum(
        1
        for a, b in zip(rows, rows[1:])
        if a["start"] + a["length"] == b["start"]
    )
    total = rows[-1]["start"] + rows[-1]["length"]
    return {
        "pos": pos,
        "rows": rows,
        "chain": chain,
        "chain_ok": chain == len(rows) - 1,
        "total": total,
    }


# --------------------------------------------------------------------------
# Summary and verification
# --------------------------------------------------------------------------


def summary(blob: bytes) -> dict:
    sec = sections(blob)
    table = read_table(blob)
    trailer = read_trailer(blob)
    index_count = len(sec["index_bytes"]) // INDEX_REC
    return {
        "file_size": len(blob),
        "schema": sec["schema"],
        "index_blocks": len(sec["index"]),
        "index_bytes": len(sec["index_bytes"]),
        "index_records": index_count,
        "record_blocks": len(sec["records"]),
        "record_bytes": len(sec["record_bytes"]),
        "table_rows": len(table),
        "table_count": sum(r["count"] for r in table),
        "table_ids": "".join(r["initial"] or "?" for r in table),
        "trailer_rows": len(trailer["rows"]),
        "trailer_total": trailer["total"],
        "trailer_matches_blocks": len(trailer["rows"]) == len(sec["records"]),
        "trailer_chain": trailer["chain_ok"],
    }


def verify(blob: bytes, cell_base: int = CELL_OFF) -> list[tuple[str, bool, str]]:
    checks = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    sec = sections(blob)
    table = read_table(blob)
    trailer = read_trailer(blob)
    index_count = len(sec["index_bytes"]) // INDEX_REC
    recs = split_records(sec["record_bytes"])

    check("index length is 22-byte aligned", len(sec["index_bytes"]) % INDEX_REC == 0,
          f"{len(sec['index_bytes'])} bytes")
    check("record blocks decompress", len(sec["record_bytes"]) > 0,
          f"{len(sec['record_bytes'])} bytes")
    check("directory ids are printable", all(r["initial"] for r in table),
          "".join(r["initial"] or "?" for r in table))
    check("directory ends with a 0xffff length", table[-1]["last"])
    check("directory count <= index records", sum(r["count"] for r in table) <= index_count,
          f"{sum(r['count'] for r in table)} <= {index_count}")

    unknown = 0
    bad_cells = 0
    for row in table:
        if row["length"] == 0xFFFF or row["length"] == 0 or row["block"] != 0:
            continue
        if row["length"] % CELL_SIZE:
            bad_cells += 1
            continue
        for cell in read_cells(blob, row["offset"], row["length"], cell_base):
            if cell["kind"] == "unknown":
                bad_cells += 1
    check("6-byte cells match the two known shapes", bad_cells == 0,
          f"{bad_cells} unknown cells")

    names = 0
    bad_half = 0
    named_c8 = 0
    bad_range = 0
    for rec in recs:
        parsed = parse_record(rec)
        unknown += parsed["unknown"]
        for rng in parsed["ranges"]:
            if not all(byte in b"0123456789:;" for byte in rng["text"]):
                bad_range += 1
        if parsed["name"] is not None:
            names += 1
            if parsed["path"] == "c8":
                named_c8 += 1
            if parsed["name_half"] != (len(parsed["name"]) + 1) // 2:
                bad_half += 1
    check("name length prefix is ceil(name/2)", bad_half == 0,
          f"{bad_half}/{names} names")
    check("c8 records never carry a name", named_c8 == 0, f"{named_c8}")
    check("range strings only use digits, colon and semicolon", bad_range == 0,
          f"{bad_range} strings")
    check("records parse without unknown bytes", unknown == 0, f"{unknown} unknown bytes")
    check("trailer rows form a contiguous partition", trailer["chain_ok"],
          f"{len(trailer['rows'])} rows, total {trailer['total']}")
    check("trailer has one row per record block",
          len(trailer["rows"]) == len(sec["records"]),
          f"{len(trailer['rows'])} rows / {len(sec['records'])} blocks")
    exact = 0
    close = 0
    for k, ((start, end, data), row) in enumerate(zip(sec["records"], trailer["rows"])):
        if row["value"] * 2 == len(data):
            exact += 1
        nxt = sec["records"][k + 1][0] if k + 1 < len(sec["records"]) else end
        if abs(row["length"] * 2 - (nxt - start)) <= 4:
            close += 1
    check("trailer value is uncompressed size / 2", exact == len(trailer["rows"]),
          f"{exact}/{len(trailer['rows'])}")
    check("trailer length is compressed size / 2 (+-4 B padding)",
          close == len(trailer["rows"]), f"{close}/{len(trailer['rows'])}")

    return checks


# --------------------------------------------------------------------------
# Synthetic self-test
# --------------------------------------------------------------------------


def _synth_file() -> tuple[bytes, dict]:
    blob = bytearray(0x6000)

    # 12-byte directory: 'A' -> 2 index records, cells at 300/12; 'Z' sentinel.
    struct.pack_into(">BBHHHHH", blob, TABLE_OFF, ord("A"), 0, 2, 0, 300, 12, 0)
    struct.pack_into(">BBHHHHH", blob, TABLE_OFF + 12, ord("Z"), 0, 0, 0, 0, 0xFFFF, 0xFFFF)

    # 6-byte cells: one value cell and one pointer cell.
    struct.pack_into(">3H", blob, CELL_OFF + 300, 0, 0x0452, 3)
    struct.pack_into(">3H", blob, CELL_OFF + 306, 306, 0xFF00, 0)

    # Index chain: header + zlib with two 22-byte records.
    index = b"".join(struct.pack(">11H", 0, 2, 0, 0xFFFF, 0xFFFF, 0, 0x4000, 1, 5, 0, k)
                     for k in (0, 1))
    idx_stream = zlib.compress(index, 6)
    idx_pos = 0x3000
    blob[idx_pos:idx_pos + 8] = CHAIN_SIG + struct.pack(">I", 0)
    blob[idx_pos + 8:idx_pos + 8 + len(idx_stream)] = idx_stream

    # Schema block and record chain.
    schema = 0x4000
    blob[schema:schema + len(SCHEMA_SIG)] = SCHEMA_SIG

    def frame(tag: int, body: bytes) -> bytes:
        length = (len(body) + 3) // 2
        return bytes([tag, length]) + body.ljust(2 * length - 2, b"\x00")

    full = frame(
        0xC0,
        bytes([0x06, 0x0C]) + bytes.fromhex("9feccded")
        + bytes([0x02, 0x40, 0x14, 0x9B])
        + bytes([0x03, 0x40, 0x14, 0xA0])
        + bytes([0x06, 0x54, 0x00, 0x00]) + b":13:;:5:"
        + bytes([0x06, 0x58, 0x00, 0x00]) + b":10:;:2:"
        + bytes([0x03, 6, 0x00, 0xFF, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00])
        + b"TEST STREET"
    )
    partial = frame(
        0xC8,
        bytes([0x06, 0x0E]) + bytes.fromhex("9feccded")
        + bytes([0x02, 0x40, 0x14, 0x96])
        + bytes([0x03, 0x40, 0x14, 0x9B])
        + bytes([0x07, 0x54, 0x00, 0x00]) + b":19:;:15:" + b"\x00"
        + bytes([0x07, 0x58, 0x00, 0x00]) + b":16:;:12:" + b"\x00"
        + b"\x00\x00\x00\xff"
    )
    streams = [zlib.compress(full, 6), zlib.compress(partial, 6)]
    pos = schema + 0x100
    for stream in streams:
        blob[pos:pos + len(stream)] = stream
        pos += len(stream) + 2

    # Trailer: one row per record block, sizes in 16-bit words.
    tpos = 0x5000
    blob[tpos:tpos + 4] = TRAILER_SIG
    acc = 0
    for k, (stream, body) in enumerate(zip(streams, (full, partial))):
        length = (len(stream) + 1) // 2
        struct.pack_into(">3I", blob, tpos + 4 + 12 * k, acc, length, len(body) // 2)
        acc += length
    return bytes(blob), {"full": full, "partial": partial, "index": index}


def selftest() -> int:
    blob, fixture = _synth_file()
    failures = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        if not cond:
            failures.append(name + (f": {detail}" if detail else ""))
        print(f"{'PASS' if cond else 'FAIL'} {name}" + (f"  {detail}" if detail and not cond else ""))

    sec = sections(blob)
    check("index bytes", sec["index_bytes"] == fixture["index"], f"{len(sec['index_bytes'])}")
    check("record bytes", sec["record_bytes"] == fixture["full"] + fixture["partial"])

    table = read_table(blob)
    check("table rows", len(table) == 2, str(len(table)))
    check("table ids", "".join(r["initial"] or "?" for r in table) == "AZ")
    check("table count", sum(r["count"] for r in table) == 2)
    check("sentinel", table[-1]["last"])

    cells = read_cells(blob, 300, 12)
    check("cell count", len(cells) == 2)
    check("cell value", cells[0]["kind"] == "value" and cells[0]["b"] == 0x0452)
    check("cell pointer", cells[1]["kind"] == "pointer" and cells[1]["a"] == 306)

    recs = split_records(sec["record_bytes"])
    check("record count", len(recs) == 2, str(len(recs)))
    first = parse_record(recs[0])
    second = parse_record(recs[1])
    check("c0 path", first["path"] == "c0")
    check("c8 path", second["path"] == "c8")
    check("coord", first["coord"] == (0x9FEC, 0xCDED), str(first["coord"]))
    check("points", [(p["x"], p["y"]) for p in first["points"]] == [(0x14, 0x9B), (0x14, 0xA0)])
    check("ranges", [r["text"] for r in first["ranges"]] == [b":13:;:5:", b":10:;:2:"])
    check("name", first["name"] == b"TEST STREET", str(first["name"]))
    check("name half", first["name_half"] == 6, str(first["name_half"]))
    check("c8 has no name", second["name"] is None)
    check("no unknown tokens", first["unknown"] == 0 and second["unknown"] == 0)

    trailer = read_trailer(blob)
    check("trailer rows", len(trailer["rows"]) == 2, str(len(trailer["rows"])))
    check("trailer chain", trailer["chain_ok"] and trailer["total"] == sum((len(zlib.compress(x, 6)) + 1) // 2 for x in (fixture["full"], fixture["partial"])))

    checks = verify(blob)
    check("verify all PASS", all(ok for _, ok, _ in checks),
          "; ".join(name for name, ok, _ in checks if not ok))

    if failures:
        print(f"\nselftest FAILED ({len(failures)}): " + ", ".join(failures))
        return 1
    print("\nselftest OK")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_layout(args: argparse.Namespace) -> int:
    s = summary(load_blob(Path(args.file)))
    for key, value in s.items():
        print(f"{key:16s} {value}")
    return 0


def _cmd_table(args: argparse.Namespace) -> int:
    blob = load_blob(Path(args.file))
    for row in read_table(blob):
        length = "sentinel" if row["last"] else str(row["length"])
        print(f"0x{row['pos']:06x} {row['initial']!r:4s} n={row['count']:6d} "
              f"block={row['block']} off=0x{row['offset']:04x} len={length}")
    return 0


def _cmd_cells(args: argparse.Namespace) -> int:
    blob = load_blob(Path(args.file))
    for row in read_table(blob):
        if args.id and row["initial"] != args.id:
            continue
        if row["length"] in (0, 0xFFFF) or row["block"] != 0:
            continue
        for cell in read_cells(blob, row["offset"], row["length"], cell_base):
            print(f"{row['initial']} 0x{cell['pos']:06x} {cell['raw'].hex()} "
                  f"{cell['kind']:8s} a={cell['a']:5d} b=0x{cell['b']:04x} c={cell['c']}")
    return 0


def _cmd_records(args: argparse.Namespace) -> int:
    blob = load_blob(Path(args.file))
    recs = split_records(sections(blob)["record_bytes"])
    for k, rec in enumerate(recs):
        if args.limit and k >= args.limit:
            break
        p = parse_record(rec)
        coord = "-" if p["coord"] is None else f"{p['coord'][0]:04x}:{p['coord'][1]:04x}"
        pts = " ".join(f"{q['x']:02x}{q['y']:02x}" for q in p["points"])
        rng = " ".join(f"{r['prefix']:02x}{r['subtype']:02x}={r['text'].decode('latin-1')}"
                       for r in p["ranges"])
        name = p["name"].decode("latin-1") if p["name"] else ""
        print(f"#{k:5d} {p['path']} L={p['length']:3d} id={coord} pts={pts or '-'} "
              f"rng={rng or '-'} name={name}")
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    blob = load_blob(Path(args.file))
    recs = split_records(sections(blob)["record_bytes"])
    counts = {"c0": 0, "c8": 0, "c0_named": 0, "c8_named": 0, "unknown": 0}
    points = 0
    pairs = 0
    equal_x = 0
    tags = {}
    ranges = {}
    for rec in recs:
        p = parse_record(rec)
        counts[p["path"]] += 1
        if p["name"] is not None:
            counts[p["path"] + "_named"] += 1
        counts["unknown"] += p["unknown"]
        points += len(p["points"])
        for q in p["points"]:
            tags[q["tag"]] = tags.get(q["tag"], 0) + 1
        for r in p["ranges"]:
            key = (r["prefix"], r["subtype"])
            ranges[key] = ranges.get(key, 0) + 1
        primary = [q for q in p["points"] if q["tag"] in (0x02, 0x03, 0x04, 0x05)]
        if len(primary) == 2:
            pairs += 1
            if primary[0]["x"] == primary[1]["x"]:
                equal_x += 1
    print(f"records        {len(recs)}")
    for key in ("c0", "c8", "c0_named", "c8_named", "unknown"):
        print(f"{key:14s} {counts[key]}")
    print(f"points         {points}")
    print(f"primary pairs  {pairs}")
    print(f"equal-X pairs  {equal_x}" + (f" ({equal_x / pairs:.4f})" if pairs else ""))
    print("point tags     " + " ".join(f"{k:#04x}:{v}" for k, v in sorted(tags.items())))
    print("range tokens   " + " ".join(f"{p:#04x}/{s:#04x}:{n}" for (p, s), n in sorted(ranges.items())))
    return 0


def _cmd_trailer(args: argparse.Namespace) -> int:
    t = read_trailer(load_blob(Path(args.file)))
    print(f"marker 0x{t['pos']:06x} rows={len(t['rows'])} "
          f"total={t['total']} chain={'OK' if t['chain_ok'] else 'BROKEN'}")
    for r in t["rows"]:
        print(f"  start={r['start']:10d} length={r['length']:8d} value={r['value']}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    checks = verify(load_blob(Path(args.file)), args.cell_base)
    bad = 0
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name}" + (f"  [{detail}]" if detail and not ok else ""))
        bad += not ok
    return 1 if bad else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--selftest", action="store_true", help="run the synthetic self-test")
    sub = p.add_subparsers(dest="command")

    for name, func, help_text in (
        ("layout", _cmd_layout, "one-line container summary"),
        ("table", _cmd_table, "print the 12-byte directory"),
        ("records", _cmd_records, "print parsed address records"),
        ("stats", _cmd_stats, "record, range and point statistics"),
        ("trailer", _cmd_trailer, "print the trailer table"),
        ("verify", _cmd_verify, "run structural checks"),
    ):
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("file")
        if name == "records":
            sp.add_argument("--limit", type=int, default=0)
        if name == "verify":
            sp.add_argument("--cell-base", type=lambda v: int(v, 0), default=CELL_OFF)
        sp.set_defaults(func=func)

    sp = sub.add_parser("cells", help="print the 6-byte cells")
    sp.add_argument("file")
    sp.add_argument("--id", default=None)
    sp.add_argument("--cell-base", type=lambda v: int(v, 0), default=CELL_OFF)
    sp.set_defaults(func=_cmd_cells)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if not getattr(args, "func", None):
        build_parser().print_help()
        return 2
    try:
        return args.func(args)
    except (AddreError, OSError) as exc:
        print(f"addre: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
