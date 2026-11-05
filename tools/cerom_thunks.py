#!/usr/bin/env python3
"""IAT thunk -> ``module!export`` resolver for one CE ROM segment.

Stdlib only. Reads the CE image with :mod:`cerom` (never edits it), builds an
export index over the segment, then maps a module's import address table to
symbolic targets so a disassembly shows ``OBJDLL!MAL_DataVol_getOffset``
instead of a raw ``0x0369xxxx``.

Two IAT shapes are handled:

* **import descriptor** -- the standard PE ``IMAGE_DIRECTORY_ENTRY_IMPORT``
  (``e32_unit[1]``): 20-byte ``IMAGE_IMPORT_DESCRIPTOR`` records, an optional
  ``OriginalFirstThunk`` (ILT with hint/name or ordinal entries) and the
  ``FirstThunk`` IAT slots whose stored value is the bound target;
* **pre-bound IAT** -- a Windows CE XIP ROM usually has **no** import
  descriptor (the loader's fixups are applied at link time), so the only
  evidence left is a run of consecutive ``u32`` slots inside a module's
  section that point at another module's export VAs.  ``resolve`` falls back
  to that shape automatically (``--force-scan`` also uses it when a
  descriptor does exist, as a cross-check).  A run must be at least
  ``--min-run`` slots long (default 2) so isolated pointers are not mistaken
  for a table.

The export index is built with ``cerom.CERom.exports()`` (named exports) and
backfilled from the export directory's ``AddressOfFunctions`` so
**ordinal-only** exports (present in the function table, absent from
``AddressOfNames``) are still resolvable as ``module!#ordinal``.  That matters
for ``COREDLL``-style ordinal imports.  Aliased exports (two ordinals at the
same RVA) stay separate entries and are reported *ambiguous* when a bare VA is
the only evidence.

Exit codes: ``0`` all slots resolved, ``1`` partial (any unresolved or
ambiguous slot, or nothing found to resolve), ``2`` usage/image error.
``exports`` and ``stats`` exit ``1`` only when part of the segment could not
be read.

**Honest scope.** The real check needs the vendor image (EU 2011
``LEAF_2011-2012_QSD-309-101_navi158_eu.img``,
SHA-256 ``105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307``);
that image is not in the repo, so every number this tool prints for it is
unverified.  ``--selftest`` proves only the *algorithm* on a synthetic ROM
(two modules, one export table with named, unnamed and aliased entries, a
hand-built import descriptor and a pre-bound slot run); it cannot prove that
the real ROM has a descriptor, that real IAT slots hold export VAs, or that
the boundary between a real IAT and ordinary data is detectable.  A pre-bound
image may expose **no** import descriptor, in which case the scan is a
heuristic, not a parse.

Usage::

    cerom_thunks.py IMG exports [--module-set A,B] [--json] [--list]
    cerom_thunks.py IMG resolve MODULE [--module-set A,B] [--json]
                                 [--force-scan] [--min-run N]
    cerom_thunks.py IMG stats [--module-set A,B] [--json]
    cerom_thunks.py --selftest
    cerom_thunks.py --write-fixture PATH   # synthetic ROM, no vendor bytes

``--module-set`` is the comma-separated **module-name** universe of the export
index (default: every named module in the segment); it is not a segment
selector.  ``--image-start`` (global, before the subcommand) pins the CE
segment when the image holds several.

See docs/format/cerom.md for the structures and
docs/experiments/EXP-2026-11-05-50-cerom-thunks.md for the evidence record.
"""
from __future__ import annotations

import argparse
import array
import bisect
import hashlib
import json
import os
import struct
import sys

import cerom

THUNKS_SCHEMA = "osm2leaf.cerom.thunks/v1"
INDEX_SCHEMA = "osm2leaf.cerom.exports/v1"
STATS_SCHEMA = "osm2leaf.cerom.thunkstats/v1"
GENERATOR = "tools/cerom_thunks.py"

IMPORT_DESC_SIZE = 20
IMAGE_ORDINAL_FLAG = 0x80000000
ORDINAL_MASK = 0xFFFF
MAX_FUNCS = 0x100000
MAX_IAT_SLOTS = 0x10000
#: VA bands a bound import slot may legitimately point into on this platform:
#: physical/module space (``0x8…``) and the module band seen in the code
#: (``0x02xxxxxx``/``0x03xxxxxx``, docs/format/cerom.md §7).
PLAUSIBLE_VA = ((0x80000000, 0x90000000), (0x02000000, 0x04000000))

STATUS_RESOLVED = "resolved"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_UNRESOLVED = "unresolved"

EXIT_OK, EXIT_PARTIAL, EXIT_ERROR = 0, 1, 2


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def hx(value):
    """Format an integer as ``0x…`` (the L3 JSON contract style)."""
    return "0x%x" % value


def norm_module(name):
    """Normalise a DLL/module name for index lookups (basename, lower case)."""
    if not name:
        return None
    return os.path.basename(name.strip().replace("\\", "/")).lower()


def u32_at(data, offset):
    if offset is None or offset < 0 or offset + 4 > len(data):
        return None
    return struct.unpack_from("<I", data, offset)[0]


def cstr_at(data, offset, limit=260):
    """NUL-terminated Latin-1 string at a file offset, or ``None``."""
    if offset is None or offset < 0 or offset >= len(data):
        return None
    end = data.find(b"\0", offset, offset + limit)
    if end < 0:
        return None
    return data[offset:end].decode("latin1")


def iter_u32(data, offset, count):
    """Yield ``count`` little-endian u32 values starting at ``offset``."""
    if count <= 0:
        return
    if offset % 4 == 0:
        chunk = data[offset:offset + 4 * count]
        values = array.array("I")
        values.frombytes(chunk[:len(chunk) & ~3])
        if sys.byteorder != "little":
            values.byteswap()
        yield from values
        return
    for i in range(count):
        yield struct.unpack_from("<I", data, offset + 4 * i)[0]


# --------------------------------------------------------------------------
# VA map: which module/section owns a VA, and RVA -> VA
# --------------------------------------------------------------------------


