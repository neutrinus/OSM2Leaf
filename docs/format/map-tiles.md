# `MAPAL001` map tiles

> **Evidence status:** the tile grid and coordinate encoding are `VERIFIED`
> on the EU 2011 image; the stream/record layout is `OBSERVED`; the `0x1ac`
> and `0x2b0` descriptor semantics remain `HYPOTHESIS`/`UNKNOWN`.

`MAPAL001/` holds the map geometry. In the EU 2011 image it contains:

- 45 files named `BxxRyyR.DAT` (plus `LEV3456R.DAT`)
- `LEV3456R.DAT` (76,066,304 bytes) — much larger than every other tile

## Verified tile grid

`B` and `R` in the filename are **hexadecimal**. One grid unit is **1° of
longitude** and **2/3° of latitude**; a tile is 8 × 8 units:

```
lat_min = int(B, 16) * 2/3
lat_max = lat_min + 8 * 2/3      # 5.333°
lon_max = 108 - int(R, 16)
lon_min = lon_max - 8            # 8°
```

Examples:

| Tile | lat | lon | Size |
| --- | --- | --- | --: |
| `B48R060R` | 48.00–53.33 °N | 4–12 °E (Germany/Benelux/Alps) | 436.0 MB |
| `B40R060R` | 42.67–48.00 °N | 4–12 °E (France/Alps) | 359.4 MB |
| `B48R058R` | 48.00–53.33 °N | 12–20 °E (E Germany/Poland) | 289.3 MB |
| `B38R070R` | 37.33–42.67 °N | −12…−4 °E (Iberia/Atlantic) | 165.4 MB |
| `B68R058R` | 69.33–74.67 °N | 12–20 °E (north Norway) | 1.57 MB |
| `B58R070R` | 58.67–64.00 °N | −12…−4 °E (Norwegian Sea) | 0.11 MB |

The 45 files occupy a **63-cell** addressable lattice (rows `B28`–`B68`,
9 values; columns `R048`–`R078`, 7 values, step 8); 45 cells exist as files and
18 are absent (sea/empty), so lattice-derived counts are upper bounds (C-566).
The smallest tiles are sea;
`R = 0x78` (lon −20…−12) exists only at `B28`/`B30`, i.e. Atlantic coast off
Morocco, nowhere on land.

The same grid is used by `COORD001` (see
[coord-zcode-icode.md](coord-zcode-icode.md)), which is independent
confirmation of the rule.

**Which tiles a region needs (P1 census, 2026-11-18).** A profile's
`region.bbox` selects tiles by this grid, not by the 45-file inventory.
`tools/mesh_grid.py list MAPAL001` prints one lat/lon box per tile (45 rows on
the EU 2011 card) and `cell BxxRyyR` prints one; `python3 tools/mesh_grid.py
cover PROFILE [MAPAL001]` (M5.46) is the census that classifies every lattice
tile `contained`/`intersects`/`outside` against a profile. Against
`profiles/dolnoslaskie-test.json` (`14.0–17.9 E, 49.9–51.9 N`) it gives
`contained=1` (`B48R058R`), `intersects=0`, `outside=62` — no edge tile.
`contained` means the whole region box lies inside the tile, so P1's
Dolnośląskie card is that one factory tile **copied verbatim**, not spliced.
The same census on `profiles/poland-full.json` gives `contained=0`,
`intersects=4` (`B48R050R`, `B48R058R`, `B50R050R`, `B50R058R`), `outside=59`.
Counts are from `mesh_grid.py cover … /home/marek/projekty/leafre-work/m5.29-factory-root/MAPAL001`,
not from a card; EXP-2026-11-18-M5.46-containment has the per-row output and
`cover --all` for the full 63-row table.

**What a region card is at each rung.** The ladder (P0, P1, and the P2 routing
placeholder) and the command that decides each rung — with its exact expected
output — live in [`card-ladder.md`](card-ladder.md). This page owns the tile
grid and the tile census; the ladder page owns the gate per rung.

## Coordinate encoding (from `COORD001`)

`COORD001` stores per-region bounding boxes in grid units at 1/128 resolution:

```
lat = (x - 32768) / 192        # 192 = 128 * 3/2
lon = (y - 52742) / 128
```

A least-squares fit over 33 regions gives ~0.03° latitude / ~0.07° longitude
rms. The asymmetric divisors are exactly the grid: 1 grid unit = 1° lon =
2/3° lat, stored at 1/128.

## File structure

Every tile starts with the common 512-byte header
([file-header.md](file-header.md)). After it:

- `0x200` .. ~`0x2b0`: zeros
- ~`0x2b0`: a small descriptor/record area
- up to ~`0x5200`: mostly zeros and sparse records; the first zlib stream
  usually begins exactly at `0x5200` (`LEV3456R.DAT`: `0xbe00`)
- after that: many small **independent zlib streams**, each with a normal
  `78 9c` header

Example `B28R070R.DAT` (1,083,392 bytes):

```
0x5200  zlib stream -> 204 bytes
0x5300  zlib stream -> 296 bytes
0x5370  zlib stream -> 384 bytes
0x5450  zlib stream -> 404 bytes
0x5600  zlib stream -> 300 bytes
...
```

Example `LEV3456R.DAT`:

```
0xbe00  zlib stream -> 548 bytes
0xbf00  zlib stream -> 2224 bytes
0xc474  zlib stream -> 484 bytes
...
```

The decompressed blocks look like small structured records, not raster
imagery. The first bytes of a decoded stream are typically:

```
95 1f c8 02 00 fa ff ff ff ff 00 00 00 00 ff ff 00 00 00 0b 00 28 ...
```

## Descriptor tables (`0x1ac` and `0x2ac`)

Both are the same container:

```
00 | n_tables | { table_id, n_entries, entries... } | 00
```

- `0x1ac`: entries are `(level, kind, u16 count)`; this is the
  level-of-detail table.
- `0x2ac`: entries are 10 bytes
  `(level, flags, i16 lat_top, i16 lat_bottom, i16 lon_left, i16 lon_right)`
  in **signed arc-minutes**.

`B28R070R.DAT` `0x2ac`:

```
02 01 02 02 00 07 80 06 95 fd 30 fd ce 01
00 07 80 06 98 fd 30 fd ce 02
02 02 00 07 80 07 17 fd 30 fd a1 01
00 07 80 07 1a fd 30 fd 9f
```

`0x0780` = 1920′ = 32.00°, `0x0695` = 1685′ = 28.08°, `0xfd30` = −720′ =
−12.00°, `0xfdce` = −562′ = −9.37°. Every box lies inside the tile rectangle
computed from the filename (0 violations over all 45 tiles).

## Stream prefix = absolute coordinates

Every zlib stream starts with a 6-byte key:

```
u16 BE A = 32768 + lat * 192      # 1024 units per 5.333° row
u16 BE B = 52736 + lon * 128      # 1024 units per 8° column
u16 BE section_tag
```

- Both axes quantise to exactly 1024 units per grid cell; 1 unit ≈ 600 m.
- The tag is a table selector: `0x00fa` → table 1, `0x0000` → table 2,
  `0x0009`/`0x000a` → table 4. The section count equals `n_tables` in 46/46
  files.
- 3,497,371 streams decoded with zero exceptions.
- `COORD001` uses longitude origin `52742`; the stream prefix uses `52736`.
  The 6-unit difference (~0.047°) is not yet explained.
- Firmware diagnostics impose a runtime intra-mesh bound of **`0..2047`**
  (11-bit) and validate `MESHMAX_LEV1`. This is not a storage rule: raw
  `REFER001` bodies contain `u16` values above 2047, so coordinates are
  bit-packed/masked rather than plain `u16`.

## Stream layout

- First stream at `0x5200` (ordinary tiles) or `0xbe00` (`LEV3456R.DAT`).
- Streams are back-to-back with 0–3 bytes of padding (93 % of gaps).
- Number of streams per tile: 3,769–216,332.
- Block order is monotone in `A` and `B`.
- **Negative result:** there is no `u32` offset table in the header; the
  streams are effectively a random-access page array addressed by `(A,B,tag)`.

## Payload structure

Each stream is one ~600 m block: a 6-byte key plus a body of 16-bit
big-endian words (`0xffff` = empty).

- In `B30R048R.DAT`, 2,374 of 3,769 payloads are exactly 448 bytes and only
  13 distinct bodies exist (2,256 are byte-identical apart from the key).
  These are empty/default pages; they compress to ~77 bytes.
- The remaining ~1 % (128/132/176/188/592 bytes…) carry real data with an
  undecoded grammar. Recurring constants: `20 1e`, `07 ff`, separator
  `45 xx 12`.
- The `(A,B)` values occupy a 4-unit sub-lattice (low 2 bits look like a
  4-way quadrant), suggesting a quadtree address.

## ZE0-specific record structure (viewer-verified)

The `osm2clarion` QY8x tools need four ZE0 fixes (see
[`tools/ze0-viewer/`](../../tools/ze0-viewer/README.md)):

1. zlib streams start with `78 9c`; upstream hardcodes `58 85`.
2. Background record kind is `0x00fa` at both levels; the **even/odd record
   pair** separates road-shape (even) from background (odd).
3. Directory slot-body size follows the directory kind: section-2 level-2 is
   `0x2046` with 512-byte bodies, not 256.
4. Empty slots may use `0x7fffffff` as well as `0xffffffff`.

The bbox table is fixed at `0x2ac`. ZE0 has 45 grid tiles + `LEV3456R`, not
the 52 of the QY8x family. There is no layer-11 coastline; the coast is the
sea-polygon edge.

Byte-identical rebuilds with the patched harness:

| Tile | Result |
| --- | --- |
| `B58R070R.DAT` | byte-identical; 459/459 background records |
| `B28R070R.DAT` | byte-identical; 7,103/7,103 background, 455/455 graph |
| `B30R060R.DAT` | byte-identical; 8,465/8,465 background, 37/37 graph |
| `LEV3456R.DAT` | byte-identical; level 5 decoded and rebuilt exactly (see below) |

### Dense tiles and roads (round 2)

All five target tiles now rebuild **byte-identically**, including the dense
`B30R048R` (1,358,592 B). The missing container pieces were:

