# EXP-2026-11-05-36: Profile schema, validator and dry-run estimator

- **Status:** done
- **Date:** 2026-11-05
- **Sample:** no vendor data. Text inputs only:
  `profiles/schema.json` `3045450d…b53b98`,
  `profiles/dolnoslaskie-detail.json` `310fcf44…c916`,
  `profiles/dolnoslaskie-test.json` `386ada53…a36e`,
  `profiles/poland-full.json` `ee913786…3dc4`,
  `profiles/europe-motorways.json` `4ec0ad0d…5997`
- **Claims:** proposed C-538–C-541 (claim text in *Conclusion*; the ledger is
  not edited by this experiment)
- **Supersedes:** none
- **Superseded by:** none

## Question

Can the 2026-11-05 build profiles be validated mechanically, and how many
whole `BxxRyyR` tiles does each one actually select once the verified grid math
and the border buffer are applied?

## Hypothesis

`profiles/*.json` were written from estimates, not from the decoded grid.
Applying `lat_min = int(B,16) * 2/3`, `lon_max = 108 - int(R,16)`, span 8 units
(1 lat unit = 2/3°, 1 lon unit = 1°) should give an exact tile count, and the
"Dolnośląskie falls into 2–3 tiles" statement in
`docs/research/build-profiles.md` may not survive that math.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none (no vendor data used) |
| SHA-256 | see header; `sha256sum profiles/schema.json profiles/*.json` |
| Offset(s) | not applicable |
| Tool version | `python3 tools/profile_validate.py` / `tools/build.py`, Python 3.10+ stdlib only |

## Method

```bash
python3 -m py_compile tools/profile_validate.py tools/build.py
python3 tools/profile_validate.py --selftest
python3 tools/build.py --selftest

python3 tools/profile_validate.py \
  profiles/dolnoslaskie-detail.json \
  profiles/dolnoslaskie-test.json \
  profiles/poland-full.json \
  profiles/europe-motorways.json

python3 tools/build.py --profile profiles/dolnoslaskie-detail.json --dry-run
```

Tile geometry is imported from `tools/mesh_grid.py` (`tile_box`), not copied.
The buffer is applied in latitude degrees and padded in longitude by
`buffer / cos(mid-latitude)`; the legacy `border_buffer_km` is converted with
111.32 km/deg. The selectable space is the addressable **9 × 7** lattice
(`B28`–`B68` rows × `R048`–`R078` columns, 63 cells); the factory image ships
**45** of those cells, and the exact subset is vendor data that is not in this
repository.

## Observations

`python3 tools/profile_validate.py --selftest`:

```
checks: 35, failures: 0
selftest: OK
```

`python3 tools/build.py --selftest`:

```
checks: 23, failures: 0
selftest: OK
```

Optional cross-check (not a dependency of the tools): the four legacy profiles,
normalized to version 2, produce **zero** errors under the third-party
`jsonschema` 4.19.2 `Draft202012Validator` with `profiles/schema.json`. So the
schema itself is a valid 2020-12 schema and the built-in subset engine agrees
on the shipped profiles.

`python3 tools/profile_validate.py profiles/*.json` (one run per file), exit 0
for all four:

| Profile | Shape | Region | Buffer | Tiles | Tier split |
| --- | --- | --- | --- | --: | --- |
| `dolnoslaskie-detail` | v1 → v2 | 14.0–17.9 E, 49.9–51.9 N | 0.45° (50 km) | 1 | `detail` 1 |
| `dolnoslaskie-test` | v1 → v2 | same bbox, `include: [B48R058R]` | 0.09° (10 km) | 1 | `detail` 1 |
| `poland-full` | v1 → v2 | 14.12–24.15 E, 49.00–54.84 N | 0.45° (50 km) | 4 | `detail` 4 |
| `europe-motorways` | v1 → v2 | PL bbox + corridor `[-12, 34, 40, 72]` | 0.90° (100 km) | 56 | `detail` 4, `corridor` 52 |

Resolved ids:

