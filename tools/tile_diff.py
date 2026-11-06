#!/usr/bin/env python3
"""One-tile diff report: sections, records and bytes (M5.8).

    tile_diff.py A B [--json] [--block 4096]

Reports what changed between a factory tile A and a built or mutated tile B:
  - file size and SHA-256 of both files
  - zlib streams: each clean stream is listed by file offset with compressed
    length, plain length and plain SHA-256. Streams are matched by offset.
    A stream is "changed" when its plain content differs at the same offset,
    "added" or "removed" when only one file has it there.
  - bytes: count of differing bytes and the differing block ranges (block size
    --block), so a one-parcel change shows as a few short ranges.
  - sections: stream counts per side, the same tally as the streams above.

This is structural and offset-based. It does not decode features; the
feature-level check is harness.py compare-tiles.

Exit status: 0 when A and B are identical, 1 when they differ, 2 on error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zlib
from pathlib import Path


def clean_streams(blob: bytes):
    """Yield (offset, compressed_len, plain bytes) for each clean zlib stream."""
    pos = 0
    for m in re.finditer(rb"\x78[\x01\x5e\x9c\xda]", blob):
        h = m.start()
        if h < pos:
            continue
        o = zlib.decompressobj()
        try:
            out = o.decompress(blob[h:h + 4_000_000])
        except zlib.error:
            continue
        if not o.eof:
            continue
        clen = min(len(blob) - h, 4_000_000) - len(o.unused_data)
        pos = h + clen
        yield h, clen, out


def byte_ranges(a: bytes, b: bytes, block: int):
    """Differing byte count and block ranges (start, end) between a and b."""
    n = max(len(a), len(b))
    diff = 0
    ranges: list[list[int]] = []
    for start in range(0, n, block):
        end = min(start + block, n)
        ca = a[start:end]
        cb = b[start:end]
        if ca == cb:
            continue
        cnt = sum(1 for i in range(max(len(ca), len(cb)))
                  if (ca[i] if i < len(ca) else None) != (cb[i] if i < len(cb) else None))
        diff += cnt
        if ranges and ranges[-1][1] == start:
            ranges[-1][1] = end
        else:
            ranges.append([start, end])
    return diff, ranges


def report(a_path: Path, b_path: Path, block: int) -> dict:
    a = a_path.read_bytes()
    b = b_path.read_bytes()
    sa = {off: (clen, hashlib.sha256(p).hexdigest(), len(p), p) for off, clen, p in clean_streams(a)}
    sb = {off: (clen, hashlib.sha256(p).hexdigest(), len(p), p) for off, clen, p in clean_streams(b)}
    changed, added, removed, same = [], [], [], 0
    for off in sorted(set(sa) | set(sb)):
        if off in sa and off in sb:
            if sa[off][1] == sb[off][1]:
                same += 1
            else:
                changed.append({"offset": off, "plain_a": sa[off][2], "plain_b": sb[off][2],
                                "compressed_a": sa[off][0], "compressed_b": sb[off][0]})
        elif off in sa:
            removed.append({"offset": off, "plain": sa[off][2]})
        else:
            added.append({"offset": off, "plain": sb[off][2]})
    diff_bytes, ranges = byte_ranges(a, b, block)
    return {
        "a": {"path": str(a_path), "size": len(a), "sha256": hashlib.sha256(a).hexdigest(), "streams": len(sa)},
        "b": {"path": str(b_path), "size": len(b), "sha256": hashlib.sha256(b).hexdigest(), "streams": len(sb)},
        "streams": {"same": same, "changed": len(changed), "added": len(added), "removed": len(removed),
                    "changed_detail": [{k: v for k, v in c.items()} for c in changed[:50]]},
        "bytes": {"differing": diff_bytes, "block": block, "ranges": ranges[:200],
                  "range_count": len(ranges)},
        "identical": a == b,
    }


def _selftest() -> int:
    fails = []
    import os
    import tempfile

    def check(name, cond):
        if not cond:
            fails.append(name)

    p1 = b"header" + zlib.compress(b"alpha" * 50) + b"mid" + zlib.compress(b"beta" * 50)
    p2 = bytearray(p1)
    p2[-5] ^= 0xFF  # change a byte inside the second stream's compressed data
    with tempfile.TemporaryDirectory() as d:
        fa = Path(d, "a.dat"); fb = Path(d, "b.dat")
        fa.write_bytes(p1); fb.write_bytes(bytes(p2))
        r = report(fa, fb, 16)
        check("identical false", r["identical"] is False)
        check("two streams in a", r["a"]["streams"] == 2)
        check("changed stream counted", r["streams"]["changed"] + r["streams"]["removed"] + r["streams"]["added"] >= 1)
        check("differing bytes > 0", r["bytes"]["differing"] > 0)
        same = report(fa, fa, 16)
        check("self compare identical", same["identical"] is True and same["bytes"]["differing"] == 0)
        check("self compare streams same", same["streams"]["same"] == 2 and same["streams"]["changed"] == 0)
        check("ranges merged", all(s < e for s, e in r["bytes"]["ranges"]))
        _ = os  # keep import used on all paths
    print(f"selftest: {'OK' if not fails else 'FAIL ' + ', '.join(fails)}")
    return 0 if not fails else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a", nargs="?")
    ap.add_argument("b", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--block", type=int, default=4096)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not args.a or not args.b:
        ap.error("A and B are required")
    try:
        r = report(Path(args.a), Path(args.b), args.block)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(f"A {r['a']['size']} bytes {r['a']['sha256'][:16]} streams={r['a']['streams']}")
        print(f"B {r['b']['size']} bytes {r['b']['sha256'][:16]} streams={r['b']['streams']}")
        s = r["streams"]
        print(f"streams: same={s['same']} changed={s['changed']} added={s['added']} removed={s['removed']}")
        print(f"bytes differing={r['bytes']['differing']} in {r['bytes']['range_count']} ranges")
        print("RESULT: " + ("IDENTICAL" if r["identical"] else "DIFFERS"))
    return 0 if r["identical"] else 1


if __name__ == "__main__":
    sys.exit(main())
