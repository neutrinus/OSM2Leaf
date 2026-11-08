#!/usr/bin/env python3
# @category OSM2Leaf
# @runtime PyGhidra
"""The one documented Ghidra entry script of the L3 harness (TODO M9.20).

``runner.py run`` (legacy mode, no FUNC) hands a Ghidra run this script.  The
contract, as ``runner.py`` builds it::

    analyzeHeadless <project> l3 -import <image> -processor SuperH:BE:32:SH-4 \\
        -scriptPath tools/l3_harness/ghidra -postScript l3_run.py \\
        <rommap.json> <manifest.json> <result.json>

Behaviour, in full:

* three positional arguments, else exit ``2``;
* the memory map and the manifest are loaded and validated with the harness
  modules; an invalid input exits ``1`` and writes **no** result, so the
  runner reports ``BLOCKED`` ("no result JSON is not a pass");
* otherwise it writes ``osm2leaf.l3.ghidra_result/v1`` with ``status``
  ``BLOCKED`` and an empty ``cases`` list, and exits ``0``.  No located reader
  is wired into this script yet, so it never reports a verdict; the runner
  turns the ``BLOCKED`` status into exit ``4`` and a missing ``cases`` entry
  can never be read as a pass.

A module-kind target is run by ``runner.py run TARGET --engine ghidra`` through
``engine.GhidraBackend`` (in-process pyghidra), not by this script.  That path
is **not verified**: no Ghidra or Java is installed in this repository's
environment, so no Ghidra run has happened.

Runtime: CPython with PyGhidra (Ghidra 12.2+).  Jython 2.7 is not supported
here; the Jython scripts that ``ghidra_import.py`` writes are a separate path.
The ``ghidra`` package is imported only inside :func:`ghidra_api_available`, so
this file imports and self-tests without Ghidra.

Usage::

    python3 tools/l3_harness/ghidra/l3_run.py ROMMAP MANIFEST RESULT
    python3 tools/l3_harness/ghidra/l3_run.py --selftest

Exit codes: ``0`` result written (status BLOCKED), ``1`` invalid input, ``2``
usage error, ``3`` selftest failure.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from l3_harness import manifest as manifest_mod  # noqa: E402
from l3_harness import rommap as rommap_mod  # noqa: E402

RESULT_SCHEMA = "osm2leaf.l3.ghidra_result/v1"
NO_READER_REASON = (
    "no located reader entry is wired into ghidra/l3_run.py; a module target "
    "runs through runner.py run TARGET --engine ghidra (unverified, no Ghidra "
    "here)"
)

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
EXIT_SELFTEST = 3


#: A real submodule of the Ghidra API.  The bare name ``ghidra`` is not a
#: probe: with ``tools/l3_harness`` on ``sys.path``, the directory named
#: ``ghidra/`` imports as an empty namespace package.
GHIDRA_PROBE_MODULE = "ghidra.program.model.listing"


def ghidra_api_available() -> bool:
    """True when the Ghidra Python API can be imported (PyGhidra or Ghidra)."""

    import importlib

    try:
        importlib.import_module(GHIDRA_PROBE_MODULE)
    except ImportError:
        return False
    return True


def build_result(*, ghidra_api: bool, rommap_path: str, manifest_path: str) -> dict:
    """The result document.  Always BLOCKED: this script runs no reader."""

    reason = NO_READER_REASON
    if not ghidra_api:
        reason = "Ghidra API not importable in this interpreter; " + reason
    return {
        "schema": RESULT_SCHEMA,
        "status": "BLOCKED",
        "reason": reason,
        "ghidra_api": ghidra_api,
        "inputs": {"rommap": rommap_path, "manifest": manifest_path},
        "cases": [],
        "l3_claim": False,
    }


def load_inputs(rommap_path: str, manifest_path: str) -> list[str]:
    """Problems in the two input documents; empty when both are valid."""

    problems: list[str] = []
    try:
        rommap_doc = rommap_mod.load(rommap_path)
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"cannot read memory map {rommap_path}: {exc}")
    else:
        problems.extend(rommap_mod.validate(rommap_doc))
    try:
        manifest_doc = manifest_mod.load(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"cannot read manifest {manifest_path}: {exc}")
    else:
        problems.extend(manifest_mod.validate(manifest_doc, check_files=False))
    return problems


def run(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            "usage: l3_run.py ROMMAP MANIFEST RESULT (or --selftest)",
            file=sys.stderr,
        )
        return EXIT_USAGE
    rommap_path, manifest_path, result_path = argv
    problems = load_inputs(rommap_path, manifest_path)
    if problems:
        for problem in problems:
            print(f"FAIL {problem}", file=sys.stderr)
        return EXIT_INVALID
    result = build_result(
        ghidra_api=ghidra_api_available(),
        rommap_path=rommap_path,
        manifest_path=manifest_path,
    )
    Path(result_path).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"l3_run: BLOCKED ({RESULT_SCHEMA}) -> {result_path}")
    return EXIT_OK


def _script_args() -> list[str]:
    """Arguments from ``analyzeHeadless -postScript`` or ``sys.argv``."""

    getter = globals().get("getScriptArgs")
    if callable(getter):
        return [str(item) for item in getter()]
    return sys.argv[1:]


# --------------------------------------------------------------------------
# Selftest (no Ghidra, no vendor data)
# --------------------------------------------------------------------------


def selftest() -> int:
    import contextlib
    import io

    from l3_harness import selftest as suite

    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        corpus = suite.make_corpus(tmp)
        rommap_path = suite.write_json(
            root / "rommap.json", rommap_mod.convert(suite.make_report())
        )
        manifest_path = suite.write_json(
            root / "manifest.json", suite.make_manifest(corpus)
        )
        result_path = root / "result.json"

        def check(name, ok):
            if not ok:
                failures.append(name)
            print(f"{'ok  ' if ok else 'FAIL'} l3_run: {name}")

        doc = build_result(
            ghidra_api=False,
            rommap_path="r.json",
            manifest_path="m.json",
        )
        check("result is BLOCKED with no cases and no claim",
              doc["status"] == "BLOCKED" and doc["cases"] == [] and doc["l3_claim"] is False)
        check("result names its schema", doc["schema"] == RESULT_SCHEMA)
        check("missing Ghidra API is stated in the reason",
              "not importable" in doc["reason"])

        # The hazard the probe avoids: an empty ``ghidra/`` directory on the
        # path must not count as the Ghidra API.
        fake_root = root / "path-with-ghidra-dir"
        (fake_root / "ghidra").mkdir(parents=True)
        sys.path.insert(0, str(fake_root))
        try:
            collided = ghidra_api_available()
        finally:
            sys.path.remove(str(fake_root))
            for name in [n for n in sys.modules if n == "ghidra" or n.startswith("ghidra.")]:
                del sys.modules[name]
        check("an empty ghidra/ directory on sys.path is not the Ghidra API",
              collided is False)

        with contextlib.redirect_stderr(io.StringIO()):
            usage = run([str(rommap_path)])
        check("wrong argument count is a usage error (exit 2)", usage == EXIT_USAGE)
        check("usage error writes no result", not result_path.exists())

        bad = root / "bad-rommap.json"
        bad.write_text("{}", encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            invalid = run([str(bad), str(manifest_path), str(result_path)])
        check("invalid memory map exits 1", invalid == EXIT_INVALID)
        check("invalid input writes no result (not a pass)", not result_path.exists())

        with contextlib.redirect_stdout(io.StringIO()):
            ok = run([str(rommap_path), str(manifest_path), str(result_path)])
        check("valid inputs exit 0", ok == EXIT_OK)
        written = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
        check("written result is BLOCKED, never PASS",
              written.get("status") == "BLOCKED" and written.get("cases") == [])

    if failures:
        print(f"l3_run selftest: FAILED ({len(failures)})")
        return EXIT_SELFTEST
    print("l3_run selftest: OK")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _script_args() if argv is None else list(argv)
    if args == ["--selftest"]:
        return selftest()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
