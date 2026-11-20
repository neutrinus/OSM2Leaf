#!/usr/bin/env python3
"""datask_l3.py - run the firmware's data-access task against a virtual card.

`vcard_l3.py` (M9.44) runs the map-file layer of `Navi.exe`: it mounts a card
and serves read requests.  This tool runs the *client* next to it: the
data-access task, the code that asks for map files and parses what comes back.
Both tasks run in one PySh4 machine; the tool plays the kernel's part and
carries each `OSM_TaskSend` message to the task it names:

    "map database ready" (message 0x07d0, sub 100)
        -> data-access task opens the tile directory, asks for file headers
        -> map-file task reads the card, sends completion 0x04a0
        -> data-access task looks the request tag up in its completion table
           and calls the handler: file header, section table, directory ...
        -> the handler asks for the next piece

For every completed read the tool prints the file, offset and length, the
handler the firmware chose, and which bytes of the buffer each firmware
function loaded.  The functions that load tile bytes are the tile readers;
their entry and arguments are what M3.25 asked for.

No vendor byte is stored here: the tool reads the image and card it is given.

Usage:
  datask_l3.py --selftest
  datask_l3.py tables IMG256
  datask_l3.py diff   A.json B.json [--file NAME]
  datask_l3.py mount  IMG256 --card-image CARD.img [--max-reads N] [--file NAME]
                      [--position LAT,LON]
                      [--bytes] [--json OUT] [--flip MAPAL001/LEV3456R.DAT@0x803:0x01]

Exit codes: mount: 0 the run finished and at least one tile read was parsed,
1 no tile read was parsed; diff: 0 SAME, 1 DIFFERENT; 3 BLOCKED (missing
model, engine stop); 2 usage or missing input.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE / "l3_harness"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import vcard_l3 as V  # noqa: E402

# --------------------------------------------------------------------------
# The data-access task of Navi.exe, EU2011 build A.  Function VAs are pdata
# starts (docs/format/firmware.md, "The data-access task"; EXP M3.25).  Data
# addresses are written short on purpose: fn_audit reads eight hex digits as
# a function citation.
DA_EU2011 = {
    "build": "EU2011",
    "task_entry": 0x003EBFB4,     # init + receive loop (not called: we are the loop)
    "init": (0x003F6908, 0x003EBA78),
    "dispatch": 0x003EBEE8,       # (message *) -> handler by message id
    "msg_table": (0x177 << 12) + 0xFD0,        # 43 rows {u16 id, u16 defer, u32 handler}
    "msg_rows": 43,
    "sub_tables": {0x07D0: ((0x179 << 12) + 0x6F4, 6), 0x00A0: ((0x179 << 12) + 0x6C4, 5)},
    "done_handler": 0x003F72E4,   # message 0x04a0: a read finished
    "done_table": (0x178 << 12) + 0xD60,       # 20 rows {u16 tag class, u16 0, u32 handler}
    "done_rows": 20,
    "read_api": 0x0041841C,       # map-file layer: (file id, request *)
    "da_task_id": 0x11FFF58,      # global: task id the reply goes to
    "map_task_id": 0x11FFFB8,     # global: task id of the map-file task
    "state": 0xD62490,            # 2 = mounting, 3 = ready
    "mesh_count": 0xD63CA0,       # tile files found in MAPAL001
    "version": 0xD8AD20,          # map format version from the volume header
    "mmain_buf": 0xE23CC0,        # the volume header the map-file layer read
    # leaf functions (no pdata record): header date reader, block-header reader
    "leaves": (0x0040A8D0, 0x004144A8),
    "position": (0xD94 << 12) + 0x0E4,   # u32: (lat code << 16) | lon code
    "default_position_fn": 0x0040B49C,   # (kind) -> start position from a per-area table, or -1
    # directory read length (M3.31): leaf (kind, column) -> u32 from a
    # 16-row table {u32 kind, u32 length / 0x100, u32 buffer size}; the
    # directory request of 0x00414338 asks column 1 for the level-table kind
    "len_lookup": 0x0040901C,
    "len_table": ((0x179 << 12) + 0xC08, 16),
    "ready_msg": (0x07D0, 100),
    "done_msg": 0x04A0,
}
DA_TASK, MAP_TASK = 2, 0x10       # any two different non-zero ids

# what each completion handler is, from the reads it was seen to serve
HANDLER_ROLE = {
    0x0040B8B4: "file header (first 0x1000 bytes)",
    0x0040C308: "section table",
    0x0041597C: "directory",
    0x003F72CC: "REFER001 search data",
}


class State:
    """What the models need to share with the tool."""

    def __init__(self):
        self.task = 1
        self.sems = 0x5E00
        self.datavol = None
        self.zeroed: list[str] = []


def install_models(st: State) -> None:
    """Kernel and object-store calls the data-access task makes.

    Each model is the smallest behaviour the caller checks; none invents data:
    memory comes from the tool's heap, the saved-settings block is empty and
    flagged invalid, the car position is never written.
    """
    M = V.MODELS
    M["taskIdSelf"] = lambda m: st.task

    def sem_create(m):
        st.sems += 1
        return st.sems
    M["OSM_SemCreate"] = sem_create
    for name in ("OSM_SemTake", "OSM_SemGive", "OSM_SemDelete"):
        M[name] = lambda m: 0
    M["OSM_isSender"] = lambda m: 0x20
    # memory areas 0..3: one 4 MiB area, the rest empty
    M["OSM_MemSize"] = lambda m: (4 << 20) if m.arg(0) == 0 else 0
    M["OSM_MemGet"] = lambda m: m.malloc(m.arg(0)) if m.arg(0) else 0

    def sram_get(m):
        # (id, size, void **out, u32 *out_size): an empty block
        size = m.arg(1)
        va = m.malloc(size)
        m.put(va, bytes(size))
        m.put(m.arg(2), struct.pack("<I", va))
        m.put(m.arg(3), struct.pack("<I", size))
        return 0
    M["OSM_SramGet"] = sram_get
    M["OSM_SramCheck"] = lambda m: 1          # contents not valid: start fresh

    def write_datavol(m):
        # the map-file layer publishes the volume header it read (id, bytes *)
        st.datavol = bytes(m.eng.read_mem(m.arg(1), 0x1000))
        m.objects.append({"kind": "OBJ_DriveInfo_writeDataVol",
                          "args": [m.arg(i) for i in range(4)], "pr": m.reg("pr")})
        return 0
    M["OBJ_DriveInfo_writeDataVol"] = write_datavol

    def read_discvol(m):
        # (id, 0, 20, dst): the same header, as the object store hands it out.
        # In the unit 0x00377ae0 copies DataVol to DiscVol; that function did
        # not run here, so this model is the copy.
        data = st.datavol
        if data is None:
            data = bytes(m.eng.read_mem(DA_EU2011["mmain_buf"], 0x1000))
        m.put(m.arg(3), data)
        m.objects.append({"kind": "OBJ_DiscInfo_readDiscVol",
                          "args": [m.arg(i) for i in range(4)], "pr": m.reg("pr")})
        return 0
    M["OBJ_DiscInfo_readDiscVol"] = read_discvol

    for name in ("OBJ_CarPos_initPrm", "OBJ_CarPos_read", "OBJ_CarPos_setEventMesh",
                 "OBJ_CarPos_startEvent", "OBJ_Event_setPrm", "OBJ_Event_initPrm",
                 "OBJ_RoutePntTbl_setEventPnt", "OBJ_RoutePntTbl_startEvent"):
        if name not in M:
            M[name] = lambda m: 0
            st.zeroed.append(name)


# --------------------------------------------------------------------------
# pure helpers (host side; covered by --selftest without any image)

def decode_table(blob: bytes, rows: int) -> list[tuple[int, int, int]]:
    """Rows of {u16 key, u16 flag, u32 handler}."""
    return [struct.unpack_from("<HHI", blob, 8 * i) for i in range(rows)]


def len_lookup(rows, kind: int, column: int) -> int:
    """The firmware's rule in the leaf 0x0040901c (EU2011): the first of the
    16 rows {kind, length / 0x100, buffer size} whose kind equals ``kind``
    gives column ``column``; no row gives 0."""
    for row in rows:
        if row[0] == kind:
            return row[column]
    return 0


def decode_len_table(blob: bytes, rows: int) -> list[tuple[int, int, int]]:
    return [struct.unpack_from("<III", blob, 12 * i) for i in range(rows)]


def done_lookup(table, tag: int):
    """The firmware's rule in 0x003f72e4: first row whose key is not zero and
    equals the tag in bits 8..14."""
    for key, _flag, handler in table:
        if handler == 0:
            return None
        if key and ((tag ^ key) & 0x7F00) == 0:
            return handler
    return None


def msg_lookup(table, msg_id: int):
    for key, flag, handler in table:
        if key == msg_id:
            return handler, flag
    return None


def runs(offsets) -> list[tuple[int, int]]:
    out: list[list[int]] = []
    for o in sorted(set(offsets)):
        if out and o <= out[-1][1] + 1:
            out[-1][1] = o
        else:
            out.append([o, o])
    return [(a, b) for a, b in out]


def show_runs(rr, limit: int = 10) -> str:
    text = ",".join(("%#x-%#x" % (a, b)) if a != b else ("%#x" % a) for a, b in rr[:limit])
    if len(rr) > limit:
        text += " ... (%d runs)" % len(rr)
    return text


def decode_request(raw: bytes) -> dict:
    """First 16 bytes of a read request: dst, sector, offset, length / 4."""
    dst, sector, off, words = struct.unpack_from("<IIII", raw)
    return {"dst": dst, "pos": sector * 0x800 + off, "length": words * 4}


def encode_position(lat: float, lon: float) -> int:
    """The COORD001 grid (map-tiles.md): lat code = 32768 + 192 * lat,
    lon code = 52742 + 128 * lon, packed lat high."""
    y = int(round(32768 + 192 * lat))
    x = int(round(52742 + 128 * lon))
    if not (0 <= y <= 0xFFFF and 0 <= x <= 0xFFFF):
        raise ValueError("position %r, %r is outside the grid" % (lat, lon))
    return (y << 16) | x


def decode_position(code: int) -> tuple[float, float]:
    return (((code >> 16) - 32768) / 192.0, ((code & 0xFFFF) - 52742) / 128.0)


def ready_message() -> bytes:
    msg = bytearray(32)
    struct.pack_into("<HH", msg, 8, *DA_EU2011["ready_msg"])
    return bytes(msg)


# --------------------------------------------------------------------------

class DataTask:
    """The data-access task and the map-file task on one virtual card."""

    def __init__(self, image: str, card, build: dict = DA_EU2011, position=None):
        self.b = build
        self.st = State()
        install_models(self.st)
        out, s = V.boot_report(image, card)
        if s is None or out.get("verdict") != "ACCEPT":
            raise V.Blocked("the card did not mount: %s" % (out.get("blocked") or out.get("verdict")))
        self.s, self.m, self.card = s, s.m, card
        self.boot = out
        m = self.m
        self.st.task = DA_TASK
        for va in build["init"]:
            m.call(va, [], max_insns=80_000_000)
        m.put(build["da_task_id"], struct.pack("<I", DA_TASK))
        m.put(build["map_task_id"], struct.pack("<I", MAP_TASK))
        self.default_position = m.u32(build["position"])
        if position is not None:
            # 0x0040b49c looks the start position up in a per-area table and
            # falls back to the global when the table has no row.  A chosen
            # position is given as that fallback: the lookup answers "no row".
            m.put(build["position"], struct.pack("<I", encode_position(*position)))
            m.eng.on_exec(build["default_position_fn"], lambda engine, va: V.StubReturn(V.M32))
        rd = lambda va, n: bytes(m.eng.read_mem(va, n))
        self.msg_table = decode_table(rd(build["msg_table"], 8 * build["msg_rows"]), build["msg_rows"])
        self.done_table = decode_table(rd(build["done_table"], 8 * build["done_rows"]), build["done_rows"])
        self.sub_tables = {k: decode_table(rd(va, 8 * n), n) for k, (va, n) in build["sub_tables"].items()}
        self.names = {f["fid"]: f["path"] for f in s.files()}
        self.requests: dict[int, dict] = {}
        self.called: list[int] = []
        va, n = build["len_table"]
        self.len_table = decode_len_table(rd(va, 12 * n), n)
        self.last_len = None
        m.eng.on_exec(build["len_lookup"], self._on_len_lookup)
        m.eng.on_exec(build["read_api"], self._on_read)
        for h in sorted({h for _k, _f, h in self.done_table if h}):
            m.eng.on_exec(h, self._on_handler(h))
        self.fn_of = self._fn_of(image)
        self.entered: set[int] = set()
        for va in build["leaves"]:
            m.eng.on_exec(va, self._on_leaf(va))
        self.routed = len(m.messages)
        self.rows: list[dict] = []
        self.other: list[dict] = []

    @staticmethod
    def _fn_of(image: str):
        import pdata
        data = Path(image).read_bytes()
        records, _meta = pdata.load_table(data, V.IMAGE_A, "Navi.exe")
        return pdata.fn_of_factory(records)

    def leaf_start(self, pc: int) -> int:
        """Start of the leaf function around ``pc``: the last call target at
        or below it that the run entered (leaves have no pdata record)."""
        best = 0
        for va in self.entered:
            if best < va <= pc:
                best = va
        return best

    def _on_len_lookup(self, engine, va):
        m = self.m
        kind, col = m.arg(0), m.arg(1)
        if col == 1:
            self.last_len = {"kind": kind, "column": col, "value": len_lookup(self.len_table, kind, col),
                             "from": (m.reg("pr") - 4) & V.M32}
        return None

    def _on_read(self, engine, va):
        m = self.m
        req = decode_request(bytes(m.eng.read_mem(m.arg(1), 16)))
        req["fid"] = m.arg(0)
        req["len_lookup"], self.last_len = self.last_len, None
        self.requests[req["dst"]] = req
        return None

    def _on_leaf(self, va):
        def hook(engine, _va):
            self.entered.add(va)
            return None
        return hook

    def _on_handler(self, h):
        def hook(engine, va):
            self.called.append(h)
            return None
        return hook

    # -- the kernel's part ------------------------------------------------
    def deliver(self, body: bytes) -> None:
        """Hand one message to the data-access task's dispatcher."""
        m = self.m
        self.st.task = DA_TASK
        p = m.malloc(64)
        m.put(p, body.ljust(64, b"\0"))
        try:
            m.call(self.b["dispatch"], [p], max_insns=400_000_000)
        finally:
            m.free(p)

    def map_task_turn(self) -> None:
        self.st.task = MAP_TASK
        self.m.call(self.s.b["event"], [2])

    def complete(self, body: bytes, want_bytes: bool) -> dict:
        """Deliver one read completion and record who parsed the buffer."""
        m, e = self.m, self.m.eng
        _mid, tag = struct.unpack_from("<HH", body, 8)
        status, buf, n = struct.unpack_from("<III", body, 12)
        req = self.requests.pop(buf, {})
        e._watches.clear()
        e._watch_hits.clear()
        if n:
            e.watch(buf, buf + n, "r", "buffer")
            e.arm_watch()
        first = len(self.called)
        try:
            self.deliver(body)
        finally:
            e.disarm_watch()
        by: dict[int, list[int]] = {}
        for hit in e.watch_hits():
            if hit.kind != "r":
                continue
            fn = self.fn_of(hit.pc)
            if fn is None:                    # a leaf function has no pdata record
                fn = self.leaf_start(hit.pc)
            by.setdefault(fn, []).extend(range(hit.va - buf, hit.va - buf + hit.size))
        e._watch_hits.clear()
        handler = self.called[first] if len(self.called) > first else None
        row = {"tag": tag, "status": status, "length": n, "fid": req.get("fid"),
               "file": self.names.get(req.get("fid"), "?"), "pos": req.get("pos"),
               "handler": handler, "expected_handler": done_lookup(self.done_table, tag),
               "len_lookup": req.get("len_lookup"),
               "readers": [{"fn": fn, "bytes": len(set(v)), "runs": runs(v) if want_bytes else runs(v)[:10],
                            "nruns": len(runs(v))} for fn, v in by.items()]}
        self.rows.append(row)
        return row

    def run(self, max_reads: int = 0, want_bytes: bool = False, on_row=None) -> str:
        """Announce the map and carry messages until both tasks are idle."""
        m = self.m
        self.deliver(ready_message())
        while True:
            if max_reads and len(self.rows) >= max_reads:
                return "stopped after %d reads (--max-reads)" % max_reads
            if self.routed >= len(m.messages):
                before = len(m.messages)
                self.map_task_turn()          # anything still queued in the file task?
                if len(m.messages) == before:
                    return "both tasks idle"
                continue
            x = m.messages[self.routed]
            self.routed += 1
            if x["kind"] != "send":
                self.other.append({"kind": x["kind"], "args": x.get("args")})
                continue
            body = bytes.fromhex(x["body"])
            msg_id, sub = struct.unpack_from("<HH", body, 8)
            if x["task"] == MAP_TASK:
                self.map_task_turn()
            elif x["task"] == DA_TASK and msg_id == self.b["done_msg"]:
                row = self.complete(body, want_bytes)
                if on_row:
                    on_row(row)
            elif x["task"] == DA_TASK:
                self.deliver(body)
            else:
                self.other.append({"kind": "send", "task": x["task"], "id": msg_id, "sub": sub,
                                   "from": (x["pr"] - 4) & V.M32})

    def summary(self) -> dict:
        m = self.m
        return {"state": m.u32(self.b["state"]), "mesh_count": m.u32(self.b["mesh_count"]),
                "version": m.u32(self.b["version"]), "reads": len(self.rows),
                "zero_models": self.st.zeroed}


