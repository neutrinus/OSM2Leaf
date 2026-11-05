#!/usr/bin/env python3
"""Decompress the two compression families used by Windows CE ROM sections.

Stdlib only.  A CE XIP image stores some sections compressed: `o32_flags` has
`IMAGE_SCN_COMPRESSED` (0x2000), `o32_psize` is the stored length and
`o32_vsize` the unpacked length (TODO M1.2/M1.3, docs/format/cerom.md §5).
Nothing in the repo could unpack those bytes yet, and which compressor the image
uses was UNKNOWN.

**Status: SPEC CONFORMANCE IS UNVERIFIED.**  No vendor image exists in this
checkout, so neither decoder below has ever seen a real ROM section.  What is
tested is *symmetry*: the reference encoder in `--selftest` produces LZSS
streams from literals, ordinary matches, maximum-length matches and a 4 KiB
window wrap, and the decoder reproduces them byte-exactly; the LZX half is
tested at the block-header and bit-reader level with hand-built streams.  A
passing self-test says these two halves agree with the format written down here.
It does **not** say this is the format the ZE0 image uses.  The kernel's own
decompressor (`nk.exe`, M8.E1 / M9.6) is the only real confirmation.

Family 1 — ``cecompress`` / LZSS, 4 KiB window
----------------------------------------------
``method="lzss"`` (aliases ``cecompress``, ``ce-lzss``).

Window 4096 bytes, minimum match 3, maximum match 18.  The stream is a series of
groups; each group starts with one flag byte and is followed by up to eight
items, bit 0 of the flag byte first:

=============  ===============================================================
flag bit = 0   literal: one byte, appended to the output.
flag bit = 1   match: two bytes ``lo``, ``hi``.
=============  ===============================================================

For a match::

    offset = lo | ((hi & 0xF0) << 4)      # 12 bits, 0..4095
    length = (hi & 0x0F) + 3              # 4 bits, 3..18
    source = len(out) - (offset + 1)      # the stored offset is "distance - 1"

``out[source:source+length]`` is copied one byte at a time, so a match may
overlap its own output (a run).  ``source >= 0`` is required.  The last group may
be short: the decoder stops at end of input and ignores unused flag bits, so an
LZSS stream carries no length, end marker or checksum — the caller supplies the
expected size (`o32_vsize`).

This is the classic Okumura ``lzss.c`` layout with the 12+4 bit split.  Variants
that swap the nibbles or move the length into the first byte exist; this module
implements the layout above and nothing else.

Family 2 — ``lzx`` (Microsoft LZX, the ``romimage`` family), 32 KiB window
--------------------------------------------------------------------------
``method="lzx"``.

Bit reader: the stream is a sequence of 16-bit little-endian words and bits are
taken MSB-first from a word, continuing into the next word, i.e. the bit order
is ``word0[15] … word0[0] word1[15] …``.  `BitReader` keeps the unconsumed bits
in a shift register (`buf = (buf << 16) | word`) and takes the top ``n`` bits,
which yields exactly that sequence.

Stream header: 1 bit "E8 pre-processing present"; if set, a 32-bit file size
(16 bits high, then 16 bits low); then 1 reserved bit that must be 0.

Each block header is 3 bits of block type and a 24-bit uncompressed size
(16 bits, then 8 bits shifted up by 8)::

    0  invalid         error
    1  verbatim        Huffman-coded — not implemented
    2  aligned offset  Huffman-coded + aligned offsets — not implemented
    3  uncompressed    implemented (the LZX "stored" block)

A verbatim or aligned block raises
``UnsupportedFormat("UNSUPPORTED(lzx block type verbatim)")``: the decoder never
guesses at Huffman trees it does not have, and never returns partly-wrong bytes
for a block it cannot read.

An uncompressed block is: bit padding to the next 16-bit boundary, then R0, R1,
R2 (12 bits each, kept for the record, unused by stored blocks), then ``size``
bytes, each stored as one 16-bit little-endian word (only the low byte is data).
The padding rule and the word-per-byte storage are the MS LZX quirks as written
down here; both are UNVERIFIED against a real stream.  The decoder reports how
many stored high bytes were non-zero, because a stream read with the wrong bit
convention usually shows up there first.

E8 call translation is **off by default** (``e8_translation=False``): a stream
whose header declares the pre-processing raises `UnsupportedFormat` instead of
returning shifted addresses.  ``e8_translation=True`` applies
`lzx_e8_translate` (relative displacement -> absolute) to the output; that
transform is also unverified.

Auto-detection never pretends to know: `detect` returns a candidate method plus
the evidence for and against it, and `decompress(method="auto")` refuses a
"weak" candidate (an LZSS stream has no signature, so *any* byte string decodes
as LZSS unless a back-reference points before the start of the output).

Usage::

    cecompress.py detect FILE [--size N] [--json]
    cecompress.py decompress FILE -o OUT [--method m] [--size N] [--json]
                                [--window-bits 15] [--e8-translation]
    cecompress.py --selftest          # synthetic streams, no vendor data

API::

    blob = decompress(data, expected_size=None, method="auto")
    verdict = detect(data, expected_size=None)
    blob = decompress_file("section.bin", expected_size=0x5b8)
"""
import argparse
import hashlib
import json
import os
import struct
import sys

DEFAULT_MAX_OUTPUT = 64 << 20

# --- LZSS / "cecompress" -----------------------------------------------------
LZSS_WINDOW = 4096
LZSS_MIN_MATCH = 3
LZSS_MAX_MATCH = 18
LZSS_FLAG_BITS = 8

# --- LZX ---------------------------------------------------------------------
LZX_DEFAULT_WINDOW_BITS = 15          # 32 KiB
LZX_MIN_WINDOW_BITS = 15
LZX_MAX_WINDOW_BITS = 21
LZX_BLOCK_NAMES = {0: "invalid", 1: "verbatim", 2: "aligned", 3: "uncompressed"}
LZX_BLOCK_HEADER_BITS = 3 + 16 + 8    # smallest possible header, for padding

