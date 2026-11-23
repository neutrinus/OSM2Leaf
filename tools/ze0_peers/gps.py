#!/usr/bin/env python3
"""GPS receiver peer for the QEMU ``ze0`` machine (TODO M8.H30, M8.H73).

The receiver on ``SCI7:`` speaks the 7-bit binary protocol documented in
``docs/firmware/navdrv.md`` (M8.H27), not NMEA::

    [start with bit 7 set] [payload ...] [sum(payload) & 0x7f] [0xf0]

Two length tables exist in ``navdrv.dll`` and they differ: frames the
receiver sends to the unit use the RX table at ``0x39e17e4`` (dispatch at
``0x39e42a4``), frames the unit sends to the receiver use the TX table at
``0x39e1808`` (dispatch at ``0x39e42e8``).  ``A0`` is 36 bytes on RX and
14 bytes on TX.

The position report is the receiver's 36-byte ``A0`` frame (M8.H73).  The
US ``Navi.exe`` build unpacks its 33-byte payload in function ``0x0039e880``
into a 48-byte record whose fields are named by the firmware's own debug
dump at ``0x003a12e8`` (format strings at ``0x0001e1c8`` and next to it):
status, latitude and longitude (signed 28-bit, 1/1000 arc-minute), height
in metres, speed in 0.1 km/h, heading in 0.1 degree, date and time, DOPs,
error ellipse, satellite count.  ``OBJ_GpsInfo`` (function ``0x00497aa0``)
multiplies latitude and longitude by 30.72, i.e. it turns 1/60000 degree
into 1/512 arc-second.  See ``docs/firmware/navdrv.md`` "Receiver frames".

The older ``A0 00`` 14-byte frame (C-8244, TestMode ``GpsDataSetLatLon``)
is a unit-to-receiver command; it is kept as ``encode_seed`` and is never
sent by the peer.

Usage:
  gps.py --selftest
  gps.py --socket PATH [--fix LAT,LON[,ALT]] [--speed KMH] [--heading DEG]
         [--time YYYY-MM-DDTHH:MM:SS] [--rate HZ] [--no-fix]
         [--control PATH] [--listen] [--duration S]
  gps.py replay track.gpx --rate 1 --socket PATH
  gps.py replay track.nmea --rate 1 --socket PATH
  gps.py decode HEX       # print the fields of one 36-byte A0 frame

Control socket lines (one per connection, reply ``OK ...`` or ``ERR ...``):
``gps LAT LON``, ``on``, ``no-fix``, ``speed KMH``, ``heading DEG``,
``alt M``, ``stat HEX``, ``sats N``, ``status``.

Stdlib only.  Method and results:
docs/experiments/EXP-2026-11-22-M8.H30-gps-peer.md,
docs/experiments/EXP-2026-11-23-M8.H73-receiver-fix-frame.md
"""

import argparse
import math
import os
import re
import select
import socket
import struct
import sys
import time
import xml.etree.ElementTree as ET

# From navdrv.dll sec0 file offset 0x4260200 + (0x39e1808 - 0x39e1000).
# Selector = table[start - 0xa0]; frame length = DISPATCH[selector // 4].
TX_SELECTORS = bytes.fromhex(
    "00 18 04 18 18 08 18 18 18 18 18 18 18 18 18 18 "
    "0c 14 10 14 14 18 18 18 18 18 18 18 18 18 18 18 14 14")
TX_DISPATCH = (14, 10, 8, 6, 44, 4, 0)   # indices 0..6 of the braf at 0x39e4302
# Receiver -> unit: table at 0x39e17e4, braf at 0x39e42ba.  81 is the
# variable-length marker (the walker at 0x39e4748 then searches for 0xf0).
RX_LENGTHS = {0xa0: 36, 0xa3: 81, 0xa4: 100, 0xa5: 8, 0xb0: 6, 0xb1: 4,
              0xb2: 44, 0xb3: 4, 0xb4: 10, 0xc0: 4, 0xc1: 4}
