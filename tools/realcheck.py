#!/usr/bin/env python3
"""Real-image regression run for the CE ROM tools (H7).

One command replays the pinned checks from EXP-2026-11-06-H5 on the shared
``IMG256`` slice and prints PASS/FAIL per check, so a tool that passes its
synthetic self-test but fails on real bytes is caught the same day (C-1714).

Checks, in order:

  input     SHA-256 and size of the file itself (the IMG256 slice)
  romhdr    build A ROMHDR: modules, files, CPU, physfirst, physlast
  exports   image B ``coredll.dll``: export count and the C-1710 ordinals
  imports   image A ``Navi.exe``: import slot count
  comphdr   image A, every compressed section: HOLDS/REFUTED/UNPARSED
  thunks    image A ``Navi.exe``: detected stubs and import slots
  sh4xref   image A ``Navi.exe``: the EXP-50 thunk call sites
  probe     image A ``NaviMapCC.dll``: decoder probe on the two EXP-49 sections

Every expected value lives in the ``PINS`` table below.  The tool never edits
that table on its own: on a readable image ``--update`` only prints a proposed
table and exits 3; ``--update --write`` is the explicit, separate switch that
rewrites it.

A missing or unreadable image makes every check ``SKIP no image`` and exits 2;
``--require-image`` turns those skips into FAILs (exit 1).

Usage::

    python3 tools/realcheck.py IMG256
    python3 tools/realcheck.py IMG256 --require-image
    python3 tools/realcheck.py --selftest
    python3 tools/realcheck.py IMG256 --update            # print, refuse to write
    python3 tools/realcheck.py IMG256 --update --write    # deliberate re-pin

Exit codes: 0 all PASS (or all SKIP without ``--require-image``), 1 any FAIL,
2 image missing/unreadable, 3 ``--update`` without ``--write``.
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cecompress  # noqa: E402
import cerom  # noqa: E402
import sh4xref  # noqa: E402

READ_LIMIT = 128 << 20
# Split so the marker value does not occur in this definition itself; the only
# literal occurrence in the file is the actual PINS block that --write edits.
PINS_JSON_MARKER = 'PINS_JSON = r' + '"""'

# Pinned values.  Every scalar is what the named tool must report on IMG256;
# a mismatch is a FAIL, never a silent re-pin.  Addresses are strings in hex
# so the table stays readable; sizes are strings for the same reason.  Selector
# keys (image_start, module, ordinals, to, offsets, all) are inputs, the
# "expect" object is the compared part.
PINS_JSON = r"""
{
  "input": {
    "expect": {
      "sha256": "92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9",
      "size": 268435456
    }
  },
  "romhdr": {
    "image_start": "0x200200",
    "expect": {
      "nummods": 149,
      "numfiles": 1,
      "usCPUType": "0x01a6",
      "physfirst": "0x8cae1000",
      "physlast": "0x8e233c88"
    }
  },
  "exports": {
    "image_start": "0x3e00200",
    "module": "coredll.dll",
    "ordinals": [
      719,
      1145,
      1143,
      59,
      66,
      1047,
      1118,
      496,
      65
    ],
    "expect": {
      "names": 1651,
      "ordinals": {
        "719": "sprintf",
        "1145": "_wfopen",
        "1143": "fgetws",
        "59": "wcschr",
        "66": "wcsncpy",
        "1047": "memset",
        "1118": "fclose",
        "496": "Sleep",
        "65": "wcsncmp"
      }
    }
  },
  "imports": {
    "image_start": "0x200200",
    "module": "Navi.exe",
    "expect": {
      "slots": 846
    }
  },
  "comphdr": {
    "image_start": "0x200200",
    "all": true,
    "expect": {
      "sections": 245,
      "holds": 245,
      "refuted": 0,
      "unparsed": 0
    }
  },
  "thunks": {
    "image_start": "0x200200",
    "module": "Navi.exe",
    "expect": {
      "stubs": 3728,
      "import_slots": 846,
      "covered_slots": 845,
      "slot_coverage": 99.9
    }
  },
  "sh4xref": {
    "image_start": "0x200200",
    "module": "Navi.exe",
    "to": [
      "0x003d1bb0",
      "0x003d1ba4"
    ],
    "expect": {
      "jsr_sites": [
        "0x003778b2",
        "0x003778bc",
        "0x00377b46",
        "0x00377b52"
      ],
      "fn_sites": [
        "0x00377870",
        "0x00377ae0"
      ]
    }
  },
  "probe": {
    "image_start": "0x200200",
    "module": "NaviMapCC.dll",
    "offsets": "0-40",
    "expect": {
      "sections": [
        {
          "rva": "0x13000",
          "vsize": "0x5b8",
          "psize": "0x2c6",
          "matches": 0,
          "attempts": 205
        },
        {
          "rva": "0x14000",
          "vsize": "0xcc0",
          "psize": "0x68c",
          "matches": 0,
          "attempts": 205
        }
      ]
    }
  }
}
"""

