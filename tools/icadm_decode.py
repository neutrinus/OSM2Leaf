#!/usr/bin/env python3
"""Decode ``REFER001/ICADM0nn.DAT`` and count how much of each shard it explains.

``ICADM0nn`` is the administrative-terminology family.  Decoded, every shard
has three parts (see ``docs/format/refer.md`` section ``ICADM0nn``):

* the common 4096-byte CLARION header, whose slot table at ``0x800`` describes
  the file's frames (``0x000..0x17f`` is UTF-16BE text, ``0x180`` on is binary);
* an ISO/tier-label table at ``0x1000``: ``u16 size_halfwords, u16 count``,
  then ``count`` 462-byte entries.  Each entry is ``u16 stride (0x00e7),
  u16 ISO-3166-1 numeric, 7 x 64-byte tier-label slots, 10 x 0xff pad``.
  The 462-byte stride is stored as 231 *halfwords*; no firmware reader for it
  was located (M3.18 r3, negative), so this census reports the observed stride
  and tag histogram rather than attributing a VA;
* a term blob: runs of ``u16 code, u16 len, u32 flags, u32 value`` followed by
  a text field of ``2*len`` bytes (NUL-padded to whole words).  Two record
  forms are observed: one with a trailing ``u16 value`` (``flags == ffffffff``
  or a small index), one without it; both are counted.  A ``code == 0x0006``
  word with ``len == 0`` separates the sections.  Text is single-byte
  Latin-1/ASCII, not UTF-16 (e.g. ``AUTOHÄNDLER`` stores a lone ``0xc4``).

``census ROOT [ROOT ...]`` walks every ``ICADM0nn`` file under each card tree
(EU2011 and US2011) and prints, per shard: header, ISO table, record count,
per-field value ranges, a few decoded terms, bytes explained / total, and a
histogram of the unexplained bytes.  The stride question is answered with a
histogram; the blob's second record family and the small pre-blob index region
are named, never guessed.  ``--selftest`` builds a synthetic shard and checks
the decoder, the root discovery and a mutated-byte negative control; no vendor
data is used.  ``--mutate-byte OFF`` repeats the negative control on a real
shard.

Evidence: docs/experiments/EXP-2026-11-22-M4.83-icadm-decode.md,
claims C-7840-C-7849.
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

import cmpind  # noqa: E402

HEADER = 0x1000
ISO_BASE = 0x1000
ISO_HEADER = 4
ENTRY = 462
NSLOT = 7
SLOT = 64
ISO_PAD = 10
STRIDE = 0x00E7
PREFIX = 12
MAXLEN = 0x80

SLOT0 = 0x800
NSLOTS = 341
ZERO_SLOTS = range(300, NSLOTS)


def load(path: Path) -> bytes:
    """Decode one shard from a ``.cmp``/``.ind`` pair or a decoded ``.DAT``."""
    if path.suffix == ".cmp":
        blob, _ = cmpind.decode(path)
        return blob
    return path.read_bytes()


def shard_paths(root: Path) -> list[Path]:
    """All ICADM shards under ROOT (a card tree, a REFER001 dir or one file)."""
    if root.is_file():
        return [root] if "ICADM" in root.name.upper() else []
    bases = [root, root / "REFER001"]
    found: dict[str, Path] = {}
    for base in bases:
        if not base.is_dir():
            continue
        for p in sorted(base.glob("ICADM0*.DAT")):
            found.setdefault(p.name, p)
        for p in sorted(base.glob("ICADM0*.DAT.cmp")):
            name = p.name[:-4]
            if name not in found:
                found[name] = p
    return [found[k] for k in sorted(found)]


def parse_header(data: bytes) -> dict[str, Any]:
    """The common CLARION header: text at 0x000 and the slot table at 0x800."""
    head = data[:HEADER]
    texts: dict[str, str] = {}
    for off, n in ((0x000, 8), (0x040, 7), (0x080, 14), (0x0A0, 24),
                   (0x0E0, 22), (0x162, 6)):
        raw = head[off:off + n * 2]
        try:
            val = raw.decode("utf-16-be").rstrip("\uffff").strip("\x00")
        except UnicodeDecodeError:
            val = ""
        if val:
            texts[f"0x{off:03x}"] = val
    slots: dict[int, tuple[int, int]] = {}
    for k in range(NSLOTS):
        addr, blk = struct.unpack_from(">IH", head, SLOT0 + 6 * k)
        default = (0, 0) if k in ZERO_SLOTS else (0xFFFFFFFF, 0)
        if (addr, blk) != default:
            slots[k] = (addr, blk)
    return {"size": len(head), "texts": texts, "slots": slots}


def iso_table(data: bytes) -> dict[str, Any]:
    """The 462-byte-stride ISO/tier-label table at 0x1000."""
    size_hw, count = struct.unpack_from(">HH", data, ISO_BASE)
    entries = []
    for i in range(count):
        o = ISO_BASE + ISO_HEADER + i * ENTRY
        stride, iso = struct.unpack_from(">HH", data, o)
        labels = []
        for s in range(NSLOT):
            raw = bytes(data[o + 4 + s * SLOT: o + 4 + (s + 1) * SLOT])
            txt = raw.split(b"\x00")[0]
            if txt:
                labels.append(txt.decode("latin-1"))
        pad = bytes(data[o + 4 + NSLOT * SLOT: o + ENTRY])
        entries.append({"stride": stride, "iso": iso, "labels": labels,
                        "pad_all_ff": pad == b"\xff" * ISO_PAD})
    return {
        "size_halfwords": size_hw,
        "count": count,
        "table_end": ISO_BASE + ISO_HEADER + count * ENTRY,
        "entries": entries,
        "stride_hist": dict(collections.Counter(e["stride"] for e in entries)),
        "iso_values": [e["iso"] for e in entries],
        "label_counts": [len(e["labels"]) for e in entries],
        "pad_all_ff": all(e["pad_all_ff"] for e in entries),
    }


def _plausible(text: bytes) -> bool:
    """A decoded text field is Latin-1/ASCII with at most word padding."""
    nz = [b for b in text if b != 0]
    if not nz:
        return False
    good = sum(1 for b in nz if 0x20 <= b <= 0x7E or 0x80 <= b <= 0xFF)
    return good >= 0.95 * len(nz)


def blob_start(data: bytes, table_end: int) -> int | None:
    """First 12-byte-prefix record signature after the ISO table."""
    n = len(data)
    for o in range(table_end, min(n - PREFIX, table_end + 0x2000)):
        if (data[o + 4:o + 8] == b"\xff" * 4
                and data[o + 2] == 0 and 0 < data[o + 3] < MAXLEN):
            return o
    return None


def term_walk(data: bytes, start: int) -> dict[str, Any]:
    """Walk term records from START to EOF; report gaps as a byte histogram."""
    n = len(data)
    o = start
    recs: list[dict[str, Any]] = []
    forms: collections.Counter = collections.Counter()
    gaps: list[tuple[int, int]] = []
    while o + PREFIX <= n:
        code, length = struct.unpack_from(">HH", data, o)
        flags, value = struct.unpack_from(">II", data, o + 4)
        if length == 0 and flags in (0xFFFFFFFF, 0):
            recs.append({"off": o, "code": code, "len": 0, "flags": flags,
                         "value": value, "text": "", "form": "marker", "size": 14})
            forms["marker"] += 1
            o += 14
            continue
        te = o + PREFIX + 2 * length
        if 0 < length < MAXLEN and te <= n and _plausible(data[o + PREFIX:te]):
            tail = struct.unpack_from(">H", data, te)[0] if te + 2 <= n else None
            with_trailer = tail == (value & 0xFFFF)
            form = "term+trailer" if with_trailer else "term"
            recs.append({"off": o, "code": code, "len": length, "flags": flags,
                         "value": value,
                         "text": data[o + PREFIX:te].rstrip(b"\x00").decode("latin-1"),
                         "form": form,
                         "size": PREFIX + 2 * length + (2 if with_trailer else 0)})
            forms[form] += 1
            o += PREFIX + 2 * length + (2 if with_trailer else 0)
            continue
        # Resync: find the next offset that parses as a record.  Bytes skipped
        # here are the unexplained part (second record family / index frames).
        q = o + 1
        found = None
        while q + PREFIX <= n:
            ln = struct.unpack_from(">H", data, q + 2)[0]
            if 0 < ln < MAXLEN:
                t = q + PREFIX + 2 * ln
                if t <= n and _plausible(data[q + PREFIX:t]):
                    found = q
                    break
            q += 1
        gaps.append((o, found if found is not None else n))
        if found is None:
            break
        o = found

    residual: collections.Counter = collections.Counter()
    residual_zero = residual_ff = 0
    for a, b in gaps:
        for x in data[a:b]:
            residual[x] += 1
            if x == 0:
                residual_zero += 1
            elif x == 0xFF:
                residual_ff += 1

    explained = start + sum(r["size"] for r in recs)
    # Field ranges are reported on the well-formed (flags == ffffffff)
    # family; resync artifacts from the second family are excluded so the
    # min/max are not dominated by a mid-record byte misread as a code.
    clean = [r for r in recs if r["flags"] == 0xFFFFFFFF]
    codes = [r["code"] for r in clean]
    lens = [r["len"] for r in clean if r["len"]]
    flags_ff = len(clean)
    return {
        "start": start,
        "records": len(recs),
        "forms": dict(forms),
        "sample_terms": [r["text"] for r in recs if r["text"]][:6],
        "code_min": min(codes) if codes else None,
        "code_max": max(codes) if codes else None,
        "code_highbit": sum(1 for c in codes if c & 0x8000),
        "len_min": min(lens) if lens else None,
        "len_max": max(lens) if lens else None,
        "flags_ffffffff": flags_ff,
        "flags_other": len(recs) - flags_ff,
        "value_min": min((r["value"] for r in clean), default=None),
        "value_max": max((r["value"] for r in clean), default=None),
        "explained_bytes": min(explained, n),
        "explained_pct": round(100.0 * min(explained, n) / n, 3),
        "residual_bytes": sum(b - a for a, b in gaps),
        "residual_runs": len(gaps),
        "residual_zero": residual_zero,
        "residual_ff": residual_ff,
        "residual_other": {f"0x{k:02x}": v for k, v in residual.most_common(10)
                           if k not in (0, 0xFF)},
    }


def census_one(data: bytes) -> dict[str, Any]:
    iso = iso_table(data)
    start = blob_start(data, iso["table_end"])
    blob = term_walk(data, start) if start is not None else None
    header = parse_header(data)
    # term_walk's explained_bytes already covers the header, ISO table and
    # every walked record (it starts its count at the blob offset).
    explained = blob["explained_bytes"] if blob else iso["table_end"]
    return {
        "size": len(data),
        "header": header,
        "iso": {k: v for k, v in iso.items() if k != "entries"},
        "iso_first": [{"stride": e["stride"], "iso": e["iso"],
                       "labels": e["labels"][:3]} for e in iso["entries"][:4]],
        "blob": blob,
        "reader_va": "UNKNOWN (M3.18 r3, negative): no 462-byte-stride / 0x00e7 reader located",
        "explained_bytes": min(explained, len(data)),
        "explained_pct": round(100.0 * min(explained, len(data)) / len(data), 3),
    }


def print_one(path: Path, res: dict[str, Any]) -> None:
    h = res["header"]
    iso = res["iso"]
    blob = res["blob"]
    print(f"  {path.name}  size={res['size']:,} B")
    print(f"    header: {', '.join(f'{k}={v}' for k, v in h['texts'].items())}"
          f"  slots={{{', '.join(f'{k}:{v}' for k, v in sorted(h['slots'].items()))}}}")
    print(f"    ISO table: count={iso['count']} stride_hist={iso['stride_hist']}"
          f" table_end=0x{iso['table_end']:x} pad_all_ff={iso['pad_all_ff']}")
    print(f"      iso={iso['iso_values'][:12]}{' ...' if len(iso['iso_values']) > 12 else ''}"
          f"  labels/country={iso['label_counts'][:8]}")
    for e in res["iso_first"][:2]:
        print(f"      entry stride=0x{e['stride']:04x} iso={e['iso']} labels={e['labels']}")
    if blob:
        print(f"    blob: start=0x{blob['start']:x} records={blob['records']:,}"
              f" forms={blob['forms']}")
        print(f"      code=0x{blob['code_min']:04x}..0x{blob['code_max']:04x}"
              f" (high-bit {blob['code_highbit']:,}/{blob['flags_ffffffff']:,} clean)"
              f"  len={blob['len_min']}..{blob['len_max']}"
              f"  flags ffffffff={blob['flags_ffffffff']:,} other={blob['flags_other']:,}"
              f"  value={blob['value_min']}..{blob['value_max']}")
        print(f"      terms: {', '.join(t[:24] for t in blob['sample_terms'])}")
        print(f"      bytes explained: {blob['explained_bytes']:,} / {res['size']:,}"
              f" = {res['explained_pct']}%")
        print(f"      unexplained: {blob['residual_bytes']:,} B in"
              f" {blob['residual_runs']} runs (zero {blob['residual_zero']:,},"
              f" 0xff {blob['residual_ff']:,}, other {blob['residual_other']})")
    else:
        print(f"    blob: NOT FOUND; only ISO table explained"
              f" ({res['explained_bytes']:,} B = {res['explained_pct']}%)")
    print(f"    reader: {res['reader_va']}")


def cmd_census(args) -> int:
    overall = True
    for root in args.roots:
        paths = shard_paths(root)
        if not paths:
            print(f"no ICADM0nn shards under {root}", file=sys.stderr)
            overall = False
            continue
        print(f"== {root}  ({len(paths)} shards)")
        agg = collections.Counter()
        for p in paths:
            data = load(p)
            res = census_one(data)
            if args.mutate_byte is not None:
                bad = bytearray(data)
                bad[args.mutate_byte] ^= 0xFF
                bad_res = census_one(bytes(bad))
                nr = res["blob"]["records"] if res["blob"] else 0
                br = bad_res["blob"]["records"] if bad_res["blob"] else 0
                print(f"  mutate 0x{args.mutate_byte:x}:"
                      f" {data[args.mutate_byte]:02x}->{bad[args.mutate_byte]:02x}"
                      f" | stride {res['iso']['stride_hist']}->"
                      f"{bad_res['iso']['stride_hist']}"
                      f" | records {nr:,}->{br:,}"
                      f" | explained {res['explained_bytes']:,}->"
                      f"{bad_res['explained_bytes']:,}"
                      f" ({res['explained_pct']}%->{bad_res['explained_pct']}%)")
            if args.json:
                print(json.dumps({"path": str(p), **res}, indent=2))
            else:
                print_one(p, res)
            agg["shards"] += 1
            agg["size"] += res["size"]
            agg["explained"] += res["explained_bytes"]
            if res["blob"]:
                agg["records"] += res["blob"]["records"]
        if not args.json:
            pct = 100.0 * agg["explained"] / agg["size"] if agg["size"] else 0
            print(f"  CARD TOTAL: shards={agg['shards']} size={agg['size']:,} B"
                  f" records={agg['records']:,}"
                  f" explained={agg['explained']:,} B = {pct:.2f}%")
    return 0 if overall else 1


def synth_shard() -> bytes:
    """A tiny synthetic ICADM shard: header, 2-entry ISO table, term records."""
    data = bytearray(b"\xff" * HEADER)
    data[0:16] = "CLARION".encode("utf-16-be")
    # slot 4 (addr 512, blk 1) and slot 13 (addr 516, blk 1)
    struct.pack_into(">IH", data, SLOT0 + 6 * 4, 512, 1)
    struct.pack_into(">IH", data, SLOT0 + 6 * 13, 516, 1)
    data += b"\x00" * (2 * ENTRY)          # room for the ISO table
    struct.pack_into(">HH", data, ISO_BASE, 2 * ENTRY // 2, 2)
    for i, iso in enumerate((20, 840)):
        o = ISO_BASE + ISO_HEADER + i * ENTRY
        struct.pack_into(">HH", data, o, STRIDE, iso)
        labels = [b"2=COUNTRY", b"2=PARROQUIA"] if i == 0 else [b"3=COUNTRY", b"3=STATE"]
        for s, lab in enumerate(labels):
            data[o + 4 + s * SLOT:o + 4 + s * SLOT + len(lab)] = lab
        data[o + 4 + NSLOT * SLOT:o + ENTRY] = b"\xff" * ISO_PAD

    def term(code: int, length: int, flags: int, value: int, text: bytes,
             trailer: bool) -> None:
        nonlocal data
        data += struct.pack(">HHII", code, length, flags, value)
        body = text + b"\x00" * (length * 2 - len(text))
        data += body
        if trailer:
            data += struct.pack(">H", value & 0xFFFF)

    term(0x800E, 7, 0xFFFFFFFF, 13, b"COUNTRY", True)
    term(0x800B, 4, 0xFFFFFFFF, 25, b"CITY", True)
    data += struct.pack(">HHII", 0x0006, 0, 0xFFFFFFFF, 0xFFFFFFFF) + b"\x00\x00"
    term(0x8007, 1, 0xFFFFFFFF, 0x0DAE, b"AC", False)
    term(0x800C, 6, 0xFFFFFFFF, 0x0DB2, b"AKZENT-HOTEL", False)
    return bytes(data)


def selftest() -> int:
    fails: list[str] = []

    def check(ok: bool, msg: str) -> None:
        print(("ok: " if ok else "FAIL: ") + msg)
        if not ok:
            fails.append(msg)

    data = synth_shard()
    res = census_one(data)
    iso = res["iso"]
    check(iso["count"] == 2 and iso["stride_hist"] == {STRIDE: 2},
          f"ISO table: 2 entries, stride hist {iso['stride_hist']}")
    check(iso["pad_all_ff"], "ISO pad 0xff")
    check(iso["iso_values"] == [20, 840], "ISO codes 20/840")
    check(iso_first_ok(data), "ISO labels decode as Latin-1")
    h = res["header"]
    check(h["texts"].get("0x000") == "CLARION", "header text CLARION")
    check(h["slots"].get(4) == (512, 1) and h["slots"].get(13) == (516, 1),
          "header slots 4/13")
    blob = res["blob"]
    check(blob is not None and blob["start"] == ISO_BASE + ISO_HEADER + 2 * ENTRY,
          "blob start after ISO table")
    check(blob["records"] == 5, f"5 term records (got {blob['records']})")
    check(blob["forms"] == {"term+trailer": 2, "marker": 1, "term": 2},
          f"forms term/trailer x2, marker x1, term x2 (got {blob['forms']})")
    check(blob["sample_terms"][0] == "COUNTRY", "text decode COUNTRY")
    check("AKZENT-HOTEL" in blob["sample_terms"], "second-form text decode")
    check(res["explained_pct"] > 50,
          f"explained >50% (got {res['explained_pct']}%)")
    check(blob["residual_bytes"] == 0, "synthetic file fully explained")
    # Negative control: corrupt a stride tag (0x00e7 -> 0x00e6) and a term
    # length; both must be detected in the census.
    bad = bytearray(data)
    bad[ISO_BASE + ISO_HEADER] ^= 1
    bad_res = census_one(bytes(bad))
    check(bad_res["iso"]["stride_hist"] != {STRIDE: 2},
          f"mutated stride tag detected ({bad_res['iso']['stride_hist']})")
    bad = bytearray(data)
    bad[blob["start"] + 3] = 0x20
    bad_res = census_one(bytes(bad))
    check(bad_res["explained_pct"] < res["explained_pct"],
          f"mutated term length lowers coverage"
          f" ({bad_res['explained_pct']}% < {res['explained_pct']}%)")
    if fails:
        print(f"icadm_decode selftest: {len(fails)} failures")
        return 1
    print("icadm_decode selftest: all ok")
    return 0


def iso_first_ok(data: bytes) -> bool:
    iso = iso_table(data)
    return iso["entries"][0]["labels"] == ["2=COUNTRY", "2=PARROQUIA"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true", help="run synthetic self-test")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("census", help="census of one or more ICADM card trees")
    c.add_argument("roots", nargs="+", type=Path)
    c.add_argument("--json", action="store_true")
    c.add_argument("--mutate-byte", type=lambda s: int(s, 0), metavar="OFF",
                   help="negative control: flip byte at OFF before the census")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "census":
        return cmd_census(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
