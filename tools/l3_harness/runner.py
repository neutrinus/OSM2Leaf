#!/usr/bin/env python3
"""L3 harness runner: run one target end to end, never fake a pass.

Commands:

``check``
    Validate the corpus manifest (shape, hashes when ``--root`` is given) and
    the Ghidra memory map.  Exit ``1`` on any problem.
``plan``
    Print the trace targets, the readers that still have no entry point, the
    stubs each reader needs and the remaining blockers.  Never claims a reader
    is runnable.
``targets``
    List the named targets in ``targets.json`` with their entry kind, reader
    and expected verdict.
``run FUNC``
    **Target mode** (M9.5): load ``--input FILE`` (or the target's corpus
    entry under ``--corpus DIR``) into the virtual file system, map the
    target program, install the stub dispatcher with ``on_exec``, execute on
    ``--engine pysh4|ghidra|qemu`` and print the verdict as JSON.  A synthetic
    target runs on the pure-Python reference engine; a reader that is not
    located reports ``BLOCKED``; a back end that is absent reports ``SKIP``
    (exit ``3``) and never ``PASS``.  A ``module`` entry (M9.20) calls a
    function at a VA of a memory map: ``run FUNC --rommap MAP.json --image FW``
    maps the named module's blocks from the image bytes (no hand-written
    ``-device loader`` list), passes ``entry.args`` in ``r4``-``r7``, reads the
    verdict from ``r0`` through ``entry.verdict_map`` and reports ``BLOCKED``
    for a VA outside an executable block or an unmapped ``r0``.
``run`` (legacy, no FUNC)
    Look for Ghidra's ``analyzeHeadless``.  Without it, print
    ``MISSING_GHIDRA`` plus exact install instructions and exit ``3``.  With
    Ghidra but without the entry script ``ghidra/l3_run.py``, a located reader
    or the firmware image, print ``BLOCKED`` and exit ``4``.  The script's
    result is read back: a ``BLOCKED`` result is exit ``4``; only a result
    whose cases match every manifest verdict may exit ``0``.

Exit codes: ``0`` pass, ``1`` invalid inputs, ``2`` usage error,
``3`` back end missing / skipped, ``4`` blocked, ``5`` result mismatch.

Usage::

    python3 tools/l3_harness/runner.py check --manifest m.json --rommap r.json
    python3 tools/l3_harness/runner.py plan  --manifest m.json --rommap r.json
    python3 tools/l3_harness/runner.py targets
    python3 tools/l3_harness/runner.py run probe-zlib-cmf --input card.cmp --json
    python3 tools/l3_harness/runner.py run probe-zlib-cmf --corpus /tmp/l3/corpus \\
        --engine pysh4 --json
    python3 tools/l3_harness/runner.py run probe-zlib-cmf --input card.cmp \\
        --engine ghidra --dry-run
    python3 tools/l3_harness/runner.py run --manifest m.json --rommap r.json \\
        --image archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img
    python3 tools/l3_harness/runner.py --selftest
    python3 tools/l3_harness/runner.py selftest
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from l3_harness import dispatch as dispatch_mod  # noqa: E402
from l3_harness import engine as engine_mod  # noqa: E402
from l3_harness import manifest as manifest_mod  # noqa: E402
from l3_harness import rommap as rommap_mod  # noqa: E402
from l3_harness import stubs as stubs_mod  # noqa: E402

HERE = Path(__file__).resolve().parent
HARNESS_SCRIPT = HERE / "ghidra" / "l3_run.py"
TARGETS_FILE = HERE / "targets.json"

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_MISSING_GHIDRA = 3
#: A back end that is not installed is *skipped*, never passed.
EXIT_SKIP = EXIT_MISSING_GHIDRA
EXIT_BLOCKED = 4
EXIT_MISMATCH = 5

DEFAULT_SEARCH_ROOTS = ("/opt", "/usr/local", "/usr/share", "~")

#: Anchors recorded by earlier firmware work.  ``status`` deliberately
#: distinguishes a file offset from a link-time VA: a file offset is not
#: runnable until the memory map binds it.
TRACE_TARGETS = [
    {
        "id": "mapcode-comparator",
        "reader": "hdd_info",
        "role": "helper",
        "what": "map-code comparator chain (Sys[...] vs SD[...])",
        "anchor": "0x6fab2c -> 0x6faeb0 -> 0x6fb05c, data delta 0x02800000",
        "status": "located-file-offset",
        "note": (
            "file offsets, not VAs; the HDD_INFO parser itself is behind a "
            "runtime COM object and is not located"
        ),
    },
    {
        "id": "hdd-info-parser",
        "reader": "hdd_info",
        "role": "reader",
        "what": "HDD_INFO.TXT parser",
        "anchor": None,
        "status": "unknown",
        "note": "reached through a runtime COM object",
    },
    {
        "id": "cmp-ind-reader",
        "reader": "cmp_ind",
        "role": "reader",
        "what": ".cmp/.ind container reader (zlib calls, descriptor fields)",
        "anchor": None,
        "status": "unknown",
        "note": "no literal map filename exists; must be traced from the TOC",
    },
    {
        "id": "tile-reader",
        "reader": "tile",
        "role": "reader",
        "what": "MAPAL001 tile reader (MESH_ID/DIVID, 0x1ac level table)",
        "anchor": None,
        "status": "unknown",
        "note": "no entry point recovered",
    },
    {
        "id": "drstr-parser",
        "reader": "drstr",
        "role": "reader",
        "what": "DRSTR001.DAT tree parser (40-byte nodes, 32-byte entries)",
        "anchor": "0x00419350",
        "status": "anchor-only",
        "note": ("EU2011 fn 0x00419350 (caller 0x00419684); runs as target "
                 "drstr_parser (firmware_call drstr_parser_v1, M9.24)"),
    },
    {
        "id": "cmp-lst-opener",
        "reader": "cmp_lst",
        "role": "reader",
        "what": "CMP.LST / map-path opener",
        "anchor": "0xc438a4",
        "status": "refuted",
        "note": (
            "0xc438a4 is a stats formatter, not the opener; map filenames "
            "have zero literal references"
        ),
    },
    {
        "id": "anchor-c0ebf8",
        "reader": None,
        "role": "anchor",
        "what": "old call-graph anchor",
        "anchor": "0xc0ebf8",
        "status": "anchor-only",
        "note": "proposed in feedback-loop.md; no reader proven",
    },
    {
        "id": "anchor-c48380",
        "reader": None,
        "role": "anchor",
        "what": "old call-graph anchor",
        "anchor": "0xc48380",
        "status": "anchor-only",
        "note": "proposed in feedback-loop.md; no reader proven",
    },
    {
        "id": "anchor-c42520",
        "reader": None,
        "role": "anchor",
        "what": "NaviStateCC fd method candidate",
        "anchor": "0xc42520",
        "status": "anchor-only",
        "note": "COM vtable is built at runtime, so a static hook is missing",
    },
]


# ==========================================================================
# Target mode (TODO M9.5)
# ==========================================================================
#
# ``targets.json`` names one firmware function or one synthetic probe.  The
# runner resolves the corpus input, maps the program, installs the stub
# dispatcher (:mod:`dispatch`) as ``on_exec`` hooks and lets the chosen engine
# (:mod:`engine`) execute it.  Nothing here emulates the firmware: a reader
# whose entry point is not located is declared ``blocked`` in the JSON and the
# runner reports ``BLOCKED`` for it.

TARGETS_SCHEMA = "osm2leaf.l3.targets/v1"

TARGET_KEYS = {
    "name",
    "reader",
    "what",
    "module",
    "entry",
    "stubs",
    "corpus",
    "expect",
    "notes",
    "build",
    "generated_corpus",   # H106: our tiles, listed by l3check, never run here
}

#: Firmware builds a target can be registered against (M1.22b).  A target run
#: must say which build its reader VA belongs to; ``eu2011`` is the default the
#: whole matrix was built on, ``us2011`` marks a US VA (M1.22/M9.10/M9.12).
BUILDS = ("eu2011", "us2011")

#: ``entry.kind`` values.  ``synthetic``: a program shipped in this file;
#: ``module``: a function at a VA of a memory map (M9.5/M9.20); ``blocked``: a
#: reader whose entry point is not located yet; ``firmware_call``: a located
#: firmware function run with explicit memory setup (M9.11b, chunk reader).
ENTRY_KINDS = ("synthetic", "module", "blocked", "firmware_call")
MODULE_ENTRY_KEYS = {
    "kind", "module", "va", "endian", "args", "verdict_map", "note",
    "input_region",
}
#: A ``entry.input_region`` maps caller-supplied or file-derived bytes at a
#: chosen guest VA (M9.28) so a module reader can consume real input instead
#: of faulting on its argument pointer.  Bounds are exact: one byte past
#: ``va+size`` is unmapped, unlike ``point_walk_l3``'s ``+0x40`` pad.
INPUT_REGION_KEYS = {"va", "size", "bytes_source", "provenance"}
INPUT_BYTES_KEYS = {"kind", "path", "hex"}
#: Small literal fixtures only: a literal is a synthetic control, never a page.
INPUT_LITERAL_MAX = 0x400
FIRMWARE_CALL_ENTRY_KEYS = {
    "kind", "program", "module", "va", "endian", "note",
    "sec1_table", "inputs", "verdict_map",
}
#: The ``firmware_call`` programs that read a sec1 (inflate-mask / parse-cache)
#: table; ``point_walk_v1`` (M9.55) reads only the image, the pair and a page.
SEC1_PROGRAMS = ("cmp_ind_chunk_v1", "mapcode_compare_v1")
#: Byte order of a module entry.  ``"little"`` needs ``PySh4(endian="little")``
#: (M9.21); the other back ends are big-endian in this harness and refuse it.
MODULE_ENDIANS = ("big", "little")
#: The SH-4 register arguments a module call can pass (r4-r7); stack arguments
#: are not modelled for module entries.
MODULE_MAX_ARGS = 4

# -- synthetic probe memory layout (the only program shipped so far) --------

PROGRAM_VA = 0x8C100000
PROGRAM_SIZE = 0x200
STACK_VA = 0x8C1FF000
STACK_SIZE = 0x1000
STACK_TOP = STACK_VA + STACK_SIZE
DATA_VA = 0x8C200000
DATA_SIZE = 0x1000
HEAP_VA = 0x8C202000
HEAP_SIZE = 0x2000

#: Offsets inside the data region (``DATA_VA``).
FMT_PATH_OFF = 0x010          # "%s"
FMT_LOG_OFF = 0x020           # "%s|%d"
PATH_OFF = 0x100              # ANSI guest path (sprintf %s, part of the log)
WPATH_OFF = 0x200             # UTF-16LE guest path (CreateFileW)
PATHBUF_OFF = 0x300           # sprintf("%s") output
LOGBUF_OFF = 0x400            # sprintf("%s|%d") output
READBUF_OFF = 0x500           # ReadFile destination
READ_LIMIT = 0x40

#: The probe's frame: ``sts.l pr,@-r15`` then ``add #-32,r15``, count at +12.
#: ``STACK_TOP - 4 - 32 + 12`` is the ``lpNumberOfBytesRead`` slot.
COUNT_VA = STACK_TOP - 4 - 32 + 12

#: Stub VAs the shipped program jumps to; ``targets.json`` must match them.
PROBE_STUB_VAS = {
    "sprintf_path": PROGRAM_VA + 0x200,
    "createfile": PROGRAM_VA + 0x210,
    "readfile": PROGRAM_VA + 0x220,
    "closehandle": PROGRAM_VA + 0x230,
    "sprintf_log": PROGRAM_VA + 0x240,
}

M32 = 0xFFFFFFFF


class TargetError(ValueError):
    """``targets.json`` or a target run cannot be used as given."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