METHOD_ALIASES = {
    "auto": "auto",
    "lzss": "lzss",
    "cecompress": "lzss",
    "ce-lzss": "lzss",
    "lzx": "lzx",
}


class CeCompressError(Exception):
    """Base class for every refusal or decode failure in this module."""


class UnsupportedFormat(CeCompressError):
    """The stream is not this format, or the format is not (fully) implemented."""


class DecodeError(CeCompressError):
    """The stream claims the format but is truncated, corrupt or impossible."""


def normalise_method(method):
    """Map a user-facing method name to ``auto``/``lzss``/``lzx``."""
    key = str(method).strip().lower()
    try:
        return METHOD_ALIASES[key]
    except KeyError:
        raise UnsupportedFormat(
            "UNSUPPORTED(method %r); known: auto, lzss (cecompress), lzx" % method
        ) from None


# --------------------------------------------------------------------------
# LZSS (CE "cecompress" variant, 4 KiB window, 12-bit offset + 4-bit length)
# --------------------------------------------------------------------------


def _lzss_decode(data, expected_size=None, max_output=DEFAULT_MAX_OUTPUT):
    """Decode an LZSS stream; return ``(bytes, info)``."""
    out = bytearray()
    info = {
        "method": "lzss",
        "input_size": len(data),
        "output_size": 0,
        "groups": 0,
        "literals": 0,
        "matches": 0,
        "match_bytes": 0,
        "max_length": 0,
        "max_offset": 0,
    }
    i, n = 0, len(data)
    while i < n:
        flags = data[i]
        i += 1
        info["groups"] += 1
        for bit in range(LZSS_FLAG_BITS):
            if i >= n:
                break
            if flags & (1 << bit):
                if i + 2 > n:
                    raise DecodeError(
                        "lzss: truncated match at byte %d (need 2 bytes, %d left)"
                        % (i, n - i)
                    )
                lo, hi = data[i], data[i + 1]
                i += 2
                offset = lo | ((hi & 0xF0) << 4)
                length = (hi & 0x0F) + LZSS_MIN_MATCH
                source = len(out) - offset - 1
                if source < 0:
                    raise DecodeError(
                        "lzss: match at output %d refers %d bytes back, before the "
                        "start of the output" % (len(out), offset + 1)
                    )
                for k in range(length):
                    out.append(out[source + k])
                info["matches"] += 1
                info["match_bytes"] += length
                if length > info["max_length"]:
                    info["max_length"] = length
                if offset > info["max_offset"]:
                    info["max_offset"] = offset
            else:
                out.append(data[i])
                i += 1
                info["literals"] += 1
            if len(out) > max_output:
                raise DecodeError("lzss: output exceeds the %d-byte limit" % max_output)
    info["output_size"] = len(out)
    if expected_size is not None and len(out) != expected_size:
        raise DecodeError(
            "lzss: decoded %d bytes, expected %d" % (len(out), expected_size)
        )
    return bytes(out), info


def decompress_lzss(data, expected_size=None, max_output=DEFAULT_MAX_OUTPUT):
    """Decode the 4 KiB-window LZSS variant; return bytes."""
    return _lzss_decode(data, expected_size, max_output)[0]


def encode_lzss(data, max_match=LZSS_MAX_MATCH):
    """Reference LZSS encoder; **test-only** (used by ``--selftest``).

    Greedy longest match inside a 4096-byte window, minimum 3 bytes, at most
    ``max_match`` (18 in the real format).  It exists to prove that the decoder
    above inverts this documented encoding; it is not a ROM writer.
    """
    out = bytearray()
    n = len(data)
    table = {}
    stats = {"literals": 0, "matches": 0, "max_length": 0, "max_offset": 0}

    def register(pos):
        if pos + 3 <= n:
            table.setdefault(data[pos:pos + 3], []).append(pos)

    pos = 0
    while pos < n:
        flag_at = len(out)
        out.append(0)
        flags = 0
        for bit in range(LZSS_FLAG_BITS):
            if pos >= n:
                break
            best_len = 0
            best_dist = 0
            if pos + 3 <= n:
                limit = min(max_match, n - pos)
                for cand in reversed(table.get(data[pos:pos + 3], ())):
                    dist = pos - cand
                    if dist > LZSS_WINDOW:
                        break
                    length = 3
                    while length < limit and data[cand + length] == data[pos + length]:
                        length += 1
                    if length > best_len:
                        best_len, best_dist = length, dist
                        if length == limit:
                            break
            if best_len >= LZSS_MIN_MATCH:
                flags |= 1 << bit
                offset = best_dist - 1
                out.append(offset & 0xFF)
                out.append(((offset >> 8) << 4) | (best_len - LZSS_MIN_MATCH))
                for k in range(best_len):
                    register(pos + k)
                pos += best_len
                stats["matches"] += 1
                if best_len > stats["max_length"]:
                    stats["max_length"] = best_len
                if offset > stats["max_offset"]:
                    stats["max_offset"] = offset
            else:
                out.append(data[pos])
                register(pos)
                pos += 1
                stats["literals"] += 1
        out[flag_at] = flags
    return bytes(out), stats


# --------------------------------------------------------------------------
# LZX: bit reader, block framing, stored blocks, E8 translation
# --------------------------------------------------------------------------


