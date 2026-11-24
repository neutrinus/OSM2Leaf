#!/usr/bin/env python3
"""Offline inventory of every sound source of the ZE0 navigation unit.

This is a *printing* tool: every number quoted in EXP-2026-11-24-M4.60 comes
from one of its commands.  It never writes to the repository and never commits
vendor bytes.  Stdlib only.

Subcommands:

  speech DIR [DIR ...]   walk ``SPEECH/<lang>/{GID,TTS,VR}`` trees, parse each
                         archive with ``speech_years.parse_archive`` and print
                         size / serial / entry count / RIFF-WAVE hits.
  gid FILE               dump the GID payload header and report whether a
                         standard RIFF/WAVE sample can be extracted.
  romscan IMG            count RIFF / WAVE / 'fmt ' / ADPCM byte signatures in
                         the uncompressed executable sections of ROM A.
  modules IMG            print sizes and named imports of the audio driver
                         modules (BeepDrv / DspDrv / MuteDrv) and Audio.exe.

Usage::

    python3 tools/sounds_inventory.py speech /path/to/SPEECH
    python3 tools/sounds_inventory.py gid SSP00000.GID
    python3 tools/sounds_inventory.py romscan archive/head256.img
    python3 tools/sounds_inventory.py modules archive/head256.img
    python3 tools/sounds_inventory.py --selftest

Exit codes: 0 = success, 2 = usage/IO/parse error.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

import cerom
import speech_years

SIGNATURES = (b"RIFF", b"WAVE", b"fmt ", b"ADPCM", b"ima4")
AUDIO_MODULES_A = ("Speech.exe", "Audio.exe", "SpeechCC.dll", "wavessi1.dll",
                   "wavessi2.dll", "waveapi.dll")
AUDIO_MODULES_B = ("BeepDrv.dll", "DspDrv.dll", "MuteDrv.dll", "Audio.exe",
                   "AudioMiconUpdate.exe", "AudioUpdateCC.dll", "wavessi1.dll")
NAMED_IMPORTS = ("CApi_GetSoundEffect", "CApi_GetCustomVoiceNo",
                 "CApi_SetCustomVoiceNo", "GuidanceVoiceAtt", "SCI1:", "CEN1:")


def strings_report(image: Path, image_start: int, needles: list[str]) -> str:
    """Find literal ASCII needles in uncompressed sections of one build."""
    data = image.read_bytes()
    rom = cerom.CERom(data, image_start)
    lines = []
    for needle in needles:
        hits = []
        for mod in rom.modules():
            try:
                secs = list(rom.o32(mod))
            except (struct.error, ValueError):
                continue
            for sec in secs:
                if sec["flags"] & 0x2000 or not sec["psize"]:
                    continue
                off = rom._romptr2file(sec["dataptr"])
                if off is None or off + sec["psize"] > len(data):
                    continue
                blob = data[off:off + sec["psize"]]
                pos = 0
                while True:
                    i = blob.find(needle.encode("ascii"), pos)
                    if i < 0:
                        break
                    hits.append(f"{mod['name']}(rva=0x{sec['rva'] + i:x})")
                    pos = i + 1
        lines.append(f"{needle!r}: {len(hits)} hit(s) " +
                     " ".join(hits[:8]))
    return "\n".join(lines)


def count_signatures(data: bytes) -> dict[str, int]:
    """Count non-overlapping occurrences of each audio signature."""
    result: dict[str, int] = {}
    for sig in SIGNATURES:
        result[sig.decode("latin-1")] = data.count(sig)
    return result


def speech_trees(roots: list[Path]) -> list[dict]:
    """Parse every GID/TTS/AGM archive below each SPEECH/ root."""
    rows = []
    for root in roots:
        if not root.is_dir():
            raise ValueError(f"not a directory: {root}")
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix not in (".gid", ".tts", ".agm"):
                continue
            data = path.read_bytes()
            info = speech_years.parse_archive(data)
            kind = {".gid": "GID", ".tts": "TTS", ".agm": "AGM"}[suffix]
            lang = path.parent.parent.name
            rows.append({
                "root": str(root), "lang": lang, "kind": kind,
                "name": path.name, "size": len(data),
                "serial": info["serial"], "entries": info["count"],
                "signatures": count_signatures(data),
                "first_entry": (info["entries"][0]["name"]
                                if info["entries"] else ""),
            })
    return rows


def format_speech(rows: list[dict]) -> str:
    lines = ["kind lang file size serial entries RIFF/WAVE/fmt/ADPCM/ima4 first-entry"]
    for r in rows:
        s = r["signatures"]
        sig = "/".join(str(s[k]) for k in
                       ("RIFF", "WAVE", "fmt ", "ADPCM", "ima4"))
        lines.append(f"{r['kind']:3s} {r['lang']:2s} {r['name']:16s} "
                     f"{r['size']:9d} {r['serial']} {r['entries']:2d} "
                     f"{sig:15s} {r['first_entry']}")
    lines.append(f"files: {len(rows)}")
    return "\n".join(lines)


def gid_probe(path: Path) -> str:
    """Report the GID payload header and whether a RIFF/WAVE sample exists."""
    data = path.read_bytes()
    info = speech_years.parse_archive(data)
    if not info["entries"]:
        raise ValueError("GID has no entries")
    entry = info["entries"][0]
    payload = data[entry["offset"]:entry["offset"] + entry["size"]]
    words = struct.unpack_from("<6I", payload, 0) if len(payload) >= 24 else ()
    sigs = count_signatures(payload)
    lines = [
        f"file: {path}",
        f"size: {len(data)} serial: {info['serial']} count: {info['count']}",
        f"entry[0]: {entry['name']} offset=0x{entry['offset']:x} "
        f"size={entry['size']}",
        "payload head u32[6]: " + " ".join(f"0x{w:x}" for w in words),
        "payload signatures: " + " ".join(
            f"{k}={v}" for k, v in sigs.items()),
    ]
    if sigs["RIFF"] or sigs["WAVE"]:
        lines.append("decodable: possible RIFF/WAVE sample present")
    else:
        lines.append("decodable: NO — no RIFF/WAVE container in the GID "
                     "payload; indexed vendor records with an unknown codec "
                     "(no L3/L4 firmware run), so not decodable offline")
    return "\n".join(lines)


def rom_scan(image: Path, image_start: int) -> str:
    """Count audio byte signatures in uncompressed ROM-A sections."""
    data = image.read_bytes()
    rom = cerom.CERom(data, image_start)
    lines = []
    total = {sig.decode("latin-1"): 0 for sig in SIGNATURES}
    sections = 0
    bytes_scanned = 0
    for mod in rom.modules():
        try:
            secs = list(rom.o32(mod))
        except (struct.error, ValueError):
            continue
        for sec in secs:
            if sec["flags"] & 0x2000 or not sec["psize"]:
                continue
            off = rom._romptr2file(sec["dataptr"])
            if off is None or off + sec["psize"] > len(data):
                continue
            blob = data[off:off + sec["psize"]]
            counts = count_signatures(blob)
            hit = {k: v for k, v in counts.items() if v}
            if hit:
                lines.append(f"{mod['name']:28s} rva=0x{sec['rva']:08x} "
                             f"size={sec['psize']:8d} " +
                             " ".join(f"{k}={v}" for k, v in sorted(hit.items())))
            for k, v in counts.items():
                total[k] += v
            sections += 1
            bytes_scanned += sec["psize"]
    lines.append(f"sections_scanned: {sections} bytes_scanned: {bytes_scanned}")
    lines.append("TOTAL " + " ".join(
        f"{k}={v}" for k, v in sorted(total.items())))
    return "\n".join(lines)


def module_report(image: Path, image_start: int) -> str:
    """Print sizes and named imports of the audio modules of one build."""
    data = image.read_bytes()
    rom = cerom.CERom(data, image_start)
    wanted = AUDIO_MODULES_A if image_start == 0x200200 else AUDIO_MODULES_B
    lines = []
    for mod in rom.modules():
        if mod["name"] not in wanted:
            continue
        lines.append(f"module {mod['name']} index={mod['index']} size={mod['size']}")
        seen = set()
        for dll, slot, nm, ordn in rom.imports(mod):
            label = nm or f"#{ordn}"
            if any(n in label for n in NAMED_IMPORTS) and label not in seen:
                seen.add(label)
                lines.append(f"  import {dll} {label} slot=0x{slot:08x}")
    return "\n".join(lines)


def selftest() -> int:
    failures = []

    def check(label: str, ok: bool) -> None:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
        if not ok:
            failures.append(label)

    print("signature counting")
    blob = b"xRIFFyWAVEzfmt gADPCMima4RIFF"
    c = count_signatures(blob)
    check("RIFF counted twice", c["RIFF"] == 2)
    check("WAVE counted once", c["WAVE"] == 1)
    check("fmt counted once", c["fmt "] == 1)
    check("ADPCM counted once", c["ADPCM"] == 1)
    check("ima4 counted once", c["ima4"] == 1)
    check("empty has zero", all(v == 0 for v in count_signatures(b"").values()))

    print("GID probe")
    import tempfile
    arch = bytearray()
    arch += b"0000102020100524"
    arch += struct.pack("<IIII", 0x38 + 64, 0x38, 0, 1)
    arch += b"SSP00000.GID".ljust(12, b"\0")
    arch += struct.pack("<III", 0x38, 64, 64)
    arch += b"\x10\x00\x00\x00" + struct.pack("<5I", 1, 2, 3, 4, 5) + b"\x00" * 36
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "SX00000.GID"
        p.write_bytes(bytes(arch))
        text = gid_probe(p)
        check("probe parses serial", "0000102020100524" in text)
        check("probe reports no RIFF", "decodable: NO" in text)
        wav = bytearray(arch)
        wav[0x38:0x40] = b"RIFF"
        wav[0x3c:0x40] = b"WAVE"
        p.write_bytes(bytes(wav))
        text2 = gid_probe(p)
        check("probe sees injected RIFF", "possible RIFF/WAVE" in text2)

    print("speech tree walk")
    import tempfile as _tf
    with _tf.TemporaryDirectory() as td:
        root = Path(td) / "SPEECH" / "SP" / "GID"
        root.mkdir(parents=True)
        (root / "SSP00000.GID").write_bytes(bytes(arch))
        rows = speech_trees([Path(td) / "SPEECH"])
        check("one file found", len(rows) == 1)
        check("kind decoded", rows[0]["kind"] == "GID")
        check("language decoded", rows[0]["lang"] == "SP")
        check("entry count decoded", rows[0]["entries"] == 1)

    print("string census")
    import tempfile as _st
    with _st.TemporaryDirectory() as td:
        img = Path(td) / "head.img"
        img.write_bytes(b"\x00" * 0x40)
        try:
            strings_report(img, 0x200200, ["RIFF"])
            check("non-ROM image rejected", False)
        except (ValueError, struct.error):
            check("non-ROM image rejected", True)

    print(f"selftest: {len(failures)} failure(s)")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    q = sub.add_parser("speech", help="parse all GID/TTS/AGM archives below SPEECH roots")
    q.add_argument("roots", nargs="+", type=Path)
    q = sub.add_parser("gid", help="probe a GID payload for a decodable sample")
    q.add_argument("file", type=Path)
    q = sub.add_parser("romscan", help="count audio signatures in ROM-A sections")
    q.add_argument("image", type=Path)
    q.add_argument("--image-start", type=lambda x: int(x, 0), default=0x200200)
    q = sub.add_parser("modules", help="print audio driver module sizes and imports")
    q.add_argument("image", type=Path)
    q.add_argument("--image-start", type=lambda x: int(x, 0), default=0x3e00200)
    q = sub.add_parser("strings", help="find audio literal strings in a build")
    q.add_argument("image", type=Path)
    q.add_argument("needles", nargs="+")
    q.add_argument("--image-start", type=lambda x: int(x, 0), default=0x200200)
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
        if args.cmd == "speech":
            print(format_speech(speech_trees(args.roots)))
        elif args.cmd == "gid":
            print(gid_probe(args.file))
        elif args.cmd == "romscan":
            print(rom_scan(args.image, args.image_start))
        elif args.cmd == "modules":
            print(module_report(args.image, args.image_start))
        elif args.cmd == "strings":
            print(strings_report(args.image, args.image_start, args.needles))
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