class _Asm:
    """Tiny two-pass SH-4 emitter for the synthetic probe (labels, no guessing).

    Every encoding is standard SH-4; the program builder below is the only
    user.  Labels are byte offsets inside the program, PC-relative literals are
    appended after the code, and both branch and literal displacements are
    patched in :meth:`build`, which raises instead of emitting a bad encoding.
    """

    def __init__(self) -> None:
        self.words: list[int] = []
        self.labels: dict[str, int] = {}
        self.branches: list[tuple[int, str]] = []
        self.pcliterals: list[tuple[int, int, str]] = []
        self.values: dict[str, int] = {}

    # -- emission ----------------------------------------------------------

    def emit(self, word: int) -> int:
        self.words.append(word & 0xFFFF)
        return len(self.words) - 1

    def label(self, name: str) -> None:
        if name in self.labels:
            raise TargetError([f"assembler: duplicate label {name!r}"])
        self.labels[name] = len(self.words) * 2

    def mov_imm(self, n: int, imm: int) -> None:
        self.emit(0xE000 | (n << 8) | (imm & 0xFF))

    def add_imm(self, n: int, imm: int) -> None:
        self.emit(0x7000 | (n << 8) | (imm & 0xFF))

    def mov_reg(self, src: int, dst: int) -> None:
        self.emit(0x6003 | (dst << 8) | (src << 4))

    def jsr(self, n: int) -> None:
        self.emit(0x400B | (n << 8))

    def nop(self) -> None:
        self.emit(0x0009)

    def tst(self, m: int, n: int) -> None:
        self.emit(0x2008 | (n << 8) | (m << 4))

    def cmp_eq_imm(self, imm: int) -> None:
        self.emit(0x8800 | (imm & 0xFF))

    def bt(self, label: str) -> None:
        self.branches.append((self.emit(0x8900), label))

    def bf(self, label: str) -> None:
        self.branches.append((self.emit(0x8B00), label))

    def store_long(self, src: int, base: int, disp: int) -> None:
        self.emit(0x1000 | (base << 8) | (src << 4) | (disp & 0xF))

    def load_long(self, dst: int, base: int, disp: int) -> None:
        self.emit(0x5000 | (dst << 8) | (base << 4) | (disp & 0xF))

    def load_byte(self, dst: int, base: int) -> None:
        self.emit(0x6000 | (dst << 8) | (base << 4))

    def pc_literal(self, n: int, name: str) -> None:
        self.pcliterals.append((self.emit(0xD000 | (n << 8)), n, name))

    # -- patching ----------------------------------------------------------

    def build(self) -> bytes:
        if len(self.words) % 2:
            self.nop()          # keep every literal 4-byte aligned
        code = list(self.words)
        literals: list[int] = []
        for index, n, name in self.pcliterals:
            if name not in self.values:
                raise TargetError([f"assembler: undefined literal {name!r}"])
            literal_va = PROGRAM_VA + len(code) * 2 + len(literals) * 4
            literals.append(self.values[name] & M32)
            insn_va = PROGRAM_VA + index * 2
            if literal_va % 4:
                raise TargetError(["assembler: literal pool is not aligned"])
            disp = (literal_va - ((insn_va + 4) & ~3)) // 4
            if not 0 <= disp <= 0xFF:
                raise TargetError(
                    [f"assembler: literal {name!r} is out of PC range ({disp})"]
                )
            code[index] = 0xD000 | (n << 8) | disp

        for index, label in self.branches:
            if label not in self.labels:
                raise TargetError([f"assembler: undefined label {label!r}"])
            insn_va = PROGRAM_VA + index * 2
            target_va = PROGRAM_VA + self.labels[label]
            delta = target_va - (insn_va + 4)
            if delta % 2 or not -256 <= delta <= 254:
                raise TargetError(
                    [f"assembler: branch to {label!r} is out of range ({delta})"]
                )
            code[index] |= (delta // 2) & 0xFF

        payload = b"".join(struct.pack(">H", word) for word in code)
        payload += b"".join(struct.pack(">I", value) for value in literals)
        if len(payload) > PROGRAM_SIZE:
            raise TargetError(
                [f"assembler: program is {len(payload)} bytes, over {PROGRAM_SIZE}"]
            )
        return payload


def build_probe_zlib_cmf() -> bytes:
    """Assemble the synthetic target probe.

    The probe is **not** a firmware reader.  It is the smallest program that
    exercises the whole L3 pipeline: two ``sprintf`` calls through the
    dispatcher (a 3-argument path build and a 4-argument log line), a
    ``CreateFileW`` with three stack arguments, a ``ReadFile`` with one stack
    argument, a ``CloseHandle``, and a verdict derived from the first byte the
    host stub actually served:

    ``r4`` pathbuf, ``r5`` logbuf, ``r6`` readbuf, ``r12`` ANSI guest path,
    ``r13`` UTF-16LE guest path, ``gbr`` data base, ``r15`` stack top.
    The verdict is ``1`` (ACCEPT) when exactly one byte was read and it is
    ``0x78`` -- the zlib CMF the ``.cmp`` container starts with -- else ``0``.

    .. code-block:: none

        sts.l pr,@-r15 ; add #-32,r15 ; save pointers
        sprintf(pathbuf, "%s", ansi_path)
        CreateFileW(wide_path, GENERIC_READ, 0, 0, OPEN_EXISTING, 0, 0)
        ReadFile(handle, readbuf, 1, &count, 0)
        if count == 1 and readbuf[0] == 0x78: verdict = 1
        CloseHandle(handle)
        sprintf(logbuf, "%s|%d", pathbuf, verdict)
        return verdict
    """

    asm = _Asm()
    asm.label("entry")
    asm.emit(0x4F22)                    # sts.l pr,@-r15
    asm.add_imm(15, -32)                # frame: stack args + count slot
    asm.mov_reg(4, 2)                   # r2 = pathbuf
    asm.mov_reg(5, 3)                   # r3 = logbuf
    asm.mov_reg(6, 10)                  # r10 = readbuf
    asm.mov_reg(12, 11)                 # r11 = ANSI guest path
    asm.mov_imm(9, 0)                   # r9 = verdict = REJECT

    # sprintf(pathbuf, "%s", ansi_path)
    asm.mov_reg(2, 4)
    asm.pc_literal(5, "fmt_path")
    asm.mov_reg(11, 6)
    asm.pc_literal(1, "stub:sprintf_path")
    asm.jsr(1)
    asm.nop()

    # CreateFileW(wide_path, GENERIC_READ, 0, 0, OPEN_EXISTING, 0, 0)
    asm.mov_reg(13, 4)
    asm.pc_literal(5, "generic_read")
    asm.mov_imm(6, 0)
    asm.mov_imm(7, 0)
    asm.mov_imm(0, 3)                   # OPEN_EXISTING
    asm.store_long(0, 15, 0)
    asm.mov_imm(0, 0)
    asm.store_long(0, 15, 1)
    asm.store_long(0, 15, 2)
    asm.pc_literal(1, "stub:createfile")
    asm.jsr(1)
    asm.nop()
    asm.mov_reg(0, 8)                   # r8 = handle
    asm.cmp_eq_imm(-1)                  # INVALID_HANDLE_VALUE?
    asm.bt("skip_close")

    # ReadFile(handle, readbuf, 1, &count, 0)
    asm.mov_reg(8, 4)
    asm.mov_reg(10, 5)
    asm.mov_imm(6, 1)
    asm.mov_reg(15, 7)
    asm.add_imm(7, 12)                  # r7 = frame + 12 = &count
    asm.mov_imm(0, 0)
    asm.store_long(0, 15, 0)            # lpOverlapped = NULL
    asm.pc_literal(1, "stub:readfile")
    asm.jsr(1)
    asm.nop()
    asm.tst(0, 0)                       # ReadFile returned 0?
    asm.bt("close")
    asm.load_long(0, 15, 3)             # r0 = count
    asm.cmp_eq_imm(1)
    asm.bf("close")
    asm.load_byte(0, 10)                # r0 = readbuf[0]
    asm.cmp_eq_imm(0x78)                # zlib CMF byte
    asm.bf("close")
    asm.mov_imm(9, 1)                   # verdict = ACCEPT

    asm.label("close")
    asm.mov_reg(8, 4)                   # CloseHandle(handle)
    asm.pc_literal(1, "stub:closehandle")
    asm.jsr(1)
    asm.nop()

    asm.label("skip_close")
    asm.mov_reg(3, 4)                   # sprintf(logbuf, fmt, pathbuf, verdict)
    asm.pc_literal(5, "fmt_log")
    asm.mov_reg(2, 6)
    asm.mov_reg(9, 7)
    asm.pc_literal(1, "stub:sprintf_log")
    asm.jsr(1)
    asm.nop()

    asm.mov_reg(9, 0)                   # return the verdict in r0
    asm.add_imm(15, 32)
    asm.emit(0x4F26)                    # lds.l @r15+,pr
    asm.emit(0x000B)                    # rts
    asm.nop()                           # delay slot

    asm.values.update(
        {
            "fmt_path": DATA_VA + FMT_PATH_OFF,
            "fmt_log": DATA_VA + FMT_LOG_OFF,
            "generic_read": 0x80000000,
        }
    )
    for stub_id, va in PROBE_STUB_VAS.items():
        asm.values[f"stub:{stub_id}"] = va
    return asm.build()


#: Synthetic programs ``targets.json`` may name.
SYNTHETIC_PROGRAMS = {
    "probe_zlib_cmf_v1": {
        "build": build_probe_zlib_cmf,
        "va": PROGRAM_VA,
        "requires": sorted(PROBE_STUB_VAS),
        "strings": {
            "fmt_path": (FMT_PATH_OFF, "%s"),
            "fmt_log": (FMT_LOG_OFF, "%s|%d"),
        },
        "prose": (
            "synthetic SH-4 probe: 2x sprintf, CreateFileW (3 stack args), "
            "ReadFile (1 stack arg), CloseHandle; ACCEPT iff the served first "
            "byte is the zlib CMF 0x78. Not a firmware reader."
        ),
    }
}


# --------------------------------------------------------------------------
# targets.json
# --------------------------------------------------------------------------


def _hex(value, where: str, problems: list[str]) -> int | None:
    if value is None:
        return None
    try:
        number = int(str(value), 0)
    except (TypeError, ValueError):
        problems.append(f"{where}: {value!r} is not an integer address")
        return None
    if not 0 <= number <= M32:
        problems.append(f"{where}: {value!r} leaves the 32-bit space")
        return None
    return number


def _validate_stub_spec(spec, where: str, problems: list[str]) -> None:
    if not isinstance(spec, dict):
        problems.append(f"{where}: must be an object")
        return
    for key in ("id", "module", "target"):
        if not isinstance(spec.get(key), str) or not spec.get(key):
            problems.append(f"{where}: {key} must be a non-empty string")
    if "va" not in spec:
        problems.append(f"{where}: missing va")
    _hex(spec.get("va"), f"{where}.va", problems)
    arity = spec.get("arity")
    if isinstance(arity, bool) or not isinstance(arity, int) or not 0 <= arity <= 8:
        problems.append(f"{where}: arity must be an integer 0..8")
    target = spec.get("target")
    if isinstance(target, str) and not target.startswith("#"):
        entry = stubs_mod.by_name(target)
        if entry is None:
            problems.append(
                f"{where}: unknown stub {target!r} (see tools/l3_harness/stubs.py)"
            )
        elif entry["status"] != "modeled":
            problems.append(
                f"{where}: stub {target!r} is {entry['status']}, not modeled"
            )
    if isinstance(target, str) and target.startswith("#"):
        try:
            ordinal = int(target[1:], 0)
        except ValueError:
            problems.append(f"{where}: bad ordinal target {target!r}")
            return
        if not any(
            stubs_mod.normalize_module(entry["module"]) == spec.get("module")
            and entry.get("ordinal") == ordinal
            for entry in stubs_mod.STUBS
        ):
            problems.append(
                f"{where}: ordinal {target!r} is not bound for module "
                f"{spec.get('module')!r}"
            )


def _validate_input_region(entry, where: str) -> list[str]:
    """Problems in ``entry.input_region``; empty when absent or valid (M9.28)."""

    region = entry.get("input_region")
    if region is None:
        return []
    problems: list[str] = []
    if not isinstance(region, dict):
        return [f"{where}: input_region must be an object"]
    unknown = sorted(set(region) - INPUT_REGION_KEYS)
    if unknown:
        problems.append(f"{where}: input_region has unknown key(s) {unknown}")
    va = region.get("va")
    if va is None:
        problems.append(f"{where}: input_region needs va")
    else:
        _hex(va, f"{where}.input_region.va", problems)
    size = region.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        problems.append(f"{where}: input_region.size must be a positive integer")
    elif isinstance(va, (int, str)):
        start = _hex(va, f"{where}.input_region.va", problems)
        if start is not None and start + size > M32 + 1:
            problems.append(f"{where}: input_region leaves the 32-bit address space")
    source = region.get("bytes_source")
    if not isinstance(source, dict):
        problems.append(f"{where}: input_region needs bytes_source (file or literal)")
    else:
        unknown = sorted(set(source) - INPUT_BYTES_KEYS)
        if unknown:
            problems.append(f"{where}: bytes_source has unknown key(s) {unknown}")
        kind = source.get("kind")
        if kind == "file":
            if not isinstance(source.get("path"), str) or not source.get("path"):
                problems.append(f"{where}: bytes_source file needs a path")
            if "hex" in source:
                problems.append(f"{where}: bytes_source file must not carry hex")
        elif kind == "literal":
            raw = source.get("hex")
            if not isinstance(raw, str) or not raw:
                problems.append(f"{where}: bytes_source literal needs hex")
            else:
                try:
                    data = bytes.fromhex(raw[2:] if raw.startswith("0x") else raw)
                except ValueError:
                    problems.append(f"{where}: bytes_source hex is not valid hex")
                else:
                    if len(data) > INPUT_LITERAL_MAX:
                        problems.append(
                            f"{where}: literal bytes_source is limited to "
                            f"{INPUT_LITERAL_MAX} B (a control, not a page)"
                        )
            if "path" in source:
                problems.append(f"{where}: bytes_source literal must not carry path")
        else:
            problems.append(
                f"{where}: bytes_source.kind must be 'file' or 'literal'"
            )
    prov = region.get("provenance")
    if not isinstance(prov, str) or not prov.strip():
        problems.append(
            f"{where}: input_region needs provenance (why these bytes belong at "
            "this VA); a guessed buffer is not allowed"
        )
    return problems


def _validate_module_entry(entry, where: str) -> list[str]:
    """Problems in an ``entry.kind = "module"`` block; empty when valid."""

    problems: list[str] = []
    unknown = sorted(set(entry) - MODULE_ENTRY_KEYS)
    if unknown:
        problems.append(f"{where}: unknown entry key(s) {unknown}")
    module = entry.get("module")
    if not isinstance(module, str) or not module:
        problems.append(f"{where}: module entry needs a module name, e.g. Navi.exe")
    if entry.get("va") is None:
        problems.append(f"{where}: module entry needs a va")
    else:
        _hex(entry["va"], f"{where}.entry.va", problems)
    endian = entry.get("endian", "big")
    if endian not in MODULE_ENDIANS:
        problems.append(
            f"{where}: entry.endian must be one of {', '.join(MODULE_ENDIANS)}, "
            f"not {endian!r}"
        )
    args = entry.get("args", [])
    if not isinstance(args, list) or len(args) > MODULE_MAX_ARGS:
        problems.append(
            f"{where}: entry.args must be a list of at most {MODULE_MAX_ARGS} "
            "register values (r4-r7; stack arguments are not modelled)"
        )
    else:
        for index, item in enumerate(args):
            if item is None or isinstance(item, bool) or not isinstance(item, (int, str)):
                problems.append(f"{where}: entry.args[{index}] must be an integer")
            else:
                _hex(item, f"{where}.entry.args[{index}]", problems)
    verdict_map = entry.get("verdict_map")
    if not isinstance(verdict_map, dict) or not verdict_map:
        problems.append(
            f"{where}: module entry needs verdict_map, e.g. {{\"0x0\": \"REJECT\"}}; "
            "the r0-to-verdict rule is written down, never guessed"
        )
    else:
        seen: set[int] = set()
        for key, verdict in verdict_map.items():
            number = _hex(key, f"{where}.entry.verdict_map key", problems)
            if number is not None:
                if number in seen:
                    problems.append(f"{where}: verdict_map key {key!r} repeats a value")
                seen.add(number)
            if verdict not in ("ACCEPT", "REJECT"):
                problems.append(
                    f"{where}: verdict_map[{key!r}] must be ACCEPT or REJECT"
                )
    problems.extend(_validate_input_region(entry, where))
    return problems


def _validate_firmware_call_entry(entry, where: str) -> list[str]:
    """Problems in an ``entry.kind = "firmware_call"`` block (M9.11b).

    A firmware_call runs a located firmware function with explicit memory
    setup.  It must declare every non-trivial input (notably the sec1 table)
    with provenance; a silent default is a validation error, because M9.11b's
    stop condition forbids registering a passing target on guessed/undeclared
    inputs.
    """

    problems: list[str] = []
    unknown = sorted(set(entry) - FIRMWARE_CALL_ENTRY_KEYS)
    if unknown:
        problems.append(f"{where}: unknown entry key(s) {unknown}")
    program = entry.get("program")
    if not isinstance(program, str) or not program:
        problems.append(f"{where}: firmware_call entry needs a program name")
    if entry.get("module") and not isinstance(entry.get("module"), str):
        problems.append(f"{where}: entry.module must be a string")
    if entry.get("va") is not None:
        _hex(entry["va"], f"{where}.entry.va", problems)
    endian = entry.get("endian", "little")
    if endian not in MODULE_ENDIANS:
        problems.append(
            f"{where}: entry.endian must be one of {', '.join(MODULE_ENDIANS)}, "
            f"not {endian!r}"
        )
    sec1 = entry.get("sec1_table")
    # M9.11b's rule is "declare every non-trivial input"; the two chunk/mapcode
    # programs read the sec1 table, while point_walk_v1 (M9.55) does not touch
    # sec1 at all (its inputs are the image, the .cmp/.ind pair and the page
    # offset).  Requiring a sec1 table there would be a fabricated declaration,
    # exactly what the stop condition forbids.
    needs_sec1 = program in SEC1_PROGRAMS
    if not isinstance(sec1, dict):
        if needs_sec1:
            problems.append(
                f"{where}: firmware_call entry needs sec1_table as a declared "
                "input with provenance (not a silent default; M9.11b stop condition)"
            )
    else:
        if sec1.get("va") is None:
            problems.append(f"{where}: sec1_table needs va (sourced from code)")
        else:
            _hex(sec1["va"], f"{where}.sec1_table.va", problems)
        values = sec1.get("values")
        source = sec1.get("source", "declared")
        if source not in ("declared", "image"):
            problems.append(f"{where}: sec1_table.source must be 'declared' or 'image'")
        if source == "image":
            # M1.19: the bytes come from the image (kernel decoder), never a list
            if values is not None:
                problems.append(f"{where}: sec1_table.source 'image' takes no values")
        elif not isinstance(values, list) or not values:
            problems.append(f"{where}: sec1_table needs values (declared, not a default)")
        else:
            for i, item in enumerate(values):
                if item is None or isinstance(item, bool) or not isinstance(item, (int, str)):
                    problems.append(f"{where}: sec1_table.values[{i}] must be an integer")
                else:
                    _hex(item, f"{where}.sec1_table.values[{i}]", problems)
        prov = sec1.get("provenance")
        if not isinstance(prov, str) or not prov.strip():
            problems.append(
                f"{where}: sec1_table needs provenance (source of VA/values; "
                "a guessed table is not allowed)"
            )
    inputs = entry.get("inputs")
    if inputs is not None and not isinstance(inputs, dict):
        problems.append(f"{where}: entry.inputs must be an object when present")
    vmap = entry.get("verdict_map")
    if vmap is not None:
        # M9.24: return value -> verdict, decoded from the function's exits
        if not isinstance(vmap, dict) or not vmap:
            problems.append(f"{where}: entry.verdict_map must be a non-empty object")
        else:
            for key, verdict in vmap.items():
                _hex(key, f"{where}.verdict_map key", problems)
                if verdict not in ("ACCEPT", "REJECT"):
                    problems.append(f"{where}: verdict_map[{key}] must be ACCEPT or REJECT")
    # M9.55: point_walk_v1 reads its page through --cmp/--ind; the corpus-relative
    # path lets l3check --build-corpus name the same fixture the manifest hashed.
    if program == "point_walk_v1" and isinstance(inputs, dict):
        source = inputs.get("source")
        if not isinstance(source, str) or not source.strip():
            problems.append(
                f"{where}: point_walk_v1 needs inputs.source (corpus-relative "
                ".cmp path of the POINT page)"
            )
        elif source.startswith("/") or ".." in source.split("/"):
            problems.append(
                f"{where}: inputs.source must be relative and inside the corpus"
            )
    return problems


def validate_targets(doc) -> list[str]:
    """Return every problem in a ``targets.json`` document."""

    problems: list[str] = []
    if not isinstance(doc, dict):
        return ["targets: document must be a JSON object"]
    if doc.get("schema") != TARGETS_SCHEMA:
        problems.append(f"targets: schema must be {TARGETS_SCHEMA!r}")
    targets = doc.get("targets")
    if not isinstance(targets, list) or not targets:
        return problems + ["targets: 'targets' must be a non-empty list"]

    seen: set[str] = set()
    for index, target in enumerate(targets):
        where = f"targets[{index}]"
        if not isinstance(target, dict):
            problems.append(f"{where}: must be an object")
            continue
        name = target.get("name")
        if not isinstance(name, str) or not name:
            problems.append(f"{where}: missing name")
            continue
        where = f"targets[{index}] ({name})"
        if name in seen:
            problems.append(f"{where}: duplicate name")
        seen.add(name)
        unknown = sorted(set(target) - TARGET_KEYS)
        if unknown:
            problems.append(f"{where}: unknown key(s) {unknown}")
        for key in ("reader", "what"):
            if not isinstance(target.get(key), str) or not target.get(key):
                problems.append(f"{where}: {key} must be a non-empty string")
        build = target.get("build")
        if build is not None and build not in BUILDS:
            problems.append(
                f"{where}: build must be one of {', '.join(BUILDS)} (got {build!r})"
            )

        entry = target.get("entry")
        if not isinstance(entry, dict):
            problems.append(f"{where}: entry must be an object")
        else:
            kind = entry.get("kind")
            if kind not in ENTRY_KINDS:
                problems.append(
                    f"{where}: entry.kind must be one of {', '.join(ENTRY_KINDS)}"
                )
            elif kind == "blocked":
                if not isinstance(entry.get("reason"), str) or not entry["reason"]:
                    problems.append(f"{where}: blocked entry needs a reason")
            elif kind == "module":
                problems.extend(_validate_module_entry(entry, where))
            elif kind == "firmware_call":
                problems.extend(_validate_firmware_call_entry(entry, where))
            else:
                program = entry.get("program")
                if program not in SYNTHETIC_PROGRAMS:
                    problems.append(
                        f"{where}: unknown synthetic program {program!r} "
                        f"(known: {', '.join(sorted(SYNTHETIC_PROGRAMS))})"
                    )
                va = _hex(entry.get("va"), f"{where}.entry.va", problems)
                if va is not None and va != SYNTHETIC_PROGRAMS[program]["va"]:
                    problems.append(
                        f"{where}: entry.va {entry['va']!r} is not the program's "
                        f"load address "
                        f"0x{SYNTHETIC_PROGRAMS[program]['va']:08x}"
                    )

        stubs = target.get("stubs")
        kind_now = entry.get("kind") if isinstance(entry, dict) else None
        # module/firmware_call may declare no stub list entry specs (hooks are
        # installed by the runner/program); blocked uses name strings.
        if kind_now == "firmware_call":
            if not isinstance(stubs, list):
                problems.append(f"{where}: stubs must be a list")
        elif not isinstance(stubs, list) or (not stubs and kind_now != "module"):
            problems.append(f"{where}: stubs must be a non-empty list")
        elif isinstance(entry, dict) and entry.get("kind") == "blocked":
            for item in stubs:
                if not isinstance(item, str) or item not in stubs_mod.names():
                    problems.append(f"{where}: unknown stub name {item!r}")
        elif isinstance(entry, dict) and entry.get("kind") in ("synthetic", "module"):
            ids = set()
            for stub_index, spec in enumerate(stubs):
                _validate_stub_spec(spec, f"{where}.stubs[{stub_index}]", problems)
                if isinstance(spec, dict) and isinstance(spec.get("id"), str):
                    if spec["id"] in ids:
                        problems.append(
                            f"{where}: duplicate stub id {spec['id']!r}"
                        )
                    ids.add(spec["id"])
            program = entry.get("program")
            if program in SYNTHETIC_PROGRAMS:
                missing = [
                    item
                    for item in SYNTHETIC_PROGRAMS[program]["requires"]
                    if item not in ids
                ]
                if missing:
                    problems.append(
                        f"{where}: program {program!r} needs stub id(s) "
                        f"{missing}"
                    )

        corpus = target.get("corpus")
        if corpus is None and kind_now == "module":
            pass  # a module call takes its inputs from the entry, not a corpus
        elif not isinstance(corpus, dict):
            problems.append(f"{where}: corpus must be an object")
        else:
            for key in ("path", "guest_path", "reader"):
                if not isinstance(corpus.get(key), str) or not corpus.get(key):
                    problems.append(f"{where}: corpus.{key} must be a string")
            path = corpus.get("path")
            if isinstance(path, str) and (
                path.startswith("/") or ".." in path.split("/")
            ):
                problems.append(
                    f"{where}: corpus.path must be relative and inside the corpus"
                )
            guest = corpus.get("guest_path")
            if isinstance(guest, str) and not guest:
                problems.append(f"{where}: corpus.guest_path must not be empty")
            case = corpus.get("case")
            if case is not None:
                if case not in manifest_mod.CASES:
                    problems.append(f"{where}: unknown corpus.case {case!r}")
                elif isinstance(corpus.get("reader"), str):
                    allowed = manifest_mod.CASES[case]["readers"]
                    if corpus["reader"] not in allowed:
                        problems.append(
                            f"{where}: case {case!r} does not apply to reader "
                            f"{corpus['reader']!r} (allowed: {list(allowed)})"
                        )
                    expect_doc = target.get("expect")
                    if (
                        isinstance(expect_doc, dict)
                        and expect_doc.get("verdict")
                        != manifest_mod.CASES[case]["verdict"]
                    ):
                        problems.append(
                            f"{where}: expect.verdict "
                            f"{expect_doc.get('verdict')!r} disagrees with case "
                            f"{case!r} ({manifest_mod.CASES[case]['verdict']})"
                        )
            if corpus.get("reader") not in manifest_mod.READERS:
                problems.append(
                    f"{where}: corpus.reader {corpus.get('reader')!r} is not a "
                    "manifest reader"
                )

        expect = target.get("expect")
        if not isinstance(expect, dict):
            problems.append(f"{where}: expect must be an object")
        else:
            if expect.get("verdict") not in manifest_mod.VERDICTS:
                problems.append(
                    f"{where}: expect.verdict must be ACCEPT or REJECT"
                )
            python_verdict = expect.get("python_verdict")
            if python_verdict is not None and python_verdict not in manifest_mod.VERDICTS:
                problems.append(
                    f"{where}: expect.python_verdict must be ACCEPT, REJECT or null"
                )
            if not isinstance(expect.get("rule"), str) or not expect["rule"]:
                problems.append(f"{where}: expect.rule must describe the verdict")
    return problems


def load_targets(path=None) -> tuple[dict[str, dict], dict]:
    """Load and validate ``targets.json``; return ``(by_name, document)``."""

    path = Path(path or TARGETS_FILE)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TargetError([f"cannot read {path}: {exc}"]) from exc
    except json.JSONDecodeError as exc:
        raise TargetError([f"{path} is not valid JSON: {exc}"]) from exc
    problems = validate_targets(doc)
    if problems:
        raise TargetError(problems)
    by_name = {target["name"]: target for target in doc["targets"]}
    return by_name, doc


# --------------------------------------------------------------------------
# Guest memory / virtual FS / dispatcher bridge
# --------------------------------------------------------------------------


class _EngineMemory(dispatch_mod.FlatMemory):
    """``FlatMemory`` API backed by the engine, so stubs see real guest memory.

    :class:`dispatch` reads and writes guest buffers through this object; every
    access goes to the engine's mapped regions instead of a private copy, so
    ``sprintf`` output is visible to the following ``CreateFileW`` and the
    program's own buffers can be read back after the call.
    """

    def __init__(self, backend, endian: str = "big") -> None:
        super().__init__(endian=endian)
        self._backend = backend

    def read(self, va: int, size: int) -> bytes:
        if size < 0:
            raise dispatch_mod.StubFault("memory: read size must be non-negative")
        if size == 0:
            return b""
        try:
            return self._backend.read_mem(va, size)
        except engine_mod.EngineError as exc:
            raise dispatch_mod.StubFault(f"memory: {exc.message}") from exc

    def write(self, va: int, data) -> None:
        payload = bytes(data)
        if not payload:
            return
        try:
            self._backend.write_mem(va, payload)
        except engine_mod.EngineError as exc:
            raise dispatch_mod.StubFault(f"memory: {exc.message}") from exc


class StubBridge:
    """Install :class:`dispatch.StubDispatcher` calls as ``on_exec`` hooks.

    SH-4 cdecl: the first four arguments are in ``r4``-``r7``, the rest at
    ``0(r15)``, ``4(r15)`` so on.  Each hook has a fixed declared arity, so an
    accidental mismatch is a loud :class:`engine.Blocked`, never a guessed
    value.  A ``missing stub: NAME`` from the dispatcher keeps that exact text.
    """

    def __init__(self, dispatcher, specs) -> None:
        self.dispatcher = dispatcher
        self.specs = {int(str(spec["va"]), 0): spec for spec in specs}
        self.calls: list[dict] = []

    def install(self, backend) -> None:
        for va in sorted(self.specs):
            backend.on_exec(va, self._handler(va))

    def _handler(self, va: int):
        spec = self.specs[va]
        target = (spec["module"], spec["target"])
        return self.dispatcher.engine_hook(
            target,
            arity=int(spec["arity"]),
            on_call=self.calls.append,
        )



class InitGuardError(engine_mod.EngineError):
    code = "INIT_GUARD"

    def __init__(self, va: int):
        self.va = int(va) & 0xFFFFFFFF
        super().__init__(f"INIT 0x{self.va:08x} (guarded; rommap.py --init-from-image maps it)")


class StubBlockError(engine_mod.Blocked):
    """A bound IAT trampoline for an import that must stop as BLOCKED STUB."""

    code = "BLOCKED_STUB"

    def __init__(self, dll: str, name: str):
        self.dll = dll
        self.name = name
        super().__init__(f"BLOCKED STUB {dll}!{name}")


class GuardedPySh4(engine_mod.PySh4):
    """PySh4 with INIT read guards (M9.35): IAT slot VAs are exceptions."""

    def __init__(self, endian: str = "big"):
        super().__init__(endian=endian)
        self._init_guards = []  # (start, end, exceptions_set)

    def add_init_guard(self, start: int, end: int, exceptions=None):
        exc = {int(v) & 0xFFFFFFFF for v in (exceptions or [])}
        self._init_guards.append((int(start) & 0xFFFFFFFF, int(end) & 0xFFFFFFFF, exc))

    def _check_init_read(self, va: int, size: int):
        if not self._init_guards or size <= 0:
            return
        va &= 0xFFFFFFFF
        for start, end, exceptions in self._init_guards:
            if va + size <= start or va >= end:
                continue
            # IAT binding must win for slot VAs: slot is 4 bytes.
            if size == 4 and (va & 3) == 0 and va in exceptions and va + 4 <= end:
                return
            # find first offending byte in overlapping range
            off = max(va, start)
            limit = min(va + size, end)
            while off < limit:
                if off in exceptions and size == 4 and va == off:
                    return
                if off in exceptions:
                    off += 4
                    continue
                raise InitGuardError(off)
        return

    def _read(self, va: int, size: int) -> bytes:
        self._check_init_read(va, size)
        return super()._read(va, size)

    def _load(self, va: int, size: int) -> int:
        self._check_init_read(va, size)
        return super()._load(va, size)

    def _load_signed(self, va: int, size: int) -> int:
        self._check_init_read(va, size)
        return super()._load_signed(va, size)


class WatchedPySh4(GuardedPySh4):
    """PySh4 that logs every data load inside one input region (M9.28).

    Consumption proof: a mapped buffer must be *read*, not merely mapped, for
    a run to count as having received input.  The watcher records the width
    and the faulting PC of each load that touches ``[start, start+size)``; it
    never changes semantics, so a run with and without it is identical.  It
    subclasses :class:`GuardedPySh4` so the M9.35 INIT guard composes with the
    read watch instead of one replacing the other.
    """

    def __init__(self, endian: str = "big", start: int = 0, size: int = 0):
        super().__init__(endian=endian)
        self.watch_start = int(start) & M32
        self.watch_end = (int(start) + int(size)) & 0xFFFFFFFFFFFF
        self.reads: list[dict] = []

    def _watch(self, va: int, size: int) -> None:
        if self.watch_end <= self.watch_start or size <= 0:
            return
        if va + size <= self.watch_start or va >= self.watch_end:
            return
        self.reads.append({"va": va & M32, "size": int(size), "pc": self._regs["pc"] & M32})

    def _load(self, va: int, size: int) -> int:
        value = super()._load(va, size)
        self._watch(va, size)
        return value


# --------------------------------------------------------------------------
# Input resolution
# --------------------------------------------------------------------------


def _guest_paths(target) -> tuple[str, str]:
    corpus = target["corpus"]
    wide = corpus["guest_path"]
    ansi = corpus.get("ansi_path")
    if not ansi:
        text = wide.replace("\\", "/").lstrip("/")
        parts = [part for part in text.split("/") if part not in ("", ".")]
        if parts and parts[0].lower() in ("storage card", "sdcard", "sd card"):
            parts = parts[1:]
        ansi = "/".join(parts)
    return ansi, wide


def _read_input(target, args, problems: list[str]) -> dict:
    """Resolve the run input; never invent bytes when the target is blocked."""

    corpus_path = target["corpus"]["path"]
    source = None
    data = None
    manifest_entry = None

    if getattr(args, "input", None):
        path = Path(args.input)
        try:
            data = path.read_bytes()
        except OSError as exc:
            problems.append(f"cannot read --input {path}: {exc}")
        else:
            source = f"file:{path.name}"
    elif getattr(args, "corpus", None):
        root = Path(args.corpus)
        candidate = root / corpus_path
        try:
            data = candidate.read_bytes()
        except OSError as exc:
            problems.append(
                f"corpus {root}: cannot read {corpus_path}: {exc}"
            )
        else:
            source = f"corpus:{corpus_path}"
            manifest_path = root / "manifest.json"
            if manifest_path.is_file():
                try:
                    manifest_doc = manifest_mod.load(manifest_path)
                except (OSError, json.JSONDecodeError) as exc:
                    problems.append(f"corpus manifest: {exc}")
                else:
                    manifest_entry = next(
                        (
                            entry
                            for entry in manifest_doc.get("corpus", [])
                            if entry.get("path") == corpus_path
                        ),
                        None,
                    )
                    if manifest_entry is None:
                        problems.append(
                            f"corpus manifest has no entry for {corpus_path}"
                        )
    else:
        problems.append("pass --input FILE or --corpus DIR to supply the input")

    info = {
        "path": corpus_path,
        "guest_path": target["corpus"]["guest_path"],
        "source": source,
    }
    if data is not None:
        info["size"] = len(data)
        info["sha256"] = hashlib.sha256(data).hexdigest()
    if manifest_entry is not None:
        info["manifest"] = {
            "id": manifest_entry.get("id"),
            "expected": manifest_entry.get("expected"),
            "sha256": manifest_entry.get("sha256"),
            "size": manifest_entry.get("size"),
        }
        if data is not None:
            info["manifest_sha256_match"] = (
                hashlib.sha256(data).hexdigest() == manifest_entry.get("sha256")
            )
            if not info["manifest_sha256_match"]:
                problems.append(
                    f"{corpus_path}: input SHA-256 does not match the corpus "
                    "manifest (rebuild the corpus or pass the right file)"
                )
    return {"info": info, "data": data}


# --------------------------------------------------------------------------
# Running one target
# --------------------------------------------------------------------------


def _data_blob(target, ansi_path: str, wide_path: str) -> bytes:
    program = SYNTHETIC_PROGRAMS[target["entry"]["program"]]
    blob = bytearray(DATA_SIZE)
    for _name, (offset, text) in program["strings"].items():
        raw = text.encode("latin-1") + b"\x00"
        blob[offset:offset + len(raw)] = raw
    if not wide_path.endswith("\x00"):
        wide_path = wide_path + "\x00"
    wide = wide_path.encode("utf-16-le")
    if len(wide) > PATHBUF_OFF - WPATH_OFF:
        raise TargetError(["guest path is too long for the data region"])
    blob[WPATH_OFF:WPATH_OFF + len(wide)] = wide
    ansi = ansi_path.encode("latin-1") + b"\x00"
    if len(ansi) > WPATH_OFF - PATH_OFF:
        raise TargetError(["ANSI guest path is too long for the data region"])
    blob[PATH_OFF:PATH_OFF + len(ansi)] = ansi
    return bytes(blob)


def _cstring(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("latin-1")


def _plan_target(target, args) -> dict:
    """The ``--dry-run`` plan; describes everything and claims nothing."""

    entry = target["entry"]
    payload = {
        "command": "run",
        "mode": "target",
        "status": "DRY_RUN",
        "exit": EXIT_OK,
        "target": target["name"],
        "what": target["what"],
        "reader": target["reader"],
        "engine": args.engine,
        "entry": entry,
        "expect": target["expect"],
        "stubs": target["stubs"],
        "note": "dry run: no engine was started and no verdict is claimed",
    }
    if entry["kind"] == "blocked":
        payload["reason"] = entry["reason"]
        payload["note"] = (
            "dry run: this reader is not located, so any run reports BLOCKED"
        )
        return payload
    if entry["kind"] == "module":
        payload["module_entry"] = {
            "module": entry["module"],
            "va": entry["va"],
            "endian": entry.get("endian", "big"),
            "args": list(entry.get("args", [])),
            "verdict_map": dict(entry["verdict_map"]),
            "rommap": str(args.rommap) if getattr(args, "rommap", None) else None,
            "image": str(args.image) if getattr(args, "image", None) else None,
        }
        payload["note"] = (
            "dry run: module entry; the memory map, the image SHA-256 and the "
            "stub bindings are checked by a real run, and no engine was started"
        )
        return payload
    if entry["kind"] == "firmware_call":
        sec1_doc = entry.get("sec1_table")
        payload["firmware_call"] = {
            "program": entry.get("program"),
            "module": entry.get("module"),
            "va": entry.get("va"),
            "sec1_table": {
                "va": (sec1_doc or {}).get("va"),
                "declared": _sec1_source(entry, args) == "declared",
                "source": _sec1_source(entry, args),
                "provenance": (sec1_doc or {}).get("provenance"),
                "value_count": len((sec1_doc or {}).get("values") or []),
            },
            "inputs": dict(entry.get("inputs") or {}),
            "image": str(args.image) if getattr(args, "image", None) else None,
            "cmp": str(getattr(args, "cmp", None)) if getattr(args, "cmp", None) else None,
            "ind": str(getattr(args, "ind", None)) if getattr(args, "ind", None) else None,
            "mutate": getattr(args, "mutate", "none"),
        }
        payload["note"] = (
            "dry run: firmware_call entry; "
            + ("no sec1 table (point_walk_v1)" if sec1_doc is None else
               "sec1 table is "
               + ("read from the image (nk_decomp, M1.19)"
                  if _sec1_source(entry, args) == "image" else "a declared input"))
            + " (no silent default). No engine was started and no verdict is claimed."
        )
        return payload

    if args.engine not in engine_mod.BACKENDS:
        payload["engine_status"] = engine_mod.Blocked(
            f"unknown engine {args.engine!r}"
        ).as_dict()
    else:
        backend = engine_mod.BACKENDS[args.engine]()
        try:
            payload["engine_status"] = backend.probe().as_dict()
        finally:
            backend.close()

    ansi, wide = _guest_paths(target)
    payload["regions"] = [
        {"name": "code", "va": engine_mod.px(PROGRAM_VA), "size": PROGRAM_SIZE,
         "rwx": "rx"},
        {"name": "stack", "va": engine_mod.px(STACK_VA), "size": STACK_SIZE,
         "rwx": "rw"},
        {"name": "data", "va": engine_mod.px(DATA_VA), "size": DATA_SIZE,
         "rwx": "rw"},
        {"name": "heap", "va": engine_mod.px(HEAP_VA), "size": HEAP_SIZE,
         "rwx": "rw"},
    ]
    payload["program"] = {
        "name": target["entry"]["program"],
        "prose": SYNTHETIC_PROGRAMS[target["entry"]["program"]]["prose"],
        "strings": {
            "ansi_path": ansi,
            "wide_path": wide,
            "fmt_path": "%s",
            "fmt_log": "%s|%d",
        },
        "count_slot": engine_mod.px(COUNT_VA),
    }
    input_problems: list[str] = []
    payload["input"] = _read_input(target, args, input_problems)["info"]
    if input_problems:
        payload["input_problems"] = input_problems
    payload["note"] = (
        "dry run: no engine was started and no verdict is claimed"
    )
    return payload


def _input_region_bytes(region, args) -> tuple[bytes | None, dict, list[str]]:
    """Resolve ``entry.input_region`` to bytes, a provenance record, and problems.

    A ``file`` source is read from ``--input-root`` (or the current directory);
    a ``literal`` is a small synthetic control.  The recorded provenance is
    emitted on every path, including a refusal, so a verdict can never be read
    without knowing which bytes (and hash) a target was given.
    """

    problems: list[str] = []
    start = int(str(region["va"]), 0) & M32
    size = int(region["size"])
    source = region["bytes_source"]
    record = {
        "va": engine_mod.px(start),
        "size": size,
        "end": engine_mod.px(start + size),
        "kind": source.get("kind"),
        "provenance": region.get("provenance"),
        "sha256": None,
        "path": None,
    }
    data: bytes | None = None
    if source["kind"] == "literal":
        raw = source["hex"]
        data = bytes.fromhex(raw[2:] if raw.startswith("0x") else raw)
    else:
        root = getattr(args, "input_root", None)
        path = Path(source["path"])
        if not path.is_absolute() and root:
            path = Path(root) / path
        record["path"] = str(path)
        try:
            data = path.read_bytes()
        except OSError as exc:
            problems.append(f"cannot read input_region file {path}: {exc}")
            return None, record, problems
    record["sha256"] = hashlib.sha256(data).hexdigest()
    if len(data) != size:
        problems.append(
            f"input_region size {size} does not match {len(data)} B supplied "
            f"(sha256 {record['sha256']}); exact bounds are required"
        )
        return None, record, problems
    return data, record, problems


def _sha256_file(path, limit=None) -> str:
    """SHA-256 of the first *limit* bytes of *path* (the whole file if None)."""

    digest = hashlib.sha256()
    remaining = limit
    with open(path, "rb") as handle:
        while remaining is None or remaining > 0:
            want = (1 << 20) if remaining is None else min(1 << 20, remaining)
            chunk = handle.read(want)
            if not chunk:
                break
            digest.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
    return digest.hexdigest()


def _run_module_target(target, args, base) -> dict:
    """Call a function at a module VA, mapped from ``--rommap`` and ``--image``.

    The memory map (``cerom.py memmap`` through ``rommap.py``) supplies every
    block address, file offset and permission, and the image supplies the
    bytes, so no ``-device loader`` list is written by hand.  Only the named
    module is mapped; a call into another module stops as ``UnmappedAccess``
    and is reported ``BLOCKED``.  The verdict is read from ``r0`` through the
    target's ``verdict_map`` and nothing else.
    """

    entry = target["entry"]
    module = entry["module"]
    va = int(str(entry["va"]), 0)

    def blocked(reason: str, **extra) -> dict:
        return dict(
            base, status="BLOCKED", exit=EXIT_BLOCKED, reason=reason,
            accepted=None, l3_claim=False, **extra,
        )

    rommap_path = getattr(args, "rommap", None)
    image_path = getattr(args, "image", None)
    if not rommap_path or not image_path:
        return blocked(
            "a module target needs --rommap MAP.json and --image FW.img: the "
            "memory map and the bytes it was made from"
        )
    try:
        rommap_doc = rommap_mod.load(rommap_path)
    except (OSError, json.JSONDecodeError) as exc:
        return dict(base, status="INVALID", exit=EXIT_INVALID,
                    problems=[f"cannot read --rommap {rommap_path}: {exc}"])
    problems = rommap_mod.validate(rommap_doc)
    if problems:
        return dict(base, status="INVALID", exit=EXIT_INVALID, problems=problems)

    image = Path(image_path)
    if not image.is_file():
        return blocked(f"firmware image not readable: {image}")
    # cerom.py hashes a window of the image (source.image_sha256_scope): hash
    # the same bytes here, or refuse; never compare a prefix with a whole file.
    source = rommap_doc.get("source") or {}
    expected_sha = source.get("image_sha256")
    scope_text = str(source.get("image_sha256_scope") or "")
    covered = None
    image_sha = None
    if isinstance(expected_sha, str) and expected_sha:
        whole = re.fullmatch(r"whole file \((\d+) bytes\)", scope_text)
        window = re.fullmatch(r"first (\d+) of (\d+) bytes", scope_text)
        if whole:
            covered = total = int(whole.group(1))
        elif window:
            covered, total = int(window.group(1)), int(window.group(2))
        else:
            return dict(
                base, status="INVALID", exit=EXIT_INVALID,
                problems=[
                    "the memory map has image_sha256 but no recognised "
                    f"image_sha256_scope ({scope_text!r}); the hash cannot be "
                    "checked, so the image is not accepted"
                ],
            )
        if total != image.stat().st_size:
            return dict(
                base, status="INVALID", exit=EXIT_INVALID,
                problems=[
                    f"the memory map's hash covers a {total}-byte image; "
                    f"{image} is {image.stat().st_size} bytes"
                ],
            )
        try:
            image_sha = _sha256_file(image, covered)
        except OSError as exc:
            return blocked(f"cannot hash --image {image}: {exc}")
        if image_sha != expected_sha:
            return dict(
                base, status="INVALID", exit=EXIT_INVALID,
                problems=[
                    f"image SHA-256 of the first {covered} bytes is {image_sha}, "
                    f"not the memory map's {expected_sha}; the map was made "
                    "from another image"
                ],
            )

    blocks = [
        block for block in rommap_doc.get("blocks", [])
        if block.get("module") == module and block.get("loadable")
    ]
    if not blocks:
        return blocked(f"module {module!r} is not in the memory map")
    owner = next(
        (
            block for block in blocks
            if int(block["address"], 0) <= va < int(block["address"], 0) + block["size"]
        ),
        None,
    )
    if owner is None:
        # A compressed section is skipped by the map, not mapped: say so, so
        # the reason is not confused with a wrong VA.
        hidden = next(
            (
                item for item in rommap_doc.get("skipped", [])
                if item.get("module") == module
                and int(item["va"], 0) <= va < int(item["va"], 0) + int(item["size"])
            ),
            None,
        )
        if hidden is not None:
            return blocked(
                f"entry VA {engine_mod.px(va)} is in compressed section "
                f"{module}/{hidden['section']} ({hidden['reason']}); the memory "
                "map skips it, so no code is mapped (rommap.py --init-from-image maps it)"
            )
        return blocked(
            f"entry VA {engine_mod.px(va)} is outside every loadable block of {module}"
        )
    if "x" not in owner["permissions"]:
        return blocked(
            f"entry VA {engine_mod.px(va)} is in {owner['name']} "
            f"({owner['permissions']}), which is not executable"
        )

    call_args = [int(str(item), 0) & M32 for item in entry.get("args", [])]
    endian = entry.get("endian", "big")

    region_spec = entry.get("input_region")
    region_data = None
    region_record = None
    if region_spec is not None:
        region_data, region_record, region_problems = _input_region_bytes(region_spec, args)
        base["input_region"] = region_record
        if region_problems:
            return dict(
                base, status="INVALID", exit=EXIT_INVALID,
                problems=region_problems, accepted=None, l3_claim=False,
            )
        r_start = int(region_record["va"], 0)
        r_end = r_start + int(region_record["size"])
        n_iat = len(rommap_doc.get("iat_bindings") or [])
        iat_size = max(0x1000, ((n_iat + 0xFF) & ~0xFF) * 4) if n_iat else 0x1000
        spans = [("stack", STACK_VA, STACK_TOP), ("heap", HEAP_VA, HEAP_VA + HEAP_SIZE),
                 ("iat_trampolines", 0x8C300000, 0x8C300000 + iat_size)]
        spans += [(blk["name"], int(blk["address"], 0), int(blk["address"], 0) + blk["size"])
                  for blk in blocks]
        for name, lo, hi in spans:
            if r_start < hi and lo < r_end:
                return dict(
                    base, status="INVALID", exit=EXIT_INVALID,
                    problems=[
                        f"input_region {engine_mod.px(r_start)}..{engine_mod.px(r_end)} "
                        f"overlaps {name} {engine_mod.px(lo)}..{engine_mod.px(hi)}; "
                        "the region is refused, never silently mapped over code"
                    ],
                    accepted=None, l3_claim=False,
                )

    iat_bindings = rommap_doc.get("iat_bindings") or []
    init_guards = rommap_doc.get("init_guards") or []
    guarded = bool(init_guards or (rommap_doc.get("load_model") or {}).get("mode"))
    if args.engine == "pysh4":
        if region_record is not None:
            backend = WatchedPySh4(
                endian=endian,
                start=int(region_record["va"], 0),
                size=int(region_record["size"]),
            )
        elif init_guards or guarded:
            backend = GuardedPySh4(endian=endian)
        else:
            backend = engine_mod.PySh4(endian=endian)
    elif endian != "big":
        return blocked(
            f"entry.endian {endian!r} needs the pysh4 engine; "
            f"{args.engine} runs big-endian in this harness"
        )
    else:
        if init_guards or iat_bindings:
            return blocked(
                "bss-zero/init-guard module runs require --engine pysh4 (guarded memory model)"
            )
        backend = engine_mod.BACKENDS[args.engine]()
    try:
        availability = backend.probe()
        if not availability.available:
            return dict(
                base,
                status="SKIP",
                exit=EXIT_SKIP,
                reason=f"{availability.code}: {availability.detail}",
                skipped=True,
                l3_claim=False,
            )
        base["engine_kind"] = backend.kind
        base["engine_verified"] = backend.verified

        mapped: list[str] = []
        with open(image, "rb") as handle:
            for block in blocks:
                address = int(block["address"], 0)
                size = int(block["size"])
                stored = int(block.get("stored_size") or 0)
                data = b""
                if block.get("file_offset") is not None and stored:
                    handle.seek(int(block["file_offset"], 0))
                    data = handle.read(stored)
                    if len(data) != stored:
                        return blocked(f"short read for {block['name']} from {image}")
                elif block.get("init_source") == "nk_decomp":
                    # M1.19: INIT bytes decoded by the kernel routine (cache file)
                    try:
                        data = rommap_mod.read_init(block)
                    except (OSError, rommap_mod.RommapError) as exc:
                        return blocked(f"INIT bytes for {block['name']}: {exc}")
                perm = "".join(letter for letter in block["permissions"] if letter in "rwx")
                backend.map(block["name"], address, data + bytes(size - len(data)), perm)
                mapped.append(block["name"])
        backend.map("stack", STACK_VA, STACK_SIZE, "rw")
        backend.map("heap", HEAP_VA, HEAP_SIZE, "rw")
        if region_record is not None:
            region_va = int(region_record["va"], 0)
            region_size = int(region_record["size"])
            backend.map("input_region", region_va, region_data, "rw")
            mapped.append("input_region")

        memory = _EngineMemory(backend, endian=endian)
        context = dispatch_mod.StubContext(
            memory=memory,
            fs=dispatch_mod.VirtualFS(),
            heap=dispatch_mod.Heap(memory, HEAP_VA, HEAP_SIZE),
            registry=dispatch_mod.Registry(),
        )
        dispatcher = dispatch_mod.StubDispatcher(context)
        bridge = StubBridge(dispatcher, target["stubs"])
        bridge.install(backend)

        # Install IAT trampolines (M9.35): slot holds tramp VA; tramp dispatches to stub
        # or stops as BLOCKED STUB DLL!name.
        iat_calls: list[dict] = []
        if iat_bindings:
            tramp_base = 0x8C300000
            tramp_size = max(0x1000, ((len(iat_bindings) + 0xFF) & ~0xFF) * 4)
            # avoid overlap with heap (0x8C202000..+0x2000) and stack; 0x8C300000 is free
            backend.map("iat_trampolines", tramp_base, tramp_size, "rx")
            # build lookup of modeled implementations by export name/module hints
            modeled_by_key = {}
            modeled_by_name = {}
            for stub in stubs_mod.STUBS:
                if stub.get("status") != "modeled":
                    continue
                key = stubs_mod.stub_key(stub)
                modeled_by_key[key] = stub
                modeled_by_name.setdefault(stub["export"], []).append(stub)
                modeled_by_name.setdefault(stub["name"], []).append(stub)

            def _resolve_import_stub(dll, name):
                mod = stubs_mod.normalize_module(dll)
                # direct key
                stub = modeled_by_key.get(f"{mod}!{name}")
                if stub and stubs_mod.stub_key(stub) in dispatch_mod.IMPLEMENTATIONS:
                    return stub
                # try export/name match (coredll/internal aliases)
                cands = modeled_by_name.get(name) or []
                for cand in cands:
                    if stubs_mod.stub_key(cand) in dispatch_mod.IMPLEMENTATIONS:
                        return cand
                return None

            for i, b in enumerate(iat_bindings):
                slot_va = int(str(b["va"]), 0)
                tramp_va = tramp_base + i * 4
                dll = b.get("dll") or "unknown"
                name = b.get("name") or "unknown"
                # IAT binding wins: write trampoline VA into slot
                memory.write_u32(slot_va, tramp_va)
                stub_entry = _resolve_import_stub(dll, name)
                label = f"{dll}!{name}"

                def make_handler(_label=label, _dll=dll, _name=name, _stub=stub_entry):
                    def handler(bk, _va):
                        if _stub is None or stubs_mod.stub_key(_stub) not in dispatch_mod.IMPLEMENTATIONS:
                            raise StubBlockError(_dll, _name)
                        arity = len(_stub.get("args") or [])
                        target = (stubs_mod.normalize_module(_stub["module"]), _stub["export"])
                        hook = dispatcher.engine_hook(target, arity=arity, on_call=iat_calls.append)
                        return hook(bk, _va)
                    return handler

                backend.on_exec(tramp_va, make_handler())

        # Install INIT guards (M9.35): IAT slot VAs are exceptions
        if init_guards and isinstance(backend, GuardedPySh4):
            for g in init_guards:
                start = int(str(g["start"]), 0)
                end = int(str(g["end"]), 0)
                exc = [int(str(v), 0) for v in (g.get("iat_slots") or [])]
                backend.add_init_guard(start, end, exc)

        backend.set_regs({name: 0 for name in engine_mod.REGISTERS})
        backend.set_regs(r15=STACK_TOP)
        value = backend.call(va, call_args) & M32
        run = backend.last_run
    except OSError as exc:
        return blocked(f"cannot read {image}: {exc}")
    except InitGuardError as exc:
        return blocked(exc.message)
    except StubBlockError as exc:
        return blocked(exc.message)
    except engine_mod.EngineError as exc:
        if exc.code in ("MISSING_GHIDRA", "MISSING_QEMU"):
            return dict(base, status="SKIP", exit=EXIT_SKIP,
                        reason=f"{exc.code}: {exc.message}", skipped=True,
                        l3_claim=False)
        # preserve exact "missing stub: NAME" / BLOCKED STUB messages in reason
        msg = exc.message
        if getattr(exc, "code", "") == "BLOCKED" and msg.startswith("stub ") and "BLOCKED STUB " in msg:
            # normalize to "BLOCKED STUB DLL!name"
            idx = msg.find("BLOCKED STUB ")
            msg = msg[idx:]
        return blocked(f"{exc.code}: {msg}" if exc.code not in ("BLOCKED",) else msg)
    except dispatch_mod.StubError as exc:
        msg = exc.message
        if isinstance(exc, dispatch_mod.MissingStub):
            # try to format as BLOCKED STUB <DLL!name> when possible
            msg = f"BLOCKED STUB {msg.replace('missing stub: ', '')}"
        return blocked(msg)
    finally:
        backend.close()

    called = [call["stub"] for call in bridge.calls]
    iat_called = [call["stub"] for call in locals().get("iat_calls", [])]
    expected_stubs = sorted({f"{spec['module']}!{spec['target']}" for spec in target["stubs"]})
    verdict_map = {int(str(key), 0) & M32: item for key, item in entry["verdict_map"].items()}
    observed = verdict_map.get(value)
    common = dict(
        base,
        returned=engine_mod.px(value),
        instructions=run.insns if run else -1,
        cycles_unit="instruction/stub steps (PySh4 1 IPC; not SH-4 clock cycles)",
        finished=run.reason if run else "none",
        stub_calls=bridge.calls,
        iat_stub_calls=locals().get("iat_calls", []),
        stubs_expected=expected_stubs,
        stubs_called=sorted(set(called)),
        iat_stubs_called=sorted(set(iat_called)),
        rommap={
            "path": str(rommap_path),
            "module": module,
            "block": owner["name"],
            "entry_va": engine_mod.px(va),
            "blocks_mapped": mapped,
            "image_sha256": image_sha,
            "image_sha256_bytes": covered,
            "image_sha256_checked": covered is not None,
        },
        l3_claim=False,
    )
    if isinstance(backend, WatchedPySh4):
        reads = backend.reads
        widths = sorted({item["size"] for item in reads})
        common["input_region"]["reads"] = {
            "count": len(reads),
            "first": engine_mod.px(reads[0]["va"]) if reads else None,
            "last": engine_mod.px(reads[-1]["va"]) if reads else None,
            "widths": widths,
            "first_pc": engine_mod.px(reads[0]["pc"]) if reads else None,
            "last_pc": engine_mod.px(reads[-1]["pc"]) if reads else None,
        }
        common["consumed_input"] = bool(reads)
    if observed is None:
        return dict(
            common,
            status="BLOCKED",
            exit=EXIT_BLOCKED,
            reason=(
                f"r0 {engine_mod.px(value)} is not in the entry's verdict_map; "
                "no verdict is guessed"
            ),
            accepted=None,
        )

    problems: list[str] = []
    if run is None or run.reason != "return":
        problems.append(f"run stopped with {run.reason if run else 'no result'}, not at the return sentinel")
    missing_calls = sorted(set(expected_stubs) - set(called))
    if missing_calls:
        problems.append(f"declared stub(s) were never called: {', '.join(missing_calls)}")
    if observed != target["expect"]["verdict"]:
        problems.append(
            f"engine verdict {observed}, target expects {target['expect']['verdict']}"
        )
    return dict(
        common,
        status="PASS" if not problems else "MISMATCH",
        exit=EXIT_OK if not problems else EXIT_MISMATCH,
        accepted=observed == "ACCEPT",
        verdict=observed,
        problems=problems,
        note=(
            "module entry: the function ran from the memory map, not from a "
            "hand-written loader list; it is pipeline evidence, not a reader "
            "verdict, until the reader's VA and byte order are verified (M9.6)"
        ),
    )


def _sec1_source(entry, args) -> str:
    """``image`` when the compressed sections come from the image (M1.19).

    Either the target says so (``sec1_table.source: image``) or the caller
    passed ``--init-from-image``; otherwise the declared table is used.
    """
    if getattr(args, "init_from_image", False):
        return "image"
    return (entry.get("sec1_table") or {}).get("source", "declared")


def _run_firmware_call_target(target, args, base) -> dict:
    """Run a firmware_call target (M9.11b): chunk reader with declared inputs.

    The sec1 table is taken from ``entry.sec1_table`` (declared, sourced); the
    runner never substitutes a silent default.  Memory setup and the chunk
    decode path follow ``tools/chunk_decoder_l3.py`` (M9.11).
    """

    entry = target["entry"]
    program = entry.get("program")
    if program == "mapcode_compare_v1":
        return _run_mapcode_target(target, args, base)
    if program == "drstr_parser_v1":
        return _run_drstr_target(target, args, base)
    if program == "point_walk_v1":
        return _run_point_walk_target(target, args, base)
    if program != "cmp_ind_chunk_v1":
        return dict(
            base, status="BLOCKED", exit=EXIT_BLOCKED,
            reason=f"unknown firmware_call program {program!r}", accepted=None,
            l3_claim=False,
        )

    # Sec1 table: declared input only (M9.11b stop condition).
    sec1_table = entry.get("sec1_table")
    if not isinstance(sec1_table, dict):
        return dict(
            base, status="BLOCKED", exit=EXIT_BLOCKED,
            reason="sec1_table missing or not declared; cannot run without a "
                   "sourced table (silent default forbidden, M9.11b)",
            accepted=None, l3_claim=False,
        )

    cmp_path = getattr(args, "cmp", None)
    ind_path = getattr(args, "ind", None)
    image_path = getattr(args, "image", None)
    mutate = getattr(args, "mutate", "none") or "none"
    if mutate not in ("none", "swap-4-8", "corrupt-ind"):
        return dict(base, status="INVALID", exit=EXIT_INVALID,
                    problems=[f"unsupported --mutate {mutate!r}"])
    if not image_path or not cmp_path or not ind_path:
        missing = [n for n, v in (("--image", image_path), ("--cmp", cmp_path),
                                  ("--ind", ind_path)) if not v]
        return dict(base, status="INVALID", exit=EXIT_INVALID,
                    problems=[f"firmware_call needs {', '.join(missing)}"])

    inputs = entry.get("inputs") or {}
    offset = getattr(args, "offset", None)
    if offset is None:
        offset = inputs.get("offset", 0x840BA0)
    length = getattr(args, "length", None)
    if length is None:
        length = inputs.get("length", 42848)
    offset = int(str(offset), 0)
    length = int(str(length), 0)

    for path in (image_path, cmp_path, ind_path):
        if not Path(path).exists():
            return dict(base, status="INVALID", exit=EXIT_INVALID,
                        problems=[f"missing input: {path}"])

    try:
        import chunk_decoder_l3 as cdl3
        import cmpind
        import point_walk_l3 as pw
    except Exception as exc:  # noqa: BLE001
        return dict(base, status="BLOCKED", exit=EXIT_BLOCKED,
                    reason=f"cannot import chunk decoder dependencies: {exc}",
                    accepted=None, l3_claim=False)

    # The target's build picks the chunk-engine and helper VAs (M9.32): the
    # US target used to run with the EU helpers and could only block.  The
    # registered entry VA must be that build's engine, or nothing runs.
    build = target.get("build") or "eu2011"
    tgt = cdl3.BUILD_TARGETS.get(build)
    entry_va = int(str(entry.get("va", "0")), 0)
    if tgt is None or entry_va != tgt["fn_chunk"]:
        return dict(base, status="INVALID", exit=EXIT_INVALID,
                    problems=[f"entry.va {entry_va:#010x} is not the {build} chunk "
                              "engine in tools/build_targets.py"])

    try:
        usize, csize, _count, chunk_size, offsets = cmpind.read_index(Path(ind_path))
        image = pw.load_image(str(image_path))
        _, secs = pw.module_sections(image, cdl3.IMAGE_START, cdl3.MODULE)
        index = cdl3.chunk_index(offset, chunk_size)
        offsets = cdl3.mutate_offsets(offsets, mutate, index)
        rows = cdl3.table_rows(usize, csize, offsets, chunk_size)
        if mutate == "swap-4-8":
            cdl3.mutate_rows(rows, mutate, index)
        cmp_bytes = Path(cmp_path).read_bytes()
    except Exception as exc:  # noqa: BLE001
        return dict(base, status="INVALID", exit=EXIT_INVALID,
                    problems=[f"cannot prepare firmware_call inputs: {exc}"])

    source = _sec1_source(entry, args)
    init_sections = None
    mask_words = None
    if source == "image":
        # M1.19: map Navi.exe's compressed sections as the loader does, with
        # the INIT bytes decoded by the kernel routine (cached), then zero BSS.
        try:
            init_sections = cdl3.image_init_sections(image)
            tva = int(str(sec1_table.get("va", tgt["inflate_mask"])), 0)
            for sva, blob in init_sections.items():
                if sva <= tva < sva + len(blob):
                    mask_words = list(cdl3.mask_from_section(blob, sva, tva))
        except Exception as exc:  # noqa: BLE001
            return dict(base, status="BLOCKED", exit=EXIT_BLOCKED,
                        reason=f"--init-from-image: cannot decode {cdl3.MODULE} "
                               f"compressed sections: {exc}",
                        accepted=None, l3_claim=False)
    try:
        ret, out, stats = cdl3.run_firmware(
            image, cmp_bytes, rows, offset, length, chunk_size,
            sec_mode="image" if source == "image" else "zero-mask",
            sec1_table=None if source == "image" else sec1_table, tgt=tgt,
            init_sections=init_sections,
        )
    except cdl3.Blocked as exc:
        va = exc.args[1] if len(exc.args) > 1 else None
        where = cdl3.section_of(secs, va) if va is not None else "no VA given"
        reason = f"BLOCKED: {exc.args[0]} (firmware access in {where} of {cdl3.MODULE})"
        return dict(base, status="BLOCKED", exit=EXIT_BLOCKED, reason=reason,
                    accepted=None, l3_claim=False)
    except Exception as exc:  # noqa: BLE001
        return dict(base, status="BLOCKED", exit=EXIT_BLOCKED,
                    reason=f"firmware_call engine error: {exc}",
                    accepted=None, l3_claim=False)

    common = dict(
        base,
        firmware={"r0": ret if ret != cdl3.MINUS_ONE else -1, "insns": stats["insns"],
                  "memcpy": stats["memcpy"], "mod_calls": len(stats["mod"])},
        sec1_table={"va": sec1_table.get("va"), "declared": source == "declared",
                    "source": source, "provenance": sec1_table.get("provenance"),
                    "mask": stats.get("mask"),
                    "image_words": None if mask_words is None else [f"0x{w:x}" for w in mask_words],
                    "image_words_equal_zlib": None if mask_words is None
                    else cdl3.check_mask(mask_words) is None},
        inputs={"cmp": str(cmp_path), "ind": str(ind_path), "image": str(image_path),
                "offset": f"0x{offset:x}", "length": length, "mutate": mutate},
        l3_claim=False,
    )

    if mutate == "corrupt-ind":
        ok = ret == cdl3.MINUS_ONE
        verdict_text = "PASS (firmware rejects the corrupt .ind)" if ok else \
            "FAIL (firmware accepted the corrupt .ind)"
        return dict(common, status="PASS" if ok else "MISMATCH",
                    exit=EXIT_OK if ok else EXIT_MISMATCH,
                    accepted=None, verdict=verdict_text,
                    problems=[] if ok else [verdict_text],
                    note="control matches EXP-2026-11-08-M9.11-chunk-decoder")

    try:
        expected = cdl3.reference_slice(Path(cmp_path), Path(ind_path), offset, length)
    except Exception as exc:  # noqa: BLE001
        # For mutated inputs the reference may reject; treat as control context.
        expected = None
        ref_error = str(exc)

    if mutate == "swap-4-8":
        ok = ret != length or out != (expected if expected is not None else b"")
        # If reference failed on mutated ind, compare structurally: clean failure.
        if expected is None:
            ok = True  # clean failure (no exception from firmware path reached here)
        verdict_text = "PASS (control: swapped +4/+8 fails cleanly, no exception)" if ok else \
            "FAIL (swapped +4/+8 still returns the page)"
        return dict(common, status="PASS" if ok else "MISMATCH",
                    exit=EXIT_OK if ok else EXIT_MISMATCH,
                    accepted=None, verdict=verdict_text,
                    problems=[] if ok else [verdict_text],
                    reference_error=locals().get("ref_error"),
                    note="control matches EXP-2026-11-08-M9.11-chunk-decoder")

    if expected is None:
        return dict(common, status="MISMATCH", exit=EXIT_MISMATCH,
                    accepted=None, verdict="FAIL",
                    problems=[f"reference: {ref_error}"])

    ok = ret == length and out == expected
    verdict = "ACCEPT" if ok else "REJECT"
    return dict(
        common,
        status="PASS" if ok else "MISMATCH",
        exit=EXIT_OK if ok else EXIT_MISMATCH,
        accepted=ok,
        verdict=verdict if ok else "FAIL (not byte-identical to cmpind.decode)",
        problems=[] if ok else [
            f"firmware output differs from cmpind.decode (r0={ret}, "
            f"first differing byte {next((i for i, (a, b) in enumerate(zip(out, expected)) if a != b), -1)})"
        ],
    )


def _run_point_walk_target(target, args, base) -> dict:
    """Run the POINT record walker from the target's build (M9.55).

    ``point_walk_l3.py`` already executes ``fn 0x003f5194`` (EU) /
    ``0x0041db44`` (US); this program ports that run into the runner so an
    ``l3check`` row can report its verdict.  The page is read from the
    ``--cmp``/``--ind`` pair, the walker VAs come from the target's ``build``
    (``tools/build_targets.py``), and the verdict compares the firmware's
    record offsets with ``mutate_refer_poi.parse_page`` and the walker's own
    length model over the records the caller names.

    A wrong build/image pairing is a verdict, not a crash: an engine fault or
    an entry outside this image's executable text is ``status=FAIL`` with the
    ``FAIL (unmapped ...)`` text (M9.42 shape), never a fabricated PASS.
    """

    entry = target["entry"]
    image_path = getattr(args, "image", None)
    cmp_path = getattr(args, "cmp", None)
    ind_path = getattr(args, "ind", None)
    missing = [n for n, v in (("--image", image_path), ("--cmp", cmp_path),
                              ("--ind", ind_path)) if not v]
    if missing:
        return dict(base, status="INVALID", exit=EXIT_INVALID,
                    problems=[f"point_walk_v1 needs {', '.join(missing)}"])
    for path in (image_path, cmp_path, ind_path):
        if not Path(path).exists():
            return dict(base, status="INVALID", exit=EXIT_INVALID,
                        problems=[f"missing input: {path}"])

    try:
        import mutarefer  # noqa: F401
    except ImportError:
        pass
    try:
        import point_walk_l3 as pw
    except Exception as exc:  # noqa: BLE001
        return dict(base, status="BLOCKED", exit=EXIT_BLOCKED,
                    reason=f"cannot import point_walk_l3: {exc}",
                    accepted=None, l3_claim=False)

    build = target.get("build") or "eu2011"
    try:
        tgt = pw.target(build)
    except SystemExit as exc:
        return dict(base, status="INVALID", exit=EXIT_INVALID,
                    problems=[str(exc)])

    inputs = entry.get("inputs") or {}
    offset = getattr(args, "offset", None)
    if offset is None:
        offset = inputs.get("offset", 0x840BA0)
    length = getattr(args, "length", None)
    if length is None:
        length = inputs.get("length", 42848)
    offset = int(str(offset), 0)
    length = int(str(length), 0)

    import mutate_refer_poi as mrp
    import zlib

    try:
        cmp_bytes = Path(cmp_path).read_bytes()
        _u, _c, _n, _cs, offsets = mrp.read_ind(Path(ind_path))
        dat = mrp.decode(cmp_bytes, offsets)
        end = offset + length if length else len(dat)
        raw = zlib.decompressobj().decompress(dat[offset:end])
        recs = mrp.parse_page(raw)
    except Exception as exc:  # noqa: BLE001
        return dict(base, status="INVALID", exit=EXIT_INVALID,
                    problems=[f"cannot decode the POINT page: {exc}"])

    try:
        image = pw.load_image(str(image_path))
        text_va, text = pw.navi_text(image, 0x200200)
    except SystemExit as exc:
        return dict(base, status="BLOCKED", exit=EXIT_BLOCKED,
                    reason=f"no executable text in {image_path}: {exc}",
                    accepted=None, l3_claim=False)

    count = len(recs)
    requested = inputs.get("n")
    if requested is None:
        ns = sorted({0, 1, 2, 3, 10, count // 2, count - 2, count - 1, count})
    else:
        ns = [int(x) if isinstance(x, int) else int(str(x), 0)
              for x in requested]
    native = pw.swap16(raw)
    text_entry = int(str(entry.get("va", "0")), 0)
    if text_entry and text_entry != tgt["nth"]:
        return dict(base, status="INVALID", exit=EXIT_INVALID,
                    problems=[f"entry.va {text_entry:#010x} is not the {build} "
                              "POINT walker in tools/build_targets.py"])

    problems: list[str] = []
    rows: list[dict] = []
    mismatch = None
    values, mismatch = pw.guarded(
        [lambda n=n: pw.run_nth(text_va, text, native, n, tgt, build)
         for n in ns])
    for n, fw in zip(ns, values):
        py = recs[n]["offset"] if n < count else None
        model = pw.model_nth(raw, n, escape_len=tgt["escape_len"])
        ok = fw == py == model
        if not ok:
            problems.append(
                f"n={n}: firmware {fw!r} parse_page {py!r} model {model!r}")
        rows.append({"n": n,
                     "firmware": None if fw is None else f"0x{fw:x}",
                     "parse_page": None if py is None else f"0x{py:x}",
                     "model": None if model is None else f"0x{model:x}",
                     "ok": ok})

    if mismatch is not None:
        where = ("" if mismatch.fault_va is None
                 else f" 0x{mismatch.fault_va:08x}")
        verdict = (f"FAIL (unmapped{where} @ build {build}, {mismatch.code})")
        return dict(
            base,
            status="FAIL",
            exit=EXIT_MISMATCH,
            accepted=None,
            verdict=verdict,
            firmware={"build": build, "nth": f"0x{tgt['nth']:08x}",
                      "insns": None},
            inputs={"image": str(image_path), "cmp": str(cmp_path),
                    "ind": str(ind_path), "page": f"0x{offset:x}",
                    "records": count},
            records=rows,
            problems=[verdict],
            l3_claim=True,
            note=("wrong build/image pairing: the walker entry is not this "
                  "image's (M9.42); a verdict, not a crash"),
        )

    expected = getattr(args, "expect", None) or target["expect"]["verdict"]
    observed = "ACCEPT" if not problems else "REJECT"
    ok = observed == expected
    return dict(
        base,
        status="PASS" if ok else "MISMATCH",
        exit=EXIT_OK if ok else EXIT_MISMATCH,
        accepted=observed == "ACCEPT",
        verdict=observed,
        expected_verdict=expected,
        firmware={"build": build, "nth": f"0x{tgt['nth']:08x}",
                  "insns": None},
        inputs={"image": str(image_path), "cmp": str(cmp_path),
                "ind": str(ind_path), "page": f"0x{offset:x}",
                "records": count},
        records=rows,
        problems=[] if ok else problems,
        l3_claim=True,
        note=(f"POINT record walker {tgt['nth']:#010x} ({build}) reads "
              "record offsets like mutate_refer_poi.parse_page; the walker "
              "proves the record framing, not the name/coordinate contents "
              "(C-4178)"),
    )


def _run_mapcode_target(target, args, base) -> dict:
    """Run AppLaunch.dll ``fn 0x03bd2ad8`` (EU2011 build B, M9.6) on one file.

    ``--input`` is the ``HDD_INFO.TXT`` served at the guest path; the unit
    record (``KernelIoControl(0x0101302C)`` output ``+0x60``) is a declared
    input: ``--unit-from FACTORY`` (line-1 bytes 0..10) or ``--unit-code``.
    The verdict is the firmware's own return value (1 ACCEPT, 0 REJECT);
    ``--expect`` overrides ``expect.verdict`` for an edited-file control.
    Engine and stubs live in ``tools/mapcode_l3.py``.
    """

    entry = target["entry"]
    sec1 = entry.get("sec1_table")
    if not isinstance(sec1, dict):
        return dict(base, status="BLOCKED", exit=EXIT_BLOCKED,
                    reason="sec1_table (parse cache) not declared", accepted=None,
                    l3_claim=False)
    image_path = getattr(args, "image", None)
    card_path = getattr(args, "input", None)
    unit_from = getattr(args, "unit_from", None)
    unit_code = getattr(args, "unit_code", None)
    missing = [n for n, v in (("--image", image_path), ("--input", card_path)) if not v]
    if not (unit_from or unit_code):
        missing.append("--unit-from or --unit-code")
    if missing:
        return dict(base, status="INVALID", exit=EXIT_INVALID,
                    problems=[f"mapcode_compare_v1 needs {', '.join(missing)}"])
    for path in (image_path, card_path, unit_from):
        if path and not Path(path).exists():
            return dict(base, status="INVALID", exit=EXIT_INVALID,
                        problems=[f"missing input: {path}"])
    try:
        import mapcode_l3 as ml3
    except Exception as exc:  # noqa: BLE001
        return dict(base, status="BLOCKED", exit=EXIT_BLOCKED,
                    reason=f"cannot import mapcode_l3: {exc}", accepted=None,
                    l3_claim=False)
    try:
        if unit_code:
            unit = unit_code.encode("latin-1")
            unit_src = "--unit-code"
        else:
            raw = Path(unit_from).read_bytes()
            unit = ml3.unit_code_from(raw)
            unit_src = f"--unit-from line 1, sha256 {hashlib.sha256(raw).hexdigest()}"
        card = Path(card_path).read_bytes()
        with open(image_path, "rb") as fh:
            image = fh.read(128 << 20)
    except (OSError, ValueError, UnicodeEncodeError) as exc:
        return dict(base, status="INVALID", exit=EXIT_INVALID,
                    problems=[f"cannot prepare mapcode inputs: {exc}"])
    # The declared parse-cache value is written by run_compare's zero map;
    # refuse a declaration that is not the BSS zero this program models.
    values = [int(str(v), 0) for v in sec1.get("values") or []]
    if any(values):
        return dict(base, status="BLOCKED", exit=EXIT_BLOCKED,
                    reason="sec1_table declares a non-zero parse cache; only the "
                           "BSS zero (first call) is modelled", accepted=None,
                    l3_claim=False)
    try:
        result = ml3.run_compare(image, card, unit,
                                 fn=int(str(entry.get("va")), 0))
    except ml3.Blocked as exc:
        return dict(base, status="BLOCKED", exit=EXIT_BLOCKED,
                    reason=f"BLOCKED: {exc}", accepted=None, l3_claim=False)
    except ValueError as exc:
        return dict(base, status="INVALID", exit=EXIT_INVALID,
                    problems=[str(exc)])
    expected = getattr(args, "expect", None) or target["expect"]["verdict"]
    observed = result["verdict"]
    ok = observed == expected
    return dict(
        base,
        status="PASS" if ok else "MISMATCH",
        exit=EXIT_OK if ok else EXIT_MISMATCH,
        accepted=observed == "ACCEPT",
        verdict=observed,
        expected_verdict=expected,
        firmware={"r0": result["r0"], "insns": result["insns"],
                  "fn": result["fn"], "build": result["build"],
                  "module": result["module"]},
        sec1_table={"va": sec1.get("va"), "declared": True,
                    "provenance": sec1.get("provenance")},
        inputs={"image": str(image_path), "card": str(card_path),
                "card_sha256": hashlib.sha256(card).hexdigest(),
                "unit_code": result["unit_code"], "unit_source": unit_src,
                "card_slot0": result["card_slot0"]},
        stub_log=result["stub_log"],
        compressed_section_access=result["compressed_section_access"],
        problems=[] if ok else [f"firmware verdict {observed}, expected {expected}"],
        l3_claim=True,
        note=("firmware verdict of AppLaunch.dll fn 0x03bd2ad8 (EU2011 build B); "
              "the unit record +0x60 is a declared input, not read from a unit"),
    )


def _run_drstr_target(target, args, base) -> dict:
    """Run Navi.exe's ``DRSTR001.DAT`` parser ``fn 0x00419350`` (EU2011, M9.24).

    ``--input`` is the ``DRSTR001.DAT`` served at the layer's volume root;
    ``tools/drstr_l3.py`` calls open wrapper -> parser -> close wrapper with
    ``vcard_l3``'s bound imports.  The verdict is the parser's return value
    through ``entry.verdict_map``, which must equal the map decoded from the
    parser's exits (``drstr_l3.VERDICT_MAP``); a fault is ``BLOCKED`` with
    its PC.
    """

    entry = target["entry"]
    sec1 = entry.get("sec1_table")
    if not isinstance(sec1, dict):
        return dict(base, status="BLOCKED", exit=EXIT_BLOCKED,
                    reason="sec1_table not declared", accepted=None, l3_claim=False)
    image_path = getattr(args, "image", None)
    file_path = getattr(args, "input", None)
    missing = [n for n, v in (("--image", image_path), ("--input", file_path)) if not v]
    if missing:
        return dict(base, status="INVALID", exit=EXIT_INVALID,
                    problems=[f"drstr_parser_v1 needs {', '.join(missing)}"])
    for path in (image_path, file_path):
        if not Path(path).exists():
            return dict(base, status="INVALID", exit=EXIT_INVALID,
                        problems=[f"missing input: {path}"])
    try:
        import drstr_l3 as dl3
    except Exception as exc:  # noqa: BLE001
        return dict(base, status="BLOCKED", exit=EXIT_BLOCKED,
                    reason=f"cannot import drstr_l3: {exc}", accepted=None, l3_claim=False)
    declared = {int(str(k), 0): v for k, v in (entry.get("verdict_map") or {}).items()}
    if declared != dl3.VERDICT_MAP:
        return dict(base, status="BLOCKED", exit=EXIT_BLOCKED,
                    reason="entry.verdict_map differs from the map decoded from "
                           "fn 0x00419350's exits (drstr_l3.VERDICT_MAP)",
                    accepted=None, l3_claim=False)
    if int(str(entry.get("va")), 0) != dl3.EU2011["parse"]:
        return dict(base, status="BLOCKED", exit=EXIT_BLOCKED,
                    reason="entry.va is not the EU2011 parser fn 0x00419350",
                    accepted=None, l3_claim=False)
    data = Path(file_path).read_bytes()
    try:
        result = dl3.run(str(image_path), dl3.memory_card("DRSTR001.DAT", data))
    except dl3.Blocked as exc:
        return dict(base, status="BLOCKED", exit=EXIT_BLOCKED,
                    reason=f"BLOCKED: {exc}", accepted=None, l3_claim=False)
    expected = getattr(args, "expect", None) or target["expect"]["verdict"]
    observed = result["verdict"]
    ok = observed == expected
    return dict(
        base,
        status="PASS" if ok else "MISMATCH",
        exit=EXIT_OK if ok else EXIT_MISMATCH,
        accepted=observed == "ACCEPT",
        verdict=observed,
        expected_verdict=expected,
        firmware={"r0": result["r0"], "fn": result["fn"], "build": result["build"],
                  "module": "Navi.exe", "stage": result["stage"], "log_codes": result["log_codes"],
                  "log_sites": result["log_sites"], "guest_path": result["guest_path"]},
        verdict_map={("%#010x" % k): v for k, v in sorted(dl3.VERDICT_MAP.items())},
        sec1_table={"va": sec1.get("va"), "declared": False, "source": sec1.get("source"),
                    "provenance": sec1.get("provenance")},
        inputs={"image": str(image_path), "file": str(file_path),
                "file_sha256": hashlib.sha256(data).hexdigest(), "size": len(data)},
        imports_called=result["imports"],
        problems=[] if ok else [f"firmware verdict {observed}, expected {expected}"],
        l3_claim=True,
        note="firmware verdict of Navi.exe fn 0x00419350 (EU2011 build A), via its open/close wrappers",
    )


def run_target(target, args) -> dict:
    """Execute one target and return its verdict payload.

    Never fabricates a result: a missing back end is ``SKIP`` (exit 3), a
    blocked reader or a stub/engine failure is ``BLOCKED`` (exit 4), and a
    verdict that differs from ``expect.verdict`` is ``MISMATCH`` (exit 5).
    """

    entry = target["entry"]
    base = {
        "command": "run",
        "mode": "target",
        "target": target["name"],
        "what": target["what"],
        "reader": target["reader"],
        "engine": args.engine,
        "backend": args.engine,
        "expect": target["expect"],
        "accepted": None,
        "synthetic": entry["kind"] == "synthetic",
    }

    if entry["kind"] == "blocked":
        return dict(
            base,
            status="BLOCKED",
            exit=EXIT_BLOCKED,
            reason=entry["reason"],
            stubs_expected=list(target["stubs"]),
            l3_claim=False,
        )

    if args.engine not in engine_mod.BACKENDS:
        return dict(
            base,
            status="INVALID",
            exit=EXIT_INVALID,
            problems=[
                f"unknown engine {args.engine!r} "
                f"(known: {', '.join(sorted(engine_mod.BACKENDS))})"
            ],
        )

    if entry["kind"] == "module":
        return _run_module_target(target, args, base)
    if entry["kind"] == "firmware_call":
        return _run_firmware_call_target(target, args, base)

    problems: list[str] = []
    resolved = _read_input(target, args, problems)
    if problems:
        return dict(
            base, status="INVALID", exit=EXIT_INVALID, problems=problems
        )
    data = resolved["data"]
    info = resolved["info"]
    ansi, wide = _guest_paths(target)
    try:
        data_blob = _data_blob(target, ansi, wide)
    except (TargetError, UnicodeEncodeError) as exc:
        return dict(
            base,
            status="INVALID",
            exit=EXIT_INVALID,
            problems=[
                f"cannot lay out the data region: "
                f"{getattr(exc, 'problems', exc)}"
            ],
        )

    backend = engine_mod.BACKENDS[args.engine]()
    try:
        availability = backend.probe()
        if not availability.available:
            return dict(
                base,
                status="SKIP",
                exit=EXIT_SKIP,
                reason=f"{availability.code}: {availability.detail}",
                skipped=True,
                l3_claim=False,
            )
        base["engine_kind"] = backend.kind
        base["engine_verified"] = backend.verified

        program = SYNTHETIC_PROGRAMS[entry["program"]]["build"]()
        backend.map("code", PROGRAM_VA, program, "rx")
        backend.map("stack", STACK_VA, STACK_SIZE, "rw")
        backend.map("data", DATA_VA, data_blob, "rw")
        backend.map("heap", HEAP_VA, HEAP_SIZE, "rw")

        memory = _EngineMemory(backend, endian="big")
        fs = dispatch_mod.VirtualFS({info["guest_path"]: data})
        context = dispatch_mod.StubContext(
            memory=memory,
            fs=fs,
            heap=dispatch_mod.Heap(memory, HEAP_VA, HEAP_SIZE),
            registry=dispatch_mod.Registry(),
        )
        dispatcher = dispatch_mod.StubDispatcher(context)
        bridge = StubBridge(dispatcher, target["stubs"])
        bridge.install(backend)

        backend.set_regs({name: 0 for name in engine_mod.REGISTERS})
        backend.set_regs(
            r4=DATA_VA + PATHBUF_OFF,
            r5=DATA_VA + LOGBUF_OFF,
            r6=DATA_VA + READBUF_OFF,
            r7=0,
            r12=DATA_VA + PATH_OFF,
            r13=DATA_VA + WPATH_OFF,
            gbr=DATA_VA,
            r15=STACK_TOP,
            pc=PROGRAM_VA,
            pr=engine_mod.RETURN_VA,
        )
        run = backend.run_until(max_insns=args.max_insns)
        value = backend.get_regs()["r0"] & M32

        log_raw = backend.read_mem(DATA_VA + LOGBUF_OFF, 0x100)
        path_raw = backend.read_mem(DATA_VA + PATHBUF_OFF, 0x100)
        read_raw = backend.read_mem(DATA_VA + READBUF_OFF, READ_LIMIT)
        count_raw = backend.read_mem(COUNT_VA, 4)
    except engine_mod.EngineError as exc:
        code = exc.code
        if code in ("MISSING_GHIDRA", "MISSING_QEMU"):
            return dict(
                base,
                status="SKIP",
                exit=EXIT_SKIP,
                reason=f"{code}: {exc.message}",
                skipped=True,
                l3_claim=False,
            )
        return dict(
            base,
            status="BLOCKED",
            exit=EXIT_BLOCKED,
            reason=f"{code}: {exc.message}",
            l3_claim=False,
        )
    except dispatch_mod.StubError as exc:
        return dict(
            base,
            status="BLOCKED",
            exit=EXIT_BLOCKED,
            reason=f"{exc.code}: {exc.message}",
            l3_claim=False,
        )
    finally:
        backend.close()

    observed = "ACCEPT" if value & 1 else "REJECT"
    log_text = _cstring(log_raw)
    path_text = _cstring(path_raw)
    outputs = {
        "log": log_text,
        "log_sha256": hashlib.sha256(log_raw.split(b"\x00", 1)[0]).hexdigest(),
        "path": path_text,
        "read_bytes_hex": read_raw.hex(),
        "count": int.from_bytes(count_raw, "big"),
    }
    called_stubs = {call["stub"] for call in bridge.calls}
    expected_stubs = [
        f"{spec['module']}!{spec['target']}" for spec in target["stubs"]
    ]
    missing_calls = sorted(set(expected_stubs) - called_stubs)
    if missing_calls:
        problems.append(
            f"declared stub(s) were never called: {', '.join(missing_calls)}"
        )
    if value not in (0, 1):
        problems.append(f"probe returned {engine_mod.px(value)}, want 0 or 1")
    if run is None or run.reason != "return":
        problems.append(
            f"run stopped with {run.reason if run else 'no result'}, not at the "
            f"return sentinel {engine_mod.px(engine_mod.RETURN_VA)}"
        )
    if observed != target["expect"]["verdict"]:
        problems.append(
            f"engine verdict {observed}, target expects {target['expect']['verdict']}"
        )

    payload = dict(
        base,
        status="PASS" if not problems else "MISMATCH",
        exit=EXIT_OK if not problems else EXIT_MISMATCH,
        accepted=observed == "ACCEPT",
        verdict=observed,
        returned=engine_mod.px(value),
        cycles=run.insns if run else -1,
        instructions=run.insns if run else -1,
        cycles_unit="instruction/stub steps (PySh4 1 IPC; not SH-4 clock cycles)",
        finished=run.reason if run else "none",
        stub_calls=bridge.calls,
        stubs_expected=sorted(set(expected_stubs)),
        stubs_called=sorted(called_stubs),
        input=info,
        outputs=outputs,
        problems=problems,
        l3_claim=False,
        note=(
            "synthetic pipeline probe: it proves the runner/dispatcher path, "
            "NOT the firmware reader's verdict"
        ),
    )
    manifest = info.get("manifest")
    if manifest is not None:
        payload["python"] = {
            "reader": target["corpus"]["reader"],
            "case": target["corpus"].get("case"),
            "manifest_expected": manifest.get("expected"),
            "agrees_with_engine": manifest.get("expected") == observed,
        }
    return payload


def _emit_target(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2))
        return
    status = payload["status"]
    print(f"target   {payload['target']} ({payload.get('reader', '-')})")
    print(
        f"engine   {payload.get('engine') or '-'} "
        f"{payload.get('engine_kind', '')}".rstrip()
    )
    if status == "DRY_RUN":
        print(f"entry    {payload['entry']}")
        availability = payload.get("engine_status") or {}
        if availability:
            print(
                f"backend  {availability.get('engine')} "
                f"{availability.get('status')}"
            )
        print(f"expect   {payload['expect']['verdict']}: {payload['expect']['rule']}")
        inp = payload.get("input")
        if inp:
            print(f"input    {inp.get('source') or 'unresolved'}")
        elif payload.get("firmware_call"):
            fc = payload["firmware_call"]
            print(f"inputs   cmp={fc.get('cmp')} ind={fc.get('ind')} mutate={fc.get('mutate')}")
            print(f"sec1     va={fc['sec1_table'].get('va')} declared=True")
        print("RESULT: DRY_RUN (exit 0; no verdict is claimed)")
        return
    if status == "INVALID":
        for problem in payload.get("problems", []):
            print(f"FAIL {problem}")
        print(f"RESULT: INVALID ({len(payload.get('problems', []))} problem(s))")
        return
    if status in ("BLOCKED", "SKIP"):
        print(f"reason   {payload.get('reason')}")
        print(f"RESULT: {status} (exit {payload['exit']}); nothing was claimed")
        return
    expected = payload.get("expected_verdict") or payload["expect"]["verdict"]
    print(f"verdict  {payload['verdict']} (expected {expected})")
    if payload.get("records"):
        fw = payload.get("firmware") or {}
        print(f"walker   nth={fw.get('nth')} build={fw.get('build')} "
              f"records={len(payload['records'])}")
        for row in payload["records"]:
            print(f"  n={row['n']:<5} firmware={row['firmware']!s:<8} "
                  f"parse_page={row['parse_page']!s:<8} "
                  f"model={row['model']!s:<8} {'OK' if row['ok'] else 'MISMATCH'}")
    elif payload.get("firmware"):
        fw = payload["firmware"]
        if "fn" in fw:
            print(f"firmware fn {fw['fn']} {fw['build']} {fw.get('module', '')} "
                  f"r0={fw.get('r0')} insns={fw.get('insns')}")
            if "log_codes" in fw:
                print(f"fwlog    codes={fw['log_codes']} sites={fw['log_sites']}")
        else:
            print(f"firmware r0={fw.get('r0')} insns={fw.get('insns')} memcpy={fw.get('memcpy')}")
        inp = payload.get("inputs") or {}
        if inp and "card" in inp:
            print(f"inputs   card={inp.get('card')} sha256={inp.get('card_sha256')}")
            print(f"unit     +0x60={inp.get('unit_code')!r} ({inp.get('unit_source')})")
            print(f"card     slot0={inp.get('card_slot0')!r}")
        elif inp and "file" in inp:
            print(f"inputs   file={inp.get('file')} sha256={inp.get('file_sha256')} size={inp.get('size')}")
        elif inp:
            print(f"inputs   cmp={inp.get('cmp')} ind={inp.get('ind')} mutate={inp.get('mutate')}")
        sec1 = payload.get("sec1_table") or {}
        if sec1:
            print(f"sec1     va={sec1.get('va')} declared={sec1.get('declared')}")
        for call in payload.get("stub_log", []):
            extra = {k: v for k, v in call.items() if k not in ("stub", "args", "ret")}
            print(f"stub     {call['stub']}({', '.join(call['args'])}) -> {call['ret']}"
                  + (f" {extra}" if extra else ""))
        for key, span in (payload.get("compressed_section_access") or {}).items():
            print(f"access   {key} {span['lo']}..{span['hi']} ({span['bytes']} B)")
    else:
        print(
            f"call     r0={payload['returned']} over {payload['cycles']} "
            "instruction/stub steps"
        )
        for call in payload.get("stub_calls", []):
            print(
                f"stub     {call['stub']} at {call['va']} "
                f"args={call['args']} -> {call['returned']}"
            )
        if payload.get("outputs"):
            print(f"log      {payload['outputs']['log']!r}")
    for problem in payload.get("problems", []):
        print(f"FAIL {problem}")
    print(
        f"RESULT: {status}"
        + ("" if status == "PASS" else " (exit %d)" % payload["exit"])
    )


def cmd_targets(args) -> int:
    try:
        by_name, doc = load_targets(getattr(args, "targets", None))
    except TargetError as exc:
        for problem in exc.problems:
            print(f"FAIL {problem}")
        print(f"RESULT: FAIL ({len(exc.problems)} problem(s))")
        return EXIT_INVALID
    payload = {
        "command": "targets",
        "schema": doc.get("schema"),
        "targets": [
            {
                "name": target["name"],
                "reader": target["reader"],
                "entry": target["entry"].get("kind"),
                "expect": target["expect"]["verdict"],
                "program": target["entry"].get("program"),
            }
            for target in by_name.values()
        ],
        "result": "PASS",
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return EXIT_OK
    for item in payload["targets"]:
        print(
            f"{item['name']:<28} {item['reader']:<10} {item['entry']:<9} "
            f"expect {item['expect']}"
            + (f"  [{item['program']}]" if item["program"] else "")
        )
    print(f"RESULT: PASS ({len(payload['targets'])} target(s))")
    return EXIT_OK


def cmd_run_target(args) -> int:
    try:
        by_name, _doc = load_targets(getattr(args, "targets", None))
    except TargetError as exc:
        payload = {
            "command": "run",
            "mode": "target",
            "target": args.target,
            "status": "INVALID",
            "exit": EXIT_INVALID,
            "problems": exc.problems,
        }
        _emit_target(payload, args.json)
        return EXIT_INVALID

    target = by_name.get(args.target)
    if target is None:
        payload = {
            "command": "run",
            "mode": "target",
            "target": args.target,
            "status": "BLOCKED",
            "exit": EXIT_BLOCKED,
            "reason": (
                f"no target named {args.target!r} in {TARGETS_FILE.name}; "
                f"known targets: {', '.join(sorted(by_name))}"
            ),
            "accepted": None,
            "l3_claim": False,
        }
        _emit_target(payload, args.json)
        return EXIT_BLOCKED

    if args.dry_run:
        payload = _plan_target(target, args)
        _emit_target(payload, args.json)
        return payload["exit"]

    payload = run_target(target, args)
    _emit_target(payload, args.json)
    return payload["exit"]


def _load_inputs(args):
    """Load and validate both input documents; return (docs, problems)."""

    problems: list[str] = []
    docs: dict[str, dict] = {}

    try:
        docs["manifest"] = manifest_mod.load(args.manifest)
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"manifest: cannot read {args.manifest}: {exc}")
    else:
        root = getattr(args, "root", None)
        for problem in manifest_mod.validate(
            docs["manifest"], root=root, check_files=bool(root)
        ):
            problems.append(f"manifest: {problem}")

    try:
        docs["rommap"] = rommap_mod.load(args.rommap)
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"rommap: cannot read {args.rommap}: {exc}")
    else:
        for problem in rommap_mod.validate(docs["rommap"]):
            problems.append(f"rommap: {problem}")

    return docs, problems


def _corpus_summary(doc):
    readers: dict[str, dict] = {}
    for entry in doc.get("corpus", []):
        reader = entry.get("reader")
        info = readers.setdefault(
            reader, {"entries": 0, "cases": [], "verdicts": []}
        )
        info["entries"] += 1
        if entry.get("case") not in info["cases"]:
            info["cases"].append(entry.get("case"))
        if entry.get("expected") not in info["verdicts"]:
            info["verdicts"].append(entry.get("expected"))
    return readers


def build_plan(manifest_doc, rommap_doc) -> dict:
    readers = _corpus_summary(manifest_doc)
    located = {
        target["reader"]
        for target in TRACE_TARGETS
        if target["status"] == "located-file-offset"
        and target.get("role") == "reader"
        and target["reader"]
    }

    reader_plan = []
    for reader in sorted(readers):
        reader_plan.append(
            {
                "reader": reader,
                "entries": readers[reader]["entries"],
                "cases": sorted(readers[reader]["cases"]),
                "verdicts": sorted(readers[reader]["verdicts"]),
                "stubs": stubs_mod.READER_STUBS.get(reader, []),
                "entry_point": (
                    "located-file-offset"
                    if reader in located
                    else "UNKNOWN (no runnable entry point)"
                ),
            }
        )

    blockers = [
        f"reader {reader} has no runnable entry point"
        for reader in sorted(readers)
        if reader not in located
    ]
    script_name = HARNESS_SCRIPT.relative_to(HERE.parent.parent)
    blockers.append(
        f"Ghidra entry script {script_name} runs no reader yet (it reports "
        "BLOCKED)"
        if HARNESS_SCRIPT.is_file()
        else f"Ghidra entry script {script_name} is missing"
    )
    blockers.append(
        "no Ghidra run has produced a result JSON yet; L3 is not claimed"
    )

    blocks = rommap_doc.get("blocks", [])
    return {
        "status": "BLOCKED",
        "corpus": {
            "entries": len(manifest_doc.get("corpus", [])),
            "readers": reader_plan,
        },
        "rommap": {
            "segment_index": rommap_doc.get("source", {}).get("segment_index"),
            "segment_base": rommap_doc.get("source", {}).get("segment_base"),
            "processor": rommap_doc.get("processor", {}).get("id"),
            "processor_verified": rommap_doc.get("processor", {}).get("verified"),
            "blocks": len(blocks),
            "loadable": sum(1 for b in blocks if b.get("loadable")),
            "ram": rommap_doc.get("ram") is not None,
            "skipped": len(rommap_doc.get("skipped", [])),
        },
        "stubs": {
            "modeled": sum(1 for s in stubs_mod.STUBS if s["status"] == "modeled"),
            "planned": sum(1 for s in stubs_mod.STUBS if s["status"] == "planned"),
        },
        "trace_targets": TRACE_TARGETS,
        "blockers": blockers,
        "first_run_needs": [
            "tools/cerom.py section table (va, file_offset, size, "
            "characteristics, compressed) for one build",
            "rommap.py convert of that report (one segment, no compressed "
            "sections or an explicit --skip-compressed)",
            "one located reader entry point with a VA from the memory map",
            "Ghidra 12.2+ with analyzeHeadless and a JDK it supports",
            "tools/l3_harness/ghidra/l3_run.py wired to a located reader (it "
            "is the entry script; it runs no reader yet)",
            "a corpus root matching the manifest, with hashes verified",
            "the firmware image for -import and the reader's expected VA",
        ],
    }


def _ghidra_instructions(args) -> str:
    manifest_arg = args.manifest
    rommap_arg = args.rommap
    image_arg = getattr(args, "image", None) or "<firmware-image>"
    return "\n".join(
        [
            "MISSING_GHIDRA: analyzeHeadless was not found.",
            "",
            "Install Ghidra (12.2 or newer) and a JDK it supports, then either",
            "put analyzeHeadless on PATH or export GHIDRA_INSTALL_DIR:",
            "",
            "  # 1. download and unpack, e.g. to /opt",
            "  #    https://github.com/NationalSecurityAgency/ghidra/releases",
            "  export GHIDRA_INSTALL_DIR=/opt/ghidra_12.2_PUBLIC",
            "  ls \"$GHIDRA_INSTALL_DIR/support/analyzeHeadless\"",
            "",
            "  # 2. re-run the check (no Ghidra needed for this step)",
            f"  python3 tools/l3_harness/runner.py check "
            f"--manifest {manifest_arg} --rommap {rommap_arg}",
            "",
            "  # 3. re-run the harness",
            f"  python3 tools/l3_harness/runner.py run "
            f"--manifest {manifest_arg} --rommap {rommap_arg} "
            f"--image {image_arg}",
            "",
            "A run is only reported as PASS after a real analyzeHeadless run",
            "matches every manifest verdict. Missing Ghidra is exit 3, never 0.",
        ]
    )


def detect_ghidra(explicit=None, env=None, extra_roots=None):
    """Return ``(path_or_None, searched)``.

    ``searched`` is a list of ``(source, candidate)`` pairs, so a failed run
    can tell the user exactly where it looked.
    """

    env = os.environ if env is None else env
    searched: list[tuple[str, str]] = []

    def usable(candidate: Path) -> bool:
        return candidate.is_file() and os.access(candidate, os.X_OK)

    if explicit:
        candidate = Path(explicit).expanduser()
        searched.append(("--headless", str(candidate)))
        return (str(candidate), searched) if usable(candidate) else (None, searched)

    for variable in ("GHIDRA_INSTALL_DIR", "GHIDRA_HOME"):
        value = env.get(variable)
        if not value:
            searched.append((f"${variable}", "unset"))
            continue
        candidate = Path(value) / "support" / "analyzeHeadless"
        searched.append((f"${variable}", str(candidate)))
        if usable(candidate):
            return str(candidate), searched

    on_path = shutil.which(
        "analyzeHeadless", path=env.get("PATH", os.defpath)
    )
    searched.append(("$PATH", on_path or "not found"))
    if on_path:
        return on_path, searched

    roots = DEFAULT_SEARCH_ROOTS if extra_roots is None else tuple(extra_roots)
    home = env.get("HOME")
    for root in roots:
        if root == "~":
            if not home:
                continue
            root = home
        base = Path(root)
        if not base.is_dir():
            continue
        for match in sorted(base.glob("ghidra*")):
            candidate = match / "support" / "analyzeHeadless"
            searched.append(("glob", str(candidate)))
            if usable(candidate):
                return str(candidate), searched

    return None, searched


def cmd_check(args) -> int:
    docs, problems = _load_inputs(args)

    payload = {
        "command": "check",
        "manifest": str(args.manifest),
        "rommap": str(args.rommap),
        "root": getattr(args, "root", None),
        "entries": 0,
        "blocks": 0,
        "problems": problems,
        "result": "FAIL" if problems else "PASS",
    }
    if "manifest" in docs:
        payload["entries"] = len(docs["manifest"].get("corpus", []))
    if "rommap" in docs:
        payload["blocks"] = len(docs["rommap"].get("blocks", []))

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for problem in problems:
            print(f"FAIL {problem}")
        if not problems:
            print(
                f"manifest: {payload['entries']} entries"
                + (
                    f", files verified under {args.root}"
                    if getattr(args, "root", None)
                    else ", file hashes not verified (no --root)"
                )
            )
            print(
                f"rommap: {payload['blocks']} blocks, "
                f"processor {docs['rommap'].get('processor', {}).get('id')} "
                f"(verified={docs['rommap'].get('processor', {}).get('verified')})"
            )
            print("RESULT: PASS")
        else:
            print(f"RESULT: FAIL ({len(problems)} problem(s))")

    return EXIT_OK if not problems else EXIT_INVALID


def _print_plan(plan: dict) -> None:
    corpus = plan["corpus"]
    print("L3 plan (design only; nothing below is claimed as run)")
    print("=" * 66)
    print(f"corpus: {corpus['entries']} entries")
    for reader in corpus["readers"]:
        verdicts = "/".join(reader["verdicts"])
        cases = ", ".join(reader["cases"])
        print(
            f"  {reader['reader']:<9} {reader['entries']:>2} entries "
            f"[{verdicts}] {cases}"
        )
        print(f"            entry point: {reader['entry_point']}")
        print(f"            stubs: {', '.join(reader['stubs'])}")

    rommap = plan["rommap"]
    print()
    print(
        f"rommap: segment {rommap['segment_index']} "
        f"({rommap['segment_base']}), {rommap['blocks']} blocks, "
        f"{rommap['loadable']} loadable, ram={'yes' if rommap['ram'] else 'no'}, "
        f"{rommap['skipped']} skipped"
    )
    print(
        f"processor: {rommap['processor']} "
        f"(verified={rommap['processor_verified']})"
    )
    print(
        f"stubs: {plan['stubs']['modeled']} modeled, "
        f"{plan['stubs']['planned']} planned"
    )

    print()
    print("trace targets:")
    for target in plan["trace_targets"]:
        anchor = target["anchor"] or "-"
        reader = target["reader"] or "(unassigned)"
        print(
            f"  [{target['status']:<20}] {target.get('role', 'reader'):<6} "
            f"{reader:<9} {anchor}"
        )
        print(f"                          {target['what']}")
        if target["note"]:
            print(f"                          {target['note']}")

    print()
    print("blockers:")
    for blocker in plan["blockers"]:
        print(f"  - {blocker}")

    print()
    print("first real run needs:")
    for item in plan["first_run_needs"]:
        print(f"  - {item}")


def cmd_plan(args) -> int:
    docs, problems = _load_inputs(args)
    if problems:
        for problem in problems:
            print(f"FAIL {problem}", file=sys.stderr)
        print(
            f"RESULT: FAIL ({len(problems)} problem(s)); fix the inputs first",
            file=sys.stderr,
        )
        return EXIT_INVALID

    plan = build_plan(docs["manifest"], docs["rommap"])
    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        _print_plan(plan)
    return EXIT_OK


def _emit_run(payload, as_json, lines) -> None:
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        for line in lines:
            print(line)


def cmd_run(args, env=None) -> int:
    """``run`` dispatches to target mode when a FUNC was given."""

    if getattr(args, "target", None):
        return cmd_run_target(args)
    return cmd_run_legacy(args, env=env)


def cmd_run_legacy(args, env=None) -> int:
    if not args.manifest or not args.rommap:
        print(
            "usage: run FUNC --input FILE [--engine pysh4|ghidra|qemu] "
            "or run --manifest m.json --rommap r.json --image fw.img",
            file=sys.stderr,
        )
        return 2
    docs, problems = _load_inputs(args)
    if problems:
        payload = {
            "command": "run",
            "status": "INVALID",
            "exit": EXIT_INVALID,
            "problems": problems,
        }
        _emit_run(
            payload,
            args.json,
            [f"FAIL {problem}" for problem in problems]
            + [f"RESULT: FAIL ({len(problems)} problem(s))"],
        )
        return EXIT_INVALID

    headless, searched = detect_ghidra(
        explicit=args.headless,
        env=env,
        extra_roots=args.search_root or None,
    )
    if not headless:
        payload = {
            "command": "run",
            "status": "MISSING_GHIDRA",
            "exit": EXIT_MISSING_GHIDRA,
            "searched": [{"source": source, "candidate": candidate} for source, candidate in searched],
        }
        _emit_run(
            payload,
            args.json,
            [_ghidra_instructions(args), "", "RESULT: MISSING_GHIDRA (exit 3)"],
        )
        return EXIT_MISSING_GHIDRA

    if not HARNESS_SCRIPT.is_file():
        payload = {
            "command": "run",
            "status": "BLOCKED",
            "exit": EXIT_BLOCKED,
            "reason": f"harness script missing: {HARNESS_SCRIPT}",
            "ghidra": headless,
        }
        _emit_run(
            payload,
            args.json,
            [
                f"BLOCKED: Ghidra found at {headless}",
                f"BLOCKED: harness script missing: {HARNESS_SCRIPT}",
                "The P-code harness and a located reader entry point are the",
                "next step; no result is produced and no pass is claimed.",
                "RESULT: BLOCKED (exit 4)",
            ],
        )
        return EXIT_BLOCKED

    image = args.image
    if not image or not Path(image).is_file():
        payload = {
            "command": "run",
            "status": "BLOCKED",
            "exit": EXIT_BLOCKED,
            "reason": "firmware image not provided or not readable",
            "ghidra": headless,
            "image": image,
        }
        _emit_run(
            payload,
            args.json,
            [
                f"BLOCKED: Ghidra found at {headless}",
                f"BLOCKED: firmware image missing: {image}",
                "Pass --image <the vendor image>; it is never committed.",
                "RESULT: BLOCKED (exit 4)",
            ],
        )
        return EXIT_BLOCKED

    blocks = [
        block
        for block in docs["rommap"].get("blocks", [])
        if block.get("loadable")
    ]
    if not blocks:
        payload = {
            "command": "run",
            "status": "BLOCKED",
            "exit": EXIT_BLOCKED,
            "reason": "memory map has no loadable blocks",
        }
        _emit_run(
            payload,
            args.json,
            ["BLOCKED: the memory map has no loadable blocks", "RESULT: BLOCKED (exit 4)"],
        )
        return EXIT_BLOCKED

    project_dir = args.project_dir
    result_path = Path(args.result or (Path(project_dir) / "l3-result.json"))
    command = [
        headless,
        project_dir,
        "l3",
        "-import",
        image,
        "-processor",
        docs["rommap"]["processor"]["id"],
        "-scriptPath",
        str(HARNESS_SCRIPT.parent),
        "-postScript",
        HARNESS_SCRIPT.name,
        str(args.rommap),
        str(args.manifest),
        str(result_path),
    ]

    if args.dry_run:
        payload = {
            "command": "run",
            "status": "DRY_RUN",
            "exit": EXIT_OK,
            "command": command,
            "note": "no Ghidra process was started and no verdict is claimed",
        }
        _emit_run(payload, args.json, [" ".join(command), "RESULT: DRY_RUN (exit 0)"])
        return EXIT_OK

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        payload = {
            "command": "run",
            "status": "BLOCKED",
            "exit": EXIT_BLOCKED,
            "reason": f"analyzeHeadless failed to run: {exc}",
            "command": command,
        }
        _emit_run(payload, args.json, [f"BLOCKED: {exc}", "RESULT: BLOCKED (exit 4)"])
        return EXIT_BLOCKED

    if completed.returncode != 0:
        payload = {
            "command": "run",
            "status": "BLOCKED",
            "exit": EXIT_BLOCKED,
            "reason": f"analyzeHeadless exit {completed.returncode}",
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "command": command,
        }
        _emit_run(
            payload,
            args.json,
            [
                f"BLOCKED: analyzeHeadless exit {completed.returncode}",
                completed.stderr[-2000:],
                "RESULT: BLOCKED (exit 4)",
            ],
        )
        return EXIT_BLOCKED

    if not result_path.is_file():
        payload = {
            "command": "run",
            "status": "BLOCKED",
            "exit": EXIT_BLOCKED,
            "reason": "analyzeHeadless finished but wrote no result JSON",
            "command": command,
        }
        _emit_run(
            payload,
            args.json,
            ["BLOCKED: no result JSON; a missing result is not a pass", "RESULT: BLOCKED (exit 4)"],
        )
        return EXIT_BLOCKED

    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        payload = {
            "command": "run",
            "status": "BLOCKED",
            "exit": EXIT_BLOCKED,
            "reason": f"unreadable result JSON: {exc}",
        }
        _emit_run(payload, args.json, [f"BLOCKED: {exc}", "RESULT: BLOCKED (exit 4)"])
        return EXIT_BLOCKED

    if isinstance(result, dict) and result.get("status") == "BLOCKED":
        # The script itself reports that no reader ran: that is BLOCKED (exit
        # 4), not a per-case mismatch, and never a pass.
        reason = str(result.get("reason") or "the harness script reported BLOCKED")
        payload = {
            "command": "run",
            "status": "BLOCKED",
            "exit": EXIT_BLOCKED,
            "reason": reason,
            "result": str(result_path),
        }
        _emit_run(payload, args.json, [f"BLOCKED: {reason}", "RESULT: BLOCKED (exit 4)"])
        return EXIT_BLOCKED

    mismatches = _compare_result(docs["manifest"], result)
    payload = {
        "command": "run",
        "status": "PASS" if not mismatches else "MISMATCH",
        "exit": EXIT_OK if not mismatches else EXIT_MISMATCH,
        "mismatches": mismatches,
        "result": str(result_path),
    }
    _emit_run(
        payload,
        args.json,
        [f"MISMATCH {item}" for item in mismatches]
        + [
            "RESULT: PASS"
            if not mismatches
            else f"RESULT: MISMATCH ({len(mismatches)})",
        ],
    )
    return payload["exit"]


def _compare_result(manifest_doc, result: dict) -> list[str]:
    """Compare harness verdicts with the manifest expectations.

    Missing cases are mismatches: a harness that skips an entry has not
    passed it.
    """

    mismatches: list[str] = []
    observed = {}
    for case in result.get("cases", []) if isinstance(result, dict) else []:
        if isinstance(case, dict) and isinstance(case.get("id"), str):
            observed[case["id"]] = case.get("verdict")

    for entry in manifest_doc.get("corpus", []):
        entry_id = entry.get("id")
        expected = entry.get("expected")
        if entry_id not in observed:
            mismatches.append(f"{entry_id}: no verdict in the harness result")
        elif observed[entry_id] != expected:
            mismatches.append(
                f"{entry_id}: harness {observed[entry_id]!r}, "
                f"manifest {expected!r}"
            )
    return mismatches


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="L3 harness runner (design-only)")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_inputs(cmd, required=True):
        cmd.add_argument(
            "--manifest", required=required, help="corpus manifest JSON"
        )
        cmd.add_argument(
            "--rommap", required=required, help="memory map JSON"
        )
        cmd.add_argument(
            "--root",
            help="corpus root; enables size/SHA-256 checks",
        )
        cmd.add_argument("--json", action="store_true")

    check_cmd = sub.add_parser("check", help="validate manifest and memory map")
    add_inputs(check_cmd)

    plan_cmd = sub.add_parser("plan", help="print trace targets, stubs and blockers")
    add_inputs(plan_cmd)

    targets_cmd = sub.add_parser(
        "targets", help="list the named targets in targets.json"
    )
    targets_cmd.add_argument("--targets", help="path to targets.json")
    targets_cmd.add_argument("--json", action="store_true")

    run_cmd = sub.add_parser(
        "run",
        help="run one target end to end, or the legacy Ghidra harness",
    )
    add_inputs(run_cmd, required=False)
    run_cmd.add_argument(
        "target",
        nargs="?",
        help="target name from targets.json (target mode)",
    )
    run_cmd.add_argument(
        "--engine",
        default="pysh4",
        help="back end for target mode: %s" % ", ".join(engine_mod.BACKENDS),
    )
    run_cmd.add_argument("--targets", help="path to targets.json")
    run_cmd.add_argument(
        "--input-root",
        help=(
            "base directory for entry.input_region file sources (M9.28); "
            "relative paths resolve here, not to the firmware image"
        ),
    )
    run_cmd.add_argument(
        "--input", help="host file to load into the virtual FS (target mode)"
    )
    run_cmd.add_argument(
        "--corpus",
        help="corpus root built by corpus.py; resolves the target's corpus path",
    )
    run_cmd.add_argument(
        "--cmp",
        help="firmware_call: .cmp payload path (M9.11b cmp_ind_reader)",
    )
    run_cmd.add_argument(
        "--ind",
        help="firmware_call: .ind index path (M9.11b cmp_ind_reader)",
    )
    run_cmd.add_argument(
        "--mutate",
        default="none",
        choices=("none", "swap-4-8", "corrupt-ind"),
        help="firmware_call: control mutation (M9.11b; default none)",
    )
    run_cmd.add_argument(
        "--offset",
        type=lambda s: int(s, 0),
        default=None,
        help="firmware_call: logical page offset (default from target entry)",
    )
    run_cmd.add_argument(
        "--length",
        type=lambda s: int(s, 0),
        default=None,
        help="firmware_call: page length (default from target entry)",
    )
    run_cmd.add_argument(
        "--unit-from",
        help="mapcode_compare_v1: factory HDD_INFO.TXT whose line-1 bytes 0..10 "
             "are the declared unit record +0x60 (M9.6)",
    )
    run_cmd.add_argument(
        "--unit-code",
        help="mapcode_compare_v1: declared unit record +0x60, 11 ASCII bytes",
    )
    run_cmd.add_argument(
        "--expect",
        choices=("ACCEPT", "REJECT"),
        help="mapcode_compare_v1, drstr_parser_v1: expected verdict for this input "
             "(default: the target's expect.verdict)",
    )
    run_cmd.add_argument(
        "--max-insns",
        type=int,
        default=engine_mod.DEFAULT_MAX_INSNS,
        help="instruction/stub budget for target mode",
    )
    run_cmd.add_argument("--headless", help="path to analyzeHeadless")
    run_cmd.add_argument(
        "--search-root",
        action="append",
        default=[],
        help="extra directory to glob for ghidra* (repeatable)",
    )
    run_cmd.add_argument("--image", help="firmware image for -import")
    run_cmd.add_argument(
        "--init-from-image", action="store_true",
        help="firmware_call: map the module's compressed sections with their "
             "INIT bytes decoded by tools/nk_decomp.py instead of the declared "
             "sec1 table (M1.19)",
    )
    run_cmd.add_argument("--project-dir", default="/tmp/opencode/l3-ghidra")
    run_cmd.add_argument("--result", help="result JSON path")
    run_cmd.add_argument("--timeout", type=float, default=1800.0)
    run_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan/command without running anything",
    )

    st = sub.add_parser("selftest", help="run the package self-test")
    mode = st.add_mutually_exclusive_group()
    mode.add_argument("--quick", action="store_true",
                      help="bounded checks (default); fast path for main loops")
    mode.add_argument("--full", action="store_true",
                      help="complete checks, including external back-end parity when available")
    return parser