class BitReader:
    """MSB-first bit reader over 16-bit little-endian words (LZX order).

    Valid bits live in the low bits of ``buf``; the next bit is the highest of
    them.  Refilling shifts the existing bits up and appends a new word below,
    so words are consumed in stream order and bits are consumed MSB-first inside
    each word.
    """

    __slots__ = ("data", "pos", "buf", "bits", "consumed")

    def __init__(self, data, pos=0):
        self.data = data
        self.pos = pos
        self.buf = 0
        self.bits = 0
        self.consumed = 0

    def read(self, count):
        if count < 0 or count > 24:
            raise ValueError("BitReader.read: count must be 0..24, not %r" % (count,))
        if count == 0:
            return 0
        while self.bits < count:
            if self.pos + 2 > len(self.data):
                raise DecodeError(
                    "lzx: bitstream truncated (%d more bits needed at byte %d of %d)"
                    % (count - self.bits, self.pos, len(self.data))
                )
            word = self.data[self.pos] | (self.data[self.pos + 1] << 8)
            self.pos += 2
            self.buf = (self.buf << 16) | word
            self.bits += 16
        self.bits -= count
        value = (self.buf >> self.bits) & ((1 << count) - 1)
        self.buf &= (1 << self.bits) - 1
        self.consumed += count
        return value

    def skip(self, count):
        """Discard ``count`` bits without materialising them."""
        if count < 0:
            raise ValueError("BitReader.skip: negative count")
        take = min(count, self.bits)
        if take:
            self.bits -= take
            self.buf &= (1 << self.bits) - 1
            self.consumed += take
            count -= take
        whole = count // 16
        if whole:
            self.pos += 2 * whole
            self.consumed += 16 * whole
            count -= 16 * whole
            if self.pos > len(self.data):
                raise DecodeError("lzx: bitstream truncated while skipping")
        if count:
            self.read(count)

    def align16(self):
        """Discard 0..15 bits up to the next 16-bit boundary; return the count."""
        pad = (-self.consumed) % 16
        if pad:
            self.skip(pad)
        return pad

    def remaining_bits(self):
        return self.bits + 8 * (len(self.data) - self.pos)

    @property
    def at_end(self):
        return self.bits == 0 and self.pos + 2 > len(self.data)


def lzx_e8_translate(data, filesize, start=0):
    """Apply the LZX E8 call post-processing (relative -> absolute).

    For every ``0xE8`` byte at absolute position ``p`` (``start + i``) whose
    signed 32-bit little-endian displacement ``d`` satisfies
    ``-p <= d < filesize - p``, the displacement becomes ``d + p``.  UNVERIFIED:
    this is the classic LZX rule, not yet checked against a real stream.
    """
    buf = bytearray(data)
    i, n = 0, len(buf)
    while i + 4 < n:
        if buf[i] == 0xE8:
            disp = int.from_bytes(buf[i + 1:i + 5], "little", signed=True)
            pos = start + i
            if -pos <= disp < filesize - pos:
                buf[i + 1:i + 5] = (disp + pos).to_bytes(4, "little")
            i += 5
        else:
            i += 1
    return bytes(buf)


def _lzx_decode(data, expected_size=None, window_bits=LZX_DEFAULT_WINDOW_BITS,
                e8_translation=False, max_output=DEFAULT_MAX_OUTPUT, strict=True):
    """Decode LZX block framing plus uncompressed blocks; return ``(bytes, info)``.

    With ``strict=False`` an unimplemented block type stops the decode instead
    of raising, so `detect` can report the framing it did understand.
    """
    if not LZX_MIN_WINDOW_BITS <= window_bits <= LZX_MAX_WINDOW_BITS:
        raise ValueError(
            "lzx: window_bits must be %d..%d, not %r"
            % (LZX_MIN_WINDOW_BITS, LZX_MAX_WINDOW_BITS, window_bits)
        )
    reader = BitReader(data)
    info = {
        "method": "lzx",
        "input_size": len(data),
        "output_size": 0,
        "window_bits": window_bits,
        "intel_e8": 0,
        "intel_filesize": None,
        "e8_translation": bool(e8_translation),
        "blocks": [],
        "stored_bytes": 0,
        "stored_nonzero_high": 0,
        "complete": False,
        "stop_reason": None,
    }

    info["intel_e8"] = reader.read(1)
    if info["intel_e8"]:
        info["intel_filesize"] = (reader.read(16) << 16) | reader.read(16)
    if reader.read(1):
        raise DecodeError(
            "lzx: reserved stream-header bit is set; this is not an LZX stream"
        )
    if info["intel_e8"] and not e8_translation:
        raise UnsupportedFormat(
            "UNSUPPORTED(lzx E8 pre-processing); pass e8_translation=True to "
            "return translated output"
        )

    out = bytearray()
    while True:
        if expected_size is not None and len(out) >= expected_size:
            info["complete"] = True
            break
        if reader.remaining_bits() < LZX_BLOCK_HEADER_BITS:
            info["complete"] = True
            break
        btype = reader.read(3)
        size = (reader.read(16) << 8) | reader.read(8)
        name = LZX_BLOCK_NAMES.get(btype, "unknown(%d)" % btype)
        block = {"type": name, "type_id": btype, "size": size, "offset": len(out)}
        info["blocks"].append(block)

        if btype == 3:
            block["pad_bits"] = reader.align16()
            block["r"] = [reader.read(12), reader.read(12), reader.read(12)]
            if len(out) + size > max_output:
                raise DecodeError(
                    "lzx: stored block of %d bytes exceeds the %d-byte limit"
                    % (size, max_output)
                )
            high = 0
            for _ in range(size):
                word = reader.read(16)
                out.append(word & 0xFF)
                if word >> 8:
                    high += 1
            info["stored_bytes"] += size
            info["stored_nonzero_high"] += high
            block["high_bytes_nonzero"] = high
        elif btype == 0:
            raise DecodeError("lzx: invalid block type 0 at output %d" % len(out))
        else:
            reason = "lzx block type %s at output %d" % (name, len(out))
            if strict:
                raise UnsupportedFormat(
                    "UNSUPPORTED(%s); only uncompressed (stored) LZX blocks are "
                    "implemented" % reason
                )
            info["stop_reason"] = "UNSUPPORTED(%s)" % reason
            break

    info["output_size"] = len(out)
    if expected_size is not None and len(out) != expected_size:
        raise DecodeError("lzx: decoded %d bytes, expected %d" % (len(out), expected_size))
    blob = bytes(out)
    if info["intel_e8"] and e8_translation:
        blob = lzx_e8_translate(blob, info["intel_filesize"] or len(blob))
    return blob, info


