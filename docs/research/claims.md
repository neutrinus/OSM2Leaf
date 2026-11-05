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

Evidence should cite the relevant `docs/experiments/EXP-...` record and/or a
`tools/` command. The experiment log is append-only; if a result is corrected,
add a new experiment and mark `Supersedes` / `Superseded by`.

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
| C-030 | `DRSTR001.DAT` has **no header**. The node table starts at `0x0000` with the root node `/`; the 2011 sample has 40 nodes. `0x2f` is the ASCII `/` of the root name, not a count. | VERIFIED | H | EXP-2026-11-05-01; `40*40 + 324*32 = 11968` |
| C-031 | Node records are 40 bytes, name-first: `name[8]` at `+0x00`, `next_index` at `+0x14`, `parent_index+1` at `+0x16`, `entry_count` at `+0x18`, `listing_offset` at `+0x24`. | VERIFIED | H | 40/40 parse; invariants pass |
| C-032 | Listings are 32-byte entries: `name[13]` at `+0x00`, `type` at `+0x16` (0 = file, 2 = dir), `value` at `+0x1c`. | VERIFIED | H | 324 entries; names match FAT |
| C-033 | An earlier "one-node shift" was a parsing artefact: the table starts at `0x0000`, not `0x28`, and each node describes its own listing. | VERIFIED | H | corrected `tools/drstr.py`; listings tile exactly to EOF |
| C-034 | `next_index` is always `index + 1`; its purpose is unknown. | OBSERVED | H | all 40 nodes |
| C-035 | `CMP.LST` contains exactly `\SystemSD\REFER001\` (19 bytes, no newline). | VERIFIED | H | hexdump |
| C-036 | Entry `value`: for `.cmp` files it is the logical uncompressed size (`.ind`, 194/194); for `MAPAL001` tiles it is the **on-disk** size; for directories it is the recursive subtree total (verified for all 39 dirs). | VERIFIED | H | size invariants + FAT cross-check |
| C-037 | `MMAIN001.DAT` is **not** a manifest: no file names, offsets or checksums. It is a format/version descriptor (common header, per-language code list at `0x18c`, 3-section descriptor at `0x1ac`). | VERIFIED (negative) | H | full-byte analysis; CRC/Adler/sum probes negative |
| C-038 | There is no checksum/signature file on the card and no checksum field in `DRSTR001.DAT` or `MMAIN001.DAT`. Integrity of `REFER001` is zlib Adler-32 per 64 KiB chunk. | VERIFIED | H | 194/194 decompressions; field accounting |
| C-039 | The fixed data before the payload may extend to `0x5d6`, not 512 bytes: the 10-byte sequence `80 00 00 00 05 00 fb 50 0b 0b` appears at `0x5cc` in many files. | OBSERVED | M | cross-file hexdump; parser boundary not proven |

## `MAPAL001` tiles

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-040 | There are **45** `BxxRyyR.DAT` tiles plus `LEV3456R.DAT` (76,066,304 bytes), i.e. 46 files. | VERIFIED | H | directory listing + `tools/mesh_grid.py` |
| C-041 | Tiles start with the common 512-byte header, then descriptor tables at `0x1ac` and `0x2ac`. | VERIFIED | H | hexdump |
| C-042 | Tiles contain many small independent zlib streams (`78 9c`). | VERIFIED | H | successful decompression; 3,497,371 streams |
| C-043 | Decompressed streams are structured records, not raster imagery. | VERIFIED | H | 6-byte keys and 16-bit word bodies |
| C-044 | The first stream starts at `0x5200` for ordinary tiles and `0xbe00` for `LEV3456R.DAT`. | VERIFIED | H | all tiles checked |
| C-045 | Tile grid: B/R are hex; `lat_min = int(B,16)*2/3`, `lon_max = 108-int(R,16)`, cell 5.333°×8°. | VERIFIED | H | 45/45 descriptor boxes inside; 44/45 share an exact edge |
| C-046 | `LEV3456R.DAT` is a shared coarse overview covering rows B20–B78 / cols R040–R078 at levels 3–6. | OBSERVED | M | stream keys and levels; role not proven |
| C-047 | `0x2ac` holds 10-byte entries `(level, flags, i16 lat_top, lat_bottom, lon_left, lon_right)` in signed arc-minutes. | VERIFIED | H | boxes match tile names |
| C-048 | Stream prefix: `A = 32768 + lat*192`, `B = 52736 + lon*128`, `u16 tag` selects a table. | VERIFIED | H | 3,497,371 streams, 0 exceptions |
| C-049 | The record grammar inside real payloads is unknown; most payloads are default 448-byte pages. | UNKNOWN | — | 2,374/3,769 in B30R048R; 13 distinct bodies |
| C-050 | Road geometry is split between `MAPAL001` and `RDSTM001` in an unknown way. | UNKNOWN | — | `RDSTM001` has street-like data, tiles have geometry-like data |
| C-051 | There is no `u32` offset table in the tile header; streams are back-to-back with 0–3 bytes padding. | VERIFIED (negative) | H | 4/200 coincidental matches only |
| C-052 | `0x1ac` holds `00 | n_tables | {table_id, n_entries, (level, kind, u16 count)} | 00`. | VERIFIED | H | structure parses in all tiles |
| C-053 | `COORD001` uses longitude origin 52742; the tile stream prefix uses 52736. The 6-unit difference (~0.047°) is unexplained. | OBSERVED | M | independent fits |
| C-170 | ZE0 tiles use zlib `78 9c`; background record kind is `0x00fa` at both levels; the even/odd record pair separates road-shape from background. | VERIFIED | H | EXP-2026-11-05-04 |
| C-171 | `B28R070R`, `B30R060R`, `B58R070R` and `LEV3456R` rebuild byte-identically from the decoded model. | VERIFIED | H | EXP-2026-11-05-04 |
| C-172 | Dense tile `B30R048R` (section 4, directory `0x2146`) does not round-trip yet. | OBSERVED | H | EXP-2026-11-05-04 |
| C-173 | The tile bbox table is fixed at `0x2ac`; ZE0 has 45 grid tiles + `LEV`, not 52. | VERIFIED | H | viewer harness |
| C-174 | There is no layer-11 coastline; the coast is the sea-polygon edge. | OBSERVED | M | decoded geometry |
| C-175 | Drawn road-shape records (even pair) are not decoded yet, so the PNG has no roads; `read_tile` is not streaming. | OBSERVED | H | viewer harness |
| C-250 | Dense `B30R048R` now round-trips byte-identically (1,358,592 B): mask pair flag `0x80000000`, preserve raw slot tails, accept `0x7fffffff`, keep the extra `0x2146` tail and the 55 KiB unreferenced gap. | VERIFIED | H | EXP-2026-11-05-12 |
| C-251 | All five target tiles (`B28R070R`, `B30R060R`, `B58R070R`, `B30R048R`, `LEV3456R`) rebuild byte-identically. | VERIFIED | H | EXP-2026-11-05-12 |
| C-252 | Road-shape records: section 1, even pair, `w2=0x00fa`; level 1 uses a 12-pair layer table, level 2 uses 11 pairs from word 22; shapes are start node + link headers + points + end node. | VERIFIED | H | EXP-2026-11-05-12 |
| C-253 | `B30R060R` roads: 37/37 parsed, 784 shapes, 8,923 points; `B30R048R`: 188/188, 6,270 shapes, 84,470 points; rebuild byte-identical. | VERIFIED | H | EXP-2026-11-05-12 |
| C-254 | Streaming writer handles 73 MB `B40R050R` exactly, max RSS ~120 MB, 0.30 s; grows by relocating the row to EOF and patching the slot tag. | VERIFIED | H | EXP-2026-11-05-12 |
| C-255 | `LEV3456R` level 6: no count word, table at word 11 with 26 `(offset,point-count)` pairs; 156 features, bbox lon −16.05..67.96, lat 30.01..63.18. | VERIFIED | H | EXP-2026-11-05-12 |
| C-256 | Coarse levels 3–5 now rebuild with 0 failures; 1,722 opaque records are preserved verbatim. | VERIFIED | H | EXP-2026-11-05-12 |
| C-257 | Section-4 content (`w2=0x0009`) is still opaque; road names/classes/speeds/one-way and layers 4/6 rendering remain open. | UNKNOWN | — | EXP-2026-11-05-12 |

## `COORD001` / `ZCODE*` / `ICODE001`

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-110 | `COORD001` is a 33-entry table of region bounding boxes at `0x1010`, 14-byte big-endian records, sentinel-terminated; not a point list. | VERIFIED | H | `coord.py` fit |
| C-111 | Coordinate encoding: `lat = (x-32768)/192`, `lon = (y-52742)/128`; rms ~0.031° lat / ~0.073° lon over 33 regions. | VERIFIED | H | least-squares + outlier checks |
| C-112 | `ZCODE0nn` is a character/digit trie; postal-code text is never stored, so `strings` cannot extract it. | VERIFIED (negative) | H | full walk of ZCODE001/010/018 |
| C-113 | ZCODE directory entries are 12 bytes `(size, 0, tag, 0, count, offset)`; leaf records are 8 bytes `(x, y, sub_x, sub_y)` with 11-bit sub-positions. | VERIFIED | H | decoded records |
| C-114 | `ICODE001` starts with 33 per-country administrative schemas, then a flat ASCII place-name database. | VERIFIED | H | schema parse; 111 MB payload |
| C-115 | Region numbering 001–033 is alphabetical by German country name (001 Andorra … 033 United Kingdom). | OBSERVED | H | ICODE schemas + several bounding boxes |
| C-116 | The 2011 map covers Western/Central Europe only; Iceland, Malta, Cyprus, Turkey, Belarus, Ukraine, Russia, Moldova and the Balkans are absent. | OBSERVED | M | 33-region list |

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

## `REFER001` / `REFER002` families

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-130 | REFER payloads share a fixed `0x0200–0x0fff` reserved area; real structure starts at `0x1000`. The old `0xac` rule was a template byte. | VERIFIED | H | 194-file comparison |
| C-131 | Families are sharded by country: 33 numbered regions matching `COORD001`/`ICODE001`; `COORD`/`ICODE`/`ZIPFR` are global. | VERIFIED | H | shard table + region list |
| C-132 | POINT carries an internal ASCII field dictionary with per-field **bit offsets** (area, category, name, address, dndc-id). | VERIFIED | H | `poipoint.py schema` |
| C-133 | POINT records are bit-packed and length-prefixed (`byte[1]=length/2`), stored in pages of exactly 1000. | VERIFIED | H | POINT004/021 counts |
| C-134 | POINT has no **named** lat/lon field, no mesh ID, no `Pre`/`Next` links and no icon-id table; the 4-byte id still decodes as a coordinate. | VERIFIED (negative + decode) | H | targeted scans + coordinate formula |
| C-135 | INTER has a 12-byte record table at `0x1108` plus three zlib streams; offsets index a 6-byte element table. | VERIFIED | H | `decode.py inter` |
| C-136 | ICADM has 33 blocks of 462-byte stride, 7 slots × 64 bytes, with big-endian ISO-3166 numeric codes. | VERIFIED | H | all 33 codes matched |
| C-137 | ZIPFR has 14-byte records `char key[10] + u32 mask`; 36,881 records, 119 distinct masks. | VERIFIED | H | `decode.py zipfr` |
| C-138 | `REFER002` is not a duplicate of `REFER001`; it carries a longer EV schema (xy-coordinates, plug info, parking). | OBSERVED | M | schema comparison |
| C-139 | The `ADDRE0nn` record layout is not yet decoded. | UNKNOWN | — | in progress |
| C-140 | Confirmed factory data families: roads/names (`MAPAL001`/`RDSTM001`/`LCTBL001`), addresses (`ADDRE`), POIs (`POINT`), intersections (`INTER`), freeways (`FRWAY`), admin (`ICADM`), postal (`ZCODE`/`ZIPFR`). | VERIFIED (presence) | H | file families + partial decodes |
| C-141 | Building footprints, forest/landuse polygons, explicit water polygons, speed limits and turn restrictions have **not** been found in the decoded records. | UNKNOWN | — | absence of evidence, not proof of absence |
| C-142 | `MAPAL001` payloads are vector records, so polygon/area record types are technically possible; none identified yet. | UNKNOWN | — | tile grammar partially decoded |
| C-210 | POI `f11 = (2000*page + slot) & 0xffff`; match rates 99.3 % (POINT004) / 95.4 % (POINT021). | VERIFIED | H | EXP-2026-11-05-08 |
| C-211 | POI point A is the display point (inside the COORD001 box in 100 %); B is the address reference (matches street ADDRE ids 95 % vs 10 %). | VERIFIED | H | EXP-2026-11-05-08 |
| C-212 | POI↔ADDRE joins at record level via `(street name, house number)`; the id alone is only a cell. | VERIFIED | H | EXP-2026-11-05-08 |
| C-213 | `BICON001` is a PNG container: header, 103-icon table, PNGs at `0x1408` (32×32, five 30×30). | VERIFIED | H | EXP-2026-11-05-08 |
| C-214 | The POI `icon code` → `BICON001` PNG mapping is unknown; `f0` is a table id, not an icon. | UNKNOWN | — | no icon-id table in POINT |
| C-215 | The bit-packed POI field block cannot be anchored yet: schema offsets need ≥170 bits but only 48 sit between the two ids. | UNKNOWN | — | negative result |
| C-216 | REFER002 EV facilities are a separate set (0 name overlap with REFER001 POINT002); the join mechanism is the same. | OBSERVED | M | name comparison |
| C-143 | `REFER002` has 16 files and is a separate EV/charging POI layer, not an uncompressed copy of `REFER001`. | VERIFIED | H | directory listing + schema |
| C-144 | The FAT contains zero executables; `DRSTR001.DAT` stores logical sizes, not disk offsets, so the FAT is the only location index. | VERIFIED | H | card/FAT research |
| C-145 | REFER001 display names are plain Latin-1 text inside small inner zlib pages, not encrypted or custom-coded. | VERIFIED | H | `scan_refer_names.py` |
| C-146 | A same-length POI rename in `POINT032.DAT` was produced offline: logical size unchanged, changes confined to page `0x4200`, DRSTR unchanged, `cmpind.py verify` 1/1 OK. | VERIFIED | H | EXP-2026-11-05-02; `mutate_refer_poi.py` + `validate_mutation.py` |
| C-147 | No per-file checksum was found in the 512-byte header, `.ind`, `DRSTR001.DAT` or `MMAIN001.DAT`. | VERIFIED (negative) | H | targeted probes |
| C-148 | A whole-card image is the only externally validated clone method; file-level and FAT-only clones are unreported. One OEM tile is fragmented, so contiguity/file order/timestamps do not matter. | OBSERVED | M | card research |
| C-149 | The 2011 image is larger than a common 8 GB card in sectors; use a 16 GB SDHC (not SDXC) for a clone. | OBSERVED | M | sector count + forum reports |
| C-150 | POINT's 4-byte id decodes as `lat=(x-32768)/192`, `lon=(y-52742)/128`; the two copies are usually equal, sometimes differ by a small delta. | VERIFIED | H | cross-match with ADDRE/Monaco/Andorra |
| C-151 | The 24-byte POI index joins the record via `f7`/`f8`; `f11` is a dense POI id only for single-page shards. | OBSERVED | M | five single-page shards |
| C-152 | `REFER002/POINT002.DAT` adds an explicit `xy-coordinates` field; `REFER002/COORD001.DAT` has 22 × 0x18-byte projection-like records. | OBSERVED | M | schema + payload |
| C-153 | ADDRE has a constant `0x500` template, a 22-byte index chain (20,000 records/block), one `0x100` schema block and a variable-length address-record chain. | VERIFIED | H | 33-shard survey |
| C-154 | ADDRE address records contain a 4-byte coordinate id, street-segment end points and upper-case Latin-1 names; the only numeric strings are `:N:;:N:` house-number ranges. | VERIFIED | H | record decode |
| C-155 | POINT and ADDRE share the same 4-byte coordinate ids; ADDRE017 ids occur in POINT017/POINT008. None occur in INTER/FRWAY/ZCODE/ZIPFR. | VERIFIED | H | cross-shard search |
| C-156 | `REFER002` ships no ADDRE and only 15 of 33 POINT shards. | VERIFIED | H | directory listing |

## Firmware

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-060 | A firmware container begins at `0x200000` with `82FX210ECNI.158`, `SUM4`, `470-2824-34`, `NKOK`, `ECEC`, and a size-like `u32 0x01751978`. | VERIFIED | H | hexdump |
| C-061 | No valid PE file exists in the pre-partition area. | VERIFIED | H | byte-by-byte `MZ` scan validating `e_lfanew` and `PE\0\0` returned 0 files |
| C-062 | The firmware area contains five payloads / three builds: A `470-2824-34` at `0x200000`/`0x2000000` (byte-identical), B `470-2759-01` at `0x3e00000`/`0x4800000`, C `470-3142-00` at `0x5200000`. | VERIFIED | H | header hashes + part-number search |
| C-063 | The payload is **uncompressed** SH-4/WinCE code, not a custom-compressed container: entropy ~6.03, capstone decodes clean SH-4, strings/PDB names present. | VERIFIED | H | capstone + strings |
| C-064 | `ECEC` is a fixed field present in all payloads; reading it as the WinCE ROM signature is a hypothesis. | OBSERVED | M | five payloads |
| C-065 | `HCXCmp` is **not** used for map `.DAT` payloads (those are plain zlib). Its firmware role is unknown. | VERIFIED (negative) | H | map decompression + strings |
| C-066 | Firmware strings reference `Navi.exe`, `NaviAPL`, `NaviSearchCC.dll`, `NaviDrawCC.dll`, `NaviRouteCC.dll`, `NaviMapScrollCC.dll`, `NaviRegCC.dll`, `TelemaRouteCC.dll`, `CETUS_SH4`, `C:\WINCE500\PBWorkspaces\10eNavi_UpdateNK`. | VERIFIED | H | `strings` scan |
| C-067 | Firmware strings reference mesh IDs (`MESHID[0x%08X]`, `Mesh[LV1:0x%08X LV2:0x%08X]`, `mesh=%08X x:y=%07d:%07d`). | VERIFIED | H | `strings` scan |
| C-068 | The map path is partially recovered: function at `0xc438a4` builds `\CMP.LST` and opens `\SystemSD\REFER001\`. | OBSERVED | M | Ghidra/capstone analysis |
| C-069 | A TFAT16 volume starts at image offset `0x1C8400400` (OEM `MSWIN4.1`), with a WinCE TFAT hidden root (`DONT_DEL*`). | VERIFIED | H | FAT boot sector |
| C-085 | `SUM4` is a tagged checksum, but CRC-32, Adler-32 and plain word sums were rejected; the algorithm is unknown. | UNKNOWN | — | checksum probes |
| C-086 | For the map module's data, `VA = file_offset + 0x02000000`; code literals use at least one other delta, so the ROM is section-based. | OBSERVED | M | 21 pointer literals |
| C-087 | The pre-partition payload length is declared as `0x01752c88` (24,456,328 bytes) at `0x200000`; the bytes immediately after that offset are not a zero gap. | VERIFIED | H | header + byte check |
| C-180 | The 24-byte ROM section records at `0x374000`/`0x3e0060` are `o32_rom`-shaped, but their `dataptr` fields point into `0xff` fill and the records do not share a delta. The table is **not usable** as a file map. | VERIFIED (negative) | H | EXP-2026-11-05-05 |
| C-181 | For the map module, two deltas suffice: code `VA = file + 0x02200000` (`0xc00000–0xc4b000`), `.rdata` `VA = file + 0x02000000` (`0xdf6000–0xe10000`). | VERIFIED | H | Ghidra code density + 21 literals |
| C-182 | Reader-related functions: `0xc438a4` opens `\CMP.LST`; `0xc42520` dumps a file descriptor incl. `hcxcmp`; `0xc426a4` dumps dir/file counts; `0xc48380` installs `MAP_DATA READ`; `0xc0ebf8` allocates `0x1ac`. | OBSERVED | H | EXP-2026-11-05-05 |
| C-183 | The `.ind`/`.cmp` reader, `DRSTR` parser and tile reader are not located yet: filenames use a fixed 16-byte table at `0xdf8120`, and constants (`0x10000`, `40`, `0x1ac`) are built from immediates+shifts. | UNKNOWN | — | EXP-2026-11-05-05 |
| C-200 | Map filenames have **zero literal references** in the payload for every plausible delta; readers are name-driven through `DRSTR001.DAT` and `CMP.LST`. | VERIFIED (negative) | H | EXP-2026-11-05-07 |
| C-201 | The 16-byte table at `0xdf8120` is reporting/update-tool data, not the runtime tile/file selector. | OBSERVED | M | EXP-2026-11-05-07 |
| C-202 | The two-delta model is local to the module at `0xc00000–0xc4b000`; shared `.rdata` is mapped at other VAs elsewhere. Accept a delta only when ≥4 pointer slots resolve to real strings. | VERIFIED | H | 10-slot table at `0xa9cf8c` |
| C-203 | Map-code check is a text/field comparison of `HDD_INFO.TXT` (`Sys[...] SD[...]`, `userdata_type`, `manufacturer_id`, `destination_id`), not crypto. | VERIFIED | H | strings |
| C-204 | The `0x06000000` copy is likely the system-side reference for that comparison; the exact line↔field mapping is unknown. | HYPOTHESIS | M | string context |
| C-205 | The literal `"DIFFERENT MAP CODE"` is absent from build A; nearest hits are unrelated. | VERIFIED (negative) | H | string scan |
| C-206 | No runtime map-content checksum beyond zlib Adler-32; the ASN.1/crypto provider is not linked to the map path. | VERIFIED | H | xref/call scan |
| C-207 | fd field `+0xC4` is a type tag (switch 7…15), not `hcxcmp`. | VERIFIED | H | decompilation |
| C-208 | `DRSTR` layout is confirmed file-side but the parser code is silent (no 40-byte stride multiply in the map module). | VERIFIED / UNKNOWN | H | file arithmetic + code scan |
| C-220 | `obj+0x78…+0x9c` is a **message catalogue**, not a vtable: the stored values are string pointers. Image-wide there are 28 dispatches through those slots, but zero in the map module; the map module dispatches through `+0x04/+0x08/+0x18`. | VERIFIED | H | EXP-2026-11-05-09 |
| C-221 | The four functions `0xc412ca`/`0xc42a7a`/`0xc42ba6`/`0xc42e30` are read-only classifiers, not fd writers. The struct is a state descriptor keyed by `(0xAC,0xB4,0xB8)`; `+0xC4` is a separate type tag. | VERIFIED | H | EXP-2026-11-05-09 |
| C-222 | File `0x877740` holds `Lib.out32.dll` and a string table with data delta `0x01e00000`; it contains a zlib copy (`z_errmsg` strings). Its code delta is unknown. | OBSERVED | H | EXP-2026-11-05-09 |
| C-223 | The `HDD_INFO` comparison function is not located; the `shll2`-scaled index into `0xa9cf8c` is missing. Best candidate caller is `0x132e06c` (delta `0x2180000`), unproven. | UNKNOWN | — | EXP-2026-11-05-09 |
| C-224 | No 40-byte stride, `mov #5`+`shll3`, or `0x28` multiply exists in the payload; the DRSTR parser is not located from code. | VERIFIED (negative) | H | EXP-2026-11-05-09 |
| C-225 | The tile reader is not located; it depended on the non-existent vtable. Only the `MAP_DATA`/`MESH_ID` strings and the `0x1ac` allocation remain. | UNKNOWN | — | EXP-2026-11-05-09 |
| C-230 | The `Lib.out32` code delta is not pinnable: its pool is only data-referenced, and prologue scoring over 473 targets is flat. The module identity is weakened, not refuted. | VERIFIED (negative) | H | EXP-2026-11-05-10 |
| C-231 | The `.ind` parser is not detectable by the tested shapes: 0 sites for `mov #1; shll16`, 0 literal `0x10000`, 0 runs of four `mov.l @Rm+,Rn`. | VERIFIED (negative) | H | EXP-2026-11-05-10 |
| C-232 | `0x132e06c` is data, not code; the `0xa9cf8c` table has no literal reference. The `HDD_INFO` comparator remains unknown. | VERIFIED (negative) | H | EXP-2026-11-05-10 |
| C-233 | Root cause: ROM sections use independent `(file offset, VA)` pairs and shared `.rdata` has ≥3 deltas; single literal→string hits are unreliable. | VERIFIED | H | EXP-2026-11-05-10 |
| C-234 | Record `0x3221b0` decodes only if `dataptr` is payload-relative (`0x11000 → 0x211000`), implying delta `0x8c97b000`; 0/21 literals land on prologues. | OBSERVED | M | open lead |
| C-235 | Next targets: copy/section descriptor list at `0x1952b00` (32-byte records) and export tables at `0x29eec0–0x29f700`. | PLANNED | — | EXP-2026-11-05-10 |
| C-240 | PE export directories give a stable file base: TFAT.dll at `0x28e200`, 35/35 name-RVAs resolve, 34/35 exports are SH-4 prologues; `file = Fb + RVA`. | VERIFIED | H | EXP-2026-11-05-11 |
| C-241 | `module_scan.py` maps 26 modules (TFAT, DISKCACHE, FATUTIL, OLEAUT32, …). | VERIFIED | H | EXP-2026-11-05-11 |
| C-242 | VA base is recovered as constant `V − RVA` across exports; OLEAUT32 `Vb=0x03930000` verified with 282 literal sites (166 `jsr`). | VERIFIED | H | EXP-2026-11-05-11 |
| C-243 | `0x1952b00` is a RAM copy list, not a section map: no file offsets, sizes do not tile, and the value is not a CRC32. | VERIFIED (negative) | H | EXP-2026-11-05-11 |
| C-244 | The navi/map modules have no export directory in `0x44xxxx–0x1952c88`. | VERIFIED (negative) | H | EXP-2026-11-05-11 |
| C-245 | Import-descriptor candidates for navi modules are noisy/unverified; harden with ≥4 VA-like thunks + an IAT run into one of the 26 mapped modules. | OBSERVED | M | EXP-2026-11-05-11 |
| C-246 | The readers are still not located; nothing about the data formats is contradicted. | UNKNOWN | — | EXP-2026-11-05-11 |

