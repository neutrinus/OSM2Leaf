# `COORD001`, `ZCODE*`, `ICODE001`

Sample: EU 2011 image
(SHA-256 `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`).

> **Evidence status:** layouts and the coordinate formula are `VERIFIED`;
> COORD001 `level`/mask and header fields are `VERIFIED` (EU+US, M4.12);
> ZCODE form-A offset base and record addressing are `VERIFIED` (EU ZCODE018/033, M4.12);
> ZCODE form-B directory/offset-base is `OBSERVED`/partly unresolved;
> ICODE001 ISO header and per-language country-chain roots are `VERIFIED` (EU+US, M4.12)
> but the root-pointer index table location is `UNKNOWN`.
> Region-to-country mapping is `OBSERVED`/`HYPOTHESIS` except where a bounding
> box or place name confirms it.

## `COORD001` — region bounding boxes

`COORD001` is **not** a point list. It is a table of *N* region bounding
boxes (EU 33, US 11), one per country/region payload, in the same grid as
`MAPAL001`.

```
0x1000  u32 guard          (== last region's level_u32; EU 0xf0, US 0x56)
0x1004  u16 count          (33 EU, 11 US)
0x1006  u16 field2         (7, both EU and US)
0x1008  u32 field3         (0x00008000, both EU and US)
0x100c  u32 zero
0x1010  count * 14-byte records, big-endian
        + 1 all-zero sentinel record
```

Record:

```c
struct coord_region {
    uint16_t x0;      // latitude min (grid)
    uint16_t y0;      // longitude min (grid)
    uint16_t x1;      // latitude max (grid)
    uint16_t y1;      // longitude max (grid)
    uint32_t level;   // 48-bit mask, high 32 bits
    uint16_t pad;     // 48-bit mask, low 16 bits
};
```

### `level` / region mask (VERIFIED, M4.12)

`M = (level_u32 << 16) | pad_u16` is a 48-bit field. For region `i`
(1-based, `i = 1..count-1`, all non-last regions):

```
M = 0x400000000000 >> (i - 1)      (one-hot, bit 46 down)
```

This holds for every non-last region on EU (r1–r32) and US (r1–r10),
including EU r32 where the bit spills into `pad_u16` (`level_u32=0`,
`pad_u16=0x8000`, `M=0x000000008000`).

The **last** region is not one-hot: `M` is an aggregate
(EU r33 `0x000000f00000`, `level_u32=0xf0`; US r11 `0x000000560000`,
`level_u32=0x56`) and **`level_u32 == guard`** (header 0x1000).

Interpretation: a 48-bit region membership/selection bitmask with one bit per
non-last region in order, plus an aggregate/summary in the last slot; the
exact runtime semantics of the mask and of `field2`/`field3` remain to be
confirmed against firmware use (the bit positions and guard invariant are the
verified structural facts).

### Coordinate decoding

```
lat = (x - 32768) / 192        // 192 = 128 * 3/2
lon = (y - 52742) / 128
```

- Least-squares over 33 regions: ~0.031° lat / ~0.073° lon rms.
- The asymmetric divisors are the tile grid: 1 grid unit = 1° lon = 2/3° lat,
  stored at 1/128.
- Record *i* describes region *i+1*. Proof: the coordinate payload of
  `ZCODE018` lies inside record 17 in both axes.
- Outliers confirm the fit: Spain only fits with the Canaries, the UK only
  with Gibraltar, Denmark with Bornholm, Finland with Åland, Greece with the
  east Aegean, Portugal with Madeira.
- `REFER002/COORD001.DAT` has 15 records: a strict subset of the 33 boxes in
  a different order.

Open: runtime semantics of the mask/`field2`/`field3`; longitude origin
`52742` rationale.

## `ZCODE0nn` — postal-code tries

`ZCODE0nn` is a digit/character trie, **not** a string table. Postal-code
text is never stored; `strings` will not find it. EU has 33 files (one per
region); US factory REFER001 has no ZCODE files.

Two on-disk forms are observed in the EU sample (M4.12):

### Form A — filled header, ADDRE-style trie + addr-encoded records (VERIFIED)

Files: `ZCODE018` (Netherlands, 9.8 MB), `ZCODE033` (UK, 37 MB).

Header fields (BE):

