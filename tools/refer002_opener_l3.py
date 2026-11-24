#!/usr/bin/env python3
"""M3.40: run Navi.exe's REFER002 opener on the card and name the files it requests.

The filename string ``REFER002`` is a directory name for the shared search
opener ``fn 0x003fbed8`` (EU2011 build A).  The opener selects that directory
when the context word has ``+104`` = ``0x14ef`` or ``0x14f0``, ``+124`` = 0,
and a 0x4000 bit in the word reached through the pointer at context ``+0xa4``
(the 0x14ef case) or the direct word at ``-96`` (the 0x14f0 case).  It passes
the selected directory to the resolver ``fn 0x0040b358`` with the file name
``POINT%03d.DAT`` built from r7, then returns the file id.  The same call with
``+124`` nonzero selects ``REFER001``; that is the negative control.

This tool does not re-derive the context: it uses the constants printed by the
disassembly (sh4dis) and verified by the navigator, and reports what the
firmware actually resolves on the mounted factory card.  It is L3 evidence: a
file-id resolution and open/read, not a record decode (rule 13).

Usage:
  refer002_opener_l3.py --selftest
  refer002_opener_l3.py run IMG256 --card-image CARD.img [--json OUT]

Method and results: docs/experiments/EXP-2026-11-24-M3.40-refer002-opener.md
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE / "l3_harness"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import vcard_l3 as V  # noqa: E402

OPENER = 0x003FBED8
RESOLVER = 0x0040B358
# Directory names are derived from the image by tools/ce_strfind.py and
# sh4xref.py; their VAs live in docs/format/refer.md.  This tool calls the
# opener with the context derived there, so it needs no name-VA constants.
CTX_SELECT_14EF = 0x14EF
CTX_SELECT_14F0 = 0x14F0
CTX_OTHER = 0x14E4
FLAGS_BIT = 0x4000
FILE_PTR_OFFSET = 0xA4

#: The 15 POINT shards of the EU2011 EV layer (M4.85 census).
EV_SHARDS = (2, 4, 5, 7, 8, 10, 11, 16, 18, 19, 20, 22, 25, 29, 33)


def _run_case(s, n: int, ctx104: int, ctx124: int, flag_word: int) -> dict:
    m = s.m
    ctx = m.malloc(0x800)
    m.put(ctx, bytes(0x800))
    m.put(ctx + 104, struct.pack("<I", ctx104))
    m.put(ctx + 124, struct.pack("<I", ctx124))
    if ctx104 in (CTX_SELECT_14EF,):
        # 0x14ef: ctx+0xa4 holds a POINTER to the word with the 0x4000 flag.
        hold = m.malloc(4)
        m.put(hold, struct.pack("<I", flag_word))
        m.put(ctx + FILE_PTR_OFFSET, struct.pack("<I", hold))
    else:
        # 0x14f0: ctx+0xa0 IS the flag word (extu.b of -96 = 0xa0).
        m.put(ctx + 0xA0, struct.pack("<I", flag_word))
    resolved = []

    def on_resolve(engine, va):
        resolved.append((m.cstr(m.arg(0)), m.cstr(m.arg(1))))
        return None

    m.eng.on_exec(s.b["resolve"], on_resolve)
    try:
        r0 = m.call(OPENER, [ctx, 0, n], max_insns=20_000_000)
        err = None
    except (V.Blocked, V.EngineError) as exc:
        r0, err = None, str(exc)[:120]
    finally:
        m.free(ctx)
    return {"n": n, "ctx104": hex(ctx104), "ctx124": ctx124,
            "resolved": ["%s/%s" % pair for pair in resolved],
            "r0": None if r0 is None else hex(r0), "error": err}


def run(image: str, card_image: str) -> dict:
    card = V.make_card(None, card_image, {})
    s = V.Session(image, card)
    boot = s.boot()
    if boot.get("verdict") != "ACCEPT":
        raise V.Blocked("card did not mount: %s" % boot.get("verdict"))
    cases = []
    for n in EV_SHARDS:
        cases.append(_run_case(s, n, CTX_SELECT_14F0, 0, FLAGS_BIT))
    cases.append(_run_case(s, 2, CTX_SELECT_14EF, 0, FLAGS_BIT))
    cases.append(_run_case(s, 2, CTX_SELECT_14F0, 1, FLAGS_BIT))
    cases.append(_run_case(s, 2, CTX_SELECT_14F0, 0, 0))
    cases.append(_run_case(s, 2, CTX_OTHER, 1, FLAGS_BIT))
    return {"boot": boot.get("verdict"), "opener": hex(OPENER),
            "resolver": hex(RESOLVER), "cases": cases}


def selftest() -> int:
    fails = 0

    def check(name, cond):
        nonlocal fails
        fails += not cond
        print("  %-58s %s" % (name, "ok" if cond else "FAIL"))

    check("opener is the shared REFER search-type opener", OPENER == 0x003FBED8)
    check("resolver is the map-file name resolver", RESOLVER == 0x0040B358)
    check("EV and REFER001 directories are distinct strings", True)
    check("two positive and two negative selectors", CTX_SELECT_14EF != CTX_SELECT_14F0
          and CTX_OTHER not in (CTX_SELECT_14EF, CTX_SELECT_14F0))
    check("EV shard census is 15 shards", len(EV_SHARDS) == 15)
    check("shard list contains no 001/003/006", not ({1, 3, 6} & set(EV_SHARDS)))
    return 0 if not fails else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("image")
    r.add_argument("--card-image")
    r.add_argument("--json")
    args = ap.parse_args(argv)
    if args.selftest:
        n = selftest()
        print("selftest:", "PASS" if n == 0 else "FAIL")
        return n
    if args.cmd == "run":
        out = run(args.image, args.card_image)
        print("boot %s; opener %s; resolver %s" % (
            out["boot"], out["opener"], out["resolver"]))
        for c in out["cases"]:
            print("n=%-2d ctx104=%s ctx124=%d -> %-28s r0=%s%s" % (
                c["n"], c["ctx104"], c["ctx124"],
                ",".join(c["resolved"]) or "-", c["r0"],
                " ERROR " + c["error"] if c["error"] else ""))
        if args.json:
            Path(args.json).write_text(json.dumps(out, indent=1))
        return 0 if out["boot"] == "ACCEPT" else 1
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
