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

Which build a card is
---------------------
The build is chosen from the Clarion **part number** in the NB00 header
(+0x50, e.g. ``470-2824-34`` EU, ``470-2818-33`` US), never from the build
name: the documented EU-on-US workflow (docs/hardware/eu-card-on-us-unit.md)
first rewrites the name at +0x16 to the unit's build, so a name-based choice
patches the *other* market's event ids into a card with a false PASS
(M8.C1p follow-up, H143).  The part number is not touched by that rewrite or
by this patch.  ``--build eu|us`` overrides the detection for a card whose
part number is unknown (a later release, another market); without it an
unknown card is refused instead of guessed.

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
import os
import struct
import sys
from collections import OrderedDict, namedtuple

APP_OFF = 0x200200
COPIES = (0x200000, 0x2000000)       # NB00 / NB01
NKOK_LEN = 0x00
NKOK_NAME = 0x16
NKOK_TAG = 0x30
NKOK_SUM4 = 0x34
NKOK_HEADER = 0x200

# Derived from the card's own name tables and code (NOT from Companion bytes).
# SK_OTH_SCREEN_UNLOCK id = 0x0889 (US) / 0x088f (EU, corrected 2026-11-24); the handler
# compares event id in r5 with a literal loaded by `mov.w @(disp,pc),r3`
# (0x93xx) then `cmp/eq r3,r5` (0x3530).  `find` verifies the whole site and
# refuses ambiguous scans.
CMP_EQ = 0x3530
MOV_W_R3 = 0x93

# NB00 header fields used to tell the cards apart and to report the identity.
NKOK_PART = 0x50
PART_LEN = 12

Build = namedtuple("Build", "label part name agree unlock index")

# Per-build anchors: the Clarion part number identifies the card (the NKOK
# name does not: card_mapcode.py rewrites it for the unit, H143); the state
# table index and the SK_SCT_AGREE_CLICK id are printed for evidence; the site
# is found by its code shape and the expected old id.
BUILDS = OrderedDict((
    # EU ids corrected 2026-11-24 (EXP-2026-11-24-M8.C1p-eu-consent-l4): the
    # EU consent handler (state id 0x263, fn 0x02c21b0c) compares
    # SK_SCT_AGREE_CLICK 0x08a4 and receives SK_OTH_SCREEN_UNLOCK as 0x088f
    # (gdb on -M ze0).  The earlier 0x08a6 -> 0x0891 patched another handler.
    ("eu", Build("EU 2011", "470-2824-34", "X210ECNI.158", 0x08a4, 0x088f, 610)),
    ("us", Build("US 2011", "470-2818-33", "X210NBNI.147", 0x089e, 0x0889, 609)),
))

# Real cards only (image A length -> build label): the literal offsets
# relative to the copy base, from the M8.C1p `find` runs.  `verify` checks
# these exact places, because SK_OTH_SCREEN_UNLOCK is also a literal in other
# handlers and a shape scan for the new id alone passes on a wrong card.
BUILD_LENGTHS = {0x01752c88: "EU 2011", 0x017978e0: "US 2011"}
SITE_OFFSETS = {
    "EU 2011": (0x1236d5a, 0x123748c),
    "US 2011": (0x1279a9a, 0x127a1b4),
}
# Wrong patches of tool versions before 2026-11-24, EU cards only, as
# (offset, original, wrong): US ids on a renamed EU card, and the wrong EU
# ids 0x08a6 -> 0x0891.  `patch` puts them back, `verify` reports them.
MISPATCH = {
    "EU 2011": ((0x1205912, 0x089e, 0x0889), (0x123f2c0, 0x089e, 0x0889),
                (0x11ebf3e, 0x08a6, 0x0891)),
}


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


def card_identity(data: bytes):
    """(build name, part number) from the NB00 NKOK header."""
    name = header(data, COPIES[0])[0]
    raw = data[COPIES[0] + NKOK_PART:COPIES[0] + NKOK_PART + PART_LEN]
    return name, raw.split(b"\0")[0].decode("ascii", "replace").strip()


