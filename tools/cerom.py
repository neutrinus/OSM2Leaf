#!/usr/bin/env python3
"""Windows CE ROM image (XIP) reader for the ZE0 nav firmware image.

Stdlib only. Reads the CE image embedded in the raw SD-card image (or in the
first ~32 MB of it, e.g. ``dd bs=1M count=32``) and walks ROMHDR, the module
TOC (TOCentry + e32_rom + o32_rom) and the FILESentry table.

The CE image is located by the ``ECEC`` signature at image start + 0x40,
which is followed by pTOC (VA of ROMHDR) and the ROMHDR offset from image
start. See docs/experiments/EXP-2026-11-05-35-ce-romhdr.md.

Usage:
  cerom.py IMG romhdr
  cerom.py IMG modules
  cerom.py IMG files
  cerom.py IMG sections MODULE
  cerom.py IMG exports MODULE
  cerom.py IMG va2file VA
  cerom.py IMG file2va OFFSET
  cerom.py IMG extract MODULE -o DIR   # raw o32 sections, uncompressed only
  cerom.py IMG memmap [--modules M1,M2] [--out FILE] [--pretty]
                      [--exclude-compressed] [--ghidra-script FILE]
  cerom.py IMG ghidra ...              # alias of memmap
  cerom.py --selftest                  # synthetic ROM, no vendor data

``memmap`` emits the section table ``tools/l3_harness/rommap.py`` consumes:
one block per ``o32_rom`` record of the selected modules, at ``o32_realaddr``,
with the bytes at ``p2f(o32_dataptr)``.  ``size`` is ``o32_psize`` (the stored
extent); ``vsize`` (the runtime extent) and ``rwx`` are extra keys.  Compressed
sections (``IMAGE_SCN_COMPRESSED``, 0x2000) are always flagged and are never
written out as raw section bytes; ``--exclude-compressed`` drops them from the
JSON and reports the count instead.  ``--ghidra-script`` additionally writes a
small Jython script that maps the same blocks with ``createMemoryBlock``.

See docs/experiments/EXP-2026-11-05-47-cerom-selftest.md and
docs/experiments/EXP-2026-11-05-48-cerom-memmap.md.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
import struct
import sys
import tempfile

ROMHDR_FIELDS = (
    "dllfirst dlllast physfirst physlast nummods ulRAMStart ulRAMFree "
    "ulRAMEnd ulCopyEntries ulCopyOffset ulProfileLen ulProfileOffset "
    "numfiles ulKernelFlags ulFSRamPercent ulDrivglobStart ulDrivglobLen"
).split()
ROMHDR_SIZE = 0x54
TOC_SIZE = 32
FILES_SIZE = 28
O32_SIZE = 24
IMAGE_SCN_COMPRESSED = 0x00002000
CNT_CODE = 0x00000020
CNT_UNINITIALIZED_DATA = 0x00000080
MEM_EXECUTE = 0x20000000
MEM_READ = 0x40000000
MEM_WRITE = 0x80000000

MEMMAP_SCHEMA = "osm2leaf.cerom.memmap/v1"
MEMMAP_GENERATOR = "tools/cerom.py memmap"


class CERom:
    def __init__(self, data, image_start=None):
        self.d = data
        if image_start is None:
            image_start = self.find_image_start()
        self.start = image_start
        sig, self.ptoc, self.toc_off = struct.unpack_from("<4sII", data, image_start + 0x40)
        if sig != b"ECEC":
            raise ValueError("no ECEC at image start + 0x40 (0x%x)" % (image_start + 0x40))
        self.hdr_off = image_start + self.toc_off
        vals = struct.unpack_from("<17IHHIII", data, self.hdr_off)
        self.hdr = dict(zip(ROMHDR_FIELDS, vals[:17]))
        self.hdr["usCPUType"], self.hdr["usMiscFlags"] = vals[17], vals[18]
        self.hdr["pExtensions"], self.hdr["ulTrackingStart"], self.hdr["ulTrackingLen"] = vals[19:22]
        # VA of image start: pTOC - offset of ROMHDR from image start.
        self.va_base = self.ptoc - self.toc_off

    def find_image_start(self):
        i = 0
        while True:
            i = self.d.find(b"ECEC", i)
            if i < 0:
                raise ValueError("ECEC signature not found")
            if i >= 0x40:
                ptoc, off = struct.unpack_from("<II", self.d, i + 4)
                if 0x80000000 <= ptoc and ptoc - off >= 0x80000000 and i - 0x40 + off < len(self.d):
                    return i - 0x40
            i += 1

    def va2file(self, va):
        return va - self.va_base + self.start

    def file2va(self, off):
        return off - self.start + self.va_base

    def cstr(self, va):
        o = self.va2file(va)
        if not 0 <= o < len(self.d):
            return None
        e = self.d.find(b"\0", o, o + 260)
        if e < 0:
            return None
        return self.d[o:e].decode("latin1")

    def modules(self):
        base = self.hdr_off + ROMHDR_SIZE
        for i in range(self.hdr["nummods"]):
            attrib, ftl, fth, size, name, e32, o32, load = struct.unpack_from("<8I", self.d, base + TOC_SIZE * i)
            yield dict(index=i, attrib=attrib, ft=(fth << 32) | ftl, size=size, name=self.cstr(name),
                       e32=e32, o32=o32, load=load)

    def files(self):
        base = self.hdr_off + ROMHDR_SIZE + TOC_SIZE * self.hdr["nummods"]
        for i in range(self.hdr["numfiles"]):
            attrib, ftl, fth, rsize, csize, name, load = struct.unpack_from("<7I", self.d, base + FILES_SIZE * i)
            yield dict(index=i, attrib=attrib, ft=(fth << 32) | ftl, rsize=rsize, csize=csize,
                       name=self.cstr(name), load=load)

    def e32(self, mod):
        o = self.va2file(mod["e32"])
        objcnt, flags, entry, vbase, smaj, smin, stack, vsize, s14rva, s14size, ts = \
            struct.unpack_from("<HHIIHHIIIII", self.d, o)
        units = struct.unpack_from("<18I", self.d, o + 36)
        return dict(objcnt=objcnt, imageflags=flags, entryrva=entry, vbase=vbase, stackmax=stack,
                    vsize=vsize, timestamp=ts,
                    export=(units[0], units[1]), imp=(units[2], units[3]), res=(units[4], units[5]))

    def o32(self, mod):
        e = self.e32(mod)
        o = self.va2file(mod["o32"])
        for i in range(e["objcnt"]):
            vsize, rva, psize, dataptr, real, flags = struct.unpack_from("<6I", self.d, o + O32_SIZE * i)
            yield dict(vsize=vsize, rva=rva, psize=psize, dataptr=dataptr, realaddr=real, flags=flags)

    def imports(self, mod):
        """Import slots of ``mod`` from the uncompressed OriginalFirstThunk table.

        Yields (dll, slot_va, name_or_None, ordinal_or_None). ``slot_va`` is the
        process VA of the FirstThunk entry (vbase + RVA). Names come from the
        OFT, so compressed sections (where FirstThunk may live) are not needed.
        """
        e = self.e32(mod)
        base = e["vbase"]
        off = self.rva2file(mod, e["imp"][0])
        if off is None:
            return
        while True:
            oft, _ts, _fw, name_rva, ft = struct.unpack_from("<5I", self.d, off)
            if not (oft or name_rva or ft):
                break
            dll_off = self.rva2file(mod, name_rva)
            dll = self.d[dll_off:self.d.find(b"\0", dll_off)].decode("latin1") if dll_off else "?"
            thunk = self.rva2file(mod, oft or ft)
            i = 0
            while thunk is not None:
                (v,) = struct.unpack_from("<I", self.d, thunk + 4 * i)
                if v == 0:
                    break
                slot = base + ft + 4 * i
                if v & 0x80000000:
                    yield dll, slot, None, v & 0xFFFF
                else:
                    no = self.rva2file(mod, v)
                    nm = self.d[no + 2:self.d.find(b"\0", no + 2)].decode("latin1") if no is not None else "?"
                    yield dll, slot, nm, None
                i += 1
            off += 20

    def rva2file(self, mod, rva):
        """File offset of an RVA in an uncompressed section of ``mod`` (or None)."""
        for sec in self.o32(mod):
            if sec["rva"] <= rva < sec["rva"] + sec["psize"] and not sec["flags"] & IMAGE_SCN_COMPRESSED:
                return self.va2file(sec["dataptr"]) + rva - sec["rva"]
        return None

    def exports(self, mod):
        """Yield (ordinal, name, rva) for the named exports of ``mod``."""
        e = self.e32(mod)
        o = self.rva2file(mod, e["export"][0])
        if o is None or not e["export"][1]:
            return
        _fl, _ts, _mj, _mn, _name, base, nfun, nnam, aof, aon, aoo = struct.unpack_from("<IIHHIIIIIII", self.d, o)
        names = struct.unpack_from("<%dI" % nnam, self.d, self.rva2file(mod, aon))
        ords = struct.unpack_from("<%dH" % nnam, self.d, self.rva2file(mod, aoo))
        funcs = struct.unpack_from("<%dI" % nfun, self.d, self.rva2file(mod, aof))
        for n, i in zip(names, ords):
            p = self.rva2file(mod, n)
            yield i + base, self.d[p:self.d.find(b"\0", p)].decode("latin1"), funcs[i]

    def module(self, name):
        for m in self.modules():
            if m["name"] and m["name"].lower() == name.lower():
                return m
        raise KeyError(name)


# --------------------------------------------------------------------------
# Memory map (`memmap` / `ghidra`): the section table rommap.py consumes.
# --------------------------------------------------------------------------


def hx(value):
    """Format an integer the way the L3 JSON contract does."""
    return "0x%x" % value


def rwx_bits(flags):
    """CE section flags -> ``rwx`` triple, same rule as rommap.py."""
    if flags & (MEM_EXECUTE | MEM_READ | MEM_WRITE):
        read = bool(flags & MEM_READ)
        execute = bool(flags & MEM_EXECUTE)
        write = bool(flags & MEM_WRITE)
    else:
        # No MEM_* bits: fall back to the content flags.
        read = True
        execute = bool(flags & CNT_CODE)
        write = bool(flags & CNT_UNINITIALIZED_DATA)
    return ("r" if read else "-") + ("w" if write else "-") + ("x" if execute else "-")


def section_record(cerom, module_name, section, index):
    """One ``o32_rom`` record in the shape ``rommap.py`` reads.

    ``size`` is ``o32_psize`` (bytes actually stored in the image) and
    ``vsize`` keeps the unpacked runtime extent; ``compressed`` is never a
    guess, it comes from ``IMAGE_SCN_COMPRESSED``.  A section with no stored
    bytes (``psize == 0``, typically BSS) gets ``file_offset: null``.
    """
    compressed = bool(section["flags"] & IMAGE_SCN_COMPRESSED)
    if section["psize"]:
        offset = cerom.va2file(section["dataptr"])
        if not (0 <= offset and offset + section["psize"] <= len(cerom.d)):
            raise ValueError(
                "%s/%d: stored bytes 0x%x..0x%x lie outside the image (%d bytes)"
                % (module_name, index, offset, offset + section["psize"], len(cerom.d)))
    else:
        offset = None
    return {
        "name": "sec%d" % index,
        "va": hx(section["realaddr"]),
        "file_offset": offset,
        "size": section["psize"],
        "vsize": section["vsize"],
        "characteristics": hx(section["flags"]),
        "compressed": compressed,
        "rwx": rwx_bits(section["flags"]),
    }


def build_memmap_report(cerom, image_name, image_size, image_sha256=None,
                        modules=None, exclude_compressed=False, sha256_scope=None):
    """Build the ``memmap`` document for one CE segment.

    ``modules`` is a list of module names (case-insensitive); ``None`` keeps
    every named module.  The result is directly usable as the ``--report``
    input of ``tools/l3_harness/rommap.py convert``.
    """
    all_modules = [m for m in cerom.modules() if m["name"]]
    if modules:
        available = {m["name"].lower() for m in all_modules}
        missing = [name for name in modules if name.lower() not in available]
        if missing:
            raise KeyError(missing[0])
        wanted = {name.lower() for name in modules}
        selected = [m for m in all_modules if m["name"].lower() in wanted]
    else:
        selected = all_modules

    blocks = []
    skipped_modules = []
    counts = {"modules": 0, "sections": 0, "compressed": 0, "skipped_compressed": 0}
    for module in selected:
        sections = []
        for index, section in enumerate(cerom.o32(module)):
            record = section_record(cerom, module["name"], section, index)
            if record["compressed"]:
                if exclude_compressed:
                    counts["skipped_compressed"] += 1
                    continue
                counts["compressed"] += 1
            sections.append(record)
        if not sections:
            skipped_modules.append(module["name"])
            continue
        blocks.append({
            # ``module`` is the flat name TODO M9.1 asks for; ``name`` is the
            # key rommap.py reads.  ``vbase`` is the module's link-time base.
            "module": module["name"],
            "name": module["name"],
            "vbase": hx(cerom.e32(module)["vbase"]),
            "sections": sections,
        })
        counts["sections"] += len(sections)

    counts["modules"] = len(blocks)
    counts["skipped_modules"] = skipped_modules
    segment = {
        "segment_index": 0,
        "segment_base": hx(cerom.start),
        "phys_base": hx(cerom.hdr["physfirst"]),
        "pTOC": hx(cerom.ptoc),
        "romhdr": dict(cerom.hdr),
        "counts": counts,
        "modules": blocks,
    }
    return {
        "schema": MEMMAP_SCHEMA,
        "generator": MEMMAP_GENERATOR,
        "image": os.path.basename(image_name),
        "image_size": image_size,
        "image_sha256": image_sha256,
        "image_sha256_scope": sha256_scope,
        "segments": [segment],
    }


def sha256_scope_text(data_length, image_size):
    """Describe what the reported SHA-256 covers (the tool reads a window)."""
    if data_length >= image_size:
        return "whole file (%d bytes)" % image_size
    return "first %d of %d bytes" % (data_length, image_size)


GHIDRA_TEMPLATE = """\
# Ghidra script generated by `python3 tools/cerom.py IMG memmap --ghidra-script`.
# One memory block per o32 section, at o32_realaddr, bytes read from
# p2f(o32_dataptr).  Compressed sections (IMAGE_SCN_COMPRESSED, 0x2000) are
# NOT mapped: their stored bytes are not the section contents and no CE
# decompressor exists yet (TODO M1.2/M1.3).
__OMITTED__# Usage: analyzeHeadless <project> <name> -process <program> -noanalysis \\
#            -scriptPath <dir> -postScript <this file>
# @category OSM2Leaf
# @runtime Jython

