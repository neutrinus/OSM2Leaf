#!/usr/bin/env python3
"""Provisional OSM ``highway=*`` -> Clarion tile class/speed table v0 (M5.28).

Compiler-unblocking, **L2-testable** mapping. It covers every in-scope
``highway=*`` (``osm_ingest.DRIVABLE_HIGHWAYS``) either as an explicit mapped
entry or as explicit ``UNMAPPED`` with ``refuse_generate`` -- never a silent
drop or default.

Rule 13 / Stop-condition honesty: this mapping is **provisional and not
firmware-confirmed**. L2 is necessary, not sufficient; L3/L4/L5 acceptance is
unknown. No M4.2 row key or RDSTM/LCTBL class semantic is claimed (M4.17 is
negative; ``class_code`` is a hypothesis only). M5.23 confirms the
``(layer, cls_hi)`` *mechanism* for level-1 ``0x00fa`` records and that the
five ``fa_encode.CLASSES`` buckets appear in factory data, but OSM->value is
provisional/incomplete (factory has unmapped ``(layer,cls)`` values; global
semantics remain M5.3).

``busway`` and ``road`` are emitted as **provisional placeholders** (option a,
navigator-approved): mapped to a placeholder bucket only to unblock the
compiler/L2, with ``entry_kind=provisional-placeholder``,
``confidence=low-provisional`` and explicit rationale/alternatives
(``UNMAPPED/refuse_generate``). They are **not** equivalent-confidence to the
15 mechanism-confirmed bucket entries and are never presented as
firmware-confirmed.

Consumed by ``tilewriter.py --class-table`` (emits ``ze0-road-class-table/1``)
and by the compiler (importable API).

Usage::

    python3 tools/roadclass_v0.py                 # human report
    python3 tools/roadclass_v0.py --json           # machine-auditable JSON
    python3 tools/roadclass_v0.py --class-table-out /tmp/rc.json
    python3 tools/roadclass_v0.py --check-highway busway
    python3 tools/roadclass_v0.py --selftest

Exit codes: 0 ok, 1 check/selftest failure, 2 usage/input error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
ZE0_DIR = TOOLS_DIR / "ze0-viewer" / "tools_ze0"
for _path in (str(TOOLS_DIR), str(ZE0_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import fa_encode  # noqa: E402  (authoritative copy, same as tilewriter.py)
import osm_ingest  # noqa: E402
import tilewriter  # noqa: E402 (contract/checks; synthetic build in selftest)

MAPPING_VERSION = "provisional-v0"
CLASS_TABLE_FORMAT = tilewriter.CLASS_TABLE_FORMAT  # ze0-road-class-table/1
GENERATOR = "tools/roadclass_v0.py"
FAENCODE_SOURCE = "tools/ze0-viewer/tools_ze0/fa_encode.py"

IN_SCOPE_HIGHWAYS = tuple(sorted(osm_ingest.DRIVABLE_HIGHWAYS))

# M5.4 real-splice precedent: road -> ((5,8),7) (level-1 layer 5, cls 8).
# Chosen only as a compiler-unblocking L2 placeholder; OSM `road` is "unknown
# type" and `busway` has no confirmed Clarion semantic mapping here.
PLACEHOLDER_HIGHWAYS = {
    "road": {
        "layer": 5,
        "cls": 8,
        "rationale": (
            "OSM highway=road means unknown road type (no safe semantic mapping "
            "without inventing semantics; M4.2/M5.3 open, M4.17 negative). "
            "Mapped provisionally to (layer=5,cls=8) unclassified/residential "
            "bucket as a compiler-unblocking L2 placeholder, following M5.4 "
            "real-splice precedent (EXP-2026-11-08-M5.4-splice). NOT "
            "firmware-confirmed; alternative: UNMAPPED/refuse_generate."),
        "alternatives": ["UNMAPPED/refuse_generate", "remap when M5.3/M4.2 resolves"],
    },
    "busway": {
        "layer": 5,
        "cls": 8,
        "rationale": (
            "OSM highway=busway (dedicated bus infrastructure) has no confirmed "
            "Clarion semantic mapping in this repo (M4.2/M5.3 open, M4.17 "
            "negative). Mapped provisionally to (layer=5,cls=8) as a "
            "compiler-unblocking L2 placeholder; no safe semantic mapping chosen "
            "here. NOT firmware-confirmed; alternatives: UNMAPPED/refuse_generate, "
            "(4,9) service-like placeholder, remap when M5.3/M4.2 resolves."),
        "alternatives": [
            "UNMAPPED/refuse_generate",
            "(4,9) service-like placeholder (unverified)",
            "remap when M5.3/M4.2 resolves",
        ],
    },
}

RULE13 = (
    "provisional-v0: NOT firmware-confirmed (rule 13). L2 is necessary, not "
    "sufficient; L3/L4/L5 acceptance unknown. No M4.2 row key and no RDSTM/LCTBL "
    "class semantic claimed (M4.17 negative; class_code hypothesis only). "
    "M5.23 confirms (layer,cls_hi) mechanism and presence of CLASSES buckets in "
    "factory data; OSM->value remains provisional/incomplete (factory unmapped "
    "(layer,cls) values exist; M5.3)."
)


class RoadClassError(ValueError):
    """Bad input / check failure (exit 2 for CLI input errors)."""


def _entry_base(highway: str) -> dict[str, Any]:
    return {
        "mapping": MAPPING_VERSION,
        "highway": highway,
        "in_scope": highway in IN_SCOPE_HIGHWAYS,
        "source": FAENCODE_SOURCE,
        "rule13": RULE13,
    }


def map_highway(
    highway: str,
    *,
    maxspeed_kmh: Any = None,
    maxspeed_cms: Any = None,
    oneway: Any = None,
    access: Any = None,
    tags: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map one OSM highway to a provisional Clarion class/speed result.

    Returns a machine-auditable dict. Unknown/OOS highways yield
    ``status='unmapped'`` and ``refuse_generate=True`` -- never a silent drop.
    """
    tags = tags or {}
    hw = str(highway)
    if maxspeed_kmh is None and "maxspeed_kmh" in tags:
        maxspeed_kmh = tags.get("maxspeed_kmh")
    if oneway is None and "oneway" in tags:
        oneway = tags.get("oneway")
    if access is None and "access" in tags:
        access = tags.get("access")

    entry = _entry_base(hw)

    # Speed/style: mechanism-only, provisional (tilewriter neutral style today;
    # M4.2 semantics open). Never presented as firmware-confirmed.
    speed_limit_kmh = None
    style = None
    if maxspeed_kmh is not None:
        try:
            speed_limit_kmh = fa_encode.speed_limit(str(int(maxspeed_kmh)))
        except Exception:
            speed_limit_kmh = None
    oneway_flag = oneway in ("yes", "-1", True, 1)
    try:
        style = fa_encode.style_word(speed_limit_kmh, oneway=oneway_flag)
    except Exception:
        style = None
    entry["speed_style"] = {
        "provisional": True,
        "mechanism_only": True,
        "maxspeed_kmh_input": maxspeed_kmh,
        "maxspeed_cms_input": maxspeed_cms,
        "speed_limit_kmh": speed_limit_kmh,
        "style_word": style,
        "oneway": oneway,
        "access": access,
        "note": (
            "Derived via fa_encode mechanisms only; tilewriter currently emits "
            "neutral style (M5.4) and style/speed/oneway firmware semantics are "
            "unresolved (M4.2/M5.3). Not firmware-confirmed."
        ),
    }

    if hw in PLACEHOLDER_HIGHWAYS:
        ph = PLACEHOLDER_HIGHWAYS[hw]
        entry.update(
            status="mapped",
            refuse_generate=False,
            entry_kind="provisional-placeholder",
            confidence="low-provisional",
            layer=ph["layer"],
            cls=ph["cls"],
            rationale=ph["rationale"],
            alternatives=list(ph["alternatives"]),
        )
        return entry

    if hw in fa_encode.CLASSES:
        (l1, c1), _c2, _c3 = fa_encode.CLASSES[hw]
        entry.update(
            status="mapped",
            refuse_generate=False,
            entry_kind="mechanism-confirmed-bucket",
            confidence="provisional-mechanism",
            layer=int(l1),
            cls=int(c1),
            rationale=(
                "Level-1 (layer,cls_hi) bucket from authoritative fa_encode.CLASSES "
                "(same source as tilewriter). M5.23 confirms mechanism and that "
                "CLASSES buckets appear in factory data (C-2661); OSM->value "
                "mapping remains provisional/incomplete (C-2662, M5.3). Not "
                "firmware-confirmed (rule 13)."
            ),
            alternatives=["remap when M5.3/M4.2 resolves"],
        )
        return entry

    # Explicit UNMAPPED: never silent drop/default.
    entry.update(
        status="unmapped",
        refuse_generate=True,
        entry_kind="unmapped",
        confidence="none",
        layer=None,
        cls=None,
        rationale=(
            f"highway={hw!r} is not in provisional-v0 in-scope/mapped set; no safe "
            "Clarion value assigned without inventing semantics. Refuse generation "
            "(Stop condition)."
        ),
        alternatives=["add explicit reviewed mapping in a future version"],
    )
    return entry


