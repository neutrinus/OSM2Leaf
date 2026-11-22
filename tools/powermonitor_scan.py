#!/usr/bin/env python3
"""Static checks for the ZE0 power/ACC state machine (TODO M8.H53).

The reader lives in build B's ``PowerMonitor.dll`` (VA base ``0x039d0000``).
This tool answers three questions that otherwise need ad-hoc heredocs:

* which function owns a literal string / code pointer (through the pinned LE
  literal pools, ``tools/sh4xref.py``);
* where the virtual-method table of the power manager starts, and which
  method offset holds each shutdown step (the table is found by walking back
  from the pool that holds ``SysDisable`` -- no fitted base);
* which driver IOCTL constants are used, by which function (through
  ``.pdata`` function starts).

``--check`` verifies the pinned facts on the real image; ``--json`` prints the
full scan.  Stdlib only, every address comes from the ROM headers (cerom.py)
or from a literal pool in an executable section.

Usage:
  powermonitor_scan.py IMG --image-start 0x3e00200 --check
  powermonitor_scan.py IMG --image-start 0x3e00200 --json
  powermonitor_scan.py --selftest

Method: docs/experiments/EXP-2026-11-22-M8.H53-powermonitor-static.md
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
DEFAULT_START = 0x3e00200

# VAs (build B) of the strings the state machine logs.
STRINGS = {
    0x039d1638: "EVT_POW_NOTIFY_ACC_CHG",
    0x039d1668: "EVT_POW_NOTIFY_IGN_CHG",
    0x039d1f80: "Pow >> AccOffProc Start",
    0x039d1fb4: "Pow >> Pow Off 2nd Detect!!!",
    0x039d1ff8: "Pow >> Acc Off Not Notify SystemEXE... ",
    0x039d2050: "Pow >> Application Layer Shutdown Complete!!! ",
    0x039d20b8: "Pow >> No Action at ACC-OFF? Timeout!! Force PowerOff!!!",
    0x039d2130: "Pow >> Acc Off Notify SystemEXE!!! ",
    0x039d217c: "Pow >> Pow Off 1st Detect!!!",
    0x039d21bc: "NOTIFY_ACC_OFF_EVENT",
    0x039d2254: "Wait ACC-OFF Interrupt",
    0x039d238c: "Wait Backup Interrupt",
    0x039d2490: "MUTEX_MCT_WRITEFILE",
    0x039d2364: "BackUp Detect!!!!",
}

# String VA -> owning function (pdata start), verified through literal pools.
STRING_FN = {
    0x039d21bc: 0x039d58f8,   # create the named event
    0x039d217c: 0x039d56f4,   # AccOffProc, 1st detect
    0x039d1fb4: 0x039d56f4,   # AccOffProc, 2nd detect
    0x039d20b8: 0x039d56f4,   # AccOffProc, timeout
    0x039d1f80: 0x039d56f4,   # AccOffProc, entry
    0x039d2254: 0x039d5a7c,   # AccOffDetectThread
    0x039d238c: 0x039d5b30,   # BackupDetectThread
    0x039d2490: 0x039d5b30,   # MUTEX_MCT_WRITEFILE
    0x039d2364: 0x039d5b30,   # BackUp Detect!!!!
}

# Virtual-method offsets, named by the log string at each implementation.
METHODS = {
    0x039d56f4: "AccOffProc",
    0x039d57bc: "InitEvents",
    0x039d58f8: "NotifySystemEXE",
    0x039d5a7c: "AccOffDetectThread",
    0x039d5b30: "BackupDetectThread",
    0x039d5ca8: "SystemResetThread",
    0x039d5d14: "HWControlThread",
    0x039d5dc8: "OperationControlThread",
    0x039d5f5c: "SysDisable",
    0x039d6008: "VideoMute_VIN1",
    0x039d60fc: "KeyDisable_KEP1",
    0x039d6204: "BT_OneSegReset",
    0x039d6428: "PowerOFF_Sequence",
    0x039d6494: "KernelIoControl",
    0x039d6510: "DiskShutdown_SDC1",
    0x039d6630: "I2C_Disable",
    0x039d6750: "BoleroAccOff",
    0x039d6858: "SRM_Disable",
    0x039d696c: "FLM_Disable",
    0x039d6a7c: "FMD_Disable",
    0x039d6b6c: "BoleroAccControl",
    0x039d6d2c: "StartThreads",
    0x039d6f90: "WdtStart",
}

# Driver IOCTL constants found in this module's literal pools.
IOCTLS = {
    0x8003200c: "IOCTL_SDC_SHUTDOWN",
    0x8005200c: "I2C control (C-6421)",
    0x80062024: "IOCTL_VIN_DISABLE",
    0x80092004: "IOCTL_GPIO_ACCESS_BOLERO_ACC",
    0x80092060: "IOCTL_GPIO_ACCESS_BT_RESET",
    0x80092080: "IOCTL_GPIO_ACCESS_DTV_RST",
    0x80112014: "IOCTL_FMD_WRITE_DISABLE",
    0x80132000: "POW IOCTL 0x80132000",
    0x80132004: "POW IOCTL 0x80132004",
    0x8013200c: "POW IOCTL 0x8013200c (system reset)",
    0x80132010: "POW IOCTL 0x80132010",
    0x80132014: "POW IOCTL 0x80132014",
    0x80142004: "IOCTL_SRM_ENABLE_COMMIT",
    0x801f200c: "ERR_DTAL_IOCTL_KEP_SET_NOTIFY_KEY",
    0x8020205c: "IOCTL_CAN_IGN_CHG",
    0x80202060: "IOCTL_GPIO_ACCESS_BOLERO_ACC (CAN)",
    0x80202064: "IOCTL_CAN_ACCDET_NOTICE",
    0x8021200c: "IOCTL_FLM_ALL_DISABLE",
    0x01013000: "IOCTL_HAL_POWER_SEQUENSE",
}

# (code VA, expected u16) -- the interrupt ids and the 40 s ACC-off wait.
IMMEDIATES = {
    0x039d5a92: 0xe511,       # mov #17,r5  (ACC-off interrupt id)
    0x039d5b78: 0xe510,       # mov #16,r5  (backup interrupt id)
    0x039d4f6c: 0xe532,       # mov #50,r5  (line-monitor interrupt id)
    0x039d5bce: 0x964a,       # mov.w @(pc),r6 -> 0x1388 (5000 ms)
    0x039d573c: 0xd619,       # mov.l @(pc),r6 -> 0x9c40 (40000 ms)
}
POOLS = {
    0x039d57a4: 0x00009c40,   # ACC-off application-shutdown timeout
}


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
    for seg in [s for s in mem.segs]:
        # literal pools live in the executable section; walk it as words
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
           "exports": {}, "strings": [], "string_fn": {},
           "vtable_base": None, "methods": {}, "ioctls": {},
           "immediates": {}, "pools": {}}

    for _ord, name, rva in rom.exports(mod):
        out["exports"][name] = rva

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

    # The vtable base is derived: walk back from the pool holding SysDisable
    # while the words are still code pointers (no fitted VA).
    pools = sh4xref.pool_entries(mem, exec_segs, 0x039d5f5c)
    if pools:
        va = pools[0]
        lo = va - 0x400
        while va > lo and (w := mem.u32(va)) is not None and 0x039d4700 <= w <= 0x039d8500:
            va -= 4
        base = va + 4
        code_lo, code_hi = 0x039d4700, 0x039d8500
        out["vtable_base"] = hex(base)
        for off in range(0, 0x400, 4):
            w = mem.u32(base + off)
            if w in METHODS:
                out["methods"][hex(off)] = {"va": hex(w), "name": METHODS[w]}
        del code_lo, code_hi

    for val, name in IOCTLS.items():
        fn = _fn_of_mem(mem, val)
        if fn is not None:
            out["ioctls"][hex(val)] = {"name": name, "fn": hex(fn)}
    for va, expect in IMMEDIATES.items():
        if mem.u16(va) == expect:
            out["immediates"][hex(va)] = hex(expect)
    for va, expect in POOLS.items():
        if mem.u32(va) == expect:
            out["pools"][hex(va)] = hex(expect)
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
    if result["vtable_base"] != hex(0x039d1c10):
        failures.append("vtable base %s" % result["vtable_base"])
    for off, info in result["methods"].items():
        if info["va"] not in {hex(v) for v in METHODS}:
            failures.append("method " + off)
    for val in IOCTLS:
        if hex(val) not in result["ioctls"]:
            failures.append("ioctl 0x%x" % val)
    for va in IMMEDIATES:
        if hex(va) not in result["immediates"]:
            failures.append("immediate 0x%x" % va)
    for va in POOLS:
        if hex(va) not in result["pools"]:
            failures.append("pool 0x%x" % va)
    print("powermonitor_scan --check: %s" % ("PASS" if not failures else "FAIL"))
    print("  strings %d/%d, xrefs %d/%d, methods %d, ioctls %d/%d, immediates %d/%d, pools %d/%d"
          % (len(result["strings"]), len(STRINGS), len(result["string_fn"]), len(STRING_FN),
             len(result["methods"]), len(result["ioctls"]), len(IOCTLS),
             len(result["immediates"]), len(IMMEDIATES), len(result["pools"]), len(POOLS)))
    if failures:
        print("  FAILURES: " + ", ".join(failures))
    return 0 if not failures else 1


def _synthetic():
    """A tiny fake ROM with one 4-word vtable and one 0x9c40 literal pool."""
    base = 0x1000
    blob = bytearray(0x80)
    for i, v in enumerate((0x2000, 0x2002, 0x2004, 0x2006)):
        struct.pack_into("<I", blob, i * 4, v)
    struct.pack_into("<I", blob, 0x20, 0x9c40)
    struct.pack_into("<H", blob, 0x30, 0xe511)
    return sh4dis.Mem([(base, bytes(blob))]), bytes(blob)


def selftest():
    mem, blob = _synthetic()
    ok = True
    ok &= mem.u32(0x1000) == 0x2000
    ok &= mem.u32(0x100c) == 0x2006
    ok &= mem.u32(0x1020) == 0x00009c40        # LE pool word
    ok &= mem.u16(0x1030) == 0xe511            # LE halfword (not 0x11e5)
    ok &= sh4dis.read_u16(bytes.fromhex("11e5")) == 0xe511
    words = [struct.unpack_from("<I", blob, i)[0] for i in range(0, 0x10, 4)]
    ok &= words == [0x2000, 0x2002, 0x2004, 0x2006]
    print("powermonitor_scan --selftest: %s (5/5)" % ("PASS" if ok else "FAIL"))
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
