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
import functools
import json
import os
import re
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
    "WatchRange",
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

#: SR.Q and SR.M (bits 8 and 9), the divide-step state of div0s/div0u/div1.
SR_Q = 0x100
SR_M = 0x200

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


def _div1_step(rn: int, rm: int, t: bool, old_q: int, mbit: int):
    """One SH-4 ``div1 Rm,Rn`` step, transcribed from the manual's C code.

    Returns ``(new Rn, new Q)``; the caller sets T = (Q == M).  ``rm`` is read
    before Rn is shifted, so ``div1 Rn,Rn`` matches the manual too.
    """
    q = (rn >> 31) & 1
    rn = ((rn << 1) | (1 if t else 0)) & M32
    tmp0 = rn
    if old_q == mbit:                    # (Q,M) = (0,0) or (1,1): subtract
        rn = (rn - rm) & M32
        tmp1 = 1 if rn > tmp0 else 0     # borrow
    else:                                # (0,1) or (1,0): add
        rn = (rn + rm) & M32
        tmp1 = 1 if rn < tmp0 else 0     # carry
    # Manual: Q = tmp1 when Q == (M ^ old_q ^ ... ) -- spelled out per case:
    # old_q=0,M=0: Q=0 -> tmp1, Q=1 -> !tmp1
    # old_q=0,M=1: Q=0 -> !tmp1, Q=1 -> tmp1
    # old_q=1,M=0: Q=0 -> tmp1, Q=1 -> !tmp1
    # old_q=1,M=1: Q=0 -> !tmp1, Q=1 -> tmp1
    if mbit == 0:
        q = tmp1 if q == 0 else 1 - tmp1
    else:
        q = 1 - tmp1 if q == 0 else tmp1
    return rn, q


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
class WatchRange:
    """One ``watch()`` request: log every guest access of *kind* to [lo, hi).

    Observation only: the hit is recorded *inside* ``PySh4._load``/``_store``
    after the real access, so a watch never changes a verdict.  ``kind`` is
    ``"r"`` (loads), ``"w"`` (stores) or ``"rw"``; the caller-facing report
    separates ``api`` hits (``read_mem``/``write_mem``, used by stubs and
    setup) and ``x`` hits (instruction fetch) so they can never be counted as
    guest reads.
    """

    lo: int
    hi: int
    kind: str
    name: str

    def covers(self, va: int, size: int) -> bool:
        return va < self.hi and self.lo < va + size


@dataclass
class WatchHit:
    """One recorded access: program counter, address, width, kind."""

    pc: int
    va: int
    size: int
    kind: str          # "r" | "w" | "api-r" | "api-w" | "x"
    name: str

    def as_dict(self) -> dict:
        return {"pc": px(self.pc), "va": px(self.va), "size": self.size,
                "kind": self.kind, "watch": self.name}


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
        self._watches: list[WatchRange] = []
        self._watch_hits: list[WatchHit] = []
        self._watch_armed = False
        self._watches_on = False       # fast path: False means no recording

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

    # -- read/write watch (M9.38) -----------------------------------------

    def watch(self, lo: int, hi: int, kind: str = "r", name: str = "watch") -> WatchRange:
        """Log every guest access of *kind* to ``[lo, hi)`` at the next arm.

        ``kind``: ``"r"`` loads, ``"w"`` stores, ``"rw"`` both.  The range must
        already be mapped when :meth:`arm_watch` runs (a typo is a loud usage
        error, never a silent zero).  Recording is inert until ``arm_watch()``,
        so set-up writes (map, input bytes, ctx/stack/table) are not hits.
        """
        if kind not in ("r", "w", "rw"):
            raise UsageError(f"watch(): kind must be 'r', 'w' or 'rw', not {kind!r}")
        lo = int(lo) & M32
        hi = int(hi) & M32
        if hi <= lo:
            raise UsageError(f"watch(): empty range {px(lo)}..{px(hi)}")
        if not isinstance(name, str) or not name:
            raise UsageError("watch(): name must be a non-empty string")
        item = WatchRange(lo=lo, hi=hi, kind=kind, name=name)
        self._watches.append(item)
        return item

    def arm_watch(self) -> None:
        """Start recording; every watch range must be inside a mapped region."""
        for item in self._watches:
            if self.region_at(item.lo) is None or self.region_at(item.hi - 1) is None:
                raise UsageError(
                    f"watch[{item.name}]: {px(item.lo)}..{px(item.hi)} is not inside "
                    "a mapped region at arm time (wrong base?)"
                )
        self._watch_armed = bool(self._watches)
        self._watches_on = self._watch_armed

    def disarm_watch(self) -> None:
        self._watch_armed = False
        self._watches_on = False

    def watch_hits(self) -> list[WatchHit]:
        return list(self._watch_hits)

    def watch_ranges(self) -> list[dict]:
        return [{"name": w.name, "lo": px(w.lo), "hi": px(w.hi), "kind": w.kind}
                for w in self._watches]

    def _record_watch(self, va: int, size: int, tag: str) -> None:
        """Called from inside a load/store; ``tag`` is r/w/x or api-r/api-w.

        ``x`` (instruction fetch) never matches a data watch.  ``api-*`` hits
        are recorded but the summary excludes them from guest reads: they come
        from stubs and harness setup, not from the function under test.
        """
        if not self._watches_on or tag == "x":
            return
        base = "r" if tag in ("r", "api-r") else "w"
        # Attribute a guest access to the instruction that made it, not to
        # ``pc`` -- PySh4 has already advanced pc past the instruction.
        pc = self._insn_pc if self._insn_pc is not None else (self._get_pc() & M32)
        for item in self._watches:
            if item.kind != "rw" and item.kind != base:
                continue
            if not item.covers(va, size):
                continue
            self._watch_hits.append(WatchHit(
                pc=pc & M32, va=va & M32, size=size,
                kind=tag, name=item.name,
            ))
            return

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

#: Instruction-form table, written **only** from the SH-4 manual encoding
#: (``nnnn`` = bits 11-8, ``mmmm`` = bits 7-4, ``dddd`` = bits 3-0; the
#: ``0x8xxx`` group puts ``Rn`` in bits 7-4 and the low nibble is the
#: displacement).  This table is deliberately independent of ``_exec_*``: it
#: exists so the decoder and the executor can be compared, and a bug in one
#: cannot hide itself in the other (M9.37).  ``register_fields`` says which
#: nibbles name a register: ``"n"``, ``"m"``, ``"nm"``, ``"m"`` or
#: ``""`` (no register operand).
#:
#: ``(mask, match, form, register_fields)`` in first-match order.
DECODE_TABLE: tuple[tuple[int, int, str, str], ...] = (
    # group 0: system / control (low byte distinguishes)
    (0xFFFF, 0x0009, "nop", ""),
    (0xFFFF, 0x000B, "rts", ""),
    (0xFFFF, 0x002B, "rte", ""),
    (0xFFFF, 0x0008, "clrt", ""),
    (0xFFFF, 0x0018, "sett", ""),
    (0xFFFF, 0x0028, "clrmac", ""),
    (0xFFFF, 0x0019, "div0u", ""),
    (0xF0FF, 0x0002, "stc_sr", "n"),
    (0xF0FF, 0x0012, "stc_gbr", "n"),
    (0xF0FF, 0x0022, "stc_vbr", "n"),
    (0xF0FF, 0x000A, "sts_mach", "n"),
    (0xF0FF, 0x001A, "sts_macl", "n"),
    (0xF0FF, 0x002A, "sts_pr", "n"),
    (0xF0FF, 0x0029, "movt", "n"),
    (0xF0FF, 0x0003, "bsrf", "n"),
    (0xF0FF, 0x0023, "braf", "n"),
    (0xF00F, 0x0007, "mul.l", "nm"),
    (0xF0FF, 0x0083, "pref", "n"),
    (0xF0FF, 0x0093, "ocbi", "n"),
    (0xF0FF, 0x00A3, "ocbp", "n"),
    (0xF0FF, 0x00B3, "ocbwb", "n"),
    (0xF0FF, 0x00C3, "movca.l", "n"),
    (0xF00F, 0x000F, "mac.l", "nm"),            # mac.l @Rm+,@Rn+ (M9.51)
    (0xF00F, 0x0004, "mov.b_m_at_r0_plus_n", "nm"),
    (0xF00F, 0x0005, "mov.w_m_at_r0_plus_n", "nm"),
    (0xF00F, 0x0006, "mov.l_m_at_r0_plus_n", "nm"),
    (0xF00F, 0x000C, "mov.b_at_r0_plus_m_n", "nm"),
    (0xF00F, 0x000D, "mov.w_at_r0_plus_m_n", "nm"),
    (0xF00F, 0x000E, "mov.l_at_r0_plus_m_n", "nm"),
    # group 1: mov.l Rm,@(disp,Rn)
    (0xF000, 0x1000, "mov.l_m_at_disp_n", "nm"),
    # group 2: stores and alu-immediate (low nibble distinguishes)
    (0xF00F, 0x2000, "mov.b_m_at_n", "nm"),
    (0xF00F, 0x2001, "mov.w_m_at_n", "nm"),
    (0xF00F, 0x2002, "mov.l_m_at_n", "nm"),
    (0xF00F, 0x2004, "mov.b_m_at_minus_n", "nm"),
    (0xF00F, 0x2005, "mov.w_m_at_minus_n", "nm"),
    (0xF00F, 0x2006, "mov.l_m_at_minus_n", "nm"),
    (0xF00F, 0x2007, "div0s", "nm"),
    (0xF00F, 0x2008, "tst", "nm"),
    (0xF00F, 0x2009, "and", "nm"),
    (0xF00F, 0x200A, "xor", "nm"),
    (0xF00F, 0x200B, "or", "nm"),
    (0xF00F, 0x200C, "cmp/str", "nm"),
    (0xF00F, 0x200D, "xtrct", "nm"),
    (0xF00F, 0x200E, "mulu.w", "nm"),
    (0xF00F, 0x200F, "muls.w", "nm"),
    # group 3: alu register-register
    (0xF00F, 0x3000, "cmp/eq", "nm"),
    (0xF00F, 0x3002, "cmp/hs", "nm"),
    (0xF00F, 0x3003, "cmp/ge", "nm"),
    (0xF00F, 0x3004, "div1", "nm"),
    (0xF00F, 0x3006, "cmp/hi", "nm"),
    (0xF00F, 0x3007, "cmp/gt", "nm"),
    (0xF00F, 0x3008, "sub", "nm"),
    (0xF00F, 0x300A, "subc", "nm"),
    (0xF00F, 0x300B, "subv", "nm"),
    (0xF00F, 0x300C, "add", "nm"),
    (0xF00F, 0x300D, "dmuls.l", "nm"),
    (0xF00F, 0x300E, "addc", "nm"),
    (0xF00F, 0x300F, "addv", "nm"),
    (0xF00F, 0x3005, "dmulu.l", "nm"),
    # group 4: system / shifts / control registers (register is bits 11-8)
    (0xF0FF, 0x4000, "shll", "n"),
    (0xF0FF, 0x4001, "shlr", "n"),
    (0xF0FF, 0x4008, "shll2", "n"),
    (0xF0FF, 0x4009, "shlr2", "n"),
    (0xF0FF, 0x4018, "shll8", "n"),
    (0xF0FF, 0x4019, "shlr8", "n"),
    (0xF0FF, 0x4020, "shal", "n"),
    (0xF0FF, 0x4021, "shar", "n"),
    (0xF0FF, 0x4024, "rotcl", "n"),
    (0xF0FF, 0x4025, "rotcr", "n"),
    (0xF0FF, 0x4028, "shll16", "n"),
    (0xF0FF, 0x4029, "shlr16", "n"),
    (0xF0FF, 0x4010, "dt", "n"),
    (0xF0FF, 0x4011, "cmp/pz", "n"),
    (0xF0FF, 0x4015, "cmp/pl", "n"),
    (0xF0FF, 0x401B, "tas.b", "n"),
    (0xF0FF, 0x400B, "jsr", "n"),
    (0xF0FF, 0x402B, "jmp", "n"),
    (0xF0FF, 0x400E, "ldc_sr", "n"),
    (0xF0FF, 0x401E, "ldc_gbr", "n"),
    (0xF0FF, 0x402E, "ldc_vbr", "n"),
    (0xF0FF, 0x400A, "lds_mach", "n"),
    (0xF0FF, 0x401A, "lds_macl", "n"),
    (0xF0FF, 0x402A, "lds_pr", "n"),
    (0xF0FF, 0x4002, "sts.l_mach_at_minus_n", "n"),
    (0xF0FF, 0x4012, "sts.l_macl_at_minus_n", "n"),
    (0xF0FF, 0x4022, "sts.l_pr_at_minus_n", "n"),
    (0xF0FF, 0x4003, "stc.l_sr_at_minus_n", "n"),
    (0xF0FF, 0x4013, "stc.l_gbr_at_minus_n", "n"),
    (0xF0FF, 0x4023, "stc.l_vbr_at_minus_n", "n"),
    (0xF0FF, 0x4006, "lds.l_mach_at_n_plus", "n"),
    (0xF0FF, 0x4016, "lds.l_macl_at_n_plus", "n"),
    (0xF0FF, 0x4026, "lds.l_pr_at_n_plus", "n"),
    (0xF0FF, 0x4007, "ldc.l_sr_at_n_plus", "n"),
    (0xF0FF, 0x4017, "ldc.l_gbr_at_n_plus", "n"),
    (0xF0FF, 0x4027, "ldc.l_vbr_at_n_plus", "n"),
    (0xF00F, 0x400C, "shad", "nm"),
    (0xF00F, 0x400D, "shld", "nm"),
    (0xF00F, 0x400F, "mac.w", "nm"),
    # group 5: mov.l @(disp,Rm),Rn
    (0xF000, 0x5000, "mov.l_at_disp_m_n", "nm"),
    # group 6: loads
    (0xF00F, 0x6000, "mov.b_at_m_n", "nm"),
    (0xF00F, 0x6001, "mov.w_at_m_n", "nm"),
    (0xF00F, 0x6002, "mov.l_at_m_n", "nm"),
    (0xF00F, 0x6003, "mov_m_n", "nm"),
    (0xF00F, 0x6004, "mov.b_at_m_plus_n", "nm"),
    (0xF00F, 0x6005, "mov.w_at_m_plus_n", "nm"),
    (0xF00F, 0x6006, "mov.l_at_m_plus_n", "nm"),
    (0xF00F, 0x6007, "not", "nm"),
    (0xF00F, 0x6008, "swap.b", "nm"),
    (0xF00F, 0x6009, "swap.w", "nm"),
    (0xF00F, 0x600A, "negc", "nm"),
    (0xF00F, 0x600B, "neg", "nm"),
    (0xF00F, 0x600C, "extu.b", "nm"),
    (0xF00F, 0x600D, "extu.w", "nm"),
    (0xF00F, 0x600E, "exts.b", "nm"),
    (0xF00F, 0x600F, "exts.w", "nm"),
    # group 7: add #imm,Rn
    (0xF000, 0x7000, "add_imm", "n"),
    # group 8: Rn is bits 7-4, d is the low nibble
    (0xFF00, 0x8000, "mov.b_r0_at_disp_m", "m"),
    (0xFF00, 0x8100, "mov.w_r0_at_disp_m", "m"),
    (0xFF00, 0x8400, "mov.b_at_disp_m_r0", "m"),
    (0xFF00, 0x8500, "mov.w_at_disp_m_r0", "m"),
    (0xFF00, 0x8800, "cmp/eq_imm", ""),
    (0xFF00, 0x8900, "bt", ""),
    (0xFF00, 0x8B00, "bf", ""),
    (0xFF00, 0x8D00, "bt/s", ""),
    (0xFF00, 0x8F00, "bf/s", ""),
    # group 9: mov.w @(disp,PC),Rn
    (0xF000, 0x9000, "mov.w_pc", "n"),
    # group A/B: bra / bsr
    (0xF000, 0xA000, "bra", ""),
    (0xF000, 0xB000, "bsr", ""),
    # group C: immediate byte (the n nibble selects the form)
    (0xFF00, 0xC000, "mov.b_r0_gbr", ""),
    (0xFF00, 0xC100, "mov.w_r0_gbr", ""),
    (0xFF00, 0xC200, "mov.l_r0_gbr", ""),
    (0xFF00, 0xC300, "trapa", ""),
    (0xFF00, 0xC400, "mov.b_gbr_r0", ""),
    (0xFF00, 0xC500, "mov.w_gbr_r0", ""),
    (0xFF00, 0xC600, "mov.l_gbr_r0", ""),
    (0xFF00, 0xC700, "mova", ""),
    (0xFF00, 0xC800, "tst_imm", ""),
    (0xFF00, 0xC900, "and_imm", ""),
    (0xFF00, 0xCA00, "xor_imm", ""),
    (0xFF00, 0xCB00, "or_imm", ""),
    (0xFF00, 0xCC00, "tst.b_imm", ""),
    (0xFF00, 0xCD00, "and.b_imm", ""),
    (0xFF00, 0xCE00, "xor.b_imm", ""),
    (0xFF00, 0xCF00, "or.b_imm", ""),
    # group D: mov.l @(disp,PC),Rn
    (0xF000, 0xD000, "mov.l_pc", "n"),
    # group E: mov #imm,Rn
    (0xF000, 0xE000, "mov_imm", "n"),
    # group F: floating point (not modelled, counted)
    (0xF000, 0xF000, "fpu", ""),
)


