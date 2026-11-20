#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""mount_dirs_l3.py - check a firmware mount run against the Python container models.

`datask_l3.py mount --json` (M9.13) records every read the firmware's
data-access task asks for during the mount and which bytes each firmware
function loaded from it.  For a `MAPAL001` file that is the header, one table
per section and the directories under the start position.  This tool answers
the M9.18 question for those reads: does the firmware walk the file the way
our Python readers say it is built?

  * `MAPAL001/LEV3456R.DAT` is modelled by `tools/lev3456.py`
    (`read_section_table`, `read_sections`, `read_dir`);
  * a `BxxRyyR.DAT` tile by `tools/ze0-viewer/tools_ze0/clarion_tile.py`
    (`read_tile`, the reader `tilewriter.py` and `section4.py` work with).

For each read of the named file:

  * a section-table read (handler `0x0040c308`, EU2011) must ask for a
    section table the model lists, and the firmware's table walker
    (`0x0040be84`) must load bytes only inside that table (`2 * words`);
  * a directory read (handler `0x0041597c`) must ask for a directory the model
    lists (section, level, index), and the slot-table parser picked by
    `0x004157dc` must load exactly `+0xa` to the end of the directory the
    header word 0 declares (`2 * size - 1`).

`compare` takes two runs with their files and compares them relative to the
model: the same (section, level, directory index) in the same order, the same
parser and the same loaded ranges, while the file offsets may differ.  That is
the verdict for a generated file whose records moved (`SAME-RELOCATED`).
Reads of other files are compared as `datask_l3.py diff` does.

No vendor byte is stored: the tool reads the files it is given.

Usage:
  mount_dirs_l3.py check   RUN.json --file MAPAL001/LEV3456R.DAT=PATH [--file ...]
  mount_dirs_l3.py compare A.json B.json --file-a REL=PATH --file-b REL=PATH
  mount_dirs_l3.py --selftest

Exit codes: check: 0 every read of the file matches the model, 1 a read does
not, 3 the run never read the file; compare: 0 SAME/SAME-RELOCATED,
1 DIFFERENT; 2 usage or missing input.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "ze0-viewer" / "tools_ze0"))

import lev3456  # noqa: E402
import clarion_tile  # noqa: E402

# EU2011 Navi.exe (M3.25, C-4683-C-4691): read-completion handlers and the
# two functions every directory read passes through before its slot parser.
H_HEADER = 0x0040B8B4
H_TABLE = 0x0040C308
H_DIR = 0x0041597C
FN_TABLE = 0x0040BE84
FN_BLOCKHDR = (0x004156A4, 0x004144A8)


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------

def model_lev3456(data: bytes) -> dict:
    """Tables and directories of a LEV3456R file as `lev3456.py` reads them."""
    tables, dirs = {}, {}
    sections = lev3456.read_sections(data)
    for si, ((taddr, _cnt), sec) in enumerate(zip(lev3456.read_section_table(data), sections)):
        tables[taddr] = dict(section=sec.id, index=si, words=lev3456.u16(data, taddr))
        for L in sec.levels:
            for di, D in enumerate(L.dirs):
                nonempty = sum(1 for r in D.rows if r)
                recs = sum(1 for r in D.rows if r for x in r if x is not None)
                dirs[D.off] = dict(section=sec.id, level=L.level, index=di, box=list(D.box),
                                   size=D.head[0], rows=D.head[1], cols=D.head[2],
                                   typ=D.head[5], filled_rows=nonempty, records=recs)
    return dict(kind="lev3456", tables=tables, dirs=dirs)


def model_tile(data: bytes) -> dict:
    """Tables and directories of a BxxRyyR tile as `clarion_tile.py` reads them."""
    t = clarion_tile.read_tile(data)
    tables, dirs = {}, {}
    for si, sec in enumerate(t["sections"]):
        tables[sec["taddr"]] = dict(section=sec["id"], index=si, words=sec["table_words"])
        for L in sec["levels"]:
            for di, D in enumerate(L["dirs"]):
                recs = sum(len(s["recs"]) for s in D["slots"].values())
                dirs[D["off"]] = dict(section=sec["id"], level=L["level"], index=di,
                                      box=list(D["box"]),
                                      size=struct.unpack_from(">H", data, D["off"])[0],
                                      rows=D["nslots"], cols=None, typ=D["typ"],
                                      filled_rows=len(D["slots"]), records=recs)
    return dict(kind="tile", tables=tables, dirs=dirs)


