#!/usr/bin/env python3
"""Why the mount leaves a tile after its header (M3.33, EU2011, L3).

The data-access task opens the tile under the start position and reads its
first 0x1000 bytes.  The header handler `0x0040b8b4` passes them to the
check `0x0040acb8(kind, volume, buffer, box)`, which walks the *section
list* at header `0x800` (6-byte entries, `ff ff ff ff` = no entry):

    for part in 0..5:                       # bit `part` of the box's +4 mask
        entry = buffer + 2 * part_offsets[part]        # part 0/1/2 -> 0x800/0x806/0x80c
        if entry is ff ff ff ff and nothing of that part is loaded yet:
            box status (+16) = 3            # check + 0x16e
            if first mount (progress word 0):
                open the position again     # 0x0040a61c
                return -1                   # the handler stops: no section table is read

`0x0040a61c` asks `0x0040a1dc` for the box that holds the position; that
function skips a box whose status is 3 and answers -1 when no box is left,
and the caller turns -1 into box 0 (`cmp/pz; subc; and`).  So a tile whose
section list is shorter than its box mask is left after its header and the
mount goes on in the first box of the table.

This tool runs `tools/datask_l3.py`'s mount with hooks on those functions
and prints, per header check, the box, the section list and what the check
decided.  `sections` reads the same list from every tile of a card without
the firmware.

Usage:
  tile_drop_l3.py run IMG --card-image CARD --position LAT,LON
                          [--flip P@OFF:XOR ...] [--replace P=FILE ...] [--json OUT]
  tile_drop_l3.py sections --card-image CARD [--json OUT]
  tile_drop_l3.py third-entry --card-image CARD TILE       # --flip arguments that copy
                                                           # entry 1 of the list to entry 2
  tile_drop_l3.py --selftest

Exit status of `run`: 0 the tile under the position had its section tables
read, 1 it was left after the header, 3 the run is blocked.

Stdlib only; needs `archive/head256.img` (EU2011 build A) and a card image.
All VAs are EU2011 build A `Navi.exe`.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

EU2011 = {
    "check": 0x0040ACB8,          # (part kind, volume, buffer, box) -> 0 / -1
    "absent": 0x0040ACB8 + 0x16E,     # in the check: the branch, box status 3
    "check_ret": 0x0040ACB8 + 0x1A8,  # in the check: r2 = its result
    "find_box": 0x0040A1DC,       # (.., mask, position) -> box index or -1
    "reopen": 0x0040A61C,         # (position, kind): open the tile files of a position
    "find_ret_tile": 0x0040A61C + 0xB4,   # in reopen: r0 = find_box's answer for the tile
    "boxes": 0x00D624A0,          # 24 B per box
    "box_count": 0x00D63CA0,
    "progress": 0x00D98FCC,
    "part_offsets": (0x179 << 12) + 0xDD0,   # data VA, 6 * u32: header offset / 2 of each part's entry
}
SECT_OFF = 0x800
ENTRY = 6
STATUS = {1: "mounted", 3: "left (a part is missing)", 5: "header read pending", 6: "not opened"}


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------

def parse_section_list(raw: bytes, limit: int = 6) -> list[dict]:
    """Entries of the list at header 0x800 as stored on the card:
    `{u24 sector, u8 offset, u16 length}` big-endian; the list ends at the
    first `ff ff ff ff`."""
    out = []
    for i in range(limit):
        e = raw[ENTRY * i:ENTRY * i + ENTRY]
        if len(e) < ENTRY or e[:4] == b"\xff\xff\xff\xff":
            break
        sector = int.from_bytes(e[0:3], "big")
        out.append({"index": i, "pos": sector * 0x800 + e[3] * 0x100,
                    "length": struct.unpack(">H", e[4:6])[0] * 0x100})
    return out


def box_fields(raw: bytes) -> dict:
    """One 24-byte box of the table at 0xd624a0 (little-endian in memory)."""
    num, _a, mask, levels, y0, x0, y1, x1, status, flag = struct.unpack_from("<HHHHhhhhHH", raw)
    return {"number": num, "mask": mask, "levels": levels, "y0": y0, "x0": x0, "y1": y1, "x1": x1,
            "status": status, "flag": flag}


def box_name(box: dict) -> str:
    """File name of a box: `BxxRyyyR.DAT` from y0 and -x0 in hex; the box
    with level bits 0x3c is `LEV3456R.DAT`."""
    if box["levels"] & 0x3C:
        return "LEV3456R.DAT"
    return "B%02XR%03XR.DAT" % (box["y0"] & 0xFF, (-box["x0"]) & 0xFFF)


def missing_parts(n_entries: int, mask: int, levels: int) -> list[int]:
    """Parts the box mask asks for that the section list does not hold.  Part
    2 exists only for the two tile levels (level bits 0x03): the firmware's
    row table (3-byte rows after the part offsets, see the EXP) has no row
    for part 2 with bits 0x3c."""
    out = []
    for part in range(3):
        if not mask & (1 << part):
            continue
        if part == 2 and not levels & 0x03:
            continue
        if part >= n_entries:
            out.append(part)
    return out


def copy_entry_flips(raw: bytes, src: int = 1, dst: int = 2) -> list[tuple[int, int]]:
    """(file offset, xor) pairs that make entry `dst` of the list equal to
    entry `src` (a test change: the list then has one more entry)."""
    a = raw[ENTRY * src:ENTRY * src + ENTRY]
    b = raw[ENTRY * dst:ENTRY * dst + ENTRY]
    return [(SECT_OFF + ENTRY * dst + i, a[i] ^ b[i]) for i in range(ENTRY) if a[i] ^ b[i]]


def verdict(events: list[dict], tables: dict, wanted: str) -> tuple[str, int]:
    """One line and the exit status for the tile under the position."""
    hit = [e for e in events if e["file"] == wanted]
    if tables.get(wanted):
        return "%s: mounted, %d section table(s) read" % (wanted, tables[wanted]), 0
    if any(e["absent_part"] is not None for e in hit):
        e = [e for e in hit if e["absent_part"] is not None][0]
        return ("%s: left after its header: part %d has no entry in the section list "
                "(branch at check + 0x16e); next box asked for the position: %s" % (
                    wanted, e["absent_part"],
                    "none (-1), taken as box 0" if e["reopened_box"] == -1 else e["reopened_box"])), 1
    return "%s: no section table read and no missing part seen" % wanted, 1


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

def run_mount(image: str, card, position, build: dict = EU2011) -> dict:
    import datask_l3 as D
    t = D.DataTask(image, card, position=position)
    m = t.m
    events: list[dict] = []
    cur: list[dict] = []

    def read_box(index: int) -> dict:
        return box_fields(bytes(m.eng.read_mem(build["boxes"] + 24 * index, 24)))

    def on_check(_e, _va):
        buf, bx = m.arg(2), m.arg(3)
        index = (bx - build["boxes"]) // 24
        box = read_box(index)
        raw = bytes(m.eng.read_mem(buf + SECT_OFF, 18))
        # the firmware has swapped every u16 of the header: swap back to file order
        raw = b"".join(raw[i + 1:i + 2] + raw[i:i + 1] for i in range(0, len(raw), 2))
        ev = {"box": index, "file": box_name(box), "mask": box["mask"], "levels": box["levels"],
              "progress": m.u32(build["progress"]), "sections": parse_section_list(raw, 3),
              "absent_part": None, "reopened_box": None, "result": None}
        events.append(ev)
        cur[:] = [ev]
        return None

    def on_absent(_e, _va):
        if cur:
            cur[0]["absent_part"] = m.reg("r10")
        return None

    def on_find_ret(_e, _va):
        if cur and cur[0]["absent_part"] is not None and cur[0]["reopened_box"] is None:
            v = m.reg("r0")
            cur[0]["reopened_box"] = -1 if v == 0xFFFFFFFF else v
        return None

    def on_check_ret(_e, _va):
        if cur:
            v = m.reg("r2")
            cur[0]["result"] = -1 if v == 0xFFFFFFFF else v
            cur[:] = []
        return None

    m.eng.on_exec(build["check"], on_check)
    m.eng.on_exec(build["absent"], on_absent)
    m.eng.on_exec(build["find_ret_tile"], on_find_ret)
    m.eng.on_exec(build["check_ret"], on_check_ret)
    rows: list[dict] = []
    end = t.run(0, False, rows.append, [])
    tables: dict[str, int] = {}
    for r in rows:
        if (r["tag"] >> 8) == 6:
            name = r["file"].split("/")[-1].upper()
            tables[name] = tables.get(name, 0) + 1
    n = m.u32(build["box_count"])
    boxes = [dict(read_box(i), index=i) for i in range(min(n, 64))]
    for b in boxes:
        b["file"] = box_name(b)
    return {"end": end, "events": events, "section_tables": tables, "boxes": boxes,
            "reads": [{"tag": r["tag"], "file": r["file"], "pos": r["pos"], "length": r["length"]}
                      for r in rows]}


def wanted_tile(out: dict) -> str | None:
    """The first tile (not LEV3456R) whose header the check saw."""
    for e in out["events"]:
        if e["file"] != "LEV3456R.DAT":
            return e["file"]
    return None


def cmd_run(args) -> int:
    import vcard_l3 as V
    card = V.make_card(None, args.card_image, V.parse_mods(args))
    lat, _, lon = args.position.partition(",")
    try:
        out = run_mount(args.image, card, (float(lat), float(lon)))
    except (V.Blocked, V.EngineError) as exc:
        print("BLOCKED: %s: %s" % (type(exc).__name__, str(exc)[:300]))
        return 3
    for e in out["events"]:
        secs = ", ".join("%#x/%#x" % (s["pos"], s["length"]) for s in e["sections"]) or "-"
        what = "ok"
        if e["absent_part"] is not None:
            what = "part %d missing -> status 3" % e["absent_part"]
            if e["reopened_box"] is not None:
                what += "; position asked again -> box %s" % (
                    "-1 (taken as 0)" if e["reopened_box"] == -1 else e["reopened_box"])
        print("header check: box %2d %-13s mask %#x levels %#04x progress %d  list [%s]  %s  (returns %s)" % (
            e["box"], e["file"], e["mask"], e["levels"], e["progress"], secs, what, e["result"]))
    for name, n in out["section_tables"].items():
        print("section tables read: %-13s %d" % (name, n))
    by = {}
    for b in out["boxes"]:
        by.setdefault(b["status"], []).append(b["file"])
    for st, names in sorted(by.items()):
        print("box status %d (%s): %d%s" % (st, STATUS.get(st, "?"), len(names),
                                           "  " + ", ".join(names) if len(names) <= 4 else ""))
    want = wanted_tile(out)
    line, rc = verdict(out["events"], out["section_tables"], want) if want else ("no tile header was checked", 1)
    print("end: %s" % out["end"])
    print(line)
    if args.json:
        out["wanted"] = want
        out["verdict"] = line
        Path(args.json).write_text(json.dumps(out, indent=1) + "\n")
    return rc


def card_tiles(card) -> list[tuple[str, bytes]]:
    import vcard_l3 as V
    ex = V.Expected(card)
    out = []
    for name in sorted(card._list("mapal001")):
        up = name.upper()
        if up.endswith(".DAT") and (up.startswith("B") or up.startswith("LEV")):
            raw = ex.read("MAPAL001/" + up, SECT_OFF, 18)
            if raw:
                out.append((up, raw))
    return out


def cmd_sections(args) -> int:
    import vcard_l3 as V
    card = V.make_card(None, args.card_image, {})
    rows = []
    for name, raw in card_tiles(card):
        secs = parse_section_list(raw, 3)
        rows.append({"file": name, "entries": len(secs), "sections": secs})
        print("%-13s %d  %s" % (name, len(secs), ", ".join("%#x/%#x" % (s["pos"], s["length"]) for s in secs)))
    counts = {}
    for r in rows:
        if r["file"].startswith("B"):
            counts[r["entries"]] = counts.get(r["entries"], 0) + 1
    print("BxxRyyyR tiles: %d; by number of entries: %s" % (
        sum(counts.values()), ", ".join("%d entries: %d" % kv for kv in sorted(counts.items()))))
    short = [r["file"] for r in rows if r["file"].startswith("B") and r["entries"] < 3]
    print("tiles with fewer than 3 entries: %s" % (", ".join(short) or "none"))
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1) + "\n")
    return 0


def cmd_third(args) -> int:
    import vcard_l3 as V
    card = V.make_card(None, args.card_image, {})
    path = "MAPAL001/" + args.tile.upper()
    raw = V.Expected(card).read(path, SECT_OFF, 18)
    if not raw:
        print("no such tile: %s" % path)
        return 2
    print(" ".join("--flip %s@%#x:%#x" % (path, off, x) for off, x in copy_entry_flips(raw)))
    return 0


# --------------------------------------------------------------------------
def selftest() -> int:
    failed = 0

    def check(name, cond):
        nonlocal failed
        print("  %-58s %s" % (name, "ok" if cond else "FAIL"))
        failed += 0 if cond else 1

    two = bytes.fromhex("000002000001" "0001d9000001" "ffffffff0000")
    three = bytes.fromhex("000002000004" "015d8b070004" "022519030004")
    check("a two-entry list decodes to its positions",
          [(s["pos"], s["length"]) for s in parse_section_list(two)] == [(0x1000, 0x100), (0xEC800, 0x100)])
    check("a three-entry list decodes (offset byte counts 0x100)",
          [s["pos"] for s in parse_section_list(three)] == [0x1000, 0xAEC5F00, 0x1128CB00])
    check("an empty list has no entry", parse_section_list(b"\xff" * 18) == [])
    box = box_fields(struct.pack("<HHHHhhhhHHI", 0x27, 3, 7, 3, 0x60, -0x48, 0x68, -0x40, 3, 1, 0))
    check("a box decodes: status and mask", box["status"] == 3 and box["mask"] == 7 and box["x0"] == -0x48)
    check("a box names its tile", box_name(box) == "B60R048R.DAT")
    lev = box_fields(struct.pack("<HHHHhhhhHHI", 0x2E, 3, 7, 0x3C, 0x64, 0x64, 0x65, 0x65, 1, 0, 0))
    check("the level-3..6 box is LEV3456R", box_name(lev) == "LEV3456R.DAT")
    check("mask 7 with two entries misses part 2 on a tile", missing_parts(2, 7, 3) == [2])
    check("mask 7 with three entries misses nothing", missing_parts(3, 7, 3) == [])
    check("LEV3456R needs no part 2", missing_parts(2, 7, 0x3C) == [])
    check("a mask without bit 2 needs no part 2", missing_parts(2, 3, 3) == [])
    flips = copy_entry_flips(two)
    patched = bytearray(two)
    for off, x in flips:
        patched[off - SECT_OFF] ^= x
    check("the flips copy entry 1 to entry 2", bytes(patched[12:18]) == two[6:12] and len(flips) == 5)
    ev = [{"file": "B60R048R.DAT", "absent_part": 2, "reopened_box": -1}]
    check("verdict: left after the header", verdict(ev, {"B28R070R.DAT": 2}, "B60R048R.DAT")[1] == 1)
    check("verdict: mounted when its section tables are read",
          verdict(ev, {"B60R048R.DAT": 3}, "B60R048R.DAT")[1] == 0)
    check("verdict names the missing part", "part 2" in verdict(ev, {}, "B60R048R.DAT")[0])
    print("tile_drop_l3 selftest: %d failed" % failed)
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("run")
    p.add_argument("image")
    p.add_argument("--card-image", required=True)
    p.add_argument("--position", required=True, metavar="LAT,LON")
    for opt in ("--hide", "--replace", "--flip", "--truncate"):
        p.add_argument(opt, action="append", default=[])
    p.add_argument("--json")
    p = sub.add_parser("sections")
    p.add_argument("--card-image", required=True)
    p.add_argument("--json")
    p = sub.add_parser("third-entry")
    p.add_argument("--card-image", required=True)
    p.add_argument("tile")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "sections":
        return cmd_sections(args)
    if args.cmd == "third-entry":
        return cmd_third(args)
    ap.error("a command or --selftest is required")
    return 2


if __name__ == "__main__":
    sys.exit(main())
