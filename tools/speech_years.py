#!/usr/bin/env python3
"""Compare the SPEECH/ archives of two Leaf ZE0 card years (offline, read-only).

The three file kinds GID, TTS and AGM share one archive framing:

  0x00  serial: 16 ASCII digits
  0x10  u32 total size
  0x14  u32 header size
  0x18  u32 flags
  0x1c  u32 entry count
  0x20  count * (name[12] + u32 offset + u32 size + u32 size2)

This tool prints the fields of one file (`describe`), byte-compares the same
kind from two years (`compare`) and decodes a UTF-16LE language-name table from
a firmware dump at a given VA (`langs`).  It is deliberately a *printing*
tool: every number quoted in an experiment report comes from one of its
commands.  No vendor bytes are written to the repository.

Usage::

    python3 tools/speech_years.py describe 2011/SSP00000.GID
    python3 tools/speech_years.py compare 2011/SSP00000.GID 2014/SSP00000.GID
    python3 tools/speech_years.py langs dump.bin --va 0x32354 --count 10
    python3 tools/speech_years.py --selftest

Exit codes: 0 = success, 1 = comparison found a difference, 2 = usage/IO error.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import tempfile
from pathlib import Path

SERIAL_LEN = 16
ENTRY_SIZE = 24
NAME_LEN = 12


def parse_archive(data: bytes) -> dict:
    """Decode the common SPEECH archive header and its entry table."""
    if len(data) < 0x20:
        raise ValueError(f"need >= 32 bytes, got {len(data)}")
    try:
        serial = data[:SERIAL_LEN].decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError(f"serial is not ASCII: {exc}") from exc
    total, header_size, flags, count = struct.unpack_from("<IIII", data, 0x10)
    if count > 4096:
        raise ValueError(f"implausible entry count {count}")
    entries = []
    pos = 0x20
    for index in range(count):
        if pos + ENTRY_SIZE > len(data):
            raise ValueError(f"entry {index} past end of file")
        raw_name = data[pos : pos + NAME_LEN]
        name = raw_name.split(b"\0", 1)[0].decode("latin-1")
        offset, size, size2 = struct.unpack_from("<III", data, pos + NAME_LEN)
        entries.append({"index": index, "name": name, "offset": offset,
                        "size": size, "size2": size2})
        pos += ENTRY_SIZE
    return {
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "serial": serial,
        "total": total,
        "header_size": header_size,
        "flags": flags,
        "count": count,
        "entries": entries,
    }


def svox_config(data: bytes) -> dict:
    """Find the SVOX TTS build stamp in the leading configuration block."""
    head = data[:0x1000]
    result: dict = {"found": False}
    for key in (b"MAJVERS", b"MINVERS", b"REV ", b"SUBREV", b"TAVERS",
                b"SOFTWID", b"LINGWID", b"USRTIMESTAMP"):
        off = head.find(key)
        if off < 0:
            continue
        end = head.find(b"  ", off)
        if end < 0:
            end = min(off + 64, len(head))
        result[key.decode().strip()] = head[off + len(key) : end].decode(
            "latin-1").strip()
        result["found"] = True
    return result


def first_difference(left: bytes, right: bytes) -> int | None:
    for index in range(min(len(left), len(right))):
        if left[index] != right[index]:
            return index
    return None


def describe_archive(path: Path) -> dict:
    data = path.read_bytes()
    info = parse_archive(data)
    info["path"] = str(path)
    if path.name.endswith(".TTS"):
        info["svox"] = svox_config(data)
    if info["entries"]:
        first = info["entries"][0]
        info["first_entry_head"] = data[
            first["offset"] : first["offset"] + min(16, first["size"])
        ].hex()
    return info
    return info


def format_archive(info: dict) -> str:
    lines = [
        f"path: {info['path']}",
        f"size: {info['size']}",
        f"sha256: {info['sha256']}",
        f"serial: {info['serial']}",
        f"total: {info['total']}",
        f"header_size: {info['header_size']}",
        f"flags: {info['flags']}",
        f"count: {info['count']}",
    ]
    for entry in info["entries"][:8]:
        lines.append(
            f"  [{entry['index']}] {entry['name']!r} offset=0x{entry['offset']:x} "
            f"size={entry['size']} size2={entry['size2']}"
        )
    if "svox" in info:
        svox = info["svox"]
        for key, value in sorted(svox.items()):
            if key != "found":
                lines.append(f"  SVOX {key}: {value}")
    if "first_entry_head" in info:
        lines.append(f"  first entry head: {info['first_entry_head']}")
    return "\n".join(lines)


def compare_archives(left_path: Path, right_path: Path) -> tuple[str, bool]:
    left = left_path.read_bytes()
    right = right_path.read_bytes()
    a, b = parse_archive(left), parse_archive(right)
    lines = [
        f"A {left_path}: size={a['size']} sha256={a['sha256']}",
        f"B {right_path}: size={b['size']} sha256={b['sha256']}",
        f"A serial={a['serial']} total={a['total']} hdr={a['header_size']} "
        f"flags={a['flags']} count={a['count']}",
        f"B serial={b['serial']} total={b['total']} hdr={b['header_size']} "
        f"flags={b['flags']} count={b['count']}",
    ]
    different = False
    for key in ("serial", "total", "header_size", "flags", "count"):
        if a[key] != b[key]:
            lines.append(f"DIFF field {key}: {a[key]!r} -> {b[key]!r}")
            different = True
    names_a = [e["name"] for e in a["entries"]]
    names_b = [e["name"] for e in b["entries"]]
    if names_a != names_b:
        lines.append(f"DIFF entry names: {names_a[:12]} -> {names_b[:12]}")
        different = True
    first = first_difference(left, right)
    if first is not None:
        lines.append(f"DIFF first byte 0x{first:x} "
                     f"({left[first]:02x} -> {right[first]:02x})")
        different = True
    if left == right:
        lines.append("byte-identical")
    lines.append("RESULT: " + ("different" if different else "same framing and bytes"))
    return "\n".join(lines), different


def decode_langs(dump: bytes, va: int, count: int) -> list[dict]:
    """Decode `count` UTF-16LE names from a firmware dump.

    The build's language-name table stores each two-letter name as two UTF-16
    halfwords followed by a 4-byte zero word, i.e. an 8-byte stride, and ends
    with a ``ffff ffff`` sentinel.  The dump must start at the table's first
    name so that byte 0 maps to ``--va``.
    """
    out = []
    pos = 0
    for index in range(count):
        if pos + 8 > len(dump):
            raise ValueError(f"table entry {index} past end of dump")
        word0, word1 = struct.unpack_from("<HH", dump, pos)
        chars = ""
        for word in (word0, word1):
            if word == 0:
                break
            chars += chr(word)
        out.append({"index": index, "va": va + pos, "name": chars})
        pos += 8
    return out


def format_langs(rows: list[dict]) -> str:
    return "\n".join(f"[{r['index']}] VA 0x{r['va']:08x}: {r['name']!r}"
                     for r in rows)


def selftest() -> int:
    failures = []
    def check(label: str, ok: bool) -> None:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
        if not ok:
            failures.append(label)

    def synth(serial: bytes, total: int, hdr: int, flags: int,
              entries: list[tuple[str, bytes]]) -> bytes:
        count = len(entries)
        head = bytearray(serial.ljust(16, b"0")[:16])
        head += struct.pack("<IIII", total, hdr, flags, count)
        payloads = bytearray()
        pos = 0x20 + count * ENTRY_SIZE
        table = bytearray()
        for name, payload in entries:
            table += name.encode("ascii").ljust(NAME_LEN, b"\0")
            table += struct.pack("<III", pos, len(payload), len(payload))
            payloads += payload
            pos += len(payload)
        return bytes(head + table + payloads)

    print("archive parse and comparison")
    ent = [("A0000000.BIN", b"\x11" * 16), ("B0000000.BIN", b"\x22" * 8)]
    base = synth(b"0000102020100524", 0x1000, 0x38, 0, ent)
    info = parse_archive(base)
    check("total field decodes", info["total"] == 0x1000)
    check("serial decodes", info["serial"] == "0000102020100524")
    check("header size decodes", info["header_size"] == 0x38)
    check("entry count decodes", info["count"] == 2)
    check("entry names decode", [e["name"] for e in info["entries"]] ==
          ["A0000000.BIN", "B0000000.BIN"])
    check("entry offset decodes", info["entries"][0]["offset"] == 0x50)
    check("self compare is byte-identical",
          first_difference(base, base) is None)
    changed = synth(b"0000302420140919", 0x1000, 0x38, 0, ent)
    check("first difference at serial byte 4",
          first_difference(base, changed) == 4)
    grown = synth(b"0000102020100524", 0x1000, 0x38, 0,
                  ent + [("C0000000.BIN", b"\x33" * 4)])
    check("extra entry changes count", parse_archive(grown)["count"] == 3)
    bad = bytearray(base)
    struct.pack_into("<I", bad, 0x1c, 9999)
    try:
        parse_archive(bytes(bad))
        check("implausible count rejected", False)
    except ValueError:
        check("implausible count rejected", True)

    print("SVOX fields")
    blob = (b"MAJVERS 5  MINVERS 0  REV 0  SUBREV 3-PS-P2-XX-exported  "
            b"TAVERS 4.3.0.0-2  " b"SOFTWID 41003  LINGWID 0  " + b"\x00" * 64)
    fields = svox_config(blob)
    check("MAJVERS found", fields.get("MAJVERS", "").startswith("5"))
    check("SUBREV found", fields.get("SUBREV", "").startswith("3-PS"))
    check("TAVERS found", fields.get("TAVERS", "").startswith("4.3.0"))
    check("no config -> found false", svox_config(b"no stamp")["found"] is False)

    print("language table")
    words = [ord(c) for name in ("US", "JP", "SP", "BE")
             for c in name] + [0, 0] * 4
    # table is name,zero-word repeated; rebuild precisely
    raw = bytearray()
    for name in ("US", "JP", "SP", "BE"):
        raw += struct.pack("<HH", ord(name[0]), ord(name[1]))
        raw += struct.pack("<I", 0)
    rows = decode_langs(bytes(raw), 0x1000, 4)
    check("names decode", [r["name"] for r in rows] == ["US", "JP", "SP", "BE"])
    check("VA increments by 8", [r["va"] for r in rows] ==
          [0x1000, 0x1008, 0x1010, 0x1018])

    print(f"selftest: {len(failures)} failure(s)")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    q = sub.add_parser("describe", help="print the fields of one archive file")
    q.add_argument("file", type=Path)
    q = sub.add_parser("compare", help="compare the same kind from two years")
    q.add_argument("a", type=Path)
    q.add_argument("b", type=Path)
    q = sub.add_parser("langs", help="decode a UTF-16LE language table from a dump")
    q.add_argument("file", type=Path)
    q.add_argument("--va", type=lambda x: int(x, 0), required=True)
    q.add_argument("--count", type=int, required=True)
    q = sub.add_parser("slice", help="print a hex slice of a dump at --va")
    q.add_argument("file", type=Path)
    q.add_argument("va", type=lambda x: int(x, 0))
    q.add_argument("length", type=lambda x: int(x, 0))
    p.add_argument("--selftest", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return 0 if selftest() == 0 else 2
    if args.cmd is None:
        build_parser().print_help()
        return 2
    try:
        if args.cmd == "describe":
            print(format_archive(describe_archive(args.file)))
            return 0
        if args.cmd == "compare":
            text, different = compare_archives(args.a, args.b)
            print(text)
            return 1 if different else 0
        if args.cmd == "langs":
            data = args.file.read_bytes()
            # The dump is a module/RVA image; --va indexes into it directly.
            table = data[args.va : args.va + 8 * args.count]
            if len(table) < 8 * args.count:
                raise ValueError(f"table at 0x{args.va:x} truncated: "
                                 f"{len(table)} bytes for {args.count} names")
            print(format_langs(decode_langs(table, args.va, args.count)))
            return 0
        if args.cmd == "slice":
            data = args.file.read_bytes()
            # A dump made by `cerom.py extract --module` is sliced so that
            # byte 0 is the module's RVA 0; --va is the RVA.
            blob = data[args.va : args.va + args.length]
            print(f"slice: {args.file} [0x{args.va:x}:0x{args.va + len(blob):x}] "
                  f"({len(blob)} bytes)")
            print(blob.hex(" "))
            return 0
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
