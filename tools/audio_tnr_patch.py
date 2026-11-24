#!/usr/bin/env python3
"""Point the EU 2011 Audio.exe tuner at a device a USA unit starts (M1.59).

Why
---
The EU 2011 ``Audio.exe`` opens its only tuner device ``TNR2:`` (RDS). The
unit's kernel NK1 starts ``TNR2:`` only for area Euro; a USA unit starts
``TNR3:`` (XM) and ``TNR4:`` (RBDS) instead (C-10212, C-10213). With the EU
card on a USA unit the radio half of ``Audio.exe`` cannot open its tuner,
and the equalizer did not react in the car (EXP-2026-11-24-M1.58).

What this tool changes
----------------------
One UTF-16 character of the literal ``L"TNR2:"`` in ``Audio.exe`` of image A
(``'2'`` -> ``'4'`` by default), in both copies (NB00 at ``0x200000``, NB01
at ``0x2000000``), then each copy's ``SUM4`` (same rule as
``ze0_consent.py``: LE-u32 sum over ``[base+0x200, base+0x200+length)``).
Nothing else. The literal must occur exactly once per copy; otherwise the
tool refuses. Whether the RBDS driver answers the RDS IOCTLs is NOT known:
the open succeeds, the rest is the car test.

Usage::

    audio_tnr_patch.py show CARD.img                  # sites + SUM4, no writes
    audio_tnr_patch.py patch CARD.img --in-place      # TNR2: -> TNR4:
    audio_tnr_patch.py patch CARD.img --in-place --to 1   # TNR1: instead
    audio_tnr_patch.py patch CARD.img --in-place --to 2   # undo
    audio_tnr_patch.py --selftest

Works on the whole card image or on its first 100 MiB. Composes with
``card_mapcode.py`` (build name is outside SUM4) and ``ze0_consent.py``
(SUM4 is recomputed from the bytes). No vendor bytes are committed.
"""
from __future__ import annotations

import argparse
import array
import struct
import sys

COPIES = (0x200000, 0x2000000)      # NB00 / NB01
NKOK_LEN, NKOK_NAME, NKOK_TAG, NKOK_SUM4, NKOK_HEADER = 0x00, 0x16, 0x30, 0x34, 0x200
READ = 0x3E00000                    # both copies of image A end before ROM B


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def literal(n: str) -> bytes:
    return ("TNR%s:" % n).encode("utf-16le") + b"\0\0"


def sum4(data, base):
    length = u32(data, base + NKOK_LEN)
    start = base + NKOK_HEADER
    if length % 4 or start + length > len(data):
        raise SystemExit("audio_tnr_patch: bad NKOK length 0x%x at 0x%x" % (length, base))
    words = array.array("I")
    words.frombytes(bytes(data[start:start + length]))
    if sys.byteorder != "little":
        words.byteswap()
    return sum(words) & 0xFFFFFFFF


def check_header(data, base):
    if bytes(data[base + NKOK_TAG:base + NKOK_TAG + 4]) != b"SUM4":
        raise SystemExit("audio_tnr_patch: no SUM4 tag at 0x%x" % (base + NKOK_TAG))
    return bytes(data[base + NKOK_NAME:base + NKOK_NAME + 13]).split(b"\0")[0].decode("ascii", "replace")


def sites(data, base):
    """Offsets of any ``L"TNRn:"`` (n in 1..4) inside one copy."""
    start, end = base + NKOK_HEADER, base + NKOK_HEADER + u32(data, base + NKOK_LEN)
    out = []
    for n in "1234":
        pat = literal(n)
        i = data.find(pat, start, end)
        while i >= 0:
            out.append((i, n))
            i = data.find(pat, i + 1, end)
    return sorted(out)


def plan(data, to):
    """[(base, site_offset, old_digit)] or SystemExit when not exactly one site per copy."""
    out = []
    for base in COPIES:
        check_header(data, base)
        s = sites(data, base)
        if len(s) != 1:
            raise SystemExit("audio_tnr_patch: copy 0x%x has %d TNR literals (%s); refusing"
                             % (base, len(s), ", ".join("0x%x=TNR%s" % x for x in s) or "none"))
        out.append((base, s[0][0], s[0][1]))
    return out