PINS = json.loads(PINS_JSON)

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

MISSING = object()


class ImageError(Exception):
    """The image is missing, unreadable or empty (exit 2 territory)."""


class UpdateRefused(Exception):
    """An ``--update`` cannot be rendered because a check produced no value."""


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------


def hex32(value):
    return "0x%08x" % int(value)


def hexv(value):
    return "0x%x" % int(value)


def hex16(value):
    return "0x%04x" % int(value)


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(1 << 20)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def format_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=True)
    return str(value)


def format_observed(observed, limit=260):
    text = " ".join("%s=%s" % (key, format_value(value))
                    for key, value in observed.items())
    if len(text) > limit:
        text = text[:limit - 3] + "..."
    return text


# --------------------------------------------------------------------------
# Image context
# --------------------------------------------------------------------------


class Context:
    """One open image: the first 128 MiB for the parsers, plus its full hash."""

    def __init__(self, path):
        self.path = path
        try:
            self.image_size = os.path.getsize(path)
            with open(path, "rb") as handle:
                self.data = handle.read(READ_LIMIT)
            if not self.data:
                raise ImageError("image is empty")
            self.sha256 = file_sha256(path)
        except OSError as exc:
            raise ImageError(str(exc)) from None


# --------------------------------------------------------------------------
# Checks: each returns the measured values the pin's "expect" is compared to
# --------------------------------------------------------------------------


def check_input(ctx, pin):
    return {"sha256": ctx.sha256, "size": ctx.image_size}


def check_romhdr(ctx, pin):
    rom = cerom.CERom(ctx.data, int(pin["image_start"], 0))
    header = rom.hdr
    return {
        "nummods": header["nummods"],
        "numfiles": header["numfiles"],
        "usCPUType": hex16(header["usCPUType"]),
        "physfirst": hex32(header["physfirst"]),
        "physlast": hex32(header["physlast"]),
    }


def check_exports(ctx, pin):
    rom = cerom.CERom(ctx.data, int(pin["image_start"], 0))
    module = rom.module(pin["module"])
    exports = list(rom.exports(module))
    wanted = set(pin.get("ordinals") or ())
    ordinals = {}
    for ordinal, name, _rva in exports:
        if ordinal in wanted:
            ordinals[str(ordinal)] = name
    for ordinal in sorted(wanted):
        ordinals.setdefault(str(ordinal), None)
    return {"names": len(exports), "ordinals": ordinals}


def check_imports(ctx, pin):
    rom = cerom.CERom(ctx.data, int(pin["image_start"], 0))
    module = rom.module(pin["module"])
    return {"slots": sum(1 for _entry in rom.imports(module))}


