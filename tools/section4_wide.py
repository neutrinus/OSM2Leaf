#!/usr/bin/env python3
"""section4_wide.py — the section-4 level-1 ``0x1n46`` directory as rows (M4.93).

Section 4 uses the wide-row family of ``s1_wide_dir`` (M5.53/M5.54) with a
different base and body sizes, so it gets its own parser instead of changing the
section-1 model:

* directory header: six big-endian ``u16`` words ``kind, a, b, y, x, typ``;
  ``kind`` is the size in ``u16`` words and ``b`` (32 on EU2011) the row count.
* narrow row: 4-byte tag + 256-byte body = 32 columns of 8 bytes, one
  ``(u32 ln, u32 X)`` record pair per column (``ln`` = compressed words,
  ``X`` = inflated words; ``0x7fffffff``/``0xffffffff`` = no record).
* wide row: 4-byte tag + **768-byte** body = 32 columns of 24 bytes:
  ``(u32 ln, u32 X)`` then four ``u16`` compressed and four ``u16`` inflated
  sub-record sizes (``0xffff`` = no sub-record).  Bit 31 of a row's first
  ``ln`` marks it wide, as in section 1; the flag is masked before ``ln`` is
  used as a size.
* ``kind = 0x1046 + 0x100 * n_wide``: each wide row adds 512 bytes over a
  narrow one (256 -> 768), exactly the ``s1_wide_dir`` row-size step.  There is
  no trailing table; reading every row as 256 bytes (``clarion_tile.read_dir``)
  shifts every slot after the first wide row and leaves its record blocks
  unexplained (M4.86).
* the row's block (at its tag) holds the records column by column: ``rec``
  then ``sub0..sub3``, each ``2 * ln`` bytes (a zlib stream padded with zero
  bytes to a word).  On EU2011 ``B48R058R`` 420 sub-records occur; their code
  relation to the parent is not asserted here (UNKNOWN).

Sub-commands:

``census TILE``    parse every section-4 level-1 directory: size, wide-row
                   rule, zlib records, disjoint blocks and ``encode(parse)``
                   byte identity.  Prints counts only (no vendor bytes).
``dir TILE Y,X``   one directory's wide rows and record counts.

Exit codes: 0 ok, 1 a check failed, 2 usage.  Stdlib only.
"""
from __future__ import annotations

import argparse
import collections
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE / "ze0-viewer" / "tools_ze0", HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import clarion_tile  # noqa: E402
import s1_wide_dir  # noqa: E402  (check_record, addr_of: same record grammar)

BASE_KIND = 0x1046
NCOLS = 32
NARROW_PER = 8
WIDE_PER = 24
NARROW_BODY = NCOLS * NARROW_PER   # 256
WIDE_BODY = NCOLS * WIDE_PER       # 768
FLAG = 0x80000000
EMPTY_WORDS = (0xFFFFFFFF, 0x7FFFFFFF)
NO_SUB = 0xFFFF
MAX_WIDE = 15  # 0x1f46; 0x2046 is the section-1 family


class ModelError(Exception):
    pass


def wide_rows_of_kind(kind: int) -> int | None:
    """``n`` of a ``0x1046 + 0x100n`` directory, or ``None`` for another kind."""
    if kind & 0xFF != 0x46 or kind < BASE_KIND or (kind - BASE_KIND) % 0x100:
        return None
    n = (kind - BASE_KIND) // 0x100
    return n if n <= MAX_WIDE else None


def kind_for(n_wide: int) -> int:
    return BASE_KIND + 0x100 * n_wide


def addr_of(tag: int) -> int:
    return clarion_tile.addr_of(tag)


def _present(ln: int) -> bool:
    return (ln & 0x7FFFFFFF) != 0x7FFFFFFF


def decode_body(body: bytes, wide: bool) -> list[dict]:
    """Columns of one row body (no record bytes)."""
    per = WIDE_PER if wide else NARROW_PER
    if len(body) != per * NCOLS:
        raise ModelError("row body is %d bytes, expected %d" % (len(body), per * NCOLS))
    cols = []
    for c in range(NCOLS):
        b = body[c * per:(c + 1) * per]
        ln, x = struct.unpack_from(">II", b, 0)
        subs = []
        if wide:
            cw = struct.unpack_from(">4H", b, 8)
            xw = struct.unpack_from(">4H", b, 16)
            subs = list(zip(cw, xw))
        cols.append(dict(even=(ln, x), subs=subs))
    return cols


def encode_body(cols: list[dict], wide: bool) -> bytes:
    out = bytearray()
    for col in cols:
        out += struct.pack(">II", *col["even"])
        if wide:
            subs = col["subs"] or [(NO_SUB, NO_SUB)] * 4
            out += struct.pack(">4H", *(s[0] for s in subs))
            out += struct.pack(">4H", *(s[1] for s in subs))
    return bytes(out)