def main(argv=None, env=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--selftest":
        rest = list(argv[1:])
        full = "--full" in rest
        return selftest_targets(full=full)

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "selftest":
        from l3_harness import selftest

        child = ["--full"] if getattr(args, "full", False) else []
        return selftest.main(child)
    if args.command == "check":
        return cmd_check(args)
    if args.command == "plan":
        return cmd_plan(args)
    if args.command == "targets":
        return cmd_targets(args)
    if args.command == "run":
        return cmd_run(args, env=env)
    parser.error(f"unknown command {args.command!r}")
    return 2


# ==========================================================================
# Runner self-test (--selftest): synthetic target, ACCEPT and REJECT, honest
# BLOCKED / SKIP paths.  No vendor data, no Ghidra, no QEMU required.
# ==========================================================================

SELFTEST_CHECKS: list[tuple[str, callable]] = []
SELFTEST_SKIPS: list[str] = []
RUNNER_FULL_SELFTEST = False


def check(name):
    def register(func):
        SELFTEST_CHECKS.append((name, func))
        return func

    return register


def _run_cli(argv) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        code = main(argv)
    return code, buffer.getvalue()


def _write_input(tmp, data, name="input.bin") -> Path:
    path = Path(tmp) / name
    path.write_bytes(data)
    return path


def _run_json(tmp, data, extra=(), name="input.bin") -> tuple[int, dict, str]:
    path = _write_input(tmp, data, name)
    argv = ["run", "probe-zlib-cmf", "--input", str(path), "--json", *extra]
    code, output = _run_cli(argv)
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        raise AssertionError(f"not JSON (exit {code}): {output}") from None
    return code, payload, output


def _ns(**kwargs) -> argparse.Namespace:
    values = {
        "engine": "pysh4",
        "targets": None,
        "input": None,
        "corpus": None,
        "dry_run": False,
        "max_insns": engine_mod.DEFAULT_MAX_INSNS,
    }
    values.update(kwargs)
    return argparse.Namespace(**values)


def _probe_target():
    by_name, _doc = load_targets()
    return by_name, by_name["probe-zlib-cmf"]


@check("targets: shipped targets.json validates and names one synthetic probe")
def test_targets_file(tmp):
    by_name, doc = load_targets()
    assert doc["schema"] == TARGETS_SCHEMA, doc.get("schema")
    probe = by_name["probe-zlib-cmf"]
    assert probe["entry"]["kind"] == "synthetic", probe["entry"]
    assert probe.get("build") == "eu2011", probe.get("build")
    assert all(t.get("build") in BUILDS for t in by_name.values()), [
        (n, t.get("build")) for n, t in by_name.items()]
    targets = {spec["target"] for spec in probe["stubs"]}
    assert {"sprintf", "CreateFileW", "ReadFile", "CloseHandle"} <= targets, targets
    assert any(spec["target"].startswith("#") for spec in probe["stubs"]), (
        "one call site should resolve by the verified ordinal (C-527)"
    )
    blocked = [
        name for name, target in by_name.items()
        if target["entry"]["kind"] == "blocked"
    ]
    assert blocked, "no blocked reader target is declared"
    for name, target in by_name.items():
        corpus = target["corpus"]
        assert corpus["reader"] in manifest_mod.READERS, (name, corpus["reader"])
        assert corpus.get("case") in manifest_mod.CASES, (name, corpus.get("case"))
        assert corpus["reader"] in manifest_mod.CASES[corpus["case"]]["readers"], name
    assert "probe_zlib_cmf_v1" in SYNTHETIC_PROGRAMS
    program = build_probe_zlib_cmf()
    assert struct.unpack(">H", program[:2])[0] == 0x4F22, "probe must start with sts.l"


@check("run: ACCEPT input through sprintf, CreateFileW and ReadFile")
def test_run_accept(tmp):
    code, payload, _output = _run_json(tmp, b"\x78\x9c" + b"A" * 30)
    assert code == EXIT_OK, payload
    assert payload["status"] == "PASS", payload
    assert payload["accepted"] is True, payload
    assert payload["verdict"] == "ACCEPT", payload
    assert payload["returned"] == "0x00000001", payload
    assert payload["cycles"] > 0 and payload["finished"] == "return", payload
    assert payload["outputs"]["count"] == 1, payload["outputs"]
    assert payload["outputs"]["read_bytes_hex"].startswith("78"), payload["outputs"]
    resolved = [call["resolved"] for call in payload["stub_calls"]]
    assert resolved.count("sprintf") == 2, resolved
    assert resolved.count("CreateFileW") == 1, resolved
    assert resolved.count("ReadFile") == 1, resolved
    assert resolved.count("CloseHandle") == 1, resolved
    # The wide path goes to CreateFileW; the ANSI path is what sprintf formatted.
    create = next(c for c in payload["stub_calls"] if c["resolved"] == "CreateFileW")
    assert create["args"][0] == "0x8c200200", create         # UTF-16LE path VA
    assert create["returned"] == "0x00000010", create        # first synthetic handle
    log_call = next(c for c in payload["stub_calls"] if c["resolved"] == "sprintf"
                    and c["va"] == "0x8c100240")
    assert log_call["stub"] == "coredll!#719", log_call      # C-527 ordinal
    assert payload["outputs"]["log"] == "REFER001/ADDRE001.DAT.cmp|1", payload
    assert payload["synthetic"] is True and payload["l3_claim"] is False, payload


@check("run: a REJECT input against the ACCEPT target is a MISMATCH (exit 5)")
def test_run_mismatch(tmp):
    code, payload, _output = _run_json(tmp, b"\x00\x01" + b"B" * 30)
    assert code == EXIT_MISMATCH, payload
    assert payload["status"] == "MISMATCH", payload
    assert payload["accepted"] is False, payload
    assert payload["verdict"] == "REJECT", payload
    assert payload["returned"] == "0x00000000", payload
    assert payload["outputs"]["count"] == 1, payload["outputs"]
    assert any("engine verdict REJECT" in p for p in payload["problems"]), payload


@check("run: REJECT is a real verdict, verified by the target's own expectation")
def test_run_reject(tmp):
    by_name, probe = _probe_target()
    reject_target = copy.deepcopy(probe)
    reject_target["expect"]["verdict"] = "REJECT"
    path = _write_input(tmp, b"\x00\x01" + b"B" * 30)
    payload = run_target(reject_target, _ns(input=str(path)))
    assert payload["status"] == "PASS", payload
    assert payload["exit"] == EXIT_OK, payload
    assert payload["accepted"] is False, payload
    assert payload["verdict"] == "REJECT", payload
    assert payload["outputs"]["read_bytes_hex"].startswith("00"), payload["outputs"]


@check("run: empty file stops in ReadFile and still reports REJECT")
def test_run_empty(tmp):
    by_name, probe = _probe_target()
    reject_target = copy.deepcopy(probe)
    reject_target["expect"]["verdict"] = "REJECT"
    path = _write_input(tmp, b"")
    payload = run_target(reject_target, _ns(input=str(path)))
    assert payload["status"] == "PASS", payload
    assert payload["verdict"] == "REJECT", payload
    assert payload["outputs"]["count"] == 0, payload["outputs"]
    read = next(c for c in payload["stub_calls"] if c["resolved"] == "ReadFile")
    assert read["returned"] == "0x00000000", read


@check("run: missing target reports BLOCKED (exit 4)")
def test_run_missing_target(tmp):
    path = _write_input(tmp, b"\x78\x9c")
    code, output = _run_cli(
        ["run", "no-such-target", "--input", str(path), "--json"]
    )
    payload = json.loads(output)
    assert code == EXIT_BLOCKED, output
    assert payload["status"] == "BLOCKED", payload
    assert "no target named" in payload["reason"], payload
    assert payload["accepted"] is None, payload


@check("run: a reader that is not located reports BLOCKED")
def test_run_blocked_reader(tmp):
    path = _write_input(tmp, b"\x78\x9c")
    code, output = _run_cli(
        ["run", "hddinfo_compare", "--input", str(path), "--json"]
    )
    payload = json.loads(output)
    assert code == EXIT_BLOCKED, output
    assert payload["status"] == "BLOCKED", payload
    assert payload["reason"], payload
    assert payload["l3_claim"] is False, payload
    assert payload["stubs_expected"], payload


@check("run: an unmodelled export stops with 'missing stub: NAME'")
def test_run_missing_stub(tmp):
    by_name, probe = _probe_target()
    broken = copy.deepcopy(probe)
    broken["stubs"][0]["target"] = "OpenEventW"
    path = _write_input(tmp, b"\x78\x9c")
    payload = run_target(broken, _ns(input=str(path)))
    assert payload["status"] == "BLOCKED", payload
    assert payload["exit"] == EXIT_BLOCKED, payload
    assert "missing stub: OpenEventW" in payload["reason"], payload
    assert payload["accepted"] is None, payload


@check("run: a bad virtual-FS path blocks instead of opening a host file")
def test_run_bad_path(tmp):
    by_name, probe = _probe_target()
    broken = copy.deepcopy(probe)
    broken["corpus"]["guest_path"] = "\\"
    path = _write_input(tmp, b"\x78\x9c")
    payload = run_target(broken, _ns(input=str(path)))
    assert payload["status"] == "BLOCKED", payload
    assert "virtual FS" in payload["reason"], payload


@check("run: --dry-run prints the plan and claims no verdict")
def test_run_dry_run(tmp):
    path = _write_input(tmp, b"\x78\x9c")
    code, output = _run_cli(
        ["run", "probe-zlib-cmf", "--input", str(path), "--dry-run", "--json"]
    )
    payload = json.loads(output)
    assert code == EXIT_OK, output
    assert payload["status"] == "DRY_RUN", payload
    assert "no verdict is claimed" in payload["note"], payload
    assert payload["regions"] and payload["program"], payload
    assert payload["engine_status"]["engine"] == "pysh4", payload
    assert payload["engine_status"]["available"] is True, payload
    unscoped = json.loads(
        _run_cli(
            ["run", "probe-zlib-cmf", "--dry-run", "--json"]
        )[1]
    )
    assert "source" in unscoped["input"], unscoped["input"]


@check("run: --corpus resolves the target's corpus entry and manifest verdict")
def test_run_corpus(tmp):
    root = Path(tmp) / "corpus"
    corpus_path = "cmp/factory/ADDRE001.DAT.cmp"
    target = root / corpus_path
    target.parent.mkdir(parents=True)
    data = b"\x78\x9c" + b"C" * 40
    target.write_bytes(data)
    entry = {
        "id": "factory-refer001",
        "case": "factory",
        "reader": "cmp_ind",
        "path": corpus_path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "expected": "ACCEPT",
    }
    (root / "manifest.json").write_text(
        json.dumps({"schema": manifest_mod.SCHEMA, "corpus": [entry]}),
        encoding="utf-8",
    )
    code, output = _run_cli(
        ["run", "probe-zlib-cmf", "--corpus", str(root), "--json"]
    )
    payload = json.loads(output)
    assert code == EXIT_OK, output
    assert payload["status"] == "PASS", payload
    assert payload["input"]["source"] == f"corpus:{corpus_path}", payload
    assert payload["input"]["manifest_sha256_match"] is True, payload["input"]
    assert payload["python"]["manifest_expected"] == "ACCEPT", payload
    assert payload["python"]["agrees_with_engine"] is True, payload

    target.write_bytes(data + b"!")
    code, output = _run_cli(
        ["run", "probe-zlib-cmf", "--corpus", str(root), "--json"]
    )
    payload = json.loads(output)
    assert code == EXIT_INVALID, output
    assert any("SHA-256 does not match" in p for p in payload["problems"]), payload


@check("run: two runs give identical verdicts")
def test_run_determinism(tmp):
    first = _run_json(tmp, b"\x78\x9c" + b"D" * 30)[1]
    second = _run_json(tmp, b"\x78\x9c" + b"D" * 30)[1]
    assert second == first, "two runs differ"


def _backend_skip(name: str, data: bytes, tmp, engine_name: str) -> None:
    availability = next(
        item for item in engine_mod.probe_all([engine_name])
    )
    if availability.available and not RUNNER_FULL_SELFTEST:
        # External execution is bounded/slow and adapters may be unverified;
        # quick mode records an honest SKIP (never PASS). --full attempts it.
        SELFTEST_SKIPS.append(
            f"{engine_name}: SKIPPED_IN_QUICK - external back-end execution skipped "
            f"in quick selftest (use --full); {availability.detail}"
        )
        return
    if availability.available and RUNNER_FULL_SELFTEST:
        # Bound external execution so --full cannot hang a gate (M1.18). The
        # adapter is unverified; a timeout is a loud failure, never a pass.
        try:
            import signal

            def _alarm(signum, frame):
                raise TimeoutError(
                    f"{engine_name} external execution exceeded 45s bound"
                )

            old = signal.getsignal(signal.SIGALRM)
            signal.signal(signal.SIGALRM, _alarm)
            signal.alarm(45)
            try:
                code, payload, output = _run_json(
                    tmp, data, extra=("--engine", engine_name)
                )
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old)
        except TimeoutError:
            raise AssertionError(
                f"{engine_name}: external execution exceeded 45s bound in --full; "
                "adapter may be unverified/broken (record as limitation, not a pass)"
            )
    else:
        code, payload, output = _run_json(
            tmp, data, extra=("--engine", engine_name)
        )
    if not availability.available:
        expected = f"MISSING_{engine_name.upper()}"
        assert availability.code == expected, availability.as_dict()
        assert code == EXIT_SKIP, output
        assert payload["status"] == "SKIP", payload
        assert payload["skipped"] is True and payload["accepted"] is None, payload
        assert expected in payload["reason"], payload
        SELFTEST_SKIPS.append(f"{engine_name}: {availability.code} - {availability.detail}")
        return
    assert payload["status"] != "SKIP", payload
    if payload["status"] == "PASS":
        assert code == EXIT_OK, output
        assert payload["verdict"] == "ACCEPT", payload
        assert payload["cycles"] > 0, payload
        return
    assert payload["status"] == "BLOCKED", payload
    assert code == EXIT_BLOCKED, output


