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
`ICADM` and `ZCODE` share the 33-way split. `FRWAY` has **26** numbers on
EU2011 (missing `001,006,013,014,017,024,032`) and **11** on US2011 (`001..011`),
per `python3 tools/frway_decode.py census ROOT` (C-7837/C-7838; the older
"24 numbers" figure was a miscount).
`REFER002` is **not** duplicate data — it carries the longer EV schema
(xy-coordinates, plug info, parking capacity).

### Who opens `REFER002` (M3.40, EU 2011)

> **Status:** `OBSERVED (L3)` for the file opener/read path; the EV record
> consumer is still unlocated. Evidence: EXP-2026-11-24-M3.40-refer002-opener,
> C-8150–C-8159.

`Navi.exe`'s shared REFER search-type opener `fn 0x003fbed8` (pdata START,
prologue 22 B, length `0x214`, end `0x003fc0ec`) loads the **directory name**
`REFER002` (`0x001793a4`) into r12 at `0x003fbf40` and passes it to the
resolver `fn 0x0040b358` at `0x003fc086`; by default r12 is `REFER001`
(`0x00178c68`, loaded at `0x003fbeee`). The `0x14ef` / `0x14f0` context
selector is derived from the disassembly (LE, pinned in `sh4dis`): `ctx+104`
is one of those two words, `ctx+124 == 0`, and the word tested with
`and #0x4000` at `0x003fbf34` is nonzero — at `ctx+0xa0` for `0x14f0`, reached
through the pointer at `ctx+0xa4` for `0x14ef`. The generic read issuers
downstream are `fn 0x003f6c88` (read request) and `fn 0x0041841c` (layer read
API), not an EV-specific record reader.

Run the opener on the mounted EU 2011 factory card:

```bash
python3 tools/refer002_opener_l3.py run archive/head256.img \
  --card-image archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img
# boot ACCEPT; 15 REFER002/POINTnnn.DAT resolves, ids 0x00070002..0x00070010
# negatives: ctx+124=1 or flag=0 -> REFER001/POINT002.DAT (0x00060081)
```

With `ctx+104=0x14f0`, `ctx+124=0`, `ctx+0xa0=0x4000` it resolves all 15 EV
shards {2,4,5,7,8,10,11,16,18,19,20,22,25,29,33} as
`REFER002/POINT0nn.DAT` (file ids `0x00070002…0x00070010`), matching the
16-file on-card census. `ctx+124=1` or flag `0` selects `REFER001` instead;
`ctx+104=0x14e4` selects LCTBL. The two other `REFER002` strings —
`0x00178e4c` (volume-id table) and `0x0001ca9e` (a full `\SystemSD\REFER002`
path in `Vehicle.exe`) — have no literal-pool xref and are data/table entries,
not independent openers. No EV field-dictionary consumer or US 2011 twin is
located; the rule-13 level of this result is L3, not L4/L5.

### `REFER002` census (M4.85, EU 2011)

> **Status:** `OBSERVED` (file-level census and field schema; record-body field
> offsets still open — the shared POINT name-record grammar). Evidence:
> EXP-2026-11-22-M4.85-refer002-census, C-7860–C-7869.

`python3 tools/refer002_census.py census ROOT` reports the 16 files of the
EU 2011 layer (426,496 B, 880 facility records; US 2011 has 2 files / 1 record):

| file | zlib streams | record pages | records |
| --- | ---: | ---: | ---: |
| `COORD001.DAT` | 0 | 0 | 0 (projection companion, C-152) |
| `POINT002.DAT` | 3 | 1 | 33 |
| `POINT004.DAT` | 3 | 1 | 6 |
| `POINT005.DAT` | 3 | 1 | 9 |
| `POINT007.DAT` | 3 | 1 | 4 |
| `POINT008.DAT` | 3 | 1 | 121 |
| `POINT010.DAT` | 3 | 1 | 24 |
| `POINT011.DAT` | 3 | 1 | 4 |
| `POINT016.DAT` | 3 | 1 | 1 |
| `POINT018.DAT` | 3 | 1 | 172 |
| `POINT019.DAT` | 3 | 1 | 41 |
| `POINT020.DAT` | 3 | 1 | 24 |
| `POINT022.DAT` | 3 | 1 | 62 |
| `POINT025.DAT` | 4 | 1 | 206 |
| `POINT029.DAT` | 3 | 1 | 2 |
| `POINT033.DAT` | 3 | 1 | 171 |

Each `POINT0nn` is the `REFER001` POINT container (0x800 header, 299-cell
directory at `0x800`, zlib pages of `0x60`/`0x68` records) but carries a
**different field dictionary**: the *facility* dictionary has 11 fields, with
`xy-coordinates`, `point of arrival` and `tie-up parking` where REFER001 has
`icon code`. `plug info`, `parking capacity`, `installed facility` and
`user limitation id` are declared in the `INFORMATION` sub-schema.
`schema ROOT/POINT002.DAT` prints the table below (type `0x8000` coded,
`0x6000` text in the record tail, `0x2000` trailing rest):

| id | field | type | length (words) |
| ---: | --- | --- | ---: |
| 0 | area code | 0x8000 | 5 |
| 1 | category | 0x8000 | 1 |
| 2 | sub-category | 0x8000 | 1 |
| 3 | detailed code | 0x8000 | 1 |
| 4 | index | 0x8000 | 0 |
| 5 | facility name | 0x6000 | 19 |
| 6 | address | 0x6000 | 14 |
| 7 | dndc-id | 0x2000 | 0 |
| 8 | xy-coordinates | 0x8000 | 0 |
| 9 | point of arrival | 0x8000 | 1 |
| 10 | tie-up parking | 0x8000 | 1 |

The field dictionary is a C-block (`ff ff u16 word-offset` to a header with
`u16 first-word @+24`, `u16 nfields @+26`; entries chained by the `u16` at `+0`,
`0xffff` = last, with `id @+12`, `len @+14`, `name @+16`) — the same chain the
`fn 0x003f51e0` name accessor reads (see "Field dictionary" under POINT below).
The record *body* field positions are **not** decoded here: the 48/88-byte name
record grammar is still open for REFER001 too.

### Writing a charging station to `REFER002` (M5.79)

> **Status:** `VERIFIED` (tool, EU 2011 POINT016; C-10100–C-10109).
> Evidence: EXP-2026-11-24-M5.79-refer002-write-first-record.

`REFER002` is stored on the card as **plain uncompressed `.DAT` files**
(`roadmap.md`; the `l2check` golden is `REFER002/COORD001.DAT`), not as
`.cmp`/`.ind` pairs — `cmpind.py verify` on a REFER002 tree reports
`no .ind files`.  All 880 EU 2011 facility records across the 15 POINT shards
carry tag `0x60`; there is no `0x68` template.

`tools/refer002_add_station.py` adds one record to a factory `POINT0nn.DAT`:

1. inflate the name-page stream (POINT016: `0x1a00`, 112 B → 114 B);
2. clone the factory `0x60` record verbatim (POINT016: 114 B, `len2=57`);
3. replace **only** field 5 (`facility name`) through
   `mutate_refer_poi.field_layout(rec, 11)`: POINT016 has `starts[5]=68`,
   `lens[5]=10`, so the safe swap window is `rec[68:88]` — **20 bytes**.
   The new ASCII name must have exactly that length.  Do not swap the whole
   display text (`\x02\x11` prefix and the address at `rec[88:110]` are
   separate fields; changing their length needs the UNKNOWN body offsets,
   C-7866, and reproduces the M5.52/C-5117 stale-length defect);
4. append the clone to the same inner page (114 → 228 B), recompress that one
   stream with stock zlib 1.3.1 (factory L6/m8/w15), and require it to fit
   before the next aligned stream (POINT016: 137 B in a 256 B slot at
   `0x1b00`).  All other bytes, including the `.DAT` logical size, are kept.

