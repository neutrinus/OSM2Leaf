#!/usr/bin/env python3
"""AUITK skin string pools: where the UI texts live (M1.49).

The 2011-2012 head unit keeps almost no user-visible text in the firmware:
``ce_strfind`` finds ``English (mile)``, ``Français``, ``Deutsch``... zero
times in ROM A of EU2011, US2011 and EU2014. The menus live in the player
skin ``\\SystemSD2\\SkinChange\\001\\substance.skn`` on the TFAT16 tail of the
card (``docs/format/skins.md``), inside the object tree's string pools.

A pool is a run of frames::

    [u32 byte_length][UTF-16LE text][NUL pad to a multiple of 4]

Every language is one block of frames that begins with the language-selector
labels (``English (mile)``, ``English (km)``, ``Français``, ``Deutsch`` ...).
The same list heads every block, so the block count is one less than the
number of labels (English has a mile and a km entry but one set of texts).

Subcommands (read-only, stdlib only):

  aui_strings.py languages FILE [--anchor S] [--show N]
      number of language blocks and the head of the first one
  aui_strings.py block FILE --n K [--anchor S]
      every frame of the K-th block (offset + text)
  aui_strings.py count FILE [--anchor S]
      blocks and the frame count of each

Exit codes: 0 ok, 1 nothing found, 2 usage/file error.
Evidence: docs/experiments/EXP-2026-11-23-M1.49-ui-strings.md, C-8090-C-8099.
"""

from __future__ import annotations

import argparse
import struct
import sys

MIN_LEN, MAX_LEN = 2, 0x1000
DEFAULT_ANCHOR = "English (mile)"


def read_frame(d, o):
    """(text, next_offset) or None when no frame starts at o."""
    if o + 4 > len(d):
        return None
    ln = struct.unpack_from("<I", d, o)[0]
    if ln < MIN_LEN or ln > MAX_LEN or ln & 1 or o + 4 + ln > len(d):
        return None
    try:
        text = d[o + 4:o + 4 + ln].decode("utf-16-le")
    except UnicodeDecodeError:
        return None
    if any(ord(c) < 0x20 and c not in "\n\t" for c in text):
        return None
    return text, ((o + 4 + ln + 2 + 3) & ~3)


def pool(d, o, maxn=200000):
    """Walk one frame run from o; return (texts, offsets, stop offset)."""
    texts, offs = [], []
    while len(texts) < maxn:
        f = read_frame(d, o)
        if not f:
            break
        texts.append(f[0])
        offs.append(o)
        o = f[1]
    return texts, offs, o


def anchor_blocks(d, anchor):
    """Offsets of every frame whose text is exactly ``anchor``."""
    want = anchor.encode("utf-16le")
    out, i = [], d.find(want)
    while i >= 0:
        f = read_frame(d, i - 4)
        if f and f[0] == anchor:
            out.append(i - 4)
        i = d.find(want, i + 1)
    return out


def selftest():
    ok = True

    def expect(name, cond):
        nonlocal ok
        print("%s %s" % ("PASS" if cond else "FAIL", name))
        ok &= bool(cond)

    def frame(s):
        b = s.encode("utf-16le")
        out = struct.pack("<I", len(b)) + b + b"\0\0"
        return out + b"\0" * ((4 - len(out) % 4) % 4)

    blob = b"\x00" * 12
    blob += frame("English (mile)") + frame("Deutsch") + frame("Español")
    blob += b"\x00" * 8 + frame("English (mile)") + frame("Français")
    texts, offs, _end = pool(blob, 12)
    expect("pool walk reads the first run", texts == ["English (mile)", "Deutsch", "Español"])
    expect("second frame offset is the first frame length", offs[1] == 12 + len(frame("English (mile)")))
    blocks = anchor_blocks(blob, "English (mile)")
    expect("two anchored blocks", len(blocks) == 2)
    expect("first anchored block starts at 12", blocks[0] == 12)
    expect("anchor is frame-exact", anchor_blocks(blob, "Engl") == [])
    expect("unframed bytes do not parse", read_frame(b"\x00" * 8, 0) is None)
    expect("odd length rejected", read_frame(struct.pack("<I", 3) + b"a\0b", 0) is None)
    print("selftest: %s" % ("OK" if ok else "FAILED"))
    return 0 if ok else 1


def load_skin(args):
    """Bytes of the skin: ``--card IMG`` extracts it by TFAT cluster chain,
    otherwise ``file`` is the already-extracted .skn."""
    if getattr(args, "card", None):
        import skn_info
        fat = skn_info.Fat16(args.card, args.tfat_offset)
        e = [x for x in skn_info.tfat_walk(fat)
             if x["path"].lower().endswith("substance.skn")][0]
        data = fat.read(e["clus"])[: e["size"]]
        fat.close()
        return data
    if not args.file:
        raise SystemExit("one of FILE or --card is required")
    return open(args.file, "rb").read()


def _blocks_or_fail(args):
    d = load_skin(args)
    blocks = anchor_blocks(d, args.anchor)
    if not blocks:
        print("no %r frame found" % args.anchor)
        return d, blocks
    return d, blocks


def cmd_languages(args):
    d, blocks = _blocks_or_fail(args)
    if not blocks:
        return 1
    texts, _offs, _end = pool(d, blocks[0])
    print("language_blocks %d  first_block 0x%08x  frames %d" %
          (len(blocks), blocks[0], len(texts)))
    print("head %s" % " | ".join(texts[:args.show]))
    return 0


def cmd_block(args):
    d, blocks = _blocks_or_fail(args)
    if not blocks:
        return 1
    if not 0 <= args.n < len(blocks):
        print("block index %d out of range (0..%d)" % (args.n, len(blocks) - 1))
        return 2
    texts, offs, _end = pool(d, blocks[args.n])
    for off, t in zip(offs, texts):
        print("0x%08x  %r" % (off, t))
    print("frames %d" % len(texts))
    return 0


def cmd_count(args):
    d, blocks = _blocks_or_fail(args)
    if not blocks:
        return 1
    print("%-10s language_blocks %3d  first_block 0x%08x" %
          (args.name, len(blocks), blocks[0]))
    hist = {}
    for st in blocks:
        texts, _offs, _end = pool(d, st)
        hist[len(texts)] = hist.get(len(texts), 0) + 1
        print("  0x%08x frames %3d  head %r" % (st, len(texts), texts[:4]))
    print("frames_hist %s" % ", ".join("%d×%d" % (n, hist[n]) for n in sorted(hist)))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    for name in ("languages", "block", "count"):
        sp = sub.add_parser(name)
        sp.add_argument("file", nargs="?", help="an extracted substance.skn")
        sp.add_argument("--card", help="a card image; extracts substance.skn by TFAT")
        sp.add_argument("--tfat-offset", type=lambda s: int(s, 0), default=0x1c8400400)
        sp.add_argument("--anchor", default=DEFAULT_ANCHOR)
        if name == "languages":
            sp.add_argument("--show", type=int, default=8)
        if name == "block":
            sp.add_argument("--n", type=int, default=0)
        if name == "count":
            sp.add_argument("--name", default="file")
    args = p.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "languages":
        return cmd_languages(args)
    if args.cmd == "block":
        return cmd_block(args)
    if args.cmd == "count":
        return cmd_count(args)
    p.print_usage()
    return 2


if __name__ == "__main__":
    sys.exit(main())