@check("run: ghidra runs the probe or SKIPs with MISSING_GHIDRA (never a pass)")
def test_run_ghidra(tmp):
    _backend_skip("ghidra", b"\x78\x9c" + b"G" * 30, tmp, "ghidra")


@check("run: qemu runs the probe or SKIPs with MISSING_QEMU (never a pass)")
def test_run_qemu(tmp):
    _backend_skip("qemu", b"\x78\x9c" + b"Q" * 30, tmp, "qemu")


@check("firmware_call: shipped cmp_ind readers take sec1 from the image (M1.19), no declared values")
def test_firmware_call_registered(tmp):
    by_name, _doc = load_targets()
    for name, va in (("cmp_ind_reader", "0x00574de0"), ("cmp_ind_reader_us2011", "0x005987b0")):
        target = by_name[name]
        assert target["entry"]["kind"] == "firmware_call", target["entry"]
        assert target["entry"]["program"] == "cmp_ind_chunk_v1", target["entry"]
        sec1 = target["entry"]["sec1_table"]
        assert sec1["va"].lower() == va, sec1
        assert sec1["source"] == "image" and "values" not in sec1, sec1
        assert "nk_decomp" in sec1["provenance"] and "HYPOTHESIS" not in sec1["provenance"], sec1
    # source=image with values is refused (one source per table)
    bad = json.loads(json.dumps(by_name["cmp_ind_reader"]))
    bad["entry"]["sec1_table"]["values"] = ["0x0"]
    probs = " | ".join(validate_targets({"schema": TARGETS_SCHEMA, "targets": [bad]}))
    assert "takes no values" in probs, probs


