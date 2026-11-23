#!/usr/bin/env python3
"""Read-watch tile section 2 (route graph) inside a running `-M ze0` guest (L4).

The L3 chain for the section-2 grammar (M4.55 -> M9.74 -> M9.75) stalled:
the RPF reply handler stores the unit-0 pointer but the code that walks it
never ran in the L3 engine.  In the full emulator (NK1 + unit flash +
`ze0_launch.py --ui-start`) the real Navi.exe fetches section 2 whenever the
map moves and computes routes, so the walker runs on its own.  This tool
attaches to the gdbstub and logs which code reads which section-2 bytes.

Subcommands
-----------
``watch``   attach to the gdbstub of a running guest (EU 2011 build A Navi.exe):
            break on the RPF reply handler ``0x00336dc0``; on every hit read the
            three RPF request buffers (``0x0061a020``/``0x00619818``/``0x0061a848``,
            u16 count at +0, 32-byte entries at +4: status u16 +0, kind +4,
            mesh +12, unit pointers +16/+20/+24/+28) and put a read watchpoint
            (gdb ``Z3``) on each new unit-0 and unit-2 pointer of a kind-8 entry.
            Every watch stop is logged as JSON (pc, pr, r0-r15, the instruction
            words around pc).  QEMU reports the watchpoint's start address, not
            the access address, so the access address is recomputed from the
            instruction (``decode``).
``decode``  JSONL from ``watch`` -> per reading VA: instruction, effective address,
            offset from the record base (unit 0 pointer - 54 bytes, the 27-halfword
            record header) and from the nearest unit pointer.
``frame``   walk every section-2 record of a tile with the firmware's framing rule
            (read off ``0x003534d4``, see EXP-2026-11-23-M9.75) and report whether
            each walk ends exactly at the unit-0 length.  Reads only the tile.

Logs hold vendor bytes (register values loaded from the card); keep them out of
the repository, like serial logs and screenshots.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import socket
import struct
import sys
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HANDLER = 0x00336DC0          # RPF reply handler (M4.55, EU2011 build A)
RPF_BUFS = (0x0061A020, 0x00619818, 0x0061A848)
WALKER = (0x003534D4, 0x003535CC)   # unit-0 node/link pre-pass (this tool's EXP)
REC_HDR = 54                  # record header: 27 big-endian halfwords; unit 0 follows


# ---------------------------------------------------------------- decoding ---

def effective_address(op: int, r: list[int]):
    """SH-4 load ``op`` and registers *after* it ran -> (address, size, text).

    Only the load forms seen in section-2 readers.  Post-increment loads give
    the address before the increment.  Returns (None, None, text) otherwise."""
    n, m, hi, lo = (op >> 8) & 15, (op >> 4) & 15, op >> 12, op & 15
    if hi == 6 and lo in (0, 1, 2):
        return r[m], 1 << lo, "mov.%s @r%d,r%d" % ("bwl"[lo], m, n)
    if hi == 6 and lo in (4, 5, 6):
        sz = 1 << (lo - 4)
        return (r[m] - sz if n != m else None), sz, "mov.%s @r%d+,r%d" % ("bwl"[lo - 4], m, n)
    if hi == 8 and n in (4, 5):
        sz = 1 << (n - 4)
        return r[m] + lo * sz, sz, "mov.%s @(%d,r%d),r0" % ("bw"[n - 4], lo * sz, m)
    if hi == 5:
        return r[m] + lo * 4, 4, "mov.l @(%d,r%d),r%d" % (lo * 4, m, n)
    if hi == 0 and lo in (0xC, 0xD, 0xE):
        sz = 1 << (lo - 0xC)
        return r[0] + r[m], sz, "mov.%s @(r0,r%d),r%d" % ("bwl"[lo - 0xC], m, n)
    return None, None, "op %04x" % op


def hit_access(d: dict):
    """One logged watch stop -> (reading pc, address, size, text) or None.

    QEMU's sh4 stops after the load, so the load is at pc-2 (or pc-4 when the
    load sat in a delay slot of the instruction before)."""
    if not d.get("ins"):
        return None
    b = bytes.fromhex(d["ins"])
    r = [int(x, 16) for x in d["regs"]]
    pc = int(d["pc"], 16)
    for k, ipc in ((2, pc - 2), (0, pc - 4)):
        op = b[k] | (b[k + 1] << 8)
        a, sz, txt = effective_address(op, r)
        if a is not None:
            return ipc, a, sz, txt
    return None


def decode(path: str) -> dict:
    ptrs = {}                                   # unit pointer -> (unit, mesh)
    hits = []
    for line in open(path):
        d = json.loads(line)
        if d["ev"] == "watch":
            ptrs[int(d["ptr"], 16)] = (d["unit"], d["mesh"])
        elif d["ev"] == "hit":
            acc = hit_access(d)
            if acc:
                hits.append(acc)
    unit0 = sorted(p for p, (u, _) in ptrs.items() if u == 0)
    rows = collections.Counter()
    for ipc, a, sz, txt in hits:
        below = [p for p in ptrs if p <= a]
        p = max(below) if below else None
        rec = max([q - REC_HDR for q in unit0 if q - REC_HDR <= a], default=None)
        rows[(ipc, txt, sz,
              ("unit%d+%d" % (ptrs[p][0], a - p)) if p is not None and a - p < 0x10000 else "-",
              ("rec+%d" % (a - rec)) if rec is not None and a - rec < 0x10000 else "-")] += 1
    return {"hits": len(hits), "rows": rows}


# ----------------------------------------------------------------- framing ---

def frame_record(w: list[int]) -> dict | None:
    """Walk unit 0 of one section-2 record (big-endian halfwords) as
    ``0x003534d4`` does: u32 node count at unit+0; nodes from unit+26 halfwords;
    node = 3 halfwords, link count = first >> 12; link = 7 halfwords plus
    ((w2 & 0x3fc0) >> 6) + (w1 & 1) + (w2 & 0x3f) + (w3 >> 14) extra halfwords,
    where w1..w3 are the link's halfwords +1..+3."""
    o, n = (w[6] << 16) | w[7], (w[8] << 16) | w[9]
    if o == 0xFFFFFFFF:
        return None
    u = w[o:o + n]
    nn = (u[0] << 16) | u[1]
    p, links, rare = 26, 0, 0
    for _ in range(nn):
        cnt = u[p] >> 12
        p += 3
        for _ in range(cnt):
            w1, w2, w3 = u[p + 1], u[p + 2], u[p + 3]
            p += 7 + ((w2 & 0x3FC0) >> 6) + (w1 & 1) + (w2 & 0x3F) + (w3 >> 14)
            rare += bool((w1 & 1) or (w3 >> 14) or (w2 & 0x3030))
            links += 1
    return {"exact": p == n, "end": p, "len": n, "nodes": nn, "links": links, "rare": rare}