from java.io import RandomAccessFile
from jarray import zeros

IMAGE = __IMAGE__
# (name, va, file_offset or None, size, read, write, execute)
BLOCKS = [
__BLOCKS__]

mem = currentProgram.getMemory()
fh = RandomAccessFile(IMAGE, "r")
mapped = 0
try:
    for name, va, offset, size, read, write, execute in BLOCKS:
        addr = toAddr(va)
        block = mem.createMemoryBlock(name, addr, size, False)
        block.setRead(read)
        block.setWrite(write)
        block.setExecute(execute)
        if offset is not None:
            buffer = zeros(size, 'b')
            fh.seek(offset)
            fh.readFully(buffer)
            block.putBytes(addr, buffer)
        mapped += 1
finally:
    fh.close()
print("cerom memmap: mapped " + str(mapped) + " block(s)")
"""


def write_ghidra_script(path, image_path, report):
    """Write a Jython script mapping the report's blocks; return the count."""
    lines = []
    omitted = []
    for segment in report["segments"]:
        for module in segment["modules"]:
            for section in module["sections"]:
                name = "%s/%s" % (module["name"], section["name"])
                if section["compressed"]:
                    omitted.append(name)
                    continue
                offset = section["file_offset"]
                lines.append("    (%r, %s, %s, %d, %s, %s, %s),"
                             % (name, section["va"],
                                "None" if offset is None else "0x%x" % offset,
                                section["size"],
                                section["rwx"][0] == "r",
                                section["rwx"][1] == "w",
                                section["rwx"][2] == "x"))
    text = GHIDRA_TEMPLATE.replace("__IMAGE__", repr(os.path.abspath(image_path)))
    text = text.replace("__BLOCKS__", "\n".join(lines) + ("\n" if lines else ""))
    text = text.replace(
        "__OMITTED__",
        "# Omitted compressed sections: " + ", ".join(omitted) + "\n" if omitted else "")
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return len(lines)


