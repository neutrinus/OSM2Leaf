#!/usr/bin/env python3
"""sh4fpu.py - the SH-4 FPU for the L3 interpreter (M3.34).

``l3_harness.engine.PySh4`` stops at the first FPU instruction.  The map
library ``STDDLL.dll`` computes mesh levels and map coordinates in floating
point, so its routines could not be executed.  ``PySh4Fpu`` is a subclass
that adds the FPU and leaves every integer instruction to the base class:

* registers ``FR0``-``FR15`` and the bank ``XF0``-``XF15`` (raw 32-bit
  words), ``FPUL``, ``FPSCR`` with the bits a compiler uses: ``PR`` (19,
  double precision), ``SZ`` (20, 64-bit ``fmov``), ``FR`` (21, bank);
* ``sts``/``lds`` of ``FPUL`` and ``FPSCR`` (register and ``@-Rn``/``@Rn+``
  forms);
* ``fmov`` in every addressing form, ``fldi0``/``fldi1``, ``flds``/``fsts``,
  ``float``, ``ftrc``, ``fcnvsd``/``fcnvds``, ``fadd``/``fsub``/``fmul``/
  ``fdiv``, ``fcmp/eq``/``fcmp/gt``, ``fneg``/``fabs``/``fsqrt``, ``fmac``,
  ``fschg``/``frchg``.

Arithmetic is IEEE 754 round-to-nearest: single-precision results are
rounded by packing to 32 bits, double-precision ones are host doubles.
``ftrc`` truncates and saturates as the SH-4 manual says.  Not modelled, and
raised as ``IllegalInstruction``: ``fipr``/``ftrv``/``fsca``/``fsrra``,
rounding mode RZ, exceptions and denormal traps.

Usage:
    from sh4fpu import PySh4Fpu      # drop-in for PySh4
    sh4fpu.py --selftest
"""
from __future__ import annotations

import math
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "l3_harness"))

from engine import IllegalInstruction, PySh4  # noqa: E402

M32 = 0xFFFFFFFF
FPSCR_PR = 1 << 19
FPSCR_SZ = 1 << 20
FPSCR_FR = 1 << 21
FPSCR_RESET = 0x00040001
FPSCR_MASK = 0x003FFFFF


def f32_bits(value: float) -> int:
    try:
        return struct.unpack("<I", struct.pack("<f", value))[0]
    except OverflowError:
        return 0x7F800000 if value > 0 else 0xFF800000


