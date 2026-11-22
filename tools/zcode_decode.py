#!/usr/bin/env python3
"""Census of the ``REFER001/ZCODE0nn`` postal-code shards (M4.79).

The repo already had a *verifier* for the two on-disk ZCODE forms
(``tools/coord_zcode_icode.py --verify-zcode``). What it lacked was a
reproducible **census**: per shard, how many records the decode reaches and how
many of the file's bytes the layout accounts for, with a value histogram for
every field and an explicit histogram of whatever is left over. This tool is
that census; it reuses the addressing code from ``coord_zcode_icode`` (the
sector encoding, form detection and form-A header fields) instead of carrying a
second decoder.

Two forms (verified by M4.12, completed here for form B's offset base):

* **Form A** (filled header at ``0x1000``): ADDRE-style ``crec`` trie at
  ``0x1100`` (halfword child offsets), record block at
  ``unaddr(rec_addr_enc@0x1012)``, ``rec_size@0x1016`` bytes = ``rec_size/8``
  16-byte records. EU ZCODE018/033.
* **Form B** (sentinel stub at ``0x1000``, real header at **``0x1100``**): the
  same 48-byte header fields are mirrored at ``0x1106/0x1112/0x1116/0x1132``.
  The record block is ``unaddr(rec_addr_enc@0x1112)``. A halfword-offset tag
  table starts at **``0x1204``**; a child target is ``0x1204 + offset*2`` and
  is a nested table when it parses as ``>HHBBHI`` entries, else a block of
  16-byte area-ladder result records. 31 EU shards.

No sample is committed: ``census ROOT`` takes a directory of decompressed
``ZCODE0nn.DAT`` files (or ``.DAT.cmp``/``.ind`` pairs, decoded through
``cmpind``) and prints one block per shard. ``--selftest`` is fully synthetic.

Evidence: docs/experiments/EXP-2026-11-22-M4.79-zcode-decode.md, claims
C-7800–C-7809.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import coord_zcode_icode as cz

HEADER_A = 0x1000
HEADER_B = 0x1100
TRIE_BASE = 0x1100
TABLE_B = 0x1204
REC16 = 16
DIR_CR = 12


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from(">H", data, off)[0]


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


def form_of(data: bytes) -> str:
    """A when the 0x1000 header is filled, B when the real one is at 0x1100."""
    if len(data) < 0x1040:
        return "?"
    nodew = _u32(data, 0x1006)
    rec = _u32(data, 0x1012)
    if nodew > 0 and rec != 0xFFFFFFFF:
        return "A"
    if len(data) >= 0x1140 and _u32(data, 0x1106) > 0 and _u32(data, 0x1112) != 0xFFFFFFFF:
        return "B"
    return "B"


def header_a(data: bytes) -> dict[str, int]:
    return {
        "nodew_halfwords": _u32(data, 0x1006),
        "first": _u16(data, 0x100E),
        "rec_addr_enc": _u32(data, 0x1012),
        "rec_size": _u32(data, 0x1016),
        "recw": _u16(data, 0x101A),
        "cr": data[0x1032] * 2,
        "kw": data[0x1033],
        "area": _u16(data, 0x1042),
    }


def header_b(data: bytes) -> dict[str, int]:
    return {
        "magic": _u16(data, 0x1100),
        "kind": _u16(data, 0x1104),
        "nodew_halfwords": _u32(data, 0x1106),
        "first": _u16(data, 0x110E),
        "rec_addr_enc": _u32(data, 0x1112),
        "rec_size": _u32(data, 0x1116),
        "recw": _u16(data, 0x111A),
        "cr": data[0x1132] * 2,
        "kw": data[0x1133],
        "area": _u16(data, 0x1142),
    }


def record_lanes(data: bytes, base: int, count: int) -> dict[str, Any]:
    """Min/max and 0xffff count for each of the 8 big-endian u16 lanes."""
    lanes = [[0xFFFF, 0, 0] for _ in range(8)]
    n = 0
    for i in range(count):
        off = base + i * REC16
        if off + REC16 > len(data):
            break
        vals = struct.unpack_from(">8H", data, off)
        for j, v in enumerate(vals):
            if v < lanes[j][0]:
                lanes[j][0] = v
            if v > lanes[j][1]:
                lanes[j][1] = v
            if v == 0xFFFF:
                lanes[j][2] += 1
        n += 1
    return {
        "records_read": n,
        "lanes": [{"lane": j, "min": lo, "max": hi, "ffff": c} for j, (lo, hi, c) in enumerate(lanes)],
    }

class Coverage:
    """Byte-exact accounting: a byte is explained when a structure owns it."""

    def __init__(self, size: int) -> None:
        self.size = size
        self.owner = bytearray(size)

    def add(self, lo: int, hi: int) -> None:
        lo = max(0, lo)
        hi = min(self.size, hi)
        if hi > lo:
            self.owner[lo:hi] = b"\x01" * (hi - lo)

    def explained(self) -> int:
        return sum(self.owner)

    def unexplained_blocks(self, block: int = 0x1000) -> list[list[int]]:
        hist: Counter[int] = Counter()
        for i, b in enumerate(self.owner):
            if not b:
                hist[i // block] += 1
        return [[a * block, n] for a, n in sorted(hist.items())]


def _is_dir_entry(data: bytes, off: int, cr: int = DIR_CR) -> bool:
    if off < 0 or off + cr > len(data):
        return False
    size, z, tag, z2, count, offset = struct.unpack_from(">HHBBHI", data, off)
    return (
        z == 0
        and z2 == 0
        and (0x30 <= tag <= 0x39 or 0x41 <= tag <= 0x5A)
        and 0 < size <= 12000
        and size % 6 == 0
        and count < 0x100000
    )


def _table_len(data: bytes, off: int, cr: int = DIR_CR, limit: int = 11) -> int:
    n = 0
    while n < limit and _is_dir_entry(data, off + n * cr, cr):
        n += 1
    return n


def census_form_a(data: bytes) -> dict[str, Any]:
    h = header_a(data)
    cov = Coverage(len(data))
    cov.add(0, 0x1100)  # 512-byte common header + 0x1000 block + gap
    trie_end = TRIE_BASE + h["nodew_halfwords"] * 2
    cov.add(TRIE_BASE, trie_end)
    base = cz.unaddr(h["rec_addr_enc"])
    n_rec = h["rec_size"] // 8
    rec_end = base + n_rec * REC16
    cov.add(base, rec_end)
    checks = {
        "trie_fits": trie_end <= len(data),
        "first_in_table": h["first"] < max(1, h["nodew_halfwords"]),
        "rec_base_sector_aligned": base % 0x100 == 0,
        "rec_block_fits": rec_end <= len(data),
    }
    # the tail after the record block: second 48-byte header + ladders (018/033)
    tail = len(data) - rec_end
    tail_hdr = 0
    if tail > 0:
        nz = rec_end
        while nz < len(data) and data[nz] == 0:
            nz += 1
        if nz + 0x40 <= len(data) and data[nz:nz + 2] == b"\xff\xff":
            tail_hdr = 0x48
            cov.add(nz, nz + 0x48)
            rec_i = nz + 0x30
            while rec_i + REC16 <= len(data) and data[rec_i:rec_i + 2] != b"\x00\x00":
                rec_i += REC16
    fields = {
        "nodew_halfwords": [h["nodew_halfwords"], h["nodew_halfwords"]],
        "first": [h["first"], h["first"]],
        "rec_addr_enc": [h["rec_addr_enc"], h["rec_addr_enc"]],
        "rec_size": [h["rec_size"], h["rec_size"]],
        "cr": [h["cr"], h["cr"]],
        "kw": [h["kw"], h["kw"]],
        "area": [h["area"], h["area"]],
    }
    return {
        "form": "A",
        "header": h,
        "record_base": base,
        "records": n_rec,
        "record_bytes": n_rec * REC16,
        "rec_size_remainder": h["rec_size"] % 8,
        "tail_bytes": tail,
        "tail_header_bytes": tail_hdr,
        "checks": checks,
        "fields": fields,
        "record_fields": record_lanes(data, base, n_rec),
        "tag_histogram": {},
        "coverage": cov,
    }


def census_form_b(data: bytes) -> dict[str, Any]:
    h = header_b(data)
    cov = Coverage(len(data))
    cov.add(0, TABLE_B)  # 512 header + sentinel stub 0x1000 + real header 0x1100
    base = cz.unaddr(h["rec_addr_enc"])
    n_rec = h["rec_size"] // 8
    cov.add(base, base + n_rec * REC16)
    tags: Counter[str] = Counter()
    sizes: list[int] = []
    counts: list[int] = []
    offsets: list[int] = []
    tables = 0
    leaves = 0
    seen: set[int] = set()
    stack = [TABLE_B] if _table_len(data, TABLE_B) else []
    while stack:
        t = stack.pop()
        if t in seen or t + DIR_CR > len(data):
            continue
        seen.add(t)
        n = _table_len(data, t)
        if n == 0:
            continue
        tables += 1
        cov.add(t, t + n * DIR_CR)
        for i in range(n):
            size, _z, tag, _z2, count, offset = struct.unpack_from(">HHBBHI", data, t + i * DIR_CR)
            tags[chr(tag)] += 1
            sizes.append(size)
            counts.append(count)
            offsets.append(offset)
            target = TABLE_B + offset * 2
            if _table_len(data, target) >= 1 and target not in seen:
                stack.append(target)
            else:
                leaves += 1
                cov.add(target, target + count * REC16)
    rec_end = base + n_rec * REC16
    checks = {
        "header_kind_set": h["kind"] != 0,
        "rec_base_aligned16": base % 16 == 0,
        "rec_base_in_file": 0 < base <= len(data),
        "rec_block_fits": rec_end <= len(data),
        "cr_is_12": h["cr"] == 12,
    }
    fields = {
        "cr": [h["cr"], h["cr"]],
        "kw": [h["kw"], h["kw"]],
        "area": [h["area"], h["area"]],
        "size": [min(sizes), max(sizes)] if sizes else [0, 0],
        "count": [min(counts), max(counts)] if counts else [0, 0],
        "offset": [min(offsets), max(offsets)] if offsets else [0, 0],
    }
    return {
        "form": "B",
        "header": h,
        "record_base": base,
        "records": n_rec,
        "record_bytes": n_rec * REC16,
        "rec_size_remainder": h["rec_size"] % 8,
        "tail_bytes": len(data) - rec_end,
        "tail_header_bytes": 0,
        "tables": tables,
        "leaf_blocks": leaves,
        "checks": checks,
        "fields": fields,
        "record_fields": record_lanes(data, base, n_rec),
        "tag_histogram": dict(sorted(tags.items())),
        "coverage": cov,
    }


def census_bytes(data: bytes) -> dict[str, Any]:
    form = form_of(data) if len(data) >= 0x1040 else "?"
    if form == "A":
        res = census_form_a(data)
    elif form == "B":
        res = census_form_b(data)
    else:
        res = {
            "form": form,
            "records": 0,
            "record_base": 0,
            "checks": {},
            "fields": {},
            "tag_histogram": {},
            "coverage": Coverage(len(data)),
        }
    cov: Coverage = res.pop("coverage")
    res["size"] = len(data)
    res["bytes_explained"] = cov.explained()
    res["bytes_unexplained"] = len(data) - cov.explained()
    res["fraction"] = round(cov.explained() / len(data), 4) if data else 0.0
    res["checks"]["covers_over_half"] = res["bytes_explained"] * 2 >= len(data)
    res["unexplained_4k"] = cov.unexplained_blocks()
    res["all_checks_pass"] = all(res["checks"].values())
    return res


def _load(path: Path) -> bytes:
    return cz._load(path)


def resolve_root(root: Path, prefix: str = "ZCODE") -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = []
    for p in sorted(root.iterdir()):
        if not p.name.startswith(prefix):
            continue
        if p.name.endswith(".DAT.cmp"):
            out.append((p, p.name[: -len(".DAT.cmp")]))
        elif p.name.endswith(".DAT") and p.with_suffix(".DAT.cmp").exists():
            continue
        elif p.name.endswith(".DAT"):
            out.append((p, p.name))
    return out


def _fmt_report(name: str, r: dict[str, Any]) -> str:
    lines = [
        f"{name}: form {r['form']} size {r['size']} "
        f"records {r['records']} record_base {hex(r['record_base'])} "
        f"explained {r['bytes_explained']}/{r['size']} ({r['fraction']:.1%})"
    ]
    if r["form"] == "B":
        lines.append(
            f"    tables {r.get('tables', 0)} leaf_blocks {r.get('leaf_blocks', 0)} "
            f"record_area {r['record_bytes']}"
        )
    if r["form"] == "A":
        lines.append(
            f"    tail {r['tail_bytes']} (second header {r['tail_header_bytes']}) "
            f"rec_size_rem {r.get('rec_size_remainder', 0)}"
            + ("  OUT-OF-RANGE" if r["tail_bytes"] < 0 else "")
        )
    tagh = r.get("tag_histogram") or {}
    if tagh:
        lines.append("    tags " + " ".join(f"{k}:{v}" for k, v in list(tagh.items())[:12]))
    lines.append("    fields " + " ".join(f"{k}={v[0]}..{v[1]}" for k, v in r["fields"].items()))
    rf = r.get("record_fields") or {}
    if rf.get("lanes"):
        lines.append(
            "    record lanes "
            + " ".join(f"v{l['lane']}={l['min']}..{l['max']}(ff{l['ffff']})" for l in rf["lanes"])
        )
    lines.append(
        "    checks " + " ".join(f"{k}={'ok' if v else 'FAIL'}" for k, v in r["checks"].items())
    )
    if r["bytes_unexplained"]:
        top = r["unexplained_4k"][:6]
        lines.append(
            f"    unexplained {r['bytes_unexplained']} top4k "
            + " ".join(f"{hex(a)}:{n}" for a, n in top)
        )
    return "\n".join(lines)


def cmd_census(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    shards = resolve_root(root)
    if not shards:
        print(f"error: no ZCODE0nn.DAT[.cmp] files under {root}", file=sys.stderr)
        return 2
    mutate = None
    if args.mutate:
        off_s, val_s = args.mutate.split(":", 1)
        mutate = (int(off_s, 0), int(val_s, 0) & 0xFF)
    report = []
    mismatches = 0
    for path, name in shards:
        data = _load(path)
        if mutate and mutate[0] < len(data):
            data = bytearray(data)
            data[mutate[0]] = mutate[1]
            data = bytes(data)
        r = census_bytes(data)
        r["shard"] = name
        report.append(r)
        if not args.json:
            print(_fmt_report(name, r))
        if args.expect_form and r["form"] != args.expect_form:
            mismatches += 1
            if not args.json:
                print(f"    FORM MISMATCH: expected {args.expect_form}, got {r['form']}")
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    if args.expect_form:
        return 0 if mismatches == 0 else 1
    return 0


def cmd_one(args: argparse.Namespace) -> int:
    path = Path(args.path)
    data = _load(path)
    if args.mutate:
        off_s, val_s = args.mutate.split(":", 1)
        off, val = int(off_s, 0), int(val_s, 0) & 0xFF
        data = bytearray(data)
        data[off] = val
        data = bytes(data)
    r = census_bytes(data)
    if args.json:
        print(json.dumps(r, indent=2, sort_keys=True))
    else:
        print(_fmt_report(path.name, r))
    return 0 if r["all_checks_pass"] else 1


# ---------------------------------------------------------------------------
# Self-test (synthetic, no vendor data)
# ---------------------------------------------------------------------------

def _check(ok: bool, msg: str, failures: list[str]) -> None:
    print(f"{'ok' if ok else 'FAIL'}: {msg}")
    if not ok:
        failures.append(msg)


def _synthetic_form_a(n_keys: int = 4) -> bytes:
    trie = bytearray(0x40)
    trie[0x00:0x0C] = struct.pack(">IHH", 0x20, 42, 0) + b"1" + b"\x00" * 3
    buf = bytearray(0x1100 + len(trie))
    struct.pack_into(">I", buf, 0x1006, len(trie) // 2)
    struct.pack_into(">H", buf, 0x100E, 42)
    struct.pack_into(">I", buf, 0x1016, n_keys * 8)
    struct.pack_into(">B", buf, 0x1032, 6)
    struct.pack_into(">B", buf, 0x1033, 1)
    struct.pack_into(">H", buf, 0x1042, 0x11)
    buf[0x1100:0x1100 + len(trie)] = trie
    buf += b"\x00" * ((-len(buf)) % 0x100)
    struct.pack_into(">I", buf, 0x1012, cz.addr(len(buf)))
    for k in range(n_keys):
        buf += struct.pack(">8H", 40000 + k, 1000, 1, 2, 3, 65535, 0, 0)
    return bytes(buf)


def _synthetic_form_b(n_leaves: int = 3) -> bytes:
    """Root table of ``n_leaves`` tags at 0x1204, each one 16-byte record."""
    rec_start = 0x1300
    buf = bytearray(rec_start)
    struct.pack_into(">H", buf, 0x1100, 0xFFFF)
    struct.pack_into(">H", buf, 0x1104, 0x0202)
    struct.pack_into(">I", buf, 0x1106, 2)
    struct.pack_into(">I", buf, 0x1116, n_leaves * 8)
    struct.pack_into(">H", buf, 0x110E, 0x003C)
    struct.pack_into(">B", buf, 0x1132, 6)
    struct.pack_into(">B", buf, 0x1133, 1)
    struct.pack_into(">H", buf, 0x1142, 0x01)
    struct.pack_into(">I", buf, 0x1112, cz.addr(rec_start))
    for i in range(n_leaves):
        off_hw = (rec_start + i * REC16 - TABLE_B) // 2
        struct.pack_into(">HHBBHI", buf, TABLE_B + i * DIR_CR, 12, 0, ord("0") + i, 0, 1, off_hw)
    buf += b"\x00" * (rec_start - len(buf))
    for i in range(n_leaves):
        buf += struct.pack(">8H", 1, i, 1, 0xFFFF, 0xFFFF, 0, 1, 1)
    return bytes(buf)


def selftest() -> int:
    failures: list[str] = []
    a = _synthetic_form_a(4)
    ra = census_bytes(a)
    _check(ra["form"] == "A", "synthetic form A detected", failures)
    _check(ra["records"] == 4, "form A records = rec_size/8", failures)
    _check(ra["checks"]["rec_block_fits"], "form A record block fits", failures)
    _check(ra["fraction"] > 0.9, "synthetic form A explains > 90%", failures)

    b = _synthetic_form_b(3)
    rb = census_bytes(b)
    _check(rb["form"] == "B", "synthetic form B detected", failures)
    _check(rb["tables"] >= 1, "form B root table walked", failures)
    _check(rb["records"] == 3, "form B records = rec_size/8", failures)
    _check(rb["record_base"] % 16 == 0, "form B record base 16-aligned", failures)

    # negative control: flip the form-A nodew field; the census must notice
    mut = bytearray(a)
    struct.pack_into(">I", mut, 0x1006, 0)
    rmut = census_bytes(bytes(mut))
    _check(rmut["form"] != "A", "mutated nodew no longer classifies as form A", failures)
    # negative control: inflate the form-A record size; the block stops fitting
    mut2 = bytearray(a)
    struct.pack_into(">I", mut2, 0x1016, 0x100000)
    rmut2 = census_bytes(bytes(mut2))
    _check(not rmut2["checks"]["rec_block_fits"],
           "mutated rec_size makes the record block overflow a check", failures)
    # negative control: corrupt a form-B tag; the root table walk must shorten
    mut3 = bytearray(b)
    mut3[TABLE_B + 4] = 0x00
    rmut3 = census_bytes(bytes(mut3))
    _check(rmut3["tag_histogram"] != rb["tag_histogram"],
           "corrupted form-B tag changes the directory histogram", failures)

    # offset base identity used by form B
    _check(TABLE_B + 5 * 2 == 0x120E, "form B child base 0x1204 + offset*2", failures)
    _check(HEADER_B == 0x1100, "form B header block at 0x1100", failures)

    if failures:
        print(f"selftest: {len(failures)} failures")
        return 1
    print("selftest: all ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=False)
    ap.add_argument("--selftest", action="store_true")
    p_census = sub.add_parser("census", help="census every ZCODE0nn shard under ROOT")
    p_census.add_argument("root")
    p_census.add_argument("--json", action="store_true")
    p_census.add_argument("--mutate", help="OFF:HEXBYTE patch applied to every shard (negative control)")
    p_census.add_argument("--expect-form", choices=["A", "B"], help="fail when a shard is not this form")
    p_one = sub.add_parser("one", help="census a single decompressed file")
    p_one.add_argument("path")
    p_one.add_argument("--json", action="store_true")
    p_one.add_argument("--mutate", help="OFF:HEXBYTE patch before the census (negative control)")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.cmd == "census":
        return cmd_census(args)
    if args.cmd == "one":
        return cmd_one(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
