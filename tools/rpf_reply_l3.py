#!/usr/bin/env python3
"""M4.55: drive the RPF kind-8 reply handler in L3 and read-watch unit 0.

The route path finder (EU2011, build A) asks the data-access task for tile
section 2 with kind 8.  The ``0x14b6`` sub-5 reply registers a pending entry,
the sub-3 reply fills its four pointers (``+16`` = unit 0, ``+24`` = unit 2).

This tool fetches both replies with ``datask_req_l3``, seeds the pending entry
in the RPF reply buffer and runs the RPF reply handler ``0x00336dc0`` with a
read-watch on unit 0.  It reports the handler verdict, the watch hits with the
reading PC, and the resulting buffer.  A walker that dereferences unit 0 would
appear as ``unit0`` hits; this tool is the falsifier for M4.55's premise that
the handler itself walks the section-2 record.

Usage:
    python3 tools/rpf_reply_l3.py --selftest
    python3 tools/rpf_reply_l3.py archive/head256.img \\
        --card archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img \\
        --position 51.70,17.45 --json report.json
"""
import argparse
import json
import struct
import sys

HERE = __file__.rsplit("/", 1)[0]
sys.path.insert(0, HERE)
sys.path.insert(0, HERE + "/l3_harness")

import datask_req_l3 as R      # noqa: E402
import vcard_l3 as V            # noqa: E402

IMG = "archive/head256.img"
CARD = "archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img"
G = 0x0061A824
BUF = (0x0061A020, 0x00619818, 0x0061A848)
RPF_INIT = 0x003360BC
HANDLER = 0x00336DC0
EXPORTS = ("STD_MeshPnt_isValid", "STD_MeshPnt_chgLv", "STD_MeshID_judgeLevel",
           "STD_MeshPnt_initPrm", "STD_MeshPnt_chgMapPnt", "STD_MeshID_getAny")


def seed_entry(e: dict) -> bytes:
    """The 32-byte reply entry the requester leaves in the RPF buffer."""
    ent = bytearray(32)
    struct.pack_into("<H", ent, 0, 2)                  # pending
    struct.pack_into("<I", ent, 4, e["kind"])
    struct.pack_into("<I", ent, 8, e["word8"])
    struct.pack_into("<H", ent, 10, e["divid"])
    struct.pack_into("<I", ent, 12, e["mesh"])
    struct.pack_into("<4I", ent, 16, *e["ptrs"])
    return struct.pack("<HH", 1, 0) + bytes(ent)      # u16 count, 2 pad, entry at +4


def fetch(image: str, card: str, lat: float, lon: float) -> dict:
    """Run one kind-8 request; return the two 0x14b6 reply bodies and the entry."""
    c = R.Client(image, V.make_card(None, card, {}), (lat, lon),
                 native=("STDDLL.dll", EXPORTS))
    m, eng = c.m, c.m.eng
    lst = m.malloc(R.LIST_BYTES)
    m.put(lst, R.pack_list([(0xA68CD68C, 0)]))
    c.t.deliver(R.pack_request(R.CLIENT_TASK, 8, lst))
    sent, _ = c.carry()
    bodies = {}
    for s in sent:
        raw = s["body"]
        body = bytes.fromhex(raw) if isinstance(raw, str) else bytes(raw)
        mid, sub = struct.unpack_from("<HH", body, 8)
        if mid == 0x14B6:
            bodies[sub] = body
    assert 3 in bodies and 5 in bodies, "kind-8 request did not yield sub-3 and sub-5 replies"
    lp, = struct.unpack_from("<I", bodies[3], 20)
    e = R.decode_entry(bytes(eng.read_mem(lp + 4, 32)))
    return {"client": c, "pending": bodies[5], "data": bodies[3], "entry": e}


