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
  datask_l3.py port   IMG256 --us-image US256 --card-image CARD.img [--request MESH ...]
  datask_l3.py diff   A.json B.json [--file NAME]
  datask_l3.py mount  IMG256 --card-image CARD.img [--max-reads N] [--file NAME]
                      [--position LAT,LON] [--sdl] [--event SUB:VALUE ...]
                      [--request MESH ...] [--kind 4|0x40] [--client N] [--divid N]
                      [--bytes] [--json OUT] [--flip MAPAL001/LEV3456R.DAT@0x803:0x01]

`port` is the M9.61 Stop gate: it runs the EU mount (+ its requests), hooks
every EU `.pdata` START to record entry, and asks `fn_match` for the US pair
of each entered EU function (content hash, then the ANCHOR pass).  It prints
the verdict census and the unpaired list and exits 1 below `--min-percent`
(default 90).

Exit codes: mount: 0 the run finished and at least one tile read was parsed,
1 no tile read was parsed; port: 1 below --min-percent; diff: 0 SAME,
1 DIFFERENT; 3 BLOCKED (missing model, engine stop); 2 usage or missing
input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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
    "position": (0xD94 << 12) + 0x0E4,   # u32: (lat code << 16) | lon code (0x003F6908 names it)
    "default_position_fn": 0x0040B49C,   # (kind) -> start position from a per-area table, or -1
    # directory read length (M3.31): leaf (kind, column) -> u32 from a
    # 16-row table {u32 kind, u32 length / 0x100, u32 buffer size}; the
    # directory request of 0x00414338 asks column 1 for the level-table kind
    "len_lookup": 0x0040901C,
    "len_table": ((0x179 << 12) + 0xC08, 16),
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
# The same data-access task in the US2011 build A (`archive/us256.img`,
# SHA-256 70d945d8…04da; M9.61).  Every function is the fn_match pair of the
# EU function above and a pdata START in the US image (or a GAP leaf, for the
# five `leaves`) ; the tables were read from the US image and hold the same
# keys in the same order (handlers differ) ; data addresses are the pool value
# at the same load index of the paired `init` function.  Handlers are the US
# VAs of each role, not a fitted delta: the EU->US shift differs by handler
# (+0x28100 for most, +0x28960, +0x27dd0, …), which is why one delta fails.
DA_US2011 = {
    "build": "US2011",
    "task_entry": 0x00414AD4,     # fn_match pair of 0x003EBFB4, pdata START
    "init": (0x0041F268, 0x00414598),   # 0x003F6908 -> 0x0041F268; 0x003EBA78 -> 0x00414598
    "dispatch": 0x00414A08,       # pair of 0x003EBEE8
    "msg_table": 0x15E9D0,        # 43 rows {u16 id, u16 defer, u32 handler}, same keys/order as EU
    "msg_rows": 43,
    "sub_tables": {0x07D0: (0x1600CC, 6), 0x00A0: (0x16009C, 5)},   # same subs as EU
    "done_handler": 0x0041FC44,   # pair of 0x003F72E4: message 0x04a0
    "done_table": 0x15F760,       # 20 rows {u16 tag class, u16 0, u32 handler}
    "done_rows": 20,
    "read_api": 0x00440180,       # pair of 0x0041841C (ANCHOR: 12-byte stub, same pdata offset)
    "da_task_id": 0x011031BC,     # global: task id the reply goes to
    "map_task_id": 0x0110321C,    # global: task id of the map-file task
    "state": 0x00C90090,          # 2 = map ready, requests served; 3 = requests refused (M9.53)
    "mesh_count": 0x00C918A0,     # tile files found in MAPAL001
    "version": 0x00CB8920,        # map format version from the volume header
    "mmain_buf": 0x00D518C0,      # the volume header the map-file layer read
    "leaves": (0x004329D0, 0x0043C278, 0x0041F2C8),   # pairs of 0x0040A8D0, 0x004144A8, 0x003F6968
    "position": (0x0CC1 << 12) + 0x0CE4,   # u32: (lat code << 16) | lon code (0x003EBA78 load 172)
    "default_position_fn": 0x0043359C,   # pair of 0x0040B49C
    "len_lookup": 0x0043111C,     # pair of 0x0040901C (GAP leaf, identical instructions)
    "len_table": (0x1605E0, 16),  # the leaf's pool at 0x00431148 names it
    "ready_msg": (0x07D0, 100),
    "done_msg": 0x04A0,
    "progress": 0x00CC6BCC,       # pair of 0xD98FCC
    "event_msg": 0x07D0,          # object-store event; the sub is the subscriber's event id
    "state3_sub": 11,             # 0x0041F47C: state 2 -> 3 when the event's +28 is 16
    "state3_value": 16,
    "request_msg": 0x14B5,
    "reply_msg": 0x14B6,
    "client_open": 0x00416208,    # pair of 0x003ED6E8
    "inflate": 0x00564638,        # pair of 0x0054233C
    "mesh_y": 0x00430AF4,         # pair of 0x004089F4
    "mesh_x": 0x00430C0C,         # pair of 0x00408B0C
}
BUILDS = {"eu2011": DA_EU2011, "us2011": DA_US2011}

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
# ... and in the US2011 build (M9.61).  Pairs from fn_match; the data cells are
# the pool value at the same load index of the paired init function.  Only
# --sdl runs this dict and M9.61 does not (the mount does not wait for 0x1507);
# it is here so --sdl --build us2011 does not run EU addresses.
SDL_US2011 = {
    "task_id": 0x011031B4,         # pair of 0x11FFF50
    "entry": 0x003CDCDC,           # pair of 0x0039D854
    "init": 0x003EEE40,
    "dispatch": 0x003CDB78,
    "from_da": 0x003CD614,
    "gate": 0x003EEEC0,
    "machine": 0x003CCE88,
    "req_id": 0x00733D00,
    "state": 0x00977060,
}
SDL_BUILDS = {"eu2011": SDL_EU2011, "us2011": SDL_US2011}

