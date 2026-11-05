# TODO

Actionable backlog. For "what we do not know yet" see
[`docs/research/open-questions.md`](docs/research/open-questions.md); for the
evidence status of each claim see
[`docs/research/claims.md`](docs/research/claims.md).

## Status review and next steps (2026-11-05)

**Read this section first.** It supersedes the ordering of the older
sections below, which are kept as the historical backlog.

### Where the work is stuck

1. **Firmware: a static VA-guessing loop.** EXP-05 … EXP-29 (about 20
   experiments) tried to recover module virtual addresses by fitting deltas,
   scanning literals, export/import anchors and vtable runs. Almost every round
   retracted the previous one (C-068, C-182, C-234, C-262, C-380, C-381, …)
   and ended with "static is closed, go dynamic". Dynamic work needs hardware,
   which is unavailable, so the firmware track has stopped.
2. **The "no XIP table" negative (C-380/C-381) is probably wrong.** It was
   based on a search for the strings `B000FF` and `ROMHDR`. `B000FF` only
   exists in `.bin` files, not in a raw/NB0 ROM, and `ROMHDR` is a binary
   struct with no signature string. A standard Windows CE ROM image has the
   `ECEC` signature at **image start + `0x40`**, followed by `pTOC` (the VA of
   `ROMHDR`) and the `ROMHDR` offset from image start. That is exactly what
   sits at `0x200240`: `ECEC`, `0x8e232978`, `0x01751978`. So:
   - CE image start = `0x200200` (the Clarion wrapper header is `0x200` bytes);
   - `ROMHDR` should be at file `0x200200 + 0x01751978 = 0x01951b78`;
   - VA → file: `file = VA − 0x8e232978 + 0x01951b78`
     (i.e. image VA base `0x8cae1000` ↔ file `0x200200`);
   - the "tail table" at `0x1951ee0` (32-byte records, all pointers in
     `0x8C…0x8E`) is right after `ROMHDR` and matches the 32-byte
     `TOCentry` layout. C-381 tested bases on a coarse grid
     (`0x8BE00000…0x8DE00000`); `0x8cae1000` is not on that grid.
   If this holds, the ROM TOC gives every module's `e32_rom`/`o32_rom` records,
   i.e. exact `o32_realaddr` (VA) and `o32_dataptr` (ROM location) per section.
   That replaces all delta guessing and unblocks the reader search statically.
3. **Process problems.** `AGENTS.md` lists "no XIP/section table" as a dead end
   that must not be redone, which blocks the most promising path. TODO.md has
   three overlapping firmware sections (Gate 0a, P3, P7) and many items that
   are already done elsewhere but still unchecked (tile viewer, writers). Each
   new session re-derived context instead of acting.
4. **Format track is in good shape but parked.** Containers, `DRSTR`, tile
   grid and five target tiles round-trip byte-identically; L1/L2 validators
   work cross-year. What remains on the data side does not need firmware or
   hardware.

### Step 1 — verify the CE ROM header (one short session, high value)

**Done, confirmed (2026-11-05):** see
[`EXP-2026-11-05-35`](docs/experiments/EXP-2026-11-05-35-ce-romhdr.md) and
`tools/cerom.py`. All 149 module names resolve; old anchors agree; the
`HDD_INFO`/`SD Import` literals are in `Navi.exe` (VA `0x004e7d28`,
`0x004e8584`, `0x004e995c`). Builds B/C still open (need bytes past 32 MiB).

Needs only the first ~30 MB of the EU 2011 image (`dd bs=1M count=32`).

- [x] Read `ROMHDR` at file `0x01951b78` (0x54 bytes, little-endian):
  `dllfirst, dlllast, physfirst, physlast, nummods, ulRAMStart, ulRAMFree,
  ulRAMEnd, ulCopyEntries, ulCopyOffset, ulProfileLen, ulProfileOffset,
  numfiles, ulKernelFlags, ulFSRamPercent, ulDrivglobStart, ulDrivglobLen,
  u16 usCPUType, u16 usMiscFlags, pExtensions, ulTrackingStart,
  ulTrackingLen`.
