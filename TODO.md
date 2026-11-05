# TODO

Actionable backlog. For "what we do not know yet" see
[`docs/research/open-questions.md`](docs/research/open-questions.md); for the
evidence status of each claim see
[`docs/research/claims.md`](docs/research/claims.md).

## Start here (2026-11-05)

**Current state**

- **Data side is healthy and parked.** L1/L2 pass on the 2011/2014/2016 ZE0
  material (`tools/cardcheck.py`, `tools/l2check.py`, `tools/verify.py`).
  Containers, `DRSTR`, the tile grid and all five target tiles round-trip
  byte-identically. Writers exist: `tools/cmpind_writer.py`,
  `tools/drstr_ze0.py`, `tools/ze0-viewer/`.
- **Firmware has a new foothold.** `tools/ce_rom_parse.py` recovers the
  embedded CE ROM TOC: build A has 149 modules / 1 file, SH-4, physical range
  `0x8cae1000`–`0x8e233c88`, and resolves `Navi.exe`, `NaviStateCC.dll`,
  `OBJDLL.dll`, `STDDLL.dll` (C-088/C-089, EXP-2026-11-05-33/34).
- **Global-VA/delta guessing is closed.** The old "no XIP/section table"
  negative (C-380/C-381) is retracted; C-088/C-089 supersede it. The CE ROM
  TOC replaces literal/prologue fitting — do not restart the old search.
- **The readers are still not located.** The `.ind`/`.cmp` reader, `DRSTR`
  parser, tile reader and `HDD_INFO` parser are the main blocker.
- **No hardware access (2026-11-05).** Dynamic breaks, SD bus capture and all
  card matrices are tagged `[deferred: no hardware 2026-11-05]`.

**One next action — Step 2 (firmware track below).** Turn the recovered TOC
into Ghidra-ready modules (`tools/cerom.py`, PE or a Ghidra memory map), then
locate the readers in Step 3. Nothing else is higher value right now.

**Gate map.** 0a closed by the CE ROM TOC; 0b still open (section 4, road
attributes); Gate 1 open (`MMAIN`/headers/`REFER002`/`ADDRE` round-trip);
Gates 2 and 3 pass for the five targets; Gates 5/6 deferred; Gate 7 after
0–6. Authoritative detail:
[`docs/research/roadmap.md`](docs/research/roadmap.md).

**Non-goals**

- No new global-VA or module-base guessing from literals, deltas or prologue
  scoring. Use the CE ROM TOC (`tools/ce_rom_parse.py`) or new relocation
  evidence.
- No hardware, bench or "verified in car" claim until a spare card/unit
  confirms it. Hardware-bound work stays tagged `[deferred: no hardware
  2026-11-05]`.
- No OSM encoder before the format gates
  ([`docs/research/roadmap.md`](docs/research/roadmap.md)).
- No full-system QEMU or another emulator survey (verdict:
  [`docs/research/feedback-loop.md`](docs/research/feedback-loop.md)).

## Firmware track (canonical; merges old Gate 0a, P3, P7, P8)

**Position.** Static address recovery from literals and prologues is closed;
the CE ROM TOC replaces it. Order of work: wrapper container → CE ROM TOC →
Ghidra modules → readers → L3 oracle. Reader functions are not located yet.

### Step 0 — wrapper container (partly done)

Layout at `0x200000` is documented in
[`docs/format/firmware.md`](docs/format/firmware.md) (payload length, version
string, `SUM4`, part number, `NKOK`, 15 × `u32` table, `ECEC`). Open remainder:

- [ ] Explain `NKOK`, the `0x200200` 32-bit table, the `SUM4` algorithm and
  whether `HCXCmp` is a real compressor (map payloads use plain zlib); tracked
  in [`docs/research/open-questions.md`](docs/research/open-questions.md).

### Step 1 — CE ROM header and TOC (done)

`tools/ce_rom_parse.py` parses five valid SH-4 segments. Build A starts at
`0x00200200` (`ECEC` at `+0x40`, `pTOC = 0x8e232978`, size `0x01751978`),
`ROMHDR` at file `0x01951b78`, 149 modules / 1 file. Builds B/C and the
duplicate copies are in the same report.

- [x] Validated module count, file count, physical range, CPU type and module
  names ([`tools/ce_rom_parse.py`](tools/ce_rom_parse.py),
  EXP-2026-11-05-33/34). Copy entries are still open (Step 2).

