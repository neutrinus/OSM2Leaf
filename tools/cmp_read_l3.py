#!/usr/bin/env python3
"""Run Navi.exe's compressed file layer (mount, open, seek, read) on a real pair (M3.2).

EU2011 ``Navi.exe`` build A only.  M3.2b named the chain statically
(EXP-2026-11-19-M3.2b-cmp-chunk-reader-walk-up); this tool executes it in
PySh4 with the file-system ``ops`` table bound to host files:

* ``fn 0x0041bc98(arena, arena_end, cfg, ops)`` + stack ``CMP.LST`` path —
  the manager constructor the mount ``0x0041ba90`` calls through
  ``0x0041bd88``; it builds the ctx (``0x0041c190``), reads ``CMP.LST``
  (``0x0041c124``) and sets up the ``.IND`` cache (``0x0041cb1c``).  The
  ``cfg`` words are the mount's own constants (``fn 0x0041ba90`` +0x5e..+0x7a):
  50 handles, 20 entries, ``0x20000``, ``0x10000``, ``0x14000``; arena size
  ``0x82c60`` (its pool, ``fn 0x0041ba90`` +0x150).  The result is stored at ``*0x009cfd18``
  as the mount does.
* ``fn 0x0041b780(path, 1)`` — open; ``0x0041be30`` asks ``0x0041c2e0``
  (``CMP.LST`` match) and opens ``path.IND``/``path.CMP`` (``0x0041c524``).
* ``fn 0x0041b8a4(h, off, 0, 1)`` — seek (``0x0041bfb4`` -> ``0x0041cab0``).
* ``fn 0x0041b954(h, buf, len, 1)`` — read (``0x0041c044`` -> ``0x0041c990``
  -> ``0x0041c8c4``/``0x0041c5f0``/``0x0041c7dc`` -> inflate ``0x00542148``).

Host stubs (each an import thunk, named from ``cerom.py imports`` at run
time, or a firmware function pointer the mount passes): the seven ``ops``
(open, seek, read, write, close, size, tell -> a host file table, every call
logged); ``strlen``, ``strcpy``, ``strcat``, ``memcpy``, ``memset``,
``_divls``, ``_divlu``, ``_modls``, ``_modlu``; ``EnterCriticalSection`` /
``LeaveCriticalSection`` (no-ops: one thread); zlib ``zcalloc``/``zcfree``
trampolines (``build_targets.py``); and the error reporter ``0x0041bbec``
(``NKDbgPrintfW``/``ErrorLogMsg`` only, logged).  ``Navi.exe`` sec1/sec2 are
mapped as the kernel's own decompressor decodes them (``nk_decomp``, stored
bytes + zero BSS), so ``inflate_mask`` is read from the image, not written.

The reference is ``cmpind.decode`` (stock zlib).  Verdicts: ``ACCEPT`` (the
read returns ``len`` and the bytes equal the reference slice), ``REJECT``
(open fails, seek fails or the read returns -1), ``WRONG`` (returns data that
differ), ``BLOCKED`` (engine stop on an unmapped access; never a pass).

Usage::

  cmp_read_l3.py --selftest
  cmp_read_l3.py run IMG --card DIR --name REFER001/ADDRE001.DAT \
      [--ind PATH] [--offset N] [--length N] [--shift K] [--json]
  cmp_read_l3.py batch IMG --card DIR --name REFER001/ADDRE001.DAT --mutants DIR

``--ind`` replaces the pair's ``.ind`` (a mutant); ``--shift K`` prepends a
K-byte decoy (a valid zlib stream of other data, ``78 9c`` first) to the
``.cmp`` and adds K to word 1 and every ``chunk_offset`` (a seeking reader
returns the right bytes from offset ``chunk_offset[0] + K``; a reader that
scans for ``78 9c`` from 0 inflates the decoy).

Exit codes: 0 the verdict matches ``--expect`` (or no ``--expect``), 1 it
does not, 3 input missing, 4 BLOCKED.
Method and results: docs/experiments/EXP-2026-11-20-M3.2-ind-handling-l3.md
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
import zlib
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "l3_harness"))

import build_targets  # noqa: E402
import cerom  # noqa: E402
import cmpind_codec  # noqa: E402
from engine import RETURN_VA, EngineError, PySh4, StubReturn  # noqa: E402

IMAGE_START = 0x200200
MODULE = "Navi.exe"
BUILD = "eu2011"
M32 = 0xFFFFFFFF

# EU2011 Navi.exe build A (M3.2b, C-5100..C-5105); every VA is a .pdata START.
FN_MGR_NEW = 0x0041BC98     # manager ctor (under 0x0041bd88, mount 0x0041ba90)
FN_OPEN = 0x0041B780        # open(path, flag)
FN_SEEK = 0x0041B8A4        # seek(h, off, whence, flag)
FN_READ = 0x0041B954        # read(h, buf, len, flag)
FN_ERRLOG = 0x0041BBEC      # error reporter (NKDbgPrintfW / ErrorLogMsg)
G_MGR = 0x009CFD18          # *0x009cfd18 = manager (BSS, Navi.exe sec1)
MOUNT_CFG = (50, 20, 0x20000, 0x10000, 0x14000)   # fn 0x0041ba90 +0x5e..+0x7a
ARENA_SIZE = 0x82C60                              # fn 0x0041ba90 pool +0x150
SLOT_COMPRESSED = 0x116     # u16 per handle slot, 1 = served through .ind/.cmp

# compare sites observed during a run (EU2011): VA -> (label, left reg, right reg)
PROBES = {
    0x0041C8C4 + 0x66: ("chunk_size==cfg (fn 0x0041c8c4 +0x66)", "r8", "r3"),
    0x0041C5F0 + 0xA6: ("chunk_size==cfg (fn 0x0041c5f0 +0xa6)", "r8", "r1"),
    0x0041C990 + 0xAC: ("read len==batch (fn 0x0041c990 +0xac)", "r0", "r12"),
}

IMPORTS = ("strlen", "strcpy", "strcat", "memcpy", "memset", "_divls",
           "_divlu", "_modls", "_modlu", "EnterCriticalSection",
           "LeaveCriticalSection")
OPS = ("open", "seek", "read", "write", "close", "size", "tell")

STK_VA, STK_SIZE = 0x30000000, 0x20000
ARENA_VA = 0x40000000
DATA_VA = 0x41000000        # cfg, ops table, path strings
OPS_VA = 0x42000000         # one 16-byte stub slot per op
OUT_VA = 0x50000000
HEAP_VA, HEAP_SIZE = 0x70000000, 0x800000
MAX_INSNS = 200_000_000


class Blocked(Exception):
    pass


# ---------------------------------------------------------------------------
# host side: files, decoy, verdicts


def shifted_pair(cmp_bytes: bytes, ind_bytes: bytes, k: int) -> tuple[bytes, bytes]:
    """Prepend a *k*-byte decoy to the .cmp and move the index by *k*."""
    decoy = zlib.compress(b"DECOY " * 4096, 6)
    if k < len(decoy):
        raise ValueError(f"--shift must be >= {len(decoy)} (the decoy stream)")
    pad = decoy + b"\0" * (k - len(decoy))
    usize, csize, count, cs = struct.unpack_from("<4I", ind_bytes)
    offs = struct.unpack_from(f"<{count}I", ind_bytes, 16)
    ind = struct.pack("<4I", usize, csize + k, count, cs)
    ind += struct.pack(f"<{count}I", *(o + k for o in offs))
    return pad + cmp_bytes, ind


def python_verdict(cmp_bytes: bytes, ind_bytes: bytes, offset: int, length: int):
    """cmpind_codec's verdict on the pair: (verdict, slice or reason)."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="cmpread-") as tmp:
        c, i = Path(tmp) / "x.cmp", Path(tmp) / "x.ind"
        c.write_bytes(cmp_bytes)
        i.write_bytes(ind_bytes)
        try:
            blob, _ = cmpind_codec.decode(c, i)
        except (cmpind_codec.FormatError, zlib.error, ValueError, struct.error) as exc:
            return "REJECT", str(exc)
    return "ACCEPT", blob[offset:offset + length]