def decode_fields(insn: int) -> tuple[str, int | None, int | None, int]:
    """Independent decode of one halfword: ``(form, rn, rm, d)``.

    Walks :data:`DECODE_TABLE` in order and returns the first match.  ``rn``,
    ``rm`` are the register numbers the form names, or ``None`` when the form
    names no register there; ``d`` is the 4-bit displacement.  This shares
    nothing with ``_exec_*`` on purpose -- that independence is what the
    M9.37 drift test checks.
    """
    insn &= 0xFFFF
    n = (insn >> 8) & 0xF
    m = (insn >> 4) & 0xF
    d = insn & 0xF
    for mask, match, form, fields in DECODE_TABLE:
        if insn & mask == match:
            rn = n if "n" in fields else None
            rm = m if ("m" in fields or fields == "m") else None
            return form, rn, rm, d
    return "unknown", None, None, d


# --------------------------------------------------------------------------
# PySh4 fast path (M9.45): basic blocks translated to Python once
# --------------------------------------------------------------------------
#
# ``PySh4.run_until`` used to fetch, decode and dispatch every instruction
# through ``_step`` -> ``_execute`` -> ``_exec_*`` with a linear region search
# per fetch and per access: about 2.2 us per instruction.  The fast path
# translates each straight-line run of instructions (a *block*) into one
# Python function the first time its start PC is reached, and runs that.
#
# Equivalence with ``_step`` is the contract, not an aim:
#
# * every template below is a transcription of the ``_exec_*`` arm with the
#   same order of register writes, loads and stores, so a fault leaves the
#   same partial state; the faulting instruction's PC + 2 goes to ``pc`` and
#   its arm name to ``_arm``, as ``_step`` leaves them;
# * an instruction without a template ends the block and runs through
#   ``_step`` (every FPU, MMU, div, mac, trapa... form);
# * a block never contains a PC that ``run_until`` must look at: a stop
#   address, an ``on_exec`` hook or ``RETURN_VA`` can only be a block start;
# * a store that lands in an executable region invalidates every block and
#   leaves the current one after that instruction (self-modifying code runs
#   the new bytes, as ``_step`` would);
# * the fast path is off -- and ``_step`` runs everything -- while a watch is
#   armed, for a callable ``stop``, inside a pending delay slot, when a block
#   would run past ``max_insns``, and for any subclass or instance that
#   overrides an interpreter method (``runner.GuardedPySh4``,
#   ``div1_l3.ShimSh4``, a patched ``_execute``).
#
# ``engine.py --selftest`` holds the differential check: all 65,536
# halfwords from several register states, and random straight-line blocks,
# through both paths.


class _SMC(Exception):
    """Internal: a fast-path store hit an executable region."""


_TC_MAX = 64          # instructions per block

#: ``(start pc, instruction words, end kind)`` -> compiled block, shared by
#: every engine in the process (``nk_decomp check`` builds one engine per
#: section and would re-translate otherwise).  The source is a pure function
#: of the key; per-engine state (cache cells, ``ENG``) is bound at exec time.
_TC_CODE_CACHE: dict = {}


def _tc_r(k: int) -> str:
    return "R['r%d']" % k


def _tc_sett(cond: str) -> list:
    return ["R['sr'] = (R['sr'] | 1) if (%s) else (R['sr'] & -2)" % cond]


def _tc_sx8(expr: str) -> str:
    return "(((((%s) & 0xFF) ^ 0x80) - 0x80) & 0xFFFFFFFF)" % expr


def _tc_sx16(expr: str) -> str:
    return "(((((%s) & 0xFFFF) ^ 0x8000) - 0x8000) & 0xFFFFFFFF)" % expr


def _tc_load(dest: str, size: int, addr: str, signed: bool) -> list:
    """Lines for ``dest = _load[_signed](addr, size)``.  ``@C`` is this
    site's one-region cache cell ``[lo, hi, data]`` (numbered by the block
    builder); a miss goes through ``LDM`` -> ``_load``, which raises what
    ``_step`` raises."""
    align = "" if size == 1 else "not ma & %d and " % (size - 1)
    if size == 1:
        hit = "mv = mc[2][ma - mc[0]]"
    else:
        hit = "mv = U%d(mc[2], ma - mc[0])[0]" % size
    value = "mv"
    if signed and size == 1:
        value = _tc_sx8("mv")
    elif signed and size == 2:
        value = _tc_sx16("mv")
    return ["ma = %s" % addr, "mc = @C",
            "if %smc[0] <= ma and ma + %d <= mc[1]:" % (align, size),
            "    " + hit,
            "else:",
            "    mv = LDM(ma, %d, mc)" % size,
            "%s = %s" % (dest, value)]


def _tc_store(size: int, addr: str, value: str) -> list:
    """Lines for ``_store(addr, size, value)`` with a per-site cache cell; a
    miss (or an executable region) goes through ``STM`` -> ``_store``."""
    align = "" if size == 1 else "not ma & %d and " % (size - 1)
    if size == 1:
        hit = "mc[2][ma - mc[0]] = (%s) & 0xFF"
    else:
        hit = "P%d(mc[2], ma - mc[0], (%%s) & %s)" % (size, "0xFFFF" if size == 2 else "0xFFFFFFFF")
    return ["ma = %s" % addr, "mv = %s" % value, "mc = @C",
            "if %smc[0] <= ma and ma + %d <= mc[1]:" % (align, size),
            "    " + hit % "mv",
            "else:",
            "    STM(ma, %d, mv, mc)" % size]


