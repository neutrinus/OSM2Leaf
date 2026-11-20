#!/usr/bin/env python3
"""Run the firmware's ADDRE record reader in PySh4 on a decoded factory record block (M3.13).

The ``REFER001`` field accessor that M3.11c ran on a ``POINT`` page
(``fn 0x003f61bc(r4=db, r5=rec, r6=field) -> pointer``, ``fn 0x003f5d98`` ->
length in 16-bit words; EU2011) is generic: its resolver ``fn 0x003f51e0``
takes the companion slot of ``db`` in the BSS table ``0x00d53500`` as the
file's **field dictionary**, and ``fn 0x003f56bc`` places the record's field
block by the record's type bits.  An ``ADDRE0nn.DAT`` file carries the same
dictionary (the 0x100-byte "schema block" of C-970, three fields:
``area code``, ``street name``, ``dndc-id``).

``run`` lets the firmware bind it:

1. decode the ``.cmp``/``.ind`` pair (``tools/addre.py``), find the dictionary
   with the accessor's own checks (``point_name_accessor.find_dictionary``)
   and require it to be the schema block;
2. map one decoded record block and the dictionary **swapped to native u16**;
   run the populate writer of message type ``0x14e4`` (``fn 0x003fd390``
   EU2011 / ``0x00425564`` US2011) with search type 2 (``ADDRE``, M3.28) in
   the context.  Declared inputs, as in M3.11c: the page-object global that
   the type leaf returns gets ``+0 = OBJ`` and ``+16 = 1``; ``OBJ+20 = PAGE``;
   header-table entry ``+44 = DICT`` (the field ``0x0040e9dc`` copies for this
   type and search type).  The writer itself stores the slots;
3. bind ``OSMDLL!taskIdSelf`` to a stub;
4. for every record: the dispatcher (``fn 0x003f5cdc``) returns record ``n``
   (it selects the walker through the slots the writer filled), and the field
   accessor/length run for every field.  A read watch on the page and the
   dictionary records which instruction reads which byte.

Checks per record: the dispatcher's offset equals the 10-bit framing below;
for ``c0`` the street-name field equals the name that ``addre.parse_record``
(a framing tool that knows nothing of fields) finds, and field 0 equals the
bytes between its name section and the name; for ``c8`` every field is
empty.  ``c1`` records (``addre.py`` cannot frame them) are judged against
the accessor model only.

Framing rule (the walkers ``0x003f5b88``/``0x003f5194``, EU2011): a record is
``2 * (w & 0x3ff)`` bytes for its first big-endian word ``w``
(``0x4e8`` words when ``w & 0xfc00 == 0xfc00``).  ``c1`` is a ``c0`` whose
length has bit 8 set (``L >= 256``).

``--rename OLD=NEW`` rewrites one street name with a **different length**
(field length byte and record length word updated, later records shifted),
the same way a generated card would, and requires the firmware to frame and
read the edited block.

Negative controls in every run: the dictionary left out of the header entry
(slot companion empty), a ``db`` that is in no slot, and the field accessor
on the dictionary itself instead of a record.

Usage::

  addre_reader_l3.py --selftest
  addre_reader_l3.py run IMG --cmp C --build eu2011 [--block N|all|c1] [--rename OLD=NEW]
  addre_reader_l3.py frame REFER001/ADDRE0*.DAT.cmp

Method and results: docs/experiments/EXP-2026-11-20-M3.13-addre-reader-l3.md
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "l3_harness")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import addre  # noqa: E402
import d53500_writer as dw  # noqa: E402
import point_name_accessor as pna  # noqa: E402
import point_walk_l3 as pw  # noqa: E402

MSG_TYPE = 0x14E4        # populate writer case that stores slots +0x14/+0x18/+0x2c
SEARCH_ADDRE = 2         # ctx +124, the opener's ADDRE search type (M3.28, C-4666)
CTX_SEARCH = 124
HDR_DICT = 44            # 0x0040e9dc: type 0x14e4, search type != 1 -> hdr +44
DICT_SPAN = 0x400
WATCH_LIMIT = 4          # records per block that get a read watch

#: EU2011 = head256 ``92aa525d…``, US2011 = us256 ``70d945d8…``.  ``pool``
#: entries ``(va, value, width)`` are checked against the image before a run.
BUILDS = {
    "eu2011": {
        "writer": 0x003FD390, "table": 0x00D53500, "field": 0x003F61BC,
        "field_len": 0x003F5D98, "locator": 0x003F56BC, "count": 0x003F57A8,
        "lengths": 0x003F5E10, "resolver": 0x003F51E0, "dispatch": 0x003F5CDC,
        "walker": 0x003F5B88, "lookup": 0x0040EE4C, "iat_task_id_self": 0x0055D8F0,
        "path_lookup": 0x0040B358,
        "sub": 0x003F5468, "b1_ptr": 0x003F54F4, "b1_words": 0x003F5550,
        "items": 0x003F559C, "item": 0x003F5624,
        "pool": ((0x003FD4AC, MSG_TYPE, 2), (0x003FD4C0, 0x00D53500, 4),
                 (0x003F56B8, 0x003F559C, 4),
                 (0x003F5D80, 0x003F5B88, 4), (0x003F57A0, 0x003F51E0, 4),
                 (0x003F52B4, 0x0055D8F0, 4)),
    },
    "us2011": {
        "writer": 0x00425564, "table": 0x00C81100, "field": 0x0041EB1C,
        "field_len": 0x0041E6F8, "locator": 0x0041E06C, "count": 0x0041E158,
        "lengths": 0x0041E770, "resolver": 0x0041DB90, "dispatch": 0x0041E63C,
        "walker": 0x0041E540, "lookup": 0x00436DD4, "iat_task_id_self": 0x005818D4,
        "sub": 0x0041DE18, "b1_ptr": 0x0041DEA4, "b1_words": 0x0041DF00,
        "items": 0x0041DF4C, "item": 0x0041DFD4,
        "pool": ((0x00425680, MSG_TYPE, 2), (0x00425694, 0x00C81100, 4),
                 (0x0041E068, 0x0041DF4C, 4),
                 (0x0041E6E0, 0x0041E540, 4), (0x0041EB74, 0x0041E06C, 4),
                 (0x0041DC64, 0x005818D4, 4)),
    },
}


# ---------------------------------------------------------------------------
# pure helpers (selftested; the writer-side model of what the firmware reads)


def rec_words(w: int) -> int:
    """Record length in 16-bit words for header word *w* (walker rule)."""
    return 0x4E8 if (w & 0xFC00) == 0xFC00 else (w & 0x3FF)


def frame(page: bytes) -> list[int]:
    """Record start offsets of a decoded block; stops at a zero length."""
    out, p = [], 0
    while p + 1 < len(page):
        n = rec_words((page[p] << 8) | page[p + 1])
        if n == 0:
            break
        out.append(p)
        p += 2 * n
    return out


def field_block(rec: bytes, nfields: int) -> tuple[int, list[int], list[tuple[int, int]]]:
    """(loc, lengths in words, [(start, end)] per field) for a type-6 record.

    ``loc = 2*(rec[2] + rec[3] + 2)`` (``0x003f5774``); the length block holds
    one byte per field, even field in the high byte, ``(n+1)//2`` words
    (``0x003f5e10``); fields follow in order.
    """
    w = (rec[0] << 8) | rec[1]
    if w >> 13 != 6:
        raise ValueError(f"record type {w >> 13} is not 6 (0xc000 class)")
    loc = 2 * (rec[2] + rec[3] + 2)
    nwords = (nfields + 1) // 2
    lens = [rec[loc + i] for i in range(nfields)]
    pos = loc + 2 * nwords
    spans = []
    for ln in lens:
        spans.append((pos, pos + 2 * ln))
        pos += 2 * ln
    return loc, lens, spans


def record_api(rec: bytes) -> dict:
    """What the record leaves return for a type-6 record (writer-side model).

    ``sub`` = ``(w & 0x1800) >> 11`` (``0x003f5468``: 0 for ``c0``/``c1``, 1 for
    ``c8``); block 1 (coordinate id + point tokens) starts at ``rec+4`` and is
    ``rec[2]`` words (``0x003f54f4``/``0x003f5550``); the item block (house
    ranges) starts at ``4 + 2*rec[2]``, is ``rec[3]`` words, and each item is
    ``rec[item]`` words long, its first byte (``0x003f559c`` counts items,
    ``fn 0x003f5624`` returns item ``i``).
    """
    w = (rec[0] << 8) | rec[1]
    items = []
    lo = rec[3]
    p = 4 + 2 * rec[2]
    acc = 0
    while lo and acc < lo:
        items.append(p)
        ln = rec[p] if p < len(rec) else 0
        if ln == 0:
            break
        acc += ln
        p += 2 * ln
    return {"sub": (w & 0x1800) >> 11, "b1_words": rec[2],
            "b1_ptr": 4 if rec[2] else None, "items": items}


def encode_fields(rec: bytes, nfields: int, fields: list[bytes]) -> bytes:
    """Rewrite the field block of *rec*; updates the length bytes and ``L``.

    Each field is NUL-padded to whole words.  The class bits of the header
    word and the pad byte of the length block are kept.
    """
    loc, _lens, _spans = field_block(rec, nfields)
    nwords = (nfields + 1) // 2
    block = bytearray(rec[loc:loc + 2 * nwords])
    body = bytearray()
    for i, f in enumerate(fields):
        if len(f) % 2:
            f = f + b"\x00"
        if len(f) // 2 > 0xFF:
            raise ValueError(f"field {i} longer than 255 words")
        block[i] = len(f) // 2
        body += f
    out = bytearray(rec[:loc]) + block + body
    words = len(out) // 2
    if words > 0x3FF:
        raise ValueError("record longer than 0x3ff words")
    w = ((rec[0] << 8) | rec[1]) & 0xFC00 | words
    struct.pack_into(">H", out, 0, w)
    return bytes(out)


def dictionary_names(blob: bytes, c: int) -> list[bytes]:
    """Field names of the dictionary at *c* (``u8 len`` at entry +14, text at +16)."""
    d = c + 2 * pna.be16(blob, c + 2)
    n = pna.be16(blob, d + 26)
    e = d + 2 * pna.be16(blob, d + 24)
    names = []
    for _ in range(n):
        ln = blob[e + 14]
        names.append(bytes(blob[e + 16:e + 16 + ln]))
        e = d + 2 * pna.be16(blob, e)
    return names


def strict_dictionaries(blob: bytes) -> tuple[int, list[tuple[int, int, int]]]:
    """(raw candidates, strict ones): the accessor's checks for fields 0..1,
    then every one of the ``n`` entries chained with ids ``0..n-1`` and a
    printable ASCII name (``n <= 64``)."""
    raw = pna.find_dictionary(blob, field=1)
    strict = []
    for c, d, n in raw:
        if n > 64:
            continue
        try:
            e = d + 2 * pna.be16(blob, d + 24)
            good = True
            for i in range(n):
                if pna.be16(blob, e + 12) != i:
                    good = False
                    break
                e = d + 2 * pna.be16(blob, e)
            names = dictionary_names(blob, c) if good else []
        except (IndexError, TypeError):
            good, names = False, []
        if good and all(nm and all(0x20 <= ch < 0x7F for ch in nm) for nm in names):
            strict.append((c, d, n))
    return len(raw), strict


def dictionary_words(blob: bytes, c: int) -> list[tuple[int, int]]:
    """``(u16 +4, u16 +6)`` of every dictionary entry, in field order."""
    d = c + 2 * pna.be16(blob, c + 2)
    n = pna.be16(blob, d + 26)
    e = d + 2 * pna.be16(blob, d + 24)
    out = []
    for _ in range(n):
        out.append((pna.be16(blob, e + 4), pna.be16(blob, e + 6)))
        e = d + 2 * pna.be16(blob, e)
    return out


def judge(rec: bytes, row: dict, nfields: int) -> str:
    """Compare the firmware's answers for one record with the two references."""
    if row.get("fault"):
        return "fault"
    if row["disp"] != row["offset"]:
        return "frame"
    loc, lens, spans = field_block(rec, nfields)
    got = row["fields"]
    if any(g is None for g in got):
        return "no-pointer"
    for (start, ln), (s, e), want_len in zip(got, spans, lens):
        if start != s or ln != want_len:
            return "model"
    if "api" in row and row["api"] != record_api(rec):
        return "api"
    if (rec[0] & 0xF8) == 0xC8:
        if any(ln for _s, ln in got):
            return "c8-named"
        if rec[0] == 0xC8 and "api" in row:
            try:
                p = addre.parse_record(rec)
            except addre.AddreError:
                return "parse"
            if row["api"]["items"] != [r["pos"] for r in p["ranges"]]:
                return "ranges"
        return "ok"
    if rec[0] in (0xC0,):
        try:
            p = addre.parse_record(rec)
        except addre.AddreError:
            return "parse"
        street = rec[got[1][0]:got[1][0] + 2 * got[1][1]].rstrip(b"\x00")
        if p["name"] is None or street != p["name"].rstrip(b"\x00"):
            return "name"
        area = rec[got[0][0]:got[0][0] + 2 * got[0][1]]
        if p.get("name_header") is not None and got[2][1] == 0 and area != p["name_header"]:
            return "area"
        if "api" in row and row["api"]["items"] != [r["pos"] for r in p["ranges"]]:
            return "ranges"
        return "ok"
    return "ok-model"       # c1: no independent framing tool


