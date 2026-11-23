#!/usr/bin/env python3
"""Read a head-unit flash dump (``FMD1:``, 8 MiB) made with LeafSDTools.

The dump is vendor data with personal content (SD PIN, serial, phone book):
it never enters the repository, and this tool never prints the PIN, the
serial or any user record.  It prints offsets, sizes, checksums, labels.

  unitflash.py map DUMP        erase-block table: class, entropy, content
  unitflash.py images DUMP     boot/kernel image headers (``ECEC`` at +0x40)
  unitflash.py prod DUMP       product record, PIN and serial masked
  unitflash.py stores DUMP     SMST stores, ASLG log, VEUP record
  unitflash.py parts DIR       sram/vflash/prod files against the nand file
  unitflash.py --selftest      synthetic flash, no vendor data

``images`` takes ``--offset``/``--length`` so the same scan can run on a slice
of a card image (the negative control of M6.19).

Layout facts and their evidence: docs/hardware/unit-flash.md,
docs/experiments/EXP-2026-11-22-M6.19-unit-flash-map.md.
"""
import argparse
import collections
import glob
import math
import os
import struct
import sys

FLASH_SIZE = 0x800000
SMALL_BLOCKS = 8          # blocks 0..7 are 8 KiB, the rest 64 KiB (C-5193)
BLOCK_COUNT = 0x87
PROD_OFF = 0xA000
PROD_LEN = 0x2D0          # bytes covered by the checksum word at +0x2D0
SRAM = (0x400000, 0x500000)
VFLASH = (0x500000, 0x7E0000)
# nop; nop; mov.l @(4,pc),r0; nop; jmp @r0; nop  (SH-4, little endian)
JUMP = bytes.fromhex("0900090001d009002b400900")
MASKED = ((0x50, 0x10, "serial"), (0x60, 0x10, "SD PIN (unit half)"),
          (0x100, 0x10, "SD PIN (CMD42 password)"))


def blocks():
    off = 0
    for n in range(BLOCK_COUNT):
        size = 0x2000 if n < SMALL_BLOCKS else 0x10000
        yield n, off, size
        off += size


def entropy(buf):
    if not buf:
        return 0.0
    total = len(buf)
    return -sum(c / total * math.log2(c / total)
                for c in collections.Counter(buf).values())


def classify(buf):
    if buf.count(0xFF) == len(buf):
        return "erased"
    if buf.count(0) == len(buf):
        return "zero"
    return "data"


def cstr(buf):
    return buf.split(b"\0", 1)[0].decode("ascii", "replace")


def parse_image(data, off, end=None):
    """Header fields of a boot/kernel image at ``off``, or None."""
    end = len(data) if end is None else end
    if data[off + 0x40:off + 0x44] != b"ECEC" or data[off:off + 12] != JUMP:
        return None
    entry, = struct.unpack_from("<I", data, off + 0x0C)
    cs16, size = struct.unpack_from("<HI", data, off + 0x30)
    ptoc, tocoff = struct.unpack_from("<II", data, off + 0x44)
    img = {"offset": off, "entry": entry, "label": cstr(data[off + 0x20:off + 0x30]),
           "part": cstr(data[off + 0x50:off + 0x60]), "cs16": cs16, "size": size,
           "base": (ptoc - tocoff) & 0xFFFFFFFF, "ptoc": ptoc,
           "verinf": cstr(data[off + 0x60:off + 0x70]),
           "mapdb": struct.unpack_from(">HH", data, off + 0x70), "sum4": None,
           "romhdr": None, "cs16_ok": None}
    if data[off + 0x80:off + 0x84] == b"SUM4":
        img["sum4"] = struct.unpack_from("<II", data, off + 0x84)
    if 0 < size and off + size <= end:
        body = bytearray(data[off:off + size])
        body[0x30:0x32] = b"\0\0"
        img["cs16_ok"] = (sum(body) & 0xFFFF) == cs16
    rh = off + tocoff
    if rh + 0x54 <= len(data):
        w = struct.unpack_from("<21I", data, rh)
        img["romhdr"] = {"dllfirst": w[0], "dlllast": w[1], "physfirst": w[2],
                         "physlast": w[3], "nummods": w[4], "ramstart": w[5],
                         "ramfree": w[6], "ramend": w[7], "numfiles": w[12]}
    return img