def _tc_insn(insn: int, pc: int):
    """Template for one instruction at *pc*.

    Returns ``None`` (no template: ``_step`` runs it), or a tuple
    ``(kind, lines, faults, arm)`` with *kind* ``"op"`` (straight-line),
    ``"delay"`` (sets local ``tgt``; the slot follows), ``"cond"`` (bt/bf:
    *lines* is the T condition source, the target is in ``arm``'s slot --
    see below) or ``"pcend"`` (unused).  For ``"cond"`` the tuple is
    ``("cond", (cond_src, target), False, arm)``.
    """
    n = (insn >> 8) & 0xF
    m = (insn >> 4) & 0xF
    d8 = insn & 0xFF
    top = insn >> 12
    Rn, Rm = _tc_r(n), _tc_r(m)
    M = "0xFFFFFFFF"

    def op(lines, arm, faults=False):
        return ("op", lines, faults, arm)

    if top == 0xE:
        return op(["%s = %d" % (Rn, _sx(d8, 8) & M32)], "mov_imm")
    if top == 0x7:
        return op(["%s = (%s + %d) & %s" % (Rn, Rn, _sx(d8, 8), M)], "add_imm")
    if top == 0xD:
        return op(_tc_load(Rn, 4, str(((pc + 4) & ~3) + d8 * 4), False), "mov.l_pc", True)
    if top == 0x9:
        return op(_tc_load(Rn, 2, str(pc + 4 + d8 * 2), True), "mov.w_pc", True)
    if top == 0xA:
        return ("delay", ["tgt = %d" % ((pc + 4 + _sx(insn & 0xFFF, 12) * 2) & M32)],
                False, "bra")
    if top == 0xB:
        return ("delay", ["R['pr'] = %d" % ((pc + 4) & M32),
                          "tgt = %d" % ((pc + 4 + _sx(insn & 0xFFF, 12) * 2) & M32)],
                False, "bsr")
    if top == 0x1:
        return op(_tc_store(4, "(%s + %d) & %s" % (Rn, (insn & 0xF) * 4, M), Rm),
                  "mov.l_m_at_disp_n", True)
    if top == 0x5:
        return op(_tc_load(Rn, 4, "(%s + %d) & %s" % (Rm, (insn & 0xF) * 4, M), False),
                  "mov.l_at_disp_m_n", True)
    if top == 0x3:
        sub = insn & 0xF
        if sub == 0x0:
            return op(_tc_sett("%s == %s" % (Rn, Rm)), "cmp/eq")
        if sub == 0x2:
            return op(_tc_sett("%s >= %s" % (Rn, Rm)), "cmp/hs")
        if sub == 0x3:
            return op(_tc_sett("(%s ^ 0x80000000) >= (%s ^ 0x80000000)" % (Rn, Rm)),
                      "cmp/ge")
        if sub == 0x6:
            return op(_tc_sett("%s > %s" % (Rn, Rm)), "cmp/hi")
        if sub == 0x7:
            return op(_tc_sett("(%s ^ 0x80000000) > (%s ^ 0x80000000)" % (Rn, Rm)),
                      "cmp/gt")
        if sub == 0x8:
            return op(["%s = (%s - %s) & %s" % (Rn, Rn, Rm, M)], "sub")
        if sub == 0xC:
            return op(["%s = (%s + %s) & %s" % (Rn, Rn, Rm, M)], "add")
        if sub == 0xE:
            return op(["v = %s + %s + (R['sr'] & 1)" % (Rn, Rm),
                       "%s = v & %s" % (Rn, M)] + _tc_sett("v > %s" % M), "addc")
        if sub == 0xA:
            return op(["v = %s - %s - (R['sr'] & 1)" % (Rn, Rm),
                       "%s = v & %s" % (Rn, M)] + _tc_sett("v < 0"), "subc")
        return None
    if top == 0x2:
        sub = insn & 0xF
        if sub in (0x0, 0x1, 0x2):
            size = (1, 2, 4)[sub]
            arm = ("mov.b_m_at_n", "mov.w_m_at_n", "mov.l_m_at_n")[sub]
            return op(_tc_store(size, Rn, Rm), arm, True)
        if sub in (0x4, 0x5, 0x6):
            size = (1, 2, 4)[sub - 4]
            arm = ("mov.b_m_at_minus_n", "mov.w_m_at_minus_n",
                   "mov.l_m_at_minus_n")[sub - 4]
            return op(["v = %s" % Rm, "a = (%s - %d) & %s" % (Rn, size, M),
                       "%s = a" % Rn] + _tc_store(size, "a", "v"), arm, True)
        if sub == 0x8:
            return op(_tc_sett("(%s & %s) == 0" % (Rn, Rm)), "tst")
        if sub == 0x9:
            return op(["%s = %s & %s" % (Rn, Rn, Rm)], "and")
        if sub == 0xA:
            return op(["%s = %s ^ %s" % (Rn, Rn, Rm)], "xor")
        if sub == 0xB:
            return op(["%s = %s | %s" % (Rn, Rn, Rm)], "or")
        if sub == 0xE:
            return op(["R['macl'] = ((%s & 0xFFFF) * (%s & 0xFFFF)) & %s" % (Rn, Rm, M)],
                      "mulu.w")
        return None
    if top == 0x6:
        sub = insn & 0xF
        if sub in (0x0, 0x1, 0x2):
            size = (1, 2, 4)[sub]
            arm = ("mov.b_at_m_n", "mov.w_at_m_n", "mov.l_at_m_n")[sub]
            return op(_tc_load(Rn, size, Rm, size != 4), arm, True)
        if sub == 0x3:
            return op(["%s = %s" % (Rn, Rm)], "mov_m_n")
        if sub in (0x4, 0x5, 0x6):
            size = (1, 2, 4)[sub - 4]
            arm = ("mov.b_at_m_plus_n", "mov.w_at_m_plus_n",
                   "mov.l_at_m_plus_n")[sub - 4]
            return op(["a = %s" % Rm] + _tc_load(Rn, size, "a", size != 4)
                      + ["%s = (a + %d) & %s" % (Rm, size, M)], arm, True)
        if sub == 0x7:
            return op(["%s = ~%s & %s" % (Rn, Rm, M)], "not")
        if sub == 0x8:
            return op(["v = %s" % Rm,
                       "%s = ((v & 0xFF00FF00) | ((v & 0xFF) << 16) | ((v >> 16) & 0xFF)) & %s"
                       % (Rn, M)], "swap.b")
        if sub == 0x9:
            return op(["v = %s" % Rm, "%s = ((v << 16) | (v >> 16)) & %s" % (Rn, M)],
                      "swap.w")
        if sub == 0xB:
            return op(["%s = (-%s) & %s" % (Rn, Rm, M)], "neg")
        if sub == 0xC:
            return op(["%s = %s & 0xFF" % (Rn, Rm)], "extu.b")
        if sub == 0xD:
            return op(["%s = %s & 0xFFFF" % (Rn, Rm)], "extu.w")
        if sub == 0xE:
            return op(["%s = %s" % (Rn, _tc_sx8(Rm))], "exts.b")
        if sub == 0xF:
            return op(["%s = %s" % (Rn, _tc_sx16(Rm))], "exts.w")
        return None
    if top == 0x4:
        low = insn & 0xFF
        simple = {
            0x08: ("shll2", "(%s << 2) & %s"), 0x09: ("shlr2", "%s >> 2"),
            0x18: ("shll8", "(%s << 8) & %s"), 0x19: ("shlr8", "%s >> 8"),
            0x28: ("shll16", "(%s << 16) & %s"), 0x29: ("shlr16", "%s >> 16"),
        }
        if low in simple:
            arm, expr = simple[low]
            expr = expr % ((Rn, M) if "&" in expr else (Rn,))
            return op(["%s = %s" % (Rn, expr)], arm)
        if low in (0x00, 0x20):
            return op(["v = %s" % Rn] + _tc_sett("v & 0x80000000")
                      + ["%s = (v << 1) & %s" % (Rn, M)],
                      "shll" if low == 0x00 else "shal")
        if low == 0x01:
            return op(["v = %s" % Rn] + _tc_sett("v & 1") + ["%s = v >> 1" % Rn], "shlr")
        if low == 0x21:
            return op(["v = %s" % Rn] + _tc_sett("v & 1")
                      + ["%s = ((v >> 1) | (v & 0x80000000)) & %s" % (Rn, M)], "shar")
        if low == 0x10:
            return op(["v = (%s - 1) & %s" % (Rn, M), "%s = v" % Rn]
                      + _tc_sett("v == 0"), "dt")
        if low == 0x11:
            return op(_tc_sett("not %s & 0x80000000" % Rn), "cmp/pz")
        if low == 0x15:
            return op(_tc_sett("0 < %s < 0x80000000" % Rn), "cmp/pl")
        if low == 0x0B:
            return ("delay", ["v = %s" % Rn, "R['pr'] = %d" % ((pc + 4) & M32),
                              "tgt = v"], False, "jsr")
        if low == 0x2B:
            return ("delay", ["tgt = %s" % Rn], False, "jmp")
        if low == 0x2A:
            return op(["R['pr'] = %s" % Rn], "lds_pr")
        if low == 0x1A:
            return op(["R['macl'] = %s" % Rn], "lds_macl")
        if low == 0x22:
            return op(["a = (%s - 4) & %s" % (Rn, M), "%s = a" % Rn,
                       ] + _tc_store(4, "a", "R['pr']"), "sts.l_pr_at_minus_n", True)
        if low == 0x26:
            return op(["a = %s" % Rn] + _tc_load("R['pr']", 4, "a", False)
                      + ["%s = (a + 4) & %s" % (Rn, M)], "lds.l_pr_at_n_plus", True)
        if insn & 0xF in (0x0C, 0x0D):
            arithmetic = (insn & 0xF) == 0x0C
            lines = ["v = %s" % Rn, "s = %s" % Rm,
                     "if not s & 0x80000000:",
                     "    %s = (v << (s & 0x1F)) & %s" % (Rn, M),
                     "elif s & 0x1F == 0:"]
            if arithmetic:
                lines += ["    %s = %s if v & 0x80000000 else 0" % (Rn, M),
                          "else:",
                          "    %s = ((((v ^ 0x80000000) - 0x80000000) >> "
                          "(((~s) & 0x1F) + 1))) & %s" % (Rn, M)]
            else:
                lines += ["    %s = 0" % Rn,
                          "else:",
                          "    %s = v >> (((~s) & 0x1F) + 1)" % Rn]
            return op(lines, "shad" if arithmetic else "shld")
        return None
    if top == 0x8:
        sub = (insn >> 8) & 0xF
        target = (pc + 4 + _sx(d8, 8) * 2) & M32
        if sub == 0x0:
            return op(_tc_store(1, "(%s + %d) & %s" % (Rm, insn & 0xF, M), "R['r0']"),
                      "mov.b_r0_at_disp_m", True)
        if sub == 0x1:
            return op(_tc_store(2, "(%s + %d) & %s" % (Rm, (insn & 0xF) * 2, M), "R['r0']"),
                      "mov.w_r0_at_disp_m", True)
        if sub == 0x4:
            return op(_tc_load("R['r0']", 1, "(%s + %d) & %s" % (Rm, insn & 0xF, M), True),
                      "mov.b_at_disp_m_r0", True)
        if sub == 0x5:
            return op(_tc_load("R['r0']", 2, "(%s + %d) & %s" % (Rm, (insn & 0xF) * 2, M),
                               True), "mov.w_at_disp_m_r0", True)
        if sub == 0x8:
            return op(_tc_sett("R['r0'] == %d" % (_sx(d8, 8) & M32)), "cmp/eq_imm")
        if sub == 0x9:
            return ("cond", ("R['sr'] & 1", target), False, "bt")
        if sub == 0xB:
            return ("cond", ("not R['sr'] & 1", target), False, "bf")
        if sub == 0xD:
            return ("delay", ["tgt = %d if R['sr'] & 1 else %d"
                              % (target, (pc + 4) & M32)], False, "bt/s")
        if sub == 0xF:
            return ("delay", ["tgt = %d if not R['sr'] & 1 else %d"
                              % (target, (pc + 4) & M32)], False, "bf/s")
        return None
    if top == 0xC:
        sub = (insn >> 8) & 0xF
        if sub == 0x7:
            return op(["R['r0'] = %d" % (((pc + 4) & ~3) + d8 * 4)], "mova")
        if sub == 0x8:
            return op(_tc_sett("(R['r0'] & %d) == 0" % d8), "tst_imm")
        if sub == 0x9:
            return op(["R['r0'] &= %d" % d8], "and_imm")
        if sub == 0xA:
            return op(["R['r0'] ^= %d" % d8], "xor_imm")
        if sub == 0xB:
            return op(["R['r0'] |= %d" % d8], "or_imm")
        if sub in (0x0, 0x1, 0x2):
            size = (1, 2, 4)[sub]
            return op(_tc_store(size, "(R['gbr'] + %d) & %s" % (d8 * size, M), "R['r0']"),
                      ("mov.b_r0_gbr", "mov.w_r0_gbr", "mov.l_r0_gbr")[sub], True)
        if sub in (0x4, 0x5, 0x6):
            size = (1, 2, 4)[sub - 4]
            return op(_tc_load("R['r0']", size, "(R['gbr'] + %d) & %s" % (d8 * size, M),
                               size != 4),
                      ("mov.b_gbr_r0", "mov.w_gbr_r0", "mov.l_gbr_r0")[sub - 4], True)
        return None
    if top == 0x0:
        # The order of the checks is the order of ``_exec_misc``.
        if insn == 0x0009:
            return op([], "nop")
        if insn == 0x000B:
            return ("delay", ["tgt = R['pr']"], False, "rts")
        if insn == 0x0008:
            return op(["R['sr'] &= -2"], "clrt")
        if insn == 0x0018:
            return op(["R['sr'] |= 1"], "sett")
        if insn in (0x0028, 0x0019) or (insn & 0xF) == 0xF:
            return None
        pattern = insn & 0xF0FF
        if pattern in (0x0002, 0x0012, 0x0022, 0x000A, 0x001A, 0x002A):
            reg = {0x0002: "sr", 0x0012: "gbr", 0x0022: "vbr", 0x000A: "mach",
                   0x001A: "macl", 0x002A: "pr"}[pattern]
            arm = {0x0002: "stc_sr", 0x0012: "stc_gbr", 0x0022: "stc_vbr",
                   0x000A: "sts_mach", 0x001A: "sts_macl", 0x002A: "sts_pr"}[pattern]
            return op(["%s = R['%s']" % (Rn, reg)], arm)
        if pattern == 0x0029:
            return op(["%s = R['sr'] & 1" % Rn], "movt")
        if (insn & 0xF) == 0x7:
            return op(["R['macl'] = (%s * %s) & %s" % (Rn, Rm, M)], "mul.l")
        if pattern == 0x0003:
            return ("delay", ["v = %s" % Rn, "R['pr'] = %d" % ((pc + 4) & M32),
                              "tgt = (%d + v) & %s" % (pc + 4, M)], False, "bsrf")
        if pattern == 0x0023:
            return ("delay", ["tgt = (%d + %s) & %s" % (pc + 4, Rn, M)], False, "braf")
        if pattern in (0x0083, 0x0093, 0x00A3, 0x00B3):
            return op([], {0x0083: "pref", 0x0093: "ocbi", 0x00A3: "ocbp",
                           0x00B3: "ocbwb"}[pattern])
        if pattern == 0x00C3:
            return op(_tc_store(4, Rn, "R['r0']"), "movca.l", True)
        low = insn & 0xF
        if low in (0x4, 0x5, 0x6):
            size = (1, 2, 4)[low - 4]
            # mov.w Rm,@(R0,Rn) has no arm name in ``_exec_misc``: it keeps
            # the previous instruction's; None here means "leave _arm".
            arm = {0x4: "mov.b_m_at_r0_plus_n", 0x5: None,
                   0x6: "mov.l_m_at_r0_plus_n"}[low]
            return op(_tc_store(size, "(R['r0'] + %s) & %s" % (Rn, M), Rm), arm, True)
        if low in (0xC, 0xD, 0xE):
            size = (1, 2, 4)[low - 0xC]
            return op(_tc_load(Rn, size, "(R['r0'] + %s) & %s" % (Rm, M), size != 4),
                      None, True)
        return None
    return None


#: Templates are pure functions of (word, pc); blocks are rebuilt per engine.
_tc_insn_memo = functools.lru_cache(maxsize=1 << 17)(_tc_insn)


#: Interpreter methods a subclass or instance may override; any override
#: turns the fast path off for that engine (it would bypass the override).
_TC_METHODS = ("_step", "_execute", "_fetch", "_block", "_load", "_load_signed",
               "_store", "_record_watch", "_dispatch", "_get_pc", "_set_pc",
               "_get_reg", "_set_reg", "_set_t", "_t", "_exec_alu",
               "_exec_store", "_exec_load", "_exec_system", "_exec_branch8",
               "_exec_imm", "_exec_misc")


def _tc_build(eng, pc: int, barrier):
    """Translate the block at *pc*; ``None`` if its first instruction has no
    template (or cannot be fetched).  *barrier(va)* is true for a PC that
    ``run_until`` must see (stop, hook, ``RETURN_VA``): never inside a block."""
    items = []          # (pc, kind, lines, faults, arm)
    words = []
    cur = pc
    end_kind = None
    while len(items) < _TC_MAX:
        if items and barrier(cur):
            break
        try:
            insn = eng._tc_word(cur)
        except EngineError:
            break
        t = _tc_insn_memo(insn, cur)
        if t is None:
            break
        kind, lines, faults, arm = t
        if kind == "delay":
            slot = (cur + 2) & M32
            if barrier(slot):
                break
            try:
                slot_word = eng._tc_word(slot)
                slot_t = _tc_insn_memo(slot_word, slot)
            except EngineError:
                slot_t = None
            if slot_t is None or slot_t[0] != "op":
                break
            items.append((cur, kind, lines, faults, arm))
            items.append((slot, "slot", slot_t[1], slot_t[2], slot_t[3]))
            words.append(insn)
            words.append(slot_word)
            end_kind = "delay"
            break
        items.append((cur, kind, lines, faults, arm))
        words.append(insn)
        if kind == "cond":
            end_kind = "cond"
            break
        cur = (cur + 2) & M32
    if not items:
        return None
    key = (pc, tuple(words), end_kind)
    built = _TC_CODE_CACHE.get(key)
    if built is None:
        if len(_TC_CODE_CACHE) > 50000:
            _TC_CODE_CACHE.clear()
        built = _TC_CODE_CACHE[key] = _tc_codegen(pc, items, end_kind)
    code, pcs, arms, cells = built
    scope = {"_SMC": _SMC, "PCS": pcs, "ARMS": arms, "ENG": eng}
    scope.update(eng._tc_helpers())
    for k in range(cells):
        scope["C%d" % k] = [0, 0, b""]
    exec(code, scope)
    return scope["_blk"], len(items)


