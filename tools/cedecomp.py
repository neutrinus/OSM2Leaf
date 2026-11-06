#!/usr/bin/env python3
"""CE ROM section decompressor metadata and M8.E1 call targets (M1.2c).

Stdlib only. This module records the nk.exe (image B, ``--image-start
0x3e00200``) decompressor chain found by static RE of ``IMG256`` (SHA-256
``92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9``).

**Status.** The decompressor VAs and call chain are identified; the block
codec (LZXD-like, ``0x8d80805b`` marker, cecompress reports block type 4 / E8
framing) is not yet ported to pure Python. ``decode_section`` therefore raises
``UnsupportedDecompression`` and hands the call target to M8.E1 (emulated
execution of ``DECOMP_WRAP``/``DECOMP_SECT`` in nk.exe). See
docs/experiments/EXP-2026-11-06-M1.2c-rom-decompressor.md.

Usage:
  cedecomp.py info
  cedecomp.py --selftest
"""
from __future__ import annotations

import hashlib
import struct
import sys

# nk.exe, image B segment (IMG256), --image-start 0x3e00200, vbase 0x88000000.
NK_IMAGE_START = 0x3E00200
NK_VBASE = 0x88000000
NK_MODULE = "nk.exe"

# o32_flags & 0x2000 (IMAGE_SCN_COMPRESSED) check in the section loader:
# fn 0x880385e4 walks o32 records (stride 0x18), finds the matching rva, loads
# flags at @(20,r8), ANDs with 0x2000 (mov #0x20,r2; shll8 r2) at 0x88038666.
LOADER_FN = 0x880385E4
LOADER_FLAG_TEST = 0x88038666
LOADER_COMPRESSED_CALL = 0x88038698  # calls DECOMP_WRAP(dataptr, psize, dest, vsize)

# Decompressor chain (all in nk.exe .text, uncompressed, sec0 realaddr
# 0x88001000, file 0x03e01200 in IMG256):
DECOMP_WRAP = 0x88037590     # wrapper: (r4=src, r5=psize, r6=dest, r7=vsize) -> r0
DECOMP_SECT = 0x88037464     # section framing: parses form 1/2 header, loops blocks
DECOMP_BLK = 0x8803A384      # per-block LZXD-like decompressor (0x8d80805b blocks)
DECOMP_ALLOC = 0x88034D94    # called before wrap with vsize (buffer setup)

# Prototypes (SH-4 calling convention: r4-r7 args, r0 return). Derived from
# call sites; parameter names are interpretive (OBSERVED roles, not symbols).
PROTOTYPES = {
    "LOADER_FN":   "fn 0x880385e4(r4=?, r5=module/obj, r6=rva_or_idx, r7=...) "
                   "-> section info; tests o32 flags & 0x2000 at 0x88038666",
    "DECOMP_WRAP": "int 0x88037590(void *src, unsigned psize, void *dest, "
                   "unsigned vsize) -> handle/pointer (r0); locks, calls DECOMP_SECT",
    "DECOMP_SECT": "int 0x88037464(void *src, unsigned psize, void *dest_ctx, "
                   "unsigned vsize) -> decompressed size/status; parses CE section "
                   "framing (form 1 22-byte header / form 2 table) and calls DECOMP_BLK",
    "DECOMP_BLK":  "int 0x8803a384(state/frame args from DECOMP_SECT) -> status; "
                   "decompresses one 0x8d80805b LZXD-like block (block type 4 in "
                   "cecompress terms, E8 framing observed)",
}

# Call sites recorded (positive controls for the chain).
CALL_SITES = {
    "DECOMP_WRAP": [0x880260D2, 0x88026CDC, 0x88038694, 0x880390D2, 0x88039112],
    "DECOMP_SECT": [0x880375DE, 0x88037BEC],
}

IMG256_SHA256 = "92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9"

EXP49_SECTIONS = [
    {"module": "NaviMapCC.dll", "rva": 0x13000, "psize": 0x2C6, "vsize": 0x5B8,
     "ulen_form1": 0x484, "file_off": 0x01580CE0},
    {"module": "NaviMapCC.dll", "rva": 0x14000, "psize": 0x68C, "vsize": 0xCC0,
     "ulen_form1": 0xCC0, "file_off": 0x015ACA7C},
]


