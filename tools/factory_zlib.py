#!/usr/bin/env python3
"""Check which deflate encoder reproduces the factory REFER001 page streams.

A ``REFER001`` POI ``.cmp`` decodes (via its ``.ind``) to a logical ``.DAT``
blob.  Inside that blob, name/record pages are zlib streams that start on a
0x100 boundary (``mutate_refer_poi.PAGE_ALIGN``).  This tool finds those
pages and recompresses each page's plain bytes with a chosen zlib build and
(level, memLevel, strategy).  A page is *reproduced* when the output equals
the factory bytes exactly.

The zlib build is loaded with ``ctypes`` from a shared library given by
``--libz LABEL=PATH``, so each release (1.1.3 ... 1.3.1) is named by its own
file and no Python extension has to be installed.  Without ``--libz`` the
system ``libz`` is used.  zlib-ng builds are flagged: they reproduce none of
the factory streams.

Usage:
  python3 tools/factory_zlib.py ROOT/REFER001 POINT001.DAT \\
      --libz 1.1.3=/path/libz.so.1.1.3 --libz 1.3.1=/path/libz.so.1.3.1
  python3 tools/factory_zlib.py ROOT/REFER001 POINT001.DAT --grid --libz 1.1.3=...
  python3 tools/factory_zlib.py --selftest

Exit codes: 0 every checked page reproduced and the negative control
differed; 1 at least one page did not reproduce; 3 nothing runnable (no
pages found); 2 usage error.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import hashlib
import json
import os
import random
import struct
import sys
import tempfile
import zlib
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mutate_refer_poi import PAGE_ALIGN, decode, read_ind  # noqa: E402

WINDOW = 1 << 20  # compressed-stream window for a page probe (pages are ~130 KB)
CHUNK = 0x10000  # .ind chunk_size
Z_FINISH = 4
Z_OK = 0
Z_STREAM_END = 1


class ZStream(ctypes.Structure):
    """``z_stream`` for LP64 Linux (zlib 1.1.x ... 1.3.x share this layout)."""

    _fields_ = [
        ("next_in", ctypes.c_void_p),
        ("avail_in", ctypes.c_uint),
        ("total_in", ctypes.c_ulong),
        ("next_out", ctypes.c_void_p),
        ("avail_out", ctypes.c_uint),
        ("total_out", ctypes.c_ulong),
        ("msg", ctypes.c_char_p),
        ("state", ctypes.c_void_p),
        ("zalloc", ctypes.c_void_p),
        ("zfree", ctypes.c_void_p),
        ("opaque", ctypes.c_void_p),
        ("data_type", ctypes.c_int),
        ("adler", ctypes.c_ulong),
        ("reserved", ctypes.c_ulong),
    ]


class PyZlib:
    """The zlib that the running Python links (``--libz LABEL=@python``)."""

    def __init__(self, label: str):
        self.label = label
        self.path = f"python {sys.version.split()[0]} zlib module"
        self.version = zlib.ZLIB_RUNTIME_VERSION
        self.is_ng = "ng" in self.version
        self.sha256 = None

    def deflate(self, data: bytes, level: int, mem: int, strat: int = 0) -> bytes:
        co = zlib.compressobj(level, zlib.DEFLATED, 15, mem, strat)
        return co.compress(data) + co.flush()


class Lib:
    """One zlib shared object, loaded through ctypes."""

    def __init__(self, label: str, path: str | None):
        self.label = label
        if path is None:
            path = ctypes.util.find_library("z") or "libz.so.1"
        self.path = path
        self.sha256 = hashlib.sha256(Path(path).read_bytes()).hexdigest() \
            if os.path.isabs(path) else None
        self.cdll = ctypes.CDLL(path)
        self.cdll.zlibVersion.restype = ctypes.c_char_p
        self.version = self.cdll.zlibVersion().decode()
        self.cdll.deflateInit2_.argtypes = [
            ctypes.POINTER(ZStream), ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
        ]
        self.is_ng = "ng" in self.version

    def deflate(self, data: bytes, level: int, mem: int, strat: int = 0) -> bytes:
        zs = ZStream()
        rc = self.cdll.deflateInit2_(
            ctypes.byref(zs), level, 8, 15, mem, strat,
            self.version.encode(), ctypes.sizeof(ZStream),
        )
        if rc != Z_OK:
            raise RuntimeError(f"deflateInit2_ rc={rc}")
        cap = len(data) + (len(data) >> 3) + 4096
        inbuf = ctypes.create_string_buffer(data, len(data))
        outbuf = ctypes.create_string_buffer(cap)
        zs.next_in = ctypes.cast(inbuf, ctypes.c_void_p)
        zs.avail_in = len(data)
        zs.next_out = ctypes.cast(outbuf, ctypes.c_void_p)
        zs.avail_out = cap
        rc = self.cdll.deflate(ctypes.byref(zs), Z_FINISH)
        n = zs.total_out
        self.cdll.deflateEnd(ctypes.byref(zs))
        if rc != Z_STREAM_END:
            raise RuntimeError(f"deflate rc={rc}")
        return outbuf.raw[:n]


def find_pages(blob: bytes):
    """Yield (offset, stream_length, plain) for every aligned zlib page."""
    mv = memoryview(blob)
    for off in range(0, len(blob) - 2, PAGE_ALIGN):
        b0, b1 = blob[off], blob[off + 1]
        if b0 & 0x0F != 8 or ((b0 << 8) | b1) % 31 != 0:
            continue
        window = mv[off:off + WINDOW]
        d = zlib.decompressobj()
        try:
            plain = d.decompress(window)
        except zlib.error:
            continue
        if not d.eof:
            continue
        clen = len(window) - len(d.unused_data)
        yield off, clen, plain


def first_diff(a: bytes, b: bytes) -> int:
    """Index of the first differing byte, -1 if equal, min length if one is a prefix."""
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return -1 if len(a) == len(b) else n


def negative_control(lib: Lib, plain: bytes, stream: bytes, level: int, mem: int) -> bool:
    """A one-byte change to the plain page must give a different stream."""
    pos = len(plain) // 2
    changed = plain[:pos] + bytes([plain[pos] ^ 0x01]) + plain[pos + 1:]
    return lib.deflate(changed, level, mem) != stream


def check_file(root: Path, name: str, libs: list, grid: bool, max_pages: int,
               sizes: bool = False):
    usize, csize, _count, _cs, offsets = read_ind(root / (name + ".ind"))
    cmp_bytes = (root / (name + ".cmp")).read_bytes()
    assert len(cmp_bytes) == csize, "cmp size disagrees with .ind"
    blob = decode(cmp_bytes, offsets)
    assert len(blob) == usize, "decoded size disagrees with .ind"
    pages = list(find_pages(blob))
    if max_pages:
        pages = pages[:max_pages]
    report = {"file": name, "pages": len(pages), "libs": {}}
    if not pages:
        return report
    off0, clen0, plain0 = pages[0]
    stream0 = blob[off0:off0 + clen0]
    params = [(lv, m, 0) for lv in range(10) for m in range(1, 10)] if grid else [(6, 8, 0)]

    for lib in libs:
        # with --grid, only parameter sets that reproduce page 0 go on to the rest
        survivors = [p for p in params if lib.deflate(plain0, *p) == stream0]
        report.setdefault("page0_survivors", {})[lib.label] = [
            f"L{lv}m{m}s{st}" for lv, m, st in survivors]
        best = None
        for (lv, m, st) in survivors:
            ok_offs = []
            diffs = []
            for off, clen, plain in pages:
                stream = blob[off:off + clen]
                out = lib.deflate(plain, lv, m, st)
                if out == stream:
                    ok_offs.append(hex(off))
                else:
                    diffs.append({"off": hex(off), "clen": clen, "out_len": len(out),
                                  "first_diff": first_diff(out, stream)})
            cand = {"level": lv, "memLevel": m, "strategy": st, "reproduced": len(ok_offs),
                    "of": len(pages), "reproduced_offsets": ok_offs, "mismatches": diffs[:20]}
            if best is None or cand["reproduced"] > best["reproduced"]:
                best = cand
        if best is None:
            # no parameter set reproduces page 0: report the stock L6/m8 byte difference
            out = lib.deflate(plain0, 6, 8, 0)
            best = {"level": None, "memLevel": None, "strategy": None, "reproduced": 0,
                    "of": len(pages), "reproduced_offsets": [], "mismatches": [],
                    "negative_control_differs": None,
                    "l6m8_page0": {"off": hex(off0), "factory_len": clen0, "out_len": len(out),
                                   "first_diff": first_diff(out, stream0)}}
        else:
            best["negative_control_differs"] = negative_control(
                lib, plain0, stream0, best["level"], best["memLevel"])
        report["libs"][lib.label] = {"version": lib.version, "path": lib.path,
                                     "sha256": lib.sha256, "ng": lib.is_ng, "best": best}
    if sizes:
        factory_total = sum(clen for _, clen, _ in pages)
        report["factory_bytes"] = factory_total
        report["sizes"] = {}
        for lib in libs:
            table = {}
            for lv in range(1, 10):
                table[lv] = sum(len(lib.deflate(plain, lv, 8, 0)) for _, _, plain in pages)
            report["sizes"][lib.label] = table
    return report


def parse_libs(specs: list[str] | None) -> list:
    if not specs:
        return [Lib("system", None)]
    libs = []
    for spec in specs:
        label, sep, path = spec.partition("=")
        if not sep or not label:
            raise SystemExit("--libz wants LABEL=PATH (empty PATH = system libz, "
                             f"@python = the running Python's zlib), got {spec!r}")
        if path == "@python":
            libs.append(PyZlib(label))
        else:
            libs.append(Lib(label, path or None))
    return libs


def selftest() -> int:
    checks = 0
    rng = random.Random(0x1013)
    words = [bytes(rng.randrange(97, 123) for _ in range(rng.randrange(3, 9)))
             for _ in range(400)]
    plain1 = b" ".join(rng.choice(words) for _ in range(9000))
    plain2 = b"".join(rng.choice(words) for _ in range(2000))
    lib = Lib("system", None)
    s1 = lib.deflate(plain1, 6, 8)
    s2 = lib.deflate(plain2, 6, 8)

    def pad(b: bytes) -> bytes:
        return b + bytes(-len(b) % PAGE_ALIGN)

    # 1. page discovery: two aligned pages separated by zero padding
    off2 = len(pad(s1))
    blob = pad(s1) + pad(s2) + bytes(PAGE_ALIGN)
    found = {off: (clen, plain) for off, clen, plain in find_pages(blob)}
    assert 0 in found and found[0][0] == len(s1), "page 0 not found"
    assert found[0][1] == plain1, "page 0 plain mismatch"
    assert off2 in found and found[off2][0] == len(s2), "page 2 not found"
    checks += 3

    # 2. ctypes deflate round-trips through the stock decompressor
    for lv in (0, 1, 6, 9):
        for m in (1, 8, 9):
            assert zlib.decompress(lib.deflate(plain1, lv, m)) == plain1, f"L{lv} m{m}"
            checks += 1

    # 3. negative control: a changed byte gives a different stream, and a
    #    different page never matches another page's stream
    assert negative_control(lib, plain1, s1, 6, 8), "one changed byte did not differ"
    assert negative_control(lib, plain2, s1, 6, 8), "page 2 against page 1 stream did not differ"
    checks += 2

    # 4. first_diff
    assert first_diff(b"abcd", b"abXd") == 2
    assert first_diff(b"abc", b"abc") == -1
    assert first_diff(b"ab", b"abc") == 2
    checks += 3

    # 5. end to end on a synthetic .cmp/.ind pair: the decoded blob holds the
    #    page at offset 0, check_file must reproduce it and see the control
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        blob_plain = pad(s1) + bytes(CHUNK)
        blob_plain = blob_plain[:CHUNK]
        cmp_bytes = lib.deflate(blob_plain, 6, 8)
        ind = struct.pack("<IIII", len(blob_plain), len(cmp_bytes), 1, CHUNK)
        ind += struct.pack("<I", 0)
        (root / "SYN.DAT.cmp").write_bytes(cmp_bytes)
        (root / "SYN.DAT.ind").write_bytes(ind)
        rep = check_file(root, "SYN.DAT", [lib], grid=False, max_pages=0)
        best = rep["libs"]["system"]["best"]
        assert rep["pages"] == 1, f"expected 1 page, got {rep['pages']}"
        assert best["reproduced"] == 1, "synthetic page not reproduced"
        assert best["negative_control_differs"] is True, "negative control did not differ"
        checks += 3

    # 6. the Python-zlib candidate round-trips, and zlib-ng is flagged
    py = PyZlib("py")
    assert zlib.decompress(py.deflate(plain1, 6, 8)) == plain1, "PyZlib round trip"
    checks += 1
    ng = Lib.__new__(Lib)
    ng.version = "1.3.1.zlib-ng"
    ng.is_ng = "ng" in ng.version
    assert ng.is_ng
    checks += 1

    print(f"factory_zlib selftest: {checks} checks OK")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("root", nargs="?", help="directory holding POINT*.DAT.cmp/.ind")
    ap.add_argument("names", nargs="*", help="e.g. POINT001.DAT")
    ap.add_argument("--libz", action="append", metavar="LABEL=PATH",
                    help="zlib shared object to test (repeatable); default system libz")
    ap.add_argument("--grid", action="store_true",
                    help="try levels 0-9 x memLevel 1-9 on page 0, then the rest")
    ap.add_argument("--max-pages", type=int, default=0, help="0 = all pages")
    ap.add_argument("--sizes", action="store_true",
                    help="total compressed bytes per candidate at levels 1-9, memLevel 8, "
                         "against the factory total")
    ap.add_argument("--json", metavar="PATH", help="write the report as JSON")
    ap.add_argument("--selftest", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.root or not args.names:
        ap.error("need ROOT and at least one POINT*.DAT name")
    libs = parse_libs(args.libz)
    reports = []
    for name in args.names:
        rep = check_file(Path(args.root), name, libs, args.grid, args.max_pages, args.sizes)
        reports.append(rep)
        print(f"{name}: {rep['pages']} page(s)")
        for label, info in rep["libs"].items():
            b = info["best"]
            flag = " (zlib-ng: not stock)" if info["ng"] else ""
            print(f"  {label} zlib {info['version']}{flag}: L{b['level']} m{b['memLevel']} "
                  f"reproduced {b['reproduced']}/{b['of']}; "
                  f"negative control differs: {b['negative_control_differs']}")
        if args.sizes and rep["pages"]:
            print(f"  factory total {rep['factory_bytes']} bytes")
            for label, table in rep["sizes"].items():
                cells = " ".join(f"L{lv}:{n - rep['factory_bytes']:+d}" for lv, n in table.items())
                print(f"  {label} minus factory, m8: {cells}")
    if args.json:
        Path(args.json).write_text(json.dumps(reports, indent=1))
    if not any(r["pages"] for r in reports):
        return 3
    # exit 0 when some candidate reproduces every page with a differing control
    ok = any(i["best"]["reproduced"] == r["pages"] and i["best"]["negative_control_differs"]
             for r in reports if r["pages"] for i in r["libs"].values())
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
