#!/usr/bin/env python3
"""Display-unit / input peer for the QEMU ``ze0`` machine (TODO M8.H38).

The peer turns host commands into the input events decoded in
``docs/firmware/touch.md`` and ``docs/firmware/keys.md``.  Two injection
planes are behind one interface:

* **touch** — the 6-byte ``LCD1: IOCTL 0x800b205c`` record
  ``{u16 x, u16 y, u8 status ASCII '0'/'1', u8 unused}``.  The GUI receives it
  as ``PostMessageW(WM_MOUSEMOVE / WM_LBUTTONDOWN / WM_LBUTTONUP,
  (y<<16)|x)`` (build B ``0x3a17020``).
* **display unit on SCI3** (``--sci3 PATH``, M8.H35) — the peer connects to
  the QEMU chardev of ``sci3``, answers ``lcddrv.dll``'s start-up handshake
  and sends touch as the frame ``51 xh xl yh yl status``
  (``docs/firmware/lcddrv.md``).  This is the path the firmware really uses;
  the 6-byte record lines on ``--out`` are still written for the record.
* **keys** — the ``{raw, vk}`` pairs of ``kepdrv.dll``'s KeyType 3 table
  (``docs/firmware/keys.md`` §3.1, table at ``0x01f421b4``); the peer emits
  virtual-key down/up pairs for the same message-level injection plane.

Every command writes one or more events to ``--out`` (a text stream, ``-`` for
stdout).  Each line is ``touch <hex6> after_ms`` or ``key <vk_hex> down|up
after_ms``; the ``after_ms`` value is a delay relative to the preceding event,
so the stream is reproducible and can be replayed by a gdb/QMP bridge (M8.H39).

``--control PATH`` is an AF_UNIX socket for ``tools/ze0_ui.py``: one command
line in, one answer starting with ``OK`` (or ``ERR ...`` for a bad command).
The same commands are accepted on the command line.

Usage:
  panel.py --selftest
  panel.py --out events.txt tap 400 240
  panel.py --out events.txt drag 100 100 200 200
  panel.py --out events.txt key MAP --long
  panel.py --control SOCK --out events.txt
  panel.py --sci3 R.sci3 --control SOCK --forever      # live, with QEMU

Stdlib only.  Claims C-7350-C-7359; method and results in
``docs/experiments/EXP-2026-11-22-M8.H38-panel-peer.md``.
"""

import argparse
import os
import re
import select
import socket
import struct
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import anw_frames  # noqa: E402  (same DLE STX ... DLE ETX BCC framing)

SCREEN_W = 800
SCREEN_H = 480
RECORD_LEN = 6

# docs/firmware/keys.md section 3.1: KeyType 3 table at 0x01f421b4.
# Names are the manual wording marked OBSERVED in that page; map/nav-function
# assignment below 0x17..0x1a is a HYPOTHESIS and never used as firmware truth.
KEY_TABLE = {
    "ENTER": 0x0D,
    "NAV7": 0x07,
    "NAV6": 0x06,
    "MAP": 0x17,
    "MENU": 0x18,
    "DEST": 0x19,
    "ZOOM": 0x1A,
    "DAY_NIGHT": 0x21,
    "DAY/NIGHT": 0x21,
    "FUNC20": 0x20,
    "ESC": 0x1B,
    "BACK": 0x1B,
    "FUNC1C": 0x1C,
    "FUNC1D": 0x1D,
    "FUNC1E": 0x1E,
    "FUNC00": 0x00,
    "FUNC01": 0x01,
    "FUNC1F": 0x1F,
    "VOL_UP": 0x05,
    "VOLUME": 0x05,
}


class PanelError(ValueError):
    """A command with invalid coordinates, status or key name."""