END = 0xF0
UNITS_PER_DEGREE = 60000                 # 1/1000 arc-minute, from fn 0x43f2c
OBJ_SCALE = 30.72                        # OBJ_GpsInfo: double at 0x00497c9c
# Status byte of the A0 report (payload[0]).  Bits 0-3 are flags, bits 4-6
# a mode that OBJ_GpsInfo maps to 1..7 (0x40 is rejected).  The locator's
# history ring (US Navi 0x0046fa60) keeps a report only when the whole byte
# is 0x00, 0x10, 0x20 or 0x30, so flag bits must be clear (M8.H78, C-8640).
# 0x2f (the M8.H73 value) reaches OBJ_GpsInfo but never the locator.
DEFAULT_STAT = 0x30


def frame_length(start):
    """Bytes in a unit-to-receiver frame beginning with ``start`` (TX table)."""
    if not 0xa0 <= start <= 0xc1:
        return 0
    sel = TX_SELECTORS[start - 0xa0] // 4
    return TX_DISPATCH[sel] if sel < len(TX_DISPATCH) else 0


def rx_length(start):
    """Bytes in a receiver-to-unit frame beginning with ``start`` (RX table)."""
    return RX_LENGTHS.get(start, 0)


def checksum(payload):
    """The 7-bit sum the driver's validator at leaf 0x39e4248 compares."""
    return sum(payload) & 0x7f


def encode_frame(start, command, data=(), rx=False):
    """Build one frame; raises ValueError for illegal markers or 8-bit bytes.

    ``rx=True`` sizes it with the receiver-to-unit table (what the peer
    sends); the default is the unit-to-receiver table (what the guest sends).
    """
    n = rx_length(start) if rx else frame_length(start)
    if n < 4 or n == 81:
        raise ValueError("start byte 0x%02x has no fixed frame length" % start)
    if (command & 0x80) or any(b & 0x80 for b in data):
        raise ValueError("payload bytes must be 7-bit clean")
    body = [command & 0x7f] + [b & 0x7f for b in data]
    # start + body + checksum + end = n  =>  len(body) = n - 3
    if len(body) > n - 3:
        raise ValueError("payload too long: %d > %d" % (len(body), n - 3))
    body += [0] * (n - 3 - len(body))
    return bytes([start] + body + [checksum(body), END])


def verify_frame(frame, rx=False):
    """Validate a frame the way navdrv.dll does.  No side effects."""
    if len(frame) < 4 or not (frame[0] & 0x80):
        return False
    if frame[-1] & 0xf0 != END:
        return False
    n = rx_length(frame[0]) if rx else frame_length(frame[0])
    if n not in (0, 81, len(frame)):
        return False
    if any(b & 0x80 for b in frame[1:-2]):
        return False
    return checksum(frame[1:-2]) == frame[-2]


def _units(degrees):
    """Decimal degrees -> signed 28-bit 1/1000-arc-minute integer."""
    v = int(round(degrees * UNITS_PER_DEGREE))
    if not -(1 << 27) <= v < (1 << 27):
        raise ValueError("coordinate out of the 28-bit range: %r" % degrees)
    return v & 0x0FFFFFFF


def _pack7(value, nbytes):
    """Big-endian 7-bit groups, as the decoder's shift loop reads them."""
    return [(value >> (7 * (nbytes - 1 - i))) & 0x7f for i in range(nbytes)]


def _unpack7(data, signed_bits=None):
    v = 0
    for b in data:
        v = (v << 7) | (b & 0x7f)
    if signed_bits and v & (1 << (signed_bits - 1)):
        v -= 1 << signed_bits
    return v


def _seven_bit_words(value):
    return _pack7(value, 4)


def encode_seed(lat, lon, alt=None):
    """TestMode's unit-to-receiver ``A0 00`` position seed (C-8244).

    Kept for reference and tests only: the receiver never sends it, and
    navdrv's RX side would reject it (RX ``A0`` frames are 36 bytes)."""
    body = [0x00] + _seven_bit_words(_units(lat)) + _seven_bit_words(_units(lon))
    if alt is not None:
        body += [int(alt) & 0x7f, (int(alt) >> 7) & 0x7f]
    else:
        body += [0x00, 0x00]
    return encode_frame(0xa0, body[0], body[1:])


def decode_seed(frame):
    """Inverse of encode_seed; returns (lat, lon, raw_altitude)."""
    f = verify_frame(frame) and frame
    if not f or f[0] != 0xa0 or f[1] != 0x00 or len(f) != 14:
        raise ValueError("not an A0 00 seed frame")
    words = f[2:10]
    return (_unpack7(words[:4], 28) / UNITS_PER_DEGREE,
            _unpack7(words[4:8], 28) / UNITS_PER_DEGREE,
            f[10] | (f[11] << 7))


