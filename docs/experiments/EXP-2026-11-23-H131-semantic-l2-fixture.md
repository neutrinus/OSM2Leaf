# EXP-2026-11-23-H131: vendor-free semantic L2 fixture for H21's D3 case

- **Status:** done
- **Date:** 2026-11-23
- **Sample:** none (tool-only task). Every file in the fixture tree is
  generated at run time from format constants and the committed synthetic OSM
  input; no card image, vendor tile or `.DAT`/`.cmp` byte is read. The spliced
  tile is 32,948 B, SHA-256
  `3c4e1283ebfc0ff46544fc7086b192fef6d08c678908ca8f241537d1424878c3`; the
  committed synthetic input is `tools/make_l2_semantic_fixtures.py`'s
  `SYNTHETIC_OSM` (SHA-256
  `28336d6055d8806fe710898bbdd73b6a74ffd675dcb5745ae9a1ed51ff80a243` for the
  copy written to `--out`). No vendor data is committed.
- **Tools:** `python3 3.15.0`; `tools/zlibinfo.py` reports `zlib 1.3.1.zlib-ng`
  (not the reference compressor, so no byte-identical recompression claim is
  made here — the splice is a semantic write verified by decode, not a claim
  about factory stream bytes). Repo tools: `tools/cardcheck.py`,
  `tools/osm_ingest.py`, `tools/mesh_split.py`, `tools/tilewriter.py`,
  `tools/drstr_ze0.py`, `tools/l2check.py`, `tools/selftest.py`, and the new
  `tools/make_l2_semantic_fixtures.py`.
- **Claims:** C-8590–C-8599
- **Supersedes:** none
- **Superseded by:** none

## Question

Can H21's D3 "Krotoszyn fixture replacement" case — replace one level-1 parcel
of a factory-shaped tile with a known synthetic way and assert that the semantic
L2 decode returns that way — be shipped as a real, vendor-free, falsifiable
gate, with no change to `l2check` semantics?

## Hypothesis

