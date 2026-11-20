#!/usr/bin/env python3
"""Dump every ``fn_match`` verdict of a module and diff two dumps (H118).

A change to ``fn_match``'s slot derivation moves hashes on both sides, so a
before/after census is only honest when every row is compared, not only the
totals.  ``dump`` runs ``fn_match.Matcher.verdict`` on every A ``.pdata``
record with the ``fn_match`` module found in ``--tools`` (default: this
directory; point it at an extracted older tree for the "before" side) and
writes ``{"0x...": {"v": VERDICT, "b": "0x..." | null}}``.  ``diff`` prints
both censuses, the before→after transition table, and every row whose
non-null B address changed to another non-null one (the H113/H118
falsifier); it exits 1 when there is such a row.

Usage::

    python3 tools/fn_verdict_diff.py dump EU US -o AFTER.json [--tools DIR]
    python3 tools/fn_verdict_diff.py diff BEFORE.json AFTER.json
    python3 tools/fn_verdict_diff.py slots EU US [--verdicts BEFORE.json]
    python3 tools/fn_verdict_diff.py --selftest

``slots`` counts the H118 residual: PC loads the H113 forward pass keeps
that the current ``fn_match._pool_loads`` drops, split by rule (``target``:
the slot lies on a reached instruction; ``unreached``: an unreached halfword
of a function with no reached ``braf``/``jmp``), per build, and with
``--verdicts`` how many EU rows of each verdict have such a load on either
side of their pair.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORDER = ("UNIQUE", "DIFFERENT", "CALLORDER", "ANCHOR", "AMBIGUOUS",
         "LEAF", "TRUNCATED", "NOMATCH")


def ablate_open(fm):
    """Control: treat every function as closed (no computed jump).

    The slot pass then drops every unreached load, including the real loads
    of switch case bodies that only a ``braf``/``jmp`` reaches.  The walk
    itself still ends paths at ``braf``/``jmp``.
    """
    orig_reach, orig_cj = fm.reachable, fm.is_computed_jump

    def never(_w):
        return False

    def reach(words):
        fm.is_computed_jump = orig_cj
        try:
            return orig_reach(words)
        finally:
            fm.is_computed_jump = never
    fm.reachable = reach
    fm.is_computed_jump = never


def dump(eu, us, tools_dir, module, image_start, index_a, index_b,
         all_closed=False):
    """Every A record's verdict, with the ``fn_match`` in ``tools_dir``."""
    sys.path.insert(0, str(Path(tools_dir).resolve()))
    for name in ("fn_match", "cerom"):
        sys.modules.pop(name, None)
    fm = importlib.import_module("fn_match")
    if all_closed:
        ablate_open(fm)
    with contextlib.redirect_stdout(io.StringIO()):
        m = fm.Matcher(eu, us, module, image_start, index_a, index_b,
                       None, None)
        out = {}
        for f in m.fa:
            r = m.verdict(f[0])
            out["%#010x" % f[0]] = {
                "v": r[2], "b": None if r[1] is None else "%#010x" % r[1]}
    return out


def h113_loads(fm, words, base_va):
    """``(index, slot index)`` of the H113 forward pass (no control flow)."""
    slots: set[int] = set()
    for i, w in enumerate(words):
        if i in slots or not fm.is_mov_pc(w):
            continue
        size = 4 if (w >> 12) == 0xD else 2
        j = (fm.pool_addr(base_va + 2 * i, w) - base_va) // 2
        slots.update((j, j + 1) if size == 4 else (j,))
        yield i, j, size


def dropped(fm, words, base_va):
    """``{"target", "unreached"}``: loads H113 kept and H118 drops.

    ``"gained"`` counts the converse: a halfword H113 had marked as a slot
    (so it named nothing) that H118 unmasks and keeps as a real load.
    """
    now = {i for i, _l, _s, _d in fm._pool_loads(words, base_va)}
    live = fm.reachable(words)
    out = Counter()
    old = {i for i, _j, _s in h113_loads(fm, words, base_va)}
    out["gained"] += len(now - old)
    for i, j, size in h113_loads(fm, words, base_va):
        if i in now:
            continue
        hit = any(k in live for k in ((j, j + 1) if size == 4 else (j,)))
        out["target" if hit else "unreached"] += 1
    return out


