#!/usr/bin/env python3
"""Test the C-1811 ``RDSTM001`` ``ref`` -> ``INTER``/``FRWAY`` lead as aligned fields (M4.16c).

C-1811 (M4.16, 2026-11-06) found that 500 ``ref`` values read at +4 of the
M4.1 16-byte rows in ``RDSTM001.DAT`` ``0x1000..0x1a700`` occur as 4-byte
LE/BE sequences in decompressed ``INTER001``-``INTER005`` far more often than
500 uniform random ``u32`` (e.g. INTER002 95 vs 1).  The M4.1 framing is not
the record framing (C-1800, C-5134), and a uniform random ``u32`` almost never
contains zero bytes, so the lead may only say "these values have zero bytes".
This tool re-runs the byte scan and adds:

* ``zero``  - a zero-byte-matched control: each real value keeps its zero
  bytes in the same positions, the non-zero bytes are drawn at random
  (non-zero).  If the lead is an artifact of zero bytes, this control hits
  as often as the real values.
* ``bytes`` - a byte-profile control: each byte drawn from the pooled byte
  histogram of the real values.
* aligned tests: the value must sit at a 4-byte aligned offset of the file,
  or be the ``u32`` at +2 of a blob-0 6-byte element (``4000 0000 XXXX`` node
  refs, ``refer.md``), or equal one 12-byte table record's ``(key, 0)``
  or ``(length, b8)`` pair (big-endian, ``inter_table.py``).
* ``--decoded``: the same tests for real M4.16e link refs
  (``(group << 16) | entry`` of the set-1 link records), which are the
  firmware-decoded form of an RDSTM reference.

Usage::

    inter_ref_probe.py scan RDSTM001.DAT REFER001 [--files INTER001,...] [--decoded]
    inter_ref_probe.py --selftest
"""
from __future__ import annotations

import argparse
import random
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

ROW = 16
LEAD_START, LEAD_END = 0x1000, 0x1A700
DEFAULT_FILES = "INTER001,INTER002,INTER003,INTER004,INTER005"


def lead_refs(d: bytes, n: int = 500, start: int = LEAD_START, end: int = LEAD_END) -> list[int]:
    """First ``n`` unique non-zero-row LE ``u32`` at +4 of 16-byte rows (M4.1 framing, C-1811)."""
    out, seen = [], set()
    for off in range(start, min(end, len(d) - ROW + 1), ROW):
        row = d[off:off + ROW]
        if row == b"\0" * ROW:
            continue
        v = struct.unpack_from("<I", row, 4)[0]
        if v not in seen:
            seen.add(v)
            out.append(v)
            if len(out) >= n:
                break
    return out


def ctl_uniform(vals, rng):
    return [rng.getrandbits(32) for _ in vals]


def ctl_zero(vals, rng):
    """Keep zero bytes (LE byte positions), draw the other bytes from 1..255."""
    out = []
    for v in vals:
        b = bytearray(v.to_bytes(4, "little"))
        for i in range(4):
            if b[i]:
                b[i] = rng.randrange(1, 256)
        out.append(int.from_bytes(b, "little"))
    return out


def ctl_bytes(vals, rng):
    pool = [x for v in vals for x in v.to_bytes(4, "little")]
    return [int.from_bytes(bytes(rng.choice(pool) for _ in range(4)), "little") for _ in vals]


def byte_hits(vals, blob: bytes) -> int:
    """Values found anywhere as LE or BE 4-byte sequences (the C-1811 test)."""
    n = 0
    for v in vals:
        if v.to_bytes(4, "little") in blob or v.to_bytes(4, "big") in blob:
            n += 1
    return n


def aligned_sets(blob: bytes) -> dict[str, set[int]]:
    import inter_table as it

    al = set()
    for off in range(0, len(blob) - 3, 4):
        al.add(struct.unpack_from(">I", blob, off)[0])
        al.add(struct.unpack_from("<I", blob, off)[0])
    elem, table = set(), set()
    rows = it.decode(blob)
    for r in rows:
        table.add((r["key"] << 16))
        table.add((r["length"] << 16) | r["zero8"])
        table.add(r["key"])
        table.add(r["length"])
    if rows:
        # blob 0 = 6-byte elements at 0x2000 (refer.md), up to the end of the last record's run
        base = 0x2000
        last = max(r["index"] + 6 * r["length"] for r in rows)
        for off in range(base, min(len(blob) - 5, base + last), 6):
            elem.add(struct.unpack_from(">I", blob, off + 2)[0])
            elem.add(struct.unpack_from("<I", blob, off + 2)[0])
    return {"aligned4": al, "elem+2": elem, "table": table}