def find_images(data, start=0, length=None):
    end = len(data) if length is None else min(len(data), start + length)
    out = []
    pos = data.find(b"ECEC", start, end)
    while pos != -1:
        if pos - 0x40 >= start:
            img = parse_image(data, pos - 0x40, end)
            if img:
                out.append(img)
        pos = data.find(b"ECEC", pos + 1, end)
    return out


def prod_record(data, off=PROD_OFF):
    rec = data[off:off + PROD_LEN + 2]
    stored = rec[PROD_LEN] | rec[PROD_LEN + 1] << 8
    return {"signature": rec[:4], "target_id": rec[0x20:0x24],
            "model": cstr(rec[0x40:0x48].replace(b"\xff", b"\0")),
            "immo_code_blank": rec[0xA0:0xA4] == b"\xff" * 4,
            "immo_flag": rec[0x193], "sum": sum(rec[:PROD_LEN]) & 0xFFFF,
            "stored": stored,
            "masked": [(a, n, name, any(b != 0xFF for b in rec[a:a + n]))
                       for a, n, name in MASKED]}


AREAS = {0x10: "Japan", 0x20: "USA", 0x30: "Euro", 0x40: "Russia", 0x50: "China"}


def smst_stores(data):
    out = []
    for n, off, size in blocks():
        if data[off:off + 4] == b"SMST":
            version, generation, copy = struct.unpack_from("<III", data, off + 4)
            out.append({"block": n, "offset": off, "version": version,
                        "generation": generation, "copy": copy})
    return out


def content_of(data, off, size, images):
    buf = data[off:off + size]
    for img in images:
        if img["offset"] == off:
            return "image %s (%s)" % (img["label"], img["part"])
        if img["offset"] < off < img["offset"] + img["size"]:
            return "… %s" % img["label"]
    for sig, name in ((b"PROD", "product record"), (b"VEUP", "version-up record"),
                      (b"SMST", "SMST store header"), (b"ASLG", "AstLog crash log")):
        if buf[:4] == sig:
            return name
    return ""


def cmd_map(data, args):
    images = find_images(data)
    print("blk  offset     size  class   H     content")
    for n, off, size in blocks():
        buf = data[off:off + size]
        region = ""
        if SRAM[0] <= off < SRAM[1]:
            region = "[SRAM] "
        elif VFLASH[0] <= off < VFLASH[1]:
            region = "[VFlash] "
        print("%02x   0x%06x  %5x  %-6s  %4.2f  %s%s" % (
            n, off, size, classify(buf), entropy(buf), region,
            content_of(data, off, size, images)))
    return 0


def cmd_images(data, args):
    images = find_images(data, args.offset, args.length)
    for img in images:
        rh = img["romhdr"] or {}
        print("0x%08x  %-14s %-12s base=0x%08x entry=0x%08x size=0x%x cs16=0x%04x(%s)" % (
            img["offset"], img["label"], img["part"], img["base"], img["entry"],
            img["size"], img["cs16"],
            {True: "ok", False: "BAD", None: "n/a"}[img["cs16_ok"]]))
        if img["sum4"]:
            print("            SUM4 value=0x%08x size=0x%x" % img["sum4"])
        if img["verinf"] or any(img["mapdb"]):
            print("            +0x60 VerInf=%r  +0x70 map-DB window=%d..%d" % (
                img["verinf"], img["mapdb"][0], img["mapdb"][1]))
        if rh:
            print("            ROMHDR phys=0x%08x..0x%08x mods=%d files=%d "
                  "RAM=0x%08x..0x%08x dll=0x%08x..0x%08x" % (
                      rh["physfirst"], rh["physlast"], rh["nummods"], rh["numfiles"],
                      rh["ramstart"], rh["ramend"], rh["dllfirst"], rh["dlllast"]))
    print("images: %d" % len(images))
    return 0


def cmd_prod(data, args):
    p = prod_record(data)
    tid = p["target_id"]
    print("signature   %r at 0x%x" % (p["signature"], PROD_OFF))
    print("target id   %s  (+0x20; area byte +0x21 = 0x%02x %s)" % (
        tid.hex(" "), tid[1], AREAS.get(tid[1], "other")))
    print("model       %s  (+0x40)" % p["model"])
    for a, n, name, present in p["masked"]:
        print("+0x%03x       %s: %s (masked)" % (a, name, "present" if present else "blank"))
    print("immo code   %s  (+0xA0)" % ("FF FF FF FF" if p["immo_code_blank"] else "set (masked)"))
    print("immo flag   0x%02x  (+0x193)" % p["immo_flag"])
    print("checksum    computed 0x%04x stored 0x%04x %s  (sum of +0x000..+0x2CF, LE at +0x2D0)" % (
        p["sum"], p["stored"], "ok" if p["sum"] == p["stored"] else "BAD"))
    return 0 if p["sum"] == p["stored"] else 1