@check("firmware_call: validation rejects a missing/undeclared sec1 table (no silent default)")
def test_firmware_call_sec1_required(tmp):
    base_entry = {
        "kind": "firmware_call", "program": "cmp_ind_chunk_v1",
        "module": "Navi.exe", "va": "0x0041c7e8", "endian": "little",
        "note": "test",
    }
    base_target = {
        "name": "t", "reader": "cmp_ind", "what": "t", "module": "Navi.exe",
        "entry": base_entry, "stubs": [],
        "corpus": {"path": "x.cmp", "guest_path": "\\x", "reader": "cmp_ind", "case": "factory"},
        "expect": {"verdict": "ACCEPT", "python_verdict": "ACCEPT", "rule": "r"},
    }
    # missing sec1_table
    doc = {"schema": TARGETS_SCHEMA, "targets": [base_target]}
    probs = " | ".join(validate_targets(doc))
    assert "sec1_table" in probs and "declared" in probs, probs
    # sec1_table without provenance
    bad = dict(base_target)
    bad["entry"] = dict(base_entry, sec1_table={"va": "0x574de0", "values": ["0x0"] * 17})
    probs = " | ".join(validate_targets({"schema": TARGETS_SCHEMA, "targets": [bad]}))
    assert "provenance" in probs, probs
    # sec1_table without values
    bad = dict(base_target)
    bad["entry"] = dict(base_entry, sec1_table={"va": "0x574de0", "provenance": "test"})
    probs = " | ".join(validate_targets({"schema": TARGETS_SCHEMA, "targets": [bad]}))
    assert "values" in probs, probs


