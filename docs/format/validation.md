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

The UTF-16 string `DIFFERENT MAP CODE` is in `AppLaunch.dll` at physical VA
`0x883368bc` (build B) / `0x8834089c` (build C), next to `MAP DATA BASE
UNMATCH` and `NAVI VERSION NG`. Nearby launcher code reads
`\SystemSD\VER_INFO\HDD_INFO.TXT`, logs `VerInf:%s / HddInf:%s` and checks
`MapDBVer : %d <= [%d] <= %d`.

Hypotheses, in order:

1. **Market/family code.** `HDD_INFO` line 1 is `QSD-300-100` on JP cards,
   `301` US, `302` EU. It is a family check, not a per-card activation.
2. **Raw-copy comparison.** The unit may compare `HDD_INFO` against the
   byte-identical copy at image offset `0x06000000`.
3. **Unknown activation record.** A NAND-side record that we have not found.

A separate runtime check exists in `Navi.exe`: `fn 0x004dd028` reads both
`\SystemSD\VER_INFO\HDD_INFO.TXT` and `\UserSD\VER_INFO\HDD_INFO.TXT`
through `fn 0x004e7b8c`, compares field 0 (line 1) with
`wcsncmp(..., 11)` and then the numeric tail, and sets a validation flag when
the SystemSD value is greater than the UserSD value. It is triggered by the
`NaviSetCC.dll` request message `0x841000f7`, not at boot or on SD insertion
(EXP-2026-11-06-M2.11-hddinfo-trigger, C-1770–C-1779). The
`SD Import: Sys[0x%x] SD[0x%x]` ID comparison belongs to the updater path
(C-775), not this check.

The cheapest test pair on a spare card:

1. Change only `HDD_INFO` line 1 → observe `DIFFERENT MAP CODE`.
2. Change line 1 **and** the `0x06000000` copy → observe again.

That distinguishes hypotheses 1/2 without touching the unit.

### HYPOTHESIS: offline comparator model M0 (`tools/hddinfo.py`)

> **Status: HYPOTHESIS, not validated.** The model below is derived from the
> comparator chain at `0x6fab2c` → `0x6faeb0` → `0x6fb05c`
> (EXP-2026-11-05-17), *not* from a decoded parser and *not* from hardware.
> Every verdict it prints is a prediction. None of them may be quoted as a
> verified result until the spare-card matrix in
> [EXP-2026-11-05-41](../experiments/EXP-2026-11-05-41-hddinfo-model.md) has
> actually run on a car and the observed messages are recorded.

`tools/hddinfo.py` parses/serialises the 72-byte block byte-identically
(six named lines plus retained tail bytes) and compares numeric field pairs the
way the documentation says the unit does: `Sys[0x%x]` vs `SD[0x%x]` for
`manufacturer_id`, `userdata_type` (range `0..5`) and `destination_id`. `Sys`
is the built-in copy at image offset `0x06000000`; `SD` is the card's
`VER_INFO/HDD_INFO.TXT`.

Because the line→field parser is still unknown, the field derivation is part
of the hypothesis:

| Field | Model rule | Source |
| --- | --- | --- |
| `userdata_type` | leading digit of the first number on line 1 (`QSD-3…` → 3); outside `0..5` ⇒ `DIFFERENT MAP CODE` | range check at `0x6fb122`; QSD family guess (C-304) |
| `manufacturer_id` | digits of the line-4 prefix (`SDC08` → `0x08`) | shape-based guess (C-304) |
| `destination_id` | line-4 suffix (`EVEUR`) through a model-local token table; unknown tokens compare by text equality | shape-based guess (C-304) |

Semantics: all three fields must match for `ACCEPT`; a value change, an
unparsable field, or an out-of-range `userdata_type` gives
`DIFFERENT MAP CODE`. The firmware bound is recorded as `0 < v < 6` (C-301),
so `userdata_type == 0` is the boundary case the matrix must watch: the tool
accepts `0..5` and labels it in-range.