def load_model(rel: str, path: str) -> dict:
    data = Path(path).read_bytes()
    if "LEV3456R" in rel.upper():
        return model_lev3456(data)
    return model_tile(data)


# ---------------------------------------------------------------------------
# checking one run
# ---------------------------------------------------------------------------

def span(reader: dict) -> tuple[int, int] | None:
    runs = reader.get("runs") or []
    if not runs:
        return None
    return min(r[0] for r in runs), max(r[1] for r in runs)


def classify(row: dict, model: dict) -> dict:
    """One read of the file against the model: a dict with `ok` and `why`."""
    pos = row.get("pos") or 0
    out = dict(pos=pos, length=row["length"], handler=row["handler"], status=row["status"])
    if row["status"] != 0:
        out.update(kind="failed", ok=False, why="read status %d" % row["status"])
        return out
    if row["handler"] == H_HEADER:
        out.update(kind="header", ok=pos == 0, why="" if pos == 0 else "header read not at 0")
        return out
    if row["handler"] == H_TABLE:
        t = model["tables"].get(pos)
        if t is None:
            out.update(kind="table", ok=False, why="no section table at %#x in the model" % pos)
            return out
        rd = [r for r in row["readers"] if r["fn"] == FN_TABLE]
        sp = span(rd[0]) if rd else None
        ok = sp is not None and sp[1] < 2 * t["words"]
        out.update(kind="table", section=t["section"], words=t["words"],
                   parser=FN_TABLE, loaded=sp, ok=ok,
                   why="" if ok else "table walker loads %s outside %d words" % (sp, t["words"]))
        return out
    if row["handler"] == H_DIR:
        d = model["dirs"].get(pos)
        if d is None:
            out.update(kind="dir", ok=False, why="no directory at %#x in the model" % pos)
            return out
        body = [r for r in row["readers"] if r["fn"] not in FN_BLOCKHDR]
        out.update(kind="dir", section=d["section"], level=d["level"], index=d["index"],
                   box=d["box"], size=d["size"], typ=d["typ"], rows=d["rows"],
                   filled_rows=d["filled_rows"], records=d["records"])
        if len(body) != 1:
            out.update(ok=False, parser=None, loaded=None,
                       why="%d slot-table parsers ran (want 1)" % len(body))
            return out
        sp = span(body[0])
        want = (0xA, 2 * d["size"] - 1)
        ok = sp == want
        out.update(parser=body[0]["fn"], loaded=sp, want=want, ok=ok,
                   why="" if ok else "parser loads %s, model says %s" % (
                       sp and tuple(hex(x) for x in sp), tuple(hex(x) for x in want)))
        return out
    out.update(kind="other", ok=False, why="handler %#x not modelled" % row["handler"])
    return out


def check_run(run: dict, rel: str, model: dict) -> list[dict]:
    return [classify(r, model) for r in run["rows"] if r["file"].upper() == rel.upper()]


def fmt_row(i: int, c: dict) -> str:
    head = "%2d %-6s pos %#10x len %#7x" % (i, c["kind"], c["pos"], c["length"])
    if c["kind"] == "table" and "section" in c:
        head += "  section %d (%d words)" % (c["section"], c["words"])
    elif c["kind"] == "dir" and "section" in c:
        head += "  s%d L%d dir %d size %d rows %d typ %#x filled %d records %d" % (
            c["section"], c["level"], c["index"], c["size"], c["rows"], c["typ"],
            c["filled_rows"], c["records"])
    if c.get("parser"):
        head += "  fn %#010x loads %s" % (c["parser"], c["loaded"] and "%#x-%#x" % c["loaded"])
    return head + ("  OK" if c["ok"] else "  MISMATCH: " + c["why"])