def decompress_lzx(data, expected_size=None, window_bits=LZX_DEFAULT_WINDOW_BITS,
                   e8_translation=False, max_output=DEFAULT_MAX_OUTPUT):
    """Decode an LZX stream; return bytes."""
    return _lzx_decode(data, expected_size, window_bits, e8_translation, max_output)[0]


# --------------------------------------------------------------------------
# Detection and the public API
# --------------------------------------------------------------------------


def _looks_like_zlib(data):
    """True for a syntactically valid zlib header (map `.cmp`, not CE ROM)."""
    if len(data) < 2:
        return False
    cmf, flg = data[0], data[1]
    return (cmf & 0x0F) == 8 and (cmf >> 4) <= 7 and ((cmf << 8) | flg) % 31 == 0


def _pick_candidate(candidates):
    """Pick the best candidate; ties are ambiguous, never a coin flip.

    Returns ``(method, confidence, note)``.
    """
    rank = {"confirmed": 3, "candidate": 2, "weak": 1}
    if not candidates:
        return None, "none", None
    best = max(candidates, key=lambda c: rank[c["confidence"]])
    top = [c for c in candidates if rank[c["confidence"]] == rank[best["confidence"]]]
    if len(top) > 1:
        return None, "ambiguous", (
            "two candidates at the same evidence level: %s"
            % ", ".join(c["method"] for c in top)
        )
    return best["method"], best["confidence"], None


def detect(data, expected_size=None):
    """Return the candidate method with the evidence for it, never a guess.

    The result is a dict::

        {"input_size": int, "expected_size": int|None,
         "method": "lzss"|"lzx"|None, "confidence": "confirmed"|"candidate"|
                     "weak"|"ambiguous"|"none",
         "evidence": [str], "candidates": [{"method", "confidence", "evidence",
                                            "output_size"}]}

    "confirmed" means the decoded length equals ``expected_size``.  "candidate"
    means the LZX framing parsed with at least one block.  "weak" means the
    bytes merely survive the LZSS decoder — that alone proves nothing, because
    almost any input does.
    """
    result = {
        "input_size": len(data),
        "expected_size": expected_size,
        "method": None,
        "confidence": "none",
        "evidence": [],
        "candidates": [],
    }
    candidates = []

    if not data:
        result["evidence"].append("empty input: nothing to detect")
        return result

    try:
        _, lzx_info = _lzx_decode(
            data, expected_size=None, e8_translation=True, strict=False
        )
    except CeCompressError as exc:
        result["evidence"].append("lzx: framing does not parse (%s)" % exc)
    else:
        if lzx_info["blocks"]:
            evidence = [
                "stream header parsed (intel_e8=%d%s)"
                % (lzx_info["intel_e8"],
                   ", filesize=%d" % lzx_info["intel_filesize"]
                   if lzx_info["intel_filesize"] else ""),
                "%d block(s): %s"
                % (len(lzx_info["blocks"]),
                   ", ".join("%s/%d B" % (b["type"], b["size"])
                             for b in lzx_info["blocks"])),
                "stored %d B, output %d B, non-zero stored high bytes %d"
                % (lzx_info["stored_bytes"], lzx_info["output_size"],
                   lzx_info["stored_nonzero_high"]),
            ]
            confidence = "candidate"
            if expected_size is not None and lzx_info["output_size"] == expected_size:
                confidence = "confirmed"
                evidence.append("output size matches expected_size=%d" % expected_size)
            if not lzx_info["complete"]:
                evidence.append("stopped early: %s" % lzx_info["stop_reason"])
            candidates.append({
                "method": "lzx",
                "confidence": confidence,
                "evidence": evidence,
                "output_size": lzx_info["output_size"],
            })
        else:
            result["evidence"].append(
                "lzx: stream header parsed but no block follows; not a candidate"
            )

    try:
        _, lz_info = _lzss_decode(data)
    except CeCompressError as exc:
        result["evidence"].append("lzss: decode failed (%s)" % exc)
    else:
        evidence = [
            "LZSS has no signature: success only means no back-reference pointed "
            "before the start of the output",
            "%d group(s), %d literal(s), %d match(es), max length %d, max offset %d, "
            "output %d B"
            % (lz_info["groups"], lz_info["literals"], lz_info["matches"],
               lz_info["max_length"], lz_info["max_offset"], lz_info["output_size"]),
        ]
        confidence = "weak"
        if expected_size is not None and lz_info["output_size"] == expected_size:
            confidence = "confirmed"
            evidence.append("output size matches expected_size=%d" % expected_size)
        candidates.append({
            "method": "lzss",
            "confidence": confidence,
            "evidence": evidence,
            "output_size": lz_info["output_size"],
        })

    result["candidates"] = candidates

    if _looks_like_zlib(data) and not any(
        c["confidence"] == "confirmed" for c in candidates
    ):
        result["evidence"].append(
            "first bytes %02x %02x are a valid zlib header (map .cmp container); "
            "CE ROM sections are not zlib" % (data[0], data[1])
        )
        result["confidence"] = "none"
        return result

    method, confidence, note = _pick_candidate(candidates)
    result["method"] = method
    result["confidence"] = confidence
    if note:
        result["evidence"].append(note)
    return result


def decompress_info(data, expected_size=None, method="auto",
                    window_bits=LZX_DEFAULT_WINDOW_BITS, e8_translation=False,
                    max_output=DEFAULT_MAX_OUTPUT):
    """Decode and return ``(bytes, info)``; see `decompress`."""
    name = normalise_method(method)
    verdict = None
    if name == "auto":
        verdict = detect(data, expected_size)
        if verdict["method"] is None:
            raise UnsupportedFormat(
                "cannot pick a method (%s); pass method= explicitly: %s"
                % (verdict["confidence"], " | ".join(verdict["evidence"]))
            )
        if verdict["confidence"] == "weak":
            raise UnsupportedFormat(
                "only a weak %s candidate (no size match); pass method='%s' or an "
                "expected size" % (verdict["method"], verdict["method"])
            )
        name = verdict["method"]
    if name == "lzss":
        blob, info = _lzss_decode(data, expected_size, max_output)
    else:
        blob, info = _lzx_decode(data, expected_size, window_bits,
                                 e8_translation, max_output)
    info["method"] = name
    if verdict is not None:
        info["detected"] = {
            "confidence": verdict["confidence"],
            "evidence": verdict["evidence"],
        }
    return blob, info


