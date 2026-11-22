#!/usr/bin/env python3
"""Show or change the map code a card gives the unit's launcher (M8.C1m).

The launcher compares the unit's map code (``VerInf``, the running kernel
image's header ``+0x60``; NK1 in the unit's flash) with the card's
(``HddInf``, line 1 of ``VER_INFO/HDD_INFO.TXT`` in the map partition).  A
mismatch is ``AppLch >> Error Proc<00000050>`` and FailSafe, the
``DIFFERENT MAP CODE`` path (EXP-2026-11-22-M8.C1m-unit-flash-region,
C-8354, C-8356).  This tool rewrites line 1 of that file in place through
``imgpatch.py``, so only the file's cluster changes.  By default it also
updates the 72-byte raw copy at ``0x06000000``, which the launcher does not
read but which other checks may.

Commands::

    card_mapcode.py show --image CARD.img
    card_mapcode.py unit --nk1 firmware/unit-flash/nk1-QY7200ND.bin
    card_mapcode.py unit --nk1 NAND_DUMP.bin            # NK1 at +0x40000
    card_mapcode.py set  --image CARD.img --code QSD-301-100 -o OUT.img
    card_mapcode.py set  --image CARD.img --from-nk1 NK1_OR_NAND --in-place
    card_mapcode.py --selftest

``set`` writes either a full copy (``-o``; about 7.5 GB for a factory card)
or the given image itself (``--in-place``; work on a copy you made with
``dd``).  The new code must be as long as the old one (11 characters), so
the file keeps its size.  ``--dry-run`` shows the plan and writes nothing.
The tool never reads or writes the SD lock password, and it holds no
vendor bytes.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import imgpatch  # noqa: E402

VERSION_FILE = imgpatch.VERSION_FILE
NK1_IN_NAND = 0x40000
HDR_MAPCODE = 0x60
HDR_MAPDB = 0x70
CODE_RE = re.compile(rb"^[A-Z0-9]{3}-[0-9]{3}-[0-9]{3}$")


def read_card(image: str) -> tuple[bytes, bytes]:
    """HDD_INFO.TXT through the FAT, and the 72-byte raw copy."""
    import cardcheck
    img = cardcheck.Fat32Image(Path(image))
    try:
        data = img.read(VERSION_FILE)
        raw = img.read_absolute(imgpatch.HDD_COPY_OFFSET, imgpatch.HDD_COPY_LEN)
    finally:
        img.close()
    return data, raw


def card_code(data: bytes) -> bytes:
    return data.split(b"\r\n", 1)[0]


def unit_record(path: str) -> dict:
    """Map code and map-DB window from NK1's header (NK1 file or NAND dump)."""
    with open(path, "rb") as f:
        head = f.read(NK1_IN_NAND + 0x80)
    # a NAND dump also has small boot images (ECEC) at 0; NK1 is at 0x40000
    for base in (NK1_IN_NAND, 0):
        if head[base + 0x40:base + 0x44] == b"ECEC":
            hdr = head[base:base + 0x80]
            code = hdr[HDR_MAPCODE:HDR_MAPCODE + 16].split(b"\0", 1)[0]
            lo = int.from_bytes(hdr[HDR_MAPDB:HDR_MAPDB + 2], "big")
            hi = int.from_bytes(hdr[HDR_MAPDB + 2:HDR_MAPDB + 4], "big")
            return {"nk1_offset": base, "code": code.decode("ascii", "replace"),
                    "mapdb": (lo, hi)}
    raise SystemExit("card_mapcode: %s: no NK1 header (ECEC at +0x40 or +0x40040)" % path)


def new_file(data: bytes, code: str) -> bytes:
    old = card_code(data)
    new = code.encode("ascii")
    if not CODE_RE.match(new):
        raise SystemExit("card_mapcode: %r does not look like a map code (QSD-301-100)" % code)
    if len(new) != len(old):
        raise SystemExit("card_mapcode: new code %r has %d characters, the card's %r has %d"
                         % (code, len(new), old.decode(), len(old)))
    return new + data[len(old):]


def cmd_show(a) -> int:
    data, raw = read_card(a.image)
    print("%s: %s" % (VERSION_FILE, " | ".join(x.decode("ascii", "replace")
                                                for x in data.split(b"\r\n"))))
    print("map code (HddInf, launcher): %s" % card_code(data).decode())
    same = raw == data
    print("raw copy at 0x%08x: %s" % (imgpatch.HDD_COPY_OFFSET,
                                      "same as the file" if same else
                                      "differs: " + card_code(raw).decode("ascii", "replace")))
    return 0