## Validation / checksums

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-160 | Main ROM `SUM4` is at header `+0x34`, computed as the sum of LE `u32` words over `[0x200200, 0x200200+length)`, length `0x01752c88`; value `0xcdf87db0`. It ends before the FAT partition. | VERIFIED | H | recomputed from bytes |
| C-161 | Updater image checksum: `u16` at `+0x230`, `u32` length at `+0x232`, byte sum over `[0x200, 0x200+len)` with the checksum bytes zeroed; value `0x12aa`. | VERIFIED | H | recomputed from bytes |
| C-162 | No per-file checksum/signature exists in `DRSTR001.DAT`, `MMAIN001.DAT`, headers or `HDD_INFO`; 23-file hash hunt found 0 hits. | VERIFIED (negative) | H | `hash_hunt.py` |
| C-163 | `DRSTR001.DAT` covers every logical file exactly once (285 files + 39 dirs); only `DRSTR001.DAT` itself is absent. | VERIFIED | H | full accounting |
| C-164 | `MMAIN001.DAT` `0x1ac` 11-entry table equals the sum over all 46 `MAPAL001` files (incl. `LEV3456R`), 11/11. | VERIFIED | H | table comparison |
| C-165 | `DIFFERENT MAP CODE` is a UTF-16 string at firmware `0x04136abc`; nearby launcher code reads `HDD_INFO.TXT` and checks `MapDBVer`. Line 1 is likely a market/family code (JP 300, US 301, EU 302), not a per-card activation. | OBSERVED / HYPOTHESIS | M | firmware strings + external QY-7204 |
| C-166 | The 402 MB post-partition tail is a second FAT16/TFAT16 volume containing skin data, not map data. | OBSERVED | M | FAT header + contents |
| C-167 | `BICON001.DAT` is the only map file with a different data version (`11/04/08/01` vs `11/06/27/01`). | OBSERVED | M | header comparison |
| C-168 | Only ~61 % of a tile's post-`0x5200` payload is inside zlib streams; the rest is alignment padding and fixed tables. There is no per-tile digest. | VERIFIED | H | stream accounting |