def _tc_codegen(pc, items, end_kind):
    """Source -> code object for one block; returns ``(code, PCS, ARMS,
    number of cache cells)``.  Pure function of the instruction words."""

    pcs, arms = [], []
    eff = None
    for item in items:
        if item[4] is not None:
            eff = item[4]
        pcs.append(item[0])
        arms.append(eff)
    body = []
    tgt_set = False
    for k, (ipc, kind, lines, faults, _arm) in enumerate(items):
        if faults:
            body.append("i = %d" % k)
        if kind == "cond":
            cond, target = lines
            body.append("npc = %d if (%s) else %d" % (target, cond, (ipc + 2) & M32))
            continue
        body.extend(lines)
        if kind == "delay":
            tgt_set = True
    if end_kind == "delay":
        body.append("npc = tgt")
    elif end_kind is None:
        body.append("npc = %d" % ((pcs[-1] + 2) & M32))
    # Registers live in locals for the block: loaded once before ``try``
    # (cannot fault), written back on every exit -- normal, _SMC and a
    # fault -- so R holds exactly what the per-instruction path would.
    text = "\n".join(body)
    used = sorted(set(re.findall(r"R\['(\w+)'\]", text)))
    written = sorted(set(re.findall(r"R\['(\w+)'\]\s*[&|^]?=(?!=)", text)))
    text = re.sub(r"R\['(\w+)'\]", r"L_\1", text)
    back = ["R['%s'] = L_%s" % (name, name) for name in written]
    src = ["def _blk(R):"]
    src += ["    L_%s = R['%s']" % (name, name) for name in used]
    src += ["    i = 0", "    try:"]
    src += ["        " + line for line in text.split("\n")]
    src.append("    except _SMC:")
    src += ["        " + line for line in back]
    # The store completed: continue after instruction i (a slot continues
    # at the branch target).
    if tgt_set:
        src.append("        R['pc'] = tgt if i == %d else (PCS[i] + 2) & 0xFFFFFFFF"
                   % (len(items) - 1))
    else:
        src.append("        R['pc'] = (PCS[i] + 2) & 0xFFFFFFFF")
    src.append("        return i + 1, ARMS[i]")
    src.append("    except BaseException:")
    src += ["        " + line for line in back]
    src.append("        R['pc'] = (PCS[i] + 2) & 0xFFFFFFFF")
    src.append("        if ARMS[i] is not None:")
    src.append("            ENG._arm = ARMS[i]")
    src.append("        raise")
    src += ["    " + line for line in back]
    src.append("    R['pc'] = npc")
    src.append("    return %d, %r" % (len(items), arms[-1]))
    text = "\n".join(src)
    cell = 0
    while "@C" in text:
        text = text.replace("@C", "C%d" % cell, 1)
        cell += 1
    code = compile(text, "<pysh4 block %s>" % px(pc), "exec")
    return code, tuple(pcs), tuple(arms), cell



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
      stack forms, ``clrt``/``sett``/``clrmac``;
    * divide step: ``div0s``/``div0u``/``div1`` with SR.M/SR.Q/T as in the
      SH-4 manual (M9.48).

    Not modelled, and raised as :class:`IllegalInstruction` rather than
    guessed: FPU (``0xF``), ``trapa``
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
        self._arm: str = ""
        self._insn_pc: int | None = None   # PC of the instruction executing now
        self._tc_cache: dict = {}          # block start -> (fn, count) | None (M9.45)
        self._tc_stops: frozenset = frozenset()
        self._tc_bar: set = set()          # PCs run_until must see (M9.45)

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
        self._tc_reset()

    def _read(self, va: int, size: int) -> bytes:
        block = self._block(va, size, "r")
        offset = va - block.region.va
        self._record_watch(va, size, "api-r")
        return bytes(block.data[offset:offset + size])

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
        value = int.from_bytes(block.data[offset:offset + size], self.endian)
        self._record_watch(va, size, "r")
        return value

    def _store(self, va: int, size: int, value: int) -> None:
        if va % size:
            raise UnalignedAccess(f"{size}-byte store at unaligned {px(va)}")
        block = self._block(va, size, "w")
        offset = va - block.region.va
        block.data[offset:offset + size] = (value & ((1 << (8 * size)) - 1)).to_bytes(
            size, self.endian
        )
        self._record_watch(va, size, "w")

    def _fetch(self) -> int:
        pc = self._regs["pc"]
        block = self._block(pc, 2, "x")
        offset = pc - block.region.va
        self._record_watch(pc, 2, "x")
        return int.from_bytes(block.data[offset:offset + 2], self.endian)

    # -- the interpreter ---------------------------------------------------

    def _set_t(self, condition: bool) -> None:
        if condition:
            self._regs["sr"] |= 1
        else:
            self._regs["sr"] &= ~1

    def _t(self) -> bool:
        return bool(self._regs["sr"] & 1)

    def _set_mq(self, mbit: int, q: int) -> None:
        """Write SR.M (bit 9) and SR.Q (bit 8); used only by div0s/div0u/div1."""
        sr = self._regs["sr"] & ~(SR_M | SR_Q)
        self._regs["sr"] = sr | (SR_M if mbit else 0) | (SR_Q if q else 0)

    def _step(self) -> None:
        pc = self._regs["pc"]
        insn = self._fetch()
        self._regs["pc"] = (pc + 2) & M32
        self._insn_pc = pc
        delayed = self._delay
        self._delay = None
        try:
            self._execute(insn, pc)
        finally:
            self._insn_pc = None
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
            self._arm = "mov_imm"
            regs["r%d" % n] = _sx(d8, 8) & M32
        elif top == 0x7:                                 # add #imm,Rn
            self._arm = "add_imm"
            regs["r%d" % n] = (regs["r%d" % n] + _sx(d8, 8)) & M32
        elif top == 0xD:                                 # mov.l @(disp,PC),Rn
            self._arm = "mov.l_pc"
            regs["r%d" % n] = self._load(((pc + 4) & ~3) + d8 * 4, 4)
        elif top == 0x9:                                 # mov.w @(disp,PC),Rn
            self._arm = "mov.w_pc"
            regs["r%d" % n] = self._load_signed(pc + 4 + d8 * 2, 2)
        elif top == 0xA:                                 # bra
            self._arm = "bra"
            self._delay = (pc + 4 + _sx(insn & 0xFFF, 12) * 2) & M32
        elif top == 0xB:                                 # bsr
            self._arm = "bsr"
            regs["pr"] = (pc + 4) & M32
            self._delay = (pc + 4 + _sx(insn & 0xFFF, 12) * 2) & M32
        elif top == 0x1:                                 # mov.l Rm,@(disp,Rn)
            self._arm = "mov.l_m_at_disp_n"
            self._store((regs["r%d" % n] + (insn & 0xF) * 4) & M32, 4, regs["r%d" % m])
        elif top == 0x5:                                 # mov.l @(disp,Rm),Rn
            self._arm = "mov.l_at_disp_m_n"
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
            self._arm = "cmp/eq"
            self._set_t(rn == rm)
        elif sub == 0x2:                                 # cmp/hs
            self._arm = "cmp/hs"
            self._set_t(rn >= rm)
        elif sub == 0x3:                                 # cmp/ge
            self._arm = "cmp/ge"
            self._set_t(_sx(rn, 32) >= _sx(rm, 32))
        elif sub == 0x6:                                 # cmp/hi
            self._arm = "cmp/hi"
            self._set_t(rn > rm)
        elif sub == 0x7:                                 # cmp/gt
            self._arm = "cmp/gt"
            self._set_t(_sx(rn, 32) > _sx(rm, 32))
        elif sub == 0x8:                                 # sub
            self._arm = "sub"
            regs["r%d" % n] = (rn - rm) & M32
        elif sub == 0xC:                                 # add
            self._arm = "add"
            regs["r%d" % n] = (rn + rm) & M32
        elif sub == 0xE:                                 # addc
            self._arm = "addc"
            total = rn + rm + (1 if self._t() else 0)
            regs["r%d" % n] = total & M32
            self._set_t(total > M32)
        elif sub == 0xA:                                 # subc
            self._arm = "subc"
            total = rn - rm - (1 if self._t() else 0)
            regs["r%d" % n] = total & M32
            self._set_t(total < 0)
        elif sub == 0xF:                                 # addv
            self._arm = "addv"
            a, b = _sx(rn, 32), _sx(rm, 32)
            total = a + b
            regs["r%d" % n] = total & M32
            self._set_t(total < -(1 << 31) or total > (1 << 31) - 1)
        elif sub == 0xB:                                 # subv
            self._arm = "subv"
            a, b = _sx(rn, 32), _sx(rm, 32)
            total = a - b
            regs["r%d" % n] = total & M32
            self._set_t(total < -(1 << 31) or total > (1 << 31) - 1)
        elif sub == 0xD:                                 # dmuls.l
            self._arm = "dmuls.l"
            product = _sx(rn, 32) * _sx(rm, 32) & M64
            regs["mach"] = (product >> 32) & M32
            regs["macl"] = product & M32
        elif sub == 0x5:                                 # dmulu.l
            self._arm = "dmulu.l"
            product = rn * rm & M64
            regs["mach"] = (product >> 32) & M32
            regs["macl"] = product & M32
        elif sub == 0x4:                                 # div1 Rm,Rn
            self._arm = "div1"
            regs["r%d" % n], q = _div1_step(rn, rm, self._t(),
                                            (regs["sr"] >> 8) & 1,
                                            (regs["sr"] >> 9) & 1)
            mbit = (regs["sr"] >> 9) & 1
            self._set_mq(mbit, q)
            self._set_t(q == mbit)
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
            self._arm = "mov.b_m_at_n"
            self._store(rn, 1, rm)
        elif sub == 0x1:                                 # mov.w Rm,@Rn
            self._arm = "mov.w_m_at_n"
            self._store(rn, 2, rm)
        elif sub == 0x2:                                 # mov.l Rm,@Rn
            self._arm = "mov.l_m_at_n"
            self._store(rn, 4, rm)
        elif sub == 0x4:                                 # mov.b Rm,@-Rn
            self._arm = "mov.b_m_at_minus_n"
            regs["r%d" % n] = (rn - 1) & M32
            self._store((rn - 1) & M32, 1, rm)
        elif sub == 0x5:                                 # mov.w Rm,@-Rn
            self._arm = "mov.w_m_at_minus_n"
            regs["r%d" % n] = (rn - 2) & M32
            self._store((rn - 2) & M32, 2, rm)
        elif sub == 0x6:                                 # mov.l Rm,@-Rn
            self._arm = "mov.l_m_at_minus_n"
            regs["r%d" % n] = (rn - 4) & M32
            self._store((rn - 4) & M32, 4, rm)
        elif sub == 0x7:                                 # div0s Rm,Rn
            # SH-4 manual: Q (SR bit 8) = Rn bit 31, M (SR bit 9) = Rm bit 31,
            # T = !(M == Q).  (M9.37 wrote bits 2/1 and cleared T; M9.48.)
            self._arm = "div0s"
            q = (rn >> 31) & 1
            mbit = (rm >> 31) & 1
            self._set_mq(mbit, q)
            self._set_t(mbit != q)
        elif sub == 0x8:                                 # tst
            self._arm = "tst"
            self._set_t((rn & rm) == 0)
        elif sub == 0x9:                                 # and
            self._arm = "and"
            regs["r%d" % n] = rn & rm
        elif sub == 0xA:                                 # xor
            self._arm = "xor"
            regs["r%d" % n] = rn ^ rm
        elif sub == 0xB:                                 # or
            self._arm = "or"
            regs["r%d" % n] = rn | rm
        elif sub == 0xC:                                 # cmp/str
            self._arm = "cmp/str"
            left = rn.to_bytes(4, "big")
            right = rm.to_bytes(4, "big")
            self._set_t(any(a == b for a, b in zip(left, right)))
        elif sub == 0xD:                                 # xtrct
            self._arm = "xtrct"
            combined = ((rm & 0xFFFF) << 16) | ((rn >> 16) & 0xFFFF)
            regs["r%d" % n] = combined & M32
        elif sub == 0xE:                                 # mulu.w
            self._arm = "mulu.w"
            regs["macl"] = ((rn & 0xFFFF) * (rm & 0xFFFF)) & M32
        elif sub == 0xF:                                 # muls.w
            self._arm = "muls.w"
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
            self._arm = "mov.b_at_m_n"
            regs["r%d" % n] = self._load_signed(rm, 1)
        elif sub == 0x1:                                 # mov.w @Rm,Rn
            self._arm = "mov.w_at_m_n"
            regs["r%d" % n] = self._load_signed(rm, 2)
        elif sub == 0x2:                                 # mov.l @Rm,Rn
            self._arm = "mov.l_at_m_n"
            regs["r%d" % n] = self._load(rm, 4)
        elif sub == 0x3:                                 # mov Rm,Rn
            self._arm = "mov_m_n"
            regs["r%d" % n] = rm
        elif sub == 0x4:                                 # mov.b @Rm+,Rn
            self._arm = "mov.b_at_m_plus_n"
            regs["r%d" % n] = self._load_signed(rm, 1)
            regs["r%d" % m] = (rm + 1) & M32
        elif sub == 0x5:                                 # mov.w @Rm+,Rn
            self._arm = "mov.w_at_m_plus_n"
            regs["r%d" % n] = self._load_signed(rm, 2)
            regs["r%d" % m] = (rm + 2) & M32
        elif sub == 0x6:                                 # mov.l @Rm+,Rn
            self._arm = "mov.l_at_m_plus_n"
            regs["r%d" % n] = self._load(rm, 4)
            regs["r%d" % m] = (rm + 4) & M32
        elif sub == 0x7:                                 # not
            self._arm = "not"
            regs["r%d" % n] = ~rm & M32
        elif sub == 0x8:                                 # swap.b
            self._arm = "swap.b"
            regs["r%d" % n] = ((rm & 0xFF00FF00) | ((rm & 0xFF) << 16)
                               | ((rm >> 16) & 0xFF)) & M32
        elif sub == 0x9:                                 # swap.w
            self._arm = "swap.w"
            regs["r%d" % n] = ((rm << 16) | (rm >> 16)) & M32
        elif sub == 0xA:                                 # negc
            self._arm = "negc"
            total = 0 - rm - (1 if self._t() else 0)
            regs["r%d" % n] = total & M32
            self._set_t(total < 0)
        elif sub == 0xB:                                 # neg
            self._arm = "neg"
            regs["r%d" % n] = (-rm) & M32
        elif sub == 0xC:                                 # extu.b
            self._arm = "extu.b"
            regs["r%d" % n] = rm & 0xFF
        elif sub == 0xD:                                 # extu.w
            self._arm = "extu.w"
            regs["r%d" % n] = rm & 0xFFFF
        elif sub == 0xE:                                 # exts.b
            self._arm = "exts.b"
            regs["r%d" % n] = _sx(rm, 8) & M32
        elif sub == 0xF:                                 # exts.w
            self._arm = "exts.w"
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
            self._arm = "shll"
            self._set_t(bool(rn & 0x80000000))
            regs["r%d" % n] = (rn << 1) & M32
        elif low == 0x01:                                # shlr
            self._arm = "shlr"
            self._set_t(bool(rn & 1))
            regs["r%d" % n] = rn >> 1
        elif low == 0x08:                                # shll2
            self._arm = "shll2"
            regs["r%d" % n] = (rn << 2) & M32
        elif low == 0x09:                                # shlr2
            self._arm = "shlr2"
            regs["r%d" % n] = rn >> 2
        elif low == 0x18:                                # shll8
            self._arm = "shll8"
            regs["r%d" % n] = (rn << 8) & M32
        elif low == 0x19:                                # shlr8
            self._arm = "shlr8"
            regs["r%d" % n] = rn >> 8
        elif low == 0x20:                                # shal
            self._arm = "shal"
            self._set_t(bool(rn & 0x80000000))
            regs["r%d" % n] = (rn << 1) & M32
        elif low == 0x21:                                # shar
            self._arm = "shar"
            self._set_t(bool(rn & 1))
            regs["r%d" % n] = ((rn >> 1) | (rn & 0x80000000)) & M32
        elif low == 0x24:                                # rotcl Rn
            # SH-4 manual ROTCL: T <- Rn[31], Rn <- Rn << 1 | old T (M9.50).
            self._arm = "rotcl"
            t_in = regs["sr"] & 1
            self._set_t(bool(rn & 0x80000000))
            regs["r%d" % n] = ((rn << 1) | t_in) & M32
        elif low == 0x25:                                # rotcr Rn
            # SH-4 manual ROTCR: T <- Rn[0], Rn <- old T << 31 | Rn >> 1.
            self._arm = "rotcr"
            t_in = regs["sr"] & 1
            self._set_t(bool(rn & 1))
            regs["r%d" % n] = (rn >> 1) | (t_in << 31)
        elif low == 0x28:                                # shll16
            self._arm = "shll16"
            regs["r%d" % n] = (rn << 16) & M32
        elif low == 0x29:                                # shlr16
            self._arm = "shlr16"
            regs["r%d" % n] = rn >> 16
        elif low == 0x10:                                # dt
            self._arm = "dt"
            value = (rn - 1) & M32
            regs["r%d" % n] = value
            self._set_t(value == 0)
        elif low == 0x11:                                # cmp/pz
            self._arm = "cmp/pz"
            self._set_t(_sx(rn, 32) >= 0)
        elif low == 0x15:                                # cmp/pl
            self._arm = "cmp/pl"
            self._set_t(_sx(rn, 32) > 0)
        elif low == 0x0B:                                # jsr @Rn
            self._arm = "jsr"
            regs["pr"] = (pc + 4) & M32
            self._delay = rn
        elif low == 0x2B:                                # jmp @Rn
            self._arm = "jmp"
            self._delay = rn
        elif low == 0x0E:                                # ldc Rn,SR
            self._arm = "ldc_sr"
            regs["sr"] = rn
        elif low == 0x1E:                                # ldc Rn,GBR
            self._arm = "ldc_gbr"
            regs["gbr"] = rn
        elif low == 0x2E:                                # ldc Rn,VBR
            self._arm = "ldc_vbr"
            regs["vbr"] = rn
        elif low == 0x0A:                                # lds Rn,MACH
            self._arm = "lds_mach"
            regs["mach"] = rn
        elif low == 0x1A:                                # lds Rn,MACL
            self._arm = "lds_macl"
            regs["macl"] = rn
        elif low == 0x2A:                                # lds Rn,PR
            self._arm = "lds_pr"
            regs["pr"] = rn
        elif low == 0x02:                                # sts.l MACH,@-Rn
            self._arm = "sts.l_mach_at_minus_n"
            regs["r%d" % n] = (rn - 4) & M32
            self._store((rn - 4) & M32, 4, regs["mach"])
        elif low == 0x12:                                # sts.l MACL,@-Rn
            self._arm = "sts.l_macl_at_minus_n"
            regs["r%d" % n] = (rn - 4) & M32
            self._store((rn - 4) & M32, 4, regs["macl"])
        elif low == 0x22:                                # sts.l PR,@-Rn
            self._arm = "sts.l_pr_at_minus_n"
            regs["r%d" % n] = (rn - 4) & M32
            self._store((rn - 4) & M32, 4, regs["pr"])
        elif low == 0x03:                                # stc.l SR,@-Rn
            self._arm = "stc.l_sr_at_minus_n"
            regs["r%d" % n] = (rn - 4) & M32
            self._store((rn - 4) & M32, 4, regs["sr"])
        elif low == 0x13:                                # stc.l GBR,@-Rn
            self._arm = "stc.l_gbr_at_minus_n"
            regs["r%d" % n] = (rn - 4) & M32
            self._store((rn - 4) & M32, 4, regs["gbr"])
        elif low == 0x23:                                # stc.l VBR,@-Rn
            self._arm = "stc.l_vbr_at_minus_n"
            regs["r%d" % n] = (rn - 4) & M32
            self._store((rn - 4) & M32, 4, regs["vbr"])
        # ``lds.l @Rn+,...``/``ldc.l @Rn+,...`` keep the post-increment
        # register in the n field (0100 nnnn xxxx 011x), not in the m field
        # that the other system forms use as part of the opcode.
        elif low == 0x06:                                # lds.l @Rn+,MACH
            self._arm = "lds.l_mach_at_n_plus"
            regs["mach"] = self._load(rn, 4)
            regs["r%d" % n] = (rn + 4) & M32
        elif low == 0x16:                                # lds.l @Rn+,MACL
            self._arm = "lds.l_macl_at_n_plus"
            regs["macl"] = self._load(rn, 4)
            regs["r%d" % n] = (rn + 4) & M32
        elif low == 0x26:                                # lds.l @Rn+,PR
            self._arm = "lds.l_pr_at_n_plus"
            regs["pr"] = self._load(rn, 4)
            regs["r%d" % n] = (rn + 4) & M32
        elif low == 0x07:                                # ldc.l @Rn+,SR
            self._arm = "ldc.l_sr_at_n_plus"
            regs["sr"] = self._load(rn, 4)
            regs["r%d" % n] = (rn + 4) & M32
        elif low == 0x17:                                # ldc.l @Rn+,GBR
            self._arm = "ldc.l_gbr_at_n_plus"
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
            self._arm = "shad" if (insn & 0xF) == 0x0C else "shld"
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
        elif insn & 0xF == 0xF:                          # mac.w @Rm+,@Rn+
            # SH-4 manual MACW: tempn = Read_Word(R[n]); R[n] += 2;
            # tempm = Read_Word(R[m]); R[m] += 2.  Rm is bits 7-4 (M9.49: the
            # arm read an undefined ``rm`` and raised a host NameError).  With
            # n == m the second word is read at Rn+2 and Rn ends +4.  Both
            # loads happen before any register is written, so a fault leaves
            # the registers as they were (precise exception).
            # S = 0: the signed product is added to the 64-bit MACH:MACL.
            # S = 1: it is added to MACL alone, saturating at 32 bits; MACH is
            # not changed (the manual's C code).
            self._arm = "mac.w"
            rm = regs["r%d" % m]
            # ``_load_signed`` returns the register image (& M32); the
            # product needs the signed 16-bit value.
            left = _sx(self._load(rn, 2), 16)
            right = _sx(self._load((rn + 2) & M32 if n == m else rm, 2), 16)
            product = left * right
            if regs["sr"] & 0x2:
                total = _sx(regs["macl"], 32) + product
                if total > 0x7FFFFFFF:
                    total = 0x7FFFFFFF
                elif total < -0x80000000:
                    total = -0x80000000
                regs["macl"] = total & M32
            else:
                mac = ((regs["mach"] << 32) | regs["macl"])
                mac = (mac + product) & M64
                regs["mach"] = (mac >> 32) & M32
                regs["macl"] = mac & M32
            if n == m:
                regs["r%d" % n] = (rn + 4) & M32
            else:
                regs["r%d" % n] = (rn + 2) & M32
                regs["r%d" % m] = (rm + 2) & M32
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
            self._arm = "mov.b_r0_at_disp_m"
            # Rn is bits 7-4 here (H51: the store used r0 as the base before)
            self._store((regs["r%d" % m] + (insn & 0xF)) & M32, 1, regs["r0"])
        elif sub == 0x1:                                 # mov.w R0,@(disp,Rn)
            self._arm = "mov.w_r0_at_disp_m"
            self._store((regs["r%d" % m] + (insn & 0xF) * 2) & M32, 2, regs["r0"])
        elif sub == 0x4:                                 # mov.b @(disp,Rm),R0
            self._arm = "mov.b_at_disp_m_r0"
            regs["r0"] = self._load_signed((regs["r%d" % m] + (insn & 0xF)) & M32, 1)
        elif sub == 0x5:                                 # mov.w @(disp,Rm),R0
            self._arm = "mov.w_at_disp_m_r0"
            regs["r0"] = self._load_signed((regs["r%d" % m] + (insn & 0xF) * 2) & M32, 2)
        elif sub == 0x8:                                 # cmp/eq #imm,R0
            self._arm = "cmp/eq_imm"
            self._set_t((regs["r0"] & M32) == (_sx(insn & 0xFF, 8) & M32))
        elif sub == 0x9:                                 # bt
            self._arm = "bt"
            if self._t():
                regs["pc"] = target
        elif sub == 0xB:                                 # bf
            self._arm = "bf"
            if not self._t():
                regs["pc"] = target
        elif sub == 0xD:                                 # bt/s
            self._arm = "bt/s"
            if self._t():
                self._delay = target
        elif sub == 0xF:                                 # bf/s
            self._arm = "bf/s"
            if not self._t():
                self._delay = target
        else:
            raise IllegalInstruction(f"opcode {px(insn)} at {px(pc)} is not modelled")

    def _exec_imm(self, insn: int, n: int, d8: int) -> None:
        regs = self._regs
        top = (insn >> 8) & 0xF
        gbr = regs["gbr"]

        if top == 0x0:                                   # mov.b R0,@(disp,GBR)
            self._arm = "mov.b_r0_gbr"
            self._store((gbr + d8) & M32, 1, regs["r0"])
        elif top == 0x1:                                 # mov.w R0,@(disp,GBR)
            self._arm = "mov.w_r0_gbr"
            self._store((gbr + d8 * 2) & M32, 2, regs["r0"])
        elif top == 0x2:                                 # mov.l R0,@(disp,GBR)
            self._arm = "mov.l_r0_gbr"
            self._store((gbr + d8 * 4) & M32, 4, regs["r0"])
        elif top == 0x3:                                 # trapa #imm
            self._arm = "trapa"
            raise Trap(
                f"trapa #{d8} at {px(regs['pc'] - 2)}: WinCE system call; "
                "register a host stub with on_exec() instead of emulating it"
            )
        elif top == 0x4:                                 # mov.b @(disp,GBR),R0
            self._arm = "mov.b_gbr_r0"
            regs["r0"] = self._load_signed((gbr + d8) & M32, 1)
        elif top == 0x5:                                 # mov.w @(disp,GBR),R0
            self._arm = "mov.w_gbr_r0"
            regs["r0"] = self._load_signed((gbr + d8 * 2) & M32, 2)
        elif top == 0x6:                                 # mov.l @(disp,GBR),R0
            self._arm = "mov.l_gbr_r0"
            regs["r0"] = self._load((gbr + d8 * 4) & M32, 4)
        elif top == 0x7:                                 # mova @(disp,PC),R0
            self._arm = "mova"
            regs["r0"] = ((regs["pc"] - 2 + 4) & ~3) + d8 * 4
        elif top == 0x8:                                 # tst #imm,R0
            self._arm = "tst_imm"
            self._set_t((regs["r0"] & d8) == 0)
        elif top == 0x9:                                 # and #imm,R0
            self._arm = "and_imm"
            regs["r0"] &= d8
        elif top == 0xA:                                 # xor #imm,R0
            self._arm = "xor_imm"
            regs["r0"] ^= d8
        elif top == 0xB:                                 # or #imm,R0
            self._arm = "or_imm"
            regs["r0"] |= d8
        elif top == 0xC:                                 # tst.b #imm,@(R0,GBR)
            self._arm = "tst.b_imm"
            self._set_t((self._load((gbr + regs["r0"]) & M32, 1) & d8) == 0)
        elif top == 0xD:                                 # and.b #imm,@(R0,GBR)
            self._arm = "and.b_imm"
            address = (gbr + regs["r0"]) & M32
            self._store(address, 1, self._load(address, 1) & d8)
        elif top == 0xE:                                 # xor.b #imm,@(R0,GBR)
            self._arm = "xor.b_imm"
            address = (gbr + regs["r0"]) & M32
            self._store(address, 1, self._load(address, 1) ^ d8)
        elif top == 0xF:                                 # or.b #imm,@(R0,GBR)
            self._arm = "or.b_imm"
            address = (gbr + regs["r0"]) & M32
            self._store(address, 1, self._load(address, 1) | d8)
        else:  # pragma: no cover - top is a nibble
            raise IllegalInstruction(f"opcode {px(insn)} is not modelled")

    def _exec_misc(self, insn: int, n: int, m: int, pc: int) -> None:
        regs = self._regs
        pattern = insn & 0xF0FF
        rn = regs["r%d" % n]
        rm = regs["r%d" % m]

        if insn == 0x0009:                               # nop
            self._arm = "nop"
            return
        if insn == 0x000B:                               # rts
            self._arm = "rts"
            self._delay = regs["pr"]
            return
        if insn == 0x0008:                               # clrt
            self._arm = "clrt"
            self._set_t(False)
            return
        if insn == 0x0018:                               # sett
            self._arm = "sett"
            self._set_t(True)
            return
        if insn == 0x0028:                               # clrmac
            self._arm = "clrmac"
            regs["mach"] = 0
            regs["macl"] = 0
            return
        if insn == 0x0019:                               # div0u
            # SH-4 manual: M = Q = T = 0.
            self._arm = "div0u"
            self._set_mq(0, 0)
            self._set_t(False)
            return
        if (insn & 0xF) == 0xF:                          # mac.l @Rm+,@Rn+
            # SH-4 manual MACL: tempn = Read_Long(R[n]); R[n] += 4;
            # tempm = Read_Long(R[m]); R[m] += 4; MACH:MACL += tempn * tempm
            # (signed 32 x 32).  Until M9.51 this arm multiplied the register
            # values (a "mac.l Rm,Rn" form the SH-4 does not have).  With
            # n == m the second long is read at Rn+4 and Rn ends +8.  S = 1
            # (SR bit 1) saturates the 64-bit sum to 48 bits (MACH
            # 0xFFFF8000..0x00007FFF), as the manual's code does.  Both loads
            # happen before any register write (precise exception).
            # The M9.45 fast path has no template for this form: ``_step``
            # runs it.
            self._arm = "mac.l"
            left = _sx(self._load(rn, 4), 32)
            right = _sx(self._load((rn + 4) & M32 if n == m else rm, 4), 32)
            mac = ((regs["mach"] << 32) | regs["macl"])
            mac = (mac + left * right) & M64
            if regs["sr"] & 0x2:
                signed = mac - (1 << 64) if mac & (1 << 63) else mac
                if signed > 0x00007FFFFFFFFFFF:
                    mac = 0x00007FFFFFFFFFFF
                elif signed < -0x0000800000000000:
                    mac = 0xFFFF800000000000
            regs["mach"] = (mac >> 32) & M32
            regs["macl"] = mac & M32
            if n == m:
                regs["r%d" % n] = (rn + 8) & M32
            else:
                regs["r%d" % n] = (rn + 4) & M32
                regs["r%d" % m] = (rm + 4) & M32
            return
        if pattern == 0x0002:                            # stc SR,Rn
            self._arm = "stc_sr"
            regs["r%d" % n] = regs["sr"]
        elif pattern == 0x0012:                          # stc GBR,Rn
            self._arm = "stc_gbr"
            regs["r%d" % n] = regs["gbr"]
        elif pattern == 0x0022:                          # stc VBR,Rn
            self._arm = "stc_vbr"
            regs["r%d" % n] = regs["vbr"]
        elif pattern == 0x000A:                          # sts MACH,Rn
            self._arm = "sts_mach"
            regs["r%d" % n] = regs["mach"]
        elif pattern == 0x001A:                          # sts MACL,Rn
            self._arm = "sts_macl"
            regs["r%d" % n] = regs["macl"]
        elif pattern == 0x002A:                          # sts PR,Rn
            self._arm = "sts_pr"
            regs["r%d" % n] = regs["pr"]
        elif pattern == 0x0029:                          # movt Rn
            self._arm = "movt"
            regs["r%d" % n] = 1 if self._t() else 0
        elif (insn & 0xF) == 0x7:                        # mul.l Rm,Rn (any Rm, H51)
            self._arm = "mul.l"
            regs["macl"] = (rn * rm) & M32
        elif pattern == 0x0003:                          # bsrf Rn (0000 nnnn 0000 0011)
            self._arm = "bsrf"
            regs["pr"] = (pc + 4) & M32
            self._delay = (pc + 4 + rn) & M32
        elif pattern == 0x0023:                          # braf Rn (0000 nnnn 0010 0011)
            self._arm = "braf"
            # The register is the n field, not m: the m nibble is opcode space
            # here.  Using m sent zlib's inflate jump table to pc+4+Rm (M9.11).
            self._delay = (pc + 4 + rn) & M32
        elif pattern in (0x0083, 0x0093, 0x00A3, 0x00B3):
            # pref @Rn, ocbi/ocbp/ocbwb @Rn: cache hints with no architectural
            # effect, so a functional emulator ignores them on purpose.
            self._arm = {0x0083: "pref", 0x0093: "ocbi",
                         0x00A3: "ocbp", 0x00B3: "ocbwb"}[pattern]
            return
        elif pattern == 0x00C3:                          # movca.l R0,@Rn (plain store)
            self._arm = "movca.l"
            self._store(rn, 4, regs["r0"])
        elif (insn & 0xF) == 0x4:                        # mov.b Rm,@(R0,Rn)
            self._arm = "mov.b_m_at_r0_plus_n"
            self._store((regs["r0"] + rn) & M32, 1, rm)
        elif (insn & 0xF) == 0x5:                        # mov.w Rm,@(R0,Rn)
            self._store((regs["r0"] + rn) & M32, 2, rm)
        elif (insn & 0xF) == 0x6:                        # mov.l Rm,@(R0,Rn)
            self._arm = "mov.l_m_at_r0_plus_n"
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

    # -- fast path (M9.45) -------------------------------------------------

    def _tc_word(self, pc: int) -> int:
        """Instruction fetch for the translator: same checks as ``_fetch``."""
        block = self._block(pc, 2, "x")
        offset = pc - block.region.va
        return int.from_bytes(block.data[offset:offset + 2], self.endian)

    def _tc_eligible(self) -> bool:
        cls = type(self)
        for name in _TC_METHODS:
            if name in self.__dict__ or getattr(cls, name) is not _PYSH4_IMPL[name]:
                return False
        return True

    def _tc_reset(self) -> None:
        """Drop every translated block (code bytes, hooks or the map
        changed).  Cleared in place: a running loop holds the dict."""
        self._tc_cache.clear()

    def _tc_helpers(self) -> dict:
        """Names the translated blocks use: struct accessors for this
        endianness, and ``LDM``/``STM``, the cache-miss paths.  A miss runs
        ``_load``/``_store`` (so an unmapped, unaligned or forbidden access
        raises exactly as in ``_step``) and then points the site's cell at
        the region that served it.  A store into an executable region drops
        every block and raises ``_SMC`` so the block ends after it."""
        helpers = self.__dict__.get("_tc_helpers_cache")
        if helpers is not None:
            return helpers
        eng = self
        little = self.endian == "little"
        s2 = struct.Struct("<H" if little else ">H")
        s4 = struct.Struct("<I" if little else ">I")

        def ldm(a, size, cell):
            value = eng._load(a, size)
            block = eng._block(a, size, "r")
            cell[0] = block.region.va
            cell[1] = block.region.va + block.region.size
            cell[2] = block.data
            return value

        def stm(a, size, value, cell):
            eng._store(a, size, value)
            block = eng._block(a, size, "w")
            if "x" in block.region.rwx:
                eng._tc_reset()
                raise _SMC()
            cell[0] = block.region.va
            cell[1] = block.region.va + block.region.size
            cell[2] = block.data

        helpers = {"U2": s2.unpack_from, "U4": s4.unpack_from,
                   "P2": s2.pack_into, "P4": s4.pack_into,
                   "LDM": ldm, "STM": stm}
        self.__dict__["_tc_helpers_cache"] = helpers
        return helpers

    def on_exec(self, va: int, handler: Callable) -> None:
        super().on_exec(va, handler)
        self._tc_bar.add(va & M32)
        self._tc_reset()

    def _write(self, va: int, data: bytes) -> None:
        block = self._block(va, len(data), "w")
        offset = va - block.region.va
        block.data[offset:offset + len(data)] = data
        self._record_watch(va, len(data), "api-w")
        if "x" in block.region.rwx:
            self._tc_reset()

    def run_until(self, stop=None, max_insns: int = DEFAULT_MAX_INSNS) -> RunResult:
        """:meth:`Backend.run_until` with translated blocks (M9.45).

        Same results, same exceptions, same instruction count; see the
        fast-path notes above ``_TC_METHODS``.  Falls back to the base loop
        for a callable *stop* and for engines that override the interpreter.
        """
        if (callable(stop) or not self._tc_eligible()
                or not isinstance(max_insns, int) or max_insns <= 0):
            return super().run_until(stop, max_insns)
        if stop is None:
            stops = frozenset()
        elif isinstance(stop, int):
            stops = frozenset((stop & M32,))
        else:
            try:
                stops = frozenset(int(item) & M32 for item in stop)
            except TypeError:
                return super().run_until(stop, max_insns)
        if stops != self._tc_stops:
            self._tc_reset()
            self._tc_stops = stops
        hooks = self._hooks
        bar = self._tc_bar = {RETURN_VA} | set(stops) | set(hooks)
        barrier = bar.__contains__
        cache = self._tc_cache
        regs = self._regs
        insns = 0
        stubs: list[dict] = []
        # ``fast`` is re-derived after every ``_step`` and every hook call --
        # the only places a delay slot can become pending or a watch armed.
        fast = self._delay is None and not self._watches_on
        while True:
            pc = regs["pc"] & M32
            if pc in bar:
                if pc == RETURN_VA:
                    result = RunResult(insns=insns, pc=pc, reason="return", stubs=stubs)
                    self.last_run = result
                    return result
                if pc in stops:
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
                    fast = self._delay is None and not self._watches_on
                    continue
                fast = self._delay is None and not self._watches_on
            if insns >= max_insns:
                raise Runaway(
                    f"run_until(): more than {max_insns} instructions without reaching "
                    f"{px(RETURN_VA)} or a stop address; last pc {px(pc)} (infinite loop?)"
                )
            if fast:
                entry = cache.get(pc)
                if entry is None and pc not in cache:
                    entry = cache[pc] = _tc_build(self, pc, barrier)
                if entry is not None and insns + entry[1] <= max_insns:
                    done, arm = entry[0](regs)
                    if arm is not None:
                        self._arm = arm
                    insns += done
                    continue
            self._step()
            insns += 1
            fast = self._delay is None and not self._watches_on


