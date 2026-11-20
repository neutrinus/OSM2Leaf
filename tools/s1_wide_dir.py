#!/usr/bin/env python3
"""s1_wide_dir.py — the section-1 level-1 ``0x2n46`` directory as rows (M5.53).

A ZE0 (X08-02-00) section-1 level-1 directory starts with six big-endian
``u16`` words ``kind, a, b, y, x, typ``.  ``kind`` is the directory size in
``u16`` words: ``0x2046`` = 12 + 32 x (4 + 512) bytes.  The "kinds"
``0x2146`` ... ``0x2946`` are the same directory with **n wide rows**
(``n = (kind - 0x2046) >> 8``): a wide row carries a 1,024-byte body instead
of 512.  There is no trailing table; reading every row as 512 bytes (as
``clarion_tile.read_dir`` does) shifts every slot after the first wide row by
512 bytes and turns the next tags and pairs into the "0xffffffff pair fields"
and "non-zlib blocks" of EXP-2026-11-08-M5.22.

Row layout (level 1, 32 columns, OBSERVED on EU2011 ``B48R058R``):

* narrow row, 16 bytes per column: ``even (u32 ln, u32 X)``, ``odd (u32 ln,
  u32 X)``; ``ln`` = record size in ``u16`` words, ``X`` = inflated words;
  ``0x7fffffff`` / ``0xffffffff`` = no record.
* wide row, 32 bytes per column: ``even (8)``, four sub-record compressed sizes
  (4 x ``u16``), four sub-record inflated sizes (4 x ``u16``, ``0xffff`` = none),
  ``odd (8)``.  Bit 31 of the even ``ln`` is a flag; it is set on the first
  word of every wide row (``0xffffffff`` when column 0 is empty) and on the
  even pair of a column that has sub-records.  A narrow row never sets it, so
  bit 31 of a row's first body word decides its width.
* the row's block (at its tag) holds the records column by column:
  ``even, sub0..sub3, odd``, each ``2 * ln`` bytes (a zlib stream padded with
  zero bytes to a word).  The four sub-records carry the parent parcel code
  with the low nibble ``0xc | r`` replaced by ``(half << 2) | r`` — a 2 x 2
  split of the parcel (``(i, j) = (k >> 1, k & 1)`` for sub-record ``k``).

Sub-commands:

``census TILE``  parse every section-1 directory with this model and check it:
                 wide rows == n, size == 2 * kind, every record a zlib stream
                 of exactly ``X`` words inside ``2 * ln`` bytes, row blocks
                 pairwise disjoint, sub-record codes, and ``encode(parse(dir))``
                 byte-identical.  Prints counts only (no vendor bytes).
``dir TILE Y,X`` one directory's wide rows and flagged columns.

Exit codes: 0 ok, 1 a check failed, 2 usage.  Stdlib only.
"""
from __future__ import annotations

import argparse
import collections
import json
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE / "ze0-viewer" / "tools_ze0", HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import clarion_tile  # noqa: E402

NARROW_KIND = 0x2046
NROWS = 32
NCOLS = 32
NARROW_BODY = 512
WIDE_BODY = 1024
FLAG = 0x80000000
EMPTY_WORDS = (0xFFFFFFFF, 0x7FFFFFFF)
NO_SUB = 0xFFFF
X_FIELD_BIAS = 1024


class ModelError(Exception):
    pass


def wide_rows_of_kind(kind: int) -> int | None:
    """``n`` of a ``0x2n46`` directory, or ``None`` for another kind."""
    if kind & 0xFF != 0x46 or kind < NARROW_KIND or (kind - NARROW_KIND) % 0x100:
        return None
    return (kind - NARROW_KIND) >> 8


def kind_for(n_wide: int) -> int:
    return NARROW_KIND + 0x100 * n_wide


def addr_of(tag: int) -> int:
    return clarion_tile.addr_of(tag)


def _pair_present(ln: int) -> bool:
    return (ln & 0x7FFFFFFF) != 0x7FFFFFFF


