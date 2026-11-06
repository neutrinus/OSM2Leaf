# Build profiles: letting the user choose maps

Card budget is not the constraint. The EU 2011 image leaves about **2.35 GB**
free, and the measured OSM estimates are small:

| Dataset | Raw | zlib | Notes |
| --- | --: | --: | --- |
| Dolnośląskie, all drivable roads | 18.8 MB | 13.7 MB | 362,586 ways / 94,123 km |
| Dolnośląskie, motorway–secondary only | — | 1.0 MB | core network |
| Poland, all drivable roads (extrapolated) | ~165 MB | — | from the DS sample |
| Poland, core network (extrapolated) | ~11 MB | — | motorway–secondary |
| Europe, motorway + trunk (extrapolated) | — | ~67 MB | cross-border routing |

So **full Poland + European motorways fits comfortably**. Selection is about
user intent, routing scope and build time, not about saving megabytes.

> **Important:** the unit has no known runtime region picker. In v1 the user
> chooses a profile when **building the card image**; different profiles mean
> different cards/images, not a menu in the car.

## Profile format (version 2, shipped 2026-11-06)

A profile is a small JSON file under `profiles/`, validated against
[`profiles/schema.json`](../../profiles/schema.json). It describes *what to
include*, not *how to encode it*; the compiler decides encoding from the format
rules. The four shipped profiles were migrated from the 2026-11-05 version-1
draft to version 2 (EXP-2026-11-06-M7.4); version 1 is now accepted only
through the legacy adapter in `tools/profile_validate.py`.

```json
{
  "version": 2,
  "name": "poland-full",
  "description": "All of Poland, all roads, addresses and POIs, delivered as whole tiles with a border buffer for cross-border routing.",
  "sources": ["poland-latest.osm.pbf"],
  "region": {
    "name": "Poland",
    "bbox": [14.12, 49.0, 24.15, 54.84],
    "countries": ["PL"]
  },
  "coverage": {
    "default": "detail",
    "tiers": [
      {
        "id": "detail",
        "description": "Every drivable road, both address kinds, all POIs, administrative boundaries.",
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
  "outputs": {
    "image_name": "poland-full.img",
    "manifest": true,
    "verify": true,
    "card_label": "OSM-PL"
  }
}
```

### Fields

- `version`: `2`. The schema is closed for this shape; new keys need a schema
  change and a validator update.
- `region.bbox`: `[west, south, east, north]` in degrees. `countries` is
  provenance only; the bbox is authoritative.
- `coverage.tiers`: tried in array order, **first match wins**. One profile can
  therefore mix "Poland at full detail" with "the European corridor at
  motorway/trunk only", which is what `europe-motorways` does.
- `coverage.tiers[].roads`: `all`, `core` (motorway–secondary), `none`, or an
  explicit OSM class list. `addresses` keeps node and way addresses; two
  thirds of Polish addresses are on buildings.
- `coverage.tiers[].pois`: `all`, `none`, or a category list (fuel,
  charging, parking, amenity, shop, tourism…).
- `coverage.tiers[].admin_boundaries`: needed for region/city search.
- `tiles.mode`: always `whole-tiles`. `include` is an explicit tile list;
  empty means derive from `region` + buffer. `exclude` is for experiments.
- `border_buffer_deg`: buffer in latitude degrees (1° lat = 111.32 km); the
  longitude padding is divided by `cos(mid-latitude)`. The buffer keeps roads
  just outside the selected area so routing does not stop at the border.
- `attribution`: ODbL text plus where it ships (`card-file`, `download`,
  `manifest`).
- `limits`: `max_image_bytes`, `max_tiles`, `min_free_bytes`; `build.py`
  enforces all three against the estimate.
- `outputs`: image name, manifest and verify flags, FAT card label.
- `routing` from the version-1 shape is deliberately **not** in version 2: no
  routing graph is built yet, so keeping it would be a promise the tools cannot
  keep. When the graph lands it gets a real schema block.

## Shipped profiles

Resolved counts come from `tools/mesh_grid.py` through
`tools/profile_validate.py`; sizes are the `build.py --dry-run` **ESTIMATE**
(roads anchored to a measurement, refer/POI/admin placeholders).