def all_in_scope_entries() -> list[dict[str, Any]]:
    return [map_highway(hw) for hw in IN_SCOPE_HIGHWAYS]


def class_table_dict() -> dict[str, Any]:
    """Emit tilewriter-compatible ``ze0-road-class-table/1``.

    Includes every mapped in-scope DRIVABLE_HIGHWAY (17 in v0), so
    ``tilewriter --class-table`` has no misses for in-scope roads. UNMAPPED are
    excluded from ``classes`` and reported separately. Extra provenance keys are
    safe (tilewriter reads only format+classes).
    """
    entries = all_in_scope_entries()
    classes = {}
    placeholders = []
    for e in entries:
        if e["status"] == "mapped" and e["layer"] is not None:
            classes[e["highway"]] = [int(e["layer"]), int(e["cls"])]
            if e["entry_kind"] == "provisional-placeholder":
                placeholders.append(e["highway"])
        # UNMAPPED in-scope would be excluded (none in v0); still explicit in report.
    return {
        "format": CLASS_TABLE_FORMAT,
        "mapping": MAPPING_VERSION,
        "generator": GENERATOR,
        "provenance": {
            "mapping": MAPPING_VERSION,
            "rule13": RULE13,
            "faencode_source": FAENCODE_SOURCE,
            "in_scope": list(IN_SCOPE_HIGHWAYS),
            "entry_kinds": {
                "mechanism-confirmed-bucket": (
                    "15 fa_encode.CLASSES highways; mechanism confirmed by M5.23 "
                    "(C-2661), OSM->value provisional/incomplete (C-2662/M5.3)."
                ),
                "provisional-placeholder": (
                    "busway,road only: mapped as low-provisional L2-unblocking "
                    "placeholders, NOT equivalent-confidence; no safe semantic "
                    "mapping (M4.2/M5.3). Alternative UNMAPPED/refuse recorded."
                ),
                "unmapped": "explicit refuse_generate; never in classes.",
            },
            "provisional_placeholders": placeholders,
            "unmapped_policy": "excluded from classes; refuse_generate=true; never silent drop/default",
        },
        "classes": classes,
    }


