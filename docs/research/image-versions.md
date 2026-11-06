# Map image lineage (2011 → 2019)

This page is an evidence table, not a narrative. Each value comes from an
experiment record, a claim in [`claims.md`](claims.md), the 2011 golden profile
([`tools/golden/eu2011.json`](../../tools/golden/eu2011.json)), or
[`tools/verify.py`](../../tools/verify.py). If no such record exists, the cell
is `unverified`; it is not an estimate or a recollection. The prose that
previously occupied this page is not used as evidence.

## Examined samples

One row per sample with a repository record: four SD images and three map-only
archives. `Files / dirs / bytes` is the extracted filesystem census, not the
size of the `.img` or `.7z`. `Map tree` rows are extracted archives, not
complete cards.

| Sample (kind) | Market | Year | Card label | Format version | Engine | Files / dirs / bytes | `.cmp` pairs | Tiles | L2 result | Evidence |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- |
| `LEAF_2011-2012_QSD-309-101_navi158_eu.img` (SD image) | EU | 2011 | `QSD-309-101` | `X08-02-00` | ZE0 (`CLA-NAVI05-01`) | 480 / 39 / 5,173,965,667 | 194 | 46 (45 + `LEV3456R`) | PASS (golden `eu2011.json`) | [EXP-29](../experiments/EXP-2026-11-05-29-l1-l2-validators.md), [EXP-30](../experiments/EXP-2026-11-05-30-image-matrix.md), [EXP-32](../experiments/EXP-2026-11-05-32-cross-year-differential.md); C-120, C-505, C-506 |
| `LEAF_2014_EU_QSD-357-101.img` (SD image) | EU | 2014 | `QSD-357-101` | `X08-02-00` | ZE0 (`CLA-NAVI05-01`) | 504 / 58 / 6,821,761,753 | 194 | 46 (45 + `LEV3456R`) | PASS (`--no-golden --ignore-dump-artifacts`) | [EXP-30](../experiments/EXP-2026-11-05-30-image-matrix.md), [EXP-31](../experiments/EXP-2026-11-05-31-cross-year-l2.md), [EXP-32](../experiments/EXP-2026-11-05-32-cross-year-differential.md); C-120, C-504 |
| `ENV200_2016_EU_QSD-390-100.img` (SD image) | EU | 2016 | `QSD-390-100` | `X08-02-00` | ZE0 (`CLA-NAVI05-01`) | 505 / 58 / 7,180,933,678 | 194 | 46 (45 + `LEV3456R`) | PASS (`--no-golden --ignore-dump-artifacts`) | [EXP-30](../experiments/EXP-2026-11-05-30-image-matrix.md), [EXP-31](../experiments/EXP-2026-11-05-31-cross-year-l2.md), [EXP-32](../experiments/EXP-2026-11-05-32-cross-year-differential.md); C-120, C-504 |
| `EU_MAPDATA_13-14.7z` (map tree) | EU | 2013–14 | unverified | `X08-02-00` | ZE0 (`CLA-NAVI05-01`) | 504 / 57 / unverified | 194 | unverified | FAIL (informational L2; see note) | [EXP-30](../experiments/EXP-2026-11-05-30-image-matrix.md); C-502 |
| `EU_MAPDATA_14-15.7z` (map tree) | EU | 2014–15 | unverified | `X08-02-00` | ZE0 (`CLA-NAVI05-01`) | 503 / 57 / unverified | 194 | unverified | FAIL (informational L2; see note) | [EXP-30](../experiments/EXP-2026-11-05-30-image-matrix.md); C-125, C-502 |
| `EU_MAPDATA_16-17.7z` (map tree) | EU | 2016–17 | unverified | `X08-02-00` | ZE0 (`CLA-NAVI05-01`) | 504 / 57 / unverified | 194 | unverified | FAIL (informational L2; see note) | [EXP-30](../experiments/EXP-2026-11-05-30-image-matrix.md); C-125, C-502 |
| `ENV200_2019_25920-6WX1C-EUR.img` (SD image) | EU | 2019 | unverified | `X08-03-00` | QY8X (`CLA-NAVI06-01` / ZENRIN) | 14,827 / unverified / unverified | unverified | 53 | not run; `verify.py` returns `UNSUPPORTED` (exit 3) | [EXP-30](../experiments/EXP-2026-11-05-30-image-matrix.md); C-123, C-515 |
| `leaf_2011_usa_sddump.img` (SD image) | US | 2011 | `QSD-301-103` | `X08-02-00` | ZE0 (`CLA-NAVI05-01`) | 113 tiles; files/bytes unverified | 58 | 113 (112 + `LEV3456R`) | PASS (`--no-golden --ignore-dump-artifacts`; tiles skipped) | EXP-2026-11-05-35; C-070 |