class VaMap:
    """Module and section VA ranges of one CE segment.

    ``o32_realaddr`` is the address the section occupies at runtime, so an RVA
    is translated through the section that contains it rather than through a
    single module base (docs/format/cerom.md §7); the sections of one module
    do not share one delta.
    """

    def __init__(self, image):
        self.modules = []       # (start, end, name)
        self.sections = []      # dict(module, index, va, end, rva)
        self.export_dirs = []   # (start, end, module)
        self.vbase = {}         # module name -> e32_vbase
        for module in image.modules():
            name = module["name"]
            if not name:
                continue
            try:
                header = image.e32(module)
                sections = list(image.o32(module))
            except (struct.error, ValueError, IndexError):
                continue
            self.modules.append(
                (header["vbase"], header["vbase"] + max(header["vsize"], 1), name))
            for index, section in enumerate(sections):
                span = max(section["vsize"], section["psize"], 1)
                self.sections.append(dict(
                    module=name, index=index, va=section["realaddr"],
                    end=section["realaddr"] + span, rva=section["rva"]))
            self.vbase[name] = header["vbase"]
            rva, size = header["export"]
            if rva and size:
                start = self.va_of_rva(name, rva, header["vbase"])
                self.export_dirs.append((start, start + size, name))
        self._sort()

    def _sort(self):
        # A scan looks up millions of words, so every range query is a bisect.
        self.modules.sort()
        self.sections.sort(key=lambda s: s["va"])
        self._module_starts = [m[0] for m in self.modules]
        self._section_starts = [s["va"] for s in self.sections]
        self._by_module = {}
        for section in self.sections:
            self._by_module.setdefault(section["module"], []).append(section)
        for bucket in self._by_module.values():
            bucket.sort(key=lambda s: s["rva"])
        self.min_va = self.modules[0][0] if self.modules else 0
        self.max_va = max((m[1] for m in self.modules), default=0)

    def va_of_rva(self, module_name, rva, vbase=None):
        """Runtime VA of ``rva`` inside ``module_name`` (section-relative)."""
        bucket = self._by_module.get(module_name)
        if bucket:
            i = bisect.bisect_right([s["rva"] for s in bucket], rva) - 1
            if i >= 0:
                section = bucket[i]
                if rva < section["rva"] + (section["end"] - section["va"]):
                    return section["va"] + (rva - section["rva"])
        base = vbase if vbase is not None else self.vbase.get(module_name)
        return None if base is None else base + rva

    def module_at(self, va):
        i = bisect.bisect_right(self._module_starts, va) - 1
        if i >= 0 and va < self.modules[i][1]:
            return self.modules[i][2]
        # Ranges are disjoint in a CE segment; check the neighbours anyway so
        # a malformed image cannot silently mis-attribute a VA.
        j = i - 1
        while j >= 0 and self.modules[j][1] > va:
            if self.modules[j][0] <= va:
                return self.modules[j][2]
            j -= 1
        return None

    def section_at(self, va):
        i = bisect.bisect_right(self._section_starts, va) - 1
        if i >= 0 and va < self.sections[i]["end"]:
            return self.sections[i]
        j = i - 1
        while j >= 0 and self.sections[j]["end"] > va:
            if self.sections[j]["va"] <= va:
                return self.sections[j]
            j -= 1
        return None

    def export_dir_at(self, va):
        for start, end, name in self.export_dirs:
            if start <= va < end:
                return name
        return None


# --------------------------------------------------------------------------
# Export index
# --------------------------------------------------------------------------


class Entry:
    """One export: a ``(module, ordinal)`` pair at one RVA/VA.

    ``names`` is empty for an ordinal-only export.  Aliased exports are
    separate entries with their own ordinal that happen to share an RVA.
    """

    __slots__ = ("module", "ordinal", "rva", "va", "names")

    def __init__(self, module, ordinal, rva, va, names):
        self.module = module
        self.ordinal = ordinal
        self.rva = rva
        self.va = va
        self.names = list(names)

    @property
    def name(self):
        return self.names[0] if self.names else None

    def label(self):
        if self.names:
            return "%s!%s" % (self.module, self.names[0])
        return "%s!#%d" % (self.module, self.ordinal)

    def to_dict(self):
        return dict(module=self.module, ordinal=self.ordinal, name=self.name,
                    names=list(self.names), rva=hx(self.rva), va=hx(self.va),
                    label=self.label())


class ExportIndex:
    """``module!name`` / ordinal / VA lookups over a set of modules."""

    def __init__(self):
        self.entries = []
        self.by_key = {}      # (module_lower, name_lower) -> Entry
        self.by_ordinal = {}  # (module_lower, ordinal) -> [Entry]
        self.by_va = {}       # va -> [Entry]
        self.modules = []     # [dict(name, vbase, entries, named, unnamed)]
        self.notes = []
        self.counts = dict(modules=0, with_exports=0, entries=0, named=0,
                           unnamed=0, aliased=0)

    def add(self, entry):
        self.entries.append(entry)
        key_module = norm_module(entry.module)
        for name in entry.names:
            self.by_key.setdefault((key_module, name.lower()), entry)
        self.by_ordinal.setdefault((key_module, entry.ordinal), []).append(entry)
        bucket = self.by_va.setdefault(entry.va, [])
        if entry not in bucket:
            bucket.append(entry)
        self.counts["entries"] += 1
        if entry.names:
            self.counts["named"] += 1
        else:
            self.counts["unnamed"] += 1

    def finish(self):
        self.counts["modules"] = len(self.modules)
        self.counts["with_exports"] = sum(1 for m in self.modules if m["entries"])
        self.counts["aliased"] = sum(
            1 for bucket in self.by_va.values() if len(bucket) > 1)
        return self

    def has_module(self, name):
        key = norm_module(name)
        return any(norm_module(m["name"]) == key for m in self.modules)

    def lookup_name(self, module, name):
        if not module or not name:
            return None
        return self.by_key.get((norm_module(module), name.lower()))

    def lookup_ordinal(self, module, ordinal):
        bucket = self.by_ordinal.get((norm_module(module), ordinal))
        return bucket[0] if bucket else None

    def lookup_va(self, va):
        return list(self.by_va.get(va, ()))


def read_function_table(image, module):
    """``(funcs, base, note)`` from the module's PE export directory.

    ``cerom.exports()`` yields named exports only, so an ordinal-only export
    is invisible through the API.  The 40-byte export directory (standard PE
    COFF layout, placed by ``e32_unit[0]``; docs/format/cerom.md §5) is read
    here only to recover ``AddressOfFunctions`` and its ordinal base; the
    names still come from ``cerom.exports()``.
    """
    try:
        header = image.e32(module)
    except (struct.error, ValueError, IndexError) as exc:
        return None, None, "e32_rom unreadable (%s)" % exc
    rva, size = header["export"]
    if not rva or size < 40:
        return None, None, None
    offset = image.rva2file(module, rva)
    if offset is None:
        return None, None, "export directory lies in a compressed/unmapped section"
    try:
        (_characteristics, _stamp, _major, _minor, _name_rva, base,
         nfun, nnam, funcs_rva, _names_rva, _ords_rva) = struct.unpack_from(
            "<IIHHIIIIIII", image.d, offset)
    except struct.error:
        return None, None, "export directory truncated"
    if not (0 < nfun < MAX_FUNCS) or not (0 <= nnam < MAX_FUNCS):
        return None, None, "implausible export counts (nfun=%d nnam=%d)" % (nfun, nnam)
    offset = image.rva2file(module, funcs_rva)
    if offset is None or offset + 4 * nfun > len(image.d):
        return None, None, "AddressOfFunctions unreadable"
    return struct.unpack_from("<%dI" % nfun, image.d, offset), base, None


