#!/usr/bin/env python3
"""Country / location-table / service coverage of ``TMC/reception.dat`` (M4.92).

The row grammar is **not** re-derived here: it is taken from
``tools/tmc_reception.py:parse_rows`` (C-2320–C-2322), which reads the 8-byte
rows ``ff 0f CC LTN 00 ff ff ff`` and the one GB row ``03 0a CC LTN ...``.
``CC`` is the RDS country-code nibble (IEC 62106 Annex D); ``LTN`` is the TMC
location-table number.  Country attribution of the 14 service rows is inherited
from C-2320–C-2322 / C-5400–C-5403 and ``docs/format/rdstm.md``.

Commands::

    tmc_coverage.py --selftest
    tmc_coverage.py report EU2011=<image-or-reception.dat> [LABEL=<path> ...]

A ``*.img`` argument is treated as a raw card image and ``TMC/reception.dat``
is read out with the committed read-only FAT walker
``tools/ze0-viewer/tools_ze0/fatread.py``; any other path is read as the file
itself.  Stdlib only; no vendor bytes are written anywhere.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from collections import OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import tmc_reception as tr  # noqa: E402  (the decoder and the RDS CC table)

FATREAD_DIR = HERE / "ze0-viewer" / "tools_ze0"
sys.path.insert(0, str(FATREAD_DIR))

# ISO 3166 numeric -> two-letter code; the keys are exactly those of
# tools/tmc_reception.py:44 (RDS_CC), so the CC mapping has one source.
ISO_NAME = {
    40: "AT", 56: "BE", 203: "CZ", 208: "DK", 246: "FI", 250: "FR", 276: "DE",
    380: "IT", 528: "NL", 578: "NO", 616: "PL", 724: "ES", 752: "SE", 756: "CH",
    826: "GB",
}

# (CC, LTN) -> country, established by C-2320–C-2322 / C-5400–C-5403 and
# docs/format/rdstm.md ("All 14 tables ... CZ, CH, IT, BE, FI, NL, DK, AT,
# GB, DE, ES, SE, FR, NO").  The LTN disambiguates CC values shared by two
# countries (6 = BE/FI, 14 = ES/SE, 15 = FR/NO).
SERVICE_COUNTRY = {
    (0x2, 0x19): "CZ", (0x4, 0x09): "CH", (0x5, 0x01): "IT", (0x6, 0x01): "BE",
    (0x6, 0x11): "FI", (0x8, 0x11): "NL", (0x9, 0x09): "DK", (0xa, 0x01): "AT",
    (0xc, 0x0a): "GB", (0xd, 0x01): "DE", (0xe, 0x11): "ES", (0xe, 0x21): "SE",
    (0xf, 0x20): "FR", (0xf, 0x31): "NO",
}

POLAND_CC = tr.RDS_CC[616]  # 3, from the tool's own IEC 62106 table

CC_TO_NAMES: dict[int, list[str]] = {}
for _iso, _cc in tr.RDS_CC.items():
    CC_TO_NAMES.setdefault(_cc, []).append(ISO_NAME[_iso])
for _names in CC_TO_NAMES.values():
    _names.sort()


def country_for(cc: int, ltn: int) -> str:
    """Country code of a service row, or a CCn fallback for an unknown CC."""
    known = SERVICE_COUNTRY.get((cc, ltn))
    if known:
        return known
    names = CC_TO_NAMES.get(cc)
    if names:
        return "/".join(names)
    return f"CC{cc:x}"


def analyze(data: bytes) -> dict:
    """Group decoded reception.dat rows into country -> tables -> services."""
    rows = tr.parse_rows(data)
    groups: dict[str, dict] = OrderedDict()
    for cc, ltn, kind in rows:
        name = country_for(cc, ltn)
        g = groups.setdefault(name, {"ccs": set(), "ltns": set(), "n": 0, "kinds": []})
        g["ccs"].add(cc)
        g["ltns"].add(ltn)
        g["n"] += 1
        g["kinds"].append(kind)
    return {
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "row_slots": len(data) // 8,
        "decoded_rows": len(rows),
        "country_field": bool(rows),
        "groups": groups,
        "poland": "PL" in groups,
        "poland_cc": POLAND_CC,
    }


def read_source(path: str) -> tuple[str, bytes]:
    """Read reception.dat bytes from a raw card image or a bare file."""
    p = Path(path)
    if p.suffix.lower() == ".img":
        from fatread import Fat  # imported lazily: selftest needs no image

        fat = Fat(str(p))
        fat.open_part(fat.parts[0][2])
        target = None

        def walk(cluster, prefix):
            nonlocal target
            for name, isdir, child, size in fat.readdir(cluster):
                rel = f"{prefix}/{name}" if prefix else name
                if isdir:
                    walk(child, rel)
                elif name.lower() == "reception.dat":
                    target = (rel, child, size)

        walk(None, "")
        if target is None:
            raise FileNotFoundError(f"{p} has no TMC/reception.dat")
        rel, cluster, size = target
        # Truncate to the directory-entry size: the rest of the cluster chain
        # belongs to other files and must not be decoded as reception rows.
        data = fat.read_clusters(cluster, size)
        return rel, data
    return p.name, p.read_bytes()


def _md_table(result: dict) -> str:
    lines = [
        "| country | CC | location tables (LTN) | service rows |",
        "| --- | --- | --- | --- |",
    ]
    for name, g in result["groups"].items():
        ccs = ", ".join(f"{c:x}" for c in sorted(g["ccs"]))
        ltns = ", ".join(str(n) for n in sorted(g["ltns"]))
        lines.append(f"| {name} | {ccs} | {ltns} | {g['n']} |")
    if not result["poland"]:
        lines.append(f"| PL | {result['poland_cc']:x} | — | 0 |")
    return "\n".join(lines)


def cmd_report(a) -> int:
    specs = []
    for arg in a.sources:
        if "=" not in arg:
            print(f"error: expected LABEL=PATH, got {arg!r}", file=sys.stderr)
            return 2
        label, path = arg.split("=", 1)
        specs.append((label, path))

    print("TMC reception coverage (tools/tmc_coverage.py)")
    print("decoder: tools/tmc_reception.py parse_rows; country map: C-2320..C-2322 / C-5400..C-5403")
    print()
    results = []
    for label, path in specs:
        rel, data = read_source(path)
        r = analyze(data)
        r["label"] = label
        r["rel"] = rel
        results.append(r)
        print(f"### {label} — {rel}")
        print(f"size {r['size']} B   sha256 {r['sha256']}   "
              f"row slots {r['row_slots']}   decoded service rows {r['decoded_rows']}")
        if not r["country_field"]:
            print("NO COUNTRY FIELD: no CC/LTN row decoded — coverage is decided elsewhere; stop.")
            continue
        print(_md_table(r))
        print()

    if all(r["country_field"] for r in results):
        verdict = " ".join(f"{r['label']}={'present' if r['poland'] else 'absent'}"
                           for r in results)
        same = len({r["sha256"] for r in results}) == 1
        print(f"Poland (PL, CC {POLAND_CC:x}): {verdict}")
        if same:
            print("Note: the reception.dat files are byte-identical on all listed cards.")
        print("Consequence: reception.dat is the receiver-side service list. Without a "
              f"CC {POLAND_CC:x} (Poland) service, generated Polish RDSTM001/LCTBL001 "
              "location data is never requested by the receiver; a Polish service entry "
              "must be added to reception.dat as well.")
    return 0


# --------------------------------------------------------------------------
# synthetic self-test (no vendor bytes)
def _row(cc: int, ltn: int, kind: str = "ff0f") -> bytes:
    if kind == "03":
        return bytes([0x03, 0x0A, cc, ltn, 0x00, 0xFF, 0xFF, 0xFF])
    return bytes([0xFF, 0x0F, cc, ltn, 0x00, 0xFF, 0xFF, 0xFF])


def _selftest() -> int:
    fails: list[str] = []

    def check(name: str, cond: bool) -> None:
        if not cond:
            fails.append(name)

    eu = b"".join(_row(cc, ltn, kind) for (cc, ltn), _name in SERVICE_COUNTRY.items()
                  for kind in ["03" if (cc, ltn) == (0xC, 0xA) else "ff0f"])
    r = analyze(eu)
    check("14 decoded service rows", r["decoded_rows"] == 14)
    check("14 countries", len(r["groups"]) == 14)
    check("Poland absent on EU-like file", not r["poland"])
    check("Poland CC from tool", POLAND_CC == 3)
    check("country_field present", r["country_field"])

    pl = eu + _row(POLAND_CC, 1)
    rp = analyze(pl)
    check("positive Poland row present", rp["poland"] and "PL" in rp["groups"])
    check("positive Poland row counted", rp["groups"]["PL"] == {
        "ccs": {3}, "ltns": {1}, "n": 1, "kinds": ["ff0f"]})

    unknown = analyze(_row(1, 0x7F))
    check("unknown CC not assigned a country", "CC1" in unknown["groups"])

    no_field = analyze(bytes([0x01, 0x3E, 0x0F, 0x1E, 0, 0xFF, 0xFF, 0xFF]))
    check("falsifier: no country field", not no_field["country_field"]
          and no_field["decoded_rows"] == 0)

    check("image source detected", Path("x.img").suffix.lower() == ".img")
    check("bare file source detected", Path("reception.dat").suffix.lower() != ".img")

    print(f"selftest: {'OK' if not fails else 'FAIL ' + ', '.join(fails)}")
    return 0 if not fails else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("report", help="one command: coverage for all LABEL=PATH cards")
    p.add_argument("sources", nargs="+", help="LABEL=image.img or LABEL=reception.dat")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if a.cmd == "report":
        return cmd_report(a)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
