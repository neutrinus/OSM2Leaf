# `REFER001` / `REFER002` families

`REFER001` stores 194 logical databases as `.DAT.cmp` + `.DAT.ind`.
`REFER002` is **not** an uncompressed copy: it has only 16 files and is a
separate EV/charging-station POI layer. The families are sharded by
**country**, not by arbitrary number.

> **Evidence status:** the common anatomy and several record layouts are
> `VERIFIED`; field semantics are `OBSERVED`/`HYPOTHESIS`. `ADDRE` is decoded
> down to the 6-byte cell payload (`UNKNOWN`, C-972) and the `TT 40 XX YY`
> point tokens (frame `VERIFIED`; 2D geographic not derivable from
> `coord,XX,YY,tag` alone, frame/`XX` meaning `UNKNOWN`, C-976 refined by
> M4.19/C-1960–C-1969).

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
- Each facility name is bracketed by a 16-bit category code and a 16-bit
  brand code (last two bytes of the record). The brand code selects the
  `BICON001` logo; see [assets.md](assets.md) for the verified table.

### POI name page framing (page level)

A POINT inner zlib page that carries display names is a chain of
self-describing records, not a table:

```
u8 tag (0x60 | 0x68) | u8 len2 | body | text | ff ff
```

- Record size is `2 * len2` bytes, so every record is even-sized and the
  length can only be stored in 2-byte units.
- Records are packed back to back with no gaps and the page has no offset
  table; record *n+1* starts at `record_n.offset + 2 * record_n.len2`.
- The last two bytes of a record are `ff ff`. The display text is the
  printable Latin-1 suffix before it; the text ends with NUL in some
  records and directly at `ff ff` in others
  (`VATICAN MUSEUM@VIALE VATICANO\0`, `...SAN PIETRO` + `ff ff`).
- The fixed prefix before the text (tag + length + body) is 48 bytes, or 88
  when the record carries a dozen `02 XX 04 00` / `40 XX YY` coordinate
  pairs (POINT032 page `0x4200`: 25 records with 48, 14 with 88; text
  regions 26–40 bytes, all even).

Only some pages are record pages. In the EU 2011 `REFER001` tree 1,834 of
12,965 zlib pages are record chains (POINT021: 117 of 623; POINT032: 1 of
8); the others start `00 xx 00 yy` and are a different (bit-packed) page
type.

Consequence for a rename: a different-length name needs only the record's
`len2` byte updated; the rest of the page shifts, and the `.DAT` logical
size does not change because the page keeps its absolute offset. The byte
delta must be **even**. The recompressed page must still fit in the space
before the next stream (POINT032 page `0x4200`: 655 bytes used, next stream
at `0x4500`, 768 bytes reserved). `tools/mutate_refer_poi.py --resize`
implements this and refuses anything else.

### POI → location link (solved)

The 4-byte id is the POI's coordinate. Each record has two copies:

- **A = display point** — inside the `COORD001` region box in 100 % of
  records.
- **B = address reference** — on Monaco outside the box in 337/380 records;
  it matches the street's ADDRE id far more often (95 % vs 10 %).

The difference A−B is 0/1/8/12/13 grid units, mostly `(8,8)`/`(12,12)` — a
re-quantisation, not an entrance-level offset.

### POI ↔ ADDRE join (record-level)

Join by `(street name, house number)`:

```
POINT017 "AUTO KONCEPT11@BOULEVARD ALBERT 1ER"  A=a0cfd1bd B=a0c3d1b1
ADDRE017 "BOULEVARD ALBERT 1ER" -> id a0c3d1b1, ranges 17;17, 21;27, 25;25, 27;27
```

ADDRE splits a street by house range; the POI appends its house number, so
(street, number) selects the record. The id alone is only a cell (Monaco: 239
streets, 13 ids).

### `f11` index → (page, slot)

```
f11 = (2000 * page + slot) & 0xffff
```