| offset | field | meaning |
| --- | --- | --- |
| 0x1006 | u32 | node table size in halfwords |
| 0x100e | u16 | `first` (first child/root index) |
| 0x1012 | u32 | `rec_addr_enc` — **encoded sector address** of record block (see below) |
| 0x1016 | u32 | record area size (bytes) |
| 0x101a | u16 | record width field (0 in file; writer uses ZREC_W=8) |
| 0x1032 | u8 | `cr/2` (cr = trie record bytes, 12) |
| 0x1033 | u8 | `kw` (key width, 1) |

Trie: ADDRE-style `crec` nodes at **0x1100**; child offsets are in
**halfwords** (`child_node_byte = 0x1100 + child_hw * 2`). Leaf when
`size==0`, `rec_index = child / 8`.

Record block base (byte offset) uses the **`addre_io` sector encoding**
(confirmed: `zcode018 rec_addr_enc 0xbaf00` → `unaddr = 0x5d7800`):

```
addr(off)   = (off // 0x800) << 8 | (off % 0x800) // 0x100   (off % 0x100 == 0)
unaddr(enc) = (enc >> 8) * 0x800 + (enc & 0xff) * 0x100
record_base = unaddr(rec_addr_enc @ 0x1012)
record      = record_base + rec_index * 16
```

Verified (ZCODE018): record index 0 at `0x5d7800` = `(42830,53372,1712,467,
42830,53372,2012,280)` (NL bbox coords). Note: `zcode_io.assemble` produces
this form and writes 16-byte ladder records; observed ZCODE018/033 record
semantics (coord-like vs area-ladder) differ by file — the **addressing/base
is the verified part**, record payload interpretation remains per-file/OBSERVED.

### Form B — sentinel header, directory/index (OBSERVED, offset base unresolved)

Files: the other 31 EU ZCODE files (e.g. ZCODE001,002,005,013).

- Header 0x1006/0x100e/0x1012/0x1016 sentinel/zero (`rec_addr=0xffffffff`,
  `nodew=0`); still carries `cr/2` (0x1032=6→12), `kw` (0x1033=1), `area`
  (0x1042), and a `ZCODE_FH`/ZIP-CODE frame signature.
- Directory/index entries observed from 0x1204 as 12-byte
  `>HHBBHI (size, 0, tag, 0, count, offset)` blocks (digit/letter tags,
  terminators), with 16-byte **area-ladder** result records (BE halfwords,
  `0xffff` padding, trailing `0x0000`; e.g. ZCODE002 Belgium `(1,2,3,19,2,
  65535,65535,0)`).
- **Offset base (UNRESOLVED):** `offset` values do not resolve to child
  blocks/records under a single constant base (absolute, rel-0x1100,
  halfword-0x1100, `unaddr`, rel-entry and sector forms all fail to give a
  uniform rule across root-level entries; `offset=0` appears with inline/
  mixed interpretations). Form-B child resolution needs a traced walk of the
  0x1100/0x1204 structure or firmware confirmation.

The older simplified directory/leaf structs below describe the *kind* of data
present but not the verified addressing; they are **superseded in detail** by
the form A/B split above.

Directory entry (12 bytes, OBSERVED form):

```c
struct zcode_dir {
    uint16_t size;    // multiple of 6; exact meaning unknown
    uint16_t zero;
    uint8_t  tag;     // '0'..'9' or 'A'..'Z'
    uint8_t  zero;
    uint16_t count;
    uint32_t offset;  // base UNRESOLVED for form B (M4.12)
};
```

Leaf/record area (16 bytes observed as ladders in form B / per-file in form A):

```c
struct zcode_rec16 {
    uint16_t v[8];    // form B: area ladder + 0xffff + trailing 0;
                      // form A (ZCODE018): coord-like pairs (OBSERVED)
};
```

## `ICODE001` — country schemas + place names

EU ICODE001 is 111 MB decompressed (US 6.1 MB). `REFER001/ICODE001.DAT` and
`REFER002/ICODE001.DAT` exist; this section describes REFER001.

### ISO table at 0x1000 (VERIFIED, M4.12)

```
0x1000  u16 size_halfwords   (table byte size / 2)
0x1002  u16 country_count
0x1004  country_count * 462-byte ISO entries  (icode_io.iso_entry)
```

EU: `(7625 halfwords = 15250 B, 33 countries)` covering `0x1000..0x4b92`.
US: `(464 halfwords = 928 B, 2 countries)`. First ISO-entry field is a
462-byte stride in halfwords (`0x00e7=231`). Tier labels use a `2=`/`3=`
prefix and UTF-8 (per `icode_io`).

### Area-name tree and trie roots (VERIFIED roots, index table UNKNOWN)

