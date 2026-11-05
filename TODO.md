# TODO

Actionable backlog. For "what we do not know yet" see
[`docs/research/open-questions.md`](docs/research/open-questions.md); for the
evidence status of each claim see
[`docs/research/claims.md`](docs/research/claims.md).

## Next up (confidence gates)

See [`docs/research/roadmap.md`](docs/research/roadmap.md). The rule: data
archaeology + firmware RE must agree, then round-trip proves the tooling.
OSM only after that.

1. **Gate 0a — firmware reader cross-check**
   - [x] Section table at `0x374000`/`0x3e0060`: unusable (stale `dataptr`).
   - [x] Two-delta model (local to the module) and reader-related functions
     (`0xc438a4`, `0xc42520`, `0xc48380`, `0xc0ebf8`).
   - [x] Dual-base Ghidra: **negative** — filenames have zero literal
     references; readers are name-driven via `DRSTR`/`CMP.LST`.
   - [x] Map-code check: textual `HDD_INFO` field comparison; `0x06000000`
     copy is likely the system-side reference.
   - [x] Retracted: `obj+0x78…+0x9c` is a message catalogue, not a vtable;
     the four fd functions are classifiers, not writers.
   - [x] `Lib.out32` code delta: not pinnable (data-only pool, flat scoring).
   - [x] `.ind` allocation-shape search: 0 sites; parser not detectable this way.
   - [x] `HDD_INFO` candidate `0x132e06c`: data, not code.
   - [x] `0x1952b00`: RAM copy list, not a section map (retracted).
   - [x] Export anchor works: 26 modules mapped, `file = Fb + RVA`.
   - [x] Hardened import anchor: 0 candidates — pre-bound WinCE ROM strips
     imports (retracted).
   - [x] ROM module table / self-name / adjacency routes: all refuted
     (`EXP-2026-11-05-14`).
   - [x] Static VA recovery from this image is exhausted.
   - [x] Comparator chain corrected: `0x6fab2c` → `0x6faeb0` → `0x6fb05c`;
     `userdata_type` is the `0<v<6` field (EXP-2026-11-05-17).
   - [x] Test package: `tools/hddinfo_variants.py` generates 73
     length-preserving HDD_INFO variants.
   - [ ] Run the spare-card matrix (highest value, no RE).
   - [ ] Identify the COM class behind property 17 via `.rgs`/CLSID and
     decompile its `Set(17, path)` parser.
   - [ ] Firmware RE is the **primary path** (decision 2026-11-05): continue
     until the readers define the data contract. No timebox.
   - [ ] Relative call-graph tracing from `0xc438a4`, `0xc0ebf8`, `0xc48380`.
   - [ ] Ghidra P-code/emulation on selected routines.
   - [ ] Hardware/dynamic tracing (JTAG/serial or spare-card loop) if static
     relative tracing stalls.
2. **Gate 0b — tile payload grammar**
   - [x] All five targets rebuild byte-identically, including dense
     `B30R048R` (`EXP-2026-11-05-12`).
   - [x] Road-shape records decoded/rendered; streaming writer works.
   - [x] `LEV3456R` level 6 decoded; coarse levels 3–5 rebuild with 0 failures.
   - [x] Section 4 classified: administrative/place-name index, 20 records /
     68 names in `B30R048R`; GeoJSON points.
   - [x] Road names decoded via the odd partner record; streaming decoder
     handles 436 MB at 242 MB RSS.
   - [x] `compare-tiles` acceptance: zero diff on unchanged, differs on a
     one-vertex mutation.
   - [ ] Map section-4 binary fields and build a ZE0 section-4 encoder.
   - [ ] Validate one-way/speed against a known street/sign; draw layers 4/6.
   - [ ] Attach names in streaming mode.
   - Deliverable: full tile record spec + viewer.
3. **Gate 1 — uncompressed round-trip (byte-identical)**
   - [x] `DRSTR001.DAT` writer reproduces the EU 2011 file byte-for-byte.
   - [ ] `MMAIN001.DAT`, headers, `REFER002`, `ADDRE` index areas.
4. **Gate 2 — compressed round-trip**
   - [x] `.cmp`/`.ind` preserved-stream writer: 194/194 byte-identical
     (`EXP-2026-11-05-06`).
   - [x] Stock zlib 1.3.1 settings reproduce all 36,581 factory chunks;
     zlib-ng does not.
   - [x] Build rule: preserve unchanged, hybrid for changed, pin compressor
     for new files.
5. **Gate 3 — tile round-trip**
   - [x] Clean tiles byte-identical (`EXP-2026-11-05-04`).
   - [x] Dense `B30R048R` byte-identical (`EXP-2026-11-05-12`).
   - [x] One-vertex mutation changes exactly one vertex and still round-trips
     (harness `mutate`).
   - [x] `compare-tiles` zero diff on unchanged input.
   - [ ] Section-4 binary fields/encoder (content is an index, not geometry).
6. **Gate 5/6 — activation and card feedback**
   - [ ] Whole-card 16 GB SDHC clone; keep TFAT16; verify SHA-256.
   - [ ] No-op control, then POI rename (`EXP-2026-11-05-02`).
   - [ ] Map-code test: `HDD_INFO` line 1, then also the `0x06000000` copy.
7. **Gate 7 — OSM compiler** (only after 0–6)
   - [ ] Profile validator + `tools/build.py` + size estimator.
   - [ ] Encoder for roads/names/addresses/POIs.
   - [ ] Charset and turn-restriction decisions.