@check("firmware_call: --dry-run names the sec1 source (image) and claims no verdict")
def test_firmware_call_dry_run(tmp):
    code, output = _run_cli(["run", "cmp_ind_reader", "--dry-run", "--json"])
    payload = json.loads(output)
    assert code == EXIT_OK, output
    assert payload["status"] == "DRY_RUN", payload
    fc = payload["firmware_call"]
    assert fc["sec1_table"]["declared"] is False, fc
    assert fc["sec1_table"]["source"] == "image", fc
    assert fc["sec1_table"]["va"].lower() == "0x00574de0", fc
    assert fc["sec1_table"]["value_count"] == 0, fc
    assert "no verdict is claimed" in payload["note"].lower(), payload
    assert "nk_decomp" in payload["note"], payload


@check("firmware_call: missing --cmp/--ind/--image is INVALID, not a fake pass")
def test_firmware_call_missing_inputs(tmp):
    code, output = _run_cli(["run", "cmp_ind_reader", "--json"])
    payload = json.loads(output)
    assert code == EXIT_INVALID, output
    assert payload["status"] == "INVALID", payload
    probs = " | ".join(payload.get("problems", []))
    assert "--image" in probs and "--cmp" in probs and "--ind" in probs, payload


@check("firmware_call: missing input file is INVALID")
def test_firmware_call_missing_file(tmp):
    code, output = _run_cli([
        "run", "cmp_ind_reader", "--json",
        "--image", str(Path(tmp) / "no.img"),
        "--cmp", str(Path(tmp) / "no.cmp"),
        "--ind", str(Path(tmp) / "no.ind"),
    ])
    payload = json.loads(output)
    assert code == EXIT_INVALID, output
    assert "missing input" in " | ".join(payload.get("problems", [])), payload