def decode_body(body: bytes, wide: bool) -> list[dict]:
    """Columns of one row body (no record bytes)."""
    per = 32 if wide else 16
    if len(body) != per * NCOLS:
        raise ModelError("row body is %d bytes, expected %d" % (len(body), per * NCOLS))
    cols = []
    for c in range(NCOLS):
        b = body[c * per:(c + 1) * per]
        e_ln, e_x = struct.unpack_from(">II", b, 0)
        o_ln, o_x = struct.unpack_from(">II", b, per - 8)
        subs = []
        if wide:
            cw = struct.unpack_from(">4H", b, 8)
            xw = struct.unpack_from(">4H", b, 16)
            subs = list(zip(cw, xw))
        cols.append(dict(even=(e_ln, e_x), odd=(o_ln, o_x), subs=subs))
    return cols


def encode_body(cols: list[dict], wide: bool) -> bytes:
    out = bytearray()
    for col in cols:
        out += struct.pack(">II", *col["even"])
        if wide:
            subs = col["subs"] or [(NO_SUB, NO_SUB)] * 4
            out += struct.pack(">4H", *(s[0] for s in subs))
            out += struct.pack(">4H", *(s[1] for s in subs))
        out += struct.pack(">II", *col["odd"])
    return bytes(out)


def record_parts(col: dict):
    """``[(part, ln_words, x_words)]`` in block order for one column."""
    parts = []
    ln, x = col["even"]
    if _pair_present(ln):
        parts.append(("even", ln & 0x7FFFFFFF, x))
    for k, (cw, xw) in enumerate(col["subs"]):
        if cw != NO_SUB:
            parts.append(("sub%d" % k, cw, xw))
    ln, x = col["odd"]
    if _pair_present(ln):
        parts.append(("odd", ln & 0x7FFFFFFF, x))
    return parts


def check_record(raw: bytes, x_words: int) -> str | None:
    """``None`` if ``raw`` is one zlib stream of ``2*x_words`` bytes plus zero pad.

    A sub-record of size ``(0, 0)`` is an empty sub-parcel (no bytes): OK.
    """
    if not raw and x_words == 0:
        return None
    if len(raw) < 2 or raw[0] & 0x0F != 8 or ((raw[0] << 8) | raw[1]) % 31:
        return "not zlib"
    try:
        obj = zlib.decompressobj()
        plain = obj.decompress(raw)
    except zlib.error as exc:
        return "zlib error %s" % exc
    if not obj.eof:
        return "stream does not end inside 2*ln bytes"
    if len(plain) != 2 * x_words:
        return "inflates to %d bytes, X says %d" % (len(plain), 2 * x_words)
    if obj.unused_data.strip(b"\x00") or len(obj.unused_data) > 3:
        return "%d non-pad bytes after the stream" % len(obj.unused_data)
    return None


def parse_dir(data: bytes, off: int, level: int = 1, *, check: bool = True) -> dict:
    """One section-1 directory at ``off`` as rows of columns and records."""
    kind, a, b, y, x, typ = struct.unpack_from(">6H", data, off)
    nslots = b or NROWS
    p = off + 12
    rows = []
    for i in range(nslots):
        tag = struct.unpack_from(">I", data, p)[0]
        first = struct.unpack_from(">I", data, p + 4)[0]
        wide = level == 1 and bool(first & FLAG)
        blen = WIDE_BODY if wide else NARROW_BODY
        body = bytes(data[p + 4:p + 4 + blen])
        cols = decode_body(body, wide)
        row = dict(index=i, tag=tag, wide=wide, cols=cols, records=[], errors=[])
        if tag not in EMPTY_WORDS and not tag & FLAG:
            q = addr_of(tag)
            row["block_off"] = q
            for c, col in enumerate(cols):
                for part, ln, xw in record_parts(col):
                    raw = bytes(data[q:q + 2 * ln])
                    if check:
                        err = check_record(raw, xw)
                        if err:
                            row["errors"].append("col %d %s: %s" % (c, part, err))
                    row["records"].append(dict(col=c, part=part, raw=raw, words=xw))
                    q += 2 * ln
            row["block_end"] = q
        rows.append(row)
        p += 4 + blen
    return dict(off=off, kind=kind, ab=(a, b), y=y, x=x, typ=typ, level=level,
                rows=rows, end=p, size_ok=(p - off == 2 * kind))