Notes on the table:

- **L2 on the map-only archives.** EXP-30 ran `l2check.py --no-golden`
  informationally: `DRSTR`, 194/194 `.cmp` round-trips, tile semantic digests
  and the one-vertex mutation passed, but `B30R048R.DAT` failed the
  byte-identical rebuild at `0x807`/`0x808`, and the `POINT032.DAT` page
  `0x4200` POI fixture failed. These are the recorded archive results. C-504
  fixed L2 for the full 2014/2016 roots (EXP-31), not for these map-only
  archives; no later archive re-run is recorded.
- **L1 context.** L1 is PASS for the 2011, 2014 and 2016 SD images and for the
  three map trees. The 2014/2016 and map-tree runs used
  `--ignore-dump-artifacts`; 2016 explicitly fails strict L1 because of
  AppleDouble files, and the map trees also require `--partial`. The 2019
  image is a deliberate L1 FAIL (EXP-30; C-501).
- **Engine vs vehicle.** `Engine` is the navigation format family. The 2016
  sample is an e-NV200, and the 2014 Leaf is the later AZE0 generation; both
  still use `CLA-NAVI05-01` / `X08-02-00` (EXP-30, C-120). Only the 2019
  sample is the QY8x engine (`CLA-NAVI06-01` / `X08-03-00` / ZENRIN; C-123).
- **Year detection.** `verify.py` reads the year from `HDD_INFO.TXT` line 5
  ("MM-YY"). The map trees have no `VER_INFO/` directory, so their years in
  this table come from the EXP-30 sample names, not from `verify.py`.

## Sample identity

| Sample | `.img` / `.7z` size (bytes) | SHA-256 | Evidence |
| --- | ---: | --- | --- |
| `LEAF_2011-2012_QSD-309-101_navi158_eu.img` | 8,057,257,984 | `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307` | C-001, EXP-32 |
| `LEAF_2014_EU_QSD-357-101.img` | 7,969,177,600 | `4a8a21f477e9fc511f94406976b8d67037842f9c043f49ab24e1adc82d6da89b` | EXP-30, EXP-32 |
| `ENV200_2016_EU_QSD-390-100.img` | 7,969,177,600 | `f53d55f159fd4232caa0b100b9b12e3910c8fe3849201871a71ee38ac19007fb` | EXP-30, EXP-32 |
| `ENV200_2019_25920-6WX1C-EUR.img` | 16,039,018,496 | `8e95b1d6fd8772fe613ed0dd1902eb9fde48b8247f96ff084f8b1ceb72839f94` | EXP-2026-11-06-M4.14-cross-year-archive |
| `LEAF_2011-2012_US.img` | 8,057,257,984 | `53342430a1bb58d3ed6eb68c5563f079c710a400134d522e6192489b324c5383` | EXP-2026-11-05-35, EXP-2026-11-06-M4.14 |
| `EU_MAPDATA_13-14.7z` | 6,088,466,708 | `68d8b2f02b992c785c7fc33f9f1b1ea7ba2d74502e6904658b31a03655a45232` | EXP-2026-11-06-M4.14 |
| `EU_MAPDATA_14-15.7z` | 6,273,414,589 | `b61d0844557ab71ab6524a2a84b81a294e4b86bafeb135eedc81f0ea1fd6f442` | EXP-2026-11-06-M4.14 |
| `EU_MAPDATA_16-17.7z` | 6,635,659,459 | `7a215501d6b8e2bbcf0050dcc984f40ec26ab7c0a18d53536b6a9e608c659f59` | EXP-2026-11-06-M4.14 |

C-500 records that all seven files match the archived `SHA256SUMS`, but the
individual archive sums are not committed to this repository, so they are
marked `unverified` here.