def show_row(row: dict) -> None:
    role = HANDLER_ROLE.get(row["handler"], "")
    print("tag %#06x  %-28s pos %#10x len %#7x  handler %s  %s" % (
        row["tag"], row["file"], row["pos"] or 0, row["length"],
        ("%#010x" % row["handler"]) if row["handler"] else "-", role))
    lk = row.get("len_lookup")
    if lk:
        print("      length from 0x0040901c(kind %#x, %d) = %#x -> %#x B (call at %#010x)%s" % (
            lk["kind"], lk["column"], lk["value"], lk["value"] * 0x100, lk["from"],
            "" if lk["value"] * 0x100 == row["length"] else "  [not this read's length]"))
    for r in row["readers"]:
        print("      fn %#010x loads %6d B: %s" % (r["fn"], r["bytes"], show_runs(r["runs"])))


def is_tile(row: dict) -> bool:
    return row["file"].upper().startswith("MAPAL001/") and bool(row["readers"])


def cmd_tables(args) -> int:
    card = V.make_card(args.card_root, args.card_image) if (args.card_root or args.card_image) else None
    if card is None:
        # the tables are constant data: read them from the image alone
        m = V.load_machine(args.image, V.Card(V.MemorySource({})))
        rd = lambda va, n: bytes(m.eng.read_mem(va, n))
        b = DA_EU2011
        msg = decode_table(rd(b["msg_table"], 8 * b["msg_rows"]), b["msg_rows"])
        done = decode_table(rd(b["done_table"], 8 * b["done_rows"]), b["done_rows"])
        subs = {k: decode_table(rd(va, 8 * n), n) for k, (va, n) in b["sub_tables"].items()}
    else:
        t = DataTask(args.image, card)
        msg, done, subs = t.msg_table, t.done_table, t.sub_tables
    print("message table (%d rows): id  defer  handler" % len(msg))
    for key, flag, h in msg:
        print("  %#06x  %d  %#010x" % (key, flag, h))
    for k, rows in subs.items():
        print("sub-table of message %#06x: sub  handler" % k)
        for key, _flag, h in rows:
            print("  %#06x  %#010x" % (key, h))
    print("read-completion table (%d rows): tag class  handler" % len(done))
    for key, _flag, h in done:
        print("  %#06x  %#010x  %s" % (key, h, HANDLER_ROLE.get(h, "")))
    return 0