The name tree is chains of 12-byte-header + name rows (`icode_io`: `>HHIHH` =
`rlen|nosub, nlen, roff, cnt, idx` + name field). **Within a chain, `roff`
and sizes are halfwords relative to the start of that language's own country
chain** (`icode_io`).

**Per-language country-chain roots** (byte offsets of the first country row,
`idx==0`, `nosub==0`, chain of `country_count` top-level rows) located by
chain tracing (M4.12, `tools/coord_zcode_icode.py --verify-icode`):

| image | languages found | root byte offsets (hex) | first chain entries |
| --- | --- | --- | --- |
| EU | 7 | 0x4d00, 0x1a91900, 0x27d7f00, 0x351e500, 0x4264a00, 0x4fab000, 0x5cf1600 | ANDORRA + 32 countries, localized per language |
| US | 2 | 0x1500, 0x2e5d00 | CANADA, UNITED STATES |

EU refer header 0x18c lists 8 active language codes
(`05,04,02,07,0a,06,08,14`), while 7 full 33-country chains were located by
ANDORRA/chain tracing; the 8th mapping is not resolved here.

**Root-pointer index table: UNKNOWN (not located).** Refer header slots for
ICODE001 are only 4 (EU `addr=512,blk=60` → 0x20000; US `addr=512,blk=4`) and
13 (EU 0x90400; US 0x20400), which are data/name frames, not root lists. No
raw byte-offset or sector-address root table matching the verified roots was
found in the refer header or 0x0000–0x50000. The firmware may resolve roots
via a slot/frame structure not yet decoded; the **root offsets themselves** are
the verified result.

Refer header slots (EU): `(4,(512,60)), (13,(2308,1))`. US: `(4,(512,4)), (13,(516,1))`.

Open: root-pointer index table location; the 8th EU language mapping; the
partly remapped charset in names.

## Region numbering

From `ICODE001` schemas (country attribution is `HYPOTHESIS` except where a
bounding box or place name confirms it):

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

Missing from the 33: Iceland, Malta, Cyprus, Turkey, Belarus, Ukraine, Russia,
Moldova, Bosnia, Serbia, Montenegro, Albania, North Macedonia — consistent
with a Western/Central Europe 2011 map.

## Reproduce

Real-file verification (vendor data outside repo; paths as on this machine):

```bash
python3 tools/coord_zcode_icode.py --selftest
python3 tools/coord_zcode_icode.py --verify-coord /home/marek/projekty/leafre-work/root/REFER001/COORD001.DAT
python3 tools/coord_zcode_icode.py --verify-coord /home/marek/projekty/leafre-work/m5.12-us/root-factory/REFER001/COORD001.DAT
python3 tools/coord_zcode_icode.py --verify-zcode /home/marek/projekty/leafre-work/root/REFER001/ZCODE018.DAT --zcode-expect-index 0 --zcode-expect-vals 42830,53372,1712,467,42830,53372,2012,280
python3 tools/coord_zcode_icode.py --verify-zcode /home/marek/projekty/leafre-work/root/REFER001/ZCODE033.DAT
python3 tools/coord_zcode_icode.py --verify-zcode /home/marek/projekty/leafre-work/root/REFER001/ZCODE002.DAT
python3 tools/coord_zcode_icode.py --verify-icode /home/marek/projekty/leafre-work/root/REFER001/ICODE001.DAT
python3 tools/coord_zcode_icode.py --verify-icode /home/marek/projekty/leafre-work/m5.12-us/root-factory/REFER001/ICODE001.DAT
```

Supporting modules: `tools/cmpind.py`, `tools/coord.py`,
`tools/ze0-viewer/tools_ze0/{addre_io,zcode_io,icode_io,refer_header,frames}.py`.
Decompressed analysis samples (not committed) were used during investigation;
the commands above reproduce the verified checks from the `.cmp/.ind` pairs.

## Firmware reader status (M3.14, build A)

Name VAs in `Navi.exe` plain sec0 (EU image, build A): `ZCODE0` `0x0017933c`,
`ICODE001.DAT` `0x00178c88`, `COORD001.DAT` `0x00178e18`. `ICODE001` is loaded by
`fn 0x003f2cc0` (`0x003f2d70`), the candidate opener. No reader body and no
field-to-instruction map is located for any of the three files; `ZCODE0` and
`COORD001` have no plain-code literal load. Negative with control:
EXP-2026-11-08-M3.14-reader-layout (C-2190–C-2199). The layouts above stay as
written; this section adds only the firmware-side status.
