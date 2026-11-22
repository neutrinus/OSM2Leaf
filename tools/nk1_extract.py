#!/usr/bin/env python3
"""Cut the unit-flash kernel image NK1 out of a LeafSDTools NAND dump (M8.C1k).

The head unit's 8 MiB NAND holds boot loaders in its first 256 KiB, then the
Windows CE XIP image NK1 (``ECEC`` at +0x40, VA ``0x88000000``), then other
regions.  This tool finds the CE image with the most modules on a 64 KiB
boundary and writes ``physlast - physfirst`` bytes from its start.  Nothing
else of the dump is written: the rest of the NAND, ``SRAM``, ``VFlash`` and
``PROD`` (card-lock password) stay out of the repository.

Usage:
  nk1_extract.py NAND.bin [-o firmware/unit-flash/nk1-QY7200ND.bin] [--sha256 HEX]
  nk1_extract.py NAND.bin --list        # every CE image in the dump
  nk1_extract.py --selftest
"""
import argparse
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cerom import CERom  # noqa: E402

STEP = 0x10000
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "firmware", "unit-flash", "nk1-QY7200ND.bin")
KNOWN_SHA256 = "b4b3542bb95d336c55ed11e1a4854be2c5f3dce1b60e074629d2b185f3b9fb00"


def images(data):
    """[(file offset, CERom, length)] for every CE image on a 64 KiB boundary."""
    out = []
    for off in range(0, len(data) - 0x48, STEP):
        if data[off + 0x40:off + 0x44] != b"ECEC":
            continue
        try:
            rom = CERom(data, off)
            h = rom.hdr
            length = h["physlast"] - h["physfirst"]
            if 0 < length <= len(data) - off and h["nummods"] < 0x1000:
                out.append((off, rom, length))
        except (ValueError, struct.error):
            pass
    return out


def pick(data):
    found = images(data)
    if not found:
        raise SystemExit("nk1_extract: no CE image in the dump")
    return max(found, key=lambda t: t[1].hdr["nummods"])


def selftest():
    # two fake images: a boot loader (1 module) and the kernel (3 modules)
    def fake(nummods, length, va):
        blob = bytearray(b"\xff" * STEP)
        hdr_off = 0x100
        struct.pack_into("<4sII", blob, 0x40, b"ECEC", va + hdr_off, hdr_off)
        vals = [0x02000000, 0x02000000, va, va + length, nummods] + [0] * 12
        struct.pack_into("<17IHHIII", blob, hdr_off, *(vals + [0x1a6, 2, 0, 0, 0]))
        return blob
    data = bytes(fake(1, 0x2000, 0x8b000000) + fake(3, 0x8000, 0x88000000))
    off, rom, length = pick(data)
    assert (off, rom.hdr["nummods"], length) == (STEP, 3, 0x8000), (off, length)
    assert len(images(data)) == 2
    print("nk1_extract selftest: ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("nand", nargs="?")
    ap.add_argument("-o", "--out", default=DEFAULT_OUT)
    ap.add_argument("--sha256", default=None, help="expected SHA-256 of the cut image")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    if not a.nand:
        ap.error("NAND dump required")
    with open(a.nand, "rb") as f:
        data = f.read()
    if a.list:
        for off, rom, length in images(data):
            print("0x%07x  VA 0x%08x  %7d bytes  %3d modules  %2d files"
                  % (off, rom.hdr["physfirst"], length, rom.hdr["nummods"], rom.hdr["numfiles"]))
        return
    off, rom, length = pick(data)
    blob = data[off:off + length]
    digest = hashlib.sha256(blob).hexdigest()
    print("NK1 at 0x%x, %d bytes, %d modules, SHA-256 %s%s"
          % (off, length, rom.hdr["nummods"], digest,
             " (the committed image)" if digest == KNOWN_SHA256 else ""))
    if a.sha256 and digest != a.sha256.lower():
        raise SystemExit("nk1_extract: SHA-256 differs from --sha256")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "wb") as f:
        f.write(blob)
    print("wrote %s" % a.out)


if __name__ == "__main__":
    main()
