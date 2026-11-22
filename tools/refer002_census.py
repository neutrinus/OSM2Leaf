#!/usr/bin/env python3
"""Census of a ``REFER002`` (EV / charging) tree and the station record schema (M4.85).

``REFER002`` is the Leaf-specific layer that carries charging stations (plug
type, parking capacity, point of arrival, tie-up parking) on top of the
ordinary POI schema.  The matrix (``docs/research/reader-coverage.md`` row 24)
calls its schema *undecoded*; the only prior note was that the family has 16
files and is a separate EV layer.  This tool documents the layer from the
files themselves -- it is a census and a schema reader, not a writer.

Containers.  Two forms occur in the trees this repo works with:

* **plain** ``.DAT`` -- what ``leafre-work`` factories and ``cmpind.py``
  produce: a 0x800-byte header, then a 299-cell directory at ``0x800``
  (``u32 block address, u16 blocks``, big-endian -- the same cell shape as a
  ``REFER001`` POINT ``.DAT``, ``tools/point_census.py``) pointing at three
  data descriptors.  Point files then hold zlib streams of ``0x60``/``0x68``
  length-prefixed records (``byte[1] = length/2``).
* **``.DAT.cmp/.ind`` pair** -- the on-card form; decode with
  ``tools/cmpind.py`` first, then point this tool at the plain directory.

The facility record.  Every POINT file carries a *field dictionary*: a C-block
(``ff ff`` + ``u16 word-offset`` to a header whose ``u16 @+24`` is the first
entry word and ``u16 @+26`` the field count) with one 16-byte-header entry per
field, chained by the ``u16`` at entry ``+0`` (next-entry word, ``0xffff`` =
last).  Each entry is
``u16 next, u16 flags, u16 length_words, u16 type, u16, u16, u16 id @+12,
u8 len @+14, name @+16`` -- ``type`` is ``0x8000`` coded, ``0x6000`` text in
the record tail, ``0x2000`` the trailing rest.  This is the accessor's own
chain (``find_dictionary`` of ``tools/point_name_accessor.py``).

The EV additions.  Compared with a ``REFER001`` POINT dictionary, the
facility dictionary swaps ``icon code`` for ``xy-coordinates``, ``point of
arrival`` and ``tie-up parking``; ``plug info`` and ``parking capacity`` live
in the ``INFORMATION`` sub-schema (the 400-record chain) instead.  The tool
reports both: the strict facility dictionary per file and which EV field names
the file declares at all.

Usage::

  python3 tools/refer002_census.py census ROOT
  python3 tools/refer002_census.py census ROOT --json OUT
  python3 tools/refer002_census.py schema ROOT/POINT002.DAT
  python3 tools/refer002_census.py table ROOT
  python3 tools/refer002_census.py --selftest

``ROOT`` is a ``REFER002`` directory of plain ``.DAT`` files.  Read-only; no
vendor bytes are written.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import struct
import sys
import zlib

# Field names this task cares about (the EV vocabulary).  Presence is checked
# as an ASCII substring of the file, which covers both the facility dictionary
# and the INFORMATION sub-schema without parsing the latter's chain.
EV_FIELDS = ("xy-coordinates", "point of arrival", "tie-up parking",
             "plug info", "parking capacity", "installed facility",
             "user limitation id")
BASE_POI_FIELDS = (
    "area code", "category", "sub-category", "detailed code", "index",
    "facility name", "address", "dndc-id",
)
TYPE_CODED = 0x8000
TYPE_TEXT = 0x6000
TYPE_REST = 0x2000


class CensusError(Exception):
    pass


# ---------------------------------------------------------------------------
# zlib pages and the 0x60/0x68 record walk


def zlib_streams(blob: bytes) -> list[tuple[int, int, bytes]]:
    """``(file_offset, compressed_len, decompressed)`` for every zlib stream.

    Scans for the common ``78 9c`` header, decompresses and skips bytes that
    are not a valid stream.  A stream ending at the blob (``unused_data``
    empty) stops the scan.
    """
    out = []
    i = 0
    while True:
        j = blob.find(b"\x78\x9c", i)
        if j < 0:
            break
        try:
            obj = zlib.decompressobj()
            data = obj.decompress(blob[j:]) + obj.flush()
        except zlib.error:
            i = j + 2
            continue
        used = len(blob) - j - len(obj.unused_data)
        if not data or used <= 0:
            i = j + 2
            continue
        out.append((j, used, data))
        i = j + used
    return out


def walk_records(inner: bytes) -> list[bytes]:
    """Split a page into ``0x60``/``0x68`` records (``byte[1] = length/2``)."""
    recs = []
    o = 0
    while o + 2 <= len(inner):
        tag = inner[o]
        if tag not in (0x60, 0x68):
            break
        ln = inner[o + 1] * 2
        if ln < 2 or o + ln > len(inner):
            break
        recs.append(bytes(inner[o:o + ln]))
        o += ln
    return recs


def is_record_page(inner: bytes) -> bool:
    return bool(inner) and inner[0] in (0x60, 0x68) and bool(walk_records(inner))


# ---------------------------------------------------------------------------
# the field dictionary


def be16(blob: bytes, off: int) -> int | None:
    if off < 0 or off + 2 > len(blob):
        return None
    return (blob[off] << 8) | blob[off + 1]


def find_dictionary(blob: bytes) -> tuple[int, int, int] | None:
    """First strict field dictionary ``(C, D, nfields)`` or ``None``.

    The checks are the accessor's (``tools/point_name_accessor.find_dictionary``):
    a ``ff ff`` marker at C, a word offset to D, ``0 < n <= 64``, and every one
    of the ``n`` entries chained by ``+0`` with ids ``0..n-1`` and a printable
    ASCII name.
    """
    for c in range(0, len(blob) - 4, 2):
        if blob[c] != 0xFF or blob[c + 1] != 0xFF:
            continue
        off = be16(blob, c + 2)
        if not off:
            continue
        d = c + 2 * off
        n = be16(blob, d + 26)
        first = be16(blob, d + 24)
        if not n or not first or n > 64:
            continue
        e = d + 2 * first
        ok = True
        names = []
        try:
            for i in range(n):
                if be16(blob, e + 12) != i:
                    ok = False
                    break
                ln = blob[e + 14]
                name = bytes(blob[e + 16:e + 16 + ln])
                if not name or not all(0x20 <= ch < 0x7F for ch in name):
                    ok = False
                    break
                names.append(name.decode("ascii"))
                if i + 1 < n:
                    nxt = be16(blob, e)
                    if not nxt:
                        ok = False
                        break
                    e = d + 2 * nxt
        except (IndexError, TypeError):
            ok = False
        if ok and len(names) == n:
            return c, d, n
    return None


def read_fields(blob: bytes, c: int, d: int, n: int) -> list[dict]:
    """Fields in dictionary order: ``id, name, type, length_words, next_word``."""
    e = d + 2 * be16(blob, d + 24)
    fields = []
    for _ in range(n):
        nxt = be16(blob, e)
        ln = blob[e + 14]
        name = bytes(blob[e + 16:e + 16 + ln]).decode("ascii")
        fields.append({"id": be16(blob, e + 12), "name": name,
                       "type": be16(blob, e + 6),
                       "length_words": be16(blob, e + 4),
                       "next_word": nxt})
        if nxt == 0xFFFF:
            break
        e = d + 2 * nxt
    return fields


def classify(fields: list[dict]) -> dict:
    out = {"coded": [], "text": [], "rest": []}
    for f in fields:
        typ = f["type"] or 0
        if typ & TYPE_TEXT == TYPE_TEXT:
            out["text"].append(f["name"])
        elif typ & TYPE_REST == TYPE_REST:
            out["rest"].append(f["name"])
        else:
            out["coded"].append(f["name"])
    return out


def ev_present(blob: bytes) -> list[str]:
    """EV field names declared anywhere in the file (facility dict or INFORMATION)."""
    return [name for name in EV_FIELDS if blob.find(name.encode("ascii")) >= 0]


# ---------------------------------------------------------------------------
# census


def file_census(path: str) -> dict:
    with open(path, "rb") as fh:
        blob = fh.read()
    name = os.path.basename(path)
    row = {"file": name, "size": len(blob), "kind": "point",
           "streams": 0, "record_pages": 0, "records": 0,
           "fields": 0, "dict_offset": None,
           "coded": [], "text": [], "rest": [], "ev": ev_present(blob)}
    if name.upper().startswith("COORD"):
        row["kind"] = "coord"
        return row
    streams = zlib_streams(blob)
    row["streams"] = len(streams)
    for _off, _used, inner in streams:
        if is_record_page(inner):
            row["record_pages"] += 1
            row["records"] += len(walk_records(inner))
    hit = find_dictionary(blob)
    if hit:
        c, d, n = hit
        cls = classify(read_fields(blob, c, d, n))
        row.update({"fields": n, "dict_offset": c,
                    "coded": cls["coded"], "text": cls["text"],
                    "rest": cls["rest"]})
    return row


def dir_census(root: str) -> dict:
    paths = sorted(glob.glob(os.path.join(root, "*.DAT")),
                   key=lambda p: os.path.basename(p).upper())
    if not paths:
        raise CensusError("no .DAT files in %s" % root)
    rows = [file_census(p) for p in paths]
    return {"root": root, "files": rows,
            "totals": {"files": len(rows),
                       "records": sum(r["records"] for r in rows),
                       "size": sum(r["size"] for r in rows)}}


def schema_of(path: str) -> dict:
    with open(path, "rb") as fh:
        blob = fh.read()
    hit = find_dictionary(blob)
    if not hit:
        raise CensusError("no field dictionary in %s" % path)
    c, d, n = hit
    fields = read_fields(blob, c, d, n)
    return {"file": os.path.basename(path), "dict_offset": c,
            "fields": fields, "classified": classify(fields),
            "ev": ev_present(blob)}


# ---------------------------------------------------------------------------
# output


def cmd_census(args) -> int:
    rep = dir_census(args.root)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, indent=2)
    print("%-16s %8s %5s %6s %7s %4s  %s" %
          ("file", "size", "strm", "pages", "records", "fd", "EV field names"))
    for r in rep["files"]:
        print("%-16s %8d %5d %6d %7d %4s  %s" %
              (r["file"], r["size"], r["streams"], r["record_pages"],
               r["records"], r["fields"] or "-", ", ".join(r["ev"]) or "-"))
    t = rep["totals"]
    print("\nfiles %d  records %d  bytes %d" %
          (t["files"], t["records"], t["size"]))
    return 0


def cmd_schema(args) -> int:
    s = schema_of(args.path)
    print("# %s  facility dictionary @0x%x" % (s["file"], s["dict_offset"]))
    print("%3s %-16s %6s %9s" % ("id", "field", "type", "length_w"))
    for f in s["fields"]:
        print("%3d %-16s 0x%04x %9d" %
              (f["id"], f["name"], f["type"] or 0, f["length_words"] or 0))
    cls = s["classified"]
    print("\ncoded: %s" % ", ".join(cls["coded"]))
    print("text : %s" % ", ".join(cls["text"]))
    print("rest : %s" % ", ".join(cls["rest"]))
    print("EV declared in file: %s" % (", ".join(s["ev"]) or "-"))
    return 0


def cmd_table(args) -> int:
    """Markdown tables for ``docs/format/refer.md`` and the EXP record."""
    rep = dir_census(args.root)
    print("### REFER002 files\n")
    print("| file | bytes | zlib streams | record pages | records | EV fields |")
    print("| --- | ---: | ---: | ---: | ---: | --- |")
    for r in rep["files"]:
        if r["kind"] == "coord":
            print("| `%s` | %d | - | - | - | (projection companion) |" %
                  (r["file"], r["size"]))
        else:
            print("| `%s` | %d | %d | %d | %d | %s |" %
                  (r["file"], r["size"], r["streams"], r["record_pages"],
                   r["records"], ", ".join(r["ev"]) or "-"))
    for r in rep["files"]:
        if r["kind"] == "point" and r["fields"]:
            s = schema_of(os.path.join(args.root, r["file"]))
            print("\n### %s facility dictionary\n" % r["file"])
            print("| id | field | type | length (words) |")
            print("| ---: | --- | --- | ---: |")
            for f in s["fields"]:
                print("| %d | %s | 0x%04x | %d |" %
                      (f["id"], f["name"], f["type"] or 0, f["length_words"] or 0))
            break
    return 0


def display_text(rec: bytes) -> bytes:
    """The text after the record's last inner ``ff ff`` marker (M3.11c rule)."""
    body = rec[:-2]
    i = body.rfind(b"\xff\xff")
    return body[i + 2:] if i >= 0 else b""


