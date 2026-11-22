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

Copied modules (M8.C1i, ``--copy-dlls apptimer``): ``AppTimerDll.dll`` is
not a unit-flash DLL; it sits in ROM image C of the card, which the IPL does
not load.  Audio.exe, Speech.exe, Vehicle.exe, Usb.exe, PhoneBTA.exe and
CameraCC import it.  Its fixed addresses collide with image A (its code VA
``0x01e41000`` lies in the data of image A's ``OBJDLL.dll``), so the module
is copied and moved: the code and read-only sections go to a free 64 KiB
window in the ROM DLL code space, the read-write section (the import table
and one global) to a free page of image A's DLL data range.  Every aligned
word of the code and read-only sections that points into one of the old
sections is rewritten for the new place (the literal pools, a pointer
table, the ``.pdata`` entries); RVAs (export and import directories) do not
change.  The list of rewritten words is printed with the notes.

Usage::

    ze0_ipl.py patch archive/head256.img --prefer-app auiapp.exe,auirtdll.dll \
               --stub-dlls hcx --copy-dlls apptimer -o ipl.txt
    ze0_stubdll.py --selftest
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ze0_aui import asm, export  # noqa: E402
from cerom import CERom  # noqa: E402

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


# name -> [(module, source)]; source is the image start of a ROM in the card
# image, or "nk1": the unit-flash kernel image (firmware/unit-flash/, M8.C1k)
COPIES = {
    "apptimer": [("AppTimerDll.dll", 0x5200200)],
    "unitflash": [("HCXLog.dll", "nk1"), ("HCXMemory.dll", "nk1"),
                  ("AppTimerDll.dll", "nk1")],
}
NK1_DEFAULT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "firmware", "unit-flash", "nk1-QY7200ND.bin")
DATA_SPACE = (0x01000000, 0x02000000)


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


def all_mods(rom):
    return list(rom.modules())


def free_page(used, lo, hi):
    """Lowest free page in [lo, hi) that no range in ``used`` touches."""
    va = (lo + PAGE - 1) & ~(PAGE - 1)
    while va + PAGE <= hi:
        if not any(a < va + PAGE and va < b for a, b in used):
            return va
        va += PAGE
    raise SystemExit("ze0_stubdll: no free data page in 0x%08x..0x%08x" % (lo, hi))


def relocate(blob, base, moves):
    """Rewrite the aligned words of ``blob`` (at VA ``base``) that point into a
    moved range.  ``moves`` is [(old_lo, old_hi, new_lo)].  Returns (bytes,
    [(va, old, new)])."""
    out, done = bytearray(blob), []
    for off in range(0, len(out) - 3, 4):
        v = struct.unpack_from("<I", out, off)[0]
        for lo, hi, new in moves:
            if lo <= v < hi:
                struct.pack_into("<I", out, off, new + v - lo)
                done.append((base + off, v, new + v - lo))
                break
    return bytes(out), done


def section_bytes(src, s, unpack=None):
    """Stored bytes of section ``s``, decompressed through ``unpack`` when the
    section is compressed (``IMAGE_SCN_COMPRESSED``)."""
    if s["flags"] & 0x2000:
        if unpack is None:
            raise SystemExit("ze0_stubdll: compressed section and no decompressor")
        return unpack(src, s)
    return bytes(src.d[src.va2file(s["dataptr"]):][:s["psize"]])


