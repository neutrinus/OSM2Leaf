#!/usr/bin/env python3
"""Driver table of the CE ROM registry as loaded: drivers, IoBase/Irq, load order (M8.E2).

Static route: the ROM hives ``boot.hv`` and ``default.hv`` of one CE segment
are decoded with the kernel's own routine (``cerom.py`` files decode, M1.4 /
M1.21; nothing is written to disk) and parsed with ``tools/cehive.py``.
Printed per segment:

* ``init``: the ``LaunchNN``/``DependNN`` process list (start order = NN).
* ``Drivers\\BuiltIn`` (the bus ``BusEnum.dll`` enumerates): each subkey's
  ``Dll``, ``Prefix``+``Index``, ``Order``, ``Flags`` and the resource
  values ``IoBase``/``IoLen``/``MemBase``/``MemLen``/``Irq``/``SysIntr``.
  Load order: ascending ``Order``; equal ``Order`` keeps hive order (the
  device manager's enumeration order inside one ``Order`` is not taken from
  the firmware here).
* ``Drivers\\Launch``: the same columns, plus each key's position in the
  compiled-in launch table of ``AppLaunch.dll`` (the BuiltIn driver
  ``AppLch``, prefix ``LDR``).  That table is found structurally: the UTF-16
  string ``\\Drivers\\Launch\\`` repeats at a fixed stride in the module's
  code section; each entry carries a device name (``SCI0:``) before the key.
* ``Drivers\\Resources``: the IRQ/ID resource ranges.

Usage:
  ce_drivers.py --selftest
  ce_drivers.py IMG [--image-start 0x3e00200] [--markdown] [--json OUT]
  ce_drivers.py --hive boot.hv --hive default.hv [--markdown]

Exit codes: 0 ok, 1 self-test failure or a hive that does not parse closed
(dangling links), 2 usage error or no image.  Stdlib only; no vendor bytes
are written (the table prints names and numbers only).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cehive  # noqa: E402

RES_FIELDS = ("IoBase", "IoLen", "MemBase", "MemLen", "Irq", "SysIntr")
DRIVER_ROOTS = ("Drivers\\BuiltIn", "Drivers\\Launch")
LAUNCH_NEEDLE = "\\Drivers\\Launch\\".encode("utf-16-le")
DEFAULT_SEGMENT = 0x3E00200
HIVES = ("boot.hv", "default.hv")


# --------------------------------------------------------------------------
# Hive -> key/value dict
# --------------------------------------------------------------------------

def _num(text):
    try:
        return int(text, 16) if text.startswith("0x") else None
    except (AttributeError, ValueError):
        return None


def hive_keys(blob):
    """(ordered {path: {name: (type, text)}}, stats)."""
    rows, st = cehive.tree(blob)
    keys = {}
    for path, name, typ, text in rows:
        k = keys.setdefault(path, {})
        if name is not None:
            k[name] = (typ, text)
    return keys, st


def drivers(keys, root, hive):
    """Driver rows of the direct subkeys of ``root``, in hive order."""
    out = []
    pre = root + "\\"
    for path, vals in keys.items():
        if not path.startswith(pre) or "\\" in path[len(pre):]:
            continue
        get = lambda n: vals.get(n, (None, None))[1]  # noqa: E731
        row = {"hive": hive, "root": root, "key": path[len(pre):],
               "dll": get("Dll"), "prefix": get("Prefix"), "index": _num(get("Index")),
               "order": _num(get("Order")), "flags": _num(get("Flags")),
               "entry": get("Entry")}
        for f in RES_FIELDS:
            row[f] = _num(get(f)) if vals.get(f, (None,))[0] == "DWORD" else get(f)
        out.append(row)
    # stable sort: Order ascending, missing Order last, hive order kept
    return sorted(out, key=lambda r: (r["order"] is None, r["order"] or 0))


def init_launch(keys):
    vals = keys.get("init", {})
    out = []
    for name, (_t, text) in vals.items():
        m = re.fullmatch(r"Launch(\d+)", name)
        if m:
            n = int(m.group(1))
            dep = vals.get("Depend%d" % n, (None, None))[1]
            out.append({"n": n, "exe": text, "depend": dep})
    return sorted(out, key=lambda r: r["n"])


def resources(keys):
    out = {}
    for path, vals in keys.items():
        if path.startswith("Drivers\\Resources\\"):
            out[path.split("\\")[-1]] = {k: v[1] for k, v in vals.items()}
    return out


# --------------------------------------------------------------------------
# AppLaunch.dll compiled-in table
# --------------------------------------------------------------------------

def _utf16_back(blob, end, limit=64):
    """Printable UTF-16 run ending just before ``end`` (skipping NUL pad)."""
    e = end
    while e >= 2 and blob[e - 2:e] == b"\0\0":
        e -= 2
    s = e
    while s >= 2 and e - s < limit * 2 and 0x20 <= blob[s - 2] < 0x7F and blob[s - 1] == 0:
        s -= 2
    return blob[s:e].decode("utf-16-le")


def _utf16_fwd(blob, start, limit=128):
    e = start
    while e + 2 <= len(blob) and e - start < limit * 2 and blob[e:e + 2] != b"\0\0":
        e += 2
    return blob[start:e].decode("utf-16-le", "replace")


def launch_table(blob, base):
    """Entries of the ``\\Drivers\\Launch\\`` table: (pos, va, device, key, stride)."""
    hits = []
    i = blob.find(LAUNCH_NEEDLE)
    while i >= 0:
        if i % 2 == 0:
            hits.append(i)
        i = blob.find(LAUNCH_NEEDLE, i + 2)
    if len(hits) < 2:
        return [], None
    gaps = [b - a for a, b in zip(hits, hits[1:])]
    stride = max(set(gaps), key=gaps.count)
    # longest run at that stride
    best, cur = [hits[0]], [hits[0]]
    for a, b in zip(hits, hits[1:]):
        cur = cur + [b] if b - a == stride else [b]
        if len(cur) > len(best):
            best = cur
    rows = []
    for pos, off in enumerate(best):
        key = _utf16_fwd(blob, off + len(LAUNCH_NEEDLE))
        dev = _utf16_back(blob, off)
        rows.append({"pos": pos, "va": base + off, "device": dev, "key": key})
    return rows, stride


# --------------------------------------------------------------------------
# Image binding
# --------------------------------------------------------------------------

def load_from_image(path, image_start):
    import cerom
    with open(path, "rb") as fh:
        data = fh.read(128 << 20)
    rom = cerom.CERom(data, image_start)
    rep = cerom.files_report(rom, data, path, decompress=True, method="auto",
                             names=set(HIVES))
    blobs = rep.get("_blobs", {})
    hives = {}
    for rec in rep["files"]:
        if rec["status"] != "OK":
            raise SystemExit("hive %s did not decode: %s %s"
                             % (rec["name"], rec["status"], rec["error"]))
        hives[rec["name"].lower()] = (blobs[rec["index"]], rec["decoded_sha256"])
    table, stride, mod = [], None, None
    try:
        m = rom.module("AppLaunch.dll")
        s = list(rom.o32(m))[0]
        off = rom.va2file(s["dataptr"])
        table, stride = launch_table(data[off:off + s["psize"]], s["realaddr"])
        mod = "AppLaunch.dll sec0 0x%08x" % s["realaddr"]
    except KeyError:
        return hives, table, stride, mod
    # M1.34: the walker's own table (getters, 112 records of 0x310 B).  Its
    # record index replaces the stride position; the stride scan stays as a
    # cross-check (same keys, same count).
    import applaunch_table as alt
    segs = alt.load_segments(path, image_start, "AppLaunch.dll")
    hits = alt.find_getters(segs)
    if len(hits) == 1:
        _cva, count, _bva, base = hits[0]
        recs = alt.parse_table(segs, base, count)
        pre = "\\drivers\\launch\\"
        rec_rows = [{"pos": r["index"], "va": r["va"], "device": r["name"],
                     "key": r["path"][len(pre):], "id": r["id"], "type": r["type"],
                     "waits": [w["id"] for w in r["waits"]]}
                    for r in recs if r["path"].lower().startswith(pre)]
        if [t["key"] for t in rec_rows] != [t["key"] for t in table]:
            raise SystemExit("AppLaunch table: getter records and stride scan disagree")
        table = rec_rows
        mod += "; walker table 0x%08x, %d records (M1.34 getters)" % (base, count)
    return hives, table, stride, mod


def build(hives, table):
    out = {"hives": {}, "init": [], "drivers": [], "resources": {}, "launch_table": table}
    allkeys = {}
    for name in HIVES:
        if name not in hives:
            continue
        blob, sha = hives[name]
        keys, st = hive_keys(blob)
        out["hives"][name] = {"bytes": len(blob), "sha256": sha, **st}
        allkeys[name] = keys
        out["init"] += [dict(r, hive=name) for r in init_launch(keys)]
        for root in DRIVER_ROOTS:
            out["drivers"] += drivers(keys, root, name)
        for k, v in resources(keys).items():
            out["resources"]["%s:%s" % (name, k)] = v
    pos = {}
    for t in table:
        pos.setdefault(t["key"].lower(), t)
    for d in out["drivers"]:
        t = pos.get(d["key"].lower()) if d["root"] == "Drivers\\Launch" else None
        d["table_pos"] = t["pos"] if t else None
        d["table_device"] = t["device"] if t else None
        d["table_id"] = t.get("id") if t else None
        d["table_waits"] = t.get("waits") if t else None
    keyset = {d["key"].lower() for d in out["drivers"] if d["root"] == "Drivers\\Launch"}
    out["table_without_key"] = [t["key"] for t in table if t["key"].lower() not in keyset]
    return out


def _h(v):
    if v is None:
        return "-"
    return "0x%x" % v if isinstance(v, int) else str(v)


def print_text(out, markdown=False):
    for name, st in out["hives"].items():
        print("# %s: %d B sha256 %s keys %d values %d dangling %d"
              % (name, st["bytes"], st["sha256"], st["keys"], st["values"], st["dangling"]))
    print("init launch order: " + ", ".join(
        "Launch%d=%s%s" % (r["n"], r["exe"], " (Depend %s)" % r["depend"] if r["depend"] else "")
        for r in out["init"]))
    for k, v in out["resources"].items():
        print("resources %s: %s" % (k, ", ".join("%s=%s" % kv for kv in v.items())))
    cols = ["#", "root", "key", "Dll", "device", "Order", "AppLaunch record", "Flags", "resources"]
    if markdown:
        print("| " + " | ".join(cols) + " |")
        print("| " + " | ".join("---" for _ in cols) + " |")
    n = {}
    for d in out["drivers"]:
        n[d["root"]] = n.get(d["root"], 0) + 1
        dev = "%s%s" % (d["prefix"] or "", "" if d["index"] is None else d["index"])
        res = ", ".join("%s=%s" % (f, _h(d[f])) for f in RES_FIELDS if d[f] is not None)
        cells = ["%d" % n[d["root"]], d["root"].split("\\")[-1] + "/" + d["hive"].split(".")[0],
                 d["key"], d["dll"] or ("(%s)" % d["entry"] if d["entry"] else "-"),
                 dev or "-", _h(d["order"]),
                 "-" if d["table_pos"] is None else "%d %s%s" % (
                     d["table_pos"], d["table_device"],
                     "" if d["table_id"] is None else " id 0x%x waits %s" % (
                         d["table_id"], "/".join("%d" % w for w in d["table_waits"]) or "-")),
                 _h(d["flags"]), res or "-"]
        if markdown:
            print("| " + " | ".join(c if c == "-" or c.isdigit() else "`%s`" % c
                                    for c in cells) + " |")
        else:
            print("  ".join(cells))
    t = out["launch_table"]
    print("AppLaunch Drivers\\Launch records: %d%s; Drivers\\Launch keys with a record %d; "
          "table entries with no hive key %d (%s)"
          % (len(t), "" if not t else " (stride 0x%x)" % out.get("stride", 0),
             sum(1 for d in out["drivers"] if d["table_pos"] is not None),
             len(out["table_without_key"]), ", ".join(out["table_without_key"]) or "-"))


# --------------------------------------------------------------------------
# Self-test (synthetic hive + synthetic table; no vendor bytes)
# --------------------------------------------------------------------------

def _synthetic_hive():
    k, v, pad = cehive._key, cehive._val, cehive._pad4
    dw = lambda x: struct.pack("<I", x)  # noqa: E731
    sz = lambda s: (s + "\0").encode("utf-16-le")  # noqa: E731
    cells = [
        k(1, "Drivers", child=2, sib=10),
        k(2, "BuiltIn", child=3, sib=6, val=30),
        k(3, "Late", sib=4, val=40),
        k(4, "Early", val=50),
        k(6, "Launch", child=7),
        k(7, "SER", val=60),
        k(10, "init", val=70),
        v(30, "Dll", 1, sz("BusEnum.dll")),
        v(40, "Dll", 1, sz("late.dll"), nxt=41),
        v(41, "Order", 4, dw(5), nxt=42),
        v(42, "Prefix", 1, sz("LAT")),
        v(50, "Dll", 1, sz("early.dll"), nxt=51),
        v(51, "Order", 4, dw(1), nxt=52),
        v(52, "IoBase", 4, dw(0x3F8), nxt=53),
        v(53, "Irq", 4, dw(4)),
        v(60, "Dll", 1, sz("ser.dll"), nxt=61),
        v(61, "Prefix", 1, sz("SCI"), nxt=62),
        v(62, "Index", 4, dw(0), nxt=63),
        v(63, "SysIntr", 4, dw(0x1C)),
        v(70, "Launch30", 1, sz("gwes.exe"), nxt=71),
        v(71, "Launch20", 1, sz("device.exe"), nxt=72),
        v(72, "Depend30", 3, bytes.fromhex("1400")),
    ]
    return b"".join(pad(c) for c in cells)


def _synthetic_table():
    stride = 0x40
    blob = bytearray(0x10 + 3 * stride)
    for i, (dev, key) in enumerate((("SCI0:", "SER"), ("GPI1:", "GPIO"), ("NAV1:", "Navigation"))):
        o = 0x10 + i * stride
        d = dev.encode("utf-16-le") + b"\0\0"
        blob[o:o + len(d)] = d
        s = LAUNCH_NEEDLE + key.encode("utf-16-le") + b"\0\0"
        blob[o + 0x14:o + 0x14 + len(s)] = s
    return bytes(blob)


def selftest():
    fails = []

    def check(name, got, want):
        ok = got == want
        print("%s %s%s" % ("ok  " if ok else "FAIL", name, "" if ok else ": got %r want %r" % (got, want)))
        if not ok:
            fails.append(name)

    hv = _synthetic_hive()
    keys, st = hive_keys(hv)
    check("synthetic hive closes", st["dangling"], 0)
    bi = drivers(keys, "Drivers\\BuiltIn", "default.hv")
    check("BuiltIn load order by Order", [d["key"] for d in bi], ["Early", "Late"])
    check("IoBase/Irq as numbers", (bi[0]["IoBase"], bi[0]["Irq"]), (0x3F8, 4))
    check("missing resource is None", bi[1]["IoBase"], None)
    check("init launch order", [(r["n"], r["exe"], r["depend"]) for r in init_launch(keys)],
          [(20, "device.exe", None), (30, "gwes.exe", "1400")])
    tab, stride = launch_table(_synthetic_table(), 0x1000)
    check("launch table stride", stride, 0x40)
    check("launch table entries", [(t["pos"], t["device"], t["key"]) for t in tab],
          [(0, "SCI0:", "SER"), (1, "GPI1:", "GPIO"), (2, "NAV1:", "Navigation")])
    out = build({"default.hv": (hv, "-")}, tab)
    la = [d for d in out["drivers"] if d["root"] == "Drivers\\Launch"]
    check("Launch key matched to table position", (la[0]["table_pos"], la[0]["table_device"]),
          (0, "SCI0:"))
    check("table entries with no hive key", out["table_without_key"], ["GPIO", "Navigation"])
    # negative: a hive with a dangling link is reported
    bad = bytearray(hv)
    i = bad.find(struct.pack("<I", 0x20000000 | 2))
    struct.pack_into("<I", bad, i, 0x20000000 | 99)
    check("dangling link counted (negative)", hive_keys(bytes(bad))[1]["dangling"] > 0, True)
    check("no table without the needle (negative)", launch_table(b"\0" * 64, 0)[0], [])
    print("ce_drivers selftest: %s" % ("FAIL %s" % fails if fails else "PASS"))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("image", nargs="?")
    ap.add_argument("--image-start", type=lambda s: int(s, 0), default=DEFAULT_SEGMENT)
    ap.add_argument("--hive", action="append", help="decoded hive file (boot.hv/default.hv)")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    stride = mod = None
    if a.hive:
        hives = {Path(p).name.lower(): (Path(p).read_bytes(), "-") for p in a.hive}
        table = []
    elif a.image:
        if not os.path.isfile(a.image):
            print("no image at %s" % a.image)
            return 2
        hives, table, stride, mod = load_from_image(a.image, a.image_start)
        print("# segment 0x%x; launch table in %s" % (a.image_start, mod or "- (no AppLaunch.dll)"))
    else:
        ap.error("IMG, --hive or --selftest is required")
    out = build(hives, table)
    out["stride"] = stride
    print_text(out, a.markdown)
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1))
    return 0 if all(st["dangling"] == 0 for st in out["hives"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
