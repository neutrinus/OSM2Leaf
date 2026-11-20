#!/usr/bin/env python3
"""datask_req_l3.py - ask the firmware's data-access task for map data by kind.

`datask_l3.py` (M3.25) mounts the EU 2011 card with the data-access task and
the map-file task of `Navi.exe` in one PySh4 machine.  This tool then plays a
client of that task: it sends the request message `0x14b5` (sub 2) that the
renderer (`MAP_DATA READ`, kind 4), the router (`RGD_DATA READ`, kind 0x40)
and the route path finder (`RPF_PreMap_start`, kinds 8 and 0x10) send, carries
the messages until both tasks are idle, and prints the `0x14b6` replies: per
list entry the status, the mesh id the task used, the four data pointers, the
tile record the map-file task read for it, and where each pointer lands inside
that record (decompressed, as a `u16` word index).

So it answers "which tile section does request kind K fetch, and which word of
the record does the reply point at" with the firmware's own lookup, not from
names (M4.40).

Declared model (the only one added to `datask_l3.py`'s): the client task is
registered by writing one row of the client table (`CLIENTS`, 24 rows of 64
bytes: task id, sub id `0xff`, kind mask) instead of running a registration
message; `--no-register` leaves the table alone (the request is then refused,
status 9: the negative control).

No vendor byte is stored here: the tool reads the image and card it is given.

Usage:
  datask_req_l3.py --selftest
  datask_req_l3.py kinds IMG256
  datask_req_l3.py gate --tile TILE.DAT --section 2 --section 4
  datask_req_l3.py request IMG256 --card-image CARD.img --position LAT,LON
                   MESH:DIVID:KIND [...] [--no-register] [--json OUT]

Exit codes: request: 0 every request got a reply, 1 a request got none;
2 usage or missing input; 3 BLOCKED (missing model, engine stop).
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE / "l3_harness"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# --------------------------------------------------------------------------
# EU2011 build A `Navi.exe` (docs/format/map-tiles.md, M4.40).  Data
# addresses are written short on purpose: fn_audit reads eight hex digits as a
# function citation.
REQ_EU2011 = {
    "build": "EU2011",
    "kind_table": (0x179 << 12) + 0xB20,   # 19 rows {u32 group mask, u32 kind mask, u32 section index}
    "kind_rows": 19,
    "clients": (0xD98 << 12) + 0xFE0,      # 24 rows of 64 B: +0 task id, +4 sub id, +12 kind mask
    "client_rows": 24,
    "req_msg": 0x14B5,
    "reply_msg": 0x14B6,
}
CLIENT_TASK = 0x77         # any id the two tasks do not use (datask_l3: 2 and 0x10)
LIST_BYTES = 0x2004        # the list size 0x004066ac copies (C-5643)
STATUS = {1: "data", 2: "pending (a read was queued)", 3: "refused", 4: "no data", 9: "refused (message status)"}


# --------------------------------------------------------------------------
# pure helpers (host side; covered by --selftest without any image)

def decode_kinds(blob: bytes, rows: int) -> list[tuple[int, int, int]]:
    """Rows ``(group mask, kind mask, section index)`` up to the first empty row."""
    out = []
    for i in range(rows):
        g, k, v = struct.unpack_from("<III", blob, 12 * i)
        if g == 0:
            break
        out.append((g, k, v))
    return out


def kind_section(table, group: int, kind: int) -> int | None:
    """The firmware's lookup (``0x00408f9c``): first row whose masks both hit."""
    for g, k, v in table:
        if g & group and k & kind:
            return v
    return None


def pack_request(task: int, kind: int, lst: int) -> bytes:
    """Message ``0x14b5`` sub 2 as ``0x004266ec``/``0x00425f40`` build it."""
    msg = bytearray(32)
    struct.pack_into("<HHIIII", msg, 8, REQ_EU2011["req_msg"], 2, task, kind, lst, 2)
    return bytes(msg)


