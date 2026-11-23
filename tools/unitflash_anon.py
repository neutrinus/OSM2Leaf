#!/usr/bin/env python3
"""Build a shareable head-unit flash image that holds no data of a real unit.

A real dump (``FMD1:``, 8 MiB, LeafSDTools) holds the SD PIN, the serial, a
phone book, call lists, destinations and position logs.  It never enters the
repository.  This tool does not edit such a dump field by field.  It builds
the user areas from what the firmware itself writes when it boots on an
erased flash, so nothing of the unit's user areas is copied at all:

  1. ``prod``     a product record with a fictitious serial and SD PIN
  2. ``build``    erased flash + that record + the NK1 kernel ("bare" image)
  3.              boot the bare image in ``-M ze0`` and save the two RAM
                  mirrors with the monitor (see docs/emulator/running.md):
                    pmemsave 0x09a40000 0x100000 "mirror.bin"   (VSram)
                    pmemsave 0x09b40000 0x300000 "flm.bin"      (FlashManager)
  4. ``capture``  mirror.bin -> sram.bin (eight ``SMST`` stores with their
                  sums), flm.bin -> vflash.bin
  5. ``build``    erased flash + record + NK1 + sram.bin + vflash.bin
  6. ``scan``     search the result for the private values of a real dump

  unitflash_anon.py prod -o PROD.bin [--from DUMP] [--serial HEX] [--pin HEX]
  unitflash_anon.py capture --mirror M [--flm F] --sram S.bin [--vflash V.bin]
  unitflash_anon.py build -o FLASH.bin            (the committed files)
  unitflash_anon.py build -o BARE.bin --bare [--prod P]
  unitflash_anon.py build -o FLASH.bin --prod P --sram S --vflash V [--nk1 N]
  unitflash_anon.py check FLASH.bin
  unitflash_anon.py scan FLASH.bin --dump REAL_DUMP
  unitflash_anon.py --selftest

``scan`` prints counts and offsets in the anonymous image only; it never
prints a private value.  Layout facts: docs/hardware/unit-flash.md.  Record:
docs/experiments/EXP-2026-11-23-M6.24-anonymous-unit-flash.md.
"""
import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unitflash  # noqa: E402

FLASH_SIZE = unitflash.FLASH_SIZE
PROD_OFF = unitflash.PROD_OFF
PROD_LEN = unitflash.PROD_LEN
NK1_OFF = 1 << 18
SRAM_OFF, SRAM_END = unitflash.SRAM
VFLASH_OFF, VFLASH_END = unitflash.VFLASH
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIT_DIR = os.path.join(REPO, "firmware", "unit-flash")
NK1_DEFAULT = os.path.join(UNIT_DIR, "nk1-QY7200ND.bin")
PROD_DEFAULT_FILE = os.path.join(UNIT_DIR, "prod-anon.bin")
SRAM_DEFAULT_FILE = os.path.join(UNIT_DIR, "sram-anon.bin")
VFLASH_DEFAULT_FILE = os.path.join(UNIT_DIR, "vflash-anon.bin")

# Fictitious values.  The tail of the CMD42 password is a constant of the
# firmware (docs/research/us-eu-region.md), not a secret of one unit.
FAKE_SERIAL = bytes.fromhex("00012345")
FAKE_PIN = bytes.fromhex("12345678")
PIN_TAIL = b"Clarion95321"
SMST_VERSION = 14

# (offset in the RAM mirror, size, flash offset of copy 1, of copy 2).
# The mirror keeps the four areas back to back; the flash keeps each twice.
AREAS = ((0x00000, 0x30000, 0x400000, 0x430000),
         (0x30000, 0x10000, 0x460000, 0x470000),
         (0x40000, 0x10000, 0x480000, 0x490000),
         (0x50000, 0x30000, 0x4A0000, 0x4D0000))
MIRROR_LEN = 0x80000

# Fields of the product record that say nothing about one unit.
PROD_KEEP = ((0x000, 4, "tag"), (0x020, 4, "Target ID"), (0x040, 8, "model"),
             (0x090, 9, "option bytes (meaning unknown)"),
             (0x0A0, 4, "IMMO code (blank)"), (0x0B0, 5, "part-number suffix"),
             (0x140, 2, "prefix of the long serial"),
             (0x180, 4, "flags"), (0x190, 4, "flags"))
