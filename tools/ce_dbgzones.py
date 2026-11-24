#!/usr/bin/env python3
"""Find Windows CE ``DBGPARAM`` debug-zone records in a CE ROM image.

CE 5 ``dbgapi.h`` (learn.microsoft.com/en-us/previous-versions/windows/
embedded/aa451060)::

    typedef struct _DBGPARAM {
        WCHAR lpszName[32];          // 64 bytes
        WCHAR rglpszZones[16][32];   // 16 x 32 WCHARs = 1024 bytes
        ULONG ulZoneMask;            // struct + 0x440
    } DBGPARAM;

A secondary variant with ``rglpszZones[16][16]`` (mask at +0x240) is also
tested so a wrong stride cannot silently produce a false negative. A record
is accepted only when the name and all 16 zone names are printable ASCII
UTF-16LE, NUL-terminated inside their fields and zero-padded to the end,
and a 32-bit mask follows. SH-4 is little-endian.

Usage:
  ce_dbgzones.py --selftest
  ce_dbgzones.py IMG --image-start 0x200200 [--decoded-dir DIR] [--json]

Compressed ``.data`` sections cannot be read from stored bytes; pass a
directory produced by ``cerom.py IMG decompress --out DIR`` to include them.
Sections without decoded bytes are reported as skipped, never as searched.
Method and results: docs/experiments/EXP-2026-11-24-M8.H15-debug-zones.md
"""

import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cerom

NAME_LEN = 64
VARIANTS = (("32W", 64, 0x440), ("16W", 32, 0x240))
FMT_STR_MIN = 4


def _field_end(d, o, flen):
    """End offset of a printable NUL-terminated, zero-padded UTF-16LE field."""
    if o + 1 >= len(d) or d[o + 1] != 0 or not (0x20 <= d[o] < 0x7F):
        return None
    i = 0
    while i < flen and d[o + i + 1] == 0 and 0x20 <= d[o + i] < 0x7F:
        i += 2
    if i >= flen or i < 2:
        return None
    if d[o + i:o + i + 2] != b"\x00\x00" or any(d[o + i:o + flen]):
        return None
    return i


def scan_zones(d, stride, mask_off):
    """Yield (offset, name, zones, mask) for strict DBGPARAM records."""
    limit = len(d) - NAME_LEN - 16 * stride - 4
    for o in range(0, limit, 2):
        nlen = _field_end(d, o, NAME_LEN)
        if nlen is None:
            continue
        name = d[o:o + nlen].decode("utf-16-le")
        zo = o + NAME_LEN
        zones = []
        ok = True
        for _ in range(16):
            zlen = _field_end(d, zo, stride)
            if zlen is None:
                ok = False
                break
            zones.append(d[zo:zo + zlen].decode("utf-16-le"))
            zo += stride
        if not ok:
            continue
        mo = o + mask_off
        if mo + 4 > len(d):
            continue
        yield o, name, zones, struct.unpack_from("<I", d, mo)[0]


def format_strings(d):
    """Count printable UTF-16LE strings that contain a printf-style '%'."""
    count = 0
    i = 0
    n = len(d)
    while i + 1 < n:
        if d[i + 1] != 0 or not (0x20 <= d[i] < 0x7F):
            i += 1
            continue
        j = i
        while j + 1 < n and d[j + 1] == 0 and 0x20 <= d[j] < 0x7F:
            j += 2
        s = d[i:j].decode("ascii", "replace")
        if len(s) >= FMT_STR_MIN and "%" in s:
            count += 1
        i = j + 2
    return count


def synthetic(offset=0, mask=0x0000FFFF, stride=64, mask_off=0x440,
              corrupt_zone=False):
    """Build a synthetic image containing one DBGPARAM (and trailing room)."""
    d = bytearray(0x1000)

    def putw(buf, o, s):
        for i, ch in enumerate(s):
            struct.pack_into("<H", buf, o + 2 * i, ord(ch))

    putw(d, offset, "NaviMapCC")
    names = ["INIT", "LOAD", "MAP", "ROUTE", "ERR", "WARN", "INFO", "TRACE",
             "DB", "GEO", "RENDER", "CACHE", "GPS", "SEARCH", "DRAW", "MISC"]
    for i, z in enumerate(names):
        putw(d, offset + NAME_LEN + i * stride, z)
    struct.pack_into("<I", d, offset + mask_off, mask)
    if corrupt_zone:
        struct.pack_into("<H", d, offset + NAME_LEN, 0x0001)
    return bytes(d)


