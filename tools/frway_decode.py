#!/usr/bin/env python3
"""Reproducible census of a REFER001 ``FRWAY0nn.DAT`` (M4.82).

The M3.16 prose described the FRWAY body ("12-byte table, then blob 1 = route
refs, blob 2 = main table") but no committed tool reproduced it.  This tool
walks every structure of a shard and counts the bytes each one explains:

  class            offset / reached from        grammar
  ---------------  ---------------------------  ----------------------------
  header           0x000..0x1ff                 512-byte common CLAR header
  template         0x200..0xfff                 shared ``ff`` fill (3584 B)
  type block       0x1000..0x1107               0x108-byte volume block with four
                                                fixed marker words: u16@+0=ffff,
                                                +4=0201, +0x10=4d40, +0x32=0601
                                                (all 37 shards); other words are
                                                counted, meaning UNKNOWN (C-7830)
  record table     0x1108                       8-byte block header, then 12-byte
                                                big-endian records at 0x1110:
                                                u16 key, u16 0, u8 id, u8 0,
                                                u16 length, u16 0, u16 offset
                                                (C-2215); u16 ffff key terminates
  directory        table end + 16               ``u8 code``, ``u8 0``, ``u16 count``,
                                                ``u16 block``, ``u16 offset``, ``u16 len``,
                                                ``u16 tail``; ended by an all-zero row
  index / route /  zlib streams, file order      ``4e 20 00 00`` + ``u32`` before the
    main blobs                                  first stream; the streams are framed by
                                                ``2 * (u16 & 0x3ff)`` as in POINT
  schema           0x100-aligned signature      ``ff ff 00 10 ff ff ff ff ...``; the
                                                field dictionary, described below
  padding          between structures           zero or ``ff`` fill

The value ranges are computed for the record table, the directory and the
main-blob records.  The
schema block is decoded with the writer model already used for ``ADDRE`` and
``POINT`` (``tools/addre_field_reader.py``, ``tools/point_name_accessor.py``):
each entry is ``(u16 next, u16 class, u16 max_words, u8 id, u8 len, name)``.
The **table** and the **location** are built from the factory bytes; the
**meaning** of a field (its offset in a main-blob record) is not decoded by
this tool and is printed as UNKNOWN.

Exactly one byte per shard is not covered by any grammar: the byte at
``table-terminator + 0x0d`` (the 4-byte gap between the terminator row and the
directory).  It is reported with its value histogram, never guessed (C-7836).

``census ROOT`` accepts a card root (``ROOT/REFER001/FRWAY0nn.DAT`` decoded
files, taken from ``tools/cmpind.py extract``), a directory of decoded
``FRWAY0nn.DAT`` files, or a directory of ``.DAT.cmp``/``.DAT.ind`` pairs.
It prints one row per shard and a family summary with the missing numbers of
the 1..33 split.

``--selftest`` builds a synthetic shard (no vendor bytes) and checks that the
grammar frames it, and that a single mutated byte is reported as unexplained
(the negative control).

Usage::

  python3 tools/frway_decode.py census ROOT [--json OUT]
  python3 tools/frway_decode.py census ROOT --files FRWAY002 FRWAY030
  python3 tools/frway_decode.py --selftest

Method and results: docs/experiments/EXP-2026-11-22-M4.82-frway-decode.md
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import struct
import sys
import tempfile
import zlib
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import addre  # noqa: E402
import addre_field_reader as afr  # noqa: E402
import inter_table  # noqa: E402
import point_name_accessor as pna  # noqa: E402

TYPE_BLOCK = 0x1000
TABLE_BLOCK = 0x1108
RESERVED = 0x1000
SCHEMA_SIG = addre.SCHEMA_SIG
CHAIN_SIG = addre.CHAIN_SIG
SHARD_TOTAL = 33
REC_WORDS_ESCAPE = 0x4E8


# ---------------------------------------------------------------------------
# framing (the POINT walkers reused; the main-blob records are 0x60/0x68)


def rec_words(w: int) -> int:
    return REC_WORDS_ESCAPE if (w & 0xFC00) == 0xFC00 else (w & 0x3FF)


def frame(buf: bytes, limit: int = 1 << 22) -> list[int]:
    """Record starts for the shared ``2*(w & 0x3ff)`` walk; stops at a 0 word."""
    out: list[int] = []
    p = 0
    while p + 1 < len(buf) and len(out) < limit:
        n = rec_words((buf[p] << 8) | buf[p + 1])
        if n == 0:
            break
        out.append(p)
        p += 2 * n
    return out


def framed_to_end(buf: bytes, offs: list[int]) -> bool:
    if not offs:
        return False
    last = offs[-1]
    n = rec_words((buf[last] << 8) | buf[last + 1])
    return last + 2 * n == len(buf)


# ---------------------------------------------------------------------------
# structural walks (pure; no I/O)


class FrwayError(Exception):
    pass


def type_block(blob: bytes) -> dict:
    """Validate the four fixed words of the 0x108-byte volume block at 0x1000.

    All 37 factory shards (26 EU, 11 US) carry the same four big-endian marker
    words.  The other words vary; their meaning is UNKNOWN and only their
    distribution is reported.  A wrong marker is a loud failure, so the
    header/table split can fail instead of silently skipping the region.
    """
    if len(blob) < TYPE_BLOCK + 0x108:
        raise FrwayError("type block truncated")
    want = {0x00: 0xFFFF, 0x04: 0x0201, 0x10: 0x4D40, 0x32: 0x0601}
    marks = {off: struct.unpack_from(">H", blob, TYPE_BLOCK + off)[0]
             for off in want}
    if marks != want:
        raise FrwayError(f"type-block markers {marks!r} != {want!r}")
    words = [struct.unpack_from(">H", blob, TYPE_BLOCK + 2 * i)[0]
             for i in range(0x84)]
    active = [w for w in words
              if w not in (0, 0xFFFF, 0x0201, 0x4D40, 0x0601)]
    return {"markers": {f"+0x{o:02x}": f"0x{v:04x}" for o, v in marks.items()},
            "nonzero_words": len(active),
            "word_ranges": [min(active), max(active)] if active else [0, 0]}


def table(blob: bytes) -> dict:
    """Records of the 0x1108 table (inter_table's 12-byte layout) and ranges.

    The 8-byte block header (``00 00 00 24 00 36 00 00``) is not a record; the
    records are ``u16 key, u16 0, u8 id, u8 0, u16 length, u16 0, u16 offset``
    (``tools/inter_table.py``, C-2215/C-2216).  A ``0xffff`` key at +0 is the
    terminator row.
    """
    start = TABLE_BLOCK + 8
    rows = []
    pos = start
    while pos + 12 <= len(blob):
        key, zero2, ident, zero5, length, zero8, offset = struct.unpack(
            ">HHBBHHH", blob[pos:pos + 12])
        if key == inter_table.TERMINATOR:
            break
        if zero2 != 0 or zero5 != 0:
            raise FrwayError(f"record at {pos:#x} violates the layout "
                             f"(u16@+2={zero2:#x}, u8@+5={zero5:#x})")
        rows.append({"offset": pos, "key": key, "id": ident,
                     "length": length, "index": offset, "u16_at_8": zero8})
        pos += 12
    terminator = pos
    if pos + 12 > len(blob):
        raise FrwayError("no 0xffff terminator")
    # Directory starts exactly 0x10 past the terminator record (the 12-byte
    # terminator row, four zero bytes, then the first directory row).
    rng = {}
    if rows:
        rng = {
            "key": (min(r["key"] for r in rows), max(r["key"] for r in rows)),
            "length": (min(r["length"] for r in rows), max(r["length"] for r in rows)),
            "index": (min(r["index"] for r in rows), max(r["index"] for r in rows)),
            "distinct_ids": len({r["id"] for r in rows}),
            "zero_length": sum(r["length"] == 0 for r in rows),
            "nonzero_u16_at_8": sum(r["u16_at_8"] != 0 for r in rows),
        }
    return {"start": start, "rows": rows, "terminator": terminator,
            "end": terminator + 12, "ranges": rng}


def directory(blob: bytes, terminator: int) -> dict:
    """Rows of the name-initial directory that follows the record table.

    The directory starts exactly 0x10 past the record-table terminator and runs
    up to the index-chain header (``4e 20 00 00``).  Rows are ``u8 code``,
    ``u8 0``, ``u16 count``, ``u16 block``, ``u16 offset``, ``u16 length``,
    ``u16 tail``.  ``code`` is the name initial: ``0x30``–``0x39``,
    ``0x41``–``0x5a``, a space ``0x20`` or ``0xff``.
    """
    start = terminator + 0x10
    chain = blob.find(CHAIN_SIG, start)
    stop = chain if chain >= 0 else len(blob)
    pos = start
    rows = []
    while pos + 12 <= stop:
        code, zero, count, block, offset, length, tail = struct.unpack(
            ">BBHHHHH", blob[pos:pos + 12])
        if code == 0 and zero == 0 and count == 0 and block == 0 \
                and offset == 0 and length == 0 and tail == 0:
            break
        if zero != 0 or not (code == 0xFF or code == 0x20 or 0x30 <= code <= 0x5A):
            break
        rows.append({"offset": pos, "code": code, "count": count,
                     "block": block, "offset": offset, "length": length,
                     "tail": tail})
        pos += 12
    rng = {}
    if rows:
        rng = {
            "count": (min(r["count"] for r in rows), max(r["count"] for r in rows)),
            "offset": (min(r["offset"] for r in rows), max(r["offset"] for r in rows)),
            "length": (min(r["length"] for r in rows), max(r["length"] for r in rows)),
            "nonzero_block": sum(r["block"] != 0 for r in rows),
            "distinct_codes": len({r["code"] for r in rows}),
        }
    return {"start": start, "rows": rows, "end": pos, "ranges": rng}


def streams(blob: bytes, start: int = RESERVED) -> list[dict]:
    """Every zlib stream in file order from *start*, with its consumed span."""
    out: list[dict] = []
    i = start
    n = len(blob)
    while i < n - 2:
        if blob[i] == 0x78 and blob[i + 1] in (0x01, 0x5E, 0x9C, 0xDA):
            try:
                dec = zlib.decompressobj()
                data = dec.decompress(blob[i:])
            except zlib.error:
                data = b""
                dec = None
            if dec is not None and dec.eof and len(data) >= 16:
                consumed = n - i - len(dec.unused_data)
                out.append({"start": i, "end": i + consumed, "data": data})
                i += consumed
                continue
        i += 1
    return out


def schema(blob: bytes) -> dict | None:
    """Field dictionary: names and the writer-model entries, if present."""
    c = blob.find(SCHEMA_SIG)
    if c < 0:
        return None
    nraw, strict = afr.strict_dictionaries(blob)
    names: list[bytes] = []
    words: list[tuple[int, int]] = []
    if strict:
        try:
            names = afr.dictionary_names(blob, c)
            words = afr.dictionary_words(blob, c)
        except (IndexError, TypeError):
            names, words = [], []
    return {"offset": c, "raw": nraw, "strict": len(strict),
            "names": [nm.decode("latin-1") for nm in names],
            "entries": [{"max_words": w[0], "class": w[1]} for w in words]}


def classify_streams(blob: bytes, st: list[dict], dir_end: int) -> dict:
    """Label each stream: index (before the schema), route, or main.

    * index — a stream before the schema block that does **not** frame with
      the shared walker (the tables' offset directory);
    * route — a stream at/after the schema that frames to its exact end with
      every record tagged ``0xa0``;
    * main — a stream that frames with the ``0x60``/``0x68`` record class.
    """
    sch = None
    hit = blob.find(SCHEMA_SIG)
    if hit >= 0:
        sch = hit
    for s in st:
        offs = frame(s["data"])
        s["records"] = len(offs)
        s["exact_end"] = framed_to_end(s["data"], offs)
        tags: Counter = Counter()
        for o in offs:
            if o + 1 < len(s["data"]):
                tags[s["data"][o]] += 1
        s["tags"] = dict(sorted(tags.items()))
        if sch is not None and s["start"] < sch and not s["exact_end"]:
            s["class"] = "index"
        elif s["exact_end"] and tags and all(t == 0xA0 for t in tags):
            s["class"] = "route"
        elif s["exact_end"] and tags and all(t in (0x60, 0x68) for t in tags):
            s["class"] = "main"
        elif s["exact_end"]:
            s["class"] = "records"
        else:
            s["class"] = "other"
    return {
        "index": sum(1 for s in st if s["class"] == "index"),
        "route": sum(1 for s in st if s["class"] == "route"),
        "main": sum(1 for s in st if s["class"] == "main"),
        "other": sum(1 for s in st if s["class"] == "other"),
        "main_records": sum(s["records"] for s in st if s["class"] == "main"),
        "route_records": sum(s["records"] for s in st if s["class"] == "route"),
    }


# ---------------------------------------------------------------------------
# byte accounting


def census(blob: bytes) -> dict:
    """Walk every structure and return counts + a byte-class breakdown."""
    n = len(blob)
    cover = bytearray(n)

    def mark(a: int, z: int) -> None:
        for k in range(max(0, a), min(n, z)):
            cover[k] = 1

    info: dict = {"size": n}
    mark(0, min(n, RESERVED))
    info["header"] = 0x200
    info["template"] = RESERVED - 0x200
    info["type_block"] = type_block(blob)

    tab = table(blob)
    mark(TYPE_BLOCK, TYPE_BLOCK + 0x108)
    mark(tab["start"] - 8, tab["end"])
    info["table"] = {"records": len(tab["rows"]), "ranges": tab["ranges"],
                     "terminator": tab["terminator"]}

    dirn = directory(blob, tab["terminator"])
    mark(dirn["start"], dirn["end"])
    info["directory"] = {"rows": len(dirn["rows"]), "ranges": dirn["ranges"]}

    sch = schema(blob)
    st = streams(blob, TYPE_BLOCK)
    for s in st:
        mark(s["start"], s["end"])
        # An index chain is preceded by its ``4e 20 00 00`` + u32 header.
        if s["start"] >= 8 and blob[s["start"] - 8:s["start"] - 4] == CHAIN_SIG:
            mark(s["start"] - 8, s["start"])
    if sch is not None:
        # The dictionary body up to the first stream after it, or 0x400.
        after = [s["start"] for s in st if s["start"] > sch["offset"]]
        stop = min(after) if after else min(sch["offset"] + 0x400, n)
        mark(sch["offset"], stop)
        info["schema"] = sch

    # Tail table: two 0x100-byte blocks at EOF (after the last stream), each
    # starting with a ``u16 1200``/``u16 0x04b0`` block word; the file is
    # padded to whole blocks.  The block's field meanings are UNKNOWN.
    tail = tail_block(blob, max((s["end"] for s in st), default=0))
    if tail is not None:
        mark(tail["start"], n)
        info["tail"] = tail

    cls = classify_streams(blob, st, dirn["end"])
    info["streams"] = {
        "count": len(st),
        "bytes": sum(s["end"] - s["start"] for s in st),
        "index": cls["index"], "route": cls["route"], "main": cls["main"],
        "other": cls["other"],
        "main_records": cls["main_records"],
        "route_records": cls["route_records"],
    }
    # Per field ranges over the main-blob records.
    info["main_fields"] = main_field_ranges(st)

    unexplained = [k for k in range(n) if not cover[k]]
    pad = sum(1 for k in unexplained if blob[k] in (0x00, 0xFF))
    real = [k for k in unexplained if blob[k] not in (0x00, 0xFF)]
    info["explained"] = n - len(unexplained)
    info["padding"] = pad
    info["unexplained"] = len(real)
    info["unexplained_runs"] = runs(real)
    # Name the unexplained bytes by their position relative to the table
    # terminator and report the value histogram; never assign a meaning.
    info["unexplained_detail"] = [
        {"offset": k, "rel_to_terminator": k - tab["terminator"],
         "value": blob[k]} for k in real
    ]
    # Padding is an accounted-for class, so it counts as explained.
    info["fraction_explained"] = (n - len(real)) / n if n else 0.0
    return info


def tail_block(blob: bytes, last_stream_end: int):
    """The trailing 0x100-block table at EOF, if one is present.

    Every shard ends with two 0x100-byte blocks after its last zlib stream;
    the first block starts with ``u16 1200`` (0x04b0, the main page size) and
    a second u16 that varies (tab counts).  We only check the block-aligned
    start and the 0x04b0 marker; the table's fields are not decoded.
    """
    n = len(blob)
    if last_stream_end <= 0:
        return None
    start = (last_stream_end + 0xFF) & ~0xFF
    if start + 4 > n:
        return None
    word0 = struct.unpack_from(">H", blob, start)[0]
    if word0 not in (0x09C4, 0x04B0):
        return None
    return {"start": start, "bytes": n - start,
            "size_words": struct.unpack_from(">H", blob, start + 2)[0]}


def main_field_ranges(st: list[dict]) -> dict:
    """Per-word counters over the 0x60/0x68 main-blob records.

    The first 24 bytes hold the two 4-byte ids, the two 11-bit fine fields and
    the coordinate words; later words are followed by variable-length field
    blocks.  We report per-*word* value ranges up to word 12 and the record
    length / tag distribution.  Field **semantics** are UNKNOWN (the names in
    the schema block name them, the offsets do not).
    """
    cols: dict[int, list[int]] = {}
    lengths: Counter = Counter()
    for s in st:
        if s["class"] != "main":
            continue
        data = s["data"]
        for o in frame(data):
            nw = rec_words((data[o] << 8) | data[o + 1])
            rec = data[o:o + 2 * nw]
            lengths[nw] += 1
            for w in range(min(12, len(rec) // 2)):
                val = (rec[2 * w] << 8) | rec[2 * w + 1]
                cols.setdefault(w, []).append(val)
    out = {}
    for w, vals in cols.items():
        out[f"+{2 * w:#04x}"] = [min(vals), max(vals)]
    return {"words": out,
            "length": [min(lengths), max(lengths)] if lengths else [0, 0],
            "records": sum(lengths.values())}


def runs(offsets: list[int]) -> list[list[int]]:
    """Group sorted offsets into ``[start, length]`` runs."""
    out: list[list[int]] = []
    for k in offsets:
        if out and k == out[-1][0] + out[-1][1]:
            out[-1][1] += 1
        else:
            out.append([k, 1])
    return sorted(out, key=lambda r: -r[1])[:8]


# ---------------------------------------------------------------------------
# shard discovery and reporting


def find_shards(root: Path) -> dict[str, Path]:
    """Map ``FRWAYnnn`` -> path for decoded ``.DAT`` or a ``.cmp``/``.ind`` pair."""
    root = Path(root)
    found: dict[str, Path] = {}
    if root.is_file():
        cand = [root]
    else:
        cand = sorted(root.glob("**/FRWAY*.DAT")) + sorted(root.glob("**/FRWAY*.DAT.cmp"))
    pat = re.compile(r"FRWAY0*(\d+)\.DAT(\.cmp)?$")
    for p in cand:
        m = pat.search(p.name)
        if not m:
            continue
        key = "FRWAY%03d" % int(m.group(1))
        found.setdefault(key, p)
    return dict(sorted(found.items()))


def load_shard(path: Path) -> bytes:
    if path.suffix == ".cmp":
        return addre.load_blob(path)
    return path.read_bytes()


def cmd_census(args) -> int:
    root = Path(args.root)
    shards = find_shards(root)
    want = set(args.files) if args.files else None
    if not shards:
        print(f"no FRWAY0nn.DAT under {root}", file=sys.stderr)
        return 2
    rows = []
    total = {"size": 0, "explained": 0, "padding": 0, "unexplained": 0,
             "records": 0, "main_records": 0, "route_records": 0}
    print("%-11s %3s %8s %6s %6s %6s %8s %8s %7s %6s" % (
        "shard", "t1", "bytes", "dir", "strm", "main", "mrec", "rrec", "unexp", "expl%"))
    for name, path in shards.items():
        if want and name not in want:
            continue
        try:
            blob = load_shard(path)
            info = census(blob)
        except (FrwayError, addre.AddreError, OSError) as exc:
            print(f"{name}: ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
            rows.append({"shard": name, "error": str(exc), "path": str(path)})
            continue
        info["shard"] = name
        info["path"] = str(path)
        rows.append(info)
        total["size"] += info["size"]
        total["explained"] += info["explained"]
        total["padding"] += info["padding"]
        total["unexplained"] += info["unexplained"]
        total["records"] += info["table"]["records"]
        total["main_records"] += info["streams"]["main_records"]
        total["route_records"] += info["streams"]["route_records"]
        print("%-11s %3d %8d %6d %6d %6d %8d %8d %7d %5.1f" % (
            name, info["table"]["records"], info["size"],
            info["directory"]["rows"], info["streams"]["count"],
            info["streams"]["main"], info["streams"]["main_records"],
            info["streams"]["route_records"], info["unexplained"],
            100 * info["fraction_explained"]))

    present = sorted(int(re.sub(r"FRWAY0*", "", n)) for n in shards)
    missing = [i for i in range(1, SHARD_TOTAL + 1) if i not in present]
    frac = total["explained"] / total["size"] if total["size"] else 0.0
    print()
    print("shards present: %d of %d (missing %s)" % (
        len(present), SHARD_TOTAL,
        ",".join("%03d" % m for m in missing) if missing else "none"))
    print("records: %d 12-byte BE records at 0x1110, %d main-blob, "
          "%d route-ref" % (total["records"], total["main_records"],
                            total["route_records"]))
    print("bytes: %d of %d explained (%.2f%%); %d zero/ff padding counted "
          "explained; %d real unexplained" % (
              total["explained"], total["size"], 100 * frac, total["padding"],
              total["unexplained"]))
    detail = [d for r in rows if "error" not in r
              for d in r["unexplained_detail"]]
    if detail:
        hist = Counter(d["value"] for d in detail)
        rels = sorted({d["rel_to_terminator"] for d in detail})
        print("unexplained: %d byte(s) at table-terminator+%s; values %s "
              "(histogram, meaning UNKNOWN)" % (
                  len(detail),
                  "/".join(f"0x{r:02x}" for r in rels),
                  ", ".join(f"0x{v:02x}x{n}" for v, n in sorted(hist.items()))))
    flagged = [r for r in rows if "error" not in r
               and r["fraction_explained"] < 0.5]
    if flagged:
        print("BELOW HALF EXPLAINED (the falsifier fires):",
              ", ".join(r["shard"] for r in flagged))
    else:
        print("every shard explains at least half of its bytes")

    if args.json:
        doc = {"root": str(root), "present": present, "missing": missing,
               "total": total, "rows": rows}
        Path(args.json).write_text(json.dumps(doc, indent=1, sort_keys=True))
        print(f"json: {args.json}")
    return 0 if not flagged else 1


# ---------------------------------------------------------------------------
# synthetic shard and selftest


def _schema_block(names: list[bytes]) -> bytes:
    """A factory-shape 0x100-byte schema block: signature at +0, D at +0x20."""
    sig = SCHEMA_SIG
    d = bytearray(32)
    struct.pack_into(">H", d, 24, 16)
    struct.pack_into(">H", d, 26, len(names))
    entries = bytearray()
    pos = 32
    for i, nm in enumerate(names):
        size = 16 + len(nm) + (len(nm) % 2)
        e = bytearray(size)
        struct.pack_into(">H", e, 0, (pos + size) // 2)
        struct.pack_into(">H", e, 12, i)
        e[14] = len(nm)
        e[16:16 + len(nm)] = nm
        entries += e
        pos += size
    block = bytearray(sig + bytes(16)) + d + entries
    block += bytes(0x100 - len(block))
    return bytes(block)


def _build_synthetic(mutate: bool = False) -> bytes:
    """A minimal shard in the factory shape, then (optionally) one bad byte."""
    buf = bytearray(0x1700)
    buf[0:0x10] = b"\x00C\x00L\x00A\x00R\x00I\x00O\x00N".ljust(16, b"\xff")
    nrec = 2
    struct.pack_into(">HHH", buf, TYPE_BLOCK, 0xFFFF, 0x0000, 0x0201)
    struct.pack_into(">H", buf, TYPE_BLOCK + 6, 0x0002)
    struct.pack_into(">H", buf, TYPE_BLOCK + 0x10, 0x4D40)
    struct.pack_into(">H", buf, TYPE_BLOCK + 10, 0x0200 | nrec)
    struct.pack_into(">H", buf, TYPE_BLOCK + 12, 0x0024)
    struct.pack_into(">H", buf, TYPE_BLOCK + 0x32, 0x0601)
    struct.pack_into(">H", buf, TABLE_BLOCK, 0x0024)
    struct.pack_into(">H", buf, TABLE_BLOCK + 2, 0x0036)
    recs = [(0x0012, 0x41, 0x0024, 0x0114),
            (0x001E, 0x42, 0x0012, 0x0144)]
    pos = TABLE_BLOCK + 8
    for key, ident, length, offset in recs:
        struct.pack_into(">HHBBHHH", buf, pos, key, 0, ident, 0, length, 0, offset)
        pos += 12
    struct.pack_into(">HHBBHHH", buf, pos, 0xFFFF, 0xFFFF, 0xFF, 0, 0, 0, 0)
    term = pos
    d = term + 0x10
    struct.pack_into(">BBHHHHH", buf, d, 0x41, 0, 5, 0, 0x0120, 0, 0)

    # index chain: 4e20 header + u32 length, then a zlib stream
    idx_head = b"\x4e\x20\x00\x00" + struct.pack(">I", 8)
    idx_data = struct.pack(">HHHH", 1, 1, 3, 7) + b"\x00" * 12
    idx_data += b"\x00" * 32
    idx = zlib.compress(idx_data)
    buf[0x1200:0x1200 + len(idx_head)] = idx_head
    buf[0x1208:0x1208 + len(idx)] = idx

    # schema block (0x100 bytes at 0x1400); names reachable from its signature
    buf[0x1400:0x1500] = _schema_block([b"area code", b"route number"])

    # route stream: records tagged 0xa0, framed exactly (>= 16 B decompressed)
    route = b"".join(struct.pack(">H", 0xA003) + b"E70\x00" for _ in range(3))
    rzip = zlib.compress(route)
    buf[0x1500:0x1500 + len(rzip)] = rzip
    # main stream: two 0x60 records, framed exactly
    rec0 = struct.pack(">H", 0x6006) + bytes.fromhex("a62fd03e024010c6") + b"\x00" * 2
    rec1 = struct.pack(">H", 0x6808) + bytes.fromhex("a62fd03e024010c6") + \
        struct.pack(">H", 0x0100) + b"\x00" * 4
    mzip = zlib.compress(rec0 + rec1)
    buf[0x1600:0x1600 + len(mzip)] = mzip

    if mutate:
        # flip one byte in a region no grammar reaches (the reserved fill)
        return bytes(buf[:0x1700]) + bytes(0x8FF) + b"\x7e"
    return bytes(buf[:0x1700])


def selftest() -> int:
    fails = 0

    def check(name, cond):
        nonlocal fails
        print("%-64s %s" % (name, "ok" if cond else "FAIL"))
        fails += not cond

    blob = _build_synthetic()
    info = census(blob)
    check("synthetic: four type-block markers validated",
          info["type_block"]["markers"] ==
          {"+0x00": "0xffff", "+0x04": "0x0201",
           "+0x10": "0x4d40", "+0x32": "0x0601"})
    check("synthetic: table has two records", info["table"]["records"] == 2)
    check("synthetic: directory has one row", info["directory"]["rows"] == 1)
    check("synthetic: schema has two named fields",
          info.get("schema", {}).get("names") == ["area code", "route number"])
    check("synthetic: two main records framed",
          info["streams"]["main_records"] == 2)
    check("synthetic: three route records framed",
          info["streams"]["route_records"] == 3)
    check("synthetic: every byte explained", info["unexplained"] == 0)
    check("synthetic: fraction explained is 1.0",
          abs(info["fraction_explained"] - 1.0) < 1e-9)
    check("synthetic: main record lengths are 6 and 8 words",
          info["main_fields"]["length"] == [6, 8])

    # negative control: one mutated byte in the unexplained fill must be caught
    bad = _build_synthetic(mutate=True)
    binfo = census(bad)
    check("negative: a mutated byte leaves exactly one unexplained byte",
          binfo["unexplained"] == 1)
    check("negative: the unexplained byte is the mutated offset",
          binfo["unexplained_runs"] and binfo["unexplained_runs"][0][0] == 0x1FFF)
    check("negative: the mutated byte is named in the detail",
          binfo["unexplained_detail"] == [
              {"offset": 0x1FFF,
               "rel_to_terminator": 0x1FFF - binfo["table"]["terminator"],
               "value": 0x7E}])

    # negative: a flipped type-block marker is refused, not silently skipped
    broken_marker = bytearray(_build_synthetic())
    broken_marker[TYPE_BLOCK + 0x10] = 0x00
    try:
        type_block(bytes(broken_marker))
        check("negative: a broken type-block marker is refused", False)
    except FrwayError:
        check("negative: a broken type-block marker is refused", True)

    # negative: a corrupted record-table terminator is refused
    broken = bytearray(_build_synthetic())
    broken[TABLE_BLOCK + 8 + 24] = 0x00  # key high byte: not 0xffff
    try:
        table(bytes(broken))
        check("negative: a broken table terminator is refused", False)
    except FrwayError:
        check("negative: a broken table terminator is refused", True)

    # positive control for discovery: decoded .DAT and .cmp/.ind pairs sort
    # by FRWAY number, and 001 (absent from EU, present on US) is a legal key.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "FRWAY002.DAT").write_bytes(b"")
        (root / "FRWAY033.DAT.cmp").write_bytes(b"")
        (root / "FRWAY001.DAT.cmp").write_bytes(b"")
        (root / "FRWAY001.DAT.ind").write_bytes(b"")
        (root / "ADDRE001.DAT").write_bytes(b"")
        found = find_shards(root)
        check("discovery: both decoded and .cmp pairs are found",
              list(found) == ["FRWAY001", "FRWAY002", "FRWAY033"])
        check("discovery: FRWAY001 is a legal key", "FRWAY001" in found)
    print("selftest:", "PASS" if not fails else "FAIL (%d)" % fails)
    return 0 if not fails else 1


# ---------------------------------------------------------------------------
# entry point


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("census", help="walk every shard and print the byte census")
    c.add_argument("root")
    c.add_argument("--files", nargs="*",
                   help="only these shard names (FRWAY002 FRWAY030)")
    c.add_argument("--json", help="write the census document to this path")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "census":
        return cmd_census(args)
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
