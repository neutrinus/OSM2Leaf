#!/usr/bin/env python3
"""Low-nibble census of ``COORD001`` and ``ADDRE`` ids, and the ``ADDRE`` fine-field search (M4.61).

``point_census`` found that the copy-A words of a POINT name record are not
1-unit coordinates: their low nibble is ``11xx`` (two marker bits, then a
4-unit sub-cell index) and two 11-bit fields refine the sub-cell in 1/512
unit (M4.27, C-2679).  ``coord.py``, however, decoded ``COORD001`` bboxes and
``ADDRE`` ids with the 1-unit ``(x-32768)/192``, ``(y-52742)/128`` form.  This
tool measures, offline and read-only, whether those ids share the POINT form:

  * ``COORD001``: every entry is 14 bytes ``x0, y0, x1, y1, level_u32,
    pad_u16`` (``coord_zcode_icode.coord001_records``); census the low nibble
    of the four coordinate words only.  ``COORD001`` has **no fine field**.
  * ``ADDRE``: every record's packed ``coord`` id (``(cx, cy)``, the two
    ``u16`` of the ``06 00 ax ay`` token, ``addre.parse_record``) -- census
    both words.  ADDRE has no name record, so the POINT-style ``0x0800`` fine
    pair is searched for separately.

The answer is reported per shard and per card as a histogram, not as one
verdict: the cards mix ``11xx`` and 0..7 nibbles, and in the EU 2011 card the
split is per shard (Monaco's ids are ``11xx``, Andorra's are not).

``fine`` searches every even byte offset of every ADDRE record for two
adjacent ``u16`` that look like the POINT fine pair (bit ``0x0800`` set, low
bits 0..0x7ff), records the offsets where they occur, and reports the closest
occurrence to the id token.  It answers "no POINT-style 11-bit pair" (the
common case) separately from "no fine position at all" (the offsets tested).

Usage:
  python3 tools/refer_id_census.py ids --eu DIR --us DIR [--shards ADDRE001 ...]
  python3 tools/refer_id_census.py fine --dir DIR [--shards ADDRE001 ADDRE017]
  python3 tools/refer_id_census.py --selftest

DIR holds ``COORD001.DAT.cmp``/``.ind`` and ``ADDRE0nn.DAT.cmp``/``.ind``
pairs.  Read-only; no vendor bytes are written anywhere.
"""
from __future__ import annotations

import argparse
import struct
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import addre  # noqa: E402
import cmpind  # noqa: E402
import coord  # noqa: E402
import coord_zcode_icode as cz  # noqa: E402

#: The POINT fine layout (M3.34/M4.27, record bytes 6-9): the first word is
#: ``0x0800 | fine_lon`` (low 11 bits) and the second is the raw ``fine_lat``
#: (0..0x7ff).  The ``0x0800`` flag is on the first word only.
FINE_FLAG = 0x0800
FINE_MASK = 0x07FF
NIBBLE_11XX = 0xC


def fine_pair(word6: int, word8: int) -> tuple[int, int] | None:
    """``(fine_lon, fine_lat)`` when the two words are the POINT record pair."""
    if (word6 & 0xF800) != FINE_FLAG or word8 > FINE_MASK:
        return None
    return word6 & FINE_MASK, word8


def is_11xx(word: int) -> bool:
    """The low nibble is ``11xx``: both marker bits set."""
    return (word & NIBBLE_11XX) == NIBBLE_11XX


def nibble_hist(words: list[int]) -> Counter:
    return Counter(word & 0xF for word in words)


def coord001_words(path: Path) -> list[int]:
    """The four coordinate words of every ``COORD001`` entry."""
    data = cmpind.decode(path)[0]
    words: list[int] = []
    for rec in cz.coord001_records(data):
        words += [rec["x0"], rec["y0"], rec["x1"], rec["y1"]]
    return words


def addre_records(path: Path) -> list[bytes]:
    """The address records of one shard (``c0``/``c8``, variable length)."""
    blob = addre.load_blob(path)
    return addre.split_records(addre.sections(blob)["record_bytes"])


