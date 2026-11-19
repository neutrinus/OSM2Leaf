#!/usr/bin/env python3
"""Differential census of ``MAPAL001`` map tiles across the three EU editions
(2011, 2014, 2016) for M4.41.

M4.41 is a **census, not an interpretation**: for every ``BxxRyyR.DAT`` of two
editions it reports, per section, the size and SHA-256 of the section span and
the record counts, then how many records were kept / changed / added / removed.
For the tiles with the smallest non-zero section-1 change it names the
added/removed section-1 records and the byte ranges that changed in sections 2
and 4.  The output only says *what changes together with what*; the "one
variable" pairs are handed to M4.40 / M4.36 / the section-4 reader.

Section framing
---------------
A tile is a 0x1000-byte header (``docs/format/map-tiles.md``) followed by one
span per section.  The span starts at the section-table address the container
declares (``clarion_tile.read_tile``) and ends at the next section's start (the
last section runs to EOF), so each section's size and SHA-256 are computed over
the bytes the firmware container maps to that section -- directory tables,
slot bodies, block streams and their inter-record gaps included.

Record identity
---------------
A record is a zlib stream the container reaches (``tile_diff``), inflated and
hashed on its *plain* bytes, so a recompression is not a change.  Because the
factory re-packs a tile between editions, the same logical record can appear at
a different slot, directory row/column, record index and file offset.  Records
are therefore matched in this order:

1. **kept** -- same plain SHA-256 (content), counted as a multiset;
2. **changed** -- for content-leftovers, same *identity* (section, level,
   directory row/column, slot) and same first-4-byte id (section 1/4 parcel,
   section 2 node word); the plain bytes differ but it is one edited record;
3. **added / removed** -- whatever is left after 1 and 2.

Without step 2 a shifted coordinate or a moved block reads as hundreds of
add + remove pairs; the identity match is what makes an "added road" countable.

Usage::

    python3 tools/diff_years_tiles.py A B [--json] [--top 20] [--pairs]
    python3 tools/diff_years_tiles.py --selftest

``A`` and ``B`` are card roots, raw images, or extracted ``MAPAL001``
directories.  Exit 0 when the census ran (differences are data, not an error),
2 on usage/IO error or a failed self-test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import tempfile
import zlib
from collections import Counter
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "ze0-viewer" / "tools_ze0"))

import cardcheck  # noqa: E402
import tile_diff  # noqa: E402

MAPAL = "MAPAL001"
TILE_NAME = re.compile(r"^B[0-9A-F]{2}R[0-9A-F]{3}R\.DAT$", re.IGNORECASE)
MAX_RANGES = 64


# ---------------------------------------------------------------------------
# sources


def open_source(path: str | Path):
    target = Path(path)
    if target.is_dir():
        return cardcheck.RootSource(target)
    return cardcheck.Fat32Image(target)


def read_tile(source, name: str) -> bytes:
    rel = f"{MAPAL}/{name}"
    if isinstance(source, cardcheck.RootSource):
        direct = Path(source.root) / name
        if direct.is_file():
            return direct.read_bytes()
    return source.read(rel)


def tile_names(source) -> set[str]:
    names = set()
    if isinstance(source, cardcheck.RootSource):
        for path in Path(source.root).glob("*.DAT"):
            if TILE_NAME.match(path.name):
                names.add(path.name)
    if names:
        return names
    for entry in source.walk():
        if entry.is_dir:
            continue
        parts = entry.path.split("/")
        if (len(parts) == 2 and parts[0] == MAPAL
                and TILE_NAME.match(parts[1])):
            names.add(parts[1])
    return names


# ---------------------------------------------------------------------------
# section framing and record scan


def section_bounds(tile, blob: bytes):
    """``[(sid, start, end)]`` from the read-time section-table addresses."""
    starts = sorted((sec["taddr"], sec["id"]) for sec in tile["sections"])
    out = []
    for i, (start, sid) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(blob)
        out.append((sid, start, end))
    return out


def scan_records(blob: bytes, tile_mod):
    """Walk the container and hash every reachable record's plain bytes.

    Returns ``(tile, {sid: [row, ...]})``.  A row is ``{sha, plen, clen, off,
    pos, key}`` where ``key`` is the logical identity ``(level, y, x, slot,
    id)`` and ``id`` is the first 4 plain bytes (section 1/4 parcel, section 2
    node word).  The plain bytes are not kept, so a large tile stays bounded.
    """
    tile = tile_mod.read_tile(blob)
    rows: dict[int, list[dict]] = {}
    for sec in tile["sections"]:
        sid = sec["id"]
        items = []
        for level in sec["levels"]:
            for directory in level["dirs"]:
                for slot_i in sorted(directory["slots"]):
                    slot = directory["slots"][slot_i]
                    cursor = slot["block_off"]
                    for k, rec in enumerate(slot["recs"]):
                        raw = rec["raw"]
                        plain = None
                        if tile_mod.is_zlib(raw):
                            try:
                                plain = zlib.decompress(raw)
                            except zlib.error:
                                plain = None
                        if plain is None:
                            sha = "raw:" + hashlib.sha256(raw).hexdigest()
                            plen = len(raw)
                            ident = None
                        else:
                            sha = hashlib.sha256(plain).hexdigest()
                            plen = len(plain)
                            ident = plain[:4].hex() if len(plain) >= 4 else ""
                        items.append({
                            "sha": sha,
                            "plen": plen,
                            "clen": len(raw),
                            "off": cursor,
                            "pos": [sid, level["level"], directory["y"],
                                    directory["x"], slot_i, k],
                            "key": (level["level"], directory["y"],
                                    directory["x"], slot_i, ident),
                        })
                        cursor += len(raw)
        items.sort(key=lambda row: row["off"])
        rows[sid] = items
    return tile, rows


def resolve_plains(blob: bytes, tile_mod, wanted: set[str]):
    """Re-inflate records whose plain SHA is in ``wanted`` (first hit each)."""
    found: dict[str, bytes] = {}
    tile = tile_mod.read_tile(blob)
    for sec in tile["sections"]:
        for level in sec["levels"]:
            for directory in level["dirs"]:
                for slot in directory["slots"].values():
                    for rec in slot["recs"]:
                        raw = rec["raw"]
                        if not tile_mod.is_zlib(raw):
                            continue
                        try:
                            plain = zlib.decompress(raw)
                        except zlib.error:
                            continue
                        sha = hashlib.sha256(plain).hexdigest()
                        if sha in wanted and sha not in found:
                            found[sha] = plain
    return found


# ---------------------------------------------------------------------------
# per-section comparison


def classify_section(a_rows, b_rows):
    """Kept / changed / added / removed counts for one section.

    1. *kept* = plain-SHA multiset intersection;
    2. *changed* = content-leftovers sharing a logical ``key`` (same level,
       directory, slot and first-4-byte id) -- one edited record, not add+remove;
    3. *added* / *removed* = the rest, still counted by ``key`` so a duplicate
       record inside one slot is handled as a multiset.
    Returns ``(counts, leftover_a, leftover_b, changed_keys)``; the leftover
    lists are the rows still unmatched after step 1.
    """
    ca = Counter(row["sha"] for row in a_rows)
    cb = Counter(row["sha"] for row in b_rows)
    kept = sum(min(ca[s], cb[s]) for s in set(ca) | set(cb))

    need_a = Counter((row["sha"] for row in a_rows))
    for sha, n in Counter((row["sha"] for row in b_rows)).items():
        if sha in need_a:
            need_a[sha] = max(0, need_a[sha] - n)

    def leftover(rows, need):
        used = Counter(need)
        out = []
        for row in rows:
            if used[row["sha"]] > 0:
                used[row["sha"]] -= 1
                out.append(row)
        return out

    need_b = Counter((row["sha"] for row in b_rows))
    for sha, n in Counter((row["sha"] for row in a_rows)).items():
        if sha in need_b:
            need_b[sha] = max(0, need_b[sha] - n)

    left_a = leftover(a_rows, need_a)
    left_b = leftover(b_rows, need_b)

    ka = Counter(row["key"] for row in left_a)
    kb = Counter(row["key"] for row in left_b)
    changed = sum(min(ka[k], kb[k]) for k in set(ka) | set(kb))
    added = sum(max(0, kb[k] - ka.get(k, 0)) for k in kb)
    removed = sum(max(0, ka[k] - kb.get(k, 0)) for k in ka)

    counts = {"kept": kept, "changed": changed, "added": added,
              "removed": removed}
    return counts, left_a, left_b


def unmatched_rows(left_a, left_b, side: str):
    """Rows of one side not explained by a same-key partner (added/removed)."""
    match = left_a if side == "removed" else left_b
    other = left_b if side == "removed" else left_a
    ko = Counter(row["key"] for row in other)
    out = []
    for row in match:
        if ko[row["key"]] > 0:
            ko[row["key"]] -= 1
        else:
            out.append(row)
    return out


def section_size(bounds, blob, sid):
    for s, start, end in bounds:
        if s == sid:
            return end - start, start, end
    return 0, 0, 0


def byte_diff(a: bytes, b: bytes, max_ranges: int = MAX_RANGES):
    """Differing byte count and merged ``[start, end)`` ranges between slices."""
    size = max(len(a), len(b))
    differing = 0
    ranges: list[list[int]] = []
    last_end = -1
    for i in range(size):
        x = a[i] if i < len(a) else None
        y = b[i] if i < len(b) else None
        if x == y:
            continue
        differing += 1
        if ranges and i == last_end:
            ranges[-1][1] = i + 1
        elif len(ranges) < max_ranges:
            ranges.append([i, i + 1])
        last_end = i + 1
    return differing, ranges


# ---------------------------------------------------------------------------
# census


def census(A, B, name: str, tile_mod):
    """One tile pair: per-section sizes, hashes and record deltas."""
    blob_a = read_tile(A, name)
    blob_b = read_tile(B, name)
    sha_a = hashlib.sha256(blob_a).hexdigest()
    sha_b = hashlib.sha256(blob_b).hexdigest()
    tile_a, rows_a = scan_records(blob_a, tile_mod)
    tile_b, rows_b = scan_records(blob_b, tile_mod)
    bounds_a = section_bounds(tile_a, blob_a)
    bounds_b = section_bounds(tile_b, blob_b)
    section_ids = sorted(set([s for s, _, _ in bounds_a]) |
                         set([s for s, _, _ in bounds_b]))

    sections: dict[int, dict] = {}
    for sid in section_ids:
        size_a, start_a, end_a = section_size(bounds_a, blob_a, sid)
        size_b, start_b, end_b = section_size(bounds_b, blob_b, sid)
        counts, _, _ = classify_section(rows_a.get(sid, []),
                                        rows_b.get(sid, []))
        if all(counts[k] == 0 for k in ("kept", "changed", "added",
                                        "removed")):
            continue
        sections[sid] = {
            "size_a": size_a,
            "size_b": size_b,
            "sha_a": hashlib.sha256(blob_a[start_a:end_a]).hexdigest(),
            "sha_b": hashlib.sha256(blob_b[start_b:end_b]).hexdigest(),
            "start_a": start_a,
            "start_b": start_b,
            "records_a": len(rows_a.get(sid, [])),
            "records_b": len(rows_b.get(sid, [])),
            **counts,
            "delta": counts["changed"] + counts["added"] + counts["removed"],
            "add_rem": counts["added"] + counts["removed"],
        }

    sec1 = sections.get(1, {})
    return {
        "tile": name,
        "size_a": len(blob_a),
        "size_b": len(blob_b),
        "sha_a": sha_a,
        "sha_b": sha_b,
        "identical": sha_a == sha_b,
        "sections": sections,
        "sec1_delta": sec1.get("delta", 0),
        "sec1_add_rem": sec1.get("add_rem", 0),
        "sec1_added": sec1.get("added", 0),
        "sec1_removed": sec1.get("removed", 0),
        "sec1_changed": sec1.get("changed", 0),
    }


def detail(A, B, name: str, tile_mod, bg_mod, sec4_mod):
    """Name the section-1/2/4 add/remove records of one tile."""
    blob_a = read_tile(A, name)
    blob_b = read_tile(B, name)
    tile_a, rows_a = scan_records(blob_a, tile_mod)
    tile_b, rows_b = scan_records(blob_b, tile_mod)
    bounds_a = section_bounds(tile_a, blob_a)
    bounds_b = section_bounds(tile_b, blob_b)
    out = {"tile": name, "sections": {}}

    for sid in (1, 2, 4):
        counts, left_a, left_b = classify_section(rows_a.get(sid, []),
                                                  rows_b.get(sid, []))
        size_a, start_a, end_a = section_size(bounds_a, blob_a, sid)
        size_b, start_b, end_b = section_size(bounds_b, blob_b, sid)
        if size_a == 0 and size_b == 0 and not any(counts.values()):
            continue
        differ, ranges = byte_diff(blob_a[start_a:end_a], blob_b[start_b:end_b])
        added = unmatched_rows(left_a, left_b, "added")
        removed = unmatched_rows(left_a, left_b, "removed")

        rec = {
            "size_a": size_a,
            "size_b": size_b,
            "bytes_differing": differ,
            "changed_ranges": ranges,
            **counts,
            "added_rows": added,
            "removed_rows": removed,
        }
        if sid == 1:
            wa = {r["sha"] for r in removed}
            wb = {r["sha"] for r in added}
            pa = resolve_plains(blob_a, tile_mod, wa)
            pb = resolve_plains(blob_b, tile_mod, wb)
            rec["removed_named"] = [_name_sec1(r, pa.get(r["sha"]), bg_mod)
                                    for r in removed]
            rec["added_named"] = [_name_sec1(r, pb.get(r["sha"]), bg_mod)
                                  for r in added]
        if sid == 4:
            wa = {r["sha"] for r in removed}
            wb = {r["sha"] for r in added}
            pa = resolve_plains(blob_a, tile_mod, wa)
            pb = resolve_plains(blob_b, tile_mod, wb)
            rec["removed_named"] = [_name_sec4(r, pa.get(r["sha"]), sec4_mod)
                                    for r in removed]
            rec["added_named"] = [_name_sec4(r, pb.get(r["sha"]), sec4_mod)
                                  for r in added]
        out["sections"][sid] = rec

    out["class"] = _classify(out)
    return out


def _parcel_words(plain):
    if plain is None or len(plain) < 4:
        return None
    w0, w1 = struct.unpack_from(">HH", plain, 0)
    return [w0, w1]


def _name_sec1(row, plain, bg_mod):
    item = {"pos": row["pos"], "off": row["off"], "plen": row["plen"]}
    item["parcel"] = _parcel_words(plain)
    item["type"] = None
    if plain is not None and bg_mod is not None:
        try:
            item["type"] = bg_mod.parse_record(plain)["hdr"][2]
        except Exception:
            pass
    return item


def _name_sec4(row, plain, sec4_mod):
    item = {"pos": row["pos"], "off": row["off"], "plen": row["plen"],
            "parcel": _parcel_words(plain), "names": []}
    if plain is not None and sec4_mod is not None:
        try:
            rec = sec4_mod.parse_record(plain, 0, "zlib", 7)
            item["parcel"] = [rec["parcel_w0"], rec["parcel_w1"]]
            item["names"] = [n["text"] for n in rec["names"]]
        except Exception:
            pass
    return item


def _classify(detail_out):
    """Label the tile from its own section add/remove counts (census only)."""
    sec = detail_out["sections"]
    s1 = sec.get(1, {})
    s2 = sec.get(2, {})
    s4 = sec.get(4, {})
    ar1 = s1.get("added", 0) + s1.get("removed", 0)
    ch1 = s1.get("changed", 0)
    ar4 = s4.get("added", 0) + s4.get("removed", 0)
    ch4 = s4.get("changed", 0)
    d2 = s2.get("bytes_differing", 0)
    labels = []
    if ar1 == 0 and ch1 == 0 and d2 > 0 and ar4 == 0 and ch4 == 0:
        labels.append("routing-only")
    if ar1 == 1 and d2 == 0 and ar4 == 0 and ch4 == 0:
        labels.append("one-section1-record")
    if ar1 == 0 and ch1 == 0 and d2 == 0 and ar4 > 0:
        labels.append("section4-only")
    if ar1 == 1 and ar4 == 1:
        labels.append("one-add-all-sections")
    return labels


# ---------------------------------------------------------------------------
# driver


def run(a_path, b_path, top=20, want_pairs=False):
    mods = tile_diff.ze0()
    if mods is None:
        raise RuntimeError("tools/ze0-viewer/tools_ze0 is not available")
    tile_mod, bg_mod = mods
    sec4_mod = tile_diff.section4_module()

    A = open_source(a_path)
    B = open_source(b_path)
    try:
        names = sorted(tile_names(A) & tile_names(B))
        rows = [census(A, B, name, tile_mod) for name in names]
    finally:
        A.close()
        B.close()

    changed = [r for r in rows if r["sec1_delta"] > 0]
    changed.sort(key=lambda r: (r["sec1_add_rem"], r["sec1_delta"], r["tile"]))
    selected = [r["tile"] for r in changed[:top]]

    A = open_source(a_path)
    B = open_source(b_path)
    try:
        details = [detail(A, B, name, tile_mod, bg_mod, sec4_mod)
                   for name in selected]
    finally:
        A.close()
        B.close()

    totals = {
        "tiles": len(rows),
        "tiles_identical": sum(1 for r in rows if r["identical"]),
        "tiles_sec1_changed": sum(1 for r in rows
                                  if r["sec1_delta"] > 0),
    }
    for sid in (1, 2, 4):
        for key in ("kept", "changed", "added", "removed"):
            totals[f"sec{sid}_{key}"] = sum(
                r["sections"].get(sid, {}).get(key, 0) for r in rows)
        totals[f"sec{sid}_changed_tiles"] = sum(
            1 for r in rows if r["sections"].get(sid, {}).get("delta", 0) > 0)

    pairs = []
    if want_pairs:
        for d in details:
            for label in d["class"]:
                pairs.append({"tile": d["tile"], "class": label})

    return {
        "format": "diff-years-tiles/1",
        "a": str(a_path),
        "b": str(b_path),
        "totals": totals,
        "tiles": rows,
        "selected": selected,
        "details": details,
        "pairs": pairs,
    }


def render_text(result: dict) -> str:
    lines = [f"A: {result['a']}", f"B: {result['b']}"]
    t = result["totals"]
    lines.append(
        f"census: tiles={t['tiles']} identical={t['tiles_identical']} "
        f"sec1_changed={t['tiles_sec1_changed']}")
    for sid in (1, 2, 4):
        lines.append(
            f"  sec{sid}: kept={t[f'sec{sid}_kept']} "
            f"changed={t[f'sec{sid}_changed']} "
            f"added={t[f'sec{sid}_added']} removed={t[f'sec{sid}_removed']} "
            f"tiles_changed={t[f'sec{sid}_changed_tiles']}")
    lines.append("")
    lines.append("per-tile census (kept/changed/added/removed per section):")
    for r in sorted(result["tiles"], key=lambda x: x["tile"]):
        cells = []
        for sid in (1, 2, 4):
            d = r["sections"].get(sid, {})
            cells.append(
                f"s{sid}={d.get('kept', 0)}/{d.get('changed', 0)}/"
                f"{d.get('added', 0)}/{d.get('removed', 0)}")
        lines.append(f"  {r['tile']:<12} {r['size_a']}/{r['size_b']} "
                     + "  ".join(cells))
    lines.append("")
    lines.append("tiles with the smallest non-zero section-1 change "
                 "(add+remove first, then edits):")
    for d in result["details"]:
        s = d["sections"]
        s1 = s.get(1, {})
        s2 = s.get(2, {})
        s4 = s.get(4, {})
        lines.append(
            f"  {d['tile']}: sec1 +{s1.get('added', 0)}"
            f"/-{s1.get('removed', 0)} (changed {s1.get('changed', 0)})  "
            f"sec2_diff={s2.get('bytes_differing', 0)}B  "
            f"sec4 +{s4.get('added', 0)}/-{s4.get('removed', 0)}  "
            f"class={','.join(d['class']) or '-'}")
    if result["pairs"]:
        lines.append("")
        lines.append("pair candidates:")
        for p in result["pairs"]:
            lines.append(f"  {p['class']:<24} {p['tile']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# self-test (synthetic tiles, no vendor data)


def selftest() -> int:
    failures = []
    if tile_diff.ze0() is None:
        print("SKIP: tools/ze0-viewer/tools_ze0 is not available")
        return 2
    tile_mod, bg_mod = tile_diff.ze0()

    def check(name, cond):
        print(f"  {'ok  ' if cond else 'FAIL'} {name}")
        if not cond:
            failures.append(name)

    with tempfile.TemporaryDirectory(prefix="diff-years-tiles-") as tmp:
        path_a, path_b, facts = tile_diff.make_synthetic_tiles(Path(tmp))
        dir_a = Path(tmp) / "A"
        dir_b = Path(tmp) / "B"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "B48R058R.DAT").write_bytes(path_a.read_bytes())
        (dir_b / "B48R058R.DAT").write_bytes(path_b.read_bytes())
        result = run(dir_a, dir_b, top=10)

        check("one tile compared", result["totals"]["tiles"] == 1)
        check("tile reported changed",
              result["totals"]["tiles_sec1_changed"] == 1)
        d = result["details"][0]["sections"].get(1, {})
        check("in-place vertex edit is one changed record",
              d.get("changed", 0) == 1)
        check("in-place vertex edit adds nothing", d.get("added", 0) == 0)
        check("in-place vertex edit removes nothing", d.get("removed", 0) == 0)
        check("byte ranges found", d.get("bytes_differing", 0) > 0)

        # A genuine added record: B carries one extra directory/record.
        plains = [
            tile_diff._background_record(bg_mod, [(300, 400), (340, 440),
                                                  (300, 440)]),
            tile_diff._background_record(bg_mod, [(350, 500), (390, 540),
                                                  (350, 540)]),
        ]
        extra = tile_diff._background_record(bg_mod, [(400, 600), (440, 640),
                                                      (400, 640)])
        add_a, add_b = Path(tmp) / "add_a", Path(tmp) / "add_b"
        add_a.mkdir()
        add_b.mkdir()
        (add_a / "B48R058R.DAT").write_bytes(
            tile_diff._synthetic_tile(tile_mod, plains))
        (add_b / "B48R058R.DAT").write_bytes(
            tile_diff._synthetic_tile(tile_mod, plains + [extra]))
        res2 = run(add_a, add_b, top=10)
        d2 = res2["details"][0]["sections"].get(1, {})
        check("extra record is one added section-1 record",
              d2.get("added", 0) == 1)
        check("extra record removes nothing", d2.get("removed", 0) == 0)
        check("extra record keeps the old ones", d2.get("kept", 0) == 2)
    print(f"selftest: {'OK' if not failures else 'FAIL'} "
          f"({len(failures)} failure(s))")
    return 0 if not failures else 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Per-section differential census of MAPAL001 tiles (M4.41).")
    parser.add_argument("a", nargs="?", help="first card root, image or "
                        "MAPAL001 directory")
    parser.add_argument("b", nargs="?", help="second card root, image or "
                        "MAPAL001 directory")
    parser.add_argument("--json", action="store_true", help="JSON report")
    parser.add_argument("--top", type=int, default=20,
                        help="tiles with the smallest non-zero section-1 "
                             "add+remove to detail (default 20)")
    parser.add_argument("--pairs", action="store_true",
                        help="list one-variable pair candidates")
    parser.add_argument("--selftest", action="store_true",
                        help="build synthetic tiles and verify")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.a or not args.b:
        parser.error("A and B are required (or use --selftest)")
    try:
        result = run(args.a, args.b, top=args.top, want_pairs=args.pairs)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(render_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
