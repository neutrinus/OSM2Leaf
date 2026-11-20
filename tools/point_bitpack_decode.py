#!/usr/bin/env python3
"""Classify and decode POINT bit-packed (non-0x60/0x68) zlib inner pages.

M4.27 follow-up to M4.8b (C-2936/C-2939): ``poi_icons.iter_streams`` yields
zlib-compressed inner pages from a ``cmpind``-decoded POINT ``.DAT``.  Name
pages carry ``0x60``/``0x68`` POI records with packed copy-A/B coordinates
(``poi_point_check``).  The remaining "bit-packed" pages have other grammars.

This tool classifies those non-name zlib pages by their first two BE ``u16``
words (``w0,w1``), decodes the dominant fixed-record classes, and reports
whether any decoded class carries coordinate-bearing POI position records in
the known copy-A/B form.  It does not decode undecoded classes (stop
condition): for those it records header bytes and counts only.

M4.37 adds ``--coord-test``: a mechanical yes/no test of whether any
bit page encodes a coordinate pair, with a positive control (a ``78 9c`` name
page, whose copy-A ids are known coordinates) and a negative control (a phone
page) run through the same code.  A word pair ``(x, y)`` is scanned at every
2-byte step under 32 alignments (big- and little-endian words, bit phase
0..15, so bit-packed fields that do not start on a byte are covered):

* **mask-pass (C-2129 masks):** neither word is the walker's escape form
  (``w & 0xfc00 == 0xfc00``, type ``0x3f``) and both are absolute packed
  coordinates in the COORD001 form (bit 15 set: ``0x8000 <= w < 0xfc00``);
  separately the tool counts *local* pairs (both ``w <= 0x7ff``, the 0..2047
  runtime bound) at the two byte-aligned alignments;
* **bounds-pass:** the pair lies inside the shard's own COORD001 region box
  (region *n* = ``POINT0nn``; 100 % of copy-A ids do, EXP-2026-11-19-M4.37).

A page is mask-pass when one alignment has >= ``MIN_PAIRS`` mask pairs, and
bounds-pass when one alignment has >= ``MIN_PAIRS`` in-region pairs that are
>= ``MIN_RATIO`` of that alignment's mask pairs.  A local pair has no
geographic bound on its own (any 0..2047 pair is inside some cell), so local
counts are reported, not used for the verdict.

Usage::

    point_bitpack_decode.py --selftest
    point_bitpack_decode.py summary ROOT SHARD [SHARD ...]
    point_bitpack_decode.py check-coords ROOT SHARD [SHARD ...]
    point_bitpack_decode.py --coord-test IMG_OR_ROOT [--shards POINT002 ...] [--no-raw]
    point_bitpack_decode.py raw-index IMG_OR_ROOT SHARD [SHARD ...]

ROOT contains ``REFER001/SHARD.DAT.cmp`` and ``.ind``; ``IMG`` is a full card
image, read in place through ``mkcard`` (FAT32 walk, nothing extracted).
"""

from __future__ import annotations

import argparse
import collections
import re
import struct
import sys
import zlib
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import cmpind  # noqa: E402
import cmpind_codec  # noqa: E402
import coord_zcode_icode  # noqa: E402
import poi_icons  # noqa: E402


# (w0, w1) -> (record_size_bytes, class_name, coord_bearing)
# coord_bearing: 'no' = demonstrated non-coordinate (ASCII phone/index),
# 'unknown' = structure partially known but coordinate content not established.
KNOWN_CLASSES = {
    (8, 6): (16, "phone-us-fixed16", "no"),
    (10, 8): (20, "phone-intl-fixed20", "no"),
    (1, 6): (24, "index-24b-w1-6", "unknown"),
    (1, 44): (24, "index-24b-w1-44", "unknown"),
    (1, 47): (24, "index-24b-w1-47", "unknown"),
    (1, 9): (24, "index-24b-w1-9", "unknown"),
    (1, 11): (24, "index-24b-w1-11", "unknown"),
    (28, 10): (24, "index-24b-w28", "unknown"),
    (2, 0): (None, "mixed-w2", "unknown"),
}


