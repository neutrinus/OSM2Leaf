#!/usr/bin/env python3
"""Write the IPL patch that joins ROM image A to the running kernel on ``-M ze0``.

The SD card holds three Windows CE ROM images (C-700): A at file ``0x200200``
(149 modules: Navi.exe, AuiApp.exe, the ``*CC.dll`` screens, no ``nk.exe``),
and the kernels B (``0x3e00200``) and C (``0x5200200``).  ``-M ze0`` loads B
and A into RAM, but the kernel never looks at A: OEMInit prints ``Rom chain
NOT found`` and every application ``CreateProcessW`` fails with LastError 2
(EXP-2026-11-22-M8.C1d-multi-xip).  On a unit something before the kernel
(the IPL, not on the card) has to tell it where A is.  This tool computes
the bytes that do that; ``-M ze0,ipl-patch=FILE`` (``ze0-0012``) writes them
into the loaded images before the CPU starts.  No byte on the card changes.

What the patch holds (each line is ``PHYS HEXBYTES  # why``):

1. An ``XIPCHAIN_INFO`` block (count + 0x290-byte ``XIPCHAIN_ENTRY`` per
   region, flag ``ROMXIP_OK_TO_LOAD``) for kernel + A at ``--chain-at``.
2. The kernel's chain pointer (a fixup variable in nk.exe ``.data``, value
   ``0xffffffff`` on the card) set to that block, in the ``.data`` template
   the kernel copies at start.  The variable is found from the code that
   prints ``Looking for rom chain``.
3. The kernel ROMHDR ``ulRAMEnd`` lowered below A (to the start of the
   opening-image buffer just below A when the next fixup pair says so), so
   the kernel does not hand A's pages out as free RAM.
4. A's ROMHDR ``dllfirst`` low half set to ``dlllast`` so the per-process
   DLL data reservation skips A (A and B were not built as one multi-region
   image; their DLL windows overlap).
5. Both TOCs compacted: A loses the modules the kernel already has (the
   kernel copy wins) and the modules whose sections overlap a kernel module;
   the kernel loses its updater-only modules (``BT_FW.dll``, ``*UpdateCC.dll``)
   that overlap A's application DLLs.
6. ``--prefer-app NAMES`` (M8.C1g) reverses rule 5 for the named modules:
   the kernel copy is dropped and A's copy kept even where A's DLL data
   window overlaps kernel drivers (each process maps DLL data on its own;
   the drivers live in device.exe, the AUI DLLs in AuiApp.exe).  The kernel
   image B is the updater build, so its ``auiapp.exe``/``auirtdll.dll`` do
   not know A's screens; ``--prefer-app auiapp.exe,auirtdll.dll`` runs A's.
7. ``--stub-dlls hcx`` (M8.C1h) appends stub modules for ``HCXLog.dll`` and
   ``HCXMemory.dll`` (unit flash, not on the card) to image A's TOC; see
   ``ze0_stubdll.py``.

Usage::

    ze0_ipl.py patch archive/head256.img -o ipl.txt [--kernel-off 0x3e00200]
                     [--prefer-app auiapp.exe,auirtdll.dll] [--stub-dlls hcx]
    ze0_ipl.py plan  archive/head256.img            # what would be dropped
    ze0_ipl.py --selftest
"""
import argparse
import mmap
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cerom import CERom, ROMHDR_SIZE, TOC_SIZE, FILES_SIZE  # noqa: E402

XIP_ENTRY_LEN = 0x290
ROMXIP_OK_TO_LOAD = 1
DEFAULT_CHAIN_AT = 0x0e6f0000
CHAIN_MSG = "Looking for rom chain"
KERNEL_DROPPABLE_EXACT = {"bt_fw.dll", "updatemngcc.dll", "monitoringcc.dll"}
KERNEL_DROPPABLE_SUFFIX = "updatecc.dll"
PHYS_MASK = 0x1fffffff


def phys(va):
    return va & PHYS_MASK


def kernel_droppable(name):
    n = name.lower()
    return n in KERNEL_DROPPABLE_EXACT or n.endswith(KERNEL_DROPPABLE_SUFFIX)