### Step 2 — CE ROM → Ghidra-ready modules (next action)

- [ ] Add `tools/cerom.py` (stdlib only): `romhdr`, `modules`, `files`,
  `sections <module>`, `va2file`, `file2va`, `extract <module> -o dir`.
- [ ] Rebuild each module as a PE (or as a Ghidra memory map: one block per
  `o32` at `o32_realaddr`, bytes from `o32_dataptr`); record file/VA bases.
  Sections with `IMAGE_SCN_COMPRESSED` (`0x00002000`) need CE ROM
  decompression; check whether that is the `HCXCmp` mystery or plain
  `CECompress`.
- [ ] Re-check the old `o32_rom` records (C-180, C-234, C-262) against the
  TOC: they are probably real `o32_rom` entries read with the wrong base.
- [ ] Use `ulCopyEntries`/`ulCopyOffset` to validate the copy list and explain
  the RAM copies; this should explain why the VA map looked "not injective"
  (EXP-22, `0x0367b180`).
- [ ] Export tables come with `e32_rom`; COM class factories follow from
  `DllGetClassObject`, so the NaviStateCC vtable can be found statically
  (constructor → vtable store), contrary to EXP-29.
- [ ] Extract `Navi.exe` / `NaviAPL` / `Navi*CC.dll` module bodies from the
  TOC and load them in Ghidra (SuperH4) or rizin; trace relative call graphs
  from the known anchors and find:
  - [ ] the file-open/read path for `.cmp`/`.ind` (and the `CMP.LST` path)
  - [ ] calls to `inflate` / zlib
  - [ ] the `DRSTR001.DAT` parser
  - [ ] the tile reader and `MESHID` logic
  - [ ] the map validity/activation check
- [ ] Locate the map-code comparator and the `HDD_INFO` open/split/parse path
  in the extracted modules.
- [ ] Re-run the existing anchors (`0x6fab2c` → `0x6faeb0` → `0x6fb05c`,
  `MAL_DataVol_getOffset`, `0x0369d400`) with exact VAs. Target: the `.ind`
  reader, the `DRSTR` parser, the tile reader and the `HDD_INFO` parser.
- [ ] Re-resolve `0x0367–0x0369` and the map-module delta through the TOC, not
  literal arithmetic; reach the parser.
- [ ] Replace the ad-hoc `scripts/rommap.py` (not in the repo) with
  `tools/cerom.py`; never keep firmware scripts only in `/tmp`. Record the
  commands in an `EXP-...`.

### Step 3 — L3 contract oracle (after Step 2)

Follow [`docs/research/l3-ghidra.md`](docs/research/l3-ghidra.md), now with a
real memory map:

- [ ] Build a headless Ghidra P-code harness with a documented memory map.
- [ ] Stub WinCE file I/O (`CreateFile`, `ReadFile`, `SetFilePointer`,
  `CloseHandle`), allocator, `memset`/`memcpy` and `OSM_Printf`/`OSM_LogMsg`.
- [ ] Add the test corpus: factory, no-op rebuild, recompressed, POI rename,
  corrupted `.ind`, truncated `.cmp`, factory/generated tile, `DRSTR`
  variants, `HDD_INFO` variants.
- [ ] Start with the `.ind`/`.cmp` reader: run it with the corpus from
  `tools/ind_mutate.py`. This answers the `chunk_size` and seek-vs-scan
  questions **without a spare card**.
- [ ] Then the `HDD_INFO` comparator with `tools/hddinfo_variants.py`: this
  answers which fields cause `DIFFERENT MAP CODE` without hardware.
- [ ] Then `DRSTR` and one tile reader.
- [ ] Compare accept/reject and normalised output with the Python readers.
- [ ] Require one generated `.cmp` and one generated tile to be accepted by
  the firmware reader.
- [ ] Record every run as an `EXP-...`; mark un-runnable functions `UNKNOWN`
  with the exact blocker.

### Closed: static-address campaign (do not redo)

- Section table at `0x374000`/`0x3e0060` is unusable (stale `dataptr`); the
  two-delta model, dual-base Ghidra, `Lib.out32` delta, `.ind` allocation
  search, `HDD_INFO` candidate `0x132e06c`, `0x1952b00` section map,
  hardened import anchor and the self-name/adjacency routes all failed.
  Static global-VA recovery is exhausted (many EXP records; summary in
  [`docs/format/firmware.md`](docs/format/firmware.md)).
