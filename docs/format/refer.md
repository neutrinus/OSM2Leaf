# `REFER001` / `REFER002` families

`REFER001` stores 194 logical databases as `.DAT.cmp` + `.DAT.ind`.
`REFER002` is **not** an uncompressed copy: it has only 16 files and is a
separate EV/charging-station POI layer. The families are sharded by
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
- **Coordinates are present, but not as a named field.** Each POI record
  contains a 4-byte id (two `u16`); it decodes with the same formula as
  `COORD001`/`ADDRE`:
  `lat = (x-32768)/192`, `lon = (y-52742)/128`. The two copies are usually
  equal; the second can differ by a small delta (e.g. `(8,8)` in Vatican
  records).
- No icon-id table inside POINT; `BICON001` correlation is **UNKNOWN**.

### POI → location link (partially solved)

The 4-byte id is the POI's coordinate, not an opaque key. It was confirmed by
cross-matching POINT ids with `ADDRE` records (e.g. 18 of ADDRE017's ids occur
in POINT017, 31 in POINT008).

What is solved:

- POINT record → 4-byte lat/lon id → the same grid as `COORD001`, `ADDRE` and
  the tile stream keys.
- POINT ↔ ADDRE share the same ids, so the address record for a POI is
  reachable by coordinate (and probably by the address string).

What is still open:

- The 24-byte index record `f11` is a dense POI id only for single-page
  shards; on multi-page shards it is not a global record index.
- `f7`/`f8` join a POI record to the index, but the pair is not unique.
- The POI `icon code` → `BICON001` mapping is unknown.
- Two point copies per record: which one is the display point when they differ?
- `REFER002/POINT002.DAT` (EV layer) has an explicit `xy-coordinates` field;
  it may document the intended coordinate semantics for all POINTs.

Next experiments:

1. Map `f11` onto the 1000-record pages of a multi-page shard (POINT004).
2. Decode `REFER002/COORD001.DAT` (22 × `0x18` B) and compare with the same
   transform.
3. Pick a POI with two different point copies and compare both against the
   address record / known ground truth.
4. Decode `BICON001` and map the POI `icon code`.

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

Decoded at the container/record level. Each of the 33 shards has the same
skeleton:

```
0x000  512-byte common header
0x200  0x500-byte constant template, byte-identical in all 33 files
0x700  uncompressed index area (0xFF fill + 6-/12-byte cells)
  I    zlib block chain -> 22-byte index records (20,000 per full block)
  S    exactly one 0x100-byte schema block
  R    zlib block chain -> variable-length address records
  T    zero padding + trailer of big-endian u32
```

- The `0x200–0x6ff` template is **constant across all 33 files**. The old
  “first non-FF at `0xac`” is a `00 00` slot inside it and carries no per-file
  information.
- Schema block signature: `ff ff 00 10 ff ff ff ff 00 00 00 00 ff ff ff ff`,
  exactly once, `0x100`-aligned. Fields: `STREET`, `area code`, `street name`,
  `dndc-id`.
- Inner blocks are plain **zlib streams** (`78 01/5e/9c/da`) with 0–3 bytes
  padding, **no length prefix**.
- Index records: 22 bytes = 11 big-endian `u16`; full blocks are 440,000 B =
  20,000 records.
- Address records: variable length, separated by `0xff`; `c0`/`c8` starts a
  record (`c8` length = `2*L-1`). Fields:
  - `06 xx` + **4-byte coordinate id**
  - `02/03/04/05 40 XX YY` — street-segment end points
  - `06/07` + subtype + NUL-terminated upper-case Latin-1 string
  - `:N:;:N:` — house-number range (N = 1..341)
- Coordinate id: `x = id >> 16`, `y = id & 0xffff`,
  `lat = (x-32768)/192`, `lon = (y-52742)/128`. Verified against Andorra,
  Luxembourg, Monaco and Lazio.

`REFER002` ships **no ADDRE at all**; only 15 of 33 POINT shards exist there.
`COORD001` table entry *i* is the region box of `ADDRE(i).DAT` (31/33 shards
100 % inside; two spill at borders).

Still open: the uncompressed 6-/12-byte index cells, the exact `c0` vs `c8`
tag grammar, subtypes `0x54`/`0x58`, the `40 XX YY` point encoding, the 6
trailing bytes of each `COORD001` entry, and the per-file trailer table.

## What this means for the compiler

- Address/POI sharding is per country, so a `poland-full` profile touches
  shard 021 plus any neighbouring-country shards needed for whole tiles.
- POI records are bit-packed; the field dictionary must be read from the
  file, not hard-coded.
- The absence of coordinates in POINT means coordinates must come from
  `COORD001`/`REFER002`/tile links; the join is still unknown.
- `REFER002` is not a backup copy; it has extra EV fields. Do not overwrite it
  with a copy of `REFER001`.
