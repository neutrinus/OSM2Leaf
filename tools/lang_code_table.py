#!/usr/bin/env python3
"""Decode the firmware language tables behind the MMAIN001 ``0x18c`` code list (M4.38).

The ``0x18c`` list in ``MMAIN001.DAT``/``BICON001`` (EU 2011 ``05 04 02 07 0a
06 08 14``, US ``03 04``) has no name on the card. Two firmware modules read
the same user setting (``OBJDLL!OBJ_Setting_readExpLanguage``, a value
3001, 3002, ...) and turn it into two different things:

* ``Navi.exe`` ``sdl_com_hdl_get_lang`` searches an array of 8-byte rows
  ``{u32 exp_language; u16 map_code; u16 0}`` and returns ``map_code``
  (default ``0x3f``, the same byte that fills the ``0x18c`` list);
* ``Speech.exe`` switches on the same setting and loads the UTF-16 name of a
  ``SPEECH/<dir>`` (``BE``, ``FR``, ...), through one or two ``braf`` jump
  tables.

Joining the two on ``exp_language`` gives ``map_code -> SPEECH dir`` from the
firmware alone. ``card`` reads the codes and the ``SPEECH/`` dirs from a card
image, and ``join`` checks one against the other.

Subcommands (all read-only, stdlib only):

  firmware IMG [--image-start X]     decode both tables of one CE build
  card IMG                           0x18c codes (MMAIN001) + SPEECH dirs
  rows IMG [--read-mib N]            raw scan for every run of >= 4 rows of
                                     the get_lang shape {u32 3001..3999; u16
                                     code; u16 0} (where else a table could be)
  join FW_IMG CARD_IMG               code -> dir for the card, with checks
                                     and two negative controls (codes shifted
                                     by +-1; codes read as the Speech.exe
                                     language number without the Navi table)

Exit codes: 0 ok (join: every card SPEECH dir is named by a card code and the
negative control fails), 1 check failed / not found, 2 usage error.

Addresses come from ``tools/cerom.py`` via ``tools/sh4xref.load_module``;
decoding is ``tools/sh4dis.py`` (little-endian pinned there). Evidence:
docs/experiments/EXP-2026-11-19-M4.38-lang-code-table.md, claims C-3760..C-3769.
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sh4dis  # noqa: E402
import sh4xref  # noqa: E402

FILL = 0x3F
LANG_CONV_NEEDLE = b"LANG CONV ERROR"
EXP_LANG_MIN, EXP_LANG_MAX = 3000, 3999


# --------------------------------------------------------------------------
# SH-4 jump-table switch decoder (braf form emitted by the CE compiler)
# --------------------------------------------------------------------------

def _s8(x):
    return x - 0x100 if x & 0x80 else x


def _s16(x):
    return x - 0x10000 if x & 0x8000 else x


def _utf16_short(mem, va, maxlen=8):
    """A short NUL-terminated UTF-16LE ASCII string at ``va``, else None."""
    b = mem.read(va, 2 * (maxlen + 1))
    if b is None:
        return None
    out = []
    for i in range(0, len(b), 2):
        c = b[i] | b[i + 1] << 8
        if c == 0:
            break
        if not 0x20 < c < 0x7F:
            return None
        out.append(chr(c))
    else:
        return None
    return "".join(out) if out else None


def decode_switch(mem, braf_va):
    """Decode the switch that ends in ``braf Rn`` at ``braf_va``.

    Shape (both builds): ``[add #-b,Rx | mov.w L; sub]`` bias, ``mov #n-1,Rk;
    cmp/hi Rk,Rx; bt DEFAULT``, ``mov.l @(pc),Rt`` (table), ``mov Rx,r0``,
    ``[add r0,r0]``, ``mov.b|mov.w @(r0,Rt),r0``, ``braf r0``. Case ``i``
    (value ``i + bias``) jumps to ``braf_va + 4 + table[i]``. Returns a dict or
    None if the shape does not match.
    """
    w = mem.u16(braf_va)
    if w is None or w & 0xF0FF != 0x0023:
        return None
    width = table_reg = table_va = None
    back = [braf_va - 2 * k for k in range(1, 16)]
    for a in back[:4]:
        x = mem.u16(a)
        if x is not None and x & 0xF00F in (0x000C, 0x000D) and (x >> 8) & 15 == 0:
            width = 1 if x & 0xF == 0xC else 2
            table_reg = (x >> 4) & 15
            break
    if width is None:
        return None
    for a in back:
        t = sh4dis.movl_pc_target(a, mem.u16(a))
        if t and t[0] == table_reg:
            table_va = mem.u32(t[1])
            break
    if table_va is None:
        return None
    count = default = idx_reg = cmp_va = None
    for a in back:
        x = mem.u16(a)
        if x is not None and x & 0xF00F == 0x3006:            # cmp/hi Rm,Rn
            k, n = (x >> 4) & 15, (x >> 8) & 15
            bt = mem.u16(a + 2)
            if bt is None or bt & 0xFF00 != 0x8900:
                continue
            default = a + 2 + 4 + 2 * _s8(bt & 0xFF)
            for b in [a - 2 * j for j in range(1, 6)]:
                y = mem.u16(b)
                if y is not None and y & 0xF000 == 0xE000 and (y >> 8) & 15 == k:
                    count = _s8(y & 0xFF) + 1
                    break
            idx_reg, cmp_va = n, a
            break
    if count is None:
        return None
    bias = 0
    for b in [cmp_va - 2 * j for j in range(1, 8)]:
        y = mem.u16(b)
        if y is None:
            continue
        if y & 0xF000 == 0x7000 and (y >> 8) & 15 == idx_reg and y & 0x80:
            bias = -_s8(y & 0xFF)
            break
        if y & 0xF00F == 0x3008 and (y >> 8) & 15 == idx_reg:   # sub Rm,Rn
            m = (y >> 4) & 15
            for c in [b - 2 * j for j in range(1, 6)]:
                z = mem.u16(c)
                if z is not None and z & 0xF000 == 0x9000 and (z >> 8) & 15 == m:
                    bias = mem.u16(c + 4 + 2 * (z & 0xFF))
                    break
            break
    base = braf_va + 4
    cases = []
    for i in range(count):
        if width == 1:
            raw = mem.read(table_va + i, 1)
            off = _s8(raw[0]) if raw else None
        else:
            v = mem.u16(table_va + 2 * i)
            off = _s16(v) if v is not None else None
        if off is None:
            return None
        cases.append((i + bias, _case_value(mem, base + off, default)))
    return {"braf": braf_va, "table": table_va, "width": width, "bias": bias,
            "count": count, "default": default, "cases": cases}


def _case_value(mem, target, default):
    """('default',) | ('int', v) | ('str', s, va) | ('target', va)."""
    if target == default:
        return ("default",)
    w = mem.u16(target)
    if w is None:
        return ("target", target)
    if w & 0xF000 == 0xA000:                                  # bra; delay slot
        d = mem.u16(target + 2)
        if d is not None and d & 0xF000 == 0xE000:
            return ("int", _s8(d & 0xFF))
    if w & 0xF000 == 0xE000:                                  # mov #imm,Rn
        return ("int", _s8(w & 0xFF))
    t = sh4dis.movl_pc_target(target, w)
    if t:
        va = mem.u32(t[1])
        s = _utf16_short(mem, va) if va is not None else None
        if s is not None:
            return ("str", s, va)
    return ("target", target)


def find_switches(mem, exec_segs):
    out = []
    for base, blob in exec_segs:
        for off in range(0, len(blob) - 1, 2):
            w = blob[off] | blob[off + 1] << 8
            if w & 0xF0FF == 0x0023:
                sw = decode_switch(mem, base + off)
                if sw:
                    out.append(sw)
    return out


# --------------------------------------------------------------------------
# Navi.exe: sdl_com_hdl_get_lang table
# --------------------------------------------------------------------------

def _string_va(segs, needle):
    for base, blob in segs:
        i = blob.find(needle)
        if i >= 0:
            j = i
            while j > 0 and blob[j - 1] != 0:
                j -= 1
            return base + j
    return None


def parse_lang_rows(mem, va, limit=64):
    rows = []
    for i in range(limit):
        b = mem.read(va + 8 * i, 8)
        if b is None:
            break
        exp, code, pad = struct.unpack("<IHH", b)
        if not (EXP_LANG_MIN < exp <= EXP_LANG_MAX) or pad != 0 or code > 0xFF:
            break
        rows.append((exp, code))
    return rows


def navi_get_lang(mem, exec_segs):
    """Locate the get_lang function from its 'LANG CONV ERROR' log string and
    return {fn, string, table, bound, rows, default}."""
    svs = _string_va(mem.segs, LANG_CONV_NEEDLE)
    if svs is None:
        return None
    for pool in sh4xref.pool_entries(mem, exec_segs, svs):
        for load, _reg in sh4xref.loads_of(mem, pool):
            fn = sh4xref.fn_start(mem, load)
            if fn is None:
                continue
            best = None
            bound = default = None
            a = fn
            while a < load + 0x40:
                w = mem.u16(a)
                t = sh4dis.movl_pc_target(a, w)
                if t:
                    lit = mem.u32(t[1])
                    rows = parse_lang_rows(mem, lit) if lit is not None else []
                    if len(rows) >= 4 and (best is None or len(rows) > len(best[1])):
                        best = (lit, rows)
                nxt = mem.u16(a + 2)
                if (w is not None and w & 0xF000 == 0xE000 and nxt is not None
                        and nxt & 0xF00F == 0x3003 and (nxt >> 4) & 15 == (w >> 8) & 15):
                    bound = _s8(w & 0xFF)                     # mov #n,Rk; cmp/ge Rk,Rx
                if default is None and w is not None and w & 0xF000 == 0xE000 and (w & 0xFF) == FILL:
                    default = FILL
                a += 2
            if best:
                lit, rows = best
                if bound is not None:
                    rows = rows[:bound]
                return {"fn": fn, "string": svs, "table": lit, "bound": bound,
                        "rows": rows, "default": default}
    return None


# --------------------------------------------------------------------------
# Speech.exe: exp_language -> SPEECH dir
# --------------------------------------------------------------------------

def speech_dirs(mem, exec_segs):
    """Return {fn_a, fn_b, map: {exp_language: dir|None}} from the two switches."""
    sws = find_switches(mem, exec_segs)
    sw_a = sw_b = None
    for sw in sws:
        kinds = [c[1][0] for c in sw["cases"]]
        if sw["bias"] == EXP_LANG_MIN + 1 and kinds.count("int") >= 4:
            sw_a = sw_a or sw
        if sum(1 for c in sw["cases"] if c[1][0] == "str" and len(c[1][1]) == 2) >= 5:
            sw_b = sw_b or sw
    if sw_a is None or sw_b is None:
        return None
    v_of = {}
    for key, val in sw_a["cases"]:
        v_of[key] = val[1] if val[0] == "int" else None
    dir_of_v = {key: (val[1] if val[0] == "str" else None) for key, val in sw_b["cases"]}
    out = {}
    for exp, v in sorted(v_of.items()):
        out[exp] = (v, dir_of_v.get(v) if v is not None else None)
    return {"switch_a": sw_a, "switch_b": sw_b, "map": out}


def firmware_tables(img, image_start=0x200200):
    navi = mem_n = None
    mem_n, ex_n, _i, _e = sh4xref.load_module(img, image_start, "Navi.exe")
    navi = navi_get_lang(mem_n, ex_n)
    mem_s, ex_s, _i, _e = sh4xref.load_module(img, image_start, "Speech.exe")
    speech = speech_dirs(mem_s, ex_s)
    return navi, speech


def code_to_dirs(navi, speech):
    """{map_code: [(exp_language, dir|None)]} joined on exp_language."""
    out = {}
    for exp, code in navi["rows"]:
        v, d = speech["map"].get(exp, (None, None))
        out.setdefault(code, []).append((exp, d))
    return out


# --------------------------------------------------------------------------
# Card side
# --------------------------------------------------------------------------

def card_info(img):
    import cardcheck
    import identity_fields
    fat = cardcheck.Fat32Image(img)
    hdr = fat.read_range("MMAIN001.DAT", 0, 0x200)
    if len(hdr) < 0x200:
        raise ValueError("MMAIN001.DAT header not readable from this image")
    codes = identity_fields.parse_header(hdr)["codes_0x18c"]
    dirs = sorted(e.name for e in fat.list_dir("SPEECH") if e.is_dir and e.name not in (".", ".."))
    return {"label": fat.geometry.label, "codes": codes, "speech_dirs": dirs}


def join(c2d, codes, dirs, shift=0):
    """Map each card code (+shift) to the firmware dirs; return rows + verdict."""
    rows, covered = [], set()
    for c in codes:
        entries = c2d.get(c + shift, [])
        named = sorted({d for _e, d in entries if d})
        present = [d for d in named if d in dirs]
        covered.update(present)
        rows.append((c, entries, named, present))
    missing = [d for d in dirs if d not in covered]
    return rows, missing


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def _print_firmware(navi, speech, image_start):
    print("build_image_start 0x%x" % image_start)
    if navi is None:
        print("navi_get_lang NOT FOUND")
    else:
        print("navi_get_lang fn 0x%08x  log_string 0x%08x  table 0x%08x  rows %d  loop_bound %s  default 0x%02x"
              % (navi["fn"], navi["string"], navi["table"], len(navi["rows"]),
                 navi["bound"], navi["default"] if navi["default"] is not None else -1))
    if speech is None:
        print("speech_switches NOT FOUND")
    else:
        for name in ("switch_a", "switch_b"):
            sw = speech[name]
            print("speech_%s braf 0x%08x  table 0x%08x  width %d  bias %d  cases %d  default 0x%08x"
                  % (name, sw["braf"], sw["table"], sw["width"], sw["bias"], sw["count"], sw["default"]))
    if navi is None or speech is None:
        return
    print("%-12s %-9s %-8s %s" % ("exp_language", "map_code", "speech_v", "speech_dir"))
    navi_rows = dict(navi["rows"])
    for exp in sorted(set(navi_rows) | set(speech["map"])):
        code = navi_rows.get(exp)
        v, d = speech["map"].get(exp, (None, None))
        print("%-12d %-9s %-8s %s" % (exp, "0x%02x" % code if code is not None else "-",
                                     v if v is not None else "-", d or "(default)"))
    print("map_code -> SPEECH dirs:")
    for code, entries in sorted(code_to_dirs(navi, speech).items()):
        print("  0x%02x  %s" % (code, ", ".join("%d:%s" % (e, d or "-") for e, d in entries)))


def cmd_firmware(args):
    navi, speech = firmware_tables(args.image, args.image_start)
    _print_firmware(navi, speech, args.image_start)
    return 0 if navi and speech else 1


def scan_rows(blob, min_rows=4):
    """Every 4-aligned run of >= min_rows get_lang-shaped rows in ``blob``:
    [(offset, [(exp, code), ...])]. Raw bytes, no module parsing."""
    out = []
    i, n = 0, len(blob) - 8
    while i <= n:
        rows = []
        j = i
        while j <= n:
            exp, code, pad = struct.unpack_from("<IHH", blob, j)
            if not (EXP_LANG_MIN < exp <= EXP_LANG_MAX) or pad != 0 or code > 0xFF:
                break
            rows.append((exp, code))
            j += 8
        if len(rows) >= min_rows:
            out.append((i, rows))
            i = j
        else:
            i += 4
    return out


def cmd_rows(args):
    with open(args.image, "rb") as fh:
        blob = fh.read(args.read_mib << 20)
    runs = scan_rows(blob)
    codes = set()
    for off, rows in runs:
        codes.update(c for _e, c in rows)
        print("file 0x%08x  rows %d  codes %s" % (off, len(rows), " ".join("%02x" % c for _e, c in rows)))
    print("bytes_scanned %d  runs %d  distinct_codes %s" % (len(blob), len(runs),
          " ".join("%02x" % c for c in sorted(codes))))
    return 0


def cmd_card(args):
    info = card_info(args.image)
    print("label %s" % info["label"])
    print("codes_0x18c %s" % " ".join("%02x" % c for c in info["codes"]))
    print("speech_dirs %d %s" % (len(info["speech_dirs"]), " ".join(info["speech_dirs"])))
    return 0


def cmd_join(args):
    navi, speech = firmware_tables(args.firmware, args.image_start)
    if navi is None or speech is None:
        print("firmware tables NOT FOUND")
        return 1
    info = card_info(args.card)
    c2d = code_to_dirs(navi, speech)
    print("card %s  codes %s  speech_dirs %s" % (info["label"], " ".join("%02x" % c for c in info["codes"]),
                                                 " ".join(info["speech_dirs"])))
    rows, missing = join(c2d, info["codes"], info["speech_dirs"])
    no_row = 0
    for c, entries, named, present in rows:
        if not entries:
            no_row += 1
            status = "no exp_language row"
        elif present:
            status = "dir on card: " + ",".join(present)
        elif named:
            status = "dir NOT on card: " + ",".join(named)
        else:
            status = "speech default (no dir)"
        print("  code 0x%02x  exp %s  -> %s" % (c, ",".join(str(e) for e, _ in entries) or "-", status))
    wrong = sum(1 for _c, _e, named, present in rows if named and not present)
    print("coverage %d/%d speech dirs named by a card code; missing %s; codes with a dir not on card %d; codes without a row %d"
          % (len(info["speech_dirs"]) - len(missing), len(info["speech_dirs"]),
             ",".join(missing) or "-", wrong, no_row))
    ok = not missing and wrong == 0
    ctrl_fail = 0
    for shift in (-1, 1):
        r2, m2 = join(c2d, info["codes"], info["speech_dirs"], shift)
        w2 = sum(1 for _c, _e, named, present in r2 if named and not present)
        cov = len(info["speech_dirs"]) - len(m2)
        failed = bool(m2) or w2 > 0
        ctrl_fail += failed
        print("negative control shift %+d: coverage %d/%d, wrong %d -> %s"
              % (shift, cov, len(info["speech_dirs"]), w2, "FAILS (as required)" if failed else "PASSES (control broken)"))
    # Control B: skip the Navi table and read each card code as the Speech.exe
    # language number v directly (the reading the Navi table makes unnecessary).
    v_dir = {}
    for _exp, (v, d) in speech["map"].items():
        if v is not None:
            v_dir.setdefault(v, []).append((v, d))
    r3, m3 = join(v_dir, info["codes"], info["speech_dirs"])
    w3 = sum(1 for _c, _e, named, present in r3 if named and not present)
    failed = bool(m3) or w3 > 0
    ctrl_fail += failed
    print("negative control code-as-speech-v: coverage %d/%d, wrong %d -> %s"
          % (len(info["speech_dirs"]) - len(m3), len(info["speech_dirs"]), w3,
             "FAILS (as required)" if failed else "PASSES (control broken)"))
    print("result: %s" % ("PASS" if ok and ctrl_fail == 3 else "FAIL"))
    return 0 if ok and ctrl_fail == 3 else 1


# --------------------------------------------------------------------------
# Self-test (synthetic code, no vendor bytes)
# --------------------------------------------------------------------------

def _asm_switch_byte():
    """Synthetic 2011-shape switch: v in 1..3 -> UTF-16 'AA','BB', default."""
    code = 0x1000
    words = [
        0x62E2,             # 1000 mov.l @r14,r2
        0xE302,             # 1002 mov #2,r3  (count 3)
        0x72FF,             # 1004 add #-1,r2 (bias 1)
        0x3236,             # 1006 cmp/hi r3,r2
        0x890A,             # 1008 bt -> 0x1008+4+20 = 0x1020 default
        0xD306,             # 100a mov.l @(0x1024),r3 -> table
        0x6023,             # 100c mov r2,r0
        0x003C,             # 100e mov.b @(r0,r3),r0
        0x0009,             # 1010 nop
        0x0023,             # 1012 braf r0  -> base 0x1016
        0x0009,             # 1014 nop
        0xD504,             # 1016 mov.l @(0x1028),r5 -> 'AA'
        0x0009, 0x0009,     # 1018,101a
        0xD504,             # 101c mov.l @(0x1030),r5 -> 'BB'
        0x0009,             # 101e
        0x0009,             # 1020 default
        0x0009,             # 1022
    ]
    blob = bytearray(b"".join(struct.pack("<H", w) for w in words))
    blob += struct.pack("<I", 0x2000)            # 1024 table ptr
    blob += struct.pack("<I", 0x2010)            # 1028 'AA'
    blob += b"\0" * 4                            # 102c
    blob += struct.pack("<I", 0x2018)            # 1030 'BB'
    data = bytearray(0x40)
    data[0:3] = bytes([0x00, 0x06, 0x0A])        # 1016, 101c, 1020(default)
    data[0x10:0x16] = "AA".encode("utf-16le") + b"\0\0"
    data[0x18:0x1e] = "BB".encode("utf-16le") + b"\0\0"
    return sh4dis.Mem([(code, bytes(blob)), (0x2000, bytes(data))]), code + 0x12


def _asm_switch_word_sub():
    """Synthetic 2014-shape switch A: mov.w 3001; sub; mov.b table; bra+mov #imm."""
    code = 0x1000
    words = [
        0x9310,             # 1000 mov.w @(0x1024),r3 = 3001
        0x52F5,             # 1002 mov.l @(20,r15),r2
        0x3238,             # 1004 sub r3,r2
        0xE301,             # 1006 mov #1,r3 (count 2)
        0x3236,             # 1008 cmp/hi r3,r2
        0x8909,             # 100a bt -> 0x100a+4+18 = 0x1020
        0xD306,             # 100c mov.l @(0x1028),r3 table
        0x6023,             # 100e mov r2,r0
        0x003C,             # 1010 mov.b @(r0,r3),r0
        0x0009,             # 1012
        0x0023,             # 1014 braf r0 -> base 0x1018
        0x0009,             # 1016
        0xA002,             # 1018 bra 0x1020 ; delay mov #7,r8
        0xE807,             # 101a
        0xA000,             # 101c bra 0x1020
        0xE809,             # 101e mov #9,r8
        0x0009,             # 1020
        0x0009,             # 1022
        0x0BB9,             # 1024 3001
        0x0000,             # 1026
    ]
    blob = bytearray(b"".join(struct.pack("<H", w) for w in words))
    blob += struct.pack("<I", 0x2000)            # 1028
    data = bytes([0x00, 0x04])
    return sh4dis.Mem([(code, bytes(blob)), (0x2000, data)]), code + 0x14


def selftest():
    ok = True

    def expect(name, cond):
        nonlocal ok
        print("%s %s" % ("PASS" if cond else "FAIL", name))
        ok &= bool(cond)

    mem, braf = _asm_switch_byte()
    sw = decode_switch(mem, braf)
    expect("byte switch decoded", sw is not None)
    if sw:
        expect("byte switch bias 1 (add #-1)", sw["bias"] == 1)
        expect("byte switch 3 cases", sw["count"] == 3)
        expect("case 1 -> 'AA'", sw["cases"][0][1][:2] == ("str", "AA"))
        expect("case 2 -> 'BB'", sw["cases"][1][1][:2] == ("str", "BB"))
        expect("case 3 -> default", sw["cases"][2][1] == ("default",))
    expect("non-braf word rejected", decode_switch(mem, 0x1000) is None)

    mem2, braf2 = _asm_switch_word_sub()
    sw2 = decode_switch(mem2, braf2)
    expect("sub-bias switch decoded", sw2 is not None)
    if sw2:
        expect("bias 3001 from mov.w literal", sw2["bias"] == 3001)
        expect("3001 -> int 7, 3002 -> int 9",
               sw2["cases"] == [(3001, ("int", 7)), (3002, ("int", 9))])

    # get_lang rows parser
    rows_blob = b"".join(struct.pack("<IHH", e, c, 0) for e, c in [(3001, 1), (3002, 2), (3003, 4)])
    rows_blob += b"[SDL] xx"
    rmem = sh4dis.Mem([(0x3000, rows_blob)])
    expect("row parser stops at non-row", parse_lang_rows(rmem, 0x3000) == [(3001, 1), (3002, 2), (3003, 4)])

    # join + shifted negative control
    c2d = {2: [(3002, "BE")], 4: [(3003, "FR"), (3005, "CF")], 5: [(3006, "GE")]}
    rows, missing = join(c2d, [5, 4, 2, 0x14], ["BE", "FR", "GE"])
    expect("join covers all dirs", missing == [])
    expect("code 0x14 has no row", rows[3][1] == [])
    _r, m_shift = join(c2d, [5, 4, 2, 0x14], ["BE", "FR", "GE"], shift=1)
    expect("shift +1 control loses coverage", m_shift != [])
    rows_us, missing_us = join(c2d, [4], ["CF"])
    expect("code 4 on a CF-only card covers CF", missing_us == [] and rows_us[0][3] == ["CF"])
    blob = b"\0" * 4 + rows_blob + b"\0" * 8 + struct.pack("<IHH", 3001, 1, 0) * 3
    found = scan_rows(blob)
    expect("raw row scan finds both 3-row runs at min_rows=3",
           [o for o, _r in scan_rows(blob, 3)] == [4, 4 + len(rows_blob) + 8])
    expect("raw row scan ignores runs shorter than 4", found == [])
    print("selftest: %s" % ("OK" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    f = sub.add_parser("firmware")
    f.add_argument("image")
    f.add_argument("--image-start", type=lambda s: int(s, 0), default=0x200200)
    c = sub.add_parser("card")
    c.add_argument("image")
    r = sub.add_parser("rows")
    r.add_argument("image")
    r.add_argument("--read-mib", type=int, default=256)
    j = sub.add_parser("join")
    j.add_argument("firmware")
    j.add_argument("card")
    j.add_argument("--image-start", type=lambda s: int(s, 0), default=0x200200)
    args = p.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "firmware":
        return cmd_firmware(args)
    if args.cmd == "card":
        return cmd_card(args)
    if args.cmd == "rows":
        return cmd_rows(args)
    if args.cmd == "join":
        return cmd_join(args)
    p.print_usage()
    return 2


if __name__ == "__main__":
    sys.exit(main())
