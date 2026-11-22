#!/usr/bin/env python3
"""Rename a POINT record with ISO-8859-2 bytes and read the name back at L3.

M4.13 (EXP-2026-11-05) stores Polish names as ISO-8859-2 single bytes and says
to reject characters outside that set.  ``mutate_refer_poi.py`` is the byte-level
POINT writer, but its CLI decodes ``--old``/``--new`` as Latin-1.  This helper
maps every wanted Latin-2 byte to the Latin-1 code point of the same *value*
before calling that tool, so the pair contains exactly the M4.13 bytes while no
tool owned by another task is edited.

``compare`` runs the firmware's own name accessor (M3.11c, through
``point_name_accessor.decode_page``) on the edited page and prints the stored
name and the returned name as hex, so a change of a single non-ASCII byte is
visible.  It is a check, not a decoder: both the expected bytes and the page
fragments are supplied by the caller.

Usage::

  rename_poi_latin2.py --selftest
  rename_poi_latin2.py CMP IND OUTDIR --page 0x6e06d0 \
      --rename OLD=NEW [--rename OLD=NEW ...]
  rename_poi_latin2.py compare IMG CMP IND --page 0x6e06d0 --record 0 \
      --expect-hex a3f364bc20af616269656e6965632e

Method and results: docs/experiments/EXP-2026-11-22-M9.70-polish-poi-l3.md
"""

from __future__ import annotations

import argparse
import os
import sys
import zlib
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "l3_harness")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import mutate_refer_poi as mrp  # noqa: E402
import point_name_accessor as pna  # noqa: E402
import point_walk_l3 as pw  # noqa: E402

# EU2011 POINT010 name page (M3.11c, EXP-2026-11-19).  Also the defaults of
# point_name_accessor.cmd_run for this build; overridable on the CLI.
EU_PAGE = 0x6E06D0
EU_PAGE_LEN = 97158
EU_BUILD = "eu2011"


def latin2_bytes(text: str) -> bytes:
    """The M4.13 bytes of *text*; a character outside Latin-2 is rejected."""
    return text.encode("iso-8859-2")


def as_cli(text: str) -> str:
    """Latin-1 mojibake whose Latin-1 encoding is exactly ``latin2_bytes``.

    ``mutate_refer_poi.main`` calls ``args.old.encode('latin-1')``; encoding the
    wanted bytes to Latin-2 and decoding them as Latin-1 gives a string that
    survives that call unchanged at the byte level.
    """
    return latin2_bytes(text).decode("latin-1")


def parse_rename(spec: str) -> tuple[str, str]:
    """``OLD=NEW`` -> (OLD, NEW); only the first '=' separates."""
    old, sep, new = spec.partition("=")
    if not sep or not old or not new:
        raise ValueError(f"--rename needs OLD=NEW, got {spec!r}")
    return old, new


def cmd_edit(args) -> int:
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    cur_cmp, cur_ind = Path(args.cmp), Path(args.ind)
    for spec in args.rename:
        old, new = parse_rename(spec)
        print(f"rename {old!r} -> {new!r}: "
              f"{latin2_bytes(old).hex()} -> {latin2_bytes(new).hex()}")
        rc = mrp.main([
            str(cur_cmp), str(cur_ind), str(outdir),
            "--page", hex(args.page), "--old", as_cli(old), "--new", as_cli(new),
            "--resize",
        ])
        if rc:
            return rc
        cur_cmp, cur_ind = outdir / Path(args.cmp).name, outdir / Path(args.ind).name
    return 0