def report_dict() -> dict[str, Any]:
    entries = all_in_scope_entries()
    mapped = [e for e in entries if e["status"] == "mapped"]
    unmapped = [e for e in entries if e["status"] == "unmapped"]
    placeholders = [e for e in mapped if e["entry_kind"] == "provisional-placeholder"]
    return {
        "tool": GENERATOR,
        "mapping": MAPPING_VERSION,
        "rule13": RULE13,
        "in_scope_count": len(IN_SCOPE_HIGHWAYS),
        "in_scope_highways": list(IN_SCOPE_HIGHWAYS),
        "mapped_count": len(mapped),
        "unmapped_count": len(unmapped),
        "placeholder_count": len(placeholders),
        "all_in_scope_accounted": len(entries) == len(IN_SCOPE_HIGHWAYS)
        and all(e["status"] in ("mapped", "unmapped") for e in entries),
        "placeholders": [e["highway"] for e in placeholders],
        "unmapped_highways": [e["highway"] for e in unmapped],
        "entries": entries,
    }


def _render_text(rep: dict[str, Any]) -> str:
    lines = [
        f"{GENERATOR} mapping={rep['mapping']}",
        "rule13: provisional, NOT firmware-confirmed; L2 necessary not sufficient; L3-L5 unknown; no M4.2 row key.",
        f"in-scope highways: {rep['in_scope_count']}  mapped={rep['mapped_count']}  unmapped={rep['unmapped_count']}  placeholders={rep['placeholder_count']}",
        f"all in-scope accounted: {rep['all_in_scope_accounted']}",
        "",
    ]
    for e in rep["entries"]:
        lc = f"({e['layer']},{e['cls']})" if e["status"] == "mapped" else "UNMAPPED"
        ref = " refuse_generate" if e.get("refuse_generate") else ""
        lines.append(
            f"  {e['highway']:18s} {e['status']:8s} {e['entry_kind']:26s} {lc:10s} conf={e['confidence']}{ref}"
        )
    if rep["unmapped_highways"]:
        lines.append("")
        lines.append("UNMAPPED (refuse generation): " + ", ".join(rep["unmapped_highways"]))
    lines.append("")
    lines.append(
        "placeholders (mapped, low-provisional, NOT firmware-confirmed): "
        + ", ".join(rep["placeholders"])
    )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Selftest (synthetic, no vendor data)
