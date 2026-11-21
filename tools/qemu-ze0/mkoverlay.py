#!/usr/bin/env python3
"""Write an empty qcow2 overlay over a raw card image (no qemu-img needed).

QEMU's sd-card model needs a power-of-two size and the Leaf card images are
not (EU 2011: 8 057 257 984 B).  ``qemu-img create -f qcow2 -b CARD -F raw
OUT 8G`` solves that, but a QEMU built with ``--disable-tools`` (what
``build.sh`` produces) has no ``qemu-img``.  This writes the same thing: a
qcow2 v3 file with a backing file, the ``raw`` backing-format extension and
an empty L1 table, so every read falls through to the card image and every
write lands in the overlay (the card image is never modified).

    python3 tools/qemu-ze0/mkoverlay.py CARD.img OUT.qcow2 [--size-gib 8]
    python3 tools/qemu-ze0/mkoverlay.py --selftest
"""
import argparse
import os
import struct
import sys
import tempfile

CLUSTER_BITS = 16
CLUSTER = 1 << CLUSTER_BITS
EXT_BACKING_FORMAT = 0xE2792ACA


def build(backing: str, size: int) -> bytes:
    name = os.path.abspath(backing).encode()
    l2_span = CLUSTER * (CLUSTER // 8)          # bytes covered by one L2 table
    l1_size = (size + l2_span - 1) // l2_span
    if l1_size * 8 > CLUSTER:
        raise ValueError("size too large for a one-cluster L1 table")
    fmt = b"raw"
    ext = struct.pack(">II", EXT_BACKING_FORMAT, len(fmt)) + fmt.ljust(8, b"\0")
    ext += struct.pack(">II", 0, 0)
    backing_off = 104 + len(ext)
    hdr = struct.pack(
        ">4sIQIIQIIQQIIQQQQII",
        b"QFI\xfb", 3, backing_off, len(name), CLUSTER_BITS, size, 0,
        l1_size, 3 * CLUSTER,      # L1 table in cluster 3
        1 * CLUSTER, 1,            # refcount table in cluster 1
        0, 0, 0, 0, 0,             # snapshots, feature bits
        4, 104)                    # refcount_order (16 bit), header length
    assert len(hdr) == 104
    c0 = (hdr + ext + name).ljust(CLUSTER, b"\0")
    c1 = struct.pack(">Q", 2 * CLUSTER).ljust(CLUSTER, b"\0")   # -> block
    c2 = (struct.pack(">H", 1) * 4).ljust(CLUSTER, b"\0")       # clusters 0-3
    c3 = bytes(CLUSTER)                                         # empty L1
    return c0 + c1 + c2 + c3


def parse(blob: bytes) -> dict:
    f = struct.unpack(">4sIQIIQIIQQIIQQQQII", blob[:104])
    return {"magic": f[0], "version": f[1],
            "backing": blob[f[2]:f[2] + f[3]].decode(), "size": f[5],
            "l1_size": f[7], "l1_off": f[8], "rc_off": f[9]}


def selftest() -> int:
    with tempfile.TemporaryDirectory() as d:
        card = os.path.join(d, "card.img")
        open(card, "wb").write(b"\x55" * 4096)
        blob = build(card, 8 << 30)
        p = parse(blob)
        ok = [p["magic"] == b"QFI\xfb", p["version"] == 3,
              p["backing"] == card, p["size"] == 8 << 30, p["l1_size"] == 16,
              len(blob) == 4 * CLUSTER, blob[3 * CLUSTER:] == bytes(CLUSTER),
              blob[2 * CLUSTER:2 * CLUSTER + 8] == b"\0\1" * 4]
        try:                                   # negative: L1 would overflow
            build(card, 1 << 50)
            ok.append(False)
        except ValueError:
            ok.append(True)
    print("mkoverlay selftest:", "PASS" if all(ok) else "FAIL", ok)
    return 0 if all(ok) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("card", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--size-gib", type=int, default=8)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.card or not a.out:
        ap.error("CARD and OUT are required")
    size = a.size_gib << 30
    if os.path.getsize(a.card) > size:
        ap.error("card image is larger than --size-gib")
    if size & (size - 1):
        ap.error("--size-gib must give a power of two")
    with open(a.out, "wb") as f:
        f.write(build(a.card, size))
    print(f"{a.out}: qcow2 overlay, {a.size_gib} GiB, backing {os.path.abspath(a.card)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
