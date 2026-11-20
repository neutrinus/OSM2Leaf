# `RDSTM001.DAT` and `LCTBL001.DAT` (road data)

Sample: EU 2011 image
(SHA-256 `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`).

- `RDSTM001.DAT`: 23,335,680 bytes,
  SHA-256 `f822044c0aab75327b9fb484e9a4c7c8dd5938b21efaacec0e5b2d8b23ab3e49`
- `LCTBL001.DAT`: 7,489,024 bytes,
  SHA-256 `8cab17754114b5f7ca47d4f46d55c95c6acf841629e1fcc42e6da45063353e9d`

> **Evidence status:** block layouts and stream counts are `VERIFIED`;
> field semantics are `OBSERVED`/`HYPOTHESIS`; the firmware-side record field
> set and order are `VERIFIED` (EXP-2026-11-06-M3.7-router-rdstm);
> speed/direction/turn restrictions are **not** in this file (verified
> negative within the firmware accessor set).

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
| records below `0x1a700` are graph tuples | HYPOTHESIS | node/link shape, roles unchecked; the firmware record set at `0x1000` is the twelve TMC fields (C-882), so any graph tuples must be elsewhere | `tools/rdstm_schema.py layout` |
| framing drift at `0x10a0` (`+14` → `+4`) | OBSERVED | records are variable length: the firmware walks a per-record field directory | C-106, C-884 |
| name-index mapping (code → LCTBL name) | UNKNOWN | the join rate is a bound, not a decode | `tools/rdstm_schema.py join` |
| speed / one-way / turn restrictions | UNKNOWN (not in `RDSTM`) | routing speed comes from elsewhere | C-885; M3.7 field set |
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

1. **speed / one-way / turn restrictions.** Not present in the record field set
   the firmware reads (C-885, EXP-2026-11-06-M3.7-router-rdstm), so they must
   come from elsewhere (`MAPAL001` tiles, `INTER001`/`FRWAY001`) — not from
   this file.
2. **record size and framing.** The `0x1000` table drifts at `0x10a0`, so
   either the rows are variable length or the table ends there. A grid score
   cannot settle it; it can only show where a constant size stops fitting.
   The firmware decodes records through a per-record length/offset directory
   (C-884). **Resolved (M4.16b):** that directory frames the `LCTBL001.DAT`
   page records, not this table; the `0x1000` block here is a `0x180`-word
   header followed at `0x1300` by variable-length location → link records
   (see "`RDSTM001.DAT` location → link records" below).
3. **graph tuple roles.** A `(src, dst)` reading of the `0x1a700` arrays is a
   hypothesis. `--layout` reports reciprocity and back references as
   diagnostics: high reciprocity is what a road graph should show, but other
   structures (index pairs, shared references) would score the same.
4. **name index.** Whether the 2-byte code indexes the LCTBL catalog, the
   name records or a class code is unknown; `join` only reports how often a
   code is a known LCTBL code, which is necessary but not sufficient.
5. **code position drift.** Why the code moves from `+14` to `+4` at `0x10a0`
   is unexplained by a fixed layout. The `0x1000..0x1224` bytes are the
   file's table header (per-table rows ending in the catalog code, e.g.
   `3219`), not records; its row layout is not decoded (M4.16e).

## What the firmware reads (field list with VAs)

Source: EXP-2026-11-06-M3.7-router-rdstm (build A, `Navi.exe`). The record is
the **TMC location record** of the `RDSTM001` volume; it is not a graph edge.

### Volume resolution

| Item | VA | Meaning |
| --- | --- | --- |
| `RDSTM001` (volume id) | `0x00179398` | 8-char id in the volume table at `0x00179338` |
| `LCTBL001.DAT` (file) | `0x0017a1f8` | name table opened together with the volume |
| data type `0x14e4` | code `0x004125a8`, compare at `0x004125fa` | selects `RDSTM001` + `LCTBL001.DAT` (kind 1) |
| volume lookup | `0x0040b358` | `(volume, name)` → entry index, 28-byte entries (`count` at `+24`, list at `+32`) |
| literal `RDSTM001.DAT` | `0x00179f7c` | **no code reference**; the file name is built from the id (`0x003fbed8`) |

### Record fields