- `module_scan` `(file_base, va_base)` pairs are wrong for most modules; the
  VA map is not injective (`0x0367b180`), and the collision is unresolved
  (C-382/C-384).
- `0x2e0xxxx` is an import-thunk area, not an export module: 86 thunks, IAT
  `0x1ab9000`, pre-bound and unnamed; the export-directory anchor still
  works for normal modules (26 mapped, 135 export modules).
- `0xc438a4` is a stats formatter, not the `CMP.LST` opener; `+0x02200000` is
  not the map-code delta; `0x6faf30` is a Bluetooth/OPP handler;
  `NaviStateCC` is a COM DLL with a runtime-built vtable; `0x171e9e8` is a
  type-library helper, not a vtable builder.
- `obj+0x78…+0x9c` is a message catalogue, not a vtable; the four fd
  functions are classifiers; the initializer `0xc43430` has no static caller.
- Comparator chain is verified (`0x6fab2c` → `0x6faeb0` → `0x6fb05c`);
  `userdata_type` is the `0 < v < 6` field; `0x6faeb0` is the only
  `HDD_INFO` path builder; VerInfoCC and `0x30f008` are ruled out; the
  three-filter literal method is documented.
- Anchor set: `OBJDLL.dll` (1294 exports), `STDDLL.dll` (310), six zlib
  copies, MAL volume chain (`OBJ_DiscInfo_readDiscVol` →
  `MAL_DataVol_getOffset` → `getSize`).
- Test packages: `tools/hddinfo_variants.py` (89 variants),
  `tools/ind_mutate.py` (8 variants), `tools/solve_data_delta.py`.
- Docs/claim hygiene is done: C-380/C-381 retracted, stale `0xc438a4` claims
  retracted, reader row in `roadmap.md` corrected, EXP-33/34 recorded,
  `docs/research/dynamic-break-guide.md` written.

## Hardware track (deferred: no hardware 2026-11-05)

Every item needs physical access. Keep this as the checklist for the next
hardware session; do not present these as ready actions. The original card
stays read-only; test only on spare media. The `[deferred: no hardware
2026-11-05]` tag is repeated on each top-level task; nested checks inherit it.

**US card / unit**

- [ ] Get the owner's US 2011 SD dump (read-only, SHA-256, `archive/`)
  `[deferred: no hardware 2026-11-05]`.
- [ ] Compare the US dump against the EU 2011 image
  `[deferred: no hardware 2026-11-05]`:
  - [ ] `VER_INFO/HDD_INFO.TXT` values
  - [ ] top-level directory set (does `TFTBL001` exist?)
  - [ ] `DRSTR001.DAT` node/entry layout
  - [ ] tile names and count
  - [ ] common 512-byte header version strings
- [ ] Read-only: unlock and image the US card; dump the unit NAND if possible
  `[deferred: no hardware 2026-11-05]`.
- [ ] Determine whether the US 2011 card is tiled (`MAPAL001/*.DAT`) or
  monolithic (JDM-style ~1 GB `MMAIN001.DAT`); this decides whether a software
  patch is plausible `[deferred: no hardware 2026-11-05]`.
- [ ] Record the unit's PROD `A022`, `NAVI-1`, map record and SD lock state
  `[deferred: no hardware 2026-11-05]`.
- [ ] Bench harness / L4: spare unit, 12 V, ground `TEST_B1` to bypass
  `SECURE`, CAN simulator, SD extension + host writer, power relay, screen
  capture. First pass: boot + map screen; then no-op control; then POI rename
  `[deferred: no hardware 2026-11-05]`.

**Spare card and activation matrix**

- [ ] Whole-card 16 GB SDHC clone; keep TFAT16; verify SHA-256
  `[deferred: no hardware 2026-11-05]`.
- [ ] No-op recompression control (on the US card/unit)
  `[deferred: no hardware 2026-11-05]`.
- [ ] Same-length POI rename on a spare card; record screens and rollback
  (`EXP-2026-11-05-02`) `[deferred: no hardware 2026-11-05]`.
- [ ] `.ind` mutation matrix (`tools/ind_mutate.py`, 8 variants:
  chunk_size/count/offset) `[deferred: no hardware 2026-11-05]`.
