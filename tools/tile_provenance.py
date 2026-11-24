#!/usr/bin/env python3
"""tile_provenance.py — how much of a tile is the factory's (M5.86).

"Built from zero" must be a number.  This tool reads a factory tile and a
generated tile with the ``tile_relayout`` model (section tables, directories
with the wide-row parsers, record blocks) and matches every record of the
generated tile against the factory's records by the SHA-256 of its inflated
payload (raw, non-zlib records by their bytes), independent of position.

It prints, per section and level, ``factory_records=N/M`` (N of the M
generated records also occur in the factory tile), and for the container the
bytes of the 4 KiB header that equal the factory header
(``container_constant_bytes``: the header strings, level and box tables are
spec constants that a from-zero writer still takes from the factory, so they
are counted, not hidden).

    tile_provenance.py FACTORY.DAT GENERATED.DAT [--json] [--require-zero]
    tile_provenance.py --selftest

``--require-zero`` exits 1 when any generated record is a factory record.
Exit codes: 0 ok, 1 check failed, 2 usage.  Prints counts and hashes only.
"""
from __future__ import annotations

import argparse
import collections
import hashutil
import json
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import tile_relayout  # noqa: E402

sha256 = hashutil.sha256_bytes

HEADER = tile_relayout.TABLE1_OFF


def record_key(raw: bytes) -> str:
    """SHA-256 of the inflated payload; raw bytes when not one zlib stream."""
    try:
        obj = zlib.decompressobj()
        plain = obj.decompress(raw)
        if obj.eof:
            return "z:" + sha256(plain)
    except zlib.error:
        pass
    return "r:" + sha256(raw.rstrip(b"\0"))


def records(m: dict):
    """Yield ``(section id, level, key)`` for every record of a model."""
    for sec in m["sections"]:
        for L in sec["levels"]:
            for dm in L["dirs"]:
                for u in dm["units"]:
                    if not u["live"]:
                        continue
                    for raw in u["recs"]:
                        if raw:
                            yield sec["id"], L["level"], record_key(raw)


def provenance(factory: bytes, generated: bytes) -> dict:
    fm = tile_relayout.read_model(factory)
    gm = tile_relayout.read_model(generated)
    fkeys = {k for _, _, k in records(fm)}
    per = collections.defaultdict(lambda: [0, 0])
    for sid, lv, k in records(gm):
        per[(sid, lv)][1] += 1
        per[(sid, lv)][0] += k in fkeys
    same_header = sum(a == b for a, b in zip(factory[:HEADER], generated[:HEADER]))
    rows = [dict(section=s, level=l, factory=n, total=t) for (s, l), (n, t) in sorted(per.items())]
    return dict(rows=rows,
                factory_records=sum(r["factory"] for r in rows),
                records=sum(r["total"] for r in rows),
                container_constant_bytes=same_header,
                header_bytes=HEADER,
                factory_sha256=sha256(factory),
                generated_sha256=sha256(generated))


def render(rep: dict) -> str:
    out = []
    for r in rep["rows"]:
        out.append("section %d level %d: factory_records=%d/%d" % (r["section"], r["level"], r["factory"], r["total"]))
    out.append("total: factory_records=%d/%d container_constant_bytes=%d/%d"
               % (rep["factory_records"], rep["records"], rep["container_constant_bytes"], rep["header_bytes"]))
    return "\n".join(out)


def selftest() -> int:
    import struct
    fails = 0

    def ok(cond, msg):
        nonlocal fails
        print(("ok   " if cond else "FAIL ") + msg)
        fails += 0 if cond else 1

    # Reuse tile_relayout's synthetic builder through its selftest helpers:
    # build a one-directory tile, then a copy with one record replaced.
    TABLE1_OFF, SECT_OFF = tile_relayout.TABLE1_OFF, tile_relayout.SECT_OFF
    enc, pad = tile_relayout.enc_addr, tile_relayout.pad256

    def tile(payloads):
        hdr = bytearray(TABLE1_OFF)
        lo = tile_relayout.clarion_tile.LEVEL_OFF
        struct.pack_into(">H", hdr, lo, 1)
        hdr[lo + 2:lo + 4] = bytes([2, 1])
        hdr[lo + 4:lo + 8] = bytes([1, 0x90]) + struct.pack(">H", 1)
        struct.pack_into(">IH", hdr, SECT_OFF + 6, 0xFFFFFFFF, 0)
        recs = []
        for p in payloads:
            c = zlib.compress(p, 6)
            c += bytes((-len(c)) % 4)
            recs.append((c, len(c) // 2, len(p) // 2))
        table, dirp = TABLE1_OFF, TABLE1_OFF + 256
        body = 256
        pos = pad(dirp + 12 + 32 * (4 + body))
        blocks = []
        for c, _, _ in recs:
            blocks.append(pos)
            pos = pad(pos + len(c))
        out = bytearray(pos)
        out[:TABLE1_OFF] = hdr
        struct.pack_into(">IH", out, SECT_OFF, enc(table), 1)
        a = enc(dirp)
        out[table:table + 20] = struct.pack(">10H", 10, 2, 8, 1, 100, 0, 0, 100, a >> 16, a & 0xFFFF)
        d = bytearray(struct.pack(">6H", 0x1046, 0, 32, 5, 6, 0))
        for i in range(32):
            if i < len(recs):
                d += struct.pack(">I", enc(blocks[i])) + struct.pack(">II", recs[i][1], recs[i][2]) + b"\xff" * (body - 8)
            else:
                d += b"\xff" * (4 + body)
        out[dirp:dirp + len(d)] = d
        for (c, _, _), q in zip(recs, blocks):
            out[q:q + len(c)] = c
        return bytes(out)

    p = [bytes([i]) * 40 for i in (1, 2, 3)]
    fac = tile(p)
    same = provenance(fac, fac)
    ok(same["factory_records"] == same["records"] == 3, "factory vs itself: 3/3 factory records (positive control)")
    ok(same["container_constant_bytes"] == TABLE1_OFF, "factory vs itself: whole header constant")
    gen = tile([p[0], bytes([9]) * 40, bytes([8]) * 40])
    r = provenance(fac, gen)
    ok(r["factory_records"] == 1 and r["records"] == 3, "one kept, two new: 1/3 (negative control)")
    new = tile([bytes([7]) * 40])
    ok(provenance(fac, new)["factory_records"] == 0, "all new: 0/1")
    ok(main([str(Path("/nonexistent"))]) == 2, "usage error exits 2")
    print("tile_provenance selftest: %s (%d failure(s))" % ("OK" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("factory", nargs="?")
    ap.add_argument("generated", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--require-zero", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.factory or not args.generated:
        print("usage: tile_provenance.py FACTORY GENERATED", file=sys.stderr)
        return 2
    try:
        rep = provenance(Path(args.factory).read_bytes(), Path(args.generated).read_bytes())
    except OSError as exc:
        print("tile_provenance: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps(rep, indent=1) if args.json else render(rep))
    if args.require_zero and rep["factory_records"]:
        print("tile_provenance: FAIL %d factory record(s)" % rep["factory_records"])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