def run(image: str, card: str, lat: float, lon: float, modes=(1, 2, 3)) -> dict:
    got = fetch(image, card, lat, lon)
    c, e = got["client"], got["entry"]
    m, eng = c.m, c.m.eng
    u0 = e["ptrs"][0]
    lp, = struct.unpack_from("<I", got["data"], 20)
    out = {"unit0": u0, "mesh": e["mesh"], "entry_ptrs": e["ptrs"],
           "reply_list": lp, "modes": {}}
    for mode in modes:
        m.call(RPF_INIT, [], max_insns=2_000_000)
        m.put(G + 4, struct.pack("<I", mode))
        m.put(BUF[0], seed_entry(e))
        msg = m.malloc(0x100)
        eng.watch(u0, u0 + 0x1000, "r", "unit0")
        eng.watch(lp, lp + 0x100, "r", "replylist")   # positive control
        eng.arm_watch()
        verdict = []
        for label, body in (("sub5", got["pending"]), ("sub3", got["data"])):
            m.put(msg, body)
            try:
                r0 = m.call(HANDLER, [msg], max_insns=80_000_000)
                verdict.append({"reply": label, "r0": r0})
            except Exception as ex:                  # noqa: BLE001 - fault is a result
                verdict.append({"reply": label, "fault": "%s: %s" %
                                (type(ex).__name__, str(ex)[:200])})
        hits = [{"pc": h.pc, "off": h.va - u0, "size": h.size,
                 "val": int.from_bytes(eng.read_mem(h.va, h.size), "little")}
                for h in eng.watch_hits() if h.name == "unit0"]
        ctrl = [h for h in eng.watch_hits() if h.name == "replylist"]
        out["modes"][str(mode)] = {
            "verdict": verdict, "unit0_reads": len(hits), "hits": hits[:80],
            "replylist_reads": len(ctrl),
            "replylist_pcs": sorted({h.pc for h in ctrl})[:20],
            "bufA": bytes(eng.read_mem(BUF[0], 40)).hex(),
        }
    return out


def selftest() -> int:
    e = {"kind": 8, "word8": 0x0303FFFF, "divid": 7, "mesh": 0xA680D680,
         "ptrs": [0x302ABBF2, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF]}
    b = seed_entry(e)
    assert len(b) == 36 and struct.unpack_from("<H", b, 0)[0] == 1
    assert struct.unpack_from("<H", b, 4)[0] == 2          # pending status at +4
    assert struct.unpack_from("<I", b, 16)[0] == e["mesh"]      # mesh at +16 (match key)
    assert struct.unpack_from("<I", b, 20)[0] == e["ptrs"][0]   # unit0 at +20
    assert struct.unpack_from("<I", b, 28)[0] == e["ptrs"][2]   # unit2 at +28
    assert struct.unpack_from("<I", b, 8)[0] == 8          # kind at +8
    print("selftest OK: reply-entry layout, unit0 at buf+16, unit2 at buf+24")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--selftest", action="store_true")
    p.add_argument("image", nargs="?")
    p.add_argument("--card", default=CARD)
    p.add_argument("--position", default="51.70,17.45")
    p.add_argument("--json")
    a = p.parse_args()
    if a.selftest:
        return selftest()
    if not a.image:
        p.error("image required")
    lat, lon = (float(x) for x in a.position.split(","))
    res = run(a.image, a.card, lat, lon)
    text = json.dumps(res, indent=2)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print("unit0=%#x mesh=%#x" % (res["unit0"], res["mesh"]))
    for mode, r in res["modes"].items():
        print("mode %s: %s unit0 reads=%d replylist reads=%d (positive control)" %
              (mode, "; ".join("%s r0=%#x" % (v["reply"], v.get("r0", -1))
                               for v in r["verdict"]), r["unit0_reads"],
               r["replylist_reads"]))
        for h in r["hits"][:20]:
            print("   pc=%08x off=%+5d size=%d val=%#x" %
                  (h["pc"], h["off"], h["size"], h["val"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