- mask the `0x80000000` pair flag before computing a compressed length;
- preserve raw slot tails (e.g. `B30R048` slot 21 at body `+0xE8`);
- accept `0x7fffffff` empty tags at level 1;
- the EU 2011 section-1 level-1 `0x2n46` "kinds" are **not** a 512-byte-row
  directory with an `n*512`-byte tail (M5.22's reading, C-2810–C-2812,
  superseded). Header word 0 is the directory size in `u16` words, and
  `0x2n46` is a `0x2046` directory with **n wide rows** (M5.53,
  C-5270–C-5273, `tools/s1_wide_dir.py`):

  | Row | Body | Per column (32 columns) |
  | --- | --: | --- |
  | narrow | 512 B | even `(u32 ln, u32 X)`, odd `(u32 ln, u32 X)` |
  | wide | 1,024 B | even (8 B), 4 x `u16` sub-record sizes, 4 x `u16` sub-record inflated sizes, odd (8 B) |

  Bit 31 of a row's first body word marks a wide row (`0xffffffff` when
  column 0 is empty; never set in a narrow row). In a wide row bit 31 of the
  even `ln` is also set on every column with sub-records. The row block holds,
  per column, `even, sub0..sub3, odd`, each `2 * ln` bytes (zlib, zero-padded
  to a word); `(0, 0)` is an empty sub-record. The sub-records are a 2 x 2
  split of the parcel: their parcel codes replace the low nibble `0xc | r` of
  the parent code with `(half << 2) | r`. On `B48R058R` all 68 section-1
  directories parse this way (139,510 records, every one a whole zlib stream of
  its declared size, 0 overlapping row blocks). `tilewriter` splices into
  `0x2146` (M5.53) and `0x2246`–`0x2946` (M5.54) through this model: a written
  parcel loses its sub-records, and when no wide row keeps one the whole
  directory turns into `0x2046` (a partial splice keeps the kind). The row-model
  kinds `0x2a46` and up (seen outside the P1 bbox) are still preserved. At L3 the firmware reads a
  spliced directory with the slot-table parser `0x00414dbc`, loading the
  `0x2046` length (C-5546); what it does with the sub-records is UNKNOWN
  (record/sub-record decoding not covered, rule 13);
- copy the 55 KiB unreferenced gap at `0x9a520..0xa7d00` verbatim.

Road-shape records (section 1, even pair, `w2=0x00fa`) are decoded:

| Tile | Even records | Shapes | Points |
| --- | --: | --: | --: |
| `B30R060R` | 37 | 784 | 8,923 |
| `B30R048R` | 188 | 6,270 | 84,470 |

**Level-1 (grid tile) header fields, confirmed** (EXP-2026-11-08-M5.23,
C-2660–C-2663): the 22-word header (big-endian `u16`, 0-based) carries
`w[2]=0x00fa`, and **`w[20]` is the per-record ISO 3166-1 numeric country
code** with **`w[19]=0`** in factory data (45,887 EU level-1 records across 3
tiles; a cross-border tile varies country per record, e.g. 616 PL / 276 DE /
203 CZ / 40 AT / 703 SK / 348 HU). Per-shape class is encoded as
`(draw layer, cls_hi) = (layer table slot, w[p+2]>>12)`, matching
`fa_encode.parse_record`/`shape_words` (C-2661); the OSM→`(layer,cls_hi)` value
mapping is **provisional/incomplete** (factory contains unmapped values such as
`(6,7),(6,6),(7,2),(0,10),(0,12)`; global semantics M5.3/M4.17, C-2662). The
level-5 `LEV3456R` record layout (below) uses different header semantics for
`w[19]/w[20]`.

`LEV3456R` level 6 is decoded: no count word, table at word 11 with 26
`(offset, point-count)` pairs (156 features). Coarse levels 3–5 rebuild with
0 failures; 1,722 opaque records are preserved verbatim.

### Section 4, road names and streaming

