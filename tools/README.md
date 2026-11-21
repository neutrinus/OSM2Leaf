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

## `rebuild_manifests.py`

Rebuild `DRSTR001.DAT`, `MMAIN001.DAT` `0x1ac` level-table totals,
`REFER001/*.ind` (stream-preserving pair rewrite) and `CMP.LST` for a card
tree so `cardcheck` L1 passes (M5.6). DRSTR uses `drstr_ze0.build` and keeps
stored name/order; MMAIN counts are recomputed from `MAPAL001` tile headers
(big-endian `u16`, C-164/C-1788); `CMP.LST` is the fixed `\SystemSD\REFER001\`.

```bash
python3 tools/rebuild_manifests.py --selftest
python3 tools/rebuild_manifests.py --root /path/to/card-tree --check
python3 tools/rebuild_manifests.py --root /path/to/card-tree --check --partial --fast --json
```

## `lctbl_names.py`

Decode the `LCTBL001.DAT` catalog and compressed name database.

```bash
python3 tools/lctbl_names.py verify LCTBL001.DAT
python3 tools/lctbl_names.py catalog LCTBL001.DAT
python3 tools/lctbl_names.py names LCTBL001.DAT --sample 10
```

`verify` on the EU 2011 image prints `streams 517 / plain 11481060 /
records 328628 / OK`. The last number is a **text-run scan**, not the record
count; use `lctbl_records.py` for the framed records.

## `lctbl_records.py`

Decode the fixed records inside the `LCTBL001.DAT` zlib streams: a 16-byte
header, four even-padded name slots and an opaque footer.

```bash
python3 tools/lctbl_records.py stats LCTBL001.DAT
python3 tools/lctbl_records.py dump LCTBL001.DAT --stream 2 --limit 10
python3 tools/lctbl_records.py roundtrip LCTBL001.DAT --all
python3 tools/lctbl_records.py verify LCTBL001.DAT
python3 tools/lctbl_records.py --selftest          # synthetic, no vendor data
```

`verify` on the EU 2011 image prints `streams 517 / plain 11481060 /
records 247089 / fields (36461, 66189, 243907, 109944) / OK`; `roundtrip`
re-encodes every stream byte-identically. See
[`../docs/format/rdstm.md`](../docs/format/rdstm.md) "Record layout".

## `poi_icons.py`

List the `BICON001` PNG table and join `POINT` category/brand codes to icons.

```bash
python3 tools/poi_icons.py bicon BICON001/BICON001.DAT
python3 tools/poi_icons.py codes /tmp/poi      # extracted POINT0nn.DAT files
python3 tools/poi_icons.py verify /tmp/poi --bicon BICON001/BICON001.DAT
```

`codes`/`verify` read `POINT0nn.DAT` files that were first extracted with
`tools/cmpind.py extract`. `verify` checks all 34 rows of the mapping in
`docs/format/assets.md` and prints `RESULT: PASS`.

## `poi_point_check.py`

Decode POI copy-A/B packed ids from POINT shards and compare with a reference
table (M4.8b). Records are addressed by `(shard, stream_offset, record_index)`;
`find` prints names to the terminal only.

```bash
python3 tools/poi_point_check.py --selftest
python3 tools/poi_point_check.py find ROOT SHARD --a X Y
python3 tools/poi_point_check.py check --us US_ROOT --eu EU_ROOT REFS.tsv
```

## `poi_subunit.py`

Scan zlib-framed POINT name records for 0..2047-class sub-unit position fields
and test correlation with `local(A)` at `coord.py` scales 1 and 2 (M4.8d).

```bash
python3 tools/poi_subunit.py --selftest
python3 tools/poi_subunit.py scan ROOT SHARD [SHARD ...] [--limit N]
python3 tools/poi_subunit.py refs --us US_ROOT --eu EU_ROOT REFS.tsv
```

Finds the 11-bit body fields `v6=0x0800|(v6&0x7ff)`, `v8`, and discrete
`v16/v20` (OBSERVED); none encode a geographic local position of copy A
(negative, C-2931). `refs` needs the M4.8b TSV (Wikipedia coords, not in repo).

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

# Different-length POI rename: patch the record length byte and shift the page
python3 tools/mutate_refer_poi.py POINT032.DAT.cmp POINT032.DAT.ind /tmp/mut \
    --page 0x4200 --resize --old "VATICAN MUSEUM" --new "OSM2LEAF PROBE POI"

# Run Navi.exe's own POINT record walker (fn 0x003f5194) on a real page (M3.11)
python3 tools/point_walk_l3.py sections head256.img        # 0 compressed code sections
python3 tools/point_walk_l3.py walk head256.img --cmp POINT010.DAT.cmp \
    --ind POINT010.DAT.ind --page 0x840ba0 --page-len 42848

# Who reads (and writes) a decoded page: read/write watch, per function (M9.38)
python3 tools/l3_harness/watch.py label head256.img --entry 0x003f5194 0x003f5194
python3 tools/read_watch_l3.py walk us256.img --cmp POINT010.DAT.cmp \
    --ind POINT010.DAT.ind --page 0x840ba0 --build us2011 --n 0,1,2
python3 tools/read_watch_l3.py above head256.img --cmp POINT010.DAT.cmp \
    --ind POINT010.DAT.ind --build eu2011 --n 1
python3 tools/read_watch_l3.py probe head256.img --buf LCTBL001.DAT \
    --entry 0x0040de98,0x004125a8

# Offline acceptance check
python3 tools/validate_mutation.py REFER001 /tmp/mut POINT032.DAT \
    --page 0x4200 --drstr DRSTR001.DAT --inner-page 0x4200
```

`--resize` understands the POINT name-page framing (`docs/format/refer.md`):
`u8 tag (0x60/0x68) | u8 len2` records of `2*len2` bytes, ending `ff ff`.
It refuses a page that is not a record chain, an odd name delta (the length is
stored as `size/2`) and a recompressed page that would cross the next stream.
`--selftest` covers the framing and those refusals on a synthetic page.

`mutate_refer_page.py` applies a same-length in-page byte patch (e.g. a
coordinate nudge). `drstr_ze0.py` is the reader/writer helper used by the
validator. See [`../docs/research/minimal-change.md`](../docs/research/minimal-change.md).

## ZE0 tile viewer / round-trip

`tools/ze0-viewer/` ships a checked-in copy of the pinned `osm2clarion` tools
(`tools_ze0/`, patched by `ze0-tools.patch`) and a harness that decodes tiles to
GeoJSON/PNG and round-trips them. `harness.py` imports that copy directly;
`setup.sh` only audits or regenerates it against a git-ignored `vendor/` clone
and is not needed to run the harness
(see [`../docs/format/ze0-tools.md`](../docs/format/ze0-tools.md)).

```bash
cd tools/ze0-viewer
python3 harness.py verify /path/to/B58R070R.DAT
python3 harness.py compose /path/to/B30R060R.DAT /path/to/LEV3456R.DAT \
    out/B30R060R_composite.png --cell B30R060R

# Only after a pin or patch change: rebuild and compare the checked-in copy
./setup.sh              # clone/fetch the pin, rebuild, diff (no write)
./setup.sh --update     # replace tools_ze0/ with the rebuild
```

Clean tiles (`B28R070R`, `B30R060R`, `B58R070R`, `LEV3456R`) rebuild
byte-identically. Dense section-4 tiles and drawn roads are still open.

## `lev3456.py` — coarse levels 3–5 of `LEV3456R.DAT`

Read directories, records and streams of the whole-database coarse file, count
what each overview level holds, and rebuild a level from decoded records.
Standard library only. `verify`/`rebuild` recompress with stock zlib, so run
them under Python 3.10–3.13 (Python 3.14 often ships zlib-ng, which does not
reproduce the factory streams).

```bash
# Header, directory geometry and content counts per level
python3 tools/lev3456.py info MAPAL001/LEV3456R.DAT

# Decode, re-encode and rebuild levels 3/4/5 (level 5 is strict)
python3.13 tools/lev3456.py verify MAPAL001/LEV3456R.DAT

# Rebuild one level from decoded records; byte-identical on the 2011 file
python3.13 tools/lev3456.py rebuild MAPAL001/LEV3456R.DAT --level 5 -o lev5.DAT
cmp lev5.DAT MAPAL001/LEV3456R.DAT

python3 tools/lev3456.py --selftest
```

Expected `verify` on the EU 2011 file:

```
section 1 level 3: ... opaque 1677, region identical 51040512 B
section 1 level 4: ... region identical 10017280 B
section 1 level 5: records 62, plain 62/62, streams 62/62, opaque 0, region identical 904960 B
section 2 level 4: ... region identical 12794112 B
section 2 level 5: ... region identical 1261568 B
OK (section 1 level 5 strict; levels 3/4 best-effort)
```

See [`../docs/format/map-tiles.md`](../docs/format/map-tiles.md) "LEV3456R.DAT:
coarse levels 3–5".

## `lev3456gen.py` — write coarse-level roads into `LEV3456R.DAT` (M5.16, M5.59)

Splices road shapes for levels 3, 4 and 5 from a JSON extract into a factory
template. The level-3 directory is chosen by the directory box (M5.59).
`placement` checks a generated file without the generator's split: every
changed record is decoded back to lat/lon and must lie on a road of the
extract. `codes` counts record headers that equal the geometric parcel code.

```bash
python3 tools/lev3456gen.py --selftest
python3 tools/lev3456gen.py generate --template LEV3456R.DAT --extract tools/fixtures/m9.18-krotoszyn-lev3456.json -o G.DAT
python3 tools/lev3456gen.py placement --template LEV3456R.DAT --generated G.DAT --extract tools/fixtures/m9.18-krotoszyn-lev3456.json --expect-l3-dir 24
python3 tools/lev3456gen.py codes LEV3456R.DAT
```

