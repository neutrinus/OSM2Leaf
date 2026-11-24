#!/usr/bin/env python3
"""Inject one TMC traffic event at fn 0x003bcc7c and watch the LCTBL reads (M8.H63).

M8.H62 located the EU2011 injection point: ``fn 0x003bcc7c`` (TMC search
wrapper, pdata START len 0xa4) takes a caller-owned context pointer in ``r4``.
The context carries the three TMC lookup keys at ``+16/+20/+24`` (country,
location-database number, location code); the wrapper calls
``fn 0x003bcac0`` -> ``fn 0x003c0e68`` -> ``OSM_TaskSend`` with a 64-byte
``0x14e4:1`` data-layer request, which makes the firmware read
``RDSTM001/LCTBL001.DAT`` and answer ``0x14fb``.

This tool mounts the EU2011 card with ``tmc_req_l3.Runner`` (the firmware's own
data-access + map-file tasks in PySh4), writes a context, *actually calls the
wrapper* with ``m.call(0x003bcc7c, [p])``, then carries the resulting messages
through to the ``0x14fb`` answer.  The carry loop is the union of
``tmc_req_l3.loop`` (DA/MAP messages and completion routing) and
``lctbl_lookup_l3.Lookup`` (the ``HDL_MapTblTask`` inflate on ``0x14b8`` turns),
so a found code reaches the record-page inflate and the 48-byte record — not
just the request send.

Modes, selectable with ``--inject``/``--mutation``:

* present code ``2,25,1203``: status 1, the record-page inflate and a
  48-byte TMC place record equal to ``lctbl_build.parse``'s model;
* absent code ``2,25,60000``: status 4, only index-page reads, no inflate;
* ``--mutation null-context``: ``r4 = 0`` -> ``r0 = -1``, no request sent;
* ``--mutation wrong-id``: data-layer request id ``0x14f4`` -> reads
  ``REFER001/POINT001.DAT`` only, answer ``0x14b8`` (M8.H62 control).

The two codes' read sets, statuses and inflate counts are compared; if they are
identical the tool prints ``FALSIFIED`` and exits 1 (the task falsifier).

No vendor bytes are stored here: the tool reads the image and card it is given.

Usage::

  python3 tools/tmc_inject_l3.py --selftest
  python3 tools/tmc_inject_l3.py run IMG256 --card-image CARD.img \\
      --inject 2,25,1203 --inject 2,25,60000 [--json OUT]

Exit codes: 0 every injection agreed with the model and the falsifier is
refuted; 1 a verdict disagreed or the falsifier held; 3 BLOCKED (mount failed
or the engine stopped); 2 usage.

Stdlib only.  All VAs are EU2011 build A ``Navi.exe``.
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

import lctbl_build as L  # noqa: E402
import lctbl_lookup_l3 as LL  # noqa: E402
import tmc_req_l3 as TR  # noqa: E402
import vcard_l3 as V  # noqa: E402
import tmc_fielddir as TF  # noqa: E402

#: The injection point and its callee (M8.H62, pdata STARTs, SH-4 little-endian).
INJECT_FN = 0x003BCC7C
SEARCH_FN = 0x003BCAC0
SEND_FN = 0x003C0E68
#: BSS globals the wrapper/tests read (va_class: sec1, zero at load) and the
#: data-access task id global; pre-written before the call.
DEBUG_GUARDS = (0x01379CD8, 0x01379CD4, 0x01379CD0)
DA_TASK_ID_GLOBAL = 0x011FFF58

NAME_BUILDER = TR.NAME_BUILDER
REQUEST, ANSWER, TO_TBL = 0x14E4, 0x14FB, 0x14B8
FOUND, NOT_FOUND = 1, 4
TBL_TASK = LL.TBL_TASK
LCTBL_PATH_KEY, POINT_PATH_KEY = "LCTBL001", "POINT001"


def build_context(m, cc: int, db: int, code: int, *, guard: int = 1,
                  body_ptr: int | None = None) -> int:
    """Allocate the 64-byte context the wrapper reads through ``r4``.

    Layout from the disassembly of fn 0x003bcc7c/0x003bcac0 (tmc-path.md §4a):
    +0 guard byte, +2 count u16, +4 pointer to the decoded message body,
    +8 message kind u16, +16/+20/+24 the three u32 lookup keys.  The body
    pointer must be a valid 64-byte buffer; the search function only forwards
    the context, it does not read the keys through the body.
    """
    if body_ptr is None:
        body_ptr = m.malloc(64)
        m.put(body_ptr, bytes(64))
    ctx = bytearray(64)
    ctx[0] = guard & 0xFF
    struct.pack_into("<H", ctx, 2, 1)          # nonzero count
    struct.pack_into("<I", ctx, 4, body_ptr)   # decoded message body pointer
    struct.pack_into("<H", ctx, 8, 2)          # message kind
    struct.pack_into("<III", ctx, 16, cc & 0xFFFF, db & 0xFFFF, code & 0xFFFF)
    p = m.malloc(64)
    m.put(p, bytes(ctx))
    return p


class Injection:
    """One L3 machine, one mounted card, many injections."""

    def __init__(self, image: str, card_image: str):
        import datask_l3 as D

        self.D = D
        self.runner = TR.Runner(image, card_image)
        self.dt = self.runner.dt
        self.m = self.dt.m
        self.mount = self.runner.mount
        # BSS state that makes the wrapper's debug/printf path reachable and
        # routes the resulting OSM_TaskSend back to the data-access task.
        for va in DEBUG_GUARDS:
            self.m.put(va, struct.pack("<I", 1))
        self.m.put(DA_TASK_ID_GLOBAL, struct.pack("<I", D.DA_TASK))
        # HDL_MapTblTask state, from lctbl_lookup_l3.Lookup (M5.60).
        self.m.put(LL.EU2011["tbl_task_id"], struct.pack("<I", TBL_TASK))
        self.inflate_calls = 0
        self.m.eng.on_exec(self.dt.b["inflate"], self._on_inflate)

    def _on_inflate(self, _engine, _va):
        self.inflate_calls += 1
        return None

    def _tbl_turn(self, body: bytes) -> None:
        dt, m = self.dt, self.m
        dt.st.task = TBL_TASK
        p = m.malloc(64)
        m.put(p, body.ljust(64, b"\0"))
        try:
            if struct.unpack_from("<H", body, 8)[0] == TO_TBL:
                m.call(LL.EU2011["tbl_inflate_msg"], [p], max_insns=400_000_000)
            m.call(LL.EU2011["tbl_after"], [p], max_insns=400_000_000)
        finally:
            m.free(p)
            dt.st.task = self.D.DA_TASK

    def _carry(self) -> tuple[str, list[dict]]:
        """Carry every queued message to idle, playing the kernel + MapTblTask."""
        D, dt, m = self.D, self.dt, self.m
        outgoing: list[dict] = []
        while True:
            if dt.routed >= len(m.messages):
                before = len(m.messages)
                dt.map_task_turn()
                if len(m.messages) == before:
                    return "idle", outgoing
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
            elif x["task"] == TBL_TASK:
                self._tbl_turn(body)
            else:
                outgoing.append({"task": x["task"], "id": mid, "sub": sub,
                                 "pr": (x["pr"] - 4) & V.M32})
                self.outgoing_bodies.append((mid, body))

    def inject(self, cc: int, db: int, code: int, *, mutation: str = "none") -> dict:
        """Call fn 0x003bcc7c with one context and carry to the answer."""
        dt, m = self.dt, self.m
        out: dict = {"cc": cc, "db": db, "code": code, "mutation": mutation,
                     "table": LL.table_code(cc, db)}
        if mutation == "null-context":
            p = 0
        elif mutation in ("none", "wrong-id"):
            p = build_context(m, cc, db, code)
        else:
            raise ValueError("unknown mutation %r" % mutation)

        first_row, first_msg, first_inflate = len(dt.rows), len(m.messages), self.inflate_calls
        self.outgoing_bodies: list[tuple[int, bytes]] = []
        self.runner.live = True
        self.runner.builder = []
        self.runner.chain_hits = {k: 0 for k in self.runner.chain_hits}
        stop = None
        try:
            r0 = m.call(INJECT_FN, [p], max_insns=400_000_000)
        except (V.Blocked, V.EngineError) as exc:
            out["r0"], stop = None, "%s: %s" % (type(exc).__name__, str(exc)[:200])
        else:
            out["r0"] = r0 & 0xFFFFFFFF
        self.runner.live = False

        # Wrong-id mutation: rewrite the 0x14e4 request just sent to 0x14f4.
        if mutation == "wrong-id":
            for x in m.messages[first_msg:]:
                if x["kind"] == "send":
                    b = bytearray.fromhex(x["body"])
                    if struct.unpack_from("<H", b, 8)[0] == REQUEST:
                        struct.pack_into("<H", b, 8, 0x14F4)
                        x["body"] = b.hex()
                        break

        end, outgoing = self._carry() if stop is None else ("stopped", [])
        out["end"] = end
        out["stop"] = stop
        out["new_msgs"] = len(m.messages) - first_msg
        out["outgoing"] = outgoing
        out["builder_calls"] = len(self.runner.builder)
        out["builder"] = self.runner.builder[:4]
        out["reads"] = [{"file": r["file"], "pos": r["pos"] or 0,
                         "length": r["length"], "tag": r["tag"]}
                        for r in dt.rows[first_row:]]
        out["lctbl_reads"] = [r for r in out["reads"]
                              if LCTBL_PATH_KEY in r["file"].upper()]
        out["point_reads"] = [r for r in out["reads"]
                              if POINT_PATH_KEY in r["file"].upper()]
        out["inflates"] = self.inflate_calls - first_inflate
        out["status"] = None
        out["count"] = None
        out["record"] = None
        for mid, body in self.outgoing_bodies:
            if mid == ANSWER:
                status, count, ptr = struct.unpack_from("<III", body, 16)
                out["status"], out["count"] = status, count
                if status == FOUND and ptr:
                    out["record"] = bytes(m.eng.read_mem(ptr, 0x200)).hex()
        return out


def judge(inj: dict, model: dict) -> tuple[str, bool]:
    """Compare one injection's outcome with the model (lctbl_lookup style)."""
    # Mutations are artifact-level controls, not code presence/absence tests.
    if inj["mutation"] == "null-context":
        ok = inj["r0"] == 0xFFFFFFFF and inj["new_msgs"] == 0 and not inj["lctbl_reads"]
        return ("null context -> r0 %s, %d new messages, %d LCTBL reads"
                % (hex(inj["r0"] or 0), inj["new_msgs"], len(inj["lctbl_reads"]))), ok
    if inj["mutation"] == "wrong-id":
        ok = bool(inj["point_reads"]) and not inj["lctbl_reads"]
        return ("wrong id -> %d POINT reads, %d LCTBL reads"
                % (len(inj["point_reads"]), len(inj["lctbl_reads"]))), ok
    present, expected = LL.model_record(model, inj["cc"], inj["db"], inj["code"])
    if not present:
        return "table not in the model: status %s (not compared)" % inj["status"], True
    if expected is None:
        ok = inj["status"] == NOT_FOUND and inj["inflates"] == 0
        return ("absent code -> status %s, %d inflates"
                % (inj["status"], inj["inflates"])), ok
    ok = inj["status"] == FOUND and inj["record"] is not None
    detail = "present code -> status %s, %d inflates" % (inj["status"], inj["inflates"])
    if ok:
        got = bytes.fromhex(inj["record"])[:len(expected)]
        eq = LL.swap16(got) == expected
        detail += ", record %s the model's (%d B)" % ("equals" if eq else "DIFFERS", len(expected))
        ok = eq
    return detail, ok