Section 4 is a per-parcel **administrative/place-name index**, not geometry.
(M4.40, L3: it is also what the router's `RGD_DATA` request fetches, and the records it served hold
signpost destinations and road numbers, e.g. `0=POZNAN:KALISZ:(36):RAWICZ`; header word 6 is the
name text's word offset and word 7 its length in words — see
[Which section each request kind fetches](#which-section-each-request-kind-fetches-m440-l3-eu2011-build-a), C-5925.)
`B30R048R` has 20 records / 68 names; record word 2 = `0x0009`, word 8 = ISO
3166 numeric country (300 = Greece). Names are `0=NAME` strings (`RODOS`,
`LINDOS`, `PARALIP AFANTOU`, …). `ze0_section4.py` emits GeoJSON points.

#### Section 4 grammar

> **Status:** the zlib framing and the fields at `0x00`/`0x02`/`0x04`/`0x10`
> are `OBSERVED`; the binary span between `0x06` and `0x0f` and the name-list
> placement are `UNKNOWN`. There is still no ZE0 section-4 encoder.

A section-4 payload is a sequence of independent zlib streams, one record per
stream, like every other tile stream. A single decompressed record may also be
supplied as plain bytes. There is no record-length field. Record sizes observed
so far are 84–684 bytes.

Documented per-record offsets (big-endian):

| Offset | Size | Field | Status |
| --: | --: | --- | --- |
| `0x00` | u16 | parcel word 0 (level-1 code) | OBSERVED |
| `0x02` | u16 | parcel word 1 (level-1 code) | OBSERVED |
| `0x04` | u16 | record type, `0x0009` | OBSERVED |
| `0x06` | 10 B | unexplained | UNKNOWN |
| `0x10` | u16 | ISO 3166 numeric country (`0x012c` = 300 = Greece) | VERIFIED |
| `0x12` | … | unexplained binary, then the name list | UNKNOWN / OBSERVED |

Names are `d=TEXT` with a one-digit prefix (`0=` and `1=` observed), normally
NUL-terminated; adjacent names sometimes omit the NUL
(`LINDOS0=RODOS`). Text is ASCII or Latin-1; valid UTF-8 is also accepted. The
name-list start offset, its terminator rule and any count/length prefix are
**not** mapped. The only documented u32 view is the parcel code at `0x00`
(two u16 words); no other `u32` offset is interpreted. `tools/section4.py`
prints every non-documented span as hex instead of guessing.

**HYPOTHESIS:** the undocumented words at `0x06..0x0f` locate or count the name
list (offset/count/length); the tool deliberately does not use them.

**Reference case.** `B30R048R.DAT` section 4 (directory kind `0x1146`,
256-byte bodies, section type `0x93`):

| Year | Records | Names | Record delta vs 2011 |
| --- | --: | --: | --: |
| 2011 | 20 | 68 | — |
| 2014 | 24 | 126 | +4 |
| 2016 | 24 | 129 | +4 |

This is `OBSERVED` reference data from `EXP-2026-11-05-32` (claim C-126),
counted with the viewer's `0=` splitter. The record counts (20/24/24) are
the stable part; a stricter name decoder may change the 68/126/129 name
counts. It is not a claim that every year parses identically.

**Verbatim-preservation rule.** An unchanged tile copies the original
section-4 zlib streams byte-for-byte. An edited tile must also preserve the
whole section-4 payload verbatim, because only the documented fields above can
be rebuilt. `tools/section4.py encode build` rewrites those fields and refuses
with exit 3 whenever names, unknown binary or a missing opaque map would force
it to invent bytes; `encode preserve` is the default for unchanged tiles.

```bash
python3 tools/section4.py parse PAYLOAD --json-out model.json
python3 tools/section4.py encode preserve model.json payload.out
python3 tools/section4.py verify PAYLOAD
```

Road names: shape header word 4 is the name offset in the **odd partner
record's** names section. `B30R060R` has 297/1,195 named lines; `B30R048R`
1,972/10,667. Style bits are raw; one-way/speed mapping is a **hypothesis**
(`0x201e` two-way, `0x001e` ferry).

Streaming decoder: `B48R060R` (436 MB) → 2,710,087 features, ~40 s, 242 MB
RSS. `harness.py compare-tiles FACTORY BUILT` gives **ZERO DIFF** on an
unchanged copy and `DIFFERS` on a one-vertex mutation.

Known limits:

- section-4 binary fields between country and names are not fully mapped; no
  ZE0 section-4 encoder;
- one-way/speed mapping needs validation against a known street/sign;
- streaming mode does not attach road names yet;
- `RDSTM001`/`LCTBL001` cross-reference is still unresolved — use
  [`rdstm.md`](rdstm.md), not the viewer's incomplete negative.

## `LEV3456R.DAT`: coarse levels 3–5

`LEV3456R.DAT` is the **whole-database** coarse file. Section 1 holds levels 6,
5, 4 and 3 (no levels 1–2), section 2 holds levels 5 and 4 (the router graph).
One level is one grid over the whole database extent (lat 21.33–80 °N,
lon −20–68 °E in the 2011 build), not one file per `BxxRyyR` cell. Everything
below is `VERIFIED` on the EU 2011 file
(`MAPAL001/LEV3456R.DAT`, 76,066,304 B, SHA-256
`08a584feacf049cc39260ff29f742c3dcf1b53059cb98bd3e9798e7ab819df35`) with
`tools/lev3456.py` unless marked otherwise.

### Directory geometry

| Level | Directories | Grid | Parcel | Pairs per row | Slot body | Type |
| --- | --- | --- | --- | --- | --- | --- |
| 3 | 45 (one per cell) | 16 × 16 | 30′ × 20′ | 32 (16 columns × 2) | 256 B | `0x91` |
| 4 | 1 | 44 × 44 | 2° × 4/3° | 88 (44 columns × 2) | 704 B | `0x91` |
| 5 | 1 | 11 × 11 | 8° × 16/3° | 11 | 88 B | `0x90` |
| 6 | 1 | 1 × 1 | whole database | 1 | raw | `0x80` |

A directory head is six big-endian `u16`: `size/2, rows, cols, y, x, typ`,
where `x` is stored as `x0 − 1024`. Rows are at `y = 1.5 × lat` and columns at
`x = lon + 924`, so the coarse grid is `y 32..120`, `x 904..992`. Each row is a
`u32` block address (`0xffffffff` when the row is empty) and one
`(compressed words, plain words)` pair per record slot. Level 6 is one raw
record (not zlib) and is preserved verbatim.

**Placing a point (M5.59).** In the unit the head stores, a point is
`y = 1.5 × lat`, `x = lon − 100` (the signed head `x`). A directory holds it
when `head_y ≤ y < head_y + rows × step` and `head_x ≤ x < head_x + cols ×
step`, with `step` 0.5 (level 3), 2 (level 4), 8 (level 5); the parcel is
`row = ⌊(y − head_y) / step⌋`, `col = ⌊(x − head_x) / step⌋` and the stored
11-bit point is the fraction inside the parcel × 2048. Krotoszyn (51.70 N
17.45 E) is level-3 directory `(72, −88)` (index 24 on the EU 2011 card), row
11, col 10. The record header `(w0, w1)` is the parcel code of the row below
(C-2805) in half units with low nibble 3/4/5 for the level; it fits every
section-1 record of levels 3, 4 and 5 of the EU 2011 file (13,142 of 13,142;
`python3 tools/lev3456gen.py codes`, C-6106).

### Splice semantics and the size consequence (M5.45)

`tools/tilewriter.py:splice_factory` patches a factory tile in place where it
can and appends where it cannot. For each written directory row it rebuilds the
slot body and block from the parsed records and applies the first matching
rule, in this order:

1. **unchanged** — the rebuilt block is byte-identical to the block already at
   the slot's tag: the block gets no write, only the slot body is rewritten
   (`container.unchanged`). This reports a repeated splice as "no write" and is
   the only branch that leaves a shared block untouched. Before M5.45 a repeat
   fell through to rule 2 and rewrote the same blocks in place (the size did
   not grow then either).
2. **in place** — the slot owns the block, the new block fits the old one, and
   the bytes at that offset are still the old block: it overwrites the block
   and zeroes the rest of the old span.
3. **append** — otherwise (block grew, slot unowned, or a shared/aliased
   block): the block is written at the next 256-byte boundary, the slot tag is
   repointed, and the old block is left behind
   (`container.superseded_bytes` counts it).

The consequence is that tile size is not a function of content alone: a tile
whose directory has no room left cannot be updated in place, so every splice
that changes a block there appends the new block and orphans the old one. A
directory's slot blocks are disjoint from the directory container (the slot
tags point past it), so the "free room" a row needs is in the appended region,
not next to the slot table. Measured on `B48R058R` (EXP-2026-11-18-M5.45): the
M5.34 full-directory splice appends 32 blocks and keeps 1,789,864 B of
superseded factory blocks, +4,671,350 B over factory; the *same input* over the
already-spliced tile keeps all 32 blocks (`unchanged=32`) and adds 0 B, at any
repeat — the append is once per changed block, not once per run.

### Level-2 directory grid (M5.44)

Level 1 and level 2 share one directory *identity*: a level-2 directory's
header `(y, x)` is exactly a level-1 directory's, and `--parcel Y,X` names the
same mesh pair at both levels. What differs is the **directory span** and the
**parcel grid inside it**:

| Level | Directory span | Parcel grid | Parcel size | Pairs per row | Slot body | Header `x` field |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 × 1 mesh (1° × 2/3°) | 32 × 32 | 1/32° × (2/3)/32° | 32 (64 pair slots) | 512 B | `x0 − 1024` |
| 2 | 4 × 4 meshes (4° × 8/3°) | **32 × 32** | 1/8° × (2/3)/8° | 32 (64 pair slots) | 512 B | `x0 − 1024` |

At level 2 the directory's 4 × 4-mesh box is filled by the **same 32 × 32**
parcel grid, so a level-2 parcel is four times wider and four times taller than
a level-1 parcel (1/8° × 1/12° ≈ 8.4 km × 7.4 km at 51 °N). This is *not* a
4-mesh × 4-mesh parcel grid: `clarion_bg.LEVELS[2]` has `rows = cols = 32`, and
the 32 row blocks × 32 columns are 1,024 parcels, each written as a road
record in even pair `2·col` and a background partner in odd pair `2·col + 1`.

The factory tile confirms both halves directly. In `MAPAL001/B48R058R.DAT`
the four section-1 level-2 directories each carry a box in the level table
(the `y1, y0, x0, x1` six-word directory group that `clarion_tile.read_tile`
keeps as `directory["box"]`; `x0`/`x1` are stored with the same `−1024` bias
as the header `x`). Each box is exactly 4 meshes — e.g. `(76,940)` is
`y 76..80`, `x 940..944`, i.e. `lon 16.0..20.0`, `lat 50.6667..53.3333` — and
every **filled** pair slot in a directory (2,046 of 2,048 in `(76,940)`;
2,030–2,047 across the four) holds a record whose `w0/w1`
is `clarion_bg.parcel_code(2, y0·8 + row, x0·8 + col)`: `(76,940)` slot 0
pair 0 is `0xa60f/0xd602` and pair 2 (col 1) is `0xa60f/0xd612`, slot 31 pair
0 is `0xa7ff/0xd602`, so the row/col indices run `0..31`, not `0..7`
(`EXP-2026-11-18-M5.44-level2`). The box the level table declares is therefore
the union of a 32 × 32 parcel grid of 1/8° × (2/3)/8° parcels, which is the
same grid `clarion_bg.parcel_geo` `(level 2, row, col)` walks:
`parcel_geo(2, 76, 940, 0, 0)` is `16.0, 50.66667` and parcel `(31,31)` ends at
`20.0, 53.3333`.

Consequently `tilewriter.parcel_of` must use `LEVELS[level]["cols"/"rows"]`
(32 at both levels) to clamp `col`/`row`, not `cols // DIR_MESHES[level]` (which
gives 8 at level 2 and would press every point east of `17°` into column 7). The
directory *placement* still uses `DIR_MESHES[level]` (1 at level 1, 4 at level
2) to snap `(y0, x0)` to the directory origin. `parcel_census.directory_bbox`
likewise takes the union of the full `LEVELS[level]` grid; its old
`rows // DIR_MESHES[level]` gave an 8 × 8 grid and a 1/4-size box (M5.44).

### What the three levels contain

| Level | Records | Road-shape records | Background records | Road shapes | Background shapes | Points (road / background) |
| --- | --: | --: | --: | --: | --: | --: |
| 3 | 12,059 | 4,882 | 7,177 | 888,736 | 275,957 decoded | 3,349,300 / 13,492,596 |
| 4 | 1,021 | 380 | 641 | 227,934 | 52,964 | 814,503 / 3,938,982 |
| 5 | 62 | 34 road blocks | 62 | 27,951 | 16,306 | 94,151 / 324,720 |

- **Level 3 (2 and 4 km).** Even slot = one **road-shape record** (kind
  `0x00fa`, eleven layer pairs, geometry at w7/w8, classes 3–7 plus ferries).
  Odd slot = one **background record** (sea, coast, rivers, land/area polygons,
  point labels, and a name/point index). 1,677 of the 7,177 background records
  carry a point-index section at w15/w16 that is not decoded here and is
  preserved verbatim; the shape counts above exclude them. The geometry
  pointer pair (`w9/w10` normally, `w7/w8` for a road-only record; see
  `bg_slot`) declares a `geo_len`-unit region; the layer table is bounded by
  `geo_len`. In three `B30R048R` level-1 records (dir `0x2ad00`, slots
  6/8/11) the bytes immediately past the 26-unit geometry region are the start
  of the names section (`w11 = geo_off + geo_len`), so an unbounded table scan
  misreads names bytes as table entries; the bounded read accepts and rebuilds
  them (`harness.py` reports `parse refused 0` on `B30R048R`; C-2860–C-2863,
  EXP-2026-11-08-M9.23-b30r048r-opaque).
- **Level 4 (10 and 16 km).** Same split: 380 even-slot road records and 641
  odd-slot background records. Background shapes use the same group grammar as
  level 5; road records use the same shape grammar as level 5's road block.
- **Level 5 (64 km).** One record per non-empty 8° × 16/3° parcel (62 of the
  121 slots). A record holds a background block **and**, in 34 cases, a road
  block in the same record; 48 records carry a level-5 names section.

Background shape types. Most level-3 types use `0xa..` and most level-4/5 types
`0x8..`, but the high nibble is not a strict level selector: level 3 also has
16,471 `0x800c`, 6 `0x8026` and 21 `0x8049` shapes. The low byte is the class.

| Type | Meaning | Level 5 | Level 4 | Level 3 |
| --- | --- | --: | --: | --: |
| `0x..07` | coastline | 439 | 597 | 953 |
| `0x..08/09` | island/coast variant (UNKNOWN) | 1,142 | 8,364 | 8,565 |
| `0x..0c` | point label anchor | 176 | 1,247 | 16,471 + 1,986 (`0xa00c`) |
| `0x..10` | land/area polygon (UNKNOWN) | 10,795 | 8,824 | 15,977 |
| `0x..11` | unknown area | 254 | 842 | 1,258 |
| `0x..12` | sea polygon | 1,192 | 5,353 | 18,610 |
| `0x..14` | river/stream line | 1,866 | 1,941 | 1,888 |
| `0x..15` | water polygon | 420 | 1,412 | 16,128 |
| `0x..1a` | forest/wood polygon | — | 16,619 | 96,793 |
| `0x..1b` | heath/open land | — | 408 | 809 |
| `0x..1d` | park polygon | — | 74 | 904 |
| `0x..26` | unknown line | — | 93 | 651 |
| `0x..2b` | generic land/urban area | 22 | 6,814 | 94,501 |
| `0x..49` | unknown point | — | — | 213 |

The remaining rare types (`0x801c`, `0x8049`, `0x8023`, …) are counted by
`lev3456.py info`.

Road classes in the shape's top nibble (`class << 12`). The shipped 2011 data
uses classes 1–7 and ferries 10–12; classes 8–9 are rare (26/89 shapes at level
3) and their meaning is `UNKNOWN`.

| Class | Road | Where |
| --- | --- | --- |
| 3 | motorway | levels 3, 4, 5 layer 6 |
| 4 | trunk | levels 3, 4, 5 layer 6 |
| 5 | primary | levels 3, 4, 5 layer 6 |
| 6 | secondary | levels 3, 4, 5 layer 6 |
| 7 | tertiary | level 3 (and a few level-4 shapes) |
| 1–2 | minor/local | level 5 layer 7; rare at level 4 |
| 10–12 | ferry | layer 0 |

### Level-5 record layout

The 22-word (44-byte) header is seven `(offset, length)` pairs in 4-byte units
from the record start, plus the parcel code and a token:

| Words | Content |
| --- | --- |
| w0, w1 | parcel code (L4/L5, VERIFIED M4.26/C-2805–C-2806, all 1911 LEV3456R L4/L5 records sec1+sec2): `r20=ay*2, c30=ax*2, R=r20>>2, C=c30>>2, w0=(((C>>8)<<7|R)<<8)|(((r20&2)<<6)|((r20&1)<<4)|0xf), w1=((C&0xff)<<8)|(((c30&2)<<6)|((c30&1)<<4)|(0x5 if L5 else 0x4))`, with absolute coarse-grid `ay=head_y+ri*step`, `ax=x0+ci*step`, `x0=(head_x_signed+1024)`, `head_x_signed=head_x-65536 if head_x>32767 else head_x`, `step=8` (L5)/`2` (L4), `ci=k//per_col`, `per_col=pairs_per_row/cols`. `clarion_bg.parcel_code` with directory-relative indices reproduces 0 (negative control). |
| w2 | record kind, `0x00fa` (this sec1 level-5 layout; sec2 routing records use the M4.23 unit-0/unit-1 grammar) |
| w3–w6 | `ffff ffff 0000 0000` |
| w7, w8 | **road block**: offset/length; `ffff/0000` when absent |
| w9, w10 | **background block**: offset/length |
| w11, w12 | **names section**: offset/length; `ffff/0000` when absent |
| w13–w18 | unused sections, `ffff/0000` |
| w19, w20 | `0000` + per-parcel token |
| w21 | second token word (value varies) |

19 of the 62 records place a **2–6-word unidentified segment at unit 11**,
before the road block (`w7` is 12–14 instead of 11). Its values look like
small coordinates (e.g. `033a 0000`, `0114 017c 01b6 01ec 02f4 0000`). It is
preserved verbatim; its meaning is `UNKNOWN`.

### Background block grammar (levels 3–5)

A background block is a table of **26** `(offset, length)` pairs in 4-byte
units, then the layer data. The table's size is the first non-empty offset
(26 here; a road block reserves 11). Each layer is one group:

```
group:  0001 0003, kind byte, count byte, shapes, zero-pad to 4 bytes
shape:  u16 point count, u16 type, u16 ref, u16 x0, u16 y0,
        (count-1) × (int8 dx, int8 dy)          # polygon/polyline
point:  u16 type, u16 ref, u16 x, u16 y          # kind 0
```

**The count byte is one byte and wraps.** The Ireland/Scotland level-5 layer 8
holds **604** islet polygons and its count byte says **92** (604 mod 256); the
layer length is the authority and every shape is self-delimiting. Walking to
the layer end, not to the count, reproduces all 62 level-5 background blocks
byte for byte. Layer data may end with up to three zero bytes of 4-byte padding.

### Road shape grammar (levels 3–5)

A road block (level 5) or road-shape record (levels 3/4) is eleven
`(offset in 4-byte units, shape count)` pairs and then the shapes. Level 5
keeps classes 3–6 in layer 6, minor classes 1–2 in layer 7 and ferries in
layer 0; levels 3/4 put all roads in layer 6.

```
w0  length in words (0x2000/0x4000 add 1/2 header words)
w1  0x8000 | point count   (level 3: point count alone)
w2  class << 12
w3  style/flag word (0x3000 unnamed, 0x0004 or 0x0144 named, 0x6000 observed)
w4  name reference (word offset into the names section) or ffff
w5, w6  0
w7, w8  start point, x | 0x0800, y (level 5)
        then per link: id, x|0x2000, y|0x4800; last point 0x3000/0x4000
```

Levels 4 and 5 carry a link id per link; level 3 has no ids. `tools/lev3456.py`
decodes and re-encodes every level-5 road block (27,951 shapes) and every
level-3/4 road record without a mismatch on the factory data.

### Level-5 names section

```
u16 version (6), u16 count, five (offset, length) pairs (all ffff/0000)
then count entries:
  8-byte key: type, flags, x, y
  optional u16 0x2c00 when the key's second word is 0x4800 (place label)
  u16 byte length, text, no terminator
```

The section is zero-padded to a 4-byte boundary. The 2011 level 5 has 2,985
entries: 2,726 route references (`00ff 2800`, text `2=A-92;…`), 176 place
labels (`8068 4800`, extra `2c00`) and 83 sea labels (`8089 2800`).
Levels 3 and 4 use a different, partly-subtable names layout (437 and 3,646
sections) that is preserved verbatim and not interpreted here.

### Streams and a byte-identical level rebuild

Every record is one `78 9c` zlib stream. Stock zlib 1.3.1 reproduces all of
them with **level 6, windowBits 15, memLevel 8**; the compressed stream is then
zero-padded to a **4-byte** boundary (the directory pair stores
`(compressed words, plain words)`). zlib-ng (often Python 3.14) does not
reproduce them; use Python 3.10–3.13.

The rebuild proof is section 1 **level 5**:

```bash
python3.13 tools/lev3456.py verify MAPAL001/LEV3456R.DAT
python3.13 tools/lev3456.py rebuild MAPAL001/LEV3456R.DAT --level 5 -o lev5.DAT
cmp lev5.DAT MAPAL001/LEV3456R.DAT
```

All 62 records decode, re-encode and recompress byte-identically; the rebuilt
directory and all row blocks are identical, and the resulting file is
**byte-identical to the 76,066,304-byte factory file** (`cmp` silent). The whole
`verify` command also reports section 1 levels 3/4 and section 2 region-identical
(level 4: 980/1,021 records fully decoded, 41 preserved; level 3: 10,363/10,382
records, 1,677 preserved).

### Regenerating levels 3–5 from OSM

The coarse levels are a whole-database statement: a build replaces every
parcel of the level, not just the cells in a profile, and the unit refuses a
widened directory (it assumes 44 level-4 and 11 level-5 columns). The chain is:

1. **Roads** – decode OSM `highway=*` ways, chain them across way boundaries
   where class and `ref` agree, clip to parcels, simplify and quantise to
   `0..2047`. Map `motorway* → 3`, `trunk* → 4`, `primary* → 5`,
   `secondary* → 6`, `tertiary* → 7` (level 3 only); `route=ferry` → class
   10–12 in layer 0. Classes 3–6 go to layer 6 at level 5, minor roads 1–2 to
   layer 7; levels 3/4 keep all roads in layer 6.
2. **Background** – build land/sea from `natural=coastline`/land polygons
   (sea = complement of land inside the parcel, one rectangle for an all-sea
   parcel), `natural=water` → water polygon, `waterway=river` → river line,
   `landuse=forest` → forest, `leisure=park` → park, other `landuse=*` →
   `0x802b` area, `place=*` → point label at `0x..0c`. Types carry the level
   band in the high nibble (`0xa` level 3, `0x8` levels 4/5).
3. **Names** – level 5 route references come from OSM `ref`
   (`2=REF;2=REF:…`), place labels from `name` on `place=*`, sea labels from
   the water body name. Levels 3/4 names are written by the factory in the
   level-2 subtable layout, which is not decoded here.
4. **Write** – encode one record per parcel, compress with stock zlib as above,
   lay directories and row blocks out at 256-byte boundaries, and rebuild the
   level region. Regenerated bytes are **not** expected to match the factory
   bytes; byte-identity is the regression test for the round trip, not a
   requirement for OSM data.

Known limits: 1,677 level-3 background records with a w15/w16 point index,
437/3,646 level-3/4 names sections, the 19 level-5 pre-road segments and all
section-2 graph records are preserved verbatim rather than regenerated. None of
this has been validated in a car.

## Firmware tile reader (build A, `Navi.exe`)

The map/tile handling code is in `Navi.exe`, not in `NaviMapCC.dll`
(which exposes only the four COM entry points). Reader VAs (build A):

| Path | Function VA | String referenced |
| --- | --- | --- |
| cell-table MAKE (START) | `0x004259bc`, `0x0042757a` | `CELL_TBL MAKE START MESH_ID=%08x DIVID=%04x` (and `DIVID=----`) at `0x0017c358`/`0x0017c388` |
| cell-table MAKE (END) | `0x0041f26c` | `CELL_TBL MAKE END MESH_ID=%08x DIVID=%04x` (and `DIVID=----`) at `0x0017be4c`/`0x0017be1c` |

`MESH_ID`/`DIVID` diagnostics also include `MAP_DATA READ …`, `RGD_DATA READ …`,
`RGD MESH_ID=…`, `OWN_MESH_ID=…` (`0x0017c400`–`0x0017c73d`) and
`MESH_ID = %08x | DIV_CODE/DIV_STS = …` (`0x00181e96`/`0x00181fa1`).

### Six-level table (`VTb`)

The firmware documents a six-level tile table via a debug dump header stored at
VA `0x001783a1`:

```
VTb Tp;Lv;St;F#|L1;L2;L3;L4;L5;L6|Sz;Adr
```

Per entry the fields are:

- `Tp` — type
- `Lv` — level
- `St` — status
- `F#` — file number
- `L1`…`L6` — six level slots
- `Sz` — size
- `Adr` — address

The header has no direct `mov.l` xref; it is reached through the pointer table
at `0x003ec3d4`…`0x003ec414` (which holds `0x001783a0` at `0x003ec400`).

This is a **runtime/firmware structure**, not an on-disk tile header: the tile
files (`BxxRyyR.DAT`, `LEV3456R.DAT`) carry no such table, and the `0x1ac`
per-object descriptor is unrelated (C-296 retraction). See
`docs/research/claims.md` C-860–C-869 and
`docs/experiments/EXP-2026-11-06-M3.5-tile-reader.md`.

### Which sections the renderer/router reads (M3.6, build A Navi.exe)

> **Status:** `OBSERVED` for the MAP_DATA/RGD_DATA path split and section roles;
> **VERIFIED (negative, scoped)** for section 4 not being read by the located
> tile-load paths. Evidence: IMG256 `92aa525d…`, `Navi.exe` `.text` at
> `0x00011000` (`--image-start 0x200200`), `sh4xref.py` + capstone SH4 LE
> disassembly, EXP-2026-11-06-M3.6-tile-sections-renderer, C-870–C-879.

Two distinct tile-data load paths share loader `0x0041ee14` (type/record
validator: `0x0041ebc0` classifies `@(8,rec)` codes `0x0fa0/0x0fa1/0x0fa2` and
others with `@(10,rec)` subtypes, `0x0041e7a8` dispatches subtypes
`0x14/0x264/0x269/0x385`; C-874):

| Data path | Load fn VA | String / xref | Role | Slot table |
| --- | --- | --- | --- | --- |
| `MAP_DATA READ` | `0x00425f40` | pool `0x00426128`→`0x00426088` loads `0x0017c3ec` "MAP_DATA READ START MESH_ID=%08x DIVID=%04x"; callers `0x00426cfc`, `0x0042752c` (CELL_TBL MAKE START, entry `0x0042757a`) | map display (renderer) data | `0xe8fa88`, stride `0x109a4` |
| `RGD_DATA READ` | `0x004266ec` | pool `0x004268ac`→`0x0042680e` loads `0x0017c4ac` "RGD_DATA READ START MESH_ID=%08x DIVID=%04x"; callers `0x00426cfc`, `0x00427870` | routing/guide (RGD) data | `0xea675c`/`0xec3954`/`0xe99698`, 20-byte entries |

Per-section status (each tile section = "read by VA" or "not read by located paths / ignored"):

| File / section | Content (format) | Read by | Evidence / note |
| --- | --- | --- | --- |
| Grid `BxxRyyR.DAT` **section 1** | road-shape (even pairs) + background (odd pairs), display geometry (`w2=0x00fa`; C-170/C-252) | **read by VA `0x00425f40`** (`MAP_DATA`, renderer/display path) | C-870/C-871/C-873 (OBSERVED from path role + section content) |
| Grid `BxxRyyR.DAT` **section 2** | regulation/connectivity graph (routing), unit-0 grammar shared with LEV sec2; dir kinds include `0x1046` (L1) / `0x2046` (L2) (M4.23, C-2620–C-2621) | **read via RGD_DATA path `fn 0x004266ec`** (routing, OBSERVED by callers/role; C-2802/C-2803). `0x00426cfc` invokes MAP_DATA then RGD_DATA on the same load path; `0x00427870` (RGD slot manager, from `0x00427c90`) conditionally invokes RGD_DATA when `*0x009cfd80 != 1` (C-2800/C-2801). Per-kind dispatch inside `0x004266ec`/loader and the regulation-word consumer VA are **UNKNOWN** (C-2803/C-2804, scope: callers only). | EXP-2026-11-08-M4.26; C-870–C-872, C-2621, C-2629, C-2800–C-2804 |
| Grid `BxxRyyR.DAT` **section 4** | admin/place-name index, `w2=0x0009`, dir kind `0x1146`, section type `0x93`, "not geometry" (C-280/C-133) | **not read by located tile-load paths** `0x00425f40` (MAP_DATA), `0x004266ec` (RGD_DATA), `0x0041ee14`/`0x0041ebc0`; **no section-4-specific read VA found** (UNKNOWN whether a separate label/place-name or search subsystem reads it) | C-875/C-876. Searched Navi.exe .text: 0 `cmp/eq #9,r0`; 0x1146 hits coincidental instruction bytes (no data-literal compare); 0x93 only in data/string areas; MAP/RGD call graph (107 fns, depth 4) has no `0x0009/0x1146/0x0093` compare; `0x0041ebc0` does not accept `0x0009` |
| `LEV3456R.DAT` **section 1** | coarse geometry, levels 6,5,4,3 (display) | **read by VA `0x00425f40`** (`MAP_DATA`, renderer/display path) | C-870/C-872 (OBSERVED) |
| `LEV3456R.DAT` **section 2** | router graph, levels 5,4 | **read by VA `0x004266ec`** (`RGD_DATA`, router path) — **not** read by renderer/MAP_DATA path | C-870–C-872; cross-ref RGD handlers C-887 (OBSERVED) |

**Section 4 (especially):** not geometry (C-280). No evidence of access by the
located MAP_DATA or RGD_DATA tile-load paths; no section-4-specific handler VA
was located. It may be consumed by a separate name/search/label subsystem or be
unused at render time — **UNKNOWN** from this analysis.

### Route-link key: what a section-2 entry joins to (M4.39)

> **Status:** `VERIFIED` (L2, factory EU2011 tiles, shuffled and other-parcel
> nulls) for the link key and the node-coordinate key; `VERIFIED (negative)`
> for every numeric `LCTBL001` field. Evidence: EXP-2026-11-19-M4.39-route-link-id,
> C-5150–C-5156, `tools/route_link_join.py`. No firmware run: which key the
> router itself uses is not tested here (C-887's `link[mesh,no,rdtype]` string
> is consistent with it, OBSERVED only).

A level-1 section-2 entry (`clarion_rd.parse_record`, seven words + regulation
words) names its link by **`(parcel code, class, link id)`**: parcel = record
words 0–1, class = class word `& 0xf`, link id = entry word 3 `& 0x1fff`
(`0x2000` = the entry sits at the drawn last point). The same triple names one
drawn link in the parcel's section-1 `0x00fa` shape record (link ids restart at
1 per class), and that shape's word 4 is the label in the odd partner record.
ADDRE street records reach the same link from the other side: their parcel
code + point word offset land on a drawn point, whose link triple is in
section 2.

