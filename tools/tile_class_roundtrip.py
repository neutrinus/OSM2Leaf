#!/usr/bin/env python3
"""tile_class_roundtrip.py - L2 golden for the level-1 road class (M5.36).

``tilewriter.roadclass_v0`` maps an OSM ``highway=*`` to a provisional
Clarion ``(draw layer, shape class nibble)`` pair (``cls_hi = w[p+2] >> 12``)
and writes it into the even ``0x00fa`` road record of a parcel.  Nothing
checked that the class the writer *emitted* is the class the reader *decodes*
back: a wrong table could draw a residential street as a motorway and every
existing gate stayed green.

This tool compares the class list of every road record in a tile with the
class list a writer emitted for that record.  The emitted list is a small JSON
file (``ze0-road-class/1``)::

    {"format": "ze0-road-class/1", "level": 1, "records": [
        {"level": 1, "row": 2451, "col": 13724, "classes": [[7, 1]]}]}

``l2check.py`` looks for ``MAPAL001/<tile>.class.json`` next to the tile, or
takes the map with ``--class-emitted``; without a map the check decodes the
class rows and reports ``decoded``, which is a census and never a PASS.

Writer = ``tilewriter.build_road_record`` / ``fa_encode.build_record``; reader
= ``fa_encode.parse_record`` on the inflated record; the record is located by
``rd_check.rowcol`` (absolute parcel), not by slot.  Only the ``(layer, cls)``
pair is compared: the writer controls it and the reader exposes it.  What the
class *means* to the firmware is M5.3/M4.17 and stays open (rule 13).

Commands::

    tile_class_roundtrip.py check TILE [--emitted CLASSES.json] [--json PATH]
        PASS when every emitted class list is decoded unchanged; FAIL on a
        mismatch or a missing record; ``decoded`` (exit 0) without a map.
    tile_class_roundtrip.py dump TILE --out CLASSES.json
        write the decoded class map (a census, for inspecting a real tile).
    tile_class_roundtrip.py from-imf IMF --cell BxxRyyR [--class-table T]
            --out CLASSES.json
        build the emitted class map from the writer's own input (the split
        JSONL and the class table), the inverse of ``tilewriter`` at the
        class level; feed it to ``check --emitted``.
    tile_class_roundtrip.py mutate CLASSES.json --out OUT.json
        negative control: change the first emitted class by one value.
    tile_class_roundtrip.py --selftest

Exit codes: 0 PASS/decoded, 1 FAIL, 2 usage.  Read-only on its inputs.
"""
from __future__ import annotations

import argparse
import collections
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "ze0-viewer", "tools_ze0"))
sys.path.insert(0, HERE)
import fa_encode  # noqa: E402
import rd_check  # noqa: E402
from tile_scan import TileScan  # noqa: E402

FORMAT = "ze0-road-class/1"
ROAD_TAG = 0x00FA
LEVELS = (1, 2)
#: not compared and not claimed: the class does not say which highway it came from
UNKNOWN = ("the OSM highway behind a decoded class",
           "what the class means to the firmware (M5.3/M4.17)")


def _rec_classes(plain: bytes, level: int):
    """``((row, col), [(layer, cls), ...])`` for one inflated 0x00fa record."""
    code, _unit, shapes = fa_encode.parse_record(plain, level)
    return rd_check.rowcol(level, *code), [(s["layer"], s["cls"]) for s in shapes]


def extract_tile(tile, levels=LEVELS):
    """``{ (level, row, col): [[layer, cls], ...] }`` plus per-level stats.

    Only even (road-pair) records are read; an odd partner is the background
    record and carries no road class.  Records that do not inflate or parse
    are counted, not hidden: a caller comparing an emitted map will report its
    own missing record.
    """
    records = {}
    stats = collections.Counter()
    classes = collections.Counter()
    with TileScan(tile) as t:
        for level in levels:
            for rec in t.records(section=1, level=level):
                if rec.k % 2:
                    continue
                stats["records_raw"] += 1
                try:
                    plain = rec.plain()
                except Exception:  # noqa: BLE001 - a corrupt stream is data
                    stats["inflate_error"] += 1
                    continue
                if len(plain) < 6 or plain[4:6] != ROAD_TAG.to_bytes(2, "big"):
                    continue
                try:
                    key, cls = _rec_classes(plain, level)
                except Exception:  # noqa: BLE001 - a foreign 0x00fa body
                    stats["parse_error"] += 1
                    continue
                if not cls:
                    stats["empty"] += 1
                    continue
                full = (level, key[0], key[1])
                if full in records:
                    stats["duplicate_parcel"] += 1
                    continue
                records[full] = cls
                stats["records"] += 1
                stats["shapes"] += len(cls)
                for pair in cls:
                    classes["%d/%d" % pair] += 1
    stats["classes"] = dict(sorted(classes.items()))
    return records, dict(stats)


