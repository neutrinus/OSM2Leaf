#!/usr/bin/env python3
"""Acceptance envelope of one factory tile header, field by field (M9.68, L3).

M9.13 showed that a generated tile reads the same as factory and a
fresh-container tile fails; M3.33 showed that a missing third section-list
entry drops the tile.  This tool fills in the envelope: it flips one *field*
of the `0x1000`-byte common header / level table / box table / section list
of `B48R058R.DAT` at a time, runs the whole firmware mount
(``datask_l3.py mount`` path) on the EU2011 build A harness, and prints

    field -> verdict -> rejecting/changed fn

where a verdict is ``read-same`` (every tile read and parser byte range
identical to the factory baseline), ``read-different`` (the tile is still
parsed but the read set changes) or ``rejected`` (the tile is left after its
header, the header check returns -1, or the run is blocked).  The `fn` column
names the header check for a drop and the first parser whose byte range
changed otherwise; ``-`` means nothing changed.

Every field layout is taken from code, not guessed from prose: the identity
and constant offsets, `DATA_VERSION`/`BOUNDS` and the 4/10-byte level/box
entries come from ``tools/ze0_tile_header.py`` (tested by its ``--check``
against all 46 EU2011 tiles); the 6-byte section list comes from
``tools/tile_drop_l3.py.parse_section_list``; the reader VAs come from that
tool's ``EU2011`` dict and the VERIFIED M3.25 table in
``docs/format/map-tiles.md``.  SH-4 code is little-endian; the header buffer
is byte-swapped by the firmware (``tile_drop_l3.py`` line 164).

No vendor byte is stored here: the image and card are read from the paths
given.  Standard library only.

Usage:
  tile_sweep_l3.py --selftest
  tile_sweep_l3.py sweep IMG256 --card-image CARD [--position LAT,LON]
                   [--tile B48R058R.DAT] [--only NAME,...] [--limit N]
                   [--json OUT]
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE / "l3_harness"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import tile_drop_l3 as T  # noqa: E402
import vcard_l3 as V  # noqa: E402

TILE = "B48R058R.DAT"
DEFAULT_POSITION = (51.70, 17.45)
HEADER_SIZE = 0x1000
CHECK = T.EU2011["check"]          # 0x0040acb8: the header/section-list check
MAX_MUTATIONS = 64


# ---------------------------------------------------------------------------
# Fields: one mutation per field, not per byte
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Field:
    name: str
    group: str
    flips: tuple[tuple[int, int], ...]   # (header offset, xor)
    note: str = ""


def _f(name, group, off, xor, note=""):
    return Field(name, group, ((off, xor),), note)


def fields(header: bytes) -> list[Field]:
    """The field list.  ``header`` is only used to build the one field whose
    mutation is a replacement (the third section-list entry -> terminator)."""
    out = [
        # Common header identity / constants (ze0_tile_header.IDENT/CONSTS)
        _f("id.CLARION@0x00", "header", 0x01, 0xFF, "identity, never read by this mount"),
        _f("id.HITACHI@0x40", "header", 0x41, 0xFF, "negative control: not read at L3"),
        _f("id.CLA-NAVI05-01@0x80", "header", 0x81, 0xFF, "identity"),
        _f("id.FORMAT-X08-02-00@0xa0", "header", 0xA1, 0xFF, "identity"),
        _f("ver.V05.00.00@0x162", "header", 0x163, 0xFF, "version string"),
        _f("const.0x1600@0x160", "header", 0x160, 0xFF, "u16 constant before the version"),
        _f("const.0x24@0x182", "header", 0x182, 0xFF, "byte constant before BOUNDS"),
        _f("date.year@0xfa", "header", 0xFB, 0xFF, "loaded by fn 0x0040a8d0"),
        _f("date.seq@0x10c", "header", 0x10D, 0xFF, "loaded by fn 0x0040a8d0"),
        _f("bounds.lat_max@0x184", "header", 0x185, 0x01, "i16 arc-minutes"),
        _f("bounds.lat_min@0x186", "header", 0x187, 0x01, "i16 arc-minutes"),
        _f("bounds.lon_min@0x188", "header", 0x189, 0x01, "i16 arc-minutes"),
        _f("bounds.lon_max@0x18a", "header", 0x18B, 0x01, "i16 arc-minutes"),
        _f("const.0x80000000@0x5cc", "header", 0x5CD, 0x01, "pair flag constant"),
        _f("bounds2.lat_min@0x5d0", "header", 0x5D1, 0x01, "i16 arc-minutes"),
        _f("bounds2.lon_min@0x5d2", "header", 0x5D3, 0x01, "i16 arc-minutes"),
        _f("const.0x0b0b@0x5d4", "header", 0x5D5, 0x01, "byte constant"),
        # Level table at 0x1ac: u16 n_tables, {id, n} then (lvl, kind, u16 count)
        _f("level.n_tables@0x1ac", "level", 0x1AC, 0xFF, "M3.25: no bound on this walk"),
        _f("level.s1.id@0x1ae", "level", 0x1AE, 0x01, "table id"),
        _f("level.s1.n@0x1af", "level", 0x1AF, 0x01, "entry count"),
        _f("level.s1.L6.level@0x1b0", "level", 0x1B0, 0x01, "level byte"),
        _f("level.s1.L6.kind@0x1b1", "level", 0x1B1, 0x01, "kind byte"),
        _f("level.s1.L6.count@0x1b3", "level", 0x1B3, 0x01, "count 0 -> 1"),
        _f("level.s1.L2.count@0x1c3", "level", 0x1C3, 0x01, "count 4 -> 5"),
        _f("level.s1.L1.kind@0x1c5", "level", 0x1C5, 0x01, "kind 0x92: directory read length"),
        _f("level.s1.L1.count@0x1c7", "level", 0x1C7, 0x01, "count 0x40 -> 0x41"),
        _f("level.s2.id@0x1c8", "level", 0x1C8, 0x01, "table id"),
        _f("level.s2.n@0x1c9", "level", 0x1C9, 0x01, "entry count"),
        _f("level.s2.L5.kind@0x1cb", "level", 0x1CB, 0x01, "kind byte"),
        _f("level.s2.L1.kind@0x1d7", "level", 0x1D7, 0x01, "kind 0x90: directory read length"),
        _f("level.s4.id@0x1da", "level", 0x1DA, 0x01, "table id"),
        _f("level.s4.L1.kind@0x1dd", "level", 0x1DD, 0x01, "kind 0x93: directory read length"),
        # Box table at 0x2ac: not loaded by the header entry in this mount
        _f("box.n_tables@0x2ac", "box", 0x2AD, 0x01, "negative control: not read"),
        _f("box.s1.id@0x2ae", "box", 0x2AE, 0x01, "not read"),
        _f("box.s1.n@0x2af", "box", 0x2AF, 0x01, "not read"),
        _f("box.s1.L2.level@0x2b0", "box", 0x2B0, 0x01, "not read"),
        _f("box.s1.L2.flag@0x2b1", "box", 0x2B1, 0x01, "not read"),
        _f("box.s1.L2.lat_top@0x2b3", "box", 0x2B3, 0x01, "not read"),
        _f("box.s1.L2.lon_left@0x2b7", "box", 0x2B7, 0x01, "not read"),
        _f("box.s4.id@0x2da", "box", 0x2DA, 0x01, "not read"),
        _f("box.s4.L1.flag@0x2dd", "box", 0x2DD, 0x01, "not read"),
        # Section list at 0x800: 6 bytes {u24 sector, u8 offset, u16 length}
        _f("sect.0.sector@0x800", "sect", 0x802, 0x01, "sector low byte"),
        _f("sect.0.offset@0x803", "sect", 0x803, 0x01, "M3.25: 0x1000 -> 0x1100"),
        _f("sect.0.length@0x804", "sect", 0x805, 0x01, "length 0x400 -> 0x500"),
        _f("sect.1.sector@0x806", "sect", 0x808, 0x01, "sector low byte"),
        _f("sect.1.offset@0x809", "sect", 0x809, 0x01, "offset byte"),
        _f("sect.1.length@0x80a", "sect", 0x80B, 0x01, "length low byte"),
        _f("sect.2.sector@0x80c", "sect", 0x80E, 0x01, "sector low byte"),
        _f("sect.2.offset@0x80f", "sect", 0x80F, 0x01, "offset byte"),
        _f("sect.2.length@0x810", "sect", 0x811, 0x01, "length low byte"),
        _f("sect.terminator@0x812", "sect", 0x812, 0xFF, "ff -> 00: creates a 4th entry"),
    ]
    # Positive control: the whole third entry becomes the terminator, the
    # M3.33 mutation that drops the tile (one field, four bytes).
    third = header[0x80C:0x810]
    if len(third) != 4:
        raise ValueError("header must be 0x1000 bytes")
    out.append(Field("sect.2.entry@0x80c", "sect",
                     tuple((0x80C + i, b ^ 0xFF) for i, b in enumerate(third)),
                     "positive control: remove entry 2 -> tile left after header"))
    if len(out) > MAX_MUTATIONS:
        raise ValueError("%d fields exceeds the %d-mutation budget" % (len(out), MAX_MUTATIONS))
    return out


def apply_flips(header: bytes, field: Field) -> bytes:
    b = bytearray(header)
    for off, xor in field.flips:
        if not 0 <= off < HEADER_SIZE:
            raise ValueError("offset %#x outside the header" % off)
        b[off] ^= xor
    return bytes(b)


def flip_specs(path: str, field: Field) -> list[str]:
    return ["%s@%#x:%#x" % (path, off, xor) for off, xor in field.flips]


# ---------------------------------------------------------------------------
# One firmware run, with the header-check hooks of tile_drop_l3.py
# ---------------------------------------------------------------------------


def run_mount(image: str, card, position) -> dict:
    """Run the whole mount once; keep every read row and every header-check
    event.  The hooks are the ones in ``tools/tile_drop_l3.py`` lines 155-193."""
    import datask_l3 as D

    t = D.DataTask(image, card, position=position)
    m = t.m
    b = T.EU2011
    events: list[dict] = []
    cur: list[dict] = []

    def read_box(index: int) -> dict:
        return T.box_fields(bytes(m.eng.read_mem(b["boxes"] + 24 * index, 24)))

    def on_check(_e, _va):
        buf, bx = m.arg(2), m.arg(3)
        index = (bx - b["boxes"]) // 24
        box = read_box(index)
        raw = bytes(m.eng.read_mem(buf + T.SECT_OFF, 18))
        # the firmware swapped every u16 of the header: swap back to file order
        raw = b"".join(raw[i + 1:i + 2] + raw[i:i + 1] for i in range(0, len(raw), 2))
        ev = {"box": index, "file": T.box_name(box), "mask": box["mask"],
              "levels": box["levels"], "progress": m.u32(b["progress"]),
              "sections": T.parse_section_list(raw, 3),
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

    for va, hook in ((b["check"], on_check), (b["absent"], on_absent),
                     (b["find_ret_tile"], on_find_ret), (b["check_ret"], on_check_ret)):
        m.eng.on_exec(va, hook)

    rows: list[dict] = []
    blocked = None
    try:
        end = t.run(0, False, rows.append, [])
    except (V.Blocked, V.EngineError) as exc:
        end = "blocked"
        blocked = {"type": type(exc).__name__, "message": str(exc)[:200]}
    tables: dict[str, int] = {}
    for r in rows:
        if (r["tag"] >> 8) == 6:
            name = (r["file"] or "").split("/")[-1].upper()
            tables[name] = tables.get(name, 0) + 1
    return {"end": end, "blocked": blocked, "events": events, "rows": rows,
            "section_tables": tables, "summary": t.summary()}


# ---------------------------------------------------------------------------
# Signature and verdict
# ---------------------------------------------------------------------------


def rows_sig(rows: list[dict], tile: str) -> list[dict]:
    out = []
    for r in rows:
        if (r.get("file") or "").split("/")[-1].upper() != tile:
            continue
        out.append({"tag": r.get("tag"), "pos": r.get("pos"),
                    "length": r.get("length"), "handler": r.get("handler"),
                    "readers": [{"fn": x.get("fn"), "bytes": x.get("bytes"),
                                 "runs": x.get("runs")} for x in r.get("readers", [])]})
    return out


def events_sig(events: list[dict], tile: str) -> list[dict]:
    keys = ("mask", "levels", "progress", "sections", "absent_part",
            "reopened_box", "result")
    return [{k: e.get(k) for k in keys} for e in events if e.get("file") == tile]


def _first_reader_diff(a: dict, b: dict):
    ra = {x.get("fn"): x for x in a.get("readers", [])}
    rb = {x.get("fn"): x for x in b.get("readers", [])}
    for fn in sorted(set(ra) | set(rb)):
        if ra.get(fn) != rb.get(fn):
            return fn
    return None


def first_diff(base: dict, mut: dict, tile: str):
    """The fn and a one-line reason for the first observable change."""
    br, mr = base["rows"], mut["rows"]
    if len(br) != len(mr):
        fn = (mr or br)[0].get("handler") if (mr or br) else None
        return fn, "tile read count %d -> %d" % (len(br), len(mr))
    for i, (a, b) in enumerate(zip(br, mr)):
        if a == b:
            continue
        if a.get("handler") != b.get("handler"):
            return b.get("handler") or a.get("handler"), "read %d handler changed" % i
        fn = _first_reader_diff(a, b)
        if fn is not None:
            return fn, "read %d parser byte range changed" % i
        return a.get("handler"), "read %d changed" % i
    be, me = base["events"], mut["events"]
    if be != me:
        return CHECK, "header check saw a different section list"
    return None, "signature changed"


def classify(base: dict, mut: dict, tile: str):
    """Return (verdict, fn, detail).  Pure: selftest feeds it synthetic runs."""
    sig_b = {"rows": rows_sig(base.get("rows", []), tile),
             "events": events_sig(base.get("events", []), tile)}
    sig_m = {"rows": rows_sig(mut.get("rows", []), tile),
             "events": events_sig(mut.get("events", []), tile)}
    ev_m = [e for e in mut.get("events", []) if e.get("file") == tile]
    if mut.get("blocked"):
        return ("rejected", "0x%08x" % CHECK,
                "%s: %s" % (mut["blocked"]["type"], mut["blocked"]["message"]))
    absent = [e for e in ev_m if e.get("absent_part") is not None]
    if absent:
        part = absent[0]["absent_part"]
        return ("rejected", "0x%08x" % CHECK,
                "part %d missing -> check +0x16e returns -1" % part)
    if ev_m and not mut.get("section_tables", {}).get(tile) and not sig_m["rows"]:
        return ("rejected", "0x%08x" % CHECK, "tile left after its header")
    if any(e.get("result") == -1 for e in ev_m):
        return ("rejected", "0x%08x" % CHECK, "header check returned -1")
    if sig_m != sig_b:
        fn, why = first_diff(sig_b, sig_m, tile)
        return ("read-different", ("0x%08x" % fn) if fn is not None else "-", why)
    return ("read-same", "-", "")


# ---------------------------------------------------------------------------
# The sweep
# ---------------------------------------------------------------------------


def discover_tile(base: dict) -> str:
    for e in base.get("events", []):
        if e.get("file") != "LEV3456R.DAT":
            return e["file"]
    return TILE


def cmd_sweep(args) -> int:
    image = args.image
    card_path = args.card_image
    lat, _, lon = args.position.partition(",")
    position = (float(lat), float(lon))
    base_card = V.make_card(None, card_path, {})
    header = V.Expected(base_card).read("MAPAL001/" + args.tile, 0, HEADER_SIZE)
    if header is None or len(header) != HEADER_SIZE:
        print("cannot read the 0x1000-byte header of MAPAL001/%s" % args.tile)
        return 2
    print("sample tile: MAPAL001/%s; header %d bytes" % (args.tile, len(header)))

    print("running factory baseline ...", flush=True)
    base = run_mount(image, base_card, position)
    tile = discover_tile(base)
    if args.tile.upper() != tile:
        print("note: firmware mounted %s, not %s; mutations still target %s" %
              (tile, args.tile, args.tile))
    print("baseline: %s; %d tile read(s), section tables %s" %
          (base["end"], len(rows_sig(base["rows"], tile)),
           base["section_tables"].get(tile, 0)), flush=True)

    only = set(x.upper() for x in args.only.split(",") if x) if args.only else None
    flist = [f for f in fields(header)
             if not only or any(o in f.name.upper() or o == f.group.upper() for o in only)]
    if args.limit:
        flist = flist[:args.limit]
    print("mutations: %d (budget %d)" % (len(flist), MAX_MUTATIONS))

    table = []
    for f in flist:
        card = V.make_card(None, card_path,
                           {"flip": flip_specs("MAPAL001/" + args.tile, f)})
        mut = run_mount(image, card, position)
        verdict, fn, detail = classify(base, mut, tile)
        table.append({"field": f.name, "group": f.group, "verdict": verdict,
                      "fn": fn, "detail": detail, "note": f.note,
                      "flips": [list(x) for x in f.flips],
                      "end": mut["end"], "blocked": mut["blocked"],
                      "tile_reads": len(rows_sig(mut["rows"], tile)),
                      "section_tables": mut["section_tables"].get(tile, 0),
                      "rows": rows_sig(mut["rows"], tile),
                      "events": events_sig(mut["events"], tile)})
        print("%-30s %-8s %-12s %s%s" %
              (f.name, verdict, fn, detail, ("  [" + f.note + "]") if f.note else ""),
              flush=True)

    counts = {}
    for r in table:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print("verdicts: " + ", ".join("%s %d" % kv for kv in sorted(counts.items())))
    ctrl = [r for r in table if r["field"].startswith("sect.2.entry")]
    if ctrl:
        print("positive control: %s -> %s (%s)" %
              (ctrl[0]["field"], ctrl[0]["verdict"], ctrl[0]["fn"]))
    neg = [r for r in table if r["field"].startswith("id.HITACHI")]
    if neg:
        print("negative control: %s -> %s" % (neg[0]["field"], neg[0]["verdict"]))

    if args.json:
        Path(args.json).write_text(json.dumps({
            "sample": {"image": image, "card": card_path, "tile": args.tile,
                       "position": list(position)},
            "baseline": {"end": base["end"], "rows": rows_sig(base["rows"], tile),
                         "events": events_sig(base["events"], tile),
                         "section_tables": base["section_tables"]},
            "verdicts": counts, "table": table,
        }, indent=1) + "\n")
    return 0


# ---------------------------------------------------------------------------
# self-test (synthetic; no vendor data)
# ---------------------------------------------------------------------------


def _synthetic_run():
    return {
        "rows": [{"file": "MAPAL001/" + TILE, "tag": 0x0400, "pos": 0,
                  "length": 0x1000, "handler": 0x0040B8B4,
                  "readers": [{"fn": 0x0040AA50, "bytes": 40,
                               "runs": [(0x1AC, 0x1D4)]}]}],
        "events": [{"file": TILE, "mask": 7, "levels": 3, "progress": 0,
                    "sections": [{"pos": 0x1000, "length": 0x400}],
                    "absent_part": None, "reopened_box": None, "result": 0}],
        "section_tables": {TILE: 3}, "blocked": None,
    }


def selftest() -> int:
    failed = 0

    def ok(cond, msg):
        nonlocal failed
        print(("  ok   " if cond else "  FAIL ") + msg)
        failed += 0 if cond else 1

    print("tile_sweep_l3 selftest (synthetic, no vendor data)")
    h = bytearray(HEADER_SIZE)
    h[0x80C:0x810] = bytes.fromhex("02251903")
    fs = fields(bytes(h))
    ok(len(fs) <= MAX_MUTATIONS, "field count %d <= %d" % (len(fs), MAX_MUTATIONS))
    ok(len(set(f.name for f in fs)) == len(fs), "field names are unique")
    ok(all(0 <= off < HEADER_SIZE for f in fs for off, _ in f.flips),
       "every flip is inside the 0x1000 header")
    ok(all(len(f.flips) == 1 for f in fs if not f.name.startswith("sect.2.entry")),
       "one byte per ordinary field")
    ctrl = [f for f in fs if f.name == "sect.2.entry@0x80c"][0]
    ok([off for off, _x in ctrl.flips] == [0x80C, 0x80D, 0x80E, 0x80F],
       "positive control mutates the whole third entry")
    ok(apply_flips(bytes(h), ctrl)[0x80C:0x810] == b"\xff" * 4,
       "positive control writes the terminator")
    one = _f("probe", "header", 0x123, 0x01)
    m = apply_flips(bytes(h), one)
    ok([i for i in range(HEADER_SIZE) if m[i] != h[i]] == [0x123],
       "apply_flips changes exactly one byte")
    ok(flip_specs("MAPAL001/X.DAT", one) == ["MAPAL001/X.DAT@0x123:0x1"],
       "flip_specs uses the overlay syntax")

    base = _synthetic_run()
    ok(classify(base, copy.deepcopy(base), TILE)[0] == "read-same",
       "identical run -> read-same")
    diff = copy.deepcopy(base)
    diff["rows"][0]["readers"][0]["bytes"] = 402
    v, fn, _why = classify(base, diff, TILE)
    ok(v == "read-different" and fn == "0x0040aa50",
       "changed parser range -> read-different, names the parser fn")
    drop = copy.deepcopy(base)
    drop["events"][0]["absent_part"] = 2
    drop["section_tables"] = {}
    v, fn, _why = classify(base, drop, TILE)
    ok(v == "rejected" and fn == "0x%08x" % CHECK,
       "missing part -> rejected by the header check")
    blocked = dict(_synthetic_run(), blocked={"type": "Blocked", "message": "no import model"})
    ok(classify(base, blocked, TILE)[0] == "rejected", "blocked run -> rejected")
    neg = copy.deepcopy(base)
    neg["events"][0]["sections"][0]["pos"] = 0x1100
    ok(classify(base, neg, TILE)[0] == "read-different",
       "a changed section list is not silently called read-same")
    ok(T.parse_section_list(bytes.fromhex("000002000001" + "ffffffff0000")) != [],
       "reused parse_section_list still decodes one entry")
    print("tile_sweep_l3 selftest: %s (%d failure(s))" % ("PASS" if failed == 0 else "FAIL", failed))
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("sweep", help="flip one field at a time and print the verdict table")
    p.add_argument("image")
    p.add_argument("--card-image", required=True)
    p.add_argument("--position", default=",".join(str(x) for x in DEFAULT_POSITION),
                   metavar="LAT,LON")
    p.add_argument("--tile", default=TILE)
    p.add_argument("--only", default=None, help="comma-separated field names or groups")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--json", default=None)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "sweep":
        return cmd_sweep(args)
    ap.error("a command or --selftest is required")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
