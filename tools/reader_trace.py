#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""reader_trace.py - one JSON record for a reader call made through firmware code.

L3 tools print a reader's outcome each in its own shape (`mmain_l3.py` cases,
`drstr_l3.py` run/controls), and the L4 parity work (M8.H11) will add another.
This tool defines the record they share (M9.69) so two runs of the same reader,
or two readers on the same file, can be compared field by field and listed in
the M9.62 manifest without per-tool parsing:

    {"schema": "osm2leaf.reader_trace/v1",
     "producer": "mmain_l3",          # the tool that made the call
     "build": "eu2011",               # the firmware build the VA belongs to
     "module": "Navi.exe",            # optional; the module holding `function`
     "function": "0x0041a438",        # the reader entry point that was called
     "arguments": {...},              # what the call was given (input hash, case, ...)
     "reads": [{"file": "MMAIN001.DAT", "offset": 0, "length": 4096, "got": 4096}],
     "result": {"verdict": "ACCEPT", "r0": null, "stage": null,
                "log_codes": [], "reason": null,
                "checks": {"buffer_sha256": "…", "buffer_equals_swap16": true}},
     "environment": {...}}            # optional; imports, engine note

`reads` is the card access log attributed to the call (file, byte offset, asked,
got), so a run that reads different bytes is DIFFERENT even with one verdict.
`result` is the reader's own outcome; `verdict` is required and one of ACCEPT,
REJECT, BLOCKED. `result.checks` is an optional object of the tool's own
derived assertions (a hash of what the firmware held, a boolean comparison)
with scalar values, so a reader that copies different bytes under the same
verdict is still DIFFERENT between two runs. Unknown top-level keys are
tolerated (a later L4 producer may add fields); the `reads` and `result`
objects are strict so one concept cannot hide under two names.

Usage:
  reader_trace.py --selftest
  reader_trace.py validate FILE [FILE ...]
  reader_trace.py compare A.json B.json

A trace file holds one record or a JSON array of records (one entry per reader
call). `validate` accepts every record; `compare` compares record i of A with
record i of B and requires two equal-length files.

Exit codes: validate: 0 every record accepted, 1 a record or file is invalid;
compare: 0 SAME, 1 DIFFERENT; 2 usage.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
import tempfile
from pathlib import Path

SCHEMA = "osm2leaf.reader_trace/v1"
VERDICTS = ("ACCEPT", "REJECT", "BLOCKED")
READ_KEYS = ("file", "offset", "length", "got")
RESULT_KEYS = ("verdict", "r0", "stage", "log_codes", "reason", "checks")
TOP_REQUIRED = ("schema", "producer", "build", "function", "arguments", "reads", "result")
COMPARE_KEYS = ("producer", "build", "module", "function", "arguments",
                "environment", "reads", "result")

_FUNCTION_RE = re.compile(r"^0x[0-9a-fA-F]{8}$")


class TraceError(ValueError):
    """A record does not satisfy the schema; the message names every problem."""


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def check_record(doc) -> list[str]:
    """Return every way *doc* differs from the schema (empty list = accepted)."""
    if not isinstance(doc, dict):
        return ["record is not a JSON object"]
    problems: list[str] = []
    for key in TOP_REQUIRED:
        if key not in doc:
            problems.append("missing %s" % key)
    if "schema" in doc and doc["schema"] != SCHEMA:
        problems.append("schema is %r, want %r" % (doc["schema"], SCHEMA))
    for key in ("producer", "build"):
        value = doc.get(key)
        if key in doc and (not isinstance(value, str) or not value):
            problems.append("%s must be a non-empty string" % key)
    function = doc.get("function")
    if "function" in doc:
        if not isinstance(function, str) or not _FUNCTION_RE.match(function):
            problems.append("function %r is not a 0x + 8 hex digit VA" % (function,))
    if "module" in doc and doc["module"] is not None and not isinstance(doc["module"], str):
        problems.append("module must be a string or null")
    if "arguments" in doc and not isinstance(doc["arguments"], dict):
        problems.append("arguments must be an object")
    if "environment" in doc and not isinstance(doc["environment"], dict):
        problems.append("environment must be an object")
    if "reads" in doc:
        problems.extend(_read_problems(doc["reads"]))
    if "result" in doc:
        problems.extend(_result_problems(doc["result"]))
    return problems