def cmd_mount(args) -> int:
    card = V.make_card(args.card_root, args.card_image, V.parse_mods(args))
    try:
        position = None
        if args.position:
            lat, _, lon = args.position.partition(",")
            position = (float(lat), float(lon))
        t = DataTask(args.image, card, position=position)
        print("position: %s (default %.3f, %.3f)" % (
            ("%.3f, %.3f" % position) if position else "default", *decode_position(t.default_position)))
        want = args.file.upper() if args.file else None

        def on_row(row):
            if want is None or want in row["file"].upper():
                show_row(row)
        end = t.run(args.max_reads, args.bytes, on_row)
    except (V.Blocked, V.EngineError) as exc:
        print("BLOCKED: %s: %s" % (type(exc).__name__, str(exc)[:300]))
        return 3
    out = t.summary()
    out["end"] = end
    print("end: %s; state %d, tile files %d, map version %#x, reads %d" % (
        end, out["state"], out["mesh_count"], out["version"], out["reads"]))
    for o in t.other:
        print("not delivered: %s" % json.dumps(o))
    if out["zero_models"]:
        print("models that return 0 and write nothing: %s" % ", ".join(out["zero_models"]))
    tiles = [r for r in t.rows if is_tile(r)]
    print("tile reads parsed by the firmware: %d" % len(tiles))
    if args.json:
        out["rows"] = t.rows
        out["other"] = t.other
        Path(args.json).write_text(json.dumps(out, indent=1))
    return 0 if tiles else 1


