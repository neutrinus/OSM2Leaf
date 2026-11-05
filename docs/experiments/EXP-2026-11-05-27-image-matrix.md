# EXP-2026-11-05-27: full map-image archive and cross-year L1 matrix

- **Status:** done
- **Date:** 2026-11-05
- **Sample:** all seven files from `files.viaaq.eu` (four SD images and three
  map archives)
- **Claims:** C-409, C-410, C-411, C-412
- **Supersedes:** none
- **Superseded by:** none

## Question

Is the complete public map-image set present in `archive/images/`, do the
SHA-256 sums match, and does the L1 validator pass on the ZE0-era samples?

## Hypothesis

L1 passes on 2011–2016 ZE0 cards and map trees; the 2019 e-NV200 image is a
different engine and should fail the ZE0 checks. Dump artefacts may need an
explicit ignore option.

## Inputs

Remote inventory (2026-11-05):

| File | Size |
| --- | --: |
| `LEAF_2011-2012_QSD-309-101_navi158_eu.img` | 8,057,257,984 |
| `LEAF_2014_EU_QSD-357-101.img` | 7,969,177,600 |
| `ENV200_2016_EU_QSD-390-100.img` | 7,969,177,600 |
| `ENV200_2019_25920-6WX1C-EUR.img` | 16,039,018,496 |
| `EU_MAPDATA_13-14.7z` | 6,088,466,708 |
| `EU_MAPDATA_14-15.7z` | 6,273,414,589 |
| `EU_MAPDATA_16-17.7z` | 6,635,659,459 |

Local archive: `archive/images/`, with `SHA256SUMS`.

## Method

```bash
cd archive/images
sha256sum -c SHA256SUMS

# SD images (strict and with the dump-artifact filter)
python3 tools/cardcheck.py --image archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img
python3 tools/cardcheck.py --image archive/images/LEAF_2014_EU_QSD-357-101.img \
    --ignore-dump-artifacts
python3 tools/cardcheck.py --image archive/images/ENV200_2016_EU_QSD-390-100.img \
    --ignore-dump-artifacts
python3 tools/cardcheck.py --image archive/images/ENV200_2019_25920-6WX1C-EUR.img \
    --ignore-dump-artifacts

# Map-only archives: extract one at a time, then validate
7z x -y -o/tmp/eu1314 archive/images/EU_MAPDATA_13-14.7z
python3 tools/cardcheck.py --root /tmp/eu1314 --partial --ignore-dump-artifacts
# repeat for 14-15 and 16-17
```

## Observations

### Hashes

All seven files match `SHA256SUMS`: seven `OK` lines, no mismatch.

### L1 on SD images

| Image | Result | Notes |
| --- | --- | --- |
| 2011 EU | PASS | 480 files / 39 dirs / 5,173,965,667 B; 194/194 `.cmp`; DRSTR 40/324; MMAIN 11/11 |
| 2014 EU | PASS | 504 files / 58 dirs; `TFTBL001` warning |
| 2016 e-NV200 | PASS with `--ignore-dump-artifacts` | strict run fails on `._reception.dat` / `._OIXXEVNI.001`; 505 files / 58 dirs after filtering; `TFTBL001` warning |
| 2019 e-NV200 | FAIL | `CLA-NAVI06-01`, `ZENRIN`, `X08-03-00`, 53 tiles, no `VER_INFO`, macOS artefacts; this is the QY8x family, not ZE0 |

The 2016 strict failure is caused by AppleDouble files:

```
DRSTR size 1606224 != actual 1610320   (OPNG)
DRSTR size 208 != actual 4304          (TMC)
TMC: '._reception.dat' is on card but not in DRSTR
```

With `--ignore-dump-artifacts`, the same image passes all structural checks.

### L1 on map-only archives

| Archive | Result | Notes |
| --- | --- | --- |
| 2013-14 | PASS (partial) | 504 files / 57 dirs; `TFTBL001`; DRSTR lists `VER_INFO` but the folder is absent |
| 2014-15 | PASS (partial) | 503 files / 57 dirs; same stale `VER_INFO` |
| 2016-17 | PASS (partial) | 504 files / 57 dirs; same stale `VER_INFO` |

The archives are map trees, not full cards. `--partial` allows the missing
`VER_INFO` directory and reports it as a warning.

### L2 on map-only archives (informational)

`l2check.py --no-golden` passes `DRSTR`, 194/194 `.cmp` round-trips, the tile
semantic digests and the one-vertex tile mutation on all three archives, but:

- `B30R048R.DAT` fails the byte-identical tile rebuild at `0x807`/`0x808` on
  the 2013–2016 archives;
- the `POINT032.DAT` page `0x4200` POI mutation is a 2011-specific fixture and
  fails on the other years.

These are L2 portability limits, not L1 failures.

## Interpretation

- **FACT:** the complete public mirror set is archived and SHA-256 verified.
- **FACT:** L1 passes on the 2011, 2014 and 2016 ZE0-era SD images; 2016 needs
  `--ignore-dump-artifacts` because of AppleDouble files.
- **FACT:** L1 passes on the 2013-14, 2014-15 and 2016-17 map trees with
  `--partial --ignore-dump-artifacts`.
- **FACT:** the 2019 image is a different generation and correctly fails ZE0
  checks.
- **OBSERVED:** `DRSTR` in the map archives carries a stale `VER_INFO` node.
- **OBSERVED:** L2's dense-tile round-trip and POI-mutation fixture are not yet
  portable across years.

## Conclusion

The archive is complete and verified. L1 is a cross-year structural validator
for ZE0-era cards. L2 remains validated on the 2011 reference and needs
per-year fixtures before it can be called cross-year.

Do not confuse the two "other architectures": 2013–2016 is a different vehicle
generation (AZE0) but the **same navigation format family**
(`CLA-NAVI05-01` / `X08-02-00`); the L2 `B30R048R` difference is a writer/header
variant. Only the 2019 e-NV200 image is a genuinely different navigation engine
(`CLA-NAVI06-01` / ZENRIN / QY8x).

## Follow-ups

- [ ] Investigate the `B30R048R` 2013–2016 rebuild difference at `0x807`.
- [ ] Parameterise the L2 POI mutation fixture per year.
- [ ] Keep `--ignore-dump-artifacts` explicit; do not hide dump artefacts by
      default.
- [ ] Do not add a 2019 ZE0 golden profile; it is a different engine.
