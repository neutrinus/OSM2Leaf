#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Census of the point reference word in ZE0 section-1 0x00fa road records.

C-6775: for a point whose x word is at word index p in a shape (and whose y
word is p+1), the reference is the word at p + ((y >> 13) & 1) + 2.  It is
another point's word index in the same shape, or 0xffff for none.  This tool
counts, on factory records, how often that target is a real point of the same
shape and how often the target's own reference points back (mutual pair).

Commands:
  python3 tools/fa_ref_census.py --selftest
  python3 tools/fa_ref_census.py TILE [--level 1] [--limit N] [--json OUT]
"""
import argparse
import collections
import json
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "ze0-viewer" / "tools_ze0"))
import clarion_tile  # noqa: E402
import fa_encode  # noqa: E402

import tilewriter  # noqa: E402


def ref_slot(w, p):
    """Word index of the reference word belonging to the point at word p."""
    return p + ((w[p + 1] >> 13) & 1) + 2


def census(tile_path, level=1, limit=0, max_records=0, starts_only=False):
    data = Path(tile_path).read_bytes()
    tile = clarion_tile.read_tile(data)
    entry = tilewriter.road_level(tile, level)
    counts = collections.Counter()
    samples = []
    records = 0
    for di, directory in enumerate(entry["dirs"]):
        for slot, S in directory["slots"].items():
            for rec in S["recs"]:
                if max_records and records >= max_records:
                    break
                if rec["k"] % 2 != 0:
                    continue
                records += 1
                try:
                    plain = zlib.decompressobj().decompress(rec["raw"])
                    if struct.unpack_from(">H", plain, 4)[0] != 0x00FA:
                        continue
                    _code, _g, shapes = fa_encode.parse_record(plain, level)
                except (zlib.error, struct.error, AssertionError, IndexError):
                    counts["refused"] += 1
                    continue
                w = list(struct.unpack_from(">%dH" % (len(plain) // 2), plain))
                allpoints = {p for sh in shapes for p in sh["points"]}
                for sh in shapes:
                    pts = sorted(sh["points"].items())
                    for pi, (p, info) in enumerate(pts):
                        role = info[0] if isinstance(info, tuple) else info
                        if starts_only and not (role == 'start' or
                                (pi and (pts[pi - 1][1][0] if isinstance(pts[pi - 1][1], tuple)
                                         else pts[pi - 1][1]) == 'end' and pi < len(pts) - 1)):
                            continue
                        x, y = w[p] & 0x7FF, w[p + 1] & 0x7FF
                        if x in (0, 0x7FF) or y in (0, 0x7FF):
                            counts["skipped_edge_point"] += 1
                            continue
                        has_y13 = bool(w[p + 1] & 0x2000)
                        s = ref_slot(w, p)
                        if s >= len(w):
                            counts["slot_outside"] += 1
                            continue
                        ref = w[s]
                        counts["points"] += 1
                        if ref == 0xFFFF:
                            counts["none"] += 1
                            continue
                        counts["carries"] += 1
                        if has_y13:
                            counts["y13_carries"] += 1
                        target = _g + ref  # reference is a word index in the shape buffer
                        if 0 <= ref < 5632:  # M9.66: shape buffer 11,264 B = 5,632 words
                            counts["buffer_index"] += 1
                        if 0 <= target < len(w):
                            counts["in_record"] += 1
                        else:
                            counts["outside_record"] += 1
                        if target not in allpoints:
                            counts["target_not_point"] += 1
                            continue
                        if target == p:
                            counts["self"] += 1
                            continue
                        counts["in_shape"] += 1
                        ts = ref_slot(w, target)
                        mutual = ts < len(w) and w[ts] == (p - _g)
                        if mutual:
                            counts["mutual"] += 1
                            if has_y13:
                                counts["y13_mutual"] += 1
                        else:
                            counts["not_mutual"] += 1
                        if len(samples) < limit:
                            samples.append(dict(dir=hex(directory["off"]), slot=slot, rec=rec["k"],
                                                shape=hex(sh["at"]), point=p, ref=ref,
                                                mutual=mutual))
    explained = counts["mutual"] / counts["carries"] if counts["carries"] else 0.0
    y13 = counts["y13_mutual"] / counts["y13_carries"] if counts["y13_carries"] else 0.0
    return dict(file=str(tile_path), level=level, road_records=records,
                counts=dict(counts), mutual_share=round(explained, 6),
                y13_mutual_share=round(y13, 6), samples=samples)


def selftest():
    # A six-word shape with two mutually referring points; the slot follows
    # C-6775 and the inverse check finds the pair.
    w = [0x0800, 0x0800, 0x0000, 0x0100, 5, 0x0801, 0x0801, 0x0000, 6, 0x0000]
    p, q = 0, 4
    wp, wq = ref_slot(w, p), ref_slot(w, q)
    w[wp], w[wq] = q, p
    assert ref_slot(w, p) == 2 and ref_slot(w, q) == 6, (wp, wq)
    assert w[ref_slot(w, q)] == p
    print("fa_ref_census selftest: C-6775 slot and mutual pair OK")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("tile", nargs="?")
    ap.add_argument("--level", type=int, default=1)
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--max-records", type=int, default=0)
    ap.add_argument("--starts-only", action="store_true",
                    help="count only link-start points, the only ones with a reference word")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.tile:
        ap.error("TILE is required")
    out = census(a.tile, a.level, a.limit, a.max_records, a.starts_only)
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2) + "\n")
    print("file %s level %d" % (out["file"], out["level"]))
    print("counts %s" % out["counts"])
    print("mutual/carries = %.4f" % out["mutual_share"])
    for s in out["samples"][:5]:
        print("  dir %s slot %d rec %d shape %s point %s -> ref %s mutual %s" %
              (s["dir"], s["slot"], s["rec"], s["shape"], s["point"], s["ref"], s["mutual"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