def encode_sample(x, y, status):
    """Return the 6-byte record the firmware's IOCTL 0x800b205c returns.

    ``status`` is the ASCII byte: '1' = press, '0' = release.  Coordinates are
    screen pixels clamped by the firmware to 800x480 (C-7335); out-of-range
    values are refused here rather than silently wrapped.
    """
    if isinstance(status, str):
        if status not in ("0", "1"):
            raise PanelError("status must be '0' or '1', got %r" % status)
        status = ord(status)
    if not isinstance(x, int) or not isinstance(y, int):
        raise PanelError("x and y must be integers")
    if not 0 <= x <= SCREEN_W:
        raise PanelError("x %d out of range 0..%d" % (x, SCREEN_W))
    if not 0 <= y <= SCREEN_H:
        raise PanelError("y %d out of range 0..%d" % (y, SCREEN_H))
    return struct.pack("<HHsB", x, y, bytes([status]), 0)


def tap_events(x, y, ms=100):
    """Press / hold / release at one point; returns (after_ms, record) pairs."""
    if ms < 0:
        raise PanelError("hold time must be >= 0")
    return [(0, encode_sample(x, y, "1")),
            (int(ms), encode_sample(x, y, "0"))]


def drag_events(x1, y1, x2, y2, steps=5, ms=20):
    """Press, intermediate moves, release.

    The firmware accepts only status '0'/'1' in the wire record (C-7333), so
    a drag is a sequence of press samples at moving coordinates followed by
    one release; the driver turns the repeated press into WM_MOUSEMOVE after
    the button is down.  That last step is a HYPOTHESIS pending M8.H39.
    """
    if steps < 1:
        raise PanelError("steps must be >= 1")
    events = [(0, encode_sample(x1, y1, "1"))]
    for i in range(1, steps + 1):
        t = i / float(steps + 1)
        x = int(round(x1 + (x2 - x1) * t))
        y = int(round(y1 + (y2 - y1) * t))
        events.append((int(ms), encode_sample(x, y, "1")))
    events.append((int(ms), encode_sample(x2, y2, "0")))
    return events


def key_code(name):
    """Resolve a human key name or a raw hex code to the CE virtual key."""
    upper = name.strip().upper()
    if upper in KEY_TABLE:
        return KEY_TABLE[upper]
    m = re.fullmatch(r"0X([0-9A-F]{1,2})", upper)
    if m:
        return int(m.group(1), 16)
    if upper.isdigit() and int(upper) <= 255:
        return int(upper)
    raise PanelError("unknown key %r" % name)


def key_events(name, long=False):
    """Key down / up pair with the virtual key from keys.md."""
    vk = key_code(name)
    hold = 600 if long else 80
    return [(0, "key 0x%02x down" % vk), (hold, "key 0x%02x up" % vk)]


def format_event(after_ms, event):
    if isinstance(event, (bytes, bytearray)):
        return "touch %s %d" % (bytes(event).hex(), after_ms)
    return "%s %d" % (event, after_ms)


def _int(token, what):
    try:
        return int(token, 10)
    except ValueError:
        raise PanelError("%s must be an integer, got %r" % (what, token))


def control_commands(line, state):
    """Apply one control line; return an answer starting with OK or ERR.

    Accepted: ``tap X Y [--ms N]``, ``drag X1 Y1 X2 Y2``, ``key NAME
    [--long]``, ``status``.  A rejected command must not change the event
    stream — the negative control used by the selftest.
    """
    parts = line.strip().split()
    if not parts:
        return "ERR empty command"
    cmd = parts[0].lower()
    try:
        if cmd == "tap" and len(parts) in (3, 5):
            x, y = _int(parts[1], "x"), _int(parts[2], "y")
            ms = 100
            if len(parts) == 5:
                if parts[3].lower() != "--ms":
                    raise PanelError("expected --ms N")
                ms = _int(parts[4], "ms")
            ev = tap_events(x, y, ms)
            state["events"].extend(format_event(*e) for e in ev)
            return "OK tap %d %d %d events" % (x, y, len(ev))
        if cmd == "drag" and len(parts) == 5:
            x1, y1, x2, y2 = (_int(p, "coordinate") for p in parts[1:])
            ev = drag_events(x1, y1, x2, y2)
            state["events"].extend(format_event(*e) for e in ev)
            return "OK drag %d %d %d %d %d events" % (x1, y1, x2, y2, len(ev))
        if cmd == "key" and len(parts) in (2, 3):
            if len(parts) == 3 and parts[2].lower() != "--long":
                raise PanelError("expected --long")
            ev = key_events(parts[1], len(parts) == 3)
            state["events"].extend(format_event(*e) for e in ev)
            return "OK key %s%s" % (parts[1], " long" if len(parts) == 3 else "")
        if cmd == "status":
            return "OK status events=%d" % len(state["events"])
    except PanelError as exc:
        return "ERR %s" % exc
    return "ERR unknown command: %s" % cmd