`page` is the 0-based record page (1000 records/page), `slot` is 0..999.
Match rates: POINT004 **99.3 %**, POINT021 **95.4 %**; controls are ~8–10 %.
The id is 16-bit and the per-page block is 2000, not 1000. On a one-page shard
this degenerates to `f11 = slot`, which is why the old “dense id” reading only
held there.

Still open:

- the second 1000-id block per page (hypothesis: `INFORMATION` sub-records),
- the pharmacy/parking brand codes (the `BICON001` mapping is in
  [assets.md](assets.md); two generic glyphs are still unmapped),
- the bit-packed field block origin,
- the `body` grammar of a name record (48/88-byte variants measured, not
  decoded),
- `REFER002/POINT002.DAT` explicit `xy-coordinates` bits.

`BICON001` is a PNG container with 103 icons; see
[assets.md](assets.md).

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

Each of the 33 shards has the same skeleton:

```
0x000  512-byte common header
0x200  0x500-byte constant template, byte-identical in all 33 files
0x700  0xFF fill
0x1108 12-byte directory cells (name-initial table)
0x2000 6-byte cell array addressed by the directory
  I    zlib block chain -> 22-byte index records (20,000 per full block)
  S    exactly one 0x100-byte schema block
  R    zlib block chain -> variable-length address records
  T    zero padding, then the record-block TOC, then zero padding to EOF
```

- The `0x200–0x6ff` template is **constant across all 33 files**. The old
  “first non-FF at `0xac`” is a `00 00` slot inside it and carries no per-file
  information.
- Schema block signature: `ff ff 00 10 ff ff ff ff 00 00 00 00 ff ff ff ff`,
  exactly once, `0x100`-aligned. Fields: `STREET`, `area code`, `street name`,
  `dndc-id`. The record chain starts exactly at `S + 0x100`.
- Inner blocks are plain **zlib streams** (`78 01/5e/9c/da`) with 0–3 bytes
  padding, **no length prefix**. The index chain is preceded by an 8-byte
  `4e 20 00 00` header plus a `u32` offset array (300 B at `ADDRE021`, 604 B at
  `ADDRE033`); the record chain has no header.
- Index records: 22 bytes = 11 big-endian `u16`; full blocks are 440,000 B =
  20,000 records. `ADDRE003` carries 12 full blocks + one 108,768 B block
  (244,944 records); `ADDRE021` 73 + one 357,698 B block (1,476,259 records).

### 12-byte directory cells (`0x1108`)

```
struct addre_dir {
    uint8_t  initial;   // ASCII name initial: '1'..'9', 'A'..'Z', '\'', '/'
    uint8_t  zero;
    uint16_t count;     // number of 22-byte index records for this initial
    uint16_t block;     // 0 on single-block shards; 0..6 on large shards
    uint16_t offset;    // byte offset into the 6-byte cell array at 0x2000
    uint16_t length;    // byte length of the cell run (multiple of 6)
    uint16_t tail;      // 0, or 0xffff on the last row (sentinel length)
};
```

- Verified on `ADDRE001`, `ADDRE002`, `ADDRE003`, `ADDRE004`, `ADDRE005`,
  `ADDRE017`, `ADDRE021`, `ADDRE033`: every `initial` is printable and the
  sequence is the shard's name-initial set (Andorra `1A..VX`, Poland
  `1..9A..Z`).
- `count` sums to the 22-byte index-record count exactly on the two
  single-block shards (`ADDRE001` 2621/2621, `ADDRE017` 1616/1616). On larger
  shards the sum is lower (`ADDRE003` 179,408/244,944, `ADDRE021`
  689,827/1,476,259); why is **UNKNOWN** (hypothesis: only named index records
  are counted, or each index block has its own directory).
- `block` is zero on all rows of `ADDRE001`/`ADDRE017`; on large shards it is
  0,1,2,3 or 6. The cell base for `block > 0` is **UNKNOWN** and the tool does
  not decode those runs.

### 6-byte cells (`0x2000`)

