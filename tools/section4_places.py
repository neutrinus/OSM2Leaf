#!/usr/bin/env python3
"""Fill a ZE0 tile's section-4 place-name index from OSM place nodes.

M4.21's ``section4.py generate`` produces verify-accepted payloads for a
changed parcel set, but its ``encode_build`` refuses names that have no
``payload_hex`` base: the name-list placement grammar is UNKNOWN (C-2391).
This tool stays on the proven side of that line.  It never invents a byte:

* it takes a **factory named record** as the base, so every undocumented byte
  (0x06..0x0f, offset pairs, terminators) is preserved verbatim;
* it substitutes only the text bytes of an existing ``d=NAME`` slot, with an
  OSM name folded to CP1252 **of exactly the same byte length**, so no offset
  or terminator moves (the inverse of ``section4.scan_names``, not a new
  grammar claim);
* it rebuilds the record with ``section4.encode_build`` (stock zlib settings
  L6/w15/m8) and splices only the changed record's own zlib stream into the
  tile, updating the directory pair exactly as ``ze0_mutate.py`` does.

With no ``--places`` input the tool writes the tile byte-identically; that is
the negative control for the no-input case.

Usage::

    python3 tools/section4_places.py --selftest
    python3 tools/section4_places.py build --tile TILE.DAT --places IMF.jsonl \
        --out OUT.DAT --report REPORT.json
    python3 tools/section4_places.py build --tile TILE.DAT --out OUT.DAT \
        --report REPORT.json            # negative control: no names
"""

from __future__ import annotations

import argparse
import hashlib
import hashutil
import json
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
VIEWER = os.path.join(HERE, "ze0-viewer")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(VIEWER, "tools_ze0"))
sys.path.insert(0, VIEWER)

import section4  # noqa: E402
import clarion_tile  # noqa: E402
import ze0_tile_io  # noqa: E402
from imf_check import fold_cp1252  # noqa: E402

PLACE_KINDS = ("town", "city")
DEFAULT_MIN_NAMES = 10
DEFAULT_MAX_NAMES = 40
EXIT_OK = 0
EXIT_CHECK_FAILED = 1
EXIT_BAD_INPUT = 2


sha256 = hashutil.sha256_bytes


def read_jsonl_places(path, kinds=PLACE_KINDS, bbox=None, limit=400):
    """Stream IMF JSONL and return CS1252-folded place nodes inside ``bbox``.

    ``bbox`` is (lat_min, lon_min, lat_max, lon_max) in degrees.  A name that
    cannot be represented in CP1252 is skipped: writing '?' would make the
    tool invent a byte the OSM input did not carry.
    """
    places = []
    seen = set()
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if '"place"' not in line:
                continue
            record = json.loads(line)
            tags = record.get("tags") or {}
            if tags.get("place") not in kinds:
                continue
            name = record.get("name") or tags.get("name")
            if not name:
                continue
            folded, faithful = fold_cp1252(name)
            if not faithful:
                continue
            try:
                raw = folded.encode("cp1252")
            except UnicodeEncodeError:
                continue
            if not (1 <= len(raw) <= 128):
                continue
            lat, lon = record.get("lat"), record.get("lon")
            if lat is None or lon is None:
                continue
            if bbox and not (bbox[0] <= lat <= bbox[2] and bbox[1] <= lon <= bbox[3]):
                continue
            key = (raw, round(float(lat), 5), round(float(lon), 5))
            if key in seen:
                continue
            seen.add(key)
            places.append(
                {
                    "osm_id": record.get("id"),
                    "place": tags.get("place"),
                    "name": folded,
                    "bytes": raw,
                    "length": len(raw),
                    "lat": float(lat),
                    "lon": float(lon),
                }
            )
            if len(places) >= limit:
                break
    places.sort(key=lambda p: (p["osm_id"] or "", p["name"]))
    return places


def bbox_from_tile(data):
    """Section-4 level-1 bbox from the tile's common header (harness.py logic)."""
    off = 0x2AC
    count = struct.unpack_from(">H", data, off)[0]
    pos = off + 2
    for _ in range(count):
        sid, levels = data[pos], data[pos + 1]
        pos += 2
        for _ in range(levels):
            _lv, _flag, a, b, c, d = struct.unpack_from(">BBhhhh", data, pos)
            pos += 10
            if sid == 4 and _lv == 1:
                # harness.py binds these as (sid, lv, flag, lat_max, lat_min,
                # lon_min, lon_max) and prints lat_min..lat_max.
                return (b / 60, c / 60, a / 60, d / 60)
    return None