# ---------------------------------------------------------------------------

def _synthetic_imf(cell: str = "B48R058R") -> list[dict[str, Any]]:
    """IMF covering mechanism-confirmed highways + both placeholders in one cell.

    Coordinates are inside tilewriter's synthetic fixture area so parcels are
    populated in a make_factory(B48R058R) tile.
    """
    # Reuse tilewriter fixture base coordinates; add busway/road ways.
    lat0 = 48.0 + 4.0 / 48.0 + 0.2 / 48.0
    lon0 = 12.0 + 3.0 / 32.0 + 0.2 / 32.0
    nodes = [
        ("n1", lat0, lon0),
        ("n2", lat0 + 0.40 / 48.0, lon0 + 0.005),
        ("n3", lat0 + 0.90 / 48.0, lon0 + 0.006),
        ("n4", lat0, lon0 + 0.002),
        ("n5", lat0 + 0.10 / 48.0, lon0 + 0.008),
        ("n6", lat0 + 0.50 / 48.0, lon0 + 0.010),
        ("n7", lat0 + 0.15 / 48.0, lon0 + 0.012),
        ("n8", lat0 + 0.55 / 48.0, lon0 + 0.014),
    ]
    records: list[dict[str, Any]] = [
        {"imf": 1, "type": "node", "id": nid, "lat": la, "lon": lo, "tile": cell}
        for nid, la, lo in nodes
    ]
    ways = [
        ("w_res", ["n1", "n2"], {"highway": "residential", "name": "Res"}, "yes", 50),
        ("w_sec", ["n2", "n3"], {"highway": "secondary", "name": "Sec"}, "no", 50),
        ("w_road", ["n4", "n5"], {"highway": "road", "name": "Unknown"}, "no", None),
        ("w_bus", ["n5", "n6"], {"highway": "busway", "name": "Bus"}, "yes", 30),
        ("w_pri", ["n7", "n8"], {"highway": "primary"}, "no", 70),
    ]
    for wid, nids, tags, oneway, ms in ways:
        rec: dict[str, Any] = {
            "imf": 1,
            "type": "way",
            "id": wid,
            "tile": cell,
            "tiles": [cell],
            "nodes": nids,
            "tags": tags,
            "oneway": oneway,
        }
        if ms is not None:
            rec["maxspeed_kmh"] = ms
        records.append(rec)
    return records