## `cerom.py` — CE ROM header, modules and sections

Reads the Windows CE ROM (`ECEC` → `ROMHDR` → `TOCentry`/`e32_rom`/`o32_rom`,
`FILESentry`) from the image or from its first 32 MiB. Stdlib only.

```bash
python3 tools/cerom.py IMAGE romhdr
python3 tools/cerom.py IMAGE modules
python3 tools/cerom.py IMAGE sections Navi.exe
python3 tools/cerom.py IMAGE --image-start 0x3e00200 exports coredll.dll   # B/C need --image-start
python3 tools/cerom.py IMAGE va2file 0x03498d48     # -> 0x007f5f48
python3 tools/cerom.py IMAGE extract OBJDLL.dll -o out/   # raw sections
python3 tools/cerom.py --image-start 0x200200 IMAGE imports Navi.exe   # IAT slots, names from the OFT
# resolve ordinal imports via exporter segments/names in the same image (M1.9):
python3 tools/cerom.py --image-start 0x200200 IMAGE imports Navi.exe --resolve-with 0x3e00200
python3 tools/cerom.py --image-start 0x200200 IMAGE imports Navi.exe --names exports.json
```

`extract` writes raw section bytes; compressed (`0x2000`) sections are not
decompressed yet. `imports --resolve-with`/`--names` resolves ordinals to
`MODULE!export` and lists unresolved slots with reasons.

## `sh4xref.py` — SH-4 literal/call xrefs

Finds code that loads a literal VA and labels call targets via imports/exports.

```bash
python3 tools/sh4xref.py IMG Navi.exe --image-start 0x200200 --to 0x004e7d28
python3 tools/sh4xref.py IMG Navi.exe --image-start 0x200200 --calls 0x004e7b8c
# resolve ordinal import labels the same way as cerom.py (M1.9):
python3 tools/sh4xref.py IMG Navi.exe --image-start 0x200200 --calls 0x004e7b8c \
    --resolve-with 0x3e00200
python3 tools/sh4xref.py --selftest
```

## `callgraph.py` — static call graph of a module (H101, M3.23 core)

**Rebuild any graph made before 2026-11-19 (H112):** the first version decoded
literal-pool words as instructions and reported about 10 % false edges
(C-4620). Imports by ordinal now carry the export's name (`OSMDLL!OSM_TaskSend`).

Nodes are the `.pdata` functions plus called leaves; edges are `bsr`, calls
through a pool literal and import calls (thunks folded into their callers).
A `jsr @Rn` with no literal is counted as unresolved, never guessed.

```bash
python3 tools/callgraph.py --selftest
python3 tools/callgraph.py build IMG256 -o archive/work/navi_eu.json   # ~20 s
python3 tools/callgraph.py callers archive/work/navi_eu.json 0x0041b4f8 --depth 2
python3 tools/callgraph.py reach   archive/work/navi_eu.json 0x004266ec
python3 tools/callgraph.py users   archive/work/navi_eu.json fread,fseek,fopen
python3 tools/callgraph.py path    archive/work/navi_eu.json 0x0041c044 0x00542250
```

The graph file is derived from vendor code: keep it under `archive/`.

## `event_subs.py` — who listens to which object-store event (M9.57)

Lists every call of `OBJ_Event_setPrm` / `OBJ_Event_setPrmForMP` in every
module of a CE segment, with the task, the sub (the `+10` word of the
`0x07d0` message the task will receive) and the object call that follows.
Import stubs come from each module's own import table, so DLLs are covered;
helpers that take the task or sub as an argument are listed once per caller.

```bash
python3 tools/event_subs.py --selftest
python3 tools/event_subs.py archive/head256.img --expect-site 0x003eb99c
python3 tools/event_subs.py archive/head256.img --task 0x011fff58 \
    --handler-table Navi.exe:0x001796f4:6        # table rows without a subscriber
python3 tools/event_subs.py archive/head256.img --sub 11 --json out.json
```

With `--task`/`--sub` the exit status is 1 when no row matches; a negative
needs `--expect-site` (a known site that must be in the census, else exit 2).

## `tile_drop_l3.py` — does the mount keep the tile under a position? (M3.33)

Runs `datask_l3.py`'s mount with hooks on the header check `0x0040acb8`
(EU2011) and prints, per tile header, the box, the section list at `0x800`
and whether a part is missing (status 3, the tile is left and the mount
goes on in box 0). `sections` lists the section lists of a card's tiles
without the firmware.

```bash
python3 tools/tile_drop_l3.py --selftest
python3 tools/tile_drop_l3.py sections --card-image CARD
python3 tools/tile_drop_l3.py run archive/head256.img --card-image CARD --position 65.0,30.0
python3 tools/tile_drop_l3.py third-entry --card-image CARD B60R048R.DAT   # --flip arguments
```

## `lctbl_kind.py` — what the `LCTBL001` kind code (`class_code`) encodes (M4.35)

Tests field 0 of every record as the TMC location type `10000·class +
100·type + subtype`: `census` checks that the reference columns obey the
class (`liner ref` → linear, `area ref` → area, offsets → same class),
`roadclass` compares the `L1.x` subtype with the road class that the syntax
of the road number shows (Czechia, Germany, UK, USA). Both repeat the test
with permuted codes as the control. Read-only.

```bash
python3 tools/lctbl_kind.py --selftest
python3 tools/lctbl_kind.py census LCTBL001.DAT
python3 tools/lctbl_kind.py roadclass LCTBL001.DAT --market eu
python3 tools/lctbl_kind.py kinds LCTBL001.DAT
```

## `lctbl_lookup_l3.py` — the firmware looks a TMC location code up in `LCTBL001.DAT` (M5.60)

Runs the whole lookup of EU2011 `Navi.exe` in PySh4 on a card image: request
`0x14e4` → catalog → B-tree index pages → page directory → zlib page inflated
by `HDL_MapTblTask` → answer `0x14fb`, and compares the returned record with
the model of `lctbl_build.py parse`. `--file` puts a generated file on the
card for the run; `--flip OFF[:XOR]` damages one byte (negative control).
Exit 0 all lookups agree, 1 one does not, 3 blocked.

```bash
python3 tools/lctbl_lookup_l3.py --selftest
python3 tools/lctbl_lookup_l3.py extract --card-image CARD -o /tmp/LCTBL001.DAT   # never commit
python3 tools/lctbl_lookup_l3.py run archive/head256.img --card-image CARD --lookup 2,25,1203
python3 tools/lctbl_lookup_l3.py run archive/head256.img --card-image CARD --file SYN.DAT --lookup 3,25,3604 --lookup 3,25,5
```

## `poi_position_l3.py` — the firmware's POI position arithmetic on factory records (M3.34)

Runs EU2011 `Navi.exe` fn `0x003c032c` (name record → mesh point) and
`STDDLL!STD_MeshPnt_chgMapPnt` (mesh point → 1/512″ map point) in
`sh4fpu.PySh4Fpu`, from the image's own code and import/export tables, on
the name records of a factory (or generated) `POINTnnn` pair, and compares
the result with `point_census.fine_position`. Controls: fine fields
exchanged, the one-unit reading, a class-0 record. Exit 0 ACCEPT, 1
mismatch, 3 BLOCKED (other build). Read-only.

```bash
python3 tools/poi_position_l3.py --selftest
python3 tools/poi_position_l3.py run archive/head256.img --dir /tmp/pt --file POINT010 --count 200
python3 tools/poi_position_l3.py mesh archive/head256.img 0x8b608b60 100 200
```

## `locmap_l3.py` — the firmware's chain from a car position to the `LOC_map` shape walk (M9.66)

Runs, in one PySh4 machine with the FPU engine, EU2011 `Navi.exe`'s own
client: mount (`datask_l3.py`), client init `fn 0x00427a34`, the dispatcher
`fn 0x00427144` with a position message and the request tick, the
data-access task with the request the client sent, the reply handler
`fn 0x0042613c`, and the `LOC_map` receiver `fn 0x00421548`. Prints the
wanted groups, the request, the tile reads, and every load the walk
`fn 0x0041f3dc` makes from the copied record (per instruction, distinct
bytes, loads past the copy window), plus the result table. `--replace`
serves a generated tile, `--patch WORD=VALUE` changes one record word before
the copy, `diff` compares two `--json` results (copy, trace, result).
Exit 0 walk ran, 1 no `LOC_map` message, 3 BLOCKED. Read-only.

```bash
python3 tools/locmap_l3.py --selftest
python3 tools/locmap_l3.py run archive/head256.img --card-image CARD.img --json F.json
python3 tools/locmap_l3.py run archive/head256.img --card-image CARD.img --replace MAPAL001/B48R058R.DAT=G.DAT --patch 58=0x0010 --json G58.json
python3 tools/locmap_l3.py diff F.json G58.json
```

## `point_tree_l3.py` — the firmware's nearest-POI walk on a POINT spatial tree (M3.35)

