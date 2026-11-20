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

The mount ends with the state word at 2 and one message the two tasks do not
answer: `0x1507` sub 1.  Its receiver is a third task of `Navi.exe`,
`SDL_task` (M9.52); `--sdl` runs that task too.  It drops the message: it
takes a message from the data-access task only as the answer to a request of
its own.  What moves the state word to 3 is an object-store event, message
`0x07d0` sub 11 with `+28 = 16`; `--event 11:16` delivers it as a stand-in
(its sender is not part of the run, and the tool says so).

State 3 is not "ready" (M9.53): in state 3 the request check 0x00405970
refuses every map request.  The map is served in state 2.  `--request MESH`
sends one map request (message 0x14b5, as C-5641 lays it out) after the
mount: the client task is first opened with 0x003ed6e8 (without a slot the
answer is status 9), the data-access task reads the record block of that
mesh (tag 0x0900, handler 0x00404ee4), byte-swaps it (0x003f6968), inflates
it (0x0054233c) and swaps the output; the row lists who loads the inflated
record.  The reply 0x14b6 goes to the client, which is not part of the run:
the roads in the record are walked there.

Usage:
  datask_l3.py --selftest
  datask_l3.py tables IMG256
  datask_l3.py diff   A.json B.json [--file NAME]
  datask_l3.py mount  IMG256 --card-image CARD.img [--max-reads N] [--file NAME]
                      [--position LAT,LON] [--sdl] [--event SUB:VALUE ...]
                      [--request MESH ...] [--kind 4|0x40] [--client N] [--divid N]
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
    "state": 0xD62490,            # 2 = map ready, requests served; 3 = requests refused (M9.53)
    "mesh_count": 0xD63CA0,       # tile files found in MAPAL001
    "version": 0xD8AD20,          # map format version from the volume header
    "mmain_buf": 0xE23CC0,        # the volume header the map-file layer read
    # leaf functions (no pdata record): header date reader, block-header reader,
    # u16 byte swap of a buffer (record block before and after inflate, M9.53)
    "leaves": (0x0040A8D0, 0x004144A8, 0x003F6968),
    "position": (0xD94 << 12) + 0x0E4,   # u32: (lat code << 16) | lon code
    "default_position_fn": 0x0040B49C,   # (kind) -> start position from a per-area table, or -1
    "ready_msg": (0x07D0, 100),
    "done_msg": 0x04A0,
    "progress": 0xD98FCC,         # 1 = the dispatcher runs deferred rows at once (unless state 3)
    "event_msg": 0x07D0,          # object-store event; the sub is the subscriber's event id
    "state3_sub": 11,             # 0x003f6b1c: state 2 -> 3 when the event's +28 is 16
    "state3_value": 16,
    # the map request (M9.53): message 0x14b5, answered with 0x14b6
    "request_msg": 0x14B5,
    "reply_msg": 0x14B6,
    "client_open": 0x003ED6E8,    # (mode 1, client task id, kind mask, out *): a slot at data VA 0xd98fe0
    "inflate": 0x0054233C,        # zlib inflate (method 8, header check mod 31) of a record block
    "mesh_y": 0x004089F4,         # (mesh id) -> y; y >> 5 is the directory row (B48R058R: 72..79)
    "mesh_x": 0x00408B0C,         # (mesh id) -> x; x >> 5 is the directory column (B48R058R: -88..-81)
}
DA_TASK, MAP_TASK, SDL_TASK = 2, 0x10, 3       # any three different non-zero ids
CLIENT_TASK = 5                                 # the task that sends map requests (any id > 1)
KIND_RENDER, KIND_ROUTE = 4, 0x40               # +16 kinds of the callers in C-5641

