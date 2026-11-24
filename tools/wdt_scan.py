#!/usr/bin/env python3
"""Static checks for the watchdog and reset paths of TODO M8.H67.

The reader of interest is build B's ``PowerMonitor.dll`` (VA base
``0x039d0000``), whose ``C.WdtMonitor`` class owns the WDT start/stop/clear
events, and build B's ``nk.exe`` (image B start ``0x3e00200``).  This tool
answers three questions that otherwise need ad-hoc heredocs:

* which code owns each WDT/Reset log string (literal pool -> ``mov.l`` loads,
  through ``tools/sh4xref.py`` and the pinned ``.pdata`` functions);
* which KernelIoControl IOCTLs the reset path uses, and at which function;
* what the derived WDT event period and the vtable method offsets are.

No signature is fitted: every VA comes from ``tools/cerom.py`` section
offsets, a literal pool in an executable section, or the derived vtable
(walking back from the pinned ``SysDisable`` pool, as M8.H53 does).
All reads are little-endian SH-4 (``tools/sh4dis.read_u16``).  Stdlib only.

Usage:
  wdt_scan.py IMG --image-start 0x3e00200 --check
  wdt_scan.py IMG --image-start 0x3e00200 --json
  wdt_scan.py --selftest

Method: docs/experiments/EXP-2026-11-24-M8.H67-watchdog-reset.md
"""
import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cerom  # noqa: E402
import pdata  # noqa: E402
import sh4dis  # noqa: E402
import sh4xref  # noqa: E402

MODULE = "PowerMonitor.dll"
DEFAULT_START = 0x3E00200

# VAs (build B) of the strings the WDT / reset path logs.  Keys are the full
# string start VAs (decoded UTF-16LE, little-endian), quoted from EXP M8.H67.
STRINGS = {
    0x039D3F04: "Failed to Wait For WDT Event[%d];",
    0x039D3F78: "Failed to Create WDT Clear Thread;",
    0x039D3FF0: "Failed to Create WDT Stop Event;",
    0x039D4038: "EVENT_WDT_STOP",
    0x039D4080: "Failed to Create WDT Start Event;",
    0x039D40C8: "EVENT_WDT_START",
    0x039D3EC8: "CWdtMonitor::WdtClearThread()",
    0x039D24B8: "Power Monitor Driver SystemResetThread Exception",
    0x039D3924: "System Reset Thread Not Set Priority",
}

# String VA -> owning function, derived from literal-pool loads.  Entries are
# only included where sh4xref actually resolved a literal pool to a .pdata
# function; the four "Failed to Create/Wait ..." strings are referenced
# indirectly through C++ objects and have no direct literal pool (documented
# as UNKNOWN in the EXP, not pinned here).
STRING_FN = {
    0x039D4038: 0x039D71D8,   # C.WdtMonitor::Init -> CreateEvent(EVENT_WDT_STOP)
    0x039D40C8: 0x039D71D8,   # same function -> CreateEvent(EVENT_WDT_START)
    0x039D3EC8: 0x039D706C,   # WdtClearThread logs "Failed to Wait For WDT Event"
    0x039D24B8: 0x039D5CA8,   # SystemResetThread error string
}

# Virtual-method offsets of the PowerMonitor manager (vtable 0x039d1c10,
# derived by walking back from the SysDisable pool, M8.H53 convention).
# Positive control: vt+0x344 = AccOffProc (0x039d56f4) is shared with H53.
VTABLE_OFFSETS = {
    0x000: (0x039D6F90, "WdtStart"),
    0x2F8: (0x039D55E8, "Init"),
    0x304: (0x039D5F54, "IOCTL_80132004_handler"),
    0x308: (0x039D5F5C, "SysDisable"),
    0x30C: (0x039D6008, "VideoMute_VIN1"),
    0x310: (0x039D60FC, "KeyDisable_KEP1"),
    0x314: (0x039D6204, "BT_OneSegReset"),
    0x320: (0x039D6428, "PowerOFF_Sequence"),
    0x324: (0x039D6494, "KernelIoControl_wrapper"),
    0x344: (0x039D56F4, "AccOffProc"),
    0x348: (0x039D57BC, "InitEvents"),
    0x34C: (0x039D58F8, "NotifySystemEXE"),
    0x350: (0x039D6D2C, "StartThreads"),
    0x354: (0x039D6C80, "IOCTL_80132010_handler"),
    0x358: (0x039D6CB4, "IOCTL_80132014_handler"),
}

