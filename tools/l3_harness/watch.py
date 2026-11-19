#!/usr/bin/env python3
"""Attribute a read/write watch's hits to functions (M9.38).

The engine records ``(pc, va, size, kind)`` for every watched access; this
module turns those records into the table the task asks for:
``function / reads / first offset / last offset / widths``.

Attribution is ``.pdata``-exact where it can be, and **never invents a
function**:

* ``START``  -> ``fn 0x003f5194`` (the PC is a function entry);
* ``INSIDE`` -> ``fn 0x003f5cdc`` (the record's true start);
* ``GAP``    -> ``GAP@0x003f5098 (pc 0x003f51a0, entry 0x003f5194)`` -- a
  leaf function has no record, so its container is the gap, and the entry
  named is the nearest preceding directly-called entry inside that gap (or
  the PC when none is known).  It is **never** printed as ``fn 0x003f5098``:
  that address is the *preceding* record's start, not this code's.
* no table  -> ``pc 0x003f51a0`` (no label is guessed).

Only PySh4 records hits; a watch request on any other back end fails loudly
(:class:`UnsupportedWatch`) rather than returning an empty table that would
read as "nothing touched it".

Usage::

    python3 tools/l3_harness/watch.py --selftest
    python3 tools/l3_harness/watch.py label IMG --module Navi.exe VA...

Method and results: docs/experiments/EXP-2026-11-19-M9.38-read-watch.md
"""

from __future__ import annotations

