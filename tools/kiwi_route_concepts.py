#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Numeric concept tests for M4.72: KIWI route-planning ideas vs ZE0 section 2.

No KIWI specification is available (M4.65), so this tool does not claim a KIWI
layout.  It tests the three numeric questions the task asks on our own data:
link length (section-2 word b) vs drawn geometry distance, node degree vs
edge-entry count, and whether any section-2 field can be a level-up pointer.
Commands:
  python3 tools/kiwi_route_concepts.py --selftest
  python3 tools/kiwi_route_concepts.py check TILE [--every K] [--json OUT]
  python3 tools/kiwi_route_concepts.py --tree ROOT --tile B48R058R  # M4.72 replay
  python3 tools/kiwi_route_concepts.py --card IMG --tile B48R058R   # one FAT file, no 7z
"""
import argparse
import collections
import hashlib
import json
import math
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "ze0-viewer" / "tools_ze0"))
import clarion_rd  # noqa: E402
import clarion_tile  # noqa: E402

import _kiwi_replay as replay  # noqa: E402


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    den = math.sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))
    return sum(a * b for a, b in zip(dx, dy)) / den if den else 0.0


def check(tile_path, every=16):
    data = Path(tile_path).read_bytes()
    tile = clarion_tile.read_tile(data)
    counts = collections.Counter()
    lengths, times, degrees = [], [], []
    samples = []
    for sec in tile["sections"]:
        if sec["id"] != 2:
            continue
        for level in sec["levels"]:
            for di, directory in enumerate(level["dirs"]):
                for slot, S in directory["slots"].items():
                    for rec in S["recs"]:
                        counts["records"] += 1
                        if counts["records"] % every:
                            continue
                        try:
                            plain = zlib.decompressobj().decompress(rec["raw"])
                            model = clarion_rd.parse_record(plain)
                        except (zlib.error, struct.error, IndexError):
                            counts["refused"] += 1
                            continue
                        if not model.get("nodes"):
                            counts["empty"] += 1
                            continue
                        counts["sampled"] += 1
                        nodes = model["nodes"]
                        links, _ends = clarion_rd.links(model)
                        # node degree: distinct edge entries per node
                        for i, nd in enumerate(nodes):
                            deg = len(nd["entries"])
                            degrees.append(deg)
                            if deg == 0:
                                counts["isolated_nodes"] += 1
                        # link length b against straight-line node distance
                        for lid, i, j, cls, a, b in links:
                            if i >= len(nodes) or j >= len(nodes) or b == 0:
                                continue
                            p, q = nodes[i], nodes[j]
                            d = math.hypot(p["x"] - q["x"], p["y"] - q["y"])
                            if not (0 < d < 2048):
                                continue
                            lengths.append((b, d))
                            times.append((a, d))
                            if len(samples) < 5:
                                samples.append(dict(dir=hex(directory["off"]), slot=slot,
                                                    link=lid, b=b, dist=round(d, 2)))
    bl = pearson([x for x, _ in lengths], [y for _, y in lengths]) if lengths else 0.0
    al = pearson([x for x, _ in times], [y for _, y in times]) if times else 0.0
    return dict(file=str(tile_path), sha256=hashlib.sha256(data).hexdigest(),
                every=every, counts=dict(counts),
                link_length_pairs=len(lengths), r_length_vs_geometry=round(bl, 4),
                r_traveltime_vs_geometry=round(al, 4),
                node_entries=len(degrees), degree_histogram=dict(collections.Counter(degrees)),
                level_up_field="UNKNOWN (no KIWI spec, M4.65; no firmware VA)", samples=samples)


def selftest():
    assert abs(pearson([1, 2, 3, 4], [2, 4, 6, 8]) - 1.0) < 1e-9
    assert abs(pearson([1, 2, 3, 4], [8, 6, 4, 2]) + 1.0) < 1e-9
    assert pearson([1, 1, 1], [2, 3, 4]) == 0.0
    print("kiwi_route_concepts selftest: Pearson +1/-1/0 OK")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    replay.add_source_args(ap)
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("check")
    p.add_argument("tile")
    p.add_argument("--every", type=int, default=16)
    p.add_argument("--json")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        source = replay.resolve(a)
    except replay.SourceError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    if source is not None:
        out = check(source.path, every=16)
        print("file %s sha256 %s" % (source.display, out["sha256"]))
        print("counts %s" % out["counts"])
        print("link length vs geometry: n=%d r=%.4f; travel time r=%.4f" %
              (out["link_length_pairs"], out["r_length_vs_geometry"],
               out["r_traveltime_vs_geometry"]))
        print("node entries=%d degrees=%s" % (out["node_entries"], out["degree_histogram"]))
        print("level-up: %s" % out["level_up_field"])
        summary = "%s sampled=%d links=%d r_length=%.4f r_time=%.4f nodes=%d" % (
            replay.norm_tile(a.tile), out["counts"].get("sampled", 0),
            out["link_length_pairs"], out["r_length_vs_geometry"],
            out["r_traveltime_vs_geometry"], out["node_entries"])
        return replay.replay_line(source, "EXP-2026-11-22-M4.72-kiwi-route-concepts", summary)
    if a.cmd == "check":
        out = check(a.tile, a.every)
        if a.json:
            Path(a.json).write_text(json.dumps(out, indent=2) + "\n")
        print("file %s sha256 %s" % (out["file"], out["sha256"]))
        print("counts %s" % out["counts"])
        print("link length vs geometry: n=%d r=%.4f; travel time r=%.4f" %
              (out["link_length_pairs"], out["r_length_vs_geometry"],
               out["r_traveltime_vs_geometry"]))
        print("node entries=%d degrees=%s" % (out["node_entries"], out["degree_histogram"]))
        print("level-up: %s" % out["level_up_field"])
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
