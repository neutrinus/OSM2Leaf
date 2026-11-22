#!/usr/bin/env python3
"""Decode ``REFER001/ICODE001.DAT`` and count how much of the file it explains.

The file has two structures (see ``docs/format/coord-zcode-icode.md``):

* the ISO table at ``0x1000`` -- ``u16 size_halfwords``, ``u16 country_count``,
  then ``country_count`` 462-byte entries (``u16 stride``, ``u16 iso``, seven
  64-byte tier-label slots, ten ``0xff`` pad bytes);
* up to eight per-language area-name trees.  Each tree is a chain of
  12-byte-header + name rows (``>HHIHH`` = ``rlen|nosub, nlen, roff, cnt, idx``)
  whose ``roff``/``cnt`` locate the child chain relative to that language's
  country-chain root (halfword offset, halfword size).  A row with ``nlen == 0``
  and ``roff != 0xffffffff`` is a redirect/container row (no name, a child
  chain); a terminator has ``nlen == 0, roff == 0xffffffff, cnt == 0xffff``.

Root pointers are not stored in the refer header (M4.12).  This tool finds the
roots from the data: the earliest country chain is a seed, the tree is walked,
and each remaining large uncovered run contributes its earliest country chain
as another language root, iterated to a fixed point.  That reproduces the EU 8
(including the French chain at ``0xd4b200`` that M4.12 missed) and the US 2
without hard-coded offsets.

``census ROOT`` prints, per card: records, bytes explained / total, per-field
value ranges, and the first country names of each language; unexplained bytes
are reported as a histogram and never guessed.  ``--selftest`` builds a
synthetic two-language ICODE001 and checks the decoder, root discovery and a
mutated-byte negative control (no vendor data).

Evidence: docs/experiments/EXP-2026-11-22-M4.80-icode-census.md,
claims C-7810-C-7819.
"""

from __future__ import annotations

import argparse
import collections
import json
import struct
import sys
from pathlib import Path
from typing import Any

_TOOLS = str(Path(__file__).resolve().parent)
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

ISO_TABLE = 0x1000
ISO_HEADER = 4
ENTRY = 462
NSLOT = 7
SLOT = 0x40
ISO_PAD = 10
TERM = 6
NOSUB = 0x8000
REDIRECT = 0xFFFFFFFF
_ROW = struct.Struct(">HHIHH")


def read_row(data: bytes, off: int) -> tuple[int, int, int, int, int, int]:
    rlen, nlen, roff, cnt, idx = _ROW.unpack_from(data, off)
    return rlen >> 15, rlen & 0x7FFF, nlen, roff, cnt, idx


def row_name(data: bytes, off: int, nlen: int) -> bytes:
    return bytes(data[off + 12 : off + 12 + nlen * 2])


def iso_table(data: bytes) -> dict[str, Any]:
    size_hw, count = struct.unpack_from(">HH", data, ISO_TABLE)
    entries = []
    for i in range(count):
        o = ISO_TABLE + ISO_HEADER + i * ENTRY
        stride, iso = struct.unpack_from(">HH", data, o)
        labels = []
        for s in range(NSLOT):
            raw = bytes(data[o + 4 + s * SLOT : o + 4 + (s + 1) * SLOT])
            txt = raw.split(b"\x00")[0]
            if txt:
                labels.append(txt)
        pad = bytes(data[o + 4 + NSLOT * SLOT : o + ENTRY])
        entries.append(
            {
                "ordinal": i,
                "stride": stride,
                "iso": iso,
                "labels": labels,
                "pad_all_ff": pad == b"\xff" * ISO_PAD,
            }
        )
    return {
        "size_halfwords": size_hw,
        "country_count": count,
        "table_end": ISO_TABLE + ISO_HEADER + count * ENTRY,
        "entries": entries,
    }


def chain_start(data: bytes, a: int, b: int, country_count: int) -> int | None:
    """Earliest offset in [a, b) that begins a ``country_count``-row country chain."""
    n = len(data)
    o = a if a % 2 == 0 else a + 1
    while o + 12 <= b:
        nosub, rlen, nlen, roff, cnt, idx = read_row(data, o)
        if (
            not nosub
            and idx == 0
            and 6 <= rlen <= 0x400
            and 0 < nlen < 64
            and 0 < roff < n // 2
            and 0 < cnt < n // 2
        ):
            p = o
            ok = 0
            for k in range(country_count):
                if p + 12 > n:
                    break
                snosub, srlen, snlen, sroff, scnt, sidx = read_row(data, p)
                if sidx != k or srlen < 6 or not (0 < snlen < 64) or snosub:
                    break
                if sroff >= n or scnt >= n:
                    break
                ok += 1
                p += srlen * 2
            if ok == country_count:
                _, _, tnlen, troff, _, _ = read_row(data, p)
                if tnlen == 0 and troff == REDIRECT:
                    return o
        o += 2
    return None