- [ ] `HDD_INFO` variant matrix (`tools/hddinfo_variants.py`, 89 variants);
  record every accepted/rejected case `[deferred: no hardware 2026-11-05]`.
- [ ] Map-code test: change only `HDD_INFO` line 1, then also the
  `0x06000000` copy; observe `DIFFERENT MAP CODE`
  `[deferred: no hardware 2026-11-05]`.
- [ ] Card/FAT/boot variants: FAT-only clone, pre-partition zeroed, changed
  label/serial `[deferred: no hardware 2026-11-05]`.
- [ ] Catalogue every error screen and trigger (`NAVI VERSION NG`,
  `DIFFERENT MAP CODE`, `MAP DATA BASE UNMATCH`, `SD UNLOCK NG`, blue
  screen); record SD lock, map-code and map-data behaviour
  `[deferred: no hardware 2026-11-05]`.
- [ ] Determine whether the unit can roll back to the previous card or NAND
  slot after a bad map/firmware `[deferred: no hardware 2026-11-05]`.
- [ ] Document the recovery path (test pin, NAND restore, spare card swap)
  `[deferred: no hardware 2026-11-05]`.
- [ ] Check `SECURE`/CAN/VIN behaviour before moving a unit between cars
  `[deferred: no hardware 2026-11-05]`.
- [ ] Back up the original card and verify the hash
  `[deferred: no hardware 2026-11-05]`.
- [ ] Write a modified image to a **spare** SD card
  `[deferred: no hardware 2026-11-05]`.
- [ ] Test in the car; record every screen/error message
  `[deferred: no hardware 2026-11-05]`.

**Unit / firmware experiments (spare unit only)**

- [ ] Card-only: US image + EU data except `VER_INFO`, re-locked with the US
  password `[deferred: no hardware 2026-11-05]`.
- [ ] Card-only: patch `0x20001f` (`NAVI VERSION NG`), line 1 of
  `HDD_INFO.TXT` (`DIFFERENT MAP CODE`), then full EU `VER_INFO`
  `[deferred: no hardware 2026-11-05]`.
- [ ] PROD `A022` `0x20→0x30` + checksum
  `[deferred: no hardware 2026-11-05]`.
- [ ] Donor EU `NB04`/`NB00`; evaluate audio and `SECURE` risks
  `[deferred: no hardware 2026-11-05]`.
- [ ] Prepare a hardware kit (JTAG/serial + card matrix) for later
  `[deferred: no hardware 2026-11-05]`.
- [ ] Dynamic break on the MAL chain: `MAL_DataVol_getOffset`
  (VA `0x03498d48`, file `0x7f5f48`) or `getSize` (VA `0x03498d28`, file
  `0x7f5f28`), then fd methods, then fd thunks; see
  [`docs/research/dynamic-break-guide.md`](docs/research/dynamic-break-guide.md)
  `[deferred: no hardware 2026-11-05]`.
- [ ] SD bus capture (CLK/CMD/DAT) for boot/map-entry read order and
  seek-vs-scan `[deferred: no hardware 2026-11-05]`.

## Data-side backlog (no firmware or hardware)

### Containers, DRSTR and REFER

- [ ] Decode the `0x180` descriptor block in the common header field by field.
- [ ] Determine the `DRSTR001.DAT` leading `u32` meaning (47 in the EU image;
  the node count is 40 — explain the difference).
- [ ] `RDSTM001`: decode the `0x1000` record size, graph tuples, record fields
  and road attributes; locate speed/direction/turn restrictions. Routing is
  the scope priority.
- [ ] Join `LCTBL` name indices to `RDSTM` road records and tile mesh codes.
- [ ] Validate the hex `B/R` grid with Prague geometry from OSM.
- [ ] `ADDRE` remaining: 6-/12-byte index cells, `c0` vs `c8` grammar,
  subtypes `0x54`/`0x58`, `40 XX YY` point encoding, trailer table.
- [ ] Decode `FRWAY` mesh-id encoding and `INTER` `n` semantics.
- [ ] Map the POI `icon code` to one of the 103 PNGs.
- [ ] Anchor the bit-packed POI field block (≥170 bits needed, 48 available).
- [ ] Explain the second 1000-id block per page.
- [ ] Isolate REFER002 `xy-coordinates` bits.
- [ ] Decode `CMP.LST` update semantics (the `MMAIN001` descriptor itself is
  decoded: C-037).

Done and documented elsewhere:

