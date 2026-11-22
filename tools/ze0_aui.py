#!/usr/bin/env python3
"""IPL patch lines that let image A's AuiApp start its screens on ``-M ze0`` (M8.C1g).

With ``ze0_ipl.py patch --prefer-app auiapp.exe,auirtdll.dll`` the emulator
runs image A's AUI host instead of the kernel image's updater copy.  Three
things that the unit's own flash would provide are still missing
(EXP-2026-11-22-M8.C1g-ui-layer):

1. ``HKCU\\Software\\Microsoft\\Automotive\\AuiApp\\SkinPath``.  The kernel's
   ``user.hv`` has the key but not the value, so AUIRT stops with
   ``Only SKN file format is supported in this version.()``.
2. The COM registrations of image A's controls (``*CC.dll``,
   ``multiskin.dll``).  The kernel's ``default.hv`` lists 102 CLSID keys,
   none of them A's, so every control fails with
   ``AUI:WRN:02034302 Failed initialize control``.
3. SystemEXE waits 45 000 ms for the first AUI form and then shuts the
   system down (``CAuiMonitorCmn::ThreadProc::TIMEOUT``, ACC-off path).

The tool writes ``PHYS HEXBYTES  # why`` lines (the ``ze0_ipl.py`` format;
append them to its output) that patch image A in RAM before the CPU starts:

* a small SH-4 routine in AuiApp's ``-help`` text that copies
  ``\\windows\\ReleaseMain.skn`` into the SkinPath buffer, calls
  ``CoInitializeEx(0, 0)`` and then ``DllRegisterServer`` of every control
  DLL in a name list (``LoadLibraryW`` + ``GetProcAddressW``); the name list
  sits in the strings of AuiApp's debug thread (unused unless
  ``DebugMode`` is set);
* AuiApp's registry read of SkinPath redirected to that routine
  (``jsr @r10`` -> ``jsr @r4`` and the name pointer -> the routine);
* with ``--no-aui-timeout``, SystemEXE's 45 000 ms wait set to INFINITE.

Every address is found from the image (strings, literal pools, exports),
not hard-coded; the tool refuses if a pattern is not unique.  No byte on
the card changes; the lines only reach RAM through ``-M ze0,ipl-patch``.

Usage::

    ze0_aui.py archive/head256.img -o aui.txt [--no-aui-timeout]
               [--skins ReleaseMain.skn,Substance.skn]
    cat ipl.txt aui.txt > ipl_ui.txt
    ze0_aui.py --selftest
"""
import argparse
import mmap
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cerom import CERom  # noqa: E402
import ze0_ipl  # noqa: E402

SKIN = "\\windows\\ReleaseMain.skn"
FIRST = ["multiskin.dll", "SystemCC.dll", "AuiMonitoringCC.dll"]
AUI_TIMEOUT_MS = 45000


# ---------------------------------------------------------------- assembler
def asm(prog, base, lits):
    """Two-pass assembler for the few SH-4 forms the routine needs.

    ``prog`` items: ``("L", name)`` label, ``(word,)`` raw, ``("LDL", rn,
    lit)`` mov.l @(disp,pc),rn of literal ``lit``, ``("BT"|"BF"|"BRA",
    label)``.  ``lits``: [(name, value or callable(labels))]; literals
    follow the code, 4-aligned.
    """
    def one(labels):
        pc, out = base, []
        for ins in prog:
            if ins[0] == "L":
                labels[ins[1]] = pc
                continue
            if len(ins) == 1:
                w = ins[0]
            elif ins[0] == "LDL":
                t = labels.get(ins[2], (pc + 8) & ~3)
                d = (t - ((pc & ~3) + 4)) // 4
                if not (0 <= d < 256 and t % 4 == 0):
                    raise ValueError("literal %s out of range" % ins[2])
                w = 0xd000 | ins[1] << 8 | d
            elif ins[0] in ("BT", "BF"):
                d = (labels.get(ins[1], pc) - (pc + 4)) // 2
                if not -128 <= d < 128:
                    raise ValueError("branch out of range")
                w = (0x8900 if ins[0] == "BT" else 0x8b00) | (d & 0xff)
            elif ins[0] == "BRA":
                d = (labels.get(ins[1], pc) - (pc + 4)) // 2
                w = 0xa000 | (d & 0xfff)
            else:
                raise ValueError(ins)
            out.append(w)
            pc += 2
        if pc % 4:
            out.append(0x0009)
            pc += 2
        code = struct.pack("<%dH" % len(out), *out)
        pool = b""
        for name, _ in lits:
            labels[name] = pc + len(pool)
            pool += b"\0\0\0\0"
        return code, pool, pc
    labels = {}
    one(labels)
    code, pool, pc = one(labels)
    tail = bytearray(pool)
    extra = b""
    for name, val in lits:
        if isinstance(val, (bytes, bytearray)):
            while (pc + len(tail) + len(extra)) % 4:
                extra += b"\0"
            v = pc + len(tail) + len(extra)
            extra += bytes(val)
        else:
            v = val
        struct.pack_into("<I", tail, labels[name] - pc, v)
    return code + bytes(tail) + extra, labels