| Section-2 field (entry word) | Tested as key into | Hit, `B48R058R` | Shuffled null | Other-parcel null | Hit, `B38R068R` | Verdict |
| --- | --- | --: | --: | --: | --: | --- |
| link id (3, `& 0x1fff`) + class | drawn link with an end at the entry's node | 99.9 % | 6.1 % | 0.0 % | 99.9 % | **key** |
| node `(x, y)` (node words 0–1, `& 0x7ff`) | drawn link end points of the parcel | 100.0 % | — | 0.0 % | 100.0 % | **key** (node, not link) |
| w4 (1) | same | 3.8 % | 2.6 % | 0.0 % | 2.2 % | not a key |
| w5 (2) | same | 0.1 % | 0.1 % | 0.0 % | 0.1 % | not a key |
| travel time `a` (5) | same | 1.0 % | 1.0 % | 0.0 % | 1.6 % | not a key |
| length `b` (6) | same | 0.8 % | 0.8 % | 0.0 % | 1.4 % | not a key |
| far node index (0) | same | 6.8 % | 3.8 % | 0.0 % | 7.3 % | not a key |
| own node index | same | 7.2 % | 3.8 % | 0.0 % | 7.9 % | not a key |
| link id, w4, w5, a, b, class word, parcel words, node x/y | every `LCTBL001` attr byte, class, footer `u16` of name-matched records | best ratio 1.43 at 0.1 % | shuffled pairing | — | best ratio 1.26 at 1.9 % | **no LCTBL key** |