def cmd_compare(args) -> int:
    data = pw.load_image(args.image)
    _u, _c, _n, _ch, offsets = mrp.read_ind(Path(args.ind))
    blob = mrp.decode(Path(args.cmp).read_bytes(), offsets)
    end = args.page + (args.page_len or len(blob) - args.page)
    raw = zlib.decompressobj().decompress(blob[args.page:end])
    records = mrp.parse_page(raw)
    out = pna.decode_page(data, EU_BUILD, blob, raw)
    if "blocked" in out:
        print(f"BLOCKED: {out['blocked']}")
        return 4
    rows = out["rows"]
    want = bytes.fromhex(args.expect_hex)
    nonascii = lambda b: bytes(x for x in b if x >= 0x80)
    ok = True
    for idx in args.record:
        if idx < 0 or idx >= len(rows):
            print(f"record {idx}: out of range (0..{len(rows) - 1})")
            return 2
        row = rows[idx]
        stored = pna.display_text(records[idx]["bytes"]).rstrip(b"\x00")
        # The accessor's name word count includes the NUL that separates the
        # name from field 6; strip only at the very end, never per field.
        got_name = row.get("name", b"").rstrip(b"\x00")
        got = (row.get("name", b"") + row.get("addr", b"")).rstrip(b"\x00")
        print(f"record {idx}: offset={row['offset']:#06x} verdict={row['verdict']} "
              f"name_words={row['len']} ptr={row.get('ptr')!r}")
        print(f"  stored   hex={stored.hex()}")
        print(f"  returned hex={got.hex()}")
        print(f"  name     hex={got_name.hex()}")
        print(f"  stored   nonascii={nonascii(stored).hex()}")
        print(f"  returned nonascii={nonascii(got).hex()}")
        print(f"  expected hex={want.hex()}")
        good = (row["verdict"] == "ok" and got == stored and got_name == want
                and nonascii(got) == nonascii(want) == nonascii(stored))
        ok &= good
        print(f"  record {idx}: {'OK' if good else 'MISMATCH'}")
    print(f"accessor slots={out['slots']!r} slots_ok={out['slots_ok']} "
          f"negative={out['negative']!r}")
    ok &= out["slots_ok"] and out["negative"]["ok"]
    verdict = "PASS" if ok else "FAIL"
    print(f"result: {verdict}")
    return 0 if ok else 1


def selftest() -> int:
    fails = 0

    def check(name, cond):
        nonlocal fails
        print("%-62s %s" % (name, "ok" if cond else "FAIL"))
        fails += not cond

    # The five Polish letters used by this task (M4.13 is ISO-8859-2).
    letters = {"ł": 0xB3, "Ł": 0xA3, "ó": 0xF3, "ź": 0xBC, "Ż": 0xAF}
    for ch, byte in letters.items():
        check(f"{ch} encodes to {byte:#04x} in ISO-8859-2", latin2_bytes(ch) == bytes([byte]))
        check(f"{ch} survives the Latin-1 CLI transport",
              as_cli(ch).encode("latin-1") == bytes([byte]))
    name = "Łódź Żabieniec."
    check("full name keeps every non-ASCII byte through the transport",
          as_cli(name).encode("latin-1") == latin2_bytes(name)
          == bytes.fromhex("a3f364bc20af616269656e6965632e"))
    check("the lowercase-ł name keeps every non-ASCII byte",
          as_cli("łódź Żabieniec.").encode("latin-1")
          == bytes.fromhex("b3f364bc20af616269656e6965632e"))
    try:
        latin2_bytes("€")
        check("negative: a character outside Latin-2 is rejected", False)
    except UnicodeEncodeError:
        check("negative: a character outside Latin-2 is rejected", True)
    check("parse_rename splits on the first '=' only",
          parse_rename("OLD=A=B") == ("OLD", "A=B"))
    for bad in ("OLD", "=NEW", "OLD="):
        try:
            parse_rename(bad)
            check(f"negative: {bad!r} is rejected", False)
        except ValueError:
            check(f"negative: {bad!r} is rejected", True)
    print("selftest:", "PASS" if not fails else f"FAIL ({fails})")
    return 0 if not fails else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    e = sub.add_parser("edit", aliases=[])
    e.add_argument("cmp")
    e.add_argument("ind")
    e.add_argument("outdir")
    e.add_argument("--page", type=lambda s: int(s, 0), default=EU_PAGE)
    e.add_argument("--rename", action="append", required=True, metavar="OLD=NEW")

    c = sub.add_parser("compare")
    c.add_argument("image")
    c.add_argument("cmp")
    c.add_argument("ind")
    c.add_argument("--page", type=lambda s: int(s, 0), default=EU_PAGE)
    c.add_argument("--page-len", type=lambda s: int(s, 0), default=EU_PAGE_LEN)
    c.add_argument("--record", type=int, action="append", required=True)
    c.add_argument("--expect-hex", required=True)
    return ap


def main(argv=None) -> int:
    ap = build_parser()
    # The edit form has no subcommand word (CMP IND OUTDIR ...), so it must be
    # recognised before argparse tries to read CMP as a subcommand name.
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return selftest()
    if argv and argv[0] == "compare":
        args = ap.parse_args(argv)
    elif argv:
        args = ap.parse_args(["edit"] + argv)
    else:
        ap.print_help()
        return 2
    if args.cmd == "edit":
        return cmd_edit(args)
    if args.cmd == "compare":
        return cmd_compare(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
