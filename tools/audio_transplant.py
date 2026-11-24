#!/usr/bin/env python3
"""Transplant the US 2011 Audio.exe into the EU 2011 card's image A (M1.59).

Why
---
On a USA unit the EU ``Audio.exe`` cannot open its tuner (``TNR2:`` is
Euro-only in NK1, C-10213) and the equalizer did not react in the car. The
US ``Audio.exe`` opens ``TNR3:``/``TNR4:``, which NK1 starts for USA. Every
DLL it imports is in the EU image with the same names and OBJDLL ordinals
(EXP-2026-11-24-M1.58).

What this tool changes
----------------------
Nothing is moved. The US module (its ``e32``/``o32`` records and its stored
sections, code page-aligned) is appended after the end of the EU image A;
the EU TOC entry ``Audio.exe`` is pointed at it (``e32``, ``o32``, size;
``ulLoadOffset`` kept unless ``--load``); ROMHDR ``physlast``, the NKOK
length and ``SUM4`` are updated; the new image A is written to both copies
(NB00 ``0x200000``, NB01 ``0x2000000``). The old EU ``Audio.exe`` bytes stay
in place, unreferenced. An EXE runs at process base ``0x10000`` in both
builds, so its code needs no relocation. The radio screen control stays the
EU ``RDSCC.dll`` (COM ``RDSCC.RDSCtrl``); whether it talks to the US
``Audio.exe`` is the car test.

Limits it checks: the new length stays at or below the US image A length
(which NK1 is known to load), and the slot before NB01 / ROM B is free.

Usage::

    audio_transplant.py plan EU_CARD US_SRC          # print the plan, no writes
    audio_transplant.py apply EU_CARD US_SRC --in-place
    audio_transplant.py apply EU_CARD US_SRC -o OUT
    audio_transplant.py --selftest

``EU_CARD`` is the whole card image or its first 100 MiB (``curl -r
0-104857599``); ``US_SRC`` needs only the first 100 MiB of the US card.
Composes with ``card_mapcode.py`` (name outside SUM4) and ``ze0_consent.py``
/ ``audio_tnr_patch.py`` (run those on the EU bytes; after this tool the TNR
literal is the US module's). No vendor bytes are committed.
"""
from __future__ import annotations

import argparse
import array
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cerom  # noqa: E402

COPIES = (0x200000, 0x2000000)
HDR = 0x200
NKOK_LEN, NKOK_SUM4, NKOK_TAG = 0x00, 0x34, 0x30
READ = 0x3E00000
E32_SIZE = 112                      # e32_rom incl. padding (TOC spacing)
PAGE = 0x1000
EXEC = 0x20000000
COMPRESSED = 0x2000
MODULE = "Audio.exe"


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def sum4(data, base):
    length = u32(data, base + NKOK_LEN)
    words = array.array("I")
    words.frombytes(bytes(data[base + HDR:base + HDR + length]))
    if sys.byteorder != "little":
        words.byteswap()
    return sum(words) & 0xFFFFFFFF


def toc_entry(rom, name):
    base = rom.hdr_off + cerom.ROMHDR_SIZE
    for m in rom.modules():
        if m["name"].lower() == name.lower():
            return m, base + cerom.TOC_SIZE * m["index"]
    raise SystemExit("audio_transplant: %s not in TOC" % name)


def build(eu: bytes, us: bytes, load=None, name=MODULE):
    """Return (new image A bytes incl. NKOK header, report dict)."""
    for base in COPIES:
        if eu[base + NKOK_TAG:base + NKOK_TAG + 4] != b"SUM4":
            raise SystemExit("audio_transplant: EU copy 0x%x has no SUM4 header" % base)
    L = u32(eu, COPIES[0])
    if eu[COPIES[0]:COPIES[0] + HDR + L] != eu[COPIES[1]:COPIES[1] + HDR + L]:
        raise SystemExit("audio_transplant: EU NB00 and NB01 differ; refusing")
    re_ = cerom.CERom(eu, COPIES[0] + HDR)
    ru = cerom.CERom(us, COPIES[0] + HDR)
    if re_.hdr["physlast"] - re_.hdr["physfirst"] != L:
        raise SystemExit("audio_transplant: EU physlast does not match the NKOK length")
    mu, _ = toc_entry(ru, name)
    me, toc_off = toc_entry(re_, name)
    eu_imports = {(dll.lower(), nm, od) for dll, _s, nm, od in re_.imports(me)}
    us_imports = {(dll.lower(), nm, od) for dll, _s, nm, od in ru.imports(mu)}
    missing = sorted(map(str, us_imports - eu_imports))
    img = bytearray(eu[COPIES[0]:COPIES[0] + HDR + L])
    start = HDR                                         # image byte 0 in `img`
    va0 = re_.hdr["physfirst"]

    def va_of(pos):                                     # pos = index into img
        return va0 + (pos - start)

    def append(blob, align=4):
        pad = (-(va_of(len(img)) - va0)) % align
        img.extend(b"\0" * pad)
        pos = len(img)
        img.extend(blob)
        return va_of(pos)

    secs = []
    for s in ru.o32(mu):
        o = ru.va2file(s["dataptr"])
        blob = bytes(us[o:o + s["psize"]]) if s["psize"] else b""
        align = PAGE if (s["flags"] & EXEC and not s["flags"] & COMPRESSED) else 4
        new_ptr = append(blob, align) if blob else 0
        secs.append(dict(s, dataptr=new_ptr))
    e32_blob = bytes(us[ru.va2file(mu["e32"]):ru.va2file(mu["e32"]) + E32_SIZE])
    e32_va = append(e32_blob, 4)
    o32_va = append(b"".join(struct.pack("<6I", s["vsize"], s["rva"], s["psize"], s["dataptr"],
                                         s["realaddr"], s["flags"]) for s in secs), 4)
    img.extend(b"\0" * ((-(len(img) - start)) % 4))
    newL = len(img) - start
    usL = u32(us, COPIES[0])
    if newL > usL:
        raise SystemExit("audio_transplant: new length 0x%x exceeds the US image A 0x%x" % (newL, usL))
    if COPIES[0] + HDR + newL > COPIES[1] or COPIES[1] + HDR + newL > 0x3E00000:
        raise SystemExit("audio_transplant: new image A does not fit its slot")
    # TOC entry: attrib, ftl, fth, size, name, e32, o32, load
    rel = toc_off - (COPIES[0])                        # TOC offset inside img
    f = list(struct.unpack_from("<8I", img, rel))
    old = dict(size=f[3], e32=f[5], o32=f[6], load=f[7])
    f[3], f[5], f[6] = mu["size"], e32_va, o32_va
    if load is not None:
        f[7] = load
    struct.pack_into("<8I", img, rel, *f)
    # ROMHDR physlast (4th dword)
    hdr_rel = re_.hdr_off - COPIES[0]
    struct.pack_into("<I", img, hdr_rel + 12, va0 + newL)
    struct.pack_into("<I", img, NKOK_LEN, newL)
    tmp = bytearray(img)
    struct.pack_into("<I", img, NKOK_SUM4, sum4(tmp, 0))
    rep = dict(old_len=L, new_len=newL, us_len=usL, toc_old=old,
               toc_new=dict(size=f[3], e32=f[5], o32=f[6], load=f[7]),
               sections=[(hex(s["realaddr"]), s["psize"], hex(s["dataptr"])) for s in secs],
               missing_imports=missing, sum4=u32(img, NKOK_SUM4))
    return bytes(img), rep