class GuestFS:
    """Host files behind the firmware's ops table; paths compare upper-case."""

    def __init__(self, files: dict[str, bytes]):
        self.files = {k.upper(): v for k, v in files.items()}
        self.handles: dict[int, list] = {}
        self.log: list[tuple] = []
        self.opened = 0

    def open(self, path: str, mode: str) -> int:
        data = self.files.get(path.upper())
        if data is None:
            self.log.append(("open", path, mode, 0))
            return 0
        self.opened += 1
        h = 0x1000 + 0x10 * self.opened
        self.handles[h] = [path, 0, data]
        self.log.append(("open", path, mode, h))
        return h

    def seek(self, h: int, off: int, whence: int) -> int:
        f = self.handles.get(h)
        if f is None:
            return M32
        base = (0, f[1], len(f[2]))[whence] if whence in (0, 1, 2) else None
        pos = None if base is None else base + struct.unpack("<i", struct.pack("<I", off & M32))[0]
        ok = pos is not None and 0 <= pos <= len(f[2])
        if ok:
            f[1] = pos
        self.log.append(("seek", f[0], off, whence, 0 if ok else -1))
        return 0 if ok else M32

    def read(self, h: int, n: int) -> bytes:
        f = self.handles[h]
        got = f[2][f[1]:f[1] + n]
        f[1] += len(got)
        self.log.append(("read", f[0], f[1] - len(got), n, len(got)))
        return got

    def close(self, h: int) -> int:
        f = self.handles.pop(h, None)
        self.log.append(("close", f[0] if f else None))
        return 0

    def size(self, h: int) -> int:
        return len(self.handles[h][2])

    def tell(self, h: int) -> int:
        return self.handles[h][1]


