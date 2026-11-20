# EXP-2026-11-20-H19: Re-run of the five thinnest records of 2026-11-20

- **Status:** done
- **Date:** 2026-11-20
- **Sample:** `archive/head256.img` (EU 2011 IMG256, SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`); full EU
  2011 card `LEAF_2011-2012_QSD-309-101_navi158_eu.img` (SHA-256
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`), files
  extracted read-only to `/home/user/scratch/factory-eu/`:
  `RDSTM001/RDSTM001.DAT` `f822044c0aab75327b9fb484e9a4c7c8dd5938b21efaacec0e5b2d8b23ab3e49`,
  `RDSTM001/LCTBL001.DAT` `8cab17754114b5f7ca47d4f46d55c95c6acf841629e1fcc42e6da45063353e9d`,
  `MAPAL001/LEV3456R.DAT` `08a584feacf049cc39260ff29f742c3dcf1b53059cb98bd3e9798e7ab819df35`,
  `CMP.LST` `88883eb953dd526d56e56ce9de9afa957a8b4f0e4781fb4ced0ccd7547761162`,
  `REFER001/ADDRE001.DAT.ind` `98030b99834c30cd87c64d39f3f31ba94c6067248ce41529689baebe6a5df540`,
  `REFER001/ADDRE001.DAT.cmp` `bbeb60f242a57f297d2d2c6d7180b8b68e57a2bec90fcbfd699eead7271a7025`;
  `VER_INFO/HDD_INFO.TXT` (72 B) `9f014643ed9f4e1359d418f415f264f943e027669b872fc7675f3d99d9bc650a`.
  Every hash equals the one the original record gives.
- **Tools:** Python 3.13.18; `tools/rdstm_place.py`, `tools/rdstm_links.py`,
  `tools/mapcode_l3.py`, `tools/hddinfo_variants.py`,
  `tools/hddinfo_check2_matrix.py`, `tools/datavol_trace.py`,
  `tools/ind_mutate.py`, `tools/cmp_read_l3.py`, `tools/nk_decomp.py`
  (all at `origin/main` `ab1d3a2` and its parents)
- **Claims:** C-2520
- **Supersedes:** none
- **Superseded by:** none

## Question

Do the five shortest experiment records merged on 2026-11-20 reproduce when
their key commands are re-run, unchanged, by a different session?

## Hypothesis

They reproduce exactly, because the tools are deterministic. **Falsifier:**
any count, verdict or `pdata` classification below that differs from the
number printed in the original record.

## Inputs

Selection: `wc -l docs/experiments/EXP-2026-11-20-*.md`, then the five
shortest (16 records on 2026-11-20): M4.16b (107 lines), M4.16e (129),
M2.19 (184), M4.48 (189), M3.3 (199). The coordinator's instruction for this
pass (records of the last 24 h) replaces the 2026-11-06 list named in the H19
Goal (M2.6, M3.5, M3.10, M9.1, M8.E1); those older records are not covered here.

## Method

1. **Sample and hash** as above (`sha256sum`).
2. **Commands** (worktree root; `F=/home/user/scratch/factory-eu`,
   `CARD=/home/user/OSM2Leaf/archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img`):

```bash
F=/home/user/scratch/factory-eu
CARD=/home/user/OSM2Leaf/archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img
IMG=archive/head256.img
S=/home/user/scratch/h19
# M4.16b
python3 tools/rdstm_place.py place-all $F/RDSTM001/LCTBL001.DAT $F/RDSTM001/RDSTM001.DAT $F/MAPAL001
# M4.16e
python3 tools/rdstm_links.py groups $F/RDSTM001/RDSTM001.DAT
python3 tools/rdstm_links.py check $F/RDSTM001/RDSTM001.DAT $F/MAPAL001 --set 0
python3 tools/rdstm_links.py place $F/RDSTM001/LCTBL001.DAT $F/RDSTM001/RDSTM001.DAT $F/MAPAL001 --table-pair 0
# M2.19
mkdir -p $S/m219
python3 tools/mapcode_l3.py extract $CARD -o $S/m219/HDD_INFO.TXT
python3 tools/hddinfo_variants.py $S/m219/HDD_INFO.TXT $S/m219/variants
python3 tools/hddinfo_check2_matrix.py run $IMG $S/m219/HDD_INFO.TXT $S/m219/variants --bounds 0x010:0x010 --bounds 0x001:0x0ff --tsv $S/m219/m2.19.tsv --all
python3 tools/nk_decomp.py pdata --image-start 0x3e00200 --module AppLaunch.dll $IMG 0x03bd2ce4 0x03bd2ecc
# M4.48
python3 tools/datavol_trace.py table $IMG
python3 tools/datavol_trace.py calls $IMG --field 0x18c --size 20
python3 tools/datavol_trace.py taint $IMG --module Navi.exe --global 0x00d8b070 --buffer 0x009c9600 --buffer 0x009c8600 --buffer 0x00625668 --buffer 0x01205040 --buffer 0x00e23cc0 --depth 2 --field 0x184 --size 8
python3 tools/nk_decomp.py pdata $IMG --module Navi.exe 0x0041a438 0x0041a304 0x00377ae0 0x0040b258 0x003f7008 0x00377870
# M3.3 (card dir = copies of CMP.LST and the ADDRE001 pair from $F)
mkdir -p $S/m33/card/REFER001
cp $F/CMP.LST $S/m33/card/
cp $F/REFER001/ADDRE001.DAT.cmp $F/REFER001/ADDRE001.DAT.ind $S/m33/card/REFER001/
python3 tools/ind_mutate.py --ind $S/m33/card/REFER001/ADDRE001.DAT.ind --out $S/m33/mut
python3 tools/cmp_read_l3.py batch $IMG --card $S/m33/card --name REFER001/ADDRE001.DAT --mutants $S/m33/mut --json-out $S/m33/batch.json
python3 tools/nk_decomp.py pdata $IMG --module Navi.exe 0x0041c7dc 0x0041c8c4 0x0041c5f0 0x0041bbec
```

