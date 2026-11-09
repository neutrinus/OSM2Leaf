#!/usr/bin/env python3
"""Run Navi.exe's chunked ``.cmp`` reader ``fn 0x0041c7e8`` on a real pair (M9.11).

``fn 0x41c7e8(ctx, &offset, length, count)`` walks ``count`` 20-byte
entries, starting at the one ``*(ctx + 28)`` points to: the caller passes the
first chunk of the requested range.  Each entry is ``+4`` compressed length,
``+8`` uncompressed offset of the chunk, ``+12`` uncompressed extent,
``+16`` pointer to the chunk's zlib stream.  For every entry that overlaps the
requested logical range it calls the one-shot inflate wrapper ``0x542148``
(zlib 1.1.3 ``inflateInit2_``/``inflate``/``inflateEnd`` in Navi.exe sec0) and
copies the slice with ``memcpy``.  Its destination is the caller-frame slot
``sp + 72`` after the function's own 32-byte frame (``S + 40`` at entry, read
at ``0x41c802``), which this tool writes.  It returns the number of bytes
copied, or ``-1`` when the inflate wrapper fails.

Only the code is taken from the image (``cerom.py`` module/section lookup, no
fitted deltas).  The imports the code calls are host stubs, each named here
with its evidence:

* ``0x003d146c`` = ``COREDLL #1044``, ``memcpy(dst, src, n)`` (M2.16 inference;
  the output compare checks it).
* ``0x003d1484`` = ``COREDLL #2006``, taken as ``r4 % r5``.  The first call is
  zlib's header check ``((CMF<<8)+FLG) % 31`` (``mov #31,r5`` before the call at
  ``0x5423e8``, dividend ``0x789c`` on the real stream).  Later calls in the
  same run use other divisors; their results are not verified (see EXP).
* ``0x00543a98`` = zlib ``zcalloc`` trampoline, ``calloc(items=r5, size=r6)``.
* ``0x00543aa8`` = zlib ``zcfree`` trampoline, ``free(ptr=r5)``.

The trampolines jump through IAT slots in compressed sec1, so the loader's
values are not in the file; the hooks replace the trampolines, not the zlib
code.

The reference is ``cmpind.decode`` (stock zlib, one stream per chunk).  Exit
codes: 0 PASS (the firmware output is byte-identical, or for
``--mutate corrupt-ind`` the firmware returns -1), 1 FAIL (disagreement),
3 image or input missing, 4 BLOCKED (the engine stopped on a firmware access
the harness cannot map; the VA and its section are named).  A blocked run is a
result, never a pass.

Usage::

  chunk_decoder_l3.py --selftest
  chunk_decoder_l3.py run IMG --cmp POINT010.DAT.cmp --ind POINT010.DAT.ind \
      [--offset 0x840ba0] [--length 42848] [--mutate none|swap-4-8|corrupt-ind]

Method and results: docs/experiments/EXP-2026-11-08-M9.11-chunk-decoder.md
"""

from __future__ import annotations

import argparse
import os
import re
import struct
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "l3_harness"))

import cerom  # noqa: E402
import cmpind  # noqa: E402
import point_walk_l3 as pw  # noqa: E402
from engine import EngineError, PySh4, StubReturn  # noqa: E402

IMAGE_START = 0x200200
MODULE = "Navi.exe"
FN_CHUNK = 0x0041C7E8
STUB_MEMCPY = 0x003D146C      # COREDLL #1044
STUB_MOD31 = 0x003D1484       # COREDLL #2006 (r4 % r5)
ZCALLOC = 0x00543A98          # zlib zcalloc trampoline
ZCFREE = 0x00543AA8           # zlib zcfree trampoline
ENTRY = 20
ENTRY_TABLE_PTR = 28          # *(ctx + 28) = table base
CACHE_PTR = 308               # *(ctx + 308) = scratch buffer for partial chunks
DST_SLOT = 40                 # caller-frame slot read as the destination (S + 40)
MINUS_ONE = 0xFFFFFFFF

