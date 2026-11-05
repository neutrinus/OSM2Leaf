#!/usr/bin/env python3
"""Parse the Clarion/Windows CE ROM segment in a Leaf SD card image."""

import argparse
import hashlib
import json
import os
import struct
import sys

ECEC = b"ECEC"
CPU_SH4 = 0x01A6


class Image:
    def __init__(self, path):
        self.path = path
        self.f = open(path, "rb")
        self.size = os.fstat(self.f.fileno()).st_size

    def read(self, off, n):
        if off < 0 or off + n > self.size:
            return None
        self.f.seek(off)
        return self.f.read(n)

    def u16(self, off):
        b = self.read(off, 2)
        return struct.unpack("<H", b)[0] if b else None

    def u32(self, off):
        b = self.read(off, 4)
        return struct.unpack("<I", b)[0] if b else None

    def close(self):
        self.f.close()


def read_c_string(img, off):
    if off is None or off < 0 or off >= img.size:
        return None
    b = img.read(off, 256)
    if b is None:
        return None
    idx = b.find(b"\x00")
    if idx >= 0:
        b = b[:idx]
    try:
        return b.decode("latin-1")
    except Exception:
        return None


def resolve_romhdr(img, base, pTOC):
    for phys_base in range(0x80000000, 0x90000000, 0x1000):
        c_off = base + pTOC - phys_base
        if c_off < 0 or c_off + 0x60 > img.size:
            continue
        cpu = img.u16(c_off + 0x44)
        if cpu != CPU_SH4:
            continue
        physfirst = img.u32(c_off + 0x08)
        if physfirst != phys_base:
            continue
        nummods = img.u32(c_off + 0x10)
        if nummods is None or not (1 <= nummods <= 5000):
            continue
        physlast = img.u32(c_off + 0x0C)
        if physlast is None or physlast <= physfirst:
            continue
        return c_off, phys_base
    return None