def place_fields(inj: dict) -> str:
    """Decode the returned 48-byte place record into its named TMC fields."""
    if not inj["record"]:
        return "-"
    plain = LL.swap16(bytes.fromhex(inj["record"])[:0x200])
    nwords = int.from_bytes(plain[:2], "big") & 0x7FF
    d = TF.decode_record(plain[: 2 * nwords])
    if not d.get("ok"):
        return "decode failed: %s" % d.get("why")
    strings = {}
    for name, field in zip(TF.FIELD_NAMES, d["fields"]):
        if name in ("road_no", "road_name", "first_name", "second_name", "exit_no"):
            text = TF.text(field)
            if text:
                strings[name] = text
    return ", ".join("%s=%r" % kv for kv in strings.items())


def show(inj: dict, verdict: str, ok: bool) -> None:
    print("== inject country %d db %d code %d (table %#06x) mutation=%s -> %s%s"
          % (inj["cc"], inj["db"], inj["code"], inj["table"], inj["mutation"],
             inj["end"], ("; " + inj["stop"]) if inj["stop"] else ""))
    print("   call r0=%s, %d new message(s), %d name-builder calls, %d inflate(s)"
          % (None if inj["r0"] is None else hex(inj["r0"]),
             inj["new_msgs"], inj["builder_calls"], inj["inflates"]))
    for r in inj["reads"]:
        print("   read %-26s off=%#08x len=%#06x tag=%#06x"
              % (r["file"], r["pos"], r["length"], r["tag"]))
    print("   status=%s count=%s, LCTBL reads %d, POINT reads %d"
          % (inj["status"], inj["count"], len(inj["lctbl_reads"]), len(inj["point_reads"])))
    if inj["record"]:
        print("   place: %s" % place_fields(inj))
    print("   %s: %s" % ("PASS" if ok else "FAIL", verdict))


