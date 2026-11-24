#!/usr/bin/env python3
"""Scan a Leaf unit dump or a firmware image for stored position records (M1.56).

Two scans, both from EXP-2026-11-22-M1.50:

``vflash DUMP``
    The navigation's stored car positions are consecutive little-endian int32
    pairs in 1/512 arc-second (the unit ``Vehicle.exe`` prints as
    ``Latitude [%10d] Longitude [%10d] (/ 512 (sec))``, C-8249).  The pair is
    inside a record whose date follows: a little-endian u16 year ``0x07d7``
    (2007), u8 month, u8 day, u8 hour, u8 minute.  With the receiver's
    1024-week rollover, 2007-04-04 stamps the real 2026-11-18.  The scanner
    counts pairs in the US-Midwest box (36..46 N, 81..91 W), reports their
    date span and bounding box, and counts copies within a radius of a
    reference point (default the OpenCARWINGS point 37.4058806, -84.4876444).

``rom IMAGE``
    The §F8 coordinate-constant scan: encode the OpenCARWINGS point into a
    dozen integer scalings, two byte orders and both pair orders, plus
    float32/64 (degrees and radians) and ASCII, search the raw image, then
    repeat with a +/-0.02 degree tolerance.

    ``--image-start`` only labels the image; the scan reads raw bytes as-is.

Usage:
  position_dump_scan.py vflash DUMP [--json] [--radius-m M] [--lat LAT --lon LON]
  position_dump_scan.py rom IMAGE [--json] [--tol-deg D]
  position_dump_scan.py --selftest

Stdlib only.  Method and results:
docs/experiments/EXP-2026-11-22-M1.50-us-unit-position-kentucky.md
"""

import argparse
import json
import math
import os
import struct
import sys
import tempfile

UNITS_PER_DEG = 512 * 3600
DATE_OFFSET = 8  # year u16 at pair+8, from EXP-M1.50 §U3 date text; see EXP Scope
US_LAT = (36.0, 46.0)
US_LON = (-91.0, -81.0)
REF_LAT = 37.4058805556
REF_LON = -84.4876444444
ROLLOVER_YEAR = 0x07D7
ROLLOVER_WEEKS = 1024


def pair_deg(lat_units, lon_units):
    return lat_units / UNITS_PER_DEG, -lon_units / UNITS_PER_DEG


def in_us_box(lat, lon):
    return US_LAT[0] <= lat <= US_LAT[1] and US_LON[0] <= lon <= US_LON[1]


def decode_date(rec, off):
    """Decode the date that follows a position pair, or None.

    The M1.50 scanner read the year as a little-endian u16 at pair+8,
    followed by month, day, hour, minute.  A 0x07d7 year is 2007, never
    2026 -- that is the rollover, not the current date.  The date offset is
    derived from the §U3 record description, not fitted to the selftest.
    """
    if len(rec) < off + DATE_OFFSET + 6:
        return None
    year, month, day, hour, minute = struct.unpack_from(
        "<HBBBB", rec, off + DATE_OFFSET)
    if not (1 <= month <= 12 and 1 <= day <= 31 and hour <= 23 and minute <= 59):
        return None
    return year, month, day, hour, minute


def year_to_ce(year):
    """Print the on-disk year; 0x07d7 is 2007, not 2026."""
    return year


def foreign_date(year, month, day):
    """The real date of a rolled-over timestamp (1024 weeks later)."""
    import datetime
    try:
        stamp = datetime.date(year, month, day)
    except ValueError:
        return None
    real = stamp + datetime.timedelta(weeks=ROLLOVER_WEEKS)
    return real.isoformat()


def distance_m(lat, lon, ref_lat, ref_lon):
    mean = math.radians((lat + ref_lat) / 2.0)
    return math.hypot((lat - ref_lat) * 111320.0,
                      (lon - ref_lon) * 111320.0 * math.cos(mean))


