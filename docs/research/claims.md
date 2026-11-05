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
| C-280 | Section 4 is a per-parcel **administrative/place-name index**, not geometry: `B30R048R` has 20 records / 68 names; word 8 is the ISO country (300 = Greece). | VERIFIED | H | EXP-2026-11-05-15 |
| C-281 | Road names: shape header word 4 is the name offset in the odd partner record; 297/1,195 named in `B30R060R`, 1,972/10,667 in `B30R048R`. | VERIFIED | H | EXP-2026-11-05-15 |
| C-282 | Road style/class is raw; one-way/speed mapping from style bits is a hypothesis (`0x201e` two-way, `0x001e` ferry). | HYPOTHESIS | M | EXP-2026-11-05-15 |
| C-283 | Streaming decoder handles 436 MB `B48R060R`: 2,710,087 features, ~40 s, 242 MB RSS. | VERIFIED | H | EXP-2026-11-05-15 |
| C-284 | `harness.py compare-tiles` gives ZERO DIFF on an unchanged copy and DIFFERS on a one-vertex mutation. | VERIFIED | H | EXP-2026-11-05-15 |
| C-285 | The viewer's negative RDSTM/LCTBL cross-reference is incomplete and superseded by `docs/format/rdstm.md` (LCTBL has 517 name streams; RDSTM has no zlib). | VERIFIED (correction) | H | EXP-2026-11-05-15 |
| C-286 | Section-4 binary fields between country and names are not fully mapped; there is no ZE0 section-4 encoder. | UNKNOWN | — | EXP-2026-11-05-15 |
| C-290 | Map-code comparator at file `0x6fafe4`–`0x6fb194`, data delta `0x02800000`; numeric `Sys[0x%x]` vs `SD[0x%x]` for `manufacturer_id`, `userdata_type`, `destination_id`. | VERIFIED | H | EXP-2026-11-05-16 |
| C-291 | One field is range-checked `0 <= v < 6`; mismatches report “finished not found” / “type not correct”. | VERIFIED | H | EXP-2026-11-05-16 |
| C-292 | A second module at file `0x1683xxx` uses code delta `0x0200e438` (4/7 pointers land on function starts). | OBSERVED | M | EXP-2026-11-05-16 |
| C-293 | The six `HDD_INFO` lines ↔ three fields mapping is unknown; `SDC08`/`EVEUR` resemblance is a guess. | UNKNOWN | — | EXP-2026-11-05-16 |
| C-294 | Tile contract: intra-mesh coordinates are `0..2047` (11-bit); `MESHMAX_LEV1` mesh validation exists; structures `area_link`, `cvdata`, `rgd_t`, `RGD_commem`. | VERIFIED | H | diagnostic strings |
| C-295 | Dump headers document a six-level table (`VTb Tp;Lv;…|L1..L6|Sz;Adr`) and the file descriptor (`HFile;FileID;Tp;Lv;V#;la Lo`). | OBSERVED | H | strings at `0xdf65a1`, `0xdf6621` |
| C-296 | `0x1ac` is **not** the tile level table: it is a 428-byte per-object OSM buffer for `obj+0x40`. | VERIFIED (retraction) | H | EXP-2026-11-05-16 |
| C-297 | Closure experiment: one HDD_INFO line per spare card, preserve length/CRLF, sweep numeric lines 0…5, read the debug `SD Import: <field>` message. | PLANNED | — | EXP-2026-11-05-16 |
| C-300 | Comparator chain: `0x6fab2c` wrapper → `0x6faeb0` mode/path selector → `0x6fb05c` field comparison. `0x6fafe4` is a 0x18-byte teardown stub (retracted). | VERIFIED | H | EXP-2026-11-05-17 |
| C-301 | `userdata_type` is the range-checked field (`0 < v < 6`); `manufacturer_id` and `destination_id` are arbitrary `u16`. | VERIFIED | H | EXP-2026-11-05-17 |
| C-302 | SD format/validate module: data delta `0x1130000`, code file `0x30d000–0x315000`; wrapper `0x30efcc` passes the path to COM property 17. FATUTIL is not the parser. | OBSERVED | H | EXP-2026-11-05-17 |
| C-303 | The file parser is behind an unnamed COM class (`Set(17, path)`); the comparator module's code delta is unrecoverable, so static tracing stops there. | UNKNOWN | — | EXP-2026-11-05-17 |
| C-304 | Six-line mapping is a ranked hypothesis: line 4 `SDC08-EVEUR` → manufacturer+destination; QSD lines → userdata_type; line 6 part number; lines 3/5 version/date. | HYPOTHESIS | M | EXP-2026-11-05-17 |
| C-305 | The `Sys` side is a parsed `u16`; the built-in `0x06000000` copy is the only system-side HDD_INFO, so both are likely used. | HYPOTHESIS | M | EXP-2026-11-05-17 |
| C-306 | `tools/hddinfo_variants.py` generates 73 length-preserving 72-byte HDD_INFO variants for the spare-card matrix. | VERIFIED | H | EXP-2026-11-05-17 |
| C-307 | The `0..2047` bound is runtime/derived, not storage: raw REFER001 u16 values exceed it, so coordinates are bit-packed/masked. | OBSERVED | H | EXP-2026-11-05-17 |
| C-310 | The COM class is `VerInfoCC.DLL`, CoClass `VerInfoCtrl`, CLSID `{408BB0AC-…}`; file base `0xa15200`. | VERIFIED | H | EXP-2026-11-05-18 |
| C-311 | VerInfoCC code delta is `0x027cae00`, VA base `0x031e0000`, proven by vptr identity (`0x031e14e4`). | VERIFIED | H | EXP-2026-11-05-18 |
| C-312 | VerInfoCC's public surface is `GetVersionInfo(LONG dwType, VARIANT* pVal)`; there is no setter and no path parameter. | VERIFIED | H | embedded type library |
| C-313 | “Property 17 carries the HDD_INFO path” is retracted: the call site is `obj->method#1(17,0,path)` on a different object. | VERIFIED (retraction) | H | EXP-2026-11-05-18 |
| C-314 | VerInfoCC does not parse HDD_INFO: no path, no file-I/O string, data from a compiled-in constant table. | VERIFIED (negative) | H | EXP-2026-11-05-18 |
| C-315 | The comparator module's data delta `0x02800000` is settled by its string pool and the `sprintf` at `0x6fb0d8`. | VERIFIED | H | EXP-2026-11-05-18 |
| C-316 | Six-line mapping is unknown; all three compared fields are numbers, and the `Sys` side is likely a compiled-in table. | UNKNOWN / HYPOTHESIS | M | EXP-2026-11-05-18 |
| C-317 | The missing link is the class behind the SD module's `0x30f008` call; module U only compares. | UNKNOWN | — | EXP-2026-11-05-18 |
| C-318 | `tools/solve_data_delta.py` recovers VerInfoCC's delta; `hddinfo_variants.py` now emits 89 length-preserving variants (pairwise swaps + reverse). | VERIFIED | H | EXP-2026-11-05-18 |
| C-320 | `0x30efcc` is a free function `f(obj,mode,flag)`, not a parser; there is no `bsr` to it and the object comes from the caller. The `0x30f008` premise is false. | VERIFIED (negative) | H | EXP-2026-11-05-19 |
| C-321 | `0x01f83368` is a writable global, not the HDD_INFO path; the code stores into it at `0x31098c`–`0x310996`. | VERIFIED (negative) | H | EXP-2026-11-05-19 |
| C-322 | The code range is `mspart.dll` (base `0x309200`) / `WAVEAPI.dll` (base `0x30d200`). Their bases overlap, so `base <= file < base+size` attribution is invalid. | VERIFIED | H | EXP-2026-11-05-19 |
| C-323 | Round-10 “SD module delta `0x1130000` / property 17 path” is retracted in full; the five string hits were store targets to globals. | VERIFIED (retraction) | H | EXP-2026-11-05-19 |
| C-324 | `0x6fb05c` is a message builder (memsets, descriptors, `sprintf`, field id `0x00A2`, `0..5` check in `userdata_type`, `vtable[5]`), not a parser. | VERIFIED (negative) | H | EXP-2026-11-05-19 |
| C-325 | Six-line mapping remains unknown; the path-start literal has zero references and module U uses only suffixes; linker suffix merging is the working hypothesis. | UNKNOWN / HYPOTHESIS | M | EXP-2026-11-05-19 |
| C-326 | Reader location remains unknown; three routes are closed with reasons (0x30f008 object, VerInfoCC, comparator-as-parser). | UNKNOWN | — | EXP-2026-11-05-19 |
| C-327 | Next direction: `USR_Convert_*`, especially `Set finished mark (file=%s)` at `0xe4dc18`; locate its module with a ≥3-string cluster, then walk from the path argument. | PLANNED | — | EXP-2026-11-05-19 |
| C-330 | `0xc438a4` is a memory/fd statistics formatter, not the CMP.LST opener; the real `\CMP.LST` is at `0xdf945d` with **zero** pointer references. | VERIFIED (retraction) | H | EXP-2026-11-05-20 |
| C-331 | `DRSTR001.DAT`, `.ind`, `.IND`, `REFER001.DAT`, `MAPAL001`, `LEV3456R.DAT` have zero literal references; `.cmp` has one (debug dumper). | VERIFIED (negative) | H | EXP-2026-11-05-20 |
| C-332 | The map module code is **not** `file+0x02200000`. A per-instruction `{VA,flag}` table at `0x12fa000–0x132d200` puts nine known entries in `0x02b0xxxx–0x02b5xxxx`; best fit `+0x01f07d5c`. | VERIFIED (band) / OBSERVED (exact) | H | EXP-2026-11-05-20 |
| C-333 | `0xc438a4` call targets are code VAs in another module; applying the data delta to a `jsr` target is invalid. | VERIFIED | H | EXP-2026-11-05-20 |
| C-334 | `OBJDLL.dll` file base `0x7dd200`, 1294 exports incl. `MAL_DataVol_getSize/getOffset/getAreaRect` and `OBJ_DiscInfo_*`. | VERIFIED | H | EXP-2026-11-05-20 |
| C-335 | `STDDLL.dll` file base `0x834200`, 310 exports. | VERIFIED | H | EXP-2026-11-05-20 |
| C-336 | Six zlib copies are mapped (1.1.3/1.1.4, lbase/dbase): `0x5e5f98`, `0x8b5f10`, `0xa34f48`, `0xe88f78`, `0x15c7e88`, `0x1619848`. | VERIFIED | H | EXP-2026-11-05-20 |
| C-337 | FD type tag is `+0xC0` (7–15), not `+0xC4`; dir/disc tag is `+0xB4`, second field `+0xBC`. | VERIFIED (correction) | H | EXP-2026-11-05-20 |
| C-338 | `0xc0ebf8` is mid-function; `0x1ac` is an argument to `0x2e533e4`, also called with negative values; the level-table allocation claim is unproven. | VERIFIED (retraction) | H | EXP-2026-11-05-20 |
| C-339 | The data contract is unaffected: `.cmp` chunked zlib and DRSTR 40/324 remain data-confirmed; hardcoded filenames, `0xc438a4` opener and `0x02200000` are contradicted. | VERIFIED | H | EXP-2026-11-05-20 |
| C-340 | Next trace: find the `0x2e0xxxx` module export table; run `.ind` mutation (chunk_size/count/offset) on a spare card; SD bus capture. | PLANNED | — | EXP-2026-11-05-20 |
| C-350 | Literal-pool analysis needs F1 code pages, F2 reject loads used as `jsr`/`jmp` targets, F3 reject import thunks; candidates fall 236,765 → 95,758. | VERIFIED (method) | H | EXP-2026-11-05-21 |
| C-351 | “USR_Convert module at `0x0101e408`” is retracted: those are 12-byte import stubs / IAT slots; same for `0x01011478`. | VERIFIED (retraction) | H | EXP-2026-11-05-21 |
| C-352 | “The map module references `VER_INFO\HDD_INFO.TXT`” is retracted: `0xc0dbda`/`0xc1078c`/`0xc10800` are `jsr` targets. | VERIFIED (retraction) | H | EXP-2026-11-05-21 |
| C-353 | Only one builder touches the HDD_INFO path: clean refs at `0x6faf28`, `0x6faf0e`, `0x6faf52`, `0x6faeee`, `0x6fb0ce`; path start/UserSD/fields have zero clean refs. | VERIFIED | H | EXP-2026-11-05-21 |
| C-354 | `0x6faeb0` builds the path from fragments (modes 0/10 append `mSD\VER_INFO\HDD_INFO.TXT` to `\Syste`; other modes `TXT`; DLL branch `til.dll`); it does no I/O. | VERIFIED | H | EXP-2026-11-05-21 |
| C-355 | Six-line mapping remains unknown; constraints are numeric `Sys`/`SD`, `0..5`, field enum `0x00A2`. | UNKNOWN | — | EXP-2026-11-05-21 |
| C-356 | The parser helper is one indirection away: `0x0369d400`, `0x036922cc`, `0x0367b180`, `0x0369d3dc` in the `0x0367–0x0369xxxx` module receive the built path. | OBSERVED | M | EXP-2026-11-05-21 |
| C-357 | Next: pin the `0x0367–0x0369` module with the three-filter index and a self-printed string cluster; else run the 89-variant spare-card matrix. | PLANNED | — | EXP-2026-11-05-21 |
| C-360 | `0x0360–0x036a` is a library layer, not a pinnable module: 1,899 code-target VAs, no export dir, no `MSFT`, no `.rgs`. | VERIFIED | H | EXP-2026-11-05-22 |
| C-361 | Entry-point delta solve for the 13 helper VAs peaks at 7/13 prologues (`D≈0x02236a34`), with mid-function bytes; a true delta needs ≥11/13. | VERIFIED (negative) | H | EXP-2026-11-05-22 |
| C-362 | The VA map is **not injective**: `0x0367b180` is both a `jsr` target and the UTF-16 string at file `0xe7b180`; `0x0369d400`/`0x036922cc` map to string data. | VERIFIED | H | EXP-2026-11-05-22 |
| C-363 | Cross-module calls cannot be resolved by literal arithmetic; they need the `romimage` XIP section table (`file ↔ VA ↔ size`). | VERIFIED | H | EXP-2026-11-05-22 |
| C-364 | Intra-module results stand: builder `0x6faeb0` and reporter `0x6fb05c` need no delta. | VERIFIED | H | EXP-2026-11-05-22 |
| C-365 | Parser, card-vs-built-in and six-line mapping remain unknown; only the `Sys`/`SD`, `0..5`, `0x00A2` constraints are proven. | UNKNOWN | — | EXP-2026-11-05-22 |
| C-366 | The spare-card matrix is final: 89 length-preserving 72-byte variants with a six-step plan and message oracle. | VERIFIED | H | EXP-2026-11-05-22 |
| C-367 | Next: parse the XIP section table; `ECEC` at container `+0x240` and `NKOK` at `+0x1fc` are the leads. | PLANNED | — | EXP-2026-11-05-22 |
| C-370 | The ROM export directory is 9 dwords (timestamp first); a corrected scan finds 135 export modules. | VERIFIED | H | EXP-2026-11-05-23 |
| C-371 | No module's RVA range covers `0x2e00f98–0x2e533e4`; `0x2e0xxxx` is an **import-thunk area**, not an export module. | VERIFIED (negative) | H | EXP-2026-11-05-23 |
| C-372 | The 86-entry thunk table at `0x1724eb8–0x17252c0` uses 12-byte thunks (best delta `0x16e248c`), IAT `0x1ab9000–0x1ab9440`; import names at `0x1708000–0x170a200`. | VERIFIED | H | EXP-2026-11-05-23 |
| C-373 | The underlying module is a non-exporting shared library at file ≈`0x171c000–0x1724eb8`, VA ≈`0x2e00000`; its name is unknown. | OBSERVED | M | EXP-2026-11-05-23 |
| C-374 | MAL chain: `OBJ_DiscInfo_readDiscVol` → `MAL_DataVol_getOffset` → `getSize`; OBJDLL VA base `0x03480000`; only 3 call sites, all in OBJDLL. | VERIFIED | H | EXP-2026-11-05-23 |
| C-375 | The fd/IOB layer is in `NaviStateCC.DLL`, file base `0xc32200`; it is table-dispatched. | VERIFIED | H | EXP-2026-11-05-23 |
| C-376 | The data contract is unchanged: `.cmp` zlib and `.ind`/DRSTR layouts are data-confirmed; firmware is silent. | VERIFIED | H | EXP-2026-11-05-23 |
| C-377 | `tools/ind_mutate.py` generates 8 `.ind` variants (chunk_size/count/offset) for the spare-card matrix. | VERIFIED | H | EXP-2026-11-05-23 |
| C-378 | Next: name the 86 thunks via the import descriptor (`FirstThunk=0x1ab9000`, `COREDLL.dll`) and scan NaviStateCC for ≥3 fd thunks + local zlib. | PLANNED | — | EXP-2026-11-05-23 |
| C-380 | There is **no XIP section table** in the image: 0 `B000FF`/`ROMHDR`; `CECE`/`ECEC`/`NKOK` are container metadata. | VERIFIED (negative) | H | EXP-2026-11-05-24 |
| C-381 | The `0x1951ee0` tail table is not a VA→file map: pointers are kernel-space `0x8C–0x8E`; no candidate base maps them into the payload. | VERIFIED (negative) | H | EXP-2026-11-05-24 |
| C-382 | `module_scan` `(file_base, va_base)` pairs are wrong for most modules: only OLEAUT32-class deltas hold (65 % prologues); TFAT 0 %, FATUTIL 3 %, commctrl 1 %, WAVEAPI 4 %. | VERIFIED (negative) | H | EXP-2026-11-05-24 |
| C-383 | The container stores **section groups**, not full PE images at `base + RVA`; the per-module base claim is retracted. | VERIFIED (retraction) | H | EXP-2026-11-05-24 |
| C-384 | `0x0367b180` is still both a `jsr` target and the UTF-16 string at `0xe7b180`; the collision is unresolved. | UNKNOWN | — | EXP-2026-11-05-24 |
| C-385 | 148 `RSDS`/PDB records + 155 DLL names give file-side module identity; `rommap.py` maps `0x032560c3` → TFAT `0x2942c3`, but `0x0369d400` → UNKNOWN. | VERIFIED | H | EXP-2026-11-05-24 |
| C-386 | Readers remain blocked at the `0x0369d400` cross-module call; six-line/card-vs-built-in remain unknown. | UNKNOWN | — | EXP-2026-11-05-24 |
| C-387 | Static VA reasoning is exhausted; next are a dynamic break after `0x6faf30` or the 89-variant card matrix. | PLANNED | — | EXP-2026-11-05-24 |
| C-390 | The standard import descriptor with `FirstThunk=0x1ab9000` is absent; 219 descriptor-shaped records, none matching. The navi IAT is pre-bound. | VERIFIED (negative) | H | EXP-2026-11-05-25 |
| C-391 | The 86 thunks remain unnamed; 140 ordinal-ILT runs exist but none matches the navi IAT. | VERIFIED (negative) | H | EXP-2026-11-05-25 |
| C-392 | NaviStateCC is a COM DLL with only 4 exports; `DllGetClassObject` forwards to `0x2e00eb8` (file `0x171ea2c`), class data `0x1d0f8a8`. | VERIFIED | H | EXP-2026-11-05-25 |
| C-393 | The fd/IOB layer functions are COM methods reached through a load-time vtable; no static `bsr`/vtable reference reaches them. | VERIFIED | H | EXP-2026-11-05-25 |
| C-394 | Structural scan: `0xc42e48` debug dumper, `0xc49f98` virtual dispatcher, `0xc438a4` stats formatter; fd thunk sets listed in the EXP. | OBSERVED | H | EXP-2026-11-05-25 |
| C-395 | No `0x10000` pool literal or `mov #1; shll16` near the fd layer; the `.ind` reader likely uses `chunk_size` as a buffer size, not a comparison. | OBSERVED | M | EXP-2026-11-05-25 |
| C-396 | The `.cmp`/`.ind` reader is not located. | UNKNOWN | — | EXP-2026-11-05-25 |
| C-397 | Contract unchanged; “NaviStateCC is a flat library” is contradicted (it is COM). | VERIFIED (correction) | H | EXP-2026-11-05-25 |
| C-398 | Next: disassemble `0x171ea2c` → `CreateInstance`/object vtable (or the `0x1d0f8a8` writer); run the `.ind` mutation matrix. | PLANNED | — | EXP-2026-11-05-25 |
| C-400 | `DllGetClassObject`'s real entry is file `0x171e9e8`, not `0x171ea2c`; its pool holds link-time VAs `0x0260xxxx`, while the called thunk table is runtime-placed in `0x02e0xxxx` (different section delta `0x16e64d0`). | VERIFIED | H | EXP-2026-11-05-26 |
| C-401 | `0x1d0f8a8` is a RAM global context used 23× in NaviStateCC; no store in that module, so the framework/loader initializes it. | VERIFIED | H | EXP-2026-11-05-26 |
| C-402 | The vtable is constructed, not static: 233 constructor stores write 175 method VAs (`0x0260xxxx–0x0262xxxx`); densest build at `0x170f100–0x170f2b0`. | VERIFIED | H | EXP-2026-11-05-26 |
| C-403 | Relocation wall: best single-base mapping gives 15/175 prologue hits; a correct per-section map would be ~80–90 %. | VERIFIED (negative) | H | EXP-2026-11-05-26 |
| C-404 | `0x6faf30` is not the reader: it is a `jsr @r3` in the Bluetooth/OPP handler at `0x6faeb0` (`OppAccess::msg_opp_comp_ind`). | VERIFIED (negative) | H | EXP-2026-11-05-26 |
| C-405 | No `0x10000` pool literal, no `mov #1; shll16`, no 4-dword header read near the fd layer; `chunk_size` is likely an output-buffer size, not a comparison. | OBSERVED | M | EXP-2026-11-05-26 |
| C-406 | The `.cmp`/`.ind` reader address is still unknown; a COM method is likely but not proven. | UNKNOWN | — | EXP-2026-11-05-26 |
| C-407 | Highest-value break: `MAL_DataVol_getOffset` (VA `0x03498d48`, file `0x7f5f48`) or `getSize` (VA `0x03498d28`, file `0x7f5f28`); its caller is the `.ind` wrapper. | PLANNED | — | EXP-2026-11-05-26 |
| C-408 | Card matrix `size_8000` answers buffer-vs-compare; `off_last_m1` answers exact seek vs `78 9c` scan. | PLANNED | — | EXP-2026-11-05-26 |
| C-410 | The 175 method VAs belong to **iPodCC.DLL** (file base `0x1709200`, link-time `0x0260xxxx`), not NaviStateCC. | VERIFIED | H | EXP-2026-11-05-27 |
| C-411 | `0x2e00eb8` is a **shared COM runtime helper**, not NaviStateCC's class factory; the round-4 COM branch led to the wrong module. | VERIFIED (correction) | H | EXP-2026-11-05-27 |
| C-412 | iPodCC slot tables: constructor A 18 slots (`+0x00,+0x04,+0x70…+0x9c,+0xa4…+0xc0`), B 14 slots (`+0x00,+0x04,+0x08,+0x50,+0x70…+0x94`). | VERIFIED | H | EXP-2026-11-05-27 |
| C-413 | 158/175 method VAs map under some delta (`0x11a3xxxx`/`0x1182xxxx` → file `0x145xxxx–0x14axxxx`), but confidence is low and the assignment is non-unique. | VERIFIED (coverage) / LOW confidence | M | EXP-2026-11-05-27 |
| C-414 | The iPodCC vtable contains no MAL/fd/zlib/DRSTR/tile methods. | VERIFIED (negative) | H | EXP-2026-11-05-27 |
| C-415 | No NaviStateCC vtable exists as a contiguous pointer table under `0x1f07d5c`; a ≥8-pointer run scan found 0. | VERIFIED (negative) | H | EXP-2026-11-05-27 |
| C-416 | Next anchor: find the writer/initializer of `0x1d0f8a8`; it should install the NaviStateCC class factory/vtable containing `0xc42520`, `0xc426a4`, `0xc438a4`. | PLANNED | — | EXP-2026-11-05-27 |
| C-417 | If the initializer is absent from the ROM, static is closed; use the MAL breakpoint or the card matrix. | PLANNED | — | EXP-2026-11-05-27 |
| C-420 | NaviStateCC initializer `0xc43430` writes `0x1d0f720`, `0x1d0f898=obj`, type tag `0x84`, `+88=0x300`, and the 16-byte class ID to `0x1d0f888…894`. | VERIFIED | H | EXP-2026-11-05-28 |
| C-421 | `0x1d0f8a8` itself is never written by the ROM; the only direct store is destructor `0xc4ac6a` zeroing `+96/+100/+104`. | VERIFIED (negative) | H | EXP-2026-11-05-28 |
| C-422 | `0xc43430` has no static caller; its only pointer occurrence is the per-instruction table at `0x1302760`; invocation is dynamic. | VERIFIED (negative) | H | EXP-2026-11-05-31 |
| C-423 | The RAM copy list at `0x1952b00` does not cover the NaviStateCC block (it covers OS modules at `0x8D/0x8F`). | VERIFIED (negative) | H | EXP-2026-11-05-28 |
| C-424 | No static vtable contains the fd methods: `0x2b4a27c`/`0x2b4a400`/`0x2b4b600` occur once in the per-instruction table, never in a ≥8-pointer run. | VERIFIED (negative) | H | EXP-2026-11-05-28 |
| C-425 | The object vtable is built at runtime by the shared COM helper `0x171e9e8`/loader. | OBSERVED | M | EXP-2026-11-05-28 |
| C-426 | Reader address and vtable slot layout are not in the ROM; `chunk_size` compare vs buffer size remains a hypothesis. | UNKNOWN | — | EXP-2026-11-05-28 |
| C-427 | Static fallback: break on MAL `getOffset/getSize`, fd methods, or fd thunks; hardware is the only route to the reader address. | PLANNED | — | EXP-2026-11-05-28 |
| C-428 | Next static attempt: decompile `0x171e9e8` for a slot template/construction map; also prepare the dynamic guide and hardware kit. | PLANNED | — | EXP-2026-11-05-28 |
| C-430 | `0x171e9e8` is a COM type-library registration/lookup routine, not a class factory/vtable builder: GUIDs `44ec053b…`/`44ec053a…`, strings `LoadTypeLib`/`RegisterTypeLib`/`REGISTRY`/`Module`/`oleaut32.dll`/`.tlb`. | VERIFIED | H | EXP-2026-11-05-29 |
| C-431 | Its callees are `oleaut32`/`ole32` thunks; the indirect calls are `ITypeLib`/`ITypeInfo` methods, not NaviStateCC methods. | VERIFIED | H | EXP-2026-11-05-29 |
| C-432 | No static vtable template exists and no static vtable contains `0xc42520`/`0xc426a4`/`0xc438a4`; the fd VAs occur once in the per-instruction table. | VERIFIED (negative) | H | EXP-2026-11-05-29 |
| C-433 | `0x1d0f8a8` is RAM BSS, never written by the ROM; COM resolution goes through the registry. | VERIFIED (negative) | H | EXP-2026-11-05-29 |
| C-434 | Static is closed for the NaviStateCC vtable and reader; the object vtable is a run-time artifact. | VERIFIED (negative) | H | EXP-2026-11-05-29 |
| C-435 | Dynamic guide: break on MAL `getOffset/getSize`, then fd methods, then fd thunks; offline `.ind` variants settle `chunk_size`/seek. | VERIFIED (procedure) | H | EXP-2026-11-05-29 |
| C-436 | The only remaining unknown for the reader is the runtime-built NaviStateCC object vtable/slot layout. | UNKNOWN | — | EXP-2026-11-05-29 |
| C-437 | With no hardware access, the next productive work is the compiler/offline validators plus a prepared hardware kit. | PLANNED | — | EXP-2026-11-05-29 |

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
| C-260 | The hardened import anchor returns 0 candidates: the ROM is pre-bound, so import directories are stripped. The round-6 import-anchor lead is retracted. | VERIFIED (negative) | H | EXP-2026-11-05-13 |
| C-261 | The export anchor still holds (26 modules), but navi/map modules have no export directory in `0x44xxxx–0x1952c88`. | VERIFIED | H | EXP-2026-11-05-13 |
| C-262 | The `o32_rom` section records do not cover the navi modules: no `dataptr` matches a known module file base. | VERIFIED (negative) | H | EXP-2026-11-05-13 |
| C-263 | B/C builds differ by 4 bytes but lack build A's map code (`0xc42410`, `0xc438a4`); `0xc438a4` occurs 4× in A. B/C cannot pin A's map module. | VERIFIED | H | EXP-2026-11-05-13 |
| C-264 | Map module `.text` is file `0xc00000–0xc4b000`; `.rdata` is file `0xdf6000` = VA `0x02df6000`; `Vt < 0x02df6000`. | VERIFIED | H | EXP-2026-11-05-13 |
| C-265 | `jsr` targets at `0x02e0xxxx` belong to a different module (file `0xc00000`, delta `0x02200000`), not the map module. | VERIFIED | H | EXP-2026-11-05-13 |
| C-266 | Next anchor: ROM module table at `0x15271c8` (16-byte-stride names), self-name literal and shared-`.rdata` clusters. | PLANNED | — | EXP-2026-11-05-13 |
| C-270 | `0x15271c8` is not a module table: it is 4-byte-aligned packed module-name strings in a resource blob, padded to 4/16 bytes. | VERIFIED (negative) | H | EXP-2026-11-05-14 |
| C-271 | Self-name anchor cannot apply: the navi name strings belong to a different module; only 12 scattered hits, no ≥4-pointer cluster. | VERIFIED (negative) | H | EXP-2026-11-05-14 |
| C-272 | Adjacency `Vt=0x02dab000` is wrong (830 literals point at embedded PNG data); the call-target scan is flat (18/1122 prologues). | VERIFIED (negative) | H | EXP-2026-11-05-14 |
| C-273 | The `0x1952b00` field `+0x10` is a Unix timestamp (2011-06-22…07-29), not a checksum; the round-6 checksum claim is retracted. | VERIFIED | H | EXP-2026-11-05-14 |
| C-274 | The round-2 “call-to-string paradox” is withdrawn: `0x02200000` is plausible as the code delta, though not proven. | OBSERVED | M | EXP-2026-11-05-14 |
| C-275 | Static VA recovery from this image is exhausted; reader work must shift to relative call-graph tracing or hardware/dynamic tracing. | VERIFIED (negative) | H | EXP-2026-11-05-14 |

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