def row_key(row: dict) -> tuple:
    return (row["file"].upper(), row["tag"], row["pos"], row["length"])


def row_shape(row: dict) -> tuple:
    """What the firmware did with one read: handler and, per function, how
    many bytes it loaded and in how many runs."""
    return (row["handler"], tuple(sorted((r["fn"], r["bytes"], r["nruns"]) for r in row["readers"])))


def diff_rows(a: list[dict], b: list[dict], want: str | None = None) -> list[str]:
    """Differences between two runs, in read order.  Empty = the firmware
    asked for the same bytes and parsed them the same way."""
    keep = (lambda r: want is None or want.upper() in r["file"].upper())
    a = [r for r in a if keep(r)]
    b = [r for r in b if keep(r)]
    out = []
    for i in range(max(len(a), len(b))):
        if i >= len(a) or i >= len(b):
            only = "A" if i >= len(b) else "B"
            r = a[i] if only == "A" else b[i]
            out.append("read %d only in %s: %s pos %#x len %#x" % (i + 1, only, r["file"], r["pos"] or 0, r["length"]))
            continue
        ra, rb = a[i], b[i]
        if row_key(ra) != row_key(rb):
            out.append("read %d asks differently: A %s tag %#06x pos %#x len %#x / B %s tag %#06x pos %#x len %#x" % (
                i + 1, ra["file"], ra["tag"], ra["pos"] or 0, ra["length"],
                rb["file"], rb["tag"], rb["pos"] or 0, rb["length"]))
        elif ra["status"] != rb["status"]:
            out.append("read %d (%s pos %#x) status A %d / B %d" % (i + 1, ra["file"], ra["pos"] or 0, ra["status"], rb["status"]))
        elif row_shape(ra) != row_shape(rb):
            fa = {r["fn"]: (r["bytes"], r["nruns"]) for r in ra["readers"]}
            fb = {r["fn"]: (r["bytes"], r["nruns"]) for r in rb["readers"]}
            parts = ["fn %#010x A %s B %s" % (fn, fa.get(fn), fb.get(fn))
                     for fn in sorted(set(fa) | set(fb)) if fa.get(fn) != fb.get(fn)]
            if ra["handler"] != rb["handler"]:
                parts.insert(0, "handler A %s B %s" % (ra["handler"], rb["handler"]))
            out.append("read %d (%s pos %#x len %#x) parsed differently: %s" % (
                i + 1, ra["file"], ra["pos"] or 0, ra["length"], "; ".join(parts)))
    return out