## Writers

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-190 | A preserved-stream `.cmp`/`.ind` writer rebuilds all 194 pairs byte-identically. | VERIFIED | H | EXP-2026-11-05-06 |
| C-191 | Stock zlib 1.3.1 at level 6 / wbits 15 / memLevel 8 / default strategy reproduces all 36,581 factory chunks. | VERIFIED | H | EXP-2026-11-05-06 |
| C-192 | zlib-ng reproduces 0/194 `.cmp` files; on such a machine, byte-identity requires preserved streams. | VERIFIED | H | EXP-2026-11-05-06 |
| C-193 | Build rule: unchanged files preserve streams; changed files recompress only affected 64 KiB chunks; new files pin a fixture-checked compressor. | VERIFIED (procedure) | H | EXP-2026-11-05-06 |
| C-194 | The `DRSTR001.DAT` writer reproduces the EU 2011 file byte-for-byte (11,968 B). | VERIFIED | H | EXP-2026-11-05-06 |
| C-195 | Pre-write fixtures: `COORD001` `6074a93c…`, `POINT032` `1dac3ae6…`, `ADDRE001` `bbeb60f2…` (`.cmp` SHA-256). | VERIFIED | H | EXP-2026-11-05-06 |

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
| C-120 | 2011, 2014 and 2016 ZE0-era images share `CLA-NAVI05-01` / `X08-02-00` / `V05.00.00`, the same 45 tile names and 194 `.cmp`/`.ind` pairs. | VERIFIED | H | image comparison |
| C-121 | In `HDD_INFO.TXT`, line 1 is a constant base code, line 2 tracks the map set and matches the FAT volume label, line 5 is year-month. | OBSERVED | H | 2011/2014/2016 comparison |
| C-122 | `TFTBL001/` appears in the 2014 and 2016 sets but not 2011; `REFER002/ICODE001.DAT` appears from 2013. | OBSERVED | H | top-level diff |
| C-123 | The 2019 e-NV200 image is a different engine: `CLA-NAVI06-01` / `X08-03-00` / ZENRIN, `DB_INFO.TXT`, partition at sector 888833, 14,827 files. | VERIFIED | H | image inspection |
| C-124 | ZE0-era cards carry three volumes: ~100 MiB firmware area, 7.55 GiB FAT32 map partition, and a TFAT16 volume at image offset `0x1C8400400`. | VERIFIED | H | FAT boot sector at that offset (`MSWIN4.1`, `TFAT16`) |
| C-125 | The `EU_MAPDATA_*.7z` archives are repacks of the card images, not independent builds. | OBSERVED | H | matching `MMAIN001.DAT` hashes |

## How to use this ledger

- When you verify or refute a claim, update its row and add the command/output
  to the evidence column.
- When you add a new claim, give it the next free ID in its section.
- Keep `docs/format/*.md` consistent with this file; the ledger wins if they
  disagree.
- Do not promote `OBSERVED`/`HYPOTHESIS` to `VERIFIED` without a reproducible
  check that another agent can run.
