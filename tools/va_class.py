#!/usr/bin/env python3
"""Classify module VAs by what the CE loader puts there (H49).

A "compressed sec1" blocker hides three different cases, and only one of them
needs the CE codec (M1.2f):

  CODE    executable section, stored plain: read it from the image.
  IAT     an import slot (FirstThunk entry). The loader overwrites it with the
          resolved export address, so its stored bytes never matter: bind it
          to a stub. The DLL and the export name are printed.
  INIT    inside a compressed section, below its ``uncompressed_len`` (the
          size of the stored, initialised bytes, parsed by ``cerom.py
          comphdr``). Only these bytes need M1.2f.
  BSS     inside a section, at or above its initialised length and below
          ``vsize``. The loader zero-fills it; the program writes it at run
          time. Decompressing the section yields zeros here, so M1.2f cannot
          unblock a reader that needs these bytes: find the writer instead.
  DATA    a plain (stored) non-executable section below ``psize``.
  OUTSIDE no section of the module covers the VA.

Usage:
  va_class.py IMG --module Navi.exe [--image-start 0x200200]
              [--resolve-with 0x3e00200 ...] VA [VA ...] [--json]
  va_class.py --selftest

``--resolve-with`` names other CE images whose exports resolve ordinal
imports (COREDLL lives in build B at 0x3e00200 on the ZE0 card).

Exit codes: 0 ok, 1 selftest failure, 2 usage or image error.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cerom  # noqa: E402

IMAGE_SCN_COMPRESSED = cerom.IMAGE_SCN_COMPRESSED
MEM_EXECUTE = 0x20000000


def section_layout(rom, data, module, image_start):
    """Sections of ``module`` with their initialised length."""
    mod = rom.module(module)
    e = rom.e32(mod)
    init = {}
    if any(s["flags"] & IMAGE_SCN_COMPRESSED for s in rom.o32(mod)):
        rep = cerom.comphdr_report(data, "image", module=module,
                                   image_start=image_start)
        for s in rep["sections"]:
            if s["segment"] == 0 and s["verdict"] == "HOLDS":
                init[int(s["rva"], 16)] = s["uncompressed_len"]
    out = []
    for i, s in enumerate(rom.o32(mod)):
        comp = bool(s["flags"] & IMAGE_SCN_COMPRESSED)
        ilen = init.get(s["rva"]) if comp else min(s["psize"], s["vsize"])
        out.append(dict(index=i, start=e["vbase"] + s["rva"], vsize=s["vsize"],
                        psize=s["psize"], flags=s["flags"], compressed=comp,
                        exec=bool(s["flags"] & MEM_EXECUTE), init_len=ilen))
    return out


def import_slots(rom, module, resolvers):
    """slot VA -> (dll, name) with ordinals resolved through ``resolvers``."""
    exports = {}
    for r in resolvers:
        for m in r.modules():
            if not m["name"]:
                continue
            try:
                for ordinal, name, _rva in r.exports(m):
                    exports.setdefault((m["name"].lower(), ordinal), name)
            except (KeyError, ValueError, TypeError, IndexError, Exception):  # noqa: BLE001
                continue
    slots = {}
    for dll, slot, name, ordinal in rom.imports(rom.module(module)):
        if name is None:
            name = exports.get((dll.lower(), ordinal), "#%d" % ordinal)
        slots[slot] = (dll, name)
    return slots


def classify(va, sections, slots):
    if va in slots or (va & ~3) in slots:
        dll, name = slots[va & ~3]
        return dict(cls="IAT", detail="%s!%s" % (dll, name))
    for s in sections:
        if s["start"] <= va < s["start"] + max(s["vsize"], s["psize"]):
            off = va - s["start"]
            tag = "sec%d" % s["index"]
            if s["exec"] and not s["compressed"]:
                return dict(cls="CODE", detail=tag)
            if s["init_len"] is None:
                return dict(cls="UNKNOWN", detail=tag + " compressed, header not parsed")
            if off < s["init_len"]:
                if s["compressed"]:
                    return dict(cls="INIT", detail="%s +0x%x < init 0x%x (needs M1.2f)"
                                % (tag, off, s["init_len"]))
                return dict(cls="DATA", detail=tag)
            return dict(cls="BSS", detail="%s +0x%x >= init 0x%x (zero at load; find the writer)"
                        % (tag, off, s["init_len"]))
    return dict(cls="OUTSIDE", detail="no section")


def run(args):
    with open(args.image, "rb") as f:
        data = f.read()
    rom = cerom.CERom(data, args.image_start)
    resolvers = [rom] + [cerom.CERom(data, s) for s in (args.resolve_with or [])]
    sections = section_layout(rom, data, args.module, args.image_start)
    slots = import_slots(rom, args.module, resolvers)
    rows = []
    for text in args.va:
        va = int(text, 0)
        rows.append(dict(va="0x%08x" % va, **classify(va, sections, slots)))
    if args.json:
        print(json.dumps(dict(module=args.module, sections=sections,
                              iat_slots=len(slots), rows=rows), indent=1))
    else:
        for s in sections:
            print("sec%d start=0x%08x vsize=0x%x init=%s %s%s" % (
                s["index"], s["start"], s["vsize"],
                "?" if s["init_len"] is None else "0x%x" % s["init_len"],
                "exec " if s["exec"] else "", "COMPRESSED" if s["compressed"] else "plain"))
        print("iat slots: %d" % len(slots))
        for r in rows:
            print("%s  %-7s %s" % (r["va"], r["cls"], r["detail"]))
    return 0


def selftest():
    secs = [dict(index=0, start=0x11000, vsize=0x1000, psize=0x1000, flags=0x60000020,
                 compressed=False, exec=True, init_len=0x1000),
            dict(index=1, start=0x12000, vsize=0x10000, psize=0x100, flags=0xc8002040,
                 compressed=True, exec=False, init_len=0x800),
            dict(index=2, start=0x22000, vsize=0x100, psize=0x80, flags=0x48002040,
                 compressed=True, exec=False, init_len=None)]
    slots = {0x12000: ("COREDLL.dll", "memset")}
    cases = [(0x11010, "CODE"), (0x12000, "IAT"), (0x12002, "IAT"), (0x12400, "INIT"),
             (0x12800, "BSS"), (0x1ffff, "BSS"), (0x22010, "UNKNOWN"), (0x30000, "OUTSIDE")]
    bad = 0
    for va, want in cases:
        got = classify(va, secs, slots)["cls"]
        if got != want:
            print("FAIL 0x%x: %s != %s" % (va, got, want))
            bad += 1
    print("va_class selftest: %s (%d cases)" % ("OK" if not bad else "FAIL", len(cases)))
    return 1 if bad else 0


def main():
    if "--selftest" in sys.argv:
        return selftest()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("image")
    p.add_argument("--module", required=True)
    p.add_argument("--image-start", type=lambda s: int(s, 0), default=0x200200)
    p.add_argument("--resolve-with", action="append", type=lambda s: int(s, 0))
    p.add_argument("--json", action="store_true")
    p.add_argument("va", nargs="+")
    return run(p.parse_args())


if __name__ == "__main__":
    sys.exit(main())
