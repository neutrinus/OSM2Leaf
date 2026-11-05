#!/usr/bin/env python3
"""Score which CE ROM segment (B or C) is the kernel that boots alongside A.

The tool never executes firmware and never reads the boot ROM.  It takes the
``ROMHDR`` and the module/file table of every candidate segment and prints a
scored decision table with one evidence string per criterion.  When the
evidence does not separate the candidates it returns ``UNKNOWN`` - that is the
expected answer on the real image today (C-529).

Usage
-----
  kernel_select.py --image IMG --image-start 0x3e00200 --label B \\
                   --image IMG --image-start 0x5200200 --label C
  kernel_select.py --segment B=IMG@0x3e00200 --segment C=IMG@0x5200200
  kernel_select.py --from-json report-b.json --from-json report-c.json
  kernel_select.py --selftest

``--segment`` accepts ``LABEL=PATH[@OFFSET]``; without ``@OFFSET`` the first
valid ``ECEC`` in the file is used, which for a full SD image is build A, so
pass the offset explicitly.  ``--from-json`` accepts this tool's own
``--json`` output (full round-trip, recomputed), a ``cerom.py memmap`` JSON, a
``ce_rom_parse.py`` report, or a plain ``{"romhdr": ..., "modules": [...]}``
document.  Inputs without module names, entry data or payload hashes simply
leave the corresponding criteria ``unknown``.

Criteria provenance: verified vs heuristic
------------------------------------------
Inputs that come from verified work (no fitting, no guessing):

* ``physfirst``/``physlast``, ``ulRAMStart``/``ulRAMFree``/``ulRAMEnd``,
  ``pExtensions`` and ``usCPUType`` are ROMHDR fields as parsed by
  ``tools/cerom.py`` (layout VERIFIED, ``docs/format/cerom.md``); the values
  for A/B/C are recorded in EXP-2026-11-05-36 (C-524/C-525).
* the module sets are facts from the same EXP: A has 149 application modules
  and no kernel, B and C both carry ``nk.exe``/``coredll.dll`` and the five
  kernel modules, and "B adds the updater set, C the test mode" (C-526).
* A's memory plan (image ``0x0cae1000``-``0x0e233c88``, RAM window
  ``0x09e40000``-``0x0cae1000``) is A's own ROMHDR (EXP-36 and
  ``docs/research/full-system-emulation.md`` section 1).
* a byte-identical duplicate is a fact, not a score: A and B are stored twice,
  C once (C-524); the copies are one build, not two opinions.

Heuristics - each one is documented here because none of them proves the boot
choice:

``ram_overlap``
    The kernel image must sit below A's RAM window and its ``ulRAMEnd`` must
    close exactly at A's ``physfirst``.  This ordering is observed for B *and*
    C, so passing it cannot separate them; failing it is evidence against a
    segment, passing it only shows consistency with the observed layout.
``ram_window``
    CE-5 textbook sanity only (``start <= free < end``, 4 KiB aligned, clear
    of the segment's own ROM span, below ``0x10000000``).  Sanity, not
    selection.
``p_extensions``
    A nonzero ``pExtensions`` must point inside the segment's own ROM span;
    the shared value ``0x880030a4`` is recorded for all three builds, so this
    is again a consistency check, not a discriminator.
``entry_point``
    ``nk.exe``'s ``e32_entryrva`` must lie inside ``e32_vsize`` and inside an
    executable ``o32`` section, the entry VA must be inside the ROM span and
    the first two stored bytes must not be ``0x0000``.  Public CE layout plus
    the observed entry ``0x8800ebd0`` (EXP-37); no execution.
``kernel_modules``
    Presence of ``nk.exe``, ``coredll.dll``, ``filesys.exe``, ``device.exe``
    and ``gwes.exe`` is identity evidence (a kernel image must have them);
    both B and C are expected to pass, so it mostly guards against a
    mislabelled or truncated input.
``updater_set``
    Presence of at least two updater artefacts (``UpdateMng.exe``,
    ``MapUpdate.exe``, ``PRGUpdate.exe``, ... or ``UpdateNK.skn``) is evidence
    about the *build role* - service/update build vs test build - and NOT
    about which one the IPL boots.  It is deliberately weak (weight 1) and can
    never decide alone.  TODO M1.7 also names ``UpdateMng.exe``'s update flow
    as a third source; reading that code is still open.

Decision rule
-------------
Each criterion is ``pass`` (+weight), ``fail`` (-weight) or ``unknown`` (0).
``ram_overlap``, ``kernel_modules``, ``entry_point`` and ``duplicate`` are
gates: a ``fail`` disqualifies the segment.  A verdict needs

1. at least one B and one C segment (a missing label is not a comparison),
2. at least one eligible segment, and
3. if both are eligible: at least two criteria whose status differs, at least
   one of them structural (``ram_overlap``, ``ram_window``,
   ``p_extensions``, ``entry_point``), no score tie, and at least four
   decisive criteria for the winner.

Otherwise the verdict is ``UNKNOWN``.  A single different criterion is not
enough on purpose: module-name presence alone cannot say which build boots.
Exit code is 0 whenever a report was produced, including ``UNKNOWN``.

Verdict values are only ``B``, ``C`` or ``UNKNOWN``.  The real image run that
would make this meaningful still has to show a *structural* difference between
B and C (``ulRAM*`` under a different A plan, the contents behind
``pExtensions``, or the IPL/update selection path).  Until then the honest
answer is ``UNKNOWN``.
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

import cerom

SCHEMA = "osm2leaf.kernel-select/v1"
GENERATOR = "tools/kernel_select.py"

PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"
VERDICT_UNKNOWN = "UNKNOWN"

# SH-4 P1: VA 0x8cae1000 is physical 0x0cae1000 for this image (EXP-35/36).
PHYS_OFFSET = 0x80000000

# A's plan, from A's own ROMHDR (EXP-2026-11-05-36; full-system-emulation.md).
A_IMAGE_PHYS = (0x0CAE1000, 0x0E233C88)
A_RAM_PHYS = (0x09E40000, 0x0CAE1000)

# Values recorded for A/B/C in EXP-36, quoted in evidence when they match.
RECORDED_RAM_START = 0x89E40000
RECORDED_PEXT = 0x880030A4

# Segment base -> build label (docs/format/cerom.md section 1, EXP-36).
LABEL_BY_BASE = {
    0x0200200: "A", 0x2000200: "A",
    0x03E00200: "B", 0x04800200: "B",
    0x05200200: "C",
}

KERNEL_MODULES = ("nk.exe", "coredll.dll", "filesys.exe", "device.exe", "gwes.exe")

UPDATER_MODULES = (
    "updatemng.exe", "prgupdate.exe", "mapupdate.exe", "btupdate.exe",
    "displayupdate.exe", "audiomiconupdate.exe", "vcansubmiconupdate.exe",
    "onesegupdate.exe", "fullsegupdate.exe",
)
UPDATER_SUFFIX = "updatecc.dll"
UPDATER_FILES = ("updatenk.skn",)

# (id, weight, provenance kind, description)
CRITERIA = (
    ("ram_overlap", 3, "heuristic",
     "ROM span below A's RAM window and ulRAMEnd closing at A's physfirst"),
    ("ram_window", 2, "heuristic",
     "CE ulRAMStart/ulRAMFree/ulRAMEnd sanity"),
    ("p_extensions", 1, "heuristic",
     "pExtensions is 0 or inside the segment's own ROM span"),
    ("kernel_modules", 3, "verified",
     "nk.exe, coredll.dll, filesys.exe, device.exe, gwes.exe present (C-526)"),
    ("updater_set", 1, "heuristic",
     "at least two updater modules or UpdateNK.skn (build role, not boot)"),
    ("entry_point", 3, "heuristic",
     "nk.exe entry rva inside an executable section, bytes not 0x0000"),
    ("duplicate", 0, "verified",
     "payload is byte-identical to an earlier segment (C-524)"),
)
WEIGHTS = {cid: weight for cid, weight, _kind, _desc in CRITERIA}
GATE_CRITERIA = ("ram_overlap", "kernel_modules", "entry_point", "duplicate")
STRUCTURAL = ("ram_overlap", "ram_window", "p_extensions", "entry_point")
MIN_DISCRIMINATORS = 2
MIN_DECISIVE = 4
MIN_UPDATERS = 2


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def hx(value):
    """32-bit hex or ``?``; every ROMHDR/pointer value here fits."""
    return "?" if value is None else "0x%08x" % value


def as_int(value):
    """Accept int, decimal string or ``0x`` string; None when unusable."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip(), 0)
        except ValueError:
            return None
    return None


