# AGENTS.md

Research repo for generating Nissan Leaf ZE0 (2011–2012) navigation maps from
OpenStreetMap. **Research only** — nothing here is validated in a car, and
hardware access is currently unavailable.

All repo content (code, docs, commits) is English. Conversation may be Polish.

## Read first

1. `README.md` — scope, verified findings, documentation index.
2. `docs/research/claims.md` — canonical claim ledger. Trust it over prose.
3. `docs/format/*.md` — current per-format knowledge.
4. `TODO.md` — active work; `docs/research/roadmap.md` — gates;
   `docs/research/open-questions.md` — unknowns.
5. `tools/README.md` — exact commands and expected output.

## Repo shape

- No package manager, build system or CI. Deliverables are docs plus small
  Python CLIs; run entrypoints directly.
- `tools/` — Python 3.10+, standard library only. `tools/ze0-viewer/` clones a
  pinned `osm2clarion` via `setup.sh` (git-ignored vendor tree).
- `docs/format/` — living format knowledge.
- `docs/experiments/` — append-only experiment records.
- `docs/research/` — claims, roadmap, protocols, comparisons.
- `profiles/` — user-selectable build profiles (JSON; whole tiles only).
- `archive/` — git-ignored vendor data. Never commit its contents.
- Working data lives outside the repo; on this machine
  `/home/marek/projekty/leafre-work/` (`leaf2011.img`, extracted `root/`).
  Reference image SHA-256:
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`.

## Verification ladder

Run in this order for a data/code change:

```bash
python3 tools/selftest.py                  # synthetic, no vendor data
python3 tools/cmpind.py verify <REFER001>  # expect 194/194 OK
python3 tools/cardcheck.py --root <root>   # L1 structural: expect PASS
python3 tools/l2check.py --root <root>     # L2 round-trip + golden: expect PASS
python3 tools/verify.py --root <root>      # cross-year wrapper for both
```

- `cardcheck.py --image` adds MBR/FAT checks and the `0x06000000` copy.
- `--partial` for map-only trees, `--ignore-dump-artifacts` for 2016/2019
  images; keep them explicit.
- `l2check.py --cmp-limit 20 --no-tiles` for a fast check;
  `--update-golden` only after an intentional decoder change, never to make a
  failing run pass.
- Tile-level check: `cd tools/ze0-viewer && ./setup.sh && python3 harness.py
  verify <tile>`. Expect byte-identical for `B28R070R`, `B30R060R`,
  `B58R070R`, `B30R048R`, `LEV3456R`.
- Every verification is pinned to a sample SHA-256; record the result in the
  commit body or the experiment record.

## Format facts agents get wrong

- Common header text is **UTF-16 big-endian**, only `0x000`–`0x17f`; `0x180`
  onward is binary.
- `REFER001/*.cmp` is **not** one zlib stream: `chunk_count` independent
  streams indexed by `.ind`. `zlib.decompress()` silently returns only the
  first 64 KiB chunk.
- `.ind` = `u32 uncompressed, u32 compressed, u32 count, u32 chunk_size
  (0x10000), u32 offsets[count]`. Payloads keep the 512-byte header.
- `REFER002` has **16 files**, not 194; it is a separate EV/charging layer.
- `DRSTR001.DAT` has **no header**: root `/` at `0x0000`, 40-byte nodes, then
  32-byte entries (2011: `40*40 + 324*32 = 11968`). Entry `value` is logical
  size for `.cmp`, **on-disk** size for `MAPAL001` tiles, recursive total for
  directories. `0x2f` is `/`, not a count.
- `MAPAL001` has **45** `BxxRyyR.DAT` + `LEV3456R.DAT`; not raster. B/R are
  hex: `lat_min = int(B,16)*2/3`, `lon_max = 108-int(R,16)`, 5.333° × 8°.
  Stream keys: `A = 32768 + lat*192`, `B = 52736 + lon*128`, plus a table tag.
- `COORD001` is a 33-entry region-bbox table at `0x1010`, not a point list:
  `lat = (x-32768)/192`, `lon = (y-52742)/128`. The same formula covers
  `ADDRE`/`POINT` ids; `ADDRE`/`POINT` share ids (POI↔address join is by
  street + house number).
- Tile **section 4 is an administrative/place-name index**, not geometry.
  Road names come from the odd partner record's names section.
- The `0..2047` coordinate bound is a runtime/bit-packed constraint, not a
  plain-u16 storage rule; raw payloads contain larger `u16` values.
- Use `tools/mesh_grid.py`, `tools/cmpind.py`, `tools/cmpind_writer.py`
  instead of re-deriving these.

## Writing data back

- **Unchanged file:** preserve original streams (or copy the pair) —
  byte-identical on any machine.
- **Changed file:** recompress only 64 KiB chunks containing changed bytes,
  keep the rest verbatim, rebuild `.ind` offsets.
- **New/whole-file rewrite:** stock zlib 1.3.1, level 6, wbits 15, memLevel 8,
  default strategy. zlib-ng (often Python 3.14) reproduces **none** of the
  factory streams. Check the fixtures in `docs/format/cmp-ind.md` first.

## Firmware: do not redo these dead ends

Firmware RE is the primary path, but static address recovery is **closed**:

- the ROM is **pre-bound** (imports stripped); no import descriptor names the
  thunks;
- there is **no XIP/section table** in the image; `ECEC`/`NKOK` are container
  metadata;
- `module_scan` `(file_base, va_base)` pairs are wrong for most modules;
  the VA map is **not injective** (`0x0367b180` is both a `jsr` target and a
  string);
- `0xc438a4` does **not** open `CMP.LST` (it is a stats formatter); map
  filenames have zero literal references;
- `+0x02200000` is **not** the map code delta; the per-instruction table gives
  a `0x02b0xxxx` band;
- `NaviStateCC` is a COM DLL; its vtable is built at runtime and no static
  vtable contains the fd methods (`0xc42520`, `0xc426a4`, `0xc438a4`);
- `0x6faf30` is a Bluetooth/OPP handler, not the reader.

Map-code check is numeric `Sys[0x%x]` vs `SD[0x%x]` for `manufacturer_id`,
`userdata_type` (range `0..5`) and `destination_id`; comparator chain at
`0x6fab2c` → `0x6faeb0` → `0x6fb05c`, data delta `0x02800000`. The
`HDD_INFO` parser sits behind a runtime COM object.

Next reader step is **dynamic**, not static: see
`docs/research/dynamic-break-guide.md` (break on `MAL_DataVol_getOffset`,
then fd methods, then fd thunks). Do not propose another static module-base
search without new relocation evidence.

## Documentation and evidence

Three layers, each with one job:

| Layer | Location | Rule |
| --- | --- | --- |
| Current knowledge | `docs/format/*.md` | living: best answer today |
| Experiment log | `docs/experiments/EXP-*.md` | append-only: never rewritten |
| Claim ledger | `docs/research/claims.md` | every claim has ID, status, evidence |

Flow: `format doc → claim ID → EXP record → tool command`.

- New experiment: copy `docs/experiments/TEMPLATE.md`, name
  `EXP-YYYYMMDD-NN-slug.md`.
- Record sample SHA-256, exact commands, raw observations, then
  interpretation. Never mix observation and interpretation.
- Statuses: `VERIFIED` (reproducible check), `OBSERVED`, `HYPOTHESIS`,
  `UNKNOWN`.
- When a result changes knowledge, update the format doc and `claims.md` in the
  same commit.
- **Retraction rule:** never delete a claim row. Mark it `RETRACTED` (or
  `VERIFIED (retraction)` for a proven negative), keep its ID, and add a new
  claim with `Supersedes: C-xxx`. Correction experiments set
  `Supersedes` / `Superseded by`.
- External links → `docs/research/sources.md`; unknowns →
  `docs/research/open-questions.md`; loose threads → `TODO.md`.
- Negative results are first-class; record the method and scope.

## Data, license, safety

- Never commit vendor data: images, dumps, firmware, `.DAT`, `.cmp`, `.ind`,
  `.AGM`, `.TTS`, `.GID`. `.gitignore` also drops `*.img`/`*.7z`. Keep them in
  `archive/` or outside the repo; `git add -f` only for tiny synthetic
  fixtures.
- Code is GPL-3.0-or-later; OSM-derived data is ODbL-1.0. Link to incompatible
  projects instead of copying code.
- Original SD card is read-only: back up, verify hash, test on a spare card.
- Hardware access is currently unavailable, so card matrices and dynamic
  breaks are deferred; do not present them as ready next actions.

## Commit style

Small, logical, self-contained commits. Imperative subject ≤ ~72 chars, no
trailing period; prefixes `docs:`, `tools:`, `format:`, `fix:`, `chore:`.
Explain *why* in the body. Never commit binaries, caches or vendor data.
