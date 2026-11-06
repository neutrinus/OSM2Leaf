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
  cerom.py IMG files [--extract DIR] [--decompress]
                      [--method auto|lzss|lzx] [--json]
  cerom.py IMG sections MODULE
  cerom.py IMG exports MODULE
  cerom.py IMG va2file VA
  cerom.py IMG file2va OFFSET
  cerom.py IMG extract MODULE -o DIR   # raw o32 sections, uncompressed only
  cerom.py IMG memmap [--modules M1,M2] [--out FILE] [--pretty]
                      [--exclude-compressed] [--ghidra-script FILE]
  cerom.py IMG ghidra ...              # alias of memmap
  cerom.py IMG decompress [--modules M1,M2] [--section NAME]
                          [--method auto|lzss|lzx] [--out DIR]
                          [--check] [--json]
  cerom.py IMG comphdr MODULE | --all [--json]
  cerom.py IMG thunks [MODULE | --all] [--json] [--min-coverage N]
  cerom.py --selftest                  # synthetic ROM, no vendor data

``memmap`` emits the section table ``tools/l3_harness/rommap.py`` consumes:
one block per ``o32_rom`` record of the selected modules, at ``o32_realaddr``,
with the bytes at ``p2f(o32_dataptr)``.  ``size`` is ``o32_psize`` (the stored
extent); ``vsize`` (the runtime extent) and ``rwx`` are extra keys.  Compressed
sections (``IMAGE_SCN_COMPRESSED``, 0x2000) are always flagged and are never
written out as raw section bytes; ``--exclude-compressed`` drops them from the
JSON and reports the count instead.  ``--ghidra-script`` additionally writes a
small Jython script that maps the same blocks with ``createMemoryBlock``.

``decompress`` is the M1.3 counterpart: it walks every ``o32_rom`` record with
``IMAGE_SCN_COMPRESSED`` in every discovered CE segment (builds A/B are stored
twice; the copy is reported once and not walked again) and passes exactly
``o32_psize`` stored bytes to ``tools/cecompress.py`` with
``expected_size=o32_vsize``.  Each section is classified ``OK`` (decoded length
equals ``vsize``), ``UNSUPPORTED`` (codec or block type not implemented) or
``FAIL`` (decode error); the record keeps module, section name, rva, vsize,
psize, a SHA-256 with its scope (``decoded`` or ``stored``) and the first
error.  Compressed bytes are never written as section data: only an ``OK``
decode produces ``<module>.<rva>.bin`` (under ``DIR/seg<N>/`` when more than
one segment is walked).  ``--check`` writes nothing.  Exit codes: 0 when every
requested section is ``OK``, 1 when some are ``UNSUPPORTED``/``FAIL``, 2 on a
usage or I/O error.

``comphdr`` parses the hypothesised 22-byte compressed-section header of
M1.2a (``u24 uncompressed_len``, ``u24 compressed_total``, ``u32 flags``,
``u32 uncompressed_len``, ``u32 payload_len``, ``u32 uncompressed_len``,
payload at +22) and validates it per section: ``compressed_total == psize``,
``payload_len == psize - 22``, the three length words equal, ``flags == 0x10``
and ``uncompressed_len <= vsize``.  A section is ``HOLDS`` when every check
passes, ``REFUTED`` when the header parses but a check fails, and ``UNPARSED``
when there are fewer than 22 stored bytes or the bytes lie outside the image.
``MODULE`` selects one module (case-insensitive, in every segment); ``--all``
walks every ``IMAGE_SCN_COMPRESSED`` section.  Exit codes: 0 when every parsed
section ``HOLDS``, 1 when any is ``REFUTED``/``UNPARSED``, 2 on a usage or I/O
error.

``thunks`` resolves the import stubs of every selected module (M1.6b).  A
stub is the EXP-50 pattern ``mov.l @(disp,PC),Rn; mov.l @Rn,R0; jmp @R0; nop``
or the direct variant ``mov.l @(disp,PC),Rn; jmp @Rn`` (with or without a
delay-slot ``nop``); only uncompressed code sections
(``CNT_CODE``/``MEM_EXECUTE``) are scanned, and a stub's VA is its section
``realaddr`` plus the offset.  The literal the stub loads is the process VA of
an IAT slot; the slot is resolved through the importing module's
OriginalFirstThunk (``imports``) and the exporting module's export table, so a
record names ``module!export`` and its ordinal, not a raw VA.  ``--all`` walks
every module of every discovered segment.  ``confidence`` is ``high`` (EXP-50
pattern plus an export-table confirmation), ``medium`` (EXP-50 pattern without
that confirmation, or the 3-instruction variant confirmed) or ``low`` (the
2-instruction variant, or unresolved).  Unresolved stubs keep their ``slot_va``
and carry the reason: ``slot outside image``, ``no export match`` or
``ambiguous duplicate (…)``.  Coverage is printed as ``resolved/total`` with a
percentage: stub coverage (named stubs over detected stubs) and slot coverage
(import slots that have at least one stub, over all import slots — the M1.6b
measure of "846 slots have a stub").  ``--min-coverage N`` exits 1 when either
coverage is below ``N`` percent; without it the exit code is 0 once the report
is produced.  Exit codes: 0 report produced, 1 coverage below
``--min-coverage``, 2 on a usage or I/O error.

``files`` lists the ``FILESentry`` table; the default text view is unchanged.
``--extract DIR`` also writes the stored ``csize`` bytes of every entry whose
``csize != rsize`` as ``<name>.<index>.stored.bin``.  ``--decompress`` passes
those bytes to ``tools/cecompress.py`` with ``expected_size=rsize`` under
``--method auto|lzss|lzx`` and classifies the entry ``OK`` (decoded length ==
``rsize``, written as ``<name>.<index>.bin``), ``UNSUPPORTED`` (codec or block
type not implemented) or ``FAIL`` (empty, out-of-image or undecodable payload);
a decode whose length differs from ``rsize`` is refused and never written.  An
entry with ``csize == rsize`` is ``UNCOMPRESSED`` (nothing extracted) and one
whose stored bytes were written without ``--decompress`` is ``STORED``.
``--json`` emits one record per entry with the stable keys ``index, name,
attrib, rsize, csize, load, status, method_used, output_size, sha256, error``
(``sha256`` always covers the stored bytes).  EXP-2026-11-05-51 showed that the
real compressed ``FILESentry`` payloads are not a stdlib format, so what the
real image decodes to with this classifier remains UNKNOWN.  Exit codes: 0 when
what was asked for succeeded, 1 when a requested decode is
``UNSUPPORTED``/``FAIL`` or an ``--extract`` entry could not be written, 2 on a
usage or I/O error.

