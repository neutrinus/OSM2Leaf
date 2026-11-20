#!/usr/bin/env python3
"""Dump and filter the ``AppLaunch.dll`` launch table (M1.34).

``AppLaunch.dll`` (build B, loaded by ``device.exe`` as
``Drivers\\BuiltIn\\AppLch``) starts every driver and process of the head
unit, ``Navi.exe`` included, from a compiled-in table in its code section
(M1.21, M1.34).  The table is found through two leaf getters that the
launcher main ``fn 0x03bcc680`` (EU2011) calls before the walker:

* the **count getter** ``rts; mov #N,r0`` (``000b e0NN``), and right after it
* the **base getter** ``mov.l @(4,pc),r0; rts; nop; nop; .long BASE``
  (``d001 000b 0009 0009``).

The tool searches the module's executable sections for exactly that byte
pair, so the base and the count come from the code, not from a constant.

Record layout (``0x310`` = 784 bytes; the stride is the ``mov.w`` literal of
the walker ``fn 0x03bcc5b0``, the offsets are the walker's and the thread
procedures' own ``mov.w``/``@(disp,Rn)`` loads, EU2011):

====== ============ ==========================================================
offset type         meaning (reader)
====== ============ ==========================================================
+0x000 u32          launch type 1..9 -> thread proc (``fn 0x03bcc4d0``);
                    any other type gets no proc and is skipped
+0x004 u32          boot-mode mask, ``& mode_mask(CApi_GetBootMode)``
+0x008 u32          model base-type mask (``fn 0x03bcbce4``, CApi_GetModelBaseType)
+0x00c u32          area mask, ``& area_mask(CApi_GetModelArea)``
+0x010 u32          option flags, each bit a capability query (``fn 0x03bcbc18``)
+0x014 WCHAR[32]    name (device prefix or exe name)
+0x054 WCHAR[...]   path / registry key / event name
+0x25c u16          priority of the launcher thread (walker, CeSetThreadPriority)
+0x25e u16          priority of the started process's main thread (type 3/4)
+0x260 u32          number of wait entries
+0x264 16 B each    wait entry ``{u32 id, u32 timeout_ms, u32 arg, u32 0}``
                    (IOCTL_ACM_WAIT_ID ``0x80002004`` on ``ACM9:``)
+0x304 u32          own id, signalled with IOCTL_ACM_SET_ID ``0x80002000`` when
                    the entry is up (ids >= 0xc0 are never signalled)
+0x308 u32          not read by the walker or the thread procs (meaning open)
+0x30c ptr          argument string: command line (type 3/4), entry point
                    (type 2), event name (type 7), or 0
====== ============ ==========================================================

``select`` emulates the walker's filter ``fn 0x03bcc564``: a record starts
when ``(+4 & mode_mask) != 0``, ``(+0xc & area_mask) != 0``, the base-type
test passes and the option flags hold.  Option flags are not emulated: a
selected record with flags != 0 is marked ``opt``.

Usage:
  applaunch_table.py --selftest
  applaunch_table.py IMG [--image-start 0x3e00200] [--module AppLaunch.dll]
                     dump [--json OUT]
  applaunch_table.py IMG [...] imports     # import thunk -> IAT slot -> name
  applaunch_table.py IMG [...] select --area 0x30 [--mode 0] [--base-type 1]
                     [--name Navi.exe]

Stdlib only; addresses come from ``tools/cerom.py``.
Method and the EU2011 run: docs/experiments/EXP-2026-11-20-M1.34-applaunch-table.md
"""

import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cerom  # noqa: E402

REC = 0x310
NAME_OFF, NAME_LEN = 0x14, 0x40
PATH_OFF, PATH_LEN = 0x54, 0x208
WAIT_MAX = (0x304 - 0x264) // 16          # 10 entries fit before the id

TYPE_PROC = {1: "driver (ActivateDevice)", 2: "dll (LoadLibrary+entry)",
             3: "process", 4: "process (suspended until launch gate)",
             5: "NK2", 6: "MountStorage (SD mount + HDD_INFO checks)",
             7: "event", 8: "OpImg", 9: "virtual id"}

