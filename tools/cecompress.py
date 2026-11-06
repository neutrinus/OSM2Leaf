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

Family 3 — ``lznt1`` ([MS-XCA] 2.5, the NT/CE ``RtlCompressBuffer`` codec)
--------------------------------------------------------------------------
``method="lznt1"`` (alias ``ntfs-lznt1``).

The stream is a series of independently decodable chunks of at most 4096
uncompressed bytes.  Each chunk starts with a 16-bit little-endian header::

    bits 11..0  payload size - 1                 (payload excludes the header)
    bits 14..12 signature, must be 0b011 (3)
    bit  15     1 = compressed, 0 = stored

[MS-XCA] 2.5 ("LZNT1") states this on a 59-byte example: header ``0xB038``,
signature 3, compressed flag set, field 56, chunk 59 bytes = 2 header + 57
payload.  That example is a test vector in ``--selftest``; it is the one
positive control in this module that comes from the specification rather than
from the reference encoder.

A stored chunk carries its payload verbatim.  A compressed chunk is a series of
flag bytes (LSB-first, bit 0 first), each followed by up to eight tokens:

=============  ===============================================================
flag bit = 0   literal: one byte, appended to the output.
flag bit = 1   match: two bytes ``lo``, ``hi`` (one 16-bit little-endian word).
=============  ===============================================================

The word carries the displacement in its **high** bits and the length in its
low bits, and the split moves with ``u``, the number of bytes already produced
in this chunk — the spec's pseudo-code halves ``u - 1`` while it is ``>= 0x10``::

    nbits = max(4, (u - 1).bit_length())             # displacement bits, 4..12
    displacement = (word >> (16 - nbits)) + 1        # 1..u
    length       = (word & ((1 << (16 - nbits)) - 1)) + 3

The first 16 bytes of a chunk therefore use a 4 + 12 split, and the full 12 + 4
split applies from ``u = 2049`` on (maximum length 18 there; at 4 + 12 the
length field is 12 bits wide, which is why the spec's own example contains a
27-byte match).  A displacement field of ``0x0FFF`` (nominal distance 4096, one
past a full chunk) at ``nbits == 12``, i.e. a word ``0xFFF0``–``0xFFFF``, is
treated as the reserved end-of-chunk marker that TODO M1.2b calls "the 0x0FFF
end marker": the decoder stops that chunk, skips to its end and records the
marker instead of copying 4096 bytes back.  The bare word ``0x0FFF`` is **not**
that marker — at the 12 + 4 split it is distance 256, length 18.  Which
producer emits the marker at all is UNKNOWN.

Matches may overlap their own output (byte-at-a-time copy) but may not point
before the first byte of their own chunk, because chunks are independent.  A
zero chunk header ends the data ([MS-XCA] 2.5; libfwnt); any bytes left after
it are reported as ``trailing_bytes``/``trailing_zero`` padding.  Any other
header mismatch is a `DecodeError`.

Family 4 — XPRESS variants: skeletons only, no decoder
------------------------------------------------------
``method="xpress-lz77"`` — plain LZ77 ([MS-XCA] 2.3/2.4): headerless, a 32-bit
little-endian flag DWORD groups 32 tokens (0 = literal, 1 = a 16-bit match
word), so the only structure to parse is that first flag DWORD.
``method="xpress-huffman"`` — "LZ77+Huffman" XPRESS: a 256-byte table of 512
4-bit code lengths, low nibble first, then a Huffman-coded token stream.

Neither decodes.  Each skeleton parses what it can and then raises
``UnsupportedFormat("UNSUPPORTED(xpress-lz77: …)")`` /
``UnsupportedFormat("UNSUPPORTED(xpress-huffman: …)")`` with the reason, so a
caller never receives guessed bytes.  Turning one into a real decoder is new
work with its own test vector, not a switch.

Auto-detection never pretends to know: `detect` returns a candidate method plus
the evidence for and against it, and `decompress(method="auto")` refuses a
"weak" candidate (an LZSS stream has no signature, so *any* byte string decodes
as LZSS unless a back-reference points before the start of the output).
`detect` only ranks the two families with a structural check (LZX framing,
LZSS length); LZNT1 and the XPRESS skeletons are reachable through an explicit
``--method`` and through `probe`.

`probe` is the M1.2b runner: for a file holding one stored section it tries
every method at every offset (default 0..32) and reports which attempt produces
exactly the expected (``o32_vsize``) length, with the decoded SHA-256, the first
bytes and cheap plausibility counters as evidence.  It writes nothing and never
picks a winner beyond "the length matched".

Usage::

    cecompress.py detect FILE [--size N] [--json]
    cecompress.py decompress FILE -o OUT [--method m] [--size N] [--json]
                                [--window-bits 15] [--e8-translation]
    cecompress.py probe FILE --size N [--offsets 0-32] [--methods m,m,…] [--json]
    cecompress.py --selftest          # synthetic streams, no vendor data

``probe`` exits 0 when at least one attempt decodes to exactly ``--size``, 1
when none does (a complete negative: every decoder × offset is listed) and 2 on
a usage or I/O error.

API::

    blob = decompress(data, expected_size=None, method="auto")
    verdict = detect(data, expected_size=None)
    blob = decompress_file("section.bin", expected_size=0x5b8)
    report = probe(data, expected_size=0x5b8, offsets=range(0, 33))
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

# --- LZNT1 ([MS-XCA] 2.5) ----------------------------------------------------
LZNT1_CHUNK_SIZE = 4096               # uncompressed bytes per chunk (maximum)
LZNT1_SIGNATURE = 0x3                 # bits 14..12, must be 0b011
LZNT1_SIGNATURE_BITS = LZNT1_SIGNATURE << 12
LZNT1_COMPRESSED = 0x8000             # bit 15
LZNT1_SIZE_MASK = 0x0FFF              # bits 11..0, payload size - 1
LZNT1_MIN_DISPLACEMENT_BITS = 4
LZNT1_MAX_DISPLACEMENT_BITS = 12
LZNT1_MIN_MATCH = 3
LZNT1_MAX_MATCH = 18                  # 4 length bits + 3
LZNT1_END_MARKER = 0x0FFF             # reserved displacement field

# --- XPRESS / plain LZ77 ([MS-XCA] 2.3/2.4) ---------------------------------
XPRESS_HUFFMAN_SYMBOLS = 512
XPRESS_HUFFMAN_TABLE_BYTES = XPRESS_HUFFMAN_SYMBOLS // 2   # 4 bits per symbol
XPRESS_HUFFMAN_MAX_BITS = 15
LZ77_FLAG_TOKEN_BITS = 32             # plain LZ77 groups flags in 32-bit DWORDs

# Methods `probe` enumerates.  ``detect``/``auto`` keep to lzss + lzx.
PROBE_METHODS = ("lzss", "lzx", "lznt1", "xpress-lz77", "xpress-huffman")