def load_expected(path):
    """``{(level,row,col): [[layer,cls],...]}`` from a ``ze0-road-class/1`` file."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("format") != FORMAT:
        raise ValueError("%s: format %r, want %r" % (path, data.get("format"), FORMAT))
    out = {}
    for rec in data["records"]:
        key = (int(rec["level"]), int(rec["row"]), int(rec["col"]))
        cls = [[int(pair[0]), int(pair[1])] for pair in rec["classes"]]
        if key in out:
            raise ValueError("%s: duplicate record %r" % (path, key))
        out[key] = cls
    return out


def dump_expected(path, records, cell=None, level=1):
    recs = [dict(level=k[0], row=k[1], col=k[2],
                 classes=[[int(a), int(b)] for a, b in v])
            for k, v in sorted(records.items())]
    doc = dict(format=FORMAT, cell=cell, level=level, records=recs)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=2)
        handle.write("\n")
    return doc


def compare(expected, decoded):
    """Human-readable differences between an emitted and a decoded class map."""
    diffs = []
    for key in sorted(expected):
        want = sorted(tuple(pair) for pair in expected[key])
        got = decoded.get(key)
        if got is None:
            diffs.append("%r: emitted record not found in the tile" % (key,))
        elif sorted(tuple(pair) for pair in got) != want:
            diffs.append("%r: classes decoded %s != emitted %s"
                         % (key, sorted(tuple(pair) for pair in got), want))
    return diffs


def check_tile(tile, expected=None):
    """The tile_class_roundtrip verdict for one tile (see the module doc)."""
    res = dict(tile=os.path.basename(str(tile)), verdict="decoded", records=0,
               shapes=0, match=0, fail=0, missing=0, classes={}, errors=[])
    decoded, stats = extract_tile(tile)
    res.update(stats)
    if expected is None:
        if not decoded:
            res["errors"].append("no road record with a class decoded")
        return res
    diffs = compare(expected, decoded)
    res["missing"] = sum(1 for d in diffs if "not found" in d)
    res["fail"] = sum(1 for d in diffs if "not found" not in d)
    res["match"] = len(expected) - len(diffs)
    if diffs:
        res["verdict"] = "FAIL"
        res["errors"] = diffs
    elif not expected:
        res["verdict"] = "FAIL"
        res["errors"].append("emitted class map is empty")
    else:
        res["verdict"] = "PASS"
    return res


def mutate(records):
    """A copy of an emitted class map with the first class changed by one value."""
    out = copy.deepcopy(records)
    for key in sorted(out):
        if out[key] and out[key][0]:
            layer, cls = out[key][0][0], out[key][0][1]
            out[key][0] = [layer, (cls % 15) + 1]
            break
    return out


def emitted_from_imf(imf_path, cell, class_table_path=None):
    """The class map ``tilewriter`` would emit for ``imf_path`` in ``cell``.

    Built from the writer's own input (``ways_to_runs`` + ``layer_class``), not
    from the tile: the parcel is the same, and the shape order follows the
    run order, so a ``check`` against the tile is an independent read-back of
    the writer's decision.
    """
    import clarion_bg  # noqa: PLC0415
    import tilewriter  # noqa: PLC0415

    table, source = tilewriter.load_class_table(class_table_path)
    ways, _stats = tilewriter.load_imf(imf_path, cell)
    runs = tilewriter.ways_to_runs(ways, 1, table, cell)
    out = {}
    for parcel, parcel_runs in runs.items():
        y0, x0, row, col = parcel
        lon0, lat0, width, height = clarion_bg.parcel_geo(1, y0, x0, row, col)
        classes = []
        for run in parcel_runs:
            points, highway, _name = tilewriter._run_fields(run)
            local = []
            for lon, lat in points:
                xy = tilewriter.quantise(lon, lat, lon0, lat0, width, height)
                if local and local[-1] == xy:
                    continue
                local.append(xy)
            if len(local) < 2:
                continue
            classes.append(list(fa_encode.layer_class(highway, 1)))
        if not classes:
            continue
        code = clarion_bg.parcel_code(1, y0 * 32 + row, x0 * 32 + col)
        row_a, col_a = rd_check.rowcol(1, *code)
        out[(1, row_a, col_a)] = classes
    return out, source


# ---------------------------------------------------------------------------
# self-test (synthetic, no vendor data)


def selftest() -> int:
    import tempfile
    from pathlib import Path

    import tilewriter as tw

    fails = 0

    def ok(cond, msg):
        nonlocal fails
        print(("  ok   " if cond else "  FAIL ") + msg)
        if not cond:
            fails += 1

    cell = "B48R058R"
    table, _src = tw.load_class_table(None)
    specs = [("motorway", 76, 940, 19, 28), ("service", 76, 940, 19, 27),
             ("residential", 76, 940, 20, 28)]
    expected = {}
    built = {}
    for highway, y0, x0, row, col in specs:
        import clarion_bg
        lon0, lat0, width, height = clarion_bg.parcel_geo(1, y0, x0, row, col)
        points = [(lon0 + width * 0.1, lat0 + height * 0.1),
                  (lon0 + width * 0.6, lat0 + height * 0.6)]
        plain, comp, _names, _info = tw.build_road_record(
            1, (y0, x0, row, col), [(points, highway, "")], table, 616,
            write_names=False)
        built[(y0, x0, row, col)] = dict(plain=plain, comp=comp, names_sec=None)
        layer, cls = fa_encode.layer_class(highway, 1)
        abscol = ((x0 * 32 + col) & 0x3fff)
        expected[(1, y0 * 32 + row, abscol)] = [[layer, cls]]
    blob = tw.synthetic_tile(built, 1, cell, "11/01/01/01")
    with tempfile.TemporaryDirectory(prefix="tcr-") as tmp:
        tile = Path(tmp) / (cell + ".DAT")
        tile.write_bytes(blob)
        side = Path(tmp) / (cell + ".class.json")
        dump_expected(side, expected, cell=cell)
        loaded = load_expected(side)
        ok(loaded == {k: [list(p) for p in v] for k, v in expected.items()},
           "expected map survives dump/load")
        res = check_tile(tile, expected)
        ok(res["verdict"] == "PASS" and res["records"] == len(specs),
           "emitted classes round-trip: %s (%d/%d)"
           % (res["verdict"], res["match"], len(expected)))
        ok(res["classes"] == {"4/9": 1, "5/8": 1, "7/1": 1}, "class census %s" % res["classes"])
        bad = mutate(expected)
        ok(bad != expected, "mutant changed one class")
        res_bad = check_tile(tile, bad)
        ok(res_bad["verdict"] == "FAIL" and res_bad["fail"] == 1,
           "one-value class mutant -> FAIL (%d fail)" % res_bad["fail"])
        census = check_tile(tile)
        ok(census["verdict"] == "decoded" and census["records"] == len(specs),
           "no emitted map -> decoded census, never PASS")
    if fails:
        print(f"tile_class_roundtrip selftest: FAIL ({fails} failure(s))")
        return 1
    print("tile_class_roundtrip selftest: OK (0 failure(s))")
    return 0


# ---------------------------------------------------------------------------
# CLI


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", nargs="?",
                        choices=("check", "dump", "from-imf", "mutate"))
    parser.add_argument("tile", nargs="?")
    parser.add_argument("--emitted", help="emitted class map (ze0-road-class/1)")
    parser.add_argument("--out", help="output path for dump / from-imf")
    parser.add_argument("--cell", help="tile cell for from-imf (BxxRyyR)")
    parser.add_argument("--class-table", help="class table for from-imf")
    parser.add_argument("--json", help="write the result JSON to this path")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.command or not args.tile:
        parser.error("a command and an input are required (check | dump | from-imf | mutate)")
    if not os.path.isfile(args.tile):
        print("error: %s is not a file" % args.tile, file=sys.stderr)
        return 2
    if args.command == "dump":
        if not args.out:
            parser.error("dump needs --out")
        records, stats = extract_tile(args.tile)
        dump_expected(args.out, records, cell=os.path.basename(args.tile).split(".")[0])
        print("%s: %d record(s), %d shape(s), classes %s"
              % (os.path.basename(args.tile), stats["records"], stats["shapes"],
                 stats.get("classes", {})))
        return 0
    if args.command == "from-imf":
        if not args.out or not args.cell:
            parser.error("from-imf needs --out and --cell")
        records, source = emitted_from_imf(args.tile, args.cell, args.class_table)
        dump_expected(args.out, records, cell=args.cell)
        print("%s: %d parcel(s), %d shape(s); class table %s"
              % (os.path.basename(args.tile), len(records),
                 sum(len(v) for v in records.values()), source))
        return 0
    if args.command == "mutate":
        if not args.out:
            parser.error("mutate needs --out")
        expected = load_expected(args.tile)
        bad = mutate(expected)
        dump_expected(args.out, bad, cell="mutant")
        print("%s: %d record(s); first class changed by one value"
              % (os.path.basename(args.tile), len(bad)))
        return 0
    expected = load_expected(args.emitted) if args.emitted else None
    res = check_tile(args.tile, expected)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(res, handle, indent=2)
            handle.write("\n")
    print("%s: %s records=%d shapes=%d match=%d fail=%d missing=%d"
          % (res["tile"], res["verdict"], res["records"], res["shapes"],
             res["match"], res["fail"], res["missing"]))
    for err in res["errors"][:10]:
        print("  ERROR %s" % err)
    return 0 if res["verdict"] in ("PASS", "decoded") else 1


if __name__ == "__main__":
    raise SystemExit(main())
