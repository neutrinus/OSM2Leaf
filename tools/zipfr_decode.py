#!/usr/bin/env python3
"""Reproducible structural census of a ``REFER001/ZIPFR001.DAT`` (M4.84).

``ZIPFR001`` is global (not country-sharded).  A decoded file is a common
512-byte header, the shared ``0x200..0xfff`` template, a 10-byte body header at
``0x1000``, a run of fixed 14-byte records and zero padding to EOF.  This tool
walks that layout and counts every byte, so the old ``decode.py zipfr`` claim
(C-137) is reproducible from a committed tool instead of a phrase.

Record (big-endian throughout, as in the rest of ``REFER001``)::

    +0x00 u8   flag       0x00 plain, 0x80 last key letter
    +0x01 u8   0
    +0x02 char key[6]     digits/uppercase/space, zero padded
    +0x08 u8   0
    +0x09 u8   0
    +0x0a u16  group       the 119 distinct values of C-137
    +0x0c u16  mask        plain records only (flagged class-B tail is 0)

``census ROOT`` reads every ``ZIPFR001.DAT.cmp``/``.ind`` pair under ROOT
(card tree) and prints the header, the record count, the per-field value
ranges, the distinct group/mask counts and the bytes explained / total.  The
census says whether the file uses the 14-byte record layout; alternative
strides are tried and reported, not assumed.  ``--card-root`` accepts a card
mount for the cross-card section, which also reports whether the US 2011
``DRSTR001.DAT`` lists a ``ZIPFR001`` entry at all.

Usage:
  python3 tools/zipfr_decode.py census ROOT [--json OUT]
  python3 tools/zipfr_decode.py census ROOT --alt-strides 12,14,16
  python3 tools/zipfr_decode.py census--card-root ROOT --card-root CARD
  python3 tools/zipfr_decode.py --selftest

Read-only; no vendor bytes are written anywhere.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cmpind  # noqa: E402

HEADER_TEXT = 0x180
HEADER = 0x200
TEMPLATE = (0x200, 0x0FFF)
BODY_HEADER = 0x1000
BODY_HEADER_LEN = 0x8
RECORD_BASE = BODY_HEADER + 0x8
RECORD_STRIDE = 14
KEY_LEN = 6
FLAG_PLAIN = 0x00
FLAG_LETTER = 0x80
ALT_STRIDES = (12, 14, 15, 16, 18, 20, 24, 26, 28)
MASK_OFF = 10
GROUP_OFF = 10


class ZipfrError(ValueError):
    pass


def _is_code_byte(c: int) -> bool:
    return c == 0 or 0x20 <= c < 0x7F


def _record_clean(rec: bytes) -> bool:
    if len(rec) < RECORD_STRIDE:
        return False
    if rec[0] not in (FLAG_PLAIN, FLAG_LETTER):
        return False
    return (rec[1] == 0 and rec[8] == 0 and rec[9] == 0
            and all(_is_code_byte(c) for c in rec[2:8]))


def record_count(data: bytes, stride: int = RECORD_STRIDE,
                 base: int = RECORD_BASE) -> int:
    if len(data) < base:
        return 0
    return (len(data) - base) // stride


def records(data: bytes, base: int = RECORD_BASE) -> list[bytes]:
    n = record_count(data, RECORD_STRIDE, base)
    return [data[base + RECORD_STRIDE * k:base + RECORD_STRIDE * (k + 1)]
            for k in range(n)]


def decode_record(rec: bytes) -> dict:
    flag = rec[0]
    key = rec[2:2 + KEY_LEN].split(b"\0")[0].decode("ascii", "replace")
    group = struct.unpack_from(">H", rec, GROUP_OFF)[0]
    mask = struct.unpack_from(">H", rec, MASK_OFF + 2)[0] if flag == FLAG_PLAIN else 0
    return {"flag": flag, "key": key, "group": group, "mask": mask}


def header_text(data: bytes) -> dict:
    text = data[:HEADER_TEXT].decode("utf-16-be", "replace")
    parts = [p for p in text.split("\uffff") if p]
    return {"strings": parts, "raw_180_188": data[0x180:0x188].hex()}


def layout_score(data: bytes, stride: int, base: int) -> float:
    n = record_count(data, stride, base)
    if n <= 0:
        return 0.0
    good = sum(1 for k in range(n) if _record_clean(data[base + stride * k:base + stride * k + stride]))
    return good / n


def alternative_strides(data: bytes, strides=ALT_STRIDES) -> dict:
    out = {}
    for stride in strides:
        best = None
        for base in range(BODY_HEADER, BODY_HEADER + 0x31):
            score = layout_score(data, stride, base)
            if best is None or score > best[0]:
                best = (score, base, record_count(data, stride, base))
        out[stride] = {"clean": round(best[0], 4), "base": best[1], "records": best[2]}
    return out


def record_stats(recs: list[bytes]) -> dict:
    flags = {}
    lengths = {}
    groups = {}
    masks = {}
    keys = set()
    key_sectors = set()
    u32s = set()
    all_code = True
    unclean = []
    letter_holes = []
    flagged_commas = []
    prev_key = None
    far_sector_steps = []
    prev_sector = None
    all_sectors = set()
    all_tail_u32 = set()
    for idx, rec in enumerate(recs):
        all_sectors.add(struct.unpack_from(">H", rec, 4)[0])
        all_tail_u32.add(bytes(rec[10:14]))
        if not _record_clean(rec):
            unclean.append(idx)
            continue
        flags[rec[0]] = flags.get(rec[0], 0) + 1
        key = rec[2:8].split(b"\0")[0]
        lengths[len(key)] = lengths.get(len(key), 0) + 1
        if any(not _is_code_byte(c) for c in rec[2:8]):
            all_code = False
        sector = struct.unpack_from(">H", rec, 4)[0]
        if prev_sector is not None and abs(sector - prev_sector) > 64:
            far_sector_steps.append(idx)
        prev_sector = sector
        keys.add(bytes(rec[2:8]))
        key_sectors.add(bytes(rec[4:6]))
        u32s.add(bytes(rec[10:14]))
        if rec[0] == FLAG_PLAIN:
            g = struct.unpack_from(">H", rec, GROUP_OFF)[0]
            m = struct.unpack_from(">H", rec, MASK_OFF + 2)[0]
            groups[g] = groups.get(g, 0) + 1
            masks[m] = masks.get(m, 0) + 1
        else:
            if rec[1] == 0x2C:
                flagged_commas.append(idx)
            key8 = bytes(rec[2:10]).rstrip(b"\0")
            if prev_key is not None and key8 <= prev_key:
                letter_holes.append(idx)
            prev_key = key8
        if rec[0] == FLAG_PLAIN:
            prev_key = None
    return {
        "flags": {hex(k): v for k, v in sorted(flags.items())},
        "key_lengths": dict(sorted(lengths.items())),
        "distinct_keys": len(keys),
        "key_bytes_all_printable": all_code,
        "distinct_groups": len(groups),
        "distinct_masks": len(masks),
        "distinct_key_sector_b58": len(key_sectors),
        "distinct_u32_b10": len(u32s),
        "distinct_sector_b4_all": len(all_sectors),
        "distinct_u32_b10_all": len(all_tail_u32),
        "unclean": unclean,
        "letter_order_holes": letter_holes,
        "flagged_commas": flagged_commas,
        "far_sector_steps": far_sector_steps,
        "top_groups": [[g, n] for g, n in sorted(groups.items(), key=lambda kv: -kv[1])[:10]],
        "top_masks": [[m, n] for m, n in sorted(masks.items(), key=lambda kv: -kv[1])[:10]],
    }


def body_header(data: bytes, n: int, projection_end: int = 0) -> dict:
    if len(data) < BODY_HEADER + BODY_HEADER_LEN:
        return {}
    words = struct.unpack_from(">4H", data, BODY_HEADER)
    try:
        ascii_code = data[BODY_HEADER + 2:BODY_HEADER + 8].decode("ascii")
    except UnicodeDecodeError:
        ascii_code = None
    return {"bytes": data[BODY_HEADER:BODY_HEADER + BODY_HEADER_LEN].hex(),
            "words": list(words),
            "word2": words[2],
            "word3": words[3],
            "ascii_code": ascii_code,
            "projection_end": projection_end,
            "record_count_matches_word3": words[3] == n,
            "projection_matches_word2": words[2] == projection_end}


def census_blob(data: bytes, alt_strides=ALT_STRIDES) -> dict:
    n = record_count(data)
    recs = records(data)
    header = header_text(data)
    stats = record_stats(recs)
    projection_end = stats["unclean"][0] if stats["unclean"] else n
    bh = body_header(data, n, projection_end)
    record_end = RECORD_BASE + n * RECORD_STRIDE
    tail = data[record_end:]
    template = data[TEMPLATE[0]:TEMPLATE[1] + 1]
    template_kind = "ff" if all(c == 0xFF for c in template) else (
        "00" if all(c == 0 for c in template) else "mixed")
    zero_tail = all(c == 0 for c in tail)
    header_bytes = HEADER
    template_bytes = TEMPLATE[1] + 1 - TEMPLATE[0]
    record_bytes = n * RECORD_STRIDE
    explained = header_bytes + template_bytes + BODY_HEADER_LEN + record_bytes
    if zero_tail:
        explained += len(tail)
    unexplained = len(data) - explained
    plain = stats["flags"].get("0x0", 0)
    letter = stats["flags"].get("0x80", 0)
    return {
        "size": len(data),
        "header": header,
        "template_0x200_0xfff": template_kind,
        "body_header": bh,
        "record_base": RECORD_BASE,
        "record_stride": RECORD_STRIDE,
        "records": n,
        "record_end": record_end,
        "tail_len": len(tail),
        "tail_all_zero": zero_tail,
        "flags": stats["flags"],
        "plain_records": plain,
        "letter_records": letter,
        "key_lengths": stats["key_lengths"],
        "distinct_keys": stats["distinct_keys"],
        "key_bytes_all_printable": stats["key_bytes_all_printable"],
        "unclean_records": stats["unclean"],
        "letter_order_holes": stats["letter_order_holes"],
        "flagged_comma_records": stats["flagged_commas"],
        "far_sector_steps": stats["far_sector_steps"],
        "distinct_groups": stats["distinct_groups"],
        "distinct_masks": stats["distinct_masks"],
        "distinct_key_sector_b58": stats["distinct_key_sector_b58"],
        "distinct_u32_b10": stats["distinct_u32_b10"],
        "distinct_sector_b4_all": stats["distinct_sector_b4_all"],
        "distinct_u32_b10_all": stats["distinct_u32_b10_all"],
        "top_groups": stats["top_groups"],
        "top_masks": stats["top_masks"],
        "bytes_explained": explained,
        "bytes_explained_pct": round(100.0 * explained / len(data), 3),
        "bytes_unexplained": unexplained,
        "header_bytes": header_bytes,
        "template_bytes": template_bytes,
        "record_bytes": record_bytes,
        "tail_bytes": len(tail),
        "alternative_strides": alternative_strides(data, alt_strides) if alt_strides else {},
    }


def _read_pair(cmp_path: Path, ind_path: Path | None) -> bytes:
    blob, _info = cmpind.decode(cmp_path, ind_path)
    return blob


def find_pairs(root: Path) -> list[tuple[Path, Path | None]]:
    root = Path(root)
    if root.is_file():
        return [(root, None)]
    pairs = []
    for cmp_path in sorted(root.rglob("*")):
        if cmp_path.suffix.lower() != ".cmp":
            continue
        if "ZIPFR" not in cmp_path.name.upper():
            continue
        ind = cmp_path.with_suffix(".ind")
        pairs.append((cmp_path, ind if ind.exists() else None))
    db = root / "ZIPFR001.DAT"
    if db.exists():
        pairs.append((db, None))
    return pairs


def cross_card(card_root: Path) -> dict:
    root = Path(card_root)
    refer = root / "REFER001"
    z = refer / "ZIPFR001.DAT"
    out = {"card_root": str(root), "zipfr_exists": z.exists()}
    drstr = root / "DRSTR001.DAT"
    if drstr.exists():
        import drstr as drstr_mod
        try:
            parsed = drstr_mod.parse(drstr.read_bytes())
        except ValueError as exc:
            out["drstr"] = {"error": str(exc)}
            return out
        listing = []
        for node in parsed["nodes"]:
            if node["name"] == "REFER001":
                listing = [e["name"] for e in node["entries"]]
        out["drstr"] = {"refer001_entries": len(listing),
                        "zipfr_listed": any("ZIPFR" in name.upper() for name in listing)}
    return out


def cmd_census(args: argparse.Namespace) -> int:
    root = Path(args.root)
    alt = tuple(int(x) for x in args.alt_strides.split(",")) if args.alt_strides else ()
    pairs = find_pairs(root)
    if not pairs:
        print(f"error: no ZIPFR001 .cmp/.ind pair under {root}", file=sys.stderr)
        return 2
    report = {"root": str(root), "files": [], "cross_card": None}
    for cmp_path, ind_path in pairs:
        blob = _read_pair(cmp_path, ind_path)
        rep = census_blob(blob, alt)
        rep["file"] = str(cmp_path)
        rep["sha256_input"] = _sha256(blob)
        report["files"].append(rep)
        print(f"file              {cmp_path}")
        print(f"  size            {rep['size']} bytes (SHA-256 of decoded bytes {rep['sha256_input'][:16]}…)")
        print(f"  header          {', '.join(rep['header']['strings'])}")
        print(f"  template        {rep['template_0x200_0xfff']} at 0x200..0xfff")
        print(f"  body header     {rep['body_header']['bytes']} words {rep['body_header']['words']} "
              f"ascii {rep['body_header']['ascii_code']} "
              f"word2==projection {rep['body_header']['projection_matches_word2']}")
        print(f"  records         {rep['records']} x {rep['record_stride']} B at 0x{rep['record_base']:x}..0x{rep['record_end']:x}")
        print(f"  flags           {rep['flags']} (plain {rep['plain_records']}, letter {rep['letter_records']})")
        print(f"  key lengths     {rep['key_lengths']}  distinct keys {rep['distinct_keys']}")
        if rep["unclean_records"]:
            print(f"  non-record      {rep['unclean_records']} slots fail the grammar (special marker)")
        if rep["letter_order_holes"]:
            print(f"  letter order    {rep['letter_order_holes']} letter-key inversions")
        print(f"  comma records   {rep['flagged_comma_records']}")
        print(f"  groups          {rep['distinct_groups']} distinct; top {rep['top_groups']}")
        print(f"  masks           {rep['distinct_masks']} distinct; top {rep['top_masks']}")
        print(f"  alt fields      key[4:6] {rep['distinct_key_sector_b58']} distinct; "
              f"u32[10:14] {rep['distinct_u32_b10']} distinct (C-137 names 119); "
              f"all-records sector {rep['distinct_sector_b4_all']}, u32 {rep['distinct_u32_b10_all']}")
        if rep["far_sector_steps"]:
            print(f"  sector jumps    {len(rep['far_sector_steps'])} steps > 64 at records {rep['far_sector_steps'][:5]}")
        print(f"  tail            {rep['tail_len']} B all-zero {rep['tail_all_zero']}")
        print(f"  bytes explained {rep['bytes_explained']}/{rep['size']} = {rep['bytes_explained_pct']} % "
              f"(unexplained {rep['bytes_unexplained']})")
        if alt:
            print(f"  alt strides     {rep['alternative_strides']}")
    if args.card_root:
        cc = cross_card(Path(args.card_root))
        report["cross_card"] = cc
        print(f"cross-card        {cc['card_root']}: ZIPFR001 present {cc['zipfr_exists']}")
        if "drstr" in cc:
            print(f"  DRSTR REFER001  {cc['drstr']}")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n")
    return 0


def _sha256(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def synth_blob(n: int = 8) -> bytes:
    blob = bytearray(0x1000)
    text = "CLARION\uffffHITACHI\uffffCLA-NAVI05-01\uffffFORMAT VERSION X08-02-00"
    raw = text.encode("utf-16-be")
    blob[:len(raw)] = raw
    blob[0x180:0x188] = bytes.fromhex("ffff24ff12c00500")
    blob[0x200:0x1000] = b"\xff" * (0x1000 - 0x200)
    blob[0x1000:0x1008] = bytes.fromhex("0003f064900d0007")
    keys = ["00100", "00101", "12345", "1234-", "9", "AD", "B", "Z"]
    for k, key in enumerate(keys[:n]):
        rec = bytearray(14)
        flag = 0x80 if key in ("AD", "B", "Z") else 0
        rec[0] = flag
        kb = key.encode("ascii")[:KEY_LEN]
        rec[2:2 + len(kb)] = kb
        group = 0x2000 + (k % 4)
        rec[10:12] = struct.pack(">H", group)
        if flag == 0:
            rec[12:14] = struct.pack(">H", 0x80 if key.endswith("5") else 0)
        blob += rec
    blob += b"\0" * 10
    return bytes(blob)


def selftest() -> int:
    fails = []

    def ok(cond: bool, label: str) -> None:
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    blob = synth_blob()
    rep = census_blob(blob)
    ok(rep["records"] == 8, "synthetic: 8 records")
    ok(rep["bytes_unexplained"] == 0, "synthetic: 0 unexplained bytes")
    ok(rep["tail_all_zero"], "synthetic: zero tail recognised")
    ok(rep["header"]["strings"][0] == "CLARION", "synthetic: UTF-16BE header string")
    ok(rep["body_header"]["words"] == [3, 0xF064, 0x900D, 7], "synthetic: body header words")
    ok(rep["body_header"]["record_count_matches_word3"] is False, "synthetic: word3 is not the record count")
    ok(rep["plain_records"] == 5 and rep["letter_records"] == 3, "synthetic: flag histogram")
    ok(rep["distinct_groups"] == 4, "synthetic: 4 distinct groups (C-137 says 119 on EU)")
    ok(rep["distinct_key_sector_b58"] == 3, "synthetic: key[4:6] distinct count")
    ok(rep["distinct_u32_b10"] == 5, "synthetic: u32[10:14] distinct count")
    ok(rep["key_bytes_all_printable"], "synthetic: key bytes printable")
    ok(rep["alternative_strides"][14]["clean"] == 1.0, "synthetic: stride 14 scores 1.0")
    ok(rep["alternative_strides"][16]["clean"] < 1.0, "synthetic: stride 16 scores < 1.0")

    dec = decode_record(blob[RECORD_BASE:RECORD_BASE + RECORD_STRIDE])
    ok(dec == {"flag": 0, "key": "00100", "group": 0x2000, "mask": 0}, "synthetic: record 0 decode")

    bad = bytearray(blob)
    bad[RECORD_BASE + 2] = 0x01
    badrep = census_blob(bytes(bad))
    ok(badrep["unclean_records"] == [0], "negative: a mutated key byte is detected as non-record")

    bad = bytearray(blob)
    struct.pack_into(">H", bad, RECORD_BASE + 12, 0xFFFF)
    badrep = census_blob(bytes(bad))
    ok(badrep["distinct_masks"] == rep["distinct_masks"] + 1,
       "negative control: a mutated mask byte adds a distinct mask (layout still walks)")

    print("zipfr_decode selftest: " + ("OK" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("census", help="header, records, fields and bytes explained per ZIPFR001 file")
    c.add_argument("root", help="card tree (REFER001 dir) or one .cmp file")
    c.add_argument("--json", help="write the report as JSON")
    c.add_argument("--alt-strides", default="", help="comma-separated strides to compare, e.g. 12,14,16")
    c.add_argument("--card-root", help="card mount; report cross-card presence and DRSTR listing")
    c.set_defaults(func=cmd_census)
    return ap


def main(argv=None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not getattr(args, "func", None):
        ap.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
