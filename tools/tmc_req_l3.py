#!/usr/bin/env python3
"""tmc_req_l3.py - which file and offsets a data-layer request reads (M4.53, L3).

M4.49/M4.51 named message ``0x14f4`` as the possible reader of the
``RDSTM001.DAT`` link groups: it shares the data-access handler with the TMC
location request ``0x14e4`` and has no static sender (C-5405).  This tool
answers the question dynamically.  It mounts the card with
``datask_l3.DataTask`` (the data-access task and the map-file task of
``Navi.exe`` EU2011 in PySh4, M9.44/M3.25), then hands the data-access task's
own dispatcher a synthetic request and carries the messages until both tasks
are idle.  Every read the map-file layer serves is logged with its file,
offset and length, and every call of the REFER/RDSTM name builder
``0x003fbed8`` with the context words it sees (id at ctx +104, search type at
ctx +124, C-4666/C-4667).

A request is ``ID:SUB[:W12,W16,W20,W24,W28]``: ``u16 id`` at +8, ``u16 sub`` at
+10 and optional ``u32`` words at +12.. of a 64-byte message, the layout the
static sender of ``0x14e4`` builds (``fn 0x003bcac0``: id, ``1``, ``0``, three
keys at +16/+20/+24).  ``--pattern`` fills +12..+63 with ``01 02 03 ...`` so a
run shows which body bytes reach the name builder's context.

No vendor byte is stored here: the tool reads the image and card it is given.

Usage:
  tmc_req_l3.py --selftest
  tmc_req_l3.py run IMG256 --card-image CARD.img --request 0x14e4:1 --request 0x14f4:1 [--json OUT]

Exit codes: 0 every request ran to idle; 3 BLOCKED (mount failed or the
engine stopped on a request); 2 usage.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE / "l3_harness"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

NAME_BUILDER = 0x003FBED8        # (ctx, bits, n) -> REFER001/<prefix>nn.DAT (C-4666)
# EU2011: the M4.49/M4.51 static lead (handler, id switch, slot select, sector reader, volume opener)
# and the message-table path 0x004007b0 -> 0x0041330c that datask_l3 decodes for 0x14e4/0x14f4
M4_51_CHAIN = (0x004003F4, 0x00413828, 0x004129D0, 0x00417618, 0x004125A8, 0x004007B0, 0x0041330C)


def parse_request(spec: str) -> dict:
    """``ID:SUB[:w12,w16,...]`` -> {"id", "sub", "words"}."""
    parts = spec.split(":")
    if len(parts) < 2:
        raise ValueError("request needs ID:SUB, got %r" % spec)
    words = [int(w, 0) for w in parts[2].split(",")] if len(parts) > 2 and parts[2] else []
    if len(words) > 13:
        raise ValueError("at most 13 words (+12..+60)")
    return {"id": int(parts[0], 0), "sub": int(parts[1], 0), "words": words}


def build_body(req: dict, pattern: bool = False) -> bytes:
    body = bytearray(64)
    if pattern:
        body[12:64] = bytes(range(1, 53))
    struct.pack_into("<HH", body, 8, req["id"], req["sub"])
    for i, w in enumerate(req["words"]):
        struct.pack_into("<I", body, 12 + 4 * i, w & 0xFFFFFFFF)
    return bytes(body)


def summarize(rows: list[dict]) -> dict:
    """Files read and the (offset, length) runs per file."""
    out: dict = {}
    for r in rows:
        out.setdefault(r["file"], []).append((r["pos"], r["length"]))
    return out


class Runner:
    def __init__(self, image: str, card_image: str):
        import datask_l3 as D
        import vcard_l3 as V

        self.D, self.V = D, V
        card = V.make_card(None, card_image, [])
        self.card = card
        self.dt = D.DataTask(image, card)
        self.mount = self.dt.run()
        self.builder: list[dict] = []
        self.chain_hits: dict[int, int] = {va: 0 for va in M4_51_CHAIN}
        self.live = False
        m = self.dt.m

        def on_builder(engine, va):
            if self.live:
                ctx = m.arg(0)
                self.builder.append({"ctx104": m.u32(ctx + 104) & 0xFFFF, "ctx124": m.u32(ctx + 124),
                                     "bits": m.arg(1), "n": m.arg(2),
                                     "ctx60": bytes(m.eng.read_mem(ctx + 0x60, 0x20)).hex()})
            return None
        m.eng.on_exec(NAME_BUILDER, on_builder)
        for va in M4_51_CHAIN:
            m.eng.on_exec(va, self._count(va))

    def _count(self, va):
        def hook(engine, _va):
            if self.live:
                self.chain_hits[va] += 1
            return None
        return hook

    def loop(self) -> str:
        D, V, dt, m = self.D, self.V, self.dt, self.dt.m
        while True:
            if dt.routed >= len(m.messages):
                before = len(m.messages)
                dt.map_task_turn()
                if len(m.messages) == before:
                    return "idle"
                continue
            x = m.messages[dt.routed]
            dt.routed += 1
            if x["kind"] != "send":
                continue
            body = bytes.fromhex(x["body"])
            mid, sub = struct.unpack_from("<HH", body, 8)
            if x["task"] == D.MAP_TASK:
                dt.map_task_turn()
            elif x["task"] == D.DA_TASK and mid == dt.b["done_msg"]:
                dt.complete(body, False)
            elif x["task"] == D.DA_TASK:
                dt.deliver(body)
            else:
                dt.other.append({"task": x["task"], "id": mid, "sub": sub, "from": (x["pr"] - 4) & V.M32})

    def request(self, req: dict, pattern: bool = False) -> dict:
        dt = self.dt
        first, mark, other = len(dt.rows), len(self.card.log), len(dt.other)
        self.builder = []
        self.chain_hits = {va: 0 for va in M4_51_CHAIN}
        self.live = True
        stop = None
        try:
            dt.deliver(build_body(req, pattern))
            end = self.loop()
        except (self.V.Blocked, self.V.EngineError) as exc:
            end, stop = "stopped", str(exc)[:200]
        self.live = False
        rows = [{"file": r["file"], "pos": r["pos"], "length": r["length"], "tag": r["tag"],
                 "handler": r["handler"]} for r in dt.rows[first:]]
        opens = [e["path"] for e in self.card.log[mark:] if e["op"] == "open"]
        replies = [o for o in dt.other[other:] if "id" in o]
        return {"request": "%#06x:%d" % (req["id"], req["sub"]), "words": req["words"], "pattern": pattern,
                "end": end, "stop": stop, "reads": rows, "opens": opens,
                "builder": self.builder[:8], "builder_calls": len(self.builder),
                "m4_51_chain_hits": {"%#010x" % k: v for k, v in self.chain_hits.items()},
                "replies": ["%#06x to task %#x" % (o["id"], o["task"]) for o in replies]}


def show(res: dict) -> None:
    print("== request %s words %s%s -> %s%s" % (res["request"], res["words"],
                                               " (pattern)" if res["pattern"] else "", res["end"],
                                               (": " + res["stop"]) if res["stop"] else ""))
    for r in res["reads"]:
        print("   read %-26s off=%#08x len=%#06x tag=%#06x handler=%s"
              % (r["file"], r["pos"] or 0, r["length"], r["tag"],
                 "%#010x" % r["handler"] if r["handler"] else "-"))
    for p in res["opens"]:
        print("   open %s" % p)
    if res["builder"]:
        b = res["builder"][0]
        kinds = sorted({(x["ctx104"], x["ctx124"], x["n"]) for x in res["builder"]})
        print("   name builder 0x003fbed8: %d calls; (ctx+104, ctx+124, n) %s; ctx+0x60 %s"
              % (res["builder_calls"], ", ".join("(%#x, %d, %d)" % k for k in kinds), b["ctx60"]))
    else:
        print("   name builder 0x003fbed8: not called")
    print("   function entries: %s" % ", ".join("%s=%d" % kv for kv in res["m4_51_chain_hits"].items()))
    if res["replies"]:
        print("   replies: %s" % ", ".join(res["replies"][:4]))


def cmd_run(a) -> int:
    import vcard_l3 as V

    reqs = [parse_request(s) for s in a.request]
    try:
        r = Runner(a.image, a.card_image)
    except V.Blocked as exc:
        print("BLOCKED: %s" % exc)
        return 3
    s = r.dt.summary()
    print("mount: %s, %d reads, state %d, mesh_count %d" % (r.mount, s["reads"], s["state"], s["mesh_count"]))
    out, blocked = [], False
    for q in reqs:
        res = r.request(q, a.pattern)
        show(res)
        out.append(res)
        blocked |= res["stop"] is not None
    if a.json:
        Path(a.json).write_text(json.dumps({"schema": "osm2leaf.tmc_req_l3/v1", "build": "EU2011",
                                            "mount": r.mount, "results": out}, indent=1))
    return 3 if blocked else 0


def _selftest() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("ok   " if cond else "FAIL ") + name)
        ok &= bool(cond)

    q = parse_request("0x14e4:1:0,0x3219,1203,0")
    check("parse id/sub/words", q == {"id": 0x14E4, "sub": 1, "words": [0, 0x3219, 1203, 0]})
    check("parse bare", parse_request("0x14f4:1") == {"id": 0x14F4, "sub": 1, "words": []})
    try:
        parse_request("0x14f4")
        check("parse rejects missing sub", False)
    except ValueError:
        check("parse rejects missing sub", True)
    b = build_body(q)
    check("body id at +8, sub at +10", struct.unpack_from("<HH", b, 8) == (0x14E4, 1))
    check("body words from +12", struct.unpack_from("<4I", b, 12) == (0, 0x3219, 1203, 0))
    check("body is 64 bytes, zero head", len(b) == 64 and b[:8] == bytes(8))
    p = build_body(parse_request("0x14f4:1"), pattern=True)
    check("pattern fills +12..+63", p[12] == 1 and p[63] == 52 and struct.unpack_from("<H", p, 8)[0] == 0x14F4)
    sm = summarize([{"file": "A", "pos": 0, "length": 16}, {"file": "A", "pos": 16, "length": 8},
                    {"file": "B", "pos": 4, "length": 4}])
    check("summarize groups by file", sm == {"A": [(0, 16), (16, 8)], "B": [(4, 4)]})
    print("selftest: " + ("OK" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("image")
    r.add_argument("--card-image", required=True)
    r.add_argument("--request", action="append", required=True, help="ID:SUB[:w12,w16,...]")
    r.add_argument("--pattern", action="store_true", help="fill +12..+63 with 01 02 03 ...")
    r.add_argument("--json")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if a.cmd == "run":
        return cmd_run(a)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
