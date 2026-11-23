#!/usr/bin/env python3
"""Firmware check-1 verdict for every ``HDD_INFO.TXT`` variant vs the model (M2.4).

For each ``*.HDD_INFO.TXT`` in a variant directory (``tools/hddinfo_variants.py``,
89 files for the EU 2011 factory file) this tool

1. runs the firmware's own map-code compare, ``AppLaunch.dll`` ``fn 0x03bd2ad8``
   (EU2011 build B, ``--image-start 0x3e00200``), in PySh4 through
   ``tools/mapcode_l3.py run_compare`` (the M9.6 target
   ``applaunch_mapcode_compare``), with the variant served at
   ``\\SystemSD\\VER_INFO\\HDD_INFO.TXT`` and the unit record ``+0x60`` declared
   as line 1 bytes 0..10 of the factory file (``--unit-from``);
2. evaluates ``tools/hddinfo.py classify`` check 1 (M2.15 model) with the
   factory file as ``sys``;
3. compares the two and prints one row per variant plus the 2x2 count.

The firmware verdict is ``ACCEPT`` (``r0=1``) or ``REJECT`` (``r0=0``); the model
verdict ``PASS`` maps to ``ACCEPT`` and ``DIFFERENT MAP CODE`` to ``REJECT``.  Only
check 1 (error ``0x50``) is run; check 2 (``0x51``, ``fn 0x03bd2ce4``) needs the
unit bounds ``+112/+114`` and is not part of this target.

Two controls are added to every run: the factory file itself (must be
``ACCEPT``) and the no-file branch (``CreateFileW`` fails, must be ``REJECT``).

Exit codes: 0 every variant agrees and both controls hold, 1 at least one
disagreement or a failed control, 3 missing input, 4 BLOCKED (the engine stopped
on something the harness does not model).

Usage::

  hddinfo_fw_matrix.py --selftest
  hddinfo_fw_matrix.py run IMG256 FACTORY_HDD_INFO.TXT VARIANT_DIR [--tsv OUT] [--json]

No vendor bytes are written except to ``--tsv`` (variant names, verdicts and
the 11-byte slot-0 text the firmware logged), which belongs in scratch, not in
the repo.

Method and results: docs/experiments/EXP-2026-11-19-M2.4-hddinfo-fw-verdicts.md
"""

from __future__ import annotations

import argparse
import hashlib
import hashutil
import json
import os
import sys
from collections import Counter
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import hddinfo  # noqa: E402

MODEL_TO_FW = {"PASS": "ACCEPT", hddinfo.CHECK1_CODE: "REJECT"}


_sha = hashutil.sha256_bytes


def load_variants(var_dir: Path) -> list[tuple[str, bytes]]:
    return [(p.name, p.read_bytes()) for p in sorted(var_dir.glob("*.HDD_INFO.TXT"))]


def model_check1(factory: bytes, variant: bytes) -> str:
    """M2.15 model check 1 for *variant* against the factory line 1."""
    try:
        record = hddinfo.HddInfo.parse(variant)
    except ValueError:
        return "PARSE_ERROR"
    result = hddinfo.classify(hddinfo.HddInfo.parse(factory), record)
    return result["check1_different_map_code"]["verdict"]


def firmware_log(result: dict) -> str:
    texts = [s.get("text", "") for s in result.get("stub_log", []) if s["stub"] == "NKDbgPrintfW"]
    return " | ".join(t.strip() for t in texts)


