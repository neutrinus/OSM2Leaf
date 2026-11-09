#!/usr/bin/env python3
"""Classify and decode POINT bit-packed (non-0x60/0x68) zlib inner pages.

M4.27 follow-up to M4.8b (C-2936/C-2939): ``poi_icons.iter_streams`` yields
zlib-compressed inner pages from a ``cmpind``-decoded POINT ``.DAT``.  Name
pages carry ``0x60``/``0x68`` POI records with packed copy-A/B coordinates
(``poi_point_check``).  The remaining "bit-packed" pages have other grammars.

This tool classifies those non-name zlib pages by their first two BE ``u16``
words (``w0,w1``), decodes the dominant fixed-record classes, and reports
whether any decoded class carries coordinate-bearing POI position records in
the known copy-A/B form.  It does not decode undecoded classes (stop
condition): for those it records header bytes and counts only.

Usage::

    point_bitpack_decode.py --selftest
    point_bitpack_decode.py summary ROOT SHARD [SHARD ...]
    point_bitpack_decode.py check-coords ROOT SHARD [SHARD ...]

ROOT contains ``REFER001/SHARD.DAT.cmp`` and ``.ind``.
"""

from __future__ import annotations

import argparse
import collections
import re
import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import cmpind  # noqa: E402
import poi_icons  # noqa: E402


# (w0, w1) -> (record_size_bytes, class_name, coord_bearing)
# coord_bearing: 'no' = demonstrated non-coordinate (ASCII phone/index),
# 'unknown' = structure partially known but coordinate content not established.
KNOWN_CLASSES = {
    (8, 6): (16, "phone-us-fixed16", "no"),
    (10, 8): (20, "phone-intl-fixed20", "no"),
    (1, 6): (24, "index-24b-w1-6", "unknown"),
    (1, 44): (24, "index-24b-w1-44", "unknown"),
    (1, 47): (24, "index-24b-w1-47", "unknown"),
    (1, 9): (24, "index-24b-w1-9", "unknown"),
    (1, 11): (24, "index-24b-w1-11", "unknown"),
    (28, 10): (24, "index-24b-w28", "unknown"),
    (2, 0): (None, "mixed-w2", "unknown"),
}