# --------------------------------------------------------------------------
# Synthetic ROM for --selftest.  No vendor bytes: every offset below is built
# from scratch, so the layout doubles as executable documentation of the
# structures the parser expects.
# --------------------------------------------------------------------------

SYNTH_IMAGE_START = 0x200
SYNTH_VA_BASE = 0x8CAE1000
SYNTH_TOC_OFF = 0x1000
SYNTH_HDR_OFF = SYNTH_IMAGE_START + SYNTH_TOC_OFF
SYNTH_SIZE = 0x7400


def synth_va(off):
    """Map a file offset of the synthetic image to a VA (and back)."""
    return SYNTH_VA_BASE + off - SYNTH_IMAGE_START


def synth_romhdr():
    """Expected ROMHDR content of the synthetic image, field by field."""
    return dict(
        dllfirst=synth_va(0x6000), dlllast=0x8D010000, physfirst=SYNTH_VA_BASE,
        physlast=SYNTH_VA_BASE + 0x90000, nummods=2,
        ulRAMStart=0x8E000000, ulRAMFree=0x8E100000, ulRAMEnd=0x8F000000,
        ulCopyEntries=0, ulCopyOffset=0, ulProfileLen=0, ulProfileOffset=0,
        numfiles=1, ulKernelFlags=0x00000002, ulFSRamPercent=0x80808080,
        ulDrivglobStart=0, ulDrivglobLen=0, usCPUType=0x01A6,
        usMiscFlags=0x0002, pExtensions=0, ulTrackingStart=0, ulTrackingLen=0,
    )


