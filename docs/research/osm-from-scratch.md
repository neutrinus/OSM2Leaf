# A map built from OSM from zero (London first)

> **Status:** plan (M5.84, 2026-11-23). Evidence for the state review is
> `EXP-2026-11-23-M5.84-from-scratch-plan`; every row below names the task or
> claim it comes from. Nothing here is validated in a car.

**Question (Marek, 2026-11-23):** we can rename a street and reshape roads
inside the factory tiles, but can we build the tile structure *ourselves*,
without replacing factory pieces one by one? New OSM data will not always fit
the factory's records and blocks.

**Short answer:** not yet for a whole tile. Every OSM result so far
(M5.4, M5.30, M5.74, M8.H71) is a **splice**: the factory tile is the
template, our writer replaces the records of the parcels it touches and keeps
the rest. The container writer for a fresh tile exists
(`tilewriter.py` without `--factory`, `clarion_tile.write_tile`) but writes
roads only, has never been shown on the screen, and its own docstring calls it
"a development artefact, not a unit-ready tile". This page is the path from
the splice to a tile in which no record comes from the factory, tested on the
London start screen of the emulator until touch/GPS can move the map.

## 1. What a tile is, and what we already write

`MAPAL001/BxxRyyR.DAT` = 4 KiB header (strings, level table `0x1ac`, box
table `0x2ac`, section table `0x800`), then per section a table, directories
(32 columns of parcel slots) and record blocks, all 256-byte aligned
([map-tiles.md](../format/map-tiles.md)). Each parcel has an **even** record
(road shapes) and an **odd** record (background polygons + the names section
for street labels). Dense level-1 parcels are split 2 × 2 into four
**sub-records** held in a wide directory row (M5.53).

| Object on the map | Where in the card | Decoded | Writer today | Firmware reader | Best acceptance so far |
| --- | --- | --- | --- | --- | --- |
| Road geometry, level 1 | tile sec 1, even record `0x00fa` | yes (M5.23) | `tilewriter` (M5.4), splice and fresh | MAP_DATA `0x00425f40`, `LOC_map` walk `0x0041f3dc` | **L4**: OSM roads drawn in London (M8.H71) |
| Road geometry, level 2 | tile sec 1 level 2 | yes | `tilewriter --level 2`, splice; defect M5.70 | same path | L2 only |
| Road class / width | even record shape `(layer, cls_hi)` | mechanism yes, OSM mapping provisional | `provisional-v0` table | renderer | L4 shows too many wide roads (M8.H71 O4) |
| Street names, road numbers | odd record names section `1=NAME;2=REF` | yes (M5.7, M4.90) | `tilewriter` names path (M5.7); pipeline runs `--no-names` | renderer | L4 for an in-place rename only (M8.H70) |
| Water, forest, park, river | odd record background block | yes (M4.70, levels 3–5 table) | `tilewriter --background`, one parcel, 3 classes (M5.74) | renderer | L3 mount SAME (M5.74); never on screen |
| Land/urban area, sea, coast | odd record types `0x2b`, `0x12`, `0x07` | types known | none | renderer | — |
| Buildings | no record type found | — | — | — | out of scope (data-coverage.md) |
| Dense parcel sub-records | wide directory rows `0x2n46` | yes (M5.53) | writer **drops** them | slot parser `0x00414dbc`; sub-record use UNKNOWN | — |
| Place names (tile index) | tile sec 4 `0x0009` | framing yes | `section4_places.py` into a factory record (M5.65) | RGD_DATA fetch (M4.40) | L2 |
| Routing graph | tile sec 2 | framing (M5.37) | framing only; M5.57 blocked on M4.40 | RGD_DATA `0x004266ec` | L2 golden |
| Coarse levels 3–6 | `LEV3456R.DAT` | yes, byte-identical rebuild | `lev3456gen` exists; M5.16 blocked on M9.18 | MAP_DATA | L2 |
| Search: places, streets | `LCTBL001` | yes | builder (M5.17), L3 lookup (M5.60) | located | L3 |
| POIs | `REFER001` `POINT` | partly | rename/move (M5.63); new POI M5.82 open | located (M3.11) | L3 (M9.10) |
| Addresses | `ADDRE` | partly | none (M5.18) | located (M3.13) | L3 reader only |
| Manifests | `DRSTR001`, `MMAIN001`, `CMP.LST`, `.ind` | yes | `rebuild_manifests.py` (M5.6) | mount | L3 (M5.56) |

