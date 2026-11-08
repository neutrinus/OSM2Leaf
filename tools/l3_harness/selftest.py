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
import hashlib
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


# --------------------------------------------------------------------------
# module entries (M9.20): call a function at a memory-map VA, no loader list
# --------------------------------------------------------------------------

MODULE_VA = 0x8C300000
#: SH-4 big-endian: add #1,r4 / mov r4,r0 / rts / nop  (r0 = arg + 1)
MODULE_CODE = [0x7401, 0x6043, 0x000B, 0x0009]


def module_target(entry=None, **top) -> dict:
    block = {
        "kind": "module",
        "module": "Module.bin",
        "va": hex(MODULE_VA),
        "endian": "big",
        "args": ["0x41"],
        "verdict_map": {"0x42": "ACCEPT"},
    }
    if entry:
        block.update(entry)
    target = {
        "name": "module-probe",
        "reader": "synthetic",
        "what": "synthetic module function: r0 = r4 + 1",
        "entry": block,
        "stubs": [],
        "expect": {"verdict": "ACCEPT", "rule": "r0 = arg + 1 maps to ACCEPT"},
    }
    target.update(top)
    return target


def module_fixture(tmp, target=None, code_endian="big") -> dict:
    """A synthetic image, its memory map and a targets file that names it."""

    root = Path(tmp)
    image = bytearray(0x2000)
    for index, word in enumerate(MODULE_CODE):
        image[0x1000 + 2 * index:0x1002 + 2 * index] = word.to_bytes(2, code_endian)
    image_path = root / "synthetic-module.img"
    image_path.write_bytes(bytes(image))
    report = {
        "image": "/vendor/synthetic-module.img",
        "image_size": len(image),
        # like cerom.py: a window hash, with its scope text (real EU head:
        # "first 134217728 of 268435456 bytes")
        "image_sha256": hashlib.sha256(bytes(image[:0x1000])).hexdigest(),
        "image_sha256_scope": "first 4096 of 8192 bytes",
        "segments": [
            {
                "segment_base": "0x0",
                "phys_base": hex(MODULE_VA),
                "romhdr": {
                    "physfirst": hex(MODULE_VA),
                    "physlast": hex(MODULE_VA + 0x2000),
                    "ulRAMStart": "0x8c000000",
                    "ulRAMEnd": "0x8c100000",
                    "nummods": 1,
                    "numfiles": 0,
                    "usCPUType": 0x01A6,
                },
                "modules": [
                    {
                        "name": "Module.bin",
                        "vbase": hex(MODULE_VA),
                        "sections": [
                            {"name": ".text", "va": hex(MODULE_VA), "file_offset": 0x1000,
                             "size": 0x1000, "characteristics": "0x60000020", "compressed": False},
                            {"name": ".data", "va": hex(MODULE_VA + 0x1000), "file_offset": 0x0,
                             "size": 0x1000, "characteristics": "0xc0000040", "compressed": False},
                            {"name": ".zdata", "va": hex(MODULE_VA + 0x2000), "file_offset": 0x0,
                             "size": 0x1000, "characteristics": "0x60000020", "compressed": True},
                        ],
                    }
                ],
            }
        ],
    }
    # skip_compressed keeps .zdata out of the map but records it in "skipped"
    rommap_path = write_json(
        root / "rommap.json", rommap.convert(report, skip_compressed=True)
    )
    targets_path = write_json(
        root / "targets.json",
        {"schema": runner.TARGETS_SCHEMA, "targets": [target or module_target()]},
    )
    return {
        "image": image_path,
        "rommap": rommap_path,
        "targets": targets_path,
        "sha256": report["image_sha256"],
        "root": root,
    }


def run_json(argv) -> tuple[int, dict]:
    code, output = run_cli(argv)
    return code, json.loads(output)


def module_argv(fx, name="module-probe", *extra) -> list[str]:
    return [
        "run", name, "--targets", str(fx["targets"]), "--rommap", str(fx["rommap"]),
        "--image", str(fx["image"]), "--json", *extra,
    ]


