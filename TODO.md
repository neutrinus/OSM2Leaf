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

## P1 — finish the map container description

- [ ] Decode `MMAIN001.DAT`: what do the 4,096 bytes describe? Are there
  pointers into other databases?
- [ ] Decode the `0x180` descriptor block in the common header field by field.
- [ ] Determine the `DRSTR001.DAT` leading `u32` meaning (47 in the EU image).
- [ ] Confirm whether entry `value` for tiles is the total decompressed size.
- [ ] Decode `RDSTM001` and `LCTBL001`: record types, string table, road
  attributes.
- [ ] Decode `REFER001`/`REFER002` record formats: addresses, POIs,
  coordinates, street names, `MESHID`/`POI`/`Pre`/`Next` relationships.
- [ ] Decode `MMAIN001.DAT` + `CMP.LST` update semantics.

## P2 — tiles and geography

- [ ] Determine the `BxxRyyR` naming convention and the tile-to-lat/lon
  mapping. Start from known map coverage (Europe) and correlate tile extents.
- [ ] Decode the tile descriptor area at `0x2b0` and the LOD-like table at
  `0x1ac`.
- [ ] Decode the zlib stream boundaries and the record format inside a
  decompressed tile stream.
- [ ] Explain `LEV3456R.DAT` (76 MB) and its relationship to per-tile files.
- [ ] Build a small standalone tile viewer/exporter.

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

## P4 — writer / round-trip

- [ ] Implement a `.cmp`/`.ind` **writer** and verify byte-identical output
  for unchanged files (or document which bytes differ and why).
- [ ] Implement a `DRSTR001.DAT` writer and verify re-parse equality.
- [ ] Implement a tile container writer for an unchanged tile.
- [ ] Determine all checksums/signatures and where they are stored.
- [ ] Build a minimal synthetic change (e.g. one renamed POI) and validate it
  offline by re-reading with our own tools.

## P5 — OSM pipeline

- [ ] Define the intermediate format (roads, nodes, names, addresses, POIs).
- [ ] Import OSM extract for Dolnośląskie.
- [ ] Map OSM tags to the unit's road classes/attributes.
- [ ] Generate a first synthetic dataset at the unit's tile granularity.
- [ ] Compare generated data with the factory data for the same area.

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