## Offline validation

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-505 | `tools/cardcheck.py` passes on the EU 2011 root and raw image: 480 files, 39 dirs, 5,173,965,667 bytes, 194/194 `.cmp` pairs, 40 DRSTR nodes / 324 entries, 11/11 MMAIN rows, and an identical `0x06000000` `HDD_INFO` copy. | VERIFIED | H | EXP-2026-11-05-29; `python3 tools/cardcheck.py --root …` / `--image …` |
| C-506 | `tools/l2check.py` passes on the EU 2011 root: DRSTR byte-identical, 194/194 preserved `.cmp` round-trips, five target tiles byte-identical, four golden geometry digests, and the tile/POI mutation checks. | VERIFIED | H | EXP-2026-11-05-29; `python3 tools/l2check.py --root …` |
| C-507 | The card's LFN checksum bytes do not match the standard FAT short-name checksum for most entries; the names are still recoverable from contiguous LFN sequences and agree with the `7z`/`mtools` extraction. | OBSERVED | H | EXP-2026-11-05-29; `tools/cardcheck.py` FAT reader |
| C-508 | `ze0_mutate.py` in non-strict mode could return the source record unchanged, making the one-vertex self-test a silent no-op; it now selects a strictly rebuilt record and refuses an unchanged mutation. | VERIFIED | H | EXP-2026-11-05-29; `tools/ze0-viewer/ze0_mutate.py` |