# --------------------------------------------------------------------------
# SCI3 display-unit link (M8.H35, docs/firmware/lcddrv.md)
# --------------------------------------------------------------------------

ACK = b"\x10\x06"
NAK = b"\x10\x15"
CMD_TOUCH = 0x51
# What the display unit answers to each driver command (lcddrv.dll, NK1):
# 0x23 asks for the unit's identity (phase 0, answered by a 0x24 frame of
# 14 bytes); 0x25 ends the handshake (ACK only); 0x71 is the periodic poll
# (phase 2, answered by a 0x71 frame).  Every valid frame is ACKed.
DISPLAY_REPLIES = {
    0x23: bytes.fromhex("24") + bytes(13),
    0x71: bytes.fromhex("71"),
}


def touch_frame_payload(record):
    """SCI3 payload for one decoded 6-byte record: ``51 xh xl yh yl st``.

    The wire carries big-endian coordinates (lcddrv.dll copies frame bytes
    +1..+5 into its touch slot, NK1 function at 0x03d16300, and the IOCTL
    handler at 0x03d17258 assembles them high byte first).
    """
    x, y, st, _ = struct.unpack("<HHsB", record)
    return bytes((CMD_TOUCH,)) + struct.pack(">HH", x, y) + st


class DisplayUnit:
    """Byte-stream model of the display unit; feed() returns bytes to send."""

    def __init__(self, replies=None):
        self.replies = dict(DISPLAY_REPLIES if replies is None else replies)
        self.buf = b""
        self.seen = []          # decoded driver commands, in order
        self.acks = 0           # ACKs received from the driver
        self.naks = 0

    def feed(self, data):
        self.buf += data
        out = b""
        while self.buf:
            if self.buf.startswith(ACK):
                self.acks += 1
                self.buf = self.buf[2:]
                continue
            if self.buf.startswith(NAK):
                self.naks += 1
                self.buf = self.buf[2:]
                continue
            i = self.buf.find(b"\x10\x02")
            if i < 0:
                self.buf = self.buf[-1:] if self.buf.endswith(b"\x10") else b""
                break
            if i > 0:
                self.buf = self.buf[i:]
            end = self._frame_end()
            if end is None:
                break
            frame, self.buf = self.buf[:end], self.buf[end:]
            try:
                payload = anw_frames.parse_frame(frame)
            except anw_frames.FrameError:
                out += NAK
                continue
            self.seen.append(payload[0])
            out += ACK
            reply = self.replies.get(payload[0])
            if reply is not None:
                out += anw_frames.build_frame(reply)
        return out

    def _frame_end(self):
        """Index after the BCC of the frame at buf[0], or None if partial."""
        j = 2
        while True:
            k = self.buf.find(b"\x10", j)
            if k < 0 or k + 1 >= len(self.buf):
                return None
            nxt = self.buf[k + 1]
            if nxt == 0x10:
                j = k + 2
                continue
            if nxt == 0x03:
                return k + 3 if k + 2 < len(self.buf) else None
            j = k + 1


