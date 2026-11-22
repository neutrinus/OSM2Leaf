#!/usr/bin/env python3
"""GPS receiver peer for the QEMU ``ze0`` machine (TODO M8.H30).

The receiver on ``SCI7:`` speaks the 7-bit binary protocol documented in
``docs/firmware/navdrv.md`` (M8.H27), not NMEA::

    [start with bit 7 set] [command/payload ...] [sum(payload) & 0x7f] [0xf0]

Frame lengths come from the driver's TX selector table at ``0x39e1808`` with
the dispatch at ``0x39e42e8`` (EU2011; US2011 byte-identical).  The two frames
captured from the guest in EXP-2026-11-22-M8.H1 O7 are reproduced exactly by
``encode_frame(0xb0, 0x20, [0x02, 0x00])`` and its ``0x23`` variant.

``--fix`` uses the ``A0 00`` position frame of C-8244 (TestMode's
``GpsDataSetLatLon``): latitude and longitude are 28-bit integers in
1/1000 arc-minute units, split into four 7-bit bytes each, most significant
first, negative values two's-complemented.  Altitude, speed and heading have
no confirmed command in ``navdrv.dll``; the frames they produce are marked
HYPOTHESIS in the EXP and must not be used as evidence of firmware behaviour.
The receiver's own fix frames are still unknown (M8.H29/M8.H31).

Usage:
  gps.py --selftest
  gps.py --socket PATH [--fix LAT,LON[,ALT]] [--speed KMH] [--heading DEG]
         [--time YYYY-MM-DDTHH:MM:SS] [--rate HZ] [--no-fix]
         [--control PATH] [--listen]
  gps.py replay track.gpx --rate 1 --socket PATH
  gps.py replay track.nmea --rate 1 --socket PATH

Stdlib only.  Method and results:
docs/experiments/EXP-2026-11-22-M8.H30-gps-peer.md
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
END = 0xF0
UNITS_PER_DEGREE = 60000                 # 1/1000 arc-minute, from fn 0x43f2c


def frame_length(start):
    """Bytes in a frame beginning with ``start`` (0 for an illegal byte)."""
    if not 0xa0 <= start <= 0xc1:
        return 0
    sel = TX_SELECTORS[start - 0xa0] // 4
    return TX_DISPATCH[sel] if sel < len(TX_DISPATCH) else 0


def checksum(payload):
    """The 7-bit sum the driver's validator at leaf 0x39e4248 compares."""
    return sum(payload) & 0x7f


def encode_frame(start, command, data=()):
    """Build one frame; raises ValueError for illegal markers or 8-bit bytes."""
    n = frame_length(start)
    if n < 4:
        raise ValueError("start byte 0x%02x has no frame length" % start)
    if (command & 0x80) or any(b & 0x80 for b in data):
        raise ValueError("payload bytes must be 7-bit clean")
    body = [command & 0x7f] + [b & 0x7f for b in data]
    # start + body + checksum + end = n  =>  len(body) = n - 3
    if len(body) > n - 3:
        raise ValueError("payload too long: %d > %d" % (len(body), n - 3))
    body += [0] * (n - 3 - len(body))
    return bytes([start] + body + [checksum(body), END])


def verify_frame(frame):
    """Validate a received frame the way navdrv.dll does.  No side effects."""
    if len(frame) < 4 or not (frame[0] & 0x80):
        return False
    if frame[-1] & 0xf0 != END:
        return False
    if frame_length(frame[0]) not in (0, len(frame)):
        return False
    if any(b & 0x80 for b in frame[1:-2]):
        return False
    return checksum(frame[1:-2]) == frame[-2]


def _units(degrees):
    """Decimal degrees -> signed 28-bit 1/1000-arc-minute integer."""
    v = int(round(degrees * UNITS_PER_DEGREE))
    return v & 0x0FFFFFFF


def _seven_bit_words(value):
    return [(value >> shift) & 0x7f for shift in (21, 14, 7, 0)]


def encode_fix(lat, lon, alt=None):
    """The A0 00 position frame (C-8244); altitude is HYPOTHESIS."""
    body = [0x00] + _seven_bit_words(_units(lat)) + _seven_bit_words(_units(lon))
    if alt is not None:
        body += [int(alt) & 0x7f, (int(alt) >> 7) & 0x7f]
    else:
        body += [0x00, 0x00]
    return encode_frame(0xa0, body[0], body[1:])


def decode_fix(frame):
    """Inverse of encode_fix; returns (lat, lon, raw_altitude)."""
    f = verify_frame(frame) and frame
    if not f or f[0] != 0xa0 or f[1] != 0x00 or len(f) != 14:
        raise ValueError("not an A0 00 position frame")
    words = f[2:10]

    def value(words):
        v = 0
        for b in words:
            v = (v << 7) | b
        if v & 0x08000000:
            v -= 0x10000000
        return v

    return (value(words[:4]) / UNITS_PER_DEGREE,
            value(words[4:8]) / UNITS_PER_DEGREE,
            f[10] | (f[11] << 7))


def encode_time(text):
    """B3 frame carrying a date; command semantics are HYPOTHESIS."""
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d):(\d\d)", text)
    if not m:
        raise ValueError("time must be YYYY-MM-DDTHH:MM:SS")
    vals = [int(x) for x in m.groups()]
    payload = [x % 100 for x in vals[2:]] + [vals[0] % 100, vals[1] % 100]
    # A0 00 is the position command, so use A0 01 for the date variant;
    # navdrv's B3 frame is only 4 bytes and cannot carry a date.
    return encode_frame(0xa0, 0x01, payload)


