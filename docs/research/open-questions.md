# Open questions (unknowns register)

> **Derived, not authored.** One row per unresolved question, collected from
> `claims.md` rows whose status is `HYPOTHESIS`/`UNKNOWN` or whose text records
> an open point, plus open `TODO.md` items that name an unknown. Answered
> questions move to [Answered](#answered) with their claim ID; nothing here is
> `VERIFIED` without one. Roadmap gates and sequencing live in
> [`roadmap.md`](roadmap.md) — this page only records *what we do not know* and
> the evidence that would close it.
>
> **Mode.** `now` = workable offline today; `deferred` = needs hardware or a
> data set we do not have. `Blocker` is `none`, `Ghidra`, `legal`,
> `hardware` or `vendor data`; hardware work carries
> `[deferred: no hardware 2026-11-05]` in `TODO.md`.

## Register

| ID | Question | Track | Status | Mode | Blocker | Evidence that closes it | Links |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OQ-01 | Where are the `.cmp`/`.ind`, `DRSTR001`, tile and `HDD_INFO` readers in the extracted CE ROM modules? | firmware | UNKNOWN | now | Ghidra | A TOC-extracted module loads in Ghidra/rizin and shows the open/read path reproducing a corpus result. | C-183, C-208, C-225, C-246, C-326, C-386, C-396, C-406, C-426, C-436, C-437; M1.8/M2/M3/M9; [firmware](../format/firmware.md) |
| OQ-02 | Is `chunk_size` compared or used as a buffer size, and does the reader seek via `.ind` offsets or scan for `78 9c`? | firmware | HYPOTHESIS | now | Ghidra | L3 harness over the 8 `.ind` variants, then SD capture. | C-231, C-395, C-405, C-408, C-426, C-377; M9; [cmp-ind](../format/cmp-ind.md) |
| OQ-03 | What is the NaviStateCC runtime vtable/slot layout, and which constructor installs it? | firmware | UNKNOWN | now | Ghidra | Extract `NaviStateCC.dll` via the TOC and follow `DllGetClassObject` → constructor → vtable store. | C-402, C-415, C-420–C-422, C-424, C-432–C-434, C-436; M1.8/M2/M3; [firmware](../format/firmware.md) |
| OQ-04 | Which `HDD_INFO` line maps to which compared field, and is the `Sys` side the built-in `0x06000000` copy? | firmware | HYPOTHESIS | now | Ghidra | For the two `AppLaunch` launcher checks the Sys side is a kernel target-info record (`KernelIoControl 0x0101302C`), not the `0x06000000` copy (C-786); the field mapping is still open. | C-072, C-077, C-204, C-293, C-304, C-305, C-316, C-325, C-355, C-365, C-786; M2.7/M9; [validation](../format/validation.md) |
| OQ-05 | Is there a runtime map-content or activation check beyond zlib Adler-32? | firmware | UNKNOWN | now | Ghidra | Decompile the launcher/validity path and exhaust every rejection branch. | C-009, C-038, C-147, C-162, C-203, C-206; M1.8/M2/M3, Gate 5; [validation](../format/validation.md) |
| OQ-06 | Is `SUM4` the C-160 word sum for every payload, or still open as C-085 says? | firmware | UNKNOWN | now | none | Recompute for builds B/C and a mutated payload; reconcile the two rows. | C-085, C-160, C-161; M1/M4; [validation](../format/validation.md) |
| OQ-07 | What are `NKOK`, the `0x200200` 32-bit table, the declared-vs-actual length, and `HCXCmp`'s role? | firmware | UNKNOWN | now | none | Field-by-field header decode; check whether compressed `o32` sections use `HCXCmp` or `CECompress`. | C-060, C-065, C-087, C-088; M1/M4; [firmware](../format/firmware.md) |
| OQ-08 | Which boot/copy slot is selected, and does `ulCopyEntries` explain the non-injective VA map (`0x0367b180`)? | firmware | UNKNOWN | now | Ghidra | Parse `ulCopyEntries`/`ulCopyOffset` and align `o32_rom` records with the TOC. | C-089, C-093, C-180, C-234, C-262, C-292, C-373, C-384, C-423; M1.8/M2/M3; [cerom](../format/cerom.md) |
| OQ-09 | Are CE ROM file entries in builds B/C 0x18 or 0x20 bytes, and do their names resolve? | firmware | HYPOTHESIS | now | none | Resolve all 11/10 names and compare with `FILESentry`. | C-094; M1.8/M2/M3; [cerom](../format/cerom.md) |
| OQ-10 | What is the market/region logic (`PROD 0xA022`, market-specific navi/audio builds, file-level locking)? | firmware | PARTLY ANSWERED | now | US image | Target ID → `CApi_GetModelArea` → `AppLaunch` launch mask is verified (C-780–C-787); the `0xA022` address, US build and per-entry masks remain open. | C-780–C-789, C-078, C-079, C-084, C-165; M2.7; [us-eu-region](us-eu-region.md) |
| OQ-11 | What is the grammar of the remaining real tile payloads (road shapes are decoded), and do polygon/area records exist? | data | UNKNOWN | now | none | A dense tile decodes with no opaque non-default records. | C-049, C-141, C-142, C-252, C-257, C-283; TODO Tiles; [map-tiles](../format/map-tiles.md) |
| OQ-12 | What is the road style and rendering model (class, one-way, speed, layers 4/6, LOD/zoom, label priority, colours, widths)? | data | HYPOTHESIS | now | none | Validate `0x201e`/`0x001e` against known streets/signs and reproduce factory rendering. | C-257, C-282, C-108; TODO Tiles; [map-tiles](../format/map-tiles.md) |
| OQ-13 | What are the section-4 binary fields between country and names, and can section 4 be encoded? | data | UNKNOWN | now | none | A field map plus encoder, or a documented preserved-verbatim decision. | C-126, C-257, C-280, C-286; TODO Tiles; [map-tiles](../format/map-tiles.md) |
| OQ-14 | What is the routing-graph encoding (`RDSTM001` `0x1000` framing/tuples, `FRWAY` mesh IDs, `INTER` `n`), and is routing built from it, the tiles, or both? | data | UNKNOWN | now | none | The graph tuples and attributes decode, and one route is cross-checked against tile geometry. | C-050, C-100–C-108, C-135; TODO Data; [rdstm](../format/rdstm.md) |
| OQ-15 | How do `LCTBL` name indices join to `RDSTM` road records and tile mesh codes? | data | HYPOTHESIS | now | none | A stable index→record→mesh join reproduced over several regions. | C-100–C-105, C-285; TODO Data; [rdstm](../format/rdstm.md) |
| OQ-16 | What is `LEV3456R.DAT` for? | data | HYPOTHESIS | now | none | A firmware consumer, or a proven fallback use of the coarse levels. | C-040, C-046, C-255; TODO Tiles; [map-tiles](../format/map-tiles.md) |
| OQ-17 | Why do `COORD001` (52742) and tile streams (52736) use different longitude origins? | data | UNKNOWN | now | none | One formula explains both, or evidence of two coordinate spaces. | C-048, C-053, C-111; TODO Tiles; [coord-zcode-icode](../format/coord-zcode-icode.md) |
| OQ-18 | What do `COORD001.level`, the `ZCODE` offset base and the `ICODE001` trie roots mean? | data | UNKNOWN | now | none | Field decode with an end-to-end lookup example. | C-110–C-114; TODO Tiles; [coord-zcode-icode](../format/coord-zcode-icode.md) |
| OQ-19 | Which parts of `ADDRE` remain undecoded (6/12-byte index cells, `c0`/`c8`, `0x54`/`0x58`, `40 XX YY`, trailer)? | data | UNKNOWN | now | none | Full 33-shard record decode and round-trip. | C-026, C-139, C-153, C-154, C-212; TODO Data; [refer](../format/refer.md) |
| OQ-20 | How does the POI `icon code` map to `BICON001`, and where is the bit-packed field block anchored? | data | UNKNOWN | now | none | An icon mapping table and a schema that fits the available bits. | C-132, C-213, C-214, C-215; TODO Data; [assets](../format/assets.md), [refer](../format/refer.md) |
| OQ-21 | What is the second 1000-id block per POI page, and how does it relate to `f11`/`f7`/`f8`? | data | HYPOTHESIS | now | none | Multi-page shard decode with one consistent id rule. | C-133, C-151, C-210, C-211; TODO Data; [refer](../format/refer.md) |
| OQ-22 | Which bits in `REFER002` are the explicit `xy-coordinates`, and how do EV POIs join? | data | HYPOTHESIS | now | none | Bit-level schema plus a join against `REFER001`/`COORD001`. | C-138, C-152, C-156, C-216; TODO Data; [refer](../format/refer.md) |
| OQ-23 | What do the `0x180` header descriptor and the `0x5d6` boundary describe? | data | UNKNOWN | now | none | Field-by-field map of both blocks across file types. | C-011, C-012, C-039; TODO Data; [file-header](../format/file-header.md) |
| OQ-24 | What are `CMP.LST`'s update semantics, given it has zero pointer references? | data | UNKNOWN | now | Ghidra | A firmware caller, or a documented updater-tool-only role. | C-035, C-037, C-200, C-330, C-331; TODO Data; [cmp-ind](../format/cmp-ind.md) |
| OQ-25 | What is `DRSTR001.DAT`'s `next_index` for? | data | UNKNOWN | now | none | A firmware consumer, or a documented redundancy. | C-031, C-034; TODO Data; [drstr](../format/drstr.md) |
| OQ-26 | What is the post-partition tail's purpose? | data | UNKNOWN | now | none | Verify C-166's TFAT16 skin volume and show whether the unit needs it. | C-007, C-008, C-166; TODO Data; [sd-card-layout](../format/sd-card-layout.md) |
| OQ-27 | Can `MMAIN001`, the 512/`0x5d6` headers, `REFER002` uncompressed files and `ADDRE` index areas round-trip (Gate 1)? | data | UNKNOWN | now | none | The Gate 1 row in `l2check` is green. | C-011, C-037, C-039, C-194; TODO Writers; [file-header](../format/file-header.md) |
| OQ-28 | Can `B30R048R` at `0x807`/`0x808` be written layout-aware, or is the preserved-layout fallback permanent? | data | RESOLVED | now | none | Layout-aware writer is byte-identical for 2011/2014/2016 (C-943); fallback no longer needed for this tile. | C-940–C-944; EXP-2026-11-05-M4.6-b30r048r-diff; [map-tiles](../format/map-tiles.md) |
| OQ-29 | Which cross-year diffs matter (`HDD_INFO`/headers/`MMAIN`/`DRSTR`/tiles for activation fields, `REFER002`/`ICODE001` schemas)? | data | UNKNOWN | now | none | A diff that separates fields changing with map set/version from stable ones. | C-121, C-122, C-126; TODO Cross-year; [image-versions](image-versions.md) |
| OQ-30 | What are the string limits and collation rules (max length, Polish diacritics, sorting, transliteration)? | data | UNKNOWN | now | none | Encoder/decoder behave at the limit; the render check follows OQ-39. | —; TODO Tiles/OSM; [refer](../format/refer.md) |
| OQ-31 | What does `TFTBL001` do, and is speech-language packaging in scope? | data | UNKNOWN | now | none | Decode `TFTBL001` from the 2014/2016 images and record the scope decision. | C-071, C-122; TODO Tiles; [image-versions](image-versions.md) |
| OQ-32 | What is the `BASSW7C`/`OPNG` image-tile grammar? | data | UNKNOWN | now | none | Container decoded; not required for map correctness. | —; TODO Tiles; [assets](../format/assets.md) |
| OQ-33 | How should OSM tags map onto the unit's road classes and attributes? | OSM | UNKNOWN | now | none | Depends on OQ-12; mapping table validated against factory samples. | C-101, C-108, C-282; TODO OSM; [osm-pipeline](osm-pipeline.md) |
| OQ-34 | Can OSM addresses/POIs be imported without breaking search, and what join strategy is required? | OSM | UNKNOWN | now | none | Depends on OQ-19/OQ-20; a search-visible imported POI and address. | C-139, C-212, C-214; TODO OSM; [build-profiles](build-profiles.md) |
| OQ-35 | Where does ODbL attribution live on a distributed card/image? | legal | UNKNOWN | now | legal | A written distribution rule the FAT image can carry. | —; TODO OSM; [build-profiles](build-profiles.md) |
| OQ-36 | Is the US 2011 card the same schema/tile layout, and are newer files such as `TFTBL001` required? | hardware | HYPOTHESIS | deferred | vendor data | The owner's US dump hashed and diffed against the EU image. | C-070, C-071, C-122; TODO Hardware; [us-eu-region](us-eu-region.md) |
| OQ-37 | Is the US 2011 card tiled or monolithic? | hardware | UNKNOWN | deferred | vendor data | A directory listing of the US dump. | C-070; TODO Hardware; [us-eu-region](us-eu-region.md) |
| OQ-38 | What are the unit's market/SD-lock state and the exact `NAVI VERSION NG`/`DIFFERENT MAP CODE` inputs? | hardware | HYPOTHESIS | deferred | hardware | Read PROD/`NAVI-1`/map record/SD lock and trigger each screen. | C-075, C-076, C-078, C-165; TODO Hardware; [validation](../format/validation.md) |
| OQ-39 | Does the unit accept a modified spare card (no-op, POI rename, `.ind`/`HDD_INFO` variants, FAT-only clone, free-space/label changes), and can it roll back? | hardware | UNKNOWN | deferred | hardware | Card matrix with recorded acceptance, free-space cases and recovery. | C-146, C-148, C-149, C-297, C-366, C-377; TODO Hardware; [validation](../format/validation.md) |
| OQ-40 | Can the unit run on a bench, and what is the `SECURE`/CAN/VIN risk? | hardware | UNKNOWN | deferred | hardware | Bench harness plus a documented recovery path. | C-082; TODO Hardware; [us-eu-region](us-eu-region.md) |
| OQ-41 | Where is the reader at runtime, and what is the actual SD read order? | hardware | UNKNOWN | deferred | hardware | Break on MAL `getOffset`/fd methods; SD bus capture. | C-407, C-408, C-427, C-435; TODO Hardware; [dynamic-break-guide](dynamic-break-guide.md) |
| OQ-42 | Is a reproducible US→EU conversion possible, including audio? | hardware | UNKNOWN | deferred | hardware | A controlled conversion with screen and audio evidence. | C-080–C-083; TODO Hardware; [us-eu-region](us-eu-region.md) |

## Answered

Moved here instead of deleted; each replaces an open question from the
previous revision (or a sub-question of one) and is settled by a `VERIFIED`
claim.

| Former question | Answered by | What settled it |
| --- | --- | --- |
| What does `MMAIN001.DAT` describe? | C-037 | Format/version descriptor, not a manifest. |
| How do `BxxRyyR` names map to lat/lon? | C-045 | Hex B/R: `lat_min = int(B,16)*2/3`, `lon_max = 108-int(R,16)`, 5.333° × 8° (C-107 duplicates this, stale). |
| What is the tile descriptor at `0x1ac`/`0x2ac`, and how are streams addressed? | C-047, C-051, C-052, C-296 | Bbox table, table index and back-to-back streams; `0x1ac` is not a level table. |
| Is the numeric REFER suffix a region or a shard? | C-131, C-143 | 33 country shards; `REFER002` is a separate EV layer. |
| What is `DRSTR001.DAT`'s leading `0x2f`? | C-030, C-033 | ASCII `/` of the root name; no header, root at `0x0000`. |
| How is the firmware packed? | C-060, C-063, C-064, C-088–C-093 | Uncompressed SH-4 WinCE payload with a standard CE ROM TOC. |
| Does `HCXCmp` compress map payloads? | C-065 | No; map payloads are plain zlib. |
| Can `.cmp` files and tiles round-trip byte-identically? | C-190, C-191, C-251 | Preserved streams; zlib 1.3.1 settings; all five target tiles. |
| Are there per-file or per-card checksums? | C-038, C-147, C-162 | None; only zlib Adler-32 per chunk. `SUM4`/updater sums are reproduced (C-160/C-161). |
| What are the repeated pre-partition firmware copies? | C-062, C-089, C-093 | Five segments, three builds (A/A, B/B, C); slot selection stays in OQ-08. |
| What are the `RDSTM001`/`LCTBL001` file roles? | C-100–C-105, C-285 | LCTBL is the name database; RDSTM is binary and has no zlib. |
| How are coordinates encoded across files? | C-111, C-150, C-155 | One formula covers `COORD001`, `ADDRE` and `POINT` ids. |
