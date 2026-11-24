#!/usr/bin/env python3
"""VCAN vehicle peer for the QEMU ``ze0`` machine (TODO M8.H50).

The peer models the VCAN sub-microcontroller behind ``UAT3:``.  Its state is
ignition, speed, reverse, lights and state of charge; a periodic sender emits
the frames of ``docs/firmware/can.md`` and a control socket lets
``tools/ze0_ui.py`` change the state.

**Honest scope.**  M8.H49 established the decoded CAN object
(``can_id`` u32 + 8 data bytes, see ``can.md`` §3) and the 17 frame ids, but
the byte grammar on the wire is UNKNOWN (C-7469).  Therefore this peer sends
the *decoded-layer* record ``u32 LE can_id || 8 bytes``.  It is a **model**,
not a byte-exact emulation of the sub-microcontroller: do not use its bytes
as evidence of firmware behaviour until an L4 ``uat3`` trace pins the wire
framing.  Field offsets/scale marks below are HYPOTHESIS where M8.H49 did not
recover them.

Usage:
  vcan.py --selftest
  vcan.py --socket PATH --listen [--control PATH] [--rate HZ] [--seconds S]

Stdlib only.  Method and results:
docs/experiments/EXP-2026-11-22-M8.H50-vcan-peer.md
"""

from __future__ import annotations

import argparse
import os
import select
import socket
import struct
import sys
import time
from pathlib import Path

import peerlib  # noqa: E402  (shared control-socket accept loop)

# The 17 decoded CAN ids subscribed by Vehicle.exe (docs/firmware/can.md §4).
FRAMES = {
    0x180: "ECM_TorqueControl_RN1",
    0x260: "VCM_HMI_GeneralData4",
    0x280: "CLUSTER_BasicInfo_1",
    0x354: "Brake_GeneralData",
    0x355: "CLUSTER_BasicInfo_2",
    0x35D: "BCM_SystemControl",
    0x421: "ATCVT_to_MMI_RN1",
    0x50D: "VCM_HMI_GeneralData1",
    0x510: "VCM_HMI_GeneralData2",
    0x54A: "Aircon_GeneralStatus1_ITM",
    0x54B: "Aircon_GeneralStatus2_ITM",
    0x5B3: "VCM_HMI_GeneralData3",
    0x5C0: "LBCMSG5",
    0x5C5: "CLUSTER_GeneralStatus",
    0x5EB: "VCM_ChargeHistoryData1",
    0x60D: "BCM_GeneralStatus7",
    0x625: "USM_GeneralStatus",
}

# Decoded-layer wire model (HYPOTHESIS for field placement).
FRAME_SPEED = 0x280          # setter 0x00023b9c, scale 0.1 km/h (C-7467)
FRAME_GEAR = 0x421           # gear-range enum (0x000237c8)
FRAME_ILLUM = 0x60D          # LowBeam/HighBeam setters 0x00022430/0x00022454
FRAME_BCM = 0x35D            # BCM_SystemControl (no confirmed ignition bit)
FRAME_SOC = 0x5B3            # HiVoltBattery_Real_Capacity (0x00023024)


def encode_frame(can_id: int, payload: bytes) -> bytes:
    """Decoded-layer record: u32 LE id + 8 data bytes.  No UAT3 framing."""
    if can_id not in FRAMES:
        raise ValueError("unknown CAN id 0x%x" % can_id)
    if len(payload) > 8:
        raise ValueError("payload longer than 8 bytes")
    return struct.pack("<I", can_id) + payload.ljust(8, b"\x00")


def decode_frame(frame: bytes) -> tuple[int, bytes]:
    """Inverse of :func:`encode_frame`; rejects short/unknown records."""
    if len(frame) != 12:
        raise ValueError("frame is not 12 bytes")
    can_id = struct.unpack_from("<I", frame)[0]
    if can_id not in FRAMES:
        raise ValueError("unknown CAN id 0x%x" % can_id)
    return can_id, frame[4:]


class Vehicle:
    """Small vehicle state; every setter returns the frames it changed."""

    def __init__(self) -> None:
        self.ignition = False
        self.speed_kmh = 0.0
        self.reverse = False
        self.lights = False
        self.soc = 0.0

    def set(self, key: str, value: str) -> list[bytes]:
        if key == "ignition":
            if value not in ("on", "off"):
                raise ValueError("ignition expects on|off")
            self.ignition = value == "on"
        elif key == "speed":
            kmh = float(value)
            if not 0.0 <= kmh <= 300.0:
                raise ValueError("speed out of range")
            self.speed_kmh = kmh
        elif key == "reverse":
            if value not in ("on", "off"):
                raise ValueError("reverse expects on|off")
            self.reverse = value == "on"
        elif key == "lights":
            if value not in ("on", "off"):
                raise ValueError("lights expects on|off")
            self.lights = value == "on"
        elif key == "soc":
            pct = float(value)
            if not 0.0 <= pct <= 100.0:
                raise ValueError("soc out of range")
            self.soc = pct
        else:
            raise ValueError("unknown signal %r" % key)
        return self.frames()

    def frames(self) -> list[bytes]:
        # Field placement is a model: M8.H49 recovered no byte offsets.
        tenths = int(round(self.speed_kmh * 10)) & 0xffff
        gear = 0x52 if self.reverse else 0x4e   # HYPOTHESIS (R vs N range)
        lamps = 0x80 if self.lights else 0x00   # HYPOTHESIS (low-beam flag)
        ign = 0x01 if self.ignition else 0x00   # HYPOTHESIS
        soc = int(round(self.soc)) & 0xff       # HYPOTHESIS
        return [
            encode_frame(FRAME_SPEED, struct.pack("<H", tenths)),
            encode_frame(FRAME_GEAR, bytes([gear])),
            encode_frame(FRAME_ILLUM, bytes([lamps])),
            encode_frame(FRAME_BCM, bytes([ign])),
            encode_frame(FRAME_SOC, bytes([soc])),
        ]