`0x003bc960` decodes one raw record into a 496-byte (`0x1f0`) struct at
`0x006f3918`; `0x003bbf6c` (`sdl_TMC_InitDataRecode`) clears it and sets the
ordered codes to `0xffff`. The twelve fields and their accessors:

| # | Field | decoded offset | raw field index | extractor | getter (name string VA) |
| --- | --- | --- | --- | --- | --- |
| 1 | location code | `+0x04` u16 | 0 | `0x003f66b8` | `0x003bbfe0` (`0x00045020`) |
| 2 | road number (string) | `+0x12` count, `+0x1c` block | 1 | `0x003bc028` | `0x003bc100` (`0x00045038`) |
| 3 | road name (string) | `+0x14` count, `+0x40` block | 2 | `0x003bc194` | `0x003bc26c` (`0x00045070`) |
| 4 | primary location (string) | `+0x16` count, `+0xc4` block | 3 | `0x003bc300` | `0x003bc3d8` (`0x000450a0`) |
| 5 | secondary location (string) | `+0x18` count, `+0x148` block | 4 | `0x003bc470` | `0x003bc548` (`0x000450e0`) |
| 6 | area code | `+0x06` u16 | 5 | `0x003f6734` | `0x003bc5e0` (`0x00045120`) |
| 7 | liner code | `+0x08` u16 | 6 | `0x003f6780` | `0x003bc628` (`0x0004513c`) |
| 8 | front code | `+0x0a` u16 | 7 | `0x003f67cc` | `0x003bc670` (`0x0004515c`) |
| 9 | rear code | `+0x0c` u16 | 8 | `0x003f6818` | `0x003bc6b8` (`0x0004517c`) |
| 10 | urban attribute | `+0x0e` u16 | 9 | `0x003f6864` | `0x003bc700` (`0x00045198`) |
| 11 | exit/junction (string) | `+0x1a` count, `+0x1cc` block | 10 | `0x003bc748` | `0x003bc820` (`0x000451b4`) |
| 12 | inter-section code | `+0x10` u16 | 11 | `0x003f68bc` | `0x003bc8b8` (`0x000451fc`) |

The field order is the `LCTBL001` catalog column order (see the schema table
below), so the catalog's column offsets are the record's field order — the
byte offsets themselves are looked up per record, not fixed.

### Per-record field directory (decoded, M4.16b)

The record does not have a constant stride. `0x003f61bc(handle, record,
index)` (EU2011 build A) returns a pointer to field `index`; the rule is read
from the code and verified on the card (EXP-2026-11-19-M4.16b-tmc-field-directory,
C-5130–C-5133):

| Step | VA (EU2011) | Rule |
| --- | --- | --- |
| handle → block | `0x003f51e0` | key/value word pairs at `0x00d53500` (fallback `0x003f3a10`); a handle cache, **not** a field schema |
| data start | `0x003f56bc` | `w = u16 rec[0]`; reject `(w & 0xe000) > 0xc000` or bits 11–12 ∉ {0,1}; `w>>13`: 0 → `rec+2`, 5 → `rec+8`, 2/3 → `rec+2*(hi+lo+8)` of `u16 rec[10]`, 6 → `rec+2*(hi+lo+2)` of `u16 rec[2]`, else invalid |
| field count | `0x003f57a8` | `u16 [hdr+26]` of the handle's block (`hdr = base + 2*u16[base+2]`); 12 for TMC records |
| field length | `0x003f5d98` | byte `i` of the length table at the data start (even `i` = high byte of the halfword), in 16-bit words |
| field offset | `0x003f5e10` | `data + 2*((n+1)/2 + Σ len[0:i])` (length table padded to whole halfwords) |

The records this walk reads are the `LCTBL001.DAT` page records (all of type
0, so data starts at `+2`). With 12 fields the rule frames **247,089/247,089**
EU and **303,023/303,023** US records exactly; 11 or 13 fields do not
(`python3 tools/tmc_fielddir.py walk LCTBL001.DAT`). The "16-byte header + 4
name slots + footer" layout under [Record layout](#record-layout-verified) is
the same thing seen from outside: `marker 0x01` = length of field 0, `len1..4`
= fields 1–4, the 7 "attribute" bytes = lengths of fields 5–11, and the
"footer" = fields 5–11 (u16 codes and the exit-number string).

Two corrections to the field table above:

