#!/usr/bin/env python3
"""Shared host-side plumbing for the QEMU ``ze0`` peers (M8.H77).

This module owns only the parts the peers really share:

* the SLIP byte-stuffing / framing rules of ``bt.py`` (derived from
  ``BT_FW.dll`` fn 0x035c9374, C-7523);
* an AF_UNIX control-socket accept loop (``make_control`` / ``LinePeer``);
* a generic arity-checked command dispatcher (``dispatch``).

Each peer keeps its own command grammar and its own wire encoders.  The GPS
7-bit checksum, the panel's ANW DLE/BCC frames and the VCAN decoded-layer CAN
records are *not* routed through a shared helper: their grammars disagree, and
a shared frame builder would have to guess bytes.  No wire byte is changed by
this module.  Stdlib only.  Method and results:
  docs/experiments/EXP-2026-11-24-M8.H77-peerlib.md
"""

import select
import socket

# BT_FW.dll build B, fn 0x035c9374 (wired by M8.H55, C-7523).
END, ESC, ESC_END, ESC_ESC = 0xc0, 0xdb, 0xdc, 0xdd


def escape(data):
    """SLIP stuff a payload; the firmware stores 0xc0/0xdb verbatim."""
    out = bytearray()
    for b in data:
        if b == END:
            out += bytes((ESC, ESC_END))
        elif b == ESC:
            out += bytes((ESC, ESC_ESC))
        else:
            out.append(b)
    return bytes(out)


def unescape(data):
    """Inverse of escape(); an unknown escape sequence keeps the ESC byte."""
    out = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b == ESC and i + 1 < len(data):
            nxt = data[i + 1]
            if nxt == ESC_END:
                out.append(END)
            elif nxt == ESC_ESC:
                out.append(ESC)
            else:
                out.append(b)
                i += 1
                continue
            i += 2
        else:
            out.append(b)
            i += 1
    return bytes(out)


def frame(payload):
    """One SLIP frame with END delimiters on both sides."""
    return bytes((END,)) + escape(payload) + bytes((END,))


def split(stream, carry=None):
    """Split a SLIP byte stream on 0xc0; return (payloads, partial tail)."""
    carry = bytearray() if carry is None else bytearray(carry)
    out = []
    for b in stream:
        if b == END:
            if carry:
                out.append(unescape(bytes(carry)))
                carry.clear()
        else:
            carry.append(b)
    return out, carry


def dispatch(line, rules, state, empty="", unknown="ERR unknown command: %s",
             error=None):
    """Apply one control line through arity-checked ``(predicate, action)`` rules.

    ``predicate(cmd, parts)`` selects a rule; ``action(parts, state)`` returns
    the reply string, or ``None`` to fall through.  ``error``, when set, wraps
    every action in ``except error`` and formats ``ERR <message>`` exactly as
    the peers did before the shared loop.  This is command plumbing only: the
    verbs, their replies and their validation stay in the calling peer.
    """
    parts = line.strip().split()
    if not parts:
        return empty
    cmd = parts[0].lower()
    try:
        for predicate, action in rules:
            if predicate(cmd, parts):
                reply = action(parts, state)
                if reply is not None:
                    return reply
    except error as exc:
        return "ERR %s" % exc
    return unknown % cmd


def make_control(path, timeout=0.1):
    """Create (unlink + bind + listen) an AF_UNIX control socket."""
    try:
        import os
        os.unlink(path)
    except FileNotFoundError:
        pass
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    if timeout is not None:
        server.settimeout(timeout)
    server.bind(path)
    server.listen(1)
    return server


class LinePeer:
    """Shared control loop: one line in, one ``handler(conn, line)`` call.

    The handler owns the reply (some peers send ``OK/ERR`` lines, one only
    logs), so no peer grammar is encoded here.  ``split=False`` passes the
    whole read as one line for peers that treat a message as a unit.
    """

    def __init__(self, path, handler, timeout=0.1, recv=4096, split=True):
        self.server = make_control(path, timeout)
        self.handler = handler
        self.recv = recv
        self.split = split

    def poll(self):
        """Handle every pending control connection; return their count."""
        ready, _, _ = select.select([self.server], [], [], 0)
        if not ready:
            return 0
        conn, _ = self.server.accept()
        with conn:
            data = conn.recv(self.recv).decode("utf-8", "replace")
            lines = data.splitlines() if self.split else [data]
            for line in lines:
                self.handler(conn, line)
        return 1

    def close(self):
        self.server.close()


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
    payloads, tail = split(bytes.fromhex("c001dbdc02c003"))
    check("split payloads", payloads, [bytes((1, END, 2))])
    check("split tail", bytes(tail), b"\x03")

    rules = [
        (lambda c, p: c == "set" and len(p) == 2,
         lambda p, s: "set %s" % p[1]),
        (lambda c, p: c == "bad", lambda p, s: int(p[0])),
    ]
    state = {}
    check("dispatch empty", dispatch("", rules, state), "")
    check("dispatch hit", dispatch("set x", rules, state), "set x")
    check("dispatch arity falls through", dispatch("set x y", rules, state),
          "ERR unknown command: set")
    check("dispatch unknown", dispatch("wat", rules, state),
          "ERR unknown command: wat")
    check("dispatch custom empty", dispatch("", rules, state,
                                            empty="ERR empty command"),
          "ERR empty command")
    check("dispatch error wrapped",
          dispatch("bad", rules, state, error=ValueError).startswith("ERR"), True)

    # An AF_UNIX round-trip proves the shared accept loop works without QEMU.
    import os
    import tempfile
    import threading
    with tempfile.TemporaryDirectory(prefix="peerlib-") as td:
        path = os.path.join(td, "control.sock")
        seen = []

        def handler(conn, line):
            seen.append(line)
            conn.sendall(("OK %s\n" % line).encode())

        def client():
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            for _ in range(50):
                try:
                    sock.connect(path)
                    break
                except OSError:
                    import time
                    time.sleep(0.01)
            sock.sendall(b"status\n")
            seen.append(sock.recv(64).decode().strip())
            sock.close()

        peer = LinePeer(path, handler)
        t = threading.Thread(target=client)
        t.start()
        for _ in range(50):
            if peer.poll():
                break
            import time
            time.sleep(0.01)
        t.join(3.0)
        check("control round-trip", seen, ["status", "OK status"])
        peer.close()

    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    ap.error("peerlib.py is a library; import it from a peer")
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(main())