# fn 0x03bcb9fc (EU2011): boot mode -> mode mask (braf table 0x03bb1bd8)
MODE_MASK = {0: 0x1, 1: 0x2, 2: 0x4, 3: 0x8, 4: 0x10, 5: 0x1, 6: 0x20,
             7: 0x40, 8: 0x1, 9: 0xffff}
# fn 0x03bcba58 (EU2011): model area -> area mask
AREA_MASK = {0x10: 0x00010000, 0x20: 0x00040000, 0x30: 0x00020000,
             0x40: 0x00080000, 0x50: 0x00100000}
AREA_NAME = {0x10: "Japan", 0x20: "USA", 0x30: "Euro", 0x40: "Russia",
             0x50: "China"}

COUNT_GETTER = bytes.fromhex("0b00")      # rts, then e0NN (mov #N,r0)
BASE_GETTER = bytes.fromhex("01d00b0009000900")   # d001 000b 0009 0009 (LE)


def wstr(b):
    out = []
    for i in range(0, len(b) - 1, 2):
        c = b[i] | (b[i + 1] << 8)
        if c == 0:
            break
        out.append(chr(c))
    return "".join(out)


def find_getters(segs):
    """Return [(count_va, count, base_va, base)] for every getter pair."""
    hits = []
    for base_va, blob in segs:
        i = blob.find(BASE_GETTER)
        while i >= 0:
            if i % 4 == 0 and i >= 4 and blob[i - 4:i - 2] == COUNT_GETTER \
                    and blob[i - 1] == 0xe0 and i + 12 <= len(blob):
                count = blob[i - 2]
                tbl = struct.unpack_from("<I", blob, i + 8)[0]
                hits.append((base_va + i - 4, count, base_va + i, tbl))
            i = blob.find(BASE_GETTER, i + 2)
    return hits


def read_va(segs, va, n):
    for base, blob in segs:
        if base <= va and va + n <= base + len(blob):
            return blob[va - base:va - base + n]
    return None


def parse_record(raw, va):
    typ, mode, btype, area, opt = struct.unpack_from("<5I", raw, 0)
    prio_l, prio_p = struct.unpack_from("<HH", raw, 0x25c)
    nwait = struct.unpack_from("<I", raw, 0x260)[0]
    waits = []
    for k in range(min(nwait, WAIT_MAX)):
        wid, tmo, arg, z = struct.unpack_from("<4I", raw, 0x264 + 16 * k)
        waits.append({"id": wid, "timeout_ms": tmo, "arg": arg})
    rid, u308, argp = struct.unpack_from("<3I", raw, 0x304)
    return {"va": va, "type": typ, "mode_mask": mode, "base_type": btype,
            "area_mask": area, "options": opt,
            "name": wstr(raw[NAME_OFF:NAME_OFF + NAME_LEN]),
            "path": wstr(raw[PATH_OFF:PATH_OFF + PATH_LEN]),
            "prio_launcher": prio_l, "prio_main": prio_p,
            "n_wait": nwait, "waits": waits, "id": rid, "u308": u308,
            "arg_ptr": argp}


def printable_name(s):
    return 0 < len(s) < 32 and all(32 <= ord(c) < 127 for c in s)


def parse_table(segs, base, count):
    recs = []
    for i in range(count):
        raw = read_va(segs, base + i * REC, REC)
        if raw is None:
            raise ValueError("record %d at 0x%08x outside the sections" % (i, base + i * REC))
        r = parse_record(raw, base + i * REC)
        r["index"] = i
        if r["arg_ptr"]:
            a = read_va(segs, r["arg_ptr"], 0x80)
            r["arg"] = wstr(a) if a else None
        else:
            r["arg"] = ""
        recs.append(r)
    return recs


