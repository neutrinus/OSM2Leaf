#!/usr/bin/env python3
"""Derive the four emulator run inputs from a Leaf ZE0 SD card image.

A ``-M ze0`` boot of the factory card needs four inputs that used to be made
by hand: the unit map code (``verinf``), the map-DB window (``mapdb``), the
``ipl-patch`` file and the qcow2 ``--sd`` overlay.  Every one of them is a
function of the card itself (M8.C1c, M8.C1d):

* ``verinf`` — the launcher compares the card's ``VER_INFO/HDD_INFO.TXT``
  line 1 (11 bytes) with the kernel image header ``+0x60`` that the unit's
  IPL writes.  The card already holds the code it was built for, so the value
  that passes is ``HDD_INFO.TXT`` line 1 (C-6881, C-7200).
* ``mapdb`` — the card's line 3 positions 5..7 encode ``MapDBVer``
  (``((d5*16)+d6)*16+d7``, B ``fn 0x03bd2ce4``); the window that contains it
  with the least slack is ``V-V`` (C-6881).
* ``ipl-patch`` — ``tools/ze0_ipl.py patch`` on the same image.
* ``--sd`` — a qcow2 overlay over the card (``tools/qemu-ze0/mkoverlay.py``),
  so QEMU's power-of-two ``sd-card`` sees a card and the original is never
  written.

The build name (EU2011 / US2011 / other) is read from ``HDD_INFO.TXT`` line 4
(map_code: ``EVEUR`` = EU, ``NAM`` = US), line 5 (year-month) and line 2 (map
set, the FAT label).  The FAT offset is the first FAT32 partition's byte
offset from the MBR.

Usage::

    python3 tools/ze0_card.py describe IMG [--json]
    python3 tools/ze0_card.py materialize IMG --workdir DIR [--verinf STR]
                       [--mapdb LO-HI] [--no-ipl] [--overlay-size-gib N]
    python3 tools/ze0_card.py selftest        # alias for --selftest
    python3 tools/ze0_card.py --selftest

Exit codes: 0 ok, 1 a card/structure error, 2 usage error.
"""
from __future__ import annotations

import argparse
import hashlib
import hashutil
import json
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "qemu-ze0"))

import cardcheck  # noqa: E402
import hddinfo  # noqa: E402
import leafimg  # noqa: E402
import mkcard  # noqa: E402
import mkoverlay  # noqa: E402
import ze0_ipl  # noqa: E402

SECTOR = 512
FAT32_TYPES = (0x0B, 0x0C)
HDD_COPY_OFFSET = 0x06000000
HDD_PATH = "VER_INFO/HDD_INFO.TXT"
DEFAULT_KERNEL_OFF = 0x3E00200
DEFAULT_APP_OFF = 0x200200


def _classify_build(record: hddinfo.HddInfo) -> str:
    """EU2011 / US2011 / other from the HDD_INFO text fields (no vendor bytes).

    ``map_code`` (line 4) is ``SDC08-EVEUR`` on the EU card and
    ``SDC08-EVNAM`` on the US card; the year on line 5 is ``11-xx`` for the
    2011 family.
    """
    map_code = record.text("map_code").upper()
    year_month = record.text("year_month")
    if map_code.endswith("EVEUR") and year_month.startswith("11-"):
        return "EU2011"
    if map_code.endswith("EVNAM"):
        return "US2011"
    return "other"


def _read_version(image_path: Path) -> tuple[bytes, int]:
    """Read HDD_INFO.TXT from the card tree; fall back to the 0x06000000 copy.

    Returns ``(raw, source_offset)``; the source is the FAT file when the
    partition lies inside the given file, else ``HDD_COPY_OFFSET``.
    """
    try:
        src = cardcheck.Fat32Image(image_path)
    except (ValueError, OSError):
        src = None
    if src is not None:
        try:
            raw = src.read(HDD_PATH)
            return raw, src.geometry.partition_offset
        except OSError:
            pass
        finally:
            src.close()
    with image_path.open("rb") as handle:
        handle.seek(HDD_COPY_OFFSET)
        raw = handle.read(512)
    if not raw.startswith(b"QSD-") and b"\r\n" not in raw:
        raise ValueError(
            "no VER_INFO/HDD_INFO.TXT and no HDD_INFO copy at 0x%08x"
            % HDD_COPY_OFFSET)
    return raw.split(b"\x00", 1)[0], HDD_COPY_OFFSET


def _fat_offset(image_path: Path) -> int | None:
    try:
        with image_path.open("rb") as handle:
            parts = [e for e in leafimg.mbr_entries(handle)
                     if e["type"] in FAT32_TYPES]
    except (ValueError, OSError):
        return None
    return parts[0]["offset"] if parts else None