def cmd_run(a) -> int:
    import hashlib

    card = V.make_card(None, a.card_image, {})
    data = V.Expected(card).read(LL.LCTBL_PATH, 0, 1 << 30)
    model = L.parse(data)
    print("file: card's %s, %d B, sha256 %s; model: %d tables, %d records"
          % (LL.LCTBL_PATH, len(data), hashlib.sha256(data).hexdigest(),
             len(model["tables"]), sum(len(t["records"]) for t in model["tables"])))
    try:
        results = []
        specs = [LL.parse_lookup(s) for s in a.inject]
        # The firmware's TMC record-decoder keeps global state (0x006f3918)
        # that survives a lookup; a second injection on the same machine fails
        # its null check regardless of the code.  Use one fresh mounted machine
        # per code/mutation so every case starts from the loader's zero state.
        for cc, db, code in specs:
            inj = Injection(a.image, a.card_image)
            summary = inj.dt.summary()
            print("mount: %s, state %d, mesh_count %d, reads %d"
                  % (inj.mount, summary["state"], summary["mesh_count"], summary["reads"]))
            r = inj.inject(cc, db, code)
            r["mount"] = inj.mount
            r["verdict"], r["ok"] = judge(r, model)
            show(r, r["verdict"], r["ok"])
            results.append(r)
        for mut in a.mutation:
            inj = Injection(a.image, a.card_image)
            r = inj.inject(2, 25, 1203, mutation=mut)
            r["verdict"], r["ok"] = judge(r, model)
            show(r, r["verdict"], r["ok"])
            results.append(r)
    except (V.Blocked, V.EngineError) as exc:
        print("BLOCKED: %s: %s" % (type(exc).__name__, str(exc)[:300]))
        return 3

    bad = [r for r in results if not r["ok"]]
    falsified = False
    if len(specs) == 2:
        a_, b_ = results[0], results[1]
        sig_a = (tuple((x["file"], x["pos"], x["length"]) for x in a_["lctbl_reads"]),
                 a_["status"], a_["inflates"])
        sig_b = (tuple((x["file"], x["pos"], x["length"]) for x in b_["lctbl_reads"]),
                 b_["status"], b_["inflates"])
        same = sig_a == sig_b
        print("falsifier: signatures %s; present %s; absent %s"
              % ("IDENTICAL (FALSIFIED)" if same else "DIFFERENT (refuted)", sig_a, sig_b))
        if same:
            falsified = True
    print("injections: %d, agree with model: %d, falsified: %s"
          % (len(results), len(results) - len(bad), falsified))
    if a.json:
        for r in results:
            if r["record"]:
                r["place"] = place_fields(r)
        Path(a.json).write_text(json.dumps({
            "schema": "osm2leaf.tmc_inject_l3/v1", "build": "EU2011",
            "image": a.image, "card_image": a.card_image,
            "file_sha256": hashlib.sha256(data).hexdigest(),
            "mount": [r.get("mount") for r in results], "inject_fn": hex(INJECT_FN),
            "search_fn": hex(SEARCH_FN), "send_fn": hex(SEND_FN),
            "results": results, "falsified": falsified,
        }, indent=1) + "\n")
    return 1 if bad or falsified else 0


