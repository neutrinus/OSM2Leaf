# Build profiles

A build profile says **what** goes into a ZE0 map card image, not how it is
encoded. Profiles are whole-tile only (decision in
[`docs/research/build-profiles.md`](../docs/research/build-profiles.md)): a
profile selects complete `BxxRyyR` tiles, and the border buffer extends the
tile search and the routing graph but never clips a tile.

| File | Shape | Tiles |
| --- | --- | --- |
| `schema.json` | JSON Schema draft 2020-12 for version 2 | — |
| `dolnoslaskie-detail.json` | version 1 (legacy) | 1 (`B48R058R`) |
| `dolnoslaskie-test.json` | version 1 (legacy) | 1 (`B48R058R`) |
| `poland-full.json` | version 1 (legacy) | 4 |
| `europe-motorways.json` | version 1 (legacy) | 56 |

`dolnoslaskie-test.toml` is a separate build profile for the pinned
`tools/ze0-viewer/vendor/osm2clarion` slice; it is not read by these tools.

## Version 2 (canonical)

```json
{
  "version": 2,
  "name": "dolnoslaskie-detail",
  "description": "Full detail for Dolnośląskie, delivered as the full containing tiles.",
  "sources": ["poland-latest.osm.pbf"],
  "region": {"bbox": [14.0, 49.9, 17.9, 51.9], "countries": ["PL"]},
  "coverage": {
    "default": "detail",
    "tiers": [
      {
        "id": "detail",
        "roads": "all",
        "addresses": true,
        "pois": "all",
        "admin_boundaries": true
      }
    ]
  },
  "tiles": {"mode": "whole-tiles", "include": [], "exclude": []},
  "border_buffer_deg": 0.45,
  "attribution": {
    "text": "Map data © OpenStreetMap contributors, ODbL 1.0",
    "location": "manifest",
    "odbl_version": "1.0"
  },
  "limits": {"max_tiles": 63},
  "outputs": {"image_name": "dolnoslaskie-detail.img", "manifest": true}
}
```

Fields, in schema order:

| Field | Meaning |
| --- | --- |
| `version` | `2` for this shape. Version 1 is accepted through a legacy adapter only. |
| `name` | Stable slug; the default output stem. |
| `description` | Purpose. Say that whole tiles extend past the region. |
| `sources` | Extract names, provenance only; the validator never opens them. |
| `region.bbox` | `[west, south, east, north]` in WGS84 degrees. |
| `region.countries` | ISO 3166-1 alpha-2 provenance. |
| `coverage.default` | Tier id used when no tier region matches a tile. |
| `coverage.tiers` | Spatial coverage tiers. Tried in order, first match wins. `roads` is `all`, `core`, `none` or an OSM class list; `pois` is `all`, `none` or a category list. A tier may carry its own `region`, which is how one profile mixes "Poland at full detail" with "Europe at motorway/trunk only". |
| `tiles.mode` | Always `whole-tiles`. There is no sub-tile clipping. |
| `tiles.include` | Explicit tile ids. Non-empty means exactly these tiles (minus `exclude`). |
| `tiles.exclude` | Tiles removed after resolution, for experiments. |
| `border_buffer_deg` | Buffer in latitude degrees (1° lat = 111.32 km). The tile search pads longitude by `buffer / cos(mid-latitude)` so the buffer is roughly isotropic on the ground. |
| `attribution` | ODbL text plus where it ships (`card-file`, `download`, `manifest`). The legal choice is still open. |
| `limits` | `max_image_bytes`, `max_tiles`, `min_free_bytes`; enforced by the tools. |
| `outputs` | Image name, manifest and verify flags, card label. |

## Version 1 (legacy)

The four `*.json` profiles shipped on 2026-11-05 use
`name`/`description`/`sources`/`include`/`detail`/`routing`:

- `include.countries` and `include.bbox` become `region`;
  `include.bbox: null` is replaced by a coarse national bbox from
  `COUNTRY_BBOX` in `tools/profile_validate.py` (currently `PL` only; an
  unknown country is an error, never a guess);
- `include.border_buffer_km` becomes `border_buffer_deg` (`km / 111.32`);
- `detail` becomes the default tier, and `detail.extra_network` becomes a
  second `corridor` tier;
- `attribution`, `limits` and `outputs` are filled with documented defaults;
  `routing` is kept as metadata only;