def slots_report(eu, us, module, image_start, verdicts=None):
    sys.path.insert(0, str(HERE))
    import fn_match as fm
    with contextlib.redirect_stdout(io.StringIO()):
        m = fm.Matcher(eu, us, module, image_start, 2, 2, None, None)
    hit = {}
    for name, funcs in (("A", m.fa), ("B", m.fb)):
        tot = Counter()
        for va, words, _lr, _cb, _cc in funcs:
            d = dropped(fm, words, va)
            tot["loads"] += sum(1 for _ in h113_loads(fm, words, va))
            tot.update(d)
            if d["target"] or d["unreached"]:
                tot["functions"] += 1
                hit[(name, va)] = d
        print("# %s: %d functions, %d H113 loads; dropped: target %d  "
              "unreached %d  in %d functions; gained %d" % (
                  name, len(funcs), tot["loads"], tot["target"],
                  tot["unreached"], tot["functions"], tot["gained"]))
    if verdicts:
        by = Counter()
        rows = Counter()
        for k, r in verdicts.items():
            rows[r["v"]] += 1
            va = int(k, 16)
            b = int(r["b"], 16) if r["b"] else None
            if ("A", va) in hit or (b is not None and ("B", b) in hit):
                by[r["v"]] += 1
        print("# rows with a dropped load on either side (EU side only when "
              "the row has no B address): " + "  ".join(
            "%s %d/%d" % (v, by[v], rows[v]) for v in _cols(rows)))
    return 0


def diff(before, after):
    """``(census_b, census_a, transitions, moved)`` of two dumps."""
    keys = sorted(set(before) & set(after))
    cb = Counter(before[k]["v"] for k in keys)
    ca = Counter(after[k]["v"] for k in keys)
    tr = Counter((before[k]["v"], after[k]["v"]) for k in keys)
    moved = [(k, before[k]["b"], after[k]["b"]) for k in keys
             if before[k]["b"] and after[k]["b"]
             and before[k]["b"] != after[k]["b"]]
    return cb, ca, tr, moved


def _cols(*counters):
    seen = set()
    for c in counters:
        seen |= set(c)
    return [v for v in ORDER if v in seen] + sorted(seen - set(ORDER))


def report(before, after, verbose=False, rows=False):
    cb, ca, tr, moved = diff(before, after)
    only = len(set(before) ^ set(after))
    cols = _cols(cb, ca)
    print("# rows: %d common, %d in one dump only" % (sum(cb.values()), only))
    print("# before: " + "  ".join("%s %d" % (v, cb[v]) for v in cols))
    print("# after:  " + "  ".join("%s %d" % (v, ca[v]) for v in cols))
    print("# transitions (before -> after, nonzero):")
    for (b, a), n in sorted(tr.items(), key=lambda t: (cols.index(t[0][0]),
                                                       cols.index(t[0][1]))):
        if b != a or verbose:
            print("#   %-10s -> %-10s %5d" % (b, a, n))
    print("# unchanged rows: %d" % sum(n for (b, a), n in tr.items() if b == a))
    print("# B address moved to another non-null B: %d" % len(moved))
    for k, b, a in moved:
        print("MOVED %s %s -> %s" % (k, b, a))
    if rows:
        for k in sorted(set(before) & set(after)):
            if before[k]["v"] != after[k]["v"]:
                print("CHANGED %s %s %s -> %s %s" % (
                    k, before[k]["v"], before[k]["b"] or "-",
                    after[k]["v"], after[k]["b"] or "-"))
    return 1 if moved else 0


