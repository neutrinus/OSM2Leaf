# EXP-2026-11-20-H103: `cardcheck --generate-fixture`, a deterministic no-vendor L1 tree

- **Status:** done
- **Date:** 2026-11-20
- **Sample:** none (tool-only task) — the fixture is generated in-process from
  committed modules (`tilewriter`, `ze0_tile_header`, `drstr_ze0`,
  `cmpind_writer`); it reads no image and no vendor file. The generated files'
  SHA-256s are in Observations so the tree itself is pinned.
- **Tools:** python3 3.15.0 / zlib 1.3.1 (`zlib-ng` build) for the primary run;
  python3.13 3.13.17 / zlib 1.3.2 (stock) for the cross-build control.
  `tools/cardcheck.py` at this branch (pre-change it has neither
  `--generate-fixture` nor `--selftest`); `tools/selftest.py`,
  `tools/claims_check.py`, `tools/todo_check.py`.
- **Claims:** C-4340–C-4349
- **Supersedes:** none
- **Superseded by:** none

## Question

Can `cardcheck` (the L1 whole-card validator) accept a card tree that no vendor
byte produced, deterministically and with no OSM input, so an L1 row can exist
on CI — and does that tree still fail when a check is broken?

## Hypothesis

`cardcheck`'s six root-source checks (`tree`, `headers`, `cmp`, `drstr`,
`mmain`, `version`) are structural, not semantic: a ZE0-format tree whose
level/box/header/count values come from the writer modules should pass them
with no tile *content*. A few inert literals are carried, not derived: the
`_fixture_header` 0x180 block is exactly `diff_years.synth_header`'s, the
`VER_INFO/HDD_INFO.TXT` body is exactly `one_tile_pipeline._synth_hdd_info()`'s,
and `check_version` asserts only the 6-line/printable/72-B shape, so neither
feeds a PASS number; the DRSTR `MMAIN001.DAT` checksum is a filename literal
that the file's content does not change. `mbr`, `fat` and `sha256` are image-only and must be
SKIP (never PASS) on a root tree. **Falsifier:** the tree passes while a
deliberately broken copy also passes (a check that cannot fail), or the two
runs are not byte-identical.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none — generated tree under `/tmp/opencode/h103-tree` (8 files, 9 dirs, 41,076 B) |
| SHA-256 | per-file hashes in Observations; no image sample |
| Offset(s) / VA(s) | none |
| Tool / version | `python3 3.15.0` / `zlib 1.3.1.zlib-ng`; control `python3.13 3.13.17` / `zlib 1.3.2` |
| Repo tool | `tools/cardcheck.py` (`--generate-fixture`, `--selftest`) |

## Method

1. **Sample and hash.** There is no input sample: the tool writes its own tree.
   The tree's file list and SHA-256s are recorded in Observations, so a rerun
   on the same interpreter must reproduce them exactly.
2. **Commands.** Runnable as written, in one block:

   ```bash
   # generate + validate in one run (H103 Done-when)
   rm -rf /tmp/opencode/h103-tree
   python3 tools/cardcheck.py --generate-fixture /tmp/opencode/h103-tree \
       --json /tmp/opencode/h103.json
   echo $?                                                    # 0

   # two runs must be byte-identical (determinism half)
   python3 tools/cardcheck.py --generate-fixture /tmp/opencode/h103-a --json-only
   python3 tools/cardcheck.py --generate-fixture /tmp/opencode/h103-b --json-only
   (cd /tmp/opencode/h103-a && find . -type f | sort | xargs sha256sum)
   (cd /tmp/opencode/h103-b && find . -type f | sort | xargs sha256sum) | diff - <(cd /tmp/opencode/h103-a && find . -type f | sort | xargs sha256sum)

   # selftest (determinism, 6 PASS, 2 SKIP, 2 negative controls; temp dir)
   python3 tools/cardcheck.py --selftest
   python3 tools/selftest.py --only cardcheck

   # unchanged paths: an extracted root and the vendor firmware head
   python3 tools/cardcheck.py --root /tmp/opencode/h103-tree --json /tmp/opencode/h103-root.json
   python3 tools/cardcheck.py --image archive/head256.img --json /tmp/opencode/h103-img.json

   # cross-build control: stock zlib
   python3.13 tools/cardcheck.py --generate-fixture /tmp/opencode/h103-313 --json /tmp/opencode/h103-313.json
   ```