def apply(data: bytearray, to: str):
    rows = []
    for base, off, old in plan(data, to):
        data[off + 6:off + 8] = to.encode("utf-16le")      # 'T','N','R' = 6 bytes, then the digit
        new = sum4(data, base)
        struct.pack_into("<I", data, base + NKOK_SUM4, new)
        rows.append((base, off, old, new))
    return rows


def cmd_show(path):
    with open(path, "rb") as fh:
        data = fh.read(READ)
    ok = True
    for base in COPIES:
        name = check_header(data, base)
        stored, computed = u32(data, base + NKOK_SUM4), sum4(data, base)
        s = sites(data, base)
        good = stored == computed
        ok &= good and len(s) == 1
        print("copy 0x%07x %s: SUM4 stored 0x%08x computed 0x%08x %s; tuner literal %s"
              % (base, name, stored, computed, "ok" if good else "MISMATCH",
                 ", ".join("TNR%s: at 0x%x" % (n, o) for o, n in s) or "none"))
    return 0 if ok else 1


def cmd_patch(path, to, in_place, out):
    if not in_place and not out:
        raise SystemExit("audio_tnr_patch: give --in-place or -o OUT")
    with open(path, "rb") as fh:
        data = bytearray(fh.read(READ))
    rows = apply(data, to)
    target = path if in_place else out
    if not in_place:
        import shutil
        shutil.copyfile(path, out)
    with open(target, "r+b") as fh:
        for base, off, old, new in rows:
            fh.seek(off + 6)
            fh.write(bytes(data[off + 6:off + 8]))
            fh.seek(base + NKOK_SUM4)
            fh.write(struct.pack("<I", new))
            print("copy 0x%07x: TNR%s: -> TNR%s: at 0x%x; SUM4 -> 0x%08x" % (base, old, to, off, new))
    with open(target, "rb") as fh:
        check = fh.read(READ)
    for base in COPIES:
        if u32(check, base + NKOK_SUM4) != sum4(check, base):
            raise SystemExit("audio_tnr_patch: verify failed at 0x%x" % base)
    print("verify: ok")
    return 0


def selftest():
    data = bytearray(READ)
    for base in COPIES:
        length = 0x1000
        struct.pack_into("<I", data, base + NKOK_LEN, length)
        data[base + NKOK_NAME:base + NKOK_NAME + 12] = b"X210ECNI.158"
        data[base + NKOK_TAG:base + NKOK_TAG + 4] = b"SUM4"
        data[base + 0x400:base + 0x400 + 12] = literal("2")
        data[base + 0x800:base + 0x804] = b"\x11\x22\x33\x44"
        struct.pack_into("<I", data, base + NKOK_SUM4, sum4(data, base))
    rows = apply(data, "4")
    assert [(b, o, old) for b, o, old, _ in rows] == [(0x200000, 0x200400, "2"), (0x2000000, 0x2000400, "2")]
    for base in COPIES:
        assert bytes(data[base + 0x400:base + 0x40c]) == literal("4")
        assert u32(data, base + NKOK_SUM4) == sum4(data, base)
    apply(data, "2")                                # undo restores the literal
    assert bytes(data[0x200400:0x20040c]) == literal("2")
    # negative: a second literal in one copy refuses
    data[0x200600:0x20060c] = literal("3")
    try:
        apply(data, "4")
    except SystemExit as exc:
        assert "refusing" in str(exc)
    else:
        raise AssertionError("two literals must refuse")
    print("selftest ok")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("show")
    s.add_argument("card")
    q = sub.add_parser("patch")
    q.add_argument("card")
    q.add_argument("--to", default="4", choices="1234")
    q.add_argument("--in-place", action="store_true")
    q.add_argument("-o", "--out")
    a = p.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "show":
        return cmd_show(a.card)
    if a.cmd == "patch":
        return cmd_patch(a.card, a.to, a.in_place, a.out)
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
