#!/usr/bin/env python3
"""bodydiff.py - raw byte diff of an EU2011/US2011 function-body pair.

``fn_match.py bodies`` compares *pool-masked* form streams: it proves the two
bodies are the same code with relocated literal pools, but it prints only the
first raw difference.  A reader task needs the stronger control: every raw
differing halfword must be a literal-pool slot a body load points at (a
relocated address/table), never an instruction halfword.  This tool prints the
whole raw diff, classifies each halfword, and exits non-zero when an
instruction halfword differs -- a check that can fail loudly (rule 14).

Only uncompressed executable sections are read; SH-4 halfwords are
little-endian (``tools/sh4dis.py`` pins the convention).  Function starts and
lengths come from ``pdata`` through ``fn_match``; nothing is fitted.

Usage:
  bodydiff.py --selftest
  bodydiff.py IMG_A IMG_B --module Navi.exe --pair EU_VA:US_VA [...]
             [--negative EU_VA:US_VA ...] [--limit N] [--json OUT]

Exit codes: 0 every --pair has instruction diffs 0 and every --negative has
at least one; 1 a body pair failed the control; 2 usage/bad input; 3 BLOCKED.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def pair_arg(text: str) -> tuple[int, int]:
    a, sep, b = text.partition(":")
    if not sep or not a or not b:
        raise argparse.ArgumentTypeError("expected EU_VA:US_VA, got %r" % text)
    return int(a, 0), int(b, 0)


def pool_indices(words: list[int], va: int) -> set[int]:
    """Halfword indexes of every literal-pool slot a body load points at."""
    from fn_match import _pool_loads
    out: set[int] = set()
    for _i, lit, size, _dest in _pool_loads(words, va):
        j = (lit - va) // 2
        out.update((j, j + 1) if size == 4 else (j,))
    return out


def classify(diffs: list[tuple[int, int, int]], pool_a: set[int],
             pool_b: set[int]) -> tuple[list[dict], int]:
    """Split raw diffs into per-halfword rows; count instruction halfwords."""
    rows = []
    for i, wa, wb in diffs:
        kind = "pool" if i in pool_a or i in pool_b else "instruction"
        rows.append({"offset": 2 * i, "eu": wa, "us": wb, "kind": kind})
    return rows, sum(r["kind"] == "instruction" for r in rows)


def _loads(image: str, image_start: int, module: str):
    import nk_decomp
    from fn_match import code_section, parse_pdata
    data, code, off, _lr, _rom = code_section(image, image_start, module)
    cb = data[off:off + code["vsize"]]
    pd = parse_pdata(nk_decomp.section_init(nk_decomp.load_image(image), module, 2))
    return code["realaddr"], cb, pd


def compare_pair(image_a: str, image_b: str, va_a: int, va_b: int,
                 image_start: int, module: str) -> dict:
    """Raw full-body diff of one EU/US pair (pdata START in both)."""
    from fn_match import locate, window_words
    ca, cb_a, pa = _loads(image_a, image_start, module)
    cb, cb_b, pb = _loads(image_b, image_start, module)
    ka, ra = locate(pa, va_a)
    kb, rb = locate(pb, va_b)
    if ka != "START" or kb != "START":
        return {"eu": va_a, "us": va_b, "blocked":
                "pdata %s/%s, want START/START" % (ka, kb)}
    n = min(ra[2], rb[2])
    wa = window_words(cb_a, ca, va_a, n)
    wb = window_words(cb_b, cb, va_b, n)
    diffs = [(i, wa[i], wb[i]) for i in range(len(wa)) if wa[i] != wb[i]]
    rows, n_instr = classify(diffs, pool_indices(wa, va_a), pool_indices(wb, va_b))
    diff32 = []
    i = 0
    while i < len(rows):
        if (i + 1 < len(rows) and rows[i + 1]["offset"] == rows[i]["offset"] + 2
                and rows[i]["kind"] == rows[i + 1]["kind"] == "pool"):
            diff32.append({"offset": rows[i]["offset"],
                           "eu": rows[i]["eu"] | (rows[i + 1]["eu"] << 16),
                           "us": rows[i]["us"] | (rows[i + 1]["us"] << 16)})
            i += 2
            continue
        i += 1
    return {"eu": va_a, "us": va_b, "len_eu": ra[2], "len_us": rb[2],
            "bytes_compared": 2 * len(wa), "raw_diffs": len(rows),
            "pool_diffs": len(rows) - n_instr, "instruction_diffs": n_instr,
            "rows": rows, "relocated_words": diff32,
            "ok": n_instr == 0}


def cmd_diff(args) -> int:
    for path in (args.image_a, args.image_b):
        if not Path(path).is_file():
            print("missing image: %s" % path, file=sys.stderr)
            return 2
    out = []
    bad = 0
    for a, b in args.pair or []:
        res = compare_pair(args.image_a, args.image_b, a, b,
                           args.image_start, args.module)
        out.append(res)
        if res.get("blocked"):
            print("BLOCKED EU %#010x US %#010x: %s" % (a, b, res["blocked"]))
            bad += 1
            continue
        print("EU %#010x -> US %#010x  len %#x/%#x  compared %d B  "
              "raw diffs %d (pool %d, instruction %d)  %s" % (
                  a, b, res["len_eu"], res["len_us"], res["bytes_compared"],
                  res["raw_diffs"], res["pool_diffs"], res["instruction_diffs"],
                  "OK" if res["ok"] else "FAIL"))
        for r in res["relocated_words"]:
            print("  +%#06x  EU %#010x -> US %#010x  (relocated pool word)" % (
                r["offset"], r["eu"], r["us"]))
        instr_rows = [r for r in res["rows"] if r["kind"] == "instruction"]
        for r in instr_rows[:args.limit]:
            print("  INSTRUCTION +%#06x  EU %#06x US %#06x" % (
                r["offset"], r["eu"], r["us"]))
        if len(instr_rows) > args.limit:
            print("  ... %d more instruction diffs" % (len(instr_rows) - args.limit))
        bad += not res["ok"]
    for a, b in args.negative or []:
        res = compare_pair(args.image_a, args.image_b, a, b,
                           args.image_start, args.module)
        out.append({"negative": True, **res})
        if res.get("blocked"):
            print("NEGATIVE BLOCKED EU %#010x US %#010x: %s" % (a, b, res["blocked"]))
            bad += 1
            continue
        ok = res["instruction_diffs"] > 0
        print("NEGATIVE EU %#010x US %#010x  instruction diffs %d  %s" % (
            a, b, res["instruction_diffs"], "ok" if ok else "FAIL (no instruction diff)"))
        bad += not ok
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=1))
    print("bodydiff: %s" % ("FAIL" if bad else "OK"))
    return 1 if bad else 0


def selftest() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print("%-62s %s" % (name, "ok" if cond else "FAIL"))
        ok = ok and bool(cond)

    check("pair_arg parses two addresses", pair_arg("0x10:0x20") == (0x10, 0x20))
    try:
        pair_arg("0x10")
        check("pair_arg refuses one address", False)
    except argparse.ArgumentTypeError:
        check("pair_arg refuses one address", True)
    rows, n = classify([(1, 0x1234, 0x5678)], {1}, set())
    check("a pool-slot diff is not an instruction", n == 0 and rows[0]["kind"] == "pool")
    rows, n = classify([(4, 0xAAAA, 0xBBBB)], set(), {4})
    check("the other body's pool slot is also a pool diff", n == 0 and rows[0]["kind"] == "pool")
    rows, n = classify([(4, 0xAAAA, 0xBBBB)], {1}, {1})
    check("an unmasked diff is an instruction (negative control)", n == 1
          and rows[0]["kind"] == "instruction")
    rows, n = classify([], set(), set())
    check("identical bodies have no diffs", n == 0 and rows == [])
    print("bodydiff selftest: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--module", default="Navi.exe")
    ap.add_argument("--image-start", type=lambda x: int(x, 0), default=0x200200)
    ap.add_argument("image_a", nargs="?")
    ap.add_argument("image_b", nargs="?")
    ap.add_argument("--pair", type=pair_arg, action="append", metavar="EU:US")
    ap.add_argument("--negative", type=pair_arg, action="append", metavar="EU:US")
    ap.add_argument("--limit", type=int, default=40, help="printed rows per pair")
    ap.add_argument("--json")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.image_a or not args.image_b or not args.pair:
        ap.print_usage(sys.stderr)
        return 2
    return cmd_diff(args)


if __name__ == "__main__":
    sys.exit(main())