# KernelIoControl IOCTLs used on the WDT/reset paths (literal pools).
IOCTLS = {
    0x8013200C: (0x039D5E64, "POW_IOControl system reset request"),
    0x01013000: (0x039D6494, "IOCTL_HAL_POWER_SEQUENSE"),
    0x01013048: (0x039D706C, "IOCTL_HAL_*_0x01013048 (WDT monitor)"),
}

# WDT event period immediates, read as LE halfwords from the code section.
# 0x0102 is the IOCTL compared at 0x039d70de; 0x0bb8 (3000) is the wait
# timeout set by WdtClearThread at 0x039d715e; the literal pool read at
# 0x039d719c holds 0x01013048 (IOCTL passed to KernelIoControl at 0x039d70ee).
IMMEDIATES = {
    0x039D7192: 0x0102,       # mov.w @(pc) word compared at 0x039d70e0
    0x039D7194: 0x0BB8,       # mov.w @(pc) word = 3000 (wait timeout)
    0x039D7018: 0xE67D,       # mov #125,r6 at 0x039d7018 (LE halfword)
}
POOLS = {
    0x039D6500: 0x01013000,   # IOCTL_HAL_POWER_SEQUENSE
    0x039D5F3C: 0x8013200C,   # system reset request IOCTL
    0x039D719C: 0x01013048,   # IOCTL used by C.WdtMonitor::WdtClearThread
    0x039D5CF8: 0x039D24B8,   # SystemResetThread error string pool
}

# The on-chip WDT register page 0xfff80000 is a display-unit register in this
# build (C-6920), not a WDT.  The classic SH-4 WDT registers are at
# 0xffffff80/0xffffff84/0xffffff88; a census of those pages is part of the
# check (no periodic access is attributed to a WDT write outside TMU).
WDT_PAGES = (0xFFFFFF80, 0xFFFFFF84, 0xFFFFFF88, 0xFFF80000)
TMU_PAGE = 0xFFD80000


def _load(image, image_start, module=MODULE):
    with open(image, "rb") as fh:
        data = fh.read(128 << 20)
    rom = cerom.CERom(data, image_start)
    m = rom.module(module)
    exec_segs, all_segs = [], []
    for s in rom.o32(m):
        if s["flags"] & cerom.IMAGE_SCN_COMPRESSED:
            continue
        off = rom.va2file(s["dataptr"])
        blob = data[off:off + s["psize"]]
        all_segs.append((s["realaddr"], blob))
        if s["flags"] & 0x20000000:
            exec_segs.append((s["realaddr"], blob))
    mem = sh4dis.Mem(all_segs)
    pdata.attach_fn_of_from_image(mem, data, image_start, m["name"])
    return mem, exec_segs, data, rom, m


def _fn_of_mem(mem, value):
    """Enclosing pdata function of the first load of a literal holding value."""
    for seg in mem.segs:
        base, blob = seg
        for off in range(0, len(blob) - 3, 4):
            if struct.unpack_from("<I", blob, off)[0] != value:
                continue
            pool = base + off
            for load, _reg in sh4xref.loads_of(mem, pool):
                fn = mem.fn_of(load) if getattr(mem, "fn_of", None) else sh4xref.fn_start(mem, load)
                if fn is not None:
                    return fn
    return None


