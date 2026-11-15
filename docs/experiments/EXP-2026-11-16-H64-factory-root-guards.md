# EXP-2026-11-16-H64-factory-root-guards: factory-tree provenance and `--out` overlap guard

- **Status:** done
- **Date:** 2026-11-16
- **Sample:** EU2011 factory root extracted outside the repo
  `/home/marek/projekty/leafre-work/m5.29-factory-root`, tile
  `MAPAL001/B48R058R.DAT` SHA-256
  `e9c9cb2236f6b53ad4fe9687a18a351afe80a46a63c0a1f18dc46d6c8af3ff52`
  (289,319,168 B, 3 sections); plus a tiny synthetic factory tile built in a
  temp dir by `tilewriter.make_factory("B48R058R")` for the selftest. No vendor
  bytes committed.
- **Tools:** `python3 3.13`, `tools/one_tile_pipeline.py`,
  `tools/tilewriter.py` (`make_factory`), `tools/ze0-viewer/tools_ze0/clarion_tile.py`
  (`read_tile`)
- **Claims:** C-3840, C-3841, C-3842, C-3843
- **Supersedes:** none
- **Superseded by:** none

## Question

Does `--factory-root` prove it read a real, parseable factory tile before it
mutates anything, and does an `--out` that overlaps the input root refuse
safely instead of deleting the input?

## Hypothesis

A factory-backed report can carry a tile-specific provenance
(`MAPAL001/<cell>.DAT` parsed + sha256 + size) and set
`real_image_run=factory-tree-invalid` (never `attempted`) for an empty or
unparseable tile; an `--out` equal to / a parent of / a child of the input
root exits 2 with a usage message and leaves the input untouched.

**Falsifier:** a zero-byte or unparseable tile still reports `attempted`; an
`--out == --factory-root` run returns anything other than 2 or mutates/removes
the input tree; `factory_tile_sha256` differs from `sha256sum` of the tile.

## Inputs

| Item | Value |
| --- | --- |
| Factory root (outside repo) | `/home/marek/projekty/leafre-work/m5.29-factory-root` |
| Tile | `MAPAL001/B48R058R.DAT`, 289,319,168 B |
| Tile SHA-256 | `e9c9cb2236f6b53ad4fe9687a18a351afe80a46a63c0a1f18dc46d6c8af3ff52` |
| OSM fixture | `SYNTHETIC_OSM` in `one_tile_pipeline.py`, 4 nodes / 2 ways / 7 IMF records |
| Repo tool | `tools/one_tile_pipeline.py` |

## Method

1. **Sample and hash.** The real tile above (read-only; only its sha256 and
   size are recorded). The synthetic sample is generated in a temp dir by
   `tilewriter.make_factory`, so no vendor bytes are needed.
2. **Commands** (runnable as written; the real-root run needs the extracted
   tree, the selftest does not):

```bash
cd /home/marek/projekty/OSM2Leaf
python3 tools/one_tile_pipeline.py --selftest
sha256sum /home/marek/projekty/leafre-work/m5.29-factory-root/MAPAL001/B48R058R.DAT
python3 tools/one_tile_pipeline.py \
  --factory-root /home/marek/projekty/leafre-work/m5.29-factory-root \
  --cell B48R058R --out /home/marek/projekty/leafre-work/h64-real-out \
  --json /tmp/opencode/h64-real-run.json    # writes the report; prints "report: <path>"
python3 tools/selftest.py --only one_tile_pipeline
```

Empty-tile negative (temp tree, no vendor bytes):

```bash
T=$(mktemp -d)
mkdir -p "$T/MAPAL001" "$T/VER_INFO"
: > "$T/MAPAL001/B48R058R.DAT"
: > "$T/DRSTR001.DAT"; : > "$T/MMAIN001.DAT"; : > "$T/VER_INFO/HDD_INFO.TXT"
python3 tools/one_tile_pipeline.py --factory-root "$T" --out "$T.out" --cell B48R058R --json -
# real_image_run = factory-tree-invalid, every gate BLOCKED, no "$T.out" created
```

Overlap negative:

```bash
T=$(mktemp -d); mkdir -p "$T/MAPAL001" "$T/VER_INFO"
: > "$T/MAPAL001/B48R058R.DAT"; : > "$T/DRSTR001.DAT"
: > "$T/MMAIN001.DAT"; : > "$T/VER_INFO/HDD_INFO.TXT"
python3 tools/one_tile_pipeline.py --factory-root "$T" --out "$T" --cell B48R058R
# exit 2; "$T" and its files still present
```

3. **Controls.**
   - *Positive:* honest factory tile parsed, `factory_tile_sha256` equals the
     `sha256sum` of that file (selftest + the real root); the synthetic
     fixture parses to a tile.
   - *Negative (a):* zero-byte factory tile -> `real_image_run=factory-tree-invalid`,
     every gate `BLOCKED`, no output tree created.
   - *Negative (b):* `--out` == input root, inside it, and a parent of it ->
     each exits 2 and the input tree is byte-identical afterwards.
