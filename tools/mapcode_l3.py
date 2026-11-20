#!/usr/bin/env python3
"""Run AppLaunch.dll's map-code compare ``fn 0x03bd2ad8`` (EU2011 build B) in PySh4 (M9.6).

``fn 0x03bd2ad8`` (build B, ``--image-start 0x3e00200``; M2.5/M2.15) takes no
arguments and returns ``1`` when the 11-byte unit record matches the first 11
bytes of ``HDD_INFO.TXT`` line 1, ``0`` otherwise (the router
``fn 0x03bd2ecc`` then raises error ``0x50`` = ``DIFFERENT MAP CODE``).  Its
body, decoded with ``tools/sh4dis.py``:

1. ``KernelIoControl(0x0101302C, &in=0, 4, &out, 8, NULL)`` inside a
   ``SetKMode(1)``/``SetKMode(0)`` pair; copies 11 bytes from
   ``*(u32 *)out + 0x60`` (the unit record).
2. If the parse cache byte ``*(u8 *)0x01f74b30`` is zero (it is BSS: sec1
   ``+0x1b30 >= init 0x3ac``, ``tools/va_class.py``), opens
   ``\\SystemSD\\VER_INFO\\HDD_INFO.TXT`` (``CreateFileW``, ``GENERIC_READ``,
   ``OPEN_EXISTING``), reads at most ``0x60`` bytes, closes it, and stores the
   lines in 16-byte slots at ``0x01f74b30`` (15 chars max per slot).
3. Compares the 11 unit bytes with slot 0 bytes 0..10; on mismatch formats both
   with ``wsprintfW("%c")`` and logs ``VerInf:%s / HddInf:%s`` through
   ``NKDbgPrintfW``.

Only the code and its string pool come from the image (``cerom.py`` module
and section lookup, no fitted delta).  The calls go through 4-insn import
thunks in sec0 (``mov.l @(pc),r0; mov.l @r0,r0; jmp @r0; nop``) whose IAT
slots are in compressed sec1.  ``resolve_thunks`` finds every such thunk in
sec0, maps its slot (sec1 ``realaddr`` based) to the rva-based import slot,
and names it by the COREDLL ordinal ``cerom.imports`` gives and the name
build B's own ``coredll.dll`` export table gives.  The thunk VAs are not
hard-coded (they are listed in the EXP).  Each needed thunk is replaced by a
host stub:

==============  ======  =====================================
COREDLL name    ord.    stub behaviour
==============  ======  =====================================
KernelIoControl  #557   writes a pointer to a host record whose ``+0x60``
                        holds the declared unit code, returns 1
SetKMode         #630   returns 0
CreateFileW      #168   opens the one served guest file, else ``-1``
ReadFile         #170   copies from the served file
CloseHandle      #553   returns 1
memset           #1047  fills
wsprintfW        #56    ``%c`` only (the one format used)
NKDbgPrintfW     #545   ``%s`` only, logged
==============  ======  =====================================

The unit record is **not** in the image (a kernel IOCTL answer).  It is a
declared input: by default it is the first 11 bytes of line 1 of a factory
``HDD_INFO.TXT`` given with ``--unit-from``, on the assumption that the unit a
factory card shipped with matches that card.  That assumption is stated in
every result; it is not a measurement of a real unit.

Exit codes: 0 the firmware verdict equals ``--expect`` (or no ``--expect``),
1 it differs, 3 image or input missing, 4 BLOCKED (the engine stopped on an
unmapped access or an unmodelled call; the PC is named).

Usage::

  mapcode_l3.py --selftest
  mapcode_l3.py extract CARD.img -o OUT/HDD_INFO.TXT
  mapcode_l3.py run IMG256 --card HDD_INFO.TXT --unit-from FACTORY_HDD_INFO.TXT \
      [--expect ACCEPT|REJECT] [--json]

Method and results: docs/experiments/EXP-2026-11-19-M9.6-mapcode-compare.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "l3_harness"))

import cerom  # noqa: E402
from engine import EngineError, PySh4, StubReturn  # noqa: E402

IMAGE_START = 0x3E00200
MODULE = "AppLaunch.dll"
BUILD = "eu2011"
FN_COMPARE = 0x03BD2AD8
FN_CHECK2 = 0x03BD2CE4      # MapDBVer range (error 0x51), M2.19
FN_ROUTER = 0x03BD2ECC      # router(partition): check 1 -> 0x50, check 2 -> 0x51
FN_DISPATCH = 0x03BCAFB8    # AppLaunch error dispatcher (M1.34, C-5351)
BOUNDS_MIN_OFFSET = 112     # unit record +112: MapDBVer min, u16 big-endian
BOUNDS_MAX_OFFSET = 114     # unit record +114: MapDBVer max, u16 big-endian
GLOBAL_CACHE = 0x01F74B30
GUEST_PATH = "\\SystemSD\\VER_INFO\\HDD_INFO.TXT"
IOCTL_TARGET_INFO = 0x0101302C
UNIT_OFFSET = 0x60
CODE_LEN = 11

#: COREDLL imports the compare calls, by name and ordinal (build B).
NEEDED = {
    "KernelIoControl": 557, "SetKMode": 630, "CreateFileW": 168,
    "ReadFile": 170, "CloseHandle": 553, "memset": 1047,
    "wsprintfW": 56, "NKDbgPrintfW": 545,
}
THUNK_SHAPE = (0xD001, 0x6002, 0x402B, 0x0009)

STK_VA = 0x30000000
STK_SIZE = 0x10000
REC_VA = 0x40000000
REC_SIZE = 0x100
HANDLE = 0x00001234
INVALID_HANDLE = 0xFFFFFFFF
M32 = 0xFFFFFFFF


class Blocked(Exception):
    """The run stopped on something the harness does not model."""


class _Halt(Exception):
    """The dispatcher stub in ``halt`` mode: the production dispatcher does
    not return after the first shown error (C-5351), so the run ends here."""


# ---------------------------------------------------------------------------
# inputs


def unit_code_from(hdd_info: bytes) -> bytes:
    """First 11 bytes of line 1 (the M2.15 field the compare reads)."""
    line = hdd_info.split(b"\n", 1)[0].rstrip(b"\r")
    if len(line) < CODE_LEN:
        raise ValueError(f"line 1 has {len(line)} bytes, need {CODE_LEN}")
    return line[:CODE_LEN]


def module_layout(image: bytes):
    """[(section dict, compressed, bytes or None)] for AppLaunch.dll build B."""
    rom = cerom.CERom(image, IMAGE_START)
    mod = rom.module(MODULE)
    out = []
    for sec in rom.o32(mod):
        comp = bool(sec["flags"] & cerom.IMAGE_SCN_COMPRESSED)
        blob = None
        if not comp:
            off = rom.va2file(sec["dataptr"])
            blob = image[off:off + sec["psize"]]
        out.append((sec, comp, blob))
    return out


def resolve_thunks(image: bytes) -> dict[int, tuple[str, int]]:
    """{thunk VA: (COREDLL name, ordinal)} for the NEEDED imports, from the image."""
    rom = cerom.CERom(image, IMAGE_START)
    mod = rom.module(MODULE)
    vbase = rom.e32(mod)["vbase"]
    secs = list(rom.o32(mod))
    imports = {slot: (dll, ordinal) for dll, slot, _nm, ordinal in rom.imports(mod)}
    names = {o: n for o, n, _rva in rom.exports(rom.module("coredll.dll"))}
    out: dict[int, tuple[str, int]] = {}
    for sec, comp, blob in module_layout(image):
        if comp or not sec["flags"] & 0x20000000:
            continue
        base = sec["realaddr"]
        for off in range(0, len(blob) - 12, 2):
            words = struct.unpack_from("<4H", blob, off)
            if words != THUNK_SHAPE:
                continue
            pc = base + off
            lit = ((pc & ~3) + 4 + 4) - base
            (slot,) = struct.unpack_from("<I", blob, lit)
            for data_sec in secs:
                lo = data_sec["realaddr"]
                if lo <= slot < lo + data_sec["vsize"]:
                    rva_slot = vbase + data_sec["rva"] + slot - lo
                    dll, ordinal = imports.get(rva_slot, (None, None))
                    if dll and dll.lower() == "coredll.dll" and ordinal is not None:
                        name = names.get(ordinal)
                        if NEEDED.get(name) == ordinal:
                            out[pc] = (name, ordinal)
    return out


def extract_hdd_info(card_path: str) -> bytes:
    """Read ``VER_INFO/HDD_INFO.TXT`` from the card's FAT32 partition."""
    import mkcard
    with open(card_path, "rb") as handle:
        _, geo, fat = mkcard.open_map_partition(handle)
        return mkcard.img_read(handle, geo, fat, "VER_INFO/HDD_INFO.TXT")


