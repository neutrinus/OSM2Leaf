#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a vendor-free semantic L2 fixture and prove the check can fail (H131).

This ships the D3 "Krotoszyn fixture replacement" case of H21 as a real tool.
A semantic check written only as prose is not a gate: the D3 case replaces one
level-1 parcel of a factory-shaped tile with a known synthetic way and asserts
that the L2 semantic decode returns that way. ``l2check --semantic-tiles`` is
the assertion, driven by a *fixture-local* golden profile measured from the
good tree. No vendor bytes and no change to ``l2check`` semantics.

Pipeline (all inputs generated, no card image or vendor tile)::

    cardcheck.generate_fixture      deterministic tree: DRSTR/CMP.LST skeleton
                                    + a factory-shaped B48R058R.DAT (H103)
    synthetic .osm -> osm_ingest -> mesh_split -> tilewriter --factory
                                    splice one residential way into the
                                    fixture tile's only level-1 directory
    drstr_ze0.build                 re-size DRSTR001.DAT after the tile changed
    measure feature_digest on the good tile -> DIR/golden.json
    drstr_ze0.build                 LAST, so the golden inside DIR is counted
    l2check --root DIR --profile DIR/golden.json --semantic-tiles B48R058R.DAT
                                    positive control: RESULT: PASS, rc 0
    flip one byte of the way's zlib stream in a COPY of the tree
    l2check on the mutant           negative control: tile_semantic FAIL, rc 1

The golden is a small self-contained document with only
``tiles["B48R058R.DAT"]``::

    {"profile_version": 1,
     "tiles": {"B48R058R.DAT": {"features": N, "digest": "...", "levels": [1, 2]}}}

It is measured from *this* synthetic tree, never copied from
``tools/golden/eu2011.json``. ``--update-golden`` is deliberately not used: it
hardcodes its own four-tile semantic list and ignores ``--semantic-tiles``, so
a profile it writes has no entry for B48R058R.DAT and a mutation still passes.

The synthetic way is in the fixture directory's box (mesh y=72, x=936, i.e.
lat 48.0-48.67 / lon 12-14) and has ``highway=residential``. That maps to road
layer 5, which ``stream_decode.features`` keeps; a primary way maps to layer 6
and is filtered out, which would leave the digest unchanged (a placebo splice).
The base fixture decodes 3 features; the spliced tile decodes more, proving the
way is not a placebo.

Usage::

    python3 tools/make_l2_semantic_fixtures.py --out DIR
    python3 tools/make_l2_semantic_fixtures.py --selftest

Exit codes: ``0`` the tree was written and both checks behaved as required,
``1`` a check or internal assertion failed, ``2`` usage / I/O error.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
for _p in (str(TOOLS), str(TOOLS / "ze0-viewer"),
           str(TOOLS / "ze0-viewer" / "tools_ze0")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

CELL = "B48R058R"
TILE_REL = f"MAPAL001/{CELL}.DAT"
GOLDEN_NAME = "golden.json"
MUTANT_BYTE = 0x7A02

SYNTHETIC_OSM = """<?xml version="1.0" encoding="UTF-8"?>
<!-- Synthetic OSM input for H131 (not OSM data). Inside the H103 fixture
     tile's only level-1 directory, mesh y=72 x=936 (lat 48.x, lon 12.x). -->
<osm version="0.6" generator="osm2leaf-fixture">
 <node id="1" lat="48.3000" lon="12.2000"/>
 <node id="2" lat="48.3000" lon="12.6000"/>
 <node id="3" lat="48.3200" lon="12.7000"/>
 <way id="10">
  <nd ref="1"/><nd ref="2"/><nd ref="3"/>
  <tag k="highway" v="residential"/><tag k="name" v="Fixtowa"/>
 </way>
</osm>
"""


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=str(REPO), capture_output=True, text=True)


def _tool(name: str, *args: str) -> subprocess.CompletedProcess:
    return _run([sys.executable, str(TOOLS / name), *args])


def _measure(root: Path) -> tuple[int, str]:
    """Feature count and digest of the semantic tile, via l2check's own code."""
    import l2check  # noqa: PLC0415
    import stream_decode  # noqa: PLC0415

    feats = list(stream_decode.features(str(root / TILE_REL), levels={1, 2}))
    return l2check.feature_digest(feats)


def _rebuild_drstr(root: Path) -> None:
    import drstr_ze0  # noqa: PLC0415

    (root / "DRSTR001.DAT").write_bytes(drstr_ze0.build(root))


def _l2check(root: Path, golden: Path) -> tuple[int, str]:
    rc = _tool("l2check.py", "--root", str(root), "--profile", str(golden),
               "--semantic-tiles", CELL + ".DAT", "--cmp-limit", "20")
    return rc.returncode, rc.stdout + rc.stderr