def build_synthetic_rom():
    """Return ``(bytes, layout)`` for a two-module, one-file CE ROM.

    Layout: ``ECEC`` at image start + 0x40, ROMHDR at +0x1000, two 32-byte
    ``TOCentry`` records, one 28-byte ``FILESentry``.  Module 0 has an
    uncompressed section carrying a two-export directory plus one
    ``IMAGE_SCN_COMPRESSED`` section; module 1 has no exports.
    """
    d = bytearray(SYNTH_SIZE)
    layout = dict(image_start=SYNTH_IMAGE_START, va_base=SYNTH_VA_BASE,
                  toc_off=SYNTH_TOC_OFF, hdr_off=SYNTH_HDR_OFF,
                  ptoc=synth_va(SYNTH_HDR_OFF), hdr=synth_romhdr())

    struct.pack_into("<4sII", d, SYNTH_IMAGE_START + 0x40, b"ECEC",
                     layout["ptoc"], SYNTH_TOC_OFF)
    hdr = layout["hdr"]
    struct.pack_into("<17IHHIII", d, SYNTH_HDR_OFF,
                     *[hdr[k] for k in ROMHDR_FIELDS],
                     hdr["usCPUType"], hdr["usMiscFlags"], hdr["pExtensions"],
                     hdr["ulTrackingStart"], hdr["ulTrackingLen"])

    # NUL-terminated names at 0x2000: module 2x, file 1x.
    name_off = {}
    off = 0x2000
    for name in (b"NK.EXE", b"NAVI.EXE", b"default.hv"):
        d[off:off + len(name) + 1] = name + b"\0"
        name_off[name.decode()] = off
        off += len(name) + 1

    # Export strings live in module 0's uncompressed section (rva 0x1000,
    # file 0x5000), so the directory, its three arrays and the names all sit
    # in the same section.
    exp_names = (b"MAL_DataVol_getOffset", b"MAL_DataVol_getSize")
    exp_funcs = (0x1100, 0x1200)
    name_rvas = []
    off = 0x5040
    for name in exp_names:
        d[off:off + len(name) + 1] = name + b"\0"
        name_rvas.append(0x1000 + off - 0x5000)
        off += len(name) + 1
    struct.pack_into("<IIHHIIIIIII", d, 0x5000,
                     0, 0x5F000000, 0, 0, name_rvas[0], 1, 2, 2,
                     0x1028, 0x1030, 0x1038)          # aof, aon, aoo
    struct.pack_into("<2I", d, 0x5028, *exp_funcs)      # functions
    struct.pack_into("<2I", d, 0x5030, *name_rvas)      # names
    struct.pack_into("<2H", d, 0x5038, 0, 1)            # ordinals -> base 1

    # TOCentry[0] = NK.EXE, TOCentry[1] = NAVI.EXE.
    toc = SYNTH_HDR_OFF + ROMHDR_SIZE
    struct.pack_into("<8I", d, toc,
                     0x0000001C, 0x11223344, 0x00000001, 0x8000,
                     synth_va(name_off["NK.EXE"]), synth_va(0x4000),
                     synth_va(0x4200), 0x8CE00000)
    struct.pack_into("<8I", d, toc + TOC_SIZE,
                     0x0000001C, 0x55667788, 0x00000001, 0x4000,
                     synth_va(name_off["NAVI.EXE"]), synth_va(0x6000),
                     synth_va(0x6200), 0x8D000000)

    # e32_rom: objcnt, flags, entryrva, vbase, smaj, smin, stack, vsize,
    # s14rva, s14size, timestamp; then 18 data-dir units at +36.
    struct.pack_into("<HHIIHHIIIII", d, 0x4000,
                     2, 0x0002, 0x1000, 0x8CE00000, 1, 0, 0x1000, 0x8000,
                     0, 0, 0x5F000000)
    struct.pack_into("<18I", d, 0x4000 + 36, *([0x1000, 0x80, 0, 0, 0, 0] + [0] * 12))
    struct.pack_into("<HHIIHHIIIII", d, 0x6000,
                     2, 0x2002, 0x1008, 0x8D000000, 1, 0, 0x800, 0x4000,
                     0, 0, 0x5F010000)
    struct.pack_into("<18I", d, 0x6000 + 36, *([0] * 18))

    # o32_rom: vsize, rva, psize, dataptr, realaddr, flags.
    struct.pack_into("<6I", d, 0x4200, 0x400, 0x1000, 0x400, synth_va(0x5000),
                     0x8CE01000, 0xC0000040)                  # not compressed
    struct.pack_into("<6I", d, 0x4218, 0x800, 0x2000, 0x100, synth_va(0x5400),
                     0x8CE02000, 0xC0002040)                  # COMPRESSED
    struct.pack_into("<6I", d, 0x6200, 0x300, 0x1000, 0x200, synth_va(0x6400),
                     0x8D001000, 0x60000020)
    struct.pack_into("<6I", d, 0x6218, 0x100, 0x2000, 0x80, synth_va(0x6600),
                     0x8D002000, 0xC0002040)                  # COMPRESSED

    # FILESentry: attrib, ftl, fth, real size, compressed size, name, load.
    struct.pack_into("<7I", d, toc + TOC_SIZE * 2,
                     0x00000040, 0x55667788, 0x00000000, 0x200, 0x100,
                     synth_va(name_off["default.hv"]), synth_va(0x7000))
    d[0x7000:0x7000 + 0x200] = b"\xA5" * 0x200

    layout["name_off"] = name_off
    layout["export_names"] = [n.decode() for n in exp_names]
    return bytes(d), layout