Chain from a displayed name to the router edge: label (odd record) ← shape
word 4 ← shape link `(class, id)` = section-2 entry `(class, id & 0x1fff)` in
the same parcel. `LCTBL001` reaches it only by name string (29.4 % of named
linked entries on `B48R058R`, median 8 LCTBL records per name), which is not a
key.

### Reader entry arguments (M3.27, static, build A)

> **Status:** `VERIFIED` for the entry addresses, lengths, the single static
> call site of each and the register setup at those call sites; `OBSERVED` for
> the meaning of each register; `UNKNOWN` where marked. Evidence:
> IMG256 `92aa525d…` (`archive/head256.img`), `Navi.exe` `.text` at
> `0x00011000`, `tools/nk_decomp.py pdata`, `tools/sh4xref.py --to/--calls`,
> `tools/callgraph.py`, `tools/sh4dis.py`. EXP-2026-11-19-M3.27-tile-reader-args,
> C-4580–C-4589.

Start addresses come from `.pdata`, never from this page. `0x0042757a` (the
M3.5 spelling of the third reader) is **2 bytes past** the function start
`0x00427578`; `pdata` reports it `INSIDE`, and that is the only reason the
table below uses `0x00427578`.

| Entry | Build | `pdata` (start, length, end) | r4 | r5 | r6 | r7 | Return |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `0x0041f26c` (M3.5 "cell-table MAKE END") | EU2011 A | START, `0x170`, `0x0041f3dc` | record pointer: `mov.l r4,@(52,r15)`, then `mov.l @(20,r3)` used as a `mul #20` table index at `0x0041f2b4` | pointer to a 4-entry `u32` array (loop count `mov #4,r3` at `0x0041f280`; `mov.l @r8,r3` at `0x0041f296`) | an incoming `u32` flag/mode: reloaded at `0x0041f294`, tested `tst r6,r6` at `0x0041f29c`, compared with `-1`/`-2` at `0x0041f316`/`0x0041f35c` — **meaning UNKNOWN** (callers pass unset/`0`) | **not an argument**: first write is `mov #11,r7` at `0x0041f320`, so the incoming value is dead | `r0`: no deliberate return value; the sole caller does not read `r0` (it restores registers and returns at `0x004216a4`); `r2` only as a spill |
| `0x004259bc` (M3.5 "cell-table MAKE START") | EU2011 A | START, `0xfc`, `0x00425ab8` | mesh id / status code: `mov r4,r8`, then `mul.l #20` at `0x004259de` and `0x00425a10`, and `mov r8,@(40,r15)` at `0x00425a64` | **not an argument**: first touch is the write `mov #0,r5` at `0x004259ce`; a local counter over the 4 mesh-table entries (`add #1,r5` at `0x004259f8`, `cmp/ge #4` at `0x004259fc`) | **not an argument**: first write is `extu.w r0,r6` at `0x00425a40` | control flag: `tst r7,r7` at `0x004259c8` returns immediately when zero; the sole caller reaches the call only when `r7 != 0` (`mov.l @(4,r8),r7` / `tst r7,r7` / `bt` at `0x00426500`–`0x00426504`) | `r0`: no deliberate return value; the sole caller does not read `r0` (it overwrites it at `0x00426512`); `r2` is written but never read by the caller |
| `0x00427578` (M3.5 "cell-table MAKE START", entry `0x0042757a`) | EU2011 A | START, `0x2f8`, `0x00427870` | 20-byte record pointer: `mov.w @r4,r12` (count at `+0`) and `mov r4,r9; add #4,r9` at `0x0042759a`/`0x004275a0` | **not an argument**: first write is `mov r12,r5` at `0x00427602` | **not an argument**: first write is `mov r13,r6` at `0x00427600` | **not an argument**: overwritten by `mov r14,r7` at `0x004275fe` | `r0`: no deliberate return value; the sole caller does not read `r0` (`rts` at `0x00427834`); `r2` only as a spill |

The three entries are **not one function and not thunks of each other**: the
three bodies are `0x170`/`0xfc`/`0x2f8` bytes, `0x004259bc` ends in `rts` at
`0x00425a86`, and no literal pool in the executable sections holds either
`0x0042757a` or a jump to a sibling. Control flow is a chain instead:

```
0x00427cd4 (loop over 4 slots) -> 0x00427c4c -> 0x00427578  (renderer)
0x00427a34 (thread loop, Printf-gated) -> 0x00427144 -> 0x0042613c -> 0x004259bc  (router)
0x004216dc (task loop -> 0x00421548 -> 0x0041f26c)
```

What each static call site loads, and nothing else:

