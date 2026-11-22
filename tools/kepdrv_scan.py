#!/usr/bin/env python3
"""Static map of the ZE0 dead-reckoning inputs (M8.H28).

The unit dead-reckons between GPS fixes from a gyro ADC and a speed-pulse
capture timer.  This tool re-derives, from kernel build B of the EU 2011 image
alone, the facts recorded in ``docs/firmware/kepdrv.md``:

* the two 4 KiB physical pages ``0xffc5a000`` (gyro ADC) and ``0xffc5b000``
  (pulse capture) that ``kepdrv.dll`` and ``navdrv.dll`` map with
  ``VirtualAlloc`` + ``VirtualCopy`` (``pages``);
* the TMU page ``0xffd81000`` and the register offsets written by
  ``TMURegisterInit`` (``tmu``);
* the ``gyroAdc_*`` API: each error string is attributed to the function that
  loads it, so the API names come from the image, not from a guess (``api``);
* the eight-channel ``braf`` jump table used by ``gyroAdc_GetAddData``
  (``channels``);
* the sensor sample struct built by ``navdrv.dll``: field offset -> getter VA
  and, where the getter has a named error string, its name (``sample``).

Every VA is read from the image through ``tools/cerom.py``; decoding is
``tools/sh4dis.py`` (little-endian, pinned there).  No hardware is needed.

Usage:
  python3 tools/kepdrv_scan.py IMG [--image-start 0x3e00200] [--json]
  python3 tools/kepdrv_scan.py --selftest

Method and the run: docs/experiments/EXP-2026-11-22-M8.H28-kepdrv.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cerom  # noqa: E402
import pdata  # noqa: E402
from sh4dis import Mem, decode  # noqa: E402

DEFAULT_START = 0x3E00200
PAGES = {"gyro": 0xFFC5A000, "pulse": 0xFFC5B000}
TMU_BASE = 0xFFD81000
MODULES = ("kepdrv.dll", "navdrv.dll")
# Constants whose earlier reading cost a session (see the EXP): 0x204 is the
# VirtualCopy PAGE_PHYSICAL|PAGE_READWRITE flag, 0x1388 is the 5000 ms
# WaitForSingleObject timeout in the key-timer thread.
CONSTANTS = {0x0204: "VirtualCopy flags", 0x1388: "WaitForSingleObject ms"}
TMU_OFFSETS = (0x270, 0x274, 0x278, 0x27C)


def u16(buf, off=0):
    return struct.unpack_from("<H", buf, off)[0]


def u32(buf, off=0):
    return struct.unpack_from("<I", buf, off)[0]


def load(image, image_start, module):
    """Return (rom, mod, mem, segs, data) with only uncompressed sections.

    ``mem.fn_of`` is attached from the module's pdata, so every function start
    is the same one ``tools/sh4xref.py`` reports (not a prologue heuristic).
    """
    data = open(image, "rb").read()
    rom = cerom.CERom(data, image_start)
    try:
        mod = rom.module(module)
    except KeyError:
        raise SystemExit("%s is not in the ROM at image-start 0x%x "
                         "(this scan is kernel build B, 0x3e00200)" %
                         (module, image_start))
    segs = []
    for s in rom.o32(mod):
        if s["flags"] & cerom.IMAGE_SCN_COMPRESSED:
            continue
        off = rom.va2file(s["dataptr"])
        segs.append((s["realaddr"], data[off:off + max(s["vsize"], s["psize"])]))
    mem = Mem(segs)
    pdata.attach_fn_of_from_image(mem, data, image_start, module)
    return rom, mod, mem, segs, data


def find_pool(mem, value):
    """VAs of 4-byte aligned little-endian ``value`` words in the segments."""
    out = []
    needle = struct.pack("<I", value)
    for base, blob in mem.segs:
        i = blob.find(needle)
        while i >= 0:
            if (base + i) % 4 == 0 and base + i not in out:
                out.append(base + i)
            i = blob.find(needle, i + 1)
    return sorted(out)


def halfword_loads(mem, value):
    """``mov.w @(pc),Rn`` load sites whose literal halfword equals ``value``.

    The VirtualCopy flag and the timeout are halfword immediates in the code
    stream, not 4-byte literal-pool words, so ``find_pool`` cannot see them.
    """
    out = []
    for base, blob in mem.segs:
        for i in range(0, len(blob) - 1, 2):
            d = decode(u16(blob, i), base + i, mem)
            if d.kind == "load" and d.text.startswith("mov.w") and \
                    d.lit is not None and mem.u16(d.lit) == value:
                out.append({"lit": d.lit, "at": d.va})
    return sorted(out, key=lambda r: r["at"])


def insns(mem, start, count):
    out = []
    for k in range(count):
        va = start + 2 * k
        w = mem.u16(va)
        if w is None:
            break
        out.append(decode(w, va, mem))
    return out


def all_loads(mem):
    """{lit_va: [load instruction VA, ...]} over every decoded code word."""
    out = {}
    for base, blob in mem.segs:
        for i in range(0, len(blob) - 1, 2):
            d = decode(u16(blob, i), base + i, mem)
            if d.kind == "load" and d.lit is not None:
                out.setdefault(d.lit, []).append(d.va)
    return out


def enclosing_fn(mem, va, back=0x4000):
    """Function start of ``va`` from the module's pdata (as sh4xref reports),
    falling back to the nearest ``sts.l pr,@-r15`` prologue for pdata gaps.
    """
    fn_of = getattr(mem, "fn_of", None)
    if fn_of is not None:
        start = fn_of(va)
        if start is not None:
            return start
    a = va
    for _ in range(back // 2):
        w = mem.u16(a)
        if w is None:
            return None
        if w == 0x4F22:
            return a
        a -= 2
    return None


def literal_reads(code, lit):
    """Decoded loads of literal ``lit`` in ``code``, with their VAs."""
    return [x for x in code if x.kind == "load" and x.lit == lit]


def sample_map(mem, fn, known, count=0x140):
    """Store-to-sample-struct in ``fn`` -> the getter VA last called.

    A getter is a ``jsr @rN`` whose ``rN`` was loaded from a literal pool once
    at function start (the compiler idiom here).  The register number comes
    from the decoder's structured operand ``rn``, not from the printed text,
    which carries a literal-note comment.  Both ``mov.l rX,@(off,r8)`` and the
    ``mov.w`` / ``mov.l rX,@r8`` (offset 0) forms are counted; ``-1`` is the
    error sentinel the caller checks after each getter.
    """
    code = insns(mem, fn, count)
    vals = {}
    fields, last, seen = [], None, set()
    for x in code:
        if x.kind == "load" and x.lit is not None and x.text.startswith("mov.l"):
            v = mem.u32(x.lit)
            if v is not None and x.rn is not None:
                vals[x.rn] = v
        if x.kind == "call" and x.text.startswith("jsr @"):
            try:
                reg = int(x.text.split("@r")[1].split()[0])
            except (IndexError, ValueError):
                continue
            target = vals.get(reg)
            # Only gyroAdc_* getters are sample sources; an error path calls a
            # logger through a register and must not overwrite the last getter.
            if target in known:
                last = target
        # sh4dis names the base register rn for mov.l stores but rm for mov.w
        base_reg = x.rn if x.rn is not None else x.rm
        if base_reg == 8 and x.text.startswith("mov.") and ",@" in x.text:
            if x.text.endswith(",@r8"):
                off = 0
            elif ",r8)" in x.text:
                try:
                    off = int(x.text.split(",@(")[1].split(",r8)")[0], 0)
                except ValueError:
                    continue
            else:
                continue
            if off not in seen:
                seen.add(off)
                fields.append({"off": off, "getter": last,
                               "width": 2 if x.text.startswith("mov.w") else 4})
    return sorted(fields, key=lambda f: f["off"])


def strings(mem, needle):
    """UTF-16LE strings in the code segments containing ``needle``.

    Yields (string VA, text).  Addresses come from the section table, never
    from a fitted delta; the encoding is the one the CE image uses for these
    diagnostics (UTF-16LE).
    """
    pat = needle.encode("utf-16le")
    for base, blob in mem.segs:
        i = blob.find(pat)
        while i >= 0:
            start = i
            # UTF-16LE: a character is [low byte, 0x00]; i points at a low
            # byte, so the previous character's low byte is at start-2.
            while start >= 2 and 32 <= blob[start - 2] < 127 and \
                    blob[start - 1] == 0:
                start -= 2
            end = i + len(pat)
            while end + 1 < len(blob) and 32 <= blob[end] < 127 and blob[end + 1] == 0:
                end += 2
            text = blob[start:end].decode("utf-16le", "replace")
            if needle in text:
                yield base + start, text
            i = blob.find(pat, i + 2)


def ascii_strings(mem, needle):
    """ASCII strings in code segments containing ``needle`` (kepdrv logs are
    single-byte; navdrv's gyroAdc diagnostics are UTF-16LE)."""
    pat = needle.encode("ascii")
    for base, blob in mem.segs:
        i = blob.find(pat)
        while i >= 0:
            start = i
            while start > 0 and 32 <= blob[start - 1] < 127:
                start -= 1
            end = i + len(pat)
            while end < len(blob) and 32 <= blob[end] < 127:
                end += 1
            text = blob[start:end].decode("ascii", "replace")
            if needle in text:
                yield base + start, text
            i = blob.find(pat, i + 1)


def api_from_strings(mem, loads):
    """Map each ``gyroAdc*`` error string to the function that loads it."""
    out = []
    for sva, text in strings(mem, "gyroAdc"):
        hits = []
        for pva in find_pool(mem, sva):
            for lva in loads.get(pva, []):
                fn = enclosing_fn(mem, lva)
                hits.append({"load": lva, "fn": fn})
        if hits:
            out.append({"va": sva, "text": text, "loads": hits})
    return sorted(out, key=lambda r: r["va"])


def channel_table(mem, loads):
    """The 8-byte ``braf`` jump table of ``gyroAdc_GetAddData``.

    The getter bounds its channel with ``cmp/hi #7``, loads a byte from the
    table (literal 0x039e2d38 in build B) and jumps via ``braf r0``; each byte
    is a byte offset from the instruction after the delay slot.
    """
    for sva, _text in strings(mem, "Channel ID NG"):
        for pva in find_pool(mem, sva):
            for lva in loads.get(pva, []):
                fn = enclosing_fn(mem, lva)
                if fn is None:
                    continue
                code = insns(mem, fn, 0x200)
                bsite = next((x.va for x in code if x.word == 0x0023), None)
                if bsite is None:
                    continue
                for x in code:
                    if x.va >= bsite or not (x.kind == "load" and
                                             x.text.startswith("mov.l") and
                                             x.lit is not None):
                        continue
                    tv = mem.u32(x.lit)
                    blob = mem.read(tv, 8) if tv is not None else None
                    if blob and all(0 <= b <= 0x80 for b in blob):
                        # braf r0 uses the address after its delay slot
                        anchor = bsite + 4
                        return {"va": tv, "bytes": list(blob), "getter": fn,
                                "braf": bsite,
                                "targets": [anchor + b for b in blob]}
    return None


def tmu_writes(mem, loads):
    """Register writes of ``TMURegisterInit`` in ``kepdrv.dll``.

    The struct-slot offsets (0x270/0x274/0x278/0x27c) are halfword literals;
    the values written are 0x668a (u32) and 0x21 (u16).  All are read from the
    image; the function is found through its own diagnostic string.
    """
    fn = None
    for sva, text in ascii_strings(mem, "TMURegisterInit >>"):
        for pva in find_pool(mem, sva):
            for lva in loads.get(pva, []):
                fn = enclosing_fn(mem, lva)
                if fn is not None:
                    break
            if fn is not None:
                break
        if fn is not None:
            break
    if fn is None:
        return {}
    code = insns(mem, fn, 0x80)
    slots, values = [], []
    for x in code:
        if x.kind == "load" and x.lit is not None and x.text.startswith("mov.w"):
            v = mem.u16(x.lit)
            if v in TMU_OFFSETS:
                slots.append({"slot": v, "lit": x.lit, "at": x.va})
            if v == 0x668A:
                values.append({"value": v, "lit": x.lit, "at": x.va})
        if x.text.startswith("mov #"):
            try:
                imm = int(x.text.split("#")[1].split(",")[0], 0) & 0xFFFF
            except ValueError:
                continue
            if imm == 0x0021:  # mov #33,r1 -> mov.w r1,@(slot +0x27c)
                values.append({"value": imm, "lit": None, "at": x.va})
    return {"fn": fn, "slots": slots, "values": sorted(values, key=lambda r: r["at"])}


def report(image_path, image_start):
    data = open(image_path, "rb").read()
    out = {"image": {"path": os.path.basename(image_path), "size": len(data),
                     "sha256": hashlib.sha256(data).hexdigest()},
           "image_start": image_start, "modules": {}, "pages": {},
           "constants": {}, "tmu": {}, "api": {}, "channels": {}, "sample": {}}
    for name in MODULES:
        _rom, _mod, mem, segs, _data = load(image_path, image_start, name)
        code = segs[0]
        out["modules"][name] = {"code_base": code[0], "code_vsize": len(code[1])}
        loads = all_loads(mem)
        pg = {}
        for label, base in PAGES.items():
            pools = find_pool(mem, base)
            pg[label] = {"base": base,
                         "pools": [{"va": p,
                                    "loads": [{"at": v, "fn": enclosing_fn(mem, v)}
                                              for v in loads.get(p, [])]}
                                   for p in pools]}
        out["pages"][name] = pg
        consts = {}
        for value, meaning in CONSTANTS.items():
            rows = [{"lit": r["lit"], "at": r["at"], "value": value,
                     "meaning": meaning, "fn": enclosing_fn(mem, r["at"])}
                    for r in halfword_loads(mem, value)]
            if rows:
                consts["0x%04x" % value] = rows
        out["constants"][name] = consts
        tmulit = find_pool(mem, TMU_BASE)
        if tmulit:
            out["tmu"] = {"base": TMU_BASE,
                          "pools": [{"va": p,
                                     "loads": [{"at": v, "fn": enclosing_fn(mem, v)}
                                               for v in loads.get(p, [])]}
                                    for p in tmulit]}
            out["tmu"].update(tmu_writes(mem, loads))
        if name == "navdrv.dll":
            out["api"] = api_from_strings(mem, loads)
            ch = channel_table(mem, loads)
            if ch:
                out["channels"] = ch
            # name the sample getters from the API table, then use that set so
            # an error-path call to the logger cannot be mistaken for a getter
            names = {r["loads"][0]["fn"]: _short_name(r["text"], r["va"])
                     for r in out["api"] if r.get("loads") and r["loads"][0]["fn"]}
            out["sample"] = {"fn": 0x039E59E4,
                             "fields": sample_map(mem, 0x039E59E4, set(names))}
            for f in out["sample"]["fields"]:
                f["name"] = names.get(f["getter"], "computed/inline")
    return out


def _short_name(text, va):
    """First gyroAdc_* identifier in a diagnostic string."""
    i = text.find("gyroAdc")
    if i < 0:
        return text
    j = i
    while j < len(text) and (text[j].isalnum() or text[j] == "_"):
        j += 1
    return text[i:j]


def selftest():
    ok = 0

    def check(name, cond):
        nonlocal ok
        if not cond:
            raise AssertionError(name)
        ok += 1

    check("u16 LE", u16(b"\x88\x13") == 0x1388)
    check("u32 LE", u32(b"\x00\xa0\xc5\xff") == 0xFFC5A000)
    mem = Mem([(0x1000, struct.pack("<II", 0xFFC5A000, 0x00001388))])
    check("find pool", find_pool(mem, 0xFFC5A000) == [0x1000])
    check("no pool", find_pool(mem, 0xFFC5B000) == [])
    # mov.l @(disp,pc),r9 ; literal at 0x1008
    mem2 = Mem([(0x2000, struct.pack("<H", 0xD901) + b"\x00\x00" +
                struct.pack("<I", 0xFFC5A000))])
    d = decode(mem2.u16(0x2000), 0x2000, mem2)
    check("lit load", d.kind == "load" and d.lit == 0x2008)
    # braf r0 (0x0023) is the jump-table opcode; the table must be 8 bytes
    check("braf", decode(0x0023, 0x3000, mem2).word == 0x0023)
    check("short name", _short_name("gyroAdc_SP_GetINTcount ERR.", 0) ==
          "gyroAdc_SP_GetINTcount")
    print("selftest: %d checks OK" % ok)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?")
    ap.add_argument("--image-start", type=lambda s: int(s, 0), default=DEFAULT_START)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        selftest()
        return 0
    if not args.image:
        ap.error("image required (or --selftest)")
    rep = report(args.image, args.image_start)
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0
    print("image %s %d B sha256 %s" % (rep["image"]["path"], rep["image"]["size"],
                                       rep["image"]["sha256"][:16]))
    for mod, r in rep["pages"].items():
        print("== %s ==" % mod)
        for label, pg in r.items():
            print("  %-5s 0x%08x" % (label, pg["base"]))
            for p in pg["pools"]:
                for l in p["loads"]:
                    print("    pool 0x%08x load 0x%08x fn %s" %
                          (p["va"], l["at"],
                           "0x%08x" % l["fn"] if l["fn"] else "(none)"))
        for k, rows in rep["constants"][mod].items():
            for row in rows:
                print("  const %s at 0x%08x fn %s" %
                      (k, row["at"], "0x%08x" % row["fn"] if row["fn"] else "(none)"))
    t = rep["tmu"]
    if t:
        print("TMU 0x%08x" % t["base"])
        for p in t["pools"]:
            for l in p["loads"]:
                print("  pool 0x%08x load 0x%08x fn %s" %
                      (p["va"], l["at"], "0x%08x" % l["fn"] if l["fn"] else "(none)"))
        for r in t.get("slots", []):
            print("  slot +0x%02x at 0x%08x" % (r["slot"], r["at"]))
        for r in t.get("values", []):
            print("  write 0x%04x at 0x%08x" % (r["value"], r["at"]))
    print("gyroAdc API:")
    for r in rep["api"]:
        f = r["loads"][0]["fn"] if r.get("loads") else None
        print("  %-14s 0x%08x  %s" % (_short_name(r["text"], r["va"]),
                                      f if f else 0, r["text"]))
    ch = rep["channels"]
    if ch:
        print("channel table 0x%08x: %s" %
              (ch["va"], " ".join("%02x" % b for b in ch["bytes"])))
        print("  targets: %s" % " ".join("0x%08x" % v for v in ch["targets"]))
    s = rep["sample"]
    if s:
        print("sample fn 0x%08x" % s["fn"])
        for f in s["fields"]:
            g = f["getter"]
            print("  +0x%02x <- 0x%08x %s" %
                  (f["off"], g if g else 0, f.get("name", "?")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
