# Validation, checksums and map code

> **Evidence status:** the firmware checksum formulas were reproduced from the
> bytes and are `VERIFIED`; the map-code mechanism is `OBSERVED`/`HYPOTHESIS`;
> the absence of per-file checksums is a `VERIFIED` negative result.

## Firmware checksums

### Main ROM (`NB00` at `0x200000`, copy at `0x2000000`)

- Length: `u32` at `+0x00` = `0x01752c88` (24,456,328 bytes).
- Tag `SUM4` at `+0x30`; checksum `u32` at `+0x34`.
- Formula: sum of **little-endian `u32` words** over
  `[0x200200, 0x200200 + length)`.
- Recomputed value: `0xcdf87db0`, matching the stored field.
- The checksummed range ends at `0x01952e88`, **before** the FAT partition
  (`0x06400400`). It does **not** cover map data.

### Updater image (`0x3e00000` / `0x4800000`)

- `u16` byte sum at `+0x230`, `u32` length at `+0x232`.
- Formula: byte sum over `[0x200, 0x200 + length)` with the two checksum bytes
  zeroed.
- Recomputed value: `0x12aa`, matching the stored field.
- Again, no map data in the range.

## Map tree: no per-file checksum

- `DRSTR001.DAT` covers every logical file exactly once (285 files + 39 dirs);
  only `DRSTR001.DAT` itself is absent.
- Entry size is the on-disk file size, except `REFER001` where it is the sum
  of `.ind` uncompressed sizes.
- `MMAIN001.DAT`'s 11-entry table at `0x1ac` equals the sum over all 46
  `MAPAL001` files (including `LEV3456R`), 11/11.
- A search for CRC-32/Adler-32/sum32/sum8 of 23 sampled files in DRSTR,
  MMAIN, headers, `HDD_INFO` and the raw `0x06000000` block found **0 hits**.
- Tiles: only ~61 % of the payload after `0x5200` is inside zlib streams; the
  rest is zero alignment padding and fixed tables. There is no room for a
  per-tile digest.

**Integrity is zlib Adler-32 inside each compressed chunk.** If a `.cmp` or
tile stream is corrupted, zlib catches it; the outer structures only carry
sizes.

## Map code (`DIFFERENT MAP CODE`)

The UTF-16 string `DIFFERENT MAP CODE` is at firmware `0x04136abc`, next to
`MAP DATA BASE UNMATCH` and `NAVI VERSION NG`. Nearby launcher code reads
`\SystemSD\VER_INFO\HDD_INFO.TXT`, logs `VerInf:%s / HddInf:%s` and checks
`MapDBVer : %d <= [%d] <= %d`.

Hypotheses, in order:

1. **Market/family code.** `HDD_INFO` line 1 is `QSD-300-100` on JP cards,
   `301` US, `302` EU. It is a family check, not a per-card activation.
2. **Raw-copy comparison.** The unit may compare `HDD_INFO` against the
   byte-identical copy at image offset `0x06000000`.
3. **Unknown activation record.** A NAND-side record that we have not found.

The cheapest test pair on a spare card:

1. Change only `HDD_INFO` line 1 → observe `DIFFERENT MAP CODE`.
2. Change line 1 **and** the `0x06000000` copy → observe again.

That distinguishes hypotheses 1/2 without touching the unit.

## Offline mutation matrix

| Mutation | Detected by our tools |
| --- | --- |
| flip a `.cmp` byte | yes (zlib Adler-32) |
| truncate `.cmp` | yes |
| `.ind` size/offset wrong | yes |
| `.cmp` legitimately recompressed | no (passes) |
| `DRSTR` size changed | **silent** |
| `HDD_INFO` line 1 changed | **silent** (map-code knob) |
| tile byte flip inside a stream | silent until zlib use |
| tile byte flip in padding / `MMAIN` change | silent |

## Rules for a rebuilt card

1. Keep `HDD_INFO.TXT` and its `0x06000000` copy consistent.
2. Keep `DRSTR001.DAT` sizes consistent with the actual files.
3. Keep `.ind` sizes/offsets consistent with `.cmp`.
4. Do not rely on a checksum to catch structural mistakes; validate with
   `tools/cmpind.py`, `tools/drstr.py` and a round-trip writer.
5. Treat the map code as a text/market check until a hardware test says
   otherwise.

## Open questions

- Is `DIFFERENT MAP CODE` line 1, the `0x06000000` copy, or a NAND record?
- Does `MMAIN001.DAT`'s `0x1ac` table need to match the tile set exactly, or
  is it informational?
- What is the `BICON001.DAT` data version `11/04/08/01` (vs `11/06/27/01`)?
- Is the TFAT16 volume required at boot, or only for skin/recovery?
