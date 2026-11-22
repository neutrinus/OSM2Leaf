#!/usr/bin/env python3
"""FDL bitmap-font code-point map reader (M4.87).

The map name font of build A is an FDL font blob in RASTERIZER_DLL.dll:
``dig_pfont_ucs_iso88591_hei_wx``.  The blob starts with the ASCII magic
``FDL Font``; at offset 0xd4 it holds a sorted array of little-endian
``u16 glyph, u16 codepoint`` pairs.  A code point with no glyph is absent
from the map (or present only through the repeated notdef fill value at the
end of the table).

This tool answers one question: for a list of Unicode code points, which
glyphs does the font actually map?  It never guesses an address: the font VA
is turned into a file offset with ``tools/cerom.py`` (the CE ROM headers).

Usage:
  fdl_font.py IMG --font-va 0x3431020 --image-start 0x200200
  fdl_font.py IMG --font-va 0x3431020 --codes U+0104,U+0105
  fdl_font.py --selftest

Stdlib only.  Method: docs/experiments/EXP-2026-11-22-M4.87-polish-glyphs.md
"""

import argparse
import os
import struct
import sys

MAGIC = b"FDL Font"
CMAP_OFF = 0xD4
MAX_CP = 0x1000
FILL_RUN = 16
# A glyph id that occurs this many times for one code point is a notdef fill,
# not a distinct drawable glyph (the table stores one entry per font variant).
FILL_THRESHOLD = 8

POLISH = {
    "Ą": 0x0104, "ą": 0x0105, "Ć": 0x0106, "ć": 0x0107,
    "Ę": 0x0118, "ę": 0x0119, "Ł": 0x0141, "ł": 0x0142,
    "Ń": 0x0143, "ń": 0x0144, "Ó": 0x00D3, "ó": 0x00F3,
    "Ś": 0x015A, "ś": 0x015B, "Ź": 0x0179, "ź": 0x017A,
    "Ż": 0x017B, "ż": 0x017C,
}


def parse_cmap(data, off, limit=None):
    """Return (pairs, start_off, end_off, fallback_glyph).

    ``pairs`` is a dict cp -> list of glyph ids.  The run is bounded by a
    non-increasing code point or by ``limit`` bytes (a safety cap).
    """
    if data[off:off + len(MAGIC)] != MAGIC:
        raise ValueError("no %r magic at offset 0x%x" % (MAGIC, off))
    start = off + CMAP_OFF
    end = len(data) if limit is None else min(len(data), start + limit)
    pairs = []
    last = 0
    p = start
    while p + 4 <= end:
        g, cp = struct.unpack_from("<HH", data, p)
        if cp == 0 or cp > MAX_CP or cp < last:
            break
        pairs.append((p, g, cp))
        last = cp
        p += 4
    if not pairs:
        raise ValueError("no cmap pairs at offset 0x%x" % start)
    # notdef: the most common glyph in the final FILL_RUN pairs
    tail = [g for _, g, _ in pairs[-FILL_RUN:]]
    fallback = max(set(tail), key=tail.count) if tail else 0
    return pairs, start, pairs[-1][0] + 4, fallback


def build_map(pairs, fallback):
    """cp -> list of real glyph ids (notdef fill removed).

    For each code point the table holds one entry per font variant.  A missing
    variant is filled with the same glyph id many times; those repeated ids
    are notdef, not drawable glyphs.  ``fallback`` is the global fill value
    taken from the tail of the table; additionally, any id repeated
    ``FILL_THRESHOLD`` times for one code point is treated as that code
    point's notdef fill.
    """
    from collections import Counter
    out = {}
    for _, g, cp in pairs:
        out.setdefault(cp, []).append(g)
    result = {}
    for cp, gs in out.items():
        counts = Counter(gs)
        real = []
        for g in dict.fromkeys(gs):  # dedupe, keep first-seen order
            if g == fallback:
                continue
            if counts[g] >= FILL_THRESHOLD:
                continue
            real.append(g)
        result[cp] = real
    return result