def routine(base, coinit, loadlib, getproc, names_va):
    """SkinPath copy + CoInitializeEx + DllRegisterServer loop (see docstring).

    Called in place of AuiApp's registry read with r7 = SkinPath buffer."""
    prog = [
        (0x4f22,), (0x2f86,), (0x2f96,), (0x2fa6,),     # push pr, r8-r10
        (0x7fc0,),                                     # add #-64,r15
        ("LDL", 4, "skin"),
        ("L", "cp"), (0x6045,), (0x2701,), (0x7702,), (0x2008,), ("BF", "cp"),
        ("LDL", 1, "coinit"), (0xe400,), (0x410b,), (0xe500,),   # CoInitializeEx(0,0)
        ("LDL", 8, "names"),
        ("L", "outer"), (0x6080,), (0x2008,), ("BT", "done"), (0x69f3,),
        ("L", "wide"), (0x6084,), (0x600c,), (0x2901,), (0x7902,), (0x2008,), ("BF", "wide"),
        ("LDL", 1, "loadlib"), (0x64f3,), (0x410b,), (0x0009,),  # LoadLibraryW(buf)
        (0x2008,), ("BT", "outer"), (0x6403,),
        ("LDL", 5, "drs"), ("LDL", 1, "getproc"), (0x410b,), (0x0009,),
        (0x2008,), ("BT", "outer"), (0x400b,), (0x0009,),        # DllRegisterServer()
        ("BRA", "outer"), (0x0009,),
        ("L", "done"), (0x7f40,), (0x6af6,), (0x69f6,), (0x68f6,), (0x4f26,),
        (0x000b,), (0x0009,),
    ]
    lits = [("skin", (SKIN + "\0").encode("utf-16-le")), ("coinit", coinit),
            ("names", names_va), ("loadlib", loadlib),
            ("drs", "DllRegisterServer\0".encode("utf-16-le")), ("getproc", getproc)]
    return asm(prog, base, lits)[0]


def name_list(names):
    out = b""
    for n in names:
        stem = n[:-4] if n.lower().endswith(".dll") else n
        out += stem.encode("ascii") + b"\0"
    return out + b"\0"


# ------------------------------------------------------------ image lookups
def text_section(rom, mod):
    return next(s for s in rom.o32(mod) if s["flags"] & 0x20)


def find_wstr(rom, mod, text, prefix=False):
    s = text_section(rom, mod)
    off = rom.va2file(s["dataptr"])
    blob = rom.d[off:off + s["psize"]]
    pat = (text if prefix else text + "\0").encode("utf-16-le")
    hits = [m.start() for m in re.finditer(re.escape(pat), blob)
            if m.start() % 2 == 0]
    if len(hits) != 1:
        raise SystemExit("ze0_aui: %s: %d hits for %r" % (mod["name"], len(hits), text))
    return s["realaddr"] + hits[0], s["dataptr"] + hits[0]


def pools(rom, mod, value):
    s = text_section(rom, mod)
    off = rom.va2file(s["dataptr"])
    blob = rom.d[off:off + s["psize"]]
    pat = struct.pack("<I", value)
    return [(s["realaddr"] + i, s["dataptr"] + i) for i in range(0, len(blob) - 3, 4)
            if blob[i:i + 4] == pat]


def half(rom, ptr):
    return struct.unpack_from("<H", rom.d, rom.va2file(ptr))[0]


def text_ptr(rom, mod, va):
    s = text_section(rom, mod)
    return s["dataptr"] + (va - s["realaddr"])


def export(rom, dll, name):
    m = rom.module(dll)
    base = rom.e32(m)["vbase"]
    for _o, n, rva in rom.exports(m):
        if n == name:
            return base + rva
    raise SystemExit("ze0_aui: %s has no export %s" % (dll, name))


def registry_modules(rom):
    """Names of modules that carry an ATL ``REGISTRY`` resource (uncompressed)."""
    out = []
    for m in rom.modules():
        e = rom.e32(m)
        rva, size = e["res"]
        if not size:
            continue
        for s in rom.o32(m):
            if s["rva"] <= rva < s["rva"] + max(s["vsize"], s["psize"]) and not s["flags"] & 0x2000:
                off = rom.va2file(s["dataptr"])
                sec = rom.d[off:off + s["psize"]]
                if "REGISTRY".encode("utf-16-le") in sec[rva - s["rva"]:]:
                    out.append(m["name"])
                break
    return out