The census then reads one more record (POINT016 1→2, tree 880→881).  The
only per-record index observed is the **24-byte-per-record stream at
`0x1108`**: POINT016 has one 24-B row, and on all 15 shards the stream length
divided by 24 equals the record count.  There is **no separate count field**,
so this writer does not change the index (the task's literal falsifier — a
stale numeric count — does not fire).  The new record therefore has **no
index row**: this is a real gap, not a pass of index writing.  The row's last
word is the 0-based record ordinal; words 0–5 are a per-record name key that
is not found verbatim in the record body and remains UNKNOWN (new M4 task).  L1 (`cardcheck`) and L2 (`l2check`) pass on the edited
tree; the position is inherited from the host record (no OSM coordinate is
written), and the row-24 firmware opener is still unlocated (M3.29), so no
L3/L4/L5 acceptance is claimed.

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
  contains a 4-byte id (two `u16`, "copy A") followed by two 11-bit fine
  fields; together they give the position to about 1 m — see
  [Fine POI position](#fine-poi-position-and-the-map-of-a-point-file-m427).
  The older reading `lat = (x-32768)/192`, `lon = (y-52742)/128` treats the
  id as a 1-unit coordinate and is 1.5–7 km off (the low nibble of each word
  is `11xx`, not four position bits). A second copy of the id follows at
  bytes 12–15 and can differ (e.g. by `(8,8)` in Vatican records).
- Each facility name is bracketed by a 16-bit category code and a 16-bit
  brand code (last two bytes of the record). The brand code selects the
  `BICON001` logo; see [assets.md](assets.md) for the verified table.

### POINT page chains and chain tables (M5.26)

> **Status:** `OBSERVED` on EU 2011 (33 files) and US 2011 (11 files);
> not yet tied to a firmware reader (C-2950–C-2953).

Inner zlib pages of a POINT `.DAT` are stored as **chains**: each chain
starts at a 0x100-aligned base and its pages follow back to back, each
padded with zeros to a 4-byte boundary. Every chain is described by a
**chain table** at a 0x100-aligned offset after it (all integers big-endian,
lengths in 16-bit words):

```
u16 per_page      // 1000 (name pages), 400, 2000 — the three chains of every file
u16 0
n × { u32 start_w,   // page offset from the chain base
      u32 comp_w,    // stream length rounded up to 4 bytes
      u32 inner_w }  // inflated page length
// start_w[i+1] = start_w[i] + comp_w[i]
```

- Every file of both builds carries exactly three tables (per_page 400, 1000
  and 2000); the 1000 chain is the name chain. US 2011: 8,229 name pages,
  the same count M5.21 edited by pattern.
- Every page of every chain walks exactly with the firmware record walk of
  `fn 0x003f5194` (EU2011, C-2540): BE `u16 w`, size `2*(w & 0x3ff)` bytes.
  The `ff ff` record end of the section below is **not** universal (6 of the
  16 EU POINT010 name pages fail it); the 10-bit length is the rule.
- The table holds no chain base and no absolute offset. The base and the
  table are found through the **chain locator** below (M4.47).
- Free space after a chain (up to the next non-zero byte) is 24–248 B per
  name chain: 3,656 B over 33 EU files, 1,460 B over 11 US files.
- `tools/point_pair_regen.py` re-packs a chain in place from these tables;
  index chains (`4e 20 00 00` + `u32` word lengths, as in `ADDRE`) are a
  separate structure and are not covered.

### POINT chain locator: block addresses, directory, descriptor records (M4.47)

> **Status:** `OBSERVED` on EU 2011 (33 files, 99 chains) and US 2011 (11
> files, 33 chains) (C-5390–C-5395); firmware reader `VERIFIED (L3)` in both
> builds, a relocated name chain read at its new base (C-5396–C-5399, M4.52).

A POINT `.DAT` addresses its structures in 256-byte blocks with a **block
address** (BE `u32`):

```
addr = (offset / 0x800) << 8 | (offset % 0x800) / 0x100   // 2-KiB sector, block 0..7
offset = (addr >> 8) * 0x800 + (addr & 0xff) * 0x100
```

- **Directory** at `0x800..0xf06`: 299 cells of 6 bytes `u32 addr, u16
  blocks`; an empty cell is `ffffffff 0000`. Six or seven cells are used
  (`0x824` → the `0x1000` record, `0x82a`, `0x85a`, `0xe84`, `0xe8a`,
  `0xe90`, `0xeba`).
- Cell **`0x82a`** (2 blocks) points to the record that starts `ffff 0015`:
  the **field dictionary** block that the name accessor reads (M3.11c,
  `D = C + 2*u16[C+2] = C+0x2a`). It sits 0x200 before the name chain.
- Cell **`0xeba`** (1 block) points to the record 0x100 before the 2000 chain.
- Inside these records each chain has a **base reference** `u32 addr(base),
  u32 chain length in words` and a **table reference** `u32 addr(table), u32
  table length in words, u16 per_page`:

| Chain (`per_page`) | Cell | Base reference | Table reference |
| ---: | --- | --- | --- |
| 1000 (names) | `0x82a` | record `+0x2e` (= `D+4`) | record `+0x19a` |
| 400 | `0x82a` | record `+0x13c` | record `+0x1b6` |
| 2000 | `0xeba` | record `+0x24` | record `+0x94` |

- The layout is the same in all 44 files; each of the 264 references occurs
  exactly once in its file. Example, EU `POINT010`: cell `0x82a` =
  `000d4f05 0002` → record `0x6a7d00`; `+0x2e` = `000d4f07 0004d372` → base
  `0x6a7f00`, 632,548 B; `+0x19a` = `000e9a00 00000062 03e8` → table `0x74d000`.
- The header holds no file length, so a chain may be appended at the end of
  the `.DAT` (`point_pair_regen.py relocate`: new base at the next 0x100
  boundary, base reference and table rewritten, old chain zeroed).
- **Firmware reader (M4.52).** The header parser `fn 0x003f930c` (EU2011) /
  `0x00421c3c` (US2011) decodes the directory cells with the leaf
  `0x0040f00c` / `0x00436f58` (`(w0<<11) | ((w1>>5)&0x7f8) | (w1&7)` = block
  number, on native u16); cell `0x82a` lands in object `+24`. The POINT page
  loader `fn 0x003fe2d4` (EU2011) / `0x00426480` (US2011), called by
  `fn 0x003ffce0` / `0x00427e1c`, takes the dictionary record from
  header-table entry `+64`, decodes the base reference `D+4` with the same
  leaf, adds `start_w` of the requested page and reads `2*comp_w` bytes there.
  Run in PySh4 on `relocate` output it requests the new base and record 1
  matches; with the reference left at the old base it requests the old bytes
  (`tools/point_locator_l3.py`, C-5397, C-5398).

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

Consequence for a rename: a different-length name needs the record's
`len2` byte and the field-5 length byte updated (see the next section); the rest of the page shifts, and the `.DAT` logical
size does not change because the page keeps its absolute offset. The byte
delta must be **even**. The recompressed page must still fit in the space
before the next stream (POINT032 page `0x4200`: 655 bytes used, next stream
at `0x4500`, 768 bytes reserved). `tools/mutate_refer_poi.py --resize`
implements this and refuses anything else.

### POI name field (firmware view, M3.11c)

The firmware does not split the display text at a delimiter. Each `POINT` `.DAT`
carries one **field dictionary** block (US2011 `POINT010` at `.DAT` offset
`0x749500`, EU2011 at `0x6a7d00`; 9 fields, `facility name` = field 5,
`address` = field 6). Each record's field area starts with one **length byte
per field** (in 16-bit words). The name accessor (`fn 0x003f632c` EU2011) adds
those lengths up to find field 5. On US `POINT010` record 0 this gives
`HANA HEALTH CENTER` (9 words at `+0x5e`), and the address `4590@HANA HWY\0`
follows as field 6. A renamed record must keep these length bytes consistent with
the new text. A same-length rename is safe; a different-length rename must also
change the name's length byte. In the file-order record the length of field `f`
is byte `loc + f`, `loc = 2*((hi+lo)+8)` of `u16[rec+10]` for header class 3/2
(`fn 0x003f5e10` reads the high byte for even `f`); on the US and EU `POINT010`
name pages all 2000 records are class 3 (C-5260). `mutate_refer_poi.py --resize`
patches both `len2` and that byte, and the accessor then returns the whole new
name and the unchanged address for −2, 0, +2 and +10-byte renames (M5.52,
C-5261). Evidence: EXP-2026-11-19-M3.11c-point-name-accessor-l3, C-5110–C-5117;
EXP-2026-11-19-M5.52-resize-field-len, C-5260–C-5265.

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
  decoded). **OBSERVED (M4.8d, C-2930–C-2932):** in zlib-framed `0x60`/`0x68`
  records, `v6 = rec[6..7]` is always `0x0800 | p6` with `p6 = v6 & 0x7ff`
  spanning 0..2046 (11-bit, bit 11 set) and `v8 = rec[8..9]` spans 0..2046
  (two 0..2047-class fields between copy A and copy B); `v16`/`v20` are
  2047-class but discrete (`{576,1088}`, `{512,576,832,1024,1088,1344}`).
  `(p6,v8)` does **not** encode a tile-local geographic position of copy A at
  scale 1 or 2 (negative, C-2931). **Solved by M4.27 (C-2679):** they are the
  fine position inside a 4-unit sub-cell of copy A, 512 steps per packed
  unit (`p6` longitude, `v8` latitude); see "Fine POI position" below.
- `REFER002/POINT002.DAT` explicit `xy-coordinates` bits.

### Fine POI position and the map of a POINT file (M4.27)

> **Status:** `OBSERVED` on EU 2011 (33 files, 937,131,520 B decoded) and
> US 2011 (11 files, 2,608,416,256 B) (C-2676–C-2679). The position
> formula is `VERIFIED` against the firmware on EU 2011 (M3.34,
> C-6540–C-6545, below); the spatial tree is read by the nearest-POI search
> and that code agrees with this reading on 237 factory trees (M3.35,
> C-6830–C-6839, below); a writer does not use it yet (M5.63).