| Profile | Purpose | Tiles | Estimate |
| --- | --- | --: | --: |
| `dolnoslaskie-detail` | full detail for Dolnośląskie + 50 km buffer, whole `B48R058R` | 1 | 44.6 MB |
| `dolnoslaskie-test` | one-tile vertical slice, core roads only | 1 | 1.5 MB |
| `poland-full` | all Poland, all roads, addresses, POIs | 4 | 178.4 MB |
| `europe-motorways` | Poland full + European motorway/trunk corridor | 56 | 253.4 MB |

The `dolnoslaskie-detail` estimate is 44.6 MB rather than the 20–40 MB first
guessed here, because whole-tile delivery makes that profile carry the rest of
south-west Poland inside `B48R058R`. `europe-motorways` resolves 56 addressable
cells (11 more than the 45 shipped tiles); the extra cells are sea/empty, so the
count and the estimate are upper bounds (`N001`, informational, never a
`--strict` failure).

These values are the regression constants in `tools/profile_validate.py
--selftest` (1 / 1 / 4 / 56 tiles) and `tools/build.py --selftest`
(44.6 / 1.5 / 178.4 / 253.4 MB).

## How a build runs (planned)

`tools/build.py --dry-run` prints the M5 compiler spine and marks every step
`NOT IMPLEMENTED`; it executes no stage and writes nothing. Without `--dry-run`
it exits `3`.

| # | Stage | Input → output | Status |
| --: | --- | --- | --- |
| 1 | `osm_ingest` | `.osm.pbf` → IMF v1 | **NOT IMPLEMENTED** in `build.py` (tool exists, M5.1) |
| 2 | `mesh_split` | IMF v1 → whole `BxxRyyR` tiles | **NOT IMPLEMENTED** (M5.2) |
| 3 | tile writer | tile model → tile `.DAT`/`.cmp` | **NOT IMPLEMENTED** (M5.4) |
| 4 | manifests | tiles → `DRSTR`/`MMAIN`/`.ind` | **NOT IMPLEMENTED** (M5.6) |
| 5 | card image | card tree → `<image>.img` | **NOT IMPLEMENTED** (M5.10) |

## Decision: whole tiles only

**Decision (2026-11-05): build and ship whole tiles. Do not clip inside a
tile.**

Tiles are **5.333° × 8°** on the verified `BxxRyyR` grid
([`../format/map-tiles.md`](../format/map-tiles.md)). The whole Dolnośląskie
bbox (14.0–17.9 E, 49.9–51.9 N) plus a 50 km buffer lies inside the single
tile **`B48R058R`** (48.00–53.33 N, 12–20 E), so “only Dolnośląskie” means
“that one full tile”, including whatever else it covers (C-565). An earlier
“2–3 tiles” estimate is superseded.
That is accepted: a correct, dense tile is more valuable than a sparse tile
whose behaviour on the unit is unproven.

Consequences:

- A profile selects **tile IDs**, not a polygon and not a bbox.
- `bbox`/`countries` are only used to decide which tiles to include and to
  build the routing graph; they do not clip tile contents.
- All data from the source extract that belongs to a selected tile is
  generated, including neighbouring-country roads inside the same tile.
- The border buffer is therefore mostly automatic at tile granularity, but
  the routing graph still needs explicit cross-border ways.
- “Dolnośląskie detail” is expected to be coarser than the voivodeship
  border; document that in the profile description.
- Do not implement sub-tile clipping unless the format and the unit are later
  proven to support it.

`tiles.mode` is therefore `"whole-tiles"` in every profile.

## Card output rules

A profile changes the map payload, but the card still needs:

- the common `VER_INFO/HDD_INFO.TXT` and firmware/pre-partition area (if the
  unit requires them),
- a consistent `DRSTR001.DAT` (nodes, counts, logical sizes),
- tile order/index preserved where the unit expects it,
- the correct volume label and lock state.

Removing files or changing sizes without updating the manifest is a likely
failure mode.

## Attribution

ODbL requires attribution for a distributed derived database. The unit has no
browser. Decide early whether to:

- put an `ODbL.txt`/`README.txt` on the card (test that extra files do not
  break the manifest),
- ship attribution with the image/download, and
- keep the database provenance in `manifest.json` next to the build output.

All four shipped profiles currently use `attribution.location: "manifest"`:
the text ships with the build output, not on the card. That is a placeholder
decision, not a legal conclusion — the `card-file` option still needs the
manifest test above, and the final choice belongs with the distribution plan.
