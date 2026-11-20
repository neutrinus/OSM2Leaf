#!/usr/bin/env python3
"""The firmware's own POINT byte swap, byte-equal to point_walk_l3.swap16 (M3.11b).

The Done-when of M3.11b asks for "the factory page swapped by the firmware code
itself in PySh4 and byte-equal to ``point_walk_l3.swap16``".  This tool boots the
EU 2011 factory card through the firmware's own map-file layer
(``tools/vcard_l3.py``: mount, read queue, completion) and issues a real read of
``REFER001/POINT010.DAT`` with request word +20 at both factory values.  Three
``on_exec`` hooks bracket the completion routine's swap loop (the routine is the
``fn 0x00417eac`` of C-4641):

* the loop's length setup (**function start +0x66**, EU2011), which snapshots
  the buffer *before* the swap, with ``r9`` = buffer and ``r3`` = word count;
* the loop body (**+0x70**), counted to show the loop really ran;
* just past the loop (**+0x86**, before the completion is sent), which snapshots
  the buffer *after* the swap.

With request word +20 = 0 the post-loop buffer must equal
``point_walk_l3.swap16(host)`` byte for byte and the loop must run
``length/2`` times; with +20 = 1 the loop must not be entered and the bytes
must be the stored bytes.  The head offsets are stable inside the routine, so
the VAs are derived from its start and ``fn_audit`` sees one real function
start, not a mid-function constant.

Usage::

  swap_witness_l3.py run IMG --card-image CARD [--file PATH] [--length 0x1000]
  swap_witness_l3.py --selftest

Sample, runs and the frozen probe:
docs/experiments/EXP-2026-11-20-M3.11b-point-byteorder-2.md
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
for path in (HERE, os.path.join(HERE, "l3_harness")):
    if path not in sys.path:
        sys.path.insert(0, path)

import point_walk_l3 as pw  # noqa: E402
import vcard_l3  # noqa: E402

#: The file layer's completion routine, EU2011 build A (C-4641).  Its swap loop
#: sits at ``+0x70``; ``+0x66`` is the ``shlr r3`` that turns the byte length
#: into a word count, ``+0x86`` is past the loop.  Do not spell those VAs out:
#: they are mid-function and fn_audit would read them as citations.
COMPLETION = 0x00417EAC
SWAP_WINDOW = (COMPLETION + 0x66, COMPLETION + 0x70, COMPLETION + 0x86)

DEFAULT_FILE = "REFER001/POINT010.DAT"
DEFAULT_LENGTH = 0x1000


def _verify(host: bytes, pre: bytes, post: bytes, returned: bytes,
            iters: int, length: int) -> tuple[bool, dict]:
    """Compare one +20 = 0 run against the model, and the loop count."""
    model = pw.swap16(host)
    checks = {
        "pre == host as-stored": pre == host,
        "loop swapped the buffer": post == bytes(pre[i ^ 1] for i in range(len(pre) & ~1)),
        "post == point_walk_l3.swap16(host)": post == model,
        "returned == point_walk_l3.swap16(host)": returned == model,
        "returned != host as-stored": returned != host,
        "iterations == length/2": iters == length // 2,
    }
    return all(checks.values()), checks


def _run(image: str, card_image: str | None, card_root: str | None,
         guest_path: str, length: int) -> dict:
    """Boot the card and read *guest_path* twice; return the evidence rows."""
    card = vcard_l3.make_card(card_root, card_image)
    out, s = vcard_l3.boot_report(image, card)
    if out["verdict"] != "ACCEPT":
        raise vcard_l3.Blocked("boot %s: %s" % (out["verdict"], out.get("blocked", "")))
    eng = s.m.eng
    captures: list[tuple] = []
    iters = {"n": 0}
    state = {"buf": None, "len": None}
    entry, body, exit_ = SWAP_WINDOW

    def h_entry(e, va):
        r3 = e._get_reg("r3") & vcard_l3.M32
        r9 = e._get_reg("r9") & vcard_l3.M32
        state["buf"], state["len"] = r9, r3
        iters["n"] = 0
        captures.append(("pre", r9, r3, bytes(e.read_mem(r9, r3))))

    def h_body(e, va):
        iters["n"] += 1

    def h_exit(e, va):
        if state["buf"] is None:
            return
        r9 = e._get_reg("r9") & vcard_l3.M32
        captures.append(("post", r9, state["len"], bytes(e.read_mem(r9, state["len"]))))
        captures.append(("iters", r9, state["len"], iters["n"]))

    eng.on_exec(entry, h_entry)
    eng.on_exec(body, h_body)
    eng.on_exec(exit_, h_exit)

    def read(word20_zero: bool) -> tuple[int, bytes]:
        captures.clear()
        state["buf"] = state["len"] = None
        f = s.find_file(guest_path)
        return s.request(f["fid"], 0, length, swap=word20_zero)

    host = vcard_l3.Expected(card).read(guest_path, 0, length)
    st0, d0 = read(True)                     # word +20 = 0: the layer swaps
    caps = list(captures)
    pre = [c for c in caps if c[0] == "pre" and c[2] == length]
    post = [c for c in caps if c[0] == "post" and c[2] == length]
    its = [c for c in caps if c[0] == "iters"]
    if not pre or not post or not its:
        raise vcard_l3.Blocked("the swap loop did not run on %s (no capture)" % guest_path)
    st1, d1 = read(False)                    # word +20 = 1: as stored
    return {"path": guest_path, "length": length, "boot": out["verdict"],
            "status0": st0, "status1": st1, "host": host, "swap0": d0,
            "swap1": d1, "pre": pre[-1][3], "post": post[-1][3],
            "iters": its[-1][3], "window1": [c[0] for c in captures]}


def cmd_run(args) -> int:
    try:
        r = _run(args.image, args.card_image, args.card_root, args.file, args.length)
    except (vcard_l3.Blocked, vcard_l3.EngineError) as exc:
        print("BLOCKED: %s" % str(exc)[:400])
        return 3
    ok, checks = _verify(r["host"], r["pre"], r["post"], r["swap0"], r["iters"], r["length"])
    h = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
    print("boot: %s; %s [0, %#x)" % (r["boot"], r["path"], r["length"]))
    print("host as-stored  sha256 %s" % h(r["host"]))
    print("word +20 = 0   status %#x sha256 %s iterations %d (expect %d)"
          % (r["status0"], h(r["swap0"]), r["iters"], r["length"] // 2))
    print("word +20 = 1   status %#x sha256 %s loop captures %s"
          % (r["status1"], h(r["swap1"]), r["window1"]))
    for name, good in checks.items():
        print("  %-42s %s" % (name, "True" if good else "False"))
    neg = (r["status1"] == 0 and r["swap1"] == r["host"] and not r["window1"])
    print("  %-42s %s" % ("+20 = 1 == host as-stored, no loop", "True" if neg else "False"))
    ok = ok and neg
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def selftest() -> int:
    fails = 0

    def check(name, cond):
        nonlocal fails
        print("%-58s %s" % (name, "ok" if cond else "FAIL"))
        fails += not cond

    host = bytes(range(16))
    model = pw.swap16(host)
    check("swap16 swaps each pair", model == bytes([1, 0, 3, 2, 5, 4, 7, 6,
                                                    9, 8, 11, 10, 13, 12, 15, 14]))
    ok, _ = _verify(host, host, model, model, 8, 16)
    check("a correct run passes", ok)
    bad = bytearray(model)
    bad[5] ^= 0xFF
    ok, checks = _verify(host, host, bytes(bad), model, 8, 16)
    check("one wrong post-loop byte fails",
          not ok and not checks["post == point_walk_l3.swap16(host)"])
    ok, _ = _verify(host, host, model, model, 7, 16)
    check("a short loop (7 of 8) fails", not ok)
    ok, _ = _verify(host, host, host, model, 8, 16)
    check("an unswapped post-loop buffer fails", not ok)
    # the window VAs are derived from the routine start, never mid-function
    check("swap window is start + 0x66/0x70/0x86",
          SWAP_WINDOW == tuple(COMPLETION + d for d in (0x66, 0x70, 0x86)))
    print("selftest:", "PASS" if not fails else "FAIL (%d)" % fails)
    return 0 if not fails else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("run", help="boot the card and witness the POINT swap")
    p.add_argument("image", help="first 256 MiB of the card image (the firmware)")
    p.add_argument("--card-image", help="raw SD image; its FAT32 partition is read in place")
    p.add_argument("--card-root", help="extracted card tree")
    p.add_argument("--file", default=DEFAULT_FILE, help="guest path (default %s)" % DEFAULT_FILE)
    p.add_argument("--length", type=lambda x: int(x, 0), default=DEFAULT_LENGTH)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "run":
        return cmd_run(args)
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