# ---------------------------------------------------------------------------
# the run


def check_build(data: bytes, cfg: dict) -> None:
    mem = dw.sec0_mem(data)
    for va, want, width in cfg["pool"]:
        got = mem.u16(va) if width == 2 else mem.u32(va)
        if got != want:
            raise dw.Mismatch(f"pool {va:#010x} holds {got:#x}, not {want:#x}: wrong build?")


def build_context(data: bytes, build: str, native_page: bytes, dict_native: bytes | None,
                  search: int = SEARCH_ADDRE):
    """Engine with the slot table the 0x14e4 writer leaves; dict_native=None
    keeps the dictionary out of the header entry (negative control)."""
    cfg = BUILDS[build]
    wcfg = dict(dw.BUILDS[build], type_leaf=dw.BUILDS[build]["type_leaf"])
    glob = dw.type_global(data, wcfg, MSG_TYPE)
    eng = dw.new_engine(data)
    hdr = eng.call(cfg["lookup"], [0, 0])
    eng.map("ctx", dw.CTX_VA, bytearray(0x200), "rw")
    eng.map("obj", dw.OBJ_VA, bytearray(0x100), "rw")
    eng.map("page", dw.PAGE_VA, bytearray(native_page) + bytearray(0x40), "rw")
    eng.map("dict", pna.DICT_VA, bytearray(dict_native or b"\0" * DICT_SPAN), "rw")
    eng.map("stub", pna.STUB_VA, bytearray(0x10), "rx")
    eng.on_exec(pna.STUB_VA, lambda _e, _va: 1)          # OSMDLL!taskIdSelf
    dw.put32(eng, cfg["iat_task_id_self"], pna.STUB_VA)
    dw.put32(eng, dw.CTX_VA + dw.CTX_TYPE, MSG_TYPE)
    dw.put32(eng, dw.CTX_VA + CTX_SEARCH, search)
    dw.put32(eng, glob, dw.OBJ_VA)
    dw.put32(eng, glob + 16, 1)
    dw.put32(eng, dw.OBJ_VA + 20, dw.PAGE_VA)
    if dict_native is not None:
        dw.put32(eng, hdr + HDR_DICT, pna.DICT_VA)
    table = cfg["table"]
    eng.watch(table, table + dw.TABLE_SPAN, kind="w", name="table-w")
    eng.arm_watch()
    eng.call(cfg["writer"], [0, dw.CTX_VA, 0, dw.STACK_VA + 0x100])
    writes = [(pc, off, val) for pc, off, _s, val in dw.slot_writes(eng, table)]
    eng.disarm_watch()
    return eng, hdr, glob, writes