## What the records support (2011 → 2019)

- **Stable ZE0-era family.** 2011, 2014 and 2016 share `CLA-NAVI05-01`,
  `X08-02-00`, `V05.00.00`, 45 `BxxRyyR.DAT` tile names plus `LEV3456R`, 194
  `REFER001` `.cmp`/`.ind` pairs and 11 `MMAIN` rows (C-120; EXP-32). EXP-30's
  conclusion extends the same navigation family statement to 2013–2016, which
  is why the three map-tree rows carry `X08-02-00` / ZE0.
- **`HDD_INFO.TXT`.** Line 1 is constant; line 2 tracks the map set and
  matches the FAT volume label; line 5 is year-month; lines 3 and 6 track the
  build and Clarion part number (C-121; EXP-32). The line-to-map-code-field
  mapping remains a hypothesis (C-304, C-316).
- **Feature growth.** `TFTBL001/` appears in 2014/2016 but not 2011;
  `REFER002/ICODE001.DAT` appears from 2013 (C-122). `REFER002` grows from 15
  `POINT` shards in 2011 to 28 in 2014 and 29 in 2016; 2011 has no
  `ICODE001` (EXP-32).
- **`REFER002` file count.** C-143's 16 files in 2011 is 15 `POINT` shards plus
  `COORD001` (C-152; EXP-32), not a contradiction with the 15-shard count.
- **Section 4.** `B30R048R.DAT` section 4 has 20/24/24 records and 68/126/129
  names in 2011/2014/2016 (C-126). The 2016 name count has a few suspicious
  short tokens and is marked medium confidence in EXP-32.
- **Archives are repacks.** `EU_MAPDATA_14-15.7z` has the same `MMAIN001.DAT`
  hash as the 2014 image, and `16-17.7z` the same as the 2016 image; the
  archives are map trees, not full cards (C-125; EXP-30). `13-14.7z` has a
  stale `VER_INFO` node in `DRSTR001.DAT` but no `VER_INFO/` folder (EXP-30).
- **2019 is a different engine.** `ENV200_2019_25920-6WX1C-EUR.img` uses
  `CLA-NAVI06-01` / `X08-03-00` / ZENRIN, `DB_INFO.TXT` instead of
  `VER_INFO/HDD_INFO.TXT`, a partition at sector 888833, 14,827 files and 53
  tiles (C-123; EXP-30). It is not a ZE0 reference.

## What remains unverified

- **US sample now examined.** `archive/leaf_2011_usa_sddump.img` is a North
  America ZE0 2011 card (SHA-256 `53342430…c5383`, label `QSD-301-103`);
  see the section below and EXP-2026-11-05-35. C-070 still stands for other
  US vintages only.
- **Map-tree identity.** Card labels cannot be read because there is no
  `VER_INFO/` folder; byte totals and tile-file counts for the three map trees
  are not in any experiment record.
- **2019 census.** The directory count, filesystem byte total, `.cmp` pair
  count are not recorded; the card label `485-3651-01` is now backed by
  EXP-2026-11-05-30 (C-123).
- **2013-14 build date.** The old inventory's `13/06/17` build label is not
  recorded in EXP-30, so it is omitted rather than repeated.

## US 2011 sample

`archive/leaf_2011_usa_sddump.img` is a North America ZE0 2011 card:

- SHA-256: `53342430a1bb58d3ed6eb68c5563f079c710a400134d522e6192489b324c5383`
- size: 8,057,257,984 bytes
- FAT label: `QSD-301-103`
- `HDD_INFO.TXT`: `QSD-301-100`, `QSD-301-103`, `02-100100-00`,
  `SDC08-EVNAM`, `10-30`, `470282203030`
- firmware version: `X210NBNI.147`
- `MMAIN001.DAT`: `DATA VERSION 10/08/12/01`
- CE ROM: 151 modules, 1 file, physical range
  `0x8cae1000`–`0x8e2788e0`