# SDL_task of Navi.exe, EU2011 build A (M9.52).  Created by 0x0032efa8 with
# the name "SDL_task" and the entry 0x0039d854; its id lands in the global
# that 0x00401e94 reads as the receiver of message 0x1507.
SDL_EU2011 = {
    "task_id": 0x11FFF50,          # global the data-access task sends 0x1507 to
    "entry": 0x0039D854,           # init + receive loop (not called: we are the loop)
    "init": 0x003C001C,
    "dispatch": 0x0039D6F0,        # (message *): routes by the sender id at +0
    "from_da": 0x0039D18C,         # messages from the data-access task
    "gate": 0x003C009C,            # drops a message that answers no pending request
    "machine": 0x0039CA00,         # (state, table, message, out): the state step after the gate
    "req_id": 0x6F4650,            # u32 id of the pending request; +4: u32 1 = pending
    "state": 0x9379B8,             # u16 state of the SDL machine (table at data VA 0x39e30)
}

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
        self.ticks = 0


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

    def tick(m):
        # SDL_task's trace stamps: a clock that moves, no other meaning
        st.ticks += 1
        return st.ticks
    M["tickGet"] = tick
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


def event_message(sub: int, value: int, build: dict = DA_EU2011) -> bytes:
    """An object-store event as OBJDLL's notifier 0x034942d8 (EU2011) lays it
    out for OSM_MsgSend: +8 id, +10 sub, +12..+28 the event's five words; the
    data-access task reads the last one (+28)."""
    msg = bytearray(32)
    struct.pack_into("<HH", msg, 8, build["event_msg"], sub)
    struct.pack_into("<I", msg, 28, value)
    return bytes(msg)


def request_message(client: int, kind: int, lst: int, build: dict = DA_EU2011) -> bytes:
    """A map request as its callers build it (C-5641): +0 sender, +8 0x14b5,
    +10 sub 2, +12 the client task, +16 kind, +20 the list, +24 2."""
    msg = bytearray(32)
    struct.pack_into("<IIHHIIII", msg, 0, client, 0, build["request_msg"], 2, client, kind, lst, 2)
    return bytes(msg)


def request_list(meshes, divid: int = 0) -> bytes:
    """The list the request points at: u16 count at +0, entry i at 32*i with
    DIVID u16 at +14 and mesh id u32 at +16; 0x2004 bytes (what 0x004066ac
    copies)."""
    blob = bytearray(0x2004)
    struct.pack_into("<H", blob, 0, len(meshes))
    for i, mesh in enumerate(meshes):
        struct.pack_into("<HI", blob, 32 * i + 14, divid, mesh)
    return bytes(blob)


def parse_event(text: str) -> tuple[int, int]:
    sub, _, value = text.partition(":")
    return int(sub, 0), int(value or "0", 0)


def sdl_gate(msg_req: int, pending_req: int, pending: int) -> bool:
    """0x003c009c: SDL_task takes a message from the data-access task only
    when its +12 equals the pending request id and a request is pending."""
    return msg_req == pending_req and pending == 1


def state3_after(state: int, sub: int, value: int, build: dict = DA_EU2011) -> int:
    """The data-access task's state word after one object-store event, as
    0x003f6b1c writes it (only the 2/1 -> 3 step; other subs leave it)."""
    if sub == build["state3_sub"] and value == build["state3_value"] and state != 0:
        return 3
    return state


def answer(send: dict, sdl_req: tuple[int, int] = (0, 0)) -> tuple[bytes | None, str]:
    """The reply model: given one logged send of the data-access task, the
    message that answers it, or None and why.

    Only 0x1507 is modelled.  Its receiver, SDL_task, runs it through
    0x0039d18c, whose gate 0x003c009c drops it unless it answers a request
    SDL_task made (``sdl_req`` = pending id, pending flag).  An accepted
    message goes to SDL_task's state machine, which answers in its own time;
    the tool does not invent that answer."""
    body = bytes.fromhex(send["body"]) if isinstance(send.get("body"), str) else send.get("body", b"")
    if len(body) < 16:
        return None, "no message body"
    msg_id, sub = struct.unpack_from("<HH", body, 8)
    if msg_id != 0x1507:
        return None, "no model for message %#06x" % msg_id
    req = struct.unpack_from("<I", body, 12)[0]
    if not sdl_gate(req, *sdl_req):
        return None, "SDL_task drops %#06x sub %d: +12 = %d answers no pending request" % (msg_id, sub, req)
    return None, "SDL_task accepts %#06x sub %d; its state machine decides the answer" % (msg_id, sub)


