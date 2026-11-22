#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""poi_position_l3.py - run the firmware's POI position arithmetic on factory records (M3.34).

M4.27 read the position of a POI from the file and fitted it to 16 reference
points.  This tool executes the firmware code that does the same, on name
records of a factory ``POINTnnn`` pair, and compares the two:

1. ``Navi.exe`` ``fn 0x003c032c`` (EU2011) ``(db, record, out)`` builds a
   **mesh point** ``{u32 mesh id, s16 x, s16 y}`` from a name record:
   ``id = (rec[2..5] as u32) & 0xfff3fff3`` (``fn 0x003f52e8``),
   ``x = rec[6..7] & 0x7ff`` (``fn 0x003f5368``), ``y = rec[8..9] & 0x7ff``
   (``fn 0x003f53e8``), then calls ``STDDLL!STD_MeshPnt_isValid`` and
   ``STD_MeshPnt_chgLv(mp, 1, out)`` through its import thunks.
2. ``STDDLL!STD_MeshPnt_chgMapPnt(mp, out)`` turns the mesh point into a
   map point ``{s32 a, s32 b}`` in 1/512 arc second (floating point inside).

Both run in ``sh4fpu.PySh4Fpu`` from the image's own bytes: the ``Navi.exe``
text, the ``STDDLL.dll`` text, and an import table filled the way the CE
loader fills it (slot -> export of ``STDDLL.dll``, resolved from the two
modules' import and export tables).  Nothing is modelled by hand except the
error logger ``0x003c5580`` (returns, call recorded).

The host side is ``point_census.fine_position`` (degrees).  A record passes
when the firmware map point equals the host position within ``--tol`` units
of 1/512 arc second (default 1: the library truncates a ``float``).

Controls: the two fine fields exchanged and the pre-M4.27 one-unit reading
must **not** match; a record of class 0 must be refused by the firmware.

Usage:
  poi_position_l3.py run IMG --dir PAIRS --file POINT010 [--count 200] [--json OUT]
  poi_position_l3.py mesh IMG ID X Y           # one mesh point -> map point
  poi_position_l3.py --selftest

Exit codes: 0 all records agree and the controls hold, 1 a mismatch,
3 BLOCKED (wrong build or engine stop).
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "l3_harness"))

import cerom  # noqa: E402
import ce_module  # noqa: E402
import point_census as pc  # noqa: E402
import point_pair_regen as regen  # noqa: E402
import point_walk_l3 as pw  # noqa: E402
from engine import EngineError  # noqa: E402
from sh4fpu import PySh4Fpu  # noqa: E402

IMAGE_START = 0x200200
# EU2011 Navi.exe (image SHA-256 92aa525d... for the first 256 MiB)
CONV = 0x003C032C            # record -> mesh point
ERRLOG = 0x003C5580          # error logger called on a refused record
THUNKS = {                   # import thunk VA -> expected STDDLL export
    0x003D1634: "STD_MeshPnt_initPrm",
    0x003D1640: "STD_MeshPnt_isValid",
    0x003D1658: "STD_MeshPnt_chgLv",
}
ID_MASK_LITERAL = (CONV + 0xBC, 0xFFF3FFF3)     # literal pool of fn CONV: the build check
STD_EXPORTS = ("STD_MeshPnt_chgMapPnt", "STD_MeshPnt_isValid", "STD_MeshID_judgeLevel")
UNITS_PER_DEGREE = 3600 * 512

REC_VA = 0x20000000
OUT_VA = 0x20001000
MAP_VA = 0x20001100
STACK_VA = 0x30000000
DB_DUMMY = 0x20002000        # the routines only test the pointer for 0 / -1


class Blocked(Exception):
    pass


