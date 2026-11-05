# Claims and evidence ledger

This is the canonical list of what we know, what we think we know, and what we
do not know. Other researchers and agents should use these IDs when referring
to a finding, disputing it, or extending it.

## Status labels

| Label | Meaning |
| --- | --- |
| **VERIFIED** | Reproduced directly from the sample bytes with a script; another person can re-run the check. |
| **OBSERVED** | Seen in the data, but the interpretation is not proven. |
| **HYPOTHESIS** | A plausible explanation that fits current evidence but has not been confirmed. |
| **UNKNOWN** | No reliable answer yet. |

Confidence: **H** = high, **M** = medium, **L** = low.

When a claim changes status, update this file and note the evidence in the
commit message. Do not silently promote a hypothesis to a fact.

## Reference sample

| Item | Value |
| --- | --- |
| Image | `LEAF_2011-2012_QSD-309-101_navi158_eu.img` |
| Image size | 8,057,257,984 bytes |
| Image SHA-256 | `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307` |
| Source | <https://files.viaaq.eu/sd-images/> |

Per-file SHA-256 of the extracted samples used below:

```
240e7c9774197fff0ea85276d463658d1291f4147970ccd5fdec60ffd23e9a05  MMAIN001.DAT
2b7f2fb8901bf18a2ad48334154a6d604c23a775083cb84754626d64417b25f6  DRSTR001.DAT
88883eb953dd526d56e56ce9de9afa957a8b4f0e4781fb4ced0ccd7547761162  CMP.LST
9f014643ed9f4e1359d418f415f264f943e027669b872fc7675f3d99d9bc650a  VER_INFO/HDD_INFO.TXT
6074a93c27081bf3e770411a549f4427721cd5bd44ef3198473ef03742956ed1  REFER001/COORD001.DAT.cmp
f0b8cad0d3d2d12de66448b813dca9ede96b4c0280161e3a11dc6646795b4e7b  REFER001/COORD001.DAT.ind
bbeb60f242a57f297d2d2c6d7180b8b68e57a2bec90fcbfd699eead7271a7025  REFER001/ADDRE001.DAT.cmp
98030b99834c30cd87c64d39f3f31ba94c6067248ce41529689baebe6a5df540  REFER001/ADDRE001.DAT.ind
0e4df38b659e99129c1e55f1ad16219d73e713677edd4ee3756b8ce7e74b2ddb  MAPAL001/B28R070R.DAT
08a584feacf049cc39260ff29f742c3dcf1b53059cb98bd3e9798e7ab819df35  MAPAL001/LEV3456R.DAT
f822044c0aab75327b9fb484e9a4c7c8dd5938b21efaacec0e5b2d8b23ab3e49  RDSTM001/RDSTM001.DAT
8cab17754114b5f7ca47d4f46d55c95c6acf841629e1fcc42e6da45063353e9d  RDSTM001/LCTBL001.DAT
```

## Card / image

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-001 | The EU 2011 image is 8,057,257,984 bytes with SHA-256 `105e2032…76307`. | VERIFIED | H | `sha256sum`, `stat` |
| C-002 | It has an MBR with exactly one partition, type `0x0b`, start LBA 204802. | VERIFIED | H | `fdisk -l`, `7z l`, MBR bytes at `0x1be` |
| C-003 | The FAT32 volume label is `QSD-309-101`; cluster size 65,536 bytes. | VERIFIED | H | FAT boot sector, `7z l` |
| C-004 | The filesystem contains 39 directories, 480 files, 5,173,965,667 bytes. | VERIFIED | H | `7z x`, `find`, `du` |
| C-005 | `VER_INFO/HDD_INFO.TXT` contains six CRLF-separated lines: `QSD-302-100`, `QSD-309-101`, `02-110100-00`, `SDC08-EVEUR`, `11-05`, `470323501005`. | VERIFIED | H | hexdump of the 72-byte file |
| C-006 | The 100 MB before the FAT partition contains Clarion records (`CLARION ID` at `0x200`) and a firmware container at `0x200000`. | VERIFIED | H | raw bytes, see [firmware.md](../format/firmware.md) |
| C-007 | The 402,652,160-byte post-partition tail is almost entirely non-zero (400,365,370 bytes). | VERIFIED | H | byte scan |
| C-008 | The purpose of the post-partition tail is unknown. | UNKNOWN | — | no successful parser yet |
| C-009 | The map validity/activation mechanism (checksum, signature, CID binding, version code) is unknown. | UNKNOWN | — | no matching code or test yet |

