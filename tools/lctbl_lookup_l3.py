#!/usr/bin/env python3
"""L3: the firmware looks a TMC location code up in `LCTBL001.DAT` (M5.60).

The run is `tools/datask_l3.py`'s mount of a card plus one more task of the
same module, `HDL_MapTblTask`, and one request per lookup:

    request  0x14e4 sub 1 (the only static sender is the SDL function
             `sdl_rdstmc_search_non_cache`): +16 country code, +20 location
             database number, +24 location code
    table    code = (ASCII hex digit of the country code) << 8 | database
             number, e.g. country 2, database 25 -> 0x3219
    reads    0x0b61 header, 0x0b01 catalog, 0x0b02 B-tree index pages
             (root first), 0x0b62 page directory, 0x0b14 the zlib record page
    inflate  the data-access task hands the page to `HDL_MapTblTask` with
             message 0x14b8; that task inflates it and answers 0x14b9
    answer   0x14fb sub 29: +16 status (1 found, 4 not found), +20 count,
             +24 pointer to the record, each u16 byte-swapped

Each lookup is compared with the model `tools/lctbl_build.py parse` gives
for the same file: a code the model holds must come back as that record,
a code it does not hold must come back "not found".

Usage:
  lctbl_lookup_l3.py run IMG --card-image CARD [--file LCTBL001.DAT]
                         --lookup CC,DB,CODE [--lookup ...] [--flip OFF[:XOR]] [--json OUT]
  lctbl_lookup_l3.py extract --card-image CARD -o OUT   (the card's own file, for
                         `lctbl_build.py synth --header-from`; never commit it)
  lctbl_lookup_l3.py --selftest

`--file` replaces `RDSTM001/LCTBL001.DAT` of the card for the run (a file
written by `lctbl_build.py synth`); without it the card's own file is used.
Exit status: 0 every lookup agrees with the model, 1 one does not, 3 blocked.

Stdlib only.  All VAs are EU2011 build A `Navi.exe`.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

EU2011 = {
    "tbl_task_id": (0x11FF << 12) + 0xF34,   # data VA: id of HDL_MapTblTask
    "tbl_entry": 0x003EBE70,                 # its receive loop (not called: we are the loop)
    "tbl_inflate_msg": 0x004052D4,           # the loop's handler of message 0x14b8
    "tbl_after": 0x003EC034,                 # the loop's call after every message
}
REQUEST, ANSWER, TO_TBL = 0x14E4, 0x14FB, 0x14B8
FOUND, NOT_FOUND = 1, 4
TBL_TASK = 4
LCTBL_PATH = "RDSTM001/LCTBL001.DAT"
TAGS = {0x0B61: "header", 0x0B01: "catalog", 0x0B02: "index page", 0x0B62: "page directory",
        0x0B14: "record page"}


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------

def table_code(cc: int, db: int) -> int:
    """Table code of (country code, database number): the country code as
    one ASCII hex digit in the high byte."""
    return (ord("%X" % (cc & 0xF)) << 8) | (db & 0xFF)


def request_body(cc: int, db: int, code: int) -> bytes:
    body = bytearray(64)
    struct.pack_into("<HH", body, 8, REQUEST, 1)
    struct.pack_into("<III", body, 16, cc & 0xFFFF, db & 0xFFFF, code & 0xFFFF)
    return bytes(body)


def swap16(b: bytes) -> bytes:
    return b"".join(b[i + 1:i + 2] + b[i:i + 1] for i in range(0, len(b) - 1, 2))


def parse_lookup(spec: str) -> tuple[int, int, int]:
    parts = [int(x, 0) for x in spec.split(",")]
    if len(parts) != 3:
        raise ValueError("lookup needs CC,DB,CODE, got %r" % spec)
    return parts[0], parts[1], parts[2]


def model_record(model: dict, cc: int, db: int, code: int):
    """(table present, record bytes or None) from a `lctbl_build.parse` model."""
    want = table_code(cc, db)
    for t in model["tables"]:
        if t["code"] == want:
            if code in t["codes"]:
                return True, t["records"][t["codes"].index(code)]
            return True, None
    return False, None


def judge(table_present: bool, expected, status: int, got: bytes | None) -> tuple[str, bool]:
    """Verdict of one lookup against the model."""
    if not table_present:
        return "table not in the model: status %d (not compared)" % status, True
    if expected is None:
        ok = status == NOT_FOUND
        return ("not in the model: firmware says %s" % ("not found" if ok else "status %d" % status)), ok
    if status != FOUND or got is None:
        return "in the model, but the firmware answers status %d" % status, False
    ok = swap16(got[:len(expected)]) == expected
    return ("record equals the model's (%d B)" % len(expected)) if ok else "record DIFFERS from the model's", ok


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

class Lookup:
    def __init__(self, image: str, card, build: dict = EU2011):
        import datask_l3 as D
        import vcard_l3 as V
        self.D, self.V, self.b = D, V, build
        self.dt = D.DataTask(image, card)
        self.mount = self.dt.run()
        self.dt.m.put(build["tbl_task_id"], struct.pack("<I", TBL_TASK))
        self.inflate_calls = 0
        self.dt.m.eng.on_exec(self.dt.b["inflate"], self._on_inflate)

    def _on_inflate(self, _engine, _va):
        self.inflate_calls += 1
        return None

    def _tbl_turn(self, body: bytes) -> None:
        dt, m = self.dt, self.dt.m
        dt.st.task = TBL_TASK
        p = m.malloc(64)
        m.put(p, body.ljust(64, b"\0"))
        try:
            if struct.unpack_from("<H", body, 8)[0] == TO_TBL:
                m.call(self.b["tbl_inflate_msg"], [p], max_insns=400_000_000)
            m.call(self.b["tbl_after"], [p], max_insns=400_000_000)
        finally:
            m.free(p)
            dt.st.task = self.D.DA_TASK

    def lookup(self, cc: int, db: int, code: int) -> dict:
        D, dt, m = self.D, self.dt, self.dt.m
        first, inflates = len(dt.rows), self.inflate_calls
        out = {"cc": cc, "db": db, "code": code, "table": table_code(cc, db), "status": None, "count": 0,
               "record": None, "tbl_turns": 0}
        dt.deliver(request_body(cc, db, code))
        while True:
            if dt.routed >= len(m.messages):
                before = len(m.messages)
                dt.map_task_turn()
                if len(m.messages) == before:
                    break
                continue
            x = m.messages[dt.routed]
            dt.routed += 1
            if x["kind"] != "send":
                continue
            body = bytes.fromhex(x["body"])
            mid = struct.unpack_from("<H", body, 8)[0]
            if x["task"] == D.MAP_TASK:
                dt.map_task_turn()
            elif x["task"] == D.DA_TASK and mid == dt.b["done_msg"]:
                dt.complete(body, False)
            elif x["task"] == D.DA_TASK:
                dt.deliver(body)
            elif x["task"] == TBL_TASK:
                out["tbl_turns"] += 1
                self._tbl_turn(body)
            elif mid == ANSWER:
                status, count, ptr = struct.unpack_from("<III", body, 16)
                out["status"], out["count"] = status, count
                if status == FOUND and ptr:
                    out["record"] = bytes(m.eng.read_mem(ptr, 0x200))
        out["reads"] = [{"pos": r["pos"], "length": r["length"], "tag": r["tag"], "file": r["file"]}
                        for r in dt.rows[first:]]
        out["inflates"] = self.inflate_calls - inflates
        return out


def cmd_extract(args) -> int:
    """Copy the card's own LCTBL001.DAT out (for `lctbl_build.py synth --header-from`)."""
    import vcard_l3 as V
    data = V.Expected(V.make_card(None, args.card_image, {})).read(LCTBL_PATH, 0, 1 << 30)
    Path(args.output).write_bytes(data)
    import hashlib
    print("wrote %s: %d B, sha256 %s" % (args.output, len(data), hashlib.sha256(data).hexdigest()))
    return 0