def bits_f32(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", bits & M32))[0]


def f64_bits(value: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def bits_f64(bits: int) -> float:
    return struct.unpack("<d", struct.pack("<Q", bits & 0xFFFFFFFFFFFFFFFF))[0]


def trunc_sat(value: float) -> int:
    """``ftrc``: truncate toward zero; NaN and overflow saturate (SH-4 manual)."""
    if value != value:
        return 0x80000000
    if value >= 2147483648.0:
        return 0x7FFFFFFF
    if value <= -2147483649.0:
        return 0x80000000
    return int(value) & M32


class PySh4Fpu(PySh4):
    """PySh4 plus the FPU.  See the module docstring for the modelled set."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fr = [0] * 16          # current bank, raw words
        self.xf = [0] * 16          # other bank
        self._regs["fpscr"] = FPSCR_RESET
        self._regs["fpul"] = 0
        self.fpu_count = 0

    # -- helpers -----------------------------------------------------------

    def _pr(self) -> bool:
        return bool(self._regs["fpscr"] & FPSCR_PR)

    def _sz(self) -> bool:
        return bool(self._regs["fpscr"] & FPSCR_SZ)

    def _set_fpscr(self, value: int) -> None:
        old = self._regs["fpscr"]
        value &= FPSCR_MASK
        if (old ^ value) & FPSCR_FR:
            self.fr, self.xf = self.xf, self.fr
        self._regs["fpscr"] = value

    def _dr(self, n: int, pc: int) -> float:
        if n & 1:
            raise IllegalInstruction(f"double operand DR{n} is odd at {pc:#010x}")
        return bits_f64((self.fr[n] << 32) | self.fr[n + 1])

    def _set_dr(self, n: int, value: float, pc: int) -> None:
        if n & 1:
            raise IllegalInstruction(f"double operand DR{n} is odd at {pc:#010x}")
        bits = f64_bits(value)
        self.fr[n] = (bits >> 32) & M32
        self.fr[n + 1] = bits & M32

    def _get(self, n: int, pc: int) -> float:
        return self._dr(n, pc) if self._pr() else bits_f32(self.fr[n])

    def _put(self, n: int, value: float, pc: int) -> None:
        if self._pr():
            self._set_dr(n, value, pc)
        else:
            self.fr[n] = f32_bits(value)

    def _pair_get(self, n: int) -> tuple[int, int]:
        """64-bit ``fmov`` source: DRn (even n) or XDn (odd n)."""
        bank = self.xf if n & 1 else self.fr
        n &= 0xE
        return bank[n], bank[n + 1]

    def _pair_put(self, n: int, hi: int, lo: int) -> None:
        bank = self.xf if n & 1 else self.fr
        n &= 0xE
        bank[n], bank[n + 1] = hi & M32, lo & M32

    def _load64(self, va: int) -> tuple[int, int]:
        """A double in memory: little-endian hosts keep the low word first."""
        a, b = self._load(va, 4), self._load((va + 4) & M32, 4)
        return (b, a) if self.endian == "little" else (a, b)

    def _store64(self, va: int, hi: int, lo: int) -> None:
        first, second = (lo, hi) if self.endian == "little" else (hi, lo)
        self._store(va, 4, first)
        self._store((va + 4) & M32, 4, second)

    # -- dispatch ----------------------------------------------------------

    def _execute(self, insn: int, pc: int) -> None:
        if insn >> 12 == 0xF:
            self.fpu_count += 1
            self._exec_fpu(insn, pc)
            return
        key = insn & 0xF0FF
        if key in _SYS:
            self.fpu_count += 1
            self._exec_fpsys(key, (insn >> 8) & 0xF)
            return
        super()._execute(insn, pc)

    def _exec_fpsys(self, key: int, n: int) -> None:
        regs = self._regs
        rn = "r%d" % n
        if key == 0x005A:                                # sts fpul,Rn
            self._arm = "sts_fpul"
            regs[rn] = regs["fpul"] & M32
        elif key == 0x006A:                              # sts fpscr,Rn
            self._arm = "sts_fpscr"
            regs[rn] = regs["fpscr"] & M32
        elif key == 0x405A:                              # lds Rn,fpul
            self._arm = "lds_fpul"
            regs["fpul"] = regs[rn] & M32
        elif key == 0x406A:                              # lds Rn,fpscr
            self._arm = "lds_fpscr"
            self._set_fpscr(regs[rn])
        elif key == 0x4052:                              # sts.l fpul,@-Rn
            self._arm = "sts.l_fpul"
            regs[rn] = (regs[rn] - 4) & M32
            self._store(regs[rn], 4, regs["fpul"])
        elif key == 0x4062:                              # sts.l fpscr,@-Rn
            self._arm = "sts.l_fpscr"
            regs[rn] = (regs[rn] - 4) & M32
            self._store(regs[rn], 4, regs["fpscr"])
        elif key == 0x4056:                              # lds.l @Rn+,fpul
            self._arm = "lds.l_fpul"
            regs["fpul"] = self._load(regs[rn], 4)
            regs[rn] = (regs[rn] + 4) & M32
        else:                                            # 0x4066 lds.l @Rn+,fpscr
            self._arm = "lds.l_fpscr"
            self._set_fpscr(self._load(regs[rn], 4))
            regs[rn] = (regs[rn] + 4) & M32

    def _exec_fpu(self, insn: int, pc: int) -> None:
        regs = self._regs
        n = (insn >> 8) & 0xF
        m = (insn >> 4) & 0xF
        sub = insn & 0xF
        rn, rm = "r%d" % n, "r%d" % m
        if sub <= 0x3:                                   # fadd fsub fmul fdiv
            a, b = self._get(n, pc), self._get(m, pc)
            self._arm = ("fadd", "fsub", "fmul", "fdiv")[sub]
            if sub == 0:
                value = a + b
            elif sub == 1:
                value = a - b
            elif sub == 2:
                value = a * b
            elif b == 0.0:
                value = math.nan if a == 0.0 or a != a else math.copysign(math.inf, a) * math.copysign(1.0, b)
            else:
                value = a / b
            self._put(n, value, pc)
        elif sub == 0x4:                                 # fcmp/eq
            self._arm = "fcmp/eq"
            self._set_t(self._get(n, pc) == self._get(m, pc))
        elif sub == 0x5:                                 # fcmp/gt
            self._arm = "fcmp/gt"
            self._set_t(self._get(n, pc) > self._get(m, pc))
        elif sub == 0x6:                                 # fmov @(R0,Rm),FRn
            self._arm = "fmov_load_r0"
            self._fmov_load(n, (regs["r0"] + regs[rm]) & M32)
        elif sub == 0x7:                                 # fmov FRm,@(R0,Rn)
            self._arm = "fmov_store_r0"
            self._fmov_store(m, (regs["r0"] + regs[rn]) & M32)
        elif sub == 0x8:                                 # fmov @Rm,FRn
            self._arm = "fmov_load"
            self._fmov_load(n, regs[rm])
        elif sub == 0x9:                                 # fmov @Rm+,FRn
            self._arm = "fmov_load_inc"
            self._fmov_load(n, regs[rm])
            regs[rm] = (regs[rm] + (8 if self._sz() else 4)) & M32
        elif sub == 0xA:                                 # fmov FRm,@Rn
            self._arm = "fmov_store"
            self._fmov_store(m, regs[rn])
        elif sub == 0xB:                                 # fmov FRm,@-Rn
            self._arm = "fmov_store_dec"
            regs[rn] = (regs[rn] - (8 if self._sz() else 4)) & M32
            self._fmov_store(m, regs[rn])
        elif sub == 0xC:                                 # fmov FRm,FRn
            self._arm = "fmov_reg"
            if self._sz():
                self._pair_put(n, *self._pair_get(m))
            else:
                self.fr[n] = self.fr[m]
        elif sub == 0xD:
            self._exec_fpu_unary(insn, n, m, pc)
        elif sub == 0xE:                                 # fmac FR0,FRm,FRn
            self._arm = "fmac"
            if self._pr():
                raise IllegalInstruction(f"fmac with FPSCR.PR=1 at {pc:#010x}")
            self.fr[n] = f32_bits(bits_f32(self.fr[0]) * bits_f32(self.fr[m]) + bits_f32(self.fr[n]))
        else:
            raise IllegalInstruction(f"FPU opcode {insn:#06x} at {pc:#010x} is not modelled")

    def _fmov_load(self, n: int, va: int) -> None:
        if self._sz():
            self._pair_put(n, *self._load64(va))
        else:
            self.fr[n] = self._load(va, 4)

    def _fmov_store(self, m: int, va: int) -> None:
        if self._sz():
            self._store64(va, *self._pair_get(m))
        else:
            self._store(va, 4, self.fr[m])

    def _exec_fpu_unary(self, insn: int, n: int, m: int, pc: int) -> None:
        regs = self._regs
        if insn == 0xF3FD:                               # fschg
            self._arm = "fschg"
            regs["fpscr"] ^= FPSCR_SZ
        elif insn == 0xFBFD:                             # frchg
            self._arm = "frchg"
            self._set_fpscr(regs["fpscr"] ^ FPSCR_FR)
        elif m == 0x0:                                   # fsts FPUL,FRn
            self._arm = "fsts"
            self.fr[n] = regs["fpul"] & M32
        elif m == 0x1:                                   # flds FRn,FPUL
            self._arm = "flds"
            regs["fpul"] = self.fr[n]
        elif m == 0x2:                                   # float FPUL,FRn
            self._arm = "float"
            value = regs["fpul"] & M32
            value -= (value & 0x80000000) << 1
            self._put(n, float(value), pc)
        elif m == 0x3:                                   # ftrc FRn,FPUL
            self._arm = "ftrc"
            regs["fpul"] = trunc_sat(self._get(n, pc))
        elif m == 0x4:                                   # fneg
            self._arm = "fneg"
            self.fr[n] ^= 0x80000000
        elif m == 0x5:                                   # fabs
            self._arm = "fabs"
            self.fr[n] &= 0x7FFFFFFF
        elif m == 0x6:                                   # fsqrt
            self._arm = "fsqrt"
            value = self._get(n, pc)
            self._put(n, math.sqrt(value) if value >= 0 else math.nan, pc)
        elif m == 0x8:                                   # fldi0
            self._arm = "fldi0"
            self.fr[n] = 0
        elif m == 0x9:                                   # fldi1
            self._arm = "fldi1"
            self.fr[n] = 0x3F800000
        elif m == 0xA:                                   # fcnvsd FPUL,DRn
            self._arm = "fcnvsd"
            self._set_dr(n, bits_f32(regs["fpul"]), pc)
        elif m == 0xB:                                   # fcnvds DRn,FPUL
            self._arm = "fcnvds"
            regs["fpul"] = f32_bits(self._dr(n, pc))
        else:
            raise IllegalInstruction(f"FPU opcode {insn:#06x} at {pc:#010x} is not modelled")


_SYS = frozenset((0x005A, 0x006A, 0x405A, 0x406A, 0x4052, 0x4062, 0x4056, 0x4066))


# -- selftest ---------------------------------------------------------------

def _asm_run(words, regs=None, fr=None, fpscr=FPSCR_RESET, mem=None):
    """Run *words* (then ``rts; nop``) and return the engine."""
    code = b"".join(struct.pack("<H", w) for w in list(words) + [0x000B, 0x0009])
    eng = PySh4Fpu(endian="little")
    eng.map("code", 0x1000, code, "rx")
    eng.map("data", 0x2000, bytearray(mem or bytes(0x100)), "rw")
    eng.map("stack", 0x8000, bytearray(0x400), "rw")
    eng.set_regs(r15=0x8300, **(regs or {}))
    eng._set_fpscr(fpscr)
    for i, v in (fr or {}).items():
        eng.fr[i] = v
    eng.call(0x1000, [])
    return eng


def selftest() -> int:
    fails = []

    def check(name, cond):
        print("%s %s" % ("ok  " if cond else "FAIL", name))
        if not cond:
            fails.append(name)

    one, two, three = f32_bits(1.0), f32_bits(2.0), f32_bits(3.0)
    e = _asm_run([0xF120], fr={1: one, 2: two})                     # fadd fr2,fr1
    check("fadd single 1+2=3", e.fr[1] == three)
    e = _asm_run([0xF123], fr={1: one, 2: three})                    # fdiv fr2,fr1
    check("fdiv single 1/3 rounds to float32", e.fr[1] == f32_bits(1.0 / 3.0))
    e = _asm_run([0xF122], fr={1: f32_bits(0.1), 2: f32_bits(0.2)})
    check("fmul single rounds each step", e.fr[1] == f32_bits(bits_f32(f32_bits(0.1)) * bits_f32(f32_bits(0.2))))
    d = f64_bits(88.0)
    e = _asm_run([0xF243], fpscr=FPSCR_RESET | FPSCR_PR,
                 fr={2: f64_bits(1.0) >> 32, 3: 0, 4: d >> 32, 5: d & M32})    # fdiv dr4,dr2
    check("fdiv double 1/88 = 0x3f8745d1745d1746",
          ((e.fr[2] << 32) | e.fr[3]) == 0x3F8745D1745D1746)
    e = _asm_run([0x405A, 0xF22D], regs={"r0": (-5) & M32})        # lds r0,fpul; float fpul,fr2
    check("float single -5", e.fr[2] == f32_bits(-5.0))
    e = _asm_run([0x405A, 0xF22D], regs={"r0": 7}, fpscr=FPSCR_RESET | FPSCR_PR)
    check("float double 7", ((e.fr[2] << 32) | e.fr[3]) == f64_bits(7.0))
    e = _asm_run([0xF23D, 0x015A], fr={2: f32_bits(-2.75)})          # ftrc fr2,fpul; sts fpul,r1
    check("ftrc truncates toward zero (-2.75 -> -2)", e.get_regs()["r1"] == (-2) & M32)
    e = _asm_run([0xF23D, 0x015A], fr={2: f32_bits(3e10)})
    check("ftrc saturates", e.get_regs()["r1"] == 0x7FFFFFFF)
    e = _asm_run([0x405A, 0xF2AD], regs={"r0": f32_bits(0.125)}, fpscr=FPSCR_RESET | FPSCR_PR)
    check("fcnvsd 0.125", ((e.fr[2] << 32) | e.fr[3]) == f64_bits(0.125))
    d = f64_bits(0.1)
    e = _asm_run([0xF2BD, 0x015A], fpscr=FPSCR_RESET | FPSCR_PR, fr={2: d >> 32, 3: d & M32})
    check("fcnvds rounds 0.1 to float32", e.get_regs()["r1"] == f32_bits(0.1))
    e = _asm_run([0xF125], fr={1: two, 2: one})                     # fcmp/gt fr2,fr1
    check("fcmp/gt 2 > 1 sets T", e.get_regs()["sr"] & 1 == 1)
    e = _asm_run([0xF124], fr={1: two, 2: one})
    check("fcmp/eq 2 == 1 clears T", e.get_regs()["sr"] & 1 == 0)
    e = _asm_run([0xF18D, 0xF29D, 0xF24D, 0xF35D], fr={3: f32_bits(-4.0)})
    check("fldi0, fldi1, fneg, fabs", e.fr[1] == 0 and e.fr[2] == f32_bits(-1.0) and e.fr[3] == f32_bits(4.0))
    e = _asm_run([0xFFCB, 0xF8F9], regs={}, fr={12: 0x12345678})    # fmov fr12,@-r15; fmov @r15+,fr8
    check("fmov push/pop keeps the raw word and the stack pointer",
          e.fr[8] == 0x12345678 and e.get_regs()["r15"] == 0x8300)
    e = _asm_run([0xF12A, 0xF318], regs={"r1": 0x2020}, fr={2: 0xCAFEF00D})   # fmov fr2,@r1; fmov @r1,fr3
    check("fmov fr2,@r1 / fmov @r1,fr3", e.fr[3] == 0xCAFEF00D and e.read_mem(0x2020, 4) == b"\x0d\xf0\xfe\xca")
    e = _asm_run([0x016A, 0x425A, 0x406A, 0x036A],
                 regs={"r0": FPSCR_RESET | FPSCR_PR, "r2": 0x55})    # sts fpscr,r1; lds r2,fpul; lds r0,fpscr; sts fpscr,r3
    r = e.get_regs()
    check("sts/lds fpscr and fpul", r["r1"] == FPSCR_RESET and r["r3"] == FPSCR_RESET | FPSCR_PR and r["fpul"] == 0x55)
    e = _asm_run([0xFBFD], fr={0: 1})                                # frchg
    check("frchg swaps the banks", e.fr[0] == 0 and e.xf[0] == 1)
    e = _asm_run([0xF3FD, 0xF12A, 0xF418], regs={"r1": 0x2030},
                 fr={2: 0x40568000, 3: 0x00000000})                  # fschg; fmov dr2,@r1; fmov @r1,dr4
    check("64-bit fmov keeps a double (little-endian: low word first)",
          e.fr[4] == 0x40568000 and e.fr[5] == 0 and e.read_mem(0x2030, 8) == struct.pack("<d", 90.0))
    try:
        _asm_run([0xF1ED])                                           # fipr
        check("fipr is refused", False)
    except IllegalInstruction:
        check("fipr is refused", True)
    try:
        base = PySh4(endian="little")
        base.map("code", 0x1000, struct.pack("<HHH", 0xF120, 0x000B, 0x0009), "rx")
        base.map("stack", 0x8000, bytearray(0x100), "rw")
        base.set_regs(r15=0x8080)
        base.call(0x1000, [])
        check("control: the base engine still refuses FPU code", False)
    except IllegalInstruction:
        check("control: the base engine still refuses FPU code", True)
    e = _asm_run([0xE105, 0x7103])                                   # mov #5,r1; add #3,r1
    check("integer instructions go to the base class", e.get_regs()["r1"] == 8)
    print("selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    print(__doc__)
