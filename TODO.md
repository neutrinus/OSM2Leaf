# TODO

Actionable backlog. For "what we do not know yet" see
[`docs/research/open-questions.md`](docs/research/open-questions.md); for the
evidence status of each claim see
[`docs/research/claims.md`](docs/research/claims.md).

## P0 — research groundwork

- [ ] Wait for the owner's **US 2011 SD dump**; record SHA-256 and store it in
  `archive/` (git-ignored).
- [ ] Compare the US dump against the EU 2011 image:
  - [ ] `VER_INFO/HDD_INFO.TXT` values
  - [ ] top-level directory set (does `TFTBL001` exist?)
  - [ ] `DRSTR001.DAT` node/entry layout
  - [ ] tile names and count
  - [ ] common 512-byte header version strings
- [ ] Collect all map images from `files.viaaq.eu` and build a year/market
  comparison table (subagent in progress).
- [ ] Consolidate external research into `docs/research/sources.md` with
  FACT/HYPOTHESIS labels (subagent in progress).

## P0b — region / US unit in Europe

See [`docs/research/us-eu-region.md`](docs/research/us-eu-region.md).

- [ ] Read-only: unlock and image the US card; dump the unit NAND if possible.
- [ ] Determine whether the US 2011 card is tiled (`MAPAL001/*.DAT`) or
  monolithic (JDM-style ~1 GB `MMAIN001.DAT`). This decides whether a software
  patch is plausible.
- [ ] Record the unit's PROD `A022`, `NAVI-1`, map record and SD lock state.
- [ ] Card-only: US image + EU data except `VER_INFO`, re-locked with the US
  password.
- [ ] Card-only: patch `0x20001f` (`NAVI VERSION NG`), line 1 of
  `HDD_INFO.TXT` (`DIFFERENT MAP CODE`), then full EU `VER_INFO`.
- [ ] Bench harness: 12 V, ground `TEST_B1` to bypass `SECURE`, capture error
  screens.
- [ ] Spare unit only: PROD `A022` `0x20→0x30` + checksum.
- [ ] Spare unit only: donor EU `NB04`/`NB00`; evaluate audio and `SECURE`
  risks.
- [ ] Update the layer matrix with what is proven vs still hearsay.

## P0c — validation, card and minimal change

Three agents are investigating these; merge their results here when done.

- [ ] **Checksums/validation:** does the unit check `.cmp`, `DRSTR001.DAT`,
  `MMAIN001.DAT`, `HDD_INFO.TXT`, file sizes or the whole card? Reproduce the
  `SUM4`/NK checksum if relevant. Build a mutation matrix.
- [ ] **Card/FAT/boot:** does the unit read the pre-partition firmware area or
  the post-partition tail? Determine required partition offset, cluster size,
  label, volume ID, contiguity, capacity and lock state. Build a clone
  checklist.
- [ ] **Minimal accepted change:** mutation ladder from renamed POI/street to
  added file; define offline validation and the first hardware experiment with
  rollback.

## P1 — finish the map container description

- [ ] Decode `MMAIN001.DAT`: what do the 4,096 bytes describe? Are there
  pointers into other databases?
- [ ] Decode the `0x180` descriptor block in the common header field by field.
- [ ] Determine the `DRSTR001.DAT` leading `u32` meaning (47 in the EU image).
- [ ] Confirm whether entry `value` for tiles is the total decompressed size.
- [x] `LCTBL001`: catalog, 12-column schema, 517-stream name database
  (`docs/format/rdstm.md`).
- [ ] `RDSTM001`: decode the `0x1000` record size, graph tuples, record fields
  and road attributes; locate speed/direction/turn restrictions.
- [ ] Join `LCTBL` name indices to `RDSTM` road records and tile mesh codes.
- [ ] Validate the hex `B/R` grid with Prague geometry from OSM.
- [ ] Decode `REFER001`/`REFER002` record formats: addresses, POIs,
  coordinates, street names, `MESHID`/`POI`/`Pre`/`Next` relationships.
- [ ] Decode `MMAIN001.DAT` + `CMP.LST` update semantics.

## P2 — tiles and geography

- [x] Tile grid: B/R hex, `lat_min = B*2/3`, `lon_max = 108-R`,
  5.333°×8°; `tools/mesh_grid.py` and `docs/format/map-tiles.md`.
- [x] Descriptor tables `0x1ac` (LOD) and `0x2ac` (bboxes in arc-minutes).
- [x] Stream key: `(A = 32768 + lat*192, B = 52736 + lon*128, section tag)`.
- [ ] Decode the record grammar inside real (non-448-byte) tile payloads.
- [ ] Explain `LEV3456R.DAT` (rows B20–B78, cols R040–R078, levels 3–6).
- [ ] Build a small standalone tile viewer/exporter.
- [ ] Decode `COORD001` `level`, `ZCODE` offset base, `ICODE001` trie roots.
- [ ] Reconcile longitude origin 52742 (`COORD001`) vs 52736 (tile streams).

## P2b — presentation, assets and extras

- [ ] Decode map rendering attributes: LOD/zoom levels, label priority,
  colours, road widths, visibility rules.