def parse_file_arg(s: str) -> tuple[str, str]:
    rel, sep, path = s.partition("=")
    if not sep:
        raise SystemExit("--file wants REL=PATH, got %r" % s)
    return rel, path


def cmd_check(args) -> int:
    run = json.loads(Path(args.run).read_text())
    rc = 0
    report = {}
    for spec in args.file:
        rel, path = parse_file_arg(spec)
        rows = check_run(run, rel, load_model(rel, path))
        report[rel] = rows
        print("%s (%s): %d read(s)" % (rel, path, len(rows)))
        for i, c in enumerate(rows, 1):
            print("  " + fmt_row(i, c))
        bad = sum(1 for c in rows if not c["ok"])
        if not rows:
            print("  verdict: NOT READ")
            rc = max(rc, 3)
        else:
            print("  verdict: %s (%d/%d reads match the model)" % (
                "MATCH" if not bad else "MISMATCH", len(rows) - bad, len(rows)))
            if bad:
                rc = 1 if rc != 3 else rc
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1, default=list) + "\n")
    return rc


# ---------------------------------------------------------------------------
# comparing two runs relative to their models
# ---------------------------------------------------------------------------

def rel_key(c: dict) -> tuple:
    if c["kind"] == "dir":
        return ("dir", c.get("section"), c.get("level"), c.get("index"), c.get("parser"),
                tuple(c["loaded"]) if c.get("loaded") else None, c["ok"])
    if c["kind"] == "table":
        return ("table", c.get("section"), tuple(c["loaded"]) if c.get("loaded") else None, c["ok"])
    return (c["kind"], c["pos"], c["length"], c["ok"])


def other_key(r: dict) -> tuple:
    return (r["file"], r["tag"], r.get("pos"), r["length"], r["status"], r["handler"],
            tuple((x["fn"], x["bytes"], x["nruns"]) for x in r["readers"]))


def compare_runs(a: dict, ma: dict, b: dict, mb: dict, rel: str) -> tuple[str, list[str]]:
    diffs = []
    ca, cb = check_run(a, rel, ma), check_run(b, rel, mb)
    moved = False
    for i in range(max(len(ca), len(cb))):
        if i >= len(ca) or i >= len(cb):
            diffs.append("%s read %d only in %s" % (rel, i + 1, "A" if i >= len(cb) else "B"))
            continue
        if rel_key(ca[i]) != rel_key(cb[i]):
            diffs.append("%s read %d: A %s / B %s" % (rel, i + 1, fmt_row(i + 1, ca[i]), fmt_row(i + 1, cb[i])))
        elif ca[i]["pos"] != cb[i]["pos"]:
            moved = True
    oa = [other_key(r) for r in a["rows"] if r["file"].upper() != rel.upper()]
    ob = [other_key(r) for r in b["rows"] if r["file"].upper() != rel.upper()]
    for i in range(max(len(oa), len(ob))):
        if i >= len(oa) or i >= len(ob) or oa[i] != ob[i]:
            diffs.append("other read %d differs: A %s / B %s" % (
                i + 1, oa[i] if i < len(oa) else None, ob[i] if i < len(ob) else None))
    if (a["end"], a["state"], a["mesh_count"]) != (b["end"], b["state"], b["mesh_count"]):
        diffs.append("the runs end differently")
    if diffs:
        return "DIFFERENT", diffs
    return ("SAME-RELOCATED" if moved else "SAME"), []


def changed_dirs(data_a: bytes, data_b: bytes) -> list[dict]:
    """Directories of two LEV3456R files (same section/level/dir grid) whose
    records differ: per directory the rows and records whose inflated bytes
    differ, with the directory offset in each file."""
    ca, cb = lev3456.Container(data_a), lev3456.Container(data_b)
    out = []
    for sa, sb in zip(ca.sections, cb.sections):
        for La, Lb in zip(sa.levels, sb.levels):
            for di, (Da, Db) in enumerate(zip(La.dirs, Lb.dirs)):
                rows = recs = 0
                for ra, rb in zip(Da.rows, Db.rows):
                    pa = [x.plain if x else None for x in (ra or [])]
                    pb = [x.plain if x else None for x in (rb or [])]
                    if pa != pb:
                        rows += 1
                        recs += sum(1 for x, y in zip(pa, pb) if x != y) + abs(len(pa) - len(pb))
                if rows:
                    out.append(dict(section=sa.id, level=La.level, index=di, box=list(Da.box),
                                    off_a=Da.off, off_b=Db.off, rows=rows, records=recs))
    return out