def check_comphdr(ctx, pin):
    report = cerom.comphdr_report(
        ctx.data, ctx.path, ctx.image_size, ctx.sha256,
        module=pin.get("module"), all_sections=bool(pin.get("all")),
        image_start=int(pin["image_start"], 0))
    counts = report["counts"]
    return {
        "sections": counts["sections"],
        "holds": counts["holds"],
        "refuted": counts["refuted"],
        "unparsed": counts["unparsed"],
    }


def check_thunks(ctx, pin):
    report = cerom.thunks_report(
        ctx.data, ctx.path, ctx.image_size, ctx.sha256,
        module=pin["module"], image_start=int(pin["image_start"], 0))
    counts = report["counts"]
    cov = report["coverage"]
    return {
        "stubs": counts["stubs"],
        "import_slots": counts["import_slots"],
        "covered_slots": counts["covered_slots"],
        "slot_coverage": cov["slots"]["percent"],
    }


def _xref_call_sites(mem, exec_segs, target):
    """(jsr site, enclosing function) pairs for a literal held in a pool or slot.

    Same two readings as ``sh4xref.query_to`` — the value read as a pool address
    and the value held in a pool — but built from the module's helpers so no
    printed text is parsed.
    """
    pairs = []
    for load_va, reg in sh4xref.loads_of(mem, target):
        call = sh4xref.call_after(mem, load_va, reg)
        if call is not None:
            pairs.append((call[0], sh4xref.function_start(mem, load_va)))
    for pool in sh4xref.pool_entries(mem, exec_segs, target):
        for load_va, reg in sh4xref.loads_of(mem, pool):
            call = sh4xref.call_after(mem, load_va, reg)
            if call is not None:
                pairs.append((call[0], sh4xref.function_start(mem, load_va)))
    return pairs


def check_sh4xref(ctx, pin):
    mem, exec_segs, _imports, _exports = sh4xref.load_module(
        ctx.path, int(pin["image_start"], 0), pin["module"])
    sites, functions = set(), set()
    for value in pin["to"]:
        for site, function in _xref_call_sites(mem, exec_segs, int(value, 0)):
            sites.add(site)
            if function is not None:
                functions.add(function)
    return {
        "jsr_sites": [hex32(value) for value in sorted(sites)],
        "fn_sites": [hex32(value) for value in sorted(functions)],
    }


def check_probe(ctx, pin):
    rom = cerom.CERom(ctx.data, int(pin["image_start"], 0))
    module = rom.module(pin["module"])
    offsets = cecompress.parse_offsets(pin["offsets"])
    records = []
    for section in rom.o32(module):
        if not section["flags"] & cerom.IMAGE_SCN_COMPRESSED:
            continue
        if not section["psize"]:
            continue
        offset = rom.va2file(section["dataptr"])
        blob = ctx.data[offset:offset + section["psize"]]
        report = cecompress.probe(blob, expected_size=section["vsize"],
                                  offsets=offsets)
        records.append({
            "rva": hexv(section["rva"]),
            "vsize": hexv(section["vsize"]),
            "psize": hexv(section["psize"]),
            "matches": len(report["matches"]),
            "attempts": len(report["attempts"]),
        })
    records.sort(key=lambda record: int(record["rva"], 16))
    return {"sections": records}


# --------------------------------------------------------------------------
# Check table and runner
# --------------------------------------------------------------------------


class Check:
    __slots__ = ("id", "label", "function")

    def __init__(self, check_id, label, function):
        self.id = check_id
        self.label = label
        self.function = function


CHECKS = (
    Check("input", "input SHA-256", check_input),
    Check("romhdr", "romhdr build A", check_romhdr),
    Check("exports", "exports coredll.dll (B)", check_exports),
    Check("imports", "imports Navi.exe (A)", check_imports),
    Check("comphdr", "comphdr --all (A)", check_comphdr),
    Check("thunks", "thunks Navi.exe (A)", check_thunks),
    Check("sh4xref", "sh4xref EXP-50 call sites (A)", check_sh4xref),
    Check("probe", "cecompress probe NaviMapCC.dll (A)", check_probe),
)


