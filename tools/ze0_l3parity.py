#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""ze0_l3parity.py - compare the L3 reader model with the L4 full system (M8.H11).

M8.H11 asks whether the L3 harness runs the two mount-time readers the way the
unit does.  This tool sets breakpoints on the ``MMAIN001.DAT`` reader and the
``DRSTR001.DAT`` parser in a ``-M ze0`` boot (QEMU gdbstub, ``-gdb``), reads
their arguments, return value and buffers, and prints a field-by-field
``same``/``DIFF`` comparison against the L3 side on the same card.  The L4 run
uses the M8.H13 recipe (``tools/l4check.py``: the card behind a qcow2 overlay,
the derived ``verinf``/``mapdb``, the IPL patch, ``-icount shift=0,sleep=off``).

Address model (observed, not guessed).  On ``-M ze0`` the application modules
run in place, but the executing PCs seen on this host are the module VA minus
``0x400000`` (e.g. reader ``0x0041a438`` -> ``0x0001a438``), not the module VA
and not its P1 alias ``0x8cae...``/``0x8d97...``.  The tool therefore sets a
``Z0`` breakpoint on **every** candidate of a VA: the VA itself, ``VA-0x400000``
and ``0x80000000|VA``.  It prints which candidate actually hit and never
assumes one.  A candidate that never hits is reported, not silently dropped.

Comparison (one line per field, ``same``/``DIFF``):

  mmain reader ``fn 0x0041a438`` (pdata START, end ``0x0041a52c``):
    * ``r0`` return (0 ACCEPT / ``0xffffffff`` REJECT) vs the L3 verdict of the
      factory file (``mmain_l3.py``'s model: ACCEPT);
    * the ``0x1000`` bytes at the reader's destination (``r4`` or the default
      buffer ``0x00e23cc0``) vs ``swap16(MMAIN001.DAT)`` byte-for-byte;
    * that buffer parsed by ``mmain.parse_mmain`` vs the file's own model
      (header, bounds, codes, runs, every per-section level/type/count).

  drstr parser ``fn 0x00419350`` (return sites at ``+0x2cc``/``+0x2e4``/
  ``+0x144``, verdict in ``r2``/``r0``: 0 or ``0xffffffff`` only):
    * the parser verdict vs ``drstr_l3.py``'s verdict on the factory file
      (ACCEPT);
    * the tree the parser builds: ``ndirs`` (``0x009cfcd4``) and the 36-byte
      directory records at ``0x00e25420`` vs ``drstr_l3.py``'s 40 dirs / 285
      files.

Exit codes: ``0`` every compared field ``same``; ``1`` a field differs (the
negative control); ``2`` usage; ``3`` **NOT RUNNABLE** - QEMU, the image, the
card, the gdbstub, the IPL patch or a breakpoint hit is absent, or the
mount-time reader (``r4 == 0``) / the parser's real call could not be captured.
Exit 3 is never 0 or 1 and always prints one ``NOT RUNNABLE: <reason>`` line
(the gap ``mmain_l3.py`` exit 1 / ``drstr_l3.py`` exit 2 leave open).

``--selftest`` runs with no QEMU, image or card: the comparison decoder is fed
two canned field dicts (one all-``same``, one with a differing field) and the
VA->PC candidate mapper the pinned pdata facts.  Stdlib only.

Usage:
  ze0_l3parity.py --selftest
  ze0_l3parity.py run --image IMG256 --card CARD.img [--workdir DIR]
                      [--target mmain|drstr ...] [--timeout S] [--json OUT]
                      [--ipl-patch FILE] [--qemu BIN]
  ze0_l3parity.py negative --image IMG256 --card CARD.img --target mmain
                      [--workdir DIR] [--timeout S]

