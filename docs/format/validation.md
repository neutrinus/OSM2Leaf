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

## Map code (`DIFFERENT MAP CODE`) and `MAP DATA BASE UNMATCH`

The UTF-16 strings are in `AppLaunch.dll`: `DIFFERENT MAP CODE` at physical VA
`0x883368bc` (build B) / `0x8834089c` (build C), `MAP DATA BASE UNMATCH` at
`0x88336890` (B) / `0x88340870` (C). The AppLaunch dispatcher
`fn 0x03bcafb8` (B) maps error code `0x50` → `DIFFERENT MAP CODE` and
`0x51` → `MAP DATA BASE UNMATCH` (C-761).

### Launcher checks (M2.5, M2.15, VERIFIED static, IMG256 `92aa525d…`)

`AppLaunch.dll` B router `fn 0x03bd2ecc` (C mirror via pools
`0x03bb2c54`→`0x03bb2858`, `0x03bb2c64`→`0x03bb2a64`) evaluates both checks
independently and dispatches an error for each that fails (it does **not** skip
check 2 when check 1 fails): `0x03bd2ed4/0x03bd2eda–0x03bd2ee2` call check 1
and dispatch `0x50` on `r0==0`, then `0x03bd2ee4/0x03bd2eea–0x03bd2ef2` call
check 2 and dispatch `0x51` on `r0==0`. The two HDD_INFO-parsing functions
share a parse cache at global `0x01f74b30` (pool `0x03bd2cb8` in B check 1,
`0x03bd2ea8` in B check 2): if `*0x01f74b30 != 0` they use the cached slots,
otherwise they open `\SystemSD\VER_INFO\HDD_INFO.TXT` (`pool 0x03bd2cc0`/`0x03bd2eb0`),
read 0x60 bytes and parse CRLF/LF-separated lines into **16-byte slots** at
`0x01f74b30` (slot 0 = line 1 at offset 0, slot 1 = line 2 at offset 16,
slot 2 = line 3 at offset 32, …; up to 15 chars copied per slot). The card-side
values below are taken from these slots (and therefore from the stripped line
content of the HDD_INFO file).

#### Check 1 — `DIFFERENT MAP CODE` (error `0x50`)

| | Value |
| --- | --- |
| B function / VAs | `fn 0x03bd2ad8` (C `fn 0x03bb2858`); unit read `KernelIoControl(0x0101302C)` `0x03bd2b2c` (pool `0x0101302c`/thunk `0x03bca3e8`), copy unit `+0x60` at `0x03bd2b36–0x03bd2b56` (C `0x03bb28bc`, `add #96`); copy card slot 0 `0x03bd2c06–0x03bd2c1e`; 11-byte compare `0x03bd2c1e–0x03bd2c3e`; mismatch log `VerInf:%s / HddInf:%s` (`pool 0x03bc9330`) |
| HDD_INFO source | line **1** (`base_code`, M2.3 C-740), **slot 0** bytes **0–10** = first **11 bytes** of the stripped line content. In the file this is **file offset `0x00`, length 11** for a standard 11-char line 1 (e.g. `QSD-302-100` = `51 53 44 2d 33 30 32 2d 31 30 30`); compared byte-for-byte as 11 bytes. |
| Unit-side source | `KernelIoControl(IOCTL 0x0101302C)` output, **offset `+0x60` (+96)**, **11 bytes** (NAND/system/kernel target-info record). |
| Verdict | mismatch → log `VerInf:%s / HddInf:%s\r\n`, return 0 → `DIFFERENT MAP CODE`. Match → proceed to check 2. |

#### Check 2 — `MAP DATA BASE UNMATCH` (error `0x51`)

