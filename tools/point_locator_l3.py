#!/usr/bin/env python3
"""Run the firmware's POINT chain-locator path on a (relocated) pair in PySh4 (M4.52).

M4.47 found the chain locator in the file: directory cell ``0x82a`` -> the
field-dictionary record -> base reference ``u32 block address, u32 length``
at ``D+4`` (``D = C + 2*u16[C+2]`` = record ``+0x2e``).  This tool executes
the firmware code that reads it, from ``Navi.exe`` sec0 (no hand model of the
arithmetic):

1. **Header parser** ``fn 0x003f930c`` (EU2011) / ``fn 0x00421c3c`` (US2011)
   on the file's first 0x1000 bytes (native u16, as the read layer delivers
   them): it decodes the directory cells with ``0x0040f00c`` / ``0x00436f58``
   (block address -> 256-byte block number) into the header object; ``+24``
   is the dictionary record (cell ``0x82a``).
2. **Page loader** ``fn 0x003fe2d4`` (EU2011) / ``fn 0x00426480`` (US2011),
   called by the POINT handler ``0x003ffce0``: with the dictionary record in
   header-table entry ``+64`` (what ``0x003fc518`` loads for flag ``0x21``,
   type 1), the chain table and the page index, it decodes ``D+4`` with the
   same leaf, adds ``start_w >> 7`` blocks and issues the read request
   (``0x003f6c88``; slot ``+8`` sector, ``+12`` offset, ``+16`` length).
   The request is recorded and served from the decoded ``.DAT``.
3. **Record 1**: the requested bytes are inflated on the host (the
   firmware's completion-side inflate is not run; declared) and the
   firmware walker ``0x003f5194`` / ``0x0041db44`` returns record ``n``
   (0-based, as the walker counts; ``--n 1`` is the second record).

Hooks (each logged): ``memset`` and ``_divlu`` (COREDLL thunks, models), the
sector cache lookup (miss) and allocate (a host buffer), the debug log
``0x003ec9fc`` / ``0x0041551c`` (no-op, arguments kept), the read request
(served), and the header parser's tail call ``0x0040a8d0`` / ``0x004329d0``
(returns 0).  Declared inputs: the dictionary record placed in header-table
entry ``+64`` (step 1's block number), the chain table in memory (read through
its table reference), the page index ``req+48 = 6*page``, ``ctx+124 = 1``.

Verdicts: ``ACCEPT`` (request at ``base + 2*start_w`` of the chain the
table describes, length ``2*comp_w``, and record ``n`` equals the reference
record from an independent page walk), ``REJECT`` (the request lands
elsewhere, or the bytes do not inflate to the page), ``BLOCKED`` (engine
stop; exit 3).  A wrong ``--build`` for the image stops before the run
(literal-pool check, exit 1).  ``--stale OLD.cmp`` copies the old pair's 8-byte base reference into
this one (a relocated chain whose locator was not updated): the negative.

Usage::

  point_locator_l3.py --selftest
  point_locator_l3.py run IMG --cmp C [--build eu2011] [--page 1] [--n 1] [--stale OLD.cmp] [--json OUT]

Method and results: docs/experiments/EXP-2026-11-20-M4.52-point-locator-reader.md
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import zlib
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "l3_harness")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

#: Per-build VAs (EU2011 head ``92aa525d…``, US2011 head ``70d945d8…``);
#: ``pool`` pairs are checked against the image before a run.
BUILDS = {
    "eu2011": {
        "header": 0x003F930C, "loader": 0x003FE2D4, "decode": 0x0040F00C,
        "lookup": 0x0040EE4C, "memset": 0x003D13C4, "divlu": 0x003D140C,
        "cache": 0x00407724, "alloc": 0x004086B4, "log": 0x003EC9FC,
        "request": 0x003F6C88, "hdr_tail": 0x0040A8D0, "walker": 0x003F5194,
        "pool": ((0x003F9418, 0x0040F00C), (0x003FE5F4, 0x0040F00C),
                 (0x003FE5F0, 0x0040E9DC)),
    },
    "us2011": {
        "header": 0x00421C3C, "loader": 0x00426480, "decode": 0x00436F58,
        "lookup": 0x00436DD4, "memset": 0x0040089C, "divlu": 0x004008E4,
        "cache": 0x0042F824, "alloc": 0x004307B4, "log": 0x0041551C,
        "request": 0x0041F5E8, "hdr_tail": 0x004329D0, "walker": 0x0041DB44,
        "pool": ((0x004267A0, 0x00436F58),),
    },
}

HDR_BUF = 0x23000000
OBJ = 0x23010000
DICT = 0x23020000
TOC = 0x23100000
REQ = 0x23200000
OUT = 0x23300000
FAKE = 0x23400000
BUF = 0x23500000
BUF_SIZE = 0x40000
CTX_SEARCH = 124
HDR_DICT_SLOT = 64      # header-table entry field 0x0040e9dc returns for type 1, sel 0/0x21
OBJ_DICT = 24           # header object field the parser fills from cell 0x82a


# ---------------------------------------------------------------------------
# pure helpers (selftested)


def native(b: bytes) -> bytes:
    """File order (BE u16) -> the swapped copy the read layer delivers."""
    b = bytes(b) + (b"\0" if len(b) % 2 else b"")
    out = bytearray(len(b))
    out[0::2], out[1::2] = b[1::2], b[0::2]
    return bytes(out)


def decode_model(w0: int, w1: int) -> int:
    """Python reading of ``0x0040f00c`` (non-CD branch): 256-byte block number."""
    if w0 == 0xFFFF and w1 == 0xFFFF:
        return 0xFFFFFFFF
    return ((w0 << 11) | ((w1 >> 5) & 0x7F8) | (w1 & 7)) & 0xFFFFFFFF


def slot_request(words: list[int]) -> tuple[int, int, int]:
    """(file offset, length, destination) of a read slot (``0x003f6e40`` layout)."""
    return words[2] * 0x800 + words[3], words[4], words[1]


def judge(req, expect, rec, ref) -> str:
    if req is None:
        return "BLOCKED"
    if req[:2] != expect or rec is None or rec != ref:
        return "REJECT"
    return "ACCEPT"


# ---------------------------------------------------------------------------
# the run


def _u32(eng, va):
    return struct.unpack("<I", eng.read_mem(va, 4))[0]


def _put32(eng, va, v):
    eng.write_mem(va, struct.pack("<I", v & 0xFFFFFFFF))


def check_build(data: bytes, cfg: dict) -> None:
    import d53500_writer as dw
    mem = dw.sec0_mem(data)
    for pool, want in cfg["pool"]:
        if mem.u32(pool) != want:
            raise dw.Mismatch(f"pool {pool:#010x} holds {mem.u32(pool):#010x}, not {want:#010x}")


def table_of(blob: bytes, per_page: int = 1000):
    """The chain table through its table reference (independent of the base reference)."""
    import point_pair_regen as P
    _, pt = P.locator_positions(blob, per_page)
    addr, words, pp = struct.unpack_from(">IIH", blob, pt)
    toc = P.parse_toc(blob, P.blk_off(addr))
    if toc is None or toc.per_page != pp or toc.toc_size != 2 * words:
        raise SystemExit("table reference does not lead to a chain table")
    return toc


def reference_record(blob_ref: bytes, page: int, n: int):
    """Record *n* (0-based, as the walker counts) of page *page* of the name
    chain, by the M4.47 locator walk with every page verified (host side)."""
    import point_pair_regen as P
    chain = P.chain_via_locator(blob_ref, 1000)
    if chain is None:
        raise SystemExit("reference: the pair's own locator does not lead to the chain")
    _, _, inner = chain.pages[page]
    recs = P.walk_records(inner)
    o, size = recs[n]
    return inner[o:o + size], chain


def run(image: str, cmp: str, build: str, page: int, n: int, stale: str | None) -> dict:
    import d53500_writer as dw
    import point_pair_regen as P
    import point_walk_l3 as pw
    cfg = BUILDS[build]
    data = pw.load_image(image)
    check_build(data, cfg)
    orig, *_ = P.read_pair(Path(cmp))
    blob = bytearray(orig)
    pb, _ = P.locator_positions(bytes(blob), 1000)
    if stale:
        old, *_ = P.read_pair(Path(stale))
        opb, _ = P.locator_positions(old, 1000)
        blob[pb:pb + 8] = old[opb:opb + 8]
    blob = bytes(blob)
    toc = table_of(blob)
    res = {"cmp": cmp, "build": build, "page": page, "n": n, "stale": stale,
           "base_ref": blob[pb:pb + 8].hex()}

    eng = dw.new_engine(data)
    for name, va, size in (("hdr", HDR_BUF, 0x1000), ("obj", OBJ, 0x100), ("dict", DICT, 0x400),
                           ("toc", TOC, 0x10000), ("req", REQ, 0x100), ("out", OUT, 0x100),
                           ("fake", FAKE, 0x100), ("buf", BUF, BUF_SIZE)):
        eng.map(name, va, bytearray(size), "rw")
    eng.map("ctx", dw.CTX_VA, bytearray(0x200), "rw")
    log = {"memset": 0, "divlu": [], "cache": [], "alloc": [], "debug": [], "request": []}

    def memset(e, _va):
        d, v, k = e._get_reg("r4"), e._get_reg("r5") & 0xFF, e._get_reg("r6")
        e.write_mem(d, bytes([v]) * k)
        log["memset"] += 1
        return d

    def divlu(e, _va):
        a, b = e._get_reg("r4"), e._get_reg("r5")
        log["divlu"].append((a, b))
        return a // b if b else 0

    def cache(e, _va):
        log["cache"].append(e._get_reg("r4"))
        return 0                                   # miss

    def alloc(e, _va):
        b = e._get_reg("r4")
        _put32(e, FAKE + 20, BUF)
        _put32(e, FAKE + 24, min(_u32(e, b + 24), BUF_SIZE // 2))
        log["alloc"].append(b)
        return FAKE

    def debug(e, _va):
        log["debug"].append([e._get_reg(r) for r in ("r4", "r5", "r6", "r7")])
        return 0

    def request(e, _va):
        slot = e._get_reg("r4")
        words = [_u32(e, slot + 4 * i) for i in range(6)]
        off, length, dst = slot_request(words)
        log["request"].append((off, length))
        raw = blob[off:off + min(length, BUF_SIZE)]
        e.write_mem(dst, native(raw))
        return 0

    for key, fn in (("memset", memset), ("divlu", divlu), ("cache", cache), ("alloc", alloc),
                    ("log", debug), ("request", request)):
        eng.on_exec(cfg[key], fn)
    eng.on_exec(cfg["hdr_tail"], lambda _e, _va: 0)

    # 1. header parser on the native first 0x1000 bytes
    eng.write_mem(HDR_BUF, native(blob[:0x1000]))
    try:
        eng.call(cfg["header"], [0, 0, HDR_BUF, OBJ])
    except Exception as exc:  # noqa: BLE001
        res.update(verdict="BLOCKED", stop=f"header parser: {exc}"[:200])
        return res
    obj = [_u32(eng, OBJ + 4 * i) for i in range(19)]
    rec_block = obj[OBJ_DICT // 4]
    res["header_obj"] = [hex(x) for x in obj]
    res["dict_record"] = rec_block * 0x100
    res["dict_record_model"] = decode_model(*struct.unpack_from(">HH", blob, 0x82A)) * 0x100

    # 2. page loader with the record the parser named
    rec = rec_block * 0x100
    eng.write_mem(DICT, native(blob[rec:rec + 0x400]))
    hdr = eng.call(cfg["lookup"], [0, 0])
    _put32(eng, hdr + HDR_DICT_SLOT, DICT)
    eng.write_mem(TOC, native(blob[toc.toc + 4:toc.toc + toc.toc_size]))
    _put32(eng, dw.CTX_VA + CTX_SEARCH, 1)
    _put32(eng, REQ + 20, TOC)
    _put32(eng, REQ + 28, 0)
    _put32(eng, REQ + 48, 6 * page)
    try:
        r0 = eng.call(cfg["loader"], [dw.CTX_VA, REQ, OUT, 0])
    except Exception as exc:  # noqa: BLE001
        res.update(verdict="BLOCKED", stop=f"page loader: {exc}"[:200], log=str(log)[:400])
        return res
    res["loader_r0"] = r0
    res["requests"] = [(hex(o), hex(k)) for o, k in log["request"]]
    res["debug_log"] = [[hex(x) for x in d] for d in log["debug"]]
    res["divlu"] = log["divlu"]
    req = log["request"][-1] if log["request"] else None

    # reference: the chain the table describes, located by the M5.26 scan
    ref, chain = reference_record(orig, page, n)
    s, c, _ = toc.entries[page]
    expect = (chain.base + 2 * s, 2 * c)
    res["expected_request"] = (hex(expect[0]), hex(expect[1]))

    # 3. record n of the requested page, by the firmware walker
    got = None
    if req is not None:
        raw = blob[req[0]:req[0] + req[1]]
        try:
            inner = zlib.decompressobj().decompress(raw)
        except zlib.error as exc:
            res["inflate"] = f"fails: {exc}"
            inner = None
        if inner:
            off = dw.walker_reference(data, dw.BUILDS[build], native(inner), n)
            if off not in (None, 0):
                off -= dw.PAGE_VA
                size = 2 * (struct.unpack_from(">H", inner, off)[0] & 0x3FF)
                got = inner[off:off + size]
                res["record_offset"] = off
    res["record"] = None if got is None else got[:64].hex()
    res["verdict"] = judge(req, expect, got, ref)
    return res


def cmd_run(args) -> int:
    res = run(args.image, args.cmp, args.build, args.page, args.n, args.stale)
    for k in ("build", "page", "n", "stale", "base_ref", "dict_record", "dict_record_model",
              "loader_r0", "requests", "expected_request", "debug_log", "inflate",
              "record_offset", "stop"):
        if k in res:
            v = res[k]
            print(f"{k}: {hex(v) if isinstance(v, int) and k.startswith('dict') else v}")
    print("verdict:", res["verdict"])
    if args.json:
        Path(args.json).write_text(json.dumps(res, indent=1, default=str))
    return {"ACCEPT": 0, "REJECT": 1}.get(res["verdict"], 3)


def selftest() -> int:
    import point_pair_regen as P
    n = 0

    def ok(c, m):
        nonlocal n
        if not c:
            raise AssertionError(m)
        n += 1
    ok(native(b"\x12\x34\x56\x78") == b"\x34\x12\x78\x56", "native swap")
    ok(native(native(b"abcd")) == b"abcd", "swap is an involution")
    for off in (0x1000, 0x4200, 0x30B00, 0x6A7F00, 0x968600, 0x19C57200):
        a = P.blk_addr(off)
        ok(decode_model(a >> 16, a & 0xFFFF) * 0x100 == off, f"decode model = blk_off at {off:#x}")
    ok(decode_model(0xFFFF, 0xFFFF) == 0xFFFFFFFF, "empty cell")
    ok(decode_model(0, 0x0108) == (0x0108 >> 5 & 0x7F8) | 0, "block 8 is masked away (0x0040f00c & 7)")
    ok(slot_request([0, 0x23500000, 8, 0x200, 0x290, 0]) == (0x4200, 0x290, 0x23500000), "slot decode")
    ok(judge(None, (1, 2), None, None) == "BLOCKED", "no request is blocked")
    ok(judge((1, 2), (1, 2), b"x", b"x") == "ACCEPT", "accept")
    ok(judge((3, 2), (1, 2), b"x", b"x") == "REJECT", "wrong offset rejects")
    ok(judge((1, 2), (1, 2), None, b"x") == "REJECT", "no record rejects")
    for b, cfg in BUILDS.items():
        ok(len({cfg[k] for k in cfg if k != "pool"}) == len(cfg) - 1, f"{b}: distinct VAs")
    print(f"point_locator_l3 selftest: {n} checks OK")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("run", help="run header parser + page loader on one pair")
    p.add_argument("image")
    p.add_argument("--cmp", required=True)
    p.add_argument("--build", choices=sorted(BUILDS), default="eu2011")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--stale", help="old pair whose base reference is copied in (negative)")
    p.add_argument("--json")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "run":
        return cmd_run(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