def build_matrix(factory: bytes, variants: list[tuple[str, bytes]], fw) -> dict:
    """Run *fw(card_or_None) -> result dict* on each variant and the controls.

    *fw* is ``mapcode_l3.run_compare`` bound to the image and unit code in real
    runs, and a host function in the self-test.  ``Blocked`` from *fw*
    propagates.
    """
    base = hddinfo.HddInfo.parse(factory)
    rows = []
    for name, raw in variants:
        res = fw(raw)
        model = model_check1(factory, raw)
        try:
            line, edit = hddinfo.describe_change(base, hddinfo.HddInfo.parse(raw))
        except ValueError:
            line, edit = 0, "unparsed"
        model_fw = MODEL_TO_FW.get(model, model)
        rows.append({
            "file": name,
            "sha256": _sha(raw),
            "line": line,
            "edit_kind": "permutation" if edit == "permutation of lines" else f"line {line}",
            "fw_r0": res["r0"],
            "fw": res["verdict"],
            "fw_slot0": res["card_slot0"],
            "fw_log": firmware_log(res),
            "insns": res.get("insns"),
            "model": model,
            "agree": model_fw == res["verdict"],
        })
    factory_res = fw(factory)
    nofile_res = fw(None)
    controls = {
        "factory": {"fw": factory_res["verdict"], "expect": "ACCEPT",
                    "ok": factory_res["verdict"] == "ACCEPT"},
        "no_file": {"fw": nofile_res["verdict"], "expect": "REJECT",
                    "ok": nofile_res["verdict"] == "REJECT", "log": firmware_log(nofile_res)},
    }
    pairs = Counter((r["fw"], MODEL_TO_FW.get(r["model"], r["model"])) for r in rows)
    return {
        "factory_sha256": _sha(factory),
        "variants": len(rows),
        "fw_counts": dict(Counter(r["fw"] for r in rows)),
        "model_counts": dict(Counter(r["model"] for r in rows)),
        "confusion": {f"fw={a} model={b}": n for (a, b), n in sorted(pairs.items())},
        "agree": sum(r["agree"] for r in rows),
        "disagree": [r["file"] for r in rows if not r["agree"]],
        "controls": controls,
        "rows": rows,
    }


def format_matrix(m: dict) -> str:
    out = [f"{'file':<46} {'edit':<11} {'fw':<6} r0 {'model':<18} agree slot0"]
    for r in m["rows"]:
        out.append(f"{r['file']:<46} {r['edit_kind']:<11} {r['fw']:<6} {r['fw_r0']:<2} "
                   f"{r['model']:<18} {'yes' if r['agree'] else 'NO ':<5} {r['fw_slot0']!r}")
    out.append("")
    out.append(f"variants {m['variants']}  firmware {m['fw_counts']}  model {m['model_counts']}")
    for k, n in m["confusion"].items():
        out.append(f"  {k:<36} {n:3d}")
    out.append(f"agree {m['agree']}/{m['variants']}  disagree {m['disagree'] or 'none'}")
    for k, c in m["controls"].items():
        out.append(f"control {k:<8} fw={c['fw']} expect={c['expect']} {'ok' if c['ok'] else 'FAIL'}")
    return "\n".join(out)


def matrix_ok(m: dict) -> bool:
    return not m["disagree"] and all(c["ok"] for c in m["controls"].values())


def edge_probes(factory: bytes) -> list[tuple[str, bytes]]:
    """Inputs outside the length-preserving corpus, where the firmware parser
    (16-byte slots, 15 chars max, ``ReadFile`` of at most ``0x60`` bytes) and
    the model (whole stripped line, first 11 bytes) could differ."""
    lines = factory.split(b"\r\n")
    l1, rest = lines[0], lines[1:]

    def join(first, others=rest, sep=b"\r\n"):
        return sep.join([first] + list(others))

    return [
        ("edge_l1_suffix12.HDD_INFO.TXT", join(l1 + b"X")),
        ("edge_l1_long21.HDD_INFO.TXT", join(l1 + b"-ABCDEFGHI")),
        ("edge_l1_lower.HDD_INFO.TXT", join(l1.lower())),
        ("edge_l1_lead_space.HDD_INFO.TXT", join(b" " + l1)),
        ("edge_l1_trail_space.HDD_INFO.TXT", join(l1 + b" ")),
        ("edge_l1_empty.HDD_INFO.TXT", join(b"")),
        ("edge_lf_only.HDD_INFO.TXT", join(l1, sep=b"\n")),
        ("edge_utf8_bom.HDD_INFO.TXT", b"\xef\xbb\xbf" + factory),
        ("edge_line1_only.HDD_INFO.TXT", l1),
        ("edge_over_0x60.HDD_INFO.TXT", join(l1, rest[:-1] + [rest[-1] + b"0" * 40])),
    ]


