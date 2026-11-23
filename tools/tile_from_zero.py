#!/usr/bin/env python3
"""tile_from_zero.py — write OSM roads into a tile that holds no factory record (M5.88, Z3).

The splice writer (``tilewriter.py --factory``) can only replace records in
slots the factory tile already has (M5.70); a from-zero tile has none.  This
tool takes the container of a tile (``tile_relayout.read_model`` +
``empty_model``: section tables and every directory, all empty; M5.87), builds
one level-1 road record per parcel with ``tilewriter.build_road_record`` from
mesh-split IMF, puts each record into its directory row and column (even
pair; the odd partner stays empty), and lets ``tile_relayout.write_model``
lay the tile out.  No factory record is copied (``tile_provenance.py
--require-zero`` is the gate).

    tile_from_zero.py SPLIT.jsonl --template TILE.DAT --cell B48R068R \\
        --class-table CLASS.json --country 826 -o OUT.DAT [--json] [--no-names]
    tile_from_zero.py --selftest

The template supplies only the container (header strings, level/box tables,
directory boxes); M5.86 counts those bytes.  Level 1 only.  Exit codes: 0 ok,
1 check failed, 2 usage.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE / "ze0-viewer" / "tools_ze0", HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import fa_encode  # noqa: E402
import tile_relayout  # noqa: E402
import tilewriter  # noqa: E402

EMPTY1 = 0x7FFFFFFF  # empty even pair, level 1
EMPTY_ODD = 0xFFFFFFFF  # empty odd pair, level 1 (0x7fffffff here moves the read 4 GiB, M5.88)
# No record-size ceiling is known: the firmware inflates into a window of the
# record's size rounded up to 256 (L3, M5.88: 101,128 B and 156,356 B records
# read with reply sub 3, the 101,128-B start parcel draws at L4).  --max-plain
# keeps a cap for the capacity probe (M5.92): it drops a parcel's least
# important roads until the record fits.


class CheckFailed(Exception):
    pass


def level1_dirs(m: dict) -> dict:
    """``{(y0, x0): directory model}`` of section 1 level 1."""
    out = {}
    for sec in m["sections"]:
        if sec["id"] != 1:
            continue
        for L in sec["levels"]:
            if L["level"] != 1:
                continue
            for dm in L["dirs"]:
                wm = dm["wm"]
                out[(wm["y"], tilewriter.dir_x0(wm))] = dm
    return out


def place(m: dict, built: dict) -> dict:
    """Put ``{parcel: (plain, comp)}`` into the level-1 directories of ``m``."""
    dirs = level1_dirs(m)
    rows = collections.defaultdict(dict)
    missing = 0
    for (y0, x0, row, col), (plain, comp) in built.items():
        if (y0, x0) not in dirs:
            missing += 1
            continue
        rows[(y0, x0, row)][col] = (plain, comp)
    if missing:
        raise CheckFailed("%d parcel(s) have no level-1 directory in the template" % missing)
    stats = collections.Counter()
    for (y0, x0, row), cols in rows.items():
        dm = dirs[(y0, x0)]
        r = dm["wm"]["rows"][row]
        if r["wide"]:
            raise CheckFailed("template row is wide; run tile_relayout empty first")
        block = b""
        recs = []
        for c in range(len(r["cols"])):
            if c in cols:
                plain, comp = cols[c]
                if len(comp) % 2 or len(plain) % 2:
                    raise CheckFailed("record not word aligned")
                r["cols"][c] = dict(even=(len(comp) // 2, len(plain) // 2), odd=(EMPTY_ODD, EMPTY_ODD), subs=[])
                block += comp
                recs.append(comp)
                stats["records"] += 1
                stats["plain_bytes"] += len(plain)
                stats["comp_bytes"] += len(comp)
        unit = dm["units"][row]
        unit.update(live=True, old=("new", y0, x0, row), block=block, recs=recs, tag=0)
        stats["rows"] += 1
    return dict(stats)


def build_records(split: str, cell: str, class_table: str | None, country: int, write_names: bool,
                  limit: int = 0):
    table, _src = tilewriter.load_class_table(class_table)
    ways, imf_stats = tilewriter.load_imf(split, cell)
    runs = tilewriter.ways_to_runs(ways, 1, table, cell)
    built, sizes = {}, []
    trim = collections.Counter()
    for parcel in sorted(runs):
        res, dropped = fit_record(parcel, runs[parcel], table, country, write_names, limit)
        if dropped:
            trim["parcels"] += 1
            trim["runs"] += dropped
        if res is None:
            continue
        plain, comp, _names, _info = res
        built[parcel] = (plain, comp)
        sizes.append(len(plain))
    imf_stats = dict(imf_stats, trimmed=dict(trim))
    return built, sizes, imf_stats


def fit_record(parcel, runs, table, country, write_names, limit=0):
    """Build the record; drop the least important runs until it fits ``limit``.

    The class table's second value is the rank (1 motorway ... 9 service);
    runs are dropped from the highest rank, longest first being kept.
    Returns ``(result, dropped_runs)``.
    """
    rank = lambda r: table[tilewriter._run_fields(r)[1]][1]  # noqa: E731
    order = sorted(runs, key=lambda r: (rank(r), -len(tilewriter._run_fields(r)[0])))
    keep = len(order)
    res = tilewriter.build_road_record(1, parcel, order, table, country, write_names=write_names)
    while limit and res is not None and len(res[0]) > limit and keep > 1:
        keep = max(1, keep - max(1, keep // 10))
        res = tilewriter.build_road_record(1, parcel, order[:keep], table, country, write_names=write_names)
    if limit and res is not None and len(res[0]) > limit:
        raise CheckFailed("parcel %r: one run alone exceeds %d B" % (parcel, limit))
    return res, len(order) - keep


def from_zero(template: bytes, built: dict, pad: bool = True) -> tuple[bytes, dict]:
    m = tile_relayout.empty_model(tile_relayout.read_model(template))
    st = place(m, built)
    out, wst = tile_relayout.write_model(m)
    if pad:
        out = tilewriter.pad_directory_reads(out)
    st.update(size=len(out), dirs=wst["dirs"])
    # read back: every placed record is a zlib stream that inflates to its body
    back = tile_relayout.read_model(out)
    got = 0
    for sec in back["sections"]:
        for L in sec["levels"]:
            for dm in L["dirs"]:
                for u in dm["units"]:
                    for raw in u["recs"]:
                        if raw:
                            zlib.decompress(raw)
                            got += 1
    if got != st.get("records", 0):
        raise CheckFailed("read back %d records, placed %d" % (got, st.get("records", 0)))
    return out, st


def selftest() -> int:
    fails = 0

    def ok(cond, msg):
        nonlocal fails
        print(("ok   " if cond else "FAIL ") + msg)
        fails += 0 if cond else 1

    # A one-directory section-1 level-1 template from s1_wide_dir's synthetic
    # directory, wrapped in a minimal tile.
    import s1_wide_dir
    TABLE1_OFF, SECT_OFF = tile_relayout.TABLE1_OFF, tile_relayout.SECT_OFF
    enc, pad = tile_relayout.enc_addr, tile_relayout.pad256
    hdr = bytearray(TABLE1_OFF)
    lo = tile_relayout.clarion_tile.LEVEL_OFF
    struct.pack_into(">H", hdr, lo, 1)
    hdr[lo + 2:lo + 4] = bytes([1, 1])
    hdr[lo + 4:lo + 8] = bytes([1, 0x92]) + struct.pack(">H", 1)
    struct.pack_into(">IH", hdr, SECT_OFF + 6, 0xFFFFFFFF, 0)
    y0, x0 = 77, 923
    d = bytearray(struct.pack(">6H", 0x2046, 0, 32, y0, tilewriter.x_field(x0), 0))
    for _ in range(32):
        d += struct.pack(">I", 0xFFFFFFFF) + struct.pack(">I", EMPTY1) * 128
    table_at, dir_at = TABLE1_OFF, TABLE1_OFF + 256
    out = bytearray(pad(dir_at + len(d)))
    out[:TABLE1_OFF] = hdr
    struct.pack_into(">IH", out, SECT_OFF, enc(table_at), 1)
    a = enc(dir_at)
    out[table_at:table_at + 20] = struct.pack(">10H", 10, 2, 8, 1, 100, 0, 0, 100, a >> 16, a & 0xFFFF)
    out[dir_at:dir_at + len(d)] = d
    tmpl = bytes(out)
    ok(s1_wide_dir.census(tmpl)["counts"]["dirs"] == 1, "template: one level-1 directory")
    table = tilewriter.default_class_table()
    lon0, lat0 = -0.15625, 51.5
    runs = [([(lon0 + 0.001, lat0 + 0.001), (lon0 + 0.02, lat0 + 0.015), (lon0 + 0.03, lat0 + 0.002)],
             "residential", "")]
    parcel = tilewriter.parcel_of(lon0 + 0.001, lat0 + 0.001, 1)
    plain, comp, _n, _i = tilewriter.build_road_record(1, parcel, runs, table, 826, write_names=False)
    blob, st = from_zero(tmpl, {parcel: (plain, comp)}, pad=False)
    ok(st["records"] == 1 and st["rows"] == 1, "one record placed in one row")
    c = s1_wide_dir.census(blob)
    ok(s1_wide_dir.census_ok(c) and c["counts"]["records"] == 1, "s1_wide_dir census accepts the tile, 1 record")
    m = tile_relayout.read_model(blob)
    rec = [r for sec in m["sections"] for L in sec["levels"] for dm in L["dirs"] for u in dm["units"] for r in u["recs"]]
    ok(zlib.decompress(rec[0]) == plain, "the record inflates to the built body")
    _code, _g, shapes = fa_encode.parse_record(zlib.decompress(rec[0]), 1)
    ok(shapes and all(s["ok"] for s in shapes), "fa_encode re-reads the shapes")
    try:
        from_zero(tmpl, {(y0 + 1, x0, 0, 0): (plain, comp)}, pad=False)
        ok(False, "a parcel outside the template is refused (negative control)")
    except CheckFailed:
        ok(True, "a parcel outside the template is refused (negative control)")
    # a long run is split into shapes of <= 255 points (M5.88)
    long_run = [([(lon0 + 0.0001 * i, lat0 + 0.0005 + 0.00001 * (i % 7)) for i in range(300)], "residential", "")]
    p2 = tilewriter.parcel_of(lon0 + 0.0001, lat0 + 0.0005, 1)
    pl2, _c2, _n2, _i2 = tilewriter.build_road_record(1, p2, long_run, table, 826, write_names=False)
    _code, _g, sh2 = fa_encode.parse_record(pl2, 1)
    ok(len(sh2) >= 2 and all(s["ok"] for s in sh2), "a 300-point run becomes >= 2 readable shapes (%d)" % len(sh2))
    # empty level-1 odd pairs are 0xffffffff (0x7fffffff moved the read 4 GiB, M5.88)
    cols = [col for _l, D in s1_wide_dir.section1_dirs(blob)
            for r in s1_wide_dir.parse_dir(blob, D["off"], 1, check=False)["rows"] for col in r["cols"]]
    ok(all(c["odd"][0] == EMPTY_ODD for c in cols) and sum(c["even"][0] != EMPTY1 for c in cols) == 1,
       "empty odd pairs 0xffffffff, one even record")
    # --max-plain drops the least important runs first
    two = runs + [([(lon0 + 0.002, lat0 + 0.003), (lon0 + 0.025, lat0 + 0.01)], "motorway", "")]
    full, _ = fit_record(parcel, two, table, 826, False)
    small, dropped = fit_record(parcel, two, table, 826, False, limit=len(full[0]) - 1)
    ok(dropped == 1 and len(small[0]) < len(full[0]), "a cap drops one run (the residential one)")
    print("tile_from_zero selftest: %s (%d failure(s))" % ("OK" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("split", nargs="?")
    ap.add_argument("--template")
    ap.add_argument("--cell")
    ap.add_argument("--class-table")
    ap.add_argument("--country", type=int, default=616)
    ap.add_argument("--no-names", action="store_true")
    ap.add_argument("--max-plain", type=lambda v: int(v, 0), default=0,
                    help="drop the least important roads of a parcel until its record fits (0 = no limit)")
    ap.add_argument("-o", "--out")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not (args.split and args.template and args.cell and args.out):
        ap.print_usage(sys.stderr)
        return 2
    try:
        built, sizes, imf_stats = build_records(args.split, args.cell, args.class_table, args.country,
                                                not args.no_names, args.max_plain)
        out, st = from_zero(Path(args.template).read_bytes(), built)
    except (CheckFailed, tilewriter.CheckFailed, tilewriter.WriterError) as exc:
        print("tile_from_zero: FAIL %s" % exc)
        return 1
    Path(args.out).write_bytes(out)
    sizes.sort()
    q = lambda f: sizes[min(len(sizes) - 1, int(f * len(sizes)))] if sizes else 0  # noqa: E731
    st.update(parcels=len(built), plain_min=sizes[0] if sizes else 0, plain_median=q(0.5),
              plain_p99=q(0.99), plain_max=sizes[-1] if sizes else 0,
              sha256=hashlib.sha256(out).hexdigest(), imf=imf_stats)
    if args.json:
        print(json.dumps(st, indent=1, default=str))
    else:
        print("from-zero: parcels=%d records=%d rows=%d size=%d B sha256 %s"
              % (st["parcels"], st["records"], st["rows"], st["size"], st["sha256"]))
        print("record plain bytes: min %d median %d p99 %d max %d"
              % (st["plain_min"], st["plain_median"], st["plain_p99"], st["plain_max"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