CMP_VA = 0x20000000
STK_VA = 0x30000000
STK_SIZE = 0x10000
ARG_VA = STK_VA + 0x100
CTX_VA = 0x40000000
TAB_VA = 0x40001000
OUT_VA = 0x50000000
CACHE_VA = 0x60000000
HEAP_VA = 0x70000000
HEAP_SIZE = 0x800000
MAX_EXTENT = 0x10000
INFLATE_MASK_VA = 0x00574DE0  # the table inflate indexes at 0x54369e (sec1)

MUTATIONS = ("none", "swap-4-8", "corrupt-ind")


class Blocked(Exception):
    """The firmware touched memory the harness does not map."""


# ---------------------------------------------------------------------------
# table and reference


def table_rows(usize: int, csize: int, offsets, chunk_size: int, cmp_va: int = CMP_VA):
    """The 20-byte entries the firmware reads, one per ``.ind`` chunk."""
    count = len(offsets)
    rows = []
    for i, start in enumerate(offsets):
        end = offsets[i + 1] if i + 1 < count else csize
        off = i * chunk_size
        ext = min(chunk_size, usize - off)
        rows.append([0, end - start, off, ext, cmp_va + start])
    return rows


def pack_rows(rows) -> bytes:
    return b"".join(struct.pack("<5I", *row) for row in rows)


def mutate_rows(rows, kind: str, index: int) -> None:
    """``swap-4-8``: exchange the ``+4`` and ``+8`` fields of chunk *index*."""
    if kind == "swap-4-8":
        rows[index][1], rows[index][2] = rows[index][2], rows[index][1]


def mutate_offsets(offsets, kind: str, index: int):
    """``corrupt-ind``: move chunk *index*'s compressed start by three bytes."""
    if kind == "corrupt-ind":
        out = list(offsets)
        out[index] += 3
        return out
    return list(offsets)


def chunk_index(offset: int, chunk_size: int) -> int:
    return offset // chunk_size


def reference_slice(cmp_path: Path, ind_path: Path, offset: int, length: int) -> bytes:
    blob, _ = cmpind.decode(cmp_path, ind_path)
    return blob[offset:offset + length]


# ---------------------------------------------------------------------------
# firmware run


def section_of(sections, va: int) -> str:
    for sec, comp, _ in sections:
        base = sec["realaddr"]
        if base <= va < base + sec["vsize"]:
            return "sec@%08x %s" % (base, "COMPRESSED" if comp else "plain")
    return "outside every Navi.exe section"


