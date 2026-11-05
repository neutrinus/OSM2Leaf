# Map image lineage (2011 → 2019)

Samples downloaded from `https://files.viaaq.eu/maps/` and
`https://files.viaaq.eu/sd-images/` into `archive/images/` (55 GB, SHA-256
verified; git-ignored). The old `/home/marek/projekty/leafre-work/images/`
paths are symlinks to the archive.

## Inventory

| File | Size | Target |
| --- | --: | --- |
| `LEAF_2011-2012_QSD-309-101_navi158_eu.img` | 8,057,257,984 | Leaf ZE0, EU 2011 |
| `LEAF_2014_EU_QSD-357-101.img` | 7,969,177,600 | Leaf, EU 2014 |
| `EU_MAPDATA_13-14.7z` | 6,088,466,708 | map tree, build 13/06/17 |
| `EU_MAPDATA_14-15.7z` | 6,273,414,589 | map tree = 2014 image |
| `EU_MAPDATA_16-17.7z` | 6,635,659,459 | map tree = 2016 image |
| `ENV200_2016_EU_QSD-390-100.img` | 7,969,177,600 | e-NV200, EU 2016 |
| `ENV200_2019_25920-6WX1C-EUR.img` | 16,039,018,496 | e-NV200 2019, **different generation** |

## L1 validation matrix

`tools/cardcheck.py` results on the archived set (see
[`EXP-2026-11-05-30`](../experiments/EXP-2026-11-05-30-image-matrix.md)):

| Sample | L1 result | Note |
| --- | --- | --- |
| 2011 EU image | PASS | reference; 194/194 `.cmp`, DRSTR 40/324, MMAIN 11/11 |
| 2014 EU image | PASS | `TFTBL001` warning |
| 2016 e-NV200 image | PASS | requires `--ignore-dump-artifacts` (AppleDouble files) |
| 2013-14 map tree | PASS | requires `--partial`; DRSTR has a stale `VER_INFO` node |
| 2014-15 map tree | PASS | requires `--partial`; same stale `VER_INFO` |
| 2016-17 map tree | PASS | requires `--partial`; same stale `VER_INFO` |
| 2019 e-NV200 image | FAIL | different engine (`CLA-NAVI06-01`/ZENRIN); not a ZE0 sample |

L2 now passes on the 2014 and 2016 full trees with
`--no-golden --ignore-dump-artifacts`. The unchanged dense `B30R048R` uses a
preserved-layout fallback; the 2011 golden profile remains the reference.

## `VER_INFO/HDD_INFO.TXT` (2011–2016)

72 bytes, six CRLF lines, no trailing newline:

| line | 2011 | 2014 | 2016 |
| --- | --- | --- | --- |
| 1 | `QSD-302-100` | `QSD-302-100` | `QSD-302-100` |
| 2 | `QSD-309-101` | `QSD-357-101` | `QSD-390-100` |
| 3 | `02-110100-00` | `02-140300-00` | `02-160500-00` |
| 4 | `SDC08-EVEUR` | `SDC08-EVEUR` | `SDC08-EVEUR` |
| 5 | `11-05` | `14-06` | `16-02` |
| 6 | `470323501005` | `470516001006` | `470677200002` |

Line 1 is constant (base card code), line 2 tracks the map set and matches the
FAT volume label, line 3 is a sub-version, line 5 is year-month, line 6 is a
Clarion part number.

## What stayed the same (2011 → 2016)

- Common header: `CLA-NAVI05-01`, `FORMAT VERSION X08-02-00`, `V05.00.00` in
  `MMAIN001.DAT` at every vintage.
- 46 `MAPAL001` files with **identical names** (45 `BxxRyyR.DAT` +
  `LEV3456R.DAT`).
- 194 `.cmp` + `.ind` pairs in `REFER001` at every vintage.
- `CMP.LST` byte-identical.
- The three-volume card layout: ~100 MiB firmware region outside the MBR,
  7.55 GiB FAT32 map partition at sector 204802, ~300 MiB TFAT16 volume, then
  `0xff` padding.

## What changed

- 2011 → 2014 top level: **`TFTBL001/` appears** (and nine icon-only speech
  languages). `REFER002/ICODE001.DAT` appears from 2013.
- Everything else grows in size; the structure is stable.
- The `EU_MAPDATA_*.7z` archives are repacks of the card images:
  `14-15` has the same `MMAIN001.DAT` hash as the 2014 image, `16-17` the same
  as 2016. `13-14` has a stale `VER_INFO` node in `DRSTR001.DAT` but no
  `VER_INFO/` folder.

## 2019 is a different engine

`ENV200_2019_25920-6WX1C-EUR.img` is **not** ZE0:

- label `485-3651-01`, partition at sector 888833
- 14,827 files, new dirs `DFRMR001`/`HOUSE001`/`OBJCT001`/`XPICT001`
- `DB_INFO.TXT` instead of `HDD_INFO.TXT`
- `MMAIN001.DAT` = `CLA-NAVI06-01` / `X08-03-00` / **ZENRIN**
- contains macOS dump artefacts (`.fseventsd`, `._MMAIN001.DAT`)

This is the QY8x family documented by `osm2clarion`, not the ZE0 format. Do
not use it as a ZE0 reference except for cross-checking the format family.

## Cross-year differential (2011/2014/2016)

A direct comparison of the three ZE0-era images shows the same 46 tile names,
194 `REFER001` pairs and 11 `MMAIN` rows in every year, but growing data:

- `HDD_INFO.TXT` line 1 is constant (`QSD-302-100`); lines 2, 3, 5 and 6 track
  map set, build, year-month and part number.
- `B30R048R.DAT` section 4 has 20/24/24 records and 68/126/129 names.
- `REFER002` grows from 15 `POINT` shards in 2011 to 29 in 2016, with
  `ICODE001.DAT` appearing from 2013.
- `TFTBL001` and a larger speech set appear from 2014.

These are observed cross-year differences, not proof of which fields the unit
validates. See `EXP-2026-11-05-32`.

## Implications

- The ZE0-era map format is stable across 2011–2016; a compiler target can be
  defined once. 2013+ cars are the AZE0 vehicle generation, but the navigation
  format family is still `CLA-NAVI05-01` / `X08-02-00`.
- The L2 `B30R048R` difference at `0x807` is a tile-section/header variant
  inside that family, not a new architecture.
- `TFTBL001` is optional for the 2011 baseline; decide later whether to
  support it.
- The 2019 image is a useful comparison for the QY8x/`osm2clarion` lead, but
  not for the ZE0 compiler.
- The US 2011 dump is still the missing ground truth for market differences.