- [x] Sanity checks: `physfirst ≤ 0x8e232978 < physlast`;
  `physfirst` near `0x8cae1000`; `usCPUType` = SH-4 (`0x01a6` /
  `IMAGE_FILE_MACHINE_SH4`); `nummods` and `numfiles` in the tens to low
  hundreds; `dllfirst/dlllast` cover the `0x02xxxxxx–0x03xxxxxx` module band
  seen in the code.
- [x] Walk `TOCentry[nummods]` (32 bytes: `attrib, ftTime(8), nFileSize,
  lpszFileName, ulE32Offset, ulO32Offset, ulLoadOffset`) and then
  `FILESentry[numfiles]`. Every `lpszFileName` must resolve to an ASCII name
  (`nk.exe`, `coredll.dll`, …, the navi modules) through the formula above.
- [x] ~~If the formula is off~~ (not needed: the formula holds), solve the base from `lpszFileName` pointers
  alone (they must land on NUL-terminated ASCII), not from code literals.
- [x] Repeat for builds B (`0x3e00000`) and C (`0x5200000`); B/C have a
  different wrapper layout, so locate `ECEC` first.
- [x] Record as a new `EXP-…-ce-romhdr.md`. If confirmed, mark C-380 and
  C-381 `RETRACTED` with `Superseded by`, and update `AGENTS.md`,
  `docs/format/firmware.md` and `roadmap.md` in the same commit.
- [x] ~~If refuted~~ (confirmed), record the exact `ROMHDR` bytes and why each check failed,
  so nobody repeats it.

### Step 1b — tasks after EXP-35 (ordered; each ends with an EXP + claims)

Rule for all of these: **start from `tools/cerom.py`, never from fitted
deltas.** A new firmware address is only a claim once `cerom.py` names its
module, section and file offset.

1. [x] **Full-image sweep** (done, EXP-2026-11-05-36; B/C are kernel regions) (needs the full image, not only 32 MiB): locate
   every `ECEC` (builds A at `0x200000`/`0x2000000`, B at `0x3e00000`/
   `0x4800000`, C at `0x5200000`), run `cerom.py` on each (`--image-start`),
   and diff the module lists. Record which builds contain which modules
   (the map code is only in A; B/C differ by 4 bytes in the header area).
2. [x] **Kernel region** (done: images B/C, COREDLL ordinals via `cerom.py exports`; original note:) `nk.exe`/`coredll.dll`/`filesys.exe` are not in this
   TOC; `pExtensions = 0x880030a4` and the `0x88…` addresses point to another
   XIP region. Find it (look for a second `ROMHDR`-shaped block or an `NKOK`
   region elsewhere) to name COREDLL ordinals (e.g. 719 behind `0x0369d400`).
3. [ ] **Decompress `IMAGE_SCN_COMPRESSED` sections** (245/527). Try
   CE `CECompress` (LZX/"romimage" block format) on a small one first
   (`NaviMapCC.dll` `.data`, psize `0x2c6`, vsize `0x5b8`): the output size
   must equal `vsize`. Add `cerom.py decompress` and a unit test on that
   section. This also answers the `HCXCmp` question.
4. [ ] **Ghidra memory maps.** Generate one block per `o32` at
   `o32_realaddr` for the navi-relevant modules (`Navi.exe`, `NaviStateCC`,
   `NaviMapCC`, `NaviSetCC`, `OBJDLL`, `STDDLL`, `BT_MGR`, `VerInfoCC`,
   `oleaut32`); add the script to `tools/`, not to `/tmp`.
5. [ ] **`MapUpdate.exe` (image B, file `0x04344200`)**: a second source for how the unit validates/installs map data; read it alongside the next item.
5b. [ ] **`Navi.exe` HDD_INFO / SD Import.** Disassemble around the pools at
   VA `0x004e7d28` (paths) and `0x004e8584`/`0x004e995c` (comparator
   messages). Name the function that reads `HDD_INFO.TXT`, the field parser
   and the six-line mapping; answer which fields trigger
   `DIFFERENT MAP CODE`. Compare with `tools/hddinfo_variants.py`.