## Emulation / feedback loop

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-509 | Wine is a Win32 compatibility layer, not a CPU emulator; it cannot execute the Leaf's SH-4 Windows CE ROM modules. | VERIFIED (design) | H | Wine "about"/README: Win32 API on a compatible host CPU; no SH-4/WinCE target |
| C-510 | QEMU system-mode SH-4 has only the `r2d` machine; `linux-user` SH-4 exists but runs Linux ELF, not WinCE. | VERIFIED | H | QEMU `hw/sh4/Kconfig`, `linux-user/sh4/target_syscall.h` |
| C-511 | MAME has SH-4/SH7750-family CPU models, but no CETUS_SH4 board model was found; its SH-4 on-board peripherals are still incomplete. | VERIFIED | H | MAME `src/devices/cpu/sh/sh4.cpp` header and device types |
| C-512 | sh3-emu is MIT-licensed, emulates SH-3 Windows CE 1.x/2.x (including a Clarion AutoPC 310C), and is not an SH-4/CE5 emulator. | VERIFIED | H | sh3-emu README, `docs/hardware.md`, `docs/machines/autopc.md`, `LICENSE` |
| C-513 | CERF has no SH-4 CPU core; its CPUs are ARM/StrongARM/XScale/MIPS, and its current licence is custom non-commercial. | VERIFIED | H | CERF `src/cpu` tree and `LICENSE` |
| C-514 | A true 4-bit SDIO card emulator is typically FPGA-level work; an SD extender plus a host-side writer is the cheap hardware-in-the-loop alternative. | OBSERVED | M | external SD-emulation projects; not tested on the Leaf |
| C-515 | `tools/verify.py` auto-detects the ZE0 year and runs L1/L2 with the right flags: 2011 uses the golden profile, 2014/2016 use `--no-golden --ignore-dump-artifacts`, map-only trees add `--partial`, and the QY8x 2019 image returns `UNSUPPORTED` (exit 3). | VERIFIED | H | `python3 tools/verify.py --root/--image …`; EXP-2026-11-05-31 |