def va_to_phys(va):
    """P1 VA -> physical address; already-physical values pass through."""
    if va is None:
        return None
    if 0x80000000 <= va < 0xA0000000:
        return va - PHYS_OFFSET
    return va


def overlaps(a0, a1, b0, b1):
    return a0 < b1 and b0 < a1


def short_list(values, limit=6):
    values = list(values)
    if len(values) <= limit:
        return ", ".join(values)
    return "%s, ... (%d total)" % (", ".join(values[:limit]), len(values))


def criterion(status, evidence):
    return {"status": status, "evidence": evidence, "score": 0}


def va_span_of(hdr):
    """ROM span as the VAs stored in ROMHDR (``physfirst``/``physlast``)."""
    if not hdr:
        return (None, None)
    first = as_int(hdr.get("physfirst"))
    last = as_int(hdr.get("physlast"))
    if not first or not last:
        return (None, None)
    return (first, last)


def span_of(hdr):
    """Physical ``(first, last)`` of a segment's ROM image."""
    first, last = va_span_of(hdr)
    return (va_to_phys(first), va_to_phys(last))


def default_a_plan():
    return {
        "image_phys": A_IMAGE_PHYS,
        "ram_phys": A_RAM_PHYS,
        "source": ("A's own ROMHDR: image VA 0x8cae1000-0x8e233c88, "
                   "ulRAMStart/ulRAMEnd 0x89e40000-0x8cae1000 "
                   "(EXP-2026-11-05-36; physical = VA - 0x80000000)"),
    }


def plan_from_segments(segments):
    """Use a supplied A segment for A's plan when it carries the fields."""
    for seg in segments:
        if (seg.get("label") or "").upper() != "A":
            continue
        hdr = seg.get("romhdr") or {}
        first, last = span_of(hdr)
        ram_start = as_int(hdr.get("ulRAMStart"))
        ram_end = as_int(hdr.get("ulRAMEnd"))
        if (first and last and last > first and ram_start and ram_end
                and ram_end > ram_start):
            return {
                "image_phys": (first, last),
                "ram_phys": (va_to_phys(ram_start), va_to_phys(ram_end)),
                "source": ("A segment at %s: ROMHDR physfirst/physlast and "
                           "ulRAMStart/ulRAMEnd" % hx(seg.get("segment_base"))),
            }
    return default_a_plan()


# --------------------------------------------------------------------------
# Reading live segments through tools/cerom.py
# --------------------------------------------------------------------------


def load_image(path, limit_mib, cache):
    key = (os.path.abspath(path), limit_mib)
    if key not in cache:
        with open(path, "rb") as handle:
            cache[key] = handle.read(int(limit_mib * (1 << 20)))
    return cache[key]


def extract_entry(rom, modules):
    """Plausibility input for nk.exe: e32/o32 fields plus the first bytes."""
    nk = None
    for module in modules:
        if (module.get("name") or "").lower() == "nk.exe":
            nk = module
            break
    if nk is None:
        return None
    try:
        e32 = rom.e32(nk)
        sections = [
            {"rva": sec["rva"], "vsize": sec["vsize"],
             "psize": sec["psize"], "flags": sec["flags"]}
            for sec in rom.o32(nk)
        ]
        entry = {
            "module": nk["name"],
            "entryrva": e32["entryrva"],
            "vbase": e32["vbase"],
            "vsize": e32["vsize"],
            "entry_va": e32["vbase"] + e32["entryrva"],
            "sections": sections,
            "first_bytes": None,
        }
        offset = rom.rva2file(nk, e32["entryrva"])
        if offset is not None and 0 <= offset <= len(rom.d) - 2:
            entry["first_bytes"] = rom.d[offset:offset + 2].hex()
        return entry
    except (struct.error, ValueError) as exc:
        return {"module": nk["name"], "error": str(exc)}


def segment_from_cerom(label, rom, source):
    """Normalise one ``cerom.CERom`` segment into the report's raw inputs."""
    hdr = {key: value for key, value in rom.hdr.items()}

    modules = []
    try:
        for module in rom.modules():
            modules.append(module)
    except struct.error:
        pass
    module_names = [m["name"] for m in modules if m.get("name")]

    file_names = []
    try:
        for entry in rom.files():
            if entry.get("name"):
                file_names.append(entry["name"])
    except struct.error:
        file_names = None

    span = span_of(hdr)
    payload_sha256 = None
    payload_bytes = 0
    payload_complete = False
    if span[0] is not None and span[1] is not None and span[1] > span[0]:
        wanted = span[1] - span[0]
        available = max(0, min(wanted, len(rom.d) - rom.start))
        payload_sha256 = hashlib.sha256(
            rom.d[rom.start:rom.start + available]).hexdigest()
        payload_bytes = available
        payload_complete = available == wanted

    return {
        "label": label,
        "segment_base": rom.start,
        "pTOC": rom.ptoc,
        "romhdr": hdr,
        "module_names": module_names,
        "file_names": file_names,
        "entry": extract_entry(rom, modules),
        "payload_sha256": payload_sha256,
        "payload_bytes": payload_bytes,
        "payload_complete": payload_complete,
        "source": source,
    }


# --------------------------------------------------------------------------
# Reading saved JSON (this tool, cerom memmap, ce_rom_parse or a plain dict)
# --------------------------------------------------------------------------


def json_names(value):
    """List of names from ``["a"]``, ``[{"name": "a"}]`` or None."""
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        return None
    names = []
    for item in value:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict):
            name = item.get("name") or item.get("module")
            if isinstance(name, str):
                names.append(name)
    return names


def json_segments(document, source):
    if isinstance(document, dict) and isinstance(document.get("segments"), list):
        items = document["segments"]
    elif isinstance(document, list):
        items = document
    elif isinstance(document, dict):
        items = [document]
    else:
        raise ValueError("%s: unsupported JSON shape" % source)

    segments = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError("%s: segment %d is not an object" % (source, index))
        label = item.get("label")
        base = as_int(item.get("segment_base"))
        if not isinstance(label, str) or not label:
            label = LABEL_BY_BASE.get(base)
        romhdr = item.get("romhdr")
        if isinstance(romhdr, dict):
            romhdr = {key: (value if key == "extensions" else as_int(value))
                      for key, value in romhdr.items()}
        else:
            romhdr = None
        if "module_names" in item:
            module_names = json_names(item.get("module_names"))
        else:
            module_names = json_names(item.get("modules"))
        if "file_names" in item:
            file_names = json_names(item.get("file_names"))
        else:
            file_names = json_names(item.get("files"))
        entry = item.get("entry")
        if isinstance(entry, dict):
            entry = dict(entry)
            for key in ("entryrva", "vbase", "vsize", "entry_va"):
                if key in entry:
                    entry[key] = as_int(entry[key])
            if isinstance(entry.get("sections"), list):
                entry["sections"] = [
                    {key: as_int(value) for key, value in section.items()}
                    for section in entry["sections"] if isinstance(section, dict)
                ]
        else:
            entry = None
        segments.append({
            "label": label,
            "segment_base": base,
            "pTOC": as_int(item.get("pTOC")),
            "romhdr": romhdr,
            "module_names": module_names,
            "file_names": file_names,
            "entry": entry,
            "payload_sha256": item.get("payload_sha256"),
            "payload_bytes": as_int(item.get("payload_bytes")),
            "payload_complete": item.get("payload_complete"),
            "source": "%s: segment %d" % (source, index),
        })
    return segments