- `dolnoslaskie-detail`, `dolnoslaskie-test`: `B48R058R`.
- `poland-full`: `B48R050R`, `B48R058R`, `B50R050R`, `B50R058R`.
- `europe-motorways`: every `B30`–`B68` row × every `R048`–`R078` column
  (8 rows × 7 columns = 56). The `B28` row (26.67–32.00 N) is excluded because
  the corridor starts at 34° N minus the 0.90° buffer.

`python3 tools/build.py --profile profiles/dolnoslaskie-detail.json --dry-run`
(exit 0):

```
profile   profiles/dolnoslaskie-detail.json
shape     version 1 (legacy, normalized)
name      dolnoslaskie-detail
region    W   14.00  S  49.90  E   17.90  N  51.90
buffer    0.45 deg (50 km)
tiles     1: B48R058R
warning   W002 legacy version-1 profile (include/detail/routing); normalized to version 2
warning   W005 legacy routing block is metadata only; no routing graph is built yet
warning   W003 legacy profile has no attribution block; defaulted to manifest + ODbL text
warning   W004 legacy profile has no outputs block; defaulted to <name>.img with manifest

ESTIMATE (tile count x per-tile budget; NOT a measurement)
budget     roads documented (Poland 165 MB / 4 tiles; DS core 1 MB); refer/poi/admin PLACEHOLDER
tier         tiles     roads    refer     poi   admin     total  basis
detail           1     41.00     2.00    1.50    0.10     44.60  refer placeholder, poi placeholder, admin placeholder
TOTAL            1     41.00     2.00    1.50    0.10     44.60
card free  2350 MB (docs/research/build-profiles.md); this build would use 1.9 %
reference  factory dense tile B48R060R is 436.0 MB (docs/format/map-tiles.md) -- ceiling, not a target
sources    roads: Poland all-drivable ~165 MB zlib / 4 tiles, core 1.0 MB; refer/poi/admin: PLACEHOLDER (no measurement yet)
output     dolnoslaskie-detail.img (manifest=True, verify=False)
```

`python3 tools/build.py --profile profiles/poland-full.json --dry-run`:
4 tiles, roads 164.0 MB, refer 8.0 MB, poi 6.0 MB, admin 0.4 MB, total
**178.4 MB** (7.6 % of the 2.35 GB free space).

`python3 tools/build.py --profile profiles/europe-motorways.json --dry-run`:
56 tiles, `detail` 4 (roads 164.0 MB, refer 8.0 MB, poi 3.0 MB, admin 0.4 MB)
plus `corridor` 52 (roads 52.0 MB, refer 26.0 MB), total **253.4 MB**
(10.8 % of free space); also emits `W009` because 56 > 45 shipped tiles.

`python3 tools/selftest.py` after the change: `tool:profile_validate PASS`,
`tool:build PASS`. One unrelated suite failed: `tool:cerom FAIL` with
`struct.error: pack_into expected 7 items for packing (got 8)` inside
`tools/cerom.py:1831` (`build_synthetic`); that file is not part of this
experiment and was not modified.

## Interpretation

- **FACT:** the three shipped profiles validate as version 1, are normalized to
  version 2 with only warnings (W002–W005), and resolve to 1 / 4 / 56 whole
  tiles respectively.
- **FACT:** `lat_min = 48.0` and `lon_max = 20.0` for `B48R058R`; the whole
  Dolnośląskie bbox (14.0–17.9 E, 49.9–51.9 N) lies inside it, and a 50 km
  buffer (0.45° lat, 0.71° lon at 50.9 N) does not touch a second tile. The
  "2–3 tiles" line in `docs/research/build-profiles.md` is therefore wrong for
  the bbox used by the profiles; the tile count is 1.
- **OBSERVED:** `europe-motorways` selects 56 addressable cells, 11 more than
  the 45 tiles in the factory image. The 18 missing cells of the 9 × 7 lattice
  are sea/empty, so lattice-based tile counts are an **upper bound** until the
  shipped subset is known from vendor data.
- **OBSERVED:** the dry-run total for `dolnoslaskie-detail` (44.6 MB) is above
  the 20–40 MB guess in `docs/research/build-profiles.md`, because whole-tile
  delivery makes the profile carry the rest of south-west Poland inside
  `B48R058R`, not just Dolnośląskie. The `refer`/`poi`/`admin` rows are
  placeholders; only the roads row is anchored to a documented measurement.