def build_index(image, module_names=None, va_map=None):
    """Build the export index for ``module_names`` (default: every module).

    Raises ``KeyError`` (first unknown name) and ``ValueError`` (empty set) so
    the CLI can turn them into exit 2.
    """
    va_map = va_map or VaMap(image)
    modules = [m for m in image.modules() if m["name"]]
    if module_names:
        available = {norm_module(m["name"]) for m in modules}
        missing = [n for n in module_names if norm_module(n) not in available]
        if missing:
            raise KeyError(missing[0])
        wanted = {norm_module(n) for n in module_names}
        modules = [m for m in modules if norm_module(m["name"]) in wanted]
    if not modules:
        raise ValueError("no module selected")

    index = ExportIndex()
    for module in modules:
        name = module["name"]
        try:
            vbase = image.e32(module)["vbase"]
        except (struct.error, ValueError, IndexError) as exc:
            index.notes.append("%s: e32_rom unreadable (%s)" % (name, exc))
            index.modules.append(dict(name=name, vbase=None, entries=0,
                                      named=0, unnamed=0))
            continue

        named = {}   # ordinal -> [(name, rva)]
        try:
            for ordinal, export_name, rva in image.exports(module):
                named.setdefault(ordinal, []).append((export_name, rva))
        except (struct.error, ValueError, IndexError) as exc:
            index.notes.append("%s: exports() failed (%s)" % (name, exc))

        funcs, base, note = read_function_table(image, module)
        if note:
            index.notes.append("%s: %s" % (name, note))

        entries_before = len(index.entries)
        if funcs is not None:
            for i, rva in enumerate(funcs):
                if not rva:
                    continue
                ordinal = base + i
                # An ordinal with no AddressOfNames entry is ordinal-only.
                names = [n for n, r in named.get(ordinal, ()) if r == rva]
                va = va_map.va_of_rva(name, rva, vbase)
                index.add(Entry(name, ordinal, rva, va, names))
            for ordinal, bucket in named.items():
                for export_name, rva in bucket:
                    if ordinal < base or ordinal - base >= len(funcs):
                        index.notes.append(
                            "%s!%s: ordinal %d outside AddressOfFunctions"
                            % (name, export_name, ordinal))
                    elif funcs[ordinal - base] != rva:
                        index.notes.append(
                            "%s!%s: exports() rva 0x%x != AddressOfFunctions 0x%x"
                            % (name, export_name, rva, funcs[ordinal - base]))
        else:
            # No readable function table: fall back to the names we did get.
            for ordinal, bucket in sorted(named.items()):
                for export_name, rva in bucket:
                    va = va_map.va_of_rva(name, rva, vbase)
                    index.add(Entry(name, ordinal, rva, va, [export_name]))

        mine = index.entries[entries_before:]
        index.modules.append(dict(
            name=name, vbase=vbase, entries=len(mine),
            named=sum(1 for e in mine if e.names),
            unnamed=sum(1 for e in mine if not e.names)))
    return index.finish()


# --------------------------------------------------------------------------
# VA classification: the single source of truth for a bare target
# --------------------------------------------------------------------------


def classify_va(index, va_map, va):
    """Classify a bare VA against the index and the segment's VA map.

    Returns ``dict(status, candidates, reason, module, section)``.  A wrong
    hypothesis yields a reason, never a guessed name.
    """
    result = dict(status=STATUS_UNRESOLVED, candidates=[], reason=None,
                  module=None, section=None)
    if va is None:
        result["reason"] = "unreadable"
        return result
    if va == 0:
        result["reason"] = "null-slot"
        return result

    candidates = index.lookup_va(va)
    if len(candidates) == 1:
        result.update(status=STATUS_RESOLVED, candidates=candidates)
        return result
    if len(candidates) > 1:
        result.update(status=STATUS_AMBIGUOUS, candidates=candidates)
        return result

    section = va_map.section_at(va)
    if section is not None:
        result["section"] = section
        result["module"] = section["module"]
    else:
        result["module"] = va_map.module_at(va)
    if va_map.export_dir_at(va):
        # An export RVA that points back into the export directory is a
        # forwarder ("OTHERDLL.Function"), not code.
        result["reason"] = "forwarder"
    elif section is not None:
        result["reason"] = "no-export"
    elif result["module"]:
        result["reason"] = "no-section"
    else:
        result["reason"] = "outside-image"
    return result


def make_slot(number, iat_va, ilt_raw, raw):
    return dict(slot=number,
                iat_va=hx(iat_va) if iat_va is not None else None,
                ilt=hx(ilt_raw) if ilt_raw is not None else None,
                raw=hx(raw) if raw is not None else None,
                declared=None, target=None, module=None, name=None,
                ordinal=None, rva=None, status=STATUS_UNRESOLVED, via=None,
                reason=None, va_check=None, candidates=[])


def _resolved(slot, entry, via, check):
    slot["target"] = entry.label()
    slot["module"] = entry.module
    slot["name"] = entry.name
    slot["ordinal"] = entry.ordinal
    slot["rva"] = hx(entry.rva)
    slot["status"] = STATUS_RESOLVED
    slot["via"] = via          # evidence path: name | ordinal | va
    slot["reason"] = None
    slot["candidates"] = [entry.label()]
    slot["va_check"] = check
    return slot


def resolve_slot(index, va_map, dll, declared_name, declared_ordinal, raw, slot):
    """Resolve one IAT slot: declaration first, bound VA as corroboration.

    Precedence: ILT name -> ILT ordinal -> bound VA.  The declaration is the
    identity the image *claims*; the bound VA is the evidence that the claim
    was applied.  A disagreement is reported in ``va_check``, never silently
    preferred.
    """
    declared_entry = None
    if not dll:
        # The descriptor's name pointer was unreadable: only the bound VA can
        # still identify the slot.
        slot["reason"] = "no-import-name"
    elif declared_name:
        slot["declared"] = "%s!%s" % (dll, declared_name)
        declared_entry = index.lookup_name(dll, declared_name)
        if declared_entry is None:
            slot["reason"] = ("dll-not-in-index" if not index.has_module(dll)
                              else "name-not-exported")
    elif declared_ordinal is not None:
        slot["declared"] = "%s!#%d" % (dll, declared_ordinal)
        declared_entry = index.lookup_ordinal(dll, declared_ordinal)
        if declared_entry is None:
            slot["reason"] = ("dll-not-in-index" if not index.has_module(dll)
                              else "ordinal-not-exported")

    va_state = classify_va(index, va_map, raw)
    if declared_entry is not None:
        check = "unresolved"
        if va_state["status"] == STATUS_RESOLVED:
            check = "match" if va_state["candidates"][0] is declared_entry else "mismatch"
        elif va_state["status"] == STATUS_AMBIGUOUS:
            check = "match" if declared_entry in va_state["candidates"] else "mismatch"
        return _resolved(slot, declared_entry, "name" if declared_name else "ordinal",
                         check)

    if va_state["status"] == STATUS_RESOLVED:
        entry = va_state["candidates"][0]
        return _resolved(slot, entry, "va", "match")
    if va_state["status"] == STATUS_AMBIGUOUS:
        slot["status"] = STATUS_AMBIGUOUS
        slot["reason"] = "ambiguous"
        slot["candidates"] = [e.label() for e in va_state["candidates"]]
        return slot
    slot["reason"] = slot["reason"] or va_state["reason"]
    return slot


# --------------------------------------------------------------------------
# Import descriptors (standard PE shape)
# --------------------------------------------------------------------------


def read_rva_u32(image, module, rva, offset=0):
    if rva is None:
        return None
    return u32_at(image.d, image.rva2file(module, rva + offset))