# ---------------------------------------------------------------------------
# firmware run


def _wstr(eng, va: int, limit: int = 512) -> str:
    raw = bytearray()
    for i in range(limit):
        ch = eng.read_mem(va + 2 * i, 2)
        if ch == b"\x00\x00":
            break
        raw += ch
    return raw.decode("utf-16-le", "replace")


def run_compare(image: bytes, card: bytes | None, unit_code: bytes,
                fn: int = FN_COMPARE, thunks: dict | None = None,
                bounds: tuple[int, int] | None = None, args: tuple = (),
                dispatch: str | None = None) -> dict:
    """Run *fn* with *card* served at the guest path; return the result dict.

    ``card=None`` serves no file (``CreateFileW`` fails), a control for the
    open-failure branch.

    M2.19 extensions (defaults keep the M9.6 behaviour): *bounds* = declared
    ``(min, max)`` MapDBVer written big-endian at record ``+112``/``+114``
    (check 2 reads them); *args* are passed in ``r4``.. (the router takes the
    partition number); *dispatch* stubs the error dispatcher ``fn 0x03bcafb8``
    and records its code: ``"return"`` returns to the caller (the ProtoLevel /
    no-screen path), ``"halt"`` ends the run there (the production path,
    C-5351).  Without *dispatch* a call of the dispatcher runs into
    unmodelled code and is reported ``Blocked``.
    """
    if len(unit_code) != CODE_LEN:
        raise ValueError(f"unit code must be {CODE_LEN} bytes")
    layout = module_layout(image)
    eng = PySh4(endian="little")
    sec_ranges = []
    for sec, comp, blob in layout:
        name = "sec@%08x" % sec["realaddr"]
        if comp:
            # Compressed .data: mapped as zeros.  Every access is logged so the
            # EXP can show which bytes the run depended on.
            eng.map(name, sec["realaddr"], bytearray(sec["vsize"]), "rw")
            sec_ranges.append((sec["realaddr"], sec["realaddr"] + sec["vsize"], name))
        else:
            data = bytearray(blob) + bytearray(max(0, sec["vsize"] - len(blob)))
            eng.map(name, sec["realaddr"], data, "rx")
    eng.map("stack", STK_VA, bytearray(STK_SIZE), "rw")
    record = bytearray(REC_SIZE)
    record[UNIT_OFFSET:UNIT_OFFSET + CODE_LEN] = unit_code
    if bounds is not None:
        struct.pack_into(">HH", record, BOUNDS_MIN_OFFSET, bounds[0] & 0xFFFF, bounds[1] & 0xFFFF)
    eng.map("ioctl_record", REC_VA, record, "rw")
    eng.set_regs(r15=STK_VA + STK_SIZE // 2)

    log: list[dict] = []
    sec_access: dict[str, set] = {}
    files = {"open": None, "pos": 0}

    def reg(name):
        return eng._get_reg(name) & M32

    def stack_arg(n):  # SH-4 WinCE ABI: arg 5 at @(16,r15) of the caller
        return struct.unpack("<I", eng.read_mem(reg("r15") + 16 + 4 * (n - 5), 4))[0]

    def note(name, args, ret, **extra):
        item = {"stub": name, "args": [f"0x{a:x}" for a in args], "ret": f"0x{ret & M32:x}"}
        item.update(extra)
        log.append(item)
        return StubReturn(ret)

    def k_ioctl(e, va):
        code, inbuf, insz, outbuf = reg("r4"), reg("r5"), reg("r6"), reg("r7")
        outsz, retptr = stack_arg(5), stack_arg(6)
        if code != IOCTL_TARGET_INFO:
            raise Blocked(f"KernelIoControl code 0x{code:x} not modelled")
        if outsz < 4:
            raise Blocked(f"KernelIoControl out size {outsz} < 4")
        e.write_mem(outbuf, struct.pack("<I", REC_VA))
        if retptr:
            e.write_mem(retptr, struct.pack("<I", 4))
        return note("KernelIoControl", [code, inbuf, insz, outbuf, outsz, retptr], 1,
                    served=f"*out = record@0x{REC_VA:x}, +0x60 = declared unit code")

    def setkmode(e, va):
        return note("SetKMode", [reg("r4")], 0)

    def createfile(e, va):
        path = _wstr(e, reg("r4"))
        args = [reg("r4"), reg("r5"), reg("r6"), reg("r7"), stack_arg(5), stack_arg(6), stack_arg(7)]
        if card is not None and path.lower() == GUEST_PATH.lower():
            files["open"], files["pos"] = card, 0
            return note("CreateFileW", args, HANDLE, path=path)
        return note("CreateFileW", args, INVALID_HANDLE, path=path, served="no such file")

    def readfile(e, va):
        h, buf, n, nread = reg("r4"), reg("r5"), reg("r6"), reg("r7")
        ovl = stack_arg(5)
        if h != HANDLE or files["open"] is None:
            raise Blocked(f"ReadFile on unknown handle 0x{h:x}")
        chunk = files["open"][files["pos"]:files["pos"] + n]
        files["pos"] += len(chunk)
        e.write_mem(buf, chunk)
        if nread:
            e.write_mem(nread, struct.pack("<I", len(chunk)))
        return note("ReadFile", [h, buf, n, nread, ovl], 1, bytes_read=len(chunk))

    def closehandle(e, va):
        files["open"] = None
        return note("CloseHandle", [reg("r4")], 1)

    def memset(e, va):
        dst, val, n = reg("r4"), reg("r5"), reg("r6")
        if n:
            e.write_mem(dst, bytes([val & 0xFF]) * n)
        return note("memset", [dst, val, n], dst)

    def wsprintf(e, va):
        dst, fmt_va, a1 = reg("r4"), reg("r5"), reg("r6")
        fmt = _wstr(e, fmt_va)
        if fmt != "%c":
            raise Blocked(f"wsprintfW format {fmt!r} not modelled")
        e.write_mem(dst, chr(a1 & 0xFFFF).encode("utf-16-le") + b"\x00\x00")
        return note("wsprintfW", [dst, fmt_va, a1], 1, fmt=fmt)

    def dbgprint(e, va):
        fmt_va = reg("r4")
        fmt = _wstr(e, fmt_va)
        values = [reg("r5"), reg("r6"), reg("r7")]
        specs = [fmt[i + 1:i + 2] for i in range(len(fmt)) if fmt[i] == "%"]
        if any(sp not in ("s", "d") for sp in specs) or len(specs) > 3:
            raise Blocked(f"NKDbgPrintfW format {fmt!r} not modelled")
        out, k, i = "", 0, 0
        while i < len(fmt):
            if fmt[i] == "%":
                v = values[k]
                out += _wstr(e, v) if fmt[i + 1] == "s" else str(v - (1 << 32) if v & 0x80000000 else v)
                k += 1
                i += 2
            else:
                out += fmt[i]
                i += 1
        return note("NKDbgPrintfW", [fmt_va] + values[:k], 0, text=out)

    handlers = {"KernelIoControl": k_ioctl, "SetKMode": setkmode,
                "CreateFileW": createfile, "ReadFile": readfile,
                "CloseHandle": closehandle, "memset": memset,
                "wsprintfW": wsprintf, "NKDbgPrintfW": dbgprint}
    thunks = resolve_thunks(image) if thunks is None else thunks
    found = sorted({name for name, _ord in thunks.values()})
    if found != sorted(NEEDED):
        raise Blocked(f"import thunks not resolved: {sorted(set(NEEDED) - set(found))}")
    for va, (name, _ord) in thunks.items():
        eng.on_exec(va, handlers[name])

    dispatched: list[int] = []
    if dispatch is not None:
        if dispatch not in ("return", "halt"):
            raise ValueError("dispatch must be 'return' or 'halt'")

        def dispatcher(e, va):
            code = reg("r4")
            dispatched.append(code)
            note("dispatch", [code], 0, mode=dispatch)
            if dispatch == "halt":
                raise _Halt()
            return StubReturn(0)

        eng.on_exec(FN_DISPATCH, dispatcher)

    orig_load, orig_store = eng._load, eng._store

    def track(kind, va, size):
        for lo, hi, name in sec_ranges:
            if lo <= va < hi:
                sec_access.setdefault(f"{kind} {name}", set()).update(range(va, va + size))

    def load(va, size):
        track("read", va, size)
        return orig_load(va, size)

    def store(va, size, value):
        track("write", va, size)
        return orig_store(va, size, value)

    eng._load, eng._store = load, store
    halted = False
    try:
        r0 = eng.call(fn, list(args))
    except _Halt:
        halted, r0 = True, None
    except Blocked:
        raise
    except EngineError as exc:
        raise Blocked(f"engine stopped: {exc}") from exc

    cache = bytes(eng.read_mem(GLOBAL_CACHE, 0x60))
    accesses = {}
    for key, addrs in sorted(sec_access.items()):
        accesses[key] = {"lo": f"0x{min(addrs):08x}", "hi": f"0x{max(addrs) + 1:08x}",
                         "bytes": len(addrs)}
    return {
        "fn": f"0x{fn:08x}",
        "build": BUILD,
        "module": MODULE,
        "r0": r0,
        "verdict": ("HALTED" if halted else
                    {1: "ACCEPT", 0: "REJECT"}.get(r0, f"UNKNOWN r0=0x{r0:x}")),
        "dispatched": [f"0x{c:x}" for c in dispatched],
        "halted": halted,
        "bounds": None if bounds is None else {"min": bounds[0], "max": bounds[1]},
        "card_slot2": cache[32:48].split(b"\x00", 1)[0].decode("latin-1"),
        "insns": eng.last_run.insns if hasattr(eng.last_run, "insns") else None,
        "unit_code": unit_code.decode("latin-1"),
        "card_slot0": cache[:CODE_LEN].decode("latin-1"),
        "thunks": {f"0x{va:08x}": f"COREDLL #{o} {n}" for va, (n, o) in sorted(thunks.items())},
        "stub_log": log,
        "compressed_section_access": accesses,
    }


# ---------------------------------------------------------------------------
# commands


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cmd_extract(args) -> int:
    if not Path(args.card).exists():
        print(f"missing input: {args.card}", file=sys.stderr)
        return 3
    data = extract_hdd_info(args.card)
    Path(args.out).write_bytes(data)
    print(f"VER_INFO/HDD_INFO.TXT {len(data)} bytes sha256 {_sha(data)} -> {args.out}")
    return 0


def cmd_run(args) -> int:
    for path in [args.image, args.unit_from] + ([args.card] if args.card else []):
        if path and not Path(path).exists():
            print(f"missing input: {path}", file=sys.stderr)
            return 3
    if args.unit_code:
        unit = args.unit_code.encode("latin-1")
        unit_src = "--unit-code"
    elif args.unit_from:
        raw = Path(args.unit_from).read_bytes()
        unit = unit_code_from(raw)
        unit_src = f"--unit-from line 1 (sha256 {_sha(raw)})"
    else:
        print("need --unit-code or --unit-from (the unit record is a declared input)",
              file=sys.stderr)
        return 3
    card = Path(args.card).read_bytes() if args.card else None
    with open(args.image, "rb") as fh:
        image = fh.read(128 << 20)
    try:
        result = run_compare(image, card, unit)
    except Blocked as exc:
        print(f"BLOCKED: {exc}")
        return 4
    result["inputs"] = {
        "card": args.card, "card_sha256": _sha(card) if card is not None else None,
        "unit_source": unit_src,
        "assumption": "unit record +0x60 = declared code (not read from a unit)",
    }
    if args.json:
        print(json.dumps(result, indent=1))
    else:
        print(f"fn {result['fn']} ({BUILD} {MODULE}) r0={result['r0']} "
              f"verdict={result['verdict']} insns={result['insns']}")
        print(f"  unit +0x60 : {result['unit_code']!r} ({unit_src})")
        print(f"  card slot0 : {result['card_slot0']!r}")
        for item in result["stub_log"]:
            extra = {k: v for k, v in item.items() if k not in ("stub", "args", "ret")}
            print(f"  stub {item['stub']}({', '.join(item['args'])}) -> {item['ret']}"
                  + (f"  {extra}" if extra else ""))
        for key, span in result["compressed_section_access"].items():
            print(f"  {key}: {span['lo']}..{span['hi']} ({span['bytes']} B)")
    if args.expect and result["verdict"] != args.expect:
        return 1
    return 0


# ---------------------------------------------------------------------------
# self-test


def selftest() -> int:
    """Synthetic checks of the stub layer and the input rules.

    The compare itself lives in the vendor image, so the self-test runs a
    tiny hand-assembled SH-4 routine at the real FN address inside a fake
    "AppLaunch" layout: it calls the KernelIoControl and CreateFileW/ReadFile
    thunks the same way and compares 11 bytes.  It checks the stubs, not the
    firmware.
    """
    failures = 0

    def check(name, cond, detail=""):
        nonlocal failures
        print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  {detail}"))
        if not cond:
            failures += 1

    factory = b"QSD-000-000\r\nAAA-000-000\r\n"
    check("unit_code_from takes line 1 bytes 0..10",
          unit_code_from(factory) == b"QSD-000-000")
    try:
        unit_code_from(b"SHORT\r\n")
        check("unit_code_from rejects a short line 1", False)
    except ValueError:
        check("unit_code_from rejects a short line 1", True)

    # Hand-assembled routine, little-endian halfwords.  It reproduces the
    # call shapes of fn 0x03bd2ad8: IOCTL with out at r15+36 and outsz at
    # @(16,r15); CreateFileW with the path pointer; ReadFile into r15+68.
    # Then compares 11 bytes of *(out)+0x60 with the read buffer.
    # Synthetic layout: everything is an offset from the real entry, so no
    # address here stands for a firmware function except FN_COMPARE itself.
    code_va = FN_COMPARE
    pool_va, path_va = code_va + 0x128, code_va + 0x228
    fake_thunks = {code_va + 0x300: ("KernelIoControl", 557),
                   code_va + 0x310: ("CreateFileW", 168),
                   code_va + 0x320: ("ReadFile", 170)}
    for k, (name, ordinal) in enumerate(n for n in NEEDED.items()
                                         if n[0] not in ("KernelIoControl", "CreateFileW", "ReadFile")):
        fake_thunks[code_va + 0x330 + 0x10 * k] = (name, ordinal)
    asm = {
        "sts.l pr,@-r15": 0x4F22, "lds.l @r15+,pr": 0x4F26, "rts": 0x000B, "nop": 0x0009,
    }
    # frame: add #-92 twice (184 bytes)
    def mov_imm(imm, rn):
        return 0xE000 | (rn << 8) | (imm & 0xFF)

    def movl_pc(disp_idx, rn, pc):
        target = pool_va + 4 * disp_idx
        disp = (target - ((pc & ~3) + 4)) // 4
        assert 0 <= disp < 256
        return 0xD000 | (rn << 8) | disp

    pool = [IOCTL_TARGET_INFO, code_va + 0x300, path_va, code_va + 0x310, code_va + 0x320]
    prog: list = []
    pc = code_va

    def emit(word):
        nonlocal pc
        prog.append(word)
        pc += 2

    emit(asm["sts.l pr,@-r15"])
    emit(0x7FA4)                            # add #-92,r15
    emit(0x7FA4)                            # add #-92,r15
    emit(movl_pc(0, 4, pc))                 # r4 = ioctl code
    emit(mov_imm(36, 7)); emit(0x37FC)      # r7 = 36; add r15,r7
    emit(mov_imm(8, 1)); emit(0x1F14)       # r1 = 8; mov.l r1,@(16,r15)
    emit(mov_imm(0, 1)); emit(0x1F15)       # mov.l r1,@(20,r15)
    emit(movl_pc(1, 3, pc)); emit(0x430B); emit(asm["nop"])  # jsr KernelIoControl
    emit(movl_pc(2, 4, pc))                 # r4 = path
    emit(movl_pc(3, 3, pc)); emit(0x430B); emit(asm["nop"])  # jsr CreateFileW
    emit(0x6403)                            # mov r0,r4 (handle)
    emit(mov_imm(68, 5)); emit(0x35FC)      # r5 = r15+68
    emit(mov_imm(96, 6))                    # r6 = 96
    emit(mov_imm(28, 7)); emit(0x37FC)      # r7 = r15+28
    emit(movl_pc(4, 3, pc)); emit(0x430B); emit(asm["nop"])  # jsr ReadFile
    emit(0x53F9)                            # mov.l @(36,r15),r3
    emit(0x7360)                            # add #96,r3
    emit(mov_imm(68, 4)); emit(0x34FC)      # r4 = r15+68
    emit(mov_imm(11, 1))                    # r1 = 11
    emit(mov_imm(1, 0))                     # r0 = 1 (assume equal)
    loop = pc
    emit(0x6534)                            # mov.b @r3+,r5
    emit(0x6644)                            # mov.b @r4+,r6
    emit(0x3560)                            # cmp/eq r6,r5
    emit(0x8900)                            # bt +0 (skip next)
    emit(mov_imm(0, 0))                     # r0 = 0
    emit(0x4110)                            # dt r1
    disp = (loop - (pc + 4)) // 2
    emit(0x8B00 | (disp & 0xFF))            # bf loop
    emit(0x7F5C); emit(0x7F5C)              # add #92,r15 twice
    emit(asm["lds.l @r15+,pr"])
    emit(asm["rts"]); emit(asm["nop"])

    def fake_text():
        text = bytearray(0x400)
        for va in fake_thunks:   # thunk shape; hooked, so never executed
            struct.pack_into("<4H", text, va - code_va, *THUNK_SHAPE)
        for i, w in enumerate(prog):
            struct.pack_into("<H", text, i * 2, w)
        for i, v in enumerate(pool):
            struct.pack_into("<I", text, pool_va - code_va + 4 * i, v)
        wpath = GUEST_PATH.encode("utf-16-le") + b"\x00\x00"
        text[path_va - code_va:path_va - code_va + len(wpath)] = wpath
        return text

    # Re-use run_compare's stub layer by monkeypatching module_layout.
    global module_layout
    real_layout = module_layout

    def fake_layout(_image):
        text = fake_text()
        sec = {"realaddr": code_va, "vsize": len(text), "psize": len(text), "flags": 0x60000020}
        bss = {"realaddr": GLOBAL_CACHE & ~0xFFF, "vsize": 0x1000, "psize": 0, "flags": 0xC0002040}
        return [(sec, False, bytes(text)), (bss, True, None)]

    module_layout = fake_layout
    try:
        good = run_compare(b"", factory, b"QSD-000-000", thunks=fake_thunks)
        check("synthetic: equal 11 bytes -> r0=1 ACCEPT", good["verdict"] == "ACCEPT", good["r0"])
        stubs = [s["stub"] for s in good["stub_log"]]
        check("synthetic: stub log names IOCTL, CreateFileW, ReadFile in order",
              stubs == ["KernelIoControl", "CreateFileW", "ReadFile"], stubs)
        check("synthetic: ReadFile served the whole small file",
              good["stub_log"][2]["bytes_read"] == len(factory))
        bad = run_compare(b"", b"QSD-000-001\r\n" + factory[13:], b"QSD-000-000", thunks=fake_thunks)
        check("synthetic: one changed line-1 byte -> r0=0 REJECT", bad["verdict"] == "REJECT", bad["r0"])
        try:
            run_compare(b"", None, b"QSD-000-000", thunks=fake_thunks)
            check("synthetic: ReadFile on the failed handle is BLOCKED, not served", False)
        except Blocked as exc:
            check("synthetic: ReadFile on the failed handle is BLOCKED, not served",
                  "unknown handle 0xffffffff" in str(exc), str(exc))
        try:
            run_compare(b"", factory, b"SHORT", thunks=fake_thunks)
            check("synthetic: a unit code that is not 11 bytes is refused", False)
        except ValueError:
            check("synthetic: a unit code that is not 11 bytes is refused", True)
        partial = dict(list(fake_thunks.items())[:3])
        try:
            run_compare(b"", factory, b"QSD-000-000", thunks=partial)
            check("synthetic: an unresolved import thunk is BLOCKED", False)
        except Blocked as exc:
            check("synthetic: an unresolved import thunk is BLOCKED",
                  "not resolved" in str(exc), str(exc))
    except Exception as exc:  # noqa: BLE001
        check("synthetic run raised no exception", False, repr(exc))
    finally:
        module_layout = real_layout

    print("selftest: " + ("OK" if not failures else f"{failures} FAILED"))
    return 1 if failures else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("extract", help="read VER_INFO/HDD_INFO.TXT from a full card image")
    p.add_argument("card")
    p.add_argument("-o", "--out", required=True)
    p = sub.add_parser("run", help="run fn 0x03bd2ad8 (EU2011 build B) on one HDD_INFO.TXT")
    p.add_argument("image", help="IMG256 (first 256 MiB of the EU 2011 card)")
    p.add_argument("--card", help="HDD_INFO.TXT served at the guest path (omit: no file)")
    p.add_argument("--unit-from", help="factory HDD_INFO.TXT: unit code = its line-1 bytes 0..10")
    p.add_argument("--unit-code", help="unit code, 11 ASCII bytes (overrides --unit-from)")
    p.add_argument("--expect", choices=("ACCEPT", "REJECT"))
    p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "extract":
        return cmd_extract(args)
    if args.cmd == "run":
        return cmd_run(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
