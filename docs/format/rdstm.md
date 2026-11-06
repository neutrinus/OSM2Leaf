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

## Status: what the sample supports

`tools/rdstm_schema.py` scores candidate framings and joins; it does not
decode fields. Splitting the two files' evidence by kind gives the table
below. Nothing in it is a decode: a score ranks a hypothesis, it does not
confirm one.

| Item | Status | Effect on the work | Evidence |
| --- | --- | --- | --- |
| 512-byte Clarion/Hitachi container header | VERIFIED | fixed preamble; structure starts at `0x1000` | `tools/rdstm_scan.py layout`, `tools/leafimg.py header`; C-010 |
| no zlib streams, no inline ASCII names | VERIFIED (negative) | names must be indices into `LCTBL001` | `tools/rdstm_scan.py zlib --bruteforce`; C-104 |
| 2-byte codes shared with the LCTBL catalog | VERIFIED | the two files are linked by code, not by pointer | `tools/rdstm_scan.py codes --lctbl`; C-105 |
| `0x1000` starts a table of ~16-byte rows | HYPOTHESIS | scanner default start; not a proven record size | C-106; `tools/rdstm_schema.py scan` |
| records below `0x1a700` are graph tuples | HYPOTHESIS | node/link shape, roles unchecked | `tools/rdstm_schema.py layout` |
| framing drift at `0x10a0` (`+14` → `+4`) | OBSERVED | one record size does not fit the whole file | C-106 |
| name-index mapping (code → LCTBL name) | UNKNOWN | the join rate is a bound, not a decode | `tools/rdstm_schema.py join` |
| speed / one-way / turn restrictions | UNKNOWN | routing cannot be built yet | C-108 (targeted scans negative) |
| synthetic scorer + join self-test | VERIFIED (tool) | the harness itself, no vendor bytes | `tools/rdstm_schema.py --selftest` |

Exact commands (vendor files are not in the repository):

```bash
python3 tools/rdstm_schema.py --selftest                    # no vendor data
python3 tools/rdstm_schema.py scan RDSTM001.DAT --top 12
python3 tools/rdstm_schema.py layout RDSTM001.DAT \
  --layout "link=0:u16:id,4:u32:ref,8:u16:src,10:u16:dst,12:u16:code,14:u16" \
  --record-size 0x10 --lctbl LCTBL001.DAT
python3 tools/rdstm_schema.py join RDSTM001.DAT --lctbl LCTBL001.DAT \
  --code-offset 0xe --record-size 0x10
```

`--json` prints machine-readable rows. The self-test is synthetic only, so the
table records status rather than measured scores. Run the three vendor
commands (or a copy with a different `--layout`) before quoting any number as
a measurement of the sample.

### Ranked unknowns

Routing needs the first three, and none of them is settled.

1. **speed / one-way / turn restrictions.** No field is known to carry them
   (C-108). They may not exist in this file at all; the tail 4-byte entries
   with `0x40/0x60/0x80/0xe0` tags are the only candidates observed so far.
2. **record size and framing.** The `0x1000` table drifts at `0x10a0`, so
   either the rows are variable length or the table ends there. A grid score
   cannot settle it; it can only show where a constant size stops fitting.
3. **graph tuple roles.** A `(src, dst)` reading of the `0x1a700` arrays is a
   hypothesis. `--layout` reports reciprocity and back references as
   diagnostics: high reciprocity is what a road graph should show, but other
   structures (index pairs, shared references) would score the same.
4. **name index.** Whether the 2-byte code indexes the LCTBL catalog, the
   name records or a class code is unknown; `join` only reports how often a
   code is a known LCTBL code, which is necessary but not sufficient.
5. **code position drift.** Why the code moves from `+14` to `+4` at `0x10a0`
   is unanswered; it is the main reason to distrust any single layout.

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
- The plain text is **not** a flat string table. It is 247,089 fixed-format
  **records** grouped into pages: each stream holds at most 500 records
  (487 of the 517 streams are full).
- Content is hierarchical: `Evropa` → `střední Evropa` → `Česká Republika` →
  `Praha` → `Hl. m. Praha` → `kraj` → `okres` → municipality → street.