class Result:
    __slots__ = ("id", "label", "status", "detail", "expected", "observed")

    def __init__(self, check_id, label, status, detail,
                 expected=None, observed=None):
        self.id = check_id
        self.label = label
        self.status = status
        self.detail = detail
        self.expected = expected
        self.observed = observed

    @property
    def ok(self):
        return self.status in (PASS, SKIP)


class Run:
    def __init__(self, results, image_error=None):
        self.results = results
        self.image_error = image_error


def compare(expected, observed):
    """Field-by-field mismatches; an extra observed field is not a failure."""
    mismatches = []
    for key, want in expected.items():
        got = observed.get(key, MISSING)
        if got != want:
            mismatches.append((key, want, got))
    return mismatches


def run_checks(path, pins, checks=CHECKS, require_image=False):
    try:
        ctx = Context(path)
    except ImageError as exc:
        status = FAIL if require_image else SKIP
        detail = ("no image: %s" % exc) if require_image else "no image"
        results = [Result(spec.id, spec.label, status, detail)
                   for spec in checks]
        return Run(results, image_error=exc)

    results = []
    for spec in checks:
        pin = pins[spec.id]
        try:
            observed = spec.function(ctx, pin)
        except Exception as exc:  # a malformed image is a real failure
            kind = type(exc).__name__
            if kind == "error":  # struct.error names its class just "error"
                kind = "struct.error"
            results.append(Result(
                spec.id, spec.label, FAIL,
                "error: %s: %s" % (kind, exc)))
            continue
        expected = pin.get("expect", {})
        mismatches = compare(expected, observed)
        if not mismatches:
            results.append(Result(spec.id, spec.label, PASS,
                                  format_observed(observed),
                                  expected=expected, observed=observed))
            continue
        parts = []
        for key, want, got in mismatches:
            got_text = "<missing>" if got is MISSING else format_value(got)
            parts.append("%s got %s want %s"
                         % (key, got_text, format_value(want)))
        results.append(Result(spec.id, spec.label, FAIL, "; ".join(parts),
                              expected=expected, observed=observed))
    return Run(results)


def print_results(results):
    width = max((len(result.label) for result in results), default=0)
    for result in results:
        print("%-4s  %-*s  %s"
              % (result.status, width, result.label, result.detail))


def print_summary(results):
    passed = sum(1 for result in results if result.status == PASS)
    failed = sum(1 for result in results if result.status == FAIL)
    skipped = sum(1 for result in results if result.status == SKIP)
    print("realcheck: %d PASS, %d FAIL, %d SKIP" % (passed, failed, skipped))


# --------------------------------------------------------------------------
# Pinned-table update (refuse by default)
# --------------------------------------------------------------------------


def proposed_pins(pins, results, checks=CHECKS):
    """New pin table with each checked "expect" replaced by what was measured."""
    by_id = {result.id: result for result in results}
    updated = {}
    for spec in checks:
        pin = dict(pins[spec.id])
        result = by_id.get(spec.id)
        if result is None or result.observed is None:
            raise UpdateRefused("check %r produced no value" % spec.id)
        selectors = {key: value for key, value in pin.items()
                     if key != "expect"}
        selectors["expect"] = result.observed
        updated[spec.id] = selectors
    return updated


def render_pins(pins):
    return json.dumps(pins, indent=2, ensure_ascii=True) + "\n"


def extract_pins_text(text):
    start = text.index(PINS_JSON_MARKER) + len(PINS_JSON_MARKER)
    end = text.index('"""', start)
    return text[start:end]


def replace_pins_block(text, rendered):
    start = text.index(PINS_JSON_MARKER) + len(PINS_JSON_MARKER)
    end = text.index('"""', start)
    return text[:start] + "\n" + rendered + text[end:]


