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
| C-331 | `DRSTR001.DAT`, `.ind`, `.IND`, `REFER001.DAT`, `MAPAL001`, `LEV3456R.DAT` have zero literal references; `.cmp` has one (debug dumper). **Partially retracted** by C-850/C-851/C-852/C-857. | VERIFIED (negative, partial) | H | EXP-2026-11-05-20; EXP-2026-11-06-M3.4-drstr-parser |
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
| C-370 | The ROM export directory is 9 dwords (timestamp first); a corrected scan finds 135 export modules. | VERIFIED | H | Re-verified under CE TOC: `cerom.py exports MODULE` resolves the same export directories. EXP-2026-11-05-23; EXP-2026-11-06-H4 |
| C-371 | No module's RVA range covers `0x2e00f98–0x2e533e4`; `0x2e0xxxx` is an **import-thunk area**, not an export module. | RETRACTED | — | Superseded by C-522/C-633 (H4); under the CE TOC `0x2e0xxxx` is `NaviStateCC.dll` (vbase `0x02df0000`), not an unexplained thunk area. EXP-2026-11-05-23 |
| C-372 | The 86-entry thunk table at `0x1724eb8–0x17252c0` uses 12-byte thunks (best delta `0x16e248c`), IAT `0x1ab9000–0x1ab9440`; import names at `0x1708000–0x170a200`. | VERIFIED | H | Re-verified under CE TOC: `cerom.py thunks` resolves import thunks through the module OFT/export tables. EXP-2026-11-05-23; EXP-2026-11-06-H4 |
| C-373 | The underlying module is a non-exporting shared library at file ≈`0x171c000–0x1724eb8`, VA ≈`0x2e00000`; its name is unknown. | RETRACTED | — | Superseded by C-522/C-633 (H4); the module is `NaviStateCC.dll` under the CE TOC. EXP-2026-11-05-23 |
| C-374 | MAL chain: `OBJ_DiscInfo_readDiscVol` → `MAL_DataVol_getOffset` → `getSize`; OBJDLL VA base `0x03480000`; only 3 call sites, all in OBJDLL. | VERIFIED | H | Re-verified under CE TOC: `cerom.py file2va 0x7f5f48` → `0x8d0d6d48` (OBJDLL.dll `.text`, section rva `0x00001000`); `cerom.py sections OBJDLL.dll`. EXP-2026-11-05-23; EXP-2026-11-06-H4 |
| C-375 | The fd/IOB layer is in `NaviStateCC.DLL`, file base `0xc32200`; it is table-dispatched. | RETRACTED | — | Superseded by C-634/C-522 (H4); `NaviStateCC.dll` is confirmed by `cerom.py modules`, but its COM vtable is runtime-built, so the fd slot layout is not statically recoverable. EXP-2026-11-05-23 |
| C-376 | The data contract is unchanged: `.cmp` zlib and `.ind`/DRSTR layouts are data-confirmed; firmware is silent. | VERIFIED | H | EXP-2026-11-05-23 |
| C-377 | `tools/ind_mutate.py` generates 8 `.ind` variants (chunk_size/count/offset) for the spare-card matrix. | VERIFIED | H | EXP-2026-11-05-23 |
| C-378 | Next: name the 86 thunks via the import descriptor (`FirstThunk=0x1ab9000`, `COREDLL.dll`) and scan NaviStateCC for ≥3 fd thunks + local zlib. | PLANNED | — | EXP-2026-11-05-23 |
| C-380 | ~~There is no XIP section table in the image~~: the search for `B000FF`/`ROMHDR` strings could not find a raw CE ROM header. Superseded by C-516 (and C-088/C-089). | RETRACTED | — | EXP-2026-11-05-24; superseded by EXP-2026-11-05-35 |
| C-381 | ~~The `0x1951ee0` tail table is not a VA→file map~~: it lies inside the `TOCentry` array (`0x1951bcc–0x1952e6c`, 149 × 32 B) right after `ROMHDR`; the base `0x8cae1000` was off the coarse test grid. The "`0x1952b00` RAM copy list" (C-273) is in the same array. Superseded by C-517. | RETRACTED | — | EXP-2026-11-05-24; superseded by EXP-2026-11-05-35 |
| C-382 | `module_scan` `(file_base, va_base)` pairs are wrong for most modules: only OLEAUT32-class deltas hold (65 % prologues); TFAT 0 %, FATUTIL 3 %, commctrl 1 %, WAVEAPI 4 %. | VERIFIED (negative) | H | EXP-2026-11-05-24 |
| C-383 | The container stores **section groups**, not full PE images at `base + RVA`; the per-module base claim is retracted. | VERIFIED (retraction) | H | EXP-2026-11-05-24 |
| C-384 | `0x0367b180` is still both a `jsr` target and the UTF-16 string at `0xe7b180`; the collision is unresolved. Superseded by C-519. | RETRACTED | — | EXP-2026-11-05-24; EXP-2026-11-05-35 |
| C-385 | 148 `RSDS`/PDB records + 155 DLL names give file-side module identity; `rommap.py` maps `0x032560c3` → TFAT `0x2942c3`, but `0x0369d400` → UNKNOWN. Superseded by C-518/C-520. | VERIFIED (superseded) | H | EXP-2026-11-05-24; EXP-2026-11-05-35 |
| C-386 | Readers remain blocked at the `0x0369d400` cross-module call; six-line/card-vs-built-in remain unknown. Superseded by C-520/C-521. | UNKNOWN (superseded) | — | EXP-2026-11-05-24; EXP-2026-11-05-35 |
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
| C-423 | The RAM copy list at `0x1952b00` does not cover the NaviStateCC block (it covers OS modules at `0x8D/0x8F`). | RETRACTED | — | Superseded by C-638/C-381/C-517 (H4); `0x1952b00` is a `TOCentry` field, not a RAM copy list, so the coverage statement is moot. EXP-2026-11-05-28 |
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
| C-880 | Build A resolves the `RDSTM001` volume together with `LCTBL001.DAT` under data type `0x14e4`, kind 1: `Navi.exe` `0x004125a8` compares the descriptor type at `0x004125fa`, loads `"LCTBL001.DAT"` (`0x0017a1f8`) and `"RDSTM001"` (`0x00179398`) and calls the volume lookup `0x0040b358` (28-byte entries, count `+24`, list `+32`). `0x14e8` resolves `REFER001` + `INDEX003.DAT` in the same routine. | VERIFIED | H | EXP-2026-11-06-M3.7-router-rdstm |
| C-881 | The literal `RDSTM001.DAT` (`0x00179f7c`) has **no** code reference in build A; the volume is reached through the 8-char id table at `0x00179338` (`ZCODE0`, `LCTBL0`, `INTER0`, `FRWAY0`, `ADDRE0`, `POINT0`, `RDSTM001`) and the file name is built from the id (`0x003fbed8`). Only `Navi.exe` carries the map-data names; other modules only match the unrelated UI token `RDSTMC_DETOUR_INFO`. | VERIFIED (negative) | H | EXP-2026-11-06-M3.7-router-rdstm; `sh4xref.py --to 0x00179f7c` |
| C-882 | The `RDSTM001` record the firmware reads is a TMC location record, not a graph edge: `0x003bc960` decodes one raw record into a 496-byte (`0x1f0`) struct at `0x006f3918`, cleared and initialised by `0x003bbf6c` (`sdl_TMC_InitDataRecode`). Its twelve fields, in order, are location code, road number, road name, primary location, secondary location, area code, liner code, front code, rear code, urban attribute, exit/junction, inter-section code — the same twelve columns and order as the `LCTBL001` catalog. | VERIFIED | H | EXP-2026-11-06-M3.7-router-rdstm |
| C-883 | Decoded field offsets and accessors (`Navi.exe`): `+0x04` location code `0x003bbfe0`; `+0x06` area `0x003bc5e0`; `+0x08` liner `0x003bc628`; `+0x0a` front `0x003bc670`; `+0x0c` rear `0x003bc6b8`; `+0x0e` urban `0x003bc700`; `+0x10` inter `0x003bc8b8` (all u16); string fields with counts at `+0x12/+0x14/+0x16/+0x18/+0x1a` and blocks at `+0x1c/+0x40/+0xc4/+0x148/+0x1cc`: road number `0x003bc100`, road name `0x003bc26c`, primary `0x003bc3d8`, secondary `0x003bc548`, exit/junction `0x003bc820`. | VERIFIED | H | EXP-2026-11-06-M3.7-router-rdstm |
| C-884 | The raw record has no constant stride: fields are resolved through a per-record directory by `0x003f61bc(record,?,index)` over the schema lookup `0x003f51e0`, the length walk `0x003f56bc`/`0x003f5d98` (table at `record + 2*u16[record+2]`) and the offset accumulator `0x003f5e10`. Numeric fields use indexes 0, 5, 6, 7, 8, 9, 11; the five string fields have dedicated extractors. This is the mechanism behind the framing drift at `0x10a0` (C-106) and replaces a fixed record size. | OBSERVED | H | EXP-2026-11-06-M3.7-router-rdstm |
| C-885 | The road record is looked up by `(country code, location-database no, location code)`: the 48-byte SDL request built at `0x003bcb48` carries data type `0x14e4` (`0x003bcb90`) plus the three keys at `+32/+36/+40`, and the response is attached by `sdl_TMC_SetRecordAddr` (`0x003bc960` region, trace tag `0x00045268`). | OBSERVED | H | EXP-2026-11-06-M3.7-router-rdstm |
| C-886 | `RDSTM001` contains no speed, one-way, turn-restriction, toll or ferry attribute: the complete accessor surface for the record is one decoder (`0x003bc960`), twelve getters (C-883), `0x003bbf6c` and `sdl_TMC_SetRecordAddr`; none exposes such a field. The record cannot give routing a cost, direction or restriction. | VERIFIED (negative) | H | EXP-2026-11-06-M3.7-router-rdstm |
| C-887 | The router's link identity is mesh-based, not RDSTM-record-based: `link[mesh(0x%x),no(%d),rdtype(%d)]` `0x00011eb2`, `link[mesh(0x%x),no(%d,%d,%d),lktype(%d),rdtype(%d)]` `0x00011f0e`, `dir(%d),speed(%d)` `0x00011f46`, `RGD(TurnList)` `0x00020f30`; no `RDSTM`/`LCTBL` name and no record getter is referenced from the `RGD` handler band (`0x004ed410`, `0x004eeeb8`, `0x004f0b24`, `0x004f0d8c`, `0x004f21f8`) or `SVR_Rgd*` (`0x0037aed4`, `0x0037b02c`). | OBSERVED | M | EXP-2026-11-06-M3.7-router-rdstm |
| C-888 | `Navi.exe` uses the data-type code `0x14e4` in three code sites only: the descriptor lookup `0x003fa382` (`0x003f7384(type,out)`), the SDL request `0x003bcb48` and the volume/name selector `0x004125a8`; every other `0x14e4` byte in the module is data or a literal pool (e.g. `0x0009abe4`, `0x003fa5a8`). | VERIFIED | M | EXP-2026-11-06-M3.7-router-rdstm |
| C-889 | Consequence for M4.1–M4.3: `RDSTM001` must carry the twelve TMC fields for each record; speed/one-way/one-way restrictions cannot be sourced from it, so `M3.7`'s one-way/restriction part must come from the tile sections or `INTER001`/`FRWAY001`. | HYPOTHESIS | M | EXP-2026-11-06-M3.7-router-rdstm; C-886, C-887 |

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
| C-068 | RETRACTED: `0xc438a4` is a memory/fd statistics formatter, not the `\CMP.LST` opener; the real `\CMP.LST` is at `0xdf945d` with zero pointer references. | RETRACTED | — | Superseded by C-635 (H4); `cerom.py file2va 0xa438a4` places the old address in unnamed padding between modules, so the delta-era attribution is retired. EXP-2026-11-05-20 |
| C-069 | A TFAT16 volume starts at image offset `0x1C8400400` (OEM `MSWIN4.1`), with a WinCE TFAT hidden root (`DONT_DEL*`). | VERIFIED | H | FAT boot sector |
| C-085 | `SUM4` is a tagged checksum, but CRC-32, Adler-32 and plain word sums were rejected; the algorithm is unknown. | UNKNOWN | — | checksum probes |
| C-086 | For the map module's data, `VA = file_offset + 0x02000000`; code literals use at least one other delta, so the ROM is section-based. | OBSERVED | M | 21 pointer literals |
| C-087 | The pre-partition payload length is declared as `0x01752c88` (24,456,328 bytes) at `0x200000`; the bytes immediately after that offset are not a zero gap. | VERIFIED | H | header + byte check |
| C-088 | Build A's CE ROM segment parses as a standard XIP TOC: 149 modules, 1 file, CPU `0x01a6` (SH-4), physical range `0x8cae1000`–`0x8e233c88`, ROMHDR at file `0x01951b78`. | VERIFIED | H | `tools/ce_rom_parse.py`; EXP-2026-11-05-33 |
| C-089 | The CE ROM TOC resolves module names including `Navi.exe`, `NaviStateCC.dll`, `OBJDLL.dll` and `STDDLL.dll`; builds A, B and C each have a duplicate copy in the image. | VERIFIED | H | `tools/ce_rom_parse.py`; EXP-2026-11-05-33 |
| C-180 | The 24-byte ROM section records at `0x374000`/`0x3e0060` are `o32_rom`-shaped, but their `dataptr` fields point into `0xff` fill and the records do not share a delta. The table is **not usable** as a file map. | RETRACTED | — | Superseded by C-517/C-636 (H4); `cerom.py` parses the real `o32_rom` table for all 149 modules (527 sections) instead of the guessed records. EXP-2026-11-05-05 |
| C-181 | For the map module, two deltas suffice: code `VA = file + 0x02200000` (`0xc00000–0xc4b000`), `.rdata` `VA = file + 0x02000000` (`0xdf6000–0xe10000`). | VERIFIED | H | Ghidra code density + 21 literals |
| C-182 | Reader-related functions: `0xc438a4` is a memory/fd statistics formatter (retracted as `\CMP.LST` opener; real `\CMP.LST` at `0xdf945d` has zero refs); `0xc42520` dumps a file descriptor incl. `hcxcmp`; `0xc426a4` dumps dir/file counts; `0xc48380` installs `MAP_DATA READ`; `0xc0ebf8` allocates `0x1ac`. | RETRACTED | — | Superseded by C-635/C-522 (H4); the `0xc4xxxx` band is not a stable module under the CE TOC (`cerom.py modules`/`file2va`). EXP-2026-11-05-05, EXP-2026-11-05-20 |
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
| C-234 | Record `0x3221b0` decodes only if `dataptr` is payload-relative (`0x11000 → 0x211000`), implying delta `0x8c97b000`; 0/21 literals land on prologues. | RETRACTED | — | Superseded by C-637/C-517 (H4); `dataptr` is a physical pointer under the CE TOC, not payload-relative. EXP-2026-11-05-10 |
| C-235 | Next targets: copy/section descriptor list at `0x1952b00` (32-byte records) and export tables at `0x29eec0–0x29f700`. | RETRACTED | — | Superseded by C-638/C-381/C-517 (H4); `0x1952b00` is `TOCentry[121].ulE32Offset`, not a copy/section descriptor list. EXP-2026-11-05-10 |
| C-240 | PE export directories give a stable file base: TFAT.dll at `0x28e200`, 35/35 name-RVAs resolve, 34/35 exports are SH-4 prologues; `file = Fb + RVA`. | VERIFIED | H | EXP-2026-11-05-11 |
| C-241 | `module_scan.py` maps 26 modules (TFAT, DISKCACHE, FATUTIL, OLEAUT32, …). | VERIFIED | H | EXP-2026-11-05-11 |
| C-242 | VA base is recovered as constant `V − RVA` across exports; OLEAUT32 `Vb=0x03930000` verified with 282 literal sites (166 `jsr`). | VERIFIED | H | EXP-2026-11-05-11 |
| C-243 | `0x1952b00` is a RAM copy list, not a section map: no file offsets, sizes do not tile, and the value is not a CRC32. | RETRACTED | — | Superseded by C-638/C-381/C-517 (H4); the structure was mis-identified, it is a `TOCentry` field (`ulE32Offset`), not a RAM copy list. EXP-2026-11-05-11 |
| C-244 | The navi/map modules have no export directory in `0x44xxxx–0x1952c88`. | VERIFIED (negative) | H | EXP-2026-11-05-11 |
| C-245 | Import-descriptor candidates for navi modules are noisy/unverified; harden with ≥4 VA-like thunks + an IAT run into one of the 26 mapped modules. | OBSERVED | M | EXP-2026-11-05-11 |
| C-246 | The readers are still not located; nothing about the data formats is contradicted. | UNKNOWN | — | EXP-2026-11-05-11 |
| C-260 | The hardened import anchor returns 0 candidates: the ROM is pre-bound, so import directories are stripped. The round-6 import-anchor lead is retracted. | VERIFIED (negative) | H | EXP-2026-11-05-13 |
| C-261 | The export anchor still holds (26 modules), but navi/map modules have no export directory in `0x44xxxx–0x1952c88`. | VERIFIED | H | EXP-2026-11-05-13 |
| C-262 | The `o32_rom` section records do not cover the navi modules: no `dataptr` matches a known module file base. | RETRACTED | — | Superseded by C-636/C-517 (H4); `cerom.py sections` lists `o32_rom` records for Navi.exe and every Navi*CC module. EXP-2026-11-05-13 |
| C-263 | B/C builds differ by 4 bytes but lack build A's map code (`0xc42410`, `0xc438a4`); `0xc438a4` occurs 4× in A. B/C cannot pin A's map module. | VERIFIED | H | EXP-2026-11-05-13 |
| C-264 | Map module `.text` is file `0xc00000–0xc4b000`; `.rdata` is file `0xdf6000` = VA `0x02df6000`; `Vt < 0x02df6000`. | VERIFIED | H | EXP-2026-11-05-13 |
| C-265 | `jsr` targets at `0x02e0xxxx` belong to a different module (file `0xc00000`, delta `0x02200000`), not the map module. | VERIFIED | H | EXP-2026-11-05-13 |
| C-266 | Next anchor: ROM module table at `0x15271c8` (16-byte-stride names), self-name literal and shared-`.rdata` clusters. | PLANNED | — | EXP-2026-11-05-13 |
| C-270 | `0x15271c8` is not a module table: it is 4-byte-aligned packed module-name strings in a resource blob, padded to 4/16 bytes. | VERIFIED (negative) | H | EXP-2026-11-05-14 |
| C-271 | Self-name anchor cannot apply: the navi name strings belong to a different module; only 12 scattered hits, no ≥4-pointer cluster. | VERIFIED (negative) | H | EXP-2026-11-05-14 |
| C-272 | Adjacency `Vt=0x02dab000` is wrong (830 literals point at embedded PNG data); the call-target scan is flat (18/1122 prologues). | VERIFIED (negative) | H | EXP-2026-11-05-14 |
| C-273 | The `0x1952b00` field `+0x10` is a Unix timestamp (2011-06-22…07-29), not a checksum; the round-6 checksum claim is retracted. | VERIFIED | H | Re-verified under CE TOC: `0x1952b00` is `TOCentry[121]` and field `+0x10` is `ftTime` (Unix timestamp). `cerom.py romhdr`/EXP-2026-11-05-35. EXP-2026-11-05-14; EXP-2026-11-06-H4 |
| C-274 | The round-2 “call-to-string paradox” is withdrawn: `0x02200000` is plausible as the code delta, though not proven. | OBSERVED | M | EXP-2026-11-05-14 |
| C-275 | Static VA recovery from this image is exhausted; reader work must shift to relative call-graph tracing or hardware/dynamic tracing. | VERIFIED (negative) | H | EXP-2026-11-05-14 |
| C-516 | `ECEC` at `0x200240` is the CE ROM signature at image start + `0x40`: CE image start = file `0x200200`, VA `0x8cae1000`; `file = VA − 0x8cae1000 + 0x200200` for the whole region. `ROMHDR` at file `0x01951b78`: `physfirst 0x8cae1000`, `physlast 0x8e233c88`, `nummods 149`, `numfiles 1`, `usCPUType 0x01a6` (SH-4). | VERIFIED | H | EXP-2026-11-05-32; `tools/cerom.py` |
| C-517 | All 149 `TOCentry` names resolve to ASCII through C-516; `e32_rom` (112 B) / `o32_rom` (24 B) give exact `o32_realaddr`/`o32_dataptr` for 527 sections, 245 of them `IMAGE_SCN_COMPRESSED` RW data. | VERIFIED | H | EXP-2026-11-05-32; `tools/cerom.py` |
| C-518 | The TOC agrees exactly with the earlier anchors: OBJDLL `0x03480000`, `MAL_DataVol_getOffset` file `0x7f5f48` ↔ VA `0x03498d48`, OLEAUT32 `0x03930000`, VerInfoCC `0x031e0000`, NaviStateCC `0x02df0000`, iPodCC `0x02620000`; "TFAT" is `fatfsd.dll`. | VERIFIED | H | EXP-2026-11-05-32; `tools/cerom.py` |
| C-519 | `0x0367b180` is `BT_MGR.dll` code (file `0x6ef380`, prologue); file `0xe7b180` is `Navi.exe` VA `0x1fcf80`. No VA collision. | VERIFIED | H | EXP-2026-11-05-32; `tools/cerom.py` |
| C-520 | `0x0369d400` is a `BT_MGR.dll` import thunk (file `0x711600`) → IAT `0x01e72074` = `COREDLL.dll` ordinal 719. The chain `0x6fab2c`/`0x6faeb0`/`0x6fb05c` is in `BT_MGR.dll`. | VERIFIED | H | EXP-2026-11-05-32; `tools/cerom.py` |
| C-521 | The `HDD_INFO.TXT` and `SD Import: …` strings belong to `Navi.exe`; their absolute literals are in `Navi.exe` `.text` at VA `0x004e7d28` (paths) and `0x004e8584`/`0x004e995c` (comparator messages). The old `0x02800000` data-delta link to BT_MGR was a coincidence. | VERIFIED | H | EXP-2026-11-05-32; `tools/cerom.py` |
| C-522 | The "`0x2e0xxxx` thunk area / unknown shared library" is `NaviStateCC.dll` itself; `0x1d0f8a8` is in its compressed RW data; the "map module `.text` `0xc00000–0xc4b000`" spans NaviSetCC, NaviDrawCC and NaviStateCC. | VERIFIED | H | EXP-2026-11-05-32; `tools/cerom.py` |
| C-523 | `nk.exe`/`coredll.dll` are not in this ROM region; a kernel XIP region (`pExtensions 0x880030a4`) exists elsewhere. | HYPOTHESIS | M | EXP-2026-11-05-32; `tools/cerom.py` |
| C-524 | Every payload has a CE ROM header: `ECEC` at `0x200240`, `0x2000240` (A, 149 modules, VA base `0x8cae1000`, copies byte-identical), `0x3e00240`, `0x4800240` (B, 91 modules, VA base `0x88000000`), `0x5200240` (C, 88 modules, VA base `0x88000000`). | VERIFIED | H | EXP-2026-11-05-36; `tools/cerom.py` |
| C-525 | B and C are kernel regions (`nk.exe`, `coredll.dll`, `filesys.exe`, `gwes.exe`, `device.exe`, drivers); A has no kernel and imports `COREDLL`/`Errlogdll`/`SYS_INF`/`commondll` from them. | VERIFIED | H | EXP-2026-11-05-36; `tools/cerom.py` |
| C-526 | B contains the updater set (`UpdateMng.exe`, `PRGUpdate.exe`, `MapUpdate.exe`, `BtUpdate.exe`, `DisplayUpdate.exe`, …) and `UpdateNK.skn`; C contains `TestMode.exe`, `SdCardLch.exe`, USB and BT stacks. | VERIFIED | H | EXP-2026-11-05-36; `tools/cerom.py` |
| C-527 | `coredll.dll` (B, `vbase 0x03fa0000`) exports 1651 names, ordinal base 2: ordinal 719 = `sprintf`, 1071 = `strncpy`, 35 = `LocalSize`. | VERIFIED | H | EXP-2026-11-05-36; `tools/cerom.py` |
| C-528 | `0x0369d400` (C-520) is the `BT_MGR` thunk for `COREDLL!sprintf`; the `0x6faeb0` path-builder is BT_MGR code unrelated to the map-code check; the real `HDD_INFO` logic is in `Navi.exe` (C-521). | VERIFIED | H | EXP-2026-11-05-36; `tools/cerom.py` |
| C-529 | Which kernel image (B or C) boots with A, and the compression of `IMAGE_SCN_COMPRESSED` sections and `FILESentry` payloads, are unknown. | UNKNOWN | — | EXP-2026-11-05-36; `tools/cerom.py` |

