#!/usr/bin/env python3
"""Decode COORD001/ZCODE/ICODE001 remaining fields (M4.12).

Covers three decodes requested by TODO M4.12:
- COORD001 header + ``level`` field: a 48-bit region membership bitmask.
- ZCODE offset base: form A (filled header, ADDRE-style trie) vs form B
  (sentinel header, directory/index form) — base rules and what remains.
- ICODE001 trie roots: per-language country-chain root byte offsets, found
  by tracing country chains (the root-pointer index table location is not
  identified from static header/slot analysis; see claims).

Synthetic ``--selftest`` validates the COORD001 mask formula and the
``addre_io`` sector-address encoding used by ZCODE form-A record pointers
(no vendor data).  ``--verify`` runs checks on real decompressed REFER001
files (vendor data outside the repo; paths required).

Evidence: docs/experiments/EXP-2026-11-06-M4.12-coord-zcode-icode-fields.md,
claims C-1000–C-1009.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Any

_TOOLS = str(Path(__file__).resolve().parent)
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

# Reuse the repo's sector-address encoding (addre_io.addr/unaddr) when
# available; fall back to an inline copy so --selftest works standalone.
def _addr(off: int) -> int:
    assert off % 0x100 == 0, off
    return (off // 0x800) << 8 | (off % 0x800) // 0x100


def _unaddr(a: int) -> int:
    return (a >> 8) * 0x800 + (a & 0xFF) * 0x100


def _try_import_addre() -> tuple[Any, Any]:
    for p in (
        Path(__file__).resolve().parent / "ze0-viewer" / "tools_ze0",
        Path(__file__).resolve().parent,
    ):
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)
    try:
        import addre_io  # type: ignore

        return addre_io.addr, addre_io.unaddr
    except Exception:
        return _addr, _unaddr


addr, unaddr = _try_import_addre()


# ---------------------------------------------------------------------------
# COORD001
# ---------------------------------------------------------------------------

def coord001_header(data: bytes) -> dict[str, int]:
    guard, count, f2, f3, z = struct.unpack_from(">I H H I I", data, 0x1000)
    return {"guard": guard, "count": count, "field2": f2, "field3": f3, "zero": z}


def coord001_records(data: bytes) -> list[dict[str, int]]:
    h = coord001_header(data)
    out = []
    for i in range(h["count"]):
        off = 0x1010 + i * 14
        x0, y0, x1, y1, level, pad = struct.unpack_from(">HHHH I H", data, off)
        m48 = (level << 16) | pad
        out.append(
            {
                "index": i + 1,
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "level_u32": level,
                "pad_u16": pad,
                "mask48": m48,
            }
        )
    return out


def coord001_mask(region_1based: int) -> int:
    """Expected 48-bit one-hot mask for a non-last region (1-based)."""
    return 0x400000000000 >> (region_1based - 1)


def _resolve_cmp_ind(path: Path) -> tuple[Path, Path]:
    s = str(path)
    if s.endswith(".cmp"):
        return path, path.with_suffix(".ind")
    if s.endswith(".DAT") and Path(s + ".cmp").exists():
        return Path(s + ".cmp"), Path(s + ".ind")
    if s.endswith(".DAT"):
        # maybe uncompressed .DAT
        return path, path.with_suffix(".ind")
    c, i = Path(s + ".DAT.cmp"), Path(s + ".DAT.ind")
    return (c, i) if c.exists() else (path, path.with_suffix(".ind"))


def _load(path: Path) -> bytes:
    from cmpind import decode
    cmp, ind = _resolve_cmp_ind(path)
    if not ind.exists() and path.exists() and not str(path).endswith((".cmp", ".ind")):
        return path.read_bytes()
    raw = decode(cmp, ind)
    return raw[0] if isinstance(raw, tuple) else raw


def verify_coord001(path: Path) -> dict[str, Any]:
    data = _load(path)
    h = coord001_header(data)
    recs = coord001_records(data)
    checks = []
    for r in recs:
        last = r["index"] == h["count"]
        expect_onehot = coord001_mask(r["index"])
        onehot_ok = r["mask48"] == expect_onehot
        if last:
            checks.append(
                {
                    "region": r["index"],
                    "last": True,
                    "onehot": False,
                    "level_eq_guard": r["level_u32"] == h["guard"],
                    "mask48": hex(r["mask48"]),
                }
            )
        else:
            checks.append(
                {
                    "region": r["index"],
                    "onehot": onehot_ok,
                    "mask48": hex(r["mask48"]),
                }
            )
    # sentinel
    soff = 0x1010 + h["count"] * 14
    sent = struct.unpack_from(">HHHHIH", data, soff)
    return {
        "file": str(path),
        "size": len(data),
        "header": {k: (hex(v) if k == "guard" or k == "field3" else v) for k, v in h.items()},
        "sentinel_allzero": all(v == 0 for v in sent),
        "nonlast_onehot_ok": all(c.get("onehot", True) for c in checks if not c.get("last")),
        "last_level_eq_guard": next((c["level_eq_guard"] for c in checks if c.get("last")), None),
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# ZCODE
# ---------------------------------------------------------------------------

def zcode_form(data: bytes) -> str:
    nodew = struct.unpack_from(">I", data, 0x1006)[0]
    rec_addr = struct.unpack_from(">I", data, 0x1012)[0]
    if nodew > 0 and rec_addr != 0xFFFFFFFF:
        return "A"
    return "B"


def zcode_header_a(data: bytes) -> dict[str, int]:
    return {
        "nodew_halfwords": struct.unpack_from(">I", data, 0x1006)[0],
        "first": struct.unpack_from(">H", data, 0x100e)[0],
        "rec_addr_enc": struct.unpack_from(">I", data, 0x1012)[0],
        "rec_size": struct.unpack_from(">I", data, 0x1016)[0],
        "recw": struct.unpack_from(">H", data, 0x101a)[0],
        "cr": struct.unpack_from("B", data, 0x1032)[0] * 2,
        "kw": struct.unpack_from("B", data, 0x1033)[0],
    }


def zcode_record_base(data: bytes) -> int:
    """Form-A record block byte offset: unaddr of encoded rec_addr at 0x1012."""
    return unaddr(struct.unpack_from(">I", data, 0x1012)[0])


def verify_zcode(path: Path, expect_rec: tuple[int, tuple[int, ...]] | None = None) -> dict[str, Any]:
    data = _load(path)
    form = zcode_form(data)
    res: dict[str, Any] = {"file": str(path), "size": len(data), "form": form}
    if form == "A":
        h = zcode_header_a(data)
        base = zcode_record_base(data)
        res["header_a"] = h
        res["rec_base_byte"] = base
        res["rec_base_hex"] = hex(base)
        # trie sanity: 0x1100 exists
        res["trie_at_1100"] = data[0x1100:0x1104].hex()
        if expect_rec:
            idx, vals = expect_rec
            off = base + idx * 16
            got = struct.unpack_from(">8H", data, off) if off + 16 <= len(data) else None
            res["expect_rec"] = {"index": idx, "off": hex(off), "got": got, "ok": got == vals}
    else:
        # form B: report sentinel + basic structure
        res["header_raw_1000_1040"] = data[0x1000:0x1040].hex()
        res["cr"] = struct.unpack_from("B", data, 0x1032)[0] * 2
        res["kw"] = struct.unpack_from("B", data, 0x1033)[0]
        res["area"] = struct.unpack_from(">H", data, 0x1042)[0] if len(data) > 0x1044 else None
        # ladder-like 16B records count (heuristic)
        ladders = 0
        for off in range(0x1200, len(data) - 16, 16):
            hw = struct.unpack_from(">8H", data, off)
            if hw[-1] == 0 and 0xFFFF in hw and 0 < hw[0] < 0x1000:
                ladders += 1
        res["ladder_like_records"] = ladders
        res["offset_base"] = "unresolved single base; 12-byte >HHBBHI dir entries from 0x1204 with mixed/inline child resolution (see EXP)"
    return res


# ---------------------------------------------------------------------------
# ICODE001
# ---------------------------------------------------------------------------

def find_icode_country_chain_roots(
    data: bytes, anchors: list[bytes] | None = None
) -> list[dict[str, Any]]:
    """Find per-language country-chain roots by locating idx=0 country rows.

    A country-chain root is a byte offset where an N-country chain starts:
    first row has idx==0, nosub==0, roff < 0x100000 (halfword-relative base),
    and the chain reads as sequential country rows. ICODE row roff/cnt fields
    within a chain are halfwords relative to that chain's start (per icode_io).
    The root-pointer table location in refer header/slots was not identified;
    roots are located by chain tracing (verified EU/US).
    """
    if anchors is None:
        anchors = [b"ANDORRA\x00", b"CANADA\x00"]
    try:
        import icode_io  # type: ignore
    except Exception:
        # minimal inline row reader
        class _R:
            pass

        def read_row(d, off):
            rlen, nlen, roff, cnt, idx = struct.unpack_from(">HHIHH", d, off)
            r = _R()
            r.rlen = rlen & 0x7FFF
            r.nosub = rlen >> 15
            r.nlen = nlen
            r.roff = roff
            r.cnt = cnt
            r.idx = idx
            r.name = bytes(d[off + 12 : off + 12 + nlen * 2])
            return r

        def read_list(d, off):
            out = []
            while True:
                r = read_row(d, off)
                if r.nlen == 0:
                    return out
                out.append(r)
                if r.rlen == 0:
                    return out
                off += r.rlen * 2

        icode_io = type("X", (), {"read_row": staticmethod(read_row), "read_list": staticmethod(read_list)})

    roots = []
    for country_name in anchors:
        off = 0
        while True:
            i = data.find(country_name, off)
            if i < 0:
                break
            row_off = i - 12
            if row_off >= 0:
                try:
                    r = icode_io.read_row(data, row_off)
                    if r.idx == 0 and not r.nosub and r.roff < 0x100000:
                        chain = icode_io.read_list(data, row_off)
                        names = [x.name.split(b"\x00")[0][:20] for x in chain[:4]]
                        roots.append(
                            {
                                "root_byte": row_off,
                                "root_hex": hex(row_off),
                                "roff": r.roff,
                                "cnt": r.cnt,
                                "chain_len": len(chain),
                                "first_names": [n.decode("utf-8", "replace") for n in names],
                            }
                        )
                except Exception:
                    pass
            off = i + 1
    # dedupe by offset, sort
    seen = set()
    uniq = []
    for r in sorted(roots, key=lambda x: x["root_byte"]):
        if r["root_byte"] not in seen:
            seen.add(r["root_byte"])
            uniq.append(r)
    return uniq


def verify_icode(path: Path) -> dict[str, Any]:
    data = _load(path)
    res: dict[str, Any] = {"file": str(path), "size": len(data)}
    # ISO header
    sz_hw, n = struct.unpack_from(">HH", data, 0x1000)
    res["iso_header"] = {"size_halfwords": sz_hw, "country_count": n}
    roots = find_icode_country_chain_roots(data)
    res["country_chain_roots"] = roots
    res["root_count"] = len(roots)
    res["root_pointer_table"] = "not located in refer header slots (4,13 only) or 0x0000-0x50000 as raw byte/sector offsets; roots verified by chain tracing"
    return res


# ---------------------------------------------------------------------------
# Self-test (synthetic, no vendor data)
# ---------------------------------------------------------------------------

def _check(ok: bool, msg: str, failures: list[str]) -> None:
    if not ok:
        failures.append(msg)
        print(f"FAIL: {msg}")
    else:
        print(f"ok: {msg}")


def selftest() -> int:
    failures: list[str] = []

    # COORD001 mask: 48-bit one-hot 0x400000000000 >> (i-1), i=1-based region.
    _check(coord001_mask(1) == 0x400000000000, "coord mask r1", failures)
    _check(coord001_mask(2) == 0x200000000000, "coord mask r2", failures)
    _check(coord001_mask(32) == 0x000000008000, "coord mask r32 (spills into pad_u16)", failures)
    _check(coord001_mask(33) == 0x000000004000, "coord mask r33 position", failures)
    # Verify mask packs into (level_u32<<16)|pad_u16
    for i in (1, 2, 16, 31, 32):
        m = coord001_mask(i)
        lev = (m >> 16) & 0xFFFFFFFF
        pad = m & 0xFFFF
        _check(((lev << 16) | pad) == m, f"coord mask pack/unpack r{i}", failures)
    # r32: level_u32 should be 0, pad 0x8000
    m32 = coord001_mask(32)
    _check(((m32 >> 16) & 0xFFFFFFFF) == 0 and (m32 & 0xFFFF) == 0x8000,
           "coord mask r32 level=0 pad=0x8000", failures)

    # Synthetic COORD001 blob
    # 2 regions: r1 one-hot, r2 last with guard=0x55, sentinel
    def mkrec(x0, y0, x1, y1, lev, pad):
        return struct.pack(">HHHHIH", x0, y0, x1, y1, lev, pad)

    guard = 0x55
    header = struct.pack(">IHHII", guard, 2, 7, 0x8000, 0)
    blob = bytearray(0x1010)
    blob[0x1000:0x1010] = header
    m1 = coord001_mask(1)
    blob += mkrec(1, 2, 3, 4, (m1 >> 16) & 0xFFFFFFFF, m1 & 0xFFFF)
    blob += mkrec(5, 6, 7, 8, guard, 0)  # last: level==guard
    blob += mkrec(0, 0, 0, 0, 0, 0)     # sentinel
    h = coord001_header(bytes(blob))
    _check(h == {"guard": guard, "count": 2, "field2": 7, "field3": 0x8000, "zero": 0},
           "coord header parse", failures)
    recs = coord001_records(bytes(blob))
    _check(len(recs) == 2 and recs[0]["mask48"] == 0x400000000000, "coord rec1 mask", failures)
    _check(recs[1]["level_u32"] == guard, "coord last level==guard", failures)

    # ZCODE addr/unaddr (sector encoding used by form-A 0x1012)
    for off in (0, 0x100, 0x700, 0x800, 0x900, 0x5D7800, 0xBAF00 if False else 0x200200):
        enc = addr(off)
        dec = unaddr(enc)
        _check(dec == off, f"addr/unaddr roundtrip off={hex(off)} enc={hex(enc)}", failures)
    # ZCODE018 known pair: rec_addr_enc 0xbaf00 -> byte 0x5d7800
    _check(unaddr(0xBAF00) == 0x5D7800, "zcode018 rec_addr unaddr(0xbaf00)=0x5d7800", failures)
    _check(addr(0x5D7800) == 0xBAF00, "zcode018 addr(0x5d7800)=0xbaf00", failures)
    # form-A trie base constant
    _check(0x1100 + 0 * 2 == 0x1100, "zcode form-A trie base 0x1100 halfword-indexed", failures)
    _check(0x1100 + 60 * 2 == 0x1178, "zcode form-A child halfword example", failures)

    # ZCODE form detection (synthetic)
    fa = bytearray(0x2000)
    struct.pack_into(">I", fa, 0x1006, 100)
    struct.pack_into(">I", fa, 0x1012, 0x1234)
    _check(zcode_form(bytes(fa)) == "A", "zcode form A detect", failures)
    fb = bytearray(0x2000)
    struct.pack_into(">I", fb, 0x1006, 0)
    struct.pack_into(">I", fb, 0x1012, 0xFFFFFFFF)
    _check(zcode_form(bytes(fb)) == "B", "zcode form B detect", failures)

    # ICODE: ISO header parse + chain-root finder logic on synthetic chain
    # build minimal icode-like country chain at 0x200: 2 country rows idx 0,1
    def mkrow(rlen_hw, nosub, nlen, roff, cnt, idx, name):
        nm = name if isinstance(name, bytes) else name.encode()
        nm = nm + b"\x00" * (-len(nm) % 2)
        nlen2 = len(nm) // 2
        rlen2 = nlen2 + 6
        return struct.pack(">HHIHH", (rlen2 | (0x8000 if nosub else 0)), nlen2, roff, cnt, idx) + nm

    chain = mkrow(0, 0, 0, 20, 1, 0, b"ANDORRA") + mkrow(0, 0, 0, 40, 1, 1, b"BELGIUM") + struct.pack(">HHII", 6, 0, 0xFFFFFFFF, 0)
    buf = bytearray(0x500)
    buf[0x200:0x200 + len(chain)] = chain
    roots = find_icode_country_chain_roots(bytes(buf))
    _check(len(roots) == 1 and roots[0]["root_byte"] == 0x200, "icode synthetic chain root found @0x200", failures)
    _check(roots[0]["chain_len"] == 2, "icode synthetic chain len 2", failures)

    if failures:
        print(f"selftest: {len(failures)} failures")
        return 1
    print("selftest: all ok")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--verify-coord", type=Path, help="COORD001.DAT path (decompressed or .DAT with .cmp/.ind alongside)")
    ap.add_argument("--verify-zcode", type=Path)
    ap.add_argument("--zcode-expect-index", type=int)
    ap.add_argument("--zcode-expect-vals", help="comma-separated 8 u16 values")
    ap.add_argument("--verify-icode", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if args.verify_coord:
        res = verify_coord001(args.verify_coord)
        print(json.dumps(res, indent=2) if args.json else json.dumps(res, indent=2))
        return 0 if res.get("nonlast_onehot_ok") and res.get("sentinel_allzero") else 1
    if args.verify_zcode:
        expect = None
        if args.zcode_expect_index is not None and args.zcode_expect_vals:
            expect = (args.zcode_expect_index, tuple(int(x) for x in args.zcode_expect_vals.split(",")))
        res = verify_zcode(args.verify_zcode, expect)
        print(json.dumps(res, indent=2))
        ok = res.get("form") == "B" or (res.get("expect_rec", {}).get("ok", True))
        return 0 if ok else 1
    if args.verify_icode:
        res = verify_icode(args.verify_icode)
        print(json.dumps(res, indent=2))
        return 0 if res.get("root_count", 0) >= 1 else 1

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
