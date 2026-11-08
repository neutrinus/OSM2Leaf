#!/usr/bin/env python3
"""Probe LCTBL001 record fields for a road-class signal against OSM (M4.17).

``LCTBL001.DAT`` records carry a road number in name slot 1 (``names[0]``,
"field 1" in ``docs/format/rdstm.md``).  A road number that also appears as an
OSM ``ref`` gives a road of known class without any coordinates.  This tool:

1. joins numbered LCTBL records to OSM ways by normalised ``ref``
   (spaces and hyphens removed, upper case); only refs whose ways agree on one
   ``highway`` value for at least ``--min-share`` of the ways are used;
2. tests each candidate record field (header class code, size, slot lengths,
   the seven attribute bytes, footer length and leading bytes) against the OSM
   class in two ways:
   * **leave-one-road-out (LORO)**: a record is predicted from the classes of
     the *other* roads that share its field value.  A field that only names
     the road (a per-road identifier) scores high in-sample and low here.
   * **permutation null**: the in-sample majority-vote accuracy against the
     same accuracy with the road labels shuffled (``--perms``, seed 42).
3. reports the unnumbered-street control (records with a name but no road
   number) so the field values can be compared with non-road records.

What it does not do: it does not assert that a field is a road class.  The
country of a record is not stored, so an EU-wide road number may be matched to
a Dolnoslaskie OSM way of the same number in another country; the output
carries that caveat.  Stdlib only; no vendor data is written.

Usage::

    road_class_probe.py LCTBL001.DAT --imf dolnoslaskie.imf.jsonl
    road_class_probe.py LCTBL001.DAT --imf region.imf.jsonl --json
    road_class_probe.py --selftest

Exit codes: ``0`` ok, ``1`` a selftest or input check failed, ``2`` usage or
I/O error.
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import re
import sys
from pathlib import Path
from typing import Callable, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lctbl_records  # noqa: E402  (sibling tool: LCTBL001 record parser)

ROAD_SLOT = 0
PRIMARY_SLOT = 2


def norm_ref(text: str) -> str:
    """Normalise a road number: drop spaces and hyphens, upper-case."""
    return re.sub(r"[\s\-]", "", text).upper()


def osm_ref_classes(ways: Iterable[dict]) -> dict[str, collections.Counter]:
    """Map each normalised ``ref`` to a Counter of ``highway`` values."""
    out: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for way in ways:
        tags = way.get("tags", {})
        if "ref" not in tags or "highway" not in tags:
            continue
        for part in tags["ref"].split(";"):
            out[norm_ref(part)][tags["highway"]] += 1
    return out


def ref_label(counter: collections.Counter, min_share: float) -> str | None:
    """Majority ``highway`` of a ref if it reaches ``min_share``, else None."""
    if not counter:
        return None
    top, n = counter.most_common(1)[0]
    return top if n / sum(counter.values()) >= min_share else None


def join_roads(records: list[dict], osm: dict[str, collections.Counter],
               min_share: float) -> tuple[list[tuple[str, str, dict]], list[dict]]:
    """Return (labelled rows of (road, class, record), unnumbered control rows)."""
    labelled: list[tuple[str, str, dict]] = []
    control: list[dict] = []
    for record in records:
        raw = record["names"][ROAD_SLOT]
        if not raw:
            if record["names"][PRIMARY_SLOT]:
                control.append(record)
            continue
        road = norm_ref(raw.decode("latin-1"))
        label = ref_label(osm.get(road, collections.Counter()), min_share)
        if label is not None:
            labelled.append((road, label, record))
    return labelled, control


def candidate_fields() -> dict[str, Callable[[dict], object]]:
    fields: dict[str, Callable[[dict], object]] = {
        "class_code": lambda r: r["class_code"],
        "size_words": lambda r: r["size_words"],
        "slot_lengths": lambda r: tuple(r["lengths"]),
        "footer_len": lambda r: len(r["footer"]),
        "footer[0]": lambda r: r["footer"][:1],
        "footer[:2]": lambda r: r["footer"][:2],
        "attrs": lambda r: bytes(r["attrs"]),
    }
    for i in range(7):
        fields[f"attr[{i}]"] = (lambda i: lambda r: r["attrs"][i])(i)
    return fields


def loro_accuracy(rows: list[tuple[str, str, dict]],
                  fn: Callable[[dict], object]) -> float | None:
    """Leave-one-road-out vote accuracy over labelled rows (None if no votes)."""
    by_value: dict[object, collections.Counter] = collections.defaultdict(collections.Counter)
    for road, label, record in rows:
        by_value[fn(record)][(road, label)] += 1
    correct = scored = 0
    for road, label, record in rows:
        votes: collections.Counter = collections.Counter()
        for (other, other_label), _ in by_value[fn(record)].items():
            if other != road:
                votes[other_label] += 1
        if votes:
            scored += 1
            correct += votes.most_common(1)[0][0] == label
    return correct / scored if scored else None


def loro_null(rows: list[tuple[str, str, dict]], fn: Callable[[dict], object],
              perms: int, seed: int = 42) -> tuple[float | None, float | None]:
    """LORO accuracy with the class labels shuffled across roads (one label per road)."""
    road_label = {road: label for road, label, _ in rows}
    roads = sorted(road_label)
    labels = [road_label[road] for road in roads]
    rnd = random.Random(seed)
    accs = []
    for _ in range(perms):
        rnd.shuffle(labels)
        shuffled = dict(zip(roads, labels))
        acc = loro_accuracy([(road, shuffled[road], record) for road, _, record in rows], fn)
        if acc is not None:
            accs.append(acc)
    if not accs:
        return None, None
    mean = sum(accs) / len(accs)
    return mean, (sum((a - mean) ** 2 for a in accs) / len(accs)) ** 0.5


def insample_accuracy(labels: list[str], values: list[object]) -> float:
    by_value: dict[object, collections.Counter] = collections.defaultdict(collections.Counter)
    for value, label in zip(values, labels):
        by_value[value][label] += 1
    return sum(c.most_common(1)[0][1] for c in by_value.values()) / len(labels)


def permutation_null(labels: list[str], values: list[object], perms: int,
                     seed: int = 42) -> tuple[float, float]:
    rnd = random.Random(seed)
    shuffled = list(labels)
    accs = []
    for _ in range(perms):
        rnd.shuffle(shuffled)
        accs.append(insample_accuracy(shuffled, values))
    mean = sum(accs) / len(accs)
    sd = (sum((a - mean) ** 2 for a in accs) / len(accs)) ** 0.5
    return mean, sd


def probe(records: list[dict], osm_ways: Iterable[dict], *, min_share: float = 0.9,
          perms: int = 50) -> dict:
    osm = osm_ref_classes(osm_ways)
    labelled, control = join_roads(records, osm, min_share)
    labels = [label for _, label, _ in labelled]
    per_road = collections.defaultdict(collections.Counter)
    for road, label, _ in labelled:
        per_road[road][label] += 1
    fields = {}
    for name, fn in candidate_fields().items():
        values = [fn(record) for _, _, record in labelled]
        acc = insample_accuracy(labels, values) if labelled else None
        mean, sd = permutation_null(labels, values, perms) if labelled else (None, None)
        loro = loro_accuracy(labelled, fn)
        loro_mean, loro_sd = loro_null(labelled, fn, perms) if labelled else (None, None)
        fields[name] = {
            "insample": acc,
            "null_mean": mean,
            "null_sd": sd,
            "loro": loro,
            "loro_null_mean": loro_mean,
            "loro_null_sd": loro_sd,
            "distinct": len(set(values)),
        }
    return {
        "records": len(records),
        "numbered": sum(1 for r in records if r["names"][ROAD_SLOT]),
        "joined_rows": len(labelled),
        "joined_roads": len(per_road),
        "joined_road_classes": dict(collections.Counter(
            ref_label(osm[road], min_share) for road in per_road)),
        "control_unnumbered": len(control),
        "majority_share": (collections.Counter(labels).most_common(1)[0][1] / len(labels)
                           if labels else None),
        "fields": fields,
        "class_code_by_class": {
            f"{value:#06x}": dict(collections.Counter(
                label for _, label, record in labelled if record["class_code"] == value))
            for value in sorted({record["class_code"] for _, _, record in labelled})
        },
        "per_road": {road: dict(c) for road, c in sorted(per_road.items())},
    }


def _fmt(value: object) -> str:
    return "-" if value is None else (f"{value:.3f}" if isinstance(value, float) else str(value))


def print_report(result: dict) -> None:
    print(f"records {result['records']}  numbered {result['numbered']}  "
          f"joined rows {result['joined_rows']} on {result['joined_roads']} roads  "
          f"unnumbered control {result['control_unnumbered']}")
    print(f"row-weighted majority share (baseline) {_fmt(result['majority_share'])}")
    print("OSM classes of joined roads:", result["joined_road_classes"])
    print(f"{'field':14s} {'in-sample':>9s} {'null':>7s} {'LORO':>7s} {'LORO null':>9s} {'sd':>6s} {'vals':>5s}")
    for name, f in result["fields"].items():
        print(f"{name:14s} {_fmt(f['insample']):>9s} {_fmt(f['null_mean']):>7s} "
              f"{_fmt(f['loro']):>7s} {_fmt(f['loro_null_mean']):>9s} "
              f"{_fmt(f['loro_null_sd']):>6s} {f['distinct']:>5d}")
    print("class_code x OSM class (joined rows):")
    for value, counts in result["class_code_by_class"].items():
        print(f"  {value}  {counts}")
    print("caveat: country is not stored; a road number may match a same-numbered OSM way abroad")


def _load_inputs(lctbl: Path, imf: Path) -> tuple[list[dict], list[dict]]:
    _, streams = lctbl_records.load_streams(lctbl)
    records = [r for s in streams for r in lctbl_records.parse_stream(s["data"])]
    ways = []
    with imf.open(encoding="utf-8") as handle:
        for line in handle:
            if '"type":"way"' in line:
                ways.append(json.loads(line))
    return records, ways


def _synthetic_records(seed: int = 7) -> tuple[list[dict], list[dict]]:
    """Synthetic records and OSM ways.  Field ``class_code`` tracks the class;
    ``footer`` names the road; ``attrs[0]`` is random.  No vendor data."""
    rnd = random.Random(seed)
    roads = {f"A{n}": "motorway" for n in range(1, 7)}
    roads.update({f"{n}": "primary" for n in range(10, 16)})
    roads.update({f"{n}": "secondary" for n in range(20, 26)})
    ways = []
    for number, highway in roads.items():
        ways.append({"type": "way", "tags": {"ref": number, "highway": highway}})
    records = []
    class_code = {"motorway": 0x0101, "primary": 0x0202, "secondary": 0x0303}
    for index, (number, highway) in enumerate(roads.items()):
        for k in range(5):
            name = number.encode()
            footer_id = index.to_bytes(2, "big") + bytes([k])
            records.append({
                "size_words": 12, "lengths": [len(name) // 2 + 1, 0, 0, 0],
                "names": [name, b"", b"Town", b""], "footer": footer_id,
                "attrs": bytes([rnd.randrange(256)] + [0] * 6),
                "class_code": class_code[highway], "marker": 1,
            })
    for k in range(20):
        records.append({
            "size_words": 12, "lengths": [0, 0, 1, 0], "names": [b"", b"", b"Street", b""],
            "footer": bytes([k]), "attrs": bytes(7), "class_code": 0x0404, "marker": 1,
        })
    return records, ways


def selftest() -> int:
    failures = []

    def check(label: str, ok: bool) -> None:
        print(("PASS " if ok else "FAIL ") + label)
        if not ok:
            failures.append(label)

    records, ways = _synthetic_records()
    res = probe(records, ways, perms=30)
    f = res["fields"]
    check("join: every numbered synthetic road joined (18 roads, 90 rows)",
          res["joined_roads"] == 18 and res["joined_rows"] == 90)
    check("control: unnumbered records counted, not joined", res["control_unnumbered"] == 20)
    check("positive control: class_code LORO = 1.000",
          f["class_code"]["loro"] == 1.0)
    check("positive control: class_code in-sample beats null by > 5 sd",
          f["class_code"]["insample"] > f["class_code"]["null_mean"] + 5 * f["class_code"]["null_sd"])
    check("confound: footer names the road, LORO is None (no other road shares the value)",
          f["footer[:2]"]["loro"] is None)
    check("negative control: random attr[0] LORO below 0.6",
          f["attr[0]"]["loro"] is not None and f["attr[0]"]["loro"] < 0.6)
    check("permutation null sd is positive", f["class_code"]["null_sd"] > 0)
    check("positive control: class_code LORO beats its shuffled-label null",
          f["class_code"]["loro"] > f["class_code"]["loro_null_mean"] + 3 * f["class_code"]["loro_null_sd"])
    check("confound: footer[:2] has no LORO votes in either arm",
          f["footer[:2]"]["loro_null_mean"] is None)
    check("ref normalisation: 'A 4' joins 'A4'",
          norm_ref("A 4") == "A4" and norm_ref("dk-94") == "DK94")
    check("ref_label refuses a split ref below min_share",
          ref_label(collections.Counter({"primary": 1, "trunk": 1}), 0.9) is None)
    print("selftest:", "OK" if not failures else f"FAILED {len(failures)}")
    return 0 if not failures else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("lctbl", nargs="?", type=Path, help="LCTBL001.DAT")
    parser.add_argument("--imf", type=Path, help="IMF JSONL from osm_ingest.py")
    parser.add_argument("--min-share", type=float, default=0.9)
    parser.add_argument("--perms", type=int, default=50)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.lctbl is None or args.imf is None:
        parser.error("LCTBL001.DAT and --imf are required")
    try:
        records, ways = _load_inputs(args.lctbl, args.imf)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    result = probe(records, ways, min_share=args.min_share, perms=args.perms)
    if args.json:
        print(json.dumps(result, indent=2, default=lambda b: b.hex()))
    else:
        print_report(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