def run_firmware(image: bytes, cmp_bytes: bytes, rows, offset: int, length: int,
                 chunk_size: int, sec_mode: str = "block", sec1_table=None):
    """Run fn 0x41c7e8 on the chunks covering [offset, offset+length).

    The loop starts at the table entry that ``*(ctx+28)`` points to and walks
    ``count`` entries, so the caller passes the first chunk of the range and
    the number of chunks it spans.  Returns (r0, output bytes, stats).

    ``sec1_table`` (M9.11b) is an explicit declared input: ``{"va": int,
    "values": [int, ...]}`` written into the mapped compressed sec1 when
    ``sec_mode`` is ``"zero-mask"``.  If omitted, ``zero-mask`` writes the
    zlib 1.1.3 ``inflate_mask[17]`` at ``INFLATE_MASK_VA`` (public source,
    provenance recorded in EXP-2026-11-08-M9.11-chunk-decoder); callers that
    register a passing target through ``runner.py`` must pass it explicitly.
    """
    start = chunk_index(offset, chunk_size)
    count = chunk_index(offset + length - 1, chunk_size) - start + 1
    text_va, text = pw.navi_text(image, IMAGE_START)
    eng = PySh4(endian="little")
    eng.map("text", text_va, text, "rx")
    eng.map("cmp", CMP_VA, bytearray(cmp_bytes) + bytearray(0x1000), "rw")
    table = pack_rows(rows)
    eng.map("tab", TAB_VA, bytearray(table) + bytearray(0x1000), "rw")
    eng.map("ctx", CTX_VA, bytearray(0x1000), "rw")
    eng.map("out", OUT_VA, bytearray(length + MAX_EXTENT), "rw")
    eng.map("cache", CACHE_VA, bytearray(MAX_EXTENT * 2), "rw")
    eng.map("heap", HEAP_VA, bytearray(HEAP_SIZE), "rw")
    eng.map("stack", STK_VA, bytearray(STK_SIZE), "rw")
    comp_ranges = []
    if sec_mode in ("zero", "zero-mask"):
        # Diagnostic: the compressed sections are mapped as zero-filled RW so
        # the run continues, and every read that lands in them is logged.
        _, secs = pw.module_sections(image, IMAGE_START, MODULE)
        for sec, comp, _ in secs:
            if comp:
                name = "sec@%08x" % sec["realaddr"]
                eng.map(name, sec["realaddr"], bytearray(sec["vsize"]), "rw")
                comp_ranges.append((sec["realaddr"], sec["realaddr"] + sec["vsize"]))
        if sec_mode == "zero-mask":
            if sec1_table is not None:
                tva = int(str(sec1_table["va"]), 0) & 0xFFFFFFFF
                vals = sec1_table["values"]
                mask = b"".join(struct.pack("<I", int(str(v), 0) & 0xFFFFFFFF) for v in vals)
                eng.write_mem(tva, mask)
            else:
                # zlib 1.1.3 inflate_mask[17] (public source: 2^n - 1), written at
                # the table inflate indexes at 0x54369e.  Not read from the image.
                mask = b"".join(struct.pack("<I", (1 << n) - 1) for n in range(17))
                eng.write_mem(INFLATE_MASK_VA, mask)
    stack_top = STK_VA + STK_SIZE // 2
    eng.write_mem(CTX_VA + ENTRY_TABLE_PTR, struct.pack("<I", TAB_VA + ENTRY * start))
    eng.write_mem(CTX_VA + CACHE_PTR, struct.pack("<I", CACHE_VA))
    eng.write_mem(ARG_VA, struct.pack("<I", offset))
    eng.write_mem(stack_top + DST_SLOT, struct.pack("<I", OUT_VA))
    eng.set_regs(r15=stack_top)

    stats = {"insns": 0, "memcpy": 0, "mod": [], "calloc": 0, "free": 0,
             "last_pc": None, "sec_reads": {}}
    orig_load = eng._load

    def logged_load(va, size):
        for lo, hi in comp_ranges:
            if lo <= va < hi:
                key = (va, size)
                stats["sec_reads"][key] = stats["sec_reads"].get(key, 0) + 1
                break
        return orig_load(va, size)

    eng._load = logged_load
    orig_execute = eng._execute

    def counted(insn, pc):
        stats["insns"] += 1
        stats["last_pc"] = pc
        return orig_execute(insn, pc)

    eng._execute = counted

    heap = {"next": HEAP_VA}

    def memcpy_stub(e, va):
        dst, src, n = e._get_reg("r4"), e._get_reg("r5"), e._get_reg("r6")
        stats["memcpy"] += 1
        if n:  # a zero-length copy is legal C and leaves memory alone
            e.write_mem(dst, e.read_mem(src, n))
        return StubReturn(dst)

    def mod31_stub(e, va):
        dividend, divisor = e._get_reg("r4"), e._get_reg("r5")
        stats["mod"].append((dividend, divisor))
        return StubReturn(dividend % divisor)

    def calloc_stub(e, va):
        items, size = e._get_reg("r5"), e._get_reg("r6")
        pointer = heap["next"]
        heap["next"] += (items * size + 15) & ~15
        if heap["next"] > HEAP_VA + HEAP_SIZE:
            raise Blocked("calloc: harness heap exhausted")
        stats["calloc"] += 1
        return StubReturn(pointer)

    def free_stub(e, va):
        stats["free"] += 1
        return StubReturn(0)

    eng.on_exec(STUB_MEMCPY, memcpy_stub)
    eng.on_exec(STUB_MOD31, mod31_stub)
    eng.on_exec(ZCALLOC, calloc_stub)
    eng.on_exec(ZCFREE, free_stub)
    try:
        ret = eng.call(FN_CHUNK, [CTX_VA, ARG_VA, length, count])
    except EngineError as exc:
        match = re.search(r"covers (0x[0-9a-f]+)", str(exc))
        va = int(match.group(1), 16) if match else None
        raise Blocked(str(exc), va, stats) from exc
    out = bytes(eng.read_mem(OUT_VA, length))
    return ret, out, stats


