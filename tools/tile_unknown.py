#!/usr/bin/env python3
"""Rank the nonzero byte runs that ``map_signals.py`` leaves unexplained in a tile.

``tools/map_signals.py`` reports what fraction of a factory tile's nonzero
bytes past ``0x1000`` falls inside directory and slot spans (the union-of-spans
arithmetic in ``tile_explained_percent``).  On the EU 2011 card the lowest of
the three sample tiles is ``B48R058R`` (76.29 %).  This tool prints the
**complement** as a ranked table so a format task can take the largest block
instead of guessing:

* the baseline ranking uses the *same* union of ``clarion_tile`` directory
  ``(off, end)`` and slot ``(block_off, block_end)`` spans, so its percentage is
  not redefined;
* a second pass adds the ``s1_wide_dir`` row-block spans (M5.53/M5.54), which
  are real records the 512-byte ``clarion_tile`` reader steps over, to separate
  "already modelled" from "genuinely unexplained";
* a third pass adds the ``section4_wide`` row-block spans (M4.93), the 768-byte
  wide rows of section 4 the section-1 model does not cover;
* each range is attributed to a directory (section, level, kind) and an
  even/odd record using the wide-row record parts where available, else the
  slot-index parity; the first bytes are *described* (zlib signature, inflated
  length, first big-endian ``u16`` words), never dumped;
* M4.96 grades the **post-s1/s4 ``remaining`` set only** (the baseline mass is
  already attributed to ``s1_wide_dir``/``section4_wide``): every remaining gap
  gets a class letter and the classes partition its nonzero bytes.  Class ``d``
  is a section-table *metric span artifact*, not a new record class and not a
  rule-13 reader-VA claim; ``other`` is explicit so an injected control in a
  section-4/``0x1046`` context is never silently absorbed into class ``b``.

Usage::

    python3 tools/tile_unknown.py TILE.DAT [--top N] [--json]
    python3 tools/tile_unknown.py --factory-root ROOT [--top N]
    python3 tools/tile_unknown.py --selftest

``--factory-root`` selects the lowest-percentage tile from
``map_signals.TILE_NAMES`` with ``map_signals.tile_explained_percent``.  No
vendor bytes are embedded: the tool takes a path outside the checkout.

Exit codes: 0 ok, 1 the tile does not parse, 2 usage.  Stdlib only.
"""
from __future__ import annotations