def classify_page(blob: bytes) -> dict:
    """Classify one decompressed inner page blob."""
    info = {
        "len": len(blob),
        "w0": None,
        "w1": None,
        "class": "short",
        "rec_size": None,
        "coord_bearing": "unknown",
        "ascii_ratio": 0.0,
        "fixed_prefix_ok": None,
    }
    if len(blob) < 4:
        return info
    w0, w1 = struct.unpack_from(">HH", blob, 0)
    info["w0"], info["w1"] = w0, w1
    key = (w0, w1)
    spec = KNOWN_CLASSES.get(key)
    if spec is None:
        # generic w0==1 index family: 24B fixed records with 0xffff sentinels
        if w0 == 1 and len(blob) >= 24:
            spec = (24, f"index-24b-w1-{w1}", "unknown")
        elif w0 == 2:
            spec = (None, "mixed-w2", "unknown")
        else:
            spec = (None, f"unknown-w0-{w0}", "unknown")
    rec_size, cname, cb = spec
    info["class"] = cname
    info["rec_size"] = rec_size
    info["coord_bearing"] = cb
    # ASCII printable ratio over whole page (phone pages are mostly ASCII)
    printable = sum(1 for c in blob if 32 <= c < 127)
    info["ascii_ratio"] = printable / len(blob) if blob else 0.0
    if rec_size and len(blob) >= rec_size * 2:
        n = min(len(blob) // rec_size, 50)
        ok = sum(
            1
            for i in range(0, n * rec_size, rec_size)
            if struct.unpack_from(">HH", blob, i) == (w0, w1)
        )
        info["fixed_prefix_ok"] = ok == n
    return info


def decode_phone_records(blob: bytes, rec_size: int, limit: int = 5) -> list[str]:
    """Extract printable ASCII runs from fixed phone-record pages."""
    out = []
    for i in range(0, min(len(blob), rec_size * limit), rec_size):
        rec = blob[i : i + rec_size]
        # payload after 4-byte (w0,w1) prefix
        payload = rec[4:]
        txt = "".join(chr(c) if 32 <= c < 127 else "" for c in payload)
        txt = txt.strip("\x00")
        if txt:
            out.append(txt)
    return out


def decode_shard(root: Path, shard: str) -> bytes:
    data, _ = cmpind.decode(
        root / "REFER001" / f"{shard}.DAT.cmp",
        root / "REFER001" / f"{shard}.DAT.ind",
    )
    return data


def classify_shard(data: bytes) -> dict:
    name_pages = bit_pages = name_recs = 0
    classes = collections.Counter()
    coord_classes = collections.Counter()
    samples = {}
    for _off, blob in poi_icons.iter_streams(data):
        recs = list(poi_icons.iter_point_records(blob))
        if recs and recs[0][0] in (0x60, 0x68):
            name_pages += 1
            name_recs += len(recs)
            continue
        bit_pages += 1
        ci = classify_page(blob)
        key = (ci["w0"], ci["w1"], ci["class"], ci["coord_bearing"])
        classes[key] += 1
        coord_classes[ci["coord_bearing"]] += 1
        sk = ci["class"]
        if sk not in samples and ci["rec_size"]:
            samples[sk] = {
                "head_hex": blob[:16].hex(),
                "rec_size": ci["rec_size"],
                "fixed_prefix_ok": ci["fixed_prefix_ok"],
                "ascii_ratio": round(ci["ascii_ratio"], 3),
                "phone_samples": decode_phone_records(
                    blob, ci["rec_size"], limit=3
                )
                if ci["coord_bearing"] == "no"
                else [],
            }
        elif sk not in samples:
            samples[sk] = {"head_hex": blob[:16].hex(), "rec_size": None}
    return {
        "name_pages": name_pages,
        "bit_pages": bit_pages,
        "name_records": name_recs,
        "classes": classes,
        "coord_classes": coord_classes,
        "samples": samples,
    }


def geographic_coord_candidates(blob: bytes) -> int:
    """Count >HH pairs that could be packed POI coords (broad heuristic).

    Heuristic only (negative control aid): values in plausible packed-coordinate
    ranges seen in POINT copy-A/B (x roughly 32000-43000, y roughly 32000-43000
    for EU/US 2011 coverage). This is NOT a decoder - a zero/low count on a
    phone page supports 'no coordinate-bearing records'; it cannot prove absence
    in an undecoded bit layout.
    """
    n = 0
    for j in range(0, len(blob) - 3, 2):
        x, y = struct.unpack_from(">HH", blob, j)
        if 32000 <= x <= 43000 and 32000 <= y <= 43000:
            n += 1
    return n


def cmd_summary(args: argparse.Namespace) -> int:
    for shard in args.shards:
        data = decode_shard(Path(args.root), shard)
        r = classify_shard(data)
        print(f"{shard}: name_pages={r['name_pages']} bit_pages={r['bit_pages']} name_records={r['name_records']}")
        for (w0, w1, cls, cb), cnt in r["classes"].most_common():
            print(f"  w0={w0} w1={w1} class={cls} coord={cb} count={cnt}")
        for cls, s in sorted(r["samples"].items()):
            print(f"  sample {cls}: {s}")
    return 0


def cmd_check_coords(args: argparse.Namespace) -> int:
    for shard in args.shards:
        data = decode_shard(Path(args.root), shard)
        r = classify_shard(data)
        print(f"{shard}: bit_pages={r['bit_pages']} coord_classes={dict(r['coord_classes'])}")
        # heuristic scan on one sample per non-no class? and on phone pages as control
        # Scan a few pages per coord class
        seen = collections.defaultdict(int)
        totals = collections.defaultdict(int)
        for _off, blob in poi_icons.iter_streams(data):
            recs = list(poi_icons.iter_point_records(blob))
            if recs and recs[0][0] in (0x60, 0x68):
                continue
            ci = classify_page(blob)
            cb = ci["coord_bearing"]
            if seen[cb] >= 50:
                continue
            seen[cb] += 1
            totals[cb] += geographic_coord_candidates(blob)
        for cb in sorted(seen):
            print(f"  coord_class={cb} pages_sampled={seen[cb]} heuristic_coordlike_pairs={totals[cb]} (heuristic only, not a decoder)")
    return 0


# ---------------------------------------------------------------------------
# M4.37 coordinate test


DEFAULT_SHARDS = ("POINT002", "POINT008", "POINT029")
MIN_PAIRS = 16       # distinct in-region pairs a coordinate page must show
GRID_SHARE = 0.9     # share of in-region pairs that must sit on one lattice
GRID_Q = 8           # lattice step (packed units) from which a unit is a grid-key table
MIN_RATIO = 0.5      # in-region / mask-pass pairs at that alignment
RAW_WINDOW = 4096    # raw (non-stream) bytes are tested in windows of this size
ABS_LO, ABS_HI = 0x8000, 0xFC00   # bit 15 set, not the 0xfc00 escape form
LOCAL_MAX = 0x7FF                 # the 0..2047 runtime bound
# a pair of absolute words at an even offset: big-endian / little-endian
_ABS_BE = re.compile(rb"(?=[\x80-\xfb].[\x80-\xfb].)", re.S)
_ABS_LE = re.compile(rb"(?=.[\x80-\xfb].[\x80-\xfb])", re.S)
_LOC_BE = re.compile(rb"(?=[\x00-\x07].[\x00-\x07].)", re.S)
_LOC_LE = re.compile(rb"(?=.[\x00-\x07].[\x00-\x07])", re.S)


def page_family(blob: bytes) -> str:
    """Group a non-name page for the report (layout evidence, not semantics).

    ``phone``: ``(8,6)``/``(10,8)`` fixed records; ``mixed-w2``: ``w0 == 2``;
    ``index24``: 24-byte records with ``3f00`` at bytes 18..19 of the first
    two records (``w0`` is the shard number minus one); ``keyword``:
    variable records ``len_words, 0x0401|0x0501, xx ff`` followed by ASCII;
    ``other``: anything else.
    """
    if len(blob) < 6:
        return "short"
    w0, w1, w2 = struct.unpack_from(">HHH", blob, 0)
    if (w0, w1) in ((8, 6), (10, 8)):
        return "phone"
    if w0 == 2:
        return "mixed-w2"
    if len(blob) >= 48 and blob[18:20] == b"\x3f\x00" and blob[42:44] == b"\x3f\x00":
        return "index24"
    if w1 in (0x0401, 0x0501) and (w2 & 0xFF) == 0xFF:
        return "keyword"
    return "other"


def _phase(blob: bytes, bits: int) -> bytes:
    """The bit stream of *blob* starting *bits* (0..15) bits later."""
    if not bits:
        return blob
    n = len(blob)
    v = (int.from_bytes(blob, "big") << bits) & ((1 << (8 * n)) - 1)
    return v.to_bytes(n, "big")


def _pairs(buf: bytes, pattern: re.Pattern, little: bool):
    fmt = "<HH" if little else ">HH"
    for m in pattern.finditer(buf):
        i = m.start()
        if i & 1:
            continue
        yield struct.unpack_from(fmt, buf, i)


def lattice(pairs) -> tuple[int, int | None]:
    """Coarsest power-of-two lattice (q, y origin) that holds >= GRID_SHARE.

    A POI point (copy A) sits on the 1-unit lattice; a cell or grid key sits
    on ``x = 32768 + k*q``, ``y = origin + m*q`` with ``q >= GRID_Q`` (128 is
    the 2/3 deg x 1 deg grid unit, 16 is 1/12 deg x 1/8 deg).  Both y origins
    are tried: 52736 (MAPAL tile) and 52742 (COORD001).
    """
    pairs = list(pairs)
    if not pairs:
        return 1, None
    for q in (128, 64, 32, 16, 8, 4, 2):
        for origin in (52736, 52742):
            hit = sum(1 for x, y in pairs if (x - 32768) % q == 0 and (y - origin) % q == 0)
            if hit >= GRID_SHARE * len(pairs):
                return q, origin
    return 1, None


def coord_scan(blob: bytes, box: tuple[int, int, int, int]) -> dict:
    """Run the mask and bounds tests over 32 alignments of one buffer."""
    x0, x1, y0, y1 = box
    best = {"mask": 0, "inside": set(), "align": None, "raw_inside": 0, "rank": (False, 0)}
    best_mask = 0
    for bits in range(16):
        buf = _phase(blob, bits)
        for little, pat in ((False, _ABS_BE), (True, _ABS_LE)):
            mask = 0
            inside = set()
            n_in = 0
            for x, y in _pairs(buf, pat, little):
                mask += 1
                if x0 <= x <= x1 and y0 <= y <= y1:
                    inside.add((x, y))
                    n_in += 1
            best_mask = max(best_mask, mask)
            # rank: an alignment whose in-region share passes MIN_RATIO first,
            # then the number of distinct in-region pairs
            rank = (n_in >= MIN_RATIO * max(mask, 1), len(inside))
            if best["align"] is None or rank > best["rank"]:
                best = {"mask": mask, "inside": inside, "raw_inside": n_in, "rank": rank,
                        "align": f"{'le' if little else 'be'}+{bits}"}
    local = max(
        sum(1 for x, y in _pairs(blob, pat, little) if x or y)
        for little, pat in ((False, _LOC_BE), (True, _LOC_LE))
    )
    distinct = len(best["inside"])
    q, q_origin = lattice(best["inside"])
    bounds_pass = (distinct >= MIN_PAIRS
                   and best["raw_inside"] >= MIN_RATIO * max(best["mask"], 1))
    kind = None
    if bounds_pass:
        kind = "grid" if q >= GRID_Q else "point"
    return {
        "len": len(blob),
        "mask_pairs": best_mask,
        "bounds_pairs": best["raw_inside"],
        "bounds_distinct": distinct,
        "lattice_q": q,
        "lattice_origin": q_origin,
        "bounds_align": best["align"],
        "bounds_align_mask": best["mask"],
        "local_pairs": local,
        "mask_pass": best_mask >= MIN_PAIRS,
        "bounds_pass": bounds_pass,
        "kind": kind,
        "inside": best["inside"],
    }


class Source:
    """REFER001 files from an extracted tree or, read in place, a card image."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.is_image = self.path.is_file()
        self._handle = None
        if self.is_image:
            import mkcard  # FAT32 reader; imported only for image input
            self._mkcard = mkcard
            self._handle = open(self.path, "rb")
            _part, self._geo, self._fat = mkcard.open_map_partition(self._handle)

    def read(self, rel: str) -> bytes:
        if not self.is_image:
            return (self.path / rel).read_bytes()
        entry, _ = self._mkcard._resolve(self._handle, self._geo, self._fat, rel)
        return self._mkcard.read_chain(self._handle, self._geo, self._fat,
                                       entry.cluster, entry.size)

    def decode(self, name: str) -> bytes:
        cmp_b = self.read(f"REFER001/{name}.DAT.cmp")
        ind_b = self.read(f"REFER001/{name}.DAT.ind")
        usize, csize, count, chunk = struct.unpack_from("<IIII", ind_b, 0)
        offsets = struct.unpack_from(f"<{count}I", ind_b, 16)
        if csize != len(cmp_b):
            raise cmpind.FormatError(f"{name}: .ind says {csize} bytes, .cmp has {len(cmp_b)}")
        return cmpind_codec.decode_blob(cmp_b, offsets, usize=usize, chunk_size=chunk,
                                        name=f"{name}.DAT.cmp")

    def close(self):
        if self._handle:
            self._handle.close()


def region_boxes(coord001: bytes) -> dict[int, tuple[int, int, int, int]]:
    return {r["index"]: (r["x0"], r["x1"], r["y0"], r["y1"])
            for r in coord_zcode_icode.coord001_records(coord001)}


def stream_spans(data: bytes):
    """Yield (offset, consumed_bytes, blob) like ``poi_icons.iter_streams``."""
    for match in re.finditer(rb"\x78[\x01\x9c\xda\x5e]", data):
        d = zlib.decompressobj()
        window = data[match.start():match.start() + 400000]
        try:
            out = d.decompress(window)
        except zlib.error:
            continue
        if 2000 < len(out) < 400000:
            used = len(window) - len(d.unused_data) if d.eof else len(window)
            yield match.start(), used, out


def raw_windows(data: bytes, spans):
    """Non-stream, non-zero windows of the decoded .DAT (the 'raw' region)."""
    covered = bytearray(len(data) // RAW_WINDOW + 1)
    spans = sorted(spans)
    cur = 0
    for off, used in spans:
        if off + used <= cur:
            continue
        a = max(off, cur)
        for w in range(a // RAW_WINDOW, (off + used - 1) // RAW_WINDOW + 1):
            covered[w] = 1
        cur = off + used
    zero = bytes(RAW_WINDOW)
    for w in range(len(covered)):
        if covered[w]:
            continue
        chunk = data[w * RAW_WINDOW:(w + 1) * RAW_WINDOW]
        if len(chunk) < 64 or chunk == zero[:len(chunk)]:
            continue
        yield w * RAW_WINDOW, chunk


def _acc() -> dict:
    return {"tested": 0, "mask": 0, "bounds": 0, "grid": 0, "point": 0,
            "max_distinct": 0, "local": 0, "bytes": 0, "point_offsets": [],
            "lattice": collections.Counter()}


def _add(acc: dict, off: int, r: dict) -> None:
    acc["tested"] += 1
    acc["bytes"] += r["len"]
    acc["mask"] += r["mask_pass"]
    acc["bounds"] += r["bounds_pass"]
    if r["kind"]:
        acc[r["kind"]] += 1
        acc["lattice"][(r["lattice_q"], r["lattice_origin"])] += 1
    if r["kind"] == "point":
        acc["point_offsets"].append(off)
    acc["max_distinct"] = max(acc["max_distinct"], r["bounds_distinct"])
    acc["local"] += r["local_pairs"] >= MIN_PAIRS
    if r["kind"] == "point":
        acc.setdefault("pairs", set()).update(r["inside"])


JOIN_SHIFT = 37      # negative control: the same pairs moved by (+37, +37) units


def join_rate(pairs, ids: set) -> tuple[int, int, int]:
    """(distinct pairs, pairs equal to an id, shifted pairs equal to an id)."""
    pairs = set(pairs)
    hit = sum(1 for p in pairs if p in ids)
    ctl = sum(1 for x, y in pairs if (x + JOIN_SHIFT, y + JOIN_SHIFT) in ids)
    return len(pairs), hit, ctl


def coord_test_shard(data: bytes, box, raw: bool = True) -> dict:
    """Test every non-name page (and, with *raw*, every raw window) of a shard."""
    fam = collections.defaultdict(_acc)
    pos = neg = None
    spans = []
    copy_a: set = set()
    for off, used, blob in stream_spans(data):
        spans.append((off, used))
        recs = list(poi_icons.iter_point_records(blob))
        if recs and recs[0][0] in (0x60, 0x68):
            for _tag, rec in recs:
                if len(rec) >= 16:
                    copy_a.add(struct.unpack_from(">HH", rec, 2))
            if pos is None:
                pos = (off, coord_scan(blob, box))
            continue
        family = page_family(blob)
        r = coord_scan(blob, box)
        if family == "phone" and neg is None:
            neg = (off, r)
        _add(fam[family], off, r)
    out = {"families": dict(fam), "positive": pos, "negative": neg,
           "streams": len(spans), "copy_a": copy_a}
    if raw:
        acc = _acc()
        for off, chunk in raw_windows(data, spans):
            _add(acc, off, coord_scan(chunk, box))
        out["raw"] = acc
    return out


def _fmt_ctl(label: str, ctl, want: bool) -> tuple[str, bool]:
    if ctl is None:
        return f"  control {label}: MISSING", False
    off, r = ctl
    ok = r["bounds_pass"] is want and (not want or r["kind"] == "point")
    return (f"  control {label}: page {off:#x} len={r['len']} mask_pairs={r['mask_pairs']} "
            f"in_region={r['bounds_pairs']} distinct={r['bounds_distinct']} "
            f"lattice_q={r['lattice_q']}/{r['lattice_origin']} ({r['bounds_align']}) "
            f"bounds_pass={r['bounds_pass']} kind={r['kind']} -> {'OK' if ok else 'FAIL'}"), ok


def cmd_coord_test(args: argparse.Namespace) -> int:
    src = Source(Path(args.coord_test))
    try:
        boxes = region_boxes(src.decode("COORD001"))
        kind = "image" if src.is_image else "tree"
        print(f"coord-test {kind}={args.coord_test} MIN_PAIRS={MIN_PAIRS} "
              f"MIN_RATIO={MIN_RATIO} GRID_SHARE={GRID_SHARE} GRID_Q={GRID_Q} "
              f"alignments=32 (be/le x bit phase 0..15)")
        bit_points = raw_points = raw_grid = 0
        controls_ok = True
        for shard in args.shards:
            n = int(shard[5:])
            box = boxes[n]
            data = src.decode(shard)
            r = coord_test_shard(data, box, raw=not args.no_raw)
            print(f"{shard}: decoded={len(data)} streams={r['streams']} region={n} "
                  f"box x={box[0]}..{box[1]} y={box[2]}..{box[3]}")
            for label, ctl, want in (("positive (78 9c name page)", r["positive"], True),
                                     ("negative (phone page)", r["negative"], False)):
                line, ok = _fmt_ctl(label, ctl, want)
                print(line)
                controls_ok &= ok
            print(f"  {'class':<10} {'tested':>7} {'bytes':>10} {'mask-pass':>10} "
                  f"{'bounds-pass':>12} {'grid':>6} {'point':>6} {'max_dist':>9} {'local>=16':>10}")
            rows = sorted(r["families"].items())
            if "raw" in r:
                rows.append(("raw-4k", r["raw"]))
            for name, f in rows:
                print(f"  {name:<10} {f['tested']:>7} {f['bytes']:>10} {f['mask']:>10} "
                      f"{f['bounds']:>12} {f['grid']:>6} {f['point']:>6} "
                      f"{f['max_distinct']:>9} {f['local']:>10}")
                if f["lattice"]:
                    hist = ", ".join(f"q={q}/{o}:{c}" for (q, o), c in sorted(f["lattice"].items()))
                    print(f"    bounds-pass lattice: {hist}")
                for off in f["point_offsets"][:5]:
                    print(f"    point-kind bounds-pass at {off:#x}")
                if f.get("pairs"):
                    n_p, hit, ctl = join_rate(f["pairs"], r["copy_a"])
                    print(f"    point-kind pairs vs name-record copy A ({len(r['copy_a'])} ids): "
                          f"{hit}/{n_p} equal ({100.0 * hit / n_p:.1f} %), "
                          f"shifted +{JOIN_SHIFT} control {ctl}/{n_p} ({100.0 * ctl / n_p:.1f} %)")
                if name == "raw-4k":
                    raw_points += f["point"]
                    raw_grid += f["grid"]
                else:
                    bit_points += f["point"]
        print(f"controls: {'OK' if controls_ok else 'FAIL'}")
        if not controls_ok:
            print("verdict: INVALID (controls failed)")
            return 1
        verdict = "COORDINATES FOUND" if bit_points else "NO COORDINATES"
        print(f"verdict bit pages: {verdict} (point-kind bounds-pass pages: {bit_points})")
        if not args.no_raw:
            print(f"raw windows: point-kind bounds-pass {raw_points}, "
                  f"grid-key bounds-pass {raw_grid}")
        return 0
    finally:
        src.close()


def raw_index_records(data: bytes, box, spans) -> list[tuple[int, int, int]]:
    """16-byte raw records ``00 08 | u32 | u16 | x | y | 00000000`` in the region.

    Layout as observed in the non-stream region (EXP-2026-11-19-M4.37): the
    first BE word ``0x0008`` reads as a C-2129 header of type 0 and 8 words.
    Only records outside every zlib inner stream are kept.
    """
    x0, x1, y0, y1 = box
    starts = [a for a, _ in spans]
    ends = [a + u for a, u in spans]
    import bisect
    out = []
    for m in re.finditer(rb"\x00\x08", data):
        o = m.start()
        if o & 1 or o + 16 > len(data) or data[o + 12:o + 16] != b"\x00\x00\x00\x00":
            continue
        x, y = struct.unpack_from(">HH", data, o + 8)
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            continue
        k = bisect.bisect_right(starts, o) - 1
        if k >= 0 and o < ends[k]:
            continue
        out.append((o, x, y))
    return out


def cmd_raw_index(args: argparse.Namespace) -> int:
    src = Source(Path(args.source))
    try:
        boxes = region_boxes(src.decode("COORD001"))
        for shard in args.shards:
            box = boxes[int(shard[5:])]
            data = src.decode(shard)
            spans, copy_a, copy_b = [], set(), set()
            for off, used, blob in stream_spans(data):
                spans.append((off, used))
                recs = list(poi_icons.iter_point_records(blob))
                if recs and recs[0][0] in (0x60, 0x68):
                    for _tag, rec in recs:
                        if len(rec) >= 16:
                            copy_a.add(struct.unpack_from(">HH", rec, 2))
                            copy_b.add(struct.unpack_from(">HH", rec, 12))
            recs = raw_index_records(data, box, spans)
            pts = {(x, y) for _o, x, y in recs}
            coarse = {p for p in pts if lattice([p])[0] >= 16}
            fine = pts - coarse
            print(f"{shard}: raw 0x0008 records in region {len(recs)} "
                  f"(first {recs[0][0]:#x} last {recs[-1][0]:#x})" if recs else
                  f"{shard}: raw 0x0008 records in region 0")
            if not recs:
                continue
            print(f"  distinct pairs {len(pts)}: lattice>=16 {len(coarse)}, finer {len(fine)}")
            for label, group in (("finer", fine), ("lattice>=16", coarse)):
                if not group:
                    continue
                n, ha, ca = join_rate(group, copy_a)
                _, hb, _ = join_rate(group, copy_b)
                print(f"  {label}: equal copy A {ha}/{n} ({100.0 * ha / n:.1f} %), "
                      f"copy B {hb}/{n} ({100.0 * hb / n:.1f} %), "
                      f"shifted +{JOIN_SHIFT} control vs A {ca}/{n} ({100.0 * ca / n:.1f} %)")
            print(f"  name-record ids: copy A {len(copy_a)} distinct, copy B {len(copy_b)}")
        return 0
    finally:
        src.close()


def selftest() -> int:
    failures = []

    def check(name, cond, detail=""):
        print(f"  {name:<44} {'OK' if cond else 'FAIL'} {detail}".rstrip())
        if not cond:
            failures.append(name)

    # US phone page: 16-byte records, w0=8,w1=6, ASCII phone payload (12B)
    rec = struct.pack(">HH", 8, 6) + b"503-3195112\x00"
    assert len(rec) == 16, len(rec)
    page = rec * 10
    ci = classify_page(page)
    check("w0=8 phone class", ci["class"] == "phone-us-fixed16")
    check("w0=8 rec_size 16", ci["rec_size"] == 16)
    check("w0=8 coord_bearing no", ci["coord_bearing"] == "no")
    check("w0=8 fixed prefix", ci["fixed_prefix_ok"] is True)
    ph = decode_phone_records(page, 16, limit=2)
    check("phone decode has ASCII", any("503" in p for p in ph), str(ph[:1]))
    check("phone ascii_ratio high", ci["ascii_ratio"] > 0.5, f"{ci['ascii_ratio']:.2f}")

    # EU intl phone: 20-byte, w0=10,w1=8
    rec2 = struct.pack(">HH", 10, 8) + b"+(34)-946826606\x00"
    assert len(rec2) == 20
    ci2 = classify_page(rec2 * 5)
    check("w0=10 intl phone class", ci2["class"] == "phone-intl-fixed20")
    check("w0=10 coord_bearing no", ci2["coord_bearing"] == "no")
    check("w0=10 rec_size 20", ci2["rec_size"] == 20)

    # index page: w0=1, 24B, ffff sentinels
    idx = struct.pack(">HHHHHHHHHHHH", 1, 44, 0, 565, 0xFFFF, 0xFFFF, 0, 34, 0xFFFF, 16128, 5, 49727)
    assert len(idx) == 24
    ci3 = classify_page(idx * 4)
    check("w0=1 index class", "index-24b" in ci3["class"])
    check("w0=1 rec_size 24", ci3["rec_size"] == 24)
    check("w0=1 fixed prefix", ci3["fixed_prefix_ok"] is True)
    check("w0=1 coord unknown (not name grammar)", ci3["coord_bearing"] == "unknown")

    # mixed w0=2
    ci4 = classify_page(struct.pack(">HHHH", 2, 0, 2, 0) + rec)
    check("w0=2 mixed", ci4["class"].startswith("mixed"))

    # short
    check("short blob", classify_page(b"\x00\x01")["class"] == "short")

    # --- M4.37 coord test -------------------------------------------------
    box = (38078, 41181, 50414, 53294)          # EU 2011 COORD001 region 29
    import random
    rnd = random.Random(4337)
    pts = [(rnd.randint(38100, 41100), rnd.randint(50500, 53200)) for _ in range(200)]
    name = b"".join(
        bytes([0x60, 12]) + struct.pack(">HH", x, y) + b"\x08\x01\x02\x03\x00\x00"
        + struct.pack(">HH", x, y) + b"AB\x00\x00\xff\xff" for x, y in pts)
    r = coord_scan(name, box)
    check("positive: name page bounds-pass", r["bounds_pass"] and r["kind"] == "point",
          f"distinct={r['bounds_distinct']} align={r['bounds_align']}")
    phone = (struct.pack(">HH", 10, 8) + b"+(34)-946826606\x00") * 200
    r = coord_scan(phone, box)
    check("negative: phone page fails bounds", not r["bounds_pass"],
          f"in_region={r['bounds_pairs']}")
    check("phone page passes the bare mask (no power alone)", r["mask_pass"])
    # the same pairs packed 5 bits off a byte boundary must still be found
    body = b"".join(struct.pack(">HHHH", 0x0123, x, y, 0x0456) for x, y in pts)
    shifted = (int.from_bytes(body, "big") >> 5).to_bytes(len(body), "big")
    r = coord_scan(shifted, box)
    check("bit phase 5 pairs found", r["bounds_pass"] and r["bounds_align"] == "be+5",
          f"align={r['bounds_align']}")
    le = b"".join(struct.pack("<HHHH", 0x0123, x, y, 0x0456) for x, y in pts)
    r = coord_scan(le, box)
    check("little-endian pairs found", r["bounds_pass"] and r["bounds_align"].startswith("le"),
          f"align={r['bounds_align']}")
    grid = b"".join(struct.pack(">HIHHHI", 8, 0x1000 + 0x80 * i, 0x15,
                                32768 + 16 * (330 + i % 40), 52736 - 16 * (100 + i // 40), 0)
                    for i in range(200))
    r = coord_scan(grid, box)
    check("q=16 key table is grid kind", r["bounds_pass"] and r["kind"] == "grid"
          and r["lattice_q"] == 16 and r["lattice_origin"] == 52736,
          f"q={r['lattice_q']}/{r['lattice_origin']}")
    check("lattice of random points is 1", lattice(pts) == (1, None))
    check("join rate + shifted control",
          join_rate(pts[:10], set(pts)) == (10, 10, sum(
              (x + JOIN_SHIFT, y + JOIN_SHIFT) in set(pts) for x, y in pts[:10])))
    check("family phone/index24/keyword/mixed",
          [page_family(b) for b in (phone, idx * 4, struct.pack(">HHH", 14, 0x0501, 0x05FF) + b"x" * 30,
                                    struct.pack(">HHHH", 2, 0, 2, 0))]
          == ["phone", "index24", "keyword", "mixed-w2"])
    in_stream = struct.pack(">HIHHHI", 8, 9, 0x1D, *pts[1], 0)   # must be skipped
    rawdat = (b"\x00" * 6 + grid[:64] + name[:32] + in_stream
              + struct.pack(">HIHHHI", 8, 7, 0x1D, *pts[0], 0))
    found = raw_index_records(rawdat, box, [(70, 48)])
    check("raw 0x0008 records outside streams", [(x, y) for _o, x, y in found]
          == [(32768 + 16 * 332, 52736 - 16 * 100), (32768 + 16 * 333, 52736 - 16 * 100), pts[0]]
          and all(not 70 <= o < 118 for o, _x, _y in found), str(found))
    idx24 = struct.pack(">12H", 28, 10, 0, 0x55, 2, 0xFFFF, 0, 0x48, 0xFFFF, 0x3F00, 2, 0xD950)
    check("family index24", page_family(idx24 * 4) == "index24")

    print(f"point_bitpack_decode selftest: {'OK' if not failures else 'FAILED'}")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--coord-test", metavar="IMG_OR_ROOT",
                   help="M4.37: mask/bounds coordinate test of bit pages (card image or tree)")
    p.add_argument("--shards", nargs="+", default=list(DEFAULT_SHARDS),
                   help="POINT shards for --coord-test (default: %(default)s)")
    p.add_argument("--no-raw", action="store_true",
                   help="--coord-test: skip the non-stream raw 4 KiB windows")
    sub = p.add_subparsers(dest="cmd")
    sc = sub.add_parser("summary")
    sc.add_argument("root")
    sc.add_argument("shards", nargs="+")
    sc.set_defaults(func=cmd_summary)
    cc = sub.add_parser("check-coords")
    cc.add_argument("root")
    cc.add_argument("shards", nargs="+")
    cc.set_defaults(func=cmd_check_coords)
    ri = sub.add_parser("raw-index", help="M4.37: 16-byte 0x0008 raw records vs copy A")
    ri.add_argument("source", help="card image or extracted tree")
    ri.add_argument("shards", nargs="+")
    ri.set_defaults(func=cmd_raw_index)
    return p


def main(argv=None):
    p = build_parser()
    a = p.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.coord_test:
        return cmd_coord_test(a)
    if not getattr(a, "func", None):
        p.print_help()
        return 2
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
