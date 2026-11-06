#!/usr/bin/env python3
"""One-tile diff report: content-matched streams and named records (M5.9).

    tile_diff.py A B [--json] [--by-offset] [--block 4096]
    tile_diff.py --selftest

The default view matches streams by **content**:

  - a stream is *same* when its inflated SHA-256 matches; if it sits at a
    different file offset it is counted and listed as *moved*;
  - a stream present on both sides whose content changed is paired by its
    structural position (section, level, directory row/column, slot, record
    index) and listed once as *changed at A -> B*, never as remove + add, even
    when the new stream also moved;
  - only streams with no counterpart are *added* or *removed*.

Each changed pair is described with the layout the container declares, and for
a background (section 1) record with the layer/shape/vertex that moved.  A
section-4 record is named by parcel, type and country plus the name delta.

*Structural naming* needs the checked-in ``tools/ze0-viewer/tools_ze0`` package
(``clarion_tile`` for the container, ``clarion_bg`` for background records).
When it is absent, or a file does not parse, content matching still works and
the record fields are ``null``.  ``--by-offset`` prints the older offset-keyed
view (same / changed / added / removed at the same file offset), which is what
the M5.8 report used.  ``--selftest`` builds its own three-stream tile pair with
that package and uses no vendor data.

JSON keys are stable in this format (``"format": "tile-diff/2"``):

    format, identical
    a, b                 {path, size, sha256, streams, parsed}
    streams              {same, moved, changed, added, removed, reencoded}
    changed[]            {offset_a, offset_b, compressed_a, compressed_b,
                          sha256_a, sha256_b, plain_a, plain_b,
                          record_a, record_b, change}
    moved[]              {offset_a, offset_b, compressed_a, compressed_b,
                          sha256_a, sha256_b, plain_a, plain_b,
                          record_a, record_b, reencoded}
    added[], removed[]   {offset, compressed, sha256, plain, record}
    bytes                {differing, block, ranges, range_count}
    by_offset            {same, changed, added, removed, changed_detail[],
                          added_detail[], removed_detail[]}

``streams.same`` counts content matches that kept their offset;
``streams.reencoded`` counts matches whose inflated bytes are identical but
whose compressed bytes changed (a recompression, not an edit).  ``record`` is
``{section, level, dir, slot, rec}`` or ``null``; ``dir`` is ``[row, col]`` as
the directory table stores it.  Detail arrays are complete; only the text view
truncates (``DETAIL_LIMIT``).

Exit status: 0 when A and B are identical, 1 when they differ, 2 on error.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import struct
import sys
import zlib
from pathlib import Path

REPORT_FORMAT = "tile-diff/2"
TABLE1_OFF = 0x1000

# ``78 xx`` covers X08-02-00 (ZE0 2011 curves), ``58 85`` X08-03-00.
STREAM_START = re.compile(rb"\x78[\x01\x5e\x9c\xda]|\x58\x85")

#: Rows of detail in the text view; the JSON report is never truncated.
DETAIL_LIMIT = 50

_UNSET = object()
_ZE0 = _UNSET
_SECTION4 = _UNSET


# --------------------------------------------------------------------------
# Optional structural modules (checked-in, but never required for matching)
# --------------------------------------------------------------------------


def ze0():
    """Return ``(clarion_tile, clarion_bg)`` from ``tools_ze0`` or ``None``."""
    global _ZE0
    if _ZE0 is _UNSET:
        _ZE0 = None
        vendor = Path(__file__).resolve().parent / "ze0-viewer" / "tools_ze0"
        if (vendor / "clarion_tile.py").is_file():
            sys.path.insert(0, str(vendor))
            try:
                import clarion_bg  # noqa: F401  (imported for the module object)
                import clarion_tile  # noqa: F401
            except Exception:
                _ZE0 = None
            else:
                _ZE0 = (clarion_tile, clarion_bg)
    return _ZE0


def section4_module():
    """Return ``tools/section4.py`` as a module, or ``None``."""
    global _SECTION4
    if _SECTION4 is _UNSET:
        _SECTION4 = None
        path = Path(__file__).resolve().with_name("section4.py")
        if path.is_file():
            spec = importlib.util.spec_from_file_location("_tile_diff_section4", path)
            if spec is not None and spec.loader is not None:
                module = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(module)
                except Exception:
                    module = None
                _SECTION4 = module
    return _SECTION4


# --------------------------------------------------------------------------
# Stream inventory
# --------------------------------------------------------------------------


def clean_streams(blob: bytes):
    """Yield (offset, compressed_len, plain) for each clean zlib stream."""
    pos = 0
    view = memoryview(blob)
    for match in STREAM_START.finditer(blob):
        head = match.start()
        if head < pos:
            continue
        window = min(len(blob) - head, 4_000_000)
        obj = zlib.decompressobj()
        try:
            plain = obj.decompress(view[head:head + window])
        except zlib.error:
            continue
        if not obj.eof:
            continue
        clen = window - len(obj.unused_data)
        pos = head + clen
        yield head, clen, plain


def structural_index(blob: bytes, tile_mod):
    """Map file offset -> {record, plain, compressed} for declared records.

    The container walk names every zlib record it reaches, which is what turns
    a changed stream into "section/level/dir/slot/rec" instead of an offset.
    Returns ``(index, parsed)``; ``parsed`` is False when the walk failed.
    """
    found: dict[int, dict] = {}
    try:
        tile = tile_mod.read_tile(blob)
    except Exception:
        return found, False
    for sec in tile["sections"]:
        for level in sec["levels"]:
            for directory in level["dirs"]:
                for slot_i, slot in sorted(directory["slots"].items()):
                    cursor = slot["block_off"]
                    for rec in slot["recs"]:
                        raw = rec["raw"]
                        if tile_mod.is_zlib(raw):
                            try:
                                plain = zlib.decompress(raw)
                            except zlib.error:
                                plain = None
                            if plain is not None:
                                found[cursor] = {
                                    "plain": plain,
                                    "compressed": len(raw),
                                    "record": {
                                        "section": sec["id"],
                                        "level": level["level"],
                                        "dir": [directory["y"], directory["x"]],
                                        "slot": slot_i,
                                        "rec": rec["k"],
                                    },
                                }
                        cursor += len(raw)
    return found, True


def _stream(offset: int, plain: bytes, compressed: int, record, blob: bytes):
    return {
        "offset": offset,
        "plain": plain,
        "plain_len": len(plain),
        "compressed": compressed,
        "compressed_sha256": hashlib.sha256(
            blob[offset:offset + compressed]).hexdigest(),
        "sha256": hashlib.sha256(plain).hexdigest(),
        "record": record,
    }


def tile_streams(blob: bytes, tile_mod):
    """Sorted stream inventory plus whether the container parsed."""
    streams: dict[int, dict] = {}
    parsed = False
    if tile_mod is not None:
        index, parsed = structural_index(blob, tile_mod)
        for offset, item in index.items():
            streams[offset] = _stream(offset, item["plain"], item["compressed"],
                                      item["record"], blob)
    for offset, clen, plain in clean_streams(blob):
        if offset not in streams:
            streams[offset] = _stream(offset, plain, clen, None, blob)
    return [streams[offset] for offset in sorted(streams)], parsed


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------


def _position(stream):
    """(section, level, dir, slot, rec) of a stream, or None when unnamed."""
    record = stream["record"]
    if record is None:
        return None
    return (record["section"], record["level"], tuple(record["dir"]),
            record["slot"], record["rec"])


def match_streams(streams_a, streams_b):
    """Pair streams by content first, then by structural position.

    Returns ``{same, moved, changed, added, removed}`` where the first three
    are lists of ``(stream_a, stream_b)`` pairs.  A content match that changed
    offset is *moved*; a changed pair carries both offsets so a moved edit
    reads as one change at A -> B.
    """
    used = [False] * len(streams_b)
    by_hash: dict[str, list[int]] = {}
    for j, stream in enumerate(streams_b):
        by_hash.setdefault(stream["sha256"], []).append(j)

    same, moved, changed, removed = [], [], [], []
    unmatched_a = []
    for stream in streams_a:
        candidates = [j for j in by_hash.get(stream["sha256"], []) if not used[j]]
        if not candidates:
            unmatched_a.append(stream)
            continue
        position = _position(stream)
        pick = candidates[0]
        for j in candidates:
            if position is not None and _position(streams_b[j]) == position:
                pick = j
                break
        else:
            for j in candidates:
                if streams_b[j]["offset"] == stream["offset"]:
                    pick = j
                    break
        used[pick] = True
        pair = (stream, streams_b[pick])
        if stream["offset"] == streams_b[pick]["offset"]:
            same.append(pair)
        else:
            moved.append(pair)

    by_position: dict[tuple, list[int]] = {}
    for j, stream in enumerate(streams_b):
        if used[j]:
            continue
        position = _position(stream)
        if position is not None:
            by_position.setdefault(position, []).append(j)

    for stream in unmatched_a:
        position = _position(stream)
        partner = None
        if position is not None:
            candidates = by_position.get(position, [])
            while candidates:
                candidate = candidates.pop(0)
                if not used[candidate]:
                    partner = candidate
                    break
        if partner is None:
            # Offset pairing is only a fallback for unnamed streams: two named
            # records at one offset are different positions, not one edit.
            for j, other in enumerate(streams_b):
                if used[j] or other["offset"] != stream["offset"]:
                    continue
                if position is None or _position(other) is None:
                    partner = j
                    break
        if partner is None:
            removed.append(stream)
        else:
            used[partner] = True
            changed.append((stream, streams_b[partner]))

    added = [stream for j, stream in enumerate(streams_b) if not used[j]]
    return {"same": same, "moved": moved, "changed": changed,
            "added": added, "removed": removed}


# --------------------------------------------------------------------------
# Naming a content change
# --------------------------------------------------------------------------


def _vertex_change(plain_a: bytes, plain_b: bytes):
    """Name the layer/shape/vertex that moved in a background record, or None."""
    mods = ze0()
    if mods is None:
        return None
    bg_mod = mods[1]
    try:
        rec_a = bg_mod.parse_record(plain_a)
        rec_b = bg_mod.parse_record(plain_b)
    except Exception:
        return None
    layers_a, layers_b = rec_a["layers"], rec_b["layers"]
    for layer in sorted(set(layers_a) | set(layers_b)):
        group_a, group_b = layers_a.get(layer), layers_b.get(layer)
        if not group_a or not group_b:
            continue
        if "raw" in group_a or "raw" in group_b:
            continue
        groups_a = [group_a] + list(group_a.get("more", []))
        groups_b = [group_b] + list(group_b.get("more", []))
        for gi, (sub_a, sub_b) in enumerate(zip(groups_a, groups_b)):
            shapes_a = sub_a.get("shapes", [])
            shapes_b = sub_b.get("shapes", [])
            for shape_i, (shape_a, shape_b) in enumerate(zip(shapes_a, shapes_b)):
                pts_a = [tuple(p) for p in shape_a.get("pts", [])]
                pts_b = [tuple(p) for p in shape_b.get("pts", [])]
                for vertex, (pa, pb) in enumerate(zip(pts_a, pts_b)):
                    if pa != pb:
                        return {
                            "kind": "vertex",
                            "layer": layer,
                            "group": gi,
                            "shape": shape_i,
                            "vertex": vertex,
                            "from": list(pa),
                            "to": list(pb),
                            "dx": pb[0] - pa[0],
                            "dy": pb[1] - pa[1],
                            "vertices_a": len(pts_a),
                            "vertices_b": len(pts_b),
                        }
                if len(pts_a) != len(pts_b):
                    return {"kind": "vertex-count", "layer": layer, "group": gi,
                            "shape": shape_i, "vertices_a": len(pts_a),
                            "vertices_b": len(pts_b)}
            if len(shapes_a) != len(shapes_b):
                return {"kind": "shape-count", "layer": layer, "group": gi,
                        "shapes_a": len(shapes_a), "shapes_b": len(shapes_b)}
        if len(groups_a) != len(groups_b):
            return {"kind": "group-count", "layer": layer,
                    "groups_a": len(groups_a), "groups_b": len(groups_b)}
    if list(rec_a["hdr"]) != list(rec_b["hdr"]):
        words = [{"word": i, "a": rec_a["hdr"][i], "b": rec_b["hdr"][i]}
                 for i in range(len(rec_a["hdr"]))
                 if rec_a["hdr"][i] != rec_b["hdr"][i]]
        return {"kind": "record-header", "words": words[:8],
                "word_count": len(words)}
    return None


def _section4_change(stream_a, stream_b):
    """Name a section-4 record change (parcel, type, country, names), or None."""
    module = section4_module()
    if module is None:
        return None
    record_a, record_b = stream_a["record"], stream_b["record"]
    in_section = any(record is not None and record["section"] == 4
                     for record in (record_a, record_b))
    try:
        parsed_a = module.parse_record(stream_a["plain"], 0, "plain",
                                       module.DEFAULT_MIN_NAME)
        parsed_b = module.parse_record(stream_b["plain"], 0, "plain",
                                       module.DEFAULT_MIN_NAME)
    except Exception:
        return None
    if not in_section and not (parsed_a["type_tag"] == module.TYPE_TAG
                               and parsed_b["type_tag"] == module.TYPE_TAG):
        return None
    names_a = [name["text"] for name in parsed_a["names"]]
    names_b = [name["text"] for name in parsed_b["names"]]
    return {
        "kind": "section4",
        "parcel": ("0x%08x" % parsed_a["parcel_u32"]
                   if parsed_a["parcel_u32"] is not None else None),
        "type_tag": parsed_a["type_tag"],
        "country_code": parsed_a["country_code"],
        "names_a": len(names_a),
        "names_b": len(names_b),
        "names_added": [name for name in names_b if name not in names_a][:8],
        "names_removed": [name for name in names_a if name not in names_b][:8],
    }


def _byte_change(plain_a: bytes, plain_b: bytes):
    """Fallback: first differing byte and how much differs."""
    common = min(len(plain_a), len(plain_b))
    first = next((i for i in range(common) if plain_a[i] != plain_b[i]), common)
    differing = sum(1 for i in range(common) if plain_a[i] != plain_b[i])
    differing += abs(len(plain_a) - len(plain_b))
    return {
        "kind": "bytes",
        "length_a": len(plain_a),
        "length_b": len(plain_b),
        "first_diff": first,
        "differing": differing,
        "a_hex": plain_a[first:first + 8].hex(),
        "b_hex": plain_b[first:first + 8].hex(),
    }


def describe_change(stream_a, stream_b):
    """Describe one changed pair with the most specific known layout."""
    change = _vertex_change(stream_a["plain"], stream_b["plain"])
    if change is None:
        change = _section4_change(stream_a, stream_b)
    if change is None:
        change = _byte_change(stream_a["plain"], stream_b["plain"])
    return change


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def byte_ranges(blob_a: bytes, blob_b: bytes, block: int):
    """Differing byte count and block ranges (start, end) between the files."""
    size = max(len(blob_a), len(blob_b))
    differing = 0
    ranges: list[list[int]] = []
    for start in range(0, size, block):
        end = min(start + block, size)
        chunk_a = blob_a[start:end]
        chunk_b = blob_b[start:end]
        if chunk_a == chunk_b:
            continue
        count = sum(1 for i in range(max(len(chunk_a), len(chunk_b)))
                    if (chunk_a[i] if i < len(chunk_a) else None)
                    != (chunk_b[i] if i < len(chunk_b) else None))
        differing += count
        if ranges and ranges[-1][1] == start:
            ranges[-1][1] = end
        else:
            ranges.append([start, end])
    return differing, ranges


def offset_view(streams_a, streams_b):
    """The M5.8 view: streams matched only by file offset."""
    index_a = {stream["offset"]: stream for stream in streams_a}
    index_b = {stream["offset"]: stream for stream in streams_b}
    same = 0
    changed, added, removed = [], [], []
    for offset in sorted(set(index_a) | set(index_b)):
        if offset in index_a and offset in index_b:
            if index_a[offset]["sha256"] == index_b[offset]["sha256"]:
                same += 1
            else:
                changed.append({
                    "offset": offset,
                    "plain_a": index_a[offset]["plain_len"],
                    "plain_b": index_b[offset]["plain_len"],
                    "compressed_a": index_a[offset]["compressed"],
                    "compressed_b": index_b[offset]["compressed"],
                })
        elif offset in index_a:
            removed.append({"offset": offset,
                            "plain": index_a[offset]["plain_len"]})
        else:
            added.append({"offset": offset,
                          "plain": index_b[offset]["plain_len"]})
    return {"same": same, "changed": len(changed), "added": len(added),
            "removed": len(removed), "changed_detail": changed,
            "added_detail": added, "removed_detail": removed}


def _record_json(record):
    if record is None:
        return None
    return {"section": record["section"], "level": record["level"],
            "dir": list(record["dir"]), "slot": record["slot"],
            "rec": record["rec"]}


def report(a_path: Path, b_path: Path, block: int = 4096) -> dict:
    blob_a = a_path.read_bytes()
    blob_b = b_path.read_bytes()
    mods = ze0()
    tile_mod = mods[0] if mods else None
    streams_a, parsed_a = tile_streams(blob_a, tile_mod)
    streams_b, parsed_b = tile_streams(blob_b, tile_mod)
    pairs = match_streams(streams_a, streams_b)

    changed = []
    for stream_a, stream_b in pairs["changed"]:
        changed.append({
            "offset_a": stream_a["offset"],
            "offset_b": stream_b["offset"],
            "compressed_a": stream_a["compressed"],
            "compressed_b": stream_b["compressed"],
            "sha256_a": stream_a["sha256"],
            "sha256_b": stream_b["sha256"],
            "plain_a": stream_a["plain_len"],
            "plain_b": stream_b["plain_len"],
            "record_a": _record_json(stream_a["record"]),
            "record_b": _record_json(stream_b["record"]),
            "change": describe_change(stream_a, stream_b),
        })
    moved = []
    for stream_a, stream_b in pairs["moved"]:
        moved.append({
            "offset_a": stream_a["offset"],
            "offset_b": stream_b["offset"],
            "compressed_a": stream_a["compressed"],
            "compressed_b": stream_b["compressed"],
            "sha256_a": stream_a["sha256"],
            "sha256_b": stream_b["sha256"],
            "plain_a": stream_a["plain_len"],
            "plain_b": stream_b["plain_len"],
            "record_a": _record_json(stream_a["record"]),
            "record_b": _record_json(stream_b["record"]),
            "reencoded": (stream_a["compressed_sha256"]
                          != stream_b["compressed_sha256"]),
        })
    added = [{"offset": stream["offset"], "compressed": stream["compressed"],
              "sha256": stream["sha256"], "plain": stream["plain_len"],
              "record": _record_json(stream["record"])}
             for stream in pairs["added"]]
    removed = [{"offset": stream["offset"], "compressed": stream["compressed"],
                "sha256": stream["sha256"], "plain": stream["plain_len"],
                "record": _record_json(stream["record"])}
               for stream in pairs["removed"]]
    reencoded = sum(1 for pair in pairs["moved"] + pairs["same"]
                    if pair[0]["compressed_sha256"] != pair[1]["compressed_sha256"])
    differing, ranges = byte_ranges(blob_a, blob_b, block)
    return {
        "format": REPORT_FORMAT,
        "a": {"path": str(a_path), "size": len(blob_a),
              "sha256": hashlib.sha256(blob_a).hexdigest(),
              "streams": len(streams_a), "parsed": parsed_a},
        "b": {"path": str(b_path), "size": len(blob_b),
              "sha256": hashlib.sha256(blob_b).hexdigest(),
              "streams": len(streams_b), "parsed": parsed_b},
        "streams": {"same": len(pairs["same"]), "moved": len(moved),
                    "changed": len(changed), "added": len(added),
                    "removed": len(removed), "reencoded": reencoded},
        "changed": changed,
        "moved": moved,
        "added": added,
        "removed": removed,
        "bytes": {"differing": differing, "block": block, "ranges": ranges,
                  "range_count": len(ranges)},
        "by_offset": offset_view(streams_a, streams_b),
        "identical": blob_a == blob_b,
    }


# --------------------------------------------------------------------------
# Text view
# --------------------------------------------------------------------------


def _record_text(record):
    if record is None:
        return "record=unnamed"
    return "section=%s level=%s dir=(%s,%s) slot=%s rec=%s" % (
        record["section"], record["level"], record["dir"][0], record["dir"][1],
        record["slot"], record["rec"])


def change_text(change) -> str:
    """One line describing a named change."""
    if change is None:
        return "change=unknown"
    kind = change["kind"]
    if kind == "vertex":
        return ("vertex layer=%d shape=%d vertex=%d (%d,%d) -> (%d,%d) "
                "d=(%+d,%+d)" % (change["layer"], change["shape"],
                                 change["vertex"], change["from"][0],
                                 change["from"][1], change["to"][0],
                                 change["to"][1], change["dx"], change["dy"]))
    if kind == "vertex-count":
        return "vertex count layer=%d shape=%d %d -> %d" % (
            change["layer"], change["shape"], change["vertices_a"],
            change["vertices_b"])
    if kind == "shape-count":
        return "shape count layer=%d group=%d %d -> %d" % (
            change["layer"], change["group"], change["shapes_a"],
            change["shapes_b"])
    if kind == "group-count":
        return "group count layer=%d %d -> %d" % (
            change["layer"], change["groups_a"], change["groups_b"])
    if kind == "record-header":
        return "record header words %s" % [w["word"] for w in change["words"]]
    if kind == "section4":
        return ("section4 parcel=%s type=0x%04x country=%s names %d -> %d "
                "(+%d/-%d)" % (change["parcel"], change["type_tag"] or 0,
                               change["country_code"], change["names_a"],
                               change["names_b"], len(change["names_added"]),
                               len(change["names_removed"])))
    return ("bytes %d -> %d B, first diff +0x%x, %d bytes differ "
            "(%s -> %s)" % (change["length_a"], change["length_b"],
                            change["first_diff"], change["differing"],
                            change["a_hex"] or "-", change["b_hex"] or "-"))


def _truncated(count):
    return count - DETAIL_LIMIT if count > DETAIL_LIMIT else 0


def print_text(result) -> None:
    print("A %d bytes %s streams=%d layout=%s" % (
        result["a"]["size"], result["a"]["sha256"][:16], result["a"]["streams"],
        "parsed" if result["a"]["parsed"] else "raw"))
    print("B %d bytes %s streams=%d layout=%s" % (
        result["b"]["size"], result["b"]["sha256"][:16], result["b"]["streams"],
        "parsed" if result["b"]["parsed"] else "raw"))
    counts = result["streams"]
    print("streams (content): same=%d moved=%d changed=%d added=%d removed=%d"
          % (counts["same"], counts["moved"], counts["changed"],
             counts["added"], counts["removed"]))
    for entry in result["changed"][:DETAIL_LIMIT]:
        print("  changed  A %d -> B %d  %s" % (
            entry["offset_a"], entry["offset_b"],
            _record_text(entry["record_b"] or entry["record_a"])))
        print("           %s" % change_text(entry["change"]))
    for entry in result["moved"][:DETAIL_LIMIT]:
        print("  moved    A %d -> B %d  %s%s" % (
            entry["offset_a"], entry["offset_b"],
            _record_text(entry["record_a"]),
            " (recompressed)" if entry["reencoded"] else " (content identical)"))
    for entry in result["added"][:DETAIL_LIMIT]:
        print("  added    @%d  %s plain=%d" % (
            entry["offset"], _record_text(entry["record"]), entry["plain"]))
    for entry in result["removed"][:DETAIL_LIMIT]:
        print("  removed  @%d  %s plain=%d" % (
            entry["offset"], _record_text(entry["record"]), entry["plain"]))
    for label, entries in (("changed", result["changed"]),
                           ("moved", result["moved"]),
                           ("added", result["added"]),
                           ("removed", result["removed"])):
        extra = _truncated(len(entries))
        if extra:
            print("  ... %d more %s" % (extra, label))
    print("bytes differing=%d in %d ranges" % (
        result["bytes"]["differing"], result["bytes"]["range_count"]))
    print("RESULT: " + ("IDENTICAL" if result["identical"] else "DIFFERS"))


def print_offset_text(result) -> None:
    """The M5.8 offset-keyed view."""
    print("A %d bytes %s streams=%d" % (
        result["a"]["size"], result["a"]["sha256"][:16], result["a"]["streams"]))
    print("B %d bytes %s streams=%d" % (
        result["b"]["size"], result["b"]["sha256"][:16], result["b"]["streams"]))
    view = result["by_offset"]
    print("streams (by offset): same=%d changed=%d added=%d removed=%d" % (
        view["same"], view["changed"], view["added"], view["removed"]))
    for entry in view["changed_detail"][:DETAIL_LIMIT]:
        print("  changed  @%d plain %d -> %d bytes" % (
            entry["offset"], entry["plain_a"], entry["plain_b"]))
    for entry in view["added_detail"][:DETAIL_LIMIT]:
        print("  added    @%d plain=%d" % (entry["offset"], entry["plain"]))
    for entry in view["removed_detail"][:DETAIL_LIMIT]:
        print("  removed  @%d plain=%d" % (entry["offset"], entry["plain"]))
    print("bytes differing=%d in %d ranges" % (
        result["bytes"]["differing"], result["bytes"]["range_count"]))
    print("RESULT: " + ("IDENTICAL" if result["identical"] else "DIFFERS"))


# --------------------------------------------------------------------------
# Synthetic tile pair for --selftest (no vendor data)
# --------------------------------------------------------------------------


def _background_record(bg_mod, points, parcel=(0x1234, 0x5678)):
    """A minimal section-1 background record with one polygon layer."""
    group = {"kind": 0x80,
             "shapes": [{"type": 0x0001, "ref": 0, "pts": list(points)}]}
    layer = bg_mod.build_group(group)
    geometry = bytearray(struct.pack(">HH", 1, len(layer) // 4)) + layer
    header = [0] * 22
    header[0], header[1] = parcel
    header[2] = 0x19
    for word in (7, 8, 11, 12, 13, 14, 15, 16, 17, 18):
        header[word] = 0xFFFF
    header[9], header[10] = 11, len(geometry) // 4
    out = bytearray(44)
    struct.pack_into(">22H", out, 0, *header)
    out += geometry
    plain = bytes(out)
    if bg_mod.build_record(bg_mod.parse_record(plain)) != plain:
        raise RuntimeError("synthetic background record does not round-trip")
    return plain


def _shift_vertex(bg_mod, plain, dx, dy):
    record = bg_mod.parse_record(plain)
    for group in record["layers"].values():
        for shape in group.get("shapes", []):
            points = shape.get("pts", [])
            if len(points) < 3:
                continue
            x, y = points[0]
            points[0] = (min(2047, max(0, x + dx)), min(2047, max(0, y + dy)))
            record["strict"] = True
            return bg_mod.build_record(record)
    raise RuntimeError("synthetic record has no polygon vertex to move")


def _synthetic_slot(plain):
    compressed = zlib.compress(plain, 6)
    if len(compressed) % 2:
        compressed += b"\x00"  # word-aligned, as the factory does
    body = bytearray(b"\xff" * 512)
    struct.pack_into(">II", body, 0, len(compressed) // 2, len(plain) // 2)
    return {"tag": 0, "body": bytes(body), "block_off": 0,
            "recs": [{"k": 0, "raw": compressed, "words": len(plain) // 2,
                      "flag": 0}]}


def _synthetic_tile(tile_mod, plains, block_order=None):
    """Build one-section level-1 tile bytes; block_order permutes block writes."""
    header = bytearray(TABLE1_OFF)
    struct.pack_into(">HBB", header, 0x1AC, 1, 1, 1)
    struct.pack_into(">BBH", header, 0x1B0, 1, 0x92, len(plains))
    struct.pack_into(">I", header, 0x800 + 6, 0xFFFFFFFF)  # section terminator
    dirs = []
    for row, plain in enumerate(plains, start=1):
        directory = {"off": 0, "kind": 0x2046, "ab": (0x20, 0x20), "y": row,
                     "x": row, "typ": 0x92, "box": (row + 1, row, row, row + 1),
                     "body": 512, "nslots": 32}
        directory["slots"] = {0: _synthetic_slot(plain)}
        dirs.append(directory)
    model = {"header": header,
             "sections": [{"id": 1, "count": len(dirs), "taddr": 0, "ttag": 0,
                           "levels": [{"level": 1, "typ": 0x92,
                                       "dirs": dirs}]}]}
    order = tile_mod.default_order(model)
    if block_order is not None:
        blocks = [entry for entry in order if entry[1] == "blocks"]
        order = [entry for entry in order if entry[1] != "blocks"]
        order += [blocks[i] for i in block_order]
    return tile_mod.write_tile(model, order=order, preserve_gaps=False)


def make_synthetic_tiles(directory):
    """Write a synthetic tile pair for the self-test.

    Tile B changes exactly two things: the third background record's first
    vertex moves by ``(dx, dy)`` (and its block is written earlier, so the
    edited stream also moves), and the second record's block is written after
    the third, so an untouched stream moves to a new offset.  The first record
    keeps both position and content.

    Returns ``(path_a, path_b, facts)``.
    """
    mods = ze0()
    if mods is None:
        raise RuntimeError("tools/ze0-viewer/tools_ze0 is not available")
    tile_mod, bg_mod = mods
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    dx, dy = 40, 0
    plains = [
        _background_record(bg_mod, [(300, 400), (340, 440), (300, 440)]),
        _background_record(bg_mod, [(350, 500), (390, 540), (350, 540)]),
        _background_record(bg_mod, [(400, 600), (440, 640), (400, 640)]),
    ]
    edited = _shift_vertex(bg_mod, plains[2], dx, dy)
    path_a = directory / "SYNTHA.DAT"
    path_b = directory / "SYNTHB.DAT"
    path_a.write_bytes(_synthetic_tile(tile_mod, plains))
    path_b.write_bytes(_synthetic_tile(tile_mod, plains[:2] + [edited],
                                       block_order=(0, 2, 1)))
    return path_a, path_b, {"dx": dx, "dy": dy, "changed_dir": 3,
                             "moved_dir": 2, "same_dir": 1}


def _block_offsets(tile_mod, blob):
    """{(level, dir_row, dir_col): block offset} for single-record slots."""
    out = {}
    tile = tile_mod.read_tile(blob)
    for section in tile["sections"]:
        for level in section["levels"]:
            for directory in level["dirs"]:
                for slot_i, slot in sorted(directory["slots"].items()):
                    out[(level["level"], directory["y"], directory["x"],
                         slot_i)] = slot["block_off"]
    return out


def _selftest() -> int:
    import contextlib
    import io
    import tempfile

    fails = []
    summary: list[str] = []

    def check(name, condition):
        if not condition:
            fails.append(name)

    def capture(func):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            func()
        return buffer.getvalue()

    try:
        with tempfile.TemporaryDirectory() as tmp:
            path_a, path_b, facts = make_synthetic_tiles(tmp)
            result = report(path_a, path_b, 16)
            counts = result["streams"]
            check("exactly one changed stream", counts["changed"] == 1)
            check("no added stream", counts["added"] == 0)
            check("no removed stream", counts["removed"] == 0)
            check("exactly one moved stream", counts["moved"] == 1)
            check("one unchanged stream", counts["same"] == 1)
            check("all streams accounted for",
                  sum(counts[key] for key in ("same", "moved", "changed"))
                  == result["a"]["streams"] == result["b"]["streams"])
            check("stable json keys", set(result) == {
                "format", "a", "b", "streams", "changed", "moved", "added",
                "removed", "bytes", "by_offset", "identical"})
            check("json serialisable", bool(json.dumps(result)))

            mods = ze0()
            offsets_a = _block_offsets(mods[0], path_a.read_bytes())
            offsets_b = _block_offsets(mods[0], path_b.read_bytes())
            moved_key = (1, facts["moved_dir"], facts["moved_dir"], 0)
            changed_key = (1, facts["changed_dir"], facts["changed_dir"], 0)
            same_key = (1, facts["same_dir"], facts["same_dir"], 0)
            check("synthetic layout has three streams",
                  len(offsets_a) == len(offsets_b) == 3)
            check("same stream kept its offset",
                  offsets_a[same_key] == offsets_b[same_key])

            moved = result["moved"][0]
            check("moved pairing: identical content",
                  moved["sha256_a"] == moved["sha256_b"])
            check("moved pairing: A offset", moved["offset_a"] == offsets_a[moved_key])
            check("moved pairing: B offset", moved["offset_b"] == offsets_b[moved_key])
            check("moved pairing: new offset", moved["offset_a"] != moved["offset_b"])
            check("moved pairing: record named",
                  moved["record_a"] is not None
                  and moved["record_a"]["dir"] == [facts["moved_dir"],
                                                   facts["moved_dir"]]
                  and moved["record_a"]["level"] == 1)

            changed = result["changed"][0]
            check("changed pairing: A offset",
                  changed["offset_a"] == offsets_a[changed_key])
            check("changed pairing: B offset",
                  changed["offset_b"] == offsets_b[changed_key])
            check("changed stream moved too",
                  changed["offset_a"] != changed["offset_b"])
            check("changed record named",
                  changed["record_b"]["dir"] == [facts["changed_dir"],
                                                 facts["changed_dir"]])
            change = changed["change"]
            check("changed change is a vertex", change["kind"] == "vertex")
            check("changed vertex index", change["vertex"] == 0)
            check("changed vertex delta",
                  (change["dx"], change["dy"]) == (facts["dx"], facts["dy"]))
            check("changed vertex endpoints differ", change["from"] != change["to"])

            old = result["by_offset"]
            check("offset view cannot express a move",
                  old["changed"] + old["added"] + old["removed"] >= 1
                  and old["same"] < counts["same"] + counts["moved"])
            text = capture(lambda: print_text(result))
            offset_text = capture(lambda: print_offset_text(result))
            check("text view names the change", "changed  A" in text
                  and "vertex layer=" in text)
            check("text view lists the move", "moved    A" in text)
            check("offset text view prints", "by offset" in offset_text)

            same_run = report(path_a, path_a, 16)
            check("self compare identical",
                  same_run["identical"] is True
                  and same_run["bytes"]["differing"] == 0)
            check("self compare streams same",
                  same_run["streams"]["same"] == same_run["a"]["streams"]
                  and same_run["streams"]["changed"] == 0)
            check("self compare offset view same",
                  same_run["by_offset"]["same"] == same_run["a"]["streams"])
            check("ranges merged",
                  all(start < end for start, end in result["bytes"]["ranges"]))

            # A recompressed record keeps its plain bytes: still "same", but
            # flagged as reencoded rather than silently equal.
            recompressed = Path(tmp) / "SYNTH-RECOMP.DAT"
            model = mods[0].read_tile(path_a.read_bytes())
            slot = model["sections"][0]["levels"][0]["dirs"][0]["slots"][0]
            plain = zlib.decompress(slot["recs"][0]["raw"])
            comp = zlib.compress(plain, 1)
            if len(comp) % 2:
                comp += b"\x00"
            slot["recs"][0]["raw"] = comp
            body = bytearray(slot["body"])
            struct.pack_into(">II", body, 0, len(comp) // 2, len(plain) // 2)
            slot["body"] = bytes(body)
            recompressed.write_bytes(mods[0].write_tile(model,
                                                       preserve_gaps=False))
            again = report(path_a, recompressed, 16)
            check("recompression keeps the stream same",
                  again["streams"] == {"same": 3, "moved": 0, "changed": 0,
                                       "added": 0, "removed": 0,
                                       "reencoded": 1})
            summary = [
                "synthetic tile %d bytes, %d streams"
                % (result["a"]["size"], result["a"]["streams"]),
                "  content view: same=%d moved=%d changed=%d added=%d removed=%d"
                % (counts["same"], counts["moved"], counts["changed"],
                   counts["added"], counts["removed"]),
                "  changed: %s %s" % (_record_text(changed["record_b"]),
                                      change_text(change)),
                "  moved:   A %d -> B %d  %s (content identical)"
                % (moved["offset_a"], moved["offset_b"],
                   _record_text(moved["record_a"])),
                "  by offset: same=%d changed=%d added=%d removed=%d"
                % (old["same"], old["changed"], old["added"], old["removed"]),
                "  recompressed stream: same=%d reencoded=%d"
                % (again["streams"]["same"], again["streams"]["reencoded"]),
            ]
    except Exception as exc:  # keep the failure mode readable
        fails.append("%s: %s" % (type(exc).__name__, exc))
    for line in summary:
        print(line)
    print("selftest: %s" % ("OK" if not fails else "FAIL " + ", ".join(fails)))
    return 0 if not fails else 1


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Diff two ZE0 map tiles (content-matched streams).")
    parser.add_argument("a", nargs="?")
    parser.add_argument("b", nargs="?")
    parser.add_argument("--json", action="store_true",
                        help="machine-readable report (both views)")
    parser.add_argument("--by-offset", action="store_true",
                        help="print the older offset-keyed view")
    parser.add_argument("--block", type=int, default=4096)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not args.a or not args.b:
        parser.error("A and B are required")
    try:
        result = report(Path(args.a), Path(args.b), args.block)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
    elif args.by_offset:
        print_offset_text(result)
    else:
        print_text(result)
    return 0 if result["identical"] else 1


if __name__ == "__main__":
    sys.exit(main())
