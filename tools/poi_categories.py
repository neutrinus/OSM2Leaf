#!/usr/bin/env python3
"""Census of POI category codes, with BICON001 icons and names (M4.88).

A ``0x60`` POINT record carries two byte-aligned 16-bit codes: the category
immediately before the facility-name field and the brand in the record's last
two bytes (C-981).  ``tools/poi_icons.py`` verified 34 of those codes against
visible ``BICON001`` logos; this tool puts *every* coded category of a card in
one generated table and marks which part of each row is verified, which part
is a group hypothesis and which part is only a card-derived name hint.

The name field is located with the writer's inverse
(``mutate_refer_poi.name_field``), not with a loose regex: a byte pair before
any upper-case text is not necessarily a category code.  A record whose name
prefix is ``ffff`` is uncoded and counted separately, never assigned a code.

Usage::

    python3 tools/poi_categories.py --selftest
    python3 tools/poi_categories.py table ROOT [--out MD] [--json JSON]
    python3 tools/poi_categories.py places ROOT [--lat LAT --lon LON --radius-km KM]
    python3 tools/poi_categories.py verify ROOT

ROOT is an extracted card tree or a raw SD card image (FAT32 read in place).
Read-only: no extracted or vendor bytes are written by this tool.

Evidence and limits: docs/format/poi-categories.md and
EXP-2026-11-22-M4.88-poi-categories.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cmpind_codec  # noqa: E402
import mutate_refer_poi as mrp  # noqa: E402
import poi_icons  # noqa: E402
import point_census  # noqa: E402
import vcard_l3  # noqa: E402

#: Warsaw centre used by the "known real place" control (same point as the
#: reference POIs of point_census' synthetic self-test, M4.27).
PLACE_LAT, PLACE_LON = 52.2297, 21.0122
PLACE_RADIUS_KM = 20.0
PLACE_MIN_CODES = 10

NO_CODE = 0xFFFF
GROUP_ICON = {0x01: 0, 0x03: 18, 0x0D: 21, 0x0E: 21}   # C-982/C-984, hypothesis
GROUP_NAME = {0x01: "fuel/shop", 0x03: "restaurant/cafe",
              0x0D: "hotel", 0x0E: "hotel"}
VERIFIED = {code: (icon, label, prefix) for code, icon, label, prefix in poi_icons.MAPPING}


class CategoryError(ValueError):
    pass


def open_source(root: str) -> tuple[object, str]:
    """A card source from an image path or an extracted tree."""
    path = Path(root)
    if path.is_dir():
        return vcard_l3.open_source(root=root), "tree"
    if path.is_file():
        return vcard_l3.open_source(image=root), "image"
    raise CategoryError(f"ROOT does not exist: {root}")


def read_file(source, rel: str) -> bytes:
    name = next((e for e in source.list_dir(str(Path(rel).parent))
                 if e.name.lower() == Path(rel).name.lower()), None)
    if name is None:
        raise CategoryError(f"card has no {rel}")
    return source.read_range(name.path, 0, name.size)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_point(source, stem: str) -> bytes:
    """Inflate one REFER001/POINTnnn.DAT pair entirely in memory."""
    cmp_path = f"REFER001/{stem}.DAT.cmp"
    ind_path = f"REFER001/{stem}.DAT.ind"
    packed = read_file(source, cmp_path)
    ind = read_file(source, ind_path)
    if len(ind) < 16:
        raise CategoryError(f"{stem}: short .ind")
    usize, csize, count, chunk = struct.unpack_from("<IIII", ind, 0)
    if len(ind) != 16 + 4 * count or csize != len(packed):
        raise CategoryError(f"{stem}: .ind does not describe .cmp")
    offsets = struct.unpack_from(f"<{count}I", ind, 16)
    blob = cmpind_codec.decode_blob(packed, offsets, usize=usize, chunk_size=chunk, name=stem)
    return blob


def point_files(source) -> list[str]:
    """Sorted POINTnnn stems that have both halves of the .cmp/.ind pair."""
    names = {e.name for e in source.list_dir("REFER001")}
    stems = sorted(n[:-8] for n in names
                   if n.upper().startswith("POINT") and n.upper().endswith(".DAT.CMP")
                   and (n[:-8] + ".DAT.ind").lower() in {x.lower() for x in names})
    return stems


def iter_coded_records(blob: bytes):
    """Yield ``(category, brand, name, lat, lon, stream, index)`` for one shard.

    Only 0x60 records whose field layout is accepted by the verified writer's
    inverse are used.  An ffff category is an uncoded record (counted by the
    caller, never emitted as a code).
    """
    for stream, inner in poi_icons.iter_streams(blob):
        for index, (tag, rec) in enumerate(poi_icons.iter_point_records(inner)):
            if tag != 0x60:
                continue
            try:
                start, words, _ = mrp.name_field(rec)
            except mrp.PageError:
                continue
            code = int.from_bytes(rec[start - 2:start], "big")
            brand = int.from_bytes(rec[-2:], "big")
            text = rec[start:start + 2 * words].split(b"\x00", 1)[0]
            try:
                name = text.decode("latin1")
            except UnicodeDecodeError:
                name = text.decode("latin1", "replace")
            lat, lon = point_census.fine_position(rec)
            yield code, brand, name, lat, lon, stream, index


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# census
# ---------------------------------------------------------------------------


def read_bicon_bytes(data: bytes) -> tuple[int, list]:
    """The BICON001 table of assets.md / C-980, parsed from bytes in memory."""
    if len(data) < poi_icons.BICON_DATA_OFF:
        raise CategoryError("short BICON001")
    count = struct.unpack_from(">H", data, poi_icons.BICON_COUNT_OFF)[0]
    icons = []
    for i in range(count):
        pos = poi_icons.BICON_TABLE_OFF + i * 8
        start, size = struct.unpack_from(">II", data, pos)
        off = poi_icons.BICON_DATA_OFF + start * poi_icons.ICON_UNIT
        length = size * poi_icons.ICON_UNIT
        png = data[off:off + 8] == poi_icons.PNG_MAGIC and off + 24 <= len(data)
        icons.append({"index": i, "offset": off, "size": length, "png": png})
    return count, icons


def read_bicon(source) -> dict:
    data = read_file(source, "BICON001/BICON001.DAT")
    count, icons = read_bicon_bytes(data)
    highest = max(v[0] for v in VERIFIED.values())
    return {"count": count, "png": sum(1 for i in icons if i["png"]),
            "sha256": sha256(data), "indices_ok": count > highest and all(
                i["png"] for i in icons[:highest + 1])}


# ---------------------------------------------------------------------------
# verdicts
# ---------------------------------------------------------------------------


def stability(rep: dict) -> dict:
    """Falsifier test: is the (code -> icon/name) mapping stable and injective?"""
    rows = rep["rows"]
    verified = [r for r in rows if r["icon"] is not None]
    collisions = [(a["code"], b["code"]) for i, a in enumerate(verified) for b in verified[i + 1:]
                  if a["icon"] == b["icon"] and a["verified_label"] == b["verified_label"]]
    bad = [r["code"] for r in verified if r["prefix"] and r["prefix_hits"] * 2 < r["count"]]
    invented = [r["code"] for r in rows if r["icon"] is None and r["verified_label"]]
    stable = not collisions and not bad and not invented and rep["icons"]["indices_ok"]
    return {"verified_codes": len(verified), "collisions": collisions,
            "prefix_failures": bad, "invented": invented, "stable": stable}


def _collect(source, **kw):
    """Internal: run census and return (report, per-code name counters).

    A code can occupy either of the two byte-aligned fields: the category
    before the name or the brand at the record tail (C-981).  The 34-row
    verified mapping in ``poi_icons.MAPPING`` mixes both roles (0x0dac is a
    category, 0x0dad a brand), so both are counted.  ``count`` is the number
    of records carrying the code in *either* role (once if in both).
    """
    icons = read_bicon(source)
    stems = point_files(source)
    counts = Counter()
    cat_counts = Counter()
    brand_counts = Counter()
    other = defaultdict(set)
    names = defaultdict(Counter)
    shards = defaultdict(set)
    near = defaultdict(list)
    uncoded = coded = 0
    lat = kw.get("lat", PLACE_LAT)
    lon = kw.get("lon", PLACE_LON)
    radius = kw.get("radius_km", PLACE_RADIUS_KM)
    for stem in stems:
        blob = decode_point(source, stem)
        for code, brand, name, plat, plon, stream, index in iter_coded_records(blob):
            if code == NO_CODE:
                uncoded += 1
                continue
            coded += 1
            keys = {code, brand} - {NO_CODE}
            for key in keys:
                counts[key] += 1
                names[key][name] += 1
                shards[key].add(stem)
                if haversine_km(lat, lon, plat, plon) <= radius and len(near[key]) < 3:
                    near[key].append({"shard": stem, "stream": hex(stream), "record": index,
                                      "name": name, "lat": round(plat, 5),
                                      "lon": round(plon, 5), "brand": f"0x{brand:04x}"})
            cat_counts[code] += 1
            if brand != NO_CODE:
                brand_counts[brand] += 1
            for key in keys:
                other[key].add(brand if key == code else code)
        if kw.get("progress"):
            print(f"{stem}: coded={coded:,} uncoded={uncoded:,} codes={len(counts)}",
                  file=sys.stderr, flush=True)
    rows = []
    for code, n in counts.most_common():
        icon, label, prefix = VERIFIED.get(code, (None, None, None))
        group = code >> 8
        top, top_n = names[code].most_common(1)[0]
        hits = sum(v for k, v in names[code].items() if prefix and prefix.upper() in k.upper())
        rows.append({
            "code": f"0x{code:04x}", "dec": code, "count": n,
            "cat_count": cat_counts[code], "brand_count": brand_counts[code],
            "icon": icon, "group_icon": GROUP_ICON.get(group),
            "group": f"0x{group:02x}xx",
            "name": label or (f"card: {top[:28]}" if n >= 10 else "—"),
            "card_name": top, "card_name_count": top_n,
            "verified_label": label or "", "prefix": prefix or "",
            "prefix_hits": hits, "shards": len(shards[code]),
            "other_codes": len(other[code]), "near": near.get(code, []),
        })
    return {
        "rows": rows, "icons": icons,
        "totals": {"shards": len(stems), "coded": coded, "uncoded": uncoded,
                   "distinct_codes": len(counts),
                   "distinct_brands": len(brand_counts),
                   "place": {"lat": lat, "lon": lon, "radius_km": radius}},
        "names": names,
    }


def run(source, **kw) -> dict:
    rep = _collect(source, **kw)
    rep["verdict"] = stability(rep)
    near_codes = [r for r in rep["rows"] if r["near"]]
    rep["place_codes"] = len(near_codes)
    rep["place_ok"] = rep["place_codes"] >= PLACE_MIN_CODES
    return rep


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------


def md_cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_markdown(rep: dict, root: str, source_kind: str) -> str:
    t = rep["totals"]
    v = rep["verdict"]
    ic = rep["icons"]
    lines = [
        "# POI category codes (generated by `tools/poi_categories.py`)",
        "",
        "> **Evidence status:** the code counts and card names are `OBSERVED` on",
        "> EU 2011; the 34 code→icon/name rows marked `MAPPING` are `OBSERVED`",
        "> (C-983, EXP-2026-11-06-M4.10-poi-icons); a `group?` icon is a",
        "> `HYPOTHESIS` from C-982/C-984, not a code-specific firmware fact.",
        "> No firmware reader VA for this table is known (C-988), so the table is",
        "> not `CONFIRMED` in the rule-13 sense.",
        "",
        f"- Source: `{root}` ({source_kind}), read in place; ROOT may also be an extracted tree.",
        f"- Card SHA-256: `{t.get('sha256','')}`" if t.get("sha256") else "- Card SHA-256: see the EXP",
        f"- BICON001 SHA-256: `{ic['sha256']}`; icons={ic['count']}, PNG={ic['png']}.",
        f"- Shards: {t['shards']} (`POINT001`…`POINT033`); coded records: {t['coded']:,};",
        f"  uncoded (`ffff`) records: {t['uncoded']:,}; distinct codes in either",
        f"  byte-aligned role: {t['distinct_codes']}; distinct brand codes: {t['distinct_brands']}.",
        f"- Place control: {t['place']['lat']}, {t['place']['lon']} within",
        f"  {t['place']['radius_km']:g} km → {rep['place_codes']} coded categories (need {PLACE_MIN_CODES}).",
        f"- Falsifier verdict: `stable={'yes' if v['stable'] else 'no'}` —",
        f"  {v['verified_codes']} verified codes, {len(v['collisions'])} icon/name collisions,",
        f"  {len(v['prefix_failures'])} mapped-name failures, {len(v['invented'])} invented icons.",
        "",
        "Reproduce: `python3 tools/poi_categories.py table ROOT --out docs/format/poi-categories.md`.",
        "",
        "## Table",
        "",
        "A code is counted when it appears in either byte-aligned field: the",
        "category before the facility name (cat) or the brand at the record tail",
        "(brand). `n` counts records carrying the code at least once; the evidence",
        "cell splits the two roles. `icon` with no `?` is verified against BICON001;",
        "`N?` is the group-default glyph (0x01xx→0, 0x03xx→18, 0x0dxx/0x0exx→21)",
        "and is unverified for that code. `card: X` in `name` means X is the most",
        "frequent POI name carrying the code; it is a compiler hint, not a menu",
        "string. `—` means fewer than 10 records, so no name hint is published.",
        "",
        "| Code | Count | Icon | Name | Evidence |",
        "| --- | --: | --- | --- | --- |",
    ]
    for r in rep["rows"]:
        if r["icon"] is not None:
            icon = str(r["icon"])
            src = "MAPPING (C-983)"
        elif r["group_icon"] is not None:
            icon = f"{r['group_icon']}?"
            src = f"group {r['group']} (C-982/C-984, hypothesis)"
        else:
            icon = "—"
            src = "no verified icon"
        ev = (f"cat={r['cat_count']:,}, brand={r['brand_count']:,}, shards={r['shards']}, "
              f"other_codes={r['other_codes']}; "
              f"top={md_cell(r['card_name'][:24])}×{r['card_name_count']}; {src}")
        lines.append(f"| `{r['code']}` | {r['count']:,} | {icon} | "
                     f"{md_cell(r['name'])} | {ev} |")
    lines += [
        "",
        "## Ten codes at a known real place",
        "",
        f"Records within {t['place']['radius_km']:g} km of "
        f"({t['place']['lat']}, {t['place']['lon']}) — Warsaw centre. "
        f"The command found {rep['place_codes']} coded categories; the ten "
        f"largest by record count are shown:",
        "",
        "| Code | Icon | Name | POI (shard/stream/record) | Position |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in [x for x in rep["rows"] if x["near"]][:10]:
        s = r["near"][0]
        icon = (str(r["icon"]) if r["icon"] is not None else
                f"{r['group_icon']}?" if r["group_icon"] is not None else "—")
        lines.append(f"| `{r['code']}` | {icon} | "
                     f"{md_cell(r['name'])} | {md_cell(s['name'])} "
                     f"({s['shard']}/{s['stream']}/{s['record']}) | "
                     f"{s['lat']}, {s['lon']} |")
    lines += [
        "",
        "## Scope and limits",
        "",
        "- Counts include only `0x60` records whose field layout the verified",
        "  writer's inverse accepts; `0x68` twins and uncoded records are excluded.",
        "- Icon indices are `BICON001` table indices (0-based), not PNG bytes;",
        "  no icon image is committed.",
        "- The high-byte grouping is an observation about 34 mapped codes, not a",
        "  rule proved for the other codes; `group?` rows are a fallback for the",
        "  compiler to override when a firmware reader is located (M3/M9).",
        "",
    ]
    return "\n".join(lines)


def cmd_table(args) -> int:
    source, kind = open_source(args.root)
    rep = run(source, progress=args.progress)
    text = render_markdown(rep, args.root, kind)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
        print(f"wrote {out}: {len(rep['rows'])} codes, {rep['totals']['coded']:,} coded records")
    else:
        print(text)
    if args.json:
        j = {"totals": rep["totals"], "verdict": rep["verdict"],
             "place_codes": rep["place_codes"], "icons": rep["icons"],
             "rows": [{k: v for k, v in r.items() if k != "near"} for r in rep["rows"]]}
        Path(args.json).write_text(json.dumps(j, indent=1) + "\n")
        print(f"wrote {args.json}")
    print(f"verdict stable={rep['verdict']['stable']}; place codes={rep['place_codes']}/{PLACE_MIN_CODES}; "
          f"icons PNG={rep['icons']['png']}/{rep['icons']['count']}")
    return 0


def cmd_places(args) -> int:
    source, _ = open_source(args.root)
    rep = run(source, lat=args.lat, lon=args.lon, radius_km=args.radius_km)
    print(f"place {args.lat},{args.lon} r={args.radius_km:g} km: "
          f"{rep['place_codes']} coded categories (need {PLACE_MIN_CODES})")
    for r in [x for x in rep["rows"] if x["near"]][:args.top]:
        s = r["near"][0]
        icon = (str(r["icon"]) if r["icon"] is not None else
                f"{r['group_icon']}?" if r["group_icon"] is not None else "—")
        print(f"  {r['code']} n={r['count']:,} icon={icon} "
              f"name={r['name'][:24]!r} POI={s['name']!r} {s['lat']},{s['lon']} "
              f"{s['shard']}/{s['stream']}/{s['record']}")
    ok = rep["place_codes"] >= args.min_codes
    print(f"VERDICT: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def cmd_verify(args) -> int:
    source, _ = open_source(args.root)
    rep = run(source)
    v = rep["verdict"]
    print(f"codes={rep['totals']['distinct_codes']} coded={rep['totals']['coded']:,} "
          f"uncoded={rep['totals']['uncoded']:,} verified={v['verified_codes']}")
    print(f"collisions={v['collisions']} prefix_failures={v['prefix_failures']} "
          f"invented={v['invented']} icons_ok={rep['icons']['indices_ok']}")
    print(f"place_codes={rep['place_codes']} (need {PLACE_MIN_CODES})")
    ok = v["stable"] and rep["place_ok"] and rep["totals"]["distinct_codes"] > 0
    print("VERDICT: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# synthetic self-test (no vendor data)
# ---------------------------------------------------------------------------


def _png(w: int, h: int) -> bytes:
    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + b"\x00" * w * 4 for _ in range(h))
    return (poi_icons.PNG_MAGIC + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _record(name: bytes, category: int, brand: int, tag: int = 0x60,
            ax: int = 0x8ECE, ay: int = 0xCFD1) -> bytes:
    """A 0x60 record in the verified field layout (C-5115)."""
    if len(name) % 2:
        name += b"\x00"
    fields = [b"\x01\x02\x03\x04", category.to_bytes(2, "big"), b"", b"", b"",
              name, b"@SYNTH\x00\x00", b"", brand.to_bytes(2, "big")]
    lens = bytes(len(f) // 2 for f in fields) + b"\x00"
    loc = 16
    head = bytearray(bytes([tag, 0]) + struct.pack(">HHHH", ax, ay, 0x0801, 0x0801) + b"\x00" * 2)
    head += b"\x00" * (loc - len(head))
    rec = bytearray(head + lens + b"".join(fields))
    rec[1] = len(rec) // 2
    return bytes(rec)


def _synth_source():
    icons = []
    for i in range(66):
        blob = _png(30, 30) if i in (0, 18, 21, 22) else _png(32, 32)
        icons.append(blob + b"\x00" * (len(blob) % 2))
    table = b""
    start = 0
    for blob in icons:
        table += struct.pack(">II", start // 2, len(blob) // 2)
        start += len(blob)
    header = bytearray(poi_icons.BICON_DATA_OFF)
    struct.pack_into(">H", header, poi_icons.BICON_COUNT_OFF, len(icons))
    header[poi_icons.BICON_TABLE_OFF:poi_icons.BICON_TABLE_OFF + len(table)] = table
    bicon = bytes(header) + b"".join(icons)

    unit = (b"".join(_record(n, c, brand) for n, c, brand in (
        (b"FUEL TEST", 0x0190, 0x0190),
        (b"BEST WESTERN TEST", 0x0DAC, 0x0DAD),
        (b"HOTEL TEST", 0x0DAC, 0x0DAC),
        (b"UNKNOWN PLACE", 0x1234, 0x1234),
    )))
    stream = zlib.compress(unit * 24)
    logical = stream + b"\x00" * (-len(stream) % 4)
    cmp_bytes = cmpind_codec.factory_compress(logical)
    ind = cmpind_codec.build_ind(len(logical), len(cmp_bytes), cmpind_codec.CHUNK, (0,))
    return vcard_l3.MemorySource({
        "BICON001/BICON001.DAT": bicon,
        "REFER001/POINT999.DAT.cmp": cmp_bytes,
        "REFER001/POINT999.DAT.ind": ind,
    })


def selftest() -> int:
    fails = []

    def ok(cond, label):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    src = _synth_source()
    rep = run(src)
    by_code = {r["dec"]: r for r in rep["rows"]}
    ok(rep["totals"]["coded"] == 96 and rep["totals"]["distinct_codes"] == 4,
       f"synthetic counts: 96 coded records, 4 codes (got {rep['totals']['coded']}, "
       f"{rep['totals']['distinct_codes']})")
    ok(by_code.get(0x0190, {}).get("icon") == 0 and by_code[0x0190]["name"] == "petrol station (generic)",
       "positive: 0x0190 -> icon 0 fuel pump")
    ok(by_code.get(0x0DAD, {}).get("icon") == 22 and by_code[0x0DAD]["prefix_hits"] == 24,
       "positive: 0x0dad -> icon 22 Best Western, 24/24 name hits")
    ok(by_code.get(0x1234, {}).get("icon") is None and by_code[0x1234]["card_name"] == "UNKNOWN PLACE",
       "negative: unknown code gets no verified icon, only a card name")
    ok(by_code[0x1234]["group_icon"] is None and by_code[0x1234]["name"].startswith("card:"),
       "negative: unmapped high byte 0x12 gets no group glyph")
    ok(rep["icons"]["count"] == 66 and rep["icons"]["png"] == 66 and rep["icons"]["indices_ok"],
       "synthetic BICON: 66 PNGs, all verified icon indices present")
    ok(rep["verdict"]["stable"], f"falsifier: synthetic mapping stable ({rep['verdict']})")

    fake = {"rows": [
        {"code": "0x0001", "icon": 1, "verified_label": "X", "prefix": "", "prefix_hits": 0, "count": 1},
        {"code": "0x0002", "icon": 1, "verified_label": "X", "prefix": "", "prefix_hits": 0, "count": 1},
    ]}
    fake["icons"] = {"indices_ok": True}
    fake_verdict = stability(fake)
    ok(not fake_verdict["stable"] and len(fake_verdict["collisions"]) == 1,
       "negative: two codes with identical icon+name are reported unstable")
    ok(haversine_km(PLACE_LAT, PLACE_LON, PLACE_LAT, PLACE_LON) < 1e-9
       and haversine_km(PLACE_LAT, PLACE_LON, PLACE_LAT + 10, PLACE_LON) > 1000,
       "negative: displaced coordinate is not inside the place circle")
    ok(len(poi_icons.MAPPING) == len(VERIFIED) and len({v[0] for v in VERIFIED.values()}) == len(VERIFIED),
       "verified mapping is injective in icon index")

    text = render_markdown(rep, "synthetic", "tree")
    ok("| Code | Count | Icon | Name | Evidence |" in text
       and "`0x0190`" in text and "`0x1234`" in text,
       "generated markdown has the five required columns and all codes")
    print("poi_categories selftest: " + ("OK" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    t = sub.add_parser("table", help="generate the category table as Markdown")
    t.add_argument("root")
    t.add_argument("--out", help="write Markdown here (default: stdout)")
    t.add_argument("--json", help="also write the counts as JSON")
    t.add_argument("--progress", action="store_true")
    t.set_defaults(func=cmd_table)
    p = sub.add_parser("places", help="check ten coded categories at a known real place")
    p.add_argument("root")
    p.add_argument("--lat", type=float, default=PLACE_LAT)
    p.add_argument("--lon", type=float, default=PLACE_LON)
    p.add_argument("--radius-km", type=float, default=PLACE_RADIUS_KM)
    p.add_argument("--min-codes", type=int, default=PLACE_MIN_CODES)
    p.add_argument("--top", type=int, default=20)
    p.set_defaults(func=cmd_places)
    v = sub.add_parser("verify", help="run the falsifier and place checks")
    v.add_argument("root")
    v.set_defaults(func=cmd_verify)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not getattr(args, "func", None):
        ap.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