# what each completion handler is, from the reads it was seen to serve.  The
# role is keyed by the EU function; the US table lists the US VA of each role.
HANDLER_ROLE = {
    0x0040B8B4: "file header (first 0x1000 bytes)",
    0x0040C308: "section table",
    0x0041597C: "directory",
    0x003F72CC: "REFER001 search data",
}
HANDLER_ROLE_US = {0x004339B4: "file header (first 0x1000 bytes)",
                   0x00434408: "section table",
                   0x0043D74C: "directory",
                   0x0041FC2C: "REFER001 search data"}
HANDLER_ROLES = {"eu2011": HANDLER_ROLE, "us2011": HANDLER_ROLE_US}


class State:
    """What the models need to share with the tool."""

    def __init__(self):
        self.task = 1
        self.sems = 0x5E00
        self.datavol = None
        self.zeroed: list[str] = []
        self.ticks = 0
        self.build = DA_EU2011           # the per-build table the models read


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
            data = bytes(m.eng.read_mem(st.build["mmain_buf"], 0x1000))
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


def reader_entry(key, offsets, want_bytes: bool) -> dict:
    """One reader of a buffer: a function's own loads (key = fn), or the
    loads of a memcpy/memmove model it called (key = (fn, "memmove"))."""
    fn, via = key if isinstance(key, tuple) else (key, None)
    rr = runs(offsets)
    out = {"fn": fn, "bytes": len(set(offsets)), "runs": rr if want_bytes else rr[:10], "nruns": len(rr)}
    if via:
        out["via"] = via
    return out


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


def ready_message(build: dict = DA_EU2011) -> bytes:
    msg = bytearray(32)
    struct.pack_into("<HH", msg, 8, *build["ready_msg"])
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
        self.st.build = build
        install_models(self.st)
        out, s = V.boot_report(image, card, build=V.BUILDS[build["build"].lower()])
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
            self.sdl = SDL_BUILDS[build["build"].lower()]
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
        copies: list[tuple[str, int, str, int, int]] = []
        saved = {k: V.MODELS[k] for k in ("memcpy", "memmove") if k in V.MODELS}

        def copy_logger(name, inner):
            # memcpy/memmove are Python models (vcard_l3.py), so the engine's
            # watch never sees their loads: log the source overlap here and
            # charge it to the calling function.
            def wrapped(mm):
                src, cnt = mm.arg(1), mm.arg(2)
                if e._watches_on and cnt:
                    pc = (mm.reg("pr") - 4) & V.M32
                    fn = self.fn_of(pc) or self.leaf_start(pc)
                    for w in e._watches:
                        lo, hi = max(src, w.lo), min(src + cnt, w.hi)
                        if lo < hi:
                            copies.append((w.name, fn, name, lo - w.lo, hi - w.lo))
                return inner(mm)
            return wrapped
        for k, f in saved.items():
            V.MODELS[k] = copy_logger(k, f)
        try:
            self.deliver(body)
        finally:
            e.disarm_watch()
            V.MODELS.update(saved)
        by: dict = {}
        rec: dict = {}
        out_lo = {w.name: w.lo for w in e._watches}
        for wname, fn, via, lo, hi in copies:
            (by if wname == "buffer" else rec).setdefault((fn, via), []).extend(range(lo, hi))
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
               "len_lookup": req.get("len_lookup"),
               "readers": [reader_entry(k, v, want_bytes) for k, v in by.items()]}
        if self.inflated:
            row["inflated"] = self.inflated
            row["record_readers"] = [reader_entry(k, v, False) for k, v in rec.items()]
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


