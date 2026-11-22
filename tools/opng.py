#!/usr/bin/env python3
"""OPNG opening-image container: inspect, lossless PNG carrier, round-trip.

``OPNG/MKR_OPNG/NISSAN/OIXXEVNI.001`` (US: ``OIXXNVNI.001``) is the animation
the launcher loads before ``Navi.exe`` (M8.C1b / L4).  It is a ``BASS``
container, *not* a PNG: a small global header followed by 35 frames.  Each
frame repeats an 800x480 canvas descriptor, a payload length and a duration;
the durations of EU2011/US2011 sum to exactly 5000 ms.

The frame payload grammar is NOT decoded.  Under every plausible raw-pixel
view (RGB565 LE/BE, RGBA/BGRA, 8-bit grayscale, 1/4-bpp) the payload is noise
(EXP-2026-11-22-M4.91-opening-picture).  Consequently ``decode`` writes a PNG
that is a *lossless carrier*: a byte-map visualization plus a compressed
``zTXt`` chunk holding the exact original file bytes.  ``encode`` reads that
chunk back, so ``decode -> encode`` is byte-identical on any input.  This is a
container round trip (L2), not a claim that the pixels were understood.

No vendor byte is embedded in this source; all samples are read at run time.

Usage::

    python3 tools/opng.py info FILE
    python3 tools/opng.py decode FILE -o PNG
    python3 tools/opng.py encode PNG -o FILE
    python3 tools/opng.py --selftest
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import math
import struct
import sys
import zlib
from collections import Counter
from pathlib import Path

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
DESCRIPTOR = bytes.fromhex("2003e001")  # u16 800, u16 480 (little endian)
HEADER_LEN = 0x50       # bytes before the first 16-byte frame header
FRAME_HDR_LEN = 16      # prefix:u32 w:u16 h:u16 payload_len:u32 duration_ms:u32
CARRIER_KEY = b"opng-container-v1"
CANVAS_W = 800
CANVAS_H = 480


# --------------------------------------------------------------------------
# PNG primitives (stdlib only)
# --------------------------------------------------------------------------

def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data +
            struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))


def _png_write_gray(path: str, w: int, h: int, rows: list[bytes],
                    ztxt: tuple[bytes, bytes]) -> None:
    """Write an 8-bit grayscale PNG with one uncompressed zTXt payload."""
    key, value = ztxt
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)
    raw = b"".join(b"\x00" + row for row in rows)
    out = bytearray(PNG_MAGIC)
    out += _chunk(b"IHDR", ihdr)
    out += _chunk(b"zTXt", key + b"\x00\x00" + zlib.compress(value, 6))
    out += _chunk(b"IDAT", zlib.compress(raw, 6))
    out += _chunk(b"IEND", b"")
    Path(path).write_bytes(out)


def _png_read_ztxt(data: bytes, key: bytes) -> bytes:
    if not data.startswith(PNG_MAGIC):
        raise ValueError("not a PNG (bad signature)")
    pos = len(PNG_MAGIC)
    found = None
    while pos + 12 <= len(data):
        length = struct.unpack_from(">I", data, pos)[0]
        tag = data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        if pos + 12 + length > len(data):
            raise ValueError("truncated PNG chunk %r" % tag)
        if tag == b"zTXt":
            k, sep, rest = payload.partition(b"\x00")
            if k == key:
                if not sep or len(rest) < 1:
                    raise ValueError("malformed zTXt payload")
                found = zlib.decompress(rest[1:])
        pos += 12 + length
        if tag == b"IEND":
            break
    if found is None:
        raise ValueError("PNG has no %r zTXt carrier" % key)
    return found


# --------------------------------------------------------------------------
# Container parser
# --------------------------------------------------------------------------

def parse(data: bytes) -> dict:
    """Parse the BASS/OPNG container.  Raises ValueError on malformed input."""
    if len(data) < HEADER_LEN:
        raise ValueError("file shorter than %d bytes" % HEADER_LEN)
    magic = data[:8]
    if magic[:4] != b"BASS":
        raise ValueError("bad magic: %s" % magic.hex())
    declared = struct.unpack_from("<I", data, 0x14)[0]
    count = struct.unpack_from("<I", data, 0x40)[0]
    field44 = struct.unpack_from("<I", data, 0x44)[0]
    ident = data[0x1c:0x40].split(b"\x00", 1)[0].decode("ascii", "replace")

    frames = []
    pos = HEADER_LEN
    for idx in range(count):
        if pos + FRAME_HDR_LEN > len(data):
            raise ValueError("frame %d header past EOF" % idx)
        prefix = struct.unpack_from("<I", data, pos)[0]
        descriptor = data[pos + 4:pos + 8]
        if descriptor != DESCRIPTOR:
            raise ValueError("frame %d bad descriptor at 0x%x: %s" %
                             (idx, pos + 4, descriptor.hex()))
        w, h = struct.unpack_from("<HH", data, pos + 4)
        n, duration = struct.unpack_from("<II", data, pos + 8)
        payload_off = pos + FRAME_HDR_LEN
        if payload_off + n > len(data):
            raise ValueError("frame %d payload past EOF" % idx)
        frames.append({"index": idx, "header_off": pos, "prefix": prefix,
                       "width": w, "height": h, "payload_len": n,
                       "duration_ms": duration, "payload_off": payload_off})
        pos = payload_off + n

    trailer = len(data) - pos
    if not 0 <= trailer <= 4:
        raise ValueError("unexpected trailer of %d bytes at EOF" % trailer)
    return {"magic": magic, "size": len(data), "declared_size": declared,
            "identity": ident, "frame_count": count, "field_44": field44,
            "header": data[:HEADER_LEN], "frames": frames,
            "trailer": trailer,
            "duration_sum_ms": sum(f["duration_ms"] for f in frames)}


def _entropy(buf: bytes) -> float:
    if not buf:
        return 0.0
    counts = Counter(buf)
    n = len(buf)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def info(data: bytes, path: str) -> str:
    p = parse(data)
    sha = hashlib.sha256(data).hexdigest()
    payload = bytearray()
    for f in p["frames"]:
        payload += data[f["payload_off"]:f["payload_off"] + f["payload_len"]]
    out = []
    out.append("file: %s" % path)
    out.append("size: %d (0x%x)" % (len(data), len(data)))
    out.append("sha256: %s" % sha)
    out.append("magic: %s" % p["magic"].hex())
    out.append("declared_size@0x14: %d" % p["declared_size"])
    out.append("identity@0x1c: %r" % p["identity"])
    out.append("frame_count@0x40: %d" % p["frame_count"])
    out.append("field@0x44: %d" % p["field_44"])
    out.append("descriptor_count: %d" % sum(
        1 for i in range(len(data) - 3) if data[i:i + 4] == DESCRIPTOR))
    out.append("duration_sum_ms: %d" % p["duration_sum_ms"])
    out.append("eof_trailer_bytes: %d" % p["trailer"])
    out.append("payload_bytes: %d" % len(payload))
    out.append("payload_entropy_bits_per_byte: %.4f" % _entropy(payload))
    c16 = Counter(struct.unpack("<%dH" % (len(payload) // 2),
                                payload[:len(payload) // 2 * 2]))
    out.append("top_payload_u16: %s" % ", ".join(
        "0x%04x=%d" % (v, n) for v, n in c16.most_common(6)))
    out.append("frames (index header_off prefix w h payload_len duration_ms):")
    for f in p["frames"]:
        out.append("  %2d 0x%06x 0x%08x %d %d %7d %5d" %
                   (f["index"], f["header_off"], f["prefix"], f["width"],
                    f["height"], f["payload_len"], f["duration_ms"]))
    return "\n".join(out)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_info(args):
    data = Path(args.file).read_bytes()
    print(info(data, args.file))
    return 0


def cmd_decode(args):
    data = Path(args.file).read_bytes()
    p = parse(data)  # fail early on malformed containers
    carrier = {
        "format": "opng-container-v1",
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "frames": p["frames"],
        "bytes_b64": base64.b64encode(data).decode("ascii"),
    }
    raw = json.dumps(carrier, separators=(",", ":")).encode("utf-8")
    # Visualization: 800x480 byte map of the first frame payload (documented
    # as noise; the real pixel grammar is undecoded).
    first = p["frames"][0]
    region = data[first["payload_off"]:first["payload_off"] + CANVAS_W * CANVAS_H]
    region = region.ljust(CANVAS_W * CANVAS_H, b"\x00")
    rows = [region[y * CANVAS_W:(y + 1) * CANVAS_W]
            for y in range(CANVAS_H)]
    _png_write_gray(args.output, CANVAS_W, CANVAS_H, rows,
                    (CARRIER_KEY, raw))
    print("wrote %s (%d bytes carrier, %d frames)" %
          (args.output, len(raw), len(p["frames"])))
    return 0


def cmd_encode(args):
    png = Path(args.input).read_bytes()
    raw = _png_read_ztxt(png, CARRIER_KEY)
    carrier = json.loads(raw.decode("utf-8"))
    if carrier.get("format") != "opng-container-v1":
        raise ValueError("unknown carrier format")
    data = base64.b64decode(carrier["bytes_b64"], validate=True)
    p = parse(data)
    if len(data) != carrier["size"] or \
            hashlib.sha256(data).hexdigest() != carrier["sha256"]:
        raise ValueError("carrier payload failed its own hash/size check")
    Path(args.output).write_bytes(data)
    print("wrote %s (%d bytes, %d frames)" %
          (args.output, len(data), len(p["frames"])))
    return 0


# --------------------------------------------------------------------------
# Self-test (synthetic container; no vendor data)
# --------------------------------------------------------------------------

def _synthetic(frames: list[tuple[int, int]], ident: bytes = b"TEST.ID.001") -> bytes:
    d = bytearray(HEADER_LEN)
    d[0:4] = b"BASS"
    d[4:8] = bytes.fromhex("573743d8")
    d[0x14:0x18] = struct.pack("<I", 0)  # patched at the end
    d[0x1c:0x1c + len(ident)] = ident
    d[0x40:0x44] = struct.pack("<I", len(frames))
    d[0x44:0x48] = struct.pack("<I", 2)
    for i, (n, dur) in enumerate(frames):
        payload = bytes(((i * 37 + j * 11) & 0xff) for j in range(n))
        d += struct.pack("<IHHII", i, 800, 480, n, dur) + payload
    d += b"\x00" * 2
    d[0x14:0x18] = struct.pack("<I", len(d))
    return bytes(d)


def selftest() -> int:
    ok = fail = 0

    def check(name, cond):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            print("FAIL", name)

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # Positive: 3-frame synthetic container round-trips byte-identically.
        src = _synthetic([(64, 400), (128, 70), (96, 2290)])
        f = td / "a.001"
        f.write_bytes(src)
        p = parse(src)
        check("frame count", p["frame_count"] == 3)
        check("duration sum", p["duration_sum_ms"] == 2760)
        check("declared size", p["declared_size"] == len(src))
        png, back = td / "a.png", td / "b.001"
        cmd_decode(argparse.Namespace(file=str(f), output=str(png)))
        cmd_encode(argparse.Namespace(input=str(png), output=str(back)))
        check("round trip byte-identical", back.read_bytes() == src)

        # Second positive: different frame sizes and identity.
        src2 = _synthetic([(7, 1), (1024, 5000)], b"OTHER.ID.002")
        f2 = td / "c.001"
        f2.write_bytes(src2)
        png2, back2 = td / "c.png", td / "d.001"
        cmd_decode(argparse.Namespace(file=str(f2), output=str(png2)))
        cmd_encode(argparse.Namespace(input=str(png2), output=str(back2)))
        check("round trip 2 byte-identical", back2.read_bytes() == src2)

        # Negative controls: each must be rejected by parse.
        bad_magic = bytearray(src); bad_magic[0] = ord("X")
        try:
            parse(bytes(bad_magic)); check("bad magic rejected", False)
        except ValueError:
            check("bad magic rejected", True)
        bad_desc = bytearray(src); bad_desc[0x54] = 0x21
        try:
            parse(bytes(bad_desc)); check("bad descriptor rejected", False)
        except ValueError:
            check("bad descriptor rejected", True)
        truncated = src[:-8]  # more than the <= 4 allowed EOF trailer bytes
        try:
            parse(truncated); check("truncated rejected", False)
        except ValueError:
            check("truncated rejected", True)
        bad_count = bytearray(src)
        bad_count[0x40:0x44] = struct.pack("<I", 4)
        try:
            parse(bytes(bad_count)); check("bad frame count rejected", False)
        except ValueError:
            check("bad frame count rejected", True)

        # Tampered carrier must fail its own hash check.
        blob = bytearray(png.read_bytes())
        i = blob.find(CARRIER_KEY)
        blob[i + len(CARRIER_KEY) + 2] ^= 1
        tampered = td / "tampered.png"
        tampered.write_bytes(bytes(blob))
        try:
            cmd_encode(argparse.Namespace(input=str(tampered),
                                          output=str(td / "e.001")))
            check("tampered carrier rejected", False)
        except (ValueError, zlib.error, binascii.Error):
            check("tampered carrier rejected", True)

    print("opng selftest: %d ok, %d fail" % (ok, fail))
    return 1 if fail else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="OPNG opening-image container (M4.91)")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    pinfo = sub.add_parser("info", help="print the parsed container structure")
    pinfo.add_argument("file")
    pdec = sub.add_parser("decode", help="write PNG carrier + byte-map view")
    pdec.add_argument("file")
    pdec.add_argument("-o", "--output", required=True)
    penc = sub.add_parser("encode", help="rebuild the OPNG from a PNG carrier")
    penc.add_argument("input")
    penc.add_argument("-o", "--output", required=True)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "info":
        return cmd_info(args)
    if args.cmd == "decode":
        return cmd_decode(args)
    if args.cmd == "encode":
        return cmd_encode(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
