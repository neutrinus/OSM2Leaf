#!/usr/bin/env python3
"""Boot probe: run the ZE0 Windows CE kernel image under stock QEMU (SH-4A).

Stdlib only; needs ``qemu-system-sh4`` (Debian/Ubuntu: ``qemu-system-misc``).

The SD image carries no bootloader (the IPL lives in on-board flash), so the
probe plays the bootloader itself: it copies the kernel CE image (B or C) to
its physical load address (``physfirst & 0x1fffffff``), the application
image A to its own, sets the PC to the ``nk.exe`` entry point and runs
QEMU's empty ``none`` machine with an ``sh7785`` (SH-4A) CPU and plain RAM.
No SoC peripheral is modelled, so every register access is logged by QEMU
as an invalid access. The probe prints those accesses in first-seen order,
the CPU exceptions and the PC where the kernel ended up. That list is the
peripheral work-list for a full-system emulator
(see docs/research/full-system-emulation.md).

``--patch VA=HEX`` writes bytes at a kernel/app VA before booting, e.g. to
NOP a polling branch (``0x88048b70=0900`` skips the ``0xffe70808`` poll in
image B).

Usage:
  ce_qemu_probe.py IMAGE [--kernel 0x3e00200] [--app 0x200200]
                   [--mem 512M] [--seconds 4] [--patch VA=HEX ...]
                   [--workdir DIR] [--qemu qemu-system-sh4]

IMAGE may be the full SD image or its first ~110 MB (``head -c 110000000``).
Nothing is written next to the image; outputs go to --workdir (a new
temporary directory by default).
"""
import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cerom import CERom  # noqa: E402

READ_LIMIT = 110_000_000  # the CE images end before 0x5e00000

_ACCESS = re.compile(r"Invalid (read|write) at addr 0x([0-9A-Fa-f]+), size (\d+)")
_EXC = re.compile(r"exception 0x([0-9a-f]+) \[([a-z_]+)\] raised")
_PC = re.compile(r"\bpc=0x([0-9a-f]+)")


def summarize_log(text):
    """Return (accesses, exceptions) from a QEMU ``-d unimp,guest_errors,int`` log.

    ``accesses`` lists unique ``(kind, addr)`` in first-seen order; cache
    address-array writes (``0xf0000000``-``0xf7ffffff``) collapse into one
    entry per array (``addr & 0xff000000``). ``exceptions`` lists
    ``(code, name, pc)`` in order.
    """
    seen, accesses, exceptions = set(), [], []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = _ACCESS.search(line)
        if m:
            addr = int(m.group(2), 16)
            if 0xF0000000 <= addr < 0xF8000000:
                addr &= 0xFF000000
            key = (m.group(1), addr)
            if key not in seen:
                seen.add(key)
                accesses.append(key)
            continue
        m = _EXC.search(line)
        if m:
            pc = None
            if i + 1 < len(lines):
                p = _PC.search(lines[i + 1])
                pc = int(p.group(1), 16) if p else None
            exceptions.append((int(m.group(1), 16), m.group(2), pc))
    return accesses, exceptions


def ce_image(data, start):
    rom = CERom(data, start)
    first, last = rom.hdr["physfirst"], rom.hdr["physlast"]
    blob = bytearray(data[start:start + (last - first)])
    return rom, first, blob


def nk_entry(rom):
    for m in rom.modules():
        if m["name"] == "nk.exe":
            e = rom.e32(m)
            return e["vbase"] + e["entryrva"]
    raise ValueError("nk.exe not in the kernel image")


def apply_patch(images, va, raw):
    for first, blob in images:
        if first <= va and va + len(raw) <= first + len(blob):
            blob[va - first:va - first + len(raw)] = raw
            return
    raise ValueError("patch VA 0x%08x is outside the loaded images" % va)


def hmp(sock_path, cmd, timeout=5.0):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(sock_path)
    out = b""
    try:
        time.sleep(0.2)
        out += s.recv(65536)
        s.sendall(cmd.encode() + b"\n")
        time.sleep(0.5)
        out += s.recv(65536)
    except socket.timeout:
        pass
    finally:
        s.close()
    return out.decode("latin1")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("image")
    ap.add_argument("--kernel", type=lambda x: int(x, 0), default=0x3E00200,
                    help="CE image start of the kernel image (B 0x3e00200, C 0x5200200)")
    ap.add_argument("--app", type=lambda x: int(x, 0), default=0x200200,
                    help="CE image start of the application image A (0 = do not load)")
    ap.add_argument("--mem", default="512M")
    ap.add_argument("--seconds", type=float, default=4.0)
    ap.add_argument("--patch", action="append", default=[], metavar="VA=HEX")
    ap.add_argument("--workdir")
    ap.add_argument("--qemu", default="qemu-system-sh4")
    a = ap.parse_args(argv)

    if not shutil.which(a.qemu):
        sys.exit("%s not found (install qemu-system-misc)" % a.qemu)
    with open(a.image, "rb") as f:
        data = f.read(READ_LIMIT)

    krom, kfirst, kblob = ce_image(data, a.kernel)
    images = [(kfirst, kblob)]
    if a.app:
        _arom, afirst, ablob = ce_image(data, a.app)
        images.append((afirst, ablob))
    entry = nk_entry(krom)
    for p in a.patch:
        va, hx = p.split("=")
        apply_patch(images, int(va, 0), bytes.fromhex(hx))

    work = a.workdir or tempfile.mkdtemp(prefix="ce_qemu_probe_")
    os.makedirs(work, exist_ok=True)
    cmd = [a.qemu, "-M", "none", "-cpu", "sh7785", "-m", a.mem, "-nographic",
           "-serial", "none", "-monitor", "unix:%s,server,nowait" % os.path.join(work, "hmp.sock")]
    for i, (first, blob) in enumerate(images):
        path = os.path.join(work, "image%d.bin" % i)
        with open(path, "wb") as f:
            f.write(blob)
        cmd += ["-device", "loader,file=%s,addr=0x%x,force-raw=on" % (path, first & 0x1FFFFFFF)]
        print("load   0x%08x..0x%08x  (VA 0x%08x, %d bytes)"
              % (first & 0x1FFFFFFF, (first & 0x1FFFFFFF) + len(blob), first, len(blob)))
    log = os.path.join(work, "qemu.log")
    cmd += ["-device", "loader,addr=0x%x,cpu-num=0" % entry,
            "-d", "unimp,guest_errors,int", "-D", log]
    print("entry  0x%08x (nk.exe)" % entry)

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(a.seconds)
        regs = ""
        try:
            regs = hmp(os.path.join(work, "hmp.sock"), "info registers")
        except OSError as e:
            regs = "(monitor unavailable: %s)" % e
    finally:
        proc.kill()
        proc.wait()

    with open(log, "r", errors="replace") as f:
        accesses, exceptions = summarize_log(f.read())
    print("\nunmodelled register accesses (first-seen order): %d" % len(accesses))
    for kind, addr in accesses:
        print("  %-5s 0x%08x" % (kind, addr))
    print("\nexceptions: %d" % len(exceptions))
    for code, name, pc in exceptions[:20]:
        print("  0x%03x %-20s pc=%s" % (code, name, "0x%08x" % pc if pc is not None else "?"))
    m = _PC.search(regs)
    print("\nfinal pc: %s" % ("0x" + m.group(1) if m else "unknown"))
    print("workdir: %s" % work)
    return 0


if __name__ == "__main__":
    sys.exit(main())