# Payload of the receiver's 36-byte A0 report: (name, first byte, bytes,
# signed bits or None, record offset in Navi's 48-byte record, unit).  From
# the US Navi.exe decoder 0x0039e880 and the debug dump 0x003a12e8.
REPORT_FIELDS = (
    ("stat", 0, 1, None, 0, "flags/mode"),
    ("lat", 1, 4, 28, 4, "1/1000 arc-min"),
    ("lon", 5, 4, 28, 8, "1/1000 arc-min"),
    ("high", 9, 2, 14, 12, "m"),
    ("sp", 11, 2, None, 14, "0.1 km/h"),
    ("dir", 13, 2, None, 16, "0.1 deg"),
    ("year", 15, 1, None, 18, "2 digits (<90: 20yy, else 19yy)"),
    ("month", 16, 1, None, 20, ""),
    ("day", 17, 1, None, 22, ""),
    ("hour", 18, 1, None, 24, "UTC"),
    ("minute", 19, 1, None, 26, ""),
    ("second", 20, 1, None, 28, ""),
    ("hdop", 21, 1, None, 30, "0.2"),
    ("vdop", 22, 1, None, 32, "0.2"),
    ("pdop", 23, 1, None, 34, "0.2"),
    ("long_err", 24, 2, None, 36, "m"),
    ("short_err", 26, 2, None, 38, "m"),
    ("slant", 28, 1, None, 40, "180/128 deg"),
    ("sats", 29, 1, None, 42, "count"),
    ("wsvacc", 30, 1, None, 44, ""),
    ("delay", 32, 1, None, 46, "0.1 s"),
)
REPORT_PAYLOAD = 33          # 36 - start - checksum - end


def encode_report(lat, lon, alt=0, speed_kmh=0.0, heading=0.0, when=None,
                  stat=DEFAULT_STAT, sats=8, hdop=5, vdop=5, pdop=5,
                  long_err=10, short_err=10, slant=0, wsvacc=0, delay=0):
    """The receiver's 36-byte ``A0`` position report (M8.H73)."""
    if when is None:
        when = time.gmtime()
    elif isinstance(when, str):
        m = re.match(r"(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d):(\d\d)", when)
        if not m:
            raise ValueError("time must be YYYY-MM-DDTHH:MM:SS")
        when = time.struct_time(tuple(int(x) for x in m.groups()) + (0, 0, 0))
    vals = {
        "stat": stat & 0x7f, "lat": _units(lat), "lon": _units(lon),
        "high": int(round(alt)) & 0x3fff,
        "sp": int(round(speed_kmh * 10)) & 0x3fff,
        "dir": int(round((heading % 360.0) * 10)) & 0x3fff,
        "year": when.tm_year % 100, "month": when.tm_mon, "day": when.tm_mday,
        "hour": when.tm_hour, "minute": when.tm_min, "second": when.tm_sec,
        "hdop": hdop, "vdop": vdop, "pdop": pdop,
        "long_err": long_err, "short_err": short_err, "slant": slant,
        "sats": sats, "wsvacc": wsvacc, "delay": delay,
    }
    payload = [0] * REPORT_PAYLOAD
    for name, first, n, _sb, _off, _unit in REPORT_FIELDS:
        payload[first:first + n] = _pack7(vals[name], n)
    return encode_frame(0xa0, payload[0], payload[1:], rx=True)


def decode_report(frame):
    """Fields of a 36-byte A0 report, decoded as Navi.exe 0x0039e880 does."""
    f = bytes(frame)
    if len(f) != 36 or f[0] != 0xa0 or not verify_frame(f, rx=True):
        raise ValueError("not a valid 36-byte A0 report")
    p = f[1:1 + REPORT_PAYLOAD]
    out = {}
    for name, first, n, sb, _off, _unit in REPORT_FIELDS:
        out[name] = _unpack7(p[first:first + n], sb) if n > 1 else p[first]
    out["lat_deg"] = out["lat"] / UNITS_PER_DEGREE
    out["lon_deg"] = out["lon"] / UNITS_PER_DEGREE
    out["obj_lat"] = int(out["lat"] * OBJ_SCALE)
    out["obj_lon"] = int(out["lon"] * OBJ_SCALE)
    return out


# --------------------------------------------------------------------------
# Tracks
# --------------------------------------------------------------------------

