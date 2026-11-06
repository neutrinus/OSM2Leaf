#!/usr/bin/env python3
"""Build and run the host self-test of the RP2040 SD lock tool.

``tools/sdlock-pico/`` is C firmware for the Raspberry Pi Pico that sets,
locks, unlocks and clears an SD card's CMD42 password over SPI
(docs/hardware/sd-blocker-pico.md).  Its protocol and driver code is
hardware-independent; ``test/test_sdlock.c`` runs it against a byte-level
simulated SD card and checks, among other things, that no CMD42 frame with the
ERASE bit can leave the driver.

This wrapper compiles that test with the host C compiler and runs it::

    python3 tools/sdlock_pico_check.py            # build + run, print result
    python3 tools/sdlock_pico_check.py --selftest # same, for tools/selftest.py
    python3 tools/sdlock_pico_check.py --cc clang

Exit code 0 = all checks passed.  With no C compiler on PATH the self-test
reports SKIP and exits 0 (the repository has no build system; the check is
optional on machines without a compiler).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "sdlock-pico"
SOURCES = ["src/sd_proto.c", "src/sd_card.c", "test/test_sdlock.c"]
CFLAGS = ["-std=c99", "-O1", "-Wall", "-Wextra", "-Werror"]


def find_cc(preferred: str | None) -> str | None:
    for name in ([preferred] if preferred else ["cc", "gcc", "clang"]):
        if name and shutil.which(name):
            return name
    return None


def run(cc: str | None, verbose: bool) -> int:
    if cc is None:
        print("SKIP: no C compiler (cc/gcc/clang) on PATH")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / "test_sdlock"
        cmd = [cc, *CFLAGS, f"-I{ROOT / 'src'}",
               *[str(ROOT / s) for s in SOURCES], "-o", str(exe)]
        build = subprocess.run(cmd, capture_output=True, text=True)
        if build.returncode != 0:
            print("FAIL: build\n" + build.stdout + build.stderr)
            return 1
        proc = subprocess.run([str(exe)], capture_output=True, text=True,
                              timeout=60)
        out = proc.stdout.strip()
        if verbose or proc.returncode != 0:
            print(out)
        else:
            print(out.splitlines()[-1] if out else "(no output)")
        return 0 if proc.returncode == 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true",
                    help="run the host self-test (same as no arguments)")
    ap.add_argument("--cc", help="C compiler to use (default: cc/gcc/clang)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    return run(find_cc(args.cc), args.verbose)


if __name__ == "__main__":
    sys.exit(main())
