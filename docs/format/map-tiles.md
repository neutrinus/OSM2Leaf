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
- keep declared-size directory tails: the EU 2011 section-1 level-1 `0x2n46`
  family carries an extra `n*512`-byte tail for `n=1–7` observed (e.g. 512 B
  for `0x2146`, 3584 B for `0x2746`; `0x2946` had 0 in `B48R058R`). Their
  slot-table container (header/tag/body/tail) round-trips, but many blocks hold
  non-zlib records / `0xffffffff` pair fields, so `tilewriter` preserves these
  kinds and refuses mutation inside them (M5.22, C-2810–C-2813);
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