def print_plan(rep):
    print("image A length 0x%x -> 0x%x (US image A 0x%x, limit)" % (rep["old_len"], rep["new_len"], rep["us_len"]))
    o, n = rep["toc_old"], rep["toc_new"]
    print("TOC %s: size %d -> %d, e32 0x%08x -> 0x%08x, o32 0x%08x -> 0x%08x, load 0x%08x -> 0x%08x"
          % (MODULE, o["size"], n["size"], o["e32"], n["e32"], o["o32"], n["o32"], o["load"], n["load"]))
    for real, psize, ptr in rep["sections"]:
        print("  section realaddr %s psize %d at %s" % (real, psize, ptr))
    print("imports the EU image lacks: %s" % (", ".join(rep["missing_imports"]) or "none"))
    print("SUM4 0x%08x" % rep["sum4"])


def load_two(eu_path, us_path):
    with open(eu_path, "rb") as fh:
        eu = fh.read(READ)
    with open(us_path, "rb") as fh:
        us = fh.read(READ)
    return eu, us


def cmd_plan(a):
    eu, us = load_two(a.eu, a.us)
    _, rep = build(eu, us, a.load)
    print_plan(rep)
    return 1 if rep["missing_imports"] else 0


def cmd_apply(a):
    if not a.in_place and not a.out:
        raise SystemExit("audio_transplant: give --in-place or -o OUT")
    eu, us = load_two(a.eu, a.us)
    img, rep = build(eu, us, a.load)
    if rep["missing_imports"]:
        raise SystemExit("audio_transplant: imports missing in EU image: %s" % rep["missing_imports"])
    print_plan(rep)
    target = a.eu if a.in_place else a.out
    if not a.in_place:
        shutil.copyfile(a.eu, a.out)
    with open(target, "r+b") as fh:
        for base in COPIES:
            fh.seek(base)
            fh.write(img)
    with open(target, "rb") as fh:
        check = fh.read(READ)
    for base in COPIES:
        if u32(check, base + NKOK_SUM4) != sum4(check, base):
            raise SystemExit("audio_transplant: SUM4 verify failed at 0x%x" % base)
    rom = cerom.CERom(check, COPIES[0] + HDR)
    m, _ = toc_entry(rom, MODULE)
    if m["size"] != rep["toc_new"]["size"]:
        raise SystemExit("audio_transplant: TOC verify failed")
    print("verify: ok (both copies, SUM4, TOC)")
    return 0


def selftest():
    # page alignment helper and SUM4 over a synthetic header
    img = bytearray(HDR + 8)
    struct.pack_into("<I", img, NKOK_LEN, 8)
    img[HDR:HDR + 8] = b"\x01\0\0\0\x02\0\0\0"
    assert sum4(img, 0) == 3
    # refuse when the copies differ
    eu = bytearray(READ)
    for base in COPIES:
        eu[base + NKOK_TAG:base + NKOK_TAG + 4] = b"SUM4"
        struct.pack_into("<I", eu, base, 4)
    eu[COPIES[1] + HDR] = 1
    try:
        build(bytes(eu), bytes(eu))
    except SystemExit as exc:
        assert "differ" in str(exc)
    else:
        raise AssertionError("differing copies must refuse")
    print("selftest ok")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    for nm in ("plan", "apply"):
        q = sub.add_parser(nm)
        q.add_argument("eu")
        q.add_argument("us")
        q.add_argument("--load", type=lambda s: int(s, 0), help="ulLoadOffset for the new entry")
        if nm == "apply":
            q.add_argument("--in-place", action="store_true")
            q.add_argument("-o", "--out")
    a = p.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "plan":
        return cmd_plan(a)
    if a.cmd == "apply":
        return cmd_apply(a)
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
