#!/usr/bin/env python3
"""Compare firmware-read records with the Python models (M9.18, record level).

The firmware path is NOT reimplemented here.  ``datask_l3.py mount --request``
runs the real EU2011 data-access task on PySh4 and records, for the served
record: which file/offset/length it read, where its completion handler moved
the compressed stream, how many inflated bytes the word-swap function
(``fn 0x003f6968``) loaded, which words ``0x004048cc``/``0x00405078`` loaded and
the ``0x14b6`` reply sub codes.  This tool takes those *observed* windows and
compares them with the same record decoded offline by ``lev3456.py`` (coarse
levels 3-6) and ``section4.py`` (tile section-4 name list).

Only offsets, counts, hashes and short header words enter the JSON report;
no vendor bytes are written into the repository.

Usage
-----
  python3 tools/record_l3.py --selftest
  python3 tools/record_l3.py run IMG256 --card-image CARD \
      --lev-mesh 0xA40FD405 --lev-level 5 \
      --s4-mesh 0xa6cdd6be --s4-kind 0x40 --position LAT,LON \
      --factory-root FACT --json OUT.json
  python3 tools/record_l3.py analyze --lev-json LEV.json --s4-json S4.json \
      --factory-root FACT --json OUT.json

``run`` forwards ``--flip``/``--replace`` to ``datask_l3.py`` so a corruption
control changes the bytes the *firmware* reads (a Python-side buffer flip is
not a control).  ``analyze`` re-checks JSON produced by such a run.
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
import zlib
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import lev3456  # noqa: E402
import section4  # noqa: E402

# Firmware VAs observed by datask_l3.py (EU2011 build A).  Not guessed literals:
# each is a pdata START reported by nk_decomp.py pdata (M9.18 EXP, section 2a);
# 0x003f6968 is a code location INSIDE fn 0x003f6908, never a callable entry.
FN_WORDSWAP = 0x003F6968
FN_CODE = 0x004048CC       # loads the parcel code words 0-1
FN_UNIT = 0x00405078       # loads the unit-table words
TAG_RECORD = 0x0900

LEV_FILE = "MAPAL001/LEV3456R.DAT"
S4_FILE_FRAG = "B48R058R.DAT"   # the factory tile of the section-4 run

# Expected reply sub codes for a served record (M9.53 C-5918): sub 5 + sub 3.
SERVED_SUBS = {5, 3}


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from(">H", data, off)[0]


def find_record_row(doc: dict, mesh: int, file_frag: str) -> dict | None:
    """The record read of *mesh* from the file whose name contains *file_frag*."""
    hits = [
        r for r in doc.get("rows", [])
        if r.get("request") == mesh
        and file_frag.upper() in str(r.get("file", "")).upper()
        and r.get("tag") == TAG_RECORD
    ]
    return hits[-1] if hits else None


def firmware_facts(doc: dict, mesh: int, file_frag: str) -> dict:
    """Facts the firmware run observed, with no vendor bytes."""
    row = find_record_row(doc, mesh, file_frag)
    if row is None:
        return {"mesh": mesh, "file_frag": file_frag, "found": False,
                "reply_subs": sorted({s.get("sub") for r in doc.get("requests", [])
                                      for s in r.get("replies", [])})}
    code_runs = []
    unit_runs = []
    for reader in row.get("record_readers", []):
        if reader.get("fn") == FN_CODE:
            code_runs.extend(reader.get("runs", []))
        elif reader.get("fn") == FN_UNIT:
            unit_runs.extend(reader.get("runs", []))
    memmove = []
    for reader in row.get("readers", []):
        if reader.get("via") == "memmove":
            memmove.extend(reader.get("runs", []))
    subs = sorted({s.get("sub") for r in doc.get("requests", [])
                   for s in r.get("replies", [])})
    return {
        "mesh": mesh,
        "file_frag": file_frag,
        "found": True,
        "file": row["file"],
        "pos": row["pos"],
        "length": row["length"],
        "status": row.get("status"),
        "memmove": memmove,
        "inflated_len": row["record_readers"][0]["bytes"] if row.get("record_readers") else None,
        "code_runs": code_runs,
        "unit_runs": unit_runs,
        "reply_subs": subs,
    }


def model_facts(fw: dict, factory_root: str, kind: str,
                lev_level: int = 5, min_name: int = 4) -> dict:
    """Decode, with the Python models, the same record the firmware read."""
    if not fw.get("found") or not fw.get("memmove"):
        return {"decoded": False, "reason": "no firmware record read or no memmove window"}
    start, end = fw["memmove"][0]
    path = Path(factory_root) / fw["file"]
    data = path.read_bytes()
    raw = data[fw["pos"] + start: fw["pos"] + end + 1]
    try:
        plain = zlib.decompress(raw)
    except zlib.error as exc:
        return {"decoded": False, "reason": "zlib: %s" % exc,
                "raw": len(raw), "plain_prefix": raw[:4].hex()}
    w0, w1 = _u16(plain, 0), _u16(plain, 2)
    parcel = (w0 << 16) | w1
    result = {
        "decoded": True,
        "raw": len(raw),
        "plain_len": len(plain),
        "parcel_w0": w0,
        "parcel_w1": w1,
        "parcel_u32": parcel,
        "plain_sha256": _sha(plain),
    }
    if kind == "lev":
        rec = lev3456.decode_record(plain, lev_level, 0, sid=1)
        result["role"] = rec.get("role")
        result["opaque"] = bool(rec.get("opaque"))
        result["header0"] = rec.get("header", [])[:8]
    else:
        rec = section4.parse_record(plain, 0, "zlib", min_name)
        result["status"] = rec.get("status")
        result["type_tag"] = rec.get("type_tag")
        result["country_code"] = rec.get("country_code")
        result["names"] = [n.get("text") for n in rec.get("names", [])]
    return result


def _sha(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()[:16]


def compare(fw: dict, model: dict, kind: str, mesh: int,
            s4_file: str = S4_FILE_FRAG) -> dict:
    """One MATCH/MISMATCH verdict with the checked quantities."""
    checks = []
    expected_file = LEV_FILE if kind == "lev" else s4_file
    checks.append(("firmware-read-file", fw.get("found", False)
                   and expected_file.upper() in str(fw.get("file", "")).upper()))
    checks.append(("status-ok", fw.get("status") == 0))
    checks.append(("served-subs", set(fw.get("reply_subs", [])) == SERVED_SUBS))
    checks.append(("decoded", model.get("decoded", False)))
    if model.get("decoded"):
        checks.append(("inflated-length", model["plain_len"] == fw.get("inflated_len")))
        checks.append(("parcel-code", model["parcel_u32"] == mesh))
        if kind == "lev":
            checks.append(("coarse-role", model.get("role") in ("level5", "road", "background")
                           and not model.get("opaque")))
        else:
            checks.append(("section4-status", model.get("status") == "ok"))
            checks.append(("name-list", len(model.get("names", [])) > 0))
        for lo, hi in fw.get("unit_runs", []):
            checks.append(("unit-run-in-record", hi < model["plain_len"]))
        for lo, hi in fw.get("code_runs", []):
            checks.append(("code-run-in-record", hi < model["plain_len"]))
    verdict = "MATCH" if all(ok for _, ok in checks) else "MISMATCH"
    return {
        "kind": kind,
        "mesh": hex(mesh),
        "verdict": verdict,
        "checks": {name: ("OK" if ok else "FAIL") for name, ok in checks},
        "firmware": fw,
        "model": model,
    }


def _run_datask(args, image: str, card: str | None, card_root: str | None,
                mesh: int, kind: int, position: str, json_path: Path) -> str:
    cmd = [sys.executable, str(TOOLS_DIR / "datask_l3.py"), "mount", image]
    if card:
        cmd += ["--card-image", card]
    if card_root:
        cmd += ["--card-root", card_root]
    cmd += ["--position", position, "--request", hex(mesh),
            "--kind", hex(kind), "--bytes", "--json", str(json_path)]
    for fl in args.flip:
        cmd += ["--flip", fl]
    for rp in args.replace:
        cmd += ["--replace", rp]
    env = os.environ.copy()
    # Short TMPDIR in the home tree: /tmp is a 3.8 GiB tmpfs here.
    scratch = Path(args.workdir).expanduser()
    scratch.mkdir(parents=True, exist_ok=True)
    env["TMPDIR"] = str(scratch)
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError("datask_l3.py exited %d for mesh %s:\n%s" %
                           (proc.returncode, hex(mesh), proc.stderr[-2000:]))
    return proc.stdout


def command_run(args) -> int:
    work = Path(args.workdir).expanduser()
    work.mkdir(parents=True, exist_ok=True)
    lev_json = work / "record-lev.json"
    s4_json = work / "record-s4.json"
    _run_datask(args, args.image, args.card_image, args.card_root,
                args.lev_mesh, 4, args.position, lev_json)
    _run_datask(args, args.image, args.card_image, args.card_root,
                args.s4_mesh, args.s4_kind, args.position, s4_json)
    return _report(args, json.loads(lev_json.read_text()),
                   json.loads(s4_json.read_text()))


def command_analyze(args) -> int:
    return _report(args, json.loads(Path(args.lev_json).read_text()),
                   json.loads(Path(args.s4_json).read_text()))


def _report(args, lev_doc: dict, s4_doc: dict) -> int:
    results = []
    for kind, doc, mesh, level in (
        ("lev", lev_doc, args.lev_mesh, args.lev_level),
        ("s4", s4_doc, args.s4_mesh, None),
    ):
        s4_file = getattr(args, "s4_file", S4_FILE_FRAG)
        fw = firmware_facts(doc, mesh, LEV_FILE if kind == "lev" else s4_file)
        model = model_facts(fw, args.factory_root, kind, lev_level=level or 5)
        res = compare(fw, model, kind, mesh, s4_file=s4_file)
        results.append(res)
        print("%-3s mesh %-12s %-8s  file=%s pos=%s len=%s inflated=%s model=%s" % (
            kind.upper(), hex(mesh), res["verdict"],
            fw.get("file", "-"), hex(fw.get("pos", 0)), hex(fw.get("length", 0)),
            fw.get("inflated_len"), model.get("plain_len", "-")))
        for name, state in res["checks"].items():
            print("      %-22s %s" % (name, state))
        if kind == "s4" and model.get("names"):
            print("      names: %s" % ", ".join(model["names"]))
    out = {
        "schema": "osm2leaf.record_l3/v1",
        "image": getattr(args, "image", None),
        "card_image": getattr(args, "card_image", None),
        "factory_root": args.factory_root,
        "results": results,
        "ok": all(r["verdict"] == "MATCH" for r in results),
    }
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2, sort_keys=True))
    print("RESULT: %s" % ("MATCH" if out["ok"] else "MISMATCH"))
    return 0 if out["ok"] else 1


def selftest() -> int:
    """Tool plumbing only: synthetic windows, never a firmware verdict."""
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))

    mesh = 0xA40FD405
    plain = bytearray(b"\x00" * 64)
    struct.pack_into(">HH", plain, 0, 0xA40F, 0xD405)
    struct.pack_into(">H", plain, 0xE, 13)   # unit table word the firmware loads
    raw = zlib.compress(bytes(plain))
    fw = {"mesh": mesh, "file_frag": "LEV3456R", "found": True,
          "file": LEV_FILE, "pos": 0x86900, "length": len(raw), "status": 0,
          "memmove": [[0, len(raw) - 1]], "inflated_len": len(plain),
          "code_runs": [[0, 3]], "unit_runs": [[14, 15]], "reply_subs": [3, 5]}
    model = {"decoded": True, "plain_len": len(plain),
             "parcel_w0": 0xA40F, "parcel_w1": 0xD405,
             "parcel_u32": mesh, "role": "level5", "opaque": False}
    check("synthetic-MATCH", compare(fw, model, "lev", mesh)["verdict"] == "MATCH")
    bad = dict(model)
    bad["parcel_u32"] = mesh ^ 1
    check("synthetic-MISMATCH", compare(fw, bad, "lev", mesh)["verdict"] == "MISMATCH")
    check("no-firmware-read-is-MISMATCH",
          compare(firmware_facts({"rows": [], "requests": []}, mesh, "LEV3456R"),
                  model, "lev", mesh)["verdict"] == "MISMATCH")
    check("sub9-is-MISMATCH",
          compare(dict(fw, reply_subs=[5, 9]), model, "lev", mesh)["verdict"] == "MISMATCH")
    check("model-decode-uses-zlib", zlib.decompress(raw) == bytes(plain))
    ok = all(v for _, v in checks)
    for name, v in checks:
        print("  %-32s %s" % (name, "OK" if v else "FAIL"))
    print("record_l3 selftest: %s (%d/%d)" % ("OK" if ok else "FAIL",
                                               sum(v for _, v in checks), len(checks)))
    return 0 if ok else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    def add_common(sp, need_json=True):
        sp.add_argument("--factory-root", required=True,
                        help="root with MAPAL001/LEV3456R.DAT and the factory tile")
        sp.add_argument("--lev-mesh", type=lambda v: int(v, 0), default=0xA40FD405)
        sp.add_argument("--s4-mesh", type=lambda v: int(v, 0), default=0xA6CDD6BE)
        sp.add_argument("--s4-kind", type=lambda v: int(v, 0), default=0x40)
        sp.add_argument("--s4-file", default=S4_FILE_FRAG,
                        help="expected served tile file fragment (default B48R058R.DAT)")
        sp.add_argument("--lev-level", type=int, default=5)
        sp.add_argument("--position", default="51.70,17.45")
        sp.add_argument("--json", required=need_json)

    r = sub.add_parser("run", help="run both datask_l3.py fetches, then compare")
    r.add_argument("image")
    r.add_argument("--card-image")
    r.add_argument("--card-root")
    r.add_argument("--workdir", required=True)
    r.add_argument("--flip", action="append", default=[], metavar="PATH@OFF:BYTE")
    r.add_argument("--replace", action="append", default=[], metavar="PATH=FILE")
    add_common(r)

    a = sub.add_parser("analyze", help="compare existing datask_l3.py --json outputs")
    a.add_argument("--lev-json", required=True)
    a.add_argument("--s4-json", required=True)
    add_common(a)

    args = p.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "run":
        return command_run(args)
    if args.cmd == "analyze":
        return command_analyze(args)
    p.error("choose --selftest, run or analyze")


if __name__ == "__main__":
    sys.exit(main())
