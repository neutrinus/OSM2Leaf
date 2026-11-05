# Roadmap and confidence gates

> **Last updated:** 2026-11-05. Current position: Gate 0 is the primary path
> (firmware RE defines the data contract); Gate 2 passed, Gate 3 passed for
> all five target tiles.

**Decision:** firmware RE is prioritized. The reader code tells us how the
format is consumed, which is more valuable for the compiler than guessing from
bytes alone. Hardware access is currently unavailable (2026-11-05), so the
dynamic break and card matrices are deferred; the static vtable/section
reconstruction continues.

Principle: **two independent sources must agree** before we trust a format.

1. **Data archaeology** — inspecting the card gives a hypothesis about the
   structure.
2. **Firmware RE** — the reader code tells us how the structure is consumed.
3. **Round-trip** — if we can unpack and repack a layer, the tooling proves we
   understood it.

Only after those gates do we build the OSM compiler.

## Gate 0 — format model converged

For each format area, we need either:

- a data-side decode **and** a firmware cross-check (reader function, table
  size, decompressor call), or
- an explicit `UNKNOWN` with a planned experiment.

Current status:

| Area | Data side | Firmware side |
| --- | --- | --- |
| `.cmp`/`.ind` | verified | reader path partially found (`0xc438a4` opens `REFER001`) |
| `DRSTR001.DAT` | verified | opened by media manager; runtime use unproven |
| Tile grid/stream keys | verified | string pool references `MESH_ID`/`DIVID`; reader not decompiled |
| Tile payload grammar | all five targets round-trip byte-identically; roads + names decoded; section 4 classified as an admin/place index; streaming decoder works | not yet mapped |
| ADDRE/POINT/ZCODE | mostly decoded; POI↔ADDRE ids shared | not yet mapped |
| Firmware addressing | 175-method vtable is **iPodCC**, not NaviStateCC; `0x2e00eb8` is a shared COM helper; no NaviStateCC vtable | next is the writer/initializer of `0x1d0f8a8`; if absent, static is closed |
| Map code/activation | text/market hypothesis | launcher strings found; check not decompiled |
| Checksums | no per-file checksum found | `SUM4`/updater formulas reproduced; FAT not covered |

**Exit criterion:** every critical area has a data test and a firmware
cross-check, or is explicitly marked open.

## Gate 1 — uncompressed layer round-trip

Targets:

- `DRSTR001.DAT` (writer already reproduces the 2011 file byte-for-byte)
- `MMAIN001.DAT`
- common 512-byte / `0x5d6` headers
- `REFER002` uncompressed files
- uncompressed index areas in `ADDRE`

**Criterion:** unpack → repack → **byte-identical SHA-256**.

This is the strongest and cheapest proof.

## Gate 2 — compressed container round-trip

**Status:** passed for preserved streams (194/194 byte-identical). Full
recompression is byte-identical with stock zlib 1.3.1; zlib-ng requires
preserved streams.

Targets:

- `REFER001/*.cmp` + `.ind`
- inner zlib pages inside REFER payloads

Two levels:

1. **Preserved-stream round-trip:** if content is unchanged, keep the original
   compressed streams; output must be byte-identical.
2. **Semantic round-trip:** if content changed, recompress and require
   `decode(repack(x)) == x`, stable chunking and valid `.ind` sizes.

**Caveat:** byte-identical recompression is not guaranteed across zlib
versions/settings. Do not promise it; either preserve streams or document the
exact encoder parameters.

## Gate 3 — tile round-trip

**Status:** passed for all five targets, including dense `B30R048R`
(byte-identical). Roads decode/render; section-4 content and road attributes
are open.

- Enumerate all inner streams with their keys.
- Preserve unchanged streams; re-encode changed ones.
- **Criterion:** unchanged tile → byte-identical; changed tile → same keys,
  same inventory, same viewer output for unchanged blocks.

This depends on Gate 0 (tile grammar) and unlocks the viewer and geometry
writer.

## Gate 4 — whole-image round-trip

Rebuild the card:

- MBR + FAT32 partition + pre-partition firmware area + TFAT16 tail.
- Keep `HDD_INFO`, `DRSTR`, sizes and tile order consistent.

**Criterion:** payload-identical (same file hashes and boot sectors). A full
image SHA-256 may differ because FAT metadata (timestamps, serial, allocation,
file order) is not semantic. Define and document the canonical image.

## Gate 5 — activation / checksum confidence

From firmware:

- confirm whether the unit checks map content at runtime (none found
  statically so far);
- identify the exact `DIFFERENT MAP CODE` input (line 1 vs `0x06000000` copy
  vs NAND record);
- confirm `SUM4`/updater coverage (already reproduced; FAT excluded).

**Criterion:** we can explain every rejection path we intend to hit.

## Gate 6 — hardware mutation

- whole-card clone on a spare 16 GB SDHC;
- no-op recompression control;
- same-length POI rename;
- map-code field test.

**Criterion:** the unit accepts the no-op control and shows the renamed POI,
or we learn exactly which check rejects it.

## Gate 7 — OSM compiler

Only after Gates 0–6:

- profile validator + `tools/build.py`;
- OSM encoder for roads/names/addresses/POIs;
- whole-tile selection;
- viewer/validation loop;
- card image writer.

Buildings/landuse/water remain out of scope until a polygon record type is
proven.

## What not to do yet

- Full-system QEMU (not the critical path; see
  [`feedback-loop.md`](feedback-loop.md)).
- Full firmware decompile before the section table.
- OSM encoder before the format gates.
- Buildings/forest/water before a polygon record is proven.
