#!/usr/bin/env python3
"""Decode and verify Leaf ZE0 ``.cmp`` / ``.ind`` containers.

Verified against all 194 pairs in the EU 2011 image
``LEAF_2011-2012_QSD-309-101_navi158_eu.img`` (SHA-256
``105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307``).

Format::

    u32 uncompressed_size
    u32 compressed_size        # must equal the .cmp file size
    u32 chunk_count
    u32 chunk_size              # 0x10000 in every observed file
    u32 chunk_offset[chunk_count]

Each chunk is an independent zlib stream.  Concatenating the decompressed
chunks yields exactly ``uncompressed_size`` bytes.

Decoding is independent of the zlib build.  On a build that is not stock
zlib 1.3.1 (e.g. zlib-ng) ``verify`` prints a note through
``tools/zlibinfo.py``: the pairs are still verified, but byte-identical
*recompression* needs stock zlib.  ``verify --json`` carries the runtime in a
``zlib`` field.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import zlibinfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmpind_codec  # noqa: E402

HEADER = cmpind_codec.IND_HEADER
FormatError = cmpind_codec.FormatError


def read_index(ind_path: Path) -> tuple[int, int, int, int, tuple[int, ...]]:
    return cmpind_codec.read_ind(ind_path)


def chunk_ranges(cmp_size: int, offsets: tuple[int, ...]):
    yield from cmpind_codec.chunk_ranges(cmp_size, offsets)


def decode(cmp_path: Path, ind_path: Path | None = None) -> tuple[bytes, dict]:
    if ind_path is None:
        if cmp_path.suffix != ".cmp":
            raise FormatError(f"{cmp_path}: expected a .cmp file")
        ind_path = cmp_path.with_suffix(".ind")
    blob, info = cmpind_codec.decode(cmp_path, ind_path)
    # preserve historical info shape (cmp_path not previously exposed)
    return blob, {k: v for k, v in info.items() if k != "cmp_path"}


def cmd_info(args: argparse.Namespace) -> int:
    usize, csize, count, chunk_size, offsets = read_index(Path(args.ind))
    print(f"index          {args.ind}")
    print(f"uncompressed   {usize} bytes")
    print(f"compressed     {csize} bytes")
    print(f"chunks         {count}")
    print(f"chunk size     {chunk_size}")
    print("offsets        " + ", ".join(f"0x{o:x}" for o in offsets[:10]))
    if len(offsets) > 10:
        print(f"               ... ({len(offsets) - 10} more)")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    cmp_path = Path(args.cmp)
    ind_path = Path(args.ind) if args.ind else None
    blob, info = decode(cmp_path, ind_path)

    out = Path(args.output)
    if out.resolve() == cmp_path.resolve():
        print("error: refusing to overwrite input", file=sys.stderr)
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    print(
        f"{cmp_path} -> {out}: {len(blob)} bytes "
        f"({info['chunk_count']} chunk(s))",
        file=sys.stderr,
    )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    root = Path(args.directory)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    rt = zlibinfo.note_if_nonstock(
        tool="cmpind.py verify",
        note=(
            "decoding is unaffected, but byte-identical recompression needs "
            "stock zlib %s" % zlibinfo.REFERENCE_VERSION
        ),
    )

    inds = sorted(root.glob("*.ind"))
    if not inds:
        print(f"error: no .ind files in {root}", file=sys.stderr)
        return 2

    ok = 0
    failures: list[tuple[Path, str]] = []
    total_uncompressed = 0
    total_compressed = 0

    for ind in inds:
        cmp_path = ind.with_suffix(".cmp")
        if not cmp_path.exists():
            failures.append((ind, f"missing {cmp_path.name}"))
            continue
        try:
            blob, info = decode(cmp_path, ind)
        except (FormatError, OSError) as exc:
            failures.append((ind, str(exc)))
            continue
        ok += 1
        total_uncompressed += info["uncompressed_size"]
        total_compressed += info["compressed_size"]

    if args.json:
        print(json.dumps({
            "checked": len(inds),
            "ok": ok,
            "failed": len(failures),
            "logical": total_uncompressed,
            "stored": total_compressed,
            "failures": [
                {"path": str(path), "error": reason} for path, reason in failures
            ],
            "zlib": rt.as_dict(),
        }, indent=2))
        return 0 if not failures else 1

    print(f"checked   {len(inds)} pair(s)")
    print(f"ok        {ok}")
    print(f"failed    {len(failures)}")
    print(f"logical   {total_uncompressed} bytes")
    print(f"stored    {total_compressed} bytes")
    for path, reason in failures:
        print(f"FAIL {path}: {reason}", file=sys.stderr)
    return 0 if not failures else 1


def selftest() -> int:
    import struct
    import tempfile
    import zlib

    with tempfile.TemporaryDirectory(prefix="cmpind-") as td:
        tmp = Path(td)
        chunk0 = (b"HELLO ZE0 " * 6554)[:65536]
        chunk1 = b"tail" * 100
        blob = chunk0 + chunk1
        streams = [zlib.compress(chunk0, 6), zlib.compress(chunk1, 6)]
        cmp_bytes = b"".join(streams)
        offsets = [0, len(streams[0])]
        ind = struct.pack("<IIII", len(blob), len(cmp_bytes), 2, 65536)
        ind += struct.pack("<2I", *offsets)
        ind_path = tmp / "SAMPLE.DAT.ind"
        cmp_path = tmp / "SAMPLE.DAT.cmp"
        ind_path.write_bytes(ind)
        cmp_path.write_bytes(cmp_bytes)
        out_blob, info = decode(cmp_path, ind_path)
        assert out_blob == blob and info["chunk_count"] == 2
        assert read_index(ind_path)[4] == tuple(offsets)
        out = tmp / "out.dat"
        assert main(["extract", str(cmp_path), "-o", str(out)]) == 0
        assert out.read_bytes() == blob
        assert main(["verify", str(tmp)]) == 0
    print("cmpind selftest: OK")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true", help="run synthetic checks and exit")
    sub = parser.add_subparsers(dest="command")

    p_info = sub.add_parser("info", help="print an .ind header")
    p_info.add_argument("ind")
    p_info.set_defaults(func=cmd_info)

    p_extract = sub.add_parser("extract", help="decompress a .cmp into a .DAT")
    p_extract.add_argument("cmp")
    p_extract.add_argument("--ind", help="index path (default: same stem with .ind)")
    p_extract.add_argument("-o", "--output", required=True)
    p_extract.set_defaults(func=cmd_extract)

    p_verify = sub.add_parser("verify", help="verify every .cmp/.ind pair in a directory")
    p_verify.add_argument("directory")
    p_verify.add_argument("--json", action="store_true", help="machine-readable report")
    p_verify.set_defaults(func=cmd_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "selftest", False):
        return selftest()
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except (FormatError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
