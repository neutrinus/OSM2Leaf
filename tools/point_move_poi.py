#!/usr/bin/env python3
"""Move one POI of a REFER001 ``POINTnnn.DAT`` pair to a given position (M5.63).

The POI tools so far rename only.  A POI needs a position, and ``point_census``
(M4.27) showed where it lives: the name record holds copy A (words 2..3, low
nibble ``11xx``) and the two fine words (words 6 and 8, 11 bits each), and the
leaf of its category's spatial tree repeats those words.  This tool writes the
first step of the writer:

* **step 1 (this tool):** move a POI inside its own copy-A cell — rewrite
  ``rec[6..7]`` and ``rec[8..9]`` of its name record and the fine word of its
  spatial-tree leaf(s).  Every other structure (trie, index chain, phone tree,
  the 400/2000 tables) carries no position and is left byte for byte.
* **not done here:** a move to another cell (a level-1 key and node change) is
  step 2 and is refused with the reason named.

The name chain is re-packed in place (``point_pair_regen.regen_chain``), so
only the edited page's stream changes.  The chain slot often has less slack
than one fine change costs (~1-3 B), so the tool searches the neighbourhood of
the requested position (``--span`` fine steps, closest first) and takes the
closest pair of fine values whose page still compresses into its original
4-byte slot; that position must be within 2 m of the request or the move is
refused.  No page grows, so no other page of the chain moves and the chain
table does not change.  The page must re-encode with the pinned stock zlib
1.3.1 (``--libz``) or the slot check is not the factory one; a stock runtime
that is not 1.3.1 is accepted only with ``--allow-nonreference``.

Commands::

  python3 tools/point_move_poi.py CMP OUTDIR --position LAT LON [--record N]
  python3 tools/point_move_poi.py CMP OUTDIR --position LAT LON --select TEXT
  python3 tools/point_move_poi.py CMP OUTDIR --position LAT LON --span 40
  python3 tools/point_move_poi.py CMP OUTDIR --noop
  python3 tools/point_move_poi.py CMP OUTDIR --position LAT LON --control leave-leaf
  python3 tools/point_move_poi.py CMP OUTDIR --position LAT LON --control leave-record
  python3 tools/point_move_poi.py --selftest

``--select TEXT`` picks the first name record whose name contains TEXT
(case-insensitive); ``--record N`` is the record's ordinal in chain order and
is the default selector at 0.  ``--control leave-leaf`` writes the pair with the
name record moved but the leaf left and expects ``joins`` to refuse it;
``--control leave-record`` is the mirror.

Exit codes: 0 moved and verified (or control behaved as expected); 1 refused or
verification failed; 2 usage; 3 the encoder cannot be verified as the factory
one (``zlibinfo``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cmpind_codec  # noqa: E402
import mutate_refer_poi as mrp  # noqa: E402
import point_census as pc  # noqa: E402
import point_pair_regen as regen  # noqa: E402
import zlibinfo  # noqa: E402

NAME_CHAIN = 1000
CELL_SPATIAL = pc.CELL_SPATIAL
FINE_MAX = 0x7FF
FINE_STEP_LAT_M = 111320.0 / (pc.FINE_PER_UNIT * pc.LAT_SCALE)     # ~1.13 m
TARGET_TOLERANCE_M = 2.0
DEFAULT_SEARCH = 6                 # fine steps searched around the request


class MoveError(ValueError):
    """The move is refused; nothing is written."""


# ---------------------------------------------------------------------------
# name records and spatial leaves


def name_records(blob: bytes, chain) -> list[dict]:
    """Every record of the name chain, with its page and page offset."""
    out = []
    for pi, (page, _, inner) in enumerate(chain.pages):
        recs = regen.walk_records(inner)
        if recs is None:
            raise MoveError(f"name page {page:#x} does not walk as a record chain")
        for off, size in recs:
            rec = inner[off:off + size]
            w = (rec[0] << 8) | rec[1]
            out.append({"index": len(out), "page_index": pi, "page": page,
                        "offset": off, "size": size, "rec": rec,
                        "ordinal": w & 0x3FF})
    return out


def record_name(rec: bytes) -> str:
    start, words, _ = mrp.name_field(rec)
    return rec[start:start + 2 * words].decode("latin-1")


def select_record(records: list[dict], record: int | None, text: str | None) -> dict:
    if text is not None:
        want = text.upper()
        for row in records:
            if want in record_name(row["rec"]).upper():
                return row
        raise MoveError(f"no name record contains {text!r}")
    if record is None:
        record = 0
    if not 0 <= record < len(records):
        raise MoveError(f"record {record} outside 0..{len(records) - 1}")
    return records[record]


def spatial_refs(blob: bytes) -> list[dict]:
    cells = {cell: (rec, blocks) for cell, rec, blocks in regen.directory(blob)}
    if CELL_SPATIAL not in cells:
        raise MoveError("the file has no spatial-tree directory cell (0x85a)")
    rec, blocks = cells[CELL_SPATIAL]
    return pc.read_ref_list(blob, rec, blocks * regen.BLOCK)


def leaf_slots(blob: bytes, ptr: int) -> list[tuple[int, int, int]]:
    """``(absolute position, key_x, key_y)`` of every leaf that points at *ptr*."""
    out = []
    for ref in spatial_refs(blob):
        base, words = ref["start"], ref["words"]
        stack = [(0, ref["root_words"], 0, (0, 0))]
        while stack:
            off, size, depth, key = stack.pop()
            if off + size > words:
                raise MoveError(f"spatial {base:#x}: node {off:#x}+{size:#x} outside the tree")
            pos, end = base + 2 * off, base + 2 * (off + size)
            while pos < end:
                (head,) = struct.unpack_from(">H", blob, pos)
                if head == 5:
                    pos += 10
                    continue
                if head != 8:
                    raise MoveError(f"spatial {base:#x}: entry head {head:#x} at {pos:#x}")
                _, leaf_ptr, csize, kx, ky, _ = pc.SPATIAL_ENTRY.unpack_from(blob, pos)
                if csize:
                    stack.append((leaf_ptr, csize, depth + 1,
                                  (kx, ky) if depth < pc.CELL_DEPTH else key))
                elif leaf_ptr == ptr:
                    out.append((pos, key[0], key[1]))
                pos += 16
    return out


# ---------------------------------------------------------------------------
# fine values


def request_fine(lat: float, lon: float) -> tuple[int, int, int, int]:
    """``(A.x, A.y, fine_lon_word, fine_lat_word)`` of a requested position."""
    return pc.encode_position(lat, lon)


def fine_candidates(flon: int, flat: int, span: int) -> list[tuple[int, int, int, int]]:
    """Fine pairs around ``(flon, flat)`` as ``(d_lon, d_lat, flon, flat)``,
    closest first, staying inside the 11-bit field."""
    out = []
    for dlon in range(-span, span + 1):
        for dlat in range(-span, span + 1):
            nlon, nlat = flon + dlon, flat + dlat
            if 0 <= nlon <= FINE_MAX and 0 <= nlat <= FINE_MAX:
                out.append((abs(dlon) + abs(dlat), dlon, dlat, nlon, nlat))
    out.sort()
    return [(dlon, dlat, nlon, nlat) for _, dlon, dlat, nlon, nlat in out]


def page_compress_fits(enc: regen.Encoder, inner: bytearray, slot: int) -> int | None:
    """Stream length when the page re-encodes into the same 4-byte slot."""
    stream = enc.compress(bytes(inner))
    if (len(stream) + regen.PAGE_PAD - 1) // regen.PAGE_PAD * regen.PAGE_PAD == slot:
        return len(stream)
    return None


def plan_move(blob: bytes, chain, row: dict, lat: float, lon: float,
              enc: regen.Encoder, span: int = DEFAULT_SEARCH,
              allow_nonreference: bool = False) -> dict:
    """Choose fine values for *row* at *lat*/*lon* that keep its page slot."""
    if not enc.is_reference and not allow_nonreference:
        raise MoveError(f"encoder zlib {enc.version} is not the pinned reference "
                        f"{regen.REFERENCE_ZLIB}; the slot check is not the factory one")
    rec = row["rec"]
    ax, ay, v6, v8 = struct.unpack_from(">4H", rec, 2)
    tx, ty, t6, t8 = request_fine(lat, lon)
    if (tx, ty) != (ax, ay):
        raise MoveError(
            f"target {lat},{lon} is in copy-A cell ({tx:#06x},{ty:#06x}), the record in "
            f"({ax:#06x},{ay:#06x}): moving across a cell is step 2 (not this tool)")
    flon, flat = t6 & FINE_MAX, t8 & FINE_MAX
    pi = row["page_index"]
    slot = chain.entries[pi][1] * 2
    best = None
    for dlon, dlat, nlon, nlat in fine_candidates(flon, flat, span):
        inner = bytearray(chain.pages[pi][2])
        struct.pack_into(">HH", inner, row["offset"] + 6, 0x800 | nlon, nlat)
        length = page_compress_fits(enc, inner, slot)
        if length is None:
            continue
        landed = struct.pack(">5H", 0, ax, ay, 0x800 | nlon, nlat)
        pla, plo = pc.fine_position(landed)
        distance = pc.haversine_m(lat, lon, pla, plo)
        if best is None or distance < best["distance_m"]:
            best = {"page_index": pi, "page": row["page"], "record": row["index"],
                    "offset": row["offset"], "old_lat": pc.fine_position(rec)[0],
                    "old_lon": pc.fine_position(rec)[1], "lat": pla, "lon": plo,
                    "request_lat": lat, "request_lon": lon, "distance_m": distance,
                    "d_lon": dlon, "d_lat": dlat, "flon": nlon, "flat": nlat,
                    "cell": [ax, ay], "slot": slot, "stream": length,
                    "candidates": (2 * span + 1) ** 2}
        if distance <= TARGET_TOLERANCE_M:
            return best
    if best is not None:
        raise MoveError(
            f"page {row['page']:#x} keeps its {slot} B slot only in a sparse set of fine "
            f"pairs; the closest one decodes {best['distance_m']:.2f} m from the request "
            f"(> {TARGET_TOLERANCE_M:.0f} m). Grow the chain (relocate, M4.47) is not this "
            "tool's step; nothing written")
    raise MoveError(
        f"no fine pair within {span} steps of the request keeps page {row['page']:#x} "
        f"inside its {slot} B slot")


def apply_move(blob: bytes, chain, plan: dict, leaves: list[tuple[int, int, int]],
               move_record: bool, move_leaf: bool) -> bytes:
    """Re-pack the page and rewrite the leaf fine words; mutates a copy."""
    out = bytearray(blob)
    pi = plan["page_index"]
    new_inners = [p[2] for p in chain.pages]
    inner = bytearray(new_inners[pi])
    if move_record:
        struct.pack_into(">HH", inner, plan["offset"] + 6, 0x800 | plan["flon"], plan["flat"])
    new_inners[pi] = bytes(inner)
    olds = [blob[o:o + u] for o, u, _ in chain.pages]
    regen.regen_chain(out, chain, new_inners, EncoderRef.enc, olds, force=False)
    if move_leaf:
        if not leaves:
            raise MoveError(f"record {plan['record']} has no spatial-tree leaf to move")
        for pos, _, _ in leaves:
            old_fine = struct.unpack_from(">I", out, pos + 12)[0]
            hi = (old_fine >> 16) & 0xF800
            lo = old_fine & 0xF800
            new_fine = ((hi | (0x800 | plan["flon"])) << 16) | (lo | plan["flat"])
            struct.pack_into(">I", out, pos + 12, new_fine)
    return bytes(out)


class EncoderRef:
    """The encoder of the current build (set by :func:`run_move`)."""

    enc: regen.Encoder


# ---------------------------------------------------------------------------
# pair I/O


def read_pair(cmp_path: Path) -> tuple[bytes, bytes, list[int], int, int]:
    usize, csize, count, chunk, offsets = cmpind_codec.read_ind(
        cmp_path.with_suffix(".IND") if not cmp_path.with_suffix(".ind").exists()
        else cmp_path.with_suffix(".ind"))
    packed = cmp_path.read_bytes()
    if csize != len(packed):
        raise MoveError(f"{cmp_path.name}: .ind says {csize} B, file has {len(packed)}")
    blob = cmpind_codec.decode_blob(packed, offsets, usize=usize, chunk_size=chunk,
                                    name=cmp_path.name)
    return blob, packed, list(offsets), usize, chunk


def write_pair(cmp_path: Path, outdir: Path, blob_old: bytes, blob_new: bytes,
               enc: regen.Encoder) -> tuple[Path, Path]:
    blob, packed, offsets, usize, chunk = read_pair(cmp_path)
    if len(blob) != len(blob_new):
        raise MoveError("the move changed the decoded size; only an in-place move is allowed")
    cmp_bytes, ind_bytes = cmpind_codec.rebuild_pair_bytes(
        packed, offsets, usize, chunk, blob_old, blob_new, compress=enc.compress)
    outdir.mkdir(parents=True, exist_ok=True)
    cmp_out = outdir / cmp_path.name
    ind_out = outdir / cmp_path.name.replace(".CMP", ".IND") if ".CMP" in cmp_path.name \
        else outdir / cmp_path.with_suffix(".ind").name
    cmp_out.write_bytes(cmp_bytes)
    ind_out.write_bytes(ind_bytes)
    return cmp_out, ind_out


def verify_move(blob_old: bytes, blob_new: bytes, plan: dict, leaves, enc: regen.Encoder,
                move_record: bool, move_leaf: bool) -> dict:
    """Census, joins, position tolerance and the changed-byte envelope."""
    res = {"errors": []}
    try:
        rep = pc.census(blob_new, want_joins=True)
    except (pc.CensusError, struct.error, ValueError) as exc:
        res["errors"].append(f"census raises: {exc}")
        return res
    res["census_ok"] = rep["ok"]
    res["unaccounted"] = rep["classes"].get("unaccounted", 0)
    if not rep["ok"]:
        res["errors"].append("census failed: " + "; ".join(t for t, ok in rep["checks"] if not ok))
    j = rep["joins"]
    sp = j["spatial"]
    res["leaves"] = sp["leaves"]
    res["leaf_match"] = sp["match"]
    res["joins_ok"] = (sp["match"] == sp["leaves"] and j["index"]["match"] == j["index"]["records"]
                       and j["marker"]["fine_out_of_form"] == 0
                       and j.get("phone", {}).get("match", 0) == j.get("phone", {}).get("keys", 0))
    if not res["joins_ok"]:
        res["errors"].append(f"joins fail: spatial {sp['match']}/{sp['leaves']}, "
                             f"index {j['index']['match']}/{j['index']['records']}")
    recs = name_records(blob_new, regen.chain_via_locator(blob_new, NAME_CHAIN))
    lat, lon = pc.fine_position(recs[plan["record"]]["rec"])
    res["lat"], res["lon"] = lat, lon
    res["distance_m"] = pc.haversine_m(plan["request_lat"], plan["request_lon"], lat, lon)
    if res["distance_m"] > TARGET_TOLERANCE_M:
        res["errors"].append(f"moved record decodes {res['distance_m']:.2f} m from the request")
    # the changed bytes must stay inside the touched page's 4-byte slot and the leaves
    chain = regen.chain_via_locator(blob_new, NAME_CHAIN)
    page_off = chain.pages[plan["page_index"]][0]
    page_slot = chain.entries[plan["page_index"]][1] * 2
    allowed = [(page_off, page_off + page_slot)] + [(p + 12, p + 16) for p, _, _ in leaves]
    changed = outside = 0
    outside_positions = []
    for i, (a, b) in enumerate(zip(blob_old, blob_new)):
        if a == b:
            continue
        changed += 1
        if not any(s <= i < e for s, e in allowed):
            outside += 1
            outside_positions.append(i)
    res["changed_bytes"] = changed
    res["outside_bytes"] = outside
    res["outside_positions"] = [hex(p) for p in outside_positions[:16]]
    if outside:
        res["errors"].append(f"{outside} bytes changed outside the touched page stream and leaves")
    res["table_unchanged"] = (blob_old[chain.toc:chain.toc + chain.toc_size]
                              == blob_new[chain.toc:chain.toc + chain.toc_size])
    if not res["table_unchanged"]:
        res["errors"].append("the chain table changed although no page grew")
    res["ok"] = not res["errors"] and (move_record and move_leaf)
    return res


# ---------------------------------------------------------------------------
# driver


def run_move(args) -> int:
    enc = regen.Encoder(args.libz)
    EncoderRef.enc = enc
    if not enc.is_reference and not args.allow_nonreference:
        print(f"encoder: {enc.describe()} is not stock zlib {regen.REFERENCE_ZLIB}; refusing "
              "(pass --libz PATH to a stock 1.3.1 libz)", file=sys.stderr)
        return zlibinfo.EXIT_UNVERIFIABLE
    print(f"encoder: zlib {enc.version} via {enc.source}")
    cmp_path = Path(args.cmp)
    blob, packed, offsets, usize, chunk = read_pair(cmp_path)
    chain = regen.chain_via_locator(blob, NAME_CHAIN)
    if chain is None:
        print(f"REFUSED: the per_page {NAME_CHAIN} locator does not lead to a verified chain")
        return 1
    bad = regen.check_factory_encoder(blob, chain, enc)
    if bad:
        print(f"REFUSED: encoder does not reproduce {len(bad)} of {len(chain.pages)} name pages "
              f"(first {bad[0]}); refusing to re-encode")
        return 1 if enc.is_reference else zlibinfo.EXIT_UNVERIFIABLE
    if args.noop:
        blob_new = blob
        cmp_new, ind_new = cmpind_codec.rebuild_pair_bytes(
            packed, offsets, usize, chunk, blob, blob_new, compress=enc.compress)
        ind_old = (cmp_path.with_suffix(".IND") if not cmp_path.with_suffix(".ind").exists()
                   else cmp_path.with_suffix(".ind")).read_bytes()
        print(f"no-op: decoded identical {blob_new == blob}, .cmp identical "
              f"{cmp_new == packed}, .ind identical {ind_new == ind_old}")
        out = Path(args.outdir)
        out.mkdir(parents=True, exist_ok=True)
        (out / cmp_path.name).write_bytes(cmp_new)
        name = cmp_path.name.replace(".CMP", ".IND") if ".CMP" in cmp_path.name \
            else cmp_path.with_suffix(".ind").name
        (out / name).write_bytes(ind_new)
        return 0 if (cmp_new == packed and ind_new == ind_old) else 1

    records = name_records(blob, chain)
    row = select_record(records, args.record, args.select)
    plan = plan_move(blob, chain, row, args.position[0], args.position[1], enc,
                     span=args.span)
    name = record_name(row["rec"])
    leaves = leaf_slots(blob, row["index"])
    move_record = args.control != "leave-record"
    move_leaf = args.control != "leave-leaf"
    blob_new = apply_move(blob, chain, plan, leaves, move_record, move_leaf)
    print(f"record {row['index']} {name!r} page {plan['page']:#x} at +{plan['offset']:#x}; "
          f"cell ({plan['cell'][0]:#06x},{plan['cell'][1]:#06x}); leaves {len(leaves)}")
    print(f"request {plan['request_lat']:.6f},{plan['request_lon']:.6f} -> "
          f"{plan['lat']:.6f},{plan['lon']:.6f} ({plan['distance_m']:.2f} m); fine "
          f"{plan['flon']}+{plan['d_lon']} {plan['flat']}+{plan['d_lat']}; "
          f"stream {plan['stream']}/{plan['slot']} B")
    res = verify_move(blob, blob_new, plan, leaves, enc, move_record, move_leaf)
    res["plan"] = plan
    cmp_out, ind_out = write_pair(cmp_path, Path(args.outdir), blob, blob_new, enc)
    res["cmp"] = str(cmp_out)
    res["ind"] = str(ind_out)
    res["sha256_cmp"] = hashlib.sha256(cmp_out.read_bytes()).hexdigest()
    if args.control:
        # a control is passing when the broken pair is refused for the right reason
        if args.control == "leave-leaf":
            good = res.get("joins_ok") is False and res["leaf_match"] < res["leaves"]
            print(f"control leave-leaf: spatial joins {res['leaf_match']}/{res['leaves']} "
                  f"(refused: {good}); census {res.get('census_ok')}; "
                  f"bytes changed outside {res.get('outside_bytes')}")
        else:
            good = res["distance_m"] > TARGET_TOLERANCE_M
            print(f"control leave-record: leaf moved without its record; the record still "
                  f"decodes {res['distance_m']:.2f} m away (refused: {good})")
        print("control:", "PASS" if good else "FAIL")
        if args.json:
            Path(args.json).write_text(json.dumps(res, indent=1))
        return 0 if good else 1
    print(f"census {'OK' if res.get('census_ok') else 'FAIL'} (unaccounted {res.get('unaccounted')}); "
          f"joins {'hold' if res.get('joins_ok') else 'FAIL'} "
          f"({res.get('leaf_match')}/{res.get('leaves')} leaves); "
          f"changed bytes {res.get('changed_bytes')} outside {res.get('outside_bytes')}; "
          f"table unchanged {res.get('table_unchanged')}")
    if args.json:
        Path(args.json).write_text(json.dumps(res, indent=1))
    for err in res["errors"][:8]:
        print("error:", err)
    print("verify:", "PASS" if res["ok"] else "FAIL")
    return 0 if res["ok"] else 1


# ---------------------------------------------------------------------------
# selftest (synthetic, no vendor bytes)


def synth_pair(enc: regen.Encoder, td: Path) -> tuple[Path, bytes]:
    blob, _ = pc.synth_blob()
    packed, offsets = cmpind_codec.encode_chunks(blob, 0x10000, compress=enc.compress)
    ind = cmpind_codec.build_ind(len(blob), len(packed), 0x10000, offsets)
    cmp_path = td / "POINT099.DAT.cmp"
    (td / "POINT099.DAT.ind").write_bytes(ind)
    cmp_path.write_bytes(packed)
    return cmp_path, blob


def selftest() -> int:
    import tempfile
    fails = []

    def ok(cond, label):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    enc = regen.Encoder(None)
    EncoderRef.enc = enc
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        cmp_path, blob = synth_pair(enc, td)
        chain = regen.chain_via_locator(blob, NAME_CHAIN)
        ok(chain is not None and len(chain.pages) == 1, "synthetic name chain is located")
        records = name_records(blob, chain)
        ok(len(records) == 2, "synthetic file has two name records")
        rep = pc.census(blob, want_joins=True)
        ok(rep["ok"] and rep["joins"]["spatial"]["match"] == 2, "synthetic census and joins pass")

        # no-op keeps every factory stream (the unchanged page is copied, not
        # re-encoded; a re-encode differs in the zlib header byte because the
        # synthetic file was compressed by this runtime, not 1.3.1)
        for per in (1000, 400, 2000):
            that = regen.chain_via_locator(blob, per)
            inners = [p[2] for p in that.pages]
            streams = [blob[o:o + u] for o, u, _ in that.pages]
            body, entries = regen.pack_chain(that, inners, enc, streams)
            ok(body == blob[that.base:that.end] and entries == that.entries,
               f"a no-op re-pack of chain {per} keeps every factory stream")

        row = records[0]
        ax, ay, v6, v8 = struct.unpack_from(">4H", row["rec"], 2)
        old_lat, old_lon = pc.fine_position(row["rec"])
        target = (old_lat + 0.00002, old_lon + 0.00002)
        plan = plan_move(blob, chain, row, *target, enc, allow_nonreference=True)
        ok((plan["cell"][0], plan["cell"][1]) == (ax, ay), "the plan stays inside the copy-A cell")
        ok(plan["distance_m"] <= TARGET_TOLERANCE_M, "the plan decodes within 2 m of the request")
        leaves = leaf_slots(blob, row["index"])
        ok(len(leaves) == 1, "the record owns one spatial leaf")
        moved = apply_move(blob, chain, plan, leaves, True, True)
        res = verify_move(blob, moved, plan, leaves, enc, True, True)
        ok(res["ok"], "moving the record and its leaf verifies: " + "; ".join(res["errors"]))
        ok(res["changed_bytes"] > 0 and res["outside_bytes"] == 0,
           "every changed byte is inside the touched page stream or a leaf")
        ok(res["table_unchanged"], "the chain table did not change")
        ok(res["lat"] == plan["lat"] and res["lon"] == plan["lon"], "the output decodes to the plan")
        moved_again = apply_move(blob, chain, plan, leaves, True, True)
        ok(moved_again == moved, "a repeated move is byte-identical (deterministic re-encode)")

        # negative control: the record moved, the leaf left -> joins refuse
        broken = apply_move(blob, chain, plan, leaves, True, False)
        r = verify_move(blob, broken, plan, leaves, enc, True, False)
        ok((not r["joins_ok"]) and r["leaf_match"] < r["leaves"],
           "negative: a moved record with its leaf left is refused by joins")
        # negative control: the leaf moved, the record left -> the record does not decode to the target
        broken2 = apply_move(blob, chain, plan, leaves, False, True)
        r2 = verify_move(blob, broken2, plan, leaves, enc, False, True)
        ok(r2["distance_m"] > TARGET_TOLERANCE_M,
           "negative: a moved leaf without its record does not reach the target")

        # refusal: a target in another copy-A cell
        far = (old_lat + 0.5, old_lon + 0.5)
        try:
            plan_move(blob, chain, row, *far, enc, allow_nonreference=True)
            ok(False, "a target in another cell is refused")
        except MoveError as exc:
            ok("step 2" in str(exc), "a target in another cell is refused and names step 2")
        # refusal: a non-factory encoder is refused before any plan is made
        class Wrong(regen.Encoder):
            def compress(self, data):
                return __import__("zlib").compress(data, 1)
        plan_move(blob, chain, row, *target, enc, allow_nonreference=True)
        try:
            plan_move(blob, chain, row, *target, Wrong(None))
            ok(False, "a non-factory encoder is refused")
        except MoveError as exc:
            ok("not the pinned reference" in str(exc),
               "a non-factory encoder is refused before the slot check")
        # no leaf -> refused
        try:
            apply_move(blob, chain, plan, [], True, True)
            ok(False, "a record with no leaf is refused")
        except MoveError as exc:
            ok("no spatial-tree leaf" in str(exc), "a record with no leaf is refused")

        # the written pair decodes to the moved bytes
        cmp_out, ind_out = write_pair(cmp_path, td / "out", blob, moved, enc)
        dec, *rest = cmpind_codec.decode(cmp_out, ind_out)
        ok(dec == moved, "the written pair decodes to the moved file")

    print("point_move_poi selftest: " + ("OK" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("cmp", nargs="?", help="POINTnnn.DAT.cmp of the input pair")
    ap.add_argument("outdir", nargs="?", help="directory for the rebuilt pair")
    ap.add_argument("--position", nargs=2, type=float, metavar=("LAT", "LON"),
                    help="requested position of the moved POI")
    g = ap.add_mutually_exclusive_group(required=False)
    g.add_argument("--record", type=int, help="record ordinal in chain order (default 0)")
    g.add_argument("--select", help="first name record whose name contains TEXT")
    ap.add_argument("--noop", action="store_true", help="control: re-pack every page with itself")
    ap.add_argument("--control", choices=("leave-leaf", "leave-record"),
                    help="write a broken pair and expect the matching check to refuse it")
    ap.add_argument("--span", type=int, default=DEFAULT_SEARCH,
                    help=f"fine steps searched around the request (default {DEFAULT_SEARCH}, "
                         "each step ~1.1 m; a wider span reaches further but takes longer)")
    ap.add_argument("--libz", help="stock zlib shared library to compress with (ctypes)")
    ap.add_argument("--allow-nonreference", action="store_true",
                    help="accept a stock zlib other than 1.3.1 (the factory check still runs)")
    ap.add_argument("--json")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmp or not args.outdir:
        ap.print_help()
        return 2
    if not args.noop and not args.position:
        ap.error("--position is required unless --noop")
    try:
        return run_move(args)
    except MoveError as exc:
        print(f"REFUSED: {exc}")
        return 1
    except cmpind_codec.FormatError as exc:
        print(f"REFUSED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
