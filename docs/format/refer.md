# `REFER001` / `REFER002` families

`REFER001` stores 194 logical databases as `.DAT.cmp` + `.DAT.ind`; `REFER002`
holds the same logical names uncompressed. The families are sharded by
**country**, not by arbitrary number.

> **Evidence status:** the common anatomy and several record layouts are
> `VERIFIED`; field semantics are `OBSERVED`/`HYPOTHESIS`. `ADDRE` is still
> being decoded.

## Common anatomy

```
0x0000..0x01ff  common 512-byte header (UTF-16BE text + binary @0x180)
0x0200..0x0fff  fixed reserved area, byte-identical in almost all 194 files
0x1000..        typed payload
```

The old "first non-FF at body offset `0xac`" is an isolated `00 00` inside the
fixed template, not a header field. Real structure starts at `0x1000`.

Some families (`INTER`, `FRWAY`, `ADDRE`, `POINT`) contain exactly **three
zlib streams**. A section is preceded by an 8-byte header
`4e 20 00 00 | u32`; decode by inflating, not by trusting the length word.

## Sharding

There are 33 numbered shards, matching the 33 regions:

```
001 Andorra      002 Belgium      003 Bulgaria     004 Denmark
005 Germany      006 Estonia      007 Finland      008 France
009 Greece       010 Ireland      011 Italy        012 Croatia
013 Latvia       014 Liechtenstein 015 Lithuania   016 Luxembourg
017 Monaco       018 Netherlands  019 Norway       020 Austria
021 Poland       022 Portugal     023 Romania      024 San Marino
025 Sweden       026 Switzerland  027 Slovakia     028 Slovenia
029 Spain        030 Czechia      031 Hungary      032 Vatican
033 United Kingdom
```

`COORD001`, `ICODE001` and `ZIPFR001` are global; `ADDRE`, `POINT`, `INTER`,
`ICADM` and `ZCODE` share the 33-way split. `FRWAY` has only 24 numbers.
`REFER002` is **not** duplicate data — it carries the longer EV schema
(xy-coordinates, plug info, parking capacity).

## `POINT0nn` — POIs

- The field dictionary is inside each file: plain ASCII names with per-field
  **bit offsets**: area code 32/44, category 58, sub-category 73, detailed
  code 84, index 99, facility name 111, address 123, dndc-id 255 (`0xff` =
  variable).
- POI records are **bit-packed** and length-prefixed (`byte[1] = length/2`,
  `byte[0] ∈ {0x60,0x68}`).
- Records are stored in pages of exactly **1000**: POINT004 = 13 pages =
  13,000; POINT021 = 68 pages = 68,000.
- Names/addresses are Latin-1, NUL-terminated at the record end; `@` separates
  house number from street (`51@CARRER PRAT DE LA CREU`).
- The 24-byte index record is 12 big-endian `u16`; `f11` is the POI id (dense
  only for single-page shards).
- **No coordinates found** in POINT: no lat/lon, no mesh ID, no `Pre`/`Next`
  links. The firmware `MESHID`/`Pre`/`Next` strings are probably in-memory
  structures, not on-disk POINT fields.
- No icon-id table inside POINT; `BICON001` correlation is **UNKNOWN**.

## `INTER0nn` — intersections

- Table 1 at `0x1108`, behind an 8-byte block header.
- **12-byte records**: `u8 id`, `u16 n`, `u16 0`, `u16 offset`,
  `u16 length (6*k)`, `u16 0`; `0xffff` length = terminator.
- Offsets index blob 0, whose 6-byte elements are `FFFF…` (empty),
  `4000 0000 XXXX` (node ref) or `0000 a b` (attribute).
- `n` is not `length/6` (counter-example in FRWAY023); meaning unknown.

## `FRWAY0nn` — freeways/routes

- Same 12-byte table, then blob 1 = route refs (`A1`, `E70`, `E773`…), and
  blob 2 = main table.
- Records end with `u16, u16 0, u8 serial, text\0` and repeat a 4-byte **mesh
  id** (`9f be da 1e`, `a0 6f db cf`…). Encoding unresolved.

## `ICADM0nn` — administrative country data

- 33 blocks, **462-byte stride**, 7 slots × 64 bytes.
- Slot: `u16 tag (0x00e7)`, `u16 ISO-3166-1 numeric` (big-endian),
  `char[60]` admin terminology.
- All 33 ISO codes match the country whose terminology follows (020 Andorra →
  `PARROQUIA`; 826 UK → `POSTAL COUNTY`).

## `ZIPFR001` — postal/freeway masks

- 14-byte records: `char key[10] + u32 LE mask`; 36,881 records, 119 distinct
  masks. Keys look like truncated postal codes.

## `ADDRE0nn` — addresses

Not yet decoded in this repo. Expect the same 33-way sharding, bit-packed
records and a string table. Track progress in `TODO.md`.

## What this means for the compiler

- Address/POI sharding is per country, so a `poland-full` profile touches
  shard 021 plus any neighbouring-country shards needed for whole tiles.
- POI records are bit-packed; the field dictionary must be read from the
  file, not hard-coded.
- The absence of coordinates in POINT means coordinates must come from
  `COORD001`/`REFER002`/tile links; the join is still unknown.
- `REFER002` is not a backup copy; it has extra EV fields. Do not overwrite it
  with a copy of `REFER001`.