def describe(image_path: Path, *, with_hash: bool = True) -> dict:
    """All values ``run.sh --card`` needs, plus the card's identity."""
    raw, hdd_source = _read_version(image_path)
    record = hddinfo.HddInfo.parse(raw)
    base_code = record.text("base_code")
    mapdb = hddinfo.extract_mapdbver(record)
    verinf = raw[:hddinfo.CHECK1_LEN]
    return {
        "image": str(image_path),
        "size": image_path.stat().st_size,
        "sha256": _sha256(image_path) if with_hash else None,
        "fat_offset": _fat_offset(image_path),
        "build": _classify_build(record),
        "label": record.text("map_set"),
        "map_code": base_code,
        "mapdbver": mapdb["value"],
        "verinf": verinf.decode("latin-1"),
        "mapdb": "%d-%d" % (mapdb["value"], mapdb["value"]),
        "hdd_info_source": hex(hdd_source),
        "hdd_info_sha256": _sha256_bytes(raw),
        "hdd_info_size": len(raw),
        "lines": {k: record.text(k) for k in hddinfo.LINE_NAMES},
    }


_sha256 = hashutil.sha256_file


_sha256_bytes = hashutil.sha256_bytes


def materialize(image_path: Path, workdir: Path, *, verinf: str | None,
                mapdb: str | None, make_ipl: bool,
                overlay_gib: int) -> dict:
    """Write the run inputs into ``workdir`` and return the paths/argv."""
    info = describe(image_path, with_hash=False)
    workdir.mkdir(parents=True, exist_ok=True)
    verinf = verinf if verinf is not None else info["verinf"]
    mapdb = mapdb if mapdb is not None else info["mapdb"]

    overlay = workdir / (image_path.stem + ".qcow2")
    size = overlay_gib << 30
    if image_path.stat().st_size > size:
        raise ValueError(
            "card %d bytes does not fit in a %d GiB overlay"
            % (image_path.stat().st_size, overlay_gib))
    overlay.write_bytes(mkoverlay.build(str(image_path), size))

    ipl_patch = None
    if make_ipl:
        lines, _notes, _info = ze0_ipl.build(
            ze0_ipl.open_image(image_path), DEFAULT_KERNEL_OFF, DEFAULT_APP_OFF,
            ze0_ipl.DEFAULT_CHAIN_AT)
        ipl_patch = workdir / "ipl-patch.txt"
        ipl_patch.write_text(ze0_ipl.render(lines))

    return {
        "overlay": str(overlay),
        "ipl_patch": str(ipl_patch) if ipl_patch else None,
        "verinf": verinf,
        "mapdb": mapdb,
        "build": info["build"],
        "strings": ["%s,%s" % (verinf, mapdb)],
    }


def _emit(info: dict) -> None:
    print("image            %s" % info["image"])
    print("size             %d bytes" % info["size"])
    if info["sha256"]:
        print("sha256           %s" % info["sha256"])
    print("build            %s" % info["build"])
    print("label            %s" % info["label"])
    print("map code         %s" % info["map_code"])
    print("mapdb            %s" % info["mapdb"])
    print("map-DB value     %d (0x%03x)" % (info["mapdbver"], info["mapdbver"]))
    print("verinf           %s" % info["verinf"])
    print("FAT offset       %s" % (
        "0x%x" % info["fat_offset"] if info["fat_offset"] is not None else "none"))
    print("HDD_INFO         %s (%d bytes, sha256 %s)" % (
        info["hdd_info_source"], info["hdd_info_size"],
        info["hdd_info_sha256"][:16]))