class UnsupportedDecompression(Exception):
    """Block codec not ported; use M8.E1 call target."""

    def __init__(self, reason, call_target=DECOMP_WRAP):
        super().__init__(reason)
        self.call_target = call_target
        self.reason = reason


def info():
    return {
        "nk_image_start": NK_IMAGE_START,
        "nk_module": NK_MODULE,
        "loader_flag_test_va": LOADER_FLAG_TEST,
        "decompressor_chain": {
            "wrap": DECOMP_WRAP,
            "sect": DECOMP_SECT,
            "blk": DECOMP_BLK,
        },
        "prototypes": PROTOTYPES,
        "img256_sha256": IMG256_SHA256,
        "status": "VAs/prototypes recorded; block codec unported -> M8.E1 call target",
    }


def decode_section(stored, vsize, ulen=None):
    """Decode an IMAGE_SCN_COMPRESSED section (form 1/2 framing + LZXD blocks).

    ``stored`` is the raw o32 psize bytes (including comphdr). Returns decoded
    bytes of length ``ulen`` (form 1 uncompressed_len) or ``vsize``. Raises
    ``UnsupportedDecompression`` until the block codec is ported; callers should
    use the M8.E1 call target ``DECOMP_WRAP``/``DECOMP_SECT`` on nk.exe.
    """
    if len(stored) < 22:
        raise UnsupportedDecompression("stored section too short for comphdr")
    # Form 1/2 framing is parsed by cerom.comphdr/classify_comphdr; the block
    # payload starts at a marker 0x8d80805b. cecompress LZX reports
    # "unknown block type 4 / E8" on the real payloads, so pure-Python decode
    # is not available here.
    marker = b"\x5b\x80\x80\x8d"
    if marker not in stored:
        raise UnsupportedDecompression(
            "no 0x8d80805b LZXD marker found; unknown framing/codec",
            call_target=DECOMP_SECT,
        )
    raise UnsupportedDecompression(
        "LZXD block codec (block type 4 / CE variant) not ported; "
        "hand to M8.E1: call DECOMP_WRAP 0x88037590 or DECOMP_SECT 0x88037464 "
        "in nk.exe (--image-start 0x3e00200) with (src, psize, dest, vsize)",
        call_target=DECOMP_WRAP,
    )


def selftest():
    errors = 0

    def check(cond, msg):
        nonlocal errors
        if not cond:
            print("FAIL:", msg)
            errors += 1
        else:
            print("ok:", msg)

    inf = info()
    check(inf["loader_flag_test_va"] == 0x88038666, "loader flag test VA")
    check(inf["decompressor_chain"]["wrap"] == 0x88037590, "wrap VA")
    check(inf["decompressor_chain"]["sect"] == 0x88037464, "sect VA")
    check(inf["decompressor_chain"]["blk"] == 0x8803A384, "blk VA")
    check(DECOMP_WRAP in CALL_SITES["DECOMP_WRAP"] or len(CALL_SITES["DECOMP_WRAP"]) == 5,
          "wrap has 5 call sites recorded")
    # marker detection / explicit M8.E1 handoff
    fake = b"\x00" * 22 + b"\x5b\x80\x80\x8d" + b"\x00" * 32
    try:
        decode_section(fake, 0x100, 0x80)
        check(False, "decode_section should raise on unported codec")
    except UnsupportedDecompression as e:
        check(e.call_target == DECOMP_WRAP, "handoff names DECOMP_WRAP")
        check("M8.E1" in str(e), "handoff mentions M8.E1")
    # no-marker path
    try:
        decode_section(b"\x00" * 40, 0x100)
        check(False, "decode_section should raise without marker")
    except UnsupportedDecompression as e:
        check(e.call_target == DECOMP_SECT, "no-marker handoff")
    # short input
    try:
        decode_section(b"\x00" * 10, 0x100)
        check(False, "short input raises")
    except UnsupportedDecompression:
        check(True, "short input rejected")

    if errors:
        print("cedecomp selftest: %d FAILED" % errors)
        return 1
    print("cedecomp selftest: all ok")
    return 0


def main():
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    if len(sys.argv) < 2 or sys.argv[1] == "info":
        inf = info()
        for k, v in inf.items():
            print("%s: %s" % (k, v))
        return
    print(__doc__)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