def call(eng, va, args):
    try:
        return eng.call(va, args), None
    except Exception as exc:  # noqa: BLE001
        return None, exc


def run_block(eng, cfg: dict, page: bytes, nfields: int, watch: int):
    """Rows for every record; read hits for the first *watch* records."""
    offs = frame(page)
    rows, hits = [], []
    eng.watch(dw.PAGE_VA, dw.PAGE_VA + len(page), kind="r", name="page-r")
    eng.watch(pna.DICT_VA, pna.DICT_VA + DICT_SPAN, kind="r", name="dict-r")
    for n, off in enumerate(offs):
        armed = n < watch
        if armed:
            eng.arm_watch()
            before = len(eng.watch_hits())
        rec_va = dw.PAGE_VA + off
        disp, fault = call(eng, cfg["dispatch"], [dw.PAGE_VA, n])
        fields = []
        for f in range(nfields):
            ptr, f1 = call(eng, cfg["field"], [dw.PAGE_VA, rec_va, f])
            ln, f2 = call(eng, cfg["field_len"], [dw.PAGE_VA, rec_va, f])
            fault = fault or f1 or f2
            fields.append(None if ptr in (None, 0, 0xFFFFFFFF) or ln is None
                          else (ptr - rec_va, ln))
        api = {}
        for key in ("sub", "b1_words", "b1_ptr", "items"):
            v, fx = call(eng, cfg[key], [dw.PAGE_VA, rec_va])
            fault = fault or fx
            api[key] = v
        if api["b1_ptr"] is not None:
            api["b1_ptr"] = None if api["b1_ptr"] == 0 else api["b1_ptr"] - rec_va
        offs_i = []
        for i in range(api["items"] or 0):
            v, fx = call(eng, cfg["item"], [dw.PAGE_VA, rec_va, i])
            fault = fault or fx
            offs_i.append(None if not v else v - rec_va)
        api["items"] = offs_i
        if armed:
            for h in eng.watch_hits()[before:]:
                if h.kind != "r":
                    continue
                if h.name == "page-r":
                    rel = h.va - dw.PAGE_VA - off
                    hits.append((n, f"rec {page[off]:02x}", h.pc, rel, h.size))
                else:
                    hits.append((n, "dict", h.pc, h.va - pna.DICT_VA, h.size))
            eng.disarm_watch()
        rows.append({"n": n, "offset": off, "tag": page[off],
                     "disp": None if disp is None else disp - dw.PAGE_VA,
                     "fields": fields, "api": api, "fault": fault})
    return offs, rows, hits


