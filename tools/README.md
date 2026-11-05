# Tools

Small, standard-library Python 3.10+ scripts for inspecting Leaf ZE0 map data.
None of them need vendor files to be present unless you ask them to inspect
one. All are read-only by default.

## `cmpind.py`

Decode and verify `REFER001/*.DAT.cmp` + `*.DAT.ind` containers.

```bash
# Print the index header and chunk offsets
python3 tools/cmpind.py info REFER001/ADDRE001.DAT.ind

# Decompress one file
python3 tools/cmpind.py extract REFER001/ADDRE001.DAT.cmp -o /tmp/ADDRE001.DAT

# Verify every pair in a directory
python3 tools/cmpind.py verify REFER001
```

Expected output of `verify` on the EU 2011 image:

```
checked   194 pair(s)
ok        194
failed    0
logical   2390610176 bytes
stored    1421900190 bytes
```

## `cmpind_writer.py`

Read/write `.cmp`/`.ind`. Two modes:

```bash
# Preserve original streams; rebuild only the index (byte-identical)
python3.13 tools/cmpind_writer.py preserve \
    REFER001/COORD001.DAT.cmp REFER001/COORD001.DAT.ind out COORD001.DAT

# Recompress from scratch (semantic; byte-identical only with matching zlib)
python3.13 tools/cmpind_writer.py recompress \
    REFER001/COORD001.DAT.cmp REFER001/COORD001.DAT.ind out COORD001.DAT

# Verify every pair
python3.13 tools/cmpind_writer.py verify REFER001
```

Factory-identical recompression needs stock zlib 1.3.1, level 6, wbits 15,
memLevel 8, default strategy. zlib-ng (sometimes Python 3.14) does **not**
reproduce the bytes; use `preserve`.

## `leafimg.py`

Inspect a raw SD card image and the common 512-byte map-file header.

```bash
python3 tools/leafimg.py info /path/to/leaf2011.img
python3 tools/leafimg.py header MAPAL001/B28R070R.DAT
```

`info` reads the MBR, finds FAT partitions, and prints the volume label,
cluster size and root cluster. `header` decodes the UTF-16BE strings and the
binary block at `0x180`.

## `drstr.py`

Parse `DRSTR001.DAT` into nodes and directory listings.

```bash
python3 tools/drstr.py parse DRSTR001.DAT
python3 tools/drstr.py parse DRSTR001.DAT --json
```

The parser stops at the first listing, because the node table ends where the
first 32-byte entry begins.

## `lctbl_names.py`

Decode the `LCTBL001.DAT` catalog and compressed name database.

```bash
python3 tools/lctbl_names.py verify LCTBL001.DAT
python3 tools/lctbl_names.py catalog LCTBL001.DAT
python3 tools/lctbl_names.py names LCTBL001.DAT --sample 10
```

`verify` on the EU 2011 image prints `streams 517 / plain 11481060 /
records 328628 / OK`.

## `rdstm_scan.py`

Inspect `RDSTM001.DAT`: block layout, negative zlib result, and the 2-byte
codes shared with the LCTBL catalog.

```bash
python3 tools/rdstm_scan.py layout RDSTM001.DAT
python3 tools/rdstm_scan.py zlib RDSTM001.DAT --bruteforce
python3 tools/rdstm_scan.py codes RDSTM001.DAT --lctbl LCTBL001.DAT
```

## `mesh_grid.py`

Map `MAPAL001/BxxRyyR.DAT` names to latitude/longitude (B/R are hex).

```bash
python3 tools/mesh_grid.py list MAPAL001
python3 tools/mesh_grid.py matrix MAPAL001
python3 tools/mesh_grid.py cell B48R058
```

## REFER mutation helpers

```bash
# List Latin-1 names inside inner zlib pages
python3 tools/scan_refer_names.py POINT032.DAT.cmp --min 8

# Same-length POI rename (writes a new .cmp/.ind pair)
python3 tools/mutate_refer_poi.py POINT032.DAT.cmp POINT032.DAT.ind /tmp/mut \
    --page 0x4200 --old "VATICAN MUSEUM" --new "OSM2LEAF PROBE"

# Offline acceptance check
python3 tools/validate_mutation.py REFER001 /tmp/mut POINT032.DAT \
    --page 0x4200 --drstr DRSTR001.DAT --inner-page 0x4200
```

`mutate_refer_page.py` applies a same-length in-page byte patch (e.g. a
coordinate nudge). `drstr_ze0.py` is the reader/writer helper used by the
validator. See [`../docs/research/minimal-change.md`](../docs/research/minimal-change.md).

## ZE0 tile viewer / round-trip

`tools/ze0-viewer/` clones a pinned `osm2clarion`, applies the ZE0 patch and
provides a harness that decodes tiles to GeoJSON/PNG and round-trips them.

```bash
cd tools/ze0-viewer
./setup.sh
python3 harness.py verify /path/to/B58R070R.DAT
python3 harness.py compose /path/to/B30R060R.DAT /path/to/LEV3456R.DAT \
    out/B30R060R_composite.png --cell B30R060R
```

