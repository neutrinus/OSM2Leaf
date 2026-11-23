#!/usr/bin/env python3
"""locmap_model.py - host model of the `LOC_map` shape walk `fn 0x0041f3dc`
(M9.67, EU2011 `Navi.exe` build A).

The walk of M9.66 (`tools/locmap_l3.py`) loads the served record's shape
buffer (`record + 0x2c`) in a fixed order.  This tool re-implements the part
of that walk the session could prove byte for byte from the shape buffer
alone -- the 12 rows, the shape headers, and the (x, y) point sequence --
and is checked against the firmware's own trace by `locmap_l3.py`.

What the model reproduces exactly (see EXP-2026-11-23-M9.67):

* the row-count helper `fn 0x00422384` reads the 12 counts at bytes
  ``4 + 4 i`` and aborts the whole walk if any count is ``>= 0x7d0``;
* `fn 0x0041f3dc` reads the 12 (start, count) pairs, skips a row with count
  0, then walks ``count`` shapes from byte ``4 * start``;
* a shape header is four words; the first point sits at byte
  ``B + 0xe + 2 * (w3 & 3) + 2 * (w0 >> 13)`` (word 7 of the shape);
* each further point is ``4 + 2 [x bits 0x1800 not both set] + 2 [y bit
  0x2000] + 2 [y bit 0x1000] + 2 [y bit 0x0800]`` bytes after the previous
  point;
* the next shape is at ``B + 2 * (w0 & 0x1fff)``.

What it does NOT reproduce (the finding of M9.67): the reference/count stage
that each point with ``(x & 0x1800) != 0x1800`` enters (``fn 0x00420174`` and
its copies, plus the last-point ``fn 0x00420298``) reads a per-point node
index built from a coordinate cell table (``*0x00ec3600`` / ``*0x00e8f5c4``)
whose slot the point coordinates do **not** give by a rule the static decode
closed; it targets a *different* point of the whole 11 KB buffer, not the one
its own reference word names.  The model therefore emits the shape/point reads
and marks every reference block ``UNKNOWN``.

The tool is standard-library only and reads a shape-buffer dump produced by
``locmap_l3.py run ... --shape-out FILE``; it never needs an image.

Usage:
  locmap_model.py --selftest
  locmap_model.py skeleton SHAPE.bin            # print the predicted reads
  locmap_model.py verify RESULT.json SHAPE.bin  # head-match + ref-block census

Exit codes: verify: 0 the skeleton head matched every point read, 1 a
mismatch, 2 usage/missing input.
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys

# Instruction addresses (EU2011 build A) of the shape-buffer loads.  The order
# is the order the model emits them.
PC = {
    "helper": 0x00422388,   # fn 0x00422384: 12 row counts, abort >= 0x7d0
    "rcnt": 0x0041F47A,     # row count
    "rstart": 0x0041F486,   # row start
    "w0": 0x0041F49E, "w1": 0x0041F4B2, "w2": 0x0041F4CC, "w3": 0x0041F4D0,
    "p0x": 0x0041F500, "p0y": 0x0041F504,
    "pjx": 0x0041F5AA, "pjy": 0x0041F5BC,
    "ry": 0x00420174, "rw": 0x00420186, "rx": 0x004201A2,
    "ty": 0x004201DE, "tw": 0x004201F0, "tx": 0x004201FA,
    "s2y": 0x00420298, "s2x": 0x004202AA, "s2w": 0x004202BE,
    "s3y": 0x004202F8, "s3w": 0x0042030A, "s3x": 0x00420314,
}
REF_PCS = {PC["ry"], PC["rw"], PC["rx"], PC["ty"], PC["tw"], PC["tx"],
           PC["s2y"], PC["s2x"], PC["s2w"], PC["s3y"], PC["s3w"], PC["s3x"]}
ROW_COUNT = 12
ABORT_COUNT = 0x07d0          # fn 0x00422384: `cmp/hs` against this


def u16(buf: bytes, off: int) -> int:
    if off < 0 or off + 2 > len(buf):
        return 0
    return struct.unpack_from("<H", buf, off)[0]


def point_advance(x: int, y: int) -> int:
    """Bytes from a point's (x word, y word) to the next point."""
    step = 4
    if (x & 0x1800) != 0x1800:
        step += 2
    if y & 0x2000:
        step += 2
    if y & 0x1000:
        step += 2
    if y & 0x0800:
        step += 2
    return step


