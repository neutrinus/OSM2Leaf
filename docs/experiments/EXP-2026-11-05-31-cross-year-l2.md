# EXP-2026-11-05-31: cross-year L2 for the 2014 and 2016 cards

- **Status:** done
- **Date:** 2026-11-05
- **Sample:** `LEAF_2014_EU_QSD-357-101.img`
  (`4a8a21f477e9fc511f94406976b8d67037842f9c043f49ab24e1adc82d6da89b`)
  and `ENV200_2016_EU_QSD-390-100.img`
  (`f53d55f159fd4232caa0b100b9b12e3910c8fe3849201871a71ee38ac19007fb`)
- **Claims:** C-504
- **Supersedes:** the cross-year L2 limitation in C-503
- **Superseded by:** none

## Question

Can L2 pass on the 2014 and 2016 ZE0-era cards, not just the 2011 reference?

## Hypothesis

Yes, after two fixes:

1. an unchanged factory tile may be kept verbatim when the layout writer
   would compact a shared/non-monotonic block layout;
2. the REFER001 mutation fixture must be found per year, and the `DRSTR`
   lookup must not confuse `REFER001/POINT001.DAT` with
   `REFER002/POINT001.DAT`.

## Method

```bash
# Full map trees from the raw images (temp dirs, removed afterwards)
7z x -y -o/home/marek/projekty/leafre-work/_root2014 \
    archive/images/LEAF_2014_EU_QSD-357-101.img
7z x -y -o/home/marek/projekty/leafre-work/_root2016 \
    archive/images/ENV200_2016_EU_QSD-390-100.img

python3 tools/l2check.py --root /home/marek/projekty/leafre-work/_root2014 \
    --no-golden --ignore-dump-artifacts
python3 tools/l2check.py --root /home/marek/projekty/leafre-work/_root2016 \
    --no-golden --ignore-dump-artifacts

# The unchanged dense tile now keeps its factory layout.
python3 tools/ze0-viewer/harness.py roundtrip \
    /home/marek/projekty/leafre-work/_root2014/MAPAL001/B30R048R.DAT
```

## Observations

### 2014

```
census          files=504 dirs=58 bytes=6821761753
drstr_roundtrip size=14104
cmp_roundtrip   pairs=194 ok=194
tile_roundtrip  tiles=5 preserved=1
                WARN B30R048R.DAT: unchanged tile uses preserved layout
tile_semantic   B28R070R=7986 B30R060R=15051 B58R070R=2564 B30R048R=18089
tile_mutation   removed=1 added=1 changed_vertices=1
refer_mutation  POINT001.DAT page=0x39700
                +(376)-809190 -> +(376)-80919X
                validate=PASS
RESULT: PASS
```

### 2016

```
census          files=505 dirs=58 bytes=7180933678
drstr_roundtrip size=14136
cmp_roundtrip   pairs=194 ok=194
tile_roundtrip  tiles=5 preserved=1
                WARN B30R048R.DAT: unchanged tile uses preserved layout
tile_semantic   B28R070R=7986 B30R060R=15114 B58R070R=3068 B30R048R=17326
tile_mutation   removed=1 added=1 changed_vertices=1
refer_mutation  POINT001.DAT page=0x3d700
                +(376)-809190 -> +(376)-80919X
                validate=PASS
RESULT: PASS
```

The 2016 tree was validated with `--ignore-dump-artifacts` because the image
contains AppleDouble files.

### Unchanged dense tile

```
B30R048R.DAT: byte-identical rebuild OK (1526528 bytes) (preserved layout)
```

## Interpretation

- **FACT:** L2 passes on full 2014 and 2016 roots with `--no-golden
  --ignore-dump-artifacts`.
- **FACT:** `B30R048R.DAT` is byte-identical via the preserved-layout fallback;
  the layout writer still compacts this tile if it is actually edited.
- **FACT:** the REFER mutation fixture is now discovered per year; the 2011
  fixture remains `POINT032.DAT` page `0x4200`.
- **FACT:** `validate_mutation.py --drstr-dir REFER001` removes the
  `REFER001/REFER002` name collision for `POINT001.DAT`.
- **OBSERVED:** the 2016 image needs the dump-artifact filter; that is an image
  artefact, not a map-format difference.

## Conclusion

Cross-year L2 is fixed for factory cards. The remaining limitation is editing
the 2013–2016 dense `B30R048R` layout: the writer can read it and preserve it,
but a changed dense tile may need a layout-aware writer. The 2011 reference
still exercises the real writer (`preserved=0`).

## Follow-ups

- [ ] Add per-year golden profiles if we want digest comparison beyond the
      factory data (optional; `--no-golden` is enough for structural checks).
- [ ] If 2013–2016 dense-tile editing becomes a target, add a layout-aware
      writer for shared/non-monotonic block layouts.
- [ ] Keep 2019 out of scope: it is the different QY8x engine.
