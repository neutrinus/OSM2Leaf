#!/usr/bin/env python3
"""Run the LCTBL001 name convert loop ``0x003ca858`` on one real name (M3.15).

The M3.15 EXP claimed the swap direction from an *executed* control, but the
only committed tool that ran firmware (``read_watch_l3.py probe``) reports
``NO READER`` for ``0x003ca858`` and no committed command showed the bytes
swap.  This tool closes that gap: it maps ``Navi.exe`` sec0 into the PySh4
engine, seeds a buffer with a name taken from the card (or ``--hex``), calls
``0x003ca858(buf, len, mode)`` and prints the buffer before and after.

A real executed run is the positive control; two structural controls decide
the direction rather than a pinned hash:

* ``--expect swap`` (default) passes only when every ``u16`` of the buffer is
  byte-reversed (``a b -> b a``) and the trailing pad is unchanged;
* ``--expect none`` passes only when the buffer is unchanged (the negative
  control: a wrong address that does not swap must not be read as a pass);
* ``--fault-at VA`` runs ``VA`` instead of ``0x003ca858`` so the selftest can
  prove a wrong entry does not produce the swap signature.

Evidence: ``EXP-2026-11-20-M3.15-lctbl-reader``; C-2205.

Usage::

  lctbl_string_decode.py --selftest
  lctbl_string_decode.py IMG --hex "42 65 72 61 6e 6f 76 fd 63 68"
  lctbl_string_decode.py IMG --file LCTBL001.DAT --stream 2 --record 0 --field 3
  lctbl_string_decode.py IMG --file LCTBL001.DAT --stream 2 --record 0 --field 3 \\
      --expect swap --json -
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
for path in (HERE, os.path.join(HERE, "l3_harness")):
    if path not in sys.path:
        sys.path.insert(0, path)

import point_walk_l3 as pw  # noqa: E402
from engine import PySh4  # noqa: E402

IMAGE_START = 0x200200
DECODE_VA = 0x003CA858
BUF_VA = 0x00E00000
STACK_VA = 0x00E10000


def _engines(text_va: int, text: bytes, payload: bytes):
    eng = PySh4(endian="little")
    eng.map("text", text_va, text, "rx")
    eng.map("buf", BUF_VA, bytearray(payload) + bytearray(0x40), "rw")
    eng.map("stack", STACK_VA, bytearray(0x4000), "rw")
    eng.set_regs(r15=STACK_VA + 0x3F00)
    return eng


def run_decode(image: str, payload: bytes, mode: int = 1,
               entry: int = DECODE_VA) -> tuple[int, bytes]:
    """Call ``entry`` (default ``0x003ca858``) on *payload*; return (r0, out)."""
    data = pw.load_image(image)
    text_va, text = pw.navi_text(data, IMAGE_START)
    eng = _engines(text_va, text, payload)
    ret = eng.call(entry, [BUF_VA, len(payload), mode])
    if not payload:
        return ret & 0xFFFFFFFF, b""
    return ret & 0xFFFFFFFF, bytes(eng.read_mem(BUF_VA, len(payload)))


def swap_signature(before: bytes, after: bytes) -> bool:
    """True when every even-length ``u16`` is byte-reversed and the tail stays."""
    if len(before) != len(after):
        return False
    for i in range(0, len(before) - 1, 2):
        if after[i] != before[i + 1] or after[i + 1] != before[i]:
            return False
    if len(before) & 1 and after[-1] != before[-1]:
        return False
    return True


def record_name(path: str, stream: int, record: int, field: int) -> bytes:
    import lctbl_names
    import lctbl_records

    data = Path(path).read_bytes()
    streams = lctbl_names.scan_streams(data)
    records = lctbl_records.parse_stream(streams[stream]["data"])
    return records[record]["names"][field]


def _selftest() -> int:
    fails = 0

    def check(name: str, cond: bool) -> None:
        nonlocal fails
        if not cond:
            fails += 1
            print(f"FAIL {name}")

    name = bytes.fromhex("42 65 72 61 6e 6f 76 fd 63 68")
    swapped = bytes.fromhex("65 42 61 72 6f 6e fd 76 68 63")
    check("swap signature accepts high-byte-first", swap_signature(name, swapped))
    check("swap signature rejects identity", not swap_signature(name, name))
    check("swap signature rejects a half swap",
          not swap_signature(name, name[:2] + swapped[2:]))
    check("swap signature rejects unequal length",
          not swap_signature(name, swapped + b"\x00"))
    # odd length: the final byte is a pad and must survive
    odd = bytes.fromhex("42 65 72 61 6e 6f 76 fd 63 68")
    check("swap signature keeps a trailing odd byte",
          swap_signature(odd, bytes.fromhex("65 42 61 72 6f 6e fd 76 68 63")))
    # structural inverse: swapping twice is the identity
    check("double swap is identity", swap_signature(swapped, name))
    print(f"selftest: {'OK' if not fails else 'FAIL ' + str(fails)}")
    return 0 if not fails else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--selftest", action="store_true")
    p.add_argument("image", nargs="?", help="256 MiB firmware head (archive/head256.img)")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--hex", help="name bytes as hex, e.g. '42 65 72'")
    src.add_argument("--file", help="LCTBL001.DAT to pull a name from")
    p.add_argument("--stream", type=int, default=0)
    p.add_argument("--record", type=int, default=0)
    p.add_argument("--field", type=int, default=2)
    p.add_argument("--mode", type=int, default=1)
    p.add_argument("--entry", type=lambda s: int(s, 0), default=DECODE_VA)
    p.add_argument("--expect", choices=("swap", "none"), default="swap")
    p.add_argument("--json", nargs="?", const="-", default=None)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return _selftest()
    if not args.image:
        build_parser().print_help()
        return 2
    if not args.hex and not args.file:
        print("error: give --hex or --file", file=sys.stderr)
        return 2
    if args.file:
        payload = record_name(args.file, args.stream, args.record, args.field)
    elif args.hex:
        payload = bytes.fromhex(args.hex)
    else:
        print("error: give --hex or --file", file=sys.stderr)
        return 2
    ret, out = run_decode(args.image, payload, args.mode, args.entry)
    swapped = swap_signature(payload, out)
    unchanged = out == payload
    if args.expect == "swap":
        ok = swapped and not unchanged
    else:
        ok = unchanged
    doc = {
        "entry": f"0x{args.entry:08x}",
        "mode": args.mode,
        "len": len(payload),
        "before": payload.hex(" "),
        "after": out.hex(" "),
        "r0": f"0x{ret:08x}",
        "swap_signature": swapped,
        "unchanged": unchanged,
        "expect": args.expect,
        "ok": ok,
    }
    if args.json is not None:
        text = json.dumps(doc, indent=2)
        if args.json == "-":
            print(text)
        else:
            Path(args.json).write_text(text + "\n", encoding="utf-8")
    else:
        print(f"entry {doc['entry']} mode {args.mode} len {len(payload)}")
        print(f"before {doc['before']}")
        print(f"after  {doc['after']}")
        print(f"r0 {doc['r0']} swap={swapped} unchanged={unchanged}")
        print("result:", "PASS" if ok else "FAIL (expect %s)" % args.expect)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