def rename(page: bytes, nfields: int, old: bytes, new: bytes) -> tuple[bytes, int]:
    """Different-length street rename in the first c0 record that holds *old*."""
    out = bytearray()
    done = -1
    for i, off in enumerate(frame(page)):
        rec = page[off:off + 2 * rec_words((page[off] << 8) | page[off + 1])]
        if done < 0 and (rec[0] & 0xF8) == 0xC0:
            _loc, _lens, spans = field_block(rec, nfields)
            fields = [rec[s:e] for s, e in spans]
            if fields[1].rstrip(b"\x00") == old:
                fields[1] = new
                rec = encode_fields(rec, nfields, fields)
                done = i
        out += rec
    if done < 0:
        raise SystemExit(f"rename: {old!r} is not a street name in this block")
    return bytes(out), done


def pick_blocks(sec: dict, spec: str) -> list[int]:
    nb = len(sec["records"])
    if spec == "all":
        return list(range(nb))
    if spec == "c1":
        for i, (_s, _e, d) in enumerate(sec["records"]):
            if any(d[o] in (0xC1, 0xC9) for o in frame(d)):
                return [i]
        raise SystemExit("no block holds a c1 record")
    return [int(x, 0) for x in spec.split(",")]


def cmd_run(args) -> int:
    cfg = BUILDS[args.build]
    data = pw.load_image(args.image)
    check_build(data, cfg)
    blob = addre.load_blob(Path(args.cmp))
    sec = addre.sections(blob)
    nraw, hits = strict_dictionaries(blob)
    print(f"build {args.build}: writer={cfg['writer']:#010x} type={MSG_TYPE:#x} search={SEARCH_ADDRE} "
          f"field={cfg['field']:#010x} length={cfg['field_len']:#010x} "
          f"locator={cfg['locator']:#010x} dispatch={cfg['dispatch']:#010x}")
    print(f"file {Path(args.cmp).name}: {len(blob)} B decoded, schema block {sec['schema']:#x}, "
          f"{len(sec['records'])} record blocks; dictionary candidates={nraw} strict={len(hits)} "
          + " ".join(f"C={c:#x}/D={d:#x}/n={n}" for c, d, n in hits))
    if len(hits) != 1 or hits[0][0] != sec["schema"]:
        print("BLOCKED: the dictionary is not unique or is not the schema block")
        return 4
    c, _d, nfields = hits[0]
    names = dictionary_names(blob, c)
    words = dictionary_words(blob, c)
    print("fields: " + ", ".join(f"{i}={n.decode('latin-1')!r}(+4={a:#x},+6={b:#06x})"
                                 for i, (n, (a, b)) in enumerate(zip(names, words))))
    dict_native = pw.swap16(blob[c:c + DICT_SPAN])
    total: dict[str, int] = {}
    all_hits = []
    ok = True
    first_c0 = None
    for b in pick_blocks(sec, args.block):
        page = sec["records"][b][2]
        renamed = None
        if args.rename:
            old, new = (s.encode("latin-1") for s in args.rename.split("=", 1))
            page, renamed = rename(page, nfields, old, new)
            print(f"rename {old!r} -> {new!r} in block {b} record {renamed} "
                  f"(block {len(sec['records'][b][2])} -> {len(page)} B)")
        native = pw.swap16(page)
        eng, hdr, glob, writes = build_context(data, args.build, native, dict_native)
        if b == pick_blocks(sec, args.block)[0]:
            print(f"context: page-object global={glob:#010x} header entry={hdr:#010x}")
            for pc, off, val in writes:
                print(f"  writer store pc={pc:#010x} table+{off:#04x} = {val:#010x}")
        offs, rows, rhits = run_block(eng, cfg, page, nfields, WATCH_LIMIT if b == 0 or args.rename else 0)
        all_hits += [(b,) + h for h in rhits]
        verdicts: dict[str, int] = {}
        tags: dict[int, int] = {}
        for row in rows:
            rec = page[row["offset"]:row["offset"] + 2 * rec_words((page[row["offset"]] << 8) | page[row["offset"] + 1])]
            row["verdict"] = judge(rec, row, nfields)
            verdicts[row["verdict"]] = verdicts.get(row["verdict"], 0) + 1
            tags[row["tag"]] = tags.get(row["tag"], 0) + 1
            if first_c0 is None and row["tag"] == 0xC0 and row["verdict"] == "ok":
                first_c0 = (b, row, rec)
        end_ok = offs and offs[-1] + 2 * rec_words((page[offs[-1]] << 8) | page[offs[-1] + 1]) == len(page)
        for k, v in verdicts.items():
            total[k] = total.get(k, 0) + v
        print(f"block {b}: {len(page)} B, records={len(rows)} framing-ends-at-block-end={bool(end_ok)} "
              f"tags={{{', '.join(f'{t:#04x}:{v}' for t, v in sorted(tags.items()))}}} "
              + " ".join(f"{k}={v}" for k, v in sorted(verdicts.items())))
        ok = ok and bool(end_ok)
        shown = [r for r in rows if r["n"] < args.show or r["n"] == renamed or r["tag"] in (0xC1, 0xC9)]
        for row in shown[:args.show + 3]:
            off = row["offset"]
            desc = []
            for f, fv in enumerate(row["fields"]):
                if fv is None:
                    desc.append(f"f{f}=-")
                    continue
                s, ln = fv
                desc.append(f"f{f}=+{s:#x}/{ln}w {page[off + s:off + s + 2 * ln]!r}")
            a = row["api"]
            desc.append(f"sub={a['sub']} block1=+{a['b1_ptr'] or 0:#x}/{a['b1_words']}w items="
                        + ",".join(f"+{i:#x}" for i in a["items"] if i is not None))
            print(f"  rec {row['n']} @{off:#06x} tag={row['tag']:#04x} disp=+{row['disp']:#x} "
                  + " ".join(desc) + f" -> {row['verdict']}")
        if renamed is not None:
            row = rows[renamed]
            s, ln = row["fields"][1]
            got = page[row["offset"] + s:row["offset"] + s + 2 * ln].rstrip(b"\x00")
            print(f"rename check: record {renamed} street = {got!r}")
            ok = ok and got == new and row["verdict"] in ("ok", "ok-model")
    print("records: " + " ".join(f"{k}={v}" for k, v in sorted(total.items()))
          + f" of {sum(total.values())}")
    good = {"ok", "ok-model"}
    ok = ok and all(k in good for k in total)
    # read map (first records of the first watched block)
    if all_hits:
        agg: dict[tuple, set] = {}
        for _b, n, region, pc, rel, size in all_hits:
            agg.setdefault((region, pc, size), set()).add(rel)
        print("reads (region pc width: offsets, first watched records):")
        for (region, pc, size), rels in sorted(agg.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            rs = sorted(rels)
            show = ",".join(f"{r:+#x}" for r in rs[:8]) + ("…" if len(rs) > 8 else "")
            print(f"  {region:6s} pc={pc:#010x} w={size}: {show}")
    # negative controls on block 0
    page0 = sec["records"][pick_blocks(sec, args.block)[0]][2]
    off0 = frame(page0)[0]
    eng0, _h, _g, w0 = build_context(data, args.build, pw.swap16(page0), None)
    p0, f0 = call(eng0, cfg["field"], [dw.PAGE_VA, dw.PAGE_VA + off0, 1])
    print(f"negative (no dictionary in the header entry): street ptr="
          + ("None" if p0 is None else f"{p0:#x}") + (f" fault={type(f0).__name__}" if f0 else ""))
    engp, _h, _g, _w = build_context(data, args.build, pw.swap16(page0), dict_native)
    p1, f1 = call(engp, cfg["field"], [dw.PAGE_VA + 2, dw.PAGE_VA + off0, 1])
    print("negative (db in no slot): street ptr="
          + ("None" if p1 is None else f"{p1:#x}") + (f" fault={type(f1).__name__}" if f1 else ""))
    p2, f2 = call(engp, cfg["field"], [dw.PAGE_VA, pna.DICT_VA, 1])
    print("negative (rec = the dictionary, header 0xffff): street ptr="
          + ("None" if p2 is None else f"{p2:#x}") + (f" fault={type(f2).__name__}" if f2 else ""))
    neg_ok = all(p in (None, 0, 0xFFFFFFFF) for p in (p0, p1, p2))
    # the locator alone, and the pre-M3.13 candidate 0x0040b358, on record 0
    loc, fl = call(engp, cfg["locator"], [dw.PAGE_VA, dw.PAGE_VA + off0, 1])
    want_loc = field_block(page0[off0:], nfields)[0]
    print(f"locator {cfg['locator']:#010x}(db, rec0, 1) = "
          + ("None" if loc is None else f"rec+{loc - dw.PAGE_VA - off0:#x}")
          + f" (field-length block at rec+{want_loc:#x})" + (f" fault={type(fl).__name__}" if fl else ""))
    ok = ok and loc is not None and loc - dw.PAGE_VA - off0 == want_loc
    if cfg.get("path_lookup"):
        engp.watch(dw.PAGE_VA, dw.PAGE_VA + len(page0), kind="r", name="page-r")
        engp.arm_watch()
        before = len(engp.watch_hits())
        r, fx = call(engp, cfg["path_lookup"], [dw.PAGE_VA + off0, dw.PAGE_VA + off0])
        reads = [h for h in engp.watch_hits()[before:] if h.kind == "r"]
        engp.disarm_watch()
        pcs = sorted({h.pc for h in reads})
        print(f"probe {cfg['path_lookup']:#010x}(rec0, rec0): r0="
              + ("None" if r is None else f"{r:#x}") + f" page reads={len(reads)} at "
              + (",".join(f"{p:#010x}" for p in pcs) or "-")
              + (f" fault={type(fx).__name__}: {fx}" if fx else ""))
    ok = ok and neg_ok
    if args.expect and first_c0 is not None:
        _b, row, rec = first_c0
        s, ln = row["fields"][1]
        got = rec[s:s + 2 * ln].rstrip(b"\x00")
        want = args.expect.encode("latin-1")
        print(f"first c0 street: {got!r} (expect {want!r})")
        ok = ok and got == want
    print("result:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def cmd_frame(args) -> int:
    """Pure-Python census of the walker's 10-bit framing over whole shards."""
    bad_total = 0
    max_match = 0
    for path in args.files:
        blob = addre.load_blob(Path(path))
        sec = addre.sections(blob)
        _nraw, dicts = strict_dictionaries(blob)
        nf = dicts[0][2] if len(dicts) == 1 and dicts[0][0] == sec["schema"] else 0
        dmax = [a for a, _b in dictionary_words(blob, dicts[0][0])] if nf else []
        maxlen = [0] * nf
        tags: dict[int, int] = {}
        exact = 0
        long_words = []
        for _s, _e, d in sec["records"]:
            offs = frame(d)
            for o in offs:
                tags[d[o]] = tags.get(d[o], 0) + 1
                if d[o] in (0xC1, 0xC9):
                    long_words.append(rec_words((d[o] << 8) | d[o + 1]))
                if nf and d[o] >> 5 == 6:
                    for i, ln in enumerate(field_block(d[o:o + 2 * rec_words((d[o] << 8) | d[o + 1])], nf)[1]):
                        maxlen[i] = max(maxlen[i], ln)
            if offs and offs[-1] + 2 * rec_words((d[offs[-1]] << 8) | d[offs[-1] + 1]) == len(d) \
                    and all((d[o] & 0xF0) == 0xC0 for o in offs):
                exact += 1
        nb = len(sec["records"])
        bad_total += nb - exact
        max_match += bool(nf) and maxlen == dmax
        lw = f" long L={min(long_words)}..{max(long_words)}" if long_words else ""
        print(f"{Path(path).name}: blocks={nb} exact-end={exact} "
              f"tags={{{', '.join(f'{t:#04x}:{v}' for t, v in sorted(tags.items()))}}}{lw} "
              f"field-max-words={maxlen} dict+4={dmax}")
    print(f"blocks not framed to their end: {bad_total}")
    print(f"dictionary entry +4 == largest field length (words), every field: {max_match} of {len(args.files)} files")
    return 0 if bad_total == 0 else 1


# ---------------------------------------------------------------------------
# self-test (synthetic; no vendor bytes)


def _synthetic_record(tag: int, street: bytes, area: bytes = b"\x00\x00\x00\x03\x00\x00") -> bytes:
    prefix = bytes([0, 0, 0x06, 0x00]) + b"\x9f\xec\xce\xcd" + b"\x02\x40\x14\x9b\x03\x40\x14\xa0"
    lenblk = bytes([0, 0, 0, 0xFF])
    rec = prefix + lenblk
    rec = bytes([tag, len(rec) // 2]) + rec[2:]
    if tag == 0xC8:
        return rec
    return encode_fields(rec, 3, [area, street, b""])


def _named_dictionary(names: list[bytes]) -> bytes:
    """Synthetic dictionary in the factory shape: ``ff ff`` + D offset, a
    32-byte D header, then entries ``(next, ..., id@+12, len@+14, name@+16)``."""
    c = bytearray(b"\xff\xff" + struct.pack(">H", 4)) + bytearray(4)
    d = bytearray(32)
    struct.pack_into(">H", d, 24, 16)
    struct.pack_into(">H", d, 26, len(names))
    entries = bytearray()
    pos = 32
    for i, nm in enumerate(names):
        size = 16 + len(nm) + (len(nm) % 2)
        e = bytearray(size)
        struct.pack_into(">H", e, 0, (pos + size) // 2)
        struct.pack_into(">H", e, 12, i)
        e[14] = len(nm)
        e[16:16 + len(nm)] = nm
        entries += e
        pos += size
    return bytes(c + d + entries + bytes(16))


def selftest() -> int:
    fails = 0

    def check(name, cond):
        nonlocal fails
        print("%-62s %s" % (name, "ok" if cond else "FAIL"))
        fails += not cond

    r0 = _synthetic_record(0xC0, b"AVINGUDA CARLEMANY")
    loc, lens, spans = field_block(r0, 3)
    check("field block: placed at 2*(rec[2]+rec[3]+2)", loc == 16 and lens == [3, 9, 0])
    check("field block: street span", r0[spans[1][0]:spans[1][1]] == b"AVINGUDA CARLEMANY")
    check("encode: header word = class | words", r0[0] == 0xC0 and r0[1] * 2 == len(r0))
    r8 = _synthetic_record(0xC8, b"")
    check("c8: every field empty", field_block(r8, 3)[1] == [0, 0, 0])
    page = r0 + r8 + r0 + b"\x00\x00"
    check("frame: three records, stop at a zero word", frame(page) == [0, len(r0), len(r0) + len(r8)])
    long = encode_fields(r0, 3, [b"\x00" * 6, b"X" * 510, b""])
    check("frame: L >= 256 sets bit 8 -> tag c1", long[0] == 0xC1 and frame(long + r8) == [0, len(long)])
    check("rec_words: 0xfc00 escape", rec_words(0xFC12) == 0x4E8)
    odd = encode_fields(r0, 3, [b"\x00" * 6, b"ODD", b""])
    check("encode: odd name NUL-padded, 2 words", field_block(odd, 3)[1][1] == 2)
    try:
        field_block(b"\x60\x10" + b"\x00" * 30, 3)
        check("field block negative: type 3 (POINT 0x60) is refused", False)
    except ValueError:
        check("field block negative: type 3 (POINT 0x60) is refused", True)
    row = {"offset": 0, "disp": 0, "fault": None,
           "fields": [(s, ln) for (s, _e), ln in zip(spans, lens)]}
    check("judge: model and parse_record agree -> ok", judge(r0, row, 3) == "ok")
    bad = dict(row, fields=[row["fields"][0], (spans[1][0] + 2, 9), row["fields"][2]])
    check("judge negative: a shifted street pointer is a model error", judge(r0, bad, 3) == "model")
    check("judge negative: a wrong dispatcher offset is a frame error",
          judge(r0, dict(row, disp=4), 3) == "frame")
    api = record_api(_synthetic_record(0xC0, b"X"))
    check("record api: block 1 at +4, 6 words, no items", api == {
        "sub": 0, "b1_words": 6, "b1_ptr": 4, "items": []})
    rr = bytearray(_synthetic_record(0xC8, b""))
    rr[3] = 13
    rr = bytes(rr[:16]) + bytes([6, 0x54, 0, 0]) + b":13:;:5:" + bytes([7, 0x58, 0, 0]) + b":19:;:15:\x00" + bytes(rr[16:])
    check("record api: two items, lengths from their first byte", record_api(rr)["items"] == [16, 28])
    check("record api: c8 sub bits = 1", record_api(rr)["sub"] == 1)
    d = pna._synthetic_dictionary(3)
    check("dictionary: 3-field block passes the accessor checks",
          [h[2] for h in pna.find_dictionary(b"\x00" * 8 + d, field=1)] == [3])
    named = _named_dictionary([b"area code", b"street name", b"dndc-id"])
    check("strict: printable names keep the block",
          [h[0] for h in strict_dictionaries(b"\x00" * 8 + named)[1]] == [8])
    check("dictionary names: read back in field order",
          dictionary_names(named, 0) == [b"area code", b"street name", b"dndc-id"])
    check("strict negative: unnamed entries are dropped",
          strict_dictionaries(b"\x00" * 8 + d)[1] == [])
    print("selftest:", "PASS" if not fails else f"FAIL ({fails})")
    return 0 if not fails else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("image")
    r.add_argument("--cmp", required=True, help="ADDRE0nn.DAT.cmp (the .ind beside it)")
    r.add_argument("--build", choices=tuple(BUILDS), default="eu2011")
    r.add_argument("--block", default="0", help="record block index, list, 'all' or 'c1'")
    r.add_argument("--show", type=int, default=3)
    r.add_argument("--rename", help="OLD=NEW street rename (any length)")
    r.add_argument("--expect", help="the first c0 record's expected street name")
    f = sub.add_parser("frame", help="10-bit framing census over whole shards (no emulation)")
    f.add_argument("files", nargs="+")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "frame":
        return cmd_frame(args)
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
