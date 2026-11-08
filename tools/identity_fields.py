#!/usr/bin/env python3
"""Read the M4.22 identity fields of a Leaf ZE0 card (stdlib only).

Subcommands (all read-only):

  header FILE...     MMAIN001/BICON001 common header: 0x160 prefix, the six
                     words at 0x180, the four bounds at 0x184 (BE i16, read
                     as N, S, W, E in arc-minutes), the 0x18c code list up to
                     the 0x3f fill, and the DATA VERSION text.
  drstr FILE         DRSTR001.DAT (no common header): the 40-byte node that
                     contains offset 0x18c, its listing offset, and the entry
                     count of the SPEECH node.
  tiles PATH         MAPAL001 tile bounding box from the BxxRyyR names.
                     PATH is a directory holding MAPAL001/ or a `7z l -slt`
                     listing saved to a text file.
  speech LISTING     SPEECH/<lang>/<kind>/ sets from a `7z l -slt` listing.

Evidence: docs/research/claims.md C-2490..C-2496; EXP-2026-11-08-M4.22.
Run `python3 tools/identity_fields.py --selftest` for synthetic checks.
"""

from __future__ import annotations

import argparse
import os
import re
import struct
import sys

CODE_FILL = 0x3F
CODE_START = 0x18C
DRSTR_NODE = 40
TILE_RE = re.compile(r"^B([0-9A-Fa-f]+)R([0-9A-Fa-f]+)R\.DAT$")


def _utf16be_until_ffff(blob: bytes) -> str:
    end = len(blob)
    for i in range(0, len(blob) - 1, 2):
        if blob[i : i + 2] == b"\xff\xff":
            end = i
            break
    return blob[:end].decode("utf-16-be", errors="replace")


def parse_header(blob: bytes) -> dict:
    """Decode the identity fields of a 512-byte MMAIN/BICON-style header."""
    if len(blob) < 0x200:
        raise ValueError(f"need 512 bytes, got {len(blob)}")
    words = [struct.unpack_from("<H", blob, 0x180 + 2 * i)[0] for i in range(6)]
    bounds = [struct.unpack_from(">h", blob, 0x184 + 2 * k)[0] for k in range(4)]
    codes = []
    pos = CODE_START
    while pos < 0x1A0 and blob[pos] != CODE_FILL:
        codes.append(blob[pos])
        pos += 1
    fill = 0
    while pos + fill < 0x1A0 and blob[pos + fill] == CODE_FILL:
        fill += 1
    version = _utf16be_until_ffff(blob[0x0E0:0x160])
    m = re.search(r"DATA VERSION (\S+)", version)
    return {
        "software_prefix_0x160": struct.unpack_from(">H", blob, 0x160)[0],
        "software_text_0x162": _utf16be_until_ffff(blob[0x162:0x180]),
        "words_0x180": words,
        "bounds_NSWE_arcmin": bounds,
        "bounds_deg": [b / 60 for b in bounds],
        "codes_0x18c": codes,
        "code_fill_bytes": fill,
        "data_version": m.group(1) if m else None,
    }