# ---------------------------------------------------------------------------
# commands


def print_reads(stats) -> None:
    """Print the logged reads into the compressed sections (diagnostic mode)."""
    if not stats.get("sec_reads"):
        return
    reads = sorted(stats["sec_reads"].items())
    print(f"compressed-section reads: {len(reads)} distinct (va, size)")
    for (va, size), hits in reads[:80]:
        print(f"  {va:#010x} size {size} x{hits}")


def cmd_run(args) -> int:
    image_path = Path(args.image)
    cmp_path, ind_path = Path(args.cmp), Path(args.ind)
    for path in (image_path, cmp_path, ind_path):
        if not path.exists():
            print(f"missing input: {path}", file=sys.stderr)
            return 3
    usize, csize, count, chunk_size, offsets = cmpind.read_index(ind_path)
    image = pw.load_image(str(image_path))
    _, secs = pw.module_sections(image, IMAGE_START, MODULE)

    index = chunk_index(args.offset, chunk_size)
    offsets = mutate_offsets(offsets, args.mutate, index)
    rows = table_rows(usize, csize, offsets, chunk_size)
    if args.mutate == "swap-4-8":
        mutate_rows(rows, args.mutate, index)
    cmp_bytes = cmp_path.read_bytes()
    try:
        ret, out, stats = run_firmware(image, cmp_bytes, rows, args.offset,
                                       args.length, chunk_size, args.sec1)
    except Blocked as exc:
        args = exc.args
        va = args[1] if len(args) > 1 else None
        where = section_of(secs, va) if va is not None else "no VA given"
        print("BLOCKED: " + str(args[0]))
        print(f"  firmware access lies in {where} of {MODULE}")
        if len(args) > 2:
            stats = args[2]
            print(f"  before the stop: insns={stats['insns']} "
                  f"mod-calls={len(stats['mod'])} memcpy={stats['memcpy']} "
                  f"calloc={stats['calloc']} free={stats['free']} "
                  f"last_pc={stats['last_pc']:#010x}")
            print_reads(stats)
        return 4

    print_reads(stats)
    print(f"firmware: r0={ret if ret != MINUS_ONE else -1} copied={args.length} "
          f"insns={stats['insns']} memcpy={stats['memcpy']} "
          f"calloc={stats['calloc']} free={stats['free']} "
          f"mod-calls={len(stats['mod'])} divisors="
          f"{sorted({hex(d) for _, d in stats['mod']})}")
    if args.mutate == "corrupt-ind":
        ok = ret == MINUS_ONE
        print("verdict:", "PASS (firmware rejects the corrupt .ind)" if ok else
              "FAIL (firmware accepted the corrupt .ind)")
        return 0 if ok else 1
    try:
        expected = reference_slice(cmp_path, ind_path, args.offset, args.length)
    except cmpind.FormatError as exc:
        print("reference rejects the input:", exc)
        return 1
    ok = ret == args.length and out == expected
    if args.mutate == "swap-4-8":
        # Control: a wrong +4/+8 field must fail, cleanly (no engine exception).
        clean_fail = not ok
        print("verdict:", "PASS (control: swapped +4/+8 fails cleanly, no exception)"
              if clean_fail else "FAIL (swapped +4/+8 still returns the page)")
        return 0 if clean_fail else 1
    print("verdict:", "PASS (byte-identical to cmpind.decode)" if ok else
          f"FAIL (ret={ret}, first differing byte "
          f"{next((i for i, (a, b) in enumerate(zip(out, expected)) if a != b), -1)})")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# self-test (no vendor data)


