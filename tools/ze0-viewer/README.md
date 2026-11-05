# ZE0 tile viewer / round-trip harness

A thin ZE0-specific layer on top of the GPL-3.0 `albertbm/osm2clarion` tools.
It decodes `MAPAL001` background geometry to GeoJSON/PNG and round-trips
tiles.

> **Status:** works byte-identically for `B28R070R`, `B30R060R`, `B58R070R`
> and `LEV3456R`. Dense tiles with section 4 (`B30R048R`, `B40R050R`) are not
> fully decoded. Drawn road shapes are not rendered yet.

## Setup

```bash
cd tools/ze0-viewer
./setup.sh
```

The script clones `https://github.com/albertbm/osm2clarion` at the pinned
commit `07fbf78d049e7765db887818e77419ffc3dd499a` into `vendor/`
(git-ignored), applies `ze0-tools.patch`, and creates the `tools_ze0` symlink.

Requirements: `git`, `patch`, Python 3.10+. PNG rendering uses Pillow if
available; otherwise a slower stdlib fallback is used.

## Commands

```bash
# Structural self-test and round-trip on one tile
python3 harness.py selftest /path/to/B58R070R.DAT
python3 harness.py verify   /path/to/B28R070R.DAT

# Decode to GeoJSON
python3 harness.py decode /path/to/B30R060R.DAT out/B30R060R.geojson

# Render a tile, optionally with the LEV3456R coarse background
python3 harness.py render /path/to/B30R060R.DAT out/B30R060R.png
python3 harness.py compose /path/to/B30R060R.DAT /path/to/LEV3456R.DAT \
    out/B30R060R_composite.png --cell B30R060R

# One-vertex mutation + round-trip check
python3 harness.py mutate /path/to/B58R070R.DAT out/mutated.DAT

# Compare a decoded coastline against an OSM XML extract
python3 compare_osm.py out/B30R060R.geojson osm-extract.osm
```

## What the ZE0 patch fixes

1. zlib header is `78 9c` (upstream hardcodes `58 85`).
2. Background record kind is `0x00fa` at both levels; the even/odd pair is the
   reliable discriminator.
3. Directory slot-body size follows the directory kind; section-2 level-2 is
   `0x2046` with 512-byte bodies.
4. Empty slots may use `0x7fffffff` as well as `0xffffffff`.

The bounding-box table is fixed at `0x2ac`; `VER_INFO/HDD_INFO.TXT` replaces
`DB_INFO.TXT`; ZE0 has 45 grid tiles + `LEV`.

## Known limits

- `B30R048R` (section 4, directory `0x2146`) does not round-trip yet.
- `read_tile` is not streaming; a 73 MB tile peaked at ~20 GB RSS. Use
  `harness.py scan` for large tiles.
- Drawn road-shape records (even pair) are not decoded, so the PNG has no
  roads.
- `LEV3456R` levels 3–5 work; level 6 has a different layer layout.
- No address/POI reader exists in `osm2clarion`; it has writers only.

## Licensing

`osm2clarion` is GPL-3.0-or-later; this repo is GPL-3.0-or-later. The upstream
code is not vendored here — `setup.sh` clones it and applies our patch. Keep
the upstream license and attribution when redistributing.