_PYSH4_IMPL = {name: getattr(PySh4, name) for name in _TC_METHODS}

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
#: ``--full`` runs every check, including external-backend parity that may be
#: slow or need a working Ghidra/QEMU adapter.  The default (quick) keeps the
#: PySh4/reference checks and SKIPs external execution with an honest reason so
#: main loops stay bounded (M1.18).  A SKIP is never a PASS.
FULL_SELFTEST = False


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


@check("pysh4: mov.b/mov.w R0,@(disp,Rn) base is Rn; mul.l any Rm; movca.l (H51)")
def test_h51_store_r0_disp_and_mul():
    base = 0x8C100000
    engine = PySh4(endian="little")
    engine.map("d", base, bytearray(0x40), "rw")
    # r0 holds the value AND would be a wild pointer if used as the base.
    engine.set_regs(r0=0xFFFFFF84, r14=base)
    engine._execute(0x80E8, 0x8C000000)              # mov.b r0,@(8,r14)
    _expect_equal(bytes(engine.read_mem(base + 8, 1)), b"\x84", "mov.b r0,@(8,r14)")
    engine.set_regs(r0=0x1234ABCD)
    engine._execute(0x81E3, 0x8C000000)              # mov.w r0,@(6,r14)
    _expect_equal(bytes(engine.read_mem(base + 6, 2)), b"\xcd\xab", "mov.w r0,@(6,r14)")
    engine.set_regs(r13=7, r6=3)
    engine._execute(0x0D67, 0x8C000000)              # mul.l r6,r13 (Rm != r0)
    _expect_equal(engine._get_reg("macl"), 21, "mul.l r6,r13")
    engine.set_regs(r0=0xCAFEF00D, r4=base + 0x10)
    engine._execute(0x04C3, 0x8C000000)              # movca.l r0,@r4
    _expect_equal(bytes(engine.read_mem(base + 0x10, 4)), b"\x0d\xf0\xfe\xca", "movca.l r0,@r4")


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