def build(out: Path) -> dict:
    """Write the fixture tree into ``out``; return measured evidence."""
    import cardcheck  # noqa: PLC0415

    out = Path(out)
    if out.exists():
        if not out.is_dir():
            raise ValueError(f"--out exists and is not a directory: {out}")
        if any(out.iterdir()):
            raise ValueError(f"--out is not empty: {out}")
    out.mkdir(parents=True, exist_ok=True)

    # H103 skeleton (vendor-free). Its tile is factory-shaped but the way we
    # splice must stay inside its only level-1 directory.
    cardcheck.generate_fixture(out)

    osm = out / "synthetic.osm"
    osm.write_text(SYNTHETIC_OSM)
    imf = out / "imf.jsonl"
    split = out / "split.jsonl"
    for cp in (
        _tool("osm_ingest.py", str(osm), "-o", str(imf)),
        _tool("mesh_split.py", str(imf), "-o", str(split)),
        _tool("tilewriter.py", str(split), "--factory", str(out / TILE_REL),
              "--cell", CELL, "--country", "616", "--out", str(out / TILE_REL)),
    ):
        if cp.returncode != 0:
            raise RuntimeError(f"pipeline step failed: {cp.stdout}\n{cp.stderr}")

    # First DRSTR pass: the tile length changed, so the skeleton's DRSTR is
    # stale. The golden is written next and counted by the final rebuild.
    _rebuild_drstr(out)
    features, digest = _measure(out)
    if features <= 3:
        raise RuntimeError(f"spliced way did not add features (features={features})")

    golden = out / GOLDEN_NAME
    golden.write_text(json.dumps({
        "profile_version": 1,
        "tiles": {CELL + ".DAT": {
            "features": features, "digest": digest, "levels": [1, 2],
        }},
    }, indent=2, sort_keys=True) + "\n")
    # Rebuild DRSTR LAST so the golden's presence is accounted for.
    _rebuild_drstr(out)

    return {"features": features, "digest": digest, "golden": str(golden)}


def verify(out: Path, evidence: dict) -> dict:
    """Positive control on the tree, negative control on a copy."""
    import hashlib  # noqa: PLC0415

    out = Path(out)
    tile = out / TILE_REL
    raw = tile.read_bytes()
    if len(raw) <= MUTANT_BYTE:
        raise RuntimeError(f"tile too short to mutate: {len(raw)} bytes")

    good_rc, good_out = _l2check(out, out / GOLDEN_NAME)
    if good_rc != 0 or "RESULT: PASS" not in good_out:
        raise RuntimeError(f"good tree did not pass l2check (rc={good_rc}):\n{good_out}")

    # Mutate a COPY: the delivered --out tree stays byte-identical.
    tmp_root = Path(tempfile.mkdtemp(prefix="h131-mutant-", dir=str(out)))
    try:
        mutant = tmp_root / "tree"
        shutil.copytree(out, mutant, ignore=shutil.ignore_patterns("h131-mutant-*"))
        m_tile = mutant / TILE_REL
        data = bytearray(m_tile.read_bytes())
        before = data[MUTANT_BYTE]
        data[MUTANT_BYTE] ^= 0x01
        m_tile.write_bytes(data)
        bad_rc, bad_out = _l2check(mutant, mutant / GOLDEN_NAME)
        if bad_rc == 0 or "tile_semantic] FAIL" not in bad_out:
            raise RuntimeError(f"mutant did not fail tile_semantic (rc={bad_rc}):\n{bad_out}")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return {
        "good_rc": good_rc,
        "mutant_rc": bad_rc,
        "mutant_byte": hex(MUTANT_BYTE),
        "mutant_from": hex(before),
        "mutant_to": hex(before ^ 0x01),
        "tile_sha256": hashlib.sha256(raw).hexdigest(),
        "features": evidence["features"],
        "digest": evidence["digest"],
        "good_tail": good_out.strip().splitlines()[-1],
        "bad_tail": bad_out.strip().splitlines()[-1],
    }


def selftest() -> int:
    work = Path(tempfile.mkdtemp(prefix="h131-selftest-"))
    old_tmp = os.environ.get("TMPDIR")
    os.environ["TMPDIR"] = str(work)  # keep subprocesses off the tmpfs
    try:
        out = work / "fixture"
        evidence = build(out)
        result = verify(out, evidence)
        assert result["good_rc"] == 0, result
        assert result["mutant_rc"] == 1, result
        assert result["good_tail"].endswith("PASS"), result
        assert result["bad_tail"].endswith("FAIL"), result
        print("make_l2_semantic_fixtures selftest: PASS")
        print(f"  features={result['features']} digest={result['digest']}")
        print(f"  good rc={result['good_rc']} {result['good_tail']}")
        print(f"  mutant {result['mutant_byte']} {result['mutant_from']}->"
              f"{result['mutant_to']} rc={result['mutant_rc']} {result['bad_tail']}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"make_l2_semantic_fixtures selftest: FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        if old_tmp is None:
            os.environ.pop("TMPDIR", None)
        else:
            os.environ["TMPDIR"] = old_tmp
        shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", metavar="DIR", help="write the fixture tree here")
    ap.add_argument("--selftest", action="store_true",
                    help="run the vendor-free positive+negative self-test")
    args = ap.parse_args(argv)
    if args.selftest:
        if args.out:
            ap.error("--out and --selftest are mutually exclusive")
        return selftest()
    if not args.out:
        ap.error("--out is required (or use --selftest)")
    try:
        out = Path(args.out)
        evidence = build(out)
        result = verify(out, evidence)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"result": "PASS", "tree": str(out), **result}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
