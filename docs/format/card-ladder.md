# The card ladder: P0, P1, and the P2 placeholder

> **Status:** the gates in this page are `VERIFIED (host, 2026-11-19)` — every
> command below was run and every row prints the token it says it prints
> (EXP-2026-11-19-M5.50-card-ladder). The ladder *content* (what each rung
> should contain, P0–P4, and the inconsistencies the firmware will see) is
> [`docs/research/card-ladder.md`](../research/card-ladder.md) (M5.38); this
> page only says which command decides a
> rung, so "is P1 one tile or many?" has one answer with a command behind it.

A rung is a **check**, not a description: a region/profile, a tile set, and a
set of commands with exact expected output. If a row's command exits 0 without
printing its token, the row fails — that is the falsifier for the whole page.
A rung with no runnable gate is printed as `NOT RUN — <task>`, never as prose.

| Rung | Region / profile | Tile set | Change vs factory | Gate commands | Deliberately not proven |
| --- | --- | --- | --- | --- | --- |
| **P0** | `profiles/dolnoslaskie-test.json` | `B48R058R` (the whole test box is inside it) | section-1 display geometry of that one tile is OSM-derived; everything else factory | census, `cardcheck --root/--image`, `fit_census`, `check-diff`, `l2check`, `7z t` (§P0) | routing, names, search, any firmware read (rule 13) |
| **P1** | same profile | same one tile | **nothing in the tile**: factory bytes copied verbatim; only `DRSTR001.DAT` may move | census, `fit_census` delta 0; the card gate is `NOT RUN — M5.49` (§P1) | that OSM data reaches the unit (P0 does that); routing/names/search; firmware read |
| **P2** | `profiles/poland-full.json` | 4 tiles (`B48R050R`, `B48R058R`, `B50R050R`, `B50R058R`) | section 2 + `LEV3456R.DAT` sec2 (routing), road-class table | census only today; **`NOT RUN — M5.16`** (routing), **`NOT RUN — M5.36`** (class golden) (§P2) | everything about names/search; firmware read |

P3 (names) and P4 (search) are M5.38's rows and are out of scope here until a
gate exists; this page stops where a command stops.

## Inputs