def encode_dir(model: dict) -> bytes:
    """Directory bytes; the kind word is recomputed from the wide-row count."""
    nwide = sum(1 for r in model["rows"] if r["wide"])
    kind = kind_for(nwide) if model.get("level", 1) == 1 else model["kind"]
    out = bytearray(struct.pack(">6H", kind, *model["ab"], model["y"], model["x"], model["typ"]))
    for row in model["rows"]:
        out += struct.pack(">I", row["tag"]) + encode_body(row["cols"], row["wide"])
    if len(out) != 2 * kind:
        raise ModelError("encoded %d bytes for kind 0x%04x" % (len(out), kind))
    return bytes(out)


def row_block(row: dict) -> bytes:
    return b"".join(r["raw"] for r in row["records"])


def narrow_row(row: dict) -> bool:
    """Turn a wide row without sub-records into a narrow row (in place).

    Returns False (and changes nothing) while any column still has a
    sub-record.  Clears the bit-31 flag of every even pair; the record bytes
    and the block order (even, odd per column) are unchanged.
    """
    if not row["wide"]:
        return True
    if any(cw != NO_SUB for col in row["cols"] for cw, _ in col["subs"]):
        return False
    for col in row["cols"]:
        ln, x = col["even"]
        col["even"] = (ln & 0x7FFFFFFF, x)
        col["subs"] = []
    row["wide"] = False
    return True


def sub_code(parent: tuple[int, int], k: int) -> tuple[int, int]:
    """Parcel code of sub-record ``k`` of a level-1 parent code (OBSERVED rule)."""
    i, j = k >> 1, k & 1
    w0 = (parent[0] & ~0xC) | (i << 2)
    w1 = (parent[1] & ~0xC) | (j << 2)
    return w0 & 0xFFFF, w1 & 0xFFFF


def section1_dirs(data: bytes):
    """``[(level, directory)]`` of section 1 via ``clarion_tile`` (offsets only)."""
    tile = clarion_tile.read_tile(data)
    out = []
    for sec in tile["sections"]:
        if sec["id"] != 1:
            continue
        for entry in sec["levels"]:
            for d in entry["dirs"]:
                out.append((entry["level"], d))
    return out