def check_table(recs, segs, base, count):
    """Structural checks; return a list of problems (empty = consistent)."""
    bad = []
    for r in recs:
        if not printable_name(r["name"]):
            bad.append("record %d: name not printable" % r["index"])
        if not 1 <= r["type"] <= 0x10:
            bad.append("record %d: type %d outside 1..16" % (r["index"], r["type"]))
        if r["n_wait"] > WAIT_MAX:
            bad.append("record %d: %d waits > %d" % (r["index"], r["n_wait"], WAIT_MAX))
    nxt = read_va(segs, base + count * REC, REC)
    if nxt is not None:
        r = parse_record(nxt, base + count * REC)
        if printable_name(r["name"]) and 1 <= r["type"] <= 0x10:
            bad.append("record %d (past the count) still looks like a record" % count)
    return bad


def base_type_ok(mask, base_type):
    """fn 0x03bcbce4: model base type 1/2 test bit 1/2; -1 passes; else fails."""
    if base_type == 1:
        return mask & 1 == 1
    if base_type == 2:
        return mask & 2 == 2
    return base_type == -1


def select(recs, area, mode, base_type):
    amask = AREA_MASK.get(area, 0xffffffff)
    mmask = MODE_MASK.get(mode, 0)
    out = []
    for r in recs:
        if (r["mode_mask"] & mmask) and (r["area_mask"] & amask) \
                and base_type_ok(r["base_type"], base_type):
            out.append(r)
    return out, amask, mmask


def load_segments(img, image_start, module):
    with open(img, "rb") as fh:
        data = fh.read(128 << 20)
    rom = cerom.CERom(data, image_start)
    m = rom.module(module)
    segs = []
    for s in rom.o32(m):
        if s["flags"] & cerom.IMAGE_SCN_COMPRESSED:
            continue
        if not s["flags"] & 0x20000000:          # MEM_EXECUTE only
            continue
        off = rom.va2file(s["dataptr"])
        segs.append((s["realaddr"], data[off:off + s["psize"]]))
    return segs


THUNK_SHAPE = (0xd001, 0x6002, 0x402b, 0x0009)   # mov.l @(4,pc),r0; mov.l @r0,r0; jmp @r0; nop


def thunk_names(img, image_start, module):
    """{thunk VA: (IAT slot, name)}: the slot in compressed sec1 is mapped to the
    rva-based import slot (vbase + rva + slot - realaddr), named from the
    import table and, for ordinals, from the exporting module of the same
    segment (same method as tools/mapcode_l3.py resolve_thunks)."""
    with open(img, "rb") as fh:
        data = fh.read(128 << 20)
    rom = cerom.CERom(data, image_start)
    m = rom.module(module)
    vbase = rom.e32(m)["vbase"]
    secs = list(rom.o32(m))
    imports = {slot: (dll, nm, ordn) for dll, slot, nm, ordn in rom.imports(m)}
    exp_cache = {}
    out = {}
    for s in secs:
        if s["flags"] & cerom.IMAGE_SCN_COMPRESSED or not s["flags"] & 0x20000000:
            continue
        off0 = rom.va2file(s["dataptr"])
        blob = data[off0:off0 + s["psize"]]
        for off in range(0, len(blob) - 12, 2):
            if struct.unpack_from("<4H", blob, off) != THUNK_SHAPE:
                continue
            pc = s["realaddr"] + off
            lit = ((pc & ~3) + 8) - s["realaddr"]
            slot = struct.unpack_from("<I", blob, lit)[0]
            name = None
            for d in secs:
                if d["realaddr"] <= slot < d["realaddr"] + d["vsize"]:
                    ent = imports.get(vbase + d["rva"] + slot - d["realaddr"])
                    if ent:
                        dll, nm, ordn = ent
                        if nm is None and ordn is not None:
                            if dll not in exp_cache:
                                try:
                                    exp_cache[dll] = {o: n for o, n, _ in
                                                      rom.exports(rom.module(dll))}
                                except Exception:
                                    exp_cache[dll] = {}
                            nm = exp_cache[dll].get(ordn, "#%d" % ordn)
                        name = "%s!%s" % (dll, nm)
            out[pc] = (slot, name)
    # every import slot, also those called indirectly (``mov.l @rN`` + jsr)
    slots = {}
    for oft, (dll, nm, ordn) in imports.items():
        for d in secs:
            lo = vbase + d["rva"]
            if lo <= oft < lo + d["vsize"]:
                if nm is None and ordn is not None:
                    if dll not in exp_cache:
                        try:
                            exp_cache[dll] = {o: n for o, n, _ in
                                              rom.exports(rom.module(dll))}
                        except Exception:
                            exp_cache[dll] = {}
                    nm2 = exp_cache[dll].get(ordn, "#%d" % ordn)
                else:
                    nm2 = nm
                slots[d["realaddr"] + oft - lo] = "%s!%s" % (dll, nm2)
    return out, slots


