#!/usr/bin/env python3
"""TestMode GPS setup frames written to the receiver (M1.52).

The frame grammars are implemented by ``TestMode.exe`` (image C at
0x5200200, module #82, vbase 0x00010000) in US2011 and EU2011:

* ``fn 0x00043da8`` ``GpsDataSetDate``: 10-byte frame, byte[0]=0xa2.
  bytes[1..5] = YY, MM-1, DD, hh, mm parsed from the text fields
  (obj+0x9c onward); byte[6..7]=0; byte[8]=sum(bytes[1..7])&0x7f;
  byte[9]=0xf0.
* ``fn 0x00043f70`` ``GpsDataSetLatLon``: 14-byte frame, byte[0]=0xa0,
  byte[1]=0, bytes[2..5]=lat 4x7-bit, bytes[6..9]=lon 4x7-bit,
  byte[10..11]=0, byte[12]=sum(bytes[1..11])&0x7f, byte[13]=0xf0.
  The lat/lon text fields are at obj+0x8c / obj+0x94, hemispheres at
  obj+0x8c-8 / obj+0x94-8; N/E add 1, S/W complement.
* ``fn 0x0004443c`` ``GpsDataSetB0_A3``, ``fn 0x00044494``
  ``GpsDataSetB0_A0``, ``fn 0x000444ec`` ``GpsDataSetB3``,
  ``fn 0x0004453c`` ``GpsDataSetB4``: four 6-byte constant command frames.

All numeric VA/offset values come from ``tools/cerom.py`` and
``tools/sh4dis.py`` (EXP-2026-11-24-M1.52-testmode-gps-init). SH-4 code is
little-endian. This tool only encodes/decodes frames; it never opens or
writes a device. Stdlib only, no vendor bytes; ``--selftest`` is
auto-discovered by ``tools/selftest.py``.

Usage:
  gps_testmode_frames.py --selftest
  gps_testmode_frames.py --check date 26 11 22 11 36
  gps_testmode_frames.py --check latlon 52 13.8 N 21 0.6 E
  gps_testmode_frames.py frame A000013F2269004C7839000048F0
  gps_testmode_frames.py commands
"""
from __future__ import annotations

import argparse

DELIM = 0xF0
START_DATE = 0xA2
START_LATLON = 0xA0

DATE_VA = 0x00043DA8
LATLON_VA = 0x00043F70
COMMAND_VAS = {
    "B0_A3": (0x0004443C, 0xB0, 0x23, 0x04, 0x00, 0x27),
    "B0_A0": (0x00044494, 0xB0, 0x20, 0x02, 0x00, 0x22),
    "B3": (0x000444EC, 0xB3, 0x00, 0x00, 0x00, 0x00),
    "B4": (0x0004453C, 0xB4, 0x00, 0x00, 0x00, 0x00),
}


class FrameError(ValueError):
    """A frame failed framing or checksum validation."""


def checksum(data):
    """7-bit sum of the checksummed bytes (fn 0x43da8 / fn 0x43f70)."""
    return sum(data) & 0x7F


def date_frame(year, month, day, hour, minute):
    """Build the 10-byte date frame of fn 0x43da8 from the text fields."""
    fields = [year % 100, month - 1, day, hour, minute, 0, 0]
    if not all(0 <= value <= 99 for value in fields[:5]):
        raise FrameError("date field out of range")
    if not 0 <= fields[1] <= 11 or not 1 <= fields[2] <= 31:
        raise FrameError("date field out of range")
    return bytes([START_DATE] + fields + [checksum(fields), DELIM])


def scaled(degrees, minutes):
    """Text DDMM.mmmm to integer 1/1000 arc-minutes (fn 0x43f2c)."""
    if degrees < 0 or not 0 <= minutes < 60:
        raise FrameError("DD/MM out of range")
    return int((degrees * 60 + minutes) * 1000)


