#!/usr/bin/env python3
"""Per-record area masks, the USA/Euro launch diff and the mode-4 selection.

M2.20 asks whether a region change (PROD area byte, C-5201) leaves the unit
recoverable, i.e. whether software-update mode still starts.  This tool reads
the same launch table as ``tools/applaunch_table.py`` (M1.34) and answers the
table-side questions.  Every number it prints is read from the image through
the code getters (``0x03bccb84`` count, ``0x03bccb88`` base), not fitted.

Subcommands (all take ``IMG`` and ``--image-start``; default build B):

* ``masks``       every record whose area mask is not all-areas, plus a focus
                  list (the update programs) with the VA of its mode and area
                  mask fields (record VA + 4 / + 0xc);
* ``diff``        records where USA ``0x00040000`` and Euro ``0x00020000``
                  selection disagree, ``(area & 0x40000) != (area & 0x20000)``;
* ``field-diff``  field-wise comparison of the EU and US tables, with
                  ``--other IMG`` (base/count/record VAs must match);
* ``select``      the walker's per-record filter ``fn 0x03bcc564`` for one
                  area and boot mode (mode 4 = mask ``0x10``, the update
                  programs; mode 0 = mask ``0x1``, the everyday boot);
* ``mutate``      negative control: set one record's area mask in memory and
                  re-run ``select`` for USA and Euro;
* ``table-hash``  SHA-256 of the ``count * 0x310`` table bytes;
* ``braf``        the boot-mode -> mask branch table ``0x03bb1bd8``
                  (``fn 0x03bcb9fc``) as bytes and their targets.

The area filter (M1.34, C-5350) starts a record iff
``(+4 & mode_mask) != 0`` and ``(+0xc & area_mask) != 0``.  An area mask of
``0xffff0000`` carries every area bit, so such a record starts for USA, Euro
and every other value ``fn 0x03bcba58`` maps.

Usage:
  launch_area.py --selftest
  launch_area.py IMG masks [--focus UpdateMng.exe ...]
  launch_area.py IMG diff
  launch_area.py IMG field-diff --other IMG2
  launch_area.py IMG select --area 0x30 --mode 4 [--name UpdateMng.exe]
  launch_area.py IMG mutate --index 98 --area 0x00020000 --mode 4
  launch_area.py IMG table-hash
  launch_area.py IMG braf

Stdlib only; addresses come from ``tools/cerom.py``.
"""

import argparse
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cerom  # noqa: E402
import applaunch_table as A  # noqa: E402
import hashutil  # noqa: E402

sha256 = hashutil.sha256_bytes

USA, EURO = 0x00040000, 0x00020000
ALL_AREAS = 0xffff0000
MASK_FIELD = 0x0c
MODE_FIELD = 0x04
BRAF_VA = 0x03bb1bd8
BRAF_INSN = 0x03bcba12   # braf instruction address; target = insn + 4 + offset


def update_records(recs, names):
    want = {n.lower() for n in names}
    return [r for r in recs if r["name"].lower() in want]


def area_diff(recs):
    """Records where USA (0x40000) and Euro (0x20000) selection disagree."""
    usa, euro = [], []
    for r in recs:
        u = bool(r["area_mask"] & USA)
        e = bool(r["area_mask"] & EURO)
        if u != e:
            (usa if u else euro).append(r)
    return usa, euro


def read_table(img, image_start):
    segs = A.load_segments(img, image_start, "AppLaunch.dll")
    hits = A.find_getters(segs)
    if len(hits) != 1:
        raise SystemExit("getters: %d candidate pairs (need exactly 1)" % len(hits))
    cva, count, bva, base = hits[0]
    recs = A.parse_table(segs, base, count)
    bad = A.check_table(recs, segs, base, count)
    if bad:
        raise SystemExit("structure: FAIL " + "; ".join(bad[:5]))
    raw = A.read_va(segs, base, count * A.REC)
    return recs, base, count, raw