4. **Scope.** `tools/one_tile_pipeline.py` only. One real tile/cell
   (`B48R058R`) on the EU2011 root; the rest of the corpus is the synthetic
   fixture. `tilewriter`, gate vocabulary and the `0x2146` corridor decision
   are unchanged.
5. **Falsifier.** As stated in Hypothesis.

## Observations

- Selftest: `python3 tools/one_tile_pipeline.py --selftest` -> `OK
  (0 failure(s))`, including the two new negatives and the honest-tile
  positive. `python3 tools/selftest.py --only one_tile_pipeline` -> `PASS 0.69s`.
- Real root: `sha256sum .../MAPAL001/B48R058R.DAT` =
  `e9c9cb2236f6b53ad4fe9687a18a351afe80a46a63c0a1f18dc46d6c8af3ff52`;
  report `factory_tile_sha256` = the same,
  `factory_tile_size` = 289,319,168, `factory_tree_provenance` =
  `factory-tile-parsed`, `factory_tile_sections` = 3, `mode=factory-backed`,
  `real_image_run=attempted`.
- Real root counts: `osm_ingest_rc=0`, `mesh_split_rc=0`, `roadclass_rc=0`,
  `tilewriter_rc=2`; stderr `directory y=76 x=941 has kind 0x2146: slot-table
  structure is modelled and preserved, but record boundaries are not safe to
  mutate; refused (see PRESERVE_ONLY_DIR_KINDS, EXP-2026-11-08-M5.22)`.
  All five gates `BLOCKED`.
- Empty-tile negative: `real_image_run=factory-tree-invalid`,
  `factory_tile_sha256=None`, `factory_tile_size=0`, every gate `BLOCKED`,
  no output tree; exit 1 (blocked, not a usage error).
- Pre-fix state (QA report, not re-run here): `--out == --factory-root`
  returned exit 1 with `FileNotFoundError` and the input was gone; an empty
  tile reported `real_image_run=attempted`. Both are the defects this task
  closes; the commands above are the post-fix controls.
- Overlap negative after the change: `--out == root`, `--out` inside root,
  and `--out` a parent of root each exit 2 with a usage message; the root and
  its files remain. All three branches — including parent-of-root, and the
  `build_synthetic_out(..., input_root=parent)` form — are covered by
  `--selftest`, not only by hand.
- `--json` is `nargs="?"` (`const="-"`): bare `--json`/`--json -` print to
  stdout, `--json PATH` writes the report atomically and prints
  `report: <path>`. `--selftest` runs `--json PATH` and re-parses the file.

## Interpretation

- **FACT:** the report now carries a tile-specific provenance
  (`factory_tile_sha256`, `factory_tile_size`,
  `factory_tree_provenance`) taken from parsing `MAPAL001/<cell>.DAT`, not from
  the whole-image hash.
- **FACT:** an empty or unparseable factory tile yields
  `real_image_run=factory-tree-invalid` and `BLOCKED` gates, never `attempted`.
- **FACT:** an `--out` that overlaps the input root (equal, parent, or child)
  exits 2 with no filesystem change.
- **OBSERVED:** the genuine EU2011 root still fails at `tilewriter` on the
  `0x2146` directory (M5.22), so the corridor result is unchanged: `rc=2`,
  all gates `BLOCKED`.
- **UNKNOWN:** whether a parseable-but-wrong tile (a different cell's tile
  copied into place) would be caught; only the tile's own parse and sha are
  provenance, not a match to the card's expected sha. That is out of scope
  here.
- **UNKNOWN:** firmware acceptance remains L3/L4/L5 (rule 13).

## Conclusion

`tools/one_tile_pipeline.py` now proves it read a parseable factory tile
before it copies anything, and rejects an overlapping `--out` before any
delete. The `0x2146` corridor decision is untouched: the real run still
reports `tilewriter rc=2`. Nothing changed in `docs/format/`; the claims
record the tool behaviour only.

## Reproduction

```bash
python3 tools/one_tile_pipeline.py --selftest     # expected: OK (0 failure(s))
python3 tools/selftest.py --only one_tile_pipeline  # expected: PASS
sha256sum /home/marek/projekty/leafre-work/m5.29-factory-root/MAPAL001/B48R058R.DAT
# expected: e9c9cb22...8af3ff52
```

## Follow-ups

- [ ] C-3844–C-3849 stay RESERVED; no claim was added for the `--json PATH`
  writer beyond the selftest coverage.
- [ ] A parseable-but-wrong tile (another cell's tile copied into
  `MAPAL001/<cell>.DAT`) is not rejected: provenance is the tile's own parse
  and sha, not a match to an expected card sha. If a factory-tree fingerprint
  is wanted, it needs a task (the whole-image sha is explicitly not the test).
- [ ] The genuine EU2011 corridor run is still blocked at `tilewriter` on the
  `0x2146` directory (`y=76 x=941`); that is M5.22/M5.34 work, not this task.