- **HYPOTHESIS:** the 41 MB/tile all-roads budget (165 MB Poland / 4 tiles) will
  stay within ±30 % once the first real tile is encoded; the placeholder rows
  will move more.
- **UNKNOWN:** the exact set of 45 shipped tiles; whether refer (names plus
  address index) really costs ~2 MB per dense tile; where ODbL attribution
  ships on a FAT32 card.

## Conclusion

Added, without touching vendor data:

- `profiles/schema.json` — JSON Schema draft 2020-12 for version-2 profiles
  (region bbox, coverage tiers, `whole-tiles`, border buffer in degrees,
  attribution, limits, outputs).
- `tools/profile_validate.py` — stdlib-only schema-subset validator, legacy
  adapter, bbox/buffer/tier/tile checks, tile resolution via `mesh_grid`,
  `--json`, `--strict`, exit 0/1/2.
- `tools/build.py` — `--profile … --dry-run` estimator, `--selftest`, exit 3
  without `--dry-run`.
- `profiles/README.md` — shape, commands, resolved tile counts, budget table.

Proposed claim text for `docs/research/claims.md` (next free IDs, not added by
this experiment):

- **C-538 (VERIFIED):** `tools/profile_validate.py` accepts all four shipped
  version-1 profiles through the legacy adapter and resolves 1 / 1 / 4 / 56
  whole tiles for `dolnoslaskie-detail`, `dolnoslaskie-test`, `poland-full`,
  `europe-motorways`; evidence `python3 tools/profile_validate.py profiles/*.json`,
  EXP-2026-11-05-36.
- **C-539 (VERIFIED):** The whole Dolnośląskie bbox (14.0–17.9 E, 49.9–51.9 N)
  plus a 50 km buffer lies inside the single tile `B48R058R` (48.00–53.33 N,
  12–20 E); the "2–3 tiles" estimate in `docs/research/build-profiles.md` is
  superseded for that bbox. Evidence EXP-2026-11-05-36.
- **C-540 (OBSERVED):** The EU 2011 tile space is a 9 × 7 addressable lattice
  (rows `B28`–`B68`, columns `R048`–`R078`, 63 cells) of which 45 cells exist;
  lattice-derived tile counts are upper bounds because the 18 sea/empty cells
  are not enumerable without vendor data. Evidence `docs/format/map-tiles.md`,
  EXP-2026-11-05-36; the shipped 45-name subset is still vendor data.
- **C-541 (OBSERVED):** `tools/build.py --dry-run` estimates 44.6 MB for
  `dolnoslaskie-detail`, 178.4 MB for `poland-full` and 253.4 MB for
  `europe-motorways` using documented road budgets and placeholder
  refer/POI/admin budgets; the rows are labelled ESTIMATE. Evidence
  EXP-2026-11-05-36.

Open: nothing in this experiment was validated on hardware or against a real
encoder; `TODO.md` items "Add a schema validator and `tools/build.py --profile`"
and "Print a size breakdown before writing an image" can be ticked by the
owner.

## Follow-ups

- [ ] Migrate `profiles/*.json` to version 2 and drop the legacy adapter path
      from the shipped files (keep the adapter for old archives).
- [ ] Populate the 45-tile shipped subset once the image is available, and turn
      `SHIPPED_TILE_COUNT` into an exact list.
- [ ] Replace the `refer`/`poi`/`admin` placeholders with measured densities
      after the first encoded tile.
- [ ] Decide `attribution.location` (`card-file` vs `download` vs `manifest`)
      and test that an extra card file keeps the `DRSTR001.DAT` manifest valid.
- [ ] Implement the writer behind `tools/build.py` (currently exit 3).
- [ ] Reconcile the "2–3 tiles" sentence in `docs/research/build-profiles.md`
      with C-539.
- [ ] Investigate the unrelated `tools/cerom.py --selftest` `struct.pack_into`
      failure before the next full `tools/selftest.py` gate.