def dll_ranges(rom, mod):
    """Section windows of a module in the shared DLL space (>= 0x01000000)."""
    out = []
    try:
        for s in rom.o32(mod):
            if s["realaddr"] >= 0x01000000 and s["vsize"]:
                out.append((s["realaddr"], s["realaddr"] + s["vsize"]))
    except (struct.error, TypeError, ValueError):
        pass
    return out


def overlaps(ra, rb):
    return any(a0 < b1 and b0 < a1 for a0, a1 in ra for b0, b1 in rb)


def plan(kern, app, prefer=()):
    """Decide which TOC entries stay.  Returns (keep_kernel, keep_app, notes).

    ``prefer``: lower-case module names whose image A copy replaces the
    kernel's (rule 6 of the module docstring)."""
    prefer = {n.lower() for n in prefer}
    allk = list(kern.modules())
    amods = list(app.modules())
    drop_k = {m["index"]: "replaced by image A's copy (--prefer-app)" for m in allk
              if m["name"].lower() in prefer}
    kmods = [m for m in allk if m["index"] not in drop_k]
    knames = {m["name"].lower() for m in kmods}
    kr = {m["index"]: dll_ranges(kern, m) for m in kmods}
    drop_a = {}
    for m in amods:
        if m["name"].lower() in knames:
            drop_a[m["index"]] = "duplicate of the kernel image's module"
            continue
        ar = dll_ranges(app, m)
        if not ar or m["name"].lower() in prefer:
            continue
        for k in kmods:
            if not overlaps(ar, kr[k["index"]]):
                continue
            if kernel_droppable(k["name"]):
                drop_k.setdefault(k["index"], "updater-only, overlaps " + m["name"])
            else:
                drop_a[m["index"]] = "overlaps kernel module " + k["name"]
                break
    keep_k = [m for m in allk if m["index"] not in drop_k]
    keep_a = [m for m in amods if m["index"] not in drop_a]
    notes = ([("kernel", allk[i]["name"], why) for i, why in sorted(drop_k.items())] +
             [("app", amods[i]["name"], why) for i, why in sorted(drop_a.items())])
    return keep_k, keep_a, notes


def toc_bytes(rom, keep, extra=()):
    """New TOC (kept entries, then ``extra`` entries) and the unchanged FILES."""
    base = rom.hdr_off + ROMHDR_SIZE
    out = b"".join(rom.d[base + TOC_SIZE * m["index"]: base + TOC_SIZE * (m["index"] + 1)]
                   for m in keep)
    out += b"".join(extra)
    fstart = base + TOC_SIZE * rom.hdr["nummods"]
    out += rom.d[fstart: fstart + FILES_SIZE * rom.hdr["numfiles"]]
    return out


def find_chain_var(kern):
    """VA of the XIP-chain pointer fixup: first .data literal after the message."""
    nk = kern.module("nk.exe")
    sec = next(s for s in kern.o32(nk) if s["flags"] & 0x20)
    code_off = kern.va2file(sec["realaddr"])
    code = kern.d[code_off: code_off + sec["psize"]]
    msg = CHAIN_MSG.encode("utf-16-le")
    lo = kern.hdr["ulRAMStart"]
    copy_src, copy_dst, copy_len = copy_entry(kern)
    pos = kern.d.find(msg, kern.start, kern.start + (kern.hdr["physlast"] - kern.hdr["physfirst"]))
    if pos < 0:
        raise SystemExit("ze0_ipl: '%s' not in the kernel image" % CHAIN_MSG)
    msg_va = kern.file2va(pos)
    base = sec["realaddr"]
    hits = []
    for k in range(0, len(code) - 1, 2):
        op = struct.unpack_from("<H", code, k)[0]
        if op >> 12 != 0xd:
            continue
        pc = base + k
        ea = (pc & ~3) + 4 + (op & 0xff) * 4
        if not base <= ea < base + len(code) - 3:
            continue
        if struct.unpack_from("<I", code, ea - base)[0] == msg_va:
            hits.append(k)
    for k in hits:
        for j in range(k + 2, min(k + 40, len(code) - 1), 2):
            op = struct.unpack_from("<H", code, j)[0]
            if op >> 12 != 0xd:
                continue
            pc = base + j
            ea = (pc & ~3) + 4 + (op & 0xff) * 4
            v = struct.unpack_from("<I", code, ea - base)[0]
            if copy_dst <= v < copy_dst + copy_len and v >= lo:
                return v, msg_va
    raise SystemExit("ze0_ipl: no chain-pointer literal after the '%s' reference" % CHAIN_MSG)