def set_hits(vals, s: set) -> int:
    return sum(v in s for v in vals)


def decoded_refs(d: bytes, n: int, rng) -> list[int]:
    import tmc_fielddir as tf

    pairs = tf.rdstm_pairs(d)
    pool = sorted({r for p in pairs[len(pairs) // 2:] for groups in p["links"].values()
                   for _role, refs in groups for r in refs})
    return rng.sample(pool, min(n, len(pool)))


def run(d: bytes, blobs: dict[str, bytes], decoded: bool, seed: int, n: int) -> list[tuple]:
    rng = random.Random(seed)
    families = {"lead": lead_refs(d, n)}
    if decoded:
        families["m4.16e"] = decoded_refs(d, n, rng)
    rows = []
    for fam, vals in families.items():
        ctls = {"real": vals, "uniform": ctl_uniform(vals, rng), "zero": ctl_zero(vals, rng),
                "bytes": ctl_bytes(vals, rng)}
        for name, blob in blobs.items():
            sets = aligned_sets(blob)
            for cname, cv in ctls.items():
                rows.append((fam, name, cname, len(cv), byte_hits(cv, blob),
                             set_hits(cv, sets["aligned4"]), set_hits(cv, sets["elem+2"]),
                             set_hits(cv, sets["table"])))
    return rows


def cmd_scan(a) -> int:
    import cmpind

    d = Path(a.rdstm).read_bytes()
    root = Path(a.refer)
    blobs = {}
    for name in a.files.split(","):
        cmp_ = root / f"{name}.DAT.cmp"
        blob, _ = cmpind.decode(cmp_, root / f"{name}.DAT.ind")
        blobs[name] = blob
    rows = run(d, blobs, a.decoded, a.seed, a.n)
    print("family  file      values   n  byte_hits  aligned4  elem+2  table")
    for fam, name, cname, n, bh, al, el, tb in rows:
        print(f"{fam:7s} {name:9s} {cname:8s} {n:3d} {bh:9d} {al:9d} {el:7d} {tb:6d}")
    tot: dict = {}
    for fam, _name, cname, _n, bh, al, el, tb in rows:
        t = tot.setdefault((fam, cname), [0, 0, 0, 0])
        for i, v in enumerate((bh, al, el, tb)):
            t[i] += v
    print("totals over files:")
    for (fam, cname), t in tot.items():
        print(f"  {fam:7s} {cname:8s} byte {t[0]:5d} aligned4 {t[1]:5d} elem+2 {t[2]:5d} table {t[3]:4d}")
    return 0


def _selftest() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("ok   " if cond else "FAIL ") + name)
        ok &= bool(cond)

    rng = random.Random(5)
    # rows at 0x1000 with refs at +4; zero row skipped; duplicates dropped
    d = bytearray(0x1000 + 4 * ROW)
    struct.pack_into("<I", d, 0x1000 + 4, 0x00000005)
    struct.pack_into("<I", d, 0x1000 + ROW + 4, 0x00000005)
    struct.pack_into("<I", d, 0x1000 + 3 * ROW + 4, 0x12345678)
    check("lead_refs unique, zero row skipped", lead_refs(bytes(d), 10) == [5, 0x12345678])
    vals = [0x00000005, 0x00120000, 0xABCDEF01]
    z = ctl_zero(vals, rng)
    check("zero control keeps zero bytes",
          all((x.to_bytes(4, "little")[i] == 0) == (v.to_bytes(4, "little")[i] == 0)
              for x, v in zip(z, vals) for i in range(4)))
    # a blob of small big-endian u16 pairs: zero-heavy values hit, uniform ones do not
    blob = b"".join(struct.pack(">HH", 0, i) for i in range(1, 300))
    small = list(range(1, 200))
    check("small values hit byte scan", byte_hits(small, blob) == len(small))
    check("uniform control misses", byte_hits(ctl_uniform(small, rng), blob) < 5)
    check("zero control hits like the real values", byte_hits(ctl_zero(small, rng), blob) > 150)
    al = {struct.unpack_from(">I", blob, o)[0] for o in range(0, len(blob) - 3, 4)}
    check("aligned set holds the BE pairs", set_hits(small, al) == len(small))
    print("selftest: " + ("OK" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("scan")
    s.add_argument("rdstm")
    s.add_argument("refer", help="REFER001 directory with .DAT.cmp/.ind pairs")
    s.add_argument("--files", default=DEFAULT_FILES)
    s.add_argument("--decoded", action="store_true", help="also test real M4.16e link refs")
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("-n", type=int, default=500)
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if a.cmd == "scan":
        return cmd_scan(a)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
