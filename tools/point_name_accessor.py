#!/usr/bin/env python3
"""Run the POINT name accessor in PySh4 with the page context the firmware builds (M3.11c).

M3.11c named the accessor (``fn 0x003f632c(r4=db, r5=rec) -> name ptr`` and
``fn 0x003f5e78 -> name length`` in EU2011; ``0x0041ec8c`` / ``0x0041e7d8`` in
US2011) but could not run it: its resolver ``fn 0x003f51e0`` looks ``db`` up in
the BSS slot table ``0x00d53500`` and takes the *companion* slot (``+0x1c`` ->
``+0x20`` for the POINT walker slot) as the page's field dictionary.  M3.22
(``tools/d53500_writer.py``) showed which writer fills those two slots.

``run`` builds that context with the firmware's own writer:

1. locate the field dictionary block in the decoded ``POINT`` ``.DAT``: the one
   offset ``C`` with ``u16[C] == 0xffff`` that satisfies every check the
   accessor makes (``D = C + 2*u16[C+2]``, ``u16[D+26]`` fields, entries chained
   from ``D + 2*u16[D+24]`` with ``u16[e+12] == i`` for ``i = 0..5``).  This is
   the writer-inverse of the accessor; the tool prints how many offsets match;
2. map the dictionary and the decoded page **swapped to native u16** (the walker
   reads native words, M9.38), run the populate writer (type ``0x14ef``) with
   the page object's buffer = page and the header-table entry's ``+44`` =
   dictionary, so the writer itself fills ``+0x1c`` (page) and ``+0x20``
   (dictionary);
3. bind the one import the resolver calls (``OSMDLL!taskIdSelf``) to a stub;
4. call the name and length accessors on every record of the page, and the
   generic field accessor for field 6 (address).

Checks per record: the name pointer is inside the record, ``2*len`` bytes of
name followed by the field-6 address make up the display text (the suffix after
the record's inner ``ff ff`` marker), and the name is printable Latin-1.  The
text is read from the **file-order** page at the returned offset; in the
swapped buffer the same bytes are pairwise swapped (byte order is M3.11b).

``--rename OLD=NEW`` applies the M5.12 rename (same length) to the page first.
Negative controls in every run: the dictionary slot left empty, and a ``db``
that is not in the table.

Usage::

  point_name_accessor.py --selftest
  point_name_accessor.py run IMG --cmp C --ind I --build us2011 [--rename OLD=NEW]

Method and results: docs/experiments/EXP-2026-11-19-M3.11c-point-name-accessor-l3.md
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
import zlib
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "l3_harness")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import d53500_writer as dw  # noqa: E402
import mutate_refer_poi as mrp  # noqa: E402
import point_walk_l3 as pw  # noqa: E402

DICT_VA = 0x23000000
DICT_SPAN = 0x400
STUB_VA = 0x24000000
HDR_DICT = 44          # hdr field 0x0040e9dc copies for type 0x14ef, selector 0
ESCAPE_TAG = 0x68

#: Per-build entries (EU2011 head ``92aa525d…``, US2011 head ``70d945d8…``).
#: ``pool`` pairs are verified against the image before a run.
BUILDS = {
    "eu2011": {
        "name": 0x003F632C, "length": 0x003F5E78, "field": 0x003F61BC,
        "field_len": 0x003F5D98, "resolver": 0x003F51E0,
        "lookup": 0x0040EE4C, "iat_task_id_self": 0x0055D8F0,
        "pool": ((0x003F6378, 0x003F61BC), (0x003F52B4, 0x0055D8F0),
                 (0x003F5EC4, 0x003F5D98)),
    },
    "us2011": {
        "name": 0x0041EC8C, "length": 0x0041E7D8, "field": 0x0041EB1C,
        "field_len": 0x0041E6F8, "resolver": 0x0041DB90,
        "lookup": 0x00436DD4, "iat_task_id_self": 0x005818D4,
        "pool": ((0x0041ECD8, 0x0041EB1C), (0x0041DC64, 0x005818D4),
                 (0x0041E824, 0x0041E6F8)),
    },
}


# ---------------------------------------------------------------------------
# pure helpers (selftested)


def be16(b: bytes, o: int) -> int | None:
    return (b[o] << 8) | b[o + 1] if 0 <= o and o + 1 < len(b) else None


def find_dictionary(blob: bytes, field: int = 5) -> list[tuple[int, int, int]]:
    """[(C, D, nfields)] for every block that passes the accessor's checks.

    *blob* is in file order (big-endian u16), which is what the firmware sees
    as native words after the swap.
    """
    hits = []
    for c in range(0, len(blob) - 4, 2):
        if blob[c] != 0xFF or blob[c + 1] != 0xFF:
            continue
        off = be16(blob, c + 2)
        if not off:
            continue
        d = c + 2 * off
        n = be16(blob, d + 26)
        first = be16(blob, d + 24)
        if not n or n <= field or first is None:
            continue
        e = d + 2 * first
        ok = True
        for i in range(field + 1):
            if be16(blob, e + 12) != i:
                ok = False
                break
            if i < field:
                nxt = be16(blob, e)
                if nxt is None:
                    ok = False
                    break
                e = d + 2 * nxt
        if ok:
            hits.append((c, d, n))
    return hits


def display_text(rec: bytes) -> bytes:
    """The text after the record's last inner ``ff ff`` marker, before the
    trailing ``ff ff`` (NULs kept)."""
    body = rec[:-2]
    i = body.rfind(b"\xff\xff")
    return body[i + 2:] if i >= 0 else b""


def printable(text: bytes) -> bool:
    t = text.rstrip(b"\x00")
    return bool(t) and all(0x20 <= c < 0x7F or c >= 0xA0 for c in t)


# ---------------------------------------------------------------------------
# the run


def check_build(data: bytes, cfg: dict) -> None:
    mem = dw.sec0_mem(data)
    for pool, want in cfg["pool"]:
        if mem.u32(pool) != want:
            raise dw.Mismatch(f"pool {pool:#010x} holds {mem.u32(pool):#010x}, "
                              f"not {want:#010x}: wrong build?")


def build_context(data: bytes, build: str, native_page: bytes, dict_native: bytes | None,
                  stub_log: list | None = None):
    """Engine with the writer-filled slot table; dict_native=None leaves +0x20 empty.

    *stub_log*, when given, gets one entry per call of the only import the
    run binds (``OSMDLL!taskIdSelf``)."""
    wcfg = dw.BUILDS[build]
    cfg = BUILDS[build]
    glob = dw.type_global(data, wcfg, dw.TYPE_POINT)
    eng = dw.new_engine(data)
    hdr = eng.call(cfg["lookup"], [0, 0])
    eng.map("ctx", dw.CTX_VA, bytearray(0x200), "rw")
    eng.map("obj", dw.OBJ_VA, bytearray(0x100), "rw")
    eng.map("page", dw.PAGE_VA, bytearray(native_page) + bytearray(0x40), "rw")
    eng.map("dict", DICT_VA, bytearray(dict_native or b"\0" * DICT_SPAN), "rw")
    eng.map("stub", STUB_VA, bytearray(0x10), "rx")
    def task_id_self(_e, _va):                        # OSMDLL!taskIdSelf
        if stub_log is not None:
            stub_log.append("OSMDLL!taskIdSelf")
        return 1
    eng.on_exec(STUB_VA, task_id_self)
    dw.put32(eng, cfg["iat_task_id_self"], STUB_VA)
    dw.put32(eng, dw.CTX_VA + dw.CTX_TYPE, dw.TYPE_POINT)
    dw.put32(eng, glob, dw.OBJ_VA)
    dw.put32(eng, glob + 16, 1)
    dw.put32(eng, dw.OBJ_VA + 20, dw.PAGE_VA)
    if dict_native is not None:
        dw.put32(eng, hdr + HDR_DICT, DICT_VA)
    eng.call(wcfg["writer"], [0, dw.CTX_VA, 0, dw.STACK_VA + 0x100])
    slots = (dw.u32(eng, wcfg["table"] + 0x1C), dw.u32(eng, wcfg["table"] + 0x20))
    return eng, hdr, glob, slots


def call(eng, va, args):
    try:
        return eng.call(va, args), None
    except Exception as exc:  # noqa: BLE001
        return None, exc


def run_records(eng, cfg: dict, raw: bytes, records, limit: int):
    rows = []
    for r in records[:limit]:
        rec_va = dw.PAGE_VA + r["offset"]
        ptr, f1 = call(eng, cfg["name"], [dw.PAGE_VA, rec_va])
        ln, f2 = call(eng, cfg["length"], [dw.PAGE_VA, rec_va])
        aptr, f3 = call(eng, cfg["field"], [dw.PAGE_VA, rec_va, 6])
        aln, f4 = call(eng, cfg["field_len"], [dw.PAGE_VA, rec_va, 6])
        row = {"offset": r["offset"], "tag": r["tag"], "ptr": ptr, "len": ln,
               "aptr": aptr, "alen": aln, "fault": f1 or f2 or f3 or f4}
        if ptr not in (None, 0, 0xFFFFFFFF) and ln is not None:
            off = ptr - dw.PAGE_VA
            row["rel"] = off - r["offset"]
            row["name"] = raw[off:off + 2 * ln]
            if aptr not in (None, 0, 0xFFFFFFFF) and aln is not None:
                ao = aptr - dw.PAGE_VA
                row["addr"] = raw[ao:ao + 2 * aln]
        rows.append(row)
    return rows


def judge(row, rec: bytes) -> str:
    if row["fault"] is not None:
        return "fault"
    if "name" not in row:
        return "no-pointer"
    if not 0 <= row["rel"] < len(rec):
        return "outside"
    disp = display_text(rec)
    joined = row["name"] + row.get("addr", b"")
    if not printable(row["name"]):
        return "not-text"
    if joined.rstrip(b"\x00") == disp.rstrip(b"\x00") or \
            (disp.startswith(row["name"]) and "addr" not in row):
        return "ok"
    return "mismatch"


def cmd_run(args) -> int:
    build = args.build
    cfg = BUILDS[build]
    data = pw.load_image(args.image)
    check_build(data, cfg)
    _u, _c, _n, _ch, offsets = mrp.read_ind(Path(args.ind))
    blob = mrp.decode(Path(args.cmp).read_bytes(), offsets)
    page = args.page if args.page is not None else (0x840BA0 if build == "us2011" else 0x6E06D0)
    plen = args.page_len if args.page_len is not None else (42848 if build == "us2011" else 97158)
    raw = zlib.decompressobj().decompress(blob[page:page + plen])
    if args.rename:
        old, new = (s.encode("latin-1") for s in args.rename.split("=", 1))
        raw, info = mrp.resize_name(raw, old, new)
        print(f"rename {old!r} -> {new!r} in record {info['index']} (delta {info['delta']})")
    records = mrp.parse_page(raw)
    hits = find_dictionary(blob)
    print(f"build {build}: name={cfg['name']:#010x} length={cfg['length']:#010x} "
          f"field={cfg['field']:#010x} resolver={cfg['resolver']:#010x}")
    print(f"page {page:#x}: {len(raw)} B decoded, {len(records)} records; "
          f"dictionary candidates={len(hits)} "
          + " ".join(f"C={c:#x}/D={d:#x}/n={n}" for c, d, n in hits))
    if len(hits) != 1:
        print("BLOCKED: the field dictionary is not unique in this file")
        return 4
    c = hits[0][0]
    dict_native = pw.swap16(blob[c:c + DICT_SPAN])
    native = pw.swap16(raw)
    eng, hdr, glob, slots = build_context(data, build, native, dict_native)
    print(f"context: page-object global={glob:#010x} header entry={hdr:#010x} "
          f"slot+0x1c={slots[0]:#010x} slot+0x20={slots[1]:#010x}")
    rows = run_records(eng, cfg, raw, records, args.limit)
    verdicts: dict[str, int] = {}
    for row, rec in zip(rows, records):
        v = judge(row, rec["bytes"])
        row["verdict"] = v
        verdicts[v] = verdicts.get(v, 0) + 1
    for row in rows[:args.show]:
        print(f"  rec @{row['offset']:#06x} tag={row['tag']:#04x} "
              f"name=+{row.get('rel', -1):#x} len={row['len']} words "
              f"text={row.get('name')!r} addr={row.get('addr')!r} -> {row['verdict']}")
    print("records: " + " ".join(f"{k}={v}" for k, v in sorted(verdicts.items()))
          + f" of {len(rows)}")
    # negative controls
    eng0, _h, _g, slots0 = build_context(data, build, native, None)
    r0 = records[0]
    ptr0, f0 = call(eng0, cfg["name"], [dw.PAGE_VA, dw.PAGE_VA + r0["offset"]])
    print(f"negative (no dictionary, slot+0x20={slots0[1]:#x}): rec0 ptr="
          + ("None" if ptr0 is None else f"{ptr0:#x}")
          + (f" fault={type(f0).__name__}" if f0 else ""))
    ptr1, f1 = call(eng, cfg["name"], [dw.PAGE_VA + 2, dw.PAGE_VA + r0["offset"]])
    print("negative (db not in table): rec0 ptr="
          + ("None" if ptr1 is None else f"{ptr1:#x}")
          + (f" fault={type(f1).__name__}" if f1 else ""))
    neg_ok = (ptr0 in (None, 0, 0xFFFFFFFF)) and (ptr1 in (None, 0, 0xFFFFFFFF))
    first = rows[0]
    ok = (slots == (dw.PAGE_VA, DICT_VA) and verdicts.get("ok", 0) == len(rows)
          and neg_ok)
    if args.expect:
        want = args.expect.encode("latin-1")
        got = first.get("name", b"").rstrip(b"\x00")
        print(f"record 0 name: {got!r} (expect {want!r})")
        ok = ok and got == want
    print("result:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def decode_page(data: bytes, build: str, blob: bytes, raw: bytes, limit: int = 100000) -> dict:
    """Run the accessors on every record of *raw* (a decoded page of *blob*).

    The library form of ``run`` for ``l3_harness/runner.py`` (M9.10): no
    printing, one dict.  ``blocked`` is set when the field dictionary is not
    unique in *blob*.  Raises ``d53500_writer.Mismatch`` for a wrong build.
    """
    cfg = BUILDS[build]
    check_build(data, cfg)
    records = mrp.parse_page(raw)
    hits = find_dictionary(blob)
    out = {"build": build, "records": len(records), "dictionary": [list(h) for h in hits]}
    if len(hits) != 1:
        out["blocked"] = "the field dictionary is not unique in this file (%d candidates)" % len(hits)
        return out
    c = hits[0][0]
    dict_native = pw.swap16(blob[c:c + DICT_SPAN].ljust(DICT_SPAN, b"\0"))
    native = pw.swap16(raw)
    stub_log: list = []
    eng, _hdr, _glob, slots = build_context(data, build, native, dict_native, stub_log)
    rows = run_records(eng, cfg, raw, records, limit)
    verdicts: dict[str, int] = {}
    for row, rec in zip(rows, records):
        row["verdict"] = judge(row, rec["bytes"])
        verdicts[row["verdict"]] = verdicts.get(row["verdict"], 0) + 1
    eng0, _h, _g, slots0 = build_context(data, build, native, None)
    r0 = records[0]
    ptr0, _f0 = call(eng0, cfg["name"], [dw.PAGE_VA, dw.PAGE_VA + r0["offset"]])
    ptr1, _f1 = call(eng, cfg["name"], [dw.PAGE_VA + 2, dw.PAGE_VA + r0["offset"]])
    out.update(rows=rows, verdicts=verdicts, slots=list(slots),
               slots_ok=slots == (dw.PAGE_VA, DICT_VA),
               stub_calls=len(stub_log),
               negative={"no_dictionary": ptr0, "db_not_in_table": ptr1,
                         "ok": ptr0 in (None, 0, 0xFFFFFFFF) and ptr1 in (None, 0, 0xFFFFFFFF)})
    return out


def name_of_record0(data: bytes, build: str, blob: bytes, raw: bytes) -> dict:
    """Record 0's name by the accessor alone, without ``parse_page`` (for a
    page the Python parser refuses, e.g. a corrupted ``len2``)."""
    cfg = BUILDS[build]
    check_build(data, cfg)
    hits = find_dictionary(blob)
    if len(hits) != 1:
        return {"blocked": "the field dictionary is not unique in this file"}
    c = hits[0][0]
    stub_log: list = []
    eng, _h, _g, _s = build_context(data, build, pw.swap16(raw),
                                    pw.swap16(blob[c:c + DICT_SPAN].ljust(DICT_SPAN, b"\0")), stub_log)
    ptr, f1 = call(eng, cfg["name"], [dw.PAGE_VA, dw.PAGE_VA])
    ln, f2 = call(eng, cfg["length"], [dw.PAGE_VA, dw.PAGE_VA])
    name = None
    if ptr not in (None, 0, 0xFFFFFFFF) and ln is not None:
        name = raw[ptr - dw.PAGE_VA:ptr - dw.PAGE_VA + 2 * ln]
    return {"name": name, "fault": f1 or f2, "stub_calls": len(stub_log)}


# ---------------------------------------------------------------------------
# self-test (synthetic; no vendor bytes)


def _synthetic_dictionary(nfields: int = 7) -> bytes:
    c = bytearray(b"\xff\xff" + struct.pack(">H", 4)) + bytearray(4)   # D at +8
    d = bytearray(32)
    struct.pack_into(">H", d, 24, 16)      # first entry at D + 32
    struct.pack_into(">H", d, 26, nfields)
    entries = bytearray()
    for i in range(nfields):
        e = bytearray(16)
        struct.pack_into(">H", e, 0, 16 + 8 * (i + 1))   # next entry, words from D
        struct.pack_into(">H", e, 12, i)
        entries += e
    return bytes(c + d + entries)


def selftest() -> int:
    fails = 0

    def check(name, cond):
        nonlocal fails
        print("%-60s %s" % (name, "ok" if cond else "FAIL"))
        fails += not cond

    blob = b"\x00" * 64 + _synthetic_dictionary() + b"\x00" * 64
    hits = find_dictionary(blob)
    check("dictionary: one block found at its offset", [h[0] for h in hits] == [64])
    check("dictionary: field count read", hits and hits[0][2] == 7)
    broken = bytearray(blob)
    struct.pack_into(">H", broken, 64 + 8 + 32 + 16 * 3 + 12, 9)   # entry 3 id
    check("dictionary negative: a wrong field id is rejected", find_dictionary(bytes(broken)) == [])
    few = b"\x00" * 64 + _synthetic_dictionary(nfields=5) + b"\x00" * 64
    check("dictionary negative: 5 fields cannot hold field 5", find_dictionary(few) == [])
    rec = b"\x60\x10" + b"\x00" * 10 + b"\xff\xffHANA HEALTH CENTER4590@HANA HWY\x00\xff\xff"
    check("display text: suffix after the inner marker",
          display_text(rec) == b"HANA HEALTH CENTER4590@HANA HWY\x00")
    row = {"fault": None, "rel": 14, "name": b"HANA HEALTH CENTER",
           "addr": b"4590@HANA HWY\x00"}
    check("judge: name + address == display text", judge(row, rec) == "ok")
    row2 = dict(row, addr=b"4591@HANA HWY\x00")
    check("judge negative: a wrong split is a mismatch", judge(row2, rec) == "mismatch")
    check("judge negative: a fault is reported", judge(dict(row, fault=RuntimeError()), rec) == "fault")
    check("printable: control bytes are not text", not printable(b"\x01\x02"))
    print("selftest:", "PASS" if not fails else f"FAIL ({fails})")
    return 0 if not fails else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("image")
    r.add_argument("--cmp", required=True)
    r.add_argument("--ind", required=True)
    r.add_argument("--build", choices=tuple(BUILDS), default="us2011")
    r.add_argument("--page", type=lambda s: int(s, 0), default=None)
    r.add_argument("--page-len", type=lambda s: int(s, 0), default=None)
    r.add_argument("--limit", type=int, default=100000)
    r.add_argument("--show", type=int, default=3)
    r.add_argument("--rename", help="OLD=NEW (same-length M5.12 rename)")
    r.add_argument("--expect", help="record 0's expected name")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "run":
        return cmd_run(args)
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
