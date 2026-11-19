#!/usr/bin/env python3
"""Read the key tree of a decoded Windows CE ROM registry hive (``*.hv``).

M1.21 decoded the ROM ``FILESentry`` payloads ``boot.hv``, ``default.hv`` and
``user.hv`` with the kernel routine (``nk_decomp.py files``).  The decoded
hives start with ``00 04 00 00 .. .. .. .. 'EKIM'`` and are not NT ``regf``.
This tool reads only what M1.21 needed: key paths and value name/type/data.

Cell layout (derived from the decoded EU2011 hives, M1.21 EXP; not from a
published spec):

* every cell starts ``u32 size | kind``, ``u32 0``, ``u32 id``; ``kind`` is
  ``0xc0000000`` for a key, ``0xd0000000`` for a value; links to other cells
  are ``0x20000000 | id`` (0 = none);
* key:   ``+12 next-sibling``, ``+16 first-child``, ``+20 first-value``,
  ``+24 u32 name length`` (UTF-16 code units), ``+28 name``;
* value: ``+12 next-value``, ``+16 u16 type``, ``+18 u16 data length``
  (bytes), ``+20 u16 name length``, ``+22 name`` then the data.

Cells are found by scanning 4-byte aligned offsets for that header and a
name that fits; the parse is then checked: every link must resolve to a cell
of the right kind (``dangling`` counts the misses), and every key must be
reached from a root (a key that is nobody's child or sibling).

Usage:
  cehive.py --selftest
  cehive.py HIVE [--grep REGEX] [--keys] [--json OUT]

Paths are printed relative to the hive root (``boot.hv``/``default.hv`` are
HKLM-rooted, ``user.hv`` HKCU-rooted in CE).  Stdlib only; the tool reads a
file the caller names and writes no vendor bytes to the repo.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path

KEY, VAL = 0xC, 0xD
LINK = 0x20000000
REG_TYPES = {0: "NONE", 1: "SZ", 2: "EXPAND_SZ", 3: "BINARY", 4: "DWORD",
             7: "MULTI_SZ"}


def _utf16(b: bytes) -> str:
    return b.decode("utf-16-le", "replace")


def scan_cells(d: bytes):
    """(keys, values): ``{id: dict}`` for every well-formed cell."""
    keys, vals = {}, {}
    for o in range(0, len(d) - 28, 4):
        w, z, cid = struct.unpack_from("<III", d, o)
        kind = w >> 28
        if z or kind not in (KEY, VAL) or (w & 0x0FFF0000) or not cid or cid >= LINK:
            continue
        if kind == KEY:
            sib, child, val, nlen = struct.unpack_from("<IIII", d, o + 12)
            end = o + 28 + 2 * nlen
            if not 0 < nlen < 256 or end > len(d):
                continue
            if any(x and (x & 0xF0000000) != LINK for x in (sib, child, val)):
                continue
            keys[cid] = dict(off=o, sib=sib & 0xFFFFFFF, child=child & 0xFFFFFFF,
                             val=val & 0xFFFFFFF, name=_utf16(d[o + 28:end]))
        else:
            nxt, typ, dlen, nlen = struct.unpack_from("<IHHH", d, o + 12)
            end = o + 22 + 2 * nlen + dlen
            if nlen >= 256 or end > len(d) or (nxt and (nxt & 0xF0000000) != LINK):
                continue
            name = _utf16(d[o + 22:o + 22 + 2 * nlen])
            data = d[o + 22 + 2 * nlen:end]
            vals[cid] = dict(off=o, next=nxt & 0xFFFFFFF, type=typ, name=name,
                             data=data)
    return keys, vals


def value_text(v) -> str:
    t, data = v["type"], v["data"]
    if t in (1, 2):
        return _utf16(data).rstrip("\0")
    if t == 7:
        return "|".join(x for x in _utf16(data).split("\0") if x)
    if t == 4 and len(data) == 4:
        return "0x%08x" % struct.unpack("<I", data)[0]
    return data[:16].hex() + ("..+%d" % (len(data) - 16) if len(data) > 16 else "")


def tree(d: bytes):
    """Parse a hive: rows of (path, value-name|None, type, text) and stats."""
    keys, vals = scan_cells(d)
    dangling = 0
    referenced = set()
    for k in keys.values():
        for ref, pool in ((k["sib"], keys), (k["child"], keys), (k["val"], vals)):
            if ref and ref not in pool:
                dangling += 1
        referenced.update(x for x in (k["sib"], k["child"]) if x)
    for v in vals.values():
        if v["next"] and v["next"] not in vals:
            dangling += 1
    roots = sorted(cid for cid in keys if cid not in referenced)
    rows, seen = [], set()

    def walk(cid, prefix):
        while cid and cid in keys and cid not in seen:
            seen.add(cid)
            k = keys[cid]
            path = prefix + "\\" + k["name"] if prefix else k["name"]
            rows.append((path, None, None, None))
            vid, vseen = k["val"], set()
            while vid and vid in vals and vid not in vseen:
                vseen.add(vid)
                v = vals[vid]
                rows.append((path, v["name"], REG_TYPES.get(v["type"], str(v["type"])),
                             value_text(v)))
                vid = v["next"]
            walk(k["child"], path)
            cid = k["sib"]

    for r in roots:
        walk(r, "")
    stats = dict(keys=len(keys), values=len(vals), roots=len(roots),
                 reached=len(seen), dangling=dangling,
                 values_reached=sum(1 for r in rows if r[1] is not None))
    return rows, stats


# ---------------------------------------------------------------- selftest

def _key(cid, name, sib=0, child=0, val=0):
    n = name.encode("utf-16-le")
    body = struct.pack("<IIII", *(LINK | x if x else 0 for x in (sib, child, val)), len(name)) + n
    return struct.pack("<III", 0xC0000000 | (len(body) + 4), 0, cid) + body


def _val(cid, name, typ, data, nxt=0):
    n = name.encode("utf-16-le")
    body = struct.pack("<IHHH", LINK | nxt if nxt else 0, typ, len(data), len(name)) + n + data
    return struct.pack("<III", 0xD0000000 | (len(body) + 4), 0, cid) + body


def _pad4(b: bytes) -> bytes:
    return b + b"\0" * (-len(b) % 4)


def selftest() -> int:
    fails = []

    def check(name, cond):
        print("%s %s" % ("ok  " if cond else "FAIL", name))
        if not cond:
            fails.append(name)

    sz = "SystemSD\0".encode("utf-16-le")
    cells = [
        _key(1, "Drivers", child=2),
        _key(2, "SDHC", sib=3, val=10),
        _key(3, "Profiles", child=4),
        _key(4, "SDProfile", val=11),
        _val(10, "Dll", 1, "SDHC.dll\0".encode("utf-16-le"), nxt=12),
        _val(12, "Order", 4, struct.pack("<I", 20)),
        _val(11, "Folder", 1, sz),
        _key(5, "Init", val=13),
        _val(13, "Launch50", 1, "Navi.exe\0".encode("utf-16-le")),
    ]
    blob = b"\x00\x04\x00\x00" + b"\0" * 4 + b"EKIM" + b"\0" * 0x34
    for c in cells:
        blob += _pad4(c)
    rows, st = tree(blob)
    paths = {(p, n): t for p, n, _ty, t in rows}
    check("two roots, every key reached",
          (st["roots"], st["reached"], st["keys"]) == (2, 5, 5))
    check("no dangling links", st["dangling"] == 0)
    check("child path", ("Drivers\\SDHC", None) in paths)
    check("sibling is a sibling, not a child",
          ("Drivers\\Profiles\\SDProfile", None) in paths)
    check("REG_SZ value", paths.get(("Drivers\\Profiles\\SDProfile", "Folder")) == "SystemSD")
    check("value chain via next", paths.get(("Drivers\\SDHC", "Order")) == "0x00000014")
    check("second root", paths.get(("Init", "Launch50")) == "Navi.exe")
    bad = blob.replace(struct.pack("<I", LINK | 12), struct.pack("<I", LINK | 99))
    check("negative: a broken value link is counted as dangling",
          tree(bad)[1]["dangling"] == 1)
    check("negative: random bytes give no keys",
          scan_cells(bytes(range(256)) * 16)[0] == {})
    print("selftest: %s (%d failed)" % ("OK" if not fails else "FAIL", len(fails)))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("hive", nargs="?")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--grep", help="only rows whose path, name or data match (case-insensitive)")
    ap.add_argument("--keys", action="store_true", help="print key paths only")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.hive:
        ap.error("HIVE or --selftest is required")
    d = Path(a.hive).read_bytes()
    rows, st = tree(d)
    print("# %s: %d bytes, keys %d (reached %d from %d roots), values %d (reached %d), "
          "dangling links %d" % (Path(a.hive).name, len(d), st["keys"], st["reached"],
                                 st["roots"], st["values"], st["values_reached"],
                                 st["dangling"]))
    rx = re.compile(a.grep, re.I) if a.grep else None
    for path, name, typ, text in rows:
        if a.keys and name is not None:
            continue
        line = path if name is None else "%s  %s (%s) = %s" % (path, name, typ, text)
        if rx and not rx.search(line):
            continue
        print(line)
    if a.json:
        Path(a.json).write_text(json.dumps({"stats": st, "rows": rows}, indent=1))
    return 0 if st["dangling"] == 0 and st["keys"] else 1


if __name__ == "__main__":
    sys.exit(main())
