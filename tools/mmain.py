#!/usr/bin/env python3
"""MMAIN001.DAT: parse, write and round-trip (M4.5).

Observed (EU 2011 image, 4,096 bytes, see the EXP):
  0x000-0x01f  header: label "QSD-309-101" at 0x00, rest UNKNOWN (kept verbatim)
  0x020-0x67f  51 FAT 32-byte directory records (standard FAT short-name
               layout, VERIFIED against the entries). Deleted records start
               with 0xE5 and still carry their old name, cluster and size.
               Live records (not 0xE5) are the current root listing.
  0x680-0xfff  zero fill

Writer: rebuilds the file from the parsed fields. Byte identity is checked by
round-trip. A rebuilt file equal to the input proves the fields cover every
non-zero byte; it does not prove what the device does with the records.

Usage:
  mmain.py FILE [--list]     parse, print the live root listing, round-trip check
  mmain.py --selftest        synthetic checks, no vendor data
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

SIZE = 0x1000
HDR_END = 0x020
REC = 0x20
REC_END = 0x680
ATTR_NAMES = {0x01: "RO", 0x02: "HID", 0x04: "SYS", 0x08: "VOL", 0x10: "DIR", 0x20: "ARC"}


def parse(blob: bytes) -> dict:
    if len(blob) != SIZE:
        raise ValueError(f"expected {SIZE} bytes, got {len(blob)}")
    recs = []
    for off in range(HDR_END, REC_END, REC):
        e = blob[off:off + REC]
        recs.append({
            "name": e[0:8].hex(),       # raw bytes, keeps 0xE5 and padding
            "ext": e[8:11].hex(),
            "attr": e[11],
            "nt": e[12],
            "ctime_fine": e[13],
            "ctime": e[14:16].hex(),
            "cdate": e[16:18].hex(),
            "adate": e[18:20].hex(),
            "cluster_hi": e[20:22].hex(),
            "mtime": e[22:24].hex(),
            "mdate": e[24:26].hex(),
            "cluster": struct.unpack("<H", e[26:28])[0],
            "size": struct.unpack("<I", e[28:32])[0],
        })
    return {"header": blob[:HDR_END].hex(), "records": recs, "tail": blob[REC_END:].hex()}


def write(doc: dict) -> bytes:
    out = bytearray(SIZE)
    hdr = bytes.fromhex(doc["header"])
    out[0:len(hdr)] = hdr
    for i, r in enumerate(doc["records"]):
        off = HDR_END + i * REC
        e = bytearray(REC)
        e[0:8] = bytes.fromhex(r["name"])
        e[8:11] = bytes.fromhex(r["ext"])
        e[11] = r["attr"]
        e[12] = r["nt"]
        e[13] = r["ctime_fine"]
        e[14:16] = bytes.fromhex(r["ctime"])
        e[16:18] = bytes.fromhex(r["cdate"])
        e[18:20] = bytes.fromhex(r["adate"])
        e[20:22] = bytes.fromhex(r["cluster_hi"])
        e[22:24] = bytes.fromhex(r["mtime"])
        e[24:26] = bytes.fromhex(r["mdate"])
        struct.pack_into("<H", e, 26, r["cluster"])
        struct.pack_into("<I", e, 28, r["size"])
        out[off:off + REC] = e
    tail = bytes.fromhex(doc["tail"])
    out[REC_END:REC_END + len(tail)] = tail
    return bytes(out)


def live_listing(doc: dict) -> list[dict]:
    rows = []
    for r in doc["records"]:
        name = bytes.fromhex(r["name"])
        if name[0] in (0x00, 0xE5):
            continue
        base = bytes.fromhex(r["name"]).decode("latin1").rstrip()
        ext = bytes.fromhex(r["ext"]).decode("latin1").rstrip()
        full = base + ("." + ext if ext else "")
        rows.append({"name": full, "attr": r["attr"], "cluster": r["cluster"], "size": r["size"]})
    return rows


def _selftest() -> int:
    fails = []

    def check(name, cond):
        if not cond:
            fails.append(name)

    # synthetic: header, one live dir, one deleted file, zero tail
    blob = bytearray(SIZE)
    blob[0:11] = b"SYN-000-000"
    e = bytearray(REC)
    e[0:8] = b"DEMO    "; e[8:11] = b"DAT"; e[11] = 0x20
    struct.pack_into("<H", e, 26, 2); struct.pack_into("<I", e, 28, 4096)
    blob[HDR_END:HDR_END + REC] = e
    e2 = bytearray(REC)
    e2[0:8] = b"\xe5OLD    "; e2[8:11] = b"LST"; e2[11] = 0x20
    struct.pack_into("<H", e2, 26, 5); struct.pack_into("<I", e2, 28, 19)
    blob[HDR_END + REC:HDR_END + 2 * REC] = e2
    blob = bytes(blob)
    doc = parse(blob)
    check("synthetic record count", len(doc["records"]) == 51)
    check("synthetic roundtrip", write(doc) == blob)
    rows = live_listing(doc)
    check("live listing", rows == [{"name": "DEMO.DAT", "attr": 0x20, "cluster": 2, "size": 4096}])
    check("bad length refused", _raises(lambda: parse(b"\x00" * 10)))
    print(f"selftest: {'OK' if not fails else 'FAIL ' + ', '.join(fails)}")
    return 0 if not fails else 1


def _raises(fn) -> bool:
    try:
        fn()
    except ValueError:
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if not a.file:
        ap.error("FILE is required")
    blob = Path(a.file).read_bytes()
    doc = parse(blob)
    ok = write(doc) == blob
    live = live_listing(doc)
    print(f"records={len(doc['records'])} deleted={sum(1 for r in doc['records'] if r['name'][:2] == 'e5')} live={len(live)}")
    if a.list:
        for r in live:
            attr = "+".join(v for k, v in ATTR_NAMES.items() if r["attr"] & k) or "-"
            print(f"  {r['name']:<12} attr={attr:<4} cluster={r['cluster']:#06x} size={r['size']}")
    print(f"roundtrip={'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
