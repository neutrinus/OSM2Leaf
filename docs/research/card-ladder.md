# The card ladder P0–P4: what each card contains

> **Status:** planning page (M5.38, EXP-2026-11-19-M5.38-card-ladder). It
> restates existing claims and task states and adds one measured count (the
> P1 directory census below). No format fact is new here; a cell that nobody
> has measured says `unknown` and names the task that answers it.
>
> **Two pages, two jobs.** This page says what a card *contains* at each step
> and which inconsistencies the firmware will see. The gate *commands* — every
> row a command with its expected string — are on
> [`docs/format/card-ladder.md`](../format/card-ladder.md) (M5.50). Step
> names are the same on both pages.

"A Poland card" is five different cards. The ladder orders them so that each
step changes one family of files and every earlier step stays true. Region
scale (Dolnośląskie → Poland → Europe) is a separate axis, owned by M7; the
ladder is about *which files* are ours.

| Step | What is ours | Region | State (2026-11-19) |
| --- | --- | --- | --- |
| **P0** | section 1 of one tile: one level-2 `0x2046` directory holds OSM roads | a 0.05° × 0.03° window of Dolnośląskie in `B48R058R` | **built** — card `b0faf119…33237` (M5.30), gates on the format page |
| **P1** | section 1 of the region's tile: every directory over the region | all of Dolnośląskie (1 tile, `contained=1`) | not built — 11 of 20 directories are not writable today (below) |
| **P2** | routing: tile section 2 + `LEV3456R.DAT` + road class | as P1, then Poland (4 tiles) | not built — M5.16 blocked, M4.40 open |
| **P3** | names: tile section 4 + `RDSTM001/LCTBL001.DAT` + `RDSTM001.DAT` | as P2 | not built — no section-4 or LCTBL builder (M5.17) |
| **P4** | search: `REFER001` `POINT`/`ADDRE` (+ the other REFER families) | as P3 | not built — POINT rename only (M5.18/M5.26) |

**Order decision.** M5.38's block proposed P2 = names, P3 = routing. This page
uses **P2 = routing, P3 = names**, because (a) the merged gate page
(M5.50) and the board's critical path already call routing P2 and name
M5.16/M5.36 as its gates, and renumbering a verified page would break its
rows; (b) names hang on section 4 *and* on `ADDRE`/`POINT` keys
(M4.36 links them to the section-4 index), so names and search are closer to
each other than to routing.

**P1 vs the gate page's P1 rows.** The gate page's P1 rows (M5.49) copy the
factory tile verbatim and prove the pipeline carries the region tile unchanged
(delta 0). That is P1's *precondition*, not P1 itself: P1's content is the
region's OSM roads in section 1. When M5.49 lands, the P1 rows that write OSM
data are the next rows of the same table (task M5.53).

The common counts, from the EU 2011 factory tree (480 files; `find FAC -type f | wc -l`):
`MAPAL001` 46 files (45 tiles + `LEV3456R.DAT`), `REFER001` 388, `REFER002` 16,
`SPEECH` 21, `RDSTM001` 2, and one each of `MMAIN001.DAT`, `DRSTR001.DAT`,
`CMP.LST`, `BICON001`, `OPNG`, `TMC`, `VER_INFO`.

## How to read a step

Each step lists three things, as M5.38 asked:

- **Generated** — files (or parts of files) whose bytes come from OSM.
- **Copied** — files kept as factory bytes. Verdicts per family are from
  EXP-2026-11-08-M3.17 and [`reader-coverage.md`](reader-coverage.md).
- **Inconsistencies the firmware will see** — a generated part that a copied
  part does not agree with, and the task that finds out, *in emulation*, what
  the firmware does about it. These are known wrong behaviours, stated so they
  are not mistaken for bugs.

The **gate** of a step is its L1/L2 checks plus the L3 targets that exist for
its generated files ([`reader-coverage.md`](reader-coverage.md) column "L3").
A generated file with no running L3 target is **ungated** (rule 13: the
firmware has not read it). A target that exits `BLOCKED (4)` is not a gate.

## P0 — one OSM directory in one tile (built)

- **Generated:** `MAPAL001/B48R058R.DAT` section 1, level-2 directory
  `(76,940)` kind `0x2046` — 88 OSM ways from `--osm-bbox 16.40,51.10,16.45,51.13`
  (EXP-2026-11-18-M5.44); `DRSTR001.DAT` directory values (size/offset of the
  grown tile). Card: EXP-2026-11-19-M5.30, diff 586 ranges, outside 0.