def encode_speed(kmh):
    """B0 20 frame; speed scaling is HYPOTHESIS."""
    return encode_frame(0xb0, 0x20, [int(kmh) & 0x7f, (int(kmh) >> 7) & 0x7f])


def encode_heading(deg):
    """B0 23 frame; heading scaling is HYPOTHESIS."""
    return encode_frame(0xb0, 0x23, [int(deg) & 0x7f, (int(deg) >> 7) & 0x7f])


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
    if cmd in ("gps", "fix") and len(parts) >= 3:
        state["lat"], state["lon"] = float(parts[1]), float(parts[2])
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
    if cmd == "status":
        return "status %s lat=%s lon=%s" % (
            "fix" if state["fix"] else "no-fix", state["lat"], state["lon"])
    return "ERR unknown command: %s" % cmd


def state_frames(state, text_time=None):
    if not state["fix"]:
        return []
    frames = [encode_fix(state["lat"], state["lon"], state.get("alt"))]
    if text_time:
        frames.append(encode_time(text_time))
    if state.get("speed") is not None:
        frames.append(encode_speed(state["speed"]))
    if state.get("heading") is not None:
        frames.append(encode_heading(state["heading"]))
    return frames


def run(args):
    sink = Sink(args.socket, args.listen)
    state = {"fix": not args.no_fix, "lat": None, "lon": None, "alt": None,
             "speed": args.speed, "heading": args.heading}
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
            for _sec, lat, lon in interpolate(points, args.rate):
                hexdata = sink.send(encode_fix(lat, lon))
                print("gps: %s" % hexdata)
                time.sleep(1.0 / args.rate)
            return 0
        deadline = time.monotonic() + args.duration
        next_tx = 0.0
        while time.monotonic() < deadline:
            if ctrl is not None:
                ready, _, _ = select.select([ctrl], [], [], 0)
                if ready:
                    conn, _ = ctrl.accept()
                    with conn:
                        line = conn.recv(1024).decode("utf-8", "replace")
                        print("gps: control %s -> %s" %
                              (line.strip(), control_commands(line, state)))
            if state["fix"] and state["lat"] is not None and \
                    time.monotonic() >= next_tx:
                for f in state_frames(state, args.time):
                    print("gps: %s" % sink.send(f))
                next_tx = time.monotonic() + (1.0 / args.rate)
            time.sleep(0.01)
        return 0
    finally:
        sink.close()
        if ctrl is not None:
            ctrl.close()


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
    check("A0 length from table", frame_length(0xa0), 14)

    # Position frames round-trip; the Wrocław point of C-8248 is a good span.
    for lat, lon in ((52.23, 21.01), (-33.8688, 151.2093),
                     (37.4058806, -84.4876444), (0.0, 0.0)):
        f = encode_fix(lat, lon)
        back = decode_fix(f)
        # 1/1000 arc-minute ~= 1.7e-5 degrees, so 4 decimal places can differ
        # by one unit; compare with a tolerance instead of exact rounding.
        check("fix round-trip %.4f,%.4f" % (lat, lon),
              abs(back[0] - lat) < 3e-5 and abs(back[1] - lon) < 3e-5, True)
    check("random fix round-trip", _random_roundtrip(), True)

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
        frames = [encode_fix(lat, lon) for _, lat, lon in samples]
        check("gpx frames all valid", all(verify_frame(f) for f in frames), True)
        check("gpx frames differ", len(set(frames)), len(frames))
        nmea = os.path.join(td, "track.nmea")
        with open(nmea, "w", encoding="ascii") as fh:
            fh.write("$GPRMC,120000,A,5221.0000,N,02101.0000,E,,,0,0,120100,,A*00\n")
        check("nmea point", [tuple(round(x, 4) for x in p)
                             for p in parse_nmea(nmea)], [(52.35, 21.0167)])

    st = {"fix": True, "lat": 52.23, "lon": 21.01, "alt": 100,
          "speed": 30.0, "heading": 90.0}
    check("state emits all frame types", len(state_frames(st, "2026-11-22T12:00:00")), 4)
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
        back = decode_fix(encode_fix(lat, lon))
        if abs(back[0] - lat) >= 3e-5 or abs(back[1] - lon) >= 3e-5:
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
    ap.add_argument("--speed", type=float, help="speed in km/h (HYPOTHESIS frame)")
    ap.add_argument("--heading", type=float, help="heading in degrees (HYPOTHESIS frame)")
    ap.add_argument("--time", help="YYYY-MM-DDTHH:MM:SS (HYPOTHESIS frame)")
    ap.add_argument("--no-fix", action="store_true", help="send nothing until controlled")
    ap.add_argument("--rate", type=float, default=1.0, help="frames per second")
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--control", help="AF_UNIX control socket for ze0_ui.py")
    ap.add_argument("--selftest-only", action="store_true", help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd")
    rp = sub.add_parser("replay")
    rp.add_argument("file", help="GPX or NMEA track")
    rp.add_argument("--rate", type=float, default=1.0)
    rp.add_argument("--socket")
    rp.add_argument("--listen", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest or args.selftest_only:
        return selftest()
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
