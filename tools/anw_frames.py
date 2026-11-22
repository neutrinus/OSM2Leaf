#!/usr/bin/env python3
"""`anwdrv.dll` iNai frame codec on `SCI1:` (M8.H43).

The frame grammar is implemented by ``CInaiFormat`` in build B's
``anwdrv.dll`` (EU2011, image start ``0x3e00200``):

* ``fn 0x03ba23f4`` writes ``10 02`` (DLE STX), the DLE-stuffed message,
  ``10 03`` (DLE ETX) and the BCC;
* ``fn 0x03ba2260`` / ``fn 0x03ba2334`` stuff / unstuff DLE (``0x10`` is
  doubled inside the message);
* ``fn 0x03ba2138`` accumulates the BCC as an XOR of every byte it is given;
* ``fn 0x03ba0860`` (``BccCheck``) checks it over ``frame[2..size-2]``.

The one frame logged by EXP-2026-11-22-M8.C2a O4 is the pinned vector:
``10 02 02 08 00 10 03 19``. Stdlib only, no vendor bytes; ``--selftest``
is auto-discovered by ``tools/selftest.py``.

Usage:
  anw_frames.py --selftest
  anw_frames.py frame 1002020800100319
  anw_frames.py build 020800
"""
import argparse
import sys

DLE = 0x10
STX = 0x02
ETX = 0x03
LOGGED_FRAME = bytes.fromhex("1002020800100319")

# Control (DT) byte values accepted by CInaiFormat::GetControlType,
# fn 0x03ba1f5c: 0x02 -> 0, 0x06 -> 1, 0x15 -> 2, anything else -> 3.
CONTROL_TYPES = {0x02: 0, 0x06: 1, 0x15: 2}
CTRL_ACK = 0x02
CTRL_NAK = 0x15


class FrameError(ValueError):
    """A frame failed framing, stuffing or BCC validation."""


def bcc(data):
    """Block check character: XOR of all bytes (fn 0x03ba2138)."""
    acc = 0
    for byte in data:
        acc ^= byte
    return acc & 0xFF


def stuff(payload):
    """Double every DLE byte in the message body (fn 0x03ba2260)."""
    out = bytearray()
    for byte in payload:
        out.append(byte)
        if byte == DLE:
            out.append(DLE)
    return bytes(out)


def unstuff(body):
    """Remove the second byte of every ``10 10`` pair (fn 0x03ba2334)."""
    out = bytearray()
    i = 0
    while i < len(body):
        byte = body[i]
        out.append(byte)
        if byte == DLE and i + 1 < len(body) and body[i + 1] == DLE:
            i += 1
        i += 1
    return bytes(out)


def build_frame(payload):
    """Encode an iNai message (first byte is the control/DT byte)."""
    if not payload:
        raise FrameError("empty payload")
    body = stuff(payload)
    tail = bytes((DLE, ETX))
    return bytes((DLE, STX)) + body + tail + bytes((bcc(body + tail),))


def parse_frame(frame):
    """Validate and decode a frame; return the unstuffed message bytes."""
    if len(frame) < 6:
        raise FrameError("frame shorter than 6 bytes")
    if frame[0] != DLE or frame[1] != STX:
        raise FrameError("missing DLE STX")
    if frame[-3] != DLE or frame[-2] != ETX:
        raise FrameError("missing DLE ETX")
    expected = bcc(frame[2:-1])
    if expected != frame[-1]:
        raise FrameError("BCC %02x != %02x" % (frame[-1], expected))
    body = frame[2:-3]
    # Every DLE inside the message must be doubled; a lone DLE would end
    # the frame early (fn 0x03ba2334 rejects it as "Illegal DLE").
    i = 0
    while i < len(body):
        if body[i] == DLE:
            if i + 1 >= len(body) or body[i + 1] != DLE:
                raise FrameError("undoubled DLE in message body")
            i += 1
        i += 1
    return unstuff(body)


def control_type(payload):
    """The DT class of a decoded message (fn 0x03ba1f5c)."""
    return CONTROL_TYPES.get(payload[0], 3) if payload else 3


def _selftest():
    checks = []

    def eq(name, got, want):
        checks.append((name, got == want, got, want))

    # Positive control: the frame logged on SCIF1 by M8.C2a O4.
    eq("logged BCC", bcc(bytes.fromhex("0208001003")), 0x19)
    eq("logged frame", build_frame(bytes.fromhex("020800")).hex(),
       LOGGED_FRAME.hex())
    eq("logged decode", parse_frame(LOGGED_FRAME).hex(), "020800")
    eq("logged control", control_type(bytes.fromhex("020800")), 0)
    # A DLE in the body must be doubled, and BCC covers the doubled bytes.
    doubled = build_frame(bytes.fromhex("02100300"))
    eq("DLE stuffing", doubled.hex(), "10020210100300100312")
    eq("DLE unstuffing", parse_frame(doubled).hex(), "02100300")
    # Negative controls: a wrong BCC and a missing ETX must fail loudly.
    for name, bad in (
        ("bad BCC", LOGGED_FRAME[:-1] + bytes((0x18,))),
        ("bad ETX", LOGGED_FRAME[:6] + bytes((0x04, 0x19))),
        ("bad STX", bytes((0x10, 0x05)) + LOGGED_FRAME[2:]),
        ("undoubled DLE", bytes.fromhex("1002100200100319")),
    ):
        try:
            parse_frame(bad)
            eq(name, "accepted", "rejected")
        except FrameError as exc:
            eq(name, "rejected", "rejected")
    eq("unknown control", control_type(b"\x77"), 3)
    eq("NAK control", control_type(bytes((CTRL_NAK,))), 2)
    failed = [c for c in checks if not c[1]]
    for name, ok, got, want in checks:
        print("%-18s %s (got %r, want %r)" %
              (name, "PASS" if ok else "FAIL", got, want))
    print("selftest: %d/%d PASS" % (len(checks) - len(failed), len(checks)))
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("command", nargs="?", choices=("frame", "build"))
    ap.add_argument("hexdata", nargs="?")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not args.command or not args.hexdata:
        ap.error("give --selftest, 'frame HEX' or 'build HEX'")
    try:
        raw = bytes.fromhex(args.hexdata)
    except ValueError as exc:
        print("bad hex: %s" % exc, file=sys.stderr)
        return 2
    try:
        if args.command == "frame":
            payload = parse_frame(raw)
            print("payload=%s control=%d (0x%02x) BCC=%02x" %
                  (payload.hex(), control_type(payload), payload[0], raw[-1]))
        else:
            print(build_frame(raw).hex())
    except FrameError as exc:
        print("frame error: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