**Firmware reading (EU2011, M3.34).** `Navi.exe` fn `0x003c032c` builds a
mesh point from a name record — `id = bytes 2–5 & 0xfff3fff3` (the `11` of
each `11xx` nibble is a marker the reader strips), `x = word 6 & 0x7ff`,
`y = word 8 & 0x7ff` — and `STDDLL!STD_MeshPnt_chgMapPnt` turns it into
1/512″ units: one mesh is 1/48° of latitude (high half, `y`) by 1/32° of
longitude (low half, `x`), 2048 fine steps each. This is the formula below
with origins 32768 / 52736; the integer result is within 1 unit (6 cm) of
it. `tools/poi_position_l3.py run` checks a pair against the firmware code.

**Every byte of a POINT `.DAT` belongs to a structure reached from the
directory.** `tools/point_census.py census` walks them all; no byte is left
over in any of the 44 files. Share of the decoded bytes, EU / US:

| Class | Reached from | EU | US |
| --- | --- | ---: | ---: |
| name tries | cells `0x824`, `0xe84`, `0xe8a`, `0xe90` | 22.5 % | 30.6 % |
| index chains | each trie descriptor | 7.5 % | 10.0 % |
| spatial trees | cell `0x85a` | 55.8 % | 35.4 % |
| phone B-tree | cell `0x82a` record `+4` | — | 5.0 % |
| page chains 1000 / 400 / 2000 | cells `0x82a`, `0xeba` | 12.8 / 0.8 / 0.4 % | 17.3 / 1.5 / 0.04 % |
| header, directory, descriptors, tables, fill | | 0.2 % | 0.06 % |

**Structure reference** (inside a descriptor record; lists chain entries
with a leading `u16 next_w`, `ffff` on the last):

```
u32 block address   // of the trie or tree
u32 length in words
u32 0
u16 root node size in words
u16 flags           // 4c40: trie + chain of 12-word records; 4d40: 9-word
                    // records; 8000: spatial tree (no chain)
u32 block address of the index chain, u32 inflated words   // not for 8000
```

**Name trie** (spelling search; one for the whole file at cell `0x824`, one
per category `0xe84`, per sub-category `0xe8a`, one for area names `0xe90`).
A node is a run of 12-byte entries:

```
u32 off_w, u16 size_w, u16 0, u8 char, u24 count      // child or leaf
u32 index_off_w, u32 parent_node_off_w, ff 00, u16 n  // last entry of a node
```

`size_w > 0`: the child node is `size_w` words at `off_w` (from the trie
start). `size_w = 0`: `off_w` is a word offset into the trie's index chain.
The nodes tile the region exactly.

**Index chain**: `4e20 0000`, `n × u32 comp_w`, then `n` zlib streams of up
to 20,000 fixed records. The 12-word record is the sort key of a name
record plus its ordinal (`u32` in words 10–11, 0-based over the name chain);
words 0–1, the words 2–5 that are not `ffff`, and words 7–8 occur verbatim
in that name record just before the name (all 28,295,255 records of the
cell-`0x824` chains checked). It
holds no position. The 9-word record ends with the ordinal of a 2000-chain
(`ADM`) record.

**Spatial tree** (one per category): 16-byte entries
`0008, u32 ptr, u16 size_w, u16 kx, u16 ky, u32 fine`, a node ends with
`0005 ffffffff u32`. Levels 0, 1, 2 are keyed by the copy-A id with the low
7, 4 and 0 bits cleared; some trees add a level keyed by a category code.
A leaf (`size_w = 0`) has `ptr` = name-record ordinal and `fine` = that
record's bytes 6–9 with flag bits on top (usually `0x8800 | fine_lon`,
`0xf800 | fine_lat`). Checked for all 10,718,316 leaves of both builds.

**Firmware reading of the tree (EU2011, M3.35).** The tree is read by the
nearest-POI search of `Navi.exe` (`tools/point_tree_l3.py` runs it):

| Function | What it reads |
| --- | --- |
| `fn 0x0040f944` child loader | inner entry `ptr` (`+2`), `size_w` (`+6`), key `kx`, `ky` (`+8`, `+10`); child = block `(ptr >> 7)` after the tree base, `((ptr & 0x7f) + size_w + 127) >> 7` blocks of 128 words |
| `fn 0x004110dc` step | entry `index` of a node, each entry `2 * word 0` bytes; levels `0x1001` (root node) … `0x1005` (category node) |
| `fn 0x004114dc` node walker | ends at the first entry with word 0 below 8 (`0005`); at the cell node an entry without `word 6 & 0x0800` is inner; leaf: `x = word 6 & 0x7ff`, `y = word 7 & 0x7ff`, code `((word 6 & 0x8000) \| (word 7 >> 1)) >> 10`, `ptr` = name-record ordinal |
| `fn 0x00408ea4` distance | `STDDLL!STD_MeshLine_calcLength` from the search origin; results (at most 128) in `0x00d5d800` |

A leaf is kept only when its code is 0, 63 or equal to the global
`*0x005638ec`. The usual `0x8800 | fine_lon`, `0xf800 | fine_lat` is code
63; factory trees also carry leaves with codes 2–10, which the search skips
while the global is 0 (C-6836). M3.37 (C-6970–C-6979): `fn 0x003f2f98`
writes request-indexed `*0x005638ec/0x005638f4/0x005638fc` (`r8*4`, request
`+0x0c/+0x10`), so the code is request/setup state, not a tree constant. EU
census: 2,653,215 leaves, codes {63:2631890,6:3414,4:3356,5:3064,10:3061,
7:2866,2:2803,8:2761}, 4,945 same-position multi-code positions / 2,532,220;
meaning remains HYPOTHESIS (variant/language/brand selector). Root loader
`fn 0x0040f674` runs in L3 and sets `*0x00d5b858` to the expected tree base on
`POINT010` tree 0, but full descent needs more seeded request state (BLOCKED).
US2011 twins: LOAD_CHILD `0x437774`, STEP `0x438f0c`, WALK `0x43930c`,
DISTANCE `0x430fa4`, ROOT_LOAD `0x4374a4`, DRIVER_A `0x439dac`, DRIVER_B
`0x43a134`, SETUP_338 `0x437168`, SETUP_2FC `0x43712c`, WRITER_255c
`0x41aefc`; EU `fn 0x003f2f98`/US `*0x005638ec` filter equivalent not found by
direct signature/VA scan. So a written leaf needs the `0x0800` flag, code 63,
the ordinal, the two fine values, and a `0005` terminator after the node's
last entry. Checked on 5 files, 237 trees, 8,475 cells (C-6838).

**Phone B-tree** (US only): 0x1000-byte nodes of 16-byte entries
`u32 child_w, u32 name ordinal, 8-byte BCD number (f-padded)`. The number
equals the one in the `INFORMATION` record of that POI (7,018,762 keys).

**400 chain** = one `INFORMATION` record (postcode, telephone number, ASCII)
per name record whose tag is `0x60`, in the same order (a `0x68` name record
has none). **2000 chain** = `ADM` records (area code, language type, area
name).

**Fine position.** The copy-A words are not 1-unit coordinates: their low
nibble is always `11xx` (two marker bits, then a 4-unit sub-cell index), and
bytes 6–9 of the record refine the sub-cell in 1/512 unit:

```
u(v, fine) = (v & ~15) + 4 * (v & 3) + fine / 512        // packed units
lat = (u(A.x, rec[8..9])          - 32768) / 192
lon = (u(A.y, rec[6..7] & 0x7ff)  - 52736) / 128         // tile origin
```

One step is 1/98,304° of latitude (1.1 m) and 1/65,536° of longitude.
Against the 16 reference POIs of M4.8b the median error is 115 m (8 within
100 m, the far ones are airports), against 3,558 m for the 1-unit reading;
it is closer for 16 of 16, and exchanging the two fine fields gives 1,568 m.
The longitude origin is the tile origin 52736; the "52742" of the older
formula absorbed the average of the marker bits. `point_census.py
encode_position` is the inverse for a writer.

### Writing a new POI (M5.82)

`tools/point_add_poi.py` adds one synthetic POI to a copy of the EU 2011
`POINT010` pair. It clones a `0x68` name record (a `0x60` template would also
need a 400-chain `INFORMATION` record), replaces its field-5 name bytes and the
copy-A/fine words from `coord.encode_point_id`, then makes three local writes:

1. the grown 1000-page chain is relocated through its locator (M4.47) to the
   next 0x100 boundary — the firmware page loader follows the new base;
2. one 16-byte spatial leaf (`0008, ptr, 0, kx, ky, fine`, `0x0800` flag, code
   63) is inserted before the terminator of the host's depth-3/4 leaf node,
   consuming part of the zero gap to the next node; the parent entry's `csize`
   grows by 8 words;
3. one 24-byte index key is appended to the last name-trie index stream, using
   8 of its 76 B of slack, and the descriptor's `chain_words` is bumped.

The new record's ordinal is the global record index (15,469 on POINT010); it
is page-local 469 on the relocated last page, which is the `n` passed to
`point_walk_l3.py`. Verified on the factory pair: census `unaccounted=0`,
`joins hold` with 15,379 leaves and 35,527 keys, `cmpind verify` PASS,
`point_walk_l3` PASS on the new record, and `point_tree_l3` ACCEPT on the
modified tree. No trie leaf or L4/L5 run yet (EXP-2026-11-23-M5.82).