class Peer:
    def __init__(self) -> None:
        self.car = Vehicle()
        self.guest: socket.socket | None = None
        self.sent = 0

    def send(self, frames: list[bytes]) -> None:
        if self.guest:
            for f in frames:
                self.guest.sendall(f)
                self.sent += 1

    def control(self, conn: socket.socket, line: str) -> None:
        parts = line.strip().split()
        if not parts:
            return
        if parts[0] == "status":
            v = self.car
            conn.sendall(("ignition=%s speed=%.1f reverse=%s lights=%s "
                          "soc=%.1f frames=%d\n" %
                          (v.ignition, v.speed_kmh, v.reverse, v.lights,
                           v.soc, self.sent)).encode())
            return
        if len(parts) != 2:
            conn.sendall(b"ERR expected SIGNAL VALUE\n")
            return
        try:
            frames = self.car.set(parts[0], parts[1])
        except ValueError as exc:
            conn.sendall(("ERR %s\n" % exc).encode())
            return
        self.send(frames)
        conn.sendall(("OK %s %s\n" % (parts[0], parts[1])).encode())

    def serve(self, path: str, listen: bool, control: str | None,
              rate: float, seconds: float) -> None:
        if listen:
            p = Path(path)
            if p.exists():
                p.unlink()
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(path)
            srv.listen(1)
        else:
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.connect(path)
            self.guest = srv
            srv = None
        # M8.H77: the control socket's accept/read loop is shared plumbing;
        # the command grammar (status / SIGNAL VALUE) stays in Peer.control.
        line_peer = peerlib.LinePeer(control, self.control,
                                     timeout=0.1) if control else None
        deadline = time.monotonic() + seconds
        next_send = time.monotonic() + 1.0 / max(rate, 0.01)
        try:
            while time.monotonic() < deadline:
                fds = [x for x in (srv, self.guest) if x]
                if line_peer is not None:
                    fds.append(line_peer.server)
                if not fds:
                    break
                ready, _, _ = select.select(fds, [], [], 0.1)
                for fd in ready:
                    if fd is srv:
                        self.guest, _ = srv.accept()
                if line_peer is not None:
                    line_peer.poll()
                if self.guest and time.monotonic() >= next_send:
                    self.send(self.car.frames())
                    next_send = time.monotonic() + 1.0 / max(rate, 0.01)
        finally:
            for s in (self.guest, srv):
                if s:
                    s.close()
            if line_peer is not None:
                line_peer.close()


def selftest() -> int:
    """Examples from can.md plus negatives; no QEMU needed."""
    checks: list[tuple[str, bool]] = []
    v = Vehicle()
    f = v.set("speed", "123.4")[0]
    checks.append(("speed frame uses id 0x280", f[:4] == struct.pack("<I", 0x280)))
    checks.append(("speed 123.4 km/h -> 1234 tenths",
                   decode_frame(f)[1][:2] == struct.pack("<H", 1234)))
    checks.append(("all five set signals produce 5 frames", len(v.frames()) == 5))
    v.set("ignition", "on"); v.set("reverse", "on")
    v.set("lights", "on"); v.set("soc", "42")
    state = v.frames()
    checks.append(("ignition frame bit set", state[3][4] & 1 == 1))
    checks.append(("reverse range code differs", state[1][4] == 0x52))
    checks.append(("lights flag set", state[2][4] & 0x80 == 0x80))
    checks.append(("soc byte is 42", state[4][4] == 42))
    bad = 0
    for payload in (lambda: encode_frame(0x999, b""),
                    lambda: encode_frame(0x280, b"\x00" * 9),
                    lambda: decode_frame(b"\x01\x02"),
                    lambda: v.set("speed", "999"),
                    lambda: v.set("ignition", "maybe")):
        try:
            payload()
        except ValueError:
            bad += 1
    checks.append(("negative: 5 invalid inputs refused", bad == 5))
    checks.append(("negative: unknown id in decode refused",
                   rejects_unknown_id()))
    ok = all(value for _, value in checks)
    for name, value in checks:
        print("%-48s %s" % (name, "PASS" if value else "FAIL"))
    print("selftest: %d/%d" % (sum(v for _, v in checks), len(checks)))
    return 0 if ok else 1


def rejects_unknown_id() -> bool:
    try:
        decode_frame(struct.pack("<I", 0x777) + b"\x00" * 8)
    except ValueError:
        return True
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--socket", help="AF_UNIX socket of the uat3 chardev")
    ap.add_argument("--listen", action="store_true")
    ap.add_argument("--control", help="AF_UNIX control socket")
    ap.add_argument("--rate", type=float, default=10.0)
    ap.add_argument("--seconds", type=float, default=3600.0)
    ap.add_argument("--selftest-only", action="store_true",
                    help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.socket:
        ap.error("--socket is required outside --selftest")
    Peer().serve(a.socket, a.listen, a.control, a.rate, a.seconds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