def record_parts(col: dict):
    """``[(part, ln_words, x_words)]`` in block order for one column."""
    parts = []
    ln, x = col["even"]
    if _present(ln):
        parts.append(("rec", ln & 0x7FFFFFFF, x))
    for k, (cw, xw) in enumerate(col["subs"]):
        if cw != NO_SUB:
            parts.append(("sub%d" % k, cw, xw))
    return parts


def check_record(raw: bytes, x_words: int) -> str | None:
    """Same zlib / inflated-size check as ``s1_wide_dir.check_record``."""
    return s1_wide_dir.check_record(raw, x_words)


def parse_dir(data: bytes, off: int, *, check: bool = True) -> dict:
    """One section-4 level-1 directory at ``off`` as rows of columns/records."""
    kind, a, b, y, x, typ = struct.unpack_from(">6H", data, off)
    nslots = b or NCOLS
    p = off + 12
    rows = []
    for i in range(nslots):
        tag = struct.unpack_from(">I", data, p)[0]
        first = struct.unpack_from(">I", data, p + 4)[0]
        wide = bool(first & FLAG)
        body = bytes(data[p + 4:p + 4 + (WIDE_BODY if wide else NARROW_BODY)])
        cols = decode_body(body, wide)
        row = dict(index=i, tag=tag, wide=wide, cols=cols, records=[], errors=[], row_off=p)
        if tag not in EMPTY_WORDS and not tag & FLAG:
            q = addr_of(tag)
            start = q
            for c, col in enumerate(cols):
                for part, ln, xw in record_parts(col):
                    raw = bytes(data[q:q + 2 * ln])
                    if check:
                        err = check_record(raw, xw)
                        if err:
                            row["errors"].append("col %d %s: %s" % (c, part, err))
                    row["records"].append(dict(col=c, part=part, raw=raw, words=xw))
                    q += 2 * ln
            row["block_off"] = start
            row["block_end"] = q
        rows.append(row)
        p += 4 + (WIDE_BODY if wide else NARROW_BODY)
    return dict(off=off, kind=kind, ab=(a, b), y=y, x=x, typ=typ, rows=rows,
                end=p, size_ok=(p - off == 2 * kind),
                wide_ok=(sum(r["wide"] for r in rows) == wide_rows_of_kind(kind)))


def encode_dir(model: dict) -> bytes:
    """Directory bytes; the kind word is recomputed from the wide-row count."""
    nwide = sum(r["wide"] for r in model["rows"])
    kind = kind_for(nwide)
    out = bytearray(struct.pack(">6H", kind, *model["ab"], model["y"], model["x"], model["typ"]))
    for row in model["rows"]:
        out += struct.pack(">I", row["tag"]) + encode_body(row["cols"], row["wide"])
    if len(out) != 2 * kind:
        raise ModelError("encoded %d bytes for kind 0x%04x" % (len(out), kind))
    return bytes(out)


def row_block(row: dict) -> bytes:
    return b"".join(r["raw"] for r in row["records"])


def section4_dirs(data: bytes, tile: dict | None = None):
    """Section-4 level-1 directory descriptors via ``clarion_tile`` (offsets only)."""
    tile = tile or clarion_tile.read_tile(data)
    out = []
    for sec in tile["sections"]:
        if sec["id"] != 4:
            continue
        for level in sec["levels"]:
            if level["level"] != 1:
                continue
            out.extend(level["dirs"])
    return out


def row_block_spans(data: bytes, tile: dict | None = None) -> list[tuple[int, int]]:
    """``[(start, end)]`` of every section-4 level-1 row's record block."""
    spans = []
    for d in section4_dirs(data, tile):
        m = parse_dir(data, d["off"], check=False)
        for row in m["rows"]:
            if "block_off" in row and row["block_end"] > row["block_off"]:
                spans.append((row["block_off"], row["block_end"]))
    return spans