def control_dlls(app, kept, skins=()):
    """Control DLLs to register: REGISTRY modules of A that stay in the TOC.

    With ``skins`` (raw .skn bytes) only DLLs whose CLSIDs the skins name."""
    cand = [n for n in registry_modules(app) if n.lower() != "atlce400.dll" and n.lower() in kept]
    if skins:
        want = set()
        for b in skins:
            want |= {x.decode("utf-16-le").upper() for x in
                     re.findall(rb"\{\x00(?:[0-9A-Fa-f-]\x00){36}\}\x00", b)}
            want |= {x.decode().upper() for x in re.findall(rb"\{[0-9A-Fa-f-]{36}\}", b)}
        keep = []
        for n in cand:
            m = app.module(n)
            blob = b"".join(app.d[app.va2file(s["dataptr"]):app.va2file(s["dataptr"]) + s["psize"]]
                            for s in app.o32(m) if not s["flags"] & 0x2000)
            ids = {x.decode().upper() for x in re.findall(rb"\{[0-9A-Fa-f-]{36}\}", blob)}
            if ids & want:
                keep.append(n)
        cand = keep
    first = [n for n in FIRST if n.lower() in {c.lower() for c in cand}]
    return first + sorted((n for n in cand if n not in first), key=str.lower)


# --------------------------------------------------------------------- build
def reg_call(app, aui, value):
    """AuiApp's registry read of ``value``: (jsr_va, pool_va).

    The call is ``mov.l @(pool),r4`` (pool = &L"value") then ``jsr @r10``."""
    sp_va, _ = find_wstr(app, aui, value)
    cands = []
    for pva, pptr in pools(app, aui, sp_va):
        tsec = text_section(app, aui)
        for i in range(0, 0x400, 2):        # loads reach back at most 1 KiB
            iva = pva - i
            if iva < tsec["realaddr"]:
                break
            w = half(app, text_ptr(app, aui, iva))
            if w >> 12 == 0xd and (w >> 8) & 15 == 4 and \
                    ((iva & ~3) + 4 + 4 * (w & 0xff)) == pva:
                for k in range(2, 16, 2):
                    if half(app, text_ptr(app, aui, iva + k)) == 0x4a0b:  # jsr @r10
                        cands.append((iva + k, pva))
                        break
    if len(cands) != 1:
        raise SystemExit("ze0_aui: %s call site not unique (%d)" % (value, len(cands)))
    return cands[0]


def copy_routine(base, text):
    """Registry-read replacement: copy L"text" to r7, return 0 (ERROR_SUCCESS)."""
    prog = [("LDL", 4, "s"),
            ("L", "cp"), (0x6045,), (0x2701,), (0x7702,), (0x2008,), ("BF", "cp"),
            (0x000b,), (0xe000,)]
    return asm(prog, base, [("s", (text + "\0").encode("utf-16-le"))])[0]


