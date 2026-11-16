# EXP-2026-11-16-H67-factory-tile-cell: binding a factory tile to its cell

- **Status:** done
- **Date:** 2026-11-16
- **Sample:** EU2011 factory root extracted outside the repo
  `/home/marek/projekty/leafre-work/m5.29-factory-root`, tile
  `MAPAL001/B48R058R.DAT` SHA-256
  `e9c9cb2236f6b53ad4fe9687a18a351afe80a46a63c0a1f18dc46d6c8af3ff52`
  (289,319,168 B); the negative sample is the same root's sibling
  `MAPAL001/B30R060R.DAT` SHA-256
  `8ca92bd5601e33bd97ab3bbab62b4394448cbe0e2adf31ba6046eebb52b8b62d`
  (1,294,336 B) copied over `B48R058R.DAT`. The selftest sample is a synthetic
  tile built in a temp dir by `tilewriter.make_factory`. No vendor bytes are
  committed.
- **Tools:** `python3 3.13`, `tools/one_tile_pipeline.py`,
  `tools/tilewriter.py` (`make_factory`, `cell_db_bounds`), `tools/drstr.py`,
  `tools/ze0-viewer/tools_ze0/clarion_tile.py` (`read_tile`)
- **Claims:** C-3880, C-3881, C-3882, C-3883, C-3884, C-3885
- **Supersedes:** none
- **Superseded by:** none

## Question

Does a factory-backed run prove that `MAPAL001/<cell>.DAT` is *that cell's*
factory tile, rather than any tile that happens to parse and hash?

## Hypothesis

The tile's header box table at `0x2ac` (per-section, per-level `(y1, y0, x0, x1)`
arc-minute bounds) binds the tile to its `BxxRyyR` cell: every honest row lies
inside the cell's arc-minute bounds, and a sibling cell's tile does not. A
different cell's tile copied into `MAPAL001/B48R058R.DAT` therefore yields
`real_image_run=factory-tree-invalid` with `factory_tree_provenance=
factory-tile-mismatch` and no output tree.

**Falsifier:** the sibling tile copied over `B48R058R.DAT` still reports
`mode=factory-backed` / `real_image_run=attempted`; or an honest `B48R058R` tile
fails the binding (false reject); or the honest run's `factory_tile_sha256`
changes.

## Inputs

| Item | Value |
| --- | --- |
| Factory root (outside repo) | `/home/marek/projekty/leafre-work/m5.29-factory-root` |
| Honest tile | `MAPAL001/B48R058R.DAT`, 289,319,168 B, `e9c9cb22…8af3ff52` |
| Sibling tile (negative) | `MAPAL001/B30R060R.DAT`, 1,294,336 B, `8ca92bd5…2b8b62d` |
| Cell bounds formula | `tilewriter.cell_db_bounds`: arc-minutes of `lat_min=int(B,16)*2/3`, `lon_max=108-int(R,16)`, 5.333° × 8° |
| Repo tool | `tools/one_tile_pipeline.py` |

## Method

1. **Sample and hash.** The real tiles above (read-only; only size and sha256
   are recorded). The synthetic tile is generated in a temp dir by
   `tilewriter.make_factory(cell)`.
2. **Commands** (runnable as written; the real-root runs need the extracted
   tree, the selftest does not):

```bash
cd /home/marek/projekty/OSM2Leaf
python3 tools/one_tile_pipeline.py --selftest
python3 tools/selftest.py --only one_tile_pipeline
python3 tools/one_tile_pipeline.py --check-cell-binding \
  /home/marek/projekty/leafre-work/m5.29-factory-root   # 45 cells, 213 rows, 0/1980
sha256sum /home/marek/projekty/leafre-work/m5.29-factory-root/MAPAL001/B48R058R.DAT
python3 tools/one_tile_pipeline.py \
  --factory-root /home/marek/projekty/leafre-work/m5.29-factory-root \
  --cell B48R058R --out /home/marek/projekty/leafre-work/h67-real-out \
  --json /tmp/opencode/h67-real-run.json        # honest positive control
```

Wrong-cell negative (honest sibling over `B48R058R.DAT`, temp tree, no output
expected):

```bash
R=/home/marek/projekty/leafre-work/m5.29-factory-root
W=$(mktemp -d /tmp/opencode/h67-wrong.XXXX)
mkdir -p "$W/MAPAL001" "$W/VER_INFO"
cp "$R/MAPAL001/B30R060R.DAT" "$W/MAPAL001/B48R058R.DAT"
cp "$R/DRSTR001.DAT" "$R/MMAIN001.DAT" "$W/" ; cp "$R/VER_INFO/HDD_INFO.TXT" "$W/VER_INFO/"
python3 tools/one_tile_pipeline.py --factory-root "$W" --out "$W.out" \
  --cell B48R058R --json /tmp/opencode/h67-wrong-run.json
test ! -e "$W.out"; echo "no output tree: $?" ; rm -rf "$W"
```

3. **Controls.**
   - *Positive:* the honest `B48R058R` tile parses and every one of its 5 box
     rows lies inside the cell bounds; `factory_tile_sha256` equals the
     `sha256sum` above. The same sibling `B30R060R` tile under its own name
     passes (`factory-tile-parsed`), so the check rejects the *cell*, not the
     bytes.
   - *Negative:* the sibling tile copied over `B48R058R.DAT` yields
     `factory-tree-mismatch` / `factory-tree-invalid`, every gate `BLOCKED`,
     and no output tree. The empty-tile and `--out`-overlap cases from H64 are
     unchanged.