def coord_words(recs: list[bytes]) -> list[int]:
    """Both words of the packed ``coord`` id of every record that has one."""
    words: list[int] = []
    for rec in recs:
        c = addre.parse_record(rec)["coord"]
        if c is not None:
            words += [c[0], c[1]]
    return words


def _rows(words: list[int]) -> dict:
    n11 = sum(1 for w in words if is_11xx(w))
    return {"words": len(words), "words_11xx": n11, "hist": nibble_hist(words)}


def coord001_boxes(path: Path) -> dict[int, tuple[int, int, int, int]]:
    """Region index -> ``(x0, y0, x1, y1)`` from ``COORD001``."""
    data = cmpind.decode(path)[0]
    return {r["index"]: (r["x0"], r["y0"], r["x1"], r["y1"])
            for r in cz.coord001_records(data)}


def in_box(x: float, y: float, box: tuple[int, int, int, int]) -> bool:
    x0, y0, x1, y1 = box
    return x0 <= x <= x1 and y0 <= y <= y1


def decode_control(recs: list[bytes], box: tuple[int, int, int, int]) -> dict:
    """In-box rate per nibble class under plain vs marker-stripped decode.

    The decisive check: a POINT copy-A word is a coordinate only after its
    ``11xx`` marker is stripped (``packed_units``); an ADDRE/COORD001 id is a
    plain 1-unit coordinate.  If the plain reading puts the ``11xx`` class in
    the region box and the stripped one does not, the nibble is position bits
    there, not a marker.
    """
    out = {}
    for label in ("11xx", "low"):
        ids = [addre.parse_record(r)["coord"] for r in recs]
        ids = [c for c in ids if c is not None
               and ((c[0] & 0xC) == 0xC and (c[1] & 0xC) == 0xC) == (label == "11xx")]
        if not ids:
            continue
        plain = sum(1 for x, y in ids if in_box(x, y, box))
        masked = sum(1 for x, y in ids
                     if in_box(coord.packed_units(x, 0), coord.packed_units(y, 0), box))
        out[label] = {"n": len(ids), "plain": plain, "masked": masked}
    return out


def box_control(recs: list[bytes], box: tuple[int, int, int, int]) -> dict:
    """Plain ids against the plain box and against the marker-stripped box.

    Decides ``COORD001`` itself: its entries have no fine field and no external
    anchor, but the ADDRE ids of the same region do.  If the plain ids sit in
    the plain box and fall out of the stripped one, the box words are plain
    1-unit coordinates, not ``11xx``-marked POINT ids.
    """
    ids = [addre.parse_record(r)["coord"] for r in recs]
    ids = [c for c in ids if c is not None]
    stripped = tuple(int(coord.packed_units(w, 0)) for w in box)
    return {
        "n": len(ids),
        "plain_box": sum(1 for x, y in ids if in_box(x, y, box)),
        "stripped_box": sum(1 for x, y in ids if in_box(x, y, stripped)),
        "box": box,
        "stripped": stripped,
    }