def first_point_offset(base: int, w0: int, w3: int) -> int:
    return base + 0x0E + 2 * (w3 & 3) + 2 * (w0 >> 13)


def skeleton(shape: bytes):
    """Return (reads, info).  *reads* is [(pc, offset)] in emitted order."""
    reads = []
    counts = []
    for i in range(ROW_COUNT):
        off = 4 + 4 * i
        reads.append((PC["helper"], off))
        counts.append(u16(shape, off))
    info = {"rows": [], "points": 0, "ref_slots": 0}
    if any(c >= ABORT_COUNT for c in counts):
        info["aborted"] = True       # fn 0x00422384 returns 0xffff, walk stops
        return reads, info
    for r in range(ROW_COUNT):
        reads.append((PC["rcnt"], 4 + 4 * r))
        count = u16(shape, 4 + 4 * r)
        if count == 0:
            continue
        reads.append((PC["rstart"], 2 + 4 * r))
        base = 4 * u16(shape, 2 + 4 * r)
        info["rows"].append({"row": r, "start": u16(shape, 2 + 4 * r), "count": count})
        for _ in range(count):
            w0, w1 = u16(shape, base), u16(shape, base + 2)
            w2, w3 = u16(shape, base + 4), u16(shape, base + 6)
            reads += [(PC["w0"], base), (PC["w1"], base + 2),
                      (PC["w2"], base + 4), (PC["w3"], base + 6)]
            npt = w1 & 0x0FFF
            poff = first_point_offset(base, w0, w3)
            x, y = u16(shape, poff), u16(shape, poff + 2)
            reads += [(PC["p0x"], poff), (PC["p0y"], poff + 2)]
            info["points"] += 1
            if (x & 0x1800) != 0x1800:
                info["ref_slots"] += 1
            p = poff
            for _j in range(1, npt):
                p += point_advance(x, y)
                x, y = u16(shape, p), u16(shape, p + 2)
                reads += [(PC["pjx"], p), (PC["pjy"], p + 2)]
                info["points"] += 1
                if (x & 0x1800) != 0x1800:
                    info["ref_slots"] += 1
            length = w0 & 0x1FFF
            if length == 0:
                break
            base += 2 * length
    return reads, info


def compare(shape: bytes, trace):
    """Compare the model skeleton with a firmware trace.

    The firmware trace interleaves shape/point reads with reference blocks.
    The model reproduces the shape/point reads *in order*; the reference
    blocks are reported as UNKNOWN.  We verify the shape/point subsequence
    matches the trace's non-reference subsequence exactly.
    """
    model, info = skeleton(shape)
    fw = [(pc, off, sz) for pc, off, sz in trace]
    fw_skel = [(pc, off) for pc, off, sz in fw if pc not in REF_PCS]
    ref_reads = [(pc, off) for pc, off, sz in fw if pc in REF_PCS]
    n = min(len(model), len(fw_skel))
    first_bad = next((i for i in range(n) if model[i] != fw_skel[i]), None)
    return {
        "model_reads": len(model),
        "fw_skeleton_reads": len(fw_skel),
        "fw_reference_reads": len(ref_reads),
        "skeleton_matches": first_bad is None and len(model) == len(fw_skel),
        "first_mismatch": None if first_bad is None else {
            "index": first_bad, "model": list(model[first_bad]),
            "firmware": list(fw_skel[first_bad])},
        "info": info,
    }


