#!/usr/bin/env python3
"""Windows CE ROM image (XIP) reader for the ZE0 nav firmware image.

Stdlib only. Reads the CE image embedded in the raw SD-card image (or in the
first ~32 MB of it, e.g. ``dd bs=1M count=32``) and walks ROMHDR, the module
TOC (TOCentry + e32_rom + o32_rom) and the FILESentry table.

The CE image is located by the ``ECEC`` signature at image start + 0x40,
which is followed by pTOC (VA of ROMHDR) and the ROMHDR offset from image
start. See docs/experiments/EXP-2026-11-05-32-ce-romhdr.md.

Usage:
  cerom.py IMG romhdr
  cerom.py IMG modules
  cerom.py IMG files
  cerom.py IMG sections MODULE
  cerom.py IMG va2file VA
  cerom.py IMG file2va OFFSET
  cerom.py IMG extract MODULE -o DIR   # raw o32 sections, uncompressed only
"""
import argparse
import os
import struct
import sys

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

    def module(self, name):
        for m in self.modules():
            if m["name"] and m["name"].lower() == name.lower():
                return m
        raise KeyError(name)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--image-start", type=lambda s: int(s, 0), default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("romhdr")
    sub.add_parser("modules")
    sub.add_parser("files")
    p = sub.add_parser("sections"); p.add_argument("module")
    p = sub.add_parser("va2file"); p.add_argument("va", type=lambda s: int(s, 0))
    p = sub.add_parser("file2va"); p.add_argument("off", type=lambda s: int(s, 0))
    p = sub.add_parser("extract"); p.add_argument("module"); p.add_argument("-o", required=True)
    a = ap.parse_args(argv)

    with open(a.image, "rb") as fh:
        data = fh.read(64 << 20)
    r = CERom(data, a.image_start)

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