def classify_page(blob: bytes) -> dict:
    """Classify one decompressed inner page blob."""
    info = {
        "len": len(blob),
        "w0": None,
        "w1": None,
        "class": "short",
        "rec_size": None,
        "coord_bearing": "unknown",
        "ascii_ratio": 0.0,
        "fixed_prefix_ok": None,
    }
    if len(blob) < 4:
        return info
    w0, w1 = struct.unpack_from(">HH", blob, 0)
    info["w0"], info["w1"] = w0, w1
    key = (w0, w1)
    spec = KNOWN_CLASSES.get(key)
    if spec is None:
        # generic w0==1 index family: 24B fixed records with 0xffff sentinels
        if w0 == 1 and len(blob) >= 24:
            spec = (24, f"index-24b-w1-{w1}", "unknown")
        elif w0 == 2:
            spec = (None, "mixed-w2", "unknown")
        else:
            spec = (None, f"unknown-w0-{w0}", "unknown")
    rec_size, cname, cb = spec
    info["class"] = cname
    info["rec_size"] = rec_size
    info["coord_bearing"] = cb
    # ASCII printable ratio over whole page (phone pages are mostly ASCII)
    printable = sum(1 for c in blob if 32 <= c < 127)
    info["ascii_ratio"] = printable / len(blob) if blob else 0.0
    if rec_size and len(blob) >= rec_size * 2:
        n = min(len(blob) // rec_size, 50)
        ok = sum(
            1
            for i in range(0, n * rec_size, rec_size)
            if struct.unpack_from(">HH", blob, i) == (w0, w1)
        )
        info["fixed_prefix_ok"] = ok == n
    return info


def decode_phone_records(blob: bytes, rec_size: int, limit: int = 5) -> list[str]:
    """Extract printable ASCII runs from fixed phone-record pages."""
    out = []
    for i in range(0, min(len(blob), rec_size * limit), rec_size):
        rec = blob[i : i + rec_size]
        # payload after 4-byte (w0,w1) prefix
        payload = rec[4:]
        txt = "".join(chr(c) if 32 <= c < 127 else "" for c in payload)
        txt = txt.strip("\x00")
        if txt:
            out.append(txt)
    return out


def decode_shard(root: Path, shard: str) -> bytes:
    data, _ = cmpind.decode(
        root / "REFER001" / f"{shard}.DAT.cmp",
        root / "REFER001" / f"{shard}.DAT.ind",
    )
    return data


def classify_shard(data: bytes) -> dict:
    name_pages = bit_pages = name_recs = 0
    classes = collections.Counter()
    coord_classes = collections.Counter()
    samples = {}
    for _off, blob in poi_icons.iter_streams(data):
        recs = list(poi_icons.iter_point_records(blob))
        if recs and recs[0][0] in (0x60, 0x68):
            name_pages += 1
            name_recs += len(recs)
            continue
        bit_pages += 1
        ci = classify_page(blob)
        key = (ci["w0"], ci["w1"], ci["class"], ci["coord_bearing"])
        classes[key] += 1
        coord_classes[ci["coord_bearing"]] += 1
        sk = ci["class"]
        if sk not in samples and ci["rec_size"]:
            samples[sk] = {
                "head_hex": blob[:16].hex(),
                "rec_size": ci["rec_size"],
                "fixed_prefix_ok": ci["fixed_prefix_ok"],
                "ascii_ratio": round(ci["ascii_ratio"], 3),
                "phone_samples": decode_phone_records(
                    blob, ci["rec_size"], limit=3
                )
                if ci["coord_bearing"] == "no"
                else [],
            }
        elif sk not in samples:
            samples[sk] = {"head_hex": blob[:16].hex(), "rec_size": None}
    return {
        "name_pages": name_pages,
        "bit_pages": bit_pages,
        "name_records": name_recs,
        "classes": classes,
        "coord_classes": coord_classes,
        "samples": samples,
    }


def geographic_coord_candidates(blob: bytes) -> int:
    """Count >HH pairs that could be packed POI coords (broad heuristic).

    Heuristic only (negative control aid): values in plausible packed-coordinate
    ranges seen in POINT copy-A/B (x roughly 32000-43000, y roughly 32000-43000
    for EU/US 2011 coverage). This is NOT a decoder - a zero/low count on a
    phone page supports 'no coordinate-bearing records'; it cannot prove absence
    in an undecoded bit layout.
    """
    n = 0
    for j in range(0, len(blob) - 3, 2):
        x, y = struct.unpack_from(">HH", blob, j)
        if 32000 <= x <= 43000 and 32000 <= y <= 43000:
            n += 1
    return n


def cmd_summary(args: argparse.Namespace) -> int:
    for shard in args.shards:
        data = decode_shard(Path(args.root), shard)
        r = classify_shard(data)
        print(f"{shard}: name_pages={r['name_pages']} bit_pages={r['bit_pages']} name_records={r['name_records']}")
        for (w0, w1, cls, cb), cnt in r["classes"].most_common():
            print(f"  w0={w0} w1={w1} class={cls} coord={cb} count={cnt}")
        for cls, s in sorted(r["samples"].items()):
            print(f"  sample {cls}: {s}")
    return 0


def cmd_check_coords(args: argparse.Namespace) -> int:
    for shard in args.shards:
        data = decode_shard(Path(args.root), shard)
        r = classify_shard(data)
        print(f"{shard}: bit_pages={r['bit_pages']} coord_classes={dict(r['coord_classes'])}")
        # heuristic scan on one sample per non-no class? and on phone pages as control
        # Scan a few pages per coord class
        seen = collections.defaultdict(int)
        totals = collections.defaultdict(int)
        for _off, blob in poi_icons.iter_streams(data):
            recs = list(poi_icons.iter_point_records(blob))
            if recs and recs[0][0] in (0x60, 0x68):
                continue
            ci = classify_page(blob)
            cb = ci["coord_bearing"]
            if seen[cb] >= 50:
                continue
            seen[cb] += 1
            totals[cb] += geographic_coord_candidates(blob)
        for cb in sorted(seen):
            print(f"  coord_class={cb} pages_sampled={seen[cb]} heuristic_coordlike_pairs={totals[cb]} (heuristic only, not a decoder)")
    return 0


def selftest() -> int:
    failures = []

    def check(name, cond, detail=""):
        print(f"  {name:<44} {'OK' if cond else 'FAIL'} {detail}".rstrip())
        if not cond:
            failures.append(name)

    # US phone page: 16-byte records, w0=8,w1=6, ASCII phone payload (12B)
    rec = struct.pack(">HH", 8, 6) + b"503-3195112\x00"
    assert len(rec) == 16, len(rec)
    page = rec * 10
    ci = classify_page(page)
    check("w0=8 phone class", ci["class"] == "phone-us-fixed16")
    check("w0=8 rec_size 16", ci["rec_size"] == 16)
    check("w0=8 coord_bearing no", ci["coord_bearing"] == "no")
    check("w0=8 fixed prefix", ci["fixed_prefix_ok"] is True)
    ph = decode_phone_records(page, 16, limit=2)
    check("phone decode has ASCII", any("503" in p for p in ph), str(ph[:1]))
    check("phone ascii_ratio high", ci["ascii_ratio"] > 0.5, f"{ci['ascii_ratio']:.2f}")

    # EU intl phone: 20-byte, w0=10,w1=8
    rec2 = struct.pack(">HH", 10, 8) + b"+(34)-946826606\x00"
    assert len(rec2) == 20
    ci2 = classify_page(rec2 * 5)
    check("w0=10 intl phone class", ci2["class"] == "phone-intl-fixed20")
    check("w0=10 coord_bearing no", ci2["coord_bearing"] == "no")
    check("w0=10 rec_size 20", ci2["rec_size"] == 20)

    # index page: w0=1, 24B, ffff sentinels
    idx = struct.pack(">HHHHHHHHHHHH", 1, 44, 0, 565, 0xFFFF, 0xFFFF, 0, 34, 0xFFFF, 16128, 5, 49727)
    assert len(idx) == 24
    ci3 = classify_page(idx * 4)
    check("w0=1 index class", "index-24b" in ci3["class"])
    check("w0=1 rec_size 24", ci3["rec_size"] == 24)
    check("w0=1 fixed prefix", ci3["fixed_prefix_ok"] is True)
    check("w0=1 coord unknown (not name grammar)", ci3["coord_bearing"] == "unknown")

    # mixed w0=2
    ci4 = classify_page(struct.pack(">HHHH", 2, 0, 2, 0) + rec)
    check("w0=2 mixed", ci4["class"].startswith("mixed"))

    # short
    check("short blob", classify_page(b"\x00\x01")["class"] == "short")

    print(f"point_bitpack_decode selftest: {'OK' if not failures else 'FAILED'}")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    sc = sub.add_parser("summary")
    sc.add_argument("root")
    sc.add_argument("shards", nargs="+")
    sc.set_defaults(func=cmd_summary)
    cc = sub.add_parser("check-coords")
    cc.add_argument("root")
    cc.add_argument("shards", nargs="+")
    cc.set_defaults(func=cmd_check_coords)
    return p


def main(argv=None):
    p = build_parser()
    a = p.parse_args(argv)
    if a.selftest:
        return selftest()
    if not getattr(a, "func", None):
        p.print_help()
        return 2
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