def show(rec):
    return ("  #%3d %-22s rec 0x%08x area=0x%08x @0x%08x mode=0x%04x @0x%08x"
            % (rec["index"], rec["name"], rec["va"], rec["area_mask"],
               rec["va"] + MASK_FIELD, rec["mode_mask"], rec["va"] + MODE_FIELD))


def cmd_masks(recs, focus):
    print("## every record whose area mask is not all-areas (0x%08x)" % ALL_AREAS)
    for r in recs:
        if r["area_mask"] != ALL_AREAS:
            print(show(r))
    print("## focus records (mode mask in @+4, area mask in @+0xc)")
    for r in update_records(recs, focus):
        print(show(r))


def cmd_diff(recs):
    usa, euro = area_diff(recs)
    print("## USA-only (area & 0x%08x, not Euro)" % USA)
    for r in usa:
        print(show(r))
    print("## Euro-only (area & 0x%08x, not USA)" % EURO)
    for r in euro:
        print(show(r))
    print("# counts: USA-only=%d Euro-only=%d" % (len(usa), len(euro)))


def cmd_field_diff(recs, base, count, other, other_base, other_count, other_recs):
    print("base A 0x%08x count %d | base B 0x%08x count %d"
          % (base, count, other_base, other_count))
    if (base, count) != (other_base, other_count):
        print("# tables differ in base or count")
        return
    diff = []
    for i in range(count):
        changed = [k for k in recs[i]
                   if recs[i][k] != other_recs[i][k]]
        if changed:
            diff.append((i, changed))
    print("# records with any differing field: %d" % len(diff))
    for i, changed in diff:
        print("  #%3d %-22s fields %s" % (i, recs[i]["name"], ",".join(changed)))


def cmd_select(recs, area, mode, name):
    sel, amask, mmask = A.select(recs, area, mode, 1)
    print("select area=0x%02x (mask 0x%08x) mode=%d (mask 0x%04x): %d of %d"
          % (area, amask, mode, mmask, len(sel), len(recs)))
    for r in sel:
        if name and r["name"].lower() != name.lower():
            continue
        print("  " + ("opt " if r["options"] else "    ") + show(r)[2:])


def cmd_mutate(recs, index, new_area, mode):
    mut = copy.deepcopy(recs)
    print("mutate #%d %s area 0x%08x -> 0x%08x"
          % (index, mut[index]["name"], mut[index]["area_mask"], new_area))
    mut[index]["area_mask"] = new_area
    for area, label in ((0x20, "USA"), (0x30, "Euro")):
        sel, _, _ = A.select(mut, area, mode, 1)
        print("  area 0x%02x (%s) mode %d: %s present %s"
              % (area, label, mode, mut[index]["name"],
                 any(r["index"] == index for r in sel)))


