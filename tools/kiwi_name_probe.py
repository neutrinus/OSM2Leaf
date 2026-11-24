#!/usr/bin/env python3
"""KIWI 7.4 Name Data Frame vs ZE0 tile names / section 4 (M4.71).

Field names and chapter numbers are from <https://github.com/jharg/kiwiread>
commit 74741c5b75695b7004cc1dea9a9348eab2a511e0 (GPL-3; names and chapter
numbers only, no code copied).  This is NOT a KIWI reader: it answers the
narrow question "do the KIWI 7.4 byte fields describe our section-4 name
records and tile name bytes?" with a synthetic positive control, explicit
negative mutations and a counted corpus.

Usage:
    python3 tools/kiwi_name_probe.py --selftest
    python3 tools/kiwi_name_probe.py fields TILE [--limit N]
    python3 tools/kiwi_name_probe.py placement TILE
    python3 tools/kiwi_name_probe.py names TILE --target TEXT
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "ze0-viewer" / "tools_ze0"))
import clarion_tile  # noqa: E402
import section4 as s4  # noqa: E402

COMMIT = "74741c5b75695b7004cc1dea9a9348eab2a511e0"
SWS_SENTINEL = 0xFFFF


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sws(v: int) -> int:
    return SWS_SENTINEL if v == SWS_SENTINEL else 2 * v


def D(v: int) -> int:
    return SWS_SENTINEL if v == SWS_SENTINEL else 2 * v


def extract(word: int, hi: int, lo: int) -> int:
    return (word >> lo) & ((1 << (hi - lo + 1)) - 1)


def u16(b: bytes, o: int) -> int:
    return struct.unpack_from(">H", b, o)[0]


def records(path: str) -> list[dict]:
    """All decompressed level-1 records of one tile, with section/dir context."""
    data = Path(path).read_bytes()
    out = []
    for sec in clarion_tile.read_tile(data)["sections"]:
        for lvl in sec["levels"]:
            for dr in lvl["dirs"]:
                for slot, s in dr["slots"].items():
                    for rec in s["recs"]:
                        raw = rec["raw"]
                        plain = (zlib.decompress(raw)
                                 if clarion_tile.is_zlib(raw) else raw)
                        out.append({
                            "section": sec["id"], "dir": dr["off"],
                            "slot": slot, "k": rec["k"], "plain": plain,
                        })
    return out


def section4_records(path: str) -> list[dict]:
    r = [x for x in records(path) if x["section"] == 4 and len(x["plain"]) >= 0x12]
    return [x for x in r if u16(x["plain"], 4) == s4.TYPE_TAG]


def name_span(plain: bytes):
    """M4.75: word6 offset, word7 word count (both big-endian at 0x0c)."""
    if len(plain) < 0x10:
        return None
    w6, w7 = u16(plain, 0x0C), u16(plain, 0x0E)
    if not (0 < w6 and 0 < w7 and w6 * 2 + 2 * w7 <= len(plain)):
        return None
    return w6, w7, plain[w6 * 2:w6 * 2 + 2 * w7]


# --------------------------------------------------------------------------
# KIWI 7.4 synthetic field grammar (positive control).
def synth_kiwi(st: int, text: bytes) -> bytes:
    """One KIWI 7.4 distribution header, one mgmt pair, one name record of kind st."""
    buf = bytearray(0x100)
    struct.pack_into(">H", buf, 0, 3)               # SWS header = 6 bytes
    struct.pack_into(">HH", buf, 2, 7, 1)           # D offset = 14, N = 1
    p = 14
    struct.pack_into(">HHH", buf, p, 0x0601, (st << 8) | 0x40, 0x0131)
    # sx/sy coordinates (st != 4)
    struct.pack_into(">HH", buf, p + 6, 0x1234, 0x2345)
    if st == 1:
        struct.pack_into(">H", buf, p + 12, len(text) // 2)  # word count
        buf[p + 14:p + 14 + len(text)] = text
    elif st == 4:
        struct.pack_into(">HH", buf, p + 6, 0x0020, 0x0010)
        struct.pack_into(">H", buf, p + 10, len(text) // 2)
        buf[p + 12:p + 12 + len(text)] = text
    elif st == 5:
        struct.pack_into(">HH", buf, p + 12, 0x005A, len(text) // 2)
        buf[p + 16:p + 16 + len(text)] = text
    elif st == 6:
        struct.pack_into(">HH", buf, p + 12, 0x0030, len(text) // 2)
        buf[p + 16:p + 16 + len(text)] = text
    return bytes(buf)


def kiwi_parse(buf: bytes) -> dict:
    """Walk the KIWI 7.4 frame built by synth_kiwi; return fields or a reason."""
    if len(buf) < 2:
        return {"ok": False, "reason": "short"}
    hlen = sws(u16(buf, 0))
    if not (6 <= hlen <= len(buf)):
        return {"ok": False, "reason": "header_size", "hlen": hlen}
    pairs = []
    for off in range(2, hlen - 3, 4):
        toff, tnum = D(u16(buf, off)), u16(buf, off + 2)
        if toff == SWS_SENTINEL:
            continue
        if not (0 <= toff < len(buf)) or not (1 <= tnum <= 256):
            return {"ok": False, "reason": "management", "toff": toff, "tnum": tnum}
        pairs.append((toff, tnum))
    if not pairs:
        return {"ok": False, "reason": "no_management"}
    toff, tnum = pairs[0]
    recs = []
    for _ in range(tnum):
        if toff + 6 > len(buf):
            return {"ok": False, "reason": "record_short"}
        na, attr1, attr2 = struct.unpack_from(">HHH", buf, toff)
        st = extract(attr1, 10, 8)
        if st not in (1, 4, 5, 6):
            return {"ok": False, "reason": "string_type", "st": st}
        if st == 1:
            sp = toff + 12
            wl = u16(buf, sp)
            start = sp + 2
        elif st == 4:
            sp = toff + 10
            wl = u16(buf, sp)
            start = sp + 2
        else:
            sp = toff + 14
            wl = u16(buf, sp)
            start = sp + 2
        slen = 2 * wl
        if not (0 < slen <= 256) or start + slen > len(buf):
            return {"ok": False, "reason": "string_length", "slen": slen}
        text = bytes(buf[start:start + slen]).rstrip(b"\0")
        recs.append({"st": st, "na": na, "attr1": attr1, "attr2": attr2,
                     "slen": slen, "text": text.decode("ascii", "replace")})
        toff = start + slen
    return {"ok": True, "hlen": hlen, "pairs": pairs, "records": recs}


def _selftest() -> int:
    fails = []

    def check(name, cond):
        print("  %-58s %s" % (name, "ok" if cond else "FAIL"))
        if not cond:
            fails.append(name)

    for st in (1, 4, 5, 6):
        text = b"KIWI%d" % st + b"\0"
        if len(text) % 2:
            text += b"\0"
        parsed = kiwi_parse(synth_kiwi(st, text))
        check("synthetic KIWI st=%d parses" % st,
              parsed.get("ok") and parsed["records"][0]["st"] == st
              and parsed["records"][0]["text"] == "KIWI%d" % st)
    base = bytearray(synth_kiwi(1, b"KIWI1\0"))
    bad = bytearray(base)
    struct.pack_into(">H", bad, 0, 0xFFF0)       # hlen outside frame
    check("mutant hlen rejected", kiwi_parse(bytes(bad)).get("reason") == "header_size")
    bad = bytearray(base)
    struct.pack_into(">H", bad, 2, 0xFF00)       # mgmt offset outside frame
    check("mutant management offset rejected", kiwi_parse(bytes(bad)).get("reason") == "management")
    bad = bytearray(base)
    struct.pack_into(">H", bad, 14 + 2, (7 << 8) | 0x40)  # st=7 unsupported
    check("mutant string type rejected", kiwi_parse(bytes(bad)).get("reason") == "string_type")
    bad = bytearray(base)
    struct.pack_into(">H", bad, 14 + 12, 0x03FF)  # slen too long
    check("mutant string length rejected", kiwi_parse(bytes(bad)).get("reason") == "string_length")
    plain = bytearray(0x40)
    struct.pack_into(">HHH", plain, 0, 0x1234, 0x5678, s4.TYPE_TAG)
    struct.pack_into(">HH", plain, 0x0C, 9, 8)   # word6=9 -> byte 18, word7=8 -> 16 B
    plain[18:34] = b"0=LINDOS\x000=RODOS"
    sp = name_span(bytes(plain))
    check("synthetic ZE0 word6/word7 decode",
          sp is not None and b"LINDOS" in sp[2] and b"RODOS" in sp[2])
    check("synthetic ZE0 is not a KIWI frame",
          not kiwi_parse(plain).get("ok"))
    print("kiwi_name_probe selftest: %d checks, %s" %
          (15, "OK" if not fails else "FAIL " + ", ".join(fails)))
    return 1 if fails else 0


# --------------------------------------------------------------------------
def cmd_fields(args) -> int:
    path = args.tile
    data = Path(path).read_bytes()
    recs = section4_records(path)
    named = [r for r in recs if name_span(r["plain"])]
    if not named:
        print("no named section-4 records in %s" % path)
        return 2
    r = named[0]
    p = r["plain"]
    w = struct.unpack_from(">6H", p, 0)
    sp = name_span(p)
    print("tile %s sha256 %s" % (path, sha256(data)))
    print("record dir %#x slot %d k %d length %d" %
          (r["dir"], r["slot"], r["k"], len(p)))
    print("record words[0:6] %s" % " ".join("%04x" % x for x in w))
    print("record bytes[0:24] %s" % p[:24].hex(" "))
    field_tests = [
        ("7.4.1 hlen SWS(u16@0)", "section-4 u16@0 = parcel w0 %#x, no length field" % w[0],
         "NO FIT" if sws(w[0]) > len(p) else "ACCIDENTAL"),
        ("7.4.1 mgmt (D offset, N count)", "u16@2 = parcel w1 %#x; u16@4 = type %#x" % (w[1], w[2]),
         "NO FIT" if D(w[1]) >= len(p) else "ACCIDENTAL"),
        ("7.4.2.1.1 na bits 0..11", "u16@6 = %#x (0x06..0x0f UNKNOWN in map-tiles.md)" % w[3],
         "UNKNOWN"),
        ("7.4.2.1.1 attr1 bits 8..10 st", "u16@8 = %#x -> st=%d" % (w[4], extract(w[4], 10, 8)),
         "NO FIT" if extract(w[4], 10, 8) not in (1, 4, 5, 6) else "ACCIDENTAL"),
        ("7.4.2.1.1 attr2 type", "u16@10 = %#x; type tag at 0x04 = %#x" % (w[5], w[2]),
         "NO FIT"),
        ("7.4.2.1.x string length words x2", "word6=%d word7=%d -> %d B span" %
         (sp[0], sp[1], len(sp[2])), "FITS"),
        ("7.4.2.1.x string bytes", "hex %s" % sp[2][:32].hex(), "FITS"),
        ("7.4.2.1.x sx/sy coordinates", "name list is d=TEXT, no per-label coord pair", "NO FIT"),
    ]
    for name, detail, verdict in field_tests:
        print("%-34s %-58s %s" % (name, detail, verdict))
    kres = kiwi_parse(p)
    print("KIWI 7.4 walker on this record: ok=%s reason=%s" %
          (kres.get("ok"), kres.get("reason")))
    if args.json:
        Path(args.json).write_text(json.dumps({
            "tile": path, "sha256": sha256(data), "record": {k: v for k, v in r.items() if k != "plain"},
            "fields": field_tests, "kiwi": kres,
        }, indent=1, default=str))
    return 0


def cmd_placement(args) -> int:
    path = args.tile
    data = Path(path).read_bytes()
    recs = records(path)
    s4recs = [r for r in recs if r["section"] == 4 and len(r["plain"]) >= 0x12
              and u16(r["plain"], 4) == s4.TYPE_TAG]
    prefixes = collections.Counter()
    st_candidates = collections.Counter()
    named_odd = 0
    for r in s4recs:
        names, _ = s4.scan_names(r["plain"])
        for n in names:
            prefixes["%d=" % n["prefix"]] += 1
    for r in recs:
        if r["section"] != 1 or len(r["plain"]) < 44:
            continue
        w = struct.unpack_from(">22H", r["plain"], 0)
        if w[2] not in (0x19, 0x3E8, 0xFA, 0xFA0):
            continue
        o, ln = w[11], w[12]
        if o == 0xFFFF or not ln or 4 * o + 24 > len(r["plain"]):
            continue
        sec = r["plain"][4 * o:4 * o + 4 * ln]
        nlab = u16(sec, 0)
        if nlab in (0, 0xFFFF) or nlab > 256:
            continue
        named_odd += 1
        off = 24
        for _ in range(nlab):
            if off + 10 > len(sec):
                break
            h = struct.unpack_from(">5H", sec, off)
            wl = h[4] & 0x3FF
            txt = sec[off + 10:off + 10 + wl]
            if 4 <= wl <= 64 and all(0x20 <= b < 0x7F or b == 0 for b in txt):
                st_candidates[extract(h[1], 10, 8)] += 1
            off += 10 + wl
            while off % 4:
                off += 1
    print("tile %s sha256 %s" % (path, sha256(data)))
    print("section-4 records %d, named odd records %d" % (len(s4recs), named_odd))
    print("ZE0 name digit-prefix histogram (section 4): %s" %
          sorted(prefixes.items()))
    print("KIWI attr1 bits 8..10 candidate st histogram (odd name labels): %s" %
          sorted(st_candidates.items()))
    print("KIWI placement kinds 1=barycentric 4=linear-B 5=linear-C 6=symbol+string")
    if args.json:
        Path(args.json).write_text(json.dumps({
            "tile": path, "sha256": sha256(data), "s4_records": len(s4recs),
            "named_odd": named_odd, "prefixes": dict(prefixes),
            "st_candidates": dict(st_candidates),
        }, indent=1))
    return 0


def cmd_names(args) -> int:
    path = args.tile
    data = Path(path).read_bytes()
    target = args.target.encode("latin-1")
    for r in section4_records(path):
        sp = name_span(r["plain"])
        if not sp or target not in sp[2]:
            continue
        w6, w7, raw = sp
        names, _ = s4.scan_names(r["plain"])
        local = [n for n in names if n["offset"] == w6 * 2]
        spans = [n["text"] for n in names if w6 * 2 <= n["offset"] < w6 * 2 + 2 * w7]
        text = raw.rstrip(b"\0").decode("cp1252", "replace")
        print("tile %s sha256 %s" % (path, sha256(data)))
        print("record dir %#x slot %d k %d" % (r["dir"], r["slot"], r["k"]))
        print("word6=%d word7=%d bytes=%d" % (w6, w7, len(raw)))
        print("raw hex %s" % raw.hex())
        print("cp1252 decode %r" % text)
        print("section4.scan_names on same span: %s" % spans)
        print("match %s" % (len(spans) > 0 and all(s in text for s in spans)))
        high = sorted({b for b in raw if b >= 0x80})
        print("high bytes %s" % " ".join("%02x" % b for b in high))
        for b in high[:4]:
            print("  %02x cp1252=%r latin-2=%r" %
                  (b, bytes([b]).decode("cp1252", "replace"),
                   bytes([b]).decode("iso-8859-2", "replace")))
        if args.json:
            Path(args.json).write_text(json.dumps({
                "tile": path, "sha256": sha256(data), "word6": w6, "word7": w7,
                "raw_hex": raw.hex(), "text": text, "span_names": spans,
                "high_bytes": [hex(b) for b in high],
            }, indent=1))
        return 0
    print("target %r not found in %s" % (args.target, path))
    return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("fields")
    p.add_argument("tile")
    p.add_argument("--limit", type=int, default=1)
    p.add_argument("--json")
    p.set_defaults(func=cmd_fields)
    p = sub.add_parser("placement")
    p.add_argument("tile")
    p.add_argument("--json")
    p.set_defaults(func=cmd_placement)
    p = sub.add_parser("names")
    p.add_argument("tile")
    p.add_argument("--target", required=True)
    p.add_argument("--json")
    p.set_defaults(func=cmd_names)
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not getattr(args, "cmd", None):
        ap.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
