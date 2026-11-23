#!/usr/bin/env python3
"""One SHA-256 implementation for the tools (M8.H76).

Until this module existed, ~30 tools carried a private ``_sha``, ``sha256``,
``sha256_file`` or ``_sha256``. They used different chunk sizes (1<<16, 1<<20,
8<<20, COPY_CHUNK) but the digest of a file is chunk-invariant: the only real
difference was which side of the path/bytes split a caller hashed. Putting both
helpers here keeps that split in one place, so an evidence stamp taken by one
tool and checked by another cannot drift.

No new dependency: hashlib is in the standard library. The chunk default is
1<<20 to match the majority of the former call sites.

Usage::

    python3 tools/hashutil.py --selftest
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from pathlib import Path

DEFAULT_CHUNK = 1 << 20


def sha256_file(path, chunk: int = DEFAULT_CHUNK) -> str:
    """Hex SHA-256 of the bytes of ``path``, streamed in ``chunk`` blocks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Hex SHA-256 of one in-memory byte string."""
    return hashlib.sha256(data).hexdigest()


def selftest() -> int:
    checks = 0

    def ok(cond: bool, label: str) -> None:
        nonlocal checks
        if not cond:
            raise AssertionError(label)
        checks += 1

    ok(sha256_bytes(b"") ==
       "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
       "empty-string vector")
    ok(sha256_bytes(b"abc") ==
       "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
       "abc vector")

    with tempfile.TemporaryDirectory() as tmp:
        sample = Path(tmp) / "hashutil.bin"
        blob = bytes(range(256)) * 4096
        sample.write_bytes(blob)
        want = sha256_bytes(blob)
        ok(sha256_file(sample) == want, "file default chunk matches bytes")
        ok(sha256_file(sample, 1 << 16) == want, "64 KiB chunk")
        ok(sha256_file(sample, 7) == want, "odd chunk")
        ok(sha256_file(str(sample)) == want, "str path as well as Path")
        sample.write_bytes(blob + b"x")
        ok(sha256_file(sample) != want, "negative: changed file differs")

    print(f"hashutil selftest: {checks} checks OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true",
                        help="run synthetic SHA-256 checks and exit")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
