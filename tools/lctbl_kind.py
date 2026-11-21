#!/usr/bin/env python3
"""What the LCTBL001 ``kind code`` (``class_code`` of M4.17) encodes (M4.35).

Field 0 of an ``LCTBL001.DAT`` record -- the two bytes ``lctbl_records.py``
calls ``class_code`` and the in-file column dictionary calls ``kind code`` --
is tested here as the TMC location type of the record:

    kind = 10000 * class + 100 * type + subtype
    class 0 = area (A), 1 = linear (L), 2 = point (P)

so ``10101`` is L1.1 (motorway), ``10102`` L1.2 (first class road), ``20103``
P1.3 (motorway junction), ``100`` A1.0 (continent).

Three checks that need no OSM data:

``census``     every kind code splits into class 0..2 / type / subtype; the
               reference columns obey the class: ``liner ref`` points at a
               class-1 record, ``area ref`` at a class-0 record, the
               negative/positive offsets at a record of the record's own
               class.  Control: the same test with the kind codes permuted
               inside each table.
``roadclass``  an independent class label: the syntax of the road number.
               In Czechia ``D``/``I/``/``II/``/``III/`` is the legal road
               class, in Germany ``A``/``B``/``L``|``S``/``K``, in the UK
               ``M``/``A``, in the USA ``I-``/``US-``/``CR-``.  Counts how
               many L1.x records carry the subtype their number predicts.
               Control: permuted kind codes.
``kinds``      the kind codes of a file with counts.

Usage:
  python3 tools/lctbl_kind.py --selftest
  python3 tools/lctbl_kind.py census LCTBL001.DAT [--json OUT]
  python3 tools/lctbl_kind.py roadclass LCTBL001.DAT --market eu|us
  python3 tools/lctbl_kind.py kinds LCTBL001.DAT

Get the file with ``python3 tools/lctbl_lookup_l3.py extract --card-image CARD
-o LCTBL001.DAT`` (vendor data, never commit).  Read-only.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lctbl_build  # noqa: E402

F_KIND, F_ROADNO, F_AREA, F_LINEAR, F_NEG, F_POS, F_EXIT = 0, 1, 5, 6, 7, 8, 10
CLASS_NAME = {0: "A (area)", 1: "L (linear)", 2: "P (point)"}
SEED = 20261120

# Names of the location types met most often (EN ISO 14819-3 location type
# table, quoted from memory: a reading aid, not evidence).
KIND_NAME = {
    (0, 1, 0): "continent", (0, 2, 0): "country group", (0, 3, 0): "country",
    (0, 7, 0): "order 1 area", (0, 8, 0): "order 2 area", (0, 9, 0): "order 3 area",
    (0, 10, 0): "order 4 area", (0, 11, 0): "order 5 area",
    (1, 1, 0): "road", (1, 1, 1): "motorway", (1, 1, 2): "first class road",
    (1, 1, 3): "second class road", (1, 1, 4): "third class road",
    (1, 2, 0): "ring road", (1, 3, 0): "order 1 segment", (1, 4, 0): "order 2 segment",
    (1, 5, 0): "urban street", (1, 6, 1): "ferry", (1, 6, 2): "vehicular rail link",
    (2, 1, 1): "motorway intersection", (2, 1, 2): "motorway triangle",
    (2, 1, 3): "motorway junction", (2, 1, 4): "motorway exit", (2, 1, 5): "motorway entrance",
    (2, 1, 8): "roundabout", (2, 1, 11): "cross-roads", (2, 1, 12): "T-junction",
    (2, 3, 1): "tunnel", (2, 3, 2): "bridge", (2, 3, 3): "service area", (2, 3, 4): "rest area",
    (2, 3, 14): "border", (2, 3, 16): "toll plaza", (2, 3, 17): "ferry terminal",
    (2, 3, 27): "airport", (2, 3, 28): "station", (2, 3, 29): "hospital",
}

# market -> country digit (high byte of the table code, ASCII) -> [(regex, L1 subtype)]
ROAD_RULES = {
    "eu": {
        "2": ("Czechia", [(r"^D\d", 1), (r"^I/", 2), (r"^II/", 3), (r"^III/", 4)]),
        "D": ("Germany", [(r"^A\d", 1), (r"^B\d", 2), (r"^[LS]\d", 3), (r"^K ?\d", 4)]),
        "C": ("United Kingdom", [(r"^M\d", 1), (r"^A\d+$", 2)]),
    },
    "us": {
        "1": ("USA", [(r"^I-", 1), (r"^US-", 2), (r"^CR-", 4)]),
    },
}


class KindError(ValueError):
    pass


def split_kind(kind: int) -> tuple[int, int, int]:
    return kind // 10000, kind // 100 % 100, kind % 100


def load_tables(path: Path) -> list[dict]:
    """``[{code, country, records: {location code: 12 fields}}]`` of a file."""
    model = lctbl_build.parse(Path(path).read_bytes())
    out = []
    for table in model["tables"]:
        recs = {}
        for code, rec in zip(table["codes"], table["records"]):
            recs[code] = lctbl_build.decode_record(rec) if isinstance(rec, (bytes, bytearray)) else list(rec)
        out.append({"code": table["code"], "country": chr(table["code"] >> 8), "records": recs})
    return out


def permuted(tables: list[dict], seed: int = SEED) -> list[dict]:
    """The same tables with the kind codes shuffled among the records of each."""
    rng = random.Random(seed)
    out = []
    for table in tables:
        codes = sorted(table["records"])
        kinds = [table["records"][c][F_KIND] for c in codes]
        rng.shuffle(kinds)
        recs = {}
        for code, kind in zip(codes, kinds):
            fields = list(table["records"][code])
            fields[F_KIND] = kind
            recs[code] = fields
        out.append({**table, "records": recs})
    return out


def census(tables: list[dict]) -> dict:
    kinds = Counter()
    classes = Counter()
    invalid = 0
    refs = {name: Counter() for name in ("linear", "area", "offset")}
    road = Counter()
    exits = Counter()
    for table in tables:
        recs = table["records"]
        for fields in recs.values():
            kind = fields[F_KIND]
            if not isinstance(kind, int):
                invalid += 1
                continue
            cls, typ, sub = split_kind(kind)
            if cls not in CLASS_NAME or typ == 0:
                invalid += 1
                continue
            kinds[(cls, typ, sub)] += 1
            classes[cls] += 1
            road[(cls, fields[F_ROADNO] is not None)] += 1
            exits[((cls, typ, sub) in ((2, 1, 3), (2, 1, 4), (2, 4, 0)), fields[F_EXIT] is not None)] += 1
            for name, idxs, want in (("linear", (F_LINEAR,), 1), ("area", (F_AREA,), 0),
                                     ("offset", (F_NEG, F_POS), cls)):
                for idx in idxs:
                    ref = fields[idx]
                    if ref is None:
                        refs[name]["absent"] += 1
                    elif ref not in recs or not isinstance(recs[ref][F_KIND], int):
                        refs[name]["not in table"] += 1
                    elif split_kind(recs[ref][F_KIND])[0] == want:
                        refs[name]["class as expected"] += 1
                    else:
                        refs[name]["other class"] += 1
    return {"records": sum(len(t["records"]) for t in tables), "tables": len(tables),
            "invalid": invalid, "classes": {CLASS_NAME[c]: n for c, n in sorted(classes.items())},
            "distinct_kinds": len(kinds), "kinds": {f"{c}.{t}.{s}": n for (c, t, s), n in sorted(kinds.items())},
            "refs": {k: dict(v) for k, v in refs.items()},
            "road_number": {CLASS_NAME[c]: [road[(c, True)], road[(c, True)] + road[(c, False)]]
                            for c in sorted(classes)},
            "exit_number": {"junction/exit kinds": [exits[(True, True)], exits[(True, True)] + exits[(True, False)]],
                            "other kinds": [exits[(False, True)], exits[(False, True)] + exits[(False, False)]]}}


def ref_rate(report: dict) -> tuple[int, int]:
    good = sum(v.get("class as expected", 0) for v in report["refs"].values())
    bad = sum(v.get("other class", 0) for v in report["refs"].values())
    return good, good + bad


def roadclass(tables: list[dict], market: str) -> dict:
    out = {}
    for digit, (country, rules) in ROAD_RULES[market].items():
        compiled = [(re.compile(rx), sub) for rx, sub in rules]
        matrix = Counter()
        for table in tables:
            if table["country"] != digit:
                continue
            for fields in table["records"].values():
                kind, number = fields[F_KIND], fields[F_ROADNO]
                if not isinstance(kind, int) or not number:
                    continue
                cls, typ, sub = split_kind(kind)
                if (cls, typ) != (1, 1):
                    continue
                for rx, want in compiled:
                    if rx.search(number):
                        matrix[(want, sub)] += 1
                        break
        total = sum(matrix.values())
        agree = sum(n for (want, sub), n in matrix.items() if want == sub)
        out[country] = {"labelled": total, "agree": agree,
                        "matrix": {f"number says L1.{w} / kind L1.{s}": n for (w, s), n in sorted(matrix.items())}}
    return out


def cmd_census(args) -> int:
    tables = load_tables(args.file)
    rep = census(tables)
    ctl = census(permuted(tables))
    print(f"tables: {rep['tables']}   records: {rep['records']:,}   distinct kind codes: {rep['distinct_kinds']}   "
          f"not class 0..2 / type >= 1: {rep['invalid']}")
    for name, n in rep["classes"].items():
        print(f"  class {name}: {n:,}")
    for name in ("linear", "area", "offset"):
        want = {"linear": "class 1", "area": "class 0", "offset": "the record's own class"}[name]
        r, c = rep["refs"][name], ctl["refs"][name]
        print(f"  {name} reference -> {want}: {r.get('class as expected', 0):,}, other class "
              f"{r.get('other class', 0):,}, not in table {r.get('not in table', 0):,}, absent {r.get('absent', 0):,}"
              f"   | permuted kinds: {c.get('class as expected', 0):,} / other class {c.get('other class', 0):,}")
    for name, (have, total) in rep["road_number"].items():
        print(f"  road number present, class {name}: {have:,}/{total:,}")
    for name, (have, total) in rep["exit_number"].items():
        print(f"  exit/junction number present, {name}: {have:,}/{total:,}")
    good, total = ref_rate(rep)
    cgood, ctotal = ref_rate(ctl)
    print(f"references that obey the class: {good:,}/{total:,}; with permuted kind codes {cgood:,}/{ctotal:,}")
    if args.json:
        Path(args.json).write_text(json.dumps({"report": rep, "control": ctl}, indent=1) + "\n")
    ok = rep["invalid"] == 0 and total > 0 and good == total and cgood < 0.9 * ctotal
    print("VERDICT: " + ("kind code = TMC class / type / subtype holds" if ok else "FAIL"))
    return 0 if ok else 1


def cmd_roadclass(args) -> int:
    tables = load_tables(args.file)
    rep = roadclass(tables, args.market)
    ctl = roadclass(permuted(tables), args.market)
    agree = total = cagree = ctotal = 0
    for country, row in rep.items():
        print(f"{country}: {row['agree']:,}/{row['labelled']:,} L1.x records carry the subtype their road number "
              f"predicts; permuted kinds {ctl[country]['agree']:,}/{ctl[country]['labelled']:,}")
        for key, n in row["matrix"].items():
            print(f"    {key}: {n:,}")
        agree += row["agree"]
        total += row["labelled"]
        cagree += ctl[country]["agree"]
        ctotal += ctl[country]["labelled"]
    print(f"total: {agree:,}/{total:,}; permuted kinds {cagree:,}/{ctotal:,}")
    ok = total >= 100 and agree >= 0.95 * total and cagree < 0.6 * max(ctotal, 1)
    print("VERDICT: " + ("road-number class agrees with the kind subtype" if ok else "FAIL"))
    return 0 if ok else 1


def cmd_kinds(args) -> int:
    rep = census(load_tables(args.file))
    for key, n in rep["kinds"].items():
        cls, typ, sub = (int(x) for x in key.split("."))
        label = "ALP"[cls] + f"{typ}.{sub}"
        print(f"{10000 * cls + 100 * typ + sub:6d}  {label:<7} {n:>8,}  {KIND_NAME.get((cls, typ, sub), '')}")
    return 0


# ---------------------------------------------------------------------------


def _fields(kind, number=None, area=None, linear=None, neg=None, pos=None, exit_no=None):
    return [kind, number, None, "X", None, area, linear, neg, pos, None, exit_no, None]


def _synthetic() -> list[dict]:
    recs = {
        1: _fields(100),                                   # A1.0
        2: _fields(300, area=1),                           # A3.0
        10: _fields(10101, "D1", area=2),                  # L1.1
        11: _fields(10102, "I/3", area=2),
        12: _fields(10103, "II/101", area=2),
        13: _fields(10104, "III/1011", area=2),
        20: _fields(20103, area=2, linear=10, pos=21, exit_no="1"),
        21: _fields(20103, area=2, linear=10, neg=20, pos=22, exit_no="2"),
        22: _fields(20111, area=2, linear=11, neg=21),
    }
    for i in range(30, 70):                                 # enough rows for the rate tests
        recs[i] = _fields(10104 if i % 2 else 10103, "III/%d" % i if i % 2 else "II/%d" % i, area=2)
    for i in range(70, 130):
        recs[i] = _fields(20111, area=2, linear=12, neg=i - 1 if i > 70 else None)
    return [{"code": 0x3219, "country": "2", "records": recs}]


def selftest() -> int:
    fails = []

    def ok(cond: bool, label: str) -> None:
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    ok(split_kind(10101) == (1, 1, 1) and split_kind(20311) == (2, 3, 11) and split_kind(100) == (0, 1, 0),
       "split_kind")
    tables = _synthetic()
    rep = census(tables)
    good, total = ref_rate(rep)
    ok(rep["invalid"] == 0 and good == total and total > 100, f"synthetic table: {good}/{total} references obey the class")
    ctl = census(permuted(tables))
    cgood, ctotal = ref_rate(ctl)
    ok(cgood < 0.9 * ctotal, f"negative: permuted kind codes break the references ({cgood}/{ctotal})")
    ok(rep["exit_number"]["junction/exit kinds"] == [2, 2] and rep["exit_number"]["other kinds"][0] == 0,
       "exit numbers sit on junction kinds only")
    rc = roadclass(tables, "eu")["Czechia"]
    ok(rc["labelled"] == 44 and rc["agree"] == 44, "road-number rule agrees on the synthetic table")
    rcc = roadclass(permuted(tables), "eu")["Czechia"]
    ok(rcc["agree"] < rcc["labelled"], "negative: permuted kinds disagree with the road numbers")
    bad = [{"code": 0x3219, "country": "2", "records": {1: _fields(30101), 2: _fields(7)}}]
    ok(census(bad)["invalid"] == 2, "negative: class 3 and type 0 are counted as invalid")
    # a record written by lctbl_build and read back keeps field 0 at bytes 14..15
    raw = lctbl_build.encode_record(_fields(10101, "D1", area=2))
    ok(int.from_bytes(raw[14:16], "big") == 10101 and lctbl_build.decode_record(raw)[F_KIND] == 10101,
       "field 0 is bytes 14..15 of a record (class_code of lctbl_records.py)")
    print("lctbl_kind selftest: " + ("OK" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("census")
    c.add_argument("file")
    c.add_argument("--json")
    c.set_defaults(func=cmd_census)
    r = sub.add_parser("roadclass")
    r.add_argument("file")
    r.add_argument("--market", choices=sorted(ROAD_RULES), required=True)
    r.set_defaults(func=cmd_roadclass)
    k = sub.add_parser("kinds")
    k.add_argument("file")
    k.set_defaults(func=cmd_kinds)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmd:
        ap.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