def copy_entry(kern):
    """The ROMHDR copy entry that initialises kernel .data (the first one)."""
    off = kern.va2file(kern.hdr["ulCopyOffset"])
    src, dst, clen, dlen = struct.unpack_from("<4I", kern.d, off)
    return src, dst, clen


def template_va(kern, var):
    src, dst, clen = copy_entry(kern)
    if not dst <= var < dst + clen:
        raise SystemExit("ze0_ipl: 0x%08x is outside the initialised .data copy" % var)
    return src + (var - dst)


def u32_at_va(rom, va):
    return struct.unpack_from("<I", rom.d, rom.va2file(va))[0]


def xip_entry(addr, length, order, name):
    e = struct.pack("<IIIHHI", addr, length, length, order, ROMXIP_OK_TO_LOAD, 0)
    e += name.encode("ascii").ljust(32, b"\0")
    return e.ljust(XIP_ENTRY_LEN, b"\0")


def build(data, kernel_off, app_off, chain_at, prefer=(), stubs=None):
    kern = CERom(data, kernel_off)
    app = CERom(data, app_off)
    kh, ah = kern.hdr, app.hdr
    lines = []

    def poke(va_or_phys, blob, why):
        lines.append((phys(va_or_phys), bytes(blob), why))

    var, msg_va = find_chain_var(kern)
    tva = template_va(kern, var)
    cur = u32_at_va(kern, tva)
    if cur != 0xffffffff:
        raise SystemExit("ze0_ipl: chain pointer template 0x%08x holds 0x%08x, expected "
                         "0xffffffff" % (tva, cur))
    # opening-image buffer: the fixup pair two words after the chain pointer
    buf_addr = u32_at_va(kern, tva + 8)
    buf_len = u32_at_va(kern, tva + 12)
    ram_end = ah["physfirst"]
    if buf_addr + buf_len == ah["physfirst"]:
        ram_end = buf_addr
    chain = [xip_entry(kh["physfirst"], kh["physlast"] - kh["physfirst"], 0, "NK"),
             xip_entry(ah["physfirst"], ah["physlast"] - ah["physfirst"], 1, "NK2")]
    poke(chain_at, struct.pack("<I", len(chain)) + b"".join(chain),
         "XIPCHAIN_INFO: kernel image, then image A")
    poke(tva, struct.pack("<I", 0x80000000 | chain_at),
         "kernel .data template: XIP chain pointer (var 0x%08x)" % var)
    if kh["ulRAMEnd"] > ram_end:
        poke(kern.ptoc + 0x1c, struct.pack("<I", ram_end),
             "kernel ROMHDR ulRAMEnd 0x%08x -> 0x%08x (below image A)" % (kh["ulRAMEnd"], ram_end))
    a_dllfirst = (ah["dllfirst"] & 0xffff0000) | (ah["dlllast"] >> 16)
    poke(app.ptoc, struct.pack("<I", a_dllfirst),
         "image A ROMHDR dllfirst 0x%08x -> 0x%08x (no DLL data reservation)" % (ah["dllfirst"], a_dllfirst))
    keep_k, keep_a, notes = plan(kern, app, prefer)
    extra = []
    if stubs:
        import ze0_stubdll
        s_lines, extra, s_notes = ze0_stubdll.build(kern, app, keep_k, keep_a, stubs)
        for va, blob, why in s_lines:
            poke(va, blob, why)
        notes += [("stub", n, "") for n in s_notes]
        if len(keep_a) + len(extra) > ah["nummods"]:
            raise SystemExit("ze0_ipl: image A TOC has no room for the stub modules")
    if len(keep_k) != kh["nummods"]:
        poke(kern.ptoc + 0x54, toc_bytes(kern, keep_k), "kernel TOC, %d of %d modules + FILES"
             % (len(keep_k), kh["nummods"]))
        poke(kern.ptoc + 0x10, struct.pack("<I", len(keep_k)), "kernel ROMHDR nummods")
    poke(app.ptoc + 0x54, toc_bytes(app, keep_a, extra),
         "image A TOC, %d of %d modules%s + FILES"
         % (len(keep_a), ah["nummods"], " + %d stubs" % len(extra) if extra else ""))
    poke(app.ptoc + 0x10, struct.pack("<I", len(keep_a) + len(extra)), "image A ROMHDR nummods")
    info = dict(chain_var=var, template=tva, ram_end=ram_end, chain_at=chain_at,
                kernel_mods=(len(keep_k), kh["nummods"]), app_mods=(len(keep_a), ah["nummods"]))
    return lines, notes, info