# --------------------------------------------------------------------------

class DataTask:
    """The data-access task and the map-file task on one virtual card."""

    def __init__(self, image: str, card, build: dict = DA_EU2011, position=None, sdl: bool = False):
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
        # 0x0032efa8 stores each task id right after OSM_TaskCreate, before
        # the task runs its own initialisation: the init code already reads
        # them (it subscribes object-store events for *0x011fff58).
        m.put(build["da_task_id"], struct.pack("<I", DA_TASK))
        m.put(build["map_task_id"], struct.pack("<I", MAP_TASK))
        for va in build["init"]:
            m.call(va, [], max_insns=80_000_000)
        self.sdl = None
        self.sdl_log: list[dict] = []
        if sdl:
            self.sdl = SDL_EU2011
            m.put(self.sdl["task_id"], struct.pack("<I", SDL_TASK))
            self.st.task = SDL_TASK
            m.call(self.sdl["init"], [], max_insns=80_000_000)
            self.st.task = DA_TASK
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
        self.events: list[dict] = []
        self.inflated: list[dict] = []
        self.request = None
        self.requests_log: list[dict] = []
        self.client_open: dict[int, int] = {}
        m.eng.on_exec(build["inflate"], self._on_inflate)

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

    def _on_read(self, engine, va):
        m = self.m
        req = decode_request(bytes(m.eng.read_mem(m.arg(1), 16)))
        req["fid"] = m.arg(0)
        self.requests[req["dst"]] = req
        return None

    def _on_inflate(self, engine, va):
        """Entry of inflate: watch the output window (stream +12 next_out,
        +16 avail_out) so the row can say who reads the inflated record."""
        m, e = self.m, self.m.eng
        z = m.arg(0)
        nxt, avail = m.u32(z + 12), m.u32(z + 16)
        self.inflated.append({"out": nxt, "avail": avail, "in": m.u32(z + 4)})
        if e._watches_on and avail and e.region_at(nxt) is not None and e.region_at(nxt + avail - 1) is not None:
            e.watch(nxt, nxt + avail, "r", "record%d" % len(self.inflated))
        return None

    def mesh_xy(self, mesh: int) -> tuple[int, int]:
        """The firmware's own decoders: (y, x) of a mesh id."""
        s32 = lambda v: v - (1 << 32) if v & 0x80000000 else v
        return (s32(self.m.call(self.b["mesh_y"], [mesh]) & V.M32),
                s32(self.m.call(self.b["mesh_x"], [mesh]) & V.M32))

    def request_mesh(self, mesh: int, kind: int = KIND_RENDER, client: int = CLIENT_TASK,
                     divid: int = 0, want_bytes: bool = False, on_row=None, open_client: bool = True) -> dict:
        """Send one map request (message 0x14b5) for one mesh as client
        ``client`` and carry until idle.  The client is first opened with
        0x003ed6e8 (mode 1, as SDL_task's init does), since 0x00405970
        answers status 9 to a task with no slot."""
        m = self.m
        if open_client and (client, kind) not in self.client_open:
            out = m.malloc(16)
            m.put(out, bytes(16))
            self.st.task = client
            self.client_open[(client, kind)] = m.call(self.b["client_open"], [1, client, kind, out]) & V.M32
            self.st.task = DA_TASK
            m.free(out)
        lst = m.malloc(0x2004)
        m.put(lst, request_list([mesh], divid))
        y, x = self.mesh_xy(mesh)
        entry = {"mesh": mesh, "kind": kind, "client": client, "divid": divid, "y": y, "x": x,
                 "state": m.u32(self.b["state"]), "first_row": len(self.rows), "replies": []}
        self.request = mesh
        before = len(m.messages)
        try:
            self.deliver(request_message(client, kind, lst, self.b))
            entry["end"] = self._carry(0, want_bytes, on_row)
        finally:
            self.request = None
        for x_ in m.messages[before:]:
            if x_["kind"] == "send" and x_["task"] == client:
                body = bytes.fromhex(x_["body"])
                mid, sub = struct.unpack_from("<HH", body, 8)
                entry["replies"].append({"id": mid, "sub": sub, "words": list(struct.unpack_from("<5I", body, 12))})
        entry["rows"] = len(self.rows) - entry["first_row"]
        self.requests_log.append(entry)
        return entry

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

    def sdl_turn(self, body: bytes) -> dict:
        """Hand one message to SDL_task's dispatcher and record what it did."""
        m, s = self.m, self.sdl
        seen: list[int] = []
        hooks = (s["from_da"], s["gate"], s["machine"])
        for va in hooks:
            m.eng.on_exec(va, (lambda v: (lambda e, _va: seen.append(v)))(va))
        before = len(m.messages)
        req = (m.u32(s["req_id"]), m.u32(s["req_id"] + 4))
        self.st.task = SDL_TASK
        p = m.malloc(64)
        m.put(p, body.ljust(64, b"\0"))
        try:
            r0 = m.call(s["dispatch"], [p], max_insns=400_000_000)
        finally:
            m.free(p)
            for va in hooks:
                m.eng._hooks[va].pop()
            self.st.task = DA_TASK
        msg_id, sub = struct.unpack_from("<HH", body, 8)
        model = answer({"body": body}, req)
        entry = {"id": msg_id, "sub": sub, "r0": r0, "via": [hex(v) for v in seen],
                 "gate_dropped": s["gate"] in seen and s["machine"] not in seen,
                 "sent": len(m.messages) - before, "sdl_state": m.u32(s["state"]) & 0xFFFF,
                 "pending_request": list(req), "model": model[1]}
        self.sdl_log.append(entry)
        return entry

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
        self.inflated = []
        if n:
            e.watch(buf, buf + n, "r", "buffer")
            e.arm_watch()
        first = len(self.called)
        try:
            self.deliver(body)
        finally:
            e.disarm_watch()
        by: dict[int, list[int]] = {}
        rec: dict[int, list[int]] = {}
        out_lo = {w.name: w.lo for w in e._watches}
        for hit in e.watch_hits():
            if hit.kind != "r":
                continue
            fn = self.fn_of(hit.pc)
            if fn is None:                    # a leaf function has no pdata record
                fn = self.leaf_start(hit.pc)
            if hit.name == "buffer":
                by.setdefault(fn, []).extend(range(hit.va - buf, hit.va - buf + hit.size))
            else:                             # "record": the inflated output
                lo = out_lo[hit.name]
                rec.setdefault(fn, []).extend(range(hit.va - lo, hit.va - lo + hit.size))
        e._watch_hits.clear()
        handler = self.called[first] if len(self.called) > first else None
        row = {"tag": tag, "status": status, "length": n, "fid": req.get("fid"),
               "file": self.names.get(req.get("fid"), "?"), "pos": req.get("pos"),
               "handler": handler, "expected_handler": done_lookup(self.done_table, tag),
               "readers": [{"fn": fn, "bytes": len(set(v)), "runs": runs(v) if want_bytes else runs(v)[:10],
                            "nruns": len(runs(v))} for fn, v in by.items()]}
        if self.inflated:
            row["inflated"] = self.inflated
            row["record_readers"] = [{"fn": fn, "bytes": len(set(v)), "runs": runs(v)[:10], "nruns": len(runs(v))}
                                     for fn, v in rec.items()]
        if self.request is not None:
            row["request"] = self.request
        self.rows.append(row)
        return row

    def run(self, max_reads: int = 0, want_bytes: bool = False, on_row=None, events=()) -> str:
        """Announce the map and carry messages until the tasks are idle; then
        deliver each stand-in event of ``events`` ((sub, value) pairs) and
        carry again."""
        self.deliver(ready_message())
        end = self._carry(max_reads, want_bytes, on_row)
        for sub, value in events:
            if end.startswith("stopped"):
                break
            self.events.append({"sub": sub, "value": value, "state_before": self.m.u32(self.b["state"])})
            self.deliver(event_message(sub, value, self.b))
            end = self._carry(max_reads, want_bytes, on_row)
            self.events[-1]["state_after"] = self.m.u32(self.b["state"])
        return end

    def _carry(self, max_reads: int, want_bytes: bool, on_row) -> str:
        m = self.m
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
            elif self.sdl is not None and x["task"] == SDL_TASK:
                self.sdl_turn(body)
            else:
                self.other.append({"kind": "send", "task": x["task"], "id": msg_id, "sub": sub,
                                   "from": (x["pr"] - 4) & V.M32})

    def summary(self) -> dict:
        m = self.m
        return {"state": m.u32(self.b["state"]), "progress": m.u32(self.b["progress"]),
                "mesh_count": m.u32(self.b["mesh_count"]),
                "version": m.u32(self.b["version"]), "reads": len(self.rows),
                "zero_models": self.st.zeroed}