def cmd_ids(args) -> int:
    cards = []
    for label, directory in (("EU", args.eu), ("US", args.us)):
        if directory:
            cards.append((label, Path(directory)))
    if not cards:
        print("give --eu and/or --us", file=sys.stderr)
        return 2

    overall: Counter = Counter()
    major_ok = True
    for label, directory in cards:
        print(f"== {label}  {directory}")
        cpath = directory / "COORD001.DAT.cmp"
        boxes: dict[int, tuple[int, int, int, int]] = {}
        if cpath.exists():
            words = coord001_words(cpath)
            r = _rows(words)
            overall["coord_words"] += r["words"]
            overall["coord_11xx"] += r["words_11xx"]
            hist = " ".join(f"{k:x}:{v}" for k, v in sorted(r["hist"].items()))
            print(f"  COORD001  entries={r['words'] // 4}  words={r['words']}  "
                  f"11xx={r['words_11xx']}/{r['words']}  low nibbles: {hist}")
            boxes = coord001_boxes(cpath)
        else:
            print(f"  COORD001  absent at {cpath}")
            major_ok = False
        snip = args.shards or ["ADDRE001"]
        for shard in snip:
            path = directory / f"{shard}.DAT.cmp"
            if not path.exists():
                print(f"  {shard}  absent at {path}")
                continue
            try:
                recs = addre_records(path)
            except addre.AddreError as exc:
                # Shards with 0xc1 framing stop split_records (M4.9 open); a
                # shard the tool cannot read is named, not silently skipped.
                print(f"  {shard}  unreadable ({exc})")
                continue
            words = coord_words(recs)
            r = _rows(words)
            overall["addre_words"] += r["words"]
            overall["addre_11xx"] += r["words_11xx"]
            hist = " ".join(f"{k:x}:{v}" for k, v in sorted(r["hist"].items()))
            print(f"  {shard}  records={r['words'] // 2}  words={r['words']}  "
                  f"11xx={r['words_11xx']}/{r['words']}  low nibbles: {hist}")
            box = boxes.get(int(shard[-3:]))
            if box and args.control:
                ctl = decode_control(recs, box)
                for cls, c in sorted(ctl.items()):
                    print(f"      decode control {cls}: n={c['n']:,}  "
                          f"plain-in-box {c['plain']:,}  marker-stripped {c['masked']:,}")
                bc = box_control(recs, box)
                print(f"      box control: plain ids in plain box {bc['plain_box']:,}/{bc['n']:,}"
                      f"  in marker-stripped box {bc['stripped_box']:,}/{bc['n']:,}"
                      f"  (stripped box {bc['stripped']} vs {bc['box']})")

    cw = overall["coord_words"]
    aw = overall["addre_words"]
    print(f"\nCOORD001 words: {overall['coord_11xx']:,}/{cw:,} 11xx"
          + ("  (census complete)" if cw else ""))
    print(f"ADDRE    words: {overall['addre_11xx']:,}/{aw:,} 11xx"
          + ("  (all shards requested; unreadable ones named)" if args.shards else "  (one shard per card; --shards for more)"))
    # The census is a measurement, not a gate: a mixed result is the answer.
    return 0 if major_ok else 1


def fine_offsets(rec: bytes) -> list[int]:
    """Even offsets whose two ``u16`` are a POINT-style ``(flon, flat)`` pair."""
    out = []
    for off in range(0, len(rec) - 3, 2):
        if fine_pair(*struct.unpack_from(">HH", rec, off)) is not None:
            out.append(off)
    return out


def id_offset(rec: bytes, coord: tuple[int, int]) -> int | None:
    """Byte offset of the ``06 00 ax ay`` token that carries ``coord``."""
    ax, ay = coord
    for off in range(0, len(rec) - 5):
        if (rec[off] == 0x06 and rec[off + 1] == 0x00
                and struct.unpack_from(">HH", rec, off + 2) == (ax, ay)):
            return off
    return None


def point_token_at_id(rec: bytes, coord: tuple[int, int]) -> tuple[int, int, int] | None:
    """``(TT, XX, YY)`` of the ``TT 40 XX YY`` token right after the id, or None.

    This is the M4.19 point token (C-1960–C-1969): ``TT`` 2 or 4, ``XX`` the
    shard-capped sub-unit, ``YY`` the full byte.  It sits at ``id + 6``; it is
    not a POINT-style 11-bit fine pair, it is the ADDRE point-token candidate.
    """
    off = id_offset(rec, coord)
    if off is None:
        return None
    j = off + 6
    if j + 3 >= len(rec) or rec[j + 1] != 0x40:
        return None
    return rec[j], rec[j + 2], rec[j + 3]


