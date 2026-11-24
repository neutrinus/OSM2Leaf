#!/usr/bin/env python3
"""Static map of the ``serial_scif.dll`` receive path (TODO M8.H66).

Derives, from firmware bytes, the per-channel SCIF receive mechanism:
SCIF register literals (FRDR = receive FIFO, FTDR = transmit FIFO) found in
the executable section's literal pools, the HPB-DMAC/general-DMAC base
literals, and every call site of the per-channel DMA dispatcher.  The SH-4
decode is little-endian (pinned in sh4dis); addresses come from cerom.py.
Stdlib only.

Usage:
  scif_rx_map.py IMG [--image-start 0x3e00200] [--module serial_scif.dll]
  scif_rx_map.py IMG --json
  scif_rx_map.py --selftest
"""

from __future__ import annotations

import argparse
import json
import struct
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import cerom
import sh4dis

IMAGE_READ_BYTES = 268435456
SCIF_WINDOW = (0xFFE40000, 0xFFE4FFFF)
HPB_DMAC_BASE = 0xFFC08000
GEN_DMAC_BASE = 0xFF801000
DISPATCHER_CANDIDATE = 0x0398D084
DEFAULT_MODULE = "serial_scif.dll"
DEFAULT_START = 0x3E00200


def _load_module(img_path, image_start, module):
    with open(img_path, "rb") as fh:
        data = fh.read(IMAGE_READ_BYTES)
    r = cerom.CERom(data, image_start)
    m = r.module(module)
    mem, exec_segs, sections = sh4dis.load_segments(img_path, image_start, module)
    return r, data, mem, exec_segs, sections, m


def _pool_words(r, data, m):
    for s in r.o32(m):
        if not (s["flags"] & 0x20000000):
            continue
        if s["flags"] & cerom.IMAGE_SCN_COMPRESSED:
            continue
        off = r.va2file(s["dataptr"])
        blob = data[off:off + s["psize"]]
        va = s["realaddr"]
        for i in range(0, len(blob) - 3, 4):
            yield va + i, struct.unpack_from("<I", blob, i)[0]


def _scif_pool_words(r, data, m):
    rows = []
    for pool_va, word in _pool_words(r, data, m):
        if SCIF_WINDOW[0] <= word <= SCIF_WINDOW[1]:
            channel = (word - SCIF_WINDOW[0]) >> 12
            kind = {0x00: "base", 0x0C: "FTDR", 0x14: "FRDR"}.get(word & 0xFF, "other")
            rows.append({"pool_va": pool_va, "word": word, "channel": channel,
                         "offset": word & 0xFF, "kind": kind})
    return rows


def _dmac_dispatchers(r, data, m):
    rows = []
    for pool_va, word in _pool_words(r, data, m):
        if word in (HPB_DMAC_BASE, GEN_DMAC_BASE):
            rows.append({"pool_va": pool_va, "word": word,
                         "kind": "hpb" if word == HPB_DMAC_BASE else "general"})
    return rows


def _fn_start(exec_segs, va):
    for base, blob in exec_segs:
        if base <= va < base + len(blob):
            i = va - base
            while i > 0:
                if blob[i - 1] == 0xE6 and blob[i - 2] == 0x2F:
                    return base + i - 2
                i -= 1
            return base
    return None


def _callers_of(r, data, m, target):
    rows = []
    for pool_va, word in _pool_words(r, data, m):
        if word != target:
            continue
        for s in r.o32(m):
            if not (s["flags"] & 0x20000000) or (s["flags"] & cerom.IMAGE_SCN_COMPRESSED):
                continue
            off = r.va2file(s["dataptr"])
            base = s["realaddr"]
            blob = data[off:off + s["vsize"]]
            for i in range(0, len(blob) - 1, 2):
                hw = struct.unpack_from("<H", blob, i)[0]
                t = sh4dis.movl_pc_target(base + i, hw)
                if t is None or t[1] != pool_va:
                    continue
                if i + 3 < len(blob):
                    nxt = struct.unpack_from("<H", blob, i + 2)[0]
                    if (nxt & 0xF0FF) == 0x400B:
                        rows.append({"load_va": base + i, "pool_va": pool_va,
                                     "jsr_va": base + i + 2})
    return rows


def analyze(img_path, image_start=DEFAULT_START, module=DEFAULT_MODULE):
    r, data, mem, exec_segs, sections, m = _load_module(img_path, image_start, module)
    scif = _scif_pool_words(r, data, m)
    dmac = _dmac_dispatchers(r, data, m)
    callers = _callers_of(r, data, m, DISPATCHER_CANDIDATE)
    return {"module": module, "image_start": hex(image_start),
            "exec_sections": [s for s in sections if s["exec"]],
            "scif_pool_words": scif, "dmac_dispatchers": dmac,
            "dispatcher_call_sites": callers}


def _classify(word):
    if not (SCIF_WINDOW[0] <= word <= SCIF_WINDOW[1]):
        return None
    return ((word - SCIF_WINDOW[0]) >> 12,
            {0x00: "base", 0x0C: "FTDR", 0x14: "FRDR"}.get(word & 0xFF, "other"))


def _selftest():
    ok = 0
    fail = 0

    def check(cond, label):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            print("FAIL:", label)

    check(sh4dis.decode(0x2FE6).text == "mov.l r14,@-r15",
          "LE 0x2fe6 decodes to push r14")
    check(sh4dis.decode(0xE62F).text == "mov #47,r6",
          "byte-swapped halfword does NOT decode to push (BE trap)")
    check(_classify(0xffe41014) == (1, "FRDR"), "SCIF1 FRDR classified")
    check(_classify(0xffe47014) == (7, "FRDR"), "SCIF7 FRDR classified")
    check(_classify(0xffe4800c) == (8, "FTDR"), "SCIF8 FTDR classified")
    check(_classify(0xffe41010) == (1, "other"), "+0x10 is 'other', not FRDR")
    check(_classify(0xffe44000) == (4, "base"), "SCIF4 base classified")
    check(HPB_DMAC_BASE == 0xFFC08000 and GEN_DMAC_BASE == 0xFF801000,
          "both DMAC bases pinned")
    print("scif_rx_map selftest: OK (%d checks, %d failed)" % (ok + fail, fail))
    return 0 if fail == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", nargs="?")
    ap.add_argument("--image-start", type=lambda x: int(x, 0), default=DEFAULT_START)
    ap.add_argument("--module", default=DEFAULT_MODULE)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not args.image:
        ap.error("image is required")
    rep = analyze(args.image, args.image_start, args.module)
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0
    print("module %s  image_start %s" % (rep["module"], rep["image_start"]))
    for s in rep["exec_sections"]:
        print("  exec sec va=%#x vsize=%#x" % (s["va"], s["vsize"]))
    print("SCIF pool words (%d):" % len(rep["scif_pool_words"]))
    for w in rep["scif_pool_words"]:
        print("  pool %#x = %#x  ch%d %s (+%#x)" %
              (w["pool_va"], w["word"], w["channel"], w["kind"], w["offset"]))
    print("DMAC dispatcher literals (%d):" % len(rep["dmac_dispatchers"]))
    for w in rep["dmac_dispatchers"]:
        print("  pool %#x = %#x  %s" % (w["pool_va"], w["word"], w["kind"]))
    print("Call sites to dispatcher %#x (%d):" %
          (DISPATCHER_CANDIDATE, len(rep["dispatcher_call_sites"])))
    for c in rep["dispatcher_call_sites"]:
        print("  load %#x  jsr %#x" % (c["load_va"], c["jsr_va"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