def cmd_changed(args) -> int:
    rows = changed_dirs(Path(args.a).read_bytes(), Path(args.b).read_bytes())
    for r in rows:
        print("s%d L%d dir %-3d box %-26s A %#10x B %#10x: %d row(s), %d record(s) differ" % (
            r["section"], r["level"], r["index"], r["box"], r["off_a"], r["off_b"],
            r["rows"], r["records"]))
    print("%d directory(ies) with changed records" % len(rows))
    return 0


def cmd_compare(args) -> int:
    a = json.loads(Path(args.a).read_text())
    b = json.loads(Path(args.b).read_text())
    rel_a, pa = parse_file_arg(args.file_a)
    rel_b, pb = parse_file_arg(args.file_b)
    if rel_a.upper() != rel_b.upper():
        raise SystemExit("--file-a and --file-b must name the same card file")
    verdict, diffs = compare_runs(a, load_model(rel_a, pa), b, load_model(rel_b, pb), rel_a)
    for line in diffs:
        print("  " + line)
    print("verdict: %s (%d difference(s))" % (verdict, len(diffs)))
    return 0 if verdict != "DIFFERENT" else 1


# ---------------------------------------------------------------------------
# selftest: a synthetic two-section container both readers accept
# ---------------------------------------------------------------------------