def pack_list(reqs: list[tuple[int, int]]) -> bytes:
    """Request list: ``u16`` count at +0, 32-byte entries from +4; the
    requester writes mesh id at list ``+16 + 32 i`` and DIVID at ``+14 + 32 i``
    (``0x004266ec``), i.e. entry ``+12`` and ``+10``."""
    b = bytearray(LIST_BYTES)
    struct.pack_into("<H", b, 0, len(reqs))
    for i, (mesh, divid) in enumerate(reqs):
        struct.pack_into("<I", b, 16 + 32 * i, mesh)
        struct.pack_into("<H", b, 14 + 32 * i, divid)
    return bytes(b)


def decode_entry(raw: bytes) -> dict:
    """One 32-byte reply entry (list ``+4 + 32 i``)."""
    status, = struct.unpack_from("<H", raw, 0)
    kind, word8, mesh = struct.unpack_from("<III", raw, 4)
    ptrs = list(struct.unpack_from("<4I", raw, 16))
    return {"status": status, "status_text": STATUS.get(status, "?"), "kind": kind,
            "word8": word8, "divid": struct.unpack_from("<H", raw, 10)[0], "mesh": mesh,
            "ptrs": ptrs}


def native(b: bytes) -> bytes:
    """File order (big-endian u16) -> the swapped copy the read layer delivers (C-4641)."""
    b = bytes(b) + (b"\0" if len(b) % 2 else b"")
    out = bytearray(len(b))
    out[0::2], out[1::2] = b[1::2], b[0::2]
    return bytes(out)


def locate(guest: bytes, plain: bytes) -> int | None:
    """Byte offset of the guest bytes inside the record's native copy, or None.

    *guest* is read at a reply pointer.  A pointer near the end of a record
    reads past it, so shorter prefixes (down to 8 bytes) are tried; the match
    must be unique at the length that finds it."""
    nat = native(plain)
    n = len(guest)
    while n >= 8:
        g = guest[:n]
        at = nat.find(g)
        if at >= 0:
            return at if nat.find(g, at + 1) < 0 else None
        n //= 2
    return None


def plain_of(raw: bytes) -> bytes:
    """A record as the map-file task read it: one zlib stream, or stored."""
    if len(raw) >= 2 and (raw[0] & 0x0F) == 8 and ((raw[0] << 8) | raw[1]) % 31 == 0:
        d = zlib.decompressobj()
        return d.decompress(raw)
    return raw


def streams_of(raw: bytes) -> list[tuple[int, bytes]]:
    """Every whole zlib stream in a read, at 2-byte steps: ``[(offset, plain)]``.

    One read can hold several records (a wide directory row keeps the even,
    sub-record and odd streams of a column together, M5.53); a read that is
    one stream gives one row, a stored read gives ``[(0, raw)]``."""
    out, at = [], 0
    while at + 2 <= len(raw):
        if (raw[at] & 0x0F) == 8 and ((raw[at] << 8) | raw[at + 1]) % 31 == 0:
            d = zlib.decompressobj()
            try:
                plain = d.decompress(raw[at:])
            except zlib.error:
                plain = None
            if plain is not None and d.eof:
                out.append((at, plain))
                at += len(raw) - at - len(d.unused_data)
                at += at & 1
                continue
        at += 2
    return out or [(0, raw)]


def unit_pairs(plain: bytes) -> list[tuple[int, int]]:
    """Section-2 record header: five ``(u32 word offset, u32 word count)``
    unit pairs from byte 12 (``clarion_rd.parse_record``); ``0xffffffff`` = absent."""
    if len(plain) < 52:
        return []
    return [struct.unpack_from(">II", plain, 12 + 8 * i) for i in range(5)]


def unit_at(pairs, word: int) -> int | None:
    """Index of the unit that starts at *word*, or None."""
    for i, (off, _n) in enumerate(pairs):
        if off != 0xFFFFFFFF and off == word:
            return i
    return None