def show_row(row: dict, handler_role: dict = HANDLER_ROLE, inflate: int = 0x0054233C) -> None:
    role = handler_role.get(row["handler"], "")
    print("tag %#06x  %-28s pos %#10x len %#7x  handler %s  %s" % (
        row["tag"], row["file"], row["pos"] or 0, row["length"],
        ("%#010x" % row["handler"]) if row["handler"] else "-", role))
    lk = row.get("len_lookup")
    if lk:
        print("      length from 0x0040901c(kind %#x, %d) = %#x -> %#x B (call at %#010x)%s" % (
            lk["kind"], lk["column"], lk["value"], lk["value"] * 0x100, lk["from"],
            "" if lk["value"] * 0x100 == row["length"] else "  [not this read's length]"))
    for r in row["readers"]:
        print("      fn %#010x %s %6d B: %s" % (r["fn"], ("%s copies" % r["via"]) if r.get("via") else "loads",
                                            r["bytes"], show_runs(r["runs"])))
    for z in row.get("inflated", []):
        print("      inflate %#010x: output window %#x bytes" % (inflate, z["avail"]))
    for r in row.get("record_readers", []):
        print("      fn %#010x %s %6d B of the inflated record: %s" % (
            r["fn"], ("%s copies" % r["via"]) if r.get("via") else "loads", r["bytes"], show_runs(r["runs"])))


def is_tile(row: dict) -> bool:
    return row["file"].upper().startswith("MAPAL001/") and bool(row["readers"])


def cmd_tables(args) -> int:
    build = BUILDS[args.build]
    card = V.make_card(args.card_root, args.card_image) if (args.card_root or args.card_image) else None
    if card is None:
        # the tables are constant data: read them from the image alone
        m = V.load_machine(args.image, V.Card(V.MemorySource({})))
        rd = lambda va, n: bytes(m.eng.read_mem(va, n))
        b = build
        msg = decode_table(rd(b["msg_table"], 8 * b["msg_rows"]), b["msg_rows"])
        done = decode_table(rd(b["done_table"], 8 * b["done_rows"]), b["done_rows"])
        subs = {k: decode_table(rd(va, 8 * n), n) for k, (va, n) in b["sub_tables"].items()}
    else:
        t = DataTask(args.image, card, build=build)
        msg, done, subs = t.msg_table, t.done_table, t.sub_tables
    print("message table (%d rows): id  defer  handler" % len(msg))
    for key, flag, h in msg:
        print("  %#06x  %d  %#010x" % (key, flag, h))
    for k, rows in subs.items():
        print("sub-table of message %#06x: sub  handler" % k)
        for key, _flag, h in rows:
            print("  %#06x  %#010x" % (key, h))
    print("read-completion table (%d rows): tag class  handler" % len(done))
    roles = HANDLER_ROLES[args.build]
    for key, _flag, h in done:
        print("  %#06x  %#010x  %s" % (key, h, roles.get(h, "")))
    return 0


def card_record(args, card) -> dict:
    """What this run served: the card source, the mods asked for and, per
    overlaid path, the size and SHA-256 of the bytes the firmware was given
    (``None`` for a hidden file).  H106: a run on a generated tile names the
    tile it ran on, so a verdict cannot be quoted for a file it did not read."""
    overlay = []
    for path in sorted(card.overlay):
        data = card.overlay[path]
        overlay.append({"path": path, "size": None if data is None else len(data),
                        "sha256": None if data is None else hashlib.sha256(data).hexdigest()})
    return {"image": getattr(args, "card_image", None), "root": getattr(args, "card_root", None),
            "mods": V.parse_mods(args), "overlay": overlay}


