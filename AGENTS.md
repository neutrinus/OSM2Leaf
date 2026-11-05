# AGENTS.md

Research repo for generating Nissan Leaf ZE0 (2011–2012) navigation maps from
OpenStreetMap. **Research only** — nothing here has been validated in a car.

All repo content (code, docs, commits) is English. Conversation may be Polish.

## Read first

1. `README.md` — scope, verified findings, documentation index.
2. `docs/research/claims.md` — canonical claim ledger (IDs + status). Trust
   this over prose in other docs.
3. `docs/format/*.md` — per-format notes.
4. `TODO.md` — actionable work; `docs/research/open-questions.md` — unknowns.
5. `tools/README.md` — exact tool commands.

## Repo shape

- No package manager, build system, CI, lint or typecheck. The deliverables are
  docs plus small Python CLIs.
- `tools/` — Python 3.10+, standard library only. Entrypoints are run directly.
- `docs/format/` — on-disk format facts and hypotheses.
- `docs/research/` — claim ledger, sources, open questions.
- `archive/` — git-ignored vendor data. Never commit its contents.
- Working data lives outside the repo; on this machine:
  `/home/marek/projekty/leafre-work/` (`leaf2011.img`, extracted `root/`).
  The reference image SHA-256 is `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`.

## Commands

```bash
python3 tools/selftest.py                 # no vendor data needed; run before committing
python3 tools/cmpind.py verify <REFER001> # expect 194/194 OK on the EU 2011 image
python3 tools/leafimg.py info <image>
python3 tools/leafimg.py header <file>
python3 tools/drstr.py parse <DRSTR001.DAT>
```

There is no other test suite. For a decoder change, run it against a real
sample and state the result in the commit body. Never test a modified image in
a car without a verified backup and a spare SD card.

## Format gotchas that are easy to get wrong

- The common 512-byte header text is **UTF-16 big-endian**, not little-endian.
  Only `0x000`–`0x17f` is text; `0x180` onward is binary.
- `REFER001/*.cmp` is **not** one zlib stream. It is `chunk_count` independent
  zlib streams indexed by `.ind`. Plain `zlib.decompress()` silently returns
  only the first 64 KiB chunk. Use `tools/cmpind.py`.
- `.ind` = `u32 uncompressed_size, u32 compressed_size, u32 chunk_count,
  u32 chunk_size (0x10000), u32 chunk_offset[chunk_count]`. Decompressed
  payloads still include the 512-byte header.
- `DRSTR001.DAT` has **no header**. Node 0 is the root `/` at `0x0000`; the
  EU 2011 image has 40 nodes of 40 bytes, then 324 entries of 32 bytes
  (`40*40 + 324*32 = 11968`). Node fields: `next_index` `+0x14`,
  `parent_index+1` `+0x16`, `entry_count` `+0x18`, `listing_offset` `+0x24`.
  Entry fields: `name[13]`, `type` `+0x16`, `value` `+0x1c` (file size; for a
  directory, recursive subtree total). `0x2f` is `/`, not a count. Older notes
  about a “one-node shift” were a parsing bug; do not reintroduce it.
- `MAPAL001/*.DAT` tiles are **not raster images**. They are a header plus many
  small zlib records. Do not assume a bitmap or a single compressed blob.
- `tools/leafimg.py header` decodes only the text region by design;
  `tools/drstr.py parse` stops at the first listing by design.

## Closest prior art (external, verify before relying)

`https://github.com/albertbm/osm2clarion` documents a closely related Clarion
QY8x format (`CLA-NAVI06-01`, `X08-03-00`) with a tile grid, zlib record tree,
`DRSTR001.DAT`, `REFER001` and `LEV3456R.DAT`. External research claims:

- grid: `lat_min = B_hex * 2/3`, `lon_max = 108 - R_hex`, cell 5.333° × 8°;
- tiles are addressed by index order, not only by filename;
- `VER_INFO/HDD_INFO.TXT` line 1 is the base card code; editing it is reported
  to fix `DIFFERENT MAP CODE`;
- SD lock is a CMD42 password, not file encryption.

These are **leads from research, not verified on ZE0**. Check them against the
EU 2011 sample and record the outcome in `claims.md` before building on them.

## Data, license, safety

- Never commit vendor data: images, dumps, firmware, `.DAT`, `.cmp`, `.ind`,
  `.AGM`, `.TTS`, `.GID`. `.gitignore` also drops `*.img`/`*.7z`. Keep them in
  `archive/` or outside the repo. `git add -f` only for tiny synthetic fixtures.
- Code is GPL-3.0-or-later; OSM-derived data is ODbL-1.0. Do not copy code from
  incompatible projects; link to it.
- Original SD card is read-only: back up, verify hash, test on a spare card.

## Documentation and evidence

- Register every new claim in `docs/research/claims.md` with the next free ID
  and status `VERIFIED`, `OBSERVED`, `HYPOTHESIS` or `UNKNOWN`.
- `VERIFIED` requires a reproducible command/check; every non-obvious claim
  needs a pointer (offset, byte pattern, command or URL). Otherwise it is a
  hypothesis.
- Put format details in `docs/format/`, external links in
  `docs/research/sources.md`, unresolved questions in
  `docs/research/open-questions.md`.
- State the sample and its SHA-256 when a finding depends on one. Negative
  results are useful; record the method and scope.

## Commit style

Small, logical, self-contained commits. Imperative subject ≤ ~72 chars, no
trailing period; prefixes `docs:`, `tools:`, `format:`, `fix:`, `chore:`.
Explain *why* in the body. Never commit binaries, caches or vendor data.