HEAD_BYTES = 0x1000         # level table (0x1ac) and section table (0x800) of a tile


def section_starts(head: bytes) -> list[tuple[int, int]]:
    """``[(start, section id)]`` sorted by start: the tile's section table
    (``tile_scan.SECT_OFF``) zipped with its level table, as ``TileScan._dirs``
    and ``diff_years_tiles`` frame a section (span ``[taddr, next taddr)``)."""
    ze0 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ze0-viewer", "tools_ze0")
    if ze0 not in sys.path:
        sys.path.insert(0, ze0)
    import tile_scan as TS
    ids = [sid for sid, _lv in TS.TileScan(head).sections()]
    starts, p = [], TS.SECT_OFF
    while p + 6 <= len(head):
        a, _c = struct.unpack_from(">IH", head, p)
        p += 6
        if a == 0xFFFFFFFF:
            break
        starts.append(TS.addr_of(a))
    return sorted(zip(starts, ids))


def section_at(starts, pos: int) -> int | None:
    """Section whose span ``[taddr, next taddr)`` holds file position *pos*."""
    got = None
    for start, sid in starts:
        if pos >= start:
            got = sid
    return got


def section_of(sid: int | None, plain: bytes) -> str:
    """Label: the section whose span the read position falls in; header word 2
    (map-tiles.md: 0x00fa section 1, 0x0009 section 4) is shown as a cross-check."""
    w2 = struct.unpack_from(">H", plain, 4)[0] if len(plain) >= 6 else None
    name = "section %s" % sid if sid is not None else "section ?"
    return name + ("" if w2 is None else " (w2=%#06x)" % w2)


# --------------------------------------------------------------------------
# the run

def kinds_from_image(image: str):
    import vcard_l3 as V
    m = V.load_machine(image, V.Card(V.MemorySource({})))
    b = REQ_EU2011
    return decode_kinds(bytes(m.eng.read_mem(b["kind_table"], 12 * b["kind_rows"])), b["kind_rows"])


