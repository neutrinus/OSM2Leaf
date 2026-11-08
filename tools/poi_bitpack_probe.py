#!/usr/bin/env python3
"""Probe POINT bit-packed (non-name-record) zlib pages for 0..2047-class
coordinate-like fields (M4.8b re-attempt).

``poi_icons.iter_streams`` yields zlib-compressed inner pages; name-record
pages decode via ``iter_point_records`` (tag 0x60/0x68).  The remaining pages
often start ``00 xx 00 yy`` (bit-packed/index structures, refer.md/C-951) and
were excluded by M4.8b/M4.8d.  This tool characterizes them and tests whether
a raw packed POI copy-A pair appears in them, and samples u16 value density.

It does not decode the bit-packed grammar.  Finding no raw A pair and no
decodable 0..2047-class geographic field is a scoped negative for M4.8b's
local-scale avenue, not a proof that no sub-unit coordinate exists inside the
bit-packed encoding.

Usage::

    poi_bitpack_probe.py --selftest
    poi_bitpack_probe.py summary ROOT SHARD [SHARD ...]
    poi_bitpack_probe.py find-a ROOT SHARD AX AY
"""
from __future__ import annotations

import argparse
import collections
import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import cmpind  # noqa: E402
import poi_icons  # noqa: E402


def is_name_page(blob: bytes) -> bool:
    recs = list(poi_icons.iter_point_records(blob))
    return bool(recs and recs[0][0] in (0x60, 0x68))


def classify_pages(data: bytes):
    name, bit = [], []
    for off, blob in poi_icons.iter_streams(data):
        (name if is_name_page(blob) else bit).append((off, blob))
    return name, bit


def decode_shard(root: Path, shard: str) -> bytes:
    data, _ = cmpind.decode(root / "REFER001" / f"{shard}.DAT.cmp",
                            root / "REFER001" / f"{shard}.DAT.ind")
    return data


def header_words(blob: bytes, n: int = 12):
    return [struct.unpack_from(">H", blob, j)[0] if j + 1 < len(blob) else None
            for j in range(0, n * 2, 2)]


def sample_le2047(bit_pages, sample_bytes: int = 4096, max_values: int = 500000):
    le = n = 0
    for _, blob in bit_pages:
        for j in range(0, min(len(blob) - 1, sample_bytes), 2):
            v = struct.unpack_from(">H", blob, j)[0]
            n += 1
            if v <= 2047:
                le += 1
        if n >= max_values:
            break
    return le, n


def cmd_summary(args):
    for shard in args.shards:
        data = decode_shard(Path(args.root), shard)
        name, bit = classify_pages(data)
        print(f"{shard}: name={len(name)} bit={len(bit)}")
        for i, (_, b) in enumerate(bit[:3]):
            print(f"  head{i} len={len(b)} words={header_words(b)}")
        w0 = collections.Counter(struct.unpack_from(">H", b, 0)[0] for _, b in bit if len(b) >= 2)
        print(f"  w0 top {w0.most_common(3)}")
        le, n = sample_le2047(bit)
        pct = (le / n * 100) if n else 0.0
        print(f"  sample u16 <=2047 {le}/{n} = {pct:.1f}%")
    return 0


def cmd_find_a(args):
    data = decode_shard(Path(args.root), args.shard)
    _, bit = classify_pages(data)
    needle = struct.pack(">HH", args.ax, args.ay)
    hits = sum(1 for _, b in bit if needle in b)
    print(f"A={args.ax,args.ay} found in {hits} of {len(bit)} bit-packed pages ({args.shard})")
    return 0


def selftest() -> int:
    failures = []

    def check(name, cond, detail=""):
        print(f"  {name:<44} {'OK' if cond else 'FAIL'} {detail}".rstrip())
        if not cond:
            failures.append(name)

    # synthetic name-record blob
    name = bytearray(48)
    name[0], name[1] = 0x60, 24
    struct.pack_into(">HH", name, 2, 100, 200)
    check("is_name_page true", is_name_page(bytes(name)))
    bit = bytes.fromhex("0001002c00000235ffffffff")
    check("is_name_page false for 00-header", not is_name_page(bit))
    hw = header_words(bit, 4)
    check("header_words", hw == [1, 44, 0, 565])
    # sample_le2047
    blob = struct.pack(">HHHH", 10, 2047, 2048, 65535)
    le, n = sample_le2047([(0, blob)], sample_bytes=8)
    check("sample_le2047", le == 2 and n == 4)
    print(f"poi_bitpack_probe selftest: {'OK' if not failures else 'FAILED'}")
    return 1 if failures else 0


def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    sc = sub.add_parser("summary")
    sc.add_argument("root")
    sc.add_argument("shards", nargs="+")
    sc.set_defaults(func=cmd_summary)
    sf = sub.add_parser("find-a")
    sf.add_argument("root")
    sf.add_argument("shard")
    sf.add_argument("ax", type=int)
    sf.add_argument("ay", type=int)
    sf.set_defaults(func=cmd_find_a)
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