## 2. Where the structures limit us, and where they do not

The fear "OSM will not fit the factory blocks" splits in two.

**Not a limit any more (measured):**

- **Factory block sizes.** A grown record is appended at the end of the tile
  and its slot tag repointed; M8.H71 grew `B48R068R` by 1.85 MB and the card
  boots and draws. FAT relocation is handled (`imgpatch --allow-resize`).
- **File size.** The firmware reads a tile up to the size `DRSTR001.DAT`
  records; `rebuild_manifests.py` writes true sizes (M5.56).

**Real limits (the ones a from-zero writer must respect):**

| # | Limit | Value | Source | Consequence for the writer |
| --- | --- | --- | --- | --- |
| 1 | directory kind bytes in the header level table | factory set per section/level (`0x80 0x90 0x91 0x91 0x91 0x92` …) | M3.31, card-wide merged table | copy as constants; another kind changes the read length for every tile |
| 2 | directory read length | s1 L1 `0x8100`, s1 L2 `0x14100`, s2 L1 `0x2100`, s4 L1 `0x6100` | M3.31 table `0x179c08` | a directory is at most that long: ≤ 31 wide rows at s1 L1 |
| 3 | parcel grid | 32 columns per directory; level boxes from the tile box | map-tiles.md, M5.44 | parcels are fixed; we choose only what goes into each |
| 4 | coordinates inside a parcel | 11 bit, `0..2047` | firmware diagnostics, M4.37 | quantisation per level; simplify (M5.75: 3 m / 12 m) |
| 5 | one even + one odd record per parcel (+ 4 sub-records in a wide row) | — | M5.53 | a parcel with more data than one record can hold must use sub-records |
| 6 | largest record the firmware reads | **UNKNOWN**; factory max seen 18,580 B inflated, road blocks up to 7,472 B compressed | M4.86, M5.75 | **probe it** (M5.92) before planning dense cities |
| 7 | shape point count | `u16`, top bit is a flag at levels 4/5 | map-tiles.md | split long ways |
| 8 | background group count byte | wraps at 256; the layer length is the authority | map-tiles.md | the writer must not rely on the count byte |
| 9 | label width / font | long names not drawn (C-8223); cmap U+0001–U+011F | M8.H70, M4.87 | transliterate (M5.80), shorten |
| 10 | coarse levels | the unit refuses a widened directory (44 L4 / 11 L5 columns) | map-tiles.md | `LEV3456R` is a whole-database rewrite |

The factory's own answer to "does not fit" is limit 5: a dense parcel is cut
2 × 2 into sub-records. Our writer currently throws them away when it writes
a parcel (M5.53). Writing them (M5.93) is how dense London parcels keep their
detail without breaking limit 6.

## 3. The bench: London on the emulator

Until the touch and GPS peers can move the map (separate thread, M8.H33,
M8.H72), the only screen we can compare is the `-M ze0` start screen: central
London, level-1 parcel `(77,923; row 8, col 27)` of `B48R068R`
(M8.H71). Zoom-in already works from the touch peer (`m8c1n-*` screenshots);
zoom-out to level 2 is part of Z6.

The OSM input is the BBBike London extract (`download.bbbike.org`, reachable
from the sandbox; 201,531,314 B on 2026-11-22/23, SHA-256 in the EXP).

Every rung below is decided by four checks, in this order:

- **L1** `cardcheck.py --image` PASS and `imgpatch --check-diff` touches only
  the declared files;