- [x] `MMAIN001` is a format/version descriptor, not a manifest (C-037).
- [x] Tile entry `value` is on-disk size for tiles (C-036).
- [x] `LCTBL001` catalog/name database (`tools/lctbl_names.py`,
  `tools/rdstm_scan.py`, [`docs/format/rdstm.md`](docs/format/rdstm.md)).
- [x] REFER/ADDRE/POINT schemas and the POI↔ADDRE record join
  ([`docs/format/refer.md`](docs/format/refer.md), C-211/C-212).

### Tiles and geography

- [ ] Decode the record grammar inside real (non-448-byte) tile payloads.
- [ ] Determine whether tiles contain polygon/area records (buildings,
  landuse, water) or only road geometry.
- [ ] Explain the role of `LEV3456R.DAT` (rows B20–B78, cols R040–R078,
  levels 3–6; layout decoded, role not proven).
- [ ] Decode `COORD001` `level`, `ZCODE` offset base, `ICODE001` trie roots.
- [ ] Reconcile longitude origin 52742 (`COORD001`) vs 52736 (tile streams).
- [ ] Map section-4 binary fields between the country code and names.
- [ ] Implement a ZE0 section-4 encoder, or explicitly document why section 4
  is preserved verbatim.
- [ ] Validate one-way/speed against a known street/sign; draw layers 4/6.
- [ ] Attach names in streaming mode.
- [ ] Decode map rendering attributes: LOD/zoom levels, label priority,
  colours, road widths, visibility rules.
- [ ] Determine string limits and collation: max name length, Polish
  diacritics, sorting, transliteration fallback.
- [ ] Decode the `BASSW7C`/`OPNG` image tile grammar (BICON001 icons are
  already extracted: [`docs/format/assets.md`](docs/format/assets.md)).
- [ ] Decide `TFTBL001` and speech-language packaging scope.

Done:

- [x] Tile grid and stream keys (`tools/mesh_grid.py`), descriptor tables.
- [x] Section-4 classification: administrative/place-name index, not geometry.
- [x] Road-shape decoding and the standalone viewer/exporter
  (`tools/ze0-viewer/render_geojson.py`, `harness.py`).
- [x] `BICON001` (103 PNGs) and the `AGM`/`TTS`/`GID` archive shapes
  ([`docs/format/assets.md`](docs/format/assets.md)).
- [x] `TMC/reception.dat` decision: separate channel, not a map-compile input
  ([`docs/research/data-coverage.md`](docs/research/data-coverage.md)).

### Cross-year differential (2011 → 2014 → 2016)

- [ ] `B30R048R`: map the directory/block differences at `0x807`/`0x808` and
  either implement a layout-aware writer or formally adopt the
  preserved-layout fallback for edited dense tiles.
- [ ] Diff `HDD_INFO`, headers, `MMAIN`, `DRSTR` leading `u32`, tile
  descriptors, section 4 and REFER across years to identify map-code and
  activation-related fields. This is the cheapest substitute for the card
  matrix.
- [ ] `REFER002`/`ICODE001`: compare region schemas and place-name counts
  across years.
- [ ] Cross-year POI mutation: parameterise the fixture per year (2014
  `POINT001.DAT` page `0x39700`; 2016 `0x3d700`).

### Card and research groundwork (closed)

- [x] All public map images archived and hashed
  ([`docs/research/image-versions.md`](docs/research/image-versions.md),
  C-500).
- [x] External research consolidated with source status
  ([`docs/research/sources.md`](docs/research/sources.md)).
- [x] US/EU layer matrix with proven-vs-hearsay status
  ([`docs/research/us-eu-region.md`](docs/research/us-eu-region.md)).
- [x] Post-partition tail characterized: 402,652,160 bytes, 400,365,370
  non-zero ([`docs/format/sd-card-layout.md`](docs/format/sd-card-layout.md),
  C-007); its purpose stays in `open-questions.md`.

## Writers and round-trip

- [ ] Gate 1: `MMAIN001.DAT`, common 512-byte/`0x5d6` headers, `REFER002`
  uncompressed files and `ADDRE` index areas round-trip byte-identically.

Done:

- [x] `.cmp`/`.ind` preserved-stream writer, 194/194
  ([`tools/cmpind_writer.py`](tools/cmpind_writer.py)).
- [x] Stock zlib 1.3.1 settings reproduce all 36,581 factory chunks; zlib-ng
  does not.
