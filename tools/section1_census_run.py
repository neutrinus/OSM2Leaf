#!/usr/bin/env python3
"""Replay the six M4.79–M4.84 section-1 field decoders on real 2011 cards.

Each of ``zcode_decode.py``, ``icode_decode.py``, ``inter_decode.py``,
``frway_decode.py``, ``icadm_decode.py`` and ``zipfr_decode.py`` has a
``census ROOT`` mode, but a green ``--selftest`` only proves the grammar on a
synthetic vector.  This tool runs every census on a real EU2011 or US2011
factory tree, parses the headline counters from each tool's own stdout (no
grammar is re-derived here), and reports one line per decoder.  A shard that is
present but explains 0 bytes is a FAIL, never silently accepted as "absent".

Usage::

    python3 tools/section1_census_run.py --tree ROOT --card eu2011
    python3 tools/section1_census_run.py --tree ROOT --card us2011 --json OUT
    python3 tools/section1_census_run.py --selftest

Only the standard library is used.  No vendor bytes enter the repository.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent

CARD_EU = "eu2011"
CARD_US = "us2011"
CARDS = (CARD_EU, CARD_US)

# Which argparse root each decoder expects: some walk ROOT/REFER001 themselves,
# zcode's resolve_root() uses root.iterdir() directly and needs REFER001 passed.
# Each entry: (argv tail builder, parser key).
DECODERS = ("zcode", "icode", "inter", "frway", "icadm", "zipfr")

# Status values.
OK = "ok"
ABSENT = "absent"
FAIL = "fail"


def census_argv(decoder: str, root: Path, card: str, json_path: Path | None) -> list[str]:
    """Build the subprocess argv for one decoder's census on ROOT."""
    script = TOOLS_DIR / f"{decoder}_decode.py"
    base = [sys.executable, str(script), "census"]
    if decoder == "zcode":
        target = root / "REFER001" if (root / "REFER001").is_dir() else root
        return base + [str(target)]
    if decoder == "inter":
        argv = base + [str(root), "--labels", "EU" if card == CARD_EU else "US"]
        if json_path is not None:
            argv += ["--json", str(json_path)]
        return argv
    if decoder == "frway":
        argv = base + [str(root)]
        if json_path is not None:
            argv += ["--json", str(json_path)]
        return argv
    if decoder == "zipfr":
        argv = base + [str(root)]
        if json_path is not None:
            argv += ["--json", str(json_path)]
        return argv
    # icode, icadm accept ROOT (or a file for icadm) directly.
    return base + [str(root)]


# ---------------------------------------------------------------------------
# Stable headline parsers.  Each returns a dict of counters or raises
# ValueError when a required line is missing/garbled.  Anchors are quoted
# from the producing tool's own print statements, never from a line number.
# ---------------------------------------------------------------------------

ZCODE_LINE = re.compile(
    r"^(?P<shard>\S+): form (?P<form>[AB]) size (?P<size>\d+) "
    r"records (?P<records>\d+) record_base 0x[0-9a-f]+ "
    r"explained (?P<explained>\d+)/(?P<total>\d+)"
)


def parse_zcode(text: str) -> dict[str, Any]:
    rows = []
    for line in text.splitlines():
        m = ZCODE_LINE.match(line)
        if m:
            rows.append({
                "shard": m.group("shard"),
                "form": m.group("form"),
                "size": int(m.group("size")),
                "records": int(m.group("records")),
                "explained": int(m.group("explained")),
                "total": int(m.group("total")),
            })
    if not rows:
        raise ValueError("no 'shard: form [AB] size ... explained x/y' line")
    return {
        "shards": len(rows),
        "records": sum(r["records"] for r in rows),
        "size": sum(r["size"] for r in rows),
        "explained": sum(r["explained"] for r in rows),
        "pct": round(100.0 * sum(r["explained"] for r in rows)
                     / max(sum(r["size"] for r in rows), 1), 3),
        "zero_explained": [r["shard"] for r in rows if r["explained"] == 0],
        "per_shard": rows,
    }


ICODE_EXPL = re.compile(r"^bytes explained: (\d+) / (\d+) = ([\d.]+)%", re.M)
ICODE_REC = re.compile(r"^records: rows=(\d+)", re.M)