6. [ ] **Reader chain.** From `OBJDLL` `MAL_DataVol_getOffset`/`getSize`
   callers, then the `.ind`/`.cmp` reader and `DRSTR`/tile readers, now with
   exact VAs. Answer `chunk_size` (buffer vs compare against `0x10000`) and
   seek-vs-scan.
7. [ ] **Audit the old firmware claims.** Go through
   `docs/format/firmware.md` and C-0xx…C-3xx: mark each claim that rested on
   delta fitting as `RETRACTED`/`superseded` or re-verify it with `cerom.py`
   (retraction rule, same commit). Candidates: C-180, C-234, C-262, C-182,
   C-068, C-370…C-375, the `0x1952b00` copy-list claims, EXP-22/23/25/26/27/28/29.
8. [ ] **Untangle TODO P3/P7.** Mark as done or merge into this section.

### Step 2 — turn the ROM into Ghidra-ready modules (if Step 1 holds)

- [x] Add `tools/cerom.py` (stdlib only): `romhdr`, `modules`, `files`,
  `sections <module>`, `va2file`, `file2va`, `extract <module> -o dir`
  (raw sections; decompression still open).
- [ ] Rebuild each module as a PE (or as a Ghidra memory map: one block per
  `o32` at `o32_realaddr`, bytes from `o32_dataptr`). Sections with
  `IMAGE_SCN_COMPRESSED` (`0x00002000`) need CE ROM decompression; check
  whether this is the `HCXCmp` mystery or plain `CECompress`.
- [ ] Re-check the old `o32_rom` records (C-180, C-234, C-262) against the
  TOC: they are probably real `o32_rom` entries read with the wrong base.
- [ ] Use `ulCopyEntries`/`ulCopyOffset` to explain the RAM copies; this
  should explain why the VA map looked "not injective" (EXP-22, `0x0367b180`).
- [ ] Export tables come with `e32_rom`; COM class factories follow from
  `DllGetClassObject`, so the NaviStateCC vtable can be found statically
  (constructor → vtable store), contrary to EXP-29.
- [ ] Re-run the existing anchors (`0x6fab2c` → `0x6faeb0` → `0x6fb05c`,
  `MAL_DataVol_getOffset`, `0x0369d400`) with exact VAs. Target: the `.ind`
  reader, the `DRSTR` parser, the tile reader and the `HDD_INFO` parser.
- [ ] Replace the ad-hoc `scripts/rommap.py` (not in the repo) with
  `tools/cerom.py`; never keep firmware scripts only in `/tmp`.

### Step 3 — L3 contract oracle (after Step 2)

Follow [`docs/research/l3-ghidra.md`](docs/research/l3-ghidra.md), now with a
real memory map:

- [ ] Start with the `.ind`/`.cmp` reader: run it under Ghidra P-code with
  stubbed `CreateFile`/`ReadFile`/`SetFilePointer` and the corpus from
  `tools/ind_mutate.py`. This answers the `chunk_size` and seek-vs-scan
  questions **without a spare card**.
- [ ] Then the `HDD_INFO` comparator with `tools/hddinfo_variants.py`: this
  answers which fields cause `DIFFERENT MAP CODE` without hardware.
- [ ] Then `DRSTR` and one tile reader.

### Parallel track — data side, no firmware or hardware needed

Ordered by value for the first OSM tile:

- [ ] `RDSTM001`: decode records, graph tuples and road attributes (speed,
  one-way, turn restrictions). Routing is the scope priority and nothing is
  known yet about how the router reads the graph.
- [ ] Section 4 of the tiles: map the binary fields and write the encoder,
  or prove it can be kept verbatim for a changed tile.