3. **Controls.**
   - **Positive:** the generated tree passes all six root checks (a tree known
     to be well-formed must be found well-formed); the DRSTR search finds the
     tile name `B48R058R.DAT` (`idx >= 0`).
   - **Negative:** `--selftest` flips the first byte of the `B48R058R.DAT` entry
     in `DRSTR001.DAT` → `drstr` FAIL; it writes `0xBEEF` into a non-zero
     `MMAIN001.DAT` count → `mmain` FAIL. Both name the same check id the good
     tree passed, so a PASS is not vacuous.
   - **Vendor control:** `--image archive/head256.img` (the 256 MiB firmware
     head, not a complete card) still exits 1 with the *same per-check errors*
     as `tools/cardcheck.py` from `origin/main`, so the fixture work did not
     relax a check.

4. **Scope.** `tools/cardcheck.py` only, root-source checks. Covered:
   `tree`, `headers`, `cmp`, `drstr`, `mmain`, `version` on a single-level
   generated tree (one `MAPAL001/B48R058R.DAT`, `LEV3456R.DAT`, one
   `REFER001` `.cmp/.ind` pair, `CMP.LST`, `VER_INFO/HDD_INFO.TXT`).
   Excluded: `mbr`/`fat`/`sha256` (image-only — no FAT32 geometry in a root
   tree, reported SKIP with a reason), tile *content* semantics (an empty road
   set is accepted by design), and the `--image` path (unchanged).

5. **Falsifier.** Stated before the result: `cardcheck --generate-fixture`
   would not exist, or a broken copy of the tree would still pass.

## Observations

`--generate-fixture` run, exit 0:

```
L1 whole-card validation: /tmp/opencode/h103-tree
fixture=none (no vendor bytes)
  [mbr] SKIP (skipped=root source has no MBR)
  [fat] SKIP (skipped=root source has no FAT geometry)
  [tree] OK (files=8, dirs=9, bytes=41076)
  [headers] OK (files=3, ok=3)
  [cmp] OK (pairs=1, logical=576, stored=149, headers_ok=1, fast=False)
  [drstr] OK (nodes=10, table_end=400, entries=15, dirs=10, files=6)
  [mmain] OK (tiles=2, rows=11, ok=11)
  [version] OK (hdd_size=72)
RESULT: PASS
```

JSON: `ok=true`, `"fixture": "none"`, `counts={"pass":6,"fail":0,"skip":2}`;
every check row carries `status` and `skipped`. `--root` on the same tree:
`ok=true`, `counts={"pass":6,"fail":0,"skip":2}`, and **no** `fixture` key.

Generated file list (both runs identical, `diff` empty):

```
88883eb953dd526d56e56ce9de9afa957a8b4f0e4781fb4ced0ccd7547761162  ./CMP.LST                    19 B
ed9f4d1fdf81987d967f8956e5cc0025e74c7f5348c4b66fff9cbfefc2f9a4f8  ./DRSTR001.DAT              880 B
0d997f18c58ea6f7602dd83e3c12ed223de681addce9c3decdcbc3376a56d3f0  ./MAPAL001/B48R058R.DAT   31232 B
fb0a3d8272638b34bd5557583c5b49d9f8d0e79bac1d41364e546a3a2a6826de  ./MAPAL001/LEV3456R.DAT    4608 B
c06462c89353f14959a748a591fae48617a5f1fe721f59241178f1a711c59079  ./MMAIN001.DAT             4096 B
878adbd5481ec5561b4a6181115da348c319edc81dd84cc9715a2b3c24942441  ./REFER001/POINT001.DAT.cmp 149 B
bc598c346b479085d9e2f8439485a252e5231f477d38c1c52747172244a20478  ./REFER001/POINT001.DAT.ind  20 B
0466d76707bff35ea251b3aca8496342baf553f0f202fe64dffeed1a9b7d7610  ./VER_INFO/HDD_INFO.TXT      72 B
```

