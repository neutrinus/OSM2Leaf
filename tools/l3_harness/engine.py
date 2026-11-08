#!/usr/bin/env python3
"""One engine interface, three SH-4 back ends (TODO M9.4).

The L3 plan needs to run an original firmware function on our data.  *Where*
it runs is a policy decision: Ghidra P-code to understand a function, QEMU at
native speed to run a whole corpus.  So the harness talks to an **engine**,
never to Ghidra or QEMU directly, and the engine surface is the same for all
back ends:

======================  =================================================
``map(name, va, data, rwx)``  place bytes (or a zero-filled size) at a VA
``read_mem(va, size)``        read bytes back
``write_mem(va, data)``       write bytes
``set_regs(...)``             set any of the 25 SH-4 registers (or ``t``)
``get_regs()``                read all of them back
``call(va, args)``            set PC/PR/r4-r7, run to the return, give ``r0``
``on_exec(va, handler)``      intercept execution at a VA with a host stub
``run_until(stop, max_insns)``  run to a VA, a hook, or the return sentinel
======================  =================================================

Back ends
=========

``PySh4``
    A pure-Python SH-4 interpreter and the **reference** implementation.  It
    models the instruction subset a function-level probe needs (``add``,
    compare/branch, ``dt`` loops, ``jsr``/``bsr``/``rts`` with delay slots,
    ``mov``, loads/stores, shifts, ``ext*``, ``swap*``, stack save/restore).
    Everything else raises :class:`IllegalInstruction` -- it never guesses.
    Slow but exact, needs nothing installed, and defines the expected result.

``GhidraBackend``
    A lazy ``pyghidra``/``EmulatorHelper`` adapter.  Imports nothing at module
    load time: the first memory/register access starts Ghidra and creates the
    emulator.  No pyghidra -> :class:`MissingGhidra` (``MISSING_GHIDRA``); a
    present-but-unusable Ghidra -> :class:`Blocked` (``BLOCKED``).

``QemuBackend``
    ``qemu-system-sh4 -M none -cpu sh7785`` plus the gdbstub remote protocol.
    No binary -> :class:`MissingQemu` (``MISSING_QEMU``); a binary that will
    not start, or a gdbstub handshake that fails -> :class:`Blocked`.

Determinism: no wall clock, no host paths in results, and :meth:`Backend.map`
records every region so all three back ends enforce the *same* overlap,
unmapped-access and read/write-permission rules.  A back end that cannot run
raises; it never returns a plausible-looking result.

Stub contract
-------------

``on_exec(va, handler)`` registers ``handler(engine, va)`` for the moment the
interpreter is about to execute at ``va``.  The handler replaces the whole
function body:

* return ``None``               -> let the instruction execute normally;
* return :class:`StubReturn`    -> set ``r0`` and jump to ``pr`` (a host stub);
* return an ``int``             -> shorthand for ``StubReturn(value)``.

Every stub call is recorded in :attr:`Backend.last_run` so a result can show
what was intercepted instead of claiming the real code ran.

Usage::

    python3 tools/l3_harness/engine.py --selftest
    python3 tools/l3_harness/engine.py --demo --engine pysh4
    python3 tools/l3_harness/engine.py --demo --engine ghidra --json
    python3 tools/l3_harness/engine.py --probe

Exit codes: ``0`` ok, ``1`` check failed, ``2`` usage, ``3`` back end missing,
``4`` blocked.

Known limits (deliberate, loud, and recorded in the M9.4 EXP):

* ``call()`` passes at most four arguments, in ``r4``-``r7``.  Stack arguments
  are a target-setup job (M9.5), not an engine feature; more than four raises
  instead of writing an invented stack frame.
* Every back end single-steps, so the hook and stop rules live in *one* place
  (:meth:`Backend.run_until`).  That is fast enough for a parser probe and
  exactly comparable across engines; the QEMU breakpoint fast path is M9.5
  work, and the Ghidra adapter is written against the documented
  ``EmulatorHelper`` API but has never been executed here (no Ghidra).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

__all__ = [
    "Availability",
    "Backend",
    "Blocked",
    "EngineError",
    "GhidraBackend",
    "IllegalInstruction",
    "MissingGhidra",
    "MissingQemu",
    "PySh4",
    "QemuBackend",
    "RunResult",
    "Runaway",
    "StubReturn",
    "Trap",
    "UnalignedAccess",
    "UnmappedAccess",
    "UsageError",
    "BACKENDS",
    "DEFAULT_MAX_INSNS",
    "ISA",
    "REGISTERS",
    "RETURN_VA",
    "probe_all",
    "synthetic_program",
]

ISA = "SuperH:BE:32:SH-4"

M32 = 0xFFFFFFFF
M64 = 0xFFFFFFFFFFFFFFFF

#: The 25 SH-4 general/core registers this harness models.  FPU registers are
#: deliberately absent: no firmware target needs them yet (M9.5).
REGISTERS: tuple[str, ...] = (
    "r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7",
    "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15",
    "pc", "pr", "sr", "gbr", "vbr", "mach", "macl", "fpul", "fpscr",
)

#: Pseudo-register: the SH-4 T bit, stored as bit 0 of ``sr``.
T_BIT = "t"

#: Return sentinel.  ``call()`` puts this into ``pr``; ``run_until`` stops when
#: the PC reaches it, so no back end has to fetch from it.  Chosen inside the
#: SH-4 P1 area (physical ``0x0c0fff00``) and far from any mapping the harness
#: creates.
RETURN_VA = 0x8C0FFF00

DEFAULT_MAX_INSNS = 2_000_000

#: Exit codes, kept identical to ``runner.py`` so a wrapper can share them.
EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_MISSING = 3
EXIT_BLOCKED = 4


# --------------------------------------------------------------------------
# Errors: one code per failure, so a caller can branch on the string and a
# report can print it verbatim.
# --------------------------------------------------------------------------


class EngineError(RuntimeError):
    """Base class; ``code`` is the stable machine-readable reason."""

    code = "ENGINE"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def as_dict(self) -> dict:
        return {"status": self.code, "reason": self.message}


class MissingGhidra(EngineError):
    code = "MISSING_GHIDRA"


class MissingQemu(EngineError):
    code = "MISSING_QEMU"


class Blocked(EngineError):
    code = "BLOCKED"


class UnmappedAccess(EngineError):
    code = "UNMAPPED"


class UnalignedAccess(EngineError):
    code = "UNALIGNED"


class IllegalInstruction(EngineError):
    code = "ILLEGAL_INSN"


class Trap(EngineError):
    """``trapa``: a WinCE system call.  Stub it, do not emulate it."""

    code = "TRAP"


class Runaway(EngineError):
    code = "RUNAWAY"


class UsageError(EngineError):
    code = "USAGE"


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def px(value: int) -> str:
    return "0x%08x" % (value & M32)


def _sx(value: int, bits: int) -> int:
    """Sign-extend *value* from *bits* to 32 bits."""
    sign = 1 << (bits - 1)
    value &= (1 << bits) - 1
    return (value - (1 << bits)) if value & sign else value


def _mask(value: int) -> int:
    return value & M32


@dataclass(frozen=True)
class StubReturn:
    """A host stub's answer: put *value* in ``r0`` and return to ``pr``."""

    value: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", int(self.value) & M32)


@dataclass
class Region:
    """One mapped range.  Identical bookkeeping for every back end."""

    name: str
    va: int
    size: int
    rwx: str
    data: bytes

    @property
    def end(self) -> int:
        return self.va + self.size


@dataclass
class RunResult:
    """What happened during one ``run_until``/``call``."""

    insns: int
    pc: int
    reason: str                      # "return" | "stop" | "stub" | ...
    stubs: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "insns": self.insns,
            "pc": px(self.pc),
            "reason": self.reason,
            "stubs": [
                {"va": px(item["va"]), "value": px(item["value"])}
                for item in self.stubs
            ],
        }


@dataclass(frozen=True)
class Availability:
    """Whether a back end can run *here*, and why not."""

    name: str
    available: bool
    code: str
    detail: str

    def as_dict(self) -> dict:
        return {
            "engine": self.name,
            "available": self.available,
            "status": "READY" if self.available else self.code,
            "detail": self.detail,
        }


# --------------------------------------------------------------------------
# Backend: the public surface, implemented once.
# --------------------------------------------------------------------------