Yes. A tool can generate the H103/L1 skeleton, splice one synthetic way into
the fixture tile, measure a fixture-local golden from the good tree, and prove
`l2check --semantic-tiles` returns PASS on the good tree and FAIL on a
one-byte mutant of the way. Falsifier: the fixture builds and `l2check`
exits 0 even after the spliced way's parcel bytes are corrupted (a placebo
check), or the good tree fails for a structural reason, or a single-byte
change fails a different check (`tile_section_list`, not `tile_semantic`).

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none (tool-only): generated tree at `--out DIR` |
| Spliced tile | `MAPAL001/B48R058R.DAT`, 32,948 B, SHA-256 `3c4e1283…78c3` |
| Base H103 tile | same path before splice: 3 features, digest `4844b788…6799` |
| Spliced tile digest | 21 features, `a0eb21a7cba1c3b5ad9b33a185eaaa7b289235191e1bc7cdebd8fbe6d34a30d2` |
| Fixture golden | `DIR/golden.json`, 226 B, SHA-256 `38b51601…4036` |
| Mutant byte | on-disk tile byte `0x7a02` (inside the way's zlib stream), `0x5b` → `0x5a` |
| Repo tool | `tools/make_l2_semantic_fixtures.py` (the one that produced the numbers) |

## Method

1. **Sample and hash.** No vendor sample. The generated spliced tile's
   SHA-256 is `3c4e1283ebfc0ff46544fc7086b192fef6d08c678908ca8f241537d1424878c3`;
   the generated golden's SHA-256 is
   `38b516016da189d5745a9562891a9600028aa7a9a17c95e2adb8c5daefe54036`.
   The synthetic OSM input is committed inside the tool (`SYNTHETIC_OSM`), not
   copied from any vendor or OSM dataset.

2. **Commands.** Runnable as written from the worktree root:

   ```bash
   W=~/projekty/leafre-work/scratch/h131
   rm -rf "$W/out"
   python3 tools/make_l2_semantic_fixtures.py --out "$W/out"
   # Positive control: the delivered tree passes the semantic gate.
   python3 tools/l2check.py --root "$W/out" --semantic-tiles B48R058R.DAT \
       --profile "$W/out/golden.json" --cmp-limit 20
   # Negative control: flip one byte of the way's zlib stream in a COPY,
   # then re-run the same gate (the tool does this internally too).
   cp -a "$W/out" "$W/mutant"
   python3 -c "p='$W/mutant/MAPAL001/B48R058R.DAT';b=bytearray(open(p,'rb').read());b[0x7a02]^=1;open(p,'wb').write(b)"
   python3 tools/l2check.py --root "$W/mutant" --semantic-tiles B48R058R.DAT \
       --profile "$W/mutant/golden.json" --cmp-limit 20
   # Selftest: both controls in one temp dir, no vendor data.
   python3 tools/make_l2_semantic_fixtures.py --selftest
   python3 tools/selftest.py --only make_l2_semantic_fixtures
   python3 tools/selftest.py
   ```

3. **Controls.** *Positive*: the good tree must pass `l2check` with
   `[tile_semantic] OK (B48R058R.DAT=21)` and `RESULT: PASS` (rc 0); the base
   H103 tile before the splice decodes only 3 features, so an added way must
   raise the count. *Negative*: one byte flipped at on-disk `0x7a02` — inside
   the zlib stream whose header is at `0x7a00`, i.e. inside the way's record,
   not a container/header byte — must make `l2check` exit 1 with
   `[tile_semantic] FAIL`, `20 features != golden 21` and a differing geometry
   digest. The mutant is made on a copy so the delivered tree stays intact.

4. **Scope.** One synthetic residential way (3 nodes, 2 segments) in
   `B48R058R`, clipped by `mesh_split` to the fixture's only level-1 directory
   (mesh y=72, x=936 = lon 12–14, lat 48.0–48.67). The tree is the H103
   skeleton: 1 REFER001 pair, the DRSTR/CMP.LST skeleton, `LEV3456R.DAT` and
   one `B48R058R.DAT`. No vendor bytes, no L1 image/FAT checks, no firmware
   execution (rule 13), no change to `l2check` rules or golden data. The
   residential class was chosen because `highway=residential` maps to road
   layer 5, which `stream_decode.features` decodes; `primary` maps to layer 6
   and is filtered out, so a primary way would leave the digest unchanged
   (that is the placebo case this task exists to avoid).

5. **Falsifier.** A wrong result would be: the splice adds no features (base
   and spliced digest equal), the good tree fails structurally, the mutant
   still passes, or the mutant fails `tile_section_list`/`tree` rather than
   `tile_semantic`. Any of these would make the fixture a placebo and the
   task closed negative.

## Observations

All numbers below are printed by the commands in Method part 2 (run on this
worktree at commit `ca9b0ee5` plus the H131 implementation).

- `cardcheck --generate-fixture` base tile: `[tile_semantic] OK (B48R058R.DAT=3)`,
  digest `4844b78874b70d50c19f492c4250a849abbd5243780ab10f982c1a1eadbf6799`.
- After splice: features `21`, digest
  `a0eb21a7cba1c3b5ad9b33a185eaaa7b289235191e1bc7cdebd8fbe6d34a30d2`;
  tile 32,948 B, SHA-256 `3c4e1283…78c3`. The decoded new features are road
  layer `205` (`0xcd`), kind `64`, type `4101` (`0x1005`), first coordinate
  `(12.1999969, 48.2999980)`.
- Good tree, `python3 tools/l2check.py --root "$W/out" --semantic-tiles
  B48R058R.DAT --profile "$W/out/golden.json" --cmp-limit 20`:
  `[tile_semantic] OK (B48R058R.DAT=21)`, `RESULT: PASS`, rc `0`.
- Mutant (flip `0x7a02`, `0x5b`→`0x5a`): `[tile_semantic] FAIL
  (B48R058R.DAT=20)`, `ERROR B48R058R.DAT: 20 features != golden 21`, `ERROR
  B48R058R.DAT: geometry digest differs from golden`, `RESULT: FAIL`, rc `1`.
- `python3 tools/make_l2_semantic_fixtures.py --selftest`:
  `make_l2_semantic_fixtures selftest: PASS`, `features=21 digest=a0eb21a7…d30d2`,
  `good rc=0 RESULT: PASS`, `mutant 0x7a02 0x5b->0x5a rc=1 RESULT: FAIL`.
- `python3 tools/selftest.py --only make_l2_semantic_fixtures`: PASS.
- `python3 tools/selftest.py --timeout 180`: full suite green,
  `passed=270 failed=0 skipped=21 total=291` (after rebasing onto `origin/main`
  at `a60d15bc`; before the rebase it was `269/0/21 total=290`). At the default
  60 s timeout a concurrent-agent run gave `268/1` only because `ci_gate_repro`
  (48.46 s in isolation) hit the 60 s per-tool limit; `python3 tools/selftest.py
  --only ci_gate_repro` passes with rc 0. A later run with `TMPDIR` pointed at a
  nearly-full scratch directory hit `ENOSPC` in 13 unrelated selftests; with the
  default `/tmp` (3.6 GiB free) the full suite is green.
- Ordering trap (navigator): when `golden.json` is written to `DIR` but
  `DRSTR001.DAT` is rebuilt before it, the good run FAILs
  `[drstr_roundtrip] FAIL (size=912)`. With `drstr_ze0.build(root)` called LAST
  the good run is `RESULT: PASS`. A `generate_golden()`-derived profile (full
  `files`/`census` sections) makes even the good run FAIL
  (`[census] FAIL files=10`, `[files] FAIL`, `[drstr_roundtrip] FAIL`); the
  small golden is required.

## Interpretation

- **FACT:** H21's D3 semantic L2 case is now a real tool-backed gate. The tool
  writes a vendor-free tree, splices a known synthetic way, and proves
  `l2check --semantic-tiles` is sensitive to the way's bytes: good PASS (21
  features) vs one-byte mutant FAIL (20 features), with the failure localized
  to `tile_semantic`.
