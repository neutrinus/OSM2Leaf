#!/usr/bin/env python3
"""dir_read_len.py - the length the firmware reads for each tile directory.

M3.31 (EXP-2026-11-20-M3.31-dir-read-length): `Navi.exe` (EU2011) does not
read a directory with the directory's own size.  The request built by
`0x00414338` (EU2011) takes the length from the leaf `0x0040901c(kind, 1)`:

    length = 0x100 * T[kind].n

`T` is a 16-row table at data VA 0x179c08 (EU2011, `Navi.exe` section 0,
uncompressed) of rows `{u32 kind, u32 n, u32 buffer}`; a kind with no row
gives 0 and the directory is not read.  `kind` is the runtime level kind of
the (section, level) pair at 0xd982a0 + 72*i + 12*(level - 1) (i = the
section's position in the level table), which
`0x00409834` copies from the low byte of the merged level table: the second
byte of the 4-byte entry `(level, kind, u16 count)` in the tile header at
0x1ac (`0x0040aa50` merges the headers of the mounted files; an entry with a
non-zero count replaces the merged one).

This tool applies that rule to a tile file: per section and level it prints
the kind, the read length, the directories, the largest declared directory
size (2 * header word 0) and every directory whose read runs past the end of
the file (the M9.13 failure, C-3256).  `table` reads T from the image and
compares it with the copy below.

No vendor byte is stored: the table copy is 16 rows of small integers (the
kind codes and lengths), cross-checked against the image by `table`.

Usage:
  dir_read_len.py --selftest
  dir_read_len.py table IMG256
  dir_read_len.py predict TILE [--json OUT]

Exit codes: predict: 0 every directory is backed by its read length, 1 at
least one read runs past the end of the file; table: 0 the image matches the
copy, 1 it differs; 2 usage or missing input.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

# T at data VA 0x179c08 (EU2011 Navi.exe): (kind, length / 0x100, buffer bytes).
LEN_TABLE_VA = (0x179 << 12) + 0xC08
LEN_TABLE_EU2011 = (
    (0x00, 0x11, 0x1080), (0x01, 0xA1, 0xA100), (0x02, 0x41, 0x4080), (0x03, 0x31, 0x3080),
    (0x80, 0x11, 0x1080), (0x81, 0xA1, 0xA100), (0x82, 0x41, 0x4080), (0x83, 0x31, 0x3080),
    (0x10, 0x21, 0x2080), (0x11, 0x141, 0x14100), (0x12, 0x81, 0x8080), (0x13, 0x61, 0x6080),
    (0x90, 0x21, 0x2080), (0x91, 0x141, 0x14100), (0x92, 0x81, 0x8080), (0x93, 0x61, 0x6080),
)
IMAGE_A = 0x200200
LEVEL_OFF, SECT_OFF = 0x1AC, 0x800


def read_length(kind: int, table=LEN_TABLE_EU2011) -> int:
    """0x0040901c(kind, 1) * 0x100: the first row with this kind, else 0."""
    for k, n, _buf in table:
        if k == kind:
            return n * 0x100
    return 0


def addr_of(v: int) -> int:
    return (v >> 8) * 0x800 + (v & 0xFF) * 0x100


def level_table(head: bytes) -> list[tuple[int, list[tuple[int, int, int]]]]:
    """Header 0x1ac: u16 n, then per section {u8 id, u8 count, count x
    (u8 level, u8 kind, u16 count)} (big-endian, map-tiles.md)."""
    n = struct.unpack_from(">H", head, LEVEL_OFF)[0]
    p, out = LEVEL_OFF + 2, []
    for _ in range(n):
        sid, cnt = head[p], head[p + 1]
        p += 2
        rows = []
        for i in range(cnt):
            lv, kind, c = struct.unpack_from(">BBH", head, p + 4 * i)
            rows.append((lv, kind, c))
        p += 4 * cnt
        out.append((sid, rows))
    return out


def section_list(head: bytes) -> list[int]:
    p, out = SECT_OFF, []
    while p + 6 <= len(head):
        a, _c = struct.unpack_from(">IH", head, p)
        p += 6
        if a == 0xFFFFFFFF:
            break
        out.append(addr_of(a))
    return out


def predict(f, size: int, table=LEN_TABLE_EU2011) -> dict:
    """Per (section, level) the read length and the directories it covers."""
    f.seek(0)
    head = f.read(0x1000)
    rows = []
    short = []
    for (sid, levels), taddr in zip(level_table(head), section_list(head)):
        f.seek(taddr)
        nw = struct.unpack(">H", f.read(2))[0]
        f.seek(taddr)
        w = struct.unpack(">%dH" % nw, f.read(2 * nw))
        for li, (lv, kind, cnt) in enumerate(levels):
            length = read_length(kind, table)
            o = w[1 + li] if 1 + li < len(w) else 0xFFFF
            dirs = []
            if o != 0xFFFF and cnt:
                for k in range(w[o + 1]):
                    z, tg = w[o + 6 + 6 * k], w[o + 7 + 6 * k]
                    pos = addr_of((z << 16) | tg)
                    f.seek(pos)
                    hdr = f.read(2)
                    declared = 2 * struct.unpack(">H", hdr)[0] if len(hdr) == 2 else 0
                    dirs.append((pos, declared))
                    if length and pos + length > size:
                        short.append({"section": sid, "level": lv, "pos": pos, "end": pos + length, "size": size})
            rows.append({"section": sid, "level": lv, "kind": kind, "count": cnt, "read_length": length,
                         "dirs": len(dirs), "max_declared": max((d for _p, d in dirs), default=0),
                         "fits": all(d <= length for _p, d in dirs) if length else None})
    return {"size": size, "levels": rows, "short_reads": short}


def show(rep: dict) -> None:
    print("file size %d (%#x)" % (rep["size"], rep["size"]))
    print("section level kind  count  read length  dirs  largest declared dir")
    for r in rep["levels"]:
        print("  %5d %5d %#04x %6d  %11s  %4d  %d" % (
            r["section"], r["level"], r["kind"], r["count"],
            ("%#x" % r["read_length"]) if r["read_length"] else "none (no row)", r["dirs"], r["max_declared"]))
    for s in rep["short_reads"]:
        print("SHORT: section %d level %d directory at %#x is read to %#x, past the end of the file (%#x)" % (
            s["section"], s["level"], s["pos"], s["end"], s["size"]))
    print("directories read past the end of the file: %d" % len(rep["short_reads"]))


def image_table(image: str) -> list[tuple[int, int, int]]:
    """T read from the image through the CE ROM section table (cerom.py)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cerom
    data = Path(image).read_bytes()
    rom = cerom.CERom(data, IMAGE_A)
    mod = next(m for m in rom.modules() if m["name"].lower() == "navi.exe")
    for sec in rom.o32(mod):
        if sec["realaddr"] <= LEN_TABLE_VA < sec["realaddr"] + sec["psize"]:
            off = rom._romptr2file(sec["dataptr"]) + (LEN_TABLE_VA - sec["realaddr"])
            return [struct.unpack_from("<III", data, off + 12 * i) for i in range(16)]
    raise SystemExit("VA %#x is not in a stored Navi.exe section" % LEN_TABLE_VA)