### Where POINT coordinates are, and are not (M4.37)

> **Corrected by M4.27 (C-2679):** the statement below that no field is
> finer than one packed unit holds for the bit pages only. The name record
> itself carries the fine position (bytes 6–9) and the spatial index leaves
> repeat it; see the section above.

**OBSERVED (EU 2011, POINT002/008/029; C-3750–C-3754):**

- The non-name zlib inner pages ("bit pages": phone, `w0=2` mixed,
  24-byte index, keyword) carry **no coordinate pair** in the COORD001 form
  at any of 32 alignments (BE/LE words, bit phase 0..15): 0 of 1,212 pages
  pass the region-bounds test, while the `78 9c` name page control passes.
  The 24-byte index records start with `w0 = shard - 1` and end with the
  POI id `f11`; the keyword pages are variable records
  `len_words, 0x0401|0x0501, xx ff, w0, …, ASCII`.
- The non-stream ("raw") part of the decoded `.DAT` holds a **spatial
  index**: 16-byte records `00 08 | u32 | u16 | x | y | 00 00 00 00` (the
  first word reads as a C-2129 header: type 0, 8 words). Their finer
  `(x, y)` equal name-record **copy A** (every distinct copy-A id of each
  shard occurs; 92.6–100 % of the finer pairs are copy-A ids, a +37-unit
  shift gives 0 %), and a coarser level sits on a 16-unit lattice from the
  tile origin 52736 (1/12° × 1/8°). No field finer than one packed unit
  and no 0..2047 tile-local field was found: POINT positions are copy A
  (and B) only. `tools/point_bitpack_decode.py --coord-test`, `raw-index`.

`BICON001` is a PNG container with 103 icons; see
[assets.md](assets.md).

## `INTER0nn` — intersections

- Table 1 at `0x1108`, behind an 8-byte block header; records start at `0x1110`.
- **12-byte records, big-endian** (corrected by M3.16, C-2215): `u16 key`,
  `u16 0`, `u8 id`, `u8 flag`, `u16 length`, `u16 b8`, `u16 offset`. The
  `0xffff` **key** at record +0 is the terminator. `u16@+2` is 0 in every
  factory record; `u8 flag` and `u16 b8` are variant fields (b8 is nonzero in
  25/35 INTER002, 8/29 INTER003, 23/31 INTER004, 25/36 INTER005 records; flag
  is nonzero in 4 INTER005 records). `tools/inter_table.py check` validates
  all ten EU INTER/FRWAY shards (`OK`, exit 0).
- Offsets index blob 0, whose 6-byte elements are `FFFF…` (empty),
  `4000 0000 XXXX` (node ref) or `0000 a b` (attribute).
- `key` and `length` meanings are `UNKNOWN`.

### Offline field census (M4.81, C-7820–C-7829)

**FACT (tool):** `python3 tools/inter_decode.py --selftest` and
`census ROOT` reproduce the big-endian table above from a committed tool
(`>HHBBHHH` fields, `0xffff` key terminator, `u16@+2 == 0` on every record of
all shards). The census covers **33 EU shards / 976 records / 303,629,312 B**
and **11 US shards / 385 records / 225,175,552 B** (44 shards, 1,361 records,
528,804,864 B total). See
`EXP-2026-11-22-M4.81-inter-decode.md`.

| Field | EU range (nonzero) | US range (nonzero) |
| --- | --- | --- |
| `key` (+0) | `0x0..0xde` (912/976) | `0x0..0xde` (384/385) |
| `id` (+4) | `0x2f..0x5a` (976/976) | `0x30..0x5a` (385/385) |
| `flag` (+5) | `0x0..0x7` (23/976) | `0x0..0x1` (6/385) |
| `length` (+6) | `0x1..0xf7f0` (976/976) | `0x2..0xf878` (385/385) |
| `b8` (+8) | `0x0..0xb3` (504/976) | `0x0..0x47` (281/385) |
| `offset` (+10) | `0x0..0xff60` (943/976) | `0x0..0xfed8` (374/385) |

`id` is always nonzero; `flag` and `b8` are the sparse variant fields. Every
`offset` fits inside its own file, so it indexes an in-file structure.

**FACT (bytes explained):** the census reaches **87.416 % EU / 89.494 % US /
88.301 % both** of the bytes (worst shard 80.62 % EU INTER001, 80.88 % US
INTER011), well above the < 50 % falsifier. It counts the 512-byte header,
the table run, every `4e20 0000` index chain and standalone zlib page whose
streams inflate to `eof`, and zero/`0xff` fill. A mutated `u16@+2` byte
(`census ... --mutate-byte 0x1112`) drops EU INTER001 from 21 records to 0 and
its table span from 272 B to 8 B, so the walk detects a broken layout.

**HYPOTHESIS (not decoded):** the unexplained residue — EU 38,207,922 B
(12.584 %), US 23,655,988 B (10.506 %), dominated by bytes `0x01`, `0x0c`,
`0x02`, `0x12` — is the post-table region of 12-byte locator records and 6-byte
blob elements described above. Its field meanings are still `UNKNOWN` (M3.16,
C-2217–C-2219); the census names and histograms it, never guesses it. No
field-consuming firmware reader is located (see below), so the access-path
FACT below still covers file-level resolution only.

> **The pre-M3.16 little-endian layout is refuted (C-2216).** `refer.md` had
> written `u8 id, u16 n, u16 0, u16 offset, u16 length (6*k), u16 0` as
> **little-endian** (that sums to 11 bytes, not 12), with the `0xffff`
> terminator at +8. Read from the factory bytes, the doc's "`u16 0` at +3" and
> "`0xffff` length at +8" hold in **0** of the 177 records (over all ten EU
> shards, `python3 tools/inter_table.py refute`), while the big-endian
> `u16 key`/`u16 0` at +0/+2 holds in all of them (177/177). The earlier
> writer-inverse signature (`mov.w @(8,Rm)` near `cmp/eq #-1` + `add #12`)
> tested the wrong offsets, which is why it found 0 candidates (C-2211 did not
> test the real shape).

### Firmware access path / reader search (M3.16, build A, IMG256 `92aa525d…`, negative for content reader)

**Access path (FACT, shared REFER001 family):** `INTER0`/`FRWAY0` are members of
the volume-id table at `0x00179338` (`INTER0` file `0xdf754c` / ~VA
`0x0017934c`, `FRWAY0` `0xdf7554` / ~VA `0x00179354`, adjacent to
`ADDRE0`/`POINT0`; C-881/C-2210). File-level resolution uses the same REFER001
mechanism as POINT/ADDRE (C-880/C-2180): descriptor type `0x14e8` in
`fn 0x004125a8` (Navi.exe sec0) maps to `REFER001` (`0x00178c68`) +
`INDEX003.DAT` (`0x0017a118`) via `jsr 0x0040b358`; the volume-id table is
selected through the `fn 0x003fbed8` name-builder / `fn 0x0040b358` volume-
lookup path. Navi.exe has 0 compressed executable sections (C-2128).

**Content reader / consumed fields (NOT FOUND, M3.16 stop):** No reader VA that
consumes the real 12-byte table (big-endian `key`/`length`/`offset`) was
identified in decodable build-A Navi.exe. Four signature families over sec0
(5,553,664 B stored / 5,553,430 B vsize, `python3 tools/inter_reader_scan.py
scan archive/head256.img`) — the two of r2, plus (3) `mov.w @Rm,R0` + `add #12`
+ `cmp/eq #-1` (1 candidate, `0x00392122`, a byte `@(1,Rm)`/`0xff` walker, not
the u16-key table), and (4) `mov.w @(10,Rm)` + `mov.w @(6,Rm)` + `add #12`
(0 candidates) — put no function on both `0xffff`-at-+0 and the +6/+10 fields.
f1 (`mov.w @(8,Rm)` + `cmp/eq #-1` + `add #12`) and f2 (`0x1108` construction)
return 0. L3 read-watch of the M3.23 candidates on the factory INTER001 page
attributes only generic context reads (`0x00407724` at +0x0..+0x1c; `0x003f0aec`
a `u16` at +0x0; the rest fault on an unmapped null target), not record bytes.
Consumed-field mapping is `UNKNOWN`. The
`0x003f51e0` tagged field-dispatch resolver (POINT/ADDRE/RDSTM, C-884/C-2184)
is not the same record form. See
`EXP-2026-11-08-M3.16-inter-frway-readers-r2.md` (C-2210–C-2214) and
`EXP-2026-11-20-M3.16-inter-frway.md` (C-2215–C-2219).

## `FRWAY0nn` — freeways/routes

- Same 12-byte big-endian table (corrected layout above): an 8-byte block
  header at `0x1108`, then records from `0x1110` (`u16 key`, `u16 0`, `u8 id`,
  `u8 0`, `u16 length`, `u16 0`, `u16 offset`), `ffff` key = terminator
  (C-2215/C-7832). A name-initial directory of 12-byte rows starts at
  `terminator+0x10` (`u8 code`, `u8 0`, `u16 count`, `u16 block`, `u16 offset`,
  `u16 length`, `u16 tail`) (C-7833).