- raw field 0 is the TMC **location type** (120 values: 100 continent,
  300 country, 20111 …), not the location code;
- the **location code** is not stored in the record. It is the BCD value of
  the record's ordinal in the index at `0x4600..0x316600` (0x1000-byte pages;
  leaf pages start `ffffffff` and hold up to 340 entries `u32 ordinal` + 8
  bytes BCD padded with `0xf`; one run per location table, 30 runs on EU 2011,
  `python3 tools/tmc_fielddir.py index LCTBL001.DAT`).

### `RDSTM001.DAT` location → link records (EU 2011, M4.16b)

From `0x1300` to `0xccce00` the file holds 28 pairs of 0x100-aligned blocks,
two per location table (C-5134):

```
link record   u16 size_words (0xffff on the last record of a block)
              u16 location code
              u16 n
              n x ( u16 k ; (k >> 2) x u32 ref )      k & 3: role (UNKNOWN)
triple block  u16 count ; count x ( u16 code, u16 negative, u16 positive )
```

The TMC location code joins the decoded records to these blocks: 167,204 of
172,752 records carry the same (negative, positive) pair as the triple of
their code, and 0 at ordinal shifts ±1/+2 (C-5135,
`python3 tools/tmc_fielddir.py join LCTBL001.DAT RDSTM001.DAT`). A `ref` is
`group (>>16)` + `entry (&0xffff)`, decoded to MAPAL parcel/node/link below
(M4.16e). The US 2011 card's index and `RDSTM001.DAT` use other offsets (not
parsed yet).

### Link groups: ref → MAPAL section-2 link (EU 2011, M4.16e)

Source: EXP-2026-11-20-M4.16e-rdstm-link-groups (C-5137–C-5139, C-5370);
tool `tools/rdstm_links.py`. All words big-endian; an *addr* is the MAPAL
container address `(v >> 8) * 0x800 + (v & 0xff) * 0x100`, *blocks* are 0x100
bytes.

```
0x1000 header  u16 0x180 (words), u16 3, u16 122          (last two UNKNOWN)
               2 x set: u32 group_index_addr, u16 blocks, u16 ntables (14)
                        ntables x ( u16 table_code, u16 nlink,
                                    nlink x (u32 addr, u16 blocks),   link blocks
                                    u32 triple_addr, u16 blocks )     triple block
group index    u16 ngroups
               ngroups x (4-byte aligned):
                 u16 size_dwords, u32 data_addr, u16 data_blocks,
                 u32 key_min, u32 key_max,                  box of parcel codes
                 u16 n, n x ( u32 parcel_key, u16 count )
group data     sum(count) x ( u16 a, u16 b ), parcel by parcel in key order
```

| Set | Pairs (tables) | Group index | Groups | Parcel level | Entries |
| --- | --- | --- | --- | --- | --- |
| 0 | 0–13 | `0xcda000` | 33 (≈ one grid tile each) | 4 (`LEV3456R.DAT`) | 422,683 |
| 1 | 14–27 | `0xe78500` | 3,132 (4 × 4 level-2 parcels each) | 2 (grid tiles) | 1,877,891 |

Resolving a ref of a location record in pair `p`: take the set of `p`, group
`ref >> 16`, entry `ref & 0xffff`; the entry belongs to the parcel whose
cumulative count range holds it. `parcel_key = (w0 << 16) | w1` is the MAPAL
parcel code (`w1 & 0xf` = level). In that parcel's section-2 record (graph
part a):

- `a & 0x1fff` = **node index**, `b & 0x1fff` = **link id**; the node is an
  end of the link (99.96 % level 2, 98.8 % level 4; random node 5.7 % / 0.4 %);
