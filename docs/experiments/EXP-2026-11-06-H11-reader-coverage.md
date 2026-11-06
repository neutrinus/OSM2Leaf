# EXP-2026-11-06-H11: Reader-coverage matrix for every generated file type

- **Status:** done
- **Date:** 2026-11-06
- **Sample:** EU 2011 image `LEAF_2011-2012_QSD-309-101_navi158_eu.img`,
  SHA-256 `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`;
  US 2011 and 2014/2016 statements are restated from their own EXPs, not
  re-measured here
- **Claims:** none created — `docs/research/claims.md` is read-only for H11;
  the reserved block C-2170–C-2179 is intentionally unused
- **Supersedes:** none
- **Superseded by:** none

## Question

For every file type the OSM compiler must write (or copy), how far are we from
"the firmware reads it correctly", and which reader or L3 target has no task?

## Hypothesis

None / exploratory. The expected outcome is a bookkeeping page whose cells can
be checked against the claim ledger and `TODO.md`, not a new format fact.

## Inputs

| Item | Value |
| --- | --- |
| Card tree | `docs/format/sd-card-layout.md` top-level listing |
| Format docs | `docs/format/*.md` |
| Claim ledger | `docs/research/claims.md` (read-only) |
| L3 targets | `tools/l3_harness/targets.json` |
| Task board | `TODO.md` M3/M8/M9/M5 |
| Test plan | `docs/research/card-test-plan.md` |
| Tools | Python 3 stdlib only; `tools/cardcheck.py`, `tools/l2check.py`, `tools/l3_harness/runner.py` |

## Method

1. Read the tree listing and every `docs/format/*.md` page; map each file
   family to its format doc and writer tool.
2. Cross-check each writer/tool state with its docstring, `--selftest` and the
   cited EXP; mark it `exists`, `partial`, `none` or `copy`.
3. Cross-check each reader state against the claims that name a VA. A path or
   filename load (`0x004125a8`, `0x0040a014`) is **partial**, not a reader.
4. Read `tools/l3_harness/targets.json`; copy every `blocked`/`synthetic`
   state and refusal rule verbatim in meaning. No target was run.
5. Read `TODO.md` to attach M3/M9 task IDs; list rows with no task as gaps and
   propose next-free claim blocks, without editing `TODO.md` (H11 ownership).
6. Write `docs/research/reader-coverage.md`; add one link line each to
   `docs/research/roadmap.md` and `README.md`.

Checks run:

```bash
python3 tools/claims_check.py
python3 tools/selftest.py
```

## Observations

### Row and status counts (from the table itself)

| Measure | Count |
| --- | --: |
| Matrix rows | 30 |
| `generate · exists` | 6 |
| `generate · partial` | 5 |
| `generate · none` | 10 |
| `copy` | 9 |
| Reader `located` | 5 |
| Reader `partial` (load/path only) | 4 |
| Reader `unlocated` | 12 |
| Reader `not needed` | 7 |
| Not a file reader (card mount) | 1 |
| No semantic check located (common header) | 1 |

### Located readers (claim-backed)

| File | Reader | Claim / EXP |
| --- | --- | --- |
| `MMAIN001.DAT` | `0x0041a438` → open `0x0041b780`, read `0x0041b954` | C-1780–C-1789; EXP-M3.8 |
| `DRSTR001.DAT` | `0x00419684` → parser `sub_00419350` | C-850–C-859, C-1860–C-1869; EXP-M3.4/M3.10 |
| `CMP.LST` | `0x0041ba90` (open/close only) | C-1866, C-1869; EXP-M3.10 |
| `RDSTM001.DAT` | `0x003bc960` decoder, 12 getters, `0x003f61bc` field directory | C-882–C-884; EXP-M3.7 |
| `VER_INFO/HDD_INFO.TXT` | `0x004e7b8c`; comparator `0x03bd2ad8` | C-721–C-728, C-766; EXP-M2.1/M2.5 |

### Unlocated record readers (12 rows)

`.cmp`/`.ind` chunk reader (M3.2b), `COORD001` (M3.14), `ZCODE0nn` (M3.14),
`ICODE001` (M3.14), `POINT0nn` (M3.11), `ADDRE0nn` (M3.13), `INTER0nn`
(M3.16), `FRWAY0nn` (M3.16), `ICADM0nn` (no task), `ZIPFR001` (no task),
tile sections 2 and 4 (M3.6).

