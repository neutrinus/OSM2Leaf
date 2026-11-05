# `MAPAL001` map tiles

`MAPAL001/` holds the map geometry. In the EU 2011 image it contains:

- 46 files named `BxxRyyR.DAT`, for example `B28R070R.DAT`,
  `B30R048R.DAT`, `B68R058R.DAT`
- `LEV3456R.DAT` (76,066,304 bytes) — much larger than every other tile

The tile set is small: 46 tiles cover the whole of Europe at the coarse
level, which suggests a hierarchy of tile sizes/levels rather than a uniform
grid. The exact grid convention is **not yet decoded**.

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

## Descriptor area around `0x2b0`

`B28R070R.DAT`:

```
02 01 02 02 00 07 80 06 95 fd 30 fd ce 01
00 07 80 06 98 fd 30 fd ce 02
02 02 00 07 80 07 17 fd 30 fd a1 01
00 07 80 07 1a fd 30 fd 9f
```

`B30R048R.DAT`:

```
03 01 02 02 00 08 b1 08 5c 06 90 07 80 01
00 08 b0 08 5c 06 90 07 80 02
02 02 00 08 9d 08 70 06 90 06 a7 01
00 08 9c 08 72 06 90 06 f2 04 01 01 00 08 8b 08 76 06 90 06 9f
```

The repeating 16-bit values (`fd30` = -720, `fdce` = -562) look like signed
fixed-point deltas. The `07 80`, `06 95`, `08 b1` values may be tile-local
coordinates, level-of-detail IDs or record counts. This is a promising place
to start the tile decoder.

## Header descriptor at `0x1ac`

All tiles share a pattern:

```
00 02 01 06 06 80 00 00 05 90 00 00 04 91 00 00 03 91 00 00
02 91 00 02 01 92 00 0f 02 04 05 91 00 00 04 91 00 00 02 91 00
01 01 90 00 05 ...
```

`LEV3456R.DAT` uses mostly `01` where ordinary tiles use `00`, and has a
larger descriptor. This is consistent with a **level-of-detail table**: each
entry names a level and a count/offset. Field-by-field decoding is TODO.

## Key questions

1. What do `B` and `R` mean, and how do `xx`/`yy` map to latitude/longitude?
   Likely a Japanese-style mesh code or a Clarion proprietary block/row grid.
2. Are the zlib streams addressed by the `0x200`–`0x5200` descriptor area, or
   simply concatenated in order?
3. What is the record format inside a decompressed stream?
4. What is the relationship between `LEV3456R.DAT` and the per-tile files?
5. How are roads split between `MAPAL001` (geometry) and `RDSTM001`
   (street/attribute data)?

## Hypotheses (not verified)

- The `BxxRyyR` name encodes a tile at some mesh level: `B` = block/row
  index, `R` = row, suffix `R` = region or revision.
- `LEV3456R.DAT` is a shared multi-level table used by all tiles (hence the
  `LEV` and `3456` in the name).
- The many small zlib streams are per-object or per-tile-chunk records
  addressed by the preceding index, similar to `.cmp`/`.ind` but inline.

Do not rely on these hypotheses in code until they are checked against
multiple tiles and, ideally, the US dump.
