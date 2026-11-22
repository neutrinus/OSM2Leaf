#!/usr/bin/env python3
"""Raw byte peer for the QEMU ``ze0`` external UARTs (TODO M8.H3).

``serial_uat.dll`` talks to the VCAN sub-microcontroller on ``UAT3:`` at
230400 bps.  Its wire framing is still UNKNOWN (M8.H49, C-7469), so this peer
deliberately carries **raw bytes**: it does not invent a start byte, length,
checksum or terminator.  QEMU owns the 16-bit register file and the RX FIFO;
this program only moves bytes between an AF_UNIX socket and a host file or
control client.

Usage:
  ze0_peers/uart.py --selftest
  ze0_peers/uart.py --socket PATH --listen [--dump FILE] [--control PATH]
                    [--rx HEX] [--rate HZ]

The control socket accepts ``send HEX``, ``hex HEX``, ``on``, ``off`` and
``status`` so ``tools/ze0_ui.py`` can script it.  Stdlib only.
"""

from __future__ import annotations

import argparse
import os
import select
import socket
import sys
import time
from pathlib import Path


class UartPeer:
    """Move bytes to/from one chardev socket; no framing (M8.H49)."""

    def __init__(self) -> None:
        self.guest: socket.socket | None = None
        self.dump = None
        self.enabled = True
        self.tx_bytes = 0
        self.rx_bytes = 0

    def set_dump(self, path: str | None) -> None:
        if path:
            self.dump = open(path, "ab")

    def send(self, data: bytes) -> int:
        """Host -> guest (the guest's RX FIFO)."""
        if not data or not self.enabled or self.guest is None:
            return 0
        sent = self.guest.send(data)
        self.rx_bytes += sent
        return sent

    def receive(self, data: bytes) -> None:
        """Guest -> host (the guest's THR writes)."""
        if not data:
            return
        self.tx_bytes += len(data)
        if self.dump:
            self.dump.write(data)
            self.dump.flush()

    def serve(self, path: str, listen: bool, control: str | None,
              initial: bytes, rate: float, seconds: float) -> None:
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

        ctrl_srv = None
        if control:
            c = Path(control)
            if c.exists():
                c.unlink()
            ctrl_srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            ctrl_srv.bind(control)
            ctrl_srv.listen(1)

        deadline = time.monotonic() + seconds
        next_tx = time.monotonic() + 1.0 / max(rate, 0.01)
        ctrl = None
        try:
            while time.monotonic() < deadline:
                fds = [x for x in (srv, ctrl_srv, self.guest, ctrl) if x]
                if not fds:
                    break
                ready, _, _ = select.select(fds, [], [], 0.1)
                for fd in ready:
                    if fd is srv:
                        self.guest, _ = srv.accept()
                    elif fd is ctrl_srv:
                        if ctrl:
                            ctrl.close()
                        ctrl, _ = ctrl_srv.accept()
                    elif fd is ctrl:
                        msg = ctrl.recv(4096)
                        if not msg:
                            ctrl.close()
                            ctrl = None
                            continue
                        self._control(ctrl, msg.decode("ascii", "replace").strip())
                    elif fd is self.guest:
                        msg = self.guest.recv(4096)
                        if not msg:
                            self.guest.close()
                            self.guest = None
                        else:
                            self.receive(msg)
                if initial and self.guest and time.monotonic() >= next_tx:
                    self.send(initial)
                    next_tx = time.monotonic() + 1.0 / max(rate, 0.01)
        finally:
            for s in (self.guest, ctrl, srv, ctrl_srv):
                if s:
                    s.close()
            if self.dump:
                self.dump.close()

    def _control(self, conn: socket.socket, line: str) -> None:
        verb, _, arg = line.partition(" ")
        if verb == "send" or verb == "hex":
            try:
                data = bytes.fromhex(arg.replace("0x", ""))
            except ValueError:
                conn.sendall(b"ERR bad hex\n")
                return
            self.send(data)
            conn.sendall(("OK %d\n" % len(data)).encode())
        elif verb == "on":
            self.enabled = True
            conn.sendall(b"OK on\n")
        elif verb == "off":
            self.enabled = False
            conn.sendall(b"OK off\n")
        elif verb == "status":
            conn.sendall(("status enabled=%d tx=%d rx=%d\n" %
                          (self.enabled, self.tx_bytes, self.rx_bytes)).encode())
        else:
            conn.sendall(b"ERR unknown command\n")


def selftest() -> int:
    """Bidirectional transfer over an AF_UNIX pair, plus two negative checks."""
    import tempfile

    checks: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory(prefix="ze0-uart-") as td:
        path = os.path.join(td, "uart.sock")
        peer = UartPeer()
        dump = os.path.join(td, "guest-tx.bin")
        peer.set_dump(dump)
        host = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        host.bind(path)
        host.listen(1)

        import threading

        t = threading.Thread(target=peer.serve,
                             args=(path, False, None, b"", 1.0, 1.5),
                             daemon=True)
        t.start()
        conn, _ = host.accept()
        conn.sendall(bytes.fromhex("01 02 03 04"))
        got = peer_received(peer)
        checks.append(("guest TX reaches host", got == bytes.fromhex("01020304")))
        checks.append(("peer sends raw bytes to guest",
                       peer.send(bytes.fromhex("aa 55")) == 2))
        checks.append(("guest reads peer bytes",
                       conn.recv(2) == bytes.fromhex("aa55")))
        checks.append(("negative: empty send is a no-op", peer.send(b"") == 0))
        conn.close()
        t.join(2)
        host.close()
        checks.append(("negative: invalid hex refused",
                       not accepts_bad_hex(peer)))
    ok = all(v for _, v in checks)
    for name, value in checks:
        print("%-40s %s" % (name, "PASS" if value else "FAIL"))
    print("selftest: %d/%d" % (sum(v for _, v in checks), len(checks)))
    return 0 if ok else 1


def peer_received(peer: UartPeer) -> bytes:
    """Wait for the guest bytes to be logged by the peer dump."""
    for _ in range(30):
        if peer.tx_bytes:
            return Path(peer.dump.name).read_bytes() if peer.dump else b""
        time.sleep(0.01)
    return b""


def accepts_bad_hex(peer: UartPeer) -> bool:
    class Fake:
        def __init__(self) -> None:
            self.out = b""

        def sendall(self, data: bytes) -> None:
            self.out += data

    f = Fake()
    peer._control(f, "send zz")  # type: ignore[arg-type]
    return f.out.startswith(b"OK")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--socket", help="AF_UNIX socket of the uat3/uat4 chardev")
    ap.add_argument("--listen", action="store_true",
                    help="listen on --socket (QEMU connects as a client)")
    ap.add_argument("--dump", help="append guest TX bytes to this file")
    ap.add_argument("--control", help="AF_UNIX control socket for ze0_ui.py")
    ap.add_argument("--rx", default="", help="hex bytes to send periodically")
    ap.add_argument("--rate", type=float, default=1.0)
    ap.add_argument("--seconds", type=float, default=3600.0)
    ap.add_argument("--selftest-only", action="store_true",
                    help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.socket:
        ap.error("--socket is required outside --selftest")
    peer = UartPeer()
    peer.set_dump(a.dump)
    peer.serve(a.socket, a.listen, a.control,
               bytes.fromhex(a.rx.replace(" ", "")), a.rate, a.seconds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
