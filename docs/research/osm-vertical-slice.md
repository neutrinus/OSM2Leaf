# OSM-to-tile vertical slice (ZE0, offline only)

**Status:** plan and starter artifacts only. No factory data is modified and no
hardware validation is claimed. The unit has not been tested with the output of
this slice.

**Base:** `tools/ze0-viewer/vendor/osm2clarion` (pinned) plus the ZE0 patch in
`tools/ze0-viewer/ze0-tools.patch`. The tile writer, `DRSTR`/`MMAIN` builders
and `osmium`-based extraction are reused; nothing is reimplemented here.

## Scope of the slice

- **One tile:** `B48R058R.DAT` (48.00..53.33 N, 12.00..20.00 E), which
  contains Wrocław and is a populated, road-dense tile.
- **Roads only:** core network (motorway–secondary) at the osm2clarion
  defaults. Addresses, POIs, admin boundaries and buildings/landuse are **not**
  imported in this slice.
- **Preserve everything else:** factory `REFER001`/`REFER002`, `ADDRE`,
  `RDSTM`, `BICON`, `OPNG`, `SPEECH`, `TMC`, `VER_INFO`, all other tiles and
  the coarse `LEV3456R.DAT` except for the parcels this slice rewrites.
- **Validation is offline only** (L1/L2). Passing it is a precondition for any
  later card test, not evidence that the unit will accept the card.

## Starter artifacts

- `profiles/dolnoslaskie-test.json` — repo-level selection profile (JSON
  convention used by `docs/research/build-profiles.md`).
- `profiles/dolnoslaskie-test.toml` — osm2clarion build profile (TOML, one
  cell). This is the file the build commands below consume.

The TOML profile selects exactly one cell and keeps the shipped European
database box, so no grid shift is needed:

```text
cells  = ["B48R058R"]
bounds = [4800, 1280, -1200, 4080]   # shipped European box, arc-minutes
```

## Prerequisites

- Python 3.11 for `tomllib`/`osmium` (osmium has no wheel for 3.14 on this
  machine; 3.11 is available).
- `pip install shapely osmium`
- Vendor tools set up (read-only; does not touch factory data):

  ```bash
  cd tools/ze0-viewer
  ./setup.sh
  ```

- A verified, read-only backup of the factory image/root and its SHA-256
  (`105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307` for
  the EU 2011 image). Work only on a copy.

## Inputs

| Input | Path (example) | Notes |
| --- | --- | --- |
| Factory root (copy) | `/tmp/osm2leaf-slice/root` | extracted EU 2011 tree; never the original |
| Small OSM extract | `<repo>/build/Wroclaw.osm.pbf` | bbbike Wrocław; keeps the first run cheap |
| Build profile | `<repo>/profiles/dolnoslaskie-test.toml` | one cell |
| Output dir | `/tmp/osm2leaf-slice/out` | generated map files only |

## Commands

### 0. Validate the profile (no data needed)

```bash
cd tools/ze0-viewer/vendor/osm2clarion
python3.11 tools/clarion_profile.py /path/to/profiles/dolnoslaskie-test.toml
```

Expected: `<Profile dolnoslaskie-test cells=1 ...>` and `cells = ['B48R058R']`.

### 1. Prepare a working copy of the factory tree

```bash
rm -rf /tmp/osm2leaf-slice
mkdir -p /tmp/osm2leaf-slice
cp -a /path/to/factory/root /tmp/osm2leaf-slice/root
```

Do not use the original tree or image as the build base.

### 2. (Optional) fetch the small test extract

```bash
mkdir -p build
curl -o build/Wroclaw.osm.pbf \
  https://download.bbbike.org/osm/bbbike/Wroclaw/Wroclaw.osm.pbf
```

For a real slice, use the Geofabrik Dolnośląskie/Poland extract instead and
update the profile's `source.osm`.

### 3. Extract OSM data (the only step that needs `osmium`)

```bash
cd tools/ze0-viewer/vendor/osm2clarion
python3.11 build.py \
  --profile /path/to/profiles/dolnoslaskie-test.toml \
  --base /tmp/osm2leaf-slice/root \
  --out /tmp/osm2leaf-slice/out \
  --only extract
```

This writes `build/roads_dolnoslaskie-test.json` and
`build/coast_dolnoslaskie-test.json` (paths come from the profile). It does
**not** modify factory data.

### 4. Build the map artifacts (extract step is skipped by default)

```bash
cd tools/ze0-viewer/vendor/osm2clarion
python3.11 build.py \
  --profile /path/to/profiles/dolnoslaskie-test.toml \
  --base /tmp/osm2leaf-slice/root \
  --out /tmp/osm2leaf-slice/out
```