def cmd_edges(args) -> int:
    if not Path(args.factory).exists():
        print(f"missing input: {args.factory}", file=sys.stderr)
        return 3
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    probes = edge_probes(Path(args.factory).read_bytes())
    for name, blob in probes:
        (out / name).write_bytes(blob)
        print(f"{name:<36} {len(blob):3d} B sha256 {_sha(blob)}")
    print(f"wrote {len(probes)} edge probes to {out}")
    return 0


def cmd_run(args) -> int:
    for path in (args.image, args.factory, args.variant_dir):
        if not Path(path).exists():
            print(f"missing input: {path}", file=sys.stderr)
            return 3
    import mapcode_l3
    factory = Path(args.factory).read_bytes()
    unit_src = Path(args.unit_from).read_bytes() if args.unit_from else factory
    unit = mapcode_l3.unit_code_from(unit_src)
    variants = load_variants(Path(args.variant_dir))
    if not variants:
        print(f"no *.HDD_INFO.TXT in {args.variant_dir}", file=sys.stderr)
        return 3
    with open(args.image, "rb") as fh:
        image = fh.read(128 << 20)
    try:
        thunks = mapcode_l3.resolve_thunks(image)
        m = build_matrix(factory, variants,
                         lambda card: mapcode_l3.run_compare(image, card, unit, thunks=thunks))
    except mapcode_l3.Blocked as exc:
        print(f"BLOCKED: {exc}")
        return 4
    m["unit_code"] = unit.decode("latin-1")
    m["unit_source"] = f"line 1 bytes 0..10 of {args.unit_from or args.factory} (declared, not read from a unit)"
    m["firmware"] = f"{mapcode_l3.MODULE} fn 0x{mapcode_l3.FN_COMPARE:08x} {mapcode_l3.BUILD}"
    if args.tsv:
        with open(args.tsv, "w", encoding="utf-8") as fh:
            fh.write("file\tsha256\tedit\tfw\tr0\tmodel\tagree\tslot0\tfw_log\n")
            for r in m["rows"]:
                fh.write(f"{r['file']}\t{r['sha256']}\t{r['edit_kind']}\t{r['fw']}\t{r['fw_r0']}\t"
                         f"{r['model']}\t{r['agree']}\t{r['fw_slot0']!r}\t{r['fw_log']}\n")
    if args.json:
        print(json.dumps(m, indent=1))
    else:
        print(f"firmware {m['firmware']}  unit +0x60={m['unit_code']!r} ({m['unit_source']})")
        print(f"factory sha256 {m['factory_sha256']}")
        print(format_matrix(m))
    return 0 if matrix_ok(m) else 1


# ---------------------------------------------------------------------------
# self-test


