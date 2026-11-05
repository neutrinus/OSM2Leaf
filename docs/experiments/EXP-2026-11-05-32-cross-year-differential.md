# EXP-2026-11-05-32: Cross-year differential (2011 vs 2014 vs 2016)

- **Status:** done
- **Date:** 2026-11-05
- **Sample:** ZE0-era SD images and extracted trees
  - `LEAF_2011-2012_QSD-309-101_navi158_eu.img`
    `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
  - `LEAF_2014_EU_QSD-357-101.img`
    `4a8a21f477e9fc511f94406976b8d67037842f9c043f49ab24e1adc82d6da89b`
  - `ENV200_2016_EU_QSD-390-100.img`
    `f53d55f159fd4232caa0b100b9b12e3910c8fe3849201871a71ee38ac19007fb`
- **Claims:** C-121, C-126, C-500, C-501, C-504
- **Supersedes:** none
- **Superseded by:** none

## Question

Which map and card fields change across the 2011, 2014 and 2016 ZE0-era
images, and which of them are candidates for map-code/activation or compiler
support work?

## Hypothesis

The navigation format family stays stable, while map-set identity, tile content,
section-4 place data and `REFER002` coverage grow with each revision.

## Inputs

| Item | Value |
| --- | --- |
| Extracted roots | `leafre-work/root`, `leafre-work/_root2014`, `leafre-work/_root2016` |
| Validators | `tools/cardcheck.py`, `tools/l2check.py`, `tools/ze0-viewer` |
| Tile analysed | `MAPAL001/B30R048R.DAT` |

## Method

```bash
python3 tools/cardcheck.py --root leafre-work/root
python3 tools/cardcheck.py --root leafre-work/_root2014
python3 tools/cardcheck.py --root leafre-work/_root2016 --ignore-dump-artifacts

python3 tools/l2check.py --root leafre-work/root
python3 tools/l2check.py --root leafre-work/_root2014 --no-golden --ignore-dump-artifacts
python3 tools/l2check.py --root leafre-work/_root2016 --no-golden --ignore-dump-artifacts
```

Additional comparisons used the `HDD_INFO.TXT` files, `DRSTR001.DAT` trees,
tile feature counts, section-4 decoders and `REFER001`/`REFER002` inventories.

## Observations

### L1/census

| Metric | 2011 | 2014 | 2016 |
| --- | ---: | ---: | ---: |
| files | 480 | 504 | 505 |
| dirs | 39 | 58 | 58 |
| bytes | 5,173,965,667 | 6,821,761,753 | 7,180,933,678 |
| `.cmp`/`.ind` pairs | 194 | 194 | 194 |
| REFER logical bytes | 2,390,610,176 | 3,113,173,760 | 3,290,088,192 |
| DRSTR nodes | 40 | 59 | 59 |
| DRSTR entries | 324 | 367 | 368 |
| MAPAL files | 46 | 46 | 46 |
| MMAIN rows | 11 | 11 | 11 |

### `HDD_INFO.TXT`

| Line | 2011 | 2014 | 2016 |
| --- | --- | --- | --- |
| 1 | `QSD-302-100` | `QSD-302-100` | `QSD-302-100` |
| 2 | `QSD-309-101` | `QSD-357-101` | `QSD-390-100` |
| 3 | `02-110100-00` | `02-140300-00` | `02-160500-00` |
| 4 | `SDC08-EVEUR` | `SDC08-EVEUR` | `SDC08-EVEUR` |
| 5 | `11-05` | `14-06` | `16-02` |
| 6 | `470323501005` | `470516001006` | `470677200002` |

### Section 4 in `B30R048R.DAT`

| Year | records | names |
| --- | ---: | ---: |
| 2011 | 20 | 68 |
| 2014 | 24 | 126 |
| 2016 | 24 | 129 |

The 2016 name count includes a few suspicious short tokens from the current
splitter and should be rechecked with a stricter decoder.

### `REFER002`

- 2011: 15 `POINT*.DAT`, no `ICODE001.DAT`, `COORD001` has 15 region records.
- 2014: 28 `POINT*.DAT`, `ICODE001.DAT` 4,528,640 B, 28 region records.
- 2016: 29 `POINT*.DAT`, `ICODE001.DAT` 5,029,632 B, 29 region records.

## Interpretation

- **FACT:** L1 passes on all three ZE0-era images; 2016 needs
  `--ignore-dump-artifacts`.
- **FACT:** all three images have the same 46 `MAPAL001` file names, 194
  `REFER001` pairs, and 11 `MMAIN` rows.
- **OBSERVED:** `HDD_INFO` line 1 is constant, line 2 tracks the map set and
  FAT label, and lines 3/5/6 track build, year-month and part number.
- **OBSERVED:** section-4 place-name data grows across revisions while the
  country code remains 300 in the sampled records.
- **OBSERVED:** `REFER002`/`ICODE001` coverage expands from 2013 onward.
- **HYPOTHESIS:** lines 2, 3, 5 and 6 are candidate map-code fields, but this
  is not proven without hardware or the firmware parser.

## Conclusion

The ZE0-era format family is stable across 2011–2016. The main revision-driven
differences are map identity, tile content, section-4 place data and
`REFER002` coverage. These differences are useful inputs for compiler and
map-code work, but they do not by themselves prove activation behaviour.

## Follow-ups

- [ ] Map the `B30R048R` layout difference at `0x807`/`0x808`.
- [ ] Run the spare-card `HDD_INFO` variant matrix.
- [ ] Decode section-4 binary fields and build a ZE0 encoder.
- [ ] Compare `REFER002`/`ICODE001` schemas across years.
- [ ] Parameterise the cross-year POI mutation fixture.
- [ ] Decide `TFTBL001` and speech-language packaging scope.