| | Value |
| --- | --- |
| B function / VAs | `fn 0x03bd2ce4` (C `fn 0x03bb2a64`); unit read `KernelIoControl(0x0101302C)` (pool `0x0101302c`/thunk `0x03bca3e8`), unit `+114` (16-bit BE) read at `0x03bd2d38` (`add #114`) stored `r15+0x24`, unit `+112` (16-bit BE) read at `0x03bd2d8a` (`add #112`) stored `r15+0x20`; card MapDBVer extract `0x03bd2e3a–0x03bd2e68` (C `0x03bb2bba`); range `0x03bd2e6c–0x03bd2e7a`; log `MapDBVer : %d <= [%d] <= %d` (`pool 0x03bc9360`, `0x03bd2e7c–0x03bd2e82`). |
| HDD_INFO source | line **3** (`build`, M2.3 C-740, **slot 2** at global offset 32), **stripped-line positions 5, 6, 7** (0-based, global offsets 37/38/39). Each byte is converted by `fn 0x03bd2a40` (B; 22-char table `0-9a-fA-F` → 0–15, not-found → 0) and combined as **3 nibbles**: `MapDBVer = ((d5*16)+d6)*16 + d7`. For factory EU 2011 line 3 `02-110100-00` (file offset 26, content `30 32 2d 31 31 30 31 30 30 30 2d 30 30`) positions 5,6,7 are `'0','1','0'` (file offsets 31–33) → `0x010` = 16. |
| Unit-side source | `KernelIoControl(IOCTL 0x0101302C)` output, **offset `+112` (+0x70)** = 16-bit big-endian **minimum** and **offset `+114` (+0x72)** = 16-bit big-endian **maximum** (NAND/system/kernel target-info record). |
| Verdict | `target[+112] <= MapDBVer <= target[+114]` (unsigned 16-bit) → pass. Otherwise log `MapDBVer : %d <= [%d] <= %d\r\n` (value, min, max) and return 0 → `MAP DATA BASE UNMATCH`. |

**The deciding inputs for these two launcher checks are the NAND/system kernel
target-info record (`0x0101302C` +96/+112/+114) compared against the card's
`\SystemSD\VER_INFO\HDD_INFO.TXT` parsed line 1 (bytes 0–10) and line 3
(positions 5–7). They are NOT the `0x06000000` raw HDD_INFO copy and NOT an
HDD_INFO text record stored in NAND** (C-766, EXP-2026-11-06-M2.5,
EXP-2026-11-06-M2.15). The `0x06000000` copy is not an input on this path; this
rules it out for these two launcher checks but does **not** prove `0x06000000`
is unused everywhere (M2.7/C-783).

No market/area value is involved in either function (C-783). The market area
(`CApi_GetModelArea`) is a separate unit-side UI/launch value (see `firmware.md`).

A separate runtime check exists in `Navi.exe`: `fn 0x004dd028` reads both
`\SystemSD\VER_INFO\HDD_INFO.TXT` and `\UserSD\VER_INFO\HDD_INFO.TXT`
through `fn 0x004e7b8c`, compares field 0 (line 1) with
`wcsncmp(..., 11)` and then the numeric tail, and sets a validation flag when
the SystemSD value is greater than the UserSD value. It is triggered by the
`NaviSetCC.dll` request message `0x841000f7`, not at boot or on SD insertion
(EXP-2026-11-06-M2.11-hddinfo-trigger, C-1770–C-1779). The
`SD Import: Sys[0x%x] SD[0x%x]` ID comparison belongs to the updater path
(C-775), not this check.

The cheapest test pair on a spare card (bench, prediction — `0x06000000` not
implicated by this path):

1. Change only `HDD_INFO` line 1 (`base_code`) to differ from the unit target
   record → expect `DIFFERENT MAP CODE` (VerInf vs HddInf mismatch).
2. Change line 1 **and** the `0x06000000` copy → if only this path triggers,
   result should be the same as (1); any difference would indicate another
   path using `0x06000000`.

### HDD_INFO.TXT text layout (M2.1/M2.3, VERIFIED static)

> **Status: VERIFIED (static).** Reader layout from `Navi.exe` `fn 0x004e7b8c`
> (build A, IMG256 `92aa525d…`), disassembled and traced in
> EXP-2026-11-06-M2.1-hddinfo-fn-complete (C-721–C-728) and mapped here
> (EXP-2026-11-06-M2.3-hddinfo-fields, C-740–C-749). The file content values are
> grounded on the factory EU 2011 `VER_INFO/HDD_INFO.TXT` (sha256
> `9f014643…c650a`, 72 bytes, 6 CRLF ASCII lines, no trailing CRLF); vendor
> content is not committed.

`HDD_INFO_read(r4 ignored, r5 selector, r6 output struct base r8)` reads 6
lines from `\SystemSD\VER_INFO\HDD_INFO.TXT` (`r5==0`) or
`\UserSD\VER_INFO\HDD_INFO.TXT` (`r5==1`) with
`fgetws(buf=r15+0x40, count=0x20 wchar_t)`. It strips CR (U+000D) and LF
(U+000A) via `wcschr` and copies the **whole stripped line** with `wcsncpy`
into inline wide-char fields of the output struct at `r8` in sequence. There is
no key:value split; the separator is the CRLF line boundary. The accept check
requires the measured line length `< (max_wchars - 1)`. The line read buffer is
`r15+0x40` (0x20 `wchar_t`), cleared by `memset(r15+0x42, 0, 0x3e)` plus a
leading NUL word.

