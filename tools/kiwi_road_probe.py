#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Test the KIWI 7.2 Road Data Frame against ZE0 section-1 road records.

Field grammar quoted from jharg/kiwiread commit 74741c5b (GPL-3; field names
and chapter numbers only, no code copied).  Sizes are in 2-byte words:
SWS(v)=D(v)=2*v unless 0xffff.  ZE0 records are big-endian.

Commands:
  python3 tools/kiwi_road_probe.py --selftest
  python3 tools/kiwi_road_probe.py record TILE --offset 0x...
  python3 tools/kiwi_road_probe.py frame TILE [--level 1] [--limit N] [--json OUT]
  python3 tools/kiwi_road_probe.py --tree ROOT --tile B48R058R  # M4.69 replay
  python3 tools/kiwi_road_probe.py --card IMG --tile B48R058R   # one FAT file, no 7z
"""
import argparse
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "ze0-viewer" / "tools_ze0"))
import clarion_tile  # noqa: E402

import tilewriter  # noqa: E402

import _kiwi_replay as replay  # noqa: E402


def D(v):
    return 0 if v == 0xFFFF else 2 * v


def u8(d, o):
    return d[o]


def u16(d, o):
    return struct.unpack_from(">H", d, o)[0]


def u32(d, o):
    return struct.unpack_from(">I", d, o)[0]


def kiwi_road_frame(d):
    """Return (ok, reason, detail) for one inflated section-1 road record."""
    n = len(d)
    if n < 8:
        return False, "short", "len=%d" % n
    hlen = D(u16(d, 0))
    ninter, ndc, nad = u16(d, 2), u8(d, 4), u8(d, 5)
    lvl = (u16(d, 6) >> 10) & 0x3F
    detail = ["hlen=%d len=%d inter=%d ndc=%d nad=%d lvl=%d" % (hlen, n, ninter, ndc, nad, lvl)]
    if hlen < 8 + 4 * ndc or hlen > n:
        return False, "header_size", "hlen=%d needs>=%d len=%d" % (hlen, 8 + 4 * ndc, n)
    polys, off = 0, 8
    for i in range(ndc):
        xoff = D(u16(d, off))
        npoly = u16(d, off + 2) & 0x7FF
        off += 4
        if xoff == 0:
            continue
        if xoff + 2 > n:
            return False, "display_offset", "class %d xoff=%d outside len=%d" % (i, xoff, n)
        q = xoff + 2
        for j in range(npoly):
            if q + 16 > n:
                return False, "multilink", "poly %d/%d at %d outside len=%d" % (j, npoly, q, n)
            hdr = u32(d, q)
            nnodes = u16(d, q + 4) & 0x7FF
            shape = D(u16(d, q + 6) & 0x7FF)
            addl = D(u16(d, q + 8) & 0x7FF)
            alt = D(u16(d, q + 10) & 0x7FF)
            passage = D(u16(d, q + 12) & 0x7FF)
            size = D((hdr >> 16) & 0xFFF)
            need = 16 + shape + addl + alt + passage
            if size < need or q + size > n:
                return False, "multilink_size", "poly %d size=%d need>=%d at %d" % (j, size, need, q)
            rtype = (u16(d, q + 14) >> 12) & 0xF
            if rtype > 7:
                return False, "road_type", "poly %d rtype=%d" % (j, rtype)
            polys += 1
            q += size
        detail.append("class %d xoff=%d npoly=%d" % (i, xoff, npoly))
    return True, "fit", "%s polys=%d" % ("; ".join(detail), polys)


def synthetic_kiwi_road():
    """Positive control built only from the quoted 7.2 field lists."""
    # distribution header: hlen=14 bytes -> word 7, 1 intersection, 1 class,
    # 0 additional, level 3; one display class at byte 8+4=12 -> word 6.
    head = struct.pack(">H H B B H", 7, 1, 1, 0, 3 << 10)
    assert len(head) == 8
    cls = struct.pack(">HH", 6, 1)  # D(6)=12, npoly=1
    # multilink at byte 12 (after the class's display-scale word at 14..15 -> poly at 16)
    poly = struct.pack(">I", (10 << 16))  # management size 20 bytes
    poly += struct.pack(">H", 2)          # nodes
    poly += struct.pack(">HHHH", 0, 0, 0, 0)  # shape/additional/altitude/passage
    poly += struct.pack(">H", 3 << 12)    # road type 3
    poly += b"\x00" * 4                   # pad to 20 bytes
    assert len(poly) == 20
    return head + cls + b"\x00\x00" + poly


def road_records(tile_bytes, level=1):
    tile = clarion_tile.read_tile(tile_bytes)
    entry = tilewriter.road_level(tile, level)
    for di, directory in enumerate(entry["dirs"]):
        for slot, S in directory["slots"].items():
            for rec in S["recs"]:
                if rec["k"] % 2:
                    continue
                try:
                    plain = zlib.decompressobj().decompress(rec["raw"])
                except zlib.error:
                    continue
                if len(plain) < 6 or struct.unpack_from(">H", plain, 4)[0] != 0x00FA:
                    continue
                yield dict(dir=hex(directory["off"]), slot=slot, rec=rec["k"], plain=plain, raw=rec["raw"])


def frame_tile(path, level, limit, max_records=0):
    data = Path(path).read_bytes()
    reasons, samples, seen = {}, [], 0
    for rec in road_records(data, level):
        if max_records and seen >= max_records:
            break
        seen += 1
        ok, why, detail = kiwi_road_frame(rec["plain"])
        reasons[why] = reasons.get(why, 0) + 1
        if len(samples) < limit:
            samples.append(dict(dir=rec["dir"], slot=rec["slot"], rec=rec["rec"],
                                size=len(rec["plain"]), ok=ok, reason=why, detail=detail))
    return dict(file=str(path), sha256=hashlib.sha256(data).hexdigest(), level=level,
                records=seen, reasons=reasons, samples=samples)


def selftest():
    good = synthetic_kiwi_road()
    ok, why, detail = kiwi_road_frame(good)
    assert ok and why == "fit", (ok, why, detail)
    bad = bytearray(good)
    struct.pack_into(">H", bad, 0, 0x7FFF)  # header size outside the 44-byte buffer
    ok2, why2, _ = kiwi_road_frame(bytes(bad))
    assert not ok2 and why2 in ("header_size", "display_offset"), (ok2, why2)
    bad2 = bytearray(good)
    struct.pack_into(">H", bad2, 0x1C, 0x9000)  # rtype=9, outside KIWI 0..7
    ok3, why3, _ = kiwi_road_frame(bytes(bad2))
    assert not ok3 and why3 == "road_type", (ok3, why3)
    real = bytes.fromhex("9b8fd3ff00fa347a2aef")
    ok4, why4, detail4 = kiwi_road_frame(real)
    assert not ok4 and why4 == "header_size", (ok4, why4, detail4)
    print("kiwi_road_probe selftest: synthetic KIWI road FIT, 3 mutations REJECT, ZE0 header REJECT")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--hex", help="hex bytes of one inflated road record")
    replay.add_source_args(ap)
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("frame")
    p.add_argument("tile")
    p.add_argument("--level", type=int, default=1)
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--max-records", type=int, default=0)
    p.add_argument("--json")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.hex:
        ok, why, detail = kiwi_road_frame(bytes.fromhex(a.hex.replace(" ", "")))
        print("KIWI road frame: %s (%s) %s" % ("FIT" if ok else "NO FIT", why, detail))
        return 0
    try:
        source = replay.resolve(a)
    except replay.SourceError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    if source is not None:
        out = frame_tile(source.path, level=1, limit=3, max_records=3000)
        print("file %s sha256 %s" % (source.display, out["sha256"]))
        print("records=%d reasons=%s" % (out["records"], out["reasons"]))
        for s in out["samples"]:
            print("  dir %s slot %d rec %d len %d %s %s" %
                  (s["dir"], s["slot"], s["rec"], s["size"], s["reason"], s["detail"][:140]))
        fits = out["reasons"].get("fit", 0)
        summary = "%s fits=%d/%d records=%d reasons=%s" % (
            replay.norm_tile(a.tile), fits, out["records"], out["records"], out["reasons"])
        return replay.replay_line(source, "EXP-2026-11-22-M4.69-kiwi-road-frame", summary)
    if a.cmd == "frame":
        out = frame_tile(a.tile, a.level, a.limit, a.max_records)
        if a.json:
            Path(a.json).write_text(json.dumps(out, indent=2) + "\n")
        print("file %s sha256 %s" % (out["file"], out["sha256"]))
        print("records=%d reasons=%s" % (out["records"], out["reasons"]))
        for s in out["samples"]:
            print("  dir %s slot %d rec %d len %d %s %s" %
                  (s["dir"], s["slot"], s["rec"], s["size"], s["reason"], s["detail"][:140]))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