@check("module entry: validation accepts a valid block and refuses bad ones")
def test_module_validate(tmp):
    good = {"schema": runner.TARGETS_SCHEMA, "targets": [module_target()]}
    assert runner.validate_targets(good) == [], runner.validate_targets(good)
    cases = [
        ({"endian": "mixed"}, "must be one of"),
        ({"args": ["0x1"] * 5}, "at most 4"),
        ({"verdict_map": None}, "verdict_map"),
        ({"verdict_map": {"0x42": "MAYBE"}}, "ACCEPT or REJECT"),
        ({"verdict_map": {"0x42": "ACCEPT", "66": "REJECT"}}, "repeats"),
        ({"tile": 1}, "unknown entry key"),
        ({"va": None}, "needs a va"),
        ({"module": ""}, "module name"),
    ]
    for overrides, needle in cases:
        doc = {"schema": runner.TARGETS_SCHEMA,
               "targets": [module_target(entry=overrides)]}
        problems = " | ".join(runner.validate_targets(doc))
        assert needle in problems, f"{overrides}: wanted {needle!r}, got {problems!r}"


@check("module entry: a function from the memory map runs and passes (control)")
def test_module_run_pass(tmp):
    fx = module_fixture(tmp)
    code, payload = run_json(module_argv(fx))
    assert code == runner.EXIT_OK, payload
    assert payload["status"] == "PASS", payload
    assert int(payload["returned"], 0) == 0x42, payload
    assert payload["verdict"] == "ACCEPT" and payload["accepted"] is True
    assert payload["rommap"]["blocks_mapped"] == ["Module.bin/.text", "Module.bin/.data"]
    assert payload["rommap"]["image_sha256_checked"] is True
    assert payload["l3_claim"] is False


@check("module entry: little-endian code runs on PySh4(endian=little); big-endian code does not")
def test_module_run_endianness(tmp):
    little_target = module_target(entry={"endian": "little"})
    fx = module_fixture(tmp, little_target, code_endian="little")
    code, payload = run_json(module_argv(fx))
    assert code == runner.EXIT_OK and payload["status"] == "PASS", payload
    assert int(payload["returned"], 0) == 0x42, payload
    assert payload["engine_kind"] == "interpreter", payload

    # The same entry over big-endian bytes: the words decode differently, so
    # the function cannot return arg + 1 (control: the byte order matters).
    be_dir = Path(tmp) / "be"
    be_dir.mkdir()
    fx = module_fixture(str(be_dir), little_target, code_endian="big")
    code, payload = run_json(module_argv(fx))
    assert payload["status"] != "PASS", payload
    assert code != runner.EXIT_OK, payload

    # A back end that is big-endian in this harness refuses little-endian code
    # before it starts (Ghidra is absent here, so the refusal comes first).
    code, payload = run_json(module_argv(fx, "module-probe", "--engine", "ghidra"))
    assert code == runner.EXIT_BLOCKED and "needs the pysh4 engine" in payload["reason"], payload


@check("module entry: a wrong expectation is MISMATCH (exit 5)")
def test_module_run_mismatch(tmp):
    fx = module_fixture(tmp, module_target(entry={"verdict_map": {"0x42": "REJECT"}}))
    code, payload = run_json(module_argv(fx))
    assert code == runner.EXIT_MISMATCH and payload["status"] == "MISMATCH", payload


@check("module entry: an unmapped r0 is BLOCKED, never a guessed verdict")
def test_module_run_unmapped_r0(tmp):
    fx = module_fixture(tmp, module_target(entry={"verdict_map": {"0x43": "ACCEPT"}}))
    code, payload = run_json(module_argv(fx))
    assert code == runner.EXIT_BLOCKED and payload["status"] == "BLOCKED", payload
    assert "no verdict is guessed" in payload["reason"], payload
    assert payload["accepted"] is None


@check("module entry: a VA outside the map or in a non-executable block is BLOCKED")
def test_module_run_bad_va(tmp):
    for va, needle in [(0x8C400000, "outside every loadable block"),
                       (MODULE_VA + 0x1000, "not executable"),
                       (MODULE_VA + 0x2000, "compressed section Module.bin/.zdata")]:
        fx = module_fixture(tmp, module_target(entry={"va": hex(va)}))
        code, payload = run_json(module_argv(fx))
        assert code == runner.EXIT_BLOCKED, payload
        assert needle in payload["reason"], payload


