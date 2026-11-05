# EXP-2026-11-05-51: FILESentry compressed payloads: standard-decoder probe (M1.4)

- **Status:** inconclusive
- **Date:** 2026-11-05
- **Sample:** `LEAF_2011-2012_QSD-309-101_navi158_eu.img`, first 256 MiB, SHA-256 `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`
- **Claims:** none changed
- **Supersedes:** none
- **Superseded by:** none

## Question

Do the compressed FILESentry payloads of image B (attr `0x0800`, comp != real)
decode with a standard stdlib decoder, after skipping up to 16 header bytes?

## Hypothesis

Exploratory. If one of zlib raw/zlib/gzip (checked as a `78 9c` header too), LZMA
or bz2 applies, the output length equals `real`.

## Inputs

| Item | Value |
| --- | --- |
| Image B | `--image-start 0x3e00200` |
| Listing | `python3 tools/cerom.py --image-start 0x3e00200 IMG files` |

## Method

```bash
python3 tools/cerom.py --image-start 0x3e00200 IMG files
python3 -I - <<'PY'   # for each payload: skip 0..16 bytes, try zlib -15/15/31, lzma, bz2
...
PY
```

## Observations

- Image B FILESentry: 11+ entries. Compressed (attr `0x0800`): `ceconfig.h`, `initobj.dat`, `boot.hv`, `default.hv`, `user.hv`, `initdb.ini`, `celog.dll`, `UpdateNK.skn`, among others. Uncompressed (`0x0007`): `wince.nls`, `DFHei-Nissan-P.ttf`, `OIDEFALT.img`.
- Image C lists the same names with different sizes (`default.hv` real 106496, B has 126976).
- Stdlib results: no valid stream. Skipping 0-16 bytes gives only 0-1 byte outputs, which are spurious partial decodes, not hits. No `78 9c` header is present in the first 64 bytes of `ceconfig.h`, `boot.hv` or `UpdateNK.skn`.
- The first `u16` LE of the payload equals the real size for `ceconfig.h` (`d3 19` = 6611), `boot.hv` (`00 80` = 32768) and `initobj.dat` (`3d 5a` = 15706). It does not hold for `UpdateNK.skn` (real 1966080, which does not fit in u16), so the field is not a plain u16 size.
- `boot.hv` header continues with a progression `dd 00`, `27 01`, `71 01`, `bb 01` (step 0x4a). This may be a table, but it is not verified.

## Interpretation

The FILESentry compression is not one of the stdlib formats above. The header
carries the real size at offset 0 in the small files, and the other fields are
unexplained. Same status as EXP-49 (M1.2): the likely route is the kernel's own
decompressor (M8.E1 / M9.6).

## Next

- Check the `boot.hv` table hypothesis (block sizes, page size 0x1000).
- Use the same decompressor route as M1.2.