- **L2** `harness.py verify` / `l2check` on the tile, and `--readback` of our
  records against the IMF input;
- **L3** `datask_l3.py mount` at the London position: same reads as the
  factory, slot tables parsed, no read past the end;
- **L4** boot, screenshot after `Pow Off 1st Detect`, compared with the
  factory screenshot of the same position (pixel diff + by-eye notes), and the
  serial log's error set equal to the factory run's (M8.H71 O5).

Screenshots of factory data never go into the repository (SHA-256 only).

## 4. The rungs Z0–Z7

"Z" for *od zera*. Each rung is one or more TODO tasks; a rung is done when
its gate passes, not when the code exists.

| Rung | What the tile contains | Gate (beyond L1/L2) | Task |
| --- | --- | --- | --- |
| **Z0** | plan, tile census, factory baseline screenshot | census numbers in the EXP | M5.84 (this) |
| **Z1** | the factory tile written through **our own layout**: every table, directory, row block and record placed by our writer, nothing copied by position | L3 SAME, **L4 pixel-identical** to factory | M5.85 |
| **Z1b** | provenance tool: how many records / bytes of a tile are factory | negative and positive control | M5.86 |
| **Z2** | an **empty** London tile: container from the spec, no records | boots; the EXP lists what disappears from the screen (which on-screen items come from this tile) | M5.87 |
| **Z3** | roads from OSM, level 1, whole London bbox, in the from-zero container | L4: roads drawn, provenance 0 factory records | M5.88 |
| **Z4** | + background from OSM (water, parks, forest, urban area, rivers) for every London parcel | L4: fills drawn where OSM has them | M5.89 |
| **Z5** | + street names and road numbers, OSM class table checked against the factory's London classes | L4: labels drawn; class diff table | M5.90 |
| **Z6** | + level 2 (zoom out) and section 4 place names | L4 at the zoomed-out screen | M5.91 |
| **Z7** | routing (sec 2), `LEV3456R`, search files | existing tasks M5.57, M5.16, M5.18, M5.82 | — |

**Progress (2026-11-23):** Z1 passed — the re-laid factory tile draws a
pixel-identical screen (M5.85, C-8762). Z2 passed — the empty container is
accepted at L1/L3/L4 and the start screen goes black except the position
mark, so every item on it (fills, roads, street and place labels, shields)
comes from `B48R068R` (M5.87, C-8672/C-8673). Z3 passed — 602 OSM road
records and no factory record are drawn on the start screen (M5.88, C-8684);
an empty odd pair must be `0xffffffff` (C-8682), and records up to 101 KB
(L4) / 156 KB (L3) read without a size limit (C-8685). Z4 passed for areas —
623 OSM background records (water, parks, forest, heath, urban; layers 0/3/7,
types `0xc1..`) are drawn under the roads (M5.89, C-8694); the factory's
urban fill is generalised, so built-up area and line layers are M5.95/M5.96.
Z5 passed for names — OSM street names and place labels are drawn (M5.90,
C-8702/C-8703); shields (M5.97) and the measured class table (M5.98) remain.

Cross-cutting tasks, independent of the rungs:

- **M5.92** — capacity probe: the largest record / shape / point count the
  firmware draws (L3 + L4), with the VA that enforces it (limit 6).
- **M5.93** — sub-record writer: split an over-budget parcel 2 × 2 like the
  factory, and show at L4 that all four quarters are drawn (limit 5).
- **M5.94** — London in numbers: per-parcel OSM bytes at the default
  tolerances against the factory record sizes and the probe limit.

Order: Z1 and M5.94 first (both need only the card and the OSM extract),
M5.86 next to them; Z2 → Z3 → Z4/Z5 in sequence; M5.92 → M5.93 before any
dense parcel is written. Poland (P1, M5.61) reuses the same writer: a
from-zero tile does not depend on which factory parcels exist, which is what
blocks M5.69/M5.70 today.