def decompress(data, expected_size=None, method="auto",
               window_bits=LZX_DEFAULT_WINDOW_BITS, e8_translation=False,
               max_output=DEFAULT_MAX_OUTPUT):
    """Decode ``data`` and return the unpacked bytes.

    ``method`` is ``"auto"`` (default), ``"lzss"``/``"cecompress"`` or
    ``"lzx"``.  Raises `UnsupportedFormat` when the method cannot be chosen or
    the format is not implemented, and `DecodeError` when the stream is corrupt
    or the output length differs from ``expected_size``.
    """
    return decompress_info(data, expected_size, method, window_bits,
                           e8_translation, max_output)[0]


def decompress_file(path, out=None, **kwargs):
    """Read ``path``, decompress it, optionally write ``out``; return bytes."""
    with open(path, "rb") as handle:
        data = handle.read()
    blob = decompress(data, **kwargs)
    if out:
        directory = os.path.dirname(os.path.abspath(out))
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(out, "wb") as handle:
            handle.write(blob)
    return blob


# --------------------------------------------------------------------------
# Synthetic streams for --selftest (no vendor bytes anywhere below)
# --------------------------------------------------------------------------


def _lcg_bytes(seed, count):
    """Deterministic pseudo-random bytes (LCG, stable across versions)."""
    out = bytearray()
    x = seed & 0x7FFFFFFF
    for _ in range(count):
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        out.append((x >> 16) & 0xFF)
    return bytes(out)


def _int_bits(value, count):
    return [(value >> (count - 1 - i)) & 1 for i in range(count)]


def _bits_to_lzx(bits):
    """Pack a bit list into 16-bit little-endian LZX words, MSB-first, zero pad."""
    out = bytearray()
    for start in range(0, len(bits), 16):
        chunk = bits[start:start + 16]
        word = 0
        for bit in chunk + [0] * (16 - len(chunk)):
            word = (word << 1) | bit
        out += bytes((word & 0xFF, word >> 8))
    return bytes(out)


def _build_lzx_stored(chunks, intel_filesize=None):
    """Build an LZX stream of uncompressed blocks around ``chunks``."""
    bits = []
    bits += _int_bits(1 if intel_filesize is not None else 0, 1)
    if intel_filesize is not None:
        bits += _int_bits((intel_filesize >> 16) & 0xFFFF, 16)
        bits += _int_bits(intel_filesize & 0xFFFF, 16)
    bits += _int_bits(0, 1)                      # reserved
    for chunk in chunks:
        bits += _int_bits(3, 3)                  # uncompressed
        bits += _int_bits((len(chunk) >> 8) & 0xFFFF, 16)
        bits += _int_bits(len(chunk) & 0xFF, 8)
        if len(bits) % 16:
            bits += [0] * (16 - len(bits) % 16)  # 16-bit alignment padding
        bits += _int_bits(1, 12) + _int_bits(1, 12) + _int_bits(1, 12)
        for byte in chunk:
            bits += _int_bits(byte, 16)          # one 16-bit word per stored byte
    return _bits_to_lzx(bits)


def _build_lzx_block_header(block_type, size):
    """Stream header + one block header of ``block_type``, no body."""
    bits = _int_bits(0, 1) + _int_bits(0, 1)
    bits += _int_bits(block_type, 3)
    bits += _int_bits((size >> 8) & 0xFFFF, 16) + _int_bits(size & 0xFF, 8)
    return _bits_to_lzx(bits)


