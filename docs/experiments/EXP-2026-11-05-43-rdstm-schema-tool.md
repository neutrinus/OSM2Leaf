# EXP-2026-11-05-43: RDSTM schema hypothesis harness

- **Status:** done (synthetic only; `RDSTM001.DAT` not measured)
- **Date:** 2026-11-05
- **Sample:** synthetic 8192-byte `RDSTM001`-shaped blob and 8356-byte
  `LCTBL001`-shaped blob; no vendor data in this task
- **Claims:** C-104, C-105, C-106 (unchanged); proposed C-534/C-535/C-536 (not
  added to the ledger)
- **Supersedes:** none
- **Superseded by:** none

## Question

Can a standard-library harness rank candidate `RDSTM001` record framings,
check a user-supplied field layout as a graph, and measure a 2-byte-code join
to `LCTBL001` — without decoding anything and without vendor data?

## Hypothesis

The sample already rules out compression and inline names (C-104), links the
two files by 2-byte code (C-105) and shows the row framing drifting at
`0x10a0` (C-106). A scoring harness can therefore be built and self-tested
on synthetic bytes, even though it cannot confirm the `0x1000` record size or
any field meaning. The self-test is the control: a synthetic file built from a
known layout must rank that layout first and join at 100%.

## Inputs

| Item | Value |
| --- | --- |
| Vendor image / file | none (no vendor data in this task) |
| Synthetic RDSTM | 8192 bytes, 256 records of 16 bytes, SHA-256 `416b8c8bdd00839f5e42e1ab86e1a4e4cdecbb9e65425274ec62be2659755de9` |
| Synthetic LCTBL | 8356 bytes, 32 catalog codes + 32 names, SHA-256 `ec35f059f2f34b429186ea702f1de5e216c7906e6cb4f6ce49dc021c84b7b015` |
| Tool | `tools/rdstm_schema.py` (stdlib only, Python 3.10+) |

The synthetic RDSTM blob is pure `struct` output and is byte-deterministic.
The synthetic LCTBL blob contains one zlib stream, so its SHA-256 pins this
machine's zlib build (same caveat as EXP-2026-11-05-42).

Layout used by the synthetic file (the "true" layout):

```
link=0:u16:id,4:u32:ref,8:u16:src,10:u16:dst,12:u16:code,14:u16
```

`ref` is an absolute offset into the same window, `src`/`dst` form reciprocal
pairs, and `code` cycles over the 32 catalog codes `0x4a80..0x4a9f`.

## Method

```bash
python3 -m py_compile tools/rdstm_schema.py
python3 tools/rdstm_schema.py --selftest
```

The self-test writes no files: it builds both blobs in memory, runs the
scanner over the default grid (`--block-size 0x400,0x1000,0x4000` x
`--record-size 2..64`), decodes the true layout, and calls the join probe.

CLI control runs on the same synthetic blobs written to `/tmp/opencode/rs/`:

```bash
python3 tools/rdstm_schema.py scan /tmp/opencode/rs/RDSTM001.DAT --top 12 --length 0
python3 tools/rdstm_schema.py layout /tmp/opencode/rs/RDSTM001.DAT \
  --layout "link=0:u16:id,4:u32:ref,8:u16:src,10:u16:dst,12:u16:code,14:u16" \
  --record-size 0x10 --lctbl /tmp/opencode/rs/LCTBL001.DAT
python3 tools/rdstm_schema.py join /tmp/opencode/rs/RDSTM001.DAT \
  --lctbl /tmp/opencode/rs/LCTBL001.DAT --code-offset 0xc --record-size 0x10 --length 0
python3 tools/rdstm_schema.py join /tmp/opencode/rs/RDSTM001.DAT \
  --lctbl /tmp/opencode/rs/LCTBL001.DAT --code-offset 0xe --record-size 0x10 --length 0
```

The last command is a negative control: `+0xe` is the padding field, so it
must not join.

## Observations

`py_compile` and the self-test:

```text
py_compile: OK
synthetic RDSTM 8192 bytes, sha256 416b8c8bdd00839f5e42e1ab86e1a4e4cdecbb9e65425274ec62be2659755de9, 256 records of 16 bytes
synthetic LCTBL 8356 bytes, sha256 ec35f059f2f34b429186ea702f1de5e216c7906e6cb4f6ce49dc021c84b7b015, 32 names
scan (top 6)
   1 block 0x0400 record  16 score 0.841 align 0.644 small 0.750 pointer 1.000 shape 0.992
   2 block 0x1000 record  16 score 0.838 align 0.634 small 0.750 pointer 1.000 shape 0.992
   3 block 0x4000 record  16 score 0.838 align 0.634 small 0.750 pointer 1.000 shape 0.992
   4 block 0x0400 record  64 score 0.812 align 0.654 small 0.750 pointer 1.000 shape 0.984 multiple of 16
   5 block 0x0400 record  32 score 0.812 align 0.647 small 0.750 pointer 1.000 shape 0.992 multiple of 16
   6 block 0x1000 record  64 score 0.811 align 0.650 small 0.750 pointer 1.000 shape 0.984 multiple of 16
  -> top record size 16, score 0.841
layout link: 256 records, reciprocity 100.0%, back-reference 100.0%, pointers 100.0%
join: 256 codes, 32 unique, index hit 100.0%, catalog 100.0%, prefix 100.0%
selftest: OK
```

Full ranked grid, as printed by `scan`:

```text
file           /tmp/opencode/rs/RDSTM001.DAT
size           8192
sha256         416b8c8bdd00839f5e42e1ab86e1a4e4cdecbb9e65425274ec62be2659755de9
window         0x1000 + 0x0
grid           blocks 3 x records 13
tolerance      0.03 (multiple-of penalty)
weights        align=0.30 small=0.20 pointer=0.25 shape=0.25
rank   block record  score  align  small pointer  run  shape shapes  note
   1   0x400     16  0.841  0.644  0.750   1.000   64  0.992      3
   2  0x1000     16  0.838  0.634  0.750   1.000  256  0.992      3
   3  0x4000     16  0.838  0.634  0.750   1.000  256  0.992      3
   4   0x400     64  0.812  0.654  0.750   1.000   16  0.984      2  multiple of 16
   5   0x400     32  0.812  0.647  0.750   1.000   32  0.992      2  multiple of 16
   6  0x1000     64  0.811  0.650  0.750   1.000   64  0.984      2  multiple of 16
   7  0x4000     64  0.811  0.650  0.750   1.000   64  0.984      2  multiple of 16
   8  0x1000     32  0.810  0.639  0.750   1.000  128  0.992      2  multiple of 16
   9  0x4000     32  0.810  0.639  0.750   1.000  128  0.992      2  multiple of 16
  10   0x400     48  0.809  0.640  0.750   1.000   21  0.988      2  multiple of 16
  11  0x1000     48  0.807  0.633  0.750   1.000   85  0.988      2  multiple of 16
  12  0x4000     48  0.807  0.633  0.750   1.000   85  0.988      2  multiple of 16
note           scores rank hypotheses; 'multiple of N' marks a framing explained equally well by a smaller record size
```

Layout and graph checks:

```text
layout         link
spec           link=0:u16:id,4:u32:ref,8:u16:src,10:u16:dst,12:u16:code,14:u16
record size    0x10  records 256  window 0x1000+0x1000
fields
       f0000 +0x00   u16   id  min 0x0 max 0xff distinct 256 small 1.00 pointer 0.00
       f0004 +0x04   u32  ref  min 0x1000 max 0x1ff0 distinct 256 small 0.00 pointer 1.00
       f0008 +0x08   u16  src  min 0x0 max 0xff distinct 256 small 1.00 pointer 0.00
       f000a +0x0a   u16  dst  min 0x0 max 0xff distinct 256 small 1.00 pointer 0.00
       f000c +0x0c   u16 code  min 0x4a80 max 0x4a9f distinct 32 small 0.00 pointer 0.00
       f000e +0x0e   u16    -  min 0x0 max 0x0 distinct 1 small 1.00 pointer 0.00
graph          256 edges over 256 records, 0 out of range
  reciprocity  100.0% (256 pairs)  self loops   0.0%
  targets      256 distinct, back-reference 100.0%  node coverage 100.0%
codes          256 occurrences, 32 unique
index hit      100.0% occurrences, 100.0% unique
  catalog      100.0% occurrences, 100.0% unique (32 catalog codes)
  name prefix  100.0% occurrences, 100.0% unique (32 prefixes, 32 names)
```

Join probe, correct offset and native control:

```text
code           offset 0xc type u16
records        256 at 0x10 from 0x1000
lctbl index    1 streams, 896 plain bytes, 32 names
codes          256 occurrences, 32 unique
index hit      100.0% occurrences, 100.0% unique
  catalog      100.0% occurrences, 100.0% unique (32 catalog codes)
  name prefix  100.0% occurrences, 100.0% unique (32 prefixes, 32 names)
```

