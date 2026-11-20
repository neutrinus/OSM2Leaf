#!/usr/bin/env python3
"""The 0x1000-byte header of a ZE0 (X08-02-00) map tile, written from its parts.

``tools/ze0-viewer/tools_ze0/tile_header.py`` authors the X08-03-00 header of
the 2014-2016 cards (``ZENRIN``/``CLA-NAVI06-01``, ``V06.00.00``).  A ZE0 card
(EU/US 2011, ``HITACHI``/``CLA-NAVI05-01``, ``FORMAT VERSION X08-02-00``,
``V05.00.00``) needs the X08-02-00 layout, and ``cardcheck.py`` rejects the
X08-03-00 identity on such a card (M5.33).  The two layouts differ in:

* the identity strings at 0x40/0x80/0xa0/0x162;
* fills: X08-02-00 zero-fills the level and box tables to 0x3ae and
  0x4ac..0x800 (keeping 0x5cc, the second bounds at 0x5d0 and 0x5d4), has no
  constants at 0x3ac/0x4ed, and fills *every* section-table slot with ``ffffffff 0000``
  (the last two bytes before 0x1000 are zero);
* section 2 level types (``0x91 0x91 0x91 0x90`` instead of ``0x81 ...``).

``check()`` rebuilds a header from its variable fields alone (level table, box
table, database bounds, DATA VERSION, section-table entries) and lists the
offsets that differ, so the layout is tested against every tile of a card:

    python3 tools/ze0_tile_header.py --check ROOT/MAPAL001/*.DAT
    python3 tools/ze0_tile_header.py --selftest

``convert()`` re-authors the header of a container written with the
X08-03-00 header (``tilewriter.py`` synthetic mode, ``tilewriter.make_factory``)
as X08-02-00; the body (section tables, directories, blocks) is unchanged.
No vendor bytes are embedded here: the constants are format fields.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

HEADER_SIZE = 0x1000
IDENT = {0x00: "CLARION", 0x40: "HITACHI", 0x80: "CLA-NAVI05-01",
         0xA0: "FORMAT VERSION X08-02-00", 0x162: "V05.00.00"}
CONSTS = {0x160: "1600", 0x182: "24", 0x18C: "3f" * 20, 0x5CC: "80000000",
          0x5D4: "0b0b"}
ZERO = ((0x1AC, 0x3AE), (0x4AC, 0x800))
DATA_VERSION, BOUNDS, BOUNDS2 = 0xE0, 0x184, 0x5D0
LEVEL_OFF, BOX_OFF, BOX_END, SECT_OFF = 0x1AC, 0x2AC, 0x3AE, 0x800
EMPTY_SLOT = struct.pack(">IH", 0xFFFFFFFF, 0)

# section id -> its (level, type) rows, in factory order (EU2011, 46/46 tiles
# carry the same rows; LEV3456R lists sections 1 and 2 only)
LEVELS = {1: [(6, 0x80), (5, 0x90), (4, 0x91), (3, 0x91), (2, 0x91), (1, 0x92)],
          2: [(5, 0x91), (4, 0x91), (2, 0x91), (1, 0x90)],
          4: [(1, 0x93)]}


def author(level_groups, box_rows, db_bounds, data_version, sections=()):
    """level_groups: [(section id, [(level, type, count), ...]), ...]
    box_rows:     [(section id, [(level, flag, (y1, y0, x0, x1)), ...]), ...]
    db_bounds:    (lat max, lat min, lon min, lon max) in arc-minutes
    data_version: 'yy/mm/dd/nn'
    sections:     [(tag, count), ...] section-table entries (write_tile's)"""
    h = bytearray(b"\xff" * HEADER_SIZE)
    for a, b in ZERO:
        h[a:b] = bytes(b - a)
    for off, text in IDENT.items():
        raw = text.encode("utf-16-be")
        h[off:off + len(raw)] = raw
    for off, hexs in CONSTS.items():
        raw = bytes.fromhex(hexs)
        h[off:off + len(raw)] = raw
    raw = ("DATA VERSION " + data_version).encode("utf-16-be")
    if len(raw) != 48:
        raise ValueError(f"data version must be yy/mm/dd/nn, got {data_version!r}")
    h[DATA_VERSION:DATA_VERSION + 48] = raw
    struct.pack_into(">4h", h, BOUNDS, *db_bounds)
    struct.pack_into(">2h", h, BOUNDS2, db_bounds[1], db_bounds[2])

    p = LEVEL_OFF
    struct.pack_into(">H", h, p, len(level_groups)); p += 2
    for sid, rows in level_groups:
        h[p], h[p + 1] = sid, len(rows); p += 2
        for lvl, typ, cnt in rows:
            struct.pack_into(">BBH", h, p, lvl, typ, cnt); p += 4
    if p > BOX_OFF:
        raise ValueError("level table runs into the box table")

    p = BOX_OFF
    struct.pack_into(">H", h, p, len(box_rows)); p += 2
    for sid, rows in box_rows:
        h[p], h[p + 1] = sid, len(rows); p += 2
        for lvl, flag, box in rows:
            struct.pack_into(">BB4h", h, p, lvl, flag, *box); p += 10
    if p > BOX_END:
        raise ValueError("box table runs past 0x3ae")

    p = SECT_OFF
    while p + 6 <= HEADER_SIZE:
        h[p:p + 6] = EMPTY_SLOT
        p += 6
    h[p:HEADER_SIZE] = bytes(HEADER_SIZE - p)
    for i, (tag, count) in enumerate(sections):
        struct.pack_into(">IH", h, SECT_OFF + 6 * i, tag, count)
    return h


def _walk(h, off, elen):
    n = struct.unpack_from(">H", h, off)[0]
    p = off + 2
    out = []
    for _ in range(n):
        sid, cnt = h[p], h[p + 1]
        p += 2
        out.append((sid, [bytes(h[p + i * elen:p + (i + 1) * elen]) for i in range(cnt)]))
        p += cnt * elen
    return out


def fields(h) -> dict:
    """The variable fields of a header, as author() takes them."""
    lv = [(sid, [(e[0], e[1], struct.unpack(">H", e[2:])[0]) for e in rows])
          for sid, rows in _walk(h, LEVEL_OFF, 4)]
    bx = [(sid, [(e[0], e[1], struct.unpack(">4h", e[2:])) for e in rows])
          for sid, rows in _walk(h, BOX_OFF, 10)]
    dv = bytes(h[DATA_VERSION:DATA_VERSION + 48]).decode("utf-16-be")
    if not dv.startswith("DATA VERSION "):
        raise ValueError(f"no DATA VERSION at 0xe0: {dv!r}")
    sect, p = [], SECT_OFF
    while p + 6 <= HEADER_SIZE:
        tag, count = struct.unpack_from(">IH", h, p)
        if tag == 0xFFFFFFFF:
            break
        sect.append((tag, count))
        p += 6
    return dict(level_groups=lv, box_rows=bx,
                db_bounds=struct.unpack_from(">4h", h, BOUNDS),
                data_version=dv[13:], sections=sect)


def check(h) -> list[int]:
    """Rebuild a header from its fields; return the offsets that differ."""
    b = author(**fields(h))
    return [i for i in range(HEADER_SIZE) if b[i] != h[i]]


def ze0_levels(level_groups):
    """Map X08-03-00 (section, level) rows onto the ZE0 types, keeping counts."""
    out = []
    for sid, rows in level_groups:
        types = dict(LEVELS[sid])
        out.append((sid, [(lvl, types.get(lvl, typ), cnt) for lvl, typ, cnt in rows]))
    return out


def box_rows_for(level_groups, box):
    """One box row (flag 0, ``box``) per level that has directories, in table
    order: the shape of every EU2011 tile header (each row is the cell box)."""
    out = []
    for sid, rows in level_groups:
        have = [(lvl, 0, tuple(box)) for lvl, _typ, cnt in rows if cnt]
        if have:
            out.append((sid, have))
    return out


def convert(blob: bytes, *, db_bounds=None, box=None, data_version=None) -> bytes:
    """Re-author the header of a container as X08-02-00; the body is unchanged.

    The level counts, section-table entries and DATA VERSION come from the old
    header.  ``db_bounds`` defaults to the old header's; ``box`` (the cell box)
    gives one box row per level with directories, else the old box table is
    kept."""
    if len(blob) < HEADER_SIZE:
        raise ValueError(f"container shorter than its 0x1000-byte header ({len(blob)} B)")
    old = fields(blob)
    levels = ze0_levels(old["level_groups"])
    boxes = box_rows_for(levels, box) if box is not None else old["box_rows"]
    head = author(levels, boxes, db_bounds or old["db_bounds"],
                  data_version or old["data_version"], old["sections"])
    return bytes(head) + blob[HEADER_SIZE:]


# ---------------------------------------------------------------------------
# self-test (no vendor data)


def selftest() -> int:
    failures = 0

    def ok(cond, msg):
        nonlocal failures
        print(("  ok   " if cond else "  FAIL ") + msg)
        failures += 0 if cond else 1

    print("ze0_tile_header selftest (synthetic, no vendor data)")
    groups = [(1, [(lvl, typ, 4 if lvl == 2 else 64 if lvl == 1 else 0) for lvl, typ in LEVELS[1]]),
              (2, [(lvl, typ, 4 if lvl == 2 else 64 if lvl == 1 else 0) for lvl, typ in LEVELS[2]]),
              (4, [(1, 0x93, 64)])]
    cell = (3200, 2880, 720, 1200)
    boxes = box_rows_for(groups, cell)
    sects = [(0x10, 3), (0x20, 5), (0x30, 1)]
    h = author(groups, boxes, (4800, 1280, -1200, 4080), "11/06/27/01", sects)
    ok(len(h) == HEADER_SIZE, "header is 0x1000 bytes")
    ok(bytes(h[0x40:0x4e]).decode("utf-16-be") == "HITACHI", "0x40 HITACHI")
    ok(bytes(h[0x80:0x9a]).decode("utf-16-be") == "CLA-NAVI05-01", "0x80 CLA-NAVI05-01")
    ok(bytes(h[0xa0:0xd0]).decode("utf-16-be") == "FORMAT VERSION X08-02-00", "0xa0 X08-02-00")
    ok(check(h) == [], "check(author(fields)) round-trips")
    f = fields(h)
    ok(f["sections"] == sects and f["box_rows"] == boxes and f["level_groups"] == groups,
       "fields() returns what author() wrote")
    ok(bytes(h[0xff8:0x1000]) == EMPTY_SLOT + b"\0\0", "last full slot empty, tail zero")
    ok([len(r) for _s, r in boxes] == [2, 2, 1], "one box row per level with directories")
    bad = bytearray(h)
    bad[0x3ac] = 1  # the X08-03-00 constant at 0x3ac
    ok(check(bad) == [0x3ac], "negative control: a planted X08-03-00 byte is named")
    bad = bytearray(h)
    bad[0x40:0x4c] = "ZENRIN".encode("utf-16-be")
    ok(0x41 in check(bad), "negative control: ZENRIN identity is a difference")
    try:
        author(groups, boxes, (0, 0, 0, 0), "2011/06/27")
        ok(False, "bad data version refused")
    except ValueError:
        ok(True, "bad data version refused")

    # convert(): a tilewriter X08-03-00 container becomes X08-02-00 and still reads.
    try:
        tools = Path(__file__).resolve().parent
        for sub in (tools, tools / "ze0-viewer", tools / "ze0-viewer" / "tools_ze0"):
            if str(sub) not in sys.path:
                sys.path.insert(0, str(sub))
        import clarion_tile
        import tilewriter
    except ImportError as exc:
        ok(False, f"tilewriter/clarion_tile importable ({exc})")
    else:
        blob = tilewriter.make_factory("B48R058R")
        new = convert(blob, box=tilewriter.cell_db_bounds("B48R058R"))
        ok(new[HEADER_SIZE:] == blob[HEADER_SIZE:], "convert keeps the body")
        ok(check(new[:HEADER_SIZE]) == [], "converted header is X08-02-00 exact")
        t_old, t_new = clarion_tile.read_tile(blob), clarion_tile.read_tile(new)
        ok([len(L["dirs"]) for s in t_new["sections"] for L in s["levels"]]
           == [len(L["dirs"]) for s in t_old["sections"] for L in s["levels"]],
           "converted container reads with the same directories")
        ok(clarion_tile.write_tile(t_new) == new, "converted container rebuilds byte-identically")
        sec2 = [r for sid, rows in fields(new)["level_groups"] if sid == 2 for r in rows]
        ok([typ for _l, typ, _c in sec2] == [0x91, 0x91, 0x91, 0x90], "section 2 ZE0 types")

    print(f"ze0_tile_header selftest: {'PASS' if failures == 0 else 'FAIL'} ({failures} failure(s))")
    return 0 if failures == 0 else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", nargs="+", metavar="FILE",
                        help="rebuild each tile header from its fields and compare")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.check:
        parser.error("--check FILE... or --selftest")
    bad = 0
    for name in args.check:
        with open(name, "rb") as fh:
            h = fh.read(HEADER_SIZE)
        try:
            diff = check(h)
        except (ValueError, struct.error) as exc:
            diff = [-1]
            print(f"{name} UNPARSED ({exc})")
            bad += 1
            continue
        bad += bool(diff)
        print(name, "exact" if not diff else
              "DIFFERS at " + " ".join(f"{i:#x}" for i in diff[:12]))
    print(f"{len(args.check) - bad} of {len(args.check)} headers rebuilt exactly")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