def cmd_stores(data, args):
    for s in smst_stores(data):
        print("SMST block 0x%02x offset 0x%06x version %d generation 0x%x copy %d" % (
            s["block"], s["offset"], s["version"], s["generation"], s["copy"]))
    for n, off, size in blocks():
        if data[off:off + 4] == b"ASLG":
            w = struct.unpack_from("<5I", data, off + 4)
            print("ASLG block 0x%02x offset 0x%06x version %d capacity 0x%x used 0x%x" % (
                n, off, w[0], w[1], w[3]))
        if data[off:off + 4] == b"VEUP":
            body = data[off + 4:off + size]
            print("VEUP block 0x%02x offset 0x%06x non-erased bytes after the tag: %d" % (
                n, off, len(body) - body.count(0xFF)))
    return 0


def cmd_parts(directory):
    def one(pattern):
        hits = sorted(p for p in glob.glob(os.path.join(directory, pattern))
                      if not p.endswith(".backup"))
        if len(hits) != 1:
            raise SystemExit("expected one %s in %s, found %d" % (pattern, directory, len(hits)))
        with open(hits[0], "rb") as fh:
            return fh.read()
    nand = one("nand_*.bin")
    ok = True
    for name, pattern, (a, b) in (("sram", "sram_*.bin", SRAM), ("vflash", "vflash_*.bin", VFLASH),
                                  ("prod", "prod_*.bin", (PROD_OFF, PROD_OFF + PROD_LEN + 2))):
        part = one(pattern)
        same = part == nand[a:b]
        shifted = part == nand[a + 1:b + 1]
        ok &= same and not shifted
        print("%-6s %8d B == nand[0x%06x:0x%06x] %s (shifted control %s)" % (
            name, len(part), a, b, same, shifted))
    return 0 if ok else 1


def synthetic_flash():
    data = bytearray(b"\xff" * FLASH_SIZE)

    def image(off, label, part, base, body_len, verinf=b"", mapdb=(0, 0)):
        img = bytearray(body_len)
        img[0:12] = JUMP
        struct.pack_into("<I", img, 0x0C, base + 0x100)
        img[0x20:0x20 + len(label)] = label
        img[0x40:0x44] = b"ECEC"
        struct.pack_into("<II", img, 0x44, base + 0x200, 0x200)
        img[0x50:0x50 + len(part)] = part
        img[0x60:0x60 + len(verinf)] = verinf
        struct.pack_into(">HH", img, 0x70, *mapdb)
        struct.pack_into("<21I", img, 0x200, 0x02000000, 0x02000000, base, base + body_len,
                         1, 0x8B0B0000, 0x8B0B1000, 0x8B170000, *([0] * 13))
        for i in range(0x300, body_len):
            img[i] = (i * 7) & 0xFF
        struct.pack_into("<I", img, 0x32, body_len)
        struct.pack_into("<H", img, 0x30, sum(img) & 0xFFFF)
        data[off:off + body_len] = img

    image(0, b"IP10TEST.001", b"470-0000-00", 0xA0000000, 0x1000)
    image(0x40000, b"X110TEST.001", b"470-0000-01", 0x88000000, 0x24000,
          verinf=b"QSD-000-100", mapdb=(16, 16))
    prod = bytearray(b"\xff" * 0x2D2)
    prod[0:4] = b"PROD"
    prod[0x20:0x24] = bytes((0x10, 0x30, 0x02, 0x12))
    prod[0x40:0x48] = b"QY7TEST0"
    prod[0x60:0x64] = b"\x01\x02\x03\x04"
    prod[0x100:0x110] = b"\x01\x02\x03\x04Clarion95321"
    prod[0x193] = 0
    struct.pack_into("<H", prod, PROD_LEN, sum(prod[:PROD_LEN]) & 0xFFFF)
    data[PROD_OFF:PROD_OFF + len(prod)] = prod
    for off, gen, copy in ((0x400000, 5, 1), (0x430000, 4, 2)):
        data[off:off + 0x10000] = bytes(0x10000)
        data[off:off + 16] = b"SMST" + struct.pack("<III", 14, gen, copy)
    data[0x360000:0x360014] = b"ASLG" + struct.pack("<4I", 1, 0x2FFE4, 0, 0x40)
    data[0x3B0000:0x3B0004] = b"VEUP"
    return bytes(data)


