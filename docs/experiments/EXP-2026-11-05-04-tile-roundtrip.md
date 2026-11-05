# EXP-2026-11-05-04: ZE0 tile round-trip and viewer

- **Status:** done for clean tiles; dense tiles open
- **Date:** 2026-11-05
- **Sample:** EU 2011 `MAPAL001` tiles
- **Claims:** C-170…C-175
- **Supersedes:** none
- **Superseded by:** none

## Question

Can we decode a ZE0 `MAPAL001` tile to a neutral geometry model, rebuild it,
and get a byte-identical file?

## Hypothesis

The tile container and its zlib records are understood well enough for a
byte-identical rebuild on tiles without section 4.

## Inputs

| File | SHA-256 |
| --- | --- |
| `B28R070R.DAT` | `0e4df38b659e99129c1e55f1ad16219d73e713677edd4ee3756b8ce7e74b2ddb` |
| `B30R060R.DAT` | `8ca92bd5601e33bd97ab3bbab62b4394448cbe0e2adf31ba6046eebb52b8b62d` |
| `B58R070R.DAT` | `f8aae7e4d0df35e450377255f536a97324ac72b93cb9fd1c005a9605dd5477d7` |
| `B30R048R.DAT` | `0916101547246d6c6ed240aeb4724b4cd6e826c97a6b782e2b649fbe09a5eb28` |
| `LEV3456R.DAT` | `08a584feacf049cc39260ff29f742c3dcf1b53059cb98bd3e9798e7ab819df35` |

Tools: `tools/ze0-viewer/` (pinned `osm2clarion` + `ze0-tools.patch`).

## Method

```bash
cd tools/ze0-viewer
./setup.sh

python3 harness.py verify /path/to/B58R070R.DAT
python3 harness.py verify /path/to/B28R070R.DAT
python3 harness.py verify /path/to/B30R060R.DAT
```

## Observations

```
B58R070R: byte-identical rebuild OK (110592 bytes)
  records ok 459 bad 0 | background rebuild ok 459 | graph 0 | roundtrip OK
B28R070R: byte-identical rebuild OK (1083392 bytes)
  records ok 7937 bad 0 | background rebuild ok 7103 | graph ok 455 | roundtrip OK
B30R060R: byte-identical rebuild OK (1294336 bytes)
  records ok 8539 bad 0 | background rebuild ok 8465 | graph ok 37 | roundtrip OK
```

`LEV3456R.DAT` rebuilds byte-identically (76 MB), but 113 level 3–5 records
fail because coarse tails are not modelled.

`B30R048R.DAT` does **not** round-trip: 1,358,592 → 3,371,008 bytes, first diff
`0x807`. It carries section 4 (type `0x93`) and a `0x2146` directory layout.

## Interpretation

- **FACT:** the container and levels 1–2 of clean tiles are understood well
  enough for a byte-identical rebuild.
- **FACT:** ZE0 uses zlib `78 9c`; background kind is `0x00fa` at both levels;
  the even/odd record pair separates road-shape from background.
- **FACT:** dense tiles with section 4 are not yet modelled.
- **FACT:** `read_tile` is not streaming; a 73 MB tile peaked at ~20 GB RSS.
- **OBSERVED:** no layer-11 coastline; the coast is the sea-polygon edge.

## Conclusion

The tile layer is no longer a black box for clean tiles. The viewer can render
recognizable coastlines/land and a one-vertex mutation changes exactly one
vertex (~68 m) while still round-tripping.

## Follow-ups

- [ ] Decode section 4 / directory `0x2146` (`B30R048R`).
- [ ] Add a streaming writer for large tiles.
- [ ] Decode the drawn road-shape records (even pair) and render roads.
- [ ] Model `LEV3456R` level 6 coarse tails.
- [ ] Use the harness as the Gate 3 regression test.