def selftest():
    """Run the synthetic-ROM assertions; return 0 (raise on mismatch)."""
    rom, exp = build_synthetic_rom()
    checks = []

    def ok(label, got, want):
        if got != want:
            raise AssertionError("%s: got %r, want %r" % (label, got, want))
        checks.append(label)

    with tempfile.TemporaryDirectory(prefix="cerom-selftest-") as td:
        path = os.path.join(td, "synthetic-rom.img")
        with open(path, "wb") as fh:
            fh.write(rom)
        with open(path, "rb") as fh:
            data = fh.read()

        # Header: image discovery, then every ROMHDR field, exactly.
        r = CERom(data)
        ok("image_start", r.start, exp["image_start"])
        ok("va_base", r.va_base, exp["va_base"])
        ok("pTOC", r.ptoc, exp["ptoc"])
        ok("ROMHDR file offset", r.hdr_off, exp["hdr_off"])
        ok("ROMHDR fields", r.hdr, exp["hdr"])
        ok("nummods/numfiles/usCPUType",
           (r.hdr["nummods"], r.hdr["numfiles"], r.hdr["usCPUType"]), (2, 1, 0x01A6))
        ok("physfirst/physlast",
           (r.hdr["physfirst"], r.hdr["physlast"]),
           (SYNTH_VA_BASE, SYNTH_VA_BASE + 0x90000))

        r2 = CERom(data, exp["image_start"])
        ok("explicit --image-start agrees",
           (r2.start, r2.va_base, r2.hdr_off), (r.start, r.va_base, r.hdr_off))

        # VA <-> file offset, both directions and round-trips.
        ok("va2file(va_base)", r.va2file(exp["va_base"]), exp["image_start"])
        for off in (0x2000, 0x4000, 0x4200, 0x5000, 0x5040, 0x7000):
            ok("file2va(va2file(0x%x))" % off,
               r.file2va(r.va2file(synth_va(off))), synth_va(off))
            ok("va2file(file2va(0x%x))" % off, r.va2file(r.file2va(off)), off)

        # TOCentry + FILESentry tables, names included.
        mods = list(r.modules())
        ok("module count", len(mods), 2)
        ok("module names", [m["name"] for m in mods], ["NK.EXE", "NAVI.EXE"])
        ok("module 0 record", {k: mods[0][k] for k in
                              ("attrib", "ft", "size", "e32", "o32", "load")},
           dict(attrib=0x1C, ft=0x0000000111223344, size=0x8000,
                e32=synth_va(0x4000), o32=synth_va(0x4200), load=0x8CE00000))
        ok("module 1 record", {k: mods[1][k] for k in
                              ("attrib", "ft", "size", "e32", "o32", "load")},
           dict(attrib=0x1C, ft=0x0000000155667788, size=0x4000,
                e32=synth_va(0x6000), o32=synth_va(0x6200), load=0x8D000000))
        files = list(r.files())
        ok("file count", len(files), 1)
        ok("file name", files[0]["name"], "default.hv")
        ok("file sizes", (files[0]["rsize"], files[0]["csize"]), (0x200, 0x100))
        ok("file payload offset", r.va2file(files[0]["load"]), 0x7000)
        ok("case-insensitive module lookup", r.module("navi.exe")["index"], 1)

        # e32_rom and the two o32_rom sections (one compressed).
        e0 = r.e32(mods[0])
        ok("e32 mod0 header",
           (e0["objcnt"], e0["vbase"], e0["entryrva"], e0["vsize"], e0["timestamp"]),
           (2, 0x8CE00000, 0x1000, 0x8000, 0x5F000000))
        ok("e32 mod0 export dir (rva, size)", e0["export"], (0x1000, 0x80))
        ok("e32 mod1 header",
           (r.e32(mods[1])["objcnt"], r.e32(mods[1])["vbase"]), (2, 0x8D000000))
        secs = list(r.o32(mods[0]))
        ok("sections mod0", [(s["rva"], s["vsize"], s["psize"],
                              r.va2file(s["dataptr"]), s["realaddr"], s["flags"])
                             for s in secs],
           [(0x1000, 0x400, 0x400, 0x5000, 0x8CE01000, 0xC0000040),
            (0x2000, 0x800, 0x100, 0x5400, 0x8CE02000, 0xC0002040)])
        ok("compressed flags mod0",
           [bool(s["flags"] & IMAGE_SCN_COMPRESSED) for s in secs], [False, True])
        ok("sections mod1", [(s["rva"], s["psize"], r.va2file(s["dataptr"]), s["flags"])
                             for s in r.o32(mods[1])],
           [(0x1000, 0x200, 0x6400, 0x60000020), (0x2000, 0x80, 0x6600, 0xC0002040)])
        ok("rva2file uncompressed", r.rva2file(mods[0], 0x1010), 0x5010)
        ok("rva2file compressed -> None", r.rva2file(mods[0], 0x2010), None)

        # Export directory: ordinals (base 1), names and function RVAs.
        ok("exports mod0", sorted(r.exports(mods[0])),
           [(1, "MAL_DataVol_getOffset", 0x1100),
            (2, "MAL_DataVol_getSize", 0x1200)])
        ok("exports mod1 empty", list(r.exports(mods[1])), [])

        # Existing subcommands keep working on the same file.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli romhdr exit", main([path, "romhdr"]), 0)
        out = buf.getvalue()
        ok("cli romhdr va_base line", "va_base      0x%08x" % exp["va_base"] in out, True)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli exports exit", main([path, "exports", "NK.EXE"]), 0)
        ok("cli exports name", exp["export_names"][0] in buf.getvalue(), True)

        # --- memmap / ghidra: the section table rommap.py consumes (M1.5) ---
        sha = hashlib.sha256(rom).hexdigest()
        mm = build_memmap_report(r, path, len(rom), sha)
        seg = mm["segments"][0]
        ok("memmap schema", mm["schema"], MEMMAP_SCHEMA)
        ok("memmap generator", mm["generator"], MEMMAP_GENERATOR)
        ok("memmap image basename", mm["image"], "synthetic-rom.img")
        ok("memmap image size", mm["image_size"], len(rom))
        ok("memmap image sha256", mm["image_sha256"], sha)
        ok("memmap segment base", seg["segment_base"], "0x%x" % exp["image_start"])
        ok("memmap phys base", seg["phys_base"], "0x%x" % exp["va_base"])
        ok("memmap pTOC", seg["pTOC"], "0x%x" % exp["ptoc"])
        ok("memmap romhdr is ROMHDR", seg["romhdr"], exp["hdr"])
        ok("memmap module names", [m["name"] for m in seg["modules"]], ["NK.EXE", "NAVI.EXE"])
        ok("memmap module alias", [m["module"] for m in seg["modules"]], ["NK.EXE", "NAVI.EXE"])
        ok("memmap vbase", [m["vbase"] for m in seg["modules"]], ["0x8ce00000", "0x8d000000"])
        ok("memmap block count",
           sum(len(m["sections"]) for m in seg["modules"]), 4)
        mod0 = seg["modules"][0]["sections"]
        ok("memmap section key order", sorted(mod0[0]),
           ["characteristics", "compressed", "file_offset", "name", "rwx", "size", "va", "vsize"])
        ok("memmap mod0 name/va/file/size",
           [(s["name"], s["va"], s["file_offset"], s["size"]) for s in mod0],
           [("sec0", "0x8ce01000", 0x5000, 0x400),
            ("sec1", "0x8ce02000", 0x5400, 0x100)])
        ok("memmap mod0 vsize", [s["vsize"] for s in mod0], [0x400, 0x800])
        ok("memmap mod0 characteristics",
           [s["characteristics"] for s in mod0], ["0xc0000040", "0xc0002040"])
        ok("memmap compressed flags",
           [s["compressed"] for s in mod0], [False, True])
        ok("memmap rwx mod0", [s["rwx"] for s in mod0], ["rw-", "rw-"])
        ok("memmap mod1 name/va/file/size",
           [(s["name"], s["va"], s["file_offset"], s["size"])
            for s in seg["modules"][1]["sections"]],
           [("sec0", "0x8d001000", 0x6400, 0x200),
            ("sec1", "0x8d002000", 0x6600, 0x80)])
        ok("memmap rwx mod1",
           [s["rwx"] for s in seg["modules"][1]["sections"]], ["r-x", "rw-"])
        ok("memmap counts", seg["counts"],
           {"modules": 2, "sections": 4, "compressed": 2,
            "skipped_compressed": 0, "skipped_modules": []})

        filtered = build_memmap_report(r, path, len(rom), None, modules=["navi.exe"])
        ok("memmap module filter case-insensitive",
           [m["name"] for m in filtered["segments"][0]["modules"]], ["NAVI.EXE"])
        ok("memmap module filter block count",
           len(filtered["segments"][0]["modules"][0]["sections"]), 2)
        try:
            build_memmap_report(r, path, len(rom), None, modules=["Navi.exe", "Nope.dll"])
        except KeyError as exc:
            ok("memmap unknown module rejected", exc.args[0], "Nope.dll")
        else:
            raise AssertionError("build_memmap_report() accepted an unknown module")

        excluded = build_memmap_report(r, path, len(rom), None, exclude_compressed=True)
        ok("memmap --exclude-compressed keeps only raw sections",
           [s["compressed"] for m in excluded["segments"][0]["modules"]
            for s in m["sections"]], [False, False])
        ok("memmap --exclude-compressed count",
           excluded["segments"][0]["counts"]["skipped_compressed"], 2)
        ok("memmap --exclude-compressed section count",
           excluded["segments"][0]["counts"]["sections"], 2)

        # The report must go into rommap.py unchanged (C-559).
        rommap_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "l3_harness", "rommap.py")
        if os.path.exists(rommap_path):
            if os.path.dirname(rommap_path) not in sys.path:
                sys.path.insert(0, os.path.dirname(rommap_path))
            import rommap
            doc = rommap.convert(mm, skip_compressed=True)
            ok("memmap -> rommap.validate", rommap.validate(doc), [])
            ok("memmap -> rommap blocks",
               [b["name"] for b in doc["blocks"]],
               ["NK.EXE/sec0", "NAVI.EXE/sec0"])
            ok("memmap -> rommap address/size",
               [(b["address"], b["size"]) for b in doc["blocks"]],
               [("0x8ce01000", 0x400), ("0x8d001000", 0x200)])
            ok("memmap -> rommap permissions",
               [b["permissions"] for b in doc["blocks"]], ["rw-", "r-x"])
            ok("memmap -> rommap skipped compressed", len(doc["skipped"]), 2)
            try:
                rommap.convert(mm)
            except rommap.RommapError as exc:
                ok("rommap rejects compressed by default",
                   any("compressed" in p for p in exc.problems), True)
            else:
                raise AssertionError("rommap.convert() mapped a compressed section")
        else:
            ok("memmap section schema keys (rommap.py absent)", sorted(mod0[0]),
               ["characteristics", "compressed", "file_offset", "name", "rwx",
                "size", "va", "vsize"])

        # CLI: JSON file, --pretty, alias, script and the module-filter error.
        out_json = os.path.join(td, "memmap.json")
        out_script = os.path.join(td, "map_rom.py")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli memmap exit", main([path, "memmap", "--modules", "NAVI.EXE,NK.EXE",
                                        "--out", out_json, "--pretty",
                                        "--ghidra-script", out_script]), 0)
        ok("cli memmap summary", "section(s)" in buf.getvalue(), True)
        with open(out_json, "r", encoding="utf-8") as fh:
            written = json.load(fh)
        ok("cli memmap file module order",
           [m["name"] for m in written["segments"][0]["modules"]], ["NK.EXE", "NAVI.EXE"])
        ok("cli memmap file blocks",
           sum(len(m["sections"]) for m in written["segments"][0]["modules"]), 4)

        with open(out_script, "r", encoding="utf-8") as fh:
            script = fh.read()
        ok("ghidra script uses createMemoryBlock", "createMemoryBlock" in script, True)
        ok("ghidra script image path", repr(os.path.abspath(path)) in script, True)
        ok("ghidra script maps raw sections only",
           ("('NK.EXE/sec0'" in script) and ("('NK.EXE/sec1'" not in script), True)
        ok("ghidra script lists omitted compressed",
           "Omitted compressed sections: NK.EXE/sec1, NAVI.EXE/sec1" in script, True)
        ok("ghidra script block count", script.count("\n    ('"), 2)

        alias_json = os.path.join(td, "alias.json")
        with contextlib.redirect_stdout(io.StringIO()):
            ok("cli ghidra alias exit", main([path, "ghidra", "--out", alias_json]), 0)
        with open(alias_json, "r", encoding="utf-8") as fh:
            ok("cli ghidra alias matches memmap",
               json.load(fh)["segments"][0]["counts"], seg["counts"])

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ok("cli memmap unknown module exit",
               main([path, "memmap", "--modules", "Nope.dll"]), 2)
        ok("cli memmap unknown module message", "Nope.dll" in err.getvalue(), True)


        # Negative control: a corrupt ECEC must fail loudly, never guess.
        bad = bytearray(rom)
        bad[exp["image_start"] + 0x40:exp["image_start"] + 0x44] = b"XXXX"
        with open(os.path.join(td, "corrupt.img"), "wb") as fh:
            fh.write(bad)
        for label, kwargs in (("corrupt ECEC (explicit start)", {"image_start": exp["image_start"]}),
                              ("corrupt ECEC (discovery)", {})):
            try:
                CERom(bytes(bad), **kwargs)
            except ValueError as exc:
                ok(label, "ECEC" in str(exc), True)
            else:
                raise AssertionError("%s: CERom() accepted a corrupt image" % label)

    print("cerom selftest: %d checks OK (synthetic ROM, no vendor data)" % len(checks))
    return 0