def parse_codes(text):
    codes = []
    for tok in text.split(","):
        tok = tok.strip()
        if not tok:
            continue
        if tok.upper().startswith("U+"):
            tok = tok[2:]
        codes.append(int(tok, 16))
    return codes


def run_probe(args):
    with open(args.image, "rb") as f:
        data = f.read()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import cerom
    rom = cerom.CERom(data, args.image_start)
    off = rom.va2file(args.font_va)
    pairs, cmap_start, cmap_end, fallback = parse_cmap(data, off, args.max_bytes)
    cmap = build_map(pairs, fallback)
    print("font_va      0x%08x  file 0x%x" % (args.font_va, off))
    print("magic        %r" % MAGIC.decode())
    print("cmap         VA 0x%08x..0x%08x  pairs=%d" %
          (args.font_va + CMAP_OFF, args.font_va + CMAP_OFF + (cmap_end - cmap_start),
           len(pairs)))
    print("codepoints   U+%04X..U+%04X  distinct=%d" %
          (min(cmap), max(cmap), len(cmap)))
    print("notdef glyph 0x%04x (fallback fill)" % fallback)
    if args.codes:
        codes = parse_codes(args.codes)
    else:
        codes = list(POLISH.values())
    print("letter  codepoint  glyphs               present")
    for cp in codes:
        gs = cmap.get(cp, [])
        label = next((k for k, v in POLISH.items() if v == cp), "")
        shown = " ".join("0x%04x" % g for g in gs[:8])
        if len(gs) > 8:
            shown += " (+%d)" % (len(gs) - 8)
        print("  %s    U+%04X     %-20s %s" %
              (label or " ", cp, shown or "-", "YES" if gs else "NO"))
    return 0


def selftest():
    # Synthetic FDL blob: magic + padding + known sorted cmap + notdef fill.
    blob = bytearray(MAGIC + b"\x00" * (CMAP_OFF - len(MAGIC)))
    table = [(0x0100, 0x41), (0x0200, 0x42), (0x0300, 0x0104),
             (0x0400, 0x0105), (0x0500, 0x0106), (0x0600, 0x0118)]
    for g, cp in table:
        blob += struct.pack("<HH", g, cp)
    for _ in range(FILL_RUN + 2):
        blob += struct.pack("<HH", 0x1F00, 0x0118)
    blob = bytes(blob)
    pairs, s, e, fb = parse_cmap(blob, 0)
    assert s == CMAP_OFF and len(pairs) == len(table) + FILL_RUN + 2, (s, len(pairs))
    assert fb == 0x1F00, hex(fb)
    cmap = build_map(pairs, fb)
    assert cmap[0x41] == [0x0100] and cmap[0x0104] == [0x0300], cmap
    assert cmap[0x0105] == [0x0400] and cmap[0x0118] == [0x0600], cmap
    assert 0x42 == 0x42 and cmap.get(0x0141, []) == [], "absent cp must be empty"
    assert cmap.get(0x0119, []) == [], "cp just past table must be absent"
    try:
        parse_cmap(b"NOTFDL!!" + bytes(CMAP_OFF), 0)
    except ValueError:
        pass
    else:
        raise AssertionError("bad magic must be rejected")
    assert parse_codes("U+0104, 0x105") == [0x0104, 0x0105]
    print("fdl_font selftest: OK")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", nargs="?", help="raw firmware image")
    ap.add_argument("--font-va", type=lambda x: int(x, 0), default=0x3431020)
    ap.add_argument("--image-start", type=lambda x: int(x, 0), default=0x200200)
    ap.add_argument("--codes", help="comma-separated code points, e.g. U+0104,0x105")
    ap.add_argument("--max-bytes", type=int, default=0x30000,
                    help="safety cap for cmap scan (default 0x30000)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.image:
        ap.error("IMAGE is required unless --selftest")
    return run_probe(args)


if __name__ == "__main__":
    sys.exit(main())
