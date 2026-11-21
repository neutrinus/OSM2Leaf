#!/usr/bin/env python3
"""Skins: the TFAT16 skin volume and the `.skn` (AUITK skin) layout (M4.58).

Two sub-commands, both read-only, stdlib only:

  skn_info.py skn FILE [--json]        head of one `.skn`: magic, fixed word,
                                       section markers, object-tree census,
                                       section-3 image assets, trailer tag.
  skn_info.py tfat IMAGE [--offset N]  recursively list the TFAT16 volume that
                                       starts at the end of the FAT32 partition
                                       (default ``0x1c8400400``), with long
                                       names, attributes, cluster chains, sizes.

The `.skn` container is an AUITK skin (``auirtdll.dll`` prints "Only SKN file
format is supported in this version"); its layout is documented in
``docs/format/skins.md`` and the evidence in
``docs/experiments/EXP-2026-11-21-M4.58-skins-tfat16.md`` (C-6500-C-6509).

Record grammar found on five samples (all little-endian):

  header          0x00  u32 `0x04020001`
                  0x04  u32 `0x05006298` (constant on all samples)
                  0x08  u32 declared object count (0x41/0x43 and 0x9029/0xa5c2)
                  0x0c..0x2f  opaque counters/words (see docs)
  sections        each begins with a 4-aligned `u32` tag `0x0402000N`:
                  N=1 at 0x00 (the header itself), N=2 = end of the object
                  tree plus a `u32 count` and `count` `u16` footer values,
                  N=3 = image section (tag, `u32 payload_len`, then
                  `[u32 len][bytes]` assets 4-byte aligned), N=4 = the final
                  4-aligned tag just before the 32-byte trailer.
  object tree     0x30 .. N=2 marker: records `[u24 size][u8 type][payload]`;
                  type 1 carries `u32 flags; u32 namelen; UTF-16LE name`.
  assets          N=3 + 4: `u32 payload_len`, then `[u32 len][bytes]`,
                  padded to 4 bytes.  PNG assets start with `\\x89PNG`.
  trailer         last 32 bytes: 16-byte part number (`470-2826-34`, NUL-padded;
                  placeholder `XxX-yYyY-Zz`), then 16-byte `SKINSK10ECNI.158`.

Exit codes: 0 OK, 2 file/geometry unreadable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zlib

SECTION_TAG = 0x04020000
SECTION_BASE = 0x04020001
FIXED_WORD = 0x05006298
ASSET_MAGIC = b"\x89PNG\r\n\x1a\n"


def u24(d, o):
    return d[o] | (d[o + 1] << 8) | (d[o + 2] << 16)


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def skn_parse(d):
    """Return the header/section/asset summary of one `.skn` byte string."""
    out = {"size": len(d), "sha256": hashlib.sha256(d).hexdigest(),
           "magic": None, "fixed_word": None, "declared_objects": None,
           "header_0c": None, "sections": {}, "objects": {}, "assets": {},
           "section2_footer": None, "trailer": ""}
    if len(d) < 0x30:
        return out
    out["magic"] = u32(d, 0)
    out["fixed_word"] = u32(d, 4)
    out["declared_objects"] = u32(d, 8)
    out["header_0c"] = u32(d, 0xc)
    # locate 4-aligned section markers (a raw search also hits a coincidental
    # tag inside an asset, e.g. sec2/sec4 in the player `.skn`)
    secs = {}
    for n in range(1, 8):
        pat = struct.pack("<I", SECTION_TAG | n)
        i = d.find(pat)
        while i >= 0 and i % 4:
            i = d.find(pat, i + 1)
        if i >= 0:
            secs[n] = i
    out["sections"] = {("sec%d" % n): off for n, off in secs.items()}

    # object-tree census: 0x30 up to the N=2 marker (or first invalid record)
    end = secs.get(2, len(d))
    o = 0x30
    counts = {}
    names = []
    n_obj = 0
    names_ok = True
    while o + 4 <= end:
        sz = u24(d, o)
        typ = d[o + 3]
        if sz < 4 or o + sz > end:
            names_ok = False
            break
        counts[typ] = counts.get(typ, 0) + 1
        if typ == 1 and sz >= 12:
            nl = u32(d, o + 8)
            if 0 < nl <= sz - 12 and not (nl & 1):
                try:
                    names.append(d[o + 12:o + 12 + nl].decode("utf-16-le"))
                except UnicodeDecodeError:
                    pass
        o += sz
        n_obj += 1
    out["objects"] = {"count": n_obj, "types": counts,
                      "names": names, "complete": names_ok,
                      "end": o}

    # section 2: tag, u32 count, then `count` u16 footer values (object index?)
    if 2 in secs:
        s2 = secs[2]
        if s2 + 8 <= len(d):
            cnt = u32(d, s2 + 4)
            foot = [struct.unpack_from("<H", d, s2 + 8 + 2 * k)[0]
                    for k in range(cnt) if s2 + 10 + 2 * k <= len(d)]
            out["section2_footer"] = {"count": cnt, "values": foot}

    # section 3: tag, payload_len, then [u32 len][bytes] assets (4-aligned),
    # bounded by the section-4 tag (or by the 32-byte trailer when the tag is
    # not present)
    if 3 in secs:
        s3 = secs[3]
        payload = u32(d, s3 + 4) if s3 + 8 <= len(d) else 0
        limit = secs.get(4, len(d) - 32)
        o = s3 + 8
        n_asset = 0
        n_png = 0
        n_png_complete = 0
        n_zlib = 0
        n_zlib_ok = 0
        total = 0
        zcat = bytearray()
        while o + 4 <= limit:
            ln = u32(d, o)
            if ln == 0 or o + 4 + ln > len(d):
                break
            blob = d[o + 4:o + 4 + ln]
            if blob[:8] == ASSET_MAGIC:
                n_png += 1
                if blob.rstrip(b"\x00").endswith(b"IEND\xaeB`\x82"):
                    n_png_complete += 1
            elif blob[:2] == b"\x78\x9c":
                n_zlib += 1
                try:
                    zcat += zlib.decompress(blob)
                    n_zlib_ok += 1
                except zlib.error:
                    pass
            n_asset += 1
            total += ln
            o = (o + 4 + ln + 3) & ~3
        declared_end = s3 + 8 + payload
        out["assets"] = {"declared_len": payload, "count": n_asset,
                         "png": n_png, "png_complete": n_png_complete,
                         "zlib": n_zlib, "zlib_ok": n_zlib_ok,
                         "zlib_bytes": len(zcat),
                         "zlib_sha256": hashlib.sha256(bytes(zcat)).hexdigest(),
                         "payload_bytes": total, "end": o,
                         "declared_end": declared_end,
                         "s4_overrun": declared_end - secs[4] if 4 in secs else None}
    # trailer: last 16 bytes (ASCII, may be NUL padded)
    out["trailer"] = d[-16:].rstrip(b"\x00").decode("latin1", "replace")
    if len(d) >= 32:
        out["part_number"] = d[-32:-16].strip(b"\x00").decode("latin1", "replace")
    return out


# --------------------------------------------------------------------------
# TFAT16 volume (FAT12/16 with VFAT long names), read-only
# --------------------------------------------------------------------------

class Fat16:
    def __init__(self, path, offset):
        self.f = open(path, "rb")
        self.off = offset
        self.f.seek(offset)
        boot = self.f.read(512)
        if len(boot) < 512:
            raise ValueError("short TFAT boot sector")
        self.bps = struct.unpack_from("<H", boot, 11)[0]
        self.spc = boot[13]
        res = struct.unpack_from("<H", boot, 14)[0]
        self.nfat = boot[16]
        self.root_ent = struct.unpack_from("<H", boot, 17)[0]
        tot16 = struct.unpack_from("<H", boot, 19)[0]
        tot32 = struct.unpack_from("<I", boot, 32)[0]
        self.fatsz = struct.unpack_from("<H", boot, 22)[0]
        self.fstype = boot[54:62].decode("latin1").rstrip()
        self.oem = boot[3:11].decode("latin1").rstrip()
        self.root_secs = (self.root_ent * 32 + self.bps - 1) // self.bps
        self.data_off = offset + (res + self.nfat * self.fatsz
                                  + self.root_secs) * self.bps
        self.clus = self.bps * self.spc
        self.total = tot16 or tot32
        self.f.seek(offset + res * self.bps)
        self.fat = self.f.read(self.fatsz * self.bps)

    def close(self):
        self.f.close()

    def next(self, c):
        return struct.unpack_from("<H", self.fat, c * 2)[0]

    def chain(self, c):
        out, seen = [], set()
        while 2 <= c < 0xFFF8 and c not in seen:
            seen.add(c)
            out.append(c)
            c = self.next(c)
        return out

    def read(self, c):
        buf = bytearray()
        for x in self.chain(c):
            self.f.seek(self.data_off + (x - 2) * self.clus)
            buf += self.f.read(self.clus)
        return bytes(buf)

    def _raw_dir(self, c):
        if c == 0:
            root_start = self.data_off - self.root_secs * self.bps
            self.f.seek(root_start)
            return self.f.read(self.root_secs * self.bps)
        return self.read(c)

    def listdir(self, c):
        d = self._raw_dir(c)
        out, lfn = [], []
        for i in range(0, len(d), 32):
            e = d[i:i + 32]
            if len(e) < 32 or e[0] == 0:
                break
            if e[0] == 0xE5:
                lfn = []
                continue
            if e[11] == 0x0F:          # VFAT long-name record
                lfn.append(e)
                continue
            base = e[0:8].decode("latin1").rstrip()
            ext = e[8:11].decode("latin1").rstrip()
            short = base + ("." + ext if ext else "")
            if lfn:
                raw = b"".join(lfn_unit(x) for x in reversed(lfn))
                chars = []
                for j in range(0, len(raw), 2):
                    u = raw[j:j + 2]
                    if u == b"\x00\x00":
                        break
                    if u == b"\xff\xff":
                        continue
                    chars.append(u.decode("utf-16-le", "replace"))
                name = "".join(chars)
            else:
                name = short
            lfn = []
            out.append(dict(name=name, short=short, attr=e[11],
                            clus=struct.unpack_from("<H", e, 26)[0],
                            size=struct.unpack_from("<I", e, 28)[0]))
        return out


def lfn_unit(e):
    s = b""
    for a, b in ((1, 11), (14, 26), (28, 32)):
        s += e[a:b]
    return s


def tfat_walk(fat, clus=0, path="", depth=0, out=None):
    out = out if out is not None else []
    for e in fat.listdir(clus):
        if e["name"] in (".", ".."):
            continue
        full = path + "/" + e["name"]
        nchain = len(fat.chain(e["clus"])) if e["clus"] >= 2 else 0
        out.append({"path": full, "attr": e["attr"], "clus": e["clus"],
                    "size": e["size"], "chain": nchain})
        if (e["attr"] & 0x10) and e["clus"] >= 2 and depth < 8:
            tfat_walk(fat, e["clus"], full, depth + 1, out)
    return out


# --------------------------------------------------------------------------
# Self-test (synthetic; no vendor data)
# --------------------------------------------------------------------------

def selftest():
    ok = 0
    fail = 0

    def check(name, cond):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            print("FAIL", name)

    # ---- synthetic .skn: header + 3 records + PNG asset + zlib asset + trailer
    def rec(size, typ, payload=b""):
        body = payload
        sz = 4 + len(body)
        assert sz == size
        return bytes([sz & 0xFF, (sz >> 8) & 0xFF, (sz >> 16) & 0xFF, typ]) + body

    d = bytearray()
    d += struct.pack("<IIIII", 0x04020001, FIXED_WORD, 0x03, 0x08,
                     0x01E00320)               # 0x00..0x13; 0x08 = object count
    d += struct.pack("<IIII", 0x80000087, 0x003EE000, 0xFFFFFFFF,
                     0x00000001)               # 0x14..0x23
    d += b"\x00" * (0x30 - len(d))              # pad to 0x30
    # record type 0 (8 bytes)
    d += rec(8, 0, struct.pack("<I", 0x5001))
    # record type 1 with name "Screen"
    name = "Screen".encode("utf-16-le")
    d += rec(12 + len(name), 1, struct.pack("<II", 2, len(name)) + name)
    # record type 4 (20 bytes)
    d += rec(20, 4, b"\x00" * 16)
    sec2 = len(d)
    d += struct.pack("<II", 0x04020002, 2)      # section 2 marker + 2
    d += struct.pack("<HH", 0x11, 0x22)         # footer values
    sec3 = len(d)
    png = ASSET_MAGIC + b"\x00" * 8 + b"IEND\xaeB`\x82"
    zbuf = b"abcdefgh"
    zblob = zlib.compress(zbuf, 6)
    body = bytearray()
    for blob in (png, zblob):
        body += struct.pack("<I", len(blob)) + blob
        while len(body) % 4:
            body += b"\x00"
    d += struct.pack("<II", 0x04020003, len(body)) + bytes(body)
    # a 4-aligned, non-tag pattern that contains the sec3 tag bytes on an odd
    # offset: the aligned search must skip it (negative control for the find)
    d += b"\x00\x00" + struct.pack("<I", 0x04020003) + b"\x00" * 4
    while len(d) % 4:
        d += b"\x00"
    d += struct.pack("<II", 0x04020004, 0x11223344) + b"\x00" * 20
    d += b"ABC-1234-56" + b"\x00\x00" + b"SKIN" + b"S" + b"K" + b"10" + b"ECN" + b"I.158"
    info = skn_parse(bytes(d))
    check("magic", info["magic"] == 0x04020001)
    check("fixed word", info["fixed_word"] == FIXED_WORD)
    check("declared objects", info["declared_objects"] == 3)
    check("four sections", set(info["sections"]) == {"sec1", "sec2", "sec3", "sec4"})
    check("object count 3", info["objects"]["count"] == 3)
    check("object types", info["objects"]["types"] == {0: 1, 1: 1, 4: 1})
    check("object name", info["objects"]["names"] == ["Screen"])
    check("asset count 2", info["assets"]["count"] == 2)
    check("one PNG", info["assets"]["png"] == 1)
    check("PNG complete", info["assets"]["png_complete"] == 1)
    check("one zlib", info["assets"]["zlib"] == 1)
    check("zlib decompressed", info["assets"]["zlib_ok"] == 1
          and info["assets"]["zlib_bytes"] == len(zbuf))
    check("zlib sha256", info["assets"]["zlib_sha256"]
          == hashlib.sha256(zbuf).hexdigest())
    check("sec3 declared end arithmetic",
          info["assets"]["declared_end"] == sec3 + 8 + info["assets"]["declared_len"]
          and info["assets"]["s4_overrun"] == -12)
    # synthetic declared_len ends 12 B before sec4; on the real cards it ends
    # 12 B past sec4 (s4_overrun=+12)
    check("trailer tag", info["trailer"] == "SKINSK10ECNI.158"
          and info["part_number"] == "ABC-1234-56")
    check("sec2 footer", info["section2_footer"] == {"count": 2,
                                                     "values": [0x11, 0x22]})
    check("header 0x0c", info["header_0c"] == 8)
    check("sec3 bound by sec4 tag", info["sections"]["sec3"] == sec3
          and info["assets"]["count"] == 2)
    # negative: the odd-offset tag copy must not be treated as a section
    check("aligned section markers",
          info["sections"]["sec3"] == sec3 and info["sections"]["sec4"] > sec3)

    # negative: a short buffer is not a skin, no crash, empty summary
    short = skn_parse(b"\x01\x00")
    check("short input size", short["size"] == 2 and short["magic"] is None)

    # asset controls: a good PNG counts as complete, a corrupted IEND is a PNG
    # that is not complete, and a tagless buffer yields no assets at all
    body2 = (struct.pack("<I", len(png)) + png
             + struct.pack("<I", len(png.replace(b"IEND", b"IENX"))) 
             + png.replace(b"IEND", b"IENX"))
    twopng = bytearray(d[:sec3])
    twopng += struct.pack("<II", 0x04020003, len(body2)) + body2
    while len(twopng) % 4:
        twopng += b"\x00"
    twopng += struct.pack("<I", 0x04020004)
    a = skn_parse(bytes(twopng))["assets"]
    check("two PNGs, one complete", a["png"] == 2 and a["png_complete"] == 1)
    noassets = skn_parse(b"\x01\x00\x02\x04" + b"\x00" * 0x40)["assets"]
    check("no section 3 -> no assets", noassets == {})

    # ---- synthetic TFAT16 image: boot sector + 2 FATs + root + one long name
    bps, spc = 512, 1
    root_ent = 512
    root_secs = root_ent * 32 // bps
    fatsz = 1
    res = 1
    tot = res + 2 * fatsz + root_secs + 8
    img = bytearray(tot * bps)
    boot = bytearray(512)
    boot[0:3] = b"\xeb\x3c\x90"
    boot[3:11] = b"MSWIN4.1"
    struct.pack_into("<H", boot, 11, bps)
    boot[13] = spc
    struct.pack_into("<H", boot, 14, res)
    boot[16] = 2
    struct.pack_into("<H", boot, 17, root_ent)
    struct.pack_into("<H", boot, 19, tot)
    struct.pack_into("<H", boot, 22, fatsz)
    boot[54:62] = b"TFAT16  "
    img[0:512] = boot
    fat_off = res * bps
    # data area starts after root; cluster 2 = first data cluster
    data_off = (res + 2 * fatsz + root_secs) * bps
    # allocate cluster 2 for a directory, cluster 3 for a file
    struct.pack_into("<H", img, fat_off + 2 * 2, 0xFFFF)
    struct.pack_into("<H", img, fat_off + 3 * 2, 0xFFFF)
    struct.pack_into("<H", img, fat_off, 0xFFF8)
    struct.pack_into("<H", img, fat_off + 2, 0xFFFF)
    # root: a long-name ".skn" file pointing at cluster 3
    root_off = (res + 2 * fatsz) * bps
    lfn = bytearray(32)
    lfn[0] = 0x41                         # last, sequence 1
    lfn[11] = 0x0F
    nm = "Substance.skn".encode("utf-16-le")
    lfn[1:11] = nm[0:10]
    lfn[14:26] = nm[10:22]
    lfn[28:32] = nm[22:26]
    img[root_off:root_off + 32] = lfn
    ent = bytearray(32)
    ent[0:8] = b"SUBSTA~1"
    ent[8:11] = b"SKN"
    ent[11] = 0x20
    struct.pack_into("<H", ent, 26, 3)
    struct.pack_into("<I", ent, 28, 20)
    img[root_off + 32:root_off + 64] = ent
    img[data_off + 1 * bps:data_off + 1 * bps + 8] = b"\x89PNGtest"
    cio = _BytesIO(bytes(img))
    fat = _Fat16FromBytes(cio).build()
    ents = tfat_walk(fat, 0)
    names = [e["path"] for e in ents]
    check("tfat fstype", fat.fstype == "TFAT16")
    check("tfat long name decoded", "/Substance.skn" in names)
    check("tfat file size", any(e["size"] == 20 for e in ents))

    print("skn_info selftest: %d ok, %d fail" % (ok, fail))
    return 0 if fail == 0 else 1


# Minimal in-memory FAT16 reader for the self-test (same logic as Fat16),
# so the self-test does not need a temp file.
class _BytesIO:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def seek(self, p):
        self.pos = p

    def read(self, n):
        b = self.data[self.pos:self.pos + n]
        self.pos += n
        return b


class _Fat16FromBytes:
    def __init__(self, f):
        self.f = f
        self.off = 0

    def build(self):
        f = self.f
        f.seek(0)
        boot = f.read(512)
        fat = Fat16.__new__(Fat16)
        fat.f = f
        fat.off = 0
        fat.bps = struct.unpack_from("<H", boot, 11)[0]
        fat.spc = boot[13]
        res = struct.unpack_from("<H", boot, 14)[0]
        fat.nfat = boot[16]
        fat.root_ent = struct.unpack_from("<H", boot, 17)[0]
        tot16 = struct.unpack_from("<H", boot, 19)[0]
        tot32 = struct.unpack_from("<I", boot, 32)[0]
        fat.fatsz = struct.unpack_from("<H", boot, 22)[0]
        fat.fstype = boot[54:62].decode("latin1").rstrip()
        fat.oem = boot[3:11].decode("latin1").rstrip()
        fat.root_secs = (fat.root_ent * 32 + fat.bps - 1) // fat.bps
        fat.data_off = (res + fat.nfat * fat.fatsz + fat.root_secs) * fat.bps
        fat.clus = fat.bps * fat.spc
        fat.total = tot16 or tot32
        f.seek(res * fat.bps)
        fat.fat = f.read(fat.fatsz * fat.bps)
        return fat


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="ZE0 skin volume / .skn reader (M4.58)")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("skn")
    a.add_argument("file")
    a.add_argument("--json", action="store_true")
    b = sub.add_parser("tfat")
    b.add_argument("image")
    b.add_argument("--offset", default="0x1c8400400")
    b.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "skn":
        with open(args.file, "rb") as fh:
            info = skn_parse(fh.read())
        if args.json:
            print(json.dumps(info, indent=2))
            return 0
        print("size      %d" % info["size"])
        print("sha256    %s" % info["sha256"])
        print("magic     0x%08x" % (info["magic"] or 0))
        print("fixed     0x%08x" % (info["fixed_word"] or 0))
        print("decl_obj  %d" % (info["declared_objects"] or 0))
        print("hdr_0c    %d" % (info["header_0c"] or 0))
        print("sections  %s" % ", ".join("%s@0x%x" % kv
                                          for kv in info["sections"].items()))
        o = info["objects"]
        print("objects   %d flat (complete=%s) types=%s"
              % (o["count"], o["complete"], dict(sorted(o["types"].items()))))
        if info["declared_objects"] and info["declared_objects"] != o["count"]:
            print("nested    %d (declared - flat)"
                  % (info["declared_objects"] - o["count"]))
        if info["section2_footer"]:
            print("sec2 foot count=%d" % info["section2_footer"]["count"])
        if o["names"]:
            print("names     %d, first: %s" % (len(o["names"]),
                                               ", ".join(o["names"][:8])))
        a3 = info["assets"]
        if a3:
            print("assets    %d (png=%d png_complete=%d zlib=%d ok=%d) "
                  "payload=%d declared=%d"
                  % (a3["count"], a3["png"], a3["png_complete"], a3["zlib"],
                     a3["zlib_ok"], a3["payload_bytes"], a3["declared_len"]))
            print("zlib      %d B sha256=%s"
                  % (a3["zlib_bytes"], a3["zlib_sha256"]))
            if a3.get("s4_overrun") is not None:
                print("sec3_end  0x%x (declared runs %d B past sec4)"
                      % (a3["declared_end"], a3["s4_overrun"]))
        print("trailer   %r" % info["trailer"])
        if info.get("part_number"):
            print("part      %r" % info["part_number"])
        return 0
    if args.cmd == "tfat":
        try:
            fat = Fat16(args.image, int(args.offset, 0))
        except (OSError, ValueError) as exc:
            print("tfat: %s" % exc, file=sys.stderr)
            return 2
        try:
            ents = tfat_walk(fat)
        finally:
            fat.close()
        real = [e for e in ents if not e["path"].rsplit("/", 1)[-1]
                .upper().startswith("DONT_DEL")]
        if args.json:
            print(json.dumps({"fstype": fat.fstype, "bytes_per_cluster":
                              fat.clus, "total_clusters": fat.total,
                              "entries": len(ents), "real": real}, indent=2))
            return 0
        fbytes = sum(e["size"] for e in real if not (e["attr"] & 0x10))
        print("TFAT16 offset=0x%x oem=%s fstype=%s cluster=%dB "
              "sectors=%d volume=%dB" % (int(args.offset, 0), fat.oem,
                                         fat.fstype, fat.clus, fat.total,
                                         fat.total * fat.bps))
        print("entries=%d placeholders=%d real=%d real_bytes=%d"
              % (len(ents), len(ents) - len(real), len(real), fbytes))
        for e in real:
            print("  %-52s attr=0x%02x size=%-10d clusters=%d"
                  % (e["path"], e["attr"], e["size"], e["chain"]))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
