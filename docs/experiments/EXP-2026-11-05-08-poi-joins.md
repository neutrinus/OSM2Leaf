# EXP-2026-11-05-08: POI page mapping, point roles and icon container

- **Status:** done (icon-id mapping still open)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-210…C-216
- **Supersedes:** the "f11 is dense only on single-page shards" reading
- **Superseded by:** none

## Question

How does the 24-byte POI index `f11` map to records, which of the two 4-byte
point copies is the display point, is there a record-level POI↔ADDRE join, and
what is `BICON001`?

## Hypothesis

`f11` encodes `(page, slot)`; one point copy is the display point and the other
is an address reference; ADDRE can be joined by street + house number;
`BICON001` is an icon container.

## Inputs

| Item | Value |
| --- | --- |
| Image | `leaf2011.img` |
| SHA-256 | `105e2032…76307` |
| POINT shards | 004 (13 pages), 021 (68 pages), 017, 032 |
| Tools | `point2.py`, `poilib.py`, `addrelib.py` |

## Method

- Re-derive POINT record framing; text tail is bracketed by two copies of the
  area code: `[u16 f7][u16 f8] TEXT [00][u16 f8]`.
- Test `f11 = (2000*page + slot) & 0xffff` against the record order.
- Compare point copy A and B with the COORD001 region box and with ADDRE ids.
- Join by `(street name, house number)`.
- Parse `BICON001` as a PNG table.

## Observations

### `f11` formula

```
f11 = (2000 * page + slot) & 0xffff
```

| Shard | Pages | Records | Match | Slot-only control |
| --- | --: | --: | --: | --: |
| POINT004 | 13 | 13,000 | **12,912 (99.3 %)** | 8.6 % |
| POINT021 | 68 | 68,000 | **64,882 (95.4 %)** | 9.6 % |

The id is 16-bit and the per-page block is 2000, not 1000; the other 1000 ids
per page exist with a different `(f7,f8)` multiset (hypothesis: `INFORMATION`
sub-records). On a one-page shard the formula degenerates to `f11 = slot`.

### Point copies

- **A** is inside the `COORD001` region box in 100 % of records.
- On Monaco, **B** is outside in 337/380 while A is inside 380/380.
- B matches the street's ADDRE id more often: Monaco **254/267 (95 %)** vs A
  **26/267 (10 %)**; Luxembourg **2115/2448 (86 %)** vs **1756/2448 (72 %)**.
- A−B is 0/1/8/12/13 units, mostly `(8,8)`/`(12,12)` — a re-quantisation,
  not an entrance-level nudge.

So **A = display point, B = address reference**.

### POI ↔ ADDRE

A genuine record-level join via `(street, house number)`:

```
POINT017 "AUTO KONCEPT11@BOULEVARD ALBERT 1ER"  A=a0cfd1bd B=a0c3d1b1
ADDRE017 "BOULEVARD ALBERT 1ER" -> id a0c3d1b1, ranges 17;17, 21;27, 25;25, 27;27
```

ADDRE splits a street by house range; the POI appends its house number, so
(street, number) selects the record. The id alone is only a cell (Monaco: 239
streets, 13 ids).

### BICON001

```
0x0000  512-byte header
0x1000  header (u16 @0x100a = 0x0067 = 103 icons)
0x1016  u32 table (start, size), cumulative
0x1408  103 PNGs (32x32; five 30x30)
```

`point2.py bicon --out icons` extracts all 103. The icon code → PNG mapping is
still **UNKNOWN**: there is no icon-id table inside POINT, and `f0` is
constant per file (0/3/16/20), i.e. a table id.

## Interpretation

- **FACT:** `f11` is a 16-bit `(page, slot)` index with a 2000 stride.
- **FACT:** A is the display point; B is the address reference.
- **FACT:** POI↔ADDRE joins at record level by street + house number.
- **FACT:** `BICON001` is a PNG icon container with 103 icons.
- **UNKNOWN:** icon code → PNG, the second 1000-id block, the bit-packed field
  block origin, REFER002 `xy-coordinates`.

## Conclusion

`docs/format/refer.md`, `docs/format/assets.md` and claims C-210…C-216 were
updated. POI location is now solved for display and address lookup; only icon
mapping and the bit-packed field block remain.

## Follow-ups

- [ ] Decode the `INFORMATION` group and test it against the second id half.
- [ ] Locate the true bit origin using a record with a known area code.
- [ ] Match a known POI icon to one of the 103 PNGs.
- [ ] Isolate REFER002 `xy-coordinates` bits.