def census(data: bytes) -> dict:
    st = collections.Counter()
    by_kind = collections.Counter()
    problems = []
    spans = []
    for d in section4_dirs(data):
        m = parse_dir(data, d["off"])
        by_kind["0x%04x" % m["kind"]] += 1
        st["dirs"] += 1
        st["size_ok"] += m["size_ok"]
        st["wide_ok"] += m["wide_ok"]
        st["wide_rows"] += sum(r["wide"] for r in m["rows"])
        st["records"] += sum(len(r["records"]) for r in m["rows"])
        st["records_bad"] += sum(len(r["errors"]) for r in m["rows"])
        if not m["size_ok"]:
            problems.append("dir 0x%x: size %d != 2*kind %d" % (m["off"], m["end"] - m["off"], 2 * m["kind"]))
        if not m["wide_ok"]:
            problems.append("dir 0x%x kind 0x%04x: wide rule fails" % (m["off"], m["kind"]))
        if encode_dir(m) == bytes(data[m["off"]:m["end"]]):
            st["roundtrip_ok"] += 1
        else:
            problems.append("dir 0x%x: encode(parse) differs" % m["off"])
        for r in m["rows"]:
            problems.extend("dir 0x%x row %d %s" % (m["off"], r["index"], e) for e in r["errors"][:2])
            if "block_off" in r and r["block_end"] > r["block_off"]:
                spans.append((r["block_off"], r["block_end"]))
    spans.sort()
    st["row_blocks"] = len(spans)
    st["block_overlaps"] = sum(1 for (a0, a1), (b0, _b1) in zip(spans, spans[1:]) if b0 < a1)
    return dict(counts=dict(st), by_kind=dict(sorted(by_kind.items())), problems=problems)


def census_ok(c: dict) -> bool:
    k = collections.Counter(c["counts"])
    return (k.get("dirs", 0) > 0 and not c["problems"]
            and k["size_ok"] == k["wide_ok"] == k["roundtrip_ok"] == k["dirs"]
            and k.get("records_bad", 0) == 0 and k.get("block_overlaps", 0) == 0)


def render_census(c: dict) -> str:
    k = collections.Counter(c["counts"])
    lines = ["by kind: " + " ".join("%s=%d" % kv for kv in c["by_kind"].items())]
    lines.append("s4-wide census: dirs=%d size_ok=%d wide_ok=%d roundtrip_ok=%d wide_rows=%d "
                 "records=%d records_bad=%d row_blocks=%d block_overlaps=%d %s"
                 % (k["dirs"], k["size_ok"], k["wide_ok"], k["roundtrip_ok"], k["wide_rows"],
                    k["records"], k.get("records_bad", 0), k["row_blocks"],
                    k.get("block_overlaps", 0), "OK" if census_ok(c) else "FAIL"))
    lines.extend("problem: " + p for p in c["problems"][:20])
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Self-test (synthetic directory, no vendor bytes)
# --------------------------------------------------------------------------


def _zrec(words: int) -> bytes:
    plain = b"\x00\x09" + b"\x00\xfa" + bytes(2 * words - 4)
    comp = bytearray(zlib_compress(plain))
    if len(comp) % 2:
        comp += b"\x00"
    return bytes(comp)


def zlib_compress(plain: bytes) -> bytes:
    import zlib
    return zlib.compress(plain, 6)