def walk(data: bytes, covered: bytearray, seen: set[int], base: int, start: int,
         limit: int, depth: int, stats: dict[str, Any]) -> None:
    n = len(data)
    if start in seen:
        stats["revisit"] += 1
        return
    seen.add(start)
    end = min(start + limit, n)
    off = start
    rows = []
    while off + 12 <= end:
        nosub, rlen, nlen, roff, cnt, idx = read_row(data, off)
        if rlen <= 0 or off + rlen * 2 > end:
            stats["bad_rlen"] += 1
            break
        rows.append((nosub, rlen, nlen, roff, cnt, idx))
        covered[off : off + rlen * 2] = b"\x01" * (rlen * 2)
        stats["rows"] += 1
        stats["header_bytes"] += 12
        if nlen:
            stats["name_bytes"] += nlen * 2
            stats["named"] += 1
        else:
            stats["redirects"] += 1
        if idx == len(rows) - 1:
            stats["idx_ok"] += 1
        if roff == REDIRECT and cnt == 0xFFFF:
            stats["terminators"] += 1
            break
        off += rlen * 2
    stats["chains"] += 1
    if depth > stats["maxdepth"]:
        stats["maxdepth"] = depth
    for nosub, rlen, nlen, roff, cnt, idx in rows:
        if roff == REDIRECT or cnt == 0 or nosub:
            continue
        walk(data, covered, seen, base, base + roff * 2, cnt * 2, depth + 1, stats)


def new_stats() -> dict[str, Any]:
    s: dict[str, Any] = collections.Counter()
    s["maxdepth"] = 0
    return s


def discover_roots(data: bytes, iso_end: int, country_count: int) -> tuple[list[int], bytearray]:
    n = len(data)
    covered = bytearray(n)
    roots: list[int] = []
    seen: set[int] = set()
    seed = chain_start(data, iso_end, n, country_count)
    if seed is None:
        return roots, covered
    roots.append(seed)
    walk(data, covered, seen, seed, seed, n, 0, new_stats())
    for _ in range(16):
        best = None
        i = iso_end
        while i < n:
            if covered[i] == 0:
                j = i
                while j < n and covered[j] == 0:
                    j += 1
                if j - i > 32 and sum(1 for b in data[i:j] if b) > 32:
                    if best is None or j - i > best[1]:
                        best = (i, j - i)
                i = j
            else:
                i += 1
        if best is None:
            break
        a, ln = best
        s = chain_start(data, a, a + ln, country_count)
        if s is None:
            break
        roots.append(s)
        walk(data, covered, seen, s, s, n, 0, new_stats())
    return roots, covered


def census_open(data: bytes) -> dict[str, Any]:
    n = len(data)
    iso = iso_table(data)
    iso_end = iso["table_end"]
    roots, covered = discover_roots(data, iso_end, iso["country_count"])

    per_lang = []
    for root in roots:
        st = new_stats()
        walk(data, bytearray(n), set(), root, root, n, 0, st)
        top = []
        off = root
        for _ in range(iso["country_count"]):
            _, _, nlen, _, _, _ = read_row(data, off)
            if nlen == 0:
                break
            top.append(row_name(data, off, nlen).rstrip(b"\x00").decode("latin-1"))
            _, rlen, _, _, _, _ = read_row(data, off)
            off += rlen * 2
        per_lang.append(
            {
                "root": root,
                "rows": st["rows"],
                "chains": st["chains"],
                "named": st["named"],
                "redirects": st["redirects"],
                "terminators": st["terminators"],
                "idx_ok": st["idx_ok"],
                "bad_rlen": st["bad_rlen"],
                "maxdepth": st["maxdepth"],
                "header_bytes": st["header_bytes"],
                "name_bytes": st["name_bytes"],
                "top_names": top,
            }
        )

    covered[ISO_TABLE:iso_end] = b"\x01" * (iso_end - ISO_TABLE)
    explained = sum(covered)
    residual = collections.Counter(data[i] for i in range(n) if not covered[i])
    zero = residual.get(0, 0)
    ff = residual.get(0xFF, 0)
    other = {f"0x{k:02x}": v for k, v in residual.most_common(12) if k not in (0, 0xFF)}

    return {
        "size": n,
        "iso": {
            "size_halfwords": iso["size_halfwords"],
            "country_count": iso["country_count"],
            "table_end": iso_end,
            "stride_values": sorted({e["stride"] for e in iso["entries"]}),
            "iso_values": [e["iso"] for e in iso["entries"]],
            "labels_per_country": [len(e["labels"]) for e in iso["entries"]],
            "pad_all_ff": all(e["pad_all_ff"] for e in iso["entries"]),
        },
        "roots": roots,
        "languages": per_lang,
        "records": sum(l["rows"] for l in per_lang),
        "chains": sum(l["chains"] for l in per_lang),
        "named": sum(l["named"] for l in per_lang),
        "redirects": sum(l["redirects"] for l in per_lang),
        "header_bytes": sum(l["header_bytes"] for l in per_lang),
        "name_bytes": sum(l["name_bytes"] for l in per_lang),
        "explained_bytes": explained,
        "explained_pct": round(100.0 * explained / n, 3),
        "residual_bytes": n - explained,
        "residual_zero": zero,
        "residual_ff": ff,
        "residual_other": other,
    }


