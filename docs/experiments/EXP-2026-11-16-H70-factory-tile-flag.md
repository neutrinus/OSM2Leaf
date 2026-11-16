# EXP-2026-11-16-H70-factory-tile-flag: wiring `--factory-tile` into the one-tile pipeline

- **Status:** done
- **Date:** 2026-11-16
- **Sample:** EU2011 factory tile `MAPAL001/B48R058R.DAT` from the extracted
  root `/home/marek/projekty/leafre-work/m5.29-factory-root`, SHA-256
  `e9c9cb2236f6b53ad4fe9687a18a351afe80a46a63c0a1f18dc46d6c8af3ff52`
  (289,319,168 B). It is supplied through `--factory-tile` from a tiny stub
  root (`/tmp/opencode/h70-stub-root`, three placeholder files) that has **no**
  `MAPAL001/` directory, so the run cannot fall back to the derived path. The
  selftest sample is a synthetic tile built by `tilewriter.make_factory`. No
  vendor bytes are committed.
- **Tools:** `python3 3.13`, `tools/one_tile_pipeline.py`,
  `tools/tilewriter.py` (`make_factory`, `cell_db_bounds`),
  `tools/ze0-viewer/tools_ze0/clarion_tile.py` (`read_tile`)
- **Claims:** C-3910, C-3911, C-3912, C-3913, C-3914
- **Supersedes:** none
- **Superseded by:** none

## Question

Was `one_tile_pipeline.py --factory-tile` (declared at argparse, never read)
made to select the tile, and does that selection still bind the tile to
`--cell`?

## Hypothesis

Wiring the flag (option A in the task) is cheaper and safer than deleting it:
`--factory-tile PATH` becomes the template instead of
`FACTORY_ROOT/MAPAL001/<cell>.DAT`, and the same
`_factory_tile_provenance`/`_factory_tile_cell_binding` check (H67) runs on the
supplied tile. Deleting it (option B) would also satisfy the Done-when, but it
removes the only way to keep a factory root whose own `<cell>.DAT` is absent or
replaced, without changing `tilewriter` or the `0x2146` corridor.