class Client:
    """A mounted data-access task plus one registered client."""

    def __init__(self, image: str, card, position, register: bool = True):
        import datask_l3 as D
        self.D = D
        self.t = D.DataTask(image, card, position=position)
        self.mount_end = self.t.run(0, False)
        self.m = self.t.m
        self.card = card
        self.registered = False
        if register:
            base = REQ_EU2011["clients"]
            for i in range(REQ_EU2011["client_rows"]):
                if self.m.u32(base + 64 * i) == 0:
                    self.m.put(base + 64 * i, struct.pack("<II", CLIENT_TASK, 0xFF))
                    self.m.put(base + 64 * i + 12, struct.pack("<I", 0xFFFFFFFF))
                    self.registered = i
                    break

    def carry(self) -> tuple[list, list]:
        """datask_l3.DataTask.run's loop without the ready message: returns
        (messages to other tasks, read rows)."""
        t, m, D = self.t, self.m, self.D
        out, rows = [], []
        while True:
            if t.routed >= len(m.messages):
                before = len(m.messages)
                t.map_task_turn()
                if len(m.messages) == before:
                    return out, rows
                continue
            x = m.messages[t.routed]
            t.routed += 1
            if x["kind"] != "send":
                continue
            body = bytes.fromhex(x["body"])
            mid, sub = struct.unpack_from("<HH", body, 8)
            if x["task"] == D.MAP_TASK:
                t.map_task_turn()
            elif x["task"] == D.DA_TASK and mid == t.b["done_msg"]:
                rows.append(t.complete(body, False))
            elif x["task"] == D.DA_TASK:
                t.deliver(body)
            else:
                out.append({"task": x["task"], "id": mid, "sub": sub, "body": body})

    def starts(self, row: dict) -> list[tuple[int, int]]:
        """Section spans of the tile *row* read, from its first HEAD_BYTES (cached)."""
        cache = self.__dict__.setdefault("_starts", {})
        if row["file"] not in cache:
            head = self.read_raw({"file": row["file"], "pos": 0, "length": HEAD_BYTES})
            cache[row["file"]] = section_starts(head) if head else []
        return cache[row["file"]]

    def read_raw(self, row: dict) -> bytes | None:
        entry = self.card.resolve(row["file"].replace("/", "\\"))
        if entry is None:
            return None
        return self.card._read(entry, row["pos"], row["length"])

    def request(self, mesh: int, divid: int, kind: int, dump: int = 32) -> dict:
        m = self.m
        lst = m.malloc(LIST_BYTES)
        m.put(lst, pack_list([(mesh, divid)]))
        self.t.deliver(pack_request(CLIENT_TASK, kind, lst))
        sent, rows = self.carry()
        res = {"mesh": mesh, "divid": divid, "kind": kind, "replies": [], "reads": []}
        records = []
        for row in rows:
            rec = {"file": row["file"], "pos": row["pos"], "length": row["length"],
                   "handler": row["handler"]}
            # record reads only: header, section-table and directory reads are not records
            is_record = row["handler"] not in (0x0040B8B4, 0x0040C308, 0x0041597C)
            rec["role"] = "record" if is_record else self.D.HANDLER_ROLE.get(row["handler"], "?")
            raw = (self.read_raw(row) if is_record and row["file"].upper().startswith("MAPAL001/")
                   else None)
            if raw is not None:
                sid = section_at(self.starts(row), row["pos"])
                rec["section_id"] = sid
                parts = streams_of(raw)
                rec["streams"] = []
                for off, plain in parts:
                    one = {"offset": off, "plain_bytes": len(plain), "section": section_of(sid, plain),
                           "units": unit_pairs(plain) if sid == 2 else None,
                           "code": "%04x%04x" % struct.unpack_from(">HH", plain, 0) if len(plain) >= 4 else "?"}
                    rec["streams"].append(one)
                    records.append(({"code": one["code"], "pos": row["pos"] + off, "sid": sid}, plain))
            res["reads"].append(rec)
        for s in sent:
            if s["task"] != CLIENT_TASK or s["id"] != REQ_EU2011["reply_msg"]:
                res["replies"].append({"to": s["task"], "id": s["id"], "sub": s["sub"]})
                continue
            status, kind_w, lp = struct.unpack_from("<III", s["body"], 12)
            n = struct.unpack_from("<H", bytes(m.eng.read_mem(lp, 2)))[0]
            entries = []
            for i in range(min(n, 8)):
                e = decode_entry(bytes(m.eng.read_mem(lp + 4 + 32 * i, 32)))
                e["targets"] = []
                for p in e["ptrs"]:
                    if p in (0, 0xFFFFFFFF):
                        e["targets"].append(None)
                        continue
                    try:
                        g = bytes(m.eng.read_mem(p, dump))
                    except Exception:  # noqa: BLE001 - an unmapped pointer is a result
                        e["targets"].append({"unmapped": True})
                        continue
                    hit = None
                    for rec, plain in records:
                        at = locate(g, plain)
                        if at is not None:
                            hit = {"record": rec["code"], "pos": rec["pos"], "byte": at, "word": at // 2}
                            if rec["sid"] == 2:
                                hit["unit"] = unit_at(unit_pairs(plain), at // 2)
                            break
                    e["targets"].append(hit or {"record": None, "head": g[:16].hex()})
                entries.append(e)
            res["replies"].append({"to": s["task"], "id": s["id"], "sub": s["sub"],
                                   "status": status, "kind": kind_w, "entries": entries})
        return res


def show(res: dict) -> None:
    print("request mesh %08x DIVID %#06x kind %#x" % (res["mesh"], res["divid"], res["kind"]))
    for r in res["reads"]:
        print("  read %s pos %#x len %#x (%s), %d zlib stream(s)" % (
            r["file"], r["pos"], r["length"], r.get("role", "?"), len(r.get("streams", []))))
        for st in r.get("streams", [])[:8]:
            print("    +%#06x code %s plain %5d B  %s" % (st["offset"], st["code"], st["plain_bytes"], st["section"]))
            if st.get("units"):
                print("      unit pairs (word offset, count): %s" % ", ".join(
                    "-" if o == 0xFFFFFFFF else "(%d, %d)" % (o, n) for o, n in st["units"]))
    for rp in res["replies"]:
        if "entries" not in rp:
            print("  message %#06x sub %d to task %#x" % (rp["id"], rp["sub"], rp["to"]))
            continue
        print("  reply %#06x sub %d status %d kind %#x" % (rp["id"], rp["sub"], rp["status"], rp["kind"]))
        for e in rp["entries"]:
            print("    entry: status %d (%s), kind %#x, mesh %08x, word8 %#010x" % (
                e["status"], e["status_text"], e["kind"], e["mesh"], e["word8"]))
            for j, (p, tg) in enumerate(zip(e["ptrs"], e["targets"])):
                if tg is None:
                    continue
                where = ("record %s @%#x word %d%s" % (tg["record"], tg["pos"], tg["word"],
                                                        "" if tg.get("unit") is None else " = unit %d" % tg["unit"])
                         if tg.get("record") else ("unmapped" if tg.get("unmapped")
                                                   else "not in a read record: %s" % tg.get("head")))
                print("      +%d %#010x -> %s" % (16 + 4 * j, p, where))


def gate_census(tile: str, section: int) -> dict:
    """How many level-1 records of *section* hold a ``k`` that clears
    ``0x00422eac``'s gate (``rgd_reply_l3.candidate_ks``: word ``k+15 & 0x0f00
    == 0x0900``, ``k+7 != 0``, ``k + w[k+6]`` inside).  Host-side count only."""
    import rgd_reply_l3 as R
    t = R.Tile(Path(tile))
    out = {"tile": Path(tile).name, "section": section, "records": 0, "with_k": 0,
           "unreadable": 0, "not_zlib": 0, "words": 0, "candidates": 0}
    try:
        for r in t.records(section):
            if not r.is_zlib:
                # a slot that TileScan lists but that holds no zlib stream (an
                # empty slot's raw span); every record the reader inflates is zlib
                out["not_zlib"] += 1
                continue
            try:
                w = R.words(r.plain())
            except zlib.error:
                out["unreadable"] += 1
                continue
            out["records"] += 1
            out["words"] += len(w)
            ks = R.candidate_ks(w)
            out["candidates"] += len(ks)
            out["with_k"] += bool(ks)
    finally:
        t.close()
    return out


def cmd_gate(args) -> int:
    for sec in args.section:
        c = gate_census(args.tile, sec)
        print("%s section %d level 1: zlib records %d (not zlib %d, unreadable %d), words %d, "
              "records with a passing k %d, passing k %d" % (
                  c["tile"], sec, c["records"], c["not_zlib"], c["unreadable"], c["words"], c["with_k"],
                  c["candidates"]))
    return 0


def cmd_kinds(args) -> int:
    rows = kinds_from_image(args.image)
    print("request-kind table (%s, %d rows): group mask, kind mask -> section index" % (
        REQ_EU2011["build"], len(rows)))
    for g, k, v in rows:
        print("  %#06x  %#06x  -> %d" % (g, k, v))
    return 0


def cmd_request(args) -> int:
    import vcard_l3 as V
    reqs = []
    for r in args.reqs:
        try:
            mesh, divid, kind = (int(x, 0) for x in r.split(":"))
        except ValueError:
            print("bad request %r: want MESH:DIVID:KIND" % r)
            return 2
        reqs.append((mesh, divid, kind))
    lat, _, lon = args.position.partition(",")
    card = V.make_card(None, args.card_image, {})
    try:
        c = Client(args.image, card, (float(lat), float(lon)), register=not args.no_register)
        print("mount: %s; client row %s" % (c.mount_end, c.registered))
        out = []
        for mesh, divid, kind in reqs:
            res = c.request(mesh, divid, kind)
            show(res)
            out.append(res)
    except (V.Blocked, V.EngineError) as exc:
        print("BLOCKED: %s: %s" % (type(exc).__name__, str(exc)[:300]))
        return 3
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=1))
    return 0 if all(any("entries" in rp for rp in r["replies"]) for r in out) else 1