| Entry | Sole static call site | `r4` | `r5` | `r6` | `r7` |
| --- | --- | --- | --- | --- | --- |
| `0x0041f26c` | `jsr 0x004216a0` in `0x00421548` (pool `0x004216d8`) | `mov r8,r4` (`r8` = the function's own `r4`) | `mov r13,r5` (`r15+24`, a 4-entry array of slot indices, filled at `0x004215ca`/`0x0042163a`) | `mov.l @(16,r15),r6` (`r6 = 0` from `0x00421560`, else the count from `0x0041f04c` at `0x004215d4`) | not set |
| `0x004259bc` | `jsr 0x0042650c` in `0x0042613c` (pool `0x00426624`) | `mov r10,r4` (`r10` = per-slot iteration counter, `add #20,r10`) | `mov #0,r5` | `mov #0,r6` | `mov.w #0x0218,r7; add r14,r7` then `mov.l @(4,r8),r7` (a record pointer, not zero, so the call proceeds) |
| `0x00427578` | `jsr 0x00427c6e` in `0x00427c4c` (pool `0x00427c8c`) | `mov r8,r4` (`r8` = `0x00e8ec00` after `jsr 0x003d13e8`, a 68-byte record) | not set | not set | not set |

What the entries call back (they are **readers of already-mapped data**, not of
a file buffer):

- `0x0041f26c` → `0x0041d798`, `0x0041da5c` (twice each); table base
  `0x00e8f5dc` (48-byte stride), index table `0x00e99698` (20-byte stride),
  flag `0x00e99b0a`. `0x00e99698` is BSS (C-3442).
- `0x004259bc` → `0x0041d798`, `0x0041da5c`, `0x0041ee14` (the type/record
  validator of M3.6) and `0x003d13e8` (memcpy-like); builds a 20-byte record
  on the stack with `u16 +8 = 0x0fa0`, `u16 +10 = 0x019a` and the mesh id at
  `+12` (`0x00425a46`–`0x00425a64`).
- `0x00427578` → `0x0041d798`, `0x0041da5c`, `0x0041ee14`, `0x00426d78`,
  and `0x00425f40` (`MAP_DATA READ`, the renderer consumer of C-870) at
  `0x00427820`, gated on `*0x009cfd80 != 1`; then `rts`.
- `0x00427578` also calls `OSMDLL!#55` through `0x0055d8b4` (C-3441) with
  `r4 = 0x89`; `0x0041f26c` calls the same import with `r4 = 4`. Role of that
  import call: **UNKNOWN** here.

**Consequence for M3.25/M9.13.** No M3.5 entry takes the tile bytes in a
register: the callers pass a record (`r4`), an index array (`r5` of VA1) or the
mesh id (`r4` of VA2), and the tile content is reached through BSS tables
(`0x00e8f5dc`, `0x00e99698`) which H101 attributes to a memory-mapped view. A
harness prototype of `(tile_ptr, dst_ptr)` is therefore **not** what these
functions accept; the closest runnable target remains `0x00425f40` (M3.6) fed
by `0x00427578`, whose `r4` is a 20-byte record. Falsifier for that paragraph: a
caller that loads `MapViewOfFile`'s return value straight into `r4` of one of
the three entries (not found: all three have exactly one static call site).
### Reader entry: the read-completion handlers (M3.25, EU2011 build A)

> **Status:** `VERIFIED` (run in PySh4 on the EU 2011 card with
> `tools/datask_l3.py mount`; two controls on a changed `B28R070R.DAT`) for the
> entries, their argument and the byte ranges loaded. Names follow the
> container model of `tools/ze0-viewer/tools_ze0/clarion_tile.py` (section
> list at `0x800`, per-section table, directories, record blocks); the M3.25
> EXP and claims call the section table "level directory" and a directory
> "data block" (corrected by C-3250). EXP-2026-11-19-M3.25-tile-reader-entry, C-4680–C-4699.

Tile bytes are not passed to a `(tile, dst)` function. The data-access task
asks the map-file task for a byte range and is called back with a completion
message ([firmware.md](firmware.md#the-data-access-task-m325-eu2011-build-a)).
The handler is chosen by the request tag:

| Entry | Called for | `r4` | `r5`–`r7` | Return |
| --- | --- | --- | --- | --- |
| `0x0040b8b4` | the first `0x1000` bytes of a tile file | completion message | not arguments | not used; result is the file record and the next requests |
| `0x0040c308` | one section table | completion message | not arguments | not used |
| `0x0041597c` | one directory | completion message | not arguments | not used |

Completion message: `+8 u16 = 0x04a0`, `+10 u16` request tag, `+12 u32`
status, `+16 u32` buffer, `+20 u32` length. The buffer is in the swapped form
(C-4641): a `u16` loaded at buffer offset N is the file's big-endian `u16` at N.

What each entry loads from a factory tile (file offsets):

| Entry | Function | Arguments | Bytes loaded |
| --- | --- | --- | --- |
| header | `0x0040a8d0` (leaf) | `(buffer)` | `0xfa`–`0xfd`, `0x100`–`0x103`, `0x106`–`0x109`, `0x10c`–`0x10f` (the date digits of the common header) |
| header | `0x0040acb8` | `(kind, volume header, buffer, file record)` | `0x800` onward: 12 bytes on `LEV3456R.DAT`, 18 on `B48R068R.DAT`, 16 on `B28R070R.DAT` |
| header | `0x0040aa50`, called per level by `0x0040aea4(buffer, file index, 6, file record)` | `(buffer, file index, level)` | the level table at `0x1ac` (`0x1ac`–`0x1d9` on `B28R070R.DAT`) |
| section table | `0x0040be84` | `(message, control block, table)` | from `+2`; 152 of `0x100` bytes on `B28R070R.DAT` section 1 |
| directory | `0x004156a4` | `(0, message, control block, slot)` | `+6`–`+9` |
| directory | `0x004144a8` (leaf) | `(buffer, flags *, out *)` | the directory header: `+2`–`+5` (the two counts `clarion_tile.py` calls `a`, `b`; 32, 32 on a `0x2046` directory), `+0xa`–`+0xb`; `a` above 64 or `b` above 80 sets an error bit |
| directory | one of eight slot-table parsers picked by `0x004157dc` from the flag word: `0x00414644`, `0x00414930`, `0x00414dbc`, `0x00415330` ran; `0x0041509c`, `0x00414ae0`, `0x0041478c`, `0x00414500` did not | `(buffer, destination)` | from `+0xa` to the end of the slot table (16,514 bytes of a `0x2046` directory) |

The box table at `0x2ac` is **not loaded** by the header entry in this run.

**Section list at header `0x800`** (`SECT_OFF` in `clarion_tile.py`; the firmware's reads confirm its address encoding). 6-byte entries
`{u24 sector, u8 offset, u16 length}` (big-endian), ended by `ff ff ff ff`:
`position = sector * 0x800 + offset * 0x100`, `bytes = length * 0x100`.
`B28R070R.DAT` holds `(2, 0, 1)` and `(0x1d9, 0, 1)` and the firmware reads
`0x1000`/`0x100` and `0xec800`/`0x100`; with the offset byte of the first
entry changed to 1 it reads `0x1100`/`0x100` instead. `LEV3456R.DAT` (2
entries) and `B48R068R.DAT` (3 entries) fit the same rule.

**A tile must list three sections (M3.33, EU2011).** Every tile box of the
firmware's table (data VA `0xd624a0`, 24 B: `+4` part mask = 7, `+6` level
bits = 3, `+8`…`+14` y0/x0/y1/x1, `+16` status) asks for parts 0, 1 and 2,
whose entries are at `0x800`, `0x806` and `0x80c`. On the first mount the
header check `0x0040acb8` gives a tile whose third entry is `ff ff ff ff`
status 3 and returns -1 (`0x0040ad36` → `0x0040ae26`): no section table of
that tile is read, the box finder `0x0040a1dc` skips it, and the mount goes
on in box 0 of the table (`B28R070R.DAT` on the EU 2011 card). 8 of the 45
factory tiles have fewer than three entries and behave this way; with a
third entry written into `B60R048R.DAT` it mounts, with the third entry of
`B48R058R.DAT` removed it does not (`tools/tile_drop_l3.py`,
EXP-2026-11-20-M3.33-b60-header-drop, C-6080–C-6087). `LEV3456R.DAT` (level
bits `0x3c`) needs two.

**No bound on the level-table walk.** With the byte at `0x1ac` changed to
`0xff`, `0x0040aa50` loads 402 bytes up to `0x805` instead of 34.

For M9.13: the runnable target is the whole run (`datask_l3.py mount` with a
card whose tile is replaced), not a call of one entry on a bare buffer: the
entries find their request through the slot table that the earlier request
filled.

### What the mount reads of a tile, and a generated tile (M9.13, EU2011 build A)

> **Status:** `VERIFIED` (PySh4 runs on the EU 2011 card, `datask_l3.py mount
> --position` + `diff`); the read lengths were `OBSERVED` here and are
> read from the code in the next section (M3.31, C-5820–C-5826).
> EXP-2026-11-20-M9.13-generated-tile-l3, C-3250–C-3259.

The firmware reads the tile under a start position: `(lat code << 16) | lon
code` on the `COORD001` grid, from a per-area table (`0x0040b49c`; the EU
card starts at 51.505 N, 0.273 W) or from the `u32` at data VA `0xd940e4`. Of
that tile the mount reads the header, every section table, and per section
the level-2 and level-1 directory whose box holds the position. It asks for
a fixed length per directory, not the directory's own size:

| Directory | Read length |
| --- | --- |
| level 2 (sections 1 and 2) | `0x14100` |
| section 1 level 1 | `0x8100` |
| section 2 level 1 | `0x2100` |
| section 4 level 1 | `0x6100` |

No record block is read during the mount.

| Tile on the card (`B48R058R`, position 51.70 N 17.45 E) | Against the factory run |
| --- | --- |
| `tilewriter.py --factory`, two OSM ways written in place (directory `0xa10b100`, slots 17/18) | SAME, 28 reads; the slot-table parser `0x00414dbc` loads the changed pair entries |
| the same, directory header count 32 → 64 | DIFFERENT: the parser loads 33,014 bytes instead of 16,514 |
| the same, one pair-entry byte inverted | SAME: the mount does not act on record lengths |
| fresh container (`one_tile_pipeline.py --synthetic`, 22,272 bytes) | DIFFERENT: three section tables read, then the first directory read (`0x1100`, `0x8100` bytes) fails past the end of the file |

So a writer that does not start from a factory container must back every
directory with the length above. Whether the road records are accepted is
open (M9.52, M9.53). *Corrected by M5.56 (below): the firmware cuts each
read at the size `DRSTR001.DAT` records; the fresh tile failed because the
test card kept the factory DRSTR001 entry. Padding or a true DRSTR001 size
each suffice.*

### Where the directory read length comes from (M3.31, EU2011 build A)

> **Status:** `VERIFIED` (disassembly + PySh4 runs on the EU 2011 card:
> 118/118 directory reads in 11 runs, 6 kind-byte changes, a fourth tile
> predicted before its run). EXP-2026-11-20-M3.31-dir-read-length,
> C-5820–C-5826.

The directory request is built by `0x00414338(…, section, level)`; its
length comes from the leaf `0x0040901c(kind, 1)`, not from the directory:

```
length = 0x100 * T[kind].n            (no row for kind -> 0, the directory is not read)
```

`T` is a 16-row table `{u32 kind, u32 n, u32 buffer}` at data VA `0x179c08`
(`Navi.exe` section 0, uncompressed; `python3 tools/dir_read_len.py table
IMG256` prints it and checks the copy in the tool):

| kind | read length | | kind | read length |
| --- | --- | --- | --- | --- |
| `0x00`, `0x80` | `0x1100` | | `0x10`, `0x90` | `0x2100` |
| `0x01`, `0x81` | `0xa100` | | `0x11`, `0x91` | `0x14100` |
| `0x02`, `0x82` | `0x4100` | | `0x12`, `0x92` | `0x8100` |
| `0x03`, `0x83` | `0x3100` | | `0x13`, `0x93` | `0x6100` |

`kind` is the runtime level kind of the (section, level) pair at
`0xd982a0 + 72*i + 12*(level - 1)`, `i` the section's position in the level
table (0 = section 1, 1 = section 2, 2 = section 4). `0x00409834` writes it (store at
`0x00409960`) from the low byte of the merged level table, which
`0x0040aa50` builds from the headers of the mounted files; a header entry
with a non-zero count replaces the merged entry, an entry with count 0 does
not. So for a tile **`kind` is byte 1 of its level-table entry
`(level, kind, u16 count)` at header `0x1ac`**: on every EU2011 tile section
1 = `0x80 0x90 0x91 0x91 0x91 0x92` (levels 6..1), section 2 = `0x91 0x91
0x91 0x90` (levels 5, 4, 2, 1), section 4 = `0x93` (level 1), which gives the
four lengths of the table above (`0x14100`, `0x8100`, `0x2100`, `0x6100`)
and `0x1100`/`0x2100` for `LEV3456R.DAT` levels 6/5.

For a writer: keep the factory kind bytes (the merged table is card-wide, so
a tile with another kind changes the length the firmware uses for that
level), and back every directory with `length` bytes of file:
`python3 tools/dir_read_len.py predict TILE` prints the length per section
and level and lists every directory whose read runs past the end of the
file. Over the 46 EU2011 `MAPAL001` files it lists 53 section-4 level-1
directories in 35 files (the last directories of each file; for example 2 in
`B48R058R`, 2 in `B48R068R`, 1 in `B40R060R`); the mount of this record did
not read them (M5.56).

### A read past the end of the file, and a tile without a factory container (M5.56, EU2011 build A)

> **Status:** `VERIFIED` (PySh4 runs on the EU 2011 card, `datask_l3.py
> mount`). EXP-2026-11-20-M5.56-no-factory-container, C-5830–C-5834.

The length asked is `min(0x100 * T[kind].n, size - position)`, with `size`
the file's size **as `DRSTR001.DAT` records it**. The factory's last
section-4 directories of `B48R058R` are asked as `0x2900` and `0x5d00` (to
the file end `0x113ea900`) and parsed. A read fails (status -1) only when
the file holds fewer bytes than asked: a tile shorter than its DRSTR001
entry.

| Tile on the card (position 51.70 N 17.45 E) | Directory read `0x1100` |
| --- | --- |
| fresh tile 22,272 B, factory DRSTR001 entry (289,319,168) | `0x8100`, **-1** (C-3256) |
| the same, DRSTR001 entry 22,272 | `0x4600`, 0, slot table parsed |
| the same, DRSTR001 entry `0x5800` | `0x4700`, **-1** |
| fresh tile padded by `tilewriter.py` (37,376 B), factory DRSTR001 entry | `0x8100`, 0, slot table parsed |
| the padded tile cut to `0x9100` | `0x8100`, **-1** |

`tools/tilewriter.py` without `--factory` now zero-pads the file to the end
of its longest directory read (`pad_directory_reads`; EU2011 build A table,
US2011 not checked), so the tile mounts
whether or not DRSTR001 is rebuilt. A card built with
`rebuild_manifests.py` (true DRSTR001 sizes) needs no padding.
`dir_read_len.py drstr-size` writes a DRSTR001 copy with one size changed
for such tests.

### `LEV3456R` and section 4 at mount, against the Python readers (M9.18, EU2011 build A)

> **Status:** `VERIFIED` (PySh4 runs on the EU 2011 card, `datask_l3.py
> mount` + `mount_dirs_l3.py check`); `OBSERVED` for the parser per `typ`.
> EXP-2026-11-20-M9.18-lev3456r-sec4-l3, C-2440–C-2446.

Of `LEV3456R.DAT` the mount reads the header, both section tables, the
section-1 L6/L5/L4 directories, the section-2 L5/L4 directories and **one**
of the 45 level-3 directories: the one whose box (directory geometry above)
holds the start position, i.e. the cell of the `BxxRyyR` tile read in the
same run (Krotoszyn → dir 24, London → 22, Madrid → 10, Rome → 12). Every
read lands on a table or directory `lev3456.py` / `clarion_tile.read_tile`
list, and the slot-table parser loads exactly `+0xa … 2·size − 1` (header
word 0). Which parser runs follows the directory `typ` on the 13 directories
seen:

| `typ` | Slot-table parser | Seen in |
| --- | --- | --- |
| `0x80`, `0x90` | `fn 0x00414644` | `LEV3456R` L6/L5 (s1); tile s2 L1 |
| `0x91` | `fn 0x00414930` | `LEV3456R` L4/L3, s2 L5/L4; tile s1/s2 L2 |
| `0x92` | `fn 0x00414dbc` | tile s1 L1 |
| `0x93` | `fn 0x00415330` | tile **section 4** L1 |

A `lev3456gen.py` file is read the same way relative to its own layout (the
firmware follows the moved pointers). A level-3 directory with a wrong row
count is dropped (no parser runs). No coarse record and no section-4 record
is read at mount (M9.53). Writers must place level-3 data in the directory
whose box holds it; `lev3456gen.py` does since M5.59 (C-6100–C-6103), and
`lev3456gen.py placement` checks a generated file for it.

### The router reader asks; it does not parse (M4.40, EU2011 build A)

> **Status:** `VERIFIED (static)` for the message and the receiver, `VERIFIED (run, L3)` for the
> reply path and the words `0x00422eac` reads (M4.54). Evidence: IMG256 `92aa525d…`
> (`archive/head256.img`), `tools/sh4dis.py`, `tools/callgraph.py`, `tools/datask_l3.py tables`,
> `tools/rgd_reply_l3.py`.
> EXP-2026-11-20-M4.40-sec2-router-grammar (C-5640–C-5645), EXP-2026-11-20-M4.54-section2-read-watch (C-5710–C-5717).

`RGD_DATA READ` `0x004266ec` (router) and `MAP_DATA READ` `0x00425f40` (renderer) read no tile
bytes: their 27-function subtrees have no file or file-mapping import (C-4622). Each builds a
list of `(mesh id, DIVID)` requests (32-byte entries, mesh id at `+16`, `DIVID` at `+14`,
`u16` count at `+0`) and sends one message through `0x0041ee14` → `OSM_TaskSend` to the
data-access task (`*0x011fff58`):

| Word | Router `0x004266ec` | Renderer `0x00425f40` |
| --- | --- | --- |
| `+8 u16` id | `0x14b5` | `0x14b5` |
| `+10 u16` sub | 2 | 2 |
| `+12 u32` | `*0x011fff5c` | `*0x011fff5c` |
| `+16 u32` data kind | **`0x40`** | **`4`** |
| `+20 u32` | request list | request list |
| `+24 u32` | 2 | 2 |

Before sending, the router reserves a `0x1f400`-byte buffer per requested slot (`0x00425cb0`,
pool `*0x00ea675c`, stored at entry `+4` of the 12-byte slot table `*0x00ec3954`). The
data-access task hands `0x14b5` to `0x004066ac` (deferred while the map is not ready), which
uses the list (copied to `0x00d53f20` only when `+12` ≤ 1) and passes the kind word to
`0x00408480`; its subtree reaches 140 functions.

The data come back as message `0x14b6`: `0x00427144` sends kind 64 to `0x004268c0`, which asks
`0x003edf5c(mesh id, 0x40, …)` for a size (≤ `0x1f400`), copies that many bytes from the reply's
`+20` pointer into the slot's buffer and marks the slot state 2. **The router code that reads
that buffer is `0x00422eac`** (callers `0x0043fabc`/`0x0043fba8` ← `0x00440e00`), not
`0x004266ec`: with `k` taken from a table that `0x00424464(19, …)` returns, it reads `u16`
words `k + 15` (`& 0x0f00` must be `0x0900`), `k + 7`, `k + 6` = `d` and `k + d` (bits 3–7 are
its result). C-5646–C-5649.

#### What the four words are (M4.54, L3)

> **Corrected by M4.40 (C-5924):** the table below was produced with a **section-2** block put into
> the buffer by hand and `k` chosen as the first index that clears the gate. The firmware fills this
> buffer with a **section-4** record (kind `0x40`, next subsection), and a passing `k` exists by chance
> in about a third of section-2 records, so the part-a field names below are retracted (C-5713–C-5715).
> The run facts (pass-through store, four reads, the gate) stand.

`tools/rgd_reply_l3.py` stores a factory block through the real `0x004268c0` and runs
`0x00422eac` with a read-watch. The store is a **pass-through** (it copies the block's plain
length, e.g. 3508 B for `B48R058R` `0xb91d078`, and stores even a section-1 block's 2424 B), so the words
are ordinary part-a section-2 words at record-relative index `k`. On `B48R058R` `0xb91d078`
`k = 221` is **node 7's header word 0** (`x = 0x4fd`, count 3; unit-0 base at plain word 27):

| Read | PC | Word | Part-a field | Value | Meaning |
| --- | --- | --- | --- | --- | --- |
| `k + 15` | `0x00422fc8` | `k+15` | node 7 entry 1 `cls` | `0x0919` | class word; `& 0x0f00 == 0x0900` is the gate |
| `k + 7` | `0x00422fda` | `k+7` | node 7 entry 0 `cls` | `0x0717` | class word; 0 → alternative `k` via `0x004250e4` |
| `k + 6` | `0x0042305a` | `k+6` | node 7 entry 0 `id` | `0x0008` | link id; this is `d` |
| `k + d` | `0x00423064` | `k+d` | node 7 entry 0 `a` | `0x003b` | result `(a & 0xf8) >> 3 = 7` |

So `k` is a record-relative `u16` index, and on this block it starts a node's entry block:
`k+6` and `k+7` are the first entry's `id`/`cls`, `k+15` is the second entry's `cls`, and `k+d`
is a field of the node. On a second tile (`B30R058R` `0x5759f4`, `k = 78`) `k` is an entry's
`a` word rather than a node header, so the node-header alignment is a sample, not a rule; what
the unknown `0x00424464(19, …)` table selects is still open (C-5714).

Controls: the same `k` on a **section-1** block (`B48R058R` `0x176a800` at `k=221`,
`B30R058R` `0x66700` at `k=78`) fails the gate (`0x1d0d`, `0x7500`), and a declared `k=0` on
the section-2 block fails it too (`0x06d6`); `B28R070R` has no passing `k` in its 303
section-2 records. Over single-`k` records whose `k` is a node header, `d` always equals the
entry 0 `id` (4513/4513 on `B48R058R`), while `k+d` lands on entry 0 `a` in only 92 — `k+d` is
a record field, not necessarily `a`. C-5710–C-5717.

#### Which section each request kind fetches (M4.40, L3, EU2011 build A)

> **Status:** `VERIFIED (run, L3)` — the firmware's data-access task, mounted on the EU 2011 card by
> `tools/datask_l3.py`, served `0x14b5` requests sent by `tools/datask_req_l3.py` (one declared model:
> the client row). EXP-2026-11-20-M4.40-request-kinds, C-5920–C-5927. US2011 not run.

`0x00408f9c` maps the request kind (`+16`) to a section index through the table at data `0x179b20`
(`{u32 group mask, u32 kind mask, u32 index}`). Observed on two tiles whose section list is 1, 2, 4
(`B48R058R`, `B30R058R`): index 0 read section 1, index 1 section 2, index 2 section 4. That the index
counts the tile's sections in list order is not tested on a tile with another section list:

| Kind | Sent by (EU2011) | Index | Record read (L3, `B48R058R` and `B30R058R`) | Reply pointers (list entry `+16`…`+28`) |
| --- | --- | --: | --- | --- |
| 4 | `MAP_DATA READ` `0x00425f40` (renderer) | 0 | section 1, `0x00fa` road shapes | `+16` word 22 (layer table), `+28` word 0 |
| 8 | `RPF_PreMap_start` `0x00336bf0` (route path finder) | 1 | section 2, level 1 | `+16` **unit 0** (word 27), `+24` **unit 2** when present (word 6113 of `a6bed6ee`), absent units `0xffffffff` |
| `0x10` | `RPF_PreMap_start` `0x00336bf0` | 1 | none for `a68cd68c` (status 4) | — |
| `0x20` | — | 1 | refused: message status 9, entry status 3 | — |
| `0x40` | `RGD_DATA READ` `0x004266ec` (router) | 2 | **section 4**, `0x0009` records (`a6bed6ee`, `9b8fd56e`); status 4 where the parcel has none | `+16` word 0, `+24` name text (= header word 6), `+28` word 9 |

Run (L3): a kind-`0x40` request from a declared client reads a **section-4** record (guidance:
signposts), and a kind-8 request reads section 2 and gets pointers to the record's units 0 and 2
(C-5921, C-5922). Static: the route path finder sends kinds 8 and `0x10` (C-5923).

> **Inference (static chain + L3, not run end to end):** the router's kind-64 reply that
> `0x004268c0` stores and `0x00422eac` reads is then a section-4 record, and the section-2 reader is
> in the route path finder. The router, `0x004268c0` and `0x00422eac` were not driven with the real
> reply; the request came from a fake client (C-5921).

The reply entry
is `+0 u16` status (1 data, 2 pending — a read was queued and a second reply follows, 3 refused,
4 no data), `+4` kind, `+10 u16` DIVID, `+12` mesh id (the level-1 parcel code, rounded to the
`0x80`-unit box for kinds 4, 8 and `0x40`), `+16`…`+28` pointers. The message status is
separate: 9 = refused. A requester must have a row in the client table (data `0xd98fe0`, 24 × 64 B);
an unknown one is refused with message status 9 and entry status 3 (C-5926).

### The `LOC_map` walk of a served road record (M9.66, EU2011 build A)

`tools/locmap_l3.py` runs the firmware's own chain: a position message
(`0x0fa0` sub 119: mesh, x, y) makes the client task want four (mesh,
quadrant) groups; on the request tick the requester `fn 0x00425f40` sends
`0x14b5` kind 4; the data-access task reads the record and answers; the
handler `fn 0x0042613c` copies `record + 0x2c` into the shape buffer and the
client posts `0x0fa0` sub `0x019a` to `LOC_map`; its receiver
`fn 0x00421548` calls the walk **`fn 0x0041f3dc`** (C-6770–C-6772).

What the walk loads of the shape buffer (byte offsets from `record + 0x2c`,
words little-endian after the firmware's swap; C-6774, C-6775):

| Item | Where | Use |
| --- | --- | --- |
| 12 rows | bytes `2 + 4 i`: `u16` start, `u16` count | a row with count 0 is skipped; first shape at byte `4 * start` |
| shape word 0 | | low 13 bits: length in words (next shape); top 3 bits: extra header words |
| shape word 1 | | low 12 bits: point count |
| shape words 2, 3 | | word 2 top nibble `0xa`/`0xb`: per-point block skipped; word 3 low 2 bits: more header words |
| first point | word `7 + (w3 & 3) + (w0 >> 13)` | |
| point | `u16` x, `u16` y, 11-bit coordinates | followed by one word for each of: x bits `0x1800` not both set, y bit `0x2000`, y bit `0x1000`, y bit `0x0800` |
| point reference | byte `2 (p + ((y >> 13) & 1)) + 4` for a point at word index `p` | word index of another point, `0xffff` = none; only for coordinates neither 0 nor `0x7ff`; the walk loads the target's y and reference word and compares the latter with `p` |

On the factory record of `B48R058R` (mesh `0xa6c1d6b2`) the walk makes 5,363
loads (6,868 distinct bytes of 11,264); on the generated record of M9.53 it
makes 49 (70 distinct bytes). The generated record's first reference word was
`0x0100` (record word 58), which pointed past the 184 B record: the firmware
then loaded stale pool bytes (C-6776), and none of the generated shapes was
counted in the result table `*0x00e8f5dc` (C-6778; cause open, M9.67). The
writer now emits **`0xffff`** there (`fa_encode.NONE_REF`), so a start point
points at no point and the walk stays in the record: the fixed tile G1 makes
46 loads (66 distinct bytes) with no out-of-window load (C-6853,
EXP-2026-11-22-M5.72). Record word 59, which M9.58 took for the link id, is
not loaded by this walk (C-6777). The record tail (`record + 4*w17`) is copied
but not loaded in this run.

**The reference word on factory records.** `tools/tilewriter.py --census TILE`
reads the word for every point that carries a dedicated slot, across every
kind-`0x00fa` record the checked-in reader parses. On the 65,262 parsed records
of `B48R058R` (5,898,373 points with a word): 83.27 % hold an in-record point
index, 16.54 % hold `0xffff` ("none"), 0.22 % hold a link-header `val` word
(`0x0021`, `0x0026`, `0x0028`, …), and **0** point past the record; 60.8 %
point back (mutual). A start with a link is an in-record point, an isolated
start is `0xffff`.

**Slot arithmetic.** For a start point at record word `p`, the walk reads
`p + ((y >> 13) & 1) + 2`, which is the link header's middle word: `[style,
val, lid]` (fresh style) or `[val, lid]` (bare). The `style` word does not move
the slot (on F a fresh-header start at word 55 reads slot 36, record word 58;
a bare-header start at word 72 reads slot 53). The shape buffer starts at
record word 22 (byte 0x2c), so buffer slot `s` is record word `22 + s`.

> **Open:** the result table is still all zeros for the fixed tile G1: the
> reference is no longer out of record, but the shapes are not counted. The
> counted-shape rule of `fn 0x0041f3dc` is M9.67 (C-6857); a generated shape's
> end reference slot is `0x0000` where the factory writes a back-reference or
> `0xffff` (C-6856).

> **Not run:** the divided-record branch `fn 0x004205b8`, positions that need
> a neighbour mesh (`STDDLL!STD_MeshID_getAny`, M9.65), the consumer of the
> result table, US2011.

## Cross-edition differential census (2011/2014/2016)

`tools/diff_years_tiles.py` compares the same `BxxRyyR.DAT` in two EU editions
per section (the section span `[taddr, next_taddr)`), reporting size, SHA-256
and the record `kept/changed/added/removed` triple.  It is a **census**, not a
field decoder: it says which records change *together with* which, and names
the section-4 rename records and section-1 added records by tile and offset.

- Frame each section by its section-table `taddr` (not by a global offset);
  the container re-packs sections between editions, so a section's file offset
  moves and a per-offset byte diff is meaningless for section 2.
- Match records by identity `(level, dir_y, dir_x, slot, first-4 plain bytes)`
  before calling something added/removed; a content-only multiset turns every
  shifted coordinate into a false add+remove pair.
- The section-4 rename samples (parcel + pre-names header identical, only the
  name text differs) are listed in EXP-2026-11-19-M4.41-diff-years; they are
  the cleanest name-index pairs for M4.36 and the section-4 reader.

## Key questions

1. What is the record grammar inside a real (non-448-byte) payload?
2. What do the `20 1e` / `07 ff` constants mean? Is `20 1e` a packed `(dx,dy)`
   pair at 4-bit granularity?
3. Is the 4-unit sub-lattice really a quadtree?
4. What is the relationship between `LEV3456R.DAT` (rows B20–B78, cols
   R040–R078, levels 3–6) and the per-tile files?
5. How are roads split between `MAPAL001` (geometry) and `RDSTM001`
   (street/attribute data)?
6. Does the unit accept a tile with only part of its geographic cell
   populated? (Build profiles currently ship whole tiles.)
