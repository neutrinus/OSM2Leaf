#!/usr/bin/env python3
"""Let the EU 2011 Audio.exe start its own tuner driver on a USA unit (M1.60).

Why
---
The EU radio screen (``RDSCC.dll``) talks only to the EU ``Audio.exe``
(IPC ids ``0x83000001``/``0x82000001``, queue ``AVOSM_QUEUE_RDS``, shared
block ``rds_shared_mem``); the US ``Audio.exe`` listens on the RBDS ids, so
after the M1.59 transplant the radio screen is not connected to anything
(EXP-2026-11-24-M1.60). The EU ``Audio.exe`` in turn needs the driver class
``CRds`` of the unit's ``anwdrv.dll``: 20 of its 29 tuner IOCTLs exist only
there, and it waits on events only ``CRds`` sets. ``CRds`` is device
``TNR2:``. The unit's kernel has the registry key
``\\Drivers\\Launch\\Rds`` on every unit, but ``AppLaunch.dll`` activates it
only for area Euro.

What this tool changes
----------------------
Only the original EU ``Audio.exe`` in image A, both copies, then ``SUM4``:

* a 0x98-byte routine with the key name in the zero slack after the code
  section (``0x45150``..``0x451e8``; the section's ``psize`` covers it);
* one pool word of ``OpenDriver`` (fn ``0x35a98``): the failure branch,
  which only logged, now calls the routine.

The routine runs only when ``CreateFile(L"TNR2:")`` failed. It calls
``ActivateDevice(L"\\Drivers\\Launch\\Rds", 0x32)`` (the call and arguments
``AppLaunch.dll`` uses; ``Audio.exe`` already imports it), opens ``TNR2:``
again once and continues on the function's own success or failure path. On
a Euro unit ``TNR2:`` opens the first time and the routine never runs.

NOT known: whether the audio micom of a USA unit answers the RDS-mode
commands ``CRds`` sends (mode id 3; the USA class uses 0xd). That is the car
test. The emulator has no audio micom, so the routine is not exercised
there.

Do not combine with ``audio_transplant.py`` (the tool refuses a card whose
``Audio.exe`` is not the EU build) or with ``audio_tnr_patch.py``.

Usage::

    audio_rds_launch.py show CARD.img
    audio_rds_launch.py patch CARD.img --in-place      # or -o OUT
    audio_rds_launch.py unpatch CARD.img --in-place
    audio_rds_launch.py --selftest

Works on the whole card image or on its first 100 MiB. No vendor bytes are
committed: the tool checks the bytes it expects and refuses otherwise.
"""
from __future__ import annotations

import argparse
import array
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cerom  # noqa: E402

COPIES = (0x200000, 0x2000000)
HDR = 0x200
NKOK_LEN, NKOK_TAG, NKOK_SUM4 = 0x00, 0x30, 0x34
READ = 0x3E00000
MODULE = "Audio.exe"

CODE_VA = 0x11000            # realaddr of the code section
OPEN_FN = 0x35A98            # OpenDriver (tuner)
POOL_LOG = 0x35AF4           # pool word: error-log function, failure branch only
LOG_FN = 0x35D84
POOL_ACCESS, ACCESS = 0x35AE8, 0xC0000000
POOL_NAME, NAME_VA = 0x35AEC, 0x1DDD0      # L"TNR2:"
POOL_TAG, TAG_VA = 0x35AF0, 0x1DDC4        # "OpenDriver"
OK_TAIL, FAIL_RET = 0x35ADA, 0x35AD6
ACTIVATE_STUB = 0x3D11C      # import stub COREDLL!ActivateDevice
ACTIVATE_IAT = 0x46104
CAVE = 0x45150
KEY = "\\Drivers\\Launch\\Rds"
# bytes of OpenDriver from its start to the pool (position-independent part)
OPEN_HEAD = bytes.fromhex(
    "862f224fe07f436800e38260371f80e33c630fd6361f03e3351f00e3341f4fe3"
    "08430cd53e030b4300e70362ff88088f2818")


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def sum4(data, base):
    length = u32(data, base + NKOK_LEN)
    words = array.array("I")
    words.frombytes(bytes(data[base + HDR:base + HDR + length]))
    if sys.byteorder != "little":
        words.byteswap()
    return sum(words) & 0xFFFFFFFF


