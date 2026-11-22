#!/usr/bin/env python3
"""Decode ``REFER001/INTER0nn.DAT`` and count how much of each file is explained.

The established part of the format is the **12-byte big-endian record table**
at ``0x1108`` (M3.16, C-2215/C-2216, ``tools/inter_table.py``): an 8-byte
block header, ``u16 key`` records (``0xffff`` = terminator) with the field
shape ``>HHBBHHH`` = ``key, zero(+2), id, flag, length, b8, offset``.
This tool makes that decode reproducible and adds a byte-level census.

Census classes (a byte is counted once, in the first class that reaches it):

* ``header``   -- ``0x000..0x200``, the CLARION UTF-16BE common header;
* ``table``    -- ``0x1108`` block header + records + the ``0xffff`` terminator;
* ``chain``    -- a ``4e 20 00 00`` index chain: magic, ``u32`` halfword
  lengths and the zlib streams they name (each inflated to check it is real);
* ``zpage``    -- a zlib stream at a 0x100-aligned offset that is not inside a
  chain (a compressed blob page);
* ``fill``     -- remaining ``0x00``/``0xff`` bytes (reserved / padding);
* ``unexplained`` -- anything else, reported as a byte histogram and never
  guessed.  The post-table region of 12-byte/6-byte locator elements is the
  part M3.16 left as UNKNOWN (C-2217-C-2219); it is named here, not decoded.

``census ROOT [ROOT2 ...]`` prints, per shard, the record count, the six field
ranges, ``explained / total`` bytes and the unexplained bytes.  Pass both card
trees to get EU and US totals in one run:
``python3 tools/inter_decode.py census <EUROOT> <USROOT>``.
``--mutate-byte OFF`` flips one byte of a single shard as a negative control.

Usage::
  python3 tools/inter_decode.py --selftest
  python3 tools/inter_decode.py census ROOT [ROOT2 ...] [--labels L U] [--json]
  python3 tools/inter_decode.py census ROOT --files INTER001 ... --mutate-byte 0x1112

Read-only; no vendor bytes are written.  Evidence:
docs/experiments/EXP-2026-11-22-M4.81-inter-decode.md, claims C-7820-C-7829.
"""
from __future__ import annotations

import argparse
import collections
import json
import struct
import sys
import zlib
from pathlib import Path
from typing import Any

_TOOLS = str(Path(__file__).resolve().parent)
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import cmpind  # noqa: E402

TABLE_BLOCK = 0x1108
RECORD = struct.Struct(">HHBBHHH")      # key, zero, id, flag, length, b8, offset
TERMINATOR = 0xFFFF
HEADER_END = 0x200
CHAIN_MAGIC = b"\x4e\x20\x00\x00"
ZLIB_MAGIC = b"\x78\x9c"                # the factory streams are all level-6
ZWIN = 1 << 19                          # window for probing a candidate stream


class InterError(ValueError):
    pass


# ---------------------------------------------------------------------------
# header and table
# ---------------------------------------------------------------------------


def header_label(blob: bytes, off: int = 0) -> str:
    """Read the UTF-16BE maker text at ``off`` (refer.md: text only in 0..0x17f)."""
    raw = blob[off:off + 0x40]
    chars = []
    for i in range(0, len(raw) - 1, 2):
        c = struct.unpack_from(">H", raw, i)[0]
        if c in (0, 0xFFFF):
            break
        chars.append(chr(c) if 0x20 <= c < 0x7F else "?")
    return "".join(chars)


def read_table(blob: bytes) -> dict[str, Any]:
    """The 8-byte block header + big-endian 12-byte records at ``0x1108``."""
    if len(blob) < TABLE_BLOCK + 8 + RECORD.size:
        raise InterError("file too short for the INTER table")
    tag, count = struct.unpack_from(">II", blob, TABLE_BLOCK)
    rows = []
    pos = TABLE_BLOCK + 8
    stops = collections.Counter()
    while pos + RECORD.size <= len(blob):
        key, zero, idb, flag, length, b8, offset = RECORD.unpack_from(blob, pos)
        if key == TERMINATOR:
            stops["terminator"] += 1
            pos += RECORD.size
            break
        if zero != 0:
            stops["nonzero_+2"] += 1
            break
        rows.append({"pos": pos, "key": key, "id": idb, "flag": flag,
                     "length": length, "b8": b8, "offset": offset})
        pos += RECORD.size
    else:
        stops["no_terminator"] += 1
    return {"tag": tag, "count_field": count, "records": rows,
            "start": TABLE_BLOCK, "end": pos, "stops": dict(stops)}


