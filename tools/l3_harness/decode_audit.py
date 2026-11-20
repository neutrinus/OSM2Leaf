#!/usr/bin/env python3
"""SH-4 decode audit: engine vs sh4dis, and a census of what the engine cannot run.

The L3 engine models a subset of SH-4.  Three decode defects survived days of
use because the engine's own tests used operands that hide a register mix-up
(M9.37).  This tool answers two questions with numbers, on the real image:

* **compare** -- for every *distinct* opcode in the pdata-covered code, do
  ``l3_harness.engine.decode_fields()`` (table A) and ``tools/sh4dis.py``'s
  ``operands()`` (table B) name the same form and the same ``Rn``/``Rm``?
  Only opcodes the engine *classifies as modelled* are compared (the
  denominator); an unmodelled opcode is a census bucket, never a
  "disagreement", so "0 unexplained" can be false.
* **census** -- every distinct opcode, by bucket: ``MODELLED``, ``FPU``,
  ``MMU`` (control-register/PTE operations), ``IN_SCOPE_UNMODELLED`` (an
  integer form the engine rejects; ``div1`` until M9.48) and ``TRAP`` (``trapa``,
  which is ``Trap`` by design).  Instructions are counted, not just opcodes.

Corpus: pdata-covered halfwords only (``begin .. begin+length``).  Halfwords
in a GAP between functions (leaf code with no pdata record) are excluded and
their count is printed separately, so "0 disagreements" has a pinned
denominator.  The image start and module come from ``cerom.py``; no fitted
deltas.

Usage:
  decode_audit.py compare IMG MODULE [--image-start 0x200200] [--build EU2011]
                            [--engine-module PATH] [--json]
  decode_audit.py census  IMG MODULE [--image-start 0x200200] [--build EU2011]
                            [--engine-module PATH] [--json] [--top N]
  decode_audit.py --selftest

``--engine-module`` loads a different ``engine.py`` (a scratch copy) so the
"before" column of a fix is produced by the same tool, not a remembered
number.

Exit codes: 0 clean, 1 unexplained disagreement, 2 usage/no image, 3 corpus
empty.
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import cerom          # noqa: E402
import pdata          # noqa: E402
import sh4dis         # noqa: E402
from l3_harness import engine as default_engine  # noqa: E402

M32 = 0xFFFFFFFF

# Control-register forms that name an MMU/PTE register: they are MMU state,
# not integer arithmetic, so they are a bucket of their own (out of scope for
# a functional map decoder).  ``ldc/stc`` to SR/GBR/VBR are *core* registers
# the engine models, not MMU, so they are not listed here.  Opcodes, not
# forms: the engine prints these as unmodelled.
MMU_OPCODES = {
    0x0038: "ldtlb",      # load TLB
    0x0028: "clrmac",     # (shadowed by the engine's own clrmac; documented)
}

# Forms the engine rejects that are integer instructions a decoder target may
# still need; kept explicit so the census names them rather than lumping them
# in with unknown bytes.  Empty since M9.48 modelled ``div1``: a table form
# the executor rejects is executor drift again, with no exemption.
INTEGER_OUT_OF_SCOPE = frozenset()


def load_engine(path=None):
    """The engine module, or a scratch copy from *path* (same API)."""
    if not path:
        return default_engine
    name = "decode_audit_engine_%d" % (abs(hash(path)) % 100000)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------

def corpus(data, image_start, module):
    """Distinct opcodes inside pdata functions, and the excluded GAP count.

    Returns ``(counts, info)`` where ``counts`` maps opcode -> instruction
    count and ``info`` holds the pinned denominator facts.
    """
    rom = cerom.CERom(data, image_start)
    try:
        mod = rom.module(module)
    except KeyError:
        raise SystemExit("module %r not found at image start 0x%x"
                         % (module, image_start))
    records, _meta = pdata.load_table(data, image_start, module)
    sections = list(pdata.exec_sections(rom, mod))
    blob_of = {base: blob for _i, base, blob in sections}

    def inside(va, size):
        for base, blob in blob_of.items():
            if base <= va and va + size <= base + len(blob):
                return blob, va - base
        return None, None

    counts = collections.Counter()
    read_records = 0
    unreadable = 0
    covered_bytes = 0
    for begin, _prolog, length in records:
        blob, off = inside(begin, length)
        if blob is None:
            unreadable += 1
            continue
        read_records += 1
        chunk = blob[off:off + length]
        covered_bytes += len(chunk)
        for i in range(0, len(chunk) // 2 * 2, 2):
            counts[chunk[i] | (chunk[i + 1] << 8)] += 1

    # GAP halfwords: the executable bytes between records, excluded on purpose.
    spans = sorted((begin, begin + length) for begin, _p, length in records)
    gap_bytes = 0
    for _i, base, blob in sections:
        end = base + len(blob)
        cursor = base
        for lo, hi in spans:
            if hi <= cursor or lo >= end:
                continue
            if lo > cursor:
                gap_bytes += min(lo, end) - cursor
            cursor = max(cursor, min(hi, end))
        if cursor < end:
            gap_bytes += end - cursor

    info = {
        "module": mod["name"],
        "image_start": image_start,
        "records": len(records),
        "read_records": read_records,
        "unreadable_records": unreadable,
        "covered_bytes": covered_bytes,
        "instructions": sum(counts.values()),
        "distinct": len(counts),
        "gap_bytes": gap_bytes,
        "gap_halfwords": gap_bytes // 2,
    }
    return counts, info


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------

def _probe(engine_mod):
    """A one-instruction engine: 4 code bytes at 0x1000 and a zeroed data page
    at 0x0..0x1000.  Registers start at 0, so every ``@Rn``/``@Rm``/``@R0``
    operand lands in the data page and the instruction runs to its end instead
    of faulting on the first load (M9.49: ``mac.w``'s host ``NameError`` sat
    behind an unmapped ``@Rn`` fault and was counted as MODELLED)."""
    probe = engine_mod.PySh4(endian="little")
    probe.map("d", 0x0, 0x1000, "rw")
    probe.map("c", 0x1000, 4, "rwx")
    probe.set_regs(pc=0x1000)
    return probe


def classify(engine_mod, opcode):
    """``(bucket, arm)`` for one opcode: MODELLED/FPU/MMU/IN_SCOPE_UNMODELLED/TRAP.

    A host exception (anything that is not an ``EngineError``) is a crash in
    the executor, never "modelled": it is bucketed IN_SCOPE_UNMODELLED, so
    ``compare`` reports a table form that crashes as executor drift.
    """
    if (opcode >> 12) == 0xF:
        return "FPU", "fpu"
    form, _rn, _rm, _d = engine_mod.decode_fields(opcode)
    probe = _probe(engine_mod)
    try:
        probe._execute(opcode, 0x1000)
    except engine_mod.Trap:
        return "TRAP", form
    except engine_mod.IllegalInstruction:
        if opcode in MMU_OPCODES:
            return "MMU", MMU_OPCODES[opcode]
        if form in INTEGER_OUT_OF_SCOPE:
            return "IN_SCOPE_UNMODELLED", form
        return "IN_SCOPE_UNMODELLED", form
    except engine_mod.EngineError:
        # Unmapped/unaligned outside the probe pages: the instruction decoded
        # and started to execute, so it is modelled; the fault is the operand.
        return "MODELLED", form
    except Exception:  # noqa: BLE001 -- a host crash is the finding
        return "IN_SCOPE_UNMODELLED", form
    return "MODELLED", form


def tally(engine_mod, counts):
    buckets = collections.Counter()
    bucket_insns = collections.Counter()
    forms = collections.defaultdict(collections.Counter)
    per_opcode = {}
    for opcode, n in counts.items():
        bucket, arm = classify(engine_mod, opcode)
        buckets[bucket] += 1
        bucket_insns[bucket] += n
        forms[bucket][arm] += n
        per_opcode[opcode] = (bucket, arm)
    return buckets, bucket_insns, forms, per_opcode


# --------------------------------------------------------------------------
# compare
# --------------------------------------------------------------------------

def _norm_engine(form, rn, rm):
    """Engine's decode_fields names a register or 0; normalise 0 -> None only
    for forms that name no register at all (r0 is a real operand otherwise)."""
    return form, rn, rm


def compare(engine_mod, counts, info, top=0):
    """Compare decode_fields (engine) with sh4dis.operands() on MODELLED opcodes.

    Besides table-vs-table operand disagreement, an opcode whose form the
    engine's own table names as modelled but whose executor rejects it is a
    different kind of drift, and it is reported too -- otherwise a regression
    in the executor would silently move an opcode into a census bucket and the
    differential would still say "0 disagreements" (the M9.37 falsifier).
    """
    disagree = []
    drift = []
    compared = 0
    for opcode, n in counts.items():
        bucket, _arm = classify(engine_mod, opcode)
        eform, ern, erm, _ed = engine_mod.decode_fields(opcode)
        if bucket != "MODELLED":
            if (eform in INTEGER_OUT_OF_SCOPE or eform == "fpu"
                    or opcode in MMU_OPCODES or eform == "unknown"
                    or eform == "rte" or eform == "trapa"
                    or bucket == "TRAP"):
                continue
            drift.append({
                "opcode": opcode, "count": n, "form": eform,
                "sh4dis": sh4dis.operands(opcode)[0],
                "reason": "table names a form the executor rejects",
            })
            continue
        compared += 1
        sform, srn, srm = sh4dis.operands(opcode)
        if (eform, ern, erm) != (sform, srn, srm):
            disagree.append({
                "opcode": opcode, "count": n,
                "engine": (eform, ern, erm), "sh4dis": (sform, srn, srm),
                "sh4dis_text": sh4dis.decode(opcode).text,
            })

    # Bucket every non-MODELLED opcode so "not compared" is not "fine".
    buckets, bucket_insns, _forms, _per = tally(engine_mod, counts)
    return {
        "info": info,
        "denominator_modelled_distinct": compared,
        "disagreements": disagree,
        "executor_drift": drift,
        "buckets": dict(buckets),
        "bucket_instructions": dict(bucket_insns),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _read_image(path):
    with open(path, "rb") as fh:
        return fh.read()


def _print_info(info):
    print("module        %s" % info["module"])
    print("image-start   0x%08x" % info["image_start"])
    print("records       %d (%d read, %d unreadable)"
          % (info["records"], info["read_records"], info["unreadable_records"]))
    print("instructions  %d (pdata-covered halfwords)" % info["instructions"])
    print("distinct      %d" % info["distinct"])
    print("gap excluded  %d halfwords (%d bytes, no pdata record)"
          % (info["gap_halfwords"], info["gap_bytes"]))


def cmd_census(args):
    data = _read_image(args.image)
    counts, info = corpus(data, args.image_start, args.module)
    engine_mod = load_engine(args.engine_module)
    buckets, bucket_insns, forms, _per = tally(engine_mod, counts)
    named = named_items(engine_mod, counts, info)
    if args.json:
        print(json.dumps({
            "info": info,
            "buckets": dict(buckets),
            "bucket_instructions": dict(bucket_insns),
            "top_forms": {k: forms[k].most_common(10) for k in forms},
            "named_items": named,
        }, indent=2))
        return 0
    _print_info(info)
    print()
    order = ("MODELLED", "FPU", "MMU", "IN_SCOPE_UNMODELLED", "TRAP")
    print("%-20s %10s %10s" % ("bucket", "distinct", "instructions"))
    for name in order:
        print("%-20s %10d %10d" % (name, buckets[name], bucket_insns[name]))
    print()
    if args.top:
        for name in order:
            if not forms[name]:
                continue
            line = ", ".join("%s=%d" % (f, c) for f, c in
                             forms[name].most_common(args.top))
            print("%-20s %s" % (name, line))
        print()
    print("named in-scope items (M9.37):")
    print("%-8s %8s  %-20s %-28s %s"
          % ("opcode", "count", "engine", "sh4dis text", "verdict"))
    for row in named:
        print("%-8s %8d  %-20s %-28s %s"
              % (row["opcode"], row["count"], row["engine"],
                 row["sh4dis"], row["verdict"]))
    return 0


#: The four forms the M9.37 hint names, as representative opcodes.
NAMED = (
    ("mac.l", 0x011F),
    ("mac.w", 0x41DF),
    ("div0s", 0x2B67),
    ("div1", 0x3624),
    ("rotcl", 0x4124),
    ("rotcr", 0x4125),
)


def named_items(engine_mod, counts, info):
    rows = []
    for label, sample in NAMED:
        # Count every instruction of the same form, not only the sample
        # spelling (mac.l has 240 register combinations).
        want = label
        total = 0
        for opcode, n in counts.items():
            form, _rn, _rm, _d = engine_mod.decode_fields(opcode)
            if form == want:
                total += n
        bucket, arm = classify(engine_mod, sample)
        verdict = {"MODELLED": "fixed/modelled", "IN_SCOPE_UNMODELLED":
                   "in-scope-unmodelled"}.get(bucket, bucket.lower())
        rows.append({
            "form": label, "opcode": "0x%04x" % sample, "count": total,
            "engine": arm, "sh4dis": sh4dis.decode(sample).text,
            "verdict": verdict,
        })
    return rows


def cmd_compare(args):
    data = _read_image(args.image)
    counts, info = corpus(data, args.image_start, args.module)
    engine_mod = load_engine(args.engine_module)
    result = compare(engine_mod, counts, info)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if not (result["disagreements"] or result["executor_drift"]) else 1
    _print_info(info)
    print()
    print("compared (MODELLED distinct) %d" % result["denominator_modelled_distinct"])
    print("disagreements               %d" % len(result["disagreements"]))
    print("executor drift              %d" % len(result["executor_drift"]))
    for row in result["disagreements"]:
        print("DISAGREE 0x%04x x%d  engine=%s sh4dis=%s (%s)"
              % (row["opcode"], row["count"], row["engine"], row["sh4dis"],
                 row["sh4dis_text"]))
    for row in result["executor_drift"]:
        print("DRIFT    0x%04x x%d  %s (table form %s)"
              % (row["opcode"], row["count"], row["reason"], row["form"]))
    return 0 if not (result["disagreements"] or result["executor_drift"]) else 1


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------

def selftest():
    fails = []

    def check(label, got, want):
        if got != want:
            fails.append("%s: got %r want %r" % (label, got, want))

    engine_mod = default_engine
    # classify: five buckets reached on hand-made opcodes
    check("classify nop", classify(engine_mod, 0x0009)[0], "MODELLED")
    check("classify fpu", classify(engine_mod, 0xF000)[0], "FPU")
    check("classify trapa", classify(engine_mod, 0xC300)[0], "TRAP")
    check("classify div1 modelled (M9.48)", classify(engine_mod, 0x3624)[0],
          "MODELLED")
    check("classify div0u modelled", classify(engine_mod, 0x0019)[0], "MODELLED")
    check("classify ldtlb", classify(engine_mod, 0x0038)[0], "MMU")
    check("classify mac.l modelled", classify(engine_mod, 0x011F)[0], "MODELLED")
    # compare on a synthetic corpus: no disagreement for a modelled opcode.
    counts = collections.Counter({0x0009: 3, 0xE001: 1, 0x011F: 2})
    info = {"module": "syn", "image_start": 0, "records": 0, "read_records": 0,
            "unreadable_records": 0, "covered_bytes": 0, "instructions": 6,
            "distinct": 3, "gap_bytes": 0, "gap_halfwords": 0}
    check("compare: synthetic all agree",
          compare(engine_mod, counts, info)["disagreements"], [])
    # Negative control: a sh4dis table that puts div0s's Rm in the wrong
    # nibble must be reported as a disagreement on a div0s opcode.
    saved = sh4dis.OPERAND_TABLE
    try:
        sh4dis.OPERAND_TABLE = ((0xF00F, 0x2007, "div0s", False, True),) + saved
        bad = compare(engine_mod, collections.Counter({0x2B67: 1}), info)
        check("compare: wrong-nibble control disagrees",
              bool(bad["disagreements"]), True)
    finally:
        sh4dis.OPERAND_TABLE = saved

    # Table/executor drift over every possible halfword: a form the table
    # names as modelled must not be rejected by the executor.  This is the
    # image-free version of the differential's drift column and the check a
    # silent executor regression (M9.36's H51 class) trips.
    drift = []
    for w in range(0x10000):
        form, _rn, _rm, _d = engine_mod.decode_fields(w)
        if form in ("unknown", "fpu", "rte") or form in INTEGER_OUT_OF_SCOPE:
            continue
        if w in MMU_OPCODES:
            continue
        probe = _probe(engine_mod)
        try:
            probe._execute(w, 0x1000)
        except engine_mod.Trap:
            pass  # trapa is Trap by design, not a rejection
        except engine_mod.IllegalInstruction:
            drift.append(hex(w))
        except engine_mod.EngineError:
            pass  # decoded and faulted outside the probe pages: modelled
        except Exception as exc:  # noqa: BLE001 -- host crash is drift
            drift.append("%s:%s" % (hex(w), type(exc).__name__))
    check("all 65536 halfwords: no executor drift", drift[:8], [])

    # M9.49: a host exception inside an arm is not MODELLED.  An engine whose
    # mac.w arm raises NameError once its loads succeed must be reported, and
    # the probe page must let mac.w's loads succeed (the old 4-byte stub
    # faulted on @Rn first and hid the crash).
    class _CrashingPySh4(engine_mod.PySh4):
        def _execute(self, insn, pc):
            if insn & 0xF00F == 0x400F:
                self._load(self._regs["r%d" % ((insn >> 8) & 0xF)], 2)
                raise NameError("name 'rm' is not defined")
            return super()._execute(insn, pc)

    class _CrashingModule:
        pass

    crashing = _CrashingModule()
    for name in ("decode_fields", "Trap", "IllegalInstruction", "EngineError"):
        setattr(crashing, name, getattr(engine_mod, name))
    crashing.PySh4 = _CrashingPySh4
    check("classify host NameError is not MODELLED",
          classify(crashing, 0x412F)[0], "IN_SCOPE_UNMODELLED")
    check("classify mac.w modelled (M9.49)", classify(engine_mod, 0x412F),
          ("MODELLED", "mac.w"))
    crash_cmp = compare(crashing, collections.Counter({0x412F: 1}), info)
    check("compare: host crash is executor drift",
          [d["form"] for d in crash_cmp["executor_drift"]], ["mac.w"])

    for line in fails:
        print("FAIL", line)
    print("decode_audit selftest: %s" % ("OK" if not fails else "FAILED"))
    return 0 if not fails else 1

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("image")
        p.add_argument("module")
        p.add_argument("--image-start", type=lambda s: int(s, 0), default=0x200200)
        p.add_argument("--build", default="EU2011")
        p.add_argument("--engine-module", default=None)
        p.add_argument("--json", action="store_true")

    p = sub.add_parser("compare")
    common(p)
    p = sub.add_parser("census")
    common(p)
    p.add_argument("--top", type=int, default=0)
    sub.add_parser("selftest")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.cmd == "selftest" or args.cmd is None and "--selftest" in (argv or []):
        return selftest()
    if args.cmd == "census":
        return cmd_census(args)
    if args.cmd == "compare":
        return cmd_compare(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        raise SystemExit(selftest())
    raise SystemExit(main())
