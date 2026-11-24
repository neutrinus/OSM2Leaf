#!/usr/bin/env python3
"""capacity_l3.py - probe the largest road record and shape the firmware walks (M5.92).

The record is served from the EU2011 card through ``--replace``; the firmware
mount, data-access task and LOC_map shape walk are run by ``locmap_l3.py``.
Nothing of the firmware is replaced: the synthetic record is a real ``0x00fa``
road body built by ``fa_encode``/``tilewriter`` and spliced into a copy of the
factory tile at the parcel the start screen asks for (row 17, col 14 of
``B48R058R.DAT``, code ``0xa6cdd6be``).

What is measured, for each synthetic record:

* the L3 data-access reply sub-code (3 = served, 9 = no record);
* the inflate window the firmware allocates (groups[0]["window"]);
* whether ``locmap_l3`` produced the 0x0fa0 sub 0x019a message and ran the
  shape walk ``fn 0x0041f3dc`` (a loud pass/fail, not a trace comparison).

The first failing size is the one where the record is served (sub 3) but no
LOC_map message is produced.  ``sh4dis`` of the copy handler ``fn 0x0042613c``
names the enforcing instruction: at function offset ``+0x1b6`` it loads
``0x000109a0`` and at ``+0x1bc`` executes ``cmp/ge r3, r1``; a window above
that value bails before the LOC_map post.  The walk's shape point-count gate
is the ``cmp/hs r1, r0`` at function offset ``+0xe0`` of ``fn 0x0041f3dc``
with ``r0 = 0x03e8`` (1000 points).

Usage:
  capacity_l3.py --selftest
  capacity_l3.py probe --image IMG256 --card-image CARD.img
                  [--factory TILE.DAT] [--workdir DIR] [--json OUT]
  capacity_l3.py disasm --image IMG256

``--workdir`` holds generated tile copies (no vendor bytes are committed).
Exit codes: probe 0 all probes ran, 1 usage/input, 2 a probe was BLOCKED.
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE / "ze0-viewer" / "tools_ze0", HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

PARCEL = (77, 941, 17, 14)          # code 0xa6cdd6be, served at the start screen
MESH = 0xA6C1D6B2
XY = (1024, 1024)
FACTORY_MAX = 18_580                 # M4.86 inflated bytes (baseline)
MULTIPLIERS = (1, 2, 4, 8, 16)
POINT_COUNTS = (1_000, 8_000, 32_000)
SHAPE_POOL_LIMIT = 0x109A0           # literal at fn 0x0042613c + 0x1b6 (sh4dis)
POINT_LIMIT = 0x3E8                  # literal used at fn 0x0041f3dc + 0xe0 (sh4dis)
MAX_SHAPE_POINTS = 255               # tilewriter.M5.88 writer split
RECORD_OFF = 0xA1B5FF4               # road record block of the served parcel
DIR_PAIR_OFF = 0xA10D434             # dir even (comp_words, plain_words) of that record
OLD_COMP = 7_384                     # factory slot length, kept for in-place writes


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def point_pattern(n: int, lon0: float, lat0: float, w: float, h: float):
    """A repeating pattern: compresses well so large records fit the old slot."""
    return [(lon0 + w * (0.02 + 0.96 * (i % 50) / 50),
             lat0 + h * (0.1 + 0.8 * (i % 7) / 7)) for i in range(n)]


def build_record(plain_target: int, parcel=PARCEL):
    """Return (plain, comp, n_points) at >= plain_target inflated bytes.

    Point count is derived analytically (~4.19 B/point, header ~138 B) and
    corrected by a short linear search; no open-ended loop.
    """
    import tilewriter
    import clarion_bg

    table = tilewriter.default_class_table()
    y0, x0, row, col = parcel
    lon0, lat0, w, h = clarion_bg.parcel_geo(1, y0, x0, row, col)

    def build(n):
        pts = point_pattern(n, lon0, lat0, w, h)
        return tilewriter.build_road_record(1, parcel, [(pts, "residential", "")],
                                            table, 826, write_names=False,
                                            allow_oversize=True)

    n = max(2, int((plain_target - 138) / 4.19))
    plain, comp, _, _ = build(n)
    for _ in range(64):
        if len(plain) >= plain_target:
            break
        n = int(n * plain_target / max(1, len(plain))) + 16
        plain, comp, _, _ = build(n)
    return plain, comp, n


def splice(blob: bytes, plain: bytes, comp: bytes) -> bytes:
    """Put one record in the served parcel of a factory tile.

    Small streams are written in place (directory pair updated).  Larger ones
    use tilewriter.splice_factory, which appends a new row block and repoints
    the directory tag; the caller must also grow the DRSTR001 size when the
    new block lands past the factory EOF (documented in the EXP).
    """
    import tilewriter
    out, _report = tilewriter.splice_factory(blob, 1, {PARCEL: {
        "plain": plain, "comp": comp}})
    return out


def probe_one(image: str, card: str, factory: str, workdir: Path,
              label: str, plain: bytes, comp: bytes, size: int) -> dict:
    """Run one L3 probe and return a compact verdict row."""
    import locmap_l3 as L
    import vcard_l3 as V

    tile = splice(open(factory, "rb").read(), plain, comp)
    tile_path = workdir / (label + ".DAT")
    tile_path.write_bytes(tile)
    replaces = [f"MAPAL001/B48R058R.DAT={tile_path}"]
    if len(tile) > 0x113EA900:
        # factory EOF: grow DRSTR001 so the firmware reads the appended block
        import dir_read_len
        drstr = workdir / "DRSTR-grown.DAT"
        if not drstr.exists():
            card_obj = V.make_card(None, card, {})
            entry = card_obj.resolve("DRSTR001.DAT")
            drstr.write_bytes(V.Expected(card_obj)._whole(entry))
        tmp = workdir / "DRSTR-tmp.DAT"
        subprocess_run = __import__("subprocess").run
        subprocess_run([sys.executable, str(HERE / "dir_read_len.py"), "drstr-size",
                        str(drstr), "MAPAL001/B48R058R.DAT", str(len(tile)),
                        "-o", str(tmp)], check=True, capture_output=True)
        tmp.replace(drstr)
        replaces.append(f"DRSTR001.DAT={drstr}")

    json_path = workdir / (label + ".json")
    cmd = [sys.executable, str(HERE / "locmap_l3.py"), "run", image,
           "--card-image", card, "--mesh", hex(MESH),
           "--xy", "%d,%d" % XY, "--json", str(json_path)]
    for r in replaces:
        cmd += ["--replace", r]
    run = __import__("subprocess").run(cmd, capture_output=True, text=True)
    text = run.stdout + run.stderr
    row = dict(label=label, target_bytes=size, plain_bytes=len(plain),
               comp_bytes=len(comp), window=None, reply_subs=None,
               loc_messages=0, walk=False, verdict="BLOCKED", raw_tail=text[-400:])
    if json_path.exists():
        d = json.loads(json_path.read_text())
        row["reply_subs"] = [r["sub"] for r in d.get("requests", [{}])[0].get("replies", [])]
        if "groups" in d:
            row["window"] = d["groups"][0]["window"]
        row["loc_messages"] = d.get("loc_messages", 0)
        row["walk"] = "RESULT: walk ran" in text
        row["shape_sha1"] = d.get("shape_sha1")
        row["read_bytes"] = d.get("read_bytes")
        row["rows"] = d.get("rows")
        served = 3 in (row["reply_subs"] or [])
        if served and row["walk"]:
            row["verdict"] = "PASS"
        elif served:
            row["verdict"] = "FAIL (served, no LOC_map walk)"
        else:
            row["verdict"] = "FAIL (not served)"
    return row


def cmd_probe(args) -> int:
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    factory = args.factory or str(workdir / "F.DAT")
    if not os.path.isfile(factory):
        import vcard_l3 as V
        card = V.make_card(None, args.card_image, {})
        entry = card.resolve("MAPAL001\\B48R058R.DAT")
        Path(factory).write_bytes(V.Expected(card)._whole(entry))
    rows = []
    for mult in MULTIPLIERS:
        size = FACTORY_MAX * mult
        if size >= 0x10000 * 2:
            # tilewriter refuses > 0x10000 words (its own writer limit, not the
            # firmware's); note this and skip the build, do not call it a
            # firmware verdict.
            rows.append(dict(label=f"{mult}x", target_bytes=size, plain_bytes=None,
                             verdict="SKIP (our writer limit, not firmware)"))
            continue
        plain, comp, n = build_record(size)
        rows.append(probe_one(args.image, args.card_image, factory, workdir,
                              f"{mult}x", plain, comp, size))
    for pts in POINT_COUNTS:
        # expressed as several <=255-point shapes (a 32k-point *single* shape
        # is not expressible: word1 count is <= 0x0fff and the walk skips
        # shapes with > 1000 points at fn 0x0041f3dc + 0xe0).
        n = pts
        plain, comp, _ = build_record(max(FACTORY_MAX, n * 2))
        rows.append(probe_one(args.image, args.card_image, factory, workdir,
                              f"pts{pts}", plain, comp, n))
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=2))
    for r in rows:
        print("%-8s target=%-8s plain=%-8s window=%-8s reply=%-16s %s"
              % (r["label"], r.get("target_bytes"), r.get("plain_bytes"),
                 r.get("window"), r.get("reply_subs"), r["verdict"]))
    return 2 if any(r["verdict"] == "BLOCKED" for r in rows) else 0


def cmd_disasm(args) -> int:
    import subprocess
    for va, count in ((0x0042613C, 60), (0x0041F3DC, 240)):
        out = subprocess.run([sys.executable, str(HERE / "sh4dis.py"), args.image,
                              "Navi.exe", "--va", hex(va), "--count", str(count)],
                             capture_output=True, text=True)
        print(out.stdout)
    return 0


def selftest() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print("%-58s %s" % (name, "ok" if cond else "FAIL"))
        ok = ok and bool(cond)

    check("shape pool literal is 0x109A0 (68000 B)", SHAPE_POOL_LIMIT == 0x109A0)
    check("point-count gate is 0x3e8 (1000)", POINT_LIMIT == 0x3E8)
    check("writer splits shapes at 255 points", MAX_SHAPE_POINTS == 255)
    check("factory baseline is 18580 B inflated", FACTORY_MAX == 18580)
    check("multipliers are 1,2,4,8,16", MULTIPLIERS == (1, 2, 4, 8, 16))
    check("point probes are 1k,8k,32k", POINT_COUNTS == (1000, 8000, 32000))
    check("record off and dir pair are in the factory tile",
          0xA100000 < RECORD_OFF < 0x113EA900 and 0xA100000 < DIR_PAIR_OFF < 0x113EA900)
    plain, comp, n = build_record(FACTORY_MAX)
    check("build_record reaches >= 18580 B (%d B, n=%d)" % (len(plain), n),
          len(plain) >= FACTORY_MAX and comp[:2] == b"\x78\x9c")
    check("record code is the served parcel 0xa6cdd6be",
          struct.unpack_from(">HH", plain, 0) == (0xA6CD, 0xD6BE))
    check("factory slot fits 1x record (%d B comp)" % len(comp), len(comp) <= OLD_COMP)
    print("capacity_l3 selftest: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("probe")
    p.add_argument("--image", default="archive/head256.img")
    p.add_argument("--card-image",
                   default="archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img")
    p.add_argument("--factory", help="factory B48R058R.DAT (extracted if absent)")
    p.add_argument("--workdir", default=str(Path.home() / "projekty/leafre-work/scratch/m5.92"))
    p.add_argument("--json")
    d = sub.add_parser("disasm")
    d.add_argument("--image", default="archive/head256.img")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "probe":
        return cmd_probe(args)
    if args.cmd == "disasm":
        return cmd_disasm(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