Content joins (POI/ADDRE/icon) and `LEV3456R` remain independent leaves; they do
not block the gates above.

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

- [x] **Checksums/validation:** no per-file checksum; `SUM4`/updater formulas
  reproduced; map code is a text/market check (`docs/format/validation.md`).
- [ ] **Map-code hardware test:** change only `HDD_INFO` line 1, then also the
  `0x06000000` copy; observe `DIFFERENT MAP CODE`.
- [ ] **Card/FAT/boot:** whole-card clone is the only externally validated
  method; 16 GB SDHC; keep TFAT16. Still to test: FAT-only clone, pre-partition
  zeroed, changed label/serial.
- [x] **Minimal accepted change:** same-length POI rename validated offline
  (`docs/research/minimal-change.md`, EXP-2026-11-05-02). Hardware pending.

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
- [x] Common REFER anatomy, 33-country sharding, POINT schema/pages, INTER,
  ICADM, ZIPFR (`docs/format/refer.md`).
- [x] `ADDRE`: container, 22-byte index, schema, record tags and 4-byte
  lat/lon ids (`docs/format/refer.md`).
- [ ] `ADDRE` remaining: 6-/12-byte index cells, `c0` vs `c8` grammar,
  subtypes `0x54`/`0x58`, `40 XX YY` point encoding, trailer table.
- [ ] Prove the POI ↔ ADDRE join (shared ids confirmed; record-level join not).
- [ ] Decode `FRWAY` mesh-id encoding and `INTER` `n` semantics.
- [x] POI → location: A is the display point, B the address reference.
- [x] `f11 = (2000*page + slot) & 0xffff` (99.3 % / 95.4 % on POINT004/021).
- [x] POI ↔ ADDRE record join via `(street name, house number)`.
- [x] `BICON001`: 103 PNG icons extracted; see `docs/format/assets.md`.
- [ ] Map the POI `icon code` to one of the 103 PNGs.
- [ ] Anchor the bit-packed POI field block (≥170 bits needed, 48 available).
- [ ] Explain the second 1000-id block per page.
- [ ] Isolate REFER002 `xy-coordinates` bits.
- [ ] Decode `MMAIN001.DAT` + `CMP.LST` update semantics.

## P2 — tiles and geography

- [x] Tile grid: B/R hex, `lat_min = B*2/3`, `lon_max = 108-R`,
  5.333°×8°; `tools/mesh_grid.py` and `docs/format/map-tiles.md`.
- [x] Descriptor tables `0x1ac` (LOD) and `0x2ac` (bboxes in arc-minutes).
- [x] Stream key: `(A = 32768 + lat*192, B = 52736 + lon*128, section tag)`.
- [ ] Decode the record grammar inside real (non-448-byte) tile payloads.
- [ ] Determine whether tiles contain polygon/area records (buildings,
  landuse, water) or only road geometry.
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
- [x] Build a minimal synthetic change (same-length POI rename in
  `POINT032.DAT`) and validate it offline: size unchanged, page-confined,
  DRSTR unchanged, 1/1 verify (`docs/research/minimal-change.md`).
- [ ] Run the no-op recompression control on the **US** card/unit.
- [ ] Run the rename test on a spare card; record screens and rollback.

## P4b — feedback loop / emulation

See [`docs/research/feedback-loop.md`](docs/research/feedback-loop.md) for the
analysis. Build the cheap layers first; full-system emulation is a timeboxed
research spike, not a prerequisite.

- [x] **L0 — primitives:** static decoder + validator (`tools/cmpind.py`,
  `tools/drstr.py`, `tools/selftest.py`).
- [ ] **L1 — whole-card validator:** MBR/FAT, `DRSTR` tree, sizes, `.ind`
  offsets, zlib decode, tile inventory, `MMAIN` table, `HDD_INFO` copy. Stable
  exit code + machine-readable report.
- [ ] **L2 — semantic/golden:** decode a tile/`.cmp` to a neutral format,
  render to PNG/GeoJSON, compare with OSM/golden output; byte-identical
  round-trip for unchanged files, then a tiny mutation.
- [ ] **L3 — function-level SH-4 emulation:** run located reader functions
  under Ghidra P-code with mocked file I/O; compare with the Python reader.
  Requires relative call-graph tracing to locate the readers first.
- [ ] **L4 — bench hardware-in-the-loop:** spare unit, 12 V, `TEST_B1`, CAN
  simulator, SD extension + host writer, power relay, screen capture. First
  pass: boot + map screen; then no-op control; then POI rename.
- [x] **L5 verdict:** full-system QEMU is not realistic. QEMU has only the
  `r2d` SH-4 machine, `sh7750.c` aborts on unknown registers, and most
  peripherals/BSP are missing. Use QEMU `r2d` only as a bare-metal SH-4 bench;
  MAME's SH-4 core is the reference if a custom machine is ever needed.
- [x] **Decision record:** Wine rejected (Win32 layer, not SH-4/WinCE);
  QEMU/MAME/sh3-emu assessed; offline contracts + bench HIL recommended.
  See `docs/research/feedback-loop.md`.

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
- [x] Add `docs/experiments/README.md` and `TEMPLATE.md` with the append-only
  experiment convention.
- [ ] Add an `EXP-...` record for every hardware test and every material
  format correction.
- [ ] When a hypothesis is refuted, add a new experiment with `Supersedes`
  rather than rewriting the old record.