**Falsifier:** a supplied tile is still ignored (the output/`factory_tile`
field names the root's derived path); or another cell's supplied tile is
accepted as `factory-tile-parsed`; or the honest `B48R058R` run's
`factory_tile_sha256`/`tilewriter_rc=2` changes.

## Inputs

| Item | Value |
| --- | --- |
| Factory tile (supplied) | `…/m5.29-factory-root/MAPAL001/B48R058R.DAT`, 289,319,168 B, `e9c9cb22…8af3ff52` |
| Wrong-cell tile (negative, selftest) | `tilewriter.make_factory("B30R060R")` |
| Stub root (real run) | `/tmp/opencode/h70-stub-root` — `DRSTR001.DAT`, `MMAIN001.DAT`, `VER_INFO/HDD_INFO.TXT`, no `MAPAL001/` |
| Repo tool | `tools/one_tile_pipeline.py` |

## Method

1. **Sample and hash.** The real tile above, read-only; only size and SHA-256
   are recorded. The stub root carries placeholder one-byte files so the run's
   provenance check is about the tile, not the root listing.
2. **Commands** (runnable as written):

```bash
cd /home/marek/projekty/OSM2Leaf
python3 tools/one_tile_pipeline.py --selftest
python3 tools/selftest.py --only one_tile_pipeline
sha256sum /home/marek/projekty/leafre-work/m5.29-factory-root/MAPAL001/B48R058R.DAT

mkdir -p /tmp/opencode/h70-stub-root/VER_INFO
printf x > /tmp/opencode/h70-stub-root/DRSTR001.DAT
printf x > /tmp/opencode/h70-stub-root/MMAIN001.DAT
printf x > /tmp/opencode/h70-stub-root/VER_INFO/HDD_INFO.TXT

python3 tools/one_tile_pipeline.py \
  --factory-root /tmp/opencode/h70-stub-root \
  --factory-tile /home/marek/projekty/leafre-work/m5.29-factory-root/MAPAL001/B48R058R.DAT \
  --cell B48R058R --out /tmp/opencode/h70-real-out \
  --json /tmp/opencode/h70-real.json          # exit 1 (tilewriter 0x2146), report written
```

3. **Controls.** Positive: the supplied honest tile is used (report names the
   supplied path, `factory_tile_override=true`, sha equals `sha256sum`, output
   tile present, run reaches tilewriter). Negative: the sibling `B30R060R`
   tile supplied for `--cell B48R058R` must be `factory-tile-mismatch` with no
   output tree; and `--factory-tile` without `--factory-root` exits 2.
4. **Scope.** `tools/one_tile_pipeline.py` only (`main` args,
   `build_factory_out`, `_factory_tile_provenance`, `selftest`). Not changed:
   `tilewriter`, the `0x2146` corridor, H64/H67 behaviour, H66's sweep.
5. **Falsifier** (stated before the run): a supplied tile is ignored, or a
   wrong-cell supplied tile passes, or the honest sha / `tilewriter_rc` moves.

## Observations

- `grep -c 'args.factory_tile' tools/one_tile_pipeline.py` was 0 before the
  change and is 1 after it (one line, two uses:
  `Path(args.factory_tile) if args.factory_tile else None`).
- Selftest: `selftest: OK (0 failure(s))`, 60 `ok` lines, 0 `FAIL`; the nine
  new lines are `--factory-tile: supplied tile parsed as B48R058R`,
  `… report names the supplied tile, not the root's derived path`,
  `… report hashes the supplied tile`, `… output tile exists`,
  `… run reached tilewriter (supplied tile used as template)`,
  `… another cell's supplied tile -> factory-tile-mismatch`,
  `… another cell's supplied tile -> no output tree`,
  `--factory-tile without --factory-root exits 2`.
- `selftest.py --only one_tile_pipeline`: `PASS`, `passed=1 failed=0`.
- Real override run against the stub root, exit 1, report fields:
  `factory_tile=/home/marek/projekty/leafre-work/m5.29-factory-root/MAPAL001/B48R058R.DAT`,
  `factory_tile_override=True`,
  `factory_tile_sha256=e9c9cb2236f6b53ad4fe9687a18a351afe80a46a63c0a1f18dc46d6c8af3ff52`,
  `factory_tile_size=289319168`, `factory_tree_provenance=factory-tile-parsed`,
  `factory_tile_cell_binding="5 box rows within cell B48R058R bounds"`,
  `factory_tile_box_rows=5`, `real_image_run=attempted`, `mode=factory-backed`,
  `tilewriter_rc=2`.
- `sha256sum` of the tile equals the reported `factory_tile_sha256`.

## Interpretation

- **FACT:** `--factory-tile` is read; the supplied tile is the template and is
  reported by path, size and SHA-256 (C-3910).
- **FACT:** the supplied tile passes through `_factory_tile_cell_binding`, so a
  wrong-cell override is `factory-tile-mismatch` with no output tree (C-3911).
- **OBSERVED:** on the honest EU2011 tile the override result is identical to
  the derived path, `tilewriter_rc=2` unchanged (C-3912).
- **OBSERVED:** `--factory-tile` without `--factory-root` exits 2, and a tile
  inside `--out` is rejected before the root copy (C-3913).
- **UNKNOWN:** whether a tile absent from the root's `DRSTR001.DAT` should also
  be rejected on provenance grounds — H67 kept that out of scope and this task
  does not add it (Follow-up).

## Conclusion

Chose option A (wire) over option B (delete): the flag now selects the tile,
and the H67 cell binding runs on it unchanged, so the parsed-then-unused class
is closed without weakening a guard. `docs/research/claims.md` gains
C-3910–C-3914; no format page changes (the format is untouched). The one
remaining provenance question (a tile the root's `DRSTR001.DAT` does not list)
is recorded as a follow-up, not silently accepted.

## Reproduction

```bash
python3 tools/one_tile_pipeline.py --selftest
# expected: selftest: OK (0 failure(s)); nine `--factory-tile:` ok lines
python3 tools/selftest.py --only one_tile_pipeline   # expected: PASS
```

## Follow-ups

- A supplied tile that the root's `DRSTR001.DAT` does not list is accepted if
  its box rows bind to the cell. If root-listing consistency is wanted, it is a
  new task on `_factory_tile_provenance` (H67 deliberately left it open), not a
  change to this flag.
- H66's flag sweep must now find `--factory-tile` with a non-zero
  `args.factory_tile` count (C-3910).