def cmd_run(args) -> int:
    import lctbl_build as L
    import vcard_l3 as V
    mods = {"replace": ["%s=%s" % (LCTBL_PATH, args.file)]} if args.file else {}
    mods["flip"] = ["%s@%s" % (LCTBL_PATH, f) for f in args.flip]
    if args.file:
        data = Path(args.file).read_bytes()
    else:
        data = V.Expected(V.make_card(None, args.card_image, {})).read(LCTBL_PATH, 0, 1 << 30)
    model = L.parse(data)            # the model is always the undamaged file's
    card = V.make_card(None, args.card_image, mods)
    for f in args.flip:
        print("damage for this run: byte %s of the file on the card" % f)
    print("file: %s, %d B, sha256 %s; model: %d tables, %d records" % (
        args.file or "the card's " + LCTBL_PATH, len(data), L.sha(data),
        len(model["tables"]), sum(len(t["records"]) for t in model["tables"])))
    try:
        run = Lookup(args.image, card)
        results = []
        for spec in args.lookup:
            cc, db, code = parse_lookup(spec)
            res = run.lookup(cc, db, code)
            present, expected = model_record(model, cc, db, code)
            res["verdict"], res["ok"] = judge(present, expected, res["status"], res["record"])
            res["table_in_model"] = present
            results.append(res)
            kinds = [TAGS.get(r["tag"], "%#x" % r["tag"]) for r in res["reads"]]
            print("lookup country %d database %d code %d (table %#06x): status %s; reads: %s; "
                  "table-task turns %d, inflate calls %d" % (
                      cc, db, code, res["table"], res["status"],
                      ", ".join("%s %#x/%#x" % (k, r["pos"] or 0, r["length"])
                                for k, r in zip(kinds, res["reads"])) or "none (cached)",
                      res["tbl_turns"], res["inflates"]))
            print("  %s: %s" % ("PASS" if res["ok"] else "FAIL", res["verdict"]))
    except (V.Blocked, V.EngineError) as exc:
        print("BLOCKED: %s: %s" % (type(exc).__name__, str(exc)[:300]))
        return 3
    bad = [r for r in results if not r["ok"]]
    print("lookups: %d, agree with the model: %d" % (len(results), len(results) - len(bad)))
    if args.json:
        for r in results:
            r["record"] = r["record"][:128].hex() if r["record"] else None
        Path(args.json).write_text(json.dumps({"schema": "osm2leaf.lctbl_lookup_l3/v1", "build": "EU2011",
                                               "file_sha256": L.sha(data), "mount": run.mount,
                                               "results": results}, indent=1) + "\n")
    return 1 if bad else 0