def selftest() -> int:
    failures: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)
            print(f"FAIL: {msg}")
        else:
            print(f"ok: {msg}")

    # --- coverage / provenance ---
    rep = report_dict()
    check(rep["mapping"] == MAPPING_VERSION, "mapping version")
    check(rep["in_scope_count"] == len(IN_SCOPE_HIGHWAYS), "in-scope count matches DRIVABLE_HIGHWAYS")
    check(rep["all_in_scope_accounted"], "all in-scope accounted")
    check(rep["mapped_count"] + rep["unmapped_count"] == rep["in_scope_count"], "mapped+unmapped == in-scope")
    # v0 maps all in-scope drivable highways (2 as placeholders) so tilewriter has no misses.
    check(rep["unmapped_count"] == 0, "no in-scope UNMAPPED in v0 (all 17 mapped/placeholdered)")
    check(set(rep["placeholders"]) == {"busway", "road"}, "placeholders are exactly busway,road")

    entries = {e["highway"]: e for e in rep["entries"]}
    for hw in IN_SCOPE_HIGHWAYS:
        check(hw in entries, f"in-scope present: {hw}")
    for hw in fa_encode.CLASSES:
        e = entries[hw]
        check(e["entry_kind"] == "mechanism-confirmed-bucket", f"{hw} mechanism-confirmed-bucket")
        check(e["confidence"] == "provisional-mechanism", f"{hw} provisional-mechanism confidence")
        check([e["layer"], e["cls"]] == [fa_encode.CLASSES[hw][0][0], fa_encode.CLASSES[hw][0][1]],
              f"{hw} matches authoritative CLASSES (layer,cls)")
    for hw in ("busway", "road"):
        e = entries[hw]
        check(e["entry_kind"] == "provisional-placeholder", f"{hw} provisional-placeholder")
        check(e["confidence"] == "low-provisional", f"{hw} low-provisional")
        check(not e["refuse_generate"], f"{hw} mapped (not refused) but low-confidence")
        check("UNMAPPED" in e["rationale"] or "refuse_generate" in e["rationale"], f"{hw} rationale states alternative")
        check(e["alternatives"], f"{hw} alternatives recorded")

    # --- negative: unknown/OOS -> UNMAPPED, refuse, never silent drop ---
    for unk in ("steps", "footway", "unknown_xyz", "path"):
        e = map_highway(unk)
        check(e["status"] == "unmapped", f"{unk} unmapped")
        check(e["refuse_generate"] is True, f"{unk} refuse_generate")
        check(e["layer"] is None and e["cls"] is None, f"{unk} no class")
    # placeholders must not be treated as UNMAPPED
    for hw in ("busway", "road"):
        e = map_highway(hw)
        check(e["status"] == "mapped" and e["refuse_generate"] is False, f"{hw} not treated as UNMAPPED")

    # --- class table contract ---
    ct = class_table_dict()
    check(ct["format"] == CLASS_TABLE_FORMAT, "class-table format")
    check(ct["mapping"] == MAPPING_VERSION, "class-table mapping provenance")
    check(set(ct["classes"].keys()) == set(IN_SCOPE_HIGHWAYS), "classes cover all mapped in-scope highways")
    check(ct["provenance"]["provisional_placeholders"] == ["busway", "road"]
          or set(ct["provenance"]["provisional_placeholders"]) == {"busway", "road"},
          "provenance lists placeholders")
    # UNMAPPED excluded from classes
    check("steps" not in ct["classes"] and "unknown_xyz" not in ct["classes"], "UNMAPPED excluded from classes")
    # tilewriter accepts extended table (extras ignored; reads format+classes)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(ct, f)
        ct_path = f.name
    try:
        table, src = tilewriter.load_class_table(ct_path)
        check(isinstance(table, dict) and "busway" in table and "road" in table, "tilewriter loads emitted table incl placeholders")
        check(table["residential"] == (5, 8), "tilewriter parses residential mapping")
        check(ct_path in str(src) or "class-table" in str(src), "tilewriter reports source path")
    finally:
        os.unlink(ct_path)

    # speed/style mechanism (provisional metadata)
    ms = map_highway("residential", maxspeed_kmh=50, oneway="yes")
    check(ms["speed_style"]["speed_limit_kmh"] == 50, "speed_limit 50")
    check(isinstance(ms["speed_style"]["style_word"], int), "style_word mechanism returns int")
    check(ms["speed_style"]["provisional"] is True, "speed_style marked provisional")

    # --- synthetic L2 tile build using emitted class table (concrete) ---
    cell = "B48R058R"
    imf_records = _synthetic_imf(cell)
    # sanity: includes both placeholders
    imf_hws = {r.get("tags", {}).get("highway") for r in imf_records if r.get("type") == "way"}
    check("busway" in imf_hws and "road" in imf_hws, "synthetic IMF includes busway and road")
    with tempfile.TemporaryDirectory() as td:
        imf_path = os.path.join(td, "imf.jsonl")
        with open(imf_path, "w", encoding="utf-8") as f:
            for r in imf_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        ct_build_path = os.path.join(td, "roadclass-v0.class-table.json")
        with open(ct_build_path, "w", encoding="utf-8") as f:
            json.dump(class_table_dict(), f, indent=2, sort_keys=True)
        factory_path = os.path.join(td, f"{cell}.DAT")
        with open(factory_path, "wb") as f:
            f.write(tilewriter.make_factory(cell))
        out_path = os.path.join(td, f"{cell}.out.DAT")
        blob, build_rep = tilewriter.build(
            imf_path,
            cell,
            factory_path=factory_path,
            class_table_path=ct_build_path,
            level=1,
            country=616,
            output=out_path,
        )
        with open(out_path, "wb") as f:
            f.write(blob)
        # prove built with emitted table (not default/silent fallback)
        check("roadclass-v0.class-table.json" in str(build_rep.get("class_table", "")),
              "build report references emitted class table path")
        check(build_rep.get("mode") == "factory", "factory mode build")
        check(build_rep.get("section4", {}).get("preserved") is True, "section4 preserved")
        check(build_rep.get("unit_ready") is False, "unit_ready false (rule 13)")
        check(len(build_rep.get("parcels", [])) >= 1, "parcels produced")
        # existing tile check: readback (geometry)
        ct_table, _ = tilewriter.load_class_table(ct_build_path)
        stats, worst = tilewriter.readback(blob, imf_path, cell, ct_table, 1)
        check(stats.get("parcels_missing", 0) == 0, "readback parcels_missing==0")
        check(stats.get("input_points", 0) > 0, "readback input_points>0")
        check(stats.get("in_points_within_1m", 0) == stats["input_points"],
              "readback in_points_within_1m==input_points")
        print(f"  readback: {json.dumps(dict(stats, worst_m=round(worst, 3)), sort_keys=True)}")

    if failures:
        print(f"\nselftest FAILED ({len(failures)}):")
        for msg in failures:
            print(f" - {msg}")
        return 1
    print("\nselftest OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-auditable JSON report")
    ap.add_argument("--class-table-out", metavar="FILE", help="write ze0-road-class-table/1 JSON")
    ap.add_argument("--check-highway", metavar="HW", help="print mapping for one highway (exit 1 if unmapped/refused)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    rep = report_dict()
    ct = class_table_dict()

    if args.class_table_out:
        with open(args.class_table_out, "w", encoding="utf-8") as f:
            json.dump(ct, f, indent=2, sort_keys=True)
            f.write("\n")
        print(f"wrote {args.class_table_out} mapping={MAPPING_VERSION} classes={len(ct['classes'])}")

    if args.check_highway:
        e = map_highway(args.check_highway)
        print(json.dumps(e, indent=2, sort_keys=True))
        return 0 if (e["status"] == "mapped" and not e["refuse_generate"]) else 1

    if args.json:
        out = dict(rep, class_table=ct)
        print(json.dumps(out, indent=2, sort_keys=True))
    elif not args.class_table_out:
        print(_render_text(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
