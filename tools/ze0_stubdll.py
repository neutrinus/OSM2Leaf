#!/usr/bin/env python3
"""Stub ROM modules for the unit-flash DLLs that image A imports (M8.C1h).

Image A's AUI controls and several processes import ``HCXLog.dll`` and
``HCXMemory.dll`` by ordinal.  Neither DLL is on any ROM image of the card;
they live in the unit's own flash (EXP-2026-11-22-M8.C1g-ui-layer O5).  The
loader then refuses the importers (``DoImport Failed!``), and no AUI form
loads.  This module builds small replacement modules and adds them to image
A's TOC through the IPL patch (``ze0_ipl.py patch --stub-dlls``).  No byte on
the card changes.

What the callers need (EXP-2026-11-22-M8.C1h-hcx-stubs, census of 1 100+
call sites in image A):

* both DLLs export C++ classes: constructors (``HCXLog`` #7,
  ``HCXMemory`` #3, #24), destructors (``HCXLog`` #6, #1, ``HCXMemory`` #1,
  #29) and methods, called with ``r4 = this``; the derived classes keep
  their own members after the base, and only the stubs touch the base
  part, so a stub that does not write the object is safe;
* ``HCXMemory`` #5 (lock, ``r5`` = timeout) and #4 (unlock) are tested
  for non-zero = success;
* ``HCXMemory`` #23 ``(this, name, size)`` returns the address of a block
  of ``size`` bytes for the name (``type_info::name`` of the caller's
  class); several callers fetch the same name again and expect the same
  block, and the block is shared with other processes.

So every export is ``return this`` (``rts; mov r4,r0``), except
``HCXMemory`` #23, which widens the name and returns
``MapViewOfFile(CreateFileMappingW(-1, 0, PAGE_READWRITE, 0, size, name),
FILE_MAP_ALL_ACCESS, 0, 0, 0)``: a zeroed block, the same for the same name
in every process.  The entry point returns TRUE.

Layout: one page per module holds the code section (code, export directory
and module name); one more page holds the ``e32_rom``/``o32_rom`` records
and the file names.  Both pages reuse the physical pages of a module that
the TOC compaction dropped (by default ``gwes.exe`` in image A, whose
kernel copy runs instead), so they stay inside image A's XIP region.  The
code VA is the first free 64 KiB window above the lowest ROM DLL code
address (the gaps left by modules that the compaction dropped).

Usage::

    ze0_ipl.py patch archive/head256.img --prefer-app auiapp.exe,auirtdll.dll \
               --stub-dlls hcx -o ipl.txt
    ze0_stubdll.py --selftest
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ze0_aui import asm, export  # noqa: E402

PAGE = 0x1000
CODE_SPACE = (0x02000000, 0x04000000)
TOC_ATTRIB = 0x1007          # as image A's ROM DLLs
IMAGE_FLAGS = 0x212e         # DLL | executable | ... (image A's DLLs)
SCN_CODE = 0x60000020        # code | execute | read
PAGE_READWRITE = 4
FILE_MAP_ALL_ACCESS = 0x000f001f

# name -> (number of exported ordinals, {ordinal: special routine})
STUBS = {
    "hcx": [("HCXLog.dll", 8, {}), ("HCXMemory.dll", 32, {23: "shm"})],
}


def ret_this():
    return [(0x000b,), (0x6043,)]                    # rts; mov r4,r0


def dllmain():
    return [(0x000b,), (0xe001,)]                    # rts; mov #1,r0


def shm(cfm, mvf):
    """(this, char *name, size) -> view of a named, zeroed mapping of size."""
    return [
        (0x4f22,), (0x2f96,),                        # push pr, r9
        (0x6963,),                                   # r9 = size
        (0x7f80,), (0x7fe8,),                        # 128 B name + 24 B args
        (0x61f3,), (0x7118,),                        # r1 = r15 + 24
        (0xe23f,),                                   # r2 = 63 (max chars)
        ("L", "wide"), (0x6054,), (0x600c,), (0x2101,), (0x7102,),
        (0x2008,), ("BT", "named"),                  # stop after the NUL
        (0x4210,), ("BF", "wide"),                   # dt r2
        (0xe000,), (0x2101,),                        # cut: NUL-terminate
        ("L", "named"),
        (0xe4ff,), (0xe500,), (0xe604,), (0xe700,),  # -1, 0, PAGE_READWRITE, 0
        (0x1f94,),                                   # arg5 = size
        (0x60f3,), (0x7018,), (0x1f05,),             # arg6 = name
        ("LDL", 1, "cfm"), (0x410b,), (0x0009,),
        (0x2008,), ("BT", "out"),
        (0x6403,), ("LDL", 5, "access"), (0xe600,), (0xe700,),
        (0xe000,), (0x1f04,),                        # arg5 = 0 (whole mapping)
        ("LDL", 1, "mvf"), (0x410b,), (0x0009,),
        ("L", "out"),
        (0x7f7f,), (0x7f19,),                        # drop the 152 B frame
        (0x69f6,), (0x4f26,), (0x000b,), (0x0009,),
    ], [("cfm", cfm), ("mvf", mvf), ("access", FILE_MAP_ALL_ACCESS)]


def code_page(name, nfuncs, special, base, helpers):
    """Section bytes at VA ``base`` (= vbase + 0x1000): code, export dir, name.

    Returns (bytes, entry_va, export_dir_va, export_dir_size, func_vas)."""
    prog, lits = [("L", "main")] + dllmain() + [("L", "this")] + ret_this(), []
    for o, kind in sorted(special.items()):
        p, l = helpers[kind]
        prog += [("L", "o%d" % o)] + [(x[0], x[1], "%s%d" % (x[2], o)) if x[0] == "LDL"
                                      else (x[0], "%s%d" % (x[1], o)) if x[0] in ("L", "BT", "BF", "BRA")
                                      else x for x in p]
        lits += [("%s%d" % (n, o), v) for n, v in l]
    code, labels = asm(prog, base, lits)
    code = bytearray(code)
    while len(code) % 4:
        code += b"\0"
    funcs = [labels["o%d" % o] if o in special else labels["this"] for o in range(1, nfuncs + 1)]
    vbase = base - PAGE
    exp_va = base + len(code)
    name_va = exp_va + 40 + 4 * nfuncs
    exp = struct.pack("<IIHHIIIIIII", 0, 0, 0, 0, name_va - vbase, 1, nfuncs, 0,
                      exp_va + 40 - vbase, 0, 0)
    exp += b"".join(struct.pack("<I", f - vbase) for f in funcs)
    exp += name.encode("ascii") + b"\0"
    blob = bytes(code) + exp
    if len(blob) > PAGE:
        raise SystemExit("ze0_stubdll: %s does not fit in one page" % name)
    return blob, labels["main"], exp_va, len(exp), funcs


def e32_bytes(entry_rva, vbase, exp_rva, exp_size, timestamp):
    e = struct.pack("<HHIIHHIIIII", 1, IMAGE_FLAGS, entry_rva, vbase, 5, 0, 0x10000,
                    2 * PAGE, 0, 0, timestamp)
    units = [0] * 18
    units[0], units[1] = exp_rva, exp_size
    e += struct.pack("<18I", *units)
    e += struct.pack("<HH", 9, 0)                    # e32_subsys (WINDOWS_CE_GUI)
    return e


def o32_bytes(size, dataptr, realaddr):
    return struct.pack("<6I", size, PAGE, (size + 0x1ff) & ~0x1ff, dataptr, realaddr, SCN_CODE)


def used_ranges(roms_mods):
    out = []
    for rom, mods in roms_mods:
        for m in mods:
            try:
                e = rom.e32(m)
                out.append((e["vbase"], e["vbase"] + e["vsize"]))
                for s in rom.o32(m):
                    if s["vsize"]:
                        out.append((s["realaddr"], s["realaddr"] + s["vsize"]))
            except (struct.error, TypeError, ValueError, KeyError):
                pass
    return out


def free_windows(used, count, size=0x10000, space=CODE_SPACE):
    """``count`` free, ``size``-aligned VA windows in ``space``, lowest first."""
    out, va = [], space[0]
    while va + size <= space[1] and len(out) < count:
        if not any(a < va + size and va < b for a, b in used):
            out.append(va)
        va += size
    if len(out) < count:
        raise SystemExit("ze0_stubdll: no free %#x window for %d modules" % (size, count))
    return out


def donor_pages(app, dropped, pages):
    """Page-aligned ROM VAs of a dropped module's uncompressed code, ``pages`` long."""
    for m in app.modules():
        if m["name"].lower() not in dropped:
            continue
        for s in app.o32(m):
            if s["flags"] & 0x20 and not s["flags"] & 0x2000 and s["dataptr"] % PAGE == 0 \
                    and s["psize"] >= pages * PAGE:
                return m["name"], s["dataptr"]
    raise SystemExit("ze0_stubdll: no dropped module with %d free code pages" % pages)