def latlon_frame(lat_deg, lat_min, ns, lon_deg, lon_min, ew):
    """Build the 14-byte position frame of fn 0x43f70."""
    if ns.upper() not in ("N", "S") or ew.upper() not in ("E", "W"):
        raise FrameError("hemisphere must be N/S and E/W")
    lat = scaled(lat_deg, lat_min)
    lon = scaled(lon_deg, lon_min)
    lat = (lat + 1 if ns.upper() == "N" else ~lat) & 0xFFFFFFFF
    lon = (lon + 1 if ew.upper() == "E" else ~lon) & 0xFFFFFFFF
    body = [
        0x00,
        (lat >> 21) & 0x7F, (lat >> 14) & 0x7F, (lat >> 7) & 0x7F, lat & 0x7F,
        (lon >> 21) & 0x7F, (lon >> 14) & 0x7F, (lon >> 7) & 0x7F, lon & 0x7F,
        0x00, 0x00,
    ]
    return bytes([START_LATLON] + body + [checksum(body), DELIM])


def command_frame(name):
    """Build the 6-byte constant command frame of one of the four setters."""
    if name not in COMMAND_VAS:
        raise FrameError("unknown command " + name)
    _, *body = COMMAND_VAS[name]
    return bytes(body) + bytes([checksum(body[1:])])


def check_frame(frame):
    """Validate framing, 7-bit payload and checksum; raise FrameError."""
    if len(frame) == 6:
        body = frame[:5]
        if body[0] not in (0xB0, 0xB3, 0xB4):
            raise FrameError("bad command byte")
        if any(byte & 0x80 for byte in body[1:]):
            raise FrameError("payload byte has bit 7 set")
        if body[5] != checksum(body[1:5]):
            raise FrameError("checksum mismatch")
        return frame
    if len(frame) not in (10, 14) or frame[-1] != DELIM:
        raise FrameError("bad length/end delimiter")
    if frame[0] not in (START_DATE, START_LATLON):
        raise FrameError("bad start byte")
    body = frame[1:-2]
    if any(byte & 0x80 for byte in body):
        raise FrameError("payload byte has bit 7 set")
    if frame[-2] != checksum(body):
        raise FrameError("checksum mismatch")
    return frame


def selftest():
    date = date_frame(26, 11, 22, 11, 36)
    assert date.hex().upper() == "A21A0A160B24000069F0", date.hex()
    assert check_frame(date) == date
    lat = latlon_frame(52, 13.8, "N", 21, 0.6, "E")
    assert lat.hex().upper() == "A000013F2269004C7839000048F0", lat.hex()
    assert check_frame(lat) == lat
    assert command_frame("B0_A3") == bytes.fromhex("B0230400274E")
    assert command_frame("B0_A0") == bytes.fromhex("B02002002244")
    assert command_frame("B3") == bytes.fromhex("B30000000000")
    assert command_frame("B4") == bytes.fromhex("B40000000000")
    bad = bytearray(lat)
    bad[-2] ^= 1
    try:
        check_frame(bytes(bad))
        raise AssertionError("mutated checksum accepted")
    except FrameError:
        pass
    bad = bytearray(lat)
    bad[2] |= 0x80
    try:
        check_frame(bytes(bad))
        raise AssertionError("bit 7 accepted")
    except FrameError:
        pass
    print("OK (10 checks)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    d = sub.add_parser("date")
    for name in ("year", "month", "day", "hour", "minute"):
        d.add_argument(name, type=int)
    p = sub.add_parser("latlon")
    p.add_argument("lat_deg", type=int)
    p.add_argument("lat_min", type=float)
    p.add_argument("ns")
    p.add_argument("lon_deg", type=int)
    p.add_argument("lon_min", type=float)
    p.add_argument("ew")
    sub.add_parser("frame").add_argument("hex")
    sub.add_parser("commands")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if args.cmd == "date":
        frame = date_frame(args.year, args.month, args.day, args.hour, args.minute)
    elif args.cmd == "latlon":
        frame = latlon_frame(args.lat_deg, args.lat_min, args.ns, args.lon_deg, args.lon_min, args.ew)
    elif args.cmd == "frame":
        frame = bytes.fromhex(args.hex)
    elif args.cmd == "commands":
        for name in COMMAND_VAS:
            print(name, hex(COMMAND_VAS[name][0]), command_frame(name).hex().upper())
        return
    else:
        ap.error("give --selftest, date, latlon, frame or commands")
    if args.check:
        check_frame(frame)
    print(frame.hex().upper())


if __name__ == "__main__":
    main()