## Kernel selection (M1.7)

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-700 | Builds B and C have identical `ulRAMStart` (`0x89e40000`), `ulRAMFree` (`0x89e73000`), `pExtensions` (`0x880030a4`) and `usCPUType` (`0x01a6`); both carry `nk.exe`, `coredll.dll`, `filesys.exe`, `device.exe`, `gwes.exe`. | VERIFIED | H | `tools/cerom.py --image-start 0x3e00200/0x5200200 IMG romhdr`; EXP-2026-11-06-M1.7 |
| C-701 | `ulRAMEnd` is `0x8e600000` for both B and C, i.e. above A's image (`0x8cae1000`–`0x8e233c88`) and not closing at A's `physfirst`; the two are indistinguishable on this field. | OBSERVED | H | ROMHDR above; EXP-2026-11-06-M1.7 |
| C-702 | The `pExtensions` block at `0x880030a4` is byte-identical between B and C except one character of a build-path string (`d:\` vs `c:\wince500\...\loader.c`); it is the standard WinCE `nk` debug string pool and carries no selection flag. | VERIFIED | H | raw image bytes at `0x3e032a4`/`0x52032a4`; EXP-2026-11-06-M1.7 |
| C-703 | The 4-byte header difference between B and C is the `nk.exe` entry point stored at image offset +12: B `0x8800ebd0`, C `0x8800ebb0` (bytes `d0 eb 00 88` vs `b0 eb 00 88`). | VERIFIED | H | raw image bytes; `cerom.py e32`; EXP-2026-11-06-M1.7 |
| C-704 | Across all modules of build B, the only code referencing any of `phys 0x08000020`–`0x0800002b` (P2 `0xa8000020`–`0xa800002b`) is `nk.exe` at `0x8804ccd6`...`0x8804cd2e` (12 `mov.l` loads). | VERIFIED | H | full-module literal scan; EXP-2026-11-06-M1.7 |
| C-705 | Those 12 bytes are consumed solely by `nk.exe`'s AERTRACE dump (`0x8804cc42`) and formatted as `"Navi Version : %c%c%c%c%c%c%c%c-%c%c%c"`; no comparison, mask or branch on them exists in `nk.exe`. | OBSERVED | H | strings at `0x8800e5a8`/`0x8800e7a0`; EXP-2026-11-06-M1.7 |
| C-706 | The SD image carries no bootloader (C-535); the on-board IPL selects which of B/C is copied to phys `0x08000000`. The SD image alone does not determine the boot choice. | OBSERVED | H | C-535; EXP-2026-11-06-M1.7 |
| C-707 | `PRGUpdate.exe` (B) manages two kernel slots (`NK1`, `NK2`) plus `BOOTLOADER` in flash (`UpdateToFlash`/`UpdateToSysSD`/`UpdateToUnfrm`, `NK1VerChk`/`NK2VerChk`); this is a maintenance/update path, not the SD boot selector. | OBSERVED | M | strings in `PRGUpdate.exe`; EXP-2026-11-06-M1.7 |
| C-708 | Image C is the test-mode build: `TestMode.exe` imports `CApi_GetBootMode`/`SetBootMode`/`GetBootModeEx` and is launched from image C's launch table (C-818); reaching it requires the IPL/boot-mode flag. | HYPOTHESIS | M | imports + launch table; EXP-2026-11-06-M1.7 |
| C-709 | Verdict for M1.7: the kernel is **IPL-selected**; the 12-byte boot-argument block (`0x08000020`–`0x0800002b`) is a Navi version string, not a kernel selector, and should be seeded as the factory version bytes for M8.B4. | VERIFIED (conclusion) | H | C-704, C-705, C-706; EXP-2026-11-06-M1.7 |

## Test mode (image C, M2.10)

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-810 | `TestMode.exe` is module #82 of image C: 334848 bytes, `load=0x887e9000`, `vbase=0x00010000`, 4 sections (2 uncompressed, 2 `IMAGE_SCN_COMPRESSED`). | VERIFIED | H | `tools/cerom.py --image-start 0x5200200 IMG sections TestMode.exe` |
| C-811 | `TestMode.exe` imports `COREDLL`, `CEDDK`, `commondll` (`CApi_GetSoftwareVersion`, `CApi_GetPartsNumber`, `CApi_GetDeviceVersion`, `CApi_GetBootMode`/`SetBootMode`/`GetBootModeEx`), `SYS_INF` (`SYS_DiagLogisCurrent`), `BT_ENG`, `BT_DB`. | VERIFIED | H | `tools/cerom.py ... imports TestMode.exe` |
| C-812 | The menu dispatcher is `0x0002b17c` and prints `CTestModeManager::TestModeFunctionMain >> Invalid MenuNo` (`0x00011b80`) / `Get Mode Error` (`0x00011bf8`). | VERIFIED | H | `tools/sh4xref.py --to 0x00011b80` |
| C-813 | The title/status screen is `0x0002bd04` (`Clarion Testmode` `0x00011ccc`, `Standby`/`Busy` `0x00011cbc`/`0x00011cf8`). | VERIFIED | H | `tools/sh4xref.py --to 0x00011ccc` |
| C-814 | `TestMode.exe` contains a version screen reading software/parts numbers including `GetMapVersion`/`GetMapPno` (`CVersionReadFunction`), calling `CApi_GetSoftwareVersion`/`CApi_GetPartsNumber`/`CApi_GetDeviceVersion`. | OBSERVED | M | strings at `0x00025cce`/`0x00026a86` (no literal-pool hit) |
| C-815 | `TestMode.exe` contains an SD read/write ageing test (`RUNNING [SD R/W (%s)]` `0x00011ef8`, `INSERT TEST DISC` `0x00011ec0`, `SD ERR`/`MECHA ERR`/`SLOPE ERR`) operating on `\SystemSD`, `\SystemSD2`, `\UserSD\AGING.csv`. | OBSERVED | M | strings; ageing manager error labels |
| C-816 | `TestMode.exe` contains a log writer (`create Log file failed!!` `0x00012ab8` referenced by `0x0002e678`/`0x0002ee28`; `CAgingManager::WriteLog` `0x000130a8` referenced by `0x0002ea94`). | VERIFIED | H | `tools/sh4xref.py --to …` |
| C-817 | `TestMode.exe` is registered in image C's launch table at file offset `0x55559cc` (VA `0x883557cc`) as `\windows\TestMode.exe`. | VERIFIED | H | raw image scan |
| C-818 | Entry into test mode appears gated by a boot-mode flag (`CApi_GetBootMode`/`SetBootMode`/`GetBootModeEx` imported); no key-combination string was found, so the physical trigger (service menu vs. boot flag) is unknown. | HYPOTHESIS | L | imports + string scan |
| C-819 | The two compressed `TestMode.exe` sections (`rva 0x4f000`, `0x5b000`) may contain additional menus; they are not decoded (codec unsupported, EXP-52/53). | UNKNOWN | — | `tools/cerom.py decompress --modules TestMode.exe` |

## MapUpdate.exe / updater (image B, M2.6)

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-770 | `MapUpdate.exe` is module #81 of image B: 65536 bytes, `load=0x88a9b000`, `vbase=0x00010000`, entry `0x0001e0d4`, three sections (code `rva 0x1000` vsize `0xf5ae`, `.rdata` `rva 0x11000` vsize `0x771`, compressed `rva 0x12000` vsize `0x358` not decoded). | VERIFIED | H | `tools/cerom.py --image-start 0x3e00200 IMG sections MapUpdate.exe` |
| C-771 | `MapUpdate.exe` imports `COREDLL.dll`, `CEDDK.dll` (`MmMapIoSpace`/`MmUnmapIoSpace`) and `commondll.dll` (`CApi_GetSramVirtualAddress`, `CApi_CommitSram`, `CApi_GetModelCode`, `CApi_MakeCRC16`); it loads `fatutil.dll` dynamically and resolves `FormatVolume`. | VERIFIED | H | `tools/cerom.py --image-start 0x3e00200 IMG imports MapUpdate.exe` |
| C-772 | The process entry `0x0001988c` creates the `MUTEX_MAP_UPDATE` mutex (errors if already running), allocates the manager and calls `ManageInit` `0x0001d888`; `ClassCreate` `0x0001d170` allocates `CMapUpdate` + `CMapUpIpc` and calls `MapUpdateInit` `0x00019b70`. | VERIFIED | H | `tools/sh4xref.py --image-start 0x3e00200 IMG MapUpdate.exe --calls ...` |
| C-773 | `MapUpdateInit` (`0x00019b70`) opens the `SDC1:`/`FMD1:`/`CEN1:` stores, resolves `FormatVolume` from `fatutil.dll`, maps flash with `MmMapIoSpace` and opens the `RCV_FLAP_OPERATE_STATUS` event. | VERIFIED | H | strings + call graph |
| C-774 | Validation methods and VAs: `SdCardExists` `0x0001a8c0`, `CheckSdInfoBuban` `0x0001a9b2`, `CheckNK1HeaderDBVer`/`CheckNK1HeaderBuban` `0x0001aa78`, `ValidateReplaceMapCard` `0x0001ab64`, `ValidateRewritedCard` `0x0001acac`, `CheckFlashNK1Code` `0x0001a314`, `SilentAuthenticate` `0x0001c210`, `GetTxtSdInfo` `0x0001b292`, `GetAdmSdInfo` `0x0001b0fa`, `SecurityUnLock/LockSet/Release/Status` `0x0001b3a0`/`0x0001b572`/`0x0001b8dc`, `GetVSramCompleteFlag`/`SetVSramCompleteFlag` `0x0001bfe6`/`0x0001c0ac`. | VERIFIED | H | string xrefs |
| C-775 | `MapUpdate.exe` opens the SD-card files `\UserSD\VER_INFO\HDD_INFO.TXT`, `\SystemSD\VER_INFO\HDD_INFO.TXT`, `\UserSD\HDD_ADM.TXT`, `\SystemSD\HDD_ADM.TXT`, `\UserSD\HDD_CHK.ATT`, `\SystemSD\HDD_CHK.ATT`, `\UserSD\ClarionUpdate.key`, `\SystemSD\ClarionUpdate.key`, `\SystemSD\MapFinish.key`, `\UserSD2\PRIVATE`, `\SystemSD2\PRIVATE`, plus stores `SDC1:`/`FMD1:`/`CEN1:`/`DSK1:`/`DSK8:`. | VERIFIED | H | UTF-16 string table |
| C-776 | Install/partition methods and VAs: `MapUpCopyFile` `0x0001a3cc`, `CopyFile` `0x0001bad0`, `UpdateDisk` `0x0001bcf2`, `DeleteAndCreatePartition`/`DeleteAllPartition` `0x0001c74c`, `DriveFormat` `0x0001c58c`, `CopyUserData` `0x0001c3ec`, `UnmountAllPart` `0x0001a044`, `GetFileCount` `0x0001a11c`, `AllocCopyBuffer` `0x0001c060`, `MapUpThreadEnd` `0x0001cc74`, `CheckForReplace` `0x0001ccfc`. | VERIFIED | H | string xrefs |
| C-777 | `MapUpdate.exe` communicates over the message queues `MSG_QUEUE_MAP_UPDATE`, `MSG_QUEUE_MNGER` and `MSG_QUEUE_PRG_UPDATE_CC` (`IPCSenderAP` `0x0001ca68`, `IPCSenderCC` `0x0001cb0c`; `MapUpIpcInit` `0x0001c980`). | VERIFIED | H | string xrefs |
| C-778 | `MapUpdate.exe` handles the VSRAM complete flag via `CApi_GetSramVirtualAddress` (`GetVSramCompleteFlag` `0x0001bfe6`, `SetVSramCompleteFlag` `0x0001c0ac`) and attests the card with `CApi_MakeCRC16` over `HDD_CHK.ATT` (`SilentAuthenticate` `0x0001c210`). | VERIFIED | H | imports + strings |
| C-779 | `MapUpdate.exe` does not parse map tile geometry; acceptance of a rebuilt card depends on the attestation/version checks here plus the runtime `Navi.exe` comparator (M2.1/M2.2). The byte-level attestation algorithm and the compressed section (`rva 0x12000`) are unknown. | HYPOTHESIS | M | OBSERVED |

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

## SD card identity and lock (SDHC.dll / AppLaunch.dll)

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-790 | `SD UNLOCK NG` is an entry in the `AppLaunch.dll` error-screen block (build B physical VA `0x8833681c`, build C `0x8834081c`), shown by the dispatcher at `0x8834ffb8` (B) / `0x88359c90` (C); a failed SD security-unlock maps to this screen. | VERIFIED | H | string search + M2.9 catalogue |
| C-791 | `AppLaunch.dll` checks the SD card security-lock state before launch and logs `AppLch >> Error!!! SD Card is [Security lock state] or [no Security]....` (B `0x88336278`, C `0x88340278`) and `AppLch >> SD Card Security Unlocked!` (B `0x88336310`, C `0x88340310`); referencing functions B `0x8834f5f4`, C `0x883592cc`. | VERIFIED | H | string search + sh4xref |
| C-792 | `SDHC.dll` implements the SD card password lock (CMD42) through `CDSKMain::Init`/`SDHC_SecurityUnLock` (B `0x884743c8`, C `0x8847f3c8`) which calls `CSDHCMain::SDHC_Lock_Unlock_Card` (B `0x88476df4`, C `0x88481df4`); failure returns `ERROR_ACCESS_DENIED` and leads to `SD UNLOCK NG`. | HYPOTHESIS | M | strings + sh4xref (no hardware) |
| C-793 | The unlock password is a firmware-side value: `SDHC.dll` logs it byte-by-byte as `dPassword[%02X]` with `byPasswordLen` (B `0x88471476`/`0x88471498`, C `0x8847c476`/`0x8847c498`); no derivation from CID, CSD, FAT serial or volume label is visible in the strings or code paths examined. | HYPOTHESIS | M | string search + sh4xref |
| C-794 | No SD CID or CSD-register check exists in `SDHC.dll`, `AppLaunch.dll` or `SdCardLch.exe`: the only UTF-16 `CID`/`CSD` occurrences are identifiers (`CSDCMain`, `CSDHCMain`, `CSDDirectAccess`) or unrelated telecom modules. | VERIFIED (negative) | H | whole-image + module string search |
| C-795 | No FAT volume serial number or volume-label check exists in `SDHC.dll`, `AppLaunch.dll` or `SdCardLch.exe`; `SdCardLch.exe` reads `partInfo.szVolumeName`/`szFileSys` only for mounting and logging. | VERIFIED (negative) | H | string search over the three modules |
| C-796 | `SdCardLch.exe` (image C, module #79) is an SD-card launcher/mounter only: it mounts `DSK1:`/`DSK8:`, logs partition/volume/filesystem names (including `RELIANCE`) and never compares an identity value. | OBSERVED | M | string search |
| C-797 | The firmware rejects a card for `SD UNLOCK NG` when it is in a security-lock state with a password that does not match, or when it has no security (no password set); it accepts only a card locked with the firmware's known password. | HYPOTHESIS | M | AppLaunch/SDHC strings (no hardware) |
| C-798 | A cloned card must reproduce the SD security-lock state / unlock password (locked with the firmware password); based on the firmware strings analysed it need not reproduce CID, CSD, FAT serial number or volume label. | HYPOTHESIS | M | C-794, C-795, C-797 |
| C-799 | The VAs above are physical VAs from `cerom.py file2va`; module-internal execution VAs differ by the module vbase (`SDHC.dll` `0x039b0000`/`0x03980000`, `AppLaunch.dll` `0x03bb0000`/`0x03b90000`). | VERIFIED | H | `cerom.py` |

## Error screens (AppLaunch.dll)

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-800 | The unit's error screens are a UTF-16LE string block in `AppLaunch.dll` (builds B and C); build A has none of them. | VERIFIED | H | string search over all modules in all three builds; `docs/format/validation.md` |
| C-801 | Build B holds the block at file `0x41369cc`–`0x4136af8` (physical VA `0x883367cc`–`0x88336af8`); build C at `0x55409cc`–`0x5540ad8` (`0x883407cc`–`0x88340ad8`). | VERIFIED | H | `cerom.py file2va` |
| C-802 | The block contains 25 entries in build B and 24 in build C; build C omits `NO SERVICE TOOL`. | VERIFIED | H | extraction of the UTF-16LE block |
| C-803 | `MAP DATA BASE UNMATCH`, `DIFFERENT MAP CODE` and `NAVI VERSION NG` are entries in this block (C-165 refined: they are in `AppLaunch.dll`, not `Navi.exe`). | VERIFIED | H | string search |
| C-804 | Every entry in the block is referenced by exactly one function per build: `0x8834ffb8` (B) and `0x88359c90` (C). | VERIFIED | H | literal-pool xref + prologue scan |
| C-805 | The showing function is a single dispatcher that selects a screen from an error code; `UNKNOWN ERROR` is the fallback. | HYPOTHESIS | M | single ref per string, shared literal pool |
| C-806 | No module other than `AppLaunch.dll` in builds A/B/C contains this error-screen string set (UTF-16 and ASCII search). | VERIFIED (negative) | H | whole-image string search |
| C-807 | Function-entry VAs above were recovered by a nearest-`sts.l pr` (`0x4f22`) prologue heuristic over the shared literal pool; exact boundaries are not symbol-confirmed. | OBSERVED | M | prologue scan |
| C-808 | Build A contains none of these strings (negative result). | VERIFIED (negative) | H | whole-image search over 149 modules |
| C-809 | The VAs in this catalogue are physical VAs from `cerom.py file2va`; module-internal VAs differ by the module vbase. | VERIFIED | H | `cerom.py` |

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
| C-070 | The US 2011 card uses the same `CLA-NAVI05-01` / `X08-02-00` format family as the EU 2011 card, but with market-specific data: label `QSD-301-103`, region code `SDC08-EVNAM`, firmware `X210NBNI.147`, 11 shards, 113 North America tiles, `XMD` instead of `TMC`, and `HDD_INFO` line 1 `QSD-301-100`. | VERIFIED | H | cardcheck, l2check, `tools/ce_rom_parse.py`; EXP-2026-11-05-35 |
| C-071 | Newer map sets contain additional files such as `TFTBL001` absent from the 2011 EU image. | OBSERVED | M | wiki screenshot; must be confirmed against a real newer image |
| C-072 | The exact meaning of `SDC08-EVEUR` is unknown (likely map/region/version code). | UNKNOWN | — | only appears in `HDD_INFO.TXT` |
| C-073 | In the EU image, `\x82FX210ECNI.158` starts at `0x00200014` and the version digits `158` start at `0x0020001f`. | VERIFIED | H | `leaf2011.img` hexdump |
| C-074 | The 72-byte `HDD_INFO.TXT` block appears byte-identically at image offset `0x06000000`. | VERIFIED | H | byte comparison |
| C-075 | SD lock is a CMD42 password (4 unit-specific bytes + ASCII `Clarion95321`), not file encryption; the unit stores it in flash near `0xA100`. | OBSERVED → part VERIFIED | M-H | external teardown/forum research; the ASCII `Clarion95321` half is now firmware-VERIFIED (C-1880, EXP-2026-11-06-M2.13) and the unit unlocked with the full PIN (C-1882); the 4 unit-specific bytes stay OBSERVED |
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
| C-126 | `B30R048R.DAT` section 4 has 20/24/24 records and 68/126/129 names in the 2011/2014/2016 images. | OBSERVED | M | EXP-2026-11-05-32 |

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
| C-530 | In the CE ROM images, code (`.text`) sections are never `IMAGE_SCN_COMPRESSED`; only RW data sections are. Driver and kernel code can be disassembled today. | VERIFIED | H | EXP-2026-11-05-37; `tools/cerom.py sections` |
| C-531 | The SoC is a Renesas SH-4A car-navigation part of the SH-Navi/SH-NaviJ family (SH7772x); BSP string `R0P7772A00020S`, OEM platform `CETUS`. Exact part number unproven. | HYPOTHESIS | M | EXP-2026-11-05-37 (PDB paths, driver set, QEMU `sh7785` run) |
| C-532 | On-chip peripherals used by the firmware: SCIF `0xffe40000`–`0xffe48000`, SD hosts `0xffe4c000`/`0xffe4d000`, TMU `0xffd80000`/`0xffd81000`, INTC-like `0xff802000`/`0xff804000`, CPG `MSTPCR` `0xffc80030`–`0xffc80044`, GPIO `0xffc41000`–`0xffc43000`, I2C `0xffc71000`, SSI `0xffe00000`, DMA-related `0xff801000`/`0xffc08000`; external devices in area 6 (`0x19300000`–`0x19e00000`). Not the SH7750/SH7751 map. | OBSERVED | M | EXP-2026-11-05-37 (literal pools of nk and drivers) |
| C-533 | Stock QEMU 8.2 (`-M none -cpu sh7785`, RAM only) runs image B `nk.exe` from its entry `0x8800ebd0` into the scheduler after one patched poll (`0xffe70808`); it stops because `MMUCR` is unmodelled (kernel-page call to VA `0x5b90` faults) and no timer interrupt arrives. | VERIFIED | H | EXP-2026-11-05-37; `tools/ce_qemu_probe.py --patch 0x88048b70=0900` |
| C-534 | The kernel debug port is an SCIF at `0xffe46000` (`SCFTDR +0x0c`, `SCFSR +0x10`, `TDFE 0x20`), register-compatible with QEMU `sh_serial`. | VERIFIED | H | EXP-2026-11-05-37; nk `0x8804cfa4` |
| C-535 | The SD card holds no bootloader (MBR only before `0x200000`); the IPL is on-board and loads B/C at phys `0x08000000` and A at `0x0cae1000`. Each CE image header starts with `u32` = `physlast − physfirst`. | OBSERVED | H | EXP-2026-11-05-37; ROMHDR, pre-partition scan |
| C-536 | Physical RAM layout: kernel XIP `0x08000000`, driver DMA buffers `0x09980000`–`0x09e40000`, CE RAM `0x09e40000`–`0x0cae1000`, app XIP `0x0cae1000`–`0x0e233c88`; area 4 (`0x10000000`) is used by the graphics/DSP drivers. | OBSERVED | M | EXP-2026-11-05-37; ROMHDR + driver literals |
| C-537 | Full-system emulation effort: F0 (debug log) days, F1 (stable kernel) 1–2 weeks, F2/F3 (drivers, SD) weeks each, F4 (`Navi.exe` headless) months, F5 (screen) open-ended. | HYPOTHESIS | L | `docs/research/full-system-emulation.md` §4 |

## Image archive / cross-year validation

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-500 | The complete public mirror set (four SD images and three map archives) is stored in `archive/images/` and all seven SHA-256 sums match. | VERIFIED | H | EXP-2026-11-05-30; `sha256sum -c archive/images/SHA256SUMS` |
| C-501 | L1 passes on the 2011, 2014 and 2016 ZE0-era SD images; 2016 requires `--ignore-dump-artifacts` because of AppleDouble files. The 2019 e-NV200 image fails because it is the different `CLA-NAVI06-01`/ZENRIN engine. | VERIFIED | H | EXP-2026-11-05-30; `tools/cardcheck.py --image …` |
| C-502 | L1 passes on the 2013-14, 2014-15 and 2016-17 map trees with `--partial --ignore-dump-artifacts`; their `DRSTR001.DAT` lists a `VER_INFO` directory that is absent from the archive. | VERIFIED | H | EXP-2026-11-05-30; `tools/cardcheck.py --root … --partial` |
| C-503 | Before the cross-year fixes, L2 was 2011-specific: `B30R048R.DAT` failed the byte-identical rebuild at `0x807`/`0x808` on the 2013–2016 archives, and the `POINT032` page `0x4200` POI mutation was a 2011 fixture. Superseded by C-504. | OBSERVED (historical) | H | EXP-2026-11-05-30; `tools/l2check.py --no-golden` |
| C-504 | L2 now passes on full 2014 and 2016 roots with `--no-golden --ignore-dump-artifacts`: `B30R048R` is byte-identical via a preserved-layout fallback, the REFER fixture is discovered per year, and `validate_mutation.py --drstr-dir` disambiguates `REFER001`/`REFER002`. | VERIFIED | H | EXP-2026-11-05-31; `tools/l2check.py`, `tools/ze0-viewer/ze0_tile_io.py` |
| C-940 | `B30R048R.DAT` (2011/2014/2016) stores blocks in a non-monotonic layout: slot 24 of the level-1 directory (kind `0x2246`) lives at offset `0x6000`, inside the padded range of slot 16 of the level-2 directory (`0x5a00..0x6800`); the two blocks overlap in storage (shared block). | VERIFIED | H | EXP-2026-11-05-M4.6-b30r048r-diff; `tools/ze0-viewer/harness.py verify` |
| C-941 | `addr_of` is not injective for offsets that are multiples of 2048: `0x60` and `0xc00` both decode to `0x6000`; the factory uses the non-canonical tag `0x00000060` for that block. | VERIFIED | H | EXP-2026-11-05-M4.6-b30r048r-diff; `tools/ze0-viewer/vendor/osm2clarion/tools/clarion_tile.py` |
| C-942 | `clarion_tile.read_tile` captures the original section-table tag (`ttag`) and each directory's original pointer tag (`ptr_tag`); `dir_bytes` keeps the original slot tag when the slot is unchanged. | VERIFIED | H | EXP-2026-11-05-M4.6-b30r048r-diff |
| C-943 | `clarion_tile.write_tile` reproduces `B30R048R.DAT` byte-identically for 2011/2014/2016 via a random-access preserve path (`_try_preserve_random`) that keeps every component at its original offset; no preserve fallback is needed. | VERIFIED | H | EXP-2026-11-05-M4.6-b30r048r-diff; `tools/ze0-viewer/harness.py verify` |
| C-944 | `tools/l2check.py` `tile_roundtrip` reports `preserved=0` on all three ZE0 roots after the fix. | VERIFIED | H | EXP-2026-11-05-M4.6-b30r048r-diff; `tools/l2check.py` |

| C-920 | Section 4 (per-parcel administrative/place-name index) of a ZE0 tile can be carried byte-identically through a road edit that does not change the set of road-containing parcels; the container writer does not need to rebuild section 4. | VERIFIED | M | EXP-2026-11-06-M4.4-section4-road-edit; in-place patched tile `B30R048R.DAT` |
| C-921 | A one-vertex road edit (one shifted vertex of one section-1 background shape) that stays inside its parcel leaves the section-4 payload byte-identical (20 records / 68 names, sha256 `4cbf35f2b3a77b0a9ed9de599099de3d8667d536434e95b5f98044361c7aad03`) for `B30R048R.DAT`. | VERIFIED | M | EXP-2026-11-06-M4.4-section4-road-edit; `tools/section4.py verify` |
| C-922 | The mutated tile with verbatim section 4 passes `harness.py verify` (round-trip byte-identical, 3396 records ok / 0 bad) and `l2check.py --no-golden` (RESULT: PASS). | VERIFIED | M | EXP-2026-11-06-M4.4-section4-road-edit; `tools/l2check.py` |
| C-923 | Section 4 parcel words at `0x00`/`0x02` enumerate road-containing parcels (derived from section 2 level 1, see `sec4_write.py`); they depend on road content only at parcel granularity. A within-parcel vertex shift does not change them. | OBSERVED | M | EXP-2026-11-06-M4.4-section4-road-edit; `tools/ze0-viewer/tools_ze0/sec4_write.py` |
| C-924 | Section 4 country code at `0x10` (300 = Greece) and the name strings (`0=…`) are administrative/place-name data and do not depend on road geometry. | VERIFIED | M | EXP-2026-11-06-M4.4-section4-road-edit; `tools/section4.py parse` |
| C-925 | The undocumented bytes at `0x06..0x0f` and the name-list placement are not affected by a within-parcel road edit and must be preserved verbatim (`section4.py encode build` refuses them, exit 3). | HYPOTHESIS | M | EXP-2026-11-06-M4.4-section4-road-edit; `tools/section4.py --selftest` |
| C-926 | `tools/section4.py preserve` re-emits the section-4 payload byte-identically; `verify` confirms 20 records / 68 names and a matching sha256 between the original and the edited tile. | VERIFIED | M | EXP-2026-11-06-M4.4-section4-road-edit; `python3 tools/section4.py verify` |
| C-927 | The in-place road edit changes exactly 116 bytes of one compressed stream (`0x2fac5..0x2fb73`); all other bytes, including every section-4 stream, are unchanged and the file size stays 1,358,592 bytes. | VERIFIED | M | EXP-2026-11-06-M4.4-section4-road-edit; byte diff |
| C-928 | `l2check.py` `tile_mutation` (one vertex) passes on a tile carrying section 4 when section 4 is carried verbatim (RESULT: PASS). | VERIFIED | M | EXP-2026-11-06-M4.4-section4-road-edit; `tools/l2check.py` |
| C-929 | A road edit that changes the road parcel set (new or removed road parcel) would require section 4 to change (parcel words / directory); `sec4_write.py` regenerates it from the road parcels. Carry section 4 verbatim otherwise. | HYPOTHESIS | M | EXP-2026-11-06-M4.4-section4-road-edit; `tools/ze0-viewer/tools_ze0/sec4_write.py` |

## Tooling and offline contracts (2026-11-05)

Built without vendor data; every row states what is synthetic-only.

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-542 | IMF v1 is a UTF-8 JSON Lines file (`imf=1`) with one header (pinned source + ODbL attribution), then nodes, ways and a restriction/boundary/route relation subset. Each record carries a stable `n\|w\|r<osm id>` id and a whole `BxxRyyR` cell; a way's `tile` is its first node's cell and `tiles` is the sorted set of all its nodes' cells. Speeds are integer cm/s, coordinates WGS84 degrees at 1e-7. Design only: the writer mapping is still undecided. | OBSERVED (design) | M | EXP-2026-11-05-44; `docs/research/intermediate-format.md`; Was proposed as C-542 in EXP-2026-11-05-44 |
| C-543 | `tools/imf_check.py` enforces 22 IMF schema/consistency rules (`E001`–`E022`), with one synthetic failure case per rule, and provides `--assign-tiles` (cell assignment round-trips byte-identically) and `--sample`. | VERIFIED (tool) | H | EXP-2026-11-05-44; `python3 tools/imf_check.py --selftest` |
| C-544 | `tools/diff_years.py` compares two ZE0 roots or raw images in seven read-only categories: tree census, `HDD_INFO.TXT` (plus the `0x06000000` copy), common header (text + `0x180`), `DRSTR001.DAT`, `MMAIN001` level table, tile inventory with `0x1ac`/`0x2ac` descriptors, and SHA-256 hashes. | VERIFIED (tool, synthetic) | H | EXP-2026-11-05-46; `python3 tools/diff_years.py --selftest`; Was proposed as C-544 in EXP-2026-11-05-46 |
| C-545 | In `diff_years.py`, `--partial` suppresses only differences caused by an absent `VER_INFO` subtree and `--ignore-dump-artifacts` only macOS dump entries; neither hides unrelated data differences. | VERIFIED (tool, synthetic) | H | EXP-2026-11-05-46; synthetic mutation runs; Was proposed as C-545 in EXP-2026-11-05-46 |
| C-546 | Section-4 records expose only the parcel words at `0x00`/`0x02`, type `0x0009` at `0x04` and ISO 3166 country at `0x10`; bytes `0x06..0x0f` and the name-list placement remain `UNKNOWN`, and `tools/section4.py parse` reports them as hex. | VERIFIED (tool) | H | EXP-2026-11-05-42; `python3 tools/section4.py --selftest`; Was proposed as C-520 in EXP-2026-11-05-42 |
| C-547 | Section-4 `preserve` re-emits the payload byte-identically; `build` refuses records with names or uncovered opaque bytes (exit 3). Until the grammar is mapped, edited tiles must carry section 4 verbatim. | VERIFIED (tool) | H | EXP-2026-11-05-42; `section4.py encode preserve/build`; Was proposed as C-521 in EXP-2026-11-05-42 |
| C-548 | The `0x180`–`0x1ff` header block has four documented regions: prefix `0x180`–`0x18b`, class area `0x18c`–`0x19f`, `ff` run `0x1a0`–`0x1ab`, and the descriptor container at `0x1ac`. | OBSERVED | M | `docs/format/file-header.md`; four published samples |
| C-549 | `MMAIN001.DAT` and `REFER002/COORD001.DAT` are identical in the documented header fields; no header-only REFER/MMAIN discriminator is known, so a bare header is reported `AMBIGUOUS`. | OBSERVED | M | `tools/header_block.py class`; published hexdumps |
| C-550 | The `0x1ac` container is `00`, `n_tables`, then `table_id`, `n_entries` and 4-byte `(level:u8, kind:u8, count:u16)` entries; `n_tables` is 3 for MMAIN/REFER, 2 for MAPAL and 1 for RDSTM in the documented samples. The count field is **big-endian** on the card (endianness clause corrected by C-1788; this row previously said `u16 LE`). | OBSERVED (VERIFIED for MAPAL via C-052; count endianness retracted, see C-1788) | M | C-052; `MAPAL001/B28R070R.DAT`, `MMAIN001.DAT`, `RDSTM001.DAT` @ `0x1ac`; EXP-2026-11-06-M3.8 |
| C-551 | The eight-byte list `05 04 02 07 0a 06 08 14` at `0x18c` is a per-language/code list. | HYPOTHESIS | L | C-037; `MMAIN001.DAT` at `0x18c`; no code→language mapping |
| C-552 | The `3f` bytes at `0x18c`–`0x19f` and the `ff` bytes at `0x1a0`–`0x1ab` are fill/reserved markers. | HYPOTHESIS | L | four published samples; no mutation experiment |
| C-553 | `tools/header_block.py` checks the 512-byte size, UTF-16BE magic, `0x180` prefix, descriptor container and block trailer, reports `OBSERVED` rules as warnings, and passes 37/37 synthetic self-tests. | VERIFIED (tool) | H | EXP-2026-11-05-40; `python3 tools/header_block.py --selftest` |
| C-554 | The 72-byte `HDD_INFO.TXT` layout is six CRLF-separated lines with **no** trailing CRLF; the six documented lines reproduce SHA-256 `9f014643…`, and appending CRLF gives 74 bytes. | VERIFIED | H | EXP-2026-11-05-41; reconstructed-bytes SHA-256; Was proposed as C-528 in EXP-2026-11-05-41 |
| C-555 | `tools/hddinfo.py` parses/serialises the block byte-identically (including arbitrary tail bytes) and passes 34 synthetic self-test checks. | VERIFIED (tool) | H | `python3 tools/hddinfo.py --selftest`; Was proposed as C-529 in EXP-2026-11-05-41 |
| C-556 | Model M0 derives the three compared numbers as the family digit of line 1, the digits of the line-4 prefix and the line-4 suffix token, with `userdata_type` bounded to `0..5`; it predicts ACCEPT/DIFFERENT MAP CODE per variant. Every prediction is unvalidated until the spare-card matrix runs. | HYPOTHESIS | L | EXP-2026-11-05-41; comparator chain C-300/C-301, mapping guess C-304; Was proposed as C-530 in EXP-2026-11-05-41 |
| C-557 | `tools/hddinfo.py matrix` annotates the 89 length-preserving variants (73 with `--no-permute`) with an M0 prediction in `MANIFEST.txt`, delegating generation to `tools/hddinfo_variants.py`. | VERIFIED (tool) | H | EXP-2026-11-05-41; `python3 tools/hddinfo.py matrix …`; Was proposed as C-531 in EXP-2026-11-05-41 |
| C-558 | The L3 harness skeleton (`tools/l3_harness/`) is a vendor-free, Ghidra-free contract layer: manifest build/validate with exact ACCEPT/REJECT verdicts and SHA-256/size checks, a declarative WinCE stub table with JSON Schemas, and `cerom`-report→Ghidra memory-map conversion. `runner run` exits 3 (`MISSING_GHIDRA`) or 4 (`BLOCKED`) instead of reporting a pass. | VERIFIED (tool) | H | EXP-2026-11-05-38; `python3 tools/l3_harness/selftest.py`; Was proposed as C-532 in EXP-2026-11-05-38 |
| C-559 | `l3_harness/rommap.py` accepts `segments[].modules[].sections[]` with `name`/`va`/`file_offset`/`size`/`characteristics`/`compressed` (plus `realaddr`/`dataptr`/`vsize`/`psize`/`flags` aliases), derives `r`/`w`/`x` from CE flags, keeps a BSS section loadable with `file_offset: null`, and rejects overlapping, zero-size, compressed, out-of-image and bad-selector sections. | VERIFIED (tool) | H | EXP-2026-11-05-38; `rommap.py selftest`; Was proposed as C-533 in EXP-2026-11-05-38 |
| C-560 | `tools/rdstm_schema.py scan` scores block/record framings by column diversity, small-int density, in-window `u32` pointers and modal tuple shape, with a printed `multiple_of` penalty; it ranks the true layout first on a synthetic 16-byte fixture. | VERIFIED (tool, synthetic) | M | EXP-2026-11-05-43; `python3 tools/rdstm_schema.py --selftest`; Was proposed as C-534 in EXP-2026-11-05-43 |
| C-561 | `rdstm_schema.py layout` decodes a user layout and reports graph reciprocity, back-reference and pointer rates (256/256 records on the synthetic graph). High reciprocity is consistent with, but does not prove, a `(src, dst)` reading. | VERIFIED (tool, synthetic) | M | EXP-2026-11-05-43; `layout` output; Was proposed as C-535 in EXP-2026-11-05-43 |
| C-562 | `rdstm_schema.py join` reports the share of 2-byte codes that occur as LCTBL catalog codes or name-string prefixes (100 % at `+0xc`, 0 % on padding `+0xe` in the synthetic fixture). The rate is a necessary condition, not a decoded index; the real-file rate is unmeasured. | VERIFIED (tool, synthetic) | M | EXP-2026-11-05-43; `join` output; Was proposed as C-536 in EXP-2026-11-05-43 |
| C-563 | `tools/selftest.py` now runs named built-in suites and auto-discovers `--selftest` in every `tools/*.py` (subprocess, 60 s timeout), with `--list`, `--only`, `--json`, `--verbose` and `--include-dir`; a missing tool is `SKIP`, never a failure. | VERIFIED (tool) | H | `python3 tools/selftest.py --list`; deliberate failing probe |
| C-564 | `tools/profile_validate.py` accepts all four shipped version-1 profiles through a legacy adapter and resolves 1 / 1 / 4 / 56 whole tiles for `dolnoslaskie-detail`, `dolnoslaskie-test`, `poland-full`, `europe-motorways`. | VERIFIED (tool) | H | EXP-2026-11-05-45; `python3 tools/profile_validate.py profiles/*.json` |
| C-565 | The whole Dolnośląskie bbox (14.0–17.9 E, 49.9–51.9 N) plus a 50 km buffer lies inside the single tile `B48R058R` (48.00–53.33 N, 12–20 E). The earlier “2–3 tiles” estimate is superseded. | VERIFIED | H | EXP-2026-11-05-45; tile formula in `docs/format/map-tiles.md` |
| C-566 | The EU 2011 tile space is a 63-cell addressable lattice (rows `B28`–`B68`, columns `R048`–`R078`) of which 45 exist as files; the 18 sea/empty cells cannot be enumerated without vendor data, so lattice-derived counts are upper bounds. | OBSERVED | M | `docs/format/map-tiles.md`; EXP-2026-11-05-45 |
| C-567 | `tools/build.py --dry-run` estimates 44.6 MB (`dolnoslaskie-detail`), 178.4 MB (`poland-full`) and 253.4 MB (`europe-motorways`) from documented road budgets plus placeholder refer/POI/admin budgets; every breakdown is labelled ESTIMATE and no writer exists yet. | OBSERVED (tool) | M | EXP-2026-11-05-45; `python3 tools/build.py --profile … --dry-run` |

| C-568 | `tools/cerom.py --selftest` pins the parser on a generated CE ROM: all 22 ROMHDR fields, `va2file`/`file2va` round-trip, TOC module/file names, per-section flags and file offsets, named exports and a corrupt-`ECEC` negative case (46 checks). Images A/B/C are still not pinned end-to-end. | VERIFIED (tool, synthetic) | H | EXP-2026-11-05-47; `python3 tools/cerom.py --selftest`; Was proposed as C-568 in EXP-2026-11-05-47 |

| C-569 | `tools/cerom.py memmap` (alias `ghidra`) emits the `rommap.py` section table for one CE segment: one block per `o32_rom` at `o32_realaddr` (`size` = `psize`, plus `vsize`/`rwx`), flags `IMAGE_SCN_COMPRESSED` and never emits compressed bytes as data, optionally writes a `createMemoryBlock` Ghidra script, and passes `rommap.py convert --skip-compressed` + `validate`. Synthetic ROM only. | VERIFIED (tool, synthetic) | H | EXP-2026-11-05-48; `python3 tools/cerom.py --selftest` (93 checks); Was proposed as C-569 in EXP-2026-11-05-48 |

| C-570 | `tools/cecompress.py` decodes two candidate CE-ROM codecs without vendor data: 4 KiB-window LZSS (flag byte, 0=literal/1=match, 12-bit offset, 4-bit length−3) and LZX block framing with an MSB-first 16-bit-LE bit reader, full decoding of stored blocks, and explicit `UNSUPPORTED` for verbatim/aligned; `detect` marks a candidate `confirmed` only when the decoded size equals `expected_size`. 186 checks prove symmetry only, so the codec used by real `IMAGE_SCN_COMPRESSED` sections remains UNKNOWN. | VERIFIED (tool, synthetic) | M | EXP-2026-11-05-52; `python3 tools/cecompress.py --selftest` |
| C-710 | `tools/sh4xref.py --to 0x003d1bb0` and `--to 0x003d1ba4` on image A `Navi.exe` reproduce EXP-50's four call sites: `jsr @r3` at `0x003778b2`, `0x00377b46` (getOffset) and `0x003778bc`, `0x00377b52` (getSize), each with its enclosing function (`0x00377870`, `0x00377ae0`). | VERIFIED (tool, image A) | H | EXP-2026-11-05-M1.8-sh4xref; `python3 tools/sh4xref.py IMG Navi.exe --image-start 0x200200 --to 0x003d1bb0` |
| C-711 | The HDD_INFO slot `0x004e7d28` in `Navi.exe` is read by one `mov.l @(disp,PC)` at `0x004e7bec`, inside the function starting at `0x004e7b8c`. The slot holds the pointer `0x001d51a8`, which points at the UTF-16 string `\UserSD\VER_INFO\HDD_INFO.TXT`. | VERIFIED (tool, image A) | H | EXP-2026-11-05-M1.8-sh4xref; `python3 tools/sh4xref.py IMG Navi.exe --image-start 0x200200 --to 0x004e7d28` |
| C-712 | The value `0x004e7d28` is not a 32-bit word in any uncompressed section of `Navi.exe`. It is the address of a pool slot that the code reads, not a literal the code loads. The TODO wording "literals at 0x004e7d28" refers to that slot address. | VERIFIED (tool, image A, negative) | H | EXP-2026-11-05-M1.8-sh4xref; `python3 tools/sh4xref.py IMG Navi.exe --image-start 0x200200 --to 0x004e7d28` (reading b empty) |
| C-713 | The HDD_INFO function at `0x004e7b8c` makes 9 register calls (`jsr @r3`): 7 calls to COREDLL import thunks (6 distinct ordinals `#1047`, `#1145`, `#1143`, `#59`, `#66`, `#1118`; `#59` is called twice), and 2 to module-local `sub_004dd1f0`. Its code ends at `rts` `0x004e7cfa`. COREDLL names are not resolved (export table not loaded). | OBSERVED (tool) | M | EXP-2026-11-05-M1.8-sh4xref; `python3 tools/sh4xref.py IMG Navi.exe --image-start 0x200200 --calls 0x004e7b8c` |

| C-571 | `tools/cerom.py decompress` walks every `IMAGE_SCN_COMPRESSED` `o32_rom` section of every discovered CE segment (byte-identical A/B copies are reported and not walked), decodes exactly `psize` stored bytes through `tools/cecompress.py` with `expected_size=vsize`, and classifies each as `OK` (length == vsize), `UNSUPPORTED` (codec/block type) or `FAIL` (decode/empty/range), recording a SHA-256 with `decoded`/`stored` scope; only `OK` is written. 167 synthetic checks cover one real LZSS section and one LZX-verbatim section. Whether the ZE0 sections decode remains UNKNOWN. | VERIFIED (tool, synthetic) | H | EXP-2026-11-05-53; `python3 tools/cerom.py --selftest` |
| C-572 | `tools/kernel_select.py` scores which CE segment boots with A (B vs C) on seven auditable criteria (`ram_overlap`, `ram_window`, `p_extensions`, `kernel_modules`, `updater_set`, `entry_point`, `duplicate`), prints pass/fail/unknown plus evidence, gates on the structural criteria and refuses a verdict without at least two differing criteria, one structural. Its 61 synthetic checks cover clear B, clear C, ties, missing kernel names and duplicate copies; fed only the B/C fields recorded in EXP-36 it returns `UNKNOWN`. | VERIFIED (tool, synthetic) | H | EXP-2026-11-05-54; `python3 tools/kernel_select.py --selftest` |

| C-573 | `tools/cerom.py files` keeps its default listing and, with `--extract DIR`, writes the stored `csize` bytes of every entry whose `csize != rsize`; `--decompress` classifies each via `tools/cecompress.py` with `expected_size=rsize` as `OK` (length == rsize, the only bytes written as contents), `UNSUPPORTED` or `FAIL`, with stable `--json` records. 223 synthetic checks; real payloads stay UNKNOWN (EXP-51). | VERIFIED (tool, synthetic) | H | EXP-2026-11-05-55; `python3 tools/cerom.py --selftest` |

| C-640 | A compressed `IMAGE_SCN_COMPRESSED` `o32` section starts with a 22-byte little-endian header: `u24 uncompressed_len`, `u24 compressed_total` (= `psize`), `u32 flags = 0x10`, `u32 uncompressed_len`, `u32 payload_len` (= `psize − 22`), `u32 uncompressed_len`; payload at `+22`. Holds on both recorded prefixes (`0x484/0x2c6/0x10/0x484/0x2b0/0x484` and `0xcc0/0x68c/0x10/0xcc0/0x676/0xcc0`); 243 of 245 sections unmeasured. | VERIFIED (2 recorded prefixes) | M | EXP-2026-11-05-M1.2a-comphdr; `python3 tools/cerom.py comphdr` |
| C-641 | `cerom.py comphdr` reports `HOLDS` only when all five header checks pass, `REFUTED` when a check fails and `UNPARSED` below 22 stored bytes; a one-byte `flags` change and the synthetic LZSS stream are correctly classified. | VERIFIED (tool, synthetic) | H | EXP-2026-11-05-M1.2a-comphdr; `python3 tools/cerom.py --selftest` |



## Housekeeping / documentation refresh (H2)

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-610 | `AGENTS.md` now starts its firmware command with `tools/cerom.py` (`romhdr` on build A) instead of the legacy `tools/ce_rom_parse.py` scanner; the CE ROM TOC is the entry point for every firmware address. | VERIFIED | H | AGENTS.md "Firmware: CE ROM TOC path and dead ends"; `python3 tools/cerom.py --selftest` |
| C-611 | The old map-code comparator chain `0x6fab2c` → `0x6faeb0` → `0x6fb05c` with data delta `0x02800000` is `BT_MGR.dll` code, not the map-code check (C-520, C-528); it is listed as a retired lead in `AGENTS.md`. | VERIFIED | H | C-520, C-528; AGENTS.md dead-end list |
| C-612 | The real `HDD_INFO.TXT`/`SD Import` literals are in `Navi.exe`: path slot `0x004e7d28`, comparator messages `0x004e8584`/`0x004e995c` (C-521); `MAL_DataVol_getOffset` call sites at `0x003778b2`/`0x00377b46` (EXP-50). | VERIFIED | H | C-521; EXP-2026-11-05-50; `tools/sh4xref.py` |
| C-613 | `docs/research/l3-ghidra.md` no longer presents the retired comparator chain as a reader entry point; reader entry points remain `UNKNOWN` until M2/M3, and the retired chain is attributed to C-520/C-528. | VERIFIED | H | l3-ghidra.md status table |
| C-614 | `docs/research/feedback-loop.md` carries the L5 verdict "Superseded by EXP-2026-11-05-37": stock QEMU's SH-4A CPU runs B's `nk.exe` into the scheduler; the full board model (M8) is still unbuilt. | VERIFIED | H | EXP-2026-11-05-37; feedback-loop.md Option B |
| C-615 | `docs/format/cerom.md` §5 marks `e32_rom`/`o32_rom` layout and field decoding `VERIFIED` via `tools/cerom.py` (EXP-2026-11-05-35/36/48); the CE compression scheme and per-section initial-value policy remain `UNKNOWN` (M1.2/M1.3). | VERIFIED | H | cerom.md §5; `python3 tools/cerom.py --selftest` |
| C-616 | `tools/cerom.py` is the firmware parser of record (`romhdr`, `modules`, `files`, `sections`, `exports`, `imports`, `va2file`, `file2va`, `extract`, `memmap`/`ghidra`, `decompress`); `tools/ce_rom_parse.py` is the legacy whole-image `ECEC` scanner pending H3. | VERIFIED | H | cerom.md "Tool"; `python3 tools/cerom.py --help` |
| C-617 | Old TODO-section links (`TODO Step`, `Gate 0a`) in non-historical docs (`roadmap.md`, `open-questions.md`, `cerom.md`) were updated to current M-stream IDs; the frozen history file keeps them. | VERIFIED | H | `grep -rn "TODO Step\|TODO.md Step\|Gate 0a" docs/` |
| C-618 | `grep -n "0x6faeb0\|0x02800000"` in `AGENTS.md`, `l3-ghidra.md`, `feedback-loop.md`, `cerom.md` and `roadmap.md` hits only the dead-end list in `AGENTS.md` that names C-520/C-528. | VERIFIED | H | `grep` over the five files |
| C-619 | The documentation refresh touches no code; `python3 tools/selftest.py` remains green. | VERIFIED | H | `python3 tools/selftest.py` |

| C-690 | `tools/cerom.py thunks [MODULE\|--all] [--json] [--min-coverage N]` finds the 4-insn stub and its 3-/2-insn variants in uncompressed code sections, computes `stub_va` = realaddr + offset and `slot_va` as the loaded literal, resolves it through the importing module OFT and the exporter export table, and emits stable records with confidence plus stub/slot coverage; `--min-coverage` exits 1 below the threshold. 344 synthetic checks; the real `Navi.exe` 846-slot coverage is UNKNOWN. | VERIFIED (tool, synthetic) | H | EXP-2026-11-05-M1.6b; `python3 tools/cerom.py --selftest` |

| C-650 | `tools/cecompress.py` adds an LZNT1 decoder ([MS-XCA] 2.5: 4 KiB chunks, 16-bit header with payload−1 in bits 11…0, signature 3 in bits 14…12, flag bit 15, literal/match tokens with displacement−1 high and length−3 low at a `max(4, bits(u−1))` split, zero header terminates) validated against the spec's 59-byte example (142-byte output), XPRESS LZ77/Huffman skeletons that parse their header then raise `UNSUPPORTED`, and `probe FILE --size N [--offsets 0-32] [--methods …]` which tries every method × offset, records one status per attempt and reports only exact-size matches with content evidence; 391 checks. No real payload exists in the checkout, so the image codec is UNKNOWN. | VERIFIED (tool, synthetic + spec vector) | H | EXP-2026-11-05-M1.2b; `python3 tools/cecompress.py --selftest` |

## Housekeeping / CE ROM tool consolidation (H3)

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-620 | `tools/cerom.py scan IMG` scans the whole image for `ECEC` segments (including duplicate copies) and reports the same 5 segments as the legacy scanner on `IMG256`: A (149 modules), A copy (149), B (91), B copy (91), C (88). | VERIFIED | H | `python3 tools/cerom.py /tmp/opencode/IMG256 scan`; EXP-2026-11-06-H3 |
| C-621 | `scan` reuses `CERom`/`find_segments` validation (`nummods`, `physfirst <= pTOC < physlast`, TOC in bounds) and does not collapse duplicate copies, unlike `find_segments`. | VERIFIED (tool) | H | `tools/cerom.py` `scan_all_segments()` |
| C-622 | `tools/ce_rom_parse.py` is now a thin wrapper that forwards `--image`/`--offset`/`--out` (and positional image) to `tools/cerom.py scan` and prints a deprecation notice on stderr. | VERIFIED | H | `python3 tools/ce_rom_parse.py --image /tmp/opencode/IMG256` |
| C-623 | `tools/l3_harness/rommap.py` documentation names `tools/cerom.py ... memmap` as the report source (legacy scanner noted as fallback). | VERIFIED | H | `tools/l3_harness/rommap.py` module docstring |
| C-624 | `tools/cerom.py --selftest` (344 checks) and `tools/l3_harness/rommap.py selftest` (19 checks) both pass after the change. | VERIFIED | H | `python3 tools/selftest.py` |
| C-625 | `scan --out FILE` writes a JSON report in the legacy `ce_rom_parse.py` shape (segment base, `pTOC`, `size`, `romhdr`, modules, files). | VERIFIED | H | `python3 tools/cerom.py IMG scan --out /tmp/scan.json` |
| C-626 | `scan` reads the whole input file (not the 128 MiB window used by other subcommands) so segments beyond 128 MiB are still found. | VERIFIED | H | `tools/cerom.py` `main()` scan branch |
| C-627 | `scan --offset N` restricts candidates to segment bases at or after `N`, matching the legacy `--offset` filter. | VERIFIED | H | `tools/cerom.py scan --offset` |
| C-628 | No vendor data was committed; only code, docs and the task/claim updates. | VERIFIED | H | `git status` |
| C-629 | H3 complete: one CE ROM parser (`tools/cerom.py`) with `scan` for whole-image segment discovery; `ce_rom_parse.py` is a deprecated wrapper. | VERIFIED | H | EXP-2026-11-06-H3 |

## Delta-era firmware claim audit (H4)

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-630 | Audit of firmware claims from EXP-05…29: every candidate row (C-068, C-180, C-182, C-234, C-262, C-370…C-375 and the `0x1952b00` copy-list claims C-235/C-243/C-273/C-381/C-423) was re-checked against `cerom.py` (CE ROM TOC) and either re-verified with a module/section/offset or marked `RETRACTED` with `Superseded by`. | VERIFIED | H | EXP-2026-11-06-H4; `python3 tools/cerom.py --image-start 0x200200 archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img …` |
| C-631 | C-374's MAL chain is re-verified under the CE TOC: `MAL_DataVol_getOffset` is at file `0x007de200`/physical `0x8d0d6d48` and `getSize` at `0x8d0d6d28`, inside `OBJDLL.dll` `.text` (section rva `0x00001000`, vbase `0x03480000`); `cerom.py file2va 0x7f5f48` and `cerom.py sections OBJDLL.dll`. | VERIFIED | H | EXP-2026-11-06-H4 |
| C-632 | C-370's export-directory observation is re-verified: `cerom.py exports MODULE` resolves per-module export directories and RVAs under the CE TOC instead of the retired delta scan. | VERIFIED | H | EXP-2026-11-06-H4; `python3 tools/cerom.py --image-start 0x200200 … exports OBJDLL.dll` |
| C-633 | The `0x2e0xxxx` region is `NaviStateCC.dll` (vbase `0x02df0000`) under the CE TOC (C-522); the retired "import-thunk area / unknown shared library" interpretation (C-371, C-373) is superseded. | VERIFIED | H | EXP-2026-11-06-H4; `python3 tools/cerom.py --image-start 0x200200 … modules` (NaviStateCC.dll) |
| C-634 | `NaviStateCC.dll` is confirmed by `cerom.py modules` (vbase `0x02df0000`), but its COM vtable is built at runtime, so the fd/IOB slot layout (C-375) is not statically recoverable; remains `UNKNOWN`. | UNKNOWN | — | EXP-2026-11-06-H4; C-434/C-436 |
| C-635 | Delta-era addresses in the `0xc4xxxx` band (C-068, C-182) are not stable module VAs under the CE TOC (`cerom.py file2va 0xa438a4` lands in inter-module padding); those claims are retracted. | RETRACTED | — | EXP-2026-11-06-H4 |
| C-636 | The retired `o32_rom`-coverage negatives (C-180, C-262) are superseded: `cerom.py sections MODULE` lists `o32_rom` records for `Navi.exe` and every `Navi*CC` module. | RETRACTED | — | EXP-2026-11-06-H4; `python3 tools/cerom.py --image-start 0x200200 … sections Navi.exe` |
| C-637 | The payload-relative `dataptr` hypothesis (C-234) is superseded by C-517: `dataptr` values are physical pointers under the CE TOC. | RETRACTED | — | EXP-2026-11-06-H4 |
| C-638 | The `0x1952b00` "copy list" claims (C-235, C-243, C-381, C-423) are retracted: `0x1952b00` is `TOCentry[121].ulE32Offset`, not a copy/section list. C-273's `+0x10` Unix-timestamp observation is re-verified as the `TOCentry.ftTime` field. | RETRACTED / VERIFIED | H | EXP-2026-11-06-H4; EXP-2026-11-05-35 |
| C-639 | The H4 audit is complete: all named candidate rows now carry either a `VERIFIED` status with a `cerom.py` module/section/offset or a `RETRACTED` status with `Superseded by`; no delta-era firmware claim remains unaudited. | VERIFIED | H | EXP-2026-11-06-H4 |

## M3.4 — `DRSTR001.DAT` parser search (C-850–C-859)

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-850 | Under the real CE ROM VA model, `DRSTR001.DAT` occurs as an ASCII literal in `Navi.exe` at VA `0x0017ab24` (build A) and has a code xref: literal pool `0x00419870` holds it, loaded at `0x00419732` (r5) in function `0x00419684`, which is called from `0x00419d24`. | VERIFIED | H | `tools/sh4xref.py`; EXP-2026-11-06-M3.4-drstr-parser |
| C-851 | `\\CMP.LST` occurs in `Navi.exe` at VA `0x0017b25c` with a code xref: pool `0x0041bbb0`, loaded at `0x0041bad0` in function `0x0041ba90`, called from `0x00419ca0`. | VERIFIED | H | `tools/sh4xref.py`; EXP-2026-11-06-M3.4-drstr-parser |
| C-852 | `MAPAL001` occurs in `Navi.exe` at VA `0x00179f98` only inside a static filename table (pools `0x00179cf8`/`0x00179d04`/`0x00179d10`); `tools/sh4xref.py --to 0x00179f98` finds no `mov.l` load in executable sections. `LEV3456R.DAT` at `0x00179fa4` does have a direct code xref (`0x0040a022` in fn `0x0040a014`). | VERIFIED (negative for direct xref) | H | `tools/sh4xref.py`; EXP-2026-11-06-M3.4-drstr-parser |
| C-853 | `RDSTM001` (`0x00179398`) and other filenames (`REFER001.DAT`, `REFER002`, `INTER001.DAT`, …) appear in the same static filename table and some have code xrefs; firmware uses a filename table, not scattered literals. | OBSERVED | M | string scan; EXP-2026-11-06-M3.4-drstr-parser |
| C-854 | Functions `0x00419684` and `0x0041ba90` are CD-ROM/media-manager routines invoked during media initialisation (`0x00419d24`/`0x00419ca0`); they are the only build-A code paths naming `DRSTR001.DAT`/`CMP.LST`. | OBSERVED | M | call graph; EXP-2026-11-06-M3.4-drstr-parser |
| C-855 | No dedicated DRSTR count/order/sentinel check was identified statically: the 40-node/324-entry layout and leading `u32 = 0x0000002f` remain file-side invariants whose firmware validation is UNKNOWN. | UNKNOWN | — | EXP-2026-11-06-M3.4-drstr-parser |
| C-856 | Positive control for the xref method: `tools/sh4xref.py IMG Navi.exe --image-start 0x200200 --to 0x004e7d28` reproduces the EXP-50 call site `0x004e7bec` in function `0x004e7b8c` (C-521), so the method would report a load if one existed. | VERIFIED | H | `tools/sh4xref.py`; EXP-2026-11-06-M3.4-drstr-parser |
| C-857 | C-331 ("map filenames have zero literal references") is retracted in part for `DRSTR001.DAT` and `\\CMP.LST` (and for `MAPAL001` as a direct code literal; it survives only as a static-table entry). Superseded in part by C-850–C-852. | VERIFIED (retraction) | H | EXP-2026-11-06-M3.4-drstr-parser |
| C-858 | The search covered all uncompressed sections of `Navi.exe`, `NaviMapCC.dll`, `OBJDLL.dll`, `STDDLL.dll` (build A); `DRSTR001.DAT`/`CMP.LST` literals occur only in `Navi.exe`. Raw-image scan of the first 256 MiB found only the two build-A copies of the `DRSTR001.DAT` literal. | VERIFIED | H | EXP-2026-11-06-M3.4-drstr-parser |
| C-859 | The leading `u32 = 0x0000002f` of `DRSTR001.DAT` equals the ASCII root name `/`; no code in build A was found that compares against this constant, so the candidate check remains unverified. | UNKNOWN | — | EXP-2026-11-06-M3.4-drstr-parser |

## Board review 2026-11-06 (H5)

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-1710 | `coredll.dll` (image B) names the ordinals used by `Navi.exe` `fn 0x004e7b8c`: 1145 `_wfopen`, 1143 `fgetws`, 59 `wcschr`, 66 `wcsncpy`, 1047 `memset`, 1118 `fclose`; and by `fn 0x004dd028`: 496 `Sleep`, 65 `wcsncmp`. The M2.1 blocker "COREDLL export table not in the image" is wrong: the table is in B, not A. | VERIFIED | H | EXP-2026-11-06-H5-pm-review; `cerom.py --image-start 0x3e00200 IMG256 exports coredll.dll` |
| C-1711 | `fn 0x004e7b8c` opens `HDD_INFO.TXT` with `_wfopen`, reads it line by line with `fgetws`, splits with `wcschr` and copies fields with `wcsncpy`; it is the text parser M2.3 needs. | OBSERVED | M | C-1710; call list from EXP-2026-11-05-M2.1-hddinfo-fn |
| C-1712 | On `IMG256` image A, `cerom.py comphdr --all` gives 187 HOLDS, 58 REFUTED, 0 UNPARSED of 245 compressed sections. | VERIFIED | H | EXP-2026-11-06-H5-pm-review |
| C-1713 | The 58 REFUTED sections share a second header form whose flag word is `0x10000000 \| psize`. | HYPOTHESIS | M | EXP-2026-11-06-H5-pm-review (rows sampled, not all checked) |
| C-1714 | `cerom.py thunks` matches no import stub in any module of real image A (error on `Navi.exe` and `--all`); C-690's real coverage is 0 %, not UNKNOWN. | VERIFIED (negative) | H | EXP-2026-11-06-H5-pm-review |
| C-1715 | On the real `NaviMapCC.dll` sections 1 and 2, `cecompress.py probe` finds no exact-size match for lzss, lzx, lznt1 and xpress-huffman at offsets 0…40 (sizes `0x484`, `0x5b8`, `0xcc0`); xpress-lz77 is untested (skeleton). | VERIFIED (negative) | H | EXP-2026-11-06-H5-pm-review |
| C-1716 | From this cloud environment, `download.geofabrik.de`, `overpass-api.de` and `api.openstreetmap.org` are refused by the network policy (proxy 403); only `files.viaaq.eu` is allowed. | OBSERVED | H | EXP-2026-11-06-H5-pm-review |

## M3.5 — Tile reader entry and the level table (C-860–C-869)

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-860 | `NaviMapCC.dll` (build A) exposes only the four COM entry points (`DllCanUnloadNow`, `DllGetClassObject`, `DllRegisterServer`, `DllUnregisterServer`) and contains no `MESH_ID`, `DIVID` or `VTb` literals in its uncompressed sections. | VERIFIED (negative) | H | `tools/cerom.py extract`; grep over `/tmp/opencode/nmc/*.bin`; EXP-2026-11-06-M3.5-tile-reader |
| C-861 | The `MESH_ID`/`DIVID`/tile reader code lives in `Navi.exe` (build A), whose first section (VA `0x00011000`, `psize 0x0054be00`) holds the full diagnostic string set (`CELL_TBL MAKE …`, `MAP_DATA READ …`, `RGD_DATA READ …`, `MESH_ID = %08x \| DIV_CODE = %04x`, …). | VERIFIED | H | `tools/cerom.py extract Navi.exe`; EXP-2026-11-06-M3.5-tile-reader |
| C-862 | `CELL_TBL MAKE START MESH_ID=%08x DIVID=%04x` (and the `DIVID=----` variant) is stored at VA `0x0017c358`/`0x0017c388` and has code xrefs: literal pool `0x00425aa8` → load `0x00425a3a` (r4) in function `0x004259bc`, and pool `0x00427858` → load `0x004277c4` (r4) in function `0x0042752c` (entry `0x0042757a`). | VERIFIED | H | `tools/sh4xref.py`; EXP-2026-11-06-M3.5-tile-reader |
| C-863 | `CELL_TBL MAKE END MESH_ID=%08x DIVID=%04x` (and the `DIVID=----` variant) is stored at VA `0x0017be4c`/`0x0017be1c` and has a code xref: pool `0x0041f3d0` → load `0x0041f2e4` (r4) in function `0x0041f26c`. | VERIFIED | H | `tools/sh4xref.py`; EXP-2026-11-06-M3.5-tile-reader |
| C-864 | Reader VAs (Navi.exe, build A): cell-table MAKE (START) `0x004259bc` and `0x0042757a`; cell-table MAKE (END) `0x0041f26c`. These are the tile/cell-table make/read paths. | OBSERVED | M | xref graph; EXP-2026-11-06-M3.5-tile-reader |
| C-865 | The dump header `VTb Tp;Lv;St;F# \| L1;L2;L3;L4;L5;L6 \| Sz;Adr` is stored at VA `0x001783a1` and has **no** direct `mov.l` xref; it is reached through the pointer table at `0x003ec3d4`…`0x003ec414` (which contains `0x001783a0` at `0x003ec400`). | VERIFIED (negative for direct xref) | H | `tools/sh4xref.py --to 0x001783a1` (no hits); table scan; EXP-2026-11-06-M3.5-tile-reader |
| C-866 | The `VTb` dump documents a six-level table whose per-entry fields are: type `Tp`, level `Lv`, status `St`, file number `F#`, six level slots `L1`…`L6`, size `Sz`, address `Adr`. | VERIFIED | H | format string at `0x001783a1`; EXP-2026-11-06-M3.5-tile-reader |
| C-867 | C-225 ("tile reader not located; only `MAP_DATA`/`MESH_ID` strings and the `0x1ac` allocation remain") is superseded in part: the reader code is now located in `Navi.exe` at the VAs in C-864; the `0x1ac` allocation is unrelated (C-296 retraction stands). Superseded by C-860–C-864. | VERIFIED (retraction) | H | EXP-2026-11-06-M3.5-tile-reader |
| C-868 | C-295 ("dump headers document a six-level table `VTb Tp;Lv;…`") is confirmed: the six-level table is a firmware concept (debug dump) and its field layout is now recorded (C-866); it is **not** the `0x1ac` tile descriptor (C-296) and is not stored in the tile files. | VERIFIED | H | format string + xrefs; EXP-2026-11-06-M3.5-tile-reader |
| C-869 | The tile files (`BxxRyyR.DAT`, `LEV3456R.DAT`) carry no firmware six-level table in their headers; the `VTb` table is a runtime/firmware structure, so `map-tiles.md`'s on-disk format description is unchanged by this task. | VERIFIED | H | EXP-2026-11-06-M3.5-tile-reader; `docs/format/map-tiles.md` |

## M4.14 — Cross-year and cross-market archive (C-1020–C-1029)

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-1020 | The complete inventory of `files.viaaq.eu` map images/archives is eight files, each with a verified SHA-256 (see `docs/research/image-versions.md`). | VERIFIED | H | `sha256sum`; `EXP-2026-11-06-M4.14-cross-year-archive` |
| C-1021 | Within the ZE0 family (2011–2016, EU and US), `FORMAT VERSION` (`X08-02-00`), model (`CLA-NAVI05-01`) and engine (`V05.00.00`) are constant; only `DATA VERSION` changes with the map build. | VERIFIED | H | `cardcheck.header_fields`; `EXP-2026-11-06-M4.14` |
| C-1022 | `HDD_INFO.TXT` lines 1 (`QSD-302-100`) and 4 (`SDC08-EVEUR`) are constant across EU ZE0 samples; lines 2, 3, 5 and 6 track the map code, build, year-month and part number. | VERIFIED | H | `diff_years.py` (2011 vs 2014/2016); `EXP-2026-11-06-M4.14` |
| C-1023 | The `MAPAL001` tile set stays 45 `BxxRyyR.DAT` + `LEV3456R.DAT` across EU ZE0 samples, but tile sizes, record counts and bboxes change with the map build. | OBSERVED | H | `diff_years.py`; `EXP-2026-11-06-M4.14` |
| C-1024 | `REFER001` keeps 194 `.cmp`/`.ind` pairs in every ZE0 sample; the logical byte total grows with the map build. | VERIFIED | H | `cardcheck`; `EXP-2026-11-06-M4.14` |
| C-1025 | `REFER002` grows from 2 files / 15 POINT shards (2011) to 16 files / 29 shards (2016); `ICODE001.DAT` appears from the 2013 map set. | OBSERVED | M | directory census; `EXP-2026-11-06-M4.14` |
| C-1026 | `MMAIN001.DAT` level-table record counts (sections 1/2/4, levels 1/2) change with the map build. | OBSERVED | H | `diff_years.py`; `EXP-2026-11-06-M4.14` |
| C-1027 | `DRSTR001.DAT` entry `value`s (file sizes) and its directory set (`TFTBL001`, extra `SPEECH` languages) change with the map build. | OBSERVED | H | `diff_years.py`; `EXP-2026-11-06-M4.14` |
| C-1028 | `ENV200_2019_25920-6WX1C-EUR.img` is a different engine family (`CLA-NAVI06-01` / `X08-03-00` / `ZENRIN`, `DB_INFO.TXT`, 53 tiles, 200 `.cmp` pairs) and is not a ZE0 reference. | VERIFIED | H | `cardcheck`; `EXP-2026-11-06-M4.14` |
| C-1029 | `tools/diff_years.py` reproduces all of the above field-level differences on the 2011/2014/2016 roots. | VERIFIED | H | `diff_years.py --json`; `EXP-2026-11-06-M4.14` |

## M6.11 — RP2040 SD CMD42 lock/unlock tool (C-1940–C-1949)

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-1940 | The unit's CMD42 password is 16 bytes: the 8 hex digits of the "SD PIN" service screen as 4 raw bytes, then the 12-character ASCII suffix of C-075; the 8 digits read as ASCII would make 20 bytes, above the SD `PWD_LEN` limit of 16. The byte order of the 4 unit bytes is UNKNOWN. | HYPOTHESIS | M | SD Physical Layer Simplified Spec §4.3.7 (`PWD_LEN` ≤ 16); C-075; same structure reached independently by C-1883 (EXP-2026-11-06-M2.13); EXP-2026-11-06-M6.11-pico-sdlock |
| C-1941 | `tools/sdlock-pico` sends only CMD0/8/9/13/16/42/55/ACMD41/58, can never emit a CMD42 block with ERASE or a reserved bit, and ends every set/lock/unlock/verify/clear in the expected lock state; the host test (572 checks) detects each of three seeded mutations. | VERIFIED (simulator) | H | `python3 tools/sdlock_pico_check.py`; EXP-2026-11-06-M6.11-pico-sdlock |
| C-1942 | A plain CMD42 unlock lasts one power session and a card with a password always powers up locked, so a locked card is rewritten on a PC by clear → write → set+lock, not by unlock. | FACT (spec) / PLANNED (test) | H | SD spec §4.3.7; `docs/hardware/sd-blocker-pico.md` §2, §7.3 |
| C-1943 | The firmware `.uf2` was not built in the Claude sandbox (external SDK build refused); `sd_proto.c` and `sd_card.c` compile for Cortex-M0+ with `-Werror`. | OBSERVED | H | EXP-2026-11-06-M6.11-pico-sdlock |
| C-1945 | LeafSDTools uses as CMD42 password the 16 bytes at NAND flash `0xA100` (PROD block 5 + `0x100`; block 2 on NEW_NAV), passed unchanged to the unit's SD driver via `DSK8:` IOCTL `0x80032014` (lock) / `0x80032020` (unlock); this confirms C-075's location and the 16-byte length of C-1940/C-1883. | VERIFIED (third-party source) | H | leafsdtools `422c653` `Flash.cpp` `ReadFullSDPin`, `ChangeSDLock`; EXP-2026-11-06-M6.11-2-leafsdtools |
| C-1946 | The 8 hex digits on the "SD PIN" screen are PIN bytes 0–3 in buffer order (each printed `%02X`), so the byte-order UNKNOWN of C-1940 is resolved: `hex:<digits as shown>`. | VERIFIED (third-party source) | H | leafsdtools `SDPinControl.cpp`; EXP-2026-11-06-M6.11-2-leafsdtools |
| C-1947 | The "SD PIN" lock/unlock screen is LeafSDTools' menu run on the unit, not a factory menu; C-1882's "the unit's own menu" holds only for a unit running LeafSDTools. | OBSERVED | H | leafsdtools `SDPinControl.cpp`; EXP-2026-11-06-M6.11-2-leafsdtools |
| C-1948 | Which CMD42 flags the SD driver sends for IOCTL `0x80032014` (LOCK only, or SET_PWD+LOCK on a card without a password) is UNKNOWN; it is in `SDHC.dll` (C-792), not in LeafSDTools. | UNKNOWN | — | EXP-2026-11-06-M6.11-2-leafsdtools |
| C-1944 | Whether real cards and the unit accept a card locked by the Pico tool is UNKNOWN until M6.9 (procedure §7.1) and M6.5. | UNKNOWN | — | `docs/hardware/sd-blocker-pico.md` §10 |

## Claim ledger (H1)

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-600 | `tools/claims_check.py` reports zero duplicate claim IDs in `docs/research/claims.md` (one ID per claim row) and exits 0 on the repaired ledger. | VERIFIED (tool) | H | `python3 tools/claims_check.py`; `python3 tools/selftest.py --only claims_check,tool:claims_check` |
| C-601 | Every claim proposed in `EXP-2026-11-05-38/41/42/43/44/46/47/48` is either registered under a new ID carrying `Was proposed as C-xxx in EXP-…` or dropped with a one-line reason recorded in the EXP. | VERIFIED | H | `docs/experiments/EXP-2026-11-05-38/41/42/43/44/46/47/48`; `tools/claims_check.py` |
| C-602 | `docs/experiments/README.md` lists the two duplicate-numbered records `EXP-2026-11-05-29` and `EXP-2026-11-05-35` with distinct labels; no experiment file was renamed. | VERIFIED | H | `docs/experiments/README.md` |
| C-603 | `docs/experiments/README.md` lists every record present in `docs/experiments/` exactly once (file set = link set = unique link set), including both `EXP-2026-11-05-29` and both `EXP-2026-11-05-35` records with slug-distinct link labels; no experiment file was renamed. | VERIFIED | H | EXP-2026-11-06-H1-ledger-repair; index-coverage script in the EXP |
| C-604 | Every finding proposed by a task record without a ledger row is now registered: the six early task records under the first ID of their own reserved block (C-720 M2.1, C-890 M4.1, C-900 M4.2, C-930 M4.5, C-1010 M4.13, C-1100 M5.8), M4.8's C-960, M6.4's C-1120–C-1129, M6.8's C-1130–C-1138 and H6's C-1720–C-1726; M6.3's C-1110–C-1119 (plan only, no claim text) and M6.8's C-1139 (self-referential process claim) are dropped with a one-line reason in the EXP. | VERIFIED (process) | H | EXP-2026-11-06-H1-ledger-repair |

## Findings registered by H1 (2026-11-06)

Rows registered from task records that named a free ID or stated a finding but
did not edit this ledger. Each row keeps the task's own reserved block.

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-720 | `Navi.exe` (build A) function `0x004e7b8c` is the only code that opens `\UserSD\VER_INFO\HDD_INFO.TXT`: pool slot `0x004e7d28` holds `0x001d51a8`, read at `0x004e7bec`; it is reached only through the function pointer at pool `0x004dd1e4` from `fn 0x004dd028`, with no direct `bsr` caller. Its six COREDLL ordinals stay unnamed from image A (no `coredll` module there); image B names them in C-1710. | VERIFIED (addresses) / OBSERVED (semantics) | H | EXP-2026-11-05-M2.1-hddinfo-fn; C-710–C-713, C-1710 |
| C-890 | `tools/rdstm_record.py` decodes a 16-byte little-endian `RDSTM001` row into seven raw fields and round-trips the ten real rows `0x1000`–`0x1099` byte-identically. Field meanings (`src`/`dst`, `pad2`) remain HYPOTHESIS; the record size is the scanner default and the framing drift at `0x10a0` is unexplained. | VERIFIED (tool) / HYPOTHESIS (semantics) | M | EXP-2026-11-05-M4.1-rdstm-record; `python3 tools/rdstm_record.py --selftest` |
| C-900 | M4.2 is a verified negative: `RDSTM001` link attributes cannot be correlated with OSM from the agent sandbox — `overpass-api.de` and `api.openstreetmap.org` return code `000`, and RDSTM rows have no decoded coordinates, so no row can be matched to a known road. The attribute table is blocked, not refuted. | VERIFIED (negative) | H | EXP-2026-11-05-M4.2-rdstm-link-attrs |
| C-930 | The object `EXP-2026-11-05-M4.5` analysed as `MMAIN001.DAT` is the FAT32 root directory, not the file: SHA-256 `fe24bbc8…` is the root directory's first 4,096 bytes (51 × 32-byte entries at `0x20`–`0x67f`, 39 deleted, 12 live). The "FAT root-directory log" interpretation and its `0x18c`/`0x1ac` conflict are retracted; the live `MMAIN001.DAT` (cluster `0x10002`, SHA-256 `240e7c97…`) carries the common header and the `0x180` descriptor (C-037, C-1720). | RETRACTED | — | Superseded by C-1721; EXP-2026-11-05-M4.5-mmain001, EXP-2026-11-06-H6-drstr-docs |
| C-960 | `tools/coord.py` converts WGS84 ↔ `BxxRyyR` cell ↔ packed `u16` pair ↔ tile-local `0..2047`, keeping the two longitude origins separate (`--origin 52742` for COORD001/POINT/ADDRE, `52736` for MAPAL001 stream keys); 15/15 checks cover the published cell boxes, mesh-grid agreement (63 cells), the two POI fixtures, half-open edges and the `0..2047` local bound. No real-image POI check yet. | VERIFIED (tool; published fixtures) | H | EXP-2026-11-06-M4.8-coord; `python3 tools/coord.py --selftest` |
| C-1010 | `LCTBL001.DAT` name text: 517 clean zlib streams → 11,481,060 bytes → 1,329,518 NUL-separated pieces, of which 297,295 are printable ISO-8859-2 strings (237,269 unique, 0 decode errors, longest 151 bytes); all Polish letters (ą ę ł ń ś ź ż, capitals, ó) occur. Unsupported characters must be rejected, not substituted; cross-stream collation is UNKNOWN. | VERIFIED (counts) / UNKNOWN (collation) | H | EXP-2026-11-05-M4.13-strings; `tools/name_strings.py` |
| C-1100 | `tools/tile_diff.py` matches clean zlib streams by offset and reports differing 4 KiB ranges: factory `B28R070R` vs itself = 7,937/7,937 streams, 0 bytes, `IDENTICAL`; vs a one-vertex `harness.py mutate` output = 7,935 same / 1 changed / 1 added / 1 removed, 148 bytes in two ranges. A recompressed stream that moves reads as remove+add (offset-matching limit). | VERIFIED (tool, image A) | H | EXP-2026-11-05-M5.8-tile-diff; `python3 tools/tile_diff.py …` |
| C-1120 | Recovery invariant: the original card is stored off-bench, hashed and never reinserted; a hash-verified untouched clone is kept aside; a no-card power baseline is recorded before the first test. | PLANNED (untested) | — | EXP-2026-11-06-M6.4-recovery |
| C-1121 | `NAVI VERSION NG` is statically only a string and a dispatcher (C-803–C-805); the SD `0x0020001f` vs unit `NAVI-1` comparison (C-076) is external hearsay, so recovery is a clone swap, not a version-byte edit. | PLANNED | — | EXP-2026-11-06-M6.4-recovery |
| C-1122 | `DIFFERENT MAP CODE` is statically only a string and a dispatcher; the deciding input (line 1 / `0x06000000` copy / NAND record) is UNKNOWN, so the map code is not patched before a known-good clone boots. | PLANNED | — | EXP-2026-11-06-M6.4-recovery |
| C-1123 | `MAP DATA BASE UNMATCH` is statically a string, a dispatcher and the `MapDBVer` range string; the range semantics are HYPOTHESIS, so the screen is recorded as a market/version mismatch and not "repaired". | PLANNED | — | EXP-2026-11-06-M6.4-recovery |
| C-1124 | `SD UNLOCK NG` is recovered by re-seating, then re-locking once; the only static identity gate is the SD security state (C-790, C-794, C-795), the CMD42 scheme is external (C-075), and a repeat on the known-good clone is a lock/reader fault, not map data. | PLANNED | — | EXP-2026-11-06-M6.4-recovery |
| C-1125 | The ordered recovery path is: run card out and hashed → known-good clone → re-lock → untouched original card → updater if offered; a failure at the original-card step is a unit/bench fault, not map data. | PLANNED | — | EXP-2026-11-06-M6.4-recovery |
| C-1126 | `MapUpdate.exe` is a recovery candidate only if the unit offers an update/import prompt: it validates, then formats partitions and copies files (C-774–C-776), so it may run only on a disposable clone with factory-shipped attestation files. | PLANNED | — | EXP-2026-11-06-M6.4-recovery |
| C-1127 | No failure signature, recovery step or updater prompt has been observed on a unit; every screen-to-cause mapping is a prediction from static strings and external hearsay. | UNTESTED | — | EXP-2026-11-06-M6.4-recovery |
| C-1128 | The plan restores the card only; unit-side state (PROD `A022`/`A0A0–A0A3`, `NAVI-1`, map record, SRAM/VSRAM flag, user settings) has no backup, so NAND/settings restore stays out of scope until a pre-run dump and test-pin access exist. | PLANNED | — | EXP-2026-11-06-M6.4-recovery |
| C-1129 | Do-not-attempt: the original card, the updater format path on the only good clone, NAND/flash/PROD edits, synthesised attestation files, CID/CSD/label spoofing, password bypass, a third power cycle, live-unit pin probing, the owner's only unit — and a successful recovery is not a format result. | PLANNED (do-not-attempt) | — | EXP-2026-11-06-M6.4-recovery |
| C-1130 | The bench power baseline is a current-limited 12 V supply (indicative €80–140, ESTIMATE) with ground connected first, a 2 A fuse in the +12 V lead and a 2 A current limit for the first boot; the unit is never powered from a car harness on the bench. | HYPOTHESIS (planning) | M | EXP-2026-11-06-M6.8-bench-kit; `dynamic-break-guide.md` "Bench kit"; `feedback-loop.md` Option F |
| C-1131 | `SECURE` bypass on the bench is `TEST_B1` to ground through a removable switch (indicative €5–15, ESTIMATE); whether grounding alone suffices or a VIN/CAN frame is also required is UNKNOWN, because C-082 is external research. | HYPOTHESIS | L | EXP-2026-11-06-M6.8-bench-kit; C-082; `us-eu-region.md` |
| C-1132 | A CAN transceiver/simulator with 120 Ω termination at both ends (indicative €35–130 as a USB adapter, or €30–60 as an SBC + MCP2515/TJA1050 HAT, ESTIMATE) is required to replay ignition/speed/VIN frames; the minimum frame set the unit needs to boot on the bench is UNKNOWN. | HYPOTHESIS (part) / UNKNOWN (frame set) | M | EXP-2026-11-06-M6.8-bench-kit; `feedback-loop.md` Option F; `full-system-emulation.md` §4 F4 |
| C-1133 | Bench card iteration uses an SD extension cable ≤ 30 cm with power off before insert/remove (indicative €10–20) plus a host SD reader/writer (indicative €8–15, ESTIMATE); this is the only way to swap cards without dismantling the unit. | HYPOTHESIS | M | EXP-2026-11-06-M6.8-bench-kit; M6.3 plan; `dynamic-break-guide.md` "Offline" |
| C-1134 | The kernel debug SCIF `0xffe46000` (C-534, writer `0x8804cfa4`, pointer `0x8804ce78`) has no identified board connector or pinout in the repo, so serial access is unconfirmed and a 3.3 V USB-UART (indicative €8–20, ESTIMATE) is only useful after a TX pin is found. | VERIFIED (negative, repo) / UNKNOWN (pins) | H | EXP-2026-11-06-M6.8-bench-kit; repo-wide grep; C-534; TODO M8.A6 |
| C-1135 | A logic analyser (8 ch, ≥ 24 MHz, indicative €15–40, ESTIMATE) is the instrument that can locate the debug TX among the eight SCIF channels `0xffe40000`–`0xffe48000` and check SD CMD/DAT and CAN framing; a 2-ch 100 MHz scope (indicative €300–450) is an optional addition for signal integrity and differential CAN. | HYPOTHESIS | M | EXP-2026-11-06-M6.8-bench-kit; C-532; `dynamic-break-guide.md` access plan step 1 |
| C-1136 | The minimum card set is three spare SD cards (work, no-op control, rollback; indicative €10–15 each, ESTIMATE) plus the hashed original kept off the bench and never written or inserted in the bench unit. | HYPOTHESIS | H | EXP-2026-11-06-M6.8-bench-kit; M6.3 plan; `us-eu-region.md` "Safest experiment order" |
| C-1137 | Error screens (`NAVI VERSION NG`, `DIFFERENT MAP CODE`, `SD UNLOCK NG`, `MAP DATA BASE UNMATCH`) appear before the map UI, so a camera or USB capture (indicative €0–60) and a scripted power switch/relay (indicative €15–35, ESTIMATE) belong to the minimum loop; they give a binary accept/reject without a debugger. | OBSERVED | M | EXP-2026-11-06-M6.8-bench-kit; C-790, C-803; `us-eu-region.md` |
| C-1138 | The dynamic access order is UART/debug output → break on `MAL_DataVol_getOffset` `0x03498d48` → fd methods `0xc42520`/`0xc426a4`/`0xc438a4` → card matrix; steps 2–3 need a debug path (QEMU `ze0` gdbstub at the VA, or an undocumented BDM/JTAG header), so only step 4 is runnable with today's knowledge. | HYPOTHESIS | M | EXP-2026-11-06-M6.8-bench-kit; `dynamic-break-guide.md`; `full-system-emulation.md` §4–5 |
| C-1720 | `MMAIN001.DAT` on the EU 2011 card is a 4,096-byte file at first cluster `0x10002` (SHA-256 `240e7c97…`) that starts with the common 512-byte header (UTF-16BE `CLARION` … `V05.00.00`) and carries the `0x180` descriptor block. | VERIFIED | H | EXP-2026-11-06-H6-drstr-docs; ranged read of the published image; C-010/C-011 re-verified |
| C-1721 | The object `EXP-2026-11-05-M4.5` analysed as `MMAIN001.DAT` (SHA-256 `fe24bbc8…`) is the first 4,096 bytes of the FAT32 root directory: it starts with the volume-label entry `QSD-309-101` and holds 51 32-byte entries at `0x20`–`0x67f`. The `0x18c`/`0x1ac` "inside FAT records (`ER_INFO`)" observation applies to the root directory, not to the file. | VERIFIED (retraction) | H | EXP-2026-11-06-H6-drstr-docs; supersedes the FAT-log interpretation of EXP-2026-11-05-M4.5 (C-930); C-037 unaffected |
| C-1722 | The live `MMAIN001.DAT` root entry is at root offset `0x4e0` with first cluster `0x10002` (high word `0x0001` at `+0x14`, low word `0x0002` at `+0x1a`), size 4,096; FAT32 cluster 2 is the root directory, so reading only the low cluster word returns the directory. | VERIFIED | H | EXP-2026-11-06-H6-drstr-docs; control for C-1721 |
| C-1723 | `MMAIN001.DAT`'s `0x1ac` container holds three tables with ids `01`/`02`/`04` and 6/4/1 entries = 11 `(level, kind, count)` tuples, terminated at `0x1e0`; the `0x18c` list is `05 04 02 07 0a 06 08 14`. | OBSERVED (VERIFIED structure) | H | EXP-2026-11-06-H6-drstr-docs; re-verifies C-548/C-550/C-551; counts per C-164 |
| C-1724 | `MMAIN001.DAT` `0x184` (and `0x5d0`) hold big-endian `i16` arc-minute bounds: 4800, 1280, −1200, 4080, i.e. the EU database extent; semantics OBSERVED, not tied to firmware. | OBSERVED | M | EXP-2026-11-06-H6-drstr-docs; `tools_ze0/make_mmain.py` packs the same fields |
| C-1725 | `tools/ze0-viewer/tools_ze0/` is the authoritative copy imported by `harness.py` (46 modules, pin `07fbf78d…` + `ze0-tools.patch`, 6 files/+296/−40). `setup.sh` cannot regenerate it as written: its symlink step is guarded by the existing real directory and its `git apply -p1` targets the patch's `tools_ze0/…` new-side paths inside the clone. | VERIFIED (tool/process) | H | EXP-2026-11-06-H6-drstr-docs; `docs/format/ze0-tools.md` |
| C-1726 | The FAT root directory has 12 live entries; the DRSTR root node has 11 (the same list without `DRSTR001.DAT`, C-163); the third `DRSTR` string in the M3.4 raw scan (`0x064e5a60`) is that directory entry. | VERIFIED | H | EXP-2026-11-06-H6-drstr-docs; EXP-2026-11-06-M3.4-drstr-parser |
| C-1780 | `tools/ce_strfind.py` scans every module of builds A/B/C and finds the positive control `HDD_INFO.TXT` with the same command (A: `Navi.exe`; B: `commondll.dll`, `AppLaunch.dll`, `MapUpdate.exe`; C: `commondll.dll`, `AppLaunch.dll`). Coverage: 282/173/163 uncompressed sections; the 245/133/113 `IMAGE_SCN_COMPRESSED` sections were all attempted and every one is `UNSUPPORTED` by `tools/cecompress.py`, so the valid negative scope is the uncompressed sections (code is never compressed, C-530). | VERIFIED | H | EXP-2026-11-06-M3.8-mmain-read; `python3 tools/ce_strfind.py <img> MMAIN --control HDD_INFO.TXT --encoding all` and `--image-start 0x3e00200` / `0x5200200` |
| C-1781 | `MMAIN001.DAT` has exactly one ASCII literal in build A: `Navi.exe` VA `0x0017adac` (RVA `0x0016adac`, file `0x00df8fac`, section VA `0x00011000`). There is no UTF-16 occurrence in A and no occurrence in any B or C module. A raw scan of the first 128 MiB finds only that string, its byte-identical A copy at file `0x02bf8fac`, and the FAT root-entry text at `0x064e58e0` (not code). | VERIFIED | H | EXP-2026-11-06-M3.8-mmain-read; `tools/ce_strfind.py`, raw `bytes.find` |
| C-1782 | The `MMAIN001.DAT` literal is loaded exactly once: `0x0041a47a` (r5) from pool `0x0041a514`, inside function `0x0041a438`; `sh4xref --to 0x0017adac` reports no other load. | VERIFIED | H | EXP-2026-11-06-M3.8-mmain-read; `python3 tools/sh4xref.py <img> Navi.exe --image-start 0x200200 --to 0x0017adac` |
| C-1783 | Function `0x0041a438` builds `\SystemSD\MMAIN001.DAT`: `memset` (`0x003d13c4`) on a 260-byte stack buffer, `wcstombs` (`0x003d14cc`) of the UTF-16 `\SystemSD` at `0x00049fd4`, then `strncat` (`0x0053a384`) of `\` (`0x0017a9ec`) and `MMAIN001.DAT`; it rejects a converted length with `len + 13 >= 260`, then opens the path with `sub_0041b780(path, 1)` (`rb`) and treats a 0 return as failure. | VERIFIED | H | EXP-2026-11-06-M3.8-mmain-read; `sh4xref --calls 0x0041a438`; rizin SH-4 listing |
| C-1784 | The reader gets the fd from `sub_0041b780`, reads exactly `0x1000` bytes with `sub_0041b954(fd, dest, 0x1000, 1)`, requires the return to equal `0x1000`, closes with `sub_0041b81c(fd, 1)` and returns 0; `dest` is the caller's argument or the fixed buffer `0x00e23cc0` when it is 0. No seek or per-field read precedes it. | VERIFIED | H | EXP-2026-11-06-M3.8-mmain-read; rizin listing of `0x0041a438`/`0x0041b954` |
| C-1785 | The `MMAIN001.DAT` read path checks only the path-buffer bound, the open status and the total length `0x1000`; it compares no label, version, record count, cluster or checksum. `QSD-309-101` and `DATA VERSION` have zero literal occurrences in build A modules (same scan, `HDD_INFO.TXT` control found), so no code can compare the header text. | VERIFIED (negative, scope: uncompressed sections of A/B/C) | H | EXP-2026-11-06-M3.8-mmain-read; `tools/ce_strfind.py <img> QSD-309-101 --control HDD_INFO.TXT --encoding all` |
| C-1786 | The MMAIN reader is part of the media-mount state machine: handler table `0x0017ab38` (indexed `status*5 + mode` by `0x00419c38`, `status = *(u32*)0x009cfce0`) has `0x00419ca0` at entries 0/1 (status 0); `0x00419ca0` opens `CMP.LST` first (`sub_0041ba90`), then calls `0x0041a438(0)`, logs the result through `0x00419a9c` at `0x00e24d00`, and sets `0x009cfce0 = 1` on success; a `CMP.LST` failure sets 3, an MMAIN failure schedules a retry and leaves 0. | VERIFIED | H | EXP-2026-11-06-M3.8-mmain-read; `sh4xref --to 0x00419ca0`, `--to 0x0017ab38`; rizin listing |
| C-1787 | After mount, `sub_0041a304` byte-swaps every u16 of the 4096-byte buffer in place (`mov #8; shll8` = 0x800 iterations) and calls OBJDLL `OBJ_DriveInfo_writeDataVol` (export #244, VA `0x034b984c`), which increments `*(obj+4)` and `memcpy(obj+8, buf, 0x1000)` without parsing it. The on-card MMAIN is therefore big-endian; the firmware converts it to little-endian. | VERIFIED | H | EXP-2026-11-06-M3.8-mmain-read; `cerom.py exports OBJDLL.dll`; rizin listing of `0x0041a304`, `0x034b984c` |
| C-1788 | The `0x1ac` `(level, kind, count)` count field is u16 **big-endian** on the card (`0001 0001 0001 002d 008a 06b5` = 1, 1, 1, 45, 138, 1717 in the EU 2011 file), not little-endian. `tools/cardcheck.py` (`>BBH`) and `tools_ze0/make_mmain.py` already use big-endian. Supersedes the endianness clause of C-550. | VERIFIED | H | EXP-2026-11-06-M3.8-mmain-read; root `MMAIN001.DAT` `0x1ac`–`0x1c7`; `cardcheck.py` parser |
| C-1789 | The only other reader of the MMAIN buffer `0x00e23cc0` is the debug dump `0x0041a52c` (call site `0x00417db0`): it walks 128 32-byte records over the whole 4096 bytes (printing the first 16 bytes of each), then `VOL ADR` = buffer `+0x800` and `MGR ADR` = buffer. Consequence for M5.6: a verbatim copy of the factory file satisfies the mount path; regenerating the `0x1ac` totals is an offline `cardcheck` rule (and should follow a tile-set change), not a firmware check. Hardware behaviour of downstream `OBJ_DriveInfo` consumers is untested. | OBSERVED (decision; code references VERIFIED, hardware untested) | M | EXP-2026-11-06-M3.8-mmain-read; `sh4xref --to 0x00e23cc0`; rizin listing of `0x0041a52c` |


| C-1030 | `tools/osm_ingest.py` reads `.osm` XML and `.osm.pbf` (stdlib protobuf wire decoder) and writes IMF v1; both encodings of the synthetic fixture produce byte-identical output (12 nodes / 5 ways / 1 restriction) that passes `imf_check` with 0 errors. The PBF string table stores index 0; history files and out-of-order blobs are refused. | VERIFIED (tool, synthetic) | H | EXP-2026-11-06-M5.1-osm-ingest; `python3 tools/osm_ingest.py --selftest` |
| C-1660 | `tools/l3_harness/engine.py` exposes one engine API (`map/read_mem/write_mem/set_regs/get_regs/call/on_exec/run_until`) over a pure-Python SH-4 reference interpreter, a lazy Ghidra P-code adapter and a QEMU gdbstub adapter; the synthetic add/loop/jsr-to-stub snippet runs identically on PySh4 (26 cycles, `r0=0x5a5a`) and on any available back end, and an absent back end raises `MISSING_GHIDRA`/`MISSING_QEMU` and is reported SKIP, never pass. | VERIFIED (tool, synthetic) | M | EXP-2026-11-06-M9.4-engine; `python3 tools/l3_harness/engine.py --selftest` |
| C-1690 | `tools/l3_harness/corpus.py` builds a 108-entry vendor-byte-free L3 corpus (13 cmp/ind incl. all 8 `ind_mutate` variants, 3 DRSTR, 2 tile, 90 HDD_INFO incl. the 89 variants) with a `manifest.py`-valid `manifest.json`, a PASS `check`, a skipped `factory` slot when absent, and per-case expected reader verdicts. | VERIFIED (tool, synthetic) | H | EXP-2026-11-06-M9.7-corpus; `python3 tools/l3_harness/corpus.py --selftest` |
| C-1730 | `tools/realcheck.py` is a single-command real-image regression runner importing `cerom`, `sh4xref` and `cecompress`: eight pinned checks, PASS/FAIL per check, exit 0 all-PASS, 1 any-FAIL, 2 missing image, 3 `--update` without `--write`; pins are refuse-by-default and the synthetic CE ROM self-test covers PASS/FAIL/SKIP. | VERIFIED (tool, synthetic) | H | EXP-2026-11-06-H7-realcheck; `python3 tools/realcheck.py --selftest` |

## How to verify

Every active claim names an `EXP-...` record; this table gives the exact
repo command where one exists. `<img>` is a raw SD image (vendor data, kept
outside the repo), `<root>` an extracted card root, `<tile>` a `BxxRyyR.DAT`.

| Active claims | Command | Expected |
| --- | --- | --- |
| C-543–C-547, C-553, C-555, C-557, C-560–C-563 | `python3 tools/selftest.py` (or `--only <tool>`) | every `tool:*` suite `PASS`; `selftest: OK` |
| C-558–C-559 | `python3 tools/l3_harness/selftest.py`; `python3 tools/l3_harness/runner.py run …` | `selftest: OK (19 checks)`; `MISSING_GHIDRA` exit 3 until Ghidra is installed |
| C-546–C-547 | `python3 tools/section4.py verify SECTION4.bin` | parse→preserve byte-identical; `build` exit 3 with the unknown-field list |
| C-070–C-084, C-120–C-126, C-509–C-514 | no local command: external teardown/upstream sources only | see `sources.md`/`feedback-loop.md`; not reproduced here |
| C-110–C-116, C-132–C-142, C-150–C-156, C-210–C-216 | helpers `coord.py`/`poipoint.py`/`decode.py` are **not in `tools/`**; use `l2check.py` as the regression gate | original method in the named EXP |

## How to use this ledger

- When you verify or refute a claim, update its row and add the command/output
  to the evidence column.
- When you add a new claim, give it the next free ID in its section.
- Keep `docs/format/*.md` consistent with this file; the ledger wins if they
  disagree.
- Do not promote `OBSERVED`/`HYPOTHESIS` to `VERIFIED` without a reproducible
  check that another agent can run.

## SD unlock PIN (M2.13)

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-1880 | The 12-character tail of the unit's displayed SD unlock PIN is a hardcoded NUL-terminated ASCII literal in `PRGUpdate.exe` (image B, VA `0x00012498`) and `TestMode.exe` (image C, VA `0x000157f8`), among `SecurityCheck`/`ProductTestData` strings; it appears in both B copies. SHA-256 of the 12 bytes `249e0da5d349ebe359d7465bbbae29658482138d6b4bd0bd146475d3824f939f`. Plaintext not committed (manufacturer data). | VERIFIED | H | EXP-2026-11-06-M2.13; `IMG256` `92aa525d…`; `tools/cerom.py` |
| C-1881 | The 8-digit prefix of the displayed PIN is not a literal anywhere in `IMG256` (no ASCII or UTF-16LE match), so the full PIN is assembled at runtime from a runtime prefix and the C-1880 tail. | VERIFIED (negative) | H | EXP-2026-11-06-M2.13 |
| C-1882 | The unit unlocked the card with this PIN on its own `SD PIN` service screen (`Unlocking. OK`), confirming the value works on real hardware; the unit exposes a built-in SD LOCK/UNLOCK menu. | OBSERVED | H | owner service-screen photo 2026-11-06 (not committed) |
| C-1883 | The displayed PIN is 20 characters but a CMD42 SD-lock password is at most 16 bytes, so the displayed string is not a raw CMD42 password; the byte form CMD42 uses is UNKNOWN (M2.13b). | VERIFIED (spec) / UNKNOWN (form) | M | EXP-2026-11-06-M2.13; SD physical-layer spec |
| C-1884 | The `SDHC_SecurityUnLock` xref to the C-1880 literal is not yet traced because `SDHC.dll`'s code section is `IMAGE_SCN_COMPRESSED` (M1.2); the tie is behavioural (C-1882), not static. | OBSERVED | M | EXP-2026-11-06-M2.13; `cerom.py sections SDHC.dll` |
