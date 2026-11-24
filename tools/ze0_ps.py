#!/usr/bin/env python3
"""List CE 5 processes, threads and modules of a running ``-M ze0`` guest.

The Windows CE 5 kernel keeps its fixed-layout tables in the kernel data
page.  This tool reads them from *guest physical memory* through QEMU's HMP
monitor (``xp``), so it needs neither gdb nor a stopped guest:

    python3 tools/ze0_ps.py --monitor SOCK              # process table
    python3 tools/ze0_ps.py --monitor SOCK --threads    # + every thread
    python3 tools/ze0_ps.py --monitor SOCK --json
    python3 tools/ze0_ps.py --selftest                  # synthetic image

Layouts are the public CE 5.0 headers, not fitted deltas:

* KData page (``nkarm.h`` / ``nkintr.h``): ``pCurThd +0x94``,
  ``aInfo[32] +0x300`` with ``KINX_PROCARRAY=0``, ``KINX_MODULES=9`` and
  ``KINX_NKSIG=31`` (``NKSG``).  On SH-4 the page is P1 ``0x89e41800``,
  phys ``0x09e41800`` (docs/emulator/debugging.md) and the user alias is
  ``0x5800``.  Pointers are P1 VAs; the cached alias is converted to a
  physical address with the SH-4 ``0x1fffffff`` mask.
* ``struct Process`` (``kernel.h``): ``hProc +0x08``, ``dwVMBase +0x0c``,
  ``pTh +0x10``, ``lpszProcName +0x20``, ``pMainTh +0x34``.  Threads are a
  singly linked list from ``pTh`` via ``Thread.pNextInProc +0x08``.
* ``struct Thread`` (``kernel.h``): ``pProc +0x0c``, ``bSuspendCnt +0x02``,
  ``bWaitState +0x03``, ``dwLastError +0x38``, ``dwStartAddr +0x5c``.
  The thread's *creation* PC (``dwStartAddr``) is mapped to a module by the
  module table; the live PC inside ``ctx +0x60`` is CPU-specific and is not
  guessed here (use ``gdb-ze0.py`` for the live PC).
* ``struct Module`` (``kernel.h``): ``pMod +0x04`` (circular list),
  ``lpszModName +0x08``, ``BasePtr +0x54``, ``e32_vbase +0x7c``,
  ``e32_vsize +0x80``.  A module's slot is ``BasePtr >> 25`` on CE 5.0;
  ``Process.procnum +0x00`` is its slot number.

Off-line replay is possible with ``--dump FILE --dump-base ADDR`` (a raw
physical-memory capture).  Everything printed is derived from the tables;
a failed read is reported as such and never guessed.
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
from dataclasses import dataclass, field
from typing import Optional

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)
from ze0_gdb import Gdb, hmp_xp, parse_xp  # noqa: E402  (shared readers)

KDATA_P1 = 0x89E41800
KDATA_PHYS = 0x09E41800
AINFO = 0x300
KINX_PROCARRAY = 0
KINX_MODULES = 9
KINX_NKSIG = 31
NKSIG = 0x4E4B5347
PROC_ARRAY_LEN = 32                  # MAX_PROCESSES in pkfuncs.h

CURTHREAD = 0x94                     # KDataStruct.pCurThd
P_PROCNUM = 0x00
P_HPROC = 0x08
P_VMBASE = 0x0C
P_PTH = 0x10
P_NAME = 0x20
P_MAINTH = 0x34
T_SUSPEND = 0x02
T_WAITSTATE = 0x03
T_NEXT = 0x08
T_PROC = 0x0C
T_LASTERROR = 0x38
T_STARTADDR = 0x5C
M_NEXT = 0x04
M_NAME = 0x08
M_BASEPTR = 0x54
# CE 5.0 SH-4: openexe_t is 4 bytes shorter than on ARM, so e32 starts at
# +0x70 (ARM headers say +0x74).  Verified on the EU2011 kernel-B guest:
# beepdrv.dll has e32_vbase 0x03b70000 at +0x78 and 0x6000 at +0x7c.
M_VBASE = 0x78
M_VSIZE = 0x7C
# CE 5.0 SH-4 KINX_PROCARRAY points at 32 inline PROCESS structs, not at
# 32 pointers (CE 4.2 ARM).  The stride was read from the live guest:
# NK.EXE at +0x00, filesys.exe at +0xd0, device.exe at +0x1a0, ...
PROC_STRIDE = 0xD0
MAX_THREADS = 4096                   # loop guard, not a CE limit
MAX_MODULES = 2048
MAX_NAME = 128                       # UTF-16 code units

# CE 5.0 on SH-4 keeps the user VA -> physical map in the CPU page tables.
# KDataStruct.aSections is inline at KData +0xa0 and KINX_SECTIONS is
# aInfo[7] (KData +0x31c); both read 0x89e418a0 on the live EU2011 guest.
# SH-4 Big Physical Page 1 KiB/4 KiB/64 KiB/4 MiB sizes are selected by the
# SZ bits of the PTE (bits 9:8 of reg_data = PTE - 1, flycast's WinCE hack).
AINFO_SECTIONS = 7
ASECTIONS = 0xA0
PTE_MASKS = (0x3FF, 0xFFF, 0xFFFF, 0x3FFFFF)
PTE_HEADER = 12                      # bytes from a level-2 entry to its PTEs
MAX_PTE_SPAN = 16                    # PTE words in one level-2 table


def phys(va: int) -> int:
    """SH-4 cached/uncached P1/P2 alias -> physical address."""
    if 0x80000000 <= va <= 0xBFFFFFFF:
        return va & 0x1FFFFFFF
    if 0x00000000 <= va <= 0x1FFFFFFF:
        return va
    raise ValueError("0x%08x is not a P0/P1/P2 address" % va)


class HmpMemory:
    """Physical memory of a live guest, read with HMP ``xp``.

    ``xp`` addresses physical RAM, so P1/P2 pointers work directly.  A P0
    (user-slot) pointer is retried with HMP ``x``, the virtual-memory form,
    which succeeds only when the guest CPU currently maps that slot.
    """

    def __init__(self, sock: str, words: int = 64):
        self.sock = sock
        self.words = words
        self.cache: dict[int, int] = {}

    def read(self, addr: int, size: int) -> bytes:
        if addr < 0x80000000:
            return self._virtual(addr, size)
        addr = phys(addr)
        out = bytearray()
        while len(out) < size:
            chunk = min(self.words, ((size - len(out)) + 3) // 4)
            base = addr + len(out)
            vals = hmp_xp(self.sock, base, chunk)
            if len(vals) != chunk:
                raise OSError("xp at 0x%08x: got %d of %d words" %
                              (base, len(vals), chunk))
            for i, v in enumerate(vals):
                self.cache[base + 4 * i] = v
                out += struct.pack("<I", v)
        return bytes(out[:size])

    def _virtual(self, addr: int, size: int) -> bytes:
        from ze0_screenshot import hmp
        out = hmp(self.sock, "x /%dwx 0x%x" % ((size + 3) // 4, addr),
                  settle=0.1)
        vals = parse_xp(out.decode(errors="replace"))
        if len(vals) < (size + 3) // 4:
            raise OSError("x at 0x%08x: no virtual mapping" % addr)
        return struct.pack("<%dI" % len(vals), *vals)[:size]


class GdbMemory:
    """Guest *virtual* memory through the QEMU gdbstub ``m`` packet."""

    def __init__(self, port: int):
        self.gdb = Gdb(port)

    def read(self, addr: int, size: int) -> bytes:
        return self.gdb.mem(addr, size)


class ImageMemory:
    """Synthetic or captured physical memory, as one flat byte image."""

    def __init__(self, data: bytes | bytearray, base: int = 0):
        self.data = data
        self.base = base

    def read(self, addr: int, size: int) -> bytes:
        off = phys(addr) - self.base
        if off < 0 or off + size > len(self.data):
            raise OSError("0x%08x+%d outside image [0x%x,0x%x)" %
                          (phys(addr), size, self.base, self.base + len(self.data)))
        return bytes(self.data[off:off + size])


class PhysicalHmpMemory:
    """Always read guest *physical* memory via HMP ``xp`` (never virtual)."""

    def __init__(self, sock: str, words: int = 64):
        self.sock = sock
        self.words = words

    def read(self, addr: int, size: int) -> bytes:
        addr = phys(addr)
        out = bytearray()
        while len(out) < size:
            chunk = min(self.words, (size - len(out) + 3) // 4)
            base = addr + len(out)
            vals = hmp_xp(self.sock, base, chunk)
            if len(vals) != chunk:
                raise OSError("xp at 0x%08x: got %d of %d words" %
                              (base, len(vals), chunk))
            for v in vals:
                out += struct.pack("<I", v)
        return bytes(out[:size])


class PtbMemory:
    """Translate a CE 5.0 user-slot VA to guest physical memory.

    The idle guest's ASID does not map user slots, so HMP ``x`` and gdbstub
    ``m`` fail on ``lpszProcName``.  The map is in the CPU page tables,
    reachable through HMP ``xp`` (physical).  A section (level-1) entry is
    selected by ``va[31:25]``, a level-2 entry by ``va[24:16]``, and the PTE
    by ``va[15:10]``.  ``reg_data = PTE - 1``; its SZ bits pick a page size
    mask from :data:`PTE_MASKS`, and the physical page is the high bits of
    reg_data OR'd with ``va & mask``.  The derivation is the SH-4 MMU layout
    in flycast's WinCE hack (validated against live guest bytes), not a
    fitted delta.  Failed reads raise OSError so the caller reports them.
    """

    def __init__(self, reader, ttb: int | None = None, kdata: int = KDATA_P1):
        self.reader = reader
        self.kdata = kdata
        self.ttb = ttb if ttb is not None else self._read_ttb()
        self.cache: dict[int, int] = {}
        self.walks = 0

    def _read_ttb(self) -> int:
        # aInfo[7] (KData +0x31c) is the base of the 64-entry aSections
        # array; that array holds per-slot level-1 page-table pointers.
        # It is not equal to KData +0xa0 on the live guest: that address is
        # the first array element, i.e. slot 0's L1 pointer.
        ainfo = self.reader.read(phys(self.kdata) + AINFO +
                                 4 * AINFO_SECTIONS, 4)
        return struct.unpack("<I", ainfo)[0]

    def _word(self, addr: int) -> int:
        addr = phys(addr)
        if addr in self.cache:
            return self.cache[addr]
        val = struct.unpack("<I", self.reader.read(addr, 4))[0]
        self.cache[addr] = val
        return val

    def translate(self, va: int) -> int:
        """Return the guest physical address for a U0 VA, or raise OSError."""
        if va >= 0x80000000:
            return phys(va)
        ttb = phys(self.ttb)
        l1 = self._word(ttb + ((va >> 25) & 0x7F) * 4)
        if not (l1 & 0x80000000):
            raise OSError("U0 VA 0x%08x: invalid level-1 entry 0x%08x" %
                          (va, l1))
        l2 = self._word((l1 & 0x1FFFFFFF) + ((va >> 16) & 0x1FF) * 4)
        if not (l2 & 0x80000000):
            raise OSError("U0 VA 0x%08x: invalid level-2 entry 0x%08x" %
                          (va, l2))
        pte = self._word((l2 & 0x1FFFFFFF) + PTE_HEADER +
                         ((va >> 10) & 0x3C))
        reg = pte - 1
        sz = (reg >> 8) & 3
        if reg < 0 or pte == 1:
            raise OSError("U0 VA 0x%08x: invalid PTE 0x%08x" % (va, pte))
        mask = PTE_MASKS[sz]
        page = (reg & 0x1FFFFFFF) & ~mask
        if not page:
            raise OSError("U0 VA 0x%08x: empty PTE 0x%08x" % (va, pte))
        self.walks += 1
        return page | (va & mask)

    def read(self, va: int, size: int) -> bytes:
        out = bytearray()
        while len(out) < size:
            addr = va + len(out)
            mask = PTE_MASKS[0]
            pa = self.translate(addr)
            chunk = min(size - len(out), 4)
            # never cross a 1 KiB boundary: each chunk is one PTE
            chunk = min(chunk, 0x400 - (addr & 0x3FF))
            val = struct.unpack("<I", self.reader.read(pa, 4))[0]
            out += struct.pack("<I", val)[:chunk]
        return bytes(out[:size])


class Memory:
    """u32/UTF-16 view of one of the two byte readers above."""

    def __init__(self, reader, vreader=None, ptb=None):
        self.reader = reader
        self.vreader = vreader  # optional gdbstub fallback for user-slot VAs
        self.ptb = ptb          # optional U0 VA -> physical page-table walker
        self.errors: list[str] = []

    def u32(self, va: int) -> int:
        return struct.unpack("<I", self.reader.read(va, 4))[0]

    def utf16(self, va: int, limit: int = MAX_NAME) -> str:
        reader = self.reader
        if va < 0x80000000 and self.ptb is not None:
            reader = self.ptb
        try:
            raw = reader.read(va, 2 * limit)
        except (OSError, ValueError):
            if self.vreader is None:
                raise
            raw = self.vreader.read(va, 2 * limit)
        chars = []
        for (word,) in struct.iter_unpack("<H", raw):
            if word == 0:
                break
            chars.append(chr(word))
        return "".join(chars)

    def safe_u32(self, va: int, what: str) -> int:
        try:
            return self.u32(va)
        except (OSError, ValueError) as exc:
            self.errors.append("%s at 0x%08x: %s" % (what, va, exc))
            return 0

    def safe_utf16(self, va: int, what: str) -> str:
        try:
            return self.utf16(va)
        except (OSError, ValueError) as exc:
            self.errors.append("%s at 0x%08x: %s" % (what, va, exc))
            return "<unreadable>"


@dataclass
class Thread:
    addr: int
    next: int
    proc: int
    suspend: int
    wait: int
    last_error: int
    start_pc: int
    module: str = "?"


@dataclass
class Module:
    addr: int
    name: str
    base_ptr: int
    vbase: int
    vsize: int

    @property
    def slot(self) -> int:
        return (self.base_ptr >> 25) & 0x3F


@dataclass
class Process:
    addr: int
    procnum: int
    handle: int
    vmbase: int
    name: str
    pth: int
    main_th: int
    threads: list[Thread] = field(default_factory=list)


@dataclass
class Snapshot:
    kdata: int
    nksig: int
    procarray: int
    modlist: int
    cur_thread: int
    processes: list[Process]
    modules: list[Module]
    errors: list[str]
    ptb_walks: int = 0


def _valid_name(name: str) -> bool:
    if not name or len(name) > MAX_NAME:
        return False
    return all(0x20 <= ord(c) < 0x7F for c in name)


def walk_modules(mem: Memory, head: int) -> list[Module]:
    modules: list[Module] = []
    seen = set()
    addr = head
    while addr and addr not in seen and len(modules) < MAX_MODULES:
        seen.add(addr)
        try:
            nxt = mem.u32(addr + M_NEXT)
            name = mem.utf16(mem.u32(addr + M_NAME))
            base = mem.u32(addr + M_BASEPTR)
            vbase = mem.u32(addr + M_VBASE)
            vsize = mem.u32(addr + M_VSIZE)
        except (OSError, ValueError) as exc:
            mem.errors.append("module 0x%08x: %s" % (addr, exc))
            break
        modules.append(Module(addr, name if _valid_name(name) else "<invalid>",
                              base, vbase, vsize))
        if nxt == head or nxt == 0:
            break
        addr = nxt
    if len(modules) == MAX_MODULES:
        mem.errors.append("module list hit %d-entry guard" % MAX_MODULES)
    return modules


def module_at(modules: list[Module], pc: int) -> str:
    for m in modules:
        if m.vsize and m.vbase <= pc < m.vbase + m.vsize:
            return m.name
    return "?"


def walk_threads(mem: Memory, proc_ptr: int, head: int,
                 modules: list[Module]) -> list[Thread]:
    threads: list[Thread] = []
    seen = set()
    addr = head
    while addr and addr not in seen and len(threads) < MAX_THREADS:
        seen.add(addr)
        try:
            nxt = mem.u32(addr + T_NEXT)
            owner = mem.u32(addr + T_PROC)
            suspend = mem.reader.read(addr + T_SUSPEND, 1)[0]
            wait = mem.reader.read(addr + T_WAITSTATE, 1)[0]
            err = mem.u32(addr + T_LASTERROR)
            start = mem.u32(addr + T_STARTADDR)
        except (OSError, ValueError) as exc:
            mem.errors.append("thread 0x%08x: %s" % (addr, exc))
            break
        t = Thread(addr, nxt, owner, suspend, wait, err, start,
                   module_at(modules, start))
        threads.append(t)
        if nxt == head or nxt == 0:
            break
        addr = nxt
    return threads


def walk_processes(mem: Memory, kdata: int,
                   stride: int = PROC_STRIDE) -> tuple[list[Process], int, int, int, int]:
    sig = mem.safe_u32(kdata + AINFO + 4 * KINX_NKSIG, "KINX_NKSIG")
    parray = mem.safe_u32(kdata + AINFO + 4 * KINX_PROCARRAY, "KINX_PROCARRAY")
    modlist = mem.safe_u32(kdata + AINFO + 4 * KINX_MODULES, "KINX_MODULES")
    cur = mem.safe_u32(kdata + CURTHREAD, "pCurThd")
    modules = walk_modules(mem, modlist) if modlist else []
    procs: list[Process] = []
    if not parray:
        return procs, sig, parray, modlist, cur
    for i in range(PROC_ARRAY_LEN):
        ptr = parray + stride * i
        try:
            block = mem.reader.read(ptr, min(stride, 0x40))
            if not any(block):
                continue                    # empty slot
            handle = struct.unpack_from("<I", block, P_HPROC)[0]
            vmbase = struct.unpack_from("<I", block, P_VMBASE)[0]
            if not handle or not vmbase:
                continue                    # empty slot
            pth = struct.unpack_from("<I", block, P_PTH)[0]
            name_ptr = struct.unpack_from("<I", block, P_NAME)[0]
            main_th = struct.unpack_from("<I", block, P_MAINTH)[0]
            name = mem.utf16(name_ptr) if name_ptr else "<none>"
        except (OSError, ValueError) as exc:
            mem.errors.append("process slot %d at 0x%08x: %s" % (i, ptr, exc))
            continue
        p = Process(ptr, block[P_PROCNUM], handle, vmbase,
                    name if _valid_name(name) else "<invalid>", pth, main_th)
        p.threads = walk_threads(mem, ptr, pth, modules) if pth else []
        procs.append(p)
    return procs, sig, parray, modlist, cur


def take_snapshot(mem: Memory, kdata: int,
                  stride: int = PROC_STRIDE) -> Snapshot:
    procs, sig, parray, modlist, cur = walk_processes(mem, kdata, stride)
    return Snapshot(kdata, sig, parray, modlist, cur, procs,
                    walk_modules(mem, modlist) if modlist else [], mem.errors)


def format_report(snap: Snapshot, threads: bool = False,
                  modules: bool = True) -> list[str]:
    out = ["KData phys 0x%08x  NKSIG=%s  procarray=0x%08x  modules=0x%08x  curthread=0x%08x  ptb_walks=%d" %
           (phys(snap.kdata),
            "NKSG" if snap.nksig == NKSIG else "0x%08x" % snap.nksig,
            snap.procarray, snap.modlist, snap.cur_thread,
            snap.ptb_walks)]
    out.append("== CE processes (%d) ==" % len(snap.processes))
    out.append("%-18s %4s %-10s %-10s %6s %6s" %
               ("name", "slot", "handle", "vmbase", "threads", "pTh"))
    for p in snap.processes:
        out.append("%-18s %4d 0x%08x 0x%08x %6d 0x%08x" %
                   (p.name, p.procnum, p.handle, p.vmbase, len(p.threads), p.pth))
    if threads:
        out.append("== CE threads (%d) ==" % sum(len(p.threads) for p in snap.processes))
        for p in snap.processes:
            for t in p.threads:
                out.append("  %-18s 0x%08x wait=%d susp=%d err=%d start=0x%08x <%s>" %
                           (p.name, t.addr, t.wait, t.suspend, t.last_error,
                            t.start_pc, t.module))
    if modules:
        out.append("== CE modules (%d) ==" % len(snap.modules))
        for m in snap.modules:
            out.append("  slot %2d  0x%08x-0x%08x  %s" %
                       (m.slot, m.vbase, m.vbase + m.vsize, m.name))
    for err in snap.errors:
        out.append("READ ERROR: %s" % err)
    return out


def to_json(snap: Snapshot) -> dict:
    return {
        "kdata": "0x%08x" % snap.kdata,
        "nksig": "0x%08x" % snap.nksig,
        "procarray": "0x%08x" % snap.procarray,
        "module_list": "0x%08x" % snap.modlist,
        "current_thread": "0x%08x" % snap.cur_thread,
        "ptb_walks": snap.ptb_walks,
        "processes": [
            {
                "name": p.name, "slot": p.procnum,
                "handle": "0x%08x" % p.handle, "vmbase": "0x%08x" % p.vmbase,
                "process": "0x%08x" % p.addr, "pTh": "0x%08x" % p.pth,
                "thread_count": len(p.threads),
                "threads": [
                    {"addr": "0x%08x" % t.addr, "wait": t.wait,
                     "suspend": t.suspend, "last_error": t.last_error,
                     "start_pc": "0x%08x" % t.start_pc, "module": t.module}
                    for t in p.threads
                ],
            } for p in snap.processes
        ],
        "modules": [
            {"name": m.name, "slot": m.slot,
             "vbase": "0x%08x" % m.vbase, "vsize": "0x%08x" % m.vsize,
             "base_ptr": "0x%08x" % m.base_ptr}
            for m in snap.modules
        ],
        "errors": snap.errors,
    }


# --------------------------------------------------------------------------
# Synthetic image for --selftest: a CE-shaped guest in 2 MiB of RAM
# --------------------------------------------------------------------------

SYN_BASE = 0x09E00000
SYN_SIZE = 0x00400000


def make_synthetic() -> bytes:
    img = bytearray(SYN_SIZE)

    def put(va: int, data: bytes) -> None:
        off = phys(va) - SYN_BASE
        img[off:off + len(data)] = data

    def u32(va: int, value: int) -> None:
        put(va, struct.pack("<I", value))

    def name(va: int, text: str) -> None:
        put(va, text.encode("utf-16le") + b"\0\0")

    # KData: aInfo[NKSIG] = NKSG, process array and circular module list.
    kd = KDATA_P1
    u32(kd + AINFO + 4 * KINX_NKSIG, NKSIG)
    parray = 0x8A000000
    modlist = 0x8A001000
    u32(kd + AINFO + 4 * KINX_PROCARRAY, parray)
    u32(kd + AINFO + 4 * KINX_MODULES, modlist)
    u32(kd + CURTHREAD, 0x8A002000)

    names = ["nk.exe", "filesys.exe", "device.exe", "Navi.exe"]
    counts = [3, 2, 1, 4]
    procs = [parray + PROC_STRIDE * i for i in range(4)]
    for i, p in enumerate(procs):
        put(p + P_PROCNUM, bytes([i + 1]))
        u32(p + P_HPROC, 0x00400000 + i)
        u32(p + P_VMBASE, 0x02000000 * (i + 1))
        name_ptr = 0x8A000800 + 0x80 * i
        name(name_ptr, names[i])
        u32(p + P_NAME, name_ptr)
        first = 0x8A002000 + 0x200 * i
        u32(p + P_PTH, first)
        u32(p + P_MAINTH, first)
        for j in range(counts[i]):
            t = first + 0x40 * j
            u32(t + T_NEXT, first + 0x40 * (j + 1) if j + 1 < counts[i] else 0)
            u32(t + T_PROC, p)
            put(t + T_SUSPEND, bytes([0, j]))
            u32(t + T_LASTERROR, 14 if j == 0 else 0)
            u32(t + T_STARTADDR, 0x88000000 + 0x100000 * i + 0x1000 + j)

    # Module list: four modules, two of them DLLs shared by several slots.
    mods = [0x8A001000, 0x8A001100, 0x8A001200, 0x8A001300]
    mod_names = ["nk.exe", "filesys.exe", "device.exe", "Navi.exe"]
    for i, m in enumerate(mods):
        u32(m + M_NEXT, mods[(i + 1) % len(mods)])
        np = 0x8A000A00 + 0x80 * i
        name(np, mod_names[i])
        u32(m + M_NAME, np)
        u32(m + M_BASEPTR, 0x02000000 * (i + 1))
        u32(m + M_VBASE, 0x88000000 + 0x100000 * i)
        u32(m + M_VSIZE, 0x10000)
    return bytes(img)


# --------------------------------------------------------------------------
# Synthetic page table for --selftest: U0 VA -> physical translation
# --------------------------------------------------------------------------

SYN_TTB = 0x09E10000                  # physical page-table root
SYN_U0_VA = 0x0405FEC4                # a user-slot lpszProcName VA
SYN_U0_PHYS = 0x09E30000              # physical page holding the name


def make_synthetic_ptb() -> bytes:
    """A minimal two-level table mapping SYN_U0_VA to SYN_U0_PHYS."""
    img = bytearray(0x80000)

    def u32(va: int, value: int) -> None:
        off = phys(va) - SYN_BASE
        img[off:off + 4] = struct.pack("<I", value)

    # aInfo[7] and KData +0xa0 both hold the *base* of aSections (a P1 VA).
    # The level-1 pointer lives at TTB + slot*4, not at the base itself.
    u32(KDATA_P1 + AINFO + 4 * AINFO_SECTIONS, SYN_TTB | 0x80000000)
    u32(KDATA_P1 + ASECTIONS, SYN_TTB | 0x80000000)
    l1_phys = SYN_TTB + ((SYN_U0_VA >> 25) & 0x7F) * 4
    l2_phys = SYN_TTB + 0x1000
    u32(l1_phys, l2_phys | 0x80000000)
    l2_entry = l2_phys + ((SYN_U0_VA >> 16) & 0x1FF) * 4
    pte_phys = l2_phys + 0x100
    u32(l2_entry, pte_phys | 0x80000000)
    # PTE = reg_data + 1, reg_data = (physical page & ~mask) | sz
    reg = (SYN_U0_PHYS & ~PTE_MASKS[1]) | (1 << 8)
    u32(pte_phys + PTE_HEADER + ((SYN_U0_VA >> 10) & 0x3C), reg + 1)
    name_off = phys(SYN_U0_PHYS) + (SYN_U0_VA & PTE_MASKS[1])
    off = name_off - SYN_BASE
    img[off:off + len("filesys.exe") * 2 + 2] = \
        "filesys.exe".encode("utf-16le") + b"\0\0"
    return bytes(img)


def selftest() -> int:
    checks = 0
    failures = 0

    def check(label: str, got, want) -> None:
        nonlocal checks, failures
        checks += 1
        if got == want:
            print("  ok   %s" % label)
        else:
            failures += 1
            print("  FAIL %s: got %r, want %r" % (label, got, want))

    check("HMP xp sample parses", parse_xp(
        "0000000009e41b10: 0x0000031b 0x000000c4 0x89e42bf8 0x89e418a0\n"),
        [0x31B, 0xC4, 0x89E42BF8, 0x89E418A0])
    check("HMP xp rejects noise", parse_xp("hello (qemu) \n"), [])

    mem = Memory(ImageMemory(make_synthetic(), SYN_BASE))
    snap = take_snapshot(mem, KDATA_P1)
    check("NKSG signature", snap.nksig, NKSIG)
    check("process count", len(snap.processes), 4)
    check("process names", [p.name for p in snap.processes],
          ["nk.exe", "filesys.exe", "device.exe", "Navi.exe"])
    check("process handles", [p.handle for p in snap.processes],
          [0x400000, 0x400001, 0x400002, 0x400003])
    check("process slots", [p.procnum for p in snap.processes], [1, 2, 3, 4])
    check("thread counts", [len(p.threads) for p in snap.processes], [3, 2, 1, 4])
    check("total threads", sum(len(p.threads) for p in snap.processes), 10)
    check("thread owner back-pointer", snap.processes[2].threads[0].proc,
          snap.processes[2].addr)
    check("thread wait state", [t.wait for t in snap.processes[0].threads],
          [0, 1, 2])
    check("module count", len(snap.modules), 4)
    check("module names", [m.name for m in snap.modules],
          ["nk.exe", "filesys.exe", "device.exe", "Navi.exe"])
    check("module slots", [m.slot for m in snap.modules], [1, 2, 3, 4])
    check("thread start PC maps to module", [t.module for t in snap.processes[2].threads],
          ["device.exe"])
    check("no read errors", snap.errors, [])
    check("current thread", snap.cur_thread, 0x8A002000)

    lines = format_report(snap)
    check("report header", lines[0].startswith("KData phys 0x09e41800  NKSIG=NKSG"), True)
    check("report process row", lines[3].strip().split()[:3],
          ["nk.exe", "1", "0x00400000"])
    check("report last process row", lines[6].strip().split()[:3],
          ["Navi.exe", "4", "0x00400003"])

    # Negative controls: empty process array, dangling name, broken thread chain.
    bad = bytearray(make_synthetic())

    def poke(data: bytearray, va: int, value: int) -> None:
        off = phys(va) - SYN_BASE
        data[off:off + 4] = struct.pack("<I", value)

    for i in range(PROC_ARRAY_LEN):
        for off in range(0, 0x40, 4):
            poke(bad, 0x8A000000 + PROC_STRIDE * i + off, 0)
    empty = take_snapshot(Memory(ImageMemory(bad, SYN_BASE)), KDATA_P1)
    check("negative: empty process array", len(empty.processes), 0)
    check("negative: signature still read", empty.nksig, NKSIG)

    bad2 = bytearray(make_synthetic())
    poke(bad2, 0x8A000000 + P_NAME, 0x8BFFFFFF)
    broken = take_snapshot(Memory(ImageMemory(bad2, SYN_BASE)), KDATA_P1)
    check("negative: unreadable name drops the process",
          [p.name for p in broken.processes],
          ["filesys.exe", "device.exe", "Navi.exe"])
    check("negative: name error recorded",
          any("outside image" in e for e in broken.errors), True)

    bad3 = bytearray(make_synthetic())
    poke(bad3, 0x8A002000 + T_NEXT, 0x8A002000)  # self-loop
    looped = take_snapshot(Memory(ImageMemory(bad3, SYN_BASE)), KDATA_P1)
    check("negative: circular thread list stops", len(looped.processes[0].threads), 1)

    # Page-table translation: positive and negative controls.
    ptb_img = make_synthetic_ptb()
    ptb = PtbMemory(ImageMemory(ptb_img, SYN_BASE), None, KDATA_P1)
    check("U0 VA translates to physical", ptb.translate(SYN_U0_VA),
          SYN_U0_PHYS + (SYN_U0_VA & PTE_MASKS[1]))
    check("U0 name decoded from guest memory",
          Memory(ImageMemory(ptb_img, SYN_BASE), ptb=ptb).utf16(SYN_U0_VA),
          "filesys.exe")
    check("translation counted", ptb.walks >= 2, True)

    # Negative mutations: a corrupt level-1 / level-2 / PTE must fail loudly.
    def ptb_poke(data: bytearray, va: int, value: int) -> None:
        off = phys(va) - SYN_BASE
        data[off:off + 4] = struct.pack("<I", value)

    l1_word = SYN_TTB + ((SYN_U0_VA >> 25) & 0x7F) * 4
    l2_word = SYN_TTB + 0x1000 + ((SYN_U0_VA >> 16) & 0x1FF) * 4
    pte_word = SYN_TTB + 0x1100 + PTE_HEADER + ((SYN_U0_VA >> 10) & 0x3C)
    for label, where in (("level-1", l1_word), ("level-2", l2_word),
                         ("PTE", pte_word)):
        mut = bytearray(ptb_img)
        ptb_poke(mut, where, 0)
        bad_ptb = PtbMemory(ImageMemory(mut, SYN_BASE),
                            SYN_TTB | 0x80000000, KDATA_P1)
        try:
            bad_ptb.translate(SYN_U0_VA)
            got = "NO ERROR"
        except OSError as exc:
            got = "OSError"
        check("negative: zero %s entry fails" % label, got, "OSError")
    mut = bytearray(ptb_img)
    ptb_poke(mut, KDATA_P1 + AINFO + 4 * AINFO_SECTIONS, 0xDEADBEEF)
    bad_base = PtbMemory(ImageMemory(mut, SYN_BASE), None, KDATA_P1)
    try:
        bad_base.translate(SYN_U0_VA)
        got = "NO ERROR"
    except (OSError, ValueError):
        got = "OSError"
    check("negative: corrupt section base fails", got, "OSError")

    print("checks: %d, failures: %d" % (checks, failures))
    print("ze0_ps selftest: %s" % ("OK" if failures == 0 else "FAILED"))
    return 0 if failures == 0 else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true",
                    help="run synthetic CE-table checks (no guest needed)")
    ap.add_argument("--monitor", metavar="SOCK",
                    help="QEMU HMP UNIX socket of a running -M ze0 guest")
    ap.add_argument("--gdb", type=int, metavar="PORT",
                    help="gdbstub TCP port for virtual-name reads (optional)")
    ap.add_argument("--proc-stride", type=lambda s: int(s, 0), default=PROC_STRIDE,
                    help="PROC_ARRAY entry stride (default 0x%x)" % PROC_STRIDE)
    ap.add_argument("--dump", metavar="FILE",
                    help="replay a raw physical-memory capture instead of a guest")
    ap.add_argument("--dump-base", type=lambda s: int(s, 0), default=SYN_BASE,
                    help="physical address of byte 0 of --dump (default 0x%x)" % SYN_BASE)
    ap.add_argument("--kdata", type=lambda s: int(s, 0), default=KDATA_P1,
                    help="KData P1 address (default 0x%08x)" % KDATA_P1)
    ap.add_argument("--ttb", type=lambda s: int(s, 0), default=None,
                    help="page-table root (default: KData aInfo[7])")
    ap.add_argument("--no-ptb", action="store_true",
                    help="disable the U0 VA page-table walk (baseline H68)")
    ap.add_argument("--threads", action="store_true", help="print every thread")
    ap.add_argument("--no-modules", action="store_true", help="omit the module table")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.monitor and not args.dump:
        ap.error("--monitor SOCK or --dump FILE is required (or --selftest)")
    if args.monitor and args.dump:
        ap.error("choose --monitor or --dump, not both")
    try:
        vmem = GdbMemory(args.gdb) if args.gdb else None
        ptb = None
        if args.dump:
            with open(args.dump, "rb") as handle:
                reader = ImageMemory(handle.read(), args.dump_base)
                if not args.no_ptb:
                    ptb = PtbMemory(reader, args.ttb, args.kdata)
                mem = Memory(reader, vmem, ptb)
        else:
            reader = HmpMemory(args.monitor)
            if not args.no_ptb:
                ptb = PtbMemory(PhysicalHmpMemory(args.monitor),
                                args.ttb, args.kdata)
            mem = Memory(reader, vmem, ptb)
        snap = take_snapshot(mem, args.kdata, args.proc_stride)
        if ptb is not None:
            snap.ptb_walks = ptb.walks
    except (OSError, ValueError) as exc:
        print("ze0_ps: %s" % exc, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(to_json(snap), indent=2))
    else:
        for line in format_report(snap, args.threads, not args.no_modules):
            print(line)
    return 0 if snap.processes else 1


if __name__ == "__main__":
    raise SystemExit(main())