def parse_gpx(path):
    root = ET.parse(path).getroot()
    ns = "{http://www.topografix.com/GPX/1/1}"
    points = []
    for pt in root.iter():
        if pt.tag in (ns + "trkpt", "trkpt", ns + "wpt", "wpt"):
            points.append((float(pt.attrib["lat"]), float(pt.attrib["lon"])))
    if not points:
        raise ValueError("no <trkpt>/<wpt> in %s" % path)
    return points


def parse_nmea(path):
    points = []
    with open(path, encoding="ascii", errors="replace") as fh:
        for line in fh:
            if not line.startswith("$"):
                continue
            parts = line.strip().split(",")
            if parts[0] in ("$GPRMC", "$GNRMC") and len(parts) > 6 and parts[6]:
                lat = _nmea_coord(parts[3], parts[4])
                lon = _nmea_coord(parts[5], parts[6])
                if lat is not None and lon is not None:
                    points.append((lat, lon))
            elif parts[0] in ("$GPGGA", "$GNGGA") and len(parts) > 5:
                lat = _nmea_coord(parts[2], parts[3])
                lon = _nmea_coord(parts[4], parts[5])
                if lat is not None and lon is not None:
                    points.append((lat, lon))
    if not points:
        raise ValueError("no position sentence in %s" % path)
    return points


def _nmea_coord(value, hemi):
    if not value or not hemi:
        return None
    deg = float(value[:2] if hemi in "NS" else value[:3])
    minutes = float(value[2:] if hemi in "NS" else value[3:])
    v = deg + minutes / 60.0
    return -v if hemi in "SW" else v


def interpolate(points, rate, count=None):
    """Yield (seconds, lat, lon) at ``rate`` Hz between the given points."""
    if len(points) < 2:
        yield 0.0, points[0][0], points[0][1]
        return
    out = []
    for a, b in zip(points, points[1:]):
        steps = max(2, int(math.ceil(1.0 / rate)))
        for i in range(steps):
            t = i / float(steps)
            out.append((a[0] + (b[0] - a[0]) * t,
                        a[1] + (b[1] - a[1]) * t))
    out.append(points[-1])
    for i, (lat, lon) in enumerate(out):
        yield i / float(rate), lat, lon
        if count is not None and i + 1 >= count:
            break


# --------------------------------------------------------------------------
# I/O and control
# --------------------------------------------------------------------------

class Sink:
    def __init__(self, path=None, listen=False, timeout=5.0):
        self.sock = None
        self.server = None
        if not path:
            return
        if listen:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server.bind(path)
            self.server.listen(1)
            self.server.settimeout(timeout)
            self.sock, _ = self.server.accept()
        else:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.settimeout(timeout)
            self.sock.connect(path)

    def send(self, data):
        if self.sock is not None:
            self.sock.sendall(data)
        return data.hex()

    def close(self):
        for s in (self.sock, self.server):
            if s is not None:
                s.close()


def control_commands(line, state):
    """Apply one control line; returns a reply string."""
    parts = line.strip().split()
    if not parts:
        return ""
    cmd = parts[0].lower()
    try:
        if cmd in ("gps", "fix") and len(parts) >= 3:
            state["lat"], state["lon"] = float(parts[1]), float(parts[2])
            _units(state["lat"]), _units(state["lon"])
            return "fix %.6f %.6f" % (state["lat"], state["lon"])
        if cmd in ("no-fix", "nofix"):
            state["fix"] = False
            return "no-fix"
        if cmd == "on":
            state["fix"] = True
            return "on"
        if cmd == "speed" and len(parts) == 2:
            state["speed"] = float(parts[1])
            return "speed %g" % state["speed"]
        if cmd == "heading" and len(parts) == 2:
            state["heading"] = float(parts[1])
            return "heading %g" % state["heading"]
        if cmd == "alt" and len(parts) == 2:
            state["alt"] = float(parts[1])
            return "alt %g" % state["alt"]
        if cmd == "stat" and len(parts) == 2:
            state["stat"] = int(parts[1], 16) & 0x7f
            return "stat %02x" % state["stat"]
        if cmd == "sats" and len(parts) == 2:
            state["sats"] = int(parts[1]) & 0x7f
            return "sats %d" % state["sats"]
        if cmd == "status":
            return "status %s lat=%s lon=%s stat=%02x sent=%d" % (
                "fix" if state["fix"] else "no-fix", state["lat"], state["lon"],
                state.get("stat", DEFAULT_STAT), state.get("sent", 0))
    except ValueError as exc:
        return "ERR %s" % exc
    return "ERR unknown command: %s" % cmd


