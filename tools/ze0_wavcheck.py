#!/usr/bin/env python3
"""Capture the ZE0 SSI PCM path to a WAV and count silent/non-silent samples.

The two modes differ by one QEMU machine option:

    python3 tools/ze0_wavcheck.py off   # no playback: 44-byte WAV, 0 data bytes
    python3 tools/ze0_wavcheck.py on    # ssi-selftest=4096: non-silent data

``on`` is a **model positive control**, not guest playback: the SSI device
pushes a known PCM pattern through HPB-DMAC channel 12.  The guest-playback
gap is recorded in EXP-2026-11-22-M8.H46.

Stdlib only.  Needs a QEMU built with tools/qemu-ze0/patches/ (including
ze0-h46-ssi-audio.patch), an EU2011 head image and a card overlay.
"""

import argparse
import os
import socket
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
DEFAULT_QEMU = HOME + "/.cache/qemu-ze0/build/qemu-system-sh4"
DEFAULT_IMAGE = "archive/head256.img"
DEFAULT_CARD = "archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img"
DEFAULT_WORK = HOME + "/projekty/leafre-work/scratch/m8.h46-ssi-audio"
BOOT_MS = ("kernel-off=0x3e00200,app-off=0x200200,dbgmsg=0x880404f4,"
           "verinf=QSD-302-100,mapdb=16-16")


def machine_option(mode):
    """The one machine option the two runs differ by."""
    if mode not in ("off", "on"):
        raise ValueError(mode)
    return ",ssi-selftest=4096" if mode == "on" else ""


def results(out):
    """Return (file bytes, non-zero data bytes, rate, channels, width).

    QEMU's wav backend leaves the RIFF/data sizes at zero when the process
    is stopped with HMP ``quit``, so read the data area and the fmt chunk
    directly instead of going through the ``wave`` module.
    """
    with open(out, "rb") as f:
        raw = f.read()
    if len(raw) < 44 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("not a WAV file: " + out)
    data = raw[44:]
    info = (int.from_bytes(raw[24:28], "little"),
            int.from_bytes(raw[22:24], "little"),
            int.from_bytes(raw[34:36], "little") // 8)
    return len(raw), sum(1 for b in data if b), info


def prepare(image, card, ipl, work):
    """Create the IPL patch and card overlay once, if they are missing."""
    os.makedirs(work, exist_ok=True)
    if not os.path.isfile(ipl):
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        subprocess.run([sys.executable, os.path.join(repo, "tools", "ze0_ipl.py"),
                        "patch", image, "-o", ipl], check=True)
    overlay = os.path.join(work, "card.qcow2")
    if not os.path.isfile(overlay):
        subprocess.run(["qemu-img", "create", "-q", "-f", "qcow2",
                        "-b", os.path.abspath(card), "-F", "raw", overlay, "8G"],
                       check=True)
    return overlay


def run(mode, qemu, image, card, ipl, work, seconds, overlay):
    directory = os.path.join(work, "wavcheck-" + mode)
    os.makedirs(directory, exist_ok=True)
    out = os.path.join(directory, "out.wav")
    hmp = os.path.join(directory, "hmp.sock")
    for path in (out, hmp):
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass

    opt = machine_option(mode)
    cmd = [
        qemu,
        "-audiodev", "wav,id=w,path=" + out
                     + ",out.frequency=48000,out.channels=2,out.format=s16,"
                       "out.fixed-settings=on",
        "-M", "ze0," + BOOT_MS + ",ipl-patch=" + ipl + ",ssi-audio=w" + opt,
        "-kernel", image,
        "-nographic",
        "-serial", "file:" + os.path.join(directory, "serial.log"),
        "-monitor", "unix:" + hmp + ",server,nowait",
        "-icount", "shift=0,sleep=off",
        "-drive", "if=sd,index=0,file=" + overlay,
        "-d", "unimp,guest_errors,int,invalid_mem",
        "-D", os.path.join(directory, "qemu.log"),
    ]
    with open(os.path.join(directory, "stdout.txt"), "wb") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        time.sleep(seconds)
        for _ in range(20):
            try:
                sock = socket.socket(socket.AF_UNIX)
                sock.connect(hmp)
                sock.sendall(b"quit\n")
                sock.close()
                break
            except OSError:
                time.sleep(0.5)
        proc.wait(timeout=30)
    return out


def selftest():
    assert machine_option("off") == ""
    assert machine_option("on") == ",ssi-selftest=4096"
    try:
        machine_option("bad")
    except ValueError:
        pass
    else:
        raise AssertionError("bad mode accepted")
    print("ze0_wavcheck selftest: mode mapping OK", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", nargs="?", choices=("off", "on"))
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--qemu", default=DEFAULT_QEMU)
    ap.add_argument("--image", default=DEFAULT_IMAGE)
    ap.add_argument("--card", default=DEFAULT_CARD)
    ap.add_argument("--ipl", default=None)
    ap.add_argument("--work", default=DEFAULT_WORK)
    ap.add_argument("--seconds", type=int, default=12)
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return 0
    if args.mode is None:
        ap.error("mode is required (off or on)")
    if not os.access(args.qemu, os.X_OK):
        sys.exit("ze0_wavcheck: QEMU not found: " + args.qemu)
    for path in (args.image, args.card):
        if not os.path.isfile(path):
            sys.exit("ze0_wavcheck: sample not found: " + path)
    ipl = args.ipl or os.path.join(args.work, "ipl.txt")
    overlay = prepare(args.image, args.card, ipl, args.work)
    out = run(args.mode, args.qemu, args.image, args.card, ipl, args.work,
              args.seconds, overlay)
    size, nz, info = results(out)
    print("%s: wav=%d bytes, non-zero data=%d, rate=%d, channels=%d, width=%d"
          % (args.mode, size, nz, *info))
    if args.mode == "off" and (nz != 0):
        sys.exit("ze0_wavcheck: negative control was not silent")
    if args.mode == "on" and (nz == 0):
        sys.exit("ze0_wavcheck: positive control produced no PCM")
    return 0


if __name__ == "__main__":
    sys.exit(main())
