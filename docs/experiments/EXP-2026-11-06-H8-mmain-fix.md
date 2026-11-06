# EXP-2026-11-06-H8: `mmain.py` re-scope, `setup.sh` patch path, doc sentences

- **Status:** done
- **Date:** 2026-11-06
- **Sample:** EU 2011 card image
  `LEAF_2011-2012_QSD-309-101_navi158_eu.img`,
  SHA-256 `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-1890–C-1894 (block C-1890–C-1899; rows not added to
  `claims.md` here)
- **Supersedes:** none (corrects `tools/mmain.py`, not a claim)
- **Superseded by:** none

## Question

H6 (`EXP-2026-11-06-H6-drstr-docs`) reported four leftovers: `tools/mmain.py`
parsed the FAT32 root directory while calling itself `MMAIN001.DAT`,
`setup.sh` could not apply its own patch, `AGENTS.md`/`tools/README.md` still
called `tools_ze0` a network clone, and `realcheck.py` should pin the
`coredll.dll` ordinals. Do the tools and guides now describe the objects they
really read?

## Hypothesis

None / corrective. The H6 observations are the specification: the real
`MMAIN001.DAT` at first cluster `0x10002` (4,096 B, SHA-256 `240e7c97…`) is the
header file; the FAT32 root directory is the object the old parser read; the
checked-in `tools_ze0/` equals the pin plus `ze0-tools.patch` applied with GNU
patch `-p2`.

## Inputs

| Item | Value |
| --- | --- |
| Image | `LEAF_2011-2012_QSD-309-101_navi158_eu.img` (7.5 GiB) |
| `MMAIN001.DAT` | byte range 4400763904–4400767999 (cluster `0x10002`), 4,096 B, SHA-256 `240e7c9774197fff0ea85276d463658d1291f4147970ccd5fdec60ffd23e9a05` |
| FAT32 root (control) | byte range 105796608–105862143 (`0x064e5400` + 64 KiB); first 4,096 B SHA-256 `fe24bbc82f20bd32633c08086baa3267a5761a6eae4c682f2a20fd668048a5aa` |
| Upstream | `albertbm/osm2clarion` at `07fbf78d049e7765db887818e77419ffc3dd499a` |
| Tools | Python 3.14.4 (`zlib 1.3.1`), GNU patch 2.8, git |

Ranged `curl` reads; the bytes stay in `/tmp/opencode/`, never in the repo.

## Method

```bash
# tool checks (synthetic)
python3 -m py_compile tools/mmain.py tools/realcheck.py
python3 tools/mmain.py --selftest
python3 tools/realcheck.py --selftest
bash -n tools/ze0-viewer/setup.sh
python3 tools/selftest.py

# real MMAIN001.DAT header and the old parser's real object (control)
curl -sS -r 4400763904-4400767999 -o /tmp/opencode/mmain.bin "$IMG"
python3 tools/mmain.py /tmp/opencode/mmain.bin --list
curl -sS -r 105796608-105862143 -o /tmp/opencode/root.bin "$IMG"
dd if=/tmp/opencode/root.bin of=/tmp/opencode/root4k.bin bs=4096 count=1
python3 tools/mmain.py /tmp/opencode/root4k.bin              # must refuse
python3 tools/mmain.py --fat-root /tmp/opencode/root4k.bin --list