def detect(data: bytes, build: str = None):
    """(name, state index, old id, new id) of the card's build.

    The part number at NB00 +0x50 decides the build.  The NKOK build name is
    not used: card_mapcode.py rewrites it to the unit's build in the
    documented EU-on-US workflow, and a name-based choice then patches the
    other market's event ids (H143).  A name that differs from the detected
    build's own is reported as the launcher rename.
    """
    name, part = card_identity(data)
    if build:
        b = BUILDS[build]
        how = "--build %s" % build
    else:
        b = next((x for x in BUILDS.values() if x.part == part), None)
        if b is None:
            raise SystemExit(
                "ze0_consent: unknown card part number %r (NKOK name %r); "
                "pass --build eu|us only if the event ids for this card are known"
                % (part, name))
        how = "part %s" % part
    if b.name != name:
        print("note: NKOK name %s is the launcher rename; card build is %s (%s)"
              % (name, b.label, how))
    return b.label, b.index, b.agree, b.unlock


def load_card(path: str):
    import mmap
    f = open(path, "rb")
    return mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)


def cmd_find(a) -> int:
    data = load_card(a.card)
    name, part = card_identity(data)
    label, idx, old, new = detect(data, a.build)
    print("build: %s (part %s, NKOK name %s)  state index %d  "
          "SK_SCT_AGREE_CLICK id 0x%04x -> SK_OTH_SCREEN_UNLOCK 0x%04x"
          % (label, part, name, idx, old, new))
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
    label = BUILD_LENGTHS.get(length)
    for rel, orig, wrong in MISPATCH.get(label, ()):
        if u16(body, rel) == wrong:
            struct.pack_into("<H", body, rel, orig)
            print("repaired copy 0x%x: literal at 0x%x 0x%04x -> 0x%04x (earlier wrong patch)"
                  % (base, base + rel, wrong, orig))
    sites = find_sites(body, 0, old, new)
    want = SITE_OFFSETS.get(label)
    if want and tuple(x["lit"] for x in sites) != want:
        raise SystemExit("ze0_consent: sites %s differ from the expected %s; refusing"
                         % ([hex(x["lit"]) for x in sites], [hex(x) for x in want]))
    for site in sites:
        struct.pack_into("<H", body, site["lit"], new)
    total, _ = sum4(body, 0)
    struct.pack_into("<I", body, NKOK_SUM4, total)
    return sites, bytes(body), total, length


def cmd_patch(a) -> int:
    data = load_card(a.card)
    label, idx, old, new = detect(data, a.build)
    print("build: %s (part %s)  agree 0x%04x -> unlock 0x%04x"
          % (label, card_identity(data)[1], old, new))
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
    label, idx, old, new = detect(data, a.build)
    problems = 0
    for base in COPIES:
        n, stored, length = header(data, base)
        computed, _ = sum4(data, base)
        try:
            sites = find_sites(data, base, new, old)   # new id must now be the literal
            lit_ok = all(u16(data, x["lit"]) == new for x in sites)
        except SystemExit:
            lit_ok = False
        label = BUILD_LENGTHS.get(length)
        if label in SITE_OFFSETS:
            lit_ok = all(u16(data, base + rel) == new for rel in SITE_OFFSETS[label])
        bad = [base + rel for rel, orig, wrong in MISPATCH.get(label, ())
               if u16(data, base + rel) == wrong]
        if bad:
            print("copy 0x%x: WRONG earlier patch at %s; run `patch` again to repair"
                  % (base, ",".join("0x%x" % b for b in bad)))
        ok = stored == computed and lit_ok and not bad
        problems += not ok
        print("copy 0x%x: name=%s SUM4 stored=0x%08x computed=0x%08x agree_id_replaced=%s -> %s"
              % (base, n, stored, computed, lit_ok, "OK" if ok else "FAIL"))
    print("verify: %s" % ("PASS" if problems == 0 else "FAIL (%d copy/copies)" % problems))
    return 0 if problems == 0 else 1