Each directory run is an array of 6-byte cells. Two shapes are verified
(`ADDRE001`: 113 value + 20 pointer; `ADDRE017`: 99 value + 19 pointer +
1 empty; `ADDRE003` block 0: 0 unknown):

```
(0x0000..0x0003, value, count)   // value cell; first field is a small kind
(pointer, 0xff00, 0x0000)        // pointer cell; pointer is 6-byte aligned
```

- The base `0x2000` is proven by a control: `verify` at base `0x2000` finds
  0 unknown cells, at `0x1108` 133, at `0x1000` 121 and at `0x2010` 32
  (`tools/addre.py verify --cell-base`).
- Every pointer is a multiple of 6 and lands on another cell, so the array is
  a linked structure. The meaning of `value`/`count` is **UNKNOWN**: all 113
  values in `ADDRE001` are below the record-stream length, but only 1 lands on
  a record start and 2 on a name start — so they are not simple offsets into
  `R`; 0 of the 20 pointers lands on a value cell, so the link target is not
  the payload either.

### Address records (`c0` / `c8`)

- Both tags use the same framing: `tag + L`, record size **exactly `2*L`**
  (the old `c8 = 2*L-1` was the size minus one trailing `ff`).
- `ADDRE021`/`ADDRE033` additionally contain tag **`0xc1`** records whose
  body is a long point list and whose length is **not** `2*L` (`0x0f` at the
  observed sample, body ≈540 B). Their framing is `UNKNOWN`; `tools/addre.py`
  stops at the first one, so `verify` is claimed only for 001/017/003.
- **`c0` always carries a name section, `c8` never does** — 692/692 vs 0/349
  (`ADDRE001`), 249/249 vs 0/360 (`ADDRE017`), 56,988/56,988 vs 0/38,445
  (`ADDRE003`).
- Name section: `TT LL 00 ff` where `TT` is `0x03` on `ADDRE001`/`ADDRE017`
  and `0x04` on `ADDRE003` (per-shard), `LL = ceil(name_len/2)`. The name is
  the **last `2*LL` bytes of the record** (NUL-padded when `name_len` is odd);
  the 4–8 bytes between the marker and the name are a small header whose
  meaning is **UNKNOWN**.
- Coordinate id: first `TT ss` id token (tags `0x06`, `0x0a`, `0x12` observed)
  followed by 4 bytes: `x = id >> 16`, `y = id & 0xffff`,
  `lat = (x-32768)/192`, `lon = (y-52742)/128`. Verified against Andorra,
  Luxembourg, Monaco and Lazio.
- House-number ranges: token `prefix subtype 00 00 :N:;:M:` with
  `prefix ∈ {0x06, 0x07, 0x08}` and `subtype ∈ {0x54, 0x58, 0x64, 0x68}`.
  The **low nibble** of the subtype splits the token into two slots
  (4 vs 8) — the two sides of the street. Parity is **not** encoded by the
  subtype: Monaco (odd/even numbering) shows a 69 %/75 % parity bias per slot,
  while Andorra (consecutive numbering per side) shows none. `prefix`
  (`06`/`07`/`08`) is a second, still **UNKNOWN** class axis.