def load_json_segments(path):
    with open(path, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    return json_segments(document, os.path.basename(path))


# --------------------------------------------------------------------------
# Criteria
# --------------------------------------------------------------------------


def eval_ram_overlap(hdr, span, a_plan):
    first, last = span
    if first is None or last is None or last <= first:
        return criterion(UNKNOWN, "physfirst/physlast missing or empty")
    image0, image1 = a_plan["image_phys"]
    ram0, ram1 = a_plan["ram_phys"]
    if overlaps(first, last, image0, image1):
        return criterion(FAIL, "ROM span %s-%s overlaps A's image %s-%s"
                         % (hx(first), hx(last), hx(image0), hx(image1)))
    if overlaps(first, last, ram0, ram1):
        return criterion(FAIL, "ROM span %s-%s overlaps A's RAM window %s-%s"
                         % (hx(first), hx(last), hx(ram0), hx(ram1)))
    if last > ram0:
        return criterion(UNKNOWN,
                         "ROM span %s-%s is disjoint from A's plan but sits above "
                         "A's RAM start %s, outside the observed kernel ordering"
                         % (hx(first), hx(last), hx(ram0)))
    ram_end = as_int(hdr.get("ulRAMEnd"))
    if not ram_end:
        return criterion(UNKNOWN,
                         "ROM span %s-%s sits below A's RAM %s-%s, but ulRAMEnd is "
                         "not recorded, so the closing edge cannot be checked"
                         % (hx(first), hx(last), hx(ram0), hx(ram1)))
    closing = va_to_phys(ram_end)
    if closing != image0:
        return criterion(UNKNOWN,
                         "ulRAMEnd %s (physical %s) does not close at A's image "
                         "start %s" % (hx(ram_end), hx(closing), hx(image0)))
    return criterion(PASS,
                     "ROM span %s-%s sits below A's RAM %s-%s and ulRAMEnd %s "
                     "(physical %s) closes exactly at A's image start"
                     % (hx(first), hx(last), hx(ram0), hx(ram1),
                        hx(ram_end), hx(closing)))


def eval_ram_window(hdr, span):
    start = as_int(hdr.get("ulRAMStart"))
    free = as_int(hdr.get("ulRAMFree"))
    end = as_int(hdr.get("ulRAMEnd"))
    if not start and not free and not end:
        return criterion(UNKNOWN, "ulRAMStart/ulRAMFree/ulRAMEnd not recorded "
                                  "(all zero)")
    if not start or not free or not end:
        return criterion(UNKNOWN, "partial RAM window: start=%s free=%s end=%s"
                         % (hx(start), hx(free), hx(end)))
    pstart, pfree, pend = va_to_phys(start), va_to_phys(free), va_to_phys(end)
    if not (pstart <= pfree < pend):
        return criterion(FAIL, "RAM window out of order: %s <= %s < %s does not hold"
                         % (hx(pstart), hx(pfree), hx(pend)))
    if pstart % 0x1000 or pend % 0x1000:
        return criterion(FAIL, "RAM window not 4 KiB aligned (%s, %s)"
                         % (hx(pstart), hx(pend)))
    first, last = span
    if first is not None and last is not None and overlaps(pstart, pend, first, last):
        return criterion(FAIL, "RAM window %s-%s overlaps the segment's own ROM span"
                         % (hx(pstart), hx(pend)))
    if pend > 0x10000000:
        return criterion(FAIL, "RAM window ends at %s, above the 0x10000000 "
                               "peripheral area (EXP-37)" % hx(pend))
    note = ""
    if start == RECORDED_RAM_START:
        note = "; ulRAMStart matches the 0x89e40000 recorded for A/B/C (EXP-36)"
    return criterion(PASS,
                     "%s <= %s < %s (physical %s <= %s < %s), 4 KiB aligned, "
                     "clear of the ROM span%s"
                     % (hx(start), hx(free), hx(end), hx(pstart), hx(pfree),
                        hx(pend), note))


def eval_p_extensions(hdr, va_span):
    value = hdr.get("pExtensions")
    if value is None:
        return criterion(UNKNOWN, "pExtensions missing from the report")
    value = as_int(value)
    if value == 0:
        return criterion(PASS, "pExtensions = 0 (no extension block)")
    if value % 4:
        return criterion(FAIL, "pExtensions %s is not 4-byte aligned" % hx(value))
    region = ("inside the observed 0x88... kernel region"
              if 0x88000000 <= value < 0x89000000
              else "outside the observed 0x88... kernel region")
    first, last = va_span
    if first is None or last is None:
        return criterion(UNKNOWN, "pExtensions %s (%s), but the ROM span is unknown"
                         % (hx(value), region))
    if first <= value < last:
        note = ""
        if value == RECORDED_PEXT:
            note = "; equals the value recorded for A/B/C (EXP-36)"
        return criterion(PASS, "pExtensions %s, inside the ROM span %s-%s, %s%s"
                         % (hx(value), hx(first), hx(last), region, note))
    return criterion(FAIL, "pExtensions %s, outside the ROM span %s-%s (%s): "
                           "the IPL could not read it"
                     % (hx(value), hx(first), hx(last), region))


def eval_kernel_modules(names):
    if names is None:
        return criterion(UNKNOWN, "module list not available in this input")
    if not names:
        return criterion(UNKNOWN, "module list is empty")
    lower = {name.lower() for name in names}
    present = [name for name in KERNEL_MODULES if name in lower]
    missing = [name for name in KERNEL_MODULES if name not in lower]
    if not present:
        return criterion(FAIL, "none of the %d kernel modules present in %d module "
                               "name(s): checked %s"
                         % (len(KERNEL_MODULES), len(names),
                            ", ".join(KERNEL_MODULES)))
    if "nk.exe" not in lower:
        return criterion(FAIL, "nk.exe absent; only %s present"
                         % short_list(present))
    if missing:
        return criterion(UNKNOWN, "incomplete kernel set: %d/5 present (%s), "
                                  "missing %s"
                         % (len(present), short_list(present),
                            ", ".join(missing)))
    return criterion(PASS, "5/5 kernel modules present: %s"
                     % ", ".join(KERNEL_MODULES))


def updater_artefacts(module_names, file_names):
    modules = []
    for name in module_names or []:
        lower = name.lower()
        if lower in UPDATER_MODULES or lower.endswith(UPDATER_SUFFIX):
            modules.append(name)
    files = [name for name in file_names or [] if name.lower() in UPDATER_FILES]
    return modules, files


def eval_updater_set(module_names, file_names):
    if module_names is None and file_names is None:
        return criterion(UNKNOWN, "neither module nor file names available")
    modules, files = updater_artefacts(module_names, file_names)
    found = modules + files
    distinct = {name.lower() for name in found}
    if len(distinct) >= MIN_UPDATERS:
        return criterion(PASS, "updater set present (%d): %s"
                         % (len(distinct), short_list(found)))
    if len(distinct) == 1:
        return criterion(UNKNOWN, "only one updater artefact (%s); the documented "
                                  "set has several (C-526)" % found[0])
    return criterion(FAIL, "no updater module or file in %d module / %d file "
                           "name(s) (expected e.g. UpdateMng.exe, MapUpdate.exe, "
                           "UpdateNK.skn; C-526)"
                     % (len(module_names or []), len(file_names or [])))


def eval_entry_point(entry, va_span):
    if not entry:
        return criterion(UNKNOWN, "no nk.exe entry data in this input "
                                  "(e32/o32 not available)")
    if entry.get("error"):
        return criterion(UNKNOWN, "nk.exe e32/o32 could not be read: %s"
                         % entry["error"])
    entryrva = as_int(entry.get("entryrva"))
    vbase = as_int(entry.get("vbase"))
    vsize = as_int(entry.get("vsize"))
    if entryrva is None or vbase is None or vsize is None:
        return criterion(UNKNOWN, "entry record incomplete: entryrva=%s vbase=%s "
                                  "vsize=%s"
                         % (hx(entryrva), hx(vbase), hx(vsize)))
    if entryrva == 0:
        return criterion(FAIL, "nk.exe entryrva is 0")
    entry_va = as_int(entry.get("entry_va")) or (vbase + entryrva)
    if not (vbase <= entry_va < vbase + vsize):
        return criterion(FAIL, "entry %s outside nk.exe %s+%s"
                         % (hx(entry_va), hx(vbase), hx(vsize)))
    sections = entry.get("sections") or []
    if not sections:
        return criterion(UNKNOWN, "entry %s is inside nk.exe but no o32 sections "
                                  "are recorded for it" % hx(entry_va))
    code = [sec for sec in sections
            if sec.get("rva") is not None
            and sec["rva"] <= entryrva < sec["rva"] + max(sec.get("vsize") or 0,
                                                          sec.get("psize") or 0)
            and (sec.get("flags") or 0) & (cerom.CNT_CODE | cerom.MEM_EXECUTE)]
    if not code:
        return criterion(FAIL, "entry rva %s is not inside an executable section "
                               "(%d section(s) checked)"
                         % (hx(entryrva), len(sections)))
    first, last = va_span
    if first is not None and last is not None and not (first <= entry_va < last):
        return criterion(FAIL, "entry VA %s outside the ROM span %s-%s"
                         % (hx(entry_va), hx(first), hx(last)))
    first_bytes = entry.get("first_bytes")
    if first_bytes is None:
        return criterion(PASS, "nk.exe entry %s (rva %s in executable section rva "
                               "%s), entry bytes not readable"
                         % (hx(entry_va), hx(entryrva), hx(code[0]["rva"])))
    if int(first_bytes, 16) == 0:
        return criterion(FAIL, "first instruction at entry %s is 0x0000; no code "
                               "there" % hx(entry_va))
    return criterion(PASS, "nk.exe entry %s (rva %s in executable section rva %s), "
                           "first bytes %s"
                     % (hx(entry_va), hx(entryrva), hx(code[0]["rva"]),
                        first_bytes))


def mark_duplicates(rows):
    seen = {}
    for row in rows:
        segment = row["segment"]
        digest = segment.get("payload_sha256")
        length = segment.get("payload_bytes")
        complete = segment.get("payload_complete")
        if not digest or not length:
            row["criteria"]["duplicate"] = criterion(
                UNKNOWN, "no payload bytes available (JSON input without "
                         "payload_sha256/payload_bytes)")
            continue
        if not complete:
            row["criteria"]["duplicate"] = criterion(
                UNKNOWN, "payload truncated: %d byte(s) hashed, coverage "
                         "incomplete" % length)
            continue
        key = (digest, length)
        if key in seen:
            original = seen[key]
            row["criteria"]["duplicate"] = criterion(
                FAIL, "byte-identical to %s at %s (%d bytes, sha256 %s)"
                % (original.get("label") or "?", hx(original.get("segment_base")),
                   length, digest))
        else:
            seen[key] = segment
            row["criteria"]["duplicate"] = criterion(
                PASS, "unique payload (%d bytes, sha256 %s)" % (length, digest))


# --------------------------------------------------------------------------
# Scoring and the verdict
# --------------------------------------------------------------------------


def gate_failures(row):
    failures = []
    for cid in GATE_CRITERIA:
        if row["criteria"][cid]["status"] == FAIL:
            failures.append(cid)
    cpu = as_int((row["segment"].get("romhdr") or {}).get("usCPUType"))
    if cpu is not None and cpu != 0x01A6:
        failures.append("usCPUType 0x%04x != 0x01a6" % cpu)
    return failures


def decide(rows):
    labels = {(row["segment"].get("label") or "").upper() for row in rows}
    missing = [label for label in ("B", "C") if label not in labels]
    if missing:
        return VERDICT_UNKNOWN, ("a comparison needs both a B and a C segment; "
                                 "missing %s, supplied %s"
                                 % (", ".join(missing),
                                    ", ".join(sorted(label or "?" for label in labels)))), []

    representatives = {}
    for label in ("B", "C"):
        group = [row for row in rows
                 if (row["segment"].get("label") or "").upper() == label]
        unique = [row for row in group
                  if row["criteria"]["duplicate"]["status"] != FAIL]
        if not unique:
            return VERDICT_UNKNOWN, ("every %s segment supplied is a "
                                     "byte-identical copy (%d row(s)); no "
                                     "independent %s evidence"
                                     % (label, len(group), label)), []
        digests = {row["segment"].get("payload_sha256") for row in unique}
        if len(digests) > 1:
            return VERDICT_UNKNOWN, ("two different payloads are labelled %s: "
                                     "contradictory input, refusing to choose"
                                     % label), []
        representatives[label] = max(unique, key=lambda row: row["score"])

    eligible = {label: row for label, row in representatives.items()
                if not row["gate_failures"]}
    if not eligible:
        reasons = "; ".join("%s fails %s" % (label, ", ".join(row["gate_failures"]))
                            for label, row in representatives.items())
        return VERDICT_UNKNOWN, "no segment passes the gate criteria (%s)" % reasons, []

    if len(eligible) == 1:
        label, row = next(iter(eligible.items()))
        other = [name for name in representatives if name != label][0]
        if row["decisive"] < MIN_DECISIVE:
            return VERDICT_UNKNOWN, ("%s is the only eligible segment but has "
                                     "only %d decisive criteria"
                                     % (label, row["decisive"])), []
        return label, ("%s is the only segment that passes the gate criteria; %s "
                       "fails %s"
                       % (label, other,
                          ", ".join(representatives[other]["gate_failures"]))), []

    b_row, c_row = representatives["B"], representatives["C"]
    differences = [cid for cid, _w, _k, _d in CRITERIA
                   if cid != "duplicate"
                   and b_row["criteria"][cid]["status"]
                   != c_row["criteria"][cid]["status"]]
    detail = ", ".join("%s (%s/%s)" % (cid,
                                       b_row["criteria"][cid]["status"],
                                       c_row["criteria"][cid]["status"])
                       for cid in differences) or "none"
    if not differences:
        return VERDICT_UNKNOWN, ("scores tied at %+d/%+d; no criterion "
                                 "separates B and C"
                                 % (b_row["score"], c_row["score"])), []
    if len(differences) < MIN_DISCRIMINATORS:
        return VERDICT_UNKNOWN, ("only one criterion separates B from C (%s); a single "
                                 "criterion is not enough for a verdict" % detail), differences
    structural = [cid for cid in differences if cid in STRUCTURAL]
    if not structural:
        return VERDICT_UNKNOWN, ("only module/role criteria separate B from C "
                                 "(%s); no structural criterion differs, so this "
                                 "identifies build role, not the boot choice"
                                 % detail), differences
    if b_row["score"] == c_row["score"]:
        return VERDICT_UNKNOWN, ("conflicting evidence: %s differ, but the "
                                 "scores tie at %+d"
                                 % (detail, b_row["score"])), differences
    winner = "B" if b_row["score"] > c_row["score"] else "C"
    if representatives[winner]["decisive"] < MIN_DECISIVE:
        return VERDICT_UNKNOWN, ("%s leads but only %d criteria could be "
                                 "evaluated"
                                 % (winner,
                                    representatives[winner]["decisive"])), differences
    loser = "C" if winner == "B" else "B"
    return winner, ("%s %+d vs %s %+d; discriminators: %s; structural: %s"
                    % (winner, representatives[winner]["score"],
                       loser, representatives[loser]["score"],
                       detail, ", ".join(structural))), differences


def evaluate(segments, a_plan=None):
    a_plan = a_plan or plan_from_segments(segments)
    rows = []
    for segment in segments:
        hdr = segment.get("romhdr") or {}
        span = span_of(hdr)
        va_span = va_span_of(hdr)
        row = {
            "segment": segment,
            "span": span,
            "criteria": {
                "ram_overlap": eval_ram_overlap(hdr, span, a_plan),
                "ram_window": eval_ram_window(hdr, span),
                "p_extensions": eval_p_extensions(hdr, va_span),
                "kernel_modules": eval_kernel_modules(segment.get("module_names")),
                "updater_set": eval_updater_set(segment.get("module_names"),
                                                segment.get("file_names")),
                "entry_point": eval_entry_point(segment.get("entry"), va_span),
                "duplicate": criterion(UNKNOWN, "not evaluated yet"),
            },
        }
        rows.append(row)

    mark_duplicates(rows)
    for row in rows:
        for cid, item in row["criteria"].items():
            sign = 1 if item["status"] == PASS else -1 if item["status"] == FAIL else 0
            item["score"] = WEIGHTS[cid] * sign
        row["score"] = sum(item["score"] for item in row["criteria"].values())
        row["gate_failures"] = gate_failures(row)
        row["decisive"] = sum(1 for item in row["criteria"].values()
                              if item["status"] != UNKNOWN)

    verdict, evidence, discriminators = decide(rows)
    return {
        "schema": SCHEMA,
        "generator": GENERATOR,
        "a_plan": {
            "source": a_plan["source"],
            "image_phys": [hx(a_plan["image_phys"][0]), hx(a_plan["image_phys"][1])],
            "ram_phys": [hx(a_plan["ram_phys"][0]), hx(a_plan["ram_phys"][1])],
        },
        "criteria": [{"id": cid, "weight": weight, "kind": kind,
                      "description": description}
                     for cid, weight, kind, description in CRITERIA],
        "segments": [segment_report(row) for row in rows],
        "verdict": verdict,
        "verdict_evidence": evidence,
        "discriminators": discriminators,
    }


def segment_report(row):
    segment = row["segment"]
    label = segment.get("label")
    return {
        "label": label,
        "candidate": (label or "").upper() in ("B", "C"),
        "source": segment.get("source"),
        "segment_base": segment.get("segment_base"),
        "pTOC": segment.get("pTOC"),
        "physfirst": va_span_of(segment.get("romhdr"))[0],
        "physlast": va_span_of(segment.get("romhdr"))[1],
        "phys_first_phys": row["span"][0],
        "phys_last_phys": row["span"][1],
        "payload_sha256": segment.get("payload_sha256"),
        "payload_bytes": segment.get("payload_bytes"),
        "payload_complete": segment.get("payload_complete"),
        "romhdr": segment.get("romhdr"),
        "module_names": segment.get("module_names"),
        "file_names": segment.get("file_names"),
        "entry": segment.get("entry"),
        "criteria": {cid: {"status": item["status"], "score": item["score"],
                           "evidence": item["evidence"]}
                     for cid, item in row["criteria"].items()},
        "score": row["score"],
        "decisive": row["decisive"],
        "gate_failures": row["gate_failures"],
    }


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def display_labels(segments):
    """Label each row; a repeated label gets a ``#n`` suffix for the table."""
    seen = {}
    labels = []
    for segment in segments:
        label = segment["label"] or "?"
        seen[label] = seen.get(label, 0) + 1
        labels.append(label if seen[label] == 1 else "%s#%d" % (label, seen[label]))
    return labels


def format_report(report):
    lines = []
    segments = report["segments"]
    labels = display_labels(segments)
    lines.append("kernel_select: %d segment(s) evaluated: %s"
                 % (len(segments),
                    ", ".join("%s@%s" % (label, hx(segment["segment_base"]))
                              for label, segment in zip(labels, segments))))
    plan = report["a_plan"]
    lines.append("A plan: image %s-%s, RAM %s-%s"
                 % (plan["image_phys"][0], plan["image_phys"][1],
                    plan["ram_phys"][0], plan["ram_phys"][1]))
    lines.append("  source: %s" % plan["source"])
    lines.append("")
    lines.append("segments:")
    lines.append("  %-2s %-6s %-11s %-11s %-11s %6s %6s  %s"
                 % ("#", "label", "base", "rom_first", "rom_last", "score",
                    "decis", "gates"))
    for index, segment in enumerate(segments):
        gates = ", ".join(segment["gate_failures"]) or "ok"
        lines.append("  %-2d %-6s %-11s %-11s %-11s %+6d %6s  %s"
                     % (index, segment["label"] or "?",
                        hx(segment["segment_base"]),
                        hx(segment["phys_first_phys"]),
                        hx(segment["phys_last_phys"]), segment["score"],
                        "%d/%d" % (segment["decisive"], len(report["criteria"])),
                        gates))
    lines.append("  (rom_first/rom_last are physical; ROMHDR physfirst/physlast "
                 "are the same span as VAs)")
    lines.append("")
    width = max(len(criterion["id"]) for criterion in report["criteria"])
    lines.append("%-*s %6s  %s"
                 % (width, "criterion", "weight",
                    "  ".join("%-18s" % label for label in labels)))
    for definition in report["criteria"]:
        cid = definition["id"]
        cells = []
        for segment in segments:
            item = segment["criteria"][cid]
            cells.append("%-18s" % ("%s %+d" % (item["status"], item["score"])))
        lines.append("%-*s %6d  %s"
                     % (width, cid, definition["weight"], "  ".join(cells)))
    lines.append("")
    lines.append("evidence:")
    for label, segment in zip(labels, segments):
        suffix = ""
        if segment["criteria"]["duplicate"]["status"] == FAIL:
            suffix = " (byte-identical copy)"
        lines.append("  %s%s:" % (label, suffix))
        for definition in report["criteria"]:
            cid = definition["id"]
            item = segment["criteria"][cid]
            lines.append("    %-*s [%s %+d] %s"
                         % (width, cid, item["status"], item["score"],
                            item["evidence"]))
    lines.append("")
    lines.append("verdict: %s" % report["verdict"])
    lines.append("  %s" % report["verdict_evidence"])
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Self-test: synthetic segments only, no vendor data
# --------------------------------------------------------------------------

SYNTH_SIZE = 0x40000
SYNTH_NAME_OFF = 0x1000
SYNTH_E32_OFF = 0x2000
SYNTH_O32_OFF = 0x3000
SYNTH_HDR_OFF = 0x8000
SYNTH_TOC_OFF = SYNTH_HDR_OFF + cerom.ROMHDR_SIZE
SYNTH_DATA_OFF = 0x10000
SYNTH_FILE_LOAD_OFF = 0x38000
SYNTH_MODULE_STRIDE = 0x100
SYNTH_DATA_STRIDE = 0x800

SYNTH_KERNEL_MODULES = ["nk.exe", "coredll.dll", "filesys.exe", "device.exe",
                        "gwes.exe"]
SYNTH_UPDATERS = ["UpdateMng.exe", "PRGUpdate.exe", "MapUpdate.exe",
                  "BtUpdate.exe", "DisplayUpdate.exe"]
SYNTH_RAM_OK = (0x89E40000, 0x89E80000, 0x8CAE1000)
SYNTH_RAM_OPEN = (0x89E40000, 0x89E80000, 0x8CA00000)


def build_synthetic_segment(image_start, va_base, modules, files=(),
                            ram=SYNTH_RAM_OK, p_extensions=None,
                            entry_broken=False, fill=0x00):
    """Minimal CE XIP segment laid out exactly as ``cerom.CERom`` reads it.

    ROMHDR at image_start + 0x8000, TOC behind it, one ``e32_rom`` and two
    ``o32_rom`` records per module (one executable, one compressed), names in
    a pool at 0x1000.  The area past the TOC is zero, so the default
    ``pExtensions`` (``va_base + 0x30a4``) points at zeroed data inside the
    span exactly like the recorded builds; the extension contents themselves
    are not modelled.
    """
    data = bytearray(image_start + SYNTH_SIZE)
    if fill:
        data[:] = bytes([fill]) * len(data)
    start = image_start

    name_va = {}
    offset = SYNTH_NAME_OFF
    for name in list(modules) + list(files):
        raw = name.encode("latin1") + b"\0"
        data[start + offset:start + offset + len(raw)] = raw
        name_va[name] = va_base + offset
        offset += len(raw)
    if offset > SYNTH_E32_OFF:
        raise ValueError("synthetic name pool overflows into e32_rom")

    struct.pack_into("<4sII", data, start + 0x40, b"ECEC",
                     va_base + SYNTH_HDR_OFF, SYNTH_HDR_OFF)

    hdr = dict(
        dllfirst=0, dlllast=0,
        physfirst=va_base, physlast=va_base + SYNTH_SIZE,
        nummods=len(modules),
        ulRAMStart=ram[0], ulRAMFree=ram[1], ulRAMEnd=ram[2],
        ulCopyEntries=0, ulCopyOffset=0, ulProfileLen=0, ulProfileOffset=0,
        numfiles=len(files),
        ulKernelFlags=0, ulFSRamPercent=0, ulDrivglobStart=0, ulDrivglobLen=0,
        usCPUType=0x01A6, usMiscFlags=0x0002,
        pExtensions=(va_base + 0x30A4 if p_extensions is None else p_extensions),
        ulTrackingStart=0, ulTrackingLen=0,
    )
    struct.pack_into("<17IHHIII", data, start + SYNTH_HDR_OFF,
                     *[hdr[key] for key in cerom.ROMHDR_FIELDS],
                     hdr["usCPUType"], hdr["usMiscFlags"], hdr["pExtensions"],
                     hdr["ulTrackingStart"], hdr["ulTrackingLen"])

    toc = start + SYNTH_TOC_OFF
    for index, name in enumerate(modules):
        vbase = va_base + 0x20000 + index * 0x1000
        e32_off = SYNTH_E32_OFF + index * SYNTH_MODULE_STRIDE
        o32_off = SYNTH_O32_OFF + index * SYNTH_MODULE_STRIDE
        struct.pack_into("<8I", data, toc + cerom.TOC_SIZE * index,
                         0x0000001C, 0, 0, 0x8000, name_va[name],
                         va_base + e32_off, va_base + o32_off, vbase)
        broken = entry_broken and name.lower() == "nk.exe"
        entryrva = 0x3000 if broken else 0x1000
        struct.pack_into("<HHIIHHIIIII", data, start + e32_off,
                         2, 0x0002, entryrva, vbase, 1, 0, 0x1000, 0x2000,
                         0, 0, 0)
        struct.pack_into("<18I", data, start + e32_off + 36, *([0] * 18))
        struct.pack_into("<6I", data, start + o32_off,
                         0x1000, 0x1000, 0x400,
                         va_base + SYNTH_DATA_OFF + index * SYNTH_DATA_STRIDE,
                         vbase + 0x1000, 0x60000020)
        struct.pack_into("<6I", data, start + o32_off + cerom.O32_SIZE,
                         0x1000, 0x2000, 0x100,
                         va_base + SYNTH_DATA_OFF + 0x400
                         + index * SYNTH_DATA_STRIDE,
                         vbase + 0x2000, 0xC0002040)
        # SH-4 nop (`09 00`) at the entry rva, so "first bytes" is real code.
        data[start + SYNTH_DATA_OFF + index * SYNTH_DATA_STRIDE:
             start + SYNTH_DATA_OFF + index * SYNTH_DATA_STRIDE + 2] = b"\x09\x00"

    file_toc = toc + cerom.TOC_SIZE * len(modules)
    for index, name in enumerate(files):
        struct.pack_into("<7I", data, file_toc + cerom.FILES_SIZE * index,
                         0x00000040, 0, 0, 0x200, 0x100, name_va[name],
                         va_base + SYNTH_FILE_LOAD_OFF)

    return bytes(data), hdr


def selftest():
    """Run the synthetic decision cases; return 0 (raise on mismatch)."""
    checks = []

    def ok(label, got, want):
        if got != want:
            raise AssertionError("%s: got %r, want %r" % (label, got, want))
        checks.append(label)

    with tempfile.TemporaryDirectory(prefix="kernel-select-selftest-") as tmp:
        counter = [0]

        def write_segment(image_start, va_base, modules, files=(), **kwargs):
            counter[0] += 1
            payload, hdr = build_synthetic_segment(
                image_start, va_base, modules, files=files, **kwargs)
            path = os.path.join(tmp, "seg%d.img" % counter[0])
            with open(path, "wb") as handle:
                handle.write(payload)
            return path, payload, hdr

        last_error = [""]

        def run(argv):
            buffer, errors = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(errors):
                code = main(argv)
            last_error[0] = errors.getvalue()
            return code, buffer.getvalue()

        def run_json(argv):
            code, text = run(argv + ["--json"])
            if code != 0:
                raise AssertionError("main(%r) exited %d" % (argv, code))
            return json.loads(text)

        # --- 0. input compatibility: a ROM from cerom.build_synthetic_rom ---
        rom, layout = cerom.build_synthetic_rom()
        path = os.path.join(tmp, "cerom-synthetic.img")
        with open(path, "wb") as handle:
            handle.write(rom)
        code, text = run(["--segment", "B=%s@0x%x" % (path, layout["image_start"])])
        ok("cerom synthetic CLI exit", code, 0)
        ok("cerom synthetic single segment -> UNKNOWN", "verdict: UNKNOWN" in text, True)
        report = run_json(["--segment", "B=%s@0x%x" % (path, layout["image_start"])])
        ok("cerom synthetic schema", report["schema"], SCHEMA)
        ok("cerom synthetic label", report["segments"][0]["label"], "B")
        ok("cerom synthetic module names",
           report["segments"][0]["module_names"], ["NK.EXE", "NAVI.EXE"])
        ok("cerom synthetic kernel set incomplete",
           report["segments"][0]["criteria"]["kernel_modules"]["status"], UNKNOWN)
        ok("cerom synthetic kernel set names its gap",
           "coredll.dll" in report["segments"][0]["criteria"]["kernel_modules"]["evidence"],
           True)
        ok("cerom synthetic verdict", report["verdict"], VERDICT_UNKNOWN)

        # --- 1. clear B: only B has the updater set and a closing RAM window ---
        b_path, b_bytes, b_hdr = write_segment(0x200, 0x88000000,
                                               SYNTH_KERNEL_MODULES + SYNTH_UPDATERS,
                                               files=["UpdateNK.skn"])
        c_path, c_bytes, c_hdr = write_segment(0x200, 0x88000000,
                                               SYNTH_KERNEL_MODULES,
                                               ram=SYNTH_RAM_OPEN)
        ok("synthetic B payload hashed", b_hdr["nummods"], 10)
        ok("synthetic C payload differs from B", b_bytes == c_bytes, False)
        code, text = run(["--segment", "B=%s@0x200" % b_path,
                          "--segment", "C=%s@0x200" % c_path])
        ok("clear B CLI exit", code, 0)
        ok("clear B verdict", "verdict: B" in text, True)
        report = run_json(["--segment", "B=%s@0x200" % b_path,
                           "--segment", "C=%s@0x200" % c_path])
        ok("clear B report verdict", report["verdict"], "B")
        ok("clear B scores", [s["score"] for s in report["segments"]], [13, 8])
        ok("clear B B-criteria",
           {cid: item["status"] for cid, item in report["segments"][0]["criteria"].items()},
           {"ram_overlap": PASS, "ram_window": PASS, "p_extensions": PASS,
            "kernel_modules": PASS, "updater_set": PASS, "entry_point": PASS,
            "duplicate": PASS})
        ok("clear B C-criteria",
           {cid: item["status"] for cid, item in report["segments"][1]["criteria"].items()},
           {"ram_overlap": UNKNOWN, "ram_window": PASS, "p_extensions": PASS,
            "kernel_modules": PASS, "updater_set": FAIL, "entry_point": PASS,
            "duplicate": PASS})
        ok("clear B discriminators", report["discriminators"],
           ["ram_overlap", "updater_set"])
        ok("clear B evidence names the structural gap",
           "ulRAMEnd" in report["segments"][1]["criteria"]["ram_overlap"]["evidence"],
           True)

        # --- 2. clear C: the same table, mirrored ---
        b2_path, _b2, _h = write_segment(0x200, 0x88000000, SYNTH_KERNEL_MODULES,
                                         ram=SYNTH_RAM_OPEN)
        c2_path, _c2, _h = write_segment(0x200, 0x88000000,
                                         SYNTH_KERNEL_MODULES + SYNTH_UPDATERS,
                                         files=["UpdateNK.skn"])
        report = run_json(["--segment", "B=%s@0x200" % b2_path,
                           "--segment", "C=%s@0x200" % c2_path])
        ok("clear C verdict", report["verdict"], "C")
        ok("clear C scores", [s["score"] for s in report["segments"]], [8, 13])

        # --- 3. tie: identical evidence on both sides -> UNKNOWN ---
        t1_path, _t1, _h = write_segment(0x200, 0x88000000, SYNTH_KERNEL_MODULES,
                                         ram=SYNTH_RAM_OPEN)
        t2_path, _t2, _h = write_segment(0x200, 0x88000000, SYNTH_KERNEL_MODULES,
                                         ram=SYNTH_RAM_OPEN, fill=0x5A)
        report = run_json(["--segment", "B=%s@0x200" % t1_path,
                          "--segment", "C=%s@0x200" % t2_path])
        ok("tie verdict", report["verdict"], VERDICT_UNKNOWN)
        ok("tie scores", [s["score"] for s in report["segments"]], [8, 8])
        ok("tie evidence", "no criterion separates" in report["verdict_evidence"], True)
        ok("tie discriminators", report["discriminators"], [])

        # --- 4. missing kernel names on both sides -> UNKNOWN ---
        m1_path, _m1, _h = write_segment(0x200, 0x88000000,
                                         ["Navi.exe", "OBJDLL.dll"],
                                         files=["ReleaseMain.skn"])
        m2_path, _m2, _h = write_segment(0x200, 0x88000000,
                                         ["Navi.exe", "STDDLL.dll"],
                                         files=["ReleaseMain.skn"])
        report = run_json(["--segment", "B=%s@0x200" % m1_path,
                           "--segment", "C=%s@0x200" % m2_path])
        ok("missing kernel names verdict", report["verdict"], VERDICT_UNKNOWN)
        ok("missing kernel names status",
           [s["criteria"]["kernel_modules"]["status"] for s in report["segments"]],
           [FAIL, FAIL])
        ok("missing kernel names failure is a gate",
           [s["gate_failures"] for s in report["segments"]][0], ["kernel_modules"])
        ok("missing kernel names evidence",
           "none of the 5 kernel modules" in report["segments"][0]["criteria"]["kernel_modules"]["evidence"],
           True)

        # --- 5. byte-identical duplicate pair is one build, not two ---
        same = dict(modules=SYNTH_KERNEL_MODULES + SYNTH_UPDATERS,
                    files=["UpdateNK.skn"])
        dup1_path, dup_bytes, _h = write_segment(0x200, 0x88000000, **same)
        dup2_path, dup_bytes2, _h = write_segment(0x200, 0x88000000, **same)
        ok("duplicate payloads are byte-identical", dup_bytes == dup_bytes2, True)
        d_path, _d, _h = write_segment(0x200, 0x88000000, SYNTH_KERNEL_MODULES,
                                       entry_broken=True)
        report = run_json(["--segment", "B=%s@0x200" % dup1_path,
                           "--segment", "B=%s@0x200" % dup2_path,
                           "--segment", "C=%s@0x200" % d_path])
        ok("duplicate pair verdict", report["verdict"], "B")
        ok("duplicate pair duplicate statuses",
           [s["criteria"]["duplicate"]["status"] for s in report["segments"]],
           [PASS, FAIL, PASS])
        ok("duplicate pair evidence",
           "byte-identical to B" in report["segments"][1]["criteria"]["duplicate"]["evidence"],
           True)
        ok("duplicate pair disqualifies C",
           report["segments"][2]["gate_failures"], ["entry_point"])
        ok("duplicate pair evidence names entry",
           "entry_point" in report["verdict_evidence"], True)
        report = run_json(["--segment", "B=%s@0x200" % dup1_path,
                           "--segment", "B=%s@0x200" % dup2_path])
        ok("duplicate pair alone -> UNKNOWN", report["verdict"], VERDICT_UNKNOWN)
        ok("duplicate pair alone asks for C",
           "missing C" in report["verdict_evidence"], True)

        # Same pair inside one file, like the real A/A-copy and B/B-copy pairs.
        pair = bytearray(0x50000 + len(b_bytes))
        pair[0:len(b_bytes)] = b_bytes
        pair[0x50000:0x50000 + len(b_bytes)] = b_bytes
        pair_path = os.path.join(tmp, "pair.img")
        with open(pair_path, "wb") as handle:
            handle.write(pair)
        report = run_json(["--segment", "B=%s@0x200" % pair_path,
                           "--segment", "B=%s@0x50200" % pair_path,
                           "--segment", "C=%s@0x200" % c_path])
        ok("in-file duplicate copy is detected",
           [s["criteria"]["duplicate"]["status"] for s in report["segments"]],
           [PASS, FAIL, PASS])
        ok("in-file duplicate evidence names the base",
           "0x00000200" in report["segments"][1]["criteria"]["duplicate"]["evidence"],
           True)

        # --- 6. --from-json round-trip must reproduce the verdict ---
        report = run_json(["--segment", "B=%s@0x200" % b_path,
                           "--segment", "C=%s@0x200" % c_path])
        json_path = os.path.join(tmp, "kernel-select.json")
        with open(json_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle)
        reloaded = run_json(["--from-json", json_path])
        ok("from-json verdict", reloaded["verdict"], report["verdict"])
        ok("from-json scores",
           [s["score"] for s in reloaded["segments"]],
           [s["score"] for s in report["segments"]])
        ok("from-json criteria",
           [{cid: item["status"] for cid, item in s["criteria"].items()}
            for s in reloaded["segments"]],
           [{cid: item["status"] for cid, item in s["criteria"].items()}
            for s in report["segments"]])
        ok("from-json labels",
           [s["label"] for s in reloaded["segments"]], ["B", "C"])

        # --- 7. JSON shape tolerance: memmap-style blocks, no entry/hash ---
        memmap_doc = {
            "segments": [{
                "segment_base": "0x3e00200",
                "romhdr": b_hdr,
                "modules": [{"name": name, "vbase": "0x88020000", "sections": []}
                            for name in SYNTH_KERNEL_MODULES + SYNTH_UPDATERS],
            }]
        }
        memmap_path = os.path.join(tmp, "memmap.json")
        with open(memmap_path, "w", encoding="utf-8") as handle:
            json.dump(memmap_doc, handle)
        code, text = run(["--from-json", memmap_path])
        ok("memmap-shaped JSON exit", code, 0)
        report = run_json(["--from-json", memmap_path])
        ok("memmap-shaped JSON label inferred",
           report["segments"][0]["label"], "B")
        ok("memmap-shaped JSON entry unknown",
           report["segments"][0]["criteria"]["entry_point"]["status"], UNKNOWN)
        ok("memmap-shaped JSON duplicate unknown",
           report["segments"][0]["criteria"]["duplicate"]["status"], UNKNOWN)
        ok("memmap-shaped JSON one label -> UNKNOWN", report["verdict"], VERDICT_UNKNOWN)

        # --- 8. the recorded B/C fields (EXP-36) must NOT yield a verdict ---
        # No vendor bytes here: only the ROMHDR values and module names that
        # EXP-2026-11-05-36 recorded.  ulRAMFree/ulRAMEnd were not written
        # down for B/C, so the RAM criteria stay unknown and the updater set
        # is the single difference - which is exactly why the real answer is
        # still UNKNOWN (C-529).
        recorded = {
            "segments": [
                {
                    "label": "B", "segment_base": 0x03E00200,
                    "romhdr": {"physfirst": 0x88000000, "physlast": 0x886E18A4,
                               "nummods": 91, "numfiles": 11,
                               "ulRAMStart": 0x89E40000, "pExtensions": 0x880030A4,
                               "usCPUType": 0x01A6},
                    "modules": [{"name": name} for name in
                                SYNTH_KERNEL_MODULES + SYNTH_UPDATERS],
                },
                {
                    "label": "C", "segment_base": 0x05200200,
                    "romhdr": {"physfirst": 0x88000000, "physlast": 0x886683D8,
                               "nummods": 88, "numfiles": 10,
                               "ulRAMStart": 0x89E40000, "pExtensions": 0x880030A4,
                               "usCPUType": 0x01A6},
                    "modules": [{"name": name} for name in
                                SYNTH_KERNEL_MODULES + ["TestMode.exe",
                                                        "SdCardLch.exe"]],
                },
            ]
        }
        recorded_path = os.path.join(tmp, "recorded-bc.json")
        with open(recorded_path, "w", encoding="utf-8") as handle:
            json.dump(recorded, handle)
        report = run_json(["--from-json", recorded_path])
        ok("recorded B/C verdict", report["verdict"], VERDICT_UNKNOWN)
        ok("recorded B/C discriminators", report["discriminators"], ["updater_set"])
        ok("recorded B/C single-criterion refusal",
           "only one criterion separates" in report["verdict_evidence"], True)
        ok("recorded B/C kernel set",
           [s["criteria"]["kernel_modules"]["status"] for s in report["segments"]],
           [PASS, PASS])
        ok("recorded B/C RAM window stays unknown",
           [s["criteria"]["ram_window"]["status"] for s in report["segments"]],
           [UNKNOWN, UNKNOWN])
        ok("recorded B/C scores",
           [s["score"] for s in report["segments"]], [5, 3])

        # --- 9. usage errors: no input, bad segment spec, mismatched pairs ---
        code, _text = run([])
        ok("no input exit", code, 2)
        ok("no input message", "no segments" in last_error[0], True)
        code, _text = run(["--segment", "no-separator"])
        ok("bad segment spec exit", code, 2)
        ok("bad segment spec message", "LABEL=PATH[@OFFSET]" in last_error[0], True)
        code, _text = run(["--image", b_path, "--label", "B", "--image", b_path,
                           "--image-start", "0x200"])
        ok("mismatched --image-start count exit", code, 2)
        ok("mismatched --image-start message",
           "--image-start must be given" in last_error[0], True)
        code, text = run(["--segment", "B=%s@0x200" % b_path])
        ok("one label only exit", code, 0)
        ok("one label only says what is missing", "missing C" in text, True)

    print("kernel_select selftest: %d checks OK (synthetic segments, no vendor data)"
          % len(checks))
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_segment_spec(spec):
    if "=" not in spec:
        raise ValueError("--segment expects LABEL=PATH[@OFFSET], got %r" % spec)
    label, rest = spec.split("=", 1)
    offset = None
    if "@" in rest:
        candidate, tail = rest.rsplit("@", 1)
        try:
            offset = int(tail, 0)
        except ValueError:
            offset = None
        else:
            rest = candidate
    if not label:
        raise ValueError("--segment %r has an empty label" % spec)
    return label, rest, offset


def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", action="append", default=[], metavar="PATH",
                        help="raw image (repeatable; pair with --image-start/--label)")
    parser.add_argument("--image-start", action="append", default=[], metavar="OFFSET",
                        help="ECEC segment base in that image (repeatable)")
    parser.add_argument("--label", action="append", default=[], metavar="LABEL",
                        help="build label for the matching --image (repeatable)")
    parser.add_argument("--segment", action="append", default=[], metavar="LABEL=PATH[@OFFSET]",
                        help="one segment, optionally with its ECEC base")
    parser.add_argument("--from-json", action="append", default=[], metavar="FILE",
                        help="saved JSON (this tool, cerom memmap, ce_rom_parse)")
    parser.add_argument("--read-limit", type=float, default=128.0, metavar="MIB",
                        help="read at most this many MiB per image (default 128)")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--out", metavar="FILE", help="also write the JSON report here")
    parser.add_argument("--selftest", action="store_true",
                        help="run the synthetic self-test and exit (needs no image)")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()

    if len(args.image_start) not in (0, len(args.image)):
        print("error: --image-start must be given for every --image or none",
              file=sys.stderr)
        return 2
    if len(args.label) not in (0, len(args.image)):
        print("error: --label must be given for every --image or none",
              file=sys.stderr)
        return 2

    specs = []
    for index, path in enumerate(args.image):
        start = args.image_start[index] if args.image_start else None
        if isinstance(start, str):
            try:
                start = int(start, 0)
            except ValueError:
                print("error: bad --image-start %r" % start, file=sys.stderr)
                return 2
        label = args.label[index] if args.label else None
        specs.append((label, path, start))
    for spec in args.segment:
        try:
            specs.append(parse_segment_spec(spec))
        except ValueError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2

    segments = []
    cache = {}
    try:
        for label, path, start in specs:
            data = load_image(path, args.read_limit, cache)
            rom = cerom.CERom(data, start)
            segments.append(segment_from_cerom(
                label, rom, "%s@%s" % (os.path.basename(path), hx(rom.start))))
        for path in args.from_json:
            segments.extend(load_json_segments(path))
    except (OSError, ValueError, KeyError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if not segments:
        print("error: no segments: give --segment/--image or --from-json",
              file=sys.stderr)
        return 2

    report = evaluate(segments)
    text = json.dumps(report, indent=2) + "\n"
    if args.out:
        directory = os.path.dirname(os.path.abspath(args.out))
        os.makedirs(directory, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
    if args.json:
        sys.stdout.write(text)
    else:
        print(format_report(report))
    if args.out:
        print("wrote %s (verdict %s)" % (args.out, report["verdict"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
