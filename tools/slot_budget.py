#!/usr/bin/env python3
"""Slot budget for generated POINT name pages (M5.21).

A ``REFER001/POINTnnn.DAT`` logical file holds zlib *inner* streams (name
pages). A generated page keeps the factory slot: its stream may grow only into
the zero padding that follows it up to the next 0x100 boundary (C-2355 /
M5.12c rule). Bytes after the stream that are not zero belong to a neighbour
(pages may abut), so they cap the slot at the stream end. A zlib stream never
starts with 0x00, so a zero run cannot hide a page start.

This tool makes the budget explicit before anything is written:

  * ``slot``      = bytes the page may occupy (factory stream + zero padding);
  * ``stream``    = smallest stock-zlib stream of the edited page;
  * ``limit``     = ``slot - headroom``; a page with ``stream > limit`` is
                    refused (``FitError``) and its blob is not touched;
  * ``headroom``  = bytes kept free so that a no-op re-encode of the page still
                    fits. Its value comes from ``calibrate`` (measured, see the
                    EXP); it is a parameter, not a guess.

Edits are same-length name replacements (``name@`` POI records). Length
changes are not made here: the page tables of POINT001-009 are not known to
this tool (M5.12c EXP, Observations).

Usage:
  python3 tools/slot_budget.py calibrate --pairs DIR [--json OUT]
  python3 tools/slot_budget.py build --pairs DIR --outdir OUT \
      [--headroom N] [--image IMG] [--json OUT]
  python3 tools/slot_budget.py geom TOWN.jsonl --profile PROFILE.toml --check
  python3 tools/slot_budget.py geom-stats FACTORY_TILE.DAT --dir Y,X
  python3 tools/slot_budget.py --selftest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import subprocess
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# The geometry-budget sweep (M5.75) uses the checked-in ZE0 writer's model.
_ZE0_DIR = Path(__file__).resolve().parent / "ze0-viewer" / "tools_ze0"
if str(_ZE0_DIR) not in sys.path:
    sys.path.insert(0, str(_ZE0_DIR))
import cmpind_codec  # noqa: E402

CHUNK = cmpind_codec.CHUNK
PAGE_ALIGN = cmpind_codec.PAGE_ALIGN
WINDOW = 1 << 20
HEADER = cmpind_codec.IND_HEADER
ZLIB_HEAD = cmpind_codec.ZLIB_HEAD
#: A POI name is an upper-case run (4-40 bytes) directly followed by ``@``.
NAME_RE = re.compile(rb"(?<![A-Z0-9' &.\-])[A-Z0-9][A-Z0-9' &.\-]{3,39}@")
NAME_END = ord("@")
#: Headroom as a fraction of the factory stream: a portability margin. The
#: build must give the same answer on a machine whose zlib is not stock. On the
#: US POINT001-011 pages (31,371 zlib pages) stock zlib 1.3.2 re-encodes no
#: page above its factory stream (``calibrate.json``), while zlib-ng 1.3.1
#: re-encodes pages up to 3.64 % larger (POINT010; ``calibrate-zlibng.json``).
#: 4 % covers that measured excess. EXP-2026-11-08-M5.21-slot-budget.
HEADROOM_RATIO = 0.04


class PageError(ValueError):
    """The page does not match the layout this tool understands."""


class FitError(PageError):
    """The edited page does not fit its slot minus headroom."""

    def __init__(self, message: str, row: dict | None = None):
        super().__init__(message)
        self.row = row if row is not None else {"decision": "refuse", "reason": message}


# ---------------------------------------------------------------------------
# containers


def read_pair(cmp_path: Path, ind_path: Path):
    """Return (usize, chunk_size, offsets, cmp bytes, decoded blob)."""
    try:
        usize, csize, count, chunk_size, offsets = cmpind_codec.read_ind(ind_path)
    except cmpind_codec.FormatError as exc:
        raise PageError(str(exc)) from exc
    packed = cmp_path.read_bytes()
    if csize != len(packed):
        raise PageError(f"{cmp_path.name}: .ind says {csize}, file has {len(packed)}")
    try:
        blob = cmpind_codec.decode_blob(
            packed, offsets, usize=usize, chunk_size=chunk_size, name=cmp_path.name
        )
    except cmpind_codec.FormatError as exc:
        raise PageError(str(exc)) from exc
    return usize, chunk_size, offsets, packed, blob


def write_pair(packed: bytes, offsets, usize, chunk_size, blob_old: bytes,
               blob_new: bytes) -> tuple[bytes, bytes]:
    """Rebuild a pair: chunks whose payload is unchanged are kept verbatim.

    Changed chunks are recompressed with factory stock zlib params (M1.13/M1.16).
    Returns (cmp bytes, ind bytes).
    """
    return cmpind_codec.rebuild_pair_bytes(
        packed, offsets, usize, chunk_size, blob_old, blob_new,
        compress=cmpind_codec.factory_compress,
    )


# ---------------------------------------------------------------------------
# pages


def find_pages(blob: bytes) -> list[tuple[int, int, bytes]]:
    """Complete zlib streams in ``blob``: (offset, stream length, inflated)."""
    return list(cmpind_codec.find_zlib_streams(blob, window=WINDOW))


def slot_at(blob: bytes, page: int) -> tuple[int, int, tuple[int, int] | None, bytes]:
    """Return (stream length, slot length, encoder that reproduces it, inner)."""
    try:
        inner, consumed, slot, original = cmpind_codec.inner_stream_slot(blob, page, window=WINDOW)
    except cmpind_codec.FormatError as exc:
        raise PageError(str(exc)) from exc
    setting = reproducing_encoder(original, inner)
    return consumed, slot, setting, inner


def _deflate(data: bytes, level: int, mem_level: int) -> bytes:
    return cmpind_codec.factory_compress(
        data, level=level, mem_level=mem_level,
        wbits=cmpind_codec.FACTORY_WBITS, strategy=cmpind_codec.FACTORY_STRATEGY,
    )


ENCODERS = [(level, mem) for mem in (8, 9) for level in range(9, 0, -1)]
# Wider search for exact reproduction (M5.12c/M5.25): an unchanged page must
# round-trip to the same stream bytes when the original encoder is found.
REPRODUCE_ENCODERS = [
    (level, mem)
    for mem in (8, 9, 7, 6, 5, 4, 3, 2, 1)
    for level in (9, 6, 8, 7, 5, 4, 3, 2, 1)
]


def reproducing_encoder(original: bytes, inner: bytes, *, wide: bool = True):
    for level, mem in (REPRODUCE_ENCODERS if wide else ENCODERS):
        if _deflate(inner, level, mem) == original:
            return level, mem
    return None


def smallest_encoding(inner: bytes) -> tuple[bytes, tuple[int, int]]:
    best = None
    for level, mem in ENCODERS:
        stream = _deflate(inner, level, mem)
        if best is None or len(stream) < len(best[0]):
            best = (stream, (level, mem))
    return best


def fit_page(blob: bytes, page: int, new_inner: bytes, headroom_ratio: float = 0.0) -> tuple[bytes, dict]:
    """Refit one edited page into its slot, or refuse (copying the blob)."""
    buf = bytearray(blob)
    row = fit_page_inplace(buf, page, new_inner, headroom_ratio)
    return bytes(buf), row


def fit_page_inplace(buf: bytearray, page: int, new_inner: bytes, headroom_ratio: float) -> dict:
    """Refit one edited page into its slot in ``buf``, or refuse.

    Returns the budget row. Raises :class:`FitError` (with the row) when the
    page cannot stay inside ``slot - headroom``; ``buf`` is then unchanged.
    """
    stream_len, slot, setting, _ = slot_at(buf, page)
    headroom = math.ceil(headroom_ratio * stream_len)
    limit = slot - headroom
    row = {"page": page, "stream": stream_len, "slot": slot, "headroom": headroom,
           "headroom_ratio": headroom_ratio,
           "limit": limit, "encoder": None, "new_stream": None, "decision": None}
    cand = None
    if setting is not None:
        # The factory encoder first: an unchanged page then keeps its bytes.
        same = _deflate(new_inner, *setting)
        if len(same) <= limit:
            cand = (same, setting)
    if cand is None:
        cand = smallest_encoding(new_inner)
    stream, enc = cand
    row["new_stream"] = len(stream)
    row["encoder"] = {"level": enc[0], "memLevel": enc[1]}
    if len(stream) > limit:
        row["decision"] = "refuse"
        raise FitError(f"page {page:#x}: stream {len(stream)} > limit {limit} "
                       f"(slot {slot}, headroom {headroom})", row)
    row["decision"] = "fit"
    buf[page:page + slot] = stream + bytes(slot - len(stream))
    return row


# ---------------------------------------------------------------------------
# edits


def name_edits(inner: bytes) -> list[dict]:
    """Same-length replacement candidates: one per ``NAME@`` in the page."""
    edits = []
    for m in NAME_RE.finditer(inner):
        old = m.group()[:-1]
        edits.append({"at": m.start(), "old": old.decode("latin-1")})
    return edits


def generated_name(key: str, old: str) -> str:
    """Deterministic replacement with the same length and mixed content."""
    digest = hashlib.sha256(f"{key}:{old}".encode()).hexdigest().upper()
    alphabet = "".join(ch for ch in digest if ch.isalnum())
    text = ("OSM2 " + alphabet)[: len(old)]
    return text


def apply_edits(inner: bytes, edits: list[dict]) -> bytes:
    out = bytearray(inner)
    for e in edits:
        old, new = e["old"].encode("latin-1"), e["new"].encode("latin-1")
        if len(old) != len(new):
            raise PageError(f"edit at {e['at']:#x}: length {len(new)} != {len(old)}")
        if inner[e["at"]:e["at"] + len(old)] != old:
            raise PageError(f"edit at {e['at']:#x}: {old!r} not there")
        if inner[e["at"] + len(old)] != NAME_END:
            raise PageError(f"edit at {e['at']:#x}: not followed by '@'")
        out[e["at"]:e["at"] + len(old)] = new
    return bytes(out)


# ---------------------------------------------------------------------------
# calibration


def calibrate_pair(blob: bytes) -> list[dict]:
    """Stock-zlib overhead of unchanged pages: best re-encode minus factory."""
    rows = []
    for page, stream_len, inner in find_pages(blob):
        best, enc = smallest_encoding(inner)
        rows.append({"page": page, "stream": stream_len, "best": len(best),
                     "overhead": len(best) - stream_len,
                     "encoder": {"level": enc[0], "memLevel": enc[1]}})
    return rows


def _calibrate_one(cmp_path: Path) -> tuple[str, dict]:
    _, _, _, _, blob = read_pair(cmp_path, cmp_path.with_suffix(".ind"))
    rows = calibrate_pair(blob)
    over = [r["overhead"] for r in rows]
    entry = {
        "pages": len(rows),
        "names": sum(len(name_edits(inner)) for _, _, inner in find_pages(blob)),
        "max_overhead": max(over) if over else 0,
        "pages_overhead_gt0": sum(1 for o in over if o > 0),
        "rows": rows,
    }
    return cmp_path.name, entry


def cmd_calibrate(args) -> int:
    from concurrent.futures import ProcessPoolExecutor
    paths = sorted(Path(args.pairs).glob("POINT*.DAT.cmp"))
    report = {}
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for name, entry in pool.map(_calibrate_one, paths):
            report[name] = entry
            print(f"{name}: {entry['pages']} pages, {entry['names']} names, max stock "
                  f"overhead {entry['max_overhead']} B, {entry['pages_overhead_gt0']} "
                  f"pages above factory", flush=True)
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1), encoding="utf-8")
    return 0


# ---------------------------------------------------------------------------
# build


def build_pair(cmp_path: Path, headroom_ratio: float, key_prefix: str):
    ind_path = cmp_path.with_suffix(".ind")
    usize, chunk_size, offsets, packed, blob = read_pair(cmp_path, ind_path)
    new_blob = bytearray(blob)
    rows, refused, names_total, names_applied = [], [], 0, 0
    for page, _, inner in find_pages(blob):
        edits = name_edits(inner)
        if not edits:
            continue
        for e in edits:
            e["new"] = generated_name(f"{key_prefix}:{page}:{e['at']}", e["old"])
        names_total += len(edits)
        new_inner = apply_edits(inner, edits)
        try:
            row = fit_page_inplace(new_blob, page, new_inner, headroom_ratio)
        except FitError as exc:
            rows.append(exc.row)
            refused.append({"page": page, "edits": len(edits), "reason": str(exc)})
            continue
        row["edits"] = len(edits)
        rows.append(row)
        names_applied += len(edits)
    new_blob = bytes(new_blob)
    cmp_new, ind_new = write_pair(packed, offsets, usize, chunk_size, blob, new_blob)
    return {"file": cmp_path.name, "pages": rows, "refused": refused,
            "names_found": names_total, "names_applied": names_applied,
            "blob_changed": blob != new_blob}, cmp_new, ind_new, blob, new_blob


def _build_one(job: tuple[str, float, str, bool]) -> dict:
    """Build one pair; write its files into ``outdir`` and return its summary."""
    path, headroom_ratio, outdir, keep_budget = job
    cmp_path = Path(path)
    info, cmp_new, ind_new, _, _ = build_pair(cmp_path, headroom_ratio, cmp_path.name)
    out = Path(outdir)
    if info["blob_changed"]:
        (out / cmp_path.name).write_bytes(cmp_new)
        (out / cmp_path.with_suffix(".ind").name).write_bytes(ind_new)
    if info["refused"]:
        (out / f"{cmp_path.name}.refused.json").write_text(
            json.dumps(info["refused"], indent=1), encoding="utf-8")
    if keep_budget:
        (out / f"{cmp_path.name}.budget.json").write_text(
            json.dumps(info["pages"], indent=1), encoding="utf-8")
    summary = {k: v for k, v in info.items() if k != "pages"}
    summary["fit_pages"] = sum(1 for r in info["pages"] if r["decision"] == "fit")
    summary["refused_pages"] = len(info["refused"])
    print(f"{cmp_path.name}: names {info['names_applied']}/{info['names_found']} applied, "
          f"pages refused {len(info['refused'])}", flush=True)
    return summary


def cmd_build(args) -> int:
    from concurrent.futures import ProcessPoolExecutor
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    paths = sorted(Path(args.pairs).glob("POINT*.DAT.cmp"))
    jobs = [(str(p), args.headroom, str(outdir), bool(args.json)) for p in paths]
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        summary = list(pool.map(_build_one, jobs))
    changed = [s["file"] for s in summary if s["blob_changed"]]
    if args.image and changed:
        card = outdir / "card.img"
        subprocess.run(["cp", "--reflink=auto", args.image, str(card)], check=True)
        imgpatch = str(Path(__file__).with_name("imgpatch.py"))
        for name in changed:
            for fname in (name, Path(name).with_suffix(".ind").name):
                subprocess.run([sys.executable, imgpatch, "--image", str(card),
                                "--file", f"REFER001/{fname}",
                                "--from", str(outdir / fname), "--allow-resize", "--json"],
                               check=True, stdout=subprocess.DEVNULL)
        print(f"card: {card} patched with {len(changed)} pairs", flush=True)
    total = sum(s["names_found"] for s in summary)
    applied = sum(s["names_applied"] for s in summary)
    refused = sum(s["refused_pages"] for s in summary)
    print(f"total: {applied}/{total} names applied; refused pages {refused}")
    if args.json:
        Path(args.json).write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return 0


def _inner_at(blob: bytes, page: int) -> bytes:
    try:
        inner, _ = cmpind_codec.decompress_stream_at(blob, page, window=WINDOW)
        return inner
    except cmpind_codec.FormatError as exc:
        raise PageError(str(exc)) from exc


def _changed_offsets(a: bytes, b: bytes, block: int = 1 << 16) -> list[int]:
    """Offsets where ``a`` and ``b`` differ; equal blocks are skipped fast."""
    out = []
    for start in range(0, min(len(a), len(b)), block):
        if a[start:start + block] != b[start:start + block]:
            for i in range(start, min(start + block, len(a), len(b))):
                if a[i] != b[i]:
                    out.append(i)
    if len(a) != len(b):
        raise PageError("decoded size changed")
    return out


def _verify_one(job: tuple[str, str]) -> dict:
    """Check one built pair against its factory pair in the decoded domain.

    Checks: (1) every changed byte lies inside a fitted page's slot; (2) inside
    each fitted page the bytes that changed lie inside a name span, and every
    name span that changed reads back as the new name followed by ``@``.
    """
    factory_cmp, built_dir = job
    cmp_path = Path(factory_cmp)
    _, _, _, _, old = read_pair(cmp_path, cmp_path.with_suffix(".ind"))
    built_cmp = Path(built_dir) / cmp_path.name
    new = read_pair(built_cmp, built_cmp.with_suffix(".ind"))[4] if built_cmp.exists() else old
    budget = Path(built_dir) / f"{cmp_path.name}.budget.json"
    rows = json.loads(budget.read_text(encoding="utf-8")) if budget.exists() else []
    fit = sorted((r for r in rows if r["decision"] == "fit"), key=lambda r: r["page"])
    spans = [(r["page"], r["page"] + r["slot"]) for r in fit]
    changed = _changed_offsets(old, new)
    outside = sum(1 for i in changed if not any(lo <= i < hi for lo, hi in spans))
    names_checked = names_bad = 0
    length_hist: dict[int, int] = {}
    for r in fit:
        inner_old = _inner_at(old, r["page"])
        inner_new = _inner_at(new, r["page"])
        if len(inner_old) != len(inner_new):
            names_bad += 1
            continue
        spans_in = [(e["at"], e["at"] + len(e["old"].encode("latin-1")))
                    for e in name_edits(inner_old)]
        for i, (a, b) in enumerate(zip(inner_old, inner_new)):
            if a != b and not any(lo <= i < hi for lo, hi in spans_in):
                names_bad += 1
        for lo, hi in spans_in:
            if inner_new[lo:hi] != inner_old[lo:hi]:
                names_checked += 1
                length_hist[hi - lo] = length_hist.get(hi - lo, 0) + 1
                key = f"{cmp_path.name}:{r['page']}:{lo}"
                old_text = inner_old[lo:hi].decode("latin-1")
                if (inner_new[hi:hi + 1] != bytes([NAME_END])
                        or inner_new[lo:hi].decode("latin-1") != generated_name(key, old_text)):
                    names_bad += 1
    return {"file": cmp_path.name, "changed_bytes": len(changed), "outside_slots": outside,
            "fit_pages": len(fit), "refused_pages": sum(1 for r in rows if r["decision"] == "refuse"),
            "names_read_back": names_checked, "name_check_failures": names_bad,
            "name_length_hist": {str(k): v for k, v in sorted(length_hist.items())}}


def cmd_verify(args) -> int:
    from concurrent.futures import ProcessPoolExecutor
    paths = sorted(Path(args.factory).glob("POINT*.DAT.cmp"))
    jobs = [(str(p), args.built) for p in paths]
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(_verify_one, jobs))
    for r in results:
        print(f"{r['file']}: changed bytes {r['changed_bytes']}, outside fitted slots "
              f"{r['outside_slots']}, fit pages {r['fit_pages']}, refused {r['refused_pages']}, "
              f"names read back {r['names_read_back']}, failures {r['name_check_failures']}",
              flush=True)
    bad = sum(r["outside_slots"] + r["name_check_failures"] for r in results)
    print("verify: PASS" if bad == 0 else f"verify: FAIL ({bad})")
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1), encoding="utf-8")
    return 0 if bad == 0 else 1


# ---------------------------------------------------------------------------
# geometry budget (M5.75)
#
# The name-page slot model above has a direct analogue in parcel geometry: a
# generated 0x00fa road record must stay inside its parcel's fixed slot, or the
# tile writer has to append a new block (tilewriter.splice_factory's `appended`
# branch).  This section measures the trade between Douglas-Peucker tolerance
# and the real bytes `tilewriter.build_road_record` produces, on a synthetic
# town only.  No vendor bytes are read here; `geom-stats` reads a factory tile
# outside the repo solely to calibrate the byte budget.


#: Road levels that ``tilewriter.PARCEL_DEG`` maps to parcels.  Levels 3-5 are
#: land/coast levels whose simplify is in degrees (profile ``[land]``), so a
#: metre-based parcel-geometry budget does not apply to them.
GEOM_LEVELS = (1, 2)
#: Base tolerances in metres at level 1; level 2 scales them by the parcel-width
#: ratio derived from ``clarion_bg.parcel_geo``.
GEOM_TOLERANCES = (0.0, 0.5, 1.0, 2.0, 2.5, 3.0, 5.0, 8.0, 12.0, 20.0)
DEFAULT_GEOM_CELL = "B50R058R"
#: Mean earth radius and degrees->metres at the equator, for the DP metric.
EARTH_RADIUS_M = 6_371_008.8
METRES_PER_DEG = 111_320.0


class BudgetError(ValueError):
    """A geometry invariant of the sweep or the budget check was broken."""


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = math.radians(a[1]), math.radians(a[0])
    lat2, lon2 = math.radians(b[1]), math.radians(b[0])
    h = (math.sin((lat2 - lat1) / 2.0) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2.0) ** 2)
    return 2.0 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def _xy_m(point: tuple[float, float], lat0: float) -> tuple[float, float]:
    """Local equirectangular metres; adequate for a one-town sweep."""
    return (point[0] * METRES_PER_DEG * math.cos(math.radians(lat0)),
            point[1] * METRES_PER_DEG)


def _perp_m(a: tuple[float, float], b: tuple[float, float],
            p: tuple[float, float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0.0 and dy == 0.0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
    t = min(1.0, max(0.0, t))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def dp_simplify(points, tolerance_m: float):
    """Douglas-Peucker on lon/lat; return (kept points, max error in metres).

    The first and last point are always kept (a closed ring keeps its repeated
    endpoint).  ``max error`` is the largest perpendicular distance of any
    *removed* vertex to the segment that replaced it, so it is a directly
    reportable "visible deviation" in metres.
    """
    pts = list(points)
    if tolerance_m <= 0.0 or len(pts) <= 2:
        return pts, 0.0
    lat0 = sum(p[1] for p in pts) / len(pts)
    metric = [_xy_m(p, lat0) for p in pts]
    keep = {0, len(pts) - 1}
    stack = [(0, len(pts) - 1)]
    errors: list[float] = []
    while stack:
        first, last = stack.pop()
        worst, index = -1.0, None
        for k in range(first + 1, last):
            distance = _perp_m(metric[first], metric[last], metric[k])
            if distance > worst:
                worst, index = distance, k
        if index is None:
            continue
        if worst > tolerance_m:
            keep.add(index)
            stack.append((first, index))
            stack.append((index, last))
        else:
            errors.append(worst)
    return [pts[i] for i in sorted(keep)], (max(errors) if errors else 0.0)


def densify(points, step_m: float, wiggle_m: float):
    """Insert deterministic sinusoidal curvature into a polyline.

    The seed-1 town's ways are 2-point segments (EXP M5.76), so Douglas-Peucker
    alone has no interior vertex to remove.  This transform is the synthetic
    "street grid with curves" the sweep needs: one sine wiggle of amplitude
    ``wiggle_m`` per ``step_m`` of arc.  It is a pure function of the input.
    """
    pts = list(points)
    if step_m <= 0.0 or wiggle_m <= 0.0:
        return pts
    out: list[tuple[float, float]] = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        length = _haversine_m(a, b)
        count = max(1, int(math.ceil(length / step_m)))
        dx, dy = b[0] - a[0], b[1] - a[1]
        norm = math.hypot(dx, dy)
        px, py = (-dy / norm, dx / norm) if norm else (0.0, 0.0)
        lat0 = (a[1] + b[1]) / 2.0
        for step in range(1, count):
            fraction = step / count
            offset = wiggle_m * math.sin(2.0 * math.pi * fraction) / METRES_PER_DEG
            out.append((
                a[0] + dx * fraction + px * offset / math.cos(math.radians(lat0)),
                a[1] + dy * fraction + py * offset,
            ))
        out.append(b)
    return out


def _toml_scalars(text: str, section: str) -> dict[str, str]:
    """Read scalar ``key = value`` lines of one TOML section.

    The compiler profile only uses flat scalars in the two sections we need; a
    small reader keeps this tool Python 3.10 compatible (``tomllib`` is 3.11+).
    """
    out: dict[str, str] = {}
    active = False
    for line in text.splitlines():
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        if item.startswith("[") and item.endswith("]"):
            active = item[1:-1].strip() == section
            continue
        if not active or "=" not in item:
            continue
        key, value = item.split("=", 1)
        out[key.strip()] = value.split(" #", 1)[0].strip()
    return out


def read_geom_profile(path: str | Path) -> dict[str, float | int]:
    """Load the chosen tolerances and byte budget from a compiler profile."""
    text = Path(path).read_text(encoding="utf-8")
    roads = _toml_scalars(text, "roads")
    budget = _toml_scalars(text, "geometry_budget")
    return {
        "level_1_m": float(roads["simplify_metres"]),
        "level_2_m": float(roads["l2_simplify_metres"]),
        "max_record_bytes": int(budget["max_record_bytes"]),
        "densify_step_m": float(budget["densify_step_m"]),
        "densify_wiggle_m": float(budget["densify_wiggle_m"]),
    }


def level_scale(cell: str, level: int) -> float:
    """Parcel-width ratio ``width(level) / width(1)`` from ``parcel_geo``."""
    import clarion_bg  # noqa: E402  (lazy: only the geom subcommand needs it)
    import tilewriter  # noqa: E402

    y0, x0 = tilewriter.cell_mesh(cell)

    def width(which: int) -> float:
        _lon, lat, span, _height = clarion_bg.parcel_geo(which, y0, x0, 0, 0)
        return span * METRES_PER_DEG * math.cos(math.radians(lat))

    return width(level) / width(1)


def geom_rows(ways, cell: str, tolerances, profile: dict,
              levels=GEOM_LEVELS, country: int = 616) -> list[dict]:
    """One row per (level, base tolerance) with real writer byte counts."""
    import tilewriter  # noqa: E402

    table, _source = tilewriter.load_class_table(None)
    scales = {level: level_scale(cell, level) for level in levels}
    dense = []
    for way in ways:
        curved = dict(way)
        curved["points"] = densify(
            way["points"], profile["densify_step_m"],
            profile["densify_wiggle_m"])
        dense.append(curved)
    rows: list[dict] = []
    for level in levels:
        scale = scales[level]
        for base in tolerances:
            simplified, max_error = [], 0.0
            for way in dense:
                points, error = dp_simplify(way["points"], base * scale)
                max_error = max(max_error, error)
                item = dict(way)
                item["points"] = points
                simplified.append(item)
            runs = tilewriter.ways_to_runs(simplified, level, table, cell)
            kept = total = largest = parcels = over = 0
            for parcel in sorted(runs):
                built = tilewriter.build_road_record(
                    level, parcel, runs[parcel], table, country,
                    write_names=False)
                if built is None:
                    continue
                info = built[3]
                parcels += 1
                kept += info["points"]
                total += info["compressed_bytes"]
                largest = max(largest, info["compressed_bytes"])
                over += int(info["compressed_bytes"] > profile["max_record_bytes"])
            rows.append({
                "level": level,
                "scale": scale,
                "tol_base": float(base),
                "tol_m": base * scale,
                "kept_vertices": kept,
                "total_bytes": total,
                "max_parcel_bytes": largest,
                "max_error_m": max_error,
                "parcels": parcels,
                "over_budget": over,
            })
    return rows


def check_monotonic(rows) -> None:
    """Falsifier guard: bytes must not rise as tolerance rises."""
    for level in sorted({row["level"] for row in rows}):
        seq = [row["total_bytes"] for row in sorted(
            (r for r in rows if r["level"] == level),
            key=lambda r: r["tol_base"])]
        for low, high in zip(seq, seq[1:]):
            if high > low:
                raise BudgetError(
                    f"level {level}: bytes rose with tolerance ({low} -> {high})")


def check_budget(rows, budget: int | None = None) -> None:
    """Fail loudly when any parcel exceeds the record budget."""
    bad = [row for row in rows if row["over_budget"]]
    if bad:
        first = bad[0]
        raise FitError(
            f"{len(bad)} sweep row(s) over budget: first level {first['level']} "
            f"tol {first['tol_m']:g} m, max parcel {first['max_parcel_bytes']} B "
            f"> {budget} B")


def render_geom_table(rows, profile: dict) -> str:
    budget = profile["max_record_bytes"]
    out = [
        f"geometry budget: profile max_record_bytes={budget} B; "
        f"levels {','.join(str(level) for level in sorted({r['level'] for r in rows}))}",
        "lvl scale tol_base   tol_m  kept total_B max_parcel_B max_err_m parcels over_budget",
    ]
    for row in rows:
        chosen = profile["level_1_m"] if row["level"] == 1 else profile["level_2_m"]
        default = row["tol_m"] == chosen
        out.append(
            "%3d %5g %8g %7g %5d %7d %12d %9.2f %7d %10d%s" % (
                row["level"], row["scale"], row["tol_base"], row["tol_m"],
                row["kept_vertices"], row["total_bytes"], row["max_parcel_bytes"],
                row["max_error_m"], row["parcels"], row["over_budget"],
                "  <- default" if default else ""))
    for level in sorted({row["level"] for row in rows}):
        first = next((r for r in sorted(
            (r for r in rows if r["level"] == level), key=lambda r: r["tol_base"])
            if r["over_budget"] == 0), None)
        point = f"{first['tol_m']:g} m (base {first['tol_base']:g} m)" if first else "none in sweep"
        out.append(f"overflow point level {level}: {point}")
    return "\n".join(out)


def cmd_geom(args) -> int:
    import tilewriter  # noqa: E402

    profile = read_geom_profile(args.profile)
    if args.budget is not None:
        profile["max_record_bytes"] = int(args.budget)
    if args.step is not None:
        profile["densify_step_m"] = float(args.step)
    if args.wiggle is not None:
        profile["densify_wiggle_m"] = float(args.wiggle)
    tolerances = ([float(value) for value in args.tolerances.split(",")]
                  if args.tolerances else list(GEOM_TOLERANCES))
    ways, stats = tilewriter.load_imf(args.town, args.cell)
    rows = geom_rows(ways, args.cell, tolerances, profile)
    for row in rows:
        row["budget"] = profile["max_record_bytes"]
    print(render_geom_table(rows, profile))
    print(f"input ways={stats['ways']} nodes={stats['nodes']} cell={args.cell}")
    try:
        check_monotonic(rows)
        print("monotonic: PASS (bytes never rise with tolerance)")
    except BudgetError as exc:
        print(f"monotonic: FAIL ({exc})")
        return 1
    rc = 0
    if args.check:
        try:
            check_budget(rows, profile["max_record_bytes"])
            print(f"budget check: PASS (all parcels <= {profile['max_record_bytes']} B)")
        except FitError as exc:
            print(f"budget check: FAIL ({exc})")
            rc = 1
    if args.json:
        Path(args.json).write_text(
            json.dumps({"profile": profile, "rows": rows}, indent=2),
            encoding="utf-8")
        print(f"json: {args.json}")
    return rc


def cmd_geom_stats(args) -> int:
    """One-off calibration: even-pair road blocks of a factory directory."""
    import clarion_tile  # noqa: E402
    import tilewriter  # noqa: E402

    y_text, x_text = args.dir.split(",")
    want = (int(y_text, 0), int(x_text, 0))
    tile = clarion_tile.read_tile(Path(args.tile).read_bytes())
    lengths: list[int] = []
    for section in tile["sections"]:
        if section["id"] != 1:
            continue
        for entry in section["levels"]:
            if entry["level"] != 1:
                continue
            for directory in entry["dirs"]:
                if (directory["y"], tilewriter.dir_x0(directory)) != want:
                    continue
                for slot in directory["slots"].values():
                    for record in slot["recs"]:
                        if record["k"] % 2 == 0:
                            lengths.append(len(record["raw"]))
    if not lengths:
        print(f"error: no level-1 road records at dir {want}", file=sys.stderr)
        return 1
    lengths.sort()
    count = len(lengths)
    stats = {
        "tile": str(args.tile), "dir": list(want), "count": count,
        "min": lengths[0], "q1": lengths[count // 4],
        "median": (lengths[count // 2 - 1] + lengths[count // 2]) / 2,
        "q3": lengths[3 * count // 4], "max": lengths[-1],
        "mean": round(sum(lengths) / count, 1),
        "le_256": sum(1 for value in lengths if value <= 256),
        "le_q1": sum(1 for value in lengths if value <= lengths[count // 4]),
    }
    print("factory road block lengths: "
          + " ".join(f"{key}={value}" for key, value in stats.items()))
    if args.json:
        Path(args.json).write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return 0


# ---------------------------------------------------------------------------
# selftest


def selftest() -> int:
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(("OK  " if ok else "FAIL") + " " + name + (f" ({detail})" if detail else ""))

    import random
    rng = random.Random(7)
    # Synthetic abutting pair of name pages: page A's stream is followed
    # immediately by page B (no zero padding, so A's slot is its own length).
    # 0x00 0x62 is record framing: the name starts on a non-name byte.
    inner_a = (b"ABCDEFGH" * 300) + b"\x00\x62" + b"NAME ONE@" + (b"XY" * 300)
    inner_b = b"DEST PAGE@" * 200
    stream_a = _deflate(inner_a, 6, 8)
    stream_b = _deflate(inner_b, 6, 8)
    blob = bytearray(b"\x00" * 0x200) + stream_a + stream_b + b"\x01" * 16
    page_a = 0x200
    page_b = page_a + len(stream_a)

    cons, slot, setting, _ = slot_at(bytes(blob), page_a)
    check("abut: slot equals stream length when next byte is non-zero",
          cons == len(stream_a) and slot == len(stream_a), f"slot {slot}")
    check("positive control: factory encoder reproduces stream",
          setting == (6, 8), f"setting {setting}")

    # Positive: unchanged inner refits into the same bytes (no-op).
    same_blob, row = fit_page(bytes(blob), page_a, inner_a, 0)
    check("no-op edit: blob byte-identical", same_blob == bytes(blob),
          f"decision {row['decision']}")

    # Positive: a same-length edit that keeps the stream inside the slot.
    # The replacement repeats earlier bytes, so the stream does not grow.
    edited = inner_a.replace(b"NAME ONE@", b"ABCDEFGH@")
    new_blob, row = fit_page(bytes(blob), page_a, edited, 0)
    stream_new = bytes(new_blob)[page_a:page_a + row["slot"]]
    check("neighbour page B untouched after a fitting edit",
          new_blob[page_b:page_b + len(stream_b)] == stream_b)
    check("fit writes the page inside its slot", zlib.decompress(stream_new[:row["new_stream"]]) == edited,
          f"stream {row['new_stream']} slot {row['slot']}")

    # Negative: an incompressible replacement of the same length overruns the
    # slot; it must be refused and the blob left unchanged.
    noise = bytes(rng.randrange(256) for _ in range(len(inner_a)))
    noise = bytes(b if b != NAME_END else 0x41 for b in noise)
    try:
        fit_page(bytes(blob), page_a, noise, 0)
        check("refuse: incompressible page is refused", False)
    except FitError as exc:
        check("refuse: incompressible page is refused", exc.row["decision"] == "refuse",
              f"stream {exc.row['new_stream']} > slot {exc.row['slot']}")

    # Headroom: ratio 1.0 keeps the whole slot free (limit 0), so the same
    # edit is refused; ratio 0.04 keeps 3 B free and the edit still fits.
    try:
        fit_page(bytes(blob), page_a, edited, 1.0)
        check("headroom: edit refused when headroom leaves no room", False)
    except FitError as exc:
        check("headroom: edit refused when headroom leaves no room",
              exc.row["limit"] == 0 and exc.row["decision"] == "refuse", str(exc.row["limit"]))
    _, row4 = fit_page(bytes(blob), page_a, edited, 0.04)
    check("headroom: 4 % of the stream is kept free and the edit still fits",
          row4["decision"] == "fit" and row4["headroom"] == math.ceil(0.04 * row4["stream"]),
          f"headroom {row4['headroom']} limit {row4['limit']}")

    # Zero padding: a page followed by zeros gets the padded slot and a
    # longer stream may use it, but only over zero bytes.
    blob_z = bytearray(b"\x00" * 0x200) + stream_a + b"\x00" * 0x100 + b"\x01" * 4
    cons_z, slot_z, _, _ = slot_at(bytes(blob_z), page_a)
    check("padding: slot rounds up to 0x100 over zero bytes",
          slot_z == ((len(stream_a) + 0xFF) & ~0xFF) and cons_z == len(stream_a),
          f"slot {slot_z}")
    grown = inner_a + bytes(rng.randrange(0x41, 0x5B) for _ in range(12))
    bz, rowz = fit_page(bytes(blob_z), page_a, grown, 0)
    check("padding: refit stays inside the padded slot, next bytes intact",
          bz[page_a + slot_z:] == bytes(blob_z)[page_a + slot_z:]
          and len(bz) == len(blob_z), f"decision {rowz['decision']}")

    # Name edit check: a name not followed by '@' is refused.
    try:
        apply_edits(b"NAME ONE!" + inner_a, [{"at": 0, "old": "NAME ONE", "new": "NAME TWO"}])
        check("edit: a name not followed by '@' is refused", False)
    except PageError:
        check("edit: a name not followed by '@' is refused", True)

    # Name extraction and generated names keep their length.
    found = name_edits(inner_a)
    check("names: one NAME@ found in the synthetic page",
          [e["old"] for e in found] == ["NAME ONE"], str(found))
    g = generated_name("k", "NAME ONE")
    check("names: generated replacement keeps the length", len(g) == len("NAME ONE"), g)

    # find_pages recovers both abutting streams.
    got = find_pages(bytes(blob))
    check("find_pages: both abutting streams found",
          [(o, n) for o, n, _ in got] == [(page_a, len(stream_a)), (page_b, len(stream_b))],
          str([(hex(o), n) for o, n, _ in got]))

    # -- geometry budget (M5.75): pure-function controls and a tiny sweep ----
    base_line = [(17.0, 51.0), (17.004, 51.0)]
    curved = densify(base_line, 25.0, 12.0)
    check("geom: densify is deterministic and adds curvature",
          len(curved) > 2 and curved == densify(base_line, 25.0, 12.0),
          f"{len(curved)} points")
    check("geom: zero tolerance is the identity", dp_simplify(curved, 0.0)[0] == curved)
    kept, error = dp_simplify(curved, 20.0)
    check("geom: DP keeps endpoints and bounds the error",
          kept[0] == curved[0] and kept[-1] == curved[-1] and error <= 20.0 + 1e-6,
          f"{len(curved)}->{len(kept)} err {error:.2f} m")
    sample_profile = (
        "[roads]\nsimplify_metres = 3\nl2_simplify_metres = 12\n"
        "[geometry_budget]\nmax_record_bytes = 372\n"
        "densify_step_m = 25\ndensify_wiggle_m = 12\n")
    check("geom: profile scalar reader",
          _toml_scalars(sample_profile, "roads").get("simplify_metres") == "3"
          and _toml_scalars(sample_profile, "geometry_budget").get("max_record_bytes") == "372")
    ok_row = {"level": 1, "over_budget": 0, "tol_m": 3.0, "tol_base": 3.0,
              "max_parcel_bytes": 300, "total_bytes": 100}
    check_budget([ok_row], 372)
    check("geom: within-budget parcel passes the guard", True)
    try:
        check_budget([dict(ok_row, over_budget=1, max_parcel_bytes=500)], 372)
        check("geom: over-budget parcel fails the guard", False)
    except FitError as exc:
        check("geom: over-budget parcel fails the guard", "500 B > 372 B" in str(exc))
    try:
        check_monotonic([dict(ok_row, total_bytes=100), dict(ok_row, total_bytes=101)])
        check("geom: rising bytes fail the falsifier guard", False)
    except BudgetError:
        check("geom: rising bytes fail the falsifier guard", True)

    import clarion_bg  # noqa: E402
    import tilewriter  # noqa: E402
    cell = DEFAULT_GEOM_CELL
    y0, x0 = tilewriter.cell_mesh(cell)
    lon0, lat0, span, height = clarion_bg.parcel_geo(1, y0, x0, 16, 16)
    town_way = {
        "id": "wtest", "highway": "residential", "name": "",
        "points": densify([(lon0 + 0.1 * span, lat0 + 0.5 * height),
                           (lon0 + 0.9 * span, lat0 + 0.5 * height)], 25.0, 12.0),
    }
    tiny_profile = {"level_1_m": 20.0, "level_2_m": 80.0, "max_record_bytes": 100,
                    "densify_step_m": 25.0, "densify_wiggle_m": 12.0}
    tiny = geom_rows([town_way], cell, (0.0, 20.0), tiny_profile)
    check("geom: sweep produces one row per level and tolerance", len(tiny) == 4)
    check("geom: bytes fall as tolerance rises (positive control)",
          tiny[0]["total_bytes"] > tiny[1]["total_bytes"],
          f"{tiny[0]['total_bytes']} -> {tiny[1]['total_bytes']} B")
    check("geom: dense parcel trips the budget guard (negative control)",
          tiny[0]["over_budget"] > 0 and tiny[2]["over_budget"] > 0,
          f"over {tiny[0]['over_budget']}/{tiny[2]['over_budget']}")
    check("geom: level scale comes from parcel geometry",
          abs(level_scale(cell, 2) - 4.0) < 1e-9, f"scale {level_scale(cell, 2):g}")

    ok = all(results)
    print(f"selftest: {sum(results)}/{len(results)} checks passed")
    return 0 if ok else 1


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    v = sub.add_parser("verify")
    v.add_argument("--factory", required=True)
    v.add_argument("--built", required=True)
    v.add_argument("--jobs", type=int, default=3)
    v.add_argument("--json")
    c = sub.add_parser("calibrate")
    c.add_argument("--pairs", required=True)
    c.add_argument("--json")
    c.add_argument("--jobs", type=int, default=4)
    b = sub.add_parser("build")
    b.add_argument("--pairs", required=True)
    b.add_argument("--outdir", required=True)
    b.add_argument("--headroom", type=float, default=HEADROOM_RATIO,
                   help="fraction of the factory stream kept free (default %(default)s)")
    b.add_argument("--image")
    b.add_argument("--jobs", type=int, default=3)
    b.add_argument("--json")
    g = sub.add_parser("geom", help="sweep simplification tolerance against parcel bytes (M5.75)")
    g.add_argument("town", help="synthetic town JSONL (tools/osm_synth.py output)")
    g.add_argument("--profile", required=True, help="compiler profile with [roads] and [geometry_budget]")
    g.add_argument("--cell", default=DEFAULT_GEOM_CELL)
    g.add_argument("--tolerances", help="comma-separated level-1 tolerances in metres")
    g.add_argument("--budget", type=int, help="override the profile's max_record_bytes")
    g.add_argument("--step", type=float, help="override the densify step in metres")
    g.add_argument("--wiggle", type=float, help="override the densify amplitude in metres")
    g.add_argument("--check", action="store_true",
                   help="exit 1 when any parcel exceeds the record budget")
    g.add_argument("--json")
    s = sub.add_parser("geom-stats", help="calibrate the budget from a factory tile")
    s.add_argument("tile", help="path to a factory MAPAL001/BxxRyyR.DAT outside the repo")
    s.add_argument("--cell", default=DEFAULT_GEOM_CELL)
    s.add_argument("--dir", default="84,940", help="directory Y,X (default %(default)s)")
    s.add_argument("--json")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "calibrate":
        return cmd_calibrate(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    if args.cmd == "build":
        return cmd_build(args)
    if args.cmd == "geom":
        return cmd_geom(args)
    if args.cmd == "geom-stats":
        return cmd_geom_stats(args)
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