```bash
# parse one block (read-only), and the synthetic self-test
python3 tools/hddinfo.py parse root/VER_INFO/HDD_INFO.TXT
python3 tools/hddinfo.py --selftest            # expect: selftest: OK (34 checks)

# predict one Sys/SD pair; exit 0 = ACCEPT, 1 = DIFFERENT MAP CODE, 2 = error
python3 tools/hddinfo.py classify SYS.HDD_INFO.TXT root/VER_INFO/HDD_INFO.TXT --json

# annotate the whole variant matrix with predicted verdicts + MANIFEST.txt
python3 tools/hddinfo.py matrix root/VER_INFO/HDD_INFO.TXT /tmp/variants --sweep 0-5
```

`matrix` delegates variant generation to `tools/hddinfo_variants.py`, checks
that every output keeps the base length, and writes `MANIFEST.txt` with one
predicted verdict per variant (the variant tool's own manifest is preserved as
`MANIFEST.variants.txt`). Variant files left over from an earlier run are
excluded with a warning, so a changed `--sweep` cannot silently mix matrices;
use a fresh output directory for a clean run. With `--no-permute` it produces
the 73 content edits; with permutations, 89. `--sys FILE` compares every
variant against an extracted `0x06000000` copy instead of the base file, which
is the pairing the unit would use if it reads both sides.

The field derivation is the only unverified part and can be settled without
hardware by reaching the parser through the CE ROM TOC
(`tools/ce_rom_parse.py`, `docs/format/firmware.md`). Until either that or the
spare-card matrix happens, every verdict from the tool is a prediction.

## Error screens (`AppLaunch.dll`)

The unit's error screens are **not** in `Navi.exe`: they are a UTF-16LE string block
in `AppLaunch.dll` (builds B and C; build A has none of them, C-205/C-808). The block
is in the module's uncompressed section (rva `0x1000`). Every string in the block is
referenced by exactly one function per build, so the screen is selected by an error
code indexing into this table, not by a separate string per call site.

VAs below are **physical** VAs from `cerom.py file2va` (build B image start `0x3e00200`,
build C `0x5200200`); the same bytes reappear in the build-B copy at `0x4800200`.