def parse_icode(text: str) -> dict[str, Any]:
    m = ICODE_EXPL.search(text)
    if not m:
        raise ValueError("no 'bytes explained: x / y = z%' line")
    rec = ICODE_REC.search(text)
    if not rec:
        raise ValueError("no 'records: rows=' line")
    explained, size = int(m.group(1)), int(m.group(2))
    return {
        "shards": 1,
        "records": int(rec.group(1)),
        "size": size,
        "explained": explained,
        "pct": float(m.group(3)),
        "zero_explained": [] if explained else ["ICODE001"],
    }


def _num(s: str) -> int:
    return int(s.replace(",", ""))


INTER_TOTAL = re.compile(
    r"^  TOTAL (\w+): (\d+) shards, ([\d,]+) records, ([\d,]+) B", re.M
)
INTER_EXPL = re.compile(r"^    explained=([\d,]+)/([\d,]+) B = ([\d.]+)%", re.M)


def parse_inter(text: str, card: str) -> dict[str, Any]:
    label = "EU" if card == CARD_EU else "US"
    totals = [(m.group(1), m) for m in INTER_TOTAL.finditer(text)]
    exps = list(INTER_EXPL.finditer(text))
    if not any(lab == label for lab, _ in totals):
        raise ValueError(f"no 'TOTAL {label}:' line")
    tm = dict(totals)[label]
    # The runner always invokes `census ROOT --labels EU|US` with a single
    # root, so the card's explained line is the one that follows its TOTAL
    # line.  If a two-root census printed both, select by label order.
    if len(exps) == 1:
        em = exps[0]
    else:
        idx = 0 if label == "EU" else 1
        em = exps[idx]
    return {
        "shards": int(tm.group(2)),
        "records": _num(tm.group(3)),
        "size": _num(tm.group(4)),
        "explained": _num(em.group(1)),
        "pct": float(em.group(3)),
        "zero_explained": [],  # per-shard zeros would be visible in the JSON report
    }


FRWAY_BYTES = re.compile(
    r"^bytes: (\d+) of (\d+) explained \(([\d.]+)%\)", re.M
)
FRWAY_PRESENT = re.compile(r"^shards present: (\d+) of (\d+)", re.M)


def parse_frway(text: str) -> dict[str, Any]:
    m = FRWAY_BYTES.search(text)
    if not m:
        raise ValueError("no 'bytes: x of y explained (z%)' line")
    p = FRWAY_PRESENT.search(text)
    shards = int(p.group(1)) if p else 0
    explained, size = int(m.group(1)), int(m.group(2))
    return {
        "shards": shards,
        "records": 0,  # frway prints record counts per shard, not one total here
        "size": size,
        "explained": explained,
        "pct": float(m.group(3)),
        "zero_explained": [],  # per-shard detail is in the JSON report
    }


ICADM_TOTAL = re.compile(
    r"^  CARD TOTAL: shards=(\d+) size=([\d,]+) B "
    r"records=([\d,]+) explained=([\d,]+) B = ([\d.]+)%", re.M
)


def parse_icadm(text: str) -> dict[str, Any]:
    m = ICADM_TOTAL.search(text)
    if not m:
        raise ValueError("no 'CARD TOTAL: shards=... explained=...' line")
    return {
        "shards": int(m.group(1)),
        "size": _num(m.group(2)),
        "records": _num(m.group(3)),
        "explained": _num(m.group(4)),
        "pct": float(m.group(5)),
        "zero_explained": [],  # per-shard detail is in the JSON stream
    }


ZIPFR_EXPL = re.compile(r"^  bytes explained (\d+)/(\d+) = ([\d.]+) %", re.M)
ZIPFR_REC = re.compile(r"^  records (\d+) x (\d+) B", re.M)


def parse_zipfr(text: str) -> dict[str, Any]:
    m = ZIPFR_EXPL.search(text)
    if not m:
        raise ValueError("no 'bytes explained x/y = z %' line")
    rec = ZIPFR_REC.search(text)
    explained, size = int(m.group(1)), int(m.group(2))
    return {
        "shards": 1,
        "records": int(rec.group(1)) if rec else 0,
        "size": size,
        "explained": explained,
        "pct": float(m.group(3)),
        "zero_explained": [] if explained else ["ZIPFR001"],
    }


PARSERS = {
    "zcode": parse_zcode,
    "icode": parse_icode,
    "inter": parse_inter,
    "frway": parse_frway,
    "icadm": parse_icadm,
    "zipfr": parse_zipfr,
}