def selftest():
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))

    good = synthetic()
    hits = list(scan_zones(good, 64, 0x440))
    check("synthetic 32W DBGPARAM found", len(hits) == 1)
    check("synthetic name decoded", hits and hits[0][1] == "NaviMapCC")
    check("synthetic 16 zones decoded", hits and len(hits[0][2]) == 16)
    check("synthetic mask decoded", hits and hits[0][3] == 0x0000FFFF)
    check("negative: corrupt zone rejected",
          not list(scan_zones(synthetic(corrupt_zone=True), 64, 0x440)))
    check("negative: wrong +0x240 offset reads wrong mask",
          all(h[3] != 0x0000FFFF for h in scan_zones(good, 64, 0x240)))
    check("negative: 16W stride on 32W image misses record",
          not list(scan_zones(good, 32, 0x240)))
    check("format-string counter positive",
          format_strings("a %s and %d".encode("utf-16-le")) >= 1)
    check("format-string counter negative",
          format_strings("plain text".encode("utf-16-le")) == 0)
    bad = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print("  %-4s %s" % ("ok" if ok else "FAIL", name))
    print("selftest: %d/%d checks passed" % (len(checks) - len(bad), len(checks)))
    return 1 if bad else 0


def census(data, start, decoded_dir):
    segments, _ = cerom.find_segments(data, start)
    doc = {"image_start": hex(start), "nummods": segments[0].hdr["nummods"],
           "sections_total": 0, "stored_scanned": 0,
           "compressed_decoded_scanned": 0, "skipped": 0,
           "dbgparam_candidates": [], "format_strings": 0}
    for seg in segments:
        for mod in seg.modules():
            name = mod["name"]
            if not name:
                continue
            for sec in seg.o32(mod):
                doc["sections_total"] += 1
                blob = None
                if sec["flags"] & cerom.IMAGE_SCN_COMPRESSED:
                    if decoded_dir:
                        path = os.path.join(decoded_dir,
                                            "%s.%08x.bin" % (name, sec["rva"]))
                        if os.path.exists(path):
                            blob = open(path, "rb").read()
                            doc["compressed_decoded_scanned"] += 1
                        else:
                            doc["skipped"] += 1
                    else:
                        doc["skipped"] += 1
                else:
                    off = seg.va2file(sec["dataptr"])
                    if off is not None and 0 <= off <= len(data):
                        blob = data[off:off + sec["psize"]]
                        doc["stored_scanned"] += 1
                    else:
                        doc["skipped"] += 1
                if blob is None:
                    continue
                doc["format_strings"] += format_strings(blob)
                if len(blob) < NAME_LEN + 16 * 64 + 4:
                    continue
                for label, stride, mask_off in VARIANTS:
                    for o, nm, zones, mask in scan_zones(blob, stride, mask_off):
                        doc["dbgparam_candidates"].append({
                            "module": name, "section_rva": hex(sec["rva"]),
                            "variant": label, "struct_off": hex(o),
                            "name": nm, "zones": zones, "mask": hex(mask)})
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("image", nargs="?")
    ap.add_argument("--image-start", type=lambda s: int(s, 0), default=0x200200)
    ap.add_argument("--decoded-dir")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.image:
        ap.error("image required (or use --selftest)")
    data = open(args.image, "rb").read(200 * 1024 * 1024)
    doc = census(data, args.image_start, args.decoded_dir)
    if args.json:
        print(json.dumps(doc, indent=2))
    else:
        for key in ("image_start", "nummods", "sections_total", "stored_scanned",
                    "compressed_decoded_scanned", "skipped", "format_strings"):
            print("%s %s" % (key, doc[key]))
        print("dbgparam_candidates %d" % len(doc["dbgparam_candidates"]))
        for c in doc["dbgparam_candidates"]:
            print("  %(module)s %(section_rva)s %(variant)s off=%(struct_off)s "
                  "name=%(name)r mask=%(mask)s" % c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