4. **Scope.** `tools/one_tile_pipeline.py` only. One real cell (`B48R058R`,
   5 box rows, 3 sections) and its sibling (`B30R060R`); the selftest uses
   synthetic tiles. The binding is measured over all 45 `BxxRyyR` tiles of the
   root (213 box rows, 1,980 ordered cell pairs). `tilewriter`, the gate
   vocabulary and the `0x2146` corridor decision are untouched.
5. **Falsifier.** As stated in Hypothesis.

## Observations

- `--check-cell-binding` on the honest root: `cells=45`, `box_rows=213`,
  `honest_tiles_pass=45`, `wrong_pairs=1980`, `wrong_pairs_pass=0`,
  `skipped=["LEV3456R.DAT"]`, `ok=true` (exit 0).
- **Binding field survey** (honest root, 45 cells / 213 box rows):

  | Candidate field | Honest | Wrong cell | Verdict |
  | --- | --- | --- | --- |
  | Box table `0x2ac` (per level) | 213/213 rows in bounds | 0/1,980 ordered pairs pass | chosen |
  | `DRSTR001.DAT` size for the cell | matches (both tiles) | sibling size matches its own entry | cross-check only |
  | Header `0x184`/`0x5d0` | same in every tile | same | database-wide, not cell-specific |

- Honest run: `mode=factory-backed`, `real_image_run=attempted`,
  `factory_tile_sha256=e9c9cb22…8af3ff52` (unchanged), `factory_tile_size=
  289,319,168`, `factory_tree_provenance=factory-tile-parsed`,
  `factory_tile_cell_binding="5 box rows within cell B48R058R bounds"`,
  `factory_tile_box_rows=5`; `tilewriter_rc=2` (the `0x2146` directory), all
  gates `BLOCKED` — the corridor result is unchanged.
- Wrong-cell run: `real_image_run=factory-tree-invalid`,
  `factory_tree_provenance=factory-tile-mismatch`,
  `factory_tile_cell_binding="box row section 1 level 2 (2240,1990,240,720) is
  outside cell B48R058R bounds (3200,2880,720,1200)"`, `factory_tile_sha256=
  8ca92bd5…2b8b62d`, every gate `BLOCKED`, no `$W.out`.
- Selftest: `OK (0 failure(s))`, 51 checks including the wrong-cell negative;
  `selftest.py --only one_tile_pipeline` -> `PASS`.
- `DRSTR001.DAT` cross-check: `MAPAL001/B48R058R.DAT` is listed at 289,319,168
  B and `B30R060R.DAT` at 1,294,336 B, both equal to the on-disk sizes.

## Interpretation

- **FACT:** the box table at `0x2ac` is cell-specific: 213/213 honest rows lie
  inside their cell's arc-minute bounds and none of the 1,980 wrong-cell tile
  placements does.
- **FACT:** a different cell's tile copied over `MAPAL001/B48R058R.DAT` yields
  `factory-tree-mismatch` / `factory-tree-invalid`, every gate `BLOCKED`, and
  no output tree — it is never reported as `attempted` or `factory-backed`.
- **OBSERVED:** the honest run is unchanged (`mode=factory-backed`, same tile
  sha, `tilewriter rc=2` on `0x2146`).
- **OBSERVED:** `DRSTR001.DAT` lists each tile's on-disk size, but a sibling of
  equal size passes it, so it is recorded as a cross-check, not the binding.
- **HYPOTHESIS:** the binding is complete for a cell whose box rows are the
  cell-sized database box; a tile whose rows are all inside another cell's box
  by accident is not excluded by this field alone (not seen on the 45-tile
  root).
- **UNKNOWN:** firmware acceptance (rule 13); this is a tool-side provenance
  check, not L3/L4/L5.

## Conclusion

`tools/one_tile_pipeline.py` now binds `MAPAL001/<cell>.DAT` to its cell
through the header box table at `0x2ac`, so a parseable-but-wrong tile is
rejected before any copy. The `0x2146` corridor decision (M5.34) is untouched:
the genuine root still reports `tilewriter rc=2` and all gates `BLOCKED`.
Nothing in `docs/format/` changed; the claims record the tool behaviour only.

## Reproduction

```bash
python3 tools/one_tile_pipeline.py --selftest          # expected: OK (0 failure(s))
python3 tools/one_tile_pipeline.py --check-cell-binding \
  /home/marek/projekty/leafre-work/m5.29-factory-root  # expected: 45 cells, 0/1980 wrong passes, exit 0
python3 tools/selftest.py --only one_tile_pipeline     # expected: PASS
sha256sum /home/marek/projekty/leafre-work/m5.29-factory-root/MAPAL001/B48R058R.DAT
# expected: e9c9cb22...8af3ff52
```

## Follow-ups

- [ ] C-3886–C-3889 stay RESERVED.
- [ ] A tile whose box rows happen to fall inside a different cell's box is not
  excluded by this field alone; no such tile occurs in the 45-tile EU2011 root.
  A second binding (a `DRSTR001.DAT` CRC, if one exists) is M5 work and not
  needed for the wrong-cell case.
- [ ] The genuine EU2011 corridor run is still blocked at `tilewriter` on the
  `0x2146` directory (`y=76 x=941`); that is M5.34, not this task.