def payload_slots(plain):
    """Return ``(model, slots)`` for one decompressed section-4 record.

    A slot is ``{record, name, offset, length, text}``: ``offset`` points at
    the first byte *after* the ``d=`` prefix, ``length`` is the byte length of
    the name text.  Both come from ``section4.parse_payload``, so substituting
    ``payload_hex[offset:offset+length]`` cannot move a prefix, NUL or offset.
    """
    model = section4.parse_payload(plain, "<section4_places>")
    slots = []
    for ri, record in enumerate(model["records"]):
        body = bytes.fromhex(record["payload_hex"])
        for ni, name in enumerate(record["names"]):
            total = len(name["raw_hex"]) // 2
            length = total - 2 - (1 if name["terminated"] else 0)
            offset = name["offset"] + 2
            if length <= 0 or offset + length > len(body):
                continue
            slots.append(
                {
                    "record": ri,
                    "name": ni,
                    "offset": offset,
                    "length": length,
                    "text": name["text"],
                }
            )
    return model, slots


def substitute(model, slot, raw):
    """Replace one name's text bytes in a parsed model, byte for byte.

    Returns the recompressed record bytes.  ``encode_build`` patches only the
    documented u16 fields and recompresses at L6/w15/m8; the unknown bytes and
    the name-list framing are copied from the factory ``payload_hex``.
    """
    # ``parse_payload`` was given an already-inflated record, so it labelled
    # the framing "plain" and ``encode_build`` would emit raw bytes.  The tile
    # stores these records as independent zlib members: force zlib framing so
    # the rebuilt record is compressed at L6/w15/m8, as M4.21 does.
    model["source"]["framing"] = "zlib"
    for item in model["records"]:
        item["framing"] = "zlib"
    record = model["records"][slot["record"]]
    body = bytearray(bytes.fromhex(record["payload_hex"]))
    offset, length = slot["offset"], slot["length"]
    if len(raw) != length:
        raise ValueError("name length %d != slot length %d" % (len(raw), length))
    body[offset : offset + length] = raw
    record["payload_hex"] = bytes(body).hex()
    entry = record["names"][slot["name"]]
    entry["text"] = raw.decode("latin-1")
    entry["raw_hex"] = bytes(body[offset - 2 : offset + length]).hex()
    output = section4.encode_build(model)
    check = section4.parse_payload(output, "<substituted>")
    if not section4.encode_preserve(check) == output:
        raise ValueError("substituted record failed preserve round-trip")
    return output, len(body)


def section4_locations(tile):
    """Yield ``(dir_index, slot_index, slot, record, plain)`` for section 4."""
    for section in tile["sections"]:
        if section["id"] != 4:
            continue
        for level in section["levels"]:
            for di, directory in enumerate(level["dirs"]):
                for si, slot in directory["slots"].items():
                    for record in slot["recs"]:
                        raw = record["raw"]
                        plain = (
                            zlib.decompress(raw)
                            if clarion_tile.is_zlib(raw)
                            else raw
                        )
                        if not plain:
                            continue
                        yield di, si, slot, record, plain


def _dir_by_index(tile, di):
    section = next(s for s in tile["sections"] if s["id"] == 4)
    return section["levels"][0]["dirs"][di]


def patch_records_in_place(data, tile, slot_changes):
    """Patch section-4 record streams and directory pairs in the source bytes.

    Only the changed slots' block bytes and their pair words are written; all
    other bytes (including every section-1 record) stay exactly where they
    were.  A rebuilt block must still fit its 256-byte-padded slot, otherwise
    the change is refused rather than allowed to overrun the next block.
    """
    for (di, si), changes in slot_changes.items():
        directory = _dir_by_index(tile, di)
        slot = directory["slots"][si]
        old_block = b"".join(r["raw"] for r in slot["recs"])
        room = (len(old_block) + 255) // 256 * 256
        rebuilt = b"".join(
            changes.get(r["k"], (r["raw"], None))[0] for r in slot["recs"]
        )
        if len(rebuilt) > room:
            raise ValueError(
                "slot dir %d slot %d needs %d bytes but has %d"
                % (di, si, len(rebuilt), room)
            )
        start = slot["block_off"]
        data[start : start + room] = rebuilt + b"\x00" * (room - len(rebuilt))
        # Directory body: 12-byte header, then per slot a 4-byte tag and body.
        body_off = directory["off"] + 12 + si * (4 + directory["body"]) + 4
        for k, (raw, inflated_len) in changes.items():
            struct.pack_into(
                ">II", data, body_off + k * 8,
                len(raw) // 2, inflated_len // 2,
            )
    return bytes(data)