def cmd_mount(args) -> int:
    build = BUILDS[args.build]
    card = V.make_card(args.card_root, args.card_image, V.parse_mods(args))
    served = card_record(args, card)
    for o in served["overlay"]:
        print("card overlay: %s <- %s" % (o["path"], "hidden" if o["sha256"] is None
                                          else "%d bytes sha256 %s" % (o["size"], o["sha256"])))
    try:
        position = None
        if args.position:
            lat, _, lon = args.position.partition(",")
            position = (float(lat), float(lon))
        events = [parse_event(e) for e in args.event]
        t = DataTask(args.image, card, build=build, position=position, sdl=args.sdl)
        print("position: %s (default %.3f, %.3f)" % (
            ("%.3f, %.3f" % position) if position else "default", *decode_position(t.default_position)))
        want = args.file.upper() if args.file else None
        roles = HANDLER_ROLES[args.build]

        def on_row(row):
            if want is None or want in row["file"].upper():
                show_row(row, roles, build["inflate"])
        end = t.run(args.max_reads, args.bytes, on_row, events)
        for mesh in args.request:
            print("map request %#06x for mesh %#010x (kind %#x, client %d):" % (
                build["request_msg"], mesh, args.kind, args.client))
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
            build["event_msg"], e["sub"], e["value"], e["state_before"], e.get("state_after", -1)))
    if out["zero_models"]:
        print("models that return 0 and write nothing: %s" % ", ".join(out["zero_models"]))
    tiles = [r for r in t.rows if is_tile(r)]
    print("tile reads parsed by the firmware: %d" % len(tiles))
    if args.json:
        out["card"] = served
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
    return (row["handler"], tuple(sorted((r["fn"], r.get("via") or "", r["bytes"], r["nruns"]) for r in row["readers"])),
            tuple(sorted((r["fn"], r.get("via") or "", r["bytes"], r["nruns"]) for r in row.get("record_readers", []))))


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
            def keyed(row_):
                d = {("", r["fn"], r.get("via") or ""): (r["bytes"], r["nruns"]) for r in row_["readers"]}
                d.update({("inflated record: ", r["fn"], r.get("via") or ""): (r["bytes"], r["nruns"])
                          for r in row_.get("record_readers", [])})
                return d
            fa, fb = keyed(ra), keyed(rb)
            name = (lambda k: "%sfn %#010x%s" % (k[0], k[1], (" via " + k[2]) if k[2] else ""))
            parts = ["%s A %s B %s" % (name(k), fa.get(k), fb.get(k))
                     for k in sorted(set(fa) | set(fb)) if fa.get(k) != fb.get(k)]
            if ra["handler"] != rb["handler"]:
                parts.insert(0, "handler A %s B %s" % (ra["handler"], rb["handler"]))
            out.append("read %d (%s pos %#x len %#x) parsed differently: %s" % (
                i + 1, ra["file"], ra["pos"] or 0, ra["length"], "; ".join(parts)))
    return out


def port_census(rows: list[tuple], good=("UNIQUE", "ANCHOR", "DIFFERENT", "CALLORDER"),
                min_percent: float = 90.0):
    """Count fn_match verdicts of (eu, us, verdict) rows and decide the gate.

    Returns (counts, unpaired, percent, ok).  An ``AMBIGUOUS``/``NOMATCH`` row
    is unpaired: it has no US address (M9.61 Stop)."""
    count: dict = {}
    for _eu, _us, verdict in rows:
        count[verdict] = count.get(verdict, 0) + 1
    unpaired = [r for r in rows if r[2] not in good]
    pct = 100.0 * (len(rows) - len(unpaired)) / len(rows) if rows else 0.0
    return count, unpaired, pct, pct >= min_percent


