#!/usr/bin/env python3
"""Decompressor runtime-oracle contract for nk.exe CE-LZXD (M1.2f/M8.E1/M9).

Pins the verified EXP-49 vectors and checks an oracle result JSON produced by a
runtime back end (QEMU `cedecomp_run.py`, a future Ghidra micro-harness, or an
external run).  This module never runs QEMU/Ghidra and never claims a decode; it
only defines the contract and verifies reported bytes against pinned lengths and
optional expected hashes.

No vendor bytes are embedded.  The compressed EXP-49 inputs live in IMG256 at
the recorded file offsets (see M8.E1b / cedecomp_run.EXP49); a runtime oracle
reads them from the image it is given.

Usage:
  python3 tools/decomp_oracle.py --selftest
  python3 tools/decomp_oracle.py vectors --json
  python3 tools/decomp_oracle.py verify result.json
Exit: 0 ok/match, 1 mismatch/invalid, 2 usage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

SCHEMA = "osm2leaf.decomp_oracle/v1"
IMG256_SHA256 = "92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9"
NK_IMAGE_START = 0x3E00200

# Verified entries (LE, IMG256 nk.exe build B; M8.E1b C-2290-C-2294).
TARGETS = {
    "DECOMP_WRAP": {"va": 0x88037590, "args": ["src", "psize", "dest", "vsize"],
                    "note": "wrapper; needs kernel-context stubs under bare metal (C-2293)"},
    "DECOMP_SECT": {"va": 0x88037464, "args": ["src", "psize", "dest_ctx_or_buf", "vsize"],
                    "note": "core framing entry (form 1/2 + block loop); preferred oracle target"},
    "DECOMP_BLK": {"va": 0x8803A384, "args": "frame/state (see DECOMP_SECT)",
                   "note": "per-block LZXD-like codec (sub-fragment)"},
    "DECOMP_ALLOC": {"va": 0x88034D94, "args": ["vsize"], "note": "kernel-context dependent"},
}

# EXP-49: M1.2a lengths/payload offsets. expected_sha256 of the *decoded* output
# is intentionally absent until a runtime oracle produces it; fill via an EXP,
# never by guessing.
VECTORS = [
    {
        "name": "exp49_navimapcc_sec1",
        "module": "NaviMapCC.dll",
        "section_rva": 0x13000,
        "file_off": 0x01580CE0,
        "psize": 0x2C6,
        "vsize": 0x5B8,
        "expected_decoded_len": 0x484,
        "expected_decoded_sha256": None,
        "compressed_header_le32": 0x00C60484,
    },
    {
        "name": "exp49_navimapcc_sec2",
        "module": "NaviMapCC.dll",
        "section_rva": 0x14000,
        "file_off": 0x015ACA7C,
        "psize": 0x68C,
        "vsize": 0xCC0,
        "expected_decoded_len": 0xCC0,
        "expected_decoded_sha256": None,
        "compressed_header_le32": 0x008C0CC0,
    },
]


def vectors_doc():
    return {
        "schema": SCHEMA,
        "kind": "vectors",
        "img256_sha256": IMG256_SHA256,
        "nk_image_start": NK_IMAGE_START,
        "targets": TARGETS,
        "vectors": VECTORS,
        "notes": [
            "Decode a vector by reading psize bytes at file_off from IMG256 and "
            "calling DECOMP_SECT (preferred) or DECOMP_WRAP with kernel-context "
            "stubs; compare output length to expected_decoded_len.",
            "expected_decoded_sha256 is null until produced by a verified runtime "
            "oracle and recorded in an EXP (never guessed).",
            "SH-4 is little-endian for these code paths (M1.11/M8.E1b).",
        ],
    }


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_result(doc):
    """Verify an oracle result JSON.

    Accepted shapes:
      {"schema":..., "results":[{"name":..., "decoded_len":N, "decoded_sha256"?:hex,
        "status"?: "ok"} , ...]}
      or {"name":..., "decoded_len":N, "decoded_sha256"?:hex} (single)
    Returns (ok:bool, problems:list[str], checked:int).
    """
    problems = []
    checked = 0
    if isinstance(doc, dict) and "results" in doc:
        items = doc["results"]
    elif isinstance(doc, dict) and "name" in doc:
        items = [doc]
    elif isinstance(doc, list):
        items = doc
    else:
        return False, ["result must be an object with 'results', a single result object, or a list"], 0
    by_name = {v["name"]: v for v in VECTORS}
    for it in items:
        if not isinstance(it, dict):
            problems.append(f"non-object result item: {it!r}")
            continue
        name = it.get("name")
        if name not in by_name:
            problems.append(f"unknown vector name {name!r}")
            continue
        v = by_name[name]
        checked += 1
        if it.get("status") in ("FAIL", "MISMATCH", "ERROR"):
            problems.append(f"{name}: reported status {it.get('status')}")
        dlen = it.get("decoded_len")
        if dlen is None:
            problems.append(f"{name}: missing decoded_len")
        elif int(dlen) != v["expected_decoded_len"]:
            problems.append(f"{name}: decoded_len {dlen} != expected {v['expected_decoded_len']}")
        got_sha = it.get("decoded_sha256")
        exp_sha = v["expected_decoded_sha256"]
        if got_sha and exp_sha and got_sha.lower() != exp_sha.lower():
            problems.append(f"{name}: decoded_sha256 mismatch")
        elif got_sha and not exp_sha:
            # A produced hash is fine; it becomes evidence via EXP, not auto-pinned.
            pass
    return (len(problems) == 0 and checked > 0), problems, checked


def selftest():
    errors = 0

    def check(cond, msg):
        nonlocal errors
        if cond:
            print("ok:", msg)
        else:
            print("FAIL:", msg)
            errors += 1

    doc = vectors_doc()
    check(doc["schema"] == SCHEMA, "schema")
    check(len(doc["vectors"]) == 2, "two EXP-49 vectors")
    v1 = doc["vectors"][0]
    check(v1["expected_decoded_len"] == 0x484 and v1["psize"] == 0x2C6, "sec1 lengths")
    check(doc["vectors"][1]["expected_decoded_len"] == 0xCC0, "sec2 decoded length")
    check(TARGETS["DECOMP_SECT"]["va"] == 0x88037464, "DECOMP_SECT VA")
    check(TARGETS["DECOMP_WRAP"]["va"] == 0x88037590, "DECOMP_WRAP VA")
    check(doc["img256_sha256"] == IMG256_SHA256, "IMG256 pin")

    ok, probs, n = verify_result({"name": "exp49_navimapcc_sec1", "decoded_len": 0x484, "decoded_sha256": "ab" * 32})
    check(ok and n == 1 and probs == [], "single good result")
    ok, probs, n = verify_result({"schema": SCHEMA, "results": [
        {"name": "exp49_navimapcc_sec1", "decoded_len": 0x484},
        {"name": "exp49_navimapcc_sec2", "decoded_len": 0xCC0},
    ]})
    check(ok and n == 2, "two good results")
    ok, probs, _n = verify_result({"name": "exp49_navimapcc_sec1", "decoded_len": 0x483})
    check((not ok) and any("decoded_len" in p for p in probs), "length mismatch detected")
    ok, probs, _n = verify_result({"name": "nope", "decoded_len": 1})
    check(not ok and any("unknown" in p for p in probs), "unknown vector detected")
    ok, probs, _n = verify_result({"results": [{"name": "exp49_navimapcc_sec1", "status": "FAIL", "decoded_len": 0x484}]})
    check(not ok, "reported FAIL detected")
    ok, probs, _n = verify_result({"x": 1})
    check(not ok, "invalid shape rejected")
    # produced hash is accepted (evidence path), mismatch against a pinned hash fails
    pinned = [dict(VECTORS[0], expected_decoded_sha256="11" * 32)]
    saved = VECTORS[:]
    VECTORS[:] = pinned + VECTORS[1:]
    try:
        ok, probs, _n = verify_result({"name": "exp49_navimapcc_sec1", "decoded_len": 0x484, "decoded_sha256": "22" * 32})
        check(not ok and any("sha256 mismatch" in p for p in probs), "pinned sha mismatch detected")
    finally:
        VECTORS[:] = saved

    if errors:
        print(f"decomp_oracle selftest: {errors} FAILED")
        return 1
    print("decomp_oracle selftest: all ok")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sp = ap.add_subparsers(dest="cmd")
    v = sp.add_parser("vectors", help="print pinned vectors/targets")
    v.add_argument("--json", action="store_true")
    vf = sp.add_parser("verify", help="verify an oracle result JSON")
    vf.add_argument("result", help="result JSON path, or - for stdin")
    args = ap.parse_args()
    if args.selftest:
        raise SystemExit(selftest())
    if args.cmd == "vectors":
        print(json.dumps(vectors_doc(), indent=2))
        raise SystemExit(0)
    if args.cmd == "verify":
        raw = sys.stdin.read() if args.result == "-" else Path(args.result).read_text(encoding="utf-8")
        try:
            doc = json.loads(raw)
        except Exception as e:
            print(f"FAIL: invalid JSON: {e}")
            raise SystemExit(1)
        ok, probs, n = verify_result(doc)
        for p in probs:
            print("FAIL:", p)
        print(f"checked={n} ok={ok}")
        raise SystemExit(0 if ok else 1)
    ap.print_help()
    raise SystemExit(2)


if __name__ == "__main__":
    main()