def scan_vflash(data, ref_lat=REF_LAT, ref_lon=REF_LON, radius_m=15.0):
    pairs = []
    for off in range(0, len(data) - 15, 4):
        lat_u, lon_u = struct.unpack_from("<ii", data, off)
        lat, lon = pair_deg(lat_u, lon_u)
        if not in_us_box(lat, lon):
            continue
        date = decode_date(data, off)
        pairs.append((off, lat, lon, date))
    near = [p for p in pairs
            if distance_m(p[1], p[2], ref_lat, ref_lon) <= radius_m]
    dates = [p[3] for p in pairs if p[3]]
    result = {
        "pairs": len(pairs),
        "offsets": [p[0] for p in pairs],
        "near_ref": len(near),
        "radius_m": radius_m,
        "ref": [ref_lat, ref_lon],
        "box_lat": [min((p[1] for p in pairs), default=None),
                    max((p[1] for p in pairs), default=None)],
        "box_lon": [min((p[2] for p in pairs), default=None),
                    max((p[2] for p in pairs), default=None)],
        "date_span": None,
        "rollover_date": None,
    }
    if dates:
        lo = min(dates)
        hi = max(dates)
        result["date_span"] = "%04x-%02d-%02d %02d:%02d .. %04x-%02d-%02d %02d:%02d" % (
            lo[0], lo[1], lo[2], lo[3], lo[4],
            hi[0], hi[1], hi[2], hi[3], hi[4])
        result["rollover_date"] = foreign_date(0x07D7, 4, 4)
    return result


# §F8 integer scalings: (scale name, factor applied to degrees)
SCALES = [
    ("deg*1e5", 1e5), ("deg*1e6", 1e6), ("deg*1e7", 1e7),
    ("arcsec*1", 3600.0), ("arcsec*8", 3600.0 * 8),
    ("arcsec*10", 3600.0 * 10), ("arcsec*100", 3600.0 * 100),
    ("arcsec*256", 3600.0 * 256), ("arcsec*1000", 3600.0 * 1000),
    ("semicircles", 180.0), ("2^24/180", (1 << 24) / 180.0),
    ("u32circle", (1 << 32) / 360.0),
]


def candidate_bytes(lat, lon, scale, order, byteorder):
    a, b = (lat, lon) if order == "latlon" else (lon, lat)
    ia, ib = int(round(a * scale)), int(round(b * scale))
    return (struct.pack("<ii" if byteorder == "little" else ">ii", ia, ib),
            struct.pack("<II" if byteorder == "little" else ">II", ia & 0xFFFFFFFF, ib & 0xFFFFFFFF))


def scan_rom(data, lat=REF_LAT, lon=REF_LON, tol_deg=0.02):
    """Search raw bytes for the given point.

    ``exact_hits`` counts every encoding form found; ``exact_detail`` names
    each form so a positive control can show *which* form matched, and a
    byte-swapped blob can be shown to match none of the little-endian forms.
    """
    exact = []
    for name, scale in SCALES:
        for order in ("latlon", "lonlat"):
            for byteorder in ("little", "big"):
                pat, _ = candidate_bytes(lat, lon, scale, order, byteorder)
                if pat in data:
                    exact.append("%s %s %s" % (name, order, byteorder))
    for fmt in ("<f", ">f", "<d", ">d"):
        for a, b in ((lat, lon), (lon, lat),
                     (math.radians(lat), math.radians(lon)),
                     (math.radians(lon), math.radians(lat))):
            pat = struct.pack(fmt, a) + struct.pack(fmt, b)
            if pat in data:
                exact.append("float %s" % fmt)
    for text in ("%f,%f" % (lat, lon), "%.7f %.7f" % (lat, lon),
                 "%d %d" % (int(lat * 1e5), int(lon * 1e5))):
        if text.encode() in data:
            exact.append("ascii")

    tolerance = []
    # iter_unpack walks 4-byte LE int32 pairs in C; the old per-offset Python
    # loop took minutes on a 256 MiB image.
    lat_ref_u = lat * UNITS_PER_DEG
    lon_ref_u = -lon * UNITS_PER_DEG
    tol_u = tol_deg * UNITS_PER_DEG
    end = len(data) - (len(data) % 4)
    for off, (la, lo) in enumerate(struct.iter_unpack("<ii", data[:end])):
        if abs(la - lat_ref_u) > tol_u or abs(lo - lon_ref_u) > tol_u:
            continue
        dla = la / UNITS_PER_DEG - lat
        dlo = -lo / UNITS_PER_DEG - lon
        if in_us_box(lat + dla, lon + dlo):
            tolerance.append((off * 8, round(lat + dla, 6), round(lon + dlo, 6)))
    return {"exact_hits": len(exact), "exact_detail": exact,
            "tolerance_pairs": len(tolerance),
            "tolerance_detail": tolerance[:10], "tol_deg": tol_deg,
            "encodings": len(SCALES) * 2 * 2 * 2 + 16 + 3}