3. **Controls.** These are the records' own controls, re-run: random and
   shuffled baselines (M4.16b/e), the factory, min-above and no-file runs
   (M2.19), the bounds-reader hit and the index-7/8 field requests (M4.48),
   and the factory pair plus the six rejecting variants (M3.3). A record
   reproduces only if its controls also come out as recorded.
4. **Scope.** This covers the headline counts and VAs of the five records.
   Not re-run: secondary tables (M4.16b per-table disagreement breakdown
   except the totals line, the M2.19 regression of the M2.4 matrix, the
   M3.3 fragment-target runs). EU 2011 only, which is the only build these
   records use.
5. **Falsifier** stated above.

## Observations

| Record | Claim(s) | Command | Recorded | Re-run 2026-11-20 | Reproduced? |
| --- | --- | --- | --- | --- | --- |
| M4.16b | C-5400 | `rdstm_place.py place-all` | joined 110795, placed_l2 110788, country 110788, random 2048/27998, nbr <1 km 94551/95176, shuffled 129 | identical (totals line, 2 m 30 s) | yes |
| M4.16b | C-5401 | same | placed_l4 60321, <5 km 60321, shuffled 256 | identical | yes |
| M4.16b | C-5402 | same | code-only: lctbl_field_absent 46822 | `lctbl_field_absent_rdstm_has_0 46822` | yes |
| M4.16b | C-5403 | same | role1=rev(role0) 24948/66443 | `rev 24948 rev_n 66443` | yes |
| M4.16e | groups | `rdstm_links.py groups` | set 1: groups 3132, all referenced 3132/3132 | identical (set 0: 33/33) | yes |
| M4.16e | check | `rdstm_links.py check --set 0` | node is a link end 417540, random 1812 | 417540, random 1812 | yes |
| M4.16e | place | `rdstm_links.py place --table-pair 0` | 8532/8532 in country 203, random 106/2000 | 8532/8532, random 106/2000 | yes |
| M2.19 | check 2, pair A | `hddinfo_check2_matrix.py run` | fw {ACCEPT 77, REJECT 12}, agree 89/89, logged 12/12 | identical | yes |
| M2.19 | check 2, pair B | same | {ACCEPT 81, REJECT 8}, 89/89, logged 8/8 | identical | yes |
| M2.19 | router A | same | return {0x50 18, pass 59, 0x51 10, 0x50+0x51 2}; halt {0x50 20, pass 59, 0x51 10} | identical | yes |
| M2.19 | router B | same | {0x50 20, pass 61, 0x51 8} both | identical | yes |
| M2.19 | controls | same | 4 controls ok (each pair) | 4/4 ok each pair | yes |
| M2.19 | VAs | `nk_decomp pdata` (AppLaunch, build B start `0x3e00200`) | fn `0x03bd2ce4`, `0x03bd2ecc` | both `START` (lengths 0x1e8, 0x3c) | yes |
| M4.48 | C-5286 | `datavol_trace.py table` | table `0x01e33290`, idx 9 = `0x18c..0x1a0` | identical | yes |
| M4.48 | C-5287 | `datavol_trace.py calls` | 31 sites, 27 resolved, 0 field requests, 5 whole-block | identical | yes |
| M4.48 | C-5288 | `datavol_trace.py taint` | 40 functions, 70 accesses, control 4 hits | identical | yes |
| M4.48 | C-5289 | `nk_decomp pdata` | 6 fns `START` | all 6 `START` | yes |
| M3.3 | batch | `cmp_read_l3.py batch` | factory ACCEPT; 6 variants REJECT (agree); count_p1 ACCEPT (disagree); count_m1 WRONG first_diff 65536 (disagree) | identical, 9 rows (1 m 44 s) | yes |
| M3.3 | VAs | `nk_decomp pdata` | fn `0x0041c7dc`, `0x0041c8c4`, `0x0041c5f0`, `0x0041bbec` | all `START` | yes |

Mutants: `ind_mutate.py` wrote the same 8 variants (`count_m1 count_p1 off0_1
off_last_0 off_last_m1 off_last_p1 size_20000 size_8000`). `mapcode_l3
extract` wrote 72 B with the recorded hash; `hddinfo_variants` wrote 89
variants.

## Interpretation

- **FACT (C-2520):** all 19 checked rows of the five
  shortest 2026-11-20 records (M4.16b, M4.16e, M2.19, M4.48, M3.3) reproduce
  exactly from their committed commands and recorded input hashes, controls
  included. No retraction is needed.
- **OBSERVED:** these five records are short but not thin. Each has a
  runnable command block, sample hashes and controls, so H19's concern
  (records with no command block) does not apply to this batch.
- **UNKNOWN:** the 2026-11-06 records named in the H19 Goal (M2.6, M3.5,
  M3.10, M9.1, M8.E1) were not re-checked in this pass.

## Conclusion

H19 is done for the coordinator's selection: 19 of 19 rows reproduce, and
there are no disagreements to put in `claims.md` beyond C-2520. If the older
2026-11-06 list still matters, it needs its own pass. A reader can check every
number above against the commands in Method.