def selftest() -> int:
    fails = []

    def check(name, cond):
        print("  %-66s %s" % (name, "ok" if cond else "FAIL"))
        if not cond:
            fails.append(name)

    blob = b"".join(struct.pack("<III", *r) for r in
                    [(1, 7, 0), (1, 0x38, 1), (1, 0x40, 2), (8, 0x1F, 3), (0, 0, 0xFFFFFFFF)])
    t = decode_kinds(blob, 5)
    check("kind rows decode and stop at the first empty group", len(t) == 4 and t[2] == (1, 0x40, 2))
    check("kind 4 of group 1 is section index 0", kind_section(t, 1, 4) == 0)
    check("kind 8 and kind 0x10 of group 1 are section index 1",
          kind_section(t, 1, 8) == 1 and kind_section(t, 1, 0x10) == 1)
    check("kind 0x40 of group 1 is section index 2", kind_section(t, 1, 0x40) == 2)
    check("a kind no row names has no section", kind_section(t, 1, 0x80) is None)
    check("the group mask must hit too", kind_section(t, 8, 0x40) is None and kind_section(t, 8, 1) == 3)

    msg = pack_request(0x77, 0x40, 0x1234)
    check("request message: id, sub, task, kind, list, 2",
          struct.unpack_from("<HHIIII", msg, 8) == (0x14B5, 2, 0x77, 0x40, 0x1234, 2))
    lst = pack_list([(0xA68CD68C, 3), (0x11112222, 0)])
    check("list: count, mesh at +16, DIVID at +14, stride 32",
          struct.unpack_from("<H", lst, 0)[0] == 2 and struct.unpack_from("<I", lst, 16)[0] == 0xA68CD68C
          and struct.unpack_from("<H", lst, 14)[0] == 3 and struct.unpack_from("<I", lst, 48)[0] == 0x11112222)
    ent = struct.pack("<HHIII4I", 1, 0, 0x40, 0x0303FFFF, 0xA6B2D6E2, 0x100, 0xFFFFFFFF, 0x200, 0x300)
    ent = ent[:10] + struct.pack("<H", 7) + ent[12:]
    e = decode_entry(ent)
    check("reply entry: status, kind, mesh, DIVID, four pointers",
          e["status"] == 1 and e["kind"] == 0x40 and e["divid"] == 7 and e["ptrs"] == [0x100, 0xFFFFFFFF, 0x200, 0x300])

    plain = struct.pack(">8H", 0xA68C, 0xD68C, 0, 0, 0x13, 0x24, 0x1111, 0x2222)
    check("native swaps each u16", native(b"\x12\x34") == b"\x34\x12")
    check("a pointer prefix locates its word in the record", locate(native(plain)[8:16], plain) == 8)
    check("an ambiguous prefix is not located", locate(b"\0" * 8, plain + bytes(16)) is None)
    check("a foreign prefix is not located", locate(b"\xde\xad" * 4, plain) is None)
    check("a pointer that reads past the record end is located by its prefix",
          locate(native(plain)[8:] + b"\x55" * 8, plain) == 8)
    rec2 = struct.pack(">6H", 0xA6BE, 0xD6EE, 0, 0, 0, 0) + struct.pack(">10I", 27, 6086, 0xFFFFFFFF, 0,
                                                                          6113, 10, 0xFFFFFFFF, 0, 0xFFFFFFFF, 0)
    check("section-2 unit pairs read from byte 12", unit_pairs(rec2)[2] == (6113, 10))
    check("a pointer word names the unit that starts there",
          unit_at(unit_pairs(rec2), 27) == 0 and unit_at(unit_pairs(rec2), 6113) == 2 and unit_at(unit_pairs(rec2), 28) is None)
    raw = zlib.compress(plain)
    check("a zlib record inflates, a stored one passes", plain_of(raw) == plain and plain_of(plain) == plain)
    two = raw + (b"\0" if len(raw) % 2 else b"") + zlib.compress(plain[::-1])
    got = streams_of(two)
    check("a read with two streams gives both, with offsets",
          len(got) == 2 and got[0] == (0, plain) and got[1][1] == plain[::-1] and got[1][0] == len(raw) + (len(raw) & 1))
    head = bytearray(HEAD_BYTES)
    lv = struct.pack(">H", 3) + b"".join(bytes([sid, 1]) + bytes(4) for sid in (1, 2, 4))
    head[0x1AC:0x1AC + len(lv)] = lv
    # sections 1, 2, 4 at file 0x1000, 0x5000, 0x9000 (addr_of: (v >> 8) * 2048 + (v & 0xff) * 256)
    st = b"".join(struct.pack(">IH", v, 0) for v in (0x200, 0xA00, 0x1200)) + struct.pack(">IH", 0xFFFFFFFF, 0)
    head[0x800:0x800 + len(st)] = st
    sp = section_starts(bytes(head))
    check("section spans from the level and section tables", sp == [(0x1000, 1), (0x5000, 2), (0x9000, 4)])
    check("a read position is labelled by the span it falls in, not by header word 2",
          section_at(sp, 0x4FFF) == 1 and section_at(sp, 0x5000) == 2 and section_at(sp, 0x9100) == 4
          and section_at(sp, 0x800) is None
          and section_of(2, struct.pack(">3H", 1, 2, 0xFA)).startswith("section 2 (w2=0x00fa)"))

    img = HERE.parent / "archive" / "head256.img"
    if img.is_file():
        try:
            rows = kinds_from_image(str(img))
            check("EU2011 kind table: 4 -> 0, 8/0x10/0x20 -> 1, 0x40 -> 2",
                  kind_section(rows, 1, 4) == 0 and kind_section(rows, 1, 8) == 1
                  and kind_section(rows, 1, 0x20) == 1 and kind_section(rows, 1, 0x40) == 2)
        except Exception as exc:  # noqa: BLE001
            check("EU2011 kind table readable (%s)" % exc, False)
    else:
        print("  (archive/head256.img absent: the image check is skipped, not passed)")
    print("datask_req_l3 selftest: %s" % ("%d FAIL" % len(fails) if fails else "all OK"))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("kinds", help="print the request-kind -> section-index table")
    p.add_argument("image")
    p = sub.add_parser("gate", help="count records with a k that clears 0x00422eac's gate (host side)")
    p.add_argument("--tile", required=True)
    p.add_argument("--section", type=int, action="append", required=True)
    p = sub.add_parser("request", help="mount, register a client, send 0x14b5 requests")
    p.add_argument("image")
    p.add_argument("--card-image", required=True)
    p.add_argument("--position", required=True, metavar="LAT,LON")
    p.add_argument("--no-register", action="store_true",
                   help="do not register the client (negative control: status 9)")
    p.add_argument("--json")
    p.add_argument("reqs", nargs="+", metavar="MESH:DIVID:KIND")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmd:
        ap.print_usage()
        return 2
    if args.cmd == "gate":
        return cmd_gate(args)
    if not Path(args.image).is_file():
        print("missing image: %s" % args.image)
        return 2
    if args.cmd == "request" and not Path(args.card_image).is_file():
        print("missing card image: %s" % args.card_image)
        return 2
    return {"kinds": cmd_kinds, "request": cmd_request}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