def parse_drstr(blob: bytes) -> dict:
    """Locate the 40-byte node that contains 0x18c and the SPEECH node."""
    nodes = []
    for k in range(0x200 // DRSTR_NODE):
        off = k * DRSTR_NODE
        name = blob[off : off + 8].split(b"\0")[0].decode("latin-1")
        entries = struct.unpack_from("<I", blob, off + 0x18)[0]
        listing = struct.unpack_from("<I", blob, off + 0x24)[0]
        nodes.append({"index": k, "offset": off, "name": name,
                      "entry_count": entries, "listing_offset": listing})
    host = [n for n in nodes if n["offset"] <= CODE_START < n["offset"] + DRSTR_NODE]
    speech = [n for n in nodes if n["name"] == "SPEECH"]
    return {
        "node_containing_0x18c": host[0] if host else None,
        "value_at_0x18c": struct.unpack_from("<I", blob, CODE_START)[0],
        "speech_entry_count": speech[0]["entry_count"] if speech else None,
        "nodes": nodes,
    }


def _tile_names_from_listing(path: str) -> list[str]:
    names = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("Path = "):
                p = line[7:].strip().replace("\\", "/")
                if p.startswith("MAPAL001/"):
                    names.append(p.split("/")[-1])
    return names


def tile_bbox(names: list[str]) -> dict:
    lat_lo = lon_lo = 1e9
    lat_hi = lon_hi = -1e9
    n = 0
    for name in names:
        m = TILE_RE.match(name)
        if not m:
            continue
        n += 1
        b, r = int(m.group(1), 16), int(m.group(2), 16)
        lat0 = b * 2 / 3
        lon1 = 108 - r
        lat_lo = min(lat_lo, lat0)
        lat_hi = max(lat_hi, lat0 + 16 / 3)
        lon_lo = min(lon_lo, lon1 - 8)
        lon_hi = max(lon_hi, lon1)
    return {"tiles": n, "lat": [lat_lo, lat_hi], "lon": [lon_lo, lon_hi]}


def speech_sets(path: str) -> dict:
    sets: dict[str, set[str]] = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.startswith("Path = "):
                continue
            p = line[7:].strip().replace("\\", "/")
            parts = p.split("/")
            if len(parts) >= 3 and parts[0] == "SPEECH":
                sets.setdefault(parts[1], set()).add(parts[2])
    return {lang: sorted(kinds) for lang, kinds in sorted(sets.items())}


def _cmd_header(args) -> int:
    for path in args.files:
        with open(path, "rb") as f:
            info = parse_header(f.read(0x200))
        print(path)
        for key, value in info.items():
            if key == "words_0x180":
                value = " ".join(f"{v:04x}" for v in value)
            elif isinstance(value, list):
                value = " ".join(
                    f"{v:.2f}" if isinstance(v, float) else str(v) for v in value
                )
            print(f"  {key}: {value}")
    return 0


def _cmd_drstr(args) -> int:
    with open(args.file, "rb") as f:
        info = parse_drstr(f.read(0x200))
    for key in ("node_containing_0x18c", "value_at_0x18c", "speech_entry_count"):
        print(f"  {key}: {info[key]}")
    for node in info["nodes"]:
        print(f"  node{node['index']:2d} @0x{node['offset']:03x} {node['name']!r:12} "
              f"entries={node['entry_count']} listing=0x{node['listing_offset']:x}")
    return 0


def _cmd_tiles(args) -> int:
    if os.path.isdir(args.path):
        names = os.listdir(os.path.join(args.path, "MAPAL001"))
    else:
        names = _tile_names_from_listing(args.path)
    print(tile_bbox(names))
    return 0


def _cmd_speech(args) -> int:
    for lang, kinds in speech_sets(args.listing).items():
        print(f"  {lang}: {' '.join(kinds)}")
    return 0


def run_selftest() -> int:
    failures = 0

    def expect(label: str, ok: bool) -> None:
        nonlocal failures
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
        if not ok:
            failures += 1

    hdr = bytearray(b"\xff" * 0x200)
    hdr[0x160:0x162] = b"\x16\x00"
    hdr[0x162:0x162 + 18] = "V05.00.00".encode("utf-16-be")
    hdr[0x0E0:0x0E0 + 48] = "DATA VERSION 11/04/08/01".encode("utf-16-be")
    hdr[0x180:0x18C] = bytes.fromhex("ff ff 26 ff 12 c0 00 00 d7 b0 f3 d0")
    hdr[0x18C:0x19C] = bytes.fromhex("03 04") + b"\x3f" * 18
    info = parse_header(bytes(hdr))
    expect("0x160 prefix is 16 00", info["software_prefix_0x160"] == 0x1600)
    expect("software text starts at 0x162", info["software_text_0x162"] == "V05.00.00")
    expect("word 0 is ffff", info["words_0x180"][0] == 0xFFFF)
    expect("word 1 is ff26", info["words_0x180"][1] == 0xFF26)
    expect("bounds are 4800, 0, -10320, -3120", info["bounds_NSWE_arcmin"] == [4800, 0, -10320, -3120])
    expect("codes stop at 3f fill", info["codes_0x18c"] == [3, 4])
    expect("fill after codes is 18 bytes", info["code_fill_bytes"] == 18)
    expect("data version parsed", info["data_version"] == "11/04/08/01")

    drs = bytearray(b"\x00" * 0x200)
    drs[0x168:0x168 + 6] = b"SPEECH"
    struct.pack_into("<I", drs, 0x168 + 0x18, 2)
    struct.pack_into("<I", drs, 0x168 + 0x24, 0x1B20)
    dinfo = parse_drstr(bytes(drs))
    expect("0x18c lies in the node at 0x168", dinfo["node_containing_0x18c"]["name"] == "SPEECH")
    expect("SPEECH entry count is 2", dinfo["speech_entry_count"] == 2)
    expect("value at 0x18c is listing offset 0x1b20", dinfo["value_at_0x18c"] == 0x1B20)

    names = ["B28R070R.DAT", "B18R100R.DAT", "README.TXT"]
    box = tile_bbox(names)
    expect("two tiles counted, README ignored", box["tiles"] == 2)
    # B18R100R: lat_min 16, lon_max -148; B28R070R: lat_min 26.67, lon_max -4
    expect("lat range starts at 16.0 (B18)", abs(box["lat"][0] - 16.0) < 1e-9)
    expect("lon range starts at -156.0 (B18R100R)", abs(box["lon"][0] - (-156.0)) < 1e-9)

    listing = [
        "Path = SPEECH/SP/GID/SSP00000.GID",
        "Path = SPEECH/SP/VR/VSP00000.AGM",
        "Path = SPEECH\\CF\\TTS\\TCF00000.TTS",
        "Path = MAPAL001/B28R070R.DAT",
    ]
    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"), f"identity_fields_selftest_{os.getpid()}.txt")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(listing) + "\n")
        sets = speech_sets(tmp)
        expect("speech sets: SP has GID and VR, CF has TTS",
               sets == {"CF": ["TTS"], "SP": ["GID", "VR"]})
        names2 = _tile_names_from_listing(tmp)
        expect("tile names read from a 7z listing", names2 == ["B28R070R.DAT"])
    finally:
        os.remove(tmp)

    print(f"identity_fields selftest: {'OK' if failures == 0 else f'{failures} FAILED'}")
    return 0 if failures == 0 else 1


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv == ["--selftest"]:
        return run_selftest()
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        epilog="--selftest (alone) runs the synthetic checks and needs no vendor data.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("header")
    p.add_argument("files", nargs="+")
    p.set_defaults(func=_cmd_header)
    p = sub.add_parser("drstr")
    p.add_argument("file")
    p.set_defaults(func=_cmd_drstr)
    p = sub.add_parser("tiles")
    p.add_argument("path")
    p.set_defaults(func=_cmd_tiles)
    p = sub.add_parser("speech")
    p.add_argument("listing")
    p.set_defaults(func=_cmd_speech)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