## Common file header

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-010 | Most map files start with a 512-byte header containing the UTF-16**BE** strings `CLARION`, `HITACHI`, `CLA-NAVI05-01`, `FORMAT VERSION X08-02-00`, `DATA VERSION 11/06/27/01`, `V05.00.00`. | VERIFIED | H | hexdump of `MMAIN001.DAT`, `MAPAL001/*.DAT`, `RDSTM001.DAT`, `BICON001.DAT`, decompressed `REFER001` payloads |
| C-011 | The header contains a file-type-specific binary descriptor at `0x180`. | VERIFIED | H | identical prefix `ff ff 24 ff 12 c0 05 00 fb 50 0f f0`, then per-type bytes |
| C-012 | The meaning of the descriptor fields is unknown. | UNKNOWN | — | not decoded |
| C-013 | `DRSTR001.DAT` does not use this 512-byte header. | VERIFIED | H | first bytes are a 32-bit count + binary records |

## `.cmp` / `.ind`

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-020 | `.ind` is little-endian: `u32 uncompressed_size, u32 compressed_size, u32 chunk_count, u32 chunk_size, u32 chunk_offset[chunk_count]`. | VERIFIED | H | matches all 194 pairs; see [cmp-ind.md](../format/cmp-ind.md) |
| C-021 | `ind_size == 16 + 4 * chunk_count`. | VERIFIED | H | 194/194 |
| C-022 | `chunk_size` is `0x10000` (65,536) in every examined file. | VERIFIED | H | 194/194 |
| C-023 | Each chunk is an independent zlib stream; concatenating decompressed chunks yields exactly `uncompressed_size` bytes. | VERIFIED | H | 194/194, `tools/cmpind.py verify` |
| C-024 | Naive `zlib.decompress()` on the whole `.cmp` only returns the first stream and silently truncates large files. | VERIFIED | H | `ADDRE001`: 65,536 of 79,360 bytes |
| C-025 | The decompressed payload still starts with the 512-byte header. | VERIFIED | H | `COORD001` decompressed size 4,608 = 512 + 4,096 |
| C-026 | The record format inside address/POI payloads is not decoded. | UNKNOWN | — | only strings such as `STREET`, `area code`, `street name`, `dndc-id` observed |