```text
code           offset 0xe type u16
records        256 at 0x10 from 0x1000
lctbl index    1 streams, 896 plain bytes, 32 names
codes          256 occurrences, 1 unique
index hit        0.0% occurrences,   0.0% unique
  catalog        0.0% occurrences,   0.0% unique (32 catalog codes)
  name prefix    0.0% occurrences,   0.0% unique (32 prefixes, 32 names)
```

The tool is also picked up by the repository runner:

```text
python3 tools/selftest.py --only rdstm_schema --verbose
tool:rdstm_schema  PASS  0.12s
passed=1 failed=0 skipped=0 total=1 time=0.12s
selftest: OK
```

## Interpretation

- **FACT:** the true 16-byte layout ranks first in all three block windows
  (0.841 / 0.838 / 0.838); the 32-, 48- and 64-byte framings score 0.807–0.812
  after the documented `multiple_of 16` penalty.
- **FACT:** the 8-byte framing scores 0.533 (`shape` 0.498) because the
  pointer/target fields alternate across the two 8-byte phases; `shape` is the
  metric that separates a half-record from the record.
- **FACT:** the layout extractor recovers 256/256 records, 0 out-of-range
  tuples and 100 % reciprocity, back-reference and pointer rate.
- **FACT:** the join probe reports 100 % at `+0xc` and 0 % at the padding
  offset `+0xe`; the probe therefore discriminates rather than always hitting.
- **OBSERVED:** block size changes only the sample count; `0x400` vs `0x1000`
  differ by ~0.003 in `align` on the same distribution, which is sampling
  noise, not structure.
- **OBSERVED:** `align` alone cannot separate a record from two half-records,
  so the multiple-of rule is explicit in `rank_rows` and the penalty is
  printed as `--tolerance`; the raw score stays in `--json` as `score_raw`.
- **HYPOTHESIS:** unchanged — `0x1000` rows and the graph-tuple reading of the
  `0x1a700` arrays. A score cannot promote a hypothesis to a claim.
- **UNKNOWN:** every field meaning, the speed/one-way/turn restrictions, and
  the real-file scores (no vendor data here).
- **NOT TESTED:** `RDSTM001.DAT` itself; a run on the sample is the next step.

## Conclusion

`tools/rdstm_schema.py` adds a synthetic, stdlib-only protocol for the three
questions the sample leaves open: which framing fits, whether a layout behaves
like a graph, and whether a 2-byte code joins to `LCTBL001`. The
"Status: what the sample supports" table and the ranked-unknown list in
`docs/format/rdstm.md` now separate the verified container facts from the
unverified record/graph hypotheses. No field is decoded and no claim is
promoted.

Proposed ledger rows (scoped out of this task; `claims.md` was not edited):

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-534 | `tools/rdstm_schema.py` scores `--block-size` x `--record-size` framings by column diversity, small-int density, in-window `u32` pointers and modal tuple shape, applies a printed `multiple_of` penalty for primitive periods, and ranks the true layout first on a synthetic 16-byte fixture built from `link=0:u16:id,4:u32:ref,8:u16:src,10:u16:dst,12:u16:code,14:u16`. | VERIFIED (tool, synthetic) | M | EXP-2026-11-05-43; `python3 tools/rdstm_schema.py --selftest` |
| C-535 | The layout extractor decodes a user layout and reports graph reciprocity, back-reference and pointer rates; on the synthetic graph it reproduces 256/256 records, 0 out-of-range tuples and 100 % on all three checks. High reciprocity is consistent with — but does not prove — a `(src, dst)` reading. | VERIFIED (tool, synthetic) | M | EXP-2026-11-05-43; `layout` output above |
| C-536 | The join probe reports the share of 2-byte codes that occur as LCTBL catalog codes or name-string prefixes (`+0xc` → 100 %, padding `+0xe` → 0 % on the synthetic fixture). The rate is a necessary condition for a name-index mapping, not a decoded index; the real-file rate is unmeasured. | VERIFIED (tool, synthetic) | M | EXP-2026-11-05-43; `join` output above |

## Follow-ups

- [ ] Run `scan` on `RDSTM001.DAT` and record the ranked table and the
  `multiple_of` flags; do not promote a framing on one table.
- [ ] Run `layout` with the documented `0x1a700` tuple arrays as a `src`/`dst`
  layout and compare reciprocity with the `0x1000` rows.
- [ ] Run `join` on the real pair and compare the catalog/prefix rates with
  C-105's 10/16.
- [ ] Only after a measured, reproducible table: update the `HYPOTHESIS` rows
  in `docs/format/rdstm.md` and add the claim to the ledger.