Runs EU2011 `Navi.exe`'s child loader `fn 0x0040f944`, step
`fn 0x004110dc`, node walker `fn 0x004114dc` and distance `fn 0x00408ea4`
(with the image's `STDDLL.dll`) on the spatial trees of a decoded
`POINTnnn` pair. Per sampled cell it compares the name-record ordinals and
distances the firmware stores with `point_census`'s reading. Controls per
tree: a moved leaf, a `0005` terminator, a cleared leaf flag `0x0800`, a
leaf with a code other than 0/63. The block cache and the search state are
modelled (see the docstring). Exit 0 ACCEPT, 1 mismatch, 3 BLOCKED.
Read-only.

```bash
python3 tools/point_tree_l3.py --selftest
python3 tools/point_tree_l3.py run archive/head256.img --dir /tmp/pt --file POINT010 --tree all --cells 60 --json out.json
```

## `sh4fpu.py` — SH-4 floating point for the PySh4 engine (M3.34)

`PySh4Fpu(PySh4)` adds the FPU instructions the firmware's coordinate code
uses (single and double arithmetic, `fmov` forms, `float`/`ftrc`,
`fcnvsd`/`fcnvds`, compares, `FPUL`/`FPSCR` moves, `fschg`/`frchg`) to
`tools/l3_harness/engine.py`, which stops on them. Python doubles, rounding
to nearest, `ftrc` saturating; `fipr`/`ftrv` and FPU exceptions are not
modelled and stop the run. Import it instead of `PySh4` when a routine
calls into `STDDLL.dll` geometry.

```bash
python3 tools/sh4fpu.py --selftest
```

## `point_census.py` — every byte of a `POINTnnn.DAT` by structure, and the fine POI position (M4.27)

Walks a decoded POINT file from its directory: descriptor records, name
tries, index chains, spatial trees, the phone B-tree and the three page
chains, and reports the bytes of each class and the bytes nothing reached
(0 in all 44 files of EU 2011 and US 2011). `joins` checks the cross
references (spatial leaf ↔ name record, index key ↔ name record, phone key ↔
`INFORMATION` record). `refs` checks the fine position formula
(`fine_position`, inverse `encode_position`) against reference coordinates.
Read-only.

```bash
python3 tools/point_census.py --selftest
python3 tools/point_census.py extract --card-image CARD /tmp/pt   # never commit
python3 tools/point_census.py census /tmp/pt
python3 tools/point_census.py joins /tmp/pt
python3 tools/point_census.py refs --us /tmp/pt_us --eu /tmp/pt_eu --refs docs/experiments/EXP-2026-11-08-M4.8b-poi-refs.tsv
```

## `nk_decomp.py` — decompress ROM sections with the kernel's own routine (H51)

Runs `nk.exe` `DECOMP_SECT 0x88037464` (build B) in the PySh4 engine: no
codec port, no QEMU. `section` decodes one compressed section (`-o` writes the
full `vsize`: stored bytes, then zero BSS), `check` decodes every compressed
section of build A and compares nothing but the return value (compare with
`cerom.py comphdr`), `pdata` decodes a module's function table and says
whether a VA is a function `START`, `INSIDE` one, or in a `GAP` (leaf/data).

```bash
python3 tools/nk_decomp.py --selftest
python3 tools/nk_decomp.py section IMG256 --module Navi.exe --index 1 -o sec1.bin
python3 tools/nk_decomp.py check IMG256                 # 245 OK, ~10 min
python3 tools/nk_decomp.py pdata IMG256 --module Navi.exe 0x0041c7e8 0x0041c7dc  # INSIDE then START
python3 tools/nk_decomp.py check IMG256 --cache         # same, and fills the decode cache
python3 tools/cerom.py --image-start 0x200200 IMG256 decompress --check   # 245 OK (r0 == comphdr), M1.19
```

Decoded bytes are vendor data: keep them under `archive/`, never commit them.

**Library interface (M1.19).** Other tools call `nk_decomp.section_init(data,
MODULE, INDEX)` (the `r0` stored bytes) or `nk_decomp.section_bytes(...)`
(stored bytes + zero BSS to `vsize`); `data = nk_decomp.load_image(PATH)`.
Both go through a content-addressed cache, one file per section
(`<module>.sec<N>.<sha12 of stored bytes+vsize>.bin`) in
`$OSM2LEAF_DECOMP_CACHE` or `archive/work/decomp/`; a decode that returns
`-1` raises `DecompError` and is never cached. `cerom.py decompress` falls back
to this routine when the pure-Python codecs say `UNSUPPORTED` (`--method
kernel` skips them), `rommap.py --init-from-image` maps compressed sections
with their decoded bytes, and `runner.py run cmp_ind_reader` reads
`inflate_mask[17]` from the image (`sec1_table.source: image`).

## `pdata.py` — the function table of every module, and the census (M1.20/H51)

Reads a module's `.pdata` from the e32 exception directory (never a section
index), decoding compressed tables with `nk_decomp`. `table` prints every
record, `fn` classifies a VA `START`/`INSIDE`/`GAP`/`BEFORE`, `gaps` lists
executable ranges with no record and marks the call-target `leaf`s, and
`leaves` is the leaf census. `census IMG [--image-start S]` walks a whole CE
segment in TOC order and prints `module records section compressed` plus a
totals line with the with/without split: `NO-PDATA` means the e32 exception
directory is `(0, 0)` only, while a decode/sort/TOC fault is an `ERROR` row
and exits 2 (a broken table is never reported as "no pdata").
`--check-fixture FILE` compares that live census with the counts-only
`tools/fixtures/pdata_census_2011.json` (exit 1 on drift, 2 on an image-SHA
mismatch) as a fast CI check — the live census, not the fixture, is the
evidence. `where IMG --module M [--try-index N]` prints whether each section
holds the exception RVA and what its bytes parse to (`sorted N` / `UNSORTED`),
so a table outside sec2 (`atlce400.dll`, the B/C `nk.exe`, the updaters) is
shown, not assumed.

```bash
python3 tools/pdata.py --selftest
python3 tools/pdata.py census IMG256 --label A           # 149 modules, 87,530 records
python3 tools/pdata.py census IMG256 --image-start 0x3e00200 --label B
python3 tools/pdata.py where IMG256 --module atlce400.dll --try-index 2
python3 tools/pdata.py fn IMG256 --module Navi.exe 0x004125a8
```

## `va_class.py` — what the loader puts at a VA (H49)

Classifies module VAs as `CODE`, `IAT` (import slot, with `DLL!name`),
`INIT` (stored bytes of a compressed section — the only class that needs
M1.2f), `BSS` (zero at load, written at run time — find the writer), `DATA`
or `OUTSIDE`. Run it before writing "blocked: compressed sec1".

```bash
python3 tools/va_class.py IMG --module Navi.exe --resolve-with 0x3e00200 \
    0x0055d040 0x00d53500 0x0055e000      # IAT memset, BSS, INIT
python3 tools/va_class.py --selftest
```

## `fn_audit.py` — audit cited `fn`/`sub_` VAs against `.pdata` (M1.25/M1.29)

Every cited VA is classified by the module's `.pdata` (via `pdata.py`, never a
byte grammar): `START`, `INSIDE <true start>`, `CORRECTED <true start>`,
`GAP(leaf)` (no record, but a direct caller), `GAP(DATA/UNKNOWN)`, `AMBIGUOUS`
(two builds disagree) or `UNMAPPED` (a generic constant outside every table,
not an error). Corpora: `docs/format/*.md`, `TODO.md`, `targets.json` firmware
entries and `tools/*_l3.py` constants. Exit 1 on any `INSIDE`; `--fix-list`
prints `0x<mid> -> 0x<start>`.

`CORRECTED` is a documented correction, not a failure: a bare VA on a
correction line whose own `→` pair names the same start `.pdata` gives
(`0x00542256 → fn 0x00542250`, `0x003f5fc2`→`0x003f5f48`), or a VA on the
explicit `CORRECTION_ONLY` allowlist whose pinned start still matches the image
(prose whose true start sits on another line). A live `fn 0x…`/`sub_…` label of
the same VA, or a repeated bare VA without its own pair, stays `INSIDE`; the
summary prints `CORRECTED n` and a `correction-only` line names allowlisted
VAs that have no live label left.