def state_frames(state, text_time=None):
    """Frames for one report period: one 36-byte A0 report, or nothing."""
    if not state["fix"] or state.get("lat") is None:
        return []
    return [encode_report(state["lat"], state["lon"],
                          alt=state.get("alt") or 0,
                          speed_kmh=state.get("speed") or 0.0,
                          heading=state.get("heading") or 0.0,
                          when=text_time,
                          stat=state.get("stat", DEFAULT_STAT),
                          sats=state.get("sats", 8))]


def run(args):
    sink = Sink(args.socket, args.listen)
    state = {"fix": not args.no_fix, "lat": None, "lon": None, "alt": None,
             "speed": args.speed, "heading": args.heading,
             "stat": DEFAULT_STAT, "sats": 8, "sent": 0}
    if args.fix:
        vals = args.fix.split(",")
        state["lat"], state["lon"] = float(vals[0]), float(vals[1])
        state["alt"] = float(vals[2]) if len(vals) > 2 else None
    ctrl = None
    if args.control:
        try:
            os.unlink(args.control)
        except FileNotFoundError:
            pass
        ctrl = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        ctrl.bind(args.control)
        ctrl.listen(1)
        ctrl.settimeout(0.1)

    try:
        if args.replay:
            points = (parse_gpx(args.replay) if args.replay.endswith(".gpx")
                      else parse_nmea(args.replay))
            prev = None
            for _sec, lat, lon in interpolate(points, args.rate):
                heading = 0.0 if prev is None else _bearing(prev, (lat, lon))
                speed = 0.0 if prev is None else \
                    _distance_m(prev, (lat, lon)) * args.rate * 3.6
                prev = (lat, lon)
                hexdata = sink.send(encode_report(lat, lon, speed_kmh=speed,
                                                  heading=heading))
                print("gps: %s" % hexdata, flush=True)
                time.sleep(1.0 / args.rate)
            return 0
        deadline = (time.monotonic() + args.duration) if args.duration > 0 \
            else float("inf")
        next_tx = 0.0
        while time.monotonic() < deadline:
            if ctrl is not None:
                ready, _, _ = select.select([ctrl], [], [], 0)
                if ready:
                    conn, _ = ctrl.accept()
                    with conn:
                        line = conn.recv(1024).decode("utf-8", "replace")
                        reply = control_commands(line, state)
                        print("gps: control %s -> %s" % (line.strip(), reply),
                              flush=True)
                        try:
                            conn.sendall(("%s %s\n" % (
                                "ERR" if reply.startswith("ERR") else "OK",
                                reply.replace("ERR ", "", 1))).encode())
                        except OSError:
                            pass
                        next_tx = 0.0
            if time.monotonic() >= next_tx:
                for f in state_frames(state, args.time):
                    print("gps: %s" % sink.send(f), flush=True)
                    state["sent"] += 1
                next_tx = time.monotonic() + (1.0 / args.rate)
            time.sleep(0.01)
        return 0
    finally:
        sink.close()
        if ctrl is not None:
            ctrl.close()


def _bearing(a, b):
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlon = math.radians(b[1] - a[1])
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return math.degrees(math.atan2(y, x)) % 360.0


def _distance_m(a, b):
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------