def fmt(r):
    w = " ".join("%d/%d" % (x["id"], x["timeout_ms"]) + ("+%d" % x["arg"] if x["arg"] else "")
                 for x in r["waits"])
    return ("%3d 0x%08x t%d mode=%04x bt=%08x area=%08x opt=%08x id=0x%02x "
            "prio=%d/%d %-18s %-34s arg=%r waits[%d]=%s" % (
                r["index"], r["va"], r["type"], r["mode_mask"], r["base_type"],
                r["area_mask"], r["options"], r["id"], r["prio_launcher"],
                r["prio_main"], r["name"], r["path"], r["arg"], r["n_wait"], w))


def run(args):
    if args.cmd == "imports":
        thunks, slots = thunk_names(args.image, args.image_start, args.module)
        for pc, (slot, name) in sorted(thunks.items()):
            print("thunk 0x%08x slot 0x%08x %s" % (pc, slot, name or "UNRESOLVED"))
        for slot, name in sorted(slots.items()):
            print("slot 0x%08x %s" % (slot, name))
        return 0
    segs = load_segments(args.image, args.image_start, args.module)
    hits = find_getters(segs)
    if len(hits) != 1:
        print("getters: %d candidate pairs (need exactly 1)" % len(hits))
        return 2
    cva, count, bva, base = hits[0]
    print("count getter 0x%08x -> %d records; base getter 0x%08x -> table 0x%08x;"
          " record 0x%x bytes; end 0x%08x" % (cva, count, bva, base, REC, base + count * REC))
    recs = parse_table(segs, base, count)
    bad = check_table(recs, segs, base, count)
    print("structure: %s" % ("OK (%d records, names printable, types 1..16, "
                             "no record past the count)" % count if not bad else
                             "FAIL " + "; ".join(bad[:5])))
    if bad:
        return 1
    if args.cmd == "dump":
        for r in recs:
            print(fmt(r))
        if args.json:
            with open(args.json, "w") as fh:
                json.dump({"count_getter": cva, "base_getter": bva, "base": base,
                           "count": count, "records": recs}, fh, indent=1)
    else:
        sel, amask, mmask = select(recs, args.area, args.mode, args.base_type)
        print("select area=0x%02x (%s, mask 0x%08x) mode=%d (mask 0x%04x) base_type=%d: %d of %d"
              % (args.area, AREA_NAME.get(args.area, "WorldWide"), amask, args.mode,
                 mmask, args.base_type, len(sel), count))
        for r in sel:
            if args.name and r["name"].lower() != args.name.lower():
                continue
            print(("opt " if r["options"] else "    ") + fmt(r))
    return 0


# ---------------------------------------------------------------- selftest

