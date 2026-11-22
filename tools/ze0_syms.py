#!/usr/bin/env python3
"""Symbol table for the ZE0 guest: ``module!name`` for every ROM function.

Debugging the guest means typing VAs out of EXP records.  This tool turns a
card's CE ROM images into one JSON symbol file and answers both directions:

* every ``.pdata`` function start (``tools/pdata.py``) becomes a symbol named
  after the module's export when the export VA equals the start, otherwise
  after a known role from the firmware tables, otherwise ``fn_0x<VA>``;
* export names come from ``cerom.CERom.exports``; in build A 136 modules carry
  4,606 named exports and 3,508 of them land on a pdata start (``Navi.exe``
  itself exports none, so its symbols are role names and ``fn_0x…``);
* known role names come from ``tools/build_targets.py`` (the one owner of the
  per-build reader VAs) and from the frozen EU/US fixture
  ``tools/fixtures/fn_match_eu_us_2011.json``.  The EU/US column is chosen by
  the image SHA-256 the fixture pins, so a US role VA can never be pasted onto
  the EU build (one such VA, ``0x41bbec``, is an EU function start too).

The three CE segments of one image are separate builds: A ``0x200200`` (apps,
``Navi.exe``), B ``0x3e00200`` and C ``0x5200200`` (kernel/updaters).  A VA
resolves to a module by the module's pdata span, so the overlapping DLL
ranges of A and B/C (M8.C1d) cannot make a start land in the wrong build --
each build is looked up on its own.

Usage::

  ze0_syms.py IMG -o syms.json            # every build A, B, C
  ze0_syms.py IMG lookup 'Navi.exe!mmain_reader'
  ze0_syms.py IMG lookup 0x0041a438
  ze0_syms.py IMG --builds A lookup 0x0041a438
  ze0_syms.py IMG verify                  # cross-build attribution check
  ze0_syms.py --selftest

``lookup`` prints ``<build> <module>!<name> = <VA>`` for a name and
``<build> <VA> = <module>!<name> (<start>+<off>)`` for an address; a start
owned by more than one module of one build prints every owner (the table has
such starts, e.g. ``gwes.exe``/``shell.exe``) and marks them ``ambiguous``.
A name is matched case-insensitively, module-first; ``fn_0x…`` is always an
alias, so an unnamed function still round-trips.  ``verify`` checks the falsifier:
every build-shared function start still resolves to *each* of its owning
``build!module`` pairs, so the overlapping DLL ranges of A and B/C cannot make
a start silently resolve into the wrong build.

Stdlib only; the vendor image is never written to the repo.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cerom  # noqa: E402
import pdata  # noqa: E402

SCHEMA = "osm2leaf.ze0-syms/v1"
BUILDS = (("A", 0x200200), ("B", 0x3E00200), ("C", 0x5200200))
FIXTURE = os.path.join(HERE, "fixtures", "fn_match_eu_us_2011.json")


# --------------------------------------------------------------------------
# Known role names (docs/format tables, owned by build_targets/fixture)
# --------------------------------------------------------------------------


def _fixture_heads(path=FIXTURE):
    """``(eu_sha, us_sha)`` pinned by the frozen EU/US fixture, or Nones."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, ValueError):
        return None, None
    eu = (doc.get("eu_head") or {}).get("sha256")
    us = (doc.get("us_head") or {}).get("sha256")
    return eu, us


