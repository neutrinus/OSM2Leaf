#!/usr/bin/env python3
"""locmap_l3.py - run the firmware's own chain from a car position to the
`LOC_map` walk of the served road record (M9.66, EU2011 `Navi.exe`).

`datask_req_l3.py` (M4.40) plays the client of the data-access task by hand.
This tool lets the firmware's client do it.  In one PySh4 machine (with the
FPU engine of `sh4fpu.py`) it runs, in the order the unit does:

1. the mount (`datask_l3.py`: data-access task and map-file task);
2. the buffer allocator `fn 0x00470914` and the client task's init
   `fn 0x00427a34` up to its first `OSM_TaskReceive` (the init registers the
   task with the data-access task by itself);
3. the client dispatcher `fn 0x00427144` with a position message
   (`0x0fa0` sub 119: mesh, x, y), which fills the four wanted groups;
4. the dispatcher with the request tick (`0x07d0` sub `0x7530`, word +28 =
   `0x03f1`), on which the requester `fn 0x00425f40` sends `0x14b5`;
5. the data-access task with that request (it reads the tile on the card)
   and the dispatcher with each `0x14b6` reply: the sub-3 handler
   `fn 0x0042613c` copies the record and posts `0x0fa0` sub `0x019a`;
6. the `LOC_map` receiver `fn 0x00421548` with that message, with every
   guest load from the copied shape buffer and tail buffer recorded.

The walk of the shape words is `fn 0x0041f3dc` (with the row-count helper
`fn 0x00422384`); the tool prints which instructions load which bytes of the
record, the rows it walks and the result table it leaves.

Declared models (nothing of the firmware is replaced): the kernel's part of
message passing (a message a task sends is handed to the receiving task's
dispatcher by the tool), the launcher's two task-id stores (`0x011fff5c`,
`0x011fff74`), the position message and the tick (in the unit they come from
the locator and from a timer), and `datask_l3.py`'s models.  `--patch
WORD=VALUE` changes one 16-bit word of the served record in guest memory
after the data-access task inflated it and before the client copies it.

`--build us2011` (M9.72) selects the US2011 `Navi.exe` twins of every chain
function and global (docs/format/firmware.md).  The mount goes through
`datask_req_l3.Client`, which is build-aware, so the US head mounts its own
data-access task.  EU2011 remains the default; a wrong head/build pair is
refused by the mount and by a build-specific word in the walk.

No vendor byte is stored here: the tool reads the image and card it is given.

Usage:
  locmap_l3.py --selftest
  locmap_l3.py run IMG256 --card-image CARD.img [--build {eu2011,us2011}]
               [--replace PATH=FILE]
               [--mesh 0xa6c1d6b2] [--xy 1024,1024] [--patch WORD=VALUE ...]
               [--json OUT]
  locmap_l3.py diff A.json B.json

`--shape-out FILE` writes the copied shape buffer (record + 0x2c) so the
host model can be fed the exact bytes the firmware walked.

Exit codes: run: 0 the walk ran, 1 no `LOC_map` message was produced;
diff: 0 SAME, 1 DIFFERENT; 2 usage or missing input; 3 BLOCKED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "l3_harness"))

# Per-build reuse points (M9.72).  EU2011 from M9.66; US2011 from the paired
# function bodies and their literal pools (`fn_match.py match`/`bodies`,
# `bodydiff.py`, `nk_decomp.py pdata`, `vcard_l3.port_data`).  Every VA below is
# attributed through `cerom.py`/`pdata` to Navi.exe of the named build, never
# by a fitted module delta.  The four M9.66 functions are content matches with
# equal pdata lengths; CLIENT_INIT/DISPATCH are call-graph twins (callee import
# signature and position), and the globals are the US pool value at the same
# load index of the paired function.  All globals are BSS: the chain's own
# firmware code writes them at runtime (`va_class.py`), so none needs M1.2f.
LOCMAP_EU2011 = {
    "ALLOC": 0x00470914,        # OSM_Malloc of the shape pool and the second pool
    "CLIENT_INIT": 0x00427A34,  # client task entry: init, then the receive loop
    "DISPATCH": 0x00427144,     # client dispatcher (one message)
    "LOC_RECV": 0x00421548,     # LOC_map: handler of 0x0fa0 sub 0x019a
    "WALK": 0x0041F3DC,         # the shape walk (0x11dc bytes)
    "ROWS": 0x00422384,         # row-count helper (leaf, pdata GAP)
    # Globals written short on purpose: fn_audit reads eight hex digits as a
    # function citation (same convention as datask_l3.DA_EU2011).
    "G_CLIENT_ID": 0x11FFF5C,   # launcher: the client task's id
    "G_LOC_ID": 0x11FFF74,      # launcher: LOC_map's task id
    "G_GROUPS": 0xE99698,       # -> OSM_SramGet block; 20-byte groups from +8
    "G_SLOTS": 0xE8F604,        # -> 4 slots of 16 bytes (state, shape, tail)
    "G_LOCTAB": 0xE8F5DC,       # -> 4 result entries of 48 bytes
    "G_CAND": 0xE8F5C4,         # -> 4 result blocks of 0x1774 bytes
}
LOCMAP_US2011 = {
    "ALLOC": 0x00498EA4,        # launcher call-graph twin (fn_match's UNIQUE
                                # 0x0049c1a4 was a false positive: it read VA 0)
    "CLIENT_INIT": 0x0044F0D0,  # call-graph twin, pdata true start (0x0044f0f8 INSIDE)
    "DISPATCH": 0x0044E808,     # direct caller of US requester's 0x2f8 caller
    "LOC_RECV": 0x00448E24,     # fn_match UNIQUE, START, len 0x194
    "WALK": 0x00446CB8,         # fn_match UNIQUE, START, len 0x11dc
    "ROWS": 0x00449C60,         # fn_match LEAF UNIQUE, len 0x1e
    "G_CLIENT_ID": 0x11031C0,   # paired client-init requester pool
    "G_LOC_ID": 0x11031D8,      # US twin of EU fn 0x004259bc pool (two anchors)
    "G_GROUPS": 0xDC7658,       # paired LOC_RECV pool load index
    "G_SLOTS": 0xDBD664,        # paired WALK pool load index
    "G_LOCTAB": 0xDBD61C,       # paired WALK pool load index
    "G_CAND": 0xDBD604,         # paired WALK pool load index
}
for _b in (LOCMAP_EU2011, LOCMAP_US2011):
    # `mov.w @(4,r2),r0`, the walk's first row read: same halfword in both
    # builds, derived from the paired body at the same offset (+0x9e).
    _b["BUILD_CHECK"] = (_b["WALK"] + 0x9E, 0x8522)
BUILDS = {"eu2011": LOCMAP_EU2011, "us2011": LOCMAP_US2011}

# EU2011 aliases kept for callers and the selftest; the chain reads self.B.
ALLOC = LOCMAP_EU2011["ALLOC"]
CLIENT_INIT = LOCMAP_EU2011["CLIENT_INIT"]
DISPATCH = LOCMAP_EU2011["DISPATCH"]
LOC_RECV = LOCMAP_EU2011["LOC_RECV"]
WALK = LOCMAP_EU2011["WALK"]
ROWS = LOCMAP_EU2011["ROWS"]
BUILD_CHECK = LOCMAP_EU2011["BUILD_CHECK"]
G_CLIENT_ID = LOCMAP_EU2011["G_CLIENT_ID"]
G_LOC_ID = LOCMAP_EU2011["G_LOC_ID"]
G_GROUPS = LOCMAP_EU2011["G_GROUPS"]
G_SLOTS = LOCMAP_EU2011["G_SLOTS"]
G_LOCTAB = LOCMAP_EU2011["G_LOCTAB"]
G_CAND = LOCMAP_EU2011["G_CAND"]
LOC_TASK = 0x12             # any id no other task uses
SHAPE_POOL = 0x109A0
TAIL_POOL = 0x5DC0
CAND_BYTES = 0x1774
MSG_POS, SUB_POS = 0x0FA0, 119
MSG_TICK, SUB_TICK, TICK_ID = 0x07D0, 0x7530, 0x03F1
MSG_REQ, MSG_REPLY = 0x14B5, 0x14B6
MSG_LOC, SUB_LOC = 0x0FA0, 0x019A
ROW_COUNT = 12


def pack_msg(mid: int, sub: int, *words: int) -> bytes:
    b = bytearray(64)
    struct.pack_into("<HH", b, 8, mid, sub)
    for i, w in enumerate(words):
        struct.pack_into("<I", b, 12 + 4 * i, w & 0xFFFFFFFF)
    return bytes(b)


def rows_of(shape: bytes) -> list[tuple[int, int]]:
    """The 12 (start, count) pairs the walk reads at bytes 2 + 4 i of the
    copied shape buffer (record + 0x2c)."""
    return [struct.unpack_from("<HH", shape, 2 + 4 * i) for i in range(ROW_COUNT)]


def ref_target(word: int) -> int:
    """Byte offset in the shape buffer that a reference word points at."""
    return 2 * word + 2


def parse_patch(spec: str) -> tuple[int, int]:
    word, _, value = spec.partition("=")
    return int(word, 0), int(value, 0) & 0xFFFF


def trace_digest(reads) -> str:
    h = hashlib.sha1()
    for r in reads:
        h.update(struct.pack("<IIH", r[0], r[1], r[2]))
    return h.hexdigest()


class Chain:
    def __init__(self, image: str, card_image: str, replace=(), position=(51.70, 17.45),
                 build: str = "eu2011"):
        import datask_req_l3 as R
        import sh4fpu
        import vcard_l3 as V
        V.PySh4 = sh4fpu.PySh4Fpu          # the walk uses the FPU
        self.R, self.V = R, V
        self.build, self.B = build, BUILDS[build]
        card = V.make_card(None, card_image, {"replace": list(replace)})
        self.c = R.Client(image, card, position, register=False, build=build)
        self.m = self.c.m
        self.eng = self.m.eng
        bc_va, bc_word = self.B["BUILD_CHECK"]
        code = struct.unpack("<H", bytes(self.eng.read_mem(bc_va, 2)))[0]
        if code != bc_word:
            raise V.Blocked("not the %s build: %#06x at %#010x" % (
                build.upper(), code, bc_va))
        self.log: list[str] = []
        self.loc_msgs: list[bytes] = []
        self.copies: list[dict] = []
        self.requests: list[dict] = []
        self.patches: list[tuple[int, int]] = []
        self.patched: list[dict] = []

    def say(self, text: str) -> None:
        self.log.append(text)

    def call(self, va: int, args=(), budget: int = 400_000_000):
        """Run to return; a task entry stops at its first OSM_TaskReceive."""
        try:
            return self.m.call(va, list(args), max_insns=budget)
        except self.V.Blocked as ex:
            if "OSM_TaskReceive" not in str(ex):
                raise
            return None

    def to_client(self, body: bytes) -> list[dict]:
        p = self.m.malloc(64)
        self.m.put(p, body.ljust(64, b"\0"))
        n = len(self.m.messages)
        self.call(self.B["DISPATCH"], [p])
        return [x for x in self.m.messages[n:] if x["kind"] == "send"]

    def start(self) -> None:
        m = self.m
        m.put(self.B["G_CLIENT_ID"], struct.pack("<I", self.R.CLIENT_TASK))
        m.put(self.B["G_LOC_ID"], struct.pack("<I", LOC_TASK))
        self.call(self.B["ALLOC"])
        self.call(self.B["CLIENT_INIT"])
        self.groups = m.u32(self.B["G_GROUPS"])
        self.slots = m.u32(self.B["G_SLOTS"])
        if not self.groups or not self.slots:
            raise self.V.Blocked("client init left the group or slot table unset")

    def route(self, out: list[dict]) -> None:
        """Carry client -> data-access requests and the replies until quiet."""
        m = self.m
        for x in out:
            body = bytes.fromhex(x["body"])
            mid, sub = struct.unpack_from("<HH", body, 8)
            if mid == MSG_REQ:
                kind, lst = struct.unpack_from("<II", body, 16)
                n = struct.unpack("<H", bytes(self.eng.read_mem(lst, 2)))[0]
                want = [struct.unpack_from("<HI", bytes(self.eng.read_mem(lst + 14 + 32 * i, 6)))
                        for i in range(min(n, 4))]
                req = {"kind": kind, "entries": [{"mesh": w[1], "divid": w[0]} for w in want],
                       "reads": [], "replies": []}
                self.requests.append(req)
                self.c.t.deliver(body)
                sent, rows = self.c.carry()
                for r in rows:
                    req["reads"].append({"file": r["file"], "pos": r["pos"], "length": r["length"]})
                for s in sent:
                    if s["id"] != MSG_REPLY:
                        continue
                    req["replies"].append({"sub": s["sub"]})
                    if s["sub"] == 3 and kind == 4:
                        self.patch_record(s["body"])
                    self.route(self.to_client(s["body"]))
            elif mid == MSG_LOC and sub == SUB_LOC and x["task"] == LOC_TASK:
                self.loc_msgs.append(body)

    def patch_record(self, reply: bytes) -> None:
        lp = struct.unpack_from("<I", reply, 20)[0]
        rec = struct.unpack("<I", bytes(self.eng.read_mem(lp + 32, 4)))[0]
        if struct.unpack_from("<I", reply, 16)[0] != 4 or rec in (0, 0xFFFFFFFF):
            return
        self.record = rec
        for word, value in self.patches:
            old = struct.unpack("<H", bytes(self.eng.read_mem(rec + 2 * word, 2)))[0]
            self.m.put(rec + 2 * word, struct.pack("<H", value))
            self.patched.append({"word": word, "old": old, "new": value})

    def run(self, mesh: int, x: int, y: int, patches=(), shape_out=None) -> dict:
        m, eng = self.m, self.eng
        self.patches = list(patches)
        self.start()
        self.to_client(pack_msg(MSG_POS, SUB_POS, mesh, x, y))
        groups = bytes(eng.read_mem(self.groups + 8, 80))
        wanted = [{"mesh": struct.unpack_from("<I", groups, 4 + 20 * i)[0],
                   "divid": struct.unpack_from("<H", groups, 8 + 20 * i)[0]} for i in range(4)]
        out = self.to_client(pack_msg(MSG_TICK, SUB_TICK, 0, 0, 0, 0, TICK_ID))
        self.route(out)
        res = {"build": self.build, "mesh": mesh, "xy": [x, y], "wanted": wanted,
               "requests": self.requests, "patched": self.patched,
               "loc_messages": len(self.loc_msgs)}
        if not self.loc_msgs:
            return res
        groups = bytes(eng.read_mem(self.groups + 8, 80))
        slots = bytes(eng.read_mem(self.slots, 64))
        res["groups"] = [{"mesh": struct.unpack_from("<I", groups, 4 + 20 * i)[0],
                          "divid": struct.unpack_from("<H", groups, 8 + 20 * i)[0],
                          "divided": struct.unpack_from("<H", groups, 10 + 20 * i)[0],
                          "window": struct.unpack_from("<I", groups, 16 + 20 * i)[0],
                          "slot_state": struct.unpack_from("<H", slots, 16 * i)[0]} for i in range(4)]
        shape_va, tail_va = struct.unpack_from("<II", slots, 4)
        window = res["groups"][0]["window"]
        shape = bytes(eng.read_mem(shape_va, window))
        res["window"] = window
        res["shape_sha1"] = hashlib.sha1(shape).hexdigest()
        res["rows"] = [{"row": i, "start": s, "count": c}
                       for i, (s, c) in enumerate(rows_of(shape)) if c]
        eng.watch(shape_va, shape_va + SHAPE_POOL, "r", "shape")
        eng.watch(tail_va, tail_va + TAIL_POOL, "r", "tail")
        eng.arm_watch()
        body = self.loc_msgs[0]
        res["loc_message"] = {"mesh": struct.unpack_from("<I", body, 12)[0],
                              "divid": struct.unpack_from("<I", body, 16)[0],
                              "group": struct.unpack_from("<I", body, 20)[0]}
        q = m.malloc(64)
        m.put(q, body.ljust(64, b"\0"))
        r0 = self.call(self.B["LOC_RECV"], [q])
        res["receiver_r0"] = r0
        res["loc_recv"] = self.B["LOC_RECV"]
        reads, per_pc, seen = [], {}, {"shape": set(), "tail": set()}
        for h in eng.watch_hits():
            if h.name not in seen:
                continue
            off = h.va - (shape_va if h.name == "shape" else tail_va)
            seen[h.name].update(range(off, off + h.size))
            if h.name == "shape":
                reads.append((h.pc, off, h.size))
            key = "%s %#010x" % (h.name, h.pc)
            per_pc[key] = per_pc.get(key, 0) + h.size
        res["reads"] = len(reads)
        res["read_bytes"] = sum(r[2] for r in reads)
        res["distinct_shape_bytes"] = len(seen["shape"])
        res["distinct_tail_bytes"] = len(seen["tail"])
        res["beyond_window"] = sorted({r[1] for r in reads if r[1] >= window})
        res["per_pc"] = per_pc
        walk, rows = self.B["WALK"], self.B["ROWS"]
        res["functions"] = sorted({"%#010x" % (walk if walk <= r[0] < walk + 0x11DC else
                                               rows if rows <= r[0] < rows + 0x24 else r[0])
                                   for r in reads})
        res["trace_sha1"] = trace_digest(reads)
        res["first_reads"] = [{"pc": "%#010x" % r[0], "offset": r[1],
                               "value": struct.unpack_from("<H", bytes(eng.read_mem(shape_va + r[1], 2)))[0]}
                              for r in reads[:48]]
        res["trace"] = [[r[0], r[1], r[2]] for r in reads]
        if shape_out:
            with open(shape_out, "wb") as f:
                f.write(shape)
        table = bytes(eng.read_mem(m.u32(self.B["G_LOCTAB"]), 192))
        cand = bytes(eng.read_mem(m.u32(self.B["G_CAND"]), 4 * CAND_BYTES))
        res["result_table"] = [table[48 * i:48 * i + 48].hex() for i in range(4)]
        res["result_sha1"] = hashlib.sha1(table + cand).hexdigest()
        return res


def show(res: dict) -> None:
    print("wanted groups after the position message: "
          + ", ".join("%#x/%#06x" % (g["mesh"], g["divid"]) for g in res["wanted"]))
    for q in res["requests"]:
        print("request 0x14b5 kind %#x: %d entries (%s); reads %s; replies sub %s"
              % (q["kind"], len(q["entries"]),
                 ", ".join("%#x/%#06x" % (e["mesh"], e["divid"]) for e in q["entries"]),
                 ", ".join("%s@%#x+%#x" % (r["file"], r["pos"], r["length"]) for r in q["reads"]) or "none",
                 [r["sub"] for r in q["replies"]]))
    for p in res["patched"]:
        print("patched record word %d: %#06x -> %#06x" % (p["word"], p["old"], p["new"]))
    if not res["loc_messages"]:
        print("RESULT: no LOC_map message (0x0fa0 sub 0x019a) was produced")
        return
    g = res["groups"][0]
    print("groups after the reply: window %d B, divided flag %d, slot state %d; %d LOC_map message(s)"
          % (g["window"], g["divided"], g["slot_state"], res["loc_messages"]))
    print("shape copy sha1 %s; rows with shapes: %s"
          % (res["shape_sha1"], ", ".join("row %d start %#x count %d" % (r["row"], r["start"], r["count"])
                                           for r in res["rows"]) or "none"))
    print("build %s; receiver %#010x returned %s" % (
        res.get("build", "eu2011"), res.get("loc_recv", LOC_RECV), res["receiver_r0"]))
    print("shape-buffer loads: %d (%d B), %d distinct bytes; tail-buffer bytes read: %d; functions: %s"
          % (res["reads"], res["read_bytes"], res["distinct_shape_bytes"],
             res["distinct_tail_bytes"], ", ".join(res["functions"])))
    if res["beyond_window"]:
        print("loads beyond the %d B window (stale pool bytes): offsets %s"
              % (res["window"], ", ".join("%#x" % o for o in res["beyond_window"][:8])))
    for k in sorted(res["per_pc"]):
        print("  %s  %d B" % (k, res["per_pc"][k]))
    print("trace sha1 %s; result sha1 %s" % (res["trace_sha1"], res["result_sha1"]))
    print("RESULT: walk ran")


def cmd_run(args) -> int:
    for path in (args.image, args.card_image):
        if not os.path.isfile(path):
            print("missing input: %s" % path, file=sys.stderr)
            return 2
    try:
        x, y = (int(v, 0) for v in args.xy.split(","))
        patches = [parse_patch(p) for p in args.patch or []]
    except ValueError as ex:
        print("bad argument: %s" % ex, file=sys.stderr)
        return 2
    import vcard_l3 as V
    try:
        chain = Chain(args.image, args.card_image, args.replace or [], build=args.build)
        res = chain.run(int(args.mesh, 0), x, y, patches, shape_out=args.shape_out)
    except V.Blocked as ex:
        print("BLOCKED: %s" % ex)
        return 3
    show(res)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(res, f, indent=1)
    return 0 if res["loc_messages"] else 1


KEYS = ("shape_sha1", "trace_sha1", "result_sha1")


def compare(a: dict, b: dict) -> list[str]:
    return [k for k in KEYS if a.get(k) != b.get(k)]


def cmd_diff(args) -> int:
    try:
        a, b = (json.load(open(p)) for p in (args.a, args.b))
    except (OSError, ValueError) as ex:
        print("cannot read: %s" % ex, file=sys.stderr)
        return 2
    changed = compare(a, b)
    for k in KEYS:
        print("%-12s %s  %s  %s" % (k, a.get(k), b.get(k), "DIFFERENT" if k in changed else "SAME"))
    print("RESULT: %s" % ("DIFFERENT" if changed else "SAME"))
    return 1 if changed else 0


def selftest() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print("%-58s %s" % (name, "ok" if cond else "FAIL"))
        ok = ok and bool(cond)

    b = pack_msg(MSG_POS, SUB_POS, 0xA6C1D6B2, 1024, 1024)
    check("position message: id, sub at +8, mesh at +12",
          struct.unpack_from("<HHIII", b, 8) == (0x0FA0, 119, 0xA6C1D6B2, 1024, 1024))
    t = pack_msg(MSG_TICK, SUB_TICK, 0, 0, 0, 0, TICK_ID)
    check("tick message: timer id at +28", struct.unpack_from("<I", t, 28)[0] == 0x03F1 and len(t) == 64)
    shape = bytearray(64)
    struct.pack_into("<HH", shape, 2 + 4 * 5, 0x0D, 1)
    struct.pack_into("<HH", shape, 2 + 4 * 6, 0x15, 1)
    rows = rows_of(bytes(shape))
    check("rows_of: 12 rows, pairs at 2 + 4 i", len(rows) == 12 and rows[5] == (0x0D, 1) and rows[6] == (0x15, 1))
    check("rows_of: an empty row has count 0", rows[0] == (0, 0))
    check("ref_target: word 0x179 -> byte 0x2f4", ref_target(0x179) == 0x2F4)
    check("ref_target: word 0x100 is past a 512 B window", ref_target(0x100) >= 512)
    check("parse_patch: WORD=VALUE", parse_patch("58=0x0010") == (58, 0x10))
    try:
        parse_patch("x=1")
        bad = False
    except ValueError:
        bad = True
    check("parse_patch: refuses a non-number (negative control)", bad)
    r1 = [(WALK + 0x9E, 4, 2), (WALK + 0xAA, 0x16, 2)]
    r2 = [(WALK + 0x9E, 4, 2), (WALK + 0xAA, 0x1A, 2)]
    check("trace_digest: same trace, same digest", trace_digest(r1) == trace_digest(list(r1)))
    check("trace_digest: one changed offset changes it (control)", trace_digest(r1) != trace_digest(r2))
    a = {"shape_sha1": "a", "trace_sha1": "b", "result_sha1": "c"}
    check("compare: equal runs are SAME", compare(a, dict(a)) == [])
    check("compare: a changed trace is DIFFERENT (control)",
          compare(a, dict(a, trace_sha1="x")) == ["trace_sha1"])
    check("walk function range holds the first row read", WALK < BUILD_CHECK[0] < WALK + 0x11DC)
    check("both builds have the same chain keys",
          set(LOCMAP_EU2011) == set(LOCMAP_US2011) and set(BUILDS) == {"eu2011", "us2011"})
    check("every function and global VA differs between builds",
          all(LOCMAP_EU2011[k] != LOCMAP_US2011[k]
              for k in LOCMAP_EU2011 if k != "BUILD_CHECK"))
    check("the US build check is the US walk's first row read",
          LOCMAP_US2011["BUILD_CHECK"] == (LOCMAP_US2011["WALK"] + 0x9E, 0x8522)
          and LOCMAP_US2011["WALK"] < LOCMAP_US2011["BUILD_CHECK"][0]
          < LOCMAP_US2011["WALK"] + 0x11DC)
    try:
        BUILDS["not-a-build"]
        bad = False
    except KeyError:
        bad = True
    check("an unknown build is refused (negative control)", bad)
    print("selftest: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("run", help="run the chain and the LOC_map walk")
    p.add_argument("image")
    p.add_argument("--card-image", required=True)
    p.add_argument("--build", choices=sorted(BUILDS), default="eu2011")
    p.add_argument("--replace", action="append", metavar="PATH=FILE")
    p.add_argument("--mesh", default="0xa6c1d6b2")
    p.add_argument("--xy", default="1024,1024")
    p.add_argument("--patch", action="append", metavar="WORD=VALUE")
    p.add_argument("--json")
    p.add_argument("--shape-out", metavar="FILE", help="write the copied shape buffer")
    d = sub.add_parser("diff", help="compare two --json results")
    d.add_argument("a")
    d.add_argument("b")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "diff":
        return cmd_diff(args)
    ap.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
