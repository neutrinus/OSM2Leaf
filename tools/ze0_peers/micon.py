#!/usr/bin/env python3
"""Audio-microcontroller peer for the QEMU ``ze0`` machine (M8.H44).

The host side of ``SCI1:`` speaks the iNai frames decoded in
[`docs/firmware/anwdrv.md`](../../docs/firmware/anwdrv.md). QEMU only carries
the bytes; this program plays the audio micom so the launcher can stop
waiting for module presence. It is a plain host process with a `--selftest`,
no QEMU and no vendor bytes required.

Wire rules reused from ``tools/anw_frames.py`` (M8.H43):

    DLE STX | DLE-stuffed message | DLE ETX | XOR BCC

The `--socket` chardev is the `sci1` peer; `--control` is the AF_UNIX command
socket used by ``tools/ze0_ui.py`` later. The reply table maps a request
prefix to a response body; all framed replies get a correct BCC, and a
request with a wrong BCC is rejected rather than answered. The exact body of
the module-present reply is a HYPOTHESIS in the M8.H43 record; this peer
makes it configurable rather than claiming firmware acceptance.

Usage:
  micon.py --selftest
  micon.py --socket PATH [--listen] [--control PATH] [--duration SECONDS]
           [--log PATH] [--replay FILE]

Stdlib only. Method and results: docs/experiments/EXP-2026-11-22-M8.H44-micon-peer.md
"""

import argparse
import os
import select
import socket
import sys
import time

# anw_frames.py lives one directory up (tools/), next to ze0_peers/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import anw_frames as anw  # noqa: E402

CTRL_ACK = anw.CTRL_ACK          # 0x02, positive response
CTRL_INTR = 0x06                 # third control class of GetControlType
CTRL_NAK = anw.CTRL_NAK          # 0x15, never sent as a presence reply
LOGGED_REQUEST = bytes.fromhex("1002020800100319")

# VK values of docs/firmware/keys.md §3.1 (KeyType 3), used by `key NAME`.
KEY_VK = {"ENTER": 0x0D, "MAP": 0x17, "MENU": 0x18, "DEST": 0x19,
          "ZOOM": 0x1A, "ESC": 0x1B, "DAY_NIGHT": 0x21}


class Rule:
    """One request pattern -> reply body rule (longest prefix wins)."""

    def __init__(self, name, prefix, body, note=""):
        self.name = name
        self.prefix = bytes(prefix)
        self.body = body              # callable(payload) -> response message
        self.note = note

    def matches(self, payload):
        return payload.startswith(self.prefix)


def _echo_ack(payload):
    """ACK, echo the command and its parameters."""
    return bytes((CTRL_ACK,)) + payload


RULES = (
    Rule("ReqMo", b"\x02\x08",
         lambda p: bytes((CTRL_ACK, 0x02, 0x08, 0x00)),
         "module presence; active-mask bytes 08 00 are HYPOTHESIS (M8.H43)"),
    Rule("ReqMo", b"\x02", _echo_ack, "generic module request"),
    Rule("Audio", b"\x04", _echo_ack, "audio source command"),
    Rule("ReqAIr", b"\x01", _echo_ack, "audio interrupt request"),
    Rule("GetSy", b"\x09", _echo_ack, "system information read-back"),
)