class Asm:
    """Just enough SH-4 to build the routine; labels resolved in two passes."""

    def __init__(self, org):
        self.org, self.items = org, []

    def op(self, word):
        self.items.append(("op", word))

    def lit(self, reg, label):          # mov.l @(disp,pc),reg
        self.items.append(("lit", reg, label))

    def bt(self, label):
        self.items.append(("bt", label))

    def label(self, name):
        self.items.append(("label", name))

    def align4(self):
        self.items.append(("align",))

    def long(self, value):
        self.items.append(("long", value))

    def raw(self, blob):
        self.items.append(("raw", blob))

    def build(self):
        labels, pc = {}, self.org
        for it in self.items:                      # pass 1: addresses
            k = it[0]
            if k == "label":
                labels[it[1]] = pc
            elif k == "align":
                pc += (-pc) % 4
            elif k == "long":
                pc += 4
            elif k == "raw":
                pc += len(it[1])
            else:
                pc += 2
        out, pc = bytearray(), self.org
        for it in self.items:                      # pass 2: bytes
            k = it[0]
            if k == "label":
                continue
            if k == "align":
                pad = (-pc) % 4
                out += b"\x09\x00" * (pad // 2)
                pc += pad
            elif k == "long":
                v = labels[it[1]] if isinstance(it[1], str) else it[1]
                out += struct.pack("<I", v)
                pc += 4
            elif k == "raw":
                out += it[1]
                pc += len(it[1])
            elif k == "op":
                out += struct.pack("<H", it[1])
                pc += 2
            elif k == "lit":
                tgt = labels[it[2]]
                d = tgt - ((pc & ~3) + 4)
                if d < 0 or d % 4 or d // 4 > 255 or tgt % 4:
                    raise ValueError("literal out of reach")
                out += struct.pack("<H", 0xD000 | (it[1] << 8) | (d // 4))
                pc += 2
            elif k == "bt":
                d = labels[it[1]] - (pc + 4)
                if d % 2 or not -256 <= d // 2 <= 127:
                    raise ValueError("branch out of reach")
                out += struct.pack("<H", 0x8900 | ((d // 2) & 0xFF))
                pc += 2
        return bytes(out), labels


def routine():
    """Machine code of the routine at CAVE. Entered by ``jsr`` from the
    failure branch (r8 = this, frame of OpenDriver intact, pr = FAIL_RET)."""
    a = Asm(CAVE)
    a.lit(4, "L_key")           # r4 = key name
    a.lit(3, "L_act")
    a.op(0x430B)                # jsr @r3            ActivateDevice(key, 0x32)
    a.op(0xE532)                #  mov #0x32,r5
    a.op(0x2008)                # tst r0,r0
    a.bt("fail")
    a.op(0x88FF)                # cmp/eq #-1,r0
    a.bt("fail")
    a.op(0xE300)                # mov #0,r3          the CreateFile call again
    a.op(0x1F37)                # mov.l r3,@(28,r15)
    a.op(0xE380)                # mov #-128,r3
    a.op(0x633C)                # extu.b r3,r3
    a.op(0x1F36)                # mov.l r3,@(24,r15)
    a.op(0xE303)                # mov #3,r3
    a.op(0x1F35)                # mov.l r3,@(20,r15)
    a.op(0xE300)                # mov #0,r3
    a.op(0x1F34)                # mov.l r3,@(16,r15)
    a.op(0x6082)                # mov.l @r8,r0       vtable
    a.op(0xE34F)                # mov #79,r3
    a.op(0x4308)                # shll2 r3           0x13c
    a.op(0x033E)                # mov.l @(r0,r3),r3
    a.lit(6, "L_acc")
    a.lit(5, "L_name")
    a.op(0x6483)                # mov r8,r4
    a.op(0x430B)                # jsr @r3
    a.op(0xE700)                #  mov #0,r7
    a.op(0x88FF)                # cmp/eq #-1,r0
    a.bt("fail")
    a.op(0x1808)                # mov.l r0,@(32,r8)  handle
    a.lit(3, "L_ok")
    a.op(0x432B)                # jmp @r3            success tail of OpenDriver
    a.op(0x0009)                #  nop
    a.label("fail")
    a.lit(3, "L_ret")
    a.op(0x432A)                # lds r3,pr          return into the failure branch
    a.lit(3, "L_log")
    a.lit(7, "L_tag")
    a.op(0xE61B)                # mov #27,r6
    a.op(0xE50A)                # mov #10,r5
    a.op(0x432B)                # jmp @r3            the original log call
    a.op(0xE406)                #  mov #6,r4
    a.align4()
    for name, value in (("L_key", "key"), ("L_act", ACTIVATE_STUB), ("L_acc", ACCESS),
                        ("L_name", NAME_VA), ("L_ok", OK_TAIL), ("L_ret", FAIL_RET),
                        ("L_log", LOG_FN), ("L_tag", TAG_VA)):
        a.label(name)
        a.long(value)
    a.label("key")
    a.raw(KEY.encode("utf-16le") + b"\0\0")
    return a.build()


def locate(data, base):
    """File offset of VA 0x11000 of Audio.exe in the copy at ``base``; checks."""
    if bytes(data[base + NKOK_TAG:base + NKOK_TAG + 4]) != b"SUM4":
        raise SystemExit("audio_rds_launch: no SUM4 tag at 0x%x" % (base + NKOK_TAG))
    rom = cerom.CERom(data, base + HDR)
    mod = [m for m in rom.modules() if m["name"].lower() == MODULE.lower()]
    if len(mod) != 1:
        raise SystemExit("audio_rds_launch: %s not found in copy 0x%x" % (MODULE, base))
    secs = list(rom.o32(mod[0]))
    code = secs[0]
    if code["realaddr"] != CODE_VA or code["psize"] < CAVE + 0xA0 - CODE_VA:
        raise SystemExit("audio_rds_launch: copy 0x%x: Audio.exe is not the EU 2011 build "
                         "(code at 0x%x, psize 0x%x)" % (base, code["realaddr"], code["psize"]))
    return rom.va2file(code["dataptr"]), code


def va(off0, addr):
    return off0 + (addr - CODE_VA)


def state(data, base):
    """('clean'|'patched', off0) or SystemExit."""
    off0, code = locate(data, base)
    blob = routine()[0]
    head = bytes(data[va(off0, OPEN_FN):va(off0, OPEN_FN) + len(OPEN_HEAD)])
    if head != OPEN_HEAD:
        raise SystemExit("audio_rds_launch: copy 0x%x: OpenDriver bytes differ; refusing" % base)
    for pool, want in ((POOL_ACCESS, ACCESS), (POOL_NAME, NAME_VA), (POOL_TAG, TAG_VA)):
        if u32(data, va(off0, pool)) != want:
            raise SystemExit("audio_rds_launch: copy 0x%x: pool word 0x%x differs" % (base, pool))
    if bytes(data[va(off0, NAME_VA):va(off0, NAME_VA) + 12]) != "TNR2:".encode("utf-16le") + b"\0\0":
        raise SystemExit("audio_rds_launch: copy 0x%x: tuner literal is not TNR2: "
                         "(undo audio_tnr_patch.py first)" % base)
    stub = bytes(data[va(off0, ACTIVATE_STUB):va(off0, ACTIVATE_STUB) + 12])
    if u32(stub, 8) != ACTIVATE_IAT:
        raise SystemExit("audio_rds_launch: copy 0x%x: ActivateDevice stub not found" % base)
    cave = bytes(data[va(off0, CAVE):va(off0, CAVE) + len(blob)])
    log = u32(data, va(off0, POOL_LOG))
    if log == LOG_FN and cave == bytes(len(blob)):
        return "clean", off0
    if log == CAVE and cave == blob:
        return "patched", off0
    raise SystemExit("audio_rds_launch: copy 0x%x: unexpected bytes (pool 0x%x); refusing" % (base, log))


def edit(data: bytearray, want_patched: bool):
    """Apply or remove the patch in memory; returns [(offset, bytes)] writes."""
    writes = []
    blob = routine()[0]
    for base in COPIES:
        st, off0 = state(data, base)
        if (st == "patched") == want_patched:
            continue
        new_cave = blob if want_patched else bytes(len(blob))
        new_pool = struct.pack("<I", CAVE if want_patched else LOG_FN)
        data[va(off0, CAVE):va(off0, CAVE) + len(blob)] = new_cave
        data[va(off0, POOL_LOG):va(off0, POOL_LOG) + 4] = new_pool
        writes.append((va(off0, CAVE), new_cave))
        writes.append((va(off0, POOL_LOG), new_pool))
        s = struct.pack("<I", sum4(data, base))
        data[base + NKOK_SUM4:base + NKOK_SUM4 + 4] = s
        writes.append((base + NKOK_SUM4, s))
    return writes


def cmd_show(path):
    with open(path, "rb") as fh:
        data = fh.read(READ)
    ok = True
    for base in COPIES:
        st, off0 = state(data, base)
        stored, computed = u32(data, base + NKOK_SUM4), sum4(data, base)
        ok &= stored == computed
        print("copy 0x%07x: %s; routine at file 0x%x; SUM4 stored 0x%08x computed 0x%08x %s"
              % (base, st, va(off0, CAVE), stored, computed, "ok" if stored == computed else "MISMATCH"))
    return 0 if ok else 1


def cmd_edit(path, want_patched, in_place, out):
    if not in_place and not out:
        raise SystemExit("audio_rds_launch: give --in-place or -o OUT")
    with open(path, "rb") as fh:
        data = bytearray(fh.read(READ))
    writes = edit(data, want_patched)
    target = path if in_place else out
    if not in_place:
        shutil.copyfile(path, out)
    with open(target, "r+b") as fh:
        for off, blob in writes:
            fh.seek(off)
            fh.write(blob)
    with open(target, "rb") as fh:
        check = fh.read(READ)
    for base in COPIES:
        st, _ = state(check, base)
        if (st == "patched") != want_patched or u32(check, base + NKOK_SUM4) != sum4(check, base):
            raise SystemExit("audio_rds_launch: verify failed at 0x%x" % base)
        print("copy 0x%07x: %s; SUM4 0x%08x" % (base, st, u32(check, base + NKOK_SUM4)))
    print("verify: ok (%d write(s))" % len(writes))
    return 0


def selftest():
    blob, lab = routine()
    assert CAVE + len(blob) <= 0x45200, hex(len(blob))
    assert lab["key"] + 2 * (len(KEY) + 1) == CAVE + len(blob)
    w = struct.unpack_from("<%dH" % ((lab["L_key"] - CAVE) // 2), blob)
    # first literal load reaches the key pointer, which points at the key text
    assert u32(blob, lab["L_key"] - CAVE) == lab["key"]
    assert blob[lab["key"] - CAVE:].decode("utf-16le") == KEY + "\0"
    assert w[0] == 0xD400 | ((lab["L_key"] - ((CAVE & ~3) + 4)) // 4)
    # every bt reaches the label that loads FAIL_RET into pr
    bts = [i for i, x in enumerate(w) if x >> 8 == 0x89]
    assert len(bts) == 3
    for i in bts:
        d = w[i] & 0xFF
        d = d - 256 if d > 127 else d
        assert CAVE + 2 * i + 4 + 2 * d == lab["fail"], i
    assert w[(lab["fail"] - CAVE) // 2 + 1] == 0x432A
    pool = [u32(blob, lab["L_key"] - CAVE + 4 * i) for i in range(8)]
    assert pool[1:] == [ACTIVATE_STUB, ACCESS, NAME_VA, OK_TAIL, FAIL_RET, LOG_FN, TAG_VA]
    # every pc-relative load lands on the pool word its label names
    loads = {0: "L_key", 1: "L_act"}
    for i, name in loads.items():
        pc = CAVE + 2 * i
        assert (pc & ~3) + 4 + 4 * (w[i] & 0xFF) == lab[name], name
    # negative: a branch that cannot reach raises
    a = Asm(0)
    a.bt("far")
    a.raw(bytes(0x400))
    a.label("far")
    try:
        a.build()
    except ValueError:
        pass
    else:
        raise AssertionError("out-of-reach branch must raise")
    print("selftest ok")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("show").add_argument("card")
    for nm in ("patch", "unpatch"):
        q = sub.add_parser(nm)
        q.add_argument("card")
        q.add_argument("--in-place", action="store_true")
        q.add_argument("-o", "--out")
    a = p.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "show":
        return cmd_show(a.card)
    if a.cmd in ("patch", "unpatch"):
        return cmd_edit(a.card, a.cmd == "patch", a.in_place, a.out)
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
