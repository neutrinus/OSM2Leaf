#!/usr/bin/env python3
"""Compare two ``-M ze0`` run directories channel by channel (TODO M8.H6).

A run directory is the trace left by one boot.  Four channels are compared:

===============  ==================  ===========================================
channel          file                content
===============  ==================  ===========================================
serial           ``serial.log``      raw QEMU ``-serial file:`` bytes
dbgmsg           ``dbgmsg.log``      kernel debug text, LF-normalised
sd_reads         ``sd-reads.txt``    ordered SD block reads, one per line
vram             ``vram.sha256``     ``<sha256>  <guest milestone>``
===============  ==================  ===========================================

On ``-M ze0`` the kernel debug-string sink is serial port 0 (C-6240, M8.B6), so
``serial.log`` and ``dbgmsg.log`` come from the same capture: the collector only
normalises line endings for the second.  M8.H6 records this coupling rather
than pretending the two channels are independent.

``sd-reads.txt`` is produced from a ``sdhi-trace=on,hpbdmac-trace=on`` log with
``tools/ze0_sdhost.py decode_dma``; each line is one read in the order the
guest issued it.  ``vram.sha256`` is the hash of a VRAM dump taken at a fixed
guest milestone (not at a wall-clock timeout).

For each channel the tool prints ``SAME`` with a short digest, or ``DIFFERENT``
with the *first* difference (byte offset / line index / hash+marker).  A missing
channel file in either directory is a difference, never a silent pass.

Exit status: 0 every channel equal, 1 at least one channel different, 2 usage
error (fewer than two directories, or a directory does not exist).

Usage:
    python3 tools/ze0_rundiff.py RUN1 RUN2
    python3 tools/ze0_rundiff.py --selftest

Method and measurements: docs/experiments/EXP-2026-11-22-M8.H6-run-determinism.md
"""

import argparse
import hashlib
import os
import sys
import tempfile

CHANNELS = ("serial", "dbgmsg", "sd_reads", "vram")
FILES = {
    "serial": "serial.log",
    "dbgmsg": "dbgmsg.log",
    "sd_reads": "sd-reads.txt",
    "vram": "vram.sha256",
}


class Channel:
    """One loaded channel: ``kind`` is bytes, lines or vram."""

    def __init__(self, kind, value=None, missing=False, path=""):
        self.kind = kind
        self.value = value
        self.missing = missing
        self.path = path

    def digest(self):
        if self.missing:
            return "MISSING"
        if self.kind == "vram":
            h, marker = self.value
            return "sha256:%s marker:%s" % (h[:16], marker or "-")
        if self.kind == "lines":
            joined = "\n".join(self.value).encode("utf-8", "replace")
            return "%d lines sha256:%s" % (len(self.value), hashlib.sha256(joined).hexdigest()[:16])
        return "%d bytes sha256:%s" % (len(self.value), hashlib.sha256(self.value).hexdigest()[:16])


def load_channel(directory, name):
    path = os.path.join(directory, FILES[name])
    if not os.path.isfile(path):
        return Channel("bytes", missing=True, path=path)
    if name == "vram":
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    parts = line.split(None, 1)
                    return Channel("vram", (parts[0], parts[1].strip() if len(parts) > 1 else ""), path=path)
        return Channel("vram", ("", ""), path=path)
    if name == "sd_reads":
        with open(path, encoding="utf-8", errors="replace") as fh:
            return Channel("lines", [line.rstrip("\r\n") for line in fh], path=path)
    with open(path, "rb") as fh:
        return Channel("bytes", fh.read(), path=path)


def first_byte_diff(a, b):
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n if len(a) != len(b) else None


def context(raw, at, before=28, after=44):
    lo = max(0, at - before)
    hi = min(len(raw), at + after)
    return repr(raw[lo:hi])


def compare_channel(a, b):
    """Return ``(same, detail_lines)`` for one channel."""
    if a.missing or b.missing:
        who = "both" if a.missing and b.missing else ("A" if a.missing else "B")
        return False, ["MISSING in %s: %s" % (who, (a if a.missing else b).path)]
    if a.kind != b.kind:
        return False, ["different channel kinds: %s vs %s" % (a.kind, b.kind)]
    if a.kind == "vram":
        if a.value == b.value:
            return True, []
        ha, ma = a.value
        hb, mb = b.value
        out = []
        if ha != hb:
            out.append("hash A: %s" % ha)
            out.append("hash B: %s" % hb)
        if ma != mb:
            out.append("marker A: %s" % ma)
            out.append("marker B: %s" % mb)
        return False, out
    if a.kind == "lines":
        n = min(len(a.value), len(b.value))
        for i in range(n):
            if a.value[i] != b.value[i]:
                return False, ["first differing line %d" % i,
                               "  A: %s" % a.value[i],
                               "  B: %s" % b.value[i]]
        if len(a.value) != len(b.value):
            i = n
            longer = a if len(a.value) > len(b.value) else b
            return False, ["first differing line %d (one list ends)" % i,
                           "  %s: %s" % ("A" if longer is a else "B", longer.value[i])]
        return True, []
    at = first_byte_diff(a.value, b.value)
    if at is None:
        return True, []
    return False, ["first differing byte %d" % at,
                   "  A: %s" % context(a.value, at),
                   "  B: %s" % context(b.value, at)]


