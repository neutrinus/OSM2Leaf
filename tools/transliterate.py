#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Glyph-table-driven transliteration for OSM names (M5.80).

The table is a profile produced by M4.87, not a list hard-coded here: letters
present in the unit's font are kept verbatim; the other Polish letters are
mapped character by character.  Applied in the compiler name path when
``tilewriter.py --transliterate`` is used, and standalone to any IMF JSONL.

Commands:
  python3 tools/transliterate.py --selftest
  python3 tools/transliterate.py name 'Łódź Święta'
  python3 tools/transliterate.py jsonl IN.jsonl OUT.jsonl
"""
import argparse
import json
import sys
from pathlib import Path

DEFAULT_TABLE = Path(__file__).resolve().parent.parent / "profiles" / "pl-glyphs.json"


def load_table(path=None):
    p = Path(path) if path else DEFAULT_TABLE
    data = json.loads(p.read_text(encoding="utf-8"))
    present = set(data.get("present", []))
    mapping = dict(data.get("transliterate", {}))
    overlap = present & set(mapping)
    if overlap:
        raise ValueError("letters both present and transliterated: %s" % sorted(overlap))
    return present, mapping, data


def apply(text, present, mapping):
    """Return text with undrawable letters replaced; every other byte stays."""
    out = []
    for ch in text:
        if ch in present:
            out.append(ch)
        elif ch in mapping:
            out.append(mapping[ch])
        else:
            out.append(ch)
    return "".join(out)


def transliterate_jsonl(src, dst, table=None):
    present, mapping, _ = load_table(table)
    n = 0
    with Path(src).open(encoding="utf-8") as fin, Path(dst).open("w", encoding="utf-8") as fout:
        for line in fin:
            d = json.loads(line)
            changed = False
            for key in ("name", "addr:street"):
                if key in d and isinstance(d[key], str):
                    new = apply(d[key], present, mapping)
                    if new != d[key]:
                        d[key] = new
                        changed = True
            tags = d.get("tags")
            if isinstance(tags, dict):
                for key in ("name", "addr:street"):
                    if key in tags and isinstance(tags[key], str):
                        new = apply(tags[key], present, mapping)
                        if new != tags[key]:
                            tags[key] = new
                            changed = True
            n += int(changed)
            fout.write(json.dumps(d, ensure_ascii=False) + "\n")
    return n


def tile_scan(path, text):
    """Count inflated tile streams containing a UTF-8 name (round-trip check)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent / "ze0-viewer" / "tools_ze0"))
    import zlib
    import clarion_tile
    tile = clarion_tile.read_tile(Path(path).read_bytes())
    needle = text.encode("utf-8")
    hits = 0
    for section in tile["sections"]:
        for level in section["levels"]:
            for directory in level["dirs"]:
                for slot in directory["slots"].values():
                    for rec in slot["recs"]:
                        try:
                            plain = zlib.decompressobj().decompress(rec["raw"])
                        except zlib.error:
                            continue
                        if needle in plain:
                            hits += 1
    return hits


def selftest():
    present, mapping, data = load_table()
    assert len(present) == 8 and len(mapping) == 10, (len(present), len(mapping))
    # ó is drawable in the EU2011 font (M4.87), so it is kept: the task's
    # illustrative "Łódź -> Lodz" is overridden by the glyph table.
    assert apply("Łódź Święta", present, mapping) == "Lódz Swięta"
    assert apply("Ą ć Ę ó", present, mapping) == "Ą ć Ę ó"
    assert apply("Lodz", present, mapping) == "Lodz"
    assert apply("1=Żółć@Łódź", present, mapping) == "1=Zólć@Lódz"
    print("transliterate selftest: 8 kept, 10 mapped, ASCII/prefix unchanged")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--table")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("name")
    p.add_argument("text")
    p = sub.add_parser("jsonl")
    p.add_argument("src")
    p.add_argument("dst")
    p = sub.add_parser("tile")
    p.add_argument("tile")
    p.add_argument("--text", required=True)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "name":
        present, mapping, _ = load_table(a.table)
        print(apply(a.text, present, mapping))
        return 0
    if a.cmd == "jsonl":
        print("transliterated %d record(s)" % transliterate_jsonl(a.src, a.dst, a.table))
        return 0
    if a.cmd == "tile":
        print("hits=%d" % tile_scan(a.tile, a.text))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