def memmap_command(args, cerom, data):
    """Run ``memmap``/``ghidra``: write the JSON and the optional script."""
    modules = None
    if args.modules:
        modules = [name.strip() for name in args.modules.split(",") if name.strip()]
        if not modules:
            print("error: --modules names no module", file=sys.stderr)
            return 2

    image_size = os.path.getsize(args.image)
    try:
        report = build_memmap_report(
            cerom, args.image, image_size, hashlib.sha256(data).hexdigest(),
            modules=modules, exclude_compressed=args.exclude_compressed,
            sha256_scope=sha256_scope_text(len(data), image_size))
    except KeyError as exc:
        print("error: no module named %s in this ROM" % exc.args[0], file=sys.stderr)
        return 2
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1

    text = json.dumps(report, indent=2 if args.pretty else None) + "\n"
    counts = report["segments"][0]["counts"]
    summary = ("%d module(s), %d section(s), %d compressed"
               % (counts["modules"], counts["sections"], counts["compressed"]))
    if counts["skipped_compressed"]:
        summary += ", %d compressed omitted" % counts["skipped_compressed"]
    if args.out:
        directory = os.path.dirname(os.path.abspath(args.out))
        os.makedirs(directory, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
        print("wrote %s (%s)" % (args.out, summary))
    else:
        sys.stdout.write(text)

    if args.ghidra_script:
        mapped = write_ghidra_script(args.ghidra_script, args.image, report)
        print("wrote %s (%d block(s))" % (args.ghidra_script, mapped))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?", help="raw image (or at least its first ~32 MiB)")
    ap.add_argument("--image-start", type=lambda s: int(s, 0), default=None)
    ap.add_argument("--selftest", action="store_true",
                    help="run the synthetic-ROM self-test and exit (needs no image)")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("romhdr")
    sub.add_parser("modules")
    sub.add_parser("files")
    p = sub.add_parser("sections"); p.add_argument("module")
    p = sub.add_parser("exports"); p.add_argument("module")
    p = sub.add_parser("imports"); p.add_argument("module")
    p = sub.add_parser("va2file"); p.add_argument("va", type=lambda s: int(s, 0))
    p = sub.add_parser("file2va"); p.add_argument("off", type=lambda s: int(s, 0))
    p = sub.add_parser("extract"); p.add_argument("module"); p.add_argument("-o", required=True)
    p = sub.add_parser("memmap", aliases=["ghidra"],
                       help="memory-map JSON for rommap.py (alias: ghidra)")
    p.add_argument("--modules", help="comma-separated module names (default: all)")
    p.add_argument("--out", help="write the JSON here (default: stdout)")
    p.add_argument("--pretty", action="store_true", help="indent the JSON")
    p.add_argument("--exclude-compressed", action="store_true",
                   help="omit IMAGE_SCN_COMPRESSED sections and report the count")
    p.add_argument("--ghidra-script", metavar="FILE",
                   help="also write a Ghidra Jython script mapping the same blocks")
    a = ap.parse_args(argv)

    if a.selftest:
        return selftest()
    if a.image is None:
        ap.error("the following arguments are required: image")
    if a.cmd is None:
        ap.error("a subcommand is required (romhdr, modules, files, sections, exports, "
                 "va2file, file2va, extract, memmap)")

    with open(a.image, "rb") as fh:
        data = fh.read(128 << 20)
    r = CERom(data, a.image_start)

    if a.cmd in ("memmap", "ghidra"):
        return memmap_command(a, r, data)
    if a.cmd == "romhdr":
        print("image_start  0x%08x" % r.start)
        print("va_base      0x%08x" % r.va_base)
        print("pTOC         0x%08x  (ROMHDR at file 0x%08x)" % (r.ptoc, r.hdr_off))
        for k, v in r.hdr.items():
            print("%-15s 0x%08x" % (k, v))
    elif a.cmd == "modules":
        for m in r.modules():
            e = r.e32(m)
            print("%3d %-28s attr=%04x size=%8d load=%08x vbase=%08x objs=%d"
                  % (m["index"], m["name"], m["attrib"], m["size"], m["load"], e["vbase"], e["objcnt"]))
    elif a.cmd == "files":
        for f in r.files():
            print("%3d %-28s attr=%04x real=%8d comp=%8d load=%08x (file 0x%08x)"
                  % (f["index"], f["name"], f["attrib"], f["rsize"], f["csize"], f["load"], r.va2file(f["load"])))
    elif a.cmd == "sections":
        m = r.module(a.module)
        e = r.e32(m)
        print("%s: vbase=%08x vsize=%08x entry=%08x export=%08x+%x import=%08x+%x"
              % (m["name"], e["vbase"], e["vsize"], e["vbase"] + e["entryrva"],
                 e["export"][0], e["export"][1], e["imp"][0], e["imp"][1]))
        for s in r.o32(m):
            print("  rva=%08x vsize=%08x psize=%08x dataptr=%08x (file 0x%08x) realaddr=%08x flags=%08x%s"
                  % (s["rva"], s["vsize"], s["psize"], s["dataptr"], r.va2file(s["dataptr"]),
                     s["realaddr"], s["flags"], " COMPRESSED" if s["flags"] & IMAGE_SCN_COMPRESSED else ""))
    elif a.cmd == "exports":
        for ordinal, name, rva in sorted(r.exports(r.module(a.module))):
            print("%5d %-40s rva=%08x" % (ordinal, name, rva))
    elif a.cmd == "imports":
        for dll, slot, nm, ordn in r.imports(r.module(a.module)):
            print("%-20s slot=%08x %s" % (dll, slot, nm if nm is not None else "#%d" % ordn))
    elif a.cmd == "va2file":
        print("0x%08x" % r.va2file(a.va))
    elif a.cmd == "file2va":
        print("0x%08x" % r.file2va(a.off))
    elif a.cmd == "extract":
        m = r.module(a.module)
        os.makedirs(a.o, exist_ok=True)
        for s in r.o32(m):
            o = r.va2file(s["dataptr"])
            n = os.path.join(a.o, "%s.%08x.bin" % (m["name"], s["realaddr"]))
            with open(n, "wb") as fh:
                fh.write(data[o:o + s["psize"]])
            print(n, "COMPRESSED" if s["flags"] & IMAGE_SCN_COMPRESSED else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