- **Copied:** the other 478 files; in the tile: every level-1 directory,
  sections 2 and 4, the box/level tables outside the spliced directory.
- **Inconsistencies:**
  1. Level 2 shows OSM roads in `(76,940)`; the level-1 directory under the
     same area is factory (M5.44 compares level 1, never regenerates it). The
     unit will draw different roads at different zooms. What the renderer does
     at the level switch: **unknown** — M3.25 (tile reader run) / M4.40.
  2. Section 1 has roads section 2 does not know: the route graph is factory,
     so a route may follow roads that are not drawn. Firmware behaviour:
     **unknown** — M4.40 (section 2 from its reader), M9.13 (`tile_reader`).
  3. Search, names and POIs are the factory's (European data on a Polish
     road set). Expected wrong, not a bug.
  4. `DRSTR001.DAT` points at a grown, relocated tile chain. Whether the
     file layer opens it: **unknown** — M9.44 (virtual card, file level).
- **Gate:** L1 `cardcheck --image` PASS, `imgpatch --check-diff` outside 0,
  `7z t`; L2 `l2check --semantic-tiles B48R058R.DAT` PASS (format page §P0,
  rows 1–10; pinned for QA by M5.40). L3: tile → `tile_reader` BLOCKED (4),
  **ungated**; `DRSTR001.DAT` → `drstr_parser` BLOCKED (4), **ungated**.

## P1 — every section-1 directory over the region

- **Generated:** `B48R058R.DAT` section 1, every directory whose box
  intersects the profile bbox `14.0,49.9,17.9,51.9`; `DRSTR001.DAT`. Measured
  on the factory tile (`e9c9cb22…ff52`, EXP-2026-11-19-M5.38):
  **20 section-1 directories** intersect — level 1: 5 `0x2046` (spliceable)
  + **11 preserve-only** (`0x2146` ×5, `0x2246`, `0x2346` ×2, `0x2546`,
  `0x2646`, `0x2946`); level 2: 4 `0x2046`. Today's writer can fill **9 of 20**.
  The 11 are refused by `tilewriter` (`PRESERVE_ONLY_DIR_KINDS`, M5.22/C-3054).
  **Update (M5.53, EXP-2026-11-20-M5.53-wide-rows):** `0x2n46` is a `0x2046` directory
  with n wide rows (C-5270); `tilewriter` now splices into `0x2146` (the five
  `0x2146` boxes are classified spliceable, **14 of 20**; all five splice with
  `verify_factory` OK in the pair review), and a splice that leaves no
  sub-record turns the directory into `0x2046`. The other 6 (`0x2246`,
  `0x2346` ×2, `0x2546`, `0x2646`, `0x2946`) parse with the same model but are
  still preserved (follow-up M5.54).
  **Update (M5.54, EXP-2026-11-20-M5.54-wide-kinds):** those 6 are spliceable
  too (**20 of 20**); each was spliced end to end through `one_tile_pipeline`
  with every sub-record parcel written, and each turned into `0x2046`.
- **Copied:** sections 2 and 4 of the tile, `LEV3456R.DAT`, all of
  `REFER001`, `RDSTM001`, `MMAIN001.DAT` and the asset families.
- **Inconsistencies:** P0's 2–4 for the whole region, plus:
  1. If P1 ships with only the 9 writable directories, the region is a
     patchwork: OSM roads in 9 boxes, factory roads in 11. That is a
     *partial* P1 and must be called so (task M5.53 makes the 11 writable).
  2. The overview levels 3–6 (`LEV3456R.DAT`) still draw factory roads over
     OSM detail. Firmware behaviour at the zoom switch: **unknown** — M9.18.
- **Gate:** P0's gate over the region; L2 `l2check --semantic-tiles` on every
  changed directory; the pipeline precondition (factory tile carried with
  delta 0) is M5.49 (format page §P1, `NOT RUN — M5.49`). L3: tile
  **ungated** (`tile_reader` BLOCKED, M9.13/M3.25).

## P2 — routing

- **Generated:** tile section 2 (route graph) for every P1 directory;
  `MAPAL001/LEV3456R.DAT` sections for levels 3–6 (M5.16); the road-class
  table (M5.3, golden M5.36); border connectivity when the region grows past
  one tile (M5.5). Poland is 4 tiles (`contained=0 intersects=4`).
- **Copied:** section 4, `REFER001`, `RDSTM001`, assets.
- **Inconsistencies:**
  1. Section 2's records must point into section 1's roads; the link key is
     **unknown** — M4.39 (route-link id), M4.40 (grammar from the reader),
     M4.23/M4.24 (regulation/part-b records), M4.3 (turn restrictions).
  2. Factory names (section 4) and TMC (`RDSTM001`) name road ids that no
     longer exist. What the unit shows for a route step: **unknown** — M4.36.