- Point tokens: `TT 40 XX YY` (4 bytes). `0x40` is a **constant marker**, not a
  sign; `TT` is a role tag (`0x02`/`0x03`/`0x04`/`0x05` for the primary
  start/end pair, `0x40`+8k for interior vertices, e.g. `0x40`, `0x48`,
  `0x50`, `0x60`, `0x80`, `0x98`, `0xb0`). `YY` uses the full 0–255 range in
  every shard observed (001/002/003/017); `XX` is capped well below 255 and the
  cap is shard-dependent (max 23/50/58, distinct = max+1). In simple 2-point
  (primary tag 2–5) segments the two endpoints share `XX` in 95.4 % (Andorra),
  97.7 % (Monaco) and 97.6 % (Bulgaria) of records, while in multi-point
  polylines `XX` varies between sub-segment groups (2.6 %/11.1 %/4.9 %
  constant across all points). `YY`'s 0–255 span is consistent with a
  1/256-packed-unit subdivision of one packed unit relative to the record's
  packed `coord` id, but **a 2D geographic `(lat, lon)` is not derivable from
  `(coord, XX, YY, tag)` alone** (M4.19, C-1960–C-1969): interpreting
  `(XX,YY)` as orthogonal fractions on fixed geographic axes contradicts the
  ~97 % same-`XX` (it would make simple segments axis-aligned, geographically
  implausible across countries), and ADDRE provides no independent 2D absolute
  position to anchor a frame (`COORD001` boxes are coarse and Monaco's is
  degenerate at 14 × 1 units with spilling ids). Control (wrong hypothesis):
  whole-unit addition `cx+XX, cy+YY` places only 14.0 % of Andorra points
  inside the region box (+2 margin, 304/2168) with median primary-segment
  length 7 packed units (~4 km); the fractional 1/256 candidate places 100 %
  inside with ~0.027 packed units (~16 m) but is **not a verified 2D
  geographic mapping** (axis/frame unknown). The exact `(XX,YY)` arithmetic
  (2D frame, axis assignment, and the meaning of `XX`) remains `UNKNOWN`.

### Trailer table (`T`)

- Located by the last `01 f4 00 00` marker in the file. Each row is 12 bytes,
  big-endian `(start, length, value)`; rows are **one per record zlib block**,
  and `start` is the cumulative sum of `length` (contiguous partition, 3/3,
  2/2, 191/191, 1377/1377 and 3893/3893 rows on the shards tested).
- Semantic (verified): `value` = **uncompressed block size / 2**
  (191/191 exact on `ADDRE003`, 3/3 on `ADDRE001`) and `length` =
  **compressed block size / 2**, within ±4 bytes because the packer counts
  16-bit words while streams are padded to 2/4-byte alignment. It is a
  random-access TOC for the record chain, not a coordinate index.

`REFER002` ships **no ADDRE at all**; only 15 of 33 POINT shards exist there.
`COORD001` table entry *i* is the region box of `ADDRE(i).DAT` (31/33 shards
100 % inside; two spill at borders; Monaco's box is degenerate, so it cannot
be used as a point-decoding control).

Still open: the 6-byte cell payload (`value`/`count`), the `prefix`
`0x06/0x07/0x08` axis of the range tokens, the `(XX, YY)` 2D frame / axis
assignment and the meaning of `XX` (2D geographic not derivable from
`coord,XX,YY,tag` alone; M4.19/C-1960–C-1969), the cell base for directory
`block > 0`, why `count` under-covers large shards, the 6 trailing bytes of
each `COORD001` entry, and the 22-byte index record fields.

Tool: `tools/addre.py` (`layout`, `table`, `cells`, `records`, `stats`,
`trailer`, `verify`, `--selftest`).

## What this means for the compiler

- Name strings (`ADDRE`, `POINT`, `LCTBL001`) are single-byte CP1252/Latin-1
  with letters outside Latin-1 transliterated by dropping the diacritic; the
  firmware's fixed field capacities and its own collation table are in
  [rdstm.md](rdstm.md#writer-rules-for-names-m39) (`EXP-2026-11-06-M3.9`).
  Do not write ISO-8859-2 bytes: the reader converts them as CP_ACP, so `č`
  would become a symbol, not a letter.
- Address/POI sharding is per country, so a `poland-full` profile touches
  shard 021 plus any neighbouring-country shards needed for whole tiles.
- POI records are bit-packed; the field dictionary must be read from the
  file, not hard-coded.
- The absence of coordinates in POINT means coordinates must come from
  `COORD001`/`REFER002`/tile links; the join is still unknown.
- `REFER002` is not a backup copy; it has extra EV fields. Do not overwrite it
  with a copy of `REFER001`.