def scan(image, image_start):
    mem, exec_segs, data, rom, mod = _load(image, image_start)
    out = {"module": mod["name"], "image_start": image_start,
           "strings": [], "string_fn": {}, "vtable_base": None,
           "methods": {}, "ioctls": {}, "immediates": {}, "pools": {},
           "wdt_pages": {}}
    base = 0x039D1C10
    out["vtable_base"] = hex(base)

    for va, text in STRINGS.items():
        b = mem.read(va, 2 * len(text))
        if b is not None:
            try:
                out["strings"].append({"va": va, "text": b.decode("utf-16le")})
            except UnicodeDecodeError:
                pass

    for va, expect in STRING_FN.items():
        lines = sh4xref.query_to(mem, exec_segs, va, "string")
        fns = {int(x.split("fn 0x")[1].split()[0], 16)
               for x in lines if "fn 0x" in x}
        if expect in fns:
            out["string_fn"][hex(va)] = hex(expect)

    for off, (expect_va, name) in VTABLE_OFFSETS.items():
        if mem.u32(base + off) == expect_va:
            out["methods"][hex(off)] = {"va": hex(expect_va), "name": name}

    for val, (expect_fn, name) in IOCTLS.items():
        fn = _fn_of_mem(mem, val)
        if fn is not None and (expect_fn is None or fn == expect_fn):
            out["ioctls"][hex(val)] = {"name": name, "fn": hex(fn)}

    for va, expect in IMMEDIATES.items():
        if mem.u16(va) == expect:
            out["immediates"][hex(va)] = hex(expect)
    for va, expect in POOLS.items():
        if mem.u32(va) == expect:
            out["pools"][hex(va)] = hex(expect)

    # Count literal words that name each candidate WDT register page.  Words
    # are counted across the PowerMonitor code section only; the attribution
    # of 0xfff80000 to IOLIB is a separate cerom/ze0_regs check in the EXP.
    for page in WDT_PAGES:
        out["wdt_pages"][hex(page)] = 0
        for seg_base, blob in exec_segs:
            needle = struct.pack("<I", page)
            off = 0
            while True:
                i = blob.find(needle, off)
                if i < 0:
                    break
                if i % 4 == 0:
                    out["wdt_pages"][hex(page)] += 1
                off = i + 1
    return out


def check(image, image_start):
    result = scan(image, image_start)
    failures = []
    for va, text in STRINGS.items():
        if not any(s["va"] == va and s["text"] == text for s in result["strings"]):
            failures.append("string 0x%x" % va)
    for va in STRING_FN:
        if hex(va) not in result["string_fn"]:
            failures.append("xref 0x%x" % va)
    for off in VTABLE_OFFSETS:
        if hex(off) not in result["methods"]:
            failures.append("vtable +0x%x" % off)
    for val in IOCTLS:
        if hex(val) not in result["ioctls"]:
            failures.append("ioctl 0x%x" % val)
    for va in IMMEDIATES:
        if hex(va) not in result["immediates"]:
            failures.append("immediate 0x%x" % va)
    for va in POOLS:
        if hex(va) not in result["pools"]:
            failures.append("pool 0x%x" % va)
    print("wdt_scan --check: %s" % ("PASS" if not failures else "FAIL"))
    print("  strings %d/%d, xrefs %d/%d, methods %d/%d, ioctls %d/%d, "
          "immediates %d/%d, pools %d/%d"
          % (len(result["strings"]), len(STRINGS),
             len(result["string_fn"]), len(STRING_FN),
             len(result["methods"]), len(VTABLE_OFFSETS),
             len(result["ioctls"]), len(IOCTLS),
             len(result["immediates"]), len(IMMEDIATES),
             len(result["pools"]), len(POOLS)))
    print("  wdt-page words in PowerMonitor code: %s"
          % json.dumps(result["wdt_pages"], sort_keys=True))
    if failures:
        print("  FAILURES: " + ", ".join(failures))
    return 0 if not failures else 1


def selftest():
    """A tiny fake memory: LE pool words, vtable slots and a halfword."""
    ok = True
    blob = bytearray(0x80)
    struct.pack_into("<I", blob, 0x00, 0x01013000)
    struct.pack_into("<I", blob, 0x10, 0x039D6F90)
    struct.pack_into("<H", blob, 0x20, 0x0BB8)
    mem = sh4dis.Mem([(0x1000, bytes(blob))])
    ok &= mem.u32(0x1000) == 0x01013000            # LE word, not 0x00300101
    ok &= mem.u32(0x1010) == 0x039D6F90            # WdtStart vtable slot
    ok &= mem.u16(0x1020) == 0x0BB8                # LE halfword, not 0xB80B
    ok &= sh4dis.read_u16(bytes.fromhex("b80b")) == 0x0BB8
    ok &= sh4dis.read_u16(bytes.fromhex("023e")) == 0x3E02
    print("wdt_scan --selftest: %s (5/5)" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?")
    ap.add_argument("--image-start", type=lambda x: int(x, 0), default=DEFAULT_START)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.image:
        ap.error("image is required (or use --selftest)")
    if args.check:
        return check(args.image, args.image_start)
    result = scan(args.image, args.image_start)
    print(json.dumps(result, indent=1, sort_keys=True) if args.json
          else "\n".join("%s: %s" % (k, v) for k, v in sorted(result.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