def field_ranges(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for name in ("key", "id", "flag", "length", "b8", "offset"):
        vals = [r[name] for r in rows]
        out[name] = {"min": min(vals) if vals else -1,
                     "max": max(vals) if vals else -1,
                     "nonzero": sum(1 for v in vals if v)}
    return out


# ---------------------------------------------------------------------------
# compressed page / index-chain span discovery
# ---------------------------------------------------------------------------


def _zlib_end(blob: bytes, start: int) -> int | None:
    """End offset of the zlib stream at ``start``, or None if it does not end."""
    if blob[start:start + 2] != ZLIB_MAGIC:
        return None
    window = memoryview(blob)[start:start + ZWIN]
    try:
        d = zlib.decompressobj()
        d.decompress(window)
    except zlib.error:
        return None
    if not d.eof:
        return None
    return start + len(window) - len(d.unused_data)


def add_spans(blob: bytes, covered: bytearray) -> dict[str, int]:
    """Mark index chains and standalone zlib pages; return their byte counts."""
    n = len(blob)
    view = memoryview(blob)
    chains = pages = infl = 0

    # Standalone zlib streams (0x100-aligned).  Streams inside a 4e20 chain are
    # counted as chain bytes; we still probe every 78 9c, so a chain whose
    # length table is malformed cannot hide its compressed bytes.
    pos = 0
    stream_ends: list[tuple[int, int, int]] = []
    while True:
        i = blob.find(ZLIB_MAGIC, pos)
        if i < 0:
            break
        end = _zlib_end(blob, i)
        if end is not None and end > i + 2:
            infl += end - i                       # refined below for chains
            stream_ends.append((i, end, 0))
            pos = end
        else:
            pos = i + 1

    # Index chains: 4e 20 00 00 | u32 halfword lengths[n] | n zlib streams.
    pos = 0
    chain_ranges: list[tuple[int, int]] = []
    while True:
        i = blob.find(CHAIN_MAGIC, pos)
        if i < 0:
            break
        nlen = 1
        while i + 4 + 4 * nlen < n and blob[i + 4 + 4 * nlen] != 0x78:
            nlen += 1
        if nlen > 1 << 16 or i + 4 + 4 * nlen > n:
            pos = i + 1
            continue
        try:
            lens = struct.unpack_from(f">{nlen}I", blob, i + 4)
        except struct.error:
            pos = i + 1
            continue
        p = i + 4 + 4 * nlen
        ok = True
        for L in lens:
            if p + 2 * L > n:
                ok = False
                break
            try:
                d = zlib.decompressobj()
                d.decompress(view[p:p + 2 * L])
                if not d.eof:
                    ok = False
                    break
            except zlib.error:
                ok = False
                break
            p += 2 * L
        if ok and p > i:
            chain_ranges.append((i, p))
            pos = p
        else:
            pos = i + 1

    for a, b in chain_ranges:
        covered[a:b] = b"\x01" * (b - a)
        chains += b - a
    for a, b, _ in stream_ends:
        # chains are marked first; a stream starting inside one is a chain byte
        if covered[a] == 0:
            covered[a:b] = b"\x01" * (b - a)
            pages += b - a

    return {"chain_bytes": chains, "page_bytes": pages,
            "streams": len(stream_ends), "chains": len(chain_ranges)}


# ---------------------------------------------------------------------------
# census
# ---------------------------------------------------------------------------


def census_blob(blob: bytes, want_residual: bool = True) -> dict[str, Any]:
    n = len(blob)
    covered = bytearray(n)
    head_end = min(HEADER_END, n)
    covered[0:head_end] = b"\x01" * head_end
    table = read_table(blob)
    covered[TABLE_BLOCK:table["end"]] = b"\x01" * (table["end"] - TABLE_BLOCK)
    marks = add_spans(blob, covered)

    pos = 0
    fill = 0
    residual: collections.Counter = collections.Counter()
    residual_runs: list[tuple[int, int, int]] = []
    while True:
        a = covered.find(0, pos)
        if a < 0:
            break
        b = covered.find(1, a)
        if b < 0:
            b = n
        chunk = blob[a:b]
        f = chunk.count(0) + chunk.count(0xFF)
        fill += f
        if want_residual and f != len(chunk):
            residual.update(c for c in chunk if c not in (0, 0xFF))
            residual_runs.append((a, b, len(chunk) - f))
        pos = b

    structured = sum(covered)
    explained = structured + fill
    return {
        "size": n,
        "label": header_label(blob),
        "table": table,
        "records": len(table["records"]),
        "ranges": field_ranges(table["records"]),
        "marks": marks,
        "structured_bytes": structured,
        "fill_bytes": fill,
        "explained_bytes": explained,
        "explained_pct": round(100.0 * explained / n, 3),
        "unexplained_bytes": n - explained,
        "residual": dict(residual.most_common(12)),
        "residual_runs": residual_runs[:8],
    }


# ---------------------------------------------------------------------------
# files and CLI
# ---------------------------------------------------------------------------


def find_shards(root: Path, only: list[str] | None = None) -> list[tuple[str, Path, Path | None]]:
    base = root / "REFER001" if (root / "REFER001").is_dir() else root
    by_upper = {p.name.upper(): p for p in base.iterdir()}
    pairs: dict[str, tuple[Path, Path | None]] = {}
    for up, p in sorted(by_upper.items()):
        if not up.startswith("INTER") or ".DAT" not in up:
            continue
        if up.endswith(".DAT.CMP"):
            stem = up[:-8]
            ind = by_upper.get(stem + ".DAT.IND")
            pairs[stem] = (p, ind)
        elif up.endswith(".DAT.IND"):
            continue
        elif up.endswith(".DAT"):
            stem = up[:-4]
            pairs.setdefault(stem, (p, None))
    out = [(name, cmp_path, ind) for name, (cmp_path, ind) in sorted(pairs.items())]
    if only:
        want = {o.upper().replace(".DAT", "") for o in only}
        out = [row for row in out if row[0] in want]
    return out


def load_shard(cmp_path: Path, ind: Path | None) -> bytes:
    if cmp_path.suffix == ".cmp" or cmp_path.name.upper().endswith(".DAT.CMP"):
        if ind is None or not ind.exists():
            raise InterError(f"missing .ind for {cmp_path}")
        blob, _ = cmpind.decode(cmp_path, ind)
        return blob
    return cmp_path.read_bytes()


def auto_label(root: Path, index: int) -> str:
    parts = [p.lower() for p in root.parts]
    if any("us" in p for p in parts):
        return "US"
    if any("eu" in p for p in parts):
        return "EU"
    return f"ROOT{index + 1}"


def print_census(root: Path, label: str, rows: list[dict[str, Any]], total: dict[str, Any]) -> None:
    print(f"== {label}  {root}  shards={len(rows)}")
    for r in rows:
        rg = r["ranges"]
        print(f"  {r['file']:12} {r['size']:>10,} B  rec={r['records']:>3}  "
              f"key={rg['key']['min']:#x}..{rg['key']['max']:#x}  "
              f"id={rg['id']['min']:#x}..{rg['id']['max']:#x}  "
              f"len={rg['length']['min']:#x}..{rg['length']['max']:#x}  "
              f"off={rg['offset']['min']:#x}..{rg['offset']['max']:#x}  "
              f"explained={r['explained_pct']:6.2f}%")
    print(f"  TOTAL {label}: {total['files']} shards, {total['records']:,} records, "
          f"{total['size']:,} B")
    print(f"    header={total['header']:,}  table={total['table']:,}  "
          f"chain={total['chain']:,}  zpage={total['page']:,}  fill={total['fill']:,}  "
          f"structured={total['structured']:,}")
    print(f"    explained={total['explained']:,}/{total['size']:,} B = {total['explained_pct']}%  "
          f"unexplained={total['unexplained']:,} B ({total['unexplained_pct']}%)")
    print(f"    unexplained byte histogram: {total['residual']}")
    rg = total["ranges"]
    for name in ("key", "id", "flag", "length", "b8", "offset"):
        print(f"    {name:<7} min={rg[name]['min']:#x} max={rg[name]['max']:#x} "
              f"nonzero={rg[name]['nonzero']:,}/{total['records']:,}")


def empty_total() -> dict[str, Any]:
    return {"files": 0, "records": 0, "size": 0, "header": 0, "table": 0,
            "chain": 0, "page": 0, "fill": 0, "structured": 0, "explained": 0,
            "unexplained": 0, "ranges": {}, "residual": collections.Counter(),
            "_rg": {k: {"min": None, "max": None, "nonzero": 0}
                    for k in ("key", "id", "flag", "length", "b8", "offset")}}


def accumulate(total: dict[str, Any], rep: dict[str, Any], fname: str) -> dict[str, Any]:
    total["files"] += 1
    total["records"] += rep["records"]
    total["size"] += rep["size"]
    total["header"] += min(HEADER_END, rep["size"])
    total["table"] += rep["table"]["end"] - rep["table"]["start"]
    total["chain"] += rep["marks"]["chain_bytes"]
    total["page"] += rep["marks"]["page_bytes"]
    total["fill"] += rep["fill_bytes"]
    total["structured"] += rep["structured_bytes"]
    total["explained"] += rep["explained_bytes"]
    total["unexplained"] += rep["unexplained_bytes"]
    total["residual"].update(rep["residual"])
    for k, v in rep["ranges"].items():
        t = total["_rg"][k]
        t["min"] = v["min"] if t["min"] is None else min(t["min"], v["min"])
        t["max"] = v["max"] if t["max"] is None else max(t["max"], v["max"])
        t["nonzero"] += v["nonzero"]
    return {"file": fname, **rep}


def cmd_census(args) -> int:
    roots = [Path(r) for r in args.roots]
    labels = args.labels or [auto_label(r, i) for i, r in enumerate(roots)]
    if len(labels) != len(roots):
        print("--labels needs one label per root", file=sys.stderr)
        return 2
    all_rows: dict[str, list[dict[str, Any]]] = {}
    grand = empty_total()
    for root, label in zip(roots, labels):
        shards = find_shards(root, args.files)
        if not shards:
            print(f"no INTER shards under {root}", file=sys.stderr)
            return 2
        total = empty_total()
        rows = []
        for name, cmp_path, ind in shards:
            blob = load_shard(cmp_path, ind)
            if args.mutate_byte is not None and len(rows) == 0:
                bad = bytearray(blob)
                off = args.mutate_byte
                bad[off] ^= 0xFF
                print(f"mutate: {name} byte 0x{off:x} {blob[off]:02x} -> {bad[off]:02x}")
                blob = bytes(bad)
            rep = census_blob(blob)
            rows.append(accumulate(total, rep, name))
        total["ranges"] = dict(total["_rg"])
        total["explained_pct"] = round(100.0 * total["explained"] / max(total["size"], 1), 3)
        total["unexplained_pct"] = round(100.0 * total["unexplained"] / max(total["size"], 1), 3)
        total["residual"] = {hex(k): v for k, v in total["residual"].most_common(12)}
        all_rows[label] = rows
        print_census(root, label, rows, total)
        for key in ("files", "records", "size", "header", "table", "chain", "page",
                    "fill", "structured", "explained", "unexplained"):
            grand[key] += total[key]
        grand["residual"].update({int(k, 16): v for k, v in total["residual"].items()})
        for k, v in total["ranges"].items():
            t = grand["_rg"][k]
            t["min"] = v["min"] if t["min"] is None else min(t["min"], v["min"])
            t["max"] = v["max"] if t["max"] is None else max(t["max"], v["max"])
            t["nonzero"] += v["nonzero"]
    grand["ranges"] = dict(grand["_rg"])
    grand["explained_pct"] = round(100.0 * grand["explained"] / max(grand["size"], 1), 3)
    grand["unexplained_pct"] = round(100.0 * grand["unexplained"] / max(grand["size"], 1), 3)
    grand["residual"] = {hex(k): v for k, v in grand["residual"].most_common(12)}
    if len(roots) > 1:
        print("== ALL cards")
        print(f"  shards={grand['files']} records={grand['records']:,} "
              f"size={grand['size']:,} B  explained={grand['explained']:,} "
              f"({grand['explained_pct']}%)  unexplained={grand['unexplained']:,} B")
    if args.json:
        out = {"cards": {lab: [{"file": r["file"], "size": r["size"],
                                "records": r["records"], "ranges": r["ranges"],
                                "explained_pct": r["explained_pct"],
                                "marks": r["marks"]} for r in rows]
                         for lab, rows in all_rows.items()}, "grand": grand}
        Path(args.json).write_text(json.dumps(out, indent=1) + "\n")
    # The tool reports; it does not fail because a shard has a partial decode.
    return 0


# ---------------------------------------------------------------------------
# synthetic selftest
# ---------------------------------------------------------------------------


def synth_blob() -> bytes:
    """A tiny INTER-shaped file: header, table, three records, index chain, fill."""
    buf = bytearray(TABLE_BLOCK)
    buf[0:0x40] = "CLARION".encode("utf-16-be") + b"\xff" * 26
    buf[HEADER_END:TABLE_BLOCK] = b"\xff" * (TABLE_BLOCK - HEADER_END)
    buf += struct.pack(">II", 0x44000001, 3)
    for key, idb, length, offset in ((0x24, 0x42, 0x1C, 0x5AC),
                                     (0x30, 0x43, 0x12, 0x1704),
                                     (0x18, 0x44, 0x1B, 0x17FA)):
        buf += RECORD.pack(key, 0, idb, 0, length, 0, offset)
    buf += RECORD.pack(TERMINATOR, TERMINATOR, 0xFF, 0, 0, 0, 0)
    # a 4e20 chain with one valid zlib stream
    inner = bytes(90)
    stream = zlib.compress(inner)
    buf += CHAIN_MAGIC + struct.pack(">I", max(1, len(stream) // 2))
    buf += stream + b"\x00" * (-len(stream) % 2)
    buf += b"\x00" * (0x100 - len(buf) % 0x100)
    return bytes(buf)


def selftest() -> int:
    fails: list[str] = []

    def ok(cond: bool, msg: str) -> None:
        print(("ok   " if cond else "FAIL ") + msg)
        if not cond:
            fails.append(msg)

    blob = synth_blob()
    rep = census_blob(blob)
    t = rep["table"]
    ok(rep["label"] == "CLARION", f"header label {rep['label']!r}")
    ok(len(t["records"]) == 3, f"three records decoded (got {len(t['records'])})")
    ok(t["stops"].get("terminator") == 1, "run stops at the 0xffff key terminator")
    ok([r["id"] for r in t["records"]] == [0x42, 0x43, 0x44], "ids 0x42/0x43/0x44")
    ok(t["records"][0]["key"] == 0x24 and t["records"][0]["offset"] == 0x5AC,
       "big-endian key/offset at +0/+10")
    rg = rep["ranges"]
    ok(rg["key"]["min"] == 0x18 and rg["key"]["max"] == 0x30, "key range 0x18..0x30")
    ok(rg["id"]["min"] == 0x42 and rg["id"]["max"] == 0x44, "id range")
    ok(rep["marks"]["chains"] == 1, "one 4e20 index chain found")
    ok(rep["explained_pct"] > 90.0,
       f"coverage > 90% on the synthetic file ({rep['explained_pct']}%)")
    ok(rep["unexplained_bytes"] == 0, "synthetic file has no unexplained byte")

    # negative control 1: mutate the u16@+2 invariant of the second record
    bad = bytearray(blob)
    struct.pack_into(">H", bad, TABLE_BLOCK + 8 + RECORD.size + 2, 1)
    bad_rep = census_blob(bytes(bad))
    ok(len(bad_rep["table"]["records"]) == 1,
       f"mutated u16@+2 truncates the walk 3 -> {len(bad_rep['table']['records'])}")
    ok(bad_rep["explained_bytes"] < rep["explained_bytes"],
       f"mutated record lowers explained bytes "
       f"({bad_rep['explained_bytes']} < {rep['explained_bytes']})")

    # negative control 2: corrupt one byte of the zlib stream
    bad2 = bytearray(blob)
    z = blob.find(ZLIB_MAGIC)
    bad2[z + 3] ^= 0xFF
    bad_rep2 = census_blob(bytes(bad2))
    ok(bad_rep2["marks"]["chains"] == 0,
       "corrupt zlib byte invalidates the index chain")

    # negative control 3: a stray non-zero byte is unexplained
    bad3 = bytearray(blob)
    bad3[-1] = 0x5A
    bad_rep3 = census_blob(bytes(bad3))
    ok(bad_rep3["unexplained_bytes"] >= 1,
       "a stray non-fill byte is reported as unexplained")

    print("inter_decode selftest: " + ("OK" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true", help="run synthetic self-test")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("census", help="record/field/byte census of INTER shards")
    c.add_argument("roots", nargs="+", type=Path, help="one or two card trees")
    c.add_argument("--files", nargs="*", help="limit to these INTERnnn shards")
    c.add_argument("--labels", nargs="+", help="label per root (default EU/US from path)")
    c.add_argument("--mutate-byte", type=lambda s: int(s, 0), metavar="OFF",
                   help="negative control: flip byte OFF of the first shard")
    c.add_argument("--json", metavar="OUT", help="write machine-readable report")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "census":
        return cmd_census(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