def report(a_dir, b_dir):
    """Print the full comparison; return (all_same, results)."""
    results = {}
    print("A: %s" % a_dir)
    print("B: %s" % b_dir)
    for name in CHANNELS:
        a = load_channel(a_dir, name)
        b = load_channel(b_dir, name)
        same, detail = compare_channel(a, b)
        results[name] = (same, detail)
        print("%-11s %-9s A: %s" % (FILES[name], "SAME" if same else "DIFFERENT", a.digest()))
        if not same:
            for line in detail:
                print("    " + line)
    ok = all(v[0] for v in results.values())
    print("verdict: %s (%d/%d channels equal)"
          % ("SAME" if ok else "DIFFERENT", sum(1 for v in results.values() if v[0]), len(CHANNELS)))
    return ok, results


# ---------------------------------------------------------------------------
# Offline selftest: two fabricated run directories, no vendor bytes.
# ---------------------------------------------------------------------------

def _fabricate(root, name, serial=b"Windows CE\r\nAppLch >> Start\r\n",
               dbgmsg=b"Windows CE\nAppLch >> Start\n",
               reads=("CMD0 arg 0x0 512\n", "CMD18 arg 0x1234 4096\n"),
               vram=("a" * 64, "MSG#2")):
    path = os.path.join(root, name)
    os.makedirs(path)
    with open(os.path.join(path, FILES["serial"]), "wb") as fh:
        fh.write(serial)
    with open(os.path.join(path, FILES["dbgmsg"]), "wb") as fh:
        fh.write(dbgmsg)
    with open(os.path.join(path, FILES["sd_reads"]), "w") as fh:
        fh.write("".join(reads))
    with open(os.path.join(path, FILES["vram"]), "w") as fh:
        fh.write("%s  %s\n" % vram)
    return path


def selftest():
    fails = []

    def check(label, cond):
        print("%s %s" % ("ok  " if cond else "FAIL", label))
        if not cond:
            fails.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        a = _fabricate(tmp, "a")
        b = _fabricate(tmp, "b")
        ok, res = report(a, b)
        check("two identical fabricated runs compare SAME", ok and all(v[0] for v in res.values()))
        check("main() exits 0 for identical runs", main([a, b]) == 0)

        # Each channel, mutated on its own, must fail and be named as the cause.
        cases = [
            ("serial", dict(serial=b"Windows CE\r\nAppLch >> Other\r\n")),
            ("dbgmsg", dict(dbgmsg=b"Windows CE\nAppLch >> Other\n")),
            ("sd_reads", dict(reads=("CMD0 arg 0x0 512\n", "CMD17 arg 0x9999 512\n"))),
            ("vram", dict(vram=("b" * 64, "MSG#2"))),
        ]
        for name, kw in cases:
            other = _fabricate(tmp, "diff-" + name, **kw)
            ok, res = report(a, other)
            reasons = [n for n, (good, _d) in res.items() if not good]
            check("mutating %s is detected and named" % name,
                  not ok and name in reasons and bool(res[name][1]))
            check("main() exits 1 when %s differs" % name, main([a, other]) == 1)

        # The guest milestone is part of the vram channel, not just the hash.
        other = _fabricate(tmp, "diff-marker", vram=("a" * 64, "MSG#3"))
        ok, res = report(a, other)
        check("a different guest milestone is detected", not ok and not res["vram"][0])

        # A missing channel must be reported, never treated as equal.
        partial = os.path.join(tmp, "partial")
        os.makedirs(partial)
        ok, res = report(a, partial)
        check("a missing channel is reported as different", not ok and all(not v[0] for v in res.values()))
        check("main() exits 1 for an incomplete run directory", main([a, partial]) == 1)

        check("main() exits 2 with fewer than two directories", main([a]) == 2)
        check("main() exits 2 for a non-existent directory", main([a, os.path.join(tmp, "nope")]) == 2)

        check("first differing byte offset is exact",
              first_byte_diff(b"abcX", b"abcY") == 3)
        check("equal byte strings have no first difference",
              first_byte_diff(b"abc", b"abc") is None)
        check("length-only byte difference is caught",
              first_byte_diff(b"abc", b"abcd") == 3)

    print("selftest: %d failed" % len(fails))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dirs", nargs="*", help="two run directories to compare (A is the reference)")
    ap.add_argument("--selftest", action="store_true", help="offline test with fabricated run dirs")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if len(args.dirs) != 2:
        print("ze0_rundiff: need exactly two run directories, got %d" % len(args.dirs),
              file=sys.stderr)
        return 2
    for d in args.dirs:
        if not os.path.isdir(d):
            print("ze0_rundiff: no such directory: %s" % d, file=sys.stderr)
            return 2
    ok, _results = report(args.dirs[0], args.dirs[1])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