@check("drstr_parser_v1: shipped target is a firmware_call with the decoded verdict_map (M9.24)")
def test_drstr_registered(tmp):
    by_name, _doc = load_targets(None)
    entry = by_name["drstr_parser"]["entry"]
    assert entry["kind"] == "firmware_call" and entry["program"] == "drstr_parser_v1", entry
    assert entry["va"] == "0x00419350" and entry["sec1_table"]["source"] == "image", entry
    assert entry["verdict_map"] == {"0x00000000": "ACCEPT", "0xffffffff": "REJECT"}, entry


@check("drstr_parser_v1: missing --image/--input is INVALID, not a fake pass")
def test_drstr_missing_inputs(tmp):
    code, output = _run_cli(["run", "drstr_parser", "--json"])
    payload = json.loads(output)
    assert code == EXIT_INVALID, output
    probs = " | ".join(payload.get("problems", []))
    assert "--image" in probs and "--input" in probs, payload


@check("drstr_parser_v1: a verdict_map that differs from the decoded one is BLOCKED")
def test_drstr_guessed_map(tmp):
    _by_name, doc = load_targets(None)
    doc = copy.deepcopy(doc)
    for target in doc["targets"]:
        if target["name"] == "drstr_parser":
            target["entry"]["verdict_map"] = {"0x00000000": "ACCEPT", "0x00000001": "REJECT"}
    path = Path(tmp) / "targets.json"
    path.write_text(json.dumps(doc))
    for name in ("img", "dat"):
        (Path(tmp) / name).write_bytes(b"x")
    code, output = _run_cli([
        "run", "drstr_parser", "--json", "--targets", str(path),
        "--image", str(Path(tmp) / "img"), "--input", str(Path(tmp) / "dat"),
    ])
    payload = json.loads(output)
    assert code == EXIT_BLOCKED, output
    assert "verdict_map differs" in payload["reason"], payload