- Before the table: a 512-byte CLAR header, the shared `0x200..0xfff` fill, and
  a 0x108-byte type block at `0x1000` whose marker words `u16@+0=ffff`,
  `+4=0201`, `+0x10=4d40`, `+0x32=0601` hold in all 37 factory shards
  (C-7831). After it: zlib streams with `4e 20 00 00 | u32` headers, one index
  stream, one route stream (`A1`, `E70`, `E773`…, records tagged `0xa0`) and
  1…25 main streams framed by `2*(u16 & 0x3ff)`; a schema dictionary decodes to
  `["area code", "route number"]` in every shard; two `0x100` blocks end the
  file (C-7834/C-7835).
- `tools/frway_decode.py census ROOT` reproduces the walk, the record counts,
  the per-field value ranges and the byte accounting: EU2011 26 shards,
  101 table/94,040 main/1,322 route records, 2,908,874/2,921,728 B explained
  (99.56 %); US2011 11 shards, 58/162,124/3,000 records,
  5,136,449/5,141,760 B explained (99.90 %). Its `--selftest` is synthetic and
  is discovered by `tools/selftest.py` (C-7830/C-7837/C-7838).
- Exactly one byte per shard remains unexplained, always at
  `table-terminator+0x0d`, with a value that is a multiple of 6 (EU 14 such
  bytes, US 11); the tool prints its histogram and assigns no meaning
  (C-7836). A 4-byte **mesh id** (`9f be da 1e`, `a0 6f db cf`…) and the
  `u16, u16 0, u8 serial, text\0` tail of a main record are observed but not
  decoded; field semantics stay UNKNOWN (C-7835).

Firmware access path / reader search: see `INTER0nn` above and
`EXP-2026-11-08-M3.16-inter-frway-readers-r2.md` / `EXP-2026-11-20-M3.16-inter-frway.md`
(M3.16, negative for content reader VAs/consumed fields; shared REFER001 access
path and corrected record layout confirmed, C-2210–C-2219). Offline decode:
`EXP-2026-11-22-M4.82-frway-decode.md` (C-7830–C-7839).

**Route-guidance field names vs signpost text (M4.73, EU2011 shard 021).**
The FRWAY021 schema block at `0x1400` carries the names `FREEWAY-NAME`,
`ENTRANCE/EXIT`, `Entrance/Exit name`, `area code`, `route number`,
`attribute code`, `dndc-id`; INTER021 has no such guidance schema names but its
decoded bytes contain 187 `40 00 00 00 XXXX` node refs. The exact signpost
`0=POZNAN:KALISZ:(36):RAWICZ` occurs **0** times in INTER021's 230 and FRWAY021's
3 inner zlib members — its words appear only inside street names (`ULICA
POZNANSKA`, `ULICA RAWICZA`). The signpost is stored verbatim in tile
`B48R058R` section 4 (parcel `a6bed6ee`, name at word 53, country 616), fetched
by the router's kind-`0x40` `RGD_DATA` request (C-5925). `LANE` is absent from
both schemas; scope is two Poland shards, not a claim about other files.
Evidence: `EXP-2026-11-23-M4.73-kiwi-guidance-junction.md` (C-7720–C-7724).

## `ICADM0nn` — administrative country data

- The 4096-byte common CLARION header is followed by an ISO/tier-label table at
  `0x1000`: `u16 size_halfwords, u16 count`, then `count` 462-byte entries.
- Each entry is `u16 stride (0x00e7 = 231 halfwords)`, `u16 ISO-3166-1 numeric`
  (big-endian), 7 × 64-byte tier-label slots (`char`, Latin-1, NUL-padded), and
  10 × `0xff` pad.  EU2011: `count=33`, 15,250 B, `table_end=0x4b92`; US2011:
  `count=2`, 928 B, `table_end=0x13a0`.
- The stride histogram is `{0x00e7: 33}` (EU2011 ICADM001) and `{0x00e7: 2}`
  (US2011 ICADM001); no firmware reader for the 462-byte stride / `0x00e7` tag
  has been located (M3.18 r3, negative), so the value is reported as a
  histogram and **not** attributed to a VA (C-8363).
- All 33 ISO codes match the country whose terminology follows (020 Andorra →
  `2=PARROÒUIA`; 056 Belgium → `2=GEWEST`; 826 UK → `POSTAL COUNTY`).  US uses
  `3=`-prefixed labels (124 → `3=PROVINCE`, 840 → `3=STATE`).
- Open path (EU2011, M3.18 r3): the name is built by `fn 0x003f1640(n)` →
  `ICADM0<n+1>.DAT` (C-4669); the data-block reads complete through the shared
  `REFER001` handler `0x003f72cc` and are loaded by `0x003eff20`, `0x003f17a4`,
  `0x003f2bc4`, `0x003f0c7c` (C-4694). **No field-consuming reader** (462-byte
  stride / `0x00e7` tag) is located; the term blob is a `u16 code, u16 len,
  u32 ffffffff, u8 0, text\0` record run with no discrete indexed reader in
  decodable code (EXP-2026-11-20-M3.18, negative).

### Reproducible field decode (M4.83, C-8360–C-8369)

`tools/icadm_decode.py census ROOT` decodes every shard on both cards and
prints per-shard header, ISO table, record count, field ranges, decoded terms
and bytes explained / total.  Its `--selftest` builds a synthetic shard and a
mutated-byte negative control; `tools/selftest.py` discovers it
(`tool:icadm_decode PASS`).  Full census:

| card | shards | bytes | records | explained |
| --- | --- | --- | --- | --- |
| EU2011 (`m4.8b-eu/REFER001`) | 33 | 113,561,600 | 4,664,115 | 101,042,820 B = 88.98 % (per shard 74.964–99.752 %) |
| US2011 (`m5.12-us/root-factory/REFER001`) | 11 | 6,274,816 | 275,863 | 6,153,178 B = 98.06 % (per shard 84.589–99.933 %) |

The `m5.12c/decoded` tree named in the task input is a generated card whose
ICADM shards are byte-identical to the US factory shards (ICADM001 SHA-256
`91f6b0cc…`); the real EU2011 factory shards are in `m4.8b-eu/REFER001`
(ICADM001 SHA-256 `be791e96…`, 75,776 B).  The census uses the factory roots.

The term blob starts at a fixed offset (`0x4e00` EU2011, `0x1500` US2011).
Its dominant record is `u16 code, u16 len, u32 flags, u32 value` + a
`2*len`-byte Latin-1 text field (NUL-padded to a whole word); a `u16 value`
trailer follows in 174/10,819 US2011 ICADM001 records (10,582 have no trailer,
and `code=0x0006, len=0` is a 14-byte section marker).  On the
`flags=0xffffffff` family `code` is `0x0006..0x8019` and `len` is `1..18`.
Neither the second record family nor the small pre-blob index region is
guessed: their bytes are reported as a per-shard histogram (EU2011 ICADM001:
1,388 B in 84 runs — zero 828, `0xff` 303, `0x10` 50, `0x41` 36).  The
negative control flips one bit of the first stride tag (`0x1005`, `0xe7→0x18`)
and the stride histogram changes `{0xe7:33}→{0x18:1, 0xe7:32}`.  Evidence:
EXP-2026-11-22-M4.83-icadm-decode; matrix row 14 Offline cell is now `tool`,
the reader cell stays `partial`.

## `ZIPFR001` — postal/freeway masks

Global file (not country-sharded), EU2011/2014/2016 only (absent from the
US2011 card, C-7844). A decoded file is a common 512-byte header, the shared
`0x200..0xfff` template, an 8-byte body header at `0x1000`, fixed **14-byte
records** from `0x1008`, then zero padding to EOF. `tools/zipfr_decode.py
census` walks it and reaches every byte (100 % on all three EU cards, C-7841):

```
0x000 512-byte common header (UTF-16BE strings, binary bytes at 0x180)
0x200 0xe00-byte template (the same "mixed" 00/ff pad as the other families)
0x1000 u16 3, u16 projection_end, u16 swap16(projection_end), u16 7   body header
0x1008 14-byte records: u8 flag, u8 0, char key[6], u8 0, u8 0,
       u16 group, u16 mask
```

- **Record:** `flag` is `0x00` for plain records and `0x80` for the "expand
  letter" tail; `key[6]` is zero-padded digits/uppercase/space (C-7841). There
  are 36,881 records on EU2011 (C-137). The last record before the tail is a
  **special marker** (`80 00 00 03 f0 64 …`, a 4-byte counter in the group/mask
  words, C-7845).
- **Fields:** `key[4:6]` (bytes `+0x4..+0x5`) is a **sector** taking **119**
  distinct values on EU2011 — that is the "119 masks" C-137 counts, and it is
  not the trailing `u16` (C-7843). The trailing `u16` at `+0xc` is a per-record
  bit flag (**118** distinct, mostly `0`/`8`/`128`); the `u16` at `+0xa` is a
  small group index (**131** distinct, 0…130) (C-7846).