METHOD_ALIASES = {
    "auto": "auto",
    "lzss": "lzss",
    "cecompress": "lzss",
    "ce-lzss": "lzss",
    "lzx": "lzx",
    "lznt1": "lznt1",
    "ntfs-lznt1": "lznt1",
    "xpress-lz77": "xpress-lz77",
    "xpress-plain": "xpress-lz77",
    "lz77": "xpress-lz77",
    "xpress-huffman": "xpress-huffman",
    "xpress-huff": "xpress-huffman",
    "lz77+huffman": "xpress-huffman",
}


class CeCompressError(Exception):
    """Base class for every refusal or decode failure in this module."""


class UnsupportedFormat(CeCompressError):
    """The stream is not this format, or the format is not (fully) implemented."""


class DecodeError(CeCompressError):
    """The stream claims the format but is truncated, corrupt or impossible."""


def normalise_method(method):
    """Map a user-facing method name to one of the decoder keys."""
    key = str(method).strip().lower()
    try:
        return METHOD_ALIASES[key]
    except KeyError:
        raise UnsupportedFormat(
            "UNSUPPORTED(method %r); known: auto, lzss (cecompress), lzx, lznt1, "
            "xpress-lz77, xpress-huffman" % method
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
# LZNT1 ([MS-XCA] 2.5): 4 KiB chunks, adaptive 4..12-bit displacement split
# --------------------------------------------------------------------------


def _lznt1_displacement_bits(produced):
    """Displacement bits of the next match word: ``max(4, bits(produced - 1))``.

    [MS-XCA] 2.5 splits the 16-bit match word into a displacement field in the
    high bits and a length field in the low bits, and the split grows with
    ``u``, the bytes already produced in the chunk.  The spec's pseudo-code
    starts at ``u - 1`` and halves it while it is ``>= 0x10`` (one step each),
    so a chunk uses 4 + 12 bits up to 16 produced bytes, 5 + 11 from 17, and the
    full 12 + 4 split from 2049 produced bytes (maximum length 18).  The 4 + 12
    split for ``u = 3`` and ``u = 9`` is what the spec's worked example shows,
    and that stream is decoded in ``--selftest``.
    """
    if produced <= 1:
        return LZNT1_MIN_DISPLACEMENT_BITS
    return min(
        LZNT1_MAX_DISPLACEMENT_BITS,
        max(LZNT1_MIN_DISPLACEMENT_BITS, (int(produced) - 1).bit_length()),
    )


def _lznt1_decode(data, expected_size=None, max_output=DEFAULT_MAX_OUTPUT):
    """Decode an LZNT1 stream; return ``(bytes, info)``."""
    out = bytearray()
    info = {
        "method": "lznt1",
        "input_size": len(data),
        "output_size": 0,
        "chunks": [],
        "compressed_chunks": 0,
        "stored_chunks": 0,
        "literals": 0,
        "matches": 0,
        "match_bytes": 0,
        "max_length": 0,
        "max_displacement": 0,
        "end_markers": 0,
        "trailing_bytes": 0,
        "trailing_zero": False,
    }
    i, n = 0, len(data)
    while i < n:
        if i + 2 > n:
            raise DecodeError(
                "lznt1: truncated chunk header at byte %d (%d byte(s) left)"
                % (i, n - i)
            )
        header = data[i] | (data[i + 1] << 8)
        if header == 0:
            # [MS-XCA] 2.5 and libfwnt: a zero chunk header ends the data.
            trailing = data[i:]
            info["trailing_bytes"] = len(trailing)
            info["trailing_zero"] = not any(trailing)
            break
        signature = (header >> 12) & 0x7
        if signature != LZNT1_SIGNATURE:
            raise DecodeError(
                "lznt1: chunk header 0x%04x at byte %d has signature %d, not %d "
                "(this is not an LZNT1 chunk)" % (header, i, signature,
                                                 LZNT1_SIGNATURE)
            )
        i += 2
        payload_len = (header & LZNT1_SIZE_MASK) + 1
        chunk_end = i + payload_len
        if chunk_end > n:
            raise DecodeError(
                "lznt1: chunk at byte %d declares %d payload byte(s), only %d "
                "left in the input" % (i - 2, payload_len, n - i)
            )
        chunk_out_start = len(out)
        compressed = bool(header & LZNT1_COMPRESSED)
        chunk = {
            "offset": i - 2,
            "payload_size": payload_len,
            "compressed": compressed,
            "output_size": 0,
            "end_marker": False,
        }

        if compressed:
            pos = i
            while pos < chunk_end:
                flags = data[pos]
                pos += 1
                for bit in range(8):
                    if pos >= chunk_end:
                        break
                    if flags & (1 << bit):
                        if pos + 2 > chunk_end:
                            raise DecodeError(
                                "lznt1: truncated match word at byte %d (chunk "
                                "ends at %d)" % (pos, chunk_end)
                            )
                        word = data[pos] | (data[pos + 1] << 8)
                        pos += 2
                        nbits = _lznt1_displacement_bits(
                            len(out) - chunk_out_start
                        )
                        length_bits = 16 - nbits
                        displacement_field = word >> length_bits
                        if (nbits == LZNT1_MAX_DISPLACEMENT_BITS
                                and displacement_field == LZNT1_END_MARKER):
                            chunk["end_marker"] = True
                            info["end_markers"] += 1
                            break
                        displacement = displacement_field + 1
                        length = ((word & ((1 << length_bits) - 1))
                                  + LZNT1_MIN_MATCH)
                        produced = len(out) - chunk_out_start
                        if displacement > produced:
                            raise DecodeError(
                                "lznt1: match at output %d refers %d byte(s) "
                                "back, before the start of its chunk (%d "
                                "byte(s) produced in this chunk)"
                                % (len(out), displacement, produced)
                            )
                        source = len(out) - displacement
                        for k in range(length):
                            out.append(out[source + k])
                        info["matches"] += 1
                        info["match_bytes"] += length
                        if length > info["max_length"]:
                            info["max_length"] = length
                        if displacement > info["max_displacement"]:
                            info["max_displacement"] = displacement
                    else:
                        out.append(data[pos])
                        pos += 1
                        info["literals"] += 1
                    if len(out) - chunk_out_start > LZNT1_CHUNK_SIZE:
                        raise DecodeError(
                            "lznt1: chunk at byte %d expands past the %d-byte "
                            "chunk limit" % (chunk["offset"], LZNT1_CHUNK_SIZE)
                        )
                if chunk["end_marker"]:
                    break
            info["compressed_chunks"] += 1
        else:
            out += data[i:chunk_end]
            info["stored_chunks"] += 1

        chunk["output_size"] = len(out) - chunk_out_start
        if chunk["output_size"] > LZNT1_CHUNK_SIZE:
            raise DecodeError(
                "lznt1: chunk at byte %d produced %d byte(s), more than the "
                "%d-byte chunk limit"
                % (chunk["offset"], chunk["output_size"], LZNT1_CHUNK_SIZE)
            )
        info["chunks"].append(chunk)
        i = chunk_end
        if len(out) > max_output:
            raise DecodeError(
                "lznt1: output exceeds the %d-byte limit" % max_output
            )

    info["output_size"] = len(out)
    if expected_size is not None and len(out) != expected_size:
        raise DecodeError(
            "lznt1: decoded %d bytes, expected %d" % (len(out), expected_size)
        )
    return bytes(out), info


def decompress_lznt1(data, expected_size=None, max_output=DEFAULT_MAX_OUTPUT):
    """Decode an LZNT1 stream; return bytes."""
    return _lznt1_decode(data, expected_size, max_output)[0]


def _lznt1_tokens(chunk, max_match=LZNT1_MAX_MATCH):
    """Greedy token list for one chunk; each item is literal or match tuple."""
    tokens = []
    index = {}
    n = len(chunk)

    def register(pos):
        if pos + LZNT1_MIN_MATCH <= n:
            index.setdefault(chunk[pos:pos + LZNT1_MIN_MATCH], []).append(pos)

    pos = 0
    while pos < n:
        best_length = 0
        best_displacement = 0
        if pos + LZNT1_MIN_MATCH <= n:
            limit = min(max_match, n - pos)
            for candidate in reversed(
                index.get(chunk[pos:pos + LZNT1_MIN_MATCH], ())
            ):
                displacement = pos - candidate
                if displacement > LZNT1_CHUNK_SIZE:
                    break
                length = LZNT1_MIN_MATCH
                while (length < limit
                       and chunk[candidate + length] == chunk[pos + length]):
                    length += 1
                if length > best_length:
                    best_length, best_displacement = length, displacement
                    if length == limit:
                        break
        if best_length >= LZNT1_MIN_MATCH:
            tokens.append(("match", best_length, best_displacement))
            for k in range(best_length):
                register(pos + k)
            pos += best_length
        else:
            tokens.append(("literal", chunk[pos]))
            register(pos)
            pos += 1
    return tokens


def _emit_lznt1_payload(tokens):
    """Serialise one chunk's token list into a compressed chunk payload."""
    out = bytearray()
    produced = 0
    index = 0
    while index < len(tokens):
        group = tokens[index:index + 8]
        flags_at = len(out)
        out.append(0)
        flags = 0
        for bit, token in enumerate(group):
            if token[0] == "match":
                _, length, displacement = token
                nbits = _lznt1_displacement_bits(produced)
                length_bits = 16 - nbits
                if ((displacement - 1) >> nbits
                        or (length - LZNT1_MIN_MATCH) >> length_bits):
                    raise AssertionError(
                        "lznt1 encoder: token (%d, %d) does not fit the %d+%d "
                        "split at output %d"
                        % (length, displacement, nbits, length_bits, produced)
                    )
                flags |= 1 << bit
                word = (((displacement - 1) << length_bits)
                        | (length - LZNT1_MIN_MATCH))
                out += bytes((word & 0xFF, word >> 8))
                produced += length
            else:
                out.append(token[1])
                produced += 1
        out[flags_at] = flags
        index += len(group)
    return bytes(out)


def encode_lznt1(data):
    """Reference LZNT1 encoder; **test-only** (used by ``--selftest``).

    Splits the input into 4096-byte chunks, encodes each with a greedy longest
    match (minimum 3, maximum 18, displacement at most the chunk) and stores a
    chunk verbatim when the compressed payload is not smaller.  It exists to
    prove that the decoder inverts the documented layout; it is not a writer.
    """
    out = bytearray()
    stats = {
        "chunks": 0,
        "compressed_chunks": 0,
        "stored_chunks": 0,
        "literals": 0,
        "matches": 0,
        "max_length": 0,
        "max_displacement": 0,
    }
    for start in range(0, len(data), LZNT1_CHUNK_SIZE):
        chunk = data[start:start + LZNT1_CHUNK_SIZE]
        tokens = _lznt1_tokens(chunk)
        payload = _emit_lznt1_payload(tokens)
        if len(payload) < len(chunk):
            header = (LZNT1_SIGNATURE_BITS | LZNT1_COMPRESSED
                      | (len(payload) - 1))
            body = payload
            stats["compressed_chunks"] += 1
            for token in tokens:
                if token[0] == "match":
                    stats["matches"] += 1
                    if token[1] > stats["max_length"]:
                        stats["max_length"] = token[1]
                    if token[2] > stats["max_displacement"]:
                        stats["max_displacement"] = token[2]
                else:
                    stats["literals"] += 1
        else:
            header = LZNT1_SIGNATURE_BITS | (len(chunk) - 1)
            body = chunk
            stats["stored_chunks"] += 1
        out += bytes((header & 0xFF, header >> 8))
        out += body
        stats["chunks"] += 1
    return bytes(out), stats


# --------------------------------------------------------------------------
# XPRESS skeletons ([MS-XCA] 2.3/2.4 plain LZ77; LZ77+Huffman)
# --------------------------------------------------------------------------


def _xpress_huffman_decode(data, expected_size=None,
                           max_output=DEFAULT_MAX_OUTPUT):
    """Parse the 512-symbol code-length table, then refuse to decode."""
    if len(data) < XPRESS_HUFFMAN_TABLE_BYTES:
        raise DecodeError(
            "xpress-huffman: %d byte(s) is shorter than the %d-byte code-length "
            "table" % (len(data), XPRESS_HUFFMAN_TABLE_BYTES)
        )
    lengths = []
    for byte in data[:XPRESS_HUFFMAN_TABLE_BYTES]:
        lengths.append(byte & 0x0F)         # low nibble: even symbol
        lengths.append(byte >> 4)           # high nibble: odd symbol
    kraft = 0
    zero_length = 0
    longest = 0
    for length in lengths:
        if length == 0:
            zero_length += 1
            continue
        if length > XPRESS_HUFFMAN_MAX_BITS:
            raise DecodeError(
                "xpress-huffman: code length %d exceeds the %d-bit maximum"
                % (length, XPRESS_HUFFMAN_MAX_BITS)
            )
        kraft += 1 << (XPRESS_HUFFMAN_MAX_BITS - length)
        if length > longest:
            longest = length
    capacity = 1 << XPRESS_HUFFMAN_MAX_BITS
    if kraft > capacity:
        raise DecodeError(
            "xpress-huffman: symbol table is over-subscribed (Kraft %d > %d)"
            % (kraft, capacity)
        )
    raise UnsupportedFormat(
        "UNSUPPORTED(xpress-huffman: %d-symbol code-length table parsed (Kraft "
        "%d/%d, longest code %d bit(s), %d zero-length symbol(s)); the "
        "Huffman-coded token stream is not implemented)"
        % (XPRESS_HUFFMAN_SYMBOLS, kraft, capacity, longest, zero_length)
    )


def _xpress_lz77_decode(data, expected_size=None, max_output=DEFAULT_MAX_OUTPUT):
    """Decode an XPRESS plain LZ77 stream; return ``(bytes, info)``.

    Port of the klauspost/compress (Go) plain LZ77 decoder. Self-terminating.
    """
    out = bytearray()
    base = 0
    pending_len = -1
    flags = 0
    flags_left = 0
    i = 0
    n = len(data)
    literals = 0
    matches = 0
    match_bytes = 0
    max_length = 0
    max_offset = 0

    while True:
        if flags_left == 0:
            if i == n:
                break
            if n - i < 4:
                raise DecodeError(
                    "xpress-lz77: truncated flags at byte %d" % i
                )
            flags = int.from_bytes(data[i:i + 4], "little")
            i += 4
            flags_left = 32

        flags_left -= 1
        if (flags >> flags_left) & 1 == 0:
            if i >= n:
                raise DecodeError(
                    "xpress-lz77: truncated literal at byte %d" % i
                )
            out.append(data[i])
            i += 1
            literals += 1
            if len(out) - base > max_output:
                raise DecodeError("xpress-lz77: output exceeds limit")
            continue

        # set bit => match; no input left => end-of-data
        if i >= n:
            break
        if n - i < 2:
            raise DecodeError("xpress-lz77: truncated match at byte %d" % i)
        mb = int.from_bytes(data[i:i + 2], "little")
        i += 2
        moff = (mb >> 3) + 1
        mlen = (mb & 7) + 3

        if (mb & 7) == 7:
            if pending_len == -1:
                if i >= n:
                    raise DecodeError("xpress-lz77: truncated nibble at byte %d" % i)
                nib = data[i] & 0x0F
                pending_len = i
                i += 1
            else:
                nib = (data[pending_len] >> 4) & 0x0F
                pending_len = -1
            if nib == 15:
                if i >= n:
                    raise DecodeError("xpress-lz77: truncated raw length at byte %d" % i)
                v = data[i]
                i += 1
                if v == 255:
                    if n - i < 2:
                        raise DecodeError("xpress-lz77: truncated u16 length")
                    v = int.from_bytes(data[i:i + 2], "little")
                    i += 2
                    if v == 0:
                        if n - i < 4:
                            raise DecodeError("xpress-lz77: truncated u32 length")
                        v = int.from_bytes(data[i:i + 4], "little")
                        i += 4
                    if v < 15 + 7:
                        raise DecodeError("xpress-lz77: corrupt raw length")
                    if v > max_output:
                        raise DecodeError("xpress-lz77: too large")
                    mlen = int(v) + 3
                else:
                    mlen = int(v) + 25
            else:
                mlen = nib + 10

        if mlen > max_output - (len(out) - base):
            raise DecodeError("xpress-lz77: too large")
        if moff > len(out) - base:
            raise DecodeError("xpress-lz77: corrupt offset (moff %d > %d)" % (moff, len(out) - base))
        start = len(out) - moff
        for j in range(mlen):
            out.append(out[start + j])
        matches += 1
        match_bytes += mlen
        if mlen > max_length:
            max_length = mlen
        if moff > max_offset:
            max_offset = moff

    info = {
        "method": "xpress-lz77",
        "input_size": len(data),
        "output_size": len(out),
        "literals": literals,
        "matches": matches,
        "match_bytes": match_bytes,
        "max_length": max_length,
        "max_offset": max_offset,
    }
    if expected_size is not None and len(out) != expected_size:
        raise DecodeError(
            "xpress-lz77: decoded %d bytes, expected %d" % (len(out), expected_size)
        )
    return bytes(out), info


def decompress_xpress_huffman(data, expected_size=None,
                              max_output=DEFAULT_MAX_OUTPUT):
    """Never returns bytes: raises `UnsupportedFormat` after the header check."""
    _xpress_huffman_decode(data, expected_size, max_output)


def decompress_xpress_lz77(data, expected_size=None,
                           max_output=DEFAULT_MAX_OUTPUT):
    """Decode an XPRESS plain LZ77 stream; return bytes."""
    return _xpress_lz77_decode(data, expected_size, max_output)[0]



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
    elif name == "lzx":
        blob, info = _lzx_decode(data, expected_size, window_bits,
                                 e8_translation, max_output)
    elif name == "lznt1":
        blob, info = _lznt1_decode(data, expected_size, max_output)
    elif name == "xpress-lz77":
        blob, info = _xpress_lz77_decode(data, expected_size, max_output)
    else:
        blob, info = _xpress_huffman_decode(data, expected_size, max_output)
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

    ``method`` is ``"auto"`` (default), ``"lzss"``/``"cecompress"``,
    ``"lzx"``, ``"lznt1"``, ``"xpress-lz77"`` or ``"xpress-huffman"``.  Raises
    `UnsupportedFormat` when the method cannot be chosen or the format is not
    implemented (the two XPRESS variants are skeletons), and `DecodeError` when
    the stream is corrupt or the output length differs from ``expected_size``.
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
# Probe runner (TODO M1.2b): every method × every offset, exact length only
# --------------------------------------------------------------------------


def _offset_int(text):
    """Parse one offset: decimal, ``0x``-hex or ``0o``-octal like ``int(s, 0)``."""
    text = str(text).strip()
    try:
        return int(text, 0)
    except ValueError:
        return int(text, 10)


def parse_offsets(text, limit=1 << 20):
    """Parse ``0-32``, ``0,22,24`` or a mix into a sorted list of offsets."""
    offsets = set()
    for part in str(text).replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part[1:]:
            low_text, high_text = part.split("-", 1)
            low, high = _offset_int(low_text), _offset_int(high_text)
            if high < low:
                raise ValueError("offset range %r is reversed" % part)
            if high - low + 1 > limit:
                raise ValueError(
                    "offset range %r covers %d offsets (limit %d)"
                    % (part, high - low + 1, limit)
                )
            offsets.update(range(low, high + 1))
        else:
            offsets.add(_offset_int(part))
    if not offsets:
        raise ValueError("no offsets given")
    if min(offsets) < 0:
        raise ValueError("offsets must not be negative")
    return sorted(offsets)


def parse_methods(text):
    """Parse ``--methods``: a comma list of names, ``all``/``*`` or ``None``."""
    if text is None or not str(text).strip():
        return list(PROBE_METHODS)
    if str(text).strip().lower() in ("all", "*"):
        return list(PROBE_METHODS)
    names = []
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        name = normalise_method(part)
        if name == "auto":
            raise UnsupportedFormat(
                "probe needs explicit methods, not 'auto' (it would hide which "
                "decoder matched)"
            )
        if name not in names:
            names.append(name)
    if not names:
        raise ValueError("no methods given")
    return names


def content_evidence(blob, scan_bytes=1 << 20):
    """Cheap plausibility counters for a decoded section (evidence, not proof).

    The counters are what M1.2b asks for beyond the length: pointers into the
    ``0x8c…0x8e`` module-VA band, ASCII runs, printable ratio.  None of them
    proves a decode; they only make a lucky length match easy to dismiss.
    """
    total = len(blob)
    printable = sum(1 for byte in blob if 32 <= byte < 127 or byte in (9, 10, 13))
    runs = 0
    run = 0
    for byte in blob:
        if 32 <= byte < 127:
            run += 1
        else:
            if run >= 6:
                runs += 1
            run = 0
    if run >= 6:
        runs += 1
    scan = min(total, scan_bytes)
    va_words = 0
    for index in range(scan - 3):
        if blob[index + 3] in (0x8C, 0x8D, 0x8E):
            word = int.from_bytes(blob[index:index + 4], "little")
            if 0x8C000000 <= word < 0x8E400000:
                va_words += 1
    return {
        "sha256": hashlib.sha256(blob).hexdigest(),
        "size": total,
        "first_bytes": blob[:32].hex(),
        "printable_ratio": round(printable / total, 3) if total else 0.0,
        "ascii_runs_6plus": runs,
        "va_words_0x8c_0x8e": va_words,
        "va_scan_bytes": scan,
    }


def probe(data, expected_size=None, offsets=None, methods=None,
          max_output=DEFAULT_MAX_OUTPUT):
    """Try every method at every offset; report exact-length matches.

    ``offsets`` defaults to ``0..32`` (TODO M1.2b: the payload offset is
    unknown until M1.2a lands), ``methods`` to `PROBE_METHODS`.  Every
    combination gets one record with a status of ``match`` (decoded length ==
    ``expected_size``), ``wrong-size``, ``no-size`` (no ``expected_size``),
    ``unsupported`` (the decoder refused, e.g. an unimplemented XPRESS
    variant), ``error`` (the stream claimed the format but is corrupt) or
    ``empty-input``/``out-of-range``.  Nothing is guessed: a refusal is copied
    into ``error`` verbatim, and only an exact length match lands in
    ``matches``.
    """
    if offsets is None:
        offsets = range(0, 33)
    if methods is None:
        methods = PROBE_METHODS
    offsets = sorted(int(offset) for offset in offsets)
    methods = [normalise_method(name) for name in methods]
    report = {
        "input_size": len(data),
        "input_sha256": hashlib.sha256(data).hexdigest(),
        "expected_size": expected_size,
        "offsets": offsets,
        "methods": methods,
        "attempts": [],
        "matches": [],
        "matched": False,
        "notes": [],
    }
    if expected_size is None:
        report["notes"].append(
            "no expected_size: a match needs the section's o32_vsize (--size); "
            "output lengths are reported but nothing can be confirmed"
        )
    for offset in offsets:
        if offset < 0 or offset > len(data):
            for method in methods:
                report["attempts"].append({
                    "offset": offset,
                    "method": method,
                    "status": "out-of-range",
                    "output_size": None,
                    "expected_size": expected_size,
                    "error": "offset %d is past the end of the %d-byte input"
                             % (offset, len(data)),
                })
            continue
        window = data[offset:]
        for method in methods:
            record = {
                "offset": offset,
                "method": method,
                "status": None,
                "output_size": None,
                "expected_size": expected_size,
                "error": None,
            }
            if not window:
                record["status"] = "empty-input"
                record["error"] = "no input bytes at offset %d" % offset
                report["attempts"].append(record)
                continue
            try:
                blob, _info = decompress_info(window, None, method,
                                              max_output=max_output)
            except UnsupportedFormat as exc:
                record["status"] = "unsupported"
                record["error"] = str(exc)
            except DecodeError as exc:
                record["status"] = "error"
                record["error"] = str(exc)
            else:
                record["output_size"] = len(blob)
                if expected_size is None:
                    record["status"] = "no-size"
                elif len(blob) == expected_size:
                    record["status"] = "match"
                    record["evidence"] = content_evidence(blob)
                    report["matches"].append({
                        "offset": offset,
                        "method": method,
                        "output_size": len(blob),
                        "sha256": record["evidence"]["sha256"],
                        "evidence": record["evidence"],
                    })
                else:
                    record["status"] = "wrong-size"
                    record["error"] = (
                        "decoded %d bytes, expected %d"
                        % (len(blob), expected_size)
                    )
            report["attempts"].append(record)
    report["matched"] = bool(report["matches"])
    return report


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

    # --- LZNT1: the [MS-XCA] 2.5 worked example (a real spec vector) --------
    lznt1_spec = bytes.fromhex(
        "38b0884623200020 4720410010a24701 a045204400084501 "
        "507900c045200524 138805b4024a44ef 0358028c09160148 "
        "4500be009e000401 189000"
    )
    lznt1_spec_text = (
        b"F# F# G A A G F# E D D E F# F# E E F# F# G A A G F# E D D E F# "
        b"E D D E E F# D E F# G F# D E F# G F# E D E A F# F# G A A G F# E "
        b"D D E F# E D D"
    )
    ok("lznt1 spec vector: 142-byte string plus NUL", len(lznt1_spec_text) + 1, 142)
    lznt1_spec_blob, lznt1_spec_info = _lznt1_decode(lznt1_spec)
    ok("lznt1 spec vector: decoded bytes", lznt1_spec_blob,
       lznt1_spec_text + b"\x00")
    ok("lznt1 spec vector: header field 56 = 57-byte payload",
       lznt1_spec_info["chunks"][0]["payload_size"], 57)
    ok("lznt1 spec vector: one compressed chunk",
       (len(lznt1_spec_info["chunks"]),
        lznt1_spec_info["chunks"][0]["compressed"]), (1, True))
    ok("lznt1 spec vector: matches decoded",
       lznt1_spec_info["matches"] > 0, True)

    # --- LZNT1: encoder/decoder symmetry over the usual corpora ------------
    for label, plain in corpora:
        lznt1_stream, enc = encode_lznt1(plain)
        blob, info = _lznt1_decode(lznt1_stream)
        ok("lznt1 round-trip: %s" % label, blob, plain)
        ok("lznt1 output size: %s" % label, len(blob), len(plain))
        ok("lznt1 chunk count: %s" % label, len(info["chunks"]), enc["chunks"])
        ok("lznt1 compressed+stored chunks: %s" % label,
           info["compressed_chunks"] + info["stored_chunks"], enc["chunks"])
        ok("lznt1 stored chunk count: %s" % label,
           info["stored_chunks"], enc["stored_chunks"])
        ok("lznt1 max length bound: %s" % label,
           info["max_length"] <= LZNT1_MAX_MATCH, True)
        ok("lznt1 max displacement bound: %s" % label,
           info["max_displacement"] <= LZNT1_CHUNK_SIZE, True)
        if enc["stored_chunks"] == 0:
            ok("lznt1 literal count: %s" % label, info["literals"], enc["literals"])
            ok("lznt1 match count: %s" % label, info["matches"], enc["matches"])
            ok("lznt1 max length: %s" % label, info["max_length"], enc["max_length"])
            ok("lznt1 max displacement: %s" % label,
               info["max_displacement"], enc["max_displacement"])
    ok("lznt1 max match length reached",
       encode_lznt1(b"ABCDEFGHIJKLMNOPQR" * 40)[1]["max_length"], LZNT1_MAX_MATCH)
    ok("lznt1 incompressible input falls back to stored chunks",
       encode_lznt1(_lcg_bytes(31, 4096))[1]["stored_chunks"], 1)

    # Chunk boundary: 4096 + 4096 + 4 bytes must encode as three chunks, and
    # a match may not reference data from an earlier chunk.
    boundary = (_lcg_bytes(21, LZNT1_CHUNK_SIZE)
                + _lcg_bytes(22, LZNT1_CHUNK_SIZE) + b"tail")
    boundary_stream, boundary_stats = encode_lznt1(boundary)
    boundary_blob, boundary_info = _lznt1_decode(boundary_stream)
    ok("lznt1 chunk boundary: round-trip", boundary_blob, boundary)
    ok("lznt1 chunk boundary: three chunks", boundary_stats["chunks"], 3)
    ok("lznt1 chunk boundary: decoded chunk count",
       len(boundary_info["chunks"]), 3)
    ok("lznt1 chunk boundary: per-chunk output sizes",
       [c["output_size"] for c in boundary_info["chunks"]],
       [LZNT1_CHUNK_SIZE, LZNT1_CHUNK_SIZE, 4])
    single_literal = (
        (LZNT1_SIGNATURE_BITS | LZNT1_COMPRESSED | 1).to_bytes(2, "little")
        + bytes([0x00, ord("A")])
    )
    back_reference = (
        (LZNT1_SIGNATURE_BITS | LZNT1_COMPRESSED | 2).to_bytes(2, "little")
        + bytes([0x01, 0x00, 0x00])
    )
    exc = raises(DecodeError, "lznt1 chunks are independent",
                 decompress_lznt1, single_literal + back_reference)
    ok("lznt1 cross-chunk refusal message",
       "start of its chunk" in str(exc), True)
    ok("lznt1 cross-chunk prefix alone decodes",
       decompress_lznt1(single_literal), b"A")

    # The 0x0FFF terminator: only reachable at 12 displacement bits, i.e. once
    # more than 2048 bytes have been produced in the chunk.  It is the
    # displacement field 0xFFF (word 0xFFFn at the 12 + 4 split), not the bare
    # word 0x0FFF.
    marker_literals = _lcg_bytes(5, 2049)

    def lznt1_literal_chunk_upto_2049(token, padding=3):
        body = bytearray()
        for start in range(0, 2048, 8):
            body.append(0)                      # eight literals per flag byte
            body += marker_literals[start:start + 8]
        # Flag 0b10: bit 0 is the 2049th literal, bit 1 is the match word (the
        # remaining bits are never reached once the match ends the chunk).
        body += bytes([0b00000010, marker_literals[2048]]) + token
        body += b"\x00" * padding               # padding to the chunk end
        return body

    marker_body = lznt1_literal_chunk_upto_2049(bytes([0xF0, 0xFF]))   # 0xFFF0
    marker_stream = (
        (LZNT1_SIGNATURE_BITS | LZNT1_COMPRESSED
         | (len(marker_body) - 1)).to_bytes(2, "little")
        + bytes(marker_body)
        + (LZNT1_SIGNATURE_BITS | 3).to_bytes(2, "little")
        + b"ZZZZ"
    )
    marker_blob, marker_info = _lznt1_decode(marker_stream)
    ok("lznt1 0x0FFF terminator: chunk stops at the marker",
       (len(marker_blob), marker_blob[-4:]), (2053, b"ZZZZ"))
    ok("lznt1 0x0FFF terminator: payload before it is intact",
       marker_blob[:2049], marker_literals)
    ok("lznt1 0x0FFF terminator counted", marker_info["end_markers"], 1)
    ok("lznt1 0x0FFF terminator is not a 4096-byte look-back",
       marker_info["max_displacement"] <= 2049, True)
    ok("lznt1 0x0FFF terminator: second chunk decoded",
       [c["compressed"] for c in marker_info["chunks"]], [True, False])
    # The bare word 0x0FFF is distance 256, length 18 at the 12 + 4 split, and
    # the same word below 12 displacement bits is a length past the chunk.
    bare_body = lznt1_literal_chunk_upto_2049(bytes([0xFF, 0x0F]), padding=0)
    bare_stream = (
        (LZNT1_SIGNATURE_BITS | LZNT1_COMPRESSED
         | (len(bare_body) - 1)).to_bytes(2, "little")
        + bytes(bare_body)
    )
    bare_blob, bare_info = _lznt1_decode(bare_stream)
    ok("lznt1 bare word 0x0FFF is a match, not the marker",
       (len(bare_blob), bare_info["end_markers"],
        bare_info["max_displacement"], bare_info["max_length"]),
       (2067, 0, 256, 18))
    exc = raises(DecodeError, "lznt1 displacement past the chunk start rejected",
                 decompress_lznt1,
                 (LZNT1_SIGNATURE_BITS | LZNT1_COMPRESSED | 3).to_bytes(2, "little")
                 + bytes([0b00000010, ord("Q"), 0xF0, 0xFF]))
    ok("lznt1 displacement refusal message",
       "before the start of its chunk" in str(exc), True)
    exc = raises(DecodeError, "lznt1 oversized match rejected",
                 decompress_lznt1,
                 (LZNT1_SIGNATURE_BITS | LZNT1_COMPRESSED | 3).to_bytes(2, "little")
                 + bytes([0b00000010, ord("Q"), 0xFF, 0x0F]))
    ok("lznt1 oversized chunk refusal message",
       "chunk limit" in str(exc), True)

    # LZNT1 negatives: never partial or invented bytes.
    exc = raises(DecodeError, "lznt1 bad signature rejected",
                 decompress_lznt1, (0x2000 | 3).to_bytes(2, "little") + b"abc")
    ok("lznt1 bad signature message", "signature 2" in str(exc), True)
    exc = raises(DecodeError, "lznt1 truncated header rejected",
                 decompress_lznt1, b"\x38")
    ok("lznt1 truncated header message", "truncated chunk header" in str(exc), True)
    exc = raises(DecodeError, "lznt1 payload past the end rejected",
                 decompress_lznt1,
                 (LZNT1_SIGNATURE_BITS | LZNT1_COMPRESSED | 100).to_bytes(2, "little")
                 + b"\x00" * 10)
    ok("lznt1 payload past the end message",
       "declares 101 payload byte(s)" in str(exc), True)
    exc = raises(DecodeError, "lznt1 zero signature mid-stream rejected",
                 decompress_lznt1, single_literal + b"\x00\x01")
    ok("lznt1 zero signature message", "signature 0" in str(exc), True)
    ok("lznt1 zero header ends the data",
       decompress_lznt1(single_literal + b"\x00\x00\x00\x00"), b"A")
    ok("lznt1 zero-header trailing bytes reported",
       _lznt1_decode(single_literal + b"\x00\x00\x00\x00")[1]["trailing_bytes"], 4)
    ok("lznt1 zero-header padding is flagged as zero",
       _lznt1_decode(single_literal + b"\x00\x00\x00\x00")[1]["trailing_zero"], True)
    ok("lznt1 non-zero bytes after a zero header are reported, not decoded",
       _lznt1_decode(single_literal + b"\x00\x00junk", )[:1], (b"A",))
    raises(DecodeError, "lznt1 expected_size mismatch rejected",
           decompress_lznt1, single_literal, 4)
    ok("lznt1 empty input decodes to empty",
       _lznt1_decode(b"")[0], b"")
    ok("lznt1 alias works",
       decompress(encode_lznt1(b"abcabcabc")[0], 9, "ntfs-lznt1"), b"abcabcabc")

    # --- XPRESS skeletons: parse the header, then refuse with the reason ----
    huffman_table = bytes([0x99]) * 256         # 512 symbols x 9 bits: Kraft 2^15
    exc = raises(UnsupportedFormat, "xpress-huffman refuses after the table",
                 decompress, huffman_table + b"\x00" * 16, None, "xpress-huffman")
    ok("xpress-huffman refusal names the sub-format",
       str(exc).startswith("UNSUPPORTED(xpress-huffman:"), True)
    ok("xpress-huffman refusal reports the parsed table",
       "Kraft 32768/32768" in str(exc), True)
    ok("xpress-huffman refusal says what is missing",
       "not implemented" in str(exc), True)
    exc = raises(DecodeError, "xpress-huffman short table rejected",
                 decompress, b"\x99" * 200, None, "xpress-huffman")
    ok("xpress-huffman short table message",
       "shorter than the 256-byte" in str(exc), True)
    exc = raises(DecodeError, "xpress-huffman over-subscribed table rejected",
                 decompress, bytes([0x11]) * 256 + b"\x00" * 16, None,
                 "xpress-huffman")
    ok("xpress-huffman over-subscribed message",
       "over-subscribed" in str(exc), True)
    # xpress-lz77 is now implemented (M1.2b): a truncated stream raises DecodeError.
    exc = raises(DecodeError, "xpress-lz77 truncated stream rejected",
                 decompress, b"\x00\x00\x00\x00literal", None, "lz77")
    ok("xpress-lz77 truncated message names the sub-format",
       str(exc).startswith("xpress-lz77:"), True)
    exc2 = decompress(b"\x00\x00\x00\x00" + b"A" * 32 + b"\x00\x00\x00\x80", None, "lz77")
    ok("xpress-lz77 decodes 32 literals + end marker",
       exc2 == b"A" * 32, True)
    raises(DecodeError, "xpress-lz77 shorter than one DWORD rejected",
           decompress, b"\x00\x00", None, "xpress-lz77")
    # xpress-huffman is still a skeleton (refuses); xpress-lz77 is now implemented.
    for method in ("xpress-huffman",):
        for sample in (b"", b"\x00", b"\xff" * 300):
            try:
                decompress(sample, None, method)
            except CeCompressError:
                pass
            else:
                raise AssertionError(
                    "%s returned bytes for %r; skeletons must refuse"
                    % (method, sample[:8])
                )
    checks.append("xpress-huffman skeleton refuses instead of guessing")

    # --- probe: a hidden LZSS stream behind a 22-byte prefix ----------------
    probe_plain = b"ZE0 probe payload " * 40
    probe_lzss = encode_lzss(probe_plain)[0]
    probe_prefix = b"\x01\x00\x00" + b"section-hdr" + bytes(8)
    ok("probe fixture: 22-byte prefix", len(probe_prefix), 22)
    probe_file = probe_prefix + probe_lzss
    probe_report = probe(probe_file, len(probe_plain), range(0, 33))
    ok("probe finds the hidden LZSS stream", probe_report["matched"], True)
    ok("probe match list",
       [(m["method"], m["offset"]) for m in probe_report["matches"]],
       [("lzss", 22)])
    ok("probe attempt count", len(probe_report["attempts"]),
       len(PROBE_METHODS) * 33)
    probe_status = {
        (attempt["offset"], attempt["method"]): attempt["status"]
        for attempt in probe_report["attempts"]
    }
    ok("probe lzss at offset 0 fails before the payload",
       probe_status[(0, "lzss")], "error")
    ok("probe statuses are from the documented set",
       set(probe_status.values()) - {"match", "wrong-size", "no-size",
                                     "unsupported", "error"}, set())
    ok("probe skips methods that cannot start there",
       probe_status[(0, "xpress-huffman")] in ("unsupported", "error"), True)
    ok("probe match evidence sha256",
       probe_report["matches"][0]["sha256"],
       hashlib.sha256(probe_plain).hexdigest())
    ok("probe match evidence first bytes",
       probe_report["matches"][0]["evidence"]["first_bytes"],
       probe_plain[:32].hex())
    wrong_size = probe(probe_file, len(probe_plain) + 1, range(0, 33))
    ok("probe with a wrong size finds no match", wrong_size["matched"], False)
    ok("probe with a wrong size reports no matches", wrong_size["matches"], [])
    no_size = probe(probe_file, None, [22], ["lzss"])
    ok("probe without a size reports no-size",
       no_size["attempts"][0]["status"], "no-size")
    ok("probe without a size explains itself",
       "no expected_size" in no_size["notes"][0], True)
    xpress_probe = probe(probe_file, len(probe_plain), [22],
                         ["xpress-lz77", "xpress-huffman"])
    ok("probe xpress-lz77 is implemented (no longer unsupported)",
       xpress_probe["attempts"][0]["status"] in ("match", "mismatch", "error"), True)
    ok("probe xpress-huffman never matches",
       xpress_probe["attempts"][1]["status"] in ("unsupported", "error"), True)
    ok("probe xpress attempts explain themselves",
       all(attempt["error"] and "xpress" in attempt["error"]
           for attempt in xpress_probe["attempts"]), True)
    out_of_range = probe(b"abc", 3, [10], ["lzss"])
    ok("probe reports an offset past the end",
       out_of_range["attempts"][0]["status"], "out-of-range")
    ok("probe offset parsing", parse_offsets("0-2,5,0x10"), [0, 1, 2, 5, 16])
    try:
        parse_offsets("5-1")
    except ValueError:
        checks.append("probe rejects a reversed offset range")
    else:
        raise AssertionError("probe must reject a reversed offset range")
    try:
        parse_methods("auto")
    except CeCompressError:
        checks.append("probe rejects the auto method")
    else:
        raise AssertionError("probe must reject 'auto'")
    ok("_format_offsets compresses ranges", _format_offsets([0, 1, 2, 5, 16]),
       "0-2, 5, 16")

    evidence = content_evidence(b"ABC" * 10)
    ok("evidence sha256", evidence["sha256"], hashlib.sha256(b"ABC" * 10).hexdigest())
    ok("evidence size", evidence["size"], 30)
    ok("evidence printable ratio", evidence["printable_ratio"], 1.0)
    ok("evidence ascii runs", evidence["ascii_runs_6plus"], 1)
    va_bytes = bytearray(8)
    struct.pack_into("<I", va_bytes, 0, 0x8CAE1000)
    struct.pack_into("<I", va_bytes, 4, 0x12345678)
    ok("evidence counts module-VA words",
       content_evidence(bytes(va_bytes))["va_words_0x8c_0x8e"], 1)

    # --- Corrupt-input sweep: every truncation of a valid stream, plus the same
    # truncation with one bogus 0xFF byte appended, under all three method
    # settings, must raise CeCompressError or decode; a raw exception would mean
    # the CLI could crash on a bad section.
    sweeps = [
        (encode_lzss(b"hello hello hello world " * 40)[0], ("lzss", "lzx", "auto")),
        (_build_lzx_stored([b"payload " * 50]), ("lzss", "lzx", "auto")),
        (encode_lznt1(b"hello hello hello world " * 40)[0], ("lznt1", "auto")),
    ]
    cases = 0
    expected_cases = 0
    for base, methods in sweeps:
        for cut in range(len(base)):
            for mutated in (base[:cut], base[:cut] + b"\xff"):
                for method in methods:
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
    for base, methods in sweeps:
        expected_cases += 2 * len(methods) * len(base)
    ok("corrupt-input sweep cases", cases, expected_cases)
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

        # probe: a 22-byte prefix in front of a real LZSS stream.
        probe_path = os.path.join(tmp, "section.bin")
        with open(probe_path, "wb") as handle:
            handle.write(probe_file)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli probe --json exit",
               main(["probe", probe_path, "--size", str(len(probe_plain)),
                     "--offsets", "20-24", "--json"]), 0)
        report = json.loads(buf.getvalue())
        ok("cli probe --json matched", report["matched"], True)
        ok("cli probe --json keys", sorted(report),
           ["attempts", "expected_size", "input_sha256", "input_size", "matched",
            "matches", "methods", "notes", "offsets"])
        ok("cli probe --json match offset", report["matches"][0]["offset"], 22)
        ok("cli probe --json attempt count", len(report["attempts"]),
           len(PROBE_METHODS) * 5)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli probe text exit",
               main(["probe", probe_path, "--size", str(len(probe_plain)),
                     "--offsets", "22"]), 0)
        ok("cli probe text names the match",
           "match     lzss @22" in buf.getvalue(), True)
        ok("cli probe text summary", "1 match(es)" in buf.getvalue(), True)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli probe no-match exit",
               main(["probe", probe_path, "--size", "17", "--offsets", "22"]), 1)
        ok("cli probe no-match summary", "0 match(es)" in buf.getvalue(), True)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok("cli probe without --size exit",
               main(["probe", probe_path, "--offsets", "22", "--json"]), 1)
        ok("cli probe without --size note",
           "no expected_size" in json.loads(buf.getvalue())["notes"][0], True)

        cases = [
            ("missing file", ["probe", os.path.join(tmp, "nope"), "--size", "1"]),
            ("reversed offsets", ["probe", probe_path, "--size", "1",
                                  "--offsets", "5-1"]),
            ("bad offsets", ["probe", probe_path, "--size", "1", "--offsets", "x"]),
            ("unknown method", ["probe", probe_path, "--size", "1",
                                "--methods", "lzma"]),
            ("auto method", ["probe", probe_path, "--size", "1",
                             "--methods", "auto"]),
        ]
        for label, argv in cases:
            err = io.StringIO()
            with contextlib.redirect_stderr(err), \
                    contextlib.redirect_stdout(io.StringIO()):
                ok("cli probe %s exit 2" % label, main(argv), 2)
            ok("cli probe %s message" % label, "error:" in err.getvalue(), True)

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