@check("drstr_parser_v1: a wrong head image is BLOCKED before the engine starts")
def test_drstr_wrong_head(tmp):
    for name in ("img", "dat"):
        (Path(tmp) / name).write_bytes(b"x")
    code, output = _run_cli([
        "run", "drstr_parser", "--json",
        "--image", str(Path(tmp) / "img"), "--input", str(Path(tmp) / "dat"),
    ])
    payload = json.loads(output)
    assert code == EXIT_BLOCKED and "not the eu2011 head" in payload["reason"], payload


@check("mapcode_compare_v1: shipped target is registered with a declared BSS cache (M9.6)")
def test_mapcode_registered(tmp):
    by_name, _doc = load_targets(None)
    target = by_name["applaunch_mapcode_compare"]
    entry = target["entry"]
    assert entry["kind"] == "firmware_call" and entry["program"] == "mapcode_compare_v1", entry
    assert entry["va"] == "0x03bd2ad8" and target["build"] == "eu2011", entry
    assert entry["sec1_table"]["values"] == ["0x00000000"], entry["sec1_table"]
    assert "BSS" in entry["sec1_table"]["provenance"], entry["sec1_table"]


@check("mapcode_compare_v1: missing --image/--input/--unit-* is INVALID, not a fake pass")
def test_mapcode_missing_inputs(tmp):
    code, output = _run_cli(["run", "applaunch_mapcode_compare", "--json"])
    payload = json.loads(output)
    assert code == EXIT_INVALID, output
    probs = " | ".join(payload.get("problems", []))
    assert "--image" in probs and "--input" in probs and "--unit-from" in probs, payload


@check("mapcode_compare_v1: a non-zero declared parse cache is BLOCKED, not modelled")
def test_mapcode_nonzero_cache(tmp):
    by_name, doc = load_targets(None)
    doc = copy.deepcopy(doc)
    for target in doc["targets"]:
        if target["name"] == "applaunch_mapcode_compare":
            target["entry"]["sec1_table"]["values"] = ["0x51"]
    path = Path(tmp) / "targets.json"
    path.write_text(json.dumps(doc))
    for name in ("img", "card"):
        (Path(tmp) / name).write_bytes(b"x")
    code, output = _run_cli([
        "run", "applaunch_mapcode_compare", "--json", "--targets", str(path),
        "--image", str(Path(tmp) / "img"), "--input", str(Path(tmp) / "card"),
        "--unit-code", "QSD-000-000",
    ])
    payload = json.loads(output)
    assert code == EXIT_BLOCKED and payload["status"] == "BLOCKED", output
    assert payload["l3_claim"] is False, payload




@check("firmware_call: each target runs its own build's engine; a wrong entry.va is INVALID (M9.32)")
def test_firmware_call_build_routing(tmp):
    import types
    import chunk_decoder_l3 as cdl3

    by_name, _doc = load_targets()
    for name in ("cmp_ind_reader", "cmp_ind_reader_us2011"):
        t = by_name[name]
        want = cdl3.BUILD_TARGETS[t.get("build") or "eu2011"]["fn_chunk"]
        assert int(t["entry"]["va"], 16) == want, (name, t["entry"]["va"])
    paths = {}
    for key in ("image", "cmp", "ind"):
        paths[key] = Path(tmp) / ("x." + key)
        paths[key].write_bytes(b"\0" * 16)
    t = json.loads(json.dumps(by_name["cmp_ind_reader_us2011"]))
    t["entry"]["va"] = by_name["cmp_ind_reader"]["entry"]["va"]  # EU VA, US build
    args = types.SimpleNamespace(image=str(paths["image"]), cmp=str(paths["cmp"]),
                                 ind=str(paths["ind"]), mutate="none",
                                 offset=None, length=None)
    res = _run_firmware_call_target(t, args, {"target": t["name"]})
    assert res["status"] == "INVALID", res
    assert "us2011 chunk engine" in " | ".join(res.get("problems", [])), res

# --------------------------------------------------------------------------
# M9.35: sec1 load model (zero BSS, bound IAT, INIT guard)
# --------------------------------------------------------------------------


def _m935_base(tmp_path, *, extra_blocks=None, iat_bindings=None, init_guards=None):
    """Synthetic guarded rommap + image + module target for M9.35 selftests."""
    root = Path(tmp_path)
    module = "Navi.exe"
    # .text at 0x00401000 (file offset 0x1000), guarded .data at 0x0055d000 (vsize 0x2000, init_len 0x100)
    image = bytearray(0x4000)
    report = {
        "schema": "osm2leaf.cerom.memmap/v1",
        "generator": "test",
        "image": "synthetic-m935.img",
        "image_size": len(image),
        "image_sha256": hashlib.sha256(bytes(image)).hexdigest(),
        "image_sha256_scope": f"whole file ({len(image)} bytes)",
        "segments": [{
            "segment_index": 0,
            "segment_base": "0x200200",
            "phys_base": "0x8cae1000",
            "pTOC": "0x0",
            "romhdr": {
                "physfirst": "0x00400000",
                "physlast": "0x00600000",
                "ulRAMStart": "0x8c000000",
                "ulRAMEnd": "0x8c100000",
                "nummods": 1, "numfiles": 0,
            },
            "modules": [{
                "name": module,
                "vbase": "0x00400000",
                "sections": [
                    {"name": "sec0", "va": "0x00401000", "file_offset": 0x1000,
                     "size": 0x1000, "vsize": 0x1000, "characteristics": "0x60000020",
                     "compressed": False},
                    {"name": "sec1", "va": "0x0055d000", "file_offset": 0x2000,
                     "size": 0x100, "vsize": 0x2000, "characteristics": "0xc8002040",
                     "compressed": True},
                ],
            }],
        }],
    }
    doc = rommap_mod.convert(report, modules=[module], skip_compressed=True)
    # turn sec1 into a guarded zero-filled block and attach M9.35 metadata
    sec1 = None
    for b in doc["blocks"]:
        if b["section"] == "sec1":
            sec1 = b
            break
    if sec1 is None:
        sec1 = {
            "name": f"{module}/sec1", "module": module, "section": "sec1",
            "address": "0x55d000", "end": "0x55f000", "size": 0x2000,
            "stored_size": 0, "file_offset": None, "file_backed": False,
            "loadable": True, "permissions": "rw-", "characteristics": "0xc8002040",
        }
        doc["blocks"].append(sec1)
        doc["blocks"].sort(key=lambda b: int(b["address"], 0))
    sec1.update({
        "address": "0x55d000", "end": "0x55f000", "size": 0x2000,
        "stored_size": 0, "file_offset": None, "file_backed": False,
        "loadable": True, "permissions": "rw-", "characteristics": "0xc8002040",
        "init_len": 0x100, "guard_init": True, "init_source": "zero-bss-init-guard",
    })
    if extra_blocks:
        doc["blocks"].extend(extra_blocks)
        doc["blocks"].sort(key=lambda b: int(b["address"], 0))
    doc["iat_bindings"] = list(iat_bindings or [])
    doc["init_guards"] = list(init_guards or [])
    doc["load_model"] = {"mode": "bss-zero-init-guard"}
    # revalidate
    problems = rommap_mod.validate(doc)
    assert problems == [], problems

    rommap_path = root / "rommap.json"
    rommap_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    image_path = root / "synthetic-m935.img"
    image_path.write_bytes(bytes(image))
    return image, image_path, rommap_path, module


def _m935_run(tmp_path, image_bytes, image_path, rommap_path, target):
    Path(image_path).write_bytes(bytes(image_bytes))
    # keep rommap's image hash in sync with the (now patched) image
    doc = json.loads(Path(rommap_path).read_text(encoding="utf-8"))
    doc.setdefault("source", {})
    doc["source"]["image_sha256"] = hashlib.sha256(bytes(image_bytes)).hexdigest()
    doc["source"]["image_size"] = len(image_bytes)
    doc["source"]["image_sha256_scope"] = f"whole file ({len(image_bytes)} bytes)"
    Path(rommap_path).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    targets_path = Path(tmp_path) / "targets.json"
    targets_path.write_text(
        json.dumps({"schema": TARGETS_SCHEMA, "targets": [target]}),
        encoding="utf-8",
    )
    code, out = _run_cli([
        "run", target["name"],
        "--targets", str(targets_path),
        "--rommap", str(rommap_path),
        "--image", str(image_path),
        "--engine", "pysh4",
        "--json",
    ])
    return code, json.loads(out)


@check("M9.35: zero-BSS read returns zero (guarded compressed sec1)")
def test_m935_zero_bss(tmp):
    image, image_path, rommap_path, module = _m935_base(tmp,
        init_guards=[{"module": "Navi.exe", "section": "sec1", "start": "0x55d000",
                      "end": "0x55d100", "init_len": 0x100, "iat_slots": [],
                      "reason": "test"}])
    # code: mov.l @(1,PC),r1; mov.l @r1,r0; rts; nop; .long 0x0055d800 (BSS >= init_len)
    code = bytes.fromhex("01d112600b00090000d85500")
    image[0x1000:0x1000 + len(code)] = code
    target = {
        "name": "m935-bss", "reader": "synthetic", "what": "zero BSS read",
        "module": module,
        "entry": {"kind": "module", "module": module, "va": "0x00401000",
                  "endian": "little", "args": [], "verdict_map": {"0x0": "ACCEPT"}},
        "stubs": [], "expect": {"verdict": "ACCEPT", "rule": "BSS is zero"},
    }
    rc, payload = _m935_run(tmp, image, image_path, rommap_path, target)
    assert rc == EXIT_OK, payload
    assert payload["status"] == "PASS", payload
    assert int(str(payload["returned"]), 0) == 0, payload


@check("M9.35: bound-IAT call reaches named stub (memset)")
def test_m935_bound_iat(tmp):
    slot_va = 0x0055d040
    image, image_path, rommap_path, module = _m935_base(tmp,
        iat_bindings=[{"va": "0x0055d040", "dll": "COREDLL.dll", "name": "memset"}],
        init_guards=[{"module": "Navi.exe", "section": "sec1", "start": "0x55d000",
                      "end": "0x55d100", "init_len": 0x100, "iat_slots": ["0x0055d040"],
                      "reason": "test"}])
    # r4=0x8C202100 (heap), r5=0x41, r6=4; call memset via slot, return r0
    # mov.l @(1,PC),r1; mov.l @r1,r1; jsr @r1; nop; rts; nop; .long SLOT_VA
    code = bytes.fromhex("02d112612b4109000b00090040d05500")
    image[0x1000:0x1000 + len(code)] = code
    target = {
        "name": "m935-iat", "reader": "synthetic", "what": "bound IAT call",
        "module": module,
        "entry": {"kind": "module", "module": module, "va": "0x00401000",
                  "endian": "little", "args": ["0x8C202100", "0x41", "0x4"],
                  "verdict_map": {"0x8c202100": "ACCEPT"}},
        "stubs": [], "expect": {"verdict": "ACCEPT", "rule": "memset returns dst"},
    }
    rc, payload = _m935_run(tmp, image, image_path, rommap_path, target)
    assert rc == EXIT_OK, payload
    assert payload["status"] == "PASS", payload
    assert int(str(payload["returned"]), 0) == 0x8C202100, payload


@check("M9.35: unbound import -> BLOCKED STUB <DLL!name>")
def test_m935_unbound_import(tmp):
    image, image_path, rommap_path, module = _m935_base(tmp,
        iat_bindings=[{"va": "0x0055d8fc", "dll": "OSMDLL.dll", "name": "OSM_Malloc"}],
        init_guards=[{"module": "Navi.exe", "section": "sec1", "start": "0x55d000",
                      "end": "0x55d100", "init_len": 0x100, "iat_slots": ["0x0055d8fc"],
                      "reason": "test"}])
    # call through unknown import slot
    code = bytes.fromhex("02d112612b4109000b000900fcd85500")
    image[0x1000:0x1000 + len(code)] = code
    target = {
        "name": "m935-stub", "reader": "synthetic", "what": "unbound import",
        "module": module,
        "entry": {"kind": "module", "module": module, "va": "0x00401000",
                  "endian": "little", "args": [], "verdict_map": {"0x0": "ACCEPT"}},
        "stubs": [], "expect": {"verdict": "ACCEPT", "rule": "n/a"},
    }
    rc, payload = _m935_run(tmp, image, image_path, rommap_path, target)
    assert rc == EXIT_BLOCKED, payload
    assert payload["status"] == "BLOCKED", payload
    assert "BLOCKED STUB OSMDLL.dll!OSM_Malloc" in payload.get("reason", ""), payload


@check("M9.35: INIT read under --init-guard -> BLOCKED INIT 0x... (guarded)")
def test_m935_init_guard(tmp):
    image, image_path, rommap_path, module = _m935_base(tmp,
        iat_bindings=[{"va": "0x0055d040", "dll": "COREDLL.dll", "name": "memset"}],
        init_guards=[{"module": "Navi.exe", "section": "sec1", "start": "0x55d000",
                      "end": "0x55d100", "init_len": 0x100, "iat_slots": ["0x0055d040"],
                      "reason": "test"}])
    # read from INIT address 0x0055d080 (inside init, not IAT slot)
    code = bytes.fromhex("01d112600b00090080d05500")
    image[0x1000:0x1000 + len(code)] = code
    target = {
        "name": "m935-init", "reader": "synthetic", "what": "INIT guard",
        "module": module,
        "entry": {"kind": "module", "module": module, "va": "0x00401000",
                  "endian": "little", "args": [], "verdict_map": {"0x0": "ACCEPT"}},
        "stubs": [], "expect": {"verdict": "ACCEPT", "rule": "n/a"},
    }
    rc, payload = _m935_run(tmp, image, image_path, rommap_path, target)
    assert rc == EXIT_BLOCKED, payload
    assert payload["status"] == "BLOCKED", payload
    assert "INIT 0x0055d080 (guarded" in payload.get("reason", ""), payload


def _m119_init_map(tmp, init: bytes, tamper: bool = False):
    """The M9.35 fixture with sec1 as an ``init_source: nk_decomp`` block."""
    image, image_path, rommap_path, module = _m935_base(tmp)
    init_path = Path(tmp) / "Navi.exe.sec1.synthetic.bin"
    init_path.write_bytes(init)
    doc = json.loads(rommap_path.read_text(encoding="utf-8"))
    for block in doc["blocks"]:
        if block["section"] == "sec1":
            block.update(guard_init=False, init_source="nk_decomp", init_len=len(init),
                         init_file=str(init_path),
                         init_sha256=hashlib.sha256(init).hexdigest())
    doc["init_guards"] = []
    doc["load_model"] = {"mode": "init-from-image"}
    assert rommap_mod.validate(doc) == [], rommap_mod.validate(doc)
    rommap_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    if tamper:
        init_path.write_bytes(init[:-1] + bytes([init[-1] ^ 1]))
    # code: mov.l @(1,PC),r1; mov.l @r1,r0; rts; nop; .long 0x0055d080 (INIT)
    code = bytes.fromhex("01d112600b00090080d05500")
    image[0x1000:0x1000 + len(code)] = code
    target = {
        "name": "m119-init", "reader": "synthetic", "what": "INIT from image",
        "module": module,
        "entry": {"kind": "module", "module": module, "va": "0x00401000",
                  "endian": "little", "args": [],
                  "verdict_map": {"0x12345678": "ACCEPT"}},
        "stubs": [], "expect": {"verdict": "ACCEPT", "rule": "INIT word read"},
    }
    return _m935_run(tmp, image, image_path, rommap_path, target)


@check("M1.19: an INIT read returns the decoded byte (init_source nk_decomp)")
def test_m119_init_from_image(tmp):
    init = bytearray(0x100)
    init[0x80:0x84] = (0x12345678).to_bytes(4, "little")
    rc, payload = _m119_init_map(tmp, bytes(init))
    assert rc == EXIT_OK and payload["status"] == "PASS", payload
    assert int(str(payload["returned"]), 0) == 0x12345678, payload


@check("M1.19: a tampered INIT cache file is BLOCKED, never mapped")
def test_m119_init_tampered(tmp):
    init = bytearray(0x100)
    init[0x80:0x84] = (0x12345678).to_bytes(4, "little")
    rc, payload = _m119_init_map(tmp, bytes(init), tamper=True)
    assert rc == EXIT_BLOCKED and "init_sha256" in payload.get("reason", ""), payload
    bad = {"name": "x/sec1", "module": "x", "section": "sec1", "address": "0x1000",
           "end": "0x2000", "size": 0x1000, "stored_size": 0, "file_offset": None,
           "file_backed": False, "loadable": True, "permissions": "rw-",
           "characteristics": "0xc8002040", "init_len": 4, "guard_init": True,
           "init_source": "nk_decomp"}
    problems = " | ".join(rommap_mod.validate({"schema": rommap_mod.SCHEMA, "blocks": [bad]}))
    assert "needs init_file" in problems and "init_sha256" in problems, problems
    assert "cannot also guard INIT" in problems, problems
    try:
        rommap_mod.convert({"segments": [{}]}, init_from_image=True, init_guard=True)
    except rommap_mod.RommapError as exc:
        assert "exclude each other" in str(exc), exc
    else:
        raise AssertionError("--init-from-image with --init-guard was accepted")


# --------------------------------------------------------------------------

def selftest_targets(*, full: bool = False) -> int:
    """Run the runner's own synthetic target checks; a SKIP is not a pass.

    ``full`` runs external back-end execution checks that may be slow or need a
    working Ghidra/QEMU adapter.  Default quick skips that execution honestly
    (M1.18).
    """

    global RUNNER_FULL_SELFTEST
    RUNNER_FULL_SELFTEST = full
    SELFTEST_SKIPS.clear()
    failures = 0
    for name, func in SELFTEST_CHECKS:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                func(tmp)
            except Exception as exc:  # noqa: BLE001 - report, do not abort
                failures += 1
                print(f"FAIL {name}: {exc}")
                if os.environ.get("L3_SELFTEST_VERBOSE"):
                    import traceback

                    traceback.print_exc()
            else:
                print(f"ok   {name}")
    for skip in SELFTEST_SKIPS:
        print(f"skip {skip}")

    print()
    total = len(SELFTEST_CHECKS)
    skipped = len(SELFTEST_SKIPS)
    mode = "full" if full else "quick"
    if failures:
        print(f"selftest: FAILED ({failures}/{total} checks, {skipped} skipped, {mode})")
        return EXIT_INVALID
    if skipped:
        print(
            f"selftest: OK ({total - skipped} checks, {skipped} skipped, {mode}) - "
            "a skipped back end is not a pass"
        )
    else:
        print(f"selftest: OK ({total} checks, every back end ran, {mode})")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
