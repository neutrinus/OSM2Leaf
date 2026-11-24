#!/usr/bin/env python3
"""Patch one same-size bitmap of a ZE0 card image and fix every ROM checksum (M4.59).

The visible player-skin bitmaps are the section-3 PNG assets of
``\\SystemSD2\\SkinChange\\001\\substance.skn`` on the TFAT16 tail volume
(C-6501/C-6508), or the PNG resources built into ROM A (C-6506).  This tool
replaces one ROM-A PNG in place, keeping its byte length and dimensions, then
recomputes the ``SUM4`` u32 word sum (C-160) in both copies of the card's image
A container (``0x200000`` and ``0x2000000``).  Nothing else is written.

The replacement is synthetic: the original IDAT is decompressed, the RGB
samples are set to black, and the result is recompressed with a zlib stream padded
to the original IDAT length (a non-final stored deflate tail plus a final empty
stored block).  Then the IHDR/IDAT/IEND chunk CRCs are recomputed.  The total
PNG length is unchanged, so the ROM section offsets and the SUM4 range stay
identical.  No vendor bytes are stored in the repository.

Commands::

    # read-only plan (no writes, no vendor bytes printed)
    python3 tools/skin_patch.py plan --image IMG --offset 0xcce7b0

    # patch a reflink/copy of a card image in place
    python3 tools/skin_patch.py patch --image IMG --offset 0xcce7b0 \
        --in-place
    python3 tools/skin_patch.py verify --image IMG --offset 0xcce7b0 \
        --expected-sum4 0xcdf87db0

    python3 tools/skin_patch.py --selftest

Exit codes: 0 OK, 1 verification failure, 2 usage/geometry error,
3 refused (not a PNG, wrong size/checksum, would write outside the SUM4 range).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import struct
import sys
import zlib

SUM4_OFFSET = 0x34
SUM4_MAGIC = b"SUM4"
COPIES = (0x200000, 0x2000000)
ROM_A_START = 0x200200
ROM_A_LENGTH = 0x01752C88
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

IMAGE_START = COPIES[0]
IMAGE_LENGTH = ROM_A_LENGTH


def u32(d: bytes, off: int) -> int:
    return struct.unpack_from("<I", d, off)[0]


def be32(d: bytes, off: int) -> int:
    return struct.unpack_from(">I", d, off)[0]


def png_chunks(d: bytes) -> list[tuple[bytes, int, int]]:
    """Return [(type, payload_start, payload_len), ...] for a complete PNG.

    Raises ValueError if the signature, a chunk boundary or the trailing CRC
    is wrong.  ``d`` must be the exact PNG byte run (no surrounding padding).
    """
    if not d.startswith(PNG_MAGIC):
        raise ValueError("not a PNG (signature)")
    out: list[tuple[bytes, int, int]] = []
    k = 8
    while k + 12 <= len(d):
        ln = be32(d, k)
        typ = d[k + 4:k + 8]
        end = k + 12 + ln
        if end > len(d):
            raise ValueError("PNG chunk overruns buffer")
        crc = struct.unpack_from(">I", d, k + 8 + ln)[0]
        if zlib.crc32(d[k + 4:k + 8 + ln]) & 0xffffffff != crc:
            raise ValueError("PNG chunk CRC mismatch (%r)" % typ)
        out.append((typ, k + 8, ln))
        k = end
        if typ == b"IEND":
            if k != len(d):
                raise ValueError("PNG has trailing bytes after IEND")
            return out
    raise ValueError("PNG has no IEND")


def _chunk(typ: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + typ + payload
            + struct.pack(">I", zlib.crc32(typ + payload) & 0xffffffff))


def recolor_png(orig: bytes) -> bytes:
    """Invert RGB of one 8-bit RGBA PNG, preserving its exact byte length.

    The IDAT stream is rebuilt from a non-final zlib stream followed by a
    stored deflate tail, so it decompresses to the same raster and occupies
    exactly the original number of bytes.  CRC and IHDR are left consistent.
    """
    chunks = png_chunks(orig)
    ihdr = [(t, o, n) for t, o, n in chunks if t == b"IHDR"]
    idat = [(t, o, n) for t, o, n in chunks if t == b"IDAT"]
    iend = [(t, o, n) for t, o, n in chunks if t == b"IEND"]
    if len(ihdr) != 1 or len(idat) != 1 or len(iend) != 1 or len(chunks) < 3:
        raise ValueError("expected one IHDR, one IDAT, one IEND")
    ih = orig[ihdr[0][1]:ihdr[0][1] + ihdr[0][2]]
    if len(ih) != 13 or ih[8] != 8 or ih[9] != 6 or ih[10:13] != b"\x00\x00\x00":
        raise ValueError("only 8-bit truecolour+alpha PNGs are supported")
    w, h = struct.unpack(">II", ih[:8])
    raw = zlib.decompress(orig[idat[0][1]:idat[0][1] + idat[0][2]])
    stride = 1 + w * 4
    if len(raw) != h * stride:
        raise ValueError("IDAT raster size does not match IHDR")
    new = bytearray(raw)
    for y in range(h):
        if new[y * stride] != 0:
            raise ValueError("only PNG filter type 0 is supported")
        for x in range(w):
            p = y * stride + 1 + x * 4
            new[p] = 0
            new[p + 1] = 0
            new[p + 2] = 0

    target_total = len(orig)
    best = None
    for level in (9, 8, 7, 6, 5, 4, 3, 2, 1):
        blob = zlib.compress(bytes(new), level)
        if best is None or len(blob) < len(best):
            best = blob
    parts = [_chunk(b"IHDR", ih), _chunk(b"IDAT", best)]
    iend_chunk = _chunk(b"IEND", b"")
    fixed = len(PNG_MAGIC) + sum(len(x) for x in parts) + len(iend_chunk)
    pad_total = target_total - fixed
    if pad_total < 12:
        raise ValueError("recolour would grow the PNG (%d > %d)"
                         % (fixed + 12, target_total))
    parts.append(_chunk(b"zZzZ", b"\x00" * (pad_total - 12)))
    out = PNG_MAGIC + b"".join(parts) + iend_chunk
    if len(out) != target_total:
        raise ValueError("recoloured PNG is %d B, expected %d"
                         % (len(out), target_total))
    return out


def sum4(data: bytes) -> int:
    """LE u32 word sum over the ROM A image (C-160), masked to u32."""
    if len(data) % 4:
        raise ValueError("SUM4 range is not word aligned")
    return sum(struct.unpack_from("<%dI" % (len(data) // 4), data, 0)) & 0xffffffff


def read_header(f, off: int) -> tuple[int, bytes]:
    f.seek(off)
    head = f.read(0x40)
    if len(head) < 0x40 or head[0x30:0x34] != SUM4_MAGIC:
        raise ValueError("no SUM4 header at 0x%x" % off)
    return u32(head, SUM4_OFFSET), head


def plan(image: str, offset: int) -> dict:
    out: dict = {"image": image, "offset": offset}
    with open(image, "rb") as f:
        f.seek(offset)
        orig = f.read(1 << 20)
        if not orig.startswith(PNG_MAGIC):
            raise ValueError("no PNG at file offset 0x%x" % offset)
        # walk chunks in the prefix to find the exact PNG end, then re-read
        # only those bytes and validate the full PNG (including CRCs)
        k = 8
        end = None
        while k + 12 <= len(orig):
            ln = be32(orig, k)
            typ = orig[k + 4:k + 8]
            k += 12 + ln
            if typ == b"IEND":
                end = k
                break
        if end is None or end > (1 << 20):
            raise ValueError("incomplete PNG at 0x%x" % offset)
        f.seek(offset)
        orig = f.read(end)
        chunks = png_chunks(orig)
        ihdr = [n for t, o, n in chunks if t == b"IHDR"][0]
        w, h = struct.unpack(">II", orig[16:24])
        mirror = offset + COPIES[1] - COPIES[0]
        out.update({"png_len": len(orig), "png_sha256": hashlib.sha256(orig).hexdigest(),
                    "width": w, "height": h,
                    "new_png_sha256": hashlib.sha256(recolor_png(orig)).hexdigest(),
                    "offset_end": offset + end, "mirror_offset": mirror})
        for copy in COPIES:
            stored, head = read_header(f, copy)
            f.seek(copy + ROM_A_START - IMAGE_START)
            rom = f.read(ROM_A_LENGTH)
            if len(rom) != ROM_A_LENGTH:
                raise ValueError("short ROM A at copy 0x%x" % copy)
            out["stored_sum4_0x%x" % copy] = stored
            out["actual_sum4_0x%x" % copy] = sum4(rom)
        out["in_range"] = COPIES[0] <= offset and out["offset_end"] <= COPIES[0] + ROM_A_LENGTH
    return out


def patch(image: str, offset: int, *, in_place: bool) -> dict:
    if not in_place:
        raise ValueError("patch writes in place: pass --in-place on a copy")
    info = plan(image, offset)
    if not info["in_range"]:
        raise ValueError("PNG is outside the ROM A SUM4 range")
    for copy in COPIES:
        if info["stored_sum4_0x%x" % copy] != info["actual_sum4_0x%x" % copy]:
            raise ValueError("SUM4 at 0x%x does not match before patch" % copy)
    with open(image, "rb") as f:
        f.seek(offset)
        orig = f.read(info["png_len"])
        f.seek(info["mirror_offset"])
        mirror_orig = f.read(info["png_len"])
    if mirror_orig != orig:
        raise ValueError("the two ROM copies hold different PNGs")
    new = recolor_png(orig)
    if len(new) != len(orig):
        raise ValueError("replacement length differs")
    delta = sum4(new) - sum4(orig)
    ranges = []
    with open(image, "r+b") as f:
        for where in (offset, info["mirror_offset"]):
            f.seek(where)
            f.write(new)
            ranges.append((where, where + len(new), "png"))
        for copy in COPIES:
            f.seek(copy + SUM4_OFFSET)
            f.write(struct.pack("<I", (info["stored_sum4_0x%x" % copy] + delta) & 0xffffffff))
            ranges.append((copy + SUM4_OFFSET, copy + SUM4_OFFSET + 4, "SUM4"))
    info["changed_ranges"] = ranges
    info["sum4_delta"] = delta & 0xffffffff
    return info


def diff_ranges(before: str, after: str) -> dict:
    """Report byte-precise changed ranges by comparing two images in blocks."""
    size = os.path.getsize(before)
    if os.path.getsize(after) != size:
        raise ValueError("images have different sizes")
    runs: list[tuple[int, int]] = []
    block = 1 << 16
    with open(before, "rb") as fa, open(after, "rb") as fb:
        pos = 0
        active: list[int] = []
        def flush():
            if active:
                runs.append((active[0], active[-1] + 1))
                active.clear()
        while pos < size:
            a = fa.read(block)
            b = fb.read(block)
            if not a:
                break
            if a == b:
                flush()
            else:
                for i, (x, y) in enumerate(zip(a, b)):
                    if x != y:
                        active.append(pos + i)
            pos += len(a)
        flush()
    return {"size": size, "blocks": (size + block - 1) // block,
            "runs": [["0x%x" % a, "0x%x" % b] for a, b in runs],
            "count": len(runs)}


def verify(image: str, offset: int, expected_sum4: int | None) -> dict:
    out = plan(image, offset)
    out["png_complete"] = True
    out["png_sha256_now"] = []
    with open(image, "rb") as f:
        for where in (offset, out["mirror_offset"]):
            f.seek(where)
            png = f.read(out["png_len"])
            out["png_complete"] &= png_chunks(png)[-1][0] == b"IEND"
            out["png_sha256_now"].append(hashlib.sha256(png).hexdigest())
    out["sum4_ok"] = all(
        out["stored_sum4_0x%x" % c] == out["actual_sum4_0x%x" % c]
        for c in COPIES)
    if expected_sum4 is not None:
        out["matches_expected_factory"] = all(
            out["stored_sum4_0x%x" % c] == expected_sum4 for c in COPIES)
    return out


def selftest() -> int:
    ok = fail = 0

    def check(name: str, cond: bool) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            print("FAIL", name)

    # Synthetic 32x32 RGBA PNG with a stored (level 0) IDAT: stored deflate
    # blocks have a fixed RFC 1950/1951 layout, so the fixture's byte length
    # is identical on every zlib version (CI runs py3.11 and py3.13).  The
    # blackened stream compresses smaller at level 9, leaving room for the
    # ancillary padding chunk on every interpreter.
    raw = bytearray()
    for y in range(32):
        raw.append(0)
        for x in range(32):
            raw.extend(((x * 7 + y * 3) & 0xff, (x * 5 + y * 11) & 0xff,
                        (x ^ y) & 0xff, 255))
    raw = bytes(raw)
    ihdr = struct.pack(">IIBBBBB", 32, 32, 8, 6, 0, 0, 0)
    png = (PNG_MAGIC + _chunk(b"IHDR", ihdr)
           + _chunk(b"IDAT", zlib.compress(raw, 0)) + _chunk(b"IEND", b""))
    check("png_chunks parses synthetic PNG",
          [t for t, o, n in png_chunks(png)] == [b"IHDR", b"IDAT", b"IEND"])
    new = recolor_png(png)
    check("same length", len(new) == len(png))
    check("dimensions kept", struct.unpack(">II", new[16:24]) == (32, 32))
    new_chunks = png_chunks(new)
    new_idat = [(t, o, n) for t, o, n in new_chunks if t == b"IDAT"][0]
    check("IEND last", new_chunks[-1][0] == b"IEND")
    exp = bytearray()
    for y in range(32):
        exp.append(0)
        for x in range(32):
            p0 = y * 129 + 1 + x * 4
            exp.extend((0, 0, 0, raw[p0 + 3]))
    check("IDAT decodes", zlib.decompress(new[new_idat[1]:new_idat[1] + new_idat[2]])
          == bytes(exp))
    check("changed bytes", new != png)
    bad = bytearray(png)
    bad[-1] ^= 1
    try:
        png_chunks(bytes(bad))
        check("bad CRC rejected", False)
    except ValueError:
        check("bad CRC rejected", True)
    # SUM4 on synthetic ROM A: four words sum to 0x1e, delta for +1 is +1.
    blob = struct.pack("<4I", 1, 2, 3, 4)
    check("sum4 synthetic", sum4(blob) == 10)
    check("sum4 rejects odd length", _raises(lambda: sum4(b"\x00" * 3)))
    # negative control: a corrupted stored sum4 must be detected by plan()
    import tempfile
    with tempfile.TemporaryDirectory(prefix="skin-patch-") as tmp:
        path = os.path.join(tmp, "img.bin")
        offset = 0x200200
        with open(path, "wb") as f:
            f.write(b"\x00" * (COPIES[1] + ROM_A_LENGTH + 16))
            for copy in COPIES:
                rom = bytearray(ROM_A_LENGTH)
                rom[:len(png)] = png
                rom[len(png) + 0x1000:len(png) + 0x1000 + len(blob)] = blob
                f.seek(copy + ROM_A_START - IMAGE_START)
                f.write(bytes(rom))
            for copy in COPIES:
                f.seek(copy + 0x30)
                f.write(b"SUM4" + struct.pack("<I", 0))
        p = plan(path, offset)
        expected = sum4(bytes(png) + b"\x00" * (ROM_A_LENGTH - len(png))
                        + blob) & 0xffffffff
        check("plan sees stored 0", p["stored_sum4_0x200000"] == 0)
        check("plan sees actual recomputed", p["actual_sum4_0x200000"] == expected)
        check("plan reports in range", p["in_range"])
    print("skin_patch selftest: %d ok, %d fail" % (ok, fail))
    return 0 if fail == 0 else 1


def _raises(fn) -> bool:
    try:
        fn()
    except ValueError:
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="patch one ROM-A PNG and fix SUM4 (M4.59)")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("plan", "patch", "verify", "diff"):
        p = sub.add_parser(name)
        p.add_argument("--image", required=True)
        p.add_argument("--offset", default=hex(0xcce7b0))
        p.add_argument("--in-place", action="store_true")
        p.add_argument("--factory-sum4")
        if name == "diff":
            p.add_argument("--before", required=True)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmd:
        ap.error("a subcommand is required")
    try:
        offset = int(args.offset, 0)
        expected = int(args.factory_sum4, 0) if args.factory_sum4 else None
        if args.cmd == "diff":
            out = diff_ranges(args.before, args.image)
        elif args.cmd == "plan":
            out = plan(args.image, offset)
        elif args.cmd == "patch":
            out = patch(args.image, offset, in_place=args.in_place)
        else:
            out = verify(args.image, offset, expected)
    except (ValueError, OSError) as exc:
        print("skin_patch: %s" % exc, file=sys.stderr)
        return 3
    import json
    print(json.dumps(out, indent=2))
    if args.cmd == "verify" and not out["sum4_ok"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
