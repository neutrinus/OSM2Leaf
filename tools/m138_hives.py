#!/usr/bin/env python3
"""Decode a CE ROM segment's registry hives with the build's own DECOMP_SECT.

M1.38: ``ce_drivers.py`` hard-codes the EU2011 ``DECOMP_SECT 0x88037464``, so
the compressed hives of EU2014/EU2016 fail with ``UnmappedAccess``. This tool
locates each build's routine by reloc-masked digest match (``rom_changelog``,
no fitted address), decodes ``boot.hv``/``default.hv`` with that entry, and
prints the driver rows and hive stats. All addresses come from the ROM TOC.

    python3 tools/m138_hives.py --help
    python3 tools/m138_hives.py IMG --image-start 0x3e00200 [--name default.hv]
    python3 tools/m138_hives.py --selftest
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cerom  # noqa: E402
import cehive  # noqa: E402
import nk_decomp  # noqa: E402
import rom_changelog  # noqa: E402

REF_IMAGE = "archive/head256.img"
HIVES = ("boot.hv", "default.hv")
DRIVER_ROOTS = ("Drivers\\BuiltIn", "Drivers\\Launch")
FLASH_MARKERS = ("fmm", "flash", "lcd", "sdhc")


def decode_hives(data: bytes, image_start: int, image_b: int, ref_data: bytes):
    """Yield (name, entry, r0, size, rows, stats) for the two ROM hives."""
    entry = rom_changelog.discover_decomp_sect(data, ref_data)
    rom = cerom.CERom(data, image_start)
    regions = nk_decomp.nk_regions(data, image_b)
    out = []
    for f in rom.files():
        if f["name"].lower() not in HIVES:
            continue
        off = rom.va2file(f["load"])
        r0, blob = nk_decomp.decompress(data, off, f["csize"], f["rsize"],
                                        entry=entry, regions=regions)
        rows, st = cehive.tree(blob[:r0]) if r0 == f["rsize"] else ([], {})
        out.append((f["name"], entry, r0, f["rsize"], rows, st))
    return out


def flash_rows(rows):
    """Driver rows whose Dll name names a flash/FMM/LCD/SDHC driver."""
    found = []
    for path, name, typ, text in rows:
        if name != "Dll":
            continue
        dll = str(text or "").lower()
        if not any(t in dll for t in FLASH_MARKERS):
            continue
        root = path.rsplit("\\", 1)[0] if "\\" in path else ""
        if root not in DRIVER_ROOTS:
            continue
        found.append((path, str(text)))
    return found


def cmd_image(args):
    data = Path(args.image).read_bytes()
    ref = Path(args.ref).read_bytes()
    image_b = args.kernel_start
    for name, entry, r0, rsize, rows, st in decode_hives(
            data, args.image_start, image_b, ref):
        if args.name and name.lower() != args.name.lower():
            continue
        print("%s entry=0x%s r0=%d rsize=%d %s" % (
            name, "-" if entry is None else "%x" % entry, r0, rsize,
            "OK" if r0 == rsize else "FAIL"))
        if r0 != rsize:
            continue
        print("  keys=%d values=%d dangling=%d" % (
            st["keys"], st["values"], st["dangling"]))
        for path, dll in flash_rows(rows):
            print("  %s %s" % (path, dll))
    return 0


def _synthetic():
    """Synthetic driver rows (no vendor bytes): 4 in-scope, 1 outside."""
    return [
        ("Drivers\\Launch\\FMM_00000005", "Dll", "SZ", "fmmdrv_05.dll"),
        ("Drivers\\BuiltIn\\Flash", "Dll", "SZ", "flash.dll"),
        ("Drivers\\Launch\\LCD", "Dll", "SZ", "lcddrv.dll"),
        ("Drivers\\Launch\\SD", "Dll", "SZ", "SDHC.dll"),
        ("Software\\Other", "Dll", "SZ", "fmmdrv_07.dll"),
    ]


def rows_from(triples):
    return list(triples)


def _selftest():
    rows = _synthetic()
    got = flash_rows(rows)
    assert len(got) == 4, got
    assert all(p.startswith("Drivers\\") for p, _ in got), got
    assert ("Software\\Other", "fmmdrv_07.dll") not in got
    assert callable(decode_hives) and callable(flash_rows)
    print("m138_hives selftest: OK (filter 4/5 rows, outside-Drivers excluded)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", nargs="?", help="CE ROM image")
    ap.add_argument("--image-start", type=lambda x: int(x, 0), default=0x3e00200,
                    help="CE segment base (default 0x3e00200, build B)")
    ap.add_argument("--kernel-start", type=lambda x: int(x, 0), default=0x3e00200,
                    help="kernel segment base for region mapping (default 0x3e00200)")
    ap.add_argument("--name", help="only this hive (e.g. default.hv)")
    ap.add_argument("--ref", default=REF_IMAGE, help="EU2011 image with the reference DECOMP_SECT")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not args.image:
        ap.error("IMG is required unless --selftest is given")
    return cmd_image(args)


if __name__ == "__main__":
    sys.exit(main())
