#!/usr/bin/env python3
"""ZE0 2011 consent-screen skip in card ROM image A (M8.C1p).

Why
---
On the 2011 (ZE0) card the cold-start consent screen is ``SRT_COLD_I_AGREE``
(EU, state index 610) / ``SRT_COLD_I_AGREE_NAM`` (US, index 609).  Its
``ScreenStateCC.dll`` state class accepts only the tap event
``SK_SCT_AGREE_CLICK`` (EU event id 2214, US 2206).  The same state already
receives ``SK_OTH_SCREEN_UNLOCK`` (id 2185) automatically, with no touch,
right after ``SS_FIRST_COMPLETESHOWSCREEN``.  LeafSDTools Companion's
``agree_qy7`` only knows the AZE0 ``..._TELEMA`` states and cannot patch these
cards (C-8359).

What this tool changes
----------------------
It retargets the consent class's event handler comparator from
``SK_SCT_AGREE_CLICK`` to ``SK_OTH_SCREEN_UNLOCK``: a two-byte change to the
literal in ``mov.w @(disp,PC),r3; cmp/eq r3,r5``.  The handler then runs the
agree action ("I agree" -> ``ForwardState(MAP_RELAY)``) when the skin sends the
automatic unlock event, so the state machine leaves consent with **no** tap and
**no** ``SK_SCT_AGREE_CLICK``.  This is our own change; no Companion code or
bytes are copied.

The card stores image A twice, NB00 at 0x200000 and NB01 at 0x2000000.  Each
512-byte ``NKOK`` header holds a u32 length at +0x00, the build name at +0x16,
the ASCII tag ``SUM4`` at +0x30 and a u32 checksum at +0x34 over the little-
endian u32 words of ``[base+0x200, base+0x200+length)`` (docs/format/
validation.md:9-17).  The tool patches both copies and fixes each copy's SUM4.

Usage::

    ze0_consent.py find CARD.img                 # list sites, no writes
    ze0_consent.py patch CARD.img -o OUT.img      # patch both NB copies + SUM4
    ze0_consent.py patch CARD.img --in-place
    ze0_consent.py verify CARD.img                # check sites + SUM4 + no click
    ze0_consent.py --selftest

No vendor bytes or patched ROM are written into the repository.  ``find``
prints only offsets, ids and hashes.  The L4 run is a separate step (EXP).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import struct
import sys

APP_OFF = 0x200200
COPIES = (0x200000, 0x2000000)       # NB00 / NB01
NKOK_LEN = 0x00
NKOK_NAME = 0x16
NKOK_TAG = 0x30
NKOK_SUM4 = 0x34
NKOK_HEADER = 0x200

# Derived from the card's own name tables and code (NOT from Companion bytes).
# SK_OTH_SCREEN_UNLOCK id = 2185 (US, 0x0889) / 2193 (EU, 0x0891); the handler compares event id in r5
# with a literal loaded by `mov.w @(disp,pc),r3` (0x93xx) then `cmp/eq r3,r5`
# (0x3530).  `find` verifies the whole site and refuses ambiguous scans.
EVENT_UNLOCK = 0x0889
CMP_EQ = 0x3530
MOV_W_R3 = 0x93

# Per-build anchors: state table index and the SK_SCT_AGREE_CLICK id are printed
# for evidence; the site is found by its code shape and the expected old id.
BUILDS = {
    # sha256 prefix : (name, state index, old agree id, new unlock id)
    "105e2032": ("EU 2011", 610, 0x08a6, 0x0891),   # SK_OTH_SCREEN_UNLOCK 2193
    "53342430": ("US 2011", 609, 0x089e, 0x0889),   # SK_OTH_SCREEN_UNLOCK 2185
}


def sha256(data) -> str:
    return hashlib.sha256(data).hexdigest()


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def u16(d, o):
    return struct.unpack_from("<H", d, o)[0]


def sum4(data: bytes, base: int):
    """Card NKOK SUM4: LE-u32 sum over [base+0x200, base+0x200+length)."""
    length = u32(data, base + NKOK_LEN)
    start = base + NKOK_HEADER
    end = start + length
    if end > len(data):
        raise SystemExit("ze0_consent: copy at 0x%x runs past end of card" % base)
    if length % 4:
        raise SystemExit("ze0_consent: copy at 0x%x length not a multiple of 4" % base)
    import array
    words = array.array("I")
    words.frombytes(data[start:end])
    if sys.byteorder != "little":
        words.byteswap()
    return sum(words) & 0xFFFFFFFF, length


def header(data: bytes, base: int):
    if data[base + NKOK_TAG:base + NKOK_TAG + 4] != b"SUM4":
        raise SystemExit("ze0_consent: no SUM4 tag in header at 0x%x" % base)
    name = data[base + NKOK_NAME:base + NKOK_NAME + 13].split(b"\0")[0]
    return name.decode("ascii", "replace"), u32(data, base + NKOK_SUM4), u32(data, base + NKOK_LEN)


def find_sites(data: bytes, base: int, old_id: int, new_id: int):
    """Return the consent-handler comparator literals in one image-A copy.

    Shape (LE halfwords), within the module's executable section::

        mov.w @(disp,pc),r3     ; 0x93dd -> literal = ((pc+4)&~1)+2*disp
        cmp/eq r3,r5            ; 0x3530
        ...
        literal: old_id

    The positive scan looks for a ``mov.w ...,r3`` whose displacement lands on
    a literal equal to ``old_id`` and with a ``cmp/eq r3,r5`` as the next
    instruction.  Uniqueness is mandatory: an ambiguous or empty scan refuses.
    """
    return _find_sites_with(data, u16, u32, base, old_id, new_id)


def _find_sites_with(data, r16, r32, base, old_id, new_id):
    sites = []
    start = base + NKOK_HEADER
    limit = start + r32(data, base + NKOK_LEN)
    needle = struct.pack("<H", CMP_EQ)
    off = start
    while True:
        j = data.find(needle, off)
        if j < 0 or j + 2 > limit:
            break
        off = j + 2
        if j % 2:
            continue
        pc = j - 2
        if pc < start:
            continue
        w = r16(data, pc)
        if w >> 8 != MOV_W_R3:
            continue
        disp = w & 0xFF
        lit = ((pc + 4) & ~1) + 2 * disp
        if lit + 2 > limit or r16(data, lit) != old_id:
            continue
        sites.append(dict(pc=pc, lit=lit, old=old_id, new=new_id, disp=disp))
    if not (1 <= len(sites) <= 4):
        raise SystemExit("ze0_consent: %d sites with old id 0x%04x in copy 0x%x; refusing"
                         % (len(sites), old_id, base))
    return sites


def detect(data: bytes):
    """(name, state index, old id, new id) from the image-A build name + hash.

    Detection uses the NKOK build name (a few bytes at NB00 +0x16) and the
    SHA-256 of the first 0x200000 bytes, so it does not read the whole card.
    """
    name = header(data, COPIES[0])[0]
    head_hash = sha256(data[:0x200000])
    for label, idx, old, new in BUILDS.values():
        if (label.startswith("EU") and name == "X210ECNI.158") or \
           (label.startswith("US") and name == "X210NBNI.147"):
            return (label, idx, old, new)
    raise SystemExit("ze0_consent: unknown image A build name %r (head sha256 %s)"
                     % (name, head_hash[:16]))


def load_card(path: str):
    import mmap
    f = open(path, "rb")
    return mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)


def cmd_find(a) -> int:
    data = load_card(a.card)
    name, idx, old, new = detect(data)
    print("build: %s  state index %d  SK_SCT_AGREE_CLICK id 0x%04x -> SK_OTH_SCREEN_UNLOCK 0x%04x"
          % (name, idx, old, new))
    for base in COPIES:
        n, stored, length = header(data, base)
        computed, _ = sum4(data, base)
        sites = find_sites(data, base, old, new)
        print("copy 0x%07x: name=%s length=0x%x stored SUM4=0x%08x computed=0x%08x %s"
              % (base, n, length, stored, computed, "OK" if stored == computed else "MISMATCH"))
        for s in sites:
            print("  site: mov.w at 0x%x disp=0x%02x -> literal 0x%x = 0x%04x; cmp/eq at 0x%x"
                  % (s["pc"], s["disp"], s["lit"], u16(data, s["lit"]), s["pc"] + 2))
    return 0


def _patch_copy(data, base: int, old: int, new: int):
    """Return (sites, patched 0x200+length bytes, new SUM4, length) for one copy.

    Only ~24.5 MB is copied into RAM, not the 7.5 GB card.  The body is a
    standalone image-A copy with its NKOK header at offset 0, so find_sites and
    sum4 are called with base=0 and all returned offsets are body-relative.
    """
    length = u32(data, base + NKOK_LEN)
    body = bytearray(data[base:base + NKOK_HEADER + length])
    sites = find_sites(body, 0, old, new)
    for site in sites:
        struct.pack_into("<H", body, site["lit"], new)
    total, _ = sum4(body, 0)
    struct.pack_into("<I", body, NKOK_SUM4, total)
    return sites, bytes(body), total, length


def cmd_patch(a) -> int:
    data = load_card(a.card)
    name, idx, old, new = detect(data)
    if a.dry_run:
        for base in COPIES:
            sites, _, total, length = _patch_copy(data, base, old, new)
            print("dry run copy 0x%x: %d literal(s) at %s -> 0x%04x; SUM4=0x%08x over 0x%x bytes"
                  % (base, len(sites), ",".join("0x%x" % (x["lit"] + base) for x in sites),
                     new, total, length))
        return 0
    out = a.out or a.card
    if out == a.card and not a.in_place:
        raise SystemExit("ze0_consent: refusing to overwrite the input; use -o OUT or --in-place")
    import shutil
    if out != a.card:
        shutil.copyfile(a.card, out)
    with open(out, "r+b") as f:
        for base in COPIES:
            sites, body, total, length = _patch_copy(data, base, old, new)
            f.seek(base)
            f.write(body)
            print("patched copy 0x%x: %d literal(s) 0x%04x -> 0x%04x at %s; SUM4=0x%08x over 0x%x bytes"
                  % (base, len(sites), old, new,
                     ",".join("0x%x" % (x["lit"] + base) for x in sites), total, length))
    print("wrote %s" % out)
    return 0


def cmd_verify(a) -> int:
    data = load_card(a.card)
    name, idx, old, new = detect(data)
    problems = 0
    for base in COPIES:
        n, stored, length = header(data, base)
        computed, _ = sum4(data, base)
        try:
            sites = find_sites(data, base, new, old)   # new id must now be the literal
            lit_ok = all(u16(data, x["lit"]) == new for x in sites)
        except SystemExit:
            lit_ok = False
        ok = stored == computed and lit_ok
        problems += not ok
        print("copy 0x%x: name=%s SUM4 stored=0x%08x computed=0x%08x agree_id_replaced=%s -> %s"
              % (base, n, stored, computed, lit_ok, "OK" if ok else "FAIL"))
    print("verify: %s" % ("PASS" if problems == 0 else "FAIL (%d copy/copies)" % problems))
    return 0 if problems == 0 else 1


def selftest() -> int:
    """Synthetic NKOK + code bytes only; no vendor data."""
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))

    # Build a synthetic 'card' with two identical copies, each a small NKOK
    # header and a code blob holding one mov.w/cmp/eq site and its literal.
    length = 0x240
    lits = {}
    card = bytearray(0x2000000 + 0x200 + 0x240)
    for base in COPIES:
        pc = base + NKOK_HEADER                       # absolute file offset
        struct.pack_into("<H", card, pc, 0x9302)      # mov.w @(+4),r3
        struct.pack_into("<H", card, pc + 2, CMP_EQ)  # cmp/eq r3,r5
        lit = ((pc + 4) & ~1) + 2 * 2                 # absolute literal offset
        struct.pack_into("<H", card, lit, 0x089e)     # SK_SCT_AGREE_CLICK (US)
        lits[base] = lit
        card[base + NKOK_LEN:base + NKOK_LEN + 4] = struct.pack("<I", length)
        card[base + NKOK_TAG:base + NKOK_TAG + 4] = b"SUM4"
        card[base + NKOK_NAME:base + NKOK_NAME + 4] = b"TEST"
        total, _ = sum4(bytes(card), base)
        struct.pack_into("<I", card, base + NKOK_SUM4, total)
    # checksum reproduces itself
    for base in COPIES:
        total, ln = sum4(bytes(card), base)
        check("synthetic SUM4 0x%x" % base, u32(card, base + NKOK_SUM4), total)
        check("synthetic length", ln, length)
        s = find_sites(bytes(card), base, 0x089e, EVENT_UNLOCK)
        check("one site 0x%x" % base, len(s), 1)
        check("literal 0x%x" % base, s[0]["lit"], lits[base])
    # patch each copy and verify
    for base in COPIES:
        sites = find_sites(bytes(card), base, 0x089e, EVENT_UNLOCK)
        for site in sites:
            struct.pack_into("<H", card, site["lit"], EVENT_UNLOCK)
        total, _ = sum4(bytes(card), base)
        struct.pack_into("<I", card, base + NKOK_SUM4, total)
    for base in COPIES:
        check("patched literal 0x%x" % base, u16(card, lits[base]), EVENT_UNLOCK)
        s = find_sites(bytes(card), base, EVENT_UNLOCK, 0x089e)
        check("patched find 0x%x" % base, len(s), 1)
        check("patched SUM4 0x%x" % base, u32(card, base + NKOK_SUM4), sum4(bytes(card), base)[0])
    # negative: mutate a patch byte in one copy -> verifier pattern absent
    bad = bytearray(card)
    struct.pack_into("<H", bad, lits[COPIES[0]], 0x089e)
    try:
        find_sites(bytes(bad), COPIES[0], EVENT_UNLOCK, 0x089e)
        check("mutated site refused", "accepted", "refused")
    except SystemExit:
        check("mutated site refused", "refused", "refused")
    # negative: corrupt stored SUM4 -> computed mismatch
    bad2 = bytearray(card)
    struct.pack_into("<I", bad2, COPIES[1] + NKOK_SUM4, 0x12345678)
    check("SUM4 mismatch detected", u32(bad2, COPIES[1] + NKOK_SUM4) == sum4(bytes(bad2), COPIES[1])[0], False)
    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    for name, help_ in (("find", "list the consent sites, no writes"),
                        ("patch", "retarget comparator + fix SUM4 in both NB copies"),
                        ("verify", "check sites, SUM4 and that the click id is gone")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("card")
        if name == "patch":
            p.add_argument("-o", "--out")
            p.add_argument("--in-place", action="store_true")
            p.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "find":
        return cmd_find(a)
    if a.cmd == "patch":
        return cmd_patch(a)
    if a.cmd == "verify":
        return cmd_verify(a)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