def copy_pages(src, name):
    """ROM pages ``copy_module`` needs for module ``name`` of ``src``."""
    mod = next((m for m in src.modules() if m["name"].lower() == name.lower()), None)
    if mod is None:
        raise SystemExit("ze0_stubdll: %s not in the ROM at 0x%x" % (name, src.start))
    return sum((max(s["vsize"], s["psize"]) + PAGE - 1) // PAGE or 1 for s in src.o32(mod))


def copy_module(src, name, vbase, rw_va, pages, timestamp=None, unpack=None):
    """Move module ``name`` of ROM ``src`` to code VA ``vbase`` and RW VA ``rw_va``.

    ``pages`` yields the ROM VAs of free, consecutive pages; a section takes
    as many as it needs.  Compressed sections are stored decompressed
    (``unpack(src, o32)`` returns the bytes).  Returns (lines, e32, o32s,
    toc_fields, notes); e32/o32 are bytes, the o32 dataptrs already set."""
    mod = next((m for m in src.modules() if m["name"].lower() == name.lower()), None)
    if mod is None:
        raise SystemExit("ze0_stubdll: %s not in the ROM at 0x%x" % (name, src.start))
    e = src.e32(mod)
    secs = list(src.o32(mod))
    moves, plan = [], []
    for s in secs:
        writable = bool(s["flags"] & 0x80000000)
        new = rw_va if writable else vbase + s["rva"]
        if writable and s["vsize"] > PAGE:
            raise SystemExit("ze0_stubdll: %s RW section larger than a page" % name)
        moves.append((s["realaddr"], s["realaddr"] + max(s["vsize"], s["psize"]), new))
        plan.append((s, new))
    lines, o32s, notes, all_done = [], b"", [], []
    for s, new in plan:
        size = max(s["vsize"], s["psize"])
        raw = section_bytes(src, s, unpack)[:size]
        raw, done = relocate(raw + bytes(size - len(raw)), new, moves)
        if s["flags"] & 0x80000000:
            # import address table: the lookup table again (the loader binds it)
            body = bytearray(raw)
            imp_off = src.rva2file(mod, e["imp"][0])
            while True:
                oft, _t, _f, _n, ft = struct.unpack_from("<5I", src.d, imp_off)
                if not (oft or ft):
                    break
                k = 0
                while True:
                    w = struct.unpack_from("<I", src.d, src.rva2file(mod, oft) + 4 * k)[0]
                    struct.pack_into("<I", body, ft - s["rva"] + 4 * k, w)
                    if not w:
                        break
                    k += 1
                imp_off += 20
            done = [d for d in done if struct.unpack_from("<I", body, d[0] - new)[0] == d[2]]
            raw = bytes(body)
        all_done += done
        n = (len(raw) + PAGE - 1) // PAGE or 1
        run = [next(pages) for _ in range(n)]
        if run != list(range(run[0], run[0] + n * PAGE, PAGE)):
            raise SystemExit("ze0_stubdll: %s needs %d consecutive pages" % (name, n))
        dataptr = run[0]
        lines.append((dataptr, raw, "%s rva 0x%x -> 0x%08x (%d words moved%s)"
                      % (name, s["rva"], new, len(done),
                         ", stored decompressed" if s["flags"] & 0x2000 else "")))
        o32s += struct.pack("<6I", s["vsize"], s["rva"], len(raw), dataptr, new,
                            s["flags"] & ~0x2000)
    e32 = bytearray(src.d[src.va2file(mod["e32"]):][:112])
    struct.pack_into("<I", e32, 8, vbase)
    if timestamp is not None:
        struct.pack_into("<I", e32, 32, timestamp)
    notes.append("%s: copied from ROM 0x%x, vbase 0x%08x -> 0x%08x, RW 0x%08x, %d words moved: %s"
                 % (name, src.start, e["vbase"], vbase, rw_va, len(all_done),
                    " ".join("%08x" % va for va, _o, _n in all_done)))
    return lines, bytes(e32), o32s, (mod["attrib"], mod["ft"], mod["size"]), notes


def kernel_unpack(kern):
    """Decompressor for ``copy_module``: the card kernel's own routine
    (``nk_decomp.py``, PySh4) run on the source section's stored bytes."""
    import nk_decomp
    regions = nk_decomp.nk_regions(kern.d, kern.start)

    def unpack(src, s):
        off = src.va2file(s["dataptr"])
        r0, out = nk_decomp.decompress(src.d, off, s["psize"], s["vsize"], regions=regions)
        if r0 > s["vsize"]:
            raise SystemExit("ze0_stubdll: section at 0x%08x does not decompress (r0 0x%x)"
                             % (s["realaddr"], r0))
        return out
    return unpack


def build(kern, app, keep_k, keep_a, which="hcx", timestamp=0x4e363910, copies=None,
          nk1=None):
    """IPL lines and TOC entries for the stub set ``which`` and copy set ``copies``.

    ``nk1`` is the path of the unit-flash kernel image (default
    ``NK1_DEFAULT``).  Returns (lines, toc_entries, notes); lines are
    (rom_va, bytes, why)."""
    specs = STUBS[which] if which else []
    cspecs = COPIES[copies] if copies else []
    if {n.lower() for n, _f, _s in specs} & {n.lower() for n, _src in cspecs}:
        raise SystemExit("ze0_stubdll: a module is both stubbed and copied")
    roms = {}
    for _n, where in cspecs:
        if where == "nk1" and where not in roms:
            path = nk1 or NK1_DEFAULT
            if not os.path.exists(path):
                raise SystemExit("ze0_stubdll: unit-flash image %s missing" % path)
            with open(path, "rb") as f:
                roms[where] = CERom(f.read(), 0)
        elif where not in roms:
            roms[where] = CERom(app.d, where)
    need = sum(copy_pages(roms[w], n) for n, w in cspecs)
    kept_a = {m["index"] for m in keep_a}
    dropped = {m["name"].lower() for m in app.modules() if m["index"] not in kept_a}
    have = {m["name"].lower() for m in list(keep_k) + list(keep_a)}
    for n in [x[0] for x in specs] + [x[0] for x in cspecs]:
        if n.lower() in have:
            raise SystemExit("ze0_stubdll: %s already in a TOC" % n)
    donor, page0 = donor_pages(app, dropped, len(specs) + 1 + need)
    used = used_ranges([(kern, keep_k), (app, keep_a)])
    lo = min(r[0] for r in used if CODE_SPACE[0] <= r[0] < CODE_SPACE[1])
    vbases = free_windows(used, len(specs) + len(cspecs), space=(lo, CODE_SPACE[1]))
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
    if cspecs:
        # RW pages: free in images A and B (all modules, kept or not)
        every = used_ranges([(kern, all_mods(kern)), (app, all_mods(app))])
        # the loader reserves RW sections only inside the kernel image's DLL
        # data window (dllfirst high word .. 0x02000000); 0x01a7c000, inside
        # image A's own window, fails with ERROR_OUTOFMEMORY (M8.C1i run H9)
        data_lo = max(app.hdr["dllfirst"], kern.hdr["dllfirst"]) & 0xffff0000
        pages = iter(range(meta_va + PAGE, meta_va + PAGE * (1 + need), PAGE))
        unpack = kernel_unpack(kern)
        for j, (name, where) in enumerate(cspecs):
            src = roms[where]
            rw_va = free_page(every, data_lo, DATA_SPACE[1])
            every.append((rw_va, rw_va + PAGE))
            c_lines, e32, o32s, (attrib, ft, size), c_notes = copy_module(
                src, name, vbases[len(specs) + j], rw_va, pages, unpack=unpack)
            lines += c_lines
            notes += c_notes
            e32_va = meta_va + len(meta)
            meta += e32
            o32_va = meta_va + len(meta)
            meta += o32s
            name_va = meta_va + len(meta)
            meta += name.encode("ascii") + b"\0"
            meta += b"\0" * (-len(meta) % 4)
            tocs.append(struct.pack("<8I", attrib, ft & 0xffffffff, ft >> 32, size, name_va,
                                    e32_va, o32_va, c_lines[0][0]))
    if len(meta) > PAGE:
        raise SystemExit("ze0_stubdll: module records do not fit in one page")
    lines.append((meta_va, bytes(meta), "e32/o32 records of the stub and copied modules"))
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
    blob = struct.pack("<4I", 0x01e41084, 0x01e4203c, 0x12345678, 0x01e43000)
    out, done = relocate(blob, 0x03751000, [(0x01e41000, 0x01e41a00, 0x03751000),
                                           (0x01e42000, 0x01e42040, 0x01f4f000)])
    assert struct.unpack("<4I", out) == (0x03751084, 0x01f4f03c, 0x12345678, 0x01e43000)
    assert [va for va, _o, _n in done] == [0x03751000, 0x03751004]
    assert free_page([(0x01bf0000, 0x01bf1800)], 0x01bf0000, 0x01c00000) == 0x01bf2000
    print("ze0_stubdll selftest: ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    else:
        print(__doc__)