def cmd_diff(args) -> int:
    a = json.loads(Path(args.a).read_text())
    b = json.loads(Path(args.b).read_text())
    for label, run in (("A", a), ("B", b)):
        n = len([r for r in run["rows"] if args.file is None or args.file.upper() in r["file"].upper()])
        print("%s: %s; state %d, tile files %d, reads %d (%d compared)" % (
            label, run["end"], run["state"], run["mesh_count"], run["reads"], n))
    diffs = diff_rows(a["rows"], b["rows"], args.file)
    for line in diffs:
        print("  " + line)
    same_end = (a["end"], a["state"], a["mesh_count"]) == (b["end"], b["state"], b["mesh_count"])
    if not same_end:
        print("  the runs end differently")
    verdict = "SAME" if not diffs and same_end else "DIFFERENT"
    print("verdict: %s (%d difference(s))" % (verdict, len(diffs) + (0 if same_end else 1)))
    return 0 if verdict == "SAME" else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("tables", "mount"):
        p = sub.add_parser(name)
        p.add_argument("image")
        p.add_argument("--card-image")
        p.add_argument("--card-root")
        for opt in ("--hide", "--replace", "--flip", "--truncate"):
            p.add_argument(opt, action="append", default=[],
                           help="change one file of the card for this run (see vcard_l3.py)")
        if name == "mount":
            p.add_argument("--max-reads", type=int, default=0)
            p.add_argument("--file", help="print only reads of files whose path contains this")
            p.add_argument("--bytes", action="store_true", help="keep every byte run in --json")
            p.add_argument("--position", metavar="LAT,LON",
                           help="car position to mount at (decides which BxxRyyR tile is read)")
            p.add_argument("--json")
    p = sub.add_parser("diff", help="compare two mount --json runs read by read")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--file", help="compare only reads of files whose path contains this")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "diff":
        for path in (args.a, args.b):
            if not Path(path).is_file():
                print("missing run: %s" % path)
                return 2
        return cmd_diff(args)
    if not args.cmd:
        ap.print_usage()
        return 2
    if not Path(args.image).is_file():
        print("missing image: %s" % args.image)
        return 2
    if args.cmd == "mount" and not (args.card_image or args.card_root):
        print("mount needs --card-image or --card-root")
        return 2
    return {"tables": cmd_tables, "mount": cmd_mount}[args.cmd](args)


