#!/usr/bin/env python3
"""M3.29: which firmware function reads each REFER family's record bytes (run).

The static graph (M3.23) gives one shared candidate list for ``ADDRE``,
``INTER``, ``FRWAY``, ``ZCODE`` and ``COORD`` because they go through one
opener, ``fn 0x003fbed8``, whose family is the run-time word ctx +124
(C-4666).  This tool splits that list at run time: it mounts the EU 2011 card
in the ``datask_l3.py`` machine (the data-access and map-file tasks), delivers
the REFER reads the live task makes on a boot (``0x0d02`` header, ``0x0d00``
page, ``0x0d10``/``0x0d11`` search pages) and attributes every guest load of
the returned buffer to the function that executed it -- M9.38's read watch
(``datask_l3.py complete``), not a new static pattern.

It reports, per family, whether its file was read at all, and it records the
task's end state and any undelivered message (the Stop reason).  The ``openers``
command runs the shared opener ``0x003fee70`` for each family on the card.

Result: the boot issues no ``ADDRE``/``FRWAY``/``INTER``/``ZCODE`` read (the
task ends ``both tasks idle`` waiting on message ``0x1507``); the record
readers this tool measures are the ``ICODE``/``ICADM``/``POINT`` ones.

Usage:
  m3_29_family_readers.py --selftest
  m3_29_family_readers.py run IMG256 --card-image CARD.img [--json OUT]

Method and results: docs/experiments/EXP-2026-11-20-M3.29-refer-family-split.md
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

import datask_l3 as D  # noqa: E402
import vcard_l3 as V  # noqa: E402

#: The REFER read tags the data-access task issues on a boot (M3.29 run).
#: 0x0d02 = volume header, 0x0d00 = a 0x100-0x300 B page,
#: 0x0d10/0x0d11 = the two search pages (M3.29 run).
REFER_TAGS = (0x0D00, 0x0D02, 0x0D10, 0x0D11)

#: The five families the opener selects by ctx +124 (C-4666).
FAMILIES = {1: "POINT", 2: "ADDRE", 3: "FRWAY", 4: "INTER", 11: "ZCODE"}

#: The families the run reports its read state for.  The five above, plus
#: ``COORD001`` -- not a ctx +124 family, but a REFER file in the task's
#: scope (M3.14) whose reader is the same open question.
READ_FAMILIES = ("POINT", "ADDRE", "FRWAY", "INTER", "ZCODE", "COORD")

#: M3.23's per-family top-ten candidate lists (EXP-2026-11-20-M3.23, QA/QC).
QC = {
    "ICODE": [0x00401E94, 0x00402690, 0x003F0C7C, 0x003F07F8, 0x003F0E94,
              0x003F08CC, 0x003F06A8, 0x003EFF20, 0x003F088C, 0x0040782C],
    "POINT": [0x003F56BC, 0x003F5E10, 0x003F51E0, 0x00416880, 0x0040E28C,
              0x003FE61C, 0x003F056C, 0x003F5B88, 0x0040EC84, 0x003F01DC],
    "REFER": [0x003F0AEC, 0x003FD690, 0x003FBBAC, 0x0040DFA8, 0x003FDD18,
              0x0040D704, 0x0040DA3C],
    "LCTBL": [0x0040DD40, 0x0040DE98, 0x004125A8, 0x00409CC8, 0x0040B358],
}


def _reads(card, tag: int):
    """``card.log`` entries of one read tag, in order."""
    return [e for e in card.log if e.get("tag") == tag]


def _reader_fns(rows) -> list:
    """Distinct non-zero function starts that load a REFER buffer, per file."""
    out = {}
    for row in rows:
        if "REFER" not in row["file"]:
            continue
        fns = sorted({r["fn"] for r in row["readers"] if r["fn"]})
        out.setdefault(row["file"], set()).update(fns)
    return {k: sorted(v) for k, v in out.items()}


def run(image: str, card_image: str) -> dict:
    card = V.make_card(None, card_image, {})
    t = D.DataTask(image, card)
    rows = []
    end = t.run(0, True, lambda row: rows.append(row))
    by_file = _reader_fns(rows)
    opened = {path: [hex(f) for f in fns] for path, fns in by_file.items()}
    by_tag = {}
    for tag in REFER_TAGS:
        fns = set()
        for row in rows:
            if row["tag"] == tag and "REFER" in row["file"]:
                fns.update(r["fn"] for r in row["readers"] if r["fn"])
        by_tag["%#06x" % tag] = {"file": next((r["file"] for r in rows if r["tag"] == tag), None),
                                 "readers": sorted(hex(v) for v in fns)}
    confirmed = set()
    for fns in by_file.values():
        confirmed.update(fns)
    recall = {}
    for name, cand in QC.items():
        hit = sorted(hex(v) for v in (confirmed & set(cand)))
        recall[name] = {"top10": [hex(v) for v in cand], "confirmed_in_top10": hit,
                        "recall": "%d/%d" % (len(hit), len(confirmed))}
    family_files = {}
    for name in READ_FAMILIES:
        hits = sorted({r["file"] for r in rows
                       if r["file"].split("/")[-1].upper().startswith(name)})
        family_files[name] = hits
    undelivered = [o for o in t.other]
    waits = [o for o in undelivered if o.get("kind") == "send"]
    return {"tags": [hex(t0) for t0 in REFER_TAGS],
            "end": end,
            "families_read": family_files,
            "undelivered": undelivered,
            "message_wait": [{"task": o.get("task"), "id": o.get("id"),
                              "id_hex": hex(o.get("id", 0))} for o in waits],
            "fwlog": t.s.fwlog[-5:],
            "refer_reads": [(r["tag"], r["file"], hex(r["pos"] or 0), hex(r["length"]))
                            for r in rows if "REFER" in r["file"]],
            "readers_per_file": opened,
            "readers_per_tag": by_tag,
            "confirmed_readers": sorted(hex(v) for v in confirmed),
            "recall": recall}


def openers(image: str, card_image: str) -> dict:
    """Run the family opener on the card; record the file and any read request.

    ``0x003fee70`` is one of the fourteen callers of ``0x003fbed8`` (M3.28);
    it passes the family through the context word at +124.  The run shows
    which file the firmware resolves for that family and whether the call
    reaches the map-file read API at all.
    """
    card = V.make_card(None, card_image, {})
    s = V.Session(image, card)
    boot = s.boot()
    m = s.m
    if boot.get("verdict") != "ACCEPT":
        raise V.Blocked("card did not mount: %s" % boot.get("verdict"))
    resolves, reads = [], [0]

    def on_resolve(engine, va):
        resolves.append((m.cstr(m.arg(0)), m.cstr(m.arg(1))))
        return None

    def on_read(engine, va):
        reads[0] += 1
        return None

    m.eng.on_exec(s.b["resolve"], on_resolve)
    m.eng.on_exec(s.b["read"], on_read)
    out = {}
    for family in sorted(FAMILIES):
        ctx = m.malloc(0x800)
        m.put(ctx, bytes(0x800))
        m.put(ctx + 104, struct.pack("<I", 0x14CC))
        m.put(ctx + 124, struct.pack("<I", family))
        del resolves[:]
        reads[0] = 0
        try:
            r0 = m.call(0x003FEE70, [ctx], max_insns=20_000_000)
        except (V.Blocked, V.EngineError) as exc:
            r0 = "stop: %s" % str(exc)[:80]
        finally:
            m.free(ctx)
        out[FAMILIES[family]] = {"family": family,
                                 "named": ["%s/%s" % (d, n) for d, n in resolves],
                                 "read_requests": reads[0],
                                 "r0": r0 if isinstance(r0, str) else hex(r0)}
    return {"boot": boot.get("verdict"), "openers": out}


def selftest() -> int:
    fails = 0

    def check(name, cond):
        nonlocal fails
        fails += not cond
        print("  %-58s %s" % (name, "ok" if cond else "FAIL"))

    rows = [{"file": "REFER001/ADDRE001.DAT",
             "readers": [{"fn": 0x3F0400}, {"fn": 0}, {"fn": 0x3F0400}]},
            {"file": "MAPAL001/B28R070R.DAT", "readers": [{"fn": 0x0040ACB8}]}]
    fns = _reader_fns(rows)
    check("readers are de-duplicated and zero is dropped",
          fns == {"REFER001/ADDRE001.DAT": [0x3F0400]})
    check("a non-REFER file is not a REFER reader",
          "MAPAL001/B28R070R.DAT" not in fns)
    check("family names are the five from C-4666",
          FAMILIES == {1: "POINT", 2: "ADDRE", 3: "FRWAY", 4: "INTER", 11: "ZCODE"})
    check("the run reports the five families plus COORD",
          READ_FAMILIES == ("POINT", "ADDRE", "FRWAY", "INTER", "ZCODE", "COORD"))
    check("M3.23 lists are ten, ten, seven and five",
          [len(QC[k]) for k in ("ICODE", "POINT", "REFER", "LCTBL")] == [10, 10, 7, 5])
    return 0 if not fails else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("image")
    r.add_argument("--card-image")
    r.add_argument("--card-root")
    r.add_argument("--json")
    o = sub.add_parser("openers")
    o.add_argument("image")
    o.add_argument("--card-image")
    o.add_argument("--card-root")
    o.add_argument("--json")
    args = ap.parse_args(argv)
    if args.selftest:
        n = selftest()
        print("selftest:", "PASS" if n == 0 else "FAIL")
        return n
    if args.cmd == "run":
        out = run(args.image, args.card_image)
        for path, fns in out["readers_per_file"].items():
            print("%-32s readers %s" % (path, fns))
        for tag, row in out["readers_per_tag"].items():
            print("tag %s %-28s readers %s" % (tag, row["file"], row["readers"]))
        for name, files in out["families_read"].items():
            print("family %-6s read files: %s" % (name, files or "NONE"))
        print("end: %s; message wait: %s" % (
            out["end"], [w["id_hex"] for w in out["message_wait"]] or "none"))
        print("confirmed readers: %s" % out["confirmed_readers"])
        for name, row in out["recall"].items():
            print("recall %-6s %s  (%s)" % (name, row["recall"], row["confirmed_in_top10"]))
        if args.json:
            Path(args.json).write_text(json.dumps(out, indent=1))
        return 0 if out["confirmed_readers"] else 1
    if args.cmd == "openers":
        out = openers(args.image, args.card_image)
        for name, row in out["openers"].items():
            names = ",".join(row["named"]) or "-"
            print("%-6s family %2d -> %-30s read_requests=%d r0=%s" % (
                name, row["family"], names, row["read_requests"], row["r0"]))
        if args.json:
            Path(args.json).write_text(json.dumps(out, indent=1))
        return 0 if out["openers"] else 1
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
