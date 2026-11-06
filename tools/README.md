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
(1651 names, ordinal 719 = `sprintf`), image A `imports Navi.exe` (846 slots),
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
python3 tools/l3_harness/runner.py check --manifest corpus.json
```

`runner.py run` exits `3` (`MISSING_GHIDRA`) until Ghidra is installed and a
harness script exists; it never reports an unearned pass. See
[`../docs/research/l3-ghidra.md`](../docs/research/l3-ghidra.md).

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
auto-discovers `--selftest` in every other `tools/*.py`.

```bash
python3 tools/selftest.py
python3 tools/selftest.py --list
python3 tools/selftest.py --only cmpind,drstr
python3 tools/selftest.py --json
```

Built-in suites cover `cmpind`, `drstr`, `mesh_grid` and the L1 helpers (level
table, common header, LFN, `.cmp` decode, logical listing). Tools without a
self-test show `SKIP`; a missing tool is never a failure. Expected:
`selftest: OK`.

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

## `ce_qemu_probe.py` — boot the CE kernel under stock QEMU

Plays the (on-board) bootloader: copies kernel image B (or C) and app image A
to their physical load addresses, starts `nk.exe` on QEMU's `none` machine with
an `sh7785` (SH-4A) CPU, and lists every unmodelled SoC register access in
first-seen order, the CPU exceptions and the final PC. Needs
`qemu-system-sh4` (`apt install qemu-system-misc`). See
`docs/research/full-system-emulation.md` and EXP-2026-11-05-37.

```bash
python3 tools/ce_qemu_probe.py IMAGE --seconds 4                       # stops polling 0xffe70808
python3 tools/ce_qemu_probe.py IMAGE --patch 0x88048b70=0900           # skip that poll
python3 tools/ce_qemu_probe.py IMAGE --kernel 0x5200200                # image C
```

Expected with the patch (EU 2011): 50 distinct register accesses, one
`0x180 illegal_instruction` at `pc=0x00005b90`, final PC `0x8803d266`.

## Conventions

- Read-only. Scripts that write require an explicit output path.
- No hard-coded absolute paths.
- Evidence and format notes live in [`../docs/format/`](../docs/format/); claim
  status lives in [`../docs/research/claims.md`](../docs/research/claims.md).
