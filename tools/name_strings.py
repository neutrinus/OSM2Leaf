#!/usr/bin/env python3
"""Name-database string statistics for LCTBL001.DAT (M4.13).

Finds the zlib streams in LCTBL001.DAT, decompresses each clean stream, splits it
into NUL-terminated strings and reports:
  - string count, unique count, length distribution (bytes), longest string
  - characters outside the Latin-2 (ISO-8859-2) alphabet (decode errors)
  - counts of Polish-only letters (ą ę ł ń ś ź ż and their capitals) and of ó
  - per stream: string count, Polish-letter count, and whether the strings are
    in ascending byte order (collation check, byte order only)

Encoding: the doc says Latin-2. The stats are per byte, so a wrong guess shows
up as decode errors rather than silent loss.

Usage:
  name_strings.py FILE [--per-stream]    stats on a real LCTBL001.DAT
  name_strings.py --selftest             synthetic checks, no vendor data
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
import zlib
from pathlib import Path

POLISH_ONLY = "ąęłńśźżĄĘŁŃŚŹŻ"
POLISH_ALSO = "óÓ"


def clean_streams(blob: bytes):
    """Yield (offset, plain bytes) for each zlib stream that ends cleanly."""
    pos = 0
    for m in re.finditer(rb"\x78[\x01\x5e\x9c\xda]", blob):
        h = m.start()
        if h < pos:
            continue
        o = zlib.decompressobj()
        try:
            out = o.decompress(blob[h:h + 2_000_000])
        except zlib.error:
            continue
        if not o.eof:
            continue
        pos = h + (min(len(blob) - h, 2_000_000) - len(o.unused_data))
        yield h, out


def strings_of(plain: bytes) -> list[bytes]:
    """All non-empty NUL-separated pieces (includes binary fragments)."""
    parts = plain.split(b"\x00")
    return [p for p in parts if p]


def is_text(p: bytes) -> bool:
    """Printable Latin-2 text with at least two bytes and one letter."""
    if len(p) < 2 or any(b < 0x20 or b == 0x7F for b in p):
        return False
    return any(chr(b).isalpha() for b in p if b < 0x80) or any(b >= 0xA0 for b in p)


def stats(streams) -> dict:
    allstr: list[bytes] = []
    pieces = 0
    per = []
    for off, plain in streams:
        raw = strings_of(plain)
        pieces += len(raw)
        ss = [p for p in raw if is_text(p)]
        allstr.extend(ss)
        text = [s.decode("iso-8859-2", "replace") for s in ss]
        pl = sum(1 for t in text for ch in t if ch in POLISH_ONLY)
        ordered = all(ss[i] <= ss[i + 1] for i in range(len(ss) - 1))
        per.append({"offset": off, "strings": len(ss), "polish": pl, "ordered": ordered})
    lens = collections.Counter(len(s) for s in allstr)
    bad = sum(1 for s in allstr if "�" in s.decode("iso-8859-2", "replace"))
    text = [s.decode("iso-8859-2", "replace") for s in allstr]
    return {
        "streams": len(per),
        "pieces": pieces,
        "strings": len(allstr),
        "unique": len(set(allstr)),
        "max_bytes": max(lens) if lens else 0,
        "len_hist_top": lens.most_common(5),
        "decode_errors": bad,
        "polish_only": sum(1 for t in text for ch in t if ch in POLISH_ONLY),
        "polish_also_o": sum(1 for t in text for ch in t if ch in POLISH_ALSO),
        "per_stream": per,
    }


def _selftest() -> int:
    fails = []

    def check(name, cond):
        if not cond:
            fails.append(name)

    raw = [b"Praha\x00", b"ul. \xb1\xea\xb3\x00", b"Pozna\xf1\x00", b"A\x00"]
    plain = b"".join(raw)
    blob = b"junk" + zlib.compress(plain) + b"more" + zlib.compress(b"Zamo\xe6\x00")
    streams = list(clean_streams(blob))
    check("two streams found", len(streams) == 2)
    s = stats(streams)
    check("string count", s["strings"] == 4)  # "Praha", "ul. ąęł", "Poznań", "A" (not text: 1 byte)
    check("polish-only counted", s["polish_only"] == 4)  # ą ę ł ń; ć (0xE6) is not in the set
    check("decode errors zero", s["decode_errors"] == 0)
    check("longest bytes", s["max_bytes"] == 7)  # "ul. ąęł" = 4 + 3 bytes
    print(f"selftest: {'OK' if not fails else 'FAIL ' + ', '.join(fails)}")
    return 0 if not fails else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("--per-stream", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if not a.file:
        ap.error("FILE is required")
    blob = Path(a.file).read_bytes()
    s = stats(clean_streams(blob))
    print(f"streams={s['streams']} pieces={s['pieces']} text_strings={s['strings']} unique={s['unique']}")
    print(f"max_bytes={s['max_bytes']} top_lengths={s['len_hist_top']}")
    print(f"decode_errors={s['decode_errors']} polish_only={s['polish_only']} o_with_acute={s['polish_also_o']}")
    if a.per_stream:
        for r in s["per_stream"]:
            print(f"  {r['offset']:#010x} strings={r['strings']} polish={r['polish']} ordered={r['ordered']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