def selftest():
    """Run the synthetic assertions; return 0 (raise on mismatch)."""
    checks = []

    def ok(label, got, want):
        if got != want:
            raise AssertionError("%s: got %r, want %r" % (label, got, want))
        checks.append(label)

    def raises(exc_type, label, func, *args, **kwargs):
        try:
            func(*args, **kwargs)
        except exc_type as exc:
            checks.append(label)
            return exc
        except CeCompressError as exc:
            raise AssertionError(
                "%s: raised %s (%s), want %s"
                % (label, type(exc).__name__, exc, exc_type.__name__)
            )
        raise AssertionError("%s: did not raise %s" % (label, exc_type.__name__))

    # --- LZSS: round-trip over literals, matches, maximum length, sizes ------
    corpora = [
        ("empty", b""),
        ("one literal", b"A"),
        ("seven literals", bytes(range(7))),
        ("eight literals", bytes(range(8))),
        ("nine literals", bytes(range(9))),
        ("run of one byte", b"A" * 100),
        ("period 3", b"abc" * 60),
        ("max length corpus", b"ABCDEFGHIJKLMNOPQR" * 40),
        ("4 KiB", bytes(range(256)) * 16),
        ("4 KiB + 1", bytes(range(256)) * 16 + b"Z"),
        ("LCG 5000", _lcg_bytes(7, 5000)),
        ("LCG 50000", _lcg_bytes(11, 50000)),
    ]
    for label, plain in corpora:
        stream, enc = encode_lzss(plain)
        blob, info = _lzss_decode(stream)
        ok("lzss round-trip: %s" % label, blob, plain)
        ok("lzss literal count: %s" % label, info["literals"], enc["literals"])
        ok("lzss match count: %s" % label, info["matches"], enc["matches"])
        ok("lzss max length: %s" % label, info["max_length"], enc["max_length"])
        ok("lzss max offset: %s" % label, info["max_offset"], enc["max_offset"])
        ok("lzss output size: %s" % label, len(blob), len(plain))
        ok("lzss encoded size bound: %s" % label,
           len(stream) <= len(plain) + (len(plain) + 7) // 8 + 1, True)

    ok("lzss all-literal corpus uses no match",
       _lzss_decode(encode_lzss(bytes(range(7)))[0])[1]["matches"], 0)
    ok("lzss run uses a length>3 match",
       encode_lzss(b"A" * 100)[1]["max_length"] > 3, True)
    ok("lzss max match length reached",
       encode_lzss(b"ABCDEFGHIJKLMNOPQR" * 40)[1]["max_length"], 18)
    # A hand-built run: literal 'Q', then a match with offset 0 (distance 1).
    stream = bytes([0b00000010, ord("Q"), 0x00, 0x0F])
    ok("lzss hand-built run of 18", decompress_lzss(stream), b"Q" * 19)

    # Window wrap: a match at distance 4096 (stored offset 4095).
    for seed in range(1, 60):
        prefix = _lcg_bytes(seed, LZSS_WINDOW)
        if not any(prefix[p:p + 3] == prefix[0:3] for p in range(1, LZSS_WINDOW - 2)):
            break
    else:
        raise AssertionError("no LCG seed produced a unique 3-byte prefix")
    wrapped = prefix + prefix[:200]
    wrap_stream, wrap_stats = encode_lzss(wrapped)
    ok("lzss window wrap: round-trip", decompress_lzss(wrap_stream), wrapped)
    ok("lzss window wrap: max offset", wrap_stats["max_offset"], LZSS_WINDOW - 1)
    ok("lzss window wrap: max length", wrap_stats["max_length"], 18)

    # LZSS negatives: never return partial or invented bytes.
    exc = raises(DecodeError, "lzss truncated match rejected",
                 decompress_lzss, bytes([0x01, 0x00]))
    ok("lzss truncated match message", "truncated" in str(exc), True)
    exc = raises(DecodeError, "lzss back-reference before start rejected",
                 decompress_lzss, bytes([0x01, 0x00, 0x00]))
    ok("lzss back-reference message", "before the start" in str(exc), True)
    raises(DecodeError, "lzss expected_size mismatch rejected",
           decompress_lzss, encode_lzss(b"ABC")[0], 5)
    ok("lzss expected_size match accepted",
       decompress_lzss(encode_lzss(b"ABC")[0], 3), b"ABC")

    # --- LZX bit reader: MSB-first, cross-word, alignment, truncation --------
    flat = _int_bits(0xAA55, 16) + _int_bits(0xF00F, 16)

    def value(bits):
        if not bits:
            return 0
        return int("".join(str(b) for b in bits), 2)

    reader = BitReader(_bits_to_lzx(flat))
    ok("lzx bit reader word 0", reader.read(16), 0xAA55)
    ok("lzx bit reader word 1", reader.read(16), 0xF00F)
    ok("lzx bit reader at_end", reader.at_end, True)
    reader = BitReader(_bits_to_lzx(flat))
    ok("lzx bit reader 5 bits", reader.read(5), value(flat[:5]))
    ok("lzx bit reader cross-word 12 bits", reader.read(12), value(flat[5:17]))
    ok("lzx bit reader 15 bits", reader.read(15), value(flat[17:32]))
    reader = BitReader(_bits_to_lzx(flat))
    reader.read(4)
    ok("lzx align16 padding", reader.align16(), 12)
    ok("lzx align16 lands on word 1", reader.read(16), 0xF00F)
    reader = BitReader(_bits_to_lzx(_int_bits(0x1F, 5)))
    ok("lzx short first read", reader.read(5), 0x1F)
    raises(DecodeError, "lzx bitstream truncation rejected", BitReader(b"\x01").read, 16)
    raises(ValueError, "lzx bit reader rejects >24-bit reads",
           BitReader(b"\x00\x00").read, 25)

    # --- LZX stored blocks ---------------------------------------------------
    payload = bytes(range(256)) * 4 + b"tail"
    stream = _build_lzx_stored([payload])
    ok("lzx stored block round-trip",
       decompress_lzx(stream, expected_size=len(payload)), payload)
    blob, info = _lzx_decode(stream, expected_size=len(payload))
    ok("lzx stored: one block", len(info["blocks"]), 1)
    ok("lzx stored: block type", info["blocks"][0]["type"], "uncompressed")
    ok("lzx stored: block size", info["blocks"][0]["size"], len(payload))
    ok("lzx stored: R0/R1/R2", info["blocks"][0]["r"], [1, 1, 1])
    ok("lzx stored: high bytes all zero", info["stored_nonzero_high"], 0)
    ok("lzx stored: complete", info["complete"], True)
    ok("lzx stored: no E8", info["intel_e8"], 0)
    ok("lzx stored: output size", info["output_size"], len(payload))

    chunks = [b"first block", b"", b"third block, longer than the others"]
    total = sum(len(c) for c in chunks)
    blob, info = _lzx_decode(_build_lzx_stored(chunks), expected_size=total)
    ok("lzx multi-block round-trip", blob, b"".join(chunks))
    ok("lzx multi-block count", len(info["blocks"]), 3)
    ok("lzx multi-block sizes", [b["size"] for b in info["blocks"]],
       [len(c) for c in chunks])
    ok("lzx empty payload", _lzx_decode(_build_lzx_stored([b""]), 0)[0], b"")
    raises(DecodeError, "lzx expected_size mismatch rejected",
           decompress_lzx, _build_lzx_stored([b"abc"]), 4)
    raises(DecodeError, "lzx truncated stored block rejected",
           decompress_lzx, _build_lzx_stored([b"abcdef"])[:-1], 6)

    # --- LZX unsupported block types: exact refusal, no invented bytes ------
    for block_type, name in ((1, "verbatim"), (2, "aligned")):
        exc = raises(UnsupportedFormat, "lzx %s block refused" % name,
                     decompress_lzx, _build_lzx_block_header(block_type, 16))
        ok("lzx %s refusal names the type" % name,
           "UNSUPPORTED(lzx block type %s" % name in str(exc), True)
        ok("lzx %s refusal says stored-only" % name,
           "only uncompressed (stored) LZX blocks" in str(exc), True)
        blob, info = _lzx_decode(_build_lzx_block_header(block_type, 16),
                                 strict=False)
        ok("lzx %s probe stops before the body" % name, len(info["blocks"]), 1)
        ok("lzx %s probe is incomplete" % name, info["complete"], False)
        ok("lzx %s probe stop reason" % name,
           "UNSUPPORTED" in (info["stop_reason"] or ""), True)
    exc = raises(DecodeError, "lzx invalid block type 0 rejected",
                 decompress_lzx, _build_lzx_block_header(0, 16))
    ok("lzx invalid block type message", "invalid block type 0" in str(exc), True)
    raises(DecodeError, "lzx reserved header bit rejected", decompress_lzx,
           _bits_to_lzx(_int_bits(0, 1) + _int_bits(1, 1) + _int_bits(3, 3)))
    raises(DecodeError, "empty input is not LZX", decompress_lzx, b"")

    # --- LZX E8 translation (off by default) --------------------------------
    body = bytearray(32)
    body[0x10] = 0xE8
    struct.pack_into("<i", body, 0x11, 4)             # in range: 4 + 0x10 = 0x14
    body[0x18] = 0xE8
    struct.pack_into("<i", body, 0x19, -0x100)        # out of range for filesize
    body = bytes(body)
    e8_stream = _build_lzx_stored([body], intel_filesize=0x1000)
    exc = raises(UnsupportedFormat, "lzx E8 stream refused by default",
                 decompress_lzx, e8_stream, 32)
    ok("lzx E8 refusal mentions the switch", "e8_translation=True" in str(exc), True)
    blob = decompress_lzx(e8_stream, 32, e8_translation=True)
    ok("lzx E8 in-range call translated",
       struct.unpack_from("<i", blob, 0x11)[0], 4 + 0x10)
    ok("lzx E8 out-of-range call untouched",
       struct.unpack_from("<i", blob, 0x19)[0], -0x100)
    ok("lzx E8 keeps the 0xE8 opcode", (blob[0x10], blob[0x18]), (0xE8, 0xE8))

    # Corrupt-input sweep: every truncation of a valid stream, plus the same
    # truncation with one bogus 0xFF byte appended, under all three method
    # settings, must raise CeCompressError or decode; a raw exception would mean
    # the CLI could crash on a bad section.
    sweeps = [
        encode_lzss(b"hello hello hello world " * 40)[0],
        _build_lzx_stored([b"payload " * 50]),
    ]
    cases = 0
    for base in sweeps:
        for cut in range(len(base)):
            for mutated in (base[:cut], base[:cut] + b"\xff"):
                for method in ("lzss", "lzx", "auto"):
                    cases += 1
                    try:
                        decompress(mutated, method=method)
                    except CeCompressError:
                        pass
                    except Exception as exc:      # noqa: BLE001 - the point of the test
                        raise AssertionError(
                            "corrupt stream cut %d with method %s raised %s: %s"
                            % (cut, method, type(exc).__name__, exc)
                        )
    ok("corrupt-input sweep cases", cases,
       6 * sum(len(base) for base in sweeps))
    ok("corrupt-input sweep raises only CeCompressError", True, True)

    # --- detect() ------------------------------------------------------------
    plain = b"the quick brown fox " * 40
    lz_stream = encode_lzss(plain)[0]
    verdict = detect(lz_stream)
    ok("detect LZSS without a size: weak", verdict["confidence"], "weak")
    ok("detect LZSS without a size: method", verdict["method"], "lzss")
    ok("detect LZSS evidence says it is not a signature",
       any("no signature" in line
           for line in verdict["candidates"][0]["evidence"]), True)
    verdict = detect(lz_stream, expected_size=len(plain))
    ok("detect LZSS with the right size: confirmed", verdict["confidence"], "confirmed")
    ok("detect LZSS with the right size: method", verdict["method"], "lzss")
    raises(UnsupportedFormat, "auto refuses a weak-only candidate",
           decompress, lz_stream)
    ok("auto decodes LZSS with a size",
       decompress(lz_stream, len(plain)), plain)
    ok("explicit cecompress alias works",
       decompress(lz_stream, method="cecompress"), plain)

    verdict = detect(stream)
    ok("detect LZX without a size: candidate", verdict["confidence"], "candidate")
    ok("detect LZX without a size: method", verdict["method"], "lzx")
    ok("detect LZX candidate count", len(verdict["candidates"]), 1)
    ok("detect LZX candidate block evidence",
       any("uncompressed/%d B" % len(payload) in line
           for line in verdict["candidates"][0]["evidence"]), True)
    verdict = detect(stream, expected_size=len(payload))
    ok("detect LZX with the right size: confirmed", verdict["confidence"], "confirmed")
    ok("auto decodes LZX with a size", decompress(stream, len(payload)), payload)

    # The ranking rule: structured LZX beats a signature-free LZSS hit, and a
    # tie is ambiguous instead of a coin flip.
    ok("rank: no candidates",
       _pick_candidate([]), (None, "none", None))
    ok("rank: candidate beats weak",
       _pick_candidate([{"method": "lzx", "confidence": "candidate"},
                        {"method": "lzss", "confidence": "weak"}])[:2],
       ("lzx", "candidate"))
    ok("rank: weak alone stays weak",
       _pick_candidate([{"method": "lzss", "confidence": "weak"}])[:2],
       ("lzss", "weak"))
    tie = _pick_candidate([{"method": "lzx", "confidence": "confirmed"},
                           {"method": "lzss", "confidence": "confirmed"}])
    ok("rank: a confirmed tie is ambiguous", tie[:2], (None, "ambiguous"))
    ok("rank: the tie note names both", "lzx, lzss" in tie[2], True)

    verdict = detect(b"\x78\x9c" + b"\x00" * 20)
    ok("detect zlib header is not a CE stream", verdict["method"], None)
    ok("detect zlib header evidence",
       any("zlib header" in line for line in verdict["evidence"]), True)
    verdict = detect(b"")
    ok("detect empty input: none", verdict["confidence"], "none")
    ok("detect empty input: no method", verdict["method"], None)
    raises(UnsupportedFormat, "auto on empty input", decompress, b"")
    raises(UnsupportedFormat, "unknown method name rejected",
           decompress, b"abc", None, "lzma")
    raises(ValueError, "LZX window below 32 KiB rejected",
           decompress_lzx, stream, len(payload), 14)

    # --- CLI + file helper ---------------------------------------------------
    import tempfile

    with tempfile.TemporaryDirectory(prefix="cecompress-selftest-") as tmp:
        lz_path = os.path.join(tmp, "section.lzss")
        out_path = os.path.join(tmp, "section.bin")
        with open(lz_path, "wb") as handle:
            handle.write(lz_stream)
        ok("decompress_file LZSS", decompress_file(lz_path, out_path,
                                                   expected_size=len(plain)), plain)
        with open(out_path, "rb") as handle:
            ok("decompress_file wrote the output", handle.read(), plain)

        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli detect exit", main(["detect", lz_path, "--size", str(len(plain))]), 0)
        ok("cli detect prints the method", "method  lzss (confirmed)" in buf.getvalue(), True)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli detect --json exit", main(["detect", lz_path, "--json"]), 0)
        verdict = json.loads(buf.getvalue())
        ok("cli detect --json method", verdict["method"], "lzss")
        ok("cli detect --json keys",
           sorted(verdict), ["candidates", "confidence", "evidence", "expected_size",
                             "input_size", "method"])

        out2 = os.path.join(tmp, "cli.bin")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli decompress exit",
               main(["decompress", lz_path, "-o", out2, "--size", str(len(plain)),
                     "--json"]), 0)
        with open(out2, "rb") as handle:
            ok("cli decompress wrote the bytes", handle.read(), plain)
        ok("cli decompress --json sha256",
           json.loads(buf.getvalue())["sha256"],
           hashlib.sha256(plain).hexdigest())

        bad_path = os.path.join(tmp, "unsupported.bin")
        with open(bad_path, "wb") as handle:
            handle.write(_build_lzx_block_header(1, 16))
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            ok("cli unsupported stream exit",
               main(["decompress", bad_path, "-o", out2, "--method", "lzx"]), 1)
        ok("cli unsupported stream message",
           "UNSUPPORTED(lzx block type verbatim" in err.getvalue(), True)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            ok("cli missing file exit", main(["detect", os.path.join(tmp, "nope")]), 1)
        ok("cli missing file message", "error:" in err.getvalue(), True)

    print("cecompress selftest: %d checks OK (synthetic streams, no vendor data; "
          "spec conformance UNVERIFIED)" % len(checks))
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _hex_or_int(text):
    return int(text, 0)