Paths on this host. `FAC` is the read-only factory tree, `W` the M5.44 result
tree (P0's tile source), `IMG` the EU 2011 card, `S` the scratch directory
(outside the repo, deleted after the EXP).

```bash
FAC=$HOME/projekty/leafre-work/m5.29-factory-root
W=$HOME/projekty/leafre-work/m5.44/out
IMG=archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img
S=$HOME/projekty/leafre-work/scratch/m5.50
```

`Note`: `mkcard --selftest` and `l2check` need `TMPDIR` on disk (`/tmp` here is
a 3.8 GiB tmpfs), so export `TMPDIR=$S/tmp`.

## P0 — one OSM-derived tile on an accepted card

Region Dolnośląskie; the census puts the whole bbox inside one tile
(`contained=1`), so P0 changes exactly `MAPAL001/B48R058R.DAT`'s section-1 road
geometry and its `DRSTR001.DAT` directory values. Built with the M5.30 recipe:
copy the image, patch the tile, patch the manifest (EXP-2026-11-19-M5.30).

| # | Command (from the repo root) | Expected token | Exit |
| --- | --- | --- | --- |
| 1 | `python3 tools/mesh_grid.py cover profiles/dolnoslaskie-test.json $FAC/MAPAL001` | `census: contained=1 intersects=0 outside=62 lattice=63 factory_tiles=45` | 0 |
| 2 | `python3 tools/cardcheck.py --root $FAC --fast` | `RESULT: PASS` | 0 |
| 3 | `python3 tools/fit_census.py --image $IMG --tree $W` | `needs relocation: MAPAL001/B48R058R.DAT delta=+138994 slack=22272 extra_clusters=2 tail_free_run=0 tail_free_enough=False` | **1** |
| 4 | `python3 tools/fit_census.py --image $IMG --tree $FAC` | `files=480 changed=0 fits=480 needs_relocation=0 not_on_image=0 total_delta=+0` | 0 |
| 5 | `python3 tools/cardcheck.py --image $S/p0.img` | `RESULT: PASS` | 0 |
| 6 | `sha256sum $S/p0.img` | `b0faf119ee2ccfb3ce757bafa49ba7bdac6730d32c8ac97a2337fb18e3c33237` | 0 |
| 7 | `python3 tools/imgpatch.py --check-diff --image $S/p0.img --reference $IMG --file MAPAL001/B48R058R.DAT --file DRSTR001.DAT --allow-metadata` | `diffs: 586 range(s), outside: 0, metadata: 9` | 0 |
| 8 | same, **without** `--allow-metadata` | `diffs: 586 range(s), outside: 9, metadata: 0` | **1** |
| 9 | `python3 tools/l2check.py --root $W --no-golden --tiles B48R058R.DAT --semantic-tiles B48R058R.DAT --cmp-limit 20` | `tile_semantic] OK (B48R058R.DAT=2333602)` and `RESULT: PASS` | 0 |
| 10 | `7z t $S/p0.img` | `Everything is Ok` | 0 |

Rows 3 and 8 are **expected to exit 1**: `fit_census` signals "does not fit the
factory chain" and `check-diff` signals "bytes outside the admitted class" with
a non-zero exit while still printing the row's token. A row whose token is
missing is a failure whether the exit is 0 or 1.

**What P0 deliberately does not prove.** The tile's section 2 (routing graph)
and section 4 (names), `LEV3456R.DAT`'s coarse levels, `REFER001` search tables
and every speech/POI file are the factory's — the card draws new roads but the
router does not know them (M5.16/M5.37), names are factory (M4.36), search is
factory (M5.16), and no firmware has read any of it: the tile reader target is
M3.25, the full system is M8, the car is L5. `l2check` here runs on the result
tree, not on the relocated chain inside the image.

## P1 — the contained tile as a card (draft)

Region and tile set are P0's (`contained=1`); the change is **zero tile
bytes** — M5.49 copies the factory tile verbatim and rebuilds only
`DRSTR001.DAT` if its length must move (delta 0 ⇒ the M5.30 relocation work does
not apply). The point of the rung is that it is fail-loud about anything that
would touch the tile.

| # | Command | Expected token | Exit | Status |
| --- | --- | --- | --- | --- |
| 1 | `python3 tools/mesh_grid.py cover profiles/dolnoslaskie-test.json $FAC/MAPAL001` | `census: contained=1 intersects=0 outside=62 lattice=63 factory_tiles=45` | 0 | runs |
| 2 | `python3 tools/fit_census.py --image $IMG --tree $FAC` | `files=480 changed=0 fits=480 needs_relocation=0 not_on_image=0 total_delta=+0` | 0 | runs (delta-0 is the P1 property) |
| 3 | `python3 tools/one_tile_pipeline.py --preserve-tile B48R058R --out $S/p1` | — | — | **NOT RUN — M5.49** (flag absent) |
| 4 | `python3 tools/imgpatch.py --check-diff --image $S/p1.img --reference $IMG --file DRSTR001.DAT --allow-metadata` | — | — | **NOT RUN — M5.49** |
| 5 | `python3 tools/cardcheck.py --image $S/p1.img` | — | — | **NOT RUN — M5.49** |

Row 3's absence is checkable today, and it is the row's own negative control:
`python3 tools/one_tile_pipeline.py --help | awk '/--preserve-tile/{n++} END{print n+0}'`
prints `0` (exit 0) — the flag that the row calls does not exist yet, so the
row may not be reported as passing.

**What P1 deliberately does not prove.** Everything P0 does not prove, plus the
one P1-specific gap: a verbatim factory tile proves the *pipeline* carries the
region unchanged, not that OSM data reaches the unit — that is P0's gate.

## P2 — routing and the class golden (placeholder)

Region Poland (`profiles/poland-full.json`): no single tile contains it;
`contained=0`, four tiles intersect. P2 adds what P0/P1 leave factory: section 2
of the grid tiles, `LEV3456R.DAT` section 2, and the road-class round trip.

| # | Command | Expected token | Exit | Status |
| --- | --- | --- | --- | --- |
| 1 | `python3 tools/mesh_grid.py cover profiles/poland-full.json $FAC/MAPAL001` | `census: contained=0 intersects=4 outside=59 lattice=63 factory_tiles=45` | 0 | runs |
| 2 | `awk '/\*\*M5.16 —/,/Claims:/' TODO.md \| awk '/Status: blocked/{n++} END{print n+0}'` | `1` | 0 | runs — the routing gate is still blocked |
| 3 | `awk '/\*\*M5.36 —/,/Claims:/' TODO.md \| awk '/Status: open/{n++} END{print n+0}'` | `1` | 0 | runs — the class golden is still open |
| 4 | `awk '/tile_class_roundtrip/{n++} END{print n+0}' tools/l2check.py` | `0` | 0 | runs — no class check exists yet |
| 5 | `python3 tools/l2check.py --root <P2 tree> --semantic-tiles <tile>` | — | — | **NOT RUN — M5.36** |
| 6 | `python3 tools/lev3456gen.py generate …` + `python3 tools/lev3456.py verify` | — | — | **NOT RUN — M5.16** (blocked on M9.18) |

**What P2 deliberately does not prove.** That a route is *correct* (M5.37's
route-graph golden), that names resolve (M4.36), or that the unit routes on
generated data (rule 13: L3 target M3.25, L4 M8, car L5).

## One block that runs the runnable rows

`want TOKEN WANT_RC COMMAND` succeeds only if the exit code **and** the token
match, so a command that exits 0 with the wrong text fails. It builds the P0
card if `$S/p0.img` is absent (M5.30 recipe), so the block is runnable from the
repo root on a clean scratch directory. Rows that are `NOT RUN` are not silently
skipped: P1's absent flag is asserted to be absent.

```bash
cd "$(git rev-parse --show-toplevel)"
FAC=$HOME/projekty/leafre-work/m5.29-factory-root
W=$HOME/projekty/leafre-work/m5.44/out
IMG=archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img
S=$HOME/projekty/leafre-work/scratch/m5.50
mkdir -p $S/tmp; export TMPDIR=$S/tmp
if [ ! -f $S/p0.img ]; then
  cp $IMG $S/p0.img
  python3 tools/imgpatch.py --image $S/p0.img --file MAPAL001/B48R058R.DAT \
    --from $W/MAPAL001/B48R058R.DAT --allow-resize --json > /dev/null
  python3 tools/imgpatch.py --image $S/p0.img --file DRSTR001.DAT \
    --from $W/DRSTR001.DAT --json > /dev/null
fi
BAD=0
want() { w=$1; wr=$2; o=$(sh -c "$3" 2>&1); r=$?
  if [ "$r" != "$wr" ]; then echo "FAIL rc=$r (want $wr): $3"; BAD=$((BAD+1)); return 0; fi
  case $o in *"$w"*) echo "OK: $w";; *) echo "FAIL: want [$w] got [$(printf %s "$o" | tail -1)]"; BAD=$((BAD+1));; esac; }
want 'census: contained=1 intersects=0 outside=62 lattice=63 factory_tiles=45' 0 \
  "python3 tools/mesh_grid.py cover profiles/dolnoslaskie-test.json $FAC/MAPAL001"
want 'RESULT: PASS' 0 "python3 tools/cardcheck.py --root $FAC --fast"
want 'needs relocation: MAPAL001/B48R058R.DAT delta=+138994 slack=22272 extra_clusters=2 tail_free_run=0 tail_free_enough=False' 1 \
  "python3 tools/fit_census.py --image $IMG --tree $W"
want 'files=480 changed=0 fits=480 needs_relocation=0 not_on_image=0 total_delta=+0' 0 \
  "python3 tools/fit_census.py --image $IMG --tree $FAC"
want 'RESULT: PASS' 0 "python3 tools/cardcheck.py --image $S/p0.img"
want 'b0faf119ee2ccfb3ce757bafa49ba7bdac6730d32c8ac97a2337fb18e3c33237' 0 "sha256sum $S/p0.img"
want 'diffs: 586 range(s), outside: 0, metadata: 9' 0 \
  "python3 tools/imgpatch.py --check-diff --image $S/p0.img --reference $IMG --file MAPAL001/B48R058R.DAT --file DRSTR001.DAT --allow-metadata"
want 'diffs: 586 range(s), outside: 9, metadata: 0' 1 \
  "python3 tools/imgpatch.py --check-diff --image $S/p0.img --reference $IMG --file MAPAL001/B48R058R.DAT --file DRSTR001.DAT"
want 'tile_semantic] OK (B48R058R.DAT=2333602)' 0 \
  "python3 tools/l2check.py --root $W --no-golden --tiles B48R058R.DAT --semantic-tiles B48R058R.DAT --cmp-limit 20"
want 'Everything is Ok' 0 "7z t $S/p0.img"
want '0' 0 "python3 tools/one_tile_pipeline.py --help | awk '/--preserve-tile/{n++} END{print n+0}'"
want 'census: contained=0 intersects=4 outside=59 lattice=63 factory_tiles=45' 0 \
  "python3 tools/mesh_grid.py cover profiles/poland-full.json $FAC/MAPAL001"
want '1' 0 "awk '/\\*\\*M5.16 —/,/Claims:/' TODO.md | awk '/Status: blocked/{n++} END{print n+0}'"
want '1' 0 "awk '/\\*\\*M5.36 —/,/Claims:/' TODO.md | awk '/Status: open/{n++} END{print n+0}'"
want '0' 0 "awk '/tile_class_roundtrip/{n++} END{print n+0}' tools/l2check.py"
[ $BAD -eq 0 ] && echo 'card-ladder: all rows OK' || { echo "card-ladder: $BAD row(s) FAILED"; exit 1; }
```

The P0 card is 7.50 GiB on disk (`8057257984` B); delete `$S` once the EXP is written.

Nothing in this page registers a claim: it restates facts that already have
their IDs (`C-3060–C-3066` for the P0 card, `C-4470–C-4475` for the census,
`C-4560–C-4569` for the fit census). The rule-17 card number is the `sha256sum`
row above; `tools/map_signals.py` (H109) wraps the same four numbers in one
call and, once merged, replaces the hand-run block — this page cites it by path
rather than duplicating it.