def build(kern, app, keep_k, keep_a, which="hcx", timestamp=0x4e363910):
    """IPL lines and TOC entries for the stub set ``which``.

    Returns (lines, toc_entries, notes); lines are (rom_va, bytes, why)."""
    specs = STUBS[which]
    kept_a = {m["index"] for m in keep_a}
    dropped = {m["name"].lower() for m in app.modules() if m["index"] not in kept_a}
    have = {m["name"].lower() for m in list(keep_k) + list(keep_a)}
    for n, _, _ in specs:
        if n.lower() in have:
            raise SystemExit("ze0_stubdll: %s already in a TOC" % n)
    donor, page0 = donor_pages(app, dropped, len(specs) + 1)
    used = used_ranges([(kern, keep_k), (app, keep_a)])
    lo = min(r[0] for r in used if CODE_SPACE[0] <= r[0] < CODE_SPACE[1])
    vbases = free_windows(used, len(specs), space=(lo, CODE_SPACE[1]))
    helpers = {"shm": shm(export(kern, "coredll.dll", "CreateFileMappingW"),
                          export(kern, "coredll.dll", "MapViewOfFile"))}
    meta_va = page0 + len(specs) * PAGE
    meta = bytearray()
    lines, tocs, notes = [], [], []
    for i, (name, nfuncs, special) in enumerate(specs):
        vbase, dataptr = vbases[i], page0 + i * PAGE
        blob, entry, exp_va, exp_size, funcs = code_page(name, nfuncs, special, vbase + PAGE, helpers)
        lines.append((dataptr, blob, "%s stub code at 0x%08x (%d exports, M8.C1h)"
                      % (name, vbase + PAGE, nfuncs)))
        e32_va = meta_va + len(meta)
        meta += e32_bytes(entry - vbase, vbase, exp_va - vbase, exp_size, timestamp)
        meta += b"\0" * (-len(meta) % 4)
        o32_va = meta_va + len(meta)
        meta += o32_bytes(len(blob), dataptr, vbase + PAGE)
        name_va = meta_va + len(meta)
        meta += name.encode("ascii") + b"\0"
        meta += b"\0" * (-len(meta) % 4)
        tocs.append(struct.pack("<8I", TOC_ATTRIB, 0, 0, PAGE, name_va, e32_va, o32_va, dataptr))
        notes.append("%s: vbase 0x%08x, ROM 0x%08x, specials %s" % (
            name, vbase, dataptr, sorted(special) or "-"))
    lines.append((meta_va, bytes(meta), "e32/o32 records of the stub modules"))
    notes.append("pages from dropped module %s at 0x%08x" % (donor, page0))
    return lines, tocs, notes


