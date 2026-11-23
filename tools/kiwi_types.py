#!/usr/bin/env python3
"""kiwi_types.py — KIWI ch.1.2 basic types against our documented tables (M4.66).

The three type definitions are *field names and arithmetic* quoted from the
public reader jharg/kiwiread (GPL-3.0-or-later, commit 74741c5b, file
``kiwiread.c``: ``SWS``, ``D`` and ``sectoraddress_t`` / ``getsector``); no
KIWI code is copied into this repository.  See docs/research/kiwi-sources.md.

    SWS(v) = 0xffff if v == 0xffff else 2*v     size in u16 words (2-byte words)
    D(v)   = 0xffff if v == 0xffff else 2*v     offset in u16 words
    SA(v)  = (v >> 8) * 2048 + (v & 0x3f) * 32
                                                24-bit sector, 2 flag bits,
                                                6-bit word index (1.2.7)

A table "fits" a type when decoding every stored value with that type
reproduces a byte quantity measured from an *independent* oracle: a zlib
stream's own end, the parsed directory extent, the size of a .cmp file, the
summed tile counts, or the node-table geometry of DRSTR.  Raw values (the
stored u16/u32 themselves) are never used as their own oracle except where the
documented unit *is* a plain byte offset (the .ind chunk table), which is the
falsifying test for SA.

No vendor bytes are written: the tool only reads a card tree outside the repo.
Exit codes: 0 ok, 1 a required file is missing/unparsable, 2 usage.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import zlib
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
for _p in (HERE / "ze0-viewer" / "tools_ze0", HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import clarion_tile  # noqa: E402
import hashutil  # noqa: E402

ABSENT = 0xFFFF
SA_SECTOR_SZ = 2048
SA_LOGICAL_SZ = 32


def sws(v: int) -> int:
    """KIWI SWS: a size stored in 2-byte words; 0xffff means 'absent'."""
    return ABSENT if v == ABSENT else 2 * v


def d_offset(v: int) -> int:
    """KIWI D: an offset stored in 2-byte words; 0xffff means 'absent'."""
    return ABSENT if v == ABSENT else 2 * v


def sector_address(v: int, sector_sz: int = SA_SECTOR_SZ,
                   logical_sz: int = SA_LOGICAL_SZ) -> int:
    """KIWI 1.2.7 sector address -> byte offset (jharg/kiwiread getsector)."""
    return (v >> 8) * sector_sz + (v & 0x3F) * logical_sz


DECODERS: dict[str, Callable[[int], int]] = {
    "SWS": sws,
    "D": d_offset,
    "SA": sector_address,
}


def score(name: str, kiwi_type: str, unit: str, oracle: str,
          pairs: list[tuple[int, int]], note: str = "") -> dict[str, Any]:
    """Count decoded-value == independent-oracle over one documented table."""
    dec = DECODERS[kiwi_type]
    total = len(pairs)
    fits = sum(1 for stored, doc in pairs if dec(stored) == doc)
    # A fit is only informative when the stored value carries information:
    # 0/0xffff/0xffffffff sentinels, a zero oracle and (for SA) a zero word
    # index all make the two readings coincide without evidence.
    def degenerate(v: int, doc: int) -> bool:
        return (v in (0, ABSENT, 0xFFFFFFFF) or doc == 0
                or (kiwi_type == "SA" and (v & 0x3F) == 0))
    degen = sum(1 for v, doc in pairs if degenerate(v, doc))
    return {
        "table": name, "type": kiwi_type, "unit": unit, "oracle": oracle,
        "fits": fits, "total": total, "degenerate": degen,
        "informative_fits": sum(1 for v, doc in pairs
                                if dec(v) == doc and not degenerate(v, doc)),
        "informative_total": total - degen, "note": note,
    }


def _sha(path: Path) -> str:
    return hashutil.sha256_file(str(path))


def _level_counts(header: bytes) -> list[tuple[int, int, int]]:
    """(level, kind, count) tuples from the 0x1ac descriptor table."""
    tables, _ = clarion_tile.walk(header, 0x1AC, 4)
    return [(sid, rec[0], rec[1], struct.unpack_from(">H", rec, 2)[0])
            for sid, rows in tables for rec in rows]


def _mmain_tables(root: Path, tiles: list[Path]) -> tuple[Any, ...]:
    """MMAIN totals vs the summed per-tile level tables, plus tile counts."""
    mmain = root / "MMAIN001.DAT"
    totals = _level_counts(mmain.read_bytes()[:0x400])
    summed: dict[tuple[int, int, int], int] = {}
    for tile in tiles:
        with tile.open("rb") as fh:
            for sid, lvl, typ, cnt in _level_counts(fh.read(0x400)):
                key = (sid, lvl, typ)
                summed[key] = summed.get(key, 0) + cnt
    mm_pairs = [(cnt, summed.get((sid, lvl, typ), 0))
                for sid, lvl, typ, cnt in totals]
    t = score("mmain-level-totals", "SWS", "plain u16 count at 0x1ac",
              "sum of per-tile 0x1ac counts over %d MAPAL001/*.DAT headers" % len(tiles),
              mm_pairs, "MMAIN at %s" % mmain.name)
    return t, totals, summed


def _tile_tables(tiles: list[Path]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    level_pairs: list[tuple[int, int]] = []
    dir_pairs: list[tuple[int, int]] = []
    ln_pairs: list[tuple[int, int]] = []
    x_pairs: list[tuple[int, int]] = []
    tag_pairs: list[tuple[int, int]] = []
    ln_by_section: dict[int, list[tuple[int, int]]] = {}
    skipped_raw = 0
    skipped_wide = 0
    per_tile: dict[str, Any] = {}
    for tile in tiles:
        data = tile.read_bytes()
        parsed = clarion_tile.read_tile(data)
        seen: dict[tuple[int, int, int], int] = {}
        declared: list[tuple[int, int, int, int]] = []
        tables, _end = clarion_tile.walk(data, 0x1AC, 4)
        for sid, rows in tables:
            for rec in rows:
                declared.append((sid, rec[0], rec[1],
                                 struct.unpack_from(">H", rec, 2)[0]))
        n_dirs = n_streams = 0
        for sec in parsed["sections"]:
            for lvl in sec["levels"]:
                for D in lvl["dirs"]:
                    n_dirs += 1
                    key = (sec["id"], lvl["level"], lvl["typ"])
                    seen[key] = seen.get(key, 0) + 1
                    # Independent extent: the parser's own end of this
                    # directory (header + nslots*(tag+body) + wide tail).
                    dir_pairs.append((D["kind"], D["end"] - D["off"]))
                    for slot in D["slots"].values():
                        tag_pairs.append((slot["tag"], clarion_tile.addr_of(slot["tag"])))
                        q = slot["block_off"]
                        words = struct.unpack_from(">%dI" % (D["body"] // 4), slot["body"])
                        for rec in slot["recs"]:
                            ln = words[2 * rec["k"]] & 0x7FFFFFFF
                            xw = words[2 * rec["k"] + 1]
                            if not clarion_tile.is_zlib(data, q):
                                skipped_raw += 1
                                q += len(rec["raw"])
                                continue
                            z = zlib.decompressobj()
                            window = data[q:q + 0x20000]
                            inflated = z.decompress(window)
                            consumed = len(window) - len(z.unused_data)
                            # Factory streams are zero-padded to a 4-byte
                            # boundary; an SWS count is the padded byte span
                            # in 2-byte words, measured from the zlib stream.
                            padded = (consumed + 3) // 4 * 4
                            if ln >> 16 or xw >> 16:
                                skipped_wide += 1
                            else:
                                ln_pairs.append((ln, padded))
                                x_pairs.append((xw, len(inflated)))
                                ln_by_section.setdefault(sec["id"], []).append(
                                    (ln, padded))
                            n_streams += 1
                            q += len(rec["raw"])
        for sid, lvl, typ, count in declared:
            level_pairs.append((count, seen.get((sid, lvl, typ), 0)))
        per_tile[tile.name] = {
            "sha256": _sha(tile), "size": len(data), "dirs": n_dirs,
            "zlib_streams": n_streams,
        }

    by_section = {}
    for sid, pairs in sorted(ln_by_section.items()):
        s = score("section-%d" % sid, "SWS", "compressed word count",
                  "zlib stream length rounded up to 4 bytes", pairs)
        by_section[str(sid)] = "%d/%d" % (s["fits"], s["total"])
    tables = [
        score("tile-level-counts", "SWS", "plain u16 count in 0x1ac entries",
              "parsed directories of that level/kind in %d tiles" % len(tiles),
              level_pairs),
        score("tile-dir-size", "SWS", "u16 words: byte size / 2 (header word 0)",
              "parsed directory end - start", dir_pairs),
        dict(score("tile-slot-ln", "SWS", "u16 words: compressed size / 2 (pair word 0)",
                   "zlib stream length rounded up to 4 bytes", ln_pairs,
                   "%d raw records and %d >16-bit pair words skipped"
                   % (skipped_raw, skipped_wide)), by_section=by_section),
        score("tile-slot-X", "SWS", "u16 words: inflated size / 2 (pair word 1)",
              "uncompressed zlib output length", x_pairs),
        score("tile-slot-address", "SA", "u32 sector/page address (slot tag)",
              "clarion_tile.addr_of(tag), our documented byte address",
              tag_pairs, "KIWI uses 24-bit sector + 6-bit word; ZE0 16-bit sector + 8-bit page"),
    ]
    return tables, per_tile


def _ind_tables(root: Path) -> tuple[list[dict[str, Any]], int, int]:
    ind_dir = root / "REFER001"
    off_pairs: list[tuple[int, int]] = []
    size_pairs: list[tuple[int, int]] = []
    n_ind = n_offs = 0
    for ind in sorted(ind_dir.glob("*.ind")):
        raw = ind.read_bytes()
        if len(raw) < 16:
            raise ValueError("short .ind: %s" % ind)
        _unc, comp, count, _chunk = struct.unpack_from("<IIII", raw, 0)
        n_ind += 1
        cmp_path = Path(str(ind)[:-4] + ".cmp")
        size_pairs.append((comp & 0xFFFF, cmp_path.stat().st_size))
        if len(raw) != 16 + 4 * count:
            raise ValueError("bad .ind length: %s" % ind)
        for i in range(count):
            off = struct.unpack_from("<I", raw, 16 + 4 * i)[0]
            off_pairs.append((off, off))  # documented unit IS a plain byte offset
            n_offs += 1
    return [
        score("ind-chunk-offset", "SA", "u32 plain byte offset in .cmp",
              "the same u32 (only a 0 offset can fit an SA decode)", off_pairs,
              "%d .ind files, %d chunk offsets" % (n_ind, n_offs)),
        score("ind-compressed-size", "SWS", "u32 byte count (low u16 read as SWS)",
              "stat() size of the paired .cmp file", size_pairs,
              "%d .ind/.cmp pairs; high u16 ignored" % n_ind),
    ], n_ind, n_offs


def _drstr_tables(root: Path, ind_sizes: dict[str, int]) -> tuple[list[dict[str, Any]], int, int]:
    path = root / "DRSTR001.DAT"
    data = path.read_bytes()
    if len(data) < 40:
        raise ValueError("short DRSTR001.DAT")
    root_listing = struct.unpack_from("<I", data, 0x24)[0]
    node_count = root_listing // 40
    if node_count * 40 > len(data):
        raise ValueError("bad DRSTR node count %d" % node_count)

    expected = 40 * node_count
    off_pairs: list[tuple[int, int]] = []
    value_pairs: list[tuple[int, int]] = []
    n_entries = 0
    for i in range(node_count):
        node = data[40 * i:40 * (i + 1)]
        stored_listing = struct.unpack_from("<I", node, 0x24)[0]
        if stored_listing >> 16 == 0:
            off_pairs.append((stored_listing, expected))
        entry_count = struct.unpack_from("<I", node, 0x18)[0]
        if expected + 32 * entry_count > len(data):
            raise ValueError("DRSTR listing %d exceeds file" % expected)
        base = expected
        expected += 32 * entry_count
        for j in range(entry_count):
            ent = data[base + 32 * j:base + 32 * (j + 1)]
            name = ent[:13].split(b"\0", 1)[0].decode("ascii", "replace")
            typ = struct.unpack_from("<H", ent, 0x16)[0]
            value = struct.unpack_from("<I", ent, 0x1C)[0]
            n_entries += 1
            if typ == 0 and name.upper().endswith(".DAT"):
                key = name.upper()
                if key in ind_sizes:
                    value_pairs.append((value & 0xFFFF, ind_sizes[key]))
    return [
        score("drstr-listing-offset", "D", "u32 byte offset in DRSTR (low u16)",
              "40*node_count + 32*sum(earlier entry_count)", off_pairs,
              "%d nodes; high u16 ignored" % node_count),
        score("drstr-entry-value", "SWS", "u32 logical size (low u16 read as SWS)",
              ".ind uncompressed_size for the same REFER001 name", value_pairs,
              "%d entries scanned; high u16 ignored" % n_entries),
    ], node_count, n_entries


def census(root: Path, tiles: int = 3, json_path: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("no such card tree: %s" % root)
    all_files = sorted((root / "MAPAL001").glob("*.DAT"),
                       key=lambda p: (p.stat().st_size, p.name))
    if not all_files:
        raise ValueError("no MAPAL001/*.DAT tiles in %s" % root)
    # MMAIN totals sum the whole directory, including LEV3456R (levels 3-6);
    # only the small BxxRyyR grid tiles are fully parsed below.
    grid = [p for p in all_files if p.name.startswith("B")]
    chosen = grid[:tiles]

    mm_table, totals, summed = _mmain_tables(root, all_files)
    tile_tables, per_tile = _tile_tables(chosen)
    ind_tables, n_ind, n_offs = _ind_tables(root)
    ind_sizes: dict[str, int] = {}
    for ind in (root / "REFER001").glob("*.ind"):
        ind_sizes[ind.name.upper()[:-4]] = struct.unpack_from("<I", ind.read_bytes()[:4])[0]
    dr_tables, node_count, n_entries = _drstr_tables(root, ind_sizes)
    tables = [mm_table] + tile_tables + ind_tables + dr_tables
    return {
        "root": str(root),
        "files": {
            "MMAIN001.DAT": _sha(root / "MMAIN001.DAT"),
            "DRSTR001.DAT": _sha(root / "DRSTR001.DAT"),
        },
        "tiles": per_tile,
        "tile_count_all": len(grid),
        "mapal_files": len(all_files),
        "mmain_rows": len(totals),
        "mmain_summed_keys": len(summed),
        "ind_files": n_ind,
        "ind_chunk_offsets": n_offs,
        "drstr_nodes": node_count,
        "drstr_entries": n_entries,
        "tables": tables,
    }


def render(result: dict[str, Any]) -> str:
    out = [
        "kiwi_types: KIWI 1.2 types vs documented tables (jharg/kiwiread 74741c5b, GPL-3 link only)",
        "root %s" % result["root"],
        "  MMAIN001.DAT sha256 %s" % result["files"]["MMAIN001.DAT"],
        "  DRSTR001.DAT sha256 %s" % result["files"]["DRSTR001.DAT"],
        "  tiles (smallest %d of %d):" % (len(result["tiles"]), result["tile_count_all"]),
    ]
    for name, info in result["tiles"].items():
        out.append("    %s %d B sha256 %s" % (name, info["size"], info["sha256"]))
        out.append("      dirs=%d zlib_streams=%d" % (info["dirs"], info["zlib_streams"]))
    out.append("  %-22s %-4s %-12s %-16s %s" % (
        "table", "type", "fits/total", "informative", "degenerate/note"))
    for t in result["tables"]:
        out.append("  %-22s %-4s %-12s %-16s %d%s" % (
            t["table"], t["type"], "%d/%d" % (t["fits"], t["total"]),
            "%d/%d" % (t["informative_fits"], t["informative_total"]),
            t["degenerate"], (" — " + t["note"]) if t["note"] else ""))
        out.append("      unit: %s" % t["unit"])
        out.append("      oracle: %s" % t["oracle"])
        if t.get("by_section"):
            out.append("      by section: %s" % t["by_section"])
    return "\n".join(out)


def selftest() -> int:
    fails = 0

    def chk(cond: bool, msg: str) -> None:
        nonlocal fails
        if cond:
            print("  ok   %s" % msg)
        else:
            print("  FAIL %s" % msg)
            fails += 1

    print("kiwi_types selftest (synthetic values, no vendor data)")
    chk(sws(0x10) == 32 and sws(0) == 0, "SWS reads u16 word count in bytes")
    chk(sws(ABSENT) == ABSENT, "SWS 0xffff is the absent sentinel")
    chk(d_offset(0x12) == 36 and d_offset(ABSENT) == ABSENT,
        "D reads offset words and keeps the sentinel")
    chk(sector_address(0x123456C0) == 0x123456 * 2048 + 0 * 32,
        "SA ignores the two DL flag bits (bits 7..6)")
    chk(sector_address(0x00000100) == 2048,
        "SA = sector 1, word 0 -> byte 2048")
    chk(sector_address(0x0000013F) == 2048 + 0x3F * 32,
        "SA = sector 1, word 63 -> byte 2048+2016")
    pos = score("synthetic-positive", "SWS", "words", "bytes",
                [(0x10, 32), (0x11, 34), (0x12, 36)])
    chk(pos["fits"] == 3 and pos["total"] == 3 and pos["degenerate"] == 0,
        "positive control: three SWS words fit")
    neg = score("synthetic-negative", "SWS", "words", "bytes",
                [(0x10, 32), (0x11, 35), (0x12, 36)])
    chk(neg["fits"] == 2 and neg["total"] == 3,
        "negative control: one shifted value is a misfit")
    sa_plain = score("synthetic-sa", "SA", "plain byte offsets", "the same bytes",
                     [(0, 0), (0x1234, 0x1234), (0x12345678, 0x12345678)])
    chk(sa_plain["fits"] == 1 and sa_plain["degenerate"] == 1
        and sa_plain["informative_fits"] == 0,
        "SA misfits plain byte offsets; only the zero is degenerate")
    chk(score("synthetic-absent", "D", "words", "bytes", [(ABSENT, 0)])["fits"] == 0,
        "D sentinel does not decode to byte 0")
    print("kiwi_types selftest: OK (%d failure(s))" % fails)
    return 0 if fails == 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true",
                    help="run synthetic decode checks (no vendor data)")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("selftest", help="synthetic decode checks (no vendor data)")
    c = sub.add_parser("census", help="count fits/total per documented table on a card tree")
    c.add_argument("root", type=Path, help="extracted card tree with MAPAL001, REFER001, MMAIN001, DRSTR001")
    c.add_argument("--tiles", type=int, default=3, help="number of smallest B*.DAT tiles to parse (default 3)")
    c.add_argument("--json", dest="json_path", default=None,
                   help="write the full result as JSON to PATH, or '-' for stdout")
    args = ap.parse_args(argv)
    if args.selftest or args.cmd == "selftest":
        return selftest()
    if args.cmd is None:
        ap.error("a command is required (census), or use --selftest")
    try:
        result = census(args.root, args.tiles, args.json_path)
    except (ValueError, OSError) as exc:
        print("kiwi_types: %s" % exc, file=sys.stderr)
        return 1
    blob = json.dumps(result, indent=2, sort_keys=True)
    if args.json_path == "-":
        print(blob)
    else:
        print(render(result))
        if args.json_path:
            Path(args.json_path).write_text(blob + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