def synthetic_dir(wide_rows=(3, 4), sub_cols=((3, 5),)) -> tuple[bytes, int]:
    """``(bytes, off)``: a section-4 directory at ``off`` followed by its blocks."""
    off = 0x1000
    nwide = len(wide_rows)
    kind = kind_for(nwide)
    blk_start = clarion_tile.pad256(off + 2 * kind)
    q = blk_start
    rows = []
    blocks = bytearray()
    for i in range(32):
        wide = i in wide_rows
        cols = []
        for c in range(NCOLS):
            ln = len(_zrec(20 + c)) // 2
            subs = []
            if wide:
                if (i, c) in sub_cols:
                    for _k in range(4):
                        sr = _zrec(10 + _k)
                        subs.append((len(sr) // 2, 10 + _k))
                else:
                    subs = [(NO_SUB, NO_SUB)] * 4
                if c == 0:
                    ln |= FLAG
            cols.append(dict(even=(ln, 20 + c), subs=subs))
        # Record order inside a block: rec then sub0..sub3, column by column.
        recs = []
        for col in cols:
            recs.append(_zrec(col["even"][1]))
            for _cw, xw in col["subs"]:
                if _cw != NO_SUB:
                    recs.append(_zrec(xw))
        block = b"".join(recs)
        tag = clarion_tile.enc_addr(q)
        rows.append(dict(index=i, tag=tag, wide=wide, cols=cols))
        blocks += block + b"\x00" * (clarion_tile.pad256(len(block)) - len(block))
        q += clarion_tile.pad256(len(block))
    model = dict(off=off, kind=kind, ab=(32, 32), y=76,
                 x=(941 - s1_wide_dir.X_FIELD_BIAS) & 0xFFFF, typ=0x93, rows=rows)
    dbytes = encode_dir(model)
    data = bytearray(b"\x00" * off) + dbytes
    data += b"\x00" * (blk_start - len(data))
    data += blocks
    return bytes(data), off


def selftest() -> int:
    results = []

    def chk(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    chk("kind 0x1046 has 0 wide rows", wide_rows_of_kind(0x1046) == 0)
    chk("kind 0x1146 has 1 wide row", wide_rows_of_kind(0x1146) == 1)
    chk("kind 0x1946 has 9 wide rows", wide_rows_of_kind(0x1946) == 9)
    chk("kind 0x2046 is not this family", wide_rows_of_kind(0x2046) is None)
    chk("one wide row adds 512 bytes", 2 * kind_for(1) - 2 * BASE_KIND == 512)
    chk("wide body is 768 bytes", WIDE_BODY == 768)

    data, off = synthetic_dir()
    m = parse_dir(data, off)
    chk("synthetic: kind word 0x1246", m["kind"] == 0x1246, hex(m["kind"]))
    chk("synthetic: size == 2*kind", m["size_ok"])
    chk("synthetic: wide rule ok", m["wide_ok"])
    chk("synthetic: rows 3 and 4 wide", [r["index"] for r in m["rows"] if r["wide"]] == [3, 4])
    chk("synthetic: every record checks", all(not r["errors"] for r in m["rows"]),
        [r["errors"] for r in m["rows"] if r["errors"]][:1])
    chk("synthetic: 4 sub-records in row 3 col 5",
        sum(1 for r in m["rows"][3]["records"] if r["col"] == 5 and r["part"].startswith("sub")) == 4)
    chk("synthetic: encode(parse) byte-identical", encode_dir(m) == data[off:m["end"]])
    chk("synthetic: row blocks disjoint",
        all(b[0] >= a[1] for a, b in zip(
            sorted((r["block_off"], r["block_end"]) for r in m["rows"] if "block_off" in r),
            sorted((r["block_off"], r["block_end"]) for r in m["rows"] if "block_off" in r)[1:])))

    # Negative control (a): a corrupted record must be reported.
    bad = bytearray(data)
    q = m["rows"][7]["block_off"]
    bad[q] ^= 0xFF
    chk("negative: corrupted record reported", any(r["errors"] for r in parse_dir(bytes(bad), off)["rows"]))

    # Negative control (b): a forged wide marker breaks size == 2*kind.
    flip = bytearray(data)
    p = m["rows"][10]["row_off"] + 4  # row 10 is narrow; its first body word
    struct.pack_into(">I", flip, p, struct.unpack_from(">I", flip, p)[0] | FLAG)
    mf = parse_dir(bytes(flip), off, check=False)
    chk("negative: forged wide marker breaks size", not mf["size_ok"])

    # Negative control (c): an over-long sub-record size is rejected.
    long = bytearray(data)
    # row 3 wide body starts at off+12 + 3*(4+NARROW_BODY); col 5 subs at +8 of its cell
    rp = off + 12 + 3 * (4 + NARROW_BODY) + 4 + 5 * WIDE_PER + 8
    struct.pack_into(">H", long, rp, 0xFFF0)
    ml = parse_dir(bytes(long), off)
    chk("negative: over-long sub-record rejected", any(r["errors"] for r in ml["rows"]))

    ok = sum(1 for _, good, _ in results if good)
    for name, good, detail in results:
        if not good:
            print("FAIL %s %s" % (name, detail))
    print("section4_wide selftest: %s (%d/%d checks)" % ("OK" if ok == len(results) else "FAIL", ok, len(results)))
    return 0 if ok == len(results) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    cp = sub.add_parser("census", help="model every section-4 level-1 directory of a tile")
    cp.add_argument("tile")
    dp = sub.add_parser("dir", help="one section-4 level-1 directory")
    dp.add_argument("tile")
    dp.add_argument("yx", metavar="Y,X")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd is None:
        ap.print_usage(sys.stderr)
        return 2
    data = Path(a.tile).read_bytes()
    if a.cmd == "census":
        c = census(data)
        print(render_census(c))
        return 0 if census_ok(c) else 1
    y, x = (int(v) for v in a.yx.split(","))
    for d in section4_dirs(data):
        if d["y"] == y and (d["x"] + s1_wide_dir.X_FIELD_BIAS) & 0xFFFF == x:
            m = parse_dir(data, d["off"])
            print("dir %d,%d off=0x%x kind=0x%04x size_ok=%s wide_ok=%s wide_rows=%d records=%d errors=%d"
                  % (y, x, d["off"], m["kind"], m["size_ok"], m["wide_ok"],
                     sum(r["wide"] for r in m["rows"]), sum(len(r["records"]) for r in m["rows"]),
                     sum(len(r["errors"]) for r in m["rows"])))
            return 0 if m["size_ok"] and m["wide_ok"] and not any(r["errors"] for r in m["rows"]) else 1
    print("no section-4 level-1 directory %d,%d" % (y, x), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