def selftest():
    blob, entry, exp_va, exp_size, funcs = code_page(
        "X.dll", 4, {3: "shm"}, 0x02001000, {"shm": shm(0x03fadb90, 0x03faddbc)})
    w = struct.unpack_from("<4H", blob)
    assert w == (0x000b, 0xe001, 0x000b, 0x6043), [hex(x) for x in w]
    assert entry == 0x02001000 and funcs[0] == funcs[1] == funcs[3] == 0x02001004
    assert funcs[2] != 0x02001004
    assert struct.unpack_from("<H", blob, funcs[2] - 0x02001000)[0] == 0x4f22
    d = struct.unpack_from("<IIHHIIIIIII", blob, exp_va - 0x02001000)
    assert d[5] == 1 and d[6] == 4 and d[7] == 0 and d[8] == exp_va + 40 - 0x02000000
    assert blob.endswith(b"X.dll\0") and exp_size == 40 + 16 + 6
    assert struct.pack("<I", 0x03fadb90) in blob and struct.pack("<I", FILE_MAP_ALL_ACCESS) in blob
    e = e32_bytes(0x1000, 0x02000000, 0x1030, 0x40, 0)
    assert len(e) == 112 and struct.unpack_from("<I", e, 36)[0] == 0x1030
    assert len(o32_bytes(0x100, 0x8cae2000, 0x02001000)) == 24
    assert free_windows([(0x02000000, 0x02010000), (0x02015000, 0x02016000)], 2) == \
        [0x02020000, 0x02030000]
    print("ze0_stubdll selftest: ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    else:
        print(__doc__)