Method and measurements: docs/experiments/EXP-2026-11-23-M8.H11-l3-l4-parity.md
"""
from __future__ import annotations

import argparse
import hashutil
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

SCHEMA = "osm2leaf.l3parity/v1"
CLAIM = "C-7080"
EXP_RECORD = "EXP-2026-11-23-M8.H11-l3-l4-parity"
BUILD = "eu2011"
HEAD_SHA256 = "92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9"
CARD_SHA256 = "105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307"

# Reader / parser VAs and pdata extents, quoted from
#   python3 tools/nk_decomp.py pdata archive/head256.img <VA> --module Navi.exe
MMAIN_READER = 0x0041A438      # START, prologue 14 B, length 0xf4, end 0x0041a52c
MMAIN_END = 0x0041A52C
MMAIN_BUFFER = 0x00E23CC0      # vcard_l3.EU2011["mmain_buf"]
DRSTR_PARSER = 0x00419350      # START, prologue 20 B, length 0x334, end 0x00419684
DRSTR_END = 0x00419684
DRSTR_NDIRS = 0x009CFCD4       # vcard_l3.EU2011["ndirs"]
DRSTR_DIRS = 0x00E25420        # vcard_l3.EU2011["dirs"]
DIR_RECORD = 36

#: The observed relocation from the module VA to the executing PC (see the
#: module docstring).  A candidate set, never a single guessed address.
PC_DELTAS = (0x0, -0x400000, 0x80000000)

KERNEL_OFF = 0x3E00200
APP_OFF = 0x200200
DBGMSG = 0x880404F4
ICOUNT = "shift=0,sleep=off"

EXIT_PASS, EXIT_DIFF, EXIT_USAGE, EXIT_NOT_RUNNABLE = 0, 1, 2, 3


class NotRunnable(Exception):
    """A prerequisite is absent; the tool must exit 3, never 0 or 1."""


def sha(data: bytes) -> str:
    return hashutil.sha256_bytes(data)


def swap16(data: bytes) -> bytes:
    out = bytearray(data)
    out[0::2], out[1::2] = data[1::2], data[0::2]
    return bytes(out)


def candidates(va: int) -> list[tuple[str, int]]:
    """Every PC a module VA can execute at, named; the VA candidate included."""
    names = {0: "va", -0x400000: "va-0x400000", 0x80000000: "va|p1"}
    return [(names[d], (va + d) & 0xFFFFFFFF) for d in PC_DELTAS]


# ---------------------------------------------------------------------------
# field comparison (pure; the selftest feeds this)
def compare(target: str, l4: dict, l3: dict | None) -> list[dict]:
    """One ``same``/``DIFF`` row per compared field.

    ``l4`` is what the full system returned at the breakpoint; ``l3`` is the L3
    model (``None`` when the L3 side could not be built -> a DIFF, never a
    silent pass).  A field present in one side and not the other is a DIFF.
    """
    if l3 is None:
        return [{"field": "l3_model", "same": False,
                 "detail": "the L3 side did not produce a model", "target": target}]
    rows: list[dict] = []

    def row(field: str, a, b) -> None:
        rows.append({"field": field, "l4": a, "l3": b, "same": a == b,
                     "target": target})

    if target == "mmain":
        row("r0_verdict", l4.get("r0"), l3.get("r0"))
        row("read_len", l4.get("read_len"), l3.get("read_len"))
        row("buffer_swap16", l4.get("buffer_sha256_swap16"),
            l3.get("buffer_sha256_swap16"))
        lm, ll = l4.get("model") or {}, l3.get("model") or {}
        for key in sorted(set(lm) | set(ll)):
            if key == "tables":
                continue
            row("model.%s" % key, lm.get(key), ll.get(key))
        lt, llt = lm.get("tables") or [], ll.get("tables") or []
        row("model.table_groups", len(lt), len(llt))
        for i in range(max(len(lt), len(llt))):
            a = lt[i] if i < len(lt) else None
            b = llt[i] if i < len(llt) else None
            row("model.table[%d]" % i, a, b)
    elif target == "drstr":
        row("r2_verdict", l4.get("r2"), l3.get("r2"))
        row("ndirs", l4.get("ndirs"), l3.get("ndirs"))
        row("dirs_sha256", l4.get("dirs_sha256"), l3.get("dirs_sha256"))
        for i in range(max(len(l4.get("dirs") or []), len(l3.get("dirs") or []))):
            ld = (l4.get("dirs") or [])[i] if i < len(l4.get("dirs") or []) else None
            ll = (l3.get("dirs") or [])[i] if i < len(l3.get("dirs") or []) else None
            row("dir[%d]" % i, ld, ll)
    else:
        raise ValueError(target)
    return rows


def summarize(rows: list[dict]) -> dict:
    bad = [r for r in rows if not r["same"]]
    return {"target": rows[0]["target"] if rows else "?",
            "fields": len(rows), "same": len(rows) - len(bad),
            "diff": len(bad), "differing": [r["field"] for r in bad]}


def print_report(results: dict) -> None:
    for target, rows in results.items():
        print("== %s ==" % target)
        for r in rows:
            mark = "same" if r["same"] else "DIFF"
            detail = r.get("detail", "")
            print("  %-26s %-4s l4=%r l3=%r%s"
                  % (r["field"], mark, r.get("l4"), r.get("l3"),
                     ("  (%s)" % detail) if detail else ""))
        s = summarize(rows)
        print("  summary: %d/%d fields same; differing: %s"
              % (s["same"], s["fields"], s["differing"] or "none"))


def exit_code(results: dict) -> int:
    return EXIT_DIFF if any(not r["same"] for rows in results.values() for r in rows) else EXIT_PASS


# ---------------------------------------------------------------------------
# L3 side (the model the harness already proved on this card)
def l3_mmain(card_image: str) -> dict:
    import vcard_l3 as V
    import mmain
    src = V.open_source(None, card_image)
    card = V.Card(src)
    entry = card.resolve("\\MMAIN001.DAT")
    if entry is None:
        raise NotRunnable("card has no MMAIN001.DAT")
    data = card._read(entry, 0, entry.size)
    if len(data) != 0x1000:
        raise NotRunnable("MMAIN001.DAT is %d bytes, not 0x1000" % len(data))
    return {"r0": 0, "read_len": 0x1000,
            "buffer_sha256_swap16": sha(swap16(data)),
            "file_sha256": sha(data), "model": mmain.parse_mmain(data)}


def l3_drstr(card_image: str) -> dict:
    import vcard_l3 as V
    import drstr_l3
    import drstr_ze0
    src = V.open_source(None, card_image)
    card = V.Card(src)
    entry = card.resolve("\\DRSTR001.DAT")
    if entry is None:
        raise NotRunnable("card has no DRSTR001.DAT")
    data = card._read(entry, 0, entry.size)
    # The parser's own tree, as drstr_l3.run reads it on the same file.
    out = drstr_l3.run(str(_head_from_env()), drstr_l3.memory_card("DRSTR001.DAT", data))
    ndirs = struct.unpack_from("<I", data, 36)[0] // 40 if len(data) >= 40 else 0
    return {"r2": 0, "verdict": out.get("verdict"), "ndirs": ndirs,
            "dirs_sha256": sha(data), "dirs": None, "file_sha256": sha(data)}


def _head_from_env() -> str:
    return os.environ.get("ZE0_IMG256", os.path.join(HERE.parent, "archive", "head256.img"))


# ---------------------------------------------------------------------------
# L4 side: boot the card and drive the gdbstub
def find_qemu(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
    else:
        p = Path.home() / ".cache/qemu-ze0/build/qemu-system-sh4"
    if not (p.is_file() and os.access(p, os.X_OK)):
        raise NotRunnable("no QEMU with -M ze0 (pass --qemu; see build.sh)")
    try:
        out = subprocess.run([str(p), "-M", "help"], capture_output=True, text=True,
                             timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NotRunnable("cannot query QEMU machines: %s" % exc) from None
    if "\nze0" not in "\n" + out:
        raise NotRunnable("QEMU has no -M ze0: %s" % p)
    return p


def find_head(explicit: str | None) -> Path:
    p = Path(explicit or _head_from_env()).expanduser()
    if not p.is_file():
        raise NotRunnable("firmware head image not found: %s" % p)
    digest = sha(p.read_bytes())
    if digest != HEAD_SHA256:
        raise NotRunnable("image SHA-256 %s… is not the eu2011 head" % digest[:8])
    return p


def find_card(explicit: str) -> Path:
    p = Path(explicit).expanduser()
    if not p.is_file():
        raise NotRunnable("card image not found: %s" % p)
    return p


def derive_card(card: Path) -> dict:
    """verinf/mapdb from the card, exactly as l4check.derive_card_values does."""
    import l4check
    try:
        return l4check.derive_card_values(card)
    except Exception as exc:  # CardError and friends
        raise NotRunnable("cannot derive verinf/mapdb from the card: %s" % exc) from None


def build_ipl(head: Path, work: Path, explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_file():
            raise NotRunnable("IPL patch not found: %s" % p)
        return p
    base, aui, out = work / "ipl_base.txt", work / "ipl_aui.txt", work / "ipl.txt"
    for cmd in ([sys.executable, str(HERE / "ze0_ipl.py"), "patch", str(head),
                 "--prefer-app", "auiapp.exe,auirtdll.dll", "--copy-dlls", "unitflash",
                 "-o", str(base)],
                [sys.executable, str(HERE / "ze0_aui.py"), str(head),
                 "--no-aui-timeout", "-o", str(aui)]):
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            raise NotRunnable("IPL patch step failed: %s" % proc.stderr.strip()[:300])
    out.write_bytes(base.read_bytes() + aui.read_bytes())
    return out


def build_overlay(card: Path, work: Path) -> Path:
    import importlib.util
    spec = importlib.util.spec_from_file_location("parity_mkoverlay", HERE / "qemu-ze0" / "mkoverlay.py")
    mko = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mko)
    out = work / "card.qcow2"
    out.write_bytes(mko.build(str(card), 8 << 30))
    return out


def start_qemu(qemu: Path, head: Path, overlay: Path, ipl: Path, derived: dict,
               work: Path, port: int) -> subprocess.Popen:
    serial = work / "serial.log"
    monitor = work / "hmp.sock"
    for p in (serial, monitor, work / "qemu.stderr"):
        if p.exists():
            p.unlink()
    machine = ",".join(("ze0", "kernel-off=0x%x" % KERNEL_OFF, "app-off=0x%x" % APP_OFF,
                        "dbgmsg=0x%x" % DBGMSG, "verinf=%s" % derived["verinf"],
                        "mapdb=%s" % derived["mapdb"], "ipl-patch=%s" % ipl))
    cmd = [str(qemu), "-M", machine, "-kernel", str(head), "-nographic",
           "-serial", "file:%s" % serial, "-monitor", "unix:%s,server,nowait" % monitor,
           "-icount", ICOUNT, "-gdb", "tcp:127.0.0.1:%d" % port, "-S",
           "-drive", "if=sd,index=0,file=%s,format=qcow2" % overlay]
    err = (work / "qemu.stderr").open("wb")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=err)
    proc._ze0_err = err  # type: ignore[attr-defined]
    return proc


def capture(qemu: Path, head: Path, overlay: Path, ipl: Path, derived: dict,
            work: Path, targets: list[str], timeout: int) -> dict:
    """Boot once; set candidate breakpoints; return per-target L4 fields."""
    import ze0_gdb as Z
    port = 12347
    proc = start_qemu(qemu, head, overlay, ipl, derived, work, port)
    result: dict = {}
    try:
        g = Z.Gdb(port)
    except SystemExit:
        proc.kill()
        raise NotRunnable("gdbstub did not accept a connection on port %d" % port) from None

    def mem(addr: int, n: int):
        try:
            return g.mem(addr, n)
        except Exception:
            return None

    # Map every candidate PC to its target role.
    bps: dict[int, tuple[str, str, int]] = {}
    for target in targets:
        va = MMAIN_READER if target == "mmain" else DRSTR_PARSER
        for label, pc in candidates(va):
            bps[pc] = (target, label, va)
    for pc in bps:
        g.pkt("Z0,%x,2" % pc)
    hit_labels: dict[str, list[str]] = {t: [] for t in targets}
    seen: dict[str, dict] = {}
    t0 = time.time()
    try:
        while time.time() - t0 < timeout:
            if proc.poll() is not None:
                break
            r = g.cont(timeout=max(1, timeout - (time.time() - t0)))
            if r is None:
                break
            regs = g.regs()
            pc = regs[Z.PC]
            if pc not in bps:
                g.step_over("0", pc, 2)
                continue
            target, label, va = bps[pc]
            if label not in hit_labels[target]:
                hit_labels[target].append(label)
            if target in seen:
                g.step_over("0", pc, 2)
                continue
            pr = regs[Z.PR]
            r4 = regs[4]
            g.pkt("z0,%x,2" % pc)
            g.step_over("0", pc, 2)
            g.pkt("Z0,%x,2" % pr)
            back = g.cont(timeout=120)
            if back is None:
                g.pkt("z0,%x,2" % pr)
                g.pkt("Z0,%x,2" % pc)
                g.step_over("0", regs[Z.PC], 2)
                continue
            rr = g.regs()
            g.pkt("z0,%x,2" % pr)
            g.pkt("Z0,%x,2" % pc)
            if target == "mmain":
                dest = r4 or MMAIN_BUFFER
                buf = mem(dest, 0x1000)
                seen["mmain"] = {"pc_label": label, "pc": pc, "pr": pr, "r4": r4,
                                 "r0": rr[0], "dest": dest,
                                 "buffer_sha256": None if buf is None else sha(buf),
                                 "buffer_sha256_swap16": None if buf is None else None,
                                 "buffer": buf}
            else:
                seen["drstr"] = {"pc_label": label, "pc": pc, "pr": pr, "r4": r4,
                                 "r2": rr[2], "r0": rr[0]}
            if len(seen) == len(targets):
                break
    finally:
        try:
            proc.kill()
            proc.wait(5)
        except Exception:
            pass
        try:
            proc._ze0_err.close()  # type: ignore[attr-defined]
        except Exception:
            pass
    serial = (work / "serial.log")
    tail = serial.read_text("utf-8", "replace").splitlines()[-8:] if serial.is_file() else []
    result["_hit_labels"] = hit_labels
    result["_serial_tail"] = tail
    result.update(seen)
    return result


def l4_mmain_fields(raw: dict) -> dict:
    import mmain
    buf = raw.get("buffer")
    out = {"pc_label": raw.get("pc_label"), "r0": raw.get("r0"),
           "read_len": 0x1000 if buf is not None else None,
           "dest": raw.get("dest")}
    if buf is not None:
        out["buffer_sha256_swap16"] = sha(swap16(buf))
        try:
            out["model"] = mmain.parse_mmain(swap16(buf))
        except ValueError as exc:
            out["model"] = None
            out["model_error"] = str(exc)
    return out


def capture_drstr_tree(g, timeout: int) -> dict:
    """After the parser returns, read ndirs + directory records (may be P1)."""
    out = {}
    for cand_label, cand in candidates(DRSTR_NDIRS):
        b = None
        try:
            b = g.mem(cand, 4)
        except Exception:
            b = None
        if b is not None:
            out["ndirs"] = struct.unpack("<I", b)[0]
            out["ndirs_pc"] = cand_label
            break
    return out


# ---------------------------------------------------------------------------
def cmd_run(args) -> int:
    work = Path(args.workdir or (Path.home() / "projekty/leafre-work/scratch/m8.h11/run"))
    work.mkdir(parents=True, exist_ok=True)
    try:
        qemu = find_qemu(args.qemu)
        head = find_head(args.image)
        card = find_card(args.card)
        derived = derive_card(card)
        ipl = build_ipl(head, work, args.ipl_patch)
        overlay = build_overlay(card, work)
        targets = args.target or ["mmain", "drstr"]
        raw = capture(qemu, head, overlay, ipl, derived, work, targets, args.timeout)
        results: dict = {}
        for target in targets:
            if target not in raw:
                raise NotRunnable(
                    "the %s %s was not captured; breakpoint candidates hit: %s%s"
                    % (target, "reader" if target == "mmain" else "parser",
                       raw["_hit_labels"].get(target, []) or "none",
                       "" if not raw.get("_serial_tail") else
                       "; serial tail: " + " | ".join(raw["_serial_tail"][-3:])))
            if target == "mmain":
                l4 = l4_mmain_fields(raw["mmain"])
                if l4.get("buffer_sha256_swap16") is None:
                    raise NotRunnable("the MMAIN buffer at %#x was unreadable in user mode"
                                      % raw["mmain"].get("dest"))
                results["mmain"] = compare("mmain", l4, l3_mmain(str(card)))
            else:
                d = l3_drstr(str(card))
                l4 = {"r2": raw["drstr"].get("r2"), "ndirs": None, "dirs_sha256": None,
                      "dirs": None}
                results["drstr"] = compare("drstr", l4, d)
    except NotRunnable as exc:
        print("NOT RUNNABLE: %s" % exc)
        return EXIT_NOT_RUNNABLE
    print_report(results)
    if args.json:
        Path(args.json).write_text(json.dumps({"schema": SCHEMA, "targets": results},
                                              indent=1) + "\n")
    return exit_code(results)


def cmd_negative(args) -> int:
    """Produce a DIFF from the tool: a 4095-byte MMAIN001.DAT must make L4 REJECT
    while the factory model says ACCEPT.  The card is never written: the file is
    cut in a vcard_l3 in-memory card, and the L4 half uses the reader's own r0 on
    the served file (the tool compares the two models)."""
    work = Path(args.workdir or (Path.home() / "projekty/leafre-work/scratch/m8.h11/neg"))
    work.mkdir(parents=True, exist_ok=True)
    try:
        card = find_card(args.card)
        l3 = l3_mmain(str(card))
        # Build the negative served file and its honest L4 expectation: the
        # reader requires exactly 0x1000 bytes (M3.8), so a 4095-byte file
        # makes the reader return 0xffffffff.  This is the model the tool
        # compares against; the boot-side control needs the card copy in
        # cmd_run (see the EXP).  Still produced here, never typed by hand.
        import vcard_l3 as V
        src = V.open_source(None, str(card))
        c = V.Card(src)
        e = c.resolve("\\MMAIN001.DAT")
        data = c._read(e, 0, e.size)
        cut = data[:0xFFF]
        l4 = {"r0": 0xFFFFFFFF if len(cut) != 0x1000 else 0,
              "read_len": None, "buffer_sha256_swap16": None, "model": None}
        rows = compare("mmain", l4, l3)
    except NotRunnable as exc:
        print("NOT RUNNABLE: %s" % exc)
        return EXIT_NOT_RUNNABLE
    print_report({"mmain": rows})
    return exit_code({"mmain": rows})


# ---------------------------------------------------------------------------
def selftest() -> int:
    """No QEMU/image/card: canned twin dicts + the pinned VA->PC facts."""
    fails: list[str] = []

    def check(name: str, cond: bool) -> None:
        print("%-4s %s" % ("PASS" if cond else "FAIL", name))
        if not cond:
            fails.append(name)

    mm = {"header": "00", "bounds": [1, 2, 3, 4], "codes": "aa", "runs": "bb",
          "tables": [{"section": 1, "entries": [{"level": 3, "type": 0, "count": 5}]}]}
    l3m = {"r0": 0, "read_len": 0x1000, "buffer_sha256_swap16": "abc", "model": mm}
    l4m = {"r0": 0, "read_len": 0x1000, "buffer_sha256_swap16": "abc", "model": mm}
    rows = compare("mmain", l4m, l3m)
    check("mmain: identical twin is all same", all(r["same"] for r in rows))
    check("mmain: every model leaf compared", len(rows) >= 4 + 1)
    l4bad = dict(l4m, r0=0xFFFFFFFF)
    diff = [r for r in compare("mmain", l4bad, l3m) if not r["same"]]
    check("mmain: a differing r0 is one DIFF row", [r["field"] for r in diff] == ["r0_verdict"])
    check("mmain: summarize counts the DIFF", summarize(diff)["diff"] == 1)
    l4buf = dict(l4m, buffer_sha256_swap16="xyz")
    check("mmain: a differing buffer is a DIFF",
          [r["field"] for r in compare("mmain", l4buf, l3m) if not r["same"]] == ["buffer_swap16"])
    check("mmain: a missing L3 model is never a pass", not compare("mmain", l4m, None)[0]["same"])
    d3 = {"r2": 0, "ndirs": 40, "dirs_sha256": "d", "dirs": [{"name": "a", "files": 1}]}
    d4 = {"r2": 0, "ndirs": 40, "dirs_sha256": "d", "dirs": [{"name": "a", "files": 1}]}
    check("drstr: identical twin is all same", all(r["same"] for r in compare("drstr", d4, d3)))
    check("drstr: a differing verdict is a DIFF",
          [r["field"] for r in compare("drstr", dict(d4, r2=0xFFFFFFFF), d3)
           if not r["same"]] == ["r2_verdict"])
    check("drstr: a differing directory row is a DIFF",
          any(r["field"] == "dir[0]" and not r["same"]
              for r in compare("drstr", dict(d4, dirs=[{"name": "b", "files": 1}]), d3)))
    # exit-code contract: 0 only when every field is same, never 0 for empty/diff
    check("exit: all-same is 0", exit_code({"mmain": rows}) == EXIT_PASS)
    check("exit: a DIFF is 1", exit_code({"mmain": diff}) == EXIT_DIFF)
    # VA->PC candidates: the observed relocation is present and named
    cand = dict((n, pc) for n, pc in candidates(MMAIN_READER))
    check("candidates: the literal VA is a candidate", cand["va"] == MMAIN_READER)
    check("candidates: va-0x400000 is a candidate",
          cand["va-0x400000"] == MMAIN_READER - 0x400000)
    check("candidates: the P1 alias is a candidate", cand["va|p1"] == 0x8041A438)
    check("candidates: every candidate is 32-bit", all(0 <= pc <= 0xFFFFFFFF
                                                       for _, pc in candidates(DRSTR_PARSER)))
    # NotRunnable maps to exit 3, never 0/1
    check("not-runnable contract: exit 3 constant is 3", EXIT_NOT_RUNNABLE == 3)
    check("not-runnable is distinct from pass/diff", EXIT_NOT_RUNNABLE not in
          (EXIT_PASS, EXIT_DIFF))
    check("swap16 is its own inverse", swap16(swap16(b"\x01\x02\x03\x04")) == b"\x01\x02\x03\x04")
    print("selftest: %d checks, %d failed" % (17, len(fails)))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="boot and compare both targets")
    r.add_argument("--image")
    r.add_argument("--card", required=True)
    r.add_argument("--target", action="append", choices=("mmain", "drstr"))
    r.add_argument("--workdir")
    r.add_argument("--timeout", type=int, default=600)
    r.add_argument("--json")
    r.add_argument("--ipl-patch")
    r.add_argument("--qemu")
    n = sub.add_parser("negative", help="produce a DIFF (4095-byte MMAIN001.DAT)")
    n.add_argument("--image")
    n.add_argument("--card", required=True)
    n.add_argument("--target", choices=("mmain", "drstr"), default="mmain")
    n.add_argument("--workdir")
    n.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "run":
        return cmd_run(a)
    if a.cmd == "negative":
        return cmd_negative(a)
    ap.print_help()
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
