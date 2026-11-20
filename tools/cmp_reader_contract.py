#!/usr/bin/env python3
"""Check `.cmp`/`.ind` pairs and `CMP.LST` against the firmware's reader (M3.2b).

Every rule below is a check the EU2011 `Navi.exe` (build A, image start
``0x200200``) compressed-file layer performs, read with ``tools/sh4dis.py``;
the VAs are EU2011 and the method is in
``docs/experiments/EXP-2026-11-19-M3.2b-cmp-chunk-reader-walk-up.md``.

The layer's configuration is built once in ``fn 0x0041ba90`` (mount, after the
``\\CMP.LST`` open) and stored in the reader context:

* chunk size ``0x10000`` (``mov #1``/``shll16`` at ``0x0041bafe``) -> ctx
  ``+0x138``; also the size of the scratch inflate buffer at ctx ``+0x134``;
* compressed batch buffer ``0x14000`` (pool ``0x0041bbc8``) -> ctx ``+0x130``;
* at most 20 chunk entries per batch (``mov #20`` at ``0x0041baf4``) -> ctx
  ``+32``.

Rules (``R*`` firmware-enforced, ``D*`` derived from what the firmware reads):

R1  ``.ind`` word 3 (chunk size) == ``0x10000``: ``cmp/eq`` with ctx ``+0x138``
    at ``0x0041c92a`` (``fn 0x0041c8c4``) and ``0x0041c696`` (``fn 0x0041c5f0``);
    otherwise the read returns -1.
R2  every chunk's compressed length (``off[i+1]-off[i]``; the last one is
    ``.ind`` word 1 minus ``off[last]``) is at most ``0x14000``:
    ``fn 0x0041c5f0`` stops filling a batch when the running sum exceeds ctx
    ``+0x130`` (``0x0041c72a``); a single chunk above it gives an empty batch
    and ``fn 0x0041c990`` returns -1 (``0x0041c9da``).
R3  ``.ind`` word 1 (compressed size) == the ``.cmp`` file size: the last
    chunk's length is taken from it (``0x0041c6fc``-``0x0041c702``), and the batch read
    ``ops.read`` must return exactly the summed length (``0x0041ca3c``).
R4  the ``.ind`` holds ``16 + 4*count`` bytes: ``fn 0x0041c5f0`` reads
    ``chunk_offset[i]`` at ``ind + 16 + 4*i`` (``0x0041c6c6``) and
    ``fn 0x0041c524`` sizes the cached ``.IND`` as ``(count + 4) * 4``
    (``0x0041c576``..``0x0041c57a``).
D1  ``count == ceil(logical / 0x10000)`` and offsets strictly increase from 0:
    the firmware does not test these, but it computes each chunk's
    uncompressed offset as ``i * chunk`` (``0x0041c6b2``) and the last
    extent as ``logical % chunk`` (``_modls`` at ``0x0041c770``), so any other
    layout decodes to the wrong bytes.

``CMP.LST`` (``match``): ``fn 0x0041c2e0`` decides, for each path the open
wrapper ``fn 0x0041b780`` passes with its "compressed" flag set, whether the
path is served from ``NAME.CMP``/``NAME.IND`` (``fn 0x0041c524``) or opened
plainly.  The list is read whole (``fn 0x0041c124``: open, size, read, close
through the ops vtable).  Entries are separated by NUL bytes; an entry whose
last byte is ``\\`` matches when it equals the path's directory part (up to and
including the last ``\\``); any other entry must equal the whole path.  Only
``A``-``Z`` are folded to lower case; nothing else is normalised (a CR/LF
becomes part of the entry).

Usage::

  cmp_reader_contract.py check DIR [--sizes FILE]
  cmp_reader_contract.py match CMP.LST PATH [PATH ...]
  cmp_reader_contract.py --selftest

``check`` reads every ``*.ind`` in DIR (not recursive).  The ``.cmp`` size is
the sibling ``.cmp`` file's size, or a line ``NAME SIZE`` in ``--sizes``
(``NAME`` is the ``.cmp`` file name, the directory part is ignored).  Exit 0
all pass, 1 a rule failed, 2 bad input.  ``match`` prints ``compressed`` or
``plain`` per path; exit 0.
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
import tempfile
import zlib
from pathlib import Path

CHUNK = 0x10000      # ctx +0x138, fn 0x0041ba90 0x0041bafe (EU2011)
CBUF = 0x14000       # ctx +0x130, pool 0x0041bbc8 (EU2011)
BATCH = 20           # ctx +32, fn 0x0041ba90 0x0041baf4 (EU2011)

RULES = ("R1", "R2", "R3", "R4", "D1")


def check_pair(ind: bytes, cmp_size: int | None) -> dict[str, str | None]:
    """Return {rule: None if it passes, else a short reason}."""
    out: dict[str, str | None] = {r: None for r in RULES}
    if len(ind) < 16:
        for r in RULES:
            out[r] = "ind shorter than 16 B"
        return out
    logical, csize, count, chunk = struct.unpack_from("<4I", ind, 0)
    if chunk != CHUNK:
        out["R1"] = f"chunk {chunk:#x} != {CHUNK:#x}"
    if len(ind) < 16 + 4 * count:
        out["R4"] = f"ind {len(ind)} B < {16 + 4 * count}"
        out["R2"] = out["D1"] = "offsets missing"
    if cmp_size is None:
        out["R3"] = "no .cmp size"
    elif csize != cmp_size:
        out["R3"] = f"ind word1 {csize} != cmp {cmp_size}"
    if out["R4"]:
        return out
    offs = list(struct.unpack_from(f"<{count}I", ind, 16))
    lens = [(offs[i + 1] if i + 1 < count else csize) - offs[i] for i in range(count)]
    big = [i for i, n in enumerate(lens) if n > CBUF]
    if big:
        out["R2"] = f"{len(big)} chunk(s) > {CBUF:#x}, first #{big[0]} = {lens[big[0]]}"
    want = -(-logical // chunk) if chunk else -1
    if count != want:
        out["D1"] = f"count {count} != ceil(logical/chunk) {want}"
    elif count and (offs[0] != 0 or any(n <= 0 for n in lens)):
        out["D1"] = "offsets not strictly increasing from 0"
    return out


def max_chunk(ind: bytes) -> int:
    logical, csize, count, chunk = struct.unpack_from("<4I", ind, 0)
    offs = list(struct.unpack_from(f"<{count}I", ind, 16))
    return max(((offs[i + 1] if i + 1 < count else csize) - offs[i] for i in range(count)), default=0)


def cmp_lst_entries(lst: bytes) -> list[bytes]:
    return lst.split(b"\0")


def _fold(b: bytes) -> bytes:
    return bytes(c + 32 if 0x41 <= c <= 0x5A else c for c in b)


def cmp_lst_match(lst: bytes, path: bytes) -> bool:
    """Emulate fn 0x0041c2e0 (EU2011): True -> served from NAME.CMP/.IND."""
    cut = path.rfind(b"\\")
    for entry in cmp_lst_entries(lst):
        if not entry:
            continue
        if entry.endswith(b"\\"):
            if cut < 0:
                return False          # 0x0041c34e: no '\' in the path -> 0
            if _fold(entry) == _fold(path[: cut + 1]):
                return True
        elif _fold(entry) == _fold(path):
            return True
    return False


def load_sizes(path: Path | None) -> dict[str, int]:
    sizes: dict[str, int] = {}
    if path is None:
        return sizes
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        name = parts[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
        sizes[name] = int(parts[1])
    return sizes


def cmd_check(args: argparse.Namespace) -> int:
    d = Path(args.dir)
    if not d.is_dir():
        print(f"error: {d} is not a directory", file=sys.stderr)
        return 2
    sizes = load_sizes(Path(args.sizes) if args.sizes else None)
    inds = sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() == ".ind")
    if not inds:
        print(f"error: no .ind files in {d}", file=sys.stderr)
        return 2
    fails = {r: 0 for r in RULES}
    worst = (0, "")
    chunks = 0
    for p in inds:
        ind = p.read_bytes()
        cmp_name = p.name[:-4] + p.name[-4:].replace("ind", "cmp").replace("IND", "CMP")
        sib = p.with_name(cmp_name)
        size = sib.stat().st_size if sib.is_file() else sizes.get(cmp_name.lower())
        res = check_pair(ind, size)
        for r, why in res.items():
            if why:
                fails[r] += 1
                if args.verbose:
                    print(f"FAIL {r} {p.name}: {why}")
        if not res["R4"]:
            chunks += struct.unpack_from("<I", ind, 8)[0]
            m = max_chunk(ind)
            if m > worst[0]:
                worst = (m, p.name)
    print(f"pairs {len(inds)}  chunks {chunks}  largest compressed chunk {worst[0]} B "
          f"({worst[1]}) vs limit {CBUF}")
    for r in RULES:
        print(f"{r} pass {len(inds) - fails[r]} fail {fails[r]}")
    return 1 if any(fails.values()) else 0


def cmd_match(args: argparse.Namespace) -> int:
    lst = Path(args.cmp_lst).read_bytes()
    print(f"CMP.LST {len(lst)} B, {sum(1 for e in cmp_lst_entries(lst) if e)} entr(y/ies)")
    for p in args.paths:
        print(("compressed" if cmp_lst_match(lst, p.encode("latin-1")) else "plain") + "  " + p)
    return 0


def _pair(data: bytes, chunk: int = CHUNK, level: int = 6) -> tuple[bytes, bytes]:
    streams = [zlib.compress(data[i:i + chunk], level) for i in range(0, len(data), chunk)]
    offs, pos = [], 0
    for s in streams:
        offs.append(pos)
        pos += len(s)
    cmp = b"".join(streams)
    ind = struct.pack("<4I", len(data), len(cmp), len(streams), chunk) + struct.pack(f"<{len(offs)}I", *offs)
    return ind, cmp


def selftest() -> int:
    import random
    rnd = random.Random(7)
    data = bytes(rnd.getrandbits(8) for _ in range(3 * CHUNK + 1234))
    ind, cmp = _pair(data)
    ok = check_pair(ind, len(cmp))
    assert all(v is None for v in ok.values()), ok
    # level 0 (stored) is the worst case a writer can produce: still < CBUF
    ind0, cmp0 = _pair(data, level=0)
    assert all(v is None for v in check_pair(ind0, len(cmp0)).values())
    assert max_chunk(ind0) < CBUF, max_chunk(ind0)
    # R1: another chunk size
    ind8, cmp8 = _pair(data, chunk=0x8000)
    r = check_pair(ind8, len(cmp8))
    assert r["R1"] and not r["R3"], r
    # R3: .ind word 1 off by one
    bad = bytearray(ind)
    struct.pack_into("<I", bad, 4, len(cmp) + 1)
    assert check_pair(bytes(bad), len(cmp))["R3"]
    assert check_pair(ind, None)["R3"] == "no .cmp size"
    # R4: truncated offset table
    r = check_pair(ind[:-4], len(cmp))
    assert r["R4"] and r["R2"] and r["D1"], r
    # R2: one chunk longer than the batch buffer (offsets moved apart)
    big = bytearray(ind)
    struct.pack_into("<I", big, 16 + 4 * 1, CBUF + 100)
    struct.pack_into("<I", big, 16 + 4 * 2, CBUF + 200)
    struct.pack_into("<I", big, 16 + 4 * 3, CBUF + 300)
    struct.pack_into("<I", big, 4, CBUF + 400)
    r = check_pair(bytes(big), CBUF + 400)
    assert r["R2"] and r["R2"].startswith("1 chunk"), r
    # D1: count disagrees with logical size; offsets not increasing
    d1 = bytearray(ind)
    struct.pack_into("<I", d1, 0, 5 * CHUNK)
    assert check_pair(bytes(d1), len(cmp))["D1"]
    d2 = bytearray(ind)
    struct.pack_into("<I", d2, 20, 0)
    assert check_pair(bytes(d2), len(cmp))["D1"]
    # CMP.LST matcher (fn 0x0041c2e0 semantics)
    lst = b"\\SystemSD\\REFER001\\"
    assert cmp_lst_match(lst, b"\\SystemSD\\REFER001\\POINT010.DAT")
    assert cmp_lst_match(lst, b"\\systemsd\\refer001\\point010.dat")      # A-Z folded
    assert not cmp_lst_match(lst, b"\\SystemSD\\REFER001\\SUB\\X.DAT")    # one level only
    assert not cmp_lst_match(lst, b"\\SystemSD\\MMAIN001.DAT")
    assert not cmp_lst_match(lst + b"\r\n", b"\\SystemSD\\REFER001\\POINT010.DAT")
    two = b"\\SystemSD\\REFER002\\\0\\SystemSD\\X.DAT"
    assert cmp_lst_match(two, b"\\SystemSD\\x.dat")                      # exact entry
    assert cmp_lst_match(two, b"\\SystemSD\\REFER002\\A.DAT")
    assert not cmp_lst_match(two, b"\\SystemSD\\X.DAT2")
    # the CLI on a temp dir: good pair passes, sizes file is honoured
    with tempfile.TemporaryDirectory() as t:
        tp = Path(t)
        (tp / "A.DAT.ind").write_bytes(ind)
        (tp / "A.DAT.cmp").write_bytes(cmp)
        ns = argparse.Namespace(dir=t, sizes=None, verbose=False)
        assert cmd_check(ns) == 0
        (tp / "A.DAT.cmp").unlink()
        (tp / "sizes.txt").write_text(f"REFER001/A.DAT.cmp {len(cmp)}\n")
        assert cmd_check(argparse.Namespace(dir=t, sizes=str(tp / "sizes.txt"), verbose=False)) == 0
        (tp / "sizes.txt").write_text(f"REFER001/A.DAT.cmp {len(cmp) - 1}\n")
        assert cmd_check(argparse.Namespace(dir=t, sizes=str(tp / "sizes.txt"), verbose=False)) == 1
    print("selftest: OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("check", help="check every .ind in a directory")
    c.add_argument("dir")
    c.add_argument("--sizes", help="lines 'NAME SIZE' giving .cmp sizes")
    c.add_argument("--verbose", action="store_true")
    m = sub.add_parser("match", help="emulate the CMP.LST path match")
    m.add_argument("cmp_lst")
    m.add_argument("paths", nargs="+")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "check":
        return cmd_check(args)
    if args.cmd == "match":
        return cmd_match(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