def import_descriptors(image, module):
    """``(descriptors, note)``; ``descriptors is None`` means "no descriptor"."""
    try:
        header = image.e32(module)
    except (struct.error, ValueError, IndexError) as exc:
        return None, "e32_rom unreadable (%s)" % exc
    rva, size = header["imp"]
    if not rva:
        return None, None
    if size < IMPORT_DESC_SIZE:
        return None, "import directory rva=0x%x size=0x%x" % (rva, size)
    offset = image.rva2file(module, rva)
    if offset is None:
        return None, "import directory lies in a compressed/unmapped section"

    out = []
    count = min(size // IMPORT_DESC_SIZE, 4096)
    for i in range(count):
        record = offset + IMPORT_DESC_SIZE * i
        if record + IMPORT_DESC_SIZE > len(image.d):
            return (out or None), "import descriptor table truncated"
        fields = struct.unpack_from("<5I", image.d, record)
        if not any(fields):
            break                      # terminator
        original_first, stamp, chain, name_rva, first_thunk = fields
        dll = None
        if name_rva:
            dll = cstr_at(image.d, image.rva2file(module, name_rva))
        out.append(dict(index=i, dll=dll, name_rva=name_rva,
                        original_first=original_first, timestamp=stamp,
                        forwarder_chain=chain, first_thunk=first_thunk))
    return (out or None), None


def read_import_name(image, module, rva):
    """Name of a hint/name ILT entry (``u16`` hint then a C string)."""
    return cstr_at(image.d, image.rva2file(module, rva + 2))


def resolve_descriptors(image, index, va_map, module, descriptors):
    """Build and resolve the slots of every import descriptor."""
    name = module["name"]
    try:
        vbase = image.e32(module)["vbase"]
    except (struct.error, ValueError, IndexError):
        vbase = None
    slots, notes = [], []

    for desc in descriptors:
        dll = desc["dll"]
        ilt_rva = desc["original_first"]   # 0 => bound, no ILT
        iat_rva = desc["first_thunk"]
        desc["slots"] = 0
        if not dll:
            notes.append("descriptor %d: import name rva 0x%x unreadable"
                         % (desc["index"], desc["name_rva"]))
        if not iat_rva:
            notes.append("descriptor %d: FirstThunk is 0" % desc["index"])
            continue
        for n in range(MAX_IAT_SLOTS):
            ilt_raw = read_rva_u32(image, module, ilt_rva, 4 * n) if ilt_rva else None
            raw = read_rva_u32(image, module, iat_rva, 4 * n)
            if not ilt_raw and not raw:
                break
            iat_va = va_map.va_of_rva(name, iat_rva + 4 * n, vbase)
            slot = make_slot(n, iat_va, ilt_raw, raw)
            slot["descriptor"] = desc["index"]
            declared_name = None
            declared_ordinal = None
            if ilt_raw:
                if ilt_raw & IMAGE_ORDINAL_FLAG:
                    declared_ordinal = ilt_raw & ORDINAL_MASK
                else:
                    declared_name = read_import_name(image, module, ilt_raw)
                    if declared_name is None:
                        notes.append("descriptor %d slot %d: hint/name rva 0x%x "
                                     "unreadable" % (desc["index"], n, ilt_raw))
            resolve_slot(index, va_map, dll, declared_name, declared_ordinal,
                         raw, slot)
            if slot["status"] != STATUS_RESOLVED:
                notes.append("descriptor %d slot %d unresolved: %s"
                             % (desc["index"], n, slot["reason"] or "unknown"))
            slots.append(slot)
            desc["slots"] += 1
    return slots, notes


# --------------------------------------------------------------------------
# Pre-bound IAT: run scan
# --------------------------------------------------------------------------


def thunk_like(value, index, va_map):
    """Whether a word could be a bound import slot (not a declaration)."""
    if not value:
        return False
    if value in index.by_va:
        return True
    for start, end in PLAUSIBLE_VA:
        if start <= value < end:
            return True
    if value < va_map.min_va or value >= va_map.max_va:
        return False
    return va_map.module_at(value) is not None


def scan_module(image, module, index, va_map, min_run=2):
    """Find runs of thunk-like words in the module's uncompressed sections.

    A run must hold at least one word that resolves to an export: that is the
    only property that separates an IAT from ordinary data.  Without it, one
    random ``0x8…`` word in 256 would start a run and the report would be pure
    noise.
    """
    name = module["name"]
    try:
        sections = list(image.o32(module))
    except (struct.error, ValueError, IndexError) as exc:
        return [], ["%s: o32_rom unreadable (%s)" % (name, exc)]
    runs, notes = [], []
    for sect_index, section in enumerate(sections):
        if section["flags"] & cerom.IMAGE_SCN_COMPRESSED:
            continue
        if not section["psize"]:
            continue
        offset = image.va2file(section["dataptr"])
        if not (0 <= offset and offset + section["psize"] <= len(image.d)):
            notes.append("%s sec%d: stored bytes outside the image"
                         % (name, sect_index))
            continue
        count = (section["psize"] & ~3) // 4
        run = []
        hit = False
        for i, value in enumerate(iter_u32(image.d, offset, count)):
            if thunk_like(value, index, va_map):
                run.append((i, value))
                if value in index.by_va:
                    hit = True
                continue
            if len(run) >= min_run and hit:
                runs.append((sect_index, section, run))
            run, hit = [], False
        if len(run) >= min_run and hit:
            runs.append((sect_index, section, run))
    return runs, notes


def resolve_scan(index, va_map, runs):
    """Classify every word of every already-located run."""
    slots = []
    for sect_index, section, run in runs:
        for word_index, value in run:
            va = section["realaddr"] + 4 * word_index
            slot = make_slot(len(slots), va, None, value)
            slot["section"] = sect_index
            slot["rva"] = hx(section["rva"] + 4 * word_index)
            state = classify_va(index, va_map, value)
            if state["status"] == STATUS_RESOLVED:
                _resolved(slot, state["candidates"][0], "va", "match")
            elif state["status"] == STATUS_AMBIGUOUS:
                slot["status"] = STATUS_AMBIGUOUS
                slot["reason"] = "ambiguous"
                slot["candidates"] = [e.label() for e in state["candidates"]]
            else:
                slot["reason"] = state["reason"]
                slot["module"] = state["module"]
            slots.append(slot)
    return slots


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------


def summarise(slots):
    by_reason, by_via = {}, {}
    resolved = ambiguous = unresolved = 0
    for slot in slots:
        status = slot["status"]
        if status == STATUS_RESOLVED:
            resolved += 1
        elif status == STATUS_AMBIGUOUS:
            ambiguous += 1
        else:
            unresolved += 1
        if status != STATUS_RESOLVED and slot.get("reason"):
            by_reason[slot["reason"]] = by_reason.get(slot["reason"], 0) + 1
        if slot.get("via"):
            by_via[slot["via"]] = by_via.get(slot["via"], 0) + 1
    return dict(slots=len(slots), resolved=resolved, ambiguous=ambiguous,
                unresolved=unresolved, by_reason=by_reason, by_via=by_via)


def image_header(image_path, data, image):
    size = os.path.getsize(image_path) if image_path else len(data)
    return dict(
        image=os.path.basename(image_path) if image_path else None,
        image_size=size,
        image_sha256=hashlib.sha256(data).hexdigest(),
        image_sha256_scope=cerom.sha256_scope_text(len(data), size),
        segment_base=hx(image.start), phys_base=hx(image.hdr["physfirst"]),
        pTOC=hx(image.ptoc))


def resolve_module(image, index, va_map, module_name, force_scan=False, min_run=2):
    """Resolve one module's IAT; returns the ``thunks/v1`` document body."""
    module = image.module(module_name)
    descriptors, note = import_descriptors(image, module)
    notes = [note] if note else []
    source = "none"
    slots, runs = [], []

    if descriptors and not force_scan:
        source = "descriptor"
        slots, extra = resolve_descriptors(image, index, va_map, module, descriptors)
        notes.extend(extra)
    else:
        if descriptors:
            notes.append("import descriptor present but --force-scan given")
        runs_found, extra = scan_module(image, module, index, va_map, min_run)
        notes.extend(extra)
        slots = resolve_scan(index, va_map, runs_found)
        for _sect_index, section, run in runs_found:
            runs.append(dict(section=_sect_index,
                             rva=hx(section["rva"] + 4 * run[0][0]),
                             va=hx(section["realaddr"] + 4 * run[0][0]),
                             slots=len(run)))
        if runs:
            source = "iat-scan"

    # One slot number per module, across descriptors and scan runs.
    for number, slot in enumerate(slots):
        slot["slot"] = number

    header = dict(
        module=module["name"],
        vbase=hx(image.e32(module)["vbase"]),
        import_directory=dict(
            rva=hx(image.e32(module)["imp"][0]),
            size=hx(image.e32(module)["imp"][1])),
        source=source,
        descriptors=[dict(index=d["index"], dll=d["dll"],
                          name_rva=hx(d["name_rva"]),
                          original_first=hx(d["original_first"]),
                          first_thunk=hx(d["first_thunk"]),
                          timestamp=hx(d["timestamp"]))
                     for d in (descriptors or [])],
        runs=runs,
        universe=[m["name"] for m in index.modules],
        slots=slots,
        summary=summarise(slots),
        notes=notes)
    return header


def build_index_document(image, index, image_path, data, module_names):
    doc = image_header(image_path, data, image)
    doc.update(
        schema=INDEX_SCHEMA,
        generator=GENERATOR + " exports",
        module_set=module_names or "all",
        counts=dict(index.counts),
        modules=[dict(name=m["name"],
                      vbase=hx(m["vbase"]) if m["vbase"] is not None else None,
                      entries=m["entries"], named=m["named"], unnamed=m["unnamed"])
                 for m in index.modules],
        entries=[e.to_dict() for e in index.entries],
        notes=index.notes)
    return doc


def build_stats_document(image, index, va_map, image_path, data, module_names,
                         min_run=2):
    doc = image_header(image_path, data, image)
    modules, totals = [], dict(
        modules=0, with_descriptor=0, descriptors=0, scan_runs=0,
        slots=0, resolved=0, ambiguous=0, unresolved=0)
    by_reason = {}
    for module in image.modules():
        if not module["name"]:
            continue
        name = module["name"]
        body = resolve_module(image, index, va_map, name, min_run=min_run)
        summary = body["summary"]
        totals["modules"] += 1
        totals["slots"] += summary["slots"]
        totals["resolved"] += summary["resolved"]
        totals["ambiguous"] += summary["ambiguous"]
        totals["unresolved"] += summary["unresolved"]
        totals["scan_runs"] += len(body["runs"])
        if body["source"] == "descriptor":
            totals["with_descriptor"] += 1
            totals["descriptors"] += len(body["descriptors"])
        for reason, count in summary["by_reason"].items():
            by_reason[reason] = by_reason.get(reason, 0) + count
        modules.append(dict(module=name, vbase=body["vbase"],
                            source=body["source"],
                            descriptors=len(body["descriptors"]),
                            runs=len(body["runs"]),
                            slots=summary["slots"],
                            resolved=summary["resolved"],
                            ambiguous=summary["ambiguous"],
                            unresolved=summary["unresolved"]))
    totals["by_reason"] = by_reason
    doc.update(
        schema=STATS_SCHEMA,
        generator=GENERATOR + " stats",
        module_set=module_names or "all",
        index_counts=dict(index.counts),
        totals=totals,
        modules=modules,
        notes=index.notes)
    return doc


# --------------------------------------------------------------------------
# Text output
# --------------------------------------------------------------------------


def print_index(doc, show_entries):
    for module in doc["modules"]:
        print("%-24s vbase=%s exports=%3d (named=%d, unnamed=%d)"
              % (module["name"], module["vbase"], module["entries"],
                 module["named"], module["unnamed"]))
        if show_entries:
            for entry in doc["entries"]:
                if entry["module"] != module["name"]:
                    continue
                print("    %-42s ord=%-5d rva=%s %s"
                      % (entry["label"], entry["ordinal"], entry["rva"],
                         entry["va"]))
    counts = doc["counts"]
    print("total: %d module(s), %d export(s), %d named, %d unnamed, "
          "%d aliased VA(s)"
          % (counts["modules"], counts["entries"], counts["named"],
             counts["unnamed"], counts["aliased"]))
    for note in doc["notes"]:
        print("note: %s" % note)


def print_resolve(doc):
    print("module %s  vbase=%s  import source: %s"
          % (doc["module"], doc["vbase"], doc["source"]))
    for desc in doc["descriptors"]:
        print("  descriptor %d  dll=%s  ILT=%s  IAT=%s"
              % (desc["index"], desc["dll"], desc["original_first"],
                 desc["first_thunk"]))
    for run in doc["runs"]:
        print("  run section %d  va=%s  rva=%s  %d slot(s)"
              % (run["section"], run["va"], run["rva"], run["slots"]))
    for slot in doc["slots"]:
        line = "  slot %-3d iat=%s raw=%s" % (slot["slot"], slot["iat_va"],
                                              slot["raw"])
        if slot["declared"] and slot["declared"] != slot["target"]:
            line += " declared=%s" % slot["declared"]
        if slot["status"] == STATUS_RESOLVED:
            line += " -> %s [%s" % (slot["target"],
                                    "resolved via %s" % slot["via"])
            if slot["va_check"]:
                line += ", va %s" % slot["va_check"]
            line += "]"
        elif slot["status"] == STATUS_AMBIGUOUS:
            line += " -- ambiguous: %s" % ", ".join(slot["candidates"])
        else:
            line += " -- unresolved: %s" % (slot["reason"] or "unknown")
        if slot["rva"]:
            line += " rva=%s" % slot["rva"]
        print(line)
    summary = doc["summary"]
    line = ("summary: %d slot(s): %d resolved, %d ambiguous, %d unresolved"
            % (summary["slots"], summary["resolved"], summary["ambiguous"],
               summary["unresolved"]))
    if summary["by_reason"]:
        line += " (" + ", ".join("%s=%d" % item
                                 for item in sorted(summary["by_reason"].items())) + ")"
    print(line)
    for note in doc["notes"]:
        print("note: %s" % note)


def print_stats(doc):
    counts = doc["index_counts"]
    print("%d module(s), %d export(s): %d named, %d unnamed, %d aliased VA(s)"
          % (counts["modules"], counts["entries"], counts["named"],
             counts["unnamed"], counts["aliased"]))
    totals = doc["totals"]
    print("%d module(s) scanned: %d with an import descriptor (%d descriptor(s)), "
          "%d pre-bound run(s)"
          % (totals["modules"], totals["with_descriptor"], totals["descriptors"],
             totals["scan_runs"]))
    print("%d slot(s): %d resolved, %d ambiguous, %d unresolved"
          % (totals["slots"], totals["resolved"], totals["ambiguous"],
             totals["unresolved"]))
    if totals["by_reason"]:
        print("unresolved by reason: " + ", ".join(
            "%s=%d" % item for item in sorted(totals["by_reason"].items())))
    for module in doc["modules"]:
        if not module["slots"]:
            continue
        print("  %-24s source=%-10s slots=%-5d resolved=%-5d ambiguous=%-3d "
              "unresolved=%d" % (module["module"], module["source"],
                                 module["slots"], module["resolved"],
                                 module["ambiguous"], module["unresolved"]))
    for note in doc["notes"]:
        print("note: %s" % note)


# --------------------------------------------------------------------------
# Synthetic fixture (no vendor bytes).  The same builder backs --selftest.
# --------------------------------------------------------------------------

FIXTURE_EXPORTER = "NK.EXE"
FIXTURE_IMPORTER = "NAVI.EXE"
FIXTURE_EXPORT_NAME_RVAS = (0x1170, 0x1188, 0x11A0)
FIXTURE_EXPORT_DIR = 0x5100          # file offset, rva 0x1100
FIXTURE_IMPORTER_SEC0 = 0x6400       # file offset, rva 0x1000
FIXTURE_SCAN_SLOTS = (0x8CE01100, 0x8CE01200, 0x8CE01300, 0x8F000000,
                      0x8CE01010, 0)
FIXTURE_GOOD = ("NK.EXE!MAL_DataVol_getOffset", "NK.EXE!MAL_DataVol_getSize")


def build_thunk_fixture(with_descriptor=True):
    """``(bytes, layout)`` for a two-module CE ROM with IAT evidence.

    Starts from ``cerom.build_synthetic_rom()`` and rewrites two regions:

    * ``NK.EXE``'s export directory (rva 0x1100) gets four functions --
      ``MAL_DataVol_getOffset`` (ordinal 1), ``MAL_DataVol_getSize``
      (ordinal 2), an **ordinal-only** function (ordinal 3) and an
      ``MAL_DataVol_getOffsetAlias`` (ordinal 4) that shares ordinal 1's RVA;
    * ``NAVI.EXE``'s first section gets a pre-bound slot run (rva 0x1100) and,
      unless ``with_descriptor`` is false, an import descriptor (rva 0x1000)
      whose ILT imports two names plus ordinals 1 and 3.

    Neither region carries vendor bytes; every value is computed here.
    ``with_descriptor=False`` produces the *pre-bound* shape a real CE XIP
    image usually has: no descriptor at all, only the slot run.
    """
    rom, layout = cerom.build_synthetic_rom()
    data = bytearray(rom)

    # --- NK.EXE: rebuilt export directory at rva 0x1100 ------------------
    struct.pack_into("<IIHHIIIIIII", data, FIXTURE_EXPORT_DIR,
                     0, 0x5F000000, 0, 0, 0x0000, 1, 4, 3,
                     0x1130, 0x1140, 0x1150)     # base, nfun, nnam, aof/aon/aoo
    struct.pack_into("<4I", data, 0x5130,
                     0x1100, 0x1200, 0x1300, 0x1100)   # AddressOfFunctions
    struct.pack_into("<3I", data, 0x5140, *FIXTURE_EXPORT_NAME_RVAS)
    struct.pack_into("<3H", data, 0x5150, 0, 1, 3)     # AddressOfOrdinals
    names = (b"MAL_DataVol_getOffset", b"MAL_DataVol_getSize",
             b"MAL_DataVol_getOffsetAlias")
    for rva, name in zip(FIXTURE_EXPORT_NAME_RVAS, names):
        off = 0x5000 + (rva - 0x1000)
        data[off:off + len(name) + 1] = name + b"\0"
    # e32_unit[0] = export directory (rva, size) -> our new block.
    struct.pack_into("<2I", data, 0x4000 + 36, 0x1100, 0x180)

    # --- NAVI.EXE: pre-bound slot run at rva 0x1100 ----------------------
    struct.pack_into("<6I", data, 0x6500, *FIXTURE_SCAN_SLOTS)

    if not with_descriptor:
        layout["export_labels"] = [
            "NK.EXE!MAL_DataVol_getOffset", "NK.EXE!MAL_DataVol_getSize",
            "NK.EXE!#3", "NK.EXE!MAL_DataVol_getOffsetAlias"]
        layout["scan_slots"] = len(FIXTURE_SCAN_SLOTS) - 1
        layout["descriptor_slots"] = 0
        return bytes(data), layout

    # --- NAVI.EXE: import descriptor at rva 0x1000 -----------------------
    struct.pack_into("<5I", data, FIXTURE_IMPORTER_SEC0,
                     0x1040, 0, 0, 0x1030, 0x1060)   # OFT, ts, chain, name, FT
    data[0x6430:0x6437] = b"NK.EXE\0"
    struct.pack_into("<5I", data, 0x6440,
                     0x1080, 0x10A0, 0x80000001, 0x80000003, 0)
    struct.pack_into("<5I", data, 0x6460,
                     0x8CE01100, 0x8CE01200, 0x8CE01100, 0x8CE01300, 0)
    for off, name in ((0x6480, b"MAL_DataVol_getOffset"),
                      (0x64A0, b"MAL_DataVol_getSize")):
        struct.pack_into("<H", data, off, 0)
        data[off + 2:off + 2 + len(name) + 1] = name + b"\0"
    # e32_unit[1] = import directory (rva, size): one 20-byte record + terminator.
    struct.pack_into("<2I", data, 0x6000 + 36 + 8, 0x1000, 2 * IMPORT_DESC_SIZE)

    layout["export_labels"] = [
        "NK.EXE!MAL_DataVol_getOffset", "NK.EXE!MAL_DataVol_getSize",
        "NK.EXE!#3", "NK.EXE!MAL_DataVol_getOffsetAlias"]
    layout["scan_slots"] = len(FIXTURE_SCAN_SLOTS) - 1
    layout["descriptor_slots"] = 4
    return bytes(data), layout


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------


def selftest():
    """Assert the resolver on the synthetic fixture; return 0 (raise on mismatch)."""
    import tempfile

    rom, layout = build_thunk_fixture()
    checks = []

    def ok(label, got, want):
        if got != want:
            raise AssertionError("%s: got %r, want %r" % (label, got, want))
        checks.append(label)

    with tempfile.TemporaryDirectory(prefix="cerom-thunks-") as td:
        path = os.path.join(td, "thunk-fixture.img")
        with open(path, "wb") as handle:
            handle.write(rom)
        with open(path, "rb") as handle:
            data = handle.read()

        image = cerom.CERom(data)
        va_map = VaMap(image)
        index = build_index(image, va_map=va_map)

        # --- export index: named, unnamed, aliased ----------------------
        ok("index module count", [m["name"] for m in index.modules],
           [FIXTURE_EXPORTER, FIXTURE_IMPORTER])
        ok("index exporter entry count", index.modules[0]["entries"], 4)
        ok("index exporter named/unnamed",
           (index.modules[0]["named"], index.modules[0]["unnamed"]), (3, 1))
        ok("index importer has no exports",
           (index.modules[1]["entries"], index.modules[1]["named"]), (0, 0))
        ok("index counts", (index.counts["entries"], index.counts["named"],
                            index.counts["unnamed"]), (4, 3, 1))

        get_offset = index.lookup_name(FIXTURE_EXPORTER, "MAL_DataVol_getOffset")
        get_size = index.lookup_name(FIXTURE_EXPORTER.lower(), "mal_datavol_getsize")
        alias = index.lookup_name(FIXTURE_EXPORTER, "MAL_DataVol_getOffsetAlias")
        unnamed = index.lookup_ordinal(FIXTURE_EXPORTER, 3)
        ok("named export 1", (get_offset.ordinal, get_offset.rva, get_offset.va),
           (1, 0x1100, 0x8CE01100))
        ok("named export 1 label", get_offset.label(),
           "NK.EXE!MAL_DataVol_getOffset")
        ok("named export 2 (case-insensitive)",
           (get_size.ordinal, get_size.rva, get_size.va, get_size.label()),
           (2, 0x1200, 0x8CE01200, "NK.EXE!MAL_DataVol_getSize"))
        ok("ordinal fallback: address-only export", (unnamed.ordinal, unnamed.rva,
                                                     unnamed.names,
                                                     unnamed.label()),
           (3, 0x1300, [], "NK.EXE!#3"))
        ok("alias export", (alias.ordinal, alias.rva, alias.va),
           (4, 0x1100, 0x8CE01100))
        ok("aliased VA has two candidates",
           sorted(e.label() for e in index.lookup_va(0x8CE01100)),
           ["NK.EXE!MAL_DataVol_getOffset", "NK.EXE!MAL_DataVol_getOffsetAlias"])
        ok("unique VA has one candidate",
           [e.label() for e in index.lookup_va(0x8CE01200)],
           ["NK.EXE!MAL_DataVol_getSize"])
        ok("named export rva agrees with exports()",
           [n for n in index.notes if "!= AddressOfFunctions" in n], [])
        ok("module set filter",
           [m["name"] for m in build_index(
               image, [FIXTURE_EXPORTER], va_map=va_map).modules],
           [FIXTURE_EXPORTER])
        try:
            build_index(image, ["Nope.dll"], va_map=va_map)
        except KeyError as exc:
            ok("unknown module in module set rejected", exc.args[0], "Nope.dll")
        else:
            raise AssertionError("build_index() accepted an unknown module name")

        # --- classification of a bare VA -------------------------------
        ok("classify export VA", classify_va(index, va_map, 0x8CE01200)["status"],
           STATUS_RESOLVED)
        ok("classify aliased VA", classify_va(index, va_map, 0x8CE01100)["status"],
           STATUS_AMBIGUOUS)
        ok("classify null", classify_va(index, va_map, 0)["reason"], "null-slot")
        ok("classify outside image",
           classify_va(index, va_map, 0x8F000000)["reason"], "outside-image")
        ok("classify inside section, not an export",
           classify_va(index, va_map, 0x8CE01010)["reason"], "no-export")
        ok("classify forwarder window",
           classify_va(index, va_map, 0x8CE01150)["reason"], "forwarder")

        # --- pre-bound path (descriptor disabled) ----------------------
        prebound, _pre_layout = build_thunk_fixture(with_descriptor=False)
        pre_path = os.path.join(td, "prebound.img")
        with open(pre_path, "wb") as handle:
            handle.write(prebound)
        pre_image = cerom.CERom(prebound)
        pre_map = VaMap(pre_image)
        pre_index = build_index(pre_image, va_map=pre_map)
        body = resolve_module(pre_image, pre_index, pre_map, FIXTURE_IMPORTER)
        ok("pre-bound: no descriptor", body["descriptors"], [])
        ok("pre-bound: source is the scan", body["source"], "iat-scan")
        ok("pre-bound: one run", len(body["runs"]), 1)
        ok("pre-bound: run slot count", body["runs"][0]["slots"],
           layout["scan_slots"])
        ok("pre-bound: slot count", body["summary"]["slots"], 5)

        by_raw = {slot["raw"]: slot for slot in body["slots"]}
        ok("pre-bound: exact resolution",
           (by_raw["0x8ce01200"]["target"], by_raw["0x8ce01200"]["via"]),
           ("NK.EXE!MAL_DataVol_getSize", "va"))
        ok("pre-bound: ordinal-only target", by_raw["0x8ce01300"]["target"],
           "NK.EXE!#3")
        ok("pre-bound: ordinal-only via the bound VA",
           by_raw["0x8ce01300"]["via"], "va")
        ok("pre-bound: alias is ambiguous", by_raw["0x8ce01100"]["status"],
           STATUS_AMBIGUOUS)
        ok("pre-bound: ambiguity candidates",
           sorted(by_raw["0x8ce01100"]["candidates"]),
           ["NK.EXE!MAL_DataVol_getOffset", "NK.EXE!MAL_DataVol_getOffsetAlias"])
        ok("pre-bound: outside-image slot",
           (by_raw["0x8f000000"]["status"], by_raw["0x8f000000"]["reason"]),
           (STATUS_UNRESOLVED, "outside-image"))
        ok("pre-bound: no-export slot",
           (by_raw["0x8ce01010"]["status"], by_raw["0x8ce01010"]["reason"]),
           (STATUS_UNRESOLVED, "no-export"))
        ok("pre-bound: summary",
           {k: body["summary"][k] for k in ("slots", "resolved", "ambiguous",
                                            "unresolved")},
           dict(slots=5, resolved=2, ambiguous=1, unresolved=2))
        ok("pre-bound: by_reason",
           body["summary"]["by_reason"],
           {"ambiguous": 1, "no-export": 1, "outside-image": 1})

        # --- descriptor path ------------------------------------------
        body = resolve_module(image, index, va_map, FIXTURE_IMPORTER)
        ok("descriptor: source", body["source"], "descriptor")
        ok("descriptor: count", len(body["descriptors"]), 1)
        ok("descriptor: dll name", body["descriptors"][0]["dll"],
           FIXTURE_EXPORTER)
        ok("descriptor: slot count", body["summary"]["slots"],
           layout["descriptor_slots"])
        slots = body["slots"]
        ok("descriptor: slot 0 via name",
           (slots[0]["target"], slots[0]["via"], slots[0]["va_check"]),
           ("NK.EXE!MAL_DataVol_getOffset", "name", "match"))
        ok("descriptor: slot 1 exact resolution",
           (slots[1]["target"], slots[1]["declared"], slots[1]["via"]),
           ("NK.EXE!MAL_DataVol_getSize", "NK.EXE!MAL_DataVol_getSize", "name"))
        ok("descriptor: slot 2 imported by ordinal",
           (slots[2]["declared"], slots[2]["target"], slots[2]["via"]),
           ("NK.EXE!#1", "NK.EXE!MAL_DataVol_getOffset", "ordinal"))
        ok("descriptor: slot 3 ordinal-only import",
           (slots[3]["declared"], slots[3]["target"], slots[3]["via"]),
           ("NK.EXE!#3", "NK.EXE!#3", "ordinal"))
        ok("descriptor: all resolved",
           (body["summary"]["resolved"], body["summary"]["unresolved"],
            body["summary"]["ambiguous"]), (4, 0, 0))

        # --- descriptor path with an empty module set -----------------
        narrow = build_index(image, [FIXTURE_IMPORTER], va_map=va_map)
        body = resolve_module(image, narrow, va_map, FIXTURE_IMPORTER)
        ok("descriptor: foreign dll reported",
           sorted({s["reason"] for s in body["slots"]}),
           ["dll-not-in-index"])
        ok("descriptor: foreign dll keeps declared target",
           body["slots"][0]["declared"], "NK.EXE!MAL_DataVol_getOffset")

        # --- --force-scan on an image that also has a descriptor ------
        body = resolve_module(image, index, va_map, FIXTURE_IMPORTER,
                              force_scan=True)
        ok("force-scan: source", body["source"], "iat-scan")
        # The scan cannot tell an ILT from an IAT: it finds the descriptor's
        # ordinal words too.  That is the documented limit of the heuristic.
        ok("force-scan: runs (ILT + IAT + scan array)", len(body["runs"]), 3)
        ok("force-scan: slot count", body["summary"]["slots"], 11)

        # --- CLI ------------------------------------------------------
        out = os.path.join(td, "resolve.json")
        buf = sys.stdout
        try:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
            ok("cli resolve exit 0", main([path, "resolve", FIXTURE_IMPORTER]), 0)
            ok("cli resolve --json exit 0",
               main([path, "resolve", FIXTURE_IMPORTER, "--json"]), 0)
            ok("cli resolve --force-scan exit 1",
               main([path, "resolve", FIXTURE_IMPORTER, "--force-scan"]),
               EXIT_PARTIAL)
            ok("cli exports exit 0", main([path, "exports"]), 0)
            ok("cli exports --list --json exit 0",
               main([path, "exports", "--list", "--json"]), 0)
            ok("cli stats exit 0", main([path, "stats"]), 0)
            ok("cli exports --module-set exit 0",
               main([path, "exports", "--module-set", FIXTURE_EXPORTER]), 0)
        finally:
            sys.stdout.close()
            sys.stdout = buf

        # JSON document shape, via the API and the file it writes.
        doc = resolve_module(image, index, va_map, FIXTURE_IMPORTER)
        doc.update(schema=THUNKS_SCHEMA, generator=GENERATOR + " resolve")
        with open(out, "w", encoding="utf-8") as handle:
            json.dump(doc, handle)
        with open(out, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        ok("json schema", loaded["schema"], THUNKS_SCHEMA)
        ok("json slot count", len(loaded["slots"]), 4)
        ok("json summary keys", sorted(loaded["summary"]),
           ["ambiguous", "by_reason", "by_via", "resolved", "slots", "unresolved"])

        index_doc = build_index_document(image, index, path, data, None)
        ok("exports document schema", index_doc["schema"], INDEX_SCHEMA)
        ok("exports document entry labels", [e["label"] for e in index_doc["entries"]],
           layout["export_labels"])
        stats_doc = build_stats_document(image, index, va_map, path, data, None)
        ok("stats document schema", stats_doc["schema"], STATS_SCHEMA)
        ok("stats document totals",
           (stats_doc["totals"]["modules"], stats_doc["totals"]["with_descriptor"],
            stats_doc["totals"]["slots"]), (2, 1, 4))

        # Error path: an unknown module must exit 2, not resolve something.
        try:
            resolve_module(image, index, va_map, "Nope.dll")
        except KeyError:
            ok("unknown module raises KeyError", True, True)
        else:
            raise AssertionError("resolve_module() accepted an unknown module")

        # Negative control: corrupt the export table and require a note, not a
        # crash and not a silent empty index.
        broken = bytearray(rom)
        struct.pack_into("<I", broken, 0x4024, 0x7FFF0000)   # export rva
        broken_index = build_index(cerom.CERom(bytes(broken)))
        ok("corrupt export rva is noted, not fatal",
           any(FIXTURE_EXPORTER in n for n in broken_index.notes), True)
        ok("corrupt export rva yields no exporter entries",
           [m["entries"] for m in broken_index.modules
            if m["name"] == FIXTURE_EXPORTER], [0])

    print("cerom_thunks selftest: %d checks OK (synthetic ROM, no vendor data)"
          % len(checks))
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _module_set(value):
    if not value:
        return None
    names = [part.strip() for part in value.split(",") if part.strip()]
    return names or None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", nargs="?",
                        help="raw image (or at least its first ~32 MiB)")
    parser.add_argument("--image-start", type=lambda s: int(s, 0), default=None,
                        help="image start of the CE segment (default: discover)")
    parser.add_argument("--selftest", action="store_true",
                        help="run the synthetic self-test and exit (needs no image)")
    parser.add_argument("--write-fixture", metavar="PATH",
                        help="write the synthetic thunk ROM to PATH and exit")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("resolve", help="map one module's IAT to module!export")
    p.add_argument("module")
    p.add_argument("--module-set", help="comma-separated module names for the index")
    p.add_argument("--json", action="store_true", help="emit the JSON document")
    p.add_argument("--force-scan", action="store_true",
                   help="ignore any import descriptor and scan for bound slots")
    p.add_argument("--min-run", type=int, default=2,
                   help="minimum consecutive bound slots (default 2)")

    p = sub.add_parser("exports", help="summarise the export index")
    p.add_argument("--module-set", help="comma-separated module names")
    p.add_argument("--json", action="store_true", help="emit the JSON index")
    p.add_argument("--list", action="store_true", help="list every export")

    p = sub.add_parser("stats", help="segment-wide thunk statistics")
    p.add_argument("--module-set", help="comma-separated module names")
    p.add_argument("--json", action="store_true", help="emit the JSON document")

    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.write_fixture:
        rom, _layout = build_thunk_fixture()
        with open(args.write_fixture, "wb") as handle:
            handle.write(rom)
        print("wrote %s (%d bytes, synthetic)" % (args.write_fixture, len(rom)))
        return EXIT_OK
    if args.image is None:
        parser.error("the following arguments are required: image")
    if args.cmd is None:
        parser.error("a subcommand is required (resolve, exports, stats)")
    if getattr(args, "min_run", 2) < 1:
        parser.error("--min-run must be >= 1")

    try:
        with open(args.image, "rb") as handle:
            data = handle.read(128 << 20)
        image = cerom.CERom(data, args.image_start)
    except (OSError, ValueError, struct.error) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return EXIT_ERROR

    module_names = _module_set(args.module_set)
    try:
        va_map = VaMap(image)
        index = build_index(image, module_names, va_map)
    except KeyError as exc:
        print("error: no module named %s in this ROM" % exc.args[0], file=sys.stderr)
        return EXIT_ERROR
    except (ValueError, struct.error) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return EXIT_ERROR

    if args.cmd == "exports":
        doc = build_index_document(image, index, args.image, data, module_names)
        if args.json:
            print(json.dumps(doc, indent=2))
        else:
            print_index(doc, args.list)
        return EXIT_PARTIAL if index.notes else EXIT_OK

    if args.cmd == "stats":
        doc = build_stats_document(image, index, va_map, args.image, data,
                                   module_names, getattr(args, "min_run", 2))
        if args.json:
            print(json.dumps(doc, indent=2))
        else:
            print_stats(doc)
        return EXIT_PARTIAL if index.notes else EXIT_OK

    # resolve
    try:
        body = resolve_module(image, index, va_map, args.module, args.force_scan,
                              args.min_run)
    except KeyError:
        print("error: no module named %s in this ROM" % args.module,
              file=sys.stderr)
        return EXIT_ERROR
    body.update(schema=THUNKS_SCHEMA, generator=GENERATOR + " resolve")
    body.update(image_header(args.image, data, image))
    if args.json:
        print(json.dumps(body, indent=2))
    else:
        print_resolve(body)
    summary = body["summary"]
    if summary["resolved"] and not summary["unresolved"] and not summary["ambiguous"]:
        return EXIT_OK
    if not summary["slots"]:
        print("note: no import descriptor and no %d-slot run in this module"
              % args.min_run, file=sys.stderr)
    return EXIT_PARTIAL


if __name__ == "__main__":
    sys.exit(main())