# ---------------------------------------------------------------------------
# guest side


def import_thunks(image_path: str, text_va: int, text: bytes) -> dict[str, int]:
    """Map import names to the sec0 thunks that jump through their IAT slot.

    A thunk is ``mov.l @(disp,pc),r0; mov.l @r0,r0; jmp @r0``; its pool word
    is the slot, and ``cerom.py imports`` names the slot.
    """
    out = subprocess.run([sys.executable, os.path.join(HERE, "cerom.py"),
                          "--image-start", hex(IMAGE_START), image_path,
                          "imports", MODULE, "--resolve-with", "0x3e00200"],
                         capture_output=True, text=True).stdout
    slots = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1].startswith("slot="):
            slots[int(parts[1][5:], 16)] = parts[2].split("!")[-1]
    return find_thunks(text_va, text, slots)


def find_thunks(text_va: int, text: bytes, slots: dict[int, str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for off in range(0, len(text) - 8, 2):
        w0, w1, w2 = struct.unpack_from("<3H", text, off)
        if (w0 & 0xFF00) == 0xD000 and w1 == 0x6002 and w2 == 0x402B:
            va = text_va + off
            pool = ((va & ~3) + 4 + (w0 & 0xFF) * 4) - text_va
            if 0 <= pool <= len(text) - 4:
                slot = struct.unpack_from("<I", text, pool)[0]
                name = slots.get(slot)
                if name and name not in found:
                    found[name] = va
    return found


def cstr(eng, va: int, limit: int = 512) -> str:
    raw = eng.read_mem(va, limit)
    return raw.split(b"\0", 1)[0].decode("latin-1")


def signed(v: int) -> int:
    return struct.unpack("<i", struct.pack("<I", v & M32))[0]


class Layer:
    """One mounted file layer in one engine."""

    def __init__(self, image_path: str, fs: GuestFS, cmplst_path: str = "\\SystemSD\\CMP.LST",
                 cfg=MOUNT_CFG):
        self.cfg = tuple(cfg)
        import nk_decomp
        import point_walk_l3 as pw
        self.fs = fs
        self.stats = {"insns": 0, "errlog": [], "zalloc": [], "imports": {}, "probes": []}
        data = pw.load_image(image_path)
        rom, secs = pw.module_sections(data, IMAGE_START, MODULE)
        text_va, text = pw.navi_text(data, IMAGE_START)
        eng = self.eng = PySh4(endian="little")
        eng.map("text", text_va, bytearray(text) + bytearray(-len(text) % 0x1000), "rx")
        for sec, comp, _ in secs:
            if not comp:
                continue
            r0, blob = nk_decomp.decompress(data, rom.va2file(sec["dataptr"]),
                                            sec["psize"], sec["vsize"])
            if r0 == M32:
                raise Blocked("nk_decomp failed on section %#x" % sec["realaddr"])
            buf = bytearray(blob[:r0]) + bytearray(sec["vsize"] - r0)
            buf += bytearray(-len(buf) % 0x1000)
            eng.map("sec@%08x" % sec["realaddr"], sec["realaddr"], buf, "rw")
        eng.map("stack", STK_VA, bytearray(STK_SIZE), "rw")
        eng.map("arena", ARENA_VA, bytearray(ARENA_SIZE + 0x1000), "rw")
        eng.map("data", DATA_VA, bytearray(0x4000), "rw")
        eng.map("ops", OPS_VA, bytearray(0x1000), "rx")
        eng.map("heap", HEAP_VA, bytearray(HEAP_SIZE), "rw")
        self.heap = HEAP_VA
        self._hook_imports(import_thunks(image_path, text_va, text))
        self._hook_ops()
        tgt = build_targets.tool_map("chunk_decoder_l3")[BUILD]
        eng.on_exec(tgt["zcalloc"], self._zcalloc)
        eng.on_exec(tgt["zcfree"], lambda e, va: StubReturn(0))
        eng.on_exec(FN_ERRLOG, self._errlog)
        for va, (label, a, b) in PROBES.items():
            eng.on_exec(va, self._probe(label, a, b))
        counted = eng._execute

        def count(insn, pc):
            self.stats["insns"] += 1
            return counted(insn, pc)

        eng._execute = count
        self.mgr = self._mount(cmplst_path)

    # -- stubs ------------------------------------------------------------
    def _hook_imports(self, thunks: dict[str, int]) -> None:
        missing = [n for n in IMPORTS if n not in thunks]
        if missing:
            raise Blocked("no thunk found for " + ", ".join(missing))
        e = self.eng
        reg = e._get_reg

        def tally(name):
            self.stats["imports"][name] = self.stats["imports"].get(name, 0) + 1

        def mk(name, fn):
            def hook(eng, va):
                tally(name)
                return StubReturn(fn(eng) & M32)
            e.on_exec(thunks[name], hook)

        def strlen(eng):
            return len(cstr(eng, reg("r4"), 4096))

        def strcpy(eng):
            d, s = reg("r4"), cstr(eng, reg("r5"), 4096).encode("latin-1") + b"\0"
            eng.write_mem(d, s)
            return d

        def strcat(eng):
            d = reg("r4")
            n = len(cstr(eng, d, 4096))
            eng.write_mem(d + n, cstr(eng, reg("r5"), 4096).encode("latin-1") + b"\0")
            return d

        def memcpy(eng):
            d, s, n = reg("r4"), reg("r5"), reg("r6")
            if n:
                eng.write_mem(d, eng.read_mem(s, n))
            return d

        def memset(eng):
            d, c, n = reg("r4"), reg("r5"), reg("r6")
            if n:
                eng.write_mem(d, bytes([c & 0xFF]) * n)
            return d

        def div(signed_op, mod):
            def f(eng):
                a, b = reg("r4"), reg("r5")
                if signed_op:
                    a, b = signed(a), signed(b)
                if b == 0:
                    raise Blocked("division by zero in a COREDLL helper")
                q = abs(a) // abs(b) * (1 if (a < 0) == (b < 0) else -1)
                return a - q * b if mod else q
            return f

        mk("strlen", strlen)
        mk("strcpy", strcpy)
        mk("strcat", strcat)
        mk("memcpy", memcpy)
        mk("memset", memset)
        mk("_divls", div(True, False))
        mk("_divlu", div(False, False))
        mk("_modls", div(True, True))
        mk("_modlu", div(False, True))
        mk("EnterCriticalSection", lambda eng: 0)
        mk("LeaveCriticalSection", lambda eng: 0)

    def _hook_ops(self) -> None:
        e, fs, reg = self.eng, self.fs, self.eng._get_reg

        def op(i):
            name = OPS[i]

            def hook(eng, va):
                if name == "open":
                    return StubReturn(fs.open(cstr(eng, reg("r4")), cstr(eng, reg("r5"))))
                if name == "seek":
                    return StubReturn(fs.seek(reg("r4"), reg("r5"), reg("r6")))
                if name == "read":
                    got = fs.read(reg("r4"), reg("r6"))
                    if got:
                        eng.write_mem(reg("r5"), got)
                    return StubReturn(len(got))
                if name == "close":
                    return StubReturn(fs.close(reg("r4")))
                if name == "size":
                    return StubReturn(fs.size(reg("r4")))
                if name == "tell":
                    return StubReturn(fs.tell(reg("r4")))
                raise Blocked("ops.write called on a read-only layer")
            return hook

        for i in range(len(OPS)):
            e.on_exec(OPS_VA + 16 * i, op(i))

    def _zcalloc(self, eng, va):
        items, size = eng._get_reg("r5"), eng._get_reg("r6")
        p = self.heap
        self.heap += (items * size + 15) & ~15
        if self.heap > HEAP_VA + HEAP_SIZE:
            self.heap = HEAP_VA          # zcfree is a no-op; recycle between reads
            p = self.heap
            self.heap += (items * size + 15) & ~15
        self.stats["zalloc"].append(items * size)
        return StubReturn(p)

    def _probe(self, label, a, b):
        def hook(eng, va):
            x, y = eng._get_reg(a), eng._get_reg(b)
            self.stats["probes"].append((label, x, y, x == y))
            return None              # observe only; the instruction runs
        return hook

    def _errlog(self, eng, va):
        r = eng.get_regs()
        self.stats["errlog"].append((r["r4"], r["r5"], r["r6"], r["r7"],
                                     struct.unpack("<I", eng.read_mem(r["r15"] + 16, 4))[0]))
        return StubReturn(0)

    # -- calls ------------------------------------------------------------
    def call(self, va: int, args, stack_args=()):
        top = STK_VA + STK_SIZE // 2
        for i, v in enumerate(stack_args):
            self.eng.write_mem(top + 16 + 4 * i, struct.pack("<I", v & M32))
        self.eng.set_regs(r15=top)
        try:
            e = self.eng
            e.set_regs(pc=va, pr=RETURN_VA)
            for i, v in enumerate(args):
                e._set_reg("r%d" % (4 + i), int(v) & M32)
            e.run_until(max_insns=MAX_INSNS)
            return e._get_reg("r0") & M32
        except EngineError as exc:
            raise Blocked(f"{exc} (last pc {self.eng._get_reg('pc'):#010x})") from exc

    def _mount(self, cmplst_path: str) -> int:
        path_va, cfg_va, ops_va = DATA_VA, DATA_VA + 0x200, DATA_VA + 0x240
        self.eng.write_mem(path_va, cmplst_path.encode("latin-1") + b"\0")
        self.eng.write_mem(cfg_va, struct.pack("<5I", *self.cfg))
        self.eng.write_mem(ops_va, struct.pack("<7I", *(OPS_VA + 16 * i for i in range(7))))
        mgr = self.call(FN_MGR_NEW, [ARENA_VA, ARENA_VA + ARENA_SIZE, cfg_va, ops_va],
                        stack_args=[path_va])
        if mgr:
            self.eng.write_mem(G_MGR, struct.pack("<I", mgr))
        return mgr

    def open(self, guest_path: str) -> tuple[int, int | None]:
        pv = DATA_VA + 0x400
        self.eng.write_mem(pv, guest_path.encode("latin-1") + b"\0")
        h = self.call(FN_OPEN, [pv, 1])
        if not h:
            return 0, None
        flag = struct.unpack("<H", self.eng.read_mem(h + SLOT_COMPRESSED, 2))[0]
        return h, flag

    def seek(self, h: int, off: int) -> int:
        return signed(self.call(FN_SEEK, [h, off, 0, 1]))

    def read(self, h: int, length: int) -> tuple[int, bytes]:
        self.eng.map("out", OUT_VA, bytearray((length + 0x10FFF) & ~0xFFF), "rw")
        r = signed(self.call(FN_READ, [h, OUT_VA, length, 1]))
        return r, (bytes(self.eng.read_mem(OUT_VA, r)) if r > 0 else b"")


# ---------------------------------------------------------------------------
# one case


def run_case(image: str, card: Path, name: str, ind_override: Path | None,
             offset: int, length: int | None, shift: int, cfg_chunk: int = 0x10000) -> dict:
    cmp_bytes = (card / (name + ".cmp")).read_bytes()
    ind_bytes = (ind_override or card / (name + ".ind")).read_bytes()
    if shift:
        cmp_bytes, ind_bytes = shifted_pair(cmp_bytes, ind_bytes, shift)
    usize = struct.unpack_from("<I", ind_bytes)[0]
    true_usize = struct.unpack_from("<I", (card / (name + ".ind")).read_bytes())[0]
    if length is None:
        length = max(true_usize - offset, 0)
    guest = "\\SystemSD\\" + name.replace("/", "\\")
    fs = GuestFS({
        "\\SystemSD\\CMP.LST": (card / "CMP.LST").read_bytes(),
        guest + ".IND": ind_bytes,
        guest + ".CMP": cmp_bytes,
    })
    pv, ref = python_verdict(cmp_bytes, ind_bytes, offset, length)
    # the reference for the firmware's bytes is the unmutated pair
    _, good = python_verdict((card / (name + ".cmp")).read_bytes(),
                             (card / (name + ".ind")).read_bytes(), offset, length)
    res = {"name": name, "ind": str(ind_override) if ind_override else "factory",
           "cfg_chunk": cfg_chunk,
           "shift": shift, "offset": offset, "length": length, "usize_field": usize,
           "python": pv, "python_reason": ref if pv == "REJECT" else None}
    try:
        cfg = list(MOUNT_CFG)
        cfg[3] = cfg_chunk
        layer = Layer(image, fs, cfg=cfg)
        res["mgr"] = layer.mgr
        if not layer.mgr:
            res["verdict"] = "REJECT"
            res["stage"] = "mount"
            return finish(res, fs, layer)
        h, flag = layer.open(guest)
        res["handle"], res["compressed"] = h, flag
        if not h:
            res.update(verdict="REJECT", stage="open")
            return finish(res, fs, layer)
        if offset:
            s = layer.seek(h, offset)
            if s < 0:
                res.update(verdict="REJECT", stage="seek")
                return finish(res, fs, layer)
        r, out = layer.read(h, length)
        res["r0"] = r
        if r < 0:
            res.update(verdict="REJECT", stage="read")
        elif r == length and out == good:
            res["verdict"] = "ACCEPT"
        else:
            first = next((i for i, (a, b) in enumerate(zip(out, good)) if a != b),
                         min(len(out), len(good)))
            res.update(verdict="WRONG", first_diff=first)
        return finish(res, fs, layer)
    except Blocked as exc:
        res.update(verdict="BLOCKED", reason=str(exc))
        return res


def finish(res: dict, fs: GuestFS, layer: Layer) -> dict:
    res["ops"] = [list(x) for x in fs.log]
    res["insns"] = layer.stats["insns"]
    res["errlog"] = layer.stats["errlog"]
    res["zalloc_sizes"] = sorted(set(layer.stats["zalloc"]))
    res["imports"] = layer.stats["imports"]
    res["probes"] = layer.stats["probes"]
    return res


def show(res: dict) -> None:
    print(f"case {res['name']} ind={res['ind']} shift={res['shift']} cfg_chunk={res['cfg_chunk']:#x} "
          f"offset={res['offset']:#x} length={res['length']}")
    for op in res.get("ops", []):
        if op[0] == "read":
            print(f"  ops.read  {op[1]} at {op[2]:#x} n={op[3]:#x} got={op[4]:#x}")
        elif op[0] == "seek":
            print(f"  ops.seek  {op[1]} off={op[2]:#x} whence={op[3]} -> {op[4]}")
        elif op[0] == "open":
            print(f"  ops.open  {op[1]} {op[2]!r} -> {op[3]:#x}")
        else:
            print(f"  ops.{op[0]} {op[1]}")
    if res.get("errlog"):
        print("  errlog " + "; ".join("(%d,%d,%d,%d,%#x)" % e for e in res["errlog"]))
    for label, x, y, eq in res.get("probes", []):
        print(f"  probe {label}: {x:#x} vs {y:#x} -> {'equal' if eq else 'DIFFER'}")
    if "compressed" in res:
        print(f"  handle {res['handle']:#x} slot u16 +0x116 = {res['compressed']}")
    if res.get("zalloc_sizes"):
        print(f"  zcalloc sizes {[hex(x) for x in res['zalloc_sizes']]}")
    print(f"  insns {res.get('insns')} r0={res.get('r0')} stage={res.get('stage', '-')}")
    print(f"  firmware {res['verdict']}  python {res['python']}"
          + (f" ({res['python_reason']})" if res.get("python_reason") else "")
          + (f"  reason: {res['reason']}" if res.get("reason") else ""))


def cmd_run(args) -> int:
    card = Path(args.card)
    for p in (Path(args.image), card / "CMP.LST", card / (args.name + ".cmp"),
              Path(args.ind) if args.ind else card / (args.name + ".ind")):
        if not p.exists():
            print(f"missing input: {p}", file=sys.stderr)
            return 3
    res = run_case(args.image, card, args.name, Path(args.ind) if args.ind else None,
                   args.offset, args.length, args.shift, args.cfg_chunk)
    print(json.dumps(res, default=str)) if args.json else show(res)
    if res["verdict"] == "BLOCKED":
        return 4
    return 0 if args.expect in (None, res["verdict"]) else 1


def cmd_batch(args) -> int:
    card, mdir = Path(args.card), Path(args.mutants)
    rows, rc = [], 0
    for ind in sorted(mdir.glob("*.ind")):
        res = run_case(args.image, card, args.name, ind, 0, None, 0)
        show(res)
        rows.append(res)
        if res["verdict"] == "BLOCKED":
            rc = 4
    print("\nvariant        firmware  python   agree")
    for r in rows:
        agree = (r["verdict"] == "ACCEPT") == (r["python"] == "ACCEPT")
        print(f"{Path(r['ind']).stem:<14} {r['verdict']:<9} {r['python']:<8} "
              f"{'yes' if agree else 'NO'}  stage={r.get('stage', '-')}")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(rows, indent=1, default=str))
    return rc


# ---------------------------------------------------------------------------
# self-test (no vendor bytes)


def selftest() -> int:
    fails = []

    def check(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    chunks = [bytes(i * 7 & 0xFF for i in range(0x10000)), b"tail" * 100]
    streams = [zlib.compress(c, 6) for c in chunks]
    cmp_b = b"".join(streams)
    ind_b = struct.pack("<4I", sum(map(len, chunks)), len(cmp_b), 2, 0x10000)
    ind_b += struct.pack("<2I", 0, len(streams[0]))
    v, data = python_verdict(cmp_b, ind_b, 5, 100)
    check("reference: synthetic pair accepted, slice right", v == "ACCEPT" and data == b"".join(chunks)[5:105])
    c2, i2 = shifted_pair(cmp_b, ind_b, 4096)
    v2, d2 = python_verdict(c2, i2, 0, 0x10000 + 400)
    check("shift: index moved with the decoy still decodes", v2 == "ACCEPT" and d2 == b"".join(chunks))
    check("shift: decoy starts with a zlib header", c2[:2] == b"\x78\x9c")
    check("shift: word 1 grows by k", struct.unpack_from("<I", i2, 4)[0] == len(cmp_b) + 4096)
    bad = bytearray(ind_b)
    struct.pack_into("<I", bad, 20, len(streams[0]) - 1)
    check("reference: off_last-1 rejected", python_verdict(cmp_b, bytes(bad), 0, 10)[0] == "REJECT")
    try:
        shifted_pair(cmp_b, ind_b, 3)
        small = False
    except ValueError:
        small = True
    check("shift: smaller than the decoy is refused", small)

    fs = GuestFS({"\\SystemSD\\a.cmp": b"0123456789"})
    h = fs.open("\\SYSTEMSD\\A.CMP", "rb")
    check("fs: open is case-insensitive", h != 0)
    check("fs: missing file opens as 0", fs.open("\\SystemSD\\b", "rb") == 0)
    check("fs: seek set + read", fs.seek(h, 3, 0) == 0 and fs.read(h, 4) == b"3456")
    check("fs: seek cur negative", fs.seek(h, (-2) & M32, 1) == 0 and fs.tell(h) == 5)
    check("fs: seek past end fails", fs.seek(h, 11, 0) == M32)
    check("fs: log records the seek offset", ("seek", "\\SYSTEMSD\\A.CMP", 3, 0, 0) in fs.log)

    # thunk finder on a synthetic text: mov.l @(1,pc),r0; mov.l @r0,r0; jmp @r0; nop; pool
    text = struct.pack("<4HI", 0xD001, 0x6002, 0x402B, 0x0009, 0x0055D030)
    check("thunk: pool slot named", find_thunks(0x1000, text + b"\0" * 8, {0x55D030: "strlen"}) == {"strlen": 0x1000})
    check("thunk: unknown slot ignored", find_thunks(0x1000, text + b"\0" * 8, {}) == {})
    check("signed()", signed(0xFFFFFFFF) == -1 and signed(5) == 5)
    print("selftest:", "OK" if not fails else f"FAIL ({len(fails)})")
    return 0 if not fails else 1


def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    for name in ("run", "batch"):
        s = sub.add_parser(name)
        s.add_argument("image")
        s.add_argument("--card", required=True, help="directory holding CMP.LST and REFER001/")
        s.add_argument("--name", required=True, help="e.g. REFER001/ADDRE001.DAT")
        if name == "run":
            s.add_argument("--ind")
            s.add_argument("--offset", type=lambda v: int(v, 0), default=0)
            s.add_argument("--length", type=lambda v: int(v, 0))
            s.add_argument("--shift", type=lambda v: int(v, 0), default=0)
            s.add_argument("--expect", choices=("ACCEPT", "REJECT", "WRONG"))
            s.add_argument("--cfg-chunk", type=lambda v: int(v, 0), default=0x10000,
                           help="harness control: the mount's chunk constant "
                                "(firmware 0x10000, built in fn 0x0041ba90 +0x6e)")
            s.add_argument("--json", action="store_true")
        else:
            s.add_argument("--mutants", required=True)
            s.add_argument("--json-out")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "batch":
        return cmd_batch(args)
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