def selftest():
    checks = 0

    def check(cond, what):
        nonlocal checks
        checks += 1
        if not cond:
            raise SystemExit("selftest FAIL: %s" % what)

    data = synthetic_flash()
    layout = list(blocks())
    check(len(layout) == 0x87 and layout[5][1] == 0xA000, "block 5 at 0xA000")
    check(layout[8][1] == 0x10000 and layout[0x47][1] == 0x400000, "64 KiB blocks")
    check(layout[-1][1] + layout[-1][2] == FLASH_SIZE, "blocks cover 8 MiB")
    check(layout[0x57][1] == VFLASH[0] and layout[0x85][1] == VFLASH[1], "VFlash blocks")
    images = find_images(data)
    check([i["label"] for i in images] == ["IP10TEST.001", "X110TEST.001"], "two images")
    check(all(i["cs16_ok"] for i in images), "cs16 verifies")
    check(images[1]["base"] == 0x88000000 and images[1]["verinf"] == "QSD-000-100", "X1 header")
    check(images[1]["mapdb"] == (16, 16), "map-DB window big endian")
    check(images[0]["romhdr"]["physfirst"] == 0xA0000000, "ROMHDR physfirst")
    bad = bytearray(data)
    bad[0x40400] ^= 1
    check(find_images(bytes(bad))[1]["cs16_ok"] is False, "flipped byte breaks cs16")
    nojump = bytearray(data)
    nojump[0] = 0
    check(len(find_images(bytes(nojump))) == 1, "ECEC without the jump is not an image")
    check(find_images(data, 0x40000, 0x10000)[0]["cs16_ok"] is None, "truncated slice: cs16 n/a")
    p = prod_record(data)
    check(p["sum"] == p["stored"] and p["target_id"][1] == 0x30, "PROD checksum and area")
    badp = bytearray(data)
    badp[PROD_OFF + 0x21] = 0x20
    q = prod_record(bytes(badp))
    check(q["sum"] != q["stored"], "edited area byte breaks the PROD checksum")
    check([m[3] for m in p["masked"]] == [False, True, True], "masked fields flagged, not printed")
    stores = smst_stores(data)
    check([(s["generation"], s["copy"]) for s in stores] == [(5, 1), (4, 2)], "SMST headers")
    check(classify(data[0x8000:0xA000]) == "erased" and classify(data[0x410000:0x420000]) == "erased",
          "erased class")
    check(classify(bytes(16)) == "zero" and classify(b"\0\1") == "data", "zero/data class")
    check(abs(entropy(bytes(range(256))) - 8.0) < 1e-9 and entropy(b"\0" * 9) == 0.0, "entropy")
    check(content_of(data, 0x50000, 0x10000, images) == "… X110TEST.001", "image continuation")
    check(content_of(data, 0xA000, 0x2000, images) == "product record", "PROD block named")
    print("unitflash selftest: %d checks OK" % checks)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("command", nargs="?", choices=["map", "images", "prod", "stores", "parts"])
    ap.add_argument("path", nargs="?")
    ap.add_argument("--offset", type=lambda s: int(s, 0), default=0,
                    help="images: start of the scanned slice")
    ap.add_argument("--length", type=lambda s: int(s, 0), default=None,
                    help="images: length of the scanned slice")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.command or not args.path:
        ap.error("command and path required")
    if args.command == "parts":
        return cmd_parts(args.path)
    with open(args.path, "rb") as fh:
        if args.command == "images":
            fh.seek(args.offset)
            data = fh.read() if args.length is None else fh.read(args.length)
            args.offset, args.length = 0, None
        else:
            data = fh.read()
            if len(data) != FLASH_SIZE:
                raise SystemExit("expected an 8 MiB dump, got %d bytes" % len(data))
    return {"map": cmd_map, "images": cmd_images, "prod": cmd_prod,
            "stores": cmd_stores}[args.command](data, args)


if __name__ == "__main__":
    sys.exit(main())