def selftest() -> int:
    """Host-side logic always; the firmware part only when the git-ignored
    images are present (skipped otherwise, and said so)."""
    fails = []

    def check(name, cond):
        print("  %-66s %s" % (name, "ok" if cond else "FAIL"))
        if not cond:
            fails.append(name)

    blob = struct.pack("<HHI", 0x0600, 0, 0x1111) + struct.pack("<HHI", 0x0100, 0, 0x2222) \
        + struct.pack("<HHI", 0x0D01, 0, 0x3333) + struct.pack("<HHI", 0, 0, 0)
    table = decode_table(blob, 4)
    check("table rows decode as key, flag, handler", table[1] == (0x0100, 0, 0x2222))
    check("a tag matches its class in bits 8..14", done_lookup(table, 0x0103) == 0x2222)
    check("the low byte of the tag is ignored", done_lookup(table, 0x06FF) == 0x1111)
    check("bit 15 of the tag is ignored", done_lookup(table, 0x8D00) == 0x3333)
    check("an unknown class finds no handler", done_lookup(table, 0x0700) is None)
    check("the table ends at the first empty handler",
          done_lookup(decode_table(struct.pack("<HHI", 0, 0, 0) + blob, 5), 0x0100) is None)
    check("message lookup returns handler and defer flag",
          msg_lookup([(0x14B5, 1, 0x4444)], 0x14B5) == (0x4444, 1) and msg_lookup([], 1) is None)
    check("byte offsets fold into runs", runs([5, 1, 2, 3, 9, 10, 2]) == [(1, 3), (5, 5), (9, 10)])
    check("runs print as ranges", show_runs([(1, 3), (5, 5)]) == "0x1-0x3,0x5")
    check("long run lists are cut and counted", show_runs([(i * 4, i * 4) for i in range(12)]).endswith("(12 runs)"))
    req = decode_request(struct.pack("<IIII", 0x30001000, 3, 0x100, 0x40))
    check("a request decodes to position and length",
          req == {"dst": 0x30001000, "pos": 3 * 0x800 + 0x100, "length": 0x100})
    msg = ready_message()
    check("a position packs as lat code high, lon code low",
          encode_position(0, 0) == (32768 << 16) | 52742 and encode_position(48, 16) == ((32768 + 9216) << 16) | (52742 + 2048))
    check("a packed position decodes back", decode_position(encode_position(51.5, -0.25)) == (51.5, -0.25))
    check("the ready message is id 0x07d0 sub 100", struct.unpack_from("<HH", msg, 8) == (0x07D0, 100))
    check("tile rows are MAPAL001 reads somebody parsed",
          is_tile({"file": "MAPAL001/B28R070R.DAT", "readers": [1]})
          and not is_tile({"file": "REFER001/POINT001.DAT", "readers": [1]})
          and not is_tile({"file": "MAPAL001/B28R070R.DAT", "readers": []}))

    def mk(pos, length=0x100, fn=0x1000, nbytes=10, nruns=2, status=0, handler=0x2000, name="MAPAL001/B48R058R.DAT"):
        return {"file": name, "tag": 0x700, "pos": pos, "length": length, "status": status, "handler": handler,
                "readers": [{"fn": fn, "bytes": nbytes, "nruns": nruns, "runs": []}]}
    base = [mk(0x1000), mk(0x2000), mk(0x3000, name="REFER001/POINT001.DAT")]
    check("two equal runs have no difference", diff_rows(base, [dict(r) for r in base]) == [])
    check("a read at another position is named",
          "asks differently" in diff_rows(base, [mk(0x1000), mk(0x2100), base[2]])[0])
    check("the same read parsed with other byte counts is named",
          "parsed differently" in diff_rows(base, [mk(0x1000), mk(0x2000, nbytes=11), base[2]])[0])
    check("a missing read is named", "only in A" in diff_rows(base, base[:2])[0])
    check("a failed read is named", "status" in diff_rows(base, [mk(0x1000, status=5), base[1], base[2]])[0])
    check("--file limits the comparison",
          diff_rows(base, [base[0], base[1], mk(0x9000, name="REFER001/POINT001.DAT")], "B48R058R") == [])

    saved = dict(V.MODELS)
    st = State()
    install_models(st)
    check("the task id model follows the task the tool is running",
          V.MODELS["taskIdSelf"](None) == 1 and (setattr(st, "task", 7) or V.MODELS["taskIdSelf"](None) == 7))
    V.MODELS.clear()
    V.MODELS.update(saved)

    head = HERE.parent / "archive" / "head256.img"
    card_img = HERE.parent / "archive" / "sd-images" / "LEAF_2011-2012_QSD-309-101_navi158_eu.img"
    if not (head.is_file() and card_img.is_file()):
        print("  firmware part skipped: archive/head256.img or the EU card image is not present")
    else:
        try:
            t = DataTask(str(head), V.make_card(None, str(card_img)))
            check("the completion table has 20 handlers", len([1 for _k, _f, h in t.done_table if h]) == 20)
            check("message 0x04a0 goes to the completion handler",
                  msg_lookup(t.msg_table, 0x04A0) == (DA_EU2011["done_handler"], 0))
            end = t.run(max_reads=6)
            first = t.rows[0]
            check("the first read is the header of MAPAL001/LEV3456R.DAT",
                  first["file"].upper() == "MAPAL001/LEV3456R.DAT" and first["pos"] == 0
                  and first["length"] == 0x1000)
            check("the firmware calls the handler the table names",
                  all(r["handler"] == r["expected_handler"] for r in t.rows))
            check("the header handler loads bytes of the header",
                  first["handler"] == 0x0040B8B4 and sum(r["bytes"] for r in first["readers"]) > 0)
            check("a section table read follows and is parsed",
                  any(r["handler"] == 0x0040C308 and r["readers"] for r in t.rows))
            check("every load is attributed to a function",
                  all(x["fn"] for r in t.rows for x in r["readers"]))
            check("46 tile files were found", t.summary()["mesh_count"] == 46)
            check("the run stopped where asked", end.startswith("stopped after 6"))
        except (V.Blocked, V.EngineError) as exc:
            check("firmware run (%s)" % str(exc)[:80], False)
        finally:
            V.MODELS.clear()
            V.MODELS.update(saved)
    print("datask_l3 selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