class MiconPeer:
    """Frame dispatcher: one guest frame in, zero or one reply out."""

    def __init__(self, rules=RULES, log=None):
        self.rules = tuple(rules)
        self.log = log or (lambda event, fields: None)
        self.requests = 0
        self.bad = 0
        self.unknown = 0
        self.replies = 0
        self.fail_command = None
        self.pending = []

    def _emit(self, event, **fields):
        self.log(event, fields)

    def handle(self, frame):
        """Validate one complete frame and return the reply frame or None."""
        try:
            payload = anw.parse_frame(bytes(frame))
        except anw.FrameError as exc:
            self.bad += 1
            self._emit("reject", reason=str(exc), frame=bytes(frame).hex())
            return None
        self.requests += 1
        self._emit("request", payload=payload.hex(), control=anw.control_type(payload))

        if self.fail_command is not None and payload[:1] == bytes((self.fail_command,)):
            self._emit("forced_nak", command="0x%02x" % self.fail_command)
            return anw.build_frame(bytes((CTRL_NAK,)) + payload)

        rule = next((r for r in self.rules if r.matches(payload)), None)
        if rule is None:
            self.unknown += 1
            self._emit("unknown", payload=payload.hex())
            return None
        body = bytes(rule.body(payload))
        reply = anw.build_frame(body)
        self.replies += 1
        self._emit("reply", rule=rule.name, payload=body.hex(), frame=reply.hex(),
                   note=rule.note)
        if self.pending:
            self._emit("pending", events=list(self.pending))
            self.pending.clear()
        return reply

    def control(self, line):
        """One AF_UNIX control command; returns a human-readable answer."""
        parts = line.strip().split()
        if not parts:
            return ""
        cmd = parts[0].lower()
        if cmd == "status":
            return ("status requests=%d bad=%d unknown=%d replies=%d pending=%d" %
                    (self.requests, self.bad, self.unknown, self.replies,
                     len(self.pending)))
        if cmd == "reset":
            self.requests = self.bad = self.unknown = self.replies = 0
            self.pending.clear()
            return "reset"
        if cmd == "key" and len(parts) == 2:
            name = parts[1].upper()
            if name in KEY_VK:
                vk = KEY_VK[name]
            elif name.startswith("0X"):
                try:
                    vk = int(name, 16) & 0xFF
                except ValueError:
                    return "ERR bad key %s" % parts[1]
            else:
                return "ERR unknown key %s" % parts[1]
            # Interrupt-class frames are a HYPOTHESIS (M8.H43 §4); queueing
            # one does not claim the guest accepts it.
            self.pending.append("key:%s:0x%02x" % (name, vk))
            return "queued key %s 0x%02x" % (name, vk)
        if cmd == "fail" and len(parts) == 2:
            try:
                self.fail_command = int(parts[1], 16) & 0xFF
            except ValueError:
                return "ERR bad command %s" % parts[1]
            return "fail command 0x%02x" % self.fail_command
        if cmd == "nofail":
            self.fail_command = None
            return "nofail"
        return "ERR unknown command: %s" % cmd


def extract_frames(buf):
    """Pop every complete, BCC-valid frame from ``buf`` (bytearray).

    DLE-stuffed payloads are skipped correctly: only an unstuffed ``10 03``
    ends a frame. An invalid candidate is dropped with a one-byte resync.
    """
    found = []
    i = 0
    while True:
        start = buf.find(b"\x10\x02", i)
        if start < 0:
            break
        k = start + 2
        end = None
        while k + 1 < len(buf):
            if buf[k] == anw.DLE:
                if buf[k + 1] == anw.DLE:
                    k += 2
                    continue
                if buf[k + 1] == anw.ETX:
                    end = k + 3          # DLE, ETX, BCC
                    break
            k += 1
        if end is None or end > len(buf):
            break                        # incomplete frame; wait for more
        try:
            payload = anw.parse_frame(bytes(buf[start:end]))
        except anw.FrameError:
            i = start + 1
            continue
        found.append((bytes(buf[start:end]), payload))
        i = end
    del buf[:i]
    return found


def replay(path, peer):
    """Feed whitespace-separated hex frames from ``path`` through ``peer``."""
    replies = []
    with open(path, encoding="ascii") as fh:
        for line in fh:
            for token in line.split():
                if token.startswith("#"):
                    break
                replies.append(peer.handle(bytes.fromhex(token)))
    return replies


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------

def connect_serial(path, listen=False, timeout=5.0):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    if listen:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        server = sock
        server.bind(path)
        server.listen(1)
        conn, _ = server.accept()
        return conn, server
    sock.connect(path)
    return sock, None


def make_control(path):
    if not path:
        return None
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(1)
    server.settimeout(0.1)
    return server


def run(args):
    serial, server = connect_serial(args.socket, args.listen)
    ctrl = make_control(args.control)
    logfh = open(args.log, "a", encoding="utf-8") if args.log else None
    peer = MiconPeer(log=lambda ev, f: _log(logfh, ev, f))

    def emit(ev, **f):
        _log(logfh, ev, f)

    buf = bytearray()
    deadline = time.monotonic() + args.duration
    try:
        if args.replay:
            for reply in replay(args.replay, peer):
                if reply:
                    print("micon: %s" % reply.hex())
                    serial.sendall(reply)
            return 0
        while time.monotonic() < deadline:
            readable = [serial] + ([ctrl] if ctrl else [])
            ready, _, _ = select.select(readable, [], [], 0.05)
            if ctrl in ready:
                conn, _ = ctrl.accept()
                with conn:
                    line = conn.recv(1024).decode("utf-8", "replace")
                    answer = peer.control(line)
                    emit("control", line=line.strip(), answer=answer)
                    conn.sendall(answer.encode("utf-8"))
            if serial in ready:
                chunk = serial.recv(4096)
                if not chunk:
                    break
                buf.extend(chunk)
                for frame, payload in extract_frames(buf):
                    reply = peer.handle(frame)
                    if reply:
                        serial.sendall(reply)
            time.sleep(0.005)
        return 0
    finally:
        if logfh:
            logfh.close()
        serial.close()
        if server:
            server.close()
        if ctrl:
            ctrl.close()