# setup.sh: dry-run, real regenerate-and-compare, then the update branch
cd tools/ze0-viewer && ./setup.sh --dry-run
./setup.sh                  # network available here
./setup.sh --no-fetch --update
cd ../.. && git status --short tools/ze0-viewer/tools_ze0
```

## Observations

### `tools/mmain.py`

- Default mode parses the real header file:

  ```
  size=4096 sha256=240e7c9774197fff0ea85276d463658d1291f4147970ccd5fdec60ffd23e9a05
  header: clarion='CLARION' hitachi='HITACHI' model='CLA-NAVI05-01' format='FORMAT VERSION X08-02-00' data='DATA VERSION 11/06/27/01' version='V05.00.00'
  bounds@0x184=4800,1280,-1200,4080
  bounds@0x5d0=1280,-1200 consistent=True
  codes@0x18c=05 04 02 07 0a 06 08 14 (8)
  tables=3 entries=11
    section 01: 6 rows, total=1903
      level=6 type=0x80 count=1
      level=5 type=0x90 count=1
      level=4 type=0x91 count=1
      level=3 type=0x91 count=45
      level=2 type=0x91 count=138
      level=1 type=0x92 count=1717
    section 02: 4 rows, total=1662
      level=5 type=0x91 count=1
      level=4 type=0x91 count=1
      level=2 type=0x91 count=124
      level=1 type=0x90 count=1536
    section 04: 1 rows, total=935
      level=1 type=0x93 count=935
  roundtrip=OK
  ```

- The old parser, now `--fat-root`, on the root directory's first 4,096 B:

  ```
  records=51 deleted=39 live=12
    MMAIN001.DAT attr=ARC  cluster=0x10002 size=4096
    BICON001     attr=DIR  cluster=0x10003 size=0
    ...
  roundtrip=OK
  ```

  The listing now combines the FAT32 cluster high word (`+0x14`) and low word
  (`+0x1a`); before it printed `cluster=0x0002`, the exact number that made
  M4.5 read the root directory (C-1722).

- Default mode on the same root bytes exits 2:

  ```
  mmain: not an MMAIN001.DAT header: 0x000 is not UTF-16BE 'CLARION' (a FAT32 root directory needs --fat-root)
  ```

- `--selftest` builds one synthetic header (all six text fields, prefix, four
  bounds, 8 codes, `3f`/`ff` runs, 3 tables / 11 entries, `0x5d0` repeat,
  terminator at `0x1e0`) and one synthetic root directory (one live entry with
  `cluster_hi=1`/`cluster=2`, one `0xE5` entry); both parse → write →
  byte-identical, a 10-byte blob is refused, and a root directory is refused by
  the header parser. Output: `selftest: OK` (exit 0).

### `tools/realcheck.py`

- Exports pin now carries all nine `coredll.dll` ordinals used by the two M2.1
  functions (`realcheck.py` `PINS`): names `1651`, ordinals 719 `sprintf`,
  1145 `_wfopen`, 1143 `fgetws`, 59 `wcschr`, 66 `wcsncpy`, 1047 `memset`,
  1118 `fclose`, 496 `Sleep`, 65 `wcsncmp`.
- `--selftest`: `realcheck selftest: 16 checks OK (synthetic CE ROM, no vendor
  data)` (exit 0); the new guards are "real exports pin: 1651 names", "real
  exports pin: C-1710 ordinals exact" and "selectors cover expected ordinals".

### `tools/ze0-viewer/setup.sh`

- `--dry-run` prints the exact command list and exits 0 without touching
  anything: mkdir, clone, fetch, checkout pin, `rm -rf`/`cp -a` into
  `vendor/tools_ze0.new`, copy `PROVENANCE.md`, `patch -d … -p2 --dry-run`,
  `patch -d … -p2`, and the compare step.
- Real run (network to GitHub was available; the clone is git-ignored):

  ```
  Klonowanie do „…/tools/ze0-viewer/vendor/osm2clarion”...
  checking file bg_decode.py
  checking file clarion_bg.py
  checking file clarion_tile.py
  checking file inflate_tile.py
  checking file tile_grid.py
  checking file tile_scan.py
  patching file bg_decode.py
  … (6 files)
  tools_ze0 matches the pinned upstream plus ze0-tools.patch.
  left the checked-in copy untouched (--update replaces it).
  ```

  Exit 0. The patch applies with `patch -p2` because both `a/tools/x.py` and
  `b/tools_ze0/x.py` reduce to `x.py` in the staging directory; the pin is
  checked with `git rev-parse HEAD` before the patch step.
- `--no-fetch --update` replaced `tools_ze0/` from the rebuild, exit 0;
  `git status --short tools/ze0-viewer/tools_ze0` listed only the deliberately
  edited `PROVENANCE.md` (no `.py` changed), and 46 `.py` modules remain.
- `bash -n tools/ze0-viewer/setup.sh` is silent (exit 0).

### Docs and the repository self-test

- `AGENTS.md`: the repo-shape bullet now says `tools_ze0/` is checked in and
  `setup.sh` only audits/regenerates it; the verification ladder no longer runs
  `./setup.sh` before `harness.py` (the harness imports the checked-in copy and
  needs no network).
- `tools/README.md`: same two statements; the setup commands moved to an
  "only after a pin or patch change" block; the `realcheck` paragraph lists the
  C-1710 ordinals.
- `tools/ze0-viewer/tools_ze0/PROVENANCE.md`: the "Regenerate" sentence now
  describes rebuild-compare-`--update` and points at
  `docs/format/ze0-tools.md`; the harness/sys.path fact is stated.
- `python3 tools/selftest.py` tail, final run:

  ```
  tool:validate_mutation  SKIP  no --selftest
  tool:verify             SKIP  no --selftest
  tool:zlibinfo           PASS  0.04s

  passed=34 failed=0 skipped=19 total=53 time=2.27s
  selftest: OK
  ```

  One intermediate run `FAIL`ed on `tool:tile_diff` (exit 1, "offset view
  misreads the move as add+remove") while another agent was editing that file
  concurrently (`M tools/tile_diff.py`); the H8 suites never failed —
  `selftest.py --only mmain --only realcheck` → `passed=2 failed=0`, exit 0 —
  and the final full run above is green after that edit settled.

## Interpretation

- **FACT:** The default reader of `tools/mmain.py` is now the real
  `MMAIN001.DAT` header parser and re-verifies every field H6 reported on the
  card: UTF-16BE identity, `0x184` bounds `4800/1280/−1200/4080`, the `0x5d0`
  pair equal to bounds 2–3, the 8 codes, and a 3-table/11-tuple descriptor
  ending at `0x1e0` (C-1890).
- **FACT (control):** The same tool, with `--fat-root`, reproduces the old
  parser's 51 records / 39 deleted / 12 live and the old round-trip on the real
  root directory, and the default mode refuses those bytes with a `--fat-root`
  hint. The mis-read is now impossible to repeat silently (C-1890).
- **OBSERVED:** Per-section `0x1ac` totals on the EU 2011 file are 1903
  (section 1), 1662 (section 2), 935 (section 4); section 1 matches the sum of
  the published counts 1/1/1/45/138/1717 (C-1894).
- **FACT:** `setup.sh` is now a working regeneration/audit path: clone the pin,
  rebuild in `vendor/tools_ze0.new` with `patch -p2`, compare, optional
  `--update`. The rebuilt tree is byte-identical to the checked-in 46 modules
  and `PROVENANCE.md`, so the checked-in copy is exactly pin + patch (C-1891).
- **FACT:** The three guide sentences now state the checked-in-copy-first
  model, the same model as `docs/format/ze0-tools.md` (C-1892).
- **FACT:** `realcheck.py` pins the full C-1710 ordinal map, not just 719
  (C-1893).
- **UNKNOWN / not done here:** `harness.py verify` on a factory tile (no tile
  in this checkout; `tools_ze0/*.py` were not edited, so the five pinned tiles
  are unaffected), and the real `realcheck.py IMG256` run (still H7's open
  step). `setup.sh --update` was exercised only on an identical rebuild.

## Claims

Rows for the ledger task; H8 does not edit `claims.md`.

| ID | Claim | Status | Confidence | Evidence / Supersedes |
| --- | --- | --- | --- | --- |
| C-1890 | `tools/mmain.py` has two explicitly named parsers: `parse_mmain`/`write_mmain` for the 4,096-byte `MMAIN001.DAT` header (UTF-16BE common header, `0x184` big-endian i16 bounds, `0x18c` codes, `0x1ac` three-table descriptor) and `parse_fat_root`/`write_fat_root` for the FAT32 root directory, the latter reachable only through `--fat-root`. Both round-trip synthetically; on the EU 2011 card the header round-trips byte-identically (SHA-256 `240e7c97…`) and the root directory is refused by the default mode with a `--fat-root` hint. | VERIFIED | H | this EXP; `tools/mmain.py --selftest`; ranged read of the published image; C-1720/C-1721/C-1722 |
| C-1891 | `tools/ze0-viewer/setup.sh` regenerates `tools_ze0/` from the pin `07fbf78d…` plus `ze0-tools.patch` by copying upstream `tools/` to `vendor/tools_ze0.new` and applying the patch with GNU `patch -p2` (both `a/tools/…` and `b/tools_ze0/…` reduce to `x.py`); the rebuild is byte-identical to the checked-in 46 modules plus `PROVENANCE.md`. `--dry-run` prints the commands, default mode compares and exits 1 on drift, `--update` replaces the copy. | VERIFIED (tool/process) | H | this EXP; `./setup.sh`, `--dry-run`, `--no-fetch --update` |
| C-1892 | `AGENTS.md`, `tools/README.md` and `tools_ze0/PROVENANCE.md` state that `tools_ze0/` is the checked-in copy `harness.py` imports and that `setup.sh` is only its audit/regeneration path (network, `vendor/` clone); the verification ladder runs `harness.py` without `setup.sh`. This matches `docs/format/ze0-tools.md`. | VERIFIED (docs) | H | this EXP; `docs/format/ze0-tools.md`; C-1725 |
| C-1893 | `tools/realcheck.py` pins the C-1710 `coredll.dll` ordinal map in its `exports` check: 1651 names, 719 `sprintf`, 1145 `_wfopen`, 1143 `fgetws`, 59 `wcschr`, 66 `wcsncpy`, 1047 `memset`, 1118 `fclose`, 496 `Sleep`, 65 `wcsncmp`; the self-test guards the map and the selector list. | VERIFIED (tool, synthetic); pin OBSERVED (C-1710/C-527) | H | this EXP; `realcheck.py --selftest`; C-1710, C-527 |
| C-1894 | On the EU 2011 `MMAIN001.DAT` the `0x1ac` per-section totals are 1903 (section `01`), 1662 (`02`) and 935 (`04`), with 6/4/1 rows; section `01` is the published 1/1/1/45/138/1717 sum. `0x5d0` holds 1280/−1200, equal to bounds 2–3 of `0x184`. | OBSERVED | H | this EXP; `tools/mmain.py` on the filed read; C-164, C-1724 |

## Conclusion

- `tools/mmain.py` now reads `MMAIN001.DAT` by default, round-trips the real
  4 KiB file, and keeps the FAT32 root-directory parser under the explicit
  `--fat-root` name; the old trap is detectable (default mode refuses root
  bytes) and the listing prints the full 32-bit cluster.
- `tools/ze0-viewer/setup.sh` is usable: dry-run, rebuild-and-compare, and
  `--update` all exit 0, and the rebuild matches the checked-in copy exactly.
- The `AGENTS.md`, `tools/README.md` and `PROVENANCE.md` sentences now match
  `docs/format/ze0-tools.md`; the harness needs no network or `setup.sh`.
- `tools/realcheck.py` pins the C-1710 ordinal map and guards it in the
  synthetic self-test. No vendor bytes entered the repository.

## Follow-ups

- [ ] Update `docs/format/ze0-tools.md` "What `setup.sh` does, and why it is
      not the regeneration path": the script is now a working
      rebuild/compare/`--update` path, so that section (and its "needs fixing"
      sentence) is stale. H8's file list excluded the format doc.
- [ ] Run `harness.py verify` on the five pinned tiles and
      `python3 tools/realcheck.py IMG256` where the data is available.
- [ ] Map the `0x18c` codes and decode `0x1e0`–`0x1000` (still H6 follow-ups).