def _read_problems(reads) -> list[str]:
    if not isinstance(reads, list):
        return ["reads must be a list"]
    problems: list[str] = []
    for index, read in enumerate(reads):
        where = "reads[%d]" % index
        if not isinstance(read, dict):
            problems.append("%s is not an object" % where)
            continue
        missing = [key for key in READ_KEYS if key not in read]
        if missing:
            problems.append("%s: missing %s" % (where, ", ".join(missing)))
        extra = sorted(set(read) - set(READ_KEYS))
        if extra:
            problems.append("%s: unknown key(s) %s" % (where, ", ".join(extra)))
        name = read.get("file")
        if "file" in read and (not isinstance(name, str) or not name):
            problems.append("%s: file must be a non-empty string" % where)
        for key in ("offset", "length", "got"):
            if key not in read:
                continue
            value = read[key]
            if not _is_int(value) or value < 0:
                problems.append("%s: %s must be a non-negative integer, not %r"
                                % (where, key, value))
    return problems


def _result_problems(result) -> list[str]:
    if not isinstance(result, dict):
        return ["result must be an object"]
    problems: list[str] = []
    if "verdict" not in result:
        problems.append("result: missing verdict")
    elif result["verdict"] not in VERDICTS:
        problems.append("result.verdict %r is not one of %s"
                        % (result["verdict"], ", ".join(VERDICTS)))
    extra = sorted(set(result) - set(RESULT_KEYS))
    if extra:
        problems.append("result: unknown key(s) %s" % ", ".join(extra))
    for key in ("r0", "stage", "reason"):
        value = result.get(key)
        if key in result and value is not None and not isinstance(value, str):
            problems.append("result.%s must be a string or null" % key)
    if "log_codes" in result:
        codes = result["log_codes"]
        if not isinstance(codes, list) or not all(_is_int(code) for code in codes):
            problems.append("result.log_codes must be a list of integers")
    if "checks" in result:
        checks = result["checks"]
        if not isinstance(checks, dict):
            problems.append("result.checks must be an object")
        else:
            for key, value in checks.items():
                if not isinstance(key, str) or not key:
                    problems.append("result.checks has a non-string key %r" % (key,))
                if not (value is None or isinstance(value, (bool, int, str))):
                    problems.append("result.checks[%r] must be a scalar" % key)
    return problems


def _as_read(read) -> dict:
    if isinstance(read, dict):
        return read
    try:
        file, offset, length, got = read
    except (TypeError, ValueError):
        raise TraceError("a read must be a 4-tuple or an object, not %r" % (read,)) from None
    return {"file": file, "offset": offset, "length": length, "got": got}


def record(*, producer: str, build: str, function: str, arguments: dict,
           reads, result: dict, module: str | None = None,
           environment: dict | None = None, schema: str = SCHEMA) -> dict:
    """Build one schema-valid record; raise TraceError with every problem."""
    doc = {
        "schema": schema,
        "producer": producer,
        "build": build,
        "function": function,
        "arguments": arguments,
        "reads": [_as_read(read) for read in reads],
        "result": dict(result),
    }
    if module is not None:
        doc["module"] = module
    if environment is not None:
        doc["environment"] = environment
    problems = check_record(doc)
    if problems:
        raise TraceError("; ".join(problems))
    return doc


def from_mmain_l3(row: dict, *, build: str, function: str,
                  path: str = "MMAIN001.DAT", module: str = "Navi.exe",
                  producer: str = "mmain_l3") -> dict:
    """Adapter for one ``tools/mmain_l3.py run`` case row."""
    reads = [(path, offset, asked, got) for offset, asked, got in row.get("mmain_reads") or []]
    checks = {key: row.get(key) for key in
              ("buffer_sha256", "buffer_equals_swap16", "python_model_equal")
              if row.get(key) is not None}
    return record(
        producer=producer, build=build, module=module, function=function,
        arguments={"case": row.get("case"), "guest_path": "\\SystemSD\\" + path,
                   "input_sha256": row.get("served_sha256"),
                   "input_size": row.get("served_bytes")},
        reads=reads,
        result={"verdict": row.get("verdict"), "reason": row.get("why") or None,
                "checks": checks},
    )


def from_drstr_l3(out: dict, *, input_sha256: str | None = None,
                  input_size: int | None = None, arguments: dict | None = None,
                  reads=None, build: str | None = None, function: str | None = None,
                  module: str = "Navi.exe", producer: str = "drstr_l3") -> dict:
    """Adapter for ``tools/drstr_l3.py run`` output (or a BLOCKED stub of it)."""
    args = {"guest_path": out.get("guest_path"), "mode": out.get("mode"),
            "input_sha256": input_sha256, "input_size": input_size}
    if arguments:
        args.update(arguments)
    result = {"verdict": out.get("verdict"), "r0": out.get("r0"),
              "stage": out.get("stage"), "log_codes": out.get("log_codes") or [],
              "reason": out.get("reason") if out.get("verdict") == "BLOCKED" else None}
    environment = {}
    if out.get("imports") is not None:
        environment["imports"] = list(out["imports"])
    if out.get("insns_note") is not None:
        environment["insns_note"] = out["insns_note"]
    return record(
        producer=producer,
        build=build or out.get("build"),
        function=function or out.get("fn"),
        module=module,
        arguments=args,
        reads=out.get("reads") or [] if reads is None else reads,
        result=result,
        environment=environment or None,
    )