PROD_DEFAULT = {0x000: b"PROD", 0x020: bytes.fromhex("10200212"),
                0x040: b"QY7200ND", 0x180: bytes.fromhex("02000100"),
                0x190: bytes.fromhex("02000100")}


def u32sum(buf):
    return sum(struct.unpack("<%dI" % (len(buf) // 4), buf)) & 0xFFFFFFFF


def make_store(payload, size, generation, copy):
    """One ``SMST`` store: header, payload, u32 sum, ``SMED``."""
    if len(payload) != size - 0x30:
        raise ValueError("payload must be %#x bytes" % (size - 0x30))
    out = bytearray(size)
    out[0:16] = b"SMST" + struct.pack("<III", SMST_VERSION, generation, copy)
    out[0x20:size - 0x10] = payload
    struct.pack_into("<I", out, size - 0x10, u32sum(bytes(out[:size - 0x10])))
    out[size - 4:] = b"SMED"
    return bytes(out)


def check_store(buf):
    """None when the store is sound, else the reason."""
    if buf[:4] != b"SMST":
        return "no SMST"
    if buf[-4:] != b"SMED":
        return "no SMED"
    if struct.unpack_from("<I", buf, 4)[0] != SMST_VERSION:
        return "version"
    if struct.unpack_from("<I", buf, len(buf) - 0x10)[0] != u32sum(buf[:-0x10]):
        return "sum"
    return None


def make_prod(source=None, serial=FAKE_SERIAL, pin=FAKE_PIN):
    """A product record.  ``source`` (a real record) gives only PROD_KEEP."""
    rec = bytearray(b"\xff" * (PROD_LEN + 2))
    for off, val in PROD_DEFAULT.items():
        rec[off:off + len(val)] = val
    if source is not None:
        for off, n, _ in PROD_KEEP:
            rec[off:off + n] = source[off:off + n]
    rec[0x50:0x54] = serial
    rec[0x60:0x64] = pin
    rec[0x100:0x110] = pin + PIN_TAIL
    if rec[0x140:0x142] == b"\xff\xff":
        rec[0x140:0x142] = b"\0\0"
    rec[0x142:0x146] = serial
    struct.pack_into("<H", rec, PROD_LEN, sum(rec[:PROD_LEN]) & 0xFFFF)
    return bytes(rec)


def capture_sram(mirror):
    """The 1 MiB ``SRAM`` region from the VSram work mirror."""
    out = bytearray(b"\xff" * (SRAM_END - SRAM_OFF))
    for moff, size, f1, f2 in AREAS:
        payload = mirror[moff + 0x20:moff + size - 0x10]
        out[f1 - SRAM_OFF:f1 - SRAM_OFF + size] = make_store(payload, size, 2, 1)
        out[f2 - SRAM_OFF:f2 - SRAM_OFF + size] = make_store(payload, size, 1, 2)
    return bytes(out)


def capture_vflash(flm):
    return bytes(flm[:VFLASH_END - VFLASH_OFF])


def build(prod, nk1, sram=None, vflash=None):
    img = bytearray(b"\xff" * FLASH_SIZE)
    img[PROD_OFF:PROD_OFF + len(prod)] = prod
    if NK1_OFF + len(nk1) > 0x320000:
        raise ValueError("NK1 image too large")
    img[NK1_OFF:NK1_OFF + len(nk1)] = nk1
    if sram is not None:
        if len(sram) != SRAM_END - SRAM_OFF:
            raise ValueError("sram must be 1 MiB")
        img[SRAM_OFF:SRAM_END] = sram
    if vflash is not None:
        if len(vflash) != VFLASH_END - VFLASH_OFF:
            raise ValueError("vflash must be %#x bytes" % (VFLASH_END - VFLASH_OFF))
        img[VFLASH_OFF:VFLASH_END] = vflash
    return bytes(img)


def check(img):
    """List of problems of an image; empty when it is consistent."""
    bad = []
    if len(img) != FLASH_SIZE:
        return ["size %#x" % len(img)]
    rec = unitflash.prod_record(img)
    if rec["signature"] != b"PROD":
        bad.append("no PROD tag")
    if rec["sum"] != rec["stored"]:
        bad.append("PROD sum")
    kernel = unitflash.parse_image(img, NK1_OFF)
    if not kernel or not kernel["cs16_ok"]:
        bad.append("NK1 header or sum")
    if img[SRAM_OFF:SRAM_END].count(0xFF) != SRAM_END - SRAM_OFF:
        for _, size, f1, f2 in AREAS:
            for off in (f1, f2):
                why = check_store(img[off:off + size])
                if why:
                    bad.append("store %#x: %s" % (off, why))
    return bad


# ---------------------------------------------------------------- scan

STRING_MIN = 6
USER_REGIONS = ((0x360000, 0x390000), (SRAM_OFF, SRAM_END), (VFLASH_OFF, VFLASH_END))


def strings(buf, minimum=STRING_MIN):
    """Set of printable strings: ASCII and both UTF-16 byte orders."""
    out = set()
    n = str(minimum).encode()
    for m in re.finditer(rb"[\x20-\x7e]{" + n + rb",}", buf):
        out.add(m.group().decode())
    for m in re.finditer(rb"(?:[\x20-\x7e]\x00){" + n + rb",}", buf):
        out.add(m.group().decode("utf-16le"))
    for m in re.finditer(rb"(?:\x00[\x20-\x7e]){" + n + rb",}", buf):
        out.add(m.group().decode("utf-16be"))
    return {s.strip() for s in out if len(s.strip()) >= minimum}


def encodings(text):
    return (text.encode("ascii"), text.encode("utf-16le"), text.encode("utf-16be"))


def position_words(buf):
    """Packed COORD001 position words (u32) that occur at least 8 times."""
    count = {}
    for (w,) in struct.iter_unpack("<I", buf[:len(buf) // 4 * 4]):
        lat = ((w >> 16) - 32768) / 192.0
        lon = ((w & 0xFFFF) - 52742) / 128.0
        if 20 <= lat <= 72 and -170 <= lon <= 60 and w >> 16 != w & 0xFFFF:
            count[w] = count.get(w, 0) + 1
    return {w for w, c in count.items() if c >= 8}


def scan(anon, dump):
    """Compare an anonymous image with a real dump.  Returns (rows, failed).

    Each row is (name, hits, detail) where ``detail`` never holds a private
    value: it holds offsets in the anonymous image or counts.
    """
    rows = []
    failed = False
    prod = dump[PROD_OFF:PROD_OFF + PROD_LEN]
    needles = (("serial (PROD +0x50)", prod[0x50:0x54]),
               ("SD PIN unit half (PROD +0x60)", prod[0x60:0x64]),
               ("SD PIN password (PROD +0x100)", prod[0x100:0x110]),
               ("long serial (PROD +0x140)", prod[0x140:0x146]))
    for name, val in needles:
        hits = [m.start() for m in re.finditer(re.escape(val), anon)]
        for form in (val.hex().encode(), val.hex().upper().encode()):
            hits += [m.start() for m in re.finditer(re.escape(form), anon)]
        rows.append((name, len(hits), ", ".join("%#x" % h for h in hits[:8])))
        failed |= bool(hits)
    user = b"".join(dump[a:b] for a, b in USER_REGIONS)
    anon_user = anon[:NK1_OFF] + anon[0x320000:]
    # 1. strings of the dump's user areas that reach the anonymous image
    theirs = strings(user)
    shared = sorted(s for s in theirs
                    if any(e in anon_user for e in encodings(s)))
    rows.append(("strings of the dump's user areas", len(theirs), "in the dump"))
    rows.append(("  of these in the anonymous image", len(shared),
                 "firmware defaults; listed with --list-shared"))
    # 2. digit runs (phone numbers, SIM and device numbers)
    digits = {m.group().decode() for m in re.finditer(rb"[0-9]{7,}", user)}
    for s in theirs:
        digits.update(re.findall(r"[0-9]{7,}", s))
    dshared = sorted(d for d in digits
                     if any(e in anon_user for e in encodings(d)))
    rows.append(("digit runs of 7+ in the dump's user areas", len(digits), "in the dump"))
    rows.append(("  of these in the anonymous image", len(dshared),
                 "firmware defaults; listed with --list-shared"))
    # 3. stored positions
    words = position_words(user)
    whits = sum(anon_user.count(struct.pack("<I", w)) for w in words)
    rows.append(("repeated position words in the dump", len(words), "in the dump"))
    rows.append(("  of these in the anonymous image", whits, ""))
    failed |= bool(whits)
    # 4. raw overlap: 32-byte windows of the dump's user areas
    seen = set()
    for i in range(0, len(user) - 31, 16):
        w = user[i:i + 32]
        if len(set(w)) > 8:
            seen.add(w)
    same = 0
    total = 0
    for i in range(0, len(anon_user) - 31, 16):
        w = anon_user[i:i + 32]
        if len(set(w)) > 8:
            total += 1
            same += w in seen
    rows.append(("non-trivial 32-byte windows of the anonymous user areas", total, ""))
    rows.append(("  of these also in the dump", same,
                 "firmware defaults (the image is built without the dump)"))
    return rows, failed, shared, dshared


# ---------------------------------------------------------------- CLI

def read(path):
    with open(path, "rb") as f:
        return f.read()


def write(path, data):
    with open(path, "wb") as f:
        f.write(data)
    print("%s: %d bytes" % (path, len(data)))


def cmd_prod(a):
    source = None
    if a.source:
        data = read(a.source)
        source = data[PROD_OFF:PROD_OFF + PROD_LEN] if len(data) == FLASH_SIZE else data
        if source[:4] != b"PROD":
            sys.exit("no PROD record in %s" % a.source)
    write(a.output, make_prod(source, bytes.fromhex(a.serial), bytes.fromhex(a.pin)))
    return 0


def cmd_capture(a):
    mirror = read(a.mirror)
    if len(mirror) < MIRROR_LEN:
        sys.exit("mirror must be at least %#x bytes" % MIRROR_LEN)
    for moff, size, _, _ in AREAS[:1] + AREAS[3:]:
        if mirror[moff:moff + 4] != b"SMST":
            sys.exit("no SMST at mirror %#x: saved too early?" % moff)
    write(a.sram, capture_sram(mirror))
    if a.flm:
        write(a.vflash, capture_vflash(read(a.flm)))
    return 0


def cmd_build(a):
    sram, vflash = a.sram, a.vflash
    if not a.bare and not sram and not vflash:
        sram, vflash = SRAM_DEFAULT_FILE, VFLASH_DEFAULT_FILE
    img = build(read(a.prod), read(a.nk1), read(sram) if sram else None,
                read(vflash) if vflash else None)
    bad = check(img)
    if bad:
        sys.exit("inconsistent image: " + "; ".join(bad))
    write(a.output, img)
    return 0


def cmd_check(a):
    bad = check(read(a.image))
    print("\n".join(bad) if bad else "ok: PROD sum, NK1 sum, SMST stores")
    return 1 if bad else 0


def cmd_scan(a):
    rows, failed, shared, dshared = scan(read(a.image), read(a.dump))
    for name, hits, detail in rows:
        print("%-58s %7d  %s" % (name, hits, detail))
    if a.list_shared:
        print("shared strings (also written by the firmware on an erased flash):")
        for s in shared:
            print("  " + s[:70])
        print("shared digit runs:")
        for s in dshared:
            print("  " + s)
    print("RESULT: %s" % ("FAIL" if failed else "PASS"))
    return 1 if failed else 0


def selftest():
    ok = True

    def expect(cond, what):
        nonlocal ok
        print("%s %s" % ("PASS" if cond else "FAIL", what))
        ok &= bool(cond)

    store = make_store(bytes(range(256)) * 255 + bytes(0xD0), 0x10000, 7, 1)
    expect(check_store(store) is None, "store round trip")
    flipped = bytearray(store)
    flipped[0x1234] ^= 1
    expect(check_store(bytes(flipped)) == "sum", "one flipped byte breaks the store sum")
    real = bytearray(make_prod(None, bytes.fromhex("0a0b0c0d"), bytes.fromhex("a1b2c3d4")))
    real[0x90:0x99] = b"OPTIONSXY"
    struct.pack_into("<H", real, PROD_LEN, sum(real[:PROD_LEN]) & 0xFFFF)
    rec = make_prod(bytes(real))
    expect(rec[0x50:0x54] == FAKE_SERIAL and rec[0x60:0x64] == FAKE_PIN
           and rec[0x100:0x110] == FAKE_PIN + PIN_TAIL, "record takes the fictitious values")
    expect(rec[0x90:0x99] == b"OPTIONSXY" and rec[0x20:0x24] == real[0x20:0x24],
           "record keeps the non-unit fields")
    expect(bytes.fromhex("0a0b0c0d") not in rec and bytes.fromhex("a1b2c3d4") not in rec,
           "no source serial or PIN in the record")
    expect(struct.unpack_from("<H", rec, PROD_LEN)[0] == sum(rec[:PROD_LEN]) & 0xFFFF,
           "record sum")
    # a synthetic kernel image with a valid header sum
    nk = bytearray(0x400)
    nk[0:12] = unitflash.JUMP
    nk[0x40:0x44] = b"ECEC"
    struct.pack_into("<I", nk, 0x32, len(nk))
    struct.pack_into("<H", nk, 0x30, sum(nk) & 0xFFFF)
    mirror = bytearray(MIRROR_LEN)
    for moff, size, _, _ in AREAS:
        mirror[moff:moff + 4] = b"SMST"
        mirror[moff + 0x100:moff + 0x108] = b"DEFAULTS"
    sram = capture_sram(bytes(mirror))
    img = build(rec, bytes(nk), sram, b"\0" * (VFLASH_END - VFLASH_OFF))
    expect(check(img) == [], "built image is consistent")
    expect([s["generation"] for s in unitflash.smst_stores(img)] == [2, 1] * 4,
           "eight stores, copy 1 newer")
    # scan: a "real" dump with private strings, against the clean image
    dump = bytearray(img)
    dump[PROD_OFF:PROD_OFF + PROD_LEN + 2] = real
    dump[VFLASH_OFF + 0x100:VFLASH_OFF + 0x10C] = b"+48123456789"
    name = "Jan Kowalski".encode("utf-16le")
    dump[VFLASH_OFF + 0x200:VFLASH_OFF + 0x200 + len(name)] = name
    word = struct.pack("<I", 0xA643D681)
    dump[SRAM_OFF + 0x85000:SRAM_OFF + 0x85000 + 4 * 16] = (word + b"\0\0\0\0") * 8
    rows, failed, shared, dshared = scan(img, bytes(dump))
    expect(not failed and "Jan Kowalski" not in shared and not dshared,
           "scan passes on the clean image")
    leak = bytearray(img)
    leak[VFLASH_OFF + 0x5000:VFLASH_OFF + 0x5004] = bytes.fromhex("a1b2c3d4")
    expect(scan(bytes(leak), bytes(dump))[1], "scan fails on a leaked PIN")
    leak = bytearray(img)
    leak[SRAM_OFF + 0x100:SRAM_OFF + 0x104] = word
    expect(scan(bytes(leak), bytes(dump))[1], "scan fails on a leaked position word")
    leak = bytearray(img)
    leak[VFLASH_OFF + 0x300:VFLASH_OFF + 0x300 + len(name)] = name
    expect("Jan Kowalski" in scan(bytes(leak), bytes(dump))[2],
           "scan lists a leaked name as shared")
    print("selftest: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="command")
    s = sub.add_parser("prod", help="write a product record with fictitious serial and PIN")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--from", dest="source",
                   help="real dump or PROD file: copy the non-unit fields from it")
    s.add_argument("--serial", default=FAKE_SERIAL.hex(), help="4 bytes, hex")
    s.add_argument("--pin", default=FAKE_PIN.hex(), help="4 bytes, hex")
    s = sub.add_parser("capture", help="RAM mirrors of a boot on erased flash -> sram/vflash")
    s.add_argument("--mirror", required=True)
    s.add_argument("--flm")
    s.add_argument("--sram", required=True)
    s.add_argument("--vflash")
    s = sub.add_parser("build", help="assemble the 8 MiB flash image")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--prod", default=PROD_DEFAULT_FILE)
    s.add_argument("--nk1", default=NK1_DEFAULT)
    s.add_argument("--sram", help="default: the committed sram-anon.bin")
    s.add_argument("--vflash", help="default: the committed vflash-anon.bin")
    s.add_argument("--bare", action="store_true",
                   help="erased user areas (the image to boot before 'capture')")
    s = sub.add_parser("check", help="PROD sum, NK1 sum, SMST stores")
    s.add_argument("image")
    s = sub.add_parser("scan", help="search an anonymous image for values of a real dump")
    s.add_argument("image")
    s.add_argument("--dump", required=True)
    s.add_argument("--list-shared", action="store_true",
                   help="print the strings both images hold (review before sharing the output)")
    a = p.parse_args()
    if a.selftest:
        return selftest()
    if not a.command:
        p.error("a command is required")
    if a.command == "capture" and a.flm and not a.vflash:
        p.error("--flm needs --vflash")
    return {"prod": cmd_prod, "capture": cmd_capture, "build": cmd_build,
            "check": cmd_check, "scan": cmd_scan}[a.command](a)


if __name__ == "__main__":
    sys.exit(main())