- **Body header** (C-7842): word 2 = the **projection end**, i.e. the index of
  the special marker = records before it (36,877 on EU2011 = 36,881 − marker −
  3 zero tail records; 44,060 EU2014; 46,267 EU2016); word 1 is its 16-bit
  little-endian swap (`0x900d`); words 0/3 are `3`/`7` on every card.
- **Tail:** 23 records with `flag = 0x80` expand the letters `A`–`Z` for
  prefix-keyed lookups. Three consecutive `A` entries occur (`AB` plain, `AD`
  and `AL` flagged), so the tail is not strictly alphabetical; the census
  reports the inversion list rather than assuming sorted order (C-7845).
- **Bytes:** every byte is reached by the walk (header, template, body header,
  14-byte records, zero tail); the unexplained part is zero on EU2011, EU2014
  and EU2016 (C-7841). The `sector`/`mask`/`key` *semantics* (postal vs freeway
  lookup, C-7848) and the 14-byte consumer in firmware (M3.18 r3) remain
  **HYPOTHESIS/UNKNOWN**.
- Open path (EU2011, M3.18 r3): `ZIPFR001.DAT` (`0x00178e08`) is **row 4** of a
  24-byte descriptor table in sec1 at `0x00564160` (`0x005641c0`, style code
  16, id `0x040c`, sec1 pointer `0x005641c4`). The table is loaded by
  `0x003f7d94`/`0x003f7f40`/`0x003f7b20`; row lookup `0x003f7ae4(16,0)` → 4;
  the issuer `0x003f7b54`/`0x003f7c38` builds a search packet and resolves the
  name through `0x0040b358` (card: `0x000600c2`). The name has **no**
  literal-pool xref in executable sections — it is data-only (C-2382
  retracted). No 14-byte record consumer is located; `0x003f7f94` is the
  generic read-request issuer (EXP-2026-11-20-M3.18, negative for the walker).

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
  body is a long point list. **Framing solved (M3.13, C-5932):** the record
  length is the low **10 bits** of the first big-endian word, `2 * (w & 0x3ff)`
  bytes, so `c1` is a `c0` with `L ≥ 256` (bit 8 of `L` lands in the tag byte).
  This frames all 43,602 record blocks of the 33 EU2011 shards to their exact
  end (59 `c1` records in 10 shards, `L` 261–280;
  `python3 tools/addre_field_reader.py frame REFER001/ADDRE0*.DAT.cmp`).
  `tools/addre.py` still stops at the first `c1`, so its `verify` is claimed
  only for 001/017/003.
- **`c0` always carries a name section, `c8` never does** — 692/692 vs 0/349
  (`ADDRE001`), 249/249 vs 0/360 (`ADDRE017`), 56,988/56,988 vs 0/38,445
  (`ADDRE003`).