# --------------------------------------------------------------------------
def selftest() -> int:
    failed = 0

    def check(name, cond):
        nonlocal failed
        print("  %-60s %s" % (name, "ok" if cond else "FAIL"))
        failed += 0 if cond else 1

    check("country 2, database 25 is table 0x3219", table_code(2, 25) == 0x3219)
    check("country 13 is the letter D", table_code(13, 1) == 0x4401)
    body = request_body(2, 25, 1203)
    check("request: id, sub and the three keys",
          struct.unpack_from("<HH", body, 8) == (0x14E4, 1) and struct.unpack_from("<III", body, 16) == (2, 25, 1203))
    check("swap16 swaps byte pairs", swap16(b"\x00\x18\x01\x00") == b"\x18\x00\x00\x01")
    check("a lookup spec parses", parse_lookup("3,0x19,7") == (3, 25, 7))
    model = {"tables": [{"code": 0x3319, "codes": [4, 7], "records": [b"\x00\x02AB", b"\x00\x02CD"]}]}
    check("model: code present", model_record(model, 3, 25, 7) == (True, b"\x00\x02CD"))
    check("model: code absent", model_record(model, 3, 25, 5) == (True, None))
    check("model: table absent", model_record(model, 3, 26, 7) == (False, None))
    check("found and equal passes", judge(True, b"\x00\x02CD", FOUND, swap16(b"\x00\x02CD") + b"\0\0")[1])
    check("found but different fails", not judge(True, b"\x00\x02CD", FOUND, swap16(b"\x00\x02CE"))[1])
    check("in the model but not found fails", not judge(True, b"\x00\x02CD", NOT_FOUND, None)[1])
    check("absent and not found passes", judge(True, None, NOT_FOUND, None)[1])
    check("absent but found fails", not judge(True, None, FOUND, b"\0\0")[1])
    print("lctbl_lookup_l3 selftest: %d failed" % failed)
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("run")
    p.add_argument("image")
    p.add_argument("--card-image", required=True)
    p.add_argument("--file", help="a generated LCTBL001.DAT to put on the card for this run")
    p.add_argument("--lookup", action="append", default=[], required=True, metavar="CC,DB,CODE")
    p.add_argument("--flip", action="append", default=[], metavar="OFF[:XOR]",
                   help="damage one byte of the file on the card (the model stays the undamaged file's)")
    p.add_argument("--json")
    x = sub.add_parser("extract", help="copy the card's LCTBL001.DAT to a file (do not commit it)")
    x.add_argument("--card-image", required=True)
    x.add_argument("-o", "--output", required=True)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "extract":
        return cmd_extract(args)
    ap.error("a command or --selftest is required")
    return 2


if __name__ == "__main__":
    sys.exit(main())