# A decoder reports "absent" with one of these exact strings and exit 2.
ABSENT_MARKERS = {
    "zcode": "no ZCODE0nn.DAT[.cmp] files under",
    "icode": "no REFER001/ICODE001.DAT under",
    "inter": "no INTER shards under",
    "frway": "no FRWAY0nn.DAT under",
    "icadm": "no ICADM0nn shards under",
    "zipfr": "no ZIPFR001 .cmp/.ind pair under",
}


def run_one(decoder: str, root: Path, card: str, json_dir: Path | None) -> dict[str, Any]:
    """Run one decoder's census and classify its result."""
    json_path = None
    if json_dir is not None and decoder in ("inter", "frway", "zipfr"):
        json_dir.mkdir(parents=True, exist_ok=True)
        json_path = json_dir / f"{decoder}-{card}.json"
    argv = census_argv(decoder, root, card, json_path)
    try:
        proc = subprocess.run(
            argv, cwd=str(TOOLS_DIR.parent), capture_output=True, text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return {"decoder": decoder, "status": FAIL, "detail": "timeout after 600s"}
    out = (proc.stdout or "") + (proc.stderr or "")
    marker = ABSENT_MARKERS[decoder]
    if proc.returncode != 0 and marker in out:
        return {"decoder": decoder, "status": ABSENT, "detail": marker}
    if proc.returncode != 0:
        return {"decoder": decoder, "status": FAIL,
                "detail": f"exit {proc.returncode}: {out.strip()[:200]}"}
    parser = PARSERS[decoder]
    try:
        stats = parse_inter(out, card) if decoder == "inter" else parser(out)
    except ValueError as exc:
        return {"decoder": decoder, "status": FAIL, "detail": str(exc)}
    zeros = stats.get("zero_explained") or []
    if zeros:
        return {"decoder": decoder, "status": FAIL,
                "detail": f"0 bytes explained on present shard(s): {', '.join(zeros)}",
                "stats": stats}
    if stats["explained"] <= 0:
        return {"decoder": decoder, "status": FAIL,
                "detail": "present shards but 0 bytes explained overall", "stats": stats}
    return {"decoder": decoder, "status": OK, "stats": stats}


def replay(root: Path, card: str, json_dir: Path | None) -> dict[str, Any]:
    results = [run_one(d, root, card, json_dir) for d in DECODERS]
    rows = []
    for r in results:
        if r["status"] == OK:
            s = r["stats"]
            rows.append({
                "decoder": r["decoder"], "status": OK,
                "shards": s["shards"], "records": s["records"],
                "size": s["size"], "explained": s["explained"],
                "pct": s["pct"],
            })
        else:
            rows.append({"decoder": r["decoder"], "status": r["status"],
                         "detail": r["detail"]})
    failed = [r for r in rows if r["status"] == FAIL]
    return {
        "card": card,
        "tree": str(root),
        "rows": rows,
        "ok": not failed,
    }


def print_report(report: dict[str, Any]) -> None:
    print(f"card: {report['card']}  tree: {report['tree']}")
    print(f"{'decoder':<8} {'status':<7} {'shards':>7} {'records':>10} "
          f"{'size':>13} {'explained':>13} {'pct':>7}")
    for r in report["rows"]:
        if r["status"] == OK:
            print(f"{r['decoder']:<8} {r['status']:<7} {r['shards']:>7} "
                  f"{r['records']:>10,} {r['size']:>13,} {r['explained']:>13,} "
                  f"{r['pct']:>6.2f}%")
        else:
            print(f"{r['decoder']:<8} {r['status']:<7} {'':>7} {'':>10} "
                  f"{'':>13} {'':>13}  {r['detail']}")
    print("section1_census_run: " + ("PASS" if report["ok"] else "FAIL"))


# ---------------------------------------------------------------------------
# Synthetic self-test — no vendor data.
# ---------------------------------------------------------------------------

def selftest() -> int:
    fails: list[str] = []

    def check(cond: bool, msg: str) -> None:
        print(("ok: " if cond else "FAIL: ") + msg)
        if not cond:
            fails.append(msg)

    ztext = (
        "ZCODE001: form B size 5376 records 7 record_base 0x1400 "
        "explained 4836/5376 (90.0 %)\n"
        "    checks trie_fits=ok\n"
        "ZCODE002: form A size 79616 records 2808 record_base 0x8700 "
        "explained 75268/79616 (94.5 %)\n"
        "    checks trie_fits=ok\n"
    )
    z = parse_zcode(ztext)
    check(z["shards"] == 2, "zcode parses 2 shards")
    check(z["explained"] == 4836 + 75268, "zcode sums explained bytes")
    check(z["size"] == 5376 + 79616, "zcode sums sizes")

    itext = (
        "records: rows=275766 (named 267544, redirect 8222), chains=8018\n"
        "bytes explained: 6059118 / 6071808 = 99.791%\n"
    )
    i = parse_icode(itext)
    check(i["explained"] == 6059118 and i["size"] == 6071808,
          "icode parses explained/size")
    check(i["records"] == 275766, "icode parses records")

    intertext = (
        "  TOTAL EU: 33 shards, 976 records, 303,629,312 B\n"
        "    explained=265,421,390/303,629,312 B = 87.416%\n"
        "  TOTAL US: 11 shards, 385 records, 225,175,552 B\n"
        "    explained=201,519,564/225,175,552 B = 89.494%\n"
    )
    ie = parse_inter(intertext, CARD_EU)
    iu = parse_inter(intertext, CARD_US)
    check(ie["explained"] == 265421390, "inter parses EU explained")
    check(iu["explained"] == 201519564, "inter parses US explained")

    ftext = (
        "shards present: 26 of 33 (missing 001,006,013,014,017,024,032)\n"
        "bytes: 2908874 of 2921728 explained (99.56%)\n"
    )
    f = parse_frway(ftext)
    check(f["explained"] == 2908874 and f["shards"] == 26,
          "frway parses explained and shard count")

    itext2 = (
        "  CARD TOTAL: shards=33 size=113,561,600 B records=4,664,115 "
        "explained=101,042,820 B = 88.98%\n"
    )
    ia = parse_icadm(itext2)
    check(ia["explained"] == 101042820 and ia["shards"] == 33,
          "icadm parses CARD TOTAL")

    ztext2 = (
        "  records 36881 x 14 B at 0x1008..0x7f0f6\n"
        "  bytes explained 520448/520448 = 100.0 % (unexplained 0)\n"
    )
    zf = parse_zipfr(ztext2)
    check(zf["explained"] == 520448 and zf["records"] == 36881,
          "zipfr parses explained and records")

    # Garbled / missing headline must fail, never silently pass.
    for name, fn, text in (
        ("zcode", parse_zcode, "no headline here\n"),
        ("icode", parse_icode, "bytes explained: BAD\n"),
        ("frway", parse_frway, "shards present: 1 of 33\n"),
        ("icadm", parse_icadm, "CARD TOTAL: broken\n"),
        ("zipfr", parse_zipfr, "bytes explained nope\n"),
    ):
        try:
            fn(text)  # type: ignore[arg-type]
        except ValueError:
            check(True, f"{name} refuses garbled headline")
        else:
            check(False, f"{name} refuses garbled headline")

    # A present shard reporting 0 bytes explained must be a FAIL classification,
    # not swallowed as ABSENT (CHANGE 2).
    zero = (
        "ZCODE001: form B size 5376 records 7 record_base 0x1400 "
        "explained 0/5376 (0.0 %)\n"
    )
    zz = parse_zcode(zero)
    check(zz["zero_explained"] == ["ZCODE001"],
          "a present shard with 0 explained is flagged, not absorbed")
    # The ABSENT signature is distinct from a zero-explained present shard.
    check(ABSENT_MARKERS["zcode"] not in zero,
          "ABSENT marker is not present in a zero-explained census")
    print("section1_census_run selftest: " + ("OK" if not fails else f"FAIL ({len(fails)})"))
    return 1 if fails else 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true",
                    help="run synthetic parser/status self-test")
    ap.add_argument("--tree", type=Path, help="factory card tree (ROOT)")
    ap.add_argument("--card", choices=CARDS, help="card label")
    ap.add_argument("--json", dest="json_path", type=Path,
                    help="write machine-readable report to this path")
    ap.add_argument("--json-dir", type=Path,
                    help="directory for per-decoder JSON reports (inter/frway/zipfr)")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.tree is None or args.card is None:
        ap.print_help()
        return 2
    if not args.tree.is_dir():
        print(f"error: {args.tree} is not a directory", file=sys.stderr)
        return 2
    report = replay(args.tree, args.card, args.json_dir)
    print_report(report)
    if args.json_path is not None:
        args.json_path.write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