def selftest():
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" %
              ("ok  " if ok else "FAIL", label, got, want))

    # The example of docs/firmware/navdrv.md, byte for byte.
    check("doc example b0 20", encode_frame(0xb0, 0x20, [0x02, 0x00]).hex(),
          "b020020022f0")
    check("doc example b0 23", encode_frame(0xb0, 0x23, [0x02, 0x00]).hex(),
          "b023020025f0")
    check("example validates", verify_frame(bytes.fromhex("b020020022f0")), True)
    # Negative controls: a wrong checksum and a wrong terminator must fail.
    check("wrong checksum rejected",
          verify_frame(bytes.fromhex("b020020023f0")), False)
    check("wrong terminator rejected",
          verify_frame(bytes.fromhex("b0200200220f")), False)
    check("8-bit payload rejected",
          _raises(lambda: encode_frame(0xb0, 0x20, [0x80])), True)
    check("illegal start rejected",
          _raises(lambda: encode_frame(0xa1, 0x00)), True)
    check("B0 length from table", frame_length(0xb0), 6)
    check("A0 TX length (unit -> receiver)", frame_length(0xa0), 14)
    check("A0 RX length (receiver -> unit)", rx_length(0xa0), 36)

    # The 36-byte report: decoded the way Navi.exe 0x0039e880 does it.
    t = "2026-11-23T12:34:56"
    for lat, lon in ((51.1079, 17.0385), (37.4058806, -84.4876444),
                     (-33.8688, 151.2093), (0.0, 0.0), (-0.5, -179.9)):
        f = encode_report(lat, lon, alt=-12, speed_kmh=48.3, heading=271.5,
                          when=t)
        r = decode_report(f)
        check("report %.4f,%.4f length/valid" % (lat, lon),
              (len(f), verify_frame(f, rx=True), all(b < 0x80 for b in f[1:-2])),
              (36, True, True))
        check("report %.4f,%.4f position" % (lat, lon),
              abs(r["lat_deg"] - lat) < 2e-5 and abs(r["lon_deg"] - lon) < 2e-5,
              True)
        check("report %.4f,%.4f other fields" % (lat, lon),
              (r["high"], r["sp"], r["dir"], r["year"], r["month"], r["day"],
               r["hour"], r["minute"], r["second"], r["stat"], r["sats"]),
              (-12, 483, 2715, 26, 11, 23, 12, 34, 56, DEFAULT_STAT, 8))
    # Firmware arithmetic: 28-bit value << 4, then shad -4 (sign extension).
    f = encode_report(37.4058806, -84.4876444, when=t)
    raw = 0
    for b in f[6:10]:
        raw = (raw << 7) | b
    fw = ((raw << 4) & 0xffffffff)
    fw = (fw - (1 << 32) if fw & 0x80000000 else fw) >> 4
    check("lon sign via shad -4", fw, int(round(-84.4876444 * 60000)))
    check("OBJ_GpsInfo scale 51.5 deg", decode_report(
        encode_report(51.5, 0.0, when=t))["obj_lat"], 51 * 1843200 + 921600)
    # One pinned vector so a layout change is visible in review.
    check("pinned report vector",
          encode_report(51.5, -0.25, alt=20, speed_kmh=0, heading=0, when=t,
                        stat=0x2f, sats=7).hex(),
          "a02f013c4c507f7f0a680014000000001a0b170c2238050505000a000a00"
          "0700000058f0")
    # Negative controls: the 14-byte seed is not a valid RX frame, and a
    # report with a wrong checksum or an 8-bit payload byte is rejected.
    check("14-byte A0 rejected on RX", verify_frame(encode_seed(51.5, 0.0), rx=True), False)
    bad = bytearray(encode_report(51.5, 0.0, when=t))
    bad[-2] ^= 1
    check("report wrong checksum rejected", verify_frame(bytes(bad), rx=True), False)
    bad = bytearray(encode_report(51.5, 0.0, when=t))
    bad[3] |= 0x80
    check("report 8-bit byte rejected", verify_frame(bytes(bad), rx=True), False)
    check("out-of-range coordinate rejected",
          _raises(lambda: encode_report(3000.0, 0.0, when=t)), True)
    # The seed command still round-trips (unit -> receiver, reference only).
    for lat, lon in ((52.23, 21.01), (37.4058806, -84.4876444)):
        back = decode_seed(encode_seed(lat, lon))
        check("seed round-trip %.4f,%.4f" % (lat, lon),
              abs(back[0] - lat) < 3e-5 and abs(back[1] - lon) < 3e-5, True)
    check("random report round-trip", _random_roundtrip(), True)

    # A three-point GPX track must produce interpolated frames, not the
    # original points repeated; the middle sample is between its neighbours.
    import tempfile
    gpx = ('<gpx xmlns="http://www.topografix.com/GPX/1/1">'
           '<trk><trkseg>'
           '<trkpt lat="52.00" lon="21.00"/>'
           '<trkpt lat="52.10" lon="21.20"/>'
           '<trkpt lat="52.20" lon="21.40"/>'
           '</trkseg></trk></gpx>')
    with tempfile.TemporaryDirectory(prefix="gps-peer-") as td:
        path = os.path.join(td, "track.gpx")
        with open(path, "w", encoding="ascii") as fh:
            fh.write(gpx)
        pts = parse_gpx(path)
        check("gpx points", pts, [(52.0, 21.0), (52.1, 21.2), (52.2, 21.4)])
        samples = list(interpolate(pts, 2.0))
        check("gpx sample count", len(samples), 5)
        check("gpx first sample", samples[0][1:], (52.0, 21.0))
        check("gpx last sample", samples[-1][1:], (52.2, 21.4))
        mid = samples[2][1]
        check("gpx middle interpolated", 52.0 < mid < 52.2, True)
        frames = [encode_report(lat, lon, when=t) for _, lat, lon in samples]
        check("gpx frames all valid",
              all(verify_frame(f, rx=True) for f in frames), True)
        check("gpx frames differ", len(set(frames)), len(frames))
        nmea = os.path.join(td, "track.nmea")
        with open(nmea, "w", encoding="ascii") as fh:
            fh.write("$GPRMC,120000,A,5221.0000,N,02101.0000,E,,,0,0,120100,,A*00\n")
        check("nmea point", [tuple(round(x, 4) for x in p)
                             for p in parse_nmea(nmea)], [(52.35, 21.0167)])

    st = {"fix": True, "lat": 52.23, "lon": 21.01, "alt": 100,
          "speed": 30.0, "heading": 90.0}
    fr = state_frames(st, "2026-11-22T12:00:00")
    check("state emits one A0 report", [len(x) for x in fr], [36])
    check("state report carries speed/heading",
          (decode_report(fr[0])["sp"], decode_report(fr[0])["dir"]), (300, 900))
    check("control stat", control_commands("stat 3f", st), "stat 3f")
    check("control bad coordinate", control_commands("gps 3000 0", st).startswith("ERR"), True)
    check("no-fix emits nothing", state_frames(dict(st, fix=False)), [])
    check("control fix", control_commands("gps 50 20", st), "fix 50.000000 20.000000")
    check("control no-fix", control_commands("no-fix", st), "no-fix")
    check("control unknown", control_commands("wat", st).startswith("ERR"), True)

    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def _raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


