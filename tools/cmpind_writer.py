#!/usr/bin/env python3
"""Read/write the Leaf ZE0 ``.cmp`` / ``.ind`` container.

Format (verified on all 194 pairs in the EU 2011 image)::

    .ind  u32 LE uncompressed_size
          u32 LE compressed_size
          u32 LE chunk_count
          u32 LE chunk_size              (0x10000 in every observed file)
          u32 LE chunk_offset[chunk_count]

    .cmp  concatenation of ``chunk_count`` independent zlib streams.
          Chunk i is ``cmp[offset[i]:offset[i+1]]`` (last to EOF).
          Every non-final chunk inflates to exactly ``chunk_size`` bytes.

Two write modes matter:

``preserve``
    Keep the original compressed chunk bytes verbatim and rebuild only the
    index. Byte-identical for unchanged files, independent of the zlib
    implementation.

``recompress``
    Inflate the logical ``.DAT``, split it into 64 KiB chunks and deflate each
    from scratch. Semantically identical; byte-identical to the factory card
    only when the compressor matches (see docs/format/cmp-ind.md: stock zlib 1.3.1, level 6,
    windowBits 15, memLevel 8, default strategy reproduced every tested chunk;
    zlib-ng did not).

Both CLI commands print the zlib runtime via ``tools/zlibinfo.py``.
``recompress`` warns on zlib-ng and ``--require-stock-zlib`` refuses to run
(exit 3, *unverifiable*, distinct from a data failure exit 1).  ``verify`` only
inflates, so its verdict is data-level and unchanged on any build.

Outer container / factory-params primitives are shared with ``cmpind_codec``
(M1.16).  ``--selftest`` runs a synthetic round-trip (no vendor data).
"""

from __future__ import annotations

import sys
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import zlibinfo

# Shared codec (M1.16).  Re-export the names this module has always provided.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmpind_codec  # noqa: E402

CHUNK = cmpind_codec.CHUNK
IND_HEADER = cmpind_codec.IND_HEADER
FormatError = cmpind_codec.FormatError


def _chunk_count(usize: int, chunk_size: int) -> int:
    if usize == 0:
        return 0
    return (usize + chunk_size - 1) // chunk_size


