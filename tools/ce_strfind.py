#!/usr/bin/env python3
"""Find a byte string in the modules of a Windows CE ROM image (M3.8).

Walks the CE ROM TOC with ``tools/cerom.py``, searches each module's section
content for an ASCII, UTF-16LE or UTF-16BE needle, and reports
``module / section / RVA / VA / file offset / context``. Sections marked
``IMAGE_SCN_COMPRESSED`` are decoded with ``tools/cecompress.py`` first, so a
name stored in compressed data is found too; a section the decoder cannot
handle is listed as ``UNSUPPORTED`` instead of being skipped silently.

Why this exists: filename searches decide whether firmware code names a map
file (M3.4, M3.8). A negative needs a positive control, so ``--control`` runs
the same scan with a needle known to exist and fails the run if it is missing.

Usage:
  ce_strfind.py IMAGE NEEDLE                      # ASCII, all modules
  ce_strfind.py IMAGE NEEDLE --encoding all       # ASCII + UTF-16LE/BE
  ce_strfind.py --image-start 0x3e00200 IMAGE NEEDLE
  ce_strfind.py IMAGE --control HDD_INFO.TXT NEEDLE
  ce_strfind.py IMAGE NEEDLE --module Navi.exe --json
  ce_strfind.py --selftest                        # synthetic ROM, no vendor data

Exit codes: 0 at least one hit (and the control matched), 1 none/control miss,
2 unreadable image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

import cerom

ASCII = "ascii"
UTF16LE = "utf-16le"
UTF16BE = "utf-16be"
READ_LIMIT = 128 << 20      # builds A/B/C all live in the first 128 MiB


def encodings(text, mode):
    """Return ``[(label, bytes)]`` for the requested needle encodings."""
    out = []
    if mode in ("all", ASCII):
        out.append((ASCII, text.encode("ascii")))
    if mode in ("all", UTF16LE):
        out.append((UTF16LE, text.encode("utf-16-le")))
    if mode in ("all", UTF16BE):
        out.append((UTF16BE, text.encode("utf-16-be")))
    return out


def scan_blob(blob, needle):
    """Yield the offset of every occurrence of ``needle`` in ``blob``."""
    start = 0
    while True:
        i = blob.find(needle, start)
        if i < 0:
            return
        yield i
        start = i + 1


def module_sections(rom, module, data, include_compressed=True):
    """Yield ``(section, blob, status)`` for every section of ``module``.

    ``blob`` is the section content as the CPU would see it; status is
    ``RAW``, ``DECODED``, ``UNSUPPORTED`` (decoder refused), ``SKIPPED``
    ``NO-BYTES`` (BSS) or ``RANGE-ERROR``.
    """
    cc = cerom.cecompress_module()
    for index, section in enumerate(rom.o32(module)):
        if not section["psize"]:
            yield index, section, None, "NO-BYTES"
            continue
        offset = rom.va2file(section["dataptr"])
        end = offset + section["psize"]
        if not (0 <= offset and end <= len(data)):
            yield index, section, None, "RANGE-ERROR"
            continue
        stored = data[offset:end]
        if section["flags"] & cerom.IMAGE_SCN_COMPRESSED:
            if not include_compressed:
                yield index, section, None, "SKIPPED"
                continue
            try:
                blob, _info = cc.decompress_info(stored, section["vsize"])
            except Exception:  # noqa: BLE001 - report, never hide a section
                yield index, section, None, "UNSUPPORTED"
                continue
            yield index, section, blob, "DECODED"
        else:
            yield index, section, stored, "RAW"


def scan_module(rom, data, module_name, needles, include_compressed=True):
    """Search one module; return ``(hits, section_status, errors)``."""
    try:
        module = rom.module(module_name)
    except KeyError:
        return [], [], ["module %r not in the TOC" % module_name]
    vbase = rom.e32(module)["vbase"]
    hits, statuses, errors = [], [], []
    for index, section, blob, status in module_sections(
            rom, module, data, include_compressed):
        record = {"module": module_name, "section_index": index,
                  "section": "sec%d" % index,
                  "section_va": section["realaddr"], "status": status}
        if blob is None:
            if status in ("UNSUPPORTED", "RANGE-ERROR", "NO-BYTES"):
                statuses.append(record)
            continue
        for label, needle in needles:
            for off in scan_blob(blob, needle):
                va = section["realaddr"] + off
                hits.append({
                    "module": module_name,
                    "encoding": label,
                    "section": record["section"],
                    "section_index": index,
                    "section_va": section["realaddr"],
                    "rva": va - vbase,
                    "va": va,
                    "file_offset": (rom.va2file(section["dataptr"]) + off
                                    if status == "RAW" else None),
                    "in": status,
                    "context_ascii": "".join(
                        chr(c) if 32 <= c < 127 else "."
                        for c in blob[max(0, off - 24):off + 64]),
                    "context_hex": blob[max(0, off - 8):off + 48].hex(),
                })
    return hits, statuses, errors


def scan_image(path, needles, image_start=None, module=None,
               include_compressed=True, encoding=ASCII, read_limit=READ_LIMIT):
    """Scan one CE segment (``image_start``) of ``path`` for ``needles``."""
    with open(path, "rb") as fh:
        data = fh.read(min(os.path.getsize(path), read_limit))
    rom = cerom.CERom(data, image_start)
    wanted = []
    for text in needles:
        wanted += encodings(text, encoding)
    names = [m["name"] for m in rom.modules()]
    if module is not None:
        lowered = {n.lower(): n for n in names}
        names = [lowered[module.lower()]] if module.lower() in lowered else []
    hits, statuses, errors = [], [], []
    for name in names:
        h, s, e = scan_module(rom, data, name, wanted, include_compressed)
        hits += h
        statuses += s
        errors += e
    return {
        "image": os.path.basename(path),
        "image_read_bytes": len(data),
        "image_read_sha256": hashlib.sha256(data).hexdigest(),
        "image_start": rom.start,
        "va_base": cerom.hx(rom.va_base),
        "modules_searched": len(names),
        "needles": list(needles),
        "encoding": encoding,
        "hits": hits,
        "sections": statuses,
        "errors": errors,
    }


def print_text(report, title=None):
    if title:
        print("== %s" % title)
    print("image        %s (%d bytes read, sha256 %s)" % (
        report["image"], report["image_read_bytes"],
        report["image_read_sha256"][:16]))
    print("image_start  0x%08x  va_base %s  modules %d" % (
        report["image_start"], report["va_base"],
        report["modules_searched"]))
    print("needles      %s  encoding %s  hits %d" % (
        report["needles"], report["encoding"], len(report["hits"])))
    for hit in report["hits"]:
        print("  %-20s %-9s %-5s rva=0x%08x va=0x%08x file=%s %s" % (
            hit["module"], hit["encoding"], hit["section"], hit["rva"],
            hit["va"],
            "0x%08x" % hit["file_offset"]
            if hit["file_offset"] is not None else "-",
            hit["in"]))
        print("      %s" % hit["context_ascii"])
    for item in report["sections"]:
        if item["status"] != "NO-BYTES":
            print("  section %-18s %-5s %s" % (item["module"],
                                               item["section"],
                                               item["status"]))
    for err in report["errors"]:
        print("  error %s" % err)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return selftest()
    parser = argparse.ArgumentParser(
        description="Find a byte string in the modules of a CE ROM image.")
    parser.add_argument("image")
    parser.add_argument("needles", nargs="+")
    parser.add_argument("--selftest", action="store_true",
                        help="run the synthetic-ROM checks and exit")
    parser.add_argument("--image-start", default=None,
                        help="CE segment base (A 0x200200, B 0x3e00200, "
                             "C 0x5200200); default: autodetect")
    parser.add_argument("--module", default=None,
                        help="search only this module (case-insensitive)")
    parser.add_argument("--control", action="append", default=[],
                        help="positive control needle that must be found")
    parser.add_argument("--encoding", default=ASCII,
                        choices=[ASCII, UTF16LE, UTF16BE, "all"])
    parser.add_argument("--no-compressed", action="store_true",
                        help="stored bytes only; compressed sections are listed "
                             "as UNSUPPORTED")
    parser.add_argument("--read-limit", type=lambda s: int(s, 0),
                        default=READ_LIMIT,
                        help="read at most this many bytes (default 128 MiB)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not os.path.exists(args.image):
        print("error: no such image: %s" % args.image)
        return 2
    start = int(args.image_start, 0) if args.image_start else None
    kwargs = dict(image_start=start, module=args.module,
                  include_compressed=not args.no_compressed,
                  encoding=args.encoding, read_limit=args.read_limit)
    report = scan_image(args.image, args.needles, **kwargs)
    controls = [scan_image(args.image, [c], **kwargs) for c in args.control]
    if args.json:
        print(json.dumps({"search": report, "controls": controls},
                         indent=2, sort_keys=True))
    else:
        print_text(report)
        for control, doc in zip(args.control, controls):
            print_text(doc, "control %r" % control)
    ok = True
    for control, doc in zip(args.control, controls):
        if not doc["hits"]:
            print("FAIL: control %r not found - the scan is not valid"
                  % control)
            ok = False
    if not report["hits"]:
        ok = False
    return 0 if ok else 1


def selftest():
    """Build the synthetic CE ROM and prove hit/miss/decoded-section handling."""
    import tempfile

    rom_bytes, layout = cerom.build_synthetic_rom()
    with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as fh:
        fh.write(rom_bytes)
        path = fh.name
    try:
        cases = []

        def ok(label, got, want):
            cases.append((label, got == want, got, want))

        # NK.EXE sec0 realaddr 0x8CE01000, stored at file 0x5000; the export
        # name sits at file 0x5040. The LZSS plaintext repeats the same name,
        # so keep only the raw section hit.
        hits = scan_image(path, ["MAL_DataVol_getOffset"])["hits"]
        hit = [h for h in hits
               if h["module"] == "NK.EXE" and h["section_index"] == 0]
        ok("ascii hit count", len(hit), 1)
        if hit:
            ok("ascii hit va", hit[0]["va"], 0x8CE01040)
            ok("ascii hit raw", hit[0]["in"], "RAW")
            ok("ascii hit file", hit[0]["file_offset"], 0x5040)

        compressed = scan_image(path, ["ZE0 LZSS section"])["hits"]
        ok("compressed hit found", bool(compressed), True)
        if compressed:
            ok("compressed hit decoded", compressed[0]["in"], "DECODED")
            ok("compressed hit module", compressed[0]["module"], "NK.EXE")
            ok("compressed hit section", compressed[0]["section_index"], 1)

        ok("missing needle", scan_image(path, ["MMAIN001.DAT"])["hits"], [])

        le = scan_image(path, ["ZE0"], encoding=UTF16LE)["hits"]
        ok("utf-16le no false hit", le, [])

        # module 1 (NAVI.EXE) sec1 is an LZX verbatim header: the decoder must
        # refuse it and the section must be reported, not silently skipped.
        doc = scan_image(path, ["x"])
        unsupported = [s for s in doc["sections"] if s["status"] == "UNSUPPORTED"]
        ok("unsupported section reported", len(unsupported), 1)
        ok("unsupported section module", unsupported[0]["module"], "NAVI.EXE")

        failed = [c for c in cases if not c[1]]
        for label, good, got, want in cases:
            print("%-32s %s" % (label, "OK" if good
                                else "FAIL got=%r want=%r" % (got, want)))
        print("selftest: %s (%d/%d)" % ("OK" if not failed else "FAIL",
                                        len(cases) - len(failed), len(cases)))
        return 0 if not failed else 1
    finally:
        os.unlink(path)


if __name__ == "__main__":
    sys.exit(main())