class Backend:
    """The L3 engine contract.  Subclasses supply only primitives."""

    name = "base"
    #: Honest self-description, copied into every report.
    kind = "base"
    verified = False

    def __init__(self) -> None:
        self._regions: list[Region] = []
        self._hooks: dict[int, list[Callable]] = {}
        self.last_run: RunResult | None = None

    # -- memory map --------------------------------------------------------

    def map(self, name: str, va: int, data, rwx: str = "rwx") -> Region:
        """Map *data* (bytes, or an ``int`` size to zero-fill) at *va*.

        Rejected loudly: an empty name, a duplicate name, a zero or negative
        size, a duplicate permission letter, an unknown permission letter, a
        range outside the 32-bit space, and any overlap with an existing
        region.  Overlap rejection is what catches a wrong ``cerom.py`` map
        before it silently corrupts a run.
        """
        if not isinstance(name, str) or not name:
            raise UsageError("map() needs a non-empty region name")
        if any(region.name == name for region in self._regions):
            raise UsageError(f"map(): region {name!r} already exists")
        if isinstance(data, (bytes, bytearray, memoryview)):
            payload = bytes(data)
            size = len(payload)
        elif isinstance(data, int):
            size = int(data)
            payload = b"\x00" * size
        else:
            raise UsageError(
                f"map({name!r}): data must be bytes or a size, not {type(data).__name__}"
            )
        if size <= 0:
            raise UsageError(f"map({name!r}): size must be positive, got {size}")
        if not isinstance(va, int) or va < 0 or va + size > M32 + 1:
            raise UsageError(f"map({name!r}): address {va!r} leaves the 32-bit space")
        if not isinstance(rwx, str) or not rwx:
            raise UsageError(f"map({name!r}): permissions must be a string like 'rwx'")
        if set(rwx) - set("rwx") or len(set(rwx)) != len(rwx):
            raise UsageError(f"map({name!r}): bad permissions {rwx!r}")

        region = Region(name=name, va=va, size=size, rwx=rwx, data=payload)
        for other in self._regions:
            if region.va < other.end and other.va < region.end:
                raise UsageError(
                    f"map({name!r}): {px(region.va)}..{px(region.end)} overlaps "
                    f"{other.name!r} ({px(other.va)}..{px(other.end)})"
                )
        self._map(region)
        self._regions.append(region)
        self._regions.sort(key=lambda item: item.va)
        return region

    def regions(self) -> list[dict]:
        return [
            {"name": r.name, "va": px(r.va), "size": r.size, "rwx": r.rwx}
            for r in self._regions
        ]

    def region_at(self, va: int) -> Region | None:
        for region in self._regions:
            if region.va <= va < region.end:
                return region
        return None

    def _find_region(self, va: int, size: int, perm: str) -> Region:
        if size <= 0:
            raise UsageError(f"access size must be positive, got {size}")
        if not isinstance(va, int) or va < 0 or va + size > M32 + 1:
            raise UsageError(f"access at {va!r} leaves the 32-bit space")
        end = va + size
        for region in self._regions:
            if region.va <= va and end <= region.end:
                if perm not in region.rwx:
                    raise UnmappedAccess(
                        f"{perm}-access at {px(va)} inside {region.name!r} "
                        f"({region.rwx}) is not allowed"
                    )
                return region
        raise UnmappedAccess(
            f"no mapped region covers {px(va)}..{px(end)} "
            f"({', '.join(r.name for r in self._regions) or 'nothing mapped'})"
        )

    # -- memory access -----------------------------------------------------

    def read_mem(self, va: int, size: int) -> bytes:
        self._find_region(va, size, "r")
        return self._read(va, size)

    def write_mem(self, va: int, data) -> None:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise UsageError("write_mem() needs bytes")
        payload = bytes(data)
        self._find_region(va, len(payload), "w")
        self._write(va, payload)

    # -- registers ---------------------------------------------------------

    def set_regs(self, regs: Mapping | None = None, **kwargs) -> None:
        """Set any subset of :data:`REGISTERS` plus ``t``.

        Unnamed registers keep their value, so a target setup can set ``r15``
        and a single argument without disturbing the rest.  An unknown name is
        a usage error, never silently ignored.
        """
        values: dict[str, int] = {}
        if regs:
            if not isinstance(regs, Mapping):
                raise UsageError("set_regs() takes a mapping of names to values")
            values.update(regs)
        values.update(kwargs)
        if not values:
            raise UsageError("set_regs() needs at least one register")
        # ``t`` writes sr bit 0, so apply it last and only once.
        t_value = values.pop(T_BIT, None)
        for name, value in values.items():
            if name not in REGISTERS:
                raise UsageError(f"set_regs(): unknown SH-4 register {name!r}")
            self._set_reg(name, int(value) & M32)
        if t_value is not None:
            sr = self._get_reg("sr") & ~1
            self._set_reg("sr", sr | (int(t_value) & 1))

    def get_regs(self) -> dict[str, int]:
        values = {name: self._get_reg(name) & M32 for name in REGISTERS}
        values[T_BIT] = values["sr"] & 1
        return values

    # -- execution ---------------------------------------------------------

    def on_exec(self, va: int, handler: Callable) -> None:
        """Call ``handler(engine, va)`` before executing at *va*.

        Handlers stack in registration order.  The first one that returns a
        value ends the dispatch; ``None`` means "execute the instruction".
        """
        if not callable(handler):
            raise UsageError("on_exec() needs a callable handler")
        self._hooks.setdefault(va & M32, []).append(handler)

    def hooks(self) -> dict[int, int]:
        return {va: len(items) for va, items in self._hooks.items()}

    def _dispatch(self, va: int):
        for handler in list(self._hooks.get(va, ())):
            outcome = handler(self, va)
            if outcome is None:
                continue
            if isinstance(outcome, StubReturn):
                return outcome
            if isinstance(outcome, int):
                return StubReturn(outcome)
            raise UsageError(
                f"on_exec handler at {px(va)} returned {type(outcome).__name__}; "
                "use None, StubReturn(...) or an int"
            )
        return None

    @staticmethod
    def _stop_matcher(stop):
        if stop is None:
            return None
        if isinstance(stop, int):
            target = stop & M32
            return lambda va: va == target
        if callable(stop):
            return stop
        try:
            targets = {int(item) & M32 for item in stop}
        except TypeError as exc:  # pragma: no cover - defensive
            raise UsageError(f"run_until() cannot use stop={stop!r}") from exc
        return lambda va: va in targets

    def run_until(self, stop=None, max_insns: int = DEFAULT_MAX_INSNS) -> RunResult:
        """Run until the return sentinel, *stop*, or *max_insns*.

        Stops at :data:`RETURN_VA` (``reason="return"``) and at *stop*
        (``reason="stop"``); a host stub that returns ends one instruction
        cycle and continues at ``pr``, recorded in ``result.stubs``.  Running
        out of budget raises :class:`Runaway` instead of hanging or silently
        returning a half-finished state.
        """
        if not isinstance(max_insns, int) or max_insns <= 0:
            raise UsageError(f"run_until(): max_insns must be positive, got {max_insns!r}")
        matcher = self._stop_matcher(stop)

        insns = 0
        stubs: list[dict] = []
        while True:
            pc = self._get_pc() & M32
            if pc == RETURN_VA:
                result = RunResult(insns=insns, pc=pc, reason="return", stubs=stubs)
                self.last_run = result
                return result
            if matcher is not None and matcher(pc):
                result = RunResult(insns=insns, pc=pc, reason="stop", stubs=stubs)
                self.last_run = result
                return result

            outcome = self._dispatch(pc)
            if outcome is not None:
                self._set_reg("r0", outcome.value)
                target = self._get_reg("pr") & M32
                if target == pc:
                    raise Runaway(
                        f"host stub at {px(pc)} returned to itself (pr == pc); "
                        "the stub did not set a usable return address"
                    )
                self._set_pc(target)
                stubs.append({"va": pc, "value": outcome.value})
                insns += 1
                if insns > max_insns:
                    raise Runaway(
                        f"run_until(): more than {max_insns} instruction/stub cycles; "
                        f"stuck at {px(pc)} (loop or a stub that never returns)"
                    )
                continue

            if insns >= max_insns:
                raise Runaway(
                    f"run_until(): more than {max_insns} instructions without reaching "
                    f"{px(RETURN_VA)} or a stop address; last pc {px(pc)} (infinite loop?)"
                )
            self._step()
            insns += 1

    def call(self, va: int, args: Sequence[int] = ()) -> int:
        """Call the function at *va* with *args* in ``r4``-``r7``.

        Sets ``pc`` and ``pr``, leaves every other register (including the
        stack pointer ``r15``) alone, runs to :data:`RETURN_VA` and returns
        ``r0``.  The full trace is in :attr:`last_run`.
        """
        args = list(args or ())
        if len(args) > 4:
            raise UsageError(
                "call() passes at most four arguments (r4-r7); SH-4 stack "
                "arguments belong to the target setup (M9.5), not to the engine"
            )
        self.set_regs(pc=va & M32, pr=RETURN_VA)
        for index, value in enumerate(args):
            self._set_reg("r%d" % (4 + index), int(value) & M32)
        self.run_until()
        return self._get_reg("r0") & M32

    # -- lifecycle ---------------------------------------------------------

    def probe(self) -> Availability:
        """Whether this back end can run here.  Must not raise."""
        try:
            return self._probe()
        except EngineError as exc:
            return Availability(self.name, False, exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001 - a probe never aborts a report
            return Availability(self.name, False, "BLOCKED", f"{type(exc).__name__}: {exc}")

    def close(self) -> None:
        """Release external resources.  Idempotent."""

    def __enter__(self) -> "Backend":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # -- primitives every back end must provide ----------------------------

    def _probe(self) -> Availability:  # pragma: no cover - abstract
        raise NotImplementedError

    def _map(self, region: Region) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def _read(self, va: int, size: int) -> bytes:  # pragma: no cover - abstract
        raise NotImplementedError

    def _write(self, va: int, data: bytes) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def _get_reg(self, name: str) -> int:  # pragma: no cover - abstract
        raise NotImplementedError

    def _set_reg(self, name: str, value: int) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def _step(self) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def _get_pc(self) -> int:
        return self._get_reg("pc")

    def _set_pc(self, value: int) -> None:
        self._set_reg("pc", value & M32)


# --------------------------------------------------------------------------
# PySh4: the reference interpreter
# --------------------------------------------------------------------------


class _Block:
    """A writable copy of a mapped region, for the interpreter."""

    __slots__ = ("region", "data")

    def __init__(self, region: Region) -> None:
        self.region = region
        self.data = bytearray(region.data)


class PySh4(Backend):
    """Pure-Python SH-4 interpreter; the reference result for M9.4.

    Modelled (encoding-level subset, all standard SH-4 opcodes):

    * data movement: ``mov``/``mov.b``/``mov.w``/``mov.l`` in every addressing
      form used by compiled C (register, ``@-``/``@+``, ``@(disp,Rn)``,
      ``@(R0,Rn)``, ``@(disp,PC)``, ``@(disp,GBR)``, ``mova``, ``movt``);
    * arithmetic/logic: ``add``/``add #imm``/``addc``/``addv``, ``sub*``,
      ``neg(c)``, ``and``/``or``/``xor``/``not``/``tst`` (register and
      ``#imm,R0``/GBR-byte forms), ``shl*``/``shr*``, ``ext*``, ``swap*``,
      ``xtrct``, ``mulu.w``/``muls.w``, ``dmul*``, ``mul.l``, ``cmp/*``,
      ``tas.b``;
    * control flow: ``bra``/``bsr``/``braf``/``bsrf``, ``bt``/``bf``,
      ``bt/s``/``bf/s``, ``jsr``/``jmp``/``rts`` with their delay slots,
      ``dt``, ``nop``;
    * system: ``stc``/``ldc``/``sts``/``lds`` and their ``.l @-``/``@+``
      stack forms, ``clrt``/``sett``/``clrmac``.

    Not modelled, and raised as :class:`IllegalInstruction` rather than
    guessed: FPU (``0xF``), ``div0s``/``div1``, ``trapa``
    (:class:`Trap`), and anything unrecognised.

    ``endian`` selects the byte order of loads, stores and instruction
    fetches: ``"big"`` (the default, used by the older self-tests) or
    ``"little"`` (``Navi.exe`` in the build-A image, M9.21).  The delay-slot
    rule of ``bt/s``/``bf/s`` is the one of ``bra``/``bsr``: the instruction
    after the branch always executes once, and a taken branch lands after it.
    """

    name = "pysh4"
    kind = "interpreter"
    verified = True

    def __init__(self, endian: str = "big") -> None:
        super().__init__()
        if endian not in ("big", "little"):
            raise UsageError(f"endian must be 'big' or 'little', not {endian!r}")
        self.endian = endian
        self._regs = {name: 0 for name in REGISTERS}
        self._blocks: list[_Block] = []
        self._delay: int | None = None

    # -- back end primitives ----------------------------------------------

    def _probe(self) -> Availability:
        return Availability(
            self.name,
            True,
            "",
            "pure-Python SH-4 reference interpreter (subset; no external tools)",
        )

    def _map(self, region: Region) -> None:
        self._blocks.append(_Block(region))
        self._blocks.sort(key=lambda block: block.region.va)

    def _read(self, va: int, size: int) -> bytes:
        block = self._block(va, size, "r")
        offset = va - block.region.va
        return bytes(block.data[offset:offset + size])

    def _write(self, va: int, data: bytes) -> None:
        block = self._block(va, len(data), "w")
        offset = va - block.region.va
        block.data[offset:offset + len(data)] = data

    def _get_reg(self, name: str) -> int:
        return self._regs[name]

    def _set_reg(self, name: str, value: int) -> None:
        self._regs[name] = value & M32

    def close(self) -> None:
        self._delay = None

    # -- memory internals --------------------------------------------------

    def _block(self, va: int, size: int, perm: str) -> _Block:
        end = va + size
        for block in self._blocks:
            region = block.region
            if region.va <= va and end <= region.end:
                if perm not in region.rwx:
                    raise UnmappedAccess(
                        f"{perm}-access at {px(va)} inside {region.name!r} "
                        f"({region.rwx}) is not allowed"
                    )
                return block
        raise UnmappedAccess(
            f"no mapped region covers {px(va)}..{px(end)} "
            f"({', '.join(r.name for r in self._regions) or 'nothing mapped'})"
        )

    def _load_signed(self, va: int, size: int) -> int:
        """Byte/word load into a register: SH-4 sign-extends mov.b and mov.w."""
        return _sx(self._load(va, size), 8 * size) & M32

    def _load(self, va: int, size: int) -> int:
        if va % size:
            raise UnalignedAccess(f"{size}-byte load at unaligned {px(va)}")
        block = self._block(va, size, "r")
        offset = va - block.region.va
        return int.from_bytes(block.data[offset:offset + size], self.endian)

    def _store(self, va: int, size: int, value: int) -> None:
        if va % size:
            raise UnalignedAccess(f"{size}-byte store at unaligned {px(va)}")
        block = self._block(va, size, "w")
        offset = va - block.region.va
        block.data[offset:offset + size] = (value & ((1 << (8 * size)) - 1)).to_bytes(
            size, self.endian
        )

    def _fetch(self) -> int:
        pc = self._regs["pc"]
        block = self._block(pc, 2, "x")
        offset = pc - block.region.va
        return int.from_bytes(block.data[offset:offset + 2], self.endian)

    # -- the interpreter ---------------------------------------------------

    def _set_t(self, condition: bool) -> None:
        if condition:
            self._regs["sr"] |= 1
        else:
            self._regs["sr"] &= ~1

    def _t(self) -> bool:
        return bool(self._regs["sr"] & 1)

    def _step(self) -> None:
        pc = self._regs["pc"]
        insn = self._fetch()
        self._regs["pc"] = (pc + 2) & M32
        delayed = self._delay
        self._delay = None
        self._execute(insn, pc)
        if delayed is not None:
            # A delayed branch: the instruction at pc+2 was the delay slot and
            # has just run, so the branch target wins over pc+4.
            self._regs["pc"] = delayed & M32

    def _execute(self, insn: int, pc: int) -> None:
        regs = self._regs
        n = (insn >> 8) & 0xF
        m = (insn >> 4) & 0xF
        d8 = insn & 0xFF
        top = insn >> 12

        if top == 0xE:                                   # mov #imm,Rn
            regs["r%d" % n] = _sx(d8, 8) & M32
        elif top == 0x7:                                 # add #imm,Rn
            regs["r%d" % n] = (regs["r%d" % n] + _sx(d8, 8)) & M32
        elif top == 0xD:                                 # mov.l @(disp,PC),Rn
            regs["r%d" % n] = self._load(((pc + 4) & ~3) + d8 * 4, 4)
        elif top == 0x9:                                 # mov.w @(disp,PC),Rn
            regs["r%d" % n] = self._load_signed(pc + 4 + d8 * 2, 2)
        elif top == 0xA:                                 # bra
            self._delay = (pc + 4 + _sx(insn & 0xFFF, 12) * 2) & M32
        elif top == 0xB:                                 # bsr
            regs["pr"] = (pc + 4) & M32
            self._delay = (pc + 4 + _sx(insn & 0xFFF, 12) * 2) & M32
        elif top == 0x1:                                 # mov.l Rm,@(disp,Rn)
            self._store((regs["r%d" % n] + (insn & 0xF) * 4) & M32, 4, regs["r%d" % m])
        elif top == 0x5:                                 # mov.l @(disp,Rm),Rn
            regs["r%d" % n] = self._load((regs["r%d" % m] + (insn & 0xF) * 4) & M32, 4)
        elif top == 0x3:
            self._exec_alu(insn, n, m)
        elif top == 0x2:
            self._exec_store(insn, n, m)
        elif top == 0x6:
            self._exec_load(insn, n, m)
        elif top == 0x4:
            self._exec_system(insn, n, m, pc)
        elif top == 0x8:
            self._exec_branch8(insn, n, m, pc)
        elif top == 0xC:
            self._exec_imm(insn, n, d8)
        elif top == 0x0:
            self._exec_misc(insn, n, m, pc)
        elif top == 0xF:
            raise IllegalInstruction(
                f"FPU instruction {px(insn)} at {px(pc)} is not modelled "
                "(no firmware target needs it yet; add it with a check)"
            )
        else:  # pragma: no cover - every 4-bit opcode is covered above
            raise IllegalInstruction(f"unknown opcode {px(insn)} at {px(pc)}")

    # -- groups ------------------------------------------------------------

    def _exec_alu(self, insn: int, n: int, m: int) -> None:
        regs = self._regs
        rn = regs["r%d" % n]
        rm = regs["r%d" % m]
        sub = insn & 0xF

        if sub == 0x0:                                   # cmp/eq
            self._set_t(rn == rm)
        elif sub == 0x2:                                 # cmp/hs
            self._set_t(rn >= rm)
        elif sub == 0x3:                                 # cmp/ge
            self._set_t(_sx(rn, 32) >= _sx(rm, 32))
        elif sub == 0x6:                                 # cmp/hi
            self._set_t(rn > rm)
        elif sub == 0x7:                                 # cmp/gt
            self._set_t(_sx(rn, 32) > _sx(rm, 32))
        elif sub == 0x8:                                 # sub
            regs["r%d" % n] = (rn - rm) & M32
        elif sub == 0xC:                                 # add
            regs["r%d" % n] = (rn + rm) & M32
        elif sub == 0xE:                                 # addc
            total = rn + rm + (1 if self._t() else 0)
            regs["r%d" % n] = total & M32
            self._set_t(total > M32)
        elif sub == 0xA:                                 # subc
            total = rn - rm - (1 if self._t() else 0)
            regs["r%d" % n] = total & M32
            self._set_t(total < 0)
        elif sub == 0xF:                                 # addv
            a, b = _sx(rn, 32), _sx(rm, 32)
            total = a + b
            regs["r%d" % n] = total & M32
            self._set_t(total < -(1 << 31) or total > (1 << 31) - 1)
        elif sub == 0xB:                                 # subv
            a, b = _sx(rn, 32), _sx(rm, 32)
            total = a - b
            regs["r%d" % n] = total & M32
            self._set_t(total < -(1 << 31) or total > (1 << 31) - 1)
        elif sub == 0xD:                                 # dmuls.l
            product = _sx(rn, 32) * _sx(rm, 32) & M64
            regs["mach"] = (product >> 32) & M32
            regs["macl"] = product & M32
        elif sub == 0x5:                                 # dmulu.l
            product = rn * rm & M64
            regs["mach"] = (product >> 32) & M32
            regs["macl"] = product & M32
        else:
            raise IllegalInstruction(
                f"ALU opcode {px(insn)} at {px(regs['pc'] - 2)} is not modelled"
            )

    def _exec_store(self, insn: int, n: int, m: int) -> None:
        regs = self._regs
        rn = regs["r%d" % n]
        rm = regs["r%d" % m]
        sub = insn & 0xF

        if sub == 0x0:                                   # mov.b Rm,@Rn
            self._store(rn, 1, rm)
        elif sub == 0x1:                                 # mov.w Rm,@Rn
            self._store(rn, 2, rm)
        elif sub == 0x2:                                 # mov.l Rm,@Rn
            self._store(rn, 4, rm)
        elif sub == 0x4:                                 # mov.b Rm,@-Rn
            regs["r%d" % n] = (rn - 1) & M32
            self._store((rn - 1) & M32, 1, rm)
        elif sub == 0x5:                                 # mov.w Rm,@-Rn
            regs["r%d" % n] = (rn - 2) & M32
            self._store((rn - 2) & M32, 2, rm)
        elif sub == 0x6:                                 # mov.l Rm,@-Rn
            regs["r%d" % n] = (rn - 4) & M32
            self._store((rn - 4) & M32, 4, rm)
        elif sub == 0x8:                                 # tst
            self._set_t((rn & rm) == 0)
        elif sub == 0x9:                                 # and
            regs["r%d" % n] = rn & rm
        elif sub == 0xA:                                 # xor
            regs["r%d" % n] = rn ^ rm
        elif sub == 0xB:                                 # or
            regs["r%d" % n] = rn | rm
        elif sub == 0xC:                                 # cmp/str
            left = rn.to_bytes(4, "big")
            right = rm.to_bytes(4, "big")
            self._set_t(any(a == b for a, b in zip(left, right)))
        elif sub == 0xD:                                 # xtrct
            combined = ((rm & 0xFFFF) << 16) | ((rn >> 16) & 0xFFFF)
            regs["r%d" % n] = combined & M32
        elif sub == 0xE:                                 # mulu.w
            regs["macl"] = ((rn & 0xFFFF) * (rm & 0xFFFF)) & M32
        elif sub == 0xF:                                 # muls.w
            regs["macl"] = (_sx(rn & 0xFFFF, 16) * _sx(rm & 0xFFFF, 16)) & M32
        else:
            raise IllegalInstruction(
                f"store opcode {px(insn)} at {px(regs['pc'] - 2)} is not modelled"
            )

    def _exec_load(self, insn: int, n: int, m: int) -> None:
        regs = self._regs
        rm = regs["r%d" % m]
        sub = insn & 0xF

        if sub == 0x0:                                   # mov.b @Rm,Rn
            regs["r%d" % n] = self._load_signed(rm, 1)
        elif sub == 0x1:                                 # mov.w @Rm,Rn
            regs["r%d" % n] = self._load_signed(rm, 2)
        elif sub == 0x2:                                 # mov.l @Rm,Rn
            regs["r%d" % n] = self._load(rm, 4)
        elif sub == 0x3:                                 # mov Rm,Rn
            regs["r%d" % n] = rm
        elif sub == 0x4:                                 # mov.b @Rm+,Rn
            regs["r%d" % n] = self._load_signed(rm, 1)
            regs["r%d" % m] = (rm + 1) & M32
        elif sub == 0x5:                                 # mov.w @Rm+,Rn
            regs["r%d" % n] = self._load_signed(rm, 2)
            regs["r%d" % m] = (rm + 2) & M32
        elif sub == 0x6:                                 # mov.l @Rm+,Rn
            regs["r%d" % n] = self._load(rm, 4)
            regs["r%d" % m] = (rm + 4) & M32
        elif sub == 0x7:                                 # not
            regs["r%d" % n] = ~rm & M32
        elif sub == 0x8:                                 # swap.b
            regs["r%d" % n] = ((rm & 0xFF00FF00) | ((rm & 0xFF) << 16)
                               | ((rm >> 16) & 0xFF)) & M32
        elif sub == 0x9:                                 # swap.w
            regs["r%d" % n] = ((rm << 16) | (rm >> 16)) & M32
        elif sub == 0xA:                                 # negc
            total = 0 - rm - (1 if self._t() else 0)
            regs["r%d" % n] = total & M32
            self._set_t(total < 0)
        elif sub == 0xB:                                 # neg
            regs["r%d" % n] = (-rm) & M32
        elif sub == 0xC:                                 # extu.b
            regs["r%d" % n] = rm & 0xFF
        elif sub == 0xD:                                 # extu.w
            regs["r%d" % n] = rm & 0xFFFF
        elif sub == 0xE:                                 # exts.b
            regs["r%d" % n] = _sx(rm, 8) & M32
        elif sub == 0xF:                                 # exts.w
            regs["r%d" % n] = _sx(rm, 16) & M32
        else:  # pragma: no cover - sub is a nibble and all 16 are covered
            raise IllegalInstruction(f"load opcode {px(insn)} is not modelled")

    def _exec_system(self, insn: int, n: int, m: int, pc: int) -> None:
        # Every ``0x4`` form names its register in the n field; the m field is
        # opcode space here (the same layout the assembler prints as ``Rn``).
        regs = self._regs
        rn = regs["r%d" % n]
        low = insn & 0xFF

        if low == 0x00:                                  # shll
            self._set_t(bool(rn & 0x80000000))
            regs["r%d" % n] = (rn << 1) & M32
        elif low == 0x01:                                # shlr
            self._set_t(bool(rn & 1))
            regs["r%d" % n] = rn >> 1
        elif low == 0x08:                                # shll2
            regs["r%d" % n] = (rn << 2) & M32
        elif low == 0x09:                                # shlr2
            regs["r%d" % n] = rn >> 2
        elif low == 0x18:                                # shll8
            regs["r%d" % n] = (rn << 8) & M32
        elif low == 0x19:                                # shlr8
            regs["r%d" % n] = rn >> 8
        elif low == 0x20:                                # shal
            self._set_t(bool(rn & 0x80000000))
            regs["r%d" % n] = (rn << 1) & M32
        elif low == 0x21:                                # shar
            self._set_t(bool(rn & 1))
            regs["r%d" % n] = ((rn >> 1) | (rn & 0x80000000)) & M32
        elif low == 0x28:                                # shll16
            regs["r%d" % n] = (rn << 16) & M32
        elif low == 0x29:                                # shlr16
            regs["r%d" % n] = rn >> 16
        elif low == 0x10:                                # dt
            value = (rn - 1) & M32
            regs["r%d" % n] = value
            self._set_t(value == 0)
        elif low == 0x11:                                # cmp/pz
            self._set_t(_sx(rn, 32) >= 0)
        elif low == 0x15:                                # cmp/pl
            self._set_t(_sx(rn, 32) > 0)
        elif low == 0x0B:                                # jsr @Rn
            regs["pr"] = (pc + 4) & M32
            self._delay = rn
        elif low == 0x2B:                                # jmp @Rn
            self._delay = rn
        elif low == 0x0E:                                # ldc Rn,SR
            regs["sr"] = rn
        elif low == 0x1E:                                # ldc Rn,GBR
            regs["gbr"] = rn
        elif low == 0x2E:                                # ldc Rn,VBR
            regs["vbr"] = rn
        elif low == 0x0A:                                # lds Rn,MACH
            regs["mach"] = rn
        elif low == 0x1A:                                # lds Rn,MACL
            regs["macl"] = rn
        elif low == 0x2A:                                # lds Rn,PR
            regs["pr"] = rn
        elif low == 0x02:                                # sts.l MACH,@-Rn
            regs["r%d" % n] = (rn - 4) & M32
            self._store((rn - 4) & M32, 4, regs["mach"])
        elif low == 0x12:                                # sts.l MACL,@-Rn
            regs["r%d" % n] = (rn - 4) & M32
            self._store((rn - 4) & M32, 4, regs["macl"])
        elif low == 0x22:                                # sts.l PR,@-Rn
            regs["r%d" % n] = (rn - 4) & M32
            self._store((rn - 4) & M32, 4, regs["pr"])
        elif low == 0x03:                                # stc.l SR,@-Rn
            regs["r%d" % n] = (rn - 4) & M32
            self._store((rn - 4) & M32, 4, regs["sr"])
        elif low == 0x13:                                # stc.l GBR,@-Rn
            regs["r%d" % n] = (rn - 4) & M32
            self._store((rn - 4) & M32, 4, regs["gbr"])
        elif low == 0x23:                                # stc.l VBR,@-Rn
            regs["r%d" % n] = (rn - 4) & M32
            self._store((rn - 4) & M32, 4, regs["vbr"])
        # ``lds.l @Rn+,...``/``ldc.l @Rn+,...`` keep the post-increment
        # register in the n field (0100 nnnn xxxx 011x), not in the m field
        # that the other system forms use as part of the opcode.
        elif low == 0x06:                                # lds.l @Rn+,MACH
            regs["mach"] = self._load(rn, 4)
            regs["r%d" % n] = (rn + 4) & M32
        elif low == 0x16:                                # lds.l @Rn+,MACL
            regs["macl"] = self._load(rn, 4)
            regs["r%d" % n] = (rn + 4) & M32
        elif low == 0x26:                                # lds.l @Rn+,PR
            regs["pr"] = self._load(rn, 4)
            regs["r%d" % n] = (rn + 4) & M32
        elif low == 0x07:                                # ldc.l @Rn+,SR
            regs["sr"] = self._load(rn, 4)
            regs["r%d" % n] = (rn + 4) & M32
        elif low == 0x17:                                # ldc.l @Rn+,GBR
            regs["gbr"] = self._load(rn, 4)
            regs["r%d" % n] = (rn + 4) & M32
        elif low == 0x27:                                # ldc.l @Rn+,VBR
            regs["vbr"] = self._load(rn, 4)
            regs["r%d" % n] = (rn + 4) & M32
        elif low == 0x1B:                                # tas.b @Rn
            value = self._load(rn, 1)
            self._set_t(value == 0)
            self._store(rn, 1, value | 0x80)
        elif insn & 0xF in (0x0C, 0x0D):                 # shad / shld Rm,Rn
            # Dynamic shifts: the source register is in the m field, so the
            # low byte carries it and the exact-match arms above cannot apply.
            # Rm >= 0 shifts left by Rm & 31; Rm < 0 shifts right by
            # (~Rm & 31) + 1, and Rm & 31 == 0 (Rm = -32) fills with the sign
            # (shad) or with zero (shld).  zlib's inflate uses 0x469d (shld).
            amount = regs["r%d" % m] & M32
            arithmetic = (insn & 0xF) == 0x0C
            if not amount & 0x80000000:
                result = (rn << (amount & 0x1F)) & M32
            elif amount & 0x1F == 0:
                result = M32 if (arithmetic and rn & 0x80000000) else 0
            elif arithmetic:
                result = (_sx(rn, 32) >> (((~amount) & 0x1F) + 1)) & M32
            else:
                result = rn >> (((~amount) & 0x1F) + 1)
            regs["r%d" % n] = result
        else:
            raise IllegalInstruction(
                f"system opcode {px(insn)} at {px(pc)} is not modelled "
                "(div0s/div1/bt-s/bf-s and the like fail loudly on purpose)"
            )

    def _exec_branch8(self, insn: int, n: int, m: int, pc: int) -> None:
        regs = self._regs
        sub = (insn >> 8) & 0xF
        disp = _sx(insn & 0xFF, 8)
        target = (pc + 4 + disp * 2) & M32

        if sub == 0x0:                                   # mov.b R0,@(disp,Rn)
            self._store((regs["r%d" % n] + (insn & 0xF)) & M32, 1, regs["r0"])
        elif sub == 0x1:                                 # mov.w R0,@(disp,Rn)
            self._store((regs["r%d" % n] + (insn & 0xF) * 2) & M32, 2, regs["r0"])
        elif sub == 0x4:                                 # mov.b @(disp,Rm),R0
            regs["r0"] = self._load_signed((regs["r%d" % m] + (insn & 0xF)) & M32, 1)
        elif sub == 0x5:                                 # mov.w @(disp,Rm),R0
            regs["r0"] = self._load_signed((regs["r%d" % m] + (insn & 0xF) * 2) & M32, 2)
        elif sub == 0x8:                                 # cmp/eq #imm,R0
            self._set_t((regs["r0"] & M32) == (_sx(insn & 0xFF, 8) & M32))
        elif sub == 0x9:                                 # bt
            if self._t():
                regs["pc"] = target
        elif sub == 0xB:                                 # bf
            if not self._t():
                regs["pc"] = target
        elif sub == 0xD:                                 # bt/s
            if self._t():
                self._delay = target
        elif sub == 0xF:                                 # bf/s
            if not self._t():
                self._delay = target
        else:
            raise IllegalInstruction(f"opcode {px(insn)} at {px(pc)} is not modelled")

    def _exec_imm(self, insn: int, n: int, d8: int) -> None:
        regs = self._regs
        top = (insn >> 8) & 0xF
        gbr = regs["gbr"]

        if top == 0x0:                                   # mov.b R0,@(disp,GBR)
            self._store((gbr + d8) & M32, 1, regs["r0"])
        elif top == 0x1:                                 # mov.w R0,@(disp,GBR)
            self._store((gbr + d8 * 2) & M32, 2, regs["r0"])
        elif top == 0x2:                                 # mov.l R0,@(disp,GBR)
            self._store((gbr + d8 * 4) & M32, 4, regs["r0"])
        elif top == 0x3:                                 # trapa #imm
            raise Trap(
                f"trapa #{d8} at {px(regs['pc'] - 2)}: WinCE system call; "
                "register a host stub with on_exec() instead of emulating it"
            )
        elif top == 0x4:                                 # mov.b @(disp,GBR),R0
            regs["r0"] = self._load_signed((gbr + d8) & M32, 1)
        elif top == 0x5:                                 # mov.w @(disp,GBR),R0
            regs["r0"] = self._load_signed((gbr + d8 * 2) & M32, 2)
        elif top == 0x6:                                 # mov.l @(disp,GBR),R0
            regs["r0"] = self._load((gbr + d8 * 4) & M32, 4)
        elif top == 0x7:                                 # mova @(disp,PC),R0
            regs["r0"] = ((regs["pc"] - 2 + 4) & ~3) + d8 * 4
        elif top == 0x8:                                 # tst #imm,R0
            self._set_t((regs["r0"] & d8) == 0)
        elif top == 0x9:                                 # and #imm,R0
            regs["r0"] &= d8
        elif top == 0xA:                                 # xor #imm,R0
            regs["r0"] ^= d8
        elif top == 0xB:                                 # or #imm,R0
            regs["r0"] |= d8
        elif top == 0xC:                                 # tst.b #imm,@(R0,GBR)
            self._set_t((self._load((gbr + regs["r0"]) & M32, 1) & d8) == 0)
        elif top == 0xD:                                 # and.b #imm,@(R0,GBR)
            address = (gbr + regs["r0"]) & M32
            self._store(address, 1, self._load(address, 1) & d8)
        elif top == 0xE:                                 # xor.b #imm,@(R0,GBR)
            address = (gbr + regs["r0"]) & M32
            self._store(address, 1, self._load(address, 1) ^ d8)
        elif top == 0xF:                                 # or.b #imm,@(R0,GBR)
            address = (gbr + regs["r0"]) & M32
            self._store(address, 1, self._load(address, 1) | d8)
        else:  # pragma: no cover - top is a nibble
            raise IllegalInstruction(f"opcode {px(insn)} is not modelled")

    def _exec_misc(self, insn: int, n: int, m: int, pc: int) -> None:
        regs = self._regs
        pattern = insn & 0xF0FF
        rn = regs["r%d" % n]
        rm = regs["r%d" % m]

        if pattern == 0x0009:                            # nop
            return
        if pattern == 0x000B:                            # rts
            self._delay = regs["pr"]
            return
        if pattern == 0x0002:                            # stc SR,Rn
            regs["r%d" % n] = regs["sr"]
        elif pattern == 0x0012:                          # stc GBR,Rn
            regs["r%d" % n] = regs["gbr"]
        elif pattern == 0x0022:                          # stc VBR,Rn
            regs["r%d" % n] = regs["vbr"]
        elif pattern == 0x000A:                          # sts MACH,Rn
            regs["r%d" % n] = regs["mach"]
        elif pattern == 0x001A:                          # sts MACL,Rn
            regs["r%d" % n] = regs["macl"]
        elif pattern == 0x002A:                          # sts PR,Rn
            regs["r%d" % n] = regs["pr"]
        elif pattern == 0x0029:                          # movt Rn
            regs["r%d" % n] = 1 if self._t() else 0
        elif pattern == 0x0008:                          # clrt
            self._set_t(False)
        elif pattern == 0x0018:                          # sett
            self._set_t(True)
        elif pattern == 0x0028:                          # clrmac
            regs["mach"] = 0
            regs["macl"] = 0
        elif pattern == 0x0019:                          # div0u
            self._set_t(False)
        elif pattern == 0x0007:                          # mul.l Rm,Rn
            regs["macl"] = (rn * rm) & M32
        elif pattern == 0x0003:                          # bsrf Rn (0000 nnnn 0000 0011)
            regs["pr"] = (pc + 4) & M32
            self._delay = (pc + 4 + rn) & M32
        elif pattern == 0x0023:                          # braf Rn (0000 nnnn 0010 0011)
            # The register is the n field, not m: the m nibble is opcode space
            # here.  Using m sent zlib's inflate jump table to pc+4+Rm (M9.11).
            self._delay = (pc + 4 + rn) & M32
        elif pattern in (0x0083, 0x0093, 0x00A3, 0x00B3):
            # pref @Rn, ocbi/ocbp/ocbwb @Rn: cache hints with no architectural
            # effect, so a functional emulator ignores them on purpose.
            return
        elif (insn & 0xF) == 0x4:                        # mov.b Rm,@(R0,Rn)
            self._store((regs["r0"] + rn) & M32, 1, rm)
        elif (insn & 0xF) == 0x5:                        # mov.w Rm,@(R0,Rn)
            self._store((regs["r0"] + rn) & M32, 2, rm)
        elif (insn & 0xF) == 0x6:                        # mov.l Rm,@(R0,Rn)
            self._store((regs["r0"] + rn) & M32, 4, rm)
        elif (insn & 0xF) == 0xC:                        # mov.b @(R0,Rm),Rn
            regs["r%d" % n] = self._load_signed((regs["r0"] + rm) & M32, 1)
        elif (insn & 0xF) == 0xD:                        # mov.w @(R0,Rm),Rn
            regs["r%d" % n] = self._load_signed((regs["r0"] + rm) & M32, 2)
        elif (insn & 0xF) == 0xE:                        # mov.l @(R0,Rm),Rn
            regs["r%d" % n] = self._load((regs["r0"] + rm) & M32, 4)
        else:
            raise IllegalInstruction(
                f"opcode {px(insn)} at {px(pc)} is not modelled "
                "(the PySh4 subset fails loudly instead of guessing)"
            )


# --------------------------------------------------------------------------
# GhidraBackend
# --------------------------------------------------------------------------

GHIDRA_HINT = (
    "install Ghidra 12.2+ (with a supported JDK) and pyghidra, then export "
    "GHIDRA_INSTALL_DIR or pass program=<path>; see docs/research/l3-ghidra.md"
)


class GhidraBackend(Backend):
    """``pyghidra`` + ``EmulatorHelper`` adapter, imported lazily.

    Nothing is imported at module load: the first access starts Ghidra.  The
    adapter is written against the documented API (``writeMemory``,
    ``readMemory``, ``writeRegister``, ``readRegister``, ``step``,
    ``getPCRegisterName``) and against ``ghidra.program.database.ProgramBuilder``
    for the synthetic program.  **It has never been executed on this machine**
    (no Ghidra), so a failure is reported as ``BLOCKED`` with Ghidra's own
    message rather than being smoothed over.
    """

    name = "ghidra"
    kind = "pcode-emulator"
    verified = False

    def __init__(self, program: str | os.PathLike | None = None,
                 project: str | os.PathLike | None = None,
                 analyze: bool = False) -> None:
        super().__init__()
        self.program_path = str(program) if program else None
        self.project_path = str(project) if project else None
        self.analyze = analyze
        self._ready = False
        self._program = None
        self._context = None
        self._emulator = None
        self._pc_name = "pc"
        self._step_monitor = None
        self._pending: list[Region] = []

    # -- laziness ----------------------------------------------------------

    def _probe(self) -> Availability:
        try:
            import pyghidra  # noqa: F401
        except Exception as exc:  # ImportError, or a broken JDK/JPype install
            return Availability(
                self.name, False, "MISSING_GHIDRA",
                f"pyghidra is not importable ({type(exc).__name__}: {exc}); {GHIDRA_HINT}",
            )
        return Availability(
            self.name, True, "",
            "pyghidra imports; the EmulatorHelper path is written to the "
            "documented API but has never been executed here",
        )

    def _ensure(self):
        if self._ready:
            return
        try:
            import pyghidra
        except Exception as exc:
            raise MissingGhidra(
                f"pyghidra is not importable ({type(exc).__name__}: {exc}); {GHIDRA_HINT}"
            ) from exc
        try:
            pyghidra.start()
        except Exception as exc:  # already started raises in some versions
            if "already" not in str(exc).lower():
                raise Blocked(f"pyghidra.start() failed: {type(exc).__name__}: {exc}") from exc
        try:
            from ghidra.pcode.emulate import EmulatorHelper  # type: ignore

            if self.program_path:
                self._context = pyghidra.open_program(
                    self.program_path,
                    project_location=self.project_path,
                    analyze=self.analyze,
                )
                self._program = self._context.__enter__()
            else:
                self._program = self._synthetic_program()
            self._emulator = EmulatorHelper(self._program)
            self._pc_name = self._emulator.getPCRegisterName() or "pc"
            self._step_monitor = self._make_step_monitor(EmulatorHelper)
            for region in self._pending:
                self._emulator.writeMemory(region.va, region.data)
            self._pending.clear()
        except EngineError:
            raise
        except Exception as exc:
            raise Blocked(
                f"Ghidra EmulatorHelper setup failed: {type(exc).__name__}: {exc}"
            ) from exc

        if self._synthetic_needed():
            self._populate_synthetic()
        self._ready = True

    def _synthetic_program(self):
        """Create an empty SH-4 program for mapped-on-demand synthetic code."""
        from ghidra.program.database import ProgramBuilder  # type: ignore

        self._builder = ProgramBuilder("l3-synthetic", ISA, None)
        self._synthetic = True
        return self._builder.getProgram()

    def _synthetic_needed(self) -> bool:
        return bool(getattr(self, "_synthetic", False))

    def _populate_synthetic(self) -> None:
        """Create one memory block per mapped region and write its bytes."""
        for region in self._regions:
            try:
                self._builder.createMemory(
                    region.name, "0x%08x" % region.va, region.size
                )
            except Exception as exc:
                raise Blocked(
                    f"ProgramBuilder.createMemory({region.name!r}, "
                    f"{px(region.va)}, {region.size}) failed: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
        for region in self._regions:
            self._builder.setBytes("0x%08x" % region.va, list(region.data))

    def _make_step_monitor(self, EmulatorHelper):
        """A one-instruction ``StepMonitor`` for ``EmulatorHelper.step``."""
        try:
            from jpype import JImplements, JOverride  # type: ignore

            @JImplements(EmulatorHelper.StepMonitor)
            class _OneStep:
                @JOverride
                def step(self, emulator, address, byte_count):  # noqa: ANN001
                    return False

            return _OneStep()
        except Exception as exc:
            raise Blocked(
                "cannot build an EmulatorHelper.StepMonitor "
                f"({type(exc).__name__}: {exc}); the Ghidra adapter needs the "
                "pyghidra/JPype callback bridge"
            ) from exc

    # -- primitives --------------------------------------------------------

    def _map(self, region: Region) -> None:
        if self._ready:
            try:
                self._emulator.writeMemory(region.va, region.data)
            except Exception as exc:
                raise UnmappedAccess(
                    f"Ghidra cannot write {region.name!r} at {px(region.va)}: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
        else:
            self._pending.append(region)

    def _read(self, va: int, size: int) -> bytes:
        self._ensure()
        try:
            payload = self._emulator.readMemory(va, size)
        except Exception as exc:
            raise UnmappedAccess(
                f"Ghidra read of {size} bytes at {px(va)} failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        return bytes(bytearray(payload))

    def _write(self, va: int, data: bytes) -> None:
        self._ensure()
        try:
            self._emulator.writeMemory(va, data)
        except Exception as exc:
            raise UnmappedAccess(
                f"Ghidra write of {len(data)} bytes at {px(va)} failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    def _get_reg(self, name: str) -> int:
        self._ensure()
        if name == "pc":
            name = self._pc_name
        try:
            return int(self._emulator.readRegister(name)) & M32
        except Exception as exc:
            raise Blocked(
                f"Ghidra readRegister({name!r}) failed: {type(exc).__name__}: {exc}"
            ) from exc

    def _set_reg(self, name: str, value: int) -> None:
        self._ensure()
        if name == "pc":
            name = self._pc_name
        try:
            self._emulator.writeRegister(name, value & M32)
        except Exception as exc:
            raise Blocked(
                f"Ghidra writeRegister({name!r}) failed: {type(exc).__name__}: {exc}"
            ) from exc

    def _step(self) -> None:
        self._ensure()
        try:
            self._emulator.step(self._step_monitor)
        except Exception as exc:
            raise Blocked(
                f"Ghidra single step failed at {px(self._get_pc())}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        error = None
        try:
            error = self._emulator.getLastError()
        except Exception:  # pragma: no cover - older API
            error = None
        if error:
            raise Blocked(f"Ghidra emulator error at {px(self._get_pc())}: {error}")

    def close(self) -> None:
        if self._context is not None:
            try:
                self._context.__exit__(None, None, None)
            except Exception:  # pragma: no cover - best effort
                pass
            self._context = None
        self._emulator = None
        self._ready = False


# --------------------------------------------------------------------------
# QemuBackend: `-M none` + gdbstub
# --------------------------------------------------------------------------

#: gdb stub register numbers for the SH-4 core (``gdb-xml/sh4-core.xml``:
#: r0-r15, pc, pr, gbr, vbr, mach, macl, sr, fpul, fpscr).  Kept as data so a
#: real run can correct it without touching the protocol code.
QEMU_REG_NUMBERS: dict[str, int] = {
    **{"r%d" % index: index for index in range(16)},
    "pc": 16,
    "pr": 17,
    "gbr": 18,
    "vbr": 19,
    "mach": 20,
    "macl": 21,
    "sr": 22,
    "fpul": 23,
    "fpscr": 24,
}


class _Rsp:
    """Minimal gdb remote-serial-protocol client (the subset this engine needs)."""

    def __init__(self, host: str, port: int, timeout: float = 10.0) -> None:
        self._socket = socket.create_connection((host, port), timeout=timeout)
        self._socket.settimeout(timeout)
        self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def close(self) -> None:
        try:
            self._socket.close()
        except OSError:  # pragma: no cover - best effort
            pass

    def _read_byte(self) -> bytes:
        chunk = self._socket.recv(1)
        if not chunk:
            raise ConnectionError("gdbstub closed the connection")
        return chunk

    def _read_packet(self) -> bytes:
        while True:
            byte = self._read_byte()
            if byte == b"$":
                break
            if byte in (b"+", b"-"):
                continue
            raise ConnectionError(f"unexpected gdbstub byte {byte!r}")
        body = bytearray()
        while True:
            byte = self._read_byte()
            if byte == b"#":
                break
            if byte == b"}":
                escaped = self._read_byte()
                body.append(escaped[0] ^ 0x20)
                continue
            body.extend(byte)
        checksum = self._socket.recv(2)
        if len(checksum) != 2:
            raise ConnectionError("truncated gdbstub checksum")
        expected = int(checksum.decode("latin-1"), 16) & 0xFF
        if sum(body) & 0xFF != expected:
            self._socket.sendall(b"-")
            raise ConnectionError("gdbstub checksum mismatch")
        self._socket.sendall(b"+")
        return bytes(body)

    def command(self, payload: str) -> bytes:
        data = payload.encode("latin-1")
        frame = b"$" + data + b"#" + ("%02x" % (sum(data) & 0xFF)).encode("latin-1")
        self._socket.sendall(frame)
        while True:
            reply = self._read_packet()
            if reply != b"":
                return reply

    def interrupt(self) -> None:
        try:
            self._socket.sendall(b"\x03")
        except OSError:  # pragma: no cover - best effort on shutdown
            pass


class QemuBackend(Backend):
    """``qemu-system-sh4 -M none`` driven through the gdbstub.

    The CPU is QEMU's stock SH-4A (``sh7785``), the same one EXP-2026-11-05-37
    used to boot the kernel.  With the MMU off, gdb addresses are physical, so
    a P1 VA (``0x80000000``-``0xbfffffff``) is masked to ``va & 0x1fffffff``.

    Missing binary -> ``MISSING_QEMU``.  A binary that will not start, or a
    stub that does not answer, -> ``BLOCKED`` with QEMU's stderr.  The protocol
    code below is complete for the operations the engine performs, but it has
    never run against a real ``qemu-system-sh4`` on this machine.
    """

    name = "qemu"
    kind = "full-cpu"
    verified = False

    def __init__(self, qemu: str | None = None, cpu: str = "sh7785",
                 memory: str = "256M", host: str = "127.0.0.1",
                 timeout: float = 10.0) -> None:
        super().__init__()
        self.qemu = qemu
        self.cpu = cpu
        self.memory = memory
        self.host = host
        self.timeout = timeout
        self._process: subprocess.Popen | None = None
        self._rsp: _Rsp | None = None
        self._port = 0
        self._stderr_file = None

    # -- process / protocol ------------------------------------------------

    def _probe(self) -> Availability:
        binary = self._binary()
        if not binary:
            return Availability(
                self.name, False, "MISSING_QEMU",
                "qemu-system-sh4 is not on PATH "
                "(Debian/Ubuntu: apt install qemu-system-misc)",
            )
        return Availability(
            self.name, True, "",
            f"{binary} found; the gdbstub adapter is written but has never "
            "been executed against a live stub here",
        )

    def _binary(self) -> str | None:
        candidate = self.qemu or os.environ.get("QEMU_SYSTEM_SH4")
        if candidate:
            return candidate if shutil.which(candidate) or Path(candidate).is_file() else None
        return shutil.which("qemu-system-sh4")

    @staticmethod
    def _free_port(host: str) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, 0))
            return sock.getsockname()[1]

    def _ensure(self) -> None:
        if self._rsp is not None:
            return
        binary = self._binary()
        if not binary:
            raise MissingQemu(
                "qemu-system-sh4 is not on PATH and no --qemu was given "
                "(Debian/Ubuntu: apt install qemu-system-misc)"
            )
        self._port = self._free_port(self.host)
        command = [
            binary, "-M", "none", "-cpu", self.cpu, "-m", self.memory,
            "-nographic", "-serial", "none", "-monitor", "none",
            "-S", "-gdb", f"tcp:{self.host}:{self._port}",
        ]
        self._stderr_file = tempfile.TemporaryFile()
        try:
            self._process = subprocess.Popen(
                command, stdout=subprocess.DEVNULL, stderr=self._stderr_file
            )
        except OSError as exc:
            raise MissingQemu(f"cannot execute {binary}: {exc}") from exc

        deadline = time.monotonic() + self.timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise Blocked(
                    f"qemu-system-sh4 exited ({self._process.returncode}): "
                    f"{self._stderr_text()}"
                )
            try:
                self._rsp = _Rsp(self.host, self._port, timeout=self.timeout)
                break
            except OSError as exc:
                last_error = exc
                time.sleep(0.05)
        if self._rsp is None:
            self._terminate()
            raise Blocked(
                f"no gdbstub on {self.host}:{self._port} within "
                f"{self.timeout:.0f}s ({last_error}); {self._stderr_text()}"
            )
        try:
            self._rsp.command("qSupported:multiprocess+")
        except (ConnectionError, OSError) as exc:
            self._terminate()
            raise Blocked(f"gdbstub handshake failed: {exc}") from exc

    def _stderr_text(self) -> str:
        if self._stderr_file is None:
            return "(no stderr)"
        try:
            self._stderr_file.seek(0)
            text = self._stderr_file.read().decode("utf-8", "replace").strip()
        except OSError:  # pragma: no cover - best effort
            return "(stderr unreadable)"
        return text.splitlines()[-1] if text else "(no stderr)"

    def _terminate(self) -> None:
        if self._rsp is not None:
            self._rsp.interrupt()
            self._rsp.close()
            self._rsp = None
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover
                self._process.kill()
                self._process.wait()
            self._process = None
        if self._stderr_file is not None:
            self._stderr_file.close()
            self._stderr_file = None

    def close(self) -> None:
        self._terminate()

    # -- address translation ----------------------------------------------

    @staticmethod
    def physical(va: int) -> int:
        """P1/P2 VA -> physical, MMU off (``-M none`` has no MMU mapped)."""
        if 0x80000000 <= (va & M32) <= 0xBFFFFFFF:
            return va & 0x1FFFFFFF
        if 0xC0000000 <= (va & M32) <= 0xDFFFFFFF:
            return va & 0x1FFFFFFF
        return va & M32

    def _reply(self, payload: str, what: str) -> bytes:
        self._ensure()
        try:
            reply = self._rsp.command(payload)
        except (ConnectionError, OSError) as exc:
            raise Blocked(f"gdbstub {what} failed: {exc}") from exc
        if reply.startswith(b"E"):
            raise Blocked(f"gdbstub {what} returned {reply.decode('latin-1')!r}")
        return reply

    # -- primitives --------------------------------------------------------

    def _map(self, region: Region) -> None:
        self._write_phys(self.physical(region.va), region.data)

    def _read(self, va: int, size: int) -> bytes:
        address = self.physical(va)
        reply = self._reply(f"m{address:x},{size:x}", f"read of {size} bytes at {px(va)}")
        if len(reply) != size * 2:
            raise Blocked(
                f"gdbstub returned {len(reply) // 2} bytes for a {size}-byte "
                f"read at {px(va)}, expected {size}"
            )
        return bytes.fromhex(reply.decode("latin-1"))

    def _write_phys(self, address: int, data: bytes) -> None:
        if not data:
            return
        self._reply(
            f"M{address:x},{len(data):x}:{data.hex()}",
            f"write of {len(data)} bytes at {px(address)}",
        )

    def _write(self, va: int, data: bytes) -> None:
        self._write_phys(self.physical(va), data)

    def _get_reg(self, name: str) -> int:
        number = QEMU_REG_NUMBERS[name]
        reply = self._reply(f"p{number:x}", f"read of {name}")
        try:
            return int(reply.decode("latin-1"), 16) & M32
        except ValueError as exc:
            raise Blocked(f"gdbstub sent a non-hex value for {name}: {reply!r}") from exc

    def _set_reg(self, name: str, value: int) -> None:
        number = QEMU_REG_NUMBERS[name]
        self._reply(f"P{number:x}={value & M32:08x}", f"write of {name}")

    def _step(self) -> None:
        reply = self._reply("s", "single step")
        status = reply[:1]
        if status not in (b"T", b"S"):
            raise Blocked(
                f"gdbstub single step at {px(self._get_pc())} reported "
                f"{reply.decode('latin-1')!r} instead of a stop reply"
            )


# --------------------------------------------------------------------------
# Probes and the synthetic snippet (the M9.4 proof)
# --------------------------------------------------------------------------

BACKENDS: dict[str, type[Backend]] = {
    "pysh4": PySh4,
    "ghidra": GhidraBackend,
    "qemu": QemuBackend,
}


def probe_all(names: Iterable[str] | None = None) -> list[Availability]:
    """Probe back ends without running anything.  Never raises."""
    wanted = list(names) if names else list(BACKENDS)
    results = []
    for name in wanted:
        if name not in BACKENDS:
            raise UsageError(f"unknown engine {name!r} (known: {', '.join(BACKENDS)})")
        backend = BACKENDS[name]()
        try:
            results.append(backend.probe())
        finally:
            backend.close()
    return results


# Synthetic snippet (SH-4, big-endian).  One function, 32 bytes, code at
# 0x8c100000; the stub at 0x8c100100 is host code, never fetched.
#
#   off  word    instruction              effect
#   00   4f22    sts.l pr,@-r15           save the caller's return address
#   02   e000    mov   #0,r0              acc = 0
#   04   d705    mov.l @(5,pc),r7         r7 = stub VA (literal at off 28)
#   06   304c    add   r4,r0              loop: acc += r4
#   08   4410    dt    r4                 r4--, T = (r4 == 0)
#   0a   8bfc    bf    off 06             keep looping while r4 != 0
#   0c   0009    nop
#   0e   6403    mov   r0,r4              arg0 = acc
#   10   470b    jsr   @r7                call the write stub
#   12   0009    nop                       (delay slot)
#   14   4f26    lds.l @r15+,pr           restore the caller's return address
#   16   000b    rts                      return to it
#   18   0009    nop                       (delay slot)
#   1a   0009    nop                       (padding to the 4-byte literal)
#   1c   8c100100 .long stub VA
PROGRAM_VA = 0x8C100000
STUB_VA = 0x8C100100
STACK_VA = 0x8C1FF000
STACK_SIZE = 0x1000
STACK_TOP = 0x8C200000
DEST_VA = 0x8C201000
DEST_SIZE = 0x1000
ITERATIONS = 5
STUB_RETURN = 0x5A5A

#: Everything the snippet must produce, independent of the engine.
EXPECTED = {
    "r0": STUB_RETURN,
    "r4": 0x0F,                    # 5 + 4 + 3 + 2 + 1
    "r5": DEST_VA,
    "r7": STUB_VA,
    "r15": STACK_TOP,              # the stack was restored
    "pc": RETURN_VA,
    "pr": RETURN_VA,
    "t": 1,                        # dt left T set after the last decrement
}


def synthetic_program() -> bytes:
    """The 32-byte SH-4 snippet; see the table above for the encodings."""
    words = [
        0x4F22,  # sts.l pr,@-r15
        0xE000,  # mov #0,r0
        0xD705,  # mov.l @(5,pc),r7
        0x304C,  # add r4,r0
        0x4410,  # dt r4
        0x8BFC,  # bf 6
        0x0009,  # nop
        0x6403,  # mov r0,r4
        0x470B,  # jsr @r7
        0x0009,  # nop
        0x4F26,  # lds.l @r15+,pr
        0x000B,  # rts
        0x0009,  # nop
        0x0009,  # padding
    ]
    return b"".join(struct.pack(">H", word) for word in words) + struct.pack(">I", STUB_VA)


def write_stub(engine: Backend, va: int) -> StubReturn:
    """Host stub: store ``r4`` at the pointer in ``r5``, return 0x5a5a.

    Reads its arguments and writes through the engine, so one Python function
    exercises ``get_regs``, ``write_mem`` and ``read_mem`` on every back end.
    """
    regs = engine.get_regs()
    value = regs["r4"]
    dest = regs["r5"]
    payload = struct.pack(">I", value)
    engine.write_mem(dest, payload)
    if engine.read_mem(dest, 4) != payload:
        raise EngineError(
            f"engine {engine.name}: write_mem at {px(dest)} did not read back"
        )
    return StubReturn(STUB_RETURN)


def build_world(engine: Backend) -> None:
    """Map the snippet's regions and register the stub, identically everywhere."""
    engine.map("code", PROGRAM_VA, synthetic_program(), "rx")
    engine.map("stack", STACK_VA, STACK_SIZE, "rw")
    engine.map("dest", DEST_VA, DEST_SIZE, "rw")
    engine.on_exec(STUB_VA, write_stub)
    # Zero every register first: PySh4 starts at zero, but a Ghidra program or
    # a freshly reset CPU does not, and a parity check needs one starting point.
    engine.set_regs({name: 0 for name in REGISTERS})
    engine.set_regs(r15=STACK_TOP)


def run_snippet(engine: Backend) -> dict:
    """Run the snippet on *engine* and return a comparable snapshot."""
    build_world(engine)
    r0 = engine.call(PROGRAM_VA, [ITERATIONS, DEST_VA])
    run = engine.last_run
    return {
        "engine": engine.name,
        "regs": engine.get_regs(),
        "r0": r0,
        "dest": engine.read_mem(DEST_VA, 4).hex(),
        "stack_slot": engine.read_mem(STACK_TOP - 4, 4).hex(),
        "insns": run.insns if run else -1,
        "reason": run.reason if run else "none",
        "stubs": [
            {"va": px(item["va"]), "value": px(item["value"])}
            for item in (run.stubs if run else [])
        ],
    }


def snapshot_core(snapshot: Mapping) -> dict:
    """The engine-independent part of a snapshot: everything except its label.

    The back-end name is metadata, not a result, so parity compares this dict.
    Without it a correct Ghidra or QEMU run would look different from the
    ``PySh4`` reference for the only reason that it *is* that back end.
    """
    return {key: value for key, value in snapshot.items() if key != "engine"}


# --------------------------------------------------------------------------
# Self-test: the M9.4 acceptance proof
# --------------------------------------------------------------------------

CHECKS: list[tuple[str, Callable]] = []
SKIPS: list[str] = []


def check(name: str):
    def register(func):
        CHECKS.append((name, func))
        return func

    return register


def _expect_equal(actual, expected, what: str) -> None:
    if actual != expected:
        raise AssertionError(f"{what}: got {actual!r}, expected {expected!r}")


@check("api: three back ends expose the same public methods")
def test_api_parity():
    public = {
        name
        for name in dir(Backend)
        if not name.startswith("_") and callable(getattr(Backend, name, None))
    }
    for required in (
        "map", "read_mem", "write_mem", "set_regs", "get_regs",
        "call", "on_exec", "run_until", "probe", "close", "regions", "region_at",
    ):
        if required not in public:
            raise AssertionError(f"Backend is missing {required}()")
    for name, cls in BACKENDS.items():
        if not issubclass(cls, Backend):
            raise AssertionError(f"{name} does not derive from Backend")
        for method in public:
            if getattr(cls, method, None) is None:
                raise AssertionError(f"{name} hides {method}()")
        # Each back end must supply its own primitives, not inherit a stub.
        for primitive in ("_map", "_read", "_write", "_get_reg", "_set_reg", "_step", "_probe"):
            if getattr(cls, primitive) is getattr(Backend, primitive):
                raise AssertionError(f"{name} does not implement {primitive}()")


@check("pysh4: snippet registers match the hand-computed table")
def test_pysh4_registers():
    with PySh4() as engine:
        snapshot = run_snippet(engine)
    for name, value in EXPECTED.items():
        _expect_equal(snapshot["regs"][name], value, f"pysh4 {name}")
    _expect_equal(snapshot["r0"], STUB_RETURN, "pysh4 call() return")
    _expect_equal(snapshot["reason"], "return", "pysh4 reason")


@check("pysh4: snippet memory matches (stub write + saved pr)")
def test_pysh4_memory():
    with PySh4() as engine:
        snapshot = run_snippet(engine)
        _expect_equal(snapshot["dest"], "0000000f", "pysh4 dest bytes")
        _expect_equal(
            snapshot["stack_slot"], struct.pack(">I", RETURN_VA).hex(),
            "pysh4 saved pr on the stack",
        )
        _expect_equal(engine.read_mem(PROGRAM_VA, 2).hex(), "4f22", "pysh4 code bytes")


@check("pysh4: the stub is intercepted once, with the right argument")
def test_pysh4_stub():
    with PySh4() as engine:
        snapshot = run_snippet(engine)
        _expect_equal(len(snapshot["stubs"]), 1, "stub call count")
        _expect_equal(snapshot["stubs"][0]["va"], px(STUB_VA), "stub VA")
        _expect_equal(snapshot["stubs"][0]["value"], px(STUB_RETURN), "stub return")
        _expect_equal(snapshot["insns"], 26, "instruction count")


@check("pysh4: identical results on a second, fresh run")
def test_pysh4_determinism():
    first = run_snippet(PySh4())
    second = run_snippet(PySh4())
    _expect_equal(second, first, "second run snapshot")


@check("map: overlap, zero size, duplicate name and bad perms are rejected")
def test_map_rules():
    engine = PySh4()
    engine.map("a", 0x8C000000, 16, "rw")
    for name, va, data, rwx, message in (
        ("b", 0x8C000008, 16, "rw", "overlaps"),
        ("c", 0x8C000100, 0, "rw", "positive"),
        ("a", 0x8C000200, 16, "rw", "already exists"),
        ("d", 0x8C000300, 16, "rwz", "bad permissions"),
    ):
        try:
            engine.map(name, va, data, rwx)
        except UsageError as exc:
            if message not in str(exc):
                raise AssertionError(f"wrong message: {exc}") from exc
        else:
            raise AssertionError(f"map({name!r}) was accepted")


@check("mem: unmapped read, write to a read-only region, unaligned access")
def test_memory_rules():
    engine = PySh4()
    engine.map("code", 0x8C000000, 8, "rx")
    engine.map("ram", 0x8C001000, 8, "rw")
    engine.write_mem(0x8C001000, b"\x00\x01\x02\x03")
    _expect_equal(engine.read_mem(0x8C001000, 4), b"\x00\x01\x02\x03", "round trip")
    for action, code in (
        (lambda: engine.read_mem(0x8C002000, 4), "UNMAPPED"),
        (lambda: engine.write_mem(0x8C000000, b"\x00"), "UNMAPPED"),
        (lambda: engine.read_mem(0x8C001002, 8), "UNMAPPED"),
    ):
        try:
            action()
        except EngineError as exc:
            _expect_equal(exc.code, code, "memory error code")
        else:
            raise AssertionError("a forbidden access was accepted")
    # Unaligned word/long access is an SH-4 address error, not a silent split:
    # execute ``mov.l @r1,r0`` with r1 pointing into the rw region but not on a
    # 4-byte boundary.
    engine.map("exec", 0x8C003000, struct.pack(">H", 0x6112), "rx")
    engine.set_regs(pc=0x8C003000, r1=0x8C001002)
    try:
        engine.run_until(0x8C003004)
    except UnalignedAccess as exc:
        _expect_equal(exc.code, "UNALIGNED", "unaligned load code")
    else:
        raise AssertionError("an unaligned long load was accepted")


@check("regs: unknown name rejected, partial set keeps the rest, t maps to sr")
def test_register_rules():
    engine = PySh4()
    engine.set_regs(r4=7, r15=0x8C200000)
    _expect_equal(engine.get_regs()["r4"], 7, "r4")
    _expect_equal(engine.get_regs()["r0"], 0, "untouched r0")
    engine.set_regs(t=1)
    _expect_equal(engine.get_regs()["sr"] & 1, 1, "sr bit 0")
    _expect_equal(engine.get_regs()["t"], 1, "t pseudo-register")
    engine.set_regs(sr=0)
    _expect_equal(engine.get_regs()["t"], 0, "t follows sr")
    for bad in ({"r99": 1}, {"PC": 1}):
        try:
            engine.set_regs(**bad)
        except UsageError:
            pass
        else:
            raise AssertionError(f"set_regs({bad}) was accepted")


@check("run_until: stop address, executing handler and runaway budget")
def test_run_until_rules():
    with PySh4() as engine:
        build_world(engine)

        def watch(engine_, va):
            engine_.set_regs(r6=va)               # None -> instruction runs
            return None

        engine.on_exec(PROGRAM_VA + 0x06, watch)
        engine.call(PROGRAM_VA, [ITERATIONS, DEST_VA])
        _expect_equal(engine.get_regs()["r6"], PROGRAM_VA + 0x06, "executed hook ran")

    with PySh4() as engine:
        build_world(engine)
        engine.set_regs(pc=PROGRAM_VA)
        result = engine.run_until(stop=PROGRAM_VA + 0x06)
        _expect_equal(result.reason, "stop", "stop reason")
        _expect_equal(result.pc, PROGRAM_VA + 0x06, "stop pc")
        _expect_equal(result.insns, 3, "instructions before the stop")

    with PySh4() as engine:
        engine.map("spin", 0x8C000000, 4, "rwx")
        # clrt; bf -3  -- a two-instruction endless loop that never leaves the
        # mapped region, so the budget (not an unmapped fetch) has to stop it.
        engine.write_mem(0x8C000000, struct.pack(">HH", 0x0008, 0x8BFD))
        engine.set_regs(pc=0x8C000000)
        try:
            engine.run_until(max_insns=10)
        except Runaway as exc:
            _expect_equal(exc.code, "RUNAWAY", "runaway code")
        else:
            raise AssertionError("an endless loop did not raise Runaway")


@check("call: arguments land in r4-r7, five arguments are refused")
def test_call_rules():
    with PySh4() as engine:
        _expect_equal(
            len(run_snippet(engine)["regs"]), len(REGISTERS) + 1, "reg count"
        )

    engine = PySh4()
    code = struct.pack(">HH", 0x000B, 0x0009)          # rts; nop (delay slot)
    engine.map("code", 0x8C000000, code, "rx")
    _expect_equal(
        engine.call(0x8C000000, [0x11, 0x22, 0x33, 0x44]), 0, "empty r0"
    )
    regs = engine.get_regs()
    for index, value in enumerate((0x11, 0x22, 0x33, 0x44)):
        _expect_equal(
            regs["r%d" % (4 + index)], value, "argument r%d" % (4 + index)
        )

    try:
        engine.call(0x8C000000, [1, 2, 3, 4, 5])
    except UsageError as exc:
        if "at most four" not in str(exc):
            raise AssertionError(f"wrong message: {exc}") from exc
    else:
        raise AssertionError("five arguments were accepted")


@check("pysh4: unsupported instructions fail loudly, never guess")
def test_illegal_instruction():
    engine = PySh4()
    engine.map("code", 0x8C000000, 4, "rwx")
    for word, code in ((0xF000, "ILLEGAL_INSN"), (0xC300, "TRAP")):
        engine.write_mem(0x8C000000, struct.pack(">H", word))
        engine.set_regs(pc=0x8C000000)
        try:
            engine.run_until(0x8C000004)
        except EngineError as exc:
            _expect_equal(exc.code, code, f"opcode {px(word)}")
        else:
            raise AssertionError(f"opcode {px(word)} was silently executed")


def _delay_slot_run(opcode: int, t_set: bool, endian: str, slot: int = 0x7101) -> dict:
    """Run ``sett``/``clrt``; ``bt/s``/``bf/s`` +1; ``slot`` (default
    ``add #1,r1``); ``mov #99,r3`` (fall-through); stop at the instruction
    after that.

    The branch target is ``B+8``, so a taken branch skips ``mov #99,r3`` and
    an untaken one runs it.  The delay slot runs in both cases.  A ``slot``
    that writes T shows whether the condition is read at the branch (taken)
    or after the slot.
    """
    fmt = ">H" if endian == "big" else "<H"
    words = (0x0018 if t_set else 0x0008, opcode | 0x01, slot, 0xE363)
    code = b"".join(struct.pack(fmt, word) for word in words)
    base = 0x8C000000
    engine = PySh4(endian=endian)
    engine.map("code", base, code, "rx")
    engine.set_regs(pc=base)
    result = engine.run_until(stop=base + 8)
    _expect_equal(result.reason, "stop", f"stop reason ({endian})")
    return engine.get_regs()


@check("pysh4: bf/s runs its delay slot once; taken skips the fall-through")
def test_bf_s_rules():
    for endian in ("big", "little"):
        taken = _delay_slot_run(0x8F01, t_set=False, endian=endian)
        _expect_equal(taken["r1"], 1, f"bf/s taken: delay slot ({endian})")
        _expect_equal(taken["r3"], 0, f"bf/s taken: fall-through skipped ({endian})")
        untaken = _delay_slot_run(0x8F01, t_set=True, endian=endian)
        _expect_equal(untaken["r1"], 1, f"bf/s untaken: delay slot ({endian})")
        _expect_equal(untaken["r3"], 99, f"bf/s untaken: falls through ({endian})")
        # the slot sets T: the condition is the one at the branch, so still taken
        flip = _delay_slot_run(0x8F01, t_set=False, endian=endian, slot=0x0018)
        _expect_equal(flip["r3"], 0, f"bf/s, slot sets T: taken ({endian})")
        _expect_equal(flip["sr"] & 1, 1, f"bf/s, slot sets T: T after slot ({endian})")


@check("pysh4: bt/s runs its delay slot once; taken skips the fall-through")
def test_bt_s_rules():
    for endian in ("big", "little"):
        taken = _delay_slot_run(0x8D01, t_set=True, endian=endian)
        _expect_equal(taken["r1"], 1, f"bt/s taken: delay slot ({endian})")
        _expect_equal(taken["r3"], 0, f"bt/s taken: fall-through skipped ({endian})")
        untaken = _delay_slot_run(0x8D01, t_set=False, endian=endian)
        _expect_equal(untaken["r1"], 1, f"bt/s untaken: delay slot ({endian})")
        _expect_equal(untaken["r3"], 99, f"bt/s untaken: falls through ({endian})")
        # the slot clears T: the condition is the one at the branch, so still taken
        flip = _delay_slot_run(0x8D01, t_set=True, endian=endian, slot=0x0008)
        _expect_equal(flip["r3"], 0, f"bt/s, slot clears T: taken ({endian})")
        _expect_equal(flip["sr"] & 1, 0, f"bt/s, slot clears T: T after slot ({endian})")


@check("pysh4: shad/shld shift by Rm, left for >= 0, right for < 0, -32 edge")
def test_dynamic_shifts():
    # (opcode, Rn in, Rm, expected Rn out); opcode = 0x4600 | Rm<<4 | 0xC|0xD
    # with n=6, m=9: shad r9,r6 = 0x469c, shld r9,r6 = 0x469d (zlib, C-2063).
    cases = [
        (0x469D, 0x80000001, 1, 0x00000002, "shld left 1"),
        (0x469D, 0x80000001, 0xFFFFFFFC, 0x08000000, "shld right 4 (logical)"),
        (0x469C, 0x80000000, 0xFFFFFFFC, 0xF8000000, "shad right 4 (arithmetic)"),
        (0x469C, 0x00000010, 0xFFFFFFFC, 0x00000001, "shad right 4, positive"),
        (0x469D, 0x80000000, 0xFFFFFFE0, 0x00000000, "shld Rm=-32 is zero"),
        (0x469C, 0x80000000, 0xFFFFFFE0, 0xFFFFFFFF, "shad Rm=-32 keeps sign"),
        (0x469C, 0x7FFFFFFF, 0xFFFFFFE0, 0x00000000, "shad Rm=-32, positive"),
        (0x469D, 0x00000003, 0xFFFFFFFF, 0x00000001, "shld right 1"),
    ]
    for insn, rn, rm, expected, label in cases:
        engine = PySh4(endian="little")
        engine.set_regs(r6=rn, r9=rm)
        engine._execute(insn, 0x8C000000)
        _expect_equal(engine._get_reg("r6"), expected, label)


@check("pysh4: braf/bsrf take the target from the n field, not m")
def test_braf_bsrf_use_rn():
    # braf r5 = 0x0523, bsrf r5 = 0x0503; r2 carries a decoy in the m field.
    for insn, label in ((0x0523, "braf r5"), (0x0503, "bsrf r5")):
        engine = PySh4(endian="little")
        engine.set_regs(r5=0x10, r2=0x70)
        engine._execute(insn, 0x8C000000)
        _expect_equal(engine._delay, 0x8C000014, f"{label}: target = pc+4+Rn")
    engine = PySh4(endian="little")
    engine.set_regs(r5=0x10, r2=0x70)
    engine._execute(0x0503, 0x8C000000)
    _expect_equal(engine._get_reg("pr"), 0x8C000004, "bsrf r5: pr = pc+4")


@check("pysh4: mov.b/mov.w loads into a register sign-extend (C-2063 table walk)")
def test_word_loads_sign_extend():
    base = 0x8C000100
    engine = PySh4(endian="little")
    engine.map("data", base, bytearray(b"\x80\x00\x14\xF9\x7F\x00\x00\x00"), "rw")
    # mov.b @r5,r1 = 0x6150; mov.w @r5,r1 = 0x6151
    engine.set_regs(r5=base)
    engine._execute(0x6150, 0x8C000000)
    _expect_equal(engine._get_reg("r1"), 0xFFFFFF80, "mov.b @r5,r1 of 0x80")
    engine.set_regs(r5=base + 2)
    engine._execute(0x6151, 0x8C000000)
    _expect_equal(engine._get_reg("r1"), 0xFFFFF914, "mov.w @r5,r1 of 0xF914")
    engine.set_regs(r5=base + 4)
    engine._execute(0x6151, 0x8C000000)
    _expect_equal(engine._get_reg("r1"), 0x7F, "positive word stays positive")
    # mov.w @(disp,PC),r1 = 0x9100 | disp; address = pc + 4 + 2*disp
    engine._execute(0x9102, base - 4)  # disp 2 -> base + 4 holds 0x007F
    _expect_equal(engine._get_reg("r1"), 0x7F, "mov.w @(disp,PC) of 0x007F")
    engine._execute(0x9101, base - 4)  # disp 1 -> base + 2 holds 0xF914
    _expect_equal(engine._get_reg("r1"), 0xFFFFF914, "mov.w @(disp,PC) sign-extends")


@check("pysh4: endian defaults to big, selects little, rejects other values")
def test_endian_argument():
    _expect_equal(PySh4().endian, "big", "default endian")
    little = PySh4(endian="little")
    _expect_equal(little.endian, "little", "little endian")
    big = PySh4()
    for engine, expected in ((big, 0x1234), (little, 0x3412)):
        engine.map("data", 0x8C000000, bytes([0x12, 0x34]), "rw")
        _expect_equal(engine._load(0x8C000000, 2), expected,
                      f"{engine.endian} load of 12 34")
    try:
        PySh4(endian="middle")
    except UsageError:
        pass
    else:
        raise AssertionError("endian='middle' was accepted")


def _parity(name: str, factory: Callable[[], Backend], missing_code: str) -> None:
    """Run the snippet on *name*, or record an exact SKIP when it is absent."""
    backend = factory()
    try:
        availability = backend.probe()
        if not availability.available:
            _expect_equal(availability.code, missing_code, f"{name} probe code")
            try:
                run_snippet(backend)
            except EngineError as exc:
                _expect_equal(exc.code, missing_code, f"{name} raised code")
            else:
                raise AssertionError(
                    f"{name} is unavailable but run_snippet() returned a result"
                )
            SKIPS.append(f"{name}: {availability.code} - {availability.detail}")
            return
        reference = run_snippet(PySh4())
        snapshot = run_snippet(backend)
    finally:
        backend.close()

    _expect_equal(
        snapshot_core(snapshot), snapshot_core(reference), f"{name} full snapshot"
    )
    for reg, value in EXPECTED.items():
        _expect_equal(snapshot["regs"][reg], value, f"{name} {reg}")


class _AliasPySh4(PySh4):
    """PySh4 under another name: a test double for the "available" parity path.

    It is **not** an independent engine, so it cannot prove Ghidra or QEMU
    parity.  What it proves is that the comparison path really runs here and
    that it ignores a back end's label, which is exactly where a candidate
    back end would otherwise be reported as a mismatch for being itself.
    """

    name = "alias"


@check("parity: an available back end is compared without its label")
def test_parity_available_path():
    skips_before = len(SKIPS)
    _parity("alias", _AliasPySh4, "MISSING_ALIAS")
    _expect_equal(len(SKIPS), skips_before, "available back end must not skip")


@check("ghidra: runs the snippet identically, or SKIPs with MISSING_GHIDRA")
def test_ghidra_parity():
    _parity("ghidra", GhidraBackend, "MISSING_GHIDRA")


@check("qemu: runs the snippet identically, or SKIPs with MISSING_QEMU")
def test_qemu_parity():
    _parity("qemu", QemuBackend, "MISSING_QEMU")


@check("probe: pysh4 is always ready and a missing back end is never ready")
def test_probe_report():
    results = {item.name: item for item in probe_all()}
    _expect_equal(set(results), set(BACKENDS), "probed engines")
    if not results["pysh4"].available:
        raise AssertionError("pysh4 must always be available")
    for name, item in results.items():
        if item.available:
            _expect_equal(item.code, "", f"{name} available code")
        else:
            if item.code not in ("MISSING_GHIDRA", "MISSING_QEMU", "BLOCKED"):
                raise AssertionError(f"{name}: unexpected status {item.code!r}")
            if not item.detail:
                raise AssertionError(f"{name}: unavailable without a reason")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="L3 engine interface: one API, three SH-4 back ends (M9.4).",
        epilog="Exit codes: 0 ok, 1 check failed, 2 usage, 3 back end missing, 4 blocked.",
    )
    parser.add_argument("--selftest", action="store_true",
                        help="run the synthetic acceptance checks")
    parser.add_argument("--probe", action="store_true",
                        help="report which back ends can run here")
    parser.add_argument("--demo", action="store_true",
                        help="run the synthetic snippet on --engine and print the snapshot")
    parser.add_argument("--engine", default="pysh4",
                        help="back end for --demo: %s" % ", ".join(BACKENDS))
    parser.add_argument("--program", default=None,
                        help="Ghidra program for --engine ghidra (firmware import, M9.2)")
    parser.add_argument("--qemu", default=None, help="qemu-system-sh4 binary for --engine qemu")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.selftest:
        return _run_selftest()
    if args.probe:
        results = probe_all()
        if args.json:
            print(json.dumps([item.as_dict() for item in results], indent=2))
        else:
            for item in results:
                if item.available:
                    print(f"{item.name:7s} READY    {item.detail}")
                else:
                    print(f"{item.name:7s} {item.code}: {item.detail}")
        return EXIT_OK
    if args.demo:
        return _run_demo(args)
    parser.print_help()
    return EXIT_USAGE


def _run_selftest() -> int:
    failures = 0
    for name, func in CHECKS:
        try:
            func()
        except Exception as exc:  # noqa: BLE001 - report, do not abort
            failures += 1
            print(f"FAIL {name}: {exc}")
            if os.environ.get("L3_SELFTEST_VERBOSE"):
                import traceback
                traceback.print_exc()
        else:
            print(f"ok   {name}")
    for skip in SKIPS:
        print(f"skip {skip}")
    print()
    total = len(CHECKS)
    skipped = len(SKIPS)
    if failures:
        print(f"selftest: FAILED ({failures}/{total} checks, {skipped} skipped)")
        return EXIT_FAIL
    if skipped:
        print(
            f"selftest: OK ({total - skipped} checks, {skipped} skipped) - "
            "a skipped back end is not a pass"
        )
    else:
        print(f"selftest: OK ({total} checks, every back end ran)")
    return EXIT_OK


def _run_demo(args) -> int:
    if args.engine not in BACKENDS:
        print(f"usage: unknown engine {args.engine!r} (known: {', '.join(BACKENDS)})")
        return EXIT_USAGE
    backend = BACKENDS[args.engine](**(
        {"program": args.program} if args.engine == "ghidra" and args.program else
        {"qemu": args.qemu} if args.engine == "qemu" and args.qemu else {}
    ))
    try:
        snapshot = run_snippet(backend)
    except EngineError as exc:
        if args.json:
            print(json.dumps(exc.as_dict(), indent=2))
        else:
            print(f"{exc.code}: {exc.message}")
            print(f"RESULT: {exc.code}")
        return EXIT_MISSING if exc.code in ("MISSING_GHIDRA", "MISSING_QEMU") else EXIT_BLOCKED
    finally:
        backend.close()

    payload = dict(snapshot)
    payload["regs"] = {name: px(value) for name, value in snapshot["regs"].items()}
    payload["expected"] = {name: px(value) for name, value in EXPECTED.items()}
    payload["matches_reference"] = snapshot_core(snapshot) == snapshot_core(
        run_snippet(PySh4())
    )
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"engine  {snapshot['engine']}")
        print(f"call    return r0={px(snapshot['r0'])} over {snapshot['insns']} instructions")
        print(f"dest    {snapshot['dest']}  (stub wrote r4)")
        print(f"stack   {snapshot['stack_slot']}  (saved pr)")
        for name, value in EXPECTED.items():
            print(f"{name:7s} {px(snapshot['regs'][name])}  expected {px(value)}")
        print(f"stubs   {[(item['va'], item['value']) for item in snapshot['stubs']]}")
        print(f"RESULT: {'PASS' if payload['matches_reference'] else 'MISMATCH'}")
    return EXIT_OK if payload["matches_reference"] else EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
