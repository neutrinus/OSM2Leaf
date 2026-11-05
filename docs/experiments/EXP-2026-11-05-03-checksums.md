# EXP-2026-11-05-03: Firmware checksums and per-file integrity

- **Status:** done
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-160, C-161, C-162, C-163, C-164, C-168
- **Supersedes:** none
- **Superseded by:** none

## Question

Does the card have per-file checksums or signatures, and what exactly do the
firmware `SUM4` and updater checksums cover?

## Hypothesis

The firmware checksums cover only the firmware payload, not the FAT map
partition; map integrity relies on zlib Adler-32 and size bookkeeping.

## Inputs

| Item | Value |
| --- | --- |
| Image | `leaf2011.img` |
| SHA-256 | `105e2032…76307` |
| Main ROM header | `0x200000`, length `0x01752c88` |
| Updater header | `0x3e00000`, length `0x6e18a4` |
| Tools | `python3`, `hash_hunt.py` |

## Method

```bash
# Main ROM: sum of LE u32 over [0x200200, +length)
# Updater: byte sum over [0x200, +length) with checksum bytes zeroed
# Then search sampled files for crc32/adler32/sum32/sum8 in DRSTR/MMAIN/headers
```

Full scripts and offsets: `/tmp/opencode/research-checksums/`.

## Observations

- Main ROM: stored `0xcdf87db0` at header `+0x34`, tag `SUM4` at `+0x30`.
  Recomputed value matches.
- Updater: stored `0x12aa` at `+0x230`, length at `+0x232`; recomputed byte sum
  matches with the checksum bytes zeroed.
- Both checksummed ranges end before the FAT partition (`0x06400400`).
- Hash hunt over 23 sampled files: **0 hits** for CRC-32/Adler-32/sum32/sum8
  in `DRSTR`, `MMAIN`, headers, `HDD_INFO` and the `0x06000000` block.
- `DRSTR` covers 285 files + 39 dirs; only itself is absent.
- `MMAIN` `0x1ac` table equals the sum over all 46 `MAPAL001` files (11/11).
- Tiles: ~61 % of the post-`0x5200` payload is inside zlib streams; no digest.

## Interpretation

- **FACT:** the two firmware checksum formulas are reproduced exactly.
- **FACT:** neither checksum covers map data.
- **FACT (negative):** no per-file checksum/signature was found.
- **OBSERVED:** map code is a text/market check, not a content hash.

## Conclusion

`docs/format/validation.md` and claims C-160…C-168 were added. A rebuilt card
must keep sizes/`DRSTR`/`HDD_INFO` consistent, but does not need to reproduce a
per-file checksum.

## Follow-ups

- [ ] Hardware test: `HDD_INFO` line 1 alone, then also the `0x06000000` copy.
- [ ] Explain the `BICON001` data version `11/04/08/01`.
- [ ] Check whether `MMAIN` `0x1ac` must match the tile set exactly.