def cmd_braf(img, image_start):
    data = open(img, "rb").read(128 << 20)
    rom = cerom.CERom(data, image_start)
    mod = rom.module("AppLaunch.dll")
    sec = [s for s in rom.o32(mod)
           if s["realaddr"] <= BRAF_VA < s["realaddr"] + s["vsize"]][0]
    off = rom.va2file(sec["dataptr"]) + (BRAF_VA - sec["realaddr"])
    rawoff = data[off:off + 10]
    print("## braf table 0x%08x (10 bytes): %s" % (BRAF_VA, rawoff.hex(" ")))
    for mode, b in enumerate(rawoff):
        print("  mode %d -> +0x%02x -> 0x%08x" % (mode, b, BRAF_INSN + 4 + b))


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + name)
        ok = ok and cond

    def rec(i, name, mode, area):
        return {"index": i, "name": name, "va": 0x10000 + i * A.REC,
                "type": 3, "mode_mask": mode, "area_mask": area,
                "base_type": 0xffffffff, "options": 0}

    recs = [rec(0, "gwes.exe", 0x1, ALL_AREAS),
            rec(1, "UpdateMng.exe", 0x10, ALL_AREAS),
            rec(2, "PRGUpdate.exe", 0x10, ALL_AREAS),
            rec(3, "Rds", 0xffff, 0x00020000),
            rec(4, "XMRadio", 0xffff, USA),
            rec(5, "Navi.exe", 0x1, EURO),
            rec(6, "Navi.exe", 0x1, USA)]
    got = {r["name"] for r in update_records(recs, ["UpdateMng.exe", "PRGUpdate.exe"])}
    check("focus finds both updaters", got == {"UpdateMng.exe", "PRGUpdate.exe"})
    usa, euro = area_diff(recs)
    check("USA-only = XMRadio + US Navi (indices 4,6)",
          [r["index"] for r in usa] == [4, 6])
    check("Euro-only = Rds + EU Navi (indices 3,5)",
          [r["index"] for r in euro] == [3, 5])
    sel, _, _ = A.select(recs, 0x20, 4, 1)
    check("USA mode 4 selects UpdateMng and PRGUpdate",
          {"UpdateMng.exe", "PRGUpdate.exe"} <= {r["name"] for r in sel})
    sel, _, _ = A.select(recs, 0x20, 0, 1)
    check("USA mode 0 selects the USA Navi only (not JP/Euro)",
          [r["index"] for r in sel if r["name"] == "Navi.exe"] == [6])
    check("all-areas updaters are in neither diff list",
          all(r["area_mask"] == ALL_AREAS for r in update_records(recs, ["UpdateMng.exe"])))
    # negative control: mutate UpdateMng to Euro-only, USA loses it
    mut = copy.deepcopy(recs)
    mut[1]["area_mask"] = EURO
    sel20, _, _ = A.select(mut, 0x20, 4, 1)
    sel30, _, _ = A.select(mut, 0x30, 4, 1)
    check("negative: #1 area->Euro, USA loses UpdateMng, Euro keeps it",
          not any(r["index"] == 1 for r in sel20)
          and any(r["index"] == 1 for r in sel30))
    print("selftest: %s" % ("OK" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if "--selftest" in argv:
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("image")
    ap.add_argument("--image-start", type=lambda s: int(s, 0), default=0x3e00200)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("masks")
    m.add_argument("--focus", dest="focus", nargs="+",
                   default=["UpdateMng.exe", "PRGUpdate.exe"])
    sub.add_parser("diff")
    fd = sub.add_parser("field-diff")
    fd.add_argument("--other", required=True)
    sub.add_parser("table-hash")
    sub.add_parser("braf")
    s = sub.add_parser("select")
    s.add_argument("--area", type=lambda v: int(v, 0), required=True)
    s.add_argument("--mode", type=int, default=0)
    s.add_argument("--name")
    mu = sub.add_parser("mutate")
    mu.add_argument("--index", type=int, required=True)
    mu.add_argument("--area", type=lambda v: int(v, 0), required=True)
    mu.add_argument("--mode", type=int, default=4)
    args = ap.parse_args(argv)

    if args.cmd == "braf":
        cmd_braf(args.image, args.image_start)
        return 0
    recs, base, count, raw = read_table(args.image, args.image_start)
    print("table 0x%08x, %d records, %d bytes" % (base, count, len(raw)))
    if args.cmd == "masks":
        cmd_masks(recs, args.focus)
    elif args.cmd == "diff":
        cmd_diff(recs)
    elif args.cmd == "field-diff":
        o_recs, o_base, o_count, _ = read_table(args.other, args.image_start)
        cmd_field_diff(recs, base, count, args.other, o_base, o_count, o_recs)
    elif args.cmd == "select":
        cmd_select(recs, args.area, args.mode, args.name)
    elif args.cmd == "mutate":
        cmd_mutate(recs, args.index, args.area, args.mode)
    elif args.cmd == "table-hash":
        print("sha256 %s" % sha256(raw))
    return 0


if __name__ == "__main__":
    sys.exit(main())