def cmd_port(args) -> int:
    """M9.61 Stop gate: every EU function start the mount (+ requests) enters
    gets a US pair from fn_match; exit 1 below --min-percent."""
    import contextlib
    import io
    import fn_match

    card = V.make_card(args.card_root, args.card_image, V.parse_mods(args))
    position = None
    if args.position:
        lat, _, lon = args.position.partition(",")
        position = (float(lat), float(lon))
    t = DataTask(args.image, card, position=position, sdl=args.sdl)
    import pdata
    records, _meta = pdata.load_table(Path(args.image).read_bytes(), V.IMAGE_A, "Navi.exe")
    starts = sorted({rec[0] for rec in records})
    entered: set[int] = set()
    for va in starts:
        t.m.eng.on_exec(va, lambda e, v: (entered.add(v), None)[1])
    t.run(args.max_reads)
    for mesh in args.request:
        t.request_mesh(mesh, args.kind, args.client, args.divid)
    tries = fn_match.Matcher(args.image, args.us_image, "Navi.exe", V.IMAGE_A, 2, 2, None, None)
    base = {}
    with contextlib.redirect_stdout(io.StringIO()):
        for f in tries.fa:
            base[f[0]] = tries.verdict(f[0])
    b_index = {f[0]: j for j, f in enumerate(tries.fb)}
    amap = {}
    for i, f in enumerate(tries.fa):
        bva, verdict = base[f[0]][1], base[f[0]][2]
        if verdict in fn_match.MATCHED and bva in b_index:
            amap[i] = b_index[bva]
    anchored, _owner = fn_match.anchor_verdicts(tries, base, sorted(amap), amap)
    for va, bva in anchored.items():
        base[va] = (va, bva, "ANCHOR", base[va][3])
    rows, count = [], {}
    for va in sorted(entered):
        v = base.get(va)
        if v is None:
            with contextlib.redirect_stdout(io.StringIO()):
                v = tries.verdict(va)
        rows.append((va, v[1], v[2]))
    count, unpaired, pct, ok = port_census(rows, min_percent=args.min_percent)
    print("EU function starts entered during mount+request: %d" % len(rows))
    print("verdicts: %s" % dict(sorted(count.items())))
    print("unpaired: %d%s" % (len(unpaired), "".join(
        "\n  %#010x  %s" % (va, verdict) for va, _b, verdict in unpaired)))
    print("percent paired: %.1f%% of %d" % (pct, len(rows)))
    if args.json:
        Path(args.json).write_text(json.dumps(
            [{"eu": va, "us": b, "verdict": verdict} for va, b, verdict in rows], indent=1))
    return 0 if ok else 1


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
    # the answers to map requests (M9.53): sub 3 = data served, sub 9 = no record
    ra_, rb_ = a.get("requests", []), b.get("requests", [])
    for i in range(max(len(ra_), len(rb_))):
        xa = [(x["id"], x["sub"]) for x in ra_[i]["replies"]] if i < len(ra_) else None
        xb = [(x["id"], x["sub"]) for x in rb_[i]["replies"]] if i < len(rb_) else None
        if xa != xb:
            diffs.append("request %d answered differently: A %s / B %s" % (
                i + 1, ", ".join("%#06x sub %d" % r for r in xa or []) or "-",
                ", ".join("%#06x sub %d" % r for r in xb or []) or "-"))
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
        p.add_argument("--build", choices=sorted(BUILDS), default="eu2011",
                       help="Navi.exe build the VAs belong to (default eu2011); the image "
                            "must be that build's head (vcard_l3.boot_report checks the SHA-256)")
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
    p = sub.add_parser("port", help="M9.61 Stop gate: the US pair of every EU function the mount enters")
    p.add_argument("image")
    p.add_argument("--us-image", required=True, help="the US build's head (the other image of the pair)")
    p.add_argument("--card-image")
    p.add_argument("--card-root")
    for opt in ("--hide", "--replace", "--flip", "--truncate"):
        p.add_argument(opt, action="append", default=[])
    p.add_argument("--position", metavar="LAT,LON")
    p.add_argument("--sdl", action="store_true")
    p.add_argument("--max-reads", type=int, default=0)
    p.add_argument("--request", action="append", default=[], type=lambda v: int(v, 0), metavar="MESH")
    p.add_argument("--kind", type=lambda v: int(v, 0), default=KIND_RENDER)
    p.add_argument("--client", type=int, default=CLIENT_TASK)
    p.add_argument("--divid", type=lambda v: int(v, 0), default=0)
    p.add_argument("--min-percent", type=float, default=90.0)
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
    if args.cmd == "port":
        if not (args.card_image or args.card_root):
            print("port needs --card-image or --card-root")
            return 2
        if not Path(args.us_image).is_file():
            print("missing image: %s" % args.us_image)
            return 2
        return cmd_port(args)
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
    check("reader_entry marks a copy model's loads with 'via'",
          reader_entry((0x404EE4, "memmove"), [4, 5, 6], False) == {"fn": 0x404EE4, "bytes": 3, "runs": [(4, 6)],
                                                                     "nruns": 1, "via": "memmove"})
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
    lt = decode_len_table(struct.pack("<III", 0x92, 0x81, 0x8080) + struct.pack("<III", 0x91, 0x141, 0x14100), 2)
    check("the length table gives column 1 of the kind's row",
          len_lookup(lt, 0x91, 1) == 0x141 and len_lookup(lt, 0x92, 2) == 0x8080)
    check("a kind with no length row gives 0", len_lookup(lt, 0x94, 1) == 0)
    req = decode_request(struct.pack("<IIII", 0x30001000, 3, 0x100, 0x40))
    check("a request decodes to position and length",
          req == {"dst": 0x30001000, "pos": 3 * 0x800 + 0x100, "length": 0x100})
    msg = ready_message()
    check("a position packs as lat code high, lon code low",
          encode_position(0, 0) == (32768 << 16) | 52742 and encode_position(48, 16) == ((32768 + 9216) << 16) | (52742 + 2048))
    check("a packed position decodes back", decode_position(encode_position(51.5, -0.25)) == (51.5, -0.25))
    check("the ready message is id 0x07d0 sub 100", struct.unpack_from("<HH", msg, 8) == (0x07D0, 100))
    check("both builds name the same table entries, and no US VA is the EU one",
          set(BUILDS) == {"eu2011", "us2011"} and set(DA_EU2011) == set(DA_US2011)
          and set(SDL_EU2011) == set(SDL_US2011)
          and all(DA_US2011[k] != DA_EU2011[k] for k in set(DA_EU2011) - {
              "msg_rows", "done_rows", "ready_msg", "done_msg", "event_msg", "state3_sub",
              "state3_value", "request_msg", "reply_msg"}))
    check("a ready message is built from the named build",
          struct.unpack_from("<HH", ready_message(DA_US2011), 8) == DA_US2011["ready_msg"])
    # M9.61 Stop gate: the census, not the run
    c_, u_, p_, ok_ = port_census([(1, 2, "UNIQUE"), (2, 3, "ANCHOR"), (3, 4, "DIFFERENT"),
                                   (4, None, "AMBIGUOUS")])
    check("port census: AMBIGUOUS/NOMATCH rows are unpaired and a 3/4 is below 90 %",
          c_ == {"UNIQUE": 1, "ANCHOR": 1, "DIFFERENT": 1, "AMBIGUOUS": 1}
          and len(u_) == 1 and u_[0][0] == 4 and abs(p_ - 75.0) < 1e-9 and not ok_)
    check("port census: all paired rows pass and an empty run is 0 %",
          port_census([(1, 2, "UNIQUE"), (2, 3, "ANCHOR")])[3]
          and port_census([])[2] == 0.0)
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

    class _A:
        card_image, card_root, hide, flip, truncate = "card.img", None, ["X/H.DAT"], [], []
        replace = ["MAPAL001/T.DAT=host"]
    fake = V.Card(None, overlay={"MAPAL001/T.DAT": b"abc", "X/H.DAT": None})
    rec = card_record(_A, fake)
    check("the run record names each overlaid file with its SHA-256",
          rec["overlay"] == [{"path": "mapal001/t.dat", "size": 3,
                              "sha256": hashlib.sha256(b"abc").hexdigest()},
                             {"path": "x/h.dat", "size": None, "sha256": None}]
          and rec["mods"]["replace"] == ["MAPAL001/T.DAT=host"])
    head = HERE.parent / "archive" / "head256.img"
    us_head = HERE.parent / "archive" / "us256.img"
    card_img = HERE.parent / "archive" / "sd-images" / "LEAF_2011-2012_QSD-309-101_navi158_eu.img"
    us_card = HERE.parent / "archive" / "sd-images" / "LEAF_2011-2012_US.img"
    if not (head.is_file() and card_img.is_file()):
        print("  firmware part skipped: archive/head256.img or the EU card image is not present")
    elif os.environ.get("DATASK_L3_HOST_SELFTEST") == "1":
        # tools/selftest.py runs every --selftest under one 60 s timeout; the
        # firmware runs below take ~55 s, so that runner asks for the host
        # logic only and the firmware part runs from a direct --selftest
        # (CI's `python3 tools/datask_l3.py --selftest`, ~1 min).
        print("  firmware part skipped: DATASK_L3_HOST_SELFTEST=1 (tools/selftest.py budget)")
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
            dirs = [r for r in t.rows if r["handler"] == 0x0041597C]
            check("each directory read has the length 0x0040901c gives (M3.31)",
                  dirs and all(r["len_lookup"] and r["len_lookup"]["value"] * 0x100 == r["length"] for r in dirs))
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
            mesh = 0xA6CDD6BE                  # the record's own parcel code (words 0-1 of slot 17 record 28)
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
            check("0x00405078 loads the record's unit table and the reply is 0x14b6 sub 3 (data)",
                  any(x["fn"] == 0x00405078 for x in row.get("record_readers", []))
                  and [x["sub"] for x in r["replies"]] == [5, 3])
            r = t.request_mesh(0x26C18AB2)     # same directory and record by the decoders, not the record's code
            row = t.rows[-1] if r["rows"] else {}
            check("an id that is not the record's code reads the record but gets sub 9 (no record served)",
                  r["rows"] == 1 and [x["sub"] for x in r["replies"]] == [5, 9]
                  and not any(x["fn"] == 0x00405078 for x in row.get("record_readers", [])))
            t.deliver(event_message(11, 16))
            r = t.request_mesh(mesh)
            check("in state 3 the same request is refused (status 9, no read)",
                  r["state"] == 3 and r["rows"] == 0 and any(x["sub"] == 5 and x["words"][0] == 9 for x in r["replies"]))
        except (V.Blocked, V.EngineError) as exc:
            check("firmware run (%s)" % str(exc)[:80], False)
        finally:
            V.MODELS.clear()
            V.MODELS.update(saved)

    if not (us_head.is_file() and card_img.is_file() and us_card.is_file()):
        print("  US-build part skipped: archive/us256.img or a card image is not present")
    elif os.environ.get("DATASK_L3_HOST_SELFTEST") == "1":
        print("  US-build part skipped: DATASK_L3_HOST_SELFTEST=1 (tools/selftest.py budget)")
    else:
        # M9.61: the US2011 build reads the EU card like the EU build does.
        try:
            eu_t = DataTask(str(head), V.make_card(None, str(card_img)), position=(51.70, 17.45))
            us_t = DataTask(str(us_head), V.make_card(None, str(card_img)), build=DA_US2011,
                            position=(51.70, 17.45))
            check("the US completion table has the same 20 tag classes and the US handler of each role",
                  [k for k, _f, _h in us_t.done_table] == [k for k, _f, _h in eu_t.done_table]
                  and len([1 for _k, _f, h in us_t.done_table if h]) == 20
                  and done_lookup(us_t.done_table, 0x0103) == 0x004339B4   # file header
                  and done_lookup(us_t.done_table, 0x0600) == 0x00434408   # section table
                  and done_lookup(us_t.done_table, 0x0700) == 0x0043D74C   # directory
                  and done_lookup(us_t.done_table, 0x0D00) == 0x0041FC2C)  # REFER001
            eu_t.run()
            us_t.run()
            key = lambda r: (r["file"].upper(), r["tag"], r["pos"], r["length"])
            check("the US build asks for the same reads as the EU build on the EU card",
                  [key(r) for r in us_t.rows] == [key(r) for r in eu_t.rows] and len(us_t.rows) >= 28)
            check("the US build reaches state 2 with map version 0x802, like the EU build",
                  us_t.summary()["state"] == eu_t.summary()["state"] == 2
                  and us_t.summary()["version"] == eu_t.summary()["version"])
            r = us_t.request_mesh(0xA6CDD6BE)
            row = us_t.rows[-1] if r["rows"] else {}
            check("a US map request reads the record block and is answered 0x14b6 sub 3",
                  r["rows"] == 1 and row.get("tag") == 0x0900 and row.get("handler") == 0x0042CFE4
                  and [x["sub"] for x in r["replies"]] == [5, 3])
            r = us_t.request_mesh(0x26C18AB2)
            check("the US build refuses a record whose code is not the mesh id (sub 9)",
                  [x["sub"] for x in r["replies"]] == [5, 9])
        except (V.Blocked, V.EngineError) as exc:
            check("firmware run (%s)" % str(exc)[:80], False)
        finally:
            V.MODELS.clear()
            V.MODELS.update(saved)
    print("datask_l3 selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