def _fixture_roles(path=FIXTURE):
    """``(eu, us)`` lists of ``{va, names}`` from the frozen reader fixture."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, ValueError):
        return [], []
    eu, us = {}, {}
    for row in doc.get("rows", []):
        e = int(row["eu_va"], 16) if row.get("eu_va") else None
        u = row.get("us_va") or row.get("us_candidate")
        u = int(u, 16) if u else None
        label = _slug(row.get("role") or "")
        if e and label:
            eu.setdefault(e, []).append(label)
        if u and label:
            us.setdefault(u, []).append(label)
    return _rows(eu), _rows(us)


def _slug(text):
    """A short identifier from a role description (first clause)."""
    text = text.split("(")[0].strip()
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "_":
            out.append("_")
    return "".join(out).strip("_")


def _rows(table):
    # First-seen order, not alphabetical: build_targets.py is the owner of the
    # canonical role name (``mmain_reader``); a fixture slug (``mmain``) is an
    # alias and must not become the name gdb prints.
    return [{"va": va, "names": list(dict.fromkeys(names))}
            for va, names in sorted(table.items())]


def known_roles(image_sha256, fixture=FIXTURE, roles=None):
    """Role rows ``[{va, names}]`` for an image, selected by its SHA-256.

    The fixture pins the EU and US 2011 heads; an unrecognised image (a
    synthetic selftest ROM, another year) gets no role names, never a guess.
    ``roles`` overrides the selection for tests.
    """
    if roles is not None:
        return roles
    eu_sha, us_sha = _fixture_heads(fixture)
    eu_roles, us_roles = _fixture_roles(fixture)
    if image_sha256 and eu_sha and image_sha256 == eu_sha:
        build = "eu2011"
    elif image_sha256 and us_sha and image_sha256 == us_sha:
        build = "us2011"
    else:
        return []
    try:
        import build_targets
    except Exception:  # noqa: BLE001 - a missing owner leaves the fixture only
        return us_roles if build == "us2011" else eu_roles
    table = {}
    for key, _tool, _kind, eu, us, _what in build_targets.ROLES:
        va = us if build == "us2011" else eu
        if va:
            table.setdefault(va, []).append(key)
    fixture_rows = us_roles if build == "us2011" else eu_roles
    for row in fixture_rows:
        table.setdefault(row["va"], []).extend(row["names"])
    return _rows(table)


# --------------------------------------------------------------------------
# Build one segment into a module/function document
# --------------------------------------------------------------------------


def _image_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def build_segment(data, image_start, roles=(), cache_dir=None):
    """One build's ``{build, image_start, modules, stats}`` document.

    A module without an exception directory is listed with ``functions: []``
    and ``pdata: "NO-PDATA"`` -- never invented.  A module whose table fails
    to decode is ``pdata: "ERROR"`` and is also counted in ``stats.errors``.
    """
    rom = cerom.CERom(data, image_start)
    role_at = {}
    for row in roles:
        role_at.setdefault(row["va"], []).extend(row["names"])
    modules = []
    stats = dict(modules=0, with_pdata=0, no_pdata=0, errors=0,
                 functions=0, named=0, exports=0, roles=0, roles_unplaced=0)
    placed_roles = set()
    for mod in rom.modules():
        name = mod["name"] or "?"
        stats["modules"] += 1
        try:
            vbase = rom.e32(mod)["vbase"]
        except Exception:  # noqa: BLE001 - a broken e32 is not a module we can name
            vbase = mod.get("load") or 0
        entry = dict(name=name, base=vbase, load=mod.get("load"),
                     pdata="NO-PDATA", functions=[])
        try:
            records, _meta = pdata.load_table(data, image_start, name, cache_dir)
        except pdata.NoPdata:
            records = None
        except Exception as exc:  # noqa: BLE001 - listed as ERROR, never guessed
            entry["pdata"] = "ERROR"
            entry["error"] = "%s: %s" % (type(exc).__name__, exc)
            stats["errors"] += 1
            modules.append(entry)
            continue
        if records is None:
            stats["no_pdata"] += 1
            modules.append(entry)
            continue
        entry["pdata"] = "OK"
        stats["with_pdata"] += 1

        exports = {}
        try:
            for _ordinal, export_name, rva in rom.exports(mod):
                va = vbase + rva
                exports.setdefault(va, export_name)
                stats["exports"] += 1
        except Exception:  # noqa: BLE001 - an export directory that fails is skipped
            pass

        functions = []
        for begin, _prolog, length in records:
            names = list(role_at.get(begin, []))
            if begin in exports:
                names.append(exports[begin])
            canonical = names[0] if names else "fn_0x%08x" % begin
            aliases = sorted({n for n in names[1:] if n != canonical}
                             | {"fn_0x%08x" % begin})
            functions.append(dict(start=begin, end=begin + length,
                                  name=canonical, aliases=aliases))
            if names:
                stats["named"] += 1
            if begin in role_at:
                placed_roles.add(begin)
                stats["roles"] += len(role_at[begin])
        entry["functions"] = functions
        stats["functions"] += len(functions)
        modules.append(entry)

    starts = set()
    for mod in modules:
        starts.update(f["start"] for f in mod["functions"])
    stats["roles_unplaced"] = sum(1 for va in role_at if va not in starts)
    stats["roles_total"] = sum(len(v) for v in role_at.values())
    return dict(build=None, image_start=image_start, modules=modules,
                stats=stats)


def build_document(image_path, image_start=None, builds=("A", "B", "C"),
                   roles=None, cache_dir=None, fixture=FIXTURE):
    """The whole ``syms.json`` document for one image."""
    data = open(image_path, "rb").read()
    sha = _image_sha256(image_path)
    known = known_roles(sha, fixture=fixture, roles=roles)
    out = dict(schema=SCHEMA, image=os.path.basename(image_path),
               image_sha256=sha, source="tools/ze0_syms.py",
               builds=[], stats=dict())
    wanted = set(builds)
    for tag, start in BUILDS:
        if tag not in wanted:
            continue
        if image_start is not None and start != image_start:
            continue
        try:
            segment = build_segment(data, start, known, cache_dir)
        except ValueError as exc:
            if image_start is not None:
                raise
            segment = dict(build=None, image_start=start, modules=[],
                           stats=dict(error=str(exc)))
        segment["build"] = tag
        out["builds"].append(segment)
    if not out["builds"]:
        raise ValueError("no CE segment selected (builds %s)" % ",".join(builds))
    return out


# --------------------------------------------------------------------------
# Lookups
# --------------------------------------------------------------------------


def _module_span(module):
    functions = module.get("functions") or []
    if not functions:
        return None
    return functions[0]["start"], functions[-1]["end"]


def functions_of(module):
    return module.get("functions") or []


def _function_containing(module, va):
    functions = functions_of(module)
    starts = [f["start"] for f in functions]
    i = bisect.bisect_right(starts, va) - 1
    if i < 0:
        return None
    f = functions[i]
    return f if f["start"] <= va < f["end"] else None


def addr_lookup(document, va):
    """``[{build, module, function, offset}]`` for one process VA."""
    hits = []
    for segment in document.get("builds", []):
        for module in segment.get("modules", []):
            fn = _function_containing(module, va)
            if fn is not None:
                hits.append(dict(build=segment["build"], module=module["name"],
                                 function=fn, offset=va - fn["start"]))
    return hits


def name_lookup(document, module, name):
    """``[{build, module, function}]`` for ``module!name`` (case-insensitive)."""
    want_module = (module or "").lower()
    want_name = name.lower()
    hits = []
    for segment in document.get("builds", []):
        for mod in segment.get("modules", []):
            if want_module and mod["name"].lower() != want_module:
                continue
            for fn in functions_of(mod):
                names = [fn["name"]] + list(fn.get("aliases") or [])
                if any((n or "").lower() == want_name for n in names):
                    hits.append(dict(build=segment["build"], module=mod["name"],
                                     function=fn))
    return hits


def split_symbol(text):
    """``'module!name'`` -> ``(module, name)``; no ``!`` -> ``(None, text)``."""
    if "!" in text:
        module, name = text.split("!", 1)
        return module.strip() or None, name.strip()
    return None, text.strip()


def format_addr_hits(hits, va):
    """Lines for :func:`addr_lookup`."""
    if not hits:
        return ["%#010x = (no module in any build)" % va]
    lines = []
    for hit in hits:
        fn = hit["function"]
        label = "%s!%s" % (hit["module"], fn["name"])
        extra = ""
        if hit["offset"]:
            extra = " (start %#010x+%#x)" % (fn["start"], hit["offset"])
        lines.append("%s %#010x = %s%s" % (hit["build"], va, label, extra))
    if len({(h["build"], h["module"]) for h in hits}) > 1:
        lines.append("ambiguous: %d modules own this start/address" % len(hits))
    return lines


def format_name_hits(hits):
    """Lines for :func:`name_lookup`."""
    if not hits:
        return ["(not found)"]
    lines = ["%s %s!%s = %#010x" % (hit["build"], hit["module"],
                                    hit["function"]["name"],
                                    hit["function"]["start"])
             for hit in hits]
    if len({h["build"] for h in hits}) > 1:
        lines.append("ambiguous: resolves in %d builds" % len(
            {h["build"] for h in hits}))
    return lines


def resolve(document, token):
    """Dispatch one ``lookup`` token: an address (``0x…``/digits) or a name."""
    try:
        va = int(token, 0)
    except ValueError:
        module, name = split_symbol(token)
        return format_name_hits(name_lookup(document, module, name))
    return format_addr_hits(addr_lookup(document, va), va)


def verify_attribution(document):
    """Check every build-shared start resolves to all of its real owners.

    A and B/C have overlapping DLL ranges (M8.C1d): their function starts can
    be numerically equal.  This test is the task's falsifier -- if a start from
    one build were silently attributed to a module of another, the expected
    ``(build, module)`` owner would be missing from :func:`addr_lookup`.
    Within one build several modules may own a start; those are reported too.
    """
    owners = {}
    total = 0
    for segment in document.get("builds", []):
        per_build = {}
        for module in segment.get("modules", []):
            for fn in functions_of(module):
                per_build.setdefault(fn["start"], set()).add(module["name"])
                total += 1
        owners[segment["build"]] = per_build
    tags = sorted(owners)
    pairs = {}
    shared = set()
    for i, first in enumerate(tags):
        for second in tags[i + 1:]:
            both = set(owners[first]) & set(owners[second])
            pairs["%s&%s" % (first, second)] = len(both)
            shared |= both
    missing = []
    for va in sorted(shared):
        got = {(h["build"], h["module"]) for h in addr_lookup(document, va)}
        for tag in tags:
            for module in owners[tag].get(va, ()):
                if (tag, module) not in got:
                    missing.append((tag, module, va))
    multi = {tag: sum(1 for mods in table.values() if len(mods) > 1)
             for tag, table in owners.items()}
    return dict(functions=total, pairs=pairs, shared=len(shared),
                checked=len(shared), missing=missing, multi=multi)


def format_verify(report):
    pairs = ", ".join("%s %d" % (k, v) for k, v in sorted(report["pairs"].items()))
    multi = ", ".join("%s %d" % (k, v) for k, v in sorted(report["multi"].items()))
    lines = [
        "verify: %d functions, shared starts %s (total %d)" % (
            report["functions"], pairs or "none", report["shared"]),
        "verify: checked %d shared starts, %d missing owners" % (
            report["checked"], len(report["missing"])),
        "verify: starts owned by >1 module in one build: %s" % (multi or "none"),
    ]
    for build, module, va in report["missing"][:10]:
        lines.append("verify: MISSING %s!%s at %#010x" % (build, module, va))
    return lines


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _summarise(document):
    for segment in document["builds"]:
        s = segment["stats"]
        if "error" in s:
            print("%s @ %#x: %s" % (segment["build"], segment["image_start"],
                                   s["error"]))
            continue
        print("%s @ %#x: %d modules, %d with pdata, %d NO-PDATA, %d errors, "
              "%d functions, %d named (exports %d, role names %d, %d unplaced)"
              % (segment["build"], segment["image_start"], s["modules"],
                 s["with_pdata"], s["no_pdata"], s["errors"], s["functions"],
                 s["named"], s["exports"], s["roles"], s["roles_unplaced"]))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build or query a module!name symbol table for the ZE0 guest.",
        epilog="See the module docstring for the evidence behind every name.")
    parser.add_argument("image", nargs="?", help="card or firmware-head image")
    parser.add_argument("command", nargs="?", default="build",
                        choices=["build", "lookup", "verify"],
                        help="action (default: build)")
    parser.add_argument("tokens", nargs="*",
                        help="lookup: one or more 'module!name' or 0x addresses")
    parser.add_argument("-o", "--out", metavar="FILE",
                        help="write the symbol document here")
    parser.add_argument("--builds", default="A,B,C",
                        help="comma-separated builds to include (default: A,B,C)")
    parser.add_argument("--image-start", type=lambda s: int(s, 0),
                        help="use exactly one CE segment (0x200200, 0x3e00200, 0x5200200)")
    parser.add_argument("--cache", metavar="DIR",
                        help="decoded-pdata cache directory (tools/pdata.py)")
    parser.add_argument("--no-known", action="store_true",
                        help="do not attach role names from the firmware tables")
    parser.add_argument("--selftest", action="store_true",
                        help="synthetic ROM and lookup checks, no vendor data")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.image:
        parser.error("image is required unless --selftest is given")

    builds = tuple(b.strip().upper() for b in args.builds.split(",") if b.strip())
    roles = [] if args.no_known else None
    try:
        document = build_document(args.image, image_start=args.image_start,
                                  builds=builds, roles=roles, cache_dir=args.cache)
    except (OSError, ValueError) as exc:
        print("ze0_syms: %s" % exc, file=sys.stderr)
        return 2

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(document, handle, separators=(",", ":"))
            handle.write("\n")

    if args.command == "lookup":
        if not args.tokens:
            parser.error("lookup needs at least one token")
        found = 0
        for token in args.tokens:
            lines = resolve(document, token)
            if lines != ["(not found)"] and not lines[0].endswith("(no module in any build)"):
                found += 1
            for line in lines:
                print(line)
        return 0 if found == len(args.tokens) else 1

    if args.command == "verify":
        report = verify_attribution(document)
        for line in format_verify(report):
            print(line)
        return 0 if not report["missing"] else 1

    _summarise(document)
    return 0


# --------------------------------------------------------------------------
# Selftest: a synthetic ROM with a real .pdata exception directory
# --------------------------------------------------------------------------

SYNTH_PDATA_RVA = 0x1100
# vbase 0x8CE00000; exports sit on the first and third start, 0x8CE01240 is bare
SYNTH_STARTS = (0x8CE01100, 0x8CE01140, 0x8CE01200, 0x8CE01240)
SYNTH_ROLE_START = SYNTH_STARTS[1]
SYNTH_BARE_START = SYNTH_STARTS[3]


def synthetic_rom():
    """``cerom.build_synthetic_rom`` plus a four-record ``.pdata``.

    ``NK.EXE`` gets an exception directory at RVA ``0x1100`` (inside its plain
    sec0) holding four starts; its two exports point at the first and third, a
    known role names the second, and the fourth is unnamed (``fn_0x…``).
    ``NAVI.EXE`` keeps no exception directory, so it is a ``NO-PDATA`` module.
    The compressed sec1 is left untouched: functions never read it.
    """
    blob, layout = cerom.build_synthetic_rom()
    data = bytearray(blob)
    records = b"".join(
        struct.pack("<II", start, 0x10 << 8)   # ~0x20-byte body, no prologue
        for start in SYNTH_STARTS)
    file_off = 0x5000 + (SYNTH_PDATA_RVA - 0x1000)
    data[file_off:file_off + len(records)] = records
    # e32 units[6], units[7] = exception directory (rva, size), at e32 + 36 + 24.
    struct.pack_into("<II", data, 0x4000 + 36 + 6 * 4,
                     SYNTH_PDATA_RVA, len(records))
    return bytes(data), layout


def selftest(argv=None):
    checks = 0
    failures = 0

    def check(name, got, want):
        nonlocal checks, failures
        checks += 1
        if got == want:
            print("  ok   %s" % name)
        else:
            failures += 1
            print("  FAIL %s: got %r, want %r" % (name, got, want))

    data, _layout = synthetic_rom()
    roles = [{"va": SYNTH_ROLE_START, "names": ["mmain_reader"]}]
    try:
        segment = build_segment(data, cerom.SYNTH_IMAGE_START, roles)
    except Exception as exc:  # noqa: BLE001 - a selftest must print its failure
        print("  FAIL build_segment raised %s: %s" % (type(exc).__name__, exc))
        print("selftest: FAILED")
        return 1

    modules = {m["name"]: m for m in segment["modules"]}
    check("two modules listed", sorted(modules), ["NAVI.EXE", "NK.EXE"])
    check("NK.EXE has pdata", modules["NK.EXE"]["pdata"], "OK")
    check("NAVI.EXE is NO-PDATA, not an error", modules["NAVI.EXE"]["pdata"],
          "NO-PDATA")
    nk = modules["NK.EXE"]
    check("four function starts",
          [f["start"] for f in nk["functions"]], list(SYNTH_STARTS))
    by_start = {f["start"]: f for f in nk["functions"]}
    check("an export names its start", by_start[SYNTH_STARTS[0]]["name"],
          "MAL_DataVol_getOffset")
    check("a known role names its start", by_start[SYNTH_ROLE_START]["name"],
          "mmain_reader")
    check("the second export names its start", by_start[SYNTH_STARTS[2]]["name"],
          "MAL_DataVol_getSize")
    check("an unnamed start falls back to fn_<VA>",
          by_start[SYNTH_BARE_START]["name"], "fn_0x%08x" % SYNTH_BARE_START)
    check("the export is also a fn_ alias of its start",
          "fn_0x%08x" % SYNTH_STARTS[2] in by_start[SYNTH_STARTS[2]]["aliases"],
          True)
    check("fn_ alias always present",
          "fn_0x%08x" % SYNTH_ROLE_START in by_start[SYNTH_ROLE_START]["aliases"],
          True)

    document = dict(schema=SCHEMA, image="synthetic.img", image_sha256="0" * 64,
                    builds=[dict(build="A",
                                 image_start=cerom.SYNTH_IMAGE_START,
                                 modules=segment["modules"],
                                 stats=segment["stats"])])

    hits = name_lookup(document, "nk.exe", "mmain_reader")
    check("name lookup is case-insensitive on the module", len(hits), 1)
    check("name lookup returns the start", hits[0]["function"]["start"],
          SYNTH_STARTS[1])
    check("role name ignores case", len(name_lookup(document, "NK.EXE",
                                                    "MMAIN_READER")), 1)
    check("export name resolves", len(name_lookup(document, "NK.EXE",
                                                  "MAL_DataVol_getOffset")), 1)
    check("fn_ alias resolves", len(name_lookup(document, "NK.EXE",
                                                 "fn_0x%08x" % SYNTH_STARTS[2])), 1)
    check("a name in the wrong module does not resolve",
          name_lookup(document, "NAVI.EXE", "mmain_reader"), [])
    check("an unknown name does not resolve",
          name_lookup(document, "NK.EXE", "no_such_function"), [])

    hit = addr_lookup(document, SYNTH_STARTS[1])
    check("address at a start resolves", (hit[0]["function"]["start"],
                                          hit[0]["offset"]), (SYNTH_STARTS[1], 0))
    inside = addr_lookup(document, SYNTH_STARTS[1] + 0x10)
    check("address inside resolves to the start", inside[0]["function"]["start"],
          SYNTH_STARTS[1])
    check("inside offset is reported", inside[0]["offset"], 0x10)
    past = SYNTH_STARTS[2] + 0x20
    check("an address past the last function resolves nowhere in NK",
          [h for h in addr_lookup(document, past) if h["module"] == "NK.EXE"], [])

    check("format both ways round-trips the VA",
          format_name_hits(name_lookup(document, "NK.EXE", "mmain_reader")),
          ["A NK.EXE!mmain_reader = %#010x" % SYNTH_STARTS[1]])
    check("format an address names the module",
          format_addr_hits(addr_lookup(document, SYNTH_STARTS[1]), SYNTH_STARTS[1]),
          ["A %#010x = NK.EXE!mmain_reader" % SYNTH_STARTS[1]])
    check("split module!name", split_symbol("Navi.exe!mmain_reader"),
          ("Navi.exe", "mmain_reader"))
    check("no module means every module", split_symbol("mmain_reader"),
          (None, "mmain_reader"))
    check("no known roles for an unrecognised image",
          known_roles("0" * 64, fixture=FIXTURE), [])

    # Two modules owning one start (the A/B/C DLL overlap class): both are
    # printed and the result is marked ambiguous instead of silently picking.
    shared = dict(start=0x1000, end=0x1040, name="fn_0x00001000", aliases=[])
    overlap = dict(schema=SCHEMA, image="two.img", image_sha256="0" * 64,
                   builds=[
                       dict(build="B", image_start=0x3E00200, stats={},
                            modules=[dict(name="filesys.exe", base=0,
                                          functions=[dict(shared)])]),
                       dict(build="C", image_start=0x5200200, stats={},
                            modules=[dict(name="gwes.exe", base=0,
                                          functions=[dict(shared)])]),
                   ])
    hits = addr_lookup(overlap, 0x1010)
    check("overlapping owners are both returned", len(hits), 2)
    lines = format_addr_hits(hits, 0x1010)
    check("an overlap is marked ambiguous", lines[-1].startswith("ambiguous"), True)
    check("every owner is printed",
          sorted(line.split("= ", 1)[1].split(" (")[0] for line in lines[:2]),
          ["filesys.exe!fn_0x00001000", "gwes.exe!fn_0x00001000"])
    report = verify_attribution(overlap)
    check("verify counts the shared start", (report["functions"], report["shared"]),
          (2, 1))
    check("verify finds no missing owner", report["missing"], [])
    check("verify reports no multi-owner build here", report["multi"],
          {"B": 0, "C": 0})
    # The same module name in two builds: dropping C's row must be detected.
    twin = dict(overlap, builds=[
        dict(build="B", image_start=0x3E00200, stats={},
             modules=[dict(name="filesys.exe", base=0, functions=[dict(shared)])]),
        dict(build="C", image_start=0x5200200, stats={},
             modules=[dict(name="filesys.exe", base=0, functions=[dict(shared)])]),
        dict(build="A", image_start=0x200200, stats={},
             modules=[dict(name="gwes.exe", base=0, functions=[dict(shared)]),
                      dict(name="shell.exe", base=0, functions=[dict(shared)])]),
    ])
    missing = verify_attribution(twin)["missing"]
    check("verify finds all cross-build owners", missing, [])
    check("verify flags the multi-owner build",
          verify_attribution(twin)["multi"], {"A": 1, "B": 0, "C": 0})
    broken = dict(twin, builds=[
        twin["builds"][0],
        dict(build="C", image_start=0x5200200, stats={},
             modules=[dict(name="filesys.exe", base=0,
                           functions=[dict(start=0x1000, end=0x1000,
                                           name="fn_0x00001000")])]),
        twin["builds"][2],
    ])
    check("verify fails when a span cannot be found",
          verify_attribution(broken)["missing"], [("C", "filesys.exe", 0x1000)])
    check("build_targets key is canonical, fixture slug an alias",
          _rows({0x41A438: ["mmain_reader", "mmain"]})[0]["names"],
          ["mmain_reader", "mmain"])

    print("checks: %d, failures: %d" % (checks, failures))
    print("selftest: OK" if failures == 0 else "selftest: FAILED")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