def show_row(row: dict) -> None:
    role = HANDLER_ROLE.get(row["handler"], "")
    print("tag %#06x  %-28s pos %#10x len %#7x  handler %s  %s" % (
        row["tag"], row["file"], row["pos"] or 0, row["length"],
        ("%#010x" % row["handler"]) if row["handler"] else "-", role))
    for r in row["readers"]:
        print("      fn %#010x loads %6d B: %s" % (r["fn"], r["bytes"], show_runs(r["runs"])))
    for z in row.get("inflated", []):
        print("      inflate %#010x: output window %#x bytes" % (DA_EU2011["inflate"], z["avail"]))
    for r in row.get("record_readers", []):
        print("      fn %#010x loads %6d B of the inflated record: %s" % (r["fn"], r["bytes"], show_runs(r["runs"])))


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
        events = [parse_event(e) for e in args.event]
        t = DataTask(args.image, card, position=position, sdl=args.sdl)
        print("position: %s (default %.3f, %.3f)" % (
            ("%.3f, %.3f" % position) if position else "default", *decode_position(t.default_position)))
        want = args.file.upper() if args.file else None

        def on_row(row):
            if want is None or want in row["file"].upper():
                show_row(row)
        end = t.run(args.max_reads, args.bytes, on_row, events)
        for mesh in args.request:
            print("map request %#06x for mesh %#010x (kind %#x, client %d):" % (
                DA_EU2011["request_msg"], mesh, args.kind, args.client))
            r = t.request_mesh(mesh, args.kind, args.client, args.divid, args.bytes, on_row)
            print("  mesh y %d x %d (directory row %d, column %d); state %d; %d read(s); %s" % (
                r["y"], r["x"], r["y"] >> 5, r["x"] >> 5, r["state"], r["rows"], r["end"]))
            for rep_ in r["replies"]:
                print("  reply %#06x sub %d: %s" % (rep_["id"], rep_["sub"], " ".join("%#x" % w for w in rep_["words"])))
    except (V.Blocked, V.EngineError) as exc:
        print("BLOCKED: %s: %s" % (type(exc).__name__, str(exc)[:300]))
        return 3
    out = t.summary()
    out["end"] = end
    print("end: %s; state %d, progress %d, tile files %d, map version %#x, reads %d" % (
        end, out["state"], out["progress"], out["mesh_count"], out["version"], out["reads"]))
    for o in t.other:
        print("not delivered: %s" % json.dumps(o))
    for e in t.sdl_log:
        print("SDL_task got %#06x sub %d: %s (gate %s, SDL state %d, sends %d); model: %s" % (
            e["id"], e["sub"], " -> ".join(e["via"]) or "-",
            "dropped it" if e["gate_dropped"] else "passed it", e["sdl_state"], e["sent"], e["model"]))
    for e in t.events:
        print("event model (stand-in, sender not in the run): %#06x sub %d +28=%d: state %d -> %d" % (
            DA_EU2011["event_msg"], e["sub"], e["value"], e["state_before"], e.get("state_after", -1)))
    if out["zero_models"]:
        print("models that return 0 and write nothing: %s" % ", ".join(out["zero_models"]))
    tiles = [r for r in t.rows if is_tile(r)]
    print("tile reads parsed by the firmware: %d" % len(tiles))
    if args.json:
        out["rows"] = t.rows
        out["other"] = t.other
        out["sdl"] = t.sdl_log
        out["events"] = t.events
        out["requests"] = t.requests_log
        Path(args.json).write_text(json.dumps(out, indent=1))
    return 0 if tiles else 1


