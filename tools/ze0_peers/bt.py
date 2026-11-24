#!/usr/bin/env python3
"""Bluetooth module peer for the QEMU ``ze0`` machine (TODO M8.H56).

M8.H55 derived the wire format statically from ``BT_FW.dll``: the module on
``SCI8:`` speaks CSR BCSP in SLIP-style byte stuffing (END 0xc0, ESC 0xdb,
ESC_END 0xdc, ESC_ESC 0xdd, framer at EU2011 build-B ``fn 0x035c9374`` and
the 0xc0 emitter at ``fn 0x035c889c``), at 38400 8N1.  M8.H55 also measured
that a stock EU2011 boot writes **0 bytes** to ``sci8`` (PhoneBTA.exe fails
to import HCXMemory.dll), so the recommended stub is ``absent``.

This peer therefore defaults to an *absent* stub: it frames and logs bytes
but sends nothing.  A response table (``--table`` with ``trigger_hex
reply_hex`` lines, or the ``tx`` control command) enables a "minimal present"
experiment.  **No reply byte is claimed as verified**: the exact HOST_GEN/
BCCMD opcodes were not recovered from the images.

Usage:
  bt.py --selftest
  bt.py --socket PATH [--listen] [--table FILE] [--control PATH]
        [--duration SECONDS] [--mode absent|minimal]

Stdlib only.  Method and results:
  docs/experiments/EXP-2026-11-22-M8.H56-bt-peer.md
  docs/firmware/bt-wire.md
"""

import argparse
import os
import select
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import peerlib  # noqa: E402  (shared SLIP framing and control loop)

# From BT_FW.dll build B, fn 0x035c9374 (wired by M8.H55, C-7523).
END, ESC, ESC_END, ESC_ESC = peerlib.END, peerlib.ESC, peerlib.ESC_END, peerlib.ESC_ESC


escape = peerlib.escape
unescape = peerlib.unescape
frame = peerlib.frame
frames = peerlib.split


class Table:
    """Trigger-prefix -> reply-payload rules, loaded from hex text lines."""

    def __init__(self, rules=()):
        self.rules = []
        for trigger, reply in rules:
            self.rules.append((bytes.fromhex(trigger.strip()),
                               bytes.fromhex(reply.strip())))

    def respond(self, payload):
        for trigger, reply in self.rules:
            if payload.startswith(trigger):
                return frame(reply)
        return None


def load_table(path):
    with open(path, encoding="ascii") as fh:
        return Table(line.split()[:2] for line in fh
                     if line.strip() and not line.startswith("#"))


def control_commands(line, state):
    """Apply one control line and return a printable reply (M8.H7-style).

    The verbs and their replies are unchanged; only the arity/verb dispatch
    now goes through peerlib.dispatch (M8.H77).
    """
    def mode(cmd, parts):
        return cmd in ("mode", "stub") and len(parts) == 2

    def set_mode(parts, state):
        if parts[1].lower() not in ("absent", "minimal"):
            return "ERR mode must be absent or minimal"
        state["mode"] = parts[1].lower()
        return "mode %s" % state["mode"]

    def status(cmd, parts):
        return cmd == "status"

    def get_status(parts, state):
        return "status mode=%s frames=%d tx=%d" % (
            state["mode"], state["frames"], state["tx"])

    def tx(cmd, parts):
        return cmd == "tx" and len(parts) == 2

    def queue_tx(parts, state):
        try:
            state["queue"].append(bytes.fromhex(parts[1]))
        except ValueError:
            return "ERR tx is not hex"
        return "queued %s" % parts[1]

    return peerlib.dispatch(line, [(mode, set_mode), (status, get_status),
                                   (tx, queue_tx)], state)


