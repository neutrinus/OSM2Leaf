#!/usr/bin/env python3
"""Deprecated: use ``tools/cerom.py scan``.

This module is now a thin wrapper around ``tools/cerom.py scan``.  The old
whole-image ``ECEC`` scanner has been folded into ``cerom.py`` so that fixes
land in one place (task H3).  All arguments are forwarded unchanged.
"""

import os
import subprocess
import sys


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    # Accept the legacy flag style and forward to `cerom.py scan`.
    image = None
    offset = 0x200200
    out = None
    rest = list(argv)
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok in ("--image",):
            image = rest[i + 1]
            i += 2
            continue
        if tok.startswith("--image="):
            image = tok.split("=", 1)[1]
            i += 1
            continue
        if tok in ("--offset",):
            offset = int(rest[i + 1], 0)
            i += 2
            continue
        if tok.startswith("--offset="):
            offset = int(tok.split("=", 1)[1], 0)
            i += 1
            continue
        if tok in ("--out",):
            out = rest[i + 1]
            i += 2
            continue
        if tok.startswith("--out="):
            out = tok.split("=", 1)[1]
            i += 1
            continue
        # Positional image (new style) is accepted too.
        if image is None and not tok.startswith("-"):
            image = tok
            i += 1
            continue
        i += 1

    if image is None:
        print("error: --image is required", file=sys.stderr)
        return 2

    print("ce_rom_parse.py is deprecated; use tools/cerom.py scan", file=sys.stderr)
    cerom = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cerom.py")
    cmd = [sys.executable, cerom, "scan", image, "--offset", str(offset)]
    if out is not None:
        cmd += ["--out", out]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
PY
chmod +x /tmp/opencode/h3-worktree/tools/ce_rom_parse.py
python3 /tmp/opencode/h3-worktree/tools/ce_rom_parse.py --image /tmp/opencode/IMG256 2>&1 | head -3