import argparse
import bisect
import json
import sys
import zlib
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
for _p in (HERE / "ze0-viewer" / "tools_ze0", HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import clarion_tile  # noqa: E402

TABLE_BASE = 0x1000


def _nonzero(data: bytes, a: int, b: int) -> int:
    """Count nonzero bytes in ``data[a:b]`` (C-speed via bytes.count)."""
    if b <= a:
        return 0
    return (b - a) - data[a:b].count(0)


def merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping/adjacent half-open intervals, sorted by start."""
    out: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


# --------------------------------------------------------------------------
# baseline model: exactly the map_signals.tile_explained_percent arithmetic
# --------------------------------------------------------------------------


def baseline_spans(tile: dict) -> list[tuple[int, int]]:
    """Directory ``(off, end)`` + slot ``(block_off, block_end)`` spans."""
    spans: list[tuple[int, int]] = []
    for section in tile["sections"]:
        for level in section["levels"]:
            for directory in level["dirs"]:
                spans.append((directory["off"], directory["end"]))
                spans += [(s["block_off"], s["block_end"])
                          for s in directory["slots"].values()]
    return spans


def nonzero_gaps(data: bytes, merged: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Maximal ranges outside ``merged`` that contain at least one nonzero byte."""
    gaps: list[tuple[int, int]] = []
    prev = TABLE_BASE
    for start, end in merged:
        if start > prev and _nonzero(data, prev, start):
            gaps.append((prev, start))
        prev = max(prev, end)
    if prev < len(data) and _nonzero(data, prev, len(data)):
        gaps.append((prev, len(data)))
    return gaps


# --------------------------------------------------------------------------
# attribution: which directory / record owns a range (context at range start)
# --------------------------------------------------------------------------


def _wide_models(data: bytes, tile: dict) -> dict | None:
    """Parse section-1 level-1/2 directories with the M5.53/M5.54 row model.

    Returns ``None`` when ``s1_wide_dir`` is unavailable or a directory fails
    to parse (the baseline still works).  A mapping ``(si, li, di) -> model``.
    """
    try:
        import s1_wide_dir as wd  # noqa: E402
    except Exception:
        return None
    models: dict[tuple[int, int, int], Any] = {}
    try:
        for si, section in enumerate(tile["sections"]):
            if section["id"] != 1:
                continue
            for li, level in enumerate(section["levels"]):
                if level["level"] not in (1, 2):
                    continue
                for di, directory in enumerate(level["dirs"]):
                    models[(si, li, di)] = wd.parse_dir(
                        data, directory["off"], level["level"], check=False)
    except Exception:
        return None
    return models


def _s4_spans(data: bytes, tile: dict) -> list[tuple[int, int]]:
    """Section-4 level-1 row-block spans (M4.93); empty when the tool is absent.

    Kept separate from ``_wide_models`` so the baseline and s1-wide figures
    reported by M4.86 stay unchanged.
    """
    try:
        import section4_wide as s4  # noqa: E402
        return s4.row_block_spans(data, tile)
    except Exception:
        return []


def _context_marks(tile: dict, models: dict | None):
    """Sorted ``(offset, context)`` marks for nearest-preceding attribution.

    A context is ``(section_id, level, kind_hex, parity, part)``.  Wide-row
    directories contribute one mark per record part (even/sub*/odd); other
    directories contribute one mark per slot using the slot-index parity.
    """
    marks: list[tuple[int, tuple]] = []
    for si, section in enumerate(tile["sections"]):
        for li, level in enumerate(section["levels"]):
            for di, directory in enumerate(level["dirs"]):
                sid, lvl, kind = section["id"], level["level"], directory["kind"]
                khex = "0x%04x" % kind
                model = (models or {}).get((si, li, di))
                marks.append((directory["off"], (sid, lvl, khex, "dir", "dir")))
                if model is not None:
                    for row in model["rows"]:
                        q = row.get("block_off")
                        if q is None:
                            continue
                        for rec in row["records"]:
                            parity = "odd" if rec["part"] == "odd" else "even"
                            marks.append((q, (sid, lvl, khex, parity, rec["part"])))
                            q += len(rec["raw"])
                else:
                    for i, slot in directory["slots"].items():
                        parity = "even" if i % 2 == 0 else "odd"
                        marks.append((slot["block_off"],
                                      (sid, lvl, khex, parity, "slot%d" % i)))
    marks.sort(key=lambda m: m[0])
    return marks


CONTAINER = ("container", 0, "-", "other", "header/table")


def attribute(offset: int, marks: list[tuple[int, tuple]]) -> tuple:
    """Context of the block at ``offset``: the last mark at or before it."""
    offsets = [m[0] for m in marks]  # small enough; built once per call site
    i = bisect.bisect_right(offsets, offset) - 1
    return marks[i][1] if i >= 0 else CONTAINER


# --------------------------------------------------------------------------
# first-bytes shape (describe, never dump)
# --------------------------------------------------------------------------


def describe_shape(data: bytes, a: int, b: int) -> str:
    """One-line shape of the first *nonzero* bytes of a range (<= 4 words).

    A gap includes the zero pad before the next 256-byte boundary; skipping it
    makes the description name the record that actually occupies the range.
    """
    p = a
    while p < b and data[p] == 0:
        p += 1
    if b - p < 2:
        return "raw <2 B" if p < b else "all zero pad"
    if data[p:p + 2] != b"\x78\x9c":
        words = [data[p + i:p + i + 2].hex()
                 for i in range(0, min(8, b - p - 1), 2)]
        return "raw w=[" + ",".join("0x" + w for w in words) + "]"
    try:
        obj = zlib.decompressobj()
        plain = obj.decompress(data[p:min(b, p + (1 << 20))])
    except zlib.error as exc:  # pragma: no cover - corrupt fixture guard
        return "zlib 789c (error %s)" % exc
    n = len(plain)
    words = []
    for i in range(0, min(8, n - 1), 2):
        words.append("%04x" % ((plain[i] << 8) | plain[i + 1]))
    shape = "zlib 789c inflate=%dB" % n
    if words:
        shape += " w=[" + ",".join("0x" + w for w in words) + "]"
        if len(words) >= 3 and words[2] in ("00fa", "0009"):
            shape += " kind=0x%s" % words[2]
    if not obj.eof:
        shape += " (truncated in 1MiB)"
    return shape


# --------------------------------------------------------------------------
# M4.96 grading of the post-s1/s4 remaining set
# --------------------------------------------------------------------------

CLASSES = ("a", "b", "c", "d", "other")
CLASS_NOTE = {
    "a": "unparsed section-3/5 record block",
    "b": "M4.93 section-4 row-block residual",
    "c": "padding/slack (0xff fill)",
    "d": "section header table span (count-word bounded; reader=clarion_tile)",
    "other": "unclassified (injected control lands here)",
}


def count_word_bounded(data: bytes, span: tuple[int, int, int] | None) -> bool:
    """True iff ``u16@taddr == table_words`` and the span holds the bytes.

    A section header table is a named record block only when its first big-
    endian ``u16`` (the word count read by ``clarion_tile.read_tile``) equals
    the span's own word count, so ``[taddr, taddr + 2*count)`` is exactly the
    table.  This test can fail: overwriting that word breaks the bound (and
    makes the parser raise).  Zero-fill tails outside the span carry 0 nonzero
    bytes and are padding, not part of the class-d figure.
    """
    if span is None:
        return False
    _sid, ta, tb = span
    if ta + 2 > len(data):
        return False
    import struct
    count = struct.unpack_from(">H", data, ta)[0]
    return count == (tb - ta) // 2


def section_table_spans(tile: dict) -> list[tuple[int, int, int]]:
    """``(section id, taddr, taddr + 2*table_words)`` from the header table."""
    return [(s["id"], s["taddr"], s["taddr"] + 2 * s["table_words"])
            for s in tile["sections"]]


def directory_extents(tile: dict) -> list[tuple[int, int, int, int, int]]:
    """``(section, level, kind, off, off + 2*kind)`` for every directory."""
    out: list[tuple[int, int, int, int, int]] = []
    for section in tile["sections"]:
        for level in section["levels"]:
            for directory in level["dirs"]:
                kind = directory["kind"]
                out.append((section["id"], level["level"], kind,
                            directory["off"], directory["off"] + 2 * kind))
    return out


def grade_range(data: bytes, a: int, b: int, ctx: tuple,
                tables: list[tuple[int, int, int]],
                dirs: list[tuple[int, int, int, int, int]]) -> tuple:
    """Classify one remaining range; return ``(letter, note, inside, outside,
    overlaps, chosen_span)`` on **nonzero** bytes.

    Deterministic priority when a gap overlaps more than one span: ``d`` (the
    overlapping table span with the most inside nonzero bytes, then lowest
    ``(section, taddr)``), then ``b`` (inside a section-4 L1 ``0x1046+0x100n``
    directory extent), then ``a`` (inside a section-3/5 directory extent),
    then ``c`` (all nonzero bytes are ``0xff`` slack), else ``other``.

    The extent test for ``b`` is deliberate: the injected synthetic control has
    a nearest-preceding mark of section 4 / level 1 / ``0x1046`` but lies past
    that directory's extent, so a section+kind-only rule would silently absorb
    it into (b) (the M1.22 skip-set trap).  It must stay in ``other``.
    """
    total = _nonzero(data, a, b)
    overlap = []
    for sid, ta, tb in tables:
        if ta < b and a < tb:
            inside = _nonzero(data, max(a, ta), min(b, tb))
            overlap.append((inside, sid, ta, tb))
    overlap.sort(key=lambda o: (-o[0], o[1], o[2]))
    if overlap and overlap[0][0] > 0:
        inside, sid, ta, tb = overlap[0]
        note = "sec%d table taddr=%#x table_words=%d" % (sid, ta, (tb - ta) // 2)
        return "d", note, inside, total - inside, len(overlap), (sid, ta, tb)
    for sid, lvl, kind, lo, hi in dirs:
        if (sid == 4 and lvl == 1 and kind >= 0x1046
                and (kind - 0x1046) % 0x100 == 0 and lo < b and a < hi):
            return ("b", "sec4 L1 kind=%#x dir=%#x..%#x" % (kind, lo, hi),
                    0, total, 0, None)
    for sid, lvl, kind, lo, hi in dirs:
        if sid in (3, 5) and lo < b and a < hi:
            return ("a", "sec%d L%d kind=%#x dir=%#x..%#x" % (sid, lvl, kind, lo, hi),
                    0, total, 0, None)
    if total and not (set(data[a:b]) - {0, 0xff}):
        return "c", "0xff slack", 0, total, 0, None
    return "other", "no table/dir overlap", 0, total, 0, None


# --------------------------------------------------------------------------
# analysis
# --------------------------------------------------------------------------


def analyze(data: bytes) -> dict[str, Any]:
    tile = clarion_tile.read_tile(data)
    base_merged = merge_spans(baseline_spans(tile))
    total = _nonzero(data, TABLE_BASE, len(data))
    explained = sum(_nonzero(data, a, b) for a, b in base_merged)
    gaps = nonzero_gaps(data, base_merged)

    models = _wide_models(data, tile)
    wide_spans = []
    for model in (models or {}).values():
        for row in model["rows"]:
            if "block_off" in row and row["block_end"] > row["block_off"]:
                wide_spans.append((row["block_off"], row["block_end"]))
    wide_merged = merge_spans(baseline_spans(tile) + wide_spans)
    explained_wide = sum(_nonzero(data, a, b) for a, b in wide_merged)
    s4_spans = _s4_spans(data, tile)
    full_merged = merge_spans(baseline_spans(tile) + wide_spans + s4_spans)
    explained_full = sum(_nonzero(data, a, b) for a, b in full_merged)
    remaining = nonzero_gaps(data, full_merged)

    marks = _context_marks(tile, models)

    # Wide-row record parts with their byte spans, for parity by overlap: a
    # multi-megabyte gap spans many columns/rows, so the parity of its first
    # record alone would mislabel the whole block.
    parts: list[tuple[int, int, str]] = []
    for model in (models or {}).values():
        for row in model["rows"]:
            q = row.get("block_off")
            if q is None:
                continue
            for rec in row["records"]:
                parity = "odd" if rec["part"] == "odd" else "even"
                parts.append((q, q + len(rec["raw"]), parity))
                q += len(rec["raw"])
    parts.sort()

    def gap_parity(a: int, b: int, fallback: str) -> str:
        votes = {"even": 0, "odd": 0}
        for start, end, parity in parts:
            if start >= b:
                break
            if end > a:
                votes[parity] += min(end, b) - max(start, a)
        if votes["even"] == votes["odd"] == 0:
            return fallback
        return "even" if votes["even"] >= votes["odd"] else "odd"

    ranges = []
    for a, b in gaps:
        nz = _nonzero(data, a, b)
        ctx = attribute(a, marks)
        ranges.append({
            "start": a, "end": b, "span": b - a, "bytes": nz,
            "section": ctx[0], "level": ctx[1], "kind": ctx[2],
            "record": gap_parity(a, b, ctx[3]), "part": ctx[4],
            "modelled": ("s1_wide_dir" if any(ws < b and a < we for ws, we in wide_spans)
                         else "section4_wide" if any(ss < b and a < se for ss, se in s4_spans)
                         else "unmodelled"),
            "shape": describe_shape(data, a, b),
        })
    ranges.sort(key=lambda r: (-r["bytes"], r["start"]))

    # Section tables are read by clarion_tile but are not directory/slot spans;
    # name them so a small residual is not mislabelled as a wide-row record.
    tables = [(section["taddr"], section["taddr"] + 2 * section["table_words"],
               section["id"]) for section in tile["sections"]]
    rem = []
    for a, b in remaining:
        ctx = attribute(a, marks)
        for ta, tb, sid in tables:
            if ta < b and a < tb:
                ctx = (sid, 0, "table", "other", "section table")
                break
        rem.append({
            "start": a, "end": b, "bytes": _nonzero(data, a, b),
            "context": ctx,
            "shape": describe_shape(data, a, b),
        })
    rem.sort(key=lambda r: -r["bytes"])

    # M4.96: grade only the post-s1/s4 remaining set.  The baseline mass is
    # already attributed to s1_wide_dir/section4_wide and is never re-graded.
    tables = section_table_spans(tile)
    dirs = directory_extents(tile)
    class_bytes = {c: 0 for c in CLASSES}
    class_ranges = {c: 0 for c in CLASSES}
    for r in rem:
        letter, note, inside, outside, overlaps, chosen = grade_range(
            data, r["start"], r["end"], r["context"], tables, dirs)
        r["class"] = letter
        r["class_note"] = note
        r["inside_nz"] = inside
        r["outside_nz"] = outside
        r["table_overlaps"] = overlaps
        r["table_span"] = chosen
        r["block"] = ("section-table-header" if letter == "d"
                      and count_word_bounded(data, chosen) else "unclassified")
        r["count_word_bounded"] = count_word_bounded(data, chosen)
        class_bytes[letter] += r["bytes"]
        class_ranges[letter] += 1
    graded_sum = sum(class_bytes.values())
    structure = {
        "sections": [{
            "id": s["id"], "taddr": s["taddr"], "table_words": s["table_words"],
            "levels": [{"level": L["level"], "typ": L["typ"], "dirs": len(L["dirs"])}
                       for L in s["levels"]],
        } for s in tile["sections"]],
        "section_table_spans": [
            {"section": sid, "start": ta, "end": tb} for sid, ta, tb in tables],
    }

    return {
        "tile_bytes": len(data),
        "nonzero_tail": total,
        "baseline_explained": explained,
        "baseline_percent": round(100.0 * explained / total, 3) if total else 0.0,
        "wide_row_blocks": len(wide_spans),
        "explained_with_wide": explained_wide,
        "wide_percent": round(100.0 * explained_wide / total, 3) if total else 0.0,
        "s4_row_blocks": len(s4_spans),
        "explained_with_s4": explained_full,
        "s4_percent": round(100.0 * explained_full / total, 3) if total else 0.0,
        "gaps": len(gaps),
        "gap_bytes": sum(r["bytes"] for r in ranges),
        "remaining_gaps": len(remaining),
        "remaining_bytes": sum(r["bytes"] for r in rem),
        "ranges": ranges,
        "remaining": rem,
        "structure": structure,
        "graded": rem,
        "class_bytes": class_bytes,
        "class_ranges": class_ranges,
        "class_sum": graded_sum,
        "class_sum_ok": graded_sum == sum(r["bytes"] for r in rem),
    }


def group_ranges(ranges: list[dict], key_filter: str | None = None) -> list[dict]:
    """Group ranges by (section, level, kind, record), summing byte counts."""
    groups: dict[tuple, dict] = {}
    for r in ranges:
        key = (r["section"], r["level"], r["kind"], r["record"])
        g = groups.setdefault(key, {
            "section": r["section"], "level": r["level"], "kind": r["kind"],
            "record": r["record"], "bytes": 0, "ranges": 0,
            "modelled": set(), "largest": None, "shape": "",
        })
        g["bytes"] += r["bytes"]
        g["ranges"] += 1
        g["modelled"].add(r["modelled"])
        if g["largest"] is None or r["bytes"] > g["largest"]:
            g["largest"] = r["bytes"]
            g["shape"] = r["shape"]
    out = []
    for g in groups.values():
        g["modelled"] = "+".join(sorted(g["modelled"]))
        if key_filter is None or g["modelled"] == key_filter:
            out.append(g)
    out.sort(key=lambda g: (-g["bytes"], str(g["section"]), g["level"], g["kind"]))
    return out


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


def render_text(result: dict, groups: list[dict], top: int) -> str:
    lines = [
        "tile: %d B, nonzero past 0x1000: %d" % (
            result["tile_bytes"], result["nonzero_tail"]),
        "baseline (map_signals arithmetic): explained %d B (%.3f%%), "
        "unexplained %d B in %d ranges" % (
            result["baseline_explained"], result["baseline_percent"],
            result["gap_bytes"], result["gaps"]),
        "with s1_wide_dir row blocks (%d): explained %d B (%.3f%%)" % (
            result["wide_row_blocks"], result["explained_with_wide"], result["wide_percent"]),
        "with s1 + section4_wide row blocks (%d + %d): explained %d B (%.3f%%), "
        "still unexplained %d B in %d ranges" % (
            result["wide_row_blocks"], result["s4_row_blocks"],
            result["explained_with_s4"], result["s4_percent"],
            result["remaining_bytes"], result["remaining_gaps"]),
        "",
        "TOP %d GROUPS  (section, level, kind, even/odd  ->  bytes / ranges)" % top,
        "rank  sec  lvl  kind     rec    bytes      rng  modelled        shape of largest range",
    ]
    for n, g in enumerate(groups[:top], 1):
        lines.append("%4d  %3s  %3s  %-8s %-6s %10d  %4d  %-16s %s" % (
            n, g["section"], g["level"], g["kind"], g["record"],
            g["bytes"], g["ranges"], g["modelled"], g["shape"]))
    lines.append("")
    lines.append("STILL UNEXPLAINED after s1 + section4_wide (top 8):")
    for r in result["remaining"][:8]:
        ctx = r["context"]
        lines.append("  %#x..%#x  %8d B  sec%s L%s %s %s  %s" % (
            r["start"], r["end"], r["bytes"], ctx[0], ctx[1], ctx[2],
            ctx[3], r["shape"]))
    lines.append("")
    lines.append("STRUCTURE (clarion_tile.read_tile; section table spans)")
    for s in result["structure"]["sections"]:
        lv = " ".join("L%s=%d" % (L["level"], L["dirs"]) for L in s["levels"])
        lines.append("  sec%d taddr=%#x table_words=%d  %s" % (
            s["id"], s["taddr"], s["table_words"], lv))
    lines.append("GRADED RANGES (class; nonzero inside/outside the chosen table span)")
    for r in result["graded"]:
        span = r["table_span"]
        sdesc = "sec%d %#x..%#x" % span if span else "-"
        lines.append("  %#x..%#x %8d B  %-5s %s in=%d out=%d overlaps=%d block=%s  %s" % (
            r["start"], r["end"], r["bytes"], r["class"], sdesc,
            r["inside_nz"], r["outside_nz"], r["table_overlaps"],
            r["block"], r["class_note"]))
    lines.append("CLASSES (graded = post-s1/s4 remaining; nonzero bytes; a+b+c+d+other == still unexplained)")
    lines.append("class    bytes  ranges  meaning")
    for c in CLASSES:
        lines.append("%-6s %8d %7d  %s" % (
            c, result["class_bytes"][c], result["class_ranges"][c], CLASS_NOTE[c]))
    lines.append("sum    %8d %7d  still unexplained %d B in %d ranges (sum_ok=%s)" % (
        result["class_sum"], sum(result["class_ranges"].values()),
        result["remaining_bytes"], result["remaining_gaps"],
        result["class_sum_ok"]))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# self-test (synthetic tile, no vendor bytes)
# --------------------------------------------------------------------------


def selftest() -> int:
    import tempfile

    fails = 0

    def chk(cond: bool, msg: str) -> None:
        nonlocal fails
        if cond:
            print("  ok   " + msg)
        else:
            print("  FAIL " + msg)
            fails += 1

    print("tile_unknown selftest (synthetic tile, no vendor data)")
    with tempfile.TemporaryDirectory() as tmpdir:
        import tilewriter  # noqa: E402

        clean = tilewriter.make_factory("B48R058R")
        base = analyze(clean)
        # Positive control: a known-explained directory span is covered by a
        # baseline interval, hence in no gap, and the clean tile has only tiny
        # container gaps (< 64 B each).
        tile = clarion_tile.read_tile(clean)
        some_dir = next(d for s in tile["sections"]
                        for L in s["levels"] for d in L["dirs"])
        merged = merge_spans(baseline_spans(tile))
        covered = any(a <= some_dir["off"] and some_dir["end"] <= b
                      for a, b in merged)
        chk(covered, "positive control: a directory span is covered by an explained interval")
        chk(all(r["bytes"] < 64 for r in base["ranges"]),
            "positive control: clean synthetic tile has only tiny (<64 B) gaps")
        chk(base["explained_with_s4"] >= base["explained_with_wide"],
            "positive control: section-4 spans never reduce explained bytes")
        chk(base["remaining_bytes"] <= base["gap_bytes"],
            "positive control: the section-4 pass never adds unexplained bytes")

        # M4.96 positive controls: the graded set is the post-s1/s4 remaining
        # gaps.  On the clean synthetic tile those are section-table spans, so
        # class d must cover every graded byte and the partition must hold.
        chk(base["remaining_bytes"] > 0
            and base["class_bytes"]["d"] == base["remaining_bytes"],
            "positive control: clean synthetic remaining bytes all class d (section table span)")
        chk(base["class_sum_ok"] and base["class_sum"] == base["remaining_bytes"],
            "positive control: class bytes sum to still unexplained (clean)")
        multi = [r for r in base["graded"] if r["table_overlaps"] > 1]
        chk(bool(multi) and all(r["class"] == "d"
                                and r["inside_nz"] + r["outside_nz"] == r["bytes"]
                                for r in multi),
            "positive control: a gap overlapping two table spans gets one deterministic class")
        chk(bool(multi) and "sec4" in multi[0]["class_note"],
            "positive control: the two-span tie is broken by the larger inside_nz")
        if multi:
            mg = multi[0]
            per_span = []
            for sid, ta, tb in section_table_spans(tile):
                if ta < mg["end"] and mg["start"] < tb:
                    per_span.append("sec%d inside_nz=%d" % (
                        sid, _nonzero(clean, max(mg["start"], ta), min(mg["end"], tb))))
            print("  info two-span synthetic gap: %#x..%#x %d B  %s  chosen=%s" % (
                mg["start"], mg["end"], mg["bytes"], " ".join(per_span),
                mg["class_note"].split()[0]))

        # M4.99: every class-d row is a named section-table header block,
        # count-word bounded (u16@taddr == table_words).  This can fail.
        import struct
        drows = [r for r in base["graded"] if r["class"] == "d"]
        chk(bool(drows) and all(r["block"] == "section-table-header"
                                and r["count_word_bounded"] for r in drows),
            "positive control: every class-d row is a count-word bounded section-table block")
        chk(all(r["inside_nz"] == r["bytes"] and r["outside_nz"] == 0
                for r in drows if r["table_overlaps"] == 1),
            "positive control: a single-span class-d row holds all its nonzero bytes inside the bound")

        # Mandatory negative mutation (T3): add one nonzero byte past the table
        # end.  outside_nz must become > 0 and the class sum must grow, so the
        # "inside/outside" byte test is load-bearing, not cosmetic.
        if drows:
            dr = drows[0]
            sid, ta, tb = dr["table_span"]
            mut = bytearray(clean)
            mut[tb] = 0x5a
            mutated = analyze(bytes(mut))
            mutated_d = [r for r in mutated["graded"]
                         if r["start"] <= ta < r["end"]]
            chk(bool(mutated_d) and mutated_d[0]["outside_nz"] >= 1
                and mutated["remaining_bytes"] > base["remaining_bytes"],
                "negative control: a byte past the table end flips outside_nz and the sum")
            print("  info table-end mutation: outside_nz %d->%d remaining %d->%d" % (
                dr["outside_nz"], mutated_d[0]["outside_nz"] if mutated_d else -1,
                base["remaining_bytes"], mutated["remaining_bytes"]))
            # corrupting the count word itself must fail the bound test (and a
            # real read_tile must raise — the word is load-bearing)
            cmut = bytearray(clean)
            struct.pack_into(">H", cmut, ta, 1)
            chk(not count_word_bounded(bytes(cmut), dr["table_span"]),
                "negative control: corrupting the count word fails the bound test")
            try:
                clarion_tile.read_tile(bytes(cmut))
                chk(False, "negative control: read_tile must reject a corrupt count word")
            except (IndexError, struct.error, ValueError, AssertionError):
                chk(True, "negative control: read_tile rejects a corrupt count word")
        chk(grade_range(b"\x00\xff\xff\x00", 0, 4, (), [], [])[0] == "c",
            "positive control: 0xff slack is class c")
        chk(grade_range(b"\x78\x9c\x00\x09", 0, 4, (4, 1, "0x1046", "even", "slot0"),
                        [], [(4, 1, 0x1046, 0, 8)])[0] == "b",
            "positive control: inside a sec4 0x1046 directory extent is class b")
        chk(grade_range(b"\x78\x9c\x00\x01", 0, 4, (5, 1, "0x1046", "even", "slot0"),
                        [], [(5, 1, 0x1046, 0, 8)])[0] == "a",
            "positive control: inside a section-5 directory extent is class a")

        # Negative control: inject one 4096-byte nonzero block in the trailing
        # free region; it must be ranked first, ahead of the small real gaps.
        pad = (len(clean) + 255) // 256 * 256
        inj_bytes = bytearray(clean) + b"\x00" * (pad - len(clean))
        inj_bytes += b"\xa5" * 4096
        dirty = analyze(bytes(inj_bytes))
        chk(bool(dirty["ranges"]), "negative control: injected block produces a gap")
        top = dirty["ranges"][0]
        chk(top["bytes"] == 4096, "negative control: injected 4096 B block is the top range")
        chk(top["start"] <= pad and top["end"] >= pad + 4096
            and bytes(inj_bytes)[pad:pad + 8] == b"\xa5" * 8,
            "negative control: top range covers the injected region")
        chk("0xa5a5" in top["shape"],
            "negative control: shape names the injected bytes, not the zero pad")
        chk(dirty["ranges"][1]["bytes"] < 64 if len(dirty["ranges"]) > 1 else True,
            "negative control: injected block outweighs all pre-existing gaps")

        # M4.96 negative / M1.22 skip-set trap: the injected block is in the
        # *graded* set and its nearest mark is section 4 / L1 / 0x1046, yet it
        # lies past that directory's extent.  A section+kind-only class-(b)
        # rule would silently absorb it; it must be counted in `other`.
        trap = dirty["graded"][0]
        print("  info injected graded range: %#x..%#x %d B class=%s context=%s" % (
            trap["start"], trap["end"], trap["bytes"], trap["class"], trap["context"]))
        chk(trap["bytes"] == 4096
            and trap["context"][0] == 4 and trap["context"][2] == "0x1046",
            "negative control: injected 4096 B block has the sec4/0x1046 trap context")
        chk(trap["class"] == "other",
            "negative control: injected block is class other, not (a)-(d)")
        chk(dirty["class_bytes"]["other"] == trap["bytes"]
            and all(dirty["class_bytes"][c] == 0 for c in ("a", "b", "c")),
            "negative control: no a/b/c class absorbs the injected block")
        chk(dirty["class_sum_ok"] and dirty["class_sum"] == dirty["remaining_bytes"],
            "negative control: class partition still sums to still unexplained (dirty)")
        chk(dirty["class_bytes"]["d"] == base["class_bytes"]["d"],
            "negative control: injection leaves the real table-span gaps unchanged")
        forged = grade_range(bytes(inj_bytes), trap["start"], trap["end"],
                             trap["context"], [(1, 0x0, 0x10)], [])
        chk(forged[0] == "other" and forged[1] == "no table/dir overlap",
            "negative control: a forged table taddr removes class d")

        # Falsifier guard: the synthetic distribution has one clear dominant
        # block, not an even scatter of many equal small gaps.
        chk(top["bytes"] > 8 * max(r["bytes"] for r in dirty["ranges"][1:]),
            "falsifier guard: a single block dominates (not an even padding scatter)")

        # Shape description does not dump: a zlib record is described by its
        # signature, inflated length and first words.
        shape = describe_shape(clean, 0x1000, min(len(clean), 0x2000))
        chk("w=[" in shape or "raw" in shape, "shape() returns a description, not raw bytes")

        # main() argument handling: a missing tile is a loud usage error.
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()):
            rc = main(["/nonexistent/B48R058R.DAT"])
        chk(rc == 2, "missing tile file exits 2")

    print("tile_unknown selftest: %s (%d failure(s))" % (
        "OK" if not fails else "FAIL", fails))
    return 0 if not fails else 1


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _pick_factory_tile(root: Path) -> Path:
    """Choose the lowest-percentage of map_signals.TILE_NAMES in ``root``."""
    import map_signals  # noqa: E402

    sig = map_signals.signal_tile_bytes(root)
    if sig.get("status") != "LOCAL":
        raise ValueError(sig.get("reason", "no factory tiles"))
    name = min(sig["tiles"], key=lambda n: sig["tiles"][n])
    return root / "MAPAL001" / ("%s.DAT" % name)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tile", nargs="?", metavar="TILE.DAT",
                    help="path to MAPAL001/BxxRyyR.DAT (outside the repo)")
    ap.add_argument("--factory-root", type=Path, default=None,
                    help="pick the lowest-percentage map_signals tile in ROOT")
    ap.add_argument("--top", type=int, default=12, help="rows in the ranked table (default 12)")
    ap.add_argument("--json", nargs="?", const="-", default=None, metavar="PATH")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if bool(args.tile) == bool(args.factory_root):
        ap.error("give exactly one of TILE.DAT and --factory-root (or --selftest)")
    if args.top < 1:
        ap.error("--top must be >= 1")
    try:
        if args.factory_root is not None:
            path = _pick_factory_tile(args.factory_root)
        else:
            path = Path(args.tile)
        data = path.read_bytes()
    except (OSError, ValueError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    try:
        result = analyze(data)
    except Exception as exc:  # a malformed tile is a result, not a crash
        print("error: %s does not parse as a tile: %s: %s" % (
            path, type(exc).__name__, exc), file=sys.stderr)
        return 1
    groups = group_ranges(result["ranges"])
    result["top_groups"] = groups[:args.top]
    if args.json is not None:
        text = json.dumps(result, indent=2, sort_keys=True)
        if args.json == "-":
            print(text)
        else:
            Path(args.json).write_text(text + "\n", encoding="utf-8")
            print("report: %s" % args.json)
    else:
        print(render_text(result, groups, args.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
