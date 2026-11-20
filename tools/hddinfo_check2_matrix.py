#!/usr/bin/env python3
"""Firmware check 2 (MapDBVer, ``0x51``) and router verdicts for every ``HDD_INFO`` variant (M2.19).

M2.4 ran check 1 (``fn 0x03bd2ad8``, error ``0x50``) on the 89 variants of
``tools/hddinfo_variants.py``.  This tool runs the rest of the gate on the same
corpus, EU2011 build B ``AppLaunch.dll``, in PySh4 through
``tools/mapcode_l3.py run_compare``:

1. **check 2 alone** - ``fn 0x03bd2ce4`` with a cold parse cache: two
   ``KernelIoControl(0x0101302C)`` calls read the unit bounds (record ``+112``
   min, ``+114`` max, u16 big-endian), the file is parsed into the 16-byte
   slots at ``0x01f74b30``, and line 3 (slot 2) chars 5, 6, 7 are turned into
   nibbles by ``fn 0x03bd2a40`` (``0-9a-fA-F``; anything else 0) and combined
   ``(n5 << 8) | (n6 << 4) | n7``; ``r0 = min <= value <= max``.  A failure
   logs ``MapDBVer : %d <= [%d] <= %d``.
2. **the router** ``fn 0x03bd2ecc(0)`` (partition 0): check 1, then check 2 on
   the cache check 1 filled, with the dispatcher ``fn 0x03bcafb8`` stubbed in
   two modes: ``return`` (every code the router raises is recorded and the
   router continues; the ProtoLevel / no-screen path) and ``halt`` (the run ends
   at the first code; the production path, C-5351).

Each firmware verdict is compared with ``tools/hddinfo.py classify`` (M2.15
model) given the same declared bounds: check 2 ``PASS`` / ``MAP DATA BASE
UNMATCH`` against check 2 ``ACCEPT`` / ``REJECT``; the router codes against
the model's ``failures`` list (``DIFFERENT MAP CODE`` = ``0x50``, ``MAP DATA
BASE UNMATCH`` = ``0x51``; ``halt`` keeps only the first).

The unit bounds are **declared inputs**, not measurements (they come from a
kernel IOCTL answer that is not in the image).  Several pairs can be given;
each is a separate matrix.

Controls per bounds pair: the factory file must pass check 2 when the bounds
contain its value and fail it with ``min = value + 1``; with no file served,
check 2 sees MapDBVer 0 (the slot is zero), so it must fail iff ``min > 0``,
and the router must raise ``0x50`` first.

Exit codes: 0 all rows agree and the controls hold, 1 a disagreement or failed
control, 3 missing input, 4 BLOCKED.

Usage::

  hddinfo_check2_matrix.py --selftest
  hddinfo_check2_matrix.py run IMG256 FACTORY_HDD_INFO.TXT VARIANT_DIR \\
      --bounds 0x010:0x010 --bounds 0x001:0x0ff [--tsv OUT] [--json]

No vendor bytes go to the repo; ``--tsv`` (names, verdicts, the 3 MapDBVer
chars the firmware logged) belongs in scratch.

Method and results: docs/experiments/EXP-2026-11-20-M2.19-check2-router-l3.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import hddinfo  # noqa: E402

CODE = {hddinfo.CHECK1_CODE: "0x50", hddinfo.CHECK2_CODE: "0x51"}


def parse_bounds(text: str) -> tuple[int, int]:
    lo, hi = text.split(":")
    return int(lo, 0), int(hi, 0)


def model_row(factory: bytes, variant: bytes, bounds: tuple[int, int]) -> dict:
    try:
        rec = hddinfo.HddInfo.parse(variant)
    except ValueError:
        return {"check2": "PARSE_ERROR", "value": None, "codes": None}
    res = hddinfo.classify(hddinfo.HddInfo.parse(factory), rec,
                           mapdbver_min=bounds[0], mapdbver_max=bounds[1])
    c2 = res["check2_map_data_base_unmatch"]
    return {"check2": "ACCEPT" if c2["verdict"] == "PASS" else "REJECT",
            "value": c2["mapdbver"]["value"],
            "codes": [CODE[f] for f in res["failures"]]}


def fw_value(result: dict) -> int | None:
    """MapDBVer the firmware logged (only on a check-2 failure)."""
    for s in result.get("stub_log", []):
        t = s.get("text", "")
        if s["stub"] == "NKDbgPrintfW" and t.startswith("MapDBVer"):
            return int(t.split("[", 1)[1].split("]", 1)[0])
    return None


def build_matrix(factory: bytes, variants, bounds, fw_check2, fw_router) -> dict:
    """*fw_check2(card, bounds)* -> result dict of ``fn 0x03bd2ce4``;
    *fw_router(card, bounds, mode)* -> result dict of ``fn 0x03bd2ecc(0)``.
    Real runs bind ``mapcode_l3.run_compare``; the self-test binds host fakes."""
    rows = []
    for name, raw in variants:
        m = model_row(factory, raw, bounds)
        c2 = fw_check2(raw, bounds)
        rr = fw_router(raw, bounds, "return")
        rh = fw_router(raw, bounds, "halt")
        model_halt = (m["codes"] or [])[:1]
        row = {
            "file": name,
            "model_value": m["value"],
            "fw_value_logged": fw_value(c2),
            "fw_check2": c2["verdict"],
            "model_check2": m["check2"],
            "fw_router_return": rr["dispatched"],
            "fw_router_halt": rh["dispatched"],
            "model_codes": m["codes"],
            "slot2": c2.get("card_slot2", ""),
        }
        row["agree_check2"] = row["fw_check2"] == row["model_check2"]
        row["agree_router"] = (rr["dispatched"] == m["codes"] and rh["dispatched"] == model_halt)
        if row["fw_value_logged"] is not None and m["value"] is not None:
            row["agree_value"] = row["fw_value_logged"] == m["value"]
        rows.append(row)

    fac_val = model_row(factory, factory, bounds)["value"]
    lo, hi = bounds
    contains = lo <= fac_val <= hi
    ctl = {}
    c = fw_check2(factory, bounds)
    ctl["factory"] = {"fw": c["verdict"], "expect": "ACCEPT" if contains else "REJECT"}
    c = fw_check2(factory, (fac_val + 1, max(hi, fac_val + 1)))
    ctl["factory_min_above"] = {"fw": c["verdict"], "expect": "REJECT"}
    c = fw_check2(None, bounds)
    ctl["no_file_check2"] = {"fw": c["verdict"], "expect": "REJECT" if lo > 0 else "ACCEPT"}
    r = fw_router(None, bounds, "halt")
    ctl["no_file_router_halt"] = {"fw": r["dispatched"], "expect": ["0x50"]}
    for v in ctl.values():
        v["ok"] = v["fw"] == v["expect"]

    return {
        "bounds": {"min": lo, "max": hi},
        "variants": len(rows),
        "fw_check2": dict(Counter(r["fw_check2"] for r in rows)),
        "model_check2": dict(Counter(r["model_check2"] for r in rows)),
        "router_return": dict(Counter("+".join(r["fw_router_return"]) or "pass" for r in rows)),
        "router_halt": dict(Counter("+".join(r["fw_router_halt"]) or "pass" for r in rows)),
        "agree_check2": sum(r["agree_check2"] for r in rows),
        "agree_router": sum(r["agree_router"] for r in rows),
        "value_checked": sum("agree_value" in r for r in rows),
        "value_agree": sum(r.get("agree_value", False) for r in rows),
        "disagree": [r["file"] for r in rows
                     if not (r["agree_check2"] and r["agree_router"] and r.get("agree_value", True))],
        "controls": ctl,
        "rows": rows,
    }


def matrix_ok(m: dict) -> bool:
    return not m["disagree"] and all(c["ok"] for c in m["controls"].values())


def format_matrix(m: dict, all_rows: bool = False) -> str:
    b = m["bounds"]
    out = [f"bounds min=0x{b['min']:03x} max=0x{b['max']:03x}"]
    for r in m["rows"]:
        moved = r["model_value"] != 0x010 or r["fw_check2"] == "REJECT" or r["fw_router_return"]
        if not (all_rows or moved):
            continue
        out.append(f"  {r['file']:<38} value={r['model_value'] if r['model_value'] is None else hex(r['model_value']):<6}"
                   f" fw_log={r['fw_value_logged']!s:<4} c2 fw={r['fw_check2']:<6} model={r['model_check2']:<6}"
                   f" router ret={'+'.join(r['fw_router_return']) or 'pass':<9}"
                   f" halt={'+'.join(r['fw_router_halt']) or 'pass':<5}"
                   f" model={'+'.join(r['model_codes'] or []) or 'pass':<9}"
                   f" {'ok' if r['file'] not in m['disagree'] else 'DIFF'} slot2={r['slot2']!r}")
    out.append(f"  variants {m['variants']}  check2 fw {m['fw_check2']} model {m['model_check2']}")
    out.append(f"  router return {m['router_return']}  halt {m['router_halt']}")
    out.append(f"  agree check2 {m['agree_check2']}/{m['variants']}  router {m['agree_router']}/{m['variants']}"
               f"  logged value {m['value_agree']}/{m['value_checked']}  disagree {m['disagree'] or 'none'}")
    for k, c in m["controls"].items():
        out.append(f"  control {k:<20} fw={c['fw']} expect={c['expect']} {'ok' if c['ok'] else 'FAIL'}")
    return "\n".join(out)


def cmd_run(args) -> int:
    for path in (args.image, args.factory, args.variant_dir):
        if not Path(path).exists():
            print(f"missing input: {path}", file=sys.stderr)
            return 3
    import mapcode_l3
    factory = Path(args.factory).read_bytes()
    unit = mapcode_l3.unit_code_from(Path(args.unit_from).read_bytes() if args.unit_from else factory)
    variants = [(p.name, p.read_bytes()) for p in sorted(Path(args.variant_dir).glob("*.HDD_INFO.TXT"))]
    if not variants:
        print(f"no *.HDD_INFO.TXT in {args.variant_dir}", file=sys.stderr)
        return 3
    with open(args.image, "rb") as fh:
        image = fh.read(128 << 20)
    pairs = [parse_bounds(b) for b in (args.bounds or ["0x010:0x010"])]
    try:
        thunks = mapcode_l3.resolve_thunks(image)

        def c2(card, bounds):
            return mapcode_l3.run_compare(image, card, unit, fn=mapcode_l3.FN_CHECK2,
                                          thunks=thunks, bounds=bounds)

        def router(card, bounds, mode):
            return mapcode_l3.run_compare(image, card, unit, fn=mapcode_l3.FN_ROUTER,
                                          thunks=thunks, bounds=bounds, args=(0,), dispatch=mode)

        mats = [build_matrix(factory, variants, b, c2, router) for b in pairs]
    except mapcode_l3.Blocked as exc:
        print(f"BLOCKED: {exc}")
        return 4
    if args.tsv:
        with open(args.tsv, "w", encoding="utf-8") as fh:
            fh.write("bounds\tfile\tmodel_value\tfw_logged\tfw_check2\tmodel_check2\t"
                     "router_return\trouter_halt\tmodel_codes\tslot2\n")
            for m in mats:
                for r in m["rows"]:
                    fh.write(f"{m['bounds']['min']}:{m['bounds']['max']}\t{r['file']}\t{r['model_value']}\t"
                             f"{r['fw_value_logged']}\t{r['fw_check2']}\t{r['model_check2']}\t"
                             f"{'+'.join(r['fw_router_return'])}\t{'+'.join(r['fw_router_halt'])}\t"
                             f"{'+'.join(r['model_codes'] or [])}\t{r['slot2']!r}\n")
    if args.json:
        print(json.dumps(mats, indent=1))
    else:
        print(f"firmware {mapcode_l3.MODULE} {mapcode_l3.BUILD} check 2 fn 0x{mapcode_l3.FN_CHECK2:08x},"
              f" router fn 0x{mapcode_l3.FN_ROUTER:08x}(0); unit +0x60={unit.decode('latin-1')!r} (declared)")
        for m in mats:
            print(format_matrix(m, args.all))
    return 0 if all(matrix_ok(m) for m in mats) else 1


# ---------------------------------------------------------------------------
# self-test


def selftest() -> int:
    failures = 0

    def check(name, cond, detail=""):
        nonlocal failures
        print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  {detail}"))
        failures += 0 if cond else 1

    factory = b"\r\n".join([b"ABC-000-111", b"ABC-000-222", b"02-110100-00",
                            b"XXX00-YYYYY", b"00-00", b"000000000000"])
    unit = factory[:11]
    parts = factory.split(b"\r\n")

    def value_of(card):
        if card is None:
            return 0
        line3 = (card.split(b"\r\n") + [b""] * 3)[2][:15] + b"\x00" * 8
        nib = [hddinfo._conv_nibble(line3[p]) for p in (5, 6, 7)]
        return (nib[0] << 8) | (nib[1] << 4) | nib[2]

    def l1_ok(card):
        return card is not None and (card.split(b"\r\n")[0][:15] + b"\x00" * 11)[:11] == unit

    def fw_c2(card, bounds, offset=0):
        v = value_of(card) + offset
        ok = bounds[0] <= v <= bounds[1]
        log = [] if ok else [{"stub": "NKDbgPrintfW", "text": f"MapDBVer : {bounds[0]} <= [{v}] <= {bounds[1]}"}]
        return {"verdict": "ACCEPT" if ok else "REJECT", "stub_log": log, "card_slot2": ""}

    def fw_router(card, bounds, mode):
        codes = []
        if not l1_ok(card):
            codes.append("0x50")
            if mode == "halt":
                return {"dispatched": codes}
        if fw_c2(card, bounds)["verdict"] == "REJECT":
            codes.append("0x51")
        return {"dispatched": codes}

    v_l3 = b"\r\n".join(parts[:2] + [b"02-115100-00"] + parts[3:])     # value 0x510
    v_l1 = b"\r\n".join([b"ABC-000-112"] + parts[1:])
    v_both = b"\r\n".join([b"ABC-000-112", parts[1], b"02-115100-00"] + parts[3:])
    variants = [("l3", v_l3), ("l1", v_l1), ("both", v_both)]
    m = build_matrix(factory, variants, (0x010, 0x010), fw_c2, fw_router)
    check("factory MapDBVer is 0x010", model_row(factory, factory, (0, 0))["value"] == 0x010)
    check("check 2: l3 edit REJECT, l1 edit ACCEPT, both REJECT",
          [r["fw_check2"] for r in m["rows"]] == ["REJECT", "ACCEPT", "REJECT"], m["rows"])
    check("router return: 0x51 / 0x50 / 0x50+0x51",
          [r["fw_router_return"] for r in m["rows"]] == [["0x51"], ["0x50"], ["0x50", "0x51"]])
    check("router halt keeps only the first code",
          [r["fw_router_halt"] for r in m["rows"]] == [["0x51"], ["0x50"], ["0x50"]])
    check("model agrees on all rows and the logged value", matrix_ok(m) and m["value_agree"] == 2, m)
    wide = build_matrix(factory, variants, (0x001, 0xfff), fw_c2, fw_router)
    check("wide bounds: every check 2 passes, controls still hold",
          wide["fw_check2"] == {"ACCEPT": 3} and matrix_ok(wide), wide["controls"])
    zero = build_matrix(factory, [], (0x000, 0x010), fw_c2, fw_router)
    check("min 0: the no-file control expects ACCEPT (value 0 in range)",
          zero["controls"]["no_file_check2"]["expect"] == "ACCEPT" and matrix_ok(zero))
    bad = build_matrix(factory, variants, (0x010, 0x010),
                       lambda c, b: fw_c2(c, b, offset=1), fw_router)
    check("negative: an off-by-one firmware value is caught (disagree + factory control)",
          not matrix_ok(bad) and not bad["controls"]["factory"]["ok"])

    def router_no_chain(card, bounds, mode):  # a router that skips check 2 after 0x50
        r = fw_router(card, bounds, "halt")
        return r if r["dispatched"] else fw_router(card, bounds, mode)

    nc = build_matrix(factory, variants, (0x010, 0x010), fw_c2, router_no_chain)
    check("negative: a router that never raises 0x51 after 0x50 disagrees on 'both'",
          nc["disagree"] == ["both"], nc["disagree"])
    check("bounds parser", parse_bounds("0x010:0x0ff") == (16, 255))
    print("selftest: " + ("OK" if not failures else f"{failures} FAILED"))
    return 1 if failures else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("run", help="firmware check 2 and router vs model for every variant")
    p.add_argument("image")
    p.add_argument("factory")
    p.add_argument("variant_dir")
    p.add_argument("--bounds", action="append", help="MIN:MAX declared unit bounds (repeatable)")
    p.add_argument("--unit-from", help="file whose line 1 bytes 0..10 are the unit +0x60 (default: factory)")
    p.add_argument("--tsv")
    p.add_argument("--json", action="store_true")
    p.add_argument("--all", action="store_true", help="print every row, not only rows that move")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "run":
        return cmd_run(args)
    ap.print_help()
    return 3


if __name__ == "__main__":
    sys.exit(main())