def selftest() -> int:
    """Synthetic checks of the matrix logic (no firmware, no vendor bytes)."""
    failures = 0

    def check(name, cond, detail=""):
        nonlocal failures
        print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  {detail}"))
        if not cond:
            failures += 1

    factory = b"\r\n".join([b"ABC-000-111", b"ABC-000-222", b"00-000000-00",
                            b"XXX00-YYYYY", b"00-00", b"000000000000"])
    unit = factory[:11]

    def fw_equal(card):  # behaves like the firmware rule: slot 0 bytes 0..10
        slot0 = b"\x00" * 11 if card is None else (card.split(b"\r\n")[0][:15] + b"\x00" * 11)[:11]
        r0 = int(slot0 == unit)
        return {"r0": r0, "verdict": "ACCEPT" if r0 else "REJECT",
                "card_slot0": slot0.decode("latin-1"), "stub_log": [], "insns": 1}

    def fw_line2(card):  # a wrong "firmware" that compares line 2 instead
        line2 = b"" if card is None else card.split(b"\r\n")[1]
        r0 = int(line2 == factory.split(b"\r\n")[1])
        return {"r0": r0, "verdict": "ACCEPT" if r0 else "REJECT",
                "card_slot0": "", "stub_log": [], "insns": 1}

    parts = factory.split(b"\r\n")
    v_l1 = b"\r\n".join([b"ABC-000-112"] + parts[1:])
    v_l2 = b"\r\n".join([parts[0], b"ABC-000-223"] + parts[2:])
    v_sw = b"\r\n".join([parts[1], parts[0]] + parts[2:])
    variants = [("l1.HDD_INFO.TXT", v_l1), ("l2.HDD_INFO.TXT", v_l2), ("sw.HDD_INFO.TXT", v_sw)]

    m = build_matrix(factory, variants, fw_equal)
    check("equal-rule firmware: 3 rows", m["variants"] == 3)
    check("equal-rule firmware: line-1 edit REJECT, line-2 edit ACCEPT, swap REJECT",
          [r["fw"] for r in m["rows"]] == ["REJECT", "ACCEPT", "REJECT"], m["rows"])
    check("equal-rule firmware: model agrees on all 3", m["agree"] == 3 and not m["disagree"], m)
    check("equal-rule firmware: controls hold (factory ACCEPT, no file REJECT)",
          all(c["ok"] for c in m["controls"].values()), m["controls"])
    check("equal-rule firmware: matrix_ok", matrix_ok(m))
    check("swap is labelled a permutation", m["rows"][2]["edit_kind"] == "permutation")

    bad = build_matrix(factory, variants, fw_line2)
    check("line-2 'firmware': disagreements are reported (falsifier can fire)",
          set(bad["disagree"]) == {"l1.HDD_INFO.TXT", "l2.HDD_INFO.TXT"}, bad["disagree"])
    check("line-2 'firmware': matrix_ok is False", not matrix_ok(bad))

    def fw_accept_all(card):
        return {"r0": 1, "verdict": "ACCEPT", "card_slot0": "", "stub_log": [], "insns": 1}

    ctl = build_matrix(factory, [], fw_accept_all)
    check("accept-all 'firmware': the no-file control fails",
          not ctl["controls"]["no_file"]["ok"] and not matrix_ok(ctl))

    class Stop(Exception):
        pass

    def fw_blocked(card):
        raise Stop("engine stopped")

    try:
        build_matrix(factory, variants, fw_blocked)
        check("a blocked run propagates (no silent verdict)", False)
    except Stop:
        check("a blocked run propagates (no silent verdict)", True)

    check("model maps PASS/DIFFERENT MAP CODE to ACCEPT/REJECT",
          MODEL_TO_FW["PASS"] == "ACCEPT" and MODEL_TO_FW[hddinfo.CHECK1_CODE] == "REJECT")

    print("selftest: " + ("OK" if not failures else f"{failures} FAILED"))
    return 1 if failures else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("run", help="firmware vs model check 1 for every variant")
    p.add_argument("image", help="IMG256 (EU2011 head)")
    p.add_argument("factory", help="factory HDD_INFO.TXT (model sys file, control)")
    p.add_argument("variant_dir", help="directory of *.HDD_INFO.TXT variants")
    p.add_argument("--unit-from", help="file whose line 1 bytes 0..10 are the unit +0x60 (default: factory)")
    p.add_argument("--tsv", help="write the per-variant table here (scratch, not the repo)")
    p.add_argument("--json", action="store_true")
    e = sub.add_parser("edges", help="write parser edge probes (not length-preserving) to OUT_DIR")
    e.add_argument("factory")
    e.add_argument("out_dir")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "edges":
        return cmd_edges(args)
    ap.print_help()
    return 3


if __name__ == "__main__":
    sys.exit(main())
