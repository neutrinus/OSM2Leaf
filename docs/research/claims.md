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
| C-030 | The file starts with `u32 0x2f` (47) followed by zero padding to `0x28`. The value is **not** the node count; its meaning is unknown. | VERIFIED (bytes) / UNKNOWN (meaning) | H | first `0x28` bytes; only 39 nodes parse |
| C-031 | There are 39 node records of 40 bytes starting at `0x28`, **name first**: `name[8]` at `+0x00`, zeros at `+0x08..+0x13`, `next_index` at `+0x14`, `type` at `+0x16`, `entry_count` at `+0x18`, `listing_offset` at `+0x24`. | VERIFIED | H | 39/39 clean parse; listings match FAT |
| C-032 | Listings are 32-byte entries: `name[12]` at `+0x00`, zeros, `type` at `+0x16` (0 = file, 2 = dir), `value` at `+0x1c` (logical size for files). | VERIFIED | H | `REFER001`/`REFER002` sizes match `.ind` uncompressed sizes |
| C-033 | An earlier "one-node shift" was a parsing artefact: the record name is at `+0x00`, not `+0x18`. With the correct layout each node describes its own listing. | VERIFIED | H | corrected `tools/drstr.py`; 39 nodes, each listing matches its directory |
| C-034 | The meaning of `next_index` is not proven (it increases by one per record). | OBSERVED | M | field values 2,3,4,… |
| C-035 | `CMP.LST` contains exactly `\SystemSD\REFER001\` (19 bytes, no newline). | VERIFIED | H | hexdump |
| C-036 | `value` at entry `+0x1c` is the logical uncompressed size for files. For map tiles it can exceed the on-disk size and is probably the total decompressed payload. | OBSERVED | M | `MAPAL001` entries vs file sizes |

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

## How to use this ledger

- When you verify or refute a claim, update its row and add the command/output
  to the evidence column.
- When you add a new claim, give it the next free ID in its section.
- Keep `docs/format/*.md` consistent with this file; the ledger wins if they
  disagree.
- Do not promote `OBSERVED`/`HYPOTHESIS` to `VERIFIED` without a reproducible
  check that another agent can run.