def _synthetic(name: str, part: str, agree_id: int):
    """A small synthetic card: two identical copies, NKOK header + one site."""
    length = 0x240
    card = bytearray(0x2000000 + 0x200 + 0x240)
    lits = {}
    for base in COPIES:
        pc = base + NKOK_HEADER
        struct.pack_into("<H", card, pc, 0x9302)      # mov.w @(+4),r3
        struct.pack_into("<H", card, pc + 2, CMP_EQ)  # cmp/eq r3,r5
        lit = ((pc + 4) & ~1) + 2 * 2                 # absolute literal offset
        struct.pack_into("<H", card, lit, agree_id)
        lits[base] = lit
        card[base + NKOK_LEN:base + NKOK_LEN + 4] = struct.pack("<I", length)
        card[base + NKOK_TAG:base + NKOK_TAG + 4] = b"SUM4"
        card[base + NKOK_NAME:base + NKOK_NAME + len(name)] = name.encode()
        card[base + NKOK_PART:base + NKOK_PART + len(part)] = part.encode()
    for base in COPIES:
        total, _ = sum4(bytes(card), base)
        struct.pack_into("<I", card, base + NKOK_SUM4, total)
    return card, lits


def selftest() -> int:
    """Synthetic NKOK + code bytes only; no vendor data."""
    import contextlib
    import io
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))

    eu, us = BUILDS["eu"], BUILDS["us"]

    # Identity comes from the part number, so a renamed card keeps its ids:
    # the regression behind H143 (card_mapcode.py writes the unit's name first).
    eu_card, _ = _synthetic(eu.name, eu.part, eu.agree)
    check("EU card -> EU ids", detect(bytes(eu_card))[2:], (eu.agree, eu.unlock))
    renamed, lits = _synthetic(us.name, eu.part, eu.agree)
    check("renamed EU card -> EU ids", detect(bytes(renamed))[2:], (eu.agree, eu.unlock))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        detect(bytes(renamed))
    check("rename reported, not acted on", "launcher rename" in buf.getvalue(), True)
    us_card, _ = _synthetic(us.name, us.part, us.agree)
    check("US card -> US ids", detect(bytes(us_card))[2:], (us.agree, us.unlock))
    unknown, _ = _synthetic(us.name, "999-999-99", us.agree)
    try:
        detect(bytes(unknown))
        check("unknown part refused", "accepted", "refused")
    except SystemExit:
        check("unknown part refused", "refused", "refused")
    check("--build override on unknown part", detect(bytes(unknown), "us")[2:],
          (us.agree, us.unlock))

    # Site shape, SUM4 and the patch itself on the renamed EU card.
    for base in COPIES:
        total, ln = sum4(bytes(renamed), base)
        check("synthetic SUM4 0x%x" % base, u32(renamed, base + NKOK_SUM4), total)
        check("synthetic length", ln, 0x240)
        s = find_sites(bytes(renamed), base, eu.agree, eu.unlock)
        check("one EU site 0x%x" % base, len(s), 1)
        check("EU literal 0x%x" % base, s[0]["lit"], lits[base])
    for base in COPIES:
        for site in find_sites(bytes(renamed), base, eu.agree, eu.unlock):
            struct.pack_into("<H", renamed, site["lit"], eu.unlock)
        total, _ = sum4(bytes(renamed), base)
        struct.pack_into("<I", renamed, base + NKOK_SUM4, total)
    for base in COPIES:
        check("patched literal 0x%x" % base, u16(renamed, lits[base]), eu.unlock)
        s = find_sites(bytes(renamed), base, eu.unlock, eu.agree)
        check("patched find 0x%x" % base, len(s), 1)
        check("patched SUM4 0x%x" % base, u32(renamed, base + NKOK_SUM4),
              sum4(bytes(renamed), base)[0])
    check("identity survives the patch", detect(bytes(renamed))[2:], (eu.agree, eu.unlock))

    # negative: mutate a patch byte in one copy -> verifier pattern absent
    bad = bytearray(renamed)
    struct.pack_into("<H", bad, lits[COPIES[0]], eu.agree)
    try:
        find_sites(bytes(bad), COPIES[0], eu.unlock, eu.agree)
        check("mutated site refused", "accepted", "refused")
    except SystemExit:
        check("mutated site refused", "refused", "refused")
    # negative: corrupt stored SUM4 -> computed mismatch
    bad2 = bytearray(renamed)
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
        p.add_argument("--build", choices=sorted(BUILDS),
                       help="force the card build when its part number is unknown")
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