def _random_roundtrip():
    import random
    rng = random.Random(1234)
    for _ in range(50):
        lat = rng.uniform(-89, 89)
        lon = rng.uniform(-179, 179)
        r = decode_report(encode_report(lat, lon, when="2026-01-01T00:00:00"))
        if abs(r["lat_deg"] - lat) >= 2e-5 or abs(r["lon_deg"] - lon) >= 2e-5:
            return False
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--socket", help="AF_UNIX socket of the --serial-peer chardev")
    ap.add_argument("--listen", action="store_true",
                    help="bind the socket as a server (QEMU connects)")
    ap.add_argument("--fix", help="LAT,LON[,ALT] in decimal degrees")
    ap.add_argument("--speed", type=float, help="speed in km/h (A0 report field)")
    ap.add_argument("--heading", type=float, help="heading in degrees (A0 report field)")
    ap.add_argument("--time", help="YYYY-MM-DDTHH:MM:SS UTC for the report (default: now)")
    ap.add_argument("--no-fix", action="store_true", help="send nothing until controlled")
    ap.add_argument("--rate", type=float, default=1.0, help="frames per second")
    ap.add_argument("--duration", type=float, default=0.0,
                    help="seconds to run; 0 (default) runs until killed")
    ap.add_argument("--control", help="AF_UNIX control socket for ze0_ui.py")
    ap.add_argument("--selftest-only", action="store_true", help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd")
    dp = sub.add_parser("decode", help="print the fields of a 36-byte A0 report")
    dp.add_argument("hex")
    rp = sub.add_parser("replay")
    rp.add_argument("file", help="GPX or NMEA track")
    rp.add_argument("--rate", type=float, default=1.0)
    rp.add_argument("--socket")
    rp.add_argument("--listen", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest or args.selftest_only:
        return selftest()
    if args.cmd == "decode":
        for k, v in decode_report(bytes.fromhex(args.hex.replace(" ", ""))).items():
            print("%-10s %s" % (k, v))
        return 0
    if args.cmd == "replay":
        args.replay = args.file
        # subparser options override the globals when explicitly given
        if args.socket is None:
            args.socket = None
        return run(args)
    args.replay = None
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