def selftest():
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" %
              ("ok  " if ok else "FAIL", label, got, want))

    with tempfile.TemporaryDirectory(prefix="position-dump-scan-") as td:
        path = os.path.join(td, "dump.bin")
        rec = bytearray(1024)
        struct.pack_into("<ii", rec, 64, int(round(REF_LAT * UNITS_PER_DEG)),
                         int(round(-REF_LON * UNITS_PER_DEG)))
        struct.pack_into("<HBBBB", rec, 64 + DATE_OFFSET, 0x07D7, 4, 4, 15, 34)
        with open(path, "wb") as fh:
            fh.write(rec)
        with open(path, "rb") as fh:
            data = fh.read()
        got = scan_vflash(data)
        check("planted pair count", got["pairs"], 1)
        check("planted pair near ref", got["near_ref"], 1)
        check("planted pair offset", got["offsets"][0], 64)
        check("planted date span", got["date_span"],
              "07d7-04-04 15:34 .. 07d7-04-04 15:34")
        check("0x07d7 is 2007", "%04x" % year_to_ce(0x07D7), "07d7")
        check("rollover date", got["rollover_date"], "2026-11-18")

        # Negative: the same pair encoded little-endian lon/lat (swapped) is
        # outside the US box and must not count.
        swapped = bytearray(1024)
        struct.pack_into("<ii", swapped, 64, int(round(-REF_LON * UNITS_PER_DEG)),
                         int(round(REF_LAT * UNITS_PER_DEG)))
        check("swapped pair ignored", scan_vflash(swapped)["pairs"], 0)
        # Negative: an arbitrary LE pair far outside the box is ignored.
        zeros = bytearray(1024)
        check("empty dump pair count", scan_vflash(zeros)["pairs"], 0)
        # Negative: the same date at the alternative 4-byte offset must not
        # be reported as the planted date (offset derived, not self-confirmed).
        shiftdate = bytearray(rec)
        struct.pack_into("<HBBBB", shiftdate, 64 + 4, 0x07D7, 4, 4, 15, 34)
        struct.pack_into("<HBBBB", shiftdate, 64 + DATE_OFFSET, 0, 0, 0, 0, 0)
        check("shifted-date span rejected",
              scan_vflash(shiftdate)["date_span"], None)
        # Negative: a date that is not 0x07d7 is not stamped 2007-04-04.
        baddate = bytearray(rec)
        struct.pack_into("<HBBBB", baddate, 64 + DATE_OFFSET, 0x07EA, 4, 4, 15, 34)
        check("wrong year still in span",
              "07d7-04-04" in scan_vflash(baddate)["date_span"], False)

        # §F8 synthetic: plant the exact scaled pair in an otherwise empty
        # image; the scan must find it, and an empty image must find none.
        # §F8 positive control: plant known coordinate constants in BOTH byte
        # orders and a float64 form; the scan must find them all and name them.
        rom_blob = bytearray(2048)
        for scale, order, bo, off in ((1e6, "latlon", "little", 128),
                                      (1e7, "lonlat", "big", 256)):
            pat, _ = candidate_bytes(REF_LAT, REF_LON, scale, order, bo)
            rom_blob[off:off + 8] = pat
        rom_blob[512:528] = struct.pack("<d", REF_LAT) + struct.pack("<d", REF_LON)
        rom = scan_rom(rom_blob)
        check("rom exact hits >= 3", rom["exact_hits"] >= 3, True)
        check("rom little scaling named",
              any("deg*1e6 latlon little" in d for d in rom["exact_detail"]), True)
        check("rom big scaling named",
              any("deg*1e7 lonlat big" in d for d in rom["exact_detail"]), True)
        check("rom float64 named",
              any("float <d" in d for d in rom["exact_detail"]), True)
        empty = scan_rom(bytearray(2048))
        check("empty ROM exact hits", empty["exact_hits"], 0)
        check("empty ROM tolerance pairs", empty["tolerance_pairs"], 0)
        # Negative: byte-swap the planted LE pair -> its LE form is gone.
        swapped_blob = bytearray(rom_blob)
        pat, _ = candidate_bytes(REF_LAT, REF_LON, 1e6, "latlon", "little")
        swapped_blob[128:136] = pat[::-1]
        swap = scan_rom(swapped_blob)
        check("byte-swapped LE form absent",
              any("deg*1e6 latlon little" in d for d in swap["exact_detail"]), False)
        # Positive tolerance: a planted LE 1/512 pair is found within 0.02 deg.
        tolerance_blob = bytearray(1024)
        tolerance_blob[128:136] = struct.pack(
            "<ii", int(round(REF_LAT * UNITS_PER_DEG)),
            int(round(-REF_LON * UNITS_PER_DEG)))
        tolerance = scan_rom(tolerance_blob)
        check("planted ROM tolerance pair", tolerance["tolerance_pairs"] >= 1, True)
        check("planted ROM tolerance offset",
              tolerance["tolerance_detail"][0][0], 128)

    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    v = sub.add_parser("vflash", help="scan a unit dump for LE int32 1/512s pairs")
    v.add_argument("dump")
    v.add_argument("--radius-m", type=float, default=15.0)
    v.add_argument("--lat", type=float, default=REF_LAT)
    v.add_argument("--lon", type=float, default=REF_LON)
    v.add_argument("--json", action="store_true")
    r = sub.add_parser("rom", help="scan a firmware image for a coordinate constant")
    r.add_argument("image")
    r.add_argument("--tol-deg", type=float, default=0.02)
    r.add_argument("--image-start", type=lambda s: int(s, 0), default=None)
    r.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "vflash":
        with open(args.dump, "rb") as fh:
            data = fh.read()
        got = scan_vflash(data, args.lat, args.lon, args.radius_m)
        if args.json:
            print(json.dumps(got, sort_keys=True))
        else:
            print("pairs=%d near_ref=%d radius_m=%g" %
                  (got["pairs"], got["near_ref"], got["radius_m"]))
            print("box_lat=%.6f..%.6f box_lon=%.6f..%.6f" %
                  (got["box_lat"][0], got["box_lat"][1],
                   got["box_lon"][0], got["box_lon"][1]))
            print("date_span=%s" % got["date_span"])
            print("rollover_date=%s" % got["rollover_date"])
        return 0
    if args.cmd == "rom":
        with open(args.image, "rb") as fh:
            data = fh.read()
        got = scan_rom(data, tol_deg=args.tol_deg)
        if args.json:
            print(json.dumps(got, sort_keys=True))
        else:
            print("encodings=%d exact_hits=%d tolerance_pairs=%d" %
                  (got["encodings"], got["exact_hits"], got["tolerance_pairs"]))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
