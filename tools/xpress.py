#!/usr/bin/env python3
"""XPRESS (MS-XCA) plain LZ77 decompressor (M1.2b).

Implements the plain LZ77 variant of [MS-XCA] as documented by the
klauspost/compress reference (xpress.go). The stream is self-terminating.

Stdlib only. Synthetic self-test uses crafted control streams.
"""

from __future__ import annotations

import struct
import sys


MAX_SIZE = 32 << 20


def decompress_plain(data: bytes) -> bytes:
    out = bytearray()
    base = 0
    pending_len = -1  # offset of shared-nibble byte, -1 if none pending
    flags = 0
    flags_left = 0
    i = 0
    n = len(data)

    while True:
        if flags_left == 0:
            if i == n:
                return bytes(out)
            if n - i < 4:
                raise ValueError("truncated flags")
            flags = struct.unpack_from("<I", data, i)[0]
            i += 4
            flags_left = 32

        flags_left -= 1
        if (flags >> flags_left) & 1 == 0:
            # literal
            if i >= n:
                raise ValueError("truncated literal")
            out.append(data[i])
            i += 1
            if len(out) - base > MAX_SIZE:
                raise ValueError("too large")
            continue

        # set bit => match; no input left => end-of-data
        if i >= n:
            return bytes(out)
        if n - i < 2:
            raise ValueError("truncated match")
        mb = struct.unpack_from("<H", data, i)[0]
        i += 2
        moff = (mb >> 3) + 1
        mlen = (mb & 7) + 3

        if (mb & 7) == 7:
            if pending_len == -1:
                if i >= n:
                    raise ValueError("truncated nibble")
                nib = data[i] & 0x0F
                pending_len = i
                i += 1
            else:
                nib = (data[pending_len] >> 4) & 0x0F
                pending_len = -1
            if nib == 15:
                if i >= n:
                    raise ValueError("truncated raw length")
                v = data[i]
                i += 1
                if v == 255:
                    if n - i < 2:
                        raise ValueError("truncated u16 length")
                    v = struct.unpack_from("<H", data, i)[0]
                    i += 2
                    if v == 0:
                        if n - i < 4:
                            raise ValueError("truncated u32 length")
                        v = struct.unpack_from("<I", data, i)[0]
                        i += 4
                    if v < 15 + 7:
                        raise ValueError("corrupt length")
                    if v > MAX_SIZE:
                        raise ValueError("too large")
                    mlen = int(v) + 3
                else:
                    mlen = int(v) + 25
            else:
                mlen = nib + 10

        if mlen > MAX_SIZE - (len(out) - base):
            raise ValueError("too large")
        if moff > len(out) - base:
            raise ValueError("corrupt offset")
        start = len(out) - moff
        for j in range(mlen):
            out.append(out[start + j])

    # unreachable
    return bytes(out)


def selftest() -> int:
    checks = []

    def check(cond, label):
        checks.append((bool(cond), label))

    # empty stream: one flag group, top bit set, no input => end marker
    empty = struct.pack("<I", 0x80000000)
    r = decompress_plain(empty)
    check(r == b"", "empty stream yields empty output")
    check(len(r) == 0, "empty length 0")

    # single literal 'A' then end
    # flags: bit31 clear (literal), bit30 set (end on no input) => 0x40000000
    one = struct.pack("<I", 0x40000000) + b"A"
    r = decompress_plain(one)
    check(r == b"A", "single literal decodes")
    check(len(r) == 1, "single literal length")

    # two literals
    two = struct.pack("<I", 0x00000000) + b"AB" + struct.pack("<I", 0x80000000)
    # 32 clear bits need 32 literals; instead use 1 flag group with 30 trailing set bits? simpler: one literal then 31 set bits with no input -> end after first? Actually first clear bit literal consumes one byte, then next set bit with no input -> end. So flags 0x40000000 enough for one literal then end; for two literals need two clear bits then a set bit: flags 0x20000000? bit31 clear, bit30 clear, bit29 set. + 2 bytes.
    two = struct.pack("<I", 0x20000000) + b"AB"
    r = decompress_plain(two)
    check(r == b"AB", "two literals decode")

    # match test: output "AAAA" via literal A then match length 3 offset 1
    # flags: literal (clear) + match (set) => 0x40000000? bit31 clear literal, bit30 set match. + 'A' + match word.
    # match word: moff=(offset-1)=0 in top 13 bits => 0; mlen=(len-3)=0 in low 3 bits => 0; mb=0. nibble form not used (mb&7=0 !=7).
    match = struct.pack("<I", 0x60000000) + b"A" + struct.pack("<H", 0)
    r = decompress_plain(match)
    check(r == b"AAAA", "match copies repeated byte")

    # shared-nibble form test: length 10 (nib=0? nib+10=10) offset 1
    # need mb&7==7: low 3 bits =7. mb = (0<<3)|7 = 7. Then pending nibble. First match triggers nibble read: if pending_len==-1 read low nibble of next byte. Set that byte low nibble 0 => length 10. High nibble pending for next match (none). 
    # flags: literal clear + match set => 0x40000000
    nibdata = struct.pack("<I", 0x60000000) + b"A" + struct.pack("<H", 7) + bytes([0x00])
    r = decompress_plain(nibdata)
    check(r == b"A" + b"A"*10, "shared nibble length 10")

    # raw length test: nib==15 -> v = next byte; if v !=255, mlen=v+25. Use v=0 => 25.
    rawb = struct.pack("<I", 0x60000000) + b"A" + struct.pack("<H", 7) + bytes([15, 0])  # nib 15, v=0? v=0 means 25? v=0 -> mlen=0+25=25 (not 255 path). Actually if v==0 and not 255, mlen=0+25=25. OK.
    r = decompress_plain(rawb)
    check(r == b"A" + b"A"*25, "raw length byte form")

    ok = all(c for c, _ in checks)
    for c, label in checks:
        print(("PASS" if c else "FAIL"), label)
    print(f"xpress selftest: {'OK' if ok else 'FAIL'} ({sum(c for c,_ in checks)}/{len(checks)})")
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    if len(sys.argv) < 2:
        print("usage: xpress.py [--selftest] | decompress INPUT [-o OUT] | selftest")
        return 2
    if sys.argv[1] == "selftest":
        return selftest()
    if sys.argv[1] == "decompress":
        inp = sys.argv[2]
        out = None
        if "-o" in sys.argv:
            out = sys.argv[sys.argv.index("-o") + 1]
        data = open(inp, "rb").read()
        res = decompress_plain(data)
        if out:
            open(out, "wb").write(res)
        else:
            sys.stdout.buffer.write(res)
        print(f"decoded {len(res)} bytes", file=sys.stderr)
        return 0
    print("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