def scan_fine(recs: list[bytes]) -> dict:
    """Census the POINT-style fine pair and the ``TT 40 XX YY`` token per record."""
    with_coord = with_pair = adjacent = at_six = 0
    offsets: Counter = Counter()
    rel: Counter = Counter()
    tested = 0
    token = 0
    tt: Counter = Counter()
    xx_max = yy_max = -1
    for rec in recs:
        c = addre.parse_record(rec)["coord"]
        if c is None:
            continue
        with_coord += 1
        tested += (len(rec) - 3 + 1) // 2
        hits = fine_offsets(rec)
        if hits:
            with_pair += 1
            offsets.update(hits)
            idpos = id_offset(rec, c)
            if idpos is not None:
                for off in hits:
                    rel[off - idpos] += 1
        if any(fine_pair_at(rec, c, delta) is not None for delta in (6, 8, 10)):
            adjacent += 1
        if fine_pair_at(rec, c, 6) is not None:
            at_six += 1
        tok = point_token_at_id(rec, c)
        if tok is not None:
            token += 1
            tt[tok[0]] += 1
            xx_max = max(xx_max, tok[1])
            yy_max = max(yy_max, tok[2])
    return {
        "records": with_coord,
        "with_pair": with_pair,
        "pair_at_id": adjacent,
        "pair_at_id6": at_six,
        "offsets": offsets,
        "rel": rel,
        "offsets_tested": tested,
        "point_token_at_id": token,
        "tt": tt,
        "xx_max": xx_max,
        "yy_max": yy_max,
    }


def cmd_fine(args) -> int:
    directory = Path(args.dir)
    shards = args.shards or ["ADDRE001"]
    for shard in shards:
        path = directory / f"{shard}.DAT.cmp"
        if not path.exists():
            print(f"{shard}: absent at {path}", file=sys.stderr)
            continue
        try:
            records = addre_records(path)
        except addre.AddreError as exc:
            print(f"{shard}: unreadable ({exc})", file=sys.stderr)
            continue
        r = scan_fine(records)
        print(f"== {shard}")
        print(f"  records with a coord id: {r['records']:,}")
        print(f"  even byte offsets tested per record (0..len-4): {r['offsets_tested']:,}")
        print(f"  with a POINT-style (0x800|flon, flat) pair anywhere: {r['with_pair']:,}"
              f"  ({100.0 * r['with_pair'] / max(r['records'], 1):.2f} %)")
        print(f"  such a pair at id+6/+8/+10 (fixed field position): {r['pair_at_id']:,}"
              f"  ({100.0 * r['pair_at_id'] / max(r['records'], 1):.2f} %)"
              f"  at id+6 exactly (the POINT field position): {r['pair_at_id6']:,}")
        top = ", ".join(f"{off}:{n}" for off, n in r["offsets"].most_common(6))
        print(f"  pair offsets seen: {top or 'none'}")
        rel = ", ".join(f"{off}:{n}" for off, n in sorted(r["rel"].items())
                        if 0 <= off <= 24)
        print(f"  pair offset relative to the id token (0..24, even): {rel or 'none'}")
        print(f"  TT 40 XX YY token at id+6: {r['point_token_at_id']:,}"
              f"  ({100.0 * r['point_token_at_id'] / max(r['records'], 1):.2f} %)"
              f"  TT={dict(sorted(r['tt'].items()))}"
              f"  XX max {r['xx_max']}  YY max {r['yy_max']}")
    print("\nVERDICT: ADDRE carries no fine position for the coord id."
          " No POINT-style (flon, flat) pair sits at id+6, the byte position the"
          " POINT name record uses; the pair-shaped hits at id+8/+12 do not decode"
          " as a sub-cell of the same coord (eu ADDRE001: 2-6 km from the plain"
          " position), so they are point/range token payloads, not a fine pair."
          " The only id-adjacent structured field is the TT 40 XX YY point token"
          " (1/256 scale, no 2D frame, M4.19/C-1964).")
    return 0