def icode_path(root: Path) -> tuple[Path | None, Path | None]:
    for base in (root, root / "REFER001"):
        if base.is_file():
            if base.name == "ICODE001.DAT.cmp":
                return base, Path(str(base)[:-4] + ".ind")
            if base.name == "ICODE001.DAT":
                if Path(str(base) + ".cmp").exists():
                    return Path(str(base) + ".cmp"), Path(str(base) + ".ind")
                return base, None
        if base.is_dir():
            dat = base / "ICODE001.DAT"
            if Path(str(dat) + ".cmp").exists():
                return Path(str(dat) + ".cmp"), Path(str(dat) + ".ind")
            if dat.exists():
                return dat, None
    return None, None


def load(root: Path) -> bytes:
    cmp, ind = icode_path(root)
    if cmp is None:
        raise SystemExit(f"no REFER001/ICODE001.DAT under {root}")
    if cmp.suffix == ".cmp":
        from cmpind import decode

        blob, _ = decode(cmp, ind)
        return blob
    return cmp.read_bytes()


def print_census(root: Path, res: dict[str, Any]) -> None:
    print(f"file:   {root}  ({res['size']} B)")
    iso = res["iso"]
    print(
        f"ISO:    size_halfwords={iso['size_halfwords']} countries={iso['country_count']} "
        f"stride={iso['stride_values']} table_end=0x{iso['table_end']:x} "
        f"pad_all_ff={iso['pad_all_ff']}"
    )
    print(f"        iso_numbers={iso['iso_values']}")
    print(f"        labels_per_country={iso['labels_per_country']}")
    print(f"languages: {len(res['roots'])}")
    for lang in res["languages"]:
        print(
            f"  root 0x{lang['root']:x}  rows={lang['rows']} chains={lang['chains']} "
            f"named={lang['named']} redirect={lang['redirects']} "
            f"terms={lang['terminators']} idx_ok={lang['idx_ok']}/{lang['rows']} "
            f"depth={lang['maxdepth']}"
        )
        print(f"        first country names: {', '.join(lang['top_names'][:4])}")
    print(
        f"records: rows={res['records']} (named {res['named']}, redirect {res['redirects']}), "
        f"chains={res['chains']}, header bytes={res['header_bytes']}, "
        f"name bytes={res['name_bytes']}"
    )
    print(
        f"bytes explained: {res['explained_bytes']} / {res['size']} "
        f"= {res['explained_pct']}%"
    )
    print(
        f"unexplained: {res['residual_bytes']} B "
        f"(zero {res['residual_zero']}, 0xff {res['residual_ff']}, other {res['residual_other']})"
    )