def render(lines):
    out = ["# ze0 IPL patch (tools/ze0_ipl.py): PHYS HEXBYTES  # why"]
    for p, blob, why in lines:
        out.append("0x%08x %s  # %s" % (p, blob.hex(), why))
    return "\n".join(out) + "\n"


def open_image(path):
    f = open(path, "rb")
    return mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)


def selftest():
    e = xip_entry(0x8cae1000, 0x10, 1, "NK2")
    assert len(e) == XIP_ENTRY_LEN and e[14] == 1 and e[16:20] == b"\0\0\0\0" and e[20:23] == b"NK2"
    assert kernel_droppable("BT_FW.dll") and kernel_droppable("PrgUpdateCC.dll")
    assert not kernel_droppable("gdisubdrv.dll")
    assert overlaps([(0, 10)], [(9, 20)]) and not overlaps([(0, 10)], [(10, 20)])
    assert phys(0x8e6f0000) == 0x0e6f0000

    class Fake:
        def __init__(self, mods):
            self.mods = mods

        def modules(self):
            return [dict(index=i, name=n) for i, (n, _) in enumerate(self.mods)]

        def o32(self, m):
            return [dict(realaddr=a, vsize=b - a) for a, b in self.mods[m["index"]][1]]
    k = Fake([("auiapp.exe", []), ("GPIO.dll", [(0x01f46000, 0x01f46158)])])
    a = Fake([("auiapp.exe", []), ("auirtdll.dll", [(0x01eb3000, 0x01f493b0)])])
    kk, ka, _ = plan(k, a)
    assert [m["name"] for m in kk] == ["auiapp.exe", "GPIO.dll"] and ka == []
    kk, ka, _ = plan(k, a, ["auiapp.exe", "auirtdll.dll"])
    assert [m["name"] for m in kk] == ["GPIO.dll"]
    assert [m["name"] for m in ka] == ["auiapp.exe", "auirtdll.dll"]
    txt = render([(0x100, b"\x01\x02", "x")])
    assert "0x00000100 0102  # x" in txt
    print("ze0_ipl selftest: ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("patch", "plan"):
        p = sub.add_parser(name)
        p.add_argument("image")
        p.add_argument("--kernel-off", type=lambda s: int(s, 0), default=0x3e00200)
        p.add_argument("--app-off", type=lambda s: int(s, 0), default=0x200200)
        p.add_argument("--chain-at", type=lambda s: int(s, 0), default=DEFAULT_CHAIN_AT)
        p.add_argument("--prefer-app", default="",
                       help="comma list: keep image A's copy of these modules (M8.C1g)")
        p.add_argument("--stub-dlls", default="", choices=("", "hcx"),
                       help="add stub modules for unit-flash DLLs (M8.C1h, ze0_stubdll.py)")
        if name == "patch":
            p.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    if not a.cmd:
        ap.error("command required")
    data = open_image(a.image)
    prefer = [n.strip() for n in a.prefer_app.split(",") if n.strip()]
    lines, notes, info = build(data, a.kernel_off, a.app_off, a.chain_at, prefer,
                              a.stub_dlls or None)
    print("chain pointer var 0x%08x (template 0x%08x), XIPCHAIN at phys 0x%08x, RAM end 0x%08x"
          % (info["chain_var"], info["template"], info["chain_at"], info["ram_end"]))
    print("kernel modules kept %d/%d, image A modules kept %d/%d"
          % (info["kernel_mods"] + info["app_mods"]))
    if a.cmd == "plan":
        for where, name, why in notes:
            print("drop %-6s %-26s %s" % (where, name, why))
        return
    with open(a.out, "w") as f:
        f.write(render(lines))
    print("wrote %s (%d lines)" % (a.out, len(lines)))


if __name__ == "__main__":
    main()