Steps run: `coarse`, `background`, `roads`, `master`, `index`. Output contains
`MAPAL001/B48R058R.DAT`, `MAPAL001/LEV3456R.DAT`, `MMAIN001.DAT` and
`DRSTR001.DAT`.

### 5. Merge the generated files into the factory clone

Copy **only** the four generated files; keep every other factory file:

```bash
cp /tmp/osm2leaf-slice/out/MAPAL001/B48R058R.DAT \
   /tmp/osm2leaf-slice/root/MAPAL001/B48R058R.DAT
cp /tmp/osm2leaf-slice/out/MAPAL001/LEV3456R.DAT \
   /tmp/osm2leaf-slice/root/MAPAL001/LEV3456R.DAT
cp /tmp/osm2leaf-slice/out/MMAIN001.DAT \
   /tmp/osm2leaf-slice/root/MMAIN001.DAT
cp /tmp/osm2leaf-slice/out/DRSTR001.DAT \
   /tmp/osm2leaf-slice/root/DRSTR001.DAT
```

### 6. L1 — structural validation

```bash
python3 tools/cardcheck.py --root /tmp/osm2leaf-slice/root
```

Expected (EU 2011 baseline shape, with the four files above replaced):

- `RESULT: PASS`, exit code 0
- `files=480`, `dirs=39` (counts unchanged)
- `pairs=194`, `ok=194` (all `REFER001` pairs still valid)
- `tiles=46`, `rows=11`, `ok=11`
- no errors; warnings are acceptable only if explained

`cardcheck` verifies `DRSTR001.DAT` against the real tree, `MMAIN001.DAT`
level totals against every tile header, common headers and `.cmp`/`.ind` pairs.

### 7. L2 — semantic / round-trip validation

```bash
python3 tools/l2check.py --root /tmp/osm2leaf-slice/root --no-golden
```

Expected:

- `DRSTR001.DAT` rebuilt from the tree is byte-identical
- all 194 `REFER001` pairs survive a preserved-stream round-trip
- the five reference tiles (`B28R070R`, `B30R060R`, `B58R070R`,
  `B30R048R`, `LEV3456R`) rebuild byte-identically
- tile mutation and POI-rename checks pass

Use `--no-golden`: the tile geometry changed, so the stored golden digest in
`tools/golden/eu2011.json` no longer applies. Do not refresh the golden
profile to hide a failure.

### 8. Inspect the rebuilt tile

```bash
cd tools/ze0-viewer
python3 harness.py verify /tmp/osm2leaf-slice/root/MAPAL001/B48R058R.DAT
python3 harness.py info   /tmp/osm2leaf-slice/root/MAPAL001/B48R058R.DAT
```

Expected: every record inflates, every background record rebuilds
byte-exactly, and no assertion is raised.

Optional geometry sanity check:

```bash
python3 harness.py decode \
  /tmp/osm2leaf-slice/root/MAPAL001/B48R058R.DAT \
  /tmp/b48r058r.geojson --levels 1,2 --cell B48R058R
```

Then inspect the GeoJSON for a plausible road count and names.

## Stop conditions

Stop and do **not** proceed to any card test if any of the following holds:

1. `cardcheck.py` reports an error or non-zero exit code.
2. `l2check.py` reports a failure or non-zero exit code.
3. `DRSTR001.DAT` rebuilt from the tree is not byte-identical.
4. `MMAIN001.DAT` level totals disagree with the tile headers.
5. An unchanged reference tile no longer rebuilds byte-identically.
6. `harness.py verify` raises or a background record does not rebuild.
7. The merged tree contains unexpected files or any factory `REFER001`,
   `ADDRE`, POI, `RDSTM`, `BICON`, `OPNG`, `SPEECH`, `TMC` or `VER_INFO`
   file changed.
8. The slice appears to need sub-tile clipping, address/POI import or a
   section-4 encoder — these are explicitly out of scope and require a new
   plan/experiment before implementation.
9. There is any temptation to describe offline L1/L2 success as hardware
   acceptance. It is not; hardware validation is a separate gate
   (`docs/research/roadmap.md`, Gate 6) and requires a spare SD card.

## Non-goals (not done by this slice)

- No full Poland/Europe build and no multi-tile output.
- No address, POI, admin-boundary or building/landuse import.
- No section-4 (admin/place index) encoder; section 4 is preserved verbatim by
  the tile writer.
- No routing-graph changes beyond what osm2clarion already emits.
- No modification of firmware, map codes or `HDD_INFO.TXT`.
- No claim of hardware validation.

## Safety notes

- The original SD card/image stays read-only; verify its hash before and after.
- All generated artifacts live under `/tmp` or `<repo>/build`; neither is
  committed. `archive/` and `*.img` are git-ignored.
- OSM-derived output is ODbL 1.0; record provenance in `manifest.json` before
  any distribution (see `docs/research/build-profiles.md`).
