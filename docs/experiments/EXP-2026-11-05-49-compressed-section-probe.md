# EXP-2026-11-05-49: Compressed .data section — standard-decoder probe

- **Status:** inconclusive
- **Date:** 2026-11-05
- **Sample:** `LEAF_2011-2012_QSD-309-101_navi158_eu.img`, first 256 MiB (`curl -r 0-268435455`), SHA-256 of the 256 MiB slice `92aa525d…`
- **Claims:** C-529 (still UNKNOWN after this probe)
- **Supersedes:** none
- **Superseded by:** none

## Question

Does the `IMAGE_SCN_COMPRESSED` section of `NaviMapCC.dll` (M1.2) decode with a
standard decoder available in the stdlib (zlib raw/zlib/gzip, LZMA, bz2)?

## Hypothesis

Exploratory. If the ROM uses one of these, output length would equal `vsize`.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `LEAF_2011-2012_QSD-309-101_navi158_eu.img`, image A at `0x200200` |
| SHA-256 (256 MiB slice) | `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9` |
| Section | `NaviMapCC.dll`, rva `0x13000`, vsize `0x5b8`, psize `0x2c6`, file `0x01580ce0`, flags `c8002040` |
| Second section | rva `0x14000`, vsize `0xcc0`, psize `0x68c`, file `0x015aca7c`, flags `48002040` |

## Method

```bash
python3 tools/cerom.py IMG sections NaviMapCC.dll
python3 -I - <<'PY'
import zlib, lzma, bz2
d = open('head256.img', 'rb').read()
for name, o, n, vs in [
    ('NaviMapCC .data (rva 0x13000)', 0x01580ce0, 0x2c6, 0x5b8),
    ('NaviMapCC rva 0x14000',         0x015aca7c, 0x68c, 0xcc0)]:
    b = d[o:o+n]
    for wb in (-15, 15, 31):           # raw deflate, zlib, gzip
        try: print(name, 'zlib', wb, len(zlib.decompressobj(wb).decompress(b)), 'vsize', hex(vs))
        except zlib.error as e: print(name, 'zlib', wb, 'zlib.error', e)
    for fn, lab in [(lzma.decompress, 'lzma'), (bz2.decompress, 'bz2')]:
        try: print(name, lab, len(fn(b)))
        except Exception as e: print(name, lab, type(e).__name__)
PY
```

Limitation: decoders were run from the stream start only. None were tried after skipping the header words.

## Observations

- Section 1 stream (710 bytes) starts `84 04 00 c6 02 00 10 00 00 00 84 04 00 00 b0 02 00 00 84 04 00 00 5b 80 80 8d 00 20 40 48`.
- Section 2 stream (1676 bytes) starts `c0 0c 00 8c 06 00 10 00 00 00 c0 0c 00 00 76 06 00 00 c0 0c 00 00 5b 80 80 8d 00 20 01 cc`.
- zlib raw (`-15`), zlib (`15`), gzip (`31`): `zlib.error` (`-3`) on both streams.
- LZMA: `LZMAError`. bz2: `OSError`.
- Header words: section 1 starts with psize `0x2c6` (`c6 02`), then the repeated word `0x484` (1156). `0x484` is not section 1's vsize (0x5b8). Section 2 is different: `c0 0c` = vsize `0xcc0`, `8c 06` = psize `0x68c`. The 12-byte header pattern is common to both, but the meaning of `0x484` is unexplained.
- Both streams contain the word `0x8d80805b`. It may be a VA, but this is unverified.

## Interpretation

Decoders fail when fed from the stream start. They were not tried after skipping the header, so the stdlib formats are ruled out only in that form. The format is still unknown.
This is a negative result only, with no positive control yet. Candidates left:
the kernel's own decompressor (M8.E1 / M9.6, via QEMU or L3 CE-HLE), or a
CE-specific LZ variant to be identified from `nk.exe` / `romimage` strings.

## Next

1. Find the decompressor call site in `nk.exe` (image B) by searching for the
   `IMAGE_SCN_COMPRESSED` handling in the loader path (`va2file`, `sections`).
2. Use the same call on section 1 and check output length `0x5b8`.