- **FACT:** the splice changes the decoded digest (base `4844b788…6799`, 3
  features → spliced `a0eb21a7…d30d2`, 21 features), so the assertion is not a
  placebo. `highway=residential` (layer 5) is required; a `primary` way at
  lon 17.4 is out of the fixture directory and maps to the filtered layer 6,
  leaving the digest unchanged.
- **FACT:** `--update-golden` is unsafe here — it hardcodes four semantic tile
  names and ignores `--semantic-tiles`, so a profile it writes has no
  `B48R058R.DAT` entry and a mutation still passes. The tool writes an explicit
  fixture-local golden instead, measured from the good tile with `l2check`'s
  own `feature_digest`, never from `tools/golden/eu2011.json`.
- **OBSERVED:** all commands in Method part 2 were run on this worktree; the
  counts above are their printed stdout/stderr, not recomputed estimates.
- **HYPOTHESIS:** the same skeleton-plus-splice pattern can host other H21
  semantic L1/L2 cases (e.g. level-2 parcels) with a different synthetic way;
  not required by this task.
- **UNKNOWN:** firmware acceptance of the synthetic tile (rule 13); no L3/L4
  run was made. The `0x7a02` mutant is a clean decoder-level falsifier, not a
  statement about how a unit would render the parcel.

## Conclusion

`tools/make_l2_semantic_fixtures.py` is added with `--out DIR` and `--selftest`,
listed in `tools/README.md`, and covered by `tools/selftest.py`. It implements
H21's D3 case with no vendor bytes, no new L2 rule and no `l2check` change. The
positive control (good tree PASS) and negative control (one-byte mutant FAIL
in `tile_semantic`) both pass, and the splice demonstrably changes the digest.
No `docs/format/` change was needed; claim IDs C-8590–C-8599 back the result.

## Overtaken by a later commit

none

## Reproduction

```bash
W=~/projekty/leafre-work/scratch/h131
python3 tools/make_l2_semantic_fixtures.py --out "$W/out"   # expected: "result": "PASS", features=21
python3 tools/l2check.py --root "$W/out" --semantic-tiles B48R058R.DAT \
    --profile "$W/out/golden.json" --cmp-limit 20           # expected: RESULT: PASS, rc 0
python3 tools/make_l2_semantic_fixtures.py --selftest       # expected: good PASS + mutant 0x7a02 FAIL
```

## Follow-ups

- [ ] H21's second L1/L2 semantic case (level-1 names) is still prose; this
      tool covers only the D3 "Krotoszyn fixture replacement" case.
- [ ] Port `l2check`'s semantic decoder to wide `0x2n46` directory rows so the
      fixture can host a wide-row mutant (already a follow-up in M5.53).

## Corrections after navigator review

Two rounds. Round 1 (CHANGES) found that `--update-golden` ignores
`--semantic-tiles` and a profile from it leaves `tile_semantic` PASS even after
mutation; fixed by writing an explicit fixture-local golden with a
`tiles["B48R058R.DAT"]` entry measured via `feature_digest`, and by keeping
`--no-golden` out of both verification commands. Round 1 also surfaced that the
native `m9.53-krotoszyn.osm` way is a placebo here (out of directory, filtered
layer 6); fixed by a committed synthetic `residential` way inside the fixture
directory (layer 5). Round 2 (APPROVE, with ordering caveat) required rebuilding
`DRSTR001.DAT` LAST after the golden is written and keeping the golden minimal;
implemented, and the implemented tool's positive/negative controls were
re-verified.
