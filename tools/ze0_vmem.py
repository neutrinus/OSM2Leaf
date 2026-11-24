#!/usr/bin/env python3
"""Read a WinCE process's user memory from a QEMU ze0 physical RAM dump.

The QEMU sh4 gdbstub and HMP ``gva2gpa`` translate only through the UTLB.
WinCE refills the TLB in software, so most user pages of a stopped process
read as ``E14`` / ``Unmapped`` even though they are in RAM.  This tool walks
the kernel's own page tables instead:

* KData (P1 ``0x89e41800``) ``aInfo[KINX_SECTIONS]`` (``+0x31c``) points at
  ``SectionTable[64]``; section ``va >> 25``; section 0 is the current
  process (on NK1 Navi.exe is slot 15).
* A section holds 512 ``MEMBLOCK *`` (64 KiB each, index ``(va >> 16) &
  0x1ff``); ``MEMBLOCK.aPages[16]`` at ``+0x0c`` hold ``PA | flags``.

Dump RAM at a breakpoint with HMP (both banks of the NK1 unit)::

    pmemsave 0x08000000 0x8000000 "OUT.08000000.bin"
    pmemsave 0x10000000 0x8000000 "OUT.10000000.bin"

then ``python3 tools/ze0_vmem.py OUT 0x6236a8 0x40``.  Checked against gdb
reads of resident pages (NK1, 2026-11-24, M5.103).

Dumps hold vendor map data and the unit's memory: never commit them.
"""
from __future__ import annotations

import argparse
import glob
import struct

KDATA_PHYS = 0x09E41800
KINX_SECTIONS_OFF = 0x300 + 7 * 4


class Phys:
    def __init__(self, prefix: str):
        self.parts = []
        for f in sorted(glob.glob(prefix + ".*.bin")):
            try:
                base = int(f.rsplit(".", 2)[-2], 16)
            except ValueError:
                continue
            self.parts.append((base, open(f, "rb").read()))
        if not self.parts:
            raise SystemExit("no dump files %s.<hexbase>.bin" % prefix)

    def read(self, pa: int, n: int) -> bytes:
        pa &= 0x1FFFFFFF
        for b, d in self.parts:
            if b <= pa and pa + n <= b + len(d):
                return d[pa - b:pa - b + n]
        raise KeyError("phys 0x%x not in dump" % pa)

    def u32(self, pa: int) -> int:
        return struct.unpack("<I", self.read(pa, 4))[0]


class VM:
    def __init__(self, prefix: str):
        self.p = Phys(prefix)
        self.sect = self.p.u32(KDATA_PHYS + KINX_SECTIONS_OFF)

    def pa(self, va: int) -> int:
        if 0x80000000 <= va < 0xC0000000:
            return va & 0x1FFFFFFF
        sec = self.p.u32(self.sect + 4 * (va >> 25))
        if sec < 0x80000000:
            raise KeyError("no section for 0x%x (0x%x)" % (va, sec))
        mb = self.p.u32(sec + 4 * ((va >> 16) & 0x1FF))
        if mb < 0x80000000:
            raise KeyError("no block for 0x%x (0x%x)" % (va, mb))
        pg = self.p.u32(mb + 0x0C + 4 * ((va >> 12) & 0xF))
        if pg & 0x1FFFF000 == 0 or pg == 0xFFFFFFF0:
            raise KeyError("no page for 0x%x (0x%x)" % (va, pg))
        return (pg & 0x1FFFF000) | (va & 0xFFF)

    def read(self, va: int, n: int) -> bytes:
        out = b""
        while n:
            k = min(n, 0x1000 - (va & 0xFFF))
            out += self.p.read(self.pa(va), k)
            va += k
            n -= k
        return out

    def u16(self, va: int) -> int:
        return struct.unpack("<H", self.read(va, 2))[0]

    def u32(self, va: int) -> int:
        return struct.unpack("<I", self.read(va, 4))[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("prefix", help="dump prefix (files PREFIX.<hexbase>.bin)")
    ap.add_argument("va", type=lambda s: int(s, 16))
    ap.add_argument("length", type=lambda s: int(s, 0), nargs="?", default=0x40)
    a = ap.parse_args()
    vm = VM(a.prefix)
    print("section table 0x%08x  va 0x%08x -> pa 0x%08x" % (vm.sect, a.va, vm.pa(a.va)))
    data = vm.read(a.va, a.length)
    for i in range(0, len(data), 16):
        print("%08x  %s" % (a.va + i, data[i:i + 16].hex(" ")))


if __name__ == "__main__":
    main()