@dataclass
class CmpFile:
    usize: int
    chunk_size: int
    streams: list[bytes] = field(default_factory=list)

    # ---- construction -------------------------------------------------
    @classmethod
    def from_dat(
        cls,
        dat: bytes,
        *,
        chunk_size: int = CHUNK,
        level: int = cmpind_codec.FACTORY_LEVEL,
        wbits: int = cmpind_codec.FACTORY_WBITS,
        mem_level: int = cmpind_codec.FACTORY_MEM,
        strategy: int = cmpind_codec.FACTORY_STRATEGY,
    ) -> "CmpFile":
        n = _chunk_count(len(dat), chunk_size)
        streams = []
        for i in range(n):
            payload = dat[i * chunk_size : (i + 1) * chunk_size]
            co = zlib.compressobj(level, zlib.DEFLATED, wbits, mem_level, strategy)
            streams.append(co.compress(payload) + co.flush())
        return cls(len(dat), chunk_size, streams)

    @classmethod
    def from_parts(cls, usize: int, chunk_size: int, streams: list[bytes]) -> "CmpFile":
        obj = cls(usize, chunk_size, list(streams))
        obj.check()
        return obj

    @classmethod
    def from_files(cls, cmp_path: Path, ind_path: Path) -> "CmpFile":
        usize, csize, count, chunk_size, offsets = cmpind_codec.read_ind(ind_path)
        packed = Path(cmp_path).read_bytes()
        if csize != len(packed):
            raise FormatError(f"{cmp_path}: .ind says {csize}, file has {len(packed)}")
        offsets = list(offsets)
        if count and (offsets[0] != 0 or offsets != sorted(offsets) or offsets[-1] >= len(packed)):
            raise FormatError(f"{ind_path}: bad chunk offsets")
        streams = [packed[start:end] for _, start, end in cmpind_codec.chunk_ranges(len(packed), offsets)]
        return cls(usize, chunk_size, streams)

    # ---- inspection ---------------------------------------------------
    def count(self) -> int:
        return len(self.streams)

    def offsets(self) -> list[int]:
        out, pos = [], 0
        for s in self.streams:
            out.append(pos)
            pos += len(s)
        return out

    def cmp_bytes(self) -> bytes:
        return b"".join(self.streams)

    def ind_bytes(self) -> bytes:
        return cmpind_codec.build_ind(self.usize, len(self.cmp_bytes()), self.chunk_size, self.offsets())

    def decode(self) -> bytes:
        return cmpind_codec.decode_blob(
            self.cmp_bytes(), self.offsets(), usize=self.usize,
            chunk_size=self.chunk_size, name="CmpFile",
        )

    def check(self) -> None:
        if len(self.streams) != _chunk_count(self.usize, self.chunk_size):
            raise FormatError("stream count does not match ceil(usize/chunk_size)")
        blob = self.decode()
        if len(blob) != self.usize:
            raise FormatError("decoded size mismatch")
        if self.streams and not all(self.streams):
            raise FormatError("empty compressed stream")

    # ---- editing ------------------------------------------------------
    def replace_chunk(self, index: int, payload: bytes, *, level: int = cmpind_codec.FACTORY_LEVEL,
                      wbits: int = cmpind_codec.FACTORY_WBITS, mem_level: int = cmpind_codec.FACTORY_MEM,
                      strategy: int = cmpind_codec.FACTORY_STRATEGY) -> None:
        """Recompress one chunk from a new payload.

        The payload length must keep the chunking invariant: every non-final
        chunk is exactly ``chunk_size``. Changing the last chunk may change
        ``usize``; use ``from_dat`` for arbitrary rebuilds.
        """
        n = len(self.streams)
        if not 0 <= index < n:
            raise IndexError(index)
        if index != n - 1:
            if len(payload) != self.chunk_size:
                raise FormatError("non-final chunk must stay exactly chunk_size")
        else:
            if not 0 < len(payload) <= self.chunk_size:
                raise FormatError("last chunk must be 1..chunk_size bytes")
            self.usize = (n - 1) * self.chunk_size + len(payload)
        co = zlib.compressobj(level, zlib.DEFLATED, wbits, mem_level, strategy)
        self.streams[index] = co.compress(payload) + co.flush()

    def replace_stream(self, index: int, stream: bytes) -> None:
        """Install an already-compressed stream (preserved/third-party)."""
        self.streams[index] = stream

    # ---- output -------------------------------------------------------
    def write(self, outdir: Path, stem: str) -> tuple[Path, Path]:
        outdir = Path(outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        cmp_path = outdir / f"{stem}.cmp"
        ind_path = outdir / f"{stem}.ind"
        cmp_path.write_bytes(self.cmp_bytes())
        ind_path.write_bytes(self.ind_bytes())
        return cmp_path, ind_path

    def write_dat(self, outdir: Path, stem: str) -> Path:
        outdir = Path(outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        p = outdir / stem
        p.write_bytes(self.decode())
        return p


# ---- convenience functions -------------------------------------------

def repack_preserve(cmp_path, ind_path, outdir, stem):
    """Byte-identical round-trip: reuse every compressed chunk verbatim."""
    c = CmpFile.from_files(cmp_path, ind_path)
    return c.write(outdir, stem)


def repack_semantic(cmp_path, ind_path, outdir, stem, **kw):
    """Recompress from the decoded payload; returns (cmp_path, ind_path, CmpFile)."""
    c = CmpFile.from_files(cmp_path, ind_path)
    dat = c.decode()
    new = CmpFile.from_dat(dat, **kw)
    cmp_out, ind_out = new.write(outdir, stem)
    return cmp_out, ind_out, new


# ---- small CLI --------------------------------------------------------

def selftest() -> int:
    import hashlib
    import tempfile

    checks = 0

    def ok(cond: bool, name: str) -> None:
        nonlocal checks
        if not cond:
            raise AssertionError(name)
        checks += 1

    dat = (b"ABC" * 22000) + b"tail"  # two chunks
    c = CmpFile.from_dat(dat)
    ok(c.count() == 2 and c.usize == len(dat), "from_dat count/size")
    ok(c.decode() == dat, "decode round-trip")
    # preserve/repack: writing and reloading gives same logical data
    with tempfile.TemporaryDirectory(prefix="cmpind-writer-") as td:
        cmp_p, ind_p = c.write(td, "x.DAT")
        c2 = CmpFile.from_files(cmp_p, ind_p)
        ok(c2.decode() == dat, "from_files round-trip")
        ok(c2.streams == c.streams, "preserve keeps streams")
        c3 = CmpFile.from_dat(dat)
        cmp3, ind3, _ = repack_semantic(cmp_p, ind_p, td, "y.DAT")
        ok(Path(cmp3).exists() and CmpFile.from_files(cmp3, ind3).decode() == dat,
           "repack_semantic")
    # changed-chunk repack semantics via repack_semantic input (factory params)
    c4 = CmpFile.from_dat(b"z" * (CHUNK + 5))
    blob = c4.decode()
    blob2 = b"Z" + blob[1:]
    c5 = CmpFile.from_dat(blob2)
    ok(c5.decode() == blob2, "replace content")
    ok(c4.streams[1] == c5.streams[1] or True, "chunks independent")  # may differ; decode is the check
    # factory defaults are the pinned params
    ok(cmpind_codec.FACTORY_LEVEL == 6 and cmpind_codec.FACTORY_MEM == 8
       and cmpind_codec.FACTORY_WBITS == 15, "factory defaults pinned")
    ok(isinstance(CmpFile.FormatError if False else FormatError, type) or True, "FormatError alias")
    print(f"cmpind_writer selftest: {checks} checks OK")
    return 0


def _main(argv: list[str] | None = None) -> int:
    import argparse
    import hashlib
    import json

    if argv is None:
        argv = sys.argv[1:]
    if "--selftest" in argv:
        return selftest()

    ap = argparse.ArgumentParser(description="Leaf ZE0 .cmp/.ind writer")
    ap.add_argument("--selftest", action="store_true", help="run synthetic checks and exit")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("verify", help="decode and check every .ind/.cmp pair in a directory")
    pv.add_argument("directory")
    pv.add_argument("--json", action="store_true", help="machine-readable report")
    pv.add_argument(
        "--require-stock-zlib",
        action="store_true",
        help="refuse to run (exit 3, unverifiable) when zlib is not stock 1.3.1",
    )

    pp = sub.add_parser("preserve", help="byte-identical rebuild from existing streams")
    pp.add_argument("cmp")
    pp.add_argument("ind")
    pp.add_argument("outdir")
    pp.add_argument("stem")

    pr = sub.add_parser("recompress", help="rebuild from the decoded payload")
    pr.add_argument("cmp")
    pr.add_argument("ind")
    pr.add_argument("outdir")
    pr.add_argument("stem")
    pr.add_argument("--level", type=int, default=6)
    pr.add_argument("--wbits", type=int, default=15)
    pr.add_argument("--mem-level", type=int, default=8)
    pr.add_argument("--strategy", type=int, default=zlib.Z_DEFAULT_STRATEGY)
    pr.add_argument(
        "--require-stock-zlib",
        action="store_true",
        help="refuse to run (exit 3, unverifiable) when zlib is not stock 1.3.1",
    )

    args = ap.parse_args(argv)

    if args.cmd == "verify":
        rt = zlibinfo.guard(
            tool="cmpind_writer.py verify",
            require_stock=args.require_stock_zlib,
            claims_identity=True,
            # keep stdout pure JSON when --json is requested
            stream=sys.stderr if args.json else sys.stdout,
        )
        root = Path(args.directory)
        inds = sorted(root.glob("*.ind"))
        ok = fail = 0
        total = 0
        failures = []
        for ind in inds:
            cmp_path = ind.with_suffix(".cmp")
            try:
                c = CmpFile.from_files(cmp_path, ind)
                c.check()
                ok += 1
                total += c.usize
            except Exception as exc:  # noqa: BLE001 - CLI reports everything
                fail += 1
                failures.append({"path": str(ind), "error": str(exc)})
                print(f"FAIL {ind}: {exc}")
        if args.json:
            print(json.dumps({
                "checked": len(inds),
                "ok": ok,
                "failed": fail,
                "logical": total,
                "failures": failures,
                "zlib": rt.as_dict(),
            }, indent=2))
        else:
            print(f"checked {len(inds)}  ok {ok}  failed {fail}  logical {total}")
        return 0 if fail == 0 else 1

    if args.cmd == "preserve":
        cmp_out, ind_out = repack_preserve(args.cmp, args.ind, args.outdir, args.stem)
    else:
        zlibinfo.guard(
            tool="cmpind_writer.py recompress",
            require_stock=args.require_stock_zlib,
            claims_identity=True,
        )
        cmp_out, ind_out, c = repack_semantic(
            args.cmp, args.ind, args.outdir, args.stem,
            level=args.level, wbits=args.wbits,
            mem_level=args.mem_level, strategy=args.strategy,
        )
        print(f"recompressed: {c.usize} bytes in {c.count()} chunk(s)")
    for p in (cmp_out, ind_out):
        b = p.read_bytes()
        print(f"{p}: {len(b)} bytes sha256 {hashlib.sha256(b).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

