# `RDSTM001.DAT` and `LCTBL001.DAT` (road data)

Sample: EU 2011 image
(SHA-256 `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`).

- `RDSTM001.DAT`: 23,335,680 bytes,
  SHA-256 `f822044c0aab75327b9fb484e9a4c7c8dd5938b21efaacec0e5b2d8b23ab3e49`
- `LCTBL001.DAT`: 7,489,024 bytes,
  SHA-256 `8cab17754114b5f7ca47d4f46d55c95c6acf841629e1fcc42e6da45063353e9d`

> **Evidence status:** block layouts and stream counts are `VERIFIED`;
> field semantics are `OBSERVED`/`HYPOTHESIS`; speed/direction/turn
> restrictions are `UNKNOWN`.

## `LCTBL001.DAT` — catalog + compressed name database

It is **not** a raw string table or a road-class lookup. It is a data
dictionary plus a zlib-compressed place/street name database.

```
0x000000  512    common Clarion/Hitachi header (text + binary @0x180)
0x000200  0xe00  0xff then zero fill
0x001000  0x3600 catalog: 90 x "Location Data" descriptors (+ 12 columns)
0x004600  0x312000 packed binary index/geometry (not decoded)
0x316600  0x40b1df 517 independent zlib streams -> 11,481,060 bytes
0x7217df  0x2e21 0xff padding to EOF
```

### Catalog (verified)

- 90 descriptors named `Location Data`, u16 LE name length at `+0x1e`.
- Three layout variants: 30 × 46 bytes, 30 × 376 bytes (with a 330-byte
  inline column block), 30 × 34 bytes.
- Each descriptor ends with a 2-byte code at `+0x1c`; the first 30 are sorted
  (`3219 3409 3501 … 4631`).

### Column schema (verified names, hypothesis semantics)

```
0 kind code        4 second name      8 positive offset
1 road no          5 area ref         9 urban
2 road name        6 liner ref       10 exit/junction no
3 first name       7 negative offset 11 Inter-section code
```

Each column descriptor stores a byte offset inside the road record
(`kind code` `0x23`, `road no` `0x2f`, `road name` `0x3c`, …), a `u32` type
word (`0x0180`, `0x0560`, `0x1360`, `0x1660`, meaning unknown) and a column
index.

### Name database (verified)

- 517 independent zlib streams, all decompress cleanly to EOF.
- Total plain size 11,481,060 bytes; compressed 4,234,414 bytes.
- 328,628 NUL-terminated **Latin-2** strings (231,033 unique); 11,827 match a
  road-number pattern (`N18`, `A21 - E34`, `B3232`).
- Content is hierarchical: `Evropa` → `střední Evropa` → `Česká Republika` →
  `Praha` → `Hl. m. Praha` → `kraj` → `okres` → municipality → street.
- Last streams are Norwegian and French.
- Record framing is partly decoded: 16-byte metadata block + `u16` class/level
  + NUL-terminated strings. The `u16` behaves like a hierarchy level
  (100 continent, 200 sub-continent, 300 country, 700 sub-region, 800 admin
  region, 900 district, 1000 municipality, 10500 street/POI). The meaning of
  metadata bytes `+0x01`, `+0x03`, `+0x07` and the 2-byte string prefix is
  **UNKNOWN**.

Reproduce:

```bash
python3 tools/lctbl_names.py verify LCTBL001.DAT     # streams 517, plain 11481060, records 328628
python3 tools/lctbl_names.py catalog LCTBL001.DAT
python3 tools/lctbl_names.py names LCTBL001.DAT --sample 10
```

## `RDSTM001.DAT` — uncompressed packed binary

**Negative result (verified):** no zlib streams. A sequential `78 9c` scan and
8,190 headerless raw-deflate/gzip probes over the first 2 MiB find nothing. The
file is dense structured binary; the largest zero run is 554 bytes. It has no
inline ASCII names, so road names must be indices into `LCTBL001.DAT`.

Observed layout:

```
0x000000  512    common header (descriptor 00 01 03 02 04 ff ff ff 02 ff ff ff)
0x000200  0x1ae  zeros
0x0003ae  0xfe   0xff
0x0004ac  0xb54  zeros
0x001000  table of 16-byte rows; last u16 = 2-byte code shared with LCTBL
0x01a700  u16 tuple arrays (ids + two references), 0x0000 separators
0x0640000 dense u16/u32 tables
0x12c0000 4-byte entries with 2-3 high control bits
0x15f0000 dense 4-byte entries to EOF
```

- At `0x1000`, 16-byte rows start `0001 0000 | 0203 016f | 0000 3002 | 0051
  3409`. 10 of the first 16 rows carry the same 2-byte code as the LCTBL
  catalog. The framing breaks at `0x10a0` (the code moves from `+14` to `+4`),
  so the real record size is **UNKNOWN**.
- The `0x1a700` arrays look like a node/link graph; the tail 4-byte entries
  carry tags `0x40/0x60/0x80/0xe0`, possibly turn/per-edge flags.

Reproduce:

```bash
python3 tools/rdstm_scan.py layout RDSTM001.DAT
python3 tools/rdstm_scan.py zlib RDSTM001.DAT --bruteforce
python3 tools/rdstm_scan.py codes RDSTM001.DAT --lctbl LCTBL001.DAT
```

## Tile linkage and grid

`MAPAL001/` covers the same geographic area as the names. External prior art
(`osm2clarion`, QY8x) gives a grid hypothesis that fits the name inventory:

```
B and R in BxxRyyR are hexadecimal.
lat_min = int(B, 16) * 2/3
lon_max = 108 - int(R, 16)
cell    = 5.333° (lat) × 8° (lon)
```

For `B48R058R`: `0x48` = 72 → lat 48–53.33 °N; `0x58` = 88 → lon 12–20 °E.
Prague (~50.08 °N, 14.42 °E) falls inside, and the Czech names are in the first
LCTBL stream. This is **supporting evidence, not proof**; the tile itself and
the mesh-code encoding still need decoding.

## Road attributes

| Attribute | Location | Status |
| --- | --- | --- |
| kind code | LCTBL column 0 (record offset `0x23`) | column verified; values unknown |
| road no | column 1 (`0x2f`) | column verified; values unknown |
| road/first/second name | columns 2–4 (`0x3c/0x49/0x57`) | column verified; name index mapping hypothesis |
| area / liner ref | columns 5–6 (`0x63/0x70`) | column verified; meaning unknown |
| negative/positive offset | columns 7–8 (`0x80/0x90`) | column verified; meaning unknown |
| urban | column 9 (`0x9b`) | column verified |
| exit/junction no | column 10 (`0xab`) | column verified |
| Inter-section code | column 11 | column verified |
| speed / direction / turn restrictions | not found | UNKNOWN |

`INTER`/`FRWAY` IDs were not located in these two files (see
[inter-frway.md](inter-frway.md)).