def selftest() -> int:
    import tempfile
    import zlib

    failures = []

    def check(name: str, cond: bool) -> None:
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            failures.append(name)

    # table fields for a 40-byte stream in 16-byte chunks, offsets 0,10,25, csize 33
    rows = table_rows(40, 33, [0, 10, 25], 16, cmp_va=0x1000)
    check("table: chunk 0 = (+4 csize, +8 off, +12 ext, +16 ptr)",
          rows[0] == [0, 10, 0, 16, 0x1000])
    check("table: chunk 1 compressed length = 25 - 10",
          rows[1] == [0, 15, 16, 16, 0x100A])
    check("table: last chunk ends at csize, extent = usize - off",
          rows[2] == [0, 8, 32, 8, 0x1019])
    check("table: packed row is 20 bytes", len(pack_rows(rows)) == 60)

    swapped = [list(r) for r in rows]
    mutate_rows(swapped, "swap-4-8", 1)
    check("mutate swap-4-8 exchanges +4 and +8 of one chunk",
          swapped[1][1] == 16 and swapped[1][2] == 15 and swapped[0] == rows[0])
    check("mutate none leaves the offsets alone",
          mutate_offsets([0, 10, 25], "none", 1) == [0, 10, 25])
    check("mutate corrupt-ind moves one chunk start by 3",
          mutate_offsets([0, 10, 25], "corrupt-ind", 1) == [0, 13, 25])
    check("chunk index of offset 0x840ba0 with 64 KiB chunks is 132",
          chunk_index(0x840BA0, 0x10000) == 132)

    # the reference rejects a corrupt .ind; the firmware is expected to as well
    with tempfile.TemporaryDirectory(prefix="chunk-selftest-") as tmp:
        base = Path(tmp)
        # cmpind requires every chunk but the last to be exactly 64 KiB
        chunks = [b"A" * 0x10000, bytes(i * 31 & 0xFF for i in range(0x10000)),
                  b"z" * 300]
        streams = [zlib.compress(c, 6) for c in chunks]
        cmp_bytes = b"".join(streams)
        offsets, pos = [], 0
        for s in streams:
            offsets.append(pos)
            pos += len(s)
        usize = sum(len(c) for c in chunks)
        ind = struct.pack("<IIII", usize, len(cmp_bytes), len(offsets), 0x10000)
        ind += struct.pack(f"<{len(offsets)}I", *offsets)
        (base / "x.cmp").write_bytes(cmp_bytes)
        (base / "x.ind").write_bytes(ind)
        blob, _ = cmpind.decode(base / "x.cmp", base / "x.ind")
        check("reference: synthetic pair decodes to the three chunks",
              blob == b"".join(chunks))
        check("reference slice matches the logical bytes",
              reference_slice(base / "x.cmp", base / "x.ind", 100, 50) == blob[100:150])
        bad = mutate_offsets(offsets, "corrupt-ind", 1)
        ind_bad = struct.pack("<IIII", usize, len(cmp_bytes), len(bad), 0x10000)
        ind_bad += struct.pack(f"<{len(bad)}I", *bad)
        (base / "bad.ind").write_bytes(ind_bad)
        (base / "bad.cmp").write_bytes(cmp_bytes)
        try:
            cmpind.decode(base / "bad.cmp", base / "bad.ind")
            rejected = False
        except (cmpind.FormatError, zlib.error):
            rejected = True
        check("reference rejects the corrupt .ind (positive control for PASS)", rejected)

    # the table rows the firmware reads for the synthetic pair match its .ind
    rows2 = table_rows(usize, len(cmp_bytes), offsets, 0x10000, cmp_va=0x2000)
    check("table for the synthetic pair: last entry ends at the .cmp size",
          rows2[-1][1] == len(cmp_bytes) - offsets[-1])

    print("selftest:", "OK" if not failures else f"FAIL ({len(failures)})")
    return 0 if not failures else 1


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    run = sub.add_parser("run", help="run fn 0x41c7e8 on one .cmp/.ind pair")
    run.add_argument("image")
    run.add_argument("--cmp", required=True)
    run.add_argument("--ind", required=True)
    run.add_argument("--offset", type=lambda s: int(s, 0), default=0x840BA0)
    run.add_argument("--length", type=lambda s: int(s, 0), default=42848)
    run.add_argument("--mutate", choices=MUTATIONS, default="none")
    run.add_argument("--sec1", choices=("block", "zero", "zero-mask"), default="block",
                     help="block: a compressed-section access stops the run (default); "
                          "zero: diagnostic, map compressed sections as zeros and log reads; "
                          "zero-mask: as zero, plus zlib's public inflate_mask[17] at 0x574de0")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "run":
        return cmd_run(args)
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