def update_source(path, pins, allow_write):
    """Return (exit code, rendered table); writes only when allowed."""
    rendered = render_pins(pins)
    if not allow_write:
        return 3, rendered
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    new_text = replace_pins_block(text, rendered)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(new_text)
    os.replace(temporary, path)
    return 0, rendered


# --------------------------------------------------------------------------
# Self-test: synthetic CE ROM plus a missing-image case (no vendor bytes)
# --------------------------------------------------------------------------


def selftest():
    fails = []
    total = 0

    def check(label, condition, detail=""):
        nonlocal total
        total += 1
        if condition:
            print("%-52s ok" % label)
        else:
            print("%-52s FAIL %s" % (label, detail))
            fails.append(label)

    payload, layout = cerom.build_synthetic_rom()
    image_start = hexv(layout["image_start"])
    pins = {
        "input": {
            "expect": {
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
            }
        },
        "romhdr": {
            "image_start": image_start,
            "expect": {
                "nummods": 2,
                "numfiles": 3,
                "usCPUType": "0x01a6",
                "physfirst": hex32(cerom.SYNTH_VA_BASE),
                "physlast": hex32(cerom.SYNTH_VA_BASE + 0x90000),
            },
        },
        "exports": {
            "image_start": image_start,
            "module": "NK.EXE",
            "ordinals": [1, 2],
            "expect": {
                "names": 2,
                "ordinals": {
                    "1": layout["export_names"][0],
                    "2": layout["export_names"][1],
                },
            },
        },
    }
    checks = [CHECKS[0], CHECKS[1], CHECKS[2]]

    check("pin table covers every real check",
          all(spec.id in PINS and "expect" in PINS[spec.id]
              for spec in CHECKS),
          [spec.id for spec in CHECKS
           if spec.id not in PINS or "expect" not in PINS[spec.id]])

    # C-1710: the coredll.dll ordinals Navi.exe imports by name, plus C-527's
    # 719 = sprintf and 1651 named exports.  These are check *selectors* and
    # expectations, so a re-pin must touch this guard deliberately too.
    c1710 = {719: "sprintf", 1145: "_wfopen", 1143: "fgetws", 59: "wcschr",
             66: "wcsncpy", 1047: "memset", 1118: "fclose", 496: "Sleep",
             65: "wcsncmp"}
    export_pin = PINS["exports"]
    check("real exports pin: 1651 names",
          export_pin["expect"]["names"] == 1651,
          export_pin["expect"]["names"])
    check("real exports pin: C-1710 ordinals exact",
          export_pin["expect"]["ordinals"] == {str(k): v for k, v in c1710.items()},
          export_pin["expect"]["ordinals"])
    check("real exports pin: selectors cover expected ordinals",
          sorted(export_pin["ordinals"]) == sorted(c1710),
          export_pin["ordinals"])

    mem, exec_segs = sh4xref._synthetic()
    check("sh4xref helper finds the synthetic jsr site",
          _xref_call_sites(mem, exec_segs, 0x10040) == [(0x10008, 0x10004)],
          _xref_call_sites(mem, exec_segs, 0x10040))

    with tempfile.TemporaryDirectory() as tmp:
        image = os.path.join(tmp, "synthetic-ce-rom.img")
        with open(image, "wb") as handle:
            handle.write(payload)

        run = run_checks(image, pins, checks)
        check("synthetic ROM: all three checks PASS",
              [result.status for result in run.results] == [PASS, PASS, PASS],
              [(result.id, result.status, result.detail)
               for result in run.results])
        check("synthetic ROM: PASS detail names the measured values",
              all(result.detail for result in run.results
                  if result.status == PASS))
        check("--update proposal equals the run's measurements",
              proposed_pins(pins, run.results, checks) == pins)

        wrong = json.loads(json.dumps(pins))
        wrong["romhdr"]["expect"]["physlast"] = hex32(
            cerom.SYNTH_VA_BASE + 0x90000 + 0x1000)
        bad_run = run_checks(image, wrong, checks)
        statuses = {result.id: result.status for result in bad_run.results}
        check("wrong pin: only that check FAILs",
              statuses == {"input": PASS, "romhdr": FAIL, "exports": PASS},
              statuses)
        bad = next(result for result in bad_run.results
                   if result.id == "romhdr")
        check("wrong pin: FAIL names the field",
              "physlast" in bad.detail and bad.observed is not None,
              bad.detail)

        missing = os.path.join(tmp, "absent.img")
        skip_run = run_checks(missing, pins, checks)
        check("missing image: every check SKIPs",
              all(result.status == SKIP and result.detail == "no image"
                  for result in skip_run.results),
              [(result.status, result.detail) for result in skip_run.results])
        check("missing image: run carries the exit-2 error",
              skip_run.image_error is not None)
        required = run_checks(missing, pins, checks, require_image=True)
        check("--require-image: every skip becomes FAIL",
              all(result.status == FAIL and result.detail.startswith("no image")
                  for result in required.results),
              [(result.status, result.detail) for result in required.results])

        copy = os.path.join(tmp, "realcheck_copy.py")
        with open(os.path.abspath(__file__), "r", encoding="utf-8") as handle:
            source = handle.read()
        with open(copy, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(source)
        with open(copy, "rb") as handle:
            before = handle.read()
        code, _rendered = update_source(copy, pins, allow_write=False)
        check("--update without --write refuses (exit 3)", code == 3, code)
        with open(copy, "rb") as handle:
            check("refused update leaves the file byte-identical",
                  handle.read() == before)
        code, _rendered = update_source(copy, pins, allow_write=True)
        with open(copy, "r", encoding="utf-8") as handle:
            written = json.loads(extract_pins_text(handle.read()))
        check("--update --write round-trips the pin table",
              code == 0 and written == pins, (code, written))

    if fails:
        print("realcheck selftest: FAILED %d/%d" % (len(fails), total))
        return 1
    print("realcheck selftest: %d checks OK (synthetic CE ROM, no vendor data)"
          % total)
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", nargs="?",
                        help="IMG256 slice (or full image); pinned by SHA-256")
    parser.add_argument("--selftest", action="store_true",
                        help="run the synthetic-ROM self-test and exit")
    parser.add_argument("--require-image", action="store_true",
                        help="turn 'SKIP no image' into FAIL (exit 1)")
    parser.add_argument("--update", action="store_true",
                        help="print a pin table built from this run; never "
                             "writes without --write")
    parser.add_argument("--write", action="store_true",
                        help="with --update: rewrite the PINS table in this file")
    args = parser.parse_args(argv)

    if args.selftest:
        if args.update or args.write:
            parser.error("--selftest cannot be combined with --update/--write")
        return selftest()
    if args.image is None:
        parser.error("an image is required unless --selftest is used")
    if args.write and not args.update:
        parser.error("--write only makes sense with --update")

    run = run_checks(args.image, PINS, CHECKS,
                     require_image=args.require_image)
    print_results(run.results)
    print_summary(run.results)

    if args.update:
        if run.image_error is not None:
            print("realcheck: cannot update pins without a readable image",
                  file=sys.stderr)
            return 2
        try:
            updated = proposed_pins(PINS, run.results, CHECKS)
        except UpdateRefused as exc:
            print("realcheck: cannot update pins: %s" % exc, file=sys.stderr)
            return 1
        code, rendered = update_source(os.path.abspath(__file__), updated,
                                       allow_write=args.write)
        if code == 3:
            sys.stdout.write(rendered)
            print("realcheck: refusing to write pins; re-run with "
                  "--update --write to apply", file=sys.stderr)
        else:
            print("realcheck: wrote %d pinned checks to %s"
                  % (len(updated), os.path.abspath(__file__)))
        return code

    if run.image_error is not None:
        return 1 if args.require_image else 2
    return 0 if all(result.ok for result in run.results) else 1


if __name__ == "__main__":
    sys.exit(main())