class Firmware:
    """The two modules of one image, loaded once."""

    def __init__(self, image: bytes):
        self.rom = cerom.CERom(image, IMAGE_START)
        self.navi_va, self.navi = ce_module.text_section(image, IMAGE_START)
        _, std_secs = ce_module.legacy_module(image, IMAGE_START, "STDDLL.dll")
        text = [(s, blob) for s, comp, blob in std_secs if not comp and s["flags"] & 0x20000000]
        if not text:
            raise Blocked("STDDLL.dll has no uncompressed code section")
        self.std_sec, self.std = text[0]
        std_mod = self.rom.module("STDDLL.dll")
        self.std_base = self.rom.e32(std_mod)["vbase"]
        self.exports = {name: self.std_base + rva for _o, name, rva in self.rom.exports(std_mod)}
        self.by_ordinal = {o: name for o, name, _r in self.rom.exports(std_mod)}
        lit = ID_MASK_LITERAL[0] - self.navi_va
        if not 0 <= lit <= len(self.navi) - 4 or struct.unpack_from("<I", self.navi, lit)[0] != ID_MASK_LITERAL[1]:
            raise Blocked("this image is not EU2011: no 0xfff3fff3 literal at %#010x" % ID_MASK_LITERAL[0])
        self.iat = self._resolve_thunks()

    def _resolve_thunks(self) -> dict[int, int]:
        """{slot VA: STDDLL function VA} for the three thunks, from the import table."""
        navi = self.rom.module("Navi.exe")
        imports = {}
        for dll, slot, name, ordinal in self.rom.imports(navi):
            if dll.lower() == "stddll.dll":
                imports[slot] = name if name is not None else self.by_ordinal.get(ordinal)
        out = {}
        for thunk, want in THUNKS.items():
            off = thunk - self.navi_va
            w0, w1, w2 = struct.unpack_from("<3H", self.navi, off)
            if (w0 & 0xFF00, w1, w2) != (0xD000, 0x6002, 0x402B):
                raise Blocked("no import thunk at %#010x" % thunk)
            (slot,) = struct.unpack_from("<I", self.navi, ((thunk + 4) & ~3) + 4 * (w0 & 0xFF) - self.navi_va)
            name = imports.get(slot)
            if name != want:
                raise Blocked("thunk %#010x imports %r, expected %s" % (thunk, name, want))
            out[slot] = self.exports[name]
        return out

    def engine(self) -> PySh4Fpu:
        eng = PySh4Fpu(endian="little")
        eng.map("navi", self.navi_va, self.navi, "rx")
        eng.map("stddll", self.std_sec["realaddr"], self.std, "rx")
        page = min(self.iat) & ~0xFFF
        table = bytearray(0x1000)
        for slot, target in self.iat.items():
            if slot - page >= 0x1000:
                raise Blocked("import slots span more than one page")
            struct.pack_into("<I", table, slot - page, target)
        eng.map("iat", page, table, "r")
        eng.map("scratch", REC_VA, bytearray(0x3000), "rw")
        eng.map("stack", STACK_VA, bytearray(0x4000), "rw")
        return eng


def map_point(fw: Firmware, eng: PySh4Fpu, mesh_id: int, x: int, y: int):
    """STD_MeshPnt_chgMapPnt on one mesh point -> (status, a, b)."""
    eng.write_mem(OUT_VA, struct.pack("<Ihh", mesh_id & 0xFFFFFFFF, x, y))
    eng.write_mem(MAP_VA, bytes(8))
    eng.set_regs(r15=STACK_VA + 0x3F00)
    status = eng.call(fw.exports["STD_MeshPnt_chgMapPnt"], [OUT_VA, MAP_VA])
    a, b = struct.unpack("<ii", eng.read_mem(MAP_VA, 8))
    return status, a, b


def firmware_position(fw: Firmware, eng: PySh4Fpu, rec_file: bytes) -> dict:
    """Run the record -> mesh point -> map point path on one file-order record."""
    logged = []
    native = pw.swap16(rec_file[:64] + bytes(64 - min(64, len(rec_file))))
    eng.write_mem(REC_VA, native)
    eng.write_mem(OUT_VA, bytes(8))
    eng.set_regs(r15=STACK_VA + 0x3F00)
    if not getattr(eng, "_poi_hooked", False):
        eng.on_exec(ERRLOG, lambda e, va: (eng._poi_log.append(e.get_regs()["r6"]), 0)[1])
        eng._poi_hooked = True
    eng._poi_log = logged
    status = eng.call(CONV, [DB_DUMMY, REC_VA, OUT_VA])
    mesh_id, x, y = struct.unpack("<Ihh", eng.read_mem(OUT_VA, 8))
    out = {"status": status, "mesh_id": mesh_id, "x": x, "y": y, "logged": logged}
    if status == 0:
        eng.set_regs(r15=STACK_VA + 0x3F00)
        out["level"] = eng.call(fw.exports["STD_MeshID_judgeLevel"], [mesh_id])
        st, a, b = map_point(fw, eng, mesh_id, x, y)
        out.update(map_status=st, a=a, b=b)
    return out


