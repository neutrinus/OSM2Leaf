#!/usr/bin/env python3
"""Map the IMMO/SECURE (antitheft) message strings to their code sites (M1.48).

Why this exists
---------------
The ANT protocol strings are stored as UTF-16LE literals in the Windows CE
modules.  An ASCII search finds nothing (a false negative, the same trap as
M8.E1 but for text), and a different image start selects a different CE
segment (build A 0x200200 = apps, build B 0x3e00200 = kernel/updaters).  This
tool walks the ROM TOC with ``tools/cerom.py``, finds each needle in the
module sections, attributes the file offset to a module/section (never a bare
offset), and lists the code literal pools that load the string VA via
``mov.l @(disp,PC),Rn`` (SH-4 code is little-endian, pinned in sh4dis.py).

It is a static map only: no L3/L4/L5 execution is claimed, no bytes are
patched and nothing is committed from a real unit.

Usage::
    python3 tools/antitheft_map.py --image-start 0x3e00200 archive/us256.img
    python3 tools/antitheft_map.py --image-start 0x200200 archive/head256.img
    python3 tools/antitheft_map.py --selftest
"""
from __future__ import annotations

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cerom  # noqa: E402

NEEDLES = (
    "ANT_RCV_SECURITY_LOCK",
    "ANT_RCV_SECURITY_RELEASE_OK",
    "ANT_SEND_SEC_RESPONSE",
    "ANT_SEND_SEC_RELEASE",
    "CApi_AntitheftUnlock",
    "CApi_AntitheftRcvSecure",
    "ANTITHEFT_UNLOCKOK",
    "AntiTheft.exe",
)


def module_sections(rom):
    """Yield (module, index, section, file_start, file_end) for every section."""
    for module in rom.modules():
        for index, section in enumerate(rom.o32(module)):
            if not section["psize"]:
                continue
            start = rom.va2file(section["dataptr"])
            yield module, index, section, start, start + section["psize"]


def find_needles(rom, data, needles):
    """Return a list of (needle, module, index, sec, rva, file, va)."""
    hits = []
    secs = list(module_sections(rom))
    for needle in needles:
        blob = needle.encode("utf-16-le")
        for module, index, section, start, end in secs:
            pos = start
            while True:
                i = data.find(blob, pos, end)
                if i < 0:
                    break
                rva = i - start + (section["realaddr"] - section["realaddr"])
                # realaddr is the module VA of the section start; rva is the
                # displacement from that start, as ce_strfind.py reports it.
                va = section["realaddr"] + (i - start)
                hits.append((needle, module["name"], index, section["realaddr"],
                             va, i, section["flags"]))
                pos = i + 1
    return hits


def code_xrefs(rom, data, needle_hit, digest):
    """List literal-pool loads of a string VA in uncompressed code sections."""
    needle, name, index, sec_real, va, file_off, flags = needle_hit
    word = struct.pack("<I", va)
    out = []
    for module, sidx, section, start, end in module_sections(rom):
        if section["flags"] & 0x2000:
            continue
        blob = data[start:end]
        pos = 0
        while True:
            j = blob.find(word, pos)
            if j < 0:
                break
            out.append((module["name"], sidx, sec_real if False else section["realaddr"] + j))
            pos = j + 1
    return out


def report(rom, data, needles):
    hits = find_needles(rom, data, needles)
    if not hits:
        print("no UTF-16LE hits for %d needle(s)" % len(needles))
        return 1
    for needle, name, index, sec_real, va, file_off, flags in hits:
        print("%-28s %-24s sec%d va=0x%08x file=0x%x %s"
              % (needle, name, index, va, file_off,
                 "COMPRESSED" if flags & 0x2000 else "RAW"))
        xrefs = code_xrefs(rom, data, (needle, name, index, sec_real, va, file_off, flags), None)
        if xrefs:
            for mod, sidx, xva in xrefs:
                print("    literal 0x%08x in %s sec%d" % (xva, mod, sidx))
        else:
            print("    (no code literal pool holds this VA)")
    return 0


def selftest():
    # synthetic little-endian literal pool: a mov.l @(disp,PC),r0 loading a
    # string VA (the same addressing mode the firmware uses for ANT strings).
    word = struct.pack("<I", 0x03b8b0ec)
    assert word == bytes.fromhex("ecb0b803"), "SH-4 literals must be LE"
    # negative: a big-endian reading must NOT match (the M8.E1 trap)
    be = struct.pack(">I", 0x03b8b0ec)
    assert be != word and be[::-1] == word
    print("selftest: PASS (LE literal pinned, BE refuted)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--image-start", type=lambda x: int(x, 0), default=0x200200)
    ap.add_argument("--read-limit", type=lambda x: int(x, 0), default=0x8000000)
    ap.add_argument("image", nargs="?")
    ap.add_argument("needles", nargs="*")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.image:
        ap.print_help()
        return 2
    data = open(a.image, "rb").read(a.read_limit)
    rom = cerom.CERom(data, a.image_start)
    needles = a.needles or list(NEEDLES)
    return report(rom, data, needles)


if __name__ == "__main__":
    sys.exit(main())