def selftest() -> int:
    failed = 0

    def check(name, cond):
        nonlocal failed
        print("  %-58s %s" % (name, "ok" if cond else "FAIL"))
        failed += 0 if cond else 1

    model = {"tables": [{"code": 0x3219, "codes": [7], "records": [b"\x00\x02AB"]}]}
    inj = {"cc": 2, "db": 25, "code": 7, "mutation": "none", "status": FOUND,
           "inflates": 1, "record": LL.swap16(b"\x00\x02AB").hex(), "r0": 0,
           "new_msgs": 1, "lctbl_reads": [{}], "point_reads": []}
    check("found record agrees with model", judge(inj, model)[1])
    inj2 = dict(inj, status=NOT_FOUND, inflates=0, record=None)
    check("absent (model present) fails", not judge(inj2, model)[1])
    check("record mismatch fails", not judge(dict(inj, record=LL.swap16(b"\x00\x02AC").hex()), model)[1])
    inj3 = dict(inj, mutation="null-context", r0=0xFFFFFFFF, new_msgs=0, lctbl_reads=[])
    check("null context negative", judge(inj3, model)[1])
    check("null context positive control fails when msg sent",
          not judge(dict(inj3, new_msgs=1), model)[1])
    inj4 = dict(inj, mutation="wrong-id", lctbl_reads=[], point_reads=[{}])
    check("wrong id negative", judge(inj4, model)[1])
    check("wrong id fails with LCTBL read", not judge(dict(inj4, lctbl_reads=[{}]), model)[1])
    inj5 = dict(inj, code=8, status=NOT_FOUND, inflates=0, record=None)
    check("absent code (table present) agrees", judge(inj5, model)[1])
    check("absent code with status 1 fails", not judge(dict(inj5, status=FOUND), model)[1])
    check("table code 2,25 is 0x3219", LL.table_code(2, 25) == 0x3219)
    print("tmc_inject_l3 selftest: %d failed" % failed)
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("image")
    r.add_argument("--card-image", required=True)
    r.add_argument("--inject", action="append", default=[], metavar="CC,DB,CODE",
                   help="location code to inject (repeat for present+absent)")
    r.add_argument("--mutation", action="append", default=[],
                   choices=("null-context", "wrong-id"),
                   help="negative control to inject")
    r.add_argument("--json")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "run":
        if not args.inject:
            ap.error("at least one --inject CC,DB,CODE is required")
        return cmd_run(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