def _synthetic(count=3, shift=0):
    base_va = 0x10000
    tbl = 0x10100
    blob = bytearray(0x100 + (count + 1) * REC + 0x100)
    # getters at 0x10010: 000b e0NN | d001 000b 0009 0009 | .long tbl
    struct.pack_into("<HH", blob, 0x10, 0x000b, 0xe000 | count)
    blob[0x14:0x1c] = BASE_GETTER
    struct.pack_into("<I", blob, 0x1c, tbl + shift)
    specs = [(3, 1, 0xffffffff, 0xffff0000, "gwes.exe", 0xc0, []),
             (4, 1, 0xffffffff, 0x00020000, "Navi.exe", 0xa2, [(82, 30000)]),
             (4, 1, 0xffffffff, 0x00040000, "Navi.exe", 0xa2, [(80, 30000)])]
    for i, (t, mode, bt, area, nm, rid, waits) in enumerate(specs[:count]):
        o = tbl - base_va + i * REC
        struct.pack_into("<5I", blob, o, t, mode, bt, area, 0)
        enc = nm.encode("utf-16le")
        blob[o + NAME_OFF:o + NAME_OFF + len(enc)] = enc
        p = ("\\windows\\" + nm).encode("utf-16le")
        blob[o + PATH_OFF:o + PATH_OFF + len(p)] = p
        struct.pack_into("<HHI", blob, o + 0x25c, 0xd9, 0xdc, len(waits))
        for k, (wid, tmo) in enumerate(waits):
            struct.pack_into("<4I", blob, o + 0x264 + 16 * k, wid, tmo, 0, 0)
        struct.pack_into("<3I", blob, o + 0x304, rid, 0, 0)
    return [(base_va, bytes(blob))]


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + name)
        ok = ok and cond

    segs = _synthetic()
    hits = find_getters(segs)
    check("getter pair found once, count 3, base 0x10100",
          hits == [(0x10010, 3, 0x10014, 0x10100)])
    recs = parse_table(segs, 0x10100, 3)
    check("structure check passes on the synthetic table",
          check_table(recs, segs, 0x10100, 3) == [])
    check("record fields (type, name, path, prio, waits, id)",
          recs[1]["type"] == 4 and recs[1]["name"] == "Navi.exe"
          and recs[1]["path"] == "\\windows\\Navi.exe"
          and (recs[1]["prio_launcher"], recs[1]["prio_main"]) == (0xd9, 0xdc)
          and recs[1]["waits"] == [{"id": 82, "timeout_ms": 30000, "arg": 0}]
          and recs[1]["id"] == 0xa2)
    sel, _, _ = select(recs, 0x30, 0, 1)
    check("Euro (area 0x30 -> mask 0x20000) selects gwes + the 0x20000 Navi only",
          [r["index"] for r in sel] == [0, 1])
    sel, _, _ = select(recs, 0x20, 0, 1)
    check("USA (area 0x20 -> mask 0x40000) selects gwes + the 0x40000 Navi only",
          [r["index"] for r in sel] == [0, 2])
    sel, _, _ = select(recs, 0x30, 1, 1)
    check("mode 1 (mask 2) selects nothing with mode mask 1", sel == [])
    check("base type 3 fails, -1 passes", not base_type_ok(0xffffffff, 3)
          and base_type_ok(1, -1) and not base_type_ok(2, 1))
    # negative controls
    segs4 = _synthetic(shift=4)
    recs4 = parse_table(segs4, 0x10104, 3)
    check("negative: base +4 fails the structure check",
          check_table(recs4, segs4, 0x10104, 3) != [])
    segs2 = _synthetic(count=2)
    hits2 = find_getters(segs2)
    blob = bytearray(segs2[0][1])
    struct.pack_into("<HH", blob, 0x10, 0x000b, 0xe000 | 2)   # count too small
    recs2 = parse_table([(0x10000, bytes(blob))], 0x10100, 2)
    full = _synthetic(count=3)
    check("negative: a count one short is caught (record past the count)",
          hits2 and check_table(parse_table(full, 0x10100, 2), full, 0x10100, 2) != []
          and len(recs2) == 2)
    broken = bytearray(segs[0][1])
    broken[0x14] ^= 0xff
    check("negative: a broken base getter is not found",
          find_getters([(0x10000, bytes(broken))]) == [])
    print("selftest: %s" % ("OK" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if "--selftest" in argv:
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true",
                    help="run the synthetic self-test and exit")
    ap.add_argument("image")
    ap.add_argument("--image-start", type=lambda s: int(s, 0), default=0x3e00200)
    ap.add_argument("--module", default="AppLaunch.dll")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump")
    d.add_argument("--json")
    sub.add_parser("imports")
    s = sub.add_parser("select")
    s.add_argument("--area", type=lambda v: int(v, 0), required=True)
    s.add_argument("--mode", type=int, default=0)
    s.add_argument("--base-type", type=int, default=1)
    s.add_argument("--name")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