- [ ] Gate 1: `MMAIN001.DAT` (4,096 bytes, 11 entries) round-trip and field
  meaning; the `0x180` header block.
- [ ] Explain the `B30R048R` 2013–2016 rebuild difference at `0x807`
  (EXP-30); it is probably a header/writer variant worth one diff session.
- [ ] Cross-year differential (2011 → 2014 → 2016 cards): diff `HDD_INFO`,
  headers, `MMAIN`, `DRSTR` leading `u32` and tile descriptors to see which
  fields change with the map code. This is the cheapest substitute for the
  card matrix.
- [ ] P9 vertical slice: one tile from OSM through `osm2clarion`, preserving
  factory REFER data, rebuilt `DRSTR`/`MMAIN`, passing L1 and L2.

### Hardware (deferred, keep ready)

- [ ] Get the owner's US 2011 SD dump (read-only, record SHA-256).
- [ ] Spare-card kit: 16 GB SDHC whole-card clone, no-op control, POI rename,
  `HDD_INFO` and `.ind` matrices. Steps 1–3 should shrink these matrices to a
  few confirming cases.

### Housekeeping

- [ ] Merge the firmware sections (Gate 0a, P3, P7, P8) into one list after
  Step 1; tick items that are done (tile viewer, `.cmp`/`DRSTR`/tile
  writers, `rdstm.md`/`refer.md` exist).
- [ ] Per session: one experiment, one `EXP-…` record, one commit. Stop a
  firmware line after two rounds without new evidence and write down why.

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
   - [x] `VerInfoCC` identified (`0x027cae00`, `GetVersionInfo`) but ruled
     out as the parser (EXP-2026-11-05-18).
   - [x] `0x30f008` trail: false (free function; `0x01f83368` is a writable
     global; mspart/WAVEAPI bases overlap). Round-10 link retracted.
   - [x] `0xc438a4` retracted: memory/fd stats formatter, not CMP.LST; real
     CMP.LST at `0xdf945d` has zero refs (EXP-2026-11-05-20).
   - [x] Code delta `+0x02200000` retracted; per-instruction table gives band
     `0x02b0xxxx–0x02b5xxxx`, best fit `+0x01f07d5c`.
   - [x] New anchors: OBJDLL (`0x7dd200`, 1294 exports), STDDLL
     (`0x834200`), six zlib copies.
   - [ ] Find the `0x2e0xxxx` module export table (RVA range must cover
     `0x2e00f98–0x2e533e4`).
   - [ ] Run the `.ind` mutation matrix on a spare card (chunk_size/count/offset).
   - [ ] SD bus capture (CLK/CMD/DAT) for read order and seek-vs-scan.
   - [x] `USR_Convert` module `0x0101e408` retracted (IAT slots); map-module
     `VER_INFO` refs retracted (call targets).
   - [x] Three-filter literal method (F1/F2/F3): 236,765 → 95,758.
   - [x] HDD_INFO builder `0x6faeb0` builds the path from fragments; parser
     helpers at `0x0369d400`/`0x036922cc`/`0x0367b180`/`0x0369d3dc`.
   - [x] `0x0367–0x0369` cannot be pinned: library band, best delta 7/13,
     VA map not injective (`0x0367b180` is both jsr target and string).
   - [ ] Parse the `romimage` XIP section table (`file ↔ VA ↔ size`); leads:
     `ECEC` at `+0x240`, `NKOK` at `+0x1fc`.
   - [ ] Re-resolve `0x0367–0x0369` and the map-module delta; reach the parser.
   - [x] `0x2e0xxxx` is an import-thunk area, not an export module; 86
     thunks, IAT `0x1ab9000`, import names at `0x1708000`.
   - [x] MAL chain (`OBJ_DiscInfo_readDiscVol` → `MAL_DataVol_getOffset` →
     `getSize`) and NaviStateCC fd layer anchored.
   - [x] Import descriptor `FirstThunk=0x1ab9000`: absent (pre-bound IAT);
     86 thunks unnamed.
   - [x] NaviStateCC is a COM DLL, not a flat library; fd layer are COM
     methods behind a load-time vtable.
   - [x] The 175-method vtable is **iPodCC**, not NaviStateCC; `0x2e00eb8`
     is a shared COM helper. No NaviStateCC vtable exists as a contiguous
     pointer table.
   - [x] `0x6faf30` is a Bluetooth/OPP handler, not the reader.
   - [x] Initializer `0xc43430` found; `0x1d0f8a8` never written by ROM;
     no static vtable contains the fd methods.
   - [x] `0x171e9e8` is a type-library helper, not a vtable builder; no
     static template; **static closed for the reader**.
   - [x] Dynamic guide written: `docs/research/dynamic-break-guide.md`.
   - [ ] **No hardware access currently (2026-11-05):** dynamic break, SD bus
     and card matrices deferred.
   - [ ] Prepare a hardware kit (JTAG/serial + card matrix) for later.
   - [ ] While waiting: build the compiler/offline validators (`tools/build.py`,
     profile validator, round-trip checks).
   - [x] `tools/ind_mutate.py` generates 8 `.ind` variants for the spare-card
     matrix.
   - [x] `hddinfo_variants.py` now emits 89 length-preserving variants;
     `solve_data_delta.py` added.
   - [ ] Firmware RE is the **primary path** (decision 2026-11-05): continue
     via the CE ROM segment recovery in P7 (do not resume global-VA/delta
     guessing); until the readers define the data contract. No timebox.
   - [ ] Relative call-graph tracing from extracted CE ROM modules (P7); `0xc438a4`
     is retracted as an opener and must not be used as an anchor.
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
- [x] **L1 — whole-card validator:** `tools/cardcheck.py` checks MBR/FAT,
  `DRSTR` tree, sizes, `.ind` offsets, zlib decode, tile inventory, `MMAIN`
  table, `HDD_INFO` copy and `CMP.LST`. Stable exit code + JSON report.