def build(args):
    data = open(args.tile, "rb").read()
    tile = clarion_tile.read_tile(data)
    bbox = bbox_from_tile(data)
    if bbox is None:
        raise ValueError("tile has no section-4 level-1 bbox")

    if not args.places:
        # Negative control: no OSM input, no record change, no dirty tile.
        out = ze0_tile_io.write_tile(tile)
        if out != data:
            raise ValueError("no-input control changed the tile")
        report = {
            "tile": args.tile,
            "tile_sha256": sha256(data),
            "output_sha256": sha256(out),
            "bbox": bbox,
            "places_input": None,
            "changed_records": 0,
            "names_added": 0,
            "names_removed": 0,
            "names": [],
            "negative_control": True,
        }
        with open(args.out, "wb") as handle:
            handle.write(out)
        with open(args.report, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
        print("section4_places: no --places: tile byte-identical (%d bytes, %s)"
              % (len(out), sha256(out)))
        return EXIT_OK

    places = read_jsonl_places(args.places, bbox=bbox)
    if not places:
        raise ValueError("no OSM place node inside bbox %r" % (bbox,))

    # Candidate slots, with factory Poland records first for determinism.
    candidates = []
    for di, si, slot, record, plain in section4_locations(tile):
        try:
            model, slots = payload_slots(plain)
        except section4.ShapeError:
            continue
        if model["records"][0].get("type_tag") != section4.TYPE_TAG:
            continue
        country = model["records"][0].get("country_code")
        for s in slots:
            candidates.append(
                {
                    "key": (0 if country == 616 else 1, di, si, record["k"], s["offset"]),
                    "di": di,
                    "si": si,
                    "k": record["k"],
                    "plain": plain,
                    "slot": s,
                    "factory_text": s["text"],
                }
            )
    candidates.sort(key=lambda c: c["key"])

    by_length = {}
    for c in candidates:
        by_length.setdefault(c["slot"]["length"], []).append(c)

    chosen = []
    used_slots = set()
    used_records = set()
    for place in places:
        pool = by_length.get(place["length"], ())
        pick = None
        for c in pool:
            record_key = (c["di"], c["si"], c["k"])
            if c["key"] in used_slots or record_key in used_records:
                continue
            pick = c
            break
        if pick is None:
            continue
        used_slots.add(pick["key"])
        used_records.add((pick["di"], pick["si"], pick["k"]))
        chosen.append((pick, place))
        if len(chosen) >= args.max_names:
            break
    if len(chosen) < args.min_names:
        raise ValueError(
            "only %d/%d OSM places fit a same-length slot (need %d)"
            % (len(chosen), len(places), args.min_names)
        )

    # Rebuild only the changed records' own zlib streams and the directory
    # pairs that describe them.  The factory tile layout is kept byte-for-byte
    # everywhere else: a full clarion_tile.write_tile() rewrite moves section-1
    # blocks and corrupts records there when a section-4 stream grows.
    slot_changes = {}
    written = []
    for pick, place in chosen:
        key = (pick["di"], pick["si"], pick["k"])
        skey = (pick["di"], pick["si"])
        current = slot_changes.get(skey, {})
        if key in current:
            raise ValueError("two names selected for the same record")
        model, _slots = payload_slots(pick["plain"])
        new_raw, inflated_len = substitute(model, pick["slot"], place["bytes"])
        if len(new_raw) % 2:
            new_raw += b"\x00"
        # A rebuilt slot block must still fit its 256-byte-padded slot.  If it
        # grows past that, refuse this candidate and leave the block alone.
        slot = _slot_by_key(tile, *skey)
        old_len = sum(len(r["raw"]) for r in slot["recs"])
        room = (old_len + 255) // 256 * 256
        delta = sum(
            len(v[0]) - len(_record_by_key(tile, *skey, k)["raw"])
            for k, v in current.items()
        )
        if old_len + delta + len(new_raw) - len(
            _record_by_key(tile, *skey, pick["k"])["raw"]
        ) > room:
            continue
        slot_changes.setdefault(skey, {})[pick["k"]] = (new_raw, inflated_len)
        written.append(
            {
                "osm_id": place["osm_id"],
                "name": place["name"],
                "bytes": place["length"],
                "factory_text": pick["factory_text"],
                "location": {
                    "dir": pick["di"], "slot": pick["si"], "k": pick["k"],
                    "name_offset": pick["slot"]["offset"],
                },
            }
        )

    if len(written) < args.min_names:
        raise ValueError(
            "only %d names fit their slot blocks (need %d)"
            % (len(written), args.min_names)
        )
    out = patch_records_in_place(bytearray(data), tile, slot_changes)
    with open(args.out, "wb") as handle:
        handle.write(out)
    report = {
        "tile": args.tile,
        "tile_sha256": sha256(data),
        "output_sha256": sha256(out),
        "bbox": bbox,
        "places_input": args.places,
        "places_inside_bbox": len(places),
        "candidate_slots": len(candidates),
        "changed_records": sum(len(v) for v in slot_changes.values()),
        "names_added": len(written),
        "names_removed": len(written),
        "names": written,
        "negative_control": False,
    }
    with open(args.report, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    print(
        "section4_places: %d OSM place names into %d section-4 records "
        "(%d inside bbox, %d candidate slots) -> %s (%d bytes, %s)"
        % (len(written), sum(len(v) for v in slot_changes.values()),
           len(places), len(candidates),
           args.out, len(out), sha256(out))
    )
    return EXIT_OK


def _slot_by_key(tile, di, si):
    section = next(s for s in tile["sections"] if s["id"] == 4)
    level = section["levels"][0]
    return level["dirs"][di]["slots"][si]


def _record_by_key(tile, di, si, k):
    return next(r for r in _slot_by_key(tile, di, si)["recs"] if r["k"] == k)


def selftest():
    # Pure in-memory: no tile, no vendor bytes.  The synthetic record follows
    # section4._synthetic_record so the name area shape is the one the parser
    # already understands.
    record = section4._synthetic_record([(0, b"RODOS"), (0, b"LINDOS")])
    model, slots = payload_slots(record)
    assert [s["length"] for s in slots] == [5, 6], slots
    out, inflated = substitute(model, slots[0], b"WROCL")
    assert inflated == len(record), (inflated, len(record))
    text = [n["text"] for n in section4.parse_payload(out, "t")["records"][0]["names"]]
    assert text == ["WROCL", "LINDOS"], text
    try:
        substitute(model, slots[0], b"TOOLONGNAME")
    except ValueError:
        pass
    else:
        raise AssertionError("wrong-length substitution was accepted")
    # A no-place build must refuse before touching any tile data.
    assert PLACE_KINDS == ("town", "city")
    print("section4_places selftest: 2 slots, exact-length substitution OK")
    print("  wrong-length substitution refused")
    print("selftest: OK")
    return EXIT_OK


def build_parser():
    parser = argparse.ArgumentParser(
        description="Fill ZE0 section 4 place names from OSM IMF place nodes."
    )
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="command")
    cmd = sub.add_parser("build", help="write a section-4-named tile")
    cmd.add_argument("--tile", required=True, help="factory-backed tile (read-only)")
    cmd.add_argument("--places", help="IMF JSONL with OSM place nodes (omit for control)")
    cmd.add_argument("--out", required=True, help="output tile path")
    cmd.add_argument("--report", required=True, help="JSON report path")
    cmd.add_argument("--min-names", type=int, default=DEFAULT_MIN_NAMES)
    cmd.add_argument("--max-names", type=int, default=DEFAULT_MAX_NAMES)
    cmd.set_defaults(func=build)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not getattr(args, "command", None):
        parser.error("choose build (or use --selftest)")
    try:
        return args.func(args)
    except (ValueError, OSError, section4.ShapeError, section4.BuildRefused) as exc:
        print("section4_places: %s" % exc, file=sys.stderr)
        return EXIT_BAD_INPUT


if __name__ == "__main__":
    sys.exit(main())