def cmd_record(args) -> int:
    """Dump the first ``--n`` facility records: tag, length, name@address text.

    The record *body* field positions are not decoded here (the POINT name
    record has the same 48/88-byte grammar that is still open for REFER001,
    see ``docs/format/refer.md``); the dictionary above names the fields, and
    this command reports only what the walker verifies per record.
    """
    with open(args.path, "rb") as fh:
        blob = fh.read()
    shown = 0
    for off, _used, inner in zlib_streams(blob):
        if not is_record_page(inner):
            continue
        for rec in walk_records(inner):
            text = display_text(rec).rstrip(b"\x00")
            print("@0x%x tag=0x%02x bytes=%d text=%r" %
                  (off, rec[0], len(rec), text))
            shown += 1
            if shown >= args.n:
                return 0
    return 0


# ---------------------------------------------------------------------------
# self-test (synthetic; no vendor bytes)


def _build_dictionary(names: list[str], types: list[int],
                      lengths: list[int]) -> bytes:
    """Pack a strict field dictionary the accessor accepts (C at offset 0)."""
    head = bytearray(32)
    struct.pack_into(">H", head, 24, 16)      # first entry at D + 32 bytes
    struct.pack_into(">H", head, 26, len(names))
    blocks = []
    for nm in names:
        nb = nm.encode("ascii")
        e = bytearray(16)
        e[14] = len(nb)
        blocks.append((e + nb) if (len(nb) % 2 == 0) else (e + nb + b"\x00"))
    offs = []
    o = 32
    for b in blocks:
        offs.append(o // 2)
        o += len(b)
    for i, b in enumerate(blocks):
        struct.pack_into(">H", b, 0, offs[i + 1] if i + 1 < len(blocks) else 0xFFFF)
        struct.pack_into(">H", b, 4, lengths[i])
        struct.pack_into(">H", b, 6, types[i])
        struct.pack_into(">H", b, 12, i)
    buf = bytearray(4)
    buf[0:2] = b"\xff\xff"
    struct.pack_into(">H", buf, 2, 2)          # D at byte 4
    return bytes(buf + head + b"".join(blocks))


def _synthetic_root(tmp: str) -> None:
    names = list(BASE_POI_FIELDS) + ["xy-coordinates", "point of arrival", "tie-up parking"]
    types = [TYPE_CODED, TYPE_CODED, TYPE_CODED, TYPE_CODED, TYPE_CODED,
             TYPE_TEXT, TYPE_TEXT, TYPE_REST, TYPE_CODED, TYPE_CODED, TYPE_CODED]
    lengths = [5, 1, 1, 1, 0, 19, 14, 0, 0, 1, 1]
    d = _build_dictionary(names, types, lengths)
    os.makedirs(tmp, exist_ok=True)

    def recs(n: int) -> bytes:
        out = bytearray()
        for k in range(n):
            body = b"STATION%03d" % k          # 10 bytes, even so the record walks
            out += struct.pack(">H", 0x6000 | ((2 + len(body)) // 2)) + body
        return bytes(out)

    blob = bytearray(b"\xff" * 0x800)
    blob += d.ljust(0x400, b"\x00")
    blob += zlib.compress(recs(6)) + zlib.compress(recs(1))
    # the INFORMATION vocabulary lives elsewhere in the file
    blob += b"\x00plug info\x00parking capacity\x00"
    with open(os.path.join(tmp, "POINT002.DAT"), "wb") as fh:
        fh.write(blob)
    with open(os.path.join(tmp, "COORD001.DAT"), "wb") as fh:
        fh.write(b"\xff" * 0x1000)


def selftest() -> int:
    import tempfile
    fails = 0

    def check(name, cond):
        nonlocal fails
        print("%-64s %s" % (name, "ok" if cond else "FAIL"))
        fails += not cond

    with tempfile.TemporaryDirectory(prefix="m4.85-") as tmp:
        _synthetic_root(tmp)
        rep = dir_census(tmp)
        by = {r["file"]: r for r in rep["files"]}
        p2 = by["POINT002.DAT"]
        check("census: POINT002 has two record pages", p2["record_pages"] == 2)
        check("census: POINT002 records count", p2["records"] == 7)
        check("census: POINT002 dictionary has 11 fields", p2["fields"] == 11)
        check("census: text fields are facility name + address",
              p2["text"] == ["facility name", "address"])
        check("census: rest field is dndc-id", p2["rest"] == ["dndc-id"])
        check("census: EV vocabulary found (facility + INFORMATION)",
              p2["ev"] == ["xy-coordinates", "point of arrival", "tie-up parking",
                           "plug info", "parking capacity"])
        check("census: COORD001 classified as coordinate companion",
              by["COORD001.DAT"]["kind"] == "coord")
        s = schema_of(os.path.join(tmp, "POINT002.DAT"))
        check("schema: ids are dense 0..n-1",
              [f["id"] for f in s["fields"]] == list(range(11)))
        check("schema: base POI fields keep their order",
              [f["name"] for f in s["fields"]][:8] == list(BASE_POI_FIELDS))
        check("schema: last field chains out (0xffff)",
              s["fields"][-1]["next_word"] == 0xFFFF)
    check("find_dictionary: all-ff blob has none", find_dictionary(b"\xff" * 64) is None)
    check("walk_records: a non-record page walks empty", walk_records(b"\x00\x01") == [])
    print("selftest:", "PASS" if not fails else "FAIL (%d)" % fails)
    return 0 if not fails else 1


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    c = sub.add_parser("census")
    c.add_argument("root")
    c.add_argument("--json")
    s = sub.add_parser("schema")
    s.add_argument("path")
    t = sub.add_parser("table")
    t.add_argument("root")
    r = sub.add_parser("record")
    r.add_argument("path")
    r.add_argument("--n", type=int, default=3)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "census":
        return cmd_census(args)
    if args.cmd == "schema":
        return cmd_schema(args)
    if args.cmd == "table":
        return cmd_table(args)
    if args.cmd == "record":
        return cmd_record(args)
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