## `DRSTR001.DAT`

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-030 | `DRSTR001.DAT` has **no header**. The node table starts at `0x0000` with the root node `/`; the 2011 sample has 40 nodes. `0x2f` is the ASCII `/` of the root name, not a count. | VERIFIED | H | `40*40 + 324*32 = 11968`; cross-checked on 2014/2016 |
| C-031 | Node records are 40 bytes, name-first: `name[8]` at `+0x00`, `next_index` at `+0x14`, `parent_index+1` at `+0x16`, `entry_count` at `+0x18`, `listing_offset` at `+0x24`. | VERIFIED | H | 40/40 parse; invariants pass |
| C-032 | Listings are 32-byte entries: `name[13]` at `+0x00`, `type` at `+0x16` (0 = file, 2 = dir), `value` at `+0x1c`. | VERIFIED | H | 324 entries; names match FAT |
| C-033 | An earlier "one-node shift" was a parsing artefact: the table starts at `0x0000`, not `0x28`, and each node describes its own listing. | VERIFIED | H | corrected `tools/drstr.py`; listings tile exactly to EOF |
| C-034 | `next_index` is always `index + 1`; its purpose is unknown. | OBSERVED | H | all 40 nodes |
| C-035 | `CMP.LST` contains exactly `\SystemSD\REFER001\` (19 bytes, no newline). | VERIFIED | H | hexdump |
| C-036 | For file entries, `value` is the logical size (`.ind` uncompressed size, 194/194). For directory entries it is the recursive subtree total (verified for all 39 dirs). | VERIFIED | H | size invariants + FAT cross-check |
| C-037 | `MMAIN001.DAT` is **not** a manifest: no file names, offsets or checksums. It is a format/version descriptor (common header, per-language code list at `0x18c`, 3-section descriptor at `0x1ac`). | VERIFIED (negative) | H | full-byte analysis; CRC/Adler/sum probes negative |
| C-038 | There is no checksum/signature file on the card and no checksum field in `DRSTR001.DAT` or `MMAIN001.DAT`. Integrity of `REFER001` is zlib Adler-32 per 64 KiB chunk. | VERIFIED | H | 194/194 decompressions; field accounting |
| C-039 | The fixed data before the payload may extend to `0x5d6`, not 512 bytes: the 10-byte sequence `80 00 00 00 05 00 fb 50 0b 0b` appears at `0x5cc` in many files. | OBSERVED | M | cross-file hexdump; parser boundary not proven |

## `MAPAL001` tiles

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-040 | There are 46 tiles named `BxxRyyR.DAT` plus `LEV3456R.DAT` (76,066,304 bytes). | VERIFIED | H | directory listing |
| C-041 | Tiles start with the common 512-byte header, then a sparse descriptor area. | VERIFIED | H | hexdump |
| C-042 | Tiles contain many small independent zlib streams (`78 9c`). | VERIFIED | H | successful `zlib.decompress` from `0x5200` in several tiles, `0xbe00` in `LEV3456R.DAT` |
| C-043 | Decompressed streams are structured records, not raster imagery. | OBSERVED | M | first bytes look like record/coordinate data |
| C-044 | The first stream starts at `0x5200` for ordinary tiles and `0xbe00` for `LEV3456R.DAT`. | OBSERVED | M | sample of 4 files; must be checked on all 46 |
| C-045 | The `B`/`R` filename components encode a mesh/grid position. | HYPOTHESIS | L | naming pattern only; no decoded mapping |
| C-046 | `LEV3456R.DAT` is a shared multi-level table. | HYPOTHESIS | L | name and size |
| C-047 | The descriptor at `0x2b0` contains signed fixed-point deltas. | HYPOTHESIS | L | values such as `0xfd30` = -720 look like deltas |
| C-048 | The tile-to-latitude/longitude mapping is unknown. | UNKNOWN | — | no correlation with coordinates yet |
| C-049 | The record format inside decompressed tile streams is unknown. | UNKNOWN | — | not decoded |
| C-050 | Road geometry is split between `MAPAL001` and `RDSTM001` in an unknown way. | UNKNOWN | — | `RDSTM001` has street-like data, tiles have geometry-like data |

## `RDSTM001.DAT` / `LCTBL001.DAT`

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-100 | `LCTBL001.DAT` is a catalog + zlib-compressed name database, not a raw string table: catalog at `0x1000`, 517 streams from `0x316600`. | VERIFIED | H | `tools/lctbl_names.py verify` |
| C-101 | The catalog has 90 `Location Data` descriptors and a 12-column road schema (`kind code`, `road no`, `road name`, `first/second name`, `area ref`, `liner ref`, offsets, `urban`, exit/junction, Inter-section code). | VERIFIED (names) / HYPOTHESIS (semantics) | H | descriptor hexdumps |
| C-102 | The 517 streams decompress to 11,481,060 bytes containing 328,628 NUL-terminated Latin-2 strings (231,033 unique). | VERIFIED | H | `lctbl_names.py verify` |
| C-103 | The name hierarchy runs continent → country → region → district → municipality → street; Czech names are first, Norwegian/French last. | OBSERVED | H | `lctbl_names.py names` |
| C-104 | `RDSTM001.DAT` has no zlib streams and no inline ASCII names; it is dense packed binary. | VERIFIED (negative) | H | `rdstm_scan.py zlib --bruteforce` |
| C-105 | The `0x1000` table in `RDSTM001.DAT` shares 2-byte codes with the LCTBL catalog (10/16 first rows match). | VERIFIED | H | `rdstm_scan.py codes` |
| C-106 | The `0x1000` record framing is not a constant 16 bytes; it changes after `0x10a0`. | OBSERVED | H | hexdump |
| C-107 | Grid hypothesis: B/R are hex; `lat_min = int(B,16)*2/3`, `lon_max = 108-int(R,16)`, cell 5.333°×8°. `B48R058R` covers Prague and Czech names are first. | HYPOTHESIS | M | fits one sample; not proven |
| C-108 | Speed, direction, turn restrictions and `INTER`/`FRWAY` IDs were not found in `RDSTM001`/`LCTBL001`. | UNKNOWN | — | targeted scans negative |

## Firmware

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-060 | A firmware container begins at `0x200000` with `82FX210ECNI.158`, `SUM4`, `470-2824-34`, `NKOK`, `ECEC`, and a size-like `u32 0x01751978`. | VERIFIED | H | hexdump |
| C-061 | No valid PE file exists in the pre-partition area. | VERIFIED | H | byte-by-byte `MZ` scan validating `e_lfanew` and `PE\0\0` returned 0 files |
| C-062 | The firmware payload is duplicated at several offsets and separated by `0xff` gaps. | VERIFIED | H | entropy map and byte comparison |
| C-063 | The firmware uses a custom compression/container instead of plain PE modules. | HYPOTHESIS | M | `HCXCmpLib`/`hcxcmp` strings, `ECEC` marker, packed copies; not yet decoded |
| C-064 | `ECEC` is a compression magic. | HYPOTHESIS | L | position in the container header |
| C-065 | `HCXCmp` also applies to map `.DAT` payloads. | HYPOTHESIS | L | contradicted for `REFER001` (plain zlib) and tiles (plain zlib); may apply only to firmware |
| C-066 | Firmware strings reference `Navi.exe`, `NaviAPL`, `NaviSearchCC.dll`, `NaviDrawCC.dll`, `NaviRouteCC.dll`, `NaviMapScrollCC.dll`, `NaviRegCC.dll`, `TelemaRouteCC.dll`, `CETUS_SH4`, `C:\WINCE500\PBWorkspaces\10eNavi_UpdateNK`. | VERIFIED | H | `strings` scan |
| C-067 | Firmware strings reference mesh IDs (`MESHID[0x%08X]`, `Mesh[LV1:0x%08X LV2:0x%08X]`, `mesh=%08X x:y=%07d:%07d`). | VERIFIED | H | `strings` scan |
| C-068 | The firmware reader/decompressor logic is not yet inspected. | UNKNOWN | — | PE files not extractable yet |

## Market / version

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-070 | The US 2011 card layout is assumed to be close to the EU one but is not verified. | HYPOTHESIS | L | same ZE0 generation, different market |
| C-071 | Newer map sets contain additional files such as `TFTBL001` absent from the 2011 EU image. | OBSERVED | M | wiki screenshot; must be confirmed against a real newer image |
| C-072 | The exact meaning of `SDC08-EVEUR` is unknown (likely map/region/version code). | UNKNOWN | — | only appears in `HDD_INFO.TXT` |
| C-073 | In the EU image, `\x82FX210ECNI.158` starts at `0x00200014` and the version digits `158` start at `0x0020001f`. | VERIFIED | H | `leaf2011.img` hexdump |
| C-074 | The 72-byte `HDD_INFO.TXT` block appears byte-identically at image offset `0x06000000`. | VERIFIED | H | byte comparison |
| C-075 | SD lock is a CMD42 password (4 unit-specific bytes + ASCII `Clarion95321`), not file encryption; the unit stores it in flash near `0xA100`. | OBSERVED | M | external teardown/forum research; not tested by us |
| C-076 | `NAVI VERSION NG` compares the ASCII version at SD `0x20001f` with the unit's `NAVI-1`. | HYPOTHESIS | M | external research |
| C-077 | `DIFFERENT MAP CODE` compares `HDD_INFO.TXT` line 1 with the unit's stored map record. | HYPOTHESIS | M | external research |
| C-078 | The unit market is a PROD-block byte at `0xA022` (`0x10` JP/world, `0x20` US, `0x30` EU, `0x40` RU, `0x50` CN), checked by `AppLaunch.dll` via `CApi_GetModelArea`. | HYPOTHESIS | M | external research |
| C-079 | Navi app (`NB00` card / `NB04` NAND) and audio CPU firmware (`70F3355` JP, `70F3356` US, `70F3357` EU) are market-specific builds. | HYPOTHESIS | M | external research |
| C-080 | A US QY7210NN reportedly booted and drew European streets from an EU card. | OBSERVED | M | leafsdtools issue #3; not reproduced by us |
| C-081 | A JP→EU conversion (PROD + EU loader + EU card) produced EU UI/map/languages but lost all audio. | OBSERVED | M | external teardown; not reproduced by us |
| C-082 | `SECURE` is a CAN/VIN anti-theft check; clearing PROD `A0A0–A0A3` or grounding `TEST_B1` disables it. | OBSERVED | M | external research |
| C-083 | A full, reproducible US→EU conversion recipe is unknown; commercial converters exist but success/audio survival is unproven. | UNKNOWN | — | no published recipe |
| C-084 | The map database is not region-locked at file level; the blocker is unit region/coordinate/firmware logic. | HYPOTHESIS | M | follows from C-080; not proven |

## How to use this ledger

- When you verify or refute a claim, update its row and add the command/output
  to the evidence column.
- When you add a new claim, give it the next free ID in its section.
- Keep `docs/format/*.md` consistent with this file; the ledger wins if they
  disagree.
- Do not promote `OBSERVED`/`HYPOTHESIS` to `VERIFIED` without a reproducible
  check that another agent can run.
