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

``verify`` checks the recorded patch addresses (per build) plus each copy's
SUM4 separately; a presence test for "any comparator with the new id" is not
enough, because both cards already contain an unrelated natural
``SK_OTH_SCREEN_UNLOCK`` comparator elsewhere (H69).

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
# The exact image-A literal offsets that `patch` rewrites, per build (NB00
# offsets; NB01 = offset + 0x2000000). Derived from each card's own name tables
# and code (see `find` output / EXP O3); record them so `verify` checks THESE
# addresses, never an arbitrary pre-existing comparator with the new id (H69).
SITE_OFFSETS = {
    "EU 2011": [0x13EBF3E],
    "US 2011": [0x1479A9A, 0x147A1B4],
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


def verify_copy(data, base, old, new, offsets):
    """(ok, verdict, detail) for one image-A copy against the known patch sites.

    H69 fix: check the *exact recorded addresses*, not "any comparator carrying
    the new id" — both cards already contain an unrelated natural comparator
    with the same id, so a presence test passes on an unpatched card.
    """
    n, stored, length = header(data, base)
    computed, _ = sum4(data, base)
    sum_ok = stored == computed
    values = []
    for off in offsets:
        lit = off + (base - COPIES[0])       # NB01 = NB00 offset + 0x2000000
        values.append((lit, u16(data, lit)))
    lit_ok = all(v == new for _, v in values)
    ok = sum_ok and lit_ok
    detail = ("name=%s SUM4 stored=0x%08x computed=0x%08x sites=%s sum_ok=%s"
              % (n, stored, computed,
                 ",".join("0x%x=0x%04x" % (o, v) for o, v in values), sum_ok))
    return ok, ("OK" if ok else "FAIL"), detail


def verify_card(data, offsets=None):
    """Verify both copies; return (all_ok, lines). Pure function for selftest.

    ``offsets`` is the per-build site list; when None it is taken from the
    build detected from the card.  Selftest injects its own synthetic offsets.
    """
    name, idx, old, new = detect(data) if offsets is None else ("TEST", 0, 0x089e, EVENT_UNLOCK)
    if offsets is None:
        offsets = SITE_OFFSETS[name]
    lines = []
    all_ok = True
    for base in COPIES:
        ok, verdict, detail = verify_copy(data, base, old, new, offsets)
        all_ok &= ok
        lines.append("copy 0x%x: %s -> %s" % (base, detail, verdict))
    lines.append("verify: %s" % ("PASS" if all_ok else "FAIL"))
    return all_ok, lines


def cmd_verify(a) -> int:
    data = load_card(a.card)
    ok, lines = verify_card(data)
    for line in lines:
        print(line)
    return 0 if ok else 1


def selftest() -> int:
    """Synthetic NKOK + code bytes only; no vendor data.

    Mirrors the real US card: two consent sites per copy plus an unrelated,
    pre-existing comparator that already carries the unlock id (H69 trap).
    """
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))

    def put_site(card, off, lit_val):
        """Write mov.w @(+4),r3; cmp/eq r3,r5; literal at off."""
        struct.pack_into("<H", card, off, 0x9302)
        struct.pack_into("<H", card, off + 2, CMP_EQ)
        lit = ((off + 4) & ~1) + 2 * 2
        struct.pack_into("<H", card, lit, lit_val)
        return lit

    def build(n_sites=2, natural=False):
        length = 0x240
        card = bytearray(0x2000000 + 0x200 + length)
        lits = {}
        for base in COPIES:
            sites = []
            for i in range(n_sites):
                off = base + NKOK_HEADER + i * 0x20
                sites.append(put_site(card, off, 0x089e))    # SK_SCT_AGREE_CLICK
            natur = None
            if natural:
                natur = put_site(card, base + NKOK_HEADER + 0x100, EVENT_UNLOCK)
            lits[base] = (sites, natur)
            card[base + NKOK_LEN:base + NKOK_LEN + 4] = struct.pack("<I", length)
            card[base + NKOK_TAG:base + NKOK_TAG + 4] = b"SUM4"
            card[base + NKOK_NAME:base + NKOK_NAME + 13] = b"X210NBNI.147\0"
            total, _ = sum4(bytes(card), base)
            struct.pack_into("<I", card, base + NKOK_SUM4, total)
        return card, lits

    def sync_sum(card, base):
        struct.pack_into("<I", card, base + NKOK_SUM4, sum4(bytes(card), base)[0])

    # 1) two-site US-like card with a natural unlock comparator: patch + verify
    card, lits = build(n_sites=2, natural=True)
    for base in COPIES:
        check("two sites found 0x%x" % base,
              len(find_sites(bytes(card), base, 0x089e, EVENT_UNLOCK)), 2)
        for site in find_sites(bytes(card), base, 0x089e, EVENT_UNLOCK):
            struct.pack_into("<H", card, site["lit"], EVENT_UNLOCK)
        sync_sum(card, base)
    ok, lines = verify_card(bytes(card), lits[COPIES[0]][0])
    check("patched 2-site + natural -> PASS", ok, True)

    # 2) H69: fully revert both sites to old id (keep natural comparator),
    #    recompute SUM4 so only the patch is missing -> verify must FAIL.
    reverted = bytearray(card)
    for base in COPIES:
        for lit in lits[base][0]:
            struct.pack_into("<H", reverted, lit, 0x089e)
        sync_sum(reverted, base)
    ok, lines = verify_card(bytes(reverted), lits[COPIES[0]][0])
    check("fully reverted + natural -> FAIL", ok, False)
    check("natural comparator still present",
          len(find_sites(bytes(reverted), COPIES[0], EVENT_UNLOCK, 0x089e)), 1)

    # 3) one of two sites reverted -> FAIL (not just zero sites)
    one = bytearray(card)
    lit0 = lits[COPIES[0]][0][0]
    struct.pack_into("<H", one, lit0, 0x089e)
    sync_sum(one, COPIES[0])
    ok, lines = verify_card(bytes(one), lits[COPIES[0]][0])
    check("one of two sites reverted -> FAIL", ok, False)

    # 4) SUM4 corruption -> FAIL
    bad2 = bytearray(card)
    struct.pack_into("<I", bad2, COPIES[1] + NKOK_SUM4, 0x12345678)
    ok, lines = verify_card(bytes(bad2), lits[COPIES[0]][0])
    check("corrupt SUM4 -> FAIL", ok, False)

    # 5) original old-id scan on an unpatched card still finds exactly the
    #    consent sites (no natural old-id comparator), so patch targeting holds
    card0, _ = build(n_sites=2, natural=False)
    for base in COPIES:
        check("unpatched old-id sites 0x%x" % base,
              len(find_sites(bytes(card0), base, 0x089e, EVENT_UNLOCK)), 2)

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