def cmd_unit(a) -> int:
    r = unit_record(a.nk1)
    print("NK1 at +0x%x: map code (VerInf) %s, map DB window %d-%d"
          % (r["nk1_offset"], r["code"], r["mapdb"][0], r["mapdb"][1]))
    return 0


def cmd_set(a) -> int:
    if bool(a.out) == bool(a.in_place) and not a.dry_run:
        raise SystemExit("card_mapcode: give -o OUT.img or --in-place")
    code = a.code or unit_record(a.from_nk1)["code"]
    data, raw = read_card(a.image)
    old = card_code(data).decode()
    if old == code:
        print("card already has map code %s; nothing to do" % code)
        return 0
    newdata = new_file(data, code)
    copy = not a.file_only
    if copy and len(newdata) != imgpatch.HDD_COPY_LEN:
        raise SystemExit("card_mapcode: %s is %d bytes, not %d; use --file-only"
                         % (VERSION_FILE, len(newdata), imgpatch.HDD_COPY_LEN))
    with tempfile.NamedTemporaryFile(prefix="hdd_info_", suffix=".txt", delete=False) as t:
        t.write(newdata)
        src = t.name
    try:
        rep = imgpatch.patch_image(a.image, VERSION_FILE, src,
                                   None if a.in_place else a.out,
                                   dry_run=a.dry_run, update_version_copy=copy)
        target = rep["target"]
        print("%s %s: map code %s -> %s (%s)" % (
            "planned" if a.dry_run else "patched", target, old, code,
            "file and raw copy" if copy else "file only"))
        if not a.dry_run:
            v = imgpatch.verify_image(target, VERSION_FILE, src, update_version_copy=copy)
            print("verify: %s" % ("ok" if v["ok"] else "MISMATCH"))
            if not v["ok"]:
                return 1
    except imgpatch.PatchError as e:
        print("card_mapcode: refused (%s): %s" % (e.reason, e.message), file=sys.stderr)
        return e.exit_code
    finally:
        os.unlink(src)
    return 0


def selftest() -> int:
    with tempfile.TemporaryDirectory() as d:
        img = Path(d) / "card.img"
        imgpatch.make_selftest_image(img)
        data, _raw = read_card(str(img))
        assert card_code(data) == b"QSD-302-100", data[:16]
        # NK1-shaped header for the unit side
        nk1 = Path(d) / "nk1.bin"
        hdr = bytearray(0x80)
        hdr[0x40:0x44] = b"ECEC"
        hdr[0x60:0x6b] = b"QSD-301-100"
        hdr[0x70:0x74] = b"\x00\x10\x00\x10"
        nk1.write_bytes(bytes(hdr))
        r = unit_record(str(nk1))
        assert r["code"] == "QSD-301-100" and r["mapdb"] == (16, 16), r
        nand = Path(d) / "nand.bin"
        nand.write_bytes(bytes(NK1_IN_NAND) + bytes(hdr))
        assert unit_record(str(nand))["nk1_offset"] == NK1_IN_NAND
        # length guard and shape guard
        for bad in ("QSD-301-10", "qsd-301-100"):
            try:
                new_file(data, bad)
            except SystemExit:
                pass
            else:
                raise AssertionError("accepted %r" % bad)
        p = argparse.Namespace(image=str(img), code=None, from_nk1=str(nk1), out=None,
                               in_place=True, dry_run=False, file_only=False)
        assert cmd_set(p) == 0
        data2, raw2 = read_card(str(img))
        assert card_code(data2) == b"QSD-301-100", data2[:16]
        assert data2[11:] == data[11:]
        assert raw2 == data2, raw2[:16]
        assert cmd_set(p) == 0          # second run: nothing to do
    print("card_mapcode selftest: ok")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("show", help="print the card's HDD_INFO.TXT and map code")
    s.add_argument("--image", required=True)
    u = sub.add_parser("unit", help="print the unit's map code from NK1 / a NAND dump")
    u.add_argument("--nk1", required=True)
    t = sub.add_parser("set", help="change the card's map code")
    t.add_argument("--image", required=True)
    g = t.add_mutually_exclusive_group(required=True)
    g.add_argument("--code", help="new map code, e.g. QSD-301-100")
    g.add_argument("--from-nk1", metavar="FILE", help="take it from NK1 or a NAND dump")
    t.add_argument("-o", "--out", help="write a patched copy here")
    t.add_argument("--in-place", action="store_true", help="patch IMAGE itself")
    t.add_argument("--file-only", action="store_true",
                   help="leave the raw copy at 0x06000000 unchanged")
    t.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "show":
        return cmd_show(a)
    if a.cmd == "unit":
        return cmd_unit(a)
    if a.cmd == "set":
        return cmd_set(a)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