def build(data, kernel_off, app_off, prefer, skins=(), no_timeout=False, start_form=""):
    kern, app = CERom(data, kernel_off), CERom(data, app_off)
    keep_k, keep_a, _ = ze0_ipl.plan(kern, app, prefer)
    kept = {m["name"].lower() for m in keep_a}
    lines = []
    aui = app.module("auiapp.exe")

    jsr_va, pool_va = reg_call(app, aui, "SkinPath")

    code_va, _ = find_wstr(app, aui, "Usage: auiapp [<skin file>", prefix=True)
    code_va = (code_va + 3) & ~3
    code_end, _ = find_wstr(app, aui, "Invalid command line argument(s)", prefix=True)
    names_va, _ = find_wstr(app, aui, "##AUITK ERROR##: CETLSTUB.DLL", prefix=True)
    names_end, _ = find_wstr(app, aui, "\\release\\scrn_400_240.bmp")

    dlls = control_dlls(app, kept, skins)
    blob = name_list(dlls)
    while len(blob) > names_end - names_va:
        dlls.pop()
        blob = name_list(dlls)
    code = routine(code_va, export(kern, "ole32.dll", "CoInitializeEx"),
                   export(kern, "coredll.dll", "LoadLibraryW"),
                   export(kern, "coredll.dll", "GetProcAddressW"), names_va)
    if code_va + len(code) > code_end:
        raise SystemExit("ze0_aui: routine does not fit (%d bytes)" % len(code))

    def ph(va):
        return ze0_ipl.phys(text_ptr(app, aui, va))
    lines.append((ph(code_va), code, "auiapp: SkinPath default %s, CoInitializeEx, "
                  "DllRegisterServer loop (M8.C1g)" % SKIN))
    lines.append((ph(names_va), blob, "auiapp: %d control DLLs to register" % len(dlls)))
    lines.append((ph(jsr_va), struct.pack("<H", 0x440b), "auiapp: SkinPath read -> jsr @r4"))
    lines.append((ph(pool_va), struct.pack("<I", code_va), "auiapp: r4 = routine"))
    if start_form:
        sf_va = (code_va + len(code) + 3) & ~3
        sf = copy_routine(sf_va, start_form)
        if sf_va + len(sf) > code_end:
            raise SystemExit("ze0_aui: StartForm routine does not fit")
        sf_jsr, sf_pool = reg_call(app, aui, "StartForm")
        lines.append((ph(sf_va), sf, "auiapp: StartForm default %s (M8.C1h)" % start_form))
        lines.append((ph(sf_jsr), struct.pack("<H", 0x440b), "auiapp: StartForm read -> jsr @r4"))
        lines.append((ph(sf_pool), struct.pack("<I", sf_va), "auiapp: r4 = StartForm routine"))

    if no_timeout:
        se = app.module("SystemEXE.exe")
        hits = pools(app, se, AUI_TIMEOUT_MS)
        if len(hits) != 1:
            raise SystemExit("ze0_aui: SystemEXE %d ms literal not unique (%d)"
                             % (AUI_TIMEOUT_MS, len(hits)))
        lines.append((ze0_ipl.phys(hits[0][1]), struct.pack("<I", 0xffffffff),
                      "SystemEXE: CAuiMonitorCmn wait %d ms -> INFINITE" % AUI_TIMEOUT_MS))
    return lines, dlls


def selftest():
    code, labels = asm([("L", "a"), (0x0009,), ("LDL", 1, "x"), ("BF", "a"), ("BRA", "a")],
                       0x1000, [("x", 0x12345678), ("s", b"ab")])
    w = struct.unpack_from("<4H", code)
    assert w[0] == 0x0009 and w[1] == 0xd101 and w[2] == 0x8bfc and w[3] == 0xaffb, [hex(x) for x in w]
    assert struct.unpack_from("<I", code, 8)[0] == 0x12345678
    assert struct.unpack_from("<I", code, 12)[0] == 0x1010 and code[16:18] == b"ab"
    r = routine(0x11414, 0x03dd259c, 0x03facfc0, 0x03fad150, 0x11b78)
    assert struct.unpack_from("<H", r, 0)[0] == 0x4f22 and len(r) < 0x194
    assert SKIN.encode("utf-16-le") in r and "DllRegisterServer".encode("utf-16-le") in r
    assert name_list(["SystemCC.dll", "multiskin"]) == b"SystemCC\0multiskin\0\0"
    c = copy_routine(0x2000, "frm_X")
    assert struct.unpack_from("<H", c, 0)[0] >> 8 == 0xd4 and "frm_X\0".encode("utf-16-le") in c
    print("ze0_aui selftest: ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("image", nargs="?")
    ap.add_argument("-o", "--out")
    ap.add_argument("--kernel-off", type=lambda s: int(s, 0), default=0x3e00200)
    ap.add_argument("--app-off", type=lambda s: int(s, 0), default=0x200200)
    ap.add_argument("--prefer-app", default="auiapp.exe,auirtdll.dll")
    ap.add_argument("--skins", default="", help="comma list of .skn files: register only "
                    "the DLLs whose CLSIDs they name")
    ap.add_argument("--no-aui-timeout", action="store_true")
    ap.add_argument("--start-form", default="", help="AuiApp StartForm value (M8.C1h), "
                    "e.g. frm_PRAGR_AgreeCaution")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    if not a.image or not a.out:
        ap.error("image and -o required")
    f = open(a.image, "rb")
    data = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    skins = [open(p, "rb").read() for p in a.skins.split(",") if p]
    prefer = [n.strip() for n in a.prefer_app.split(",") if n.strip()]
    lines, dlls = build(data, a.kernel_off, a.app_off, prefer, skins, a.no_aui_timeout,
                        a.start_form)
    with open(a.out, "w") as fo:
        for p, blob, why in lines:
            fo.write("0x%08x %s  # %s\n" % (p, blob.hex(), why))
    print("wrote %s: %d lines, %d control DLLs (%s ...)" % (a.out, len(lines), len(dlls),
                                                             ", ".join(dlls[:4])))


if __name__ == "__main__":
    main()
