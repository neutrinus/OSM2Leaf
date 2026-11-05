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

The 45 tiles form a 9 × 7 lattice stepping by 8. The smallest tiles are sea;
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
| `LEV3456R.DAT` | byte-identical; 113 level 3–5 records not modelled |

### Dense tiles and roads (round 2)

All five target tiles now rebuild **byte-identically**, including the dense
`B30R048R` (1,358,592 B). The missing container pieces were:

- mask the `0x80000000` pair flag before computing a compressed length;
- preserve raw slot tails (e.g. `B30R048` slot 21 at body `+0xE8`);
- accept `0x7fffffff` empty tags at level 1;
- keep the extra 512-byte `0x2146` tail;
- copy the 55 KiB unreferenced gap at `0x9a520..0xa7d00` verbatim.

Road-shape records (section 1, even pair, `w2=0x00fa`) are decoded:

| Tile | Even records | Shapes | Points |
| --- | --: | --: | --: |
| `B30R060R` | 37 | 784 | 8,923 |
| `B30R048R` | 188 | 6,270 | 84,470 |

`LEV3456R` level 6 is decoded: no count word, table at word 11 with 26
`(offset, point-count)` pairs (156 features). Coarse levels 3–5 rebuild with
0 failures; 1,722 opaque records are preserved verbatim.

Known limits:

- section-4 content (`w2=0x0009`) is still opaque;
- road names/classes/speeds/one-way are not decoded;
- layers 4/6 are parsed but not drawn;
- a streaming **decoder** for the 436 MB tile is still missing (the writer
  streams in 8 MiB chunks, max RSS ~120 MB).

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