def census(data: bytes) -> dict:
    st = collections.Counter()
    by_kind = collections.Counter()
    problems = []
    spans = []
    for level, d in section1_dirs(data):
        if level not in (1, 2):
            # Levels 3-6 (LEV3456R) use other directory bodies; not this model.
            st["dirs_other_levels"] += 1
            continue
        m = parse_dir(data, d["off"], level)
        dx = (m["x"] + X_FIELD_BIAS) & 0xFFFF
        st["dirs"] += 1
        nwide = sum(r["wide"] for r in m["rows"])
        expect = wide_rows_of_kind(m["kind"]) if level == 1 else 0
        by_kind["0x%04x" % m["kind"]] += 1
        st["wide_rows"] += nwide
        if expect == nwide:
            st["kind_rule_ok"] += 1
        else:
            problems.append("dir %d,%d kind 0x%04x: %d wide rows" % (m["y"], dx, m["kind"], nwide))
        if m["size_ok"]:
            st["size_ok"] += 1
        else:
            problems.append("dir %d,%d: size %d != 2*kind" % (m["y"], dx, m["end"] - m["off"]))
        # Negative control: the 512-byte reading (clarion_tile.read_dir) of the
        # same directory; count rows whose tag it reads differently.
        for row in m["rows"]:
            s512 = d["slots"].get(row["index"])
            tag512 = s512["tag"] if s512 else d.get("empty_tags", {}).get(row["index"])
            if tag512 != row["tag"]:
                st["rows_512_reader_wrong_tag"] += 1
        if encode_dir(m) == bytes(data[m["off"]:m["end"]]):
            st["roundtrip_ok"] += 1
        else:
            problems.append("dir %d,%d: encode(parse) differs" % (m["y"], dx))
        for row in m["rows"]:
            st["records"] += len(row["records"])
            st["records_bad"] += len(row["errors"])
            problems.extend("dir %d,%d row %d %s" % (m["y"], dx, row["index"], e)
                            for e in row["errors"][:3])
            if "block_off" in row and row["block_end"] > row["block_off"]:
                spans.append((row["block_off"], row["block_end"], (m["y"], dx, row["index"])))
            for c, col in enumerate(row["cols"]):
                ln = col["even"][0]
                flagged = bool(ln & FLAG) and ln != 0xFFFFFFFF
                has_subs = any(cw != NO_SUB for cw, _ in col["subs"])
                if bool(col["odd"][0] & FLAG) and col["odd"][0] != 0xFFFFFFFF:
                    st["odd_flagged"] += 1
                if not row["wide"]:
                    if flagged:
                        st["narrow_flagged"] += 1
                    continue
                if has_subs:
                    st["cols_with_subs"] += 1
                    st["cols_with_subs_flagged"] += flagged
                elif flagged:
                    st["flag_without_subs_col0" if c == 0 else "flag_without_subs_other"] += 1
            if row["wide"]:
                st["wide_first_word_flag"] += bool(row["cols"][0]["even"][0] & FLAG)
                recs = {(r["col"], r["part"]): r for r in row["records"]}
                for c in range(NCOLS):
                    parent = recs.get((c, "even"))
                    for k in range(4):
                        sub = recs.get((c, "sub%d" % k))
                        if sub is None:
                            continue
                        if not sub["raw"]:
                            st["sub_records_empty"] += 1
                            continue
                        st["sub_records"] += 1
                        if parent is None or row["errors"]:
                            continue
                        pc = struct.unpack(">2H", zlib.decompress(parent["raw"])[:4])
                        sc = struct.unpack(">2H", zlib.decompress(sub["raw"])[:4])
                        if sc == sub_code(pc, k):
                            st["sub_code_ok"] += 1
                        else:
                            problems.append("dir %d,%d row %d col %d sub%d code %04x,%04x parent %04x,%04x"
                                            % (m["y"], dx, row["index"], c, k, *sc, *pc))
    spans.sort()
    overlaps = 0
    for (a0, a1, _), (b0, _b1, _) in zip(spans, spans[1:]):
        if b0 < a1:
            overlaps += 1
    st["row_blocks"] = len(spans)
    st["block_overlaps"] = overlaps
    return dict(counts=dict(st), by_kind=dict(sorted(by_kind.items())), problems=problems)


def census_ok(c: dict) -> bool:
    k = collections.Counter(c["counts"])
    if not k.get("dirs"):
        return False
    return (not c["problems"] and k.get("records_bad", 0) == 0 and k.get("block_overlaps", 0) == 0
            and k["kind_rule_ok"] == k["dirs"] == k["size_ok"] == k["roundtrip_ok"])


def render_census(c: dict) -> str:
    k = collections.Counter(c["counts"])
    lines = ["by kind: " + " ".join("%s=%d" % kv for kv in c["by_kind"].items())]
    for key in ("wide_rows", "wide_first_word_flag", "cols_with_subs", "cols_with_subs_flagged",
                "flag_without_subs_col0", "flag_without_subs_other", "narrow_flagged",
                "odd_flagged", "sub_records", "sub_records_empty", "sub_code_ok", "row_blocks", "rows_512_reader_wrong_tag"):
        lines.append("%s=%d" % (key, k.get(key, 0)))
    lines.extend("problem: " + p for p in c["problems"][:20])
    lines.append("dirs_other_levels=%d (levels 3-6, not modelled here)" % k.get("dirs_other_levels", 0))
    lines.append("s1-wide census: dirs=%d kind_rule_ok=%d size_ok=%d roundtrip_ok=%d records=%d "
                 "records_bad=%d block_overlaps=%d %s"
                 % (k["dirs"], k["kind_rule_ok"], k["size_ok"], k["roundtrip_ok"], k["records"],
                    k.get("records_bad", 0), k["block_overlaps"], "OK" if census_ok(c) else "FAIL"))
    return "\n".join(lines)


def find_dir(data: bytes, y: int, x0: int, level: int = 1):
    for lv, d in section1_dirs(data):
        if lv == level and d["y"] == y and (d["x"] + X_FIELD_BIAS) & 0xFFFF == x0:
            return parse_dir(data, d["off"], level)
    return None