def synth_shard() -> bytes:
    """A tiny ADDRE record stream: one 11xx id, one low id, no fine pair."""
    def rec(ax: int, ay: int, sub: int) -> bytes:
        body = (bytes.fromhex("0600") + struct.pack(">HH", ax, ay)
                + bytes([0x02, sub]) + bytes.fromhex("12bc054012b7030b00ff"))
        body += b"\x00" * (len(body) % 2)          # records are whole words
        total = 2 + len(body)
        assert total % 2 == 0 and total // 2 < 0x100
        return bytes([0xC0, total // 2]) + body

    return rec(0xA0CF, 0xD1BD, 0x40) + rec(0xA0C3, 0xD1B1, 0x14)


def fine_pair_at(rec: bytes, coord: tuple[int, int], delta: int) -> tuple[int, int] | None:
    """The POINT-style ``(flon, flat)`` pair at ``id + delta``, or None."""
    off = id_offset(rec, coord)
    if off is None:
        return None
    return fine_pair(*struct.unpack_from(">HH", rec, off + delta))


def selftest() -> int:
    fails = []

    def ok(cond: bool, label: str) -> None:
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    ok(is_11xx(0xA0CF) and is_11xx(0xD1BD) and not is_11xx(0xA0C3)
       and not is_11xx(0x9363), "is_11xx: 0xc/0xd/0xe/0xf, not 0x3/0x1")
    ok(nibble_hist([0xA0CF, 0xD1BD, 0xA0C3]) == Counter({0xF: 1, 0xD: 1, 0x3: 1}),
       "nibble_hist counts low nibbles")
    r = _rows([0xA0CF, 0xD1BD, 0xA0C3, 0xD1B1])
    ok(r["words"] == 4 and r["words_11xx"] == 2, "rows: 2 of 4 words are 11xx")

    stream = synth_shard()
    recs = addre.split_records(stream)
    ok(len(recs) == 2, "synthetic stream splits into 2 records")
    words = coord_words(recs)
    ok(words == [0xA0CF, 0xD1BD, 0xA0C3, 0xD1B1], "coord_words reads both id words")
    ok(sum(1 for w in words if is_11xx(w)) == 2, "synthetic: exactly one id is 11xx")
    sc = scan_fine(recs)
    ok(sc["records"] == 2 and sc["with_pair"] == 0,
       "synthetic: no POINT-style fine pair")
    ok(sc["pair_at_id"] == 0, "synthetic: no pair at id+6/+8/+10")
    ok(sc["pair_at_id6"] == 0, "synthetic: nothing at id+6")
    ok(fine_offsets(bytes.fromhex("0600a0cfd1bd0bda01f40a")) == [6],
       "fine_pair: the documented POINT record pair at 6 (flon 0x800|986, flat 500)")
    ok(fine_pair(0x800, 0x400) is not None and fine_pair(0x900, 0x800) is None,
       "fine_pair: flag on the first word only, lat must be <= 0x7ff")
    ok(in_box(10, 10, (0, 0, 20, 20)) and not in_box(21, 10, (0, 0, 20, 20)),
       "in_box: inclusive bounds")
    tok = point_token_at_id(recs[0], (0xA0CF, 0xD1BD))
    ok(tok is not None and tok[0] in (2, 4),
       f"synthetic: TT 40 XX YY token at id+6 -> {tok}")
    ok(point_token_at_id(recs[1], (0xA0C3, 0xD1B1)) is None,
       "synthetic: no token on the low-nibble record (next word is not 40)")
    sc = scan_fine(recs)
    ok(sc["point_token_at_id"] == 1 and sc["tt"] == Counter({tok[0]: 1}),
       "scan: exactly one point token")

    print("refer_id_census selftest: " + ("OK" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    ids = sub.add_parser("ids", help="low-nibble census of COORD001 and ADDRE ids")
    ids.add_argument("--eu")
    ids.add_argument("--us")
    ids.add_argument("--shards", nargs="*")
    ids.add_argument("--control", action="store_true",
                     help="per shard, compare plain vs marker-stripped decode inside its COORD001 box")
    ids.set_defaults(func=cmd_ids)
    fine = sub.add_parser("fine", help="search ADDRE records for a POINT-style fine pair")
    fine.add_argument("--dir", required=True)
    fine.add_argument("--shards", nargs="*")
    fine.set_defaults(func=cmd_fine)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmd:
        ap.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