| Line | Field name (`tools/hddinfo.py`) | On-disk type | In-memory type (firmware) | Struct offset (`r8+`) | `wcsncpy` max (`wchar_t`) | Factory EU 2011 example |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `base_code` | ASCII text line, CRLF-terminated | `wchar_t[]` (UTF-16LE in memory) | `0x00` | 12 | `QSD-302-100` |
| 2 | `map_set` | ASCII text line, CRLF-terminated | `wchar_t[]` (UTF-16LE in memory) | `0x18` | 12 | `QSD-309-101` |
| 3 | `build` | ASCII text line, CRLF-terminated | `wchar_t[]` (UTF-16LE in memory) | `0x30` | 13 | `02-110100-00` |
| 4 | `map_code` | ASCII text line, CRLF-terminated | `wchar_t[]` (UTF-16LE in memory) | `0x4a` | 12 | `SDC08-EVEUR` |
| 5 | `year_month` | ASCII text line, CRLF-terminated | `wchar_t[]` (UTF-16LE in memory) | `0x62` | 12 | `11-05` |
| 6 | `part_number` | ASCII text line, CRLF-terminated | `wchar_t[]` (UTF-16LE in memory) | `0x7a` | 13 | `470323501005` |

Evidence: M2.1 `--calls 0x004e7b8c --resolve-with 0x3e00200` names
`_wfopen`/`fgetws`/`wcschr`×2/`wcsncpy`/`memset`/`fclose`; dest-pointer table
`r15+0x10+r9` = `r8+{0x00,0x18,0x30,0x4a,0x62,0x7a}` and max table `r15+0x28+r9`
= `{12,12,13,12,12,13}` (C-723–C-727, C-1711). `tools/hddinfo.py` exposes this
as `HDD_INFO_FIELDS` (canonical, self-tested) and keeps byte-identical
parse/serialise of the on-disk file.

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

M2.3 (above) verifies the reader line→slot/struct-offset mapping; model M0's
semantic numeric derivation from lines 1/4 remains part of the hypothesis
(scope note C-735/M2.2):

| Field | Model rule | Source |
| --- | --- | --- |
| `userdata_type` | leading digit of the first number on line 1 (`QSD-3…` → 3); outside `0..5` ⇒ `DIFFERENT MAP CODE` | range check at `0x6fb122`; QSD family guess (C-304). **Scope (C-735/M2.2):** the Navi.exe SD Import *location-record* comparators (`.slc`/`.hlc`, `sub_004e84c4`/`sub_004e989c`) check a *different* `userdata_type` word (`r8+0x12`) by `cmp/eq` to constants `0x1010`/`0x1011`, not `0<x<6` — distinct from this HDD_INFO.TXT model and from the retired chain (C-301/C-521/C-611). |
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

## HDD_CHK.ATT attestation (updater path)

> **Evidence status:** static firmware analysis of `MapUpdate.exe`/`commondll.dll`
> in image B (`IMG256` `92aa525d…`) is `VERIFIED` for the code path and CRC16
> algorithm. `sub_0001e3f4` is **partially decoded** (structure/return semantics,
> CRLF+8B parse) with crypto primitives and the full on-disk layout **deferred**
> (`OBSERVED`/`UNKNOWN`). **Factory EU/US cards carry no `HDD_CHK.ATT` file**
> (verified). Boot-time absence in `Navi.exe` is a `VERIFIED` static negative
> with a positive control, not a runtime proof. EXP-2026-11-06-M2.12-hdd-chk-att,
> EXP-2026-11-06-M2.16-hddchk-att-realcards, C-1870–C-1879, C-2090–C-2096.

**Presence on factory cards (M2.16, C-2090–C-2091):** neither EU `leaf2011.img`
(SHA `105e2032…`) nor US `LEAF_2011-2012_US.img` (SHA `53342430…`) contains an
`HDD_CHK.ATT` data file (extracted roots: `VER_INFO/HDD_INFO.TXT` present,
`*hdd_chk*` absent; full-image chunked search: only the 4 UTF-16LE
`\UserSD`/`\SystemSD\HDD_CHK.ATT` path strings inside `MapUpdate.exe` sec1, CE B
+ its byte-identical copy, same offsets on both images — firmware strings, not
card files). The file is therefore not a factory-card artifact; it is consumed by
the updater path when present/required.