- `include.tiles.mode: "whole"` is accepted, any other mode is an error.

Every normalization step is reported as a warning (`W002`–`W005`). New
profiles must use version 2; `--strict` rejects the legacy shape.

## Validate and estimate

```bash
# Validate one profile or all of them
python3 tools/profile_validate.py profiles/dolnoslaskie-detail.json
python3 tools/profile_validate.py profiles/*.json

# Machine-readable, and warnings-as-errors
python3 tools/profile_validate.py profiles/poland-full.json --json
python3 tools/profile_validate.py profiles/poland-full.json --strict

# Size breakdown, no writing
python3 tools/build.py --profile profiles/dolnoslaskie-detail.json --dry-run
```

Exit codes: `profile_validate.py` 0 valid, 1 validation errors, 2 usage/I/O.
`build.py` 0 dry run, 1 invalid profile or over its own limits, 2 usage,
**3 writer not implemented** (any invocation without `--dry-run`).

Both tools have synthetic self-tests and are picked up by
`python3 tools/selftest.py`:

```bash
python3 tools/profile_validate.py --selftest
python3 tools/build.py --selftest
```

## Resolved tile counts

The tile geometry comes from `tools/mesh_grid.py`
(`lat_min = int(B,16) * 2/3`, `lon_max = 108 - int(R,16)`, span 8 units).
The EU 2011 map addresses a **9 × 7 lattice** of `BxxRyyR` cells (rows
`B28`–`B68`, columns `R048`–`R078`, 63 cells), but only **45** cells exist as
files; the rest are sea or empty and the exact subset is vendor data, so a
resolved count of cells is an **upper bound**. `W009` flags selections wider
than 45 cells.

| Profile | Region | Buffer | Tiles | Tier split |
| --- | --- | --- | --: | --- |
| `dolnoslaskie-detail` | 14.0–17.9 E, 49.9–51.9 N | 50 km (0.45°) | 1 | `detail` 1 (`B48R058R`) |
| `dolnoslaskie-test` | same, explicit include | 10 km (0.09°) | 1 | `detail` 1 (`B48R058R`) |
| `poland-full` | PL extent 14.12–24.15 E, 49.0–54.84 N | 50 km (0.45°) | 4 | `detail` 4 (`B48R050R`, `B48R058R`, `B50R050R`, `B50R058R`) |
| `europe-motorways` | PL extent + corridor `[-12, 34, 40, 72]` | 100 km (0.90°) | 56 | `detail` 4, `corridor` 52 |

Notes:

- Dolnośląskie fits **one** tile (`B48R058R` = 48.00–53.33 N, 12–20 E), not the
  "2–3 tiles" guessed in `docs/research/build-profiles.md`. A 50 km buffer does
  not change that.
- Whole-tile delivery dominates the estimate for small regions: the
  `dolnoslaskie-detail` tile also contains the rest of south-west Poland, so the
  build carries roughly two Dolnośląskie-sized road networks.
- `europe-motorways` selects 56 of the 63 addressable cells (all but the
  `B28` row: the corridor starts at 34° N, north of the `B28` tile), which is
  11 more cells than the 45 shipped tiles; those extra cells are sea/empty and
  the size estimate is an upper bound.

## Size budgets used by `build.py`

| Row | Bytes per tile | Provenance |
| --- | --: | --- |
| roads, `all` | 41.0 MB | `docs/research/osm-pipeline.md`: Poland all drivable ≈ 165 MB zlib over the 4 `poland-full` tiles |
| roads, `core` | 1.0 MB | `docs/research/build-profiles.md`: Dolnośląskie motorway–secondary |
| roads, class list | 41.0 MB / 1.0 MB | 41.0 if the list touches `residential`/`service`/`track`…, else 1.0 |
| refer (names + address index) | 2.0 MB dense / 0.5 MB sparse | **PLACEHOLDER**, no measurement |
| poi | 1.5 MB `all` / 0.75 MB subset | **PLACEHOLDER**, no measurement |
| admin boundaries | 0.1 MB | **PLACEHOLDER**, no measurement |

The printout is labelled `ESTIMATE` and never claims to be a measurement. The
card has about 2.35 GB free (`docs/research/build-profiles.md`); the dense
factory tile `B48R060R` is 436.0 MB (`docs/format/map-tiles.md`) and is shown
only as a ceiling.