def parse_romhdr(img, c_off, base_file, phys_base):
    def r32(o):
        return img.u32(o)

    def r16(o):
        return img.u16(o)

    def p2f(x):
        return base_file + (x - phys_base)

    off = c_off
    dllfirst = r32(off + 0x00)
    dlllast = r32(off + 0x04)
    physfirst = r32(off + 0x08)
    physlast = r32(off + 0x0C)
    nummods = r32(off + 0x10)
    ul_ram_start = r32(off + 0x14)
    ul_ram_free = r32(off + 0x18)
    ul_ram_end = r32(off + 0x1C)
    ul_copy_entries = r32(off + 0x20)
    ul_copy_offset = r32(off + 0x24)
    ul_profile_len = r32(off + 0x28)
    ul_profile_offset = r32(off + 0x2C)
    numfiles = r32(off + 0x30)
    us_cpu_type = r16(off + 0x44)
    us_misc_flags = r16(off + 0x46)
    p_extensions = r32(off + 0x48)
    ul_tracking_start = r32(off + 0x4C)
    ul_tracking_len = r32(off + 0x50)

    total_entries = nummods + numfiles
    entries = []
    toc_off = off + 0x54
    for idx in range(total_entries):
        e = toc_off + idx * 0x20
        if e + 0x20 > img.size:
            break
        attrs = r32(e + 0x00)
        ft_time = struct.unpack("<Q", img.read(e + 0x04, 8))[0]
        file_size = r32(e + 0x0C)
        name_ptr = r32(e + 0x10)
        e32_off = r32(e + 0x14)
        o32_off = r32(e + 0x18)
        load_off = r32(e + 0x1C)
        name = None
        if 0x80000000 <= name_ptr <= 0x90000000:
            name = read_c_string(img, p2f(name_ptr))
        kind = "module" if idx < nummods else "file"
        entries.append({
            "index": idx,
            "kind": kind,
            "dwFileAttributes": attrs,
            "ftTime": ft_time,
            "nFileSize": file_size,
            "lpszFileName_ptr": name_ptr,
            "name": name,
            "ulE32Offset": e32_off,
            "ulO32Offset": o32_off,
            "ulLoadOffset": load_off,
        })

    modules = [e for e in entries if e["kind"] == "module"]
    files = [e for e in entries if e["kind"] == "file"]

    ext_info = None
    if 0x80000000 <= p_extensions <= 0x90000000:
        eo = p2f(p_extensions)
        if 0 <= eo < img.size:
            words = []
            for k in range(8):
                v = img.u32(eo + k * 4)
                if v is None:
                    break
                words.append(v)
            ext_info = {"offset": eo, "first_dwords": words}

    romhdr = {
        "dllfirst": dllfirst,
        "dlllast": dlllast,
        "physfirst": physfirst,
        "physlast": physlast,
        "nummods": nummods,
        "ulRAMStart": ul_ram_start,
        "ulRAMFree": ul_ram_free,
        "ulRAMEnd": ul_ram_end,
        "ulCopyEntries": ul_copy_entries,
        "ulCopyOffset": ul_copy_offset,
        "ulProfileLen": ul_profile_len,
        "ulProfileOffset": ul_profile_offset,
        "numfiles": numfiles,
        "usCPUType": us_cpu_type,
        "usMiscFlags": us_misc_flags,
        "pExtensions": p_extensions,
        "ulTrackingStart": ul_tracking_start,
        "ulTrackingLen": ul_tracking_len,
        "extensions": ext_info,
    }
    return romhdr, modules, files


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description="Parse Clarion/WinCE ROM segment")
    ap.add_argument("--image", required=True, help="path to raw SD image")
    ap.add_argument("--offset", type=lambda x: int(x, 0), default=0x200200,
                    help="image offset to start scanning for ECEC (default 0x200200)")
    ap.add_argument("--out", help="write JSON report to this path")
    args = ap.parse_args()

    img = Image(args.image)

    # Scan ECEC occurrences once.
    ecec_offsets = []
    pos = 0
    chunk = 4 * 1024 * 1024
    while pos < img.size:
        img.f.seek(pos)
        block = img.f.read(chunk)
        if not block:
            break
        i = 0
        while True:
            j = block.find(ECEC, i)
            if j < 0:
                break
            ecec_offsets.append(pos + j)
            i = j + 1
        pos += len(block)

    ecec_offsets = [o for o in ecec_offsets if o >= args.offset]

    segments = []
    for occ in ecec_offsets:
        base = occ - 0x40
        if base < 0 or base + 0x4C > img.size:
            continue
        pTOC = img.u32(base + 0x44)
        size = img.u32(base + 0x48)
        if (pTOC is None or size is None or
                not (0x80000000 <= pTOC <= 0x90000000) or
                not (0 < size < 0x10000000)):
            continue
        resolved = resolve_romhdr(img, base, pTOC)
        if resolved is None:
            continue
        c_off, phys_base = resolved
        romhdr, modules, files = parse_romhdr(img, c_off, base, phys_base)
        segments.append({
            "segment_base": base,
            "ecec_offset": occ,
            "pTOC": pTOC,
            "size": size,
            "romhdr_offset": c_off,
            "phys_base": phys_base,
            "romhdr": romhdr,
            "modules": modules,
            "files": files,
        })

    img.close()

    report = {
        "image": os.path.abspath(args.image),
        "image_size": os.path.getsize(args.image),
        "image_sha256": sha256_file(args.image),
        "segments": segments,
    }

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            f.write("\n")

    print(f"image: {report['image']}")
    print(f"sha256: {report['image_sha256']}")
    print(f"segments: {len(segments)}")
    for seg in segments:
        rh = seg["romhdr"]
        print(f"--- segment base 0x{seg['segment_base']:x} (ECEC 0x{seg['ecec_offset']:x}) ---")
        print(f"pTOC=0x{seg['pTOC']:x} size=0x{seg['size']:x} romhdr=0x{seg['romhdr_offset']:x} phys_base=0x{seg['phys_base']:x}")
        print(f"nummods={rh['nummods']} numfiles={rh['numfiles']} cpu=0x{rh['usCPUType']:04x} physfirst=0x{rh['physfirst']:x} physlast=0x{rh['physlast']:x} ulCopyEntries={rh['ulCopyEntries']} pExtensions=0x{rh['pExtensions']:x}")
        mod_names = [m["name"] for m in seg["modules"] if m["name"]]
        print(f"modules ({len(mod_names)}): " + " ".join(mod_names))
        file_names = [f["name"] for f in seg["files"] if f["name"]]
        if file_names:
            print(f"files ({len(file_names)}): " + " ".join(file_names))


if __name__ == "__main__":
    main()