def selftest() -> int:
    fails: list[str] = []

    def check(ok: bool, msg: str) -> None:
        if not ok:
            fails.append(msg)
            print(f"FAIL: {msg}")
        else:
            print(f"ok: {msg}")

    def mkrow(name: bytes, roff: int, cnt: int, idx: int, *,
              nosub: bool = False, term: bool = False) -> bytes:
        if term:
            return struct.pack(">HHIHH", TERM | (NOSUB if nosub else 0), 0,
                               REDIRECT, 0xFFFF, 0xFFFF)
        nm = name + (b"\x00" if len(name) % 2 else b"")
        return struct.pack(">HHIHH", len(nm) // 2 + 6 | (NOSUB if nosub else 0),
                           len(nm) // 2, roff, cnt, idx) + nm

    countries = 2
    iso_end = ISO_TABLE + ISO_HEADER + countries * ENTRY
    buf = bytearray(iso_end)
    struct.pack_into(">HH", buf, ISO_TABLE, countries * ENTRY // 2, countries)
    for i in range(countries):
        o = ISO_TABLE + ISO_HEADER + i * ENTRY
        struct.pack_into(">HH", buf, o, ENTRY // 2, 100 + i)
        lab = b"2=COUNTRY"
        buf[o + 4 : o + 4 + len(lab)] = lab
        buf[o + 4 + NSLOT * SLOT : o + ENTRY] = b"\xff" * ISO_PAD

    child1 = mkrow(b"ALPHA", REDIRECT, 0, 0, nosub=True)
    child2 = mkrow(b"BETA", REDIRECT, 0, 0, nosub=True)
    term = mkrow(b"", 0, 0, 0, term=True)
    row1 = mkrow(b"ONE", 0, 0, 0)
    row2 = mkrow(b"TWO", 0, 0, 1)
    top_len = len(row1) + len(row2) + len(term)
    off1 = top_len // 2
    off2 = (top_len + len(child1)) // 2
    lang = (mkrow(b"ONE", off1, len(child1) // 2, 0)
            + mkrow(b"TWO", off2, len(child2) // 2, 1)
            + term + child1 + child2)
    buf.extend(lang)
    buf.extend(lang)
    data = bytes(buf)

    iso = iso_table(data)
    check(iso["country_count"] == 2 and iso["size_halfwords"] == countries * ENTRY // 2,
          "iso header")
    check(iso["entries"][0]["stride"] == ENTRY // 2 and iso["entries"][0]["iso"] == 100,
          "iso entry")
    check(all(e["pad_all_ff"] for e in iso["entries"]), "iso pad 0xff")
    check(iso["entries"][0]["labels"] == [b"2=COUNTRY"], "iso label")

    _, _, nlen, _, _, _ = read_row(data, iso_end)
    check(nlen == 2 and row_name(data, iso_end, nlen) == b"ONE\x00", "row name decode")

    roots, _ = discover_roots(data, iso["table_end"], iso["country_count"])
    check(len(roots) == 2, f"two roots discovered (got {len(roots)}: {[hex(r) for r in roots]})")

    res = census_open(data)
    check(res["records"] == 10, f"record count 10 (got {res['records']})")
    tree_bytes = res["size"] - iso["table_end"]
    tree_explained = res["explained_bytes"] - (iso["table_end"] - ISO_TABLE)
    check(tree_explained / tree_bytes > 0.95,
          f"tree region explained >95% (got {round(100.0 * tree_explained / tree_bytes, 1)}%)")
    check(res["languages"][0]["top_names"][:2] == ["ONE", "TWO"], "top names decoded")

    bad = bytearray(data)
    struct.pack_into(">H", bad, iso_end, 0x0000)
    res_bad = census_open(bytes(bad))
    check(res_bad["explained_bytes"] < res["explained_bytes"],
          f"mutated byte lowers coverage ({res_bad['explained_bytes']} < {res['explained_bytes']})")

    if fails:
        print(f"selftest: {len(fails)} failures")
        return 1
    print("selftest: all ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true", help="run synthetic self-test")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("census", help="census of a card tree or an ICODE001 file")
    c.add_argument("root", type=Path)
    c.add_argument("--json", action="store_true")
    c.add_argument("--mutate-byte", type=lambda s: int(s, 0), metavar="OFF",
                   help="negative control: flip byte at OFF before the census")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.cmd == "census":
        data = load(args.root)
        res = census_open(data)
        if args.mutate_byte is not None:
            bad = bytearray(data)
            bad[args.mutate_byte] ^= 0xFF
            res_bad = census_open(bytes(bad))
            print(f"mutate: byte 0x{args.mutate_byte:x} 0x{data[args.mutate_byte]:02x}"
                  f" -> 0x{bad[args.mutate_byte]:02x}")
            print(f"  explained {res['explained_bytes']} -> {res_bad['explained_bytes']} "
                  f"({res['explained_pct']}% -> {res_bad['explained_pct']}%)")
            print(f"  records   {res['records']} -> {res_bad['records']}")
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print_census(args.root, res)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