def host_units(lat: float, lon: float) -> tuple[float, float]:
    return lat * UNITS_PER_DEGREE, lon * UNITS_PER_DEGREE


def compare(fwres: dict, rec: bytes, tol: float) -> dict:
    """Pass/fail of one record against the three host readings (pure)."""
    def close(pos):
        la, lo = host_units(*pos)
        return abs(fwres["a"] - la) <= tol + 1e-6 and abs(fwres["b"] - lo) <= tol + 1e-6

    ax, ay, flon, flat = pc.fine_fields(rec)
    want_id = ((ax << 16) | ay) & 0xFFF3FFF3
    return {
        "mesh": (fwres["mesh_id"], fwres["x"], fwres["y"]) == (want_id, flon, flat & 0x7FF),
        "fine": close(pc.fine_position(rec)),
        "swapped": close(pc.swapped_position(rec)),
        "legacy": close(pc.legacy_position(rec)),
    }


def name_records(pair_dir: Path, name: str) -> list[bytes]:
    pair = pc.find_pairs(pair_dir, [name])
    if not pair:
        raise Blocked(f"{name} not in {pair_dir}")
    blob = pc.load(pair[0][1], pair[0][2])
    chain = regen.chain_via_locator(blob, 1000)
    if chain is None:
        raise Blocked(f"{name}: no name chain")
    return pc.chain_records(chain)


