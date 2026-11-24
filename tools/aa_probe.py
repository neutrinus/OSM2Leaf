#!/usr/bin/env python3
"""M8.G3: static Android-Auto capability probe across four Leaf card images.

For each CE segment (A 0x200200, B 0x3e00200, C 0x5200200) of each image we
print a module census and a needle census. Needles are grouped by hypothesis
(H.264 video decode, USB host/AOA, projection/DirectShow, Wi-Fi, OS/codec).
A positive control (a string present in the image) and a negative control
(a string that must not match) make every count falsifiable.

Outputs a stable JSON document with a per-(image, build, hypothesis) matrix,
so the numbers in an EXP can be quoted from a command, not typed by hand.

Usage:
  python3 tools/aa_probe.py --selftest
  python3 tools/aa_probe.py --out FILE archive/head256.img archive/eu2014-256.img ...
  python3 tools/aa_probe.py --image archive/eu2014-256.img --build A --json

Stdlib only; reuses tools/cerom.py and tools/ce_strfind.py. No vendor bytes
are written: only module names, needles, counts, VAs and file offsets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

import cerom
import ce_strfind

BUILDS = {"A": 0x200200, "B": 0x3e00200, "C": 0x5200200}
READ_LIMIT = 128 << 20
GEN = {
    "head256.img": "ZE0-2011-EU",
    "us256.img": "ZE0-2011-US",
    "eu2014-256.img": "AZE0-2014-EU",
    "eu2016-256.img": "AZE0-2016-EU",
}

# Needles chosen to be *definitive markers*, not substrings: each is a long
# string that would exist only if a real Android Auto / H.264 stack were built
# in. Short tokens (e.g. "VPU", "AVC", "projection") were tried first and
# rejected: they match random compressed bytes (RGVPUJ, NAVConv) and are not
# evidence. Encodings searched: ascii + utf-16le/be.
HYPOTHESES = {
    "h264_decode": [
        "OpenMAX IL", "OMX_Video", "IH264D", "IH264DEC", "H264DEC",
        "avcodec", "libavcodec", "libavformat", "gstreamer", "VideoDecoder",
        "H264 Video", "H.264/AVC", "AVC/H.264", "MPEG-4 AVC", "h264_mp4toannexb",
    ],
    "projection": [
        "AndroidAuto", "Android Auto", "CarPlay", "MirrorLink", "Android Open Accessory",
        "android.accessory", "AOA Protocol", "AOAP", "DirectShow",
        "IGraphBuilder", "IAMVideoControl", "Samsung MirrorLink",
    ],
    "usb_host": [
        "UsbEhci.dll", "EHCI", "usb_device_mode", "USB Disk",
        "UsbConMngCC", "usbmsc.dll", "usbdisk6.dll", "AndroidAccessory",
        "android.hardware.usb.accessory", "UsbAccessory",
    ],
    "wifi": [
        "WLAN", "WiFi", "802.11", "WPA2", "wpa_supplicant", "wireless LAN",
        "SoftAP",
    ],
    "os_codec": [
        "WINCE500", "Windows CE.NET", "Windows CE 5.00", "Video Compression Manager",
        "DirectDraw", "ddraw.dll", "AVIStream", "waveOut",
    ],
}

# Module-name patterns, applied case-insensitively to the TOC names. Excluded
# from "codec" on purpose: AvCCWrapper.dll has only 3 IPC exports and is not a
# video codec (see the EXP).
MODULE_PATTERNS = {
    "h264_decode": ["h264", "vpu", "mpeg", "dshow", "openmax", "avcodec"],
    "projection": ["android", "carplay", "mirror", "projection", "ddraw", "celavi"],
    "usb_host": ["usbohci", "usbehci", "usbcon", "usbmsc", "usbdisk"],
    "wifi": ["wifi", "wlan", "wpa", "80211"],
    "os_codec": ["ddraw", "ddcore", "ddhel", "wavessi", "avccwrap"],
}

# Positive controls: strings that must exist in a valid scan. Real CE images
# all contain the `gwes.exe` module name string; the synthetic ROM used by the
# selftest uses the export name below instead.
POSITIVE_CONTROL = "gwes.exe"
SYNTHETIC_POSITIVE_CONTROL = "MAL_DataVol_getOffset"
# Negative control: a string that must not exist in any image we hold.
NEGATIVE_CONTROL = "THIS_STRING_CANNOT_EXIST_IN_A_LEAF_ROM_7f3a9b21"


def control_check(path, image_start, positive=POSITIVE_CONTROL):
    """Return (positive_hits, negative_hits) for one segment."""
    pos = ce_strfind.scan_image(path, [positive], image_start=image_start,
                                encoding="all", read_limit=READ_LIMIT)
    neg = ce_strfind.scan_image(path, [NEGATIVE_CONTROL], image_start=image_start,
                                encoding="all", read_limit=READ_LIMIT)
    return len(pos["hits"]), len(neg["hits"])


def probe_segment(path, image_start):
    """Return a dict of module + needle counts for one CE segment."""
    with open(path, "rb") as fh:
        data = fh.read(min(os.path.getsize(path), READ_LIMIT))
    rom = cerom.CERom(data, image_start)
    names = [m["name"] for m in rom.modules()]
    needle_hits = {}
    needle_modules = {}
    module_hits = {}
    unsupported_needed = set()
    for hyp, needles in HYPOTHESES.items():
        rep = ce_strfind.scan_image(path, needles, image_start=image_start,
                                    encoding="all", read_limit=READ_LIMIT)
        hits = rep["hits"]
        needle_hits[hyp] = len(hits)
        needle_modules[hyp] = sorted(set(
            "%s:(%s)" % (h["module"], h["context_ascii"][:48]) for h in hits))
        for item in rep["sections"]:
            if item["status"] in ("UNSUPPORTED", "RANGE-ERROR"):
                unsupported_needed.add("%s:%s:%s" % (
                    hyp, item["module"], item["section"]))
        module_hits[hyp] = sorted(set(h["module"] for h in hits))
    matched_modules = {}
    for hyp, patterns in MODULE_PATTERNS.items():
        matched_modules[hyp] = sorted(
            n for n in names if any(p in n.lower() for p in patterns))
    pos, neg = control_check(path, image_start)
    return {
        "image": os.path.basename(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "image_start": "0x%08x" % image_start,
        "modules_searched": len(names),
        "needle_hits": needle_hits,
        "needle_context": needle_modules,
        "needle_modules": module_hits,
        "module_name_matches": matched_modules,
        "positive_control_hits": pos,
        "negative_control_hits": neg,
        "unsupported_sections": sorted(unsupported_needed),
    }


def probe_image(path):
    """Probe all three CE segments of one image."""
    return {
        "generation": GEN.get(os.path.basename(path), "unknown"),
        "segments": {b: probe_segment(path, st) for b, st in BUILDS.items()},
    }


def print_text(doc):
    for gen, image in doc["images"].items():
        first = next(iter(image["segments"].values()))
        print("== %s  %s  sha256 %s" % (gen, image["file"], first["sha256"]))
        for build, seg in image["segments"].items():
            print("  build %s image_start %s modules %d ctrl +%d/-%d" % (
                build, seg["image_start"], seg["modules_searched"],
                seg["positive_control_hits"], seg["negative_control_hits"]))
            for hyp in HYPOTHESES:
                mods = ",".join(seg["needle_modules"][hyp]) or "-"
                print("    %-14s hits=%-4d modules=%s" % (
                    hyp, seg["needle_hits"][hyp], mods))
                ctx = seg.get("needle_context", {}).get(hyp, [])
                for line in ctx[:6]:
                    print("    %-14s   %s" % ("", line))
                names = ",".join(seg["module_name_matches"][hyp]) or "-"
                print("    %-14s named=%s" % ("", names))
            if seg["unsupported_sections"]:
                print("    unsupported: %s" % ",".join(
                    seg["unsupported_sections"][:8]))
    print("-- summary matrix (needle hits; 0 = definitive string absent) --")
    for hyp in HYPOTHESES:
        cells = []
        for image in doc["images"].values():
            for build in sorted(image["segments"]):
                seg = image["segments"][build]
                cells.append("%s/%s=%d" % (
                    image["generation"], build, seg["needle_hits"][hyp]))
        print("  %-14s %s" % (hyp, " ".join(cells)))


def selftest():
    """Prove hit/miss and control behaviour on the synthetic ROM from cerom."""
    import tempfile

    rom_bytes, layout = cerom.build_synthetic_rom()
    start = layout["image_start"]
    with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as fh:
        fh.write(rom_bytes)
        path = fh.name
    try:
        cases = []

        def ok(label, got, want):
            cases.append((label, got == want, got, want))

        pos, neg = control_check(path, start, SYNTHETIC_POSITIVE_CONTROL)
        ok("positive control found", pos > 0, True)
        ok("negative control absent", neg, 0)
        rep = ce_strfind.scan_image(path, ["MAL_DataVol_getOffset"],
                                    image_start=start, encoding="all")
        ok("synthetic hit found", len(rep["hits"]) > 0, True)
        bad = ce_strfind.scan_image(path, [NEGATIVE_CONTROL],
                                    image_start=start, encoding="all")
        ok("synthetic miss", len(bad["hits"]), 0)
    finally:
        os.unlink(path)
    failed = [c for c in cases if not c[1]]
    for label, good, got, want in cases:
        print("%-28s %s" % (label, "OK" if good
                            else "FAIL got=%r want=%r" % (got, want)))
    print("selftest: %s (%d/%d)" % ("OK" if not failed else "FAIL",
                                    len(cases) - len(failed), len(cases)))
    return 0 if not failed else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return selftest()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="*")
    parser.add_argument("--image", action="append", default=[],
                        help="single image to probe (repeatable)")
    parser.add_argument("--build", choices=sorted(BUILDS), default=None,
                        help="only this CE segment (with --image)")
    parser.add_argument("--out", default=None, help="write JSON here")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args(argv)
    images = args.images + args.image
    if not images:
        parser.error("no images given")
    doc = {"images": {}}
    for path in images:
        if not os.path.exists(path):
            print("error: no such image: %s" % path, file=sys.stderr)
            return 2
        if args.image and args.build:
            seg = probe_segment(path, BUILDS[args.build])
            doc["images"][os.path.basename(path)] = {
                "generation": GEN.get(os.path.basename(path), "unknown"),
                "file": path,
                "segments": {args.build: seg},
            }
        else:
            image = probe_image(path)
            image["file"] = path
            doc["images"][os.path.basename(path)] = image
    payload = json.dumps(doc, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    if args.json:
        print(payload)
    else:
        print_text(doc)
    failed = []
    for name, image in doc["images"].items():
        for build, seg in image["segments"].items():
            if seg["positive_control_hits"] == 0:
                failed.append("%s/%s positive control missing" % (name, build))
            if seg["negative_control_hits"] != 0:
                failed.append("%s/%s negative control matched" % (name, build))
    for line in failed:
        print("FAIL: " + line, file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