- [ ] Determine string limits and collation: max name length, Polish
  diacritics, sorting, transliteration fallback.
- [ ] Decode `BICON001.DAT` (POI icons) and the `BASSW7C`/`OPNG` asset container.
- [ ] Decode the simple `AGM`/`TTS`/`GID` archive format (header, entry table)
  in case icons/voice are needed later.
- [ ] Decide whether `TMC/reception.dat` affects map compilation or is a
  separate data channel.

## P3 — firmware / reader

- [ ] Decode the firmware container at `0x200000` (`NKOK`, `ECEC`, `SUM4`,
  32-bit table at `0x200200`).
- [ ] Identify or disprove `HCXCmp` as the compression algorithm.
- [ ] Extract `Navi.exe` / `NaviAPL` / `Navi*CC.dll` SH-4 modules.
- [ ] Load them in Ghidra (SuperH4) or rizin and find:
  - [ ] file-open/read path for `.cmp`/`.ind`
  - [ ] calls to `inflate` / zlib
  - [ ] `DRSTR001.DAT` parser
  - [ ] tile reader and `MESHID` logic
  - [ ] map validity/activation check
- [ ] Inspect the 402,652,160-byte post-partition tail.

## P3b — update, error and recovery behavior

- [ ] Catalogue every error screen and what triggers it (`NAVI VERSION NG`,
  `DIFFERENT MAP CODE`, `MAP DATA BASE UNMATCH`, `SD UNLOCK NG`, blue screen).
- [ ] Determine whether the unit can roll back to the previous card or NAND
  slot after a bad map/firmware.
- [ ] Document the recovery path (test pin, NAND restore, spare card swap).
- [ ] Check `SECURE`/CAN/VIN behaviour before moving a unit between cars.

## P4 — writer / round-trip

- [ ] Implement a `.cmp`/`.ind` **writer** and verify byte-identical output
  for unchanged files (or document which bytes differ and why).
- [ ] Implement a `DRSTR001.DAT` writer and verify re-parse equality.
- [ ] Implement a tile container writer for an unchanged tile.
- [ ] Determine all checksums/signatures and where they are stored.
- [ ] Build a minimal synthetic change (e.g. one renamed POI) and validate it
  offline by re-reading with our own tools.

## P4b — emulation / feedback loop

Build the cheap layers first; full-system boot is a research spike, not a
prerequisite.

- [x] Layer 0: static decoder + validator (`tools/cmpind.py`,
  `tools/drstr.py`, `tools/selftest.py`).
- [ ] Layer 1: decode a tile/`.cmp` to a neutral format, render to
  PNG/GeoJSON, compare with OSM.
- [ ] Layer 2: round-trip an unchanged file byte-identically, then a tiny
  mutation.
- [ ] Layer 3: run extracted SH-4 decoder functions in Ghidra P-code
  emulation (works today) and compare with the Python reader.
- [x] Layer 4 verdict: full-system QEMU is not realistic. QEMU has only the
  `r2d` SH-4 board, `sh7750.c` aborts on unknown registers, and most
  peripherals/BSP are missing. Use QEMU `r2d` only as a bare-metal SH-4 bench;
  MAME's SH-4 core is the reference if a custom machine is ever needed.

## P5 — OSM pipeline

- [ ] Define the intermediate format (roads, nodes, names, addresses, POIs).
- [ ] Import OSM extract for Dolnośląskie.
- [ ] Map OSM tags to the unit's road classes/attributes.
- [ ] Generate a first synthetic dataset at the unit's tile granularity.
- [ ] Compare generated data with the factory data for the same area.

## P5b — user-selectable build profiles

See [`docs/research/build-profiles.md`](docs/research/build-profiles.md) and
`profiles/*.json`.

- [x] Define the initial JSON profile shape and three starting profiles
  (`dolnoslaskie-detail`, `poland-full`, `europe-motorways`).
- [ ] Add a schema validator and `tools/build.py --profile ...`.
- [ ] Print a size breakdown before writing an image.
- [x] Decide tile selection: **whole tiles only**, no sub-tile clipping
  (`docs/research/build-profiles.md`).
- [ ] Implement whole-tile selection once the `BxxRyyR` grid is decoded.
- [ ] Keep a border buffer so cross-border routing does not stop at the border.
- [ ] Decide where ODbL attribution lives on a distributed card/image.
- [ ] Verify that removing/adding files keeps `DRSTR001.DAT` and the unit
  consistent.

## P6 — hardware testing (only after P0–P5)

- [ ] Back up the original card and verify the hash.
- [ ] Write a modified image to a **spare** SD card.
- [ ] Test in the car; record every screen/error message.
- [ ] Document recovery steps.

## Documentation / housekeeping

- [ ] Add a `docs/format/rdstm.md` once `RDSTM001` is decoded.
- [ ] Add a `docs/format/refer.md` once address/POI records are decoded.
- [ ] Keep `claims.md` updated whenever a hypothesis is confirmed or refuted.
- [x] Add tiny synthetic fixtures (not vendor data) for the tools.
- [x] Add a `tools/README.md` with exact commands and expected output.
- [x] Add `tools/selftest.py` covering `cmpind.py` and `drstr.py` without
  vendor data.
