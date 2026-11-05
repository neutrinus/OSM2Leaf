#!/usr/bin/env python3
"""Self-test for the L3 harness skeleton (synthetic data only).

Covers the acceptance conditions from the work item:

* a built manifest validates, and a bad SHA-256, an unknown verdict, an
  unknown reader/case, a duplicate and a missing file are all rejected;
* a synthetic cerom report converts to a valid memory map, while overlapping
  sections, a compressed section and a zero-sized section are rejected;
* the stub table is complete and its schema is JSON-serialisable;
* ``runner check``/``plan`` succeed on valid inputs, a bad manifest fails,
  missing Ghidra exits ``3`` and a missing harness script exits ``4`` without
  claiming a pass.

No vendor data, no network, no Ghidra.  Usage::

    python3 tools/l3_harness/selftest.py
    python3 tools/l3_harness/runner.py selftest

Exit codes: ``0`` all checks passed, ``1`` at least one failed.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from l3_harness import manifest, rommap, runner, stubs  # noqa: E402

CORPUS_FILES = {
    "REFER001/ADDRE001.DAT.cmp": b"cmp payload \x00\x01\x02",
    "REFER001/ADDRE001.DAT.cmp.bad-ind": b"broken index",
    "MAPAL001/B28R070R.DAT": b"tile bytes",
    "DRSTR001.DAT": b"drstr tree",
    "VER_INFO/HDD_INFO.TXT": b"manufacturer_id=1 userdata_type=0 destination_id=2\n",
}

CORPUS_SPECS = [
    ("factory", "cmp_ind", "REFER001/ADDRE001.DAT.cmp", None),
    ("corrupt_ind", "cmp_ind", "REFER001/ADDRE001.DAT.cmp.bad-ind", None),
    ("tile_factory", "tile", "MAPAL001/B28R070R.DAT", None),
    ("drstr_factory", "drstr", "DRSTR001.DAT", None),
    ("hdd_info_factory", "hdd_info", "VER_INFO/HDD_INFO.TXT", None),
]

CHECKS: list[tuple[str, callable]] = []


def check(name):
    def register(func):
        CHECKS.append((name, func))
        return func

    return register


def make_corpus(tmp) -> Path:
    root = Path(tmp) / "corpus"
    for relative, data in CORPUS_FILES.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return root


def make_manifest(root) -> dict:
    return manifest.build(root, CORPUS_SPECS)


def make_report() -> dict:
    return {
        "image": "/vendor/LEAF_2011-2012_QSD-309-101_navi158_eu.img",
        "image_size": 0x10000,
        "image_sha256": "a" * 64,
        "segments": [
            {
                "segment_base": "0x200200",
                "ecec_offset": "0x200240",
                "pTOC": "0x80000000",
                "size": "0x1000",
                "phys_base": "0x8cae1000",
                "romhdr": {
                    "physfirst": "0x8cae1000",
                    "physlast": "0x8cb00000",
                    "ulRAMStart": "0x8c000000",
                    "ulRAMEnd": "0x8c100000",
                    "nummods": 2,
                    "numfiles": 0,
                    "usCPUType": 0x01A6,
                },
                "modules": [
                    {
                        "name": "Navi.exe",
                        "vbase": "0x8cae1000",
                        "sections": [
                            {
                                "name": ".text",
                                "va": "0x8cae1000",
                                "file_offset": 0x1000,
                                "size": 0x2000,
                                "characteristics": "0x60000020",
                                "compressed": False,
                            },
                            {
                                "name": ".rdata",
                                "va": "0x8caf0000",
                                "file_offset": 0x3000,
                                "size": 0x1000,
                                "characteristics": "0x40000040",
                                "compressed": False,
                            },
                        ],
                    },
                    {
                        "name": "STDDLL.dll",
                        "vbase": "0x8cb00000",
                        "sections": [
                            {
                                "name": ".bss",
                                "va": "0x8cb00000",
                                "size": 0x800,
                                "stored_size": 0,
                                "characteristics": "0xc0000080",
                                "compressed": False,
                            }
                        ],
                    },
                ],
            }
        ],
    }


def assert_clean(problems, where):
    assert not problems, f"{where}: unexpected problems: {problems}"


def assert_problem(problems, needle, where):
    joined = "\n".join(problems)
    assert needle in joined, f"{where}: expected {needle!r} in:\n{joined}"


def write_json(path: Path, doc) -> Path:
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------


@check("manifest: build and validate")
def test_manifest_build(tmp):
    root = make_corpus(tmp)
    doc = make_manifest(root)
    assert doc["schema"] == manifest.SCHEMA
    assert len(doc["corpus"]) == len(CORPUS_SPECS), doc["corpus"]
    assert_clean(manifest.validate(doc, root=root), "built manifest")

    by_path = {entry["path"]: entry for entry in doc["corpus"]}
    entry = by_path["REFER001/ADDRE001.DAT.cmp"]
    assert entry["expected"] == "ACCEPT"
    assert entry["reader"] == "cmp_ind"
    assert entry["size"] == len(CORPUS_FILES["REFER001/ADDRE001.DAT.cmp"])
    assert len(entry["sha256"]) == 64

    bad = by_path["REFER001/ADDRE001.DAT.cmp.bad-ind"]
    assert bad["expected"] == "REJECT", bad

    reloaded = json.loads(json.dumps(doc))
    assert_clean(manifest.validate(reloaded, root=root), "reloaded manifest")


@check("manifest: bad sha256 rejected")
def test_manifest_bad_sha256(tmp):
    root = make_corpus(tmp)
    doc = make_manifest(root)
    doc["corpus"][0]["sha256"] = "0" * 64
    assert_problem(
        manifest.validate(doc, root=root), "sha256 mismatch", "wrong hash"
    )

    doc = make_manifest(root)
    doc["corpus"][0]["sha256"] = "not-a-hash"
    assert_problem(
        manifest.validate(doc), "sha256 must be 64", "malformed hash"
    )


@check("manifest: unknown verdict rejected")
def test_manifest_unknown_verdict(tmp):
    root = make_corpus(tmp)
    for verdict, needle in (
        ("MAYBE", "unknown verdict"),
        ("accept", "unknown verdict"),
        (True, "unknown verdict"),
    ):
        doc = make_manifest(root)
        doc["corpus"][0]["expected"] = verdict
        assert_problem(manifest.validate(doc), needle, f"verdict {verdict!r}")

    doc = make_manifest(root)
    doc["corpus"][0]["expected"] = "REJECT"
    assert_problem(
        manifest.validate(doc), "requires verdict 'ACCEPT'", "case/verdict clash"
    )


@check("manifest: unknown reader and case rejected")
def test_manifest_unknown_reader_case(tmp):
    root = make_corpus(tmp)
    doc = make_manifest(root)
    doc["corpus"][0]["reader"] = "magic"
    assert_problem(manifest.validate(doc), "unknown reader", "unknown reader")

    doc = make_manifest(root)
    doc["corpus"][0]["case"] = "cassette"
    assert_problem(manifest.validate(doc), "unknown case", "unknown case")

    doc = make_manifest(root)
    doc["corpus"][2]["case"] = "corrupt_ind"  # tile reader, .ind case
    assert_problem(
        manifest.validate(doc), "does not apply to reader", "case/reader clash"
    )


@check("manifest: duplicates and unknown keys rejected")
def test_manifest_duplicates(tmp):
    root = make_corpus(tmp)
    doc = make_manifest(root)
    doc["corpus"].append(dict(doc["corpus"][0]))
    assert_problem(manifest.validate(doc), "duplicate id", "duplicate id")

    doc = make_manifest(root)
    clone = dict(doc["corpus"][0])
    clone["id"] = "second-id"
    doc["corpus"].append(clone)
    assert_problem(
        manifest.validate(doc), "duplicate (path, reader)", "duplicate pair"
    )

    doc = make_manifest(root)
    doc["corpus"][0]["sha_256"] = "0" * 64
    assert_problem(manifest.validate(doc), "unknown key", "typo key")


@check("manifest: missing file and build errors rejected")
def test_manifest_missing_file(tmp):
    root = make_corpus(tmp)
    doc = make_manifest(root)
    doc["corpus"][0]["path"] = "REFER001/nope.cmp"
    assert_problem(
        manifest.validate(doc, root=root), "file not found", "missing file"
    )

    assert_clean(
        manifest.validate(doc), "shape only (no root)"
    ), "shape-only validation must not need files"

    try:
        manifest.build(
            root,
            [("factory", "cmp_ind", "REFER001/missing.cmp", None)],
        )
    except manifest.ManifestError as exc:
        assert "file not found" in str(exc), exc.problems
    else:
        raise AssertionError("build accepted a missing file")

    try:
        manifest.build(
            root,
            [("corrupt_ind", "tile", "MAPAL001/B28R070R.DAT", None)],
        )
    except manifest.ManifestError as exc:
        assert "does not apply" in str(exc), exc.problems
    else:
        raise AssertionError("build accepted a case/reader mismatch")

    try:
        manifest.build(
            root, [("factory", "cmp_ind", "REFER001/ADDRE001.DAT.cmp", "REJECT")]
        )
    except manifest.ManifestError as exc:
        assert "requires verdict" in str(exc), exc.problems
    else:
        raise AssertionError("build accepted a wrong verdict")


@check("manifest: JSON schema is serialisable")
def test_manifest_schema(tmp):
    schema = manifest.json_schema()
    text = json.dumps(schema)
    assert manifest.SCHEMA in text
    assert schema["$defs"]["entry"]["required"], schema
    assert "case" in schema["$defs"]["entry"]["properties"]
    assert "reader" in schema["$defs"]["entry"]["properties"]


# --------------------------------------------------------------------------
# rommap
# --------------------------------------------------------------------------


@check("rommap: synthetic report converts")
def test_rommap_convert(tmp):
    doc = rommap.convert(make_report())
    assert doc["schema"] == rommap.SCHEMA
    assert len(doc["blocks"]) == 3, doc["blocks"]
    assert doc["source"]["image"] == (
        "LEAF_2011-2012_QSD-309-101_navi158_eu.img"
    ), "host paths must not leak into the map"
    assert doc["ram"]["start"] == "0x8c000000"
    assert doc["ram"]["end"] == "0x8c100000"
    assert doc["processor"]["verified"] is False

    by_name = {block["name"]: block for block in doc["blocks"]}
    text = by_name["Navi.exe/.text"]
    assert text["address"] == "0x8cae1000", text
    assert text["permissions"] == "r-x", text
    assert text["file_backed"] is True
    assert text["file_offset"] == "0x1000"

    rdata = by_name["Navi.exe/.rdata"]
    assert rdata["permissions"] == "r--", rdata

    bss = by_name["STDDLL.dll/.bss"]
    assert bss["file_backed"] is False, bss
    assert bss["file_offset"] is None, bss
    assert bss["permissions"] == "rw-", bss

    assert_clean(rommap.validate(doc), "converted map")
    assert_clean(
        rommap.validate(json.loads(json.dumps(doc))), "reloaded map"
    )

    text_dump = rommap.render_block_text(doc)
    assert "0x8cae1000 0x8cae3000 Navi.exe/.text r-x" in text_dump, text_dump


@check("rommap: overlapping sections rejected")
def test_rommap_overlap(tmp):
    report = make_report()
    sections = report["segments"][0]["modules"][0]["sections"]
    sections[1]["va"] = "0x8cae1800"  # inside .text
    try:
        rommap.convert(report)
    except rommap.RommapError as exc:
        text = "\n".join(exc.problems)
        assert "overlapping sections" in text, text
    else:
        raise AssertionError("overlapping sections were accepted")

    doc = rommap.convert(make_report())
    doc["blocks"][0]["end"] = doc["blocks"][1]["end"]  # now overlaps
    assert_problem(rommap.validate(doc), "overlapping sections", "doc overlap")


@check("rommap: compressed section rejected")
def test_rommap_compressed(tmp):
    report = make_report()
    section = report["segments"][0]["modules"][0]["sections"][0]
    section["characteristics"] = "0xe0002020"  # MEM_* + COMPRESSED 0x2000
    try:
        rommap.convert(report)
    except rommap.RommapError as exc:
        text = "\n".join(exc.problems)
        assert "compressed section" in text, text
        assert "decompressor" in text, text
    else:
        raise AssertionError("compressed section was accepted")

    report = make_report()
    report["segments"][0]["modules"][0]["sections"][0]["compressed"] = True
    try:
        rommap.convert(report)
    except rommap.RommapError as exc:
        assert "compressed section" in "\n".join(exc.problems)
    else:
        raise AssertionError("explicit compressed=True was accepted")

    report = make_report()
    report["segments"][0]["modules"][0]["sections"][0]["characteristics"] = (
        "0xe0002020"
    )
    doc = rommap.convert(report, skip_compressed=True)
    assert len(doc["blocks"]) == 2, doc["blocks"]
    assert len(doc["skipped"]) == 1, doc["skipped"]
    assert "compressed" in doc["skipped"][0]["reason"].lower()
    assert_clean(rommap.validate(doc), "map with a skipped section")


@check("rommap: zero-size, empty and out-of-range rejected")
def test_rommap_bad_structure(tmp):
    report = make_report()
    report["segments"][0]["modules"][0]["sections"][0]["size"] = 0
    try:
        rommap.convert(report)
    except rommap.RommapError as exc:
        assert "size must be positive" in "\n".join(exc.problems)
    else:
        raise AssertionError("zero-size section was accepted")

    try:
        rommap.convert({"segments": []})
    except rommap.RommapError as exc:
        assert "no segments" in "\n".join(exc.problems)
    else:
        raise AssertionError("empty report was accepted")

    try:
        rommap.convert(make_report(), segment=5)
    except rommap.RommapError as exc:
        assert "out of range" in "\n".join(exc.problems)
    else:
        raise AssertionError("bad segment index was accepted")

    report = make_report()
    report["segments"][0]["modules"][0]["sections"][1]["file_offset"] = 0xF800
    try:
        rommap.convert(report)
    except rommap.RommapError as exc:
        assert "outside the image" in "\n".join(exc.problems)
    else:
        raise AssertionError("out-of-image file range was accepted")


# --------------------------------------------------------------------------
# stubs
# --------------------------------------------------------------------------


@check("stubs: table is complete and valid")
def test_stubs_table(tmp):
    assert_clean(stubs.validate(), "stub table")
    names = set(stubs.names())
    for required in stubs.REQUIRED_STUBS:
        assert required in names, f"missing stub {required}"

    for reader, wanted in stubs.READER_STUBS.items():
        assert reader in manifest.READERS, f"unknown reader id {reader}"
        for name in wanted:
            assert name in names, f"{reader} needs unknown stub {name}"
            entry = stubs.by_name(name)
            assert entry["status"] in stubs.STATUSES

    for reader in manifest.READERS:
        assert reader in stubs.READER_STUBS, f"no stub list for {reader}"

    broken = [dict(stub) for stub in stubs.STUBS]
    broken[0]["side_effects"] = []
    assert_problem(stubs.validate(broken), "side_effects", "empty side effects")

    broken = [dict(stub) for stub in stubs.STUBS]
    broken[0]["status"] = "wishful"
    assert_problem(stubs.validate(broken), "status must be one of", "bad status")


@check("stubs: JSON schema is serialisable")
def test_stubs_schema(tmp):
    schema = stubs.json_schema()
    text = json.dumps(schema)
    assert stubs.SCHEMA in text
    assert schema["$defs"]["stub"]["properties"]["binding"]["enum"]
    payload = json.dumps(stubs.document())
    assert "CreateFileW" in payload and "OSM_LogMsg" in payload


# --------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------


def runner_fixtures(tmp):
    root = make_corpus(tmp)
    manifest_path = write_json(Path(tmp) / "manifest.json", make_manifest(root))
    rommap_path = write_json(Path(tmp) / "rommap.json", rommap.convert(make_report()))
    return root, manifest_path, rommap_path


def run_cli(argv):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        code = runner.main(argv)
    return code, buffer.getvalue()


@check("runner: check passes on valid inputs")
def test_runner_check(tmp):
    root, manifest_path, rommap_path = runner_fixtures(tmp)
    code, output = run_cli(
        ["check", "--manifest", str(manifest_path), "--rommap", str(rommap_path),
         "--root", str(root)]
    )
    assert code == runner.EXIT_OK, output
    assert "RESULT: PASS" in output, output

    code, output = run_cli(
        ["check", "--manifest", str(manifest_path), "--rommap", str(rommap_path)]
    )
    assert code == runner.EXIT_OK, output
    assert "not verified" in output, output


@check("runner: check fails on a bad manifest")
def test_runner_check_bad(tmp):
    root, manifest_path, rommap_path = runner_fixtures(tmp)
    doc = manifest.load(manifest_path)
    doc["corpus"][0]["sha256"] = "0" * 64
    write_json(manifest_path, doc)
    code, output = run_cli(
        [
            "check",
            "--manifest",
            str(manifest_path),
            "--rommap",
            str(rommap_path),
            "--root",
            str(root),
        ]
    )
    assert code == runner.EXIT_INVALID, output
    assert "sha256 mismatch" in output, output
    assert "RESULT: FAIL" in output, output


@check("runner: plan reports blockers")
def test_runner_plan(tmp):
    _, manifest_path, rommap_path = runner_fixtures(tmp)
    code, output = run_cli(
        ["plan", "--manifest", str(manifest_path), "--rommap", str(rommap_path)]
    )
    assert code == runner.EXIT_OK, output
    assert "trace targets:" in output, output
    assert "UNKNOWN (no runnable entry point)" in output, output
    assert "first real run needs:" in output, output
    assert "is not claimed" in output, output


@check("runner: missing Ghidra exits 3, never 0")
def test_runner_missing_ghidra(tmp):
    _, manifest_path, rommap_path = runner_fixtures(tmp)
    env = {
        "PATH": "",
        "HOME": str(Path(tmp) / "no-home"),
        "GHIDRA_INSTALL_DIR": "",
        "GHIDRA_HOME": "",
    }
    saved_roots = runner.DEFAULT_SEARCH_ROOTS
    runner.DEFAULT_SEARCH_ROOTS = ()
    try:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = runner.main(
                [
                    "run",
                    "--manifest",
                    str(manifest_path),
                    "--rommap",
                    str(rommap_path),
                ],
                env=env,
            )
        output = buffer.getvalue()
    finally:
        runner.DEFAULT_SEARCH_ROOTS = saved_roots

    assert code == runner.EXIT_MISSING_GHIDRA, f"{code}: {output}"
    assert "MISSING_GHIDRA" in output, output
    assert "GHIDRA_INSTALL_DIR" in output, output
    assert "never 0" in output, output


@check("runner: Ghidra without a harness script blocks (exit 4)")
def test_runner_blocked(tmp):
    _, manifest_path, rommap_path = runner_fixtures(tmp)
    fake = Path(tmp) / "analyzeHeadless"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(0o755)
    saved_script = runner.HARNESS_SCRIPT
    runner.HARNESS_SCRIPT = Path(tmp) / "ghidra" / "l3_run.py"
    try:
        code, output = run_cli(
            [
                "run",
                "--manifest",
                str(manifest_path),
                "--rommap",
                str(rommap_path),
                "--headless",
                str(fake),
            ]
        )
    finally:
        runner.HARNESS_SCRIPT = saved_script
    assert code == runner.EXIT_BLOCKED, f"{code}: {output}"
    assert "BLOCKED" in output, output
    assert "no pass is claimed" in output, output


@check("runner: result comparison cannot fake a pass")
def test_runner_compare(tmp):
    doc = {
        "corpus": [
            {"id": "a", "expected": "ACCEPT"},
            {"id": "b", "expected": "REJECT"},
        ]
    }
    assert runner._compare_result(doc, {"cases": []}) == [
        "a: no verdict in the harness result",
        "b: no verdict in the harness result",
    ]
    assert runner._compare_result(
        doc,
        {
            "cases": [
                {"id": "a", "verdict": "ACCEPT"},
                {"id": "b", "verdict": "ACCEPT"},
            ]
        },
    ) == ["b: harness 'ACCEPT', manifest 'REJECT'"]
    assert runner._compare_result(
        doc,
        {
            "cases": [
                {"id": "a", "verdict": "ACCEPT"},
                {"id": "b", "verdict": "REJECT"},
            ]
        },
    ) == []


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--selftest":
        argv = argv[1:]

    failures = 0
    for name, func in CHECKS:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                func(tmp)
            except Exception as exc:  # noqa: BLE001 - report, do not abort
                failures += 1
                print(f"FAIL {name}: {exc}")
                if os.environ.get("L3_SELFTEST_VERBOSE"):
                    traceback.print_exc()
            else:
                print(f"ok   {name}")

    print()
    if failures:
        print(f"selftest: FAILED ({failures}/{len(CHECKS)} checks)")
        return 1
    print(f"selftest: OK ({len(CHECKS)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