def run(args):
    table = load_table(args.table) if args.table else Table()
    state = {"mode": args.mode, "frames": 0, "tx": 0, "queue": []}
    server = None
    if args.listen:
        try:
            os.unlink(args.socket)
        except FileNotFoundError:
            pass
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(args.socket)
        server.listen(1)
        server.settimeout(1.0)
        conn, _ = server.accept()
    else:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(1.0)
        conn.connect(args.socket)
    conn.settimeout(0.2)
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

    carry = bytearray()
    deadline = time.monotonic() + args.duration
    try:
        while time.monotonic() < deadline:
            if ctrl is not None:
                ready, _, _ = select.select([ctrl], [], [], 0)
                if ready:
                    client, _ = ctrl.accept()
                    with client:
                        line = client.recv(1024).decode("utf-8", "replace")
                        print("bt: control %s -> %s" %
                              (line.strip(), control_commands(line, state)),
                              flush=True)
            while state["queue"]:
                data = state["queue"].pop(0)
                conn.sendall(data)
                state["tx"] += 1
                print("bt: tx %s" % data.hex(), flush=True)
            try:
                data = conn.recv(4096)
            except socket.timeout:
                continue
            if not data:
                break
            print("bt: rx %s" % data.hex(), flush=True)
            payloads, carry = frames(data, carry)
            for payload in payloads:
                state["frames"] += 1
                print("bt: frame %s" % payload.hex(), flush=True)
                if state["mode"] == "minimal":
                    reply = table.respond(payload)
                    if reply:
                        conn.sendall(reply)
                        state["tx"] += 1
                        print("bt: tx %s" % reply.hex(), flush=True)
    finally:
        conn.close()
        for s in (ctrl, server):
            if s is not None:
                s.close()
    return 0


def selftest():
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" %
              ("ok  " if ok else "FAIL", label, got, want))

    check("escape", escape(bytes((1, END, ESC, 2))).hex(), "01dbdcdbdd02")
    check("unescape", unescape(bytes((1, ESC, ESC_END, ESC, ESC_ESC, 2))),
          bytes((1, END, ESC, 2)))
    check("bad escape keeps ESC", unescape(bytes((ESC, 0x11))), bytes((ESC, 0x11)))
    check("frame", frame(b"\x01\x02").hex(), "c00102c0")
    payloads, tail = frames(bytes.fromhex("c001dbdc02c003"))
    check("stream split", payloads, [bytes((1, END, 2))])
    check("stream tail", bytes(tail), b"\x03")
    table = Table([("01", "02ff")])
    check("table hit", table.respond(b"\x01\x99"), b"\xc0\x02\xff\xc0")
    check("table miss", table.respond(b"\x09"), None)
    st = {"mode": "absent", "frames": 0, "tx": 0, "queue": []}
    check("control mode", control_commands("mode minimal", st), "mode minimal")
    check("control status", control_commands("status", st),
          "status mode=minimal frames=0 tx=0")
    check("control tx hex", control_commands("tx c00102c0", st),
          "queued c00102c0")
    check("control bad hex", control_commands("tx zz", st).startswith("ERR"), True)

    # A socketpair round-trip proves the peer's framer works over a chardev
    # socket without QEMU (positive control for the I/O path).
    import threading
    a, b = socket.socketpair()
    got = []

    def reader():
        a.settimeout(2.0)
        got.append(a.recv(64))

    t = threading.Thread(target=reader)
    t.start()
    b.sendall(frame(b"\x01\x02"))
    t.join(3.0)
    check("socketpair round-trip", got[0] if got else b"", b"\xc0\x01\x02\xc0")
    a.close()
    b.close()

    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--socket", help="AF_UNIX socket of the --serial-peer chardev")
    ap.add_argument("--listen", action="store_true",
                    help="bind the socket as a server (QEMU connects)")
    ap.add_argument("--table", help="hex text file: TRIGGER_HEX REPLY_HEX per line")
    ap.add_argument("--mode", choices=("absent", "minimal"), default="absent",
                    help="absent logs only (default); minimal uses the table")
    ap.add_argument("--duration", type=float, default=120.0)
    ap.add_argument("--control", help="AF_UNIX control socket for ze0_ui.py")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.socket:
        ap.error("--socket PATH is required without --selftest")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