Clean tiles (`B28R070R`, `B30R060R`, `B58R070R`, `LEV3456R`) rebuild
byte-identically. Dense section-4 tiles and drawn roads are still open.

## `solve_data_delta.py`

Window-scored data-delta solver for firmware pools (useful when a module mixes
data and code pointers). It recovered VerInfoCC's `0x027cae00` where a
0x1000-only grid would fail.

```bash
python3 tools/solve_data_delta.py IMAGE --around 0x6fb000 --span 0x2000
```

## `hddinfo_variants.py`

Generate length-preserving `HDD_INFO.TXT` variants for the spare-card
map-code matrix (all outputs stay 72 bytes):

```bash
python3 tools/hddinfo_variants.py VER_INFO/HDD_INFO.TXT /tmp/variants --sweep 0-5
```

It emits a last-character change, `0…5` sweeps over digit runs, and
uppercase-word replacements, plus `MANIFEST.txt`.

## `selftest.py`

Runs synthetic tests for the primitive parsers without any vendor data. It
covers `cmpind.py`, `drstr.py`, `mesh_grid.py` and the L1 helpers (level table,
common header, LFN, `.cmp` decode, logical listing):

```bash
python3 tools/selftest.py
```

Expected: `selftest: OK`.

## `cardcheck.py` — L1 whole-card validator

Validates a raw image or an extracted card root. It reads MBR/FAT32 in image
mode, checks the required tree, common headers, every `.cmp`/`.ind` pair,
`DRSTR001.DAT` against the real tree, `MMAIN001` level-table totals against
every tile header, `HDD_INFO.TXT`, `CMP.LST` and the image copy at
`0x06000000`.

```bash
# Extracted root (fast)
python3 tools/cardcheck.py --root /path/to/root

# Raw image (also checks MBR, FAT and the 0x06000000 copy)
python3 tools/cardcheck.py --image /path/to/leaf2011.img

# Machine-readable report and image hash
python3 tools/cardcheck.py --image /path/to/leaf2011.img \
    --json report.json --hash \
    --expect-sha256 105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307
```

Expected on the EU 2011 sample: `RESULT: PASS`, with `files=480`,
`dirs=39`, `bytes=5173965667`, `pairs=194`, `logical=2390610176`,
`stored=1421900190`, `tiles=46`, `rows=11`, `ok=11`.

Exit codes: `0` pass, `1` validation error, `2` bad source. Warnings do not
fail unless `--strict` is used. `--fast` skips `.cmp` decompression.

`--partial` validates a map-only tree (the archived `EU_MAPDATA_*.7z` trees)
where `VER_INFO/` is absent; it treats the missing directory as a warning.
`--ignore-dump-artifacts` ignores macOS `._*`, `.fseventsd` and
`System Volume Information` entries. It is needed for the 2016 e-NV200 image
and the 2019 image, but keep it explicit: it can hide a real extra file.

## `l2check.py` — L2 semantic / golden checks

Checks that a root still round-trips and that the decoded geometry matches a
stored golden profile:

* `DRSTR001.DAT` rebuilt from the tree is byte-identical;
* every `REFER001` pair survives a preserved-stream round-trip;
* five target tiles rebuild byte-identically;
* decoded geometry of four target tiles matches the golden digest;
* a one-vertex tile mutation changes exactly one vertex;
* a same-length POI rename passes `validate_mutation.py`.

```bash
# Full L2 run against tools/golden/eu2011.json
python3 tools/l2check.py --root /path/to/root

# Quick run: 20 .cmp pairs, no tile checks
python3 tools/l2check.py --root /path/to/root --cmp-limit 20 --no-tiles

# Regenerate the golden profile after an intentional decoder change
python3 tools/l2check.py --root /path/to/root \
    --update-golden tools/golden/eu2011.json --image /path/to/leaf2011.img
```

Expected on the EU 2011 sample: `RESULT: PASS`, with `pairs=194`, `ok=194`,
five round-trip tiles, four geometry digests, and `tile_mutation` reporting
one removed and one added feature.

`--no-golden` skips profile comparisons (useful for a newly built card);
`--include-lev` adds the slow `LEV3456R.DAT` geometry digest; `--hash-image`
checks the raw image hash against the profile.

L2 now passes on full 2014 and 2016 roots with
`--no-golden --ignore-dump-artifacts`. The unchanged dense `B30R048R.DAT`
uses a preserved-layout fallback (reported as a warning); changed tiles still
go through the writer. The REFER001 mutation fixture is discovered per year,
and `validate_mutation.py --drstr-dir REFER001` avoids the
`REFER001`/`REFER002` name collision. The 2011 golden profile remains the
reference; per-year golden profiles are optional.

## Golden profile

`tools/golden/eu2011.json` stores the reference sample's image hash, tree
census, `DRSTR`/`MMAIN` hashes, selected file hashes and the tile geometry
digests. It contains no vendor data, only hashes and counts. Update it only
when a decoder change is intentional, and record the reason in an experiment.

## Conventions

- Read-only. Scripts that write require an explicit output path.
- No hard-coded absolute paths.
- Evidence and format notes live in [`../docs/format/`](../docs/format/); claim
  status lives in [`../docs/research/claims.md`](../docs/research/claims.md).