def selftest() -> int:
    fails = []
    ran = []

    def check(name, cond):
        ran.append(name)
        if not cond:
            fails.append(name)
            print("FAIL", name)

    b = {"0x1": {"v": "UNIQUE", "b": "0x10"},
         "0x2": {"v": "NOMATCH", "b": None},
         "0x3": {"v": "DIFFERENT", "b": "0x30"},
         "0x4": {"v": "UNIQUE", "b": "0x40"}}
    a = {"0x1": {"v": "UNIQUE", "b": "0x10"},
         "0x2": {"v": "UNIQUE", "b": "0x20"},
         "0x3": {"v": "UNIQUE", "b": "0x30"},
         "0x4": {"v": "AMBIGUOUS", "b": None}}
    cb, ca, tr, moved = diff(b, a)
    check("census before", cb == Counter(UNIQUE=2, NOMATCH=1, DIFFERENT=1))
    check("census after", ca == Counter(UNIQUE=3, AMBIGUOUS=1))
    check("transitions", tr[("NOMATCH", "UNIQUE")] == 1
          and tr[("UNIQUE", "AMBIGUOUS")] == 1 and tr[("UNIQUE", "UNIQUE")] == 1)
    check("null->addr and addr->null are not a move", moved == [])
    a2 = dict(a)
    a2["0x3"] = {"v": "UNIQUE", "b": "0x31"}
    check("a changed non-null B is a move",
          diff(b, a2)[3] == [("0x3", "0x30", "0x31")])
    with contextlib.redirect_stdout(io.StringIO()):
        check("report exits 0 without a move", report(b, a) == 0)
        check("report exits 1 on a move", report(b, a2) == 1)
    sys.path.insert(0, str(HERE))
    import fn_match as fm
    ws = [0x0009] * 130
    for k, w in ((0, 0xD702), (1, 0x8907), (2, 0x000B), (6, 0xDA39),
                 (10, 0xD105), (11, 0x000B), (50, 0xD023), (122, 0xC11E)):
        ws[k] = w
    check("slots: hw50 is an H113 load that H118 drops as unreached",
          50 in {i for i, _j, _s in h113_loads(fm, ws, 0x1000)}
          and dropped(fm, ws, 0x1000) == Counter(unreached=1, gained=0))
    ws[1], ws[11] = 0xA039, 0x0023        # bra over the pool, open function
    ws[124] = 0x0023
    check("slots: a slot on a reached insn is dropped as target",
          dropped(fm, ws, 0x1000)["target"] == 1)
    ws2 = [0x0009] * 130
    for k, w in ((0, 0xD702), (1, 0x8907), (2, 0x000B), (6, 0xDA39),
                 (10, 0xD105), (11, 0x0023), (50, 0xD023), (122, 0xC11E)):
        ws2[k] = w
    kept = 122 in fm.pool_slots(ws2, 0x1000)
    ablate_open(fm)
    gone = 122 not in fm.pool_slots(ws2, 0x1000)
    walk = fm.reachable(ws2) == {0, 1, 2, 3, 10, 11, 12}
    sys.modules.pop("fn_match", None)
    check("ablation: an open function keeps hw50, --all-closed drops it, "
          "the walk still stops at braf", kept and gone and walk)
    check("unknown verdicts still get a column",
          _cols(Counter(X=1), Counter(UNIQUE=1)) == ["UNIQUE", "X"])
    print("fn_verdict_diff selftest: %s (%d checks, %d failed)"
          % ("OK" if not fails else "FAIL", len(ran), len(fails)))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    d = sub.add_parser("dump")
    d.add_argument("eu")
    d.add_argument("us")
    d.add_argument("-o", "--out", required=True)
    d.add_argument("--tools", default=str(HERE),
                   help="directory holding the fn_match.py to run")
    d.add_argument("--module", default="Navi.exe")
    d.add_argument("--image-start", type=lambda x: int(x, 0), default=0x200200)
    d.add_argument("--index-a", type=int, default=2)
    d.add_argument("--index-b", type=int, default=2)
    d.add_argument("--all-closed", action="store_true",
                   help="control: drop every unreached load, even in a "
                        "function with a braf/jmp (H118 ablation)")
    sl = sub.add_parser("slots")
    sl.add_argument("eu")
    sl.add_argument("us")
    sl.add_argument("--verdicts", help="a dump to split the rows by verdict")
    sl.add_argument("--module", default="Navi.exe")
    sl.add_argument("--image-start", type=lambda x: int(x, 0), default=0x200200)
    f = sub.add_parser("diff")
    f.add_argument("before")
    f.add_argument("after")
    f.add_argument("--verbose", action="store_true",
                   help="also print the unchanged diagonal")
    f.add_argument("--rows", action="store_true",
                   help="print every row whose verdict changed")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "dump":
        out = dump(args.eu, args.us, args.tools, args.module, args.image_start,
                   args.index_a, args.index_b, args.all_closed)
        Path(args.out).write_text(json.dumps(out, sort_keys=True, indent=0))
        c = Counter(r["v"] for r in out.values())
        print("# %d rows: " % len(out) +
              "  ".join("%s %d" % (v, c[v]) for v in _cols(c)))
        return 0
    if args.cmd == "slots":
        v = json.loads(Path(args.verdicts).read_text()) if args.verdicts else None
        return slots_report(args.eu, args.us, args.module, args.image_start, v)
    if args.cmd == "diff":
        return report(json.loads(Path(args.before).read_text()),
                      json.loads(Path(args.after).read_text()), args.verbose,
                      args.rows)
    ap.error("--selftest or a subcommand is required")
    return 2


if __name__ == "__main__":
    sys.exit(main())