- [x] `DRSTR001.DAT` writer byte-identical
  ([`tools/drstr_ze0.py`](tools/drstr_ze0.py)).
- [x] Tile writer for unchanged tiles
  ([`tools/ze0-viewer/stream_writer.py`](tools/ze0-viewer/stream_writer.py)).
- [x] No per-file checksums; `SUM4`/updater formulas reproduced
  ([`docs/format/validation.md`](docs/format/validation.md)).
- [x] Gate 2 and Gate 3 pass for all five target tiles, including the
  one-vertex mutation and `compare-tiles`
  (`tools/ze0-viewer/harness.py`).

## Feedback loop and emulation

Design and verdict: [`docs/research/feedback-loop.md`](docs/research/feedback-loop.md).

- [ ] Optional per-year golden profiles (the 2011 profile remains the
  reference; 2014/2016 run with `--no-golden`).

Done:

- [x] L0 primitives (`tools/cmpind.py`, `tools/drstr.py`, `tools/selftest.py`).
- [x] L1 `tools/cardcheck.py`.
- [x] L2 `tools/l2check.py` and `tools/golden/eu2011.json`.
- [x] Cross-year wrapper `tools/verify.py`.
- [x] OSM comparison helper `tools/ze0-viewer/compare_osm.py`.
- [x] L5 QEMU verdict and the Wine/QEMU/MAME decision record
  ([`docs/research/feedback-loop.md`](docs/research/feedback-loop.md)).

L3 is Step 3 in the firmware track; L4 is the bench item in the hardware
track.

## OSM pipeline and build profiles

- [x] Define the intermediate format (roads, nodes, names, addresses, POIs):
  IMF v1 in [`docs/research/intermediate-format.md`](docs/research/intermediate-format.md),
  validator `tools/imf_check.py` (C-516/C-517).
- [ ] Import OSM extract for Dolnośląskie.
- [ ] Map OSM tags to the unit's road classes/attributes.
- [ ] Generate a first synthetic dataset at the unit's tile granularity.
- [ ] Compare generated data with the factory data for the same area.
- [ ] Add a schema validator and `tools/build.py --profile ...`.
- [ ] Print a size breakdown before writing an image.
- [ ] Implement whole-tile selection (the `BxxRyyR` grid is decoded:
  `tools/mesh_grid.py`).
- [ ] Keep a border buffer so cross-border routing does not stop at the border.
- [ ] Decide where ODbL attribution lives on a distributed card/image.
- [ ] Verify that removing/adding files keeps `DRSTR001.DAT` and the unit
  consistent.
- [ ] Decide charset and turn-restriction handling.
- [ ] P9 vertical slice, based on `tools/ze0-viewer/vendor/osm2clarion`:
  - [ ] Select one target tile and one profile (`dolnoslaskie-detail` or the
    tiny `dolnoslaskie-test`).
  - [ ] Generate roads/coast/landuse for that tile from OSM.
  - [ ] Preserve factory REFER/ADDRE/POI data in the first slice.
  - [ ] Rebuild `DRSTR001.DAT` and `MMAIN001.DAT`.
  - [ ] Run L1 and L2 on the rebuilt card.
  - [ ] Implement the OSM encoder for roads/names/addresses/POIs beyond the
    first tile.
  - [ ] Decide the address/POI import strategy after the first tile passes.

Done:

- [x] Initial JSON profile shape and three starting profiles
  (`profiles/*.json`).
- [x] Whole-tile-only decision
  ([`docs/research/build-profiles.md`](docs/research/build-profiles.md)).
- [x] Dolnośląskie vertical-slice plan
  ([`docs/research/osm-vertical-slice.md`](docs/research/osm-vertical-slice.md)).

## Housekeeping

- [x] Merge the firmware sections (Gate 0a, P3, P7, P8) into one ordered list,
  deduplicate repeated tasks and tick items already delivered elsewhere
  (this revision, 2026-11-05).
- [ ] Per session: one experiment, one `EXP-...` record, one commit. Stop a
  firmware line after two rounds without new evidence and write down why.
- [ ] Keep `claims.md` updated whenever a hypothesis is confirmed or refuted;
  it is the single source of truth.
- [ ] Add an `EXP-...` record for every hardware test and every material
  format correction.
- [ ] When a hypothesis is refuted, add a new experiment with `Supersedes`
  rather than rewriting the old record.