- [x] **L2 — semantic/golden:** `tools/l2check.py` checks `DRSTR` and
  `.cmp` preserved round-trips, five target tile rebuilds, golden geometry
  digests, a one-vertex tile mutation and a POI rename. Golden profile:
  `tools/golden/eu2011.json`.
  - [x] Cross-year L2 for full 2014/2016 roots (`--no-golden
    --ignore-dump-artifacts`); unchanged dense tile uses preserved layout.
  - [x] Unified cross-year wrapper `tools/verify.py` (auto-detects year/flags;
    2019 returns `UNSUPPORTED`).
  - [ ] Optional per-year golden profiles.
  - [ ] Optional OSM comparison remains in `tools/ze0-viewer/compare_osm.py`.
- [ ] **L3 — function-level SH-4 emulation (complete harness).**
  Design: [`docs/research/l3-ghidra.md`](docs/research/l3-ghidra.md).
  - [ ] Locate the `CMP.LST`/map-path opener, `.cmp`/`.ind` reader, `DRSTR`
    parser and tile reader by relative call-graph tracing.
  - [ ] Build a headless Ghidra P-code harness with a documented memory map.
  - [ ] Stub WinCE file I/O (`CreateFile`, `ReadFile`, `SetFilePointer`,
    `CloseHandle`), allocator, `memset`/`memcpy` and `OSM_Printf`/`OSM_LogMsg`.
  - [ ] Add the test corpus: factory, no-op rebuild, recompressed, POI rename,
    corrupted `.ind`, truncated `.cmp`, factory/generated tile, `DRSTR`
    variants, `HDD_INFO` variants.
  - [ ] Compare accept/reject and normalised output with the Python readers.
  - [ ] Require one generated `.cmp` and one generated tile to be accepted by
    the firmware reader.
  - [ ] Record every run as an `EXP-...`; mark un-runnable functions `UNKNOWN`
    with the exact blocker.
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

## P7 — firmware recovery via standard CE ROM format