def _log(fh, event, fields):
    import json
    line = "%s %s" % (event, " ".join("%s=%s" % (k, v) for k, v in fields.items()))
    print("micon: %s" % line)
    if fh:
        fh.write(json.dumps({"event": event, **fields}) + "\n")
        fh.flush()


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------

def selftest():
    checks = []

    def eq(name, got, want):
        ok = got == want
        checks.append(ok)
        print("%-30s %s (got %r, want %r)" %
              (name, "PASS" if ok else "FAIL", got, want))

    # Positive control: the frame logged by EXP-M8.C2a O4.
    peer = MiconPeer()
    reply = peer.handle(LOGGED_REQUEST)
    eq("logged frame answered", reply is not None, True)
    body = anw.parse_frame(reply)
    eq("reply control ACK", body[0], CTRL_ACK)
    eq("reply echoes command", body[1], 0x02)
    eq("reply BCC valid", anw.bcc(reply[2:-1]), reply[-1])
    eq("reply framed", (reply[0], reply[1], reply[-3], reply[-2]),
       (0x10, 0x02, 0x10, 0x03))
    eq("counters", (peer.requests, peer.replies, peer.bad), (1, 1, 0))

    # Every table rule produces a framed, BCC-valid, command-echoing reply.
    for rule in RULES:
        request = anw.build_frame(rule.prefix + b"\x11")
        got = MiconPeer().handle(request)
        ok = got is not None and anw.parse_frame(got)[0] == CTRL_ACK
        ok = ok and anw.parse_frame(got)[1] == rule.prefix[0]
        eq("table rule %s/0x%02x" % (rule.name, rule.prefix[0]), ok, True)

    # Negative control: a corrupted checksum must be rejected, not answered.
    bad = LOGGED_REQUEST[:-1] + bytes((LOGGED_REQUEST[-1] ^ 0xFF,))
    badpeer = MiconPeer()
    eq("corrupt BCC rejected", badpeer.handle(bad), None)
    eq("corrupt BCC logged", badpeer.bad, 1)
    eq("corrupt BCC no reply", badpeer.replies, 0)
    eq("bad STX rejected", MiconPeer().handle(b"\x10\x05" + LOGGED_REQUEST[2:]), None)

    # Unknown command is logged and not answered (never a fabricated NAK).
    unk = MiconPeer().handle(anw.build_frame(b"\x77\x00"))
    eq("unknown not answered", unk, None)

    # Forced NAK path exists and produces a valid frame (for testing only).
    nakpeer = MiconPeer()
    nakpeer.control("fail 02")
    nak = nakpeer.handle(LOGGED_REQUEST)
    eq("forced NAK framed", anw.parse_frame(nak)[0], CTRL_NAK)

    # Streaming: a frame split across reads is still one request, and two
    # frames in one read are two requests. DLE-stuffed payloads are safe.
    buf = bytearray()
    feed = []
    for chunk in (LOGGED_REQUEST[:3], LOGGED_REQUEST[3:]):
        buf.extend(chunk)
        feed.extend(extract_frames(buf))
    eq("split frame count", len(feed), 1)
    buf = bytearray(LOGGED_REQUEST * 2)
    eq("two frames in one read", len(extract_frames(buf)), 2)
    stuffed = anw.build_frame(b"\x02\x10\x00")
    buf = bytearray(stuffed)
    got = extract_frames(buf)
    eq("stuffed frame extracted", got[0][1].hex() if got else "", "021000")

    # Control socket commands.
    st = MiconPeer()
    eq("control status", st.control("status"),
       "status requests=0 bad=0 unknown=0 replies=0 pending=0")
    eq("control key", st.control("key MAP"),
       "queued key MAP 0x17")
    eq("control key raw", st.control("key 0x9c"), "queued key 0X9C 0x9c")
    eq("control bad key", st.control("key WAT").startswith("ERR"), True)
    eq("control unknown", st.control("wat").startswith("ERR"), True)
    eq("control nofail", st.control("nofail"), "nofail")

    passed = sum(checks)
    print("selftest: %d/%d PASS" % (passed, len(checks)))
    return 0 if passed == len(checks) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--socket", help="AF_UNIX chardev of the guest's sci1")
    ap.add_argument("--listen", action="store_true",
                    help="create and listen on --socket instead of connecting")
    ap.add_argument("--control", help="AF_UNIX control socket to create")
    ap.add_argument("--log", help="append JSON-lines event log")
    ap.add_argument("--duration", type=float, default=3600.0)
    ap.add_argument("--replay", help="file of whitespace-separated hex frames")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.socket:
        ap.error("--socket PATH is required (or use --selftest)")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
