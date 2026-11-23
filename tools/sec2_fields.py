#!/usr/bin/env python3
"""Check the section-2 field meanings read off Navi.exe (M4.98) on a factory tile.

Each check states a rule taken from decompiled firmware (EU2011 build A, see
EXP-2026-11-23-M4.98-sec2-fields-ghidra) and counts how many links or records
of a tile obey it.  Reads only the tile; prints counts, never vendor bytes.

    python3 tools/sec2_fields.py TILE.DAT [--sample N]
    python3 tools/sec2_fields.py --selftest
"""
from __future__ import annotations

import argparse
import collections
import os
import random
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def link_words(w1: int, w2: int, w3: int) -> int:
    """Extra halfwords after the 7 fixed link words (firmware size rule)."""
    return ((w2 & 0x3FC0) >> 6) + (w1 & 1) + (w2 & 0x3F) + (w3 >> 14)


def walk(u: list[int]):
    """Yield (node_index, node_words, link_words, extra_words) for unit 0."""
    nn = (u[0] << 16) | u[1]
    p = 26
    for k in range(nn):
        node = u[p:p + 3]
        p += 3
        for _ in range(node[0] >> 12):
            lw = u[p:p + 7]
            n = link_words(lw[1], lw[2], lw[3])
            yield k, node, lw, u[p + 7:p + 7 + n]
            p += 7 + n


def check_record(w: list[int], st: collections.Counter) -> None:
    o, n = (w[6] << 16) | w[7], (w[8] << 16) | w[9]
    if o == 0xFFFFFFFF:
        return
    u = w[o:o + n]
    nn, nl = (u[0] << 16) | u[1], (u[2] << 16) | u[3]
    pairs = [(u[4 + 2 * i], u[5 + 2 * i]) for i in range(11)]
    st["records"] += 1
    st["header: sum of 11 pair firsts == node count"] += sum(a for a, _ in pairs) == nn
    st["header: sum of 11 pair seconds == link count"] += sum(b for _, b in pairs) == nl
    ends = collections.defaultdict(list)
    for k, node, lw, extra in walk(u):
        st["links"] += 1
        edge = (node[0] & 0x7FF) in (0, 0x7FF) or (node[1] & 0x7FF) in (0, 0x7FF)
        if lw[4] & 0x8000:
            st["boundary link (w4 & 0x8000)"] += 1
            st["boundary link at a mesh-edge node"] += edge
        else:
            ends[(lw[4] & 0xF, lw[3] & 0x1FFF)].append(lw)
        for x in extra[:(lw[2] & 0x3FC0) >> 6]:
            st["turn word"] += 1
            st["turn word, target nibble 0xf (condition record)"] += (x >> 12) == 0xF
            st["turn word, low byte 0xff (always banned)"] += (x & 0xFF) == 0xFF
            st["turn word, low byte 0 (allowed)"] += (x & 0xFF) == 0
    for lst in ends.values():
        if len(lst) != 2:
            continue
        a, b = (x[2] >> 14 for x in lst)
        st["inner link seen from both ends"] += 1
        key = {(0, 0): "two-way (0/0)", (3, 3): "closed (3/3)"}.get((a, b))
        if key is None and {a, b} == {1, 2}:
            key = "one-way (1/2)"
        st["direction " + (key or "other %d/%d" % (a, b))] += 1


def run(tile: str, sample: int | None) -> collections.Counter:
    import tile_relayout
    m = tile_relayout.read_model(open(tile, "rb").read())
    st = collections.Counter()
    for sec in m["sections"]:
        if sec["id"] != 2:
            continue
        for L in sec["levels"]:
            if L["level"] != 1:
                continue
            recs = [r for dm in L["dirs"] for un in dm["units"] for r in un["recs"] if r]
            if sample:
                random.seed(1)
                recs = random.sample(recs, min(sample, len(recs)))
            for raw in recs:
                pl = zlib.decompress(raw)
                w = list(struct.unpack(">%dH" % (len(pl) // 2), pl[:len(pl) // 2 * 2]))
                st["country (header halfword 26) %d" % w[26]] += 1
                check_record(w, st)
    return st


def selftest() -> int:
    # one record: node 0 (edge) with a one-way link to node 1 and a boundary link,
    # node 1 with the other end of the one-way link
    u = [0, 2, 0, 2] + [0, 0] * 11
    u[4:6] = [2, 2]
    u += [0x2000, 0x0100, 0, 1, 0, 0x4000, 0x0003, 5, 0, 0,
          0, 0, 0, 0x0003, 0x8004, 0, 0]
    u += [0x1100, 0x0100, 0, 0, 0, 0x8000, 0x2003, 5, 0, 0]
    w = [0] * 27
    w[6:10] = [0, 27, 0, len(u)]
    st = collections.Counter()
    check_record(w + u, st)
    assert st["direction one-way (1/2)"] == 1, st
    assert st["boundary link at a mesh-edge node"] == 1, st
    assert st["header: sum of 11 pair firsts == node count"] == 1, st
    assert link_words(1, 0x0041, 0x4000) == 4
    print("selftest OK: link size, one-way pairing, boundary links, header pairs")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tile", nargs="?")
    ap.add_argument("--sample", type=int)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.tile:
        ap.error("TILE required")
    for k, v in sorted(run(a.tile, a.sample).items()):
        print("%-55s %d" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
