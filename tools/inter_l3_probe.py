#!/usr/bin/env python3
"""Follow the INTER/FRWAY openers and read-watch their buffer (M3.16 r3).

Three commands, all on real bytes:

``openers``
    Run ``name_loaders.py``'s static opener query on the mounted card's image;
    print the `0x003fbed8` row (family table and one-call-away read issuers)
    plus an L3 ``vcard_l3.py trace`` of the real opener for family 4 (INTER)
    and 3 (FRWAY).  This is the structural source of the two follower VAs.

``watch``
    Put the decoded factory INTER001 page in a guest buffer, seed the two
    context words the followers dereference (ctx+0x68 name id, ctx+0x7c
    family), call each follower directly with a read watch on that page, and
    print which offsets were touched.  The LCTBL reader ``0x0040de98`` is the
    positive control.  A watch with no guest read is reported as NO READER.

``scan``
    Two derived structural signature families over build-A Navi.exe sec0,
    derived from the L3-observed *context-header* reads and the family dispatch
    in the follower disassembly (NOT from the doc byte grammar), to see whether
    any other function has the same shape.  f5 = the ctx+0x7c/+0x68 read pair;
    f6 = the `cmp/eq #4` + `cmp/eq #3` family dispatch.

No vendor byte is stored here: the tool reads the image/card it is given.

Usage::

  python3 tools/inter_l3_probe.py --selftest
  python3 tools/inter_l3_probe.py openers IMG --graph g.json --card-root ROOT
  python3 tools/inter_l3_probe.py watch IMG --card-root ROOT --buf INTER001.DAT
  python3 tools/inter_l3_probe.py scan IMG

Method and results: docs/experiments/EXP-2026-11-24-M3.16-opener-follow.md
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
for path in (HERE, os.path.join(HERE, "l3_harness")):
    if path not in sys.path:
        sys.path.insert(0, path)

import cerom  # noqa: E402
import sh4dis  # noqa: E402
import vcard_l3 as V  # noqa: E402
from l3_harness import watch as watch_mod  # noqa: E402

IMAGE_A = 0x200200
MODULE = "Navi.exe"
OPENER = 0x003FBED8
FOLLOWERS = (0x003FC0EC, 0x003FC518)     # pdata STARTs, C-4666 / name_loaders
POS_CONTROL = 0x0040DE98                  # LCTBL reader
CTX_NAME_OFF = 0x68
CTX_FAMILY_OFF = 0x7C
PAGE_VA = 0x50000000
FAMILY = {4: "INTER", 3: "FRWAY"}


# ---------------------------------------------------------------------------
# shared helpers

def _boot(image: str, card_root: str):
    card = V.make_card(card_root, None, {})
    out, session = V.boot_report(image, card)
    return out, session, card


def _module_halfwords(image: bytes):
    """(halfwords, base_va, psize) of Navi.exe sec0, little-endian."""
    rom = cerom.CERom(image, IMAGE_A)
    mod = rom.module(MODULE)
    sec = list(rom.o32(mod))[0]
    off = rom.va2file(sec["dataptr"])
    return sh4dis.halfwords_le(image[off:off + sec["psize"]]), sec["realaddr"], sec["psize"]


# ---------------------------------------------------------------------------
# openers

def cmd_openers(args) -> int:
    import name_loaders as NL
    with open(args.image, "rb") as fh:
        data = fh.read(256 << 20)
    blob, base, graph, cen = NL._load(argparse.Namespace(
        image=args.image, image_start=IMAGE_A, module=MODULE, graph=args.graph))
    rows = NL.openers(cen, graph, NL.RESOLVER_EU2011,
                      [int(x, 0) for x in NL.READERS_EU2011])
    row = next((r for r in rows if r["fn"] == OPENER), None)
    if row is None:
        print("BLOCKED: opener %#010x is not a resolver caller" % OPENER)
        return 3
    print("opener %#010x: direct=%s tables=%s" % (
        OPENER, row["direct"],
        [(hex(t["table"]), t["names"]) for t in row["tables"]]))
    print("one-call-away read issuers: %s" %
          ", ".join(hex(x) for x in row["reads"]))
    for fam, name in sorted(FAMILY.items()):
        argv = ["ctx"]
        out, session, card = _boot(args.image, args.card_root)
        if out["verdict"] != "ACCEPT":
            print("%s: boot %s" % (name, out["verdict"]))
            continue
        m = session.m
        ctx = m.malloc(0x800)
        m.put(ctx, bytes(0x800))
        m.put(ctx + 104, struct.pack("<I", 0x14CC))
        m.put(ctx + CTX_FAMILY_OFF, struct.pack("<I", fam))
        try:
            r0 = m.call(0x003FEE70, [ctx], max_insns=20_000_000)
        except (V.Blocked, Exception) as exc:  # noqa: BLE001
            r0 = "stop: %s" % str(exc)[:80]
        resolves = [e for e in card.log if e["op"] == "resolve"]
        named = resolves[-1]["name"] if resolves else "-"
        print("L3 opener family %d (%s): r0=%s, named=%s" % (
            fam, name, r0 if isinstance(r0, str) else hex(r0), named))
    return 0


# ---------------------------------------------------------------------------
# watch

def cmd_watch(args) -> int:
    out, session, card = _boot(args.image, args.card_root)
    if out["verdict"] != "ACCEPT":
        V.show_boot(out)
        return 3
    m = session.m
    buf = Path(args.buf).read_bytes()
    m.eng.map("interpage", PAGE_VA, bytearray(buf) + bytearray(0x40), "rw")
    m.put(PAGE_VA + CTX_NAME_OFF, struct.pack("<I", 0x14CC))
    m.put(PAGE_VA + CTX_FAMILY_OFF, struct.pack("<I", 4))
    m.eng.watch(PAGE_VA, PAGE_VA + len(buf), kind="r", name="page-r")
    m.eng.arm_watch()
    results = {}
    for va in [int(x, 0) for x in args.entries.split(",")]:
        hits0 = len(m.eng.watch_hits())
        try:
            r0 = m.call(va, [PAGE_VA, 0, 0], max_insns=20_000_000)
            fault = None
        except Exception as exc:  # noqa: BLE001
            r0, fault = None, exc
        hits = m.eng.watch_hits()[hits0:]
        rows = watch_mod.summarise(hits, PAGE_VA)
        guest_r = sum(1 for h in hits if h.kind == "r")
        results[va] = {"r0": None if r0 is None else hex(r0 & 0xFFFFFFFF),
                       "guest_reads": guest_r, "rows": rows,
                       "fault": None if fault is None else type(fault).__name__}
        print("entry=%#010x r0=%s guest-reads=%d%s" % (
            va, results[va]["r0"], guest_r,
            "" if fault is None else " fault=%s" % results[va]["fault"]))
        for row in rows:
            print("  %s %s n=%d first=%s last=%s widths=%s" % (
                row["kind"], row["function"], row["accesses"],
                row["first_offset"], row["last_offset"], row["widths"]))
    real = [va for va in results if va != POS_CONTROL]
    touched = [va for va in real if any(
        r["first_offset"] in ("+0x1108", "+0x1110")
        or (r["first_offset"].startswith("+0x11")
            and r["kind"] == "r") for r in results[va]["rows"])]
    print("table-touched followers: %s" % (", ".join(hex(v) for v in touched) or "NONE"))
    ctl = results.get(POS_CONTROL)
    print("positive control %#010x: %s" % (
        POS_CONTROL,
        "PASS (guest-reads=%d)" % ctl["guest_reads"] if ctl and ctl["guest_reads"] else
        "NO READER"))
    if args.json:
        Path(args.json).write_text(__import__("json").dumps(results, indent=1))
    return 0 if touched else 1


# ---------------------------------------------------------------------------
# derived structural signature scan

MOV_IMM = 0xE000        # 0xEnii
ADD_IMM = 0x7000        # 0x7nii
MOVW_AT_RM = 0x6000     # 0x6n m 0
CMP_EQ_IMM_R0 = 0x8800  # 0x88ii
JSR_RN = 0x400B         # 0x40 n 0B (mask 0xF00F)
EXTU_W = 0x6000         # 0x6n n 0 (mask 0xF0FF) -- extu.w Rn,Rn


def _add_imm(h, imm):
    return (h & 0xF0FF) == (ADD_IMM | 0x0C) if imm == 12 else False


def _ctx_read(win, off):
    """True if the window contains `add #off,Rn; mov.l @Rn,Rm` (a ctx field read)."""
    for j, h in enumerate(win):
        if (h & 0xF0FF) != (ADD_IMM | off):
            continue
        reg = (h >> 8) & 0xF
        if any((h1 & 0xF00F) == 0x6002 and ((h1 >> 8) & 0xF) == reg
               for h1 in win[j + 1:j + 8]):
            return True
    return False


def f5(words, i):
    """Both L3-observed ctx reads in one function: `+0x7c` (family word) and
    `+0x68` (name id), each an `add #off,Rn; mov.l @Rn,Rm` pair.  Anchored on
    the `add #124` hit at pc 0x003fc142 / 0x003fc65c."""
    h = words[i]
    if (h & 0xF0FF) != (ADD_IMM | 0x7C):
        return False
    win = words[i:i + 168]
    return _ctx_read(win, 0x7C) and _ctx_read(win, 0x68)


def f6(words, i):
    """The two family-word comparisons (`cmp/eq #4` INTER, `cmp/eq #3` FRWAY)
    in one function with a `+0x68` ctx read -- the dispatch shape in
    `0x003fc518` (pcs 0x003fc542/0x003fc568/0x003fc534)."""
    h = words[i]
    if h != (CMP_EQ_IMM_R0 | 4):
        return False
    win = words[i + 1:i + 80]
    return (CMP_EQ_IMM_R0 | 3) in win and _ctx_read(win, 0x68)


FAMILIES = {5: f5, 6: f6}


def cmd_scan(args) -> int:
    with open(args.image, "rb") as fh:
        data = fh.read(256 << 20)
    words, base, psize = _module_halfwords(data)
    print("corpus %s sec0 %d B stored at VA %#x (uncompressed executable, C-2128)"
          % (MODULE, psize, base))
    for num, fn in sorted(FAMILIES.items()):
        hits = [base + 2 * i for i in range(len(words)) if fn(words, i)]
        print("f%d: %d candidate(s)  %s" % (
            num, len(hits), ", ".join(hex(h) for h in hits[:20])))
    return 0


# ---------------------------------------------------------------------------
def selftest() -> int:
    fails = 0

    def check(name, cond):
        nonlocal fails
        print("%-58s %s" % (name, "ok" if cond else "FAIL"))
        fails += not cond

    check("families are the two derived ones", sorted(FAMILIES) == [5, 6])
    check("followers are pdata-START pair", FOLLOWERS == (0x003FC0EC, 0x003FC518))
    words = [0x0009] * 400
    words[0] = ADD_IMM | (4 << 8) | 0x7C
    words[1] = 0x6002 | (4 << 8) | (5 << 4)
    words[3] = ADD_IMM | (6 << 8) | 0x68
    words[4] = 0x6002 | (6 << 8) | (7 << 4)
    check("f5 finds the synthetic context-read pair", f5(words, 0))
    words[1] = 0x0009
    check("f5 misses without the context load", not f5(words, 0))
    words = [0x0009] * 200
    words[0] = CMP_EQ_IMM_R0 | 4
    words[2] = ADD_IMM | (6 << 8) | 0x68
    words[3] = 0x6002 | (6 << 8) | (7 << 4)
    words[10] = CMP_EQ_IMM_R0 | 3
    check("f6 finds the family dispatch", f6(words, 0))
    words[10] = 0x0009
    check("f6 misses without cmp/eq #3", not f6(words, 0))
    print("selftest:", "PASS" if not fails else "FAIL (%d)" % fails)
    return 1 if fails else 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    o = sub.add_parser("openers")
    o.add_argument("image")
    o.add_argument("--graph", required=True)
    o.add_argument("--card-root", required=True)
    w = sub.add_parser("watch")
    w.add_argument("image")
    w.add_argument("--card-root", required=True)
    w.add_argument("--buf", required=True)
    w.add_argument("--entries", default="0x003fc0ec,0x003fc518,0x0040de98")
    w.add_argument("--json")
    s = sub.add_parser("scan")
    s.add_argument("image")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    for path in (args.image, getattr(args, "card_root", None), getattr(args, "buf", None)):
        if path and not Path(path).exists():
            print("error: missing input %s" % path, file=sys.stderr)
            return 2
    return {"openers": cmd_openers, "watch": cmd_watch, "scan": cmd_scan}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