def detect_command(args):
    with open(args.file, "rb") as handle:
        data = handle.read()
    verdict = detect(data, args.size)
    if args.json:
        print(json.dumps(verdict, indent=2))
        return 0
    print("file    %s" % args.file)
    print("input   %d bytes" % verdict["input_size"])
    if verdict["expected_size"] is not None:
        print("expect  %d bytes" % verdict["expected_size"])
    if verdict["method"] is None:
        print("method  none (%s)" % verdict["confidence"])
    else:
        print("method  %s (%s)" % (verdict["method"], verdict["confidence"]))
    for candidate in verdict["candidates"]:
        print("  candidate %s (%s), output %d B"
              % (candidate["method"], candidate["confidence"], candidate["output_size"]))
        for line in candidate["evidence"]:
            print("    - %s" % line)
    for line in verdict["evidence"]:
        print("  note: %s" % line)
    return 0


def decompress_command(args):
    with open(args.file, "rb") as handle:
        data = handle.read()
    blob, info = decompress_info(
        data, args.size, args.method, args.window_bits, args.e8_translation,
        args.max_output,
    )
    directory = os.path.dirname(os.path.abspath(args.out))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(args.out, "wb") as handle:
        handle.write(blob)
    digest = hashlib.sha256(blob).hexdigest()
    if args.json:
        print(json.dumps({
            "file": args.file,
            "out": args.out,
            "method": info["method"],
            "confidence": info.get("detected", {}).get("confidence"),
            "input_size": len(data),
            "output_size": len(blob),
            "sha256": digest,
        }, indent=2))
        return 0
    print("wrote %s (method %s, %d -> %d bytes, sha256 %s)"
          % (args.out, info["method"], len(data), len(blob), digest))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--selftest", action="store_true",
                    help="run the synthetic stream self-test and exit (needs no image)")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("detect", help="report the candidate method with evidence")
    p.add_argument("file")
    p.add_argument("--size", type=_hex_or_int, default=None,
                   help="expected output size; a match confirms the candidate")
    p.add_argument("--json", action="store_true", help="machine-readable output")

    p = sub.add_parser("decompress", help="decode a stream into a file")
    p.add_argument("file")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--method", default="auto",
                   help="auto (default), lzss/cecompress or lzx")
    p.add_argument("--size", type=_hex_or_int, default=None,
                   help="expected output size (o32_vsize); mismatches are errors")
    p.add_argument("--window-bits", type=int, default=LZX_DEFAULT_WINDOW_BITS,
                   help="LZX window size (default 15 = 32 KiB)")
    p.add_argument("--e8-translation", action="store_true",
                   help="apply the LZX E8 post-processing (off by default)")
    p.add_argument("--max-output", type=_hex_or_int, default=DEFAULT_MAX_OUTPUT,
                   help="refuse to produce more than this many bytes")
    p.add_argument("--json", action="store_true", help="machine-readable output")

    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd is None:
        ap.error("a subcommand is required (detect, decompress) or --selftest")
    try:
        if args.cmd == "detect":
            return detect_command(args)
        return decompress_command(args)
    except CeCompressError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    except OSError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
