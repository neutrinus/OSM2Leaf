#!/usr/bin/env python3
"""Map the anwdrv.dll (EU2011, build B) iNai message handlers (M1.42).

The driver builds each outgoing iNai message in a function that loads a
``[Msg:pInBuf]`` / ``[Msg:pOutBuf]`` log literal into a register and calls the
``CInaiMsg`` vtable slot 0x310 with ``mov #N,r6`` in the jsr delay slot; ``N``
is the iNai command byte written into the outgoing message. This tool derives
the mapping from the bytes, instead of guessing a command from the doc:

1. collect distinct ``[Name:p*Buf]`` literals in the uncompressed exec section;
2. find every ``mov.l @(disp,PC),Rn`` literal-load whose target word equals a
   literal VA;
3. in the sixteen halfwords before that load, find ``jsr @Rn`` followed by a
   ``mov #N,r6`` delay slot -- the code-derived command byte.

The enclosing handler VA is the nearest preceding ``.pdata`` START. Only
uncompressed code is read (SH-4 code is little-endian, C-2128). Stdlib only;
``--selftest`` uses synthetic code and needs no vendor image.

Usage:
  anw_msgs.py IMAGE
  anw_msgs.py IMAGE --json
  anw_msgs.py --selftest
"""

from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys

import cerom

IMAGE_START = 0x3E00200
MODULE = "anwdrv.dll"
NAME_RE = re.compile(rb"\[([A-Za-z][A-Za-z0-9]{1,6}):p(?:In|Out|Inf)Buf\]")


def _exec_section(rom, module):
    """Return (realaddr, bytes) of the uncompressed executable section."""
    m = rom.module(module)
    for sec in rom.o32(m):
        if sec["flags"] & 0x2000 or not (sec["flags"] & 0x20000000):
            continue
        off = rom.va2file(sec["dataptr"])
        data = rom.d[off:off + sec["vsize"]]
        if len(data) == sec["vsize"] and sec["vsize"]:
            return sec["realaddr"], data
    raise ValueError("no uncompressed executable section in %s" % module)


def pdata_starts(data, image_start=IMAGE_START, module=MODULE):
    """Function-start VAs of a module, from tools/pdata.py (no fitted deltas)."""
    import pdata
    records, _meta = pdata.load_table(data, image_start, module)
    return sorted({int(r[0]) for r in records})


def derive(data, base, starts):
    """Return rows: name, literal VA, command byte, jsr VA, load VA, handler VA."""
    halfwords = struct.unpack("<%dH" % (len(data) // 2),
                              data[:len(data) // 2 * 2])
    names = {}
    for m in NAME_RE.finditer(data):
        names.setdefault(m.group(1).decode(), base + m.start())

    loads = {}
    for i, hw in enumerate(halfwords):
        if (hw & 0xF000) != 0xD000:  # mov.l @(disp,PC),Rn
            continue
        disp = hw & 0x00FF
        pc = base + 2 * i
        target = ((pc + 4) + disp * 4) & ~3
        off = target - base
        if 0 <= off + 4 <= len(data):
            val = struct.unpack_from("<I", data, off)[0]
            loads.setdefault(val, []).append(pc)

    def enclosing(va):
        left = [s for s in starts if s <= va]
        return left[-1] if left else None

    rows = []
    for name, sva in sorted(names.items(), key=lambda kv: kv[1]):
        found = None
        for load_pc in loads.get(sva, []):
            idx = (load_pc - base) // 2
            for j in range(idx - 1, max(-1, idx - 17), -1):
                # jsr @Rn = 0x430n; mov #N,r6 = 0xE6N0 (delay slot)
                if (halfwords[j] & 0xFFF0) == 0x4300 and j + 1 < len(halfwords):
                    nxt = halfwords[j + 1]
                    if (nxt & 0xFF00) == 0xE600 and ((nxt >> 8) & 0xF) == 6:
                        jsr = base + 2 * j
                        found = (name, sva, nxt & 0xFF, jsr, load_pc,
                                 enclosing(jsr))
                        break
            if found:
                break
        rows.append(found or (name, sva, None, None, None, None))
    return rows


def _selftest():
    checks = []

    def eq(name, got, want):
        checks.append((name, got == want, got, want))

    # Synthetic exec section. Pattern copied from the real BeepC handler:
    # [jsr @r3][mov #3,r6][tst][bf][mov.l @(disp,pc),r7][bra]. The mov.l
    # loads a pool word that holds the VA of the log literal. No vendor data.
    lit = b"[SetVo:pInBuf]"
    base = 0x1000
    hva = base
    mov_pc = hva + 8
    pool_va = base + 0x3F0
    lit_va = base + 0x400
    disp = (pool_va - (mov_pc + 4)) // 4
    code = bytearray(struct.pack(
        "<6H", 0x430B, 0xE603, 0x2008, 0x8B02,
        0xD700 | (disp & 0xFF), 0xA02D))
    code += b"\x00" * (pool_va - base - len(code))
    code += struct.pack("<I", lit_va)
    code += b"\x00" * (lit_va - base - len(code))
    code += lit
    rows = derive(bytes(code), base, [hva])
    eq("row count", len(rows), 1)
    eq("name", rows[0][0], "SetVo")
    eq("command byte", rows[0][2], 3)
    eq("handler VA", rows[0][5], hva)
    # Negative control: flip the literal's first byte -> no name match.
    bad = bytes(code)
    bad = bad[:lit_va - base] + b"X" + bad[lit_va - base + 1:]
    bad_rows = derive(bad, base, [hva])
    eq("mutated literal", bad_rows[0][0] if bad_rows else None, None)
    failed = [c for c in checks if not c[1]]
    for name, ok, got, want in checks:
        print("%-18s %s (got %r, want %r)" %
              (name, "PASS" if ok else "FAIL", got, want))
    print("selftest: %d/%d PASS" % (len(checks) - len(failed), len(checks)))
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--image-start", type=lambda x: int(x, 0), default=IMAGE_START)
    ap.add_argument("--module", default=MODULE)
    ap.add_argument("image", nargs="?")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not args.image:
        ap.error("give IMAGE or --selftest")
    with open(args.image, "rb") as fh:
        data = fh.read()
    rom = cerom.CERom(data, args.image_start)
    base, sec = _exec_section(rom, args.module)
    starts = pdata_starts(data, args.image_start, args.module)
    rows = derive(sec, base, starts)
    mapped = [r for r in rows if r[2] is not None]
    out = {
        "image": os.path.basename(args.image),
        "image_start": args.image_start,
        "module": args.module,
        "section_va": base,
        "section_vsize": len(sec),
        "pdata_starts": len(starts),
        "literals": len(rows),
        "mapped": len(mapped),
        "rows": [
            {"name": r[0], "literal_va": r[1], "command": r[2],
             "jsr_va": r[3], "load_va": r[4], "handler_va": r[5]}
            for r in rows
        ],
    }
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print("image=%s module=%s section=%#x/%d pdata=%d literals=%d mapped=%d"
              % (out["image"], out["module"], base, len(sec), len(starts),
                 len(rows), len(mapped)))
        for r in out["rows"]:
            cmd = "UNKNOWN" if r["command"] is None else str(r["command"])
            fn = "UNKNOWN" if r["handler_va"] is None else hex(r["handler_va"])
            print("%-9s cmd=%-7s fn=%s str=%s" %
                  (r["name"], cmd, fn, hex(r["literal_va"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