def _format_offsets(offsets):
    """Compress a sorted offset list into ``0-32``-style ranges for the CLI."""
    if not offsets:
        return "(none)"
    parts = []
    start = previous = offsets[0]
    for offset in offsets[1:]:
        if offset == previous + 1:
            previous = offset
            continue
        parts.append("%d" % start if start == previous else "%d-%d" % (start, previous))
        start = previous = offset
    parts.append("%d" % start if start == previous else "%d-%d" % (start, previous))
    return ", ".join(parts)


def _format_probe_attempt(attempt):
    if attempt["status"] == "match":
        detail = "out %d B sha256 %s" % (
            attempt["output_size"],
            attempt.get("evidence", {}).get("sha256", ""),
        )
    else:
        detail = attempt.get("error") or ""
        if attempt["output_size"] is not None:
            detail = "out %d B%s" % (
                attempt["output_size"], "; " + detail if detail else ""
            )
    return "  @%-3d %-16s %-12s %s" % (
        attempt["offset"], attempt["method"], attempt["status"], detail
    )


def probe_command(args):
    try:
        with open(args.file, "rb") as handle:
            data = handle.read()
        offsets = parse_offsets(args.offsets)
        methods = parse_methods(args.methods)
    except (OSError, ValueError, CeCompressError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    report = probe(data, args.size, offsets, methods, args.max_output)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if report["matched"] else 1

    print("file      %s" % args.file)
    print("input     %d bytes (sha256 %s)"
          % (report["input_size"], report["input_sha256"]))
    if report["expected_size"] is None:
        print("expect    (none: a match needs --size, the section's o32_vsize)")
    else:
        print("expect    %d bytes" % report["expected_size"])
    print("methods   %s" % ", ".join(report["methods"]))
    print("offsets   %s (%d)" % (_format_offsets(report["offsets"]),
                                 len(report["offsets"])))
    print("")
    for attempt in report["attempts"]:
        print(_format_probe_attempt(attempt))
    print("")
    for match in report["matches"]:
        evidence = match["evidence"]
        print("match     %s @%d: %d bytes, sha256 %s"
              % (match["method"], match["offset"], match["output_size"],
                 match["sha256"]))
        print("          first 32 bytes %s" % evidence["first_bytes"])
        print("          printable %.3f, ascii runs>=6 %d, VA words "
              "0x8c..0x8e %d (of %d byte(s) scanned)"
              % (evidence["printable_ratio"], evidence["ascii_runs_6plus"],
                 evidence["va_words_0x8c_0x8e"], evidence["va_scan_bytes"]))
    for note in report["notes"]:
        print("note      %s" % note)
    print("%d match(es) in %d attempt(s): %d offset(s) x %d method(s)"
          % (len(report["matches"]), len(report["attempts"]),
             len(report["offsets"]), len(report["methods"])))
    return 0 if report["matched"] else 1


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
                   help="auto (default), lzss/cecompress, lzx, lznt1, "
                        "xpress-lz77 or xpress-huffman (skeletons: always "
                        "UNSUPPORTED)")
    p.add_argument("--size", type=_hex_or_int, default=None,
                   help="expected output size (o32_vsize); mismatches are errors")
    p.add_argument("--window-bits", type=int, default=LZX_DEFAULT_WINDOW_BITS,
                   help="LZX window size (default 15 = 32 KiB)")
    p.add_argument("--e8-translation", action="store_true",
                   help="apply the LZX E8 post-processing (off by default)")
    p.add_argument("--max-output", type=_hex_or_int, default=DEFAULT_MAX_OUTPUT,
                   help="refuse to produce more than this many bytes")
    p.add_argument("--json", action="store_true", help="machine-readable output")

    p = sub.add_parser("probe", help="try every method at every offset and "
                                     "report exact-length matches (M1.2b)")
    p.add_argument("file")
    p.add_argument("--size", type=_hex_or_int, default=None,
                   help="expected output size (o32_vsize); only an exact match "
                        "counts, and without it nothing can match")
    p.add_argument("--offsets", default="0-32",
                   help="offsets to try: '0-32' (default), '0,22,24', '0x16'")
    p.add_argument("--methods", default=None,
                   help="comma list: %s, or 'all' (default)"
                        % ", ".join(PROBE_METHODS))
    p.add_argument("--max-output", type=_hex_or_int, default=DEFAULT_MAX_OUTPUT,
                   help="refuse an attempt that would produce more than this")
    p.add_argument("--json", action="store_true", help="machine-readable output")

    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd is None:
        ap.error("a subcommand is required (detect, decompress, probe) or "
                 "--selftest")
    if args.cmd == "probe":
        return probe_command(args)
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