@check("pysh4: distinct registers -- every modelled form, no operand hiding")
def test_distinct_register_forms():
    """One row per modelled form, with ``Rn``, ``Rm`` and ``R0`` distinct.

    Values are chosen so a register mix-up *and* an ``n == 0``/``m == 0``
    hiding trick both change the result -- the three pre-M9.37 defects
    survived because the old tests used zero operands.  Each row's opcode is
    also decoded independently by ``decode_fields`` and must name the same
    form and the same ``(n, m)`` register fields the row expects, so the
    table is checked against the manual encoding, not against the executor.
    """
    D = 0x8C100000
    N, M = 11, 5
    VN, VM, V0 = 0x00001234, 0x00000102, 0x00005678
    M32 = 0xFFFFFFFF

    def rr(top, sub, n, m):
        return (top << 12) | (n << 8) | (m << 4) | sub

    def fresh(**extra):
        e = PySh4(endian="big")
        e.map("mem", D, bytearray(0x600), "rw")
        e.map("code", 0x8C000000, 4, "rwx")
        base = {"r0": V0, "r%d" % N: VN, "r%d" % M: VM,
                "r15": D + 0x400, "pc": 0x8C000000, "mach": 0, "macl": 0, "sr": 0}
        base.update(extra)
        e.set_regs(**base)
        return e

    rows = [
        ("sub", rr(0x3, 0x8, N, M), (N, M), {"r%d" % N: (VN - VM) & M32}, []),
        ("add", rr(0x3, 0xC, N, M), (N, M), {"r%d" % N: (VN + VM) & M32}, []),
        ("and", rr(0x2, 0x9, N, M), (N, M), {"r%d" % N: VN & VM}, []),
        ("xor", rr(0x2, 0xA, N, M), (N, M), {"r%d" % N: VN ^ VM}, []),
        ("or", rr(0x2, 0xB, N, M), (N, M), {"r%d" % N: VN | VM}, []),
        ("mulu.w", rr(0x2, 0xE, N, M), (N, M),
         {"macl": (VN & 0xFFFF) * (VM & 0xFFFF) & M32}, []),
        ("mov", rr(0x6, 0x3, N, M), (N, M), {"r%d" % N: VM}, []),
        ("not", rr(0x6, 0x7, N, M), (N, M), {"r%d" % N: ~VM & M32}, []),
        ("extu.b", rr(0x6, 0xC, N, M), (N, M), {"r%d" % N: VM & 0xFF}, []),
        ("exts.b", rr(0x6, 0xE, N, M), (N, M), {"r%d" % N: _sx(VM, 8) & M32}, []),
        ("neg", rr(0x6, 0xB, N, M), (N, M), {"r%d" % N: (-VM) & M32}, []),
        ("shld", rr(0x4, 0xD, N, M), (N, M),
         {"r%d" % N: (VN << (VM & 31)) & M32}, []),
        ("mul.l", rr(0x0, 0x7, N, M), (N, M),
         {"macl": (VN * VM) & M32, "mach": 0}, []),
        # mac.l @Rm+,@Rn+ (M9.51): longs 0x00010000 at @Rn and 0xFFFFFFFE (-2)
        # at @Rm; MACH:MACL preset to 0x1_00010000 so the add borrows from
        # MACH.  The register values are not multiplied.
        ("mac.l", rr(0x0, 0xF, N, M), (N, M),
         {"mach": 0x0, "macl": 0xFFFF0000,
          "r%d" % N: D + 0x84, "r%d" % M: D + 0x94},
         [(D + 0x80, b"\x00\x01\x00\x00"), (D + 0x90, b"\xff\xff\xff\xfe")],
         {"r%d" % N: D + 0x80, "r%d" % M: D + 0x90,
          "mach": 0x1, "macl": 0x00010000}),
        ("div0s", rr(0x2, 0x7, N, M), (N, M), {"sr": 0}, []),
        # div1 from Q=M=T=0: Rn = (VN<<1) - VM = 0x2366, no borrow -> Q=0, T=1.
        ("div1", rr(0x3, 0x4, N, M), (N, M),
         {"r%d" % N: ((VN << 1) - VM) & M32, "sr": 0x001}, []),
        # rotcl/rotcr Rn (M9.50): T in = 1, so the carried-in bit shows; the
        # bit shifted out (VN[31] = 0, VN[0] = 0) lands in T.
        ("rotcl", rr(0x4, 0x4, N, 0x2), (N, None),
         {"r%d" % N: ((VN << 1) | 1) & M32, "sr": 0x0}, [], {"sr": 0x1}),
        ("rotcr", rr(0x4, 0x5, N, 0x2), (N, None),
         {"r%d" % N: (VN >> 1) | 0x80000000, "sr": 0x0}, [], {"sr": 0x1}),
        # mac.w @Rm+,@Rn+ (M9.49): words 0x1234 at @Rn and 0xFF02 (-254) at
        # @Rm, MACH:MACL preset so the 64-bit add carries into MACH.
        ("mac.w", rr(0x4, 0xF, N, M), (N, M),
         {"macl": (0xFFFFFFF0 + 0x1234 * -254) & M32,
          "mach": ((0x1_FFFFFFF0 + 0x1234 * -254) >> 32) & M32,
          "r%d" % N: D + 0x22, "r%d" % M: D + 0x32},
         [(D + 0x20, b"\x12\x34"), (D + 0x30, b"\xff\x02")],
         {"r%d" % N: D + 0x20, "r%d" % M: D + 0x30,
          "mach": 0x1, "macl": 0xFFFFFFF0}),
        ("mov.l Rm,@(R0,Rn)", rr(0x0, 0x6, N, M), (N, M), {},
         [(D + 0x110, VM.to_bytes(4, "big"))],
         {"r0": D + 0x10, "r%d" % N: 0x100}),
        ("mov.l Rm,@-Rn", rr(0x2, 0x6, N, M), (N, M),
         {"r%d" % N: (D + 0x200 - 4) & M32},
         [((D + 0x200 - 4) & M32, VM.to_bytes(4, "big"))],
         {"r%d" % N: D + 0x200}),
    ]

    for row in rows:
        label, opcode, (rn, rm), expect_regs, expect_mem = row[:5]
        setup = row[5] if len(row) > 5 else {}
        engine = fresh(**setup)
        for address, data in expect_mem:
            engine.write_mem(address, data)
        engine._execute(opcode, 0x8C000000)
        form, trn, trm, _d = decode_fields(opcode)
        _expect_equal(engine._arm, form, f"{label}: executor arm vs decode table")
        _expect_equal((trn, trm), (rn, rm),
                      f"{label}: decode_fields register fields")
        snap = engine.get_regs()
        for name, value in expect_regs.items():
            _expect_equal(snap[name], value, f"{label}: {name}")
        for address, data in expect_mem:
            _expect_equal(bytes(engine.read_mem(address, len(data))), data,
                          f"{label}: memory at {px(address)}")

    # div0s (SH-4 manual): Q (SR bit 8) = Rn[31], M (SR bit 9) = Rm[31],
    # T = !(M == Q); other SR bits untouched.  M9.37 had bits 2/1 and T=0.
    for rn_v, rm_v, want in ((0, 0, 0x000), (0x80000000, 0, 0x101),
                             (0, 0x80000000, 0x201),
                             (0x80000000, 0x80000000, 0x300)):
        e = fresh()
        e.set_regs(**{"r%d" % N: rn_v, "r%d" % M: rm_v, "sr": 0x40000006})
        e._execute(rr(0x2, 0x7, N, M), 0x8C000000)
        _expect_equal(e.get_regs()["sr"], 0x40000006 | want,
                      f"div0s M/Q/T from Rn={px(rn_v)} Rm={px(rm_v)}")
    # div0u clears M, Q and T only.
    e = fresh(sr=0x40000301)
    e._execute(0x0019, 0x8C000000)
    _expect_equal(e._arm, "div0u", "div0u arm")
    _expect_equal(e.get_regs()["sr"], 0x40000000, "div0u clears M/Q/T only")
    # div0s;div1 Rm,Rn, one control per sign case (hand-computed from the
    # manual's DIV1 C code).  Every row but ++ differs if M/Q are ignored
    # (always "shift, subtract, Q=borrow").
    for rn_v, rm_v, want_rn, want_sr in (
            (0x00000010, 0x00000003, 0x0000001D, 0x001),   # + / +
            (0x00000010, 0xFFFFFFFD, 0x0000001E, 0x200),   # + / -
            (0xFFFFFFF0, 0x00000003, 0xFFFFFFE4, 0x100),   # - / +
            (0xFFFFFFF0, 0xFFFFFFFD, 0xFFFFFFE3, 0x301)):  # - / -
        e = fresh()
        e.set_regs(**{"r%d" % N: rn_v, "r%d" % M: rm_v, "sr": 0})
        e._execute(rr(0x2, 0x7, N, M), 0x8C000000)       # div0s Rm,Rn
        e._execute(rr(0x3, 0x4, N, M), 0x8C000000)       # div1 Rm,Rn
        snap = e.get_regs()
        _expect_equal(snap["r%d" % N], want_rn,
                      f"div0s;div1 Rn from Rn={px(rn_v)} Rm={px(rm_v)}")
        _expect_equal(snap["sr"], want_sr,
                      f"div0s;div1 M/Q/T from Rn={px(rn_v)} Rm={px(rm_v)}")
    # div1 Rn,Rn reads Rm before the shift (manual: tmp2 = R[m] first).
    e = fresh()
    e.set_regs(**{"r%d" % N: 0x00000005, "sr": 0})
    e._execute(rr(0x3, 0x4, N, N), 0x8C000000)
    _expect_equal(e.get_regs()["r%d" % N], 0x00000005, "div1 Rn,Rn: (5<<1)-5")

    # rotcl/rotcr with T in = 0 and the outgoing bit set: T out = 1, the
    # vacated bit is 0, other SR bits kept.
    for word, rn_v, want in ((rr(0x4, 0x4, N, 0x2), 0x80000001, 0x00000002),
                             (rr(0x4, 0x5, N, 0x2), 0x80000001, 0x40000000)):
        e = fresh(sr=0x40000300, **{"r%d" % N: rn_v})
        e._execute(word, 0x8C000000)
        snap = e.get_regs()
        _expect_equal((snap["r%d" % N], snap["sr"]), (want, 0x40000301),
                      f"{e._arm} Rn={px(rn_v)} T=0")

    # mac.l with n == m: the second long is read at Rn+4 and Rn ends +8.
    e = fresh(**{"r%d" % N: D + 0xA0})
    e.write_mem(D + 0xA0, b"\x00\x00\x00\x03\xff\xff\xff\xf9")
    e._execute(rr(0x0, 0xF, N, N), 0x8C000000)
    snap = e.get_regs()
    _expect_equal((snap["mach"], snap["macl"], snap["r%d" % N]),
                  (0xFFFFFFFF, (-21) & M32, D + 0xA8), "mac.l @Rn+,@Rn+: 3*-7 and Rn+8")
    # mac.l with S = 1: the 64-bit sum saturates to 48 bits.
    for mach, macl, a, b, want in (
            (0x00007FFF, 0xFFFFFFF0, 0x00000010, 0x00000010, (0x00007FFF, 0xFFFFFFFF)),
            (0xFFFF8000, 0x00000010, 0x80000000, 0x7FFFFFFF, (0xFFFF8000, 0x00000000)),
            (0x00000000, 0x00000010, 0xFFFFFFFF, 0x00000002, (0x00000000, 0x0000000E)),
            (0x00010000, 0x00000000, 0x00000001, 0x00000001, (0x00007FFF, 0xFFFFFFFF))):
        e = fresh(sr=0x2, mach=mach, macl=macl,
                  **{"r%d" % N: D + 0xB0, "r%d" % M: D + 0xC0})
        e.write_mem(D + 0xB0, a.to_bytes(4, "big"))
        e.write_mem(D + 0xC0, b.to_bytes(4, "big"))
        e._execute(rr(0x0, 0xF, N, M), 0x8C000000)
        snap = e.get_regs()
        _expect_equal((snap["mach"], snap["macl"]), want,
                      f"mac.l S=1 MAC={px(mach)}:{px(macl)} {px(a)}*{px(b)}")
    # A fault on the @Rm load leaves Rn and MAC unchanged (precise exception).
    e = fresh(**{"r%d" % N: D + 0xB0, "r%d" % M: 0x10, "mach": 5})
    try:
        e._execute(rr(0x0, 0xF, N, M), 0x8C000000)
    except EngineError:
        pass
    else:
        raise AssertionError("mac.l from unmapped @Rm did not fault")
    _expect_equal((e.get_regs()["r%d" % N], e.get_regs()["mach"]), (D + 0xB0, 5),
                  "mac.l fault keeps Rn and MACH")
    # The M9.45 fast path has no mac.l template: _step runs it.
    _expect_equal(_tc_insn(rr(0x0, 0xF, N, M), 0x8C000000), None,
                  "mac.l has no fast-path template")

    # mac.w with n == m: the second word is read at Rn+2 and Rn ends +4.
    e = fresh(**{"r%d" % N: D + 0x40})
    e.write_mem(D + 0x40, b"\x00\x03\x00\x07")
    e._execute(rr(0x4, 0xF, N, N), 0x8C000000)
    snap = e.get_regs()
    _expect_equal((snap["macl"], snap["r%d" % N]), (21, D + 0x44),
                  "mac.w @Rn+,@Rn+: 3*7 and Rn+4")
    # mac.w with S = 1 (SR bit 1): 32-bit saturation of MACL, MACH kept.
    for macl, a, b, want in ((0x7FFFFFF0, 0x7FFF, 0x7FFF, 0x7FFFFFFF),
                             (0x80000010, 0x8000, 0x7FFF, 0x80000000),
                             (0x00000010, 0xFFFF, 0x0002, 0x0000000E)):
        e = fresh(sr=0x2, mach=0x55, macl=macl,
                  **{"r%d" % N: D + 0x50, "r%d" % M: D + 0x60})
        e.write_mem(D + 0x50, a.to_bytes(2, "big"))
        e.write_mem(D + 0x60, b.to_bytes(2, "big"))
        e._execute(rr(0x4, 0xF, N, M), 0x8C000000)
        snap = e.get_regs()
        _expect_equal((snap["mach"], snap["macl"]), (0x55, want),
                      f"mac.w S=1 MACL={px(macl)} {px(a)}*{px(b)}")
    # A fault on the @Rm load leaves Rn unchanged (precise exception).
    e = fresh(**{"r%d" % N: D + 0x40, "r%d" % M: 0x10})
    try:
        e._execute(rr(0x4, 0xF, N, M), 0x8C000000)
    except EngineError:
        pass
    else:
        raise AssertionError("mac.w from unmapped @Rm did not fault")
    _expect_equal(e.get_regs()["r%d" % N], D + 0x40, "mac.w fault keeps Rn")

    # mov.w r0,@(disp,Rm): Rn is bits 7-4; r0 holds the value, not the base.
    engine = fresh(r0=0x0000_ABCD, **{"r%d" % M: D + 0x40})
    base = engine.get_regs()["r%d" % M]
    opcode = 0x8100 | (M << 4) | 0x3                    # mov.w r0,@(6,Rm)
    engine._execute(opcode, 0x8C000000)
    _expect_equal(bytes(engine.read_mem(base + 6, 2)), b"\xab\xcd",
                  "mov.w r0,@(disp,Rm) stores through Rm, not r0")
