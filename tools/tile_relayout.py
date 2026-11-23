#!/usr/bin/env python3
"""tile_relayout.py — write a MAPAL001 tile through our own layout (M5.85, Z1).

A from-zero tile needs a writer that places every component itself: the
section tables, the directories and the record blocks.  This tool proves that
writer on a factory tile: it reads every component into a model, forgets the
file offsets, lays the components out again (header, then per section: table,
directories, blocks; 256-byte aligned) and rewrites every pointer: the
section-table entries at ``0x800``, the directory pointers in each section
table and the slot/row tags in each directory.  Records are carried as opaque
bytes; nothing is copied by file position.

Directory models:

* section 1 levels 1 and 2: ``s1_wide_dir.parse_dir`` (rows of 512 or 1,024 bytes,
  one row block per row: even, sub0..sub3, odd per column; M5.53).  The
  generic 512-byte reader misplaces wide-row tags (C-8752).
* every other directory: ``clarion_tile.read_dir`` (one block per slot).

Tags that do not address a block (``0xffffffff``, ``0x7fffffff``, bit 31 set,
or below the header) are kept as they are.

Sub-commands::

    tile_relayout.py relayout IN.DAT -o OUT.DAT [--pad] [--json]
    tile_relayout.py compare A.DAT B.DAT      # same model, ignoring offsets
    tile_relayout.py --selftest

``relayout`` prints: components moved / kept at the same offset, record count,
bytes of the input not covered by any modelled component (dropped) and how many
of them are non-zero.  ``--pad`` zero-pads the end so every directory is backed
by the length the firmware reads (M3.31, ``tilewriter.pad_directory_reads``).
``compare`` exits 1 when the two tiles differ in any table box, directory
header, body word other than a tag, empty tag, or record byte.

Exit codes: 0 ok, 1 a check failed, 2 usage.  Stdlib only; no vendor bytes
are printed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE / "ze0-viewer" / "tools_ze0", HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import clarion_tile  # noqa: E402
import s1_wide_dir  # noqa: E402

TABLE1_OFF = clarion_tile.TABLE1_OFF
SECT_OFF = clarion_tile.SECT_OFF
pad256 = clarion_tile.pad256
enc_addr = clarion_tile.enc_addr
addr_of = clarion_tile.addr_of
FLAG = 0x80000000


class CheckFailed(Exception):
    pass


def _tag_live(tag: int, size: int) -> bool:
    if tag in (0xFFFFFFFF, 0x7FFFFFFF) or tag & FLAG:
        return False
    q = addr_of(tag)
    return TABLE1_OFF <= q < size


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------

def read_model(d: bytes) -> dict:
    """Tile -> model with old offsets recorded (for the moved/kept count)."""
    t = clarion_tile.read_tile(d)
    sections = []
    for si, sec in enumerate(t["sections"]):
        levels = []
        for li, L in enumerate(sec["levels"]):
            dirs = []
            for di, D in enumerate(L["dirs"]):
                if sec["id"] == 1 and L["level"] in (1, 2):
                    m = s1_wide_dir.parse_dir(d, D["off"], level=L["level"], check=False)
                    units = []
                    for r in m["rows"]:
                        live = "block_off" in r
                        units.append(dict(tag=r["tag"], live=live,
                                          old=r.get("block_off"),
                                          block=s1_wide_dir.row_block(r) if live else b"",
                                          recs=[x["raw"] for x in r["records"]]))
                    dirs.append(dict(model="wide", box=D["box"], old=D["off"],
                                     wm=m, units=units))
                elif sec["id"] == 4 and L["level"] == 1:
                    rows = parse_s4_dir(d, D["off"])
                    units = [dict(tag=r["tag"], live=r["live"], old=r["block_off"],
                                  block=b"".join(r["recs"]), recs=r["recs"]) for r in rows]
                    dirs.append(dict(model="s4wide", box=D["box"], old=D["off"],
                                     head=bytes(d[D["off"]:D["off"] + 12]), rows=rows,
                                     units=units))
                else:
                    units = []
                    for i in range(D.get("nslots", clarion_tile.SLOTS)):
                        s = D["slots"].get(i)
                        if s is None:
                            units.append(dict(tag=D.get("empty_tags", {}).get(i), live=False,
                                              old=None, block=b"", recs=[]))
                        else:
                            units.append(dict(tag=s["tag"], live=True, old=s["block_off"],
                                              block=clarion_tile.block_bytes(s),
                                              recs=[r["raw"] for r in s["recs"]]))
                    dirs.append(dict(model="slot", box=D["box"], old=D["off"], D=D, units=units))
            levels.append(dict(level=L["level"], typ=L["typ"], dirs=dirs))
        sections.append(dict(id=sec["id"], count=sec["count"], old=sec["taddr"], levels=levels))
    return dict(header=bytes(t["header"]), sections=sections, size=len(d))


S4_NARROW_COL, S4_WIDE_COL, NO_SUB = 8, 24, 0xFFFF


def parse_s4_dir(d: bytes, off: int) -> list[dict]:
    """Section-4 level-1 directory as rows (M5.85 finding, C-8765).

    Same row rule as section 1 (M5.53) with one record per column: a narrow
    row has 8 bytes per column ``(u32 ln, u32 X)``; a row whose first body
    word has bit 31 set is wide, 24 bytes per column: the 8-byte pair, four
    ``u16`` sub-record compressed sizes and four ``u16`` inflated sizes
    (``0xffff`` = none).  The row block holds, per column, the record and
    then its sub-records, each ``2 * ln`` bytes.  ``kind = 0x1046 + 0x100 *
    wide rows`` (``2 * kind`` = directory bytes)."""
    kind = struct.unpack_from(">H", d, off)[0]
    nslots = struct.unpack_from(">H", d, off + 4)[0] or 32
    p = off + 12
    rows = []
    for _ in range(nslots):
        tag, first = struct.unpack_from(">II", d, p)
        wide = bool(first & FLAG)
        per = S4_WIDE_COL if wide else S4_NARROW_COL
        body = bytes(d[p + 4:p + 4 + 32 * per])
        live = _tag_live(tag, len(d))
        recs = []
        q = addr_of(tag) if live else None
        if live:
            for c in range(32):
                b = body[c * per:(c + 1) * per]
                ln, x = struct.unpack_from(">II", b, 0)
                parts = []
                if (ln & 0x7FFFFFFF) != 0x7FFFFFFF:
                    parts.append(ln & 0x7FFFFFFF)
                if wide:
                    parts += [w for w in struct.unpack_from(">4H", b, 8) if w != NO_SUB]
                for n in parts:
                    recs.append(bytes(d[q:q + 2 * n]))
                    q += 2 * n
        rows.append(dict(tag=tag, wide=wide, body=body, live=live,
                         block_off=addr_of(tag) if live else None, recs=recs))
        p += 4 + 32 * per
    if p - off != 2 * kind:
        raise CheckFailed("section-4 directory at 0x%x: rows end at %d B, kind 0x%04x says %d B"
                          % (off, p - off, kind, 2 * kind))
    return rows


def _dir_len(dm: dict) -> int:
    if dm["model"] == "s4wide":
        return 12 + sum(4 + len(r["body"]) for r in dm["rows"])
    if dm["model"] == "wide":
        return len(s1_wide_dir.encode_dir(dm["wm"]))
    D = dm["D"]
    return 12 + D.get("nslots", clarion_tile.SLOTS) * (4 + D["body"]) + len(D.get("tail", b""))


def _dir_bytes(dm: dict, new_tags: list) -> bytes:
    if dm["model"] == "s4wide":
        out = bytearray(dm["head"])
        for r, tag in zip(dm["rows"], new_tags):
            out += struct.pack(">I", tag) + r["body"]
        return bytes(out)
    if dm["model"] == "wide":
        wm = dm["wm"]
        for row, tag in zip(wm["rows"], new_tags):
            row["tag"] = tag
        return s1_wide_dir.encode_dir(wm)
    D = dm["D"]
    addrs = {}
    for i, (u, tag) in enumerate(zip(dm["units"], new_tags)):
        if u["live"]:
            addrs[i] = addr_of(tag)
    # dir_bytes keeps the factory tag only when the address is unchanged;
    # we always want our own tag, so drop the old block_off first.
    saved = {i: D["slots"][i]["block_off"] for i in addrs}
    for i in addrs:
        D["slots"][i]["block_off"] = -1
    try:
        return clarion_tile.dir_bytes(D, addrs)
    finally:
        for i, v in saved.items():
            D["slots"][i]["block_off"] = v


def _table_bytes(sec: dict, dir_at: dict, si: int) -> bytes:
    nlev = len(sec["levels"])
    pos = 1 + nlev
    offs, groups = [], []
    for li, L in enumerate(sec["levels"]):
        if not L["dirs"]:
            offs.append(0xFFFF)
            continue
        offs.append(pos)
        groups.append(li)
        pos += 2 + 6 * len(L["dirs"])
    w = [pos] + offs
    for li in groups:
        L = sec["levels"][li]
        w += [2 + 6 * len(L["dirs"]), len(L["dirs"])]
        for di, dm in enumerate(L["dirs"]):
            a = enc_addr(dir_at[(si, li, di)])
            w += list(dm["box"]) + [a >> 16, a & 0xFFFF]
    return struct.pack(">%dH" % len(w), *w)


def write_model(m: dict) -> tuple[bytes, dict]:
    """Lay the model out from scratch; returns (bytes, stats)."""
    pos = TABLE1_OFF
    table_at, dir_at, block_at = {}, {}, {}
    # Two units can start at one address (an empty row and a real one, or a
    # factory block shared by two slots): give the address its longest block
    # and require every other one to be a prefix of it.
    longest = {}
    for sec in m["sections"]:
        for L in sec["levels"]:
            for dm in L["dirs"]:
                for u in dm["units"]:
                    if u["live"]:
                        cur = longest.get(u["old"], b"")
                        if len(u["block"]) > len(cur):
                            cur, short = u["block"], cur
                        else:
                            short = u["block"]
                        if cur[:len(short)] != short:
                            raise CheckFailed("two blocks at 0x%x differ" % u["old"])
                        longest[u["old"]] = cur
    # pass 1: offsets
    for si, sec in enumerate(m["sections"]):
        nw = 1 + len(sec["levels"]) + sum(2 + 6 * len(L["dirs"]) for L in sec["levels"] if L["dirs"])
        table_at[si] = pos
        pos = pad256(pos + 2 * nw)
        for li, L in enumerate(sec["levels"]):
            for di, dm in enumerate(L["dirs"]):
                dir_at[(si, li, di)] = pos
                pos = pad256(pos + _dir_len(dm))
        for li, L in enumerate(sec["levels"]):
            for di, dm in enumerate(L["dirs"]):
                for ui, u in enumerate(dm["units"]):
                    if not u["live"]:
                        continue
                    if u["old"] in block_at:      # shared block: keep shared
                        continue
                    block_at[u["old"]] = pos
                    pos = pad256(pos + len(longest[u["old"]]))
    out = bytearray(pos)
    out[:TABLE1_OFF] = m["header"]
    stats = dict(tables=0, dirs=0, blocks=0, same_offset=0, records=0)
    p = SECT_OFF
    for si, sec in enumerate(m["sections"]):
        struct.pack_into(">IH", out, p, enc_addr(table_at[si]), sec["count"])
        p += 6
    for si, sec in enumerate(m["sections"]):
        tb = _table_bytes(sec, dir_at, si)
        out[table_at[si]:table_at[si] + len(tb)] = tb
        stats["tables"] += 1
        stats["same_offset"] += table_at[si] == sec["old"]
        for li, L in enumerate(sec["levels"]):
            for di, dm in enumerate(L["dirs"]):
                tags = []
                for u in dm["units"]:
                    if u["live"]:
                        q = block_at[u["old"]]
                        tags.append(enc_addr(q))
                        out[q:q + len(longest[u["old"]])] = longest[u["old"]]
                        stats["records"] += len(u["recs"])
                    else:
                        tags.append(u["tag"])
                db = _dir_bytes(dm, tags)
                q = dir_at[(si, li, di)]
                out[q:q + len(db)] = db
                stats["dirs"] += 1
                stats["same_offset"] += q == dm["old"]
    stats["blocks"] = len(block_at)
    stats["shared_addresses"] = sum(1 for sec in m["sections"] for L in sec["levels"]
                                    for dm in L["dirs"] for u in dm["units"] if u["live"]) - len(block_at)
    stats["same_offset"] += sum(1 for old, new in block_at.items() if old == new)
    stats["size"] = len(out)
    return bytes(out), stats


def coverage(d: bytes, m: dict) -> dict:
    """Input bytes past the header that no modelled component covers."""
    spans = []
    for si, sec in enumerate(m["sections"]):
        nw = struct.unpack_from(">H", d, sec["old"])[0]
        spans.append((sec["old"], sec["old"] + 2 * nw))
        for L in sec["levels"]:
            for dm in L["dirs"]:
                spans.append((dm["old"], dm["old"] + _dir_len(dm)))
                for u in dm["units"]:
                    if u["live"]:
                        spans.append((u["old"], u["old"] + len(u["block"])))
    spans.sort()
    gaps, nonzero, pos = 0, 0, TABLE1_OFF
    nz_ranges = 0
    for a, b in spans:
        if a > pos:
            gaps += a - pos
            seg = d[pos:a]
            nz = len(seg) - seg.count(0)
            nonzero += nz
            nz_ranges += nz > 0
        pos = max(pos, b)
    if pos < len(d):
        seg = d[pos:]
        gaps += len(seg)
        nz = len(seg) - seg.count(0)
        nonzero += nz
        nz_ranges += nz > 0
    return dict(uncovered=gaps, uncovered_nonzero=nonzero, nonzero_ranges=nz_ranges)


def signature(d: bytes) -> dict:
    """Offset-free description of a tile, for ``compare``."""
    m = read_model(d)
    out = dict(header=hashlib.sha256(_header_wo_sections(m["header"])).hexdigest(), sections=[])
    for sec in m["sections"]:
        S = dict(id=sec["id"], count=sec["count"], levels=[])
        for L in sec["levels"]:
            LL = dict(level=L["level"], typ=L["typ"], dirs=[])
            for dm in L["dirs"]:
                LL["dirs"].append(dict(box=list(dm["box"]), head=_dir_head(dm),
                                       units=[[u["live"], None if u["live"] else u["tag"],
                                               hashlib.sha256(b"".join(u["recs"])).hexdigest(),
                                               len(u["recs"])] for u in dm["units"]]))
            S["levels"].append(LL)
        out["sections"].append(S)
    return out


def _header_wo_sections(h: bytes) -> bytes:
    """Header with the section table addresses zeroed (they are layout)."""
    b = bytearray(h)
    p = SECT_OFF
    while p + 6 <= len(b):
        a = struct.unpack_from(">I", b, p)[0]
        if a == 0xFFFFFFFF:
            break
        b[p:p + 4] = b"\0\0\0\0"
        p += 6
    return bytes(b)


def _dir_head(dm: dict) -> list:
    if dm["model"] == "s4wide":
        return [dm["head"].hex(), hashlib.sha256(b"".join(r["body"] for r in dm["rows"])).hexdigest()]
    if dm["model"] == "wide":
        w = dm["wm"]
        bodies = [s1_wide_dir.encode_body(r["cols"], r["wide"]).hex() for r in w["rows"]]
        return [w["kind"], list(w["ab"]), w["y"], w["x"], w["typ"],
                hashlib.sha256("".join(bodies).encode()).hexdigest()]
    D = dm["D"]
    bodies = b"".join(D["slots"][i]["body"] if i in D["slots"]
                      else D.get("empty_bodies", {}).get(i, b"")
                      for i in range(D.get("nslots", clarion_tile.SLOTS)))
    return [D["kind"], list(D["ab"]), D["y"], D["x"], D["typ"],
            hashlib.sha256(bodies + D.get("tail", b"")).hexdigest()]


def compare(a: bytes, b: bytes) -> list[str]:
    sa, sb = signature(a), signature(b)
    diffs = []
    if sa["header"] != sb["header"]:
        diffs.append("header (outside the section-table addresses)")
    if len(sa["sections"]) != len(sb["sections"]):
        return diffs + ["section count %d vs %d" % (len(sa["sections"]), len(sb["sections"]))]
    for si, (x, y) in enumerate(zip(sa["sections"], sb["sections"])):
        if (x["id"], x["count"]) != (y["id"], y["count"]):
            diffs.append("section %d id/count" % si)
        for li, (L, M) in enumerate(zip(x["levels"], y["levels"])):
            if (L["level"], L["typ"], len(L["dirs"])) != (M["level"], M["typ"], len(M["dirs"])):
                diffs.append("section %d level %d shape" % (x["id"], L["level"]))
                continue
            for di, (D, E) in enumerate(zip(L["dirs"], M["dirs"])):
                if D["box"] != E["box"] or D["head"] != E["head"]:
                    diffs.append("sec %d lv %d dir %d header/body" % (x["id"], L["level"], di))
                if D["units"] != E["units"]:
                    n = sum(1 for u, v in zip(D["units"], E["units"]) if u != v)
                    diffs.append("sec %d lv %d dir %d: %d slot(s) differ" % (x["id"], L["level"], di, n))
    return diffs


def relayout(d: bytes, pad: bool = False) -> tuple[bytes, dict]:
    m = read_model(d)
    cov = coverage(d, m)
    out, stats = write_model(m)
    if pad:
        import tilewriter  # noqa: E402  (heavy import, only when asked)
        out = tilewriter.pad_directory_reads(out)
        stats["size_padded"] = len(out)
    stats.update(cov)
    stats["input_size"] = len(d)
    diffs = compare(d, out)
    stats["compare_diffs"] = len(diffs)
    if diffs:
        raise CheckFailed("model changed by the relayout: " + "; ".join(diffs[:5]))
    census = s1_wide_dir.census(out)
    if census["counts"].get("dirs", 0) and not s1_wide_dir.census_ok(census):
        raise CheckFailed("s1_wide_dir census fails on the relaid tile")
    return out, stats


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------

def selftest() -> int:
    fails = 0

    def ok(cond, msg):
        nonlocal fails
        print(("ok   " if cond else "FAIL ") + msg)
        fails += 0 if cond else 1

    # Build a small tile with clarion_tile: 1 section (id 2), 1 level, 1 dir,
    # three slots, then shuffle its layout by hand and check compare/relayout.
    def rec(words, seed):
        body = bytes((seed + i) & 0xFF for i in range(2 * words))
        c = zlib.compress(body, 6)
        c += bytes((-len(c)) % 4)
        return c, len(c) // 2, words

    hdr = bytearray(TABLE1_OFF)
    struct.pack_into(">H", hdr, clarion_tile.LEVEL_OFF, 1)
    hdr[clarion_tile.LEVEL_OFF + 2:clarion_tile.LEVEL_OFF + 4] = bytes([2, 1])
    hdr[clarion_tile.LEVEL_OFF + 4:clarion_tile.LEVEL_OFF + 8] = bytes([1, 0x90]) + struct.pack(">H", 1)
    struct.pack_into(">IH", hdr, SECT_OFF + 6, 0xFFFFFFFF, 0)

    def build(order_blocks_first: bool) -> bytes:
        body = 256
        recs = [rec(40, 1), rec(10, 7), rec(25, 3)]
        layout = {}
        pos = TABLE1_OFF
        items = ["table", "dir", "b0", "b1", "b2"]
        if order_blocks_first:
            items = ["b2", "b0", "table", "b1", "dir"]
        dlen = 12 + 32 * (4 + body)
        for it in items:
            layout[it] = pos
            n = {"table": 2 * 10, "dir": dlen}.get(it, len(recs[int(it[1]) if it[0] == "b" else 0][0]))
            pos = pad256(pos + n)
        out = bytearray(pos)
        out[:TABLE1_OFF] = hdr
        struct.pack_into(">IH", out, SECT_OFF, enc_addr(layout["table"]), 1)
        a = enc_addr(layout["dir"])
        w = [10, 2, 2 + 6, 1, 100, 0, 0, 100, a >> 16, a & 0xFFFF]
        out[layout["table"]:layout["table"] + 20] = struct.pack(">10H", *w)
        d = bytearray(struct.pack(">6H", 0x1046, 0, 32, 5, 6, 0))
        for i in range(32):
            if i in (2, 9, 17):
                k = (2, 9, 17).index(i)
                d += struct.pack(">I", enc_addr(layout["b%d" % k]))
                bb = struct.pack(">II", recs[k][1], recs[k][2]) + b"\xff" * (body - 8)
                d += bb
            else:
                d += b"\xff" * (4 + body)
        out[layout["dir"]:layout["dir"] + len(d)] = d
        for k in range(3):
            q = layout["b%d" % k]
            out[q:q + len(recs[k][0])] = recs[k][0]
        return bytes(out)

    plain = build(False)
    shuffled = build(True)
    ok(plain != shuffled, "two layouts of one tile differ as bytes")
    ok(compare(plain, shuffled) == [], "compare: two layouts of one tile are the same model")
    out, st = relayout(shuffled)
    ok(compare(shuffled, out) == [], "relayout keeps the model (records %d)" % st["records"])
    ok(st["records"] == 3, "relayout carries 3 records")
    ok(st["uncovered_nonzero"] == 0, "no non-zero byte left uncovered")
    ok(out == relayout(plain)[0], "relayout output does not depend on the input layout")
    # negative control: one record byte flipped
    bad = bytearray(shuffled)
    q = TABLE1_OFF + 8  # inside b2, first block in the shuffled layout
    bad[q] ^= 0xFF
    ok(compare(shuffled, bytes(bad)) != [], "compare finds a flipped record byte (negative control)")
    # negative control: an extra non-zero byte in a gap is reported
    gap = bytearray(shuffled)
    gap.extend(bytes(256))
    gap[-5] = 1
    st2 = relayout(bytes(gap))[1]
    ok(st2["uncovered_nonzero"] == 1, "a non-zero byte outside every component is counted")
    print("tile_relayout selftest: %s (%d failure(s))" % ("OK" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("relayout")
    p.add_argument("tile")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--pad", action="store_true")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("compare")
    p.add_argument("a")
    p.add_argument("b")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "relayout":
        d = Path(args.tile).read_bytes()
        try:
            out, st = relayout(d, pad=args.pad)
        except CheckFailed as exc:
            print("tile_relayout: FAIL %s" % exc)
            return 1
        Path(args.out).write_bytes(out)
        st["sha256"] = hashlib.sha256(out).hexdigest()
        moved = st["tables"] + st["dirs"] + st["blocks"] - st["same_offset"]
        st["moved"] = moved
        if args.json:
            print(json.dumps(st, indent=1, sort_keys=True))
        else:
            print("relayout: tables=%d dirs=%d blocks=%d records=%d moved=%d same_offset=%d"
                  % (st["tables"], st["dirs"], st["blocks"], st["records"], moved, st["same_offset"]))
            print("input %d B -> output %d B%s; uncovered input %d B (non-zero %d B in %d ranges)"
                  % (st["input_size"], st["size"],
                     (" (padded %d B)" % st["size_padded"]) if "size_padded" in st else "",
                     st["uncovered"], st["uncovered_nonzero"], st["nonzero_ranges"]))
            print("compare: 0 differences; s1_wide_dir census OK; sha256 %s" % st["sha256"])
        return 0
    if args.cmd == "compare":
        diffs = compare(Path(args.a).read_bytes(), Path(args.b).read_bytes())
        for x in diffs[:50]:
            print("DIFF", x)
        print("compare: %d difference(s)" % len(diffs))
        return 1 if diffs else 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