- Name section: `TT LL 00 ff`, `LL = ceil(name_len/2)`. The name is
  the **last `2*LL` bytes of the record** (NUL-padded when `name_len` is odd);
  the 4–8 bytes between the marker and the name are a small header whose
  meaning is **UNKNOWN**. *Superseded by the firmware reading (M3.13,
  C-5931):* `TT LL 00 ff` is the **field-length block** of the file's three
  fields (`area code`, `street name`, `dndc-id`, one byte each in words, `ff`
  pad), and the "header" is the `area code` field — see
  [Record fields as the firmware reads them](#record-fields-as-the-firmware-reads-them-m313).
- **Where the name section starts (M4.46, C-5157):** at byte
  `4 + 2*rec[2] + 2*rec[3]` of a `c0` record — byte 2 counts the words of the
  coordinate id + reference block from byte 4, byte 3 the words of the item
  block after it (the same rule as `route_link_join.street_name`, M4.39). The
  position, not `TT`, identifies it: on a `TT = 0x05` shard a reference point
  token `05 40 00 ff` can have the same shape (the `addre.py` self-test plants
  one). EXP-2026-11-20-M4.46-addre-tt05-names. `tools/addre.py parse_record` uses
  this rule (the pre-M4.46 token scan accepted only `TT` `0x03`/`0x04` and
  named 0 of ADDRE002's 198,497 `c0` records).
- **`TT` per shard** (EU2011, all 33 shards, `c0`/`c8` records before the first
  `c1`; `python3 tools/addre.py names REFER001/ADDRE0*.DAT.cmp --parse`):
  4,610,363 `c0` records, 4,610,363 with a section at that position, `TT`
  `0x03` 2,531 / `0x04` 1,332,147 / `0x05` 3,275,685; 0 of 7,424,226 `c8`
  records carry one. `TT` is a per-record byte that is constant in 26 shards and
  mixed in 7 (e.g. ADDRE005 `0x04` 456 / `0x05` 1,420,930). **HYPOTHESIS:**
  `TT` is the area-level count `nl` that `tools/ze0-viewer/tools_ze0/addre_io.py`
  `name_record` writes before the level halfwords (`LL 00` = the first
  little-endian halfword, the name length in words); not tested here.

| Shard | `c0` | `c8` | `TT` histogram (`c0` records) | stops at `c1` |
| --- | --: | --: | --- | --- |
| `ADDRE001` | 692 | 349 | `0x03` 692 | — |
| `ADDRE002` | 198,497 | 359,800 | `0x05` 198,497 | — |
| `ADDRE003` | 56,988 | 38,445 | `0x04` 56,988 | — |
| `ADDRE004` | 45,037 | 108,188 | `0x04` 45,037 | `0xc1@0x6f0aec` |
| `ADDRE005` | 1,421,386 | 2,397,537 | `0x04` 456, `0x05` 1,420,930 | — |
| `ADDRE006` | 15,347 | 31,955 | `0x04` 15,347 | — |
| `ADDRE007` | 277,985 | 915,140 | `0x05` 277,985 | — |
| `ADDRE008` | 127,839 | 186,717 | `0x05` 127,839 | `0xc1@0xf8d7a8` |
| `ADDRE009` | 12,371 | 24,546 | `0x04` 6, `0x05` 12,365 | `0xc1@0x1b2ddc` |
| `ADDRE010` | 90,512 | 47,017 | `0x04` 90,512 | — |
| `ADDRE011` | 414 | 352 | `0x05` 414 | `0xc1@0x8d32` |
| `ADDRE012` | 42,331 | 67,883 | `0x04` 42,331 | — |
| `ADDRE013` | 14,414 | 24,762 | `0x03` 241, `0x04` 14,173 | `0xc1@0x1ba1ec` |
| `ADDRE014` | 1,271 | 2,083 | `0x04` 1,271 | — |
| `ADDRE015` | 13,046 | 35,768 | `0x05` 13,046 | — |
| `ADDRE016` | 8,682 | 12,242 | `0x05` 8,682 | — |
| `ADDRE017` | 249 | 360 | `0x03` 249 | — |
| `ADDRE018` | 103,156 | 206,843 | `0x04` 103,156 | `0xc1@0xdac356` |
| `ADDRE019` | 147,628 | 226,305 | `0x04` 147,628 | — |
| `ADDRE020` | 200,388 | 256,812 | `0x04` 32, `0x05` 200,356 | — |
| `ADDRE021` | 11,894 | 16,292 | `0x05` 11,894 | `0xc1@0x123392` |
| `ADDRE022` | 261,580 | 238,124 | `0x04` 261,580 | — |
| `ADDRE023` | 37,037 | 13,092 | `0x03` 339, `0x04` 36,698 | — |
| `ADDRE024` | 969 | 1,217 | `0x03` 969 | — |
| `ADDRE025` | 357,478 | 515,423 | `0x04` 357,478 | `0xc1@0x272629c` |
| `ADDRE026` | 217,045 | 252,205 | `0x05` 217,045 | — |
| `ADDRE027` | 30,055 | 68,860 | `0x04` 3, `0x05` 30,052 | — |
| `ADDRE028` | 33,151 | 139,297 | `0x04` 33,151 | — |
| `ADDRE029` | 651,783 | 916,999 | `0x04` 14, `0x05` 651,769 | `0xc1@0x4b60c9e` |
| `ADDRE030` | 104,811 | 86,829 | `0x05` 104,811 | — |
| `ADDRE031` | 123,812 | 229,864 | `0x04` 123,812 | — |
| `ADDRE032` | 41 | 0 | `0x03` 41 | — |
| `ADDRE033` | 2,474 | 2,920 | `0x04` 2,474 | `0xc1@0x401b6` |
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

### Record fields as the firmware reads them (M3.13)

Source: `EXP-2026-11-20-M3.13-addre-reader-l3`, C-5930–C-5939 (EU2011 and
US2011, PySh4 with the slots the firmware's own writer stores).

```
word 0      class/length   w >> 13 == 6 (0xc000 class); (w & 0x1800) >> 11 = 0 (c0/c1) or 1 (c8);
                           record = 2 * (w & 0x3ff) bytes  (c1 = c0 with L >= 256)
byte 2      n1             words of block 1 (from byte 4): coordinate id + point tokens
byte 3      n2             words of the item block after it (house ranges)
4           block 1        2*n1 bytes
4 + 2*n1    items          length-prefixed: item[0] = item length in words (06/07/08 ...)
4+2*(n1+n2) length block   one byte per field, in words: area code, street name, dndc-id, pad 0xff
            fields         area code, street name, dndc-id, each 2*len bytes (NUL-padded)
```

- The 0x100-byte **schema block is the field dictionary** the `REFER001`
  accessor reads (`ff ff`, `D = C + 2*u16[C+2]`, `u16[D+26]` = 3 fields,
  entries chained from `D + 2*u16[D+24]` with the id at `+12`, a length byte at
  `+14` and the name at `+16`). Entry word `+4` is the largest length of that
  field in the shard, in words (33/33 EU2011 shards and US `ADDRE010`); entry
  word `+6` is `0x8000`/`0x6000`/`0x2000`.
- `c8` records have the same layout with an all-zero length block
  (`00 00 00 ff`): three empty fields.
- `TT` = the `area code` length (3–5 words); the `area code` bytes are the
  former "4–8-byte header". `dndc-id` is empty in every record run.
- The range-token "prefix" `06/07/08` (C-975) is the item length in words.
- What the reader needs (read map): the dictionary's `C+2`, `D+24`, `D+26`,
  entry chain and ids, and the per-record length block; the firmware finds the
  street by these, not by position from the end. Entry `+4` = max length is
  **OBSERVED** in the factory files only (33/33 shards); no instruction in the
  read map reads it, so it is not a known firmware requirement.

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

### Which files use the `11xx` nibble (M4.61)

> **Status:** `OBSERVED` on EU 2011 (33 `ADDRE` shards, 132 `COORD001` words)
> and US 2011 (11 shards, 44 `COORD001` words) (C-6560–C-6563). This is a
> measurement, not a new model: the ids are **plain 1-unit coordinates** in
> `COORD001` and `ADDRE`, decoded with `(x−32768)/192`, `(y−52742)/128`.

`tools/point_census.py` found that a **POINT** copy-A word is `11xx`-marked and
needs the marker stripped (M4.27, C-2679). `COORD001` and `ADDRE` ids often
carry the same `11xx` low nibble, but there it is **position, not a marker**:

- `COORD001` has **no fine field** — each of the 33 (EU) / 11 (US) entries is
  14 bytes `x0, y0, x1, y1, level_u32, pad_u16` (`coord_zcode_icode.py`), and
  only the four coordinate words are ids. All 132/132 (EU) and 44/44 (US)
  words have low nibble `11xx` (`c`/`d`/`e`/`f`), but the box is read as plain
  coordinates: with the marker stripped, a stripped box moves every MONACO
  ADDRE id out (0/609) while the plain box keeps them (57/609).
- `ADDRE` ids split **per shard and per card**, and the split is a first-class
  result, not noise: EU `ADDRE001` 2,082/2,082 words `11xx`, `ADDRE017`
  only 114/1,218 (`ADDRE017`'s 57 `11xx` ids are exactly the addresses inside
  Monaco's box; its 552 low-nibble ids land ~0.06° south of it, C-6561).
  Totals: EU 16,539,516/17,409,252 words `11xx`; US 32,719,161/32,981,740
  (10 EU and 4 US shards with `0xc1` framing are unreadable by
  `split_records`, M4.9, and are named in the census, not counted).
- In every discriminating shard the **plain** decode is the in-box one:
  `ADDRE017` 57/57 plain vs 0/57 stripped; `ADDRE032` 9/9 vs 0/9;
  EU `ADDRE001` 1,041/1,041 plain vs 845 stripped; `ADDRE014` 3,354/3,354 vs
  2,951. So `11xx` on a `COORD001`/`ADDRE` id is four position bits, and only
  a POINT copy-A word (read by the firmware with the marker stripped, M3.34)
  uses the fine form.

**The `ADDRE` fine position is absent.** Every even offset of every readable
`ADDRE` record was tested for the POINT record pair (`0x800|flon`, then a raw
`flat` 0..0x7ff). No such pair sits at **`id+6`**, the byte position the POINT
name record uses (0 in every shard tested). A pair-shaped pair at `id+8`/`id+12`
does occur (5.8 % EU `ADDRE001`, 4.5 % `ADDRE003`, 0.4 % US `ADDRE001`), but
decoded as `(flon, flat)` of the same coord it lands 2–6 km from the plain
position (EU `ADDRE001`), so it is not a sub-cell refinement — it is point- and
range-token payload bytes. The only structured field adjacent to the id is the
**`TT 40 XX YY` point token** at `id+6` (2 or 4, 1/256 scale), which M4.19
could not give a 2D frame (C-1964); it is not a POINT-style fine pair.

Tool: `python3 tools/refer_id_census.py ids --eu DIR --us DIR --control` and
`... fine --dir DIR --shards ADDRE001 ADDRE017` (`--selftest`).

Still open: the 6-byte cell payload (`value`/`count`), the `prefix`
`0x06/0x07/0x08` axis of the range tokens, the `(XX, YY)` 2D frame / axis
assignment and the meaning of `XX` (2D geographic not derivable from
`coord,XX,YY,tag` alone; M4.19/C-1960–C-1969), the cell base for directory
`block > 0`, why `count` under-covers large shards, the 6 trailing bytes of
each `COORD001` entry, and the 22-byte index record fields.

Tool: `tools/addre.py` (`layout`, `table`, `cells`, `records`, `stats`,
`trailer`, `verify`, `--selftest`).

### Firmware reader (M3.13, located and run in L3)

> **Status (2026-11-20, C-5930–C-5939):** the record reader is located and
> runs in PySh4 on factory blocks of both builds (EU2011 3,650 records,
> US2011 57,180, all correct) with the slot binding the firmware's own
> `0x14e4` writer makes, and on edited blocks. Reader chain (EU2011; US2011 in
> brackets): writer `fn 0x003fd390` [`0x00425564`] stores page → slots `+0x14`
> and `+0x2c`, dictionary → `+0x18` (search type 2); field accessor
> `fn 0x003f61bc(db, rec, f)` / length `fn 0x003f5d98` [`0x0041eb1c` /
> `0x0041e6f8`] → resolver `fn 0x003f51e0` → locator `fn 0x003f56bc` →
> `fn 0x003f5e10`; record `n` through the dispatcher `fn 0x003f5cdc` → walker
> `0x003f5b88`; record leaves `0x003f5468`, `0x003f54f4`, `0x003f5550`,
> `0x003f559c` and the item accessor `fn 0x003f5624` [`0x0041dfd4`]. Field →
> instruction table below; `EXP-2026-11-20-M3.13-addre-reader-l3`. The text
> from here to that table is the pass-1–3 history (C-2180–C-2187); where it
> says "not mapped" or "HYPOTHESIS", the 2026-11-20 table wins.

ADDRE is resolved through the same `REFER001` family mechanism as POINT
(M3.11, C-880/C-881/C-2122): descriptor type `0x14e8` in `fn 0x004125a8` (Navi.exe
sec0) maps to `REFER001` (`0x00178c68`) + `INDEX003.DAT` (`0x0017a118`) via
volume lookup `jsr 0x0040b358` (`fn 0x0040b358`, 28-byte table, count `+24`,
list `+32`). The volume-id table `0x00179338` contains `ADDRE0` (`0x0017935c`)
selected by name builder `fn 0x003fbed8` (dispatch on `*(r10+124)`, pool
`0x003fc0d8`→id table, `jsr 0x0040b358` at `0x003fc084`); `fn 0x0040114e`
additionally resolves `ADDRE0` (`r5` loaded at `0x00401216` from pool
`0x00401254`, name/digit build + COREDLL string ops, `jsr 0x0040b358` at
`0x0040123c`). `ADDRE001.DAT` (`0x00179f30`) has no executable-section literal
ref.

**Reader VAs (Navi.exe sec0, uncompressed):** `fn 0x003f56bc` — 0xc000-class
header consumer/entry locator: resolves buffer via `fn 0x003f51e0` (`0x003f56ca`,
`0x00d53500` REFER table, same family as POINT walker `0x003f5194`); reads
header `w=*r5` (`0x003f56e0`), masks `0xe000` (`0x003f56e4-0x003f56ea`), loads
literal `0xc000` (`0x003f56ec`, pool `0x003f57a4`), accepts `(w & 0xe000) >=
0xc000` (`0x003f56ee cmp/hs`, `0x003f56f0 bf reject`) — covering ADDRE
`c0`/`c8`/`c1` in native swapped `u16` form; walks a sub-table (`u16@(r2+24/26)`,
2-byte stride, entry compare `u16@(entry+12)`) and dispatches on header/type
bits to return a pointer. Sole `0xe000`-mask+`cmp/hs>=0xc000` gate among 82
`0xc000` literal loads in sec0. Called by `fn 0x003f5d98` (pool `0x003f5e08`,
`jsr 0x003f5dbc`; extracts a byte by index via `0x003f57a8`) and
`fn 0x003f61bc` (pool `0x003f6214`). `fn 0x003f5cdc` dispatcher routes POINT
buffer slots to `0x003f5b88`/`0x003f5194`/`0x003f39c0`, not directly to
`0x003f56bc`. Buffer-slot→ADDRE binding is `HYPOTHESIS` pending `0x00d53500`/L3
trace.

Pass-1 byte-grammar signature (`cmp/eq #0xc0/#0xc8`, `mov.b @(1)+shll` 2*L)
found no record-stream walker (282 sections / 23.6 MB) — that negative stands
for those signatures. Navi.exe sec1/sec2 are compressed *data* (C-2128), so
"not found in executable code" is not a compression blocker.

**Grammar field → consuming instruction (M3.13 L3 run, 2026-11-20, EU2011;
US2011 offsets per function: `+0x289b0` for `fn 0x003f51e0`, `fn 0x003f56bc`, `fn 0x003f57a8`, the leaves `0x003f5468`/`0x003f54f4`/`0x003f5550`/`0x003f559c` and `fn 0x003f5624`; `+0x28960` for `fn 0x003f5cdc`, `fn 0x003f5d98`, `fn 0x003f5e10`, `fn 0x003f61bc`; `+0x289b8` for the walker `0x003f5b88`; memory offsets are in the
byte-swapped buffer, so a byte read at memory `+k` is file byte `k^1`):**

| Field (claim) | Consumed by | Status |
| --- | --- | --- |
| Schema block = field dictionary (C-970, C-5931) | `fn 0x003f56bc` `0x003f56d2` (`C+2`), `0x003f570c` (`D+26`), `0x003f5716` (`D+24`), `0x003f5726` (chain), `0x003f5736` (id `+12`); `fn 0x003f57a8` `0x003f57b4`/`0x003f57c6` | read |
| Index chain, directory `0x1108`, cells `0x2000` (C-970–C-972) | — | not inputs of the record reader; reader not located (search path, M3.30) |
| Header class `c0/c8/c1` (C-973) | `0x003f56e0`–`0x003f570a`; leaf `0x003f5468` (`c8` bit, `0x003f547e`) | read |
| Record length `2*(w & 0x3ff)`, incl. `c1` (C-973, C-5932) | walker `0x003f5b88` at `0x003f5bb8` | read |
| `rec[2]` / `rec[3]` word counts (C-5933) | `0x003f5774`; `0x003f5536`, `0x003f5594`, `0x003f55e4`, `0x003f567e` | read |
| `TT LL 00 ff` = field-length block (C-974, C-5931) | `fn 0x003f5d98` `0x003f5dd2`; `fn 0x003f5e10` `0x003f5e36` | read |
| `area code` / `street name` / `dndc-id` | pointer + length from `fn 0x003f61bc` / `fn 0x003f5d98` | located; bytes read by callers (UNKNOWN) |
| Range item length byte (C-975 "prefix", C-5934) | `0x003f5604`, `0x003f5692` | read |
| Range item body `subtype 00 00 :N:;:M:` (C-975) | item pointer from `fn 0x003f5624` | located; bytes read by callers `fn 0x003ad680`/`fn 0x003ad9a4`/`fn 0x003b9d38`/`fn 0x003bacc4` (UNKNOWN, M3.32) |
| Block 1: coordinate id + point tokens (C-976) | pointer `0x003f54f4`, words `0x003f5550` | located; bytes read by the same callers (UNKNOWN, M3.32) |
| Trailer TOC (C-977) | — | not an input of the record reader |
| `fn 0x0040b358` (pre-M3.13 candidate) | — | a path-name lookup (`0x00409cc8` tests `/` and `\`); reads no record byte |

**Pass-3 table (2026-11-12, history; superseded by the table above):**

| Field (claim) | Consuming instruction VA | Status |
| --- | --- | --- |
| Container/layout: dir `0x1108`, cells `0x2000`, index `4e 20 00 00`+`u32` offsets, schema `+0x100`, record chain, trailer (C-970) | — | **never read in sec0 literal pools** (no sec0 pool holds `0x0000204e`/`0x4e200000`/`0x0000f401`/`0x01f40000`; EXP-2026-11-12-M3.13-addre-reader-3; decoded sec1/sec2 not searched — M1.24) |
| 12-byte directory `(initial,0,count,block,offset,length,tail)` (C-971) | — | not mapped; not proven absent (family `@(12,entry)` is a 2-byte-stride field compare, not a 12-byte row) |
| 6-byte cells `(0..3,value,count)` / `(pointer,0xff00,0)` (C-972) | — | not mapped (`fn 0x003f56bc` sub-table stride is 2 bytes, not 6) |
| `c0`/`c8`/`c1` records, `2*L` framing (C-973) | `0x003f56e0` `mov.w @r9,r3`; `0x003f56e4-0x003f56ea` `e1e0/4118/2319` mask `0xe000`; `0x003f56ec` `d12d` literal `0xc000`; `0x003f56f0` `bf reject` (`fn 0x003f56bc`) | **tag-class consumed** (accepts `c0/c8/c1` native swapped `u16`); sequential `2*L` record-stream cursor walk **not mapped** |
| name `TT LL 00 ff`, `LL=ceil(name_len/2)`, last `2*LL` bytes (C-974) | — | not mapped (no `0x0000ff00` literal in `0x003f5000–0x003f7000`; `cmp/eq #0x40` ×88 global, 0 in family after a byte load; EXP-3) |
| range `prefix subtype 00 00 :N:;:M:` (low-nibble slot; prefix/slot meaning UNKNOWN) (C-975) | — | **never read in sec0 literal pools** (`:;:` literals at `0x002674bb/fb`,`0x002684bb/fb` unreferenced by any sec0 pool; EXP-3; sec1/sec2 not searched — M1.24) |
| point `TT 40 XX YY` (`0x40` constant, role `TT`; 2D arithmetic UNKNOWN) (C-976, C-1964) | — | not mapped (`cmp/eq #0x40` ×88 global, 0 in family window after a byte load; name-TT compares unsearchable by immediate; EXP-3) |
| trailer TOC `(start,length,value)` per block (C-977) | — | **never read in sec0 literal pools** (no sec0 pool holds `0x0000f401`/`0x01f40000`; EXP-3; sec1/sec2 not searched — M1.24) |
| `tools/addre.py` (offline, C-978) | n/a | repo tool, not firmware |
| negative scope (cell payload / `XX,YY` arithmetic, C-979) | — | unchanged |

## `INDEX001` / `INDEX003` — POI/name search index files

> **Evidence status:** `OBSERVED` (on-disk absence on EU/US 2011 stock) +
> `UNKNOWN` (record layout). Firmware mapping `0x14e8` → `REFER001` +
> `INDEX003.DAT` is `VERIFIED` in code refs (C-880/C-2122).

`REFER001/INDEX003.DAT` (the `0x14e8` descriptor target, C-880) is **absent as
an on-disk file** from the EU 2011 (`leaf2011.img`) and US 2011
(`53342430…`, 8,057,257,984 B) stock card images examined:

| Check | EU 2011 (`REFER001` 388 files) | US 2011 (`REFER001` 116 files) |
| --- | --- | --- |
| `INDEX003.DAT` / `.cmp` / `.ind` in FAT | absent (0 `INDEX*` hits in `REFER001`, none in FAT) | absent (0 `INDEX003` hits; only `INDEX001` pair present) |
| `INDEX003` in `DRSTR001.DAT` | absent | absent (`INDEX001` named at DRSTR offset `0x1780`) |
| `INDEX003` bytes in raw image | offsets `14648088`, `46105368` (firmware/string area, not a FAT file) | offsets `14679280`, `46136560` (firmware/string area, not a FAT file) |

The only INDEX-family file present is US `REFER001/INDEX001.DAT.cmp`/`.ind`
(logical 552448 B, 9 × 65536-byte chunks, compressed 142292 B); decoded
content is binary with no long ASCII name runs observed. `INDEX001` is not the
`0x14e8` target and its record layout/role remain **UNKNOWN**.

**Implication for POI name search / S2 rename (scoped to these images):**
because `INDEX003` is absent on these stock images, POI lookup cannot go
through a second copy of the POI name stored in an on-disk `INDEX003` file on
these images. No `INDEX003` entry refers to the US POI `HANA HEALTH CENTER`
(`POINT010`, page `0x840ba0`, record 0, M5.12/C-1980) on these images, so an
S2-style POI rename on these images does **not** need to update an `INDEX003`
file.

**Record layout:** **UNKNOWN.** Cannot be determined from the EU/US 2011 stock
images (file absent). The open question — whether an `INDEX003` entry holds
name bytes or pointers into `POINT` pages — requires an image version that
ships the file. Factory vs mutated comparison (M5.12 mutated only `POINT010`)
is N/A on these images.

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
- `INDEX003.DAT` (firmware `0x14e8` target, C-880) is absent on EU/US 2011
  stock images; treat its record layout as **UNKNOWN** and do not assume an
  on-disk `INDEX003` name copy must be updated for an S2 POI rename on these
  images. Re-check on any image version that ships the file.