def load_records(path) -> list[dict]:
    """Read a trace file: one record object or a JSON array of records."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise TraceError("cannot read %s: %s" % (path, exc)) from None
    except json.JSONDecodeError as exc:
        raise TraceError("%s is not JSON: %s" % (path, exc)) from None
    if isinstance(doc, dict):
        return [doc]
    if isinstance(doc, list):
        return doc
    raise TraceError("%s is not a record object or an array of records" % path)


def validate_file(path) -> list[str]:
    """Return every schema problem in *path* (empty list = accepted)."""
    try:
        records = load_records(path)
    except TraceError as exc:
        return [str(exc)]
    if not records:
        return ["%s has no records" % path]
    problems: list[str] = []
    for index, doc in enumerate(records):
        for problem in check_record(doc):
            problems.append("records[%d]: %s" % (index, problem))
    return problems


def write_trace(path, records) -> None:
    """Validate every record, then write the JSON array (UTF-8, newline)."""
    records = list(records)
    if not records:
        raise TraceError("refusing to write a trace with no records")
    problems: list[str] = []
    for index, doc in enumerate(records):
        for problem in check_record(doc):
            problems.append("records[%d]: %s" % (index, problem))
    if problems:
        raise TraceError("; ".join(problems))
    Path(path).write_text(json.dumps(records, indent=1) + "\n", encoding="utf-8")


def compare_records(left: dict, right: dict) -> list[str]:
    """Names of the record fields that differ (empty list = SAME)."""
    return [key for key in COMPARE_KEYS if left.get(key) != right.get(key)]


def compare_files(path_a, path_b) -> list[str]:
    """Compare two trace files record by record; return the differing fields."""
    left, right = load_records(path_a), load_records(path_b)
    if len(left) != len(right):
        return ["record count (%d vs %d)" % (len(left), len(right))]
    problems: list[str] = []
    for index, (a, b) in enumerate(zip(left, right)):
        for key in compare_records(a, b):
            problems.append("[%d] %s" % (index, key))
    return problems


# ---------------------------------------------------------------------------
# CLI
def cmd_validate(args) -> int:
    bad = 0
    for path in args.files:
        problems = validate_file(path)
        if problems:
            bad += 1
            for problem in problems:
                print("FAIL %s: %s" % (path, problem))
        else:
            print("OK   %s (%d record(s))" % (path, len(load_records(path))))
    return 1 if bad else 0


def cmd_compare(args) -> int:
    try:
        problems = compare_files(args.left, args.right)
    except TraceError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if problems:
        print("DIFFERENT: " + ", ".join(problems))
        return 1
    print("SAME")
    return 0


def selftest() -> int:
    failures, checks = [], 0

    def check(name, condition):
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(name)
            print("FAIL %s" % name)
        else:
            print("PASS %s" % name)

    def problems(doc):
        return check_record(doc)

    good = record(
        producer="selftest", build="eu2011", module="Navi.exe", function="0x0041a438",
        arguments={"case": "factory", "input_sha256": "a" * 64, "input_size": 4096},
        reads=[("MMAIN001.DAT", 0, 4096, 4096)],
        result={"verdict": "ACCEPT"},
    )
    check("record: a complete record is accepted", problems(good) == [])

    for key in TOP_REQUIRED:
        broken = dict(good)
        del broken[key]
        check("missing %s is rejected" % key, any(key in p for p in problems(broken)))
    check("a non-object is rejected", problems(["not a record"]) != [])
    check("a wrong schema is rejected",
          any("schema" in p for p in problems(dict(good, schema="x"))))
    check("a build that is not a string is rejected",
          any("build" in p for p in problems(dict(good, build=2011))))
    for bad_function in ("0x41a438", "0041a438", "0x0041a43g", 0x0041A438):
        check("function %r is rejected" % (bad_function,),
              any("function" in p for p in problems(dict(good, function=bad_function))))
    check("arguments that are not an object are rejected",
          any("arguments" in p for p in problems(dict(good, arguments=[]))))
    check("a verdict outside the map is rejected",
          any("verdict" in p for p in problems(dict(good, result={"verdict": "OK"}))))
    check("a missing verdict is rejected",
          any("verdict" in p for p in problems(dict(good, result={}))))
    check("an unknown result key is rejected",
          any("unknown" in p for p in problems(dict(good, result={"verdict": "ACCEPT",
                                                                 "extra": 1}))))
    check("log_codes that are not integers are rejected",
          any("log_codes" in p for p in problems(dict(good, result={"verdict": "ACCEPT",
                                                                   "log_codes": ["x"]}))))
    check("checks that are not an object are rejected",
          any("checks" in p for p in problems(dict(good, result={"verdict": "ACCEPT",
                                                                 "checks": []}))))
    check("a non-scalar check value is rejected",
          any("checks" in p for p in problems(dict(good, result={
              "verdict": "ACCEPT", "checks": {"nested": {"x": 1}}}))))
    check("a read without got is rejected",
          any("got" in p for p in problems(dict(good, reads=[
              {"file": "a", "offset": 0, "length": 1}]))))
    check("a read with an unknown key is rejected",
          any("unknown" in p for p in problems(dict(good, reads=[
              {"file": "a", "offset": 0, "length": 1, "got": 1, "kind": 1}]))))
    check("a negative read offset is rejected",
          any("offset" in p for p in problems(dict(good, reads=[
              {"file": "a", "offset": -1, "length": 1, "got": 1}]))))
    check("a boolean read length is rejected",
          any("length" in p for p in problems(dict(good, reads=[
              {"file": "a", "offset": 0, "length": True, "got": 1}]))))

    mmain_row = {
        "case": "factory", "verdict": "ACCEPT", "expect": "ACCEPT",
        "served_bytes": 4096, "served_sha256": "b" * 64,
        "mmain_reads": [[0, 4096, 4096]], "buffer_sha256": "c" * 64,
        "buffer_equals_swap16": True, "python_model_equal": True, "ok": True, "why": "",
    }
    mmain_blocked = dict(mmain_row, verdict="BLOCKED", mmain_reads=[],
                         why="BLOCKED: no engine")
    mmain_record = from_mmain_l3(mmain_row, build="eu2011", function="0x0041a438")
    check("adapter mmain_l3: a case row becomes a valid record", problems(mmain_record) == [])
    check("adapter mmain_l3: the read keeps file, offset, asked and got",
          mmain_record["reads"] == [{"file": "MMAIN001.DAT", "offset": 0,
                                     "length": 4096, "got": 4096}])
    check("adapter mmain_l3: the case and input hash are arguments",
          mmain_record["arguments"]["case"] == "factory"
          and mmain_record["arguments"]["input_sha256"] == "b" * 64)
    check("adapter mmain_l3: the buffer hash and comparisons are checks",
          mmain_record["result"]["checks"] == {
              "buffer_sha256": "c" * 64, "buffer_equals_swap16": True,
              "python_model_equal": True})
    rebuilt_row = dict(mmain_row, case="rebuilt", served_sha256="e" * 64,
                       buffer_sha256="f" * 64)
    rebuilt_record = from_mmain_l3(rebuilt_row, build="eu2011", function="0x0041a438")
    falsifier_diffs = compare_records(mmain_record, rebuilt_record)
    check("falsifier: two ACCEPT cases with the same read differ (input/buffer hash)",
          mmain_record["result"]["verdict"] == rebuilt_record["result"]["verdict"]
          and mmain_record["reads"] == rebuilt_record["reads"]
          and "arguments" in falsifier_diffs and "result" in falsifier_diffs)
    check("adapter mmain_l3: a BLOCKED row keeps its reason",
          from_mmain_l3(mmain_blocked, build="eu2011", function="0x0041a438")
          ["result"]["reason"] == "BLOCKED: no engine")
    check("adapter mmain_l3: a row with no verdict is refused",
          _raises(lambda: from_mmain_l3(dict(mmain_row, verdict=None),
                                        build="eu2011", function="0x0041a438")))

    drstr_out = {
        "build": "eu2011", "fn": "0x00419350", "guest_path": "\\SystemSD\\DRSTR001.DAT",
        "mode": "rb", "fd": "0x6f000000", "verdict": "ACCEPT", "stage": "parse",
        "r0": "0x00000000", "log_codes": [], "log_sites": [],
        "reads": [["DRSTR001.DAT", 0, 11968, 11968]],
        "imports": ["fopen", "fread"], "insns_note": "PySh4, vcard_l3 import models",
    }
    drstr_record = from_drstr_l3(drstr_out, input_sha256="d" * 64, input_size=11968)
    check("adapter drstr_l3: a run result becomes a valid record", problems(drstr_record) == [])
    check("adapter drstr_l3: function, r0 and stage are kept",
          (drstr_record["function"], drstr_record["result"]["r0"],
           drstr_record["result"]["stage"]) == ("0x00419350", "0x00000000", "parse"))
    check("adapter drstr_l3: imports stay in environment, not result",
          drstr_record["environment"]["imports"] == ["fopen", "fread"]
          and "imports" not in drstr_record["result"])
    drstr_blocked = from_drstr_l3(
        {"verdict": "BLOCKED", "reason": "wrong head"}, input_sha256="d" * 64,
        input_size=11968, build="eu2011", function="0x00419350",
        reads=[["DRSTR001.DAT", 0, 32, 32]])
    check("adapter drstr_l3: a BLOCKED stub is valid and keeps its reason",
          problems(drstr_blocked) == []
          and drstr_blocked["result"]["reason"] == "wrong head")
    check("adapter drstr_l3: a stub with no build or function is refused",
          _raises(lambda: from_drstr_l3({"verdict": "ACCEPT"})))

    with tempfile.TemporaryDirectory(prefix="reader-trace-selftest-") as tmp:
        good_path = Path(tmp) / "good.json"
        write_trace(good_path, [mmain_record, drstr_record])
        check("write_trace: a two-record file validates", validate_file(good_path) == [])
        check("write_trace: the file is a JSON array", isinstance(
            json.loads(good_path.read_text()), list))
        bad_path = Path(tmp) / "bad.json"
        broken = dict(mmain_record, function="nope")
        check("write_trace: an invalid record raises",
              _raises(lambda: write_trace(Path(tmp) / "no.json", [broken])))
        bad_path.write_text(json.dumps([broken]) + "\n")
        check("validate_file: an invalid record is named",
              any("function" in p for p in validate_file(bad_path)))
        empty_path = Path(tmp) / "empty.json"
        empty_path.write_text("[]\n")
        check("validate_file: an empty array is refused",
              validate_file(empty_path) == ["%s has no records" % empty_path])
        not_json = Path(tmp) / "not.json"
        not_json.write_text("{")
        check("validate_file: invalid JSON is refused",
              any("not JSON" in p for p in validate_file(not_json)))
        check("compare: the same record is SAME",
              compare_records(good, dict(good)) == [])
        changed_read = json.loads(json.dumps(good))
        changed_read["reads"][0]["got"] = 0
        check("compare: a changed read is DIFFERENT", compare_records(
            good, changed_read) == ["reads"])
        changed_result = json.loads(json.dumps(good))
        changed_result["result"]["verdict"] = "REJECT"
        check("compare: a changed verdict is DIFFERENT", compare_records(
            good, changed_result) == ["result"])
        changed_args = json.loads(json.dumps(good))
        changed_args["arguments"]["case"] = "rebuilt"
        check("compare: changed arguments are DIFFERENT", compare_records(
            good, changed_args) == ["arguments"])
        check("compare: files with different record counts are DIFFERENT",
              compare_files(good_path, bad_path) == ["record count (2 vs 1)"])
        same_path = Path(tmp) / "same.json"
        write_trace(same_path, [mmain_record, drstr_record])
        check("compare: two equal files are SAME", compare_files(good_path, same_path) == [])
        code, output = _cli(["validate", str(good_path)])
        check("cli validate: a good file exits 0", code == 0 and "OK" in output)
        code, output = _cli(["validate", str(bad_path)])
        check("cli validate: a bad file exits 1", code == 1 and "FAIL" in output)
        code, output = _cli(["compare", str(good_path), str(same_path)])
        check("cli compare: SAME exits 0", code == 0 and output.strip() == "SAME")
        code, output = _cli(["compare", str(good_path), str(bad_path)])
        check("cli compare: a count difference exits 1",
              code == 1 and "DIFFERENT" in output)

    print("selftest: %d checks, %d failed" % (checks, len(failures)))
    return 1 if failures else 0


def _raises(func) -> bool:
    try:
        func()
    except TraceError:
        return True
    return False


def _cli(argv) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        code = main(argv)
    return code, buffer.getvalue()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--selftest", action="store_true",
                        help="synthetic schema, adapter and compare checks")
    sub = parser.add_subparsers(dest="cmd")
    validate = sub.add_parser("validate", help="check trace files against the schema")
    validate.add_argument("files", nargs="+")
    compare = sub.add_parser("compare", help="compare two trace files record by record")
    compare.add_argument("left")
    compare.add_argument("right")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "validate":
        return cmd_validate(args)
    if args.cmd == "compare":
        return cmd_compare(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