def cmd_run(args) -> int:
    fw = Firmware(pw.load_image(args.image))
    eng = fw.engine()
    recs = name_records(Path(args.dir), args.file)
    normal = [r for r in recs if 1 <= r[0] >> 5 <= 3 and r[0] & 0xFC != 0xFC]
    step = max(1, len(normal) // args.count)
    sample = normal[::step][:args.count]
    rows, bad, swapped_hits, legacy_hits, distinct = [], 0, 0, 0, 0
    levels = set()
    worst = 0.0
    for rec in sample:
        res = firmware_position(fw, eng, rec)
        if res["status"] != 0 or res.get("map_status") != 0:
            bad += 1
            rows.append({"record": rec[:16].hex(), "status": res["status"], "logged": res["logged"]})
            continue
        cmpd = compare(res, rec, args.tol)
        la, lo = host_units(*pc.fine_position(rec))
        worst = max(worst, abs(res["a"] - la), abs(res["b"] - lo))
        levels.add(res["level"])
        ok = cmpd["mesh"] and cmpd["fine"]
        bad += 0 if ok else 1
        _, _, flon, flat = pc.fine_fields(rec)
        if flon != flat & 0x7FF:
            distinct += 1
            swapped_hits += cmpd["swapped"]
        legacy_hits += cmpd["legacy"]
        rows.append({"record": rec[:16].hex(), "mesh_id": "%08x" % res["mesh_id"], "x": res["x"],
                     "y": res["y"], "a": res["a"], "b": res["b"], "ok": ok})
    zero = bytearray(sample[0])
    zero[0] &= 0x1F                                   # class 0: not a name record
    refused = firmware_position(fw, eng, bytes(zero))
    first = rows[0]
    print("%s: %d name records, %d sampled (every %d)" % (args.file, len(recs), len(sample), step))
    print("  first: record %s -> mesh %s x=%s y=%s -> map point (%s, %s) = %.6f, %.6f deg" % (
        first["record"], first.get("mesh_id"), first.get("x"), first.get("y"), first.get("a"), first.get("b"),
        first.get("a", 0) / UNITS_PER_DEGREE, first.get("b", 0) / UNITS_PER_DEGREE))
    print("  firmware = point_census.fine_position within %g unit(s) of 1/512\": %d/%d (worst %.3f)" % (
        args.tol, len(sample) - bad, len(sample), worst))
    print("  mesh level reported by STD_MeshID_judgeLevel: %s" % sorted(levels))
    print("  control, fine fields exchanged: %d/%d match (records with different fields)" % (swapped_hits, distinct))
    print("  control, one-unit reading:      %d/%d match" % (legacy_hits, len(sample)))
    print("  control, class-0 record:        status %#x, logger line %s" % (
        refused["status"], refused["logged"]))
    ok = (bad == 0 and distinct > 0 and swapped_hits * 20 <= distinct and legacy_hits * 20 <= len(sample)
          and refused["status"] != 0 and levels == {1})
    print("RESULT: %s" % ("ACCEPT" if ok else "REJECT"))
    if args.json:
        Path(args.json).write_text(json.dumps({
            "file": args.file, "records": len(recs), "sampled": len(sample), "mismatch": bad,
            "worst_units": worst, "levels": sorted(levels), "swapped_match": swapped_hits,
            "distinct": distinct, "legacy_match": legacy_hits,
            "refused": {"status": refused["status"], "logged": refused["logged"]},
            "rows": rows[:50]}, indent=1) + "\n")
    return 0 if ok else 1


def cmd_mesh(args) -> int:
    fw = Firmware(pw.load_image(args.image))
    eng = fw.engine()
    mesh_id = int(args.id, 0)
    eng.set_regs(r15=STACK_VA + 0x3F00)
    level = eng.call(fw.exports["STD_MeshID_judgeLevel"], [mesh_id])
    st, a, b = map_point(fw, eng, mesh_id, args.x, args.y)
    print("mesh %#010x x=%d y=%d: level %d, status %d, map point (%d, %d) = %.7f, %.7f deg" % (
        mesh_id, args.x, args.y, level, st, a, b, a / UNITS_PER_DEGREE, b / UNITS_PER_DEGREE))
    return 0 if st == 0 else 1


def selftest() -> int:
    """Pure checks of the comparison (the firmware run needs the image: ``run``)."""
    n = 0
    ax, ay, w6, w8 = pc.encode_position(52.2297, 21.0122)
    rec = struct.pack(">HHHHH", 0x6008, ax, ay, w6, w8) + bytes(6)
    lat, lon = pc.fine_position(rec)
    assert abs(lat - 52.2297) < 2e-5 and abs(lon - 21.0122) < 2e-5
    n += 1
    la, lo = host_units(lat, lon)
    good = {"mesh_id": ((ax << 16) | ay) & 0xFFF3FFF3, "x": w6 & 0x7FF, "y": w8 & 0x7FF,
            "a": int(la), "b": int(lo)}
    c = compare(good, rec, 1)
    assert c["mesh"] and c["fine"] and not c["legacy"], c
    n += 1
    assert not compare(dict(good, a=good["a"] + 3), rec, 1)["fine"]          # 3 units off: refused
    assert not compare(dict(good, x=good["x"] ^ 1), rec, 1)["mesh"]
    assert not compare(dict(good, mesh_id=good["mesh_id"] | 0xC), rec, 1)["mesh"]   # marker bits kept
    n += 3
    if w6 & 0x7FF != w8 & 0x7FF:
        assert not c["swapped"]
        n += 1
    # the mesh arithmetic the firmware reports, as a formula: one level-1 cell is
    # 2048 fine steps, 38400 units of latitude and 57600 of longitude
    cell_lat = UNITS_PER_DEGREE * 4 / pc.LAT_SCALE
    cell_lon = UNITS_PER_DEGREE * 4 / pc.LON_SCALE
    assert (cell_lat, cell_lon) == (38400.0, 57600.0)
    n += 1
    assert host_units(15.0 + 1 / 6, -133.25) == (27955200.0, -245606400.0)       # mesh 0x8b608b60
    n += 1
    print("selftest OK (%d checks)" % n)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("image")
    r.add_argument("--dir", required=True, help="directory with POINTnnn.DAT.CMP/.IND pairs")
    r.add_argument("--file", default="POINT010")
    r.add_argument("--count", type=int, default=200)
    r.add_argument("--tol", type=float, default=1.0)
    r.add_argument("--json")
    m = sub.add_parser("mesh")
    m.add_argument("image")
    m.add_argument("id")
    m.add_argument("x", type=int)
    m.add_argument("y", type=int)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmd:
        ap.error("need a command or --selftest")
    try:
        return cmd_run(args) if args.cmd == "run" else cmd_mesh(args)
    except Blocked as exc:
        print("BLOCKED: %s" % exc)
        return 3
    except EngineError as exc:
        print("BLOCKED: engine stop: %s" % str(exc)[:300])
        return 3


if __name__ == "__main__":
    sys.exit(main())