- Last streams are Norwegian and French.

#### Record layout (verified)

Every record is a 16-byte header, four fixed-size name slots and an opaque
binary footer. All header integers are big-endian.

```
+0   u16  size_words   record size in bytes = 2 * size_words
+2   u8   marker       always 0x01
+3   u8   len1         name slot 1 size in words (0 = slot absent)
+4   u8   len2
+5   u8   len3
+6   u8   len4
+7   7 B  attributes   roles UNKNOWN (kept verbatim)
+14  u16  class        hierarchy level / record kind (semantics HYPOTHESIS)
```

Then four name slots, each exactly `2 * lenN` bytes. A slot holds a Latin-2
name padded to an **even byte length with `0x00`** — so an even-length name
fills its slot exactly and an odd-length name carries one trailing NUL. Two
consecutive names therefore have no separator when the first is even-length.
This is why a NUL-scan over the plain text miscounts: it sees padding, not
terminators.

The remainder (`size_words*2 - 16 - sum(2*lenN)`, 0–22 bytes, always even) is
a footer this repo has **not** decoded; `tools/lctbl_records.py` keeps it
opaque. `0x00` is common as its first byte.

#### Per-field counts and lengths (EU 2011)

| Field | Non-empty | Empty | Min | Median | Max | Slot max | Distinct |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 36,461 | 210,628 | 1 | 4 | 10 | 10 | 17,028 |
| 2 | 66,189 | 180,900 | 1 | 14 | 85 | 86 | 16,566 |
| 3 | 243,907 | 3,182 | 1 | 11 | 99 | 100 | 142,139 |
| 4 | 109,944 | 137,145 | 1 | 5 | 64 | 64 | 47,458 |

`Slot max` is the largest padded slot; `Max` is the longest actual name. The
record size ranges 18–170 bytes (mean 46.5).

Field roles are partly observed:

- **Field 3** is the record's primary name and is present in 98.7 % of records:
  the hierarchy names, municipalities and street names.
- **Field 1** holds road numbers (`D5`, `I/34`, `II/243`); 54 % match a
  road-number pattern. It is non-empty in 36,461 records across 299 of the
  517 streams; stream 1, a route list, is the clearest example.
- **Field 2** and **field 4** hold aliases/second names; fields 2 and 4 carry
  a road number in 1.5 % / 31 % of their values. Mapping them to the catalog
  columns (`road name`/`first name`/`second name`) is still a hypothesis.

The four slot-presence combinations in order of frequency:
`0010` 90,425; `0011` 60,598; `0110` 45,083; `1011` 28,268; `0111` 11,616;
`1111` 7,887 (1 = present).

#### Cross-year control

The same layout tiles the 2014 and 2016 samples exactly:

| Sample | Streams | Plain bytes | Records | Full 500-record pages | Max record |
| --- | --- | --- | --- | --- | --- |
| EU 2011 | 517 | 11,481,060 | 247,089 | 487 | 170 |
| 2014 | 665 | 16,233,466 | 329,296 | 651 | 228 |
| 2016 | 693 | 16,792,922 | 342,891 | 679 | 228 |

Field maxima grow to 10/85/118/118 in 2014/2016 (longer street names), but the
framing, marker, half-length encoding and 500-record page cap are unchanged.

Reproduce:

```bash
python3 tools/lctbl_names.py verify LCTBL001.DAT     # streams 517, plain 11481060, strings 328628
python3 tools/lctbl_names.py catalog LCTBL001.DAT
python3 tools/lctbl_records.py stats LCTBL001.DAT    # records 247089, per-field table
python3 tools/lctbl_records.py dump LCTBL001.DAT --stream 2 --limit 10
python3 tools/lctbl_records.py roundtrip LCTBL001.DAT --all   # every stream OK
python3 tools/lctbl_records.py verify LCTBL001.DAT   # totals + all-stream round-trip
```

The old `names` count (328,628 "NUL-terminated strings") is a string-scan
artifact: it counts text runs, not records. The canonical counts are 247,089
records and 456,501 non-empty name slots (C-1832, C-1839).


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
