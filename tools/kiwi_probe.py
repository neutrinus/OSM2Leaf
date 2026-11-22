#!/usr/bin/env python3
"""Structural probe for the KIWI field grammar quoted by jharg/kiwiread.

This is NOT a KIWI reader.  It answers one narrow question: do the byte fields
that KIWI uses where ZE0 has an analogous record actually fit our card bytes?
Each check has a synthetic positive control (a buffer built from the field
grammar, not from a real KIWI disc) and reports PASS only when that grammar
fits.  A PASS on a ZE0 file would be evidence for M4.63; a FAIL is the expected
result and is not a tool failure.

Field names and chapter numbers are from
<https://github.com/jharg/kiwiread> commit ``74741c5b`` (GPL-3; names only,
no code copied).  See ``docs/experiments/EXP-2026-11-22-M4.63-kiwi-map.md``.

Usage::

    python3 tools/kiwi_probe.py --selftest
    python3 tools/kiwi_probe.py sizes
    python3 tools/kiwi_probe.py header FILE          # 0xa0, 0x800, 0x184, 0x1ac
    python3 tools/kiwi_probe.py words 9b8f d3ff ...  # 22 road-header words
    python3 tools/kiwi_probe.py shape 0039c112...    # 14+ background-shape bytes
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

# Byte sizes of the packed KIWI structures, derived from the field lists in
# kiwiread.c (big-endian, #pragma pack(1)).  Used as a cross-check in the EXP.
SIZES = {
    "5.1 datavol_t": 2048,
    "management-header mhr_t": 18,
    "directory-entry dde[]": 16,
    "6.1 pdmdh_t": 30,
    "6.1.1 lmr_t": 40,
    "6.1.2 bsmr_t": 10,
    "6.2.1 bmt_t": 6,
    "7.2.1 roadhdr_t": 8,
    "7.2.1 dcmr_t": 4,
    "7.2.2.1.1 multilink_t": 16,
    "7.3.2.2.1 mingr_t (no coords)": 12,
    "mapframe_t": 36,
    "1.2.13 pid_t": 8,
}

KIWI_TYPE_CODES = {0x121, 0x122, 0x123, 0x124, 0x128, 0x210, 0x211}

# Address formulas, quoted from the two readers' field definitions.
ADDR = {
    "KIWI D (dir offset)": "offset * 2 + 0x800",
    "KIWI getsector (2048/32)": "(sa >> 8) * 2048 + (sa & 0x3f) * 32",
    "ZE0 addr_of": "(v >> 8) * 2048 + (v & 0xff) * 256",
}


def _be16(b, o):
    return struct.unpack_from(">H", b, o)[0]


def _be32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def _sws(v):
    """KIWI [SWS] word count to bytes (0xffff is the 'absent' sentinel)."""
    return 0xFFFF if v == 0xFFFF else v * 2


def _geonum(b, o):
    """KIWI 1.2.x geonum: 24-bit 1/8 arc-seconds with bit 23 as sign."""
    v = int.from_bytes(b[o:o + 3], "big")
    return (-1 if v & 0x800000 else 1) * (v & 0x7FFFFF) / 28800.0


def _printable_run(buf):
    best = run = 0
    for c in buf:
        run = run + 1 if 0x20 <= c <= 0x7E else 0
        best = max(best, run)
    return best


def check_datavol(buf, off=0xA0, span=64):
    """datavol_t.format_ver [C.64] is a printable, NUL-terminated C string."""
    field = buf[off:off + span]
    run = _printable_run(field)
    ok = run >= 8 and field.find(b"\0") >= run
    return ok, f"0x{off:x} C.64 longest printable run={run} (KIWI needs >=8)"


def check_mhr(buf, off=0x800, count=34):
    """34 mhr_t records after the 2048-byte volume header: name[12] is ASCII."""
    good = 0
    first = []
    for i in range(count):
        p = off + i * 18
        if p + 18 > len(buf):
            break
        dsa, size = _be32(buf, p), _be16(buf, p + 4)
        name = buf[p + 6:p + 18]
        valid = (0x20 <= name[0] <= 0x7E
                 and all(c == 0 or 0x20 <= c <= 0x7E for c in name)
                 and dsa not in (0, 0xFFFFFFFF) and size not in (0, 0xFFFF))
        good += bool(valid)
        if i < 2:
            first.append(f"{buf[p:p+18].hex()}")
    ok = good == count
    return ok, (f"0x{off:x} mhr_t x{count}: plausible names={good}/{count}; "
                f"first={','.join(first)}")


def check_pdmdh(buf, off=0x184):
    """pdmdh_t: lat/lng frame as four geonums, then SWS sizes and small counts."""
    if off + 30 > len(buf):
        return False, f"0x{off:x}: short buffer"
    g = [_geonum(buf, off + 8 + 3 * i) for i in range(4)]
    lmr_sz = _sws(_be16(buf, off + 12))
    nlmr, nbsmr = _be16(buf, off + 18), _be16(buf, off + 20)
    ok = (-90 <= g[0] <= 90 and -90 <= g[1] <= 90
          and -180 <= g[2] <= 180 and -180 <= g[3] <= 180
          and g[0] > g[1] and g[3] > g[2]
          and lmr_sz >= 40 and 1 <= nlmr <= 64 and 1 <= nbsmr <= 256)
    return ok, (f"0x{off:x}: geonums={[round(x, 3) for x in g]} "
                f"lmr_sz={lmr_sz} nlmr={nlmr} nbsmr={nbsmr}")


def check_lmr(buf, off=0x1AC):
    """lmr_t: level in bits 10..15, display flags, byte counts-1, bsmr offset."""
    if off + 40 > len(buf):
        return False, f"0x{off:x}: short buffer"
    level = (_be16(buf, off) >> 10) & 0x3F
    disp = [_be32(buf, off + 4 + 4 * i) for i in range(5)]
    parcels = list(buf[off + 28:off + 36])
    bsmr_off = _sws(_be16(buf, off + 36))
    ok = (1 <= level <= 6 and max(parcels) <= 15
          and all(0 < d < 0x100000 for d in disp) and bsmr_off > 0)
    return ok, (f"0x{off:x}: lvl={level} dispflag0={disp[0]:#x} "
                f"nparcels={parcels} bsmr_off={bsmr_off}")


def check_road(words):
    """roadhdr_t from the 22-word ZE0 road header: 8,4,1,1,2 bytes."""
    if len(words) < 5:
        return False, "need at least five words"
    size, ninter, ndc, nad, lvl = _sws(words[0]), words[1], words[2], words[3], (words[4] >> 10) & 0x3F
    ok = (8 <= size <= 0x10000 and ninter <= 4095
          and 1 <= ndc <= 16 and nad <= 16 and 1 <= lvl <= 6)
    return ok, (f"roadhdr_t: SWS(size)={size} ninter={ninter} "
                f"ndc={ndc} nad={nad} lvl={lvl}")


def check_shape(data):
    """mingr_t: hdr [SWS], flag (11-bit ncoord), type code, addl, sx, sy."""
    if len(data) < 12:
        return False, "need at least 12 bytes"
    hdr, flag, code, addl = struct.unpack_from(">HHHH", data, 0)
    ncoord = flag & 0x7FF
    length = 12 + 2 * ncoord + (2 if addl & 0x1000 else 0) + (2 if addl & 0x0800 else 0)
    ok = code in KIWI_TYPE_CODES and _sws(hdr) == length
    return ok, (f"mingr_t: SWS(hdr)={_sws(hdr)} ncoord={ncoord} "
                f"code={code:#x} implied length={length}")


CHECKS = (check_datavol, check_mhr, check_pdmdh, check_lmr)


def first_bg_shape(path, level=1):
    """Locate one ZE0 background shape using the checked-in viewer tools.

    Returns (offset in the inflated record, 14 raw bytes, decoded shape).
    """
    here = Path(__file__).resolve().parent / "ze0-viewer"
    sys.path.insert(0, str(here))
    sys.path.insert(0, str(here / "tools_ze0"))
    import clarion_bg
    import clarion_tile
    import ze0_mutate

    tile = clarion_tile.read_tile(Path(path).read_bytes())
    _d, _slot, _rec, _parsed, plain, _group, shape, _i = ze0_mutate.first_background(
        tile, level, dx=40)
    w = list(struct.unpack_from(">22H", plain, 0))
    gi = clarion_bg.bg_slot(w)
    base = 4 * w[gi]
    table, nlayers = [], 1 << 30
    while len(table) < nlayers and len(table) < w[gi + 1]:
        o, ln = struct.unpack_from(">HH", plain, base + 4 * len(table))
        table.append((o, ln))
        if o != 0xFFFF:
            nlayers = min(nlayers, o)
    i0 = next(i for i, (o, _ln) in enumerate(table) if o != 0xFFFF)
    p = base + 4 * table[i0][0]
    nsub, _hw = struct.unpack_from(">HH", plain, p)
    q = p + 4 + 2 + (2 if nsub > 1 else 0)
    return q, plain[q:q + 14], shape


def cmd_sizes(_args):
    for name, size in SIZES.items():
        print(f"{name:36s} {size:5d} bytes")
    print("-- addressing --")
    for name, formula in ADDR.items():
        print(f"{name:36s} {formula}")
    return 0


def cmd_header(args):
    buf = Path(args.file).read_bytes()
    print(f"file {args.file}")
    print(f"sha256 {hashlib.sha256(buf).hexdigest()}")
    bad = 0
    for fn in CHECKS:
        ok, detail = fn(buf)
        print(f"{'PASS' if ok else 'FAIL'} {fn.__name__:16s} {detail}")
        bad += not ok
    print(f"KIWI grammar fits {len(CHECKS) - bad}/{len(CHECKS)} checks "
          f"(PASS is evidence for KIWI; FAIL is expected for ZE0)")
    return 0


def cmd_words(args):
    words = [int(w, 16) for w in args.words]
    ok, detail = check_road(words)
    print(f"{'PASS' if ok else 'FAIL'} {detail}")
    return 0


def cmd_shape(args):
    ok, detail = check_shape(bytes.fromhex(args.hex))
    print(f"{'PASS' if ok else 'FAIL'} {detail}")
    return 0


def _synth_header():
    buf = bytearray(0x1000)
    # datavol_t.format_ver, chapter 5.1 [C.64]
    buf[0xA0:0xA0 + 18] = b"KIWI FORMAT 1.2.3\0"
    # 34 mhr_t at 0x800, chapter 5.1
    for i in range(34):
        p = 0x800 + i * 18
        struct.pack_into(">IH", buf, p, 0x1000 + i, 4)
        buf[p + 6:p + 12] = b"PRDM00"
    # pdmdh_t frame at 0x184, chapter 6.1
    def geonum(deg):
        v = round(abs(deg) * 28800)
        return (v | 0x800000 if deg < 0 else v).to_bytes(3, "big")
    buf[0x184 + 8:0x184 + 20] = geonum(60.0) + geonum(35.0) + geonum(10.0) + geonum(30.0)
    struct.pack_into(">HHHHH", buf, 0x184 + 12, 20, 4, 2, 3, 2)
    # lmr_t at 0x1ac, chapter 6.1.1
    struct.pack_into(">HH", buf, 0x1AC, 1 << 10, 0x0001)
    for i in range(5):
        struct.pack_into(">I", buf, 0x1AC + 4 + 4 * i, 0x100 + i)
    buf[0x1AC + 28:0x1AC + 36] = bytes([1, 1, 2, 2, 3, 3, 0, 0])
    struct.pack_into(">H", buf, 0x1AC + 36, 0x20)
    return bytes(buf)


def cmd_bgshape(args):
    off, data, shape = first_bg_shape(args.file, args.level)
    print(f"file {args.file}")
    print(f"sha256 {hashlib.sha256(Path(args.file).read_bytes()).hexdigest()}")
    print(f"inflated offset 0x{off:x}")
    print(f"bytes {data.hex()}")
    print(f"ZE0 parse: count={struct.unpack_from('>H', data, 0)[0]} "
          f"type={struct.unpack_from('>H', data, 2)[0]:#x} points={len(shape['pts'])}")
    ok, detail = check_shape(data)
    print(f"{'PASS' if ok else 'FAIL'} {detail}")
    return 0


def selftest() -> int:
    good = _synth_header()
    for fn in CHECKS:
        ok, detail = fn(good)
        assert ok, f"positive control failed for {fn.__name__}: {detail}"
    # Negative controls: real ZE0 bytes from EU2011 B28R070R.DAT
    # (SHA-256 0e4df38b…ddb), embedded so the selftest needs no card.
    ztile = bytearray(0x1000)
    ztile[0xA0:0xA0 + 64] = bytes.fromhex(
        "0046004f0052004d00410054002000560045005200530049004f004e0020005800300038002d00300032002d00300030"
        "ffffffffffffffffffffffffffffffff")
    for i in range(34):
        ztile[0x800 + i * 18:0x800 + (i + 1) * 18] = bytes.fromhex(
            "0000020000010001d9000001ffffffff0000")
    ztile[0x184:0x184 + 30] = bytes.fromhex(
        "12c00500fb500ff03f3f3f3f3f3f3f3f3f3f3f3f3f3f3fffff")
    ztile[0x1AC:0x1AC + 40] = bytes.fromhex(
        "0002010606800000059000000491000003910000029100020192000f020405910000049100000291")
    for fn in CHECKS:
        ok, _ = fn(bytes(ztile))
        assert not ok, f"negative control failed for {fn.__name__}"
    ok, _ = check_road([0x40, 3, 4, 1, 1 << 10] + [0] * 17)
    assert ok
    ok, _ = check_road([0x9B8F, 0xD3FF, 0x00FA, 0x347A, 0x2AEF] + [0] * 17)
    assert not ok
    shape = bytearray(14)
    struct.pack_into(">HHHH", shape, 0, 9, 3, 0x121, 0)
    ok, _ = check_shape(bytes(shape))
    assert ok
    ok, _ = check_shape(bytes.fromhex("0039c112ffff07ff066698c698"))
    assert not ok
    assert SIZES["5.1 datavol_t"] == 2048
    assert SIZES["6.1.1 lmr_t"] == 40
    assert SIZES["7.3.2.2.1 mingr_t (no coords)"] == 12
    print("selftest: 4 header positive controls, 4 negative controls, "
          "road +/- 1, shape +/- 1, 3 struct sizes OK")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="run synthetic checks and exit")
    sub = ap.add_subparsers(dest="command")
    sub.add_parser("sizes", help="print packed KIWI structure sizes")
    p_header = sub.add_parser("header", help="probe a tile or MMAIN header")
    p_header.add_argument("file")
    p_words = sub.add_parser("words", help="probe ZE0 road-header words")
    p_words.add_argument("words", nargs="+")
    p_shape = sub.add_parser("shape", help="probe background-shape bytes")
    p_shape.add_argument("hex")
    p_bg = sub.add_parser("bgshape", help="locate and probe a real ZE0 background shape")
    p_bg.add_argument("file")
    p_bg.add_argument("--level", type=int, default=1)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.command == "sizes":
        return cmd_sizes(args)
    if args.command == "header":
        return cmd_header(args)
    if args.command == "words":
        return cmd_words(args)
    if args.command == "shape":
        return cmd_shape(args)
    if args.command == "bgshape":
        return cmd_bgshape(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