def describe_dir(m: dict) -> str:
    dx = (m["x"] + X_FIELD_BIAS) & 0xFFFF
    lines = ["dir %d,%d off=0x%x kind=0x%04x wide_rows=%d size_ok=%s"
             % (m["y"], dx, m["off"], m["kind"], sum(r["wide"] for r in m["rows"]), m["size_ok"])]
    for row in m["rows"]:
        if not row["wide"]:
            continue
        sub_cols = [c for c, col in enumerate(row["cols"]) if any(cw != NO_SUB for cw, _ in col["subs"])]
        flag_cols = [c for c, col in enumerate(row["cols"])
                     if col["even"][0] & FLAG and col["even"][0] != 0xFFFFFFFF]
        lines.append("  row %2d wide records=%d flagged_cols=%s sub_cols=%s errors=%d"
                     % (row["index"], len(row["records"]), flag_cols, sub_cols, len(row["errors"])))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Self-test (synthetic directory, no vendor bytes)
# --------------------------------------------------------------------------

def _zrec(code, words):
    plain = struct.pack(">2H", *code) + b"\x00\xfa" + bytes(2 * words - 6)
    comp = zlib.compress(plain, 6)
    if len(comp) % 2:
        comp += b"\x00"
    return comp, words


def synthetic_dir(wide_rows=(3,), sub_cols=((3, 5),), base=0x10000, kind=None):
    """``(bytes, off)``: a directory at ``off`` followed by its row blocks."""
    off = 0x1000
    rows = []
    blocks = bytearray()
    blk_start = clarion_tile.pad256(off + 2 * kind_for(len(wide_rows)))
    q = blk_start
    for i in range(NROWS):
        wide = i in wide_rows
        cols = []
        recs = []
        for c in range(NCOLS):
            code = (0xA60C | (i & 3) | ((i >> 2) << 4), 0xD60C | (c & 3) | ((c >> 2) << 4))
            even_raw, ew = _zrec(code, 40 + c)
            odd_raw, ow = _zrec(code, 20)
            subs = []
            parts = [even_raw]
            ln = len(even_raw) // 2
            if wide:
                if (i, c) in sub_cols:
                    for k in range(4):
                        sr, sw = _zrec(sub_code(code, k), 30 + k)
                        subs.append((len(sr) // 2, sw))
                        parts.append(sr)
                    ln |= FLAG
                else:
                    subs = [(NO_SUB, NO_SUB)] * 4
                if c == 0:
                    ln |= FLAG
            parts.append(odd_raw)
            cols.append(dict(even=(ln, ew), odd=(len(odd_raw) // 2, ow), subs=subs))
            recs.extend(parts)
        block = b"".join(recs)
        tag = clarion_tile.enc_addr(q)
        rows.append(dict(index=i, tag=tag, wide=wide, cols=cols))
        blocks += block
        pad = clarion_tile.pad256(len(block)) - len(block)
        blocks += b"\x00" * pad
        q += len(block) + pad
    model = dict(kind=0, ab=(32, 32), y=76, x=(941 - X_FIELD_BIAS) & 0xFFFF, typ=146, level=1, rows=rows)
    dbytes = encode_dir(model)
    data = bytearray(b"\x00" * off) + dbytes
    data += b"\x00" * (blk_start - len(data))
    data += blocks
    return bytes(data), off


def selftest() -> int:
    results = []

    def chk(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    chk("kind 0x2046 has 0 wide rows", wide_rows_of_kind(0x2046) == 0)
    chk("kind 0x2146 has 1 wide row", wide_rows_of_kind(0x2146) == 1)
    chk("kind 0x2946 has 9 wide rows", wide_rows_of_kind(0x2946) == 9)
    chk("kind 0x1046 is not this family", wide_rows_of_kind(0x1046) is None)
    chk("0x2146 size = 0x2046 size + 512 bytes", 2 * kind_for(1) - 2 * NARROW_KIND == 512)
    chk("sub code rule", sub_code((0xA65D, 0xD68D), 3) == (0xA655, 0xD685)
        and sub_code((0xA65D, 0xD68D), 0) == (0xA651, 0xD681))

    data, off = synthetic_dir(wide_rows=(3,), sub_cols=((3, 5),))
    m = parse_dir(data, off)
    chk("synthetic: kind word 0x2146", m["kind"] == 0x2146, hex(m["kind"]))
    chk("synthetic: size == 2*kind", m["size_ok"])
    chk("synthetic: exactly row 3 wide", [r["index"] for r in m["rows"] if r["wide"]] == [3])
    chk("synthetic: every record checks", all(not r["errors"] for r in m["rows"]),
        [r["errors"] for r in m["rows"] if r["errors"]][:1])
    chk("synthetic: 4 sub-records in row 3 col 5",
        sum(1 for r in m["rows"][3]["records"] if r["col"] == 5 and r["part"].startswith("sub")) == 4)
    chk("synthetic: row 4 follows the wide row (tag readable)",
        m["rows"][4]["block_off"] == m["rows"][3]["block_end"] + (-m["rows"][3]["block_end"]) % 256)
    chk("synthetic: encode(parse) byte-identical", encode_dir(m) == data[off:m["end"]])

    # The 512-byte reading (clarion_tile) misreads every slot after the wide row.
    d512 = clarion_tile.read_dir(data, off, box=(0, 0, 0, 0))
    chk("negative: 512-byte reader misplaces row 4's tag",
        d512["slots"].get(4, {}).get("tag") != m["rows"][4]["tag"])

    # A wide row with sub-records cannot be narrowed; without them it can.
    row3 = m["rows"][3]
    chk("narrow refused while sub-records remain", narrow_row(row3) is False and row3["wide"])
    col = row3["cols"][5]
    col["subs"] = [(NO_SUB, NO_SUB)] * 4
    row3["records"] = [r for r in row3["records"] if not (r["col"] == 5 and r["part"].startswith("sub"))]
    chk("narrow accepted once sub-records are gone", narrow_row(row3) is True and not row3["wide"])
    chk("narrowed: no even flag left", all(not c["even"][0] & FLAG for c in row3["cols"]))
    m2 = dict(m)
    enc = encode_dir(m2)
    chk("narrowed directory is kind 0x2046 (16,524 bytes)",
        struct.unpack(">H", enc[:2])[0] == 0x2046 and len(enc) == 16524, hex(struct.unpack(">H", enc[:2])[0]))

    # census on a minimal tile is covered by the real-tile run (needs a tile header);
    # here: a broken record is reported.
    bad = bytearray(data)
    q = m["rows"][7]["block_off"]
    bad[q] ^= 0xFF
    mb = parse_dir(bytes(bad), off)
    chk("negative: corrupted record reported", any(r["errors"] for r in mb["rows"]))

    # Flag on a narrow row's first word would make it wide: the size check fails.
    flip = bytearray(data)
    p = off + 12 + 10 * 516 + 512 + 4  # row 10 sits after the wide row 3
    struct.pack_into(">I", flip, p, struct.unpack_from(">I", flip, p)[0] | FLAG)
    mf = parse_dir(bytes(flip), off, check=False)
    chk("negative: a forged wide marker breaks size == 2*kind", not mf["size_ok"])

    ok = sum(1 for _, good, _ in results if good)
    for name, good, detail in results:
        if not good:
            print("FAIL %s %s" % (name, detail))
    print("s1_wide_dir selftest: %s (%d/%d checks)" % ("OK" if ok == len(results) else "FAIL", ok, len(results)))
    return 0 if ok == len(results) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    cp = sub.add_parser("census", help="model every section-1 directory of a tile")
    cp.add_argument("tile")
    cp.add_argument("--json", metavar="PATH")
    dp = sub.add_parser("dir", help="one level-1 directory's wide rows")
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
        if a.json:
            Path(a.json).write_text(json.dumps(c, indent=1, sort_keys=True) + "\n")
        return 0 if census_ok(c) else 1
    y, x = (int(v) for v in a.yx.split(","))
    m = find_dir(data, y, x)
    if m is None:
        print("no level-1 directory %d,%d" % (y, x), file=sys.stderr)
        return 2
    print(describe_dir(m))
    return 0 if m["size_ok"] and not any(r["errors"] for r in m["rows"]) else 1


if __name__ == "__main__":
    sys.exit(main())
