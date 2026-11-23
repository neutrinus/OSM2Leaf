#!/usr/bin/env python3
"""M5.61 driver: build one Poland tile (one section-1 level) from an OSM PBF.

Pipeline::

    osm_ingest.py --bbox <the tile's box>     OSM -> IMF (repo extractor)
      -> keep single-cell ways                (drop ways that leave the tile)
      -> tilewriter.py --factory              (repo tile writer)

Drop rule (a tile is an independent file, so it has to be able to hold its
own data): a parcel whose record the checked-in reader cannot re-read loses
whole ways lowest class first until it re-reads; ways that touch a level-2
parcel with no factory even slot are dropped whole (the writer cannot create
one). Every dropped way is counted by highway value.

``osm_ingest --bbox`` already tags every way with the cells it touches, so a
way whose ``tiles`` is exactly this cell needs no ``mesh_split``; keeping only
those is the "clip at the tile border" semantic.

Usage::

  m5_61_build_tile.py --osm PBF --cell B50R050R --level 1 \
      --factory-root ROOT --out TILE.DAT --scratch DIR --report R.json

``--drop-parcel Y,X,R,C`` builds with that parcel left factory (no drop): the
negative control for the full pipeline.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))


def run(mod: str, argv: list[str]) -> tuple[int, str, str]:
    p = subprocess.run([sys.executable, str(REPO / "tools" / mod), *argv],
                       capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def tile_bbox(cell: str) -> tuple[float, float, float, float]:
    lat0 = int(cell[1:3], 16) * 2 / 3
    lon_max = 108 - int(cell[4:7], 16)
    return lon_max - 8.0, lat0, lon_max, lat0 + 16.0 / 3.0


def selftest() -> int:
    ok = True

    def chk(cond, msg):
        nonlocal ok
        print(("ok   " if cond else "FAIL ") + msg)
        ok = ok and cond

    def close(box, want):
        return all(abs(a - b) < 1e-9 for a, b in zip(box, want))

    chk(close(tile_bbox("B50R050R"), (20.0, 160 / 3, 28.0, 176 / 3)),
        "B50R050R box is 20..28 E, 53.33..58.67 N")
    chk(close(tile_bbox("B48R058R"), (12.0, 48.0, 20.0, 160 / 3)),
        "B48R058R box is 12..20 E, 48..53.33 N")
    table = {"motorway": (0, 1), "residential": (5, 9), "track": (7, 12)}
    chk(max(table, key=lambda h: table[h]) == "track",
        "drop rule picks track (7,12) before residential/motorway")
    # M5.71: --drop-parcel removes a declared parcel's ways from the actual
    # build but not from the declared set (so the writer's guard fails).
    parcel_ways = {("a",): {"w1", "w2"}, ("b",): {"w3"}}
    declared = {p for p in parcel_ways if any(w not in set() for w in parcel_ways[p])}
    skip = set(parcel_ways[("a",)])
    built = {p for p in parcel_ways if any(w not in skip for w in parcel_ways[p])}
    chk(("a",) in declared and ("a",) not in built,
        "--drop-parcel: parcel declared but left factory")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--osm")
    ap.add_argument("--cell")
    ap.add_argument("--level", type=int, choices=(1, 2), default=1)
    ap.add_argument("--factory-root")
    ap.add_argument("--out")
    ap.add_argument("--scratch")
    ap.add_argument("--report")
    ap.add_argument("--max-drop", type=int, default=20000,
                    help="refuse (no tile) when the drop rule removes more ways")
    ap.add_argument("--drop-parcel", metavar="Y,X,R,C",
                    help="build with this parcel kept factory (negative control)")
    ap.add_argument("--drop-absent-slot", action="store_true",
                    help="M5.61 rule: drop whole ways that touch a level-2 parcel "
                         "with no factory even slot (the writer can now create one; "
                         "use only to reproduce the old count)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    for name in ("osm", "cell", "factory_root", "out", "scratch", "report"):
        if not getattr(args, name):
            ap.error("--%s is required" % name.replace("_", "-"))

    scratch = Path(args.scratch)
    (scratch / "tmp").mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = str(scratch / "tmp")
    cell, level = args.cell, args.level
    report: dict = {"cell": cell, "level": level}
    box = tile_bbox(cell)
    report["tile_bbox"] = box
    imf = scratch / f"{cell}-L{level}.imf.jsonl"

    if not imf.exists():
        rc, so, se = run("osm_ingest.py", [args.osm, "-o", str(imf), "--bbox",
                                           ",".join("%.7f" % v for v in box),
                                           "--source-name", "poland-latest"])
        report["osm_ingest_rc"] = rc
        if rc != 0:
            report["error"] = (se or so)[-800:]
            Path(args.report).write_text(json.dumps(report, indent=2))
            print(report["error"], file=sys.stderr)
            return 1

    single = scratch / f"{cell}-L{level}.single.split.jsonl"
    if not single.exists():
        ways_in = ways_out = 0
        with single.open("w", encoding="utf-8", newline="\n") as out:
            for line in imf.open(encoding="utf-8"):
                rec = json.loads(line)
                if rec.get("type") == "way":
                    ways_in += 1
                    tiles = rec.get("tiles") or ([rec["tile"]] if rec.get("tile") else [])
                    if {str(t) for t in tiles} != {cell}:
                        continue
                    ways_out += 1
                out.write(line)
        report["ways_in"] = ways_in
        report["ways_single_cell"] = ways_out
        report["ways_leaving_tile"] = ways_in - ways_out

    ctab = scratch / "ctab.json"
    if not ctab.exists():
        rc, so, se = run("roadclass_v0.py", ["--class-table-out", str(ctab)])
        if rc != 0:
            print("roadclass_v0 failed: " + se, file=sys.stderr)
            return 1

    import tilewriter as T
    import clarion_tile
    table, _ = T.load_class_table(str(ctab))
    yb, xb = T.cell_mesh(cell)
    shift = 8 - T.DIR_MESHES[level]

    keep_parcel = None
    if args.drop_parcel:
        keep_parcel = tuple(int(x) for x in args.drop_parcel.split(","))
        report["drop_parcel"] = "%d,%d,%d,%d" % keep_parcel

    # Level-2 parcels with no factory even slot.  M5.70: the writer can now
    # create one (splice_factory appends a whole rebuilt slot block, the
    # firmware follows the tag), so this is a *census*, not a drop reason.
    # The M5.61 rule (present slot rows only) and the Done-when rule (all 32
    # rows, including rows absent from the slot table) are counted apart so
    # the 1313-vs-1505 confusion cannot recur (M5.70 N1).
    unwritable: set[tuple] = set()
    census: dict = {}
    if level == 2:
        factory_bytes = (Path(args.factory_root) / "MAPAL001" / f"{cell}.DAT").read_bytes()
        census = T.l2_slot_census(T.read_tile_rows(factory_bytes))
        report["l2_census"] = {k: census[k] for k in
                               ("present_rows", "absent_rows", "total")}
        # --drop-absent-slot reproduces M5.61's old rule (keep the drop the
        # writer no longer needs); by default nothing is dropped for a slot.
        if args.drop_absent_slot:
            unwritable = set(census["missing"])
    report["l2_unwritable_parcels"] = len(unwritable)

    nodes: dict[str, tuple[float, float]] = {}
    for line in single.open(encoding="utf-8"):
        rec = json.loads(line)
        if rec.get("type") == "node":
            nodes[str(rec["id"])] = (float(rec["lon"]), float(rec["lat"]))

    ways: dict[str, tuple[str, list]] = {}
    parcel_ways: dict[tuple, set] = {}
    for line in single.open(encoding="utf-8"):
        rec = json.loads(line)
        if rec.get("type") != "way":
            continue
        hw = (rec.get("tags") or {}).get("highway")
        if hw not in table:
            continue
        try:
            pts = [nodes[str(n)] for n in rec.get("nodes") or []]
        except KeyError:
            continue
        if len(pts) < 2:
            continue
        wid = str(rec["id"])
        pieces = []
        for parcel, pseq in T.parcel_runs(pts, level):
            y0, x0, row, col = parcel
            y0 = min(max(y0, yb), yb + shift)
            x0 = min(max(x0, xb), xb + shift)
            key = (y0, x0, row, col)
            pieces.append((key, pseq))
            parcel_ways.setdefault(key, set()).add(wid)
        ways[wid] = (hw, pieces)

    skip: set[str] = set()
    no_slot: set[str] = set()
    if level == 2:
        for wid, (_hw, pieces) in ways.items():
            if any(p in unwritable for p, _ in pieces):
                no_slot.add(wid)
        skip |= no_slot

    def records(parcel, dropped: set[str]) -> list:
        out = []
        for wid in parcel_ways.get(parcel, ()):
            if wid in dropped:
                continue
            for key, pseq in ways[wid][1]:
                if key == parcel:
                    out.append((pseq, ways[wid][0], ""))
        return out

    def unreadable(parcel, dropped: set[str]) -> bool:
        try:
            T.build_road_record(level, parcel, records(parcel, dropped), table,
                                616, write_names=False)
            return False
        except T.CheckFailed:
            return True

    def table_only(parcel, dropped):
        return T.build_road_record(level, parcel, records(parcel, dropped),
                                   table, 616, write_names=False)

    # Build the in-memory runs once (linear) and find the dense parcels.
    runs: dict[tuple, list] = {}
    for wid, (hw, pieces) in ways.items():
        if wid in skip:
            continue
        for parcel, pseq in pieces:
            if parcel in unwritable:
                continue
            runs.setdefault(parcel, []).append((pseq, hw, ""))

    def check_parcel(parcel, runlist):
        try:
            T.build_road_record(level, parcel, runlist, table, 616, write_names=False)
            return True
        except T.CheckFailed:
            return False

    bad = [p for p in sorted(runs) if not check_parcel(p, runs[p])]
    report["parcels"] = len(runs)
    report["dense_parcels_before"] = len(bad)
    report["dense_parcels_before_list"] = ["%d,%d,%d,%d" % p for p in bad]

    dense_drop: dict[str, int] = {}
    for parcel in bad:
        while True:
            if check_parcel(parcel, records(parcel, skip)):
                break
            candidates = [w for w in parcel_ways.get(parcel, ()) if w not in skip]
            if not candidates:
                raise SystemExit("parcel %r cannot be made readable" % (parcel,))
            victim = max(candidates, key=lambda w: table[ways[w][0]])
            skip.add(victim)
            dense_drop[ways[victim][0]] = dense_drop.get(ways[victim][0], 0) + 1
            if len(skip) > args.max_drop:
                report["dropped_ways"] = {"total": len(skip), "dense": len(skip) - len(no_slot),
                                          "by_highway": dict(sorted(dense_drop.items()))}
                report["error"] = "drop rule exceeded --max-drop %d" % args.max_drop
                Path(args.report).write_text(json.dumps(report, indent=2))
                return 1

    # M5.71: the parcels this build *declares* it wrote, from OSM alone and
    # independent of --drop-parcel (which only removes ways from the actual
    # build below).  A parcel is declared when it is writable and the writer
    # would emit a record for it from the benign drop set (no-slot / dense,
    # already in ``skip`` here).  Using ``table_only`` (the writer's own
    # ``build_road_record``) keeps the set equal to what the real build emits,
    # so a real build never false-fails on a degenerate parcel.
    def _declared_record(parcel):
        try:
            return table_only(parcel, skip)
        except T.CheckFailed:
            return None

    declared = sorted(
        parcel for parcel in parcel_ways
        if parcel not in unwritable and _declared_record(parcel) is not None
    )
    report["declared_parcels"] = len(declared)
    declared_path = scratch / f"{cell}-L{level}.declared.json"
    declared_path.write_text(json.dumps({
        "format": "ze0-declared-parcels/1",
        "cell": cell, "level": level,
        "parcels": [list(p) for p in declared],
    }), encoding="utf-8")

    # --drop-parcel: the negative control.  It removes that parcel's ways after
    # the declared set is fixed, so the writer sees a declared parcel left at
    # factory and must fail (M5.61 §7 / M5.71).
    if keep_parcel is not None:
        for wid in parcel_ways.get(keep_parcel, ()):
            skip.add(wid)

    # Rebuild the runs the tilewriter will see.
    runs = {}
    for wid, (hw, pieces) in ways.items():
        if wid in skip:
            continue
        for parcel, pseq in pieces:
            if parcel in unwritable:
                continue
            runs.setdefault(parcel, []).append((pseq, hw, ""))
    report["dense_parcels_after"] = sum(1 for p in runs if not check_parcel(p, runs[p]))
    slot_drop: dict[str, int] = {}
    for wid in no_slot:
        slot_drop[ways[wid][0]] = slot_drop.get(ways[wid][0], 0) + 1
    report["dropped_ways"] = {
        "total": len(skip),
        "no_slot": len(no_slot),
        "dense": len(skip) - len(no_slot),
        "by_highway": dict(sorted(dense_drop.items())),
        "no_slot_by_highway": dict(sorted(slot_drop.items())),
    }

    kept = scratch / f"{cell}-L{level}.kept.split.jsonl"
    if not skip:
        shutil.copyfile(single, kept)
    else:
        with kept.open("w", encoding="utf-8", newline="\n") as out:
            for line in single.open(encoding="utf-8"):
                rec = json.loads(line)
                if rec.get("type") == "way" and str(rec["id"]) in skip:
                    continue
                out.write(line)

    factory = Path(args.factory_root) / "MAPAL001" / f"{cell}.DAT"
    rc, so, se = run("tilewriter.py", [str(kept), "--cell", cell,
                                       "--factory", str(factory),
                                       "--class-table", str(ctab),
                                       "--no-names", "--level", str(level),
                                       "--declared-parcels", str(declared_path),
                                       "--out", args.out, "--json"])
    report["tilewriter_rc"] = rc
    if rc != 0:
        report["error"] = (se or so)[-1200:]
        Path(args.report).write_text(json.dumps(report, indent=2))
        print(report["error"], file=sys.stderr)
        return 1
    twr = json.loads(so)
    report["tilewriter"] = {k: twr.get(k) for k in ("size", "sha256", "mode")}
    report["container"] = {k: twr.get("container", {}).get(k)
                           for k in ("in_place", "appended", "superseded_bytes",
                                     "factory_size", "size")}
    report["out_size"] = Path(args.out).stat().st_size
    # "0 parcels left without a slot": the parcels the writer attempted (one
    # readable record each) must all have an even pair in the output.  A parcel
    # OSM never populated keeps the factory's gap and is not in this set.
    missing = []
    written = []
    if level == 2 and twr.get("parcels"):
        written, missing = T.l2_written_without_slot(
            T.read_tile_rows(Path(args.out).read_bytes()), str(kept), cell, table,
            level=2, country=616)
    report["l2_written_parcels"] = len(written)
    report["l2_written_without_slot"] = len(missing)
    report["l2_written_without_slot_list"] = ["%d,%d,%d,%d" % m for m in missing[:50]]
    Path(args.report).write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report.get(k) for k in
                      ("cell", "level", "parcels", "dense_parcels_before",
                       "dense_parcels_after", "dropped_ways", "l2_written_parcels",
                       "l2_written_without_slot", "out_size")},
                     indent=2))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