See docs/experiments/EXP-2026-11-05-47-cerom-selftest.md,
docs/experiments/EXP-2026-11-05-48-cerom-memmap.md,
docs/experiments/EXP-2026-11-05-53-cerom-decompress.md,
docs/experiments/EXP-2026-11-05-55-filesentry-extract.md,
docs/experiments/EXP-2026-11-05-M1.2a-comphdr.md and
docs/experiments/EXP-2026-11-05-M1.6b-thunks.md.
"""
import argparse
import array
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
COMPHDR_SIZE = 22
COMPHDR_FLAGS = 0x10
IMAGE_SCN_COMPRESSED = 0x00002000
CNT_CODE = 0x00000020
CNT_UNINITIALIZED_DATA = 0x00000080
MEM_EXECUTE = 0x20000000
MEM_READ = 0x40000000
MEM_WRITE = 0x80000000

MEMMAP_SCHEMA = "osm2leaf.cerom.memmap/v1"
MEMMAP_GENERATOR = "tools/cerom.py memmap"
DECOMPRESS_SCHEMA = "osm2leaf.cerom.decompress/v1"
DECOMPRESS_GENERATOR = "tools/cerom.py decompress"
COMPHDR_SCHEMA = "osm2leaf.cerom.comphdr/v1"
COMPHDR_GENERATOR = "tools/cerom.py comphdr"
FILES_SCHEMA = "osm2leaf.cerom.files/v1"
FILES_GENERATOR = "tools/cerom.py files"
THUNKS_SCHEMA = "osm2leaf.cerom.thunks/v1"
THUNKS_GENERATOR = "tools/cerom.py thunks"
THUNKS_RECORD_KEYS = ("stub_va", "slot_va", "module", "export", "ordinal",
                      "section", "confidence", "status", "reason", "pattern",
                      "owner", "segment")
THUNKS_PATTERN_RANK = {"4-insn": 2, "inlined": 2, "3-insn": 1, "2-insn": 0}
FILES_RECORD_KEYS = ("index", "name", "attrib", "rsize", "csize", "load",
                     "status", "method_used", "output_size", "sha256", "error")
SEGMENT_MAX_MODULES = 4096


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
        off = va - self.va_base + self.start
        if 0 <= off < len(self.d):
            return off
        # Fall back to module section realaddr mapping (module-local VAs,
        # e.g. Navi.exe realaddr 0x00011000, are not in ROM VA space).
        if not getattr(self, "_in_realaddr", False):
            self._in_realaddr = True
            try:
                mapped = self.realaddr2file(va)
            finally:
                self._in_realaddr = False
            if mapped is not None:
                return mapped
        return off

    def realaddr2file(self, va):
        """File offset of a process VA by scanning o32 realaddr ranges.

        Works for module-local VAs (realaddr/vbase space) where ROM-linear
        va2file does not apply.  Returns None when unmapped or in a
        compressed section (stored bytes are not the section contents).
        """
        for mod in self.modules():
            try:
                secs = list(self.o32(mod))
            except (struct.error, ValueError):
                continue
            for sec in secs:
                if sec["flags"] & IMAGE_SCN_COMPRESSED:
                    continue
                if not sec["psize"]:
                    continue
                if sec["realaddr"] <= va < sec["realaddr"] + sec["psize"]:
                    dataptr_off = va - self.va_base + self.start
                    # dataptr is a ROM VA for stored sections
                    if not (0 <= dataptr_off < len(self.d)):
                        dataptr_off = None
                    # prefer dataptr-based mapping (matches stored bytes)
                    base_off = self._romptr2file(sec["dataptr"])
                    if base_off is not None:
                        off = base_off + (va - sec["realaddr"])
                        if 0 <= off < len(self.d):
                            return off
        return None

    def _romptr2file(self, va):
        off = va - self.va_base + self.start
        return off if 0 <= off < len(self.d) else None

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
# Compressed sections (`decompress`): `IMAGE_SCN_COMPRESSED` bodies decoded
# through tools/cecompress.py.  Which codec the image uses is still UNKNOWN
# (EXP-2026-11-05-49/52), so this command reports what happens per section
# instead of assuming one.
# --------------------------------------------------------------------------


def cecompress_module():
    """Import and return the sibling ``tools/cecompress.py`` module."""
    directory = os.path.dirname(os.path.abspath(__file__))
    if directory not in sys.path:
        sys.path.insert(0, directory)
    import cecompress
    return cecompress


def find_segments(data, image_start=None):
    """Return ``(segments, duplicates)`` for every valid CE segment in ``data``.

    A candidate is accepted only when ``ECEC`` sits at ``start + 0x40`` and the
    ``ROMHDR`` it points at is self-consistent: ``physfirst <= pTOC < physlast``,
    ``0 < nummods <= 4096`` and a TOC that ends inside the bytes read.  Builds A
    and B are each stored twice; a copy (same ``pTOC``, ``physfirst``,
    ``physlast``, ``nummods`` and ``numfiles``) is listed once under
    ``duplicates`` instead of being walked again.
    """
    if image_start is None:
        candidates = []
        found = 0
        while True:
            found = data.find(b"ECEC", found)
            if found < 0:
                break
            if found >= 0x40 and (found - 0x40) not in candidates:
                candidates.append(found - 0x40)
            found += 1
    else:
        candidates = [image_start]

    segments, keys, duplicates = [], [], []
    for start in candidates:
        try:
            segment = CERom(data, start)
        except (ValueError, struct.error):
            continue
        header = segment.hdr
        if not 0 < header["nummods"] <= SEGMENT_MAX_MODULES:
            continue
        if not header["physfirst"] <= segment.ptoc < header["physlast"]:
            continue
        toc_end = (segment.hdr_off + ROMHDR_SIZE + TOC_SIZE * header["nummods"]
                   + FILES_SIZE * header["numfiles"])
        if toc_end > len(data):
            continue
        key = (segment.ptoc, header["physfirst"], header["physlast"],
               header["nummods"], header["numfiles"])
        if key in keys:
            duplicates.append({"segment_base": hx(start),
                               "duplicate_of": keys.index(key)})
            continue
        keys.append(key)
        segments.append(segment)
    if not segments:
        if image_start is not None:
            raise ValueError("no valid CE segment at image_start 0x%x" % image_start)
        raise ValueError("no valid CE segment found in %d bytes" % len(data))
    return segments, duplicates


def section_selector(text):
    """Return a matcher for ``--section``: ``secN``, ``MODULE/secN`` or an RVA.

    The matcher takes ``(module_name, section_index, section_rva)``.  A bare
    number is an RVA only in hex form (``0x2000``); section indexes need the
    ``sec`` prefix so the two readings never collide.
    """
    raw = text.strip()
    if not raw:
        raise ValueError("--section names nothing")
    module = None
    name = raw
    if "/" in raw:
        module, name = (part.strip() for part in raw.split("/", 1))
        if not module or not name:
            raise ValueError("--section %r needs MODULE/secN or secN" % text)
    lowered = name.lower()
    if lowered.startswith("sec") and lowered[3:].isdigit():
        index = int(lowered[3:])

        def matches_index(module_name, section_index, section_rva):
            return ((module is None or module_name.lower() == module.lower())
                    and section_index == index)

        return matches_index
    try:
        rva = int(name, 0)
    except ValueError:
        raise ValueError(
            "--section %r is not sec<N>, MODULE/sec<N> or an RVA" % text) from None

    def matches_rva(module_name, section_index, section_rva):
        return ((module is None or module_name.lower() == module.lower())
                and section_rva == rva)

    return matches_rva


def section_out_dir(out_dir, segment_index, segment_count):
    """Per-segment subdirectory only when more than one segment is walked."""
    if segment_count > 1:
        return os.path.join(out_dir, "seg%d" % segment_index)
    return out_dir


def decompress_report(data, image_name, image_size=None, image_sha256=None,
                      sha256_scope=None, modules=None, section=None,
                      method="auto", out_dir=None, check=True, image_start=None):
    """Classify the decode of every compressed ``o32`` section.

    ``check`` (or a missing ``out_dir``) writes nothing.  Only an ``OK`` decode
    is written, as ``<module>.<rva>.bin``; a section whose stored range is
    empty/outside the image, whose codec is not implemented or whose decode
    fails is recorded and never written.  The document is stable JSON: every
    section record carries the same keys whatever its status.
    """
    cc = cecompress_module()
    method = cc.normalise_method(method)
    segments, duplicates = find_segments(data, image_start)

    wanted = None
    if modules:
        available = set()
        for segment in segments:
            for module in segment.modules():
                if module["name"]:
                    available.add(module["name"].lower())
        missing = [name for name in modules if name.lower() not in available]
        if missing:
            raise KeyError(missing[0])
        wanted = {name.lower() for name in modules}

    write = bool(out_dir) and not check
    if write:
        out_dir = os.path.abspath(out_dir)
    records, errors = [], []
    for segment_index, segment in enumerate(segments):
        for module in segment.modules():
            name = module["name"]
            if not name:
                continue
            if wanted is not None and name.lower() not in wanted:
                continue
            try:
                sections = list(segment.o32(module))
            except struct.error as exc:
                errors.append({"segment": segment_index, "module": name,
                               "error_type": "struct.error",
                               "error": str(exc)})
                continue
            for index, sec in enumerate(sections):
                if not sec["flags"] & IMAGE_SCN_COMPRESSED:
                    continue
                if section is not None and not section(name, index, sec["rva"]):
                    continue
                record = {
                    "segment": segment_index,
                    "module": name,
                    "section": "sec%d" % index,
                    "rva": hx(sec["rva"]),
                    "vsize": sec["vsize"],
                    "psize": sec["psize"],
                    "flags": hx(sec["flags"]),
                    "file_offset": None,
                    "status": None,
                    "method": method,
                    "method_used": None,
                    "detected": None,
                    "output_size": None,
                    "sha256": None,
                    "sha256_scope": None,
                    "out": None,
                    "error_type": None,
                    "error": None,
                }
                offset = segment.va2file(sec["dataptr"])
                record["file_offset"] = offset
                blob = None
                if not sec["psize"]:
                    record["status"] = "FAIL"
                    record["error_type"] = "EmptySection"
                    record["error"] = ("IMAGE_SCN_COMPRESSED with psize 0: "
                                       "nothing stored to decode")
                elif not (0 <= offset and offset + sec["psize"] <= len(data)):
                    record["status"] = "FAIL"
                    record["error_type"] = "RangeError"
                    record["error"] = (
                        "stored bytes 0x%x..0x%x lie outside the image (%d bytes)"
                        % (offset, offset + sec["psize"], len(data)))
                else:
                    payload = data[offset:offset + sec["psize"]]
                    record["sha256"] = hashlib.sha256(payload).hexdigest()
                    record["sha256_scope"] = "stored"
                    try:
                        blob, info = cc.decompress_info(
                            payload, sec["vsize"], method)
                    except cc.UnsupportedFormat as exc:
                        record["status"] = "UNSUPPORTED"
                        record["error_type"] = type(exc).__name__
                        record["error"] = str(exc)
                    except cc.CeCompressError as exc:
                        record["status"] = "FAIL"
                        record["error_type"] = type(exc).__name__
                        record["error"] = str(exc)
                    except Exception as exc:  # noqa: BLE001 - one bad section must not stop the walk
                        record["status"] = "FAIL"
                        record["error_type"] = type(exc).__name__
                        record["error"] = str(exc)
                    else:
                        record["status"] = "OK"
                        record["method_used"] = info.get("method")
                        record["detected"] = info.get("detected") or None
                        record["output_size"] = len(blob)
                        record["sha256"] = hashlib.sha256(blob).hexdigest()
                        record["sha256_scope"] = "decoded"
                if record["status"] == "OK" and write:
                    directory = section_out_dir(out_dir, segment_index, len(segments))
                    os.makedirs(directory, exist_ok=True)
                    path = os.path.join(directory,
                                        "%s.%08x.bin" % (name, sec["rva"]))
                    with open(path, "wb") as handle:
                        handle.write(blob)
                    record["out"] = path
                records.append(record)

    counts = {"sections": len(records), "ok": 0, "unsupported": 0, "fail": 0,
              "errors": len(errors)}
    for record in records:
        counts[record["status"].lower()] += 1

    segment_records = []
    for index, segment in enumerate(segments):
        segment_records.append({
            "segment_index": index,
            "segment_base": hx(segment.start),
            "phys_base": hx(segment.hdr["physfirst"]),
            "pTOC": hx(segment.ptoc),
            "nummods": segment.hdr["nummods"],
            "numfiles": segment.hdr["numfiles"],
        })
    return {
        "schema": DECOMPRESS_SCHEMA,
        "generator": DECOMPRESS_GENERATOR,
        "image": os.path.basename(image_name),
        "image_size": image_size,
        "image_sha256": image_sha256,
        "image_sha256_scope": sha256_scope,
        "method": method,
        "check": not write,
        "out_dir": out_dir if write else None,
        "segments": segment_records,
        "duplicate_segments": duplicates,
        "counts": counts,
        "errors": errors,
        "sections": records,
    }


def print_decompress_text(report):
    """Print one line per section plus a summary (the non-``--json`` view)."""
    for record in report["sections"]:
        label = "%s/%s" % (record["module"], record["section"])
        line = ("%-11s %-34s rva=%s vsize=0x%x psize=0x%x"
                % (record["status"], label, record["rva"],
                   record["vsize"], record["psize"]))
        if record["sha256"]:
            line += " %s=%s" % (record["sha256_scope"], record["sha256"])
        if record["out"]:
            line += " -> %s" % record["out"]
        if record["error"]:
            line += " error=%s" % record["error"]
        print(line)
    for error in report["errors"]:
        print("module error: %s (segment %d): %s: %s"
              % (error["module"], error["segment"], error["error_type"],
                 error["error"]))
    counts = report["counts"]
    summary = ("%d compressed section(s) in %d segment(s): %d OK, "
               "%d UNSUPPORTED, %d FAIL"
               % (counts["sections"], len(report["segments"]), counts["ok"],
                  counts["unsupported"], counts["fail"]))
    written = sum(1 for record in report["sections"] if record["out"])
    if written:
        summary += ", %d file(s) written" % written
    elif report["check"]:
        summary += ", nothing written (check)"
    print(summary)
    if report["duplicate_segments"]:
        print("%d duplicate segment copy/copies not walked: %s"
              % (len(report["duplicate_segments"]),
                 ", ".join("0x%x" % int(d["segment_base"], 16)
                           for d in report["duplicate_segments"])))


# --------------------------------------------------------------------------
# Compressed-section header (`comphdr`): the 22-byte layout M1.2a tests.
# --------------------------------------------------------------------------


def u24le(blob, offset):
    """Little-endian 24-bit unsigned integer at ``offset``."""
    return blob[offset] | (blob[offset + 1] << 8) | (blob[offset + 2] << 16)


def parse_comphdr(blob):
    """Parse the hypothesised 22-byte compressed-section header.

    Layout, all little-endian: ``u24 uncompressed_len``, ``u24
    compressed_total``, ``u32 flags``, ``u32 uncompressed_len``, ``u32
    payload_len``, ``u32 uncompressed_len``; the payload starts at +22.  The
    repeated length words are kept apart (``len_u24``/``len_a``/``len_b``) so a
    disagreement is visible instead of hidden by the parse.  Returns ``None``
    when fewer than 22 bytes are available.
    """
    if blob is None or len(blob) < COMPHDR_SIZE:
        return None
    return {
        "len_u24": u24le(blob, 0),
        "compressed_total": u24le(blob, 3),
        "flags": struct.unpack_from("<I", blob, 6)[0],
        "len_a": struct.unpack_from("<I", blob, 10)[0],
        "payload_len": struct.unpack_from("<I", blob, 14)[0],
        "len_b": struct.unpack_from("<I", blob, 18)[0],
        "payload_offset": COMPHDR_SIZE,
    }


COMPHDR_CHECK_LABELS = {
    "compressed_total_is_psize": "compressed_total == psize",
    "payload_len_is_psize_minus_22": "payload_len == psize - 22",
    "lengths_agree": "uncompressed_len words agree",
    "flags_is_0x10": "flags == 0x10",
    "uncompressed_len_within_vsize": "uncompressed_len <= vsize",
}


def comphdr_checks(fields, psize, vsize):
    """Evaluate the M1.2a invariants; return ``(checks, failed_keys)``."""
    checks = {
        "compressed_total_is_psize": fields["compressed_total"] == psize,
        "payload_len_is_psize_minus_22":
            fields["payload_len"] == psize - COMPHDR_SIZE,
        "lengths_agree": fields["len_u24"] == fields["len_a"] == fields["len_b"],
        "flags_is_0x10": fields["flags"] == COMPHDR_FLAGS,
        "uncompressed_len_within_vsize": fields["len_u24"] <= vsize,
    }
    return checks, [name for name in checks if not checks[name]]


def classify_comphdr(blob, psize, vsize):
    """Parse and validate one stored compressed section.

    Returns the header half of a report record with stable keys whatever the
    verdict.  ``HOLDS`` means every invariant in ``COMPHDR_CHECK_LABELS``
    passed, ``REFUTED`` that the header parsed but a check failed, and
    ``UNPARSED`` that there was no 22-byte header to read.
    """
    record = {
        "verdict": "UNPARSED",
        "uncompressed_len": None,
        "compressed_total": None,
        "flags": None,
        "payload_len": None,
        "payload_offset": None,
        "within_vsize": None,
        "checks": None,
        "failed": [],
        "error": None,
    }
    if not psize:
        record["error"] = "IMAGE_SCN_COMPRESSED with psize 0: nothing stored"
        return record
    if psize < COMPHDR_SIZE:
        record["error"] = ("psize 0x%x is shorter than the %d-byte header"
                           % (psize, COMPHDR_SIZE))
        return record
    fields = parse_comphdr(blob)
    if fields is None:
        record["error"] = ("stored bytes shorter than the %d-byte header"
                           % COMPHDR_SIZE)
        return record
    checks, failed = comphdr_checks(fields, psize, vsize)
    record.update(
        verdict="HOLDS" if not failed else "REFUTED",
        uncompressed_len=fields["len_u24"],
        compressed_total=fields["compressed_total"],
        flags=hx(fields["flags"]),
        payload_len=fields["payload_len"],
        payload_offset=fields["payload_offset"],
        within_vsize=checks["uncompressed_len_within_vsize"],
        checks=checks,
        failed=failed,
    )
    return record


def comphdr_report(data, image_name, image_size=None, image_sha256=None,
                   sha256_scope=None, module=None, all_sections=False,
                   image_start=None):
    """Parse the 22-byte header of every selected compressed ``o32`` section.

    ``module`` selects one module by name (case-insensitive, in every segment);
    ``all_sections`` walks every ``IMAGE_SCN_COMPRESSED`` section instead.  A
    section whose stored range is empty, shorter than the header or outside the
    image is ``UNPARSED`` and carries the reason.  ``counts["exceptions"]`` is
    the number of sections that did not ``HOLDS``.
    """
    segments, duplicates = find_segments(data, image_start)

    if not all_sections:
        if not module:
            raise ValueError("comphdr needs a module name or --all")
        available = set()
        for segment in segments:
            for entry in segment.modules():
                if entry["name"]:
                    available.add(entry["name"].lower())
        if module.lower() not in available:
            raise KeyError(module)

    records, errors = [], []
    for segment_index, segment in enumerate(segments):
        for entry in segment.modules():
            name = entry["name"]
            if not name:
                continue
            if not all_sections and name.lower() != module.lower():
                continue
            try:
                sections = list(segment.o32(entry))
            except struct.error as exc:
                errors.append({"segment": segment_index, "module": name,
                               "error_type": "struct.error",
                               "error": str(exc)})
                continue
            for index, sec in enumerate(sections):
                if not sec["flags"] & IMAGE_SCN_COMPRESSED:
                    continue
                offset = segment.va2file(sec["dataptr"])
                record = {
                    "segment": segment_index,
                    "module": name,
                    "section": "sec%d" % index,
                    "rva": hx(sec["rva"]),
                    "vsize": sec["vsize"],
                    "psize": sec["psize"],
                    "file_offset": offset,
                }
                if sec["psize"] and not (
                        0 <= offset and offset + sec["psize"] <= len(data)):
                    record.update(classify_comphdr(None, sec["psize"], sec["vsize"]))
                    record["error"] = (
                        "stored bytes 0x%x..0x%x lie outside the image (%d bytes)"
                        % (offset, offset + sec["psize"], len(data)))
                else:
                    blob = (data[offset:offset + sec["psize"]]
                            if sec["psize"] else None)
                    record.update(classify_comphdr(blob, sec["psize"], sec["vsize"]))
                records.append(record)

    counts = {"sections": len(records), "holds": 0, "refuted": 0, "unparsed": 0,
              "exceptions": 0, "errors": len(errors)}
    for record in records:
        counts[record["verdict"].lower()] += 1
    counts["exceptions"] = counts["refuted"] + counts["unparsed"]

    segment_records = []
    for index, segment in enumerate(segments):
        segment_records.append({
            "segment_index": index,
            "segment_base": hx(segment.start),
            "phys_base": hx(segment.hdr["physfirst"]),
            "pTOC": hx(segment.ptoc),
            "nummods": segment.hdr["nummods"],
            "numfiles": segment.hdr["numfiles"],
        })
    return {
        "schema": COMPHDR_SCHEMA,
        "generator": COMPHDR_GENERATOR,
        "image": os.path.basename(image_name),
        "image_size": image_size,
        "image_sha256": image_sha256,
        "image_sha256_scope": sha256_scope,
        "scope": "all" if all_sections else module,
        "header_size": COMPHDR_SIZE,
        "segments": segment_records,
        "duplicate_segments": duplicates,
        "counts": counts,
        "errors": errors,
        "sections": records,
    }


def print_comphdr_text(report):
    """Print one line per compressed section plus the exception count."""
    for record in report["sections"]:
        label = "%s/%s" % (record["module"], record["section"])
        line = ("%-8s %-34s rva=%s vsize=0x%x psize=0x%x"
                % (record["verdict"], label, record["rva"], record["vsize"],
                   record["psize"]))
        if record["verdict"] == "UNPARSED":
            line += " error=%s" % record["error"]
        else:
            line += (" uncompressed_len=0x%x compressed_total=0x%x flags=%s "
                     "payload_len=0x%x%s"
                     % (record["uncompressed_len"],
                        record["compressed_total"], record["flags"],
                        record["payload_len"],
                        "" if record["within_vsize"] else " OVER-VSIZE"))
            if record["failed"]:
                line += " failed=[%s]" % ", ".join(record["failed"])
        print(line)
    for error in report["errors"]:
        print("module error: %s (segment %d): %s: %s"
              % (error["module"], error["segment"], error["error_type"],
                 error["error"]))
    counts = report["counts"]
    summary = ("%d compressed section(s) in %d segment(s): %d HOLDS, "
               "%d REFUTED, %d UNPARSED (exceptions: %d)"
               % (counts["sections"], len(report["segments"]), counts["holds"],
                  counts["refuted"], counts["unparsed"], counts["exceptions"]))
    print(summary)
    if report["duplicate_segments"]:
        print("%d duplicate segment copy/copies not walked: %s"
              % (len(report["duplicate_segments"]),
                 ", ".join("0x%x" % int(d["segment_base"], 16)
                           for d in report["duplicate_segments"])))


# --------------------------------------------------------------------------
# Import stubs (`thunks`): the EXP-50 stub pattern -> module!export (M1.6b)
# --------------------------------------------------------------------------


def movl_pc_literal(addr, word):
    """Literal VA of ``mov.l @(disp,PC),Rn`` (``0xDnnn``), else None.

    SH-4 reads PC as the instruction address + 4 and clears the low two bits:
    ``((addr + 4) & ~3) + disp*4`` (same rule as ``tools/sh4xref.py``).
    """
    if word & 0xF000 != 0xD000:
        return None
    return ((addr + 4) & ~3) + (word & 0xFF) * 4


def stub_pattern(words, index):
    """Pattern name of the import stub whose first word is ``words[index]``.

    ``4-insn`` is the EXP-50 double-deref IAT stub
    (``mov.l @(disp,PC),Rn; mov.l @Rn,Rn; jmp @Rn; nop``), ``3-insn`` the
    direct ``mov.l @(disp,PC),Rn; jmp @Rn`` variant with its delay-slot
    ``nop`` and ``2-insn`` the variant without it.  ``Rn`` may be any
    register.  Returns None when the word does not start a stub.
    """
    total = len(words)
    first = words[index]
    if first & 0xF000 != 0xD000:
        return None
    reg = (first >> 8) & 0xF
    movl_at_rn = 0x6002 | (reg << 8) | (reg << 4)   # mov.l @Rn,Rn
    jmp_rn = 0x402B | (reg << 8)                      # jmp @Rn
    if (index + 3 < total and words[index + 1] == movl_at_rn
            and words[index + 2] == jmp_rn and words[index + 3] == 0x0009):
        return "4-insn"
    if index + 1 < total and words[index + 1] == jmp_rn:
        if index + 2 < total and words[index + 2] == 0x0009:
            return "3-insn"
        return "2-insn"
    return None


def _deref_call_window(words, index, load_reg, window=12):
    """True if a PC-rel load of ``load_reg`` at ``index`` is followed by an
    IAT deref+call: ``mov.l @load_reg,Rm`` then ``jmp/jsr @Rm`` within
    ``window`` instructions, allowing interleaved arg setup (conservative:
    stop if ``load_reg`` is overwritten by ``mov.l @(pc),load_reg``).
    Handles cross-register deref (Rm != load_reg).
    """
    total = len(words)
    limit = min(total, index + 1 + window)
    for j in range(index + 1, limit):
        w = words[j]
        # mov.l @load_reg, Rm ?  0x6 m (load_reg) 2
        if w & 0xF0FF == (0x6002 | (load_reg << 4)):
            call_reg = (w >> 8) & 0xF
            jmp_r = 0x402B | (call_reg << 8)
            jsr_r = 0x400B | (call_reg << 8)
            for k in range(j + 1, min(total, j + 1 + window)):
                wk = words[k]
                if wk == jmp_r or wk == jsr_r:
                    return "inlined-4", call_reg != load_reg
        # stop if load_reg overwritten by mov.l @(pc),load_reg
        if w & 0xFF00 == (0xD000 | (load_reg << 8)):
            break
    return None, False


def section_words(data, offset, size):
    """Little-endian ``u16`` view of ``size`` stored section bytes."""
    words = array.array("H")
    words.frombytes(data[offset:offset + (size & ~1)])
    if sys.byteorder != "little":
        words.byteswap()
    return words


def read_u32_va(cerom, data, va):
    """32-bit word stored at ``va`` in the image, or None when not stored."""
    offset = cerom.va2file(va)
    if 0 <= offset and offset + 4 <= len(data):
        return struct.unpack_from("<I", data, offset)[0]
    return None


def read_u32_realaddr(cerom, data, va, section):
    """32-bit word at process VA ``va`` in an uncompressed section's bytes.

    Uses ``section['realaddr']``/``dataptr`` mapping, so it works for
    module-local VAs (e.g. Navi.exe ``0x00011000``) where ROM-linear
    ``va2file`` does not apply.
    """
    base = section["realaddr"]
    if not (base <= va and va + 4 <= base + section["psize"]):
        return None
    file_off = cerom._romptr2file(section["dataptr"])
    if file_off is None:
        return None
    off = file_off + (va - base)
    if 0 <= off and off + 4 <= len(data):
        return struct.unpack_from("<I", data, off)[0]
    return None


def scan_section_stubs(cerom, data, section, index, import_slots=None):
    """Import stubs/call sites in one uncompressed code section.

    Detects (1) consecutive standalone stub patterns (4/3/2-insn) and (2)
    inlined IAT call sites: a PC-rel load of a known import slot followed
    within a window by ``mov.l @Rn,Rm; jmp/jsr @Rm`` (possibly with
    interleaved arg setup).  Inlined detection runs only when
    ``import_slots`` is provided; it catches imports that are not behind a
    standalone trampoline.

    Returns records with ``stub_va``, ``slot_va``, ``section``, ``pattern``.
    ``pattern`` is ``4-insn``/``3-insn``/``2-insn`` for standalone forms or
    ``inlined`` for call-site forms.  A candidate whose literal is not stored
    is skipped.
    """
    file_off = cerom._romptr2file(section["dataptr"])
    size = section["psize"]
    if file_off is None or not size or not (
            0 <= file_off and file_off + size <= len(data)):
        return []
    words = section_words(data, file_off, size)
    base = section["realaddr"]
    slot_set = set(import_slots) if import_slots else None
    stubs = []
    seen = set()  # (stub_va, slot_va) dedup
    for position, word in enumerate(words):
        if word & 0xF000 != 0xD000:
            continue
        stub_va = base + 2 * position
        lit_va = movl_pc_literal(stub_va, word)
        slot = read_u32_realaddr(cerom, data, lit_va, section)
        if slot is None:
            slot = read_u32_va(cerom, data, lit_va)
        if slot is None:
            continue

        pattern = stub_pattern(words, position)
        if pattern is not None:
            is_import = slot_set is not None and slot in slot_set
            # Keep 4-insn (EXP-50 IAT thunk form) always; keep 2/3-insn only
            # when they target a known import slot (suppresses non-IAT noise).
            if pattern == "4-insn" or is_import:
                key = (stub_va, slot)
                if key not in seen:
                    seen.add(key)
                    stubs.append({"stub_va": stub_va, "slot_va": slot,
                                  "section": "sec%d" % index, "pattern": pattern})
                continue
            # 2/3-insn non-import: skip noise, but still allow inlined check
            # below (won't trigger since not in slot_set).
            continue

        # Inlined IAT call: only for known import slots.
        if slot_set is not None and slot in slot_set:
            reg = (word >> 8) & 0xF
            kind, _cross = _deref_call_window(words, position, reg)
            if kind is not None:
                key = (stub_va, slot)
                if key not in seen:
                    seen.add(key)
                    stubs.append({"stub_va": stub_va, "slot_va": slot,
                                  "section": "sec%d" % index,
                                  "pattern": "inlined"})
    return stubs


def build_thunk_index(segment, segment_index=0):
    """Return ``(imports_at, exports_by_dll, module_names, errors)``.

    ``imports_at`` maps an IAT slot VA of this segment to the import entries
    that name it, ``exports_by_dll`` maps a lower-cased DLL name to its export
    table (``by_name`` / ``by_ordinal``) and ``module_names`` maps a lower-cased
    module name to the TOC spelling.  Kept per segment: builds A and B can map
    the same slot VA to different imports.
    """
    imports_at, exports_by_dll, module_names, errors = {}, {}, {}, []
    for entry in segment.modules():
        name = entry["name"]
        if not name:
            continue
        module_names.setdefault(name.lower(), name)
        try:
            exports = list(segment.exports(entry))
        except (struct.error, ValueError, TypeError, IndexError) as exc:
            exports = []
            errors.append({"segment": segment_index, "module": name,
                           "error_type": type(exc).__name__, "error": str(exc)})
        if exports:
            table = exports_by_dll.setdefault(name.lower(),
                                              {"by_name": {}, "by_ordinal": {}})
            for ordinal, export_name, _rva in exports:
                table["by_name"].setdefault(export_name, ordinal)
                table["by_ordinal"].setdefault(ordinal, export_name)
        try:
            imports = list(segment.imports(entry))
        except (struct.error, ValueError, TypeError, IndexError) as exc:
            imports = []
            errors.append({"segment": segment_index, "module": name,
                           "error_type": type(exc).__name__, "error": str(exc)})
        for dll, slot, import_name, ordinal in imports:
            record = {"dll": dll, "name": import_name, "ordinal": ordinal}
            bucket = imports_at.setdefault(slot, [])
            if record not in bucket:
                bucket.append(record)
    return imports_at, exports_by_dll, module_names, errors


def collect_exports(segment):
    """Return ``(exports_by_dll, module_names)`` for every module in ``segment``.

    ``exports_by_dll`` maps a lower-cased DLL/module name to
    ``{"display": name, "by_name": {name: ordinal}, "by_ordinal": {ordinal: name}}``.
    Modules with no export directory are still registered in ``module_names``
    (display spelling) but not in ``exports_by_dll``.  Errors from malformed
    modules are skipped: a resolver table is best-effort.
    """
    exports_by_dll, module_names = {}, {}
    for entry in segment.modules():
        name = entry["name"]
        if not name:
            continue
        module_names.setdefault(name.lower(), name)
        try:
            exports = list(segment.exports(entry))
        except (struct.error, ValueError, TypeError, IndexError):
            continue
        if not exports:
            continue
        table = exports_by_dll.setdefault(
            name.lower(), {"display": name, "by_name": {}, "by_ordinal": {}})
        table.setdefault("display", name)
        for ordinal, export_name, _rva in exports:
            table["by_name"].setdefault(export_name, ordinal)
            table["by_ordinal"].setdefault(ordinal, export_name)
    return exports_by_dll, module_names


def merge_export_tables(*tables):
    """Merge several ``exports_by_dll`` tables (earlier entries win per key)."""
    merged = {}
    for table in tables:
        for key, value in (table or {}).items():
            dest = merged.setdefault(
                key, {"display": value.get("display", key),
                      "by_name": {}, "by_ordinal": {}})
            dest.setdefault("display", value.get("display", key))
            for name, ordinal in value.get("by_name", {}).items():
                dest["by_name"].setdefault(name, ordinal)
            for ordinal, name in value.get("by_ordinal", {}).items():
                dest["by_ordinal"].setdefault(ordinal, name)
    return merged


def merge_module_names(*tables):
    merged = {}
    for table in tables:
        for key, value in (table or {}).items():
            merged.setdefault(key, value)
    return merged


def load_names_json(path):
    """Load a cross-image export-names DB.

    Accepted shapes:
      * ``{"modules": {"coredll.dll": {"1145": "_wfopen", ...}, ...}}``
      * ``{"coredll.dll": {"1145": "_wfopen"}, ...}``
      * a list of ``{"module"/"dll", "ordinal", "name"}`` records
    Returns ``(exports_by_dll, module_names)``.
    """
    with open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    exports_by_dll, module_names = {}, {}
    if isinstance(doc, dict) and "modules" in doc and isinstance(doc["modules"], dict):
        doc = doc["modules"]
    if isinstance(doc, list):
        items = []
        for rec in doc:
            mod = rec.get("module") or rec.get("dll")
            if mod and rec.get("name") is not None and rec.get("ordinal") is not None:
                items.append((mod, rec["ordinal"], rec["name"]))
        for mod, ordinal, name in items:
            key = mod.lower()
            module_names.setdefault(key, mod)
            table = exports_by_dll.setdefault(
                key, {"display": mod, "by_name": {}, "by_ordinal": {}})
            table.setdefault("display", mod)
            try:
                ordv = int(ordinal)
            except (TypeError, ValueError):
                continue
            table["by_name"].setdefault(name, ordv)
            table["by_ordinal"].setdefault(ordv, name)
        return exports_by_dll, module_names
    if isinstance(doc, dict):
        for mod, mapping in doc.items():
            key = mod.lower()
            module_names.setdefault(key, mod)
            table = exports_by_dll.setdefault(
                key, {"display": mod, "by_name": {}, "by_ordinal": {}})
            table.setdefault("display", mod)
            if not isinstance(mapping, dict):
                continue
            for ordk, name in mapping.items():
                try:
                    ordv = int(ordk)
                except (TypeError, ValueError):
                    continue
                if name is None:
                    continue
                table["by_name"].setdefault(str(name), ordv)
                table["by_ordinal"].setdefault(ordv, str(name))
    return exports_by_dll, module_names


def load_resolver_tables(data, resolve_starts, names_path=None):
    """Build merged cross-image export tables.

    ``resolve_starts`` is a list of ``--image-start`` offsets (ints) to load as
    additional CE segments from the same image bytes; ``names_path`` is an
    optional JSON names DB.  Returns ``(exports_by_dll, module_names)``.
    """
    tables, names = [], []
    for start in resolve_starts or []:
        seg = CERom(data, start)
        ex, mn = collect_exports(seg)
        tables.append(ex)
        names.append(mn)
    if names_path:
        ex, mn = load_names_json(names_path)
        tables.append(ex)
        names.append(mn)
    return merge_export_tables(*tables), merge_module_names(*names)


def display_module_name(dll, module_names):
    """Canonical display name for a DLL/module key (uppercased base, keeps ext)."""
    display = (module_names or {}).get(dll.lower(), dll)
    # Strip extension for the MODULE!symbol form when it reads cleaner; keep if
    # that's surprising? The task example shows COREDLL!_wfopen (no .dll).
    base = display
    if base.lower().endswith(".dll"):
        base = base[:-4]
    elif base.lower().endswith(".exe"):
        base = base[:-4]
    return base.upper()


def resolve_import_entry(dll, name, ordinal, exports_by_dll, module_names):
    """Resolve one import to ``(symbol, resolved, note)``.

    ``symbol`` is ``MODULE!name`` when a name is known (from the import itself
    or from the export table), else ``#ordinal`` / ``#ordinal (unresolved)``.
    ``resolved`` is True when the name came from the export table or the import
    already carried a name.  ``note`` is a short reason for unresolved ordinals.
    """
    mod = display_module_name(dll, module_names)
    table = (exports_by_dll or {}).get(dll.lower())
    if name is not None:
        # Name import: keep it; optionally confirm ordinal from exporter.
        if table and name in table.get("by_name", {}):
            return "%s!%s" % (mod, name), True, None
        return "%s!%s" % (mod, name), True, None
    if ordinal is not None and table and ordinal in table.get("by_ordinal", {}):
        return "%s!%s" % (mod, table["by_ordinal"][ordinal]), True, None
    if ordinal is not None:
        reason = "no export table for %s" % dll if not table else "ordinal %d not in %s exports" % (ordinal, dll)
        return "#%d" % ordinal, False, reason
    return "?", False, "no name and no ordinal"


def resolve_thunk(slot, data, cerom, imports_at, exports_by_dll, module_names):
    """Resolve one stub slot VA to ``module!export`` (ordinal) plus a reason.

    ``reason`` is None when resolved, else ``slot outside image`` (the literal
    is not a mappable VA and not a known import slot), ``no export match``
    (no import entry names the slot, or an ordinal import whose exporter is
    absent) or ``ambiguous duplicate (…)`` (two different import entries claim
    the slot).  ``confirmed`` is True when the exporter's own export table
    supplied or confirmed the name, which is what raises the confidence to
    ``high``.
    """
    unresolved = {"module": None, "export": None, "ordinal": None,
                  "reason": None, "confirmed": False}
    entries = imports_at.get(slot) or []
    if not entries:
        # Not a known import slot: report mapping status for diagnostics.
        offset = cerom.va2file(slot)
        if 0 <= offset and offset + 4 <= len(data):
            unresolved["reason"] = "no export match"
        else:
            unresolved["reason"] = "slot outside image"
        return unresolved
    if len(entries) > 1:
        labels = ", ".join(
            "%s!%s" % (entry["dll"],
                       entry["name"] if entry["name"] is not None
                       else "#%s" % entry["ordinal"]) for entry in entries)
        unresolved["reason"] = "ambiguous duplicate (%s)" % labels
        return unresolved

    entry = entries[0]
    table = exports_by_dll.get(entry["dll"].lower())
    module = module_names.get(entry["dll"].lower(), entry["dll"])
    if entry["name"] is not None:
        ordinal = entry["ordinal"]
        confirmed = bool(table and entry["name"] in table["by_name"])
        if confirmed:
            ordinal = table["by_name"][entry["name"]]
        return {"module": module, "export": entry["name"], "ordinal": ordinal,
                "reason": None, "confirmed": confirmed}
    if (entry["ordinal"] is not None and table
            and entry["ordinal"] in table["by_ordinal"]):
        return {"module": module,
                "export": table["by_ordinal"][entry["ordinal"]],
                "ordinal": entry["ordinal"], "reason": None, "confirmed": True}
    # Ordinal import with no exporter table/name: keep the slot identified.
    return {"module": module, "export": None, "ordinal": entry["ordinal"],
            "reason": "no export match", "confirmed": False}


def thunk_confidence(rank, confirmed, resolved):
    """Confidence label of one stub (see ``thunks_report``)."""
    if not resolved:
        return "low"
    if rank >= 2:
        return "high" if confirmed else "medium"
    if rank >= 1:
        return "medium" if confirmed else "low"
    return "low"


def coverage_percent(part, whole):
    """Coverage percentage rounded to one decimal; 100.0 for an empty whole."""
    if not whole:
        return 100.0
    return round(100.0 * part / whole, 1)


def thunks_report(data, image_name, image_size=None, image_sha256=None,
                  sha256_scope=None, module=None, all_modules=False,
                  image_start=None, resolve_starts=None, names_path=None):
    """Resolve import thunks/call sites of the selected modules (M1.6b/c).

    Detects standalone 4/3/2-insn stubs and inlined IAT call sites (a PC-rel
    load of an import slot followed by deref+``jsr/jmp``).  ``resolve_starts``
    / ``names_path`` (M1.9) supply cross-image export tables so ordinal
    imports resolve to names.  ``module`` selects one module (case-insensitive,
    in every segment); ``all_modules`` walks every module of every discovered
    segment.
    """
    segments, duplicates = find_segments(data, image_start)
    extra_exports, extra_names = load_resolver_tables(
        data, resolve_starts, names_path)

    if not all_modules:
        if not module:
            raise ValueError("thunks needs a module name or --all")
        available = set()
        for segment in segments:
            for entry in segment.modules():
                if entry["name"]:
                    available.add(entry["name"].lower())
        if module.lower() not in available:
            raise KeyError(module)

    records, module_records, errors = [], [], []
    for segment_index, segment in enumerate(segments):
        imports_at, exports_by_dll, module_names, index_errors = build_thunk_index(
            segment, segment_index)
        exports_by_dll = merge_export_tables(exports_by_dll, extra_exports)
        module_names = merge_module_names(module_names, extra_names)
        errors.extend(index_errors)
        for entry in segment.modules():
            name = entry["name"]
            if not name:
                continue
            if not all_modules and name.lower() != module.lower():
                continue

            slot_map = {}
            try:
                for dll, slot, stub_name, ordinal in segment.imports(entry):
                    slot_map.setdefault(slot, (dll, stub_name, ordinal))
            except (struct.error, ValueError, TypeError, IndexError) as exc:
                errors.append({"segment": segment_index, "module": name,
                               "error_type": type(exc).__name__,
                               "error": str(exc)})
            try:
                sections = list(segment.o32(entry))
            except (struct.error, ValueError) as exc:
                sections = []
                errors.append({"segment": segment_index, "module": name,
                               "error_type": type(exc).__name__,
                               "error": str(exc)})

            found, scanned = [], 0
            import_slot_set = set(slot_map)
            for index, sec in enumerate(sections):
                if sec["flags"] & IMAGE_SCN_COMPRESSED:
                    continue
                if not sec["flags"] & (CNT_CODE | MEM_EXECUTE):
                    continue
                if not sec["psize"]:
                    continue
                scanned += 1
                found.extend(scan_section_stubs(
                    segment, data, sec, index, import_slots=import_slot_set))

            module_stubs = []
            for stub in found:
                resolution = resolve_thunk(stub["slot_va"], data, segment,
                                           imports_at, exports_by_dll,
                                           module_names)
                resolved = resolution["reason"] is None
                rank = THUNKS_PATTERN_RANK.get(stub["pattern"], 0)
                record = {
                    "stub_va": hx(stub["stub_va"]),
                    "slot_va": hx(stub["slot_va"]),
                    "module": resolution["module"],
                    "export": resolution["export"],
                    "ordinal": resolution["ordinal"],
                    "section": stub["section"],
                    "confidence": thunk_confidence(rank,
                                                   resolution["confirmed"],
                                                   resolved),
                    "status": "resolved" if resolved else "unresolved",
                    "reason": resolution["reason"],
                    "pattern": stub["pattern"],
                    "owner": name,
                    "segment": segment_index,
                }
                module_stubs.append(record)
                records.append(record)

            stub_slots = {stub["slot_va"] for stub in found}
            covered = len(stub_slots & set(slot_map))
            resolved_count = sum(1 for record in module_stubs
                                 if record["status"] == "resolved")
            module_records.append({
                "segment": segment_index,
                "module": name,
                "scanned_sections": scanned,
                "stubs": len(module_stubs),
                "resolved": resolved_count,
                "unresolved": len(module_stubs) - resolved_count,
                "import_slots": len(slot_map),
                "covered_slots": covered,
                "stub_coverage": coverage_percent(resolved_count,
                                                  len(module_stubs)),
                "slot_coverage": coverage_percent(covered, len(slot_map)),
            })

    total = sum(entry["stubs"] for entry in module_records)
    resolved = sum(entry["resolved"] for entry in module_records)
    import_slots = sum(entry["import_slots"] for entry in module_records)
    covered = sum(entry["covered_slots"] for entry in module_records)
    counts = {
        "segments": len(segments),
        "modules": len(module_records),
        "scanned_sections": sum(entry["scanned_sections"]
                                for entry in module_records),
        "stubs": total,
        "resolved": resolved,
        "unresolved": total - resolved,
        "import_slots": import_slots,
        "covered_slots": covered,
        "outside_image": sum(1 for record in records
                             if record["reason"] == "slot outside image"),
        "no_export": sum(1 for record in records
                         if record["reason"] == "no export match"),
        "ambiguous": sum(1 for record in records
                         if (record["reason"] or "").startswith(
                             "ambiguous duplicate")),
        "errors": len(errors),
    }
    coverage = {
        "stubs": {"resolved": resolved, "total": total,
                  "percent": coverage_percent(resolved, total)},
        "slots": {"covered": covered, "total": import_slots,
                  "percent": coverage_percent(covered, import_slots)},
    }
    segment_records = [{
        "segment_index": index,
        "segment_base": hx(segment.start),
        "phys_base": hx(segment.hdr["physfirst"]),
        "pTOC": hx(segment.ptoc),
        "nummods": segment.hdr["nummods"],
        "numfiles": segment.hdr["numfiles"],
    } for index, segment in enumerate(segments)]
    return {
        "schema": THUNKS_SCHEMA,
        "generator": THUNKS_GENERATOR,
        "image": os.path.basename(image_name),
        "image_size": image_size,
        "image_sha256": image_sha256,
        "image_sha256_scope": sha256_scope,
        "scope": "all" if all_modules else module,
        "segments": segment_records,
        "duplicate_segments": duplicates,
        "counts": counts,
        "coverage": coverage,
        "modules": module_records,
        "stubs": records,
        "errors": errors,
    }


def print_thunks_text(report):
    """Print one block per module: its stubs, then stub and slot coverage."""
    grouped = {}
    for record in report["stubs"]:
        grouped.setdefault((record["segment"], record["owner"]), []).append(record)
    for module in report["modules"]:
        print("%s (segment %d)" % (module["module"], module["segment"]))
        for record in grouped.get((module["segment"], module["module"]), []):
            if record["status"] == "resolved":
                label = "%s!%s (#%s)" % (
                    record["module"], record["export"],
                    record["ordinal"] if record["ordinal"] is not None else "?")
            else:
                label = "UNRESOLVED (%s)" % record["reason"]
            print("  %-4s stub=%s slot=%s %-6s %-6s %s"
                  % (record["section"], record["stub_va"], record["slot_va"],
                     record["pattern"], record["confidence"], label))
        print("  coverage %d/%d stub(s) (%.1f %%), %d/%d slot(s) (%.1f %%)"
              % (module["resolved"], module["stubs"], module["stub_coverage"],
                 module["covered_slots"], module["import_slots"],
                 module["slot_coverage"]))
    for error in report["errors"]:
        print("module error: %s (segment %d): %s: %s"
              % (error["module"], error["segment"], error["error_type"],
                 error["error"]))
    counts, coverage = report["counts"], report["coverage"]
    print("%d stub(s) in %d module(s), %d segment(s): %d resolved, %d unresolved"
          " (stubs %d/%d, %.1f %%; slots %d/%d, %.1f %%)"
          % (counts["stubs"], counts["modules"], counts["segments"],
             counts["resolved"], counts["unresolved"],
             coverage["stubs"]["resolved"], coverage["stubs"]["total"],
             coverage["stubs"]["percent"], coverage["slots"]["covered"],
             coverage["slots"]["total"], coverage["slots"]["percent"]))
    if report["duplicate_segments"]:
        print("%d duplicate segment copy/copies not walked: %s"
              % (len(report["duplicate_segments"]),
                 ", ".join("0x%x" % int(d["segment_base"], 16)
                           for d in report["duplicate_segments"])))


# --------------------------------------------------------------------------
# FILESentry extraction (`files`): stored payloads, optional decode
# --------------------------------------------------------------------------


def stored_name(name, index):
    """Filesystem-safe stem for one ``FILESentry`` payload name."""
    base = name if name else "entry%d" % index
    for ch in '/\\:*?"<>|':
        base = base.replace(ch, "_")
    base = base.strip()
    return base or "entry%d" % index


def files_report(cerom, data, image_name, image_size=None, image_sha256=None,
                 sha256_scope=None, extract_dir=None, decompress=False,
                 method="auto"):
    """List ``FILESentry`` records and classify their stored payloads.

    ``sha256`` always covers the stored ``csize`` bytes.  A record is
    ``UNCOMPRESSED`` when ``csize == rsize`` (nothing to extract or decode),
    ``STORED`` when the stored bytes were written but no decode was requested,
    ``OK`` when ``tools/cecompress.py`` decoded them to exactly ``rsize`` bytes,
    ``UNSUPPORTED`` when the codec/block type is not implemented and ``FAIL``
    for an empty, out-of-image or undecodable payload.  Only an ``OK`` decode is
    ever written as file contents; a decode whose length differs from ``rsize``
    is refused, never written.
    """
    cc = cecompress_module()
    method = cc.normalise_method(method)
    write = bool(extract_dir)
    if write:
        extract_dir = os.path.abspath(extract_dir)

    records, extracted = [], []
    for entry in cerom.files():
        record = {
            "index": entry["index"],
            "name": entry["name"],
            "attrib": entry["attrib"],
            "rsize": entry["rsize"],
            "csize": entry["csize"],
            "load": entry["load"],
            "status": None,
            "method_used": None,
            "output_size": None,
            "sha256": None,
            "error": None,
        }
        compressed = entry["csize"] != entry["rsize"]
        offset = cerom.va2file(entry["load"])
        stored = None
        blob = None
        if not entry["csize"]:
            if entry["rsize"]:
                record["status"] = "FAIL"
                record["error"] = ("csize 0 with rsize %d: nothing stored to "
                                   "extract" % entry["rsize"])
            else:
                record["status"] = "UNCOMPRESSED"
        elif not (0 <= offset and offset + entry["csize"] <= len(data)):
            record["status"] = "FAIL"
            record["error"] = (
                "stored bytes 0x%x..0x%x lie outside the image (%d bytes)"
                % (offset, offset + entry["csize"], len(data)))
        else:
            stored = data[offset:offset + entry["csize"]]
            record["sha256"] = hashlib.sha256(stored).hexdigest()
            if not compressed:
                record["status"] = "UNCOMPRESSED"
            elif not decompress:
                record["status"] = "STORED"
            else:
                try:
                    blob, info = cc.decompress_info(
                        stored, entry["rsize"], method)
                except cc.UnsupportedFormat as exc:
                    record["status"] = "UNSUPPORTED"
                    record["error"] = str(exc)
                except cc.CeCompressError as exc:
                    record["status"] = "FAIL"
                    record["error"] = str(exc)
                except Exception as exc:  # noqa: BLE001 - one bad entry must not stop the walk
                    record["status"] = "FAIL"
                    record["error"] = "%s: %s" % (type(exc).__name__, exc)
                else:
                    # Belt and braces: never accept bytes that are not rsize.
                    if len(blob) != entry["rsize"]:
                        decoded_size = len(blob)
                        blob = None
                        record["status"] = "FAIL"
                        record["error"] = ("decoded %d bytes, expected %d"
                                           % (decoded_size, entry["rsize"]))
                    else:
                        record["status"] = "OK"
                        record["method_used"] = info.get("method")
                        record["output_size"] = len(blob)

        if stored is not None and write and compressed:
            os.makedirs(extract_dir, exist_ok=True)
            stem = "%s.%d" % (stored_name(entry["name"], entry["index"]),
                              entry["index"])
            stored_path = os.path.join(extract_dir, stem + ".stored.bin")
            with open(stored_path, "wb") as handle:
                handle.write(stored)
            paths = {"index": entry["index"], "stored_out": stored_path,
                     "out": None}
            if record["status"] == "OK" and blob is not None:
                decoded_path = os.path.join(extract_dir, stem + ".bin")
                with open(decoded_path, "wb") as handle:
                    handle.write(blob)
                paths["out"] = decoded_path
            extracted.append(paths)
        records.append(record)

    counts = {"files": len(records), "compressed": 0, "uncompressed": 0,
              "stored": 0, "ok": 0, "unsupported": 0, "fail": 0}
    for record in records:
        if record["csize"] != record["rsize"]:
            counts["compressed"] += 1
        else:
            counts["uncompressed"] += 1
        status = record["status"]
        if status == "STORED":
            counts["stored"] += 1
        elif status == "OK":
            counts["ok"] += 1
        elif status == "UNSUPPORTED":
            counts["unsupported"] += 1
        elif status == "FAIL":
            counts["fail"] += 1

    return {
        "schema": FILES_SCHEMA,
        "generator": FILES_GENERATOR,
        "image": os.path.basename(image_name),
        "image_size": image_size,
        "image_sha256": image_sha256,
        "image_sha256_scope": sha256_scope,
        "method": method,
        "decompress": bool(decompress),
        "extract_dir": extract_dir if write else None,
        "counts": counts,
        "extracted": extracted,
        "files": records,
    }


def print_files_text(report, cerom):
    """Print the FILESentry listing, plus extraction status when asked."""
    for record in report["files"]:
        print("%3d %-28s attr=%04x real=%8d comp=%8d load=%08x (file 0x%08x)"
              % (record["index"], record["name"], record["attrib"],
                 record["rsize"], record["csize"], record["load"],
                 cerom.va2file(record["load"])))
    if not (report["decompress"] or report["extract_dir"]):
        return
    paths = {item["index"]: item for item in report["extracted"]}
    for record in report["files"]:
        if record["csize"] == record["rsize"]:
            continue
        line = ("%-11s %-28s real=%8d comp=%8d"
                % (record["status"], record["name"], record["rsize"],
                   record["csize"]))
        item = paths.get(record["index"])
        if item and item["stored_out"]:
            line += " stored=%s" % item["stored_out"]
        if item and item["out"]:
            line += " decoded=%s" % item["out"]
        if record["error"]:
            line += " error=%s" % record["error"]
        print(line)
    counts = report["counts"]
    summary = ("%d compressed of %d file entr(ies): %d OK, %d UNSUPPORTED, %d FAIL"
               % (counts["compressed"], counts["files"], counts["ok"],
                  counts["unsupported"], counts["fail"]))
    if counts["stored"]:
        summary += ", %d stored only" % counts["stored"]
    written = sum(1 for item in report["extracted"] if item["stored_out"])
    written += sum(1 for item in report["extracted"] if item["out"])
    if written:
        summary += ", %d file(s) written" % written
    print(summary)


def files_command(args, cerom, data):
    """Run ``files``: listing, optional stored extraction and decode."""
    try:
        cc = cecompress_module()
    except ImportError as exc:
        print("error: cannot import tools/cecompress.py: %s" % exc, file=sys.stderr)
        return 2

    image_size = os.path.getsize(args.image)
    try:
        report = files_report(
            cerom, data, args.image, image_size, hashlib.sha256(data).hexdigest(),
            sha256_scope=sha256_scope_text(len(data), image_size),
            extract_dir=args.extract, decompress=args.decompress,
            method=args.method)
    except cc.CeCompressError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if args.json:
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
    else:
        print_files_text(report, cerom)

    counts = report["counts"]
    if args.decompress and (counts["unsupported"] or counts["fail"]):
        return 1
    if args.extract and counts["fail"]:
        return 1
    return 0


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

# The two compressed-section prefixes recorded in EXP-2026-11-05-49 (30 bytes
# each: the 22-byte header plus 8 payload bytes).  They are quoted in the repo
# docs, not read from the vendor image, and only feed the comphdr self-test.
COMPHDR_FIXTURES = (
    {
        "module": "NAVIMAPCC.DLL",
        "rva": 0x13000,
        "vsize": 0x5B8,
        "psize": 0x2C6,
        "flags": 0xC0002040,
        "prefix": bytes.fromhex(
            "840400c602001000000084040000b0020000840400005b80808d00204048"),
        "fields": {"len_u24": 0x484, "compressed_total": 0x2C6, "flags": 0x10,
                   "len_a": 0x484, "payload_len": 0x2B0, "len_b": 0x484},
    },
    {
        "module": "NAVIMAPCC.DLL",
        "rva": 0x14000,
        "vsize": 0xCC0,
        "psize": 0x68C,
        "flags": 0x48002040,
        "prefix": bytes.fromhex(
            "c00c008c060010000000c00c000076060000c00c00005b80808d002001cc"),
        "fields": {"len_u24": 0xCC0, "compressed_total": 0x68C, "flags": 0x10,
                   "len_a": 0xCC0, "payload_len": 0x676, "len_b": 0xCC0},
    },
)


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
        numfiles=3, ulKernelFlags=0x00000002, ulFSRamPercent=0x80808080,
        ulDrivglobStart=0, ulDrivglobLen=0, usCPUType=0x01A6,
        usMiscFlags=0x0002, pExtensions=0, ulTrackingStart=0, ulTrackingLen=0,
    )


def build_synthetic_rom():
    """Return ``(bytes, layout)`` for a two-module, three-file CE ROM.

    Layout: ``ECEC`` at image start + 0x40, ROMHDR at +0x1000, two 32-byte
    ``TOCentry`` records, three 28-byte ``FILESentry`` records.  Module 0 has an
    uncompressed section carrying a two-export directory plus one
    ``IMAGE_SCN_COMPRESSED`` section; module 1 has no exports.  The compressed
    bodies are real streams from ``tools/cecompress.py``: module 0 stores an
    LZSS stream produced by ``encode_lzss`` (decodes to ``vsize`` bytes) and
    module 1 stores an LZX **verbatim** block header, which the decoder must
    refuse as UNSUPPORTED rather than emit bytes for.

    The three files cover the ``FILESentry`` cases EXP-2026-11-05-51 found in
    the real image: ``default.hv`` is LZSS-compressed and decodes to ``rsize``,
    ``boot.hv`` stores the same LZX verbatim header (UNSUPPORTED under
    ``--method auto``), and ``wince.nls`` is stored with ``csize == rsize``
    (UNCOMPRESSED, not extracted).  Storage is keyed on ``csize != rsize``,
    never on the unverified ``attrib`` bit.
    """
    cc = cecompress_module()
    lzss_plain = (b"ZE0 LZSS section: MAL_DataVol_getOffset " * 128)[:0x800]
    lzss_stream, lzss_stats = cc.encode_lzss(lzss_plain)
    unsupported_stream = cc._build_lzx_block_header(1, 16)   # block type verbatim
    hive_plain = (b"ZE0 FILESentry: default.hv registry hive " * 16)[:0x200]
    hive_stream, hive_stats = cc.encode_lzss(hive_plain)
    raw_plain = b"\xA5" * 0x40

    d = bytearray(SYNTH_SIZE)
    layout = dict(image_start=SYNTH_IMAGE_START, va_base=SYNTH_VA_BASE,
                  toc_off=SYNTH_TOC_OFF, hdr_off=SYNTH_HDR_OFF,
                  ptoc=synth_va(SYNTH_HDR_OFF), hdr=synth_romhdr(),
                  lzss_plain=lzss_plain, lzss_stream=lzss_stream,
                  lzss_stats=lzss_stats, unsupported_stream=unsupported_stream,
                  file_hive_plain=hive_plain, file_hive_stream=hive_stream,
                  file_hive_stats=hive_stats, file_raw_plain=raw_plain)

    struct.pack_into("<4sII", d, SYNTH_IMAGE_START + 0x40, b"ECEC",
                     layout["ptoc"], SYNTH_TOC_OFF)
    hdr = layout["hdr"]
    struct.pack_into("<17IHHIII", d, SYNTH_HDR_OFF,
                     *[hdr[k] for k in ROMHDR_FIELDS],
                     hdr["usCPUType"], hdr["usMiscFlags"], hdr["pExtensions"],
                     hdr["ulTrackingStart"], hdr["ulTrackingLen"])

    # NUL-terminated names at 0x2000: module 2x, file 3x.
    name_off = {}
    off = 0x2000
    for name in (b"NK.EXE", b"NAVI.EXE", b"default.hv", b"boot.hv", b"wince.nls"):
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
    struct.pack_into("<6I", d, 0x4218, 0x800, 0x2000, len(lzss_stream),
                     synth_va(0x5400), 0x8CE02000, 0xC0002040)  # COMPRESSED, LZSS
    struct.pack_into("<6I", d, 0x6200, 0x300, 0x1000, 0x200, synth_va(0x6400),
                     0x8D001000, 0x60000020)
    struct.pack_into("<6I", d, 0x6218, 0x100, 0x2000, len(unsupported_stream),
                     synth_va(0x6600), 0x8D002000, 0xC0002040)  # COMPRESSED, LZX verbatim
    d[0x5400:0x5400 + len(lzss_stream)] = lzss_stream
    d[0x6600:0x6600 + len(unsupported_stream)] = unsupported_stream

    # FILESentry: attrib, ftl, fth, real size, compressed size, name, load.
    # keyed on csize != rsize: LZSS (0x6c00), LZX verbatim (0x7100), stored
    # as-is (0x7200).  The 0x0800 attrib follows EXP-2026-11-05-51 but the
    # status classification never reads it.
    files_at = toc + TOC_SIZE * 2
    struct.pack_into("<7I", d, files_at,
                     0x00000800, 0x55667788, 0x00000000, len(hive_plain),
                     len(hive_stream),
                     synth_va(name_off["default.hv"]), synth_va(0x6C00))
    struct.pack_into("<7I", d, files_at + FILES_SIZE,
                     0x00000800, 0x55667788, 0x00000001, 0x100,
                     len(unsupported_stream),
                     synth_va(name_off["boot.hv"]), synth_va(0x7100))
    struct.pack_into("<7I", d, files_at + 2 * FILES_SIZE,
                     0x00000007, 0x55667788, 0x00000002, len(raw_plain),
                     len(raw_plain),
                     synth_va(name_off["wince.nls"]), synth_va(0x7200))
    d[0x6C00:0x6C00 + len(hive_stream)] = hive_stream
    d[0x7100:0x7100 + len(unsupported_stream)] = unsupported_stream
    d[0x7200:0x7200 + len(raw_plain)] = raw_plain

    layout["name_off"] = name_off
    layout["export_names"] = [n.decode() for n in exp_names]
    return bytes(d), layout


def build_comphdr_rom(prefix, vsize, psize, module_name="NAVIMAPCC.DLL",
                      rva=0x13000, section_flags=0xC0002040):
    """Return a one-module synthetic ROM whose only stored section is compressed.

    ``prefix`` is copied verbatim at the start of the ``psize`` stored bytes and
    the rest is zero padding: enough for the header probe, never a decode.  The
    prefixes in ``COMPHDR_FIXTURES`` are the recorded 30-byte starts from
    EXP-2026-11-05-49.
    """
    if len(prefix) > psize:
        raise ValueError("prefix is longer than psize")
    if 0x5000 + psize > SYNTH_SIZE:
        raise ValueError("section does not fit the synthetic image")
    d = bytearray(SYNTH_SIZE)
    struct.pack_into("<4sII", d, SYNTH_IMAGE_START + 0x40, b"ECEC",
                     synth_va(SYNTH_HDR_OFF), SYNTH_TOC_OFF)
    hdr = dict(synth_romhdr(), nummods=1, numfiles=0)
    struct.pack_into("<17IHHIII", d, SYNTH_HDR_OFF,
                     *[hdr[k] for k in ROMHDR_FIELDS], hdr["usCPUType"],
                     hdr["usMiscFlags"], hdr["pExtensions"],
                     hdr["ulTrackingStart"], hdr["ulTrackingLen"])

    name = module_name.encode("ascii") + b"\0"
    d[0x2000:0x2000 + len(name)] = name
    toc = SYNTH_HDR_OFF + ROMHDR_SIZE
    struct.pack_into("<8I", d, toc, 0x0000001C, 0x11223344, 0x00000001,
                     0x8000, synth_va(0x2000), synth_va(0x4000),
                     synth_va(0x4200), 0x8CB00000)
    struct.pack_into("<HHIIHHIIIII", d, 0x4000, 1, 0x0002, 0x1000,
                     0x8CB00000, 1, 0, 0x1000, 0x20000, 0, 0, 0x5F000000)
    struct.pack_into("<18I", d, 0x4000 + 36, *([0] * 18))
    struct.pack_into("<6I", d, 0x4200, vsize, rva, psize, synth_va(0x5000),
                     SYNTH_VA_BASE + rva, section_flags)
    d[0x5000:0x5000 + len(prefix)] = prefix
    return bytes(d)


def build_thunks_rom(local_va=False):
    """Return ``(bytes, layout)`` for a two-module ROM with three import stubs.

    ``OBJDLL.DLL`` exports two functions with export base 5 (ordinals 5 and 6).
    ``NAVI.EXE`` has one import descriptor for that DLL with two slots — one
    imported by name, one by ordinal — and one code section holding three
    stubs: the EXP-50 four-instruction pattern for the named slot, the direct
    three-instruction variant for the ordinal slot, and a fourth stub whose
    literal is a VA outside the image.

    ``local_va=True`` places ``realaddr``/``vbase``/slot VAs in module-local
    space (``0x00010000``), like real Navi.exe, while ``dataptr`` stays a ROM
    VA.  This reproduces the M1.6c root cause (ROM-linear ``va2file`` cannot
    map module-local VAs).
    """
    code_off, code_rva = 0x5000, 0x1000
    data_off, data_rva = 0x6000, 0x2000
    obj_off, obj_rva = 0x3600, 0x1000
    if local_va:
        navi_vbase = 0x00010000
    else:
        navi_vbase = synth_va(code_off) - code_rva
    code_va = navi_vbase + code_rva
    data_va = navi_vbase + data_rva
    obj_vbase = synth_va(obj_off) - obj_rva
    slot0 = navi_vbase + 0x2100
    slot1 = slot0 + 4

    d = bytearray(SYNTH_SIZE)
    struct.pack_into("<4sII", d, SYNTH_IMAGE_START + 0x40, b"ECEC",
                     synth_va(SYNTH_HDR_OFF), SYNTH_TOC_OFF)
    hdr = dict(synth_romhdr(), nummods=2, numfiles=0)
    struct.pack_into("<17IHHIII", d, SYNTH_HDR_OFF,
                     *[hdr[k] for k in ROMHDR_FIELDS], hdr["usCPUType"],
                     hdr["usMiscFlags"], hdr["pExtensions"],
                     hdr["ulTrackingStart"], hdr["ulTrackingLen"])

    name_off = {}
    off = 0x2000
    for name in (b"OBJDLL.DLL", b"NAVI.EXE"):
        d[off:off + len(name) + 1] = name + b"\0"
        name_off[name.decode()] = off
        off += len(name) + 1

    # Export directory of module 0: base 5, two names, function RVAs arbitrary.
    exp_names = (b"MAL_DataVol_getOffset", b"MAL_DataVol_getSize")
    name_rvas = []
    off = 0x3640
    for name in exp_names:
        d[off:off + len(name) + 1] = name + b"\0"
        name_rvas.append(obj_rva + off - obj_off)
        off += len(name) + 1
    struct.pack_into("<IIHHIIIIIII", d, obj_off, 0, 0x5F000000, 0, 0,
                     name_rvas[0], 5, 2, 2, 0x1028, 0x1030, 0x1038)
    struct.pack_into("<2I", d, obj_off + 0x28, 0x1100, 0x1200)
    struct.pack_into("<2I", d, obj_off + 0x30, *name_rvas)
    struct.pack_into("<2H", d, obj_off + 0x38, 0, 1)      # ordinals -> 5, 6

    toc = SYNTH_HDR_OFF + ROMHDR_SIZE
    struct.pack_into("<8I", d, toc, 0x0000001C, 0x11223344, 0x00000001, 0x2000,
                     synth_va(name_off["OBJDLL.DLL"]), synth_va(0x3000),
                     synth_va(0x3200), obj_vbase)
    struct.pack_into("<8I", d, toc + TOC_SIZE, 0x0000001C, 0x55667788,
                     0x00000001, 0x4000, synth_va(name_off["NAVI.EXE"]),
                     synth_va(0x4000), synth_va(0x4200), navi_vbase)

    # e32_rom: exporter with an export dir and no imports; importer with an
    # import dir at rva 0x2000 and no exports.
    struct.pack_into("<HHIIHHIIIII", d, 0x3000, 1, 0x0002, 0, obj_vbase,
                     1, 0, 0x1000, 0x2000, 0, 0, 0x5F000000)
    struct.pack_into("<18I", d, 0x3000 + 36, *([0x1000, 0x80, 0, 0, 0, 0]
                                               + [0] * 12))
    struct.pack_into("<HHIIHHIIIII", d, 0x4000, 2, 0x2002, 0x1000, navi_vbase,
                     1, 0, 0x800, 0x4000, 0, 0, 0x5F010000)
    struct.pack_into("<18I", d, 0x4000 + 36, *([0, 0, 0x2000, 0xA0, 0, 0]
                                               + [0] * 12))

    # o32_rom: exporter data section, importer code section + data section.
    struct.pack_into("<6I", d, 0x3200, 0x200, obj_rva, 0x200,
                     synth_va(obj_off), obj_vbase + obj_rva, 0xC0000040)
    struct.pack_into("<6I", d, 0x4200, 0x400, code_rva, 0x400,
                     synth_va(code_off), code_va, 0x60000020)
    struct.pack_into("<6I", d, 0x4218, 0x200, data_rva, 0x200,
                     synth_va(data_off), data_va, 0xC0000040)

    # Import descriptor (OFT, timestamp, forwarder, DLL name, FirstThunk).
    struct.pack_into("<5I", d, data_off, 0x2040, 0, 0, 0x2020, 0x2100)
    struct.pack_into("<5I", d, data_off + 20, 0, 0, 0, 0, 0)
    d[data_off + 0x20:data_off + 0x20 + 11] = b"OBJDLL.DLL\0"
    struct.pack_into("<3I", d, data_off + 0x40, 0x2060, 0x80000006, 0)
    struct.pack_into("<H", d, data_off + 0x60, 0)         # hint
    hint = data_off + 0x62
    d[hint:hint + len(exp_names[0]) + 1] = exp_names[0] + b"\0"

    # Three stubs, each with its literal 8 bytes after the first instruction.
    for base_off, opcodes, literal in (
            (code_off, (0xD001, 0x6002, 0x402B, 0x0009), slot0),
            (code_off + 0x20, (0xD001, 0x402B, 0x0009), slot1),
            (code_off + 0x40, (0xD001, 0x6002, 0x402B, 0x0009), 0x7FFF0000)):
        for position, word in enumerate(opcodes):
            struct.pack_into("<H", d, base_off + 2 * position, word)
        struct.pack_into("<I", d, base_off + 8, literal)

    layout = dict(image_start=SYNTH_IMAGE_START, va_base=SYNTH_VA_BASE,
                  toc_off=SYNTH_TOC_OFF, hdr_off=SYNTH_HDR_OFF,
                  ptoc=synth_va(SYNTH_HDR_OFF), hdr=hdr,
                  navi_vbase=navi_vbase, obj_vbase=obj_vbase,
                  code_va=code_va, data_va=data_va,
                  slots=(slot0, slot1),
                  stub_vas=(code_va, code_va + 0x20, code_va + 0x40),
                  export_names=[name.decode() for name in exp_names],
                  export_ordinals=(5, 6), import_slots=2, stub_count=3)
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
           (r.hdr["nummods"], r.hdr["numfiles"], r.hdr["usCPUType"]), (2, 3, 0x01A6))
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
        ok("file count", len(files), 3)
        ok("file names", [f["name"] for f in files],
           ["default.hv", "boot.hv", "wince.nls"])
        ok("file sizes", [(f["rsize"], f["csize"]) for f in files],
           [(0x200, len(exp["file_hive_stream"])),
            (0x100, len(exp["unsupported_stream"])), (0x40, 0x40)])
        ok("file attribs", [f["attrib"] for f in files],
           [0x0800, 0x0800, 0x0007])
        ok("file payload offsets", [r.va2file(f["load"]) for f in files],
           [0x6C00, 0x7100, 0x7200])
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
            (0x2000, 0x800, len(exp["lzss_stream"]), 0x5400, 0x8CE02000, 0xC0002040)])
        ok("compressed flags mod0",
           [bool(s["flags"] & IMAGE_SCN_COMPRESSED) for s in secs], [False, True])
        ok("sections mod1", [(s["rva"], s["psize"], r.va2file(s["dataptr"]), s["flags"])
                             for s in r.o32(mods[1])],
           [(0x1000, 0x200, 0x6400, 0x60000020),
            (0x2000, len(exp["unsupported_stream"]), 0x6600, 0xC0002040)])
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
            ("sec1", "0x8ce02000", 0x5400, len(exp["lzss_stream"]))])
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
            ("sec1", "0x8d002000", 0x6600, len(exp["unsupported_stream"]))])
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

        # --- decompress: every IMAGE_SCN_COMPRESSED section (M1.3) ----------
        segs, dupes = find_segments(rom)
        ok("decompress segment discovery",
           [(s.start, s.va_base) for s in segs],
           [(exp["image_start"], exp["va_base"])])
        ok("decompress segment duplicates", dupes, [])
        segs2, dupes2 = find_segments(rom + rom)
        ok("decompress duplicate segment not walked", len(segs2), 1)
        ok("decompress duplicate segment reported", dupes2,
           [{"segment_base": hx(len(rom) + exp["image_start"]),
             "duplicate_of": 0}])

        # Two distinct segments in one file: both are walked, one output
        # directory each, so equal `<module>.<rva>.bin` names cannot collide.
        twin = bytearray(rom + rom)
        struct.pack_into("<I", twin, len(rom) + exp["hdr_off"] + 0x0c,
                         exp["hdr"]["physlast"] + 0x1000)
        twin_path = os.path.join(td, "twin.img")
        with open(twin_path, "wb") as fh:
            fh.write(twin)
        twin_dir = os.path.join(td, "twin-out")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli decompress two segments exit",
               main([twin_path, "decompress", "--out", twin_dir]), 1)
        ok("decompress two segments were walked",
           "4 compressed section(s) in 2 segment(s)" in buf.getvalue(), True)
        ok("decompress writes one directory per segment",
           sorted(os.listdir(twin_dir)), ["seg0", "seg1"])
        ok("decompress per-segment file names",
           [sorted(os.listdir(os.path.join(twin_dir, name)))
            for name in ("seg0", "seg1")],
           [["NK.EXE.00002000.bin"], ["NK.EXE.00002000.bin"]])

        check_dir = os.path.join(td, "check-only")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli decompress --check --json exit",
               main([path, "decompress", "--check", "--json", "--out", check_dir]), 1)
        doc = json.loads(buf.getvalue())
        ok("decompress schema", doc["schema"], DECOMPRESS_SCHEMA)
        ok("decompress generator", doc["generator"], DECOMPRESS_GENERATOR)
        ok("decompress image basename", doc["image"], "synthetic-rom.img")
        ok("decompress image sha256", doc["image_sha256"], hashlib.sha256(rom).hexdigest())
        ok("decompress method", doc["method"], "auto")
        ok("decompress check flag", doc["check"], True)
        ok("decompress out_dir not written", doc["out_dir"], None)
        ok("decompress --check wrote nothing", os.path.exists(check_dir), False)
        ok("decompress segment record", doc["segments"],
           [{"segment_index": 0, "segment_base": hx(exp["image_start"]),
             "phys_base": hx(exp["va_base"]), "pTOC": hx(exp["ptoc"]),
             "nummods": 2, "numfiles": 3}])
        ok("decompress counts", doc["counts"],
           {"sections": 2, "ok": 1, "unsupported": 1, "fail": 0, "errors": 0})
        ok("decompress module errors", doc["errors"], [])
        ok("decompress record key order", sorted(doc["sections"][0]),
           ["detected", "error", "error_type", "file_offset", "flags", "method",
            "method_used", "module", "out", "output_size", "psize", "rva",
            "section", "segment", "sha256", "sha256_scope", "status", "vsize"])
        ok("decompress records",
           [(r["segment"], r["module"], r["section"], r["rva"], r["vsize"], r["psize"])
            for r in doc["sections"]],
           [(0, "NK.EXE", "sec1", "0x2000", 0x800, len(exp["lzss_stream"])),
            (0, "NAVI.EXE", "sec1", "0x2000", 0x100, len(exp["unsupported_stream"]))])
        ok("decompress stored file offsets",
           [r["file_offset"] for r in doc["sections"]], [0x5400, 0x6600])
        ok("decompress compressed flags",
           [r["flags"] for r in doc["sections"]], ["0xc0002040", "0xc0002040"])
        lz = doc["sections"][0]
        ok("decompress LZSS status/method", (lz["status"], lz["method_used"]), ("OK", "lzss"))
        ok("decompress LZSS output size", lz["output_size"], 0x800)
        ok("decompress LZSS sha256 scope", lz["sha256_scope"], "decoded")
        ok("decompress LZSS sha256",
           lz["sha256"], hashlib.sha256(exp["lzss_plain"]).hexdigest())
        ok("decompress LZSS detected confidence",
           lz["detected"]["confidence"], "confirmed")
        ok("decompress LZSS no error", (lz["error"], lz["error_type"]), (None, None))
        ok("decompress LZSS wrote nothing in check mode", lz["out"], None)
        bad = doc["sections"][1]
        ok("decompress unsupported status",
           (bad["status"], bad["error_type"]), ("UNSUPPORTED", "UnsupportedFormat"))
        ok("decompress unsupported message",
           "UNSUPPORTED(lzx block type verbatim" in bad["error"], True)
        ok("decompress unsupported keeps the stored hash",
           (bad["sha256_scope"], bad["sha256"]),
           ("stored", hashlib.sha256(exp["unsupported_stream"]).hexdigest()))
        ok("decompress unsupported has no output",
           (bad["output_size"], bad["out"], bad["method_used"]), (None, None, None))

        out_dir = os.path.join(td, "sections")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli decompress --out exit", main([path, "decompress", "--out", out_dir]), 1)
        ok("decompress wrote only the OK section",
           sorted(os.listdir(out_dir)), ["NK.EXE.00002000.bin"])
        with open(os.path.join(out_dir, "NK.EXE.00002000.bin"), "rb") as fh:
            ok("decompress written bytes", fh.read(), exp["lzss_plain"])
        ok("decompress text summary",
           "1 OK, 1 UNSUPPORTED, 0 FAIL" in buf.getvalue(), True)
        ok("decompress text writes one file", "1 file(s) written" in buf.getvalue(), True)
        ok("decompress text names the refusal",
           "UNSUPPORTED(lzx block type verbatim" in buf.getvalue(), True)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli decompress --method lzss exit",
               main([path, "decompress", "--method", "lzss", "--json"]), 1)
        doc = json.loads(buf.getvalue())
        ok("decompress --method lzss counts",
           (doc["counts"]["ok"], doc["counts"]["unsupported"], doc["counts"]["fail"]),
           (1, 0, 1))
        ok("decompress --method lzss FAIL record",
           (doc["sections"][1]["status"], doc["sections"][1]["error_type"]),
           ("FAIL", "DecodeError"))
        ok("decompress --method lzss FAIL says the length",
           "expected 256" in (doc["sections"][1]["error"] or ""), True)

        # Truncated images: an unreachable stored range is FAIL (never data),
        # and a module whose e32/o32 cannot be read is an error, not a crash.
        with open(os.path.join(td, "cut-data.img"), "wb") as fh:
            fh.write(rom[:0x6602])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli decompress out-of-image exit",
               main([os.path.join(td, "cut-data.img"), "decompress", "--json"]), 1)
        doc = json.loads(buf.getvalue())
        ok("decompress out-of-image counts",
           (doc["counts"]["ok"], doc["counts"]["fail"]), (1, 1))
        ok("decompress out-of-image record",
           (doc["sections"][1]["status"], doc["sections"][1]["error_type"],
            doc["sections"][1]["out"]), ("FAIL", "RangeError", None))
        ok("decompress out-of-image message",
           "lie outside the image" in doc["sections"][1]["error"], True)

        with open(os.path.join(td, "cut-module.img"), "wb") as fh:
            fh.write(rom[:0x6000])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli decompress unreadable module exit",
               main([os.path.join(td, "cut-module.img"), "decompress", "--json"]), 1)
        doc = json.loads(buf.getvalue())
        ok("decompress unreadable module recorded", doc["errors"],
           [{"segment": 0, "module": "NAVI.EXE", "error_type": "struct.error",
             "error": doc["errors"][0]["error"]}])
        ok("decompress unreadable module error is not silent",
           "unpack_from requires a buffer" in doc["errors"][0]["error"], True)
        ok("decompress unreadable module counts",
           (doc["counts"]["sections"], doc["counts"]["errors"]), (1, 1))

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli decompress --modules NK.EXE exits 0",
               main([path, "decompress", "--modules", "NK.EXE", "--json"]), 0)
        doc = json.loads(buf.getvalue())
        ok("decompress module filter", [r["module"] for r in doc["sections"]],
           ["NK.EXE"])
        ok("decompress module filter counts",
           (doc["counts"]["sections"], doc["counts"]["ok"]), (1, 1))

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli decompress --section MODULE/secN exit",
               main([path, "decompress", "--section", "NAVI.EXE/sec1", "--json"]), 1)
        ok("decompress section selector",
           [(r["module"], r["section"]) for r in json.loads(buf.getvalue())["sections"]],
           [("NAVI.EXE", "sec1")])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli decompress --section RVA exit",
               main([path, "decompress", "--section", "0x2000", "--json"]), 1)
        ok("decompress RVA selector",
           len(json.loads(buf.getvalue())["sections"]), 2)

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ok("cli decompress unknown module exit",
               main([path, "decompress", "--modules", "Nope.dll"]), 2)
        ok("cli decompress unknown module message", "Nope.dll" in err.getvalue(), True)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ok("cli decompress empty --modules exit",
               main([path, "decompress", "--modules", ",,"]), 2)
        ok("cli decompress empty --modules message",
           "--modules names no module" in err.getvalue(), True)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ok("cli decompress bad --section exit",
               main([path, "decompress", "--section", "nonsense"]), 2)
        ok("cli decompress bad --section message",
           "is not sec<N>" in err.getvalue(), True)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ok("cli decompress bad --method exit",
               main([path, "decompress", "--method", "lzma"]), 2)
        ok("cli decompress bad --method message",
           "UNSUPPORTED(method 'lzma')" in err.getvalue(), True)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ok("cli decompress no match exit",
               main([path, "decompress", "--section", "sec0"]), 2)
        ok("cli decompress no match message",
           "no IMAGE_SCN_COMPRESSED section matched" in err.getvalue(), True)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ok("cli decompress missing image exit",
               main([os.path.join(td, "nope.img"), "decompress"]), 2)
        ok("cli decompress missing image message", "error:" in err.getvalue(), True)

        # --- files: FILESentry listing, extraction and decode (M1.4) --------
        listing = files_report(r, data, path, len(rom), sha)
        ok("files schema", listing["schema"], FILES_SCHEMA)
        ok("files generator", listing["generator"], FILES_GENERATOR)
        ok("files image basename", listing["image"], "synthetic-rom.img")
        ok("files record keys", list(listing["files"][0]), list(FILES_RECORD_KEYS))
        ok("files listing decompress flag", listing["decompress"], False)
        ok("files listing extract dir", listing["extract_dir"], None)
        ok("files listing statuses",
           [x["status"] for x in listing["files"]],
           ["STORED", "STORED", "UNCOMPRESSED"])
        ok("files listing stored hash", listing["files"][0]["sha256"],
           hashlib.sha256(exp["file_hive_stream"]).hexdigest())
        ok("files listing raw hash", listing["files"][2]["sha256"],
           hashlib.sha256(exp["file_raw_plain"]).hexdigest())
        ok("files listing counts", listing["counts"],
           {"files": 3, "compressed": 2, "uncompressed": 1, "stored": 2,
            "ok": 0, "unsupported": 0, "fail": 0})
        ok("files listing writes nothing", listing["extracted"], [])

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli files exit", main([path, "files"]), 0)
        lines = buf.getvalue().splitlines()
        ok("cli files text line count", len(lines), 3)
        ok("cli files text first line",
           lines[0].startswith("  0 default.hv") and " real=     512 comp=" in lines[0],
           True)
        ok("cli files text has no summary",
           [line for line in lines if "compressed of" in line], [])

        stored_dir = os.path.join(td, "files-stored")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli files --extract exit",
               main([path, "files", "--extract", stored_dir]), 0)
        ok("files --extract names", sorted(os.listdir(stored_dir)),
           ["boot.hv.1.stored.bin", "default.hv.0.stored.bin"])
        ok("files --extract sizes",
           [os.path.getsize(os.path.join(stored_dir, n)) for n in
            ("default.hv.0.stored.bin", "boot.hv.1.stored.bin")],
           [len(exp["file_hive_stream"]), len(exp["unsupported_stream"])])
        with open(os.path.join(stored_dir, "default.hv.0.stored.bin"), "rb") as fh:
            ok("files --extract stored bytes", fh.read(), exp["file_hive_stream"])
        ok("files --extract leaves uncompressed out",
           os.path.exists(os.path.join(stored_dir, "wince.nls.2.stored.bin")), False)
        ok("files --extract text summary",
           "2 compressed of 3 file entr(ies): 0 OK, 0 UNSUPPORTED, 0 FAIL, "
           "2 stored only, 2 file(s) written" in buf.getvalue(), True)

        out_dir = os.path.join(td, "files-out")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli files --extract --decompress --json exit",
               main([path, "files", "--extract", out_dir, "--decompress",
                     "--json"]), 1)
        doc = json.loads(buf.getvalue())
        ok("files json schema", doc["schema"], FILES_SCHEMA)
        ok("files json method", doc["method"], "auto")
        ok("files json decompress flag", doc["decompress"], True)
        ok("files json extract dir", doc["extract_dir"], out_dir)
        ok("files json keys", list(doc["files"][0]), list(FILES_RECORD_KEYS))
        ok("files json statuses",
           [(x["index"], x["name"], x["status"], x["method_used"])
            for x in doc["files"]],
           [(0, "default.hv", "OK", "lzss"),
            (1, "boot.hv", "UNSUPPORTED", None),
            (2, "wince.nls", "UNCOMPRESSED", None)])
        ok("files json counts", doc["counts"],
           {"files": 3, "compressed": 2, "uncompressed": 1, "stored": 0,
            "ok": 1, "unsupported": 1, "fail": 0})
        hive, boot, raw = doc["files"]
        ok("files json decoded size", hive["output_size"], 0x200)
        ok("files json record sizes", (hive["rsize"], hive["csize"]),
           (0x200, len(exp["file_hive_stream"])))
        ok("files json stored hash", hive["sha256"],
           hashlib.sha256(exp["file_hive_stream"]).hexdigest())
        ok("files json unsupported has no output",
           (boot["output_size"], boot["method_used"]), (None, None))
        ok("files json unsupported message",
           "UNSUPPORTED(lzx block type verbatim" in (boot["error"] or ""), True)
        ok("files json raw is not decoded", (raw["output_size"], raw["sha256"]),
           (None, hashlib.sha256(exp["file_raw_plain"]).hexdigest()))
        ok("files json extracted paths",
           [(x["index"], x["stored_out"] is not None, x["out"] is not None)
            for x in doc["extracted"]],
           [(0, True, True), (1, True, False)])

        ok("files decoded tree", sorted(os.listdir(out_dir)),
           ["boot.hv.1.stored.bin", "default.hv.0.bin",
            "default.hv.0.stored.bin"])
        with open(os.path.join(out_dir, "default.hv.0.bin"), "rb") as fh:
            ok("files decoded bytes", fh.read(), exp["file_hive_plain"])
        ok("files decoded size equals rsize",
           os.path.getsize(os.path.join(out_dir, "default.hv.0.bin")), 0x200)
        with open(os.path.join(out_dir, "boot.hv.1.stored.bin"), "rb") as fh:
            ok("files unsupported stores the raw stream",
               fh.read(), exp["unsupported_stream"])

        text_dir = os.path.join(td, "files-text")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli files text extract exit",
               main([path, "files", "--extract", text_dir, "--decompress"]), 1)
        ok("files text statuses",
           ("OK" in buf.getvalue() and "UNSUPPORTED" in buf.getvalue()), True)
        ok("files text summary",
           "2 compressed of 3 file entr(ies): 1 OK, 1 UNSUPPORTED, 0 FAIL, "
           "3 file(s) written" in buf.getvalue(), True)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli files --decompress --method lzss exit",
               main([path, "files", "--decompress", "--method", "lzss",
                     "--json"]), 1)
        doc = json.loads(buf.getvalue())
        ok("files lzss boot.hv is FAIL",
           (doc["files"][1]["status"], doc["files"][1]["output_size"]),
           ("FAIL", None))
        ok("files lzss FAIL says the length",
           "expected 256" in (doc["files"][1]["error"] or ""), True)
        ok("files --decompress without --extract writes nothing",
           (doc["extracted"], doc["extract_dir"]), ([], None))

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ok("cli files bad --method exit",
               main([path, "files", "--decompress", "--method", "lzma"]), 2)
        ok("cli files bad --method message",
           "UNSUPPORTED(method 'lzma')" in err.getvalue(), True)

        with open(os.path.join(td, "cut-files.img"), "wb") as fh:
            fh.write(rom[:0x6C01])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli files out-of-image exit",
               main([os.path.join(td, "cut-files.img"), "files",
                     "--decompress", "--json"]), 1)
        doc = json.loads(buf.getvalue())
        ok("files out-of-image statuses",
           [x["status"] for x in doc["files"]], ["FAIL", "FAIL", "FAIL"])
        ok("files out-of-image message",
           "lie outside the image" in (doc["files"][0]["error"] or ""), True)
        ok("files out-of-image counts", doc["counts"]["fail"], 3)

        cut_extract = os.path.join(td, "cut-extract")
        with contextlib.redirect_stdout(io.StringIO()):
            ok("cli files out-of-image --extract exit",
               main([os.path.join(td, "cut-files.img"), "files",
                     "--extract", cut_extract]), 1)
        ok("files out-of-image --extract wrote nothing",
           os.path.exists(cut_extract), False)

        # --- comphdr: the 22-byte compressed-section header (M1.2a) --------
        # The two real prefixes recorded in EXP-2026-11-05-49 (30 bytes each)
        # are the acceptance vectors; no other vendor bytes are used.
        for fixture in COMPHDR_FIXTURES:
            label = "%s rva 0x%x" % (fixture["module"], fixture["rva"])
            ok("comphdr %s recorded prefix length" % label,
               len(fixture["prefix"]), 30)
            fields = parse_comphdr(fixture["prefix"])
            ok("comphdr %s header fields" % label, fields,
               dict(fixture["fields"], payload_offset=22))
            invariants, failed = comphdr_checks(
                fields, fixture["psize"], fixture["vsize"])
            ok("comphdr %s invariants" % label, failed, [])
            ok("comphdr %s every check true" % label,
               sorted(invariants.values()), [True] * len(invariants))
            ok("comphdr %s verdict" % label,
               classify_comphdr(fixture["prefix"], fixture["psize"],
                                fixture["vsize"])["verdict"], "HOLDS")

        base = COMPHDR_FIXTURES[0]
        for label, patch, psize, vsize, failed_keys in (
                ("wrong flags", (6, 0x11), base["psize"], base["vsize"],
                 ["flags_is_0x10"]),
                ("compressed_total mismatch", (3, 0xC7), base["psize"],
                 base["vsize"], ["compressed_total_is_psize"]),
                ("payload_len mismatch", (14, 0xB1), base["psize"],
                 base["vsize"], ["payload_len_is_psize_minus_22"]),
                ("length words disagree", (10, 0x85), base["psize"],
                 base["vsize"], ["lengths_agree"]),
                ("length over vsize", None, base["psize"], 0x400,
                 ["uncompressed_len_within_vsize"])):
            blob = bytearray(base["prefix"])
            if patch is not None:
                blob[patch[0]] = patch[1]
            record = classify_comphdr(bytes(blob), psize, vsize)
            ok("comphdr %s is REFUTED" % label, record["verdict"], "REFUTED")
            ok("comphdr %s names the failed check" % label,
               record["failed"], failed_keys)
        ok("comphdr over-vsize sets within_vsize",
           classify_comphdr(base["prefix"], base["psize"], 0x400)
           ["within_vsize"], False)

        for label, blob, psize in (
                ("psize 0", None, 0),
                ("psize below the header", base["prefix"][:16], 0x10),
                ("stored bytes truncated", base["prefix"][:16], base["psize"])):
            record = classify_comphdr(blob, psize, base["vsize"])
            ok("comphdr %s is UNPARSED" % label, record["verdict"], "UNPARSED")
            ok("comphdr %s has no header fields" % label,
               (record["uncompressed_len"], record["checks"]), (None, None))
            ok("comphdr %s keeps the reason" % label,
               bool(record["error"]), True)

        for fixture in COMPHDR_FIXTURES:
            rom_c = build_comphdr_rom(fixture["prefix"], fixture["vsize"],
                                      fixture["psize"], rva=fixture["rva"])
            fixture_path = os.path.join(
                td, "comphdr-%05x.img" % fixture["rva"])
            with open(fixture_path, "wb") as fh:
                fh.write(rom_c)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ok("cli comphdr --all exit",
                   main([fixture_path, "comphdr", "--all", "--json"]), 0)
            doc = json.loads(buf.getvalue())
            ok("comphdr schema", doc["schema"], COMPHDR_SCHEMA)
            ok("comphdr generator", doc["generator"], COMPHDR_GENERATOR)
            ok("comphdr header size", doc["header_size"], COMPHDR_SIZE)
            ok("comphdr scope", doc["scope"], "all")
            ok("comphdr counts", doc["counts"],
               {"sections": 1, "holds": 1, "refuted": 0, "unparsed": 0,
                "exceptions": 0, "errors": 0})
            record = doc["sections"][0]
            ok("comphdr record key set", sorted(record),
               ["checks", "compressed_total", "error", "failed",
                "file_offset", "flags", "module", "payload_len",
                "payload_offset", "psize", "rva", "section", "segment",
                "uncompressed_len", "verdict", "vsize", "within_vsize"])
            ok("comphdr record identity",
               (record["segment"], record["module"], record["section"],
                record["rva"], record["vsize"], record["psize"],
                record["file_offset"]),
               (0, fixture["module"], "sec0", hx(fixture["rva"]),
                fixture["vsize"], fixture["psize"], 0x5000))
            ok("comphdr record header fields",
               (record["verdict"], record["uncompressed_len"],
                record["compressed_total"], record["flags"],
                record["payload_len"], record["payload_offset"]),
               ("HOLDS", fixture["fields"]["len_u24"],
                fixture["fields"]["compressed_total"], "0x10",
                fixture["fields"]["payload_len"], COMPHDR_SIZE))
            ok("comphdr record within vsize", record["within_vsize"], True)
            ok("comphdr record no failure", (record["failed"], record["error"]),
               ([], None))

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ok("cli comphdr MODULE exit",
                   main([fixture_path, "comphdr", "navimapcc.dll"]), 0)
            text = buf.getvalue()
            ok("comphdr text verdict", text.startswith("HOLDS"), True)
            ok("comphdr text lengths",
               "uncompressed_len=0x%x" % fixture["fields"]["len_u24"] in text,
               True)
            ok("comphdr text summary",
               "1 HOLDS, 0 REFUTED, 0 UNPARSED (exceptions: 0)" in text, True)

        # A corrupt flag byte must refute, not crash or silently hold.
        bad_rom = bytearray(build_comphdr_rom(base["prefix"], base["vsize"],
                                              base["psize"]))
        bad_rom[0x5000 + 6] = 0x11
        bad_path = os.path.join(td, "comphdr-bad.img")
        with open(bad_path, "wb") as fh:
            fh.write(bad_rom)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli comphdr corrupt exit",
               main([bad_path, "comphdr", "--all"]), 1)
        ok("comphdr corrupt verdict in text", "REFUTED" in buf.getvalue(), True)
        ok("comphdr corrupt names the check",
           "flags_is_0x10" in buf.getvalue(), True)
        ok("comphdr corrupt summary",
           "0 HOLDS, 1 REFUTED, 0 UNPARSED (exceptions: 1)" in buf.getvalue(),
           True)

        # Negative control on the main synthetic ROM: its LZSS/LZX streams do
        # not carry this header, so --all must refute both, not bless them.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli comphdr --all on non-M1.2a streams exit",
               main([path, "comphdr", "--all", "--json"]), 1)
        doc = json.loads(buf.getvalue())
        ok("comphdr refutes the LZSS stream and cannot parse the 4-byte LZX one",
           (doc["counts"]["refuted"], doc["counts"]["holds"],
            doc["counts"]["unparsed"]), (1, 0, 1))
        ok("comphdr exception count includes every non-HOLDS",
           doc["counts"]["exceptions"], 2)

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ok("cli comphdr needs MODULE or --all exit",
               main([path, "comphdr"]), 2)
        ok("comphdr usage message", "MODULE or --all" in err.getvalue(), True)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ok("cli comphdr rejects MODULE plus --all",
               main([path, "comphdr", "NK.EXE", "--all"]), 2)
        ok("comphdr both-selection message",
           "not both" in err.getvalue(), True)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ok("cli comphdr unknown module exit",
               main([path, "comphdr", "Nope.dll"]), 2)
        ok("comphdr unknown module message", "Nope.dll" in err.getvalue(), True)

        # --- thunks: EXP-50 stubs resolved through OFT + exports (M1.6b) ---
        thunk_rom, thunk_exp = build_thunks_rom()
        tpath = os.path.join(td, "thunks-rom.img")
        with open(tpath, "wb") as fh:
            fh.write(thunk_rom)
        tdata = thunk_rom
        tr = CERom(tdata, thunk_exp["image_start"])
        ok("thunks VA mapping is linear",
           (tr.va2file(thunk_exp["code_va"]), tr.va2file(thunk_exp["data_va"])),
           (0x5000, 0x6000))
        ok("thunks import slots match the stubs' literals",
           sorted(slot for _dll, slot, _n, _o in tr.imports(tr.module("NAVI.EXE"))),
           sorted(thunk_exp["slots"]))

        tsha = hashlib.sha256(thunk_rom).hexdigest()
        thunks = thunks_report(thunk_rom, tpath, len(thunk_rom), tsha,
                               all_modules=True)
        ok("thunks schema", thunks["schema"], THUNKS_SCHEMA)
        ok("thunks generator", thunks["generator"], THUNKS_GENERATOR)
        ok("thunks image basename", thunks["image"], "thunks-rom.img")
        ok("thunks image sha256", thunks["image_sha256"], tsha)
        ok("thunks scope is all", thunks["scope"], "all")
        ok("thunks record key order", list(thunks["stubs"][0]),
           list(THUNKS_RECORD_KEYS))

        stubs = thunks["stubs"]
        ok("thunks stub count", len(stubs), thunk_exp["stub_count"])
        ok("thunks stub VAs", [stub["stub_va"] for stub in stubs],
           [hx(va) for va in thunk_exp["stub_vas"]])
        ok("thunks slot VAs",
           [stub["slot_va"] for stub in stubs],
           [hx(thunk_exp["slots"][0]), hx(thunk_exp["slots"][1]), "0x7fff0000"])
        ok("thunks section labels", [stub["section"] for stub in stubs],
           ["sec0", "sec0", "sec0"])
        ok("thunks patterns", [stub["pattern"] for stub in stubs],
           ["4-insn", "3-insn", "4-insn"])
        ok("thunks owner", [stub["owner"] for stub in stubs],
           ["NAVI.EXE", "NAVI.EXE", "NAVI.EXE"])
        ok("thunks segment index", [stub["segment"] for stub in stubs], [0, 0, 0])
        ok("thunks resolved module/export/ordinal",
           [(stub["module"], stub["export"], stub["ordinal"])
            for stub in stubs[:2]],
           [("OBJDLL.DLL", thunk_exp["export_names"][0],
             thunk_exp["export_ordinals"][0]),
            ("OBJDLL.DLL", thunk_exp["export_names"][1],
             thunk_exp["export_ordinals"][1])])
        ok("thunks confidence table",
           [stub["confidence"] for stub in stubs], ["high", "medium", "low"])
        ok("thunks unresolved status/reason",
           (stubs[2]["status"], stubs[2]["reason"]),
           ("unresolved", "slot outside image"))
        ok("thunks unresolved record has no name",
           (stubs[2]["module"], stubs[2]["export"], stubs[2]["ordinal"]),
           (None, None, None))
        ok("thunks counts",
           (thunks["counts"]["stubs"], thunks["counts"]["resolved"],
            thunks["counts"]["unresolved"], thunks["counts"]["outside_image"],
            thunks["counts"]["no_export"], thunks["counts"]["ambiguous"]),
           (3, 2, 1, 1, 0, 0))
        ok("thunks import slot counts",
           (thunks["counts"]["import_slots"],
            thunks["counts"]["covered_slots"]), (2, 2))
        ok("thunks stub coverage", thunks["coverage"]["stubs"],
           {"resolved": 2, "total": 3, "percent": 66.7})
        ok("thunks slot coverage", thunks["coverage"]["slots"],
           {"covered": 2, "total": 2, "percent": 100.0})
        ok("thunks module summary",
           [(entry["module"], entry["stubs"], entry["resolved"],
             entry["import_slots"], entry["covered_slots"],
             entry["stub_coverage"], entry["slot_coverage"])
            for entry in thunks["modules"]],
           [("OBJDLL.DLL", 0, 0, 0, 0, 100.0, 100.0),
            ("NAVI.EXE", 3, 2, 2, 2, 66.7, 100.0)])
        ok("thunks scanned section count",
           [entry["scanned_sections"] for entry in thunks["modules"]], [0, 1])

        # Resolution reasons that the synthetic stubs do not produce.
        ambiguous = resolve_thunk(
            thunk_exp["slots"][0], tdata, tr,
            {thunk_exp["slots"][0]: [
                {"dll": "A.dll", "name": "x", "ordinal": None},
                {"dll": "B.dll", "name": "y", "ordinal": None}]},
            {}, {})
        ok("thunks ambiguous duplicate reason",
           ambiguous["reason"].startswith("ambiguous duplicate ("), True)
        missing = resolve_thunk(thunk_exp["data_va"], tdata, tr, {}, {}, {})
        ok("thunks no export match reason", missing["reason"],
           "no export match")

        # CLI: --all --json, MODULE selection, text layout, --min-coverage.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli thunks --all --json exit",
               main([tpath, "thunks", "--all", "--json"]), 0)
        doc = json.loads(buf.getvalue())
        ok("thunks json schema", doc["schema"], THUNKS_SCHEMA)
        ok("thunks json key order", list(doc["stubs"][0]),
           list(THUNKS_RECORD_KEYS))
        ok("thunks json stub VAs", [stub["stub_va"] for stub in doc["stubs"]],
           [hx(va) for va in thunk_exp["stub_vas"]])
        ok("thunks json coverage", doc["coverage"], thunks["coverage"])

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli thunks MODULE exit (case-insensitive)",
               main([tpath, "thunks", "navi.exe"]), 0)
        text = buf.getvalue()
        ok("thunks text groups by module", "NAVI.EXE (segment 0)" in text, True)
        ok("thunks text prints stub coverage", "2/3 stub(s) (66.7 %)" in text,
           True)
        ok("thunks text prints slot coverage", "2/2 slot(s) (100.0 %)" in text,
           True)
        ok("thunks text prints the unresolved reason",
           "UNRESOLVED (slot outside image)" in text, True)

        # --min-coverage gates on slot coverage (M1.6b/c: the primary measure).
        # Synthetic ROM: slot coverage 100%, so 100 passes and 101 is invalid.
        for label, threshold, want in (("--min-coverage below", 60, 0),
                                       ("--min-coverage at slot 100%", 100, 0)):
            with contextlib.redirect_stdout(io.StringIO()):
                with contextlib.redirect_stderr(io.StringIO()):
                    ok("cli thunks %s exit" % label,
                       main([tpath, "thunks", "--all",
                             "--min-coverage", str(threshold)]), want)
        with contextlib.redirect_stderr(io.StringIO()):
            ok("cli thunks --min-coverage >100 exit",
               main([tpath, "thunks", "--all", "--min-coverage", "101"]), 2)

        # M1.6c regression: module-local VAs (realaddr in 0x0001xxxx, not ROM
        # VA space) must not break stub/literal reads.  This reproduces the
        # root cause of C-1714 ("no import stub matched" on real Navi.exe).
        lrom, lexp = build_thunks_rom(local_va=True)
        lpath = os.path.join(td, "thunks-localva.img")
        with open(lpath, "wb") as fh:
            fh.write(lrom)
        lr = CERom(lrom, lexp["image_start"])
        ok("local-va va_base differs from module vbase",
           lr.va_base != lexp["navi_vbase"], True)
        # va2file now resolves module-local VAs via section realaddr mapping
        # (the M1.6c fix); it must map to the same file bytes as dataptr.
        ok("local-va va2file resolves module-local VA",
           0 <= lr.va2file(lexp["code_va"]) < len(lrom), True)
        lreport = thunks_report(lrom, lpath, len(lrom), all_modules=True)
        lstubs = lreport["stubs"]
        ok("local-va finds 3 stubs (M1.6c root cause fixed)",
           len(lstubs), lexp["stub_count"])
        ok("local-va stub VAs are module-local",
           [s["stub_va"] for s in lstubs], [hx(v) for v in lexp["stub_vas"]])
        ok("local-va slot VAs resolve", [s["slot_va"] for s in lstubs],
           [hx(lexp["slots"][0]), hx(lexp["slots"][1]), "0x7fff0000"])
        ok("local-va resolves module/export",
           [(s["module"], s["export"], s["ordinal"]) for s in lstubs[:2]],
           [("OBJDLL.DLL", lexp["export_names"][0], lexp["export_ordinals"][0]),
            ("OBJDLL.DLL", lexp["export_names"][1], lexp["export_ordinals"][1])])
        ok("local-va slot coverage 100%",
           lreport["coverage"]["slots"]["percent"], 100.0)
        with contextlib.redirect_stdout(io.StringIO()):
            ok("cli thunks local-va MODULE exit",
               main([lpath, "thunks", "navi.exe"]), 0)

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ok("cli thunks unknown module exit",
               main([tpath, "thunks", "Nope.dll"]), 2)
        ok("thunks unknown module message", "Nope.dll" in err.getvalue(), True)

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ok("cli thunks needs MODULE or --all exit",
               main([tpath, "thunks"]), 2)
        ok("thunks usage message", "MODULE or --all" in err.getvalue(), True)

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ok("cli thunks rejects MODULE plus --all",
               main([tpath, "thunks", "NAVI.EXE", "--all"]), 2)
        ok("thunks both-selection message", "not both" in err.getvalue(), True)

        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(err):
                ok("cli thunks module with no stub exit",
                   main([tpath, "thunks", "OBJDLL.DLL"]), 2)
        ok("thunks no-stub message", "no import stub" in err.getvalue(),
           True)

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

        # The discovery must not invent a segment (or crash) on the same bytes.
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ok("cli decompress corrupt image exit",
               main([os.path.join(td, "corrupt.img"), "decompress"]), 2)
        ok("cli decompress corrupt image message",
           "no valid CE segment" in err.getvalue(), True)

        # --- cross-image import name resolution (M1.9) --------------------
        sym, resolved, note = resolve_import_entry(
            "COREDLL.DLL", None, 1145,
            {"coredll.dll": {"display": "coredll.dll",
                             "by_name": {"_wfopen": 1145},
                             "by_ordinal": {1145: "_wfopen"}}},
            {"coredll.dll": "coredll.dll"})
        ok("resolve ordinal 1145 -> COREDLL!_wfopen", (sym, resolved),
           ("COREDLL!_wfopen", True))
        sym2, resolved2, note2 = resolve_import_entry(
            "COREDLL.DLL", None, 9999, {}, {})
        ok("resolve unknown ordinal stays unresolved",
           (sym2, resolved2, note2 is not None and "no export table" in note2),
           ("#9999", False, True))
        sym3, resolved3, _ = resolve_import_entry(
            "SYS_INF.DLL", "SomeName", None, {}, {})
        ok("resolve named import keeps MODULE!name", (sym3, resolved3),
           ("SYS_INF!SomeName", True))

        names_path = os.path.join(td, "names.json")
        with open(names_path, "w", encoding="utf-8") as fh:
            json.dump({"modules": {"coredll.dll": {"1145": "_wfopen"},
                                   "commondll.dll": {"7": "Foo"}}}, fh)
        ex_n, mn_n = load_names_json(names_path)
        ok("load_names_json modules shape",
           ex_n["coredll.dll"]["by_ordinal"][1145], "_wfopen")
        names_path2 = os.path.join(td, "names2.json")
        with open(names_path2, "w", encoding="utf-8") as fh:
            json.dump({"COREDLL.DLL": {"1145": "_wfopen"}}, fh)
        ex_n2, _ = load_names_json(names_path2)
        ok("load_names_json flat shape",
           ex_n2["coredll.dll"]["by_ordinal"][1145], "_wfopen")

        trom, tlayout = build_thunks_rom()
        tpath = os.path.join(td, "thunks.img")
        with open(tpath, "wb") as fh:
            fh.write(trom)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli imports no resolver exit", main([tpath, "imports", "NAVI.EXE"]), 0)
        out = buf.getvalue()
        ok("cli imports no resolver shows ordinal #6",
           "OBJDLL.DLL" in out and "#6" in out, True)
        ok("cli imports no resolver shows named import",
           "MAL_DataVol_getOffset" in out, True)

        obj_names = os.path.join(td, "objnames.json")
        with open(obj_names, "w", encoding="utf-8") as fh:
            json.dump({"OBJDLL.DLL": {"6": "MAL_DataVol_getSize"}}, fh)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli imports --names exit",
               main([tpath, "imports", "NAVI.EXE", "--names", obj_names]), 0)
        out = buf.getvalue()
        ok("cli imports --names resolves ordinal",
           "OBJDLL!MAL_DataVol_getSize" in out, True)
        ok("cli imports --names summary",
           "resolved" in out and "unresolved" in out, True)
        ok("cli imports --names no #6 left unresolved in lines",
           "\n" in out and "  OBJDLL" not in out.replace("OBJDLL!MAL_DataVol_getSize", ""), True)

        # --resolve-with: exporter and importer in the same synthetic image
        # (thunks ROM has OBJDLL exporter + NAVI importer). Resolving against
        # the same segment start proves the loader path.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli imports --resolve-with exit",
               main([tpath, "imports", "NAVI.EXE",
                     "--resolve-with", "0x%x" % tlayout["image_start"]]), 0)
        out = buf.getvalue()
        ok("cli imports --resolve-with resolves ordinal 6",
           "OBJDLL!MAL_DataVol_getSize" in out, True)

        # Realistic coredll #1145 case via --names (end-to-end shape).
        coredll_names = os.path.join(td, "coredll.json")
        with open(coredll_names, "w", encoding="utf-8") as fh:
            json.dump({"modules": {"coredll.dll": {"1145": "_wfopen"}}}, fh)
        ex_c, mn_c = load_names_json(coredll_names)
        sym_c, res_c, _ = resolve_import_entry(
            "COREDLL.DLL", None, 1145, ex_c, mn_c)
        ok("coredll #1145 -> COREDLL!_wfopen via names file",
           (sym_c, res_c), ("COREDLL!_wfopen", True))

    print("cerom selftest: %d checks OK (synthetic ROM, no vendor data)" % len(checks))
    return 0


def decompress_command(args, data):
    """Run ``decompress``: classify (and optionally write) compressed sections."""
    try:
        cc = cecompress_module()
    except ImportError as exc:
        print("error: cannot import tools/cecompress.py: %s" % exc, file=sys.stderr)
        return 2

    modules = None
    if args.modules is not None:
        modules = [name.strip() for name in args.modules.split(",") if name.strip()]
        if not modules:
            print("error: --modules names no module", file=sys.stderr)
            return 2
    selector = None
    if args.section is not None:
        try:
            selector = section_selector(args.section)
        except ValueError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2

    image_size = os.path.getsize(args.image)
    try:
        report = decompress_report(
            data, args.image, image_size, hashlib.sha256(data).hexdigest(),
            sha256_scope=sha256_scope_text(len(data), image_size),
            modules=modules, section=selector, method=args.method,
            out_dir=args.out, check=args.check, image_start=args.image_start)
    except cc.CeCompressError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    except KeyError as exc:
        print("error: no module named %s in this ROM" % exc.args[0], file=sys.stderr)
        return 2
    except OSError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if not report["counts"]["sections"]:
        print("error: no IMAGE_SCN_COMPRESSED section matched "
              "(--modules %s, --section %s)" % (args.modules, args.section),
              file=sys.stderr)
        return 2

    if args.json:
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
    else:
        print_decompress_text(report)

    counts = report["counts"]
    if counts["errors"]:
        return 1
    return 0 if counts["ok"] == counts["sections"] else 1


def comphdr_command(args, data):
    """Run ``comphdr``: parse and validate the 22-byte section header."""
    if args.all_sections and args.module:
        print("error: give MODULE or --all, not both", file=sys.stderr)
        return 2
    if not args.all_sections and not args.module:
        print("error: comphdr needs MODULE or --all", file=sys.stderr)
        return 2

    image_size = os.path.getsize(args.image)
    try:
        report = comphdr_report(
            data, args.image, image_size, hashlib.sha256(data).hexdigest(),
            sha256_scope=sha256_scope_text(len(data), image_size),
            module=args.module, all_sections=args.all_sections,
            image_start=args.image_start)
    except KeyError as exc:
        print("error: no module named %s in this ROM" % exc.args[0],
              file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if not report["counts"]["sections"]:
        print("error: no IMAGE_SCN_COMPRESSED section matched (module %s, "
              "--all %s)" % (args.module, args.all_sections), file=sys.stderr)
        return 2

    if args.json:
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
    else:
        print_comphdr_text(report)
    return 0 if report["counts"]["exceptions"] == 0 else 1


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


def thunks_command(args, data):
    """Run ``thunks``: resolve import stubs/call sites and print coverage."""
    if args.all_modules and args.module:
        print("error: give MODULE or --all, not both", file=sys.stderr)
        return 2
    if not args.all_modules and not args.module:
        print("error: thunks needs MODULE or --all", file=sys.stderr)
        return 2
    if args.min_coverage is not None and not 0 <= args.min_coverage <= 100:
        print("error: --min-coverage must be 0..100", file=sys.stderr)
        return 2

    image_size = os.path.getsize(args.image)
    try:
        report = thunks_report(
            data, args.image, image_size, hashlib.sha256(data).hexdigest(),
            sha256_scope=sha256_scope_text(len(data), image_size),
            module=args.module, all_modules=args.all_modules,
            image_start=args.image_start,
            resolve_starts=getattr(args, "resolve_with", None),
            names_path=getattr(args, "names", None))
    except KeyError as exc:
        print("error: no module named %s in this ROM" % exc.args[0],
              file=sys.stderr)
        return 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if not report["counts"]["stubs"]:
        print("error: no import stub/call site matched (module %s, --all %s)"
              % (args.module, args.all_modules), file=sys.stderr)
        return 2

    if args.json:
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
    else:
        print_thunks_text(report)

    if args.min_coverage is not None:
        slots = report["coverage"]["slots"]
        if slots["total"] and slots["percent"] < args.min_coverage:
            print("error: slot coverage below --min-coverage %g: %d/%d (%.1f %%)"
                  % (args.min_coverage, slots["covered"], slots["total"],
                     slots["percent"]), file=sys.stderr)
            return 1
    return 0


def scan_all_segments(data, offset=0):
    """Return every valid CE segment in ``data`` (copies included).

    Unlike :func:`find_segments`, duplicates are NOT collapsed: the result
    mirrors the legacy ``tools/ce_rom_parse.py`` whole-image scan, which lists
    build A, its copy, build B, its copy and build C as five segments.
    """
    candidates = []
    found = 0
    while True:
        found = data.find(b"ECEC", found)
        if found < 0:
            break
        if found >= 0x40 and (found - 0x40) not in candidates and (found - 0x40) >= offset:
            candidates.append(found - 0x40)
        found += 1

    segments = []
    for start in candidates:
        try:
            segment = CERom(data, start)
        except (ValueError, struct.error):
            continue
        header = segment.hdr
        if not 0 < header["nummods"] <= SEGMENT_MAX_MODULES:
            continue
        if not header["physfirst"] <= segment.ptoc < header["physlast"]:
            continue
        toc_end = (segment.hdr_off + ROMHDR_SIZE + TOC_SIZE * header["nummods"]
                   + FILES_SIZE * header["numfiles"])
        if toc_end > len(data):
            continue
        segments.append(segment)
    return segments


def scan_report(data, image_name, image_size, image_sha256=None, offset=0):
    """Build a JSON report in the legacy ``ce_rom_parse.py`` shape."""
    segments_out = []
    for seg in scan_all_segments(data, offset=offset):
        modules = []
        for m in seg.modules():
            modules.append({
                "index": m["index"],
                "kind": "module",
                "dwFileAttributes": m["attrib"],
                "ftTime": m["ft"],
                "nFileSize": m["size"],
                "lpszFileName_ptr": m["e32"],
                "name": m["name"],
                "ulE32Offset": m["e32"],
                "ulO32Offset": m["o32"],
                "ulLoadOffset": m["load"],
            })
        files = []
        for f in seg.files():
            files.append({
                "index": f["index"],
                "kind": "file",
                "dwFileAttributes": f["attrib"],
                "ftTime": f["ft"],
                "nFileSize": f["rsize"],
                "rsize": f["rsize"],
                "csize": f["csize"],
                "name": f["name"],
                "ulLoadOffset": f["load"],
            })
        segments_out.append({
            "segment_base": seg.start,
            "ecec_offset": seg.start + 0x40,
            "pTOC": seg.ptoc,
            "size": seg.toc_off,
            "romhdr_offset": seg.hdr_off,
            "phys_base": seg.hdr["physfirst"],
            "romhdr": dict(seg.hdr),
            "modules": modules,
            "files": files,
        })
    return {
        "image": os.path.abspath(image_name),
        "image_size": image_size,
        "image_sha256": image_sha256,
        "segments": segments_out,
    }


def print_scan_text(report, segments):
    print("image: %s" % report["image"])
    print("sha256: %s" % report["image_sha256"])
    print("segments: %d" % len(segments))
    for seg in segments:
        rh = seg.hdr
        print("--- segment base 0x%x (ECEC 0x%x) ---" % (seg.start, seg.start + 0x40))
        print("pTOC=0x%x size=0x%x romhdr=0x%x phys_base=0x%x" % (seg.ptoc, seg.toc_off, seg.hdr_off, rh["physfirst"]))
        print("nummods=%d numfiles=%d cpu=0x%04x physfirst=0x%x physlast=0x%x ulCopyEntries=%d pExtensions=0x%x"
              % (rh["nummods"], rh["numfiles"], rh["usCPUType"], rh["physfirst"], rh["physlast"],
                 rh["ulCopyEntries"], rh["pExtensions"]))
        mod_names = [m["name"] for m in seg.modules() if m["name"]]
        print("modules (%d): %s" % (len(mod_names), " ".join(mod_names)))
        file_names = [f["name"] for f in seg.files() if f["name"]]
        if file_names:
            print("files (%d): %s" % (len(file_names), " ".join(file_names)))


def scan_command(args, data):
    offset = getattr(args, "offset", 0) or 0
    segments = scan_all_segments(data, offset=offset)
    image_sha = hashlib.sha256(data).hexdigest()
    report = scan_report(data, args.image, len(data), image_sha, offset=offset)
    if getattr(args, "out", None):
        import os as _os
        _os.makedirs(_os.path.dirname(_os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            f.write("\n")
    if getattr(args, "json", False):
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    print_scan_text(report, segments)
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
    p = sub.add_parser("scan",
                       help="scan the whole image for CE ROM (ECEC) segments")
    p.add_argument("--offset", type=lambda x: int(x, 0), default=0,
                   help="only segments at or after this file offset (default 0)")
    p.add_argument("--out", help="write a JSON report to this path")
    p.add_argument("--json", action="store_true", help="print the JSON report")
    p = sub.add_parser("files",
                       help="list FILESentry records; optionally extract/decode")
    p.add_argument("--extract", metavar="DIR",
                   help="write the stored csize bytes of every csize != rsize entry")
    p.add_argument("--decompress", action="store_true",
                   help="decode extracted payloads through tools/cecompress.py")
    p.add_argument("--method", default="auto",
                   help="auto (default), lzss/cecompress or lzx")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p = sub.add_parser("sections"); p.add_argument("module")
    p = sub.add_parser("exports"); p.add_argument("module")
    p = sub.add_parser("imports",
                       help="list import slots; resolve ordinals via --resolve-with/--names")
    p.add_argument("module")
    p.add_argument("--resolve-with", action="append", type=lambda s: int(s, 0),
                   metavar="IMAGE_START",
                   help="CE segment image-start (hex) in the same image whose exports "
                        "resolve ordinal imports (repeatable, e.g. 0x3e00200)")
    p.add_argument("--names", metavar="FILE",
                   help="JSON export-names DB used to resolve ordinal imports")
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
    p = sub.add_parser("decompress",
                       help="decode IMAGE_SCN_COMPRESSED o32 sections (M1.3)")
    p.add_argument("--modules", help="comma-separated module names (default: all)")
    p.add_argument("--section", metavar="NAME",
                   help="only sec<N>, MODULE/sec<N> or an RVA in hex")
    p.add_argument("--method", default="auto",
                   help="auto (default), lzss/cecompress or lzx")
    p.add_argument("--out", metavar="DIR",
                   help="write each OK decode as <module>.<rva>.bin")
    p.add_argument("--check", action="store_true",
                   help="decode only, write nothing (default without --out)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p = sub.add_parser("comphdr",
                       help="parse the 22-byte compressed-section header (M1.2a)")
    p.add_argument("module", nargs="?",
                   help="module name to inspect (case-insensitive)")
    p.add_argument("--all", dest="all_sections", action="store_true",
                   help="every IMAGE_SCN_COMPRESSED section in every segment")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p = sub.add_parser("thunks",
                       help="resolve import stubs/call sites to module!export (M1.6b/c)")
    p.add_argument("module", nargs="?",
                   help="module name to inspect (case-insensitive)")
    p.add_argument("--all", dest="all_modules", action="store_true",
                   help="every module in every discovered segment")
    p.add_argument("--resolve-with", action="append", type=lambda s: int(s, 0),
                   metavar="IMAGE_START",
                   help="CE segment image-start(s) whose exports resolve ordinal "
                        "imports (repeatable, e.g. 0x3e00200)")
    p.add_argument("--names", metavar="FILE",
                   help="JSON export-names DB used to resolve ordinal imports")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--min-coverage", type=float, default=None, metavar="N",
                   help="exit 1 when stub or slot coverage is below N percent")
    a = ap.parse_args(argv)

    if a.selftest:
        return selftest()
    if a.image is None:
        ap.error("the following arguments are required: image")
    if a.cmd is None:
        ap.error("a subcommand is required (scan, romhdr, modules, files, sections, exports, "
                 "va2file, file2va, extract, memmap, decompress, comphdr, thunks)")

    try:
        with open(a.image, "rb") as fh:
            if a.cmd == "scan":
                data = fh.read()
            else:
                data = fh.read(128 << 20)
    except OSError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if a.cmd == "scan":
        return scan_command(a, data)

    if a.cmd == "decompress":
        return decompress_command(a, data)

    if a.cmd == "comphdr":
        return comphdr_command(a, data)

    if a.cmd == "thunks":
        return thunks_command(a, data)

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
        return files_command(a, r, data)
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
        try:
            ex_tables, mod_names = load_resolver_tables(
                data, getattr(a, "resolve_with", None), getattr(a, "names", None))
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2
        unresolved = []
        total = 0
        for dll, slot, nm, ordn in r.imports(r.module(a.module)):
            total += 1
            symbol, resolved, note = resolve_import_entry(
                dll, nm, ordn, ex_tables, mod_names)
            print("%-20s slot=%08x %s" % (dll, slot, symbol))
            if not resolved and ordn is not None:
                unresolved.append((dll, slot, ordn, note))
        if getattr(a, "resolve_with", None) or getattr(a, "names", None):
            resolved_n = total - len(unresolved)
            print("%d/%d resolved, %d unresolved" % (resolved_n, total, len(unresolved)))
            if unresolved:
                print("unresolved:")
                for dll, slot, ordn, note in unresolved:
                    print("  %-20s slot=%08x #%d  %s" % (dll, slot, ordn, note or ""))
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