A frozen corpus (M1.30) turns the live count into a reviewable artifact:
`--write-snapshot PATH` writes one row per citation
(`file, va, kind, class, true_start, class_sha256`) — **one physical line per
row, no `line` field** (H119) — sorted by `(file, va, kind)` and the row's
canonical JSON, plus the summary and the image SHA-256; `--corpus PATH` audits
that file **with the image**: the frozen part is `file/va/kind` (and a `ctx`
row's paired `correction`), and every stored `class` is re-derived from
`.pdata`, so a hand-edited class fails. Because there is no `line` and the two
files carry `merge=union` (`.gitattributes`), two task PRs that each add a
citation merge as text instead of both re-freezing the snapshot; the summary
is recomputed from the rows at load, so a union merge never has to edit it.
`--corpus` also re-scans the live corpus of the snapshot's own scope by
default (`--no-live-check` skips that offline) and splits the result into:

* clean — the same identity multiset — `CORPUS OK: 0 new / 0 gone / 0 moved`,
  exit 0. A line move is not a change at all (there is no `line` to move), so
  it cannot fail or warn (H119 removed the old `CORPUS DRIFT` line-move class);
* `CORPUS STALE` — an added (`new`) or removed (`gone`) citation, or a verdict
  change at an unchanged `(file, va, kind)` — **exits 1**. This is the failure
  the corpus exists for and it is never weakened.

The comparison is over **occurrences**, not distinct keys: the same
`(file,va,kind)` cited twice is a count of two, so deleting one of the two is
`gone` and adding a duplicate is `new` (both exit 1) (H69).

`--fix-list` in corpus mode runs those checks first and then prints only the
snapshot's `INSIDE` rows. The committed corpus is
`docs/research/fn-audit-corpus-2026-11-16.json`; a diff to it is the review
artifact for the M1.26 gate.

### Refreshing the snapshot (H69, H119)

With H119 a task PR that only **adds** a correct citation usually does not need
to touch the snapshot at all: the union merge keeps both PRs' rows, the gate
re-runs on the merged file and finds `0 new / 0 gone`. A re-freeze is needed
only when the gate prints `CORPUS STALE` (a `new`/`gone` row or a verdict
change), i.e. when the snapshot and the tree really disagree. The rules:

1. **Only an intentional `--write-snapshot` rewrites the file.** Never a CI job,
   never a hook, never `--corpus` (it is read-only). A stale snapshot is a
   finding, not an autofix.
2. **Refresh after the citation edits are final** (e.g. after the task's own
   `TODO.md` citations and `Result:` line are in the tree).
3. **The review artifact is the diff.** Run `--corpus` against the committed
   file first: `CORPUS OK` needs nothing; `CORPUS STALE` means the citation set
   or the image changed and must be explained in the PR. Then write the new
   snapshot and diff it (`git diff -- ...json`): only added/removed row lines
   should move unless the PR says why.
4. **Rows are never deleted to make a gate pass**, and the sort stays
   `(file, va, kind)` then canonical JSON so a refresh diff shows rows, not
   reordering.
5. **Record the old and new SHA-256** (`sha256sum`) and the row/VA counts in
   the refresh EXP; a fresh `--write-snapshot` must reproduce the committed
   file byte-for-byte.

A gate that runs on the snapshot (M1.26) consumes this policy; when a merge
brings two added rows together the gate runs on the merged file, so the
`new`/`gone`/verdict-change rule above is the whole contract.

### `--scope l3`: the standing gate (M1.26)

`--scope l3` widens the audit to the corpora the M9/M3 board cites: the l3
harness `targets.json`, `docs/format/firmware.md`, every
`docs/experiments/EXP-*.md` (parsed only — EXPs are append-only) and the
**code citations** in an **open** `TODO.md` task block. The block uses the
docs discipline, not "every hex token": a live `fn`/`sub_` label, a correction
`ctx` with its own arrow pair, or a documented `CORRECTION_ONLY` pin is cited;
a bare data address, path offset, range, string pointer or US-build start is
skipped (it is not a citation a task can "fix"). `US_BUILD_STARTS` (33 before
M9.61 + the 31 US data-access VAs of `build_targets._DATA_TASK_US`, 64 in all)
are skipped for every kind in both scopes so the EU head never reports a valid
US address as `INSIDE` (the M9.61 `datask_l3.py --build us2011` table is why
the set grew; `python3 tools/build_targets.py --selftest` checks the count). It reports
`NOT SCANNED <reason>` for a corpus whose parser or file is missing, and exits
1 on any `INSIDE` (or an `AMBIGUOUS` whose candidates include one). The whole
l3 citation set is frozen to `docs/research/fn-audit-l3-corpus-2026-11-20.json`
by the same `--write-snapshot` (scope `l3`), because EXPs cannot be edited:
their stale VAs are a register, not a diff to fix. Since H77 both scopes skip
fenced code blocks (```` ``` ```` / `~~~`, any indentation; an unclosed fence, or one whose
body dedents below its opener, hides nothing): a VA quoted in a command or output block is not a citation.
The pre-H77 overlay `fn-audit-l3-corpus-2026-11-16.json` is kept at `main`'s
state when H77 merged (1204 rows, 159 of them fenced, SHA-256 `c80330ac…`); it
is not re-synced after H77 (`--write-snapshot` refuses that name, exit 2).
Re-sync `fn-audit-l3-corpus-2026-11-20.json` instead
(EXP-2026-11-20-H77-skip-fenced-code).

`--corpus BASE --overlay L3` audits both layers and applies the H69 policy
**per source**: each layer gets its own live comparison (`docs` for the base,
`l3` for the overlay) and its own histogram line (`DOCS BASE:` / `L3
OVERLAY:`), so l3 line churn can never fold into the docs `moved` count. A
moved-only change in either layer warns and exits 0; `new`/`gone`/a count
delta/a verdict change in either layer is `CORPUS STALE` and exits 1. A frozen
`INSIDE` in the **overlay** is the register and does not fail the gate (EXPs
cannot be corrected); in the **docs base** a frozen `INSIDE` still fails. An
`AMBIGUOUS` overlay row exercises H72's candidate-set comparison: a live
candidate set that gains an `INSIDE` is a verdict change and exits 1.

```bash
python3 tools/fn_audit.py archive/head256.img              # full report, exit 1 on INSIDE
python3 tools/fn_audit.py archive/head256.img --fix-list   # machine-readable fixes
python3 tools/fn_audit.py archive/head256.img --scope docs \
    --write-snapshot docs/research/fn-audit-corpus-2026-11-16.json
python3 tools/fn_audit.py archive/head256.img --scope l3 \
    --write-snapshot docs/research/fn-audit-l3-corpus-2026-11-20.json
python3 tools/fn_audit.py archive/head256.img \
    --corpus docs/research/fn-audit-corpus-2026-11-16.json \
    --overlay docs/research/fn-audit-l3-corpus-2026-11-20.json --quiet
python3 tools/fn_audit.py --selftest                       # no image needed
```

## `ce_strfind.py` — string search across every CE ROM module

Walks the TOC and searches each module's sections for an ASCII, UTF-16LE or
UTF-16BE needle; reports `module / section / RVA / VA / file offset / context`.
Compressed sections are offered to `cecompress` and listed as `UNSUPPORTED`
when it cannot decode them, so a section is never skipped silently. Use
`--control` for the mandatory positive control.

```bash
python3 tools/ce_strfind.py IMAGE MMAIN --control HDD_INFO.TXT --encoding all
python3 tools/ce_strfind.py --image-start 0x3e00200 IMAGE MMAIN --control HDD_INFO.TXT
python3 tools/ce_strfind.py IMAGE MMAIN --module Navi.exe --json
python3 tools/ce_strfind.py --selftest
```

Exit 0 = at least one hit and every control found; 1 = no hit or a control
miss. The read is capped at 128 MiB (builds A/B/C all live below that), so an
8 GB image is not loaded whole.

## `realcheck.py` — pinned real-image regression

Replays the real-image checks recorded in
[`../docs/experiments/EXP-2026-11-06-H5-pm-review.md`](../docs/experiments/EXP-2026-11-06-H5-pm-review.md)
on the shared `IMG256` slice and prints `PASS`/`FAIL` per check, so a tool that
passes its synthetic self-test but fails on real bytes is caught immediately
(C-1714). Every expected value lives in the `PINS` table in the file; the run
never re-pins itself.

```bash
python3 tools/realcheck.py IMG256              # exit 0 = all PASS
python3 tools/realcheck.py IMG256 --require-image
python3 tools/realcheck.py --selftest
```

It checks, in order: input SHA-256 and size, image A `romhdr` (149 modules / 1
file / `0x01a6` / `0x8cae1000`…`0x8e233c88`), image B `exports coredll.dll`
(1651 names and the C-1710 ordinals: 719 `sprintf`, 1145 `_wfopen`, 1143
`fgetws`, 59 `wcschr`, 66 `wcsncpy`, 1047 `memset`, 1118 `fclose`, 496 `Sleep`,
65 `wcsncmp`), image A `imports Navi.exe` (846 slots),
`comphdr --all` (245 sections, 187 HOLDS / 58 REFUTED / 0 UNPARSED),
`thunks Navi.exe` (846 stubs / 846 slots — currently 0 stubs, so this check is
the `FAIL` that tracks C-1714), the four EXP-50 `sh4xref.py` call sites, and
`cecompress.py probe` on the two `NaviMapCC.dll` sections (0 matches in 205
attempts each).

Exit codes: `0` all PASS, `1` any FAIL, `2` image missing/unreadable (every
check prints `SKIP no image`; `--require-image` turns those into FAILs), `3`
`--update` refused because `--write` was not given. `--update` alone prints a
new table built from the run and writes nothing; `--update --write` is the
deliberate re-pin. `--selftest` builds `cerom.build_synthetic_rom()` and proves
the PASS/FAIL/SKIP classification without vendor bytes.

The image is not in the repository. `IMG256` is the first 256 MiB
(`curl -r 0-268435455`) of
`LEAF_2011-2012_QSD-309-101_navi158_eu.img`; its SHA-256 is pinned in the table.

## `cedecomp.py` — nk.exe ROM section decompressor (M1.2c, verified M8.E1b)

Records the nk.exe (image B, `--image-start 0x3e00200`) `IMAGE_SCN_COMPRESSED`
loader/decompressor chain, **verified on IMG256 LE SH-4 bytes**
(EXP-2026-11-06-M8.E1b, C-2290–C-2293; M8.E1's BE-refutation C-1600
superseded). Loader `fn 0x880385e4` tests `o32_flags & 0x2000` at `0x88038666`
(o32 walk, stride 24); compressed branch → `DECOMP_ALLOC 0x88034d94` then
`DECOMP_WRAP 0x88037590 (src,psize,dest,vsize)` → `DECOMP_SECT 0x88037464`
(form 1/2 framing) → `DECOMP_BLK 0x8803a384` (LZXD-like, `0x8d80805b`, 8-byte
block header). Pure-Python block decode is **not** ported: `decode_section`
raises `UnsupportedDecompression` naming the M8.E1 runtime call target
(`qemu-system-sh4` LE; DECOMP_WRAP needs kernel lock/context stubs, C-2293).

```bash
python3 tools/cedecomp.py info
python3 tools/cedecomp.py --selftest
```

## `cedecomp_run.py` — QEMU+gdbstub ROM decompressor runner (M8.E1, unblocked)

```bash
python3 tools/cedecomp_run.py --selftest
python3 tools/cedecomp_run.py info
python3 tools/cedecomp_run.py probe --image IMG256 [--qemu qemu-system-sh4]
python3 tools/cedecomp_run.py exp49 --image IMG256 --entry 0x88037464
```

Execution framework for calling nk.exe (image B, `0x3e00200`) ROM decompressor
with RAM-only state: `qemu-system-sh4 -M none -cpu sh7785 -S -gdb` (LE SH-4) +
`-device loader` + GDB RSP. M8.E1b verified VAs (C-2290–C-2293); EXP-49 runtime
decode (sec1→0x484/vsize 0x5b8, sec2→0xcc0) and all-245/FILESentry still need
LE QEMU and kernel-context stubs for DECOMP_WRAP (or a direct SECT call with
initialised frame), C-2294. Requires `qemu-system-sh4`. See
EXP-2026-11-06-M8.E1b-nk-decompressor-derive.

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

## `hddinfo.py`

Parse the 72-byte `VER_INFO/HDD_INFO.TXT` block and predict the map-code
verdict with model **M0**. The model is a **HYPOTHESIS** taken from the
firmware comparator chain (`0x6fab2c` → `0x6faeb0` → `0x6fb05c`); no verdict is
validated until the spare-card matrix runs. See
[`docs/format/validation.md`](../docs/format/validation.md).

```bash
python3 tools/hddinfo.py parse root/VER_INFO/HDD_INFO.TXT
python3 tools/hddinfo.py --selftest
python3 tools/hddinfo.py classify SYS.HDD_INFO.TXT root/VER_INFO/HDD_INFO.TXT
python3 tools/hddinfo.py matrix root/VER_INFO/HDD_INFO.TXT /tmp/variants --sweep 0-5
```

Exit codes: `0` success/ACCEPT, `1` DIFFERENT MAP CODE, `2` usage/parse/IO
error. `matrix` calls `hddinfo_variants.py`, keeps every variant length-equal,
and writes a `MANIFEST.txt` with one predicted verdict per variant.

## `diff_years.py`

Read-only differential between two extracted card roots or two raw images:
tree census, `VER_INFO/HDD_INFO.TXT` (and the `0x06000000` copy), common
headers, `DRSTR001.DAT` layout, `MMAIN001` level table, tile inventory and
`0x1ac`/`0x2ac` descriptors, plus SHA-256 hashes.

```bash
python3 tools/diff_years.py root2011 root2014
python3 tools/diff_years.py --image a.img --image b.img --json report.json
```

`--partial` suppresses only a missing `VER_INFO`; `--ignore-dump-artifacts`
suppresses only macOS dump entries. Exit codes: `0` identical, `1` different,
`2` bad source. `--selftest` builds two synthetic roots.

## `header_block.py`

Inspect and validate the `0x180` binary block of the common 512-byte header.

```bash
python3 tools/header_block.py dump FILE
python3 tools/header_block.py class FILE
python3 tools/header_block.py compare A B
python3 tools/header_block.py check FILE
```

Classification uses the UTF-16BE family text plus the `0x1ac` descriptor
signature; a bare `MMAIN`/`REFER` header is reported as `AMBIGUOUS` because the
documented header fields do not distinguish them. See
[`../docs/format/file-header.md`](../docs/format/file-header.md). `--selftest`
builds synthetic headers for all four classes.

## `section4.py`

Parse and re-emit the tile section-4 administrative/place-name index. Only the
parcel words, the `0x0009` type tag and the ISO country are understood, so
`encode preserve` is the supported path and `encode build` refuses records with
names or unmapped bytes.

```bash
python3 tools/section4.py parse SECTION4.bin
python3 tools/section4.py encode preserve SECTION4.bin out.bin
python3 tools/section4.py verify SECTION4.bin
```

Exit code `3` means "grammar not known, refusing to invent bytes". See
[`../docs/format/map-tiles.md`](../docs/format/map-tiles.md).

## `addre.py`

Parse the `REFER001/ADDRE0nn.DAT` address database: the 12-byte name-initial
directory at `0x1108`, the 6-byte cell array at `0x2000`, the `c0`/`c8`
records (coordinate id, `40 XX YY` point tokens, `:N:;:M:` range slots, name
section) and the record-block trailer TOC. Reads the `.cmp`/`.ind` pair
without extracting it.

```bash
python3 tools/addre.py --selftest
python3 tools/addre.py layout  REFER001/ADDRE001.DAT.cmp
python3 tools/addre.py table   REFER001/ADDRE001.DAT.cmp
python3 tools/addre.py cells   REFER001/ADDRE001.DAT.cmp --id A
python3 tools/addre.py records REFER001/ADDRE001.DAT.cmp --limit 5
python3 tools/addre.py stats   REFER001/ADDRE001.DAT.cmp
python3 tools/addre.py trailer REFER001/ADDRE001.DAT.cmp
python3 tools/addre.py verify  REFER001/ADDRE001.DAT.cmp
```

`verify` runs 14 structural checks (index alignment, directory ids, cell
shapes, `c0`/`c8` name rule, name length prefix, range grammar, no unknown
token bytes, trailer/block agreement). `--cell-base` reproduces the
`0x2000` control. The 6-byte cell payload and the point arithmetic are
`UNKNOWN`; the tool prints them raw. See
[`../docs/format/refer.md`](../docs/format/refer.md) and
EXP-2026-11-06-M4.9.

## `imf_check.py`

Validate the intermediate map format (IMF v1, JSON Lines) used between OSM and
the future tile writer, and assign whole `BxxRyyR` cells.

```bash
python3 tools/imf_check.py sample --out sample.imf.jsonl
python3 tools/imf_check.py check sample.imf.jsonl
python3 tools/imf_check.py assign-tiles sample.imf.jsonl --out fixed.imf.jsonl
```

The spec is [`../docs/research/intermediate-format.md`](../docs/research/intermediate-format.md).
`--selftest` exercises every error rule (`E001`–`E022`).

## `rdstm_schema.py`

Hypothesis harness for `RDSTM001.DAT`; no vendor data needed to exercise it.

```bash
python3 tools/rdstm_schema.py scan RDSTM001.DAT
python3 tools/rdstm_schema.py layout RDSTM001.DAT --layout 'link=0:u16:id,4:u32:ref,8:u16:src,10:u16:dst,12:u16:code,14:u16'
python3 tools/rdstm_schema.py join RDSTM001.DAT --lctbl LCTBL001.DAT --code-offset 0xc
```

`scan` ranks block/record framings; `layout` reports reciprocity and pointer
rates; `join` gives an LCTBL hit rate (necessary, not sufficient). No decode is
claimed. See [`../docs/format/rdstm.md`](../docs/format/rdstm.md).

## `rdstm_place.py`

Probes candidate join keys between M4.1 16-byte `RDSTM001` rows
(`ref/src/dst/code`) and tile road identifiers (section 1 link ids, section 2
graph ids, parcels, stream keys). Reports hits, expected rate and a random-key
control; verdict is `NO JOIN` when hits are at chance. M4.16 result: no
segment-specific join found (C-1810).

```bash
python3 tools/rdstm_place.py probe RDSTM001.DAT MAPAL001 --limit-tiles 8 --limit-rows 34
python3 tools/rdstm_place.py --selftest
```

## `profile_validate.py` and `build.py`

Validate a build profile against `profiles/schema.json` and print a dry-run
size estimate; nothing is written yet.

```bash
python3 tools/profile_validate.py profiles/dolnoslaskie-detail.json
python3 tools/build.py --profile profiles/dolnoslaskie-detail.json --dry-run
```

`build.py` without `--dry-run` exits `3` (writer not implemented). Estimates
are labelled and based on documented budgets, not measurements.

## `l3_harness/` — L3 contract layer

```bash
python3 tools/l3_harness/selftest.py
python3 tools/l3_harness/rommap.py convert --report cerom.json --out ghidra-map.json
python3 tools/l3_harness/rommap.py convert --report cerom.json --module Navi.exe   --bss-zero --init-guard --image IMG256 --image-start 0x200200 --resolve-with 0x3e00200   --out ghidra-map-guarded.json   # M9.35: zero BSS + bound IAT + INIT guard
python3 tools/l3_harness/rommap.py convert --report cerom.json --module Navi.exe   --init-from-image --image IMG256 --image-start 0x200200 --resolve-with 0x3e00200   --out ghidra-map-init.json   # M1.19: decoded INIT + zero BSS + bound IAT, no guard
python3 tools/l3_harness/runner.py check --manifest corpus.json
python3 tools/l3_harness/runner.py targets
python3 tools/l3_harness/runner.py run probe-zlib-cmf --input FILE --json
python3 tools/l3_harness/runner.py run NAME --rommap map.json --image FW.img --json
# the US firmware's POI name accessor on a POINT pair (M9.10); --mutate corrupt-len2 is the len2 control
python3 tools/l3_harness/runner.py run poi_record_decode --image archive/us256.img --cmp POINT010.DAT.cmp --ind POINT010.DAT.ind --expect-name "HANA HEALTH CENTER"
python3 tools/l3_harness/runner.py run NAME --rommap map.json --image FW.img   --input-root DIR --json   # M9.28: entry.input_region file source
```

`runner.py run` has two modes. With a target name it runs on the pure-Python
`PySh4` engine: a `synthetic` target (the shipped probe) or a `module` entry, a
function at a VA of a memory map whose bytes come from `--image` (M9.20). A
`blocked` reader stays `BLOCKED`. Without a name, the legacy path needs Ghidra:
it exits `3` (`MISSING_GHIDRA`) when Ghidra is absent, and otherwise runs
`ghidra/l3_run.py` as its one entry script. That script reports `BLOCKED` until
a reader is wired in, and it has not been run under Ghidra. The runner never
reports an unearned pass; exit codes are `0` pass, `1` invalid, `2` usage, `3`
skipped (back end missing), `4` blocked, `5` mismatch. See
[`l3_harness/README.md`](l3_harness/README.md) and
[`../docs/research/l3-ghidra.md`](../docs/research/l3-ghidra.md).

### Module-entry input region (M9.28)

A module entry may declare `entry.input_region` to map caller-supplied or
file-derived bytes at a chosen guest VA, so a reader can consume real input
instead of faulting on its argument pointer:

```json
"input_region": {
  "va": "0x20000000", "size": 97158,
  "bytes_source": {"kind": "file", "path": "page.bin"},
  "provenance": "EU2011 POINT010 0x6e06d0, 97158 B swap16, C-3537/C-4172"
}
```

- Bounds are **exact**: one byte past `va+size` is unmapped. The region is
  refused (`INVALID`) if it overlaps any module block, `stack`, `heap` or the
  IAT trampolines (`0x8C300000`); it is never mapped silently over code.
- `bytes_source.kind` is `file` (read from `--input-root`, or the current
  directory for an absolute path) or `literal` (a synthetic control, at most
  1 KiB). A file must match `size` exactly.
- `provenance` is mandatory. The result carries `input_region` on **every**
  path, including refusals: `va`, `size`, `end`, `kind`, `sha256`, `path`,
  `provenance`.
- Consumption is proven, not assumed: each run also reports `consumed_input`
  and `input_region.reads` (`count`, `first`, `last`, `widths`, `first_pc`,
  `last_pc`), a read watch inside `[va, va+size)` with the loading PC.
- An `r0` outside the entry's `verdict_map` still makes the run `BLOCKED`
  ("no verdict is guessed"): a mapped buffer is pipeline evidence, not a
  reader verdict (`l3_claim: false`).

## `progress_report.py` — L1–L5 progress dashboard (H27/T2)

Aggregates existing sources of truth (`reader-coverage.md`, `claims.md`,
`TODO.md`, tool JSON) into one `progress.json`/`progress.md` view that separates
**udowodnione offline** (L1/L2), **udowodnione przez firmware/L3** (only
non-synthetic `l3_claim` PASS targets, firmware fragments),
**emulator pełnosystemowy** (L4, M8/QEMU, explicit/manual), and
**wymaga auta/stanowiska** (L5, M6 S0–S3, explicit manual). It never promotes
L2 to L3/L4/L5, never auto-passes L4/L5, and requires no vendor data for
`--selftest` or JSON-based aggregation.

**Level mapping (2026-11-09):** L3=firmware fragments, L4=full-system emulator
(M8), L5=bench/car (M6). Before 2026-11-09 L4/L5 were swapped. Schema v2 emits
`l4_emulator` + `l5_car` and keeps `l4` as a backward-compatible alias for car
(L5).

`reader-coverage.md` is parsed only under an explicit matrix-table contract
(header `| # | File type / path |`, fixed 12 leading columns); a contract
mismatch is reported as a problem, never guessed.

```bash
python3 tools/progress_report.py --selftest
python3 tools/l1l2_fixtures.py --json /tmp/opencode/h27-l1l2.json --md /tmp/opencode/h27-l1l2.md --no-stdout-md
python3 tools/l3check.py --build-corpus --json > /tmp/opencode/h27-l3.json
python3 tools/progress_report.py --l1l2-json /tmp/opencode/h27-l1l2.json \
    --l3-json /tmp/opencode/h27-l3.json --l5-status /tmp/opencode/l5.json \
    --json progress.json --md progress.md --no-stdout
```

Schema: `osm2leaf.progress_report/v2` (`schema_legacy` v1). Claims C-2770–C-2779;
see [`../docs/experiments/EXP-2026-11-08-H27-progress-dashboard.md`](../docs/experiments/EXP-2026-11-08-H27-progress-dashboard.md).

## `l3check.py` — L3 rung of the verification ladder

Runs every target declared in `tools/l3_harness/targets.json` through
`tools/l3_harness/runner.py`, on a corpus built by
`tools/l3_harness/corpus.py` (or one supplied with `--corpus`), and prints one
status per target with its reader and claim IDs. It is the L3 counterpart of
`cardcheck.py` (L1) and `l2check.py` (L2).

```bash
# Fresh synthetic corpus in a new temporary directory (kept; path printed)
python3 tools/l3check.py --build-corpus

# A corpus you built yourself (manifest.json is validated before any target runs)
python3 tools/l3check.py --corpus /tmp/opencode/l3-corpus
python3 tools/l3check.py --corpus /tmp/opencode/l3-corpus \
    --target probe-zlib-cmf --json
python3 tools/l3check.py --build-corpus --json /tmp/opencode/l3.json
python3 tools/l3check.py --selftest
```

`--json` takes an optional path: bare `--json` (or `--json -`) prints the
document to stdout, `--json PATH` writes the same document to `PATH`
(atomic, UTF-8).

Statuses and exit codes:

* `PASS` — the engine verdict matched the target's `expect.verdict`;
* `FAIL` — a mismatch, an invalid/missing corpus file, or a target that could
  not run (never silently skipped);
* `SKIP` — the requested `--engine` back end is absent; nothing is claimed;
* `BLOCKED` — the reader has no located entry point in `targets.json`;
  nothing is claimed.

Exit `0` only when every runnable target passed (blocked/skipped targets are
counted and printed, not failed), `1` on a failure or invalid input, `2` on a
usage error, `3` when nothing was runnable. Expected run on the 108-entry
synthetic corpus with no Ghidra/QEMU (2026-11-06):

```
target              reader     entry      claims         RESULT
probe-zlib-cmf      synthetic  synthetic  C-1670,C-1690  PASS
hddinfo_compare     hdd_info   blocked    C-521          BLOCKED
cmp_ind_reader      cmp_ind    blocked    -              BLOCKED
tile_reader         tile       blocked    -              BLOCKED
drstr_parser        drstr      blocked    -              BLOCKED
mapcode_comparator  hdd_info   blocked    C-520,C-528    BLOCKED

counts   pass=1 fail=0 skip=0 blocked=5 runnable=1/6
RESULT: PASS (every runnable target passed; 5 blocked, 0 skipped)
```

A synthetic `PASS` proves the runner/dispatcher path, not that the firmware
accepts a card. `--root` and `--image` are accepted for the ladder interface but
only recorded. Card gate (M9.12, C-2160): `--card OUT.img --factory IMG` diffs
card-relevant files (`VER_INFO/HDD_INFO.TXT`, `DRSTR001.DAT`, `REFER001/*`,
`MAPAL001/*`) and reports per-target `pass`/`fail`/`not-yet-available` (exit 1
on fail; no fake pass for unavailable readers — e.g. POI/M9.10 reported
`not-yet-available`). Differing `.cmp/.ind` pairs use the M9.11 firmware
chunk-decoder adapter when `IMG256`/Navi head is available. See
[`../docs/experiments/EXP-2026-11-08-M9.12-l3check-card.md`](../docs/experiments/EXP-2026-11-08-M9.12-l3check-card.md)
and
[`../docs/experiments/EXP-2026-11-06-M9.8-l3check.md`](../docs/experiments/EXP-2026-11-06-M9.8-l3check.md).

## `sdlock-pico/` and `sdlock_pico_check.py` — SD CMD42 lock tool

RP2040 firmware (C, Pico SDK) that sets, locks, unlocks and clears an SD
card's CMD42 password over SPI; no erase path. Hardware, build and operator
steps: `docs/hardware/sd-blocker-pico.md`.

```bash
python3 tools/sdlock_pico_check.py -v   # host test against a simulated card
# expected last line: sdlock host test: 580 checks, 0 failed
```

## `selftest.py`

Runs synthetic tests for the primitive parsers without any vendor data, and
auto-discovers `--selftest` in `tools/*.py` and in `tools/l3_harness/` (H38).

```bash
python3 tools/selftest.py
python3 tools/selftest.py --list
python3 tools/selftest.py --only cmpind,drstr
python3 tools/selftest.py --only l3_harness        # L3 harness aggregate (bounded/quick)
python3 tools/selftest.py --json
```

Built-in suites cover `cmpind`, `drstr`, `mesh_grid` and the L1 helpers (level
table, common header, LFN, `.cmp` decode, logical listing). L3 harness suites
are reported as `tool:l3_harness*`: the aggregate `tool:l3_harness` runs
`tools/l3_harness/selftest.py` (34 synthetic checks, bounded/quick;
Ghidra/QEMU absent is an honest SKIP inside, never a PASS) and exits non-zero
on harness failure. Tools without a compatible self-test show `SKIP`; a missing
tool is never a failure. Expected: `selftest: OK`.

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

## `mkcard.py` — SD card image builder

Builds an SD card image from a map tree, following the factory layout from a
source image: copies the MBR and all firmware/pre-partition bytes (including the
`0x06000000` HDD_INFO copy checked by `cardcheck.py --image`) verbatim and
rebuilds the FAT32 map partition from the tree (64 KiB clusters, label/root
layout derived from the source).

```bash
# Compare a tree to the source image (no output written)
python3 tools/mkcard.py --from-image IMG --tree ROOT --compare-only -v

# Rebuild the map partition and write an image
python3 tools/mkcard.py --from-image IMG --tree ROOT -o out.img --cardcheck

# Synthetic test (no vendor data)
python3 tools/mkcard.py --selftest
```

For an unchanged tree the output is byte-identical to `IMG` (verified on the EU
2011 reference: SHA-256 unchanged, `cardcheck.py --image` PASS). For a changed
tree, differing byte ranges vs the source are reported and explained
(timestamps, allocation/free-cluster order, FAT/reserved/data-area changes); the
tool cannot reproduce the SD lock state or the card CID.

## `l2check.py` — L2 semantic / golden checks

Checks that a root still round-trips and that the decoded geometry matches a
stored golden profile:

* `DRSTR001.DAT` rebuilt from the tree is byte-identical;
* every `REFER001` pair survives a preserved-stream round-trip;
* five target tiles rebuild byte-identically;
* decoded geometry of four target tiles matches the golden digest;
* a one-vertex tile mutation changes exactly one vertex;
* a same-length POI rename passes `validate_mutation.py`;
* a different-length POI rename passes `validate_mutation.py` and re-parses as
  the same records with only the renamed one changed (2011: POINT032 page
  `0x4200`, +4 bytes).

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

## `verify.py` — cross-year wrapper

Detects the card generation and runs L1 and L2 with the right flags in one
command. For `--image` it extracts the map tree to `archive/work/` for L2
(`--no-l2` avoids the extraction).

```bash
python3 tools/verify.py --root /path/to/root
python3 tools/verify.py --image archive/images/LEAF_2014_EU_QSD-357-101.img
python3 tools/verify.py --image ... --no-l2 --json report.json
```

Behaviour:

* ZE0 2011: golden L2 profile;
* ZE0 2014/2016: `--no-golden --ignore-dump-artifacts`;
* map-only tree: `--partial`;
* QY8x 2019 (`CLA-NAVI06-01` / ZENRIN): `UNSUPPORTED`, exit 3.

Exit codes: `0` pass, `1` validation error, `2` bad source, `3` unsupported
engine. `--strict` treats warnings as errors; `--keep-work` keeps the
extracted L2 root.

## Golden profile

`tools/golden/eu2011.json` stores the reference sample's image hash, tree
census, `DRSTR`/`MMAIN` hashes, selected file hashes and the tile geometry
digests. It contains no vendor data, only hashes and counts. Update it only
when a decoder change is intentional, and record the reason in an experiment.

## `ce_rom_parse.py`

Parse the embedded Clarion/Windows CE ROM segments and print their TOCs.

```bash
python3 tools/ce_rom_parse.py \
  --image archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img \
  --out /tmp/ce-rom-report.json
```

Expected on the EU 2011 sample: five valid SH-4 segments; build A has
`149` modules and `1` file, physical range `0x8cae1000`–`0x8e233c88`, and
resolves names such as `Navi.exe`, `NaviStateCC.dll`, `OBJDLL.dll` and
`STDDLL.dll`.

## `qemu_boot_cmp.py` — is a `-M ze0` boot the same on another QEMU build?

Compares `tools/qemu-ze0/run.sh --workdir` directories (the first is the
reference) by the observables that do not depend on the emulator's own
translation cache: the kernel debug text (one must be a prefix of the
other), the sequence of synchronous traps with their pc (TLB misses and
interrupts excluded), the interrupt counts and the unmodelled-access list.
Exit 0 = same, 1 = different. Used to accept the QEMU 11.1.3 port of the
`ze0` series (TODO M8.A9, C-4321); TLB-miss counts are printed for
information only because they are not reproducible on QEMU 11.x.

```bash
python3 tools/qemu_boot_cmp.py /tmp/w8 /tmp/w11      # verdict: SAME
python3 tools/qemu_boot_cmp.py --selftest
```

## `ce_qemu_probe.py` — boot the CE kernel under stock QEMU

Plays the (on-board) bootloader: copies kernel image B (or C) and app image A
to their physical load addresses, starts `nk.exe` on QEMU's `none` machine with
an `sh7785` (SH-4A) CPU, and lists every unmodelled SoC register access in
first-seen order, the CPU exceptions and the final PC. Needs
`qemu-system-sh4` (`apt install qemu-system-misc`); on QEMU >= 10 it adds
`-d invalid_mem`, where the unmapped-access lines now live (C-4323). See
`docs/research/full-system-emulation.md` and EXP-2026-11-05-37.

```bash
python3 tools/ce_qemu_probe.py IMAGE --seconds 4                       # stops polling 0xffe70808
python3 tools/ce_qemu_probe.py IMAGE --patch 0x88048b70=0900           # skip that poll
python3 tools/ce_qemu_probe.py IMAGE --kernel 0x5200200                # image C
```

Expected with the patch (EU 2011): 50 distinct register accesses, one
`0x180 illegal_instruction` at `pc=0x00005b90`, final PC `0x8803d266`.

## `fetch_image.py` — pinned, resumable vendor-image downloads

The four vendor SD images (and the 256 MiB firmware head `IMG256`) with size
and, where known, SHA-256. Writes to `PATH.part` and renames only after the
size and hash match. A network error keeps the `.part` for the next run; a
failed check deletes it.

```bash
python3 tools/fetch_image.py --list
python3 tools/fetch_image.py --image IMG256 -o archive/head256.img   # ~1 min
python3 tools/fetch_image.py --verify archive/head256.img            # matches EU2011 256M
python3 tools/fetch_image.py --selftest                              # local HTTP fixture, no vendor data
```

EU2016 has no pinned SHA-256 yet: its download is checked by size only.
The host answers 403 to Python's default User-Agent, so the tool sends its own.

## `name_loaders.py` — which firmware function names which map file (M3.28)

Static census of `Navi.exe`: every map-file name string in the first section,
the function whose literal pool loads it or the rodata table it sits in, and
the functions that load each table (`census`); then the callers of the name
resolver `0x0040b358` with the names each can pass and the read requests issued
one call away (`openers`). Needs the image and a graph from `callgraph.py
build`.

```bash
python3 tools/callgraph.py build IMG256 -o g.json
python3 tools/name_loaders.py census  IMG256 --graph g.json
python3 tools/name_loaders.py openers IMG256 --graph g.json
python3 tools/name_loaders.py --selftest
```

EU2011: 60 name strings (52 files, 8 directory copies), 13 resolver callers.
The dynamic half, running an opener on a card, is `vcard_l3.py trace` and
`lookup`. Table and results: `docs/format/firmware.md` "Who names which file",
`docs/experiments/EXP-2026-11-19-M3.28-file-openers.md`.

## `datask_l3.py` — the firmware's map client on a virtual card (M3.25)

Runs the data-access task of `Navi.exe` (EU2011 build A) next to the map-file
task of `vcard_l3.py` in one PySh4 machine and carries the messages between
them. The firmware then mounts the card by itself: it asks for file headers,
tile level directories and data blocks, and its own handlers parse what comes
back. For each completed read the tool prints file, position, length, the
handler the firmware chose and which bytes of the buffer each function loaded.

```bash
python3 tools/datask_l3.py tables IMG256
python3 tools/datask_l3.py mount  IMG256 --card-image CARD.img [--max-reads 7] [--file B28R070R]
python3 tools/datask_l3.py mount  IMG256 --card-image CARD.img --flip MAPAL001/B28R070R.DAT@0x803:0x01
python3 tools/datask_l3.py mount  IMG256 --card-image CARD.img --bytes --json out.json
python3 tools/datask_l3.py mount  IMG256 --card-image CARD.img --position 51.70,17.45 --replace MAPAL001/B48R058R.DAT=OUR.DAT --bytes --json B.json
python3 tools/datask_l3.py diff   A.json B.json [--file B48R058R]
python3 tools/datask_l3.py --selftest
```

`--position LAT,LON` places the car, which decides the `BxxRyyR` tile the
mount reads; `diff` compares two runs read by read (file, position, length,
status, handler, bytes parsed) and prints `SAME` or `DIFFERENT` (M9.13).
`--hide`, `--replace`, `--flip`, `--truncate` change one file of the card as
in `vcard_l3.py`. A full mount of the EU card takes about two minutes. Exit 0
when at least one `MAPAL001` read was parsed, 1 when none, 3 on a missing
model or engine stop. Models (object store, saved settings, memory areas, car
position) are listed in the module; the run says which of them return 0.
Results: `docs/format/firmware.md` "The data-access task",
`docs/format/map-tiles.md` "Reader entry",
`docs/experiments/EXP-2026-11-19-M3.25-tile-reader-entry.md`,
`docs/experiments/EXP-2026-11-20-M9.13-generated-tile-l3.md`.

## `vcard_l3.py` — a virtual card in a virtual unit (M9.44)

Runs the map-file layer of `Navi.exe` (EU2011 build A) in PySh4 with the files
of a card behind the firmware's own `fopen`/`fseek`/`fread` imports. The card is
an extracted tree (`--card-root`) or a raw SD image (`--card-image`, FAT32 read
in place, no extraction). Nothing in the layer is replaced: its init, its mount
state machine, its `DRSTR001.DAT` parser, its request queue, its `.cmp`/`.ind`
decoder and the firmware's zlib all execute. The verdict is the firmware's own
state (`2/2` = mounted), not ours.

```bash
python3 tools/vcard_l3.py boot    IMG256 --card-image CARD.img --tree
python3 tools/vcard_l3.py boot    IMG256 --card-image CARD.img --truncate DRSTR001.DAT@0x800
python3 tools/vcard_l3.py compare IMG256 --card-image A.img --other-root B_ROOT
python3 tools/vcard_l3.py read    IMG256 --card-image CARD.img REFER001/POINT010.DAT --length 0x10000
python3 tools/vcard_l3.py read    IMG256 --card-image CARD.img REFER001/ADDRE001.DAT \
    --replace REFER001/ADDRE001.DAT.cmp=NEW.cmp --replace REFER001/ADDRE001.DAT.ind=NEW.ind
python3 tools/vcard_l3.py sweep   IMG256 --card-image CARD.img --bytes 0x4000
python3 tools/vcard_l3.py --selftest
```

- `boot` prints every open and read the firmware makes while mounting, its
  error-log calls (caller, function number, line number), the recognition status
  it writes and a SHA-256 of the volume table it built.
- `compare` boots two cards and exits 0 only when verdict, state sequence, read
  log, volume table and `MMAIN` buffer are the same.
- `read` asks the layer for a byte range of one file (request record, queue,
  worker, completion message) and compares the bytes with a host-side decode.
  For a file under the `CMP.LST` prefix the firmware opens `X.IND` and `X.CMP`
  and inflates with its own zlib, so this is the rule-13 test for a rebuilt
  `.cmp`/`.ind` pair.
- `sweep` does that for the head and tail of every file in the firmware's
  volume table.
- `lookup DIR/NAME…` runs the firmware's own name lookup (`0x0040b358`) on the
  mounted card and prints the file id, or `not found` (exit 1). The lookup is
  case-sensitive.
- `trace VA --args … --ctx OFF=VALUE` calls one firmware function on the mounted
  card and lists every name it resolves, every read request it makes and the
  card accesses: the way to see which file an opener names (M3.28).
- `--hide`, `--replace PATH=FILE`, `--flip PATH@OFF[:XOR]`, `--truncate PATH@N`
  change one file of the card for one run: the negative controls and the way to
  test a generated file without building an image.

Exit codes: 0 accept / identical / all OK, 1 reject / different, 3 BLOCKED (an
import with no model, an engine stop: no verdict), 2 usage. `IMG256` is the
first 256 MiB of the EU card image (the firmware); the 30 MiB of decompressed
`.data` is cached under `archive/work/`. Limits: EU2011 addresses only; a boot
takes about 9 s, a 64 KiB compressed read about 4 s (PySh4 speed, M9.45); the
read API takes lengths in multiples of 4, so the last `size % 4` bytes of a file
are out of reach. Results: `docs/experiments/EXP-2026-11-19-M9.44-virtual-card.md`.

## `swap_witness_l3.py` — the firmware's own POINT byte swap, equal to `swap16` (M3.11b)

Boots the EU 2011 factory card through `vcard_l3.py`, reads
`REFER001/POINT010.DAT` through the firmware's own request queue and brackets the
completion routine's swap loop (the loop inside `fn 0x00417eac`, C-4641) with
three `on_exec` hooks derived from the routine start (`+0x66` pre-swap snapshot,
`+0x70` iteration count, `+0x86` post-swap snapshot). It shows the loop runs
`length/2` times and the buffer it leaves equals `point_walk_l3.swap16` byte for
byte when request word +20 = 0, and that +20 = 1 never enters the loop.

```bash
python3 tools/swap_witness_l3.py run IMG256 --card-image CARD.img
python3 tools/swap_witness_l3.py run IMG256 --card-image CARD.img --length 0x400
python3 tools/swap_witness_l3.py --selftest
```

Exit codes: 0 PASS, 1 FAIL, 3 BLOCKED (boot rejected or the loop never ran),
2 usage. The head offsets are start-relative, so the tool spells no mid-function
VA. Results: `docs/experiments/EXP-2026-11-20-M3.11b-point-byteorder-2.md`.

## `imgpatch.py` — patch one file inside a card image in place

Writes one file's new bytes into its **existing** clusters of a card image,
without a FAT rebuild, so a byte diff against the input shows only that file's
clusters, its 32-byte directory entry and, on a resize, the FAT/FSInfo entries.
Refuses size changes unless `--allow-resize`; refuses to overwrite the source
image (`-o` must differ). `--dry-run` writes nothing; `--verify` checks an
image against the new bytes. Exit codes: 0 ok, 1 verify mismatch, 2 usage,
3 refused by a guard.

```bash
python3 tools/imgpatch.py --image IMG --file REFER001/POINT010.DAT.cmp \
    --from POINT010.DAT.cmp -o OUT.img
python3 tools/imgpatch.py --verify --image OUT.img \
    --file REFER001/POINT010.DAT.cmp --from POINT010.DAT.cmp
python3 tools/imgpatch.py --selftest      # synthetic image, 46 checks
```

Use it instead of `mkcard.py` when a test must change only the file under test
(M5.13b, M6.5–M6.7). Background: the docstring in `imgpatch.py`.

## `qemu-ze0/` — pinned QEMU for the `ze0` SH-4 machine

Out-of-tree home of the M8 emulator work. No QEMU source is vendored: the
directory holds `build.sh` (fetches the pinned QEMU 11.1.3 tarball, checks its
SHA-256, applies `patches/*.patch`, builds the SH-4 target only and checks that
`qemu-system-sh4 -M help` lists `ze0`), `run.sh` (boots the CE images in a
work directory) and `gdb-ze0.py`. The pin and its SHA-256 are in
[`qemu-ze0/README.md`](qemu-ze0/README.md). Source and build trees go under
`--srcdir` (default `~/.cache/qemu-ze0`), outside the repository.

```bash
tools/qemu-ze0/build.sh --dry-run    # print every command; write nothing
tools/qemu-ze0/build.sh              # fetch, verify, patch, build, check `ze0`
tools/qemu-ze0/run.sh --help         # boot orchestrator (stage F0, M8.A7)
python3 tools/qemu-ze0/mkoverlay.py CARD.img OUT.qcow2   # qcow2 overlay for --sd, no qemu-img needed (M8.C1b)
python3 tools/qemu-ze0/mkoverlay.py --selftest
```

`mkoverlay.py` writes an empty qcow2 v3 file of 8 GiB whose backing file is
the raw card image: QEMU's `sd-card` needs a power-of-two size, the card
image is never written, and `build.sh` builds no `qemu-img`.

## `ze0_sdhost.py` — SD bring-up evidence for `-M ze0` (M8.C10, M8.C1b)

```bash
python3 tools/ze0_sdhost.py inttable archive/head256.img          # OAL interrupt table of nk.exe
python3 tools/ze0_sdhost.py sdtrace  qemu-unimp.log               # SD commands (sdhi-trace=on)
python3 tools/ze0_sdhost.py dmatrace qemu-unimp.log --card CARD.img   # HPB-DMAC transfers vs the card (hpbdmac-trace=on)
python3 tools/ze0_sdhost.py serial   serial.log                   # SD/lock/mount milestones of the debug log
python3 tools/ze0_sdhost.py --selftest
```

`dmatrace --card` exits 0 only when at least one CMD17/CMD18 read was
compared and every one has the CRC-32 of the card image at its block.
Records: EXP-2026-11-20-M8.C10-sd-host, EXP-2026-11-21-M8.C1b-hpb-dmac-model.

Status: `ze0` machine not yet written (M8.A2); until it exists `run.sh` falls
back to stock `-M none -cpu sh7785`. Stages F0–F5 and their gates are in
[`docs/research/full-system-emulation.md`](../docs/research/full-system-emulation.md)
and TODO M8.

## `board.py` — edit `TODO.md` and `claims.md` by line operations (H123)

Every change to the board files is one splice; a guard refuses a write that
drops a task ID or claim ID, moves the line count by more than the edit, or
touches another task block. `resolve` merges a conflicted board file by ID
from the three index stages; `lost` lists IDs present at a ref and missing now
(the local form of H121).

```bash
python3 tools/board.py claim M9.12 --owner task/m9.12-x   # Status: in progress · Owner: …
python3 tools/board.py done M9.12 --result "EXP-…"         # [x], done, Result
python3 tools/board.py add-task block.md                   # end of its stream
python3 tools/board.py add-claims --section "…" --row "| C-… | … | … | … | … |"
python3 tools/board.py archive M1.2e --to docs/research/todo-history-2026-11-21.md
python3 tools/board.py resolve TODO.md                     # during a conflicted rebase/merge
python3 tools/board.py lost --base origin/main             # exit 1 names lost IDs
python3 tools/board.py --dry-run done M9.12 --result x     # print the diff only
python3 tools/board.py --selftest
```

## `todo_check.py`

Lint `TODO.md` board structure: duplicate task IDs, duplicate/overlapping or
malformed `Claims` ranges, missing required fields, invalid Status/Critical,
checkbox/status contradictions, `blocked` without `Unblock`, `done` without
`Result`, cyclic `Depends` refs, and (as warnings) unknown `Depends` refs and
missing Precheck/Scope/Stop on firmware/search tasks. Complements
`claims_check.py`, which validates `docs/research/claims.md`.

```bash
python3 tools/todo_check.py TODO.md      # lint the board (exit 1 on errors)
python3 tools/todo_check.py --json TODO.md
python3 tools/todo_check.py --selftest   # synthetic checks + real TODO parse
```

## `worktree_audit.py` — stale worktrees and branches ahead of `main` (H54)

Joins `git worktree list --porcelain`, `git for-each-ref` and the `TODO.md`
`Status:` lines into one row per non-main worktree and per branch ahead of
`main`: `path · kind · branch|detached · commit · age · locked · task ·
todo status · flag`. A row is `STALE` when a detached tree older than seven
days has a commit that is an ancestor of `main`, or when a branch ahead of
`main` belongs to a task already `done`/`blocked`. Task IDs come from the
branch name only; anything else is `UNKNOWN`.

```
python3 tools/worktree_audit.py            # text report + counts
python3 tools/worktree_audit.py --json     # machine-readable document
python3 tools/worktree_audit.py --prune    # dry run: prints the remove commands
python3 tools/worktree_audit.py --selftest # throwaway git repo, no vendor data
```

`--prune` deletes nothing by itself; `--prune --apply` removes only the stale,
unlocked worktrees. The tool never deletes a branch and never removes or
force-removes a locked tree.

## Conventions

- Read-only. Scripts that write require an explicit output path.
- No hard-coded absolute paths.
- Evidence and format notes live in [`../docs/format/`](../docs/format/); claim
  status lives in [`../docs/research/claims.md`](../docs/research/claims.md).