def _write_custom_hdd(workdir: Path, label: str, lines: list[str],
                      spc: int) -> Path:
    """Write a synthetic FAT32 card whose HDD_INFO.TXT holds ``lines``.

    Uses ``mkcard.make_synthetic_image`` for the filesystem/MBR and
    ``mkcard.mkcard`` to place the 72-byte block in ``VER_INFO/``; the image
    copy at ``0x06000000`` is written too.
    """
    raw = b"\r\n".join(line.encode("ascii") for line in lines)
    tree = workdir / "tree"
    (tree / "VER_INFO").mkdir(parents=True, exist_ok=True)
    (tree / "VER_INFO" / "HDD_INFO.TXT").write_bytes(raw)
    (tree / "CMP.LST").write_bytes(b"x")
    template = workdir / "template.img"
    mkcard.make_synthetic_image(
        template, {"X.TXT": b"x" * 64},
        part_lba=(HDD_COPY_OFFSET // SECTOR) + 256,
        total_sectors=(HDD_COPY_OFFSET // SECTOR) + 256 + 131072,
        spc=spc, label=label)
    out = workdir / "card.img"
    mkcard.mkcard(template, tree, out, explain=False, label=label)
    with out.open("r+b") as handle:
        handle.seek(HDD_COPY_OFFSET)
        handle.write(raw)
    return out


def selftest() -> int:
    fails = 0

    def check(ok: bool, label: str) -> None:
        nonlocal fails
        fails += not ok
        print("%s %s" % ("ok  " if ok else "FAIL", label))

    tmp = Path(tempfile.mkdtemp(prefix="ze0_card_selftest_"))
    eu_spec = ["QSD-302-100", "QSD-309-101", "02-110100-00",
               "SDC08-EVEUR", "11-05", "470323501005"]
    us_spec = ["QSD-301-100", "QSD-301-103", "02-100100-00",
               "SDC08-EVNAM", "10-30", "470282203030"]
    eu = _write_custom_hdd(tmp / "mk-eu", "QSD-309-101", eu_spec, spc=1)
    us = _write_custom_hdd(tmp / "mk-us", "QSD-301-103", us_spec, spc=1)
    eu_info = describe(eu)
    us_info = describe(us)

    check(eu_info["build"] == "EU2011", "EU synthetic card classifies EU2011")
    check(us_info["build"] == "US2011", "US synthetic card classifies US2011")
    check(eu_info["verinf"] == "QSD-302-100", "EU verinf is line 1")
    check(us_info["verinf"] == "QSD-301-100", "US verinf is line 1")
    check(eu_info["mapdbver"] == 16, "EU MapDBVer is 16 (0x010)")
    check(us_info["mapdbver"] == 16, "US MapDBVer is 16 (0x010)")
    check(eu_info["mapdb"] == "16-16", "EU mapdb window is 16-16")
    check(eu_info["verinf"] != us_info["verinf"], "EU and US verinf differ")
    check(eu_info["label"] != us_info["label"], "EU and US label differ")
    check(eu_info["fat_offset"] is not None and eu_info["fat_offset"] > 0,
          "EU FAT offset found")

    # Negative: a card whose line 4/5 mark a non-2011 region must classify
    # "other"; the map-DB value changes with the build digits.
    other_spec = ["QSD-302-100", "QSD-390-100", "02-140300-00",
                  "SDC08-EVEUR", "14-06", "470516001006"]
    other = _write_custom_hdd(tmp / "mk-other", "QSD-390-100",
                              other_spec, spc=1)
    other_info = describe(other)
    check(other_info["build"] == "other", "2014 card classifies 'other' (negative)")

    # materialize: overlay + ipl-patch land in the work dir, card is untouched
    before = _sha256(eu)
    work = tmp / "run"
    mat = materialize(eu, work, verinf=None, mapdb=None, make_ipl=False,
                      overlay_gib=1)
    check(Path(mat["overlay"]).is_file(), "materialize writes the overlay")
    check(mat["verinf"] == "QSD-302-100", "materialize uses derived verinf")
    check(mat["mapdb"] == "16-16", "materialize uses derived mapdb")
    check(_sha256(eu) == before, "materialize never writes the card")
    check(mat["ipl_patch"] is None, "--no-ipl leaves ipl-patch absent")

    print("ze0_card selftest: %s (%d failure(s))" %
          ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def cmd_describe(args: argparse.Namespace) -> int:
    info = describe(Path(args.image), with_hash=not args.no_hash)
    if args.json:
        print(json.dumps(info, indent=2))
    else:
        _emit(info)
    return 0


def cmd_materialize(args: argparse.Namespace) -> int:
    result = materialize(
        Path(args.image), Path(args.workdir),
        verinf=args.verinf, mapdb=args.mapdb,
        make_ipl=not args.no_ipl, overlay_gib=args.overlay_size_gib)
    for key in ("overlay", "ipl_patch", "verinf", "mapdb", "build"):
        print("%-12s %s" % (key, result[key]))
    return 0


def cmd_selftest(_args: argparse.Namespace) -> int:
    return selftest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    p_desc = sub.add_parser("describe", help="print the derived run inputs")
    p_desc.add_argument("image")
    p_desc.add_argument("--json", action="store_true")
    p_desc.add_argument("--no-hash", action="store_true",
                        help="skip the whole-image SHA-256 (fast dry-run)")
    p_desc.set_defaults(func=cmd_describe)
    p_mat = sub.add_parser("materialize",
                           help="write the overlay and ipl-patch to a work dir")
    p_mat.add_argument("image")
    p_mat.add_argument("--workdir", required=True)
    p_mat.add_argument("--verinf")
    p_mat.add_argument("--mapdb")
    p_mat.add_argument("--no-ipl", action="store_true")
    p_mat.add_argument("--overlay-size-gib", type=int, default=8)
    p_mat.set_defaults(func=cmd_materialize)
    p_self = sub.add_parser("selftest", help="alias for --selftest")
    p_self.set_defaults(func=cmd_selftest)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if not getattr(args, "func", None):
        build_parser().error("a command is required")
    try:
        return args.func(args)
    except (OSError, ValueError, struct.error) as exc:
        print("ze0_card: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
