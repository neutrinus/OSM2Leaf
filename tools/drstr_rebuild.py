#!/usr/bin/env python3
"""Rebuild a card's DRSTR001.DAT with our writer, from the card image (M9.14).

`drstr_ze0.build(root)` needs a card tree: names, file sizes, and the real
bytes of every ``.ind`` (a ``.cmp`` entry stores the logical size read from
its ``.ind``).  Extracting a 7.5 GB card for that is not needed: ``skeleton``
writes a sparse tree from the FAT32 image in place (every file at its size,
holes for data, real bytes only for ``*.ind``, ``DRSTR001.DAT`` and
``CMP.LST``), and ``build`` runs the writer on it.

  drstr_rebuild.py skeleton CARD.img OUT_DIR
  drstr_rebuild.py build OUT_DIR -o DRSTR.DAT [--grow PATH=BYTES] [--writer-order]
  drstr_rebuild.py --selftest

``build`` prints ``BYTE-IDENTICAL`` when the result equals the card's own
``DRSTR001.DAT`` (the positive control of the writer).  ``--grow`` enlarges
one file of the skeleton by BYTES first (a changed card); ``--writer-order``
ignores the reference file's child order (the writer's own sorted order).
Only sizes and names enter the output; no vendor bytes are written into the
repository by this tool.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cardcheck   # noqa: E402
import drstr_ze0   # noqa: E402

REAL = (".ind",)
REAL_NAMES = ("DRSTR001.DAT", "CMP.LST")


def skeleton(source, out: Path) -> dict:
    """Write the sparse tree of *source* (``list_dir``/``read_range``/``walk``)."""
    counts = {"dirs": 0, "files": 0, "real": 0, "bytes": 0}
    out.mkdir(parents=True, exist_ok=True)
    for entry in source.walk():
        dst = out / entry.path.strip("/")
        if entry.is_dir:
            dst.mkdir(parents=True, exist_ok=True)
            counts["dirs"] += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        counts["files"] += 1
        counts["bytes"] += entry.size
        if entry.name.lower().endswith(REAL) or entry.name.upper() in REAL_NAMES:
            dst.write_bytes(source.read_range(entry.path, 0, entry.size))
            counts["real"] += 1
        else:
            with open(dst, "wb") as fh:
                fh.truncate(entry.size)
    return counts


def build(root: Path, grow: list[str], writer_order: bool) -> bytes:
    """Run the writer on *root*; ``grow`` sizes are applied and then undone."""
    undo = []
    try:
        for spec in grow:
            rel, _, n = spec.rpartition("=")
            path = root / rel
            size = path.stat().st_size
            undo.append((path, size))
            with open(path, "r+b") as fh:
                fh.truncate(size + int(n, 0))
        if not writer_order:
            return drstr_ze0.build(root)
        ref = root / "DRSTR001.DAT"
        saved = ref.read_bytes()
        ref.unlink()
        try:
            return drstr_ze0.build(root)
        finally:
            ref.write_bytes(saved)
    finally:
        for path, size in undo:
            with open(path, "r+b") as fh:
                fh.truncate(size)


def selftest() -> int:
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        (src / "REFER001").mkdir(parents=True)
        (src / "MAPAL001").mkdir()
        (src / "MAPAL001" / "B28R070R.DAT").write_bytes(b"t" * 300)
        (src / "REFER001" / "A.DAT.cmp").write_bytes(b"c" * 50)
        ind = (1000).to_bytes(4, "little") + (50).to_bytes(4, "little") + (1).to_bytes(4, "little") \
            + (0x10000).to_bytes(4, "little") + (0).to_bytes(4, "little")
        (src / "REFER001" / "A.DAT.ind").write_bytes(ind)
        (src / "CMP.LST").write_bytes(b"REFER001\r\n")
        (src / "DRSTR001.DAT").write_bytes(drstr_ze0.build(src))
        want = (src / "DRSTR001.DAT").read_bytes()
        sk = Path(tmp) / "sk"
        counts = skeleton(cardcheck.RootSource(src), sk)
        if counts["files"] != 5 or counts["real"] != 3:
            fails.append("skeleton counts %r" % counts)
        if (sk / "MAPAL001" / "B28R070R.DAT").read_bytes() != bytes(300):
            fails.append("data file is not a hole of its size")
        if (sk / "REFER001" / "A.DAT.ind").read_bytes() != ind:
            fails.append(".ind bytes not copied")
        if build(sk, [], False) != want:
            fails.append("positive control: rebuild of the skeleton is not byte-identical")
        grown = build(sk, ["MAPAL001/B28R070R.DAT=0x800"], False)
        if grown == want or len(grown) != len(want):
            fails.append("negative control: a grown file did not change only values")
        if (sk / "MAPAL001" / "B28R070R.DAT").stat().st_size != 300:
            fails.append("--grow was not undone")
    for f in fails:
        print("FAIL", f)
    print("drstr_rebuild selftest: %s" % ("OK" if not fails else "FAILED"))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("skeleton")
    p.add_argument("card")
    p.add_argument("out")
    p = sub.add_parser("build")
    p.add_argument("root")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--grow", action="append", default=[], metavar="PATH=BYTES")
    p.add_argument("--writer-order", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "skeleton":
        src = cardcheck.Fat32Image(Path(args.card))
        counts = skeleton(src, Path(args.out))
        print("skeleton: %(dirs)d directories, %(files)d files (%(real)d with real bytes), "
              "%(bytes)d logical bytes" % counts)
        return 0
    if args.cmd == "build":
        root = Path(args.root)
        got = build(root, args.grow, args.writer_order)
        Path(args.output).write_bytes(got)
        ref = (root / "DRSTR001.DAT").read_bytes()
        print("built %d bytes sha256 %s" % (len(got), hashlib.sha256(got).hexdigest()))
        if got == ref:
            print("BYTE-IDENTICAL to the card's DRSTR001.DAT")
        else:
            diffs = [i for i in range(min(len(got), len(ref))) if got[i] != ref[i]]
            print("differs from the card's DRSTR001.DAT: %d byte(s)%s, length %d vs %d"
                  % (len(diffs), (", first at %#x" % diffs[0]) if diffs else "", len(got), len(ref)))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
