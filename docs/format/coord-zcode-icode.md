# `COORD001`, `ZCODE*`, `ICODE001`

Sample: EU 2011 image
(SHA-256 `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`).

> **Evidence status:** layouts and the coordinate formula are `VERIFIED`; the
> region-to-country mapping is `OBSERVED`/`HYPOTHESIS` except where a bounding
> box or place name confirms it. Unknown fields are labelled.

## `COORD001` — region bounding boxes

`COORD001` is **not** a point list. It is a table of 33 region bounding
boxes, one per country/region payload, in the same grid as `MAPAL001`.

```
0x1000  u32 guard
0x1004  u16 33
0x1006  u16 7
0x1010  33 * 14-byte records, big-endian, sentinel-terminated
```

Record:

```c
struct coord_region {
    uint16_t x0;      // latitude min
    uint16_t y0;      // longitude min
    uint16_t x1;      // latitude max
    uint16_t y1;      // longitude max
    uint32_t level;   // one-hot / priority; meaning unknown
    uint16_t pad;     // 0
};
```

Decoding:

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

Unknown: the `level` field (one-hot in `REFER001`, non-positional in
`REFER002`) and the longitude origin `52742`.

## `ZCODE0nn` — postal-code tries

`ZCODE0nn` is a digit/character trie, **not** a string table. Postal-code
text is never stored; `strings` will not find it.

Directory entry (12 bytes):

```c
struct zcode_dir {
    uint16_t size;    // multiple of 6; exact meaning unknown
    uint16_t zero;
    uint8_t  tag;     // '0'..'9' or 'A'..'Z'
    uint8_t  zero;
    uint16_t count;
    uint32_t offset;  // base unknown
};
// terminated by ff ff ff ff ff
```

Leaf record (8 bytes):

```c
struct zcode_leaf {
    uint16_t x;       // latitude grid coordinate
    uint16_t y;       // longitude grid coordinate
    uint16_t sub_x;   // 0..0x7ff
    uint16_t sub_y;   // 0..0x7ff
};
```

Example: `ZCODE001` is region 001 (Andorra), 7 codes `AD100`…`AD700`,
top-level tag `'A'`, count 7. `ZCODE018` is a large region whose coordinate
payload fits `COORD001` record 17.

## `ICODE001` — country schemas + place names

```
0x1000..0x4b90   33 per-country administrative schemas, in region order
0x4c00..end      flat ASCII place-name records
```

Name record:

```c
struct icode_name {
    uint32_t id;
    char     name[];    // ASCII, NUL-padded to even length
    uint8_t  zero;      // 0x80
    uint8_t  a;         // unknown
    uint16_t b;         // unknown
    uint32_t null;      // 0xffffffff next-sibling
};
```

- At least 200,000 records; names are not stored in region order.
- Several disjoint id spaces; the trie roots and the partly remapped charset
  are `UNKNOWN`.

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

The full analysis scripts and decompressed samples live in
`/tmp/opencode/research-mapdata/coord-zcode-icode/` (not committed). The
tile-grid check is available in the repo as `tools/mesh_grid.py`.