def _divide_32(signed: bool, dividend: int, divisor: int, step=None) -> int:
    """Run the SH-4 manual's 32-bit divide sequence (div0u/div0s + 32 x
    ``rotcl; div1``) on PySh4 and return R2 (the quotient).

    Every instruction, ``rotcl`` included (modelled since M9.50; before it
    the host applied it between engine steps), runs in the engine.  *step*
    replaces ``_div1_step`` (the negative control).
    """
    e = PySh4(endian="big")
    e.map("code", 0x8C000000, 4, "rwx")
    saved = globals()["_div1_step"]
    if step is not None:
        globals()["_div1_step"] = step
    try:
        def run(word):
            e._execute(word, 0x8C000000)

        def rotcl(reg):
            run(0x4024 | (int(reg[1:]) << 8))            # rotcl Rn

        e.set_regs(r0=divisor & M32, r2=dividend & M32, sr=0)
        if signed:
            run(0x6323)                                  # mov r2,r3
            rotcl("r3")                                  # rotcl r3
            run(0x311A)                                  # subc r1,r1
            run(0xE300)                                  # mov #0,r3
            run(0x323A)                                  # subc r3,r2
            run(0x2107)                                  # div0s r0,r1
        else:
            run(0xE100)                                  # mov #0,r1
            run(0x0019)                                  # div0u
        for _ in range(32):
            rotcl("r2")
            run(0x3104)                                  # div1 r0,r1
        rotcl("r2")
        if signed:
            run(0x323E)                                  # addc r3,r2
        return e.get_regs()["r2"]
    finally:
        globals()["_div1_step"] = saved