- map coverage: North America, lat `16.00..80.00 N`, lon `-172.00..-52.00 E`
- `MAPAL001`: 113 files (112 `BxxRyyR.DAT` + `LEV3456R.DAT`)
- `REFER001`: 58 `.cmp`/`.ind` pairs, 3,743,680,000 logical bytes
- `REFER001` shards: 11 (`ADDRE001..011`, `POINT001..011`, etc.)
- `REFER002`: only `COORD001.DAT` and `POINT001.DAT`
- top level has `XMD` instead of `TMC`; `SPEECH` has only `CF` and `US`

Validation: `cardcheck.py --image` PASS (after market-specific top-level
names and 13-byte DRSTR names), `l2check.py --no-golden
--ignore-dump-artifacts` PASS for census/DRSTR/`.cmp` round-trip (58/58), and
`cmpind_writer.py verify` 58/58 OK. Tile rebuilds are skipped because the EU
golden tile names are absent. The card is structurally valid; the differences
are market and map coverage, not corruption (EXP-2026-11-05-35).

## Fields that change with the map code

Derived from `tools/diff_years.py` on the 2011/2014/2016 EU roots
(`EXP-2026-11-06-M4.14-cross-year-archive`). "Constant" means identical in
all three EU ZE0 samples; "changes" means reported by `diff_years.py`.

| Field | Constant across ZE0 EU samples | Changes with the map code |
| --- | --- | --- |
| `VER_INFO/HDD_INFO.TXT` line 1 | `QSD-302-100` | — |
| `VER_INFO/HDD_INFO.TXT` line 2 (map set) | — | `QSD-309-101` → `QSD-357-101` → `QSD-390-100` |
| `VER_INFO/HDD_INFO.TXT` line 3 (build) | — | `02-110100-00` → `02-140300-00` → `02-160500-00` |
| `VER_INFO/HDD_INFO.TXT` line 4 (region) | `SDC08-EVEUR` | — |
| `VER_INFO/HDD_INFO.TXT` line 5 (year-month) | — | `11-05` → `14-06` → `16-02` |
| `VER_INFO/HDD_INFO.TXT` line 6 (part number) | — | `470323501005` → `470516001006` → `470677200002` |
| Common header `FORMAT VERSION` | `X08-02-00` | — |
| Common header `DATA VERSION` | — | `11/06/27/01` → `14/04/12/01` → `16/08/01/01` |
| Common header model / engine | `CLA-NAVI05-01` / `V05.00.00` | — |
| `0x180` binary block (10 bytes) | — | changes with the data version |
| `MMAIN001.DAT` level-table counts | — | section 1/2/4, levels 1/2 record counts grow |
| `MAPAL001` tile set | 45 `BxxRyyR.DAT` + `LEV3456R.DAT` | — |
| `MAPAL001` tile sizes / descriptors | — | sizes, record counts and bboxes change per tile |
| `REFER001` `.cmp`/`.ind` pairs | 194 | — (count stable; bytes change) |
| `REFER001` logical byte total | — | 2,390,610,176 → 3,113,173,760 → 3,290,088,192 |
| `REFER002` file set | — | grows: 2 files/15 POINT shards (2011) → 16 files/29 shards (2016); `ICODE001` from 2013 |
| `DRSTR001.DAT` entry `value` | — | file sizes change |
| `DRSTR001.DAT` directory set | — | `TFTBL001`, extra `SPEECH` languages appear from 2014 |
| `0x06000000` image copy | tracks `HDD_INFO.TXT` when an image is available | tracks `HDD_INFO.TXT` |

The US 2011 sample uses the same ZE0 format family but a different map code
(`QSD-301-103`, `SDC08-EVNAM`, `DATA VERSION 10/08/12/01`, 113 tiles,
58 `.cmp` pairs). The 2019 sample is a different engine family and is excluded
from this table (see the examined-samples row).

## Implications

- The ZE0-era format is stable across 2011–2016; one compiler target is
  enough. 2013+ cars are AZE0, but the navigation format family is still
  `CLA-NAVI05-01` / `X08-02-00`.
- The L2 `B30R048R` difference at `0x807` is a tile-section/header variant
  inside that family, not a new architecture.
- `TFTBL001` is optional for the 2011 baseline; decide later.
- The 2019 image is useful for the QY8x/`osm2clarion` lead, not for ZE0.
- Market differences are real (US: 151 modules, 113 tiles, 58 pairs); keep
  market and coverage columns separate when adding a vintage.