- `b & 0x2000` = the end flag of that link end (as in the node's id word);
- `a` 0x4000/0x8000, `b` 0x4000/0x8000 and the link-record role `k & 3` are
  UNKNOWN (C-5371).

Node `(x, y)` (0..2047) gives coordinates: level 2 parcel origin
`lat = row/12`, `lon = col/8 − 924` with `row = (w0>>8 & 0x7f)<<4 | (w0>>4 & 0xf)`,
`col = ((w0>>15)<<8 | w1>>8)<<4 | (w1>>4 & 0xf)`, size 1/12° × 1/8°. With this,
every joined record of the CZ (8,532) and DE (22,884) tables lands in its own
country and next to its TMC positive neighbour (C-5370). The firmware reader of
these blocks is not located yet (M4.49).

**All 14 tables, both levels (M4.16b, C-5400–C-5403).** `python3
tools/rdstm_place.py place-all LCTBL001.DAT RDSTM001.DAT MAPAL001` places
110,788 of the 110,795 location-code-joined records of all 14 RDSTM tables
(CZ, CH, IT, BE, FI, NL, DK, AT, GB, DE, ES, SE, FR, NO) on level-2 nodes, each
in its table's country; set 0 (pair `t`, level 4) places 60,321 of the same
records within 5 km of their level-2 nodes (median 0.02–0.03 km). The join key
is the location code alone; the (negative, positive) agreement of C-5135 is a
confirmation. Link-record roles: role 1 is the role-0 link list reversed in
24,948 of 66,443 records carrying both (HYPOTHESIS: the two travel
directions); roles 2/3 are UNKNOWN.

**Firmware reader: not located (M4.49, C-5375–C-5379).** The TMC data-layer
subtree of `Navi.exe` (EU2011, 230 functions below the `0x14e4`/`0x14f4`
message handlers) has no `0x1fff` mask and no function with the group-index
shape; message `0x14f4` shares the TMC handler `0x004003f4` and has its own
buffer in the generic sector reader `0x00417618` — the lead for M4.51. The
link-group layout above is therefore a data-side decode, not *confirmed*
(rule 13).

### Writer (M5.19)

Source: EXP-2026-11-20-M5.19-rdstm-writer (C-2430–C-2436); tool
`tools/rdstm_write.py`. Copying the factory file is correct only while
section 2 is the factory one. Against a renumbered section 2 the copied refs
resolve at random (6,910/200,987 on `B48R058R`), so a generated map needs
re-pointed refs (C-2430).

The writer rebuilds the EU 2011 file **byte for byte** from records,
`{code: (negative, positive)}` triples and ref targets `(parcel_key, a, b)`
(C-2431). These layout rules are pinned by that identity:

- **Layout.**
  - Blocks are contiguous and zero-padded to `0x100`.
  - The order is: header `0x1000` (`0x180` words), set 0 tables, set 1
    tables, set 0 group index + data, set 1 group index + data, EOF.
  - Group heads are padded to whole dwords (`size_dwords`).
  - A link record's size word is `size_words`; the last record of a chunk
    has `0xffff`.
- **Tables.**
  - Records are sorted by location code.
  - A table is split into 1, 2 or 4 equal-count chunks (remainder to the
    last chunks), stored in the order 0, 2, 1, 3.
  - Triples are in stored order.
  - Chunk count: 1 up to 506,394 B, 2 from 575,240 B, 4 from 1,340,644 B.
    The limit `0x80000` is a HYPOTHESIS.
- **Groups.**
  - Set 1: aligned 4 × 4 level-2 parcel boxes in ascending key.
  - Set 0: a supplied parcel → group table (3 of 33 factory groups hold
    parcels outside their box).
  - One entry per ref. Per group, parcels are in key order; per parcel,
    entries are in the location-code order of the records (C-2432).

`rdstm_write.py repoint` renumbers nodes and links and re-points the targets.
The written file then resolves exactly as the factory pair does
(200,190/200,987) (C-2433).

**Firmware walk (L3, EU2011 build A).** `fn 0x003f61bc` and `fn 0x003f5d98`
walk writer-encoded TMC rows (`encode_tmc`) exactly by the field-directory
rule above:

- 24 + 500 factory rows and 24 synthetic Polish rows match;
- controls are at 0: type 7, a 13-field block, unswapped bytes (C-2434).

The handle block carries a descriptor chain: `u16[hdr+24]` = first
descriptor, `+0` = next, `+12` = field index, which must equal the requested
index (C-2435). The walk reads little-endian halfwords and takes field `2k`
from the high byte, so card records are walked after a 16-bit swap. The
loader that swaps is not located (C-2436). The link groups have no firmware
reader VA yet (M4.49 blocked; M4.51).

### Table codes and `TMC/reception.dat` (EU 2011, M4.16d)

A header `table_code` is `ord(CC hex digit) << 8 | LTN`: high byte the ASCII
hex digit of the RDS country code, low byte the TMC location table number
(`0x3219` = CZ, CC 2, LTN 25; `0x4401` = DE, CC D, LTN 1). `TMC/reception.dat`
(208 B, 8-byte rows) lists the same 14 pairs as `ff 0f CC LTN 00 ff ff ff`
rows (GB as `03 0a 0c 0a …`); the first two rows are not decoded (C-2320–C-2322,
`python3 tools/tmc_reception.py join reception.dat RDSTM001.DAT MAPAL001`).

### Table dump

`0x003a0034` prints the twelve fields in order; its format strings are at
`0x0003cbb0` (`hdlm recorde info`), then `0x0003cb90` `LocationCode(%d)`,
`0x0003cb68`, `0x0003cb44`, `0x0003cb18`, `0x0003caec`, `0x0003cac8`,
`0x0003caa4`, `0x0003ca80`, `0x0003ca5c`, `0x0003ca3c`, `0x0003ca0c`,
`0x0003c9e8`.

### Consumer split

- Search / guidance text uses this record, keyed by `(country,
  location-database no, location code)` (`0x003bcb48` request, type `0x14e4`).
- The routing graph is mesh-keyed: `link[mesh(0x%x),no(%d),rdtype(%d)]`
  (`0x00011eb2`), `...,lktype(%d),rdtype(%d)` (`0x00011f0e`),
  `dir(%d),speed(%d)` (`0x00011f46`), `RGD(TurnList)` (`0x00020f30`).
  Nothing in the `RGD`/`RPF` bands references this volume or these getters.
- Consequence for the writer: `RDSTM001` must carry the twelve TMC attributes
  above; speed, one-way and restrictions are **not** here.

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

### Code-side reader (M3.15, located)

The record walk and the name decode are named (EXP-2026-11-20-M3.15-lctbl-reader;
C-2205, C-2208, C-2209). All VAs below are `Navi.exe` build A `CODE sec0`
(`va_class.py --resolve-with 0x3e00200`), none is `INIT`.

- **Record walk = the C-884 field directory.** `fn 0x003f61bc(handle, rec,
  field)` is the accessor, built from `0x003f56bc` (data start, C-5131),
  `0x003f57a8` (field count), `0x003f5e10` (field offset) and `0x003f5d98`
  (field length). The same rule frames 247,089/247,089 EU and
  303,023/303,023 US records (M4.16b, C-5132). `0x003f61bc` does **not** read
  the page itself: `0x003f51e0` maps the handle to the block (C-5130), and the
  page-buffer reader is the per-volume page-cache registration `0x0040de98`
  (M9.38, C-3607), which copies `@(8,r4)`/`@(4,r4)`/`@(2,r4)` into a 20-byte
  slot of the 32×20 table at `0x00d53640` and is *not* the walk (C-2208).
- **Twelve extractors, one per catalog field,** called in field order by the
  TMC record decoder `fn 0x003bc960` (C-882); the index is set by the
  `mov #N,r6` + `jmp 0x003f61bc` thunks `0x003f60e0/ec/f8/6104/6110`,
  `0x003f68b0`, `0x003f66b8`:

  | Field | Catalog column | Extractors / index | Struct offset |
  | --- | --- | --- | --- |
  | 0 | location type | `0x003f66b8` (0) | `+0x04` |
  | 1 | road number | `0x003bc028` (2) via `0x003f60e0` | `+0x14`/`+0x1c` |
  | 2 | road name | `0x003bc194` (1) via `0x003f60ec` | `+0x12`/`+0x40` |
  | 3 | primary location | `0x003bc300` (3) via `0x003f60f8` | `+0x16`/`+0xc4` |
  | 4 | secondary location | `0x003bc470` (4) via `0x003f6104` | `+0x18`/`+0x148` |
  | 5 | area | `0x003f6734` (5) | `+0x06` |
  | 6 | linear | `0x003f6780` (6) | `+0x08` |
  | 7 | negative | `0x003f67cc` (7) | `+0x0a` |
  | 8 | positive | `0x003f6818` (8) | `+0x0c` |
  | 9 | urban | `0x003f6864` (9) | `+0x0e` |
  | 10 | exit/junction | `0x003bc748` (10) via `0x003f6110` | `+0x1a`/`+0x1cc` |
  | 11 | inter-section | `0x003f68bc` (11) via `0x003f68b0` | `+0x10` |

  The walk is reached from the TMC handlers `0x003bcac0`/`0x003bcbc4`/
  `0x003bcc7c`, **not** from the `0x004125a8` subtree M3.23 ranked (C-2208).
- **String decode = `fn 0x003ca858(buffer, byte_len, mode)`.** `mode == 1`
  (the branch every string extractor uses, e.g. `0x003bc0ac` in
  `0x003bc028`) reads a buffer of **big-endian 16-bit words** and stores each
  as a native little-endian `u16` — `(w<<8)|(w>>8)`, high byte first, `r2 +=
  2` — one character per halfword; `mode == 2` does the same 4 bytes at a time
  (C-2205).
- **Encoding = single-byte CP_ACP** (C-1799): the loop leaves one byte per
  character in the low half of each `u16` (pad `0x00` in the high half), with
  no multibyte check and no UTF-16 pair. The only transform is the 16-bit
  high-byte-first swap. Card record 0 of stream 2 carries
  `42 65 72 61 6e 6f 76 fd 63 68` (`Beranových`, CP1252 `ý`=`0xfd`), exactly
  the bytes the swap loop consumes.

Reproduce (see the EXP for the full set):

```bash
IMG=archive/head256.img
python3 tools/sh4xref.py $IMG Navi.exe --image-start 0x200200 --resolve-with 0x3e00200 --calls 0x003f61bc
# jsr 0x003f56bc / 0x003f57a8 / 0x003f5e10
python3 tools/sh4xref.py $IMG Navi.exe --image-start 0x200200 --resolve-with 0x3e00200 --calls 0x003bc960
python3 tools/sh4dis.py $IMG Navi.exe --image-start 0x200200 --va 0x003ca858 --count 120
python3 tools/tmc_fielddir.py walk LCTBL001.DAT   # directory exact 247089, mismatch 0
```

Prior history: the first M3.15 pass called `0x0055d924`/`0x0055d954`
"compressed sec1 helpers"; H49/C-3443 showed they are the IAT imports
`OSMDLL!OSM_isSender`/`OSM_Printf`, and the H49 reopen's two writer-inverse
signature families scanned Navi.exe sec0 and OBJDLL.dll sec0 with 0 hits
(C-2203, C-2204, C-2207). The signatures were the miss, not hidden bytes.

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
- The name bytes are ASCII + Latin-1/CP1252, **not** ISO-8859-2: letters
  outside Latin-1 are transliterated by dropping the diacritic (`Č`→`C`,
  `ř`→`r`, `ł`→`l`), while Latin-1 letters survive (`München` keeps `ü`).
  See [Writer rules for names](#writer-rules-for-names-m39).
- Content is hierarchical: `Evropa` → `strední Evropa` → `Ceská Republika` →
  `Praha` → `Hl. m. Praha` → `kraj` → `okres` → municipality → street
  (the háček/caron letters are already stripped in the data).
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

Then four name slots, each exactly `2 * lenN` bytes. A slot holds a
single-byte name (CP1252/Latin-1, see [Writer rules for
names](#writer-rules-for-names-m39)) padded to an **even byte length with
`0x00`** — so an even-length name fills its slot exactly and an odd-length
name carries one trailing NUL. Two consecutive names therefore have no
separator when the first is even-length. This is why a NUL-scan over the plain
text miscounts: it sees padding, not terminators.

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

### Writer rules for names (M3.9)

The firmware side is decoded in
`EXP-2026-11-06-M3.9-name-collation` (build A); these are the rules a writer
must follow for `LCTBL001` names and for the `ADDRE`/`POINT` name strings.

1. **Encoding.** One byte per character in the system ANSI code page
   (CP_ACP). The firmware converts with `MultiByteToWideChar(CodePage = 0, …)`
   (VA `0x02ed41fc` in `NaviSearchCC.dll`). The shipped text is ASCII +
   Latin-1/CP1252. There is no ISO-8859-2 path: `STDDLL.dll` classifies
   ISO-8859-1/5/6/9 only, and the data contains no Latin-2 letter codes.
2. **Characters outside Latin-1.** Transliterate by dropping the diacritic,
   exactly as the vendor data does (`Cesk`, `stredn`, `Zizkov`, `Plzen`;
   Polish admin names `KEPNO`, `SLOWINO`, `DABROWA`). Do not emit ISO-8859-2
   bytes and do not substitute digraphs: a Latin-2 byte would be read as a
   CP1252 symbol or another accented letter.
3. **Length.** On the card, a name is a padded slot of `2 * lenN` bytes
   (max observed: field 1 10 B, field 2 86 B, field 3 100 B, field 4 64 B;
   see "Record layout"). At runtime the firmware copies names into
   fixed-capacity string objects (`STD_StringImp_initPrm` `0x03465760`,
   `input` `0x03465888`, which truncates): road formal name **32** chars,
   road common name **128** (`OBJ_RoadName_initPrm` `0x0349fb60`); place
   country/state **64**, county/city **128** (`OBJ_PntName_initPrm`
   `0x0349c4d4`). Keep names inside both bounds; do not rely on truncation.
4. **Order.** The on-card name streams are **unordered** with respect to the
   firmware collation (50.4 % of adjacent pairs ascend under the firmware's
   own key; 1 of 513 streams is sorted), so a writer must not sort or
   binary-search them. Sorting happens at runtime.
5. **Collation.** Where the firmware sorts (registered points, phone book), it
   uses its own table (`OBJDLL!OBJ_Sort_cmpStr` `0x0349d3b4`, weights at
   `0x03485400`/`0x03485500`): case-insensitive, accent-folding, letters
   (`0x47`–`0x60`) < digits (`0x64`–`0x6d`) < punctuation, ties by length;
   the binary search uses `STD_StringImp_comparePriority` (`0x03467d84`).
   Nothing in the file format depends on reproducing that order.

## Placement / join key (M4.16, negative)

No join key from M4.1 16-byte row fields (`id,pad2,ref,src,dst,code,tail`) to
tile road segments was identified (EXP-2026-11-06-M4.16-rdstm-placement,
C-1810–C-1812). `src/dst/code` vs section 1/2 link ids match at chance given
the dense lid value space (sec1 lids 25,147/65,536, all 0–255 present, 8 tiles);
`ref` vs section-1/2 parcel and stream `(A,B)` keys gives 0 hits (random
control 0). `INTER001`–`INTER005` show `ref` LE/BE byte-pattern enrichment vs
random u32 (e.g. 95/1, 116/7) — an unverified aligned-record lead, not a
segment join. M4.15/C-884 (undecoded per-record field directory) and
M3.7/C-887 (RDSTM is TMC, not a mesh-keyed graph) mean placement likely needs
the per-record/TMC→location decode or an `INTER/FRWAY`→mesh→coordinate chain.
Tool: `tools/rdstm_place.py`.

M4.16b re-test (`rdstm_place.py probe-decoded`, tile `B48R058R`): no decoded
field and no form of the RDSTM link reference joins tile ids above chance per
record (C-5136); the route to coordinates is the link-group decode, done in
M4.16e: a ref is `(group, entry)` → `(node, link)` of a section-2 parcel record
(see "Link groups" above, C-5139/C-5370).

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
| kind code | LCTBL column 0 (record offset `0x23`) | column verified; read as "location code" (`0x003f66b8`) |
| road no | column 1 (`0x2f`) | string field, getter `0x003bc100` |
| road/first/second name | columns 2–4 (`0x3c/0x49/0x57`) | string fields, getters `0x003bc26c`/`0x003bc3d8`/`0x003bc548` |
| area / liner ref | columns 5–6 (`0x63/0x70`) | u16 codes, extractors `0x003f6734`/`0x003f6780` |
| negative/positive offset | columns 7–8 (`0x80/0x90`) | front/rear code, extractors `0x003f67cc`/`0x003f6818` |
| urban | column 9 (`0x9b`) | u16, extractor `0x003f6864` |
| exit/junction no | column 10 (`0xab`) | string field, extractor `0x003bc748` |
| Inter-section code | column 11 | u16, extractor `0x003f68bc` |
| speed / direction / turn restrictions | not in the record | VERIFIED (negative, C-885) |

The byte offsets `0x23…0xab` are the `LCTBL001` catalog column offsets; the
firmware resolves the same twelve fields through a per-record field directory
instead of fixed offsets, in the same order.

`INTER`/`FRWAY` IDs were not located in these two files (see
[inter-frway.md](inter-frway.md)).