## Image archive / cross-year validation

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-500 | The complete public mirror set (four SD images and three map archives) is stored in `archive/images/` and all seven SHA-256 sums match. | VERIFIED | H | EXP-2026-11-05-30; `sha256sum -c archive/images/SHA256SUMS` |
| C-501 | L1 passes on the 2011, 2014 and 2016 ZE0-era SD images; 2016 requires `--ignore-dump-artifacts` because of AppleDouble files. The 2019 e-NV200 image fails because it is the different `CLA-NAVI06-01`/ZENRIN engine. | VERIFIED | H | EXP-2026-11-05-30; `tools/cardcheck.py --image …` |
| C-502 | L1 passes on the 2013-14, 2014-15 and 2016-17 map trees with `--partial --ignore-dump-artifacts`; their `DRSTR001.DAT` lists a `VER_INFO` directory that is absent from the archive. | VERIFIED | H | EXP-2026-11-05-30; `tools/cardcheck.py --root … --partial` |
| C-503 | Before the cross-year fixes, L2 was 2011-specific: `B30R048R.DAT` failed the byte-identical rebuild at `0x807`/`0x808` on the 2013–2016 archives, and the `POINT032` page `0x4200` POI mutation was a 2011 fixture. Superseded by C-504. | OBSERVED (historical) | H | EXP-2026-11-05-30; `tools/l2check.py --no-golden` |
| C-504 | L2 now passes on full 2014 and 2016 roots with `--no-golden --ignore-dump-artifacts`: `B30R048R` is byte-identical via a preserved-layout fallback, the REFER fixture is discovered per year, and `validate_mutation.py --drstr-dir` disambiguates `REFER001`/`REFER002`. | VERIFIED | H | EXP-2026-11-05-31; `tools/l2check.py`, `tools/ze0-viewer/ze0_tile_io.py` |

## How to use this ledger

- When you verify or refute a claim, update its row and add the command/output
  to the evidence column.
- When you add a new claim, give it the next free ID in its section.
- Keep `docs/format/*.md` consistent with this file; the ledger wins if they
  disagree.
- Do not promote `OBSERVED`/`HYPOTHESIS` to `VERIFIED` without a reproducible
  check that another agent can run.