class Sci3Link:
    """The QEMU ``sci3`` chardev socket driven by a DisplayUnit."""

    def __init__(self, path, log=None, connect_s=30.0):
        self.unit = DisplayUnit()
        self.log = log
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        deadline = time.time() + connect_s
        while True:
            try:
                self.sock.connect(path)
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.2)
        self.sock.setblocking(False)

    def _log(self, *a):
        if self.log:
            print("sci3:", *a, file=self.log, flush=True)

    def pump(self, timeout=0.0):
        """Read what the driver sent and answer at once (guest time runs on)."""
        ready, _, _ = select.select([self.sock], [], [], timeout)
        if not ready:
            return
        data = self.sock.recv(4096)
        if not data:
            raise ConnectionError("sci3 peer closed")
        before = len(self.unit.seen)
        reply = self.unit.feed(data)
        if reply:
            self.sock.sendall(reply)
        for cmd in self.unit.seen[before:]:
            if cmd != 0x71:
                self._log("driver cmd 0x%02x" % cmd)

    def send_payload(self, payload):
        self.sock.sendall(anw_frames.build_frame(payload))
        self._log("sent", payload.hex())

    def play(self, lines):
        """Send touch records of ``touch HEX after_ms`` lines, keeping time."""
        for line in lines:
            parts = line.split()
            if parts[0] == "touch":
                delay = int(parts[2]) / 1000.0
                end = time.time() + delay
                while time.time() < end:
                    self.pump(min(0.02, max(0.0, end - time.time())))
                self.send_payload(touch_frame_payload(bytes.fromhex(parts[1])))
            elif parts[0] == "frame":
                self.send_payload(bytes.fromhex(parts[1]))


class Out:
    """Text event stream; '-' is stdout, otherwise a file or AF_UNIX socket."""

    def __init__(self, path):
        self.path = path
        self.fh = None
        self.sock = None
        if path and path != "-":
            if path.startswith("unix:"):
                sock_path = path[5:]
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.settimeout(5.0)
                self.sock.connect(sock_path)
            else:
                self.fh = open(path, "a", encoding="ascii")

    def write(self, text):
        line = text + "\n"
        if self.sock is not None:
            self.sock.sendall(line.encode("ascii"))
        elif self.fh is not None:
            self.fh.write(line)
            self.fh.flush()
        else:
            sys.stdout.write(line)

    def close(self):
        for obj in (self.sock, self.fh):
            if obj is not None:
                obj.close()


def emit(events, out):
    state = {"events": []}
    for after_ms, event in events:
        line = format_event(after_ms, event)
        state["events"].append(line)
        out.write(line)
    return len(state["events"])


def group_commands(tokens):
    """Group argv tokens into complete command lines (arity checked here)."""
    words = list(tokens)
    out = []
    i = 0
    while i < len(words):
        cmd = words[i].lower()
        if cmd == "tap" and i + 2 < len(words):
            group = words[i:i + 3]
            i += 3
            if i + 1 < len(words) and words[i].lower() == "--ms":
                group += words[i:i + 2]
                i += 2
        elif cmd == "drag" and i + 4 < len(words):
            group = words[i:i + 5]
            i += 5
        elif cmd == "key" and i + 1 < len(words):
            group = words[i:i + 2]
            i += 2
            if i < len(words) and words[i].lower() == "--long":
                group.append(words[i])
                i += 1
        else:
            raise PanelError("cannot parse command at %r" % words[i])
        out.append(" ".join(group))
    return out