import argparse
import bisect
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for path in (TOOLS, HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

import pdata  # noqa: E402


class UnsupportedWatch(Exception):
    """A watch was requested on a back end that cannot record hits."""

    def __init__(self, engine: str):
        self.engine = engine
        super().__init__(
            f"--watch needs the pysh4 engine (the only one that records hits); "
            f"this run used {engine!r}, so no watch table can be produced"
        )


def locate(records, va: int) -> str:
    """``START`` / ``INSIDE`` / ``GAP`` / ``BEFORE`` for *va* (see pdata.locate)."""
    kind, _rec = pdata.locate(records, va)
    return kind


class Labeller:
    """Memoised attribution for one run (loads the table once, not per PC).

    ``entry`` is the run's own entry VA.  When a PC falls in the same gap as
    the entry, the entry names the leaf (the walker has no ``.pdata`` record,
    so the gap is its container and the entry is the only honest name); else
    the nearest preceding called entry inside the gap is used, and with
    neither the PC itself -- never the preceding record's ``fn``.
    """

    def __init__(self, data, image_start: str, module: str, entry: int | None = None,
                 cache_dir=None) -> None:
        self.data = data
        self.image_start = image_start
        self.module = module
        self.entry = int(entry) & 0xFFFFFFFF if entry is not None else None
        self.cache_dir = cache_dir
        self._records = pdata.table_or_none(data, image_start, module, cache_dir)
        self._gaps = None
        self._called = None
        self._memo: dict[int, str] = {}

    def _gap(self, va: int):
        if self._gaps is None:
            rows, _meta = pdata.gaps(self.data, self.image_start, self.module,
                                     self.cache_dir)
            self._gaps = rows
        for row in self._gaps:
            if row["start"] <= va < row["end"]:
                return row
        prev = None
        for row in self._gaps:
            if row["start"] <= va:
                prev = row
        return prev

    def _called_entries(self):
        if self._called is None:
            import cerom

            rom = cerom.CERom(self.data, self.image_start)
            mod = rom.module(self.module)
            self._called = sorted(pdata.called_entries(list(pdata.exec_sections(rom, mod))))
        return self._called

    def label(self, va: int) -> str:
        va &= 0xFFFFFFFF
        if va in self._memo:
            return self._memo[va]
        text = self._label(va)
        self._memo[va] = text
        return text

    def _label(self, va: int) -> str:
        if self._records is None:
            return f"pc 0x{va:08x}"
        kind, rec = pdata.locate(self._records, va)
        if kind == "START":
            return f"fn 0x{va:08x}"
        if kind == "INSIDE":
            return f"fn 0x{rec[0]:08x}"
        if kind == "BEFORE":
            return f"pc 0x{va:08x}"
        gap = self._gap(va)
        if gap is None:
            return f"pc 0x{va:08x}"
        if self.entry is not None and gap["start"] <= self.entry < gap["end"]:
            entry = self.entry
        else:
            called = self._called_entries()
            i = bisect.bisect_right(called, va) - 1
            entry = called[i] if i >= 0 and gap["start"] <= called[i] < gap["end"] else va
        return f"GAP@0x{gap['start']:08x} (pc 0x{va:08x}, entry 0x{entry:08x})"


def label(data, image_start: str, module: str, va: int, cache_dir=None,
          entry: int | None = None) -> str:
    """One attribution label for the PC *va* (never a guessed ``fn``)."""
    return Labeller(data, image_start, module, entry=entry,
                    cache_dir=cache_dir).label(va)


def summarise(hits, base: int, labeller=None) -> list[dict]:
    """Group hits by (label, kind) into the task's five-column rows.

    ``labeller(pc) -> str`` supplies the function label; without it the raw
    PC is kept (``pc 0x…``, never a guessed name).  ``api-*`` and ``x`` hits
    are reported separately (:func:`api_summary`) and never inflate *reads*.
    """
    groups: dict[tuple[str, str], dict] = {}
    for hit in hits:
        kind = hit.kind
        if kind.startswith("api") or kind == "x":
            continue
        key_label = labeller(hit.pc) if labeller else f"pc {hit.pc:#010x}"
        key = (key_label, kind)
        row = groups.get(key)
        if row is None:
            row = groups[key] = {
                "function": key_label, "kind": kind, "accesses": 0,
                "widths": set(), "first": hit.va, "last": hit.va,
            }
        row["accesses"] += 1
        row["widths"].add(hit.size)
        row["first"] = min(row["first"], hit.va)
        row["last"] = max(row["last"], hit.va)
    rows = []
    for row in groups.values():
        rows.append({
            "function": row["function"],
            "kind": row["kind"],
            "accesses": row["accesses"],
            "first_offset": _offset(row["first"], base, row["widths"]),
            "last_offset": _offset(row["last"], base, row["widths"]),
            "widths": sorted(row["widths"]),
        })
    rows.sort(key=lambda r: (r["kind"], r["function"], r["first_offset"]))
    return rows


def _offset(va: int, base: int, widths: set[int]) -> str:
    rel = va - base
    return f"+0x{rel:x}" if rel >= 0 else f"-0x{-rel:x}"


def api_summary(hits) -> dict:
    """Counts of ``api``/``x`` hits, which are never guest reads."""
    api = sum(1 for h in hits if h.kind.startswith("api"))
    fetch = sum(1 for h in hits if h.kind == "x")
    return {"api": api, "fetch": fetch}


def totals(hits) -> dict:
    """Per-kind guest totals (r/w), excluding api and fetch."""
    out = {"r": 0, "w": 0}
    for hit in hits:
        if hit.kind in out:
            out[hit.kind] += 1
    return out


# ---------------------------------------------------------------------------
# command: label a VA (the positive-control transcript)
# ---------------------------------------------------------------------------


def cmd_label(args) -> int:
    with open(args.image, "rb") as fh:
        data = fh.read(128 << 20)
    labeller = Labeller(data, args.image_start, args.module, entry=args.entry,
                        cache_dir=args.cache)
    for text in args.va:
        va = int(text, 0)
        print(f"0x{va:08x} {labeller.label(va)}")
    return 0


# ---------------------------------------------------------------------------
# self-test (no vendor data)
# ---------------------------------------------------------------------------


def selftest() -> int:
    fails = 0

    def check(name, cond):
        nonlocal fails
        print("%-58s %s" % (name, "ok" if cond else "FAIL"))
        fails += not cond

    # A synthetic pdata table: one 0x20-byte function at 0x1000, a gap
    # 0x1020..0x1100 whose only called entry is 0x1040, then 0x1100.
    records = [(0x1000, 4, 0x20), (0x1100, 4, 0x20)]
    check("START labels the entry", _label_from(records, 0x1000) == "fn 0x00001000")
    check("INSIDE labels the true start",
          _label_from(records, 0x1010) == "fn 0x00001000")
    gap = _label_from(records, 0x1044, called=[0x1040],
                      gap=(0x1020, 0x1100))
    check("GAP is not printed as the preceding fn", not gap.startswith("fn "))
    check("GAP names the gap start and the entry",
          gap == "GAP@0x00001020 (pc 0x00001044, entry 0x00001040)")
    check("GAP with no known entry keeps the PC as the entry",
          _label_from(records, 0x1050, called=[], gap=(0x1020, 0x1100))
          == "GAP@0x00001020 (pc 0x00001050, entry 0x00001050)")
    same = _label_from(records, 0x1044, called=[0x1040],
                       gap=(0x1020, 0x1100), entry=0x1044)
    check("a GAP entry names itself (the walker case)",
          same == "GAP@0x00001020 (pc 0x00001044, entry 0x00001044)")
    check("BEFORE gets a raw pc, never a fn",
          _label_from(records, 0x0800) == "pc 0x00000800")
    check("no table gets a raw pc", _label_from(None, 0x1000) == "pc 0x00001000")

    # summarise: widths/first/last and the api/x exclusion.
    Hit = _hit
    hits = [
        Hit(0x1000, 0x2000, 1, "r", "buf"),
        Hit(0x1000, 0x2002, 2, "r", "buf"),
        Hit(0x1010, 0x2004, 4, "r", "buf"),
        Hit(0x1000, 0x2000, 2, "w", "buf"),
        Hit(0x1000, 0x2000, 4, "api-r", "buf"),
        Hit(0x1000, 0x2000, 1, "x", "buf"),
    ]
    rows = summarise(hits, 0x2000, labeller=lambda pc: f"fn 0x{pc:08x}")
    r_rows = [r for r in rows if r["kind"] == "r"]
    by_fn = {r["function"]: r for r in r_rows}
    check("summarise splits reads by function", len(r_rows) == 2)
    check("read widths are the distinct sizes",
          by_fn["fn 0x00001000"]["widths"] == [1, 2])
    check("read first/last offsets are relative to the watched base",
          by_fn["fn 0x00001000"]["first_offset"] == "+0x0"
          and by_fn["fn 0x00001000"]["last_offset"] == "+0x2")
    check("second reader's offset is its own access",
          by_fn["fn 0x00001010"]["last_offset"] == "+0x4")
    check("write row is separate from read rows",
          any(r["kind"] == "w" and r["widths"] == [2] for r in rows))
    check("api and fetch are excluded from guest reads",
          totals(hits) == {"r": 3, "w": 1})
    check("api/fetch counted separately", api_summary(hits) == {"api": 1, "fetch": 1})
    check("UnsupportedWatch names the engine",
          "ghidra" in str(UnsupportedWatch("ghidra")))

    print("selftest:", "PASS" if not fails else "FAIL (%d)" % fails)
    return 0 if not fails else 1


def _hit(pc, va, size, kind, name="w"):
    from engine import WatchHit
    return WatchHit(pc=pc, va=va, size=size, kind=kind, name=name)


def _label_from(records, va, called=None, gap=None, entry=None):
    """The pure labelling logic, without an image (used by the selftest)."""
    if records is None:
        return f"pc 0x{va:08x}"
    kind, rec = pdata.locate(records, va)
    if kind == "START":
        return f"fn 0x{va:08x}"
    if kind == "INSIDE":
        return f"fn 0x{rec[0]:08x}"
    if kind == "BEFORE" or gap is None:
        return f"pc 0x{va:08x}"
    if entry is not None and gap[0] <= entry < gap[1]:
        return f"GAP@0x{gap[0]:08x} (pc 0x{va:08x}, entry 0x{entry:08x})"
    called = sorted(called or [])
    i = bisect.bisect_right(called, va) - 1
    chosen = called[i] if i >= 0 and gap[0] <= called[i] < gap[1] else va
    return f"GAP@0x{gap[0]:08x} (pc 0x{va:08x}, entry 0x{chosen:08x})"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    lab = sub.add_parser("label", help="print the attribution label for each VA")
    lab.add_argument("image")
    lab.add_argument("--module", default="Navi.exe")
    lab.add_argument("--image-start", type=lambda s: int(s, 0), default=0x200200)
    lab.add_argument("--cache")
    lab.add_argument("--entry", type=lambda s: int(s, 0), default=None,
                     help="the run's entry VA (names a GAP leaf)")
    lab.add_argument("va", nargs="+")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "label":
        return cmd_label(args)
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