@check("module entry: an image that is not the mapped image is INVALID (exit 1)")
def test_module_run_wrong_image(tmp):
    fx = module_fixture(tmp)
    doc = json.loads(fx["rommap"].read_text(encoding="utf-8"))
    assert doc["source"]["image_sha256"] == fx["sha256"], "map must carry the image hash"
    assert doc["source"]["image_sha256_scope"] == "first 4096 of 8192 bytes", doc["source"]
    cases = [
        ("image_sha256", "b" * 64, "the map was made from another image"),
        ("image_sha256_scope", "about half the file", "no recognised"),
        ("image_sha256_scope", "first 4096 of 999999 bytes", "covers a 999999-byte image"),
    ]
    for key, value, needle in cases:
        doc = json.loads(fx["rommap"].read_text(encoding="utf-8"))
        doc["source"][key] = value
        write_json(fx["rommap"], doc)
        code, payload = run_json(module_argv(fx))
        assert code == runner.EXIT_INVALID and payload["status"] == "INVALID", payload
        assert needle in " ".join(payload["problems"]), payload
        assert payload.get("returned") is None, "a refused image must not run"


@check("module entry: no --rommap/--image is BLOCKED; Ghidra absent is SKIP, not PASS")
def test_module_run_inputs_and_engine(tmp):
    fx = module_fixture(tmp)
    code, payload = run_json(["run", "module-probe", "--targets", str(fx["targets"]),
                              "--json"])
    assert code == runner.EXIT_BLOCKED and "needs --rommap" in payload["reason"], payload
    code, payload = run_json(module_argv(fx, "module-probe", "--engine", "ghidra"))
    assert code == runner.EXIT_SKIP and payload["status"] == "SKIP", payload
    assert payload["l3_claim"] is False


@check("module entry: --dry-run names the entry and starts no engine")
def test_module_dry_run(tmp):
    fx = module_fixture(tmp)
    code, payload = run_json(module_argv(fx, "module-probe", "--dry-run"))
    assert code == runner.EXIT_OK and payload["status"] == "DRY_RUN", payload
    assert payload["module_entry"]["module"] == "Module.bin", payload
    assert "engine_status" not in payload, payload


@check("dispatch: engine_hook argument and call checks (dispatch.py CHECKS)")
def test_engine_hook_checks(tmp):
    from l3_harness import dispatch as dispatch_mod

    hooks = [(name, func) for name, func in dispatch_mod.CHECKS if "engine_hook" in name]
    assert len(hooks) == 3, [name for name, _ in hooks]
    for _name, func in hooks:
        func(tmp)  # each raises on failure


@check("module entry: targets listing and dry run work without a corpus block")
def test_module_listing_without_corpus(tmp):
    fx = module_fixture(tmp)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        code = runner.main(["targets", "--targets", str(fx["targets"])])
    assert code == runner.EXIT_OK, buffer.getvalue()
    assert "module-probe" in buffer.getvalue(), buffer.getvalue()


@check("ghidra entry script: its own selftest (exit 1/2 controls, namespace probe)")
def test_entry_script_selftest(tmp):
    from l3_harness.ghidra import l3_run

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        code = l3_run.selftest()
    assert code == 0, buffer.getvalue()


@check("ghidra entry script: a BLOCKED result is read back as BLOCKED (exit 4)")
def test_legacy_entry_script(tmp):
    _, manifest_path, rommap_path = runner_fixtures(tmp)
    image = Path(tmp) / "fw.img"
    image.write_bytes(b"\x00" * 16)
    # A stand-in for analyzeHeadless that runs the entry script's function on
    # the last three arguments, exactly as ghidra/l3_run.py receives them.
    fake = Path(tmp) / "analyzeHeadless"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        f"sys.path.insert(0, {str(TOOLS_DIR)!r})\n"
        "from l3_harness.ghidra import l3_run\n"
        "sys.exit(l3_run.run(sys.argv[-3:]))\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    result = Path(tmp) / "result.json"
    code, payload = run_json([
        "run", "--manifest", str(manifest_path), "--rommap", str(rommap_path),
        "--image", str(image), "--headless", str(fake),
        "--project-dir", str(Path(tmp) / "proj"), "--result", str(result), "--json",
    ])
    assert code == runner.EXIT_BLOCKED and payload["status"] == "BLOCKED", payload
    written = json.loads(result.read_text(encoding="utf-8"))
    assert written["status"] == "BLOCKED" and written["cases"] == [], written
    assert "no located reader" in payload["reason"], payload


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