`MapUpdate.exe` (image B) `SilentAuthenticate` (VA `0x0001c210`) checks
`\SystemSD\HDD_CHK.ATT` and `\UserSD\HDD_CHK.ATT` (called for both copies). It
reads `0x80` bytes, decodes 20 hex ASCII chars from an updater-context field
(`ctx+120`) into 10 bytes via `sub_00019eb4`, and requires
`commondll!CApi_MakeCRC16(decoded, 10) == 0`. The CRC16 is bitwise, LSB-first
(reflected): seed `0x0000`, polynomial constant `0x00008408` (CRC-16/CCITT
reflected / KERMIT form, normal poly `0x1021`), no final XOR. On CRC==0 it calls
`sub_0001e3f4(file_buf=ctx+0x11a, decoded=r14+8, bytesRead=0x80)`.

**`sub_0001e3f4` (VA `0x0001e3f4`, M2.16, C-2092–C-2095, partially decoded):**
not a plain memcmp. Returns **1** if `bytesRead > 0xC0`; derives device/transform
material via `*0x21300` ids 5/6 (`sub_199b8`/`sub_19978`) and transforms template
`"VerUp Secret KEY\0\0\0\0"` (`0x157ec`, 16B) / buffers via `sub_1e2d4` (type-2
crypto-context path `0x1e6f8/0x1e834`; transform `!=16` => **return 2**). It
copies `file_buf` (0x80) to `*0x212d8`, incorporates `decoded[0..7]`/`file_buf[0..7]`,
and returns **`sub_1e330`'s result** (saved over `sub_1e270` cleanup).
`sub_1e330` scans the file buffer for CRLF (`0x0d,0x0a`; not found => **3**),
takes the 8 bytes after CRLF as `[p,~p]`, verifies via `sub_1e2d4` against
`0x157ec`, and compares to the derived check value => **0 accept / 3 reject**.
This constrains the 0x80 record to contain CRLF + ≥8B payload; the **exact
on-disk layout, byte-range binding, and crypto primitives remain DEFERRED**
(blocks: CE crypto/provider dispatch identity unresolved; no genuine
`HDD_CHK.ATT` sample on factory cards, C-2096).

**Which modules check it:** only `MapUpdate.exe` references `HDD_CHK.ATT` by
string in IMG256 (B/B-copy). **`Navi.exe` (image A) has no `HDD_CHK.ATT`
reference** (positive control `HDD_INFO.TXT` found in Navi's A segment); image C
has none. Navi boot-path dependence is not indicated by static evidence.

## Offline mutation matrix

| Mutation | Detected by our tools |
| --- | --- |
| flip a `.cmp` byte | yes (zlib Adler-32) |
| truncate `.cmp` | yes |
| `.ind` size/offset wrong | yes |
| `.cmp` legitimately recompressed | no (passes) |
| `DRSTR` size changed | **silent** |
| `HDD_INFO` line 1 changed | **silent** (map-code knob) |
| `HDD_CHK.ATT` changed/missing | silent to our tools; **rejected by `MapUpdate.exe` updater path** (M2.12); **absent on factory EU/US cards** (M2.16, C-2090–2091) |
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
6. If the card is installed/validated through `MapUpdate.exe`, keep
   `\SystemSD\HDD_CHK.ATT` and `\UserSD\HDD_CHK.ATT` valid for its
   `SilentAuthenticate` check (CRC-16/KERMIT residue 0 over the decoded
   10-byte field and `sub_0001e3f4` acceptance of the 128-byte record). The
   exact record layout is still open (M2.12); Navi boot-path dependence is not
   indicated by static evidence.

## Open questions

- The exact **values** of the unit/kernel target-info record
  (`KernelIoControl(0x0101302C)` output `+96`/`+112`/`+114`) for each
  market/unit are not known statically (they live in NAND/system target-info);
  the card-side HDD_INFO bytes and the comparison/range logic are now fully
  specified (M2.15, checks above). The `0x06000000` copy remains unimplicated
  by these two launcher checks but could be used by other (unobserved) paths.
- Does `MMAIN001.DAT`'s `0x1ac` table need to match the tile set exactly, or
   is it informational?
- What is the `BICON001.DAT` data version `11/04/08/01` (vs `11/06/27/01`)?
- Is the TFAT16 volume required at boot, or only for skin/recovery?
- What is the exact on-disk `HDD_CHK.ATT` layout and the full
  `MapUpdate.exe` `sub_0001e3f4`/`sub_1e330` binding to `ctx+120`/`decoded`?
  M2.16 partially decoded it (CRLF+8B-after parse, `sub_1e2d4` crypto-context
  path, returns 0/1/2/3) and confirmed factory EU/US cards carry no
  `HDD_CHK.ATT` file; **deferred** — CE crypto dispatch identity unresolved and
  no genuine sample (C-2092–C-2096).