Partial readers: `INDEX003.DAT` (load `0x004125a8`, record walk unlocated,
M3.12), `MAPAL001` tile (VAs `0x0041f26c`/`0x004259bc`/`0x0042757a`, no
runnable entry, M3.5/M3.6), `LEV3456R.DAT` (filename load `0x0040a014`, M3.4),
`LCTBL001.DAT` (load `0x004125a8`, M3.15).

### L3 targets

Six entries in `targets.json`: `probe-zlib-cmf` (synthetic, runs and proves
only the runner/stub pipeline), and `hddinfo_compare`, `cmp_ind_reader`,
`tile_reader`, `drstr_parser`, `mapcode_comparator` (all `blocked`, exit 4).
No L3 verdict exists for any map file.

### Verification output

```
$ python3 tools/claims_check.py
duplicate claim IDs: 0
unregistered proposed claims: 0
bad annotations: 0
claims_check: OK
```

First `selftest.py` run during this task:

```
passed=42 failed=1 skipped=18 total=61
selftest: FAILED
tool:imgpatch  FAIL  exit 2
  FAIL: same-length: only one data write
  FAIL: shrink: diffs inside the planned writes
  FAIL: copy: diffs only in the file cluster and the copy
```

Final `selftest.py` run after the untracked `tools/imgpatch.py` (M5.13 scope)
was updated by its own owner in this worktree:

```
$ python3 tools/selftest.py 2>&1 | tail
passed=43 failed=0 skipped=18 total=61 time=10.72s
selftest: OK
```

The transient failure was outside H11 (no H11 file is imported by
`imgpatch.py`) and disappeared without an H11 change.

## Interpretation

- **FACT:** the matrix has 30 rows; 6 writers exist, 5 are partial, 10 families
  have no writer, and 9 rows are copy-only.
- **FACT:** 12 matrix rows have no record-walking reader at all; 4 more have
  only a filename/path load anchor.
- **FACT:** no L3 target has produced a verdict; all real targets are
  `blocked`, and the only runnable target is a synthetic pipeline probe.
- **OBSERVED:** the coverage is uneven in a specific way — the manifest layer
  (`MMAIN001`, `DRSTR001`, `CMP.LST`) and `HDD_INFO` have located readers,
  while the data families the compiler actually has to generate (`POINT`,
  `ADDRE`, `COORD`, `ZCODE`, `ICODE`, `LCTBL`, `RDSTM`) do not. A generated
  POI/address layer would therefore be unproven even if L1/L2 pass.
- **OBSERVED:** the tile writer is the most advanced generator (byte-identical
  factory rebuilds and a roads-only splice), but the firmware reader for it is
  only named, not runnable, and section 4 cannot yet be built.
- **HYPOTHESIS:** the cheap next wins are M3.2b (unblocks the `.cmp` reader and
  M9.11), M3.11 (unblocks M9.10/S2), and M9.6 (the only L3 target whose address
  and corpus already exist).
- **UNKNOWN:** whether any generated tile, address or name layer is accepted by
  a real unit; no F4 or car result exists.

## Conclusion

Created [`docs/research/reader-coverage.md`](../research/reader-coverage.md)
with 30 rows and linked it from
[`roadmap.md`](../research/roadmap.md) and [`README.md`](../../README.md).
No format doc or claim changed. No existing status was promoted: every reader
claim is quoted from `claims.md`, and every L3 cell is `blocked`, `planned` or
`—`.

Gaps recorded in the new page (not added to `TODO.md`, which H11 does not
own): M9.17 `mmain_reader` (G1), M3.18 `ICADM`/`ZIPFR` readers (G2), M4.21
section-4 writer (G3), M5.16 `LEV3456R` generator (G4), M5.17 `LCTBL001`
writer (G5), M5.18 `ADDRE`/`ZCODE`/`ICODE`/`COORD` writers (G6), M5.19
`RDSTM001` writer (G7), M9.18 `LEV3456R`/section L3 targets (G8).

## Follow-ups

- [ ] Coordinator: insert G1–G8 into `TODO.md` with the proposed claim blocks
      (next free starts at C-2290) and re-block if another task takes an ID.
- [ ] M3.2b: locate the `inflate` caller and loop over `chunk_offset[]`.
- [ ] M3.11 / M3.13: locate the `POINT` record walk and the `ADDRE` readers;
      they gate M9.10 and M9.15.
- [ ] M5.4: run `tilewriter` on the real `B48R058R` factory tile and pass L2.
- [ ] Re-check this matrix after every M3/M5/M9 merge; row changes belong to
      those PRs (see "How to keep this current").