- **Gate:** L2 `tile_graph_roundtrip`/class golden (M5.36, M5.37) — not
  written; `lev3456.py verify` (M5.16, blocked). L3: section 2 and
  `LEV3456R.DAT` have **no target** — **ungated** (M9.18; reader-coverage G8).
  Format page §P2 rows are `NOT RUN — M5.16/M5.36`.

## P3 — names

- **Generated:** tile section 4 (admin/place-name index; `section4.py build`
  refuses today), `RDSTM001/LCTBL001.DAT` (M5.17), `RDSTM001/RDSTM001.DAT`
  (M5.19; TMC location records — M3.17 verdict *generate*).
- **Copied:** `REFER001`, `TMC/reception.dat`, assets.
- **Inconsistencies:**
  1. `REFER001` `POINT`/`ADDRE` still carry factory name keys into a new
     section 4 — **unknown** what search shows — M4.36.
  2. TMC location codes from `RDSTM001.DAT` must place on OSM roads —
     M4.16/M4.16b/M4.16d; class codes in `LCTBL001` — M4.29/M4.35/M4.31.
- **Gate:** L2 none for section 4 or LCTBL yet. L3: section 4 →
  `tile_reader` BLOCKED, **ungated**; `LCTBL001.DAT` → M9.15 planned,
  **ungated**; `RDSTM001.DAT` → no target, **ungated** (reader located
  `0x003bc960`, EU2011).

## P4 — search

- **Generated:** `REFER001` `POINT0nn`/`ADDRE0nn` (66 + 66 files; M5.18,
  M5.26, M5.32), then the families with no writer: `INTER` (66), `FRWAY` (52),
  `ICADM` (66), `ZIPFR` (2). `ZCODE`/`ICODE`/`COORD` are *copy-eligible* for
  an EU-base card (M3.17) until a reader says otherwise. The `.cmp`/`.ind`
  container is written by `cmpind_writer.py`.
- **Copied:** `REFER002` (EU EV layer), assets.
- **Inconsistencies:** copied `INTER`/`FRWAY` reference factory road ids
  (M4.16c); POI coordinates vs OSM (M4.8b, M4.28); bit-packed `POINT` pages
  (M4.27, M4.37).
- **Gate:** L1/L2 `cmpind` round trip; L3: container → `cmp_ind_reader`
  **PASS** (EU2011 and US2011, M9.11/M9.32) — the only running L3 gate on the
  ladder; `POINT` walk runs on the US page (M9.10, M9.41, not yet an evidence
  row); `ADDRE`, `ZCODE`/`ICODE`/`COORD` → M9.15 planned, **ungated**;
  `INTER`/`FRWAY`/`ICADM`/`ZIPFR` → no target, **ungated**.

## tooling

Work that serves every step: the L3 engine and harness (M9.24, M9.33, M9.36,
M9.45, M9.49, M9.50, M9.2), the card-level gates (M9.12, M9.31, M9.16,
M9.17), the one-command build (M5.15, M5.35) and this page (M5.38).

## Step tags on the board

Every open M4/M5/M9 block in `TODO.md` carries one line `  - Step: P0…P4` or
`  - Step: tooling`: the **lowest** step whose generated file or gate the task
serves. The board view, grouped by step (`*` = critical):

```bash
python3 tools/card_ladder.py steps --check
```

## Pending tags

Blocks held in an open PR by their owner (collision rule): the step is
recorded here instead of in the block, and moves into the block when the
owner's PR merges. `card_ladder.py steps --check` reads this table and fails
on a row whose block is already tagged or closed (stale).

| ID | Step | Why not in the block |
| --- | --- | --- |
| M4.16b | P3 | open PR #260 |
| M4.39 | P2 | open PR #263 |
| M5.11 | P1 | open PR #264 |
| M5.26 | P4 | open PR #265 |
| M5.49 | P1 | open PR #247 |
| M9.14 | P0 | owned by a parallel thread (waits on M9.36) |
| M9.17 | tooling | owned by a parallel thread (waits on M9.36) |
| M9.33 | tooling | open PR #246 |
| M9.36 | tooling | owned by a parallel thread |
| M9.41 | P4 | open PR #248 |
| M9.44 | P0 | open PR #280 |
| M9.45 | tooling | open PR #288 |
| M9.49 | tooling | open PR #286 |
| M9.50 | tooling | open PR #287 |
