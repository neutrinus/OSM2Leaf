#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Test the KIWI 7.3 Background Data Frame against ZE0 odd-partner records.

The field grammar is quoted from jharg/kiwiread commit 74741c5b (GPL-3, field
names and chapter numbers only; no code copied).  KIWI sizes are in 2-byte
words: D(v) = 2*v (0xffff = empty), SWS(v) = 2*v.  ZE0 records are big-endian
and their layer table uses 4-byte units (clarion_bg.py).

Commands:
  python3 tools/kiwi_bg_probe.py --selftest
  python3 tools/kiwi_bg_probe.py sizes
  python3 tools/kiwi_bg_probe.py hex HEX
  python3 tools/kiwi_bg_probe.py shape HEX
  python3 tools/kiwi_bg_probe.py record TILE --offset 0xDD85C
  python3 tools/kiwi_bg_probe.py frame TILE [--level 1] [--limit 10] [--json OUT]
"""
import argparse
import json
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "ze0-viewer" / "tools_ze0"))
import clarion_bg  # noqa: E402
import clarion_tile  # noqa: E402


def D(v):
    return 0 if v == 0xFFFF else 2 * v


def u16(d, off):
    return struct.unpack_from(">H", d, off)[0]


def kiwi_frame(d):
    """Return (ok, reason, detail) for one inflated geometry block.

    Walk the KIWI 7.3.1 distribution header, 7.3.1.1 element units, 7.3.2.1
    background type units and 7.3.2.2.1 minimum graphics records.  Every check
    is falsifiable: a wrong field gives a byte offset and an impossible value.
    """
    n = len(d)
    if n < 2:
        return False, "short", "len=%d" % n
    hlen = D(u16(d, 0))
    detail = ["hlen=%d len=%d" % (hlen, n)]
    if hlen < 6 or hlen > n:
        return False, "header_size", "hlen=%d outside 6..%d" % (hlen, n)
    units = []
    off = 2
    while off + 4 <= hlen:
        poff, plen = D(u16(d, off)), D(u16(d, off + 2))
        off += 4
        if poff == 0:
            continue
        if poff < hlen or poff + plen > n:
            return False, "element_unit", "poff=%d plen=%d (table %d, block %d)" % (poff, plen, hlen, n)
        units.append((poff, plen))
    if not units:
        return False, "no_element", "hlen=%d" % hlen
    shapes = 0
    for p0, plen in units:
        ntypes = u16(d, p0)
        detail.append("element@%d types=%d" % (p0, ntypes))
        if not (1 <= ntypes <= 256) or p0 + 2 + 4 * ntypes > p0 + plen:
            return False, "type_count", "n=%d at %d, unit ends %d" % (ntypes, p0, p0 + plen)
        q = p0 + 2
        for _ in range(ntypes):
            boff = D(u16(d, q))
            packed = u16(d, q + 2)
            q += 4
            count = packed & 0x7FF
            cls = (packed >> 14) & 3
            g = q - 4 + boff  # kiwiread prints poff+boff before ++poff
            if g + 12 > p0 + plen or g + 12 + 2 * count > p0 + plen:
                return False, "type_unit", "class=%d n=%d off=%d, unit ends %d" % (cls, count, g, p0 + plen)
            for _j in range(count):
                hdr, flag = u16(d, g), u16(d, g + 2)
                size, ncoord = D(hdr), flag & 0x7FF
                addl = u16(d, g + 6)
                need = 12 + 2 * ncoord + 2 * ((addl >> 11) & 1) + 2 * ((addl >> 12) & 1)
                if size != need or g + size > p0 + plen:
                    return False, "graphics", "off=%d SWS(hdr)=%d need=%d ncoord=%d" % (g, size, need, ncoord)
                g += size
                shapes += 1
    return True, "fit", "units=%d shapes=%d; %s" % (len(units), shapes, "; ".join(detail))


def mingr_alignment(d):
    """Compare KIWI 7.3.2.2.1 words with the ZE0 background shape words."""
    if len(d) < 10:
        return None
    hdr, flag, code, addl, sx, sy = struct.unpack_from(">6H", d, 0)
    kiwi_n = flag & 0x7FF
    kiwi_ok = D(hdr) == 12 + 2 * kiwi_n
    ze0_n = hdr
    ze0_prefix = 0 < ze0_n < 0x800 and len(d) >= 10 and 10 + 2 * ze0_n >= len(d)
    ze0_ok = ze0_prefix and len(d) == 10 + 2 * ze0_n
    return dict(kiwi_size=D(hdr), kiwi_ncoord=kiwi_n, kiwi_code=code, kiwi_fit=kiwi_ok,
                ze0_count=ze0_n, ze0_type=code, ze0_prefix_ok=ze0_prefix,
                ze0_fit=ze0_ok, bytes=len(d))


def synthetic_kiwi_frame():
    """Positive control built only from the quoted KIWI 7.3 field lists."""
    shapes = b""
    for code, sx, sy in ((0x0121, 0x0010, 0x0020), (0x0122, 0x0030, 0x0040)):
        shapes += struct.pack(">6H", 8, 2, code, 0x0010, sx, sy) + struct.pack(">bbbb", 4, -4, 8, 4)
    data = struct.pack(">HHH", 1, 2, 0x8002) + shapes  # n=1, type unit, 2 shapes
    assert len(data) == 2 + 4 + 32
    # element unit starts at 6 and ends at 44: 38 bytes -> 19 words
    return struct.pack(">HHH", 3, 3, 19) + data


def geom_of(rec):
    raw = rec["raw"]
    try:
        p = zlib.decompressobj().decompress(raw)
    except zlib.error:
        return None, None
    if len(p) < 44:
        return None, None
    w = struct.unpack_from(">22H", p, 0)
    gi = clarion_bg.bg_slot(w)
    off, ln = w[gi], w[gi + 1]
    if off in (0, 0xFFFF) or ln == 0 or 4 * off + 4 * ln > len(p):
        return None, None
    return p, p[4 * off:4 * off + 4 * ln]


def record_at(path, offset):
    """One inflated background record at a known file offset: ZE0 model + KIWI verdict."""
    d = Path(path).read_bytes()
    p = zlib.decompressobj().decompress(d[offset:])
    model = clarion_bg.parse_record(p)
    w = model["hdr"]
    gi = model["gi"]
    geom = p[4 * w[gi]:4 * w[gi] + 4 * w[gi + 1]]
    ok, why, detail = kiwi_frame(geom)
    types, closed, total = {}, 0, 0
    first = None
    for layer in model["layers"].values():
        for s in layer.get("shapes", []):
            t = "%04x" % s["type"]
            types[t] = types.get(t, 0) + 1
            pts = s.get("pts", [])
            total += 1
            if len(pts) > 2 and pts[0] == pts[-1]:
                closed += 1
            if first is None:
                q = p.index(struct.pack(">H", s["type"]), 4 * w[gi])
                first = p[q - 2:q + 10].hex()
    return dict(file=str(path), sha256=__import__("hashlib").sha256(d).hexdigest(),
                offset=hex(offset), inflated=len(p), geometry=len(geom),
                header=" ".join("%04x" % x for x in w), nlayers=model["nlayers"],
                kinds={"%02x" % k: sorted(v.keys()) if isinstance(v, dict) else []
                       for k, v in model["layers"].items()},
                zeo_types=types, zeo_shapes=total, zeo_closed=closed,
                first_shape=first, first_shape_alignment=mingr_alignment(bytes.fromhex(first)) if first else None,
                kiwi_fit=ok, kiwi_reason=why, kiwi_detail=detail)


def frame_tile(path, level, limit):
    d = Path(path).read_bytes()
    t = clarion_tile.read_tile(d)
    rows, reasons = [], {}
    for sec in t["sections"]:
        if sec["id"] != 1:
            continue
        for L in sec["levels"]:
            if level is not None and L["level"] != level:
                continue
            for di, DIR in enumerate(L["dirs"]):
                for slot, S in DIR["slots"].items():
                    if slot % 2 == 0:  # odd partner = background
                        continue
                    for k, rec in enumerate(S["recs"]):
                        p, geom = geom_of(rec)
                        if geom is None:
                            continue
                        ok, reason, detail = kiwi_frame(geom)
                        reasons[reason] = reasons.get(reason, 0) + 1
                        if len(rows) < limit:
                            rows.append(dict(section=sec["id"], level=L["level"], dir=di,
                                             dir_off=hex(DIR["off"]), slot=slot, rec=k,
                                             record_len=len(p), geom_len=len(geom),
                                             ok=ok, reason=reason, detail=detail))
    return dict(file=str(path), sha256=__import__("hashlib").sha256(d).hexdigest(),
                level=level, records=sum(reasons.values()), reasons=reasons, samples=rows)


def selftest():
    good = synthetic_kiwi_frame()
    ok, why, _ = kiwi_frame(good)
    assert ok and why == "fit", (ok, why)
    bad = bytearray(good)
    struct.pack_into(">H", bad, 0, 0x7F)  # hlen far outside the block
    ok2, why2, _ = kiwi_frame(bytes(bad))
    assert not ok2 and why2 == "header_size", (ok2, why2)
    bad2 = bytearray(good)
    struct.pack_into(">H", bad2, 12 + 2, 0x00FF)  # ncoord 255 vs 2 -> size mismatch
    ok3, why3, _ = kiwi_frame(bytes(bad2))
    assert not ok3 and why3 in ("graphics", "type_unit"), (ok3, why3)
    # A ZE0-shaped table (26 four-byte units, first offset 26) must be rejected
    # by the KIWI 7.3.1 header check, not silently accepted.
    ze0 = bytearray(4 * 40)
    struct.pack_into(">H", ze0, 0, 26)
    ok4, why4, _ = kiwi_frame(bytes(ze0))
    assert not ok4 and why4 in ("header_size", "element_unit", "no_element"), (ok4, why4)
    a = mingr_alignment(good[12:28])
    assert a["kiwi_fit"] and not a["ze0_fit"], a
    zshape = struct.pack(">5H", 2, 0xC112, 0xFFFF, 0x07FF, 0x0666) + bytes([0x98, 0xC6, 0x98, 0xC7])
    z = mingr_alignment(zshape)
    assert z and not z["kiwi_fit"] and z["ze0_fit"], z
    print("kiwi_bg_probe selftest: synthetic KIWI frame FIT, 3 mutations REJECT, "
          "ZE0 table REJECT, shape alignment 2/2 OK")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("sizes")
    p = sub.add_parser("hex")
    p.add_argument("hex")
    p = sub.add_parser("shape")
    p.add_argument("hex")
    p = sub.add_parser("record")
    p.add_argument("tile")
    p.add_argument("--offset", required=True)
    p = sub.add_parser("frame")
    p.add_argument("tile")
    p.add_argument("--level", type=int, default=1)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--json")
    a = ap.parse_args(argv)
    if a.selftest:
        selftest()
        return 0
    if a.cmd == "sizes":
        print("KIWI 7.3.1 header: hlen=SWS(u16@0) bytes, entries at +2 step 4: "
              "(D(off), SWS(len))\nKIWI 7.3.2.1 type unit: (D(off), "
              "class=bits14..15, n=bits0..11)\nKIWI 7.3.2.2.1 mingr_t: "
              "hdr SWS=size, flag n=bits0..10, code, addl, sx, sy, int8 dx,dy\n"
              "D(v)=SWS(v)=2*v unless ffff\nZE0 layer table: u16 pairs in 4-byte units "
              "(clarion_bg.py)")
        return 0
    if a.cmd in ("hex", "shape"):
        d = bytes.fromhex(a.hex.replace(" ", ""))
        if a.cmd == "hex":
            ok, why, detail = kiwi_frame(d)
            print("KIWI frame: %s (%s) %s" % ("FIT" if ok else "NO FIT", why, detail))
            return 0 if ok else 1
        r = mingr_alignment(d)
        print(json.dumps(r, indent=2))
        return 0
    if a.cmd == "record":
        print(json.dumps(record_at(a.tile, int(a.offset, 0)), indent=2))
        return 0
    if a.cmd == "frame":
        out = frame_tile(a.tile, a.level, a.limit)
        text = json.dumps(out, indent=2)
        if a.json:
            Path(a.json).write_text(text + "\n")
        print("file %s sha256 %s" % (out["file"], out["sha256"]))
        print("records=%d reasons=%s" % (out["records"], out["reasons"]))
        for r in out["samples"]:
            print("  L%d dir@%s slot %d rec %d len %d/%d %s %s" %
                  (r["level"], r["dir_off"], r["slot"], r["rec"], r["record_len"],
                   r["geom_len"], r["reason"], r["detail"][:160]))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