def run(args):
    out = Out(args.out)
    state = {"events": []}
    errors = []
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

    link = None
    if getattr(args, "sci3", None):
        link = Sci3Link(args.sci3, log=sys.stdout)

    def apply(line):
        if line.strip().lower().startswith("frame "):
            # raw SCI3 payload, e.g. a key frame "frame 3401" (M8.H35)
            try:
                payload = bytes.fromhex(line.split(None, 1)[1].strip())
                if not payload:
                    raise ValueError("empty")
            except ValueError as exc:
                answer = "ERR bad frame hex: %s" % exc
            else:
                if link is not None:
                    link.send_payload(payload)
                out.write("frame %s 0" % payload.hex())
                answer = "OK frame %s" % payload.hex()
            print("panel: %s -> %s" % (line.strip(), answer))
            return answer
        answer = control_commands(line, state)
        for pending in state["events"]:
            out.write(pending)
        if link is not None:
            link.play(state["events"])
        state["events"] = []
        print("panel: %s -> %s" % (line.strip(), answer))
        if answer.startswith("ERR"):
            errors.append(answer)
        return answer

    try:
        for line in args.commands or []:
            apply(line)
        deadline = None if (args.forever or link is not None) else 0.0
        while (ctrl is not None or link is not None) and (deadline is None or True):
            socks = [ctrl] if ctrl is not None else []
            if link is not None:
                link.pump(0.0)
                socks.append(link.sock)
            ready, _, _ = select.select(socks, [], [], 0.1)
            if link is not None and link.sock in ready:
                link.pump(0.0)
            if ctrl is None or ctrl not in ready:
                ready = []
            if ready:
                conn, _ = ctrl.accept()
                with conn:
                    data = conn.recv(4096).decode("utf-8", "replace")
                    for line in data.splitlines():
                        conn.sendall((apply(line) + "\n").encode("utf-8"))
            if deadline is not None:
                break
    except ConnectionError as exc:
        print("panel: %s" % exc)
    finally:
        if ctrl is not None:
            ctrl.close()
        if link is not None:
            print("panel: sci3 driver commands %d, ACKs %d, NAKs %d" %
                  (len(link.unit.seen), link.unit.acks, link.unit.naks))
            link.sock.close()
        out.close()
    return 1 if errors else 0


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

    def rejected(fn):
        try:
            fn()
        except PanelError:
            return True
        return False

    # The documented sample: docs/firmware/touch.md section 3.2.
    check("press sample 400,240", encode_sample(400, 240, "1").hex(),
          "9001f0003100")
    check("release sample 400,240", encode_sample(400, 240, "0").hex(),
          "9001f0003000")
    check("sample length", len(encode_sample(0, 0, "1")), RECORD_LEN)
    check("sample struct round trip", struct.unpack("<HHsB", encode_sample(799, 479, "1")),
          (799, 479, b"1", 0))
    check("tap sequence", [e.hex() for _, e in tap_events(400, 240, 120)],
          ["9001f0003100", "9001f0003000"])
    check("tap delays", [d for d, _ in tap_events(400, 240, 120)], [0, 120])

    # Negative controls: out-of-range coordinates and bad status must refuse.
    check("x>800 refused", rejected(lambda: encode_sample(801, 240, "1")), True)
    check("y>480 refused", rejected(lambda: encode_sample(400, 481, "1")), True)
    check("negative x refused", rejected(lambda: encode_sample(-1, 240, "1")), True)
    check("bad status refused", rejected(lambda: encode_sample(400, 240, "2")), True)
    check("float coordinate refused", rejected(lambda: encode_sample(1.5, 2, "1")), True)
    bad_state = {"events": []}
    check("tap via control refuses x>800",
          control_commands("tap 801 240", bad_state).startswith("ERR"), True)
    check("bad control emits nothing", len(bad_state["events"]), 0)

    # Drag: press, intermediate moves, release; all samples valid and in range.
    drag = drag_events(100, 100, 200, 200)
    check("drag begins with press", drag[0][1][4:5], b"1")
    check("drag ends with release", drag[-1][1][4:5], b"0")
    check("drag has intermediate moves", len(drag) >= 4, True)
    check("drag stays in bounds",
          all(0 <= x <= SCREEN_W and 0 <= y <= SCREEN_H
              for _, rec in drag
              for x, y in [struct.unpack("<HH", rec[:4])]), True)
    check("bad drag refused", rejected(lambda: drag_events(900, 1, 2, 2)), True)

    # Key names from docs/firmware/keys.md section 3.1.
    check("MAP vk", key_code("MAP"), 0x17)
    check("ENTER vk", key_code("ENTER"), 0x0D)
    check("ESC vk", key_code("ESC"), 0x1B)
    check("raw 0x0d vk", key_code("0x0d"), 0x0D)
    check("key events", [e for _, e in key_events("MAP")],
          ["key 0x17 down", "key 0x17 up"])
    check("long key holds longer",
          [d for d, _ in key_events("MAP", True)][1] >
          [d for d, _ in key_events("MAP")][1], True)
    check("unknown key refused", rejected(lambda: key_code("NOT_A_KEY")), True)
    check("control tap", control_commands("tap 400 240", {"events": []}),
          "OK tap 400 240 2 events")
    check("control key", control_commands("key MAP", {"events": []}),
          "OK key MAP")
    check("control unknown", control_commands("wat", {"events": []}).startswith("ERR"), True)
    check("control status", control_commands("status", {"events": ["x"]}),
          "OK status events=1")
    check("argv grouping", group_commands(
        ["tap", "400", "240", "key", "MAP", "--long"]),
        ["tap 400 240", "key MAP --long"])
    check("argv grouping with --ms", group_commands(
        ["drag", "1", "2", "3", "4", "tap", "5", "6", "--ms", "50"]),
        ["drag 1 2 3 4", "tap 5 6 --ms 50"])
    check("bad argv grouping refused",
          rejected(lambda: group_commands(["tap", "400"])), True)

    # SCI3 display unit (M8.H35): the handshake bytes of the R24 run.
    unit = DisplayUnit()
    check("0x23 -> ACK + 0x24 frame",
          unit.feed(bytes.fromhex("100223100330")).hex(),
          "1006" + "10022400000000000000000000000000100337")
    check("0x25 -> ACK only", unit.feed(bytes.fromhex("100225100336")).hex(), "1006")
    check("0x71 poll -> ACK + 0x71", unit.feed(bytes.fromhex("100271100362")).hex(),
          "1006100271100362")
    check("driver ACK is not answered", unit.feed(ACK), b"")
    check("driver ACK counted", unit.acks, 1)
    part = bytes.fromhex("1002423131310931100358")
    check("split frame waits", unit.feed(part[:5]), b"")
    check("split frame completes", unit.feed(part[5:]).hex(), "1006")
    check("commands seen", unit.seen, [0x23, 0x25, 0x71, 0x42])
    check("bad BCC -> NAK", unit.feed(bytes.fromhex("100271100363")).hex(), "1015")
    check("bad frame not recorded", unit.seen[-1], 0x42)
    check("touch payload 400,240 press",
          touch_frame_payload(encode_sample(400, 240, "1")).hex(), "51019000f031")
    check("touch frame on the wire",
          anw_frames.build_frame(touch_frame_payload(
              encode_sample(400, 240, "1"))).hex(), "100251019000f031100312")
    check("DLE in a coordinate is doubled",
          anw_frames.build_frame(touch_frame_payload(
              encode_sample(16, 240, "0"))).hex()[:14], "10025100101000")

    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", default="-",
                    help="event stream: '-' stdout, PATH file, unix:PATH socket")
    ap.add_argument("--control", help="AF_UNIX control socket for ze0_ui.py")
    ap.add_argument("--sci3", metavar="PATH",
                    help="QEMU chardev socket of sci3: act as the display unit "
                         "(handshake + touch frames, M8.H35)")
    ap.add_argument("--forever", action="store_true",
                    help="keep the control socket open instead of one batch")
    ap.add_argument("commands", nargs="*",
                    help="tap X Y [--ms N] | drag X1 Y1 X2 Y2 | key NAME [--long]")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        args.commands = group_commands(args.commands)
        return run(args)
    except PanelError as exc:
        print("panel: ERR %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