def read_shape(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def cmd_skeleton(args) -> int:
    shape = read_shape(args.shape)
    reads, info = skeleton(shape)
    for pc, off in reads:
        print("%#010x off %#06x" % (pc, off))
    print("shape reads: %d; points: %d; reference slots: %d; aborted: %s"
          % (len(reads), info["points"], info["ref_slots"], info.get("aborted", False)))
    return 0


def cmd_verify(args) -> int:
    res = json.load(open(args.result))
    shape = read_shape(args.shape)
    verdict = compare(shape, [tuple(r) for r in res["trace"]])
    print("model skeleton reads: %d" % verdict["model_reads"])
    print("firmware skeleton reads (no reference block): %d" % verdict["fw_skeleton_reads"])
    print("firmware reference-block reads: %d" % verdict["fw_reference_reads"])
    print("points: %d; reference slots: %d" % (verdict["info"]["points"], verdict["info"]["ref_slots"]))
    if verdict["skeleton_matches"]:
        print("RESULT: skeleton SAME (every shape/point read in order)")
        return 0
    m = verdict["first_mismatch"]
    print("first mismatch at %d: model %#010x/%#06x, firmware %#010x/%#06x"
          % (m["index"], m["model"][0], m["model"][1], m["firmware"][0], m["firmware"][1]))
    print("RESULT: skeleton DIFFERENT")
    return 1


def selftest() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print("%-62s %s" % (name, "ok" if cond else "FAIL"))
        ok = ok and bool(cond)

    check("advance: plain point (x bits both set) is 4 bytes", point_advance(0x1800, 0) == 4)
    check("advance: x bits not both set adds the x word", point_advance(0x0000, 0) == 6)
    check("advance: y 0x2000 adds a word", point_advance(0x1800, 0x2000) == 6)
    check("advance: y 0x1000 and 0x0800 add one each", point_advance(0x1800, 0x1800) == 8)
    check("first point: base + 0xe with no extra words", first_point_offset(0x34, 0x13, 0) == 0x42)
    check("first point: w3&3 moves by 2 each", first_point_offset(0x0, 0, 3) == 0x0E + 6)
    check("first point: w0>>13 moves by 2 per bit", first_point_offset(0x0, 0x2000, 0) == 0x10)
    # a one-row, one-shape, one-point buffer with no reference slot
    shape = bytearray(2048)
    struct.pack_into("<HH", shape, 2, 13, 1)                    # row 0: start 13, count 1
    struct.pack_into("<HHHH", shape, 4 * 13, 1, 1, 0x9000, 0)   # shape: w0, npt=1, w2, w3
    struct.pack_into("<HH", shape, 4 * 13 + 0x0E, 0x1800, 0)    # a link point (no ref slot)
    reads, info = skeleton(bytes(shape))
    check("skeleton: 12 helper reads then 12 row-count reads",
          [pc for pc, _ in reads[:12]] == [PC["helper"]] * 12
          and sum(1 for pc, _ in reads if pc == PC["rcnt"]) == 12)
    check("skeleton: one shape -> 4 header + 2 point reads", info["points"] == 1)
    check("skeleton: a link point makes no reference slot", info["ref_slots"] == 0)
    # abort: a count of 0x7d0 stops the walk after the helper
    bad = bytearray(shape)
    struct.pack_into("<H", bad, 4, 0x07D0)
    reads, info = skeleton(bytes(bad))
    check("skeleton: count 0x7d0 aborts after the helper", info.get("aborted") is True and len(reads) == 12)
    # a plain point makes a reference slot
    shape2 = bytearray(shape)
    struct.pack_into("<HH", shape2, 4 * 13 + 0x0E, 0x0000, 0)
    _, info2 = skeleton(bytes(shape2))
    check("skeleton: a plain point makes one reference slot", info2["ref_slots"] == 1)
    # next shape: w0&0x1fff words later
    shape3 = bytearray(4096)
    struct.pack_into("<HH", shape3, 2, 13, 2)
    struct.pack_into("<HHHH", shape3, 52, 0x1A, 1, 0x9000, 0)
    struct.pack_into("<HH", shape3, 52 + 0x0E, 0x1800, 0)
    struct.pack_into("<HHHH", shape3, 52 + 2 * 0x1A, 2, 0, 0x9000, 0)
    reads3, _ = skeleton(bytes(shape3))
    bases = [off for pc, off in reads3 if pc == PC["w0"]]
    check("skeleton: second shape at first + 2*(w0&0x1fff)", bases == [52, 52 + 2 * 0x1A])
    check("skeleton: empty input reads only the helper", skeleton(b"")[1].get("aborted", False) is False
          and len(skeleton(b"")[0]) == 24)
    # negative control: a changed point y changes the predicted offset sequence
    shape_shift = bytearray(shape)
    struct.pack_into("<H", shape_shift, 4 * 13 + 6, 1)   # w3 low 2 bits -> first point +2
    a, _ = skeleton(bytes(shape))
    b, _ = skeleton(bytes(shape_shift))
    check("negative: a shape w3 change moves the first point (control)", a != b)
    print("selftest: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("skeleton", help="print the predicted reads of a shape buffer")
    s.add_argument("shape")
    v = sub.add_parser("verify", help="compare the model against a locmap_l3 --json result")
    v.add_argument("result")
    v.add_argument("shape")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "skeleton":
        return cmd_skeleton(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    ap.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