| Build | Error string | Module | String VA | Showing function VA |
| --- | --- | --- | --- | --- |
| B | `UNKNOWN ERROR` | AppLaunch.dll | `0x883367cc` | `0x8834ffb8` |
| B | `SD ACCESS NG` | AppLaunch.dll | `0x883367e8` | `0x8834ffb8` |
| B | `SD INIT NG` | AppLaunch.dll | `0x88336804` | `0x8834ffb8` |
| B | `SD UNLOCK NG` | AppLaunch.dll | `0x8833681c` | `0x8834ffb8` |
| B | `NO SD CARD` | AppLaunch.dll | `0x88336838` | `0x8834ffb8` |
| B | `NAVI STARTUP NG` | AppLaunch.dll | `0x88336850` | `0x8834ffb8` |
| B | `NO SERVICE TOOL` | AppLaunch.dll | `0x88336870` | `0x8834ffb8` |
| B | `MAP DATA BASE UNMATCH` | AppLaunch.dll | `0x88336890` | `0x8834ffb8` |
| B | `DIFFERENT MAP CODE` | AppLaunch.dll | `0x883368bc` | `0x8834ffb8` |
| B | `NAVI VERSION NG` | AppLaunch.dll | `0x883368e4` | `0x8834ffb8` |
| B | `NAVI-2 FILE READ NG` | AppLaunch.dll | `0x88336904` | `0x8834ffb8` |
| B | `NO NAVI-2 FILE` | AppLaunch.dll | `0x8833692c` | `0x8834ffb8` |
| B | `MAIN TEST FILE READ NG` | AppLaunch.dll | `0x8833694c` | `0x8834ffb8` |
| B | `MAIN TEST FILE SIZE NG` | AppLaunch.dll | `0x8833697c` | `0x8834ffb8` |
| B | `NO MAIN TEST FILE` | AppLaunch.dll | `0x883369ac` | `0x8834ffb8` |
| B | `TEST FILE READ NG` | AppLaunch.dll | `0x883369d0` | `0x8834ffb8` |
| B | `TEST FILE SIZE NG` | AppLaunch.dll | `0x883369f4` | `0x8834ffb8` |
| B | `NO TEST FILE` | AppLaunch.dll | `0x88336a18` | `0x8834ffb8` |
| B | `UPDATE FILE READ NG` | AppLaunch.dll | `0x88336a34` | `0x8834ffb8` |
| B | `UPDATE FILE SIZE NG` | AppLaunch.dll | `0x88336a5c` | `0x8834ffb8` |
| B | `NO UPDATE FILE` | AppLaunch.dll | `0x88336a84` | `0x8834ffb8` |
| B | `NAVI-1 NG` | AppLaunch.dll | `0x88336aa4` | `0x8834ffb8` |
| B | `NO NAVI-1 FILE` | AppLaunch.dll | `0x88336ab8` | `0x8834ffb8` |
| B | `TARGET INFO NG` | AppLaunch.dll | `0x88336ad8` | `0x8834ffb8` |
| B | `E-BOOT NG` | AppLaunch.dll | `0x88336af8` | `0x8834ffb8` |
| C | `UNKNOWN ERROR` | AppLaunch.dll | `0x883407cc` | `0x88359c90` |
| C | `SD ACCESS NG` | AppLaunch.dll | `0x883407e8` | `0x88359c90` |
| C | `SD INIT NG` | AppLaunch.dll | `0x88340804` | `0x88359c90` |
| C | `SD UNLOCK NG` | AppLaunch.dll | `0x8834081c` | `0x88359c90` |
| C | `NO SD CARD` | AppLaunch.dll | `0x88340838` | `0x88359c90` |
| C | `NAVI STARTUP NG` | AppLaunch.dll | `0x88340850` | `0x88359c90` |
| C | `MAP DATA BASE UNMATCH` | AppLaunch.dll | `0x88340870` | `0x88359c90` |
| C | `DIFFERENT MAP CODE` | AppLaunch.dll | `0x8834089c` | `0x88359c90` |
| C | `NAVI VERSION NG` | AppLaunch.dll | `0x883408c4` | `0x88359c90` |
| C | `NAVI-2 FILE READ NG` | AppLaunch.dll | `0x883408e4` | `0x88359c90` |
| C | `NO NAVI-2 FILE` | AppLaunch.dll | `0x8834090c` | `0x88359c90` |
| C | `MAIN TEST FILE READ NG` | AppLaunch.dll | `0x8834092c` | `0x88359c90` |
| C | `MAIN TEST FILE SIZE NG` | AppLaunch.dll | `0x8834095c` | `0x88359c90` |
| C | `NO MAIN TEST FILE` | AppLaunch.dll | `0x8834098c` | `0x88359c90` |
| C | `TEST FILE READ NG` | AppLaunch.dll | `0x883409b0` | `0x88359c90` |
| C | `TEST FILE SIZE NG` | AppLaunch.dll | `0x883409d4` | `0x88359c90` |
| C | `NO TEST FILE` | AppLaunch.dll | `0x883409f8` | `0x88359c90` |
| C | `UPDATE FILE READ NG` | AppLaunch.dll | `0x88340a14` | `0x88359c90` |
| C | `UPDATE FILE SIZE NG` | AppLaunch.dll | `0x88340a3c` | `0x88359c90` |
| C | `NO UPDATE FILE` | AppLaunch.dll | `0x88340a64` | `0x88359c90` |
| C | `NAVI-1 NG` | AppLaunch.dll | `0x88340a84` | `0x88359c90` |
| C | `NO NAVI-1 FILE` | AppLaunch.dll | `0x88340a98` | `0x88359c90` |
| C | `TARGET INFO NG` | AppLaunch.dll | `0x88340ab8` | `0x88359c90` |
| C | `E-BOOT NG` | AppLaunch.dll | `0x88340ad8` | `0x88359c90` |

Build A contains none of these strings (string search over all 149 modules). The build-B copy at image offset `0x4800200` is byte-identical to build B, so its VAs are the same.

The showing-function VAs were recovered by the nearest `sts.l pr,@-r15` (`0x4f22`) prologue
preceding the literal pool that holds all of the string pointers; exact function boundaries are
a heuristic (C-807). The function is the single dispatcher that selects a screen from an error
code; `UNKNOWN ERROR` is the fallback.

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