def _synthetic(shift: int = 0, rows: int = 2, pairs: int = 1) -> bytes:
    """Header + level table + section table + one group table and one
    directory per section; every slot ABSENT (no record bytes)."""
    size_b = 12 + rows * (4 + 8 * pairs)
    size_b += size_b % 2
    t1, t2 = 0x1000 + shift, 0x1100 + shift
    d1, d2 = 0x1200 + shift, 0x1300 + shift
    buf = bytearray(b"\xff" * (0x1400 + shift))
    buf[:0x1000] = b"\x00" * 0x1000
    # level table: 2 sections, one level each
    struct.pack_into(">H", buf, lev3456.LEVEL_OFF, 2)
    struct.pack_into(">BBBBH", buf, lev3456.LEVEL_OFF + 2, 1, 1, 5, 0x91, 1)
    struct.pack_into(">BBBBH", buf, lev3456.LEVEL_OFF + 8, 2, 1, 5, 0x91, 1)
    # section table at 0x800, then the terminator
    struct.pack_into(">IH", buf, lev3456.SECT_OFF, lev3456.addr_code(t1), 1)
    struct.pack_into(">IH", buf, lev3456.SECT_OFF + 6, lev3456.addr_code(t2), 1)
    struct.pack_into(">IH", buf, lev3456.SECT_OFF + 12, lev3456.ABSENT, 0)
    for ta, da in ((t1, d1), (t2, d2)):
        code = lev3456.addr_code(da)
        # words: nw, level offset, group len, group count, y1 y0 x0 x1 hi lo
        w = [10, 2, 8, 1, 10, 0, 0, 10, code >> 16, code & 0xFFFF]
        struct.pack_into(">10H", buf, ta, *w)
        struct.pack_into(">6H", buf, da, size_b // 2, rows, pairs, 0, 0, 0x91)
        for r in range(rows):
            struct.pack_into(">I", buf, da + 12 + r * (4 + 8 * pairs), lev3456.ABSENT)
    return bytes(buf)


def _row(file, pos, handler, readers, status=0, length=0x100):
    return dict(file=file, tag=0x700, pos=pos, length=length, status=status, handler=handler,
                readers=[dict(fn=f, bytes=b - a + 1, runs=[[a, b]], nruns=1) for f, a, b in readers])


def _run(shift: int, size_b: int, parser_end: int | None = None) -> dict:
    rel = "MAPAL001/LEV3456R.DAT"
    end = size_b - 1 if parser_end is None else parser_end
    rows = [_row(rel, 0, H_HEADER, [(0x0040A8D0, 0xFA, 0xFD)])]
    for ta, da in ((0x1000 + shift, 0x1200 + shift), (0x1100 + shift, 0x1300 + shift)):
        rows.append(_row(rel, ta, H_TABLE, [(FN_TABLE, 2, 19)]))
        rows.append(_row(rel, da, H_DIR, [(0x004156A4, 6, 9), (0x004144A8, 2, 5),
                                           (0x00414930, 0xA, end)]))
    rows.append(_row("MAPAL001/B48R058R.DAT", 0, H_HEADER, [(0x0040A8D0, 0xFA, 0xFD)]))
    return dict(rows=rows, end="both tasks idle", state=2, mesh_count=46)


def selftest() -> int:
    rel = "MAPAL001/LEV3456R.DAT"
    a = _synthetic(0)
    size_b = 12 + 2 * 12
    ma = model_lev3456(a)
    assert len(ma["tables"]) == 2 and len(ma["dirs"]) == 2, ma
    # the generic tile reader agrees with lev3456 on tables and directories
    mt = model_tile(a)
    assert sorted(mt["tables"]) == sorted(ma["tables"]), (mt["tables"], ma["tables"])
    assert sorted(mt["dirs"]) == sorted(ma["dirs"]), (mt["dirs"], ma["dirs"])
    assert all(mt["dirs"][k]["size"] == ma["dirs"][k]["size"] for k in ma["dirs"])
    # positive: a run that walks the model
    ra = _run(0, size_b)
    rows = check_run(ra, rel, ma)
    assert len(rows) == 5 and all(c["ok"] for c in rows), rows
    assert rows[2]["level"] == 5 and rows[2]["loaded"] == (0xA, size_b - 1)
    # negative 1: the parser stops short of the declared size
    rows = check_run(_run(0, size_b, parser_end=size_b - 3), rel, ma)
    assert [c["ok"] for c in rows] == [True, True, False, True, False], rows
    # negative 2: the run read another file layout (offsets not in the model)
    rows = check_run(_run(0x800, size_b), rel, ma)
    assert not rows[1]["ok"] and "no section table" in rows[1]["why"], rows[1]
    # negative 3: a failed read
    bad = _run(0, size_b)
    bad["rows"][2]["status"] = -1
    assert not check_run(bad, rel, ma)[2]["ok"]
    # compare: same layout -> SAME; moved layout walked the same way -> SAME-RELOCATED
    b = _synthetic(0x800)
    mb = model_lev3456(b)
    assert compare_runs(ra, ma, ra, ma, rel)[0] == "SAME"
    assert compare_runs(ra, ma, _run(0x800, size_b), mb, rel)[0] == "SAME-RELOCATED"
    # moved but read with the old offsets -> DIFFERENT (no model match)
    v, d = compare_runs(ra, ma, ra, mb, rel)
    assert v == "DIFFERENT" and d, d
    # same layout, short parse -> DIFFERENT
    assert compare_runs(ra, ma, _run(0, size_b, parser_end=size_b - 3), ma, rel)[0] == "DIFFERENT"
    # another file's read changed -> DIFFERENT
    rc = _run(0, size_b)
    rc["rows"][-1]["readers"][0]["bytes"] = 99
    assert compare_runs(ra, ma, rc, ma, rel)[0] == "DIFFERENT"
    print("selftest OK (11 checks)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("check", help="check one run's reads of a file against its model")
    p.add_argument("run")
    p.add_argument("--file", action="append", default=[], required=True, metavar="REL=PATH")
    p.add_argument("--json")
    p = sub.add_parser("compare", help="compare two runs relative to their files' models")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--file-a", required=True, metavar="REL=PATH")
    p.add_argument("--file-b", required=True, metavar="REL=PATH")
    p = sub.add_parser("changed", help="LEV3456R directories whose records differ between two files")
    p.add_argument("a")
    p.add_argument("b")
    args = ap.parse_args(argv)
    if args.cmd == "changed":
        return cmd_changed(args)
    if args.selftest:
        return selftest()
    if args.cmd == "check":
        return cmd_check(args)
    if args.cmd == "compare":
        return cmd_compare(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
