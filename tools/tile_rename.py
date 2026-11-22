#!/usr/bin/env python3
"""Rename one map label inside a ``MAPAL001`` tile, keeping every stream length (M8.H70).

A ``MAPAL001`` tile is a run of independent zlib streams (``78 9c``) after
``0x5200`` (``docs/format/map-tiles.md``). Street labels sit inside the
decompressed records as ``1=NAME`` text (``ze0_decode.parse_names_section``).
This tool finds every stream whose plain bytes contain a given text and
replaces it with a text of the same length. Each changed stream is
recompressed with the first zlib setting (level, memLevel, strategy) whose
output has exactly the original compressed length, so no offset, slot or
file size moves and the card can be patched in place with
``tools/imgpatch.py`` (same length, no FAT change).

Commands
    find   TILE --text TEXT [--json]           list streams that hold TEXT
    rename TILE --old OLD --new NEW -o OUT      write the renamed tile
           [--only OFFSET ...]                 limit to the streams at these offsets
    --selftest                                  synthetic checks, no vendor data

``--word`` (default on) matches the text only between label delimiters
(``=``, ``;``, NUL or the record bytes around them), so ``KING STREET`` does
not also hit ``VIKING STREET``. ``--any`` turns this off.

Exit codes: 0 ok, 1 a stream could not be recompressed to its length (nothing
written), 2 usage error, 3 text not found / bad input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import zlib
from pathlib import Path

FIRST_STREAM = 0x5200
STRATEGIES = (zlib.Z_DEFAULT_STRATEGY, zlib.Z_FILTERED, zlib.Z_HUFFMAN_ONLY,
              zlib.Z_RLE, zlib.Z_FIXED)
ZHDR = re.compile(rb"\x78[\x01\x5e\x9c\xda]")


def streams(blob: bytes, start: int = FIRST_STREAM):
    """Yield (offset, compressed length, plain) for each clean zlib stream."""
    pos = start
    n = len(blob)
    while pos < n:
        m = ZHDR.search(blob, pos)
        if m is None:
            return
        h = m.start()
        d = zlib.decompressobj()
        try:
            plain = d.decompress(blob[h:h + (1 << 20)])
        except zlib.error:
            pos = h + 1
            continue
        if not d.eof:
            pos = h + 1
            continue
        clen = min(n - h, 1 << 20) - len(d.unused_data)
        yield h, clen, plain
        pos = h + clen


def _hits(plain: bytes, text: bytes, word: bool) -> list[int]:
    out = []
    i = plain.find(text)
    while i >= 0:
        ok = True
        if word:
            before = plain[i - 1] if i > 0 else 0
            after = plain[i + len(text)] if i + len(text) < len(plain) else 0
            # a label starts after '=' (``1=``) or ';' and ends at ';' or NUL
            ok = before in (0x3d, 0x3b, 0x00) and after in (0x3b, 0x00)
        if ok:
            out.append(i)
        i = plain.find(text, i + 1)
    return out


def find(blob: bytes, text: bytes, word: bool = True) -> list[dict]:
    res = []
    for off, clen, plain in streams(blob):
        hits = _hits(plain, text, word)
        if hits:
            ctx = [plain[max(0, h - 12):h + len(text) + 4].decode("latin1") for h in hits]
            res.append({"offset": off, "clen": clen, "plen": len(plain),
                        "key": plain[:6].hex(), "hits": hits, "context": ctx})
    return res


def recompress_exact(plain: bytes, clen: int, original: bytes | None = None):
    """First (level, mem, strategy) giving exactly ``clen`` bytes, else None.

    When ``original`` is given, a setting that reproduces it is tried first
    (it is the factory encoder, if any setting matches it).
    """
    tried = []
    for level in (9, 8, 7, 6, 5, 4, 3, 2, 1):
        for mem in (8, 9, 7, 6, 5, 4, 3, 2, 1):
            for strat in STRATEGIES:
                c = zlib.compressobj(level, zlib.DEFLATED, 15, mem, strat)
                out = c.compress(plain) + c.flush()
                tried.append(len(out))
                if len(out) == clen:
                    return out, {"level": level, "memLevel": mem, "strategy": strat}
    return None, {"lengths": sorted(set(tried))}


def factory_setting(plain: bytes, stream: bytes):
    for level in range(9, 0, -1):
        for mem in range(9, 0, -1):
            for strat in STRATEGIES:
                c = zlib.compressobj(level, zlib.DEFLATED, 15, mem, strat)
                if c.compress(plain) + c.flush() == stream:
                    return {"level": level, "memLevel": mem, "strategy": strat}
    return None


def rename(blob: bytes, old: bytes, new: bytes, word: bool = True, only=None):
    if len(old) != len(new):
        raise ValueError("same-length rename only: %d != %d" % (len(old), len(new)))
    out = bytearray(blob)
    report = []
    failed = []
    for off, clen, plain in streams(blob):
        if only is not None and off not in only:
            continue
        hits = _hits(plain, old, word)
        if not hits:
            continue
        p = bytearray(plain)
        for h in hits:
            p[h:h + len(old)] = new
        p = bytes(p)
        fac = factory_setting(plain, blob[off:off + clen])
        comp, how = None, None
        if fac:
            c = zlib.compressobj(fac["level"], zlib.DEFLATED, 15, fac["memLevel"], fac["strategy"])
            cand = c.compress(p) + c.flush()
            if len(cand) == clen:
                comp, how = cand, dict(fac, factory=True)
        if comp is None:
            comp, how = recompress_exact(p, clen)
        row = {"offset": off, "clen": clen, "hits": len(hits), "factory": fac,
               "setting": how}
        if comp is None:
            failed.append(row)
        else:
            assert zlib.decompress(comp) == p
            out[off:off + clen] = comp
            row["sha_old"] = hashlib.sha256(blob[off:off + clen]).hexdigest()[:16]
            row["sha_new"] = hashlib.sha256(comp).hexdigest()[:16]
        report.append(row)
    return bytes(out), report, failed


# ---------------------------------------------------------------- selftest

def _synthetic_tile() -> tuple[bytes, list[bytes]]:
    import random
    rnd = random.Random(7)
    plains = []
    for i in range(30):
        body = bytes(rnd.randrange(256) for _ in range(rnd.randrange(40, 400)))
        names = b"1=AIR STREET;2=A4\x00" if i in (3, 17) else b"1=VIKING STREET\x00"
        if i == 22:
            names = b"1=HAIR STREETS\x00"
        plains.append(b"\x95\x1f\xc8\x02\x00\xfa" + body + names + body[:50])
    blob = bytearray(FIRST_STREAM)
    for p in plains:
        blob += zlib.compress(p, 9)
        blob += b"\x00" * (len(blob) % 3)
    return bytes(blob), plains


def selftest() -> int:
    fails = 0

    def check(name, cond, detail=""):
        nonlocal fails
        print(("ok   " if cond else "FAIL ") + name + (" " + detail if detail else ""))
        if not cond:
            fails += 1

    blob, plains = _synthetic_tile()
    got = list(streams(blob))
    check("streams: all 30 found", len(got) == 30, str(len(got)))
    check("streams: plain bytes match", [g[2] for g in got] == plains)
    hits = find(blob, b"AIR STREET")
    check("find: word match hits streams 3 and 17 only", len(hits) == 2,
          str([h["offset"] for h in hits]))
    anyhits = find(blob, b"AIR STREET", word=False)
    check("find --any also hits HAIR STREETS", len(anyhits) == 3)
    vik = find(blob, b"KING STREET")
    check("find: KING STREET does not hit VIKING STREET", vik == [])
    new, report, failed = rename(blob, b"AIR STREET", b"OSM STREET")
    check("rename: no failed stream", not failed, str(failed))
    check("rename: file length kept", len(new) == len(blob))
    after = list(streams(new))
    check("rename: same stream offsets and lengths",
          [(o, c) for o, c, _ in after] == [(o, c) for o, c, _ in got])
    changed = [i for i, (a, b) in enumerate(zip(got, after)) if a[2] != b[2]]
    check("rename: exactly streams 3 and 17 changed", changed == [3, 17], str(changed))
    check("rename: new text present", b"1=OSM STREET;2=A4" in after[3][2])
    check("rename: stream 22 untouched", after[22][2] == plains[22])
    outside = [i for i in range(len(blob)) if blob[i] != new[i]
               and not any(r["offset"] <= i < r["offset"] + r["clen"] for r in report)]
    check("rename: no byte changed outside changed streams", not outside)
    off17 = got[17][0]
    new2, rep2, _ = rename(blob, b"AIR STREET", b"OSM STREET", only={off17})
    check("rename --only: one stream changed", [r["offset"] for r in rep2] == [off17])
    try:
        rename(blob, b"AIR STREET", b"OSM")
        check("rename: length change refused", False)
    except ValueError:
        check("rename: length change refused", True)
    print("selftest: %s (%d failed)" % ("PASS" if not fails else "FAIL", fails))
    return 0 if not fails else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    f = sub.add_parser("find", help="list streams holding a text")
    f.add_argument("tile")
    f.add_argument("--text", required=True)
    f.add_argument("--any", action="store_true", help="no label-delimiter check")
    f.add_argument("--json", action="store_true")
    r = sub.add_parser("rename", help="same-length rename, same stream lengths")
    r.add_argument("tile")
    r.add_argument("--old", required=True)
    r.add_argument("--new", required=True)
    r.add_argument("-o", "--out", required=True)
    r.add_argument("--any", action="store_true")
    r.add_argument("--only", action="append", type=lambda v: int(v, 0),
                   help="change only the stream at this file offset (repeatable)")
    r.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.cmd:
        ap.print_help()
        return 2
    blob = Path(a.tile).read_bytes()
    if a.cmd == "find":
        res = find(blob, a.text.encode("latin1"), word=not a.any)
        if a.json:
            print(json.dumps(res, indent=1))
        else:
            for row in res:
                print("0x%08x clen %5d plen %5d key %s hits %s %s" % (
                    row["offset"], row["clen"], row["plen"], row["key"],
                    row["hits"], row["context"]))
            print("%d stream(s)" % len(res))
        return 0 if res else 3
    old, new = a.old.encode("latin1"), a.new.encode("latin1")
    if len(old) != len(new):
        print("tile_rename: same-length rename only", file=sys.stderr)
        return 2
    only = set(a.only) if a.only else None
    out, report, failed = rename(blob, old, new, word=not a.any, only=only)
    if not report:
        print("tile_rename: %r not found" % a.old, file=sys.stderr)
        return 3
    for row in report:
        print(json.dumps(row) if a.json else
              "0x%08x clen %5d hits %d factory %s -> %s" % (
                  row["offset"], row["clen"], row["hits"], row["factory"], row["setting"]))
    if failed:
        print("tile_rename: %d stream(s) cannot keep their length; nothing written"
              % len(failed), file=sys.stderr)
        return 1
    Path(a.out).write_bytes(out)
    print("wrote %s (%d streams changed, sha256 %s)" % (
        a.out, len(report), hashlib.sha256(out).hexdigest()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
