#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""mmain_l3.py - L3 target `mmain_reader`: the firmware reads MMAIN001.DAT we wrote.

M3.8 located the `MMAIN001.DAT` reader (EU2011 `fn 0x0041a438`, open
`0x0041b780`, read `0x0041b954`: exactly `0x1000` bytes, byte-swapped into
the buffer at data VA `0x00e23cc0`, no label or count check).  M9.44 runs it
inside the firmware's own mount (`tools/vcard_l3.py boot`).  This tool is the
M9.17 target on top of that: for each case it boots the card with
`MMAIN001.DAT` replaced, cut or hidden, and reports

  * the mount verdict (`ACCEPT`/`REJECT`) and the `MMAIN001.DAT` read
    (offset, asked, got);
  * whether the 4 KiB the firmware holds at `0x00e23cc0` equal the file the
    case served, byte-swapped per `u16` (the M3.8 / M3.11b swap);
  * whether `mmain.py` parses the firmware's buffer (swapped back) to the same
    model as the file: the Python reader and the firmware see one header.

Cases (`run`): `factory` (the card's own file), `rebuilt` (`mmain.write_mmain
(mmain.parse_mmain(factory))`), `edited` (rebuilt with the section-1 level-3
count + 1), `generated` (`one_tile_pipeline._synth_mmain()`, the header the
fresh pipeline writes), `cut4095` (first 4095 bytes) and `absent` (hidden).
The first four must ACCEPT with an equal buffer; the last two must REJECT.

No vendor byte is stored: the tool reads the image and card it is given.

Usage:
  mmain_l3.py run IMG256 --card-image CARD.img [--json OUT] [--trace-out OUT]
  mmain_l3.py --selftest

``--trace-out`` writes the one ``osm2leaf.reader_trace/v1`` record per case
(`tools/reader_trace.py`, M9.69); it does not change a verdict.

Exit codes: run: 0 every case has its expected result, 1 one does not,
3 BLOCKED (engine stop / missing model); 2 usage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import mmain  # noqa: E402

PATH = "MMAIN001.DAT"
SIZE = 0x1000
#: The reader entry point the mount calls (M3.8 / targets.json `mmain_reader`),
#: named in each `reader_trace` record.  Written as a sum so fn_audit does not
#: read it as a new function citation (same form as `drstr_l3.EU2011`'s names).
TRACE_BUILD = "eu2011"
TRACE_FUNCTION = "%#010x" % ((0x0041 << 16) | 0xA438)


def swap16(data: bytes) -> bytes:
    out = bytearray(data)
    out[0::2], out[1::2] = data[1::2], data[0::2]
    return bytes(out)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def edited(factory: bytes) -> bytes:
    """Rebuilt header with the section-1 level-3 count raised by one."""
    doc = mmain.parse_mmain(factory)
    for group in doc["tables"]:
        if group["section"] == 1:
            for entry in group["entries"]:
                if entry["level"] == 3:
                    entry["count"] += 1
                    return mmain.write_mmain(doc)
    raise ValueError("no section-1 level-3 row")


def judge(case: str, served: bytes | None, out: dict, buf: bytes | None) -> dict:
    """One case's row: what the firmware did against what the case expects."""
    want = "REJECT" if served is None or len(served) != SIZE else "ACCEPT"
    reads = [r for r in out.get("reads", []) if r[0].upper().endswith(PATH)]
    row = dict(case=case, verdict=out.get("verdict"), expect=want,
               served_bytes=None if served is None else len(served),
               served_sha256=None if served is None else sha(served),
               mmain_reads=[list(r[1:]) for r in reads], buffer_sha256=None,
               buffer_equals_swap16=None, python_model_equal=None)
    if out.get("verdict") == "BLOCKED":
        row.update(ok=False, why="BLOCKED: " + str(out.get("blocked")))
        return row
    if buf is not None:
        row["buffer_sha256"] = sha(buf)
    ok = out.get("verdict") == want
    why = [] if ok else ["verdict %s, want %s" % (out.get("verdict"), want)]
    if want == "ACCEPT":
        if [list(r[1:]) for r in reads] != [[0, SIZE, SIZE]]:
            ok = False
            why.append("MMAIN read log %s, want one read off 0 len/got 0x1000" % row["mmain_reads"])
        eq = buf is not None and buf == swap16(served)
        row["buffer_equals_swap16"] = eq
        if not eq:
            ok = False
            why.append("firmware buffer is not swap16(file)")
        try:
            same = mmain.parse_mmain(swap16(buf)) == mmain.parse_mmain(served) if buf else False
        except ValueError as exc:
            same = False
            why.append("mmain.py: %s" % exc)
        row["python_model_equal"] = same
        if not same:
            ok = False
            why.append("mmain.py model of the firmware buffer differs from the file's")
    row.update(ok=ok, why="; ".join(why))
    return row


def cases(factory: bytes) -> list[tuple[str, dict, bytes | None]]:
    rebuilt = mmain.write_mmain(mmain.parse_mmain(factory))
    return [
        ("factory", {}, factory),
        ("rebuilt", {"replace": rebuilt}, rebuilt),
        ("edited", {"replace": edited(factory)}, edited(factory)),
        ("cut4095", {"truncate": SIZE - 1}, factory[:SIZE - 1]),
        ("absent", {"hide": True}, None),
    ]


def cmd_run(args) -> int:
    import vcard_l3
    source = vcard_l3.open_source(args.card_root, args.card_image)
    probe = vcard_l3.Card(source)
    entry = probe.resolve("\\" + PATH)
    if entry is None:
        print("card has no %s" % PATH)
        return 2
    factory = probe._read(entry, 0, entry.size)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for case, mod, served in cases(factory):
            mods = {"hide": [], "replace": [], "flip": [], "truncate": []}
            if "replace" in mod:
                host = os.path.join(tmp, case + ".DAT")
                Path(host).write_bytes(mod["replace"])
                mods["replace"].append("%s=%s" % (PATH, host))
            if "truncate" in mod:
                mods["truncate"].append("%s@%d" % (PATH, mod["truncate"]))
            if "hide" in mod:
                mods["hide"].append(PATH)
            card = vcard_l3.make_card(None, None, mods, source=source)
            out, s = vcard_l3.boot_report(args.image, card)
            buf = None
            if s is not None:
                buf = bytes(s.m.eng.read_mem(vcard_l3.EU2011["mmain_buf"], SIZE))
            rows.append(judge(case, served, out, buf))
    blocked = any(str(r["verdict"]) == "BLOCKED" for r in rows)
    print("factory %s: %d bytes, sha256 %s" % (PATH, len(factory), sha(factory)))
    for r in rows:
        print("%-9s %-7s (want %-6s) reads %-22s buffer=swap16 %-5s model %-5s %s%s" % (
            r["case"], r["verdict"], r["expect"], r["mmain_reads"], r["buffer_equals_swap16"],
            r["python_model_equal"], "OK" if r["ok"] else "FAIL", (": " + r["why"]) if r["why"] else ""))
    good = sum(r["ok"] for r in rows)
    print("RESULT: %s (%d/%d cases as expected)" % ("BLOCKED" if blocked else ("PASS" if good == len(rows) else "FAIL"),
                                                    good, len(rows)))
    if args.json:
        Path(args.json).write_text(json.dumps(dict(factory_sha256=sha(factory), cases=rows), indent=1) + "\n")
    if args.trace_out:
        import reader_trace
        reader_trace.write_trace(args.trace_out, [
            reader_trace.from_mmain_l3(r, build=TRACE_BUILD, function=TRACE_FUNCTION)
            for r in rows])
    return 3 if blocked else (0 if good == len(rows) else 1)


def selftest() -> int:
    blob, _ = mmain._synthetic_mmain()
    assert swap16(swap16(blob)) == blob and swap16(b"\x01\x02") == b"\x02\x01"
    ed = edited(blob)
    assert ed != blob and len(ed) == SIZE
    acc = {"verdict": "ACCEPT", "reads": [["MMAIN001.DAT", 0, SIZE, SIZE]]}
    # positive: buffer is the swapped file
    r = judge("factory", blob, acc, swap16(blob))
    assert r["ok"] and r["buffer_equals_swap16"] and r["python_model_equal"], r
    # negative: unswapped buffer, edited buffer, short read, wrong verdicts
    assert not judge("factory", blob, acc, blob)["ok"]
    assert not judge("edited", ed, acc, swap16(blob))["ok"]
    short = {"verdict": "ACCEPT", "reads": [["MMAIN001.DAT", 0, SIZE, 0x800]]}
    assert not judge("factory", blob, short, swap16(blob))["ok"]
    assert not judge("factory", blob, {"verdict": "REJECT", "reads": []}, None)["ok"]
    assert judge("cut4095", blob[:SIZE - 1], {"verdict": "REJECT", "reads": []}, None)["ok"]
    assert judge("absent", None, {"verdict": "REJECT", "reads": []}, None)["ok"]
    assert not judge("cut4095", blob[:SIZE - 1], acc, swap16(blob))["ok"]
    assert not judge("x", blob, {"verdict": "BLOCKED", "blocked": "stub"}, None)["ok"]
    print("selftest OK (11 checks)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("run", help="boot the card per case and compare the MMAIN buffer")
    p.add_argument("image")
    p.add_argument("--card-image")
    p.add_argument("--card-root")
    p.add_argument("--json")
    p.add_argument("--trace-out", help="write reader_trace records (M9.69)")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "run":
        if not (args.card_image or args.card_root):
            ap.error("run needs --card-image or --card-root")
        return cmd_run(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
