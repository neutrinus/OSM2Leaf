#!/usr/bin/env python3
"""Parse the 72-byte ``VER_INFO/HDD_INFO.TXT`` block and model the map-code check.

The block is six CRLF-separated ASCII lines and no trailing CRLF::

    QSD-302-100
    QSD-309-101
   02-110100-00
    SDC08-EVEUR
    11-05
    470323501005

``parse``/``to_bytes`` round-trip byte-identically, including any bytes after
the sixth line (``tail``).

The map-code model (``M0``) reproduces only what the firmware comparator chain
documents: a numeric ``Sys[0x%x]`` vs ``SD[0x%x]`` comparison of
``manufacturer_id``, ``userdata_type`` (range ``0..5``) and ``destination_id``.
It is a **HYPOTHESIS** derived from ``0x6fab2c -> 0x6faeb0 -> 0x6fb05c``
(EXP-2026-11-05-17), not from hardware.  Every verdict is unvalidated until
the spare-card matrix in ``docs/format/validation.md`` runs.  In particular the
line->field mapping below is a guess, not a decoded parser:

* ``userdata_type``  - leading digit of the first number on line 1 (family),
* ``manufacturer_id``- digits of the line-4 prefix (``SDC08`` -> 8),
* ``destination_id`` - line-4 suffix via a model-local token table.

Exit codes: 0 success / ACCEPT, 1 DIFFERENT MAP CODE, 2 usage/parse/IO error.

Usage::

    python3 tools/hddinfo.py parse VER_INFO/HDD_INFO.TXT [--json]
    python3 tools/hddinfo.py classify SYS.TXT SD.TXT [--json]
    python3 tools/hddinfo.py matrix BASE.TXT OUT_DIR [--sys SYS.TXT]
                                     [--sweep 0-5] [--no-permute] [--json]
    python3 tools/hddinfo.py --selftest [--json]

``matrix`` calls ``tools/hddinfo_variants.py`` to write the length-preserving
variants, then annotates each one with the model's prediction and replaces
``OUT_DIR/MANIFEST.txt`` (the variant tool's own manifest is kept next to it as
``MANIFEST.variants.txt``).  Variant files left over from an earlier run are
excluded from the manifest with a warning, so a changed ``--sweep`` or
``--no-permute`` cannot silently mix matrices.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

SIZE = 72
LINE_NAMES = (
    "base_code",    # line 1, QSD-302-100 - market/family base code
    "map_set",      # line 2, QSD-309-101 - tracks the map set / FAT label
    "build",        # line 3, 02-110100-00 - build/version string
    "map_code",     # line 4, SDC08-EVEUR - manufacturer + destination
    "year_month",   # line 5, 11-05 - year-month
    "part_number",  # line 6, 470323501005 - part number
)

FIELD_ORDER = ("manufacturer_id", "userdata_type", "destination_id")
USERDATA_MIN, USERDATA_MAX = 0, 5

# Model-local ordinals only: they never leave the model and carry no
# reverse-engineered meaning.  Equality of the text token is what is compared
# when a token has no entry here.
DESTINATION_IDS = {"EVEUR": 0x01}

MODEL_ID = "M0"
MODEL_STATUS = "HYPOTHESIS"
MODEL_SOURCE = (
    "firmware comparator chain 0x6fab2c -> 0x6faeb0 -> 0x6fb05c "
    "(EXP-2026-11-05-17, C-300/C-301)"
)
MODEL_NOTE = (
    "line->field mapping and numeric derivations are a hypothesis; "
    "no verdict has been validated on a car"
)

EXIT_OK, EXIT_DIFFERENT, EXIT_ERROR = 0, 1, 2


@dataclass
class HddInfo:
    """Six named lines plus the exact bytes that follow the sixth line."""

    lines: list[bytes]
    tail: bytes = b""

    @classmethod
    def parse(cls, raw: bytes) -> "HddInfo":
        parts = raw.split(b"\r\n", len(LINE_NAMES) - 1)
        if len(parts) < len(LINE_NAMES):
            raise ValueError(
                f"expected {len(LINE_NAMES)} CRLF-separated lines, found {len(parts)}"
            )
        *head, last = parts
        line6, sep, tail = last.partition(b"\r\n")
        return cls(list(head) + [line6], sep + tail)

    def to_bytes(self) -> bytes:
        return b"\r\n".join(self.lines) + self.tail

    @property
    def size(self) -> int:
        return len(self.to_bytes())

    def text(self, name: str) -> str:
        return self.lines[LINE_NAMES.index(name)].decode("latin-1")

    def with_line(self, name: str, value: bytes) -> "HddInfo":
        lines = list(self.lines)
        lines[LINE_NAMES.index(name)] = value
        return HddInfo(lines, self.tail)


@dataclass
class FieldRead:
    """One field as read from one side of the comparison."""

    raw: str | None
    value: int | None
    out_of_range: bool = False
    rule: str = ""


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_file(path: Path) -> bytes:
    return path.read_bytes()


def hexval(value: int | None) -> str:
    return "n/a" if value is None else "0x%04x" % value


def model_fields(record: HddInfo) -> dict[str, FieldRead]:
    """Derive the three compared numbers from the six text lines (M0)."""
    base = record.text("base_code")
    code = record.text("map_code")

    family = re.search(r"\d+", base)
    if family:
        token = family.group(0)
        value = int(token[0])  # leading digit == family/hundreds digit
        userdata = FieldRead(
            token,
            value,
            not (USERDATA_MIN <= value <= USERDATA_MAX),
            "leading digit of the first number on line 1",
        )
    else:
        userdata = FieldRead(None, None, False, "no number on line 1")

    prefix, sep, suffix = code.partition("-")
    digits = re.search(r"\d+", prefix)
    if digits:
        manufacturer = FieldRead(
            digits.group(0),
            int(digits.group(0)) & 0xFFFF,
            False,
            "digits of the line-4 prefix",
        )
    else:
        manufacturer = FieldRead(None, None, False, "no digits in the line-4 prefix")

    if sep and suffix:
        destination = FieldRead(
            suffix,
            DESTINATION_IDS.get(suffix),
            False,
            "line-4 suffix, model-local token table",
        )
    else:
        destination = FieldRead(None, None, False, "no line-4 suffix")

    return {
        "manufacturer_id": manufacturer,
        "userdata_type": userdata,
        "destination_id": destination,
    }


def _side(read: FieldRead) -> dict:
    return {"raw": read.raw, "value": read.value, "hex": hexval(read.value)}


def _compare(name: str, sys_read: FieldRead, sd_read: FieldRead) -> dict:
    entry = {
        "sys": _side(sys_read),
        "sd": _side(sd_read),
        "verdict": "match",
        "detail": "",
    }
    if sys_read.raw is None or sd_read.raw is None:
        missing = [side for side, r in (("Sys", sys_read), ("SD", sd_read)) if r.raw is None]
        entry["verdict"] = "unparsed"
        entry["detail"] = "field missing on " + " and ".join(missing)
        return entry

    if name == "userdata_type":
        bad = [side for side, r in (("Sys", sys_read), ("SD", sd_read)) if r.out_of_range]
        if bad:
            entry["verdict"] = "out-of-range"
            entry["detail"] = (
                "userdata_type outside %d..%d on %s"
                % (USERDATA_MIN, USERDATA_MAX, " and ".join(bad))
            )
            return entry

    if sys_read.value is not None and sd_read.value is not None:
        if sys_read.value == sd_read.value:
            return entry
        entry["verdict"] = "different"
        entry["detail"] = "Sys[%s] != SD[%s]" % (
            hexval(sys_read.value),
            hexval(sd_read.value),
        )
        return entry

    if sys_read.raw == sd_read.raw:
        entry["detail"] = "equal text token (no numeric mapping)"
        return entry

    entry["verdict"] = "different"
    entry["detail"] = "Sys[%r] != SD[%r] (no numeric mapping)" % (
        sys_read.raw,
        sd_read.raw,
    )
    return entry


def classify(sys_record: HddInfo, sd_record: HddInfo) -> dict:
    """Compare the Sys (built-in copy) side against the SD (card) side."""
    sys_fields = model_fields(sys_record)
    sd_fields = model_fields(sd_record)
    fields = {
        name: _compare(name, sys_fields[name], sd_fields[name])
        for name in FIELD_ORDER
    }
    accepted = all(entry["verdict"] == "match" for entry in fields.values())
    reasons = [
        "%s: %s" % (name, entry["detail"])
        for name, entry in fields.items()
        if entry["verdict"] != "match"
    ]
    return {
        "model": MODEL_ID,
        "model_status": MODEL_STATUS,
        "model_note": MODEL_NOTE,
        "verdict": "ACCEPT" if accepted else "DIFFERENT MAP CODE",
        "accepted": accepted,
        "fields": fields,
        "reasons": reasons,
    }


def record_json(record: HddInfo, path: Path, raw: bytes) -> dict:
    return {
        "path": str(path),
        "size": record.size,
        "size_ok": record.size == SIZE,
        "sha256": sha256(raw),
        "lines": {name: record.text(name) for name in LINE_NAMES},
        "tail_hex": record.tail.hex(),
        "model_fields": {
            name: {
                "raw": read.raw,
                "value": read.value,
                "hex": hexval(read.value),
                "out_of_range": read.out_of_range,
                "rule": read.rule,
            }
            for name, read in model_fields(record).items()
        },
    }


def format_record(record: HddInfo, path: Path, raw: bytes) -> str:
    out = [
        "%s  %d bytes%s" % (
            path,
            record.size,
            "" if record.size == SIZE else "  (expected %d)" % SIZE,
        ),
        "  sha256       %s" % sha256(raw),
    ]
    for name in LINE_NAMES:
        out.append("  %-12s %r" % (name, record.text(name)))
    out.append("  %-12s %s" % ("tail", record.tail.hex() if record.tail else "(none)"))
    for name, read in model_fields(record).items():
        flag = "  OUT OF RANGE" if read.out_of_range else ""
        out.append(
            "  %-12s %s  %s%s"
            % (name, read.raw if read.raw is not None else "(missing)", hexval(read.value), flag)
        )
    return "\n".join(out)


def format_classification(result: dict, sys_name: str, sd_name: str) -> str:
    out = [
        "model %s (%s; unvalidated): Sys=%s  SD=%s"
        % (MODEL_ID, MODEL_STATUS, sys_name, sd_name)
    ]
    for name in FIELD_ORDER:
        entry = result["fields"][name]
        line = "  %-16s Sys[%s] SD[%s]  %s" % (
            name,
            entry["sys"]["hex"],
            entry["sd"]["hex"],
            entry["verdict"],
        )
        if entry["detail"]:
            line += "  (%s)" % entry["detail"]
        out.append(line)
    out.append("verdict: %s" % result["verdict"])
    if not result["accepted"]:
        for reason in result["reasons"]:
            out.append("  ! %s" % reason)
    return "\n".join(out)


def short_line(value: bytes, limit: int = 32) -> str:
    text = value.decode("latin-1")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def describe_change(base: HddInfo, variant: HddInfo) -> tuple[int, str]:
    changed = [
        index for index in range(len(LINE_NAMES)) if base.lines[index] != variant.lines[index]
    ]
    if not changed:
        return 0, "unchanged"
    if len(changed) == 1:
        index = changed[0]
        return index + 1, "%s -> %s" % (
            short_line(base.lines[index]),
            short_line(variant.lines[index]),
        )
    if sorted(base.lines) == sorted(variant.lines):
        return 0, "permutation of lines"
    return 0, "lines " + ",".join(str(index + 1) for index in changed)


def run_variant_tool(base: Path, out_dir: Path, sweep: str, permute: bool) -> str:
    tool = Path(__file__).resolve().with_name("hddinfo_variants.py")
    if not tool.is_file():
        raise RuntimeError("missing %s" % tool)
    command = [sys.executable, str(tool), str(base), str(out_dir), "--sweep", sweep]
    if not permute:
        command.append("--no-permute")
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            "%s failed (%d): %s" % (tool.name, proc.returncode, proc.stderr.strip())
        )
    return proc.stdout.strip()


def cmd_parse(args: argparse.Namespace) -> int:
    path = Path(args.file)
    raw = read_file(path)
    record = HddInfo.parse(raw)
    if args.json:
        print(json.dumps(record_json(record, path, raw), indent=2))
    else:
        print(format_record(record, path, raw))
        if record.size != SIZE:
            print("warning: %d bytes, the card block is %d" % (record.size, SIZE), file=sys.stderr)
    return EXIT_OK


def cmd_classify(args: argparse.Namespace) -> int:
    sys_path, sd_path = Path(args.sys_file), Path(args.sd_file)
    sys_raw, sd_raw = read_file(sys_path), read_file(sd_path)
    result = classify(HddInfo.parse(sys_raw), HddInfo.parse(sd_raw))
    if args.json:
        payload = dict(result)
        payload["sys"] = record_json(HddInfo.parse(sys_raw), sys_path, sys_raw)
        payload["sd"] = record_json(HddInfo.parse(sd_raw), sd_path, sd_raw)
        print(json.dumps(payload, indent=2))
    else:
        print(format_classification(result, sys_path.name, sd_path.name))
    return EXIT_OK if result["accepted"] else EXIT_DIFFERENT


def cmd_matrix(args: argparse.Namespace) -> int:
    base_path = Path(args.base)
    out_dir = Path(args.out_dir)
    base_raw = read_file(base_path)
    base_record = HddInfo.parse(base_raw)
    sys_path = Path(args.sys) if args.sys else base_path
    sys_record = HddInfo.parse(read_file(sys_path)) if args.sys else base_record

    out_dir.mkdir(parents=True, exist_ok=True)
    before = {
        path.name: path.stat().st_mtime_ns
        for path in out_dir.glob("*.HDD_INFO.TXT")
    }
    summary = run_variant_tool(base_path, out_dir, args.sweep, not args.no_permute)
    if args.json:
        print(summary, file=sys.stderr)
    else:
        print(summary)

    # Files left over from an earlier run (different sweep/permute settings)
    # keep their old mtime and would silently distort the matrix.
    stale = sorted(
        path.name
        for path in out_dir.glob("*.HDD_INFO.TXT")
        if before.get(path.name) == path.stat().st_mtime_ns
    )
    if stale:
        print(
            "warning: %d pre-existing variant(s) not regenerated, excluded from "
            "the manifest: %s" % (len(stale), ", ".join(stale)),
            file=sys.stderr,
        )

    old_manifest = out_dir / "MANIFEST.txt"
    if old_manifest.exists():
        old_manifest.replace(out_dir / "MANIFEST.variants.txt")

    rows = []
    for path in sorted(out_dir.glob("*.HDD_INFO.TXT")):
        if path.name in stale:
            continue
        raw = read_file(path)
        if len(raw) != len(base_raw):
            raise RuntimeError(
                "%s changed length: %d != %d" % (path.name, len(raw), len(base_raw))
            )
        record = HddInfo.parse(raw)
        result = classify(sys_record, record)
        line, edit = describe_change(base_record, record)
        rows.append(
            {
                "file": path.name,
                "line": line,
                "edit": edit,
                "verdict": result["verdict"],
                "reasons": result["reasons"],
                "fields": {
                    name: entry["verdict"] for name, entry in result["fields"].items()
                },
            }
        )

    verdicts = Counter(row["verdict"] for row in rows)
    by_field = Counter(
        name
        for row in rows
        for name, verdict in row["fields"].items()
        if verdict != "match"
    )

    manifest = [
        "HDD_INFO.TXT map-code matrix (model predictions only)",
        "",
        "model:      %s (%s)" % (MODEL_ID, MODEL_STATUS),
        "source:     %s" % MODEL_SOURCE,
        "warning:    %s." % MODEL_NOTE,
        "base:       %s (%d bytes, sha256 %s)"
        % (base_path, len(base_raw), sha256(base_raw)),
        "sys side:   %s%s"
        % (
            sys_path,
            " (= base)" if not args.sys else " (sha256 %s)" % sha256(read_file(sys_path)),
        ),
        "variants:   %d, all %d bytes" % (len(rows), len(base_raw)),
        *(
            ["excluded:   %d stale file(s): %s" % (len(stale), ", ".join(stale))]
            if stale
            else []
        ),
        "",
        "predicted verdicts:",
    ]
    for verdict in ("ACCEPT", "DIFFERENT MAP CODE"):
        if verdicts.get(verdict):
            manifest.append("  %-20s %3d" % (verdict, verdicts[verdict]))
    for name in FIELD_ORDER:
        if by_field.get(name):
            manifest.append("    %-18s %3d" % (name, by_field[name]))
    manifest += [
        "",
        "%-50s %-4s %-40s %s" % ("file", "line", "edit", "prediction"),
        "%-50s %-4s %-40s %s" % ("-" * 50, "-" * 4, "-" * 40, "-" * 20),
    ]
    for row in rows:
        manifest.append(
            "%-50s %-4s %-40s %s"
            % (row["file"], row["line"] or "-", row["edit"], row["verdict"])
        )
    manifest += [
        "",
        "The variant tool's own manifest is MANIFEST.variants.txt.",
        "Run this matrix on a spare card only; the original card stays read-only.",
    ]
    (out_dir / "MANIFEST.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")

    if args.json:
        print(
            json.dumps(
                {
                    "model": MODEL_ID,
                    "model_status": MODEL_STATUS,
                    "model_note": MODEL_NOTE,
                    "base": {
                        "path": str(base_path),
                        "size": len(base_raw),
                        "sha256": sha256(base_raw),
                    },
                    "sys": {
                        "path": str(sys_path),
                        "sha256": sha256(read_file(sys_path)),
                    },
                    "out_dir": str(out_dir),
                    "counts": dict(verdicts),
                    "field_counts": dict(by_field),
                    "variants": rows,
                },
                indent=2,
            )
        )
    else:
        print("%d variants, all %d bytes" % (len(rows), len(base_raw)))
        for verdict, count in sorted(verdicts.items()):
            print("  %-20s %3d" % (verdict, count))
        for name, count in sorted(by_field.items()):
            print("    %-18s %3d" % (name, count))
        print("manifest: %s" % (out_dir / "MANIFEST.txt"))
    return EXIT_OK


def cmd_selftest(json_out: bool = False) -> int:
    """Synthetic six-line blocks only; no vendor data is read."""
    checks: list[tuple[bool, str]] = []

    def check(condition: bool, label: str) -> None:
        checks.append((bool(condition), label))

    synthetic = [
        b"TST-302-100",
        b"TST-309-101",
        b"02-990100-00",
        b"TST08-EVEUR",
        b"99-05",
        b"990323501005",
    ]
    raw = b"\r\n".join(synthetic)
    check(len(raw) == SIZE, "synthetic block is exactly %d bytes" % SIZE)

    record = HddInfo.parse(raw)
    check(record.size == SIZE, "parsed record size is %d" % SIZE)
    check(record.to_bytes() == raw, "parse/serialise round-trip is byte-identical")
    check(record.lines == synthetic, "all six named lines retain their bytes")
    check(record.tail == b"", "no tail bytes in the canonical block")

    trailing = HddInfo.parse(raw + b"\r\n")
    check(trailing.to_bytes() == raw + b"\r\n", "trailing CRLF is retained")
    check(trailing.tail == b"\r\n", "trailing CRLF is kept in tail, not in line 6")

    padded = raw + b"\r\n\x00\x00"
    padded_record = HddInfo.parse(padded)
    check(padded_record.to_bytes() == padded, "arbitrary tail bytes round-trip")
    check(padded_record.tail == b"\r\n\x00\x00", "arbitrary tail bytes stay in tail")

    fields = model_fields(record)
    check(fields["manufacturer_id"].value == 8, "manufacturer_id derives 0x08 from TST08")
    check(fields["userdata_type"].value == 3, "userdata_type derives family digit 3")
    check(fields["destination_id"].value == 1, "destination_id maps EVEUR in the model table")
    check(
        not fields["userdata_type"].out_of_range,
        "family digit 3 is inside 0..5",
    )

    same = classify(record, record)
    check(same["verdict"] == "ACCEPT", "identical Sys/SD classifies as ACCEPT")
    check(len(same["reasons"]) == 0, "identical Sys/SD has no reasons")

    part = classify(record, record.with_line("part_number", b"990323501006"))
    check(part["verdict"] == "ACCEPT", "line-6 edit stays ACCEPT (part number not compared)")
    check(
        part["fields"]["manufacturer_id"]["verdict"] == "match",
        "line-6 edit leaves manufacturer_id matching",
    )

    destination = classify(record, record.with_line("map_code", b"TST08-EVXXX"))
    check(destination["verdict"] == "DIFFERENT MAP CODE", "destination token edit is DIFFERENT")
    check(
        destination["fields"]["destination_id"]["verdict"] == "different",
        "destination token edit flags destination_id",
    )
    check(
        destination["fields"]["manufacturer_id"]["verdict"] == "match",
        "destination token edit does not flag manufacturer_id",
    )

    manufacturer = classify(record, record.with_line("map_code", b"TST09-EVEUR"))
    check(manufacturer["verdict"] == "DIFFERENT MAP CODE", "manufacturer digit edit is DIFFERENT")
    check(
        manufacturer["fields"]["manufacturer_id"]["verdict"] == "different",
        "manufacturer digit edit flags manufacturer_id",
    )
    check(
        manufacturer["fields"]["destination_id"]["verdict"] == "match",
        "manufacturer digit edit does not flag destination_id",
    )

    bad_type = record.with_line("base_code", b"TST-902-100")
    bad_result = classify(record, bad_type)
    check(bad_result["verdict"] == "DIFFERENT MAP CODE", "userdata_type 9 is rejected")
    check(
        bad_result["fields"]["userdata_type"]["verdict"] == "out-of-range",
        "userdata_type 9 is flagged out-of-range",
    )
    check(
        any("outside 0..5" in reason for reason in bad_result["reasons"]),
        "out-of-range reason names the 0..5 bound",
    )
    check(
        model_fields(bad_type)["userdata_type"].out_of_range,
        "model_fields marks userdata_type 9 out of range",
    )

    zero_record = record.with_line("base_code", b"TST-002-100")
    zero_type = classify(record, zero_record)
    check(
        zero_type["fields"]["userdata_type"]["verdict"] == "different",
        "userdata_type 0 differs but is not out-of-range",
    )
    check(
        not model_fields(zero_record)["userdata_type"].out_of_range,
        "userdata_type 0 is inside the model bound",
    )

    missing = classify(record, record.with_line("map_code", b"REVERSED"))
    check(missing["verdict"] == "DIFFERENT MAP CODE", "lost map_code line is DIFFERENT")
    check(
        missing["fields"]["destination_id"]["verdict"] == "unparsed",
        "lost map_code line leaves destination_id unparsed",
    )
    check(
        missing["fields"]["manufacturer_id"]["verdict"] == "unparsed",
        "lost map_code line leaves manufacturer_id unparsed",
    )

    short_ok = False
    try:
        HddInfo.parse(b"A\r\nB\r\nC")
    except ValueError:
        short_ok = True
    check(short_ok, "fewer than six lines raises ValueError")

    serial = True
    try:
        json.dumps(bad_result)
    except (TypeError, ValueError):
        serial = False
    check(serial, "classification result is JSON-serialisable")

    failures = [label for ok, label in checks if not ok]
    if json_out:
        print(
            json.dumps(
                {
                    "model": MODEL_ID,
                    "model_status": MODEL_STATUS,
                    "checks": len(checks),
                    "failures": failures,
                    "ok": not failures,
                },
                indent=2,
            )
        )
    else:
        for ok, label in checks:
            print("  %s  %s" % ("ok  " if ok else "FAIL", label))
        print(
            "selftest: %s (%d checks)"
            % ("OK" if not failures else "FAILED", len(checks))
        )
    return EXIT_OK if not failures else EXIT_DIFFERENT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="The model is a HYPOTHESIS; run the spare-card matrix before trusting a verdict.",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="run the synthetic self-test and exit (handled before subcommands)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_parse = sub.add_parser("parse", help="parse one HDD_INFO.TXT block")
    p_parse.add_argument("file")
    p_parse.add_argument("--json", action="store_true")
    p_parse.set_defaults(func=cmd_parse)

    p_class = sub.add_parser("classify", help="predict a verdict for one Sys/SD pair")
    p_class.add_argument("sys_file", help="Sys side (built-in 0x06000000 copy)")
    p_class.add_argument("sd_file", help="SD side (card VER_INFO/HDD_INFO.TXT)")
    p_class.add_argument("--json", action="store_true")
    p_class.set_defaults(func=cmd_classify)

    p_matrix = sub.add_parser("matrix", help="emit variants with predicted verdicts")
    p_matrix.add_argument("base", help="base HDD_INFO.TXT (72 bytes)")
    p_matrix.add_argument("out_dir")
    p_matrix.add_argument(
        "--sys", help="Sys side to compare against (default: the base file itself)"
    )
    p_matrix.add_argument("--sweep", default="0-5", help="digit sweep range (default 0-5)")
    p_matrix.add_argument(
        "--no-permute", action="store_true", help="skip line swaps and the reverse variant"
    )
    p_matrix.add_argument("--json", action="store_true")
    p_matrix.set_defaults(func=cmd_matrix)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return cmd_selftest(json_out="--json" in argv)

    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