Do not continue the old global-VA/delta guessing. Use the Clarion wrapper’s
standard Windows CE ROM segment header instead.

- [x] Extract the firmware segment starting at image offset `0x00200200`
  (ECEC at `+0x40`, `pTOC = 0x8e232978`, size `0x01751978`) with
  `tools/ce_rom_parse.py` (149 modules, 1 file, SH-4; key modules recovered).
- [ ] Validate the extracted TOC: module count, file count, `physfirst/physlast`,
  copy entries, and module names (`Navi.exe`, `Navi*CC.dll`, `OBJDLL`,
  `STDDLL`).
- [ ] Reconstruct each module as a PE for Ghidra and record file/VA bases.
- [ ] Locate the `.cmp`/`.ind` reader, `DRSTR001.DAT` parser, tile reader and
  `CMP.LST` path builder in the extracted modules.
- [ ] Locate the map-code comparator and the `HDD_INFO` open/split/parse path.
- [ ] Build L3 function-level emulation for at least one reader, with mock
  WinCE file I/O and a fixed corpus.
- [ ] Add reproducible firmware-analysis scripts to `tools/` instead of ad-hoc
  `/tmp` scripts; record commands in `EXP-...`.

## P8 — documentation and claim hygiene

- [ ] Correct stale firmware claims:
  - `claims.md` C-068 and C-182 (`0xc438a4` as `CMP.LST` opener),
  - `roadmap.md` reader-path row,
  - TODO entries that say static VA recovery is still the active route.
- [ ] Mark old VA/delta experiments as superseded by the CE ROM-segment
  recovery path.
- [ ] Add an experiment record for the ECEC/pTOC recovery and any extracted
  module analysis.
- [ ] Keep `claims.md` as the single source of truth when correcting hypotheses.

## P9 — narrow OSM compiler vertical slice

Use `tools/ze0-viewer/vendor/osm2clarion` as the base rather than reimplementing
its tile writer.

- [ ] Select one target tile and one profile (`dolnoslaskie-detail` or a tiny
  test profile).
- [ ] Generate roads/coast/landuse for that tile from OSM.
- [ ] Preserve factory REFER/ADDRE/POI data in the first slice.
- [ ] Rebuild `DRSTR001.DAT` and `MMAIN001.DAT`.
- [ ] Run L1 and L2 on the rebuilt card.
- [ ] Implement a ZE0 section-4 encoder or explicitly document why section 4 is
  preserved verbatim.
- [ ] Decode and validate road classes, names, one-way and speed attributes.
- [ ] Decide the address/POI import strategy after the first tile passes.

## P10 — differential and hardware validation

- [ ] Compare 2011/2014/2016 tiles, section 4 and REFER to identify map-code and
  activation-related fields.
- [ ] Prepare a spare-card matrix: whole-card clone, no-op recompression, then
  same-length POI rename.
- [ ] Run the `HDD_INFO` variant matrix and record every accepted/rejected case.
- [ ] Record SD lock, map-code and any map-data error behaviour.
- [ ] Keep the original card read-only and test only on spare media.

## P10b — differential follow-ups (2011/2014/2016)

- [ ] `B30R048R`: map the directory/block differences at `0x807`/`0x808` and
  either implement a layout-aware writer or formally adopt the preserved-layout
  fallback for edited dense tiles.
- [ ] Map-code/activation: run the spare-card `HDD_INFO` variant matrix and
  record which lines/fields are accepted or rejected.
- [ ] Section 4: decode the binary fields between the country code and names;
  verify the 20/24/24 record delta; build a ZE0 section-4 encoder.
- [ ] `REFER002`/`ICODE001`: compare region schemas and place-name counts
  across years.
- [ ] Cross-year POI mutation: parameterise the fixture per year (2014
  `POINT001.DAT` page `0x39700`; 2016 `0x3d700`).
- [ ] Add per-year golden profiles only if digest comparison beyond factory
  data is wanted.
- [ ] Decide `TFTBL001` and speech-language packaging scope.

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
