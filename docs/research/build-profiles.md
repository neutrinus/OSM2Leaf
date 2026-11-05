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

## Proposed profile format

A profile is a small JSON file under `profiles/`. It describes *what to
include*, not *how to encode it*. The compiler decides encoding from the
format rules.

```json
{
  "name": "poland-full",
  "description": "All of Poland, full detail, with a border buffer for cross-border routing.",
  "sources": ["poland-latest.osm.pbf"],
  "include": {
    "countries": ["PL"],
    "bbox": null,
    "border_buffer_km": 50,
    "tiles": {"mode": "auto", "include": [], "exclude": []}
  },
  "detail": {
    "roads": "all",
    "addresses": true,
    "pois": "all",
    "admin_boundaries": true
  },
  "routing": {
    "profile": "car",
    "keep_cross_border": true
  }
}
```

### Fields

- `sources`: Geofabrik extracts to read. Prefer a national extract plus a
  border buffer over a voivodeship cut, because a voivodeship cut severs
  cross-border roads.
- `include.countries` / `bbox`: coarse selection.
- `border_buffer_km`: keep roads just outside the selected area so routing
  does not stop at the border.
- `include.tiles`: `auto` (derive from the region), or explicit tile IDs once
  the `BxxRyyR` grid is decoded. `exclude` is for experiments.
- `detail.roads`: `all`, `core` (motorway–secondary), or a class list.
- `detail.addresses`: keep both node and way addresses; two thirds of Polish
  addresses are on buildings.
- `detail.pois`: `all`, `none`, or a category list (fuel, charging, parking,
  amenity, shop, tourism…).
- `detail.admin_boundaries`: needed for region/city search.
- `routing.keep_cross_border`: keep the border buffer in the routing graph.

## Starting profiles

| Profile | Purpose | Expected size |
| --- | --- | --- |
| `dolnoslaskie-detail` | full detail for Dolnośląskie + border buffer | ~20–40 MB |
| `poland-full` | all Poland, all roads, addresses, POIs | ~200–300 MB |
| `europe-motorways` | Poland full + European motorway/trunk network | ~300–400 MB |

These are estimates; the compiler should print a size breakdown before
writing an image.

## Tile-granularity caveat

External prior art suggests tiles are about **5.333° × 8°**. All of
Dolnośląskie would fall into 2–3 tiles, so “only Dolnośląskie” cannot be
implemented by dropping whole tiles without also dropping neighbouring
regions. Two options:

1. **Selected records in a full tile**: keep the tile container, generate
   records only for the selected area, leave the rest empty. Requires proof
   that the unit tolerates sparse tiles.
2. **Whole-tile selection**: simpler, but the user gets a coarser region
   (e.g. “central Europe”) rather than a voivodeship.

Until the tile format is decoded, treat `include.tiles` as a build-time hint,
not a promise of sub-tile clipping.

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

This is a legal decision, not only a technical one; record it before
distributing images.