@check("pysh4: div0u/div0s + 32 x div1 divide like C (unsigned and signed)")
def test_div1_full_divide():
    vectors = ((100, 7), (0xFFFFFFFF, 1), (0xFFFFFFFF, 0xFFFFFFFF),
               (0x80000000, 3), (12345678, 1000), (5, 9), (0, 5),
               (0x7FFFFFFF, 2), (1000, 0x7FFFFFFF))
    for a, b in vectors:
        _expect_equal(_divide_32(False, a, b), (a // b) & M32,
                      f"unsigned {px(a)} / {px(b)}")
    svectors = ((100, 7), (-100, 7), (100, -7), (-100, -7), (7, -100),
                (-(1 << 31), 3), ((1 << 31) - 1, -2), (-1, 1), (0, -5),
                (-12345678, 1000), (12345678, -1000))
    for a, b in svectors:
        want = abs(a) // abs(b) * (1 if (a < 0) == (b < 0) else -1)
        _expect_equal(_divide_32(True, a, b), want & M32,
                      f"signed {a} / {b}")
    # Negative control: a div1 that ignores the M/Q state (always "shift,
    # subtract, Q = borrow") must get a signed case wrong.
    real_step = _div1_step
    blind = lambda rn, rm, t, old_q, mbit: real_step(rn, rm, t, 0, 0)
    _expect_equal(_divide_32(True, -100, 7, step=blind) == ((-14) & M32),
                  False, "M/Q-blind div1 must fail the signed control")
    _expect_equal(_divide_32(False, 100, 7, step=blind) == 14, False,
                  "Q-blind div1 must fail the unsigned control")


@check("pysh4: watch records guest loads only; api/x tagged; arming after setup")
def test_watch_hooks():
    base = 0x8C000100
    engine = PySh4(endian="little")
    engine.map("data", base, bytearray(b"\x80\x00\x14\xF9\x7F\x00\x00\x00"), "rw")
    # Set-up writes happen before arming and must not be hits.
    engine.write_mem(base, b"\x01\x02")
    engine.watch(base, base + 4, kind="r", name="first")
    engine.watch(base + 4, base + 8, kind="r", name="second")
    engine.arm_watch()
    _expect_equal(len(engine.watch_hits()), 0, "no hits before the first access")
    engine.set_regs(r5=base)
    engine._execute(0x6150, 0x8C000000)               # mov.b @r5,r1 -> base
    engine._execute(0x6151, 0x8C000000)               # mov.w @r5,r1 -> base
    hits = engine.watch_hits()
    _expect_equal([h.size for h in hits], [1, 2], "guest loads r: widths")
    _expect_equal({h.name for h in hits}, {"first"}, "only the watched half")
    _expect_equal(len([h for h in hits if h.name == "second"]), 0,
                  "negative control: unwatched half has no hits")
    # read_mem/write_mem are api hits, never guest reads.  An api write only
    # lands in a write watch, an api read only in a read watch.
    engine.watch(base + 4, base + 8, kind="w", name="second-w")
    engine.read_mem(base, 2)
    engine.write_mem(base + 4, b"\xAA\xBB")
    api = [h for h in engine.watch_hits() if h.kind.startswith("api")]
    guest = [h for h in engine.watch_hits() if not h.kind.startswith("api")]
    _expect_equal(sorted(h.kind for h in api), ["api-r", "api-w"],
                  "api read/write recorded separately")
    _expect_equal(len(guest), 2, "api accesses excluded from guest reads")
    # An unmapped watch range fails at arm time, never silently.
    typo = PySh4()
    typo.map("data", base, bytearray(16), "rw")
    typo.watch(0xDEAD0000, 0xDEAD0010)
    try:
        typo.arm_watch()
    except UsageError:
        pass
    else:
        raise AssertionError("arm_watch accepted an unmapped range")
    # Instruction fetch is tagged x and never lands in a data watch.
    fetch = PySh4(endian="little")
    fetch.map("code", 0x8C100000, struct.pack("<H", 0x0009) + struct.pack("<H", 0x0009), "rx")
    fetch.watch(0x8C100000, 0x8C100004, kind="r")
    fetch.arm_watch()
    fetch.set_regs(pc=0x8C100000)
    fetch.run_until(stop=0x8C100002)
    _expect_equal(len(fetch.watch_hits()), 0, "fetch is x, not a data read")


def _run_with_alarm(seconds: int, func, *args, **kwargs):
    """Run *func* with a SIGALRM wall-clock bound (Linux).  Raises on timeout."""
    try:
        import signal
    except Exception:  # pragma: no cover
        return func(*args, **kwargs)

    def _handler(signum, frame):
        raise TimeoutError(f"exceeded {seconds}s wall-clock bound")

    old = signal.getsignal(signal.SIGALRM)
    try:
        signal.signal(signal.SIGALRM, _handler)
        signal.alarm(seconds)
        return func(*args, **kwargs)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def _parity(name: str, factory: Callable[[], Backend], missing_code: str,
            *, external: bool = False) -> None:
    """Run the snippet on *name*, or record an exact SKIP when it is absent.

    When *external* is true the check exercises a non-reference back end whose
    adapter may be slow or unverified.  The default quick selftest skips that
    execution (honest SKIP, never PASS); ``--full`` runs it with a wall-clock
    bound so a broken adapter fails loudly instead of hanging a gate.
    """
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
        if external and not FULL_SELFTEST:
            SKIPS.append(
                f"{name}: SKIPPED_IN_QUICK - external back end parity skipped in "
                f"quick selftest (use --full); {availability.detail}"
            )
            return
        reference = run_snippet(PySh4())
        if external:
            # External adapters are unverified here; bound --full so it cannot
            # hang a gate.  A timeout is a loud failure (not a pass/skip).
            snapshot = _run_with_alarm(60, run_snippet, backend)
        else:
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


# -- M9.45: the fast path (translated blocks) against ``_step`` -----------

_TCT_CODE, _TCT_DATA = 0x8C000000, 0x8C100000


def _tct_code(words) -> bytes:
    blob = b"".join(w.to_bytes(2, "little") for w in words)
    return blob + bytes(0x1000 - len(blob))


def _tct_engine(code_perm="rwx", words=()):
    e = PySh4(endian="little")
    e.map("code", _TCT_CODE, _tct_code(words), code_perm)
    e.map("data", _TCT_DATA, 0x1000, "rw")
    return e


def _tct_state(e, state, words, data_seed):
    if "w" in e.region_at(_TCT_CODE).rwx:
        e.write_mem(_TCT_CODE, _tct_code(words))
    e.write_mem(_TCT_DATA, bytes((data_seed * 7 + k * 13) & 0xFF for k in range(0x1000)))
    regs = {"r%d" % k: (_TCT_DATA + 0x400 + 16 * k) for k in range(16)}
    regs.update(state)
    regs.setdefault("pc", _TCT_CODE)
    e.set_regs(**regs)
    e._delay = None
    e._arm = "previous"


def _tct_outcome(e, run):
    try:
        count = run()
        error = None
    except Exception as exc:  # noqa: BLE001 - the exception is the outcome
        count, error = None, (type(exc).__name__, str(exc))
    return (count, error, e.get_regs(), bytes(e.read_mem(_TCT_DATA, 0x1000)),
            e._delay, e._arm)


#: Register states: pointers into the data page, and arithmetic seeds that
#: send pointer forms off the map (so faults are compared too).
_TCT_STATES = (
    {"r0": 0x40, "sr": 0x00000000, "gbr": _TCT_DATA + 0x800, "pr": _TCT_CODE + 0x100,
     "mach": 0x11, "macl": 0x22},
    {"r0": 0x41, "sr": 0x00000301, "gbr": _TCT_DATA + 0x801, "pr": _TCT_CODE + 0x100},
    {"r0": 0x80000001, "r1": 0xFFFFFFFF, "r2": 0x7FFFFFFF, "r3": 0x80,
     "r4": 0xFFFFFF80, "r5": 31, "r6": 0xFFFFFFE0, "r7": 0xFFFFFFE1,
     "sr": 0x00000001, "gbr": 0x10, "pr": 0x1234},
)


def _tct_words():
    """Quick mode: every top/low nibble and immediate high nibble, with the
    n and m fields drawn from {0, 1, 5, 15}; ``--full``: all 65,536."""
    if FULL_SELFTEST:
        return range(0x10000)
    fields = (0x0, 0x1, 0x5, 0xF)
    return [w for w in range(0x10000)
            if (w >> 8) & 0xF in fields and (w >> 4) & 0xF in fields]


@check("pysh4: fast path == _step on templated halfwords, 3 states (M9.45)")
def test_tc_every_halfword():
    slow, fast = _tct_engine(), _tct_engine()
    templated = 0
    words_run = _tct_words()
    for word in words_run:
        t = _tc_insn(word, _TCT_CODE)
        if t is None:
            continue
        templated += 1
        for k, state in enumerate(_TCT_STATES):
            # A delayed branch gets a nop slot; anything else is followed by
            # an FPU word, which has no template, so the block is one insn.
            words = [word, 0x0009 if t[0] == "delay" else 0xF00D]
            _tct_state(slow, state, words, k)
            _tct_state(fast, state, words, k)

            def run_slow(delayed=t[0] == "delay"):
                slow._step()
                if not delayed:
                    return 1
                slow._step()                         # the slot, taken or not
                return 2

            def run_fast():
                entry = _tc_build(fast, _TCT_CODE, lambda va: va == _TCT_CODE + 4)
                if entry is None:
                    return "no block"
                count, arm = entry[0](fast._regs)
                if arm is not None:
                    fast._arm = arm
                return count

            want = _tct_outcome(slow, run_slow)
            got = _tct_outcome(fast, run_fast)
            if got != want:
                raise AssertionError(
                    f"{px(word)} state {k}: fast {got[:2]} {got[4:]} != step {want[:2]} "
                    f"{want[4:]}; regs differ in "
                    f"{sorted(n for n in want[2] if want[2][n] != got[2][n])}, "
                    f"memory {'differs' if want[3] != got[3] else 'same'}")
    if templated < len(words_run) // 2:
        raise AssertionError(f"only {templated}/{len(words_run)} halfwords have a template")


def _tct_run(e, slow, stop=None, max_insns=400):
    run = (lambda: Backend.run_until(e, stop, max_insns).insns) if slow else \
        (lambda: e.run_until(stop, max_insns).insns)
    return _tct_outcome(e, run)


@check("pysh4: fast run_until == stepped run_until on random blocks, SMC, stops (M9.45)")
def test_tc_random_blocks():
    import random
    rng = random.Random(4545)
    pool = [w for w in range(0x10000)
            if (t := _tc_insn(w, _TCT_CODE)) is not None and t[0] == "op"]
    straight = [w for w in pool if (w >> 12) not in (0x0, 0x8, 0xC)
                or w & 0xF0FF in (0x0029,)]
    for case in range(400):
        body = [rng.choice(straight if case % 2 else pool) for _ in range(rng.randint(1, 24))]
        # A backward bf/s loop over the body, then rts; nop.
        loop = (0x8F00 | ((-(len(body) + 2)) & 0xFF))     # bf/s to the start
        words = body + [0x4010 | (14 << 8), loop, 0x0009, 0x000B, 0x0009]
        state = dict(rng.choice(_TCT_STATES))
        state["r14"] = rng.randint(1, 5)                  # dt r14 loop counter
        state["pr"] = RETURN_VA
        perm = "rwx" if case % 5 == 0 else "rx"            # SMC on some cases
        # Pointers into the code itself on some cases: with "rwx" a store
        # rewrites an instruction of the running block.
        code_regs = ({"r%d" % k: _TCT_CODE + 2 * rng.randint(0, 8) for k in (4, 5, 6)}
                     if case % 7 == 0 else {})
        stop = _TCT_CODE + 2 * rng.randint(1, len(body)) if case % 3 == 0 else None
        budget = rng.choice((7, 50, 400))
        outs = []
        for slow in (True, False):
            e = _tct_engine(perm, words)
            _tct_state(e, state, words, case)
            if code_regs:
                e.set_regs(**code_regs)
            outs.append((_tct_run(e, slow, stop, budget),
                         bytes(e.read_mem(_TCT_CODE, 0x80))))
        if outs[0] != outs[1]:
            diff = [k for k in range(len(outs[0][0])) if outs[0][0][k] != outs[1][0][k]]
            raise AssertionError(f"case {case}: words {[hex(w) for w in words]} "
                                 f"fast {outs[1][0][:2]} != step {outs[0][0][:2]}; "
                                 f"fields {diff} code {outs[0][1] != outs[1][1]} "
                                 f"{[(outs[0][0][k], outs[1][0][k]) for k in diff if k != 3]}")


@check("pysh4: fast path stays off for overrides, watches and callable stops (M9.45)")
def test_tc_fallbacks():
    class Counting(PySh4):
        def _execute(self, insn, pc):
            self.seen = getattr(self, "seen", 0) + 1
            super()._execute(insn, pc)

    words = [0x7001] * 10 + [0x000B, 0x0009]                # add #1,r0 x10; rts
    for factory, expect_seen in ((Counting, 12),):
        e = factory(endian="little")
        e.map("code", _TCT_CODE, _tct_code(words), "rx")
        e.set_regs(pc=_TCT_CODE, pr=RETURN_VA, r0=0)
        result = e.run_until(None, 100)
        _expect_equal((result.insns, e.get_regs()["r0"], e.seen), (12, 10, expect_seen),
                      "subclass override runs every instruction through _execute")
    e = PySh4(endian="little")
    e.map("code", _TCT_CODE, _tct_code(words), "rx")
    e.set_regs(pc=_TCT_CODE, pr=RETURN_VA, r0=0)
    seen = []
    result = e.run_until(lambda va: seen.append(va) or False, 100)
    _expect_equal(len(seen), 12, "callable stop sees every PC")
    # A hook registered mid-run (by another hook) inside a translated block.
    e.set_regs(pc=_TCT_CODE, pr=RETURN_VA, r0=0)
    hits = []
    e.on_exec(_TCT_CODE, lambda eng, va: eng.on_exec(_TCT_CODE + 8, lambda g, v: hits.append(v)))
    e.run_until(None, 100)
    _expect_equal(hits, [_TCT_CODE + 8], "hook added mid-run is honoured")
    # max_insns: the same Runaway, at the same PC, as the stepped loop.
    for budget in (1, 5, 11):
        msgs = []
        for slow in (True, False):
            e = PySh4(endian="little")
            e.map("code", _TCT_CODE, _tct_code(words), "rx")
            e.set_regs(pc=_TCT_CODE, pr=RETURN_VA, r0=0)
            try:
                (Backend.run_until if slow else PySh4.run_until)(e, None, budget)
            except Runaway as exc:
                msgs.append((str(exc), e.get_regs()["r0"]))
        _expect_equal(msgs[1], msgs[0], f"Runaway at max_insns={budget}")


@check("parity: an available back end is compared without its label")
def test_parity_available_path():
    skips_before = len(SKIPS)
    _parity("alias", _AliasPySh4, "MISSING_ALIAS")
    _expect_equal(len(SKIPS), skips_before, "available back end must not skip")


@check("ghidra: runs the snippet identically, or SKIPs with MISSING_GHIDRA")
def test_ghidra_parity():
    _parity("ghidra", GhidraBackend, "MISSING_GHIDRA", external=True)


@check("qemu: runs the snippet identically, or SKIPs with MISSING_QEMU")
def test_qemu_parity():
    _parity("qemu", QemuBackend, "MISSING_QEMU", external=True)


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
                        help="run acceptance checks (default: quick/bounded; use --full for external parity)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--quick", action="store_true",
                      help="bounded selftest: skip external back-end execution (default with --selftest)")
    mode.add_argument("--full", action="store_true",
                      help="complete selftest: run external Ghidra/QEMU parity when their back ends are available")
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
        return _run_selftest(full=bool(args.full))
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


def _run_selftest(*, full: bool = False) -> int:
    global FULL_SELFTEST
    FULL_SELFTEST = full
    SKIPS.clear()
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
    mode = "full" if full else "quick"
    if failures:
        print(f"selftest: FAILED ({failures}/{total} checks, {skipped} skipped, {mode})")
        return EXIT_FAIL
    if skipped:
        print(
            f"selftest: OK ({total - skipped} checks, {skipped} skipped, {mode}) - "
            "a skipped back end is not a pass"
        )
    else:
        print(f"selftest: OK ({total} checks, every back end ran, {mode})")
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