def cmd_table(args) -> int:
    rows = image_table(args.image)
    for k, n, buf in rows:
        print("kind %#04x  length %#7x  buffer %#7x" % (k, n * 0x100, buf))
    same = [tuple(r) for r in rows] == list(LEN_TABLE_EU2011)
    print("table at VA %#x: %s the copy in dir_read_len.py" % (LEN_TABLE_VA, "matches" if same else "DIFFERS from"))
    return 0 if same else 1


def cmd_predict(args) -> int:
    path = Path(args.tile)
    with path.open("rb") as f:
        rep = predict(f, path.stat().st_size)
    rep["file"] = path.name
    show(rep)
    if args.json:
        Path(args.json).write_text(json.dumps(rep, indent=1))
    return 1 if rep["short_reads"] else 0


def synth_tile(dir_len: int = 0x200, file_pad: int = 0x9000) -> bytes:
    """One section, two levels (2: kind 0x91, 1: kind 0x92), one directory each."""
    d = bytearray(0x1000)
    lv = struct.pack(">H", 1) + bytes([1, 2]) + struct.pack(">BBH", 2, 0x91, 1) + struct.pack(">BBH", 1, 0x92, 1)
    d[LEVEL_OFF:LEVEL_OFF + len(lv)] = lv
    d[SECT_OFF:SECT_OFF + 12] = struct.pack(">IH", 0x0200, 1) + b"\xff" * 6     # table at 0x1000
    # table: nw, level offsets, then per level {glen, gcnt, y1, y0, x0, x1, z, tag}
    words = [0, 3, 11, 8, 1, 0, 0, 0, 0, 0, 0x0201, 8, 1, 0, 0, 0, 0, 0, 0x0202]
    words[0] = len(words)
    tbl = struct.pack(">%dH" % len(words), *words)
    d[0x1000:0x1000 + len(tbl)] = tbl
    d += bytes(0x1200 - len(d))
    for pos in (0x1100, 0x1200):          # two directories, header word 0 = size in u16 words
        d[pos:pos + 2] = struct.pack(">H", dir_len // 2)
    d += bytes(file_pad)
    return bytes(d)


def selftest() -> int:
    import io
    fails = []

    def check(name, cond):
        print("  %-66s %s" % (name, "ok" if cond else "FAIL"))
        if not cond:
            fails.append(name)

    check("kind 0x92 (section 1 level 1) reads 0x8100", read_length(0x92) == 0x8100)
    check("kind 0x91 (level 2) reads 0x14100", read_length(0x91) == 0x14100)
    check("kind 0x90 / 0x93 read 0x2100 / 0x6100", (read_length(0x90), read_length(0x93)) == (0x2100, 0x6100))
    check("kind 0x80 (LEV3456R level 6) reads 0x1100", read_length(0x80) == 0x1100)
    check("bit 7 of the kind does not change the length",
          all(read_length(k) == read_length(k | 0x80) for k in (0, 1, 2, 3, 0x10, 0x11, 0x12, 0x13)))
    check("a kind with no row reads nothing", read_length(0x94) == 0 and read_length(0x06) == 0)
    check("the first matching row wins", read_length(5, ((5, 1, 0), (5, 2, 0))) == 0x100)
    t = synth_tile()
    lv = level_table(t)
    check("level table decodes (section, [(level, kind, count)])", lv == [(1, [(2, 0x91, 1), (1, 0x92, 1)])])
    check("section list decodes one table at 0x1000", section_list(t) == [0x1000])
    rep = predict(io.BytesIO(t), len(t))
    check("both levels get their table length",
          [(r["level"], r["read_length"], r["dirs"]) for r in rep["levels"]] == [(2, 0x14100, 1), (1, 0x8100, 1)])
    check("declared directory size is 2 * header word 0", rep["levels"][0]["max_declared"] == 0x200)
    check("a 0x9000-byte pad backs the 0x8100 read but not the 0x14100 read",
          [(s["level"], s["pos"]) for s in rep["short_reads"]] == [(2, 0x1100)])
    big = synth_tile(file_pad=0x14100)
    check("a 0x14100-byte pad backs both reads", predict(io.BytesIO(big), len(big))["short_reads"] == [])
    print("dir_read_len selftest: %d failed" % len(fails))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("table", help="read the length table from the image and compare it with the copy")
    p.add_argument("image")
    p = sub.add_parser("predict", help="read length per section/level of a tile, and short reads")
    p.add_argument("tile")
    p.add_argument("--json")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmd:
        ap.print_usage()
        return 2
    path = args.image if args.cmd == "table" else args.tile
    if not Path(path).is_file():
        print("missing input: %s" % path)
        return 2
    return {"table": cmd_table, "predict": cmd_predict}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