`--selftest` (18 checks, all ok, rc 0) includes: two runs byte-identical,
`fixture=none`, six PASS, `mbr`/`fat` SKIP with a reason, no FAIL, the DRSTR
positive control, the DRSTR negative control (`not ok`, failing id `drstr`),
the MMAIN positive control, the MMAIN negative control (`not ok`, failing id
`mmain`). `python3 tools/selftest.py --only cardcheck` → `cardcheck  PASS`.

Cross-build control: on python3.13/stock zlib the six root verdicts are
**identical** (`mbr SKIP, fat SKIP, tree/headers/cmp/drstr/mmain/version PASS`;
`counts` equal) and the run exits 0, but the raw bytes differ in **three**
files that pass through zlib. `sha256sum` of the python3 (3.15.0 / zlib
1.3.1.zlib-ng) vs python3.13 (3.13.17 / stock zlib 1.3.2) fixture runs:

```
MAPAL001/B48R058R.DAT      0d997f18c58ea6f7602dd83e3c12ed223de681addce9c3decdcbc3376a56d3f0  python3
                           ced1a8ec1507697c43bacac6aa851fc5514cc5330923b7641c3c3d7653367745  python3.13
REFER001/POINT001.DAT.cmp  878adbd5481ec5561b4a6181115da348c319edc81dd84cc9715a2b3c24942441  python3
                           2e16eccc5533ff9d6b6ac84916b8de556c4dc195445467aafffd0cbb2b0f0bd8  python3.13
REFER001/POINT001.DAT.ind  bc598c346b479085d9e2f8439485a252e5231f477d38c1c52747172244a20478  python3
                           aa0ee65e386cab2c05ef52879912e53a952ee3658032e80837ea652a7546f826  python3.13
```

The `.ind` differs because its chunk offsets are the `.cmp` chunk sizes. The
tree is byte-identical **per interpreter**; the module-level
`zlib.compressobj` output is not portable across zlib builds (AGENTS
"recompression needs stock zlib 1.3.1"). This does not affect any verdict or
the L1 exit code.

`--image archive/head256.img`: exit 1, `counts={"pass":1,"fail":7,"skip":0}`,
and each check's `errors` list equals `origin/main`'s `cardcheck.py` output for
the same image (only the new top-level `counts` key differs in the JSON).

`--selftest` runs with no source flag (rc 0), and a bare invocation still
prints the `one of the arguments --image --root --generate-fixture is required`
usage error and exits 2.

## Interpretation

- **FACT:** `cardcheck --generate-fixture DIR` writes a vendor-free tree and
  validates it in the same process; the run exits 0 with six PASS and two
  named SKIPs, and the JSON carries `fixture=none`.
- **FACT:** two consecutive runs on one interpreter produce byte-identical
  files; the selftest's negative controls make `drstr`/`mmain` FAIL on a
  one-field break, so the passing tree is a real test.
- **FACT:** the header (`_fixture_header`) is byte-identical to
  `diff_years.synth_header` (SHA-256 `b209b617…`) and the 72-B
  `VER_INFO/HDD_INFO.TXT` is byte-identical to
  `one_tile_pipeline._synth_hdd_info()` (`0466d767…`); `check_version` treats
  both as shape-only, so they are inert literals, not derived values.
- **FACT:** `mbr`/`fat`/`sha256` are SKIP with reasons on a root tree, not PASS.
- **OBSERVED:** the generator is byte-portable per interpreter, not across
  zlib builds (three files differ, the `.ind` with the `.cmp`); verdicts are
  invariant.
- **HYPOTHESIS:** none needed — this is a tool result, not a format claim.
- **UNKNOWN:** whether an L1 CI row built on this fixture catches the same
  defects as a vendor tree; that is H40/H104/H105's job (this is the primitive).

## Conclusion

`tools/cardcheck.py` now has `--generate-fixture DIR` (deterministic,
no-vendor, validates in the same run) and `--selftest` (temp-dir, no vendor
data), with `Check.status()`/`skipped` and `Report.finish()` emitting per-check
`status`, `skipped`, and top-level `counts`. The L1 validator can now be run on
a tree nobody produced from vendor bytes, which is what H40's CI row needs;
the fixture's committed baseline and `--break` negatives stay H104 and H105.
`--image` and `--root` behavior is unchanged. No format claim is added.