def cmd_frame(a) -> int:
    import tile_relayout
    m = tile_relayout.read_model(open(a.tile, "rb").read())
    s2 = [s for s in m["sections"] if s["id"] == 2]
    if not s2:
        print("no section 2")
        return 1
    for L in s2[0]["levels"]:
        st = collections.Counter()
        for dm in L["dirs"]:
            for u in dm["units"]:
                for raw in u["recs"]:
                    if not raw:
                        continue
                    pl = zlib.decompress(raw)
                    w = list(struct.unpack(">%dH" % (len(pl) // 2), pl[:len(pl) // 2 * 2]))
                    r = frame_record(w)
                    if r is None:
                        st["no unit 0"] += 1
                        continue
                    st["records"] += 1
                    st["exact"] += r["exact"]
                    st["nodes"] += r["nodes"]
                    st["links"] += r["links"]
                    st["links with rare bits"] += r["rare"]
        if st:
            print("level %d: %s" % (L["level"], dict(st)))
    return 0


# ------------------------------------------------------------------- watch ---

def cmd_watch(a) -> int:
    import ze0_gdb as Z
    out = open(a.log, "a")
    t0 = time.time()

    def log(**k):
        k["t"] = round(time.time() - t0, 2)
        out.write(json.dumps(k) + "\n")
        out.flush()

    g = Z.Gdb(a.port)
    g.pkt("?")
    while True:                       # drain a stop left over from an earlier client
        try:
            g.recv(1.0)
        except socket.timeout:
            g.s.settimeout(None)
            break
    print("Z0", g.pkt("Z0,%x,2" % HANDLER), flush=True)
    watches, seen, nh, nwalk = [], set(), 0, 0
    lo, hi = a.quiet
    while time.time() - t0 < a.seconds:
        r = g.cont(max(1, a.seconds - (time.time() - t0)))
        if r is None:
            break
        regs = g.regs()
        pc = regs[Z.PC]
        if pc == HANDLER:
            for b in RPF_BUFS:
                try:
                    raw = g.mem(b, 4 + 32 * 8)
                except OSError:
                    continue
                cnt, = struct.unpack_from("<H", raw, 0)
                ents = []
                for i in range(min(cnt, 8)):
                    e = raw[4 + 32 * i:36 + 32 * i]
                    st, = struct.unpack_from("<H", e, 0)
                    kind, _, mesh = struct.unpack_from("<III", e, 4)
                    ptrs = struct.unpack_from("<4I", e, 16)
                    ents.append((st, kind, hex(mesh), [hex(x) for x in ptrs]))
                    for ui in (0, 2):
                        p = ptrs[ui]
                        if (st != 2 and kind == 8 and p not in (0, 0xFFFFFFFF)
                                and p not in seen and len(watches) < a.max_watch):
                            seen.add(p)
                            w = p & ~3
                            rr = g.pkt("Z3,%x,%x" % (w, a.window))
                            watches.append(w)
                            log(ev="watch", addr=hex(w), unit=ui, ptr=hex(p), mesh=hex(mesh),
                                reply=rr, buf=hex(b))
                log(ev="buf", buf=hex(b), n=cnt, ents=ents)
            g.step_over("0", HANDLER)
            continue
        wa = None
        for part in r.split(";"):
            if "watch:" in part:
                wa = int(part.split(":")[-1], 16)
        base = next((w for w in watches if wa is not None and w <= wa < w + a.window), None)
        quiet = lo <= pc < hi
        nwalk += quiet
        nh += not quiet
        if not quiet or nwalk <= a.quiet_log:
            try:
                ins = g.mem(pc - 4, 6).hex()
            except OSError:
                ins = None
            log(ev="hit", pc=hex(pc), pr=hex(regs[Z.PR]), ins=ins, regs=[hex(x) for x in regs[:16]])
        if base is not None:
            g.pkt("z3,%x,%x" % (base, a.window))
            g.pkt("s")
            g.pkt("Z3,%x,%x" % (base, a.window))
        else:
            g.pkt("s")
        if nh >= a.max_hits:
            for w in watches:
                g.pkt("z3,%x,%x" % (w, a.window))
            watches = []
    for w in watches:
        g.pkt("z3,%x,%x" % (w, a.window))
    g.pkt("z0,%x,2" % HANDLER)
    g.s.sendall(Z.frame("c"))
    print("hits %d quiet %d watches %d" % (nh, nwalk, len(watches)), flush=True)
    return 0


def cmd_decode(a) -> int:
    res = decode(a.log)
    print("hits decoded: %d" % res["hits"])
    for (ipc, txt, sz, u, rec), n in sorted(res["rows"].items(), key=str):
        print("%#010x  %-22s %d  %-12s %-10s x%d" % (ipc, txt, sz, u, rec, n))
    return 0


# ---------------------------------------------------------------- selftest ---

def selftest() -> int:
    r = [0] * 16
    r[2], r[3], r[0] = 0x58353F4E, 0x58353F1A, 0x10
    assert effective_address(0x6321, r)[:2] == (0x58353F4E, 2)          # mov.w @r2,r3
    assert effective_address(0x8521, r)[:2] == (0x58353F50, 2)          # mov.w @(2,r2),r0
    assert effective_address(0x8522, r)[:2] == (0x58353F52, 2)          # mov.w @(4,r2),r0
    assert effective_address(0x5222, r)[:2] == (0x58353F4E + 8, 4)      # mov.l @(8,r2),r2
    assert effective_address(0x6325, r)[:2] == (0x58353F4C, 2)          # mov.w @r2+,r3
    assert effective_address(0x032D, r)[:2] == (0x58353F5E, 2)          # mov.w @(r0,r2),r3
    assert effective_address(0x0009, r)[0] is None                      # nop
    hit = {"ins": "21632163" + "0009", "pc": "0x353524", "regs": [hex(x) for x in r]}
    assert hit_access(hit)[:3] == (0x353522, 0x58353F4E, 2)
    # one record: header 27 halfwords, unit 0 at halfword 27, 1 node with 2 links
    u = [0, 1, 0, 2] + [0] * 22 + [0x2123, 0x0456, 0, 9, 0x0000, 0x0001, 7, 1, 2, 3, 0xAAAA,
                                     9, 0x0001, 0x0000, 7, 1, 2, 3, 0xBBBB]
    w = [0] * 27
    w[6:10] = [0, 27, 0, len(u)]
    f = frame_record(w + u)
    assert f["exact"] and f["nodes"] == 1 and f["links"] == 2 and f["rare"] == 1, f
    u[-1:] = []                                                          # one halfword short
    w[9] = len(u)
    assert not frame_record(w + u)["exact"]
    print("selftest OK: load decoder, watch-stop access, section-2 framing rule")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    w = sub.add_parser("watch", help="attach and log section-2 reads")
    w.add_argument("log")
    w.add_argument("--port", type=int, default=1240)
    w.add_argument("--seconds", type=float, default=900)
    w.add_argument("--max-watch", type=int, default=16)
    w.add_argument("--window", type=lambda s: int(s, 0), default=0x800,
                   help="bytes watched from each unit pointer (large windows slow the guest)")
    w.add_argument("--max-hits", type=int, default=4000)
    w.add_argument("--quiet", type=lambda s: tuple(int(x, 0) for x in s.split(":")),
                   default=WALKER, help="pc range counted but logged only --quiet-log times")
    w.add_argument("--quiet-log", type=int, default=300)
    d = sub.add_parser("decode", help="JSONL -> reading VA table")
    d.add_argument("log")
    f = sub.add_parser("frame", help="check the firmware framing rule on a tile")
    f.add_argument("tile")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "watch":
        return cmd_watch(a)
    if a.cmd == "decode":
        return cmd_decode(a)
    if a.cmd == "frame":
        return cmd_frame(a)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