def row_key(row: dict) -> tuple:
    return (row["file"].upper(), row["tag"], row["pos"], row["length"])


def row_shape(row: dict) -> tuple:
    """What the firmware did with one read: handler and, per function, how
    many bytes it loaded and in how many runs."""
    return (row["handler"], tuple(sorted((r["fn"], r["bytes"], r["nruns"]) for r in row["readers"])),
            tuple(sorted((r["fn"], r["bytes"], r["nruns"]) for r in row.get("record_readers", []))))


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
            for r in ra.get("record_readers", []):
                fa[("record", r["fn"])] = (r["bytes"], r["nruns"])
            for r in rb.get("record_readers", []):
                fb[("record", r["fn"])] = (r["bytes"], r["nruns"])
            name = (lambda k: ("inflated record: fn %#010x" % k[1]) if isinstance(k, tuple) else ("fn %#010x" % k))
            parts = ["%s A %s B %s" % (name(fn), fa.get(fn), fb.get(fn))
                     for fn in sorted(set(fa) | set(fb), key=lambda k: (isinstance(k, tuple), k if isinstance(k, int) else k[1]))
                     if fa.get(fn) != fb.get(fn)]
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
            p.add_argument("--sdl", action="store_true",
                           help="run SDL_task too and carry message 0x1507 to it (M9.52)")
            p.add_argument("--event", action="append", default=[], metavar="SUB:VALUE",
                           help="after the mount idles, deliver object-store event 0x07d0 sub SUB "
                                "with +28 = VALUE (a stand-in: its sender is not in the run)")
            p.add_argument("--request", action="append", default=[], type=lambda v: int(v, 0), metavar="MESH",
                           help="after the mount (and events), send map request 0x14b5 for this mesh id "
                                "(M9.53); repeat for more")
            p.add_argument("--kind", type=lambda v: int(v, 0), default=KIND_RENDER,
                           help="request kind at +16: 4 renderer (default), 0x40 router")
            p.add_argument("--client", type=int, default=CLIENT_TASK, help="client task id (> 1)")
            p.add_argument("--divid", type=lambda v: int(v, 0), default=0, help="DIVID u16 of the list entry")
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
    rq = request_message(5, KIND_RENDER, 0x1234)
    check("a map request carries 0x14b5 sub 2, client at +0 and +12, kind, list, 2",
          struct.unpack_from("<IIHHIIII", rq) == (5, 0, 0x14B5, 2, 5, 4, 0x1234, 2))
    rl = request_list([0x26C18AB2], 7)
    check("the request list holds a count and DIVID/mesh at +14/+16 of entry 0",
          len(rl) == 0x2004 and struct.unpack_from("<H", rl)[0] == 1
          and struct.unpack_from("<HI", rl, 14) == (7, 0x26C18AB2))
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

    check("an object-store event is id 0x07d0, the sub, and its value at +28",
          struct.unpack_from("<HH", event_message(11, 16), 8) == (0x07D0, 11)
          and struct.unpack_from("<I", event_message(11, 16), 28)[0] == 16)
    check("--event parses SUB:VALUE in any base", parse_event("11:0x10") == (11, 16) and parse_event("13") == (13, 0))
    check("SDL's gate passes only the answer to a pending request",
          sdl_gate(7, 7, 1) and not sdl_gate(0, 0, 0) and not sdl_gate(6, 7, 1) and not sdl_gate(7, 7, 2))
    check("event 11 with +28 = 16 moves state 2 to 3", state3_after(2, 11, 16) == 3)
    check("event 11 with another value, or another sub, leaves state 2",
          state3_after(2, 11, 15) == 2 and state3_after(2, 12, 16) == 2)
    check("event 11 before the mount started (state 0) does nothing", state3_after(0, 11, 16) == 0)
    m1507 = bytearray(32)
    struct.pack_into("<IHH", m1507, 4, 0, 0x1507, 1)
    check("reply model: 0x1507 with no pending request has no answer",
          answer({"body": bytes(m1507).hex()})[0] is None and "drops" in answer({"body": bytes(m1507).hex()})[1])
    check("reply model: an answer to a pending request is passed to SDL's machine",
          "accepts" in answer({"body": bytes(m1507)}, (0, 1))[1])
    check("reply model: other messages are not modelled",
          "no model" in answer({"body": bytes(ready_message())})[1])

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
        try:
            t = DataTask(str(head), V.make_card(None, str(card_img)), sdl=True)
            check("SDL_task starts in state 0 with no pending request",
                  t.m.u32(SDL_EU2011["state"]) & 0xFFFF == 0 and t.m.u32(SDL_EU2011["req_id"] + 4) == 0)
            e = t.sdl_turn(struct.pack("<I", DA_TASK) + bytes(m1507[4:]))   # +0: the sender, as 0x00401e94 sets it
            check("SDL_task drops 0x1507 at its gate and sends nothing",
                  e["gate_dropped"] and e["sent"] == 0 and e["via"][:2] == ["0x39d18c", "0x3c009c"])
            # positive control of the gate: with a request pending (id 0) the
            # same message passes the gate and reaches SDL's state step
            t.m.put(SDL_EU2011["req_id"], struct.pack("<II", 0, 1))
            e = t.sdl_turn(struct.pack("<I", DA_TASK) + bytes(m1507[4:]))
            check("with a request pending the same 0x1507 passes the gate to 0x0039ca00",
                  not e["gate_dropped"] and "0x39ca00" in e["via"])
            t.m.put(SDL_EU2011["req_id"], struct.pack("<II", 0, 0))
            t.deliver(ready_message())         # 0x003f75e4: state 2, the mount starts
            check("the ready message sets the state word to 2", t.m.u32(DA_EU2011["state"]) == 2)
            t.deliver(event_message(11, 15))
            check("event 11 with +28 = 15 leaves the state word at 2", t.m.u32(DA_EU2011["state"]) == 2)
            t.deliver(event_message(11, 16))
            check("event 11 with +28 = 16 sets the state word to 3 (0x003f6b1c)", t.m.u32(DA_EU2011["state"]) == 3)
        except (V.Blocked, V.EngineError) as exc:
            check("firmware run (%s)" % str(exc)[:80], False)
        finally:
            V.MODELS.clear()
            V.MODELS.update(saved)
        try:                                   # M9.53: one map request after a full mount
            t = DataTask(str(head), V.make_card(None, str(card_img)), position=(51.70, 17.45))
            t.run()
            mesh = 0x26C18AB2                  # y 2481, x -2642: directory row 77, column -83
            check("the firmware decodes the mesh to directory row 77, column -83",
                  tuple(v >> 5 for v in t.mesh_xy(mesh)) == (77, -83))
            r = t.request_mesh(mesh, client=7, open_client=False)
            check("a client without a slot is answered 0x14b6 status 9 and nothing is read",
                  r["rows"] == 0 and [(x["id"], x["sub"], x["words"][0]) for x in r["replies"]] == [(0x14B6, 5, 9)])
            r = t.request_mesh(mesh)
            row = t.rows[-1] if r["rows"] else {}
            check("with a slot the request reads one record block (tag 0x0900, handler 0x00404ee4)",
                  r["rows"] == 1 and row.get("tag") == 0x0900 and row.get("handler") == 0x00404EE4)
            check("the record block is inflated and its 11172 bytes are swapped by 0x003f6968",
                  len(row.get("inflated", [])) == 1
                  and any(x["fn"] == 0x003F6968 and x["bytes"] == 11172 for x in row.get("record_readers", [])))
            check("the reply is 0x14b6 sub 9 naming the mesh",
                  any(x["sub"] == 9 and x["words"][1] == mesh for x in r["replies"]))
            t.deliver(event_message(11, 16))
            r = t.request_mesh(mesh)
            check("in state 3 the same request is refused (status 9, no read)",
                  r["state"] == 3 and r["rows"] == 0 and any(x["sub"] == 5 and x["words"][0] == 9 for x in r["replies"]))
        except (V.Blocked, V.EngineError) as exc:
            check("firmware run (%s)" % str(exc)[:80], False)
        finally:
            V.MODELS.clear()
            V.MODELS.update(saved)
    print("datask_l3 selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